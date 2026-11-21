"""Match executed construction bodies to the current compiled SDK without game loading."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from define_construction_patches import BASE, PREFIX, patches
from build_construction import SIGNATURES, fixtures
from build_bootstrap_component import body
from verify_construction import MARKERS, COMMON


def validate():
    root = PROJECT / 'evidence/construction'
    build, result, declared = (json.loads((root / name).read_text(encoding='utf-8')) for name in
                               ('build_result.json', 'conformance.json', 'caller_patch_plan.json'))
    check_artifacts([build, result, declared])
    if result['status'] != 'CONSTRUCTION_NATIVE_PASS' or result['issues']:
        raise RuntimeError('Constructor native regression failed')
    if [r['name'] for r in result['runs']] != ['original', 'candidate']:
        raise RuntimeError('Missing original/candidate constructor execution')
    for row in result['runs']:
        text = read_text(Path(row['log']['path']))
        if row['exit_code'] or row['checks'] < 7000 or any(marker not in text for marker in (*COMMON, MARKERS[row['name']])):
            raise RuntimeError('Constructor native observations differ')
    expected = fixtures()
    for fixture in build['fixtures']:
        p = Path(fixture['path'])
        if p.read_text(encoding='utf-8') != expected[p.name]:
            raise RuntimeError('Extracted constructor fixture changed')
    candidate = expected['construction_fixture.h'].split('#else\n', 1)[1]
    for relative, signatures in SIGNATURES.items():
        text = (PROJECT / 'Source/SDK_BNW_x64' / relative).read_bytes().decode('latin1')
        for signature in signatures:
            if body(text, signature).replace('\r\n', '\n') != body(candidate, signature):
                raise RuntimeError('Compiled SDK constructor differs from tested candidate: ' + signature)
    pp = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan = json.loads(pp.read_text(encoding='utf-8'))
    baseline = json.loads(BASE.read_text(encoding='utf-8'))
    added = patches()
    if len(plan['patches']) != 693 or len(added) != 3 or declared['patches'] != added:
        raise RuntimeError('Constructor patch recipe changed')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] != baseline['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)] != added:
        raise RuntimeError('Constructor patch changed retained SDK work')
    sdk = json.loads((PROJECT / 'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status'] != 'SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects']) != 161 or sdk['patch_specification']['sha256'] != digest(pp):
        raise RuntimeError('Constructor changes have not compiled in GameCore')
    if not result['exact_sdk_bodies_executed'] or not result['game_reset_timer_host_containers_instrumented'] or any(result[k] for k in
            ('whole_gc_lifecycle_verified', 'host_side_effects_rolled_back', 'real_game_reset_database_io_executed',
             'gamecore_loaded', 'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Constructor evidence exceeds isolated ownership scope')
    entry = {'name': 'ConstructionCallers', 'build': artifact(root / 'build_result.json'),
             'conformance': artifact(root / 'conformance.json'), 'caller_plan': artifact(root / 'caller_patch_plan.json'),
             'validator': artifact(Path(__file__).resolve()),
             'scope': 'EXACT_GAME_MAP_CONSTRUCTOR_BODIES_MATCH_COMPILED_SDK_WITH_INSTRUMENTED_SERVICES_NOT_GAME_RUNTIME'}
    return build, result, entry


if __name__ == '__main__':
    _, result, _ = validate()
    print(json.dumps({'status': 'CONSTRUCTION_EVIDENCE_PASS', 'failure_cases_per_variant': 26,
                      'checks': sum(r['checks'] for r in result['runs']), 'compiled_gamecore_objects': 161}))
