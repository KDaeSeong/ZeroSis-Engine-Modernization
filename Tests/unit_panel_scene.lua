-- Focused UnitPanel input regression. Controls are declared by the verifier in
-- the frozen layout and this fixture checks ConsumeMouse target semantics.
ContextPtr:SetHide(false)
assert(ZeroSisUi.IsActive(), 'UnitPanel context did not become active')
-- The input-only UnitPanel fixture retains the stock ranking layout. Perform
-- its original sizing sequence before requesting a complete retained snapshot.
Controls.PlayerListStack:CalculateSize()
Controls.PlayerListStack:ReprocessAnchoring()
Controls.PlayerListScrollPanel:CalculateInternalSize()

local controls = {}
ContextPtr:BuildInstance('UnitPanelInputCase', controls)
local calls = 0
controls.UnitPanelConsumeClick:RegisterCallback(Mouse.eLClick, function() calls = calls + 1 end)
controls.UnitPanelNormalClick:RegisterCallback(Mouse.eLClick, function() calls = calls + 1 end)

local allTargets = ZeroSisUi.GetInputTargets()
local leftTargets = ZeroSisUi.GetInputTargets(Mouse.eLClick)
local rightTargets = ZeroSisUi.GetInputTargets(Mouse.eRClick)
local function findTarget(targets, id, event)
  for _, target in ipairs(targets) do
    if target.id == id and target.event == event then return target end
  end
end

assert(findTarget(allTargets, 'UnitPanelConsumeOnly', 'ConsumeMouse'),
  'ConsumeMouse control without a callback was not exposed')
assert(findTarget(leftTargets, 'UnitPanelConsumeClick', Mouse.eLClick),
  'ConsumeMouse control with a left callback lost its click target')
assert(not findTarget(allTargets, 'UnitPanelConsumeClick', 'ConsumeMouse'),
  'ConsumeMouse duplicated a registered left-click target')
assert(findTarget(leftTargets, 'UnitPanelNormalClick', Mouse.eLClick),
  'ordinary UnitPanel left-click target was not exposed')
assert(not findTarget(rightTargets, 'UnitPanelConsumeOnly', 'ConsumeMouse') and
  not findTarget(rightTargets, 'UnitPanelNormalClick', Mouse.eLClick),
  'UnitPanel event filtering returned an unrelated target')

local clickable = assert(findTarget(leftTargets, 'UnitPanelConsumeClick', Mouse.eLClick))
-- Use the same owner-clock provider as the surrounding real UiScene harness.
-- Only time is held fixed; snapshots and pointer dispatch are production Lua.
freezeUiClock = true
local hoverClock = uiClock
local beforeHover = ZeroSisUi.Snapshot()
assert(ZeroSisUi.DispatchPointerMove(clickable.key), 'live UnitPanel hover was rejected')
local hovered = ZeroSisUi.Snapshot()
assert(hovered ~= beforeHover, 'UnitPanel hover did not change its retained button state')
assert(ZeroSisUi.DispatchPointerMove(clickable.key) and ZeroSisUi.Snapshot() == hovered,
  'same-key UnitPanel hover changed its retained snapshot at the same owner clock')
assert(not ZeroSisUi.DispatchPointerMove(999999) and ZeroSisUi.Snapshot() == hovered,
  'rejected UnitPanel hover changed its retained snapshot')
assert(ZeroSisUi.DispatchPointerMove(0), 'UnitPanel pointer leave was rejected')
local cleared = ZeroSisUi.Snapshot()
assert(cleared ~= hovered and cleared == beforeHover,
  'UnitPanel pointer leave did not restore its retained button state')
assert(ZeroSisUi.DispatchPointerMove(0) and ZeroSisUi.Snapshot() == cleared,
  'repeated UnitPanel key-zero clear changed its retained snapshot')
assert(uiClock == hoverClock and calls == 0,
  'UnitPanel pointer dispatch advanced owner time or invoked a click callback')
freezeUiClock = false
assert(ZeroSisUi.DispatchLeftClick(clickable.key), 'registered UnitPanel click was rejected')
assert(calls == 1, 'registered UnitPanel callback did not run exactly once')
assert(not ZeroSisUi.DispatchLeftClick(999999), 'stale UnitPanel key was accepted')

ContextPtr:SetHide(true)
assert(#ZeroSisUi.GetInputTargets() == 0 and not ZeroSisUi.DispatchLeftClick(clickable.key),
  'hidden UnitPanel context exposed or accepted stale input')
__uiSceneComponentReport = '{"unitPanelInput":true,"consumeOnly":true,' ..
  '"consumeClickDeduplicated":true,"clicks":' .. tostring(calls) ..
  ',"hiddenRejected":true,"fixedClockRepeatedHoverUnchanged":true,' ..
  '"fixedClockKeyZeroUnchanged":true,"fixedClockHoverLeaveChanged":true}'
