"""Retained XML/input + actual adapter/original touch Lua in shared pure Lua 5.1.

Explicit integer/backend fixtures stand in for native menu settings. No Host,
GameCore, HWND, GPU, retail settings or user save data is opened or executed.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from menu_options_assets import (SOURCE_IDENTITIES, GAME, original_sources,
    freeze_menu_sources, menu_options_control_tree, menu_checkbox_defaults)
from prepare_ui_popup_assets import production_font_metrics, production_style_defaults, lua_value
from economic_overview_scene import execute_lua

HARNESS=r'''
local sources,layouts=@@SOURCES@@,@@LAYOUTS@@
local checks=0
local function check(value,message) checks=checks+1;assert(value,message) end
local arrayTypes={}
local function copy(v) local t={};for k,item in pairs(v) do t[k]=item end;return t end
local function json(value)
 local t=type(value)
 if t=='nil' then return 'null' end
 if t=='boolean' or t=='number' then return tostring(value) end
 if t=='string' then return '"'..value:gsub('[%z\1-\31\\"]',function(ch)
  if ch=='"' then return '\\"' elseif ch=='\\' then return '\\\\' end
  return string.format('\\u%04x',string.byte(ch)) end)..'"' end
 assert(t=='table');local parts={}
 if arrayTypes[getmetatable(value)] or #value>0 then for _,v in ipairs(value) do parts[#parts+1]=json(v) end;return '['..table.concat(parts,',')..']' end
 local keys={};for k in pairs(value) do keys[#keys+1]=k end;table.sort(keys)
 for _,k in ipairs(keys) do parts[#parts+1]=json(k)..':'..json(value[k]) end
 return '{'..table.concat(parts,',')..'}'
end
local committed={noBasicHelp=0,hideTouchHelp=0,uiCueVolumePercent=100,
 windowWidth=1280,windowHeight=720,fullscreen=0,vsync=1,policyInfo=0,noRewardPopups=0}
local cached,open,persistence,applies,fail=copy(committed),false,0,0,false
local operations={}
local capabilityOverrides={}
local function initialize(kind)
 local env=setmetatable({ZeroSisUiLayout=layouts[kind],Game={Rand=function() return 0 end,
  GetActivePlayer=function() return 0 end,GetGameTurn=function() return 1 end}}, {__index=_G});env._G=env
 env.ZeroSisUiNative=function(op,...)
  operations[op]=(operations[op] or 0)+1
  if op=='uiFrameTime' then return 0 end
  if op=='screenSize' then return 1920,1080 end
  if op=='randomSeed' then return 17 end
  if op=='locale' then return 'Option' end
  if op=='localeLength' then return #(...) end
  if op=='localeSubstring' then local s,a,n=...;return s:sub(a,a+n-1) end
  if op=='snapshotJson' then local value,marker=...;arrayTypes[marker]=true;return value end
  if op=='menuOptionsCapability' then return capabilityOverrides[(...)]~=false end
  if op=='menuOptionsBegin' then check(not open,'Nested fixture options');cached=copy(committed);open=true;return end
  if op=='menuOptionsGet' then local key,isCached=...;if isCached then check(open,'Inactive cache read') end;return (isCached and cached or committed)[key] end
  if op=='menuOptionsSet' then local key,value=...;check(open and cached[key]~=nil and value==math.floor(value),'Malformed fixture edit');cached[key]=value;return end
  if op=='menuOptionsDefaults' then cached={noBasicHelp=0,hideTouchHelp=0,uiCueVolumePercent=100,windowWidth=1280,windowHeight=720,fullscreen=0,vsync=1,policyInfo=0,noRewardPopups=0};return end
  if op=='menuOptionsCancel' then check(open,'Cancel without transaction');cached=copy(committed);open=false;return end
  if op=='menuOptionsApply' then
   check(open,'Apply without transaction');applies=applies+1
   if fail then return false,'fixture apply failure; rollback verified' end
   committed=copy(cached);open=false;persistence=persistence+1;return true,''
  end
  if op=='touchHelpGet' then return committed.hideTouchHelp~=0 end
  if op=='touchHelpCache' then local value=...;check(type(value)=='boolean','Malformed touch flag');cached=copy(committed);cached.hideTouchHelp=value and 1 or 0;return end
  if op=='touchHelpCommit' then
   if fail then cached=copy(committed);return false,'fixture store failure' end
   committed=copy(cached);persistence=persistence+1;return true,''
  end
  error('Unmodeled native operation '..op)
 end
 local fn=assert(loadstring(sources.scene,'@UiScene+input+menu-options'));setfenv(fn,env);fn()
 if kind=='touch' then
  local original=assert(loadstring(sources.touch,'@original-TouchControlsMenu.lua'));setfenv(original,env);original()
 end
 return env
end
local function click(env,id)
 for _,target in ipairs(env.ZeroSisUi.GetInputTargets()) do
  if target.id==id and target.event=='LeftClick' then
   check(env.ZeroSisUi.DispatchLeftClick(target.key)==true,'Retained click rejected '..id);return target.key
  end
 end
 error('Missing visible retained click target '..id)
end
local env=initialize('options')
check(not env.ZeroSisUi.IsActive(),'Options initially active')
env.ZeroSisUi.OpenMenuOptions()
local hiddenKey
for _,target in ipairs(env.ZeroSisUi.GetInputTargets()) do
 check(target.id~='SPQuickMovementCheckBox' and target.id~='VideoPanelBlock','Unsupported option gained input')
end
click(env,'NoRewardPopupsCheckbox')
check(committed.noRewardPopups==0 and cached.noRewardPopups==1,'Reward checkbox applied before Save')
local old=click(env,'NoBasicHelpCheckbox')
check(committed.noBasicHelp==0 and cached.noBasicHelp==1,'Checkbox applied before Save')
click(env,'CancelButton')
check(committed.noBasicHelp==0 and committed.noRewardPopups==0 and persistence==0 and not env.ZeroSisUi.IsActive(),'Cancel failed to discard')
check(env.ZeroSisUi.DispatchLeftClick(old)==false,'Closed stale input was accepted')
env.ZeroSisUi.OpenMenuOptions();click(env,'VideoButton')
click(env,'ApplyResButton');click(env,'FullscreenCheck');click(env,'VSyncCheck')
check(cached.windowWidth==1280 and cached.windowHeight==800 and cached.fullscreen==1 and cached.vsync==0,'Video cache did not edit')
click(env,'AudioButton')
local slider=env.ZeroSisUi.GetInputTargets('SliderValue')[1]
check(slider and slider.id=='EffectsVolumeSlider','Original effects slider is not connected')
check(env.ZeroSisUi.DispatchSliderValue(slider.key,0.9),'Original effects slider input was rejected')
check(cached.uiCueVolumePercent==90 and committed.uiCueVolumePercent==100,'Volume was previewed before commit')
fail=true;click(env,'AcceptButton')
check(env.ZeroSisUi.IsActive() and committed.uiCueVolumePercent==100 and persistence==0,'Failed apply closed or persisted')
fail=false;click(env,'AcceptButton')
check(not env.ZeroSisUi.IsActive() and committed.uiCueVolumePercent==90 and persistence==1,'Successful apply did not persist then close')
env.ZeroSisUi.OpenMenuOptions();click(env,'DefaultButton');click(env,'CancelButton')
check(committed.uiCueVolumePercent==90 and persistence==1,'Cancelled defaults persisted')
env.ZeroSisUi.OpenMenuOptions();check(env.ZeroSisUi.DispatchKeyDown(27),'Options Escape rejected')
check(not env.ZeroSisUi.IsActive() and not open,'Options Escape did not cancel')
local touch=initialize('touch');touch.ZeroSisUi.OpenTouchHelp()
check(touch.Controls.DontShowAgainCheckbox:IsChecked(),'Original inverse checkbox initial value changed')
click(touch,'DontShowAgainCheckbox')
check(committed.hideTouchHelp==1 and not touch.Controls.DontShowAgainCheckbox:IsChecked(),'Original inverse checkbox failed to persist')
fail=true;click(touch,'DontShowAgainCheckbox')
check(committed.hideTouchHelp==1 and not touch.Controls.DontShowAgainCheckbox:IsChecked(),'Failed touch preference was not restored')
fail=false;click(touch,'CloseButton')
check(not touch.ZeroSisUi.IsActive(),'Original touch Close button did not hide')
touch.ZeroSisUi.OpenTouchHelp();check(touch.ZeroSisUi.DispatchKeyDown(27),'Original touch Escape rejected')
check(not touch.ZeroSisUi.IsActive(),'Original touch Escape failed to hide')
local snapshot=env.ZeroSisUi.Snapshot()
check(snapshot.timerSemaphore==0 and snapshot.menuOptions.retailSettingsWritten==false,'Private menu timer/settings boundary changed')
capabilityOverrides={uiCueVolumePercent=false,windowWidth=false,windowHeight=false,fullscreen=false,vsync=false}
local limited=initialize('options');limited.ZeroSisUi.OpenMenuOptions()
for _,target in ipairs(limited.ZeroSisUi.GetInputTargets()) do
 check(target.id~='VideoButton' and target.id~='AudioButton' and target.id~='FullscreenCheck' and
  target.id~='VSyncCheck' and target.id~='ApplyResButton' and target.id~='ZeroSisCueQuieter' and
  target.id~='ZeroSisCueLouder','Unsupported Host backend acquired a visible option target')
end
limited.ZeroSisUi.CloseMenuOptions()
if _RETURN_MENU_SNAPSHOTS then
 local captures={}
 env.ZeroSisUi.OpenMenuOptions();captures.options=env.ZeroSisUi.Snapshot()
 click(env,'VideoButton');captures.video=env.ZeroSisUi.Snapshot()
 click(env,'AudioButton');captures.audio=env.ZeroSisUi.Snapshot()
 env.ZeroSisUi.CloseMenuOptions();captures.optionsClosed=env.ZeroSisUi.Snapshot()
 touch.ZeroSisUi.OpenTouchHelp();captures.touch=touch.ZeroSisUi.Snapshot()
 touch.ZeroSisUi.CloseTouchHelp();captures.touchClosed=touch.ZeroSisUi.Snapshot()
 return json(captures)
end
return json({status='PASS',checks=checks,applies=applies,persistence=persistence,
 originalTouchLuaExecuted=true,retailOptionsLuaExecuted=false,hostExecuted=false,sdkExecuted=false,
 hwndCreated=false,classification='RETAINED_LUA_FIXTURE_ONLY',operations=operations})
'''


def layout(kind):
    key='optionsXml' if kind=='MenuOptions' else 'touchXml'
    tree=menu_options_control_tree(ET.parse(GAME/SOURCE_IDENTITIES[key][0]).getroot(),kind)
    tree['controlDefaultSizes']=menu_checkbox_defaults(tree)
    styles=production_style_defaults(PROJECT/'Source/Assets/UI',tree)
    tree.update(styleDefaults=styles['controls'],styleDefaultsSource=styles['source'],styleDefaultsPolicy=styles['policy'])
    tree['fontMetrics']=production_font_metrics(tree,{})
    return tree


def fixture_script(*,scene_override=None,layouts_override=None):
    sources={'scene':'\n'.join((PROJECT/relative).read_text(encoding='utf-8-sig') for relative in
        ('Source/Host/UiScene.lua','Source/Presentation/UiPresentationInput.lua','Source/Presentation/UiMenuOptions.lua')),
        'touch':(GAME/SOURCE_IDENTITIES['touchLua'][0]).read_text(encoding='utf-8-sig')}
    if scene_override is not None:sources['scene']=scene_override
    return HARNESS.replace('@@SOURCES@@',lua_value(sources)).replace('@@LAYOUTS@@',
        lua_value(layouts_override or {'options':layout('MenuOptions'),'touch':layout('TouchHelp')})),sources


def main():
    before=original_sources();freeze_menu_sources()
    text,sources=fixture_script()
    report=execute_lua(text)
    if original_sources()!=before:raise RuntimeError('Installed menu source changed during pure Lua fixture')
    report.update(schema='zerosis.menu_options.scene_fixture.v1',original_sources=before,
        source_sha256={name:hashlib.sha256(value.encode('utf-8')).hexdigest() for name,value in sources.items()})
    evidence=PROJECT/'evidence/game_menu/offline_menu_suite/options_touch';evidence.mkdir(parents=True,exist_ok=True)
    (evidence/'lua_tests.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({key:report[key] for key in ('status','checks','classification')}))


if __name__=='__main__':main()
