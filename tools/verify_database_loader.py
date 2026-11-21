"""Execute import-audited SDK loader components without loading GameCore."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

MARKERS = {
    'original': ('ORIGINAL_UNINIT|retained_reference_not_released|cache_skips_changed_rules',
                 'ORIGINAL_SHUTDOWN|heap_ends_with_live_loader|dangling_factory_pointer_not_dereferenced'),
    'candidate': ('RESTART|64_cycles|fresh_cache_reads_changed_rules|separate_query_references_survive_owner_release',
                  'FAILURE|16_allocation_failures_and_retry|16_heap_shutdown_failures_and_retry|208_exact_releases',
                  'SHUTDOWN|context_then_loader_then_host_then_heap|factory_before_init|idempotent_owner_release')}
COMMON = 'SCOPE|exact_sdk_refcounts_cache_and_lifecycle_bodies|real_private_heap_and_sqlite|instrumented_other_game_owners|no_gamecore_loaded'


def main():
    root = PROJECT / 'evidence/database_loader'
    bp = root / 'build_result.json'
    build = json.loads(bp.read_text(encoding='utf-8'))
    check_artifacts(build)
    allowed = {'zerosisdatabase_x64.dll', 'kernel32.dll', 'msvcp140.dll', 'vcruntime140.dll', 'vcruntime140_1.dll'}
    if len(build['audits']) != 4:
        raise RuntimeError('Missing loader import audit')
    for row in build['audits']:
        deps = row['dependencies']
        if not deps or any(d.lower() not in allowed and not d.lower().startswith('api-ms-win-crt-') for d in deps):
            raise RuntimeError('Unexpected loader component import')
    rows, issues = [], []
    for name in ('original', 'candidate'):
        exe = Path(build['builds'][name]['executable']['path'])
        if pe_header(exe)['architecture'] != 'x64':
            raise RuntimeError('Loader test is not x64')
        result = run([exe], cwd=exe.parent, timeout=30)
        log = root / (name + '_execution.log')
        log.write_bytes(result.stdout + result.stderr)
        text = read_text(log)
        match = re.search(r'^PASS\|(\d+)\s*$', text, re.M)
        count = int(match[1]) if match else 0
        if result.returncode or count == 0 or any(m not in text for m in (*MARKERS[name], COMMON)):
            issues.append('Loader ownership/cache observations failed: ' + name)
        rows.append({'name': name, 'executable': artifact(exe), 'exit_code': result.returncode,
                     'log': artifact(log), 'checks': count})
        print(text, flush=True)
    report = {'status': 'DATABASE_LOADER_NATIVE_PASS' if not issues else 'DATABASE_LOADER_NATIVE_FAIL',
              'build': artifact(bp), 'verifier': artifact(Path(__file__).resolve()), 'runs': rows, 'issues': issues,
              'original_retained_reference_and_stale_cache_reproduced': not issues,
              'original_pointer_after_heap_end_observed_without_dereference': not issues,
              'candidate_restart_cycles': 64, 'allocation_failure_retries': 16, 'heap_shutdown_failure_retries': 16,
              'candidate_exact_heap_frees': 208, 'caller_owned_references_preserved': not issues,
              'fresh_loader_reads_changed_rule_rows': not issues, 'factory_before_init_shutdown_verified': not issues,
              'same_accepted_x64_database_used_for_both_algorithms': True,
              'other_game_owners_and_prefetch_instrumented': True, 'real_private_windows_heap_used': True,
              'external_borrower_quiescence_enforced': False, 'all_game_cache_teardown_complete': False,
              'gc_init_failure_propagation_implemented': False, 'whole_gc_lifecycle_verified': False,
              'original_windows_game_binary_executed': False, 'gamecore_loaded': False, 'game_launched': False,
              'game_multicore_verified': False}
    (root / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
