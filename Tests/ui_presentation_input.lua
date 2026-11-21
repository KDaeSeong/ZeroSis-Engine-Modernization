-- Component-only harness. Official Lua assets run against a bounded mock Game/UI.
-- This does not claim to verify Civ V's renderer, native event order or layout engine.
local SOURCE_INSTANCE_MANAGER = @@SOURCE_INSTANCE_MANAGER@@
local SOURCE_ICON_SUPPORT = @@SOURCE_ICON_SUPPORT@@
local SOURCE_FLUA_VECTOR = @@SOURCE_FLUA_VECTOR@@
local SOURCE_POPUP = @@SOURCE_POPUP@@
local SCENE_SOURCE = @@SCENE_SOURCE@@
local RESEARCH_INPUT_CASE = @@RESEARCH_INPUT_CASE@@
local RESEARCH_TREE_INPUT_CASE = @@RESEARCH_TREE_INPUT_CASE@@
ZeroSisUiLayout = @@LAYOUT@@
local FAILURE_MODE = @@FAILURE_MODE@@
-- Research/UnitPanel input fixtures use inert style rows. Naming that scope
-- lets their actual retained snapshots be compared without claiming artwork.
ZeroSisUiLayout.styleDefaultsSource = ZeroSisUiLayout.styleDefaultsSource or 'component-fixture:input-only'
ZeroSisUiLayout.styleDefaultsPolicy = ZeroSisUiLayout.styleDefaultsPolicy or 'INERT_INPUT_ONLY_NO_VISUAL_CLAIM'

-- The detached template exercises `<Button>` input without changing frozen ranking snapshots.
table.insert(ZeroSisUiLayout.children,{kind='Instance',attributes={Name='UiInputButtonCase'},children={
  {kind='Button',attributes={ID='InputButton',Size='10,20'},children={}},
}})
table.insert(ZeroSisUiLayout.children,{kind='Instance',attributes={Name='UiInputScrollCase'},children={
  {kind='ScrollPanel',attributes={ID='InputScrollPanel',Offset='500,300',Size='200,80',Vertical='1'},children={
    {kind='Button',attributes={ID='InputScrollRow1',Offset='0,0',Size='160,32'},children={}},
    {kind='Button',attributes={ID='InputScrollRow2',Offset='0,120',Size='160,32'},children={}},
  }},
}})
table.insert(ZeroSisUiLayout.children,{kind='Instance',attributes={Name='UiInputResearchTreeScrollCase'},children={
  {kind='ScrollPanel',attributes={ID='ResearchTreeScrollPanel',Offset='760,420',Size='120,80',Vertical='0'},children={
    {kind='Button',attributes={ID='ResearchTreeScrollRow1',Offset='0,0',Size='100,32'},children={}},
    {kind='Button',attributes={ID='ResearchTreeScrollRow2',Offset='200,0',Size='100,32'},children={}},
  }},
}})

local sequence = {0, 2, 0, 2, 3, 0, 6, 2}
local seed = 731
local nativeTimer = 0
local nativeTimerCalls = {}
local uiClock = 0
local freezeUiClock = false
local playerOneMet = true
local function nextRand(limit)
  local value = table.remove(sequence, 1)
  assert(value ~= nil, 'unexpected Game.Rand call')
  assert(type(limit) == 'number' and value >= 0 and value < limit,
    'fixture random value is outside the requested range')
  seed = seed + 1
  return value
end

ButtonPopupTypes = {BUTTONPOPUP_WHOS_WINNING = 101, BUTTONPOPUP_TECH_TREE = 67}
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
  if operation == 'locale' then
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
  elseif operation == 'smallUiAssets' then
    return false
  elseif operation == 'uiFrameTime' then
    if not freezeUiClock then uiClock = uiClock + 0.25 end
    return uiClock
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

if RESEARCH_INPUT_CASE then
  local callbacks=0
  local callbackVoids
  local button={}
  ContextPtr:BuildInstance('UiInputButtonCase',button)
  button.InputButton:SetVoids(17,23)
  button.InputButton:RegisterCallback(Mouse.eLClick,function(a,b) callbacks=callbacks+1;callbackVoids={a,b} end)
  local beforeInactive=ZeroSisUi.GetInputTargets(Mouse.eLClick)
  assert(#beforeInactive==0 and not ZeroSisUi.DispatchLeftClick(999999),
    'inactive Research timer-0 context exposed or accepted a stale row')
  ContextPtr:SetHide(false)
  assert(ZeroSisUi.IsActive(),'Research TechPopup context did not activate at timer 0')
  -- This input fixture reuses the stock ranking layout. Match the original
  -- WhosWinningPopup.lua sizing sequence before taking its full snapshot.
  Controls.PlayerListStack:CalculateSize()
  Controls.PlayerListStack:ReprocessAnchoring()
  Controls.PlayerListScrollPanel:CalculateInternalSize()
  local targets=ZeroSisUi.GetInputTargets(Mouse.eLClick)
  assert(#targets==1 and targets[1].id=='InputButton','active Research timer-0 row was not exposed')
  assert(targets[1].void1==17 and targets[1].void2==23,
    'Research input target did not preserve its optional scalar void pair')
  assert(ZeroSisUi.DispatchPointerMove(targets[1].key),'Research pointer move did not use the retained frame clock')
  assert(uiClock>0,'Research pointer move did not advance the retained UI clock')
  freezeUiClock=true
  local hoverClock=uiClock
  local hoveredSnapshot=ZeroSisUi.Snapshot()
  assert(ZeroSisUi.DispatchPointerMove(targets[1].key) and ZeroSisUi.Snapshot()==hoveredSnapshot,
    'Research repeated hover changed its actual retained snapshot at the same owner clock')
  assert(ZeroSisUi.DispatchPointerMove(0),'Research pointer leave was rejected')
  local clearedSnapshot=ZeroSisUi.Snapshot()
  assert(clearedSnapshot~=hoveredSnapshot,
    'Research hover leave did not change the retained button state at the same owner clock')
  assert(ZeroSisUi.DispatchPointerMove(0) and ZeroSisUi.Snapshot()==clearedSnapshot,
    'Research repeated key-zero clear changed its retained snapshot')
  assert(not ZeroSisUi.DispatchPointerMove(999999) and ZeroSisUi.Snapshot()==clearedSnapshot,
    'Research rejected pointer changed its retained snapshot')
  assert(uiClock==hoverClock and callbacks==0,
    'Research hover consumed owner time or invoked its click callback')
  freezeUiClock=false
  assert(ZeroSisUi.DispatchLeftClick(targets[1].key),'Research timer-0 click was not delivered')
  assert(callbacks==1,'Research callback did not run exactly once')
  assert(callbackVoids[1]==17 and callbackVoids[2]==23,
    'Research callback dispatch changed its target void arguments')
  ContextPtr:SetHide(true)
  assert(not ZeroSisUi.IsActive() and #ZeroSisUi.GetInputTargets(Mouse.eLClick)==0 and
    not ZeroSisUi.DispatchLeftClick(targets[1].key),'closed Research context accepted a stale row')
  __uiSceneComponentReport='{"researchInput":true,"timer":0,"clock":'..tostring(uiClock)..
    ',"clicks":'..tostring(callbacks)..',"inactiveRejected":true,"staleRejected":true,'..
    '"fixedClockRepeatedHoverUnchanged":true,"fixedClockKeyZeroUnchanged":true,'..
    '"fixedClockHoverLeaveChanged":true}'
  return
end

if RESEARCH_TREE_INPUT_CASE then
  local callbacks=0
  local callbackVoids
  local button={}
  ContextPtr:BuildInstance('UiInputButtonCase',button)
  button.InputButton:SetVoids(7,0)
  button.InputButton:RegisterCallback(Mouse.eLClick,function(a,b)
    callbacks=callbacks+1;callbackVoids={a,b}
  end)
  button.InputButton:RegisterCallback(Mouse.eRClick,function() error('ResearchTree must not dispatch right-click') end)
  local panel={}
  ContextPtr:BuildInstance('UiInputResearchTreeScrollCase',panel)
  panel.ResearchTreeScrollPanel:CalculateInternalSize()
  panel.ResearchTreeScrollPanel:ReprocessAnchoring()
  local row1,row2=0,0
  panel.ResearchTreeScrollRow1:RegisterCallback(Mouse.eLClick,function() row1=row1+1 end)
  panel.ResearchTreeScrollRow2:SetVoids(8,0)
  panel.ResearchTreeScrollRow2:RegisterCallback(Mouse.eLClick,function() row2=row2+1 end)
  local beforeSeed=seed
  ContextPtr:SetShowHideHandler(function(hidden,initializing)
    if not initializing then
      if hidden then UI.decTurnTimerSemaphore() else UI.incTurnTimerSemaphore() end
    end
  end)
  UIManager:QueuePopup(ContextPtr,PopupPriority.TechTree)
  Events.SerialEventGameMessagePopupShown.CallImmediate({Type=ButtonPopupTypes.BUTTONPOPUP_TECH_TREE})
  assert(nativeTimer==1 and ZeroSisUi.IsActive(),'ResearchTree did not enter its shown timer-1 state')
  local shown=ZeroSisUi.Snapshot()
  assert(shown:find('"popupKind":"ResearchTree"',1,true) and
    shown:find('"contextName":"TechTree"',1,true) and
    shown:find('"lifecycle":["queued","shown:67"]',1,true),
    'ResearchTree JSON snapshot lost its exact queued/shown context lifecycle')
  local flushCount=0
  local originalFlush=ZeroSisUi.FlushLayout
  ZeroSisUi.FlushLayout=function() flushCount=flushCount+1;return originalFlush() end

  local beforeEnumerate=flushCount
  local leftTargets=ZeroSisUi.GetInputTargets()
  assert(flushCount==beforeEnumerate+1,'ResearchTree GetInputTargets omitted its layout barrier')
  assert(#leftTargets==#ZeroSisUi.GetInputTargets(Mouse.eLClick) and
    #ZeroSisUi.GetInputTargets(Mouse.eRClick)==0,
    'ResearchTree collector exposed non-left callbacks')
  local function inputTarget(id,eventName)
    for _,target in ipairs(ZeroSisUi.GetInputTargets(eventName)) do
      if target.id==id then return target end
    end
  end
  local buttonTarget=assert(inputTarget('InputButton',Mouse.eLClick),
    'visible TechTree left-click row was not returned')
  assert(not inputTarget('InputButton',Mouse.eRClick),
    'ResearchTree right-click target was returned')
  local snapshotLeft,snapshotRight=0,0
  local leftRow='"event":"LeftClick","id":"InputButton","key":'..tostring(buttonTarget.key)
  local rightRow='"event":"RightClick","id":"InputButton","key":'..tostring(buttonTarget.key)
  if shown:find(leftRow,1,true) then snapshotLeft=1 end
  if shown:find(rightRow,1,true) then snapshotRight=1 end
  assert(snapshotLeft==1 and snapshotRight==1,
    'ResearchTree snapshot did not retain both stock callback metadata rows')
  assert(not ZeroSisUi.DispatchLeftClick(buttonTarget.key,Mouse.eRClick),
    'ResearchTree dispatched a forbidden right-click callback')
  assert(ZeroSisUi.DispatchPointerMove(buttonTarget.key) and uiClock>0,
    'ResearchTree pointer move did not update its retained frame clock')
  freezeUiClock=true
  local hoverClock=uiClock
  local hoveredSnapshot=ZeroSisUi.Snapshot()
  assert(ZeroSisUi.DispatchPointerMove(buttonTarget.key) and ZeroSisUi.Snapshot()==hoveredSnapshot,
    'ResearchTree repeated hover changed its actual retained snapshot at the same owner clock')
  assert(ZeroSisUi.DispatchPointerMove(0),'ResearchTree pointer leave was rejected')
  local clearedSnapshot=ZeroSisUi.Snapshot()
  assert(clearedSnapshot~=hoveredSnapshot and ZeroSisUi.DispatchPointerMove(0) and
    ZeroSisUi.Snapshot()==clearedSnapshot,
    'ResearchTree hover leave or repeated key-zero snapshot differs')
  assert(uiClock==hoverClock and callbacks==0 and row1==0 and row2==0,
    'ResearchTree hover advanced owner time or dispatched a callback')
  freezeUiClock=false
  local stateBeforeClick={active=ZeroSisUi.IsActive(),timer=nativeTimer,seed=seed,turn=0}
  local beforeDispatch=flushCount
  assert(ZeroSisUi.DispatchLeftClick(buttonTarget.key,Mouse.eLClick),
    'ResearchTree normal left-click callback was not delivered')
  assert(flushCount==beforeDispatch+2,
    'ResearchTree left-click did not flush layout before dispatch and after callback')
  assert(callbacks==1 and callbackVoids[1]==7 and callbackVoids[2]==0,
    'ResearchTree callback did not preserve its normal (tech,0) payload')
  assert(ZeroSisUi.IsActive()==stateBeforeClick.active and nativeTimer==stateBeforeClick.timer and
    seed==stateBeforeClick.seed and stateBeforeClick.turn==0,
    'ResearchTree selection closed or mutated timer, RNG or turn state')

  local function scrollTarget(id)
    for _,target in ipairs(ZeroSisUi.GetScrollTargets()) do
      if target.id==id then return target end
    end
  end
  local beforeScrollEnumerate=flushCount
  local wheel=assert(scrollTarget('ResearchTreeScrollPanel'),
    'TechTree horizontal ScrollPanel was not a wheel target')
  assert(flushCount==beforeScrollEnumerate+1,'ResearchTree GetScrollTargets omitted its layout barrier')
  assert(wheel.event=='Scroll' and wheel.orientation=='horizontal' and wheel.scrollX==0 and
    wheel.maximumScroll==180,
    'ResearchTree horizontal wheel target did not expose its measured scroll range')
  local maximumScroll=wheel.maximumScroll
  assert(not ZeroSisUi.DispatchScroll(wheel.key,0) and
    not ZeroSisUi.DispatchScroll(wheel.key,math.huge) and
    not ZeroSisUi.DispatchScroll(wheel.key,32768.5),
    'ResearchTree horizontal wheel accepted invalid deltas')
  assert(ZeroSisUi.DispatchScroll(wheel.key,240) and
    panel.ResearchTreeScrollPanel:GetScrollValue()==180,
    'ResearchTree wheel did not clamp to the measured horizontal range')
  wheel=assert(scrollTarget('ResearchTreeScrollPanel'))
  assert(wheel.scrollX==180 and wheel.maximumScroll==180 and
    inputTarget('ResearchTreeScrollRow2',Mouse.eLClick),
    'ResearchTree horizontal scroll did not reflow the newly visible technology row')
  assert(row1==0 and row2==0,'ResearchTree wheel invoked a click callback')
  assert(ZeroSisUi.DispatchScroll(wheel.key,-240) and
    panel.ResearchTreeScrollPanel:GetScrollValue()==0 and
    not inputTarget('ResearchTreeScrollRow2',Mouse.eLClick),
    'ResearchTree negative wheel did not restore the original horizontal viewport')
  wheel=assert(scrollTarget('ResearchTreeScrollPanel'))
  assert(wheel.scrollX==0 and wheel.maximumScroll==maximumScroll,
    'ResearchTree horizontal scroll target did not report its restored range')
  assert(seed==beforeSeed,'ResearchTree queue/input/scroll consumed gameplay RNG')

  UIManager:DequeuePopup(ContextPtr)
  Events.SerialEventGameMessagePopupProcessed.CallImmediate(ButtonPopupTypes.BUTTONPOPUP_TECH_TREE,0)
  local closed=ZeroSisUi.Snapshot()
  assert(not ZeroSisUi.IsActive() and nativeTimer==0 and #ZeroSisUi.GetInputTargets()==0 and
    not ZeroSisUi.DispatchLeftClick(buttonTarget.key),
    'closed ResearchTree retained or dispatched stale input')
  assert(closed:find('"lifecycle":["queued","shown:67","closed","processed:67"]',1,true) and
    nativeTimerCalls[1]==1 and nativeTimerCalls[2]==-1,
    'ResearchTree close did not release exactly one turn-timer semaphore')
  __uiSceneComponentReport='{"researchTreeInput":true,"timerOpen":1,"timerClosed":0,'..
    '"clock":'..tostring(uiClock)..',"clicks":'..tostring(callbacks)..
    ',"scrollX":'..tostring(wheel.scrollX)..',"maximumScroll":'..tostring(wheel.maximumScroll)..
    ',"lifecycle":"queued,shown:67,closed,processed:67","rngUnchanged":true,'..
    '"fixedClockRepeatedHoverUnchanged":true,"fixedClockKeyZeroUnchanged":true,'..
    '"fixedClockHoverLeaveChanged":true,"sdkReceiverExecuted":false,"gamecoreExecuted":false}'
  return
end

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
assert(ZeroSisUi.DispatchKeyDown(Keys.VK_ESCAPE) == true,
  'Escape did not close the first popup')
assert(not ZeroSisUi.IsActive(), 'Escape left first popup active')
local firstCopy = first

-- The immediately repeated Gold draw must be rejected; Science is accepted.
ZeroSisUi.Submit({Type = ButtonPopupTypes.BUTTONPOPUP_WHOS_WINNING})
local second = ZeroSisUi.Snapshot()
assert(ZeroSisUi.IsActive(), 'second official popup did not become active')
local repaintSeed = seed
local repaintOne, repaintTwo = ZeroSisUi.Snapshot(), ZeroSisUi.Snapshot()
assert(repaintOne == repaintTwo and seed == repaintSeed, 'repaint snapshot changed or consumed gameplay RNG')
local targets = ZeroSisUi.GetInputTargets()
assert(#targets == 1 and targets[1].id == 'CloseButton', 'official visible close button missing from targets')
assert(targets[1].void1==nil and targets[1].void2==nil,
  'ranking-popup input target schema changed with production-only button arguments')
assert(ZeroSisUi.DispatchLeftClick(targets[1].key) == true, 'left click was not delivered to official callback')
assert(not ZeroSisUi.IsActive(), 'official close-button callback left popup active')
local callsAfterClick = #nativeTimerCalls
assert(ZeroSisUi.DispatchLeftClick(targets[1].key) == false, 'closed scene accepted duplicate click')
assert(ZeroSisUi.DispatchKeyDown(Keys.VK_ESCAPE) == false, 'closed scene accepted duplicate key')
assert(ZeroSisUi.DispatchKeyDown(65) == false, 'unknown key was not ignored')
assert(#nativeTimerCalls == callsAfterClick and nativeTimer == 0, 'closed repeat changed timer lifecycle')
assert(first == firstCopy, 'a prior owned snapshot changed after a later popup')

-- Wonders is invalid with only one world wonder, so the next Gold draw is used.
playerOneMet = false
ZeroSisUi.Submit({Type = ButtonPopupTypes.BUTTONPOPUP_WHOS_WINNING})
local third = ZeroSisUi.Snapshot()
local thirdTargets = ZeroSisUi.GetInputTargets()
assert(#thirdTargets == 1 and thirdTargets[1].id == 'CloseButton', 'third popup target mismatch')
assert(ZeroSisUi.DispatchLeftClick(1.5) == false and ZeroSisUi.DispatchLeftClick('1') == false and ZeroSisUi.DispatchLeftClick(4294967295) == false, 'malformed or stale key accepted')
Controls.CloseButton:SetHide(true)
assert(ZeroSisUi.DispatchLeftClick(thirdTargets[1].key) == false and #ZeroSisUi.GetInputTargets() == 0, 'hidden button accepted input')
Controls.CloseButton:SetHide(false)
local buttonCase={}
ContextPtr:BuildInstance('UiInputButtonCase',buttonCase)
buttonCase.InputButton:SetVoids(44,55)
local received
buttonCase.InputButton:RegisterCallback(Mouse.eLClick,function(a,b) received={a,b,'left'} end)
buttonCase.InputButton:RegisterCallback(Mouse.eRClick,function(a,b) received={a,b,'right'} end)
local withDynamicButton=ZeroSisUi.GetInputTargets()
assert(#withDynamicButton==3 and withDynamicButton[2].id=='InputButton' and
  withDynamicButton[2].event==Mouse.eLClick and withDynamicButton[3].event==Mouse.eRClick,
  'dynamic Button did not expose both registered pointer callbacks')
assert(withDynamicButton[2].void1==nil and withDynamicButton[2].void2==nil,
  'ranking popup leaked production-only void arguments into exported targets')
local leftOnly=ZeroSisUi.GetInputTargets(Mouse.eLClick)
local rightOnly=ZeroSisUi.GetInputTargets(Mouse.eRClick)
assert(#leftOnly==2 and leftOnly[2].id=='InputButton' and leftOnly[2].event==Mouse.eLClick,
  'left-click event filter did not retain only left callbacks')
assert(#rightOnly==1 and rightOnly[1].id=='InputButton' and rightOnly[1].event==Mouse.eRClick,
  'right-click event filter did not retain only right callbacks')
local badFilterOk=pcall(ZeroSisUi.GetInputTargets,'not-an-event')
assert(not badFilterOk,'unsupported target event filter was accepted')
assert(ZeroSisUi.DispatchLeftClick(withDynamicButton[2].key,withDynamicButton[2].event) and
  received[1]==44 and received[2]==55 and received[3]=='left','Button callback lost its void arguments')
assert(ZeroSisUi.DispatchLeftClick(withDynamicButton[3].key,withDynamicButton[3].event) and
  received[3]=='right','Button right-click callback did not dispatch')
buttonCase.InputButton:ClearCallback(Mouse.eLClick)
assert(not ZeroSisUi.DispatchLeftClick(withDynamicButton[2].key,withDynamicButton[2].event) and
  #ZeroSisUi.GetInputTargets()==2,'cleared Button callback remained dispatchable')
buttonCase.InputButton:ClearCallback(Mouse.eRClick)
assert(#ZeroSisUi.GetInputTargets()==1,'cleared right-click callback remained an input target')
local scrollCase={}
ContextPtr:BuildInstance('UiInputScrollCase',scrollCase)
scrollCase.InputScrollPanel:CalculateInternalSize()
scrollCase.InputScrollPanel:ReprocessAnchoring()
local scrollRowCalls=0
scrollCase.InputScrollRow1:RegisterCallback(Mouse.eLClick,function() scrollRowCalls=scrollRowCalls+1 end)
scrollCase.InputScrollRow2:RegisterCallback(Mouse.eLClick,function() scrollRowCalls=scrollRowCalls+1 end)
local function targetFor(id,event)
  for _,target in ipairs(ZeroSisUi.GetInputTargets(event)) do
    if target.id==id then return target end
  end
end
local function scrollTargetFor(id)
  for _,target in ipairs(ZeroSisUi.GetScrollTargets()) do
    if target.id==id then return target end
  end
end
local ownedScrollTarget=assert(scrollTargetFor('InputScrollPanel'),'visible ScrollPanel was not a wheel target')
assert(ownedScrollTarget.event=='Scroll' and ownedScrollTarget.key>0,
  'ScrollPanel target did not expose its retained key and Scroll event')
assert(#ZeroSisUi.GetScrollTargets()>=1,'scroll collector returned no visible scroll viewport')
local firstScrollTarget=assert(targetFor('InputScrollRow1',Mouse.eLClick),'visible scroll row was not an input target')
assert(not targetFor('InputScrollRow2',Mouse.eLClick),'clipped-off scroll row was incorrectly exposed')
freezeUiClock=true
local hoverClock=uiClock
local beforeHover=ZeroSisUi.Snapshot()
assert(ZeroSisUi.DispatchPointerMove(firstScrollTarget.key),'pointer move did not accept a live input row')
local duringHover=ZeroSisUi.Snapshot()
assert(ZeroSisUi.DispatchPointerMove(firstScrollTarget.key) and ZeroSisUi.Snapshot()==duringHover,
  'repeated popup row hover changed its actual retained snapshot at the same owner clock')
assert(not ZeroSisUi.DispatchPointerMove(999999),'pointer move accepted a stale retained key')
assert(ZeroSisUi.Snapshot()==duringHover,'rejected popup row hover changed its retained snapshot')
assert(ZeroSisUi.DispatchPointerMove(0),'pointer key zero did not clear hover')
local afterHover=ZeroSisUi.Snapshot()
assert(ZeroSisUi.DispatchPointerMove(0) and ZeroSisUi.Snapshot()==afterHover,
  'repeated popup key-zero clear changed its retained snapshot')
assert(beforeHover==afterHover and uiClock==hoverClock,
  'popup hover changed owner time or failed to restore its prior retained state')
freezeUiClock=false
local closeTarget=assert(targetFor('CloseButton',Mouse.eLClick),'close button target is missing')
local beforeScroll=ZeroSisUi.Snapshot()
assert(not ZeroSisUi.DispatchScroll(closeTarget.key,48),
  'scroll accepted an unrelated button identity without an owning ScrollPanel')
assert(not ZeroSisUi.DispatchScroll(firstScrollTarget.key,0) and
  not ZeroSisUi.DispatchScroll(firstScrollTarget.key,math.huge) and
  not ZeroSisUi.DispatchScroll(firstScrollTarget.key,32768.5),
  'scroll accepted zero, infinite, or over-limit pixel delta')
assert(ZeroSisUi.DispatchScroll(ownedScrollTarget.key,48),'finite empty-panel-owned scroll was not consumed')
assert(ZeroSisUi.Snapshot()~=beforeScroll,'consumed scroll did not change the actual retained viewport snapshot')
local secondScrollTarget=assert(targetFor('InputScrollRow2',Mouse.eLClick),
  '48-pixel scroll did not move the partially visible row into the viewport')
assert(ZeroSisUi.DispatchScroll(ownedScrollTarget.key,1000),'large finite ScrollPanel-owned scroll was not consumed')
assert(targetFor('InputScrollRow2',Mouse.eLClick),'positive scroll did not clamp at the content bottom')
assert(ZeroSisUi.DispatchScroll(ownedScrollTarget.key,-1000) and not targetFor('InputScrollRow2',Mouse.eLClick) and
  targetFor('InputScrollRow1',Mouse.eLClick),'negative scroll did not clamp at zero')
assert(scrollRowCalls==0,'scroll and pointer input invoked a click callback')
assert(ZeroSisUi.DispatchKeyDown(Keys.VK_RETURN) == true,
  'Return did not close the third popup')
assert(not ZeroSisUi.IsActive() and #sequence == 0,
  'popup lifecycle or deterministic random fixture did not finish cleanly')
assert(first == firstCopy and type(second) == 'string' and type(third) == 'string',
  'snapshot ownership was not preserved')
assert(nativeTimer == 0 and #nativeTimerCalls == 6,
  'native timer adapter did not observe three balanced popup lifecycles')

__uiSceneComponentReport = '{"first":' .. first .. ',"second":' .. second ..
  ',"third":' .. third .. ',"finalSeed":' .. tostring(seed) ..
  ',"fixedClockRepeatedHoverUnchanged":true,"fixedClockKeyZeroUnchanged":true' ..
  ',"scrollSnapshotChanged":true' ..
  ',"nativeTimer":' .. tostring(nativeTimer) ..
  ',"nativeTimerCalls":[' .. table.concat(nativeTimerCalls, ',') .. ']}'
