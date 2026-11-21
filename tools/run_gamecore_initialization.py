"""Run the actual x64 GameCore initializer in a fresh copy of the verified host bundle.

This is a runtime test, separate from the component-only verification workflow.
It never starts the installed Civilization V executable or copies user saves.
"""
import argparse,ctypes,json,shutil,subprocess,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from collect_baseline import PROJECT,digest
from native_host_evidence import validate
from probe_world_builder import artifact


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--language',choices=('en_US','ko_KR'),default='en_US')
    parser.add_argument('--mode',choices=('initialize','check-core'),default='initialize')
    parser.add_argument('--timeout',type=int,default=60)
    args=parser.parse_args()
    if not 10<=args.timeout<=300:parser.error('Timeout must be between 10 and 300 seconds')
    build,_,bundle,_=validate()
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:12]
    directory=PROJECT/'Build/HostRuntime'/run_id
    evidence=PROJECT/'evidence/host_runtime'/run_id
    directory.mkdir(parents=True,exist_ok=False);evidence.mkdir(parents=True,exist_ok=False)
    allowed={'ZeroSisHost_x64.exe','CvGameCoreDLL_Expansion2_x64.dll','ZeroSisDatabase_x64.dll','ZeroSisLocalization_x64.dll',
        'rules.db','localization.db','icudt44l.dat','audio-catalog.bin','script-catalog.bin'}
    if {Path(row['path']).name for row in bundle['files']}!=allowed:raise RuntimeError('Unexpected runtime bundle files')
    pinned=[{'path':row['path'],'sha256':row['sha256']} for row in bundle['files']]
    pinned.append(bundle['manifest'])
    copies=[]
    for row in pinned:
        source=Path(row['path']);target=directory/source.name
        if digest(source)!=row['sha256']:raise RuntimeError('Runtime source changed before copying')
        shutil.copy2(source,target)
        if digest(target)!=row['sha256']:raise RuntimeError('Runtime copy differs')
        copies.append({'source':str(source),**artifact(target)})
    before={str(path):digest(path) for path in directory.iterdir() if path.is_file()}
    metadata={}
    for name,source in (('host_build',PROJECT/'evidence/host/build_result.json'),('bundle',PROJECT/'evidence/host/bundle.json'),
                        ('gamecore_link',PROJECT/'evidence/sdk_x64/link_analysis.json'),('runner',Path(__file__).resolve())):
        target=evidence/(name+('.py' if name=='runner' else '.json'));shutil.copy2(source,target);metadata[name]=artifact(target)
    snapshots=[]
    for row in build['sources']:
        source=Path(row['path']);target=evidence/'Source/Host'/source.name;target.parent.mkdir(parents=True,exist_ok=True)
        if digest(source)!=row['sha256']:raise RuntimeError('Host source changed before runtime snapshot')
        shutil.copy2(source,target);snapshots.append({'original_source':str(source),**artifact(target)})
    command=[str(directory/'ZeroSisHost_x64.exe'),'--'+args.mode,args.language]
    request={'run_id':run_id,'captured_at_utc':datetime.now(timezone.utc).isoformat(),
        **metadata,'host_source_snapshots':snapshots,'command':command,'cwd':str(directory),
        'timeout_seconds':args.timeout,'inputs':copies,'source_inputs':pinned,
        'mode':args.mode,'scope':'ACTUAL_GAMECORE_INITIALIZATION_AND_OPTIONAL_LUA_PROBE_NO_NEW_GAME_OR_TURNS'}
    (evidence/'request.json').write_text(json.dumps(request,indent=2)+'\n',encoding='utf-8')
    print('RUN_ACTUAL_GAMECORE_INITIALIZATION '+run_id,flush=True)
    # Child processes inherit the error mode; only this temporary Python runner changes it.
    # Avoid Windows crash/error dialogs for this bounded console test.
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.SetErrorMode.argtypes=[ctypes.c_uint];kernel.SetErrorMode.restype=ctypes.c_uint
    old_mode=kernel.SetErrorMode(0x0001|0x0002|0x8000)
    start=time.monotonic()
    try:process=subprocess.Popen(command,cwd=directory,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    finally:kernel.SetErrorMode(old_mode)
    timed_out=False
    try:stdout,stderr=process.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:
        timed_out=True;process.kill();stdout,stderr=process.communicate()
    duration=time.monotonic()-start
    (evidence/'stdout.log').write_bytes(stdout);(evidence/'stderr.log').write_bytes(stderr)
    output=(stdout+stderr).decode('utf-8',errors='replace').replace('\r\n','\n')
    initialized='CORE_INITIALIZED; new game and turn execution remain unimplemented.' in output
    shutdown='CORE_SHUTDOWN_PASS GAMECORE_LOADED=true GAMEPLAY_VERIFIED=false' in output
    core_lua='CORE_LUA_OBSERVATION=' in output
    game_info='GAME_INFO_OBSERVATION=' in output
    core_retirement='CORE_LUA_SHUTDOWN_PASS finalizers=1 player_retired=true team_retired=true owner_lock=true globals_stopped=true' in output
    module_unloaded='CORE_MODULE_UNLOADED=true' in output
    unchanged=all(digest(Path(row['path']))==row['sha256'] for row in pinned)
    copy_unchanged=all(digest(Path(path))==sha for path,sha in before.items())
    files=[artifact(path) for path in sorted(directory.rglob('*')) if path.is_file()]
    generated=[row for row in files if row['path'] not in before]
    passed=process.returncode==0 and initialized and shutdown and unchanged and copy_unchanged and not timed_out
    if args.mode=='check-core':passed=passed and core_lua and game_info and core_retirement and module_unloaded
    status='GAMECORE_INITIALIZATION_PASS' if passed else 'GAMECORE_INITIALIZATION_FAILED'
    report={'status':status,'request':artifact(evidence/'request.json'),'exit_code':process.returncode,
        'exit_code_hex':f'0x{process.returncode & 0xffffffff:08X}','timed_out':timed_out,'duration_seconds':duration,
        'stdout':artifact(evidence/'stdout.log'),'stderr':artifact(evidence/'stderr.log'),'generated_files':generated,
        'source_bundle_unchanged':unchanged,'copied_bundle_unchanged':copy_unchanged,
        'gamecore_load_attempted':True,'gamecore_initialization_verified':initialized,'gamecore_shutdown_verified':shutdown,
        'actual_sdk_lua_observation_verified':core_lua,'actual_player_team_retirement_verified':core_retirement,
        'actual_game_info_observation_verified':game_info,
        'gamecore_module_unloaded_verified':module_unloaded,
        'gamecore_loaded':True if initialized else None,'new_game_verified':False,'turn_execution_verified':False,'game_multicore_verified':False,
        'installed_game_executable_launched':False,'scope':request['scope']}
    (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    summary={key:report[key] for key in ('status','exit_code_hex','timed_out','duration_seconds','gamecore_initialization_verified','gamecore_shutdown_verified','source_bundle_unchanged','copied_bundle_unchanged')}
    summary['report']=str(evidence/'result.json');summary['generated_files']=len(generated)
    print(json.dumps(summary),flush=True)
    print(output[-6000:],flush=True)
    return 0 if status=='GAMECORE_INITIALIZATION_PASS' else 1

if __name__=='__main__':sys.exit(main())
