"""Validate Fractal ownership/math observations against the compiled SDK."""
import json
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from define_lua_fractal_patches import BASE,SOURCE,candidate_text,patches
from build_lua_fractal import fixture_texts


def validate():
    root=PROJECT/'evidence/lua_fractal'
    build,result,declared=(json.loads((root/name).read_text(encoding='utf-8')) for name in ('build_result.json','conformance.json','caller_patch_plan.json'))
    check_artifacts([build,result,declared])
    if result['status']!='SDK_LUA_FRACTAL_NATIVE_PASS' or result['issues'] or result['native_checks']!=48986 or len(result['runs'])!=22:
        raise RuntimeError('Fractal native evidence incomplete')
    if not build['candidate_matches_generated_sdk'] or not result['candidate_matches_generated_sdk']:
        raise RuntimeError('Only proposed Fractal bodies were tested')
    if result['exact_lua_function_bodies']!=10 or result['tested_lifetime_optimizations']!=['/O2','/Od']:
        raise RuntimeError('Fractal exact-body/configuration coverage changed')
    for variant,values in result['lifetime_failure_sweeps'].items():
        expected={'lua_failures':14,'missing_finalizers':11} if variant.startswith('original') else {'lua_failures':19,'missing_finalizers':0}
        if values!=expected:raise RuntimeError('Fractal allocation coverage changed: '+variant)
    if len(result['lifetime_failure_sweeps'])!=4 or any(row['exit_code'] or not row['checks'] for row in result['runs']):
        raise RuntimeError('Fractal native execution failed')
    if (result['math_scenarios'],result['unchanged_input_math_scenarios'],result['omitted_defaults_vs_original_explicit_defaults_scenarios'],
        result['height_samples_per_scenario'],result['foreign_input_kinds'],result['gc_objects_per_variant'])!=(18,12,6,1290,3,128):
        raise RuntimeError('Fractal numerical or lifetime inputs changed')
    for key in ('math_and_rng_traces_equal','original_duplicate_destruction_observed','original_foreign_native_dispatch_observed',
        'original_missing_optional_arguments_misread','candidate_defaults_parse_before_output','candidate_exactly_once_and_post_destroy_rejection',
        'candidate_lua_allocations_before_native_construction','candidate_weak_registry_survives_finalization_without_retaining_objects',
        'real_lua_flua_executed','real_calculation_bodies_executed_with_adapters','native_lifetime_is_instrumented'):
        if not result[key]:raise RuntimeError('Fractal contract evidence missing: '+key)
    if any(result[k] for k in ('actual_fractal_dynamic_resource_leak_proven','all_fractal_numeric_inputs_validated',
        'borrowed_game_object_lifetimes_verified','gamecore_loaded','game_launched','game_multicore_verified')):
        raise RuntimeError('Fractal component overclaims execution scope')
    source=PROJECT/'Source/SDK_BNW_x64'/SOURCE
    if source.read_bytes().decode('latin1')!=candidate_text():raise RuntimeError('Compiled Fractal source differs from candidate')
    texts,_=fixture_texts()
    for row in build['fixtures']:
        path=Path(row['path'])
        if path.read_text(encoding='utf-8')!=texts[path.name]:raise RuntimeError('Executed Fractal fixture differs from exact SDK inputs')
    pp=PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan,base=(json.loads(p.read_text(encoding='utf-8')) for p in (pp,BASE))
    if len(base['patches'])!=613 or [p for p in plan['patches'] if not p['id'].startswith(('fractal_numeric_', 'lua_borrowed_'))]!=base['patches']+patches() or len(plan['patches'])!=693 or declared['patches']!=patches():
        raise RuntimeError('Fractal patches changed the accepted 613-patch baseline')
    sdk=json.loads((PROJECT/'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects'])!=161 or sdk['patch_specification']['sha256']!=digest(pp):
        raise RuntimeError('Fractal candidate not compiled in current GameCore')
    helper=artifact(PROJECT/'Source/Porting/ZeroSisLuaFractal.h')
    if helper not in sdk['support_inputs'] or helper not in build['sources']:raise RuntimeError('GameCore and tests used different Fractal ownership helpers')
    for variant,row in build['builds'].items():
        if not any(Path(item['path'])==Path(helper['path']) and item['sha256']==helper['sha256'] for item in row['compiler_inputs']):
            raise RuntimeError('Fractal helper not consumed by compiler')
        if not all(symbol in read_text(Path(row['map']['path'])) for symbol in ('CCallWithErrorHandling','lua_close','lua_rawget')):
            raise RuntimeError('Actual Lua/FLua ownership boundary absent from executable')
    entry={'name':'LuaFractalCallers','build':artifact(root/'build_result.json'),'conformance':artifact(root/'conformance.json'),
        'caller_plan':artifact(root/'caller_patch_plan.json'),'validator':artifact(Path(__file__).resolve()),'scope':result['scope']}
    return build,result,entry


if __name__=='__main__':
    _,result,_=validate();print(json.dumps({'status':'LUA_FRACTAL_EVIDENCE_PASS','checks':result['native_checks'],'compiled_gamecore_objects':161}))
