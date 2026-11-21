"""Validate numeric fault/recovery evidence against the compiled production SDK."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from define_fractal_numeric_patches import BASE,NATIVE,HEADER,LUA,baseline_text,candidate_text,patches
from build_fractal_numeric import fixture_texts


def validate():
    root=PROJECT/'evidence/fractal_numeric'
    build,result,declared=(json.loads((root/name).read_text(encoding='utf-8')) for name in ('build_result.json','conformance.json','caller_patch_plan.json'))
    check_artifacts([build,result,declared])
    if (result['status']!='SDK_FRACTAL_NUMERIC_NATIVE_PASS' or result['issues'] or result['native_checks']!=556730
        or len(result['runs'])!=30 or not all(r['expected_outcome_observed'] for r in result['runs'])):
        raise RuntimeError('Fractal numeric execution evidence incomplete')
    if not build['candidate_matches_generated_sdk'] or not result['candidate_matches_generated_sdk']:
        raise RuntimeError('Only proposed numeric sources were tested')
    if (result['normal_native_scenarios_per_configuration'],result['normal_lua_scenarios_per_configuration'])!=(3186,18):
        raise RuntimeError('Numeric calculation matrix changed')
    if result['tested_optimizations']!=['/O2','/Od'] or result['invalid_initialization_and_ridge_rejections']!={'candidate':29,'candidate_od':29,'candidate_asan':29}:
        raise RuntimeError('Numeric configuration/preflight coverage changed')
    for variant in ('original','original_od'):
        if result['wide_blend_observations'][variant]!=['6','6'] or result['retry_observations'][variant][0]!='20000':
            raise RuntimeError('Original overflow/retry evidence changed')
    for variant in ('candidate','candidate_od'):
        if result['wide_blend_observations'][variant]!=['6','0'] or result['retry_observations'][variant][0]!='2570':
            raise RuntimeError('Numeric correction/retry evidence changed')
    if result['original_asan_fault_inputs']!=['exponent_8','short_hint_buffer','small_rift_grid']:
        raise RuntimeError('Original native memory faults not reproduced')
    for key in ('normal_heights_and_rng_match','original_integer_zero_division_reproduced','candidate_asan_boundaries_rifts_lua_errors_pass',
        'candidate_preflight_failure_preserves_state_and_rng','candidate_retry_failure_preserves_heights','candidate_cpp_errors_become_lua_errors',
        'real_lua_flua_executed','native_fractal_class_and_calculation_bodies_executed','numeric_rng_and_container_owner_adapters',
        'original_retry_has_instrumented_observation_limit'):
        if not result[key]:raise RuntimeError('Numeric contract evidence missing: '+key)
    if any(result[k] for k in ('candidate_retry_failure_rolls_back_rng','borrowed_game_object_lifetimes_verified','gamecore_loaded','game_launched','game_multicore_verified')):
        raise RuntimeError('Numeric component overclaims recovery or game execution')
    for name in (NATIVE,HEADER,LUA):
        if (PROJECT/'Source/SDK_BNW_x64'/name).read_bytes().decode('latin1')!=candidate_text(name):
            raise RuntimeError('Compiled numeric source differs from tested candidate: '+name)
    def declarations(text):return re.sub(r'\s+','',re.sub(r'/\*.*?\*/|//[^\r\n]*','',text,flags=re.S))
    if declarations(baseline_text(HEADER))!=declarations(candidate_text(HEADER)):
        raise RuntimeError('Fractal object declarations/layout changed')
    texts,_=fixture_texts()
    for row in build['fixtures']:
        path=Path(row['path'])
        if path.read_text(encoding='utf-8')!=texts[path.name]:raise RuntimeError('Numeric fixture no longer matches exact inputs')
    pp=PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan,base=(json.loads(p.read_text(encoding='utf-8')) for p in (pp,BASE))
    if len(base['patches'])!=620 or [p for p in plan['patches'] if not p['id'].startswith('lua_borrowed_')]!=base['patches']+patches() or len(plan['patches'])!=693 or declared['patches']!=patches():
        raise RuntimeError('Numeric patches changed the accepted 620-patch baseline')
    sdk=json.loads((PROJECT/'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects'])!=161 or sdk['patch_specification']['sha256']!=digest(pp):
        raise RuntimeError('Numeric candidate not compiled in current GameCore')
    helper=artifact(PROJECT/'Source/Porting/ZeroSisLuaFractalNumeric.h')
    if helper not in sdk['support_inputs'] or helper not in build['sources']:raise RuntimeError('Numeric error helper provenance differs')
    for variant,row in build['builds'].items():
        if not any(Path(item['path'])==Path(helper['path']) and item['sha256']==helper['sha256'] for item in row['compiler_inputs']):
            raise RuntimeError('Numeric error helper not consumed by compiler')
        if not all(symbol in read_text(Path(row['map']['path'])) for symbol in ('CCallWithErrorHandling','lua_pcall','lua_close')):
            raise RuntimeError('Real Lua/FLua error boundaries absent')
    entry={'name':'FractalNumericCallers','build':artifact(root/'build_result.json'),'conformance':artifact(root/'conformance.json'),
        'caller_plan':artifact(root/'caller_patch_plan.json'),'validator':artifact(Path(__file__).resolve()),'scope':result['scope']}
    return build,result,entry


if __name__=='__main__':
    _,result,_=validate();print(json.dumps({'status':'FRACTAL_NUMERIC_EVIDENCE_PASS','checks':result['native_checks'],'compiled_gamecore_objects':161}))
