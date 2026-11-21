-- Optional CityView addendum. Append after UiScene.lua in the same Lua chunk
-- so this binds the installed BNW script to the retained native UI boundary.
-- This supplies state queries and event capture; it does not add gameplay
-- behavior to the stock CityView controls.
assert(hasRetainedCityUi and popupKind=='CityView',
  'CityView addendum requires the retained CityView popup kind')

-- The installed CityView names this include, but the sealed loose/FPK name
-- inventory contains no source. Preserve the request and report the miss;
-- never register an empty replacement script or claim that it executed.
local cityUnresolvedIncludes=array()
local citySourceInclude=assert(include)
local cityInstallVectorAdd
include=function(name,pattern)
  if name=='TutorialPopupScreen' then
    assert(pattern==nil and layout.optionalMissingIncludes and
      layout.optionalMissingIncludes[1]=='TutorialPopupScreen',
      'Optional include miss requires its sealed installed-source inventory')
    if not native('optionalCityIncludeExists',name) then
      cityUnresolvedIncludes[#cityUnresolvedIncludes+1]=name
      return false
    end
  end
  local result=citySourceInclude(name,pattern)
  if name=='FLuaVector' and cityInstallVectorAdd then cityInstallVectorAdd() end
  return result
end

local function cityFinite(value,name)
  assert(type(value)=='number' and value==value and value~=math.huge and value~=-math.huge,
    (name or 'CityView value')..' must be finite')
  return value
end

local function cityInteger(value,name,minimum)
  cityFinite(value,name)
  assert(value==math.floor(value) and (minimum==nil or value>=minimum),
    (name or 'CityView value')..' must be an integer in range')
  return value
end

local function cityBoolean(value,name)
  assert(type(value)=='boolean',(name or 'CityView value')..' must be boolean')
  return value
end

-- These enum tables are supplied by the original game Lua environment. Never
-- invent enum ordinals in this frontend.
local function requireEnum(tableName,field)
  local values=rawget(_G,tableName)
  assert(type(values)=='table' and type(values[field])=='number',
    'Original '..tableName..'.'..field..' enum is unavailable')
  return values[field]
end

for _,field in ipairs({'INTERFACEMODE_SELECTION','INTERFACEMODE_PURCHASE_PLOT','INTERFACEMODE_CITY_PLOT_SELECTION'}) do
  requireEnum('InterfaceModeTypes',field)
end
for _,field in ipairs({'NO_CITY_AI_FOCUS_TYPE','CITY_AI_FOCUS_TYPE_FOOD','CITY_AI_FOCUS_TYPE_PRODUCTION',
  'CITY_AI_FOCUS_TYPE_GOLD','CITY_AI_FOCUS_TYPE_SCIENCE','CITY_AI_FOCUS_TYPE_CULTURE',
  'CITY_AI_FOCUS_TYPE_GREAT_PEOPLE','CITY_AI_FOCUS_TYPE_FAITH'}) do
  requireEnum('CityAIFocusTypes',field)
end
-- These are frontend presentation tokens, not SDK enum registrations.
YieldDisplayTypes={CITY_OWNED='CityOwned',CITY_WORKED='CityWorked',CITY_PURCHASABLE='CityPurchasable'}

include('FLuaVector')

-- UiScene's input adapter accepts only Escape/Return. CityView's stock
-- left/right shortcuts call CONTROL_PREVCITY/NEXTCITY even in viewing mode,
-- so those keys must not be admitted by this read-only context.
Keys.VK_LEFT=37
Keys.VK_RIGHT=39
MouseEvents={LButtonDown='LButtonDown',RButtonUp='RButtonUp'}
Mouse.eLCLick=Mouse.eLClick -- preserve the typo present in stock CityView.lua.

local function ensureEvent(name)
  if not rawget(Events,name) then event(name) end
  return rawget(Events,name)
end

for _,name in ipairs({'SerialEventEnterCityScreen','SerialEventCityHexHighlightDirty',
  'SerialEventMouseOverHex','StrategicViewStateChanged','SerialEventHexHighlight',
  'RequestYieldDisplay','AudioPlay2DSound'}) do
  ensureEvent(name)
end

local hexHighlights={}
local requestedYieldDisplay=nil
local tutorialRequests={}
local lastCityViewProjection=nil

local function copyVector2(value)
  assert(type(value)=='table','CityView hex coordinate must be a Vector2 value')
  return {x=cityInteger(value.x,'hex x'),y=cityInteger(value.y,'hex y')}
end

local function copyVector4(value)
  assert(type(value)=='table','CityView highlight color must be a Vector4 value')
  local result={x=cityFinite(value.x,'highlight red'),y=cityFinite(value.y,'highlight green'),
    z=cityFinite(value.z,'highlight blue'),w=cityFinite(value.w,'highlight alpha')}
  for _,channel in ipairs({result.x,result.y,result.z,result.w}) do
    assert(channel>=0 and channel<=1,'CityView highlight channel must be in [0,1]')
  end
  return result
end

-- Retained projection policy: convert the stock offset-row grid to axial
-- coordinates, then pass the inverse grid coordinate to the game projection.
-- This policy is explicit and is not claimed to match retail map projection.
ToHexFromGrid=function(grid)
  assert(type(grid)=='table','ToHexFromGrid requires the stock Vector2 grid value')
  local gridX=cityInteger(grid.x,'grid x',0)
  local gridY=cityInteger(grid.y,'grid y',0)
  return {x=gridX-math.floor(gridY/2),y=gridY}
end

HexToWorld=function(hex)
  local axial=copyVector2(hex)
  local gridX=axial.x+math.floor(axial.y/2)
  local gridY=axial.y
  local x,y,z=native('cityPlotPosition',gridX,gridY)
  return {x=cityFinite(x,'projected plot x'),y=cityFinite(y,'projected plot y'),
    z=cityFinite(z,'projected plot z'),gridX=gridX,gridY=gridY,offsetX=0,offsetY=0,offsetZ=0}
end

-- Preserve the plot identity across the stock script's VecAdd(world,offset).
-- Original offsets remain explicit candidate screen-space offsets; the base
-- point is refreshed from the current depth-tested terrain before capture.
cityInstallVectorAdd=function()
  local cityVecAdd=assert(VecAdd)
  VecAdd=function(a,b)
    local result=cityVecAdd(a,b)
    if a.gridX~=nil then
      assert(b.gridX==nil,'Cannot add two retained world plot identities')
      result.gridX=a.gridX;result.gridY=a.gridY
      result.offsetX=(a.offsetX or 0)+b.x;result.offsetY=(a.offsetY or 0)+b.y
      result.offsetZ=(a.offsetZ or 0)+b.z
    end
    return result
  end
end
cityInstallVectorAdd()

local highlightEvent=ensureEvent('SerialEventHexHighlight')
highlightEvent.Add(function(hex,visible,color)
  local position=copyVector2(hex)
  cityBoolean(visible,'hex highlight visibility')
  local rgba=copyVector4(color)
  local key=tostring(position.x)..':'..tostring(position.y)
  if visible then
    hexHighlights[key]={hex=position,color=rgba}
  else
    hexHighlights[key]=nil
  end
end)

ensureEvent('RequestYieldDisplay').Add(function(kind,x,y)
  assert(kind==YieldDisplayTypes.CITY_OWNED or kind==YieldDisplayTypes.CITY_WORKED or
    kind==YieldDisplayTypes.CITY_PURCHASABLE,'Unsupported CityView yield-display request token')
  requestedYieldDisplay={kind=kind,
    x=cityInteger(x,'yield display x',0),y=cityInteger(y,'yield display y',0)}
end)

ensureEvent('AudioPlay2DSound').Add(function(sound)
  assert(type(sound)=='string' and sound~='','CityView sound key must be nonempty')
  return native('audioPlay2DSound',sound)
end)

LuaEvents.TryQueueTutorial=ensureEvent('TryQueueTutorial')
LuaEvents.TryDismissTutorial=ensureEvent('TryDismissTutorial')
LuaEvents.TryQueueTutorial.Add(function(kind,force)
  assert(type(kind)=='string' and kind~='','Tutorial category must be a nonempty string')
  cityBoolean(force,'tutorial force flag')
  tutorialRequests[#tutorialRequests+1]={kind=kind,queued=true,force=force}
  native('tutorialRequest',kind,true)
end)
LuaEvents.TryDismissTutorial.Add(function(kind)
  assert(type(kind)=='string' and kind~='','Tutorial category must be a nonempty string')
  tutorialRequests[#tutorialRequests+1]={kind=kind,queued=false,force=false}
  native('tutorialRequest',kind,false)
end)

OptionsManager.IsNoCitizenWarning=function()
  local value=native('noCitizenWarning')
  return cityBoolean(value,'noCitizenWarning')
end

Modding=Modding or {}
function Modding.GetActivatedModEntryPoints(kind)
  assert(type(kind)=='string' and kind=='CityViewUIAddin',
    'CityView requested an unsupported mod entry-point category')
  local rows=native('activatedModEntryPoints',kind)
  assert(type(rows)=='table','activatedModEntryPoints must return an owned row table')
  local count,maximum=0,0
  for index,row in pairs(rows) do
    assert(type(index)=='number' and index>=1 and index==math.floor(index),
      'Activated CityView entry points must be a numeric array')
    assert(type(row)=='table','Activated CityView entry point must be a row table')
    count=count+1;maximum=math.max(maximum,index)
  end
  assert(count==maximum,'Activated CityView entry-point rows must be contiguous')
  for index=1,maximum do assert(type(rows[index])=='table','Activated CityView entry-point row is missing') end
  local index=0
  return function()
    index=index+1
    return rows[index]
  end
end

local function selectedUnit(nativeOperation)
  local owner,unitID=native(nativeOperation)
  if owner==nil and unitID==nil then return nil end
  assert(type(owner)=='number' and owner==math.floor(owner) and
    type(unitID)=='number' and unitID==math.floor(unitID),
    nativeOperation..' must return owner/id or nil/nil')
  local player=assert(Players and Players[owner],nativeOperation..' owner has no live player binding')
  return player:GetUnitByID(unitID)
end

UI.GetInterfaceMode=function()
  local mode=native('interfaceMode')
  assert(type(mode)=='number' and mode==mode and mode~=math.huge and mode~=-math.huge and mode==math.floor(mode),
    'interfaceMode native operation must return an integer enum')
  return mode
end
UI.SetInterfaceMode=function(mode)
  cityInteger(mode,'interface mode')
  return native('interfaceMode',mode)
end
UI.SetCityScreenViewingMode=function(value)
  return native('setCityScreenViewingMode',cityBoolean(value,'city screen viewing mode'))
end
UI.DoSelectCityAtPlot=function(plot)
  assert((type(plot)=='table' or type(plot)=='userdata') and
    type(plot.GetX)=='function' and type(plot.GetY)=='function',
    'UI.DoSelectCityAtPlot requires an actual original map plot')
  return native('selectCityAtPlot',cityInteger(plot:GetX(),'city plot x',0),
    cityInteger(plot:GetY(),'city plot y',0))
end
UI.GetHeadSelectedUnit=function() return selectedUnit('headSelectedUnit') end
UI.GetLastSelectedUnit=function() return selectedUnit('lastSelectedUnit') end
UI.ClearSelectedCities=function() return native('clearSelectedCities') end
UI.IsCityScreenUp=function()
  return cityBoolean(native('cityScreenUp'),'cityScreenUp')
end
UI.UpdateCityScreen=function() return Events.SerialEventCityScreenDirty.CallImmediate() end
UI.SelectUnit=function(unit)
  assert((type(unit)=='table' or type(unit)=='userdata') and
    type(unit.GetOwner)=='function' and type(unit.GetID)=='function',
    'UI.SelectUnit requires an original live unit')
  return native('selectUnit',cityInteger(unit:GetOwner(),'unit owner',0),
    cityInteger(unit:GetID(),'unit id',0))
end
UI.LookAtSelectionPlot=function() return native('lookAtSelectionPlot') end

Network=Network or {}
Network.SendUpdateCityCitizens=function(cityID)
    return native('updateCityCitizens',cityInteger(cityID,'city id',0))
end
Network.SendSetCityAIFocus=function(cityID,focus)
  return native('citySetFocus',cityInteger(cityID,'city id',0),cityInteger(focus,'city focus'))
end
Network.SendSetCityAvoidGrowth=function(cityID,value)
  return native('citySetAvoidGrowth',cityInteger(cityID,'city id',0),cityBoolean(value,'avoid growth'))
end
local function cityOptionalBoolean(value,name)
  if value==nil then return false end
  return cityBoolean(value,name)
end
Network.SendDoTask=function(cityID,task,data1,data2,option,alt,shift,control)
  return native('ownedCityTask',cityInteger(cityID,'city id',0),cityInteger(task,'city task'),
    cityInteger(data1,'task data1'),cityInteger(data2,'task data2'),
    cityOptionalBoolean(option,'task option'),cityOptionalBoolean(alt,'task alt'),
    cityOptionalBoolean(shift,'task shift'),cityOptionalBoolean(control,'task control'))
end
Network.SendCityBuyPlot=function(cityID,x,y)
  return native('ownedCityBuyPlot',cityInteger(cityID,'city id',0),
    cityInteger(x,'purchase x',0),cityInteger(y,'purchase y',0))
end
Network.SendSellBuilding=function(cityID,building)
  return native('ownedCitySellBuilding',cityInteger(cityID,'city id',0),cityInteger(building,'building id',0))
end

-- This runs after the original input callback has unwound. Use the live SDK
-- bindings again immediately before its original network receiver executes.
-- Numeric command kinds below are private Host transport tags, not SDK enums.
ZeroSisUi.ValidateCityCommand=function(kind,cityID,data1,data2,data3,option,alt,shift,control,afterSpecialistAutomation)
  local player=assert(Players[Game.GetActivePlayer()])
  local city=assert(UI.GetHeadSelectedCity())
  assert(active and not contextHidden and not UI.IsCityScreenViewingMode() and UI.IsCityScreenUp() and
    player:IsTurnActive() and city:GetID()==cityID and city:GetOwner()==Game.GetActivePlayer() and not city:IsPuppet(),
    'City command lost its live editable selected city')
  if kind==1 then
    if data1==TaskTypes.TASK_NO_AUTO_ASSIGN_SPECIALISTS then
      assert(data2==-1 and data3==-1,'Specialist automation payload changed')
    elseif data1==TaskTypes.TASK_ADD_SPECIALIST or data1==TaskTypes.TASK_REMOVE_SPECIALIST then
      local building=assert(GameInfo.Buildings[data3],'Specialist building is invalid')
      assert(GameInfoTypes[building.SpecialistType]==data2 and city:GetNumBuilding(data3)>0 and not option,
        'Specialist payload does not match the actual building')
      -- The complete stock callback was checked before either receiver ran.
      -- SetNoAutoAssignSpecialists itself reallocates citizens, so its following
      -- slot command may now legitimately do nothing. Preserve that SDK order.
      assert(type(afterSpecialistAutomation)=='boolean' and
        (not afterSpecialistAutomation or city:IsNoAutoAssignSpecialists()),
        'Specialist follow-up lost its delivered manual-assignment transition')
      if data1==TaskTypes.TASK_ADD_SPECIALIST then
        assert(afterSpecialistAutomation or city:IsCanAddSpecialistToBuilding(data3),
          'No legal specialist slot in this building')
      else
        assert(afterSpecialistAutomation or city:GetNumSpecialistsInBuilding(data3)>0,
          'Building has no specialist to remove')
      end
    elseif data1==TaskTypes.TASK_CHANGE_WORKING_PLOT then
      assert(data2>=0 and data2<city:GetNumCityPlots() and data3==-1 and not option,'Working plot payload is invalid')
      if data2>0 then
        local plot=assert(city:GetCityIndexPlot(data2),'Working plot disappeared')
        local working=plot:GetWorkingCity()
        assert(plot:GetOwner()==city:GetOwner() and working and
          not plot:IsVisibleEnemyUnit(city:GetOwner()) and not (plot:IsWater() and city:IsPlotBlockaded(plot)) and
          (city:CanWork(plot) or city:IsWorkingPlot(plot) or working:GetID()~=city:GetID()),
          'Working plot is no longer available to this city')
      end
    elseif data1==TaskTypes.TASK_REMOVE_SLACKER then
      assert(data2==0 and data3==-1 and not option and
        city:GetSpecialistCount(GameDefines.DEFAULT_SPECIALIST)>0,'No unemployed citizen to reassign')
    elseif data1==TaskTypes.TASK_UNRAZE then
      assert(data2==-1 and data3==-1 and not option and city:IsRazing(),'City is not being razed')
    else
      error('Unsupported original CityView task '..tostring(data1))
    end
  elseif kind==2 then
    assert(UI.GetInterfaceMode()==InterfaceModeTypes.INTERFACEMODE_PURCHASE_PLOT and
      data1>=0 and data2>=0 and city:CanBuyPlotAt(data1,data2,false),
      'Plot purchase is no longer affordable or legal')
  elseif kind==3 then
    assert(GameInfo.Buildings[data1] and city:IsBuildingSellable(data1),'Building is no longer sellable')
  elseif kind==4 or kind==5 then
    local count=city:GetOrderQueueLength()
    assert(data1>=0 and data1<count and (kind~=5 or data1+1<count),'Production queue index is stale')
  else
    error('Unknown city command transport kind')
  end
end

Events.SerialEventGameMessagePopup.Add(function(info)
  assert(type(info)=='table','City popup requires its original payload')
  native('cityProductionPopup',info.Type,info.Data1,info.Data2,info.Data3,info.Option1,info.Option2)
end)

ZeroSisUi.CityProductionVisibility=function(hidden)
  assert(active and not contextHidden,'Production visibility requires the retained city screen')
  LuaEvents.ProductionPopup(cityBoolean(hidden,'production hidden'))
end

ZeroSisUi.EnterCityView=function()
  assert(not active and contextHidden and timer==0,'CityView is already active')
  context:SetHide(false)
  Events.SerialEventEnterCityScreen()
  lastCityViewProjection=native('cityViewProjection')
  assert(type(lastCityViewProjection)=='table','cityViewProjection must return an owned CityView table')
  return true
end

ZeroSisUi.RefreshCityView=function()
  assert(active and not contextHidden and inputContextName==contextName,
    'CityView refresh requires its active context')
  Events.SerialEventCityScreenDirty.CallImmediate()
  lastCityViewProjection=native('cityViewProjection')
  assert(type(lastCityViewProjection)=='table','cityViewProjection must return an owned CityView table')
end

ZeroSisUi.FindCityViewExitButton=function()
  assert(hasRetainedCityUi and popupKind=='CityView' and active and not contextHidden,
    'CityView exit lookup requires its active original context')
  local button=assert(controls.ReturnToMapButton,'Original CityView ReturnToMapButton is missing')
  local value=state(button)
  assert(value.attributes.ID=='ReturnToMapButton','CityView exit target has the wrong original XML ID')
  local visible=not value.hidden
  local parent=value.parent
  while parent do
    if state(parent).hidden then visible=false;break end
    parent=state(parent).parent
  end
  assert(visible and not button:IsHidden() and not value.disabled,
    'Original CityView ReturnToMapButton is not visible and enabled')
  assert(type(value.callbacks[Mouse.eLClick])=='function',
    'Original CityView ReturnToMapButton lacks its stock left-click callback')
  assert(value.w>0 and value.h>0 and value.x>=0 and value.y>=0 and
    value.x+value.w<=viewport.w and value.y+value.h<=viewport.h,
    'Original CityView ReturnToMapButton has invalid retained bounds')
  return value.key,{x=value.x,y=value.y,width=value.w,height=value.h}
end

local originalNative=native
native=function(operation,...)
  if operation~='snapshotJson' then return originalNative(operation,...) end
  local snapshot=select(1,...)
  assert(type(snapshot)=='table','snapshotJson requires its original snapshot table')
  local cityView
  if active and not contextHidden then
    cityView=native('cityViewProjection')
    assert(type(cityView)=='table','cityViewProjection must return an owned CityView table')
    lastCityViewProjection=cityView
  else
    cityView=assert(lastCityViewProjection,
      'Closed CityView snapshot has no previously captured city projection')
  end
  assert(type(cityView.owner)=='number' and cityView.owner==math.floor(cityView.owner) and
    type(cityView.city)=='number' and cityView.city==math.floor(cityView.city) and
    type(cityView.viewingMode)=='boolean' and cityView.retailWorldProjectionVerified==false,
    'cityViewProjection returned malformed CityView identity or projection-verification metadata')
  local projection=assert(cityView.projection,'cityViewProjection omitted its projection table')
  assert(type(projection)=='table' and type(projection.policy)=='string' and projection.policy~='',
    'cityViewProjection omitted its projection policy')
  for _,field in ipairs({'cameraX','cameraY','gridWidth','gridHeight','tileWidth','centerX','centerY'}) do
    cityFinite(projection[field],'city projection '..field)
  end
  cityBoolean(projection.wrapX,'city projection wrapX')
  cityBoolean(projection.wrapY,'city projection wrapY')
  if projection.policy=='ZEROSIS_D3D11_CITY_VIEW_RASTER_V1' then
    assert(type(projection.plots)=='table','Terrain projection requires detached plot geometry')
    for _,plot in pairs(projection.plots) do
      setmetatable(plot.spans,arrayType)
      for _,span in ipairs(plot.spans) do setmetatable(span,arrayType) end
    end
  end
  local highlights=array()
  for _,value in pairs(hexHighlights) do
    highlights[#highlights+1]={hex={x=value.hex.x,y=value.hex.y},
      color={x=value.color.x,y=value.color.y,z=value.color.z,w=value.color.w}}
  end
  table.sort(highlights,function(a,b)
    if a.hex.y~=b.hex.y then return a.hex.y<b.hex.y end
    return a.hex.x<b.hex.x
  end)
  local requests=array()
  for _,request in ipairs(tutorialRequests) do
    requests[#requests+1]={kind=request.kind,queued=request.queued,force=request.force}
  end
  cityView.hexHighlights=highlights
  cityView.yieldDisplay=requestedYieldDisplay and {
    kind=requestedYieldDisplay.kind,x=requestedYieldDisplay.x,y=requestedYieldDisplay.y,
    rendererVerified=false} or nil
  cityView.tutorialRequests=requests
  cityView.tutorialExecutionVerified=false
  cityView.unresolvedIncludes=cityUnresolvedIncludes
  cityView.smallUIAssets=OptionsManager.GetSmallUIAssets()
  cityView.layoutVariant=layout.layoutVariant
  assert(type(cityView.smallUIAssets)=='boolean' and
    cityView.layoutVariant==(cityView.smallUIAssets and 'small' or 'default'),
    'CityView layout differs from the frozen original SmallUIAssets option')
  cityView.hexCoordinatePolicy='ZEROSIS_GRID_TO_AXIAL_ROW_ODD_V1'
  cityView.viewingMode=UI.IsCityScreenViewingMode()
  snapshot.cityView=cityView
  return originalNative(operation,...)
end
