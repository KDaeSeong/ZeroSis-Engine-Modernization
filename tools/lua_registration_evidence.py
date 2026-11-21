"""Bind exact registrar execution evidence to the current compiled SDK."""
import json
from pathlib import Path
from collect_baseline import PROJECT, digest, read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from define_lua_registration_patches import BASE, FILES, candidate_text, patches
from build_lua_registration import fixture_text


def validate():
    root=PROJECT/'evidence/lua_registration'
    build,result,declared=(json.loads((root/name).read_text(encoding='utf-8')) for name in ('build_result.json','conformance.json','caller_patch_plan.json'))
    check_artifacts([build,result,declared])
    if result['status']!='SDK_LUA_REGISTRATION_NATIVE_PASS' or result['issues'] or result['native_checks']!=243512 or len(result['runs'])!=20:
        raise RuntimeError('Registrar native evidence incomplete')
    if not build['candidate_matches_generated_sdk'] or not result['candidate_matches_generated_sdk']:
        raise RuntimeError('Only proposed registrar sources were tested')
    if not build['entire_scoped_template_included']:
        raise RuntimeError('Registrar execution requires the complete scoped instance implementation')
    if result['method_counts']!={'Fractal':2,'Map':36,'Game':262,'Player':787,'Team':141} or result['exact_sdk_function_bodies']!=22:
        raise RuntimeError('Registrar exact-body or method coverage changed')
    if result['tested_optimizations']!=['/O2','/Od'] or result['sequence_failure_boundaries']!=7:
        raise RuntimeError('Registrar error/configuration coverage changed')
    original_expected={'Fractal':8,'GameInfo':75,'Map':83,'Game':540,'Player':1878,'Team':582}
    # The private borrowed-reference tables add allocation boundaries for Player and Team.
    candidate_expected={**original_expected,'Player':2032,'Team':736}
    for variant,sweeps in result['failure_sweeps'].items():
        expected=candidate_expected if variant.startswith('candidate') else original_expected
        if {k:v['failures'] for k,v in sweeps['lua'].items()}!=expected:
            raise RuntimeError('Registrar Lua allocation coverage changed: '+variant)
        # Normal metadata registration does not allocate through C++ operator new.
        # Separate error-path execution covers FLua error formatting allocation failure.
        if any(v['failures'] for v in sweeps['cpp'].values()):
            raise RuntimeError('Registrar C++ allocation behavior changed')
        log=root/(variant+'_exception-allocation.log')
        if 'ERROR_EXCEPTION_ALLOCATION|1|error_formatting_allocation_failure|stack_lock_heap_restored' not in read_text(log):
            raise RuntimeError('Registrar error formatting failure not checked')
    if len(result['failure_sweeps'])!=4 or any(row['exit_code'] or not row['checks'] for row in result['runs']):
        raise RuntimeError('Registrar native execution failed')
    for key in ('original_failure_suppression_reproduced','candidate_short_circuit_verified','candidate_stack_lock_heap_recovery',
                'candidate_success_metadata_and_borrowed_identity_preserved','real_lua_flua_executed'):
        if not result[key]:raise RuntimeError('Registrar contract evidence missing: '+key)
    if any(result[k] for k in ('gameplay_handler_bodies_executed','real_game_object_lifetimes_verified','gamecore_loaded',
                              'game_launched','whole_game_library_registration_verified','game_multicore_verified')):
        raise RuntimeError('Registrar fixture claims full game execution')
    expected_fixture,sources,bodies,rosters=fixture_text()
    if Path(build['fixture']['path']).read_text(encoding='utf-8')!=expected_fixture or build['extracted_bodies']!=bodies or build['method_rosters']!=rosters:
        raise RuntimeError('Executed fixture differs from exact SDK registration bodies')
    for source,text in sources.items():
        if (PROJECT/'Source/SDK_BNW_x64'/source).read_bytes().decode('latin1')!=text:
            raise RuntimeError('Compiled registrar source differs from candidate: '+source)
    pp=PROJECT/'Source/Porting/sdk_x64_patches.json'
    plan,base=(json.loads(p.read_text(encoding='utf-8')) for p in (pp,BASE))
    if len(base['patches'])!=603 or [p for p in plan['patches'] if not p['id'].startswith(('lua_fractal_','fractal_numeric_', 'lua_borrowed_'))]!=base['patches']+patches() or len(plan['patches'])!=693 or declared['patches']!=patches():
        raise RuntimeError('Registrar patches changed the accepted 603-patch baseline')
    sdk=json.loads((PROJECT/'evidence/sdk_x64/build_result.json').read_text(encoding='utf-8'))
    if sdk['status']!='SDK_X64_ALL_OBJECTS_COMPILED' or len(sdk['objects'])!=161 or sdk['patch_specification']['sha256']!=digest(pp):
        raise RuntimeError('Registrar candidate not compiled in current GameCore')
    fixture=build['fixture']
    for variant,row in build['builds'].items():
        if not any(Path(item['path'])==Path(fixture['path']) and item['sha256']==fixture['sha256'] for item in row['compiler_inputs']):
            raise RuntimeError('Registrar fixture not consumed by compiler')
        if row['optimization'] not in ('/Od','/O2'):raise RuntimeError('Unexpected registrar optimization')
        if not all(symbol in read_text(Path(row['map']['path'])) for symbol in ('CCallWithErrorHandling','lua_cpcall','lua_close')):
            raise RuntimeError('Actual Lua/FLua boundary absent from test executable')
    entry={'name':'LuaRegistrationCallers','build':artifact(root/'build_result.json'),'conformance':artifact(root/'conformance.json'),
        'caller_plan':artifact(root/'caller_patch_plan.json'),'validator':artifact(Path(__file__).resolve()),
        'scope':result['scope']}
    return build,result,entry


if __name__=='__main__':
    _,result,_=validate();print(json.dumps({'status':'LUA_REGISTRATION_EVIDENCE_PASS','checks':result['native_checks'],'compiled_gamecore_objects':161}))
