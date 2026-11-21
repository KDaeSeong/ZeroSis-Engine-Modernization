-- Optional input-dispatch addendum. Append to UiScene.lua in the same Lua chunk
-- so this layer can validate retained controls and call the official handlers.
-- This does not create a window, hit-test pixels, or synthesize game input.
if hasRetainedExitConfirmUi then
  -- Keep the original modal's guarded callback entry points when installing
  -- this addendum. Generic callback dispatch must not bypass its Yes/No scope.
  exitConfirmState.originalKeyDispatch=assert(ZeroSisUi.DispatchKeyDown)
  exitConfirmState.originalLeftDispatch=assert(ZeroSisUi.DispatchLeftClick)
end
local function validInputInteger(value)
  return type(value)=='number' and value==value and value~=math.huge and
    value~=-math.huge and value>=0 and value<=9007199254740991 and value==math.floor(value)
end

local function inputEnabled()
  if not active or contextHidden or inputContextName~=contextName then return false end
  if hasRetainedPantheonUi then pantheonState.scope();return timer==1 end
  if popupKind=='TopPanel' then return contextName=='TopPanel' and timer==0 end
  if popupKind=='ActionInfoPanel' then return contextName=='ActionInfoPanel' and timer==0 end
  if popupKind=='NotificationPanel' then return contextName=='NotificationPanel' and timer==0 end
  if popupKind=='ResearchTree' then return contextName=='TechTree' and timer==1 end
  if hasRetainedEconomicChildUi then return timer==0 end
  if hasRetainedSaveMenuUi then return contextName=='SaveMenu' and timer==0 end
  if hasRetainedLoadMenuUi then return contextName=='LoadMenu' and timer==0 end
  if hasRetainedExitConfirmUi then return contextName=='ExitConfirm' and timer==0 end
  if popupKind=='MenuOptions' then return contextName=='OptionsMenu_InGame' and timer==0 end
  if popupKind=='TouchHelp' then return contextName=='TouchControlsMenu' and timer==0 end
  if popupKind=='MapMenu' then return contextName=='SaveMapMenu' and timer==0 end
  return timer==1 or ((popupKind=='Production' or popupKind=='Research' or popupKind=='CityCapture' or popupKind=='LeaderHead' or popupKind=='CityView' or popupKind=='UnitPanel') and timer==0)
end

local function isResearchTreeContext()
  return popupKind=='ResearchTree' and contextName=='TechTree'
end

local function flushRetainedInputLayout()
  if isResearchTreeContext() or (popupKind=='SocialPolicy' and contextName=='SocialPolicyPopup') or hasRetainedPantheonUi or goodyHutRewardState.enabled or hasRetainedEconomicUi or hasRetainedActionInfoUi or hasRetainedNotificationUi or hasRetainedGameMenuUi or hasRetainedExitConfirmUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp' or popupKind=='MapMenu' then
    assert(type(ZeroSisUi.FlushLayout)=='function','Retained input layout barrier is unavailable')
    ZeroSisUi.FlushLayout()
  end
end

local function findLiveControl(handle,key,ancestorsVisible)
  local value=states[handle]
  if not value then return nil end
  local visible=ancestorsVisible and not value.hidden
  if value.key==key then
    if visible then return handle,value end
    return nil
  end
  if not visible then return nil end
  for _,child in ipairs(value.children) do
    local found,childValue=findLiveControl(child,key,visible)
    if found then return found,childValue end
  end
  return nil
end

local function isLeftInputTarget(handle,value)
  if not value or inheritedDisabled(handle) then return false end
  if (hasRetainedSaveMenuUi or popupKind=='MapMenu') and value.kind=='EditBox' then
    if value.attributes.ID~='NameBox' or type(value.editCallback)~='function' then return false end
  elseif not buttonKind(value.kind) or type(value.callbacks[Mouse.eLClick])~='function' then return false end
  local left,top,right,bottom=value.x,value.y,value.x+value.w,value.y+value.h
  local parent=value.parent
  while parent do
    local ancestor=states[parent]
    if ancestor and ancestor.kind=='ScrollPanel' and
      not (value.parent==parent and pullDown.isChrome(value,ancestor)) then
      left=math.max(left,ancestor.x);top=math.max(top,ancestor.y)
      right=math.min(right,ancestor.x+ancestor.w);bottom=math.min(bottom,ancestor.y+ancestor.h)
      if right<=left or bottom<=top then return false end
    end
    parent=ancestor and ancestor.parent or nil
  end
  return true
end

local function liveEditBox()
  if not (hasRetainedSaveMenuUi or popupKind=='MapMenu') or not inputEnabled() or not focusedEditBox then return nil end
  local value=states[focusedEditBox]
  if not value or value.kind~='EditBox' or value.attributes.ID~='NameBox' or
    inheritedDisabled(focusedEditBox) or not gameMenuInputAllowed(focusedEditBox) then return nil end
  local handle=findLiveControl(root,value.key,true)
  if handle~=focusedEditBox or type(value.editCallback)~='function' then return nil end
  return value
end

function ZeroSisUi.IsTextInputEnabled()
  return liveEditBox()~=nil
end

function ZeroSisUi.GetTextInputFocusToken()
  return liveEditBox() and editFocusEpoch or 0
end

local function notifyEditBox(value,isEnter)
  if isEnter then
    assert(value.editCallback==OnEditBoxChange,'Save Enter requires the original NameBox callback')
    if hasRetainedSaveMenuUi then ownedSaveOverwrite.beginSave() end
  end
  local ok,err=pcall(value.editCallback,value.void1,value.void2,isEnter)
  if isEnter and hasRetainedSaveMenuUi then ownedSaveOverwrite.endSave(ok) end
  if not ok then error(err,0) end
  if active and hasRetainedSaveMenuUi then controls.SaveButton:SetDisabled(not saveMenuCanSave()) end
  flushRetainedInputLayout()
  return true
end

local function replaceEditBox(value,chars,caret)
  local parts={};for _,item in ipairs(chars) do parts[#parts+1]=item.character end
  setLabelText(value,table.concat(parts));value.caret=caret
  return notifyEditBox(value,false)
end

local function editBoxKey(key)
  local value=liveEditBox();if not value then return false end
  local chars=utf8Characters(value.label);local caret=math.max(0,math.min(#chars,value.caret or #chars))
  if key==Keys.VK_RETURN then
    if hasRetainedSaveMenuUi and not saveMenuCanSave() then return true end
    if popupKind=='MapMenu' and (controls.SaveButton:IsDisabled() or type(ValidateText)~='function' or not ValidateText(value.label)) then return true end
    return notifyEditBox(value,true)
  elseif key==8 then
    if caret==0 then return true end
    table.remove(chars,caret);return replaceEditBox(value,chars,caret-1)
  elseif key==46 then
    if caret==#chars then return true end
    table.remove(chars,caret+1);return replaceEditBox(value,chars,caret)
  elseif key==37 then value.caret=math.max(0,caret-1)
  elseif key==39 then value.caret=math.min(#chars,caret+1)
  elseif key==36 then value.caret=0
  elseif key==35 then value.caret=#chars
  else return false end
  return true
end

function ZeroSisUi.DispatchTextInput(scalar)
  if not validInputInteger(scalar) or scalar<0x20 or scalar>0x10FFFF or
    scalar>=0x7F and scalar<=0x9F or scalar>=0xD800 and scalar<=0xDFFF then return false end
  local value=liveEditBox();if not value then return false end
  local chars=utf8Characters(value.label);local maximum=tonumber(value.attributes.MaxLength)
  if #chars>=maximum then return true end
  -- Unsupported glyphs are rejected before changing the retained name. This
  -- preserves exact source font metrics instead of rendering invented glyphs.
  local _,glyphs=productionFont(value.attributes.Font)
  if not glyphs[scalar] then return false end
  local caret=math.max(0,math.min(#chars,value.caret or #chars))
  table.insert(chars,caret+1,{codepoint=scalar,character=utf8Codepoint(scalar)})
  return replaceEditBox(value,chars,caret+1)
end

function ZeroSisUi.DispatchKeyDown(key,...)
  if not validInputInteger(key) then return false end
  if not inputEnabled() then return false end
  if hasRetainedExitConfirmUi then
    if select('#',...)~=0 then return false end
    return exitConfirmState.originalKeyDispatch(key)
  end
  pullDown.validate()
  if key==Keys.VK_ESCAPE and pullDown.close() then flushRetainedInputLayout();return true end
  if (hasRetainedSaveMenuUi or popupKind=='MapMenu') and key~=Keys.VK_ESCAPE and editBoxKey(key) then return true end
  if key~=Keys.VK_ESCAPE and key~=Keys.VK_RETURN then return false end
  if not inputEnabled() or type(inputHandler)~='function' then return false end
  return inputHandler(KeyEvents.KeyDown,key,0)==true
end

function ZeroSisUi.DispatchLeftClick(controlKey,eventName,...)
  if not validInputInteger(controlKey) then return false end
  if not inputEnabled() then return false end
  if hasRetainedExitConfirmUi then
    if controlKey==0 or select('#',...)~=0 or (eventName~=nil and eventName~=Mouse.eLClick) then return false end
    return exitConfirmState.originalLeftDispatch(controlKey)
  end
  eventName=eventName or Mouse.eLClick
  if eventName~=Mouse.eLClick and eventName~=Mouse.eRClick then return false end
  if isResearchTreeContext() and eventName~=Mouse.eLClick then return false end
  flushRetainedInputLayout()
  local handle,value=findLiveControl(root,controlKey,true)
  if not handle or not value then return false end
  if pullDown.opened and eventName==Mouse.eLClick and handle==root then
    pullDown.close();flushRetainedInputLayout();return true
  end
  if inheritedDisabled(handle) then return false end
  if eventName==Mouse.eLClick and not isLeftInputTarget(handle,value) then return false end
  if pullDown.consumeClick(handle) then flushRetainedInputLayout();return true end
  if not gameMenuInputAllowed(handle) then return false end
  if (hasRetainedSaveMenuUi or popupKind=='MapMenu') and value.kind=='EditBox' then
    if eventName~=Mouse.eLClick or not isLeftInputTarget(handle,value) then return false end
    handle:TakeFocus();return true
  end
  if (hasRetainedSaveMenuUi or popupKind=='MapMenu') and eventName==Mouse.eLClick then setEditFocus(nil) end
  local consumed
  if hasRetainedPantheonUi then
    pantheonState.beginClick(handle)
    local ok,result=pcall(invokeCallback,handle,eventName)
    pantheonState.dispatch=nil
    if not ok then error(result,0) end
    consumed=result
  else consumed=invokeCallback(handle,eventName) end
  flushRetainedInputLayout()
  return consumed
end

function ZeroSisUi.PantheonInputObservation(controlKey)
  assert(hasRetainedPantheonUi,'Pantheon observation requires its original context')
  if not inputEnabled() or pantheonState.submitted or controls.ChooseConfirm:IsHidden() or
    state(controls.Yes).key~=controlKey or not gameMenuInputAllowed(controls.Yes) then return -1 end
  local belief=g_BeliefID
  return type(belief)=='number' and belief>=0 and belief==math.floor(belief) and belief or -1
end

-- Production pointer/wheel input is explicitly enabled by the native window.
-- The host supplies a live row key; empty panel space has no scroll owner.
function ZeroSisUi.DispatchPointerMove(targetKey)
  if not inputEnabled() then return false end
  if targetKey~=0 and not validInputInteger(targetKey) then return false end
  if pullDown.opened and targetKey==state(root).key then
    setHoveredControl(nil,frameTime());flushRetainedInputLayout();return true
  end
  local target=nil
  if targetKey~=0 then
    target=targetKey
    local handle,value=findLiveControl(root,target,true)
    if not handle or not gameMenuInputAllowed(handle) then return false end
    if not isLeftInputTarget(handle,value) then
      if not hasRetainedGameMenuUi and not hasRetainedExitConfirmUi and not hasRetainedSaveMenuUi and not hasRetainedLoadMenuUi and popupKind~='MenuOptions' and popupKind~='TouchHelp' and popupKind~='MapMenu' or not consumesMouse(value) then return false end
      target=nil
    end
  end
  local now=(popupKind=='Production' or popupKind=='Research' or popupKind=='TechAward' or popupKind=='CityCapture' or popupKind=='LeaderHead' or popupKind=='CityView' or popupKind=='TopPanel' or popupKind=='ActionInfoPanel' or popupKind=='NotificationPanel' or isResearchTreeContext() or hasRetainedEconomicUi or hasRetainedGameMenuUi or hasRetainedExitConfirmUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp' or popupKind=='MapMenu') and frameTime() or 0
  setHoveredControl(target,now)
  if popupKind=='TopPanel' then activeTopPanelTooltip=nil end
  return true
end

function ZeroSisUi.DispatchScroll(controlKey,delta)
  if not inputEnabled() or not validInputInteger(controlKey) or type(delta)~='number' or
     delta~=delta or delta==math.huge or delta==-math.huge or delta==0 or math.abs(delta)>32768 then return false end
  local handle,value=findLiveControl(root,controlKey,true)
  if not handle or not value or not gameMenuInputAllowed(handle) then return false end
  local panel=handle
  if value.kind~='ScrollPanel' then
    if not isLeftInputTarget(handle,value) then return false end
    while panel and state(panel).kind~='ScrollPanel' do panel=state(panel).parent end
  end
  if not panel or not gameMenuInputAllowed(panel) then return false end
  local scroll=state(panel)
  local vertical=scroll.attributes.Vertical=='1'
  local horizontal=isResearchTreeContext() and scroll.attributes.Vertical=='0'
  if not vertical and not horizontal then return false end
  local extent=vertical and scroll.contentH or scroll.contentW
  local viewportSize=vertical and scroll.h or scroll.w
  if extent==nil or type(panel.GetScrollValue)~='function' or type(panel.SetScrollValue)~='function' then return false end
  local maximum=math.max(0,extent-viewportSize)
  local current=panel:GetScrollValue()
  if type(current)~='number' or current~=current or current==math.huge or current==-math.huge or
     current<0 or current>maximum then return false end
  panel:SetScrollValue(math.max(0,math.min(maximum,current+delta)))
  return true
end

function ZeroSisUi.DispatchSliderValue(controlKey,amount,...)
  if select('#',...)~=0 or popupKind~='MenuOptions' or not inputEnabled() or
    not validInputInteger(controlKey) or type(amount)~='number' or amount~=amount or
    amount==math.huge or amount==-math.huge or amount<0 or amount>1 then return false end
  flushRetainedInputLayout()
  local handle,value=findLiveControl(root,controlKey,true)
  if not handle or value.kind~='Slider' or value.attributes.ID~='EffectsVolumeSlider' or
    type(value.sliderCallback)~='function' or inheritedDisabled(handle) or not gameMenuInputAllowed(handle) then return false end
  local exposed=false
  for _,target in ipairs(captureInputTargets()) do
    if target.key==controlKey and target.event=='SliderValue' then exposed=true;break end
  end
  if not exposed then return false end
  handle:SetValue(amount)
  value.sliderCallback(amount,value.void1)
  flushRetainedInputLayout()
  return true
end

-- Returns fresh identities for live, visible registered left-click targets.
-- The host still owns pointer hit-testing and must dispatch only after a real
-- button hit. The list contains retained-control keys, never SDK pointers.
function ZeroSisUi.GetInputTargets(requestedEvent)
  assert(requestedEvent==nil or requestedEvent==Mouse.eLClick or requestedEvent==Mouse.eRClick or requestedEvent=='SliderValue',
    'Unsupported input target event filter')
  local result={}
  if not inputEnabled() then return result end
  flushRetainedInputLayout()
  if popupKind=='UnitPanel' or popupKind=='TopPanel' or popupKind=='ActionInfoPanel' or popupKind=='NotificationPanel' or hasRetainedGameMenuUi or hasRetainedExitConfirmUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp' or popupKind=='MapMenu' then
    local captured=captureInputTargets()
    local leftKeys={}
    for _,target in ipairs(captured) do
      if target.event==Mouse.eLClick then leftKeys[target.key]=true end
    end
    for _,target in ipairs(captured) do
      if requestedEvent==nil or target.event==requestedEvent or
        (requestedEvent==Mouse.eLClick and target.event=='ConsumeMouse') then
        if target.event~='ConsumeMouse' or not leftKeys[target.key] then result[#result+1]=target end
      end
    end
    return result
  end
  local function visit(handle,visible)
    local value=states[handle]
    if not value then return end
    visible=visible and not value.hidden
    if not visible then return end
    if buttonKind(value.kind) and (not hasRetainedPantheonUi or gameMenuInputAllowed(handle)) then
      for _,eventName in ipairs({Mouse.eLClick,Mouse.eRClick}) do
        if (not isResearchTreeContext() or eventName==Mouse.eLClick) and
           (requestedEvent==nil or requestedEvent==eventName) and not inheritedDisabled(handle) and type(value.callbacks[eventName])=='function' and
           (eventName~=Mouse.eLClick or isLeftInputTarget(handle,value)) then
          local target={key=value.key,id=value.attributes.ID or '',event=eventName}
          if popupKind=='Production' or popupKind=='Research' or popupKind=='TechAward' or popupKind=='CityCapture' or popupKind=='LeaderHead' or popupKind=='CityView' or popupKind=='TopPanel' or popupKind=='SocialPolicy' or isResearchTreeContext() or hasRetainedEconomicUi then
            target.void1=value.void1
            target.void2=value.void2
          end
          result[#result+1]=target
        end
      end
    end
    for _,child in ipairs(value.children) do visit(child,visible) end
  end
  visit(root,true)
  return result
end

-- Returns the visible vertical ScrollPanel viewport rectangles used by the
-- native wheel hit-test. Unlike row callbacks, an empty point inside a panel
-- still has a stable owner key and can scroll that panel.
function ZeroSisUi.GetScrollTargets()
  local result={}
  if not inputEnabled() then return result end
  flushRetainedInputLayout()
  local function visit(handle,visible)
    local value=states[handle]
    if not value then return end
    visible=visible and not value.hidden
    if not visible then return end
    local vertical=value.attributes.Vertical=='1'
    local horizontal=isResearchTreeContext() and value.attributes.Vertical=='0'
    if value.kind=='ScrollPanel' and (vertical or horizontal) and gameMenuInputAllowed(handle) then
      local left,top,right,bottom=math.max(value.x,0),math.max(value.y,0),
        math.min(value.x+value.w,1920),math.min(value.y+value.h,1080)
      local parent=value.parent
      while parent do
        local ancestor=states[parent]
        if ancestor and ancestor.kind=='ScrollPanel' then
          left=math.max(left,ancestor.x);top=math.max(top,ancestor.y)
          right=math.min(right,ancestor.x+ancestor.w);bottom=math.min(bottom,ancestor.y+ancestor.h)
        end
        parent=ancestor and ancestor.parent or nil
      end
      if right>left and bottom>top then
        local target={key=value.key,id=value.attributes.ID or '',event='Scroll'}
        if horizontal then
          assert(value.contentW~=nil,'Horizontal ScrollPanel content size has not been calculated')
          target.orientation='horizontal';target.scrollX=value.scrollX
          target.maximumScroll=math.max(0,value.contentW-value.w)
        elseif hasRetainedLoadMenuUi then
          assert(value.contentH~=nil,'LoadMenu ScrollPanel content size has not been calculated')
          target.orientation='vertical';target.scrollY=value.scrollY
          target.contentHeight=value.contentH;target.viewportHeight=value.h
          target.maximumScroll=math.max(0,value.contentH-value.h)
        end
        result[#result+1]=target
      end
    end
    for _,child in ipairs(value.children) do visit(child,visible) end
  end
  visit(root,true)
  return result
end
