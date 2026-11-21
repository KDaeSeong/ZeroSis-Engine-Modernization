"""Validate bounded actual GameCore runtime evidence separately from component tests."""
import argparse,json,re,sqlite3
from pathlib import Path
from collect_baseline import PROJECT,digest,read_text
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts

ROOT=PROJECT/'evidence/host_runtime'
FINALIZER='CORE_LUA_SHUTDOWN_PASS finalizers=1 player_retired=true team_retired=true owner_lock=true globals_stopped=true'
GAME_INFO_TABLES=('Worlds','Terrains','Features','Resources','Improvements','Eras','Civilizations','Units','Buildings','MapScripts','Map_Sizes','Natural_Wonder_Placement')

def inspect_run(run_id):
    if not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}',run_id):raise ValueError('Invalid runtime run identifier')
    result_path=ROOT/run_id/'result.json';result=json.loads(result_path.read_text())
    check_artifacts(result)
    request=json.loads(Path(result['request']['path']).read_text());check_artifacts(request)
    build=json.loads((PROJECT/'evidence/host/build_result.json').read_text())
    bundle=json.loads((PROJECT/'evidence/host/bundle.json').read_text())
    link=json.loads((PROJECT/'evidence/sdk_x64/link_analysis.json').read_text())
    for name,current in (('host_build',PROJECT/'evidence/host/build_result.json'),('bundle',PROJECT/'evidence/host/bundle.json'),
                         ('gamecore_link',PROJECT/'evidence/sdk_x64/link_analysis.json'),('runner',PROJECT/'tools/run_gamecore_initialization.py')):
        if request[name]['sha256']!=digest(current):raise RuntimeError('Runtime evidence uses different current inputs: '+name)
    directory=PROJECT/'Build/HostRuntime'/run_id
    command=request['command'];language=command[-1]
    if request['mode']!='check-core' or request['run_id']!=run_id or Path(request['cwd'])!=directory or command!=[str(directory/'ZeroSisHost_x64.exe'),'--check-core',language]:
        raise RuntimeError('Unexpected actual runtime invocation')
    if language not in ('en_US','ko_KR'):raise RuntimeError('Unexpected actual runtime language')
    snapshots={Path(row['original_source']):row['sha256'] for row in request['host_source_snapshots']}
    if snapshots!={Path(row['path']):row['sha256'] for row in build['sources']}:raise RuntimeError('Runtime source snapshot differs from the built host')
    compiled={Path(row['path']):row['sha256'] for row in build['host']['compiler_inputs']}
    for name in ('HostMain.cpp','HostRun.h','GameCoreSession.h','CoreRuntimeProbe.h','ScriptSystem.h','GameInfoDatabase.h','ScriptRules.h'):
        source=PROJECT/'Source/Host'/name
        if compiled.get(source)!=snapshots[source]:raise RuntimeError('Runtime probe source was not consumed by the compiler')
    expected={Path(row['path']).name:row['sha256'] for row in bundle['files']}
    expected['bundle.manifest']=bundle['manifest']['sha256']
    if {Path(row['path']).name:row['sha256'] for row in request['inputs']}!=expected or len(request['inputs'])!=10:
        raise RuntimeError('Executed bundle copy does not match current inputs')
    if any(Path(row['path']).parent!=directory for row in request['inputs']):raise RuntimeError('Runtime file is outside its fresh copy')
    if expected['CvGameCoreDLL_Expansion2_x64.dll']!=link['generated_dll']['sha256']:raise RuntimeError('Wrong linked GameCore was executed')
    if result['status']!='GAMECORE_INITIALIZATION_PASS' or result['exit_code']!=0 or result['timed_out']:
        raise RuntimeError('Actual core runtime did not finish successfully')
    required=('source_bundle_unchanged','copied_bundle_unchanged','gamecore_initialization_verified','gamecore_shutdown_verified',
        'actual_sdk_lua_observation_verified','actual_game_info_observation_verified','actual_player_team_retirement_verified','gamecore_module_unloaded_verified','gamecore_loaded')
    if not all(result[key] for key in required):raise RuntimeError('Actual runtime milestone missing')
    if any(result[key] for key in ('new_game_verified','turn_execution_verified','game_multicore_verified','installed_game_executable_launched')):
        raise RuntimeError('Runtime observation overclaims gameplay scope')
    output=read_text(Path(result['stdout']['path'])).replace('\r\n','\n')
    if read_text(Path(result['stderr']['path'])).strip():raise RuntimeError('Unexpected actual runtime stderr')
    for marker in ('CORE_INITIALIZED; new game and turn execution remain unimplemented.',FINALIZER,'CORE_MODULE_UNLOADED=true',
                   'CORE_SHUTDOWN_PASS GAMECORE_LOADED=true GAMEPLAY_VERIFIED=false'):
        if output.count(marker)!=1:raise RuntimeError('Missing or duplicate runtime milestone: '+marker)
    values=re.findall(r'^CORE_LUA_OBSERVATION=([-\d,]+)$',output,re.M)
    if len(values)!=1:raise RuntimeError('Actual core observations missing')
    values=[int(value) for value in values[0].split(',')]
    if len(values)!=11 or values[:6]!=[64,64,0,0,0,-1] or values[6]<=0 or values[10]!=1:
        raise RuntimeError('Unexpected pre-game object state or GameInfo support changed')
    info=re.findall(r'^GAME_INFO_OBSERVATION=([-\d,]+)$',output,re.M)
    if len(info)!=1:raise RuntimeError('Actual GameInfo observations missing')
    info=[int(value) for value in info[0].split(',')]
    files={Path(row['path']).name:Path(row['path']) for row in result['generated_files']}
    if set(files)!={'rules.db','Civ5SavedGameDatabase.db'} or len(result['generated_files'])!=2:
        raise RuntimeError('Unexpected runtime output files')
    sessions={path.parent for path in files.values()}
    if len(sessions)!=1 or next(iter(sessions)).parent!=directory/'sessions':raise RuntimeError('Runtime output escaped its session directory')
    with sqlite3.connect(files['rules.db'].as_uri()+'?mode=ro',uri=True) as db:
        expected_types=[db.execute('SELECT ID FROM '+table+' WHERE Type=?',(key,)).fetchone()[0]
            for table,key in (('Units','UNIT_SETTLER'),('Civilizations','CIVILIZATION_AMERICA'),('Buildings','BUILDING_MONUMENT'))]
        if values[7:10]!=expected_types or db.execute('PRAGMA quick_check').fetchall()!=[('ok',)]:
            raise RuntimeError('Actual Lua types/rules database disagree')
        expected_info=[db.execute('SELECT COUNT(*) FROM '+table).fetchone()[0] for table in GAME_INFO_TABLES]
        expected_info.extend(db.execute(query).fetchone()[0] for query in (
            "SELECT ID FROM Terrains WHERE Type='TERRAIN_GRASS'",
            "SELECT NoGoodies FROM Eras WHERE Type='ERA_ANCIENT'",
            "SELECT COUNT(*) FROM Eras WHERE NoGoodies!=0",
            "SELECT COUNT(*) FROM Features WHERE NaturalWonder=1",
            "SELECT COUNT(*) FROM Units WHERE Class='UNITCLASS_SETTLER' AND Combat=0"))
        if info!=expected_info:raise RuntimeError('Actual GameInfo iteration/filters differ from independent SQL')
    with sqlite3.connect(files['Civ5SavedGameDatabase.db'].as_uri()+'?mode=ro',uri=True) as db:
        if db.execute('PRAGMA quick_check').fetchall()!=[('ok',)] or db.execute('SELECT COUNT(*) FROM SimpleValues').fetchone()[0]!=0:
            raise RuntimeError('Actual initial save cache differs')
    if '\nLANGUAGE='+language+'\n' not in output:raise RuntimeError('Actual language selection differs')
    return {'run_id':run_id,'language':language,'result':artifact(result_path),'values':values,'game_info':info,'duration_seconds':result['duration_seconds']}

def record(run_ids):
    runs=sorted((inspect_run(run_id) for run_id in run_ids),key=lambda row:row['language'])
    if [row['language'] for row in runs]!=['en_US','ko_KR'] or runs[0]['values']!=runs[1]['values'] or runs[0]['game_info']!=runs[1]['game_info']:
        raise RuntimeError('Require both languages with identical initialized core observations')
    report={'status':'ACTUAL_GAMECORE_INITIALIZATION_AND_LUA_PASS','validator':artifact(Path(__file__).resolve()),'runs':runs,
        'host_build':artifact(PROJECT/'evidence/host/build_result.json'),'bundle':artifact(PROJECT/'evidence/host/bundle.json'),
        'gamecore_link':artifact(PROJECT/'evidence/sdk_x64/link_analysis.json'),
        'gamecore_loaded':True,'gamecore_initialization_verified':True,'gamecore_shutdown_and_unload_verified':True,
        'actual_sdk_library_registration_executed':True,'actual_player_team_ids_per_run':[64,64],
        'retired_player_team_handles_checked_per_run':[1,1],'game_info_global_present':bool(runs[0]['values'][10]),
        'game_info_tables':dict(zip(GAME_INFO_TABLES,runs[0]['game_info'][:12])),
        'game_info_sql_comparison_verified':True,
        'new_game_verified':False,'turn_execution_verified':False,'game_multicore_verified':False,
        'scope':'ACTUAL_FULL_GAMECORE_INITIALIZATION_LUA_REGISTRATION_SELECTED_READS_AND_TWO_RETIRED_HANDLES_NOT_NEW_GAME_OR_TURNS'}
    (ROOT/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    return report

def validate():
    report=json.loads((ROOT/'conformance.json').read_text());check_artifacts(report)
    observed=[inspect_run(row['run_id']) for row in report['runs']]
    if observed!=report['runs'] or [row['language'] for row in observed]!=['en_US','ko_KR'] or observed[0]['values']!=observed[1]['values']:
        raise RuntimeError('Runtime manifest differs from exact execution records')
    if report['status']!='ACTUAL_GAMECORE_INITIALIZATION_AND_LUA_PASS' or report['validator']!=artifact(Path(__file__).resolve()):
        raise RuntimeError('Runtime validator/report differs')
    if not all(report[key] for key in ('gamecore_loaded','gamecore_initialization_verified','gamecore_shutdown_and_unload_verified','actual_sdk_library_registration_executed')):
        raise RuntimeError('Actual initialization coverage missing')
    if report['game_info_global_present']!=bool(observed[0]['values'][10]):raise RuntimeError('GameInfo presence differs from runtime observation')
    if (not report['game_info_sql_comparison_verified'] or observed[0]['game_info']!=observed[1]['game_info']
        or report['game_info_tables']!=dict(zip(GAME_INFO_TABLES,observed[0]['game_info'][:12]))):
        raise RuntimeError('GameInfo SQL comparison differs from both runtime observations')
    if any(report[key] for key in ('new_game_verified','turn_execution_verified','game_multicore_verified')):
        raise RuntimeError('Actual initialization report overclaims game support')
    entry={'name':'ActualGameCoreInitialization','conformance':artifact(ROOT/'conformance.json'),'validator':artifact(Path(__file__).resolve()),'scope':report['scope']}
    return report,entry

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--record',nargs=2,metavar=('EN_RUN','KO_RUN'));args=parser.parse_args()
    if args.record:record(args.record)
    report,_=validate();print(json.dumps({'status':report['status'],'languages':[row['language'] for row in report['runs']],
        'players_per_run':report['actual_player_team_ids_per_run'][0],'teams_per_run':report['actual_player_team_ids_per_run'][1],
        'new_game_verified':False,'turn_execution_verified':False}))
