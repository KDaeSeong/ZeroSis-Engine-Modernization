-- The stock popup keeps owner/city IDs; reacquire the actual SDK city on every
-- input and validate legality in the same VM before native receiver dispatch.
local function integer(value)
  assert(type(value)=='number' and value==math.floor(value) and value>=0 and value<=2147483647,
    'Invalid production item ID')
  return value
end
local function owned(city)
  local owner=Game.GetActivePlayer()
  local player=assert(Players[owner],'Production owner is missing')
  assert(player:IsHuman() and player:IsAlive() and player:IsTurnActive(), 'Production owner is not an active human')
  assert(city and city:GetOwner()==owner, 'Production city is not owned by the active player')
  local live=assert(player:GetCityByID(city:GetID()),'Production city no longer exists')
  assert(live:GetOwner()==owner, 'Production city ownership changed')
  return live
end
local push=assert(Game.CityPushOrder)
Game.CityPushOrder=function(city,order,id,alt,shift,control)
  city=owned(city);integer(id)
  assert(alt==false and type(shift)=='boolean' and control==true,'Unsupported production command modifiers')
  local valid=false
  if order==OrderTypes.ORDER_TRAIN then valid=GameInfo.Units[id]~=nil and city:CanTrain(id)
  elseif order==OrderTypes.ORDER_CONSTRUCT then valid=GameInfo.Buildings[id]~=nil and city:CanConstruct(id)
  elseif order==OrderTypes.ORDER_CREATE then valid=GameInfo.Projects[id]~=nil and city:CanCreate(id)
  elseif order==OrderTypes.ORDER_MAINTAIN then valid=GameInfo.Processes[id]~=nil and city:CanMaintain(id)
  end
  assert(valid,'Production command is no longer legal')
  return push(city,order,id,alt,shift,control)
end
function ZeroSisValidateProductionPurchase(cityID,unit,building,project,yield)
  local player=assert(Players[Game.GetActivePlayer()])
  local city=owned(assert(player:GetCityByID(integer(cityID))))
  assert(yield==YieldTypes.YIELD_GOLD or yield==YieldTypes.YIELD_FAITH,'Unsupported purchase yield')
  assert(city:IsCanPurchase(true,true,unit,building,project,yield),'Purchase is no longer legal')
end
local function purchase(name,tableName,slot)
  local original=assert(Game[name])
  Game[name]=function(city,id,yield)
    city=owned(city);integer(id)
    assert(GameInfo[tableName][id]~=nil,'Purchase item has no actual rules entry')
    assert(yield==YieldTypes.YIELD_GOLD or yield==YieldTypes.YIELD_FAITH,'Unsupported purchase yield')
    -- Keep the SDK binding, but require the original input scope. The host
    -- owns only value IDs until this callback and its sound request return.
    ZeroSisUiNative('requirePurchaseInput',city:GetID())
    local unit,building,project=-1,-1,-1
    if slot==1 then unit=id elseif slot==2 then building=id else project=id end
    assert(city:IsCanPurchase(true,true,unit,building,project,yield),'Purchase is no longer legal')
    return original(city,id,yield)
  end
end
purchase('CityPurchaseUnit','Units',1)
purchase('CityPurchaseBuilding','Buildings',2)
purchase('CityPurchaseProject','Projects',3)
Events.AudioPlay2DSound.Add(function(sound) ZeroSisUiNative('audioPlay2DSound',sound) end)
