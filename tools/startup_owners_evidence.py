"""Require native ownership/failure evidence to match the compiled SDK bodies."""
import json
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from define_startup_owners_patches import BASE,PREFIX,PLAYER,patches,player_owners,baseline_text
from build_startup_owners import SIGNATURES,fixtures,projected_body
from build_bootstrap_component import body
from verify_startup_owners import COMMON,MARKERS


def validate():
    root=PROJECT/'evidence/startup_owners'
    build,result,declared,audit=(json.loads((root/n).read_text(encoding='utf-8')) for n in ('build_result.json','conformance.json','caller_patch_plan.json','source_audit.json'))
    check_artifacts([build,result,declared,audit])
    if result['status']!='STARTUP_OWNERS_NATIVE_PASS' or result['issues']:raise RuntimeError('Startup ownership native evidence failed')
    if [r['name'] for r in result['runs']]!=['original','candidate'] or [r['checks'] for r in result['runs']]!=[864826,860910]:
        raise RuntimeError('Startup ownership execution accounting differs')
    if [r['actors'] for r in result['runs']]!=[[191,193,17787,64,80],[191,193,0,64,80]] or [r['actions'] for r in result['runs']]!=[[135,134,108],[135,0,0]]:
        raise RuntimeError('Startup ownership case/leak observations differ')
    for row in result['runs']:
        text=read_text(Path(row['log']['path']))
        if row['exit_code'] or COMMON not in text or MARKERS[row['name']] not in text:raise RuntimeError('Missing ownership execution observations')
    expected=fixtures()
    for row in build['fixtures']:
        p=Path(row['path'])
        if p.read_text(encoding='utf-8')!=expected[p.name]:raise RuntimeError('Startup ownership fixture changed')
    candidate=expected['startup_owners_fixture.h'].split('#else\n',1)[1]
    for relative,signatures in SIGNATURES.items():
        text=(PROJECT/'Source/SDK_BNW_x64'/relative).read_bytes().decode('latin1')
        for signature in signatures:
            if projected_body(text,signature)!=body(candidate,signature):raise RuntimeError('Compiled startup ownership body differs: '+signature)
    # The fixture intentionally omits the large player member initializer list;
    # require the production edit to preserve that list byte for byte.
    current=body((PROJECT/'Source/SDK_BNW_x64'/PLAYER).read_bytes().decode('latin1'),'CvPlayer::CvPlayer()')
    prior=body(baseline_text(PLAYER),'CvPlayer::CvPlayer()')
    if current[:current.index('{')]!=prior[:prior.index('{')]:raise RuntimeError('Untested player initializer list changed')
    fields={r[0] for r in player_owners()}
    if audit['original_missing_player_deletes']!=['m_pCulture'] or audit['candidate_missing_player_deletes'] or set(audit['candidate_scoped_children'])!=fields or len(fields)!=26:
        raise RuntimeError('Direct player ownership source inventory differs')
    pp=PROJECT/'Source/Porting/sdk_x64_patches.json';plan,base=(json.loads(p.read_text(encoding='utf-8')) for p in (pp,BASE));added=patches()
    if len(plan['patches'])!=693 or len(added)!=9 or declared['patches']!=added:
        raise RuntimeError('Startup ownership patch recipe differs')
    if [p for p in plan['patches'] if not p['id'].startswith((PREFIX,'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]!=base['patches'] or [p for p in plan['patches'] if p['id'].startswith(PREFIX)]!=added:
        raise RuntimeError('Startup ownership changed accepted SDK baseline')
    sdk=json.loads((PROJECT/'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects'])!=161 or sdk['patch_specification']['sha256']!=digest(pp):
        raise RuntimeError('Startup ownership not compiled in actual GameCore objects')
    if not all(result[k] for k in ('normal_action_order_and_metadata_equal','candidate_direct_child_and_action_cleanup_verified',
            'candidate_duplicate_array_preservation_verified','candidate_failure_retry_verified','child_types_reset_and_hotkey_services_instrumented')) or any(result[k] for k in
            ('player_member_initializer_list_executed','all_nested_child_implementations_verified','entire_action_metadata_transactional',
             'whole_gc_lifecycle_verified','gamecore_loaded','game_launched','game_multicore_verified')):
        raise RuntimeError('Startup ownership claim exceeds isolated body tests')
    entry={'name':'StartupOwnersCallers','build':artifact(root/'build_result.json'),'conformance':artifact(root/'conformance.json'),
           'caller_plan':artifact(root/'caller_patch_plan.json'),'source_audit':artifact(root/'source_audit.json'),'validator':artifact(Path(__file__).resolve()),
           'scope':'EXACT_STARTUP_OWNERSHIP_BODIES_WITH_INSTRUMENTED_CHILD_RESET_HOTKEY_SERVICES_NOT_WHOLE_GC_RECOVERY'}
    return build,result,entry


if __name__=='__main__':
    _,result,_=validate()
    print(json.dumps({'status':'STARTUP_OWNERS_EVIDENCE_PASS','checks':sum(r['checks'] for r in result['runs']),'compiled_gamecore_objects':161}))
