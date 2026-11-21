"""Independently verify persisted native saves, restored SDK observations and resumed turns."""
import argparse,collections,hashlib,json,re,shutil,uuid
from pathlib import Path
from collect_baseline import PROJECT
from probe_world_builder import artifact
from verify_first_turn_candidate import inspect_save,read_artifact
from verify_turn_cycle_candidate import inspect_cycle
from verify_world_builder_map_object import check_artifacts
from verify_restore_game_metadata import verify_game_restore

ROOT=PROJECT/'evidence/save_restore'


def one(output,key):
    values=re.findall(r'^'+re.escape(key)+r'=(.*)$',output,re.M)
    if len(values)!=1:raise RuntimeError('Expected one observation: '+key)
    return values[0]


def inspect_snapshot(data):
    text=data.decode('utf8');rows=[line.split('|') for line in text.splitlines()]
    groups=collections.defaultdict(list)
    for row in rows:groups[row[0]].append(row[1:])
    if set(groups)!={'G','M','P','U','C','T'} or groups['G']!=[['1','1','0','960']]:
        raise RuntimeError('Restored state snapshot categories or game identity differ')
    expected_widths={'G':4,'M':11,'P':10,'U':12,'C':11,'T':3}
    for kind,values in groups.items():
        if any(len(row)!=expected_widths[kind] for row in values):raise RuntimeError('State snapshot field width differs: '+kind)
        for row in values:
            numeric=row[:-1] if kind in ('C','U') else row
            if any(not re.fullmatch(r'-?\d+',value) for value in numeric):raise RuntimeError('Non-integral SDK snapshot field')
            if kind in ('C','U') and not re.fullmatch(r'(?:[0-9a-f]{2})*',row[-1]):raise RuntimeError('Invalid snapshot byte string')
    maps=[[int(value) for value in row] for row in groups['M']]
    if len(maps)!=960 or any(row[:3]!=[index,index%40,index//40] for index,row in enumerate(maps)):
        raise RuntimeError('SDK map snapshot is incomplete or reordered')
    players=[[int(value) for value in row] for row in groups['P']]
    if len(players)!=64 or [row[0] for row in players]!=list(range(64)):
        raise RuntimeError('SDK player snapshot is incomplete')
    alive=[row for row in players if row[1]]
    if [row[0] for row in alive]!=[0,1,22,23,63] or sum(row[2] for row in alive)!=1 or sum(row[3] for row in alive)!=1:
        raise RuntimeError('Restored player population differs')
    units=[[int(value) for value in row[:-1]] for row in groups['U']]
    cities=[[int(value) for value in row[:-1]] for row in groups['C']]
    for tag,items in (('units',units),('cities',cities)):
        if len({tuple(row[:2]) for row in items})!=len(items):raise RuntimeError('Duplicated SDK '+tag)
    if len(units)!=7 or len(cities)!=3 or [row[0] for row in cities]!=[1,22,23]:
        raise RuntimeError('Configured checkpoint cities or units differ')
    for player in players:
        if sum(row[0]==player[0] for row in cities)!=player[5] or sum(row[0]==player[0] for row in units)!=player[6]:
            raise RuntimeError('SDK object enumeration differs from player counts')
    techs=[[int(value) for value in row] for row in groups['T']]
    ids=sorted({row[1] for row in techs})
    if not ids or [(row[0],row[1]) for row in techs]!=[(team,tech) for team in range(64) for tech in ids] or any(row[2] not in (0,1) for row in techs):
        raise RuntimeError('SDK technology snapshot is incomplete')
    return {'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),
            'row_counts':{key:len(value) for key,value in sorted(groups.items())},
            'alive_players':alive,'sample_scope':'ALL_MAP_TERRAIN_RESOURCE_OWNER_FIELDS_PLAYER_COUNTS_GOLD_CULTURE_RESEARCH_UNITS_CITIES_TEAM_TECH_FLAGS'}


def inspect_restore(run_id):
    row=inspect_cycle(run_id,root=ROOT,save_restore=True)
    result=read_artifact(row['result']);request=read_artifact(result['request'])
    output=Path(result['stdout']['path']).read_text(encoding='utf8')
    if not request.get('save_restore_sdk_build') or not result['restore_verified'] or not result['resumed_turn_verified']:
        raise RuntimeError('SDK restore candidate identity or verification flag is missing')
    directory=Path(request['cwd']).resolve();generated={Path(item['path']).resolve():item for item in result['generated_files']}
    before=Path(one(output,'SESSION_DIRECTORY')).resolve();after=Path(one(output,'RESTORE_SESSION_DIRECTORY')).resolve()
    if before==after or any(not p.is_relative_to(directory/'sessions') for p in (before,after)):
        raise RuntimeError('Restore did not use a distinct private session')
    def recorded(path):
        path=path.resolve()
        if path not in generated:raise RuntimeError('Unrecorded runtime artifact: '+str(path))
        check_artifacts(generated[path]);return path
    for key in ('NATIVE_RESTORE_FRESH_SESSION','NATIVE_RESTORE_STATE_EQUAL','RESTORED_CORE_MODULE_UNLOADED'):
        if one(output,key)!='true':raise RuntimeError('Restore state or unload flag differs')
    if one(output,'NATIVE_RESTORE_SECTIONS_READ')!='132':raise RuntimeError('Not all SDK sections were consumed')
    phases=['verify_archive','pregame','game','map','supporting','teams','players','post_load_initialization','compare_sdk_state','idle_updates','resume_turn']
    if re.findall(r'^NATIVE_RESTORE_PHASE=(.+)$',output,re.M)!=phases or result['restore_phases']!=phases:
        raise RuntimeError('SDK restore operation sequence differs')
    snapshot_before=recorded(before/'state-before-save.txt');snapshot_after=recorded(after/'state-after-restore.txt')
    if snapshot_before.read_bytes()!=snapshot_after.read_bytes():raise RuntimeError('Actual pre-save and restored SDK state differs')
    snapshot=inspect_snapshot(snapshot_after.read_bytes())
    if int(one(output,'NATIVE_RESTORE_STATE_BYTES'))!=snapshot['bytes']:raise RuntimeError('Snapshot size log differs')
    checkpoint=recorded(Path(one(output,'NATIVE_CHECKPOINT_WRITTEN')))
    if checkpoint.parent!=before:raise RuntimeError('Checkpoint belongs to a different session')
    bundle=next(Path(item['path']) for item in request['inputs'] if Path(item['path']).name=='bundle.manifest')
    database_before=recorded(before/'Civ5SavedGameDatabase.db');database_after=recorded(after/'Civ5SavedGameDatabase.db')
    save=inspect_save(checkpoint,bundle,database_before,expected=(1,0,1,1,0,64,64,133))
    if database_before.read_bytes()!=database_after.read_bytes():raise RuntimeError('Restored embedded database differs')
    restored_checkpoint=recorded(after/'state-after-restore.zssave')
    restored_save=inspect_save(restored_checkpoint,bundle,database_after,expected=(1,0,1,1,0,64,64,133))
    changed=[f'{old["kind"]},{old["index"]}' for old,new in zip(save['sections'],restored_save['sections']) if old!=new]
    if changed!=['3,0'] or one(output,'NATIVE_RESTORE_SECTIONS_EQUAL')!='132,133' or \
       re.findall(r'^NATIVE_RESTORE_SECTION_CHANGED=(.+)$',output,re.M)!=changed:
        raise RuntimeError('Restored SDK payload changed outside the game reload metadata section')
    localization=next(Path(item['path']) for item in request['inputs'] if Path(item['path']).name=='localization.db')
    game_metadata=verify_game_restore(checkpoint,restored_checkpoint,
        rules_db_path=recorded(before/'rules.db'),localization_db_path=localization,
        language=row['language'],configuration_verified=result['configuration_verified'])
    if one(output,'NATIVE_CHECKPOINT_OBSERVATION')!=f'1,1,0,133,{save["bytes"]}':raise RuntimeError('Checkpoint metadata log differs')
    observation=[int(value) for value in one(output,'NATIVE_RESTORE_OBSERVATION').split(',')]
    if observation!=[1,1,0,40,24,960,1,1,3] or observation!=result['restore_observation']:
        raise RuntimeError('Restored SDK counters or waiting state differ')
    resumed=[int(value) for value in one(output,'RESTORED_TURN_CYCLE_OBSERVATION').split(',')]
    if len(resumed)!=8 or resumed[:6]!=[1,2,2,0,1,1] or not 1<=resumed[6]<=256 or resumed[7]!=3 or resumed!=result['restored_turn_observation']:
        raise RuntimeError('Restored SDK turn did not advance once and wait')
    for key,value in (('RESTORED_TURN_CYCLE_INPUT','MISSION_SKIP_EACH_UNIT_THEN_CONTROL_ENDTURN'),('RESTORED_TURN_CYCLE_PLAYER_OPTION','PLAYEROPTION_WAIT_END_TURN:1')):
        if one(output,key)!=value:raise RuntimeError('Restored turn bypassed the normal input sequence')
    states=re.findall(r'^RESTORED_TURN_CYCLE_STATE=(.+)$',output,re.M)
    if states!=result['restored_turn_states'] or len(states)!=resumed[6]:raise RuntimeError('Resumed SDK frame count differs')
    frames=[]
    for index,state in enumerate(states,1):
        step,values=state.split('|');frame=[int(value) for value in values.split(',')]
        if int(step)!=index or len(frame)!=5 or frame[0]!=frame[1] or frame[0] not in (1,2) or any(value not in (0,1) for value in frame[2:]):
            raise RuntimeError('Resumed SDK frame is invalid')
        frames.append(frame)
    if frames[-1]!=[2,2,1,1,1] or any(frame[0]!=1 for frame in frames[:-1]) or [1,1,0,0,0] not in frames:
        raise RuntimeError('Resumed AI completion or next human activation differs')
    events={event:int(count) for count,event in re.findall(r'^TURN_CYCLE_EVENT=(\d+)\|(.+)$',output.split('NATIVE_RESTORE_FRESH_SESSION=true')[1],re.M)}
    for event in ('local-turn-complete','local-turn-all-complete:1','local-turn-boundary:1','gameplay-turn-changed:2','new-game-turn:2','ui-active-player-turn-end','ui-active-player-turn-start'):
        if events.get(event)!=1:raise RuntimeError('Missing or duplicated restored turn event: '+event)
    if events.get('local-turn-complete-cancelled',0):raise RuntimeError('Restored SDK cancelled turn completion')
    row.update(checkpoint=save,restored_checkpoint=restored_save,byte_exact_sections=132,game_metadata=game_metadata,restored_database=artifact(database_after),
        snapshot_before=artifact(snapshot_before),snapshot_after=artifact(snapshot_after),snapshot=snapshot,
        restore_observation=observation,resumed_turn_observation=resumed,resumed_turn_frames=frames,resumed_turn_events=events,
        section_comparison=one(output,'NATIVE_RESTORE_SECTIONS_EQUAL'),
        changed_sections=re.findall(r'^NATIVE_RESTORE_SECTION_CHANGED=(.+)$',output,re.M))
    return row


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='append',required=True);args=parser.parse_args()
    if len(args.run)!=2 or len(set(args.run))!=2:parser.error('Provide two distinct EN and KO runs')
    rows=[inspect_restore(run_id) for run_id in args.run]
    if {row['language'] for row in rows}!={'en_US','ko_KR'}:raise RuntimeError('Both languages are required')
    for key in ('inputs','observation','lua_observation','first_turn_observation','turn_cycle_observation','turn_frames',
                'final_players','restore_observation','resumed_turn_observation','resumed_turn_frames','snapshot','resumed_turn_events',
                'byte_exact_sections','section_comparison','changed_sections'):
        if rows[0][key]!=rows[1][key]:raise RuntimeError('Language restore observations differ: '+key)
    frozen=ROOT/'validators'/('_'.join(args.run)+'_'+uuid.uuid4().hex[:10]);frozen.mkdir(parents=True,exist_ok=False)
    validators=[]
    for name in ('verify_native_save_restore.py','verify_restore_game_metadata.py','verify_first_turn_candidate.py','verify_turn_cycle_candidate.py','verify_new_game_candidate.py'):
        target=frozen/name;shutil.copy2(PROJECT/'tools'/name,target);validators.append(artifact(target))
    report={'status':'ISOLATED_SDK_NATIVE_SAVE_RESTORE_PAIR_PASS','validators':validators,'runs':rows,
        'sdk_restore_verified':True,'sdk_autosave_write_verified':True,'turn_execution_verified':True,
        'turns_completed_per_run':2,'fresh_session_restore_verified':True,'restored_semantic_sample_matches':True,
        'resumed_turn_execution_verified':True,'retail_save_compatibility_verified':False,
        'non_game_sections_byte_exact':True,'game_changes_match_fixture_reload_metadata_only':True,
        'complete_state_determinism_verified':False,'game_multicore_verified':False,'accepted_stage_promoted':False,
        'installed_game_launched':False,'scope':'ACTUAL_X64_NATIVE_133_SECTION_SAVE_FRESH_SESSION_RESTORE_SEMANTIC_COMPARISON_AND_RESUMED_NORMAL_TURN_EN_KO'}
    check_artifacts(report);(ROOT/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'status':report['status'],'languages':[row['language'] for row in rows],
        'snapshot':rows[0]['snapshot'],'resumed_turn':rows[0]['resumed_turn_observation']}),flush=True)


if __name__=='__main__':main()
