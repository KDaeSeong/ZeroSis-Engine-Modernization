"""Original GameMenu/SaveMenu routing fixtures with the new private map bridge.

The existing asset/DB fixture loaders are reused. Only their old expectations
for intentionally unconnected menu actions are replaced in memory. Production
Lua and all installed original scripts remain exact, read-only inputs.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(PROJECT/'tools'),str(PROJECT/'Tests')]
import game_menu_scene as game
import save_menu_scene as save
from menu_options_map_scene import fixture_script as map_fixture
from economic_overview_scene import execute_lua
from ui_pixel_scene import game_menu_contract,save_menu_contract,private_menu_contract


def replace_once(text,old,new):
    if text.count(old)!=1:raise RuntimeError('Legacy fixture anchor changed: '+old[:80])
    return text.replace(old,new,1)


def game_program():
    text=game.HARNESS
    anchor=" if op=='gameMenuUnavailable' then"
    extra=""" if op=='menuOptionsOpen' or op=='touchHelpOpen' or op=='mapMenuOpen' or
    op=='gameMenuMainMenu' or op=='gameMenuRestart' or op=='gameMenuRetire' then
  check(select('#',...)==0,'New menu route accepted extra arguments')
  local kind,action
  if op=='menuOptionsOpen' then kind,action='OpenMenuOptions','OptionsMenu_InGame'
  elseif op=='touchHelpOpen' then kind,action='OpenTouchHelp','TouchControlsMenu'
  elseif op=='mapMenuOpen' then kind,action='OpenMapMenu','SaveMapMenu'
  elseif op=='gameMenuMainMenu' then
   check(timerBalance==0 and cursor==1,'Main menu request preceded original OnLeave/cursor');kind,action='MainMenu','ExitToMainMenu'
  elseif op=='gameMenuRestart' then check(timerBalance==1,'Restart lost parent timer');kind,action='Restart','Restart'
  else check(timerBalance==1,'Retire request preceded its original OnReturn');kind,action='Retire','Retire' end
  requests[#requests+1]={kind=kind,action=action};return
 end
"""
    text=replace_once(text,anchor,extra+anchor)
    text=replace_once(text,"r.kind=='Unavailable' and r.action==action",
        "(r.kind=='Unavailable' or r.kind==({OptionsMenu_InGame='OpenMenuOptions',TouchControlsMenu='OpenTouchHelp',SaveMapMenu='OpenMapMenu',Restart='Restart',Retire='Retire',ExitToMainMenu='MainMenu'})[action]) and r.action==action")
    marker="click('RestartGameButton');latest('Restart')"
    if text.count(marker)!=1:raise RuntimeError('Original GameMenu transition fixture changed')
    text=text.split(marker)[0]+r'''
for id,action in pairs({OptionsMenu_InGame='OptionsMenu_InGame',TouchControlsMenu='TouchControlsMenu',SaveMapMenu='SaveMapMenu'}) do
 env.Controls[id]:SetHide(false);latest(action)
 check(env.ZeroSisUi.IsActive() and timerBalance==1 and node(snap().tree,id).hidden,'SetHide entry changed parent/declaration lifetime')
 env.UIManager:QueuePopup(env.Controls[id],env.PopupPriority[({OptionsMenu_InGame='OptionsMenu',TouchControlsMenu='TouchControlsMenu',SaveMapMenu='SaveMapMenu'})[id]])
 latest(action);check(env.ZeroSisUi.IsActive() and timerBalance==1,'QueuePopup entry changed parent lifetime')
end
click('RestartGameButton');latest('Restart')
check(env.ZeroSisUi.IsActive() and timerBalance==1,'Restart request closed the original parent before handoff')
env.ZeroSisUi.CloseGameMenu()
open();click('RetireButton');latest('Retire')
check(not env.ZeroSisUi.IsActive() and timerBalance==0,'Retire lost original OnReturn after its request')
open();click('MainMenuButton');local confirmation=snap()
click('Yes');latest('ExitToMainMenu')
check(timerBalance==0 and env.ZeroSisUi.IsActive() and cursor==1,'Confirmed main-menu request failed original timer/cursor boundary')
env.ZeroSisUi.CloseGameMenu();env.ZeroSisUiNative('gameMenuCursor',0)
local closed=snap()
check(not closed.active and timerBalance==0 and mutations==0,'Transition fixture changed gameplay or retained a timer')
return json({status='PASS_SOURCE_BOUND_GAME_MENU_TRANSITIONS',checks=checks,timerEvents=timerEvents,
 cursorEvents=cursorEvents,requests=requests,gameplayMutations=mutations,
 retainedSnapshotJson=json(retained),animationSnapshotJson=json(animation),detailsSnapshotJson=json(details),
 closedSnapshotJson=json(closed),noticeSnapshotJson=json(notice),restoredNoticeSnapshotJson=json(restoredNotice),
 confirmationSnapshotJson=json(confirmation),detailsNoticeSnapshotJson=json(detailsNotice)})
'''
    return text


def save_program():
    return save.HARNESS


def main():
    before={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in
        (PROJECT/'Source/Host/UiScene.lua',PROJECT/'Source/Presentation/UiPresentationInput.lua')}
    original_game,original_save=game.HARNESS,save.HARNESS
    try:
        game.HARNESS=game_program();parent=game.verify_component(include_snapshot=True)
        save.HARNESS=save_program();child=save.verify_component(include_snapshot=True)
    finally:game.HARNESS,save.HARNESS=original_game,original_save
    game_proof=game_menu_contract(parent['retained_snapshot'])
    save_proof=save_menu_contract(child['opened_snapshot'])
    if not save_proof['map_source_apis_bound'] or child['nestedMapRequests']!=1:
        raise AssertionError('New original SaveMenu map bridge was not exercised')
    bad=deepcopy(child['opened_snapshot']);bad['saveMenu']['mapMenuSourceBound']=False
    try:save_menu_contract(bad)
    except ValueError:pass
    else:raise AssertionError('Legacy source profile admitted the new map callback')
    legacy=deepcopy(child['opened_snapshot']);legacy['saveMenu']['mapMenuSourceBound']=False
    legacy['saveMenu']['unsupportedActions'].append('saveMap')
    def hide_legacy_map(node):
        if node.get('id')=='SaveMapButton':node['hidden']=node['disabled']=True;return node['key']
        for value in node['children']:
            result=hide_legacy_map(value)
            if result:return result
    map_key=hide_legacy_map(legacy['tree'])
    legacy['inputTargets']=[row for row in legacy['inputTargets'] if row['key']!=map_key]
    if save_menu_contract(legacy)['map_source_apis_bound'] is not False:
        raise AssertionError('Legacy hidden/unconnected map profile lost compatibility')
    script,_,_,_=map_fixture()
    nested=execute_lua("_RETURN_MENU_SNAPSHOTS=true;_FIXTURE_MAP_PARENT='SaveMenu'\n"+script)
    map_proof=private_menu_contract(nested['map'],context='map-menu')
    if map_proof['parent_context']!='SaveMenu':raise AssertionError('Nested map metadata lost its original immediate parent')
    if not (parent['retained_snapshot']['gameMenu']['owner']==child['opened_snapshot']['saveMenu']['owner']==map_proof['owner'] and
            parent['retained_snapshot']['gameMenu']['turn']==child['opened_snapshot']['saveMenu']['turn']==map_proof['turn']):
        raise AssertionError('Cross-context source player/turn binding differs')
    kinds={request['kind'] for request in parent['requests']}
    if not {'OpenSaveMenu','OpenMapMenu','OpenMenuOptions','OpenTouchHelp','MainMenu','Restart','Retire'}<=kinds:
        raise AssertionError('A new GameMenu route was not covered by its original callback')
    if before!={path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in before}:
        raise AssertionError('Shared production source changed during cross-context fixtures')
    evidence=PROJECT/'evidence/game_menu/offline_menu_suite/options_touch'
    report=dict(schema='zerosis.menu_lifecycle.source_cross_context.v1',status='PASS',
        game_checks=parent['checks'],save_checks=child['checks'],nested_map_requests=child['nestedMapRequests'],
        source_context_chain=['GameMenu','SaveMenu','SaveMapMenu'],owner=map_proof['owner'],turn=map_proof['turn'],
        timer_chain=[parent['retained_snapshot']['timerSemaphore'],child['opened_snapshot']['timerSemaphore'],nested['map']['timerSemaphore']],
        game_request_kinds=sorted(kinds),source_sha256=before,gameplay_mutations=parent['gameplayMutations'],
        native_router_executed=False,host_executed=False,sdk_executed=False,images_rendered=False)
    (evidence/'lifecycle_source_tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('status','game_checks','save_checks','nested_map_requests','timer_chain')}))


if __name__=='__main__':main()
