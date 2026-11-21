"""Require native observations and exact caller/header identity with compiled SDK."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from define_host_binding_patches import BASE, PREFIX, patches
from build_host_binding import SIGNATURES, UNKNOWN, UTILITY, fixtures
from build_bootstrap_component import body
from verify_host_binding import MARKERS, COMMON


def validate():
    root = PROJECT / 'evidence/host_binding'
    build, result, declared = (json.loads((root / n).read_text(encoding='utf-8')) for n in
                               ('build_result.json', 'conformance.json', 'caller_patch_plan.json'))
    check_artifacts([build, result, declared])
    if result['status'] != 'HOST_BINDING_NATIVE_PASS' or result['issues']:
        raise RuntimeError('Host binding native regression failed')
    if [r['name'] for r in result['runs']] != ['original', 'candidate'] or [r['checks'] for r in result['runs']] != [14, 1866]:
        raise RuntimeError('Host binding executions changed')
    for row in result['runs']:
        text = read_text(Path(row['log']['path']))
        if row['exit_code'] or any(m not in text for m in (*MARKERS[row['name']], COMMON)):
            raise RuntimeError('Host binding observation missing')
    expected = fixtures()
    for row in build['fixtures']:
        path = Path(row['path'])
        if path.read_text(encoding='utf-8') != expected[path.name]:
            raise RuntimeError('Host binding extracted fixture changed')
    candidate = expected['host_binding_fixture.h'].split('#else\n', 1)[1]
    for relative, signature in ((UNKNOWN, 'class ICvUnknown\r\n{'),
                                (UNKNOWN, 'static const GUID guidICvUnknown ='),
                                (UTILITY, 'static const GUID guidICvEngineUtility4 =')):
        actual = (PROJECT / 'Source/SDK_BNW_x64' / relative).read_bytes().decode('latin1')
        if body(actual, signature).replace('\r\n', '\n') != body(expected['host_binding_abi.h'], signature.replace('\r\n', '\n')):
            raise RuntimeError('Compiled SDK ownership ABI differs from executed fixture')
    for relative, signatures in SIGNATURES.items():
        actual = (PROJECT / 'Source/SDK_BNW_x64' / relative).read_bytes().decode('latin1')
        for signature in signatures:
            if body(actual, signature).replace('\r\n', '\n') != body(candidate, signature):
                raise RuntimeError('Compiled host caller differs from executed body: ' + signature)
    path = PROJECT / 'Source/Porting/sdk_x64_patches.json'
    plan, baseline = (json.loads(p.read_text(encoding='utf-8')) for p in (path, BASE))
    added = patches()
    if len(plan['patches']) != 693 or len(added) != 4 or declared['patches'] != added:
        raise RuntimeError('Host binding patch recipe changed')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))] != baseline['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)] != added:
        raise RuntimeError('Host binding modified accepted baseline')
    sdk = json.loads((PROJECT / 'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status'] != 'SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects']) != 161 or sdk['patch_specification']['sha256'] != digest(path):
        raise RuntimeError('Host binding callers not compiled in GameCore')
    header = artifact(PROJECT / 'Source/Porting/ZeroSisHostBinding.h')
    if header not in sdk['support_inputs'] or header not in build['sources']:
        raise RuntimeError('Native test and SDK use different ownership headers')
    if not result['exact_sdk_callers_and_release_dispatch_executed'] or not result['host_and_context_instrumented'] or any(result[k] for k in
            ('all_engine_interface_slots_verified', 'borrower_quiescence_enforced', 'whole_gc_lifecycle_verified',
             'gamecore_loaded', 'game_launched', 'game_multicore_verified')):
        raise RuntimeError('Host binding claim exceeds isolated component scope')
    entry = {'name': 'HostBindingCallers', 'build': artifact(root / 'build_result.json'),
             'conformance': artifact(root / 'conformance.json'), 'caller_plan': artifact(root / 'caller_patch_plan.json'),
             'validator': artifact(Path(__file__).resolve()),
             'scope': 'EXACT_BINDING_SHUTDOWN_BODIES_AND_RELEASE_DISPATCH_WITH_INSTRUMENTED_HOST_CONTEXT_NOT_GAME_RUNTIME'}
    return build, result, entry


if __name__ == '__main__':
    _, result, _ = validate()
    print(json.dumps({'status': 'HOST_BINDING_EVIDENCE_PASS', 'checks': sum(r['checks'] for r in result['runs']),
                      'compiled_gamecore_objects': 161}))
