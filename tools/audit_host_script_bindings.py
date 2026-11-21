"""Capture exact production script binding bodies and unresolved runtime contracts."""
import json,re
from pathlib import Path
from collect_baseline import PROJECT
from build_bootstrap_component import body
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def main():
    sdk=PROJECT/'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2'
    wanted=[('CvDllContext.cpp','ICvScriptSystemUtility1* CvDllGameContext::GetScriptSystemUtility()'),
            ('CvDllScriptSystemUtility.cpp','void CvDllScriptSystemUtility::RegisterScriptLibraries('),
            ('CvDllScriptSystemUtility.cpp','void CvDllScriptSystemUtility::Destroy()'),
            ('Lua/CvLuaSupport.cpp','void LuaSupport::RegisterScriptData('),
            ('Lua/CvLuaEnums.cpp','void CvLuaEnums::Register(lua_State* L)'),
            ('Lua/CvLuaEnums.cpp','void CvLuaEnums::RegisterDynamicEnums(')]
    functions=[]
    for name,signature in wanted:
        path=sdk/name;text=path.read_bytes().decode('latin1');code=body(text,signature)
        functions.append({'source':artifact(path),'signature':signature,'line':text.count('\n',0,text.index(signature))+1,
                          'body':code.replace('\r\n','\n')})
    registration=next(r['body'] for r in functions if 'RegisterScriptData' in r['signature'])
    registrars=re.findall(r'(CvLua\w+)::Register\(L\)',registration)
    if registrars!=['CvLuaEnums','CvLuaFractal','CvLuaGameInfo','CvLuaMap','CvLuaGame','CvLuaPlayer','CvLuaTeam']:
        raise RuntimeError('GameCore script registration sequence changed')
    dynamic=functions[-1]['body']
    if 'ZeroSisLuaEnums::RegisterDynamic(L, GC.GetGameDatabase()' not in dynamic:
        raise RuntimeError('Dynamic enum registration source changed; re-audit required')
    from lua_enums_evidence import validate as validate_lua_enums
    _,enum_result,enum_entry=validate_lua_enums()
    from lua_registration_evidence import validate as validate_lua_registration
    _,registration_result,registration_entry=validate_lua_registration()
    from lua_fractal_evidence import validate as validate_lua_fractal
    _,fractal_result,fractal_entry=validate_lua_fractal()
    from fractal_numeric_evidence import validate as validate_fractal_numeric
    _,numeric_result,numeric_entry=validate_fractal_numeric()
    from lua_borrowed_evidence import validate as validate_lua_borrowed
    _,borrowed_result,borrowed_entry=validate_lua_borrowed()
    lifetime_functions=[]
    for name,signature in (
        ('Lua/CvLuaFractal.cpp','CvFractal* CvLuaFractal::CreateFractal('),
        ('Lua/CvLuaFractal.cpp','int CvLuaFractal::lDestroy('),
        ('Lua/CvLuaFractal.cpp','int CvLuaFractal::lGetHeight('),
        ('Lua/CvLuaFractal.cpp','int CvLuaFractal::lBuildRidges('),
        ('Lua/CvLuaFractal.cpp','int CvLuaFractal::lCreateRifts('),
        ('Lua/CvLuaScopedInstance.h','InstanceType* CvLuaScopedInstance<Derived, InstanceType>::GetInstance('),
        ('CvFractal.cpp','CvFractal::~CvFractal()'),
        ('CvFractal.cpp','void CvFractal::uninit()')):
        path=sdk/name;text=path.read_bytes().decode('latin1')
        lifetime_functions.append({'source':artifact(path),'signature':signature,
            'line':text.count('\n',0,text.index(signature))+1,'body':body(text,signature).replace('\r\n','\n'),
            'component_execution_scope':('EXACT_LUA_BODY_WITH_LIFETIME_SPY_AND_SEPARATE_NATIVE_CALCULATION_ADAPTERS'
                if name=='Lua/CvLuaFractal.cpp' else 'NATIVE_BODY_WITH_CALCULATION_ADAPTERS'
                if name=='CvFractal.cpp' else 'EXACT_SCOPED_TEMPLATE_WITH_REAL_LUA_AND_INSTRUMENTED_GAMEPLAY_OWNERS'),
            'whole_gamecore_execution_verified':False})
    numeric_functions=[]
    for signature in ('void CvFractal::fracInitInternal(', 'void CvFractal::ridgeBuilder('):
        path=sdk/'CvFractal.cpp';text=path.read_bytes().decode('latin1')
        numeric_functions.append({'source':artifact(path),'signature':signature,
            'line':text.count('\n',0,text.index(signature))+1,'body':body(text,signature).replace('\r\n','\n'),
            'invalid_numeric_inputs_executed':True,'whole_gamecore_execution_verified':False})
    assets=json.loads((PROJECT/'evidence/host/script_catalog.json').read_text(encoding='utf-8'));check_artifacts(assets)
    report={'status':'SCRIPT_BINDING_SOURCE_AND_COMPONENT_AUDIT','auditor':artifact(Path(__file__).resolve()),
            'functions':functions,'registrars':registrars,
            'host_sources':[artifact(PROJECT/'Source/Host'/name) for name in ('ScriptSystem.h','ScriptCatalog.h','ScriptMetadata.h','GameCoreSession.h','HostRun.h')],
            'script_catalog':artifact(PROJECT/'evidence/host/script_catalog.json'),
            'enum_component':enum_entry,
            'registration_component':registration_entry,
            'fractal_component':fractal_entry,
            'fractal_numeric_component':numeric_entry,
            'borrowed_component':borrowed_entry,
            'lifetime_functions':lifetime_functions,
            'numeric_functions':numeric_functions,
            'resolved_or_reclassified_findings':[
                {'id':'SCRIPT-ENUM-LUA-UNWIND','priority':'P1','evidence':'The original attempt_032 RegisterDynamicEnums keeps Database::Results live across allocating Lua pushes; the linked Lua provider uses C longjmp.',
                 'status':'NOT_REPRODUCED_IN_TESTED_MSVC_X64_CONFIGURATIONS',
                 'original_lua_failures_without_leak':enum_result['original_lua_failures_without_leak'],
                 'correction':'The original exact SDK body released DB statements under MSVC x64 /EHsc /Od and /O2. Do not infer universal longjmp leaks. The new helper reads DB data before protected Lua publication.'},
                {'id':'SCRIPT-ENUM-QUERY-FAILURE','priority':'P1',
                 'evidence':'Four original query/step/count failures and the Register wrapper ignoring protected-call failure were reproduced. Candidate propagated them and retained successful mappings.',
                 'status':'FIXED_AND_COMPONENT_VERIFIED','actual_full_game_registration_verified':False},
                {'id':'SCRIPT-REGISTRATION-FAILURE','priority':'P1',
                 'evidence':'Six remaining registrar wrappers ignored protected-call failures. Seven sequence boundaries were reproduced with exact SDK registration bodies and real Lua/FLua; the candidate stops and the fixture discards the incomplete VM.',
                 'status':'FIXED_AND_COMPONENT_VERIFIED','native_checks':registration_result['native_checks'],
                 'actual_full_game_registration_verified':False,'real_game_object_lifetimes_verified':False},
                {'id':'SCRIPT-FRACTAL-OWNERSHIP-AND-DEFAULTS','priority':'P1',
                 'evidence':'Exact Lua bodies reproduced foreign dispatch, repeated native destruction and output userdata being mistaken for omitted arguments. Candidate proves VM ownership, exactly-once destruction and parses arguments before output allocation. Native lifetime is instrumented; separate unchanged CvFractal calculations and numeric RNG traces match in 18 scenarios.',
                 'status':'FIXED_AND_COMPONENT_VERIFIED','native_checks':fractal_result['native_checks'],
                 'actual_fractal_dynamic_resource_leak_proven':False,'actual_full_game_registration_verified':False,
                 'borrowed_game_object_lifetimes_verified':False},
                {'id':'SCRIPT-FRACTAL-NUMERIC-INPUTS','priority':'P1',
                 'evidence':'Original divide-by-zero and three ASan heap faults were reproduced with exact native bodies. Candidate guards dimensions/exponents/hints/rifts, uses wide blending, bounds seed-placement retries and translates native exceptions into Lua errors. 3186 native scenarios and 18 Lua scenarios preserve heights/RNG under O2 and Od.',
                 'status':'FIXED_AND_COMPONENT_VERIFIED','native_checks':numeric_result['native_checks'],
                 'actual_full_game_map_generation_verified':False,'retry_failure_rolls_back_rng':False},
                {'id':'SCRIPT-BORROWED-REFERENCE-IDENTITY','priority':'P1',
                 'evidence':'The integrated scoped template rejects forged/stale references and incomplete publication. Four native proxies share lifetime tracking; 34 native boundaries and Deal self-copy preservation are compiled. Exact bodies and real SDK containers were executed with instrumented gameplay owners/services.',
                 'status':'FIXED_AND_COMPONENT_VERIFIED','native_checks':borrowed_result['native_checks'],
                 'actual_gameplay_owner_lifecycle_executed':False,'gamecore_shutdown_verified':False}],
            'open_findings':[
                {'id':'SCRIPT-PATTERN-INCLUDE','priority':'P1','evidence':assets['unresolved_literal_includes'],
                 'status':'EXPLICITLY_UNSUPPORTED','next_action':'Specify and implement optional pattern include selection/order after checking the original host contract.'},
                {'id':'SCRIPT-ACTIVE-ASSET-SET','priority':'P1','evidence':'The explicit catalog contains only base maps and base/Expansion/Expansion2 gameplay scripts.',
                 'status':'PARTIAL_ASSET_SCOPE','next_action':'Integrate active DLC/scenario/mod selection, overrides, UI libraries and game object lifetimes; compare original VM and event semantics.'},
                {'id':'SCRIPT-OBJECT-LIFETIMES','priority':'P1','evidence':[
                    'VM-owned Fractal and borrowed reference identity have bounded component evidence; real gameplay-owner and shutdown execution remain outside that coverage.',
                    'CvLuaScopedInstance validates VM/type/table provenance; native invalidation is compiled, but its metadata lock does not pin gameplay objects after lookup.',
                    'Registration fixture owners are instrumented; real player, city and unit deletion/reuse and finalizers during GameCore shutdown have not been executed.'],
                 'status':'REAL_OWNER_LIFETIME_AND_SHUTDOWN_EXECUTION_PENDING','next_action':'Verify real-host stale-proxy exception handling and owner-thread locking, container alias mutations, and whole GameCore shutdown/finalizer ordering.'},
                {'id':'SCRIPT-MAP-GENERATION-RECOVERY','priority':'P1','evidence':[
                    'A failed bounded ridge placement preserves heights but retains its consumed RNG prefix.',
                    'Lua pcall/error cleanup is verified in isolated components; whole map generation and host session rollback/restart have not been executed.'],
                 'status':'WHOLE_MAP_FAILURE_RECOVERY_PENDING','next_action':'Validate whole map generation failure/restart, game-owned RNG state and original script semantics in the real host.'}],
            'gamecore_loaded':False,'actual_game_library_registration_executed':False,'game_map_generation_verified':False}
    (PROJECT/'evidence/host/script_binding_audit.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'exact_functions':len(functions),'registrars':registrars,'open_findings':len(report['open_findings'])}))


if __name__=='__main__':main()
