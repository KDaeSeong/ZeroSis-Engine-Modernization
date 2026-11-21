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


def verify_found_value_worker_metadata(request,result,sdk_found_values,found_value_workers,
                                       sdk_city_sites,city,save_restore):
    enabled=request.get('found_value_workers_enabled',False)
    workers=request.get('found_value_workers',0)
    selected=workers if found_value_workers is None else found_value_workers
    build_ref=request.get('found_value_sdk_build')
    environment=request.get('found_value_environment_overrides',{})
    profile=request.get('found_value_default_environment_profile')
    layout=request.get('found_value_input_layout','DENSE' if sdk_found_values else 'NOT_ENABLED')
    result_layout=result.get('found_value_input_layout','DENSE' if sdk_found_values else 'NOT_ENABLED')
    cpu_enabled=request.get('found_value_cpu_trace_enabled',False)
    cpu_environment=request.get('found_value_cpu_trace_environment_overrides',{})
    if type(cpu_enabled) is not bool or result.get('found_value_cpu_trace_enabled',False) is not cpu_enabled or \
       cpu_environment!=({'ZEROSIS_FOUND_VALUE_CPU_TRACE':'1'} if cpu_enabled else {}) or \
       result.get('found_value_cpu_trace_environment_overrides',{})!=cpu_environment or \
       (cpu_enabled and (not sdk_found_values or layout!='SHARED_FACTS' or selected!=4 or \
        profile!='EXPLICIT_OVERRIDES' or request.get('inherited_found_value_cpu_trace_environment_removed') is not True)):
        raise RuntimeError('Found-value CPU markers lack their explicit shared-layout launch contract')
    if not sdk_found_values:
        if enabled is True or result.get('found_value_workers_enabled',False) is True or \
           build_ref is not None or workers not in (0,None) or selected not in (0,None) or \
           request.get('found_value_trace_enabled',False) is True or \
           result.get('found_value_trace_enabled',False) is True or environment not in ({},None) or \
           profile not in (None,'NOT_ENABLED') or result.get('found_value_default_environment_profile') not in (None,'NOT_ENABLED') or \
           layout!='NOT_ENABLED' or result_layout!='NOT_ENABLED' or cpu_enabled:
            raise RuntimeError('Found-value SDK opt-in or environment appeared without verifier opt-in')
        return 0
    default_profile=profile=='SERIAL_TRACE_OFF'
    if layout not in ('DENSE','SHARED_FACTS') or result_layout!=layout:
        raise RuntimeError('Found-value request/result input layouts differ')
    if enabled is not True or type(workers) is not int or type(selected) is not int or \
       workers!=selected or result.get('found_value_workers_enabled') is not True or \
       type(result.get('found_value_workers')) is not int or result.get('found_value_workers')!=selected or \
       request.get('found_value_trace_enabled') is not (not default_profile) or \
       result.get('found_value_trace_enabled') is not (not default_profile) or \
       result.get('found_value_default_environment_profile')!=profile or \
       request.get('inherited_found_value_environment_removed') is not True:
        raise RuntimeError('Found-value request/result opt-in metadata differs')
    if not sdk_city_sites or not save_restore or city is None or selected not in (0,1,2,4) or \
       not isinstance(environment,dict) or \
       (default_profile and (selected!=0 or profile!='SERIAL_TRACE_OFF' or environment!={} or request.get('found_value_trace_enabled') is not False)) or \
       (not default_profile and (profile not in ('EXPLICIT_OVERRIDES',None) or \
        set(environment)!={'ZEROSIS_FOUND_VALUE_WORKERS','ZEROSIS_FOUND_VALUE_TRACE'} or \
        environment!={'ZEROSIS_FOUND_VALUE_WORKERS':str(selected),'ZEROSIS_FOUND_VALUE_TRACE':'1'})) or \
       not isinstance(build_ref,dict):
        raise RuntimeError('Found-value verification requires its explicit city-site SDK chain, save/restore and launch environment')
    found=read_artifact(build_ref)
    expected_status={'DENSE':'FOUND_VALUE_SDK_CANDIDATE_LINKED',
                     'SHARED_FACTS':'FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED'}[layout]
    if found.get('status')!=expected_status or found.get('input_layout','DENSE')!=layout or \
       found.get('active_sdk_updated') is not False or found.get('stage_updated') is not False or \
       found.get('mods_updated') is not False:
        raise RuntimeError('Selected Found-value SDK is not an isolated linked candidate')
    gamecore=found.get('gamecore')
    base_dll=found.get('base_city_site_build')
    base_report_ref=found.get('base_city_site_build_report')
    if not isinstance(gamecore,dict) or not isinstance(base_dll,dict) or not isinstance(base_report_ref,dict):
        raise RuntimeError('Found-value SDK lacks its linked GameCore and frozen City-site base artifacts')
    check_artifacts(gamecore);check_artifacts(base_dll)
    base_report=read_artifact(base_report_ref)
    if base_report.get('status')!='CITY_SITE_SDK_CANDIDATE_LINKED' or \
       base_report.get('build_id')!=found.get('base_city_site_build_id') or \
       found.get('base_city_site_build_id')!=city.get('build_id') or \
       base_report.get('gamecore',{}).get('sha256')!=base_dll.get('sha256') or \
       base_dll.get('sha256')!=city.get('gamecore',{}).get('sha256'):
        raise RuntimeError('Found-value SDK base does not match the selected frozen City-site candidate')
    if not any(Path(item['path']).name=='CvGameCoreDLL_Expansion2_x64.dll' and
               item['sha256']==gamecore.get('sha256') for item in request['inputs']):
        raise RuntimeError('New-game run did not load the selected Found-value SDK GameCore')
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


def inspect(run_id,root=ROOT,first_turn=False,turn_cycle=False,save_restore=False,extra_turns=0,ui_popups=False,fixture_promotions=False,fixture_unit_actions=False,sdk_city_sites=False,city_site_workers=None,sdk_found_values=False,found_value_workers=None,ui_window_popups=False,ui_window_display=False,ui_window_refresh=False):
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
    selected_found_workers=verify_found_value_worker_metadata(
        request,result,sdk_found_values,found_value_workers,sdk_city_sites,city if sdk_city_sites else None,save_restore)
    if sdk_found_values:
        sdk=read_artifact(request['found_value_sdk_build']);check_artifacts(sdk)
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
    if request.get('ui_window_popups_enabled',False) is not ui_window_popups or \
       result.get('ui_window_popups_enabled',False) is not ui_window_popups or \
       (ui_window_popups and not (ui_popups and fixture_promotions and fixture_unit_actions and save_restore and extra_turns==48)):
        raise RuntimeError('Live UI window verification requires its exact explicit profile')
    if request.get('ui_window_display_enabled',False) is not ui_window_display or \
       result.get('ui_window_display_enabled',False) is not ui_window_display or \
       (ui_window_display and not ui_window_popups):
        raise RuntimeError('GPU display resize verification requires its matching explicit opt-in')
    if request.get('ui_window_refresh_enabled',False) is not ui_window_refresh or \
       result.get('ui_window_refresh_enabled',False) is not ui_window_refresh or \
       (ui_window_refresh and not ui_window_display):
        raise RuntimeError('Closed-scene refresh verification requires its matching display opt-in')
    expected_profile_overrides={'ZEROSIS_UI_WINDOW_PROFILE':'display-refresh'} if ui_window_refresh else (
        {'ZEROSIS_UI_WINDOW_PROFILE':'display-resize'} if ui_window_display else {})
    for metadata in (request,result):
        if metadata.get('inherited_ui_window_profile_environment_removed') is not None and \
           metadata.get('inherited_ui_window_profile_environment_removed') is not True:
            raise RuntimeError('Inherited UI window profile environment was not cleared')
        if metadata.get('ui_window_profile_environment_overrides') is not None and \
           metadata.get('ui_window_profile_environment_overrides')!=expected_profile_overrides:
            raise RuntimeError('UI window profile environment override differs from its opt-in')
        if (ui_window_display or ui_window_refresh) and (metadata.get('inherited_ui_window_profile_environment_removed') is not True or
                                 metadata.get('ui_window_profile_environment_overrides')!=expected_profile_overrides):
            raise RuntimeError('GPU window profile environment provenance is incomplete')
    if ui_window_popups and build.get('status')!='UI_WINDOW_HOST_CANDIDATE_BUILT':
        raise RuntimeError('Live UI window run requires its declared host candidate')
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
    if ui_window_popups:mode='--check-save-restore-ui-window-actions'
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
    if ui_window_popups:
        if type(result.get('process_id')) is not int or result['process_id']<=0 or \
           error!=f"UI_WINDOW_PROCESS_START={result['process_id']}\n" or \
           output.splitlines().count('UI_WINDOW_MODE='+('LIVE_OFFICIAL_VM_OWNED_GPU_HWND_CLOSED_SCENE_REFRESH_POSTED_TEST_INPUT' if ui_window_refresh else ('LIVE_OFFICIAL_VM_OWNED_GPU_HWND_DISPLAY_RESIZE_POSTED_TEST_INPUT' if ui_window_display else 'LIVE_OFFICIAL_VM_OWNED_HIDDEN_HWND_POSTED_TEST_INPUT')))!=1:
            raise RuntimeError('Live UI window process identity or diagnostics differ')
        refresh_markers=re.findall(r'^UI_WINDOW_REFRESH_STATE_UNCHANGED=(\d+)\|after-refresh$',output,re.M)
        if (ui_window_refresh and refresh_markers!=['1','2']) or (not ui_window_refresh and
            re.findall(r'^UI_WINDOW_REFRESH_STATE_UNCHANGED=([^\r\n]*)$',output,re.M)):
            raise RuntimeError('Closed-scene refresh marker differs from its explicit opt-in')
    elif error:
        raise RuntimeError('Unexpected new-game error diagnostics')
    if 'LANGUAGE='+command[2] not in output or 'PLATFORM_STATISTICS_AVAILABLE=false' not in output:
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
    row={'run_id':run_id,'language':command[2],'result':artifact(result_path),
        'inputs':{name:row['sha256'] for name,row in files.items()},'observation':native,'lua_observation':lua,
        'host_service_events':events,'duration_seconds':result['duration_seconds'],
        'command':command[1:],'fixture_promotions_enabled':fixture_promotions,
        'city_site_workers_enabled':sdk_city_sites,'city_site_workers':selected_city_workers if sdk_city_sites else 0,
        'fixture_unit_actions_enabled':fixture_unit_actions,'ui_window_popups_enabled':ui_window_popups,
        'ui_window_display_enabled':ui_window_display,'ui_window_refresh_enabled':ui_window_refresh,'input_routes':input_routes,
        'action_records':action_records}
    if sdk_found_values:
        row.update(found_value_workers_enabled=True,found_value_workers=selected_found_workers,
                   found_value_sdk_build=request['found_value_sdk_build'])
    return row


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='append',required=True)
    parser.add_argument('--sdk-city-sites',action='store_true')
    parser.add_argument('--city-site-workers',type=int,choices=(0,1,2,4))
    parser.add_argument('--sdk-found-values',action='store_true')
    parser.add_argument('--found-value-workers',type=int,choices=(0,1,2,4))
    parser.add_argument('--save-restore',action='store_true')
    parser.add_argument('--ui-window-popups',action='store_true')
    parser.add_argument('--ui-window-display',action='store_true')
    parser.add_argument('--ui-window-refresh',action='store_true')
    parser.add_argument('--ui-popups',action='store_true');parser.add_argument('--fixture-promotions',action='store_true')
    parser.add_argument('--fixture-unit-actions',action='store_true');parser.add_argument('--extra-turns',type=int,default=0)
    args=parser.parse_args()
    if len(args.run)!=2 or len(set(args.run))!=2:parser.error('Provide two distinct successful language runs')
    if args.city_site_workers is not None and not args.sdk_city_sites:parser.error('--city-site-workers requires --sdk-city-sites')
    if args.sdk_city_sites and not args.save_restore:parser.error('--sdk-city-sites requires --save-restore')
    if args.found_value_workers is not None and not args.sdk_found_values:parser.error('--found-value-workers requires --sdk-found-values')
    if args.sdk_found_values and not (args.sdk_city_sites and args.save_restore):parser.error('--sdk-found-values requires --sdk-city-sites and --save-restore')
    if args.ui_window_display and not args.ui_window_popups:parser.error('--ui-window-display requires --ui-window-popups')
    if args.ui_window_refresh and not args.ui_window_display:parser.error('--ui-window-refresh requires --ui-window-display')
    rows=[inspect(run_id,save_restore=args.save_restore,extra_turns=args.extra_turns,ui_popups=args.ui_popups,
                  fixture_promotions=args.fixture_promotions,fixture_unit_actions=args.fixture_unit_actions,
                  sdk_city_sites=args.sdk_city_sites,
                  city_site_workers=args.city_site_workers if args.sdk_city_sites else None,
                  sdk_found_values=args.sdk_found_values,
                  found_value_workers=args.found_value_workers if args.sdk_found_values else None,
                  ui_window_popups=args.ui_window_popups,ui_window_display=args.ui_window_display,
                  ui_window_refresh=args.ui_window_refresh) for run_id in args.run]
    if {row['language'] for row in rows}!={'en_US','ko_KR'}:raise RuntimeError('Both language runs are required')
    for field in ('inputs','observation','lua_observation','host_service_events'):
        if rows[0][field]!=rows[1][field]:raise RuntimeError('Language run comparison differs: '+field)
    if rows[0]['city_site_workers_enabled']!=rows[1]['city_site_workers_enabled'] or \
       rows[0]['city_site_workers']!=rows[1]['city_site_workers']:
        raise RuntimeError('Language runs used different city-site worker settings')
    if args.sdk_found_values and (rows[0]['found_value_workers_enabled'] is not True or
                                  rows[0]['found_value_workers']!=rows[1]['found_value_workers']):
        raise RuntimeError('Language runs used different Found-value worker settings')
    report={'status':'ISOLATED_NEW_GAME_PAIR_PASS','validator':artifact(Path(__file__).resolve()),'runs':rows,
        'city_site_workers_enabled':args.sdk_city_sites,
        'city_site_workers':rows[0]['city_site_workers'],
        'new_game_candidate_verified':True,'sdk_lua_counts_match':True,'language_observations_match':True,
        'complete_state_determinism_verified':False,'turn_execution_verified':False,'game_multicore_verified':False,
        'accepted_stage_promoted':False,'installed_game_launched':False,
        'scope':'ACTUAL_X64_CONTINENTS_NEW_GAME_SDK_LUA_OBSERVATION_AND_UNLOAD_IN_TWO_LANGUAGES'}
    if args.sdk_found_values:
        report.update(found_value_workers_enabled=True,
                      found_value_workers=rows[0]['found_value_workers'],
                      found_value_runtime_trace_verified=False,
                      found_value_semantic_comparison_verified=False)
    (ROOT/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'languages':[row['language'] for row in rows],
        'observation':rows[0]['observation'],'lua_observation':rows[0]['lua_observation']}),flush=True)


if __name__=='__main__':main()
