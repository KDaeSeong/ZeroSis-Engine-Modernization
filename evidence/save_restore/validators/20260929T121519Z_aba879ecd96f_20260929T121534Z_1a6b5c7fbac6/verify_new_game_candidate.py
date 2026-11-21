"""Verify two actual language runs of the same isolated x64 new-game candidate."""
import argparse,json,re
from pathlib import Path
from collect_baseline import PROJECT
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

ROOT=PROJECT/'evidence/new_game'


def read_artifact(row):
    check_artifacts(row)
    return json.loads(Path(row['path']).read_text(encoding='utf-8'))


def inspect(run_id,root=ROOT,first_turn=False,turn_cycle=False,save_restore=False):
    if not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',run_id):
        raise ValueError('An existing isolated new-game run ID is required')
    result_path=root/run_id/'result.json'
    result=json.loads(result_path.read_text(encoding='utf-8'))
    check_artifacts(result)
    request=read_artifact(result['request']);check_artifacts(request)
    build=read_artifact(request['candidate_build']);check_artifacts(build)
    runtime=read_artifact(request['shared_lua_build']);check_artifacts(runtime)
    sdk=read_artifact(request['new_game_sdk_build']);check_artifacts(sdk)
    if request.get('save_restore_sdk_build'):
        sdk=read_artifact(request['save_restore_sdk_build']);check_artifacts(sdk)
    flags=('cleanup_completed','module_unloaded','candidate_inputs_unchanged','accepted_bundle_unchanged',
           'core_initialized','configuration_verified','new_game_candidate_verified')
    excluded=('timed_out','game_multicore_verified','installed_game_launched',
              'platform_statistics_available')
    status='ISOLATED_NATIVE_SAVE_RESTORE_PASS' if save_restore else ('ISOLATED_TURN_CYCLE_PASS' if turn_cycle else ('ISOLATED_FIRST_TURN_ENTRY_PASS' if first_turn else 'ISOLATED_NEW_GAME_CANDIDATE_PASS'))
    if result['status']!=status or result['exit_code']!=0 \
       or not all(result[key] is True for key in flags) or any(result[key] is not False for key in excluded) \
       or result['turn_execution_verified'] is not turn_cycle or result['host_failures'] or result['script_failures']:
        raise RuntimeError('New-game result is incomplete or has a different scope: '+run_id)
    command=request['command']
    mode='--check-save-restore' if save_restore else ('--check-turn-cycle' if turn_cycle else ('--check-first-turn' if first_turn else '--check-new-game'))
    if len(command)!=3 or command[1]!=mode or command[2] not in ('en_US','ko_KR'):
        raise RuntimeError('Unexpected new-game command')
    output=Path(result['stdout']['path']).read_text(encoding='utf-8')
    error=Path(result['stderr']['path']).read_text(encoding='utf-8')
    if error or 'LANGUAGE='+command[2] not in output or 'PLATFORM_STATISTICS_AVAILABLE=false' not in output:
        raise RuntimeError('Language/platform/error observations differ')
    expected_phases=['read_configuration','apply_configuration','game_init','players_and_map','observe']
    if re.findall(r'^NEW_GAME_PHASE=(.+)$',output,re.M)!=expected_phases or result['phases']!=expected_phases:
        raise RuntimeError('New-game phase sequence differs')
    for field,marker in (('observation','NEW_GAME_OBSERVATION'),('lua_observation','NEW_GAME_LUA_OBSERVATION')):
        matches=re.findall(r'^'+marker+r'=([-\d,]+)$',output,re.M)
        if len(matches)!=1 or [int(value) for value in matches[0].split(',')]!=result[field]:
            raise RuntimeError('New-game measurements do not match their execution log')
    native=result['observation'];lua=result['lua_observation']
    if len(native)!=9 or len(lua)!=8 or native[0]<=0 or native[1]<=0 or native[0]*native[1]!=native[2] \
       or native[3:5]!=[0,1] or min(native[5:7])<=0 or min(native[7:9])<0 \
       or lua[0]!=native[2] or min(lua[1:3])<=0 or sum(lua[1:3])!=lua[0] or lua[3:6]!=[0,2,2] \
       or lua[6]!=sum(native[5:7]) or lua[7]<0:
        raise RuntimeError('Actual SDK/Lua map and player observations are invalid')
    shutdown='NATIVE_RESTORE_SHUTDOWN_PASS GAMECORE_LOADED=true RESTORE_VERIFIED=true RESUMED_TURN_VERIFIED=true' if save_restore else ('TURN_CYCLE_SHUTDOWN_PASS GAMECORE_LOADED=true TURN_CYCLE_VERIFIED=true' if turn_cycle else \
        ('FIRST_TURN_SHUTDOWN_PASS GAMECORE_LOADED=true TURN_ENTRY_VERIFIED=true TURNS_VERIFIED=false' if first_turn else \
        'NEW_GAME_SHUTDOWN_PASS GAMECORE_LOADED=true TURNS_VERIFIED=false'))
    for marker in ('CORE_MODULE_UNLOADED=true',shutdown):
        if output.splitlines().count(marker)!=1:raise RuntimeError('Missing unique shutdown observation')
    events=[{'count':int(count),'event':event} for count,event in re.findall(r'^NEW_GAME_HOST_EVENT=(\d+)\|(.+)$',output,re.M)]
    if events!=result['host_service_events'] or any(item['count']<=0 for item in events):
        raise RuntimeError('Host notification observations differ')
    files={Path(row['path']).name:row for row in request['inputs']}
    if len(files)!=11 or files['ZeroSisHost_x64.exe']['sha256']!=build['executable']['sha256'] \
       or files['ZeroSisLua51_x64.dll']['sha256']!=runtime['lua_dll']['sha256'] \
       or files['CvGameCoreDLL_Expansion2_x64.dll']['sha256']!=sdk['gamecore']['sha256']:
        raise RuntimeError('Candidate host/core/shared Lua identity differs')
    if not Path(files['bundle.manifest']['path']).read_text(encoding='ascii').startswith('ZEROSIS_HOST_BUNDLE_V4\n'):
        raise RuntimeError('New-game execution did not use the shared Lua bundle contract')
    return {'run_id':run_id,'language':command[2],'result':artifact(result_path),
        'inputs':{name:row['sha256'] for name,row in files.items()},'observation':native,'lua_observation':lua,
        'host_service_events':events,'duration_seconds':result['duration_seconds']}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='append',required=True)
    args=parser.parse_args()
    if len(args.run)!=2 or len(set(args.run))!=2:parser.error('Provide two distinct successful language runs')
    rows=[inspect(run_id) for run_id in args.run]
    if {row['language'] for row in rows}!={'en_US','ko_KR'}:raise RuntimeError('Both language runs are required')
    for field in ('inputs','observation','lua_observation','host_service_events'):
        if rows[0][field]!=rows[1][field]:raise RuntimeError('Language run comparison differs: '+field)
    report={'status':'ISOLATED_NEW_GAME_PAIR_PASS','validator':artifact(Path(__file__).resolve()),'runs':rows,
        'new_game_candidate_verified':True,'sdk_lua_counts_match':True,'language_observations_match':True,
        'complete_state_determinism_verified':False,'turn_execution_verified':False,'game_multicore_verified':False,
        'accepted_stage_promoted':False,'installed_game_launched':False,
        'scope':'ACTUAL_X64_CONTINENTS_NEW_GAME_SDK_LUA_OBSERVATION_AND_UNLOAD_IN_TWO_LANGUAGES'}
    (ROOT/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'languages':[row['language'] for row in rows],
        'observation':rows[0]['observation'],'lua_observation':rows[0]['lua_observation']}),flush=True)


if __name__=='__main__':main()
