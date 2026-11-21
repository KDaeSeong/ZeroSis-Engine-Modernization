-- Component-only fixture: the installed BNW TradeRouteOverview.lua and
-- TradeRouteHelpers.lua execute over explicit SDK-shaped data. This does not
-- claim retail SDK, native popup dispatch, renderer equivalence, or live play.
local SOURCE_OVERVIEW = @@SOURCE_OVERVIEW@@
local SOURCE_HELPERS = @@SOURCE_HELPERS@@
local SOURCE_ICON_SUPPORT = @@SOURCE_ICON_SUPPORT@@
local SOURCE_FLUA_VECTOR = @@SOURCE_FLUA_VECTOR@@
local SCENE_SOURCE = @@SCENE_SOURCE@@
local INPUT_SOURCE = @@INPUT_SOURCE@@
local LAYOUT = @@LAYOUT@@
local ironResourceId = @@IRON_RESOURCE_ID@@
ZeroSisUiLayout = LAYOUT
ZeroSisUiLayout.fontMetrics = @@FONT_METRICS@@
ZeroSisUiLayout.styleDefaults = @@STYLE_DEFAULTS@@
ZeroSisUiLayout.styleDefaultsSource = 'installed Styles.xml fixture'
ZeroSisUiLayout.styleDefaultsPolicy = 'official Styles.xml attributes with source control overrides'

local nativeCalls, latestSnapshot = {}, nil
local timer = 0
local reportArrayType={}
local function reportJson(value) return __ZeroSisSnapshotJson(value,reportArrayType) end
local function native(operation, ...)
  local args={...}
  if operation=='snapshotJson' then
    latestSnapshot=args[1]
    return __ZeroSisSnapshotJson(...)
  elseif operation=='uiFrameTime' then return 1
  elseif operation=='screenSize' then return 1920,1080
  elseif operation=='randomSeed' then return 23
  elseif operation=='activePlayer' then return 0
  elseif operation=='civilization' then
    local playerID=args[1];return playerID==0 and 'CIVILIZATION_ROME' or 'CIVILIZATION_GREECE'
  elseif operation=='playerColor' then return -1
  elseif operation=='timer' then timer=timer+args[1];assert(timer==0 or timer==1);return true
  elseif operation=='locale' then
    local out=tostring(args[1])
    for i=2,#args do out=out..' '..tostring(args[i]) end
    return out
  elseif operation=='localeCompare' then
    if args[1]<args[2] then return -1 elseif args[1]>args[2] then return 1 else return 0 end
  elseif operation=='snapshotJson' then return __ZeroSisSnapshotJson(...)
  end
  error('Unexpected native operation: '..tostring(operation))
end
ZeroSisUiNative=native

local function exec(source)
  return assert(loadstring(source))()
end
function include(name)
  if name=='FLuaVector' then return exec(SOURCE_FLUA_VECTOR) end
  if name=='IconSupport' then return exec(SOURCE_ICON_SUPPORT) end
  if name=='TradeRouteHelpers' then return exec(SOURCE_HELPERS) end
  if name=='InstanceManager' then return true end -- stock file is included but this UI uses ContextPtr instances
  error('Unexpected stock include: '..tostring(name))
end

local function iterator(rows)
  local index=0
  return function() index=index+1;return rows[index] end
end
local resources={{ID= ironResourceId,Description='TXT_KEY_RESOURCE_IRON',IconString='[ICON_RES_IRON]'}}
local playerCivs={
  CIVILIZATION_ROME={ID=0,Description='TXT_KEY_CIVILIZATION_ROME',DefaultPlayerColor='COLOR_ROME',
    PortraitIndex=0,AlphaIconAtlas='CIV_ALPHA_ATLAS',IconAtlas='CIV_COLOR_ATLAS'},
  CIVILIZATION_GREECE={ID=1,Description='TXT_KEY_CIVILIZATION_GREECE',DefaultPlayerColor='COLOR_GREECE',
    PortraitIndex=1,AlphaIconAtlas='CIV_ALPHA_ATLAS',IconAtlas='CIV_COLOR_ATLAS'},
  CIVILIZATION_MINOR={ID=18,Description='TXT_KEY_CIVILIZATION_MINOR',DefaultPlayerColor='COLOR_MINOR',
    PortraitIndex=2,AlphaIconAtlas='CIV_ALPHA_ATLAS',IconAtlas='CIV_COLOR_ATLAS'},
}
GameInfo={Civilizations=playerCivs,MinorCivilizations={},Resources=function() return iterator(resources) end,
  Religions={},PlayerColors={
    COLOR_ROME={ID=10,PrimaryColor='COLOR_RED',SecondaryColor='COLOR_WHITE'},
    COLOR_GREECE={ID=11,PrimaryColor='COLOR_BLUE',SecondaryColor='COLOR_WHITE'},
    COLOR_MINOR={ID=18,PrimaryColor='COLOR_YELLOW',SecondaryColor='COLOR_BLACK'},
  },Colors={
    COLOR_RED={Red=0.8,Green=0.1,Blue=0.1,Alpha=1},
    COLOR_BLUE={Red=0.1,Green=0.2,Blue=0.8,Alpha=1},
    COLOR_YELLOW={Red=0.8,Green=0.7,Blue=0.1,Alpha=1},
    COLOR_WHITE={Red=1,Green=1,Blue=1,Alpha=1},
    COLOR_BLACK={Red=0,Green=0,Blue=0,Alpha=1},
  },IconTextureAtlases=function() return iterator(@@ICON_ATLAS_ROWS@@) end}
GameInfoTypes={}
GameDefines={MAX_MAJOR_CIVS=18}
ResourceUsageTypes={RESOURCEUSAGE_LUXURY=1,RESOURCEUSAGE_STRATEGIC=2}
DomainTypes={DOMAIN_LAND=0,DOMAIN_SEA=1}
ButtonPopupTypes={BUTTONPOPUP_TRADE_ROUTE_OVERVIEW=904}
Locale={}
function Locale.Lookup(key) return key end
function Locale.Compare(a,b) if a<b then return -1 elseif a>b then return 1 else return 0 end end
function Locale.ConvertTextKey(key,...)
  local result=tostring(key)
  for i=1,select('#',...) do result=result..' '..tostring(select(i,...)) end
  return result
end
function Locale.ToUpper(value) return string.upper(value) end
function GameInfo.Resources() return iterator(resources) end

local function city(name,owner,hasIron)
  return {GetOwner=function() return owner end,GetNameKey=function() return 'TXT_KEY_CITY_'..name end,
    IsHasResourceLocal=function(_,resourceID) assert(resourceID==ironResourceId);return hasIron end}
end
local origin=city('ROME',0,true)
local athens=city('ATHENS',1,false)
local corinth=city('CORINTH',1,false)
local function route(toCity,toName,fromGPT,domain)
  return {FromID=0,ToID=1,FromCity=origin,ToCity=toCity,FromCityName='Rome',ToCityName=toName,
    Domain=domain,FromGPT=fromGPT,ToGPT=200,FromScience=300,ToScience=100,ToFood=150,
    ToProduction=250,FromReligion=0,ToReligion=0,ToPressure=0,FromPressure=0,TurnsLeft=4}
end
local function copyRoutes(source)
  local result={};for i,row in ipairs(source) do result[i]=row end;return result
end
local outgoing={route(corinth,'Corinth',300,DomainTypes.DOMAIN_SEA),route(athens,'Athens',700,DomainTypes.DOMAIN_LAND)}
local available={route(athens,'Athens',500,DomainTypes.DOMAIN_LAND)}
local incoming={route(corinth,'Corinth',200,DomainTypes.DOMAIN_SEA)}
local function player(owner,civ)
  return {
    GetTradeRoutes=function() return copyRoutes(outgoing) end,
    GetTradeRoutesAvailable=function() return copyRoutes(available) end,
    GetTradeRoutesToYou=function() return copyRoutes(incoming) end,
    GetNickName=function() return '' end,GetName=function() return civ end,
    GetInternationalTradeRouteTotal=function(_,_,_,a,b)
      if a==DomainTypes.DOMAIN_LAND or a==DomainTypes.DOMAIN_SEA then return b and 150 or 0 end
      return a and 150 or 0
    end,
    GetInternationalTradeRouteBaseBonus=function() return 100 end,
    GetInternationalTradeRouteGPTBonus=function(_,_,_,from) return from and 50 or 25 end,
    GetInternationalTradeRoutePolicyBonus=function() return 0 end,
    GetInternationalTradeRouteYourBuildingBonus=function() return 0 end,
    GetInternationalTradeRouteTheirBuildingBonus=function() return 0 end,
    GetInternationalTradeRouteResourceTraitModifier=function() return 0 end,
    GetInternationalTradeRouteExclusiveBonus=function() return 0 end,
    GetInternationalTradeRouteOtherTraitBonus=function() return 0 end,
    GetInternationalTradeRouteRiverModifier=function() return 0 end,
    GetInternationalTradeRouteDomainModifier=function() return 0 end,
    GetInternationalTradeRouteScience=function() return owner==0 and 100 or 0 end,
    GetNumTechDifference=function() return 2 end,
    GetInfluenceTradeRouteScienceBonus=function() return 0 end,
    GetCivilizationAdjectiveKey=function() return 'TXT_KEY_CIV_ADJECTIVE_'..civ end,
  }
end
Players={[0]=player(0,'ROME'),[1]=player(1,'GREECE')}
PreGame={GetCivilization=function(id) return id==0 and 'CIVILIZATION_ROME' or 'CIVILIZATION_GREECE' end,
  GetCivilizationColor=function() return -1 end}
Game={}
function Game.GetActivePlayer() return 0 end
function Game:IsNetworkMultiPlayer() return false end
function Game.GetResourceUsageType(id) assert(id==ironResourceId);return ResourceUsageTypes.RESOURCEUSAGE_STRATEGIC end
function Game.Rand() return 0 end
UI={}
function UI.incTurnTimerSemaphore() native('timer',1) end
function UI.decTurnTimerSemaphore() native('timer',-1) end
function Vector2(x,y) return {x=x,y=y} end
function Vector4(x,y,z,w) return {x=x,y=y,z=z,w=w} end
local originalIconAtlases = GameInfo.IconTextureAtlases
assert(originalIconAtlases)
local originalSources={
  'Civ alpha mapping rows loaded from the original CIV5IconTextureAtlases.xml'}
setmetatable(originalSources,reportArrayType)

assert(loadstring(SCENE_SOURCE..'\n'..INPUT_SOURCE))()
assert(loadstring(SOURCE_OVERVIEW))()
assert(ZeroSisUi.ContextName=='TradeRoute' and ZeroSisUi.PopupKind=='TradeRoute')
local function findTarget(id,event)
  for _,target in ipairs(ZeroSisUi.GetInputTargets()) do
    if target.id==id and (event==nil or target.event==event) then return target end
  end
  error('Original TradeRoute input target missing: '..id)
end
local function click(id)
  local target=findTarget(id,'LeftClick')
  assert(ZeroSisUi.DispatchLeftClick(target.key),'Original callback did not dispatch: '..id)
end
local function findNode(node,id)
  if node.id==id then return node end
  for _,child in ipairs(node.children or {}) do
    local found=findNode(child,id);if found then return found end
  end
end
local function rowNames(snapshot)
  local stack=assert(findNode(snapshot.tree,'MainStack'))
  local rows={}
  for _,row in ipairs(stack.children) do
    local from=assert(findNode(row,'FromCity'));local to=assert(findNode(row,'ToCity'))
    rows[#rows+1]={from=from.text,to=to.text,fromTooltip=from.tooltip,toTooltip=to.tooltip}
  end
  return rows
end

ZeroSisUi.Submit({Type=ButtonPopupTypes.BUTTONPOPUP_TRADE_ROUTE_OVERVIEW,Data1=-1,Data2=-1})
assert(timer==1 and not ContextPtr:IsHidden() and g_CurrentTab=='YourTR',
  'TradeRoute popup did not enter the original modal default tab')
local targetsBefore=ZeroSisUi.GetInputTargets()
local originalButtonIds={}
for _,target in ipairs(targetsBefore) do if target.event=='LeftClick' then originalButtonIds[target.id]=true end end
assert(originalButtonIds.TabButtonYourTR and originalButtonIds.TabButtonAvailableTR and
  originalButtonIds.TabButtonTRWithYou and originalButtonIds.CloseButton and
  originalButtonIds.FromOwnerHeader and originalButtonIds.TurnsLeft,
  'Original tab, sort, and close callbacks were not registered')
assert(not originalButtonIds.Root,'Non-button row root invented a click target')
local buttonCount=0;for _ in pairs(originalButtonIds) do buttonCount=buttonCount+1 end
assert(buttonCount==18,'Original TradeRoute must retain exactly three tabs, fourteen sort buttons, and CloseButton')
local yourSnapshotJson=ZeroSisUi.Snapshot()
local yourSnapshot=assert(latestSnapshot)
local tabBottom=-math.huge
for _,id in ipairs({'TabButtonYourTR','TabButtonAvailableTR','TabButtonTRWithYou'}) do
  local tab=assert(findNode(yourSnapshot.tree,id))
  assert(tab.kind=='Button' and tab.width==300 and tab.height==24 and not tab.hidden,
    'Original tab lost its explicit button frame')
  tabBottom=math.max(tabBottom,tab.y+tab.height)
end
for _,id in ipairs({'Domain','FromOwnerHeader','FromCityHeader','ToOwnerHeader','ToCityHeader',
  'FromGPT','ToGPT','FromScience','ToScience','ToFood','ToProduction','FromReligion','ToReligion','TurnsLeft'}) do
  local header=assert(findNode(yourSnapshot.tree,id))
  assert(header.kind=='Button' and header.height==45 and header.y>=tabBottom,
    'Original column-header button overlaps the tab click area: '..id)
end
local initialRows=rowNames(yourSnapshot)
setmetatable(initialRows,reportArrayType)
assert(#initialRows==2 and initialRows[1].from=='Rome' and initialRows[1].to=='Corinth' and
  initialRows[1].fromTooltip:find('TXT_KEY_CHOOSE_INTERNATIONAL_TRADE_ROUTE_ITEM_TT_YOUR_REVENUE',1,true),
  'Original outgoing route order/values or helper-generated row tooltip were not retained')
assert(yourSnapshot.tradeRoute.modal and yourSnapshot.tradeRoute.timerSemaphore==1 and
  yourSnapshot.tradeRoute.rowTemplate=='TRInstance' and yourSnapshot.tradeRoute.rowSelectionPresent==false,
  'TradeRoute source/modal metadata mismatch')
local scrollTarget=assert((function()
  for _,target in ipairs(ZeroSisUi.GetScrollTargets()) do if target.id=='MainScroll' then return target end end
end)(),'Original MainScroll target missing')
local scrollGeometry=assert(yourSnapshot.tradeRoute.mainScroll)
assert(scrollTarget.event=='Scroll' and scrollTarget.key==scrollGeometry.key and
  scrollGeometry.orientation=='vertical' and scrollGeometry.contentHeight>=0 and
  scrollGeometry.maximumScroll==math.max(0,scrollGeometry.contentHeight-scrollGeometry.viewportHeight),
  'Original MainScroll input identity or retained geometry is incomplete')

click('FromGPT')
local sortedSnapshotJson=ZeroSisUi.Snapshot()
local sortedRows=rowNames(assert(latestSnapshot))
setmetatable(sortedRows,reportArrayType)
assert(sortedRows[1].to=='Athens' and sortedRows[2].to=='Corinth',
  'Original FromGPT descending sort callback was not applied')
click('FromGPT')
local ascendingSnapshotJson=ZeroSisUi.Snapshot()
local ascendingRows=rowNames(assert(latestSnapshot))
setmetatable(ascendingRows,reportArrayType)
assert(ascendingRows[1].to=='Corinth' and ascendingRows[2].to=='Athens',
  'Original FromGPT sort-direction toggle was not applied')
click('TabButtonAvailableTR')
assert(g_CurrentTab=='AvailableTR')
local availableSnapshotJson=ZeroSisUi.Snapshot()
local availableRows=rowNames(assert(latestSnapshot))
setmetatable(availableRows,reportArrayType)
assert(#availableRows==1 and availableRows[1].to=='Athens',
  'Original AvailableTR tab did not use GetTradeRoutesAvailable')
click('TabButtonTRWithYou')
assert(g_CurrentTab=='TRWithYou')
local incomingSnapshotJson=ZeroSisUi.Snapshot()
local incomingRows=rowNames(assert(latestSnapshot))
setmetatable(incomingRows,reportArrayType)
assert(#incomingRows==1 and incomingRows[1].to=='Corinth',
  'Original TRWithYou tab did not use GetTradeRoutesToYou')
ZeroSisUi.Close()
assert(timer==0 and ContextPtr:IsHidden(),
  'Escape did not close the original modal popup and release its timer')

__tradeRouteComponentReport='{"componentOnly":true,"originalLuaUnmodified":true,'..
  '"stockTabsAndSortRetained":true,"stockEscapeAndTimerLifecycle":true,'..
  '"columnHeadersDoNotOverlapTabs":true,'..
  '"sdkShapedRouteDataUsed":true,"helperTooltipRetained":true,'..
  '"originalRowControlsRetained":true,"rowSelectionExistsInOriginal":false,'..
  '"retailSdkRendererAndGameVerified":false,"sourceIncludes":'..
  reportJson(originalSources)..',"buttonTargetIds":'..
  reportJson(originalButtonIds)..',"mainScroll":'..
  reportJson(scrollGeometry)..',"mainScrollInputTarget":'..
  reportJson(scrollTarget)..',"yourRows":'..reportJson(initialRows)..
  ',"sortedRows":'..reportJson(sortedRows)..
  ',"ascendingRows":'..reportJson(ascendingRows)..
  ',"availableRows":'..reportJson(availableRows)..
  ',"incomingRows":'..reportJson(incomingRows)..
  ',"snapshot":'..yourSnapshotJson..'}'
