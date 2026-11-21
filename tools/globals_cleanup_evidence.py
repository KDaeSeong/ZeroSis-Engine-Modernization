"""Require cleanup reproduction to match the SDK bodies compiled into GameCore."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from define_globals_cleanup_patches import BASE, PREFIX, TARGET, patches
from build_globals_cleanup import STRATEGIES, SIGNATURES, fixtures
from build_bootstrap_component import body
from verify_globals_cleanup import MARKERS


def validate():
    root = PROJECT / 'evidence/globals_cleanup'
    build, result, declared = (json.loads((root / name).read_text(encoding='utf-8')) for name in
                               ('build_result.json', 'conformance.json', 'caller_patch_plan.json'))
    check_artifacts([build, result, declared])
    if result['status'] != 'GLOBALS_CLEANUP_NATIVE_PASS' or result['issues']:
        raise RuntimeError('Globals cleanup regression failed')
    for row in result['runs']:
        if row['exit_code'] or row['checks'] < 5000 or row['cases'] != 132 or MARKERS[row['name']] not in read_text(Path(row['log']['path'])):
            raise RuntimeError('Cleanup native observations differ')
    expected_fixture, expected_fields = fixtures()
    fixture = Path(build['fixture']['path']).read_text(encoding='utf-8')
    if fixture != expected_fixture or Path(build['fields']['path']).read_text(encoding='utf-8') != expected_fields:
        raise RuntimeError('Extracted cleanup fixture changed')
    plan_path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan = json.loads(plan_path.read_text(encoding='utf-8'))
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    added = patches()
    if len(plan['patches']) != 693 or len(added) != 1 or declared['patches'] != added:
        raise RuntimeError('Globals cleanup patch recipe changed')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] != baseline['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)] != added:
        raise RuntimeError('Globals cleanup changed a retained SDK patch')
    sdk = json.loads((PROJECT / 'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status'] != 'SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects']) != 161 or sdk['patch_specification']['sha256'] != digest(plan_path):
        raise RuntimeError('Cleanup SDK callers have not compiled')
    current = (PROJECT / 'Source/SDK_BNW_x64' / TARGET).read_bytes().decode('latin1')
    if body(current, 'void CvGlobals::uninit()').replace('\r\n', '\n') != body(
            fixture.split('#else\n', 1)[1], 'void CvGlobals::uninit()'):
        raise RuntimeError('Compiled SDK cleanup differs from tested candidate')
    for relative, signatures in ((TARGET, ('void CvGlobals::uninit()',)), (STRATEGIES, SIGNATURES)):
        text = (PROJECT / 'Source/SDK_BNW_x64' / relative).read_bytes().decode('latin1')
        for signature in signatures:
            if body(text, signature).replace('\r\n', '\n') not in fixture:
                raise RuntimeError('Tested cleanup body differs from compiled SDK: ' + signature)
    if not result['exact_cleanup_bodies_executed'] or not result['other_owners_and_host_instrumented'] or any(result[k] for k in
            ('whole_gc_init_uninit_verified', 'duplicate_gc_shutdown_verified', 'gamecore_loaded', 'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Globals cleanup scope exceeds extracted-body tests')
    entry = {'name': 'GlobalsCleanupCallers', 'build': artifact(root / 'build_result.json'),
             'conformance': artifact(root / 'conformance.json'), 'caller_plan': artifact(root / 'caller_patch_plan.json'),
             'validator': artifact(Path(__file__).resolve()),
             'scope': 'SDK_CLEANUP_BODIES_MATCH_161_COMPILED_OBJECTS_WITH_INSTRUMENTED_DEPENDENCIES_NOT_GAME_RUNTIME'}
    return build, result, entry


if __name__ == '__main__':
    _, result, _ = validate()
    print(json.dumps({'status': 'GLOBALS_CLEANUP_EVIDENCE_PASS', 'cases': 132,
                      'checks': sum(r['checks'] for r in result['runs']), 'compiled_gamecore_objects': 161}))
