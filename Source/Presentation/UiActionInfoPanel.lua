-- Dedicated nonmodal bridge for the unchanged BNW ActionInfoPanel script.
-- Concatenated after UiScene in one chunk, before the original script is loaded.
if hasRetainedActionInfoUi then
assert(contextName=='ActionInfoPanel' and popupKind=='ActionInfoPanel',
  'ActionInfoPanel addendum requires its original retained context')

local function integer(value,name)
  assert(type(value)=='number' and value==value and value~=math.huge and
    value~=-math.huge and value==math.floor(value),name..' must be an integer')
  return value
end
local function booleanQuery(operation)
  local value=native(operation)
  assert(type(value)=='boolean',operation..' must return the actual native boolean')
  return value
end
assert(type(Game)=='table' and type(Game.IsProcessingMessages)=='function' and
  type(Game.DoControl)=='function' and type(EndTurnBlockingTypes)=='table',
  'ActionInfoPanel requires original SDK gameplay and blocking enums')

UI.CanEndTurn=function() return booleanQuery('actionInfoCanEndTurn') end
UI.WaitingForRemotePlayers=function() return booleanQuery('actionInfoWaitingForRemotePlayers') end
PreGame.IsMultiplayerGame=function() return booleanQuery('actionInfoMultiplayer') end
Network=Network or {}
Network.HasSentNetTurnComplete=function() return booleanQuery('actionInfoNetTurnComplete') end
Network.HasSentNetTurnAllComplete=function() return booleanQuery('actionInfoNetTurnAllComplete') end
Network.SendTurnUnready=function()
  error('ActionInfoPanel multiplayer turn readiness is not integrated')
end
OptionsManager.GetAutoUnitCycle=function()
  error('ActionInfoPanel automatic unit-cycling preferences are not integrated')
end
UI.GetHeadSelectedUnit=function()
  local owner,id=native('headSelectedUnit')
  if owner==nil and id==nil then return nil end
  owner=integer(owner,'selected unit owner');id=integer(id,'selected unit ID')
  assert(owner>=0 and id>=0,'Selected unit identity is invalid')
  return assert(assert(Players[owner],'Selected unit player is missing'):GetUnitByID(id),
    'Selected SDK unit no longer exists')
end
UI.ActivateNotification=function(id)
  return native('actionInfoActivateNotification',integer(id,'notification ID'))
end
UI.RemoveNotification=function(id)
  return native('actionInfoRemoveNotification',integer(id,'notification ID'))
end
UI.SelectUnit=function(unit)
  assert(unit and type(unit.GetID)=='function' and type(unit.GetOwner)=='function',
    'ActionInfoPanel selection requires an original SDK unit')
  return native('actionInfoSelectUnit',integer(unit:GetOwner(),'unit owner'),integer(unit:GetID(),'unit ID'))
end
UI.LookAt=function(plot,lookAtType)
  assert(plot and type(plot.GetX)=='function' and type(plot.GetY)=='function',
    'ActionInfoPanel camera requires an actual SDK plot')
  return native('actionInfoLookAt',integer(plot:GetX(),'plot x'),integer(plot:GetY(),'plot y'),
    integer(lookAtType,'camera look-at type'))
end
Game.DoControl=function(control)
  control=integer(control,'Game.DoControl control')
  assert(control==GameInfoTypes.CONTROL_ENDTURN,'ActionInfoPanel may only request original end-turn control')
  return native('actionInfoEndTurn',control)
end
include('FLuaVector')
ToHexFromGrid=function(grid)
  assert(type(grid)=='table','ActionInfoPanel grid coordinate must be a Vector2')
  local x,y=integer(grid.x,'grid x'),integer(grid.y,'grid y')
  return Vector2(x-math.floor(y/2),y)
end

local stopped=false
lifecycle[#lifecycle+1]='queued'
ZeroSisUi.actionInfoPanelRefresh=function()
  assert(not stopped and active and not contextHidden and inputContextName==contextName,
    'ActionInfoPanel refresh requires its live nonmodal context')
  assert(type(OnEndTurnDirty)=='function','Original ActionInfoPanel dirty handler is missing')
  -- Do not emit EndTurnBlockingChanged here: the stock handler can select a
  -- unit. Refresh is a read-only observation, never an automatic command.
  Events.SerialEventEndTurnDirty.CallImmediate()
  flushLayout()
  return active and not contextHidden
end
ZeroSisUi.actionInfoPanelStop=function()
  if stopped then return end
  Events.ActivePlayerTurnEnd.Remove(OnActivePlayerTurnEnd)
  Events.RemotePlayerTurnEnd.Remove(OnRemotePlayerTurnEnd)
  Events.SerialEventEndTurnDirty.Remove(OnEndTurnDirty)
  Events.EndTurnBlockingChanged.Remove(OnEndTurnBlockingChanged)
  if not contextHidden then ContextPtr:SetHide(true) end
  stopped=true
end
end -- hasRetainedActionInfoUi
