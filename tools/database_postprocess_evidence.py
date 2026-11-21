"""Tie SQL behavior and corpus comparisons to the actual compiled SDK function."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from database_evidence import validate as validate_database
from define_database_postprocess_patches import BASE, PREFIX, TARGET, patches
from build_database_postprocess import fixtures
from verify_database_postprocess import MARKERS, COMMON


def validate():
    root = PROJECT / 'evidence/database_postprocess'
    build, result, declared = (json.loads((root / n).read_text(encoding='utf-8')) for n in
                               ('build_result.json', 'conformance.json', 'caller_patch_plan.json'))
    check_artifacts([build, result, declared])
    _, _, provider = validate_database(PROJECT / 'evidence/database/candidate/build_result.json')
    if build['database_provider'] != provider or result['status'] != 'DATABASE_POSTPROCESS_NATIVE_PASS' or result['issues']:
        raise RuntimeError('SQL postprocessing or provider provenance differs')
    if [r['name'] for r in result['runs']] != ['original', 'candidate', 'rollback_failure'] or [r['checks'] for r in result['runs']] != [820, 1109, 64]:
        raise RuntimeError('SQL postprocessing execution counts differ')
    for row in result['runs']:
        text = read_text(Path(row['log']['path']))
        if row['exit_code'] or any(m not in text for m in (*MARKERS[row['name']], COMMON)):
            raise RuntimeError('SQL postprocessing observed behavior missing')
    if not result['normal_rule_outputs_equal'] or len(result['corpus_comparisons']) != 2 or len(result['corpus_runs']) != 4:
        raise RuntimeError('SQL rule comparison coverage incomplete')
    if any(not r['equal_defines_resources'] for r in result['corpus_comparisons']) or any(r['exit_code'] for r in result['corpus_runs']):
        raise RuntimeError('Cached rule outputs changed')
    if result['trigger_failure_cases'] != 8 or result['outer_transaction_cases'] != 4 or not all(result[k] for k in
            ('candidate_trigger_rollbacks_and_retry_verified', 'deferred_commit_failure_rolled_back', 'logger_exception_cleanup_verified',
             'sqlite_whole_transaction_abort_propagated_as_exception')):
        raise RuntimeError('Required SQL transaction failure evidence missing')
    expected = fixtures()
    for row in build['fixtures']:
        path = Path(row['path'])
        if path.read_text(encoding='utf-8') != expected[path.name]:
            raise RuntimeError('Extracted postprocessing body or constants changed')
    added = patches()
    current = (PROJECT / 'Source/SDK_BNW_x64' / TARGET).read_bytes().decode('latin1')
    if any(current.count(p['new']) != 1 for p in added):
        raise RuntimeError('Compiled SDK differs from tested SQL postprocessing')
    pp = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, base = (json.loads(p.read_text(encoding='utf-8')) for p in (pp, BASE))
    if len(plan['patches']) != 693 or len(added) != 3 or declared['patches'] != added:
        raise RuntimeError('SQL postprocessing recipe changed')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] != base['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)] != added:
        raise RuntimeError('SQL postprocessing changed retained SDK patches')
    sdk = json.loads((PROJECT / 'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status'] != 'SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects']) != 161 or sdk['patch_specification']['sha256'] != digest(pp):
        raise RuntimeError('SQL postprocessing not compiled in GameCore')
    if not result['same_accepted_x64_database_used_for_both_algorithms'] or not result['global_database_accessor_instrumented'] or any(result[k] for k in
            ('original_windows_game_binary_executed', 'gc_init_failure_propagation_implemented', 'whole_gc_lifecycle_verified',
             'all_sqlite_failure_modes_rollback_guaranteed', 'gamecore_loaded', 'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Postprocessing evidence exceeds actual component scope')
    entry = {'name': 'DatabasePostprocessCallers', 'build': artifact(root / 'build_result.json'),
             'conformance': artifact(root / 'conformance.json'), 'caller_plan': artifact(root / 'caller_patch_plan.json'),
             'validator': artifact(Path(__file__).resolve()),
             'scope': 'EXACT_SDK_SQL_POSTPROCESSING_REAL_X64_DATABASE_NOT_GC_INITIALIZATION_OR_GAME_RUNTIME'}
    return build, result, entry


if __name__ == '__main__':
    _, result, _ = validate()
    print(json.dumps({'status': 'DATABASE_POSTPROCESS_EVIDENCE_PASS', 'checks': sum(r['checks'] for r in result['runs']),
                      'cached_rules_compared': len(result['corpus_comparisons']), 'compiled_gamecore_objects': 161}))
