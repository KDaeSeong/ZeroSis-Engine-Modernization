-- Component-only contract for the original BNW CommonBehaviors tab helper.
-- The SDK, native policy mutation, renderer, and live game are not exercised.
local SCENE_SOURCE = @@SCENE_SOURCE@@
local INPUT_ADDENDUM = @@INPUT_ADDENDUM@@
local COMMON_BEHAVIORS = @@COMMON_BEHAVIORS@@
local POLICY_LIFECYCLE = @@POLICY_LIFECYCLE@@
-- Read retained coordinates before any public snapshot/target accessor can
-- flush pending layout. This observer is appended only to the component chunk.
local COMPONENT_OBSERVER = [[
__componentRoot=root
__componentRawLayout=function(ids)
  local result={}
  for _,id in ipairs(ids) do
    local row=state(assert(Controls[id],'component control is missing: '..id))
    result[id]={x=row.x,y=row.y,width=row.w,height=row.h,text=row.label,hidden=row.hidden}
  end
  return result
end
__componentCapturedTargets=function() return captureInputTargets(),captureScrollTargets() end
__componentScrollDecorations=function(id)
  local result={}
  for _,child in ipairs(state(assert(Controls[id])).children) do
    local item=state(child)
    if item.kind=='ScrollBar' or item.kind=='UpButton' or item.kind=='DownButton' then
      result[#result+1]={kind=item.kind,hidden=item.hidden}
    end
  end
  return result
end
]]
local reportArrayType={}
local timerBalance,timerAcquisitions,timerReleases=0,0,0
local function componentNative(operation,...)
  if operation=='uiFrameTime' then return 0 end
  if operation=='screenSize' then return 1920,1080 end
  if operation=='randomSeed' then return 17 end
  if operation=='snapshotJson' then return __ZeroSisSnapshotJson(...) end
  if operation=='timer' then
    local delta=(...)
    assert(delta==1 or delta==-1,'invalid native timer delta')
    timerBalance=timerBalance+delta
    assert(timerBalance==0 or timerBalance==1,'unbalanced native modal timer')
    if delta==1 then timerAcquisitions=timerAcquisitions+1 else timerReleases=timerReleases+1 end
    return true
  end
  -- This initialization check measures no localized text or glyph placement.
  if operation=='locale' then return '' end
  error('Unexpected native operation in component fixture: '..tostring(operation))
end
local function initialize(layout,native,withInputAddendum)
  local env=setmetatable({ZeroSisUiLayout=layout,ZeroSisUiNative=native or componentNative,
    Game={Rand=function() return 0 end}},{__index=_G})
  env._G=env
  local chunk=assert(loadstring(SCENE_SOURCE..(withInputAddendum and '\n'..INPUT_ADDENDUM or '')..
    '\n'..COMPONENT_OBSERVER,
    '@UiScene-component.lua'))
  setfenv(chunk,env)
  chunk()
  return env
end

-- Initialize the actual prepared XML tree before using a small behavior fixture.
-- No SocialPolicyPopup.lua, SDK player, policy command or renderer is involved.
local originalLayout=@@ORIGINAL_LAYOUT@@
local original=initialize(originalLayout)
local staticControls=0
local function inspectStatic(node,names)
  staticControls=staticControls+1
  if node.attributes.ID then
    assert(names[node.attributes.ID],'original static control was not initialized: '..node.attributes.ID)
  end
  for _,child in ipairs(node.children) do inspectStatic(child,names) end
end
staticControls=1 -- Context has no control ID; Instance roots are deferred templates.
for _,node in ipairs(originalLayout.children) do
  if node.kind~='Instance' then inspectStatic(node,original.Controls) end
end
assert(staticControls==@@ORIGINAL_STATIC_COUNT@@,'original static control count changed')
local originalWidth,originalHeight=original.Controls.PolicyInfo:GetSizeVal()
assert(originalWidth==32 and originalHeight==32,'original prepared PolicyInfo defaults were lost')
local originalTemplates=0
for _,node in ipairs(originalLayout.children) do
  if node.kind=='Instance' then
    local names={}
    original.ContextPtr:BuildInstance(node.attributes.Name,names)
    for _,child in ipairs(node.children) do inspectStatic(child,names) end
    originalTemplates=originalTemplates+1
  end
end
assert(originalTemplates==3,'original policy template count changed')

-- Preparation appends this exact addendum in the same chunk. Its public target
-- collector must preserve the stock branch-zero payload independently of the
-- snapshot collector; the native hasVoid1 check must not be bypassed.
local function addonNative(operation,...)
  if operation=='timer' then return true end -- isolated component timer only
  return componentNative(operation,...)
end
local function openAddon(env,priority)
  env.ContextPtr:SetShowHideHandler(function(hidden,initial)
    if initial then return end
    if hidden then env.UI.decTurnTimerSemaphore() else env.UI.incTurnTimerSemaphore() end
  end)
  env.UIManager:QueuePopup(env.ContextPtr,priority)
end
local function addonTarget(env,id)
  for _,target in ipairs(env.ZeroSisUi.GetInputTargets(env.Mouse.eLClick)) do
    if target.id==id then return target end
  end
  error('input addendum omitted original callback: '..id)
end
local policyInput=initialize(originalLayout,addonNative,true)
policyInput.Controls.SocialPolicyPane:SetHide(false)
policyInput.Controls.IdeologyPane:SetHide(true)
local branch=policyInput.Controls.BranchButton0
branch:SetHide(false)
branch:SetDisabled(false)
branch:SetVoid1(0)
local branchCalls=0
branch:RegisterCallback(policyInput.Mouse.eLClick,function(first,second)
  assert(first==0 and second==-23,'input addendum changed callback payload')
  branchCalls=branchCalls+1
end)
openAddon(policyInput,policyInput.PopupPriority.SocialPolicy)
local branchTarget=addonTarget(policyInput,'BranchButton0')
assert(branchTarget.key>0 and branchTarget.event=='LeftClick' and
  branchTarget.void1==0 and branchTarget.void2==nil,
  'input addendum lost BranchButton0 zero payload or invented its absent second argument')
branch:SetVoid2(-23)
branchTarget=addonTarget(policyInput,'BranchButton0')
assert(branchTarget.void1==0 and branchTarget.void2==-23 and branchCalls==0,
  'public input target collection changed the two original callback arguments')
assert(policyInput.ZeroSisUi.DispatchLeftClick(branchTarget.key) and branchCalls==1,
  'input addendum failed to dispatch the retained branch callback payload')
policyInput.UIManager:DequeuePopup(policyInput.ContextPtr)
assert(#policyInput.ZeroSisUi.GetInputTargets()==0,'closed policy addendum exposed callback targets')
local rankingInput=initialize({kind='Context',attributes={},popupKind='WhosWinning',children={
  {kind='Button',attributes={ID='RankingButton',Size='100,30'},children={}},
}},addonNative,true)
rankingInput.Controls.RankingButton:SetVoids(0,-23)
rankingInput.Controls.RankingButton:RegisterCallback(rankingInput.Mouse.eLClick,function() end)
openAddon(rankingInput,rankingInput.PopupPriority.WhosWinning)
local rankingTarget=addonTarget(rankingInput,'RankingButton')
assert(rankingTarget.void1==nil and rankingTarget.void2==nil,
  'SocialPolicy input fix changed the existing ranking target schema')
rankingInput.UIManager:DequeuePopup(rankingInput.ContextPtr)

-- Original UpdateDisplay clears these 7 + 4 + 3 retained Label controls even
-- before an ideology is selected. Exercise real prepared labels and metrics.
local setStringLabels=@@SET_STRING_LABEL_IDS@@
local longPolicyLabel=string.rep('Policy tenet ',18)
local clearedPolicyLabels=0
for _,id in ipairs(setStringLabels) do
  local label=assert(original.Controls[id],'original ideology label is missing: '..id)
  label:SetText('')
  local emptyWidth,emptyHeight=label:GetSizeVal()
  label:SetText(longPolicyLabel)
  local filledWidth,filledHeight=label:GetSizeVal()
  assert(filledHeight>emptyHeight,'original wrapped label did not measure its nonempty text: '..id)
  label:SetString('')
  local clearedWidth,clearedHeight=label:GetSizeVal()
  assert(label:GetText()=='' and clearedWidth==emptyWidth and clearedHeight==emptyHeight,
    'SetString did not clear and remeasure the original policy label: '..id)
  label:SetText(longPolicyLabel)
  local restoredWidth,restoredHeight=label:GetSizeVal()
  assert(label:GetText()==longPolicyLabel and restoredWidth==filledWidth and restoredHeight==filledHeight,
    'SetText after SetString did not restore the original measured policy label: '..id)
  label:SetString('')
  clearedPolicyLabels=clearedPolicyLabels+1
end
local rollbackLabel=original.Controls.IdeologyButtonLabel11
rollbackLabel:SetText(longPolicyLabel)
local rollbackWidth,rollbackHeight=rollbackLabel:GetSizeVal()
local invalidText,invalidTextError=pcall(rollbackLabel.SetString,rollbackLabel,string.char(255))
local afterFailureWidth,afterFailureHeight=rollbackLabel:GetSizeVal()
assert(not invalidText and tostring(invalidTextError):find('UI label measurement failed',1,true) and
  rollbackLabel:GetText()==longPolicyLabel and afterFailureWidth==rollbackWidth and afterFailureHeight==rollbackHeight,
  'SetString bypassed the existing measurement failure rollback')
rollbackLabel:SetString('')
local wrongKind,wrongKindError=pcall(original.Controls.IdeologyButton11.SetString,original.Controls.IdeologyButton11,'')
assert(not wrongKind and tostring(wrongKindError):find('SetString requires a SocialPolicy Label control',1,true),
  'SetString was extended to a non-Label policy control')
local foreign=initialize({kind='Context',attributes={},children={
  {kind='Label',attributes={ID='ForeignLabel',String='preserved',Size='40,20'},children={}},
},popupKind='WhosWinning'})
local wrongContext,wrongContextError=pcall(foreign.Controls.ForeignLabel.SetString,foreign.Controls.ForeignLabel,'')
assert(not wrongContext and tostring(wrongContextError):find('SetString requires a SocialPolicy Label control',1,true) and
  foreign.Controls.ForeignLabel:GetText()=='preserved','SetString was extended to another UI context')

-- The original policy Lua attaches these real templates without explicitly
-- calculating ScrollPanel content. Use public scroll metadata/input, not an SDK
-- or full-policy snapshot substitute, to exercise the normal anchor boundary.
local policyScrollPanels=@@POLICY_SCROLL_PANEL_IDS@@
local policyScrollCases={}
for _,id in ipairs(policyScrollPanels) do
  local panel=assert(original.Controls[id])
  local viewportHeight=panel:GetSizeY()
  local policy,pipe={},{}
  original.ContextPtr:BuildInstanceForControl('PolicyButton',policy,panel)
  original.ContextPtr:BuildInstanceForControl('ConnectorPipe',pipe,panel)
  policy.PolicyIcon:SetOffsetVal(16,viewportHeight+40)
  pipe.ConnectorImage:SetOffsetVal(32,viewportHeight+90)
  pipe.ConnectorImage:SetSizeVal(19,180)
  policyScrollCases[id]={panel=panel,policy=policy.PolicyIcon,pipe=pipe.ConnectorImage,
    policyBottom=policy.PolicyIcon:GetOffsetY()+policy.PolicyIcon:GetSizeY(),
    pipeBottom=pipe.ConnectorImage:GetOffsetY()+pipe.ConnectorImage:GetSizeY()}
end
original.Controls.SocialPolicyPane:SetHide(false)
original.Controls.IdeologyPane:SetHide(true)
original.ContextPtr:SetShowHideHandler(function() end)
original.UIManager:QueuePopup(original.ContextPtr,original.PopupPriority.SocialPolicy)
local function scrollTarget(id)
  local selected,count=nil,0
  for _,target in ipairs(original.ZeroSisUi.GetScrollTargets()) do
    count=count+1
    if target.id==id then selected=target end
  end
  assert(count==9,'the original policy surface did not retain all nine visible scroll panels')
  return assert(selected,'original policy scroll target is missing: '..id)
end
local policyRowYDelta=@@POLICY_ROW_Y_DELTA@@
local firstPolicyRowY=scrollTarget('TraditionPanel').bounds.y
local secondPolicyRowY=scrollTarget('RationalismPanel').bounds.y
assert(secondPolicyRowY-firstPolicyRowY==policyRowYDelta,
  'original SocialPolicy nested rows did not reserve the XML-derived first-row extent')
local policyRowsChecked=1
local function assertScrollRange(id,content,offset)
  local target=scrollTarget(id)
  local panel=policyScrollCases[id].panel
  assert(target.orientation=='vertical' and target.contentHeight==content and
    target.viewportHeight==panel:GetSizeY() and target.bounds.width==panel:GetSizeX() and
    target.maximumScroll==math.max(0,content-panel:GetSizeY()) and target.scrollY==offset and
    panel:GetScrollValue()==offset,'original policy child extent or scroll range differs: '..id)
  return target
end
local scrollPanelsChecked=0
local function assertScrollDecorations(id,hidden)
  local decorations=original.__componentScrollDecorations(id)
  assert(#decorations==3,'original policy scroll panel lost its three XML decorations')
  for _,item in ipairs(decorations) do
    assert(item.hidden==hidden,'original automatic scroll decoration visibility differs: '..id..'/'..item.kind)
  end
end
for _,id in ipairs(policyScrollPanels) do
  local case=policyScrollCases[id]
  local initialContent=math.max(case.policyBottom,case.pipeBottom)
  local target=assertScrollRange(id,initialContent,0)
  assertScrollDecorations(id,false)
  assert(original.ZeroSisUi.DispatchScroll(target.key,32768))
  assertScrollRange(id,initialContent,initialContent-case.panel:GetSizeY())
  assert(original.ZeroSisUi.DispatchScroll(target.key,-32768))
  assertScrollRange(id,initialContent,0)
  local added={}
  original.ContextPtr:BuildInstanceForControl('ConnectorPipe',added,case.panel)
  added.ConnectorImage:SetOffsetVal(12,case.panel:GetSizeY()+400)
  added.ConnectorImage:SetSizeVal(19,80)
  local addedContent=added.ConnectorImage:GetOffsetY()+added.ConnectorImage:GetSizeY()
  -- DispatchScroll performs the retained root anchor pass after input.
  assert(original.ZeroSisUi.DispatchScroll(target.key,1))
  assertScrollRange(id,addedContent,1)
  assert(original.ZeroSisUi.DispatchScroll(target.key,32768))
  assertScrollRange(id,addedContent,addedContent-case.panel:GetSizeY())
  added.ConnectorImage:SetHide(true)
  assert(original.ZeroSisUi.DispatchScroll(target.key,1))
  assertScrollRange(id,initialContent,initialContent-case.panel:GetSizeY())
  case.pipe:SetHide(true)
  assert(original.ZeroSisUi.DispatchScroll(target.key,1))
  assertScrollRange(id,case.policyBottom,case.policyBottom-case.panel:GetSizeY())
  case.policy:SetHide(true)
  assert(original.ZeroSisUi.DispatchScroll(target.key,1))
  assertScrollRange(id,0,0)
  assertScrollDecorations(id,true)
  case.policy:SetHide(false)
  assert(original.ZeroSisUi.DispatchScroll(target.key,1))
  assertScrollRange(id,case.policyBottom,0)
  assertScrollDecorations(id,false)
  scrollPanelsChecked=scrollPanelsChecked+1
end
original.UIManager:DequeuePopup(original.ContextPtr)

-- Reuse the original prepared tree with its actual presentation addendum.
-- These handlers exercise text/layout boundaries only, never SDK policy data.
local batchIds={}
for _,id in ipairs(setStringLabels) do batchIds[#batchIds+1]=id end
local batchStatusLabels={'PlayerTitleLabel','NextCost','CurrentCultureLabel',
  'CulturePerTurnLabel','NextPolicyTurnLabel'}
for _,id in ipairs(batchStatusLabels) do batchIds[#batchIds+1]=id end
for _,id in ipairs({'InfoStack','InfoStack2','BranchButton0','PolicyInfo',
  'TabButtonSocialPolicies','TabButtonIdeologies','CloseButton'}) do
  batchIds[#batchIds+1]=id
end
for _,id in ipairs(policyScrollPanels) do
  batchIds[#batchIds+1]=id
  local names,pipe={},{}
  policyInput.ContextPtr:BuildInstanceForControl('PolicyButton',names,policyInput.Controls[id])
  policyInput.ContextPtr:BuildInstanceForControl('ConnectorPipe',pipe,policyInput.Controls[id])
  names.PolicyIcon:SetOffsetVal(16,40)
  pipe.ConnectorImage:SetOffsetVal(32,90)
  pipe.ConnectorImage:SetSizeVal(19,80)
  names.PolicyIcon:SetVoid1(0)
  names.PolicyIcon:RegisterCallback(policyInput.Mouse.eLClick,function() end)
end
-- Reopen the same context with the handler registered by the earlier input case.
policyInput.UIManager:QueuePopup(policyInput.ContextPtr,policyInput.PopupPriority.SocialPolicy)
local function textBatch(expanded)
  for _,id in ipairs(setStringLabels) do
    local label=policyInput.Controls[id]
    label:SetText(longPolicyLabel)
    label:SetString('')
    if expanded then label:SetText(longPolicyLabel) end
  end
  policyInput.Controls.PlayerTitleLabel:SetText(expanded and 'Policy title with a wider measured name' or 'Policy')
  policyInput.Controls.NextCost:SetText(expanded and 'Next cost\nCulture 55' or 'Next cost 25')
  policyInput.Controls.CurrentCultureLabel:SetText(expanded and 'Culture 55' or 'Culture 0')
  policyInput.Controls.CulturePerTurnLabel:SetText(expanded and 'Culture per turn\nRate 2' or 'Rate 1')
  policyInput.Controls.NextPolicyTurnLabel:SetText(expanded and 'Next policy turn 28' or 'Next policy turn 25')
end
local function encodeComponent(value) return __ZeroSisSnapshotJson(value,reportArrayType) end
local function capturedBatchTargets()
  local inputs,scrolls=policyInput.__componentCapturedTargets()
  return encodeComponent({inputs=inputs,scrolls=scrolls})
end
-- Explicit root anchoring supplies both final-state references. Neither the
-- measured event nor measured callback is allowed to use this repair path.
textBatch(true)
policyInput.__componentRoot:ReprocessAnchoring()
local expandedLayout=policyInput.__componentRawLayout(batchIds)
local expandedTargets=capturedBatchTargets()
textBatch(false)
policyInput.__componentRoot:ReprocessAnchoring()
local clearedLayout=policyInput.__componentRawLayout(batchIds)
local clearedTargets=capturedBatchTargets()
assert(expandedLayout.PlayerTitleLabel.x~=clearedLayout.PlayerTitleLabel.x and
  expandedLayout.CurrentCultureLabel.y~=clearedLayout.CurrentCultureLabel.y and
  expandedLayout.IdeologyButtonLabel11.height>clearedLayout.IdeologyButtonLabel11.height,
  'policy text batch did not exercise centered text, stacked text, and original wrapped labels')
assert(expandedTargets==clearedTargets,'policy text batch moved unrelated original input or scroll coordinates')
local instructionLimit,instructionInterval=8000000,1000
local batchInstructions={}
local function measureBatch(name,fn)
  assert(type(debug)=='table' and type(debug.sethook)=='function' and debug.gethook()==nil,
    'component instruction counter must not replace an existing instruction guard')
  local count=0
  debug.sethook(function()
    count=count+instructionInterval
    assert(count<instructionLimit,'policy text batch exhausted the unchanged 8M instruction budget: '..name)
  end,'',instructionInterval)
  local ok,err=pcall(fn)
  debug.sethook()
  assert(ok,err)
  assert(count>0 and count<instructionLimit,'policy text batch instruction observation is invalid')
  batchInstructions[name]=count
end
local batchEvents,batchCallbacks=0,0
policyInput.Events.EventPoliciesDirty.Add(function()
  batchEvents=batchEvents+1
  textBatch(true)
end)
measureBatch('eventPoliciesDirty',function() policyInput.Events.EventPoliciesDirty() end)
assert(batchEvents==1 and encodeComponent(policyInput.__componentRawLayout(batchIds))==encodeComponent(expandedLayout),
  'EventPoliciesDirty returned before the original policy text batch reached its final geometry')
assert(capturedBatchTargets()==expandedTargets,'EventPoliciesDirty changed original callback or scroll coordinates')
branch:RegisterCallback(policyInput.Mouse.eLClick,function(first,second)
  assert(first==0 and second==-23,'policy text batch callback lost its original branch payload')
  batchCallbacks=batchCallbacks+1
  textBatch(false)
end)
local batchTarget=addonTarget(policyInput,'BranchButton0')
measureBatch('inputAddendumCallback',function()
  assert(policyInput.ZeroSisUi.DispatchLeftClick(batchTarget.key),'policy text batch callback was not consumed')
end)
assert(batchCallbacks==1 and batchEvents==1 and
  encodeComponent(policyInput.__componentRawLayout(batchIds))==encodeComponent(clearedLayout),
  'public input addendum returned before the original policy text batch reached its final geometry')
assert(capturedBatchTargets()==clearedTargets,'public input addendum changed original callback or scroll coordinates')
policyInput.UIManager:DequeuePopup(policyInput.ContextPtr)

local coordinateAccepted,coordinateRejected=0,0
local function coordinateLayout(value,popupKind)
  return {kind='Context',attributes={},children={
    {kind='Box',attributes={ID='CoordinateProbe',Size=value,Offset=value},children={}},
  },popupKind=popupKind or 'SocialPolicy',
    contextName=popupKind=='CityView' and 'CityView' or 'SocialPolicyPopup'}
end
local function accepted(value,x,y,popupKind)
  local env=initialize(coordinateLayout(value,popupKind))
  local control=env.Controls.CoordinateProbe
  local width,height=control:GetSizeVal()
  assert(width==x and height==y and control:GetOffsetX()==x and control:GetOffsetY()==y,
    'coordinate changed its existing value: '..tostring(value))
  coordinateAccepted=coordinateAccepted+1
end
local function rejected(value,popupKind)
  local ok,err=pcall(initialize,coordinateLayout(value,popupKind))
  assert(not ok and tostring(err):find('Unsupported UI coordinate:',1,true),
    'invalid coordinate was accepted or failed for an unrelated reason: '..tostring(value))
  coordinateRejected=coordinateRejected+1
end
accepted(nil,0,0)
accepted('190,290 ',190,290)
accepted(' \t190,290\r\n',190,290)
accepted(' -12,-34 ',-12,-34)
accepted(' Full,Full ',1920,1080)
accepted(' Full,-20 ',1920,-20)
accepted(' -30,Full ',-30,1080)
accepted('16.0',16,0)
accepted('0,',0,0,'CityView')
accepted(' \t0,\r\n',0,0,'CityView')
for _,value in ipairs({'',' ','1 90,290','190, 290','190 ,290','Full, Full',
  '1,2,3','nan,2','+1,2','1.5,2','0,',',0','1,,2'}) do rejected(value) end
rejected('1,','CityView')
rejected(',0','CityView')

ZeroSisUiLayout = @@LAYOUT@@
ZeroSisUiNative=componentNative
Game={Rand=function() return 0 end}
ButtonPopupTypes={BUTTONPOPUP_CHOOSEPOLICY=17,BUTTONPOPUP_WHOS_WINNING=101}
assert(loadstring(SCENE_SOURCE))()
local policyInfoWidth,policyInfoHeight=Controls.PolicyInfo:GetSizeVal()
assert(policyInfoWidth==32 and policyInfoHeight==32 and
  ZeroSisUiLayout.controlDefaultSizes.PolicyInfo.texture=='Assets/UI/Art/Controls/Checkbox.dds',
  'generated SocialPolicy controlDefaultSizes did not reach UiScene.PolicyInfo')
assert(Controls.PolicyInfo:IsChecked(),'generated PolicyInfo initial checkbox state was lost')
local policyInfoOption=true
OptionsManager.GetPolicyInfo=function() return policyInfoOption end
Controls.PolicyInfo:RegisterCheckHandler(function(value) policyInfoOption=value end)
assert(Mouse.eLclick=='LeftClick' and Mouse.eLclick==Mouse.eLClick,
  'SocialPolicy did not provide the original CommonBehaviors enum spelling')
assert(loadstring(COMMON_BEHAVIORS))()
local tabs={
  SocialPolicies={Button=Controls.TabButtonSocialPolicies,Panel=Controls.SocialPoliciesPanel,
    SelectHighlight=Controls.TabButtonSocialPoliciesHL},
  Ideologies={Button=Controls.TabButtonIdeologies,Panel=Controls.IdeologiesPanel,
    SelectHighlight=Controls.TabButtonIdeologiesHL},
}
local selected=RegisterTabBehavior(tabs,tabs.SocialPolicies)
assert(g_CurrentTab==tabs.SocialPolicies,'original default tab selection did not run')
g_Tabs=tabs
local dispatches,displayUpdates,shownEvents,processedEvents=0,0,0,0
UpdateDisplay=function() displayUpdates=displayUpdates+1 end -- SDK data population is outside this component.
local submitted
Events.SerialEventGameMessagePopup.Add(function(info)
  assert(info==submitted and info.Type==17,'Submit did not preserve the policy popup event')
  dispatches=dispatches+1
end)
Events.SerialEventGameMessagePopupShown.Add(function(info)
  assert(info==submitted and ZeroSisUi.IsActive() and not ContextPtr:IsHidden() and timerBalance==1,
    'original policy Shown did not retain its active modal timer')
  shownEvents=shownEvents+1
end)
Events.SerialEventGameMessagePopupProcessed.Add(function(kind,result)
  assert(kind==17 and result==0 and ZeroSisUi.IsActive() and timerBalance==0,
    'original policy Processed did not follow its timer release while dequeuing')
  processedEvents=processedEvents+1
end)
assert(loadstring(POLICY_LIFECYCLE,'@OriginalSocialPolicyLifecycle.lua'))()
submitted={Type=17,Data1=-1,Data2=-1,Data3=-1}
ZeroSisUi.Submit(submitted)
assert(dispatches==1 and displayUpdates==1 and shownEvents==1 and processedEvents==0 and
  ZeroSisUi.IsActive() and not ContextPtr:IsHidden() and timerBalance==1,
  'public Submit did not dispatch the original policy popup through its shown state')
local duplicate,duplicateError=pcall(ZeroSisUi.Submit,submitted)
assert(not duplicate and tostring(duplicateError):find('Previous popup is still pending',1,true) and
  dispatches==1 and timerBalance==1,'active policy popup accepted a repeated Submit')
Controls.HoverGatedChild:RegisterCallback(Mouse.eLClick,function() end)
Controls.HoverTrigger:RegisterCallback(Mouse.eLClick,function() end)
local targets={}
for _,target in ipairs(ZeroSisUi.GetInputTargets(Mouse.eLClick)) do targets[target.id]=target end
assert(targets.TabButtonSocialPolicies and targets.TabButtonIdeologies,
  'CommonBehaviors did not register both stock tab buttons as left-click targets')
assert(targets.HoverGatedChild and targets.HoverTrigger,
  'HideOnMouseOver component fixture is missing its initial visible input controls')
assert(targets.PolicyInfo and targets.PolicyInfo.event=='LeftClick',
  'generated PolicyInfo was not retained as a real checkbox input target')
assert(ZeroSisUi.DispatchLeftClick(targets.PolicyInfo.key,'LeftClick')==true and
  not Controls.PolicyInfo:IsChecked(),'generated PolicyInfo checkbox did not toggle through its input callback')
assert(ZeroSisUi.DispatchPointerMove(targets.HoverTrigger.key)==true,
  'pointer move to a SocialPolicy-owned hover region failed')
local hoveredTargets={}
for _,target in ipairs(ZeroSisUi.GetInputTargets(Mouse.eLClick)) do hoveredTargets[target.id]=target end
assert(not hoveredTargets.HoverGatedChild and hoveredTargets.HoverTrigger,
  'HideOnMouseOver did not gate its children while the owning Box was hovered')
assert(ZeroSisUi.DispatchPointerMove(0)==true,'pointer leave did not clear retained hover state')
local clearedTargets={}
for _,target in ipairs(ZeroSisUi.GetInputTargets(Mouse.eLClick)) do clearedTargets[target.id]=target end
assert(clearedTargets.HoverGatedChild,'HideOnMouseOver child remained gated after pointer leave')
assert(ZeroSisUi.DispatchLeftClick(targets.TabButtonIdeologies.key,'LeftClick')==true and
  g_CurrentTab==tabs.Ideologies,'original tab callback did not select Ideologies')
assert(ZeroSisUi.DispatchLeftClick(targets.TabButtonSocialPolicies.key,'LeftClick')==true and
  g_CurrentTab==tabs.SocialPolicies,'original tab callback did not return to SocialPolicies')
assert(Controls.SocialPoliciesPanel:IsHidden()==false and Controls.IdeologiesPanel:IsHidden()==true,
  'original tab helper panel visibility contract did not settle on the selected tab')
assert(targets.CloseButton and ZeroSisUi.DispatchLeftClick(targets.CloseButton.key,'LeftClick')==true,
  'original OnClose callback did not consume its retained close-button input')
assert(not ZeroSisUi.IsActive() and ContextPtr:IsHidden() and timerBalance==0 and processedEvents==1,
  'original close did not finish its modal policy lifecycle')
local wrongTypesRejected=0
for _,kind in ipairs({101,0,17.5}) do
  local ok,err=pcall(ZeroSisUi.Submit,{Type=kind})
  assert(not ok and tostring(err):find('SocialPolicy context supports only the original policy popup',1,true),
    'SocialPolicy Submit accepted a different type or rejected it after event dispatch')
  assert(dispatches==1 and not ZeroSisUi.IsActive() and timerBalance==0,
    'rejected popup type changed the policy lifecycle')
  wrongTypesRejected=wrongTypesRejected+1
end
local other=initialize({kind='Context',attributes={},children={},popupKind='WhosWinning'})
local otherOk,otherError=pcall(other.ZeroSisUi.Submit,{Type=17})
assert(not otherOk and tostring(otherError):find('Unsupported popup type for selected context',1,true),
  'non-policy context accepted the policy popup type')
submitted={Type=17,Data1=1,Data2=-1,Data3=-1}
ZeroSisUi.Submit(submitted)
assert(dispatches==2 and displayUpdates==2 and shownEvents==2 and timerBalance==1,
  'original InGameUtmost reopen did not acquire its modal timer')
OnClose()
OnClose() -- Original close is harmless when already hidden.
assert(not ZeroSisUi.IsActive() and ContextPtr:IsHidden() and timerBalance==0 and
  processedEvents==2 and timerAcquisitions==2 and timerReleases==2,
  'original close/reopen left duplicate completion or an unbalanced modal timer')
local processedTypesRejected=0
for _,wrongKind in ipairs({101,0,17.5}) do
  local probe=initialize({kind='Context',attributes={},children={},popupKind='SocialPolicy',
    contextName='SocialPolicyPopup'},function(operation,...)
      if operation=='timer' then return true end
      return componentNative(operation,...)
    end)
  probe.ContextPtr:SetShowHideHandler(function(hidden,initial)
    if initial then return end
    if hidden then
      probe.UI.decTurnTimerSemaphore()
      probe.Events.SerialEventGameMessagePopupProcessed.CallImmediate(wrongKind,0)
    else
      probe.UI.incTurnTimerSemaphore()
      probe.Events.SerialEventGameMessagePopupShown({Type=17})
    end
  end)
  probe.Events.SerialEventGameMessagePopup.Add(function()
    probe.UIManager:QueuePopup(probe.ContextPtr,probe.PopupPriority.SocialPolicy)
  end)
  probe.ZeroSisUi.Submit({Type=17})
  local ok,err=pcall(function() probe.UIManager:DequeuePopup(probe.ContextPtr) end)
  assert(not ok and tostring(err):find('SocialPolicy processed event outside the original policy popup lifecycle',1,true),
    'SocialPolicy Processed accepted another popup kind after releasing its modal timer')
  processedTypesRejected=processedTypesRejected+1
end
local shownWhileHidden,shownWhileHiddenError=pcall(Events.SerialEventGameMessagePopupShown,{Type=17})
assert(not shownWhileHidden and tostring(shownWhileHiddenError):find('Shown event outside popup lifecycle',1,true),
  'policy Shown event was accepted after the popup closed')
local processedWhileHidden,processedWhileHiddenError=pcall(Events.SerialEventGameMessagePopupProcessed.CallImmediate,17,0)
assert(not processedWhileHidden and tostring(processedWhileHiddenError):find(
  'SocialPolicy processed event outside the original policy popup lifecycle',1,true),
  'policy Processed event was accepted after the popup closed')
__socialPolicyComponentReport=__ZeroSisSnapshotJson({
  componentOnly=true, originalCommonBehaviors=true, originalTabCallbacksRegistered=true,
  socialPolicyPriorityAccepted=true, tabsSwitchedBothWays=true, hideOnMouseOverGate=true,
  policyInfoDefaultsReachedUiScene=true, policyInfoCheckboxInputRetained=true,
  originalPreparedStaticTreeInitialized=true,originalTemplatesInitialized=originalTemplates,
  originalStaticControlCount=@@ORIGINAL_STATIC_COUNT@@,
  inputAddendumAppended=true,inputAddendumBranchZeroPayloadPreserved=true,
  inputAddendumSecondPayloadPreserved=true,inputAddendumRankingPayloadOmitted=true,
  originalSetStringLabelsCleared=clearedPolicyLabels,setStringTextGeometryReused=true,
  setStringMeasurementRollback=true,setStringScopeRejections=2,
  originalPolicyScrollPanelsMeasured=scrollPanelsChecked,policyScrollRangesFromChildExtents=true,
  originalPolicyOmittedAutoScrollBarFollowsContent=true,
  originalPolicyNestedRowsSeparated=policyRowsChecked,
  policyScrollInputClamped=true,policyScrollAddedHiddenChildrenUpdated=true,
  activeOriginalTextBatchLabels=#setStringLabels,activeOriginalTextBatchStatusLabels=#batchStatusLabels,
  textBatchEventBoundaries=batchEvents,textBatchInputAddendumCallbacks=batchCallbacks,
  textBatchFinalGeometryMatchesExplicitAnchor=true,textBatchInputCoordinatesPreserved=true,
  textBatchInstructionLimit=instructionLimit,textBatchInstructionInterval=instructionInterval,
  textBatchInstructions=batchInstructions,
  coordinateAcceptedCases=coordinateAccepted,coordinateRejectedCases=coordinateRejected,
  originalPolicyLifecycleCallbacks=true,publicSubmitEventDispatches=dispatches,
  publicSubmitOtherTypesRejected=wrongTypesRejected,publicSubmitDuplicateRejected=true,
  policySubmitRejectedByOtherContext=true,shownEvents=shownEvents,processedEvents=processedEvents,
  balancedModalTimerCycles=timerAcquisitions,
  policyProcessedOtherTypesRejected=processedTypesRejected,
  closedPolicyLifecycleEventsRejected=true,
  retailSdkRendererAndLiveGameVerified=false,
},reportArrayType)
