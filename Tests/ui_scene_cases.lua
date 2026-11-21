-- Component-only harness. Official Lua assets run against a bounded mock Game/UI.
-- This does not claim to verify Civ V's renderer, native event order or layout engine.
local SOURCE_INSTANCE_MANAGER = @@SOURCE_INSTANCE_MANAGER@@
local SOURCE_ICON_SUPPORT = @@SOURCE_ICON_SUPPORT@@
local SOURCE_FLUA_VECTOR = @@SOURCE_FLUA_VECTOR@@
local SOURCE_POPUP = @@SOURCE_POPUP@@
local SCENE_SOURCE = @@SCENE_SOURCE@@
ZeroSisUiLayout = @@LAYOUT@@
local PRODUCTION_FONT_METRICS = @@PRODUCTION_FONT_METRICS@@
local FAILURE_MODE = @@FAILURE_MODE@@

-- Keep these controls in an unattached Instance so ranking snapshots stay frozen.
table.insert(ZeroSisUiLayout.children,{kind='Instance',attributes={Name='UiSceneMethodCase'},children={
  {kind='Button',attributes={ID='CaseButton',Size='10,20'},children={}},
  {kind='Meter',attributes={ID='CaseMeter',Size='12,12'},children={}},
  {kind='Stack',attributes={ID='CaseStack',Size='40,20',StackGrowth='L',Padding='2'},children={
    {kind='Image',attributes={ID='CaseImageA',Size='10,8'},children={}},
    {kind='Image',attributes={ID='CaseImageB',Size='12,8'},children={}},
  }},
}})

local sequence = {0, 2, 0, 2, 3, 0, 6, 2}
local seed = 731
local nativeTimer = 0
local nativeTimerCalls = {}
local playerOneMet = true
local function nextRand(limit)
  local value = table.remove(sequence, 1)
  assert(value ~= nil, 'unexpected Game.Rand call')
  assert(type(limit) == 'number' and value >= 0 and value < limit,
    'fixture random value is outside the requested range')
  seed = seed + 1
  return value
end

ButtonPopupTypes = {BUTTONPOPUP_WHOS_WINNING = 101}
GameOptionTypes = {GAMEOPTION_NO_HAPPINESS = 1, GAMEOPTION_NO_SCIENCE = 2}
GameDefines = {MAX_MAJOR_CIVS = 2}
Game = {
  GetActivePlayer = function() return 0 end,
  GetActiveTeam = function() return 0 end,
  GetNumWorldWonders = function() return 1 end,
  IsOption = function() return false end,
  Rand = nextRand,
}
local function player(id)
  local result = {
    GetID = function() return id end,
    GetTeam = function() return id end,
    IsAlive = function() return true end,
    GetNumPolicies = function() return 3 end,
    GetCurrentEra = function() return 1 end,
    GetNumCivsInfluentialOn = function() return 0 end,
    GetTourism = function() return 0 end,
    GetNumWorldWonders = function() return id end,
    GetExcessHappiness = function() return 5 + id end,
    GetMilitaryMight = function() return 20 + id end,
    GetLeaderType = function() return id + 10 end,
    GetNameKey = function() return 'PLAYER_' .. id end,
    GetGold = function() return id == 0 and 40 or 20 end,
    GetNumCities = function() return 1 end,
    GetCityByID = function() return nil end,
    Cities = function()
      local emitted = false
      return function()
        if emitted then return nil end
        emitted = true
        return {
          GetCurrentProductionDifference = function() return id == 0 and 10 or 30 end,
          FoodDifference = function() return id + 1 end,
        }
      end
    end,
  }
  return result
end
Players = {[0] = player(0), [1] = player(1)}
local function team(id)
  return {
    IsHasMet = function() return id == 0 or playerOneMet end,
    GetTeamTechs = function()
      return {GetNumTechsKnown = function() return 4 + id end}
    end,
  }
end
Teams = {[0] = team(0), [1] = team(1)}
GameInfo = {
  Eras = {ERA_INDUSTRIAL = {ID = 5}},
  Leaders = {
    [10] = {Description = 'LEADER_ZERO', PortraitIndex = 0, IconAtlas = 'LEADERS'},
    [11] = {Description = 'LEADER_ONE', PortraitIndex = 1, IconAtlas = 'LEADERS'},
  },
  Civilizations = {
    [1] = {ID = 1, DefaultPlayerColor = 1, PortraitIndex = 0,
      AlphaIconAtlas = 'CIV_ALPHA', IconAtlas = 'CIV'},
    [2] = {ID = 2, DefaultPlayerColor = 2, PortraitIndex = 1,
      AlphaIconAtlas = 'CIV_ALPHA', IconAtlas = 'CIV'},
    CIVILIZATION_MINOR = {ID = -1},
  },
  PlayerColors = {
    [1] = {ID = 1, PrimaryColor = 'P1', SecondaryColor = 'S1'},
    [2] = {ID = 2, PrimaryColor = 'P2', SecondaryColor = 'S2'},
    [3] = {ID = 3, PrimaryColor = 'P3', SecondaryColor = 'S3'},
  },
  Colors = {
    P1 = {Red = 1, Green = 0, Blue = 0, Alpha = 1},
    S1 = {Red = 0, Green = 0, Blue = 0, Alpha = 1},
    P2 = {Red = 0, Green = 1, Blue = 0, Alpha = 1},
    S2 = {Red = 0, Green = 0, Blue = 0, Alpha = 1},
    P3 = {Red = 0, Green = 0, Blue = 1, Alpha = 1},
    S3 = {Red = 1, Green = 1, Blue = 0, Alpha = 1},
  },
  IconTextureAtlases = function()
    local rows = {
      {Atlas = 'CIV', IconSize = 32, Filename = 'CIV32.dds', IconsPerRow = 4, IconsPerColumn = 8},
      {Atlas = 'CIV_ALPHA', IconSize = 24, Filename = 'CIV_ALPHA24.dds', IconsPerRow = 4, IconsPerColumn = 8},
      {Atlas = 'CIV_COLOR_ATLAS', IconSize = 32, Filename = 'CIV_COLOR32.dds', IconsPerRow = 4, IconsPerColumn = 8},
      {Atlas = 'LEADERS', IconSize = 64, Filename = 'LEADERS64.dds', IconsPerRow = 4, IconsPerColumn = 8},
      {Atlas = 'LEADER_ATLAS', IconSize = 64, Filename = 'LEADER_UNMET64.dds', IconsPerRow = 4, IconsPerColumn = 8},
    }
    local index = 0
    return function()
      index = index + 1
      return rows[index]
    end
  end,
}
ZeroSisUiNative = function(operation, ...)
  local values = {...}
  if operation == 'snapshotJson' then
    return __ZeroSisSnapshotJson(...)
  elseif operation == 'locale' then
    local result = tostring(values[1] or '')
    for i = 2, #values do result = result .. ':' .. tostring(values[i]) end
    return result
  elseif operation == 'civilization' or operation == 'playerColor' then
    local id = values[1]
    if operation == 'playerColor' and id == 1 then return 3 end
    return id < 0 and -1 or id + 1
  elseif operation == 'timer' then
    assert(#values == 1 and (values[1] == 1 or values[1] == -1), 'invalid mock timer delta')
    if values[1] == 1 then
      assert(nativeTimer == 0, 'native timer acquired twice')
      nativeTimer = 1
    else
      assert(nativeTimer == 1, 'native timer released without acquisition')
      nativeTimer = 0
    end
    nativeTimerCalls[#nativeTimerCalls + 1] = values[1]
    return nil
  elseif operation == 'randomSeed' then
    return seed
  elseif operation == 'screenSize' then
    return 1920, 1080
  end
  error('unsupported test native operation: ' .. tostring(operation))
end

local sources = {
  InstanceManager = SOURCE_INSTANCE_MANAGER,
  IconSupport = SOURCE_ICON_SUPPORT,
  FLuaVector = SOURCE_FLUA_VECTOR,
  WhosWinningPopup = SOURCE_POPUP,
  ZeroSisUiScene = SCENE_SOURCE,
}
include = function(name)
  local source = assert(sources[name], 'unfrozen include requested: ' .. tostring(name))
  return assert(loadstring(source, '@' .. name))()
end
include('ZeroSisUiScene')

local clickHandler, inputHandler
local registerCallback = Controls.CloseButton.RegisterCallback
Controls.CloseButton.RegisterCallback = function(self, eventName, callback)
  if eventName == Mouse.eLClick then clickHandler = callback end
  return registerCallback(self, eventName, callback)
end
local setInputHandler = ContextPtr.SetInputHandler
ContextPtr.SetInputHandler = function(self, callback)
  inputHandler = callback
  return setInputHandler(self, callback)
end
include('WhosWinningPopup')
assert(type(clickHandler) == 'function' and type(inputHandler) == 'function',
  'official popup did not register its close button and input handler')
if FAILURE_MODE == 'shown' then
  Events.SerialEventGameMessagePopupShown.Add(function() error('INJECTED_SHOWN_HANDLER_FAILURE') end)
elseif FAILURE_MODE == 'processed' then
  Events.SerialEventGameMessagePopupProcessed.Add(function() error('INJECTED_PROCESSED_HANDLER_FAILURE') end)
end

if FAILURE_MODE == 'shown' then
  local ok, failure = pcall(ZeroSisUi.Submit, {Type = ButtonPopupTypes.BUTTONPOPUP_WHOS_WINNING})
  assert(not ok and tostring(failure):find('INJECTED_SHOWN_HANDLER_FAILURE', 1, true),
    'shown-handler fault was not propagated')
  assert(nativeTimer == 1 and #nativeTimerCalls == 1 and nativeTimerCalls[1] == 1,
    'shown-handler injection did not fail after native timer acquisition')
  -- Model the one compensation the C++ fault path must perform after Lua unwinds.
  -- The VM is then discarded; calling its broken close path would double-decrement.
  ZeroSisUiNative('timer', -1)
  assert(nativeTimer == 0 and #nativeTimerCalls == 2 and nativeTimerCalls[2] == -1,
    'shown-handler fault compensation was not balanced exactly once')
  local retried, retryFailure = pcall(ZeroSisUi.Close)
  assert(not retried and retryFailure and nativeTimer == 0 and #nativeTimerCalls == 2,
    'faulted shown-handler VM was incorrectly reusable')
  __uiSceneComponentReport = '{"injection":"shown","original_error":"INJECTED_SHOWN_HANDLER_FAILURE",' ..
    '"timer_after_fault_compensation":' .. tostring(nativeTimer) ..
    ',"timer_calls":[' .. table.concat(nativeTimerCalls, ',') ..
    '],"lua_vm_discard_required":true,"faulted_lua_retry_rejected":true}'
  return
elseif FAILURE_MODE == 'processed' then
  ZeroSisUi.Submit({Type = ButtonPopupTypes.BUTTONPOPUP_WHOS_WINNING})
  local ok, failure = pcall(ZeroSisUi.Close)
  assert(not ok and tostring(failure):find('INJECTED_PROCESSED_HANDLER_FAILURE', 1, true),
    'processed-handler fault was not propagated')
  assert(nativeTimer == 0 and #nativeTimerCalls == 2 and nativeTimerCalls[1] == 1 and nativeTimerCalls[2] == -1,
    'processed-handler injection did not fail after one native timer release')
  local retried, retryFailure = pcall(ZeroSisUi.Close)
  assert(not retried and retryFailure and nativeTimer == 0 and #nativeTimerCalls == 2,
    'faulted processed-handler VM was incorrectly reusable')
  __uiSceneComponentReport = '{"injection":"processed","original_error":"INJECTED_PROCESSED_HANDLER_FAILURE",' ..
    '"timer_after_fault":' .. tostring(nativeTimer) ..
    ',"timer_calls":[' .. table.concat(nativeTimerCalls, ',') ..
    '],"lua_vm_discard_required":true,"faulted_lua_retry_rejected":true}'
  return
end

local seedBeforeForeignPopup = seed
Events.SerialEventGameMessagePopup({Type = 999})
assert(seed == seedBeforeForeignPopup and not ZeroSisUi.IsActive(),
  'nonmatching popup consumed RNG or became active')
local accepted, failure = pcall(ZeroSisUi.Submit, {Type = 999})
assert(not accepted and failure and seed == seedBeforeForeignPopup,
  'host adapter accepted an unsupported popup or consumed RNG')

ZeroSisUi.Submit({Type = ButtonPopupTypes.BUTTONPOPUP_WHOS_WINNING})
local first = ZeroSisUi.Snapshot()
assert(ZeroSisUi.IsActive(), 'first official popup did not become active')
local activeSeed = seed
local activeCalls = #sequence
local reentered, reentryFailure = pcall(ZeroSisUi.Submit, {Type = ButtonPopupTypes.BUTTONPOPUP_WHOS_WINNING})
assert(not reentered and reentryFailure and seed == activeSeed and #sequence == activeCalls,
  'reentrant popup submission mutated RNG while the popup was active')
local beforeRejectedCalls = ZeroSisUi.Snapshot()
local malformedColor, colorFailure = pcall(function()
  Controls.PresentsLabel:SetColor({x = 1, y = 2, z = 3})
end)
assert(not malformedColor and colorFailure and ZeroSisUi.Snapshot() == beforeRejectedCalls,
  'malformed color changed the retained control snapshot')
local unsupportedMethod, unsupportedFailure = pcall(function()
  Controls.PresentsLabel:SortChildren()
end)
assert(not unsupportedMethod and unsupportedFailure and ZeroSisUi.Snapshot() == beforeRejectedCalls,
  'unsupported control method was accepted or mutated the scene')
assert(inputHandler(KeyEvents.KeyDown, Keys.VK_ESCAPE, 0) == true,
  'Escape did not close the first popup')
assert(not ZeroSisUi.IsActive(), 'Escape left first popup active')
local firstCopy = first

-- The immediately repeated Gold draw must be rejected; Science is accepted.
ZeroSisUi.Submit({Type = ButtonPopupTypes.BUTTONPOPUP_WHOS_WINNING})
local second = ZeroSisUi.Snapshot()
assert(ZeroSisUi.IsActive(), 'second official popup did not become active')
clickHandler()
assert(not ZeroSisUi.IsActive(), 'official close-button callback left popup active')
assert(first == firstCopy, 'a prior owned snapshot changed after a later popup')

-- Wonders is invalid with only one world wonder, so the next Gold draw is used.
playerOneMet = false
ZeroSisUi.Submit({Type = ButtonPopupTypes.BUTTONPOPUP_WHOS_WINNING})
local third = ZeroSisUi.Snapshot()
local methodCase={}
ContextPtr:BuildInstance('UiSceneMethodCase',methodCase)
assert(type(methodCase.CaseButton)=='table' and type(methodCase.CaseMeter)=='table' and type(methodCase.CaseStack)=='table',
  'dynamic instance did not retain button, meter and stack controls')
methodCase.CaseButton:SetVoid1('unit');methodCase.CaseButton:SetVoid2(7)
local received
methodCase.CaseButton:RegisterCallback(Mouse.eLClick,function(firstArg,secondArg) received={firstArg,secondArg} end)
methodCase.CaseButton:RegisterCallback(Mouse.eRClick,function(firstArg,secondArg) received={firstArg,secondArg,'right'} end)
assert(type(received)=='nil','registered callback ran without an input event')
methodCase.CaseButton:ClearCallback(Mouse.eLClick)
methodCase.CaseButton:ClearCallback(Mouse.eRClick)
methodCase.CaseButton:SetSize({x=18,y=26})
assert(methodCase.CaseButton:GetSize().x==18 and methodCase.CaseButton:GetSize().y==26,'GetSize/SetSize vector contract failed')
methodCase.CaseButton:SetSize({y=28})
assert(methodCase.CaseButton:GetSize().x==18 and methodCase.CaseButton:GetSize().y==28,'partial vector SetSize did not preserve the omitted axis')
methodCase.CaseButton:SetSizeY(31);methodCase.CaseButton:SetOffsetVal(3,4)
assert(methodCase.CaseButton:GetSize().y==31,'SetSizeY contract failed')
methodCase.CaseButton:SetText('plain');assert(methodCase.CaseButton:GetText()=='plain','SetText/GetText contract failed')
methodCase.CaseButton:LocalizeAndSetText('KEY',2);assert(methodCase.CaseButton:GetText()=='KEY:2','localized text contract failed')
methodCase.CaseButton:LocalizeAndSetToolTip('TIP',3);methodCase.CaseButton:SetToolTipString('tip')
methodCase.CaseMeter:SetPercent(0.5);methodCase.CaseMeter:SetPercents(0.25,0.75)
methodCase.CaseStack:CalculateSize();methodCase.CaseStack:ReprocessAnchoring()
assert(ContextPtr:IsHidden()==false,'ContextPtr:IsHidden reported visible popup as hidden')
assert(inputHandler(KeyEvents.KeyDown, Keys.VK_RETURN, 0) == true,
  'Return did not close the third popup')
assert(not ZeroSisUi.IsActive() and #sequence == 0,
  'popup lifecycle or deterministic random fixture did not finish cleanly')
assert(first == firstCopy and type(second) == 'string' and type(third) == 'string',
  'snapshot ownership was not preserved')
assert(nativeTimer == 0 and #nativeTimerCalls == 6,
  'native timer adapter did not observe three balanced popup lifecycles')

__uiSceneComponentReport = '{"first":' .. first .. ',"second":' .. second ..
  ',"third":' .. third .. ',"finalSeed":' .. tostring(seed) ..
  ',"nativeTimer":' .. tostring(nativeTimer) ..
  ',"nativeTimerCalls":[' .. table.concat(nativeTimerCalls, ',') .. ']}'
assert(ContextPtr:IsHidden(),'ContextPtr:IsHidden did not report the closed context')
local screenWidth,screenHeight=UIManager:GetScreenSizeVal()
assert(screenWidth==1920 and screenHeight==1080,'logical viewport query did not return its explicit dimensions')
ContextPtr:SetHide(false)
assert(not ContextPtr:IsHidden() and ZeroSisUi.IsActive(),'ContextPtr:SetHide(false) did not show the owned context')
ContextPtr:SetHide(true)
assert(ContextPtr:IsHidden() and not ZeroSisUi.IsActive(),'ContextPtr:SetHide(true) did not close the owned context')
local eventCalls=0
local eventHandler=function(owner,cityID) assert(owner==4 and cityID==9);eventCalls=eventCalls+1 end
Events.UnitSelectionChanged.Add(eventHandler)
Events.UnitSelectionChanged.Add(eventHandler)
Events.UnitSelectionChanged(4,9)
Events.UnitSelectionChanged.Remove(eventHandler)
Events.UnitSelectionChanged.CallImmediate(4,9)
assert(eventCalls==1,'event Add/Remove/callable dispatch contract failed')
local unsupportedWorldInput,worldInputError=pcall(UI.DoSelectCityAtPlot,{})
assert(not unsupportedWorldInput and worldInputError,'unsupported world selection was accepted as a no-op')

-- Run a second isolated Production scene to exercise official style defaults
-- and the non-geometric ShowOnMouseOver wrapper without changing ranking data.
local productionStyleDefaults={
  ScrollBarUp={attributes={Texture='Assets/UI/Art/Controls/ScrollBarUp.dds',Size='18,18'}},
  ScrollBarDown={attributes={Texture='Assets/UI/Art/Controls/ScrollBarDown.dds',Size='18,18'}},
  VertShuttle={attributes={Texture='Assets/UI/Art/Controls/9 Grids/ScrollBar.DDS',Size='18,18',Vertical='1',
    StateOffsetIncrement='0,18',UCSize='18,3',UCTexStart='0,0',CSize='18,1',CTexStart='0,3',
    LCSize='18,3',LCTexStart='0,15'}},
  VertSlider={attributes={Texture='Assets/UI/Art/Controls/ScrollBarBack.dds',Size='18,18',Vertical='1',
    StateOffsetIncrement='0,0',UCSize='18,0',ULCexStart='0,0',CSize='18,6',CTexStart='0,6',
    LCSize='18,0',LCTexStart='0,12'},children={{kind='Shuttle',style='VertShuttle',
      attributes={Style='VertShuttle',Size='18,18',Texture='Assets/UI/Art/Controls/9 Grids/ScrollBar.DDS',
        Vertical='1',StateOffsetIncrement='0,18',UCSize='18,3',UCTexStart='0,0',CSize='18,1',
        CTexStart='0,3',LCSize='18,3',LCTexStart='0,15'},children={}}}},
}
local productionFont=assert(PRODUCTION_FONT_METRICS.fonts.TwCenMT20)
local productionGlyphs=assert(PRODUCTION_FONT_METRICS.glyphSets[productionFont.glyphSet])
local wrapWidth=productionGlyphs[87].advance+productionGlyphs[73].advance
assert(wrapWidth>0,'prepared TwCenMT20 glyphgen metrics are invalid')
local productionLayout={contextName='ProductionPopup',popupKind='Production',attributes={},styleDefaults=productionStyleDefaults,
  styleDefaultsSource={path='Assets/UI/Styles.xml',sha256='fixture'},
  styleDefaultsPolicy='OFFICIAL_STYLES_XML_ATTRIBUTES_WITH_CONTROL_XML_OVERRIDES',
  fontMetrics=PRODUCTION_FONT_METRICS,children={
  {kind='Button',attributes={ID='OwnerButton',Size='340,42',Offset='100,200'},children={
    {kind='ShowOnMouseOver',attributes={ID='HoverFrame'},children={
      {kind='AlphaAnim',attributes={ID='HoverAnim',Anchor='C,C',Offset='10,0',Size='340,45',Pause='0',
        Cycle='Bounce',Speed='1',AlphaStart='2',AlphaEnd='1'},children={}},
      {kind='Button',attributes={ID='HoverOnlyButton',Size='20,10',Anchor='L,T'},children={}},
    }},
  }},
  {kind='ScrollPanel',attributes={ID='StylePanel',Size='340,400',Vertical='1'},children={
    {kind='ScrollBar',attributes={ID='StyleScrollBar',Style='VertSlider',Length='300'},children={}},
    {kind='UpButton',attributes={ID='StyleUpButton',Style='ScrollBarUp'},children={}},
    {kind='DownButton',attributes={ID='StyleDownButton',Style='ScrollBarDown'},children={}},
    {kind='Button',attributes={ID='PanelHit',Size='40,40',Anchor='L,T',Offset='330,390'},children={}},
  }},
  {kind='ScrollPanel',attributes={ID='OuterScroll',Size='100,100',Vertical='1',Anchor='L,T',Offset='500,700'},children={
    {kind='ScrollPanel',attributes={ID='NestedScroll',Size='150,150',Vertical='1',Anchor='L,T',Offset='50,50'},children={
      {kind='Button',attributes={ID='TallContent',Size='50,250',Anchor='L,T'},children={}},
    }},
    {kind='ScrollPanel',attributes={ID='HiddenScroll',Size='20,20',Vertical='1',Hidden='1'},children={}},
  }},
  {kind='ScrollPanel',attributes={ID='StaticScroll',Size='80,40',Vertical='1',Anchor='L,T',Offset='900,700'},children={
    {kind='Button',attributes={ID='ShortContent',Size='20,20',Anchor='L,T'},children={}},
  }},
  {kind='Label',attributes={ID='MeasuredLabel',String='WIWI',Font='TwCenMT20',WrapWidth=tostring(wrapWidth),
    Anchor='C,C'},children={}},
  {kind='Label',attributes={ID='InlineIconLabel',String='[ICON_PRODUCTION]',Font='TwCenMT20',
    Anchor='L,T',Offset='20,600'},children={}},
  {kind='Label',attributes={ID='LocalizedMeasureLabel',String='',Font='TwCenMT20',Anchor='C,C'},children={}},
  {kind='Stack',attributes={ID='BottomRows',Size='150,0',Offset='450,300',Anchor='L,T',
    StackGrowth='Bottom',Padding='0'},children={
    {kind='Label',attributes={ID='HiddenStaleRow',String='W',Font='TwCenMT20',Anchor='L,C',Offset='0,0',Hidden='1'},children={}},
    {kind='Label',attributes={ID='BottomRowA',String='W',Font='TwCenMT20',Anchor='L,C',Offset='3,2'},children={}},
    {kind='Label',attributes={ID='BottomRowB',String='I',Font='TwCenMT20',Anchor='L,C',Offset='5,4'},children={}},
  }},
  {kind='Stack',attributes={ID='RightRows',Size='0,40',Offset='700,300',Anchor='L,T',
    StackGrowth='Right',Padding='2'},children={
    {kind='Label',attributes={ID='RightRowA',String='W',Font='TwCenMT20',Anchor='R,C',Offset='2,3'},children={}},
    {kind='Label',attributes={ID='RightRowB',String='I',Font='TwCenMT20',Anchor='L,T',Offset='5,6'},children={}},
  }},
  {kind='Button',attributes={ID='PartialButton',Size='20,20',Anchor='L,T',Offset='-10,500'},children={}},
}}
local productionEnv=setmetatable({ZeroSisUiLayout=productionLayout,ZeroSisUiNative=function(operation,...)
  if operation=='snapshotJson' then return __ZeroSisSnapshotJson(...) end
  if operation=='uiFrameTime' then return 0 end
  if operation=='randomSeed' then return 19 end
  if operation=='locale' then
    local key=select(1,...)
    if key=='TEST_LOCALIZED_LABEL' then return 'WIWI' end
    error('unexpected Production fixture localization key: '..tostring(key))
  end
  error('unexpected Production style fixture native operation: '..tostring(operation))
end,Game={Rand=function() return 0 end}}, {__index=_G})
local productionChunk=assert(loadstring(SCENE_SOURCE,'@production-style-fixture'))
setfenv(productionChunk,productionEnv);productionChunk()
productionEnv.ContextPtr:SetHide(false)
productionEnv.Controls.OwnerButton:SetVoid1('row-owner')
productionEnv.Controls.OwnerButton:SetVoid2(87)
productionEnv.Controls.OwnerButton:RegisterCallback(Mouse.eLClick,function() end)
productionEnv.Controls.HoverOnlyButton:RegisterCallback(Mouse.eLClick,function() end)
productionEnv.Controls.PanelHit:RegisterCallback(Mouse.eLClick,function() end)
productionEnv.Controls.PartialButton:RegisterCallback(Mouse.eLClick,function() end)
productionEnv.Controls.LocalizedMeasureLabel:LocalizeAndSetText('TEST_LOCALIZED_LABEL')
local localizedWidth=productionEnv.Controls.LocalizedMeasureLabel:GetSize().x
assert(localizedWidth==2*productionGlyphs[87].advance+2*productionGlyphs[73].advance,
  'LocalizeAndSetText did not refresh exact Production glyphgen width')
local previousText=productionEnv.Controls.MeasuredLabel:GetText()
local missingGlyphAccepted=pcall(function() productionEnv.Controls.MeasuredLabel:SetText('\244\143\191\191') end)
assert(not missingGlyphAccepted and productionEnv.Controls.MeasuredLabel:GetText()==previousText,
  'Missing original font glyph did not fail closed without changing the label')
productionEnv.Controls.BottomRows:CalculateSize()
productionEnv.Controls.BottomRows:ReprocessAnchoring()
productionEnv.Controls.RightRows:CalculateSize()
productionEnv.Controls.RightRows:ReprocessAnchoring()
local scrollSize=productionEnv.Controls.StyleScrollBar:GetSize()
local upSize=productionEnv.Controls.StyleUpButton:GetSize()
local downSize=productionEnv.Controls.StyleDownButton:GetSize()
local wrapperSize=productionEnv.Controls.HoverFrame:GetSize()
assert(scrollSize.x==18 and scrollSize.y==300,'official VertSlider defaults/Length did not resolve to 18x300')
assert(upSize.x==18 and upSize.y==18 and downSize.x==18 and downSize.y==18,
  'official scrollbar button style defaults did not resolve to 18x18')
assert(wrapperSize.x==340 and wrapperSize.y==42,
  'ShowOnMouseOver did not inherit its owning button frame')
productionEnv.Controls.StylePanel:CalculateInternalSize()
productionEnv.Controls.NestedScroll:CalculateInternalSize()
productionEnv.Controls.OuterScroll:CalculateInternalSize()
productionEnv.Controls.StaticScroll:CalculateInternalSize()
local productionSnapshot=productionEnv.ZeroSisUi.Snapshot()
assert(productionSnapshot:find('"groupGeometryPolicy":"SHOW_ON_MOUSE_OVER_INHERITS_OWNING_BUTTON_FRAME"',1,true),
  'Production geometry policy was not recorded')
assert(productionSnapshot:find('"styleDefaultsPolicy":"OFFICIAL_STYLES_XML_ATTRIBUTES_WITH_CONTROL_XML_OVERRIDES"',1,true),
  'Production style defaults policy was not recorded')
assert(productionSnapshot:find('"x":110,"y":198.5',1,true),
  'ShowOnMouseOver child was not anchored from the inherited button frame')
assert(productionSnapshot:find('"sourceAttributes":{"ID":"StyleScrollBar","Length":"300","Style":"VertSlider"}',1,true),
  'Production snapshot did not preserve the original style-control XML attributes')
assert(productionSnapshot:find('"policy":"CIV5_GLYPHGEN_GGXML_LAYOUT_V1"',1,true),
  'Production glyphgen metric policy was not captured')
assert(productionSnapshot:find('"id":"MeasuredLabel"',1,true) and
  productionSnapshot:find('"text":"WI"',1,true),
  'Production exact glyph advances did not split an over-width word at a codepoint boundary')
assert(productionSnapshot:find('"id":"BottomRowA"',1,true) and
  productionSnapshot:find('"y":302',1,true),
  'Bottom-growth stack row was centered on the flow axis or lost its authored offset')
assert(productionSnapshot:find('"id":"BottomRowB"',1,true) and
  productionSnapshot:find('"y":'..tostring(300+productionFont.lineAdvance+4),1,true),
  'Bottom-growth stack slot did not follow the preceding visible row')
assert(productionSnapshot:find('"id":"HiddenStaleRow"',1,true) and
  productionSnapshot:find('"hidden":true',1,true),
  'Hidden recycled stack row was not preserved as hidden state')
assert(productionSnapshot:find('"id":"RightRowA"',1,true) and
  productionSnapshot:find('"x":702',1,true),
  'Right-growth stack slot did not preserve its flow offset and cross-axis anchor')
assert(productionSnapshot:find('"id":"RightRowB"',1,true) and
  productionSnapshot:find('"x":'..tostring(700+productionGlyphs[87].advance+2+5),1,true),
  'Right-growth stack did not advance by the actual prior label width')
assert(productionSnapshot:find('"textFrame":',1,true) and
  productionSnapshot:find('"fontMetricSource":{"ggxmlPath":',1,true),
  'Production label frame or GGXML metric provenance was not captured')
assert(productionSnapshot:find('"text":"\243\176\128\128"',1,true),
  'Official inline icon markup was not expanded to its renderer codepoint')
assert(productionSnapshot:find('"inputTargets":[{"bounds":',1,true) and
  productionSnapshot:find('"event":"LeftClick"',1,true) and
  productionSnapshot:find('"void1":"row-owner"',1,true),
  'Production hit metadata did not reflect the registered LeftClick owner callback')
local function findJsonNumber(source,key,id)
  local list=assert(source:find('"scrollTargets":[',1,true),'missing scroll target list')
  local start=assert(source:find('"id":"'..id..'"',list,true),'missing scroll target '..id)
  local objectStart
  for index=start-1,list,-1 do
    if source:sub(index,index)=='{' then objectStart=index;break end
  end
  assert(objectStart,'missing scroll target object start')
  local _,finish=source:find('}',start,true)
  local region=source:sub(objectStart,finish or #source)
  local numberText=assert((region:match('"'..key..'":([%-%d%.]+)')),
    'missing '..key..' for scroll target '..id)
  return tonumber(numberText)
end
local scrollListStart=assert(productionSnapshot:find('"scrollTargets":[',1,true))
local function jsonArrayEnd(source,start)
  local depth,inString,escaped=0,false,false
  for index=start,#source do
    local character=source:sub(index,index)
    if inString then
      if escaped then escaped=false
      elseif character=='\\' then escaped=true
      elseif character=='"' then inString=false end
    elseif character=='"' then inString=true
    elseif character=='[' then depth=depth+1
    elseif character==']' then
      depth=depth-1
      if depth==0 then return index end
    end
  end
  error('unterminated scroll target array')
end
local scrollListEnd=jsonArrayEnd(productionSnapshot,scrollListStart)
local function hasScrollTarget(id)
  local position=productionSnapshot:find('"id":"'..id..'"',scrollListStart,true)
  return position~=nil and position<scrollListEnd
end
assert(productionSnapshot:find('"scrollTargets":[',1,true),
  'Production snapshot omitted the separate scroll target manifest')
assert(hasScrollTarget('StylePanel') and
  findJsonNumber(productionSnapshot,'contentHeight','StylePanel')==430 and
  findJsonNumber(productionSnapshot,'maximumScroll','StylePanel')==30 and
  findJsonNumber(productionSnapshot,'viewportHeight','StylePanel')==400,
  'Production ScrollPanel range did not use calculated content and viewport geometry')
assert(hasScrollTarget('NestedScroll') and
  productionSnapshot:find('"clippedBounds":{"height":50,"width":50,"x":550,"y":750}',1,true) and
  findJsonNumber(productionSnapshot,'maximumScroll','NestedScroll')==100,
  'Nested ScrollPanel did not retain ancestor clipping or real maximum scroll')
assert(hasScrollTarget('StaticScroll'),'Visible non-scrollable ScrollPanel was omitted')
assert(findJsonNumber(productionSnapshot,'maximumScroll','StaticScroll')==0,
  'Non-scrollable ScrollPanel did not report zero maximum scroll')
assert(not hasScrollTarget('HiddenScroll'),'Hidden ScrollPanel appeared as a target')
productionEnv.ContextPtr:SetHide(true)
local hiddenSnapshot=productionEnv.ZeroSisUi.Snapshot()
assert(hiddenSnapshot:find('"scrollTargets":[]',1,true),
  'Inactive Production context retained scroll targets')
productionEnv.ContextPtr:SetHide(false)
__uiSceneComponentReport=__uiSceneComponentReport:sub(1,-2)..',"production":'..productionSnapshot..
  ',"productionTestExpected":{"pairAdvance":'..tostring(wrapWidth)..
  ',"wAdvance":'..tostring(productionGlyphs[87].advance)..
  ',"iconAdvance":'..tostring(PRODUCTION_FONT_METRICS.inlineIcons.ICON_PRODUCTION.advance)..'}}'
