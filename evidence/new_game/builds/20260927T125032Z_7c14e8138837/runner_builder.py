"""Build/run an isolated new-game candidate; never replace the accepted Stage bundle."""
import argparse,ctypes,json,re,shutil,subprocess,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from collect_baseline import PROJECT,digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

ROOT=PROJECT/'evidence/new_game'

def compile_candidate(shared=False):
    from build_native_host import compile_program
    build_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:12]
    frozen=ROOT/'builds'/build_id;frozen.mkdir(parents=True,exist_ok=False)
    database=json.loads((PROJECT/'evidence/database/candidate/build_result.json').read_text())
    localization=json.loads((PROJECT/'evidence/localization/provider/build_result.json').read_text())
    lua=json.loads((PROJECT/'evidence/lua_provider/build_result.json').read_text())
    runtime=json.loads((PROJECT/'evidence/shared_lua_runtime/build_result.json').read_text()) if shared else None
    if runtime:check_artifacts(runtime)
    streams=json.loads((PROJECT/'evidence/streams/provider/build_result.json').read_text())
    temp_heap=json.loads((PROJECT/'evidence/temp_heap/build_result.json').read_text())
    libraries=[database['library'],localization['library'],runtime['lua_library'] if shared else lua['library'],streams['library'],*temp_heap['x64']['libraries']];check_artifacts(libraries)
    built=compile_program(('ZeroSisNewGameShared_x64_' if shared else 'ZeroSisNewGame_x64_')+build_id,PROJECT/'Source/Host/HostMain.cpp',
        libraries=[Path(item['path']) for item in libraries],definitions=(('ZEROSIS_SHARED_LUA_RUNTIME=1','LUA_BUILD_AS_DLL') if shared else ())+('ZEROSIS_NEW_GAME_TRACE=1',),
        additional_imports=('ZeroSisLua51_x64.dll',) if shared else ())
    if shared:
        if 'ZeroSisLua51_x64.dll' not in built['imports']['dependencies'] or 'dummynode_' in Path(built['map']['path']).read_text(errors='replace'):
            raise RuntimeError('The host still contains a private Lua implementation')
        built['shared_lua_build']=artifact(PROJECT/'evidence/shared_lua_runtime/build_result.json')
    # Keep each compiled candidate and its consumed host headers immutable.
    # Later edits must not erase the provenance of a successful earlier run.
    snapshots={}
    for source in sorted((PROJECT/'Source/Host').glob('*')):
        if not source.is_file():continue
        target=frozen/'Source/Host'/source.name;target.parent.mkdir(parents=True,exist_ok=True)
        expected=artifact(source);shutil.copy2(source,target)
        if digest(target)!=expected['sha256']:raise RuntimeError('Host source changed while freezing the compiled candidate')
        snapshots[source.resolve()]={'original_source':str(source),**artifact(target)}
    for index,row in enumerate(built['compiler_inputs']):
        snapshot=snapshots.get(Path(row['path']).resolve())
        if snapshot:
            if row['sha256']!=snapshot['sha256']:raise RuntimeError('Host source changed during compilation')
            built['compiler_inputs'][index]=snapshot
    for source,name in ((Path(__file__).resolve(),'runner_builder.py'),(PROJECT/'tools/build_native_host.py','host_builder.py')):
        shutil.copy2(source,frozen/name)
    built.update(build_id=build_id,libraries=libraries,builder=artifact(frozen/'runner_builder.py'),
        compiler_driver=artifact(frozen/'host_builder.py'),sources=list(snapshots.values()))
    check_artifacts(built)
    (frozen/'build_result.json').write_text(json.dumps(built,indent=2)+'\n')
    (ROOT/('candidate_build_shared.json' if shared else 'candidate_build.json')).write_text(json.dumps(built,indent=2)+'\n')
    print('NEW_GAME_CANDIDATE_BUILT',flush=True)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--compile',action='store_true')
    parser.add_argument('--shared-lua',action='store_true')
    parser.add_argument('--sdk-new-game',action='store_true')
    parser.add_argument('--first-turn',action='store_true',help='Also bootstrap the initial human turn and verify idle updates')
    parser.add_argument('--turn-cycle',action='store_true',help='Submit SDK force-end-turn input and verify the next human turn')
    parser.add_argument('--language',choices=('en_US','ko_KR'),default='en_US')
    parser.add_argument('--timeout',type=int,default=90);args=parser.parse_args()
    if not 10<=args.timeout<=300:parser.error('Timeout must be between 10 and 300 seconds')
    if args.sdk_new_game and not args.shared_lua:parser.error('The map-failure SDK candidate requires shared Lua')
    if args.turn_cycle and args.first_turn:parser.error('Choose either first-turn entry or a complete turn cycle')
    initial_turn=args.first_turn or args.turn_cycle
    ROOT.mkdir(parents=True,exist_ok=True)
    run_root=PROJECT/('evidence/turn_cycle' if args.turn_cycle else 'evidence/first_turn') if initial_turn else ROOT
    run_root.mkdir(parents=True,exist_ok=True)
    if args.compile:compile_candidate(args.shared_lua)
    build_path=ROOT/('candidate_build_shared.json' if args.shared_lua else 'candidate_build.json')
    build=json.loads(build_path.read_text());check_artifacts(build)
    runtime=json.loads((PROJECT/'evidence/shared_lua_runtime/build_result.json').read_text()) if args.shared_lua else None
    if runtime:check_artifacts(runtime)
    sdk_path=PROJECT/'evidence/new_game_sdk/build_result.json'
    sdk=json.loads(sdk_path.read_text()) if args.sdk_new_game else None
    if sdk:check_artifacts(sdk)
    core=(sdk or runtime)['gamecore'] if runtime else None
    bundle=json.loads((PROJECT/'evidence/host/bundle.json').read_text());check_artifacts(bundle)
    link=json.loads((PROJECT/'evidence/sdk_x64/link_analysis.json').read_text());check_artifacts(link['generated_dll'])
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:12]
    directory=PROJECT/'Build/NewGameRuntime'/run_id;evidence=run_root/run_id
    directory.mkdir(parents=True,exist_ok=False);evidence.mkdir(parents=True,exist_ok=False)
    rows=[]
    for row in bundle['files']:
        name=Path(row['path']).name;source=Path(build['executable']['path']) if name=='ZeroSisHost_x64.exe' else Path(row['path'])
        if runtime and name=='CvGameCoreDLL_Expansion2_x64.dll':source=Path(core['path'])
        target=directory/name;shutil.copy2(source,target)
        if digest(target)!=digest(source):raise RuntimeError('New-game input copy differs')
        rows.append({'source':str(source),**artifact(target)})
    if runtime:
        source=Path(runtime['lua_dll']['path']);target=directory/source.name;shutil.copy2(source,target);rows.append({'source':str(source),**artifact(target)})
    if next(r['sha256'] for r in rows if Path(r['path']).name=='CvGameCoreDLL_Expansion2_x64.dll')!=(core if runtime else link['generated_dll'])['sha256']:
        raise RuntimeError('New-game candidate uses the wrong current GameCore')
    manifest=directory/'bundle.manifest'
    manifest.write_text(('ZEROSIS_HOST_BUNDLE_V4\n' if runtime else 'ZEROSIS_HOST_BUNDLE_V3\n')+''.join(Path(r['path']).name+'|'+r['sha256']+'\n' for r in rows),encoding='ascii')
    rows.append(artifact(manifest))
    snapshots=[]
    for row in build['sources']:
        source=Path(row['path']);target=evidence/'Source/Host'/source.name;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target);snapshots.append({'original_source':row.get('original_source',str(source)),**artifact(target)})
    shutil.copy2(build_path,evidence/'candidate_build.json')
    shutil.copy2(Path(__file__),evidence/'runner.py')
    if runtime:shutil.copy2(PROJECT/'evidence/shared_lua_runtime/build_result.json',evidence/'shared_lua_build.json')
    if sdk:shutil.copy2(sdk_path,evidence/'sdk_build.json')
    command=[str(directory/'ZeroSisHost_x64.exe'),'--check-turn-cycle' if args.turn_cycle else ('--check-first-turn' if args.first_turn else '--check-new-game'),args.language]
    request={'run_id':run_id,'command':command,'cwd':str(directory),'timeout_seconds':args.timeout,
        'candidate_build':artifact(evidence/'candidate_build.json'),'runner':artifact(evidence/'runner.py'),
        'inputs':rows,'host_source_snapshots':snapshots,'gamecore_link':artifact(PROJECT/'evidence/sdk_x64/link_analysis.json'),
        'accepted_bundle':artifact(PROJECT/'evidence/host/bundle.json'),
        'shared_lua_build':artifact(evidence/'shared_lua_build.json') if runtime else None,
        'new_game_sdk_build':artifact(evidence/'sdk_build.json') if sdk else None,
        'scope':'ACTUAL_ISOLATED_SDK_FORCE_END_TURN_CYCLE' if args.turn_cycle else ('ACTUAL_ISOLATED_FIRST_TURN_ENTRY_CANDIDATE' if args.first_turn else
            'ACTUAL_ISOLATED_NEW_GAME_CANDIDATE_NOT_ACCEPTED_HOST_OR_TURN_VERIFICATION')}
    (evidence/'request.json').write_text(json.dumps(request,indent=2)+'\n')
    print('RUN_NEW_GAME '+run_id,flush=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.SetErrorMode.argtypes=[ctypes.c_uint];kernel.SetErrorMode.restype=ctypes.c_uint
    old=kernel.SetErrorMode(0x0001|0x0002|0x8000);start=time.monotonic()
    try:process=subprocess.Popen(command,cwd=directory,stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    finally:kernel.SetErrorMode(old)
    timed_out=False
    try:stdout,stderr=process.communicate(timeout=args.timeout)
    except subprocess.TimeoutExpired:timed_out=True;process.kill();stdout,stderr=process.communicate()
    (evidence/'stdout.log').write_bytes(stdout);(evidence/'stderr.log').write_bytes(stderr)
    output=(stdout+stderr).decode('utf8',errors='replace').replace('\r\n','\n')
    unchanged=all(digest(Path(row['path']))==row['sha256'] for row in rows)
    accepted_unchanged=all(digest(Path(row['path']))==row['sha256'] for row in bundle['files'])
    observation=re.findall(r'^NEW_GAME_OBSERVATION=([-\d,]+)$',output,re.M)
    lua_observation=re.findall(r'^NEW_GAME_LUA_OBSERVATION=([-\d,]+)$',output,re.M)
    values=[int(value) for value in observation[0].split(',')] if len(observation)==1 else []
    lua_values=[int(value) for value in lua_observation[0].split(',')] if len(lua_observation)==1 else []
    measured=len(values)==9 and len(lua_values)==8
    measured=measured and values[0]>0 and values[1]>0 and values[0]*values[1]==values[2] and values[3:5]==[0,1]
    measured=measured and min(values[5:7])>0 and lua_values[0]==values[2] and lua_values[1]+lua_values[2]==lua_values[0]
    measured=measured and min(lua_values[1:3])>0 and lua_values[3:6]==[0,2,2] and lua_values[6]==sum(values[5:7])
    success=process.returncode==0 and measured and unchanged and accepted_unchanged and not timed_out
    first_turn=re.findall(r'^FIRST_TURN_OBSERVATION=([-\d,]+)$',output,re.M)
    turn_values=[int(value) for value in first_turn[0].split(',')] if len(first_turn)==1 else []
    marker='TURN_CYCLE_SHUTDOWN_PASS GAMECORE_LOADED=true TURN_CYCLE_VERIFIED=true' if args.turn_cycle else \
        ('FIRST_TURN_SHUTDOWN_PASS GAMECORE_LOADED=true TURN_ENTRY_VERIFIED=true TURNS_VERIFIED=false' if args.first_turn else \
        'NEW_GAME_SHUTDOWN_PASS GAMECORE_LOADED=true TURNS_VERIFIED=false')
    success=success and 'CORE_MODULE_UNLOADED=true' in output and marker in output
    if initial_turn:success=success and turn_values==[0,0,0,1,1,3]
    cycles=re.findall(r'^TURN_CYCLE_OBSERVATION=([-\d,]+)$',output,re.M)
    cycle_values=[int(value) for value in cycles[0].split(',')] if len(cycles)==1 else []
    if args.turn_cycle:success=success and len(cycle_values)==8 and cycle_values[:6]==[0,1,1,0,1,1] and 1<=cycle_values[6]<=256 and cycle_values[7]==3
    original={row['path'] for row in rows}
    status_prefix='ISOLATED_TURN_CYCLE' if args.turn_cycle else ('ISOLATED_FIRST_TURN_ENTRY' if args.first_turn else 'ISOLATED_NEW_GAME_CANDIDATE')
    report={'status':status_prefix+('_PASS' if success else '_FAILED'),
        'request':artifact(evidence/'request.json'),'exit_code':process.returncode,'exit_code_hex':f'0x{process.returncode&0xffffffff:08X}',
        'timed_out':timed_out,'duration_seconds':time.monotonic()-start,'stdout':artifact(evidence/'stdout.log'),'stderr':artifact(evidence/'stderr.log'),
        'phases':re.findall(r'^NEW_GAME_PHASE=(.+)$',output,re.M),'host_failures':re.findall(r'^HOST_FAILURE: (.+)$',output,re.M),
        'first_turn_phases':re.findall(r'^FIRST_TURN_PHASE=(.+)$',output,re.M),
        'first_turn_states':re.findall(r'^FIRST_TURN_STATE=(.+)$',output,re.M),
        'first_turn_observation':turn_values,'turn_entry_verified':bool(initial_turn and success),
        'turn_cycle_observation':cycle_values,'turn_cycle_verified':bool(args.turn_cycle and success),
        'turn_cycle_states':re.findall(r'^TURN_CYCLE_STATE=(.+)$',output,re.M),
        'turn_cycle_events':[{'count':int(count),'event':event} for count,event in re.findall(r'^TURN_CYCLE_EVENT=(\d+)\|(.+)$',output,re.M)],
        'script_failures':re.findall(r'^SCRIPT_FAILURE: (.+)$',output,re.M),
        'platform_statistics_available':False if 'PLATFORM_STATISTICS_AVAILABLE=false' in output else
            (True if 'PLATFORM_STATISTICS_AVAILABLE=true' in output else None),
        'host_service_events':[{'count':int(count),'event':event} for count,event in re.findall(r'^NEW_GAME_HOST_EVENT=(\d+)\|(.+)$',output,re.M)],
        'cleanup_completed':any(marker in output for marker in ('HOST_CLEANUP_PASS','NEW_GAME_SHUTDOWN_PASS','FIRST_TURN_SHUTDOWN_PASS','TURN_CYCLE_SHUTDOWN_PASS')),
        'module_unloaded':'CORE_MODULE_UNLOADED=true' in output,
        'observation':values,'lua_observation':lua_values,
        'candidate_inputs_unchanged':unchanged,'accepted_bundle_unchanged':accepted_unchanged,
        'generated_files':[artifact(p) for p in sorted(directory.rglob('*')) if p.is_file() and str(p) not in original],
        'core_initialized':'CORE_INITIALIZED; attempting isolated new game.' in output,
        'configuration_verified':'NEW_GAME_CONFIGURATION_VERIFIED' in output,'new_game_candidate_verified':success and measured,
        'turn_execution_verified':bool(args.turn_cycle and success),'game_multicore_verified':False,'installed_game_launched':False}
    (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    (run_root/'latest.json').write_text(json.dumps(artifact(evidence/'result.json'),indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','exit_code_hex','phases','host_failures','observation')}),flush=True)
    print(output[-7000:],flush=True)
    return 0 if success else 1

if __name__=='__main__':sys.exit(main())
