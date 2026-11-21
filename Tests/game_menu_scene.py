"""Exercise unchanged base GameMenu Lua and BNW XML in the retained Lua 5.1 VM.

SDK/player/clock calls are explicit component fixtures. Rows are read from the
current manual runtime's rules database; this is not native execution, gameplay,
pixel or retail animation timing proof. Small temporary styles are removed.
"""
from __future__ import annotations
from contextlib import closing
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
from economic_overview_scene import execute_lua
from game_menu_ui_assets import small_source_directory
from prepare_ui_popup_assets import (
    GAME, game_menu_control_tree, lua_value, production_font_metrics,
    production_style_defaults,
)

HARNESS = r'''
local source,layout,data=@@SOURCES@@,@@LAYOUT@@,@@DATA@@
local checks=0
local function check(value,message) assert(value,message);checks=checks+1 end
local arrayTypes={}
local function localized(value)
 if type(value)=='string' and value:sub(1,8)=='TXT_KEY_' then
  return assert(data.locale[value],'Missing original localization: '..value)
 end
 return tostring(value)
end
local function unicodeChars(text)
 local chars={}
 for ch in text:gmatch('[%z\1-\127\194-\244][\128-\191]*') do chars[#chars+1]=ch end
 assert(table.concat(chars)==text,'Invalid fixture UTF-8 text')
 return chars
end
-- The real native operation serializes synchronously to an immutable string.
-- Keep inspectable Lua tables here, but detach every value at that same boundary.
local function captured(value)
 if type(value)~='table' then return value end
 local result=setmetatable({},getmetatable(value))
 for key,item in pairs(value) do result[key]=captured(item) end
 return result
end
local function json(value)
 local kind=type(value)
 if kind=='nil' then return 'null' end
 if kind=='boolean' then return tostring(value) end
 if kind=='number' then return string.format('%.17g',value) end
 if kind=='string' then return '"'..value:gsub('[%z\1-\31\\"]',function(ch)
  if ch=='"' then return '\\"' elseif ch=='\\' then return '\\\\' end
  return string.format('\\u%04x',string.byte(ch)) end)..'"' end
 assert(kind=='table','Only data may enter the snapshot encoder')
 local parts={}
 if arrayTypes[getmetatable(value)] or #value>0 then
  for _,item in ipairs(value) do parts[#parts+1]=json(item) end
  return '['..table.concat(parts,',')..']'
 end
 local keys={};for k in pairs(value) do assert(type(k)=='string');keys[#keys+1]=k end
 table.sort(keys)
 for _,k in ipairs(keys) do parts[#parts+1]=json(k)..':'..json(value[k]) end
 return '{'..table.concat(parts,',')..'}'
end
local info={}
for name,rows in pairs(data.tables) do
 local indexed={}
 for _,row in ipairs(rows) do
  if row.ID~=nil then indexed[row.ID]=row end
  if row.Type~=nil then indexed[row.Type]=row end
 end
 info[name]=setmetatable(indexed,{__call=function(_,conditions)
  if type(conditions)=='string' then
   local key,value=conditions:match("^%s*(%w+)%s*=%s*'([^']*)'%s*$")
   assert(key,'Unmodeled original DB filter: '..conditions);conditions={[key]=value}
  end
  assert(conditions==nil or type(conditions)=='table','Unmodeled DB condition type')
  local at=0
  return function()
   while true do
    at=at+1;local row=rows[at];if not row then return nil end
    local matches=true
    for k,v in pairs(conditions or {}) do if row[k]~=v then matches=false;break end end
    if matches then return row end
   end
  end
 end})
end
local now,owner,turn=0,0,1
local requests,timerEvents,cursorEvents={}, {}, {}
local localeCalls={}
local timerBalance,cursor,mutations=0,0,0
local fixtureTouch=data.touch
assert(type(fixtureTouch)=='boolean','Original touch capability fixture is required')
local leader=assert(info.Leaders.LEADER_AUGUSTUS)
local civ=assert(info.Civilizations.CIVILIZATION_ROME)
local color=assert(info.PlayerColors[civ.DefaultPlayerColor])
local player={GetLeaderType=function() return leader.ID end,GetTeam=function() return 0 end,
 GetCivilizationType=function() return civ.ID end,GetHandicapType=function() return 3 end,
 GetNickName=function() return '' end}
local game={Rand=function() return 0 end,GetActivePlayer=function() return owner end,
 GetGameTurn=function() return turn end,GetStartTurn=function() return 0 end,
 IsGameMultiPlayer=function() return false end,IsNetworkMultiPlayer=function() return false end,
 IsStaticTutorialActive=function() return false end,CanDoControl=function() return true end,
 DoControl=function() mutations=mutations+1;error('Real gameplay mutation reached from component') end}
local env=setmetatable({ZeroSisUiLayout=layout,Game=game,GameInfo=info,
 Players={[0]=player},Teams={[0]={}},GameDefines={MAX_MAJOR_CIVS=22},
 ControlTypes={CONTROL_RESTART_GAME=11,CONTROL_RETIRE=12},
 InterfaceModeTypes={INTERFACEMODE_SELECTION=0}}, {__index=_G})
env._G=env
local function run(text,name)
 local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
end
env.include=function(name) return run(assert(source[name],'Missing original include '..name),name) end
env.ZeroSisUiNative=function(op,...)
 if op=='uiFrameTime' then return now end
 if op=='screenSize' then return 1920,1080 end
 if op=='snapshotJson' then local value,marker=...;arrayTypes[marker]=true;return captured(value) end
 if op=='randomSeed' then return 17 end
 if op=='locale' then
  local key=...;local args={select(2,...)}
  localeCalls[key]=(localeCalls[key] or 0)+1
  -- The native provider composes dictionary references and case modifiers.
  -- Model only the menu's data-backed upper/lower forms here; production
  -- continues to use Localization::Lookup/toUTF8, not this fixture parser.
  local value=localized(key):gsub('{%s*(TXT_KEY_[%w_]+)%s*:%s*(%a+)%s*}',function(tag,style)
   local transform=assert(({upper=string.upper,lower=string.lower})[style],
    'Unmodeled original menu localization modifier: '..style)
   return transform(localized(tag))
  end):gsub('{%s*(TXT_KEY_[%w_]+)%s*}',localized)
  value=value:gsub('{(%d+)_[%w_]+}',function(index)
   return localized(assert(args[tonumber(index)],'Missing original format argument'))
  end)
  assert(not value:find('[{}]'),'Unmodeled original menu localization format')
  return value
 end
 if op=='localeLength' then return #unicodeChars(...) end
 if op=='localeSubstring' then
  local s,a,n=...;local chars=unicodeChars(s)
  assert(a>=1 and n>=0 and a-1+n<=#chars,'Fixture Unicode substring is out of range')
  return table.concat(chars,'',a,a+n-1)
 end
 if op=='noBasicHelp' then return false end
 if op=='civilization' then return civ.ID end
 if op=='playerColor' then return color.ID end
 if op=='isTouchScreen' then return fixtureTouch end
 if op=='timer' then
  local delta=(...);timerBalance=timerBalance+delta
  check(timerBalance==0 or timerBalance==1,'Original GameMenu timer is unbalanced')
  timerEvents[#timerEvents+1]=delta;return
 end
 if op=='gameMenuPreGame' then
  local which,id=...
  if which=='leaderName' or which=='civilizationShortDescription' then return '' end
  if which=='mapScript' then return 'Assets/Maps/Continents.lua' end
  if which=='worldSize' then return 3 end
  if which=='gameSpeed' then return 2 end
  if which=='era' then return 0 end
  if which=='handicap' then return 3 end
  if which=='victory' then return true end
  if which=='gameOption' then return nil end
  if which=='loadWBScenario' then return false end
  error('Unexpected setup query '..tostring(which))
 end
 if op=='gameMenuActivatedMods' then return {} end
 if op=='gameMenuModPropertyContains' then
  local property,value=...
  check((property=='DisableQuickSave' or property=='DisableSaveGameOption' or
   property=='DisableLoadGameOption') and value=='1','Unmodeled mod property query')
  return false
 end
 if op=='gameMenuModProperty' then error('No active mod was selected') end
 if op=='gameMenuMapPreview' then return nil end
 if op=='gameMenuInterfaceMode' then check((...)==0,'Original menu requested non-selection mode');return end
 if op=='gameMenuCursor' then
  local previous=cursor;cursor=(...);check(cursor==0 or cursor==1,'Unsupported cursor token')
  cursorEvents[#cursorEvents+1]=cursor;return previous
 end
 if op=='gameMenuQuickSave' then
  check(timerBalance==0 and not env.ZeroSisUi.IsActive(),'QuickSave was not deferred after OnReturn')
  requests[#requests+1]={kind='QuickSave'};return
 end
 if op=='gameMenuUnavailable' then requests[#requests+1]={kind='Unavailable',action=(...)};return end
  if op=='gameMenuExitConfirm' then
   check(select('#',...)==0,'ExitConfirm open request accepted extra arguments')
   requests[#requests+1]={kind='OpenExitConfirm'};return
  end
 if op=='saveMenuOpen' then requests[#requests+1]={kind='OpenSaveMenu',action='SaveMenu'};return end
 if op=='loadMenuOpen' then requests[#requests+1]={kind='OpenLoadMenu',action='LoadMenu'};return end
 error('Unexpected native operation '..op)
end
run(source.scene..'\n'..source.input,'retained-GameMenu')
run(source.stock,'original-GameMenu.lua')
local function snap() return env.ZeroSisUi.Snapshot() end
local function node(tree,id)
 if tree.id==id then return tree end
 for _,child in ipairs(tree.children) do local found=node(child,id);if found then return found end end
end
local function walk(tree,fn)
 fn(tree);for _,child in ipairs(tree.children) do walk(child,fn) end
end
local function originalAutoStackLayout(snapshot)
 local parents={}
 walk(snapshot.tree,function(n)
  for _,child in ipairs(n.children) do parents[child.key]=n end
 end)
 local function union(stack)
  local left,top,right,bottom
  for _,child in ipairs(stack.children) do
   if not child.hidden then
    left=left and math.min(left,child.x) or child.x
    top=top and math.min(top,child.y) or child.y
    right=right and math.max(right,child.x+child.width) or child.x+child.width
    bottom=bottom and math.max(bottom,child.y+child.height) or child.y+child.height
   end
  end
  check(left~=nil and stack.x==left and stack.y==top and
   stack.width==right-left and stack.height==bottom-top,
   'Original auto-size Stack does not enclose its visible child union: '..stack.id)
 end
 local buttons=assert(node(snapshot.tree,'ButtonStack'))
 local frame=assert(parents[buttons.key])
 check(frame.kind=='Grid','Confirmation Stack lost its original Grid parent')
 for _,id in ipairs({'Yes','No'}) do
  local button=assert(node(snapshot.tree,id))
  check(parents[button.key]==buttons and not button.hidden and
   button.x>=frame.x and button.y>=frame.y and
   button.x+button.width<=frame.x+frame.width and
   button.y+button.height<=frame.y+frame.height,
   'Original confirmation button lies outside its Grid: '..id)
 end
 local icons=assert(parents[assert(node(snapshot.tree,'CivIconFrame')).key])
 check(icons.kind=='Stack' and icons.sourceAttributes.Padding=='-4' and
  icons.sourceAttributes.StackGrowth=='Right' and #icons.children==5,
  'Original icon Stack structure or spacing changed')
 for _,stack in ipairs({buttons,icons}) do
  local attrs=stack.sourceAttributes;local parent=assert(parents[stack.key])
  check(attrs.Size==nil and attrs.Anchor=='C,B','Original auto-size Stack declaration changed')
  union(stack)
  local dx,dy=attrs.Offset:match('^(%-?%d+),(%-?%d+)$')
  check(stack.x==parent.x+(parent.width-stack.width)/2+tonumber(dx) and
   stack.y==parent.y+parent.height-stack.height-tonumber(dy),
   'Original centered bottom Stack anchor ignored its measured extent')
 end
 union(assert(node(snapshot.tree,'MainStack')))
end
local function click(id)
 local s=snap();local n=assert(node(s.tree,id),'Missing control '..id)
 check(env.ZeroSisUi.DispatchLeftClick(n.key),'Original button was not reachable: '..id)
end
local function open()
 now=now+1;env.ZeroSisUi.OpenGameMenu()
 check(env.ZeroSisUi.IsActive() and timerBalance==1,'GameMenu did not open with one timer')
end
local function latest(action)
 local r=requests[#requests];check(r and r.kind=='Unavailable' and r.action==action,'Wrong deferred unavailable action')
 check(mutations==0,'An unavailable action mutated gameplay')
end
local function confirmationBlocksBehind()
 local current=snap();local requestCount=#requests
 check(current.gameMenu.confirmationVisible,'Confirmation blocking test needs its original visible box')
 local consumer
 for _,target in ipairs(current.inputTargets) do
  if target.id=='ExitConfirm' and target.event=='ConsumeMouse' then consumer=target end
  if target.event==env.Mouse.eLClick or target.event==env.Mouse.eRClick then
   check(target.id=='Yes' or target.id=='No' or target.id=='TouchHelpButton',
    'Confirmation snapshot exposes a background callback: '..target.id)
  end
 end
 check(consumer and consumer.consumeMouse and consumer.visible and not consumer.disabled and
  consumer.bounds.x==0 and consumer.bounds.y==0 and consumer.bounds.width==1920 and consumer.bounds.height==1080 and
  consumer.clippedBounds.width==1920 and consumer.clippedBounds.height==1080,
  'Original full-screen confirmation consumer is missing')
 local liveConsumer=false
 for _,target in ipairs(env.ZeroSisUi.GetInputTargets()) do
  if target.key==consumer.key and target.consumeMouse then liveConsumer=true end
  if target.event==env.Mouse.eLClick or target.event==env.Mouse.eRClick then
   check(target.id=='Yes' or target.id=='No' or target.id=='TouchHelpButton',
    'Final input addendum exposes a background callback: '..target.id)
  end
 end
 check(liveConsumer,'Final input addendum lost original confirmation consumption')
 for _,id in ipairs({'QuickSaveButton','ReturnButton','LoadGameButton','MainMenuButton'}) do
  local key=assert(node(current.tree,id)).key
  check(not env.ZeroSisUi.DispatchLeftClick(key),'Confirmation accepted a stale/background click: '..id)
  check(not env.ZeroSisUi.DispatchPointerMove(key),'Confirmation accepted background hover: '..id)
  check(not env.ZeroSisUi.DispatchScroll(key,1),'Confirmation accepted background scroll: '..id)
 end
 check(not env.ZeroSisUi.DispatchLeftClick(consumer.key) and #requests==requestCount and
  env.ZeroSisUi.IsActive() and timerBalance==1 and snap().gameMenu.confirmationVisible,
  'Blocked background input dispatched a command or changed modal ownership')
 local touch=assert(node(current.tree,'TouchHelpButton'))
 if fixtureTouch then
  check(env.ZeroSisUi.DispatchPointerMove(touch.key) and env.ZeroSisUi.DispatchLeftClick(touch.key),
   'Original later-sibling touch help was incorrectly covered by confirmation')
  latest('TouchControlsMenu')
 else
  check(touch.hidden and not env.ZeroSisUi.DispatchLeftClick(touch.key),
   'Original non-touch initialization exposed the touch-only callback')
 end
end
check(timerBalance==0 and not env.ZeroSisUi.IsActive(),'Initialization acquired a popup timer')
check(env.PreGame.GetMapScript()=='Assets\\Maps\\Continents.lua','SDK path did not resolve to actual unique DB spelling')
check(env.Path.GetFileNameWithoutExtension('C:\\Maps\\Some.Map.Civ5Map')=='Some.Map','MapUtilities path basename changed')
check(env.Locale.IsNilOrWhitespace(nil) and env.Locale.IsNilOrWhitespace(' \t') and
 env.Locale.IsNilOrWhitespace('\227\128\128') and not env.Locale.IsNilOrWhitespace(' map '),
 'MapUtilities whitespace contract failed')
check(env.Locale.ConvertTextKey('TXT_KEY_MENU_RESTART_GAME_BUTTON')=='게임 재시작',
 'Original Korean button text was not resolved')
check(env.Locale.ConvertTextKey('TXT_KEY_START_ERA','고대 시대')=='시작 시대 : 고대 시대',
 'Original menu localization argument was not composed')
check(env.Locale.Length('문명 V')==4 and env.Locale.Substring('문명 V',2,2)=='명 ',
 'Fixture Unicode text semantics differ from native codepoints')
open()
local retained=snap()
local retainedAtCapture=json(retained)
originalAutoStackLayout(retained)
check(retained.contextName=='GameMenu' and retained.popupKind=='GameMenu' and retained.timerSemaphore==1,'Wrong menu snapshot identity')
check(retained.gameMenu.owner==0 and retained.gameMenu.turn==1 and
 retained.gameMenu.rawMapScript=='Assets/Maps/Continents.lua' and
 retained.gameMenu.databaseMapScript=='Assets\\Maps\\Continents.lua','Map/source metadata lost')
check(#retained.gameMenu.unconnectedLuaContexts==3 and retained.gameMenu.loadMenuSourceApisBound==true and
 retained.gameMenu.sourceConnectedChildren[1]=='SaveMenu' and retained.gameMenu.sourceConnectedChildren[2]=='LoadMenu' and
 not retained.gameMenu.childContextsRuntimeVerified,'Connected source children or remaining unconnected child claims changed')
local retire=assert(node(retained.tree,'RetireButton'))
check(not retire.hidden and not retire.disabled and retire.text=='포기',
 'Original visible Retire caption did not resolve to Korean at turn 1')
check(retire.sourceAttributes.String=='{TXT_KEY_RETIRE: upper}' and
 (localeCalls[retire.sourceAttributes.String] or 0)>0,
 'Original XML expression was not forwarded intact through the native locale boundary')
local count=0
walk(retained.tree,function(n)
 if n.kind=='AlphaAnim' and n.attributes.Cycle=='Once' then
  count=count+1;local a=n.animation
  check(a.alpha==0.2 and a.elapsed==0 and a.normalizedPhase==0 and a.activationStartTime==0 and
   not a.running and not a.completed,'Initial Once state is not dormant')
 end
end)
check(count==9,'The nine original Once hover nodes were not retained')
check(not pcall(env.ZeroSisUi.OpenGameMenu) and timerBalance==1,'Duplicate menu open acquired another timer')
local hoverKey=node(retained.tree,'QuickSaveButton').key
local function onceUnder(id)
 local found;walk(node(snap().tree,id),function(n) if n.kind=='AlphaAnim' and n.attributes.Cycle=='Once' then found=n end end)
 return assert(found).animation
end
now=10;check(env.ZeroSisUi.DispatchPointerMove(hoverKey),'Hover was not consumed')
now=10.5;local animation=snap();local a=onceUnder('QuickSaveButton')
local animationAtCapture=json(animation)
check(math.abs(a.alpha-0.1)<1e-12 and a.elapsed==0.5 and a.running and not a.completed and a.activationStartTime==10,'Once linear midpoint changed: '..json(a))
now=11; a=onceUnder('QuickSaveButton')
check(a.alpha==0 and a.elapsed==1 and not a.running and a.completed,'Once did not stop at the endpoint')
now=100; a=onceUnder('QuickSaveButton')
check(a.alpha==0 and a.elapsed==1 and a.completed,'Once looped instead of holding its endpoint')
env.ZeroSisUi.DispatchPointerMove(0);now=101;env.ZeroSisUi.DispatchPointerMove(hoverKey);a=onceUnder('QuickSaveButton')
check(a.alpha==0.2 and a.elapsed==0 and a.activationStartTime==101 and a.running and not a.completed,'Hover reentry did not restart Once')
now=101.25;env.ZeroSisUi.DispatchPointerMove(hoverKey);a=onceUnder('QuickSaveButton')
check(math.abs(a.alpha-0.15)<1e-12 and a.activationStartTime==101,'Repeated hover reset the time origin')
now=104;env.ZeroSisUi.DispatchPointerMove(0);a=onceUnder('QuickSaveButton')
check(a.alpha==0 and a.elapsed==1 and a.completed and not a.running,
 'Hover leave after duration lost completion when no endpoint snapshot occurred')
click('DetailsButton');local details=snap()
local detailsAtCapture=json(details)
check(not node(details.tree,'DetailsPanel').hidden and node(details.tree,'MainContainer').hidden,'Original details toggle did not open')
check(#details.scrollTargets>0,'Original details panel lost its scroll target')
env.ZeroSisUi.ShowGameMenuUnavailable('LoadMenu','이 기능은 아직 사용할 수 없습니다.')
local detailsNotice=snap()
local detailsNoticeAtCapture=json(detailsNotice)
check(#env.ZeroSisUi.GetScrollTargets()==0,'Confirmation exposes the original details scroll behind it')
for _,target in ipairs(details.scrollTargets) do
 check(not env.ZeroSisUi.DispatchScroll(target.key,1),'Confirmation accepted a retained details scroll key')
end
click('No')
check(not node(snap().tree,'DetailsPanel').hidden,'Confirmation cancel lost the original details view')
click('DetailsButton');check(node(snap().tree,'DetailsPanel').hidden,'Original details toggle did not return')
for id,action in pairs({SaveGameButton='SaveMenu',LoadGameButton='LoadMenu',OptionsButton='OptionsMenu_InGame',TouchHelpButton='TouchControlsMenu'}) do
 if id~='TouchHelpButton' or fixtureTouch then
  click(id)
  if action=='SaveMenu' then check(requests[#requests].kind=='OpenSaveMenu','Original Save callback did not queue connected child')
  elseif action=='LoadMenu' then
   check(requests[#requests].kind=='OpenLoadMenu','Original Load callback did not queue connected child')
   check(mutations==0,'Opening the original Load child mutated gameplay')
  else latest(action) end
  check(env.ZeroSisUi.IsActive() and timerBalance==1,'Child request altered menu lifetime')
  check(node(snap().tree,action).hidden,'Inline child declaration became visible instead of deferring to its owned context')
 end
end
env.UIManager:QueuePopup(env.Controls.SaveMapMenu,env.PopupPriority.SaveMapMenu);latest('SaveMapMenu')
env.ZeroSisUi.ShowGameMenuUnavailable('LoadMenu','이 기능은 아직 사용할 수 없습니다.')
local notice=snap()
local noticeAtCapture=json(notice)
originalAutoStackLayout(notice)
check(notice.gameMenu.confirmationVisible and notice.gameMenu.unavailableAction=='LoadMenu' and
 node(notice.tree,'Yes').disabled,'Deferred notice did not disable confirmation action')
confirmationBlocksBehind()
for _,target in ipairs(env.ZeroSisUi.GetInputTargets()) do check(target.id~='Yes','Disabled Yes remained an input target') end
local noticeRequests=#requests
click('No')
local restoredNotice=snap()
local restoredNoticeAtCapture=json(restoredNotice)
check(not restoredNotice.gameMenu.confirmationVisible and restoredNotice.gameMenu.unavailableAction==nil and
 not node(restoredNotice.tree,'Yes').hidden and not node(restoredNotice.tree,'Yes').disabled and
 #requests==noticeRequests,'Original No did not dismiss only the notice and restore Yes')
env.ZeroSisUi.ShowGameMenuUnavailable('SaveMenu','이 기능은 아직 사용할 수 없습니다.')
check(env.ZeroSisUi.DispatchKeyDown(27) and env.ZeroSisUi.IsActive() and timerBalance==1 and
 snap().gameMenu.unavailableAction==nil and not node(snap().tree,'Yes').disabled,
 'Original Escape did not dismiss only the notice')
check(not pcall(function() env.ZeroSisUi.ShowGameMenuUnavailable('Unknown','bad') end),
 'Unknown unavailable action was accepted')

click('RestartGameButton');latest('Restart')
check(env.ZeroSisUi.IsActive() and timerBalance==1,'Unavailable Restart changed menu lifetime')
local beforeExitConfirm=#requests
click('ExitGameButton')
check(#requests==beforeExitConfirm+1 and requests[#requests].kind=='OpenExitConfirm',
 'Original ExitGame button did not defer exactly one separate confirmation')
check(env.ZeroSisUi.IsActive() and timerBalance==1 and cursor==0,
 'Opening the separate exit confirmation changed the parent menu lifetime')
click('MainMenuButton')
check(not node(snap().tree,'ExitConfirm').hidden,'Original confirmation did not show')
local confirmation=snap()
local confirmationAtCapture=json(confirmation)
originalAutoStackLayout(confirmation)
confirmationBlocksBehind()
local beforeRequests=#requests
check(env.ZeroSisUi.DispatchKeyDown(27) and env.ZeroSisUi.IsActive() and timerBalance==1,'Escape closed whole menu instead of only confirmation')
check(node(snap().tree,'ExitConfirm').hidden and #requests==beforeRequests,'Confirmation cancel submitted exit')
click('MainMenuButton');click('Yes');latest('ExitToMainMenu')
check(timerBalance==1 and env.ZeroSisUi.IsActive() and cursor==0 and
 cursorEvents[#cursorEvents-1]==1 and cursorEvents[#cursorEvents]==0,'Unavailable confirmed exit failed to restore timer/cursor')
click('MainMenuButton');env.ZeroSisUi.CloseGameMenu();local closed=snap()
local closedAtCapture=json(closed)
check(not closed.active and closed.timerSemaphore==0 and cursor==0 and node(closed.tree,'ExitConfirm').hidden,'Host stop failed to clear confirmation and original lifetime')
env.ZeroSisUi.CloseGameMenu();check(timerBalance==0,'Repeated host stop released timer twice')
open();click('ReturnButton');check(timerBalance==0 and not env.ZeroSisUi.IsActive(),'Original Return failed')
open();check(env.ZeroSisUi.DispatchKeyDown(27) and timerBalance==0,'Normal Escape failed')
open();click('QuickSaveButton')
check(requests[#requests].kind=='QuickSave' and not env.ZeroSisUi.IsActive() and timerBalance==0,'Original QuickSave callback order failed')
open();click('RetireButton');latest('Retire')
check(not env.ZeroSisUi.IsActive() and timerBalance==0,'Original Retire Return was lost')
check(not pcall(function() env.Game.DoControl(999) end) and mutations==0,'Unknown gameplay control was allowed')
check(not env.ZeroSisUi.DispatchLeftClick(hoverKey),'Closed menu accepted stale input')
check(not pcall(function() env.UIManager:QueuePopup({},env.PopupPriority.SaveMenu) end),'Foreign child context was accepted')
-- Load only the unchanged original TopPanel menu callback in a small TopPanel
-- scene: full TopPanel data population is covered by its own component tests.
local topLayout={attributes={},children={{kind='GridButton',attributes={ID='MenuButton',Size='100,40'},children={}}},
 popupKind='TopPanel',contextName='TopPanel',toolTipTemplates={},styleDefaults={},
 styleDefaultsSource=layout.styleDefaultsSource,styleDefaultsPolicy=layout.styleDefaultsPolicy,fontMetrics=layout.fontMetrics}
local top=setmetatable({ZeroSisUiLayout=topLayout,Game={Rand=function() return 0 end}}, {__index=_G});top._G=top
local topRequests=0
top.ZeroSisUiNative=function(op,...)
 if op=='headSelectedCity' then return nil,nil end
 if op=='uiFrameTime' then return now end
 if op=='randomSeed' then return 17 end
 if op=='gameMenuOpen' then topRequests=topRequests+1;return end
 error('Unexpected TopPanel menu operation '..op)
end
local f=assert(loadstring(source.scene,'@TopPanel-UiScene'));setfenv(f,top);f()
f=assert(loadstring(source.topMenu,'@original-TopPanel-OnMenu'));setfenv(f,top);f()
local targets=top.ZeroSisUi.GetInputTargets()
check(#targets==1 and top.ZeroSisUi.DispatchLeftClick(targets[1].key) and topRequests==1,'Original TopPanel menu callback did not queue Open')
check(not pcall(function() top.LookUpControl('/InGame/ForeignMenu') end),'Foreign TopPanel menu path accepted')
check(not pcall(function() top.UIManager:QueuePopup(top.LookUpControl('/InGame/GameMenu'),top.PopupPriority.InGameMenu) end),'Out-of-callback menu open accepted')
check(timerBalance==0 and mutations==0,'Component left game/timer mutations')
for _,item in ipairs({{retained,retainedAtCapture},{animation,animationAtCapture},
 {details,detailsAtCapture},{notice,noticeAtCapture},{restoredNotice,restoredNoticeAtCapture},
 {closed,closedAtCapture},{confirmation,confirmationAtCapture},{detailsNotice,detailsNoticeAtCapture}}) do
 check(json(item[1])==item[2],'Captured snapshot changed after later menu operations')
end
return json({status='PASS_ORIGINAL_GAME_MENU_COMPONENT',checks=checks,
 initialXmlLocalization={expression=retire.sourceAttributes.String,text=retire.text,
  nativeLocaleCalls=localeCalls[retire.sourceAttributes.String],turn=retained.gameMenu.turn},
 timerEvents=timerEvents,cursorEvents=cursorEvents,requests=requests,
 gameplayMutations=mutations,fixtureSDK=true,retailTimingVerified=false,
 retainedSnapshotJson=json(retained),animationSnapshotJson=json(animation),
 detailsSnapshotJson=json(details),closedSnapshotJson=json(closed),noticeSnapshotJson=json(notice),
 restoredNoticeSnapshotJson=json(restoredNotice),confirmationSnapshotJson=json(confirmation),
 detailsNoticeSnapshotJson=json(detailsNotice)})
'''

def verify_component(*, include_snapshot: bool = False, touch: bool = True) -> dict:
    if not isinstance(touch, bool):
        raise ValueError("Touch fixture must be an original boolean capability")
    paths = {
        "scene": PROJECT / "Source/Host/UiScene.lua",
        "input": PROJECT / "Source/Presentation/UiPresentationInput.lua",
        "stock": GAME / "Assets/UI/InGame/Menus/GameMenu.lua",
        "IconSupport": GAME / "Assets/UI/IconSupport.lua",
        "SupportFunctions": GAME / "Assets/UI/SupportFunctions.lua",
        "InstanceManager": GAME / "Assets/UI/InstanceManager.lua",
        "FLuaVector": GAME / "Assets/Gameplay/Lua/FLuaVector.lua",
        "MapUtilities": GAME / "Assets/Gameplay/Lua/MapUtilities.lua",
    }
    source = {name: path.read_text(encoding="utf-8-sig") for name, path in paths.items()}
    top_path = GAME / "Assets/DLC/Expansion2/UI/InGame/TopPanel.lua"
    top_text = top_path.read_text(encoding="utf-8-sig")
    start = top_text.index("function OnMenu()")
    end = top_text.index("Controls.MenuButton:RegisterCallback", start)
    end = top_text.index("\n", end)
    source["topMenu"] = top_text[start:end]
    xml_path = GAME / "Assets/DLC/Expansion2/UI/InGame/Menus/GameMenu.xml"
    original = ET.parse(xml_path).getroot()
    tree = game_menu_control_tree(original)
    tree.update(contextName="GameMenu", popupKind="GameMenu")
    release = json.loads((PROJECT / "Play/EarlyAccess/release.json").read_text(encoding="utf-8-sig"))
    database = PROJECT / "Build/InteractiveGameRuntime" / release["runtime_id"] / "rules.db"
    names = ("Leaders", "Leader_Traits", "Traits", "Civilizations", "PlayerColors",
             "Colors", "IconTextureAtlases", "Worlds", "HandicapInfos", "GameSpeeds",
             "Eras", "MapScripts", "Victories", "GameOptions", "Map_Sizes", "Maps")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        tables = {name: [{k: v for k, v in dict(row).items() if v is not None} for row in connection.execute('SELECT * FROM "' + name + '"')]
                  for name in names}
    localization = database.with_name("localization.db")
    tag_sources = "\n".join(source.values()) + ET.tostring(original, encoding="unicode") + json.dumps(tables)
    tags = sorted(set(re.findall(r"TXT_KEY_[A-Za-z0-9_]+", tag_sources)))
    locale = {}
    with closing(sqlite3.connect(localization.as_uri() + "?mode=ro", uri=True)) as connection:
        for language in ("en_US", "ko_KR"):
            for offset in range(0, len(tags), 500):
                batch = tags[offset:offset + 500]
                locale.update(connection.execute(
                    "SELECT Tag,Text FROM LocalizedText WHERE Language=? AND Tag IN (" +
                    ",".join("?" for _ in batch) + ")", [language, *batch]))
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name, path in {**paths, "xml": xml_path, "TopPanel": top_path}.items()}
    inline = json.loads((PROJECT / "evidence/ui_popup/assets/inline_icons.json").read_text(encoding="utf-8"))["icons"]
    with small_source_directory() as temporary:
        styles = production_style_defaults(temporary, tree)
        tree.update(styleDefaults=styles["controls"], styleDefaultsSource=styles["source"],
                    styleDefaultsPolicy=styles["policy"])
        tree["fontMetrics"] = production_font_metrics(tree, inline)
        program = (HARNESS.replace("@@SOURCES@@", lua_value(source))
                   .replace("@@LAYOUT@@", lua_value(tree))
                   .replace("@@DATA@@", lua_value({"tables": tables, "locale": locale, "touch": touch})))
        result = execute_lua(program)
    for name, path in {**paths, "xml": xml_path, "TopPanel": top_path}.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != before[name]:
            raise AssertionError("Source changed during component: " + name)
    for old_key, new_key in (
        ("retainedSnapshotJson", "retained_snapshot"),
        ("animationSnapshotJson", "animation_snapshot"),
        ("detailsSnapshotJson", "details_snapshot"),
        ("closedSnapshotJson", "closed_snapshot"),
        ("noticeSnapshotJson", "notice_snapshot"),
        ("restoredNoticeSnapshotJson", "restored_notice_snapshot"),
        ("confirmationSnapshotJson", "confirmation_snapshot"),
        ("detailsNoticeSnapshotJson", "details_notice_snapshot"),
    ):
        value = json.loads(result.pop(old_key))
        if include_snapshot:
            result[new_key] = value
    if include_snapshot and touch:
        result["confirmation_touch_snapshot"] = result["confirmation_snapshot"]
    result["source_sha256"] = before
    result["fixture_rules_db"] = str(database)
    result["fixture_rules_sha256"] = hashlib.sha256(database.read_bytes()).hexdigest()
    result["fixture_localization_db"] = str(localization)
    result["fixture_localization_sha256"] = hashlib.sha256(localization.read_bytes()).hexdigest()
    result["fixture_localization_language"] = "ko_KR"
    result["fixture_touch_enabled"] = touch
    result["temporary_styles_removed"] = not temporary.exists()
    return result

if __name__ == "__main__":
    print(json.dumps(verify_component(), ensure_ascii=False))
