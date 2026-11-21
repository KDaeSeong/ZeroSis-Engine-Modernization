"""Run immutable installed SaveMenu Lua/XML in the existing Lua 5.1 provider.

The SDK/catalog bridge is an explicit component fixture, not native game proof.
No test opens a game window or writes a save archive. Only temporary styles are
created; the inherited guarded test directory removes them after execution.
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
from game_menu_scene import HARNESS as GAME_MENU_HARNESS
from game_menu_ui_assets import small_source_directory
from prepare_ui_popup_assets import (
    GAME, SAVE_MENU_LUA, SAVE_MENU_XML, UNIQUE_BONUSES_LUA, lua_value,
    production_font_metrics, production_style_defaults, save_menu_control_tree,
)

HARNESS = GAME_MENU_HARNESS[:GAME_MENU_HARNESS.index("local now,owner,turn=")] + r'''
local now,requests,timerChanges,enumCalls=0,{},0,0
local mapOpenRequests,mapCallback=0,false
local current=data.current
local env=setmetatable({ZeroSisUiLayout=layout,GameInfo=info,
 Game={Rand=function() return 0 end,GetActivePlayer=function() return 0 end,
  GetGameTurn=function() return 1 end,GetElapsedGameTurns=function() return 1 end,
  GetTimeString=function() return '4000 BC' end},
 Players={[0]={GetCurrentEra=function() return current.CurrentEra end}},
 GameOptionTypes={GAMEOPTION_LOCK_MODS=data.lockMods},
 InterfaceModeTypes={INTERFACEMODE_SELECTION=0}}, {__index=_G})
env._G=env
local function run(text,name)
 local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
end
env.include=function(name) return run(assert(source[name],'Missing stock include '..name),name) end
local function available(name)
 if name=='기존 저장' or name=='old-autosave' then return false end
 return #unicodeChars(name)>0 and #unicodeChars(name)<=32
end
env.ZeroSisUiNative=function(op,...)
  if op=='saveMenuOverwriteSupported' then return false end
 if op=='saveMenuDeleteSupported' then return false end
 if op=='uiFrameTime' then return now end
 if op=='screenSize' then return 1920,1080 end
 if op=='snapshotJson' then local value,marker=...;arrayTypes[marker]=true;return captured(value) end
 if op=='randomSeed' then return 17 end
 if op=='locale' then
  local key=...;local args={select(2,...)};local value=localized(key)
  value=value:gsub('{(%d+)_[%w_]+}',function(index) return localized(args[tonumber(index)] or '') end)
  return value
 end
 if op=='localeLength' then return #unicodeChars(...) end
 if op=='localeUpper' then return string.upper(...) end
 if op=='localeLower' then return string.lower(...) end
 if op=='localeSubstring' then
  local s,a,n=...;return table.concat(unicodeChars(s),'',a,a+n-1)
 end
 if op=='noBasicHelp' then return false end
 if op=='civilization' then return current.PlayerCivilization end
 if op=='playerColor' then return 0 end
 if op=='timer' then timerChanges=timerChanges+1;error('SaveMenu must not own a timer') end
 if op=='saveMenuGameTypes' then
  check(select('#',...)==0,'Game type enum binding arity changed');enumCalls=enumCalls+1
  if data.enumFixture=='missing' then return nil end
  if data.enumFixture=='non_table' then return 7 end
  local value=captured(data.gameTypes)
  if data.enumFixture=='wrong_value' then value.GAME_TYPE_NONE=9 end
  if data.enumFixture=='missing_field' then value.GAME_EMAIL_MULTIPLAYER=nil end
  return value
 end
 if op=='saveMenuCurrent' then return captured(current) end
 if op=='saveMenuFiles' then return {data.savePath,data.unknownPath} end
 if op=='saveMenuHeader' then
  local path=...;check(path==data.savePath or path==data.unknownPath,'Foreign header lookup')
  return path==data.savePath and captured(current) or nil
 end
 if op=='saveMenuModificationTime' then
  check((...)==data.savePath,'Unknown archive fabricated modification display');return '2026-10-13 12:00'
 end
 if op=='saveMenuNameAvailable' then return available(...) end
 if op=='saveMenuSave' then requests[#requests+1]={kind='Save',name=(...)};return end
 if op=='mapMenuOpen' then
  check(mapCallback and select('#',...)==0,'Nested map request escaped its original SaveMapButton callback')
  mapOpenRequests=mapOpenRequests+1;return
 end
 if op=='saveMenuClose' then requests[#requests+1]={kind='Close'};return end
 if op=='gameMenuPreGame' then
  local selector=...;if selector=='gameOption' then return 0 end
  error('Unexpected setup query '..tostring(selector))
 end
 if op=='gameMenuModPropertyContains' then
  local property,value=...;check(property=='DisableSaveMapOption' and value=='1','Unexpected mod property');return false
 end
 if op=='gameMenuMapPreview' then return nil end
 error('Unexpected native operation '..op)
end
check(env.GameTypes==nil,'Fixture prepopulated a frontend GameTypes global')
run(source.scene..'\n'..source.input,'retained-SaveMenu')
check(enumCalls==1 and env.GameTypes.GAME_TYPE_NONE==data.gameTypes.GAME_TYPE_NONE and
 env.GameTypes.GAME_EMAIL_MULTIPLAYER==data.gameTypes.GAME_EMAIL_MULTIPLAYER,'Actual enum binding was bypassed')
run(source.stock,'original-SaveMenu.lua')
local function snap() return env.ZeroSisUi.Snapshot() end
local function node(tree,id)
 if tree.id==id then return tree end
 for _,child in ipairs(tree.children) do local found=node(child,id);if found then return found end end
end
local function target(id)
 for _,value in ipairs(env.ZeroSisUi.GetInputTargets(env.Mouse.eLClick)) do
  if value.id==id and value.event==env.Mouse.eLClick then return value.key end
 end
end
local function click(id)
 local key=assert(target(id),'Missing target '..id)
 local consumed=env.ZeroSisUi.DispatchLeftClick(key)
 check(consumed, 'Click failed '..id..' key='..key..' name='..env.Controls.NameBox:GetText())
end
local function replaceName(value)
 click('NameBox');env.ZeroSisUi.DispatchKeyDown(35)
 local focusToken=env.ZeroSisUi.GetTextInputFocusToken()
 for _=1,#unicodeChars(env.Controls.NameBox:GetText()) do check(env.ZeroSisUi.DispatchKeyDown(8),'Backspace failed') end
 for _,ch in ipairs(unicodeChars(value)) do
  local bytes={ch:byte(1,#ch)};local scalar=bytes[1]
  if #bytes==2 then scalar=bytes[1]-0xC0 elseif #bytes==3 then scalar=bytes[1]-0xE0 elseif #bytes==4 then scalar=bytes[1]-0xF0 end
  for i=2,#bytes do scalar=scalar*64+bytes[i]-0x80 end
  check(env.ZeroSisUi.DispatchTextInput(scalar),'Unicode insert failed')
 end
 check(env.Controls.NameBox:GetText()==value,'NameBox differs from inserted Unicode scalars')
 check(env.ZeroSisUi.GetTextInputFocusToken()==focusToken and focusToken>0,'Editing changed the focused editor lifetime')
end
check(not env.ZeroSisUi.DispatchTextInput(0xAC00),'Closed child accepted text')
check(env.ZeroSisUi.GetTextInputFocusToken()==0,'Closed editor has a focus token')
env.ZeroSisUi.OpenSaveMenu()
local opened=snap();local openedJson=json(opened)
check(opened.active and opened.timerSemaphore==0 and opened.saveMenu.parentContext=='GameMenu','Child lifetime/timer wrong')
check(opened.saveMenu.catalogCount==2 and opened.saveMenu.textInputEnabled,'Real list/focus absent')
check(opened.saveMenu.focusEpoch>0 and opened.saveMenu.textInputFocusToken==opened.saveMenu.focusEpoch and
 env.ZeroSisUi.GetTextInputFocusToken()==opened.saveMenu.focusEpoch,'Opened editor token absent')
check(snap().saveMenu.focusEpoch==opened.saveMenu.focusEpoch,'Scene refresh changed editor lifetime')
check(node(opened.tree,'NameBox').maxLength==32,'Original MaxLength changed')
for _,id in ipairs({'Delete','CloudCheck','Yes'}) do
 check(node(opened.tree,id).disabled and not target(id),'Unsupported action remained callable '..id)
 env.Controls[id]:SetDisabled(false);check(node(snap().tree,id).disabled,'Stock reset bypassed unsupported gate '..id)
end
env.Controls.SaveMapButton:SetHide(false)
check(not node(snap().tree,'SaveMapButton').hidden and not node(snap().tree,'SaveMapButton').disabled,
 'Connected original map save button remained hidden or disabled')
check(not pcall(function() env.Controls.CloudCheck:SetCheck(true) end),'Cloud setting bypassed gate')
check(not pcall(function() env.UIManager:QueuePopup(env.Controls.SaveMapMenu,env.PopupPriority.SaveMapMenu) end),'Map child bypassed gate')
check(not pcall(function() env.UI.DeleteSavedGame(data.savePath) end),'Delete API bypassed gate')
mapCallback=true;click('SaveMapButton');mapCallback=false
check(mapOpenRequests==1 and env.ZeroSisUi.IsActive() and snap().timerSemaphore==0,
 'Nested map request changed its original retained SaveMenu parent')
local rows={};for _,value in ipairs(env.ZeroSisUi.GetInputTargets()) do if value.id=='Button' then rows[#rows+1]=value.key end end
check(#rows==2,'Original LoadButton instances missing')
check(env.ZeroSisUi.DispatchLeftClick(rows[1]),'Known list entry click failed')
local selected=snap()
check(not selected.saveMenu.textInputEnabled and selected.saveMenu.focusEpoch>opened.saveMenu.focusEpoch and
 env.ZeroSisUi.GetTextInputFocusToken()==0,'List selection retained stale editor ownership')
check(node(selected.tree,'NameBox').text=='기존 저장' and node(selected.tree,'SaveButton').disabled,'Duplicate selection enabled overwrite')
check(node(selected.tree,'TimeSaved').text=='2026-10-13 12:00','Known header date missing')
check(env.ZeroSisUi.DispatchLeftClick(rows[2]),'Unknown header entry click failed')
check(node(snap().tree,'TimeSaved').text=='' and node(snap().tree,'SaveButton').disabled,'Unknown archive fabricated preview/enabled overwrite')
replaceName('한글 저장')
local editingToken=env.ZeroSisUi.GetTextInputFocusToken()
check(editingToken>selected.saveMenu.focusEpoch,'Refocusing reused blurred editor ownership')
check(not node(snap().tree,'SaveButton').disabled,'Unique Korean name did not enable Save')
check(env.ZeroSisUi.DispatchKeyDown(36) and env.ZeroSisUi.DispatchKeyDown(39),'Caret keys failed')
check(env.ZeroSisUi.DispatchTextInput(0xB098),'Middle Unicode insert failed')
check(env.Controls.NameBox:GetText()=='한나글 저장','Insert did not use codepoint caret')
check(env.ZeroSisUi.DispatchKeyDown(8) and env.Controls.NameBox:GetText()=='한글 저장','Backspace split Unicode scalar')
check(env.ZeroSisUi.DispatchKeyDown(46) and env.Controls.NameBox:GetText()=='한 저장','Delete split Unicode scalar')
check(env.ZeroSisUi.GetTextInputFocusToken()==editingToken,'Caret or Unicode edit changed editor lifetime')
replaceName(string.rep('가',32))
check(env.ZeroSisUi.DispatchTextInput(0xB098) and env.Controls.NameBox:GetText()==string.rep('가',32),'NameBox exceeded scalar maximum')
local longNameJson=json(snap())
check(env.ZeroSisUi.DispatchKeyDown(36),'Long name Home failed')
local longHomeJson=json(snap())
replaceName('[ICON_GOLD]')
check(env.Controls.NameBox:GetText()=='[ICON_GOLD]','Literal name changed')
local literalNameJson=json(snap())
replaceName('%')
check(node(snap().tree,'SaveButton').disabled and env.ZeroSisUi.DispatchKeyDown(13) and #requests==0,'Invalid name Enter submitted save')
for _,value in ipairs({0,0x1F,0x7F,0x85,0xD800,0xDFFF,0x110000,-1,1.5}) do
 check(not env.ZeroSisUi.DispatchTextInput(value),'Invalid scalar accepted')
end
replaceName('검증 저장')
local named=snap();local namedJson=json(named)
check(env.ZeroSisUi.DispatchKeyDown(13),'Original Enter callback was not invoked')
check(#requests==2 and requests[1].kind=='Save' and requests[1].name=='검증 저장' and requests[2].kind=='Close','Save/Close order changed')
local closed=snap();local closedJson=json(closed)
check(not closed.active and closed.timerSemaphore==0 and not closed.saveMenu.textInputEnabled,'Saved child did not release focus')
check(closed.saveMenu.focusEpoch>named.saveMenu.focusEpoch and closed.saveMenu.textInputFocusToken==0 and
 env.ZeroSisUi.GetTextInputFocusToken()==0,'Child close retained stale editor lifetime')
check(not env.ZeroSisUi.DispatchTextInput(0xAC00) and not env.ZeroSisUi.DispatchLeftClick(rows[1]),'Closed child accepted stale input')
env.ZeroSisUi.CloseSaveMenu();check(#requests==2,'Repeated host close requeued child close')
now=now+1;env.ZeroSisUi.OpenSaveMenu()
check(env.ZeroSisUi.GetTextInputFocusToken()>closed.saveMenu.focusEpoch,'Reopened child reused the prior editor token')
check(env.ZeroSisUi.DispatchKeyDown(27),'Original Escape failed')
check(#requests==3 and requests[3].kind=='Close' and timerChanges==0,'Cancel submitted save or touched parent timer')
check(json(opened)==openedJson and json(named)==namedJson and json(closed)==closedJson,'Captured snapshots mutated')
return json({status='PASS_ORIGINAL_SAVE_MENU_COMPONENT',checks=checks,nestedMapRequests=mapOpenRequests,
 nativeGameVerified=false,archiveWrites=0,timerChanges=timerChanges,
 enumBindingCalls=enumCalls,
 openedSnapshotJson=openedJson,namedSnapshotJson=namedJson,closedSnapshotJson=closedJson,
 longNameSnapshotJson=longNameJson,longHomeSnapshotJson=longHomeJson,literalNameSnapshotJson=literalNameJson})
'''


def sdk_game_types() -> dict:
    path = PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h"
    source = path.read_text(encoding="utf-8-sig")
    declaration = re.search(r"enum\s+GameTypes\s*\{(.*?)\};", source, re.S)
    if declaration is None:
        raise ValueError("Actual SDK GameTypes declaration is missing")
    body = re.sub(r"//[^\n]*", "", declaration.group(1))
    values, last = {}, -1
    for field in body.split(','):
        if not field.strip():
            continue
        item = re.fullmatch(r"\s*(GAME_[A-Z_]+)(?:\s*=\s*(-?\d+))?\s*", field)
        if item is None:
            raise ValueError("Actual SDK GameTypes field cannot be parsed")
        last = int(item.group(2)) if item.group(2) is not None else last + 1
        values[item.group(1)] = last
    if set(values) != {"GAME_TYPE_NONE", "GAME_SINGLE_PLAYER", "GAME_NETWORK_MULTIPLAYER",
                       "GAME_HOTSEAT_MULTIPLAYER", "GAME_EMAIL_MULTIPLAYER"}:
        raise ValueError("Actual SDK GameTypes field inventory changed")
    return values


def verify_component(*, include_snapshot: bool = False, enum_fixture: str = "exact") -> dict:
    if enum_fixture not in ("exact", "missing", "non_table", "wrong_value", "missing_field", "unsupported_header"):
        raise ValueError("Unknown native enum fixture")
    game_types = sdk_game_types()
    paths = {
        "scene": PROJECT / "Source/Host/UiScene.lua",
        "input": PROJECT / "Source/Presentation/UiPresentationInput.lua",
        "stock": GAME / SAVE_MENU_LUA,
        "InstanceManager": GAME / "Assets/UI/InstanceManager.lua",
        "IconSupport": GAME / "Assets/UI/IconSupport.lua",
        "SupportFunctions": GAME / "Assets/UI/SupportFunctions.lua",
        "UniqueBonuses": GAME / UNIQUE_BONUSES_LUA,
        "InfoTooltipInclude": GAME / "Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua",
        "FLuaVector": GAME / "Assets/Gameplay/Lua/FLuaVector.lua",
        "MapUtilities": GAME / "Assets/Gameplay/Lua/MapUtilities.lua",
    }
    source = {name: path.read_text(encoding="utf-8-sig") for name, path in paths.items()}
    xml = GAME / SAVE_MENU_XML
    original = ET.parse(xml).getroot()
    tree = save_menu_control_tree(original)
    tree.update(contextName="SaveMenu", popupKind="SaveMenu")
    release = json.loads((PROJECT / "Play/EarlyAccess/release.json").read_text(encoding="utf-8-sig"))
    database = PROJECT / "Build/InteractiveGameRuntime" / release["runtime_id"] / "rules.db"
    names = ("Leaders", "Civilization_Leaders", "Civilizations", "PlayerColors", "Colors",
             "IconTextureAtlases", "Worlds", "HandicapInfos", "GameSpeeds", "Eras",
             "MapScripts", "Map_Sizes", "Maps", "GameOptions")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        tables = {name: [{k: v for k, v in dict(row).items() if v is not None}
                         for row in connection.execute('SELECT * FROM "' + name + '"')]
                  for name in names}
    civilization = next(row for row in tables["Civilizations"] if row["Type"] == "CIVILIZATION_ROME")
    lock_mods = next(row["ID"] for row in tables["GameOptions"] if row["Type"] == "GAMEOPTION_LOCK_MODS")
    current = dict(PlayerCivilization=civilization["ID"], GameSpeed=2, StartEra=0,
                   TurnNumber=1, Difficulty=3, WorldSize=3,
                   MapScript="Assets/Maps/Continents.lua", LeaderName="",
                   CivilizationName="", CurrentEra=0, GameType=game_types["GAME_SINGLE_PLAYER"])
    if enum_fixture == "unsupported_header":
        current["GameType"] = game_types["GAME_NETWORK_MULTIPLAYER"]
    tags = sorted(set(re.findall(r"TXT_KEY_[A-Za-z0-9_]+", "\n".join(source.values()) +
                                 ET.tostring(original, encoding="unicode") + json.dumps(tables))))
    locale = {}
    localization = database.with_name("localization.db")
    with closing(sqlite3.connect(localization.as_uri() + "?mode=ro", uri=True)) as connection:
        for language in ("en_US", "ko_KR"):
            for offset in range(0, len(tags), 500):
                batch = tags[offset:offset + 500]
                locale.update(connection.execute(
                    "SELECT Tag,Text FROM LocalizedText WHERE Language=? AND Tag IN (" +
                    ",".join("?" for _ in batch) + ")", [language, *batch]))
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest()
              for name, path in {**paths, "xml": xml}.items()}
    inline = json.loads((PROJECT / "evidence/ui_popup/assets/inline_icons.json").read_text(encoding="utf-8"))["icons"]
    with small_source_directory() as temporary:
        styles = production_style_defaults(temporary, tree)
        tree.update(styleDefaults=styles["controls"], styleDefaultsSource=styles["source"],
                    styleDefaultsPolicy=styles["policy"])
        tree["fontMetrics"] = production_font_metrics(tree, inline)
        data = dict(tables=tables, locale=locale, current=current, lockMods=lock_mods,
                    gameTypes=game_types, enumFixture=enum_fixture,
                    savePath=r"C:\owned\session\기존 저장.zssave",
                    unknownPath=r"C:\owned\session\old-autosave.zssave")
        result = execute_lua(HARNESS.replace("@@SOURCES@@", lua_value(source))
                             .replace("@@LAYOUT@@", lua_value(tree))
                             .replace("@@DATA@@", lua_value(data)))
    for name, path in {**paths, "xml": xml}.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != before[name]:
            raise AssertionError("Source changed during SaveMenu component: " + name)
    for old, new in (("openedSnapshotJson", "opened_snapshot"),
                     ("namedSnapshotJson", "named_snapshot"), ("closedSnapshotJson", "closed_snapshot"),
                     ("longNameSnapshotJson", "long_name_snapshot"),
                     ("longHomeSnapshotJson", "long_home_snapshot"),
                     ("literalNameSnapshotJson", "literal_name_snapshot")):
        value = json.loads(result.pop(old))
        if include_snapshot:
            result[new] = value
    result["source_sha256"] = before
    result["fixture_rules_db"] = str(database)
    result["fixture_localization_db"] = str(localization)
    result["temporary_styles_removed"] = not temporary.exists()
    return result


if __name__ == "__main__":
    result = verify_component()
    print(json.dumps({key: result[key] for key in ("status", "checks", "nativeGameVerified",
                                                  "archiveWrites", "timerChanges", "temporary_styles_removed")}))
