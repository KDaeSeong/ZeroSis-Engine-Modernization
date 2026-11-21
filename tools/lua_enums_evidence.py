"""Validate actual enum observations and bind the candidate to compiled SDK inputs."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from define_lua_enum_patches import BASE, SOURCE, SIGNATURES, baseline_text, candidate_text, patches
from build_bootstrap_component import body


def validate():
    root=PROJECT/'evidence/lua_enums'
    build,result,declared=(json.loads((root/name).read_text(encoding='utf-8')) for name in ('build_result.json','conformance.json','caller_patch_plan.json'))
    check_artifacts([build,result,declared])
    if result['status']!='SDK_LUA_ENUM_NATIVE_PASS' or result['issues'] or result['native_checks']!=5808 or len(result['runs'])!=28:
        raise RuntimeError('Enum native evidence incomplete')
    if not build['candidate_matches_generated_sdk'] or not result['candidate_matches_generated_sdk']:
        raise RuntimeError('Only a proposed enum body was tested')
    if result['original_query_leaks_reproduced'] or not result['original_x64_unwind_verified']:
        raise RuntimeError('Do not claim the x64 longjmp leak hypothesis was reproduced')
    if result['candidate_allocation_failures_per_optimization']!={'lua':57,'cpp':51} or result['original_lua_failures_without_leak']!={'O2':56,'_od':56}:
        raise RuntimeError('Enum allocation/unwind observations changed')
    if result['tested_optimizations']!=['/O2','/Od'] or result['corpus_rows']!=58 or result['sql_failures_per_variant']!=4:
        raise RuntimeError('Enum input/configuration coverage changed')
    if any(row['exit_code'] or not row['checks'] for row in result['runs']):raise RuntimeError('Enum execution failed')
    for key in ('original_register_failure_suppression_reproduced','candidate_db_failures_before_table_mutation',
                'candidate_statement_stack_heap_recovery','candidate_table_identity_and_normal_values_preserved','real_flua_wrapper_executed'):
        if not result[key]:raise RuntimeError('Enum contract evidence missing: '+key)
    if any(result[k] for k in ('all_static_enum_families_registered','gamecore_loaded','game_launched',
                              'whole_game_library_registration_verified','game_multicore_verified')):
        raise RuntimeError('Enum component claims whole GameCore execution')
    source=PROJECT/'Source/SDK_BNW_x64'/SOURCE
    if source.read_bytes().decode('latin1')!=candidate_text():raise RuntimeError('Compiled enum source differs from candidate')
    expected_fixture=('#ifdef LUA_ENUM_ORIGINAL\n'+'\n'.join(body(baseline_text(),s) for s in SIGNATURES)
        +'\n#else\n'+'\n'.join(body(candidate_text(),s) for s in SIGNATURES)+'\n#endif\n').replace('\r\n','\n')
    if Path(build['fixture']['path']).read_text(encoding='utf-8')!=expected_fixture:
        raise RuntimeError('Executed enum fixture differs from exact source bodies')
    pp=PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan,base=(json.loads(p.read_text(encoding='utf-8')) for p in (pp,BASE))
    if [p for p in plan['patches'] if not p['id'].startswith(('lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]!=base['patches']+patches() or len(plan['patches'])!=693 or declared['patches']!=patches():
        raise RuntimeError('Enum patches changed the accepted 600-patch baseline')
    sdk=json.loads((PROJECT/'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects'])!=161 or sdk['patch_specification']['sha256']!=digest(pp):
        raise RuntimeError('Enum candidate not compiled in current GameCore')
    helper=artifact(PROJECT/'Source/Porting/ZeroSisLuaEnums.h')
    if helper not in sdk['support_inputs'] or helper not in build['sources']:
        raise RuntimeError('GameCore and fixture used different enum helpers')
    for variant,row in build['builds'].items():
        if not any(Path(item['path'])==Path(helper['path']) and item['sha256']==helper['sha256'] for item in row['compiler_inputs']):
            raise RuntimeError('Enum helper not consumed by compiler')
        if row['optimization'] not in ('/Od','/O2'):raise RuntimeError('Unexpected enum optimization')
        symbols=('CCallWithErrorHandling','lua_cpcall') + (('lua_pcall',) if variant.startswith('candidate') else ())
        if not all(symbol in read_text(Path(row['map']['path'])) for symbol in symbols):
            raise RuntimeError('Actual FLua/Lua boundary absent from test executable')
    entry={'name':'LuaEnumCallers','build':artifact(root/'build_result.json'),'conformance':artifact(root/'conformance.json'),
           'caller_plan':artifact(root/'caller_patch_plan.json'),'validator':artifact(Path(__file__).resolve()),
           'scope':'EXACT_ENUM_WRAPPERS_REAL_DB_LUA_FLUA_MSVC_X64_OD_O2; NO_WHOLE_GAMECORE_EXECUTION'}
    return build,result,entry


if __name__=='__main__':
    _,result,_=validate();print(json.dumps({'status':'LUA_ENUM_EVIDENCE_PASS','checks':result['native_checks'],'compiled_gamecore_objects':161}))
