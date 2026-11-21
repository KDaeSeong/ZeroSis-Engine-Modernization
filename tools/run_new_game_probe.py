"""Build/run an isolated new-game candidate; never replace the accepted Stage bundle."""
import argparse,json,os,re,shutil,subprocess,sys,time,uuid
from datetime import datetime,timezone
from pathlib import Path
from collect_baseline import PROJECT,digest
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from runtime_input_cache import materialize_immutable

ROOT=PROJECT/'evidence/new_game'


def inspect_fixture_unit_action_output(output,extra_turns,fixture_promotions,enabled):
    all_routes=re.findall(r'^EXTENDED_TURN_CYCLE_INPUT_ROUTE=([^\r\n]*)$',output,re.M)
    all_actions=re.findall(r'^EXTENDED_TURN_CYCLE_ACTION=([^\r\n]*)$',output,re.M)
    if not enabled:
        return not (all_routes or all_actions),[],[]
    if not fixture_promotions or extra_turns<=0:
        return False,all_routes,[]
    begin_matches=re.findall(r'^EXTENDED_TURNS_BEGIN=([^\r\n]*)$',output,re.M)
    complete_matches=re.findall(r'^EXTENDED_TURNS_COMPLETE=([^\r\n]*)$',output,re.M)
    begin_at=output.find('EXTENDED_TURNS_BEGIN=')
    complete_at=output.find('EXTENDED_TURNS_COMPLETE=')
    valid_range=len(begin_matches)==1 and len(complete_matches)==1 and \
        begin_matches==[f'2,{extra_turns}'] and \
        complete_matches==[f'2,{extra_turns+2},{extra_turns}'] and \
        0<=begin_at<complete_at
    if valid_range:
        block=output[begin_at:complete_at]
    else:
        # Keep whatever partial diagnostics exist, but never treat them as a verified scope.
        block=output
    routes=re.findall(r'^EXTENDED_TURN_CYCLE_INPUT_ROUTE=([^\r\n]*)$',block,re.M)
    action_lines=re.findall(r'^EXTENDED_TURN_CYCLE_ACTION=([^\r\n]*)$',block,re.M)
    promotion_lines=re.findall(r'^EXTENDED_TURN_CYCLE_PROMOTION=([^\r\n]*)$',block,re.M)
    action_values=[];promotion_values=[];action_records=[]
    valid=valid_range and len(routes)==extra_turns and \
        all(route=='SDK_GAME_HANDLE_ACTION' for route in routes) and len(all_routes)==len(routes) and \
        len(all_actions)==len(action_lines)
    for line in action_lines:
        if not re.fullmatch(r'\d+(?:,\d+){4}',line):
            valid=False
            continue
        try:values=[int(value) for value in line.split(',')]
        except ValueError:
            valid=False
            continue
        action_values.append(values)
    for line in promotion_lines:
        if not re.fullmatch(r'\d+(?:,\d+){7}',line):
            valid=False
            continue
        try:promotion_values.append([int(value) for value in line.split(',')])
        except ValueError:valid=False
    action_keys=[tuple(values[:4]) for values in action_values]
    promotion_keys=[tuple(values[:4]) for values in promotion_values]
    valid=valid and len(action_values)>0 and len(action_values)==len(action_lines)==len(promotion_lines) and \
        len(promotion_values)==len(promotion_lines) and len(set(action_keys))==len(action_keys) and \
        len(set(promotion_keys))==len(promotion_keys) and set(action_keys)==set(promotion_keys) and \
        all(all(value>=0 for value in values) for values in action_values+promotion_values) and \
        all(2<=values[0]<2+extra_turns for values in action_values)
    if valid_range:
        parts=re.split(r'^EXTENDED_TURN_CYCLE_PLAYER_OPTION=PLAYEROPTION_WAIT_END_TURN:1$',block,flags=re.M)[1:]
        valid=valid and len(parts)==extra_turns
        for turn,part in enumerate(parts,2):
            turn_routes=re.findall(r'^EXTENDED_TURN_CYCLE_INPUT_ROUTE=([^\r\n]*)$',part,re.M)
            turn_action_lines=re.findall(r'^EXTENDED_TURN_CYCLE_ACTION=([^\r\n]*)$',part,re.M)
            try:
                turn_actions=[[int(value) for value in line.split(',')] for line in turn_action_lines]
            except ValueError:
                turn_actions=[];valid=False
            expected=[values for values in action_values if values[0]==turn]
            valid=valid and turn_routes==['SDK_GAME_HANDLE_ACTION'] and turn_actions==expected
    action_records=[{'turn':values[0],'player':values[1],'unit':values[2],
                     'promotion_id':values[3],'action_info_index':values[4]}
                    for values in action_values]
    return bool(valid),routes,action_records


def verify_city_site_base(city_site_sdk,explore_sdk):
    base_dll=city_site_sdk.get('base_explore_build')
    report_refs=[city_site_sdk.get(name) for name in ('base_explore_build_report','base_explore_report')
                 if city_site_sdk.get(name) is not None]
    if not isinstance(base_dll,dict) or not report_refs:
        raise RuntimeError('City-site SDK build lacks frozen Explore DLL and report artifacts')
    check_artifacts(base_dll)
    for base_report in report_refs:
        check_artifacts(base_report)
        frozen_report=json.loads(Path(base_report['path']).read_text(encoding='utf-8'))
        if frozen_report.get('status')!='EXPLORE_SDK_CANDIDATE_LINKED' or \
           frozen_report.get('build_id')!=explore_sdk.get('build_id') or \
           frozen_report.get('gamecore',{}).get('sha256')!=explore_sdk.get('gamecore',{}).get('sha256'):
            raise RuntimeError('A frozen city-site base report differs from the selected Explore SDK build')
    if explore_sdk.get('status')!='EXPLORE_SDK_CANDIDATE_LINKED' or \
       city_site_sdk.get('base_explore_build_id')!=explore_sdk.get('build_id') or \
       base_dll.get('sha256')!=explore_sdk.get('gamecore',{}).get('sha256'):
        raise RuntimeError('The city-site candidate does not use the selected exploration SDK bytes')


def verify_found_value_base(found,city,layout='DENSE'):
    check_artifacts(found)
    base=found.get('base_city_site_build')
    reference=found.get('base_city_site_build_report')
    if not isinstance(base,dict) or not isinstance(reference,dict):
        raise RuntimeError('The found-value SDK lacks its frozen CitySite base DLL/report')
    frozen=json.loads(Path(reference['path']).read_text(encoding='utf8'));check_artifacts(frozen)
    expected_status={'DENSE':'FOUND_VALUE_SDK_CANDIDATE_LINKED',
                     'SHARED_FACTS':'FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED'}.get(layout)
    if expected_status is None or found.get('status')!=expected_status or \
       found.get('input_layout','DENSE')!=layout or \
       found.get('active_sdk_updated') is not False or found.get('stage_updated') is not False or \
       frozen.get('status')!='CITY_SITE_SDK_CANDIDATE_LINKED' or \
       found.get('base_city_site_build_id')!=city.get('build_id') or \
       frozen.get('build_id')!=city.get('build_id') or \
       frozen.get('gamecore',{}).get('sha256')!=city.get('gamecore',{}).get('sha256') or \
       base.get('sha256')!=city.get('gamecore',{}).get('sha256') or \
       found.get('gamecore',{}).get('sha256')==base.get('sha256'):
        raise RuntimeError('The found-value SDK is not a distinct isolated extension of the selected CitySite build')


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
    ui_assets=PROJECT/'evidence/ui_popup/assets/prepared.json'
    if ui_assets.exists():
        shutil.copy2(ui_assets,frozen/'ui_assets.json')
        built['ui_assets']=artifact(frozen/'ui_assets.json')
    check_artifacts(built)
    (frozen/'build_result.json').write_text(json.dumps(built,indent=2)+'\n')
    (ROOT/('candidate_build_shared.json' if shared else 'candidate_build.json')).write_text(json.dumps(built,indent=2)+'\n')
    print('NEW_GAME_CANDIDATE_BUILT',flush=True)

def main():
    import ctypes
    parser=argparse.ArgumentParser();parser.add_argument('--compile',action='store_true')
    parser.add_argument('--host-build',type=Path,help='Use a sealed isolated host build without replacing the accepted candidate')
    parser.add_argument('--ui-window-popups',action='store_true',help='Drive live official popups through an owned hidden HWND; requires a window host build and UI unit actions')
    parser.add_argument('--ui-window-display',action='store_true',help='Opt in to owned GPU HWND display resize and posted test input; requires --ui-window-popups')
    parser.add_argument('--ui-window-refresh',action='store_true',help='Opt in to closed-scene refresh in the owned GPU HWND; requires --ui-window-display')
    parser.add_argument('--shared-lua',action='store_true')
    parser.add_argument('--sdk-new-game',action='store_true')
    parser.add_argument('--sdk-save-restore',action='store_true',help='Use the isolated SDK serialization repair candidate')
    parser.add_argument('--restore-sdk-build',type=Path,help='Use a specific recorded restore SDK build for isolated diagnosis')
    parser.add_argument('--sdk-explore',action='store_true',help='Use the isolated SDK exploration scoring candidate')
    parser.add_argument('--workers',type=int,choices=(0,1,2,4),default=0,help='Exploration scoring workers; zero preserves the original SDK path')
    parser.add_argument('--sdk-city-sites',action='store_true',help='Use the linked city-site scoring SDK candidate')
    parser.add_argument('--city-site-workers',type=int,choices=(0,1,2,4),default=0,help='City-site scoring workers; requires --sdk-city-sites when nonzero')
    parser.add_argument('--city-site-cpu-trace',action='store_true',help='Opt in to scoring QPC/ETW markers; requires the city-site SDK and nonzero workers')
    parser.add_argument('--sdk-found-values',action='store_true',help='Use the isolated owned PlotFoundValue SDK candidate and diagnostics')
    parser.add_argument('--found-value-workers',type=int,choices=(0,1,2,4),default=0,help='Owned found-value workers; zero executes the original scalar function')
    parser.add_argument('--found-value-layout',choices=('dense','shared'),default='dense',help='Select the separately recorded dense or shared-facts Found SDK candidate')
    parser.add_argument('--found-value-cpu-trace',action='store_true',help='Explicitly enable Found QPC/ETW markers for the shared SDK four-worker save/restore profile')
    parser.add_argument('--found-value-default-environment',action='store_true',help='Run the Found-value SDK with inherited worker/trace variables cleared and no overrides; requires --sdk-found-values and zero workers')
    parser.add_argument('--first-turn',action='store_true',help='Also bootstrap the initial human turn and verify idle updates')
    parser.add_argument('--turn-cycle',action='store_true',help='Submit SDK unit skip and normal end-turn inputs, then verify the next human turn')
    parser.add_argument('--save-restore',action='store_true',help='Save turn one, unload, restore into a fresh session, and resume a normal turn')
    parser.add_argument('--extra-turns',type=int,default=0,help='After the restored turn-two checkpoint, execute 1 to 98 more ordinary fixture turns')
    parser.add_argument('--ui-popups',action='store_true',help='Opt in to the retained official BNW ranking popup UI candidate; requires save-restore')
    parser.add_argument('--fixture-promotions',action='store_true',help='Opt in to recorded legal unit promotion inputs; requires UI popups, save-restore, and extra turns')
    parser.add_argument('--fixture-unit-actions',action='store_true',help='Opt in to SDK-selected unit-action promotion inputs; requires fixture promotions, UI popups, save-restore, and extra turns')
    parser.add_argument('--language',choices=('en_US','ko_KR'),default='en_US')
    parser.add_argument('--timeout',type=int,default=90);args=parser.parse_args()
    if not 10<=args.timeout<=300:parser.error('Timeout must be between 10 and 300 seconds')
    if args.sdk_new_game and not args.shared_lua:parser.error('The map-failure SDK candidate requires shared Lua')
    if args.sdk_save_restore and not (args.shared_lua and args.sdk_new_game):parser.error('The save-restore SDK candidate requires shared Lua and the new-game SDK base')
    if args.restore_sdk_build and not args.sdk_save_restore:parser.error('An explicit restore SDK build requires --sdk-save-restore')
    if args.sdk_explore and not args.sdk_save_restore:parser.error('The exploration SDK candidate requires the save-restore SDK base')
    if args.workers and not args.sdk_explore:parser.error('Worker selection requires the exploration SDK candidate')
    if args.sdk_city_sites and not (args.sdk_explore and args.sdk_save_restore):
        parser.error('--sdk-city-sites requires --sdk-explore and --sdk-save-restore')
    if args.city_site_workers and not args.sdk_city_sites:
        parser.error('Nonzero --city-site-workers requires --sdk-city-sites')
    if args.city_site_cpu_trace and not (args.sdk_city_sites and args.city_site_workers):
        parser.error('--city-site-cpu-trace requires --sdk-city-sites and nonzero --city-site-workers')
    if args.sdk_found_values and not args.sdk_city_sites:
        parser.error('--sdk-found-values requires --sdk-city-sites and its base chain')
    if args.found_value_workers and not args.sdk_found_values:
        parser.error('--found-value-workers requires --sdk-found-values')
    if args.found_value_default_environment and (not args.sdk_found_values or args.found_value_workers!=0):
        parser.error('--found-value-default-environment requires --sdk-found-values and --found-value-workers 0')
    if args.found_value_layout=='shared' and not args.sdk_found_values:
        parser.error('--found-value-layout shared requires --sdk-found-values')
    if args.found_value_cpu_trace and not (args.sdk_found_values and args.found_value_layout=='shared' and
        args.found_value_workers==4 and args.save_restore and not args.found_value_default_environment):
        parser.error('--found-value-cpu-trace requires the shared Found SDK, four workers and explicit save/restore diagnostics')
    if not 0<=args.extra_turns<=98 or (args.extra_turns and not args.save_restore):parser.error('Extra turns require --save-restore and a count from 1 to 98')
    if args.ui_popups and not args.save_restore:parser.error('The isolated UI popup candidate requires --save-restore')
    if args.fixture_promotions and not (args.ui_popups and args.save_restore and args.extra_turns>0):
        parser.error('--fixture-promotions requires --ui-popups, --save-restore, and --extra-turns greater than zero')
    if args.fixture_unit_actions and not (args.fixture_promotions and args.ui_popups and args.save_restore and args.extra_turns>0):
        parser.error('--fixture-unit-actions requires --fixture-promotions, --ui-popups, --save-restore, and --extra-turns greater than zero')
    if args.ui_window_popups and not (args.host_build and args.shared_lua and args.fixture_unit_actions and args.extra_turns==48):
        parser.error('--ui-window-popups requires --host-build, --shared-lua and the 48-extra-turn UI unit-action profile')
    if args.ui_window_display and not args.ui_window_popups:
        parser.error('--ui-window-display requires --ui-window-popups')
    if args.ui_window_refresh and not args.ui_window_display:
        parser.error('--ui-window-refresh requires --ui-window-display')
    if args.host_build and args.compile:parser.error('--host-build and --compile are mutually exclusive')
    if sum((args.turn_cycle,args.first_turn,args.save_restore))>1:parser.error('Choose one first-turn, turn-cycle, or save-restore mode')
    cycle=args.turn_cycle or args.save_restore
    initial_turn=args.first_turn or cycle
    ROOT.mkdir(parents=True,exist_ok=True)
    run_root=PROJECT/('evidence/save_restore' if args.save_restore else ('evidence/turn_cycle' if cycle else 'evidence/first_turn')) if initial_turn else ROOT
    run_root.mkdir(parents=True,exist_ok=True)
    if args.compile:compile_candidate(args.shared_lua)
    build_path=args.host_build.resolve() if args.host_build else ROOT/('candidate_build_shared.json' if args.shared_lua else 'candidate_build.json')
    build=json.loads(build_path.read_text());check_artifacts(build)
    if args.ui_window_popups and build.get('status')!='UI_WINDOW_HOST_CANDIDATE_BUILT':
        raise RuntimeError('Live UI window requires its separately sealed x64 presentation host')
    runtime=json.loads((PROJECT/'evidence/shared_lua_runtime/build_result.json').read_text()) if args.shared_lua else None
    if runtime:check_artifacts(runtime)
    sdk_path=PROJECT/'evidence/new_game_sdk/build_result.json'
    sdk=json.loads(sdk_path.read_text()) if args.sdk_new_game else None
    if sdk:check_artifacts(sdk)
    restore_sdk_path=args.restore_sdk_build.resolve() if args.restore_sdk_build else PROJECT/'evidence/save_restore_sdk/build_result.json'
    restore_sdk=json.loads(restore_sdk_path.read_text()) if args.sdk_save_restore else None
    if restore_sdk:check_artifacts(restore_sdk)
    if restore_sdk and restore_sdk.get('status')!='SAVE_RESTORE_SDK_CANDIDATE_LINKED':raise RuntimeError('The selected restore SDK build is not linked')
    explore_sdk_path=PROJECT/'evidence/explore_sdk/build_result.json'
    explore_sdk=json.loads(explore_sdk_path.read_text()) if args.sdk_explore else None
    if explore_sdk:
        check_artifacts(explore_sdk)
        if explore_sdk.get('status')!='EXPLORE_SDK_CANDIDATE_LINKED':
            raise RuntimeError('The selected exploration SDK build is not linked')
    city_site_sdk_path=PROJECT/'evidence/city_site_sdk/build_result.json'
    city_site_sdk=json.loads(city_site_sdk_path.read_text()) if args.sdk_city_sites else None
    if city_site_sdk:
        check_artifacts(city_site_sdk)
        if city_site_sdk.get('status')!='CITY_SITE_SDK_CANDIDATE_LINKED':
            raise RuntimeError('The selected city-site SDK build is not linked')
        if not explore_sdk:raise RuntimeError('The city-site SDK requires an exploration SDK input')
        verify_city_site_base(city_site_sdk,explore_sdk)
        if city_site_sdk.get('gamecore',{}).get('sha256')==explore_sdk.get('gamecore',{}).get('sha256'):
            raise RuntimeError('The city-site SDK must identify its linked candidate GameCore separately')
    found_value_layout='SHARED_FACTS' if args.found_value_layout=='shared' else 'DENSE'
    found_value_sdk_path=PROJECT/('evidence/found_value_shared_sdk/build_result.json' if args.found_value_layout=='shared' else 'evidence/found_value_sdk/build_result.json')
    found_value_sdk=json.loads(found_value_sdk_path.read_text()) if args.sdk_found_values else None
    if found_value_sdk:verify_found_value_base(found_value_sdk,city_site_sdk,found_value_layout)
    core=(found_value_sdk or city_site_sdk or explore_sdk or restore_sdk or sdk or runtime)['gamecore'] if runtime else None
    bundle=json.loads((PROJECT/'evidence/host/bundle.json').read_text())
    # Consume the frozen baseline's bytes, not the current source of its old
    # builder. This does not certify that a historical build recipe is current.
    check_artifacts(bundle['files']);check_artifacts(bundle['manifest'])
    link=json.loads((PROJECT/'evidence/sdk_x64/link_analysis.json').read_text());check_artifacts(link['generated_dll'])
    run_id=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:12]
    directory=PROJECT/'Build/NewGameRuntime'/run_id;evidence=run_root/run_id
    directory.mkdir(parents=True,exist_ok=False);evidence.mkdir(parents=True,exist_ok=False)
    rows=[];materializations=[]
    def materialize(source,target):
        if source.suffix.lower() in ('.dll','.exe','.bin','.dat'):
            materializations.append(materialize_immutable(source,target,PROJECT/'Build/RuntimeInputCache'))
        else:
            shutil.copy2(source,target)
            materializations.append({'target':str(target),'materialization_method':'private-copy','size':target.stat().st_size})
    for row in bundle['files']:
        name=Path(row['path']).name;source=Path(build['executable']['path']) if name=='ZeroSisHost_x64.exe' else Path(row['path'])
        if runtime and name=='CvGameCoreDLL_Expansion2_x64.dll':source=Path(core['path'])
        target=directory/name;materialize(source,target)
        if digest(target)!=digest(source):raise RuntimeError('New-game input copy differs')
        rows.append({'source':str(source),**artifact(target)})
    if runtime:
        source=Path(runtime['lua_dll']['path']);target=directory/source.name;materialize(source,target);rows.append({'source':str(source),**artifact(target)})
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
    shutil.copy2(PROJECT/'tools/runtime_input_cache.py',evidence/'runtime_input_cache.py')
    if runtime:shutil.copy2(PROJECT/'evidence/shared_lua_runtime/build_result.json',evidence/'shared_lua_build.json')
    if sdk:shutil.copy2(sdk_path,evidence/'sdk_build.json')
    if restore_sdk:shutil.copy2(restore_sdk_path,evidence/'restore_sdk_build.json')
    if explore_sdk:shutil.copy2(explore_sdk_path,evidence/'explore_sdk_build.json')
    if city_site_sdk:
        shutil.copy2(city_site_sdk_path,evidence/'city_site_sdk_build.json')
        if digest(evidence/'city_site_sdk_build.json')!=digest(city_site_sdk_path):
            raise RuntimeError('The city-site SDK report changed while copying it into run evidence')
    if found_value_sdk:
        shutil.copy2(found_value_sdk_path,evidence/'found_value_sdk_build.json')
        if digest(evidence/'found_value_sdk_build.json')!=digest(found_value_sdk_path):
            raise RuntimeError('The found-value SDK report changed while copying it into run evidence')
    environment=os.environ.copy();environment['ZEROSIS_EXPLORE_WORKERS']=str(args.workers)
    environment.pop('ZEROSIS_UI_WINDOW_PROFILE',None)
    if args.ui_window_refresh:environment['ZEROSIS_UI_WINDOW_PROFILE']='display-refresh'
    elif args.ui_window_display:environment['ZEROSIS_UI_WINDOW_PROFILE']='display-resize'
    if args.sdk_city_sites:environment['ZEROSIS_CITY_SITE_WORKERS']=str(args.city_site_workers)
    else:environment.pop('ZEROSIS_CITY_SITE_WORKERS',None)
    # Trace markers are a separate explicit diagnostic opt-in. Inherited
    # environment variables must never enable them in ordinary comparisons.
    environment.pop('ZEROSIS_CITY_SITE_CPU_TRACE',None)
    if args.city_site_cpu_trace:environment['ZEROSIS_CITY_SITE_CPU_TRACE']='1'
    environment.pop('ZEROSIS_FOUND_VALUE_WORKERS',None)
    environment.pop('ZEROSIS_FOUND_VALUE_TRACE',None)
    environment.pop('ZEROSIS_FOUND_VALUE_CPU_TRACE',None)
    if args.found_value_cpu_trace:environment['ZEROSIS_FOUND_VALUE_CPU_TRACE']='1'
    if args.sdk_found_values and not args.found_value_default_environment:
        environment['ZEROSIS_FOUND_VALUE_WORKERS']=str(args.found_value_workers)
        environment['ZEROSIS_FOUND_VALUE_TRACE']='1'
    command=[str(directory/'ZeroSisHost_x64.exe'),'--check-save-restore' if args.save_restore else ('--check-turn-cycle' if cycle else ('--check-first-turn' if args.first_turn else '--check-new-game')),args.language]
    if args.ui_popups:command[1]='--check-save-restore-ui'
    if args.fixture_unit_actions:command[1]='--check-save-restore-ui-actions'
    elif args.fixture_promotions:command[1]='--check-save-restore-ui-promotions'
    if args.extra_turns:command.append(str(args.extra_turns))
    if args.ui_window_popups:command[1]='--check-save-restore-ui-window-actions'
    ui_window_tools=[]
    if args.ui_window_popups:
        tools_directory=directory/'UiPresentationTools/tools'
        for relative in ('tools/live_ui_window_driver.py','tools/render_ui_popup.py','tools/ui_pixel_scene.py',
                         'tools/ui_bitmap_fonts.py','tools/civ5_ui_assets.py'):
            source=PROJECT/relative;target=directory/'UiPresentationTools'/relative
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            if digest(source)!=digest(target):raise RuntimeError('Live UI presentation helper changed while freezing')
            ui_window_tools.append({'original_source':str(source),**artifact(target)})
        if args.ui_window_display:
            source=PROJECT/'tools/ui_window_frame.py';target=directory/'UiPresentationTools/tools/ui_window_frame.py'
            target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target)
            if digest(source)!=digest(target):raise RuntimeError('GPU UI window frame helper changed while freezing')
            ui_window_tools.append({'original_source':str(source),**artifact(target)})
    request={'run_id':run_id,'command':command,'cwd':str(directory),'timeout_seconds':args.timeout,
        'candidate_build':artifact(evidence/'candidate_build.json'),'runner':artifact(evidence/'runner.py'),
        'runtime_cache_helper':artifact(evidence/'runtime_input_cache.py'),'input_materializations':materializations,
        'inputs':rows,'host_source_snapshots':snapshots,'gamecore_link':artifact(PROJECT/'evidence/sdk_x64/link_analysis.json'),
        'accepted_bundle':artifact(PROJECT/'evidence/host/bundle.json'),
        'shared_lua_build':artifact(evidence/'shared_lua_build.json') if runtime else None,
        'new_game_sdk_build':artifact(evidence/'sdk_build.json') if sdk else None,
        'save_restore_sdk_build':artifact(evidence/'restore_sdk_build.json') if restore_sdk else None,
        'explore_sdk_build':artifact(evidence/'explore_sdk_build.json') if explore_sdk else None,
        'city_site_sdk_build':artifact(evidence/'city_site_sdk_build.json') if city_site_sdk else None,
        'city_site_workers_enabled':args.sdk_city_sites,
        'city_site_workers':args.city_site_workers if args.sdk_city_sites else 0,
        'city_site_cpu_trace_enabled':args.city_site_cpu_trace,
        'found_value_sdk_build':artifact(evidence/'found_value_sdk_build.json') if found_value_sdk else None,
        'found_value_input_layout':found_value_layout if args.sdk_found_values else 'NOT_ENABLED',
        'found_value_cpu_trace_enabled':args.found_value_cpu_trace,
        'found_value_cpu_trace_environment_overrides':{'ZEROSIS_FOUND_VALUE_CPU_TRACE':'1'} if args.found_value_cpu_trace else {},
        'found_value_workers_enabled':args.sdk_found_values,
        'found_value_workers':args.found_value_workers if args.sdk_found_values else 0,
        'found_value_trace_enabled':args.sdk_found_values and not args.found_value_default_environment,
        'found_value_default_environment_profile':'SERIAL_TRACE_OFF' if args.found_value_default_environment else ('EXPLICIT_OVERRIDES' if args.sdk_found_values else 'NOT_ENABLED'),
        'found_value_environment_overrides':({'ZEROSIS_FOUND_VALUE_WORKERS':str(args.found_value_workers),
                                            'ZEROSIS_FOUND_VALUE_TRACE':'1'} if args.sdk_found_values and not args.found_value_default_environment else {}),
        'inherited_found_value_environment_removed':True,
        'inherited_found_value_cpu_trace_environment_removed':True,
        'diagnostic_environment_overrides':{'ZEROSIS_CITY_SITE_CPU_TRACE':'1'} if args.city_site_cpu_trace else {},
        'inherited_cpu_trace_environment_removed':True,
        'environment_overrides':({'ZEROSIS_EXPLORE_WORKERS':str(args.workers),
                                  'ZEROSIS_CITY_SITE_WORKERS':str(args.city_site_workers)} if args.sdk_city_sites else
                                 {'ZEROSIS_EXPLORE_WORKERS':str(args.workers)}),
        'extra_restored_turns':args.extra_turns,
        'ui_popups_enabled':args.ui_popups,
        'ui_window_popups_enabled':args.ui_window_popups,'ui_window_display_enabled':args.ui_window_display,
        'ui_window_refresh_enabled':args.ui_window_refresh,
        'inherited_ui_window_profile_environment_removed':True,
        'ui_window_profile_environment_overrides':({'ZEROSIS_UI_WINDOW_PROFILE':'display-refresh'} if args.ui_window_refresh else
            ({'ZEROSIS_UI_WINDOW_PROFILE':'display-resize'} if args.ui_window_display else {})),
        'ui_window_tools':ui_window_tools,
        'fixture_promotions_enabled':args.fixture_promotions,
        'fixture_unit_actions_enabled':args.fixture_unit_actions,
        'session_activation':{'source':'COMPILED_HOST_FIXED_CONFIGURATION','active_mods':[]},
        'scope':'ACTUAL_ISOLATED_SDK_NATIVE_SAVE_RESTORE_AND_RESUMED_TURN' if args.save_restore else ('ACTUAL_ISOLATED_SDK_UNIT_SKIP_AND_END_TURN_CYCLE' if cycle else ('ACTUAL_ISOLATED_FIRST_TURN_ENTRY_CANDIDATE' if args.first_turn else
            'ACTUAL_ISOLATED_NEW_GAME_CANDIDATE_NOT_ACCEPTED_HOST_OR_TURN_VERIFICATION'))}
    (evidence/'request.json').write_text(json.dumps(request,indent=2)+'\n')
    if args.ui_window_popups:
        # Resolve the frozen driver before launching the child; import failures
        # cannot leave a host blocked on its presentation handshake.
        sys.path.insert(0,str(tools_directory))
        from live_ui_window_driver import collect_live_window
        if args.ui_window_display:
            from ui_window_frame import verify_frame
    attempt={'status':'PENDING_START','pid':None,'command':command,
             'executable':artifact(Path(command[0])),'request':artifact(evidence/'request.json')}
    (evidence/'attempt.json').write_text(json.dumps(attempt,indent=2)+'\n')
    print('RUN_NEW_GAME '+run_id,flush=True)
    kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.SetErrorMode.argtypes=[ctypes.c_uint];kernel.SetErrorMode.restype=ctypes.c_uint
    old=kernel.SetErrorMode(0x0001|0x0002|0x8000);start=time.monotonic()
    try:process=subprocess.Popen(command,cwd=directory,env=environment,stdin=subprocess.PIPE if args.ui_window_popups else subprocess.DEVNULL,
                                 stdout=subprocess.PIPE,stderr=subprocess.PIPE,creationflags=subprocess.CREATE_NO_WINDOW)
    finally:kernel.SetErrorMode(old)
    attempt.update(status='RUNNING',pid=process.pid)
    try:(evidence/'attempt.json').write_text(json.dumps(attempt,indent=2)+'\n')
    except Exception:
        if process.poll() is None:process.kill()
        process.communicate(timeout=5)
        raise
    timed_out=False
    ui_window_report=None
    if args.ui_window_popups:
        try:
            stdout,stderr,timed_out,ui_window_report=collect_live_window(process,directory,evidence,args.timeout,tools_directory,
                                                                          display_resize=args.ui_window_display,
                                                                          refresh_closed=args.ui_window_refresh)
        except Exception as error:
            # This also covers failure before the driver's normal cleanup guard.
            if process.poll() is None:process.kill()
            stdout,stderr=process.communicate(timeout=5)
            ui_window_report={'status':'LIVE_SDK_UI_WINDOW_FAILED','pid':process.pid,
                              'error':str(error),'cleanup':'owned_child_reaped_by_runner',
                              'returncode':process.returncode,'timed_out':False}
            (evidence/'ui_window.json').write_text(json.dumps(ui_window_report,indent=2)+'\n')
    else:
        try:stdout,stderr=process.communicate(timeout=args.timeout)
        except subprocess.TimeoutExpired:timed_out=True;process.kill();stdout,stderr=process.communicate()
    attempt.update(status='FINISHED',returncode=process.returncode,returncode_hex=f'0x{process.returncode&0xffffffff:08X}',timed_out=timed_out)
    (evidence/'attempt.json').write_text(json.dumps(attempt,indent=2)+'\n')
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
    if args.ui_window_popups:
        success=success and ui_window_report['status']=='LIVE_SDK_UI_WINDOW_POSTED_INPUT_PASS' and \
            all(digest(Path(row['path']))==row['sha256'] for row in ui_window_tools) and \
            output.count('UI_WINDOW_STATE_UNCHANGED=')==2 and 'HOST_NATIVE_EXCEPTION' not in output
        if args.ui_window_display:
            success=success and ui_window_report.get('display_resize_enabled') is True
            if not args.ui_window_refresh:
                success=success and ui_window_report.get('scope')=='actual_live_SDK_UI_VM_and_owned_GPU_HWND_display_resize_with_posted_test_input'
        elif ui_window_report.get('display_resize_enabled',False) is not False:
            success=False
        if args.ui_window_refresh:
            success=success and ui_window_report.get('refresh_closed_enabled') is True and \
                ui_window_report.get('scope')=='actual_live_SDK_UI_VM_and_owned_GPU_HWND_closed_scene_refresh_with_posted_test_input'
        elif ui_window_report.get('refresh_closed_enabled',False) is not False:
            success=False
    refresh_markers=re.findall(r'^UI_WINDOW_REFRESH_STATE_UNCHANGED=(\d+)\|after-refresh$',output,re.M)
    if args.ui_window_refresh:
        success=success and refresh_markers==['1','2']
    elif re.findall(r'^UI_WINDOW_REFRESH_STATE_UNCHANGED=([^\r\n]*)$',output,re.M):
        success=False
    first_turn=re.findall(r'^FIRST_TURN_OBSERVATION=([-\d,]+)$',output,re.M)
    turn_values=[int(value) for value in first_turn[0].split(',')] if len(first_turn)==1 else []
    marker='NATIVE_RESTORE_SHUTDOWN_PASS GAMECORE_LOADED=true RESTORE_VERIFIED=true RESUMED_TURN_VERIFIED=true' if args.save_restore else ('TURN_CYCLE_SHUTDOWN_PASS GAMECORE_LOADED=true TURN_CYCLE_VERIFIED=true' if cycle else \
        ('FIRST_TURN_SHUTDOWN_PASS GAMECORE_LOADED=true TURN_ENTRY_VERIFIED=true TURNS_VERIFIED=false' if args.first_turn else \
        'NEW_GAME_SHUTDOWN_PASS GAMECORE_LOADED=true TURNS_VERIFIED=false'))
    success=success and 'CORE_MODULE_UNLOADED=true' in output and marker in output
    session_active_mods=re.findall(r'^SESSION_ACTIVE_MODS=(\d+)$',output,re.M)
    success=success and session_active_mods==(['0','0'] if args.save_restore else ['0'])
    if args.ui_popups:
        success=success and output.count('UI_POPUP_CONTEXT=OFFICIAL_BNW_WHOS_WINNING_PERSISTENT_VM_RETAINED_CONTROLS')==2 and \
            len(re.findall(r'^UI_POPUP_CONTEXT_CLOSED=\d+$',output,re.M))==2
    if initial_turn:success=success and turn_values==[0,0,0,1,1,3]
    cycles=re.findall(r'^TURN_CYCLE_OBSERVATION=([-\d,]+)$',output,re.M)
    cycle_values=[int(value) for value in cycles[0].split(',')] if len(cycles)==1 else []
    if cycle:success=success and len(cycle_values)==8 and cycle_values[:6]==[0,1,1,0,1,1] and 1<=cycle_values[6]<=256 and cycle_values[7]==3
    restored=re.findall(r'^NATIVE_RESTORE_OBSERVATION=([-\d,]+)$',output,re.M)
    restored_values=[int(value) for value in restored[0].split(',')] if len(restored)==1 else []
    resumed=re.findall(r'^RESTORED_TURN_CYCLE_OBSERVATION=([-\d,]+)$',output,re.M)
    resumed_values=[int(value) for value in resumed[0].split(',')] if len(resumed)==1 else []
    if args.save_restore:
        success=success and restored_values==[1,1,0,40,24,960,1,1,3] and len(resumed_values)==8 and \
            resumed_values[:6]==[1,2,2,0,1,1] and 1<=resumed_values[6]<=256 and resumed_values[7]==3 and \
            'NATIVE_RESTORE_STATE_EQUAL=true' in output and 'RESTORED_CORE_MODULE_UNLOADED=true' in output
    extended_values=[[int(value) for value in line.split(',')] for line in re.findall(r'^EXTENDED_TURN_CYCLE_OBSERVATION=([-\d,]+)$',output,re.M)]
    promotion_rows=re.findall(r'^EXTENDED_TURN_CYCLE_PROMOTION=([^\r\n]+)$',output,re.M)
    promotion_policies=re.findall(r'^EXTENDED_TURN_CYCLE_PROMOTION_POLICY=([^\r\n]+)$',output,re.M)
    unit_actions_valid,input_routes,action_records=inspect_fixture_unit_action_output(
        output,args.extra_turns,args.fixture_promotions,args.fixture_unit_actions)
    if args.fixture_unit_actions:success=success and unit_actions_valid
    if args.extra_turns:
        success=success and len(extended_values)==args.extra_turns and \
            all(len(row)==8 and row[:6]==[index+2,index+3,index+3,0,1,1] and 1<=row[6]<=256 and row[7]==3 for index,row in enumerate(extended_values)) and \
            output.splitlines().count(f'EXTENDED_TURNS_COMPLETE=2,{args.extra_turns+2},{args.extra_turns}')==1
        if args.fixture_promotions:
            success=success and len(promotion_rows)>=1 and \
                promotion_policies==['SHOCK_1_SHOCK_2_SHOCK_3_FIRST_LEGAL']*args.extra_turns
        elif promotion_rows or promotion_policies:
            success=False
    elif extended_values:success=False
    original={row['path'] for row in rows}
    status_prefix='ISOLATED_NATIVE_SAVE_RESTORE' if args.save_restore else ('ISOLATED_TURN_CYCLE' if cycle else ('ISOLATED_FIRST_TURN_ENTRY' if args.first_turn else 'ISOLATED_NEW_GAME_CANDIDATE'))
    if args.extra_turns:status_prefix+='_EXTENDED'
    report={'status':status_prefix+('_PASS' if success else '_FAILED'),
        'ui_window_popups_enabled':args.ui_window_popups,
        'ui_window_display_enabled':args.ui_window_display,
        'ui_window_refresh_enabled':args.ui_window_refresh,
        'inherited_ui_window_profile_environment_removed':True,
        'ui_window_profile_environment_overrides':({'ZEROSIS_UI_WINDOW_PROFILE':'display-refresh'} if args.ui_window_refresh else
            ({'ZEROSIS_UI_WINDOW_PROFILE':'display-resize'} if args.ui_window_display else {})),
        'ui_window_report':artifact(evidence/'ui_window.json') if args.ui_window_popups else None,
        'process_id':process.pid,'city_site_cpu_trace_enabled':args.city_site_cpu_trace,
        'request':artifact(evidence/'request.json'),'exit_code':process.returncode,'exit_code_hex':f'0x{process.returncode&0xffffffff:08X}',
        'timed_out':timed_out,'duration_seconds':time.monotonic()-start,'stdout':artifact(evidence/'stdout.log'),'stderr':artifact(evidence/'stderr.log'),
        'phases':re.findall(r'^NEW_GAME_PHASE=(.+)$',output,re.M),'host_failures':re.findall(r'^HOST_FAILURE: (.+)$',output,re.M),
        'first_turn_phases':re.findall(r'^FIRST_TURN_PHASE=(.+)$',output,re.M),
        'first_turn_states':re.findall(r'^FIRST_TURN_STATE=(.+)$',output,re.M),
        'first_turn_observation':turn_values,'turn_entry_verified':bool(initial_turn and success),
        'turn_cycle_observation':cycle_values,'turn_cycle_verified':bool(cycle and success),
        'restore_observation':restored_values,'restore_verified':bool(args.save_restore and success),
        'restore_phases':re.findall(r'^NATIVE_RESTORE_PHASE=(.+)$',output,re.M),
        'restored_turn_observation':resumed_values,'resumed_turn_verified':bool(args.save_restore and success),
        'restored_turn_states':re.findall(r'^RESTORED_TURN_CYCLE_STATE=(.+)$',output,re.M),
        'extra_restored_turns':args.extra_turns,'extended_turn_observations':extended_values,
        'extended_turns_verified':bool(args.extra_turns and success),
        'city_site_workers_enabled':args.sdk_city_sites,
        'city_site_workers':args.city_site_workers if args.sdk_city_sites else 0,
        'fixture_promotions_enabled':args.fixture_promotions,
        'found_value_input_layout':found_value_layout if args.sdk_found_values else 'NOT_ENABLED',
        'found_value_cpu_trace_enabled':args.found_value_cpu_trace,
        'found_value_cpu_trace_environment_overrides':{'ZEROSIS_FOUND_VALUE_CPU_TRACE':'1'} if args.found_value_cpu_trace else {},
        'found_value_workers_enabled':args.sdk_found_values,
        'found_value_workers':args.found_value_workers if args.sdk_found_values else 0,
        'found_value_trace_enabled':args.sdk_found_values and not args.found_value_default_environment,
        'found_value_default_environment_profile':'SERIAL_TRACE_OFF' if args.found_value_default_environment else ('EXPLICIT_OVERRIDES' if args.sdk_found_values else 'NOT_ENABLED'),
        'fixture_promotions_verified':bool(args.fixture_promotions and success),
        'fixture_unit_actions_enabled':args.fixture_unit_actions,
        'fixture_unit_actions_verified':bool(args.fixture_unit_actions and success),
        'session_active_mods':[int(value) for value in session_active_mods],
        'fixture_promotion_policy_logs':promotion_policies,
        'fixture_promotion_logs':promotion_rows,
        'extended_input_routes':input_routes,
        'action_records':action_records,
        'turn_cycle_states':re.findall(r'^TURN_CYCLE_STATE=(.+)$',output,re.M),
        'turn_cycle_events':[{'count':int(count),'event':event} for count,event in re.findall(r'^TURN_CYCLE_EVENT=(\d+)\|(.+)$',output,re.M)],
        'script_failures':re.findall(r'^SCRIPT_FAILURE: (.+)$',output,re.M),
        'platform_statistics_available':False if 'PLATFORM_STATISTICS_AVAILABLE=false' in output else
            (True if 'PLATFORM_STATISTICS_AVAILABLE=true' in output else None),
        'host_service_events':[{'count':int(count),'event':event} for count,event in re.findall(r'^NEW_GAME_HOST_EVENT=(\d+)\|(.+)$',output,re.M)],
        'cleanup_completed':any(marker in output for marker in ('HOST_CLEANUP_PASS','NEW_GAME_SHUTDOWN_PASS','FIRST_TURN_SHUTDOWN_PASS','TURN_CYCLE_SHUTDOWN_PASS','NATIVE_RESTORE_SHUTDOWN_PASS')),
        'module_unloaded':'CORE_MODULE_UNLOADED=true' in output,
        'observation':values,'lua_observation':lua_values,
        'candidate_inputs_unchanged':unchanged,'accepted_bundle_unchanged':accepted_unchanged,
        'generated_files':[artifact(p) for p in sorted(directory.rglob('*')) if p.is_file() and str(p) not in original],
        'core_initialized':'CORE_INITIALIZED; attempting isolated new game.' in output,
        'configuration_verified':'NEW_GAME_CONFIGURATION_VERIFIED' in output,'new_game_candidate_verified':success and measured,
        'turn_execution_verified':bool(cycle and success),'game_multicore_verified':False,'installed_game_launched':False}
    (evidence/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    (run_root/'latest.json').write_text(json.dumps(artifact(evidence/'result.json'),indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('status','exit_code_hex','phases','host_failures','observation')}),flush=True)
    if not success:print(output[-7000:],flush=True)
    return 0 if success else 1

if __name__=='__main__':sys.exit(main())
