"""Require native ownership/failure evidence to match the compiled SDK bodies."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from database_evidence import validate as validate_database
from define_info_cleanup_patches import BASE, PREFIX, HEADER, patches, collections
from build_info_cleanup import SIGNATURES, fixtures
from build_bootstrap_component import body
from verify_info_cleanup import MARKERS, COMMON, CASES


def validate():
    root = PROJECT / 'evidence/info_cleanup'
    build, result, declared, audit = (json.loads((root / n).read_text(encoding='utf-8')) for n in
                                    ('build_result.json', 'conformance.json', 'caller_patch_plan.json', 'source_audit.json'))
    check_artifacts([build, result, declared, audit])
    _, _, provider = validate_database(PROJECT / 'evidence/database/candidate/build_result.json')
    if build['database_provider'] != provider or result['status'] != 'INFO_CLEANUP_NATIVE_PASS' or result['issues']:
        raise RuntimeError('Info cleanup evidence or database provider differs')
    if [r['name'] for r in result['runs']] != ['original', 'candidate'] or [r['checks'] for r in result['runs']] != [3182, 9557]:
        raise RuntimeError('Info cleanup execution counts differ')
    for row in result['runs']:
        if row['exit_code'] or any(m not in read_text(Path(row['log']['path'])) for m in (*MARKERS[row['name']], COMMON, CASES)):
            raise RuntimeError('Info cleanup ownership observation missing')
    expected = fixtures()
    for row in build['fixtures']:
        p = Path(row['path'])
        if p.read_text(encoding='utf-8') != expected[p.name]:
            raise RuntimeError('Extracted info cleanup fixture changed')
    candidate = expected['info_cleanup_fixture.h'].split('#else\n', 1)[1]
    for relative, signatures in SIGNATURES.items():
        text = (PROJECT / 'Source/SDK_BNW_x64' / relative).read_bytes().decode('latin1')
        for signature in signatures:
            if body(text, signature).replace('\r\n', '\n') != body(candidate, signature.replace('\r\n', '\n')):
                raise RuntimeError('Compiled info storage body differs: ' + signature)
    fields = {name for _, name in collections()}
    if len(audit['candidate_cleanup_fields']) != 40 or set(audit['candidate_cleanup_fields']) != fields or audit['original_missing_collections'] != ['m_paMultiUnitFormationInfo']:
        raise RuntimeError('Direct rule storage source inventory changed')
    pp = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, baseline = (json.loads(p.read_text(encoding='utf-8')) for p in (pp, BASE))
    added = patches()
    if len(plan['patches']) != 693 or len(added) != 4 or declared['patches'] != added:
        raise RuntimeError('Info cleanup patch recipe changed')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] != baseline['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)] != added:
        raise RuntimeError('Info cleanup changed retained SDK patches')
    sdk = json.loads((PROJECT / 'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status'] != 'SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects']) != 161 or sdk['patch_specification']['sha256'] != digest(pp):
        raise RuntimeError('Info cleanup callers not compiled in GameCore')
    if not all(result[k] for k in ('candidate_preserves_original_exceptions_and_published_entries',
            'candidate_caller_cleanup_and_retry_verified', 'lookup_items_and_counts_cleared', 'borrower_cleanup_order_verified',
            'info_entries_and_game_borrowers_instrumented')) or any(result[k] for k in
            ('all_sql_and_cache_result_failures_propagated', 'all_concrete_info_constructors_destructors_executed',
             'external_borrower_quiescence_enforced', 'gc_init_failure_propagation_implemented', 'whole_gc_lifecycle_verified',
             'original_windows_game_binary_executed', 'gamecore_loaded', 'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Info cleanup claim exceeds native component scope')
    entry = {'name': 'InfoCleanupCallers', 'build': artifact(root / 'build_result.json'),
             'conformance': artifact(root / 'conformance.json'), 'caller_plan': artifact(root / 'caller_patch_plan.json'),
             'source_audit': artifact(root / 'source_audit.json'), 'validator': artifact(Path(__file__).resolve()),
             'scope': 'EXACT_RULE_STORAGE_AND_PREFETCH_BODIES_REAL_SQLITE_INSTRUMENTED_INFO_AND_BORROWERS_NOT_FULL_GC_LIFECYCLE'}
    return build, result, entry


if __name__ == '__main__':
    _, result, _ = validate()
    print(json.dumps({'status': 'INFO_CLEANUP_EVIDENCE_PASS', 'checks': sum(r['checks'] for r in result['runs']),
                      'compiled_gamecore_objects': 161}))
