"""Run import-audited ownership components; never load the GameCore DLL."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, digest, pe_header, read_text
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

MARKERS = {
    'original': ('ORIGINAL_THROW|old_released|published_pointer_dangling_not_dereferenced',
                 'ORIGINAL_UNSUPPORTED|old_connection_lost', 'ORIGINAL_SHUTDOWN|owned_host_not_released'),
    'candidate': ('REPLACEMENT|32_cycles|unsupported_and_throw_preserve|identity_no_double_release|publish_before_destroy',
                  'CONCURRENCY|8_workers|512_busy_rejections|query_called_once|gate_reusable',
                  'SHUTDOWN|context_then_host_then_heap|private_heap_host|failed_heap_retry|idempotent',
                  'REENTRANCY|200_busy_rejections|query_release_context_callbacks')}
COMMON = 'SCOPE|exact_sdk_callers_and_release_dispatch|instrumented_host_context|no_gamecore_loaded'


def main():
    root = PROJECT / 'evidence/host_binding'
    bp = root / 'build_result.json'
    build = json.loads(bp.read_text(encoding='utf-8'))
    check_artifacts(build)
    rows, issues = [], []
    allowed = {'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
    for name in ('original', 'candidate'):
        entry = build['builds'][name]
        exe = Path(entry['executable']['path'])
        deps = entry['imports']['dependencies']
        if pe_header(exe)['architecture'] != 'x64' or digest(Path(entry['executable']['log'])) != entry['executable']['log_sha256']:
            raise RuntimeError('Host test build provenance mismatch')
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected host test runtime import')
        result = run([exe], cwd=exe.parent, timeout=30)
        log = root / (name + '_execution.log')
        log.write_bytes(result.stdout + result.stderr)
        text = read_text(log)
        match = re.search(r'^PASS\|(\d+)\s*$', text, re.M)
        checks = int(match[1]) if match else 0
        if result.returncode or checks == 0 or any(m not in text for m in (*MARKERS[name], COMMON)):
            issues.append('Host ownership observations failed: ' + name)
        rows.append({'name': name, 'executable': artifact(exe), 'exit_code': result.returncode,
                     'log': artifact(log), 'checks': checks})
        print(text, flush=True)
    report = {'status': 'HOST_BINDING_NATIVE_PASS' if not issues else 'HOST_BINDING_NATIVE_FAIL',
              'build': artifact(bp), 'verifier': artifact(Path(__file__).resolve()), 'runs': rows, 'issues': issues,
              'original_nonvirtual_delete_diagnostic': artifact(root / 'original_c5205_first_build.txt'),
              'original_delete_behavior_compiler_specific_not_portable': True,
              'original_defects_reproduced': not issues, 'candidate_failure_preservation_verified': not issues,
              'private_heap_host_destroyed_before_heap': not issues, 'heap_failure_retry_verified': not issues,
              'concurrent_mutation_busy_rejections': 512, 'reentrant_mutation_busy_rejections': 200,
              'exact_sdk_callers_and_release_dispatch_executed': True, 'host_and_context_instrumented': True,
              'all_engine_interface_slots_verified': False, 'borrower_quiescence_enforced': False,
              'whole_gc_lifecycle_verified': False, 'gamecore_loaded': False, 'game_launched': False,
              'game_multicore_verified': False}
    (root / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
