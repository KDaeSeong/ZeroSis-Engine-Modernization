"""Reproduce static Lua sentinel corruption and verify the shared runtime, both directions."""
import json,re,shutil
from pathlib import Path
from collect_baseline import PROJECT,read_text
from native_build import environment_for,run
from build_native_host import compile_program
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

def main():
    root=PROJECT/'evidence/shared_lua_boundary';root.mkdir(parents=True,exist_ok=True)
    static=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text())
    shared=json.loads((PROJECT/'evidence/shared_lua_runtime/build_result.json').read_text());check_artifacts([static,shared])
    rows=[]
    for variant in ('static','shared'):
        library=Path((static['library'] if variant=='static' else shared['lua_library'])['path'])
        for optimization in ('O2','Od'):
            name=variant+'_'+optimization;directory=PROJECT/'Build/SharedLuaBoundary'/name
            env,compiler=environment_for(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),'x64',directory);compiler=Path(compiler)
            fixture=directory/'lua_cross_module_fixture.dll';response=directory/'fixture.rsp'
            flags=['/nologo','/LD','/MD','/'+optimization,'/W4','/WX',f'/I"{PROJECT / "Source/Lua51_x64/src"}"',
                f'"{PROJECT / "Tests/lua_cross_module_fixture.c"}"',f'"{library}"',f'/Fo"{directory / "fixture.obj"}"',f'/Fe"{fixture}"']
            if variant=='shared':flags.append('/DLUA_BUILD_AS_DLL')
            response.write_text('\n'.join(flags)+'\n')
            result=run([compiler,'@'+str(response),'/link','/INCREMENTAL:NO','/MACHINE:X64','/WX','/Brepro'],cwd=directory,env=env,timeout=60)
            log=root/(name+'_build.log');log.write_bytes(result.stdout+result.stderr)
            if result.returncode:raise RuntimeError(read_text(log)[-5000:])
            built=compile_program('sdk_lua_boundary_'+name,PROJECT/'Tests/sdk_lua_cross_module.cpp',libraries=[library],optimization='/'+optimization,
                definitions=('LUA_BUILD_AS_DLL',) if variant=='shared' else (),additional_imports=('ZeroSisLua51_x64.dll',) if variant=='shared' else ())
            exe=Path(built['executable']['path']);runtime_copy=None
            if variant=='shared':
                target=exe.parent/Path(shared['lua_dll']['path']).name;shutil.copy2(shared['lua_dll']['path'],target);runtime_copy=artifact(target)
            result=run([exe,fixture],cwd=exe.parent,timeout=75)
            execution=root/(name+'_execution.log');execution.write_bytes(result.stdout+result.stderr);text=read_text(execution)
            match=re.search(r'rounds=32 host_to_dll=0x([0-9A-F]{8}) dll_to_host=0x([0-9A-F]{8}) GAMECORE_LOADED=false',text)
            if result.returncode or not match:raise RuntimeError('Cross-module harness failed: '+text[-4000:])
            codes=[int(value,16) for value in match.groups()]
            if variant=='static' and any(code!=0xC0000374 for code in codes):raise RuntimeError('Static Lua heap corruption was not reproduced: '+text)
            if variant=='shared' and any(codes):raise RuntimeError('Shared Lua did not recover both directions: '+text)
            rows.append({'variant':variant,'optimization':optimization,'fixture':artifact(fixture),'fixture_source':artifact(PROJECT/'Tests/lua_cross_module_fixture.c'),
                'fixture_response':artifact(response),'fixture_log':artifact(log),'host_build':built,'runtime_copy':runtime_copy,
                'log':artifact(execution),'harness_exit_code':result.returncode,'child_exit_codes':codes,'rounds_per_direction':32})
    check_artifacts([static,shared])
    report={'status':'SHARED_LUA_BOUNDARY_PASS','validator':artifact(Path(__file__).resolve()),'runs':rows,
        'static_heap_corruptions':4,'shared_successful_children':4,'shared_table_rounds':128,
        'gamecore_loaded':False,'full_new_game_verified':False,'shared_provider':artifact(PROJECT/'evidence/shared_lua_runtime/build_result.json')}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','static_heap_corruptions','shared_successful_children','shared_table_rounds')}),flush=True)

if __name__=='__main__':main()
