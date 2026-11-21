"""Execute import-audited SDK rule cleanup/prefetch components without loading GameCore."""
import json
import re
from pathlib import Path
from collect_baseline import PROJECT, read_text, pe_header
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

MARKERS = {
    'original': ('ORIGINAL|uninit_retains_rule_storage|helper_omits_formation_flavors_counts_maps|wrong_instance_audio|9_unpublished_entry_leaks',),
    'candidate': ('CANDIDATE|40_rule_collections|2_owned_string_arrays|lookup_items_and_counts_reset|borrowers_before_rules|duplicate_clear_safe',
                  'PREFETCH|9_exceptions_preserved|unpublished_entry_destroyed|published_entries_retained_until_caller_cleanup|retry_succeeds')}
COMMON = 'SCOPE|exact_sdk_cleanup_and_prefetch|real_sqlite|instrumented_info_entries_borrowers|no_gamecore_loaded'
CASES = 'CASES|82_partial_cleanup_states|2_generations|instance_ownership|16_normal_prefetch_cycles|9_prefetch_failures'


def main():
    root = PROJECT / 'evidence/info_cleanup'
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
        if result.returncode or count == 0 or any(m not in text for m in (*MARKERS[name], COMMON, CASES)):
            issues.append('Loader ownership/cache observations failed: ' + name)
        rows.append({'name': name, 'executable': artifact(exe), 'exit_code': result.returncode,
                     'log': artifact(log), 'checks': count})
        print(text, flush=True)
    report = {'status': 'INFO_CLEANUP_NATIVE_PASS' if not issues else 'INFO_CLEANUP_NATIVE_FAIL',
              'build': artifact(bp), 'verifier': artifact(Path(__file__).resolve()), 'runs': rows, 'issues': issues,
              'original_uninit_and_helper_leaks_reproduced': not issues,
              'original_wrong_instance_array_release_reproduced': not issues,
              'original_unpublished_entry_leaks': 9, 'candidate_rule_collections_cleared': 40,
              'candidate_string_arrays_cleared': 2, 'partial_cleanup_states_per_variant': 82,
              'prefetch_failures_per_variant': 9, 'normal_prefetch_cycles_per_variant': 16,
              'candidate_preserves_original_exceptions_and_published_entries': not issues,
              'candidate_caller_cleanup_and_retry_verified': not issues,
              'lookup_items_and_counts_cleared': not issues, 'borrower_cleanup_order_verified': not issues,
              'same_accepted_x64_database_used_for_both_algorithms': True,
              'info_entries_and_game_borrowers_instrumented': True,
              'all_sql_and_cache_result_failures_propagated': False,
              'all_concrete_info_constructors_destructors_executed': False,
              'external_borrower_quiescence_enforced': False, 'gc_init_failure_propagation_implemented': False,
              'whole_gc_lifecycle_verified': False, 'original_windows_game_binary_executed': False,
              'gamecore_loaded': False, 'game_launched': False, 'game_multicore_verified': False}
    (root / 'conformance.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(report['status'])
    if issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
