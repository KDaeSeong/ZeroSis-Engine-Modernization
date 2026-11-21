"""Production Lua component and source integration checks; never launch Host/SDK.

Only the existing shared Lua 5.1 provider is loaded. Native GameCore, CLR, HWND,
GPU, game installation writes, MODS and user saves are outside this test.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
from economic_overview_scene import execute_lua
from prepare_ui_popup_assets import lua_value

HARNESS = r'''
local source=@@SOURCE@@
local chunk=assert(loadstring(source,'@UiMenuLifecycle.lua'))
local module=chunk()
local checks=0
local function check(value,message) assert(value,message);checks=checks+1 end
local function reject(fn,message) check(not pcall(fn),message) end
local function control()
 local c={hidden=false,disabled=false}
 function c:SetHide(v) self.hidden=v end
 function c:SetDisabled(v) self.disabled=v end
 function c:SetTexture(v) self.texture=v end
 function c:UnloadTexture() self.texture=nil end
 function c:RegisterCallback(kind,fn) assert(kind=='click');self.callback=fn end
 return c
end
local function environment()
 local e={Controls={},ContextPtr={hidden=true},UIManager={},Mouse={eLClick='click'}}
 for _,id in ipairs({'Civ5Logo','SinglePlayerButton','OptionsButton','ExitButton','MultiplayerButton',
  'ModsButton','OtherButton','ExpansionRulesSwitch','MainMenuButton','RankingButton','ReplayButton',
  'DemographicsButton','BackButton'}) do e.Controls[id]=control() end
 function e.ContextPtr:IsHidden() return self.hidden end
 function e.ContextPtr:SetShowHideHandler(fn) self.show=fn end
 e.PreGame={LoadPreGameSettings=function() error('User settings must not be loaded') end}
 e.Modding={ActivateDLC=function() error('Installed DLC must not be activated') end}
 return e
end
local e=environment();local requests={};local cursor=-1
local front=module.InstallFrontEnd(e,{
 singlePlayer=function() requests[#requests+1]='single' end,
 options=function() requests[#requests+1]='options' end,
 exitConfirm=function() requests[#requests+1]='confirm' end,
 cursor=function(v) cursor=v end})
reject(function() e.Controls.SinglePlayerButton.callback() end,'Hidden front end accepted input')
e.ContextPtr.hidden=false;front.Show(false,false)
check(front.IsVisible() and cursor==0 and e.Controls.Civ5Logo.texture=='CivilzationV_Logo.dds','Front end did not show its real logo/cursor')
for _,id in ipairs({'MultiplayerButton','ModsButton','OtherButton','ExpansionRulesSwitch'}) do
 check(e.Controls[id].hidden,'Unsupported main menu button remained active: '..id)
end
e.Controls.SinglePlayerButton.callback();e.Controls.OptionsButton.callback();e.Controls.ExitButton.callback()
check(table.concat(requests,',')=='single,options,confirm','Front-end routes were lost or performed process exit')
front.Show(true,false);e.ContextPtr.hidden=true
check(not front.IsVisible() and e.Controls.Civ5Logo.texture==nil,'Hidden front end retained logo state')
reject(function() e.Controls.ExitButton.callback() end,'Hidden front end accepted exit')

local identity={owner=0,turn=8,generation=19}
local function menu(accept)
 local env={Game={},ControlTypes={CONTROL_RESTART_GAME=1,CONTROL_RETIRE=2}}
 local out={}
 local installed=module.InstallGameMenu(env,{identity=function() return identity end,
  request=function(action,owner,turn,generation)
   out[#out+1]={action,owner,turn,generation};return accept
  end},identity)
 return env,installed,out
end
local game,installed,out=menu(true)
check(game.Game.DoControl(1)==true and installed.Submitted(),'Restart request was not submitted')
check(out[1][1]=='Restart' and out[1][4]==19,'Restart lost action or generation')
reject(function() game.Game.DoControl(2) end,'Duplicate lifecycle request was accepted')
game,installed,out=menu(false)
check(game.Game.DoControl(2)==false and not installed.Submitted(),'Rejected retirement consumed menu ownership')
check(game.Game.DoControl(2)==false and #out==2,'Rejected command could not be retried')
game,installed,out=menu(true);identity.turn=9
reject(function() game.Game.DoControl(1) end,'Stale-turn restart was accepted')
identity.turn=8;identity.generation=20
reject(function() installed.ConfirmedMainMenu() end,'Stale-generation main-menu command was accepted')
identity.generation=19
game,installed,out=menu(true)
check(installed.ConfirmedMainMenu() and out[1][1]=='MainMenu','Confirmed main menu lost its distinct destination')
game,installed=menu(true)
reject(function() game.Game.DoControl(3) end,'Unexpected gameplay control crossed menu boundary')

e=environment();local stockShow=0;local stockClose=0;local ended;local childCalls=0;local mainCalls=0
e.OnDisplay=function(kind,team)
 check(kind==nil and team==-1,'Retirement fabricated a victory enum or winning team')
 stockShow=stockShow+1;e.ContextPtr.hidden=false
end
e.OnMainMenu=function() stockClose=stockClose+1;e.ContextPtr.hidden=true;return ended.ConfirmedMainMenu() end
local packet={owner=0,turn=8,generation=19,finalScore=137,localVictoryRecorded=true,replayPath='owned/retired.Civ5Replay'}
ended=module.InstallEndGame(e,{
 mainMenu=function(owner,turn,generation)
  check(e.ContextPtr.hidden,'End-game transition preceded original close')
  check(owner==0 and turn==8 and generation==19,'End-game identity changed');mainCalls=mainCalls+1;return true
 end,
 ranking=function(id,score) check(score==137,'Wrong SDK final score');id.generation=900;childCalls=childCalls+1 end,
 replay=function(id,path) check(id.generation==19 and path=='owned/retired.Civ5Replay','Child mutated replay identity');childCalls=childCalls+1 end,
 demographics=function(id) check(id.generation==19,'Child mutated demographics identity');childCalls=childCalls+1 end},packet)
packet.finalScore=-1000;packet.replayPath='wrong'
ended.Show()
check(stockShow==1 and e.Controls.BackButton.hidden and e.Controls.BackButton.disabled,'Retired game exposed continue')
check(e.OnBack()==false,'Retired game accepted extended play')
e.Controls.RankingButton.callback();e.Controls.ReplayButton.callback();e.Controls.DemographicsButton.callback()
check(childCalls==3,'Completed end-game children did not route')
e.Controls.MainMenuButton.callback()
check(stockClose==1 and mainCalls==1 and ended.Submitted(),'End-game did not leave via original close and distinct menu event')
reject(function() ended.ConfirmedMainMenu() end,'Duplicate end-game event was accepted')
reject(function() e.Controls.ReplayButton.callback() end,'Closed end game accepted a child request')
return '{"status":"PASS_PRODUCTION_MENU_LIFECYCLE_LUA_COMPONENT","checks":'..checks..
 ',"host_executed":false,"sdk_loaded":false,"hwnd_created":false,"gpu_executed":false}'
'''

def seal(path: Path) -> dict:
    data=path.read_bytes()
    return {"path":str(path),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}

def verify() -> dict:
    source=PROJECT/"Source/Presentation/UiMenuLifecycle.lua"
    before=seal(source)
    component=execute_lua(HARNESS.replace("@@SOURCE@@",lua_value(source.read_text(encoding="utf8"))))
    if seal(source)!=before:
        raise AssertionError("Production Lua changed during the component test")
    paths={name:PROJECT/"Source/Host"/name for name in (
        "MenuLifecycleSetup.h","MenuLifecycleRetirement.h","MenuLifecycleWindow.h","MenuLifecycle.h",
        "InteractiveGameSession.h","InteractiveGameLoop.h","HostServices.h","HostRun.h","HostMain.cpp")}
    text={name:path.read_text(encoding="utf-8-sig") for name,path in paths.items()}
    setup=text["MenuLifecycleSetup.h"];retire=text["MenuLifecycleRetirement.h"]
    session=text["InteractiveGameSession.h"];loop=text["InteractiveGameLoop.h"];main=text["HostMain.cpp"]
    checks={
        "restart_uses_actual_serialized_pregame": "pregame->read(input,true)" in setup and "WritePregame(*pregame)!=pregame_" in setup,
        "restart_supplements_unserialized_dlc_and_presentation_fields": all(x in setup for x in ("GetDLCAllowed()","GetDLCAvailable(player)","setCivilizationKeyPackageID","setLeaderKeyPackageID","setQuickMovement(quickMovement_)","setPersistSettings(persist_)")),
        "restart_rejects_bundle_change_and_existing_game": "bundle!=bundle_" in setup and "game->IsFinalInitialized() || map->NumPlots()!=0" in setup,
        "restart_does_not_read_fixed_profile": "NewGameConfig" not in setup and "CIVILIZATION_AMERICA" not in setup and "0x5A17C0DE" not in setup,
        "restart_reuses_initial_seeds": "pregame->mapRandomSeed()!=mapSeed_" in setup and "pregame->syncRandomSeed()!=syncSeed_" in setup,
        "retirement_exports_genuine_sdk_replay": "game.WriteReplay(stream)" in retire and "NativeSaveTransaction output(path)" in retire,
        "retirement_does_not_put_raw_replay_in_save_envelope": "NativeSaveArchive::WriteAtomic(path,bytes);" not in retire,
        "retirement_readback_and_score_are_actual": "actual!=bytes" in retire and "player->GetScore(true," in retire and "score!=actual" in retire,
        "retirement_platform_unavailability_explicit": "platformLeaderboardAvailable=false" in retire and re.search(r"bool RecordLeaderboardScore\(int score\).*?return false;",retire,re.S) is not None,
        "retirement_packet_waits_for_callback_unwind": "host_.scripts->IsQuiescent()" in retire and "MenuLifecycleEndGame Take()" in retire,
        "original_sdk_controls_reached": all(x in session for x in ("Game.DoControl(ControlTypes.CONTROL_RESTART_GAME)","Game.DoControl(ControlTypes.CONTROL_RETIRE)","restartObserved_")),
        "transition_stops_input_before_tick": loop.index("if(live.HasPendingLifecycle())")<loop.index("if(loadHandoff.HasTransition() || menuExitRequested)return;")<loop.index("if(live.Tick())redraw=true;"),
        "old_core_unloaded_before_front_end": main.index("run->Shutdown();RequireGameCoreAbsent();")<main.index("run->FrontEnd(setup,endGame)"),
        "front_end_is_actual_owned_loop": "while(true)" in text["MenuLifecycleWindow.h"] and "CreateGpuScene" in text["MenuLifecycleWindow.h"] and "PumpMessages" in text["MenuLifecycleWindow.h"],
        "front_end_does_not_execute_gamecore": "InitializeCore" not in text["MenuLifecycleWindow.h"] and "WithCore" not in text["MenuLifecycleWindow.h"],
        "host_overrides_bound_sdk_lifecycle_services": all(x in text["HostServices.h"] for x in ("bool saveReplay() override","void RestartGame() override","void OpenEndGameMenu() override","return state_->recordVictoryInformation(score)")),
    }
    failed=[key for key,value in checks.items() if not value]
    if failed:raise AssertionError("Source-only lifecycle checks failed: "+repr(failed))
    return {"schema":"zerosis.menu_lifecycle.offline.v1","status":"PASS_COMPONENT_AND_SOURCE_ONLY_NATIVE_ACCEPTANCE_DEFERRED",
            "lua_component":component,"source_only_checks":checks,"sources":[before,*map(seal,paths.values())],
            "native_execution":False,"native_window_acceptance":False,"sdk_retirement_or_restart_executed":False,
            "unfinished":["Retail pixel/input acceptance of original-atlas front-end and replay candidates","All retail front-end branches","End-game demographics UI","Front-end Options and Load routes","Native input/render/restart/retirement acceptance"]}

if __name__=="__main__":
    result=verify()
    destination=PROJECT/"evidence/game_menu/original_menu_followup/frontend/lifecycle_regression.json"
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n",encoding="utf8")
    print(json.dumps({"status":result["status"],"lua_checks":result["lua_component"]["checks"],"source_checks":len(result["source_only_checks"]),"report":str(destination)}))
