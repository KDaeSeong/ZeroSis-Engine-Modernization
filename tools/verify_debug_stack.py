"""Execute the import-audited actual SDK stack template in an isolated x64 consumer."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

MARKERS = (
    'ORIGINAL_WALK|actual_SDK_template|AMD64_context_is_null|instrumented_API_boundary',
    'BOUNDARIES|9_backend_cases|3_invalid_contexts|cycle_depth_limits|private_context|callback_exception',
    'CALLBACK|unlocked_cross_thread_symbol_query|shutdown_busy|lease_released',
    'NATIVE_STACK|257_traces|leaf_middle_root_order|addresses_above_4GiB|original_context_unchanged',
    'THREADS|8|256_stack_traces|mixed_symbol_walk|0_backend_overlap',
)


def main():
    root = PROJECT / 'evidence/debug/stack'
    root.mkdir(parents=True, exist_ok=True)
    bp = PROJECT / 'evidence/debug/build_result.json'
    build = json.loads(bp.read_text(encoding='utf-8'))
    check_artifacts(build)
    consumer = build['stack_consumer']
    exe = Path(consumer['executable']['path'])
    allowed = {'kernel32.dll', 'dbghelp.dll', 'psapi.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
    deps = consumer['imports']['dependencies']
    if pe_header(exe)['architecture'] != 'x64' or not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
        raise RuntimeError('Stack consumer architecture/import audit failed')
    execution = run([exe], cwd=exe.parent, timeout=90)
    log = root / 'execution.log'
    log.write_bytes(execution.stdout + execution.stderr)
    text = read_text(log)
    match = re.search(r'^PASS\|(\d+)\s*$', text, re.M)
    issues = []
    if execution.returncode or not match or any(m not in text for m in MARKERS):
        issues.append('Native SDK stack execution or required observations failed')
    report = {'status': 'SDK_X64_STACK_WALK_PASS' if not issues else 'SDK_X64_STACK_WALK_FAIL',
              'build': artifact(bp), 'verifier': artifact(Path(__file__).resolve()),
              'execution': {'exit_code': execution.returncode, 'log': artifact(log), 'checks': int(match[1]) if match else 0},
              'issues': issues, 'native_stack_traces': 257, 'workers': 8, 'concurrent_stack_traces': 256,
              'backend_cases': 9, 'invalid_context_cases': 3, 'backend_overlap': 0 if not issues else None,
              'sdk_template_executed': True, 'original_null_context_observed_at_instrumented_api': not issues,
              'original_null_context_passed_to_windows': False, 'native_stack_termination_proves_complete_trace': False,
              'get_call_stack_and_callstack_formatting_implemented': False,
              'gamecore_loaded': False, 'game_launched': False, 'game_multicore_verified': False}
    (root / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(text)
    print(report['status'])
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
