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


def verify_city_site_base(city,explore):
    base_dll=city.get('base_explore_build')
    report_refs=[city.get(name) for name in ('base_explore_build_report','base_explore_report')
                 if city.get(name) is not None]
    if not isinstance(base_dll,dict) or not report_refs:
        raise RuntimeError('City-site SDK build lacks frozen Explore DLL and report artifacts')
    check_artifacts(base_dll)
    for base_report in report_refs:
        frozen_report=read_artifact(base_report)
        if frozen_report.get('status')!='EXPLORE_SDK_CANDIDATE_LINKED' or \
           frozen_report.get('build_id')!=explore.get('build_id') or \
           frozen_report.get('gamecore',{}).get('sha256')!=explore.get('gamecore',{}).get('sha256'):
            raise RuntimeError('A frozen city-site base report differs from the selected Explore SDK build')
    if explore.get('status')!='EXPLORE_SDK_CANDIDATE_LINKED' or \
       city.get('base_explore_build_id')!=explore.get('build_id') or \
       base_dll.get('sha256')!=explore.get('gamecore',{}).get('sha256'):
        raise RuntimeError('City-site SDK base exploration build identity differs')


def verify_city_site_worker_metadata(request,result,sdk_city_sites,city_site_workers,save_restore):
    if sdk_city_sites and (not {'city_site_workers_enabled','city_site_workers','city_site_sdk_build'}<=request.keys() or \
                           not {'city_site_workers_enabled','city_site_workers'}<=result.keys()):
        raise RuntimeError('City-site request/result must record explicit worker opt-in and setting')
    enabled=request.get('city_site_workers_enabled',False)
    setting=request.get('city_site_workers',0)
    selected=setting if city_site_workers is None else city_site_workers
    if enabled is not sdk_city_sites or type(setting) is not int or type(selected) is not int or \
       setting!=selected or result.get('city_site_workers_enabled',False) is not sdk_city_sites or \
       type(result.get('city_site_workers',0)) is not int or result.get('city_site_workers',0)!=selected or \
       (not sdk_city_sites and selected!=0) or (sdk_city_sites and selected not in (0,1,2,4)):
        raise RuntimeError('City-site worker request metadata differs from verifier options')
    environment=request.get('environment_overrides')
    if sdk_city_sites:
        if not request.get('explore_sdk_build') or not request.get('save_restore_sdk_build') or \
           not save_restore or not isinstance(environment,dict) or \
           set(environment)!={'ZEROSIS_EXPLORE_WORKERS','ZEROSIS_CITY_SITE_WORKERS'} or \
           environment.get('ZEROSIS_EXPLORE_WORKERS') not in ('0','1','2','4') or \
           environment.get('ZEROSIS_CITY_SITE_WORKERS')!=str(selected):
            raise RuntimeError('City-site SDK verification requires its explicit linked SDK and environment chain')
        if request.get('city_site_sdk_build') is None:
            raise RuntimeError('City-site SDK build artifact is missing')
    elif request.get('city_site_sdk_build') is not None or \
         environment not in [{'ZEROSIS_EXPLORE_WORKERS':str(value)} for value in (0,1,2,4)]:
        raise RuntimeError('Non-city SDK run must retain the original single exploration-worker environment contract')
    return selected


def inspect_unit_action_logs(output,extra_turns,fixture_promotions,fixture_unit_actions):
    all_routes=re.findall(r'^EXTENDED_TURN_CYCLE_INPUT_ROUTE=([^\r\n]*)$',output,re.M)
    all_actions=re.findall(r'^EXTENDED_TURN_CYCLE_ACTION=([^\r\n]*)$',output,re.M)
    if not fixture_unit_actions:
        if all_routes or all_actions:
            raise RuntimeError('Unit-action route or records appeared without their opt-in request')
        return [],[]
    if not fixture_promotions or extra_turns<=0:
        raise RuntimeError('Fixture unit actions require promotions and continued turns')
    if output.count('EXTENDED_TURNS_BEGIN=')!=1 or output.count('EXTENDED_TURNS_COMPLETE=')!=1:
        raise RuntimeError('Fixture unit-action logs lack one extended-turn scope')
    block=output.split('EXTENDED_TURNS_BEGIN=',1)[1].split('EXTENDED_TURNS_COMPLETE=',1)[0]
    routes=re.findall(r'^EXTENDED_TURN_CYCLE_INPUT_ROUTE=([^\r\n]*)$',block,re.M)
    action_lines=re.findall(r'^EXTENDED_TURN_CYCLE_ACTION=([^\r\n]*)$',block,re.M)
    promotion_lines=re.findall(r'^EXTENDED_TURN_CYCLE_PROMOTION=([^\r\n]*)$',block,re.M)
    if len(routes)!=extra_turns or any(route!='SDK_GAME_HANDLE_ACTION' for route in routes) or len(all_routes)!=len(routes):
        raise RuntimeError('Every continued turn must use exactly one SDK_GAME_HANDLE_ACTION input route')
    if len(all_actions)!=len(action_lines):
        raise RuntimeError('A unit-action record fell outside the extended-turn scope')
    if not action_lines or len(action_lines)!=len(promotion_lines):
        raise RuntimeError('Each recorded promotion must have exactly one SDK unit-action record')
    action_rows=[]
    promotion_keys=[]
    for line in action_lines:
        if not re.fullmatch(r'\d+(?:,\d+){4}',line):
            raise RuntimeError('Unit-action record must contain five nonnegative integers')
        turn,player,unit,promotion,action_info_index=map(int,line.split(','))
        action_rows.append({'turn':turn,'player':player,'unit':unit,'promotion_id':promotion,
                            'action_info_index':action_info_index})
    for line in promotion_lines:
        if not re.fullmatch(r'\d+(?:,\d+){7}',line):
            raise RuntimeError('Promotion record must contain eight nonnegative integers')
        promotion_keys.append(tuple(map(int,line.split(',')[:4])))
    action_keys=[(row['turn'],row['player'],row['unit'],row['promotion_id']) for row in action_rows]
    if len(set(action_keys))!=len(action_keys) or len(set(promotion_keys))!=len(promotion_keys) or \
       set(action_keys)!=set(promotion_keys) or any(not 2<=row['turn']<2+extra_turns for row in action_rows):
        raise RuntimeError('SDK unit-action records do not map one-to-one to legal promotion records')
    return routes,action_rows


def inspect(run_id,root=ROOT,first_turn=False,turn_cycle=False,save_restore=False,extra_turns=0,ui_popups=False,fixture_promotions=False,fixture_unit_actions=False,sdk_city_sites=False,city_site_workers=None):
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
    if request.get('explore_sdk_build'):
        sdk=read_artifact(request['explore_sdk_build']);check_artifacts(sdk)
    selected_city_workers=verify_city_site_worker_metadata(
        request,result,sdk_city_sites,city_site_workers,save_restore)
    city_request=request.get('city_site_sdk_build')
    if sdk_city_sites:
        city=read_artifact(city_request);check_artifacts(city)
        explore=read_artifact(request['explore_sdk_build']);check_artifacts(explore)
        if city.get('status')!='CITY_SITE_SDK_CANDIDATE_LINKED':
            raise RuntimeError('City-site SDK candidate is not linked')
        verify_city_site_base(city,explore)
        sdk=city
    flags=('cleanup_completed','module_unloaded','candidate_inputs_unchanged','accepted_bundle_unchanged',
           'core_initialized','configuration_verified','new_game_candidate_verified')
    excluded=('timed_out','game_multicore_verified','installed_game_launched',
              'platform_statistics_available')
    status='ISOLATED_NATIVE_SAVE_RESTORE_PASS' if save_restore else ('ISOLATED_TURN_CYCLE_PASS' if turn_cycle else ('ISOLATED_FIRST_TURN_ENTRY_PASS' if first_turn else 'ISOLATED_NEW_GAME_CANDIDATE_PASS'))
    if request.get('fixture_promotions_enabled',False) is not fixture_promotions or \
       result.get('fixture_promotions_enabled',False) is not fixture_promotions or \
       (fixture_promotions and (not ui_popups or not save_restore or extra_turns<=0)):
        raise RuntimeError('Fixture promotion verification requires its matching explicit request')
    if request.get('fixture_unit_actions_enabled',False) is not fixture_unit_actions or \
       result.get('fixture_unit_actions_enabled',False) is not fixture_unit_actions or \
       (fixture_unit_actions and (not fixture_promotions or not ui_popups or not save_restore or extra_turns<=0)):
        raise RuntimeError('Fixture unit-action verification requires its matching explicit request')
    if fixture_promotions and result.get('fixture_promotions_verified') is not True:
        raise RuntimeError('Recorded fixture promotion input was not verified by the runner')
    if not fixture_promotions and result.get('fixture_promotions_verified',False) is not False:
        raise RuntimeError('A fixture promotion ran without the opt-in request')
    if fixture_unit_actions and result.get('fixture_unit_actions_verified') is not True:
        raise RuntimeError('SDK unit-action inputs were not verified by the runner')
    if not fixture_unit_actions and result.get('fixture_unit_actions_verified',False) is not False:
        raise RuntimeError('A fixture unit-action input ran without the opt-in request')
    if extra_turns:
        if not save_restore or not 1<=extra_turns<=98 or request.get('extra_restored_turns')!=extra_turns or \
           result.get('extra_restored_turns')!=extra_turns or result.get('extended_turns_verified') is not True:
            raise RuntimeError('Extended turn verification requires an explicitly matching request')
        status='ISOLATED_NATIVE_SAVE_RESTORE_EXTENDED_PASS'
    if result['status']!=status or result['exit_code']!=0 \
       or not all(result[key] is True for key in flags) or any(result[key] is not False for key in excluded) \
       or result['turn_execution_verified'] is not turn_cycle or result['host_failures'] or result['script_failures']:
        raise RuntimeError('New-game result is incomplete or has a different scope: '+run_id)
    command=request['command']
    mode='--check-save-restore' if save_restore else ('--check-turn-cycle' if turn_cycle else ('--check-first-turn' if first_turn else '--check-new-game'))
    if request.get('ui_popups_enabled',False) is not ui_popups or (ui_popups and not save_restore):
        raise RuntimeError('UI popup verification requires its explicitly matching request')
    if fixture_unit_actions:mode='--check-save-restore-ui-actions'
    elif fixture_promotions:mode='--check-save-restore-ui-promotions'
    elif ui_popups:mode='--check-save-restore-ui'
    if len(command)!=(4 if extra_turns else 3) or command[1]!=mode or command[2] not in ('en_US','ko_KR') or \
       (extra_turns and command[3]!=str(extra_turns)):
        raise RuntimeError('Unexpected new-game command')
    output=Path(result['stdout']['path']).read_text(encoding='utf-8')
    error=Path(result['stderr']['path']).read_text(encoding='utf-8')
    activation_counts=re.findall(r'^SESSION_ACTIVE_MODS=(\d+)$',output,re.M)
    if 'session_activation' in request:
        expected_counts=[0,0] if save_restore else [0]
        if request['session_activation']!={'source':'COMPILED_HOST_FIXED_CONFIGURATION','active_mods':[]} or \
           [int(value) for value in activation_counts]!=expected_counts or result.get('session_active_mods')!=expected_counts:
            raise RuntimeError('Fresh sessions did not use their declared empty activation configuration')
    elif activation_counts:
        raise RuntimeError('Session activation was not declared in the request')
    if error or 'LANGUAGE='+command[2] not in output or 'PLATFORM_STATISTICS_AVAILABLE=false' not in output:
        raise RuntimeError('Language/platform/error observations differ')
    promotion_lines=re.findall(r'^EXTENDED_TURN_CYCLE_PROMOTION=',output,re.M)
    promotion_policies=re.findall(r'^EXTENDED_TURN_CYCLE_PROMOTION_POLICY=',output,re.M)
    if not fixture_promotions and (promotion_lines or promotion_policies):
        raise RuntimeError('Fixture promotion logs appeared without their opt-in request')
    input_routes,action_records=inspect_unit_action_logs(output,extra_turns,fixture_promotions,fixture_unit_actions)
    if result.get('extended_input_routes',[])!=input_routes or result.get('action_records',[])!=action_records:
        raise RuntimeError('Recorded SDK unit-action inputs differ from the runner result')
    if ui_popups and (output.splitlines().count('UI_POPUP_CONTEXT=OFFICIAL_BNW_WHOS_WINNING_PERSISTENT_VM_RETAINED_CONTROLS')!=2 or
                      len(re.findall(r'^UI_POPUP_CONTEXT_CLOSED=\d+$',output,re.M))!=2):
        raise RuntimeError('Both fresh sessions must initialize and close their actual UI VM')
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
        'host_service_events':events,'duration_seconds':result['duration_seconds'],
        'command':command[1:],'fixture_promotions_enabled':fixture_promotions,
        'city_site_workers_enabled':sdk_city_sites,'city_site_workers':selected_city_workers if sdk_city_sites else 0,
        'fixture_unit_actions_enabled':fixture_unit_actions,'input_routes':input_routes,
        'action_records':action_records}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='append',required=True)
    parser.add_argument('--sdk-city-sites',action='store_true')
    parser.add_argument('--city-site-workers',type=int,choices=(0,1,2,4))
    parser.add_argument('--save-restore',action='store_true')
    args=parser.parse_args()
    if len(args.run)!=2 or len(set(args.run))!=2:parser.error('Provide two distinct successful language runs')
    if args.city_site_workers is not None and not args.sdk_city_sites:parser.error('--city-site-workers requires --sdk-city-sites')
    if args.sdk_city_sites and not args.save_restore:parser.error('--sdk-city-sites requires --save-restore')
    rows=[inspect(run_id,save_restore=args.save_restore,sdk_city_sites=args.sdk_city_sites,
                  city_site_workers=args.city_site_workers if args.sdk_city_sites else None) for run_id in args.run]
    if {row['language'] for row in rows}!={'en_US','ko_KR'}:raise RuntimeError('Both language runs are required')
    for field in ('inputs','observation','lua_observation','host_service_events'):
        if rows[0][field]!=rows[1][field]:raise RuntimeError('Language run comparison differs: '+field)
    if rows[0]['city_site_workers_enabled']!=rows[1]['city_site_workers_enabled'] or \
       rows[0]['city_site_workers']!=rows[1]['city_site_workers']:
        raise RuntimeError('Language runs used different city-site worker settings')
    report={'status':'ISOLATED_NEW_GAME_PAIR_PASS','validator':artifact(Path(__file__).resolve()),'runs':rows,
        'city_site_workers_enabled':args.sdk_city_sites,
        'city_site_workers':rows[0]['city_site_workers'],
        'new_game_candidate_verified':True,'sdk_lua_counts_match':True,'language_observations_match':True,
        'complete_state_determinism_verified':False,'turn_execution_verified':False,'game_multicore_verified':False,
        'accepted_stage_promoted':False,'installed_game_launched':False,
        'scope':'ACTUAL_X64_CONTINENTS_NEW_GAME_SDK_LUA_OBSERVATION_AND_UNLOAD_IN_TWO_LANGUAGES'}
    (ROOT/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'languages':[row['language'] for row in rows],
        'observation':rows[0]['observation'],'lua_observation':rows[0]['lua_observation']}),flush=True)


if __name__=='__main__':main()
