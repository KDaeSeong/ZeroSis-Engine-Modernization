"""Bind root lifecycle execution evidence to the exact compiled SDK recipe."""
import json
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from define_gc_lifecycle_patches import BASE,PREFIX,GLOBALS,HEADER,CONTEXT,TYPES,patches,cleanup_statements,type_defaults
from build_gc_lifecycle import SIGNATURES,fixtures
from build_bootstrap_component import body
from verify_gc_lifecycle import MARKER


def validate():
    root=PROJECT/'evidence/gc_lifecycle'
    build,result,declared=(json.loads((root/n).read_text(encoding='utf-8')) for n in ('build_result.json','conformance.json','caller_patch_plan.json'))
    check_artifacts([build,result,declared])
    if result['status']!='GC_LIFECYCLE_NATIVE_PASS' or result['issues']:raise RuntimeError('GC lifecycle native regression failed')
    if [r['name'] for r in result['runs']]!=['original','candidate'] or [r['checks'] for r in result['runs']]!=[450,1297]:raise RuntimeError('GC lifecycle execution accounting changed')
    if [r['observations'] for r in result['runs']]!=[[48,938],[48,0]]:raise RuntimeError('GC lifecycle failure/leak observations differ')
    if MARKER not in read_text(Path(result['runs'][1]['log']['path'])) or any(r['exit_code'] for r in result['runs']):raise RuntimeError('Missing lifecycle observations')
    expected=fixtures()
    for row in build['fixtures']:
        f=Path(row['path'])
        if f.read_text(encoding='utf-8')!=expected[f.name]:raise RuntimeError('GC lifecycle fixture drift')
    candidate=expected['gc_lifecycle_fixture.h'].split('#else\n',1)[1]
    for relative,signatures in SIGNATURES.items():
        text=(PROJECT/'Source/SDK_BNW_x64'/relative).read_bytes().decode('latin1')
        for signature in signatures:
            if body(text,signature).replace('\r\n','\n')!=body(candidate,signature):raise RuntimeError('Compiled GC body differs: '+signature)
    actual=(PROJECT/'Source/SDK_BNW_x64'/TYPES).read_bytes().decode('latin1')
    if body(actual,'void CvTypes::ResetTypes() noexcept').replace('\r\n','\n') not in expected['gc_lifecycle_types.h']:raise RuntimeError('Compiled type reset differs')
    if len(cleanup_statements())!=45 or len(type_defaults())!=68:raise RuntimeError('Lifecycle/type inventory changed')
    header=(PROJECT/'Source/SDK_BNW_x64'/HEADER).read_bytes().decode('latin1').replace('\r\n','\n')
    if 'private:\n\tfriend class CvDllGameContext;\n\tvoid init();\n\tvoid uninit();\npublic:' not in header:raise RuntimeError('Raw GC entrypoints remain externally callable')
    pp=PROJECT/'Source/Porting/sdk_x64_patches.json';plan,base=(json.loads(p.read_text(encoding='utf-8')) for p in (pp,BASE));added=patches()
    if len(plan['patches'])!=693 or len(added)!=12 or declared['patches']!=added:raise RuntimeError('GC lifecycle patch recipe changed')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX, 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]!=base['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)]!=added:raise RuntimeError('GC lifecycle changed accepted baseline')
    sdk=json.loads((PROJECT/'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects'])!=161 or sdk['patch_specification']['sha256']!=digest(pp):raise RuntimeError('Root lifecycle not compiled in GameCore')
    for name in ('ZeroSisHostBinding.h','ZeroSisGlobalsLifecycle.h'):
        entry=artifact(PROJECT/'Source/Porting'/name)
        if entry not in sdk['support_inputs'] or entry not in build['sources']:raise RuntimeError('SDK and lifecycle fixture use different support headers')
    if not all(result[k] for k in ('normal_call_order_equal','exact_gc_context_bodies_executed','real_type_reset_executed','game_children_host_database_instrumented')) or any(result[k] for k in ('all_transitive_children_and_game_state_recovery_verified','borrower_quiescence_enforced','gamecore_loaded','game_launched','game_multicore_verified')):raise RuntimeError('Lifecycle claim exceeds instrumented boundary tests')
    entry={'name':'GCLifecycleCallers','build':artifact(root/'build_result.json'),'conformance':artifact(root/'conformance.json'),
           'caller_plan':artifact(root/'caller_patch_plan.json'),'validator':artifact(Path(__file__).resolve()),
           'scope':'EXACT_GC_CONTEXT_CONTROL_AND_TYPE_RESET_WITH_INSTRUMENTED_SERVICES_NOT_TRANSITIVE_GAME_STATE_RUNTIME'}
    return build,result,entry


if __name__=='__main__':
    _,result,_=validate();print(json.dumps({'status':'GC_LIFECYCLE_EVIDENCE_PASS','checks':sum(r['checks'] for r in result['runs']),'compiled_gamecore_objects':161}))
