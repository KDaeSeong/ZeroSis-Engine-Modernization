-- Private Host options adapter over the unchanged installed OptionsMenu XML.
-- Only hash-pinned supported stock function bodies execute; the complete retail
-- script/top-level does not. Missing renderer/network/audio APIs are not stubs.
-- Appended to the retained scene chunk so derived controls use the same owned
-- control tree, input validation, metrics and snapshot transport.
if popupKind=='MenuOptions' or popupKind=='TouchHelp' then
  local isOptions=popupKind=='MenuOptions'
  assert(contextName==(isOptions and 'OptionsMenu_InGame' or 'TouchControlsMenu'),
    'Private menu child context identity mismatch')
  local provenance=assert(layout.menuOptions,'Private menu source provenance is missing')
  assert(provenance.profile==(isOptions and 'HOST_SUPPORTED_OPTIONS_SUBSET_V1' or 'ORIGINAL_TOUCH_HELP_V1'),
    'Private menu context profile mismatch')
  local menuState={open=false,pending=false,error='',page='game'}

  local function callBoolean(operation,...)
    local result=native(operation,...)
    assert(type(result)=='boolean',operation..' must return a boolean')
    return result
  end
  local function get(key,cached)
    local value=native('menuOptionsGet',key,cached)
    assert(type(value)=='number' and value==math.floor(value),
      'Private menu option readback must be an integer')
    return value
  end
  local function newLabel(parent,id,label,y,width)
    return make({kind='Label',attributes={ID=id,Anchor='C,T',Offset='0,'..y,
      Size=(width or 800)..',60',WrapWidth=tostring(width or 800),Font='TwCenMT18',
      String=label,ZeroSisDerivedMenuControl='HOST_MENU_ADAPTER_V1'},children={}},parent,controls)
  end
  local function newButton(parent,id,label,x,y)
    return make({kind='GridButton',attributes={ID=id,Anchor='C,T',Offset=x..','..y,
      Size='160,32',Style='SmallButton',ZeroSisDerivedMenuControl='HOST_MENU_ADAPTER_V1'},children={{kind='Label',attributes={
        Anchor='C,C',Font='TwCenMT18',String=label,ZeroSisDerivedMenuControl='HOST_MENU_ADAPTER_V1'},children={}}}},parent,controls)
  end
  local function setButtonText(handle,value)
    local found=false
    for _,child in ipairs(state(handle).children) do
      if state(child).kind=='Label' then child:SetText(value);found=true;break end
    end
    assert(found,'Private menu button has no original label child')
  end

  if not isOptions then
    -- The stock script checks WM_KEYDOWN rather than the other menus' KeyDown.
    KeyEvents.WM_KEYDOWN=KeyEvents.KeyDown
    context:SetShowHideHandler(function(hidden,initial)
      if hidden and not initial then menuState.open=false end
    end)
    local touchStatus
    local function statusText(value)
      if not touchStatus then
        local parent=assert(state(controls.CloseButton).parent)
        touchStatus=newLabel(parent,'ZeroSisTouchStatus','',-36,650)
      end
      touchStatus:SetText(value)
    end
    OptionsManager.GetHideTouchHelp=function()
      return callBoolean('touchHelpGet')
    end
    OptionsManager.SetHideTouchHelp_Cached=function(value)
      assert(menuState.open and active and not contextHidden and type(value)=='boolean',
        'Touch preference edit requires its visible original context')
      native('touchHelpCache',value)
    end
    OptionsManager.CommitGameOptions=function()
      assert(menuState.open and active and not contextHidden,
        'Touch preference commit requires its visible original context')
      local ok,message=native('touchHelpCommit')
      assert(type(ok)=='boolean' and type(message)=='string','Touch preference commit reply is invalid')
      menuState.error=message
      if not ok then
        controls.DontShowAgainCheckbox:SetCheck(not OptionsManager.GetHideTouchHelp())
        statusText('설정을 저장하지 못했습니다. 다시 선택해 주십시오.')
      else statusText('') end
      return ok
    end
    ZeroSisUi.OpenTouchHelp=function()
      assert(not menuState.open and not active and contextHidden and timer==0,
        'Touch help open requires its unused timer-free child context')
      menuState.open=true
      controls.DontShowAgainCheckbox:SetCheck(not OptionsManager.GetHideTouchHelp())
      context:SetHide(false)
      assert(active and timer==0,'Touch help did not enter without acquiring the parent timer')
    end
    ZeroSisUi.CloseTouchHelp=function()
      if active then context:SetHide(true) end
      menuState.open=false
      assert(not active and timer==0,'Touch help retained its modal state')
    end
  else
    local supported={}
    for _,key in ipairs({'noBasicHelp','noRewardPopups','uiCueVolumePercent','windowWidth','windowHeight','fullscreen','vsync','policyInfo'}) do
      supported[key]=callBoolean('menuOptionsCapability',key)
    end
    menuState.supported=supported
    local gameSupported=supported.noBasicHelp or supported.noRewardPopups
    assert(supported.windowWidth==supported.windowHeight,'Window dimensions must share one actual backend')
    local originalDefinition=assert(provenance.originalSupportedHandlers,'Original options supported callbacks are missing')
    assert(originalDefinition.profile=='EXACT_ORIGINAL_OPTIONS_HANDLERS_V1' and
      originalDefinition.completeOriginalScriptExecuted==false,'Original options callback execution scope changed')
    local originalEnvironment={Controls=controls,OptionsManager=OptionsManager,math=math,
      Locale=setmetatable({ToPercent=function(value) return math.floor(value*100+0.5)..'%' end},{__index=Locale}),
      m_PanelNames={'게임 옵션','인터페이스 옵션','화면 옵션','소리 옵션','멀티플레이 옵션'},m_WindowResList={}}
    local originalNames={OnCategory=true,OnNoBasicHelpCheckbox=true,OnNoRewardPopupsCheckbox=true,OnPolicyInfo=true,OnFullscreen=true,
      OnVSync=true,OnUIVolumeSliderValueChanged=true,OnWResolutionPull=true}
    menuState.originalInvocations={}
    for _,definition in ipairs(originalDefinition.functions) do
      assert(originalNames[definition.name] and type(definition.source)=='string' and
        not originalEnvironment[definition.name],'Unsupported or duplicate original options callback')
      local fn=assert(loadstring(definition.source,'@original-OptionsMenu.lua:'..definition.firstLine..':'..definition.name))
      setfenv(fn,originalEnvironment);fn()
      assert(type(originalEnvironment[definition.name])=='function','Original options callback did not load')
    end
    for name in pairs(originalNames) do assert(type(originalEnvironment[name])=='function','Original options callback omitted: '..name) end
    local function original(name,...)
      menuState.originalInvocations[name]=(menuState.originalInvocations[name] or 0)+1
      return originalEnvironment[name](...)
    end
    local function set(key,value)
      assert(menuState.open and not menuState.pending,'Original option edit requires its editable child context')
      native('menuOptionsSet',key,value)
    end
    for _,binding in ipairs({{'IsNoBasicHelp','noBasicHelp','SetNoBasicHelp_Cached'},
      {'IsNoRewardPopups','noRewardPopups','SetNoRewardPopups_Cached'},
      {'GetFullscreen','fullscreen','SetFullscreen_Cached'},{'GetVSync','vsync','SetVSync_Cached'},
      {'GetPolicyInfo','policyInfo','SetPolicyInfo_Cached'}}) do
      local getter,key,setter=binding[1],binding[2],binding[3]
      OptionsManager[getter]=function() return get(key,false)~=0 end
      OptionsManager[getter..'_Cached']=function() return get(key,true)~=0 end
      OptionsManager[setter]=function(value)
        assert(type(value)=='boolean','Original option setter requires a boolean')
        set(key,value and 1 or 0)
      end
    end
    OptionsManager.GetWindowResolution=function() return get('windowWidth',false),get('windowHeight',false) end
    OptionsManager.GetWindowResolution_Cached=function() return get('windowWidth',true),get('windowHeight',true) end
    OptionsManager.SetWindowResolution_Cached=function(width,height)
      assert(type(width)=='number' and width==math.floor(width) and type(height)=='number' and height==math.floor(height),
        'Original window dimensions require integers')
      set('windowWidth',width);set('windowHeight',height)
    end
    originalEnvironment.SetVolumeKnobValue=function(knob,amount)
      assert(knob==1 and type(amount)=='number' and amount==amount and amount>=0 and amount<=1,
        'Only the actual owned UI effects volume knob is supported')
      set('uiCueVolumePercent',math.floor(amount*100+0.5))
    end
    -- Retain every original node but hide unsupported subtrees before input
    -- registration. Anonymous labels/containers are pruned with their option,
    -- so a hidden renderer/network feature leaves no misleading live caption.
    local function prune(handle,keep)
      local value=state(handle);local retained=keep[value.attributes.ID or '']==true
      local childRetained=false
      for _,child in ipairs(value.children) do
        if prune(child,retained and setmetatable({},{__index=function() return true end}) or keep) then childRetained=true end
      end
      if not retained and not childRetained then handle:SetHide(true) end
      return retained or childRetained
    end
    prune(controls.GamePanel,{NoBasicHelpCheckbox=supported.noBasicHelp,NoRewardPopupsCheckbox=supported.noRewardPopups})
    prune(controls.VideoPanel,{ApplyResButton=supported.windowWidth,WResolutionPull=supported.windowWidth,
      FullscreenCheck=supported.fullscreen,VSyncCheck=supported.vsync})
    prune(controls.IFacePanel,{PolicyInfo=supported.policyInfo})
    local originalSlider=supported.uiCueVolumePercent and type(controls.EffectsVolumeSlider.RegisterSliderCallback)=='function'
    menuState.originalEffectsSlider=originalSlider
    prune(controls.AudioPanel,{EffectsVolumeSlider=originalSlider,EffectsVolumeSliderValue=originalSlider})
    controls.IFacePanel:SetHide(true);controls.MultiplayerPanel:SetHide(true)
    controls.IFaceButton:SetHide(not supported.policyInfo);controls.MultiplayerButton:SetHide(true)
    controls.IFaceHighlight:SetHide(true);controls.MultiplayerHighlight:SetHide(true)
    for _,id in ipairs({'GraphicsChangedPopup','Countdown','CountdownPopup','ResolutionConfirmPopup'}) do
      if controls[id] then controls[id]:SetHide(true) end
    end
    -- These source popups would otherwise render without their retail handlers.
    for _,handle in pairs(controls) do
      local id=state(handle).attributes.ID or ''
      if id:find('Popup',1,true) and not (id=='NoRewardPopupsCheckbox' and
          state(handle).kind=='CheckBox' and supported.noRewardPopups) then handle:SetHide(true) end
    end
    local status=newLabel(state(controls.GamePanel).parent,'ZeroSisOptionsStatus','',522,820)
    local audioLabel=newLabel(controls.AudioPanel,'ZeroSisCueVolumeLabel','',130,650)
    local quiet=newButton(controls.AudioPanel,'ZeroSisCueQuieter','-',-100,230)
    local louder=newButton(controls.AudioPanel,'ZeroSisCueLouder','+',100,230)
    local audioScope=newLabel(controls.AudioPanel,'ZeroSisCueScope',
      '도시 구매·신앙 구매·타일 구매·사회 정책의 UI 효과음에 적용됩니다.',300,760)
    if originalSlider then quiet:SetHide(true);louder:SetHide(true);audioLabel:SetHide(true) end
    if not supported.uiCueVolumePercent then
      audioLabel:SetHide(true);quiet:SetHide(true);louder:SetHide(true);audioScope:SetHide(true)
    end
    local resolutions={{1024,768},{1280,720},{1280,800},{1366,768},{1600,900},{1920,1080}}
    for index,res in ipairs(resolutions) do originalEnvironment.m_WindowResList[index]={x=res[1],y=res[2]} end
    if supported.windowWidth then
      controls.WResolutionPull:ClearEntries()
      controls.WResolutionPull:RegisterSelectionCallback(function(index)
        assert(type(index)=='number' and index==math.floor(index) and originalEnvironment.m_WindowResList[index],
          'Original resolution selection is outside the owned list')
        original('OnWResolutionPull',index)
        setButtonText(controls.ApplyResButton,get('windowWidth',true)..' x '..get('windowHeight',true)..'  >')
      end)
      for index,res in ipairs(resolutions) do
        local names={};controls.WResolutionPull:BuildEntry('InstanceOne',names)
        names.Button:SetText(res[1]..'x'..res[2]);names.Button:SetVoid1(index)
      end
      controls.WResolutionPull:CalculateInternals()
    end
    controls.MusicVolumeSlider:SetVoid1(0);controls.EffectsVolumeSlider:SetVoid1(1)
    controls.SpeechVolumeSlider:SetVoid1(2);controls.AmbienceVolumeSlider:SetVoid1(3)
    if originalSlider then controls.EffectsVolumeSlider:RegisterSliderCallback(function(amount,knob)
      original('OnUIVolumeSliderValueChanged',amount,knob)
      controls.EffectsVolumeSlider:SetValue(get('uiCueVolumePercent',true)/100)
    end) end
    local function refresh()
      if supported.noBasicHelp then controls.NoBasicHelpCheckbox:SetCheck(OptionsManager.IsNoBasicHelp_Cached()) end
      if supported.noRewardPopups then controls.NoRewardPopupsCheckbox:SetCheck(OptionsManager.IsNoRewardPopups_Cached()) end
      if supported.fullscreen then controls.FullscreenCheck:SetCheck(OptionsManager.GetFullscreen_Cached()) end
      if supported.vsync then controls.VSyncCheck:SetCheck(OptionsManager.GetVSync_Cached()) end
      if supported.policyInfo then controls.PolicyInfo:SetCheck(OptionsManager.GetPolicyInfo_Cached()) end
      if supported.windowWidth then
        setButtonText(controls.ApplyResButton,get('windowWidth',true)..' x '..get('windowHeight',true)..'  >')
        controls.ApplyResButton:SetToolTipString('클릭하여 창 해상도를 바꿉니다. 저장을 눌러 적용합니다.')
        controls.WResolutionPull:SetHide(false)
        controls.WResolutionPull:GetButton():SetText(get('windowWidth',true)..'x'..get('windowHeight',true))
        controls.FSResolutionPull:SetHide(true)
      end
      if supported.uiCueVolumePercent then audioLabel:SetText('UI 효과음 음량: '..get('uiCueVolumePercent',true)..'%') end
      if originalSlider then
        controls.EffectsVolumeSlider:SetValue(get('uiCueVolumePercent',true)/100)
        controls.EffectsVolumeSliderValue:SetText('UI 효과음 음량: '..get('uiCueVolumePercent',true)..'%')
      end
      controls.AcceptButton:SetDisabled(menuState.pending)
      controls.CancelButton:SetDisabled(menuState.pending)
      controls.DefaultButton:SetDisabled(menuState.pending)
      layoutDirty=true;flushLayout()
    end
    local function choosePage(page)
      menuState.page=page
      original('OnCategory',page=='game' and 1 or page=='interface' and 2 or page=='video' and 3 or 4)
      layoutDirty=true;flushLayout()
    end
    controls.GameButton:SetHide(not gameSupported)
    controls.VideoButton:SetHide(not (supported.windowWidth or supported.fullscreen or supported.vsync))
    controls.AudioButton:SetHide(not supported.uiCueVolumePercent)
    controls.GameButton:RegisterCallback(Mouse.eLClick,function() choosePage('game') end)
    controls.VideoButton:RegisterCallback(Mouse.eLClick,function() choosePage('video') end)
    controls.AudioButton:RegisterCallback(Mouse.eLClick,function() choosePage('audio') end)
    controls.IFaceButton:RegisterCallback(Mouse.eLClick,function() choosePage('interface') end)
    for _,entry in ipairs({{'NoBasicHelpCheckbox','noBasicHelp','OnNoBasicHelpCheckbox'},
      {'NoRewardPopupsCheckbox','noRewardPopups','OnNoRewardPopupsCheckbox'},
      {'FullscreenCheck','fullscreen','OnFullscreen'},{'VSyncCheck','vsync','OnVSync'},{'PolicyInfo','policyInfo','OnPolicyInfo'}}) do
      local id,key,callback=entry[1],entry[2],entry[3]
      if supported[key] then controls[id]:RegisterCheckHandler(function(value)
        original(callback,value)
        if key=='fullscreen' then controls.FSResolutionPull:SetHide(true);controls.WResolutionPull:SetHide(not supported.windowWidth) end
      end) end
    end
    if supported.windowWidth then controls.ApplyResButton:RegisterCallback(Mouse.eLClick,function()
      local width,height=get('windowWidth',true),get('windowHeight',true);local nextIndex=1
      for index,res in ipairs(resolutions) do if res[1]==width and res[2]==height then nextIndex=index%#resolutions+1;break end end
      original('OnWResolutionPull',nextIndex);refresh()
    end) end
    local function changeVolume(delta)
      assert(menuState.open and not menuState.pending,'Volume edit requires the editable child context')
      native('menuOptionsSet','uiCueVolumePercent',math.max(0,math.min(100,get('uiCueVolumePercent',true)+delta)))
      refresh()
    end
    quiet:RegisterCallback(Mouse.eLClick,function() changeVolume(-10) end)
    louder:RegisterCallback(Mouse.eLClick,function() changeVolume(10) end)
    local function cancel()
      if menuState.pending then return false end
      if menuState.open then native('menuOptionsCancel');menuState.open=false end
      context:SetHide(true);return true
    end
    controls.CancelButton:RegisterCallback(Mouse.eLClick,cancel)
    controls.DefaultButton:RegisterCallback(Mouse.eLClick,function()
      assert(menuState.open and not menuState.pending,'Defaults require the editable child context')
      native('menuOptionsDefaults');refresh()
    end)
    controls.AcceptButton:RegisterCallback(Mouse.eLClick,function()
      assert(menuState.open and not menuState.pending,'Apply requires the editable child context')
      local ok,message=native('menuOptionsApply')
      assert(type(ok)=='boolean' and type(message)=='string','Menu apply reply is invalid')
      menuState.error=message
      if ok then menuState.open=false;context:SetHide(true)
      else status:SetText('설정을 적용하지 못했습니다. 다시 확인해 주십시오.');refresh() end
    end)
    context:SetInputHandler(function(message,key)
      if message==KeyEvents.KeyDown and key==Keys.VK_ESCAPE then return cancel() end
      return false
    end)
    ZeroSisUi.OpenMenuOptions=function()
      assert(not menuState.open and not active and contextHidden and timer==0,
        'Menu options open requires an inactive owned child context')
      native('menuOptionsBegin');menuState.open=true;menuState.error='';status:SetText('')
      refresh();choosePage(gameSupported and 'game' or supported.policyInfo and 'interface' or
        (supported.windowWidth or supported.fullscreen or supported.vsync) and 'video' or 'audio')
      context:SetHide(false)
      assert(active and timer==0,'Menu options acquired its parent timer')
    end
    ZeroSisUi.CloseMenuOptions=function()
      assert(cancel() and not active and timer==0,'Menu options could not cancel its owned edits')
    end
  end
  ZeroSisUi.MenuOptionsMetadata=function()
    local derived=array()
    for _,value in pairs(states) do
      if value.sourceAttributes.ZeroSisDerivedMenuControl=='HOST_MENU_ADAPTER_V1' then
        derived[#derived+1]={key=value.key,id=value.attributes.ID or '',kind=value.kind,
          parentKey=value.parent and state(value.parent).key or 0,
          sourceAttributes=value.sourceAttributes}
      end
    end
    table.sort(derived,function(a,b) return a.key<b.key end)
    return {profile=provenance.profile,open=menuState.open and active,
      timerSemaphore=timer,retailSettingsWritten=false,retailOptionsLuaExecuted=false,
      owner=Game.GetActivePlayer(),turn=Game.GetGameTurn(),parentContext='GameMenu',
      supportedCapabilities=menuState.supported or {hideTouchHelp=true},derivedControls=derived,
      derivedControlPolicy='HOST_MENU_ADAPTER_V1',
      originalSupportedHandlersExecuted=isOptions,originalHandlerInvocations=menuState.originalInvocations or {},
      originalEffectsSlider=menuState.originalEffectsSlider or false,
      lastError=menuState.error,page=menuState.page,source=provenance}
  end
end
