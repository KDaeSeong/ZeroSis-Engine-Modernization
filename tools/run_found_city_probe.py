"""Run the actual SDK founding action and fresh-session native city restore.

The original starting settler supplies a separate explicit input profile. The
optional city-decision profile selects legal production/research, advances one
normal turn and restores a third fresh session. Neither profile promotes Stage.
"""
import argparse
import configparser
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from run_new_game_probe import compile_candidate, verify_city_site_base, verify_found_value_base
from runtime_input_cache import materialize_immutable
from verify_world_builder_map_object import check_artifacts

ROOT = PROJECT / 'evidence/found_city'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--compile', action='store_true')
    parser.add_argument('--sdk-city-sites', action='store_true')
    parser.add_argument('--shared-found-values', action='store_true')
    parser.add_argument('--city-decisions', action='store_true')
    parser.add_argument('--research-ui',action='store_true')
    parser.add_argument('--research-window',action='store_true')
    parser.add_argument('--research-tree',action='store_true',
                        help='Open the original TechTree through TechPopup, select normal research, scroll, close and restore')
    parser.add_argument('--production-ui', action='store_true')
    parser.add_argument('--production-window', action='store_true',
                        help='Dispatch a clipped unit hit through the owned GPU HWND and verify its closed refresh')
    parser.add_argument('--production-live', action='store_true',
                        help='Keep the production HWND live through category/pointer/panel-wheel scene updates before the unit order')
    parser.add_argument('--host-build', type=Path)
    parser.add_argument('--language', choices=('en_US', 'ko_KR'), default='en_US')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    if args.production_live:args.production_window=True
    if args.shared_found_values:args.sdk_city_sites=True
    if args.production_window:args.production_ui=True
    if args.production_ui:
        args.city_decisions = True
        if not args.host_build:
            parser.error('Production UI requires an explicit private host build report')
    if args.research_window:args.research_ui=True
    if args.research_tree:
        args.research_ui=True
        if args.research_window:parser.error('Research tree requires its separate direct-input profile')
    if args.research_ui:
        args.city_decisions=True
        if args.production_ui:parser.error('Research and production UI need distinct snapshot sessions')
        if not args.host_build:parser.error('Research UI requires an explicit private host build report')
    decision_window=args.production_window or args.research_window
    if args.compile and args.host_build:
        parser.error('Choose compilation or an explicit build report')
    if not 10 <= args.timeout <= 300:
        parser.error('Timeout must be between 10 and 300 seconds')
    if args.compile:
        compile_candidate(shared=True)
    build_path = args.host_build.resolve(strict=True) if args.host_build else PROJECT / 'evidence/new_game/candidate_build_shared.json'
    build = json.loads(build_path.read_text(encoding='utf8'))
    runtime_path = PROJECT / 'evidence/shared_lua_runtime/build_result.json'
    runtime = json.loads(runtime_path.read_text(encoding='utf8'))
    explore_path = PROJECT / 'evidence/explore_sdk/build_result.json'
    explore = json.loads(explore_path.read_text(encoding='utf8'))
    city_path = PROJECT / 'evidence/city_site_sdk/build_result.json'
    city = json.loads(city_path.read_text(encoding='utf8')) if args.sdk_city_sites else None
    bundle_path = PROJECT / 'evidence/host/bundle.json'
    bundle = json.loads(bundle_path.read_text(encoding='utf8'))
    check_artifacts(build); check_artifacts(runtime); check_artifacts(explore)
    check_artifacts(bundle['files']); check_artifacts(bundle['manifest'])
    if explore['status'] != 'EXPLORE_SDK_CANDIDATE_LINKED':
        raise RuntimeError('Founding requires the recorded linked exploration SDK baseline')
    if city:
        check_artifacts(city)
        if city['status'] != 'CITY_SITE_SDK_CANDIDATE_LINKED' or city['stage_updated'] or city['active_sdk_updated']:
            raise RuntimeError('Founding requires an isolated linked city-site SDK candidate')
        verify_city_site_base(city, explore)
    found_path=PROJECT/'evidence/found_value_shared_sdk/build_result.json'
    found=json.loads(found_path.read_text(encoding='utf8')) if args.shared_found_values else None
    if found:verify_found_value_base(found,city,'SHARED_FACTS')
    core = (found or city or explore)['gamecore']
    sources = {Path(row['path']).name: row for row in build['sources']}
    required = ('FoundCityProbe.h', 'HostMain.cpp', 'HostRun.h', 'HostServices.h', 'LocalSdkSession.h', 'LocalGameCommands.h')
    if args.city_decisions:required+=('CityDecisionProbe.h',)
    if args.production_ui or args.research_ui:required+=('UiPopupContext.h','UiPopupAssets.generated.h','UiInputDispatch.h')
    if not set(required) <= sources.keys():
        raise RuntimeError('The selected host lacks frozen founding sources; compile the new candidate')
    if '--check-found-city' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('The selected host does not implement the explicit founding mode')
    if args.city_decisions and '--check-city-decisions' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('The selected host does not implement the explicit city-decision mode')
    if args.production_ui and '--check-city-production-ui' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('The selected host does not implement official production UI input')
    if args.production_window and (build.get('status') != 'UI_WINDOW_HOST_CANDIDATE_BUILT' or
        '--check-city-production-ui-window' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8')):
        raise RuntimeError('Production native hit input requires its separately sealed window host')
    if args.production_live and '--check-city-production-ui-live' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Live production input requires its newly sealed host mode')
    if args.research_ui and '--check-city-research-ui' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Research requires the newly sealed TechPopup host')
    if args.research_window and build.get('status')!='UI_WINDOW_HOST_CANDIDATE_BUILT':
        raise RuntimeError('Research hit requires the sealed GPU host')
    if args.research_tree and '--check-city-research-tree-ui' not in Path(sources['HostMain.cpp']['path']).read_text(encoding='utf8'):
        raise RuntimeError('Research tree requires the newly sealed TechTree host')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    selected_root = PROJECT / 'evidence/city_research_tree_ui' if args.research_tree else PROJECT / 'evidence/city_research_ui' if args.research_ui else PROJECT / 'evidence/city_production_ui' if args.production_ui else PROJECT / 'evidence/city_decisions' if args.city_decisions else ROOT
    directory = PROJECT / ('Build/CityResearchTreeUiRuntime' if args.research_tree else 'Build/CityResearchUiRuntime' if args.research_ui else 'Build/CityProductionUiRuntime' if args.production_ui else 'Build/CityDecisionRuntime' if args.city_decisions else 'Build/FoundCityRuntime') / run_id
    evidence = selected_root / run_id
    directory.mkdir(parents=True, exist_ok=False); evidence.mkdir(parents=True, exist_ok=False)
    rows = []; materializations = []
    for row in bundle['files']:
        name = Path(row['path']).name
        source = Path(build['executable']['path']) if name == 'ZeroSisHost_x64.exe' else Path(row['path'])
        if name == 'CvGameCoreDLL_Expansion2_x64.dll':
            source = Path(core['path'])
        target = directory / name
        if source.suffix.lower() in ('.dll', '.exe', '.bin', '.dat'):
            materializations.append(materialize_immutable(source, target, PROJECT / 'Build/RuntimeInputCache'))
        else:
            shutil.copy2(source, target)
            materializations.append({'target': str(target), 'materialization_method': 'private-copy', 'size': target.stat().st_size})
        if digest(target) != digest(source):
            raise RuntimeError('Founding runtime input materialization differs')
        rows.append({'source': str(source), **artifact(target)})
    lua_source = Path(runtime['lua_dll']['path']); lua_target = directory / lua_source.name
    materializations.append(materialize_immutable(lua_source, lua_target, PROJECT / 'Build/RuntimeInputCache'))
    rows.append({'source': str(lua_source), **artifact(lua_target)})
    manifest = directory / 'bundle.manifest'
    manifest.write_text('ZEROSIS_HOST_BUNDLE_V4\n' + ''.join(Path(row['path']).name + '|' + row['sha256'] + '\n' for row in rows), encoding='ascii')
    rows.append(artifact(manifest))
    references = {}
    for name, source in (('candidate_build', build_path), ('shared_lua_build', runtime_path), ('explore_sdk_build', explore_path),
                         ('runner', Path(__file__).resolve()), ('runtime_cache_helper', PROJECT / 'tools/runtime_input_cache.py')):
        target = evidence / (name + source.suffix)
        shutil.copy2(source, target)
        if digest(target) != digest(source):
            raise RuntimeError('Founding proof input changed while freezing it')
        references[name] = artifact(target)
    if city:
        target = evidence / 'city_site_sdk_build.json'; shutil.copy2(city_path, target)
        if digest(target) != digest(city_path):
            raise RuntimeError('City-site SDK report changed during founding setup')
        references['city_site_sdk_build'] = artifact(target)
    if found:
        target=evidence/'found_value_shared_sdk_build.json';shutil.copy2(found_path,target)
        if digest(target)!=digest(found_path):raise RuntimeError('Shared Found SDK report changed during setup')
        references['found_value_shared_sdk_build']=artifact(target)
    ui_window_tools=[]
    if decision_window:
        tools_directory=directory/'UiPresentationTools/tools'
        for relative in ('tools/live_ui_window_driver.py','tools/live_production_window_driver.py','tools/render_ui_popup.py','tools/ui_pixel_scene.py',
                         'tools/ui_bitmap_fonts.py','tools/civ5_ui_assets.py','tools/ui_window_frame.py'):
            source=PROJECT/relative;target=directory/'UiPresentationTools'/relative
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            if digest(source)!=digest(target):raise RuntimeError('Production window helper changed while freezing')
            ui_window_tools.append({'original_source':str(source),**artifact(target)})
        source=PROJECT/'evidence/ui_popup/assets/inline_icons.json'
        target=tools_directory/'inline_icons.json';shutil.copy2(source,target)
        if digest(source)!=digest(target):raise RuntimeError('Production icon catalog changed while freezing')
        ui_window_tools.append({'original_source':str(source),**artifact(target)})
        source=PROJECT/'evidence/ui_popup/assets/prepared.json';target=evidence/'ui_assets_prepared.json'
        shutil.copy2(source,target)
        if digest(source)!=digest(target):raise RuntimeError('Production asset provenance changed while freezing')
        references['ui_assets_prepared']=artifact(target)
        prepared=json.loads(target.read_text(encoding='utf8'))
        if prepared['inline_icon_catalog']['sha256']!=digest(tools_directory/'inline_icons.json'):
            raise RuntimeError('Production FontIcons bytes differ from the asset provenance')
    ui_settings=None;small_ui_assets=None
    environment = os.environ.copy()
    inherited_small_ui_assets_removed=environment.pop('ZEROSIS_UI_SMALL_ASSETS',None) is not None
    if args.research_ui:
        setting_source=Path(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5\UserSettings.ini")
        setting_target=directory/'UserSettings.frozen.ini';shutil.copy2(setting_source,setting_target)
        if digest(setting_source)!=digest(setting_target):raise RuntimeError('User UI settings changed during freeze')
        parser_ini=configparser.ConfigParser(interpolation=None,strict=True)
        parser_ini.read_string(setting_target.read_text(encoding='utf-8-sig'))
        raw_small=parser_ini['InterfaceSettings']['SmallUIAssets'].strip()
        if raw_small not in ('0','1'):raise RuntimeError('SmallUIAssets must be an explicit boolean')
        small_ui_assets=raw_small=='1';ui_settings={'original_source':str(setting_source),**artifact(setting_target)}
        environment['ZEROSIS_UI_SMALL_ASSETS']=raw_small
    environment['ZEROSIS_EXPLORE_WORKERS'] = '0'
    environment['ZEROSIS_CITY_SITE_WORKERS'] = '0'
    environment.pop('ZEROSIS_CITY_SITE_CPU_TRACE',None)
    environment.pop('ZEROSIS_FOUND_VALUE_CPU_TRACE',None)
    environment.pop('ZEROSIS_FOUND_VALUE_TRACE',None)
    environment['ZEROSIS_FOUND_VALUE_WORKERS']='0'
    environment.pop('ZEROSIS_UI_WINDOW_PROFILE',None)
    if decision_window:environment['ZEROSIS_UI_WINDOW_PROFILE']='display-refresh'
    command = [str(directory / 'ZeroSisHost_x64.exe'), '--check-city-research-tree-ui' if args.research_tree else '--check-city-research-ui-window' if args.research_window else '--check-city-research-ui' if args.research_ui else '--check-city-production-ui-live' if args.production_live else '--check-city-production-ui-window' if args.production_window else
               '--check-city-production-ui' if args.production_ui else '--check-city-decisions' if args.city_decisions else '--check-found-city', args.language]
    request = {'run_id': run_id, 'command': command, 'cwd': str(directory), 'timeout_seconds': args.timeout,
               'language': args.language, 'inputs': rows, 'input_materializations': materializations, **references,
               'accepted_bundle': artifact(bundle_path), 'gamecore': core,
               'environment_overrides': {'ZEROSIS_EXPLORE_WORKERS': '0', 'ZEROSIS_CITY_SITE_WORKERS': '0','ZEROSIS_FOUND_VALUE_WORKERS':'0'},
               'city_site_sdk_enabled': args.sdk_city_sites, 'fixture_input': 'ORIGINAL_STARTING_SETTLER_SDK_MISSION_FOUND',
               'shared_found_value_sdk_enabled':args.shared_found_values,
               'city_decisions_enabled':args.city_decisions,
               'research_ui_enabled':args.research_ui,'research_window_requested':args.research_window,
               'research_tree_requested':args.research_tree,
               'research_tree_input_profile':'OWNER_RETAINED_CALLBACK_NORMAL_RESEARCH_HORIZONTAL_SCROLL_ESCAPE_V1' if args.research_tree else None,
               'ui_shift_policy':'NORMAL_FIXTURE_FALSE_V1' if args.research_tree else None,
               'small_ui_assets_setting':small_ui_assets,'ui_settings_source':ui_settings,
               'small_ui_assets_environment_removed':inherited_small_ui_assets_removed,
               'auto_ui_assets_effective_retail_setting_verified':False,
               'official_production_ui_requested':args.production_ui,
               'production_window_requested':args.production_window,'production_interactions_requested':args.production_live,'ui_window_tools':ui_window_tools,
               'automatic_mouse_leave_tracking':False if args.production_live else None,
               'owner_presentation_clock_step_seconds':0.125 if args.production_live else None,
               'inherited_ui_window_profile_environment_removed':True,
               'ui_window_profile_environment_overrides':{'ZEROSIS_UI_WINDOW_PROFILE':'display-refresh'} if decision_window else {},
               'turn_advancement_requested': args.city_decisions, 'decision_selection_requested': args.city_decisions,
               'inherited_cpu_trace_environment_removed':True,
               'accepted_stage_promotion_requested': False}
    (evidence / 'request.json').write_text(json.dumps(request, indent=2) + '\n', encoding='utf8')
    if decision_window:
        sys.path.insert(0,str(tools_directory))
        if args.production_live:
            from live_production_window_driver import collect_live_production_window
        else:
            from live_ui_window_driver import collect_live_window
    print(('RUN_CITY_DECISIONS ' if args.city_decisions else 'RUN_FOUND_CITY ') + run_id, flush=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.SetErrorMode.argtypes = [ctypes.c_uint]; kernel.SetErrorMode.restype = ctypes.c_uint
    old = kernel.SetErrorMode(0x0001 | 0x0002 | 0x8000)
    start = time.monotonic()
    try:
        process = subprocess.Popen(command, cwd=directory, env=environment,
                                   stdin=subprocess.PIPE if decision_window else subprocess.DEVNULL,stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    finally:
        kernel.SetErrorMode(old)
    timed_out = False
    ui_window_report=None
    if decision_window:
        try:
            if args.production_live:
                stdout,stderr,timed_out,ui_window_report=collect_live_production_window(process,directory,evidence,args.timeout,tools_directory)
            else:
                stdout,stderr,timed_out,ui_window_report=collect_live_window(process,directory,evidence,args.timeout,
                    tools_directory,display_resize=True,refresh_closed=True,production_fixture=args.production_window,research_fixture=args.research_window)
        except Exception as error:
            if process.poll() is None:process.kill()
            stdout,stderr=process.communicate(timeout=5)
            ui_window_report={'status':'LIVE_SDK_UI_WINDOW_FAILED','pid':process.pid,'error':str(error),
                              'cleanup':'owned_child_reaped_by_runner','returncode':process.returncode,'timed_out':False}
            (evidence/'ui_window.json').write_text(json.dumps(ui_window_report,indent=2)+'\n',encoding='utf8')
    else:
        try:
            stdout, stderr = process.communicate(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True; process.kill(); stdout, stderr = process.communicate()
    (evidence / 'stdout.log').write_bytes(stdout); (evidence / 'stderr.log').write_bytes(stderr)
    output = (stdout + stderr).decode('utf8', errors='replace').replace('\r\n', '\n')
    unchanged = all(digest(Path(row['path'])) == row['sha256'] for row in rows)
    accepted_unchanged = all(digest(Path(row['path'])) == row['sha256'] for row in bundle['files'])
    check_artifacts(references)
    marker = 'FOUND_CITY_SHUTDOWN_PASS GAMECORE_LOADED=true CITY_CREATED=true CITY_RESTORE_VERIFIED=true TURN_ADVANCE_VERIFIED=false'
    if args.city_decisions:marker='CITY_DECISION_SHUTDOWN_PASS GAMECORE_LOADED=true CITY_DECISIONS_ACCEPTED=true TURN_ADVANCE_VERIFIED=true CITY_DECISION_RESTORE_VERIFIED=true'
    success = process.returncode == 0 and not timed_out and unchanged and accepted_unchanged and marker in output and \
        output.splitlines().count('FOUND_CITY_RESTORE_FRESH_SESSION=true') == 1 and \
        (args.city_decisions or output.splitlines().count('FOUND_CITY_RESTORED_CORE_MODULE_UNLOADED=true') == 1) and \
        output.splitlines().count('FOUND_CITY_RESTORE_STATE_EQUAL=true') == 1 and \
        output.splitlines().count('FOUND_CITY_RESTORE_IDLE_STATE_EQUAL=true') == 1 and \
        re.findall(r'^SESSION_ACTIVE_MODS=(\d+)$', output, re.M) == ['0']*(3 if args.city_decisions else 2)
    if args.city_decisions:
        input_route='CITY_DECISION_INPUT_ROUTE=' + ('SDK_CITY_PUSH_ORDER_AND_OFFICIAL_RESEARCH_UI' if args.research_ui else 'OFFICIAL_PRODUCTION_UI_AND_ENGINE_NETWORK_SEND_RESEARCH' if args.production_ui else 'SDK_CITY_PUSH_ORDER_AND_ENGINE_NETWORK_SEND_RESEARCH')
        success=success and all(output.splitlines().count(value)==1 for value in (
            'CITY_DECISION_RESTORE_FRESH_SESSION=true','CITY_DECISION_RESTORED_CORE_MODULE_UNLOADED=true',
            'CITY_DECISION_RESTORE_STATE_EQUAL=true','CITY_DECISION_RESTORE_IDLE_STATE_EQUAL=true',
            input_route)) and \
            len(re.findall(r'^CITY_DECISION_BEFORE_TURN=(.+)$',output,re.M))==1 and \
            len(re.findall(r'^CITY_DECISION_AFTER_TURN=(.+)$',output,re.M))==1 and \
            len(re.findall(r'^CITY_DECISION_RESTORED=(.+)$',output,re.M))==4
    if args.research_ui and not args.research_tree:
        success=success and all(output.splitlines().count(value)==1 for value in (
            'RESEARCH_UI_INPUT_ROUTE=OFFICIAL_BNW_TECH_POPUP_RETAINED_BUTTON_SDK_RECEIVER',
            'RESEARCH_UI_TIMER_SEMAPHORE=0','RESEARCH_UI_OWNER_CLOCK=0,0.25','RESEARCH_UI_FRAME_GAMEPLAY_STATE_EQUAL=true',
            'RESEARCH_UI_SHUTDOWN_PASS ORIGINAL_POPUP_CALLBACK=true SDK_RECEIVER=true TURN_AND_NATIVE_RESTORE=true RETAIL_UI_EQUIVALENCE=false')) and \
            len(re.findall(r'^RESEARCH_UI_SELECTION=(.+)$',output,re.M))==1 and \
            output.splitlines().count('RESEARCH_UI_SMALL_ASSETS='+str(int(small_ui_assets)))==1
    if args.research_tree:
        success=success and all(output.splitlines().count(value)==1 for value in (
            'RESEARCH_TREE_UI_HANDOFF_ROUTE=OFFICIAL_OPEN_TT_BUTTON_DEFERRED_OWNER_NEW_VM',
            'RESEARCH_TREE_UI_TIMER_SHOWN=1','RESEARCH_TREE_UI_RESEARCH_DIRTY=1',
            'RESEARCH_TREE_UI_SELECTION_REMAINS_OPEN=true','RESEARCH_TREE_UI_TIMER_AFTER_SELECTION=1',
            'RESEARCH_TREE_UI_STALE_INPUT_REJECTED=true','RESEARCH_TREE_UI_TIMER_SEMAPHORE=0',
            'RESEARCH_TREE_UI_INPUT_ROUTE=OFFICIAL_BNW_TECH_TREE_RETAINED_BUTTON_SDK_RECEIVER',
            'RESEARCH_TREE_UI_SHUTDOWN_PASS ORIGINAL_POPUP_CALLBACK=true SDK_RECEIVER=true TURN_AND_NATIVE_RESTORE=true RETAIL_UI_EQUIVALENCE=false',
            'RESEARCH_UI_OWNER_CLOCK=0,0.25','RESEARCH_UI_FRAME_GAMEPLAY_STATE_EQUAL=true',
            'RESEARCH_UI_SMALL_ASSETS='+str(int(small_ui_assets)),
            'RESEARCH_TREE_UI_SMALL_ASSETS='+str(int(small_ui_assets)))) and \
            len(re.findall(r'^RESEARCH_TREE_UI_SELECTION=(.+)$',output,re.M))==1 and \
            len(re.findall(r'^RESEARCH_TREE_UI_HANDOFF=(.+)$',output,re.M))==1 and \
            len(re.findall(r'^RESEARCH_TREE_UI_HORIZONTAL_SCROLL=(.+)$',output,re.M))==1
    if args.production_ui:
        success=success and all(output.splitlines().count(value)==1 for value in (
            'PRODUCTION_UI_INPUT_ROUTE=OFFICIAL_BNW_POPUP_RETAINED_BUTTON_SDK_RECEIVER',
            'PRODUCTION_UI_TIMER_SEMAPHORE=0',
            'PRODUCTION_UI_OWNER_CLOCK=0,0.25',
            'PRODUCTION_UI_FRAME_GAMEPLAY_STATE_EQUAL=true',
            'PRODUCTION_UI_SHUTDOWN_PASS ORIGINAL_POPUP_CALLBACK=true SDK_RECEIVER=true TURN_AND_NATIVE_RESTORE=true RETAIL_UI_EQUIVALENCE=false')) and \
            len(re.findall(r'^PRODUCTION_UI_SELECTION=(.+)$',output,re.M))==1
    if decision_window:
        window_pass=ui_window_report['status']==('LIVE_SDK_RESEARCH_WINDOW_POSTED_INPUT_PASS' if args.research_window else 'LIVE_SDK_PRODUCTION_INTERACTIONS_PASS' if args.production_live else 'LIVE_SDK_UI_WINDOW_POSTED_INPUT_PASS') and \
            ui_window_report.get('research_fixture_enabled' if args.research_window else 'production_interactions_enabled' if args.production_live else 'production_fixture_enabled') is True
        completion_pass=(output.splitlines().count('PRODUCTION_UI_LIVE_ROUTE=OWNER_THREAD_CATEGORY_POINTER_PANEL_WHEEL_ATOMIC_SCENE_REFRESH')==1 and
            len(re.findall(r'^UI_PRODUCTION_WINDOW_COMPLETE=(.+)$',output,re.M))==1) if args.production_live else \
            re.findall(r'^UI_WINDOW_REFRESH_STATE_UNCHANGED=(\d+)\|after-refresh$',output,re.M)==['1']
        success=success and window_pass and completion_pass and \
            all(digest(Path(row['path']))==row['sha256'] for row in ui_window_tools) and \
            output.splitlines().count('RESEARCH_UI_WINDOW_ROUTE=OWNED_HWND_HIT_OFFICIAL_TECH_SELECTED_SDK_RECEIVER' if args.research_window else 'PRODUCTION_UI_WINDOW_ROUTE=OWNED_HWND_HIT_OFFICIAL_CALLBACK_SDK_RECEIVER')==1 and \
            'HOST_NATIVE_EXCEPTION' not in output
    originals = {row['path'] for row in rows}
    report = {'status': ('ISOLATED_SDK_OFFICIAL_RESEARCH_TREE_UI_TURN_AND_NATIVE_RESTORE_' if args.research_tree else 'ISOLATED_SDK_OFFICIAL_RESEARCH_UI_TURN_AND_NATIVE_RESTORE_' if args.research_ui else 'ISOLATED_SDK_OFFICIAL_PRODUCTION_UI_TURN_AND_NATIVE_RESTORE_' if args.production_ui else 'ISOLATED_SDK_CITY_DECISIONS_TURN_AND_NATIVE_RESTORE_' if args.city_decisions else 'ISOLATED_SDK_FOUND_CITY_AND_NATIVE_RESTORE_') + ('PASS' if success else 'FAILED'),
              'request': artifact(evidence / 'request.json'), 'exit_code': process.returncode,
              'pid':process.pid,
              'exit_code_hex': f'0x{process.returncode & 0xffffffff:08X}', 'timed_out': timed_out,
              'duration_seconds': time.monotonic() - start, 'stdout': artifact(evidence / 'stdout.log'),
              'stderr': artifact(evidence / 'stderr.log'), 'host_failures': re.findall(r'^HOST_FAILURE: (.+)$', output, re.M),
              'founding_action_logs': re.findall(r'^FOUND_CITY_ACTION=(.+)$', output, re.M),
              'founding_observation_logs': re.findall(r'^FOUND_CITY_OBSERVATION=(.+)$', output, re.M),
              'restored_observation_logs': re.findall(r'^FOUND_CITY_RESTORED_OBSERVATION=(.+)$', output, re.M),
              'runtime_inputs_unchanged': unchanged, 'accepted_bundle_files_unchanged': accepted_unchanged,
              'city_decisions_enabled':args.city_decisions,
              'official_production_ui_enabled':args.production_ui,
              'production_window_enabled':args.production_window,
              'production_interactions_enabled':args.production_live,
              'production_interactions_completed':bool(args.production_live and success),
              'positive_scroll_motion_verified':bool(args.research_tree and success),
              'ui_window_report':artifact(evidence/'ui_window.json') if decision_window else None,
              'native_unit_hit_dispatch_verified':bool(args.production_window and success),
              'gpu_frame_bitmap_parity_verified':bool(decision_window and success),
              'official_production_callback_verified':bool(args.production_ui and success),
              'production_ui_selection_logs':re.findall(r'^PRODUCTION_UI_SELECTION=(.+)$',output,re.M),
              'research_ui_verified':bool(args.research_ui and not args.research_tree and success),
              'research_tree_enabled':args.research_tree,
              'research_tree_ui_verified':bool(args.research_tree and success),
              'research_tree_selection_logs':re.findall(r'^RESEARCH_TREE_UI_SELECTION=(.+)$',output,re.M),
              'research_tree_handoff_logs':re.findall(r'^RESEARCH_TREE_UI_HANDOFF=(.+)$',output,re.M),
              'research_tree_scroll_logs':re.findall(r'^RESEARCH_TREE_UI_HORIZONTAL_SCROLL=(.+)$',output,re.M),
              'research_tree_window_verified':False,
              'future_tech_queue_verified':False,'shift_queue_verified':False,
              'official_research_ui_enabled':args.research_ui,'research_window_enabled':args.research_window,
              'research_ui_selection_logs':re.findall(r'^RESEARCH_UI_SELECTION=(.+)$',output,re.M),
              'official_research_callback_verified':bool(args.research_ui and success),
              'native_tech_hit_dispatch_verified':bool(args.research_window and success),
              'free_tech_or_steal_verified':False,'right_click_or_pedia_verified':False,
              'city_decision_before_turn_logs':re.findall(r'^CITY_DECISION_BEFORE_TURN=(.+)$',output,re.M),
              'city_decision_after_turn_logs':re.findall(r'^CITY_DECISION_AFTER_TURN=(.+)$',output,re.M),
              'city_decision_restored_logs':re.findall(r'^CITY_DECISION_RESTORED=(.+)$',output,re.M),
              'gamecore_loaded': True, 'turn_advance_verified': bool(args.city_decisions and success), 'decision_ui_verified': False,
              'renderer_verified': False, 'interactive_input_verified': False, 'retail_save_compatibility_verified': False,
              'accepted_stage_promoted': False,
              'generated_files': [artifact(path) for path in sorted(directory.rglob('*')) if path.is_file() and str(path) not in originals]}
    (evidence / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    selected_root.mkdir(parents=True, exist_ok=True)
    (selected_root / 'result.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({key: report[key] for key in ('status', 'exit_code_hex', 'host_failures', 'founding_observation_logs')}) , flush=True)
    return 0 if success else 1


if __name__ == '__main__':
    raise SystemExit(main())
