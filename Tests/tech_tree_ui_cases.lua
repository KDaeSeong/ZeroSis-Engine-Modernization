-- Component-only execution of the installed BNW TechTree.lua on retained controls.
-- Game/player/native values are deterministic mocks, never SDK or retail proof.
local SOURCE_INSTANCE_MANAGER = @@SOURCE_INSTANCE_MANAGER@@
local SOURCE_ICON_SUPPORT = @@SOURCE_ICON_SUPPORT@@
local SOURCE_FLUA_VECTOR = @@SOURCE_FLUA_VECTOR@@
local SOURCE_INFO_TOOLTIP = @@SOURCE_INFO_TOOLTIP@@
local SOURCE_TECH_BUTTON = @@SOURCE_TECH_BUTTON@@
local SOURCE_TECH_HELP = @@SOURCE_TECH_HELP@@
local SOURCE_TECH_TREE = @@SOURCE_TECH_TREE@@
local SOURCE_SCENE = @@SCENE_SOURCE@@
ZeroSisUiLayout = @@LAYOUT@@

local timer, timerCalls, frameClock = 0, {}, 0
local shift = false
local researched = {}
local researchCalls = {}
local function native(operation,...)
  if operation=='snapshotJson' then return __ZeroSisSnapshotJson(...) end
  if operation=='timer' then
    local delta=...
    timer=timer+delta;timerCalls[#timerCalls+1]=delta;return true
  elseif operation=='uiFrameTime' then return frameClock
  elseif operation=='uiShift' then return shift
  elseif operation=='randomSeed' then return 41
  elseif operation=='screenSize' then return 1920,1080
  elseif operation=='locale' then
    local key=(...)
    local localized={TXT_KEY_TECH_TREE_A='Alpha',TXT_KEY_TECH_TREE_B='Beta',
      TXT_KEY_ANCIENT_ERA='Ancient',TXT_KEY_CLASSICAL_ERA='Classical',TXT_KEY_TURNS='Turns'}
    return localized[key] or tostring(key)
  elseif operation=='localeLength' then
    return #( ... )
  elseif operation=='localeTruncate' then
    local value,limit,ellipsis=...;limit=math.max(0,math.floor(limit))
    if #value<=limit then return value end
    local suffix=ellipsis and '…' or ''
    return value:sub(1,math.max(0,limit-#suffix))..suffix
  elseif operation=='localeUpper' then return string.upper((...))
  elseif operation=='localeLower' then return string.lower((...))
  elseif operation=='localeCompare' then local a,b=...;return a==b and 0 or (a<b and -1 or 1)
  elseif operation=='localeEndsWith' then local s,suffix=...;return s:sub(-#suffix)==suffix
  elseif operation=='localeSubstring' then local s,start,count=...;return s:sub(start+1,start+count)
  elseif operation=='noBasicHelp' or operation=='smallUiAssets' then return false
  elseif operation=='searchForPediaEntry' then return true
  else error('Unexpected TechTree native operation: '..tostring(operation)) end
end
ZeroSisUiNative=native

local function iterator(rows)
  local i=0
  return function() i=i+1;return rows[i] end
end
local function collection(rows,index)
  return setmetatable({}, {
    __call=function() return iterator(rows) end,
    __index=function(_,key) return index and index[key] end,
  })
end
local techs={
  {ID=7,Type='TECH_TREE_A',Description='TXT_KEY_TECH_TREE_A',Help='TXT_KEY_TECH_TREE_A_HELP',
    PortraitIndex=0,IconAtlas='TECH_ATLAS',Era='ERA_ANCIENT',GridX=4,GridY=5,
    EmbarkedMoveChange=0,AllowsEmbarking=false,AllowsDefensiveEmbarking=false,
    EmbarkedAllWaterPassage=false,UnitFortificationModifier=0,UnitBaseHealModifier=0,
    AllowEmbassyTradingAllowed=false,OpenBordersTradingAllowed=false,
    DefensivePactTradingAllowed=false,ResearchAgreementTradingAllowed=false,
    TradeAgreementTradingAllowed=false,BridgeBuilding=false,MapVisible=false,
    InternationalTradeRoutesChange=0,ScenarioTechButton=0,InfluenceSpreadModifier=0,
    AllowsWorldCongress=false,ExtraVotesPerDiplomat=0},
  {ID=8,Type='TECH_TREE_B',Description='TXT_KEY_TECH_TREE_B',Help='TXT_KEY_TECH_TREE_B_HELP',
    PortraitIndex=1,IconAtlas='TECH_ATLAS',Era='ERA_CLASSICAL',GridX=30,GridY=5,
    EmbarkedMoveChange=0,AllowsEmbarking=false,AllowsDefensiveEmbarking=false,
    EmbarkedAllWaterPassage=false,UnitFortificationModifier=0,UnitBaseHealModifier=0,
    AllowEmbassyTradingAllowed=false,OpenBordersTradingAllowed=false,
    DefensivePactTradingAllowed=false,ResearchAgreementTradingAllowed=false,
    TradeAgreementTradingAllowed=false,BridgeBuilding=false,MapVisible=false,
    InternationalTradeRoutesChange=0,ScenarioTechButton=0,InfluenceSpreadModifier=0,
    AllowsWorldCongress=false,ExtraVotesPerDiplomat=0},
}
local techByID,techByType={},{}
for _,tech in ipairs(techs) do techByID[tech.ID]=tech;techByType[tech.Type]=tech end
local technologyCollection=collection(techs, setmetatable({}, {__index=function(_,key) return techByID[key] or techByType[key] end}))
local eras={
  {ID=0,Type='ERA_ANCIENT',Description='TXT_KEY_ANCIENT_ERA'},
  {ID=1,Type='ERA_CLASSICAL',Description='TXT_KEY_CLASSICAL_ERA'},
}
local eraByID,eraByType={},{}
for _,era in ipairs(eras) do eraByID[era.ID]=era;eraByType[era.Type]=era end
local eraCollection=collection(eras,setmetatable({}, {__index=function(_,key) return eraByID[key] or eraByType[key] end}))
local prereqRows={{TechType='TECH_TREE_B',PrereqTech='TECH_TREE_A'}}
local empty=collection({})
local genericInfo=setmetatable({}, {__index=function() return empty end})
GameInfo=setmetatable({
  Technologies=technologyCollection,Eras=eraCollection,
  Civilizations={[1]={ID=1,Type='CIVILIZATION_FIXTURE'}},
  Technology_PrereqTechs=collection(prereqRows),
  IconTextureAtlases=collection({
    {Atlas='TECH_ATLAS',IconSize=64,Filename='TECH64.dds',IconsPerRow=8,IconsPerColumn=8},
    {Atlas='GENERIC_FUNC_ATLAS',IconSize=45,Filename='GENERIC45.dds',IconsPerRow=8,IconsPerColumn=8},
  },{TECH_ATLAS={Atlas='TECH_ATLAS',IconSize=64,Filename='TECH64.dds',IconsPerRow=8,IconsPerColumn=8},
     GENERIC_FUNC_ATLAS={Atlas='GENERIC_FUNC_ATLAS',IconSize=45,Filename='GENERIC45.dds',IconsPerRow=8,IconsPerColumn=8}}),
}, {__index=function(_,name) return genericInfo[name] end})

GameOptionTypes={GAMEOPTION_NO_SCIENCE=1}
AdvisorTypes={ADVISOR_ECONOMIC=0,ADVISOR_MILITARY=1,ADVISOR_SCIENCE=2,ADVISOR_FOREIGN=3,NUM_ADVISOR_TYPES=4}
DomainTypes={DOMAIN_LAND=0,DOMAIN_SEA=1}
ButtonPopupTypes={BUTTONPOPUP_TECH_TREE=67}
PopupPriority={eUtmost=100,TechTree=50}
Mouse={eLClick='LeftClick',eRClick='RightClick'}
KeyEvents={KeyDown='KeyDown'}
Keys={VK_ESCAPE=27,VK_RETURN=13}
Network={SendResearch=function(...) researchCalls[#researchCalls+1]={...};return true end}

local teamTechs={
  HasTech=function(_,id) return researched[id]==true end,
  GetResearchProgress=function() return 0 end,
  GetResearchCost=function() return 100 end,
}
local player={
  GetCivilizationType=function() return 1 end,
  GetNumFreeTechs=function() return 0 end,
  CanResearch=function() return true end,
  CanResearchForFree=function() return false end,
  CanEverResearch=function() return true end,
  GetResearchTurnsLeft=function() return 10 end,
  GetCurrentResearch=function() return -1 end,
  GetScience=function() return 5 end,
  GetQueuePosition=function() return -1 end,
  GetTeam=function() return 0 end,
  GetResearchCost=function() return 100 end,
  GetResearchProgress=function() return 0 end,
  GetNumTechsToSteal=function() return 0 end,
}
Players={[0]=player}
Teams={[0]={GetTeamTechs=function() return teamTechs end,IsHasTech=function(_,id) return researched[id]==true end}}
Game={GetActivePlayer=function() return 0 end,GetActiveTeam=function() return 0 end,
  SetAdvisorRecommenderTech=function() end,IsOption=function() return false end,
  IsTechRecommended=function() return false end,Rand=function() return 0 end}

local modules={
  InstanceManager=SOURCE_INSTANCE_MANAGER,IconSupport=SOURCE_ICON_SUPPORT,FLuaVector=SOURCE_FLUA_VECTOR,
  InfoTooltipInclude=SOURCE_INFO_TOOLTIP,TechButtonInclude=SOURCE_TECH_BUTTON,
  TechHelpInclude=SOURCE_TECH_HELP,TechTree=SOURCE_TECH_TREE,
}
local loaded={}
function include(name)
  if loaded[name] then return end
  local source=assert(modules[name],'Unexpected TechTree include: '..tostring(name))
  loaded[name]=true
  assert(loadstring(source,'@official/'..name..'.lua'))()
end
assert(loadstring(SOURCE_SCENE,'@UiScene.lua'))()
include('TechTree')
assert(ZeroSisUi.ContextName=='TechTree' and ZeroSisUi.PopupKind=='ResearchTree')

local function findTarget(rows,id,void1)
  for _,target in ipairs(rows) do
    if target.id==id and (void1==nil or target.void1==void1) then return target end
  end
end

ZeroSisUi.Submit({Type=ButtonPopupTypes.BUTTONPOPUP_TECH_TREE,Data1=0,Data2=-1,Data3=-1})
assert(timer==1,'TechTree shown must acquire exactly one timer token')
local opened=ZeroSisUi.Snapshot()
assert(opened:find('"contextName":"TechTree"',1,true) and
  opened:find('"popupKind":"ResearchTree"',1,true),'snapshot context identity mismatch')
assert(opened:find('"timerSemaphore":1',1,true) and
  opened:find('"lifecycle":["queued","shown:67"]',1,true),'snapshot shown lifecycle mismatch')
assert(opened:find('"styleDefaultsSource":{"path":"Assets/UI/Styles.xml"',1,true))
assert(opened:find('"id":"TechTreeScrollPanel"',1,true) and
  opened:find('"orientation":"horizontal"',1,true) and opened:find('"scrollX":0',1,true),
  'horizontal panel state missing from capture')
local initialMaximum=tonumber(opened:match('"id":"TechTreeScrollPanel".-"maximumScroll":([%d%.e%-]+)'))
assert(initialMaximum and initialMaximum>0,'component fixture must exercise a measured horizontal overflow')
local buttonTarget=findTarget(ZeroSisUi.GetInputTargets(),'TechButton',7)
assert(buttonTarget,'official normal research button left target missing')
assert(ZeroSisUi.DispatchLeftClick(buttonTarget.key)==true)
assert(#researchCalls==1 and researchCalls[1][1]==7 and researchCalls[1][2]==0 and
  researchCalls[1][3]==-1 and researchCalls[1][4]==false,'normal TechSelected tuple differs')
assert(timer==1 and ZeroSisUi.IsActive(),'research selection must leave TechTree open')

local preDirty=ZeroSisUi.Snapshot()
researched[7]=true
Events.SerialEventResearchDirty()
local postDirty=ZeroSisUi.Snapshot()
assert(postDirty:find('"timerSemaphore":1',1,true) and
  postDirty:find('"id":"AlreadyResearched"',1,true) and
  postDirty:match('"id":"AlreadyResearched".-"hidden":false'),
  'ResearchDirty did not update captured row state')
assert(preDirty:match('"id":"AlreadyResearched".-"hidden":true'),
  'pre-dirty tech style did not retain initial state')
local maxScroll=tonumber(postDirty:match('"id":"TechTreeScrollPanel".-"maximumScroll":([%d%.e%-]+)'))
assert(maxScroll and maxScroll>0 and postDirty:find('"scrollX":0',1,true),
  'measured horizontal range missing after ResearchDirty')
local scrollHandle=Controls.TechTreeScrollPanel
assert(scrollHandle,'retained TechTree scroll panel handle missing')
scrollHandle:SetScrollValue(maxScroll)
assert(scrollHandle:GetScrollValue()==maxScroll,'horizontal scroll did not reach measured maximum')
local scrolled=ZeroSisUi.Snapshot()
assert(scrolled:find('"scrollX":'..tostring(maxScroll),1,true),
  'captured horizontal offset differs from owner state')
scrollHandle:SetScrollValue(0)
assert(scrollHandle:GetScrollValue()==0,'horizontal reset did not return to origin')
local badScroll=pcall(function() scrollHandle:SetScrollValue(maxScroll+1) end)
assert(not badScroll,'horizontal scroll accepted an out-of-range offset')

assert(ZeroSisUi.DispatchKeyDown(Keys.VK_ESCAPE)==true,'TechTree Escape close rejected')
assert(timer==0 and not ZeroSisUi.IsActive(),'TechTree close did not release timer')
local closed=ZeroSisUi.Snapshot()
assert(closed:find('"lifecycle":["queued","shown:67","closed","processed:67"]',1,true))
assert(table.concat(timerCalls,',')=='1,-1','TechTree timer acquisition/release was unbalanced')
assert(native('uiShift')==false,'fixture shift state changed')

__techTreeUiComponentReport='{"status":"PASS_RESEARCH_TREE_LUA_COMPONENT_ONLY",'..
  '"contextName":"TechTree","popupKind":"ResearchTree","officialPopupEnum":67,'..
  '"shownTimer":1,"closedTimer":0,"openLifecycle":["queued","shown:67"],'..
  '"closeLifecycle":["queued","shown:67","closed","processed:67"],'..
  '"shiftResearchTuple":[7,0,-1,false],"researchDirtyUpdatedCapture":true,'..
  '"horizontalShortRange":0,"horizontalOverflowCaptured":true,"horizontalMaximum":'..
  tostring(maxScroll)..',"scrollResetChecked":true,"retailLayoutAndPixelsVerified":false,'..
  '"sdkResearchVerified":false,"rendererVerified":false}'
