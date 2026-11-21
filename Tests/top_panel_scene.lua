-- Component-only fixture: unmodified installed BNW TopPanel.lua runs against
-- representative SDK-shaped objects and a recording native bridge. This is
-- not evidence of retail SDK binding, host rendering, or live-game behavior.
local SOURCE_TOP_PANEL = @@SOURCE_TOP_PANEL@@
local SCENE_SOURCE = @@SCENE_SOURCE@@
local INPUT_SOURCE = @@INPUT_SOURCE@@
ZeroSisUiLayout = @@LAYOUT@@
ZeroSisUiLayout.fontMetrics = @@FONT_METRICS@@
ZeroSisUiLayout.styleDefaults = @@STYLE_DEFAULTS@@
ZeroSisUiLayout.styleDefaultsSource = 'installed Styles.xml fixture'
ZeroSisUiLayout.styleDefaultsPolicy = 'component fixture source styles'

local operations, lastSnapshotValue = {}, nil
local ownerClock = 1
local function native(operation, ...)
  local args={...}
  if operation=='snapshotJson' then
    lastSnapshotValue=args[1]
    return __ZeroSisSnapshotJson(...)
  end
  if operation=='activePlayer' then return 0 end
  if operation=='uiFrameTime' then return ownerClock end
  if operation=='screenSize' then return 1920,1080 end
  if operation=='uiShift' then return false end
  if operation=='randomSeed' then return 17 end
  if operation=='headSelectedCity' then return nil,nil end
  if operation=='locale' then
    local text=tostring(args[1])
    for i=2,#args do text=text..' '..tostring(args[i]) end
    return text
  end
  if operation=='localeUpper' then return string.upper(tostring(args[1])) end
  if operation=='queueTopPanelPopup' then
    operations[#operations+1]={name=operation,type=args[1],data2=args[2]}
    return true
  end
  error('Unexpected native operation: '..tostring(operation))
end
ZeroSisUiNative=native

local resources={{ID=1,TechReveal='TECH_IRON_WORKING',TechCityTrade='TECH_IRON_WORKING',IconString='[ICON_RES_IRON]'}}
GameInfo={}
GameInfo.Victories={}
function GameInfo.Resources()
  local index=0
  return function() index=index+1;return resources[index] end
end
GameInfoTypes={TECH_IRON_WORKING=1}
ResourceUsageTypes={RESOURCEUSAGE_STRATEGIC=1}
GameOptionTypes={GAMEOPTION_NO_SCIENCE=1,GAMEOPTION_NO_HAPPINESS=2,
  GAMEOPTION_NO_POLICIES=3,GAMEOPTION_NO_RELIGION=4}
ButtonPopupTypes={BUTTONPOPUP_TECH_TREE=901}
Locale={}
function Locale.ConvertTextKey(key,...)
  local result=tostring(key)
  for i=1,select('#',...) do result=result..' '..tostring(select(i,...)) end
  return result
end
function Locale.ToUpper(value) return string.upper(value) end
OptionsManager={}
function OptionsManager.IsNoBasicHelp() return false end

local cityCount=1
local player={}
local playerValues={
  GetTeam=function() return 0 end,GetNumCities=function() return cityCount end,
  GetScience=function() return 12 end,CalculateGoldRate=function() return 3 end,
  GetGold=function() return 44 end,GetNumInternationalTradeRoutesUsed=function() return 1 end,
  GetNumInternationalTradeRoutesAvailable=function() return 3 end,GetExcessHappiness=function() return 5 end,
  IsEmpireUnhappy=function() return false end,IsEmpireVeryUnhappy=function() return false end,
  GetGoldenAgeTurns=function() return 0 end,GetGoldenAgeTourismModifier=function() return 0 end,
  GetGoldenAgeProgressMeter=function() return 4 end,GetGoldenAgeProgressThreshold=function() return 20 end,
  GetNextPolicyCost=function() return 25 end,GetJONSCulture=function() return 10 end,
  GetTotalJONSCulturePerTurn=function() return 2 end,GetTourism=function() return 7 end,
  GetFaith=function() return 8 end,GetTotalFaithPerTurn=function() return 1 end,
  GetNumGreatWorks=function() return 2 end,GetNumGreatWorkSlots=function() return 5 end,
  GetNumResourceAvailable=function() return 2 end,GetNumResourceUsed=function() return 1 end,
  GetNumResourceTotal=function() return 3 end,GetUnitProductionMaintenanceMod=function() return 0 end,
  IsUsingMayaCalendar=function() return false end,IsAnarchy=function() return false end,
}
for name,fn in pairs(playerValues) do player[name]=fn end
Players={[0]=player}
local teamTechs={}
function teamTechs:HasTech() return true end
local team={}
function team:GetTeamTechs() return teamTechs end
Teams={[0]=team}
Game={}
function Game.GetActivePlayer() return 0 end
function Game.IsOption() return false end
function Game.GetGameTurn() return 1 end
function Game.GetTurnString() return '4000 BC' end
function Game.GetResourceUsageType() return ResourceUsageTypes.RESOURCEUSAGE_STRATEGIC end
function Game.Rand() return 0 end
UI={}
function UI.GetHeadSelectedCity() return nil end
function UI.IsCityScreenUp() return false end

assert(loadstring(SCENE_SOURCE..'\n'..INPUT_SOURCE))()
function UI.IsCityScreenUp() return false end
assert(loadstring(SOURCE_TOP_PANEL))()
assert(ZeroSisUi.ContextName=='TopPanel' and ZeroSisUi.PopupKind=='TopPanel')
local function originalBarLayout(infoHidden)
  ZeroSisUi.Snapshot()
  local snapshot=assert(lastSnapshotValue)
  local right,bar,info
  local byId={}
  local function visit(node)
    if node.id~='' then byId[node.id]=node end
    local attrs=node.sourceAttributes
    if node.kind=='Stack' and attrs.Anchor=='R,T' and attrs.StackGrowth=='Left' then
      assert(not right,'Original right TopPanel Stack is not unique');right=node
    end
    if node.kind=='Image' and attrs.Size=='Full.32' then
      assert(not bar,'Original full-width TopPanel bar is not unique');bar=node
    end
    for _,child in ipairs(node.children or {}) do visit(child) end
  end
  visit(snapshot.tree)
  info=assert(byId.TopPanelInfoStack)
  assert(right and bar and right.sourceAttributes.Size==nil and
    right.sourceAttributes.Offset=='10,4' and right.sourceAttributes.Padding=='10',
    'Original size-less right TopPanel Stack declaration changed')
  local width,height,count=0,0,0
  for _,child in ipairs(right.children) do
    if not child.hidden then
      width=width+child.width;height=math.max(height,child.height);count=count+1
    end
  end
  width=width+math.max(0,count-1)*tonumber(right.sourceAttributes.Padding)
  assert(right.width==width and right.height==height and width>0 and height>0,
    'Original right TopPanel Stack was not measured before child anchoring')
  assert(right.x==snapshot.tree.width-width-10 and right.y==4,
    'Original right TopPanel Stack R,T anchor or offset changed')
  assert(bar.y==0 and bar.height==32 and bar.width==snapshot.tree.width,
    'Original 32px full-width TopPanel bar changed')
  for _,id in ipairs({'MenuButton','CivilopediaButton','CurrentTurn','CurrentDate'}) do
    local node=assert(byId[id])
    assert(not node.hidden and node.x>=0 and node.y>=bar.y and
      node.x+node.width<=bar.width and node.y+node.height<=bar.y+bar.height,
      'Original TopPanel caption escapes its bar: '..id)
  end
  for _,target in ipairs(snapshot.inputTargets) do
    if target.id=='MenuButton' or target.id=='CivilopediaButton' then
      local node=byId[target.id]
      for _,axis in ipairs({'x','y','width','height'}) do
        assert(target.bounds[axis]==node[axis] and target.clippedBounds[axis]==node[axis],
          'Original right TopPanel hit was clipped or differs from its caption: '..target.id)
      end
    end
    assert(not infoHidden or target.id~='SciencePerTurn',
      'Original zero-city condition retained a hidden science callback')
  end
  assert(info.hidden==infoHidden and info.sourceAttributes.Anchor=='L,T' and
    info.sourceAttributes.Offset=='10,6' and info.sourceAttributes.Size==nil,
    'Original TopPanel info Stack visibility or source declaration changed')
end
originalBarLayout(false)
cityCount=0
assert(ZeroSisTopPanelRefresh()==true)
originalBarLayout(true)
cityCount=1
assert(ZeroSisTopPanelRefresh()==true)
originalBarLayout(false)
local targets=ZeroSisUi.GetInputTargets()
local targetById={}
for _,target in ipairs(targets) do targetById[target.id]=target end
assert(targetById.SciencePerTurn and targetById.GoldPerTurn and targetById.MenuButton and targetById.CivilopediaButton,
  'original top-panel buttons were not retained as input targets: '..table.concat((function()
    local ids={};for _,target in ipairs(targets) do ids[#ids+1]=target.id end;return ids
  end)(),',')..' active='..tostring(ZeroSisUi.IsActive())..' hidden='..tostring(ContextPtr:IsHidden()))
for _,id in ipairs({'SciencePerTurn','GoldPerTurn','InternationalTradeRoutes','HappinessString',
  'GoldenAgeString','CultureString','TourismString','FaithString','ResourceString',
  'MenuButton','CivilopediaButton'}) do
  assert(Controls[id],'stock TopPanel control is missing: '..id)
end
for _,id in ipairs({'SciencePerTurn','GoldPerTurn','InternationalTradeRoutes',
  'CultureString','TourismString','FaithString','MenuButton','CivilopediaButton'}) do
  assert(targetById[id],'stock TopPanel click target is missing: '..id)
end
local consumeMouseCount=0
for _,target in ipairs(targets) do if target.event=='ConsumeMouse' and target.consumeMouse==true then
  consumeMouseCount=consumeMouseCount+1
end end
assert(consumeMouseCount==2,'original TopPanel ConsumeMouse bars were not retained exactly')
assert(targetById.SciencePerTurn.event=='LeftClick')
assert(targetById.SciencePerTurn.toolTipCallback==nil or targetById.SciencePerTurn.toolTipCallback==true)
assert(Controls.SciencePerTurn:GetText():find('[ICON_RESEARCH]',1,true))
assert(Controls.ResourceString:GetText():find('[ICON_RES_IRON]',1,true))
local originalGold=Controls.GoldPerTurn:GetText()
local originalScience=Controls.SciencePerTurn:GetText()
local negativeGold='[ICON_GOLD][COLOR:255:235:0:255]"4180" [COLOR:255:60:60:255](-1)"[ENDCOLOR]'
for _,text in ipairs({negativeGold,
  '[ICON_GOLD][COLOR:255:235:0:255]4180 [COLOR:255:60:60:255](-1)[ENDCOLOR]',
  (negativeGold:gsub('%[ENDCOLOR%]$','[/COLOR]'))}) do
  Controls.GoldPerTurn:SetText(text)
  ZeroSisUi.Snapshot()
  assert(Controls.GoldPerTurn:GetText()==text,'Original negative-GPT source text was rewritten')
end
for _,text in ipairs({negativeGold:gsub('255:60:60:255','255:60:61:255'),
  negativeGold..'[COLOR:1:2:3:255]'}) do
  assert(not pcall(function() Controls.GoldPerTurn:SetText(text);ZeroSisUi.Snapshot() end),
    'Malformed gold markup escaped the exact original negative-GPT scope')
  Controls.GoldPerTurn:SetText(originalGold)
end
assert(not pcall(function() Controls.SciencePerTurn:SetText(negativeGold);ZeroSisUi.Snapshot() end),
  'The gold color exception leaked into a different control')
Controls.SciencePerTurn:SetText(originalScience)
Controls.GoldPerTurn:SetText(originalGold)
local science=targetById.SciencePerTurn.key
assert(ZeroSisUi.DispatchLeftClick(science,'LeftClick')==true)
assert(#operations==1 and operations[1].name=='queueTopPanelPopup' and
  operations[1].type==ButtonPopupTypes.BUTTONPOPUP_TECH_TREE and operations[1].data2==-1,
  'science popup request was missing or not deferred with original typed data')
assert(targetById.TourismString and targetById.TourismString.toolTipCallback==true,
  'tourism input target omitted its original tooltip callback')
local hoverClock=ownerClock
assert(ZeroSisUi.DispatchPointerMove(0),'TopPanel initial pointer clear was rejected')
local noHoverSnapshot=ZeroSisUi.Snapshot()
assert(ZeroSisUi.DispatchPointerMove(0) and ZeroSisUi.Snapshot()==noHoverSnapshot,
  'TopPanel repeated key-zero clear changed its retained snapshot at the same owner clock')
assert(not ZeroSisUi.DispatchPointerMove(999999) and ZeroSisUi.Snapshot()==noHoverSnapshot,
  'TopPanel rejected pointer changed its retained snapshot')
assert(ZeroSisUi.DispatchPointerMove(targetById.TourismString.key),'live TopPanel hover was rejected')
local hoverSnapshot=ZeroSisUi.Snapshot()
assert(hoverSnapshot~=noHoverSnapshot,'TopPanel pointer entry did not change retained button state')
assert(ZeroSisUi.DispatchPointerMove(targetById.TourismString.key) and ZeroSisUi.Snapshot()==hoverSnapshot,
  'TopPanel same-key hover changed its retained snapshot at the same owner clock')
assert(ZeroSisUi.ToolTip(targetById.TourismString.key)==true,
  'original TopPanel tooltip callback did not run for the live TourismString control')
local tooltipSnapshotJson=ZeroSisUi.Snapshot()
assert(tooltipSnapshotJson~=hoverSnapshot and ZeroSisUi.Snapshot()==tooltipSnapshotJson,
  'TopPanel tooltip callback did not change or stabilize its actual retained snapshot')
local tooltipSnapshot=assert(lastSnapshotValue.topPanelTooltip)
assert(tooltipSnapshot.type=='TooltipTypeTopPanel' and tooltipSnapshot.tree.id=='TopPanelMouseover' and
  tooltipSnapshot.tree.autoSizeRequested==true and tooltipSnapshot.retailPlacementVerified==false and
  tooltipSnapshot.retailAutosizeVerified==false,'original tooltip callback state was not retained explicitly')
-- The same key is not sufficient to classify a no-op: the original pointer
-- handler clears a displayed tooltip, which remains a real visual change.
assert(ZeroSisUi.DispatchPointerMove(targetById.TourismString.key))
local sameKeyTooltipCleared=ZeroSisUi.Snapshot()
assert(sameKeyTooltipCleared~=tooltipSnapshotJson and lastSnapshotValue.topPanelTooltip==nil,
  'same-key TopPanel pointer failed to retain its tooltip-clearing visual change')
assert(ZeroSisUi.DispatchPointerMove(targetById.TourismString.key) and
  ZeroSisUi.Snapshot()==sameKeyTooltipCleared,
  'TopPanel repeated hover did not become a no-op after tooltip clearing')
assert(ZeroSisUi.ToolTip(targetById.TourismString.key)==true)
local restoredTooltip=ZeroSisUi.Snapshot()
assert(lastSnapshotValue.topPanelTooltip~=nil and restoredTooltip~=sameKeyTooltipCleared,
  'TopPanel original tooltip callback did not restore its visual state')
assert(ZeroSisUi.DispatchPointerMove(0)==true)
local leftTooltipSnapshot=ZeroSisUi.Snapshot()
assert(leftTooltipSnapshot~=restoredTooltip,'TopPanel tooltip leave did not change its retained snapshot')
assert(lastSnapshotValue.topPanelTooltip==nil,'tooltip hover state was not cleared on pointer leave')
assert(ZeroSisUi.DispatchPointerMove(0) and ZeroSisUi.Snapshot()==leftTooltipSnapshot,
  'TopPanel repeated tooltip leave changed its retained snapshot at the same owner clock')
assert(ownerClock==hoverClock and #operations==1,
  'TopPanel hover advanced owner time or repeated its science click callback')
local snapshotJson=ZeroSisUi.Snapshot()
local snapshot=assert(lastSnapshotValue)
assert(snapshot.active==true and snapshot.timerSemaphore==0 and snapshot.timerSemaphores==0 and
  snapshot.nonmodal==true and snapshot.popupKind=='TopPanel' and snapshot.contextName=='TopPanel' and
  snapshot.topPanel.activePlayer==0 and snapshot.topPanel.nonmodal==true and
  snapshot.topPanel.timerSemaphores==0,'nonmodal TopPanel metadata contract mismatch')
local refreshVisible=ZeroSisTopPanelRefresh()
assert(type(refreshVisible)=='boolean' and refreshVisible==true,
  'TopPanel refresh must return its actual boolean visible state')
ZeroSisTopPanelStop()
assert(not ZeroSisUi.IsActive() and ContextPtr:IsHidden(),
  'TopPanel Stop must leave the retained context inactive and hidden')
ZeroSisTopPanelStop()
__topPanelComponentReport='{"componentOnly":true,"originalLuaUnmodified":true,'..
  '"originalControlsRetained":true,"scienceRequestDeferred":true,'..
  '"tooltipCallbacksRetained":true,"tooltipCallbackLifecycle":true,'..
  '"tooltipClearedOnPointerLeave":true,"nonmodalSnapshot":true,'..
  '"fixedClockRepeatedHoverUnchanged":true,"fixedClockKeyZeroUnchanged":true,'..
  '"tooltipShowAndLeaveChangeSnapshot":true,"sameKeyTooltipClearChangesSnapshot":true,'..
  '"unsupportedRoutesRemainUnfinished":true,"refreshVisibleBoolean":true,'..
  '"negativeGoldOriginalColorScope":true,'..
  '"originalSizeLessStackMeasured":true,"rightCaptionsAndHitsWithinBar":true,'..
  '"originalZeroCityHideAndRestore":true,'..
  '"stopLeavesContextHidden":true,"retailSdkRendererAndGameVerified":false,'..
  '"consumeMouseCount":'..tostring(consumeMouseCount)..',"inputTargetCount":'..tostring(#targets)..
  ',"tooltipSnapshot":'..tooltipSnapshotJson..',"snapshot":'..snapshotJson..'}'
