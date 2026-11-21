"""Exercise the unchanged global ExitConfirm Lua/XML in the shared Lua 5.1 VM.

Only retained control code and the original callback bodies execute. Screen size,
clock, owner, turn, localization and the native request sink are explicit fixture
boundaries. This does not launch the Host, GameCore, CLR, a window, or a GPU.
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
    GAME, exit_confirm_control_tree, lua_value, production_font_metrics,
    production_style_defaults,
)


HARNESS = r'''
local source,layout,data=@@SOURCES@@,@@LAYOUT@@,@@DATA@@
local checks,now,contextCount=0,100,0
local requests,arrayTypes,localeCalls={},{},{}
local function check(value,message) assert(value,message);checks=checks+1 end
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
 local keys={};for key in pairs(value) do assert(type(key)=='string');keys[#keys+1]=key end
 table.sort(keys)
 for _,key in ipairs(keys) do parts[#parts+1]=json(key)..':'..json(value[key]) end
 return '{'..table.concat(parts,',')..'}'
end
local function unicodeChars(text)
 local chars={}
 for ch in text:gmatch('[%z\1-\127\194-\244][\128-\191]*') do chars[#chars+1]=ch end
 assert(table.concat(chars)==text,'Invalid fixture UTF-8 text')
 return chars
end
local function newContext()
contextCount=contextCount+1
local env=setmetatable({ZeroSisUiLayout=layout,Game={
 Rand=function() error('ExitConfirm requested gameplay RNG') end,
 GetActivePlayer=function() return 0 end,GetGameTurn=function() return 1 end,
}}, {__index=_G})
env._G=env
env.ZeroSisUiNative=function(op,...)
 if op=='uiFrameTime' then return now end
 if op=='screenSize' then return 1920,1080 end
 if op=='randomSeed' then return 17 end
 if op=='exitConfirmInGame' then
  check(select('#',...)==0,'ExitConfirm in-game query accepted arguments')
  return true
 end
 if op=='snapshotJson' then
  local value,marker=...;arrayTypes[marker]=true;return captured(value)
 end
 if op=='locale' then
  check(select('#',...)==1,'ExitConfirm locale accepted unexpected format arguments')
  local key=(...);localeCalls[key]=(localeCalls[key] or 0)+1
  return assert(data.locale[key],'Missing original ExitConfirm localization '..tostring(key))
 end
 if op=='localeLength' then return #unicodeChars(...) end
 if op=='localeSubstring' then
  local text,start,count=...;local chars=unicodeChars(text)
  assert(start>=1 and count>=0 and start-1+count<=#chars,'Fixture substring is out of range')
  return table.concat(chars,'',start,start+count-1)
 end
 if op=='exitConfirmClose' or op=='exitConfirmExit' then
  check(select('#',...)==0,'ExitConfirm native request accepted arguments')
  check(not env.ZeroSisUi.IsActive(),'ExitConfirm native request preceded original PopModal')
  requests[#requests+1]=op;return
 end
 error('Unexpected ExitConfirm native operation '..tostring(op))
end
local function run(text,name)
 local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
end
run(source.scene..'\n'..source.input,'retained-ExitConfirm')
run(source.stock,'original-ExitConfirm.lua')
return env
end
local env=newContext()
local function snap() return env.ZeroSisUi.Snapshot() end
local function node(tree,id)
 if tree.id==id then return tree end
 for _,child in ipairs(tree.children) do local found=node(child,id);if found then return found end end
end
local function click(id)
 local target=assert(node(snap().tree,id),'Missing original ExitConfirm control '..id)
 check(env.ZeroSisUi.DispatchLeftClick(target.key),'Original ExitConfirm button was unreachable: '..id)
end
local function reject(fn,label)
 local count,wasActive=#requests,env.ZeroSisUi.IsActive()
 check(not pcall(fn),label..' was accepted')
 check(#requests==count,label..' queued a native request')
 check(env.ZeroSisUi.IsActive()==wasActive,label..' changed the modal lifetime')
end
local function open()
 now=now+1;local count=#requests
 env.ZeroSisUi.OpenExitConfirm()
 check(env.ZeroSisUi.IsActive() and snap().timerSemaphore==0,
  'Original exit modal must open without owning the GameMenu timer')
 check(#requests==count,'Opening the exit modal queued an exit/close')
end
local initial=snap()
check(not initial.active and initial.timerSemaphore==0,'ExitConfirm initialized active or holding a timer')
check(initial.contextName=='ExitConfirm' and initial.popupKind=='ExitConfirm',
 'ExitConfirm snapshot has the wrong context identity')
check(initial.tree.sourceAttributes.Name=='MainMenu','Original XML Context Name was changed')
reject(function() env.UI.ExitGame() end,'Inactive direct exit')
reject(function() env.OnYes() end,'Inactive direct Yes callback')
reject(function() env.OnNo() end,'Inactive direct No callback')
reject(function() env.Events.UserRequestClose() end,'Direct close event outside host open')
reject(function() env.UIManager:PushModal({}) end,'Foreign modal push')
reject(function() env.UIManager:PopModal({}) end,'Foreign modal pop')
open()
local retained=snap();local retainedAtCapture=json(retained)
check(node(retained.tree,'Message').text==data.locale.TXT_KEY_MENU_RETURN_EXIT_WARN,
 'Original in-game unsaved-progress warning was not selected')
check((localeCalls.TXT_KEY_MENU_RETURN_EXIT_WARN or 0)>0,
 'Original warning did not pass through the localization boundary')
check(env.ContextPtr:LookUpControl('/InGame')~=nil,'Owned in-game control token is absent')
reject(function() env.ContextPtr:LookUpControl('/Foreign') end,'Foreign context lookup')
local targets=env.ZeroSisUi.GetInputTargets()
local callbacks,consumer={},nil
for _,target in ipairs(targets) do
 if target.event==env.Mouse.eLClick or target.event==env.Mouse.eRClick then
  check(target.id=='Yes' or target.id=='No','Exit modal exposes a background callback')
  callbacks[target.id]=true
 end
 if target.id=='ExitConfirm' and target.event=='ConsumeMouse' then consumer=target end
end
check(callbacks.Yes and callbacks.No,'Original exit Yes/No input targets are absent')
check(consumer and consumer.consumeMouse and consumer.visible and not consumer.disabled and
 consumer.bounds.x==0 and consumer.bounds.y==0 and consumer.bounds.width==1920 and consumer.bounds.height==1080,
 'Original exit modal lost its full-screen mouse consumer')
check(not env.ZeroSisUi.DispatchLeftClick(consumer.key) and #requests==0,
 'Background exit-modal click queued a request')
check(not env.ZeroSisUi.DispatchLeftClick(999999) and #requests==0,
 'Unknown control identity queued a request')
local liveYes=assert(node(retained.tree,'Yes')).key
for _,key in ipairs({false,-1,0,1.5,math.huge,0/0,'9'}) do
 check(not env.ZeroSisUi.DispatchLeftClick(key) and #requests==0,
  'Malformed retained click identity was accepted')
end
check(not env.ZeroSisUi.DispatchLeftClick(nil) and #requests==0,'Nil click identity was accepted')
check(not env.ZeroSisUi.DispatchLeftClick(liveYes,env.Mouse.eRClick) and #requests==0,
 'Right-click was accepted as an original Yes confirmation')
check(not env.ZeroSisUi.DispatchLeftClick(liveYes,false) and #requests==0,
 'False event token was treated as a default Yes click')
check(not env.ZeroSisUi.DispatchLeftClick(liveYes,env.Mouse.eLClick,true) and #requests==0,
 'Extra click arguments bypassed the retained modal boundary')
for _,key in ipairs({false,-1,1.5,math.huge,0/0,'27'}) do
 check(not env.ZeroSisUi.DispatchKeyDown(key) and #requests==0,
  'Malformed retained key token was accepted')
end
check(not env.ZeroSisUi.DispatchKeyDown(nil) and #requests==0,'Nil key token was accepted')
check(not env.ZeroSisUi.DispatchKeyDown(27,true) and env.ZeroSisUi.IsActive() and #requests==0,
 'Extra key arguments closed the modal')
check(env.ZeroSisUi.DispatchPointerMove(consumer.key) and #requests==0,
 'Original full-screen consumer rejected pointer hover')
check(env.ZeroSisUi.DispatchPointerMove(0) and #requests==0,'Original modal rejected pointer leave')
reject(function() env.ZeroSisUi.OpenExitConfirm() end,'Repeated host open')
reject(function() env.UI.ExitGame() end,'Active direct exit')
reject(function() env.OnYes() end,'Active direct Yes callback')
reject(function() env.OnNo() end,'Active direct No callback')
reject(function() env.UIManager:PopModal(env.ContextPtr) end,'Direct original-context modal pop')
reject(function() env.UIManager:PushModal(env.ContextPtr,true) end,'Modal push with extra arguments')
local before=#requests
env.Controls.Yes:RegisterCallback(env.Mouse.eLClick,function()
 env.UIManager:PopModal(env.ContextPtr,true)
end)
reject(function() click('Yes') end,'Dispatched modal pop with extra arguments')
env.Controls.Yes:RegisterCallback(env.Mouse.eLClick,env.OnYes)
check(#requests==before,'Extra-argument rejection queued a request')
click('No')
check(not env.ZeroSisUi.IsActive() and snap().timerSemaphore==0 and
 #requests==before+1 and requests[#requests]=='exitConfirmClose',
 'Original No must close only the modal')
local closed=snap();local closedAtCapture=json(closed)
local yesKey=assert(node(closed.tree,'Yes')).key
local count=#requests
check(not env.ZeroSisUi.DispatchLeftClick(yesKey) and #requests==count,
 'Closed modal accepted a stale Yes click')
reject(function() env.UI.ExitGame() end,'Direct exit after cancellation')
reject(function() env.OnYes() end,'Direct Yes after cancellation')
reject(function() env.ZeroSisUi.OpenExitConfirm() end,'Reopen after cancellation')
env=newContext()
open();count=#requests
check(env.ZeroSisUi.DispatchKeyDown(27) and not env.ZeroSisUi.IsActive() and
 #requests==count+1 and requests[#requests]=='exitConfirmClose',
 'Original Escape must close only the modal')
reject(function() env.ZeroSisUi.OpenExitConfirm() end,'Reopen after Escape')
env=newContext()
open();count=#requests
check(env.ZeroSisUi.DispatchKeyDown(65) and env.ZeroSisUi.IsActive() and #requests==count,
 'Original modal failed to consume an unrelated key without closing')
click('Yes')
check(not env.ZeroSisUi.IsActive() and snap().timerSemaphore==0 and #requests==count+2 and
 requests[count+1]=='exitConfirmClose' and requests[count+2]=='exitConfirmExit',
 'Original Yes must close first and queue exactly one exit')
count=#requests
check(not env.ZeroSisUi.DispatchLeftClick(yesKey) and #requests==count,
 'Repeated Yes queued another exit')
reject(function() env.UI.ExitGame() end,'Replayed direct exit after confirmation')
reject(function() env.OnYes() end,'Replayed Yes callback after confirmation')
reject(function() env.ZeroSisUi.OpenExitConfirm() end,'Reopen after confirmation')
env=newContext()
open();count=#requests
env.Controls.Yes:RegisterCallback(env.Mouse.eLClick,function()
 env.UIManager:PopModal(env.ContextPtr);env.UI.ExitGame(true)
end)
check(not pcall(function() click('Yes') end),'Exit with extra arguments was accepted')
check(not env.ZeroSisUi.IsActive() and #requests==count+1 and requests[count+1]=='exitConfirmClose',
 'Malformed exit must retain the original close without queuing exit')
env.Controls.Yes:RegisterCallback(env.Mouse.eLClick,env.OnYes)
reject(function() env.UI.ExitGame() end,'Exit replay after malformed confirmation')
reject(function() env.ZeroSisUi.OpenExitConfirm() end,'Reopen after malformed confirmation')
env=newContext()
open();count=#requests
env.Controls.No:RegisterCallback(env.Mouse.eLClick,function()
 env.UIManager:PopModal(env.ContextPtr);env.UI.ExitGame()
end)
check(not pcall(function() click('No') end),'A cancel callback was allowed to request exit')
check(not env.ZeroSisUi.IsActive() and #requests==count+1 and requests[count+1]=='exitConfirmClose',
 'Malformed cancel callback must close without queuing exit')
reject(function() env.UI.ExitGame() end,'Exit replay after malformed cancel')
env=newContext()
open();count=#requests
env.ZeroSisUi.CloseExitConfirm()
check(not env.ZeroSisUi.IsActive() and #requests==count+1 and requests[count+1]=='exitConfirmClose',
 'Retained close hook must use the original cancel path')
env.ZeroSisUi.CloseExitConfirm()
check(#requests==count+1 and snap().timerSemaphore==0,'Repeated retained close queued another request')
reject(function() env.ZeroSisUi.OpenExitConfirm() end,'Reopen after retained close')
check(json(retained)==retainedAtCapture and json(closed)==closedAtCapture,
 'Captured original modal snapshots changed after later operations')
return json({status='PASS_ORIGINAL_EXIT_CONFIRM_COMPONENT',checks=checks,contexts=contextCount,
 fixtureSDK=true,fixtureOwner=0,fixtureTurn=1,fixtureScreenWidth=1920,fixtureScreenHeight=1080,
 nativeRequests=requests,gameplayMutations=0,timerSemaphore=snap().timerSemaphore,
 originalInGameWarning=node(retained.tree,'Message').text,
 retainedSnapshotJson=json(retained),closedSnapshotJson=json(closed),
 actualHostExecuted=false,actualGameCoreLoaded=false,actualWindowCreated=false,
 actualGpuVerified=false,retailPixelsVerified=false})
'''


def verify_component(*, include_snapshot: bool = False) -> dict:
    paths = {
        "scene": PROJECT / "Source/Host/UiScene.lua",
        "input": PROJECT / "Source/Presentation/UiPresentationInput.lua",
        "stock": GAME / "Assets/UI/FrontEnd/ExitConfirm.lua",
        "xml": GAME / "Assets/UI/FrontEnd/ExitConfirm.xml",
        "lua_provider": PROJECT / "Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll",
    }
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name, path in paths.items()}
    source = {name: paths[name].read_text(encoding="utf-8-sig")
              for name in ("scene", "input", "stock")}
    original = ET.parse(paths["xml"]).getroot()
    tree = exit_confirm_control_tree(original)
    tree.update(contextName="ExitConfirm", popupKind="ExitConfirm")
    release = json.loads((PROJECT / "Play/EarlyAccess/release.json").read_text(encoding="utf-8-sig"))
    localization = PROJECT / "Build/InteractiveGameRuntime" / release["runtime_id"] / "localization.db"
    localization_before = hashlib.sha256(localization.read_bytes()).hexdigest()
    tags = sorted(set(re.findall(r"TXT_KEY_[A-Za-z0-9_]+", source["stock"] +
                                ET.tostring(original, encoding="unicode"))))
    locale = {}
    with closing(sqlite3.connect(localization.as_uri() + "?mode=ro", uri=True)) as connection:
        for language in ("en_US", "ko_KR"):
            locale.update(connection.execute(
                "SELECT Tag,Text FROM LocalizedText WHERE Language=? AND Tag IN (" +
                ",".join("?" for _ in tags) + ")", [language, *tags]))
    inline = json.loads((PROJECT / "evidence/ui_popup/assets/inline_icons.json").read_text(encoding="utf-8"))["icons"]
    with small_source_directory() as temporary:
        styles = production_style_defaults(temporary, tree)
        tree.update(styleDefaults=styles["controls"], styleDefaultsSource=styles["source"],
                    styleDefaultsPolicy=styles["policy"])
        tree["fontMetrics"] = production_font_metrics(tree, inline)
        program = (HARNESS.replace("@@SOURCES@@", lua_value(source))
                   .replace("@@LAYOUT@@", lua_value(tree))
                   .replace("@@DATA@@", lua_value({"locale": locale})))
        result = execute_lua(program)
        temporary_bytes = sum(path.stat().st_size for path in temporary.rglob("*") if path.is_file())
    after = {name: hashlib.sha256(path.read_bytes()).hexdigest()
             for name, path in paths.items()}
    if after != before or hashlib.sha256(localization.read_bytes()).hexdigest() != localization_before:
        raise AssertionError("An ExitConfirm production source, provider, or fixture DB changed during the component")
    for old_key, new_key in (("retainedSnapshotJson", "retained_snapshot"),
                             ("closedSnapshotJson", "closed_snapshot")):
        value = json.loads(result.pop(old_key))
        if include_snapshot:
            result[new_key] = value
    result.update(source_sha256=before, fixture_localization_db=str(localization),
                  fixture_localization_sha256=localization_before,
                  fixture_localization_language="ko_KR", temporary_style_bytes=temporary_bytes,
                  temporary_styles_removed=not temporary.exists())
    return result


if __name__ == "__main__":
    print(json.dumps(verify_component(), ensure_ascii=False))
