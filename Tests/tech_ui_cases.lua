-- Component-only execution of the original BNW TechPopup and its two tech
-- includes against the retained Research scene. SDK state is mocked here;
-- this proves the Lua/control contract, not a live research command.
local SOURCE_INSTANCE_MANAGER = @@SOURCE_INSTANCE_MANAGER@@
local SOURCE_ICON_SUPPORT = @@SOURCE_ICON_SUPPORT@@
local SOURCE_FLUA_VECTOR = @@SOURCE_FLUA_VECTOR@@
local SOURCE_INFO_TOOLTIP = @@SOURCE_INFO_TOOLTIP@@
local SOURCE_TECH_BUTTON = @@SOURCE_TECH_BUTTON@@
local SOURCE_TECH_HELP = @@SOURCE_TECH_HELP@@
local SOURCE_TECH_POPUP = @@SOURCE_TECH_POPUP@@
local SOURCE_SCENE = @@SCENE_SOURCE@@
ZeroSisUiLayout = @@LAYOUT@@
table.insert(ZeroSisUiLayout.children,{kind='Instance',attributes={Name='TechTabCase'},children={
  {kind='Label',attributes={ID='TabIndent',Font='TwCenMT22',String='[TAB][TAB]A'},children={}},
  {kind='Label',attributes={ID='WrappedTabIndent',Font='TwCenMT22',String='[TAB][TAB]A',WrapWidth='500'},children={}},
}})
table.insert(ZeroSisUiLayout.children,{kind='Instance',attributes={Name='TechScrollClipCase'},children={
  {kind='Box',attributes={ID='TechClipFixture',Hidden='1',Anchor='L,T',Size='0,0'},children={
    {kind='ScrollPanel',attributes={ID='TechClipOuter',Anchor='L,T',Offset='500,700',Size='100,100',Vertical='1'},children={
      {kind='ScrollPanel',attributes={ID='TechClipInner',Anchor='L,T',Offset='50,50',Size='150,150',Vertical='1'},children={
        {kind='Button',attributes={ID='TechClipContent',Anchor='L,T',Size='50,250'},children={}},
      }},
    }},
  }},
}})

local function iterator(rows)
  local index=0
  return function()
    index=index+1
    return rows[index]
  end
end
local function collection(rows)
  return setmetatable(rows or {},{__call=function(self,...) return iterator(self) end})
end
local technology={ID=7,Type='TECH_FIXTURE',Description='TXT_KEY_TECH_FIXTURE',
  Help='TXT_KEY_TECH_FIXTURE_HELP',PortraitIndex=0,IconAtlas='TECH_ATLAS',
  EmbarkedMoveChange=0,AllowsEmbarking=false,AllowsDefensiveEmbarking=false,
  EmbarkedAllWaterPassage=false,UnitFortificationModifier=0,UnitBaseHealModifier=0,
  AllowEmbassyTradingAllowed=false,OpenBordersTradingAllowed=false,DefensivePactTradingAllowed=false,
  ResearchAgreementTradingAllowed=false,TradeAgreementTradingAllowed=false,BridgeBuilding=false,
  MapVisible=false,InternationalTradeRoutesChange=0,ScenarioTechButton=0,InfluenceSpreadModifier=0,
  AllowsWorldCongress=false,ExtraVotesPerDiplomat=0}
local technologyRows={technology}
local technologyByID={[7]=technology}
local technologyByType={TECH_FIXTURE=technology}
local technologyCollection=setmetatable({}, {
  __call=function() return iterator(technologyRows) end,
  __index=function(_,key) return technologyByID[key] or technologyByType[key] end,
})
local atlasRows={
  {Atlas='TECH_ATLAS',IconSize=64,Filename='TECH64.dds',IconsPerRow=8,IconsPerColumn=8},
  {Atlas='GENERIC_FUNC_ATLAS',IconSize=45,Filename='GENERIC45.dds',IconsPerRow=8,IconsPerColumn=8},
}
GameInfo={
  Technologies=technologyCollection,Civilizations={[1]={ID=1,Type='CIVILIZATION_FIXTURE'}},
  Technology_PrereqTechs=collection({}),UnitClasses=collection({}),
  Civilization_UnitClassOverrides=collection({}),BuildingClasses=collection({}),
  Civilization_BuildingClassOverrides=collection({}),Improvements=collection({}),
  Units=collection({}),Buildings=collection({}),Resources=collection({}),Projects=collection({}),
  Builds=collection({}),Processes=collection({}),Route_TechMovementChanges=collection({}),
  Routes={},Improvement_TechYieldChanges=collection({}),Yields={},
  Improvement_TechNoFreshWaterYieldChanges=collection({}),Improvement_TechFreshWaterYieldChanges=collection({}),
  Technology_TradeRouteDomainExtraRange=collection({}),Domains={},Technology_FreePromotions=collection({}),
  UnitPromotions={},Concepts={},IconTextureAtlases=collection(atlasRows),
}
GameInfo.Civilizations.CIVILIZATION_FIXTURE=GameInfo.Civilizations[1]
GameOptionTypes={GAMEOPTION_NO_SCIENCE=1}
AdvisorTypes={ADVISOR_ECONOMIC=0,ADVISOR_MILITARY=1,ADVISOR_SCIENCE=2,ADVISOR_FOREIGN=3,NUM_ADVISOR_TYPES=4}
DomainTypes={DOMAIN_LAND=0,DOMAIN_SEA=1}
ButtonPopupTypes={BUTTONPOPUP_CHOOSETECH=501,BUTTONPOPUP_CHOOSE_TECH_TO_STEAL=502,BUTTONPOPUP_TECH_TREE=503}
local researchCalls={}
Network={SendResearch=function(...) researchCalls[#researchCalls+1]={...} end}
local teamTechs={HasTech=function() return false end,GetResearchProgress=function() return 0 end,
  GetResearchCost=function() return 100 end}
local player={
  GetCivilizationType=function() return 1 end,GetNumFreeTechs=function() return 0 end,
  CanResearch=function(_,id) return id>=7 and id<=22 end,CanResearchForFree=function() return true end,
  GetResearchTurnsLeft=function() return 4 end,GetCurrentResearch=function() return -1 end,
  GetScience=function() return 5 end,GetQueuePosition=function() return -1 end,
  GetTeam=function() return 0 end,GetResearchCost=function() return 100 end,
  GetResearchProgress=function() return 0 end,
}
Players={[0]=player}
Teams={[0]={GetTeamTechs=function() return teamTechs end,IsHasTech=function() return false end}}
Game={GetActivePlayer=function() return 0 end,GetActiveTeam=function() return 0 end,
  SetAdvisorRecommenderTech=function() end,IsOption=function() return false end,
  IsTechRecommended=function() return false end,Rand=function() return 0 end}
local function native(operation,...)
  if operation=='snapshotJson' then return __ZeroSisSnapshotJson(...) end
  if operation=='uiFrameTime' then return 0 end
  if operation=='randomSeed' then return 23 end
  if operation=='screenSize' then return 1920,1080 end
  if operation=='smallUiAssets' or operation=='noBasicHelp' then return false end
  if operation=='locale' or operation=='localeTruncate' or operation=='localeUpper' or
     operation=='localeLower' then return tostring(select(1,...)) end
  if operation=='localeCompare' then return 0 end
  if operation=='localeLength' then return #(select(1,...)) end
  if operation=='localeSubstring' then
    local value,start,count=...
    return string.sub(value,start+1,start+count)
  end
  if operation=='localeEndsWith' then
    local value,suffix=...
    return string.sub(value,-#suffix)==suffix
  end
  if operation=='searchForPediaEntry' then return end
  error('unexpected Research fixture native operation: '..tostring(operation))
end
ZeroSisUiNative=native
local scene=assert(loadstring(SOURCE_SCENE,'@research-scene'))
setfenv(scene,getfenv(0));scene()
local sources={InstanceManager=SOURCE_INSTANCE_MANAGER,IconSupport=SOURCE_ICON_SUPPORT,
  FLuaVector=SOURCE_FLUA_VECTOR,InfoTooltipInclude=SOURCE_INFO_TOOLTIP,
  TechButtonInclude=SOURCE_TECH_BUTTON,TechHelpInclude=SOURCE_TECH_HELP}
function include(name)
  local source=assert(sources[name],'unprepared original TechPopup include: '..tostring(name))
  local chunk=assert(loadstring(source,'@'..name))
  setfenv(chunk,getfenv(0));return chunk()
end
Events=Events -- scene owns the official event table
assert(ButtonPopupTypes.BUTTONPOPUP_CHOOSETECH==501)
includeChunk=assert(loadstring(SOURCE_TECH_POPUP,'@TechPopup.lua'))
setfenv(includeChunk,getfenv(0));includeChunk()
ZeroSisUi.Submit({Type=ButtonPopupTypes.BUTTONPOPUP_CHOOSETECH,Data1=0,Data2=-1,Data3=-1})
local before=ZeroSisUi.Snapshot()
assert(before:find('"contextName":"TechPopup"',1,true) and
  before:find('"popupKind":"Research"',1,true),'TechPopup context identity was not captured')
assert(before:find('"timerSemaphore":0',1,true),'TechPopup incorrectly acquired the turn timer')
assert(before:find('"shown:501"',1,true),'TechPopup shown callback lifecycle was not retained')
assert(before:find('"id":"TechButton"',1,true) and before:find('"void1":7',1,true) and
  before:find('"void2":0',1,true),'official TechButton row or exact void payload was not retained')
assert(before:find('"id":"ScrollPanel"',1,true) and before:find('"maximumScroll":0',1,true),
  'short TechPopup list did not retain its measured zero-scroll range')
assert(before:find('"shuttleBounds":',1,true) and
  before:find('"retailScrollbarGeometryVerified":false',1,true),
  'TechPopup did not retain its explicit candidate scrollbar geometry policy')
local targets=ZeroSisUi.GetInputTargets('LeftClick')
local techTarget
for _,target in ipairs(targets) do if target.id=='TechButton' then techTarget=target end end
assert(techTarget and techTarget.void1==7 and techTarget.void2==0,
  'official TechButton LeftClick identity/payload did not reach the native target list')
assert(ZeroSisUi.DispatchLeftClick(techTarget.key,'LeftClick'),'official TechSelected callback was not dispatched')
assert(#researchCalls==1 and researchCalls[1][1]==7 and researchCalls[1][2]==0 and
  researchCalls[1][3]==-1 and researchCalls[1][4]==false,
  'official Network.SendResearch ordinary selection arguments changed')
assert(not ZeroSisUi.IsActive(),'TechSelected did not close the official popup')
assert(ZeroSisUi.Snapshot():find('"processed:501"',1,true),
  'TechPopup close did not retain its processed event after SetHide')
for id=8,22 do
  local row={}
  for key,value in pairs(technology) do row[key]=value end
  row.ID=id;row.Type='TECH_FIXTURE_'..id;row.Description='TXT_KEY_TECH_FIXTURE_'..id
  technologyByID[id]=row;technologyByType[row.Type]=row;technologyRows[#technologyRows+1]=row
end
ZeroSisUi.Submit({Type=ButtonPopupTypes.BUTTONPOPUP_CHOOSETECH,Data1=0,Data2=-1,Data3=-1})
local overflow=ZeroSisUi.Snapshot()
local maxStart=assert(overflow:find('"maximumScroll":',1,true),'missing measured overflow range')
local maxText=assert(overflow:sub(maxStart):match('"maximumScroll":([%d%.]+)'))
local _,capturedTechRows=overflow:gsub('"id":"TechButton"','')
local positiveOverflowMaximum=tonumber(maxText)
assert(positiveOverflowMaximum>0,'official dynamic TechButton Stack did not produce positive measured overflow: '..
  tostring(maxText)..'; capturedRows='..tostring(capturedTechRows)..'; '
  ..tostring(overflow:match('"contentHeight":([%d%.]+)')))
local clipNames={}
ContextPtr:BuildInstance('TechScrollClipCase',clipNames)
clipNames.TechClipFixture:SetHide(false)
clipNames.TechClipInner:CalculateInternalSize()
clipNames.TechClipOuter:CalculateInternalSize()
local clipped=ZeroSisUi.Snapshot()
assert(clipped:find('"clippedBounds":{"height":50,"width":50,"x":550,"y":750}',1,true),
  'nested official retained ScrollPanel did not clip to the ancestor viewport')
local styleChildren=ZeroSisUiLayout.styleDefaults.VertSlider.children
ZeroSisUiLayout.styleDefaults.VertSlider.children={}
local malformedAccepted=pcall(ZeroSisUi.Snapshot)
ZeroSisUiLayout.styleDefaults.VertSlider.children=styleChildren
assert(not malformedAccepted,'missing official VertShuttle style was silently accepted')
local closeOk=ZeroSisUi.DispatchKeyDown(Keys.VK_ESCAPE)
assert(closeOk and not ZeroSisUi.IsActive(),'second TechPopup did not close through its registered Escape handler')
local tabNames={};ContextPtr:BuildInstance('TechTabCase',tabNames)
local tabFont=assert(ZeroSisUiLayout.fontMetrics.fonts.TwCenMT22)
local tabGlyphs=assert(ZeroSisUiLayout.fontMetrics.glyphSets[tabFont.glyphSet])
assert(tabNames.TabIndent:GetSizeX()==8*tabGlyphs[32].advance+tabGlyphs[65].advance,
  'two original TAB tokens did not retain their declared non-collapsing indentation')
assert(ZeroSisUi.Snapshot():find('"text":"\\u0009\\u0009A"',1,true),
  'wrapped original TAB indentation disappeared from the measured text lines')

-- Exercise the independent TechAward scene contract without treating it as a
-- research command. The official Lua owns the shown/hidden calls; this focused
-- fixture models those exact callbacks and the original enum/priority.
local awardTimerCalls={}
local awardLayout={attributes={},contextName='TechAwardPopup',popupKind='TechAward',
  fontMetrics={policy='CIV5_GLYPHGEN_GGXML_LAYOUT_V1',retailMetricSemanticsVerified=false,
    wrapPolicy='GREEDY_ASCII_SPACE_WORD_WRAP_SPLIT_LONG_WORD_AT_CODEPOINT',fonts={},glyphSets={},inlineIcons={}},
  styleDefaults={},styleDefaultsSource={},
  styleDefaultsPolicy='OFFICIAL_STYLES_XML_ATTRIBUTES_WITH_CONTROL_XML_OVERRIDES',children={
    {kind='Grid',attributes={ID='OuterGrid',Size='560,530',Padding='20,50'},children={
      {kind='Stack',attributes={Size='0,0',StackGrowth='Bottom',Offset='0,64'},children={
        {kind='Stack',attributes={ID='BonusStack',Size='0,0',StackGrowth='Right',Padding='-12'},children={
          {kind='Button',attributes={ID='Award1',Size='64,64'},children={}},
          {kind='Button',attributes={ID='Award2',Size='64,64'},children={}},
          {kind='Button',attributes={ID='Award3',Size='64,64'},children={}},
          {kind='Button',attributes={ID='Award4',Size='64,64'},children={}},
          {kind='Button',attributes={ID='Award5',Size='64,64'},children={}},
        }},
        {kind='Image',attributes={ID='AwardContentFixture',Size='500,400'},children={}},
      }},
      {kind='GridButton',attributes={ID='ContinueButton',Size='10,10'},children={}},
      {kind='GridButton',attributes={ID='CloseButton',Size='10,10',Hidden='1'},children={}},
    }},
  }}
local awardEnv=setmetatable({ZeroSisUiLayout=awardLayout,
  ZeroSisUiNative=function(operation,...)
    if operation=='snapshotJson' then return __ZeroSisSnapshotJson(...) end
    if operation=='uiFrameTime' then return 1 end
    if operation=='screenSize' then return 1920,1080 end
    if operation=='randomSeed' then return 23 end
    if operation=='timer' then awardTimerCalls[#awardTimerCalls+1]=select(1,...);return end
    if operation=='locale' or operation=='localeTruncate' or operation=='localeUpper' or operation=='localeLower' then
      return tostring(select(1,...))
    end
    if operation=='localeCompare' then return 0 end
    if operation=='localeLength' then return #(select(1,...)) end
    if operation=='localeSubstring' then local value,start,count=...;return string.sub(value,start+1,start+count) end
    if operation=='localeEndsWith' then local value,suffix=...;return string.sub(value,-#suffix)==suffix end
    error('unexpected TechAward fixture native operation: '..tostring(operation))
  end,
  ButtonPopupTypes={BUTTONPOPUP_TECH_AWARD=68},
  Game={Rand=function() return 0 end}}, {__index=getfenv(0)})
local awardScene=assert(loadstring(SOURCE_SCENE,'@tech-award-scene'))
setfenv(awardScene,awardEnv);awardScene()
local awardContinue=awardEnv.Controls.ContinueButton
awardContinue:RegisterCallback(awardEnv.Mouse.eLClick,function()
  awardEnv.UIManager:DequeuePopup(awardEnv.ContextPtr)
end)
awardEnv.ContextPtr:SetShowHideHandler(function(hidden,initial)
  if not initial then
    if hidden then
      awardEnv.UI.decTurnTimerSemaphore()
      awardEnv.Events.SerialEventGameMessagePopupProcessed.CallImmediate(68,0)
    else
      awardEnv.UI.incTurnTimerSemaphore()
      awardEnv.Events.SerialEventGameMessagePopupShown.CallImmediate({Type=68})
    end
  end
end)
awardEnv.Events.SerialEventGameMessagePopup.Add(function(info)
  if info.Type==68 then awardEnv.UIManager:QueuePopup(awardEnv.ContextPtr,awardEnv.PopupPriority.TechAward) end
end)
awardEnv.Controls.BonusStack:CalculateSize()
assert(awardEnv.Controls.BonusStack:GetSizeX()==272,
  'TechAward BonusStack did not preserve original Padding=-12 sizing')
awardEnv.Controls.OuterGrid:DoAutoSize()
assert(awardEnv.Controls.OuterGrid:GetSizeX()==560 and awardEnv.Controls.OuterGrid:GetSizeY()==628,
  'TechAward auto-size did not retain original 560x530 base plus bounded content/padding')
awardEnv.ZeroSisUi.Submit({Type=68})
assert(awardEnv.ZeroSisUi.IsActive() and awardEnv.ZeroSisUi.Snapshot():find('"timerSemaphore":1',1,true),
  'TechAward did not acquire shown popup input/timer state')
local awardTargets=awardEnv.ZeroSisUi.GetInputTargets(awardEnv.Mouse.eLClick)
local awardContinueTarget
for _,target in ipairs(awardTargets) do
  assert(target.id~='CloseButton','hidden TechAward close button leaked into input targets')
  if target.id=='ContinueButton' then awardContinueTarget=target end
end
assert(awardContinueTarget and awardEnv.ZeroSisUi.DispatchLeftClick(awardContinueTarget.key),
  'TechAward ContinueButton was not an active input target')
local awardClosedSnapshot=awardEnv.ZeroSisUi.Snapshot()
assert(not awardEnv.ZeroSisUi.IsActive() and
  awardClosedSnapshot:find('"lifecycle":["queued","shown:68","processed:68","closed"]',1,true) and
  #awardTimerCalls==2 and
  awardTimerCalls[1]==1 and awardTimerCalls[2]==-1,
  'TechAward close did not preserve stock processed-before-closed lifecycle and timer symmetry')
local checkedAwardEnum=awardEnv.ZeroSisUi.Submit
assert(type(checkedAwardEnum)=='function','TechAward fixture lost the independent BUTTONPOPUP_TECH_AWARD submit path')
__techUiComponentReport='{"status":"PASS_RESEARCH_POPUP_LUA_COMPONENT_ONLY",'..
  '"contextName":"TechPopup","popupKind":"Research","popupType":501,"timerSemaphore":0,'..
  '"officialTechSelectedArguments":[7,0,-1,false],"dynamicTechButtonCaptured":true,'..
  '"officialTechButtonVoidPair":[7,0],"officialShownAndProcessedLifecycle":true,'..
  '"shortListMaximumScroll":0,"positiveOverflowCaptured":true,"malformedShuttleRejected":true,'..
  '"positiveOverflowMaximum":'..tostring(positiveOverflowMaximum)..',"nestedScrollClippingChecked":true,'..
  '"rightClickPediaRuntimeVerified":false,'..
  '"retailLayoutAndPixelsVerified":false,"snapshot":'..before..'}'
