"""Run the complete original LoadMenu and includes in an existing Lua 5.1 VM.

SDK/catalog/locale operations below are explicit fixtures backed by the engine's
bundled rules/localization dictionaries. They do not prove the C++ bindings,
GameCore, retail saves, a native window, or the deferred fresh-session restore.
Only a guarded temporary Styles.xml copy is created and removed.
"""
from __future__ import annotations

from contextlib import closing
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import sys
import traceback
import uuid
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from economic_overview_scene import execute_lua
from game_menu_scene import HARNESS as GAME_MENU_HARNESS
from game_menu_ui_assets import small_source_directory
from save_menu_scene import sdk_game_types
from civ5_ui_assets import UiAssets
from prepare_ui_popup_assets import (
    GAME, LOAD_MENU_LUA, LOAD_MENU_XML, UNIQUE_BONUSES_LUA,
    attach_load_menu_control_defaults, load_menu_check_defaults,
    load_menu_control_tree, lua_value, production_font_metrics, production_style_defaults,
)

SCENE_SHA256 = "92620dacc22fdcf640efbffb06eb7b4c78a93ecd9f8a3436d4fd7d2bcb76a520"
LUA_SHA256 = "4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944"

HARNESS = GAME_MENU_HARNESS[:GAME_MENU_HARNESS.index("local now,owner,turn=")] + r'''
local phase='bootstrap'
local function exercise()
local now,timerChanges,cloudQueries,comparisons=0,0,0,0
local requests,trace,headerQueries,mapQueries={},{},{},{}
local cursor,lastDlc,lastMods=0,nil,nil
local available={}
for _,row in ipairs(data.files) do available[row.path]=row.known end
local current=data.current
local env=setmetatable({ZeroSisUiLayout=layout,GameInfo=info,
 Game={Rand=function() return 0 end,GetActivePlayer=function() return 0 end,
  GetGameTurn=function() return 1 end,GetElapsedGameTurns=function() return 1 end,
  GetTimeString=function() return '4000 BC' end,IsGameMultiPlayer=function() return false end,
  IsNetworkMultiPlayer=function() return false end},
 Players={[0]={GetCurrentEra=function() return current.CurrentEra end}},
 InterfaceModeTypes={INTERFACEMODE_SELECTION=0}}, {__index=_G})
env._G=env
local function run(text,name)
 local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
end
env.include=function(name) return run(assert(source[name],'Missing original include '..name),name) end
local function rowFor(path)
 check(type(path)=='string','Catalog fixture requires a string path')
 for _,row in ipairs(data.files) do if row.path==path then return row end end
 error('Foreign catalog path rejected: '..tostring(path))
end
env.ZeroSisUiNative=function(op,...)
 if op=='loadMenuDeleteSupported' then return false end
 if op=='uiFrameTime' then return now end
 if op=='screenSize' then return 1920,1080 end
 if op=='snapshotJson' then local value,marker=...;arrayTypes[marker]=true;return captured(value) end
 if op=='randomSeed' then return 17 end
 if op=='locale' then
  local key=...;local args={select(2,...)}
  local value=localized(key):gsub('{%s*(TXT_KEY_[%w_]+)%s*:%s*(%a+)%s*}',function(tag,style)
   return assert(({upper=string.upper,lower=string.lower})[style],'Unmodeled case modifier')(localized(tag))
  end):gsub('{%s*(TXT_KEY_[%w_]+)%s*}',localized)
  value=value:gsub('{(%d+)_[%w_]+}',function(index) return localized(assert(args[tonumber(index)],'Missing format argument')) end)
  assert(not value:find('[{}]'),'Unmodeled original locale format: '..value);return value
 end
 if op=='localeLength' then return #unicodeChars(...) end
 if op=='localeUpper' then return string.upper(...) end
 if op=='localeLower' then return string.lower(...) end
 if op=='localeSubstring' then local s,a,n=...;return table.concat(unicodeChars(s),'',a,a+n-1) end
 if op=='localeCompare' then local a,b=...;return a==b and 0 or a<b and -1 or 1 end
 if op=='localeHasTextKey' then check(select('#',...)==1,'HasTextKey arity changed');return data.locale[(...)]~=nil end
 if op=='noBasicHelp' then return false end
 if op=='civilization' then return current.PlayerCivilization end
 if op=='playerColor' then return 0 end
 if op=='timer' then timerChanges=timerChanges+1;error('Original child acquired its parent timer') end
 if op=='loadMenuGameTypes' then check(select('#',...)==0,'GameTypes arity changed');return captured(data.gameTypes) end
 if op=='loadMenuInGameView' then check(select('#',...)==0,'InGameView arity changed');return true end
 if op=='loadMenuCloudSaves' then check(select('#',...)==0,'Cloud inventory arity changed');cloudQueries=cloudQueries+1;return {} end
 if op=='loadMenuFiles' then
  check(select('#',...)==0,'Catalog arity changed');local files={}
  for _,row in ipairs(data.files) do files[#files+1]=row.path end
  return files
 end
 if op=='loadMenuHeader' then
  check(select('#',...)==1,'Header arity changed');local row=rowFor(...)
  headerQueries[#headerQueries+1]=row.path;return row.known and captured(current) or nil
 end
 if op=='loadMenuMapPreview' then
  check(select('#',...)==1,'Map-preview arity changed')
  local path=...;check(type(path)=='string','Map-preview path is not text')
  local identity=path:gsub('\\','/'):lower()
  local listed=false
  for _,row in ipairs(data.files) do if row.known and identity==current.MapScript:gsub('\\','/'):lower() then listed=true end end
  check(listed and identity:sub(-4)=='.lua','Foreign or WorldBuilder map escaped the immutable header fixture')
  mapQueries[#mapQueries+1]=path;return nil
 end
 if op=='loadMenuModificationTime' then check(select('#',...)==1,'Display-time arity changed');return rowFor(...).display end
 if op=='loadMenuModificationTimeRaw' then check(select('#',...)==1,'Raw-time arity changed');local row=rowFor(...);return row.high,row.low end
 if op=='loadMenuCompareFileTime' then
  check(select('#',...)==4,'FILETIME comparison arity changed');local ah,al,bh,bl=...
  for _,value in ipairs({ah,al,bh,bl}) do check(type(value)=='number' and value>=0 and value<=4294967295 and value==math.floor(value),'Invalid raw word reached native fixture') end
  comparisons=comparisons+1;if ah~=bh then return ah>bh and 1 or -1 end
  return al==bl and 0 or al>bl and 1 or -1
 end
 if op=='loadMenuCanLoad' then check(select('#',...)==1,'Loadability arity changed');local row=rowFor(...);return available[row.path] and 0 or 5 end
 if op=='loadMenuRequiredContent' then
  check(select('#',...)==1 and rowFor(...).known,'Unknown header claimed content requirements')
  lastDlc,lastMods={},{};return lastDlc,lastMods
 end
 if op=='loadMenuCursor' then
  check(select('#',...)==1 and (...)==1 and cursor==0,'Original wait cursor sequence changed')
  trace[#trace+1]='Cursor';cursor=1;return 0
 end
 if op=='loadMenuLoad' then
  check(select('#',...)==1,'Load event arity changed');local row=rowFor(...)
  check(row.known and available[row.path] and cursor==1 and env.g_FileList[env.g_iSelected]==row.path,
   'Load event escaped its selected known compatible local file')
  check(not env.ContextPtr:IsHidden() and not env.__componentState(env.Controls.StartButton).disabled,
   'Original load event did not precede disable/dequeue')
  trace[#trace+1]='Load';requests[#requests+1]={kind='Load',path=row.path};return
 end
 if op=='loadMenuClose' then
  check(select('#',...)==0,'Close event arity changed')
  check(env.ContextPtr:IsHidden(),'Original close preceded dequeue')
  if #requests>0 then check(requests[#requests].kind=='Load' and env.__componentState(env.Controls.StartButton).disabled,
   'Original dequeue did not follow load then button disable') end
  trace[#trace+1]='Close';requests[#requests+1]={kind='Close'};return
 end
 error('Unexpected native operation in full LoadMenu fixture: '..tostring(op))
end
run(source.scene..'\n'..source.input..[[
__componentKey=function(handle) return state(handle).key end
__componentState=function(handle) return state(handle) end
]],'retained-complete-LoadMenu.lua')
phase='unchanged-original-script'
run(source.stock,'original-complete-LoadMenu.lua')
local ui=env.ZeroSisUi
local function key(handle) return env.__componentKey(handle) end
local function node(tree,id)
 if tree.id==id then return tree end
 for _,child in ipairs(tree.children) do local result=node(child,id);if result then return result end end
end
local function matchingNode(tree,predicate)
 if predicate(tree) then return tree end
 for _,child in ipairs(tree.children) do local result=matchingNode(child,predicate);if result then return result end end
end
local function snap() return ui.Snapshot() end
local function target(value)
 for _,item in ipairs(ui.GetInputTargets(env.Mouse.eLClick)) do if item.key==value and item.event==env.Mouse.eLClick then return item end end
end
local function clickHandle(handle) check(target(key(handle))~=nil and ui.DispatchLeftClick(key(handle)),'Actual retained click failed') end
local function clickId(id) clickHandle(env.Controls[id]) end
local function disabled(id) return env.__componentState(env.Controls[id]).disabled end
local function rejects(fn,label) check(not pcall(fn),'Unsupported or foreign request succeeded: '..label) end
check(#ui.GetInputTargets(env.Mouse.eLClick)==0,'Inactive complete menu exposed input')
phase='original-show-handler'
ui.OpenLoadMenu()
local opened=snap();local openedJson=json(opened)
check(opened.active and opened.timerSemaphore==0 and opened.loadMenu.controlOnly==false and
 opened.loadMenu.sourceApisBound==true and opened.loadMenu.nativeVmConnected==false and
 opened.loadMenu.runtimeIntegrationVerified==false and opened.loadMenu.retailBackendVerified==false and
 opened.loadMenu.retailLayoutVerified==false and
 opened.loadMenu.frontendStatePolicy=='OWNED_LOCAL_INGAME_VIEW_OPAQUE_IDENTITY_NO_RETAIL_NUMERIC_ENUM_CLAIM' and
 table.concat(opened.loadMenu.unsupportedActions,',')=='cloud,delete,automatic-save-filter',
 'Complete original Lua was confused with native backend proof')
check(#env.g_FileList==#data.files and env.g_iSelected==-1 and disabled('StartButton'),
 'Original show handler fabricated selection or changed its catalog')
check(cloudQueries==1 and next(env.g_CloudSaves)==nil,'Original local show did not query explicit empty cloud inventory')
for _,id in ipairs({'Delete','Yes','AutoCheck','CloudCheck'}) do
 check(disabled(id) and target(key(env.Controls[id]))==nil,'Unsupported operation remained live: '..id)
end
check(node(opened.tree,'AutoCheck').width==32 and node(opened.tree,'AutoCheck').height==32,
 'Original omitted-size checkbox lost its disclosed 32px candidate')
rejects(function() env.UI.DeleteSavedGame(data.foreign) end,'delete')
rejects(function() env.Steam.GetCloudSaveFileName(1) end,'cloud filename')
rejects(function() env.Modding.CanLoadCloudSave(1) end,'cloud compatibility')
rejects(function() env.PreGame.SetLoadFileName(data.foreign) end,'multiplayer load handoff')
rejects(function() env.UI.SaveFileList({},env.GameTypes.GAME_SINGLE_PLAYER,true,true) end,'automatic-save filter')
rejects(function() env.PreGame.GetFileHeader(data.foreign) end,'foreign header')
rejects(function() env.PreGame.GetFileHeader(data.foreign,true) end,'cloud header option')
rejects(function() env.UI.GetMapPreview('Assets/Maps/NotInOwnedHeaders.lua') end,'foreign map preview')
check(env.Locale.HasTextKey('TXT_KEY_MISC_UNKNOWN') and not env.Locale.HasTextKey('NO_SUCH_FIXTURE_DICTIONARY_KEY'),
 'Actual Locale.HasTextKey adapter did not forward its fixture dictionary result')
local beforeInvalid=comparisons
for _,value in ipairs({-1,4294967296,0.5,math.huge,-math.huge,0/0,'1'}) do
 rejects(function() env.UI.CompareFileTime(value,0,0,0) end,'invalid FILETIME word')
end
rejects(function() env.UI.CompareFileTime(nil,0,0,0) end,'nil FILETIME word')
check(comparisons==beforeInvalid,'Invalid raw word reached native comparison')
check(env.UI.CompareFileTime(4294967295,4294967295,2147483648,0)==1 and
 env.UI.CompareFileTime(2097152,0,2097152,1)==-1 and env.UI.CompareFileTime(2097152,1,2097152,1)==0,
 'Unsigned halves or low-bit order above combined 2^53 changed')
local selectedJson=''
if #data.files==0 then
 phase='empty-catalog-back'
 check(env.Controls.NoGames:IsHidden()==false,'Empty original catalog lost its no-games state')
 clickId('BackButton');check(#requests==1 and requests[1].kind=='Close','Empty menu Back published a load')
elseif data.case=='unknown' then
 phase='unknown-header-selection'
 clickHandle(env.g_InstanceList[1].Button)
 check(env.g_iSelected==1 and env.PreGame.GetFileHeader(data.files[1].path)==nil and disabled('StartButton'),
  'Unknown original file acquired a fabricated preview or enabled Start')
 rejects(function() env.Events.PlayerChoseToLoadGame(data.files[1].path) end,'unknown header load')
 check(#requests==0,'Unknown header published a native load')
 check(ui.DispatchKeyDown(env.Keys.VK_ESCAPE),'Unknown menu rejected original Escape')
else
 phase='known-catalog-original-sorting'
 local stack=node(snap().tree,'LoadFileButtonStack')
 check(stack.children[1].key==key(env.g_InstanceList[2].InstanceRoot) and
  stack.children[2].key==key(env.g_InstanceList[1].InstanceRoot),
  'Original newest-first sort lost the one-tick high/low distinction')
 local function selectSort(label,comparator,expected)
  clickHandle(env.Controls.SortByPullDown:GetButton())
  local value=snap();local owner=key(env.Controls.SortByPullDown)
  local popup=assert(matchingNode(value.tree,function(item)
   return item.ownerPullDownKey==owner and item.originalDataKind=='GridData' end),'Original sort popup is missing')
  local entry=assert(matchingNode(popup,function(item)
   return item.kind=='GridButton' and item.id=='Button' and item.text==label end),'Original sort option is missing')
  check(target(entry.key)~=nil and ui.DispatchLeftClick(entry.key),'Original sort option was not selectable')
  local sorted=node(snap().tree,'LoadFileButtonStack')
  for index,originalIndex in ipairs(expected) do
   check(sorted.children[index].key==key(env.g_InstanceList[originalIndex].InstanceRoot),'Original sort callback produced wrong row order')
  end
  check(env.g_CurrentSort==comparator and env.Controls.SortByPullDown:GetButton():GetText()==label,
   'Original sort callback did not update comparator and caption')
  check(target(entry.key)==nil and not ui.DispatchLeftClick(entry.key),'Closed original sort option retained stale input')
 end
 selectSort(data.locale.TXT_KEY_SORTBY_NAME,env.SortByName,{1,3,2})
 selectSort(data.locale.TXT_KEY_SORTBY_LASTMODIFIED,env.SortByLastModified,{2,1,3})
 local unknown=data.files[3]
 local high,low=env.UI.GetSavedGameModificationTimeRaw(unknown.path)
 check(high==2097151 and low==4294967295,'Actual raw-time adapter truncated an unsigned low half')
 clickHandle(env.g_InstanceList[3].Button)
 check(disabled('StartButton') and env.PreGame.GetFileHeader(unknown.path)==nil,'Listed unknown preview became loadable')
 phase='known-header-selection'
 clickHandle(env.g_InstanceList[1].Button)
 check(not disabled('StartButton') and env.g_SavedGameDLCRequired==lastDlc and env.g_SavedGameModsRequired==lastMods and
 lastDlc~=lastMods and next(lastDlc)==nil and next(lastMods)==nil,'Original requirements did not retain DLC then mods return identities')
 local observed=env.PreGame.GetFileHeader(data.files[1].path)
 check(observed.TurnNumber==current.TurnNumber and observed.LeaderName==current.LeaderName and
 observed.CivilizationName==current.CivilizationName and env.Controls.TimeSaved:GetText()==data.files[1].display,
  'Original known preview did not display its observed header/time')
 local selected=snap();selectedJson=json(selected)
 phase='explicit-modal-visibility-fixtures'
 -- Explicit modal fixtures exercise owner barriers without pretending that
 -- this no-additional-content profile has real external package requirements.
 local savedKey=key(env.g_InstanceList[1].Button)
 env.Controls.DeleteConfirm:SetHide(true);env.Controls.DeleteConfirm:SetHide(false)
 check(target(savedKey)==nil and not ui.DispatchLeftClick(savedKey),'Delete confirmation leaked file-row input')
 clickId('No');check(env.Controls.DeleteConfirm:IsHidden(),'Original No did not dismiss its confirmation')
 env.Controls.ReferencedPackagesStack:CalculateSize();env.Controls.ReferencedPackagesScrollPanel:CalculateInternalSize()
 env.Controls.ReferencedPackagesWindow:SetHide(false)
 check(target(savedKey)==nil and not ui.DispatchLeftClick(savedKey),'Referenced package window leaked file-row input')
 clickId('CloseReferencedPackagesButton');check(env.Controls.ReferencedPackagesWindow:IsHidden(),'Original package Close did not dismiss')
 phase='live-compatibility-fixture'
 available[data.files[1].path]=false
 clickHandle(env.g_InstanceList[1].Button)
 check(disabled('StartButton') and #requests==0,'Incompatible current file remained loadable')
 rejects(function() env.Events.PlayerChoseToLoadGame(data.files[1].path) end,'stale compatibility load')
 available[data.files[1].path]=true;clickHandle(env.g_InstanceList[1].Button)
 clickHandle(env.Controls.SortByPullDown:GetButton())
 check(ui.DispatchKeyDown(env.Keys.VK_ESCAPE) and snap().active and #requests==0,'First Escape did not only collapse PullDown')
 clickId('BackButton');check(#requests==1 and requests[1].kind=='Close','Cancel published a load')
 check(json(opened)==openedJson and json(selected)==selectedJson,'Earlier detached captures changed after later UI actions')
 requests,trace={},{};cursor=0;ui.OpenLoadMenu()
 phase='reopened-original-load-sequence'
 check(cloudQueries==2 and env.g_iSelected==-1,'Reopen skipped the original refresh/reset lifecycle')
 clickHandle(env.g_InstanceList[2].Button)
 clickId('StartButton')
 check(#requests==2 and requests[1].kind=='Load' and requests[1].path==data.files[2].path and requests[2].kind=='Close' and
 table.concat(trace,',')=='Cursor,Load,Close','Original single-player deferred cursor/load/disable/dequeue sequence changed')
end
phase='final-closed-state'
local closed=snap()
check(not closed.active and closed.timerSemaphore==0 and #ui.GetInputTargets(env.Mouse.eLClick)==0,
 'Original closed child retained input or took the parent timer')
check(json(opened)==openedJson,'Opening snapshot mutated after close')
return json({status='PASS_COMPLETE_ORIGINAL_LOAD_MENU_LUA_FIXTURE',case=data.case,checks=checks,
 sdkNativeBindingVerified=false,nativeGameVerified=false,retailSaveVerified=false,archiveWrites=0,timerChanges=timerChanges,
 cloudQueries=cloudQueries,compareCalls=comparisons,headerQueries=headerQueries,mapPreviewFixtureQueries=mapQueries,
 requiredContentReturnOrderFixtureVerified=data.case=='known',modalVisibilityFixture=data.case=='known',
 openedSnapshotJson=openedJson,selectedSnapshotJson=selectedJson,closedSnapshotJson=json(closed)})
end
local ok,result=xpcall(exercise,function(message)
 return 'Full LoadMenu fixture case='..data.case..' phase='..phase..': '..tostring(message)
end)
assert(ok,result)
return result
'''


def suppress_fault_ui():
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.SetErrorMode.argtypes = [ctypes.c_uint32]
    kernel.SetErrorMode.restype = ctypes.c_uint32
    kernel.GetErrorMode.argtypes = []
    kernel.GetErrorMode.restype = ctypes.c_uint32
    kernel.GetCurrentProcess.argtypes = []
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.SetErrorMode(kernel.GetErrorMode() | 32771)
    kernel.WerSetFlags.argtypes = [ctypes.c_uint32]
    kernel.WerSetFlags.restype = ctypes.c_long
    kernel.WerGetFlags.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
    kernel.WerGetFlags.restype = ctypes.c_long
    flags = ctypes.c_uint32()
    if (kernel.GetErrorMode() & 32771 != 32771 or kernel.WerSetFlags(32) < 0 or
            kernel.WerGetFlags(kernel.GetCurrentProcess(), ctypes.byref(flags)) < 0 or not flags.value & 32):
        raise RuntimeError("Own Python process fault UI suppression failed")
    return {"own_process_only": True, "error_mode_mask": 32771, "wer_flags": flags.value}


def verify_component(*, include_snapshot: bool = False) -> dict:
    fault = suppress_fault_ui()
    paths = {
        "scene": PROJECT / "Source/Host/UiScene.lua", "input": PROJECT / "Source/Presentation/UiPresentationInput.lua",
        "stock": GAME / LOAD_MENU_LUA, "xml": GAME / LOAD_MENU_XML,
        "InstanceManager": GAME / "Assets/UI/InstanceManager.lua", "IconSupport": GAME / "Assets/UI/IconSupport.lua",
        "SupportFunctions": GAME / "Assets/UI/SupportFunctions.lua", "UniqueBonuses": GAME / UNIQUE_BONUSES_LUA,
        "InfoTooltipInclude": GAME / "Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua",
        "FLuaVector": GAME / "Assets/Gameplay/Lua/FLuaVector.lua", "MapUtilities": GAME / "Assets/Gameplay/Lua/MapUtilities.lua",
        "harness": Path(__file__).resolve(), "preparer": PROJECT / "tools/prepare_ui_popup_assets.py",
        "native_context_source_not_executed": PROJECT / "Source/Host/UiPopupContext.h",
        "native_load_contract_not_executed": PROJECT / "Source/Host/UiLoadMenuContract.h",
        "lua": PROJECT / "Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll",
    }
    source = {name: path.read_text(encoding="utf-8-sig") for name, path in paths.items()
              if name in {"scene", "input", "stock", "InstanceManager", "IconSupport", "SupportFunctions",
                          "UniqueBonuses", "InfoTooltipInclude", "FLuaVector", "MapUtilities"}}
    release = json.loads((PROJECT / "Play/EarlyAccess/release.json").read_text(encoding="utf-8-sig"))
    database = PROJECT / "Build/InteractiveGameRuntime" / release["runtime_id"] / "rules.db"
    localization = database.with_name("localization.db")
    paths.update(rules_db=database, localization_db=localization)
    before = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    if before["scene"] != SCENE_SHA256:
        raise AssertionError("Production LoadMenu source differs from the agreed freeze")
    provider = paths["lua"].read_bytes()
    pe_offset = int.from_bytes(provider[0x3C:0x40], "little")
    if (before["lua"] != LUA_SHA256 or provider[:2] != b"MZ" or
            provider[pe_offset:pe_offset + 4] != b"PE\0\0" or
            int.from_bytes(provider[pe_offset + 4:pe_offset + 6], "little") != 0x8664 or
            int.from_bytes(provider[pe_offset + 24:pe_offset + 26], "little") != 0x20B):
        raise AssertionError("Existing approved Lua provider is not the expected x64 PE32+ image")
    provider_metadata = {"path": str(paths["lua"]), "bytes": len(provider), "sha256": before["lua"],
                         "machine": "AMD64", "format": "PE32+", "reused_existing_provider": True}
    names = ("Leaders", "Civilization_Leaders", "Civilizations", "PlayerColors", "Colors", "IconTextureAtlases",
             "Worlds", "HandicapInfos", "GameSpeeds", "Eras", "MapScripts", "Map_Sizes", "Maps", "GameOptions")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        tables = {name: [{key: value for key, value in dict(row).items() if value is not None}
                         for row in connection.execute('SELECT * FROM "' + name + '"')] for name in names}
    original = ET.parse(paths["xml"]).getroot()
    tree = load_menu_control_tree(original)
    tree.update(contextName="LoadMenu", popupKind="LoadMenu")
    civilization = next(row for row in tables["Civilizations"] if row["Type"] == "CIVILIZATION_ROME")
    current = dict(PlayerCivilization=civilization["ID"], GameSpeed=2, StartEra=0, TurnNumber=7,
                   Difficulty=3, WorldSize=3, MapScript="Assets/Maps/Continents.lua", LeaderName="저장된 지도자",
                   CivilizationName="저장된 문명", CurrentEra=0, GameType=sdk_game_types()["GAME_SINGLE_PLAYER"])
    tags = sorted(set(re.findall(r"TXT_KEY_[A-Za-z0-9_]+", "\n".join(source.values()) +
                                 ET.tostring(original, encoding="unicode") + json.dumps(tables))))
    locale = {}
    with closing(sqlite3.connect(localization.as_uri() + "?mode=ro", uri=True)) as connection:
        for language in ("en_US", "ko_KR"):
            for offset in range(0, len(tags), 500):
                batch = tags[offset:offset + 500]
                locale.update(connection.execute("SELECT Tag,Text FROM LocalizedText WHERE Language=? AND Tag IN (" +
                                                 ",".join("?" for _ in batch) + ")", [language, *batch]))
    inline = json.loads((PROJECT / "evidence/ui_popup/assets/inline_icons.json").read_text(encoding="utf-8"))["icons"]
    files = [dict(path=r"C:\owned\session\Alpha.zssave", known=True, high=2097152, low=0, display="2026-10-15 01:00:00"),
             dict(path=r"C:\owned\session\Zulu.zssave", known=True, high=2097152, low=1, display="2026-10-15 01:00:00"),
             dict(path=r"C:\owned\session\Unknown.zssave", known=False, high=2097151, low=4294967295, display="2026-10-15 00:59:59")]
    results, captures, temporary_files = [], {}, []
    temporary = None
    case = None
    try:
        with small_source_directory() as temporary:
            styles = production_style_defaults(temporary, tree)
            tree.update(styleDefaults=styles["controls"], styleDefaultsSource=styles["source"], styleDefaultsPolicy=styles["policy"])
            attach_load_menu_control_defaults(tree, load_menu_check_defaults(temporary, UiAssets(GAME)))
            tree["fontMetrics"] = production_font_metrics(tree, inline)
            for path in sorted(temporary.rglob("*")):
                if path.is_file():
                    metadata = path.stat()
                    temporary_files.append({"path": str(path), "bytes": metadata.st_size,
                                            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                                            "device": metadata.st_dev, "file_id": metadata.st_ino})
            for case, rows in (("empty", []), ("unknown", [files[2]]), ("known", files)):
                data = dict(tables=tables, locale=locale, current=current, gameTypes=sdk_game_types(),
                            case=case, files=rows, foreign=r"C:\foreign\not-owned.zssave")
                result = execute_lua(HARNESS.replace("@@SOURCES@@", lua_value(source)).replace("@@LAYOUT@@", lua_value(tree))
                                     .replace("@@DATA@@", lua_value(data)))
                case_captures = {}
                for field in ("openedSnapshotJson", "selectedSnapshotJson", "closedSnapshotJson"):
                    raw = result.pop(field)
                    if raw:
                        case_captures[field] = json.loads(raw)
                captures[case] = case_captures
                results.append(result)
    except Exception as error:
        error.load_menu_fixture = {
            "case": case, "completed_cases": [{"case": row["case"], "checks": row["checks"]} for row in results],
            "temporary_styles_path": str(temporary) if temporary is not None else None,
            "temporary_styles_removed": temporary is not None and not temporary.exists(),
            "fault_ui_suppression": fault, "source_sha256": before,
            "temporary_cleanup": [{**item, "result": "REMOVED_ABSENT" if not Path(item["path"]).exists() else "PRESENT"}
                                  for item in temporary_files],
        }
        raise
    finally:
        changed = [name for name, path in paths.items() if hashlib.sha256(path.read_bytes()).hexdigest() != before[name]]
        if changed:
            raise AssertionError("Complete LoadMenu fixture changed input sources: " + ", ".join(changed))
    result = {"status": "PASS_COMPLETE_ORIGINAL_LOAD_MENU_LUA_FIXTURES", "checks": sum(row["checks"] for row in results),
              "cases": results, "source_sha256": before, "temporary_styles_removed": temporary is not None and not temporary.exists(),
              "fault_ui_suppression": fault, "native_sdk_binding_verified": False, "native_game_verified": False,
              "retail_save_verified": False, "archive_writes": 0, "lua_provider": provider_metadata,
              "source_bytes": {name: path.stat().st_size for name, path in paths.items()},
              "temporary_cleanup": [{**item, "result": "REMOVED_ABSENT" if not Path(item["path"]).exists() else "PRESENT"}
                                    for item in temporary_files]}
    if not result["temporary_styles_removed"] or any(item["result"] != "REMOVED_ABSENT" for item in result["temporary_cleanup"]):
        raise AssertionError("Complete LoadMenu test did not remove all of its temporary source copies")
    if include_snapshot:
        result["snapshots"] = captures
    return result


if __name__ == "__main__":
    evidence = PROJECT / "evidence/load_menu/native_handoff"
    try:
        result = verify_component()
    except Exception as error:
        attempt = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
        receipt = evidence / "scene_attempts" / attempt / "failure.json"
        receipt.parent.mkdir(parents=True, exist_ok=False)
        production = {"scene": PROJECT / "Source/Host/UiScene.lua",
                      "input": PROJECT / "Source/Presentation/UiPresentationInput.lua"}
        receipt.write_text(json.dumps({"status": "FAIL_COMPLETE_ORIGINAL_LOAD_MENU_LUA_FIXTURE",
            "error_type": type(error).__name__, "error": str(error), "traceback": traceback.format_exc(),
            "source_sha256": {key: hashlib.sha256(path.read_bytes()).hexdigest() for key, path in production.items()},
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "fixture": getattr(error, "load_menu_fixture", {}),
            "game_executed": False, "native_window_executed": False, "archive_writes": 0},
            ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"status": "FAIL", "error": str(error), "receipt": str(receipt)}, ensure_ascii=False))
        raise
    evidence.mkdir(parents=True, exist_ok=True)
    receipt = evidence / "scene.json"
    receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": result["checks"],
                      "cases": [{"case": row["case"], "checks": row["checks"]} for row in result["cases"]],
                      "temporary_styles_removed": result["temporary_styles_removed"],
                      "native_sdk_binding_verified": False, "native_game_verified": False,
                      "archive_writes": 0, "receipt": str(receipt)}, ensure_ascii=False))
