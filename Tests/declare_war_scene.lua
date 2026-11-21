-- Component fixture: run the installed BNW DeclareWarPopup bytes against
-- representative SDK-shaped data and retained controls. Native command mocks
-- record calls; they do not mutate a game or prove retail execution.
local SOURCE_INSTANCE_MANAGER = @@SOURCE_INSTANCE_MANAGER@@
local SOURCE_ICON_SUPPORT = @@SOURCE_ICON_SUPPORT@@
local SOURCE_FLUA_VECTOR = @@SOURCE_FLUA_VECTOR@@
local SOURCE_COMMON_BEHAVIORS = @@SOURCE_COMMON_BEHAVIORS@@
local SOURCE_POPUP = @@SOURCE_POPUP@@
local SCENE_SOURCE = @@SCENE_SOURCE@@
ZeroSisUiLayout = @@LAYOUT@@
local FONT_METRICS = @@FONT_METRICS@@
local STYLE_DEFAULTS = @@STYLE_DEFAULTS@@
ZeroSisUiLayout.fontMetrics=FONT_METRICS
ZeroSisUiLayout.styleDefaults=STYLE_DEFAULTS
ZeroSisUiLayout.styleDefaultsSource='fixture source styles'
ZeroSisUiLayout.styleDefaultsPolicy='fixture frozen source styles'

local timer, frameClock, uiCursor = 0, 0, 7
local commands, currentDeal, currentDealCount = {}, 0, 1
local lastSnapshotValue
local function native(operation, ...)
  local values={...}
  if operation=='snapshotJson' then
    lastSnapshotValue=values[1]
    return __ZeroSisSnapshotJson(...)
  end
  if operation=='uiFrameTime' then return frameClock end
  if operation=='uiCursor' then local previous=uiCursor;uiCursor=values[1];return previous end
  if operation=='uiShift' then return false end
  if operation=='screenSize' then return 1920,1080 end
  if operation=='randomSeed' then return 117 end
  if operation=='timer' then
    timer=timer+values[1]
    assert(timer==0 or timer==1,'unbalanced fixture timer')
  elseif operation=='locale' then
    local key=values[1]
    if key=='TXT_KEY_ACTIVE_DEAL_RESOURCE' then
      return tostring(values[2])..' '..tostring(values[3])..' '..tostring(values[4])
    end
    if key=='TXT_KEY_CHOOSE_INTERNATIONAL_TRADE_ROUTE_ITEM_GOLD' or
      key=='TXT_KEY_CHOOSE_INTERNATIONAL_TRADE_ROUTE_ITEM_FOOD' or
      key=='TXT_KEY_CHOOSE_INTERNATIONAL_TRADE_ROUTE_ITEM_PRODUCTION' or
      key=='TXT_KEY_CHOOSE_INTERNATIONAL_TRADE_ROUTE_ITEM_SCIENCE' then
      return tostring(key)..' '..tostring(values[2])
    end
    local known={
      TXT_KEY_DECLARE_WAR_YES='Declare war',TXT_KEY_DECLARE_WAR_NO='No',
      TXT_KEY_DIPLO_DIPLOMACY_BUTTON='Diplomacy',
      TXT_KEY_DECLARE_WAR_UNDER_PROTECTION_OF='Protected by',
      TXT_KEY_DIPLO_GOLD_PER_TURN='GPT',TXT_KEY_ACTIVE_DEAL_RESOURCE='Resource %s %s %s',
      TXT_KEY_CHOOSE_INTERNATIONAL_TRADE_ROUTE_ITEM_GOLD='Gold %s',
      TXT_KEY_CHOOSE_INTERNATIONAL_TRADE_ROUTE_ITEM_FOOD='Food %s',
      TXT_KEY_CHOOSE_INTERNATIONAL_TRADE_ROUTE_ITEM_PRODUCTION='Production %s',
      TXT_KEY_CHOOSE_INTERNATIONAL_TRADE_ROUTE_ITEM_SCIENCE='Science %s',
      TXT_KEY_DECLARE_WAR_DEALS_TURNS_LEFT='Turns left %s',
    }
    return known[key] or tostring(key)
  elseif operation=='civilization' then return values[1]==0 and 'CIV_PLAYER' or 'CIV_RIVAL'
  elseif operation=='playerColor' then return values[1]+1
  elseif operation=='numCurrentDeals' then assert(values[1]==0);return currentDealCount
  elseif operation=='loadCurrentDeal' then assert(values[1]==0 and values[2]==0);currentDeal=1
  elseif operation=='scratchDeal' then
    assert(currentDeal==1,'scratch deal requested before loading a real fixture deal')
    return deal
  elseif operation=='declareWarChange' then commands[#commands+1]={'change',values[1],values[2]}
  elseif operation=='declareWarDiplo' then commands[#commands+1]={'diplo',values[1],values[2],values[3],values[4]}
  elseif operation=='declareWarMove' then commands[#commands+1]={'move',unpack(values)}
  elseif operation=='declareWarMission' then commands[#commands+1]={'mission',unpack(values)}
  elseif operation=='declareWarInterfaceMode' then commands[#commands+1]={'interface',values[1]}
  else error('unexpected DeclareWar native operation: '..tostring(operation)) end
end
ZeroSisUiNative=native

Vector2=function(x,y) return {x=x,y=y} end
Vector4=function(x,y,z,w) return {x=x,y=y,z=z,w=w} end
ButtonPopupTypes={BUTTONPOPUP_DECLAREWARMOVE=41,BUTTONPOPUP_DECLAREWARRANGESTRIKE=42}
setmetatable(ButtonPopupTypes,{__index=function(values,key)
  if type(key)=='string' and key:match('^BUTTONPOPUP_') then
    local nextValue=1000
    for _,value in pairs(values) do if type(value)=='number' then nextValue=math.max(nextValue,value+1) end end
    rawset(values,key,nextValue)
    return nextValue
  end
end})
FromUIDiploEventTypes={FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR=8}
GameMessageTypes={GAMEMESSAGE_PUSH_MISSION=9}
MissionTypes={MISSION_RANGE_ATTACK=10}
InterfaceModeTypes={INTERFACEMODE_SELECTION=11}
TradeableItems={TRADE_ITEM_GOLD_PER_TURN=1,TRADE_ITEM_RESOURCES=2,
  TRADE_ITEM_RESEARCH_AGREEMENT=3,TRADE_ITEM_VOTE_COMMITMENT=4}
GameDefines={MAX_MAJOR_CIVS=2,MAX_CIV_PLAYERS=6,DOF_EXPIRATION_TIME=30,DENUNCIATION_EXPIRATION_TIME=20}
PopupPriority={GenericPopup=100,LeaderHeadPopup=200}
Mouse={eLClick='LeftClick',eRClick='RightClick'}
KeyEvents={KeyDown='KeyDown'}
Keys={VK_ESCAPE=27}

local colors={PRIMARY={Red=0.8,Green=0.2,Blue=0.2,Alpha=1},SECONDARY={Red=0.1,Green=0.1,Blue=0.1,Alpha=1}}
GameInfo={
  Leaders={[10]={PortraitIndex=0,IconAtlas='LEADER_ATLAS'},[11]={PortraitIndex=1,IconAtlas='LEADER_ATLAS'}},
  Civilizations={CIV_PLAYER={Type='CIVILIZATION_PLAYER',PortraitIndex=0,IconAtlas='CIV_COLOR_ATLAS',AlphaIconAtlas='CIV_ALPHA_ATLAS',DefaultPlayerColor=1},
    CIV_RIVAL={Type='CIVILIZATION_RIVAL',PortraitIndex=1,IconAtlas='CIV_COLOR_ATLAS',AlphaIconAtlas='CIV_ALPHA_ATLAS',DefaultPlayerColor=2},
    CIV_CITYSTATE={Type='CIVILIZATION_MINOR',ID=-1,PortraitIndex=2,IconAtlas='CIV_COLOR_ATLAS',AlphaIconAtlas='CIV_ALPHA_ATLAS',DefaultPlayerColor=3},
    CIVILIZATION_MINOR={Type='CIVILIZATION_MINOR',ID=-1}},
  PlayerColors={[1]={ID=1,PrimaryColor='PRIMARY',SecondaryColor='SECONDARY'},
    [2]={ID=2,PrimaryColor='PRIMARY',SecondaryColor='SECONDARY'},[3]={ID=3,PrimaryColor='PRIMARY',SecondaryColor='SECONDARY'},
    [4]={ID=4,PrimaryColor='PRIMARY',SecondaryColor='SECONDARY'},[5]={ID=5,PrimaryColor='PRIMARY',SecondaryColor='SECONDARY'},
    [6]={ID=6,PrimaryColor='PRIMARY',SecondaryColor='SECONDARY'}},
  Colors=colors,Resources={[5]={IconString='[ICON_RES_ALUMINUM]',Description='Aluminum'}},
  Religions={},ResolutionDecisions={},Resolutions={},
  IconTextureAtlases=function()
    local rows=@@ICON_ATLAS_ROWS@@
    local index=0;return function() index=index+1;return rows[index] end
  end,
}
local function player(id)
  return {
    GetLeaderType=function() return id==0 and 10 or 11 end,
    GetCivilizationType=function() return id==0 and 'CIV_PLAYER' or id==1 and 'CIV_RIVAL' or 'CIV_CITYSTATE' end,
    GetPlayerColor=function() return id+1 end,
    GetAlly=function() return id>=2 and 1 or -1 end,
    GetCivilizationDescriptionKey=function() return 'CITYSTATE_NAME' end,
    GetCivilizationShortDescriptionKey=function() return 'CIV_SHORT_'..id end,
    IsAlive=function() return true end,IsDoF=function() return false end,
    GetDoFCounter=function() return 0 end,IsDenouncedPlayer=function() return false end,
    GetDenouncedPlayerCounter=function() return 0 end,IsProtectingMinor=function() return false end,
    IsMinorCiv=function() return id==2 end,
    GetTradeRoutes=function()
      if id~=0 then return {} end
      return {{ToID=1,FromCityName='Capital',ToCityName='Rival City',ToolTip='Horse trade',
        FromGPT=300,ToGPT=100,FromFood=200,ToFood=0,FromProduction=0,ToProduction=100,
        FromScience=50,ToScience=0,FromPressure=0,ToPressure=0}}
    end,
    GetTradeRoutesToYou=function()
      if id~=0 then return {} end
      return {{FromID=1,FromCityName='Rival City',ToCityName='Capital',ToolTip='Incoming route',
        ToGPT=200,FromGPT=0,ToFood=100,FromFood=0,ToProduction=0,FromProduction=100,
        ToScience=0,FromScience=50,ToPressure=0,FromPressure=0}}
    end,
  }
end
Players={[0]=player(0),[1]=player(1),[2]=player(2),[3]=player(3),[4]=player(4),[5]=player(5)}
local teams={
  [0]={GetLeaderID=function() return 0 end,GetNameKey=function() return 'TEAM_PLAYER' end,GetName=function() return 'Player Team' end,IsMinorCiv=function() return false end,IsHuman=function() return true end,
    IsOpenBordersTradingAllowedWithTeam=function() return true end},
  [1]={GetLeaderID=function() return 1 end,GetNameKey=function() return 'TEAM_RIVAL' end,GetName=function() return 'Rival Team' end,IsMinorCiv=function() return false end,IsHuman=function() return false end},
}
Teams=teams
Game={GetActivePlayer=function() return 0 end,GetActiveTeam=function() return 0 end,
  IsNetworkMultiPlayer=function() return false end,GetResearchAgreementCost=function() return 100 end,
  GetNumActiveLeagues=function() return 0 end,Rand=function() return 0 end}
PreGame={GetCivilization=function(id) return id==0 and 'CIV_PLAYER' or id==1 and 'CIV_RIVAL' or 'CIV_CITYSTATE' end,
  GetCivilizationColor=function(id) return id+1 end}
Map={GetPlot=function(x,y)
  return {GetX=function() return x end,GetY=function() return y end,GetTeam=function() return 1 end,
    IsCity=function() return false end,GetOwner=function() return 1 end}
end}
local dealIndex=0
local dealItems={
  {TradeableItems.TRADE_ITEM_GOLD_PER_TURN,30,30,5,0,0,false,0},
  {TradeableItems.TRADE_ITEM_RESOURCES,30,30,5,2,0,false,1},
}
deal={GetOtherPlayer=function() return 1 end,ResetIterator=function() dealIndex=0 end,
  GetNextItem=function()
    dealIndex=dealIndex+1;local row=dealItems[dealIndex]
    if row then return unpack(row) end
  end,ClearItems=function() end}

local sources={InstanceManager=SOURCE_INSTANCE_MANAGER,IconSupport=SOURCE_ICON_SUPPORT,
  FLuaVector=SOURCE_FLUA_VECTOR,CommonBehaviors=SOURCE_COMMON_BEHAVIORS,
  DeclareWarPopup=SOURCE_POPUP,ZeroSisUiScene=SCENE_SOURCE}
include=function(name)
  local source=assert(sources[name],'unexpected source include '..tostring(name))
  return assert(loadstring(source,'@'..name))()
end
include('ZeroSisUiScene')
include('DeclareWarPopup')

local function nodeById(node,id)
  if node.id==id then return node end
  for _,child in ipairs(node.children or {}) do
    local found=nodeById(child,id);if found then return found end
  end
end
local function textById(snapshot,id)
  local node=assert(nodeById(snapshot.tree,id),'missing retained '..id)
  return node.text,node
end
local function findNotificationWar(node)
  if node.kind=='FlipAnim' and node.attributes.Texture and
    node.attributes.Texture:lower():find('notificationwar.dds',1,true) then return node end
  for _,child in ipairs(node.children or {}) do
    local found=findNotificationWar(child);if found then return found end
  end
end
local function getClick(id)
  for _,target in ipairs(ZeroSisUi.GetInputTargets(Mouse.eLClick)) do
    if target.id==id then return target.key end
  end
  error('missing original click target '..id)
end
local function clearCommands() commands={} end

local moveInfo={Type=ButtonPopupTypes.BUTTONPOPUP_DECLAREWARMOVE,Data1=1,Data2=5,Data3=5,Option1=false}
currentDealCount=0
ZeroSisUi.Submit(moveInfo)
assert(timer==1 and uiCursor==0 and ZeroSisUi.IsActive(),
  'first DeclareWar popup did not initialize from the original no-deal XML placeholders')
local noDealsJSON=ZeroSisUi.Snapshot()
local noDeals=lastSnapshotValue
local noDealsUsText,noDealsUs= textById(noDeals,'DealsFromYou')
local noDealsThemText,noDealsThem= textById(noDeals,'DealsFromThem')
assert(noDealsUs.hidden and noDealsThem.hidden and
  noDealsUsText:find('[ICON_RES_ALUMINNUM]',1,true),
  'first no-deal popup did not retain the hidden original placeholder text')
assert(noDealsUs.textMetricsPending==true and noDealsUs.textFrame==nil and
  noDealsThem.textMetricsPending==nil and noDealsThem.textFrame==nil,
  'hidden initial deal placeholders should remain pending without fabricated text frames')
assert(#commands==0,'first no-deal initialization staged a gameplay command')
ZeroSisUi.Close()
assert(timer==0 and uiCursor==7 and #commands==0,
  'first no-deal Escape path emitted commands or failed to restore timer/cursor state')
currentDealCount=1
ZeroSisUi.Submit(moveInfo)
assert(timer==1,'DeclareWar popup did not hold its stock timer while visible')
assert(uiCursor==0,'original show handler did not select the default cursor')
assert(#commands==0,'read-only GatherData staged a gameplay command')
local shownJSON=ZeroSisUi.Snapshot()
local shown=lastSnapshotValue
local notificationWar=assert(findNotificationWar(shown.tree),
  'original DeclareWar NotificationWar FlipAnim was omitted from the retained tree')
assert(notificationWar.animation and notificationWar.animation.clock==0 and
  notificationWar.animation.frame==0 and notificationWar.animation.retailTimingVerified==false and
  notificationWar.animation.sourcePause==0 and notificationWar.animation.endPause==0 and
  notificationWar.animation.timingPolicy=='CIV5_FLIP_NEGATIVE_PAUSE_END_HOLD_CANDIDATE_V1' and
  notificationWar.attributes.FrameCount=='31' and notificationWar.attributes.Speed=='10' and
  notificationWar.attributes.Pause=='0',
  'original NotificationWar frame/timing metadata differs from XML-derived candidate')
assert(getmetatable(ZeroSisUi.GetInputTargets(Mouse.eLClick))==nil and
  getmetatable(ZeroSisUi.GetScrollTargets())==nil,
  'native retained input collectors must return plain Lua tables')
assert(shown.popupKind=='DeclareWar' and shown.contextName=='DeclareWarPopup' and shown.hasRetainedPopupUi==true,
  'DeclareWar snapshot lost its selected retained context')
local targetIDs={}
local targetsByID={}
for _,target in ipairs(shown.inputTargets) do targetIDs[#targetIDs+1]=target.id;targetsByID[target.id]=true end
assert(targetsByID.Button1 and targetsByID.Button2 and targetsByID.ActiveDealsHeader and
  targetsByID.AlliedCityStatesHeader and targetsByID.DiplomacyHeader,
  'DeclareWar omitted original Yes/No or section-collapse click targets: '..table.concat(targetIDs,','))
local hasScroll=false
for _,target in ipairs(shown.scrollTargets) do
  if target.id=='DeclareWarDetailsScrollPanel' then hasScroll=true end
end
assert(hasScroll,'DeclareWar did not expose its original visible details scroll panel')
local dealsUs=textById(shown,'DealsFromYou')
local dealsThem=textById(shown,'DealsFromThem')
assert(dealsUs:find('5 GPT',1,true) and dealsThem:find('2 [ICON_RES_ALUMINUM] Aluminum',1,true),
  'original current-deal GatherData did not render both directions: us='..tostring(dealsUs)..'; them='..tostring(dealsThem))
local dealsUsNode=select(2,textById(shown,'DealsFromYou'))
assert(not dealsUsNode.hidden,'fixture deal label should be visible before testing unknown icon rejection')
local acceptedUnknownIcon,unknownIconError=pcall(function()
  Controls.DealsFromYou:SetText('4 [ICON_RES_ALUMINNUM] Aluminum')
end)
assert(not acceptedUnknownIcon and tostring(unknownIconError):find('unprepared inline icon',1,true),
  'a visible Label accepted an inline icon absent from the original mapping: '..tostring(unknownIconError))
local alliedStack=select(2,textById(shown,'AlliedCityStatesStack'))
local alliedVisible={}
for _,row in ipairs(alliedStack.children) do if not row.hidden then alliedVisible[#alliedVisible+1]=row end end
assert(#alliedVisible==4,'original GatherData omitted rival allied city states')
assert(alliedVisible[1].y==alliedVisible[2].y and alliedVisible[2].y==alliedVisible[3].y and
  alliedVisible[4].y>alliedVisible[1].y,
  'original WrapGrowth=Down city-state rows were not retained on a second row')
local routeStack=select(2,textById(shown,'TradeRoutesStack'))
local routeVisible=0
for _,row in ipairs(routeStack.children) do if not row.hidden then routeVisible=routeVisible+1 end end
assert(routeVisible==2,'original GatherData omitted representative active trade routes')
assert(ZeroSisUi.DispatchLeftClick(getClick('Button1')),'original Yes button did not dispatch')
assert(timer==0 and not ZeroSisUi.IsActive(),'original Yes handler did not close and release the timer')
assert(#commands==3 and commands[1][1]=='change' and commands[1][2]==1 and commands[1][3]==true and
  commands[2][1]=='diplo' and commands[2][2]==FromUIDiploEventTypes.FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR and
  commands[2][3]==1 and commands[2][4]==0 and commands[2][5]==0 and
  commands[3][1]=='move' and commands[3][2]==5 and commands[3][3]==5 and
  commands[3][4]==false and commands[3][5]==false and commands[3][6]==false,
  'MOVE Yes staged calls out of the installed callback order or tuple shape')

clearCommands()
local rangeInfo={Type=ButtonPopupTypes.BUTTONPOPUP_DECLAREWARRANGESTRIKE,Data1=1,Data2=7,Data3=9,Option1=false}
ZeroSisUi.Submit(rangeInfo)
assert(ZeroSisUi.DispatchLeftClick(getClick('Button1')),'original range Yes button did not dispatch')
assert(#commands==4 and commands[1][1]=='change' and commands[2][1]=='diplo' and
  commands[3][1]=='mission' and commands[3][2]==GameMessageTypes.GAMEMESSAGE_PUSH_MISSION and
  commands[3][3]==MissionTypes.MISSION_RANGE_ATTACK and commands[3][4]==7 and commands[3][5]==9 and
  commands[4][1]=='interface' and commands[4][2]==InterfaceModeTypes.INTERFACEMODE_SELECTION,
  'RANGE Yes staged calls out of the installed callback order or tuple shape')

clearCommands()
ZeroSisUi.Submit(moveInfo)
assert(ZeroSisUi.DispatchLeftClick(getClick('Button2')),'original No button did not dispatch')
assert(timer==0 and #commands==0,'original No callback emitted commands or leaked the timer')

clearCommands()
ZeroSisUi.Submit(moveInfo)
ZeroSisUi.Close()
assert(timer==0 and uiCursor==7 and #commands==0,
  'No/Escape path emitted commands or failed to restore timer/cursor state')
local closedJSON=ZeroSisUi.Snapshot()
local closed=lastSnapshotValue
assert(not closed.active and closed.timerSemaphore==0 and #closed.inputTargets==0 and
  #closed.scrollTargets==0 and closed.lifecycle[#closed.lifecycle]=='closed',
  'stock Escape/dequeue closed snapshot did not release timer and input targets')
__uiSceneComponentReport='{"declareWar":true,"nonemptyDeals":true,"unknownInlineIconRejected":true,'..
  '"emptyDealsHidden":true,"initialNoDealsPlaceholderPending":true,"alliedCityStates":4,'..
  '"tradeRoutes":2,"wrapDown":true,"moveCommandOrder":true,"rangeCommandOrder":true,'..
  '"escapeReadOnly":true,"sourceAnimationVerified":true,"retailRuntimeVerified":false,"activeSnapshot":'..shownJSON..
  ',"noDealsSnapshot":'..noDealsJSON..',"closedSnapshot":'..closedJSON..'}'
