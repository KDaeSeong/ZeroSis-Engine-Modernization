"""Inspect actual SDK turn-entry runs and independently parse persisted native saves."""
import argparse,hashlib,json,re,sqlite3,struct
from pathlib import Path
from collect_baseline import PROJECT
from probe_world_builder import artifact
from verify_new_game_candidate import inspect,read_artifact
from verify_world_builder_map_object import check_artifacts

ROOT=PROJECT/'evidence/first_turn'


def inspect_save(path,bundle,database,expected=(1,1,0,0,0,64,64,133)):
    data=path.read_bytes()
    if len(data)<80 or data[:16]!=b'ZEROSIS_SAVE_V1\0' or hashlib.sha256(data[:-32]).digest()!=data[-32:]:
        raise RuntimeError('Persisted save header or whole-file checksum differs')
    version,flags,turn,elapsed,active,teams,players,count=struct.unpack_from('<8I',data,16)
    if (version,flags,turn,elapsed,active,teams,players,count)!=expected:
        raise RuntimeError('Actual SDK save metadata differs')
    at=48;sections=[];payloads={}
    expected=[(kind,0) for kind in range(1,6)]+[(6,i) for i in range(64)]+[(7,i) for i in range(64)]
    for expected_kind,expected_index in expected:
        if at+12>len(data)-32:raise RuntimeError('Save section header is truncated')
        kind,index,size=struct.unpack_from('<3I',data,at);at+=12
        if (kind,index)!=(expected_kind,expected_index) or not size or size>0x7fffffff or at+size>len(data)-32:
            raise RuntimeError('Save section identity/length differs')
        payload=data[at:at+size];at+=size;payloads[kind,index]=payload
        sections.append({'kind':kind,'index':index,'bytes':size,'sha256':hashlib.sha256(payload).hexdigest()})
    if at!=len(data)-32 or payloads[1,0]!=bundle.read_bytes():
        raise RuntimeError('Save trailing bytes or bundle identity differs')
    if struct.unpack_from('<3I',payloads[4,0])!=(1,40,24):
        raise RuntimeError('Saved SDK map version/dimensions differ')
    embedded=database.read_bytes();game=payloads[3,0]
    if not embedded.startswith(b'SQLite format 3\0') or len(game)<len(embedded)+4 or \
       game[-len(embedded):]!=embedded or struct.unpack_from('<I',game,len(game)-len(embedded)-4)[0]!=len(embedded):
        raise RuntimeError('SDK game section did not embed the actual private saved-game database')
    with sqlite3.connect(':memory:') as db:
        db.deserialize(embedded)
        if db.execute('PRAGMA integrity_check').fetchall()!=[('ok',)]:
            raise RuntimeError('Embedded SDK database is corrupt')
        tables=[row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {'archive':artifact(path),'bytes':len(data),'section_count':len(sections),'sections':sections,
        'embedded_database':artifact(database),'embedded_database_integrity':'ok','embedded_database_tables':tables,
        'sdk_map_dimensions':[40,24],'sdk_restore_verified':False}


def inspect_turn(run_id,root=ROOT,turn_cycle=False,save_restore=False,extra_turns=0,ui_popups=False,fixture_promotions=False):
    row=inspect(run_id,root=root,first_turn=True,turn_cycle=turn_cycle,save_restore=save_restore,extra_turns=extra_turns,
                ui_popups=ui_popups,fixture_promotions=fixture_promotions)
    result=read_artifact(row['result']);request=read_artifact(result['request'])
    output=Path(result['stdout']['path']).read_text(encoding='utf-8')
    states=re.findall(r'^FIRST_TURN_STATE=(.+)$',output,re.M)
    expected=['before-start|0,0,0,1,1','after-startup|0,0,0,1,1','waiting-for-input|0,0,0,1,1']
    if states!=expected or result['first_turn_states']!=expected or not result['turn_entry_verified'] or \
       result['first_turn_observation']!=[0,0,0,1,1,3] or output.splitlines().count('FIRST_TURN_SIGNALS=1,1,0,3')!=1:
        raise RuntimeError('First-turn waiting state or actual SDK signals differ')
    files={Path(item['path']).name:Path(item['path']) for item in request['inputs']}
    paths=re.findall(r'^NATIVE_SAVE_WRITTEN=(.+)$',output,re.M)
    if len(paths)!=1:raise RuntimeError('Expected exactly one actual SDK initial autosave')
    path=Path(paths[0]);directory=Path(request['cwd']).resolve()
    if not path.resolve().is_relative_to(directory/'sessions'):
        raise RuntimeError('Save escaped the private test session')
    generated={Path(item['path']).resolve():item for item in result['generated_files']}
    database=path.parent/'Civ5SavedGameDatabase.db'
    if path.resolve() not in generated or database.resolve() not in generated:
        raise RuntimeError('Save and embedded database lack recorded execution artifacts')
    saved=inspect_save(path,files['bundle.manifest'],database)
    marker=f'NATIVE_SAVE_OBSERVATION=0,0,0,133,{saved["bytes"]}'
    if output.splitlines().count(marker)!=1:raise RuntimeError('Actual save log differs from the persisted archive')
    row.update(first_turn_observation=result['first_turn_observation'],first_turn_states=states,autosave=saved)
    return row


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='append',required=True);args=parser.parse_args()
    if len(args.run)!=2 or len(set(args.run))!=2:parser.error('Provide distinct en_US and ko_KR first-turn runs')
    rows=[inspect_turn(run_id) for run_id in args.run]
    if {row['language'] for row in rows}!={'en_US','ko_KR'}:raise RuntimeError('Both languages are required')
    for key in ('inputs','observation','lua_observation','first_turn_observation','first_turn_states','host_service_events'):
        if rows[0][key]!=rows[1][key]:raise RuntimeError('Language observations differ: '+key)
    report={'status':'ISOLATED_FIRST_TURN_AND_AUTOSAVE_PAIR_PASS','validator':artifact(Path(__file__).resolve()),
        'new_game_validator':artifact(PROJECT/'tools/verify_new_game_candidate.py'),'runs':rows,
        'new_game_candidate_verified':True,'turn_entry_verified':True,'sdk_autosave_write_verified':True,
        'sdk_restore_verified':False,'complete_state_determinism_verified':False,'turn_execution_verified':False,
        'game_multicore_verified':False,'accepted_stage_promoted':False,'installed_game_launched':False,
        'scope':'ACTUAL_X64_INITIAL_HUMAN_WAIT_THREE_UPDATES_AND_FULL_SDK_SECTION_AUTOSAVE_WRITE'}
    check_artifacts(report)
    (ROOT/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'languages':[row['language'] for row in rows],
        'observation':rows[0]['first_turn_observation'],'save_bytes':[row['autosave']['bytes'] for row in rows]}))


if __name__=='__main__':main()
