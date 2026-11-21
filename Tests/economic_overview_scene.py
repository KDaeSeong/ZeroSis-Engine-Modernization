"""Execute original EconomicOverview Lua lifecycle in an isolated Lua 5.1 VM.

Original parent/general/happiness scripts and all three XML trees are loaded.
SDK data queries and child refresh bodies are explicit component fixtures; this
does not verify live SDK economic values, native window routing, or gameplay.
Temporary style preparation is removed before returning.
"""
from __future__ import annotations

import copy
import ctypes
import json
from pathlib import Path
import re
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))

from economic_overview_renderer import GAME, prepared_sources
from prepare_ui_popup_assets import (economic_overview_layout_metadata, lua_value,
                                     production_font_metrics, production_style_defaults)
from ui_pixel_scene import compose_economic_overview_snapshot, economic_walk


def execute_lua(source: str) -> dict:
    library = PROJECT / 'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'
    if not library.is_file():
        raise RuntimeError('Existing shared Lua 5.1 provider is required; this test never builds one')
    lua = ctypes.CDLL(str(library))
    lua.luaL_newstate.argtypes = []
    lua.luaL_newstate.restype = ctypes.c_void_p
    lua.luaL_openlibs.argtypes = [ctypes.c_void_p]
    lua.luaL_openlibs.restype = None
    lua.luaL_loadbuffer.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
    lua.luaL_loadbuffer.restype = ctypes.c_int
    lua.lua_pcall.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int]
    lua.lua_pcall.restype = ctypes.c_int
    lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    lua.lua_tolstring.restype = ctypes.c_char_p
    lua.lua_close.argtypes = [ctypes.c_void_p]
    lua.lua_close.restype = None
    state = lua.luaL_newstate()
    if not state:
        raise RuntimeError('Cannot allocate component Lua state')
    try:
        lua.luaL_openlibs(state)
        data = source.encode('utf-8')
        status = lua.luaL_loadbuffer(state, data, len(data), b'@EconomicOverview-component.lua')
        if not status:
            status = lua.lua_pcall(state, 0, 1, 0)
        text = lua.lua_tolstring(state, -1, None)
        if status or not text:
            raise RuntimeError('EconomicOverview Lua component failed: ' +
                               (text.decode('utf-8', errors='replace') if text else 'no returned JSON'))
        return json.loads(text.decode('utf-8'))
    finally:
        lua.lua_close(state)


HARNESS = r'''
local source = @@SOURCES@@
local layouts = @@LAYOUTS@@
local localeInventory = @@LOCALE_INVENTORY@@
local checks=0
local function check(value,message) assert(value,message);checks=checks+1 end
local arrayTypes={}
local function marked(values) local marker={};arrayTypes[marker]=true;return setmetatable(values,marker) end
local function json(value)
  local kind=type(value)
  if kind=='nil' then return 'null' end
  if kind=='boolean' then return tostring(value) end
  if kind=='number' then return string.format('%.17g',value) end
  if kind=='string' then return '"'..value:gsub('[%z\1-\31\\"]',function(ch)
    if ch=='"' then return '\\"' elseif ch=='\\' then return '\\\\' end
    return string.format('\\u%04x',string.byte(ch)) end)..'"' end
  assert(kind=='table','component encoder accepts no userdata/functions')
  local parts={}
  if arrayTypes[getmetatable(value)] or #value>0 then
    for _,item in ipairs(value) do parts[#parts+1]=json(item) end
    return '['..table.concat(parts,',')..']'
  end
  local keys={};for key in pairs(value) do assert(type(key)=='string');keys[#keys+1]=key end
  table.sort(keys);for _,key in ipairs(keys) do parts[#parts+1]=json(key)..':'..json(value[key]) end
  return '{'..table.concat(parts,',')..'}'
end
local vm={}
local timerBalance,timerAcquisitions,timerReleases=0,0,0
local visibilityRequests,productionRequests={},{}
local numberRequests={}
local function run(text,env,name)
  local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
end
local function initialize(slot)
  local env=setmetatable({ZeroSisUiLayout=layouts[slot],
    Game={Rand=function() return 0 end,GetActivePlayer=function() return 0 end,
          IsOption=function() return false end}, Players={[0]={}},
    GameOptionTypes={GAMEOPTION_NO_HAPPINESS=1,GAMEOPTION_NO_SCIENCE=2,GAMEOPTION_NO_RELIGION=3},
    ButtonPopupTypes={BUTTONPOPUP_ECONOMIC_OVERVIEW=905,BUTTONPOPUP_CHOOSEPRODUCTION=906}}, {__index=_G})
  env._G=env
  env.ZeroSisUiNative=function(operation,...)
    if operation=='uiFrameTime' then return 0 end
    if operation=='screenSize' then return 1920,1080 end
    if operation=='randomSeed' then return 17 end
    if operation=='locale' then return 'Fixture' end
    if operation=='localeNumber' then
      check(slot~='parent' and select('#',...)==2,'number formatter argument count or owning VM changed')
      local value,pattern=...
      numberRequests[slot]=numberRequests[slot] or {}
      local requests=numberRequests[slot]
      local token='FORMAT_FIXTURE/'..slot..'/'..tostring(#requests+1)
      requests[#requests+1]={value=value,pattern=pattern,result=token}
      return token
    end
    if operation=='snapshotJson' then local snapshot,marker=...;arrayTypes[marker]=true;return snapshot end
    if operation=='timer' then
      local delta=...;check(slot=='parent' and (delta==1 or delta==-1),'child acquired popup timer')
      timerBalance=timerBalance+delta;check(timerBalance==0 or timerBalance==1,'timer imbalance')
      if delta==1 then timerAcquisitions=timerAcquisitions+1 else timerReleases=timerReleases+1 end
      return true
    end
    if operation=='economicChildHidden' then
      local id,hidden=...;visibilityRequests[#visibilityRequests+1]={id=id,hidden=hidden};return true
    end
    if operation=='economicChooseProduction' then
      local id=...;productionRequests[#productionRequests+1]=id;return true
    end
    error('Unexpected component native operation: '..slot..'/'..tostring(operation))
  end
  env.include=function(name)
    check(source[name]~=nil,'original include unavailable: '..name)
    run(source[name],env,name..'.lua')
    if name=='IconSupport' then
      -- The icon hookup's SDK database query is outside this lifecycle fixture.
      env.CivIconHookup=function() env.__iconHookups=(env.__iconHookups or 0)+1 end
    end
  end
  run(source.scene..'\n'..source.input..'\n'..source.economic..[[
__componentNode=function(handle) return state(handle) end
]],env,'retained-economic.lua')
  for _,name in ipairs(localeInventory[slot] or {}) do
    check(type(env.Locale[name])=='function','original '..slot..' requires missing Locale.'..name)
  end
  run(source[slot],env,slot..'-original.lua')
  check(env.ContextPtr:IsHidden() and not env.ZeroSisUi.IsActive(),'original script initialized active')
  check(#env.ZeroSisUi.GetInputTargets()==0,'inactive child exposed registered input')
  return env
end
vm.EconomicGeneralInfo=initialize('EconomicGeneralInfo')
vm.HappinessInfo=initialize('HappinessInfo')
vm.parent=initialize('parent')
check(vm.parent.__iconHookups==1,'original parent initial ShowHideHandler was not called')
check(vm.parent.Locale.ToNumber==nil,'child-only numeric formatter leaked into parent VM')

local numberCases={
  {name='positive',value=12.345},{name='negative',value=-98.76},{name='zero',value=0},
  {name='nan',value=0/0},{name='positive-infinity',value=math.huge},
  {name='negative-infinity',value=-math.huge}}
local numberCalls,rejectedNumberArguments=0,0
for _,slot in ipairs({'EconomicGeneralInfo','HappinessInfo'}) do
  local formatter=vm[slot].Locale.ToNumber
  for _,case in ipairs(numberCases) do
    local result=formatter(case.value,'#.##')
    local records=numberRequests[slot]
    local recorded=records[#records]
    local identical=(case.value~=case.value and recorded.value~=recorded.value) or recorded.value==case.value
    check(type(recorded.value)=='number' and identical and recorded.pattern=='#.##',
          'original number/pattern was coerced before native formatting: '..slot..'/'..case.name)
    check(result==recorded.result,'native formatter text was replaced by the Lua adapter')
    numberCalls=numberCalls+1
  end
  local function rejects(...)
    local before=#numberRequests[slot]
    check(not pcall(formatter,...),'invalid numeric formatting argument was accepted')
    check(#numberRequests[slot]==before,'invalid formatting arguments reached native formatter')
    rejectedNumberArguments=rejectedNumberArguments+1
  end
  for _,pattern in ipairs({'','#0.00','#.###',4,false}) do rejects(12.3,pattern) end
  rejects(12.3)
  for _,value in ipairs({'12.3','NaN','Infinity',false,{}}) do rejects(value,'#.##') end
  rejects(nil,'#.##')
end

-- Keep the original show/hide handlers; replace only their SDK data refresh
-- bodies with bounded source-template rows. This is not live SDK data proof.
local generalRefreshes,happinessRefreshes=0,0
local lastRow
vm.EconomicGeneralInfo.UpdateDisplay=function()
  generalRefreshes=generalRefreshes+1
  local env=vm.EconomicGeneralInfo
  env.Controls.MainStack:DestroyAllChildren()
  local row={};env.ContextPtr:BuildInstanceForControl('CityInstance',row,env.Controls.MainStack)
  row.HealthBar:SetFGColor({x=0,y=1,z=0,w=1});row.HealthBar:SetPercent(0.75)
  row.GrowthBar:SetPercent(0.25);row.GrowthBarShadow:SetPercent(0.4)
  row.ProductionBar:SetPercent(0.5);row.ProductionBarShadow:SetPercent(0.6)
  row.ProdButton:SetVoid1(7);row.ProdButton:SetVoid2(-1)
  row.ProdButton:RegisterCallback(env.Mouse.eLClick,env.OnProdClick)
  row.ProdButton:RegisterCallback(env.Mouse.eRClick,function(cityID,void2,handle)
    check(cityID==7 and void2==-1 and handle==row.ProdButton,'third callback handle was not original control')
    env.__thirdHandleChecked=true
  end)
  env.Controls.MainStack:CalculateSize();env.Controls.MainStack:ReprocessAnchoring()
  env.Controls.MainScroll:CalculateInternalSize()
  lastRow=row
end
vm.HappinessInfo.UpdateScreen=function()
  happinessRefreshes=happinessRefreshes+1
  local env=vm.HappinessInfo
  for _,id in ipairs({'HappinessStack','UnhappinessStack','ResourcesStack'}) do
    env.Controls[id]:CalculateSize();env.Controls[id]:ReprocessAnchoring()
  end
  for _,id in ipairs({'HappinessScroll','UnhappinessScroll','ResourcesScroll'}) do
    env.Controls[id]:CalculateInternalSize()
  end
end
local function synchronize()
  local parent=vm.parent
  for _,id in ipairs({'EconomicGeneralInfo','HappinessInfo'}) do
    vm[id].ZeroSisEconomicSetVisible(parent.ZeroSisUi.IsActive() and not parent.Controls[id]:IsHidden(),false)
  end
end
local function click(env,id)
  local key=env.__componentNode(assert(env.Controls[id])).key
  check(env.ZeroSisUi.DispatchLeftClick(key)==true,'original callback was not consumed: '..id)
end
local function snap()
  local value=vm.parent.ZeroSisUi.Snapshot()
  value.embeddedContexts=marked({
    {controlId='EconomicGeneralInfo',keyBase=281474976710656,snapshot=vm.EconomicGeneralInfo.ZeroSisUi.Snapshot()},
    {controlId='HappinessInfo',keyBase=562949953421312,snapshot=vm.HappinessInfo.ZeroSisUi.Snapshot()}})
  return value
end
vm.parent.ZeroSisUi.Submit({Type=905,Data1=-1})
synchronize()
check(timerBalance==1 and generalRefreshes==1 and happinessRefreshes==0,'parent open refreshed wrong child')
check(not vm.parent.Controls.EconomicGeneralInfo:IsHidden() and vm.parent.Controls.HappinessInfo:IsHidden(),
      'initial original tab visibility changed')
local first=snap()
check(first.timerSemaphore==1 and first.embeddedContexts[1].snapshot.timerSemaphore==0 and
      first.embeddedContexts[2].snapshot.timerSemaphore==0,'snapshot timer contract changed')
local oldKey=vm.EconomicGeneralInfo.__componentNode(lastRow.ProdButton).key
check(vm.EconomicGeneralInfo.ZeroSisUi.DispatchLeftClick(oldKey)==true and productionRequests[1]==7,
      'original OnProdClick did not route its city ID')
check(vm.EconomicGeneralInfo.ZeroSisUi.DispatchLeftClick(oldKey,vm.EconomicGeneralInfo.Mouse.eRClick)==true and
      vm.EconomicGeneralInfo.__thirdHandleChecked,'third callback handle check did not execute')
for _,invalid in ipairs({
  {Type=906,Data1=7,Data2=0,Data3=-1,Option1=false,Option2=false},
  {Type=906,Data1=7,Data2=-1,Data3=0,Option1=false,Option2=false},
  {Type=906,Data1=7,Data2=-1,Data3=-1,Option1=true,Option2=false},
  {Type=906,Data1=7,Data2=-1,Data3=-1,Option1=false,Option2=true},
  {Type=905,Data1=7,Data2=-1,Data3=-1,Option1=false,Option2=false}}) do
  check(not pcall(vm.EconomicGeneralInfo.Events.SerialEventGameMessagePopup,invalid),
        'non-original production popup tuple was accepted')
end
check(#productionRequests==1,'invalid popup tuple reached native command')
vm.parent.ZeroSisEconomicRefresh();synchronize()
check(timerBalance==1 and timerAcquisitions==1 and generalRefreshes==2,'repeat visible refresh reacquired timer')
check(vm.EconomicGeneralInfo.__componentNode(lastRow.ProdButton).key>oldKey and
      vm.EconomicGeneralInfo.ZeroSisUi.DispatchLeftClick(oldKey)==false,'stale instance key remained actionable')
click(vm.parent,'HappinessButton');synchronize()
check(happinessRefreshes==1 and timerBalance==1 and
      vm.parent.Controls.EconomicGeneralInfo:IsHidden() and not vm.parent.Controls.HappinessInfo:IsHidden(),
      'original Happiness tab did not switch child visibility')
check(#vm.EconomicGeneralInfo.ZeroSisUi.GetInputTargets()==0 and
      #vm.EconomicGeneralInfo.ZeroSisUi.GetScrollTargets()==0 and
      vm.EconomicGeneralInfo.ZeroSisUi.DispatchLeftClick(oldKey)==false,'hidden child exposed input')
local happiness=snap()
click(vm.parent,'GeneralInfoButton');synchronize()
check(generalRefreshes==3 and timerBalance==1,'original General tab did not refresh')
click(vm.parent,'CloseButton');synchronize()
check(timerBalance==0 and timerReleases==1,'original CloseButton leaked modal timer')
local closed=snap()
check(#closed.inputTargets==0 and #closed.embeddedContexts[1].snapshot.inputTargets==0 and
      #closed.embeddedContexts[2].snapshot.inputTargets==0,'closed parent left child input enabled')
vm.parent.ZeroSisUi.Submit({Type=905,Data1=-1});synchronize()
check(timerBalance==1 and timerAcquisitions==2 and generalRefreshes==4,'original reopen state changed')
check(vm.parent.ZeroSisUi.DispatchKeyDown(vm.parent.Keys.VK_ESCAPE),'original Escape did not close')
synchronize();check(timerBalance==0 and timerReleases==2,'Escape did not release parent semaphore')
return json({status='PASS_ECONOMIC_ORIGINAL_LUA_LIFECYCLE_COMPONENT_ONLY',checks=checks,
  sourceScriptsLoaded=marked({'EconomicOverview','EconomicGeneralInfo','HappinessInfo'}),
  childDataRefreshReplacedForFixture=true,liveSdkEconomicValuesVerified=false,
  nativeChildVmRoutingVerified=false,retailPixelsVerified=false,
  numberFormatting={numericCalls=numberCalls,rejectedArguments=rejectedNumberArguments,
    cases=marked({'positive','negative','zero','nan','positive-infinity','negative-infinity'}),
    nonFiniteValuesPreserved=true,nativeReturnPassedThrough=true,
    fixtureFormatter=true,retailIcuFormattingEquivalent=false},
  snapshots=marked({first,happiness,closed})})
'''


def verify_component() -> dict:
    prepared = prepared_sources()
    layouts = copy.deepcopy(prepared['xml_control_trees'])
    source_paths = {
        'scene': PROJECT / 'Source/Host/UiScene.lua',
        'input': PROJECT / 'Source/Presentation/UiPresentationInput.lua',
        'economic': PROJECT / 'Source/Presentation/UiEconomicOverview.lua',
        'parent': GAME / 'Assets/UI/InGame/Popups/EconomicOverview.lua',
        'EconomicGeneralInfo': GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/EconomicGeneralInfo.lua',
        'HappinessInfo': GAME / 'Assets/DLC/Expansion2/UI/InGame/Popups/HappinessInfo.lua',
        'IconSupport': GAME / 'Assets/UI/IconSupport.lua',
        'InstanceManager': GAME / 'Assets/UI/InstanceManager.lua',
        'FLuaVector': GAME / 'Assets/Gameplay/Lua/FLuaVector.lua',
    }
    source = {key: path.read_text(encoding='utf-8-sig') for key, path in source_paths.items()}
    # Inspect actual call sites in each complete original child script. The
    # inventory is checked against the live Locale table before stock init.
    locale_inventory = {
        slot: sorted(set(re.findall(r'\bLocale\s*\.\s*([A-Za-z_]\w*)\s*\(',
                                    re.sub(r'--[^\n]*', '', source[slot]))))
        for slot in ('EconomicGeneralInfo', 'HappinessInfo')}
    if not all(names for names in locale_inventory.values()):
        raise RuntimeError('Original economic Locale call inventory unexpectedly became empty')
    inline_path = PROJECT / 'evidence/ui_popup/assets/inline_icons.json'
    inline_icons = json.loads(inline_path.read_text(encoding='utf-8'))['icons']
    by_slot = {}
    with tempfile.TemporaryDirectory(prefix='zerosis-economic-component-') as temp:
        for slot, layout_name in (('parent', 'EconomicOverviewLayout'),
                                  ('EconomicGeneralInfo', 'EconomicGeneralLayout'),
                                  ('HappinessInfo', 'EconomicHappinessLayout')):
            tree = layouts[layout_name]
            style = production_style_defaults(Path(temp), tree)
            tree.update(styleDefaults=style['controls'], styleDefaultsSource=style['source'],
                        styleDefaultsPolicy=style['policy'])
            tree['fontMetrics'] = production_font_metrics(tree, inline_icons)
            tree['economicOverview'] = economic_overview_layout_metadata(layout_name)
            prepared['xml_control_trees'][layout_name] = tree
            by_slot[slot] = tree
        def assemble(sources):
            return (HARNESS.replace('@@SOURCES@@', lua_value(sources))
                    .replace('@@LAYOUTS@@', lua_value(by_slot))
                    .replace('@@LOCALE_INVENTORY@@', lua_value(locale_inventory)))
        assembled = assemble(source)
        result = execute_lua(assembled)
        missing_provider_rejected = []
        for source_key, before, after, method in (
            ('economic', 'Locale.ToNumber=function', 'Locale.ComponentMissingToNumber=function', 'ToNumber'),
            ('scene', 'Locale={ConvertTextKey=function', 'Locale={ComponentMissingConvertTextKey=function', 'ConvertTextKey'),
        ):
            if source[source_key].count(before) != 1:
                raise RuntimeError('Locale provider mutation boundary changed: ' + method)
            altered = {**source, source_key: source[source_key].replace(before, after, 1)}
            try:
                execute_lua(assemble(altered))
            except RuntimeError as error:
                if 'requires missing Locale.' + method not in str(error):
                    raise
                missing_provider_rejected.append(method)
            else:
                raise AssertionError('Original child Locale inventory accepted missing ' + method)
    snapshots = result.pop('snapshots')
    for snapshot in snapshots:
        compose_economic_overview_snapshot(snapshot, prepared)
    first = snapshots[0]['embeddedContexts'][0]['snapshot']
    health = next(node for node in economic_walk(first['tree']) if node.get('id') == 'HealthBar')
    assert health['percent'] == 0.75 and health['fgColor'] == {'x': 0, 'y': 1, 'z': 0, 'w': 1}
    result['actual_retained_snapshots_composed'] = len(snapshots)
    result['actual_bar_snapshot_verified'] = True
    result['original_child_locale_inventory'] = locale_inventory
    result['missing_locale_providers_rejected'] = missing_provider_rejected
    return result


if __name__ == '__main__':
    print(json.dumps(verify_component(), ensure_ascii=False))
