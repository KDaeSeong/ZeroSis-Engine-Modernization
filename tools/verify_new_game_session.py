"""Verify the current session operation gate independently of the accepted Stage bundle."""
import json,re,shutil
from pathlib import Path
from collect_baseline import PROJECT,read_text
from native_build import run
from build_native_host import compile_program
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def main():
    root=PROJECT/'evidence/new_game_session';root.mkdir(parents=True,exist_ok=True)
    database=json.loads((PROJECT/'evidence/database/candidate/build_result.json').read_text())
    lua=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text())
    inputs=[database['library'],database['dll'],lua['library']];check_artifacts(inputs)
    built=compile_program('sdk_new_game_session',PROJECT/'Tests/sdk_native_host.cpp',
        libraries=[Path(database['library']['path']),Path(lua['library']['path'])])
    exe=Path(built['executable']['path']);copy=exe.parent/Path(database['dll']['path']).name
    shutil.copy2(database['dll']['path'],copy)
    result=run([exe],cwd=exe.parent,timeout=60)
    log=root/'execution.log';log.write_bytes(result.stdout+result.stderr);output=read_text(log)
    marker=re.search(r'NATIVE_HOST_TEST_PASS checks=(\d+).*GAMECORE_LOADED=false WITHCORE_SUCCESS=1 WITHCORE_REJECTIONS=9 WITHCORE_OPERATION_ERRORS=1',output)
    if result.returncode or not marker:raise RuntimeError(f'exit=0x{result.returncode&0xffffffff:08X}: '+output[-4000:])
    report={'status':'NEW_GAME_SESSION_COMPONENT_PASS','validator':artifact(Path(__file__).resolve()),'build':built,
        'inputs':inputs,'database_copy':artifact(copy),'log':artifact(log),'native_checks':int(marker[1]),
        'operation_successes':1,'operation_rejections':9,'operation_errors':1,'exit_code':0,'gamecore_loaded':False,
        'scope':'EXACT_HOST_SESSION_OWNER_LOCK_REENTRY_ACTIVE_LUA_CLEANUP_RETRY_AND_INSTRUMENTED_CONTEXT'}
    (root/'conformance.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'checks':report['native_checks']}),flush=True)


if __name__=='__main__':main()
