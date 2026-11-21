-- Bridge the unchanged BNW notification script to the active player's SDK rows.
-- This addendum is part of UiScene's chunk; it never constructs replacement UI.
if hasRetainedNotificationUi then
assert(contextName=='NotificationPanel' and popupKind=='NotificationPanel',
  'NotificationPanel addendum requires its original nonmodal context')
local stopped,synchronizing=false,false
local owner,turn
local rows=array()
local byId={}
local fields={'id','type','tooltip','summary','gameData','extraGameData','player','x','y'}
local function integer(value,name)
  assert(type(value)=='number' and value==value and value~=math.huge and value~=-math.huge and
    value==math.floor(value) and math.abs(value)<=9007199254740991,name..' must be an exact integer')
  return value
end
local function live()
  assert(not stopped and active and not contextHidden and inputContextName==contextName and timer==0,
    'NotificationPanel requires its live nonmodal context')
end
local function copyRow(row)
  assert(type(row)=='table','Native notification row must be a table')
  local result={}
  for _,name in ipairs(fields) do
    if name=='tooltip' or name=='summary' then result[name]=text(row[name])
    else result[name]=integer(row[name],'notification '..name) end
  end
  assert(result.id>=0,'Notification ID must be nonnegative')
  return result
end
local function sameRow(a,b)
  if not a or not b then return false end
  for _,name in ipairs(fields) do if a[name]~=b[name] then return false end end
  return true
end
local function synchronize()
  live()
  assert(not synchronizing,'Notification rebroadcast is reentrant')
  local currentOwner=integer(Game.GetActivePlayer(),'notification owner')
  local currentTurn=integer(Game.GetGameTurn(),'notification turn')
  assert(currentOwner>=0 and currentTurn>=0,'Notification owner/turn is invalid')
  local supplied=native('notificationPanelRows')
  assert(type(supplied)=='table','notificationPanelRows must return the actual SDK array')
  local desired,desiredById=array(),{}
  local count=0
  for key in pairs(supplied) do
    assert(type(key)=='number' and key==math.floor(key) and key>=1 and key<=#supplied,
      'Native notification rows must be a dense array')
    count=count+1
  end
  assert(count==#supplied,'Native notification rows contain a hole')
  for _,item in ipairs(supplied) do
    local row=copyRow(item)
    assert(not desiredById[row.id],'Native notification ID is duplicated')
    desired[#desired+1]=row;desiredById[row.id]=row
  end
  if owner~=nil and owner~=currentOwner then
    local previous=owner
    owner=currentOwner;turn=currentTurn;rows=array();byId={}
    -- The first stock handler releases old controls. Its second handler calls
    -- UI.RebroadcastNotifications again, now for the new active player's map.
    Events.GameplaySetActivePlayer.CallImmediate(currentOwner,previous)
    return
  end
  synchronizing=true
  local ok,err=pcall(function()
    for _,row in ipairs(rows) do
      if not sameRow(row,desiredById[row.id]) then Events.NotificationRemoved.CallImmediate(row.id) end
    end
    for _,row in ipairs(desired) do
      if not sameRow(row,byId[row.id]) then
        Events.NotificationAdded.CallImmediate(row.id,row.type,row.tooltip,row.summary,
          row.gameData,row.extraGameData,row.player)
      end
    end
    owner=currentOwner;turn=currentTurn;rows=desired;byId=desiredById
    flushLayout()
  end)
  synchronizing=false
  if not ok then error(err,0) end
end

UI.RebroadcastNotifications=synchronize
UI.ActivateNotification=function(id)
  live();id=integer(id,'notification ID')
  assert(byId[id],'Cannot activate a notification outside the current SDK inventory')
  return native('notificationPanelActivateNotification',id)
end
UI.RemoveNotification=function(id)
  live();id=integer(id,'notification ID')
  assert(byId[id],'Cannot remove a notification outside the current SDK inventory')
  return native('notificationPanelRemoveNotification',id)
end
UI.IsTouchScreenEnabled=function()
  local value=native('notificationPanelTouchScreen')
  assert(type(value)=='boolean','Notification touch profile must be an actual native boolean')
  return value
end

lifecycle[#lifecycle+1]='queued'
ZeroSisUi.notificationPanelRefresh=function()
  synchronize()
  return active and not contextHidden
end
ZeroSisUi.notificationPanelMetadata=function()
  local captured=array()
  for _,row in ipairs(rows) do captured[#captured+1]=copyRow(row) end
  local provenance=assert(layout.notificationPanel,'NotificationPanel source proof is required')
  return {originalLua=assert(provenance.originalLua),originalXml=assert(provenance.originalXml),
    owner=assert(owner),turn=assert(turn),notifications=captured,
    allNotificationDestinationsIntegrated=false}
end
ZeroSisUi.notificationPanelStop=function()
  if stopped then return end
  for _,row in ipairs(rows) do Events.NotificationRemoved.CallImmediate(row.id) end
  Events.NotificationAdded.Remove(OnNotificationAdded)
  Events.NotificationRemoved.Remove(NotificationRemoved)
  Events.GameplaySetActivePlayer.Remove(OnNotificationPanelActivePlayerChanged)
  Events.GameplaySetActivePlayer.Remove(OnNotificationsActivePlayerChanged)
  rows=array();byId={}
  ContextPtr:SetHide(true)
  stopped=true
end
end -- hasRetainedNotificationUi
