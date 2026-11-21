-- Focused UnitPanel addendum contract test. The test does not emulate the game
-- renderer; it checks that the stock callback keeps its index and defers SDK
-- action execution until the callback has returned.
local SOURCE = @@UNIT_PANEL_ADDENDUM@@

local nativeCalls={}
local inCallback=false
local dirtyHandlers={}
local removed={}
local visible=true
local updateCallback=nil
local updates=0
local refreshes=0
local portraitCall=nil
native=function(name,...)
  if name=='unitPortrait' then
    portraitCall={...}
    return 19,'UNIT_PORTRAIT_ATLAS'
  end
  if name=='unitPanelAction' then
    assert(inCallback, 'SDK action must be queued while the original callback is active')
    local index=...
    nativeCalls[#nativeCalls+1]=index
    return true
  end
  if name=='headSelectedUnit' then return nil,nil end
  if name=='isTouchScreen' then return false end
  error('unexpected native operation: '..tostring(name))
end
hasRetainedUnitUi=true
contextName='UnitPanel'
popupKind='UnitPanel'
Players={}
Game={CanHandleAction=function(index) return index==17 end,
  HandleAction=function() error('stock Game.HandleAction should be wrapped') end}
local canHandleAction=Game.CanHandleAction
GameInfoActions={[17]={ActionInfoIndex=17,Type='MISSION_FORTIFY'}}
GameInfo={Units={[42]={UnitFlagAtlas='UNIT_FLAG_ATLAS'}}}
local originalHeadCity=function() return 'existing city binding' end
UI={GetHeadSelectedCity=originalHeadCity}
Controls={UnitActionMouseover={},UnitActionHotKey={},UnitActionText={},UnitActionHelp={}}
ContextPtr={
  SetUpdate=function(self,callback) updateCallback=callback end,
  IsHidden=function() return not visible end,
  SetHide=function(self,value) visible=not value end,
}
local function event()
  return {
    Add=function(callback) dirtyHandlers[#dirtyHandlers+1]=callback end,
    Remove=function(callback) removed[#removed+1]=callback end,
    CallImmediate=function(...)
      local snapshot={}
      for index,callback in ipairs(dirtyHandlers) do snapshot[index]=callback end
      for _,callback in ipairs(snapshot) do callback(...) end
    end,
  }
end
Events={SerialEventUnitInfoDirty=event(),GameplaySetActivePlayer=event(),
  ActivePlayerTurnEnd=event(),ActivePlayerTurnStart=event()}
LuaEvents={EnemyPanelHide=event()}
local stockActionCallback
function include(name)
  assert(name=='UnitPanel','addendum must include the original UnitPanel script')
  function RefreshInfoPane() refreshes=refreshes+1 end
  function OnInfoPaneDirty() dirtyPending=true end
  function OnActivePlayerChanged() end
  function OnActivePlayerTurnEnd() end
  function OnActivePlayerTurnStart() end
  function OnEnemyPanelHide() end
  function OnUnitActionClicked(index) Game.HandleAction(index) end
  stockActionCallback=OnUnitActionClicked
  Events.SerialEventUnitInfoDirty.Add(OnInfoPaneDirty)
  ContextPtr:SetUpdate(function()
    if dirtyPending then dirtyPending=false;updates=updates+1;RefreshInfoPane() end
  end)
  RefreshInfoPane()
end
ZeroSisUi={}
assert(loadstring(SOURCE,'@UiUnitPanel.lua'))()

assert(Game.CanHandleAction==canHandleAction,
  'The original SDK Game.CanHandleAction binding must remain untouched')
assert(UI.GetHeadSelectedCity==originalHeadCity,
  'The UnitPanel addendum must preserve the original city lookup')
local unit={GetUnitType=function() return 42 end,GetOwner=function() return 3 end,
  GetUnitFlagIconOffset=function() return 7 end}
local flagOffset,flagAtlas=UI.GetUnitFlagIcon(unit)
assert(flagOffset==7 and flagAtlas=='UNIT_FLAG_ATLAS',
  'unit flag icon must return the SDK offset and GameInfo atlas tuple')
local portraitOffset,portraitAtlas=UI.GetUnitPortraitIcon(unit)
assert(portraitOffset==19 and portraitAtlas=='UNIT_PORTRAIT_ATLAS' and
  portraitCall[1]==42 and portraitCall[2]==3,
  'unit portrait must use original unit type and owner identity')
assert(ZeroSisUi.unitPanelRefresh()==true and refreshes==2 and updates==1,
  'refresh must use the stock dirty event and coalesced update callback')
inCallback=true
stockActionCallback(17)
inCallback=false
assert(#nativeCalls==1 and nativeCalls[1]==17,
  'stock click callback must forward the exact GameInfoActions index')
assert(GameInfoActions[17].ActionInfoIndex==17,
  'the original action catalogue must remain available')
assert(ZeroSisUi.unitPanelStop()==true and not visible and #removed==5 and updateCallback==nil,
  'stop must hide the panel, unregister stock events, and clear its update callback')
hasRetainedUnitUi=false
assert(loadstring(SOURCE,'@UiUnitPanel.lua inactive context'))()

__uiSceneComponentReport='{"status":"PASS_UNIT_PANEL_ORIGINAL_ACTION_BRIDGE","queuedActionIndex":'..
  tostring(nativeCalls[1])..',"stockDirtyRefreshes":'..tostring(updates)..
  ',"sdkActionExecuted":false,"rendererVerified":false}'
