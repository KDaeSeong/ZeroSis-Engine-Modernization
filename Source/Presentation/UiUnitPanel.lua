-- Install the original BNW UnitPanel into the retained UnitPanel context.
-- This addendum is concatenated after UiScene.lua in the same Lua chunk so it
-- can use the original retained Controls/Context and its guarded native bridge.
if hasRetainedUnitUi then
assert(contextName=='UnitPanel' and popupKind=='UnitPanel',
  'UnitPanel addendum requires the retained UnitPanel context')

local function unitPanelInteger(value,name)
  assert(type(value)=='number' and value==value and value~=math.huge and
    value~=-math.huge and value==math.floor(value),name..' must be an integer')
  return value
end

include('FLuaVector')
ToHexFromGrid=function(grid)
  assert(type(grid)=='table','ToHexFromGrid requires the original grid coordinate')
  local x=unitPanelInteger(grid.x,'grid x')
  local y=unitPanelInteger(grid.y,'grid y')
  return Vector2(x-math.floor(y/2),y)
end

local function selectedUnit(operation)
  local owner,unitID=native(operation)
  if owner==nil and unitID==nil then return nil end
  owner=unitPanelInteger(owner,operation..' owner')
  unitID=unitPanelInteger(unitID,operation..' unit id')
  assert(owner>=0 and unitID>=0,operation..' identity is out of range')
  local player=assert(Players and Players[owner],operation..' owner is not bound')
  return assert(player:GetUnitByID(unitID),operation..' refers to a missing live unit')
end

-- The source UnitPanel asks these methods directly. Keep selection as the
-- original SDK userdata; its own action and stats routines remain authoritative.
UI.GetHeadSelectedUnit=function() return selectedUnit('headSelectedUnit') end
UI.IsTouchScreenEnabled=function()
  local result=native('isTouchScreen')
  assert(type(result)=='boolean','isTouchScreen must return a boolean')
  return result
end
UI.GetUnitFlagIcon=function(unit)
  assert(unit and type(unit.GetUnitType)=='function' and type(unit.GetUnitFlagIconOffset)=='function',
    'GetUnitFlagIcon requires the original live unit')
  local info=assert(GameInfo and GameInfo.Units[unit:GetUnitType()],
    'Unit flag icon requires its original GameInfo.Units row')
  return unit:GetUnitFlagIconOffset(),assert(info.UnitFlagAtlas,
    'Original GameInfo unit lacks UnitFlagAtlas')
end
UI.GetUnitPortraitIcon=function(unit)
  assert(unit and type(unit.GetUnitType)=='function' and type(unit.GetOwner)=='function',
    'GetUnitPortraitIcon requires the original live unit')
  return native('unitPortrait',unit:GetUnitType(),unit:GetOwner())
end
UI.LookAtSelectionPlot=function()
  return native('lookAtSelectionPlot')
end

-- Preserve the real SDK legality query and action catalogue. The normal stock
-- callback still calls Game.HandleAction(index), which this dedicated context
-- turns into a deferred host request so the SDK runs only after Lua unwinds.
assert(type(Game)=='table' and type(Game.CanHandleAction)=='function' and
  type(GameInfoActions)=='table','Original SDK action bindings are unavailable')
Game.HandleAction=function(actionIndex)
  actionIndex=unitPanelInteger(actionIndex,'Game.HandleAction action index')
  assert(actionIndex>=0 and GameInfoActions[actionIndex],
    'Game.HandleAction index is absent from original GameInfoActions')
  return native('unitPanelAction',actionIndex)
end

-- Instantiate the original XML tooltip separately, initially hidden as in the
-- frontend tooltip manager. Its controls must exist before stock Lua registers
-- TipHandler, even when no pointer is hovering a unit action.
local unitActionTooltip=nil
for _,template in ipairs(assert(layout.toolTipTemplates,'Original UnitPanel tooltip templates are missing')) do
  assert(template.name=='TypeUnitAction' and not unitActionTooltip,'Unexpected UnitPanel tooltip template')
  unitActionTooltip=make(template.tree,root,controls)
  unitActionTooltip:SetHide(true)
end
assert(unitActionTooltip,'Original TypeUnitAction tooltip was not instantiated')
TTManager=TTManager or {}
function TTManager:GetTypeControlTable(typeName,target)
  assert(typeName=='TypeUnitAction' and type(target)=='table',
    'UnitPanel requested an unsupported tooltip template')
  for _,name in ipairs({'UnitActionMouseover','UnitActionHotKey','UnitActionText','UnitActionHelp'}) do
    target[name]=assert(Controls[name],'Original UnitPanel tooltip control is missing: '..name)
  end
end

local stockSetUpdate=assert(ContextPtr.SetUpdate)
local stockUpdate=nil
ContextPtr.SetUpdate=function(self,callback)
  assert(callback==nil or type(callback)=='function','Original UnitPanel update callback must be a function or nil')
  stockUpdate=callback
  return stockSetUpdate(self,callback)
end

local stockLoaded=false
local stockInclude=assert(include)
local function ensureStockUnitPanel()
  if stockLoaded then return end
  stockInclude('UnitPanel')
  assert(type(RefreshInfoPane)=='function' and type(OnInfoPaneDirty)=='function' and
    type(stockUpdate)=='function','Original UnitPanel did not register its refresh/update flow')
  stockLoaded=true
end

ZeroSisUi=ZeroSisUi or {}
ZeroSisUi.unitPanelRefresh=function()
  ensureStockUnitPanel()
  -- Preserve the stock dirty event and its coalesced ContextPtr update path.
  Events.SerialEventUnitInfoDirty.CallImmediate()
  if stockUpdate then stockUpdate() end
  return not ContextPtr:IsHidden()
end
ZeroSisUi.unitPanelStop=function()
  if not stockLoaded then return true end
  ContextPtr:SetHide(true)
  Events.SerialEventUnitInfoDirty.Remove(OnInfoPaneDirty)
  Events.GameplaySetActivePlayer.Remove(OnActivePlayerChanged)
  Events.ActivePlayerTurnEnd.Remove(OnActivePlayerTurnEnd)
  Events.ActivePlayerTurnStart.Remove(OnActivePlayerTurnStart)
  LuaEvents.EnemyPanelHide.Remove(OnEnemyPanelHide)
  ContextPtr:SetUpdate(nil)
  stockLoaded=false
  return true
end
end -- hasRetainedUnitUi
