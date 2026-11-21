"""Exercise retained PullDown input with the unchanged stock LoadMenu sort code.

Only the original comparator, input-handler, and sort-initialization blocks run.
The remaining LoadMenu/SDK lifecycle, localization and FILETIME comparison are
explicit component fixtures. The existing Lua 5.1 DLL is reused; no compiler,
Host, window, GameCore, retail save, or MODS access is involved. Temporary copies
contain Styles.xml only and are removed by the guarded shared context manager.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import struct
import sys
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

from economic_overview_scene import execute_lua
from game_menu_ui_assets import small_source_directory
from prepare_ui_popup_assets import (
    GAME, LOAD_MENU_LUA, LOAD_MENU_XML, STYLE_SOURCE, load_menu_control_tree,
    lua_value, production_font_metrics, production_style_defaults,
)


HARNESS = r'''
local source,layout,data=@@SOURCES@@,@@LAYOUT@@,@@DATA@@
local checks=0
local function check(value,message) assert(value,message);checks=checks+1 end
local arrayTypes={}
local function marked(values) local marker={};arrayTypes[marker]=true;return setmetatable(values,marker) end
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
 assert(kind=='table','Component encoder accepts only data')
 local parts={}
 if arrayTypes[getmetatable(value)] or #value>0 then
  for _,item in ipairs(value) do parts[#parts+1]=json(item) end
  return '['..table.concat(parts,',')..']'
 end
 local keys={};for key in pairs(value) do assert(type(key)=='string');keys[#keys+1]=key end
 table.sort(keys);for _,key in ipairs(keys) do parts[#parts+1]=json(key)..':'..json(value[key]) end
 return '{'..table.concat(parts,',')..'}'
end
local now,backRequests,rowClicks,timeComparisons,nameComparisons=0,0,0,0,0
local localeCalls={}
local env=setmetatable({ZeroSisUiLayout=layout,
 Game={Rand=function() return 0 end,GetActivePlayer=function() return 0 end},
 Players={[0]={}}}, {__index=_G})
env._G=env
local function run(text,name)
 local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
end
env.ZeroSisUiNative=function(op,...)
 if op=='uiFrameTime' then return now end
 if op=='screenSize' then return 1920,1080 end
 if op=='randomSeed' then return 17 end
 if op=='snapshotJson' then local value,marker=...;arrayTypes[marker]=true;return captured(value) end
 if op=='locale' then
  local value=...
  localeCalls[value]=(localeCalls[value] or 0)+1
  return data.locale[value] or tostring(value)
 end
 error('Unexpected native operation in PullDown-only component: '..tostring(op))
end
run(source.scene..'\n'..source.input..[[
__componentKey=function(handle) return state(handle).key end
]],'retained-PullDown.lua')
local ui=env.ZeroSisUi
local pull=env.Controls.SortByPullDown
local button=pull:GetButton()
local pullKey=env.__componentKey(pull)
local buttonKey=env.__componentKey(button)
env.g_ShowAutoSaves=false
env.g_SortTable={}
-- These independent fixture operations make the original sort callbacks
-- observable without claiming that the native SDK bridge is connected.
env.Locale.Compare=function(first,second)
 check(type(first)=='string' and type(second)=='string','Locale.Compare fixture argument type')
 nameComparisons=nameComparisons+1
 return first==second and 0 or first<second and -1 or 1
end
env.UI.CompareFileTime=function(ah,al,bh,bl)
 for _,word in ipairs({ah,al,bh,bl}) do
  check(type(word)=='number' and word>=0 and word<=4294967295 and word==math.floor(word),
   'Original time comparator changed its unsigned high/low argument contract')
 end
 timeComparisons=timeComparisons+1
 if ah~=bh then return ah>bh and 1 or -1 end
 return al==bl and 0 or al>bl and 1 or -1
end
env.OnBack=function() backRequests=backRequests+1;env.ContextPtr:SetHide(true) end
run(source.comparators..'\n'..source.originalInput..'\n'..source.sortInit,'LoadMenu-original-sort-blocks.lua')

local function key(handle) return env.__componentKey(handle) end
local function walk(node,callback)
 callback(node)
 for _,child in ipairs(node.children or {}) do walk(child,callback) end
end
local function find(snapshot,predicate)
 local result
 walk(snapshot.tree,function(node) if predicate(node) then assert(not result,'Ambiguous snapshot control');result=node end end)
 return result
end
local function byKey(snapshot,value) return find(snapshot,function(node) return node.key==value end) end
local function byId(snapshot,id) return find(snapshot,function(node) return node.id==id end) end
local function popup(snapshot)
 return find(snapshot,function(node) return node.ownerPullDownKey==pullKey and node.originalDataKind=='GridData' end)
end
local function entry(snapshot,label)
 local root=assert(popup(snapshot),'PullDown popup source subtree is missing')
 local result
 walk(root,function(node)
  if node.kind=='GridButton' and node.id=='Button' and node.text==label then
   assert(not result,'Ambiguous PullDown entry text');result=node
  end
 end)
 return assert(result,'Missing original PullDown entry '..label)
end
local function targets() return ui.GetInputTargets(env.Mouse.eLClick) end
local function target(value)
 for _,item in ipairs(targets()) do if item.key==value and item.event==env.Mouse.eLClick then return item end end
end
local function snapshot() return ui.Snapshot() end
local function click(value) check(ui.DispatchLeftClick(value),'Live left click was rejected: '..tostring(value)) end
local function assertClosed(message)
 local value=snapshot()
 local pop=popup(value)
 check(not pop or pop.hidden,message..': popup remained open')
 for _,item in ipairs(targets()) do check(item.inputRole~='PullDownDismiss',message..': stale dismiss target') end
 return value
end
local function assertOpen(message)
 local value=snapshot()
 local pop=assert(popup(value),message..': popup subtree is missing')
 check(not pop.hidden,message..': popup is hidden')
 local list=targets()
 check(#list>1 and list[1].key==value.tree.key and list[1].inputRole=='PullDownDismiss' and
  list[1].ownerPullDownKey==pullKey,message..': first hit target is not the owning viewport dismissal surface')
 check(target(buttonKey)~=nil,message..': original ButtonData GridButton is not live')
 check(value.tree.children[#value.tree.children].key==pop.key,
  message..': popup was not promoted after its overlapping original siblings')
 local unique={}
 walk(value.tree,function(node) assert(not unique[node.key],message..': duplicate retained key in snapshot');unique[node.key]=true end)
 check(unique[pop.key]==true,message..': promoted popup disappeared from the retained tree')
 return value,pop
end

local rows={}
for index,item in ipairs(data.files) do
 local names={}
 env.ContextPtr:BuildInstanceForControl('LoadButton',names,env.Controls.LoadFileButtonStack)
 names.ButtonText:SetText(item.title)
 names.Button:SetVoid1(index)
 names.Button:RegisterCallback(env.Mouse.eLClick,function() rowClicks=rowClicks+1 end)
 env.g_SortTable[tostring(names.InstanceRoot)]={Title=item.title,LastModified={High=item.high,Low=item.low}}
 rows[index]=names
end
env.Controls.LoadFileButtonStack:CalculateSize()
env.Controls.ScrollPanel:CalculateInternalSize()
env.Controls.LoadFileButtonStack:SortChildren(env.g_CurrentSort)
local function rowOrder(expected,message)
 local stack=assert(byId(snapshot(),'LoadFileButtonStack'))
 check(#stack.children==#expected,message..': row count changed')
 for index,value in ipairs(expected) do check(stack.children[index].key==key(rows[value].InstanceRoot),message..': row '..index) end
end
check(#targets()==0,'Inactive owner exposed PullDown input')
check(button:GetText()==data.locale.TXT_KEY_SORTBY_LASTMODIFIED,'Original default label changed')
rowOrder({3,1,2},'Original newest-first default')
env.ContextPtr:SetHide(false)
local closed=snapshot()
check(closed.active and closed.timerSemaphore==0,'Control-only child changed the parent timer')
check(closed.popupKind=='LoadMenu' and closed.contextName=='LoadMenu','Original control context identity changed')
check(closed.loadMenu.controlOnly and not closed.loadMenu.nativeVmConnected and
 not closed.loadMenu.retailBackendVerified,'Unconnected LoadMenu backend was presented as verified')
check(localeCalls['{TXT_KEY_LOAD_GAME:upper}'] and localeCalls['{TXT_KEY_NO_SAVED_GAMES:upper}'],
 'Original brace/modifier captions bypassed the locale composer')
check(byId(closed,'NoGames').text==data.locale['{TXT_KEY_NO_SAVED_GAMES:upper}'] and
 find(closed,function(node) return node.text==data.locale['{TXT_KEY_LOAD_GAME:upper}'] end)~=nil,
 'Original caption controls did not retain the locale composer return value')
local packages=assert(byId(closed,'ReferencedPackagesScrollPanel'))
local deferredSlider
walk(packages,function(node) if node.kind=='ScrollBar' then assert(not deferredSlider);deferredSlider=node end end)
check(deferredSlider and deferredSlider.scrollMetricsPending and
 deferredSlider.scrollMetricsPendingPolicy=='ORIGINAL_LOAD_MENU_HIDDEN_PACKAGE_WINDOW_UNMEASURED' and
 deferredSlider.contentHeight==nil and deferredSlider.maximumScroll==nil,
 'Hidden original package panel fabricated a measured scroll range')
env.Controls.ReferencedPackagesWindow:SetHide(false)
local visiblePanelOk,visiblePanelResult=pcall(snapshot)
check(visiblePanelOk,'Visible original package panel failed its normal layout barrier: '..tostring(visiblePanelResult))
local measuredPanel=assert(byId(visiblePanelResult,'ReferencedPackagesScrollPanel'))
local measuredStack=assert(byId(visiblePanelResult,'ReferencedPackagesStack'))
local measuredSlider
walk(measuredPanel,function(node) if node.kind=='ScrollBar' then assert(not measuredSlider);measuredSlider=node end end)
check(measuredPanel.contentWidth==0 and measuredPanel.contentHeight==0 and
 #measuredStack.children==0 and measuredStack.width==0 and measuredStack.height==0 and
 measuredSlider and not measuredSlider.scrollMetricsPending and measuredSlider.contentHeight==0,
 'Visible package panel did not measure its actual empty original stack or clear pending metrics')
local emptyPackageRange
for _,item in ipairs(ui.GetScrollTargets()) do if item.key==packages.key then emptyPackageRange=item end end
check(emptyPackageRange and emptyPackageRange.scrollY==0 and emptyPackageRange.contentHeight==0 and
 emptyPackageRange.viewportHeight==245 and emptyPackageRange.maximumScroll==0,
 'Measured empty package panel did not expose a finite zero scroll range')
env.Controls.ReferencedPackagesWindow:SetHide(true)
local mainSlider
walk(assert(byId(snapshot(),'ScrollPanel')),function(node)
 if node.kind=='ScrollBar' then assert(not mainSlider);mainSlider=node end
end)
check(mainSlider and mainSlider.attributes.Length=='364' and mainSlider.height==364,
 'Original file-list scrollbar Length was replaced by PullDown-specific geometry')
check(target(buttonKey)~=nil,'Closed PullDown did not expose its retained button')
assertClosed('Initial closed state')

click(buttonKey)
local opened,pop=assertOpen('Original two-option popup')
local modified=entry(opened,data.locale.TXT_KEY_SORTBY_LASTMODIFIED)
local named=entry(opened,data.locale.TXT_KEY_SORTBY_NAME)
check(modified.attributes.Size=='200.24' and modified.width==200 and modified.height==24,
 'Original InstanceData entry dimensions were rewritten')
check(target(modified.key)~=nil and target(named.key)~=nil,'Original sort entries are not independently selectable')
check(ui.DispatchPointerMove(modified.key) and ui.DispatchPointerMove(opened.tree.key),
 'Popup dismissal surface rejected pointer hover reset')
assertOpen('Pointer move to viewport dismissal surface')
check(target(key(rows[1].Button))==nil,'Open popup leaked an underlying row callback')
click(named.key)
check(button:GetText()==data.locale.TXT_KEY_SORTBY_NAME and env.g_CurrentSort==env.SortByName,
 'Original name callback did not replace label and current sort')
rowOrder({2,3,1},'Original alphabetical callback')
assertClosed('Selecting the original name option')
check(target(modified.key)==nil and not ui.DispatchLeftClick(modified.key),'Closed original entry accepted stale input')

env.g_ShowAutoSaves=true
click(buttonKey);local auto=assertOpen('Autosave name popup');click(entry(auto,data.locale.TXT_KEY_SORTBY_NAME).key)
rowOrder({1,3,2},'Original reverse autosave-name callback')
env.g_ShowAutoSaves=false
click(buttonKey);local last=assertOpen('Newest-first popup');click(entry(last,data.locale.TXT_KEY_SORTBY_LASTMODIFIED).key)
rowOrder({3,1,2},'Original FILETIME high/low callback')
check(timeComparisons>0 and nameComparisons>0,'Original comparators were not executed')
check(rowClicks==0,'Sort selection reached a saved-game row callback')

click(buttonKey);assertOpen('Toggle test');click(buttonKey);assertClosed('Second button click')
click(buttonKey);assertOpen('Escape test')
check(ui.DispatchKeyDown(env.Keys.VK_ESCAPE),'Open popup rejected Escape')
assertClosed('First Escape')
check(backRequests==0 and snapshot().active,'First Escape reached the original parent-close handler')
check(ui.DispatchKeyDown(env.Keys.VK_ESCAPE),'Closed popup rejected original Escape')
check(backRequests==1 and not snapshot().active and #targets()==0,'Second Escape did not run original InputHandler/OnBack')
env.ContextPtr:SetHide(false);assertClosed('Context reopen')

click(buttonKey);local outside=assertOpen('Outside click test')
check(not ui.DispatchLeftClick(9007199254740991),'Unknown retained key consumed outside dismissal')
assertOpen('Unknown key left popup open')
click(key(rows[1].Button));assertClosed('Valid underlying key dismisses only')
check(rowClicks==0,'Outside dismissal also activated its underlying row')
click(key(rows[1].Button));check(rowClicks==1,'Dismissed popup left the original row input blocked')
click(buttonKey);local backdrop=assertOpen('Backdrop test');click(backdrop.tree.key);assertClosed('Viewport backdrop')

click(buttonKey);assertOpen('Disabled owner test');pull:SetDisabled(true)
assertClosed('Disabled owner')
check(target(buttonKey)==nil and not ui.DispatchLeftClick(buttonKey),'Disabled PullDown accepted input')
pull:SetDisabled(false);assertClosed('Re-enabled owner')
click(buttonKey);assertOpen('Hidden owner test');pull:SetHide(true);assertClosed('Hidden owner')
check(target(buttonKey)==nil,'Hidden owner button is live')
pull:SetHide(false);assertClosed('Shown owner')
click(buttonKey);assertOpen('Hidden ancestor test');env.Controls.MainSelection:SetHide(true)
assertClosed('Hidden ancestor');check(target(buttonKey)==nil,'Hidden original owner still exposed the PullDown button')
env.Controls.MainSelection:SetHide(false);assertClosed('Shown ancestor')
click(buttonKey);assertOpen('Context-close test');env.ContextPtr:SetHide(true)
check(#targets()==0,'Closed owner context exposed popup callbacks')
env.ContextPtr:SetHide(false);assertClosed('Context shown after close')

-- Reinitialize through the unchanged original ClearEntries/BuildEntry loop.
local oldEntryKey=modified.key
run(source.sortInit,'LoadMenu-original-sort-reinitialize.lua')
assertClosed('Rebuilt entries')
click(buttonKey);local rebuilt=assertOpen('Fresh entries')
check(entry(rebuilt,data.locale.TXT_KEY_SORTBY_LASTMODIFIED).key~=oldEntryKey,
 'ClearEntries reused the destroyed entry identity')
check(not ui.DispatchLeftClick(oldEntryKey),'A destroyed entry key invoked a fresh callback')
local countBefore=0;walk(assert(popup(snapshot())),function(node) if node.id=='Button' then countBefore=countBefore+1 end end)
check(not pcall(function() pull:BuildEntry('UnsupportedTemplate',{}) end),'Unknown style entry template was accepted')
local countAfter=0;walk(assert(popup(snapshot())),function(node) if node.id=='Button' then countAfter=countAfter+1 end end)
check(countBefore==countAfter,'Rejected BuildEntry changed the live entry list')
click(buttonKey);assertClosed('Reinitialized button toggle')

-- Keep the original entry template and declared ScrollThreshold; only the
-- number of component rows changes so clipping and scroll limits are exercised.
pull:ClearEntries()
local overflowRows,selected={},0
for index=1,8 do
 local names={};pull:BuildEntry('InstanceOne',names)
 names.Button:SetText('Item '..index)
 names.Button:RegisterCallback(env.Mouse.eLClick,function() selected=index end)
 overflowRows[index]=names.Button
end
pull:CalculateInternals()
click(buttonKey)
local overflowing,overflowPopup=assertOpen('Threshold overflow')
local scroll
walk(overflowPopup,function(node) if node.kind=='ScrollPanel' then assert(not scroll);scroll=node end end)
check(scroll and scroll.height==110 and scroll.contentHeight==8*24,
 'Declared ScrollThreshold failed to clamp the measured original rows')
overflowRows[1]:SetDisabled(true)
check(target(key(overflowRows[1]))==nil and not ui.DispatchLeftClick(key(overflowRows[1])) and selected==0,
 'A disabled entry remained selectable')
overflowRows[1]:SetDisabled(false)
check(target(key(overflowRows[1]))~=nil,'Re-enabled visible entry did not become live')
local up,down
walk(overflowPopup,function(node)
 if node.kind=='UpButton' then assert(not up);up=node end
 if node.kind=='DownButton' then assert(not down);down=node end
end)
check(up and down and up.attributes.AnchorSide=='O,I' and down.attributes.AnchorSide=='O,I',
 'Original outside-anchored popup scroll buttons were lost')
for _,chrome in ipairs({up,down}) do
 local item=target(chrome.key)
 check(chrome.scrollPanelChromeOwnerKey==scroll.key and
  chrome.scrollClipPolicy=='PULL_DOWN_CHROME_OUTSIDE_OWN_VIEWPORT_WITHIN_POPUP',
  'Outside popup chrome lost its explicit scroll-owner clipping policy')
 check(item and item.clippedBounds and item.clippedBounds.width>0 and item.clippedBounds.height>0 and
  item.clippedBounds.x>=scroll.x+scroll.width,
  'Original outside scroll button was clipped by its own panel content viewport')
end
click(down.key)
check(byKey(snapshot(),scroll.key).scrollY==24 and selected==0,'Popup down button did not scroll the live panel')
assertOpen('Down button keeps popup open')
click(up.key)
check(byKey(snapshot(),scroll.key).scrollY==0 and selected==0,'Popup up button did not reverse the live scroll')
assertOpen('Up button keeps popup open')
local visibleCount=0
for _,handle in ipairs(overflowRows) do if target(key(handle)) then visibleCount=visibleCount+1 end end
check(visibleCount>0 and visibleCount<8,'Overflow rows were not clipped to the popup viewport')
check(target(key(overflowRows[8]))==nil and not ui.DispatchLeftClick(key(overflowRows[8])),
 'An entry below the visible popup viewport accepted direct input')
local ownerScroll
for _,item in ipairs(ui.GetScrollTargets()) do if item.key==scroll.key then ownerScroll=item end end
check(ownerScroll~=nil and ownerScroll.maximumScroll==8*24-110,'Popup scroll owner or range is missing')
check(ui.DispatchScroll(scroll.key,10000),'Open popup rejected scrolling its own viewport')
check(target(key(overflowRows[8]))~=nil,'Last entry did not become selectable after scrolling to the end')
check(not ui.DispatchScroll(scroll.key,0) and not ui.DispatchScroll(scroll.key,math.huge),
 'Invalid wheel input changed the popup scroll range')
local scrolled=assertOpen('Scrolled overflow')
click(key(overflowRows[8]));check(selected==8,'Scrolled entry did not invoke its registered selection once')
assertClosed('Overflow selection')

pull:SetSizeVal(360,31);pull:CalculateInternals()
click(buttonKey);local resized,resizedPopup=assertOpen('Resized PullDown')
local resizedButton=assert(byKey(resized,buttonKey))
check(resizedButton.width==360 and resizedButton.height==31,'Retained button did not follow changed owner size')
check(entry(resized,'Item 1').width==200 and entry(resized,'Item 1').height==24,
 'Resize silently rewrote the original InstanceData dimensions')
check(resizedPopup.width>0 and resizedPopup.height>0,'Resize destroyed popup bounds')
local overflowLastKey=key(overflowRows[8])
pull:ClearEntries();assertClosed('ClearEntries while open')
check(not ui.DispatchLeftClick(overflowLastKey),'ClearEntries left an overflow callback alive')
check(not pcall(function() return overflowRows[8]:GetText() end),'ClearEntries did not destroy the old entry handle')
env.ContextPtr:SetHide(true)
check(#targets()==0 and backRequests==1 and rowClicks==1,'Component left live input or unexpected original callbacks')
return json({status='PASS_LOAD_MENU_PULL_DOWN_CONTROL_COMPONENT_ONLY',checks=checks,
 originalSortBlocksExecuted=true,originalInputHandlerExecuted=true,
 sdkLifecycleFixture=true,localeComparisonFixture=true,fileTimeComparisonFixture=true,
 nativeGameVerified=false,retailGeometryVerified=false,fullLoadMenuVerified=false,
 archiveWrites=0,timerChanges=0,backRequests=backRequests,rowClicks=rowClicks,
 timeComparisons=timeComparisons,nameComparisons=nameComparisons,
 localeComposerCalls=localeCalls,
 hiddenPackageMetricsDeferred=true,visiblePackageRangeMeasured=true,
 snapshots=marked({closed,opened,overflowing,scrolled,resized})})
'''


def artifact(path: Path) -> dict:
    raw = path.read_bytes()
    return {"path": str(path), "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def existing_lua_provider() -> tuple[Path, dict]:
    library = PROJECT / "Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll"
    raw = library.read_bytes()
    if len(raw) < 64 or raw[:2] != b"MZ":
        raise RuntimeError("Existing Lua provider is not a PE image")
    offset = struct.unpack_from("<I", raw, 0x3C)[0]
    if offset + 26 > len(raw) or raw[offset:offset + 4] != b"PE\0\0":
        raise RuntimeError("Existing Lua provider has no valid PE header")
    machine = struct.unpack_from("<H", raw, offset + 4)[0]
    magic = struct.unpack_from("<H", raw, offset + 24)[0]
    if machine != 0x8664 or magic != 0x20B:
        raise RuntimeError("Existing Lua provider must be x64 PE32+")
    return library, {**artifact(library), "machine": "0x8664", "format": "PE32+", "reused": True}


def original_blocks(stock: str) -> tuple[dict, dict]:
    definitions = {
        "comparators": ("function AlphabeticalSort( a, b )", "\n-- Key Down Processing", False),
        "originalInput": ("function InputHandler( uiMsg, wParam, lParam )",
                          "ContextPtr:SetInputHandler( InputHandler );", True),
        "sortInit": ("local sortOptions = {", "g_CurrentSort = sortOptions[1][2];", True),
    }
    blocks, evidence = {}, {}
    for name, (first, last, include_end) in definitions.items():
        if stock.count(first) != 1 or stock.count(last) != 1:
            raise AssertionError("Original LoadMenu block boundary changed: " + name)
        start = stock.index(first)
        end = stock.index(last, start) + (len(last) if include_end else 0)
        block = stock[start:end]
        blocks[name] = block
        evidence[name] = {"start_line": stock.count("\n", 0, start) + 1,
                          "end_line": stock.count("\n", 0, end) + 1,
                          "sha256_utf8": hashlib.sha256(block.encode("utf-8")).hexdigest()}
    expected = {"ClearEntries()": 1, 'BuildEntry( "InstanceOne", controlTable )': 1,
                "RegisterCallback(Mouse.eLClick": 1, "CalculateInternals()": 1,
                "SortChildren( v[2] )": 1}
    for token, count in expected.items():
        if blocks["sortInit"].count(token) != count:
            raise AssertionError("Original sort-initialization contract changed: " + token)
    return blocks, evidence


def verify_component(*, include_snapshots: bool = False) -> dict:
    library, provider = existing_lua_provider()
    source_paths = {
        "scene": PROJECT / "Source/Host/UiScene.lua",
        "input": PROJECT / "Source/Presentation/UiPresentationInput.lua",
        "stock": GAME / LOAD_MENU_LUA,
        "xml": GAME / LOAD_MENU_XML,
        "styles": GAME / STYLE_SOURCE,
        "preparer": PROJECT / "tools/prepare_ui_popup_assets.py",
        "harness": Path(__file__).resolve(),
        "lua_provider": library,
    }
    before = {name: artifact(path) for name, path in source_paths.items()}
    source = {name: source_paths[name].read_text(encoding="utf-8-sig")
              for name in ("scene", "input", "stock")}
    blocks, block_evidence = original_blocks(source.pop("stock"))
    source.update(blocks)
    original = ET.parse(source_paths["xml"]).getroot()
    tree = load_menu_control_tree(original)
    tree.update(popupKind="LoadMenu", contextName="LoadMenu")
    inline_path = PROJECT / "evidence/ui_popup/assets/inline_icons.json"
    before["inline_icons"] = artifact(inline_path)
    source_paths["inline_icons"] = inline_path
    inline = json.loads(inline_path.read_text(encoding="utf-8"))["icons"]
    data = {
        "locale": {"TXT_KEY_SORTBY_LASTMODIFIED": "Last modified", "TXT_KEY_SORTBY_NAME": "Name",
                   "{TXT_KEY_LOAD_GAME:upper}": "LOAD GAME",
                   "{TXT_KEY_NO_SAVED_GAMES:upper}": "NO SAVED GAMES"},
        "files": [{"title": "Zulu", "high": 7, "low": 0},
                  {"title": "Alpha", "high": 6, "low": 4294967295},
                  {"title": "Mike", "high": 7, "low": 1}],
    }
    temporary = None
    try:
        with small_source_directory() as temporary:
            styles = production_style_defaults(temporary, tree)
            tree.update(styleDefaults=styles["controls"], styleDefaultsSource=styles["source"],
                        styleDefaultsPolicy=styles["policy"])
            tree["fontMetrics"] = production_font_metrics(tree, inline)
            for font_id, font in tree["fontMetrics"]["fonts"].items():
                name = "font/" + font_id
                source_paths[name] = GAME / font["ggxmlPath"]
                before[name] = artifact(source_paths[name])
            result = execute_lua(HARNESS.replace("@@SOURCES@@", lua_value(source))
                                 .replace("@@LAYOUT@@", lua_value(tree))
                                 .replace("@@DATA@@", lua_value(data)))
    finally:
        changed = [name for name, path in source_paths.items() if artifact(path) != before[name]]
        if changed:
            raise AssertionError("PullDown component changed source inputs: " + ", ".join(changed))
    snapshots = result.pop("snapshots")
    result.update(source_artifacts=before, original_blocks=block_evidence, lua_provider=provider,
                  temporary_styles_removed=temporary is not None and not temporary.exists(),
                  snapshot_count=len(snapshots))
    if not result["temporary_styles_removed"]:
        raise AssertionError("Guarded style fixture cleanup did not remove its private directory")
    if include_snapshots:
        result["snapshots"] = snapshots
        result["prepared_layout"] = copy.deepcopy(tree)
    return result


if __name__ == "__main__":
    print(json.dumps(verify_component(), ensure_ascii=False))
