"""Exercise unchanged SaveMenu/LoadMenu deletion callbacks in a headless Lua VM.

Only the existing Lua 5.1 provider is loaded. Catalog eligibility, deletion and
tombstones are an independent in-memory mock service: no archive is created or
deleted and no Host, GameCore, HWND or retail user state is accessed.
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
from save_menu_scene import sdk_game_types
from civ5_ui_assets import UiAssets
from ui_pixel_scene import load_menu_controls_contract, save_menu_contract
from prepare_ui_popup_assets import (
    GAME, LOAD_MENU_LUA, LOAD_MENU_XML, SAVE_MENU_LUA, SAVE_MENU_XML,
    UNIQUE_BONUSES_LUA, attach_load_menu_control_defaults,
    load_menu_check_defaults, load_menu_control_tree, lua_value,
    production_font_metrics, production_style_defaults, save_menu_control_tree,
)

LUA_SHA256 = "4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944"

HARNESS = GAME_MENU_HARNESS[:GAME_MENU_HARNESS.index("local now,owner,turn=")] + r'''
local phase='bootstrap'
local function exercise()
local isSave=data.menu=='SaveMenu'
local prefix=isSave and 'saveMenu' or 'loadMenu'
local now,timerChanges,catalogQueries,capabilityQueries,eligibilityQueries=0,0,0,0,0
local deleted,available,deleteCalls,trace,captures={},{},{},{},{}
local current=data.current
local env=setmetatable({ZeroSisUiLayout=layout,GameInfo=info,
 Game={Rand=function() return 0 end,GetActivePlayer=function() return 0 end,
  GetGameTurn=function() return 1 end,GetElapsedGameTurns=function() return 1 end,
  GetTimeString=function() return '4000 BC' end,IsGameMultiPlayer=function() return false end,
  IsNetworkMultiPlayer=function() return false end},
 Players={[0]={GetCurrentEra=function() return current.CurrentEra end}},
 GameOptionTypes={GAMEOPTION_LOCK_MODS=data.lockMods},
 InterfaceModeTypes={INTERFACEMODE_SELECTION=0}}, {__index=_G})
env._G=env
local function run(text,name)
 local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
end
env.include=function(name) return run(assert(source[name],'Missing original include '..name),name) end
local function rowFor(path)
 check(type(path)=='string','Mock catalog requires an exact string path')
 for _,row in ipairs(data.files) do if row.path==path then return row end end
 error('Foreign mock catalog path: '..tostring(path))
end
for _,row in ipairs(data.files) do available[row.path]=row.known end
local function selectedPath()
 return isSave and env.g_SelectedEntry and env.g_SelectedEntry.FileName or
  not isSave and env.g_FileList[env.g_iSelected] or nil
end
local function allowed(path)
 local row=rowFor(path)
 return row.known and available[path] and not deleted[path]
end
env.ZeroSisUiNative=function(op,...)
 if op=='saveMenuOverwriteSupported' then return false end
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
  check(not value:find('[{}]'),'Unmodeled original locale format');return value
 end
 if op=='localeLength' then return #unicodeChars(...) end
 if op=='localeUpper' then return string.upper(...) end
 if op=='localeLower' then return string.lower(...) end
 if op=='localeSubstring' then local s,a,n=...;return table.concat(unicodeChars(s),'',a,a+n-1) end
 if op=='localeCompare' then local a,b=...;return a==b and 0 or a<b and -1 or 1 end
 if op=='localeHasTextKey' then return data.locale[(...)]~=nil end
 if op=='noBasicHelp' then return false end
 if op=='civilization' then return current.PlayerCivilization end
 if op=='playerColor' then return 0 end
 if op=='timer' then timerChanges=timerChanges+1;error('A child menu acquired its parent timer') end
 if op==prefix..'DeleteSupported' then
  check(select('#',...)==0,'Delete capability arity changed');capabilityQueries=capabilityQueries+1
  if data.case=='invalid-capability' then return 1 end
  return data.supported
 end
 if op==prefix..'CanDelete' then
  check(select('#',...)==1,'Delete eligibility arity changed');eligibilityQueries=eligibilityQueries+1
  if data.case=='invalid-eligibility' then return 1 end
  return allowed(...)
 end
 if op==prefix..'Delete' then
  check(select('#',...)==1,'Delete service arity changed');local path=...
  check(data.supported and allowed(path) and selectedPath()==path,
   'A non-owned, unknown, stale or different file reached the mock delete service')
  check(env.Controls.DeleteConfirm:IsHidden(),'Stock OnYes did not hide its confirmation before deletion')
  deleteCalls[#deleteCalls+1]=path;trace[#trace+1]='delete:'..path
  if data.case=='delete-error' then error('Mock delete failure before mutation') end
  if data.case=='delete-false' then return false end
  deleted[path]=true;return true
 end
 if op==prefix..'GameTypes' then return captured(data.gameTypes) end
 if op=='saveMenuCurrent' then return captured(current) end
 if op==prefix..'Files' then
  check(select('#',...)==0,'Catalog query arity changed');catalogQueries=catalogQueries+1
  trace[#trace+1]='files';local rows={}
  for _,row in ipairs(data.files) do if not deleted[row.path] then rows[#rows+1]=row.path end end
  return rows
 end
 if op==prefix..'Header' then local row=rowFor(...);return not deleted[row.path] and row.known and captured(current) or nil end
 if op==prefix..'ModificationTime' then return rowFor(...).display end
 if op=='saveMenuNameAvailable' then
  local name=...
  for _,row in ipairs(data.files) do
   if not deleted[row.path] and row.path:match('([^\\]+)%.zssave$')==name then return false end
  end
  return #unicodeChars(name)>0 and #unicodeChars(name)<=32
 end
 if op=='saveMenuSave' or op=='loadMenuLoad' then error('Deletion fixture attempted save/load gameplay') end
 if op==prefix..'Close' then check(env.ContextPtr:IsHidden(),'Close preceded original dequeue');return end
 if op=='gameMenuPreGame' then local key=...;check(key=='gameOption','Unexpected setup query');return 0 end
 if op=='gameMenuModPropertyContains' then return false end
 if op=='gameMenuMapPreview' or op=='loadMenuMapPreview' then return nil end
 if op=='loadMenuInGameView' then return true end
 if op=='loadMenuCloudSaves' then return {} end
 if op=='loadMenuCanLoad' then return rowFor(...).known and 0 or 5 end
 if op=='loadMenuRequiredContent' then return {},{} end
 if op=='loadMenuModificationTimeRaw' then local row=rowFor(...);return row.high,row.low end
 if op=='loadMenuCompareFileTime' then
  local ah,al,bh,bl=...;if ah~=bh then return ah>bh and 1 or -1 end
  return al==bl and 0 or al>bl and 1 or -1
 end
 error('Unexpected native operation in owned-delete fixture: '..tostring(op))
end
run(source.scene..'\n'..source.input..[[
__componentKey=function(handle) return state(handle).key end
__componentState=function(handle) return state(handle) end
]],'retained-owned-delete.lua')
run(source.stock,'unchanged-original-'..data.menu..'.lua')
local ui=env.ZeroSisUi
local function key(handle) return env.__componentKey(handle) end
local function target(targetKey,event)
 for _,value in ipairs(ui.GetInputTargets()) do
  if value.key==targetKey and value.event==(event or env.Mouse.eLClick) then return value end
 end
end
local function clickHandle(handle)
 local targetKey=key(handle);check(target(targetKey)~=nil,'Missing original click target')
 check(ui.DispatchLeftClick(targetKey),'Original click dispatch was rejected')
end
local function click(id) return clickHandle(env.Controls[id]) end
local function snapshot() return ui.Snapshot() end
local function observe(stage)
 local value=snapshot();if data.capture then captures[stage]=value end;return value
end
local function metadata(value) return value[isSave and 'saveMenu' or 'loadMenu'] end
local function rejects(fn,label)
 local ok=pcall(fn);check(not ok,'Expected fail-closed rejection: '..label)
end
local function countFiles()
 if isSave then return #env.g_SavedGames end
 return #env.g_FileList
end
local function findEntry(path)
 local rows=isSave and env.g_SavedGames or env.g_FileList
 for index,row in ipairs(rows) do
  if (isSave and row.FileName or row)==path then
   return isSave and row.Instance.Button or env.g_InstanceList[index].Button,index,row
  end
 end
 error('Missing listed fixture path '..path)
end
local function selectPath(path)
 local button=findEntry(path);clickHandle(button)
 check(selectedPath()==path,'Original selection chose a different file')
 return button
end
local function showDelete()
 click('Delete');check(not env.Controls.DeleteConfirm:IsHidden(),'Original OnDelete did not open confirmation')
 check(not env.Controls.Yes:IsDisabled(),'Eligible original confirmation has no Yes')
 check(metadata(observe('confirmation')).deleteConfirmationArmed,'Original Delete confirmation has no admitted path')
 check(not ui.DispatchLeftClick(key(env.Controls.Yes),env.Mouse.eRClick) and #deleteCalls==0,
  'Right-click acquired a destructive Yes dispatch')
 local barrier=assert(target(key(env.Controls.DeleteConfirm),'ConsumeMouse'),'Original confirmation backdrop lost mouse consumption')
 check(barrier.consumeMouse and barrier.bounds.x==0 and barrier.bounds.y==0 and
  barrier.bounds.width==1920 and barrier.bounds.height==1080,'Confirmation consumer does not cover the logical viewport')
end
local function finish()
 local value=observe('final')
 if isSave then ui.CloseSaveMenu() else ui.CloseLoadMenu() end
 local closed=observe('closed')
 check(not closed.active and #ui.GetInputTargets()==0 and closed.timerSemaphore==0,
  'Original close retained input or a child-owned timer')
 return json({status='PASS_ORIGINAL_OWNED_SAVE_DELETE_LUA_FIXTURE',menu=data.menu,case=data.case,checks=checks,
  capabilityQueries=capabilityQueries,eligibilityQueries=eligibilityQueries,catalogQueries=catalogQueries,
  deleteCalls=deleteCalls,trace=trace,remainingCount=countFiles(),timerChanges=timerChanges,
  metadata=metadata(value),snapshots=data.capture and captures or nil,
  originalLuaExecuted=true,deleteService='IN_MEMORY_MOCK_NO_FILESYSTEM_CALLS',
  realArchiveDeletes=0,nativeHostOrGameCoreExecuted=false,nativeWindowVerified=false})
end
phase='open-original-menu'
if isSave then ui.OpenSaveMenu() else ui.OpenLoadMenu() end
check(capabilityQueries==1,'Delete support was not bound exactly once')
check(countFiles()==#data.files,'Opening list differs from the independent mock catalog')
local opened=metadata(observe('opened'))
check(opened.localDeleteImplemented==true and opened.localDeleteBackendBound==data.supported and
 opened.selectedFileCanDelete==false,'Snapshot deletion capability is not its actual binding/selection')
local unsupportedDelete=false
for _,name in ipairs(opened.unsupportedActions) do if name=='delete' then unsupportedDelete=true end end
check(unsupportedDelete==not data.supported,'Snapshot incorrectly advertises delete support')
local path=data.files[1].path
phase='select-original-row'
local button=selectPath(path)
if data.case=='unsupported' then
 check(env.Controls.Delete:IsDisabled() and env.Controls.Yes:IsDisabled(),'Unbound delete controls became enabled')
 check(not ui.DispatchLeftClick(key(env.Controls.Delete)),'Unbound delete accepted input')
 rejects(function() env.UI.DeleteSavedGame(path) end,'unbound direct service')
 check(#deleteCalls==0 and eligibilityQueries==0,'Unbound service was consulted')
 return finish()
end
check(not env.Controls.Delete:IsDisabled() and metadata(observe('eligible')).selectedFileCanDelete,
 'Known owned selection did not enable deletion')
check(not ui.DispatchLeftClick(key(env.Controls.Delete),env.Mouse.eRClick) and #deleteCalls==0,
 'Right-click opened a destructive confirmation')
rejects(function() env.UI.DeleteSavedGame(path) end,'direct service without Yes dispatch')
rejects(function() env.UI.DeleteSavedGame(data.foreign) end,'foreign direct service')
phase='original-no-and-escape-cancel'
showDelete()
local originalRowKey=key(button)
check(target(originalRowKey)==nil and not ui.DispatchLeftClick(originalRowKey),'Confirmation leaked row input')
check(not ui.DispatchLeftClick(key(env.Controls.BackButton)),'Confirmation leaked Back input')
check(not ui.DispatchLeftClick(key(env.Controls.DeleteConfirm)),'Backdrop fabricated a callback')
if isSave then check(not ui.DispatchLeftClick(key(env.Controls.NameBox)),'Confirmation leaked editor input') end
check(ui.DispatchKeyDown(env.Keys.VK_RETURN),'Original Enter handler was not retained')
check(#deleteCalls==0 and not env.Controls.DeleteConfirm:IsHidden(),'Enter invented a destructive action')
click('No');check(env.Controls.DeleteConfirm:IsHidden() and #deleteCalls==0,'Original No deleted a file')
check(not ui.DispatchLeftClick(key(env.Controls.Yes)),'Hidden Yes accepted stale input after No')
showDelete();check(ui.DispatchKeyDown(env.Keys.VK_ESCAPE),'Original Escape was rejected')
check(env.Controls.DeleteConfirm:IsHidden() and snapshot().active and #deleteCalls==0,'Escape did not only cancel deletion')
observe('cancelled')
phase='direct-original-callbacks-cannot-grant'
env.OnDelete();check(env.Controls.Yes:IsDisabled(),'Direct OnDelete admitted a destructive confirmation')
rejects(env.OnYes,'direct original OnYes')
check(#deleteCalls==0,'Direct original callbacks reached the service')
if isSave then
 phase='overwrite-confirmation-remains-unsupported'
 env.OnSave()
 check(not env.Controls.DeleteConfirm:IsHidden() and env.Controls.Yes:IsDisabled(),
  'Shared overwrite confirmation incorrectly acquired delete permission')
 check(not ui.DispatchLeftClick(key(env.Controls.Yes)) and #deleteCalls==0,'Overwrite Yes dispatched')
 click('No')
end
phase='stale-eligibility-cannot-delete'
showDelete();available[path]=false
check(not metadata(snapshot()).deleteConfirmationArmed and env.Controls.Yes:IsDisabled() and env.Controls.Delete:IsDisabled(),
 'Stale eligibility did not disable its controls and revoke confirmation')
check(not ui.DispatchLeftClick(key(env.Controls.Yes)) and #deleteCalls==0,'Stale ownership reached mutation')
click('No');available[path]=true;selectPath(path)
if #data.files>1 then
 phase='different-selection-cannot-use-old-confirmation'
 showDelete()
 if isSave then env.g_SelectedEntry=env.g_SavedGames[2] else env.g_iSelected=2 end
 check(not metadata(snapshot()).deleteConfirmationArmed and env.Controls.Yes:IsDisabled(),
  'Changed selection retained an armed confirmation')
 check(not ui.DispatchLeftClick(key(env.Controls.Yes)) and #deleteCalls==0,'Changed selection reused the old Yes grant')
 click('No');selectPath(path)
end
for _,row in ipairs(data.files) do
 if not row.known then
  phase='unknown-header-delete-refused'
  selectPath(row.path)
  check(env.Controls.Delete:IsDisabled() and not metadata(snapshot()).selectedFileCanDelete,
   'Unknown header became eligible for deletion')
  check(not ui.DispatchLeftClick(key(env.Controls.Delete)) and #deleteCalls==0,'Unknown header reached mutation')
 end
end
phase='successful-original-yes-and-list-refresh'
selectPath(path);showDelete()
local queriesBefore=catalogQueries
local yesKey=key(env.Controls.Yes)
if data.case=='delete-false' or data.case=='delete-error' then
 rejects(function() ui.DispatchLeftClick(yesKey) end,'native service failure')
 check(#deleteCalls==1 and deleted[path]==nil and catalogQueries==queriesBefore,
  'Failed service changed catalog or fabricated original refresh')
 check(not ui.DispatchLeftClick(yesKey),'Failed service retained a stale Yes dispatch')
 rejects(function() env.UI.DeleteSavedGame(path) end,'failed service retained its grant')
 check(#deleteCalls==1 and countFiles()==#data.files,'Failure changed another file or retried mutation')
 return finish()
end
click('Yes')
check(#deleteCalls==1 and deleteCalls[1]==path and deleted[path] and countFiles()==#data.files-1,
 'Original Yes did not delete exactly its selected file')
observe('refreshed')
check(catalogQueries==queriesBefore+1 and trace[#trace]=='files' and trace[#trace-1]=='delete:'..path,
 'Original SetupFileButtonList did not immediately requery the mock service')
check(env.Controls.DeleteConfirm:IsHidden() and env.Controls.Delete:IsDisabled(),
 'Original refresh retained its confirmation or selection')
check(isSave and env.g_SelectedEntry==nil or not isSave and env.g_iSelected==-1,'Original refresh did not reset selection')
for _,row in ipairs(isSave and env.g_SavedGames or env.g_FileList) do
 check((isSave and row.FileName or row)~=path,'Deleted file survived in the retained list tail')
end
check(not ui.DispatchLeftClick(yesKey),'Duplicate Yes reached a refreshed selection')
rejects(function() env.UI.DeleteSavedGame(path) end,'deleted path direct replay')
check(#deleteCalls==1,'Deleted path was mutated twice')
if countFiles()>0 then
 local survivor=data.files[2].path;selectPath(survivor)
 check(not deleted[survivor],'Deletion changed the surviving file')
else
 check(not metadata(snapshot()).selectedFileCanDelete,'Empty refreshed list retained delete eligibility')
end
check(timerChanges==0,'Deletion changed gameplay timer ownership')
return finish()
end
local ok,result=xpcall(exercise,function(message)
 return 'Owned-delete '..data.menu..' case='..data.case..' phase='..phase..': '..tostring(message)
end)
assert(ok,result)
return result
'''


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_component(*, menus=("SaveMenu", "LoadMenu"), include_snapshot=False,
                     cases=("unsupported", "supported", "empty-after-delete", "delete-false", "delete-error")) -> dict:
    """Run only original-Lua component cases; all mutations stay in mock tables."""
    if any(menu not in ("SaveMenu", "LoadMenu") for menu in menus):
        raise ValueError("Unknown original save menu")
    valid_cases = {"unsupported", "supported", "empty-after-delete", "delete-false", "delete-error",
                   "invalid-capability", "invalid-eligibility"}
    if any(case not in valid_cases for case in cases):
        raise ValueError("Unknown owned-save deletion fixture")
    includes = {
        "InstanceManager": "Assets/UI/InstanceManager.lua", "IconSupport": "Assets/UI/IconSupport.lua",
        "SupportFunctions": "Assets/UI/SupportFunctions.lua", "UniqueBonuses": UNIQUE_BONUSES_LUA,
        "InfoTooltipInclude": "Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua",
        "FLuaVector": "Assets/Gameplay/Lua/FLuaVector.lua", "MapUtilities": "Assets/Gameplay/Lua/MapUtilities.lua",
    }
    paths = {name: GAME / relative for name, relative in includes.items()}
    paths.update(scene=PROJECT / "Source/Host/UiScene.lua", input=PROJECT / "Source/Presentation/UiPresentationInput.lua",
                 SaveMenuLua=GAME / SAVE_MENU_LUA, SaveMenuXml=GAME / SAVE_MENU_XML,
                 LoadMenuLua=GAME / LOAD_MENU_LUA, LoadMenuXml=GAME / LOAD_MENU_XML,
                 lua=PROJECT / "Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll")
    before = {name: _digest(path) for name, path in paths.items()}
    if before["lua"] != LUA_SHA256:
        raise AssertionError("Existing approved headless Lua provider changed")
    source_base = {name: paths[name].read_text(encoding="utf-8-sig") for name in (*includes, "scene", "input")}
    release = json.loads((PROJECT / "Play/EarlyAccess/release.json").read_text(encoding="utf-8-sig"))
    database = PROJECT / "Build/InteractiveGameRuntime" / release["runtime_id"] / "rules.db"
    localization = database.with_name("localization.db")
    table_names = ("Leaders", "Civilization_Leaders", "Civilizations", "PlayerColors", "Colors", "IconTextureAtlases",
                   "Worlds", "HandicapInfos", "GameSpeeds", "Eras", "MapScripts", "Map_Sizes", "Maps", "GameOptions")
    with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as connection:
        connection.row_factory = sqlite3.Row
        tables = {name: [{key: value for key, value in dict(row).items() if value is not None}
                         for row in connection.execute('SELECT * FROM "' + name + '"')] for name in table_names}
    civ = next(row for row in tables["Civilizations"] if row["Type"] == "CIVILIZATION_ROME")
    lock_mods = next(row["ID"] for row in tables["GameOptions"] if row["Type"] == "GAMEOPTION_LOCK_MODS")
    current = dict(PlayerCivilization=civ["ID"], GameSpeed=2, StartEra=0, TurnNumber=7,
                   Difficulty=3, WorldSize=3, MapScript="Assets/Maps/Continents.lua", LeaderName="저장된 지도자",
                   CivilizationName="저장된 문명", CurrentEra=0, GameType=sdk_game_types()["GAME_SINGLE_PLAYER"])
    tags = sorted(set(re.findall(r"TXT_KEY_[A-Za-z0-9_]+", "\n".join(source_base.values()) + json.dumps(tables) +
                                "\n".join(paths[name].read_text(encoding="utf-8-sig") for name in
                                          ("SaveMenuLua", "SaveMenuXml", "LoadMenuLua", "LoadMenuXml")))))
    locale = {}
    with closing(sqlite3.connect(localization.as_uri() + "?mode=ro", uri=True)) as connection:
        for language in ("en_US", "ko_KR"):
            for offset in range(0, len(tags), 500):
                batch = tags[offset:offset + 500]
                locale.update(connection.execute("SELECT Tag,Text FROM LocalizedText WHERE Language=? AND Tag IN (" +
                                                 ",".join("?" for _ in batch) + ")", [language, *batch]))
    inline = json.loads((PROJECT / "evidence/ui_popup/assets/inline_icons.json").read_text(encoding="utf-8"))["icons"]
    files = [dict(path=r"C:\owned\session\Alpha.zssave", known=True, high=2097152, low=0, display="2026-10-16 01:00"),
             dict(path=r"C:\owned\session\Beta.zssave", known=True, high=2097152, low=1, display="2026-10-16 01:01"),
             dict(path=r"C:\owned\session\Unknown.zssave", known=False, high=2097151, low=4294967295, display="2026-10-16 00:59")]
    results, temporary_files, snapshots = [], [], {}
    temporary = None
    try:
        with small_source_directory() as temporary:
            for menu in menus:
                tree = (save_menu_control_tree if menu == "SaveMenu" else load_menu_control_tree)(
                    ET.parse(paths[menu + "Xml"]).getroot())
                tree.update(contextName=menu, popupKind=menu)
                styles = production_style_defaults(temporary, tree)
                tree.update(styleDefaults=styles["controls"], styleDefaultsSource=styles["source"], styleDefaultsPolicy=styles["policy"])
                if menu == "LoadMenu":
                    attach_load_menu_control_defaults(tree, load_menu_check_defaults(temporary, UiAssets(GAME)))
                tree["fontMetrics"] = production_font_metrics(tree, inline)
                source = {**source_base, "stock": paths[menu + "Lua"].read_text(encoding="utf-8-sig")}
                for case in cases:
                    rows = files[:1] if case == "empty-after-delete" else files
                    data = dict(tables=tables, locale=locale, current=current, gameTypes=sdk_game_types(), lockMods=lock_mods,
                                menu=menu, case=case, supported=case != "unsupported", files=rows,
                                capture=case == "supported" or include_snapshot, foreign=r"C:\foreign\not-owned.zssave")
                    assembled = (HARNESS.replace("@@SOURCES@@", lua_value(source)).replace("@@LAYOUT@@", lua_value(tree))
                                 .replace("@@DATA@@", lua_value(data)))
                    observed = execute_lua(assembled)
                    states = observed.pop("snapshots", {})
                    if states:
                        contract = save_menu_contract if menu == "SaveMenu" else load_menu_controls_contract
                        for stage, snapshot in states.items():
                            try:
                                contract(snapshot, closed=stage == "closed")
                            except Exception as error:
                                raise AssertionError(f"Owned-delete compositor contract {menu}/{case}/{stage}: {error}") from error
                        observed["compositorContractStages"] = sorted(states)
                        if include_snapshot:
                            snapshots.setdefault(menu, {})[case] = states
                    results.append(observed)
            for path in sorted(temporary.rglob("*")):
                if path.is_file():
                    temporary_files.append({"path": str(path), "bytes": path.stat().st_size, "sha256": _digest(path)})
    finally:
        changed = [name for name, path in paths.items() if _digest(path) != before[name]]
        if changed:
            raise AssertionError("Owned-delete component changed protected inputs: " + ", ".join(changed))
    if temporary is None or temporary.exists():
        raise AssertionError("Owned-delete component did not remove its temporary styles")
    result = {"status": "PASS_ORIGINAL_OWNED_SAVE_DELETE_LUA_FIXTURES", "checks": sum(row["checks"] for row in results),
            "cases": results, "source_sha256": before, "original_sources_unchanged": True,
            "temporary_styles_removed": True,
            "temporary_cleanup": [{**row, "result": "REMOVED_ABSENT" if not Path(row["path"]).exists() else "PRESENT"}
                                  for row in temporary_files],
            "lua_provider": str(paths["lua"]), "native_host_or_gamecore_executed": False,
            "retail_user_state_accessed": False, "real_archive_deletes": 0}
    if include_snapshot:
        result["snapshots"] = snapshots
    return result


if __name__ == "__main__":
    result = verify_component()
    print(json.dumps({key: result[key] for key in ("status", "checks", "original_sources_unchanged",
                                                  "temporary_styles_removed", "real_archive_deletes")}, ensure_ascii=False))
