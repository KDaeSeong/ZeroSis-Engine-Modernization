"""Tie reference-count/cache observations to the exact compiled SDK callers."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from database_evidence import validate as validate_database
from define_database_loader_patches import BASE, PREFIX, GLOBALS, patches
from build_database_loader import SIGNATURES, UNKNOWN, INTERFACE, UTILITY_HEADER, fixtures
from build_bootstrap_component import body
from verify_database_loader import MARKERS, COMMON


def validate():
    root = PROJECT / 'evidence/database_loader'
    build, result, declared = (json.loads((root / n).read_text(encoding='utf-8')) for n in
                               ('build_result.json', 'conformance.json', 'caller_patch_plan.json'))
    check_artifacts([build, result, declared])
    _, _, provider = validate_database(PROJECT / 'evidence/database/candidate/build_result.json')
    if build['database_provider'] != provider or result['status'] != 'DATABASE_LOADER_NATIVE_PASS' or result['issues']:
        raise RuntimeError('Loader evidence or database provider differs')
    if [r['name'] for r in result['runs']] != ['original', 'candidate'] or [r['checks'] for r in result['runs']] != [28, 4180]:
        raise RuntimeError('Loader execution counts changed')
    for row in result['runs']:
        if row['exit_code'] or any(m not in read_text(Path(row['log']['path'])) for m in (*MARKERS[row['name']], COMMON)):
            raise RuntimeError('Required loader ownership/cache observation missing')
    expected = fixtures()
    for row in build['fixtures']:
        p = Path(row['path'])
        if p.read_text(encoding='utf-8') != expected[p.name]:
            raise RuntimeError('Extracted loader fixture changed')
    candidate = expected['database_loader_fixture.h'].split('#else\n', 1)[1]
    for relative, signatures in SIGNATURES.items():
        text = (PROJECT / 'Source/SDK_BNW_x64' / relative).read_bytes().decode('latin1')
        for signature in signatures:
            if body(text, signature).replace('\r\n', '\n') != body(candidate, signature):
                raise RuntimeError('Compiled SDK loader caller differs: ' + signature)
    text = (PROJECT / 'Source/SDK_BNW_x64' / GLOBALS).read_bytes().decode('latin1')
    signature = 'void CvGlobals::releaseDatabaseLoadUtility()'
    if body(text, signature).replace('\r\n', '\n') != body(candidate, signature):
        raise RuntimeError('Compiled owner release differs from executed body')
    for relative, signature in ((UNKNOWN, 'class ICvUnknown\r\n{'), (INTERFACE, 'class ICvDLLDatabaseUtility1'),
                                (UTILITY_HEADER, 'class CvDllDatabaseUtility:')):
        text = (PROJECT / 'Source/SDK_BNW_x64' / relative).read_bytes().decode('latin1')
        if body(text, signature).replace('\r\n', '\n') not in expected['database_loader_abi.h']:
            raise RuntimeError('Compiled loader ownership ABI differs')
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, baseline = (json.loads(p.read_text(encoding='utf-8')) for p in (path, BASE))
    added = patches()
    if len(plan['patches']) != 693 or len(added) != 5 or declared['patches'] != added:
        raise RuntimeError('Loader patch recipe changed')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] != baseline['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)] != added:
        raise RuntimeError('Loader changed accepted SDK baseline')
    sdk = json.loads((PROJECT / 'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status'] != 'SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects']) != 161 or sdk['patch_specification']['sha256'] != digest(path):
        raise RuntimeError('Loader callers not compiled in GameCore')
    header = artifact(PROJECT / 'Source/Porting/ZeroSisHostBinding.h')
    if header not in sdk['support_inputs'] or header not in build['sources']:
        raise RuntimeError('Ownership dispatcher differs between native test and GameCore')
    if not all(result[k] for k in ('caller_owned_references_preserved', 'fresh_loader_reads_changed_rule_rows',
            'factory_before_init_shutdown_verified', 'real_private_windows_heap_used', 'other_game_owners_and_prefetch_instrumented')) or any(result[k] for k in
            ('external_borrower_quiescence_enforced', 'all_game_cache_teardown_complete', 'gc_init_failure_propagation_implemented',
             'whole_gc_lifecycle_verified', 'original_windows_game_binary_executed', 'gamecore_loaded', 'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Loader claim exceeds isolated ownership/cache test scope')
    entry = {'name': 'DatabaseLoaderCallers', 'build': artifact(root / 'build_result.json'),
             'conformance': artifact(root / 'conformance.json'), 'caller_plan': artifact(root / 'caller_patch_plan.json'),
             'validator': artifact(Path(__file__).resolve()),
             'scope': 'EXACT_SDK_LOADER_REFCOUNTS_AND_CACHE_REAL_HEAP_SQLITE_INSTRUMENTED_GAME_PREFETCH_NOT_FULL_GC_LIFECYCLE'}
    return build, result, entry


if __name__ == '__main__':
    _, result, _ = validate()
    print(json.dumps({'status': 'DATABASE_LOADER_EVIDENCE_PASS', 'checks': sum(r['checks'] for r in result['runs']),
                      'compiled_gamecore_objects': 161}))
