"""Verify the actual SDK single-player turn boundary in two language runs."""
import argparse,json,re
from pathlib import Path
from collect_baseline import PROJECT
from probe_world_builder import artifact
from verify_first_turn_candidate import inspect_turn,read_artifact
from verify_world_builder_map_object import check_artifacts

ROOT=PROJECT/'evidence/turn_cycle'


def inspect_cycle(run_id,root=ROOT,save_restore=False,extra_turns=0,ui_popups=False):
    row=inspect_turn(run_id,root=root,turn_cycle=True,save_restore=save_restore,extra_turns=extra_turns,ui_popups=ui_popups)
    result=read_artifact(row['result']);request=read_artifact(result['request'])
    output=Path(result['stdout']['path']).read_text(encoding='utf-8')
    values=re.findall(r'^TURN_CYCLE_OBSERVATION=([-\d,]+)$',output,re.M)
    observed=[int(value) for value in values[0].split(',')] if len(values)==1 else []
    if len(observed)!=8 or observed[:6]!=[0,1,1,0,1,1] or not 1<=observed[6]<=256 or observed[7]!=3 \
       or result['turn_cycle_observation']!=observed or result['turn_cycle_verified'] is not True:
        raise RuntimeError('SDK turn-cycle observation is incomplete')
    for marker in ('TURN_CYCLE_INPUT=MISSION_SKIP_EACH_UNIT_THEN_CONTROL_ENDTURN',
                   'TURN_CYCLE_PLAYER_OPTION=PLAYEROPTION_WAIT_END_TURN:1'):
        if output.splitlines().count(marker)!=1:raise RuntimeError('Expected one ordinary SDK input sequence')
    states=re.findall(r'^TURN_CYCLE_STATE=(.+)$',output,re.M)
    if states!=result['turn_cycle_states'] or len(states)!=observed[6]:raise RuntimeError('SDK update count differs')
    frames=[]
    for index,state in enumerate(states,1):
        step,frame=state.split('|');frame=[int(item) for item in frame.split(',')]
        if int(step)!=index or len(frame)!=5 or any(value not in (0,1) for value in frame) or frame[0]!=frame[1]:
            raise RuntimeError('Unexpected SDK frame or turn/elapsed counters')
        frames.append(frame)
    if frames[-1]!=[1,1,1,1,1] or any(frame[0]!=0 for frame in frames[:-1]) or [0,0,0,0,0] not in frames:
        raise RuntimeError('AI processing did not end before the next human turn')
    events=[{'count':int(count),'event':event} for count,event in re.findall(r'^TURN_CYCLE_EVENT=(\d+)\|(.+)$',output,re.M)]
    if events!=result['turn_cycle_events']:raise RuntimeError('Turn event report differs from stdout')
    if save_restore:
        events=[{'count':int(count),'event':event} for count,event in re.findall(r'^TURN_CYCLE_EVENT=(\d+)\|(.+)$',output.split('NATIVE_RESTORE_FRESH_SESSION=true')[0],re.M)]
    # Trace emits a pre-input snapshot followed by the complete final snapshot.
    final={item['event']:item['count'] for item in events}
    expected={'local-turn-complete':1,'local-turn-all-complete:0':1,'local-turn-boundary:0':1,
              'gameplay-turn-changed:1':1,'new-game-turn:1':1,'ui-active-player-turn-end':1,
              'ui-active-player-turn-start':2,'local-ai-civs-processed':2,'local-player-initial-ai-processed':2,
              'local-turn-reminders-flush:0':observed[6]+6}
    for player in (0,1,22,23,63):
        expected[f'ui-player-turn-status:0:{player}:']=2 if player==0 else 1
        expected[f'ui-player-turn-status:1:{player}:']=1
    if any(final.get(key)!=value for key,value in expected.items()) or final.get('local-turn-complete-cancelled',0):
        raise RuntimeError('Missing, duplicated or cancelled SDK turn boundary events')
    players=[[int(item) for item in line.split(',')] for line in re.findall(r'^TURN_CYCLE_PLAYER=([-\d,]+)$',output,re.M)]
    if players!=[[0,1,1,0,2],[1,0,0,1,1],[22,0,0,1,0],[23,0,0,1,0],[63,0,0,0,4]]:
        raise RuntimeError('Configured scenario did not produce the expected real AI cities and units')
    materializations=request.get('input_materializations',[])
    if len(materializations)!=10:raise RuntimeError('Runtime input materialization evidence is incomplete')
    for item in materializations:
        if item['materialization_method']=='hardlink':
            target=Path(item['target']);cache=Path(item['cache'])
            if not target.samefile(cache):raise RuntimeError('Runtime hardlink no longer refers to the verified immutable cache')
    row.update(turn_cycle_observation=observed,turn_frames=frames,turn_events=events,final_players=players,
               runtime_input_materializations=materializations)
    return row


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--run',action='append',required=True);args=parser.parse_args()
    if len(args.run)!=2 or len(set(args.run))!=2:parser.error('Provide distinct en_US and ko_KR runs')
    rows=[inspect_cycle(run_id) for run_id in args.run]
    if {row['language'] for row in rows}!={'en_US','ko_KR'}:raise RuntimeError('Both languages are required')
    for key in ('inputs','observation','lua_observation','first_turn_observation','first_turn_states',
                'host_service_events','turn_cycle_observation','turn_frames','turn_events','final_players'):
        if rows[0][key]!=rows[1][key]:raise RuntimeError('Language run observations differ: '+key)
    report={'status':'ISOLATED_SDK_TURN_CYCLE_PAIR_PASS','validator':artifact(Path(__file__).resolve()),
        'supporting_validators':[artifact(PROJECT/'tools'/name) for name in ('verify_first_turn_candidate.py','verify_new_game_candidate.py')],
        'runs':rows,'new_game_candidate_verified':True,'turn_entry_verified':True,'sdk_autosave_write_verified':True,
        'turn_execution_verified':True,'turns_completed_per_run':1,'ai_cities_founded_per_run':3,
        'sdk_restore_verified':False,'complete_state_determinism_verified':False,'game_multicore_verified':False,
        'accepted_stage_promoted':False,'installed_game_launched':False,
        'scope':'ACTUAL_X64_SDK_UNIT_SKIP_NORMAL_END_TURN_AI_COMPLETION_AND_NEXT_HUMAN_WAIT_IN_TWO_LANGUAGES'}
    check_artifacts(report)
    (ROOT/'conformance.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'languages':[row['language'] for row in rows],
        'turn_cycle_observation':rows[0]['turn_cycle_observation'],'final_players':rows[0]['final_players']}))


if __name__=='__main__':main()
