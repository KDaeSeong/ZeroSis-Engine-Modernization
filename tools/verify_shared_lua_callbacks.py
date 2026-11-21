"""Exercise the actual shared Lua native callback boundary in optimized and debug callers."""
import json,re,shutil
from pathlib import Path
from collect_baseline import PROJECT,read_text
from build_native_host import compile_program
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def main():
    root=PROJECT/'evidence/shared_lua_callbacks';root.mkdir(parents=True,exist_ok=True)
    shared_path=PROJECT/'evidence/shared_lua_runtime/build_result.json'
    shared=json.loads(shared_path.read_text());check_artifacts(shared)
    rows=[]
    for optimization in ('O2','Od'):
        built=compile_program('sdk_shared_lua_callbacks_'+optimization,PROJECT/'Tests/sdk_shared_lua_callbacks.cpp',
            libraries=[Path(shared['lua_library']['path'])],optimization='/'+optimization,
            definitions=('LUA_BUILD_AS_DLL',),additional_imports=('ZeroSisLua51_x64.dll',))
        exe=Path(built['executable']['path']);target=exe.parent/Path(shared['lua_dll']['path']).name
        shutil.copy2(shared['lua_dll']['path'],target)
        result=run([exe],cwd=exe.parent,timeout=60)
        log=root/(optimization+'.log');log.write_bytes(result.stdout+result.stderr);output=read_text(log)
        marker=re.search(r'SHARED_LUA_CALLBACKS_PASS checks=(\d+) GAMECORE_LOADED=false',output)
        if result.returncode or not marker or int(marker[1])<=0:raise RuntimeError(output[-4000:])
        rows.append({'optimization':optimization,'build':built,'runtime':artifact(target),
            'checks':int(marker[1]),'exit_code':result.returncode,'log':artifact(log)})
    check_artifacts(shared)
    report={'status':'SHARED_LUA_CALLBACKS_PASS','validator':artifact(Path(__file__).resolve()),
        'shared_provider':artifact(shared_path),'runs':rows,'native_checks':sum(row['checks'] for row in rows),
        'gamecore_loaded':False,'full_new_game_verified':False,
        'scope':'ACTUAL_LUA_DISPATCH_CPP_EXCEPTION_UNWINDING_ERROR_RECOVERY_AND_COROUTINE_REGRESSION'}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'checks':report['native_checks'],'runs':len(rows)}),flush=True)


if __name__=='__main__':main()
