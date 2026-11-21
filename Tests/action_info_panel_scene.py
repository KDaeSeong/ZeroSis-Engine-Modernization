"""Exercise unchanged BNW ActionInfoPanel in the retained Lua 5.1 context.

SDK queries and deferred native requests are explicit component fixtures. This
does not prove native command commits, pixels, live turn legality, or a full game.
Style preparation is temporary and is removed even when an assertion fails.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from economic_overview_scene import execute_lua
from prepare_ui_popup_assets import (GAME, action_info_panel_control_tree, lua_value,
                                     production_font_metrics, production_style_defaults)


HARNESS = r'''
local source=@@SOURCES@@
local layout=@@LAYOUT@@
local inventory=@@INVENTORY@@
local checks=0
local function check(value,message) assert(value,message);checks=checks+1 end
local arrayTypes={}
local function json(value)
  local kind=type(value)
  if kind=='nil' then return 'null' end
  if kind=='boolean' then return tostring(value) end
  if kind=='number' then return string.format('%.17g',value) end
  if kind=='string' then return '"'..value:gsub('[%z\1-\31\\"]',function(ch)
    if ch=='"' then return '\\"' elseif ch=='\\' then return '\\\\' end
    return string.format('\\u%04x',string.byte(ch)) end)..'"' end
  assert(kind=='table','fixture JSON accepts no userdata or functions')
  local parts={}
  if arrayTypes[getmetatable(value)] or #value>0 then
    for _,item in ipairs(value) do parts[#parts+1]=json(item) end
    return '['..table.concat(parts,',')..']'
  end
  local keys={};for key in pairs(value) do assert(type(key)=='string');keys[#keys+1]=key end
  table.sort(keys);for _,key in ipairs(keys) do parts[#parts+1]=json(key)..':'..json(value[key]) end
  return '{'..table.concat(parts,',')..'}'
end
local blocking,notification,turn,turnActive,processing,canEnd,waiting,policySaving=0,41,7,true,false,false,false,false
local requests,fx={},{}
local readyUnit
local plot={GetX=function() return 8 end,GetY=function() return 3 end}
local unit={GetID=function() return 8193 end,GetOwner=function() return 0 end,
  GetPlot=function() return plot end,IsPromotionReady=function() return true end}
local player={IsHuman=function() return true end,IsTurnActive=function() return turnActive end,
  GetEndTurnBlockingType=function() return blocking end,
  GetEndTurnBlockingNotificationIndex=function() return notification end,
  GetFirstReadyUnit=function() return readyUnit end,GetUnitByID=function(_,id) return id==8193 and unit or nil end,
  GetTeam=function() return 0 end,GetCurrentEra=function() return 3 end,
  GetNumNotifications=function() return 1 end,GetNotificationIndex=function() return notification end,
  GetNotificationSummaryStr=function() return 'SDK summary fixture' end,
  GetNotificationStr=function() return 'SDK notification fixture' end,
  Units=function() local delivered=false;return function() if not delivered then delivered=true;return unit end end end}
local env=setmetatable({ZeroSisUiLayout=layout,Players={[0]=player},Teams={[0]={}},GameDefines={MAX_MAJOR_CIVS=1},
  GameInfo={Eras={ERA_INDUSTRIAL={ID=4}}},GameInfoTypes={CONTROL_ENDTURN=23},
  GameOptionTypes={GAMEOPTION_POLICY_SAVING=1},EndTurnBlockingTypes=@@BLOCKERS@@,
  Game={Rand=function() return 0 end,GetActivePlayer=function() return 0 end,
    GetGameTurn=function() return turn end,IsProcessingMessages=function() return processing end,
    DoControl=function() error('SDK command must be deferred') end,
    IsOption=function() return policySaving end,GetNumActiveLeagues=function() return 0 end,
    GetActiveLeague=function() return nil end}}, {__index=_G})
env._G=env
local function run(text,name)
  local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
end
env.include=function(name) return run(assert(source[name],'Missing original include '..name),name) end
env.ZeroSisUiNative=function(operation,...)
  if operation=='uiFrameTime' then return 0.375 end
  if operation=='screenSize' then return 1920,1080 end
  if operation=='randomSeed' then return 17 end
  if operation=='locale' then return (...) end
  if operation=='noBasicHelp' then return false end
  if operation=='actionInfoCanEndTurn' then return canEnd end
  if operation=='actionInfoWaitingForRemotePlayers' then return waiting end
  if operation=='actionInfoMultiplayer' or operation=='actionInfoNetTurnComplete' or
     operation=='actionInfoNetTurnAllComplete' then return false end
  if operation=='snapshotJson' then local snapshot,marker=...;arrayTypes[marker]=true;return snapshot end
  if operation=='headSelectedUnit' then return 0,8193 end
  if operation=='actionInfoGameplayFx' then fx[#fx+1]={...};return end
  if operation=='actionInfoLookAt' or operation=='actionInfoSelectUnit' or
     operation=='actionInfoActivateNotification' or operation=='actionInfoRemoveNotification' or
     operation=='actionInfoEndTurn' then requests[#requests+1]={operation=operation,args={...}};return end
  error('Unexpected native operation '..operation)
end
run(source.scene..'\n'..source.input..'\n'..source.addon,'retained-ActionInfoPanel')
for provider,names in pairs(inventory) do
  local tableValue=assert(env[provider],'Missing original API provider '..provider)
  for _,name in ipairs(names) do
    check(type(tableValue[name])=='function','Original ActionInfoPanel requires missing '..provider..'.'..name)
  end
end
run(source.stock,'original-BNW-ActionInfoPanel.lua')
local function snapshot() return env.ZeroSisUi.Snapshot() end
local function node(root,id)
  if root.id==id then return root end
  for _,child in ipairs(root.children) do local found=node(child,id);if found then return found end end
end
local function refresh(blocker)
  blocking=blocker or blocking
  local before=#requests
  check(env.ZeroSisUi.actionInfoPanelRefresh(),'Original panel must remain visible')
  check(#requests==before,'Read-only refresh emitted a native command')
  return snapshot()
end
local s=refresh(0)
check(s.active and s.nonmodal and s.timerSemaphore==0 and s.presentationClock==0.375,
  'Original action panel lost its nonmodal owner clock')
check(s.contextName=='ActionInfoPanel' and s.popupKind=='ActionInfoPanel','Original panel identity changed')
check(s.actionInfoPanel.owner==0 and s.actionInfoPanel.turn==7 and
  s.actionInfoPanel.notificationPanelIntegrated==false and #s.actionInfoPanel.unconnectedLuaContexts==1,
  'Action panel must expose actual state and unconnected notification declaration')
check(not node(s.tree,'NotificationPanel'),'Unconnected NotificationPanel was fabricated as a retained child')
local button=assert(node(s.tree,'EndTurnButton'))
local key=button.key
local function click(right)
  requests={};fx={}
  local accepted
  if right then accepted=env.ZeroSisUi.DispatchRightClick(key) else accepted=env.ZeroSisUi.DispatchLeftClick(key) end
  check(accepted,'Original registered callback was not consumed')
end
local function single(operation,id)
  check(#requests==1 and requests[1].operation==operation and requests[1].args[1]==id,
    'Original callback requested the wrong native operation')
end
local function pair()
  check(#requests==2 and requests[1].operation=='actionInfoLookAt' and
    requests[2].operation=='actionInfoSelectUnit','Original camera/selection order changed')
  check(requests[1].args[1]==8 and requests[1].args[2]==3 and requests[1].args[3]==0 and
    requests[2].args[1]==0 and requests[2].args[2]==8193,'Original SDK identity or coordinates changed')
  check(#fx==1 and fx[1][1]==7 and fx[1][2]==3 and fx[1][3]==-1,'Original GameplayFX arguments changed')
end
local E=env.EndTurnBlockingTypes
for _,name in ipairs({'ENDTURN_BLOCKING_RESEARCH','ENDTURN_BLOCKING_FREE_TECH',
  'ENDTURN_BLOCKING_PRODUCTION','ENDTURN_BLOCKING_FREE_POLICY','ENDTURN_BLOCKING_FOUND_PANTHEON'}) do
  refresh(E[name]);click(false);single('actionInfoActivateNotification',41)
  click(true);single('actionInfoActivateNotification',41)
end
refresh(E.ENDTURN_BLOCKING_POLICY);click(false);single('actionInfoActivateNotification',41)
click(true);single('actionInfoRemoveNotification',41)
policySaving=true;s=refresh(E.ENDTURN_BLOCKING_POLICY)
check(node(s.tree,'EndTurnButton').tooltip=='TXT_KEY_NOTIFICATION_ENOUGH_CULTURE_FOR_POLICY_DISMISS',
  'Original policy-saving dismissal guidance was lost')
readyUnit=unit
for _,name in ipairs({'ENDTURN_BLOCKING_UNITS','ENDTURN_BLOCKING_UNIT_NEEDS_ORDERS',
  'ENDTURN_BLOCKING_STACKED_UNITS','ENDTURN_BLOCKING_UNIT_PROMOTION'}) do
  refresh(E[name]);click(false);pair();click(true);pair()
end
readyUnit=nil;refresh(E.ENDTURN_BLOCKING_UNITS);click(false)
check(#requests==0,'Missing ready unit fabricated a selection')
canEnd=true;refresh(0);click(false);single('actionInfoEndTurn',23)
click(true);check(#requests==0,'Original right click must never end a clear turn')
processing=true;s=refresh(0);click(false)
check(#requests==0 and node(s.tree,'EndTurnText').text=='TXT_KEY_PLEASE_WAIT',
  'Processing state must not queue an end-turn command')
processing=false;turnActive=false;refresh(0);click(false)
check(#requests==0,'Inactive turn queued a command')
turnActive=true;waiting=true;s=refresh(0)
check(node(s.tree,'EndTurnButton').disabled,'Original remote-wait branch did not disable button')
requests={};check(not env.ZeroSisUi.DispatchLeftClick(key) and not env.ZeroSisUi.DispatchRightClick(key) and #requests==0,
  'Disabled original button accepted a callback')
waiting=false;s=refresh(0)
local targets=env.ZeroSisUi.GetInputTargets()
local left,right=0,0
for _,target in ipairs(targets) do
  if target.id=='EndTurnButton' and target.key==key then
    if target.event=='LeftClick' then left=left+1 elseif target.event=='RightClick' then right=right+1 end
  end
end
check(left==1 and right==1,'Original left/right handlers did not share one retained identity')
check(not env.ZeroSisUi.DispatchLeftClick(key+100000) and not env.ZeroSisUi.DispatchRightClick(key+100000),
  'Stale control identity was accepted')
check(env.ZeroSisUi.DispatchPointerMove(key),'Original button hover was not accepted')
check(#requests==0,'Pointer movement queued an SDK command')
local hoverSnapshotJson=json(snapshot())
local hoverFxCount=#fx
check(json(snapshot())==hoverSnapshotJson,'Action panel snapshot was not stable at its fixed owner clock')
check(env.ZeroSisUi.DispatchPointerMove(key) and json(snapshot())==hoverSnapshotJson,
  'Repeated action button hover changed its retained snapshot at the same owner clock')
check(env.ZeroSisUi.DispatchPointerMove(0),'Action panel pointer leave was not accepted')
local clearedHoverSnapshot=snapshot()
local clearedHoverJson=json(clearedHoverSnapshot)
check(clearedHoverJson~=hoverSnapshotJson,
  'Action button pointer leave lost its actual retained visual-state change')
check(env.ZeroSisUi.DispatchPointerMove(0) and json(snapshot())==clearedHoverJson,
  'Repeated action panel key-zero clear changed its retained snapshot')
check(clearedHoverSnapshot.presentationClock==0.375 and #requests==0 and #fx==hoverFxCount,
  'Action panel hover changed owner time or added an SDK request or effect')
env.Controls.EndTurnButton:SetHide(true)
check(not env.ZeroSisUi.DispatchLeftClick(key) and not env.ZeroSisUi.DispatchRightClick(key),
  'Hidden original control accepted input')
env.Controls.EndTurnButton:SetHide(false)
check(not pcall(env.UI.ActivateNotification,'41') and not pcall(env.UI.SelectUnit,{}) and
  not pcall(env.Game.DoControl,24),'Malformed commands were not rejected at Lua boundary')
local retainedSnapshotJson=json(s)
env.ZeroSisUi.actionInfoPanelStop();env.ZeroSisUi.actionInfoPanelStop()
check(not env.ZeroSisUi.IsActive() and #env.ZeroSisUi.GetInputTargets()==0 and
  not env.ZeroSisUi.DispatchRightClick(key),'Stopped original panel retained live input')
check(not pcall(env.ZeroSisUi.actionInfoPanelRefresh),'Stopped original panel was resurrected')
return json({status='PASS_ORIGINAL_ACTION_INFO_LUA_COMPONENT',checks=checks,
  fixedClockRepeatedHoverUnchanged=true,fixedClockKeyZeroUnchanged=true,hoverLeaveChangesSnapshot=true,
  unchanged_original_script_loaded=true,live_sdk_verified=false,native_commands_verified=false,
  native_pixels_verified=false,notification_panel_integrated=false,
  unconnected_notification_declaration=s.actionInfoPanel.unconnectedLuaContexts,retained_snapshot_json=retainedSnapshotJson})
'''


def verify_component(*, include_snapshot: bool = False) -> dict:
    folder = GAME / 'Assets/DLC/Expansion2/UI/InGame/WorldView'
    paths = {
        'scene': PROJECT / 'Source/Host/UiScene.lua',
        'input': PROJECT / 'Source/Presentation/UiPresentationInput.lua',
        'addon': PROJECT / 'Source/Presentation/UiActionInfoPanel.lua',
        'stock': folder / 'ActionInfoPanel.lua',
        'IconSupport': GAME / 'Assets/UI/IconSupport.lua',
        'FLuaVector': GAME / 'Assets/Gameplay/Lua/FLuaVector.lua',
    }
    sources = {name: path.read_text(encoding='utf-8-sig') for name, path in paths.items()}
    stock_without_comments = re.sub(r'--[^\n]*', '', sources['stock'])
    inventory = {provider: sorted(set(re.findall(r'\b' + provider + r'\s*\.\s*(\w+)\s*\(',
                                                 stock_without_comments)))
                 for provider in ('UI', 'Game', 'Network', 'PreGame', 'OptionsManager', 'Locale')}
    blockers = {name: index + 1 for index, name in enumerate(sorted(set(re.findall(
        r'EndTurnBlockingTypes\.(ENDTURN_BLOCKING_\w+)', stock_without_comments))))}
    # Ordinals are deliberately fixture-only. All stock comparisons use the
    # same named table; native production uses the original SDK enum bindings.
    tree = action_info_panel_control_tree(ET.parse(folder / 'ActionInfoPanel.xml').getroot())
    tree.update(contextName='ActionInfoPanel', popupKind='ActionInfoPanel')
    inline = json.loads((PROJECT / 'evidence/ui_popup/assets/inline_icons.json').read_text(encoding='utf-8'))['icons']
    with tempfile.TemporaryDirectory(prefix='zerosis-action-info-component-') as temporary:
        styles = production_style_defaults(Path(temporary), tree)
        tree.update(styleDefaults=styles['controls'], styleDefaultsSource=styles['source'],
                    styleDefaultsPolicy=styles['policy'])
        tree['fontMetrics'] = production_font_metrics(tree, inline)
        source = (HARNESS.replace('@@SOURCES@@', lua_value(sources)).replace('@@LAYOUT@@', lua_value(tree))
                  .replace('@@INVENTORY@@', lua_value(inventory)).replace('@@BLOCKERS@@', lua_value(blockers)))
        result = execute_lua(source)
    assert result.pop('unconnected_notification_declaration') == tree['actionInfoPanel']['unconnectedLuaContexts']
    snapshot = json.loads(result.pop('retained_snapshot_json'))
    if include_snapshot:
        result['retained_snapshot'] = snapshot
    result['unconnected_declaration_json_shape_verified'] = True
    result['original_api_inventory'] = inventory
    result['source_sha256'] = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    return result


if __name__ == '__main__':
    print(json.dumps(verify_component(), ensure_ascii=False))
