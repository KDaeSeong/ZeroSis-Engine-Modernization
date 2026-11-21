"""Run import-audited lifecycle and extracted SDK context-boundary programs."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text, pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def main():
    root = PROJECT / 'evidence/bootstrap'
    bp = root / 'build_result.json'
    build = json.loads(bp.read_text(encoding='utf-8'))
    check_artifacts(build)
    allowed = {'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
    for entry in build['builds'].values():
        executable = entry['executable']
        if pe_header(Path(executable['path']))['architecture'] != 'x64' or digest(Path(executable['log'])) != executable['log_sha256']:
            raise RuntimeError('Bootstrap build provenance differs')
        deps = entry['imports']['dependencies']
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected bootstrap runtime dependency')
    runs = []
    for name, executable_name, args in (
        ('lifecycle', 'lifecycle', []), ('context', 'context', []),
        ('original_duplicate', 'context_original', []), ('original_partial', 'context_original', ['partial']),
    ):
        executable = Path(build['builds'][executable_name]['executable']['path'])
        result = run([executable, *args], cwd=executable.parent, timeout=30)
        log = root / (name + '_execution.log')
        log.write_bytes(result.stdout + result.stderr)
        text = read_text(log)
        match = re.search(r'^PASS\|(\d+)\s*$', text, re.M)
        runs.append({'name': name, 'executable': artifact(executable), 'args': args, 'exit_code': result.returncode,
                     'log': artifact(log), 'checks': int(match[1]) if match else None})
        print(text, flush=True)
    issues = []
    if any(row['exit_code'] for row in runs) or any(not row['checks'] for row in runs[:2]):
        issues.append('Native bootstrap component failed')
    markers = [
        (runs[0], ['CONCURRENCY|8|256_start_calls|one_context', 'FAILURES|12|reverse_cleanup|retained_ownership|explicit_retry',
                   'REENTRANCY|startup_and_shutdown_rejected_without_deadlock']),
        (runs[1], ['CONTEXT_FAILURES|10|all_four_adapter_allocations_and_constructors|clean_retry',
                   'CONTEXT_RECOVERY|idempotent|partial_constructor_no_leak|failed_heap_destroy_retained']),
        (runs[2], ['ORIGINAL_DUPLICATE|contexts=1|adapters=4|heap=0']),
        (runs[3], ['ORIGINAL_PARTIAL|contexts=0|adapters=2|heap=1']),
    ]
    for row, expected in markers:
        text = read_text(Path(row['log']['path']))
        if any(value not in text for value in expected):
            issues.append('Missing bootstrap observation: ' + row['name'])
    report = {'status': 'BOOTSTRAP_NATIVE_COMPONENT_PASS' if not issues else 'BOOTSTRAP_NATIVE_COMPONENT_FAIL',
              'build': artifact(bp), 'verifier': artifact(Path(__file__).resolve()), 'runs': runs, 'issues': issues,
              'lifecycle_failures': 12, 'context_creation_failures': 10, 'workers': 8, 'concurrent_start_calls': 256,
              'duplicate_original_context_reproduced': not issues, 'partial_original_constructor_reproduced': not issues,
              'context_adapter_types_instrumented': True, 'actual_gamecore_context_executed': False,
              'sdk_callers_compiled': False, 'gamecore_loaded': False, 'game_launched': False, 'game_multicore_verified': False}
    (root / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
