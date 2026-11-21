-- Retained control state for an explicitly selected in-game UI context.
-- Rendering, style expansion and font measurement are separate unsupported
-- boundaries. Unsupported methods fail instead of acting as successful no-ops.
local native = assert(ZeroSisUiNative)
local layout = assert(ZeroSisUiLayout)
local states, controls, templates = {}, {}, {}
local sequence, active, timer = 0, false, 0
local showHide, inputHandler
local contextHidden, inputContextName = true, nil
local popupKind = layout.popupKind or 'WhosWinning'
local contextName = layout.contextName or 'main'
local hasRetainedTechUi = popupKind=='Research'
local hasRetainedTechAwardUi = popupKind=='TechAward'
local goodyHutRewardState={enabled=popupKind=='GoodyHutReward',shown=false,processed=false}
if goodyHutRewardState.enabled then
  assert(contextName=='GoodyHutPopup','Goody-hut reward context identity mismatch')
end
local hasRetainedTreeUi = popupKind=='ResearchTree'
local hasRetainedCaptureUi = popupKind=='CityCapture'
local hasRetainedLeaderUi = popupKind=='LeaderHead'
local hasRetainedCityUi = popupKind=='CityView'
local hasRetainedUnitUi = popupKind=='UnitPanel'
local hasRetainedDeclareWarUi = popupKind=='DeclareWar'
local hasRetainedTopPanelUi = popupKind=='TopPanel'
local hasRetainedActionInfoUi = popupKind=='ActionInfoPanel'
local hasRetainedNotificationUi = popupKind=='NotificationPanel'
local hasRetainedGameMenuUi = popupKind=='GameMenu'
local hasRetainedExitConfirmUi = popupKind=='ExitConfirm'
local exitConfirmState={opened=false,opening=false,closed=false,submitted=false,dispatch=nil}
if hasRetainedExitConfirmUi then
  assert(contextName=='ExitConfirm','ExitConfirm context identity mismatch')
end
local hasRetainedSaveMenuUi = popupKind=='SaveMenu'
local hasRetainedLoadMenuUi = popupKind=='LoadMenu'
local hasRetainedPantheonUi = popupKind=='Pantheon'
local pantheonState={enabled=hasRetainedPantheonUi,owner=-1,turn=-1,generation=-1,submitted=false,unitPanelHidden=false}
function pantheonState.scope()
  local owner,turn,generation,applied=native('pantheonContext')
  assert(owner==pantheonState.owner and turn==pantheonState.turn and generation==pantheonState.generation and
    owner==Game.GetActivePlayer() and turn==Game.GetGameTurn() and
    type(applied)=='number' and applied>=0 and applied<=1 and applied==math.floor(applied),
    'Pantheon input lost its captured owner, turn or generation')
  return applied
end
function pantheonState.beginClick(handle)
  pantheonState.scope();pantheonState.dispatch=nil
  if handle==controls.Yes and not controls.ChooseConfirm:IsHidden() and not pantheonState.submitted then
    assert(type(g_BeliefID)=='number' and g_BeliefID>=0 and g_BeliefID==math.floor(g_BeliefID),
      'Pantheon confirmation has no selected original belief')
    pantheonState.dispatch={owner=pantheonState.owner,turn=pantheonState.turn,generation=pantheonState.generation,belief=g_BeliefID}
  end
end
function pantheonState.metadata()
  local provenance=assert(layout.pantheon,'Pantheon source provenance is required')
  local metadata={};for key,value in pairs(provenance) do metadata[key]=value end
  local owner,turn,generation,applied=native('pantheonContext')
  metadata.owner=owner;metadata.turn=turn;metadata.generation=generation
  metadata.selectedMode=1;metadata.selectedBelief=g_BeliefID or -1
  metadata.confirmationVisible=not controls.ChooseConfirm:IsHidden()
  metadata.commandsApplied=applied;metadata.timerSemaphore=timer
  metadata.hudUnitPanelHidden=pantheonState.unitPanelHidden;metadata.hudInfoCornerPresent=false
  return metadata
end
local hasRetainedTradeRouteUi = popupKind=='TradeRoute'
local hasRetainedSocialPolicyUi = popupKind=='SocialPolicy'
local hasRetainedEconomicParentUi = popupKind=='EconomicOverview'
local hasRetainedEconomicGeneralUi = popupKind=='EconomicGeneral'
local hasRetainedEconomicHappinessUi = popupKind=='EconomicHappiness'
local hasRetainedEconomicChildUi = hasRetainedEconomicGeneralUi or hasRetainedEconomicHappinessUi
local hasRetainedEconomicUi = hasRetainedEconomicParentUi or hasRetainedEconomicChildUi
local hasRetainedPopupUi = popupKind=='Production' or hasRetainedTechUi or hasRetainedTechAwardUi or hasRetainedTreeUi or hasRetainedCaptureUi or hasRetainedLeaderUi or hasRetainedCityUi or hasRetainedUnitUi or hasRetainedDeclareWarUi or hasRetainedTopPanelUi or hasRetainedActionInfoUi or hasRetainedNotificationUi or hasRetainedTradeRouteUi or hasRetainedSocialPolicyUi or hasRetainedEconomicUi or hasRetainedGameMenuUi or hasRetainedExitConfirmUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or hasRetainedPantheonUi or goodyHutRewardState.enabled or popupKind=='MenuOptions' or popupKind=='TouchHelp' or popupKind=='MapMenu'
local economicDynamicStacks = hasRetainedEconomicGeneralUi and
  {MainStack=true,CityStack=true,TradeStack=true,BuildingsStack=true} or
  hasRetainedEconomicHappinessUi and {LuxuryHappinessStack=true,CityBuildingStack=true,
    TradeRouteStack=true,LocalCityStack=true,CityUnhappinessStack=true,ResourcesAvailableStack=true,
    ResourcesImportedStack=true,ResourcesExportedStack=true,ResourcesLocalStack=true} or {}
if hasRetainedEconomicUi then
  assert(contextName==(hasRetainedEconomicParentUi and 'EconomicOverview' or
    hasRetainedEconomicGeneralUi and 'EconomicGeneralInfo' or 'HappinessInfo'),
    'Economic context identity mismatch')
end
if hasRetainedTradeRouteUi then
  assert(contextName=='TradeRoute','TradeRoute context identity mismatch')
end
if hasRetainedTopPanelUi then
  assert(contextName=='TopPanel','TopPanel context identity mismatch')
  active=true;contextHidden=false;inputContextName=contextName
end
if hasRetainedActionInfoUi then
  assert(contextName=='ActionInfoPanel','ActionInfoPanel context identity mismatch')
  active=true;contextHidden=false;inputContextName=contextName
end
if hasRetainedSocialPolicyUi then
  assert(contextName=='SocialPolicyPopup','SocialPolicy context identity mismatch')
end
if hasRetainedNotificationUi then
  assert(contextName=='NotificationPanel','NotificationPanel context identity mismatch')
  active=true;contextHidden=false;inputContextName=contextName
end
if hasRetainedGameMenuUi then
  assert(contextName=='GameMenu','GameMenu context identity mismatch')
end
if hasRetainedSaveMenuUi then
  assert(contextName=='SaveMenu','SaveMenu context identity mismatch')
end
if hasRetainedLoadMenuUi then
  assert(contextName=='LoadMenu','LoadMenu context identity mismatch')
end
local captureCityOverlay=false
local arrayType = {}
local function array() return setmetatable({},arrayType) end
local lifecycle, draws = array(), array()
local methods, context = {}, {}
local root, anchor, measureScrollContent
local updateCallback
local layoutDirty=false
local lastPopupType, researchProcessedPending, lastLeaderMessage
local viewport = {w=1920, h=1080}
local lastFrameTime
local notificationLayoutClock
local topPanelStopped=false
local topPanelCallbackDepth=0
local pendingTopPanelPopup
local topPanelTooltipRoots={}
local activeTopPanelTooltip
local topPanelGameMenuToken={}
local gameMenuUnavailable,gameMenuExitCursor
local gameMenuUnavailableAction,clearGameMenuNotice
local gameMenuRawMapScript,gameMenuDatabaseMapScript
local focusedEditBox,saveMenuCurrent
local pullDown={owners={},opened=nil,
  geometryPolicy='ZEROSIS_ORIGINAL_GENERIC_PULL_DOWN_COMPOSITE_CANDIDATE_V1'}
local editFocusEpoch=0
local function setEditFocus(handle)
  if handle~=focusedEditBox or handle~=nil then
    assert(editFocusEpoch<9007199254740991,'Edit focus epoch exhausted')
    editFocusEpoch=editFocusEpoch+1
  end
  focusedEditBox=handle
end
local saveMenuCanSave,saveMenuCanCreate,loadMenuCanLoad
local ownedSaveDelete={supported=false}
local ownedSaveOverwrite={supported=false,listed={},epoch=0}
local gameMenuChildren={LoadMenu='LoadMenu',SaveMenu='SaveMenu',SaveMapMenu='SaveMapMenu',
  OptionsMenu_InGame='OptionsMenu',TouchControlsMenu='TouchControlsMenu'}

local function finite(n)
  assert(type(n)=='number' and n==n and n~=math.huge and n~=-math.huge, 'UI value must be finite')
  return n
end
local function frameTime()
  local now=finite(native('uiFrameTime'))
  assert(now>=0 and (lastFrameTime==nil or now>=lastFrameTime), 'uiFrameTime must be nonnegative and monotonic')
  lastFrameTime=now
  return now
end
local function clamp(value,low,high)
  return math.max(low,math.min(high,value))
end
local function text(s)
  assert(type(s)=='string', 'UI text must be a string')
  return s
end
function ownedSaveDelete.selectedPath()
  local path
  if hasRetainedSaveMenuUi then
    if type(g_SelectedEntry)~='table' or g_SelectedEntry.IsCloudSave or type(g_SavedGames)~='table' then return nil end
    local listed=false
    for _,entry in ipairs(g_SavedGames) do if entry==g_SelectedEntry then listed=true;break end end
    if not listed then return nil end
    path=g_SelectedEntry.FileName
  elseif hasRetainedLoadMenuUi then
    if g_ShowCloudSaves or g_ShowAutoSaves or type(g_FileList)~='table' or
      type(g_iSelected)~='number' or g_iSelected~=math.floor(g_iSelected) then return nil end
    path=g_FileList[g_iSelected]
  end
  if type(path)~='string' or path=='' or path:find('%z') then return nil end
  return path
end
function ownedSaveDelete.canDelete()
  if not ownedSaveDelete.supported or not active or contextHidden or inputContextName~=contextName or timer~=0 then return false end
  local path=ownedSaveDelete.selectedPath();if not path then return false end
  local allowed=native(ownedSaveDelete.prefix..'CanDelete',path)
  assert(type(allowed)=='boolean','Owned save deletion eligibility must be a boolean')
  return allowed
end
function ownedSaveDelete.clearConfirmation()
  ownedSaveDelete.confirmationPath=nil;ownedSaveDelete.confirmationName=nil;ownedSaveDelete.confirmationEntry=nil
end
function ownedSaveDelete.clearDispatch()
  ownedSaveDelete.dispatchPath=nil;ownedSaveDelete.dispatchName=nil;ownedSaveDelete.dispatchEntry=nil
end
function ownedSaveDelete.confirmationValid()
  local path=ownedSaveDelete.confirmationPath
  return path~=nil and not controls.DeleteConfirm:IsHidden() and path==ownedSaveDelete.selectedPath() and
    ownedSaveDelete.canDelete() and (not hasRetainedSaveMenuUi or
      ownedSaveDelete.confirmationName==controls.NameBox:GetText() and ownedSaveDelete.confirmationEntry==g_SelectedEntry)
end
function ownedSaveOverwrite.invalidate()
  ownedSaveOverwrite.confirmation=nil;ownedSaveOverwrite.dispatch=nil
end
function ownedSaveOverwrite.find(name)
  if not hasRetainedSaveMenuUi or not ownedSaveOverwrite.supported or not active or contextHidden or
    inputContextName~=contextName or timer~=0 or type(g_SavedGames)~='table' or type(name)~='string' or
    type(ValidateText)~='function' or not ValidateText(name) or Locale.Length(name)>32 then return nil end
  local found
  for _,entry in ipairs(g_SavedGames) do
    local observed=type(entry)=='table' and ownedSaveOverwrite.listed[entry.FileName]
    if observed and not entry.IsCloudSave and entry.DisplayName==observed.name and
      Locale.ToUpper(name)==Locale.ToUpper(observed.name) then
      -- Ambiguous case-folded names may never choose a destructive target.
      if found then return nil end
      if observed.known==nil then
        local header=native('saveMenuHeader',entry.FileName)
        assert(header==nil or type(header)=='table','Overwrite header must be an observed table or nil')
        observed.known=header~=nil
      end
      if not observed.known then return nil end
      found=entry
    end
  end
  return found
end
function ownedSaveOverwrite.eligible()
  return controls.NameBox~=nil and ownedSaveOverwrite.find(controls.NameBox:GetText())~=nil
end
function ownedSaveOverwrite.valid(grant)
  return grant~=nil and grant.epoch==ownedSaveOverwrite.epoch and
    controls.NameBox:GetText()==grant.name and g_SelectedEntry==grant.entry and
    ownedSaveOverwrite.find(grant.name)==grant.entry and grant.entry.FileName==grant.path
end
function ownedSaveOverwrite.armed()
  return not controls.DeleteConfirm:IsHidden() and ownedSaveOverwrite.valid(ownedSaveOverwrite.confirmation)
end
function ownedSaveOverwrite.beginSave()
  assert(hasRetainedSaveMenuUi and ownedSaveDelete.callbackRole==nil and saveMenuCanSave(),
    'Original SaveMenu save admission is unavailable or reentrant')
  ownedSaveDelete.callbackRole='Save'
end
function ownedSaveOverwrite.endSave(ok)
  ownedSaveDelete.callbackRole=nil;ownedSaveDelete.clearDispatch();ownedSaveOverwrite.dispatch=nil
  if not ok then ownedSaveDelete.clearConfirmation();ownedSaveOverwrite.invalidate() end
end
function ownedSaveOverwrite.operation()
  if ownedSaveDelete.confirmationValid() then return 'delete' end
  if hasRetainedSaveMenuUi and ownedSaveOverwrite.armed() then return 'overwrite' end
  return 'none'
end
function ownedSaveDelete.delete(path,...)
  -- Stock OnYes hides its confirmation before calling this bridge. The grant
  -- is captured at callback admission and is consumed before native mutation.
  local admitted,name,entry=ownedSaveDelete.dispatchPath,ownedSaveDelete.dispatchName,ownedSaveDelete.dispatchEntry
  ownedSaveDelete.clearDispatch()
  assert(select('#',...)==0 and ownedSaveDelete.callbackRole=='Yes' and admitted~=nil and
    path==admitted and ownedSaveDelete.selectedPath()==admitted and ownedSaveDelete.canDelete() and
    (not hasRetainedSaveMenuUi or name==controls.NameBox:GetText() and entry==g_SelectedEntry),
    'Deleting an owned save requires its original selected confirmation dispatch')
  local deleted=native(ownedSaveDelete.prefix..'Delete',text(path))
  assert(deleted==true,'Owned save deletion did not report validated success')
  return true
end
function ownedSaveDelete.refreshControls()
  if not hasRetainedSaveMenuUi and not hasRetainedLoadMenuUi then return end
  local allowed=ownedSaveDelete.canDelete()
  if ownedSaveDelete.confirmationPath~=nil and not ownedSaveDelete.confirmationValid() then ownedSaveDelete.clearConfirmation() end
  if ownedSaveOverwrite.confirmation~=nil and not ownedSaveOverwrite.armed() then ownedSaveOverwrite.invalidate() end
  assert(not (ownedSaveDelete.confirmationPath~=nil and ownedSaveOverwrite.confirmation~=nil),
    'Owned save deletion and overwrite cannot share an armed confirmation')
  controls.Delete:SetDisabled(not allowed)
  controls.Yes:SetDisabled(ownedSaveOverwrite.operation()=='none')
  if hasRetainedSaveMenuUi and controls.SaveButton then controls.SaveButton:SetDisabled(not saveMenuCanSave()) end
end
local function utf8Characters(value)
  local result={};local index=1
  while index<=#value do
    local first=string.byte(value,index);local length,codepoint
    if first<0x80 then length=1;codepoint=first
    elseif first>=0xC2 and first<=0xDF then length=2;codepoint=first-0xC0
    elseif first>=0xE0 and first<=0xEF then length=3;codepoint=first-0xE0
    elseif first>=0xF0 and first<=0xF4 then length=4;codepoint=first-0xF0
    else error('Invalid UTF-8 lead byte in production label') end
    assert(index+length-1<=#value,'Truncated UTF-8 sequence in production label')
    for offset=1,length-1 do
      local byte=string.byte(value,index+offset)
      assert(byte>=0x80 and byte<=0xBF,'Invalid UTF-8 continuation byte in production label')
      codepoint=codepoint*64+byte-0x80
    end
    assert(not (length==2 and codepoint<0x80) and
      not (length==3 and (codepoint<0x800 or (codepoint>=0xD800 and codepoint<=0xDFFF))) and
      not (length==4 and (codepoint<0x10000 or codepoint>0x10FFFF)),
      'Noncanonical UTF-8 sequence in production label')
    result[#result+1]={codepoint=codepoint,character=string.sub(value,index,index+length-1)}
    index=index+length
  end
  return result
end
local function utf8Codepoint(codepoint)
  if codepoint<0x80 then return string.char(codepoint) end
  if codepoint<0x800 then return string.char(0xC0+math.floor(codepoint/64),0x80+codepoint%64) end
  if codepoint<0x10000 then
    return string.char(0xE0+math.floor(codepoint/4096),0x80+math.floor(codepoint/64)%64,0x80+codepoint%64)
  end
  assert(codepoint<=0x10FFFF,'Invalid Unicode codepoint in production label')
  return string.char(0xF0+math.floor(codepoint/262144),0x80+math.floor(codepoint/4096)%64,
    0x80+math.floor(codepoint/64)%64,0x80+codepoint%64)
end
do
  local metrics=layout.fontMetrics
  if metrics~=nil then
    assert(type(metrics)=='table' and getmetatable(metrics)==nil,'Font metrics must be a plain table')
    if metrics.glyphSetStorage==nil then
      assert(metrics.sharedProfileId==nil and metrics.glyphSetRefs==nil and type(metrics.glyphSets)=='table',
        'Inline font metrics cannot contain shared references or omit their glyph maps')
    else
      assert(metrics.glyphSetStorage=='ZEROSIS_UI_SHARED_GLYPH_SETS_V1' and metrics.glyphSets==nil,
        'Unknown or mixed shared/inline font metric storage')
      local function digest(value)
        return type(value)=='string' and #value==64 and value:match('^[0-9a-f]+$')~=nil
      end
      assert(digest(metrics.sharedProfileId),'Shared font metrics require their exact profile ID')
      local bank=ZeroSisUiSharedFontMetrics
      assert(type(bank)=='table' and getmetatable(bank)==nil and
        bank.schema=='zerosis.ui.shared_font_metrics.v1' and digest(bank.profileId) and
        bank.profileId==metrics.sharedProfileId and type(bank.glyphSets)=='table' and
        getmetatable(bank.glyphSets)==nil,'Shared font bank schema or profile does not match the layout')
      for field in pairs(bank) do
        assert(field=='schema' or field=='profileId' or field=='glyphSets','Unknown shared font bank field')
      end
      local bankCount=0
      for id,glyphs in pairs(bank.glyphSets) do
        bankCount=bankCount+1
        assert(bankCount<=64 and digest(id) and type(glyphs)=='table' and getmetatable(glyphs)==nil and
          next(glyphs)~=nil,'Shared font bank has an invalid or empty glyph map')
      end
      assert(bankCount>0,'Shared font bank is empty')
      local refs=metrics.glyphSetRefs
      assert(type(refs)=='table' and getmetatable(refs)==nil,'Shared font references must be a plain array')
      local count=0
      for index in pairs(refs) do
        count=count+1
        assert(type(index)=='number' and index==math.floor(index) and index>=1 and index<=64,
          'Shared font references must use dense positive array indices')
      end
      assert(count>0 and count<=64 and #refs==count,'Shared font references are missing or sparse')
      local resolved,used={},{}
      local previous
      for index=1,count do
        local id=refs[index]
        assert(digest(id) and (previous==nil or previous<id),'Shared font references must be sorted and unique')
        local glyphs=bank.glyphSets[id]
        assert(type(glyphs)=='table','Shared font reference is absent from its bank')
        -- Sealed generation and catalog checks verify every original glyph value.
        resolved[id]=glyphs;previous=id
      end
      assert(type(metrics.fonts)=='table' and getmetatable(metrics.fonts)==nil,'Shared font metadata is missing')
      local fontCount=0
      for fontID,font in pairs(metrics.fonts) do
        fontCount=fontCount+1
        assert(fontCount<=64 and type(fontID)=='string' and fontID~='' and type(font)=='table' and
          getmetatable(font)==nil and digest(font.glyphSet) and font.sha256==font.glyphSet and
          resolved[font.glyphSet]~=nil and type(font.ggxmlPath)=='string' and font.ggxmlPath~='',
          'Shared font metadata must bind its exact GGXML hash to a declared glyph reference')
        finite(font.lineAdvance);finite(font.baselineOffset);finite(font.spacing);finite(font.fudgeadv)
        assert(font.lineAdvance>0,'Shared font line advance must be positive')
        used[font.glyphSet]=true
      end
      assert(fontCount>0,'Shared font metadata is empty')
      for id in pairs(resolved) do
        assert(used[id],'Shared font references contain an unused glyph map')
      end
      -- Normalize only private shallow copies; the transport and bank stay immutable.
      local normalizedMetrics,normalizedLayout={},{}
      for field,value in pairs(metrics) do normalizedMetrics[field]=value end
      normalizedMetrics.glyphSets=resolved
      for field,value in pairs(layout) do normalizedLayout[field]=value end
      normalizedLayout.fontMetrics=normalizedMetrics
      layout=normalizedLayout
    end
  end
end

local function productionFont(fontID)
  local all=assert(layout.fontMetrics,'Production layout is missing frozen glyphgen metrics')
  assert(all.policy=='CIV5_GLYPHGEN_GGXML_LAYOUT_V1' and all.retailMetricSemanticsVerified==false,
    'Unsupported production font metric policy')
  local font=assert(all.fonts and all.fonts[fontID],'Production label references an unprepared font: '..tostring(fontID))
  local glyphs=assert(all.glyphSets and all.glyphSets[font.glyphSet],'Production font glyph set is missing')
  assert(type(font.lineAdvance)=='number' and font.lineAdvance>0 and
    type(font.baselineOffset)=='number' and type(font.sha256)=='string' and type(font.ggxmlPath)=='string',
    'Invalid production font metrics')
  return font,glyphs,all
end
local function appendPlainMetrics(rows,value,glyphs,iconIndex)
  local chars=utf8Characters(value);local index=1
  while index<=#chars do
    local entry=chars[index]
    if entry.codepoint==13 then
      if chars[index+1] and chars[index+1].codepoint==10 then index=index+1 end
      rows[#rows+1]={codepoint=10,character='\n',advance=0}
    elseif entry.codepoint==10 then
      rows[#rows+1]={codepoint=10,character='\n',advance=0}
    elseif entry.codepoint==9 then
      -- Retain tab indentation as one non-collapsing layout token. The
      -- stock font has no U+0009 glyph; four GGXML spaces is our explicit
      -- presentation convention, not a measured retail tab-stop contract.
      rows[#rows+1]={codepoint=9,character='\t',advance=4*assert(glyphs[32]).advance}
    else
      local glyph=assert(glyphs[entry.codepoint],
        string.format('Production font has no exact glyph U+%04X',entry.codepoint))
      rows[#rows+1]={codepoint=entry.codepoint,character=entry.character,advance=assert(glyph.advance)}
    end
    index=index+1
  end
  return iconIndex
end
local function escapedLabelContext(value)
  local limit=128;local count=math.min(#value,limit);local bytes={}
  for index=1,count do
    local byte=string.byte(value,index)
    if byte>=0x20 and byte<=0x7E and byte~=0x22 and byte~=0x5C then
      bytes[#bytes+1]=string.char(byte)
    elseif byte==0x22 then bytes[#bytes+1]='\\"'
    elseif byte==0x5C then bytes[#bytes+1]='\\\\'
    else bytes[#bytes+1]=string.format('\\x%02X',byte) end
  end
  if #value>limit then bytes[#bytes+1]='...<truncated>' end
  return table.concat(bytes)
end
local function expandLabelMetrics(value,all,glyphs,deferUnknownIcons,finalColorDepth)
  local rows,stack={},0;local cursor=1;local iconIndex=0
  for first,token,last in string.gmatch(value,'()%[([^%[%]]*)%]()') do
    local namedToken=token:match('^[A-Z][A-Z_0-9]*$')~=nil or token=='/COLOR'
    local rgbaToken=token:sub(1,6)=='COLOR:'
    if namedToken or rgbaToken then
      if first>cursor then iconIndex=appendPlainMetrics(rows,string.sub(value,cursor,first-1),glyphs,iconIndex) end
      if token:sub(1,6)=='COLOR_' then
        stack=stack+1;assert(stack<=16,'Inline label color nesting limit exceeded')
      elseif rgbaToken then
        local red,green,blue,alpha=token:match('^COLOR:(%d+):(%d+):(%d+):(%d+)$')
        assert(red and green and blue and alpha,'Invalid inline RGBA color token: '..token)
        for _,channel in ipairs({red,green,blue,alpha}) do
          local component=tonumber(channel)
          assert(component and component>=0 and component<=255 and component==math.floor(component),
            'Inline RGBA color component is outside 0..255: '..token)
        end
        stack=stack+1;assert(stack<=16,'Inline label color nesting limit exceeded')
      elseif token=='ENDCOLOR' or token=='/COLOR' then
        assert(stack>0,'Unbalanced inline ENDCOLOR in production label');stack=stack-1
      elseif token=='NEWLINE' then
        rows[#rows+1]={codepoint=10,character='\n',advance=0}
      elseif token=='TAB' then
        appendPlainMetrics(rows,'\t',glyphs,iconIndex)
      elseif token:sub(1,5)=='ICON_' then
        local icon=all.inlineIcons and all.inlineIcons[token]
        if not icon and deferUnknownIcons then return nil end
        assert(icon,'Production label references an unprepared inline icon: '..token)
        local codepoint=0xF0000+iconIndex
        rows[#rows+1]={codepoint=codepoint,character=utf8Codepoint(codepoint),advance=assert(icon.advance)}
        iconIndex=iconIndex+1
      else
        error('Unsupported production inline presentation token: '..token)
      end
      cursor=last
    end
  end
  if cursor<=#value then appendPlainMetrics(rows,string.sub(value,cursor),glyphs,iconIndex) end
  assert(stack==(finalColorDepth or 0),'Unclosed inline color in production label')
  return rows
end
local function splitParagraph(rows,wrapWidth,glyphs)
  if #rows==0 then return {{text='',advanceWidth=0}} end
  if wrapWidth<=0 then
    local chars,advance={},0
    for _,entry in ipairs(rows) do chars[#chars+1]=entry.character;advance=advance+entry.advance end
    return {{text=table.concat(chars),advanceWidth=advance}}
  end
  local words,word={},{}
  local function pushWord()
    if #word>0 then words[#words+1]=word;word={} end
  end
  for _,entry in ipairs(rows) do
    if entry.codepoint==32 then pushWord() else word[#word+1]=entry end
  end
  pushWord()
  if #words==0 then return {{text='',advanceWidth=0}} end
  local output,current,currentWidth={}, {},0
  local function emit()
    local chars={};for _,entry in ipairs(current) do chars[#chars+1]=entry.character end
    output[#output+1]={text=table.concat(chars),advanceWidth=currentWidth}
    current={};currentWidth=0
  end
  for _,items in ipairs(words) do
    local wordWidth=0;for _,entry in ipairs(items) do wordWidth=wordWidth+entry.advance end
    local spaceWidth=0
    if #current>0 then
      local space=assert(glyphs[32],'Production font has no exact ASCII space glyph')
      spaceWidth=space.advance
    end
    if #current>0 and currentWidth+spaceWidth+wordWidth>wrapWidth then emit();spaceWidth=0 end
    if wordWidth>wrapWidth and #current==0 then
      for _,entry in ipairs(items) do
        if #current>0 and currentWidth+entry.advance>wrapWidth then emit() end
        current[#current+1]=entry;currentWidth=currentWidth+entry.advance
      end
    else
      if spaceWidth>0 then
        local space=assert(glyphs[32]);current[#current+1]={codepoint=32,character=' ',advance=space.advance}
        currentWidth=currentWidth+space.advance
      end
      for _,entry in ipairs(items) do current[#current+1]=entry;currentWidth=currentWidth+entry.advance end
    end
  end
  if #current>0 then emit() end
  return output
end
local function topPanelGoldColorDepth(value)
  if not hasRetainedTopPanelUi or value.kind~='TextButton' or value.attributes.ID~='GoldPerTurn' then return 0 end
  local body=value.label:match('^(.*)%[ENDCOLOR%]$') or value.label:match('^(.*)%[/COLOR%]$')
  if not body then return 0 end
  -- The original EN/KO negative-GPT locale pattern changes yellow to red
  -- and supplies one final close. End only that exact remaining label scope.
  -- Preserve the current provider's literal format quotes as display data.
  if body:match('^%[ICON_GOLD%]%[COLOR:255:235:0:255%]"%d+" %[COLOR:255:60:60:255%]%(%-%d+%)"$') or
     body:match('^%[ICON_GOLD%]%[COLOR:255:235:0:255%]%d+ %[COLOR:255:60:60:255%]%(%-%d+%)$') then return 1 end
  return 0
end
local function measureProductionLabel(value,deferUnknownIcons)
  if not hasRetainedPopupUi or (value.kind~='Label' and value.kind~='TextButton' and
    not ((hasRetainedSaveMenuUi or popupKind=='MapMenu') and value.kind=='EditBox')) then return end
  local font,glyphs,all=productionFont(value.attributes.Font)
  local rows
  if value.kind=='EditBox' then
    rows={};appendPlainMetrics(rows,value.label,glyphs,0)
  else rows=expandLabelMetrics(value.label,all,glyphs,deferUnknownIcons,topPanelGoldColorDepth(value)) end
  if not rows then
    value.textMeasurementPending=true
    return
  end
  local wrapWidth=0
  if value.attributes.WrapWidth then
    wrapWidth=finite(tonumber(value.attributes.WrapWidth))
    assert(wrapWidth>0,'Production WrapWidth must be positive')
  end
  local paragraphs,paragraph={},{}
  for _,entry in ipairs(rows) do
    if entry.codepoint==10 then
      paragraphs[#paragraphs+1]=paragraph;paragraph={}
    else paragraph[#paragraph+1]=entry end
  end
  paragraphs[#paragraphs+1]=paragraph
  local lines={}
  for _,part in ipairs(paragraphs) do
    for _,line in ipairs(splitParagraph(part,wrapWidth,glyphs)) do lines[#lines+1]=line end
  end
  local maxWidth=0
  for _,line in ipairs(lines) do maxWidth=math.max(maxWidth,line.advanceWidth) end
  local leading=finite(tonumber(value.attributes.LeadingOffset or '0'))
  local lineAdvance=font.lineAdvance+leading
  assert(lineAdvance>0,'Production label line advance must be positive')
  if not value.explicitSize then
    value.w=wrapWidth>0 and wrapWidth or maxWidth
    value.h=#lines*lineAdvance
  end
  value.textLines=lines
  value.textWrapWidth=wrapWidth
  value.textLineAdvance=lineAdvance
  value.textBaselineOffset=font.baselineOffset
  value.fontMetricSource={ggxmlPath=font.ggxmlPath,sha256=font.sha256}
  value.textMeasurementPending=nil
end
local function pair(s)
  if not s then return 0,0 end
  -- Stock SocialPolicy branch boxes include Size="190,290 ". Normalize
  -- only surrounding XML whitespace; malformed coordinate contents stay strict.
  s=s:match('^%s*(.-)%s*$')
  -- Both installed CityView layouts leave the buy-plot button's Y offset
  -- empty (Offset="0,"). Its omitted component keeps the initial zero.
  if hasRetainedCityUi and s=='0,' then return 0,0 end
  s=s:gsub('%.',',')
  if s=='Full,Full' then return viewport.w,viewport.h end
  local fullHeight=s:match('^Full,([%-]?%d+)$')
  if fullHeight then return viewport.w,tonumber(fullHeight) end
  local fullWidth=s:match('^([%-]?%d+),Full$')
  if fullWidth then return tonumber(fullWidth),viewport.h end
  local a,b=s:match('^([%-]?%d+),([%-]?%d+)$')
  assert(a and b, 'Unsupported UI coordinate: '..s)
  return tonumber(a),tonumber(b)
end
local function state(handle)
  return assert(states[handle], 'Invalid or destroyed UI control')
end
local function colorCopy(v)
  assert(type(v)=='table', 'UI color must be a vector')
  return {x=finite(v.x), y=finite(v.y), z=finite(v.z), w=finite(v.w)}
end
local function buttonKind(kind)
  return kind=='Button' or kind=='GridButton' or kind=='TextButton' or kind=='DownButton' or kind=='UpButton' or
    ((hasRetainedCityUi or hasRetainedSocialPolicyUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp') and (kind=='CheckBox' or kind=='RadioButton'))
end
local function inheritedDisabled(handle)
  while handle do
    local value=state(handle)
    if value.disabled then return true end
    handle=value.parent
  end
  return false
end
local metatable={__metatable='ZeroSis UI control', __index=function(handle,name)
  state(handle)
  return methods[name] or error('Unsupported UI control method: '..tostring(name))
end}
local function localizeXmlText(value)
  -- Original GameMenu strings also contain dictionary expressions with case
  -- modifiers. Forward the complete expression to the existing native composer.
  if value:match('^TXT_KEY_') or ((hasRetainedGameMenuUi or hasRetainedLoadMenuUi) and value:find('{%s*TXT_KEY_')) then
    return native('locale',value)
  end
  return value
end
local function make(node,parent,names,styleChildSource)
  assert(type(node)=='table' and type(node.attributes)=='table', 'Invalid XML control description')
  sequence=sequence+1
  local sourceAttrs={}
  for k,v in pairs(node.sourceAttributes or node.attributes) do sourceAttrs[k]=v end
  local attrs={}
  if styleChildSource then
    assert((hasRetainedNotificationUi or (hasRetainedLoadMenuUi or popupKind=='MenuOptions') and styleChildSource.ownerPullDownKey) and node.sourceAttributes,
      'Only inspected original style children may carry separate source attributes')
    for k,v in pairs(node.attributes) do attrs[k]=v end
  elseif hasRetainedPopupUi and sourceAttrs.Style then
    local defaults=assert(layout.styleDefaults and layout.styleDefaults[sourceAttrs.Style],
      'Missing frozen popup style defaults: '..sourceAttrs.Style)
    for k,v in pairs(defaults.attributes) do attrs[k]=v end
  end
  for k,v in pairs(sourceAttrs) do attrs[k]=v end
  if hasRetainedEconomicChildUi and node.kind=='Stack' and attrs.StackGrowth==nil then
    -- These exact installed stacks omit StackGrowth (some spell Growth).
    -- Keep sourceAttributes intact and disclose the frontend default candidate.
    local id=attrs.ID
    local outer=hasRetainedEconomicGeneralUi and id=='GoldStack' or
      hasRetainedEconomicHappinessUi and (id=='HappinessStack' or id=='UnhappinessStack' or id=='ResourcesStack')
    assert((outer and attrs.Growth=='Bottom') or (economicDynamicStacks[id] and attrs.Growth==nil),
      'Unregistered Economic stack direction fallback')
    assert(layout.economicOverview and
      layout.economicOverview.stackGrowthPolicy=='ECONOMIC_ORIGINAL_OMITTED_GROWTH_BOTTOM_CANDIDATE_V1',
      'Economic stack fallback provenance is missing')
    attrs.StackGrowth='Bottom'
  end
  if popupKind=='MenuOptions' and node.kind=='Stack' and attrs.StackGrowth==nil then
    assert(layout.menuOptions and layout.menuOptions.omittedStackGrowth=='Bottom' and
      layout.menuOptions.retailWidgetGeometryVerified==false,
      'Menu omitted-stack-growth candidate provenance is missing')
    attrs.StackGrowth='Bottom'
  end
  local contextFontDefaults
  if hasRetainedCityUi and not parent and layout.contextFontDefaults then
    contextFontDefaults=layout.contextFontDefaults
    assert(contextFontDefaults.policy=='ORIGINAL_CITY_VIEW_CONTEXT_FONT_FALLBACK_CANDIDATE_V1' and
      contextFontDefaults.retailDefaultFontVerified==false,'Invalid CityView context font fallback')
    for k,v in pairs(contextFontDefaults.attributes) do if attrs[k]==nil then attrs[k]=v end end
  end
  if hasRetainedPopupUi and parent then
    local inherited=state(parent).attributes
    for _,name in ipairs({'Font','FontStyle','ColorSet','ColorLayer0','ColorLayer1','ColorLayer2'}) do
      if attrs[name]==nil then attrs[name]=inherited[name] end
    end
  elseif (hasRetainedCityUi or hasRetainedUnitUi) and parent then
    local inherited=state(parent).attributes
    for _,name in ipairs({'Font','FontStyle','ColorSet','ColorLayer0','ColorLayer1','ColorLayer2'}) do
      if attrs[name]==nil then attrs[name]=inherited[name] end
    end
  end
  local handle=setmetatable({},metatable)
  local w,h=pair(attrs.Size)
  if hasRetainedEconomicParentUi and node.kind=='LuaContext' then
    assert((attrs.ID=='EconomicGeneralInfo' or attrs.ID=='HappinessInfo') and
      attrs.FileName=='Assets/UI/InGame/Popups/'..attrs.ID and
      attrs.Size==nil and attrs.Anchor==nil and attrs.Offset==nil,
      'Economic child viewport differs from the original parent slot')
    w,h=viewport.w,viewport.h
  end
  local defaultSize
  if (popupKind=='MenuOptions' or popupKind=='TouchHelp') and node.kind=='CheckBox' then
    defaultSize=assert(layout.controlDefaultSizes and layout.controlDefaultSizes[attrs.ID],
      'Menu checkbox has no source-backed default-size candidate')
    assert(defaultSize.policy=='MENU_BUTTON_16_DEFAULT_CANDIDATE_V1' and defaultSize.width==32 and
      defaultSize.height==32 and defaultSize.style=='Button_16' and defaultSize.frameCount==4 and
      defaultSize.texture=='Assets/UI/Art/Controls/Checkbox.dds' and
      defaultSize.sourceStyleAttributes.Size=='32,32' and defaultSize.retailWidgetGeometryVerified==false,
      'Invalid source-backed menu checkbox default candidate')
    attrs.Texture=defaultSize.texture;attrs.ButtonTexture=defaultSize.texture
    w,h=defaultSize.width,defaultSize.height
  end
  if hasRetainedSocialPolicyUi and node.kind=='CheckBox' and attrs.ID=='PolicyInfo' and not attrs.Size then
    defaultSize=assert(layout.controlDefaultSizes and layout.controlDefaultSizes.PolicyInfo,
      'SocialPolicy PolicyInfo has no source-backed default-size candidate')
    assert(defaultSize.policy=='SOCIAL_POLICY_BUTTON_16_DEFAULT_CANDIDATE_V1' and
      defaultSize.style=='Button_16' and defaultSize.width==32 and defaultSize.height==32 and
      defaultSize.texture=='Assets/UI/Art/Controls/Checkbox.dds' and
      defaultSize.sourceStyleAttributes.Texture==defaultSize.texture and
      defaultSize.sourceStyleAttributes.Size=='32,32' and
      defaultSize.retailWidgetGeometryVerified==false,
      'Invalid source-backed SocialPolicy checkbox default candidate')
    attrs.Texture=defaultSize.texture
    attrs.ButtonTexture=defaultSize.texture
    w,h=defaultSize.width,defaultSize.height
  end
  if hasRetainedLoadMenuUi and node.kind=='CheckBox' then
    assert((attrs.ID=='AutoCheck' or attrs.ID=='CloudCheck') and not sourceAttrs.Size and not sourceAttrs.Style and
      not sourceAttrs.ButtonTexture,'LoadMenu checkbox differs from the original declaration')
    defaultSize=assert(layout.controlDefaultSizes and layout.controlDefaultSizes[attrs.ID],
      'LoadMenu checkbox has no inspected source/atlas default candidate')
    assert(defaultSize.policy=='LOAD_MENU_BUTTON_16_DEFAULT_CANDIDATE_V1' and defaultSize.width==32 and defaultSize.height==32 and
      defaultSize.frameCount==4 and defaultSize.style=='Button_16' and
      defaultSize.texture=='Assets/UI/Art/Controls/Checkbox.dds' and
      defaultSize.sourceStyleAttributes.Texture==defaultSize.texture and defaultSize.sourceStyleAttributes.Size=='32,32' and
      defaultSize.defaultBindingVerified==false and defaultSize.retailGeometryVerified==false and
      defaultSize.retailWidgetStateMappingVerified==false and
      defaultSize.atlas.width==32 and defaultSize.atlas.height==128 and
      defaultSize.atlas.cellWidth==32 and defaultSize.atlas.cellHeight==32 and defaultSize.atlas.frameCount==4,
      'Invalid source-backed LoadMenu checkbox default candidate')
    for name,item in pairs(sourceAttrs) do assert(defaultSize.controlSourceAttributes[name]==item,
      'LoadMenu checkbox default source attributes differ') end
    for name,item in pairs(defaultSize.controlSourceAttributes) do assert(sourceAttrs[name]==item,
      'LoadMenu checkbox default added a source attribute') end
    assert(defaultSize.source.sha256==layout.styleDefaultsSource.sha256 and
      defaultSize.controlSource.sha256==layout.loadMenu.originalXml.sha256,
      'LoadMenu checkbox default source hashes differ')
    attrs.Texture=defaultSize.texture;attrs.ButtonTexture=defaultSize.texture
    w,h=defaultSize.width,defaultSize.height
  end
  if hasRetainedCityUi and not attrs.Size and (node.kind=='CheckBox' or node.kind=='RadioButton') then
    local basename=assert(attrs.ButtonTexture,'Check control has no original atlas'):gsub('\\','/'):match('([^/]+)$'):lower()
    defaultSize=assert(layout.controlDefaultSizes and layout.controlDefaultSizes[basename],
      'Check control has no inspected default atlas frame: '..basename)
    assert(defaultSize.policy=='CIV5_CHECK_ATLAS_SQUARE_FRAME_CANDIDATE_V1' and
      defaultSize.retailWidgetGeometryVerified==false and defaultSize.width==32 and defaultSize.height==32 and
      defaultSize.frameCount==4,'Invalid retained check control geometry policy')
    w,h=defaultSize.width,defaultSize.height
  end
  if attrs.Length~=nil then
    local length=finite(tonumber(attrs.Length))
    assert(length>=0,'Negative styled control length')
    if attrs.Vertical=='1' then h=length else w=length end
  end
  if popupKind=='MenuOptions' and node.kind=='Slider' then
    local slider=assert(layout.menuOptions and layout.menuOptions.sliderStyle,
      'Options slider original style provenance is missing')
    assert(slider.policy=='ORIGINAL_HORIZONTAL_SLIDER_STYLE_CANDIDATE_V1' and slider.height==32 and
      slider.shuttleWidth==32 and slider.retailWidgetGeometryVerified==false and attrs.Style=='Slider',
      'Options slider source-backed style candidate changed')
    h=slider.height
  end
  local x,y=pair(attrs.Offset)
  local tx,ty=pair(attrs.TextureOffset)
  local value={key=sequence,kind=node.kind,attributes=attrs,sourceAttributes=sourceAttrs,children={},parent=parent,
    hidden=attrs.Hidden=='1' or attrs.Hidden=='True' or attrs.Hidden=='true',w=w,h=h,offsetX=x,offsetY=y,x=0,y=0,
    label=attrs.String or '',tooltip=attrs.ToolTip or '',texture=attrs.Texture or '',
    alpha=finite(tonumber(attrs.Alpha or '1')),font=attrs.Font,anchor=attrs.Anchor or 'L,T',
    textureX=tx,textureY=ty,callbacks={},void1=nil,void2=nil,
    disabled=attrs.Disabled==true or attrs.Disabled=='1' or attrs.Disabled=='True' or attrs.Disabled=='true',
    percent=nil,percentPlus=nil,scrollX=0,scrollY=0,hovered=false,buttonState='normal',animation=nil,
    explicitSize=attrs.Size~=nil,checked=attrs.IsChecked=='1',defaultSize=defaultSize,contextFontDefaults=contextFontDefaults,
    autoSizeStack=node.kind=='Stack' and (not attrs.Size or (w==0 and h==0)),styleChildSource=styleChildSource,
    originalDataKind=node.originalDataKind,ownerPullDownKey=node.ownerPullDownKey}
  if node.kind=='AlphaAnim' then
    local alphaStart=tonumber(attrs.AlphaStart);local alphaEnd=tonumber(attrs.AlphaEnd)
    local speed=tonumber(attrs.Speed);local pause=tonumber(attrs.Pause or '0')
    local newFinger=hasRetainedNotificationUi and (sourceAttrs.Style=='NewFinger' or sourceAttrs.Style=='NewFingerRed')
    if newFinger then
      local policy=assert(layout.notificationPanel and layout.notificationPanel.animationPolicy)
      assert(attrs.Speed==nil and attrs.Cycle=='OneBounce' and attrs.EndPause=='5' and
        policy.newFinger=='CIV5_NOTIFICATION_ONE_BOUNCE_CANDIDATE_V1' and
        policy.omittedNewFingerSpeed==1 and policy.retailTimingVerified==false,
        'Original NewFinger omitted-speed candidate changed')
      speed=policy.omittedNewFingerSpeed
    end
    assert(alphaStart and alphaEnd and speed and speed>0 and pause and pause>=0,
      'AlphaAnim requires numeric AlphaStart/AlphaEnd/Speed/Pause')
    local gameMenuOnce=hasRetainedGameMenuUi and attrs.Cycle=='Once'
    if gameMenuOnce then
      local owner=parent and state(parent).parent
      local buttons={RestartGameButton=true,QuickSaveButton=true,SaveGameButton=true,
        LoadGameButton=true,OptionsButton=true,RetireButton=true,MainMenuButton=true,
        ExitGameButton=true,ReturnButton=true}
      assert(parent and state(parent).kind=='ShowOnMouseOver' and owner and
        state(owner).kind=='GridButton' and buttons[state(owner).attributes.ID] and
        sourceAttrs.AlphaStart=='.2' and sourceAttrs.AlphaEnd=='0' and
        sourceAttrs.Speed=='1' and sourceAttrs.Pause=='0' and #node.children==2,
        'Once requires an original GameMenu button hover declaration')
    end
    assert(attrs.Cycle=='Bounce' or newFinger or gameMenuOnce,'Unsupported AlphaAnim cycle: '..tostring(attrs.Cycle))
    value.animation={running=false,startTime=0,phase=0,manuallyStopped=false,
      speed=speed,defaultSpeedUsed=newFinger or nil,once=gameMenuOnce or nil,
      activationAllowed=false,activationStartTime=0,completed=false}
  elseif node.kind=='ScrollAnim' then
    local speed=tonumber(attrs.Speed);local pause=tonumber(attrs.Pause or '0')
    assert(speed and speed>0 and pause and pause>=0,'ScrollAnim requires numeric Speed/Pause')
    value.animation={running=false,startTime=0,phase=0,manuallyStopped=false}
  elseif node.kind=='SlideAnim' then
    assert(hasRetainedNotificationUi and sourceAttrs.Style=='NotificationSlide' and
      sourceAttrs.Anchor=='L,T' and sourceAttrs.ID=='NotificationSlide' and attrs.Size==nil and
      attrs.Start=='0,500' and attrs.End=='0,0' and attrs.Cycle=='Once' and attrs.Pause=='0' and
      attrs.Function=='Root' and attrs.FunctionPower=='1.5' and attrs.Speed=='1.0',
      'SlideAnim requires the original NotificationSlide source/style contract')
    value.animation={running=false,startTime=0,phase=0,manuallyStopped=false}
  elseif hasRetainedNotificationUi and node.kind=='FlipAnim' then
    value.animation={running=false,startTime=0,phase=0,manuallyStopped=false}
  end
  value.label=localizeXmlText(value.label)
  value.tooltip=localizeXmlText(value.tooltip)
  -- DeclareWar XML contains example deal strings which the stock View replaces
  -- or hides before showing the popup. An unknown icon in that initial text is
  -- not a font alias: retain it verbatim and require exact metrics if it is
  -- still visible when the context is queued. Explicit SetText stays strict.
  measureProductionLabel(value,hasRetainedDeclareWarUi or popupKind=='MenuOptions')
  states[handle]=value
  if attrs.ID then
    assert(not names[attrs.ID], 'Duplicate XML control ID: '..attrs.ID)
    names[attrs.ID]=handle
  end
  if parent then table.insert(state(parent).children,handle) end
  if hasRetainedNotificationUi and not styleChildSource and node.kind=='AlphaAnim' and
     (sourceAttrs.Style=='NewFinger' or sourceAttrs.Style=='NewFingerRed') then
    local definition=assert(layout.styleDefaults[sourceAttrs.Style])
    local origin=assert(layout.styleDefaultsSource)
    for index,child in ipairs(definition.children) do
      local indices=array();indices[1]=index
      make(child,handle,names,{style=sourceAttrs.Style,ownerKey=value.key,
        path=origin.path,sha256=origin.sha256,indices=indices})
    end
  end
  for index,child in ipairs(node.children) do
    local origin
    if styleChildSource then
      local indices=array();for _,part in ipairs(styleChildSource.indices) do indices[#indices+1]=part end
      indices[#indices+1]=index
      origin={style=styleChildSource.style,ownerKey=styleChildSource.ownerKey,
        path=styleChildSource.path,sha256=styleChildSource.sha256,indices=indices,
        ownerPullDownKey=styleChildSource.ownerPullDownKey}
    end
    make(child,handle,names,origin)
  end
  if node.kind=='PullDown' and (popupKind~='MenuOptions' or attrs.ID=='WResolutionPull') then pullDown.construct(handle) end
  return handle
end

-- GenericPullDown declares five sibling Data records. They describe one native
-- composite rather than five paintable sibling controls. Keep their source
-- records in styleDefaults and retain the actual button/frame/scroll/stack tree.
function pullDown.contains(handle,ancestor)
  while handle do
    if handle==ancestor then return true end
    local value=states[handle];handle=value and value.parent or nil
  end
  return false
end
function pullDown.close(owner)
  owner=owner or pullDown.opened
  local composite=owner and pullDown.owners[owner]
  if not composite then return false end
  local wasOpen=pullDown.opened==owner
  if states[composite.popup] then state(composite.popup).hidden=true end
  if wasOpen then pullDown.opened=nil end
  local function clearHover(handle)
    local value=states[handle];if not value then return end
    value.hovered=false;value.buttonState='normal'
    for _,child in ipairs(value.children) do clearHover(child) end
  end
  clearHover(owner);layoutDirty=true
  return wasOpen
end
function pullDown.usable(owner)
  if not active or contextHidden or inputContextName~=contextName then return false end
  while owner do
    local value=states[owner]
    if not value or value.hidden or value.disabled then return false end
    owner=value.parent
  end
  return true
end
function pullDown.validate()
  if pullDown.opened and not pullDown.usable(pullDown.opened) then pullDown.close() end
end
function pullDown.invalidate(handle,destroying)
  if not pullDown.opened then return end
  local composite=pullDown.owners[pullDown.opened]
  if pullDown.contains(pullDown.opened,handle) or pullDown.contains(composite.button,handle) or
    handle==composite.popup or handle==composite.panel or handle==composite.stack or
    destroying and pullDown.contains(handle,pullDown.opened) then pullDown.close() end
end
function pullDown.inputAllowed(handle)
  pullDown.validate()
  if not pullDown.opened then return true end
  local composite=pullDown.owners[pullDown.opened]
  return pullDown.contains(handle,composite.button) or pullDown.contains(handle,composite.popup)
end
function pullDown.consumeClick(handle)
  pullDown.validate()
  if not pullDown.opened then return false end
  if handle==root or not pullDown.inputAllowed(handle) then pullDown.close();return true end
  return false
end
function pullDown.origin(owner,indices)
  local origin=assert(layout.styleDefaultsSource,'PullDown source provenance is missing')
  local sourceIndices=array();for _,index in ipairs(indices) do sourceIndices[#sourceIndices+1]=index end
  return {style='GenericPullDown',ownerKey=state(owner).key,ownerPullDownKey=state(owner).key,
    path=origin.path,sha256=origin.sha256,indices=sourceIndices}
end
function pullDown.part(source,kind,owner,originalKind)
  return {kind=kind,attributes=source.attributes,sourceAttributes=source.sourceAttributes,
    children=source.children,originalDataKind=originalKind,ownerPullDownKey=state(owner).key}
end
function pullDown.isChrome(value,panel)
  if not (hasRetainedLoadMenuUi or popupKind=='MenuOptions') or not panel or panel.kind~='ScrollPanel' or
    panel.originalDataKind~='ScrollPanelData' or panel.sourceAttributes.AutoScrollBar~='1' or
    not panel.ownerPullDownKey or not value.styleChildSource or
    value.styleChildSource.ownerPullDownKey~=panel.ownerPullDownKey then return false end
  local expected={ScrollBar='VertSlider',UpButton='ScrollBarUp',DownButton='ScrollBarDown'}
  return expected[value.kind]~=nil and value.sourceAttributes.Style==expected[value.kind] and
    value.sourceAttributes.AnchorSide=='O,I'
end
function pullDown.deferPackageScroll(handle,value)
  local window=controls.ReferencedPackagesWindow
  return hasRetainedLoadMenuUi and value.kind=='ScrollPanel' and
    value.sourceAttributes.ID=='ReferencedPackagesScrollPanel' and window and states[window] and
    state(window).sourceAttributes.Hidden=='1' and state(window).hidden and
    pullDown.contains(handle,window) and value.contentW==nil and value.contentH==nil
end
function pullDown.construct(owner)
  local value=state(owner)
  assert(value.sourceAttributes.Style=='GenericPullDown' and
    (hasRetainedLoadMenuUi and value.attributes.ID=='SortByPullDown' and #value.children==0 or
     popupKind=='MenuOptions' and value.attributes.ID=='WResolutionPull' and #value.children==1 and
       state(value.children[1]).kind=='Label'),
    'PullDown requires an explicitly supported original GenericPullDown declaration')
  local definition=assert(layout.styleDefaults.GenericPullDown,'GenericPullDown style is missing')
  local parts=definition.children
  assert(#parts==5 and parts[1].kind=='ButtonData' and #parts[1].children==1 and
    parts[1].children[1].kind=='GridButton' and parts[2].kind=='GridData' and
    parts[3].kind=='ScrollPanelData' and parts[4].kind=='StackData' and
    parts[5].kind=='InstanceData' and parts[5].attributes.Name=='InstanceOne' and
    #parts[5].children==1 and parts[5].children[1].kind=='GridButton',
    'GenericPullDown differs from its original five-part source declaration')
  local names={}
  local button=make(pullDown.part(parts[1].children[1],'GridButton',owner,'ButtonData'),owner,names,
    pullDown.origin(owner,{1,1}))
  local popup=make(pullDown.part(parts[2],'Grid',owner,'GridData'),owner,names,
    pullDown.origin(owner,{2}))
  local panel=make(pullDown.part(parts[3],'ScrollPanel',owner,'ScrollPanelData'),popup,names,
    pullDown.origin(owner,{3}))
  local stack=make(pullDown.part(parts[4],'Stack',owner,'StackData'),panel,names,
    pullDown.origin(owner,{4}))
  local composite={button=button,popup=popup,panel=panel,stack=stack,template=parts[5],entries={}}
  pullDown.owners[owner]=composite
  state(popup).hidden=true
  state(button).callbacks[Mouse.eLClick]=function()
    if not pullDown.usable(owner) then return end
    if pullDown.opened==owner then pullDown.close(owner);return end
    pullDown.close();pullDown.measure(owner)
    if #composite.entries==0 then return end
    pullDown.opened=owner;state(popup).hidden=false;layoutDirty=true
  end
  for _,child in ipairs(state(panel).children) do
    local row=state(child)
    if row.kind=='UpButton' or row.kind=='DownButton' then
      local direction=row.kind=='UpButton' and -1 or 1
      row.callbacks[Mouse.eLClick]=function()
        local scroll=state(panel)
        panel:SetScrollValue(clamp(scroll.scrollY+direction*24,0,math.max(0,scroll.contentH-scroll.h)))
      end
    end
  end
  pullDown.measure(owner)
end
function pullDown.measure(owner)
  local value=state(owner);local composite=assert(pullDown.owners[owner],'PullDown composite is missing')
  local button,popup,panel,stack=state(composite.button),state(composite.popup),state(composite.panel),state(composite.stack)
  local entries={};for _,entry in ipairs(composite.entries) do
    if states[entry] and state(entry).parent==composite.stack then entries[#entries+1]=entry end
  end
  composite.entries=entries
  methods.CalculateSize(composite.stack)
  local threshold=finite(assert(tonumber(value.attributes.ScrollThreshold),'PullDown needs its source scroll threshold'))
  local px,py=pair(popup.attributes.Padding)
  assert(threshold>0 and px>=0 and py>=0 and value.w>0 and value.h>0,
    'Invalid PullDown composite geometry')
  local overflow=stack.h>threshold
  local reserve=overflow and value.attributes.SpaceForScroll=='1' and 18 or 0
  button.w=value.w;button.h=value.h
  popup.w=math.max(value.w,stack.w+2*px+reserve)
  panel.w=math.max(stack.w,popup.w-2*px-reserve)
  panel.h=math.min(stack.h,threshold)
  panel.offsetX=-reserve/2
  popup.h=panel.h+2*py
  panel.contentW=stack.w;panel.contentH=stack.h
  panel.scrollX=0;panel.scrollY=clamp(panel.scrollY,0,math.max(0,stack.h-panel.h))
  for _,child in ipairs(panel.children) do
    local row=state(child)
    if row.kind=='ScrollBar' or row.kind=='UpButton' or row.kind=='DownButton' then row.hidden=not overflow end
  end
  composite.overflow=overflow;composite.scrollThreshold=threshold;composite.reservedScrollWidth=reserve
  layoutDirty=true
end
function methods:GetButton()
  local value=state(self)
  assert((hasRetainedLoadMenuUi or popupKind=='MenuOptions' and value.attributes.ID=='WResolutionPull') and value.kind=='PullDown','GetButton requires an original supported PullDown')
  return assert(pullDown.owners[self]).button
end
function methods:ClearEntries()
  local value=state(self)
  assert((hasRetainedLoadMenuUi or popupKind=='MenuOptions' and value.attributes.ID=='WResolutionPull') and value.kind=='PullDown','ClearEntries requires an original supported PullDown')
  local composite=assert(pullDown.owners[self]);pullDown.close(self)
  while #state(composite.stack).children>0 do
    composite.stack:DestroyChild(state(composite.stack).children[#state(composite.stack).children])
  end
  composite.entries={};state(composite.panel).scrollY=0;pullDown.measure(self)
end
function methods:BuildEntry(name,names)
  local value=state(self)
  assert((hasRetainedLoadMenuUi or popupKind=='MenuOptions' and value.attributes.ID=='WResolutionPull') and value.kind=='PullDown' and name=='InstanceOne' and
    type(names)=='table' and next(names)==nil,'BuildEntry requires the original named PullDown instance and an empty table')
  local composite=assert(pullDown.owners[self]);local template=composite.template
  local entry=make(pullDown.part(template.children[1],'GridButton',self,'InstanceData'),composite.stack,names,
    pullDown.origin(self,{5,1}))
  assert(names.Button==entry,'Original PullDown InstanceOne Button identity changed')
  state(entry).instanceTemplate=name;state(entry).pullDownEntryOwner=self
  if popupKind=='MenuOptions' then
    state(entry).callbacks[Mouse.eLClick]=function()
      assert(type(value.selectionCallback)=='function','Resolution PullDown selection callback is missing')
      value.selectionCallback(state(entry).void1)
    end
  end
  composite.entries[#composite.entries+1]=entry;layoutDirty=true
end
function methods:RegisterSelectionCallback(callback)
  local value=state(self)
  assert(popupKind=='MenuOptions' and value.kind=='PullDown' and value.attributes.ID=='WResolutionPull' and
    type(callback)=='function','Selection callback requires the original supported resolution PullDown')
  value.selectionCallback=callback
end
function methods:CalculateInternals()
  local value=state(self)
  assert((hasRetainedLoadMenuUi or popupKind=='MenuOptions' and value.attributes.ID=='WResolutionPull') and value.kind=='PullDown','CalculateInternals requires an original supported PullDown')
  pullDown.measure(self)
  if active then anchor(root) end
end
function pullDown.records()
  local result=array()
  for owner,composite in pairs(pullDown.owners) do
    local entryKeys=array()
    for _,entry in ipairs(composite.entries) do if states[entry] then entryKeys[#entryKeys+1]=state(entry).key end end
    result[#result+1]={key=state(owner).key,opened=pullDown.opened==owner,
      buttonKey=state(composite.button).key,popupKey=state(composite.popup).key,
      scrollPanelKey=state(composite.panel).key,stackKey=state(composite.stack).key,entryKeys=entryKeys,
      style='GenericPullDown',scrollThreshold=composite.scrollThreshold,overflow=composite.overflow,
      reservedScrollWidth=composite.reservedScrollWidth,geometryPolicy=pullDown.geometryPolicy,
      retailGeometryVerified=false,retailWidgetBehaviorVerified=false,
      originalStyleSource=layout.styleDefaultsSource}
  end
  table.sort(result,function(a,b) return a.key<b.key end)
  return result
end

local function animationElapsed(animation,now)
  return animation.phase+(animation.running and math.max(0,now-animation.startTime) or 0)
end
local function gameMenuOncePhase(value,now)
  local animation=assert(value.animation)
  assert(hasRetainedGameMenuUi and animation.once,'Once phase requires a GameMenu hover')
  local elapsed=math.min(animation.speed,animationElapsed(animation,now))
  if elapsed>=animation.speed then
    animation.phase=animation.speed;animation.running=false;animation.completed=true
  end
  return elapsed/animation.speed,elapsed
end
local function alphaValue(value,now)
  local attrs=value.attributes;local animation=assert(value.animation)
  local start=assert(tonumber(attrs.AlphaStart));local finish=assert(tonumber(attrs.AlphaEnd))
  local speed=assert(tonumber(attrs.Speed) or animation.speed);local pause=tonumber(attrs.Pause or '0') or 0
  if animation.once then
    local phase=gameMenuOncePhase(value,now)
    return clamp(start+(finish-start)*phase,0,1)
  end
  if hasRetainedNotificationUi and animation.defaultSpeedUsed then
    local time=animationElapsed(animation,now)
    local hold=assert(tonumber(attrs.EndPause))
    if time<speed then return clamp(start+(finish-start)*time/speed,0,1) end
    if time<speed+hold then return clamp(finish,0,1) end
    if time<2*speed+hold then return clamp(finish+(start-finish)*(time-speed-hold)/speed,0,1) end
    return clamp(start,0,1)
  end
  assert(speed>0 and pause>=0 and attrs.Cycle=='Bounce','Unsupported AlphaAnim timing contract')
  local duration=speed;local period=2*(duration+pause)
  local time=animationElapsed(animation,now)%period
  local raw
  if time<pause then raw=start
  elseif time<pause+duration then raw=start+(finish-start)*((time-pause)/duration)
  elseif time<2*pause+duration then raw=finish
  else raw=finish+(start-finish)*((time-(2*pause+duration))/duration) end
  return clamp(raw,0,1)
end
local function notificationSlide(value,now)
  local elapsed=animationElapsed(assert(value.animation),now)
  local phase=clamp(elapsed/assert(tonumber(value.attributes.Speed)),0,1)
  local eased=phase^(1/assert(tonumber(value.attributes.FunctionPower)))
  local startX,startY=pair(value.attributes.Start);local endX,endY=pair(value.attributes.End)
  return startX+(endX-startX)*eased,startY+(endY-startY)*eased,phase
end
local function scrollPhase(value,now)
  local animation=assert(value.animation)
  local speed=assert(tonumber(value.attributes.Speed))
  local pause=tonumber(value.attributes.Pause or '0') or 0
  assert(speed>0 and pause>=0,'Unsupported ScrollAnim timing contract')
  local duration=speed
  local time=animationElapsed(animation,now)%(duration+pause)
  return clamp(time/duration,0,1)
end
local function setAnimationRunning(value,want,now,manual)
  local animation=value.animation
  if not animation then return end
  if animation.once then
    if manual then
      animation.phase=math.min(animation.speed,animationElapsed(animation,now))
      animation.running=false;animation.manuallyStopped=true
    elseif want~=animation.activationAllowed then
      animation.activationAllowed=want
      if want then
        animation.phase=0;animation.completed=false
        animation.startTime=now;animation.activationStartTime=now
        animation.running=not animation.manuallyStopped
      else
        animation.phase=math.min(animation.speed,animationElapsed(animation,now))
        animation.running=false
      end
    end
    return
  end
  if want then
    if not animation.running and not animation.manuallyStopped then
      animation.running=true;animation.startTime=now
    end
  elseif animation.running then
    animation.phase=animationElapsed(animation,now);animation.running=false
    if manual then animation.manuallyStopped=true end
  elseif manual then animation.manuallyStopped=true end
end
local function updateAnimations(handle,parentVisible,hoverAllowed,now)
  local value=state(handle)
  local visible=parentVisible and not value.hidden
  if value.kind=='ShowOnMouseOver' then hoverAllowed=hoverAllowed and value.hovered end
  if value.kind=='HideOnMouseOver' then hoverAllowed=hoverAllowed and not value.hovered end
  if value.kind=='AlphaAnim' or value.kind=='ScrollAnim' or
     hasRetainedNotificationUi and (value.kind=='SlideAnim' or value.kind=='FlipAnim') then
    setAnimationRunning(value,visible and hoverAllowed,now,false)
  end
  for _,child in ipairs(value.children) do updateAnimations(child,visible,hoverAllowed,now) end
end
local function parentActivation(handle)
  local chain={};local parent=state(handle).parent
  while parent do
    local value=states[parent]
    if not value then return false,false end
    chain[#chain+1]=parent;parent=value.parent
  end
  local visible=true;local hoverAllowed=true
  for index=#chain,1,-1 do
    local value=state(chain[index])
    visible=visible and not value.hidden
    if value.kind=='ShowOnMouseOver' then hoverAllowed=hoverAllowed and value.hovered end
    if value.kind=='HideOnMouseOver' then hoverAllowed=hoverAllowed and not value.hovered end
  end
  return visible,hoverAllowed
end
local function isDescendant(handle,ancestor)
  local current=handle
  while current do
    if current==ancestor then return true end
    local value=states[current]
    current=value and value.parent or nil
  end
  return false
end
local function findVisibleKey(handle,key,parentVisible)
  local value=states[handle]
  if not value then return nil end
  local visible=parentVisible and not value.hidden
  if value.key==key then return visible and handle or nil end
  if not visible then return nil end
  local childrenVisible=visible and not (value.kind=='HideOnMouseOver' and value.hovered)
  for _,child in ipairs(value.children) do
    local found=findVisibleKey(child,key,childrenVisible)
    if found then return found end
  end
  return nil
end
local function setHoveredControl(targetKey,now)
  local target
  if targetKey~=nil then
    assert(type(targetKey)=='number' and targetKey==math.floor(targetKey),'Invalid hovered control key')
    target=findVisibleKey(root,targetKey,true)
    assert(target,'Hovered control is not visible in the current scene')
  end
  local function visit(handle)
    local value=state(handle)
    if value.kind=='ShowOnMouseOver' then
      local hovered=target~=nil and (isDescendant(target,handle) or isDescendant(handle,target))
      if value.hovered~=hovered then value.hovered=hovered end
    elseif value.kind=='HideOnMouseOver' then
      -- DispatchPointerMove carries the hovered retained control key, not raw
      -- pointer coordinates. Use that control's center only when it lies in
      -- this original non-button hover region; blank-area hover remains outside
      -- the current input evidence contract.
      local targetState=target and state(target)
      local centerX=targetState and targetState.x+targetState.w/2
      local centerY=targetState and targetState.y+targetState.h/2
      local hovered=centerX~=nil and centerY~=nil and centerX>=value.x and centerX<value.x+value.w and
        centerY>=value.y and centerY<value.y+value.h or false
      if value.hovered~=hovered then value.hovered=hovered end
    end
    if buttonKind(value.kind) then
      value.buttonState=target~=nil and isDescendant(target,handle) and 'hover' or 'normal'
    end
    for _,child in ipairs(value.children) do visit(child) end
  end
  visit(root)
  updateAnimations(root,not contextHidden,true,now)
end

function methods:SetHide(value)
  assert(type(value)=='boolean', 'SetHide expects a boolean')
  local target=state(self)
  if (hasRetainedSaveMenuUi or hasRetainedLoadMenuUi) and target.attributes.ID=='DeleteConfirm' then
    ownedSaveDelete.clearConfirmation();ownedSaveOverwrite.confirmation=nil
    if not value and ownedSaveDelete.callbackRole=='Delete' and ownedSaveDelete.canDelete() then
      ownedSaveDelete.confirmationPath=ownedSaveDelete.selectedPath()
      if hasRetainedSaveMenuUi then
        ownedSaveDelete.confirmationName=controls.NameBox:GetText();ownedSaveDelete.confirmationEntry=g_SelectedEntry
      end
    elseif not value and hasRetainedSaveMenuUi and ownedSaveDelete.callbackRole=='Save' then
      local name=controls.NameBox:GetText();local entry=ownedSaveOverwrite.find(name)
      if entry~=nil and entry==g_SelectedEntry then
        ownedSaveOverwrite.confirmation={name=name,path=entry.FileName,entry=entry,epoch=ownedSaveOverwrite.epoch}
      end
    end
    -- SetHide has not assigned target.hidden yet; only the newly captured
    -- grants may enable Yes at this point. Refresh revalidates live visibility.
    controls.Yes:SetDisabled(ownedSaveDelete.confirmationPath==nil and ownedSaveOverwrite.confirmation==nil)
  end
  if value then pullDown.invalidate(self) end
  if hasRetainedLoadMenuUi and not value and
    (target.attributes.ID=='DeleteConfirm' or target.attributes.ID=='ReferencedPackagesWindow') then pullDown.close() end
  if hasRetainedGameMenuUi and target.kind=='LuaContext' then
    assert(gameMenuChildren[target.attributes.ID] and target.parent==root and #target.children==0,
      'GameMenu requested an unregistered child context')
    if not value then
      if target.attributes.ID=='SaveMenu' then native('saveMenuOpen')
      elseif target.attributes.ID=='LoadMenu' then native('loadMenuOpen')
      elseif target.attributes.ID=='OptionsMenu_InGame' then native('menuOptionsOpen')
      elseif target.attributes.ID=='TouchControlsMenu' then native('touchHelpOpen')
      elseif target.attributes.ID=='SaveMapMenu' then native('mapMenuOpen')
      else gameMenuUnavailable(target.attributes.ID) end
    end
    assert(target.hidden,'An unconnected GameMenu child became visible')
    return
  end
  if hasRetainedSaveMenuUi then
    if target.kind=='LuaContext' then
      assert(target.attributes.ID=='SaveMapMenu' and target.parent==root and #target.children==0,
        'SaveMenu requested an unregistered child context')
      if not value then native('mapMenuOpen') end
      assert(target.hidden,'SaveMapMenu child declaration became visible in its parent VM')
      return
    end
    if target.attributes.ID=='CloudCheck' then value=true end
  end
  if (hasRetainedTreeUi or hasRetainedSocialPolicyUi or hasRetainedNotificationUi) and target.hidden==value then return end
  target.hidden=value
  if hasRetainedEconomicParentUi and target.kind=='LuaContext' then
    assert(target.attributes.ID=='EconomicGeneralInfo' or target.attributes.ID=='HappinessInfo',
      'Unregistered Economic child visibility target')
    -- Native code applies this in the other VM only after our callback unwinds.
    -- Repeated SetHide(false) is the stock parent's intentional refresh signal.
    native('economicChildHidden',target.attributes.ID,value)
  end
  if hasRetainedTreeUi or hasRetainedTechUi or hasRetainedCityUi or hasRetainedSocialPolicyUi or hasRetainedEconomicUi or hasRetainedNotificationUi or hasRetainedGameMenuUi or hasRetainedExitConfirmUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp' or popupKind=='MapMenu' then layoutDirty=true end
  if (hasRetainedTreeUi or hasRetainedTechUi or hasRetainedCityUi or hasRetainedSocialPolicyUi or hasRetainedEconomicUi or hasRetainedNotificationUi) and root then
    local parentVisible,parentHover=parentActivation(self)
    updateAnimations(self,parentVisible and not contextHidden,parentHover,frameTime())
  elseif hasRetainedPopupUi and root then
    updateAnimations(root,not contextHidden,true,frameTime())
  end
end
function methods:IsHidden() return state(self).hidden end
function methods:SetDisabled(value)
  assert(type(value)=='boolean','SetDisabled expects a boolean')
  local target=state(self)
  assert(buttonKind(target.kind) or (hasRetainedLoadMenuUi or popupKind=='MenuOptions') and target.kind=='PullDown' or
    popupKind=='MenuOptions' and target.kind=='Slider' and target.attributes.ID=='EffectsVolumeSlider',
    'SetDisabled requires a button control')
  if hasRetainedSaveMenuUi then
    local id=target.attributes.ID
    if id=='CloudCheck' then value=true
    elseif id=='Delete' and not value then value=not ownedSaveDelete.canDelete()
    elseif id=='Yes' and not value then value=not (ownedSaveDelete.confirmationPath~=nil and ownedSaveDelete.canDelete() or
      ownedSaveOverwrite.valid(ownedSaveOverwrite.confirmation))
    elseif id=='SaveButton' and not value then value=not saveMenuCanSave() end
  end
  if hasRetainedLoadMenuUi then
    local id=target.attributes.ID
    if id=='AutoCheck' or id=='CloudCheck' then value=true
    elseif id=='Delete' and not value then value=not ownedSaveDelete.canDelete()
    elseif id=='Yes' and not value then value=ownedSaveDelete.confirmationPath==nil or not ownedSaveDelete.canDelete()
    elseif id=='StartButton' and not value then value=not loadMenuCanLoad() end
  end
  target.disabled=value
  target.attributes.Disabled=value and '1' or '0'
  if value then pullDown.invalidate(self) end
end
function methods:IsDisabled() return state(self).disabled end
local function setLabelText(target,value)
  -- Stock ProductionPopup passes city population as a number. Convert finite
  -- numeric label input here; texture/tooltip identity contracts stay textual.
  if type(value)=='number' then value=tostring(finite(value)) end
  value=text(value)
  if (hasRetainedSaveMenuUi or popupKind=='MapMenu') and target.kind=='EditBox' then
    local chars=utf8Characters(value);local maximum=assert(tonumber(target.attributes.MaxLength))
    assert(maximum==32 and target.attributes.CallOnChar=='1','NameBox source contract changed')
    if #chars>maximum then
      local limited={};for index=1,maximum do limited[index]=chars[index].character end
      value=table.concat(limited)
    end
  end
  local before=target.label
  if hasRetainedSaveMenuUi and target.kind=='EditBox' and before~=value then
    ownedSaveDelete.clearConfirmation();ownedSaveDelete.clearDispatch();ownedSaveOverwrite.invalidate()
  end
  target.label=value
  local ok,err=true,nil
  if hasRetainedPopupUi then ok,err=pcall(measureProductionLabel,target) end
  if not ok then
    target.label=before
    error(string.format('UI label measurement failed [controlKey=%s kind=%q id=%q text="%s"]: %s',
      tostring(target.key or -1),tostring(target.kind or ''),
      tostring(target.attributes and target.attributes.ID or ''),escapedLabelContext(value),tostring(err)),0)
  end
  if active and anchor then
    if hasRetainedTreeUi or hasRetainedTechUi or hasRetainedCityUi or hasRetainedSocialPolicyUi or hasRetainedEconomicUi or hasRetainedNotificationUi then
      -- Stock tech lists and policy refreshes update a batch of labels.
      -- Measure each label now, then anchor at event/input/snapshot boundaries.
      layoutDirty=true
    else anchor(root) end
  end
end
function methods:SetText(value) setLabelText(state(self),value) end
function methods:ClearString()
  local target=state(self)
  assert((hasRetainedSaveMenuUi or popupKind=='MapMenu') and target.kind=='EditBox' and target.attributes.ID=='NameBox',
    'ClearString requires the original SaveMenu NameBox')
  setLabelText(target,'');target.caret=0
end
function methods:TakeFocus()
  local target=state(self)
  assert((hasRetainedSaveMenuUi or popupKind=='MapMenu') and active and not contextHidden and timer==0 and
    target.kind=='EditBox' and target.attributes.ID=='NameBox',
    'TakeFocus requires the live original SaveMenu NameBox')
  setEditFocus(self);target.caret=#utf8Characters(target.label)
end
function methods:SetString(value)
  local target=state(self)
  assert(hasRetainedSocialPolicyUi and target.kind=='Label',
    'SetString requires a SocialPolicy Label control')
  setLabelText(target,value)
end
function methods:GetText() return state(self).label end
function methods:SetToolTipString(value)
  -- Original UnitPanel clears the city portrait tooltip with nil.
  if value==nil then value='' end
  state(self).tooltip=text(value)
end
function methods:SetToolTipCallback(callback)
  assert((hasRetainedUnitUi or hasRetainedTopPanelUi) and type(callback)=='function',
    'SetToolTipCallback requires a retained UnitPanel or TopPanel callback')
  state(self).toolTipCallback=callback
end
function methods:GetVoid1() return state(self).void1 end
function methods:LocalizeAndSetToolTip(key,...)
  state(self).tooltip=text(native('locale',key,...))
end
function methods:LocalizeAndSetText(key,...)
  local target=state(self)
  local localized=native('locale',key,...)
  if hasRetainedPopupUi then setLabelText(target,localized)
  else target.label=text(localized) end
end
function methods:SetTexture(value) state(self).texture=text(value) end
function methods:UnloadTexture()
  local target=state(self)
  assert((hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MapMenu') and target.kind=='Image' and target.attributes.ID=='LargeMapImage',
    'UnloadTexture requires the original save/load map image')
  target.texture='';target.textureX=0;target.textureY=0
end
function methods:SetTextureOffsetVal(x,y)
  local value=state(self);value.textureX=finite(x);value.textureY=finite(y)
end
function methods:SetTextureOffset(value) self:SetTextureOffsetVal(value.x,value.y) end
function methods:SetColor(value) state(self).color=colorCopy(value) end
function methods:SetColorVal(r,g,b,a)
  assert(hasRetainedPantheonUi,'SetColorVal is enabled for the original Pantheon rows only')
  for _,value in ipairs({r,g,b,a}) do assert(finite(value)>=0 and value<=1,'Color component is outside 0..1') end
  assert(r~=nil and g~=nil and b~=nil and a~=nil,'SetColorVal requires four components')
  self:SetColor({x=r,y=g,z=b,w=a})
end
function methods:SetFGColor(value)
  local target=state(self)
  assert(hasRetainedEconomicGeneralUi and target.kind=='Bar' and target.attributes.ID=='HealthBar',
    'SetFGColor requires the original EconomicGeneral HealthBar')
  local color=colorCopy(value)
  for _,component in pairs(color) do assert(component>=0 and component<=1,'Bar color is outside 0..1') end
  target.fgColor=color
end
function methods:SetAlpha(value)
  value=finite(value);assert(value>=0 and value<=1,'SetAlpha expects a value in 0..1')
  state(self).alpha=value
end
function methods:SetFontByName(name)
  assert(hasRetainedUnitUi,'SetFontByName is only retained for UnitPanel')
  name=text(name);assert(name~='','SetFontByName requires a font name')
  local value=state(self);value.font=name;value.attributes.Font=name
  measureProductionLabel(value)
  layoutDirty=true
end
function methods:SetSizeVal(w,h)
  assert(finite(w)>=0 and finite(h)>=0, 'Negative control size')
  local value=state(self);value.w=w;value.h=h
  if pullDown.owners[self] then pullDown.measure(self) end
end
function methods:GetSize()
  local value=state(self);return {x=value.w,y=value.h}
end
function methods:GetSizeVal() local value=state(self);return value.w,value.h end
function methods:GetSizeX() return state(self).w end
function methods:GetSizeY() return state(self).h end
function methods:GetOffsetX() return state(self).offsetX end
function methods:GetOffsetY() return state(self).offsetY end
function methods:GetOffsetVal() local value=state(self);return value.offsetX,value.offsetY end
function methods:SetSize(size)
  assert(type(size)=='table','SetSize expects a vector')
  local value=state(self)
  local width=size.x==nil and value.w or finite(size.x)
  local height=size.y==nil and value.h or finite(size.y)
  assert(width>=0 and height>=0 and (size.x~=nil or size.y~=nil), 'Invalid partial control size')
  value.w=width;value.h=height
  if pullDown.owners[self] then pullDown.measure(self) end
end
function methods:SetSizeY(height)
  local value=state(self);height=finite(height)
  assert(height>=0,'Negative control height');value.h=height
  if pullDown.owners[self] then pullDown.measure(self) end
end
function methods:SetSizeX(width)
  local value=state(self);width=finite(width)
  assert(width>=0,'Negative control width');value.w=width
  if pullDown.owners[self] then pullDown.measure(self) end
  if active and hasRetainedTreeUi then anchor(root) end
end
function methods:SetOffsetVal(x,y)
  local value=state(self);value.offsetX=finite(x);value.offsetY=finite(y)
end
function methods:SetAnchor(anchorValue)
  assert(hasRetainedUnitUi,'SetAnchor is only retained for UnitPanel')
  anchorValue=text(anchorValue)
  local x,y=anchorValue:match('^(%a)[,.](%a)$')
  assert(x and y and (x:upper()=='L' or x:upper()=='C' or x:upper()=='R') and
    (y:upper()=='T' or y:upper()=='C' or y:upper()=='B'),'Unsupported UnitPanel anchor')
  local value=state(self);value.anchor=x:upper()..','..y:upper();value.attributes.Anchor=value.anchor
  if anchor then anchor(self) end
end
function methods:GetScrollValue()
  local value=state(self)
  assert(value.kind=='ScrollPanel','GetScrollValue requires a scroll panel')
  return value.attributes.Vertical=='1' and value.scrollY or value.scrollX
end
function methods:GetRatio()
  local value=state(self)
  assert(hasRetainedNotificationUi and value.kind=='ScrollPanel' and value.attributes.ID=='SmallScrollPanel',
    'GetRatio requires the original notification scroll panel')
  local content=assert(value.attributes.Vertical=='1' and value.contentH,
    'Notification scroll content has not been measured')
  return content<=value.h and 1 or value.h/content
end
function methods:SetScrollValue(offset)
  local value=state(self)
  assert(value.kind=='ScrollPanel','SetScrollValue requires a scroll panel')
  offset=finite(offset)
  local horizontal=value.attributes.Vertical~='1'
  local content=horizontal and value.contentW or value.contentH
  local viewportSize=horizontal and value.w or value.h
  assert(content~=nil,'ScrollPanel content size has not been calculated')
  local maximum=math.max(0,content-viewportSize)
  assert(offset>=0 and offset<=maximum,'ScrollPanel value is outside its measured range')
  if horizontal then value.scrollX=offset else value.scrollY=offset end
  if active then anchor(root) end
end
function methods:SetPercent(value)
  value=finite(value)
  state(self).percent=value
end
function methods:SetPercents(value,plus)
  value=finite(value);plus=finite(plus)
  local target=state(self);target.percent=value;target.percentPlus=plus
end
function methods:Play()
  local value=state(self);local animation=value.animation
  assert(animation and (value.kind=='AlphaAnim' or value.kind=='ScrollAnim'),'Play requires an animation control')
  local now=frameTime();animation.manuallyStopped=false
  if animation.once and animation.completed then
    animation.phase=0;animation.completed=false;animation.activationStartTime=now
  end
  if not animation.running then animation.running=true;animation.startTime=now end
end
function methods:Stop()
  local value=state(self);local animation=value.animation
  assert(animation and (value.kind=='AlphaAnim' or value.kind=='ScrollAnim'),'Stop requires an animation control')
  local now=frameTime();animation.phase=animationElapsed(animation,now);animation.running=false;animation.manuallyStopped=true
end
function methods:SetToBeginning()
  local value=state(self);local animation=value.animation
  assert(animation and (value.kind=='AlphaAnim' or value.kind=='ScrollAnim'),'SetToBeginning requires an animation control')
  animation.phase=0;animation.startTime=frameTime();animation.running=false;animation.manuallyStopped=true
  if animation.once then animation.completed=false;animation.activationStartTime=animation.startTime end
end
function methods:SetVoid1(value) state(self).void1=value end
function methods:SetVoid2(value) state(self).void2=value end
function methods:SetVoids(first,second)
  local value=state(self);value.void1=first;value.void2=second
end
function methods:BranchResetAnimation()
  assert(hasRetainedNotificationUi and state(self).kind=='Container',
    'BranchResetAnimation requires an original notification instance root')
  local now=frameTime()
  local function reset(handle)
    local value=state(handle)
    if value.animation then
      value.animation.phase=0;value.animation.startTime=now
      value.animation.running=false;value.animation.manuallyStopped=false
    end
    for _,child in ipairs(value.children) do reset(child) end
  end
  reset(self)
  local visible,hover=parentActivation(self)
  updateAnimations(self,visible and not contextHidden,hover,now)
  layoutDirty=true
end
function methods:RegisterCallback(event,callback)
  local value=state(self)
  if (hasRetainedSaveMenuUi or popupKind=='MapMenu') and value.kind=='EditBox' then
    assert(value.attributes.ID=='NameBox' and type(event)=='function' and callback==nil,
      'NameBox callback requires the original one-function signature')
    value.editCallback=event;return
  end
  assert(type(event)=='string' and type(callback)=='function', 'Invalid UI callback')
  assert(buttonKind(value.kind), 'This control does not support button callbacks')
  assert(event==Mouse.eLClick or event==Mouse.eRClick or
    hasRetainedNotificationUi and event==Mouse.eLDblClick, 'Unsupported mouse callback event')
  value.callbacks[event]=callback
end
function methods:SetValue(amount)
  local value=state(self)
  assert(popupKind=='MenuOptions' and value.kind=='Slider' and value.attributes.ID=='EffectsVolumeSlider',
    'SetValue requires the supported original effects slider')
  amount=finite(amount);assert(amount>=0 and amount<=1,'Slider value is outside its normalized range')
  value.sliderValue=amount;layoutDirty=true
end
function methods:GetValue()
  local value=state(self)
  assert(popupKind=='MenuOptions' and value.kind=='Slider' and value.attributes.ID=='EffectsVolumeSlider',
    'GetValue requires the supported original effects slider')
  return value.sliderValue or 0
end
function methods:RegisterSliderCallback(callback)
  local value=state(self)
  assert(popupKind=='MenuOptions' and value.kind=='Slider' and value.attributes.ID=='EffectsVolumeSlider' and
    type(callback)=='function','Slider callback requires the supported original effects slider')
  value.sliderCallback=callback
end
function methods:ClearCallback(event)
  local value=state(self)
  assert(buttonKind(value.kind), 'This control does not support callbacks')
  assert(event==Mouse.eLClick or event==Mouse.eRClick, 'Unsupported mouse callback event')
  value.callbacks[event]=nil
end
function methods:SetCheck(checked)
  local value=state(self)
  assert((hasRetainedCityUi or hasRetainedSocialPolicyUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp') and (value.kind=='CheckBox' or value.kind=='RadioButton') and type(checked)=='boolean',
    'SetCheck requires a check/radio boolean')
  if hasRetainedSaveMenuUi then assert(value.attributes.ID=='CloudCheck' and not checked,'Steam Cloud is not connected') end
  if hasRetainedLoadMenuUi then assert((value.attributes.ID=='AutoCheck' or value.attributes.ID=='CloudCheck') and not checked,
    'Automatic/cloud save filters are not connected to the owned local catalog') end
  if checked and value.kind=='RadioButton' then
    local group=assert(value.attributes.RadioGroup,'RadioButton is missing its source group')
    for _,other in pairs(states) do
      if other.kind=='RadioButton' and other.attributes.RadioGroup==group then other.checked=false end
    end
  end
  value.checked=checked
end
function methods:IsChecked() return state(self).checked end
function methods:RegisterCheckHandler(callback)
  local value=state(self)
  assert((hasRetainedCityUi or hasRetainedSocialPolicyUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp') and (value.kind=='CheckBox' or value.kind=='RadioButton') and type(callback)=='function',
    'Check handler requires a checkbox or radio control')
  value.checkHandler=callback
  value.callbacks[Mouse.eLClick]=function()
    self:SetCheck(value.kind=='RadioButton' or not value.checked)
    callback(value.checked)
  end
end
function methods:SortChildren(compare)
  local value=state(self)
  assert((hasRetainedCityUi or hasRetainedEconomicGeneralUi and value.attributes.ID=='MainStack' or
    hasRetainedLoadMenuUi and value.attributes.ID=='LoadFileButtonStack') and
    value.kind=='Stack' and type(compare)=='function','SortChildren requires an original sortable stack comparator')
  table.sort(value.children,compare)
  self:CalculateSize();layoutDirty=true
end
function methods:SetWorldPosition(position)
  local value=state(self)
  assert(hasRetainedCityUi and value.kind=='WorldAnchor' and type(position)=='table','World position requires a CityView WorldAnchor')
  value.worldPosition={x=finite(position.x),y=finite(position.y),z=finite(position.z)}
  if position.gridX~=nil then
    assert(position.gridX==math.floor(position.gridX) and position.gridY==math.floor(position.gridY),
      'World anchor requires its stable grid identity')
    value.worldGrid={x=position.gridX,y=position.gridY,offsetX=finite(position.offsetX),
      offsetY=finite(position.offsetY),offsetZ=finite(position.offsetZ)}
  else value.worldGrid=nil end
  layoutDirty=true
end
function methods:DestroyChild(child)
  local own,other=state(self),state(child)
  assert(other.parent==self, 'UI child belongs to another parent')
  pullDown.invalidate(child,true)
  local function destroy(handle)
    for _,entry in ipairs(state(handle).children) do destroy(entry) end
    pullDown.owners[handle]=nil
    states[handle]=nil
  end
  for i,entry in ipairs(own.children) do
    if entry==child then table.remove(own.children,i);destroy(child);return end
  end
  error('UI child is not attached')
end
function methods:DestroyAllChildren()
  local own=state(self)
  assert(own.kind=='Stack' and (hasRetainedTradeRouteUi and own.attributes.ID=='MainStack' or
    hasRetainedEconomicChildUi and economicDynamicStacks[own.attributes.ID]),
    'DestroyAllChildren requires an original TradeRoute or Economic dynamic stack')
  while #own.children>0 do self:DestroyChild(own.children[#own.children]) end
  self:CalculateSize()
end
function methods:ReleaseChild(child)
  assert(hasRetainedNotificationUi and state(self).kind=='Stack' and state(self).attributes.ID=='SmallStack',
    'ReleaseChild requires the original notification dynamic stack')
  self:DestroyChild(child)
  layoutDirty=true
end
function methods:CalculateSize()
  local value=state(self)
  local direction=value.attributes.StackGrowth
  assert(value.kind=='Stack' and (direction=='B' or direction=='Bottom' or direction=='T' or
    direction=='Top' or direction=='L' or direction=='Left' or direction=='R' or direction=='Right'),
    'Unsupported dynamic UI sizing')
  local horizontal=(direction=='L' or direction=='Left' or direction=='R' or direction=='Right')
  local main,cross,count=0,0,0
  local padding=tonumber(value.attributes.Padding or '0')
  -- GameMenu's original icon row uses negative padding to overlap its frames.
  assert(padding and (hasRetainedTechUi or hasRetainedGameMenuUi or padding>=0 or
    (hasRetainedTechAwardUi and value.attributes.ID=='BonusStack') or
    (hasRetainedNotificationUi and value.attributes.ID=='SmallStack' and padding==-6)), 'Invalid stack padding')
  if hasRetainedDeclareWarUi and horizontal and value.attributes.WrapGrowth=='Down' then
    local wrapWidth=finite(tonumber(value.attributes.WrapWidth))
    assert(wrapWidth>0,'DeclareWar horizontal wrapping requires a positive WrapWidth')
    local cursorX,cursorY,rowHeight,maxWidth,countRows=0,0,0,0,0
    for _,child in ipairs(value.children) do
      local row=state(child);row.stackX=nil;row.stackY=nil
      if not row.hidden then
        if cursorX>0 and cursorX+row.w>wrapWidth then
          cursorY=cursorY+rowHeight+padding;cursorX=0;rowHeight=0
        end
        row.stackX=cursorX;row.stackY=cursorY
        cursorX=cursorX+row.w+padding
        rowHeight=math.max(rowHeight,row.h)
        maxWidth=math.max(maxWidth,cursorX-padding)
        countRows=countRows+1
      end
    end
    value.w=maxWidth
    value.h=countRows>0 and cursorY+rowHeight or 0
    return
  end
  local captureLeadingOffsets=hasRetainedCaptureUi and value.attributes.ID=='ButtonStack' and
    not horizontal and (direction=='B' or direction=='Bottom')
  -- CityView stack child offsets are leading spacing in the stock layout:
  -- reserve positive offsets in both the measured extent and the next slot.
  -- Keep negative offsets as visual adjustments; several stock children use
  -- them to overlap their own slot intentionally.
  local cityLeadingOffsets=hasRetainedCityUi and not horizontal and
    (direction=='B' or direction=='Bottom')
  local visible={}
  for _,child in ipairs(value.children) do
    local row=state(child)
    if hasRetainedPopupUi then row.stackX=nil;row.stackY=nil end
    if not row.hidden then
      if count>0 then main=main+padding end
      if horizontal then
        if cityLeadingOffsets then main=main+math.max(0,row.offsetX) end
        main=main+row.w;cross=math.max(cross,row.h)
      else
        if captureLeadingOffsets then
          assert(row.offsetY>=0 and row.h>=0,'Captured-city ButtonStack requires nonnegative row offset and height')
          main=main+row.offsetY
        elseif cityLeadingOffsets then
          main=main+math.max(0,row.offsetY)
        end
        main=main+row.h;cross=math.max(cross,row.w)
      end
      visible[#visible+1]=row
      count=count+1
    end
  end
  local cursor=0
  for _,row in ipairs(visible) do
    if horizontal then
      row.stackX=(direction=='L' or direction=='Left') and (main-cursor-row.w) or cursor
      cursor=cursor+row.w+padding
    else
      row.stackY=(direction=='T' or direction=='Top') and (main-cursor-row.h) or cursor
      cursor=cursor+row.h+padding+
        (captureLeadingOffsets and row.offsetY or cityLeadingOffsets and math.max(0,row.offsetY) or 0)
    end
  end
  if horizontal then value.w=main;value.h=cross else value.w=cross;value.h=main end
end
function methods:DoAutoSize()
  local value=state(self)
  if hasRetainedTopPanelUi then
    assert(value.kind=='Grid' and value.attributes.ID=='TopPanelMouseover',
      'TopPanel tooltip auto-size requires the original TopPanelMouseover Grid')
    value.autoSizeRequested=true
    return
  end
  if hasRetainedTechAwardUi then
    assert(value.kind=='Grid' and value.attributes.ID=='OuterGrid' and
      value.attributes.Size=='560,530' and value.attributes.Padding=='20,50',
      'TechAward auto-size requires the original 560x530 OuterGrid and Padding=20,50')
    local content
    for _,child in ipairs(value.children) do
      local row=state(child)
      if row.kind=='Stack' and not row.attributes.ID then
        assert(not content,'TechAward OuterGrid has multiple unlabelled content stacks')
        content=child
      end
    end
    content=assert(content,'TechAward OuterGrid content stack is missing')
    local contentRow=state(content)
    assert(contentRow.attributes.StackGrowth=='Bottom' and contentRow.attributes.Size=='0,0',
      'TechAward content stack differs from the original size-to-content contract')
    local function sizeAutoStacks(handle)
      local row=state(handle)
      for _,child in ipairs(row.children) do sizeAutoStacks(child) end
      if row.kind=='Stack' and row.autoSizeStack then methods.CalculateSize(handle) end
    end
    sizeAutoStacks(content)
    local px,py=pair(value.attributes.Padding)
    local baseW,baseH=pair(value.attributes.Size)
    assert(baseW==560 and baseH==530 and px==20 and py==50 and contentRow.offsetY>=0,
      'TechAward original auto-size base or padding changed')
    local contentW=math.max(baseW,contentRow.w+math.abs(contentRow.offsetX)+2*px)
    local contentH=math.max(baseH,contentRow.h+contentRow.offsetY+2*py)
    assert(contentW<=viewport.w and contentH<=viewport.h,
      'TechAward auto-size content exceeds the original viewport bounds')
    value.w=contentW;value.h=contentH
    if active then anchor(root) end
    return
  end
  assert(hasRetainedCaptureUi and value.kind=='Grid' and value.attributes.ID=='ButtonStackFrame',
    'Auto-size requires the original GenericPopup content frame')
  local content=assert(controls.ButtonStack,'GenericPopup content stack is missing')
  local row=state(content)
  assert(row.parent==self and row.kind=='Stack','GenericPopup auto-size content is not attached')
  local px,py=pair(value.attributes.Padding)
  local baseW,baseH=pair(value.attributes.Size)
  value.w=math.max(baseW,row.w+math.abs(row.offsetX)+2*px)
  value.h=math.max(baseH,row.h+row.offsetY+py)
  if active then anchor(root) end
end
anchor=function(handle)
  if hasRetainedLoadMenuUi and handle==root then
    pullDown.validate()
    for owner in pairs(pullDown.owners) do pullDown.measure(owner) end
  end
  if hasRetainedNotificationUi and handle==root then notificationLayoutClock=frameTime() end
  if hasRetainedDeclareWarUi and handle==root and active then
    local function measureVisiblePending(control,parentVisible)
      local row=state(control)
      local visible=parentVisible and not row.hidden
      if visible and row.textMeasurementPending then measureProductionLabel(row) end
      for _,child in ipairs(row.children) do measureVisiblePending(child,visible) end
    end
    measureVisiblePending(root,not contextHidden)
  end
  if hasRetainedSocialPolicyUi and handle==root and controls.SocialPolicyPane then
    -- SocialPolicyPane's original zero-size Bottom stack contains two
    -- horizontal policy rows. Measure its nested auto-size stacks from the
    -- leaves upward before anchoring so the second row reserves the first
    -- row's XML-derived height instead of starting at the same Y position.
    local pane=state(controls.SocialPolicyPane)
    local rows
    for _,child in ipairs(pane.children) do
      local candidate=state(child)
      if candidate.kind=='Stack' and candidate.autoSizeStack and
         candidate.attributes.StackGrowth=='Bottom' then
        assert(not rows,'SocialPolicy pane has multiple original policy row stacks')
        rows=child
      end
    end
    rows=assert(rows,'SocialPolicy original auto-size policy rows are missing')
    local measuredRows=0
    for _,child in ipairs(state(rows).children) do
      local row=state(child)
      local direction=row.attributes.StackGrowth
      if row.kind=='Stack' and row.autoSizeStack and
         (direction=='R' or direction=='Right' or direction=='L' or direction=='Left') then
        methods.CalculateSize(child)
        measuredRows=measuredRows+1
      end
    end
    assert(measuredRows==2,'SocialPolicy pane must retain its original two horizontal policy rows')
    methods.CalculateSize(rows)
  end
  if (hasRetainedCityUi or hasRetainedEconomicUi or hasRetainedNotificationUi or hasRetainedGameMenuUi or hasRetainedSaveMenuUi or hasRetainedTopPanelUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp' or popupKind=='MapMenu') and handle==root then
    -- Size-less stacks need their visible child extents before anchoring,
    -- including GameMenu's button/icon rows and TopPanel's centered captions.
    -- Measure from the leaves upward, then position the unchanged tree.
    local function sizeChildren(control)
      local row=state(control)
      for _,child in ipairs(row.children) do sizeChildren(child) end
      if row.autoSizeStack then methods.CalculateSize(control) end
    end
    sizeChildren(root)
  end
  local value=state(handle)
  if (hasRetainedTechUi or hasRetainedCityUi or hasRetainedNotificationUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions') and
    value.kind=='ScrollBar' and value.parent and state(value.parent).kind=='ScrollPanel' and
    (not (hasRetainedLoadMenuUi or popupKind=='MenuOptions') or pullDown.isChrome(value,state(value.parent))) then
    -- The TechPopup declares its vertical slider without a size. The owned
    -- frontend retains it against the parent's real viewport; stock sizing
    -- equivalence remains unverified.
    value.h=state(value.parent).h
  end
  if hasRetainedNotificationUi and value.kind=='SlideAnim' then
    local owner=assert(value.parent and state(value.parent))
    assert(owner.kind=='Container' and owner.attributes.Size=='80,80',
      'Original NotificationSlide requires its source-sized container')
    -- The retained transparent wrapper follows the actual original container;
    -- the XML remains size-less and retail wrapper geometry is not asserted.
    value.w=owner.w;value.h=owner.h
  end
  if hasRetainedCityUi and value.kind=='WorldAnchor' and value.worldPosition then
    value.x=value.worldPosition.x;value.y=value.worldPosition.y-value.worldPosition.z
    for _,child in ipairs(value.children) do anchor(child) end
    return
  end
  if hasRetainedPopupUi and value.kind=='ShowOnMouseOver' then
    local owner=value.parent
    while owner do
      local candidate=state(owner)
      if candidate.kind=='Button' or candidate.kind=='GridButton' or
         candidate.kind=='DownButton' or candidate.kind=='UpButton' then break end
      owner=candidate.parent
    end
    assert(owner,'ShowOnMouseOver requires an owning button')
    local frame=state(owner)
    value.x=frame.x;value.y=frame.y;value.w=frame.w;value.h=frame.h
    for _,child in ipairs(value.children) do anchor(child) end
    return
  end
  if hasRetainedSocialPolicyUi and value.kind=='HideOnMouseOver' then
    local owner=value.parent
    assert(owner and state(owner).kind=='Box','SocialPolicy HideOnMouseOver requires its original owning Box')
    local frame=state(owner)
    value.x=frame.x;value.y=frame.y;value.w=frame.w;value.h=frame.h
    for _,child in ipairs(value.children) do anchor(child) end
    return
  end
  if hasRetainedPopupUi and value.kind=='Stack' then
    -- Stock button/header stacks without Size inherit their child extents.
    -- In TradeRoute the 45px column-header row must have that height before
    -- center-anchoring its buttons, or they overlap the tabs above it.
    if (hasRetainedLeaderUi or hasRetainedCityUi or hasRetainedTradeRouteUi or hasRetainedEconomicUi or hasRetainedNotificationUi) and not value.explicitSize then
      methods.CalculateSize(handle)
    end
    local direction=value.attributes.StackGrowth
    local horizontal=(direction=='L' or direction=='Left' or direction=='R' or direction=='Right')
    assert(horizontal or direction=='B' or direction=='Bottom' or direction=='T' or direction=='Top',
      'Unsupported popup stack growth: '..tostring(direction))
    local padding=finite(tonumber(value.attributes.Padding or '0'))
    assert(hasRetainedPopupUi or padding>=0,'Invalid popup stack padding')
    local captureLeadingOffsets=hasRetainedCaptureUi and value.attributes.ID=='ButtonStack' and
      not horizontal and (direction=='B' or direction=='Bottom')
    local cityLeadingOffsets=hasRetainedCityUi and not horizontal and
      (direction=='B' or direction=='Bottom')
    if hasRetainedDeclareWarUi and horizontal and value.attributes.WrapGrowth=='Down' then
      methods.CalculateSize(handle)
    else
    local cursor=0
    for _,child in ipairs(value.children) do
      local row=state(child);row.stackX=nil;row.stackY=nil
      if not row.hidden then
        local extent=horizontal and row.w or row.h
        if direction=='L' or direction=='Left' then
          row.stackX=value.w-cursor-extent
        elseif direction=='R' or direction=='Right' then
          row.stackX=cursor
        elseif direction=='T' or direction=='Top' then
          row.stackY=value.h-cursor-extent
        else
          row.stackY=cursor
        end
        if captureLeadingOffsets then
          assert(row.offsetY>=0 and extent>=0,'Captured-city ButtonStack requires nonnegative row offset and extent')
        end
        local leadingOffset=cityLeadingOffsets and math.max(0,horizontal and row.offsetX or row.offsetY) or 0
        cursor=cursor+extent+padding+(captureLeadingOffsets and row.offsetY or leadingOffset)
      end
    end
    end
  end
  local parent=value.parent and state(value.parent) or {x=0,y=0,w=viewport.w,h=viewport.h}
  local ax,ay=(value.attributes.Anchor or 'L,T'):match('^(%a)[,.](%a)$')
  assert(ax and ay, 'Unsupported UI anchor')
  ax,ay=ax:upper(),ay:upper()
  local sx,sy=(value.attributes.AnchorSide or 'I,I'):match('^(%a)[,.](%a)$')
  assert(sx and sy, 'Unsupported UI anchor side')
  sx,sy=sx:upper(),sy:upper()
  local x=value.offsetX
  if ax=='C' then x=(parent.w-value.w)/2+x
  elseif ax=='R' then x=parent.w-value.w-x
  else assert(ax=='L', 'Unsupported horizontal anchor') end
  if sx=='O' then
    -- Stock ProductionPopup's Food label combines C,C with O.I. Center has
    -- no outside edge; keep its computed center in this frontend policy.
    if ax~='C' then x=ax=='R' and parent.w+value.offsetX or -value.w-value.offsetX end
  else assert(sx=='I', 'Unsupported horizontal anchor side') end
  local y=value.offsetY
  if ay=='C' then y=(parent.h-value.h)/2+y
  elseif ay=='B' then y=parent.h-value.h-y
  else assert(ay=='T', 'Unsupported vertical anchor') end
  if sy=='O' then
    if ay~='C' then y=ay=='B' and parent.h+value.offsetY or -value.h-value.offsetY end
  else assert(sy=='I', 'Unsupported vertical anchor side') end
  local parentStack=hasRetainedPopupUi and parent.kind=='Stack' and parent.attributes.StackGrowth or nil
  if parentStack=='L' or parentStack=='Left' or parentStack=='R' or parentStack=='Right' then
    value.x=parent.x+(value.stackX or 0)+value.offsetX
  else
    value.x=parent.x+x
  end
  if parentStack=='B' or parentStack=='Bottom' or parentStack=='T' or parentStack=='Top' or
    (hasRetainedDeclareWarUi and parentStack and parentStack~='B' and parentStack~='Bottom' and
     parentStack~='T' and parentStack~='Top' and value.stackY~=nil) then
    value.y=parent.y+(value.stackY or 0)+value.offsetY
  else
    value.y=parent.y+y
  end
  if value.parent and parent.kind=='ScrollPanel' and value.kind~='ScrollBar' and
     value.kind~='UpButton' and value.kind~='DownButton' then
    value.x=value.x-parent.scrollX;value.y=value.y-parent.scrollY
  end
  if hasRetainedNotificationUi and value.kind=='SlideAnim' then
    local dx,dy=notificationSlide(value,notificationLayoutClock or frameTime())
    value.x=value.x+dx;value.y=value.y+dy
  end
  if (hasRetainedLoadMenuUi or popupKind=='MenuOptions') and value.originalDataKind=='GridData' then
    -- The original popup anchors below its owning button. Keep that anchor
    -- declaration and contain the owned frontend overlay within its viewport.
    value.x=clamp(value.x,0,math.max(0,viewport.w-value.w))
    value.y=clamp(value.y,0,math.max(0,viewport.h-value.h))
  end
  for _,child in ipairs(value.children) do anchor(child) end
  if handle==root then
    if hasRetainedCityUi or hasRetainedSocialPolicyUi or hasRetainedEconomicUi or hasRetainedNotificationUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MapMenu' then
      for control,row in pairs(states) do
        if row.kind=='ScrollPanel' and not pullDown.deferPackageScroll(control,row) then
          measureScrollContent(control)
          -- The installed DX11 ScrollPanel starts with auto mode enabled;
          -- only an explicit false XML value disables it. Its size pass hides
          -- the three scrollbar decorations when there is no scroll range.
          -- Apply the verified omitted-attribute case to the original policy
          -- panels without changing their XML dimensions or input viewport.
          if row.attributes.AutoScrollBar=='1' or
             ((hasRetainedSocialPolicyUi or hasRetainedEconomicUi or hasRetainedNotificationUi) and row.attributes.AutoScrollBar==nil) then
            local overflowing=row.attributes.Vertical=='1' and row.contentH>row.h or
              row.attributes.Vertical~='1' and row.contentW>row.w
            for _,child in ipairs(row.children) do
              local item=state(child)
              if item.kind=='ScrollBar' or item.kind=='UpButton' or item.kind=='DownButton' then
                item.hidden=not overflowing
              end
            end
          end
          anchor(control)
        end
      end
    end
    layoutDirty=false
  end
end
local function flushLayout()
  ownedSaveDelete.refreshControls()
  pullDown.validate()
  if layoutDirty and active and root and anchor then
    anchor(root)
    layoutDirty=false
  end
end
function methods:ReprocessAnchoring() anchor(self) end
measureScrollContent=function(handle)
  local value=state(handle)
  assert(value.kind=='ScrollPanel', 'Internal size requires a scroll panel')
  local width,height=0,0
  for _,child in ipairs(value.children) do
    local item=state(child)
    if not item.hidden and item.kind~='ScrollBar' and
       not (item.kind=='UpButton' or item.kind=='DownButton') then
      if hasRetainedTreeUi and value.attributes.Vertical=='0' then
        width=math.max(width,item.offsetX+item.w)
        height=math.max(height,item.offsetY+item.h)
      else
        width=math.max(width,item.w+item.offsetX);height=math.max(height,item.h+item.offsetY)
      end
    end
  end
  value.contentW=width;value.contentH=height
  value.scrollX=clamp(value.scrollX,0,math.max(0,width-value.w))
  value.scrollY=clamp(value.scrollY,0,math.max(0,height-value.h))
end
function methods:CalculateInternalSize()
  measureScrollContent(self)
  if active and hasRetainedPopupUi then anchor(root) end
end

local function invokeCallback(handle,event)
  local value=state(handle);local callback=value.callbacks[event]
  if type(callback)~='function' then return false end
  if hasRetainedSaveMenuUi or hasRetainedLoadMenuUi then
    if ownedSaveDelete.callbackRole~=nil then return false end
    local id=value.attributes.ID
    if id=='Delete' then
      if event~=Mouse.eLClick or callback~=OnDelete or not ownedSaveDelete.canDelete() then
        handle:SetDisabled(true);return false
      end
      ownedSaveDelete.callbackRole='Delete'
    elseif hasRetainedSaveMenuUi and id=='SaveButton' then
      if event~=Mouse.eLClick or callback~=OnSave or not saveMenuCanSave() then
        handle:SetDisabled(true);return false
      end
      ownedSaveOverwrite.beginSave()
    elseif id=='Yes' then
      if event~=Mouse.eLClick or callback~=OnYes or controls.DeleteConfirm:IsHidden() then
        handle:SetDisabled(true);return false
      end
      if ownedSaveDelete.confirmationValid() and ownedSaveOverwrite.confirmation==nil then
        ownedSaveDelete.dispatchPath=ownedSaveDelete.confirmationPath
        ownedSaveDelete.dispatchName=ownedSaveDelete.confirmationName
        ownedSaveDelete.dispatchEntry=ownedSaveDelete.confirmationEntry
        ownedSaveDelete.clearConfirmation();ownedSaveDelete.callbackRole='Yes'
      elseif hasRetainedSaveMenuUi and ownedSaveOverwrite.armed() and ownedSaveDelete.confirmationPath==nil then
        ownedSaveOverwrite.dispatch=ownedSaveOverwrite.confirmation;ownedSaveOverwrite.confirmation=nil
        ownedSaveDelete.callbackRole='OverwriteYes'
      else handle:SetDisabled(true);return false end
    end
  end
  if hasRetainedTopPanelUi then topPanelCallbackDepth=topPanelCallbackDepth+1 end
  local ok,err
  if hasRetainedEconomicChildUi then ok,err=pcall(callback,value.void1,value.void2,handle)
  else ok,err=pcall(callback,value.void1,value.void2) end
  if hasRetainedSaveMenuUi or hasRetainedLoadMenuUi then
    ownedSaveOverwrite.endSave(ok)
  end
  if value.pullDownEntryOwner then pullDown.close(value.pullDownEntryOwner) end
  if hasRetainedTopPanelUi then
    topPanelCallbackDepth=topPanelCallbackDepth-1
    if topPanelCallbackDepth==0 and pendingTopPanelPopup then
      local request=pendingTopPanelPopup;pendingTopPanelPopup=nil
      if not ok then error(err,0) end
      native('queueTopPanelPopup',request.Type,request.Data2)
    end
  end
  if not ok then error(err,0) end
  if hasRetainedGameMenuUi then clearGameMenuNotice() end
  if hasRetainedSaveMenuUi and controls.SaveButton then
    controls.SaveButton:SetDisabled(not saveMenuCanSave())
  end
  return true
end

local function flushTopPanelPopupRequest()
  if hasRetainedTopPanelUi and topPanelCallbackDepth==0 and pendingTopPanelPopup then
    local request=pendingTopPanelPopup;pendingTopPanelPopup=nil
    native('queueTopPanelPopup',request.Type,request.Data2)
  end
end

-- Event objects keep handler snapshots so add/remove inside a dispatch affects
-- the next dispatch, not the current one. Unknown names are deliberately errors.
Events={}
local function event(name)
  local handlers={}
  local result={}
  function result.Add(fn)
    assert(type(fn)=='function', 'UI listener must be a function')
    for _,old in ipairs(handlers) do if old==fn then return end end
    handlers[#handlers+1]=fn
  end
  function result.Remove(fn)
    for i=#handlers,1,-1 do if handlers[i]==fn then table.remove(handlers,i) end end
  end
  local function dispatch(...)
    if name=='SerialEventGameMessagePopup' and popupKind=='Research' then
      local popup=(...)
      if type(popup)=='table' and popup.Type==ButtonPopupTypes.BUTTONPOPUP_TECH_TREE then
        assert(not active and contextHidden and timer==0,
          'TechTree request must be deferred until the current popup VM is inactive')
        native('requestTechTree',popup.Type,popup.Data2)
      end
    end
    if name=='SerialEventGameMessagePopup' and hasRetainedSocialPolicyUi then
      local popup=(...)
      if type(popup)=='table' and popup.Type==ButtonPopupTypes.BUTTONPOPUP_CONFIRM_POLICY_BRANCH_SWITCH then
        error('Original policy-branch-switch confirmation popup is not connected to a retained context',0)
      end
    end
    if name=='SerialEventGameMessagePopup' and hasRetainedTopPanelUi then
      local popup=(...)
      assert(type(popup)=='table' and (popup.Type==ButtonPopupTypes.BUTTONPOPUP_TECH_TREE or
        popup.Type==ButtonPopupTypes.BUTTONPOPUP_TRADE_ROUTE_OVERVIEW or
        popup.Type==ButtonPopupTypes.BUTTONPOPUP_CHOOSEPOLICY or
        popup.Type==ButtonPopupTypes.BUTTONPOPUP_ECONOMIC_OVERVIEW),
        'TopPanel popup route is unfinished except for original science, policy, trade-route, and economic requests')
      local data2=popup.Data2
      if data2==nil then data2=-1 end
      assert(data2==-1,'TopPanel popup request must preserve original/default Data2=-1')
      assert(not pendingTopPanelPopup,'TopPanel callback queued more than one popup request')
      pendingTopPanelPopup={Type=popup.Type,Data2=data2}
    end
    if name=='SerialEventGameMessagePopup' and hasRetainedEconomicChildUi then
      local popup=(...)
      assert(hasRetainedEconomicGeneralUi and active and not contextHidden and timer==0 and
        type(popup)=='table' and popup.Type==ButtonPopupTypes.BUTTONPOPUP_CHOOSEPRODUCTION and
        type(popup.Data1)=='number' and popup.Data1>=0 and popup.Data1==math.floor(popup.Data1) and
        popup.Data2==-1 and popup.Data3==-1 and popup.Option1==false and popup.Option2==false,
        'Economic child requested a non-original production popup tuple')
      native('economicChooseProduction',popup.Data1)
    end
    if name=='SpecificCityInfoDirty' then native('specificCityInfoDirty',...) end
    if name=='SearchForPediaEntry' then native('searchForPediaEntry',...) end
    if name=='GameplayFX' and hasRetainedActionInfoUi then native('actionInfoGameplayFx',...) end
    if hasRetainedGameMenuUi and (name=='UserRequestClose' or name=='ExitToMainMenu') then
      assert(select('#',...)==0,'GameMenu exit events take no arguments')
      if name=='UserRequestClose' then native('gameMenuExitConfirm')
      else
        assert(active and not contextHidden and timer==0 and gameMenuExitCursor==0,
          'Main-menu transition requires the original confirmed OnLeave/cursor boundary')
        native('gameMenuMainMenu')
      end
    end
    if name=='AudioPlay2DSound' and (hasRetainedSocialPolicyUi or hasRetainedPantheonUi) then
      local cue=(...)
      assert(select('#',...)==1 and cue=='AS2D_INTERFACE_POLICY',
        'SocialPolicy requested an unregistered original audio cue')
      native(hasRetainedPantheonUi and 'pantheonAudio' or 'policyAudio',cue)
    end
    local pending={}
    for i,fn in ipairs(handlers) do pending[i]=fn end
    for _,fn in ipairs(pending) do fn(...) end
    if hasRetainedTreeUi or hasRetainedTechUi or hasRetainedCityUi or hasRetainedSocialPolicyUi or hasRetainedEconomicUi then flushLayout() end
    if name=='SerialEventExitCityScreen' and hasRetainedCityUi then
      context:SetHide(true)
      native('exitCityScreen')
    end
    flushTopPanelPopupRequest()
  end
  result.CallImmediate=dispatch
  Events[name]=setmetatable(result,{__call=function(_,...) return dispatch(...) end})
end
for _,name in ipairs({'SerialEventGameMessagePopup','SerialEventGameMessagePopupShown',
  'SerialEventGameMessagePopupProcessed','GameplaySetActivePlayer','EventPoliciesDirty','AfterModsActivate','AfterModsDeactivate',
 'SerialEventCityScreenDirty','SerialEventCityInfoDirty','SerialEventGameDataDirty','SerialEventTurnTimerDirty','SerialEventUnitInfoDirty',
  'SerialEventResearchDirty',
 'UnitSelectionChanged','UnitGarrison','UnitEmbark','SerialEventCityDestroyed','SerialEventCityCaptured',
 'AILeaderMessage','LeavingLeaderViewMode',
 'SerialEventExitCityScreen','KeyDown','SearchForPediaEntry','SpecificCityInfoDirty','AudioPlay2DSound'}) do event(name) end
if hasRetainedLeaderUi then event('WarStateChanged') end
if hasRetainedUnitUi then
  event('ActivePlayerTurnEnd');event('ActivePlayerTurnStart');event('EnemyPanelHide')
end
if hasRetainedActionInfoUi then
  for _,name in ipairs({'ActivePlayerTurnEnd','RemotePlayerTurnEnd','SerialEventEndTurnDirty',
    'EndTurnBlockingChanged','GameplayFX'}) do event(name) end
end
if hasRetainedNotificationUi then event('NotificationAdded');event('NotificationRemoved') end
if hasRetainedGameMenuUi then event('UserRequestClose');event('ExitToMainMenu') end
if hasRetainedExitConfirmUi then event('UserRequestClose') end
setmetatable(Events,{__index=function(_,name) error('Unsupported UI event: '..tostring(name)) end})
LuaEvents={}
event('ProductionPopup')
LuaEvents.ProductionPopup=Events.ProductionPopup
if hasRetainedUnitUi then LuaEvents.EnemyPanelHide=Events.EnemyPanelHide end

-- These are host input/priority tokens, not asserted retail enum ordinals.
Mouse={eLClick='LeftClick'}
if hasRetainedSocialPolicyUi then
  -- Installed CommonBehaviors.lua spells this enum member eLclick.
  -- Keep the alias scoped to the original SocialPolicy popup contract.
  Mouse.eLclick=Mouse.eLClick
end
Mouse.eRClick='RightClick'
if hasRetainedNotificationUi then Mouse.eLDblClick='LeftDoubleClick' end
KeyEvents={KeyDown='KeyDown'}
Keys={VK_ESCAPE=27,VK_RETURN=13}
PopupPriority={WhosWinning='WhosWinning',eUtmost='eUtmost',TechTree='TechTree',GenericPopup=100}
PopupPriority.LeaderHead='LeaderHead'
PopupPriority.LeaderHeadPopup='LeaderHeadPopup'
PopupPriority.TechAward='TechAward'
PopupPriority.GoodyHut='GoodyHut'
PopupPriority.SocialPolicy='SocialPolicy'
PopupPriority.InGameUtmost='InGameUtmost'
PopupPriority.EconOverview='EconOverview'
if hasRetainedGameMenuUi or hasRetainedTopPanelUi then PopupPriority.InGameMenu='InGameMenu' end
if hasRetainedGameMenuUi then
  for _,name in pairs(gameMenuChildren) do PopupPriority[name]=name end
end
if hasRetainedSaveMenuUi then PopupPriority.SaveMenu='SaveMenu';PopupPriority.SaveMapMenu='SaveMapMenu' end
if popupKind=='MapMenu' then PopupPriority.SaveMapMenu='SaveMapMenu' end
if hasRetainedCaptureUi then
  -- Explicitly select the installed BNW capture layout for this private VM.
  -- Keep the stock pattern include and loaded script bytes unchanged.
  local sourceInclude=assert(include)
  include=function(name,pattern)
    if name=='InGame\\PopupsGeneric\\%w+Popup.lua' and pattern==true then
      sourceInclude('PuppetCityPopup')
      return {'PuppetCityPopup.lua'}
    end
    return sourceInclude(name,pattern)
  end
  Network=Network or {}
  Network.SendDoTask=function(...) return native('sendCityTask',...) end
  Network.SendLiberateMinor=function(...) return native('sendCityLiberation',...) end
end
if hasRetainedDeclareWarUi then
  -- Read-only Players, Teams, GameInfo, GameDefines, Map and Game methods
  -- remain the real SDK bindings installed in this Lua state.
  Game.DoFromUIDiploEvent=function(...)
    assert(select('#',...)==4, 'DoFromUIDiploEvent requires the stock four-argument tuple')
    return native('declareWarDiplo',...)
  end
  Game.SelectionListMove=function(...)
    assert(select('#',...)==4, 'SelectionListMove requires the stock four-argument tuple')
    local plot,alt,shift,ctrl=...
    assert((type(plot)=='table' or type(plot)=='userdata') and
      type(plot.GetX)=='function' and type(plot.GetY)=='function' and
      type(alt)=='boolean' and type(shift)=='boolean' and type(ctrl)=='boolean',
      'SelectionListMove requires plot plus the stock three boolean flags')
    return native('declareWarMove',plot:GetX(),plot:GetY(),alt,shift,ctrl)
  end
  Game.SelectionListGameNetMessage=function(...)
    assert(select('#',...)==4, 'SelectionListGameNetMessage requires the stock four-argument range-strike tuple')
    return native('declareWarMission',...)
  end
  Network=Network or {}
  Network.SendChangeWar=function(...)
    assert(select('#',...)==2, 'SendChangeWar requires the stock team/war tuple')
    return native('declareWarChange',...)
  end
  TradeableItems=assert(TradeableItems)
  FromUIDiploEventTypes=assert(FromUIDiploEventTypes)
  GameMessageTypes=assert(GameMessageTypes)
  MissionTypes=assert(MissionTypes)
  InterfaceModeTypes=assert(InterfaceModeTypes)
end
if hasRetainedPantheonUi then
  assert(contextName=='ChoosePantheonPopup','Pantheon context identity mismatch')
  Network=Network or {}
  Network.SendFoundPantheon=function(owner,belief,...)
    assert(select('#',...)==0,'SendFoundPantheon requires the original two-argument tuple')
    pantheonState.scope()
    local entry=pantheonState.dispatch
    assert(entry and not pantheonState.submitted and active and not contextHidden and timer==1 and
      entry.owner==owner and entry.belief==belief and entry.turn==pantheonState.turn and
      entry.generation==pantheonState.generation and g_BeliefID==belief and
      g_PopupInfo and g_PopupInfo.Data2==1,
      'Pantheon command requires its original visible-confirmation Yes callback')
    native('foundPantheon',owner,belief)
    pantheonState.submitted=true
  end
end
Locale={ConvertTextKey=function(...) return native('locale',...) end,
        Lookup=function(...) return native('locale',...) end,
        Length=function(value) return native('localeLength',value) end,
        TruncateString=function(...) return native('localeTruncate',...) end,
        ToUpper=function(value) return native('localeUpper',value) end,
        ToLower=function(value) return native('localeLower',value) end,
        Compare=function(a,b) return native('localeCompare',a,b) end,
        EndsWith=function(value,suffix) return native('localeEndsWith',value,suffix) end,
        GetLength=function(value) return native('localeLength',value) end,
        Substring=function(value,start,count) return native('localeSubstring',value,start,count) end,
        SubString=function(value,start,count) return native('localeSubstring',value,start,count) end}
Locale.IsNilOrWhitespace=function(value)
  if value==nil then return true end
  for _,item in ipairs(utf8Characters(text(value))) do
    local c=item.codepoint
    if not (c>=9 and c<=13 or c==32 or c==0x85 or c==0xA0 or c==0x1680 or
      c>=0x2000 and c<=0x200A or c==0x2028 or c==0x2029 or c==0x202F or c==0x205F or c==0x3000) then return false end
  end
  return true
end
OptionsManager={IsNoBasicHelp=function() return native('noBasicHelp') end,
        GetSmallUIAssets=function() return native('smallUiAssets') end}
PreGame={GetCivilization=function(id) return native('civilization',id) end,
         GetCivilizationColor=function(id) return native('playerColor',id) end}
if hasRetainedLeaderUi then
  PreGame.GetLeaderName=function(id) return native('leaderName',id) end
  PreGame.GetCivilizationShortDescription=function(id)
    return native('civilizationShortDescription',id)
  end
end
UI={incTurnTimerSemaphore=function()
      assert(timer==0, 'Duplicate popup timer acquisition');native('timer',1);timer=1
    end,
    decTurnTimerSemaphore=function()
      assert(timer==1, 'Unbalanced popup timer release');native('timer',-1);timer=0
    end,
    IsCityScreenViewingMode=function()
      local viewing=native('cityScreenViewingMode')
      assert(type(viewing)=='boolean','cityScreenViewingMode native operation must return a boolean')
      return viewing
    end,
    GetUnitPortraitIcon=function(unitID,playerID) return native('unitPortrait',unitID,playerID) end,
    SetCityScreenViewingMode=function(value)
      assert(type(value)=='boolean','City viewing mode must be boolean')
      return native('setCityScreenViewingMode',value)
    end,
    DoSelectCityAtPlot=function(plot)
      assert((type(plot)=='table' or type(plot)=='userdata') and type(plot.GetX)=='function' and type(plot.GetY)=='function',
        'City selection requires an actual plot')
      return native('selectCityAtPlot',plot:GetX(),plot:GetY())
    end,
    GetHeadSelectedCity=function()
      local owner,cityID=native('headSelectedCity')
      if owner==nil or cityID==nil then return nil end
      assert(type(owner)=='number' and owner==math.floor(owner) and type(cityID)=='number' and cityID==math.floor(cityID),
        'headSelectedCity must return owner and city id')
      local player=assert(Players and Players[owner],'headSelectedCity owner has no live player binding')
      return player:GetCityByID(cityID)
    end,
    LookAt=function(plot,lookAtType)
      assert((type(plot)=='table' or type(plot)=='userdata') and type(plot.GetX)=='function' and type(plot.GetY)=='function',
        'UI.LookAt requires an actual map plot')
      local x,y=plot:GetX(),plot:GetY()
      assert(type(x)=='number' and type(y)=='number','UI.LookAt plot coordinates are invalid')
      return native('lookAt',x,y,lookAtType)
    end,
    SetLeaderHeadRootUp=function(value)
      assert(hasRetainedLeaderUi and type(value)=='boolean','SetLeaderHeadRootUp requires a LeaderHead boolean')
      return native('leaderRootUp',value)
    end,
    GetLeaderHeadRootUp=function()
      assert(hasRetainedLeaderUi,'GetLeaderHeadRootUp requires the LeaderHead context')
      local value=native('leaderRootUp')
      assert(type(value)=='boolean','leaderRootUp native operation must return a boolean')
      return value
    end,
    RequestLeaveLeader=function()
      assert(hasRetainedLeaderUi,'RequestLeaveLeader requires the LeaderHead context')
      return native('leaveLeader')
    end}
if hasRetainedDeclareWarUi then
  UI.GetNumCurrentDeals=function(...)
    assert(select('#',...)==1,'GetNumCurrentDeals requires one player argument')
    return native('numCurrentDeals',...)
  end
  UI.LoadCurrentDeal=function(...)
    assert(select('#',...)==2,'LoadCurrentDeal requires player and deal index')
    return native('loadCurrentDeal',...)
  end
  UI.GetScratchDeal=function(...)
    assert(select('#',...)==0,'GetScratchDeal takes no arguments')
    return native('scratchDeal')
  end
  UI.SetInterfaceMode=function(...)
    assert(select('#',...)==1,'SetInterfaceMode requires the stock one-argument tuple')
    return native('declareWarInterfaceMode',...)
  end
end

if hasRetainedGameMenuUi or hasRetainedSaveMenuUi then
  -- These adapters expose the SDK's actual setup state to unchanged GameMenu.
  -- Gameplay mutations are only owned requests handled after Lua unwinds.
  for method,selector in pairs({GetLeaderName='leaderName',
    GetCivilizationShortDescription='civilizationShortDescription',GetWorldSize='worldSize',
    GetGameSpeed='gameSpeed',GetEra='era',GetHandicap='handicap',IsVictory='victory',
    GetGameOption='gameOption',GetLoadWBScenario='loadWBScenario'}) do
    local query=selector
    PreGame[method]=function(...) return native('gameMenuPreGame',query,...) end
  end
  PreGame.GetMapScript=function()
    local raw=text(native('gameMenuPreGame','mapScript'))
    local normalized=raw:gsub('\\','/'):lower()
    local matched
    for row in GameInfo.MapScripts() do
      if row.FileName:gsub('\\','/'):lower()==normalized then
        assert(not matched,'GameMenu map script has ambiguous DB path aliases')
        matched=row.FileName
      end
    end
    gameMenuRawMapScript=raw;gameMenuDatabaseMapScript=matched
    return matched or raw
  end
  Modding={
    GetActivatedMods=function() return native('gameMenuActivatedMods') end,
    AnyActivatedModsContainPropertyValue=function(...) return native('gameMenuModPropertyContains',...) end,
    GetModProperty=function(...) return native('gameMenuModProperty',...) end}
  Path={GetFileNameWithoutExtension=function(path)
    local name=text(path):gsub('\\','/'):match('([^/]*)$')
    return (name:gsub('%.[^.]*$',''))
  end}
  clearGameMenuNotice=function()
    if gameMenuUnavailableAction and controls.ExitConfirm:IsHidden() then
      controls.Yes:SetDisabled(false)
      gameMenuUnavailableAction=nil
    end
  end
  gameMenuUnavailable=function(action)
    assert(active and not contextHidden and (timer==1 or timer==0 and gameMenuExitCursor~=nil),
      'GameMenu unavailable action has no original menu lifetime')
    native('gameMenuUnavailable',action)
    if gameMenuExitCursor~=nil then
      local cursor=gameMenuExitCursor;gameMenuExitCursor=nil
      native('gameMenuCursor',cursor)
      assert(type(OnEnter)=='function','Original GameMenu OnEnter is missing')
      OnEnter()
      assert(timer==1,'Unavailable exit failed to restore the original menu lifetime')
    end
  end
  UI.GetMapPreview=function(filename) return native('gameMenuMapPreview',text(filename)) end
  UI.SetInterfaceMode=function(mode) return native('gameMenuInterfaceMode',mode) end
  UI.IsTouchScreenEnabled=function()
    local value=native('isTouchScreen')
    assert(type(value)=='boolean','GameMenu touch capability must be a boolean')
    return value
  end
  UI.QuickSave=function()
    assert(not active and contextHidden and timer==0,'QuickSave requires original OnReturn first')
    return native('gameMenuQuickSave')
  end
  UI.ExitGame=function() error('GameMenu must request its separate original ExitConfirm modal') end
  Game.DoControl=function(kind)
    assert(ControlTypes and (kind==ControlTypes.CONTROL_RESTART_GAME or kind==ControlTypes.CONTROL_RETIRE),
      'GameMenu requested a non-original gameplay control')
    assert(active and not contextHidden and timer==1 and Game.CanDoControl(kind),
      'Game control request requires the live original menu and SDK eligibility')
    return native(kind==ControlTypes.CONTROL_RESTART_GAME and 'gameMenuRestart' or 'gameMenuRetire')
  end
end

if hasRetainedExitConfirmUi then
  UI.ExitGame=function(...)
    assert(select('#',...)==0,'ExitConfirm exit takes no arguments')
    assert(exitConfirmState.dispatch=='Yes' and exitConfirmState.closed and
      not exitConfirmState.submitted and not active and contextHidden and timer==0,
      'ExitGame requires the completed original Yes/PopModal callback')
    exitConfirmState.submitted=true
    native('exitConfirmExit')
  end
end

if hasRetainedSaveMenuUi then
  ownedSaveDelete.prefix='saveMenu';ownedSaveDelete.supported=native('saveMenuDeleteSupported')
  assert(type(ownedSaveDelete.supported)=='boolean','SaveMenu delete capability must be a boolean')
  ownedSaveOverwrite.supported=native('saveMenuOverwriteSupported')
  assert(type(ownedSaveOverwrite.supported)=='boolean','SaveMenu overwrite capability must be a boolean')
  GameTypes=native('saveMenuGameTypes')
  assert(type(GameTypes)=='table' and GameTypes.GAME_TYPE_NONE==-1 and GameTypes.GAME_SINGLE_PLAYER==0 and
    GameTypes.GAME_NETWORK_MULTIPLAYER==1 and GameTypes.GAME_HOTSEAT_MULTIPLAYER==2 and
    GameTypes.GAME_EMAIL_MULTIPLAYER==3,'SaveMenu requires its actual SDK game type enum binding')
  saveMenuCurrent=assert(native('saveMenuCurrent'),'SaveMenu requires its actual current SDK header')
  assert(type(saveMenuCurrent)=='table' and
    saveMenuCurrent.GameType==GameTypes.GAME_SINGLE_PLAYER,'SaveMenu requires the supported SDK single-player session')
  PreGame.GameStarted=function() return true end
  PreGame.IsMultiplayerGame=function() return false end
  PreGame.IsHotSeatGame=function() return false end
  for method,field in pairs({GetCivilization='PlayerCivilization',GetGameSpeed='GameSpeed',
    GetEra='StartEra',GetHandicap='Difficulty',GetWorldSize='WorldSize',GetMapScript='MapScript',
    GetLeaderName='LeaderName',GetCivilizationDescription='CivilizationName'}) do
    local key=field;PreGame[method]=function() return saveMenuCurrent[key] end
  end
  PreGame.GetGameType=function() return saveMenuCurrent.GameType end
  PreGame.GetFileHeader=function(path) return native('saveMenuHeader',text(path)) end
  Steam={GetMaxCloudSaves=function() return 0 end,
    GetCloudSaves=function() error('Steam Cloud is not connected') end,
    SaveGameToCloud=function() error('Steam Cloud is not connected') end,
    CopyLastAutoSaveToSteamCloud=function() error('Steam Cloud is not connected') end}
  saveMenuCanCreate=function()
    if not active or contextHidden or inputContextName~=contextName or timer~=0 or not controls.NameBox then return false end
    local name=controls.NameBox:GetText()
    if type(ValidateText)~='function' or not ValidateText(name) or #utf8Characters(name)>32 then return false end
    local available=native('saveMenuNameAvailable',name)
    assert(type(available)=='boolean','SaveMenu name availability must be a boolean')
    return available
  end
  saveMenuCanSave=function()
    return saveMenuCanCreate() or ownedSaveOverwrite.eligible()
  end
  UI.SaveFileList=function(files,gameType,automatic,includeCustom)
    assert(type(files)=='table' and next(files)==nil and gameType==GameTypes.GAME_SINGLE_PLAYER and
      automatic==false and includeCustom==true,'SaveFileList requires the original single-player tuple')
    local paths=native('saveMenuFiles');assert(type(paths)=='table','SaveMenu file catalog must be an array')
    local count=0;for key,path in pairs(paths) do
      assert(type(key)=='number' and key==math.floor(key) and key>=1 and type(path)=='string' and path~='',
        'SaveMenu catalog has an invalid path row');count=count+1
    end
    ownedSaveDelete.clearConfirmation();ownedSaveDelete.clearDispatch();ownedSaveOverwrite.invalidate()
    ownedSaveOverwrite.epoch=ownedSaveOverwrite.epoch+1;ownedSaveOverwrite.listed={}
    for index=1,count do
      local path=text(assert(paths[index],'SaveMenu catalog must be contiguous'))
      assert(ownedSaveOverwrite.listed[path]==nil,'SaveMenu catalog repeated an exact path')
      ownedSaveOverwrite.listed[path]={name=Path.GetFileNameWithoutExtension(path)}
    end
    for index=1,count do files[index]=text(assert(paths[index],'SaveMenu catalog must be contiguous')) end
    -- The unchanged stock script overwrites rows but retains its previous tail.
    if type(g_SavedGames)=='table' then
      for index=#g_SavedGames,count+1,-1 do g_SavedGames[index]=nil end
    end
  end
  UI.GetSavedGameModificationTime=function(path) return text(native('saveMenuModificationTime',text(path))) end
  UI.SaveGame=function(name)
    local grant=ownedSaveOverwrite.dispatch;ownedSaveOverwrite.dispatch=nil
    if grant~=nil then
      assert(ownedSaveDelete.callbackRole=='OverwriteYes' and name==grant.name and ownedSaveOverwrite.valid(grant),
        'Overwrite requires its exact original selected confirmation dispatch')
      return native('saveMenuOverwrite',text(name),grant.path)
    end
    assert(saveMenuCanCreate() and name==controls.NameBox:GetText(),'SaveGame requires a new validated NameBox value')
    return native('saveMenuSave',text(name))
  end
  UI.DeleteSavedGame=ownedSaveDelete.delete
  UI.CopyLastAutoSave=function() error('Multiplayer saves are not connected') end
end

if hasRetainedLoadMenuUi then
  ownedSaveDelete.prefix='loadMenu';ownedSaveDelete.supported=native('loadMenuDeleteSupported')
  assert(type(ownedSaveDelete.supported)=='boolean','LoadMenu delete capability must be a boolean')
  GameTypes=native('loadMenuGameTypes')
  assert(type(GameTypes)=='table' and GameTypes.GAME_TYPE_NONE==-1 and GameTypes.GAME_SINGLE_PLAYER==0 and
    GameTypes.GAME_NETWORK_MULTIPLAYER==1 and GameTypes.GAME_HOTSEAT_MULTIPLAYER==2 and
    GameTypes.GAME_EMAIL_MULTIPLAYER==3,'LoadMenu requires the actual SDK game type binding')
  local function listedPath(path)
    path=text(path);assert(path~='' and not path:find('%z'),'LoadMenu requires an exact listed path');return path
  end
  local function exactWord(value)
    assert(type(value)=='number' and value==value and value>=0 and value<=4294967295 and value==math.floor(value),
      'LoadMenu FILETIME words must remain exact unsigned 32-bit numbers')
    return value
  end
  local function unsupported() error('This save operation is not connected to the owned local catalog') end
  loadMenuCanLoad=function()
    if not active or contextHidden or inputContextName~=contextName or timer~=0 or
      type(g_FileList)~='table' or type(g_iSelected)~='number' then return false end
    local path=g_FileList[g_iSelected]
    if type(path)~='string' then return false end
    local result=native('loadMenuCanLoad',listedPath(path))
    assert(result==0 or result==5,'LoadMenu native loadability result is invalid')
    return result==0
  end
  PreGame.IsHotSeatGame=function()
    assert(native('loadMenuInGameView')==true,'LoadMenu requires its initialized local single-player owner')
    return false
  end
  PreGame.GetFileHeader=function(path,...)
    assert(select('#',...)==0,'Cloud save headers are not connected')
    return native('loadMenuHeader',listedPath(path))
  end
  for _,name in ipairs({'SetLoadFileName','IsInternetGame','ReadActiveSlotCountFromSaveGame','SetGameOption','SetWorldSize'}) do
    PreGame[name]=unsupported
  end
  Path={GetFileNameWithoutExtension=function(path)
    local name=text(path):gsub('\\','/'):match('([^/]*)$');return (name:gsub('%.[^.]*$',''))
  end}
  Locale.HasTextKey=function(key)
    local result=native('localeHasTextKey',text(key))
    assert(type(result)=='boolean','Localization key availability must be a boolean');return result
  end
  Modding={CanLoadSavedGame=function(path)
      local result=native('loadMenuCanLoad',listedPath(path))
      assert(result==0 or result==5,'LoadMenu native loadability result is invalid');return result
    end,
    GetSavedGameRequirements=function(path)
      local dlc,mods=native('loadMenuRequiredContent',listedPath(path))
      assert(type(dlc)=='table' and type(mods)=='table' and next(dlc)==nil and next(mods)==nil,
        'The owned exact-bundle profile must return its explicit empty DLC then mods lists')
      return dlc,mods
    end,
    CanLoadCloudSave=unsupported,GetCloudSaveRequirements=unsupported}
  Steam={GetMaxCloudSaves=function() return 0 end,
    GetCloudSaves=function()
      local result=native('loadMenuCloudSaves')
      assert(type(result)=='table' and next(result)==nil,'The offline cloud getter must return an explicit empty list')
      return result
    end,
    GetCloudSaveFileName=unsupported,SaveGameToCloud=unsupported,CopyLastAutoSaveToSteamCloud=unsupported}
  UI.SaveFileList=function(files,gameType,automatic,includeCustom)
    assert(type(files)=='table' and next(files)==nil and gameType==GameTypes.GAME_SINGLE_PLAYER and
      automatic==false and includeCustom==true,'LoadMenu list requires the owned local single-player tuple')
    local rows=native('loadMenuFiles');assert(type(rows)=='table','LoadMenu catalog must be an array')
    local count,seen=0,{}
    for key,path in pairs(rows) do
      assert(type(key)=='number' and key>=1 and key==math.floor(key) and type(path)=='string' and
        path~='' and not seen[path],'LoadMenu catalog has an invalid or duplicate row')
      seen[path]=true;count=count+1
    end
    for index=1,count do files[index]=listedPath(assert(rows[index],'LoadMenu catalog must be contiguous')) end
  end
  UI.GetSavedGameModificationTime=function(path) return text(native('loadMenuModificationTime',listedPath(path))) end
  UI.GetMapPreview=function(filename) return native('loadMenuMapPreview',text(filename)) end
  UI.GetSavedGameModificationTimeRaw=function(path)
    local high,low=native('loadMenuModificationTimeRaw',listedPath(path));return exactWord(high),exactWord(low)
  end
  UI.CompareFileTime=function(firstHigh,firstLow,secondHigh,secondLow)
    local result=native('loadMenuCompareFileTime',exactWord(firstHigh),exactWord(firstLow),exactWord(secondHigh),exactWord(secondLow))
    assert(result==-1 or result==0 or result==1,'LoadMenu time comparison must return -1, 0 or 1');return result
  end
  UI.DeleteSavedGame=ownedSaveDelete.delete
  -- The SDK's gameplay GameStateTypes is a separate enum. This private frontend
  -- identity has no invented retail numeric value and never crosses the ABI.
  local inGameView={}
  GameStateTypes={CIV5_GS_MAINGAMEVIEW=inGameView}
  UI.GetCurrentGameState=function()
    assert(native('loadMenuInGameView')==true,'LoadMenu no longer owns the initialized local in-game view')
    return inGameView
  end
  Events.PlayerChoseToLoadGame=function(path,...)
    assert(select('#',...)==0 and loadMenuCanLoad() and path==g_FileList[g_iSelected],
      'LoadMenu load event requires its selected validated local save')
    return native('loadMenuLoad',listedPath(path))
  end
end

function context:SetUpdate(callback)
  assert(callback==nil or type(callback)=='function','ContextPtr:SetUpdate expects a function or nil')
  assert(hasRetainedUnitUi,'ContextPtr:SetUpdate is only retained for UnitPanel')
  updateCallback=callback
end
function context:LookUpControl(path)
  if hasRetainedExitConfirmUi then
    assert(path=='/InGame','ExitConfirm queried an undeclared context path')
    assert(native('exitConfirmInGame')==true,'ExitConfirm requires the actual owned in-game session')
    return context
  end
  if hasRetainedPantheonUi then
    assert(path=='/InGame/WorldView/UnitPanel/Base' or path=='/InGame/WorldView/InfoCorner',
      'Pantheon queried an undeclared world HUD path')
    if path=='/InGame/WorldView/InfoCorner' then return nil end
    return {SetHide=function(_,hidden)
      assert(type(hidden)=='boolean','Pantheon HUD visibility requires a boolean')
      native('pantheonHudVisibility',path,hidden);pantheonState.unitPanelHidden=hidden
    end}
  end
  if hasRetainedLoadMenuUi then
    assert(path=='..','LoadMenu may only query its original GameMenu parent identity')
    return {GetID=function() return 'GameMenu' end}
  end
  if hasRetainedTopPanelUi then
    assert(path=='/InGame/GameMenu','Unsupported TopPanel control lookup path')
    return topPanelGameMenuToken
  end
  assert(hasRetainedUnitUi and path=='/InGame/WorldView/EnemyUnitPanel',
    'Unsupported UnitPanel control lookup path')
  return controls.EnemyUnitPanel
end
function context:Update()
  assert(hasRetainedUnitUi,'ContextPtr:Update is only retained for UnitPanel')
  if active and not contextHidden and updateCallback then return updateCallback() end
end

local rootNode={kind='Context',attributes=layout.attributes,children={}}
root=make(rootNode,nil,controls)
states[root].w=viewport.w;states[root].h=viewport.h
if hasRetainedExitConfirmUi then states[root].exitConfirmState=exitConfirmState end
for _,node in ipairs(layout.children) do
  if node.kind=='Instance' then
    assert(node.attributes.Name and not templates[node.attributes.Name], 'Invalid instance template')
    templates[node.attributes.Name]=node
  else make(node,root,controls) end
end
if hasRetainedTopPanelUi then
  for _,template in ipairs(assert(layout.toolTipTemplates,'TopPanel tooltip template is missing')) do
    assert(template.name=='TooltipTypeTopPanel' and not topPanelTooltipRoots[template.name],
      'Unsupported or duplicate TopPanel tooltip template')
    local names={}
    topPanelTooltipRoots[template.name]={root=make(template.tree,nil,names),controls=names}
  end
  TTManager={}
  function TTManager:GetTypeControlTable(name,target)
    assert(type(target)=='table','TopPanel tooltip target must be a table')
    local source=assert(topPanelTooltipRoots[name],'Unknown TopPanel tooltip type: '..tostring(name))
    for id,handle in pairs(source.controls) do target[id]=handle end
    return target
  end
end
function context:BuildInstanceForControl(name,names,parent)
  assert(self==context and type(names)=='table', 'Invalid UI instance request')
  state(parent)
  local template=assert(templates[name], 'Unknown UI instance: '..tostring(name))
  for _,node in ipairs(template.children) do
    local handle=make(node,parent,names)
    if hasRetainedNotificationUi or hasRetainedGameMenuUi or popupKind=='MapMenu' then state(handle).instanceTemplate=name end
  end
end
function context:BuildInstance(name,names) self:BuildInstanceForControl(name,names,root) end
function context:SetInputHandler(fn)
  assert(type(fn)=='function' and not inputHandler, 'Invalid or repeated input handler')
  if hasRetainedGameMenuUi then
    inputHandler=function(...)
      local result=fn(...)
      clearGameMenuNotice()
      return result
    end
  else inputHandler=fn end
end
function context:SetShowHideHandler(fn)
  assert(type(fn)=='function' and not showHide, 'Invalid or repeated show/hide handler');showHide=fn
  fn(true,true)
end
function context:SetHide(value)
  assert(type(value)=='boolean','ContextPtr:SetHide expects a boolean')
  if value==contextHidden then return end
  if value then
    pullDown.close()
    contextHidden=true
    if hasRetainedPopupUi then updateAnimations(root,false,true,frameTime()) end
    if showHide then showHide(true,false) end
    if hasRetainedTechUi then researchProcessedPending=true end
    active=false;inputContextName=nil;lifecycle[#lifecycle+1]='context-hidden:'..contextName
  else
    assert(not active,'Another popup context is already active')
    contextHidden=false;active=true;inputContextName=contextName
    if hasRetainedPopupUi then updateAnimations(root,true,true,frameTime()) end
    anchor(root)
    lifecycle[#lifecycle+1]='queued'
    if showHide then showHide(false,false) end
  end
end
function context:IsHidden() return contextHidden end
UIManager={}
function UIManager:GetShift()
  local shifted=native('uiShift')
  assert(type(shifted)=='boolean','uiShift native operation must return a boolean')
  return shifted
end
function UIManager:SetUICursor(cursor)
  if hasRetainedLoadMenuUi then
    assert(cursor==1 and active and not contextHidden and timer==0 and loadMenuCanLoad(),
      'LoadMenu busy cursor requires its selected load callback')
    return native('loadMenuCursor',cursor)
  end
  if hasRetainedGameMenuUi then
    assert(cursor==1 and active and timer==0 and gameMenuExitCursor==nil,
      'GameMenu busy cursor requires the original confirmed-exit callback')
    gameMenuExitCursor=native('gameMenuCursor',cursor)
    assert(gameMenuExitCursor==0,'GameMenu exit cursor did not replace the default arrow')
    return gameMenuExitCursor
  end
  assert((hasRetainedLeaderUi or hasRetainedDeclareWarUi) and type(cursor)=='number' and
    cursor==cursor and cursor>=0 and cursor==math.floor(cursor),
    'SetUICursor requires a nonnegative original popup cursor token')
  local previous=native('uiCursor',cursor)
  assert(type(previous)=='number' and previous==previous and previous>=0 and previous==math.floor(previous),
    'uiCursor native operation must return the previous cursor token')
  return previous
end
function UIManager:QueuePopup(ctx,priority)
  if hasRetainedTopPanelUi and ctx==topPanelGameMenuToken then
    assert(active and not contextHidden and timer==0 and topPanelCallbackDepth>0 and
      not pendingTopPanelPopup and priority==PopupPriority.InGameMenu,
      'TopPanel GameMenu open requires the original active input callback')
    return native('gameMenuOpen')
  end
  if hasRetainedGameMenuUi and ctx~=context then
    local target=state(ctx);local expected=gameMenuChildren[target.attributes.ID]
    assert(target.kind=='LuaContext' and target.parent==root and expected and
      priority==PopupPriority[expected] and target.hidden and #target.children==0,
      'GameMenu child popup request differs from its original declaration')
    if target.attributes.ID=='SaveMenu' then return native('saveMenuOpen') end
    if target.attributes.ID=='LoadMenu' then return native('loadMenuOpen') end
    if target.attributes.ID=='OptionsMenu_InGame' then return native('menuOptionsOpen') end
    if target.attributes.ID=='TouchControlsMenu' then return native('touchHelpOpen') end
    if target.attributes.ID=='SaveMapMenu' then return native('mapMenuOpen') end
    return gameMenuUnavailable(target.attributes.ID)
  end
  if hasRetainedSaveMenuUi and ctx~=context then
    local target=state(ctx)
    assert(target.kind=='LuaContext' and target.attributes.ID=='SaveMapMenu' and target.parent==root and
      priority==PopupPriority.SaveMapMenu and target.hidden and #target.children==0,
      'SaveMenu map popup request differs from its original declaration')
    return native('mapMenuOpen')
  end
  if hasRetainedCaptureUi and ctx==controls.EmptyPopup then
    assert(active and not captureCityOverlay and priority==PopupPriority.GenericPopup+1,
      'Captured-city viewing barrier has an invalid priority or lifetime')
    native('cityViewBarrier',true)
    captureCityOverlay=true;inputContextName=nil
    lifecycle[#lifecycle+1]='city-view-covered'
    return
  end
  local allowed=ctx==context and ((popupKind=='WhosWinning' and priority==PopupPriority.WhosWinning) or
    (hasRetainedDeclareWarUi and (priority==PopupPriority.GenericPopup or priority==PopupPriority.LeaderHeadPopup)) or
    (hasRetainedTechAwardUi and priority==PopupPriority.TechAward) or
    (goodyHutRewardState.enabled and priority==PopupPriority.GoodyHut) or
    (hasRetainedTreeUi and (priority==PopupPriority.eUtmost or priority==PopupPriority.TechTree)) or
    (hasRetainedCaptureUi and priority==PopupPriority.GenericPopup) or
    (hasRetainedLeaderUi and priority==PopupPriority.LeaderHead) or
    (hasRetainedTradeRouteUi and (priority==PopupPriority.SocialPolicy or priority==PopupPriority.InGameUtmost)) or
    (hasRetainedSocialPolicyUi and (priority==PopupPriority.SocialPolicy or priority==PopupPriority.InGameUtmost)) or
    (hasRetainedPantheonUi and priority==PopupPriority.SocialPolicy) or
    (hasRetainedEconomicParentUi and (priority==PopupPriority.EconOverview or priority==PopupPriority.InGameUtmost)) or
    (hasRetainedGameMenuUi and priority==PopupPriority.InGameMenu) or
    (hasRetainedSaveMenuUi and priority==PopupPriority.SaveMenu) or
    (hasRetainedLoadMenuUi and priority==PopupPriority.LoadMenu) or
    (popupKind=='MapMenu' and priority==PopupPriority.SaveMapMenu))
  assert(allowed, 'Unsupported popup queue request')
  assert(not active and (showHide or hasRetainedCaptureUi), 'Popup already shown or handler missing')
  active=true;contextHidden=false;inputContextName=contextName;lifecycle[#lifecycle+1]='queued'
  if hasRetainedPopupUi or hasRetainedLeaderUi then updateAnimations(root,true,true,frameTime()) end
  anchor(root)
  if showHide then showHide(false,false) end
end
function UIManager:DequeuePopup(ctx)
  if hasRetainedCaptureUi and ctx==controls.EmptyPopup then
    assert(active and captureCityOverlay,'Captured-city viewing barrier is not queued')
    native('cityViewBarrier',false)
    captureCityOverlay=false;inputContextName=contextName
    lifecycle[#lifecycle+1]='city-view-returned'
    return
  end
  assert(ctx==context, 'Foreign popup context')
  if not active then return end
  pullDown.close()
  if hasRetainedPopupUi or hasRetainedLeaderUi then updateAnimations(root,false,true,frameTime()) end
  if showHide then showHide(true,false) end
  active=false;contextHidden=true;inputContextName=nil;lifecycle[#lifecycle+1]='closed'
  if hasRetainedSaveMenuUi or hasRetainedLoadMenuUi then
    ownedSaveDelete.clearConfirmation();ownedSaveDelete.clearDispatch();ownedSaveOverwrite.invalidate()
  end
  if hasRetainedSaveMenuUi then setEditFocus(nil);native('saveMenuClose') end
  if popupKind=='MapMenu' then setEditFocus(nil) end
  if hasRetainedLoadMenuUi then native('loadMenuClose') end
  if hasRetainedTreeUi or hasRetainedCaptureUi then researchProcessedPending=true end
end
function UIManager:PushModal(ctx,...)
  assert(hasRetainedExitConfirmUi and ctx==context and select('#',...)==0,
    'PushModal requires the original ExitConfirm context without extra arguments')
  assert(exitConfirmState.opening and not exitConfirmState.opened and
    not exitConfirmState.closed and not active and contextHidden and timer==0 and showHide,
    'ExitConfirm modal must open once through its owner-requested original event')
  active=true;contextHidden=false;inputContextName=contextName;exitConfirmState.opened=true
  lifecycle[#lifecycle+1]='modal-pushed'
  updateAnimations(root,true,true,frameTime());anchor(root)
  showHide(false,false)
end
function UIManager:IsModal(ctx)
  assert(hasRetainedSaveMenuUi and ctx==context,'IsModal requires the original SaveMenu context')
  -- This child is opened by the original GameMenu QueuePopup callback. It
  -- never enters the separate PushModal stack; its parent owns the timer.
  return false
end
function UIManager:PopModal(ctx,...)
  if hasRetainedExitConfirmUi then
    assert(ctx==context and select('#',...)==0,'ExitConfirm PopModal takes only its original context')
    assert(active and not contextHidden and timer==0 and exitConfirmState.opened and
      not exitConfirmState.closed and not exitConfirmState.submitted and
      (exitConfirmState.dispatch=='Yes' or exitConfirmState.dispatch=='No' or
       exitConfirmState.dispatch=='Escape' or exitConfirmState.dispatch=='Close'),
      'ExitConfirm may close only inside its original input or owner cancellation')
    self:DequeuePopup(ctx)
    exitConfirmState.closed=true;lifecycle[#lifecycle+1]='modal-popped'
    native('exitConfirmClose')
    return
  end
  assert(hasRetainedSaveMenuUi and ctx==context and select('#',...)==0,
    'PopModal requires the original SaveMenu context')
  return self:DequeuePopup(ctx)
end
function UIManager:GetScreenSizeVal()
  -- The host contract is a logical viewport, not the physical monitor size.
  local width,height=native('screenSize')
  assert(type(width)=='number' and type(height)=='number' and width>0 and height>0,
    'screenSize native operation must return positive width and height')
  return width,height
end
if hasRetainedLeaderUi then
  Modding={}
  function Modding.GetActivatedModEntryPoints(kind)
    assert(contextName=='diplomacy' and type(kind)=='string' and kind=='DiplomacyUIAddin',
      'LeaderHead requested an unsupported mod entry-point category')
    local rows=native('activatedModEntryPoints',kind)
    assert(type(rows)=='table','activatedModEntryPoints must return an owned row table')
    local count,maximum=0,0
    for index,row in pairs(rows) do
      assert(type(index)=='number' and index>=1 and index==math.floor(index),
        'Activated mod entry points must be an array')
      assert(type(row)=='table','Activated mod entry point row must be a table')
      count=count+1;maximum=math.max(maximum,index)
    end
    assert(count==maximum,'Activated mod entry-point rows must be contiguous')
    for index=1,maximum do assert(type(rows[index])=='table','Activated mod entry-point row is missing') end
    local index=0
    return function()
      index=index+1
      return rows[index]
    end
  end
end
Controls=controls
ContextPtr=context
if hasRetainedTopPanelUi then LookUpControl=function(path) return context:LookUpControl(path) end end
if hasRetainedTopPanelUi then
  function ZeroSisTopPanelRefresh()
    assert(not topPanelStopped and active and not contextHidden and inputContextName==contextName,
      'TopPanel refresh requires the active nonmodal context')
    assert(type(UpdateData)=='function','Original TopPanel UpdateData is unavailable')
    UpdateData()
    return active and not contextHidden and inputContextName==contextName
  end
  function ZeroSisTopPanelStop()
    if topPanelStopped then return end
    assert(type(OnTopPanelDirty)=='function','Original TopPanel dirty handler is unavailable')
    Events.SerialEventGameDataDirty.Remove(OnTopPanelDirty)
    Events.SerialEventTurnTimerDirty.Remove(OnTopPanelDirty)
    Events.SerialEventCityInfoDirty.Remove(OnTopPanelDirty)
    if not contextHidden then context:SetHide(true) end
    active=false;contextHidden=true;inputContextName=nil
    activeTopPanelTooltip=nil
    topPanelStopped=true
  end
end
Events.SerialEventGameMessagePopupShown.Add(function(info)
  assert(active and ((popupKind=='Production' or hasRetainedTechUi or hasRetainedCaptureUi) and timer==0 or timer==1), 'Shown event outside popup lifecycle')
  if goodyHutRewardState.enabled then
    assert(not goodyHutRewardState.shown and info.Type==ButtonPopupTypes.BUTTONPOPUP_GOODY_HUT_REWARD,
      'Goody-hut reward shown event is duplicate or foreign')
    goodyHutRewardState.shown=true
  end
  lastPopupType=info.Type
  lifecycle[#lifecycle+1]='shown:'..info.Type
end)
Events.SerialEventGameMessagePopupProcessed.Add(function(kind,result)
  if hasRetainedTechUi or hasRetainedTreeUi or hasRetainedCaptureUi then
    assert(researchProcessedPending and not active and contextHidden and timer==0 and result==0 and kind==lastPopupType,
      'Research popup processed event outside the official closed-popup lifecycle')
    researchProcessedPending=false
  elseif goodyHutRewardState.enabled then
    assert(active and timer==0 and goodyHutRewardState.shown and not goodyHutRewardState.processed and
      kind==lastPopupType and kind==ButtonPopupTypes.BUTTONPOPUP_GOODY_HUT_REWARD and result==0,
      'Goody-hut reward processed event is duplicate or outside its original lifecycle')
    goodyHutRewardState.processed=true
  elseif hasRetainedSocialPolicyUi then
    assert(active and timer==0 and kind==ButtonPopupTypes.BUTTONPOPUP_CHOOSEPOLICY and result==0,
      'SocialPolicy processed event outside the original policy popup lifecycle')
  else
    assert(active and ((hasRetainedDeclareWarUi or hasRetainedTradeRouteUi or hasRetainedPantheonUi) and timer==1 or timer==0) and result==0,
      'Processed event outside popup lifecycle')
  end
  lifecycle[#lifecycle+1]='processed:'..kind
end)

local originalRand=assert(Game.Rand)
Game.Rand=function(limit,reason)
  local before=native('randomSeed')
  local value=originalRand(limit,reason)
  draws[#draws+1]={limit=limit,reason=reason,value=value,seedBefore=before,seedAfter=native('randomSeed')}
  return value
end
local function capture(handle,now,parentVisible)
  local value=state(handle)
  local visible=parentVisible~=false and not value.hidden
  local result={key=value.key,kind=value.kind,id=value.attributes.ID or '',attributes=value.attributes,
    hidden=value.hidden,x=value.x,y=value.y,width=value.w,height=value.h,
    text=value.label,tooltip=value.tooltip,texture=value.texture,
    textureX=value.textureX,textureY=value.textureY,children=array()}
  if value.autoSizeRequested then
    result.autoSizeRequested=true
    result.autoSizePolicy='ZEROSIS_RETAINED_TOP_PANEL_TOOLTIP_AUTOSIZE_REQUEST_V1'
    result.retailAutoSizeSemanticsVerified=false
  end
  if value.color then result.color=value.color end
  if value.fgColor then result.fgColor=value.fgColor end
  if value.alpha~=nil then result.alpha=finite(value.alpha) end
  result.disabled=inheritedDisabled(handle)
  if popupKind=='MenuOptions' and value.kind=='Slider' and value.attributes.ID=='EffectsVolumeSlider' and
    type(value.sliderCallback)=='function' then
    result.sliderValue=value.sliderValue or 0
    result.sliderMinimum=0;result.sliderMaximum=1
    result.sliderStyle=layout.menuOptions.sliderStyle
    result.sliderGeometryPolicy='ORIGINAL_HORIZONTAL_SLIDER_STYLE_CANDIDATE_V1'
    result.retailSliderBehaviorVerified=false
  end
  if (hasRetainedCityUi or hasRetainedSocialPolicyUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp') and
     (value.kind=='CheckBox' or value.kind=='RadioButton') then result.checked=value.checked end
  if value.defaultSize then result.defaultSize=value.defaultSize end
  if value.contextFontDefaults then result.contextFontDefaults=value.contextFontDefaults end
  if value.worldPosition then result.worldPosition=value.worldPosition end
  if value.worldGrid then result.worldGrid=value.worldGrid end
  if value.instanceTemplate then result.instanceTemplate=value.instanceTemplate end
  if (hasRetainedSaveMenuUi or popupKind=='MapMenu') and value.kind=='EditBox' then
    result.focused=focusedEditBox==handle;result.caretCodepoint=clamp(value.caret or 0,0,#utf8Characters(value.label))
    result.maxLength=tonumber(value.attributes.MaxLength)
    result.textInputPolicy='UNICODE_SCALAR_INSERT_AT_CARET_MAX32_LITERAL_TEXT'
  end
  if value.styleChildSource then result.styleChildSource=value.styleChildSource end
  if value.originalDataKind then result.originalDataKind=value.originalDataKind end
  if value.ownerPullDownKey then result.ownerPullDownKey=value.ownerPullDownKey end
  if value.parent and pullDown.isChrome(value,state(value.parent)) then
    result.scrollPanelChromeOwnerKey=state(value.parent).key
    result.scrollClipPolicy='PULL_DOWN_CHROME_OUTSIDE_OWN_VIEWPORT_WITHIN_POPUP'
  end
  if value.kind=='PullDown' then
    result.geometryPolicy=pullDown.geometryPolicy
    result.retailGeometryVerified=false
  end
  if (hasRetainedCityUi or hasRetainedDeclareWarUi or hasRetainedNotificationUi) and value.kind=='FlipAnim' then
    local frames=assert(tonumber(value.attributes.FrameCount),'FlipAnim lacks FrameCount')
    local speed=assert(tonumber(value.attributes.Speed),'FlipAnim lacks Speed')
    local sourcePause=finite(tonumber(value.attributes.Pause or '0'))
    local pause=finite(tonumber(value.attributes.EndPause or tostring(math.abs(sourcePause))))
    -- Preserve the source Pause/EndPause distinction while retaining this
    -- end-hold interpretation as an explicit candidate pending retail timing
    -- comparison.
    assert(frames>0 and frames==math.floor(frames) and speed>0 and pause>=0,'Invalid FlipAnim timing')
    local elapsed=hasRetainedNotificationUi and animationElapsed(value.animation,now) or now
    local phase=elapsed%(frames/speed+pause)
    result.animation={clock=now,frame=math.min(frames-1,math.floor(phase*speed)),retailTimingVerified=false,
      sourcePause=sourcePause,endPause=pause,timingPolicy='CIV5_FLIP_NEGATIVE_PAUSE_END_HOLD_CANDIDATE_V1'}
    if hasRetainedNotificationUi then result.animation.elapsed=elapsed;result.animation.running=value.animation.running end
  end
  if value.contentW then result.contentWidth=value.contentW;result.contentHeight=value.contentH end
  if hasRetainedPopupUi and
     (value.kind=='Meter' or value.kind=='TextureBar' or hasRetainedEconomicGeneralUi and value.kind=='Bar') and value.percent~=nil then
    result.percent=value.percent
    if value.percentPlus~=nil then result.percentPlus=value.percentPlus end
  end
  if hasRetainedPopupUi then
    result.sourceAttributes=value.sourceAttributes
    if value.kind=='ShowOnMouseOver' then result.hovered=value.hovered end
    if value.kind=='HideOnMouseOver' then
      assert(hasRetainedSocialPolicyUi,'HideOnMouseOver is only retained for the original SocialPolicy context')
      result.hovered=value.hovered
      result.hoverPolicy='ZEROSIS_RETAINED_SOCIAL_POLICY_INVERSE_HOVER_GATE_V1'
      result.blankAreaHoverVerified=false
    end
    if buttonKind(value.kind) then
      result.buttonState=value.buttonState
    end
    if value.textMeasurementPending then result.textMetricsPending=true end
    if (value.kind=='Label' or value.kind=='TextButton' or (hasRetainedSaveMenuUi or popupKind=='MapMenu') and value.kind=='EditBox') and not value.hidden and
       (not hasRetainedDeclareWarUi or visible) then
      assert(value.textLines and value.fontMetricSource,
        'Popup label lacks measured GGXML layout: '..tostring(value.attributes.ID or value.key))
      local lines=array()
      for _,line in ipairs(value.textLines) do
        lines[#lines+1]={text=line.text,advanceWidth=line.advanceWidth}
      end
      result.textFrame={x=value.x,y=value.y,width=value.w,height=value.h,wrapWidth=value.textWrapWidth,
        lineAdvance=value.textLineAdvance,baselineOffset=value.textBaselineOffset,lines=lines}
      result.fontMetricSource=value.fontMetricSource
    end
    if value.kind=='ScrollPanel' then result.scrollX=value.scrollX;result.scrollY=value.scrollY end
    if value.kind=='ScrollBar' then
      local parent=value.parent and state(value.parent)
      assert(parent and parent.kind=='ScrollPanel','Popup ScrollBar must belong to a ScrollPanel')
      if (hasRetainedCityUi or hasRetainedEconomicChildUi and contextHidden or
        pullDown.deferPackageScroll(value.parent,parent)) and
         not visible and parent.contentW==nil and parent.contentH==nil then
        -- Stock CityView never lays out production help when that section is
        -- hidden. Economic children also defer their first data refresh until
        -- their tab is shown. The original LoadMenu measures its initially
        -- hidden package list only when requested. Preserve these states
        -- without inventing a range; visible scrollbars still require metrics.
        result.scrollMetricsPending=true
        if hasRetainedLoadMenuUi then
          result.scrollMetricsPendingPolicy='ORIGINAL_LOAD_MENU_HIDDEN_PACKAGE_WINDOW_UNMEASURED'
        end
      else
      if parent.attributes.Vertical=='0' and hasRetainedTreeUi then
        result.orientation='horizontal'
        result.scrollX=parent.scrollX
        result.contentWidth=assert(parent.contentW,'ResearchTree ScrollPanel content size has not been calculated')
        result.viewportWidth=parent.w
        result.maximumScroll=math.max(0,result.contentWidth-result.viewportWidth)
        local style=assert(layout.styleDefaults and layout.styleDefaults[value.attributes.Style],
          'ResearchTree ScrollBar lacks frozen horizontal style data')
        local shuttleSize
        for _,child in ipairs(style.children or {}) do
          if child.kind=='Shuttle' and child.attributes.Style=='Grid3Shuttle' then
            shuttleSize=child.attributes.Size;break
          end
        end
        local minimumWidth=select(1,pair(assert(shuttleSize,'ResearchTree ScrollBar lacks official Grid3Shuttle geometry')))
        local trackWidth=value.w
        local thumbWidth=result.contentWidth<=result.viewportWidth and trackWidth or
          math.min(trackWidth,math.max(minimumWidth,trackWidth*result.viewportWidth/result.contentWidth))
        local travel=math.max(0,trackWidth-thumbWidth)
        local thumbX=value.x+(result.maximumScroll>0 and travel*parent.scrollX/result.maximumScroll or 0)
        result.shuttleBounds={x=thumbX,y=value.y,width=thumbWidth,height=value.h}
        result.shuttlePolicy='ZEROSIS_RETAINED_VIEWPORT_PROPORTIONAL_V1'
        result.retailScrollbarGeometryVerified=false
      else
        result.scrollY=parent.scrollY
        result.contentHeight=assert(parent.contentH,'Popup ScrollPanel content size has not been calculated: '..tostring(parent.attributes.ID))
      end
      if hasRetainedTechUi or hasRetainedCityUi or hasRetainedNotificationUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' then
        local shuttle=assert(layout.styleDefaults and layout.styleDefaults[value.attributes.Style],
          'Research ScrollBar lacks frozen VertSlider style data').children
        local shuttleSize
        for _,child in ipairs(shuttle) do
          if child.kind=='Shuttle' and child.attributes.Style=='VertShuttle' then
            shuttleSize=child.attributes.Size;break
          end
        end
        local _,minimumHeight=pair(assert(shuttleSize,'Research VertSlider lacks its official Shuttle geometry'))
        local trackHeight=value.h
        local contentHeight=result.contentHeight
        local thumbHeight=contentHeight<=trackHeight and trackHeight or
          math.min(trackHeight,math.max(minimumHeight,trackHeight*trackHeight/contentHeight))
        local maximumScroll=math.max(0,contentHeight-trackHeight)
        local travel=math.max(0,trackHeight-thumbHeight)
        local thumbY=value.y+(maximumScroll>0 and travel*parent.scrollY/maximumScroll or 0)
        result.shuttleBounds={x=value.x,y=thumbY,width=value.w,height=thumbHeight}
        result.shuttlePolicy='ZEROSIS_RETAINED_VIEWPORT_PROPORTIONAL_V1'
        result.retailScrollbarGeometryVerified=false
      end
      end
    end
    if value.kind=='AlphaAnim' then result.animation={clock=now,alpha=alphaValue(value,now)} end
    if value.kind=='ScrollAnim' then result.animation={clock=now,phase=scrollPhase(value,now)} end
    if hasRetainedGameMenuUi and value.kind=='AlphaAnim' and value.animation.once then
      local phase,elapsed=gameMenuOncePhase(value,now)
      result.animation.elapsed=elapsed;result.animation.normalizedPhase=phase
      result.animation.running=value.animation.running;result.animation.completed=value.animation.completed
      result.animation.activationStartTime=value.animation.activationStartTime
      result.animation.timingPolicy='CIV5_GAME_MENU_ONCE_HOVER_CANDIDATE_V1'
      result.animation.childOpacityPolicy='MULTIPLY_CAPTURED_ALPHA_THROUGH_DESCENDANTS'
      result.animation.retailTimingVerified=false
    end
    if hasRetainedNotificationUi and value.kind=='AlphaAnim' and value.animation.defaultSpeedUsed then
      result.animation.elapsed=animationElapsed(value.animation,now)
      result.animation.running=value.animation.running
      result.animation.effectiveSpeed=value.animation.speed;result.animation.defaultSpeedUsed=true
      result.animation.timingPolicy='CIV5_NOTIFICATION_ONE_BOUNCE_CANDIDATE_V1'
      result.animation.retailTimingVerified=false
    end
    if hasRetainedNotificationUi and value.kind=='SlideAnim' then
      local dx,dy,phase=notificationSlide(value,now)
      result.animation={clock=now,elapsed=animationElapsed(value.animation,now),running=value.animation.running,
        phase=phase,offsetX=dx,offsetY=dy,timingPolicy='CIV5_NOTIFICATION_SLIDE_ROOT_CANDIDATE_V1',
        retailTimingVerified=false,geometryPolicy='CIV5_NOTIFICATION_SLIDE_PARENT_FRAME_CANDIDATE_V1',
        retailGeometryVerified=false}
    end
  end
  local overlay=pullDown.opened and pullDown.owners[pullDown.opened].popup
  for _,child in ipairs(value.children) do
    if child~=overlay then result.children[#result.children+1]=capture(child,now,visible) end
  end
  if handle==root and overlay then
    -- Paint this same retained source subtree once, after the ordinary tree.
    -- Its retained parent still supplies the original PullDown anchor geometry.
    local popup=capture(overlay,now,visible)
    popup.overlayOwnerKey=state(pullDown.opened).key
    popup.overlayPolicy='ROOT_LAST_PAINT_ORIGINAL_PULL_DOWN_SUBTREE'
    result.children[#result.children+1]=popup
  end
  return result
end
local function clippedTargetBounds(value,clips)
  local left,top,right,bottom=value.x,value.y,value.x+value.w,value.y+value.h
  left=math.max(left,0);top=math.max(top,0);right=math.min(right,viewport.w);bottom=math.min(bottom,viewport.h)
  for _,clip in ipairs(clips) do
    left=math.max(left,clip.x);top=math.max(top,clip.y)
    right=math.min(right,clip.x+clip.w);bottom=math.min(bottom,clip.y+clip.h)
  end
  if right<=left or bottom<=top then return nil end
  return {x=left,y=top,width=right-left,height=bottom-top}
end
-- Retained identities behind the original full-screen confirmation must not
-- bypass its ConsumeMouse region. Its later siblings remain above it in the
-- original paint order (notably the touch-help button).
-- The optional input addendum shares this helper in the same Lua chunk.
local function gameMenuInputAllowed(handle)
  if not pullDown.inputAllowed(handle) then return false end
  if hasRetainedPantheonUi then
    return controls.ChooseConfirm:IsHidden() or isDescendant(handle,controls.ChooseConfirm)
  end
  if hasRetainedLoadMenuUi then
    local barrier
    for _,child in ipairs(state(root).children) do
      if (child==controls.DeleteConfirm or child==controls.ReferencedPackagesWindow) and not state(child).hidden then
        barrier=child
      end
    end
    return not barrier or isDescendant(handle,barrier)
  end
  if not hasRetainedGameMenuUi and not hasRetainedSaveMenuUi and popupKind~='MapMenu' then return true end
  local confirmation=assert((hasRetainedSaveMenuUi or popupKind=='MapMenu') and controls.DeleteConfirm or controls.ExitConfirm,
    'Original menu confirmation is missing')
  if state(confirmation).hidden then return true end
  local parent=assert(state(confirmation).parent,'Original GameMenu confirmation has no parent')
  while handle do
    if handle==confirmation then return true end
    local value=states[handle]
    if not value then return false end
    if value.parent==parent then
      local above=false
      for _,sibling in ipairs(state(parent).children) do
        if sibling==confirmation then above=true end
        if sibling==handle then return above end
      end
      return false
    end
    handle=value.parent
  end
  return false
end
local function captureScrollTargets()
  local result=array()
  if not hasRetainedPopupUi or not active or contextHidden or inputContextName~=contextName then return result end
  local function visit(handle,visible,clips)
    local value=state(handle);visible=visible and not value.hidden
    if not visible then return end
    local horizontal=value.kind=='ScrollPanel' and hasRetainedTreeUi and value.attributes.Vertical=='0'
    local vertical=value.kind=='ScrollPanel' and value.attributes.Vertical=='1'
    if (vertical or horizontal) and gameMenuInputAllowed(handle) then
      local clipped=clippedTargetBounds(value,clips)
      if clipped then
        local record={key=value.key,id=value.attributes.ID or '',event='Scroll',visible=true,disabled=false,
          bounds={x=value.x,y=value.y,width=value.w,height=value.h},clippedBounds=clipped}
        if horizontal then
          local contentWidth=finite(assert(value.contentW,'Horizontal ScrollPanel content size has not been calculated'))
          local viewportWidth=finite(value.w);local scrollX=finite(value.scrollX)
          local maximumScroll=math.max(0,contentWidth-viewportWidth)
          assert(contentWidth>=0 and viewportWidth>0 and scrollX>=0 and scrollX<=maximumScroll,
            'Horizontal ScrollPanel retained scroll range is invalid')
          record.orientation='horizontal';record.scrollX=scrollX;record.contentWidth=contentWidth
          record.viewportWidth=viewportWidth;record.maximumScroll=maximumScroll
        else
          local contentHeight=finite(assert(value.contentH,'Vertical ScrollPanel content size has not been calculated'))
          local viewportHeight=finite(value.h);local scrollY=finite(value.scrollY)
          local maximumScroll=math.max(0,contentHeight-viewportHeight)
          assert(contentHeight>=0 and viewportHeight>0 and scrollY>=0 and scrollY<=maximumScroll,
            'Vertical ScrollPanel retained scroll range is invalid')
          record.orientation='vertical';record.scrollY=scrollY;record.contentHeight=contentHeight
          record.viewportHeight=viewportHeight;record.maximumScroll=maximumScroll
        end
        result[#result+1]=record
      end
    end
    local childClips=clips
    if value.kind=='ScrollPanel' then
      childClips={};for _,clip in ipairs(clips) do childClips[#childClips+1]=clip end
      childClips[#childClips+1]={x=value.x,y=value.y,w=value.w,h=value.h}
    end
    for _,child in ipairs(value.children) do visit(child,visible,childClips) end
  end
  visit(root,true,{})
  return result
end
local function consumesMouse(value)
  if (hasRetainedLoadMenuUi or popupKind=='MenuOptions') and value.originalDataKind=='GridData' and value.ownerPullDownKey and
    pullDown.opened and state(pullDown.opened).key==value.ownerPullDownKey then return true end
  if (hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MapMenu') and value.kind=='Box' and value.sourceAttributes.ConsumeMouseOver=='1' and
    (value.attributes.ID=='DeleteConfirm' or hasRetainedLoadMenuUi and value.attributes.ID=='ReferencedPackagesWindow') then return true end
  if hasRetainedExitConfirmUi and value.kind=='Box' and value.attributes.ID=='ExitConfirm' and
    value.sourceAttributes.ConsumeMouseOver=='1' then return true end
  if hasRetainedNotificationUi then
    return value.kind=='Container' and value.sourceAttributes.ConsumeMouseButton=='1'
  end
  return (hasRetainedUnitUi or hasRetainedTopPanelUi or hasRetainedActionInfoUi or hasRetainedGameMenuUi or hasRetainedExitConfirmUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp' or popupKind=='MapMenu') and
    (value.attributes.ConsumeMouse=='1' or value.attributes.ConsumeMouse=='true' or value.attributes.ConsumeMouse=='True')
end
local function captureInputTargets(includeConsumeOverlaps)
  local result=array()
  if not (hasRetainedPopupUi or hasRetainedUnitUi) or not active or contextHidden or inputContextName~=contextName then return result end
  local function visit(handle,visible,clips,hoverVisible)
    local value=state(handle);visible=visible and not value.hidden
    if not visible then return end
    if value.kind=='ShowOnMouseOver' then hoverVisible=hoverVisible and value.hovered end
    if value.kind=='HideOnMouseOver' then hoverVisible=hoverVisible and not value.hovered end
    local leftClickAdded=false
    if popupKind=='MenuOptions' and value.kind=='Slider' and value.attributes.ID=='EffectsVolumeSlider' and
      type(value.sliderCallback)=='function' and not inheritedDisabled(handle) and hoverVisible and gameMenuInputAllowed(handle) then
      local clipped=clippedTargetBounds(value,clips)
      if clipped then result[#result+1]={key=value.key,id=value.attributes.ID,event='SliderValue',
        visible=true,disabled=false,value=value.sliderValue or 0,minimum=0,maximum=1,
        bounds={x=value.x,y=value.y,width=value.w,height=value.h},clippedBounds=clipped,
        void1=value.void1,void2=value.void2,consumeMouse=true} end
    end
    if (buttonKind(value.kind) or (hasRetainedSaveMenuUi or popupKind=='MapMenu') and value.kind=='EditBox') and gameMenuInputAllowed(handle) then
      local disabled=inheritedDisabled(handle)
      for _,eventName in ipairs({Mouse.eLClick,Mouse.eRClick}) do
        if (type(value.callbacks[eventName])=='function' or value.kind=='EditBox' and eventName==Mouse.eLClick) and not disabled and hoverVisible then
          local clipped=clippedTargetBounds(value,clips)
          if clipped then
            result[#result+1]={key=value.key,id=value.attributes.ID or '',event=eventName,
              visible=true,disabled=false,
              bounds={x=value.x,y=value.y,width=value.w,height=value.h},clippedBounds=clipped,
              void1=value.void1,void2=value.void2,toolTipCallback=type(value.toolTipCallback)=='function',
              consumeMouse=consumesMouse(value)}
            if eventName==Mouse.eLClick then leftClickAdded=true end
          end
        end
      end
    end
    if consumesMouse(value) and gameMenuInputAllowed(handle) and (includeConsumeOverlaps or not leftClickAdded) then
      local clipped=clippedTargetBounds(value,clips)
      if clipped then
        result[#result+1]={key=value.key,id=value.attributes.ID or '',event='ConsumeMouse',
          visible=true,disabled=inheritedDisabled(handle),consumeMouse=true,
          bounds={x=value.x,y=value.y,width=value.w,height=value.h},clippedBounds=clipped}
      end
    end
    local childClips=clips
    if value.kind=='ScrollPanel' then
      childClips={};for _,clip in ipairs(clips) do childClips[#childClips+1]=clip end
      childClips[#childClips+1]={x=value.x,y=value.y,w=value.w,h=value.h}
    end
    local overlay=pullDown.opened and pullDown.owners[pullDown.opened].popup
    for _,child in ipairs(value.children) do
      if child~=overlay then
        -- These original O,I arrows live in the reserved strip outside their
        -- own viewport. They still obey all outer clips and the root viewport.
        local clipsForChild=pullDown.isChrome(state(child),value) and clips or childClips
        visit(child,visible,clipsForChild,hoverVisible)
      end
    end
  end
  pullDown.validate()
  if pullDown.opened then
    local owner=state(pullDown.opened)
    result[#result+1]={key=state(root).key,id=state(root).attributes.ID or '',event=Mouse.eLClick,
      inputRole='PullDownDismiss',ownerPullDownKey=owner.key,visible=true,disabled=false,consumeMouse=true,
      bounds={x=0,y=0,width=viewport.w,height=viewport.h},
      clippedBounds={x=0,y=0,width=viewport.w,height=viewport.h}}
  end
  visit(root,true,{},true)
  if pullDown.opened then visit(pullDown.owners[pullDown.opened].popup,true,{},true) end
  return result
end
ZeroSisUi={
  OpenLoadMenu=function()
    assert(hasRetainedLoadMenuUi and not active and contextHidden and timer==0,
      'LoadMenu open requires its inactive original context')
    assert(type(OnBack)=='function' and type(ShowHideHandler)=='function','Original LoadMenu lifecycle is missing')
    draws=array();lifecycle=array()
    ownedSaveDelete.clearConfirmation();ownedSaveDelete.clearDispatch();ownedSaveOverwrite.invalidate()
    UIManager:QueuePopup(context,PopupPriority.LoadMenu)
    for _,id in ipairs({'AutoCheck','CloudCheck'}) do controls[id]:SetDisabled(true) end
    controls.Delete:SetDisabled(not ownedSaveDelete.canDelete());controls.Yes:SetDisabled(true)
    assert(active and not contextHidden and timer==0,'Original LoadMenu changed its parent-owned timer')
  end,
  CloseLoadMenu=function()
    assert(hasRetainedLoadMenuUi,'LoadMenu close requires its original context')
    if not active then assert(timer==0,'Inactive LoadMenu owns a timer');return end
    assert(type(OnBack)=='function','Original LoadMenu OnBack is missing');OnBack()
    assert(not active and contextHidden and timer==0,'Original LoadMenu did not leave its child scope')
  end,
  OpenSaveMenu=function()
    assert(hasRetainedSaveMenuUi and not active and contextHidden and timer==0,
      'SaveMenu open requires its inactive original context')
    assert(type(OnBack)=='function' and type(ShowHideHandler)=='function','Original SaveMenu lifecycle is missing')
    draws=array();lifecycle=array()
    ownedSaveDelete.clearConfirmation();ownedSaveDelete.clearDispatch();ownedSaveOverwrite.invalidate()
    UIManager:QueuePopup(context,PopupPriority.SaveMenu)
    controls.CloudCheck:SetDisabled(true)
    controls.SaveMapButton:SetDisabled(false)
    controls.Delete:SetDisabled(not ownedSaveDelete.canDelete());controls.Yes:SetDisabled(true)
    controls.CloudCheck:SetHide(true)
    controls.SaveButton:SetDisabled(not saveMenuCanSave())
    assert(active and not contextHidden and timer==0,'Original SaveMenu did not enter with the parent timer untouched')
  end,
  CloseSaveMenu=function()
    assert(hasRetainedSaveMenuUi,'SaveMenu close requires its original context')
    if not active then assert(timer==0,'Inactive SaveMenu owns a timer');return end
    assert(type(OnBack)=='function','Original SaveMenu OnBack is missing');OnBack()
    assert(not active and contextHidden and timer==0 and focusedEditBox==nil,'Original SaveMenu did not leave')
  end,
  OpenExitConfirm=function()
    assert(hasRetainedExitConfirmUi and not active and contextHidden and timer==0 and
      not exitConfirmState.opened and not exitConfirmState.closed and not exitConfirmState.opening,
      'ExitConfirm open requires its unused owned modal context')
    exitConfirmState.opening=true
    local ok,err=pcall(function() Events.UserRequestClose() end)
    exitConfirmState.opening=false
    if not ok then error(err,0) end
    assert(active and not contextHidden and exitConfirmState.opened and timer==0,
      'Original ExitConfirm did not open its timer-free modal')
  end,
  CloseExitConfirm=function()
    assert(hasRetainedExitConfirmUi,'ExitConfirm close requires its original context')
    if not active then assert(timer==0,'Closed ExitConfirm retained a timer');return end
    assert(not exitConfirmState.dispatch and type(OnNo)=='function',
      'ExitConfirm owner cancellation cannot interrupt an input callback')
    exitConfirmState.dispatch='Close'
    local ok,err=pcall(OnNo)
    exitConfirmState.dispatch=nil
    if not ok then error(err,0) end
    assert(not active and contextHidden and timer==0,'Original ExitConfirm cancellation failed')
  end,
  OpenGameMenu=function()
    assert(hasRetainedGameMenuUi and not active and contextHidden and timer==0,
      'GameMenu open requires its inactive original context')
    assert(type(OnEnter)=='function' and type(OnReturn)=='function',
      'Original GameMenu lifecycle is missing')
    draws=array();lifecycle=array()
    UIManager:QueuePopup(context,PopupPriority.InGameMenu)
    assert(active and not contextHidden and timer==1,'Original GameMenu did not enter once')
  end,
  ShowGameMenuUnavailable=function(action,message)
    assert(hasRetainedGameMenuUi and active and not contextHidden and timer==1,
      'GameMenu notice requires its live original menu')
    assert(type(action)=='string' and (gameMenuChildren[action] or action=='Restart' or
      action=='Retire' or action=='ExitToMainMenu' or action=='ExitGame'),
      'GameMenu notice has an unknown deferred action')
    message=text(message)
    assert(#message>0 and #message<=4096,'GameMenu notice requires bounded nonempty text')
    -- The host owns this new informational message. The XML and installed Lua
    -- are unchanged; the original No / Escape paths dismiss this retained box.
    Controls.Message:SetText(message)
    gameMenuUnavailableAction=action
    Controls.Yes:SetDisabled(true)
    Controls.ExitConfirm:SetHide(false)
    Controls.BGBlock:SetHide(true)
    flushLayout()
  end,
  CloseGameMenu=function()
    assert(hasRetainedGameMenuUi,'GameMenu close requires its original context')
    if not active then assert(timer==0,'Inactive GameMenu still owns its timer');return end
    if not Controls.ExitConfirm:IsHidden() then
      assert(type(OnNo)=='function','Original GameMenu confirmation cancel is missing')
      OnNo()
      clearGameMenuNotice()
    end
    assert(type(OnReturn)=='function','Original GameMenu OnReturn is missing')
    OnReturn()
    assert(not active and contextHidden and timer==0,'Original GameMenu did not fully leave')
  end,
  Update=function(deltaTime) return context:Update(deltaTime) end,
  GetInputTargets=function(eventName)
    assert(eventName==nil or eventName==Mouse.eLClick or eventName==Mouse.eRClick,
      'Retained input collector received an unsupported mouse event')
    local result={}
    for _,target in ipairs(captureInputTargets()) do
      if eventName==nil or target.event==eventName then result[#result+1]=target end
    end
    return result
  end,
  GetScrollTargets=function()
    local result={}
    for _,target in ipairs(captureScrollTargets()) do result[#result+1]=target end
    return result
  end,
  DispatchLeftClick=function(key)
    assert(type(key)=='number' and key==math.floor(key) and key>0,
      'LeftClick requires a positive exact retained control key')
    if not active or contextHidden or inputContextName~=contextName then return false end
    flushLayout()
    local handle=findVisibleKey(root,key,true)
    if not handle then return false end
    if pullDown.consumeClick(handle) then flushLayout();return true end
    local eligible=false
    for _,target in ipairs(captureInputTargets()) do
      if target.event==Mouse.eLClick and target.key==key then eligible=true;break end
    end
    if not eligible then return false end
    if hasRetainedExitConfirmUi then
      assert((handle==controls.Yes or handle==controls.No) and not exitConfirmState.dispatch,
        'ExitConfirm input must be one original Yes or No callback')
      exitConfirmState.dispatch=handle==controls.Yes and 'Yes' or 'No'
      local ok,consumed=pcall(invokeCallback,handle,Mouse.eLClick)
      exitConfirmState.dispatch=nil
      if not ok then error(consumed,0) end
      if not consumed then return false end
    elseif not handle or not invokeCallback(handle,Mouse.eLClick) then return false end
    if hasRetainedPopupUi then flushLayout() end
    return true
  end,
  DispatchRightClick=function(key)
    assert(hasRetainedActionInfoUi or hasRetainedNotificationUi,
      'Original right-click dispatch requires an action or notification panel')
    assert(type(key)=='number' and key==math.floor(key) and key>0,
      'RightClick requires a positive exact retained control key')
    if not active or contextHidden or inputContextName~=contextName then return false end
    local eligible=false
    for _,target in ipairs(captureInputTargets()) do
      if target.event==Mouse.eRClick and target.key==key then eligible=true;break end
    end
    if not eligible then return false end
    local handle=findVisibleKey(root,key,true)
    if not handle or not invokeCallback(handle,Mouse.eRClick) then return false end
    flushLayout()
    return true
  end,
  DispatchKeyDown=function(key)
    assert(type(key)=='number' and key==math.floor(key) and key>=0,
      'KeyDown requires a nonnegative exact key token')
    if not active or contextHidden or inputContextName~=contextName then return false end
    pullDown.validate()
    if key==Keys.VK_ESCAPE and pullDown.close() then flushLayout();return true end
    if not inputHandler then return false end
    if hasRetainedExitConfirmUi then
      assert(not exitConfirmState.dispatch,'ExitConfirm keyboard callback is already active')
      exitConfirmState.dispatch=key==Keys.VK_ESCAPE and 'Escape' or nil
      local ok,consumed=pcall(inputHandler,KeyEvents.KeyDown,key,0)
      exitConfirmState.dispatch=nil
      if not ok then error(consumed,0) end
      return consumed==true
    end
    return inputHandler(KeyEvents.KeyDown,key,0)==true
  end,
  DispatchPointerMove=function(key)
    assert(type(key)=='number' and key==math.floor(key) and key>=0,
      'PointerMove requires a nonnegative retained control key')
    if not active or contextHidden or inputContextName~=contextName then return false end
    if pullDown.opened and key==state(root).key then
      setHoveredControl(nil,frameTime());flushLayout();return true
    end
    if (hasRetainedGameMenuUi or hasRetainedLoadMenuUi or popupKind=='MenuOptions' or popupKind=='TouchHelp') and key>0 then
      local handle=findVisibleKey(root,key,true)
      if not handle or not gameMenuInputAllowed(handle) then return false end
    end
    local hoveredKey=key>0 and key or nil
    setHoveredControl(hoveredKey,frameTime())
    if hasRetainedTopPanelUi then activeTopPanelTooltip=nil end
    if hasRetainedPopupUi then flushLayout() end
    return true
  end,
  DispatchScroll=function(key,delta)
    assert(type(key)=='number' and key==math.floor(key) and key>0,
      'Scroll requires a positive exact retained control key')
    delta=finite(delta)
    assert(delta~=0 and math.abs(delta)<=32768,'Scroll delta is outside its supported range')
    if not active or contextHidden or inputContextName~=contextName then return false end
    local eligible=false
    for _,target in ipairs(captureScrollTargets()) do if target.key==key then eligible=true;break end end
    if not eligible then return false end
    local handle=findVisibleKey(root,key,true)
    if not handle or state(handle).kind~='ScrollPanel' then return false end
    local value=state(handle)
    if value.attributes.Vertical=='1' then
      value.scrollY=clamp(value.scrollY+delta,0,math.max(0,value.contentH-value.h))
    else
      value.scrollX=clamp(value.scrollX+delta,0,math.max(0,value.contentW-value.w))
    end
    anchor(root);flushLayout()
    return true
  end,
  ToolTip=function(key)
    assert((hasRetainedUnitUi or hasRetainedTopPanelUi) and active and not contextHidden,
      'Tooltip requires an active retained UnitPanel or TopPanel context')
    assert(type(key)=='number' and key==math.floor(key),'Tooltip key must be an integer')
    local handle=assert(findVisibleKey(root,key,true),'Tooltip references an unknown or hidden retained control')
    local value=state(handle)
    assert(type(value.toolTipCallback)=='function','Retained control has no tooltip callback')
    if hasRetainedTopPanelUi then activeTopPanelTooltip='TooltipTypeTopPanel' end
    value.toolTipCallback(handle)
    if hasRetainedTopPanelUi then flushLayout() end
    return true
  end,
  ReturnFromCityView=function()
    assert(hasRetainedCaptureUi and active and captureCityOverlay,'No suspended captured-city context')
    Events.SerialEventExitCityScreen.CallImmediate()
    assert(not captureCityOverlay and inputContextName==contextName,'Original EmptyPopup barrier did not dequeue')
  end,
  FindCaptureButton=function(labelKey)
    assert(hasRetainedCaptureUi and active,'Capture button lookup requires its active original context')
    local label=native('locale',labelKey)
    local found
    for index=1,64 do
      local button=controls['Button'..index]
      if not button then break end
      local textControl=controls['Button'..index..'Text']
      if not button:IsHidden() and textControl and textControl:GetText()==label then
        assert(not found,'Duplicate original captured-city button label')
        assert(type(state(button).callbacks[Mouse.eLClick])=='function','Capture choice lacks original callback')
        found=state(button).key
      end
    end
    return assert(found,'Original captured-city choice is unavailable')
  end,
  FindLeaderBackButton=function()
    assert(hasRetainedLeaderUi and active,'Leader Back lookup requires the active original context')
    local button=assert(controls.BackButton,'Original LeaderHead BackButton is missing')
    local value=state(button)
    local visible=true;local parent=value.parent
    while parent do
      if state(parent).hidden then visible=false;break end
      parent=state(parent).parent
    end
    assert(visible and not button:IsHidden() and not value.disabled,'Original LeaderHead BackButton is not visible and enabled')
    assert(type(value.callbacks[Mouse.eLClick])=='function','Leader Back choice lacks original callback')
    return value.key
  end,
  SubmitLeader=function(message)
    assert(hasRetainedLeaderUi and contextName=='diplomacy','Leader message requires the diplomacy LeaderHead context')
    assert(type(message)=='table','Leader message must preserve the original event payload')
    assert(message.player~=nil and message.state~=nil and message.text~=nil and
      message.animation~=nil and message.data1~=nil,'Leader message is missing an original payload field')
    assert(type(message.text)=='string','Leader message text must be a string')
    assert(not active and timer==0,'Previous popup is still pending')
    lastLeaderMessage={player=message.player,state=message.state,text=message.text,
      animation=message.animation,data1=message.data1}
    draws=array();lifecycle=array();lastPopupType=nil;researchProcessedPending=false
    Events.AILeaderMessage.CallImmediate(message.player,message.state,message.text,message.animation,message.data1)
    assert(active and not contextHidden and timer==0,'Official LeaderHead event did not enter its shown state')
  end,
  WarStateChanged=function(team1,team2,war)
    assert(hasRetainedLeaderUi and contextName=='diplomacy' and active and not contextHidden and
      inputContextName==contextName and timer==0,'WarStateChanged requires the active LeaderHead context')
    local function validTeam(value)
      return type(value)=='number' and value==value and value~=math.huge and value~=-math.huge and
        value>=0 and value==math.floor(value)
    end
    assert(validTeam(team1) and validTeam(team2) and type(war)=='boolean' and
      (team1~=team2 or war==false),
      'WarStateChanged requires nonnegative team IDs and a boolean state; same-team war is invalid')
    Events.WarStateChanged.CallImmediate(team1,team2,war)
  end,
  Submit=function(info)
    assert(not active and timer==0, 'Previous popup is still pending')
    local expected=popupKind=='Production' and ButtonPopupTypes.BUTTONPOPUP_CHOOSEPRODUCTION or
      (hasRetainedTechUi and ButtonPopupTypes.BUTTONPOPUP_CHOOSETECH or
       (hasRetainedTreeUi and ButtonPopupTypes.BUTTONPOPUP_TECH_TREE or
        (hasRetainedTechAwardUi and ButtonPopupTypes.BUTTONPOPUP_TECH_AWARD or
         (hasRetainedCaptureUi and ButtonPopupTypes.BUTTONPOPUP_CITY_CAPTURED or ButtonPopupTypes.BUTTONPOPUP_WHOS_WINNING))))
    if goodyHutRewardState.enabled then
      assert(type(info)=='table' and info.Type==ButtonPopupTypes.BUTTONPOPUP_GOODY_HUT_REWARD and
        type(info.Data1)=='number' and info.Data1>=0 and info.Data1<=2147483647 and info.Data1==math.floor(info.Data1) and
        type(info.Data2)=='number' and info.Data2>=0 and info.Data2<=2147483647 and info.Data2==math.floor(info.Data2),
        'Goody-hut reward requires its original reward ID and nonnegative special value')
      goodyHutRewardState.shown=false;goodyHutRewardState.processed=false
      goodyHutRewardState.rewardId=info.Data1;goodyHutRewardState.specialValue=info.Data2
    elseif hasRetainedDeclareWarUi then
      assert(info.Type==ButtonPopupTypes.BUTTONPOPUP_DECLAREWARMOVE or
        info.Type==ButtonPopupTypes.BUTTONPOPUP_DECLAREWARRANGESTRIKE,
        'DeclareWar context supports only the original move and range-strike popups')
    elseif hasRetainedTradeRouteUi then
      assert(info.Type==ButtonPopupTypes.BUTTONPOPUP_TRADE_ROUTE_OVERVIEW,
        'TradeRoute context supports only the original overview popup')
    elseif hasRetainedPantheonUi then
      assert(info.Type==ButtonPopupTypes.BUTTONPOPUP_FOUND_PANTHEON and info.Data2==1,
        'Pantheon context supports only the original Pantheon mode')
      pantheonState.owner,pantheonState.turn,pantheonState.generation=native('pantheonContext')
      assert(pantheonState.owner==Game.GetActivePlayer() and pantheonState.turn==Game.GetGameTurn() and
        type(pantheonState.generation)=='number' and pantheonState.generation>0,
        'Pantheon popup has no captured current owner, turn or generation')
      pantheonState.submitted=false;pantheonState.dispatch=nil
    elseif hasRetainedSocialPolicyUi then
      assert(info.Type==ButtonPopupTypes.BUTTONPOPUP_CHOOSEPOLICY,
        'SocialPolicy context supports only the original policy popup')
    elseif hasRetainedEconomicParentUi then
      assert(info.Type==ButtonPopupTypes.BUTTONPOPUP_ECONOMIC_OVERVIEW,
        'EconomicOverview context supports only the original economic popup')
    else assert(expected and info.Type==expected, 'Unsupported popup type for selected context') end
    draws=array();lifecycle=array();lastPopupType=nil;researchProcessedPending=false
    Events.SerialEventGameMessagePopup(info)
    assert(active and not contextHidden and ((popupKind=='Production' or hasRetainedTechUi or hasRetainedCaptureUi) and timer==0 or timer==1),
      'Official popup did not enter its shown state')
  end,
  PantheonMetadata=function() return pantheonState.metadata() end,
  GoodyHutRewardMetadata=function()
    local provenance=assert(layout.goodyHutReward,'Goody-hut reward source provenance is required')
    local metadata={};for key,value in pairs(provenance) do metadata[key]=value end
    metadata.rewardId=goodyHutRewardState.rewardId;metadata.specialValue=goodyHutRewardState.specialValue
    metadata.shown=goodyHutRewardState.shown;metadata.processed=goodyHutRewardState.processed
    metadata.timerSemaphore=timer;return metadata
  end,
  Snapshot=function()
    if hasRetainedCityUi and active then
      for _,value in pairs(states) do
        if value.kind=='WorldAnchor' and value.worldGrid then
          local grid=value.worldGrid
          local x,y,z=native('cityPlotPosition',grid.x,grid.y)
          value.worldPosition={x=finite(x)+grid.offsetX,y=finite(y)+grid.offsetY,z=finite(z)+grid.offsetZ}
          layoutDirty=true
        end
      end
    end
    flushLayout()
    local now=hasRetainedPopupUi and frameTime() or nil
    if hasRetainedGameMenuUi then updateAnimations(root,not contextHidden,true,now) end
    if hasRetainedNotificationUi then
      updateAnimations(root,not contextHidden,true,now)
      anchor(root)
      now=notificationLayoutClock
    end
  local snapshot={active=active,timerSemaphore=timer,draws=draws,lifecycle=lifecycle,
      tree=capture(root,now,not (hasRetainedDeclareWarUi or hasRetainedEconomicChildUi) or not contextHidden),
      styleExpansionVerified=false,fontMeasurementVerified=false,rendererVerified=false}
    if hasRetainedUnitUi then
      snapshot.inputTargets=captureInputTargets(true);snapshot.hasRetainedUnitUi=true
      snapshot.contextHidden=contextHidden;snapshot.contextName=contextName;snapshot.popupKind=popupKind
      local variant=assert(layout.layoutVariant,'UnitPanel layout variant is missing')
      assert(variant=='default' or variant=='small','Unsupported UnitPanel layout variant')
      local small=OptionsManager.GetSmallUIAssets()
      assert(type(small)=='boolean' and small==(variant=='small'),
        'UnitPanel layout variant disagrees with the stock small-UI option')
      snapshot.layoutVariant=variant;snapshot.smallUIAssets=small
      snapshot.unitPanel={visible=active and not contextHidden,contextHidden=contextHidden,
        layoutVariant=variant,smallUIAssets=small,retailLayoutVariantSelectionVerified=false}
    end
    if hasRetainedPopupUi then
      snapshot.hasRetainedPopupUi=true
      snapshot.inputTargets=captureInputTargets()
      snapshot.scrollTargets=captureScrollTargets()
      snapshot.contextName=contextName
      snapshot.popupKind=popupKind
      snapshot.presentationClock=now
      local fontMetrics=assert(layout.fontMetrics,'Popup glyphgen metrics are required')
      snapshot.fontMetrics={policy=fontMetrics.policy,
        tabPolicy='ZEROSIS_TAB_FOUR_GGXML_SPACE_ADVANCES_V1',retailTabMetricsVerified=false,
        retailMetricSemanticsVerified=fontMetrics.retailMetricSemanticsVerified,
        wrapPolicy=fontMetrics.wrapPolicy,fonts=fontMetrics.fonts}
      snapshot.styleDefaults=assert(layout.styleDefaults,'Popup style defaults are required')
      snapshot.styleDefaultsSource=assert(layout.styleDefaultsSource,'Popup style defaults provenance is required')
      snapshot.styleDefaultsPolicy=assert(layout.styleDefaultsPolicy,'Popup style defaults policy is required')
      snapshot.groupGeometryPolicy='SHOW_ON_MOUSE_OVER_INHERITS_OWNING_BUTTON_FRAME'
      snapshot.animationPolicy='ZEROSIS_FRONTEND_XML_TIMELINE_V1'
      snapshot.retailTimingVerified=false
      if hasRetainedTechUi or hasRetainedTreeUi then
        snapshot.scrollGeometryPolicy='ZEROSIS_RETAINED_VIEWPORT_PROPORTIONAL_V1'
        snapshot.retailScrollbarGeometryVerified=false
      end
    end
    if hasRetainedLoadMenuUi then
      snapshot.loadMenu={}
      for key,value in pairs(assert(layout.loadMenu,'LoadMenu source contract is required')) do snapshot.loadMenu[key]=value end
      snapshot.loadMenu.controlOnly=false
      snapshot.loadMenu.sourceApisBound=true
      snapshot.loadMenu.nativeVmConnected=false
      snapshot.loadMenu.runtimeIntegrationVerified=false
      snapshot.loadMenu.retailBackendVerified=false
      snapshot.loadMenu.retailLayoutVerified=false
      snapshot.loadMenu.pullDownComponentImplemented=true
      snapshot.loadMenu.frontendStatePolicy='OWNED_LOCAL_INGAME_VIEW_OPAQUE_IDENTITY_NO_RETAIL_NUMERIC_ENUM_CLAIM'
      snapshot.loadMenu.localDeleteImplemented=true
      snapshot.loadMenu.localDeleteBackendBound=ownedSaveDelete.supported
      snapshot.loadMenu.selectedFileCanDelete=ownedSaveDelete.canDelete()
      snapshot.loadMenu.deleteConfirmationVisible=not controls.DeleteConfirm:IsHidden()
      snapshot.loadMenu.deleteConfirmationArmed=ownedSaveDelete.confirmationPath~=nil
      snapshot.loadMenu.unsupportedActions=ownedSaveDelete.supported and {'cloud','automatic-save-filter'} or
        {'cloud','delete','automatic-save-filter'}
      snapshot.pullDowns=pullDown.records()
      snapshot.contextHidden=contextHidden
    end
    if popupKind=='MenuOptions' then snapshot.pullDowns=pullDown.records() end
    if hasRetainedLeaderUi then
      snapshot.leaderMessage=lastLeaderMessage
      snapshot.leaderRootUp=UI.GetLeaderHeadRootUp()
      snapshot.cursorSemanticsVerified=false
      snapshot.retailLeaderRendererVerified=false
    end
    if hasRetainedTopPanelUi then
      local activePlayer=native('activePlayer')
      assert(type(activePlayer)=='number' and activePlayer>=0 and activePlayer==math.floor(activePlayer),
        'activePlayer native operation must return a nonnegative SDK player ID')
      snapshot.contextName='TopPanel';snapshot.popupKind='TopPanel';snapshot.hasRetainedPopupUi=true
      snapshot.nonmodal=true;snapshot.timerSemaphores=0
      snapshot.topPanel={activePlayer=activePlayer,nonmodal=true,timerSemaphores=0}
      snapshot.inputTargets=captureInputTargets()
      snapshot.scrollTargets=array()
      if activeTopPanelTooltip then
        local tooltip=assert(topPanelTooltipRoots[activeTopPanelTooltip])
        snapshot.topPanelTooltip={type=activeTopPanelTooltip,
          tree=capture(tooltip.root,now,true),retailPlacementVerified=false,
          retailAutosizeVerified=false}
      end
    end
    if hasRetainedActionInfoUi then
      local provenance=assert(layout.actionInfoPanel,'ActionInfoPanel source provenance is required')
      local declarations=assert(provenance.unconnectedLuaContexts)
      assert(#declarations==1 and declarations[1].kind=='LuaContext' and
        declarations[1].attributes.ID=='NotificationPanel' and
        declarations[1].attributes.FileName=='Assets/UI/InGame/WorldView/NotificationPanel' and
        #declarations[1].children==0,'Original NotificationPanel declaration changed')
      local unconnected=array()
      unconnected[1]={kind='LuaContext',attributes=declarations[1].attributes,children=array()}
      local owner=Game.GetActivePlayer()
      local player=assert(Players[owner],'ActionInfoPanel has no original active player')
      snapshot.nonmodal=true;snapshot.contextHidden=contextHidden
      snapshot.actionInfoPanel={originalLua=assert(provenance.originalLua),
        originalXml=assert(provenance.originalXml),notificationPanelIntegrated=false,
        unconnectedLuaContexts=unconnected,
        owner=owner,turn=Game.GetGameTurn(),blockingType=player:GetEndTurnBlockingType(),
        blockingNotification=player:GetEndTurnBlockingNotificationIndex(),
        canEndTurn=UI.CanEndTurn(),gameplayFxRendered=false,automaticUnitCyclingIntegrated=false}
      assert(provenance.notificationPanelIntegrated==false,
        'ActionInfoPanel cannot claim an unconnected original NotificationPanel')
    end
    if hasRetainedNotificationUi then
      snapshot.nonmodal=true;snapshot.contextHidden=contextHidden
      snapshot.notificationPanel=assert(ZeroSisUi.notificationPanelMetadata)()
    end
    if snapshot.popupKind=='GoodyHutReward' then
      snapshot.goodyHutReward=ZeroSisUi.GoodyHutRewardMetadata();snapshot.contextHidden=contextHidden
    end
    if snapshot.popupKind=='Pantheon' then
      snapshot.pantheon=ZeroSisUi.PantheonMetadata();snapshot.contextHidden=contextHidden
    end
    if hasRetainedGameMenuUi then
      local provenance=assert(layout.gameMenu,'GameMenu source provenance is required')
      local metadata={}
      for key,value in pairs(provenance) do metadata[key]=value end
      local declarations=array()
      for _,declaration in ipairs(assert(provenance.unconnectedLuaContexts)) do
        local id=declaration.attributes.ID;local value=state(assert(controls[id]))
        assert(gameMenuChildren[id] and value.kind=='LuaContext' and value.hidden and #value.children==0,
          'GameMenu child declaration became instantiated or visible')
        declarations[#declarations+1]={kind='LuaContext',attributes=declaration.attributes,children=array()}
      end
      assert(#declarations==#provenance.unconnectedLuaContexts and provenance.childContextsRuntimeVerified==false and
        provenance.retailLayoutVerified==false,'GameMenu child provenance changed')
      metadata.unconnectedLuaContexts=declarations
      metadata.loadMenuSourceApisBound=true
      metadata.sourceConnectedChildren=provenance.sourceConnectedChildren or {'SaveMenu','LoadMenu'}
      metadata.owner=Game.GetActivePlayer();metadata.turn=Game.GetGameTurn()
      metadata.modal=true;metadata.timerSemaphore=timer
      metadata.confirmationVisible=not Controls.ExitConfirm:IsHidden()
      metadata.unavailableAction=gameMenuUnavailableAction
      metadata.rawMapScript=gameMenuRawMapScript;metadata.databaseMapScript=gameMenuDatabaseMapScript
      snapshot.gameMenu=metadata;snapshot.contextHidden=contextHidden
    end
    if popupKind=='MenuOptions' or popupKind=='TouchHelp' then
      snapshot.menuOptions=ZeroSisUi.MenuOptionsMetadata()
      snapshot.contextHidden=contextHidden
    end
    if popupKind=='MapMenu' then
      snapshot.mapMenu=ZeroSisUi.MapMenuMetadata()
      snapshot.contextHidden=contextHidden
      snapshot.mapMenu.textInputEnabled=ZeroSisUi.IsTextInputEnabled()
      snapshot.mapMenu.textInputFocusToken=ZeroSisUi.GetTextInputFocusToken()
    end
    if popupKind=='ExitConfirm' then
      -- Snapshot already owns root/state/popupKind; reuse them instead of
      -- exceeding Lua 5.1's sixty captured-variable limit in this closure.
      local exitState=assert(state(root).exitConfirmState)
      local metadata={}
      for key,value in pairs(assert(layout.exitConfirm,'ExitConfirm source provenance is required')) do metadata[key]=value end
      metadata.modal=true;metadata.timerSemaphore=timer
      metadata.closed=exitState.closed;metadata.exitSubmitted=exitState.submitted
      snapshot.exitConfirm=metadata;snapshot.contextHidden=contextHidden
    end
    if hasRetainedSaveMenuUi then
      local provenance=assert(layout.saveMenu,'SaveMenu source provenance is required')
      local metadata={};for key,value in pairs(provenance) do metadata[key]=value end
      local name=state(assert(controls.NameBox))
      metadata.owner=Game.GetActivePlayer();metadata.turn=Game.GetGameTurn()
      metadata.modal=true;metadata.timerSemaphore=timer;metadata.parentContext='GameMenu'
      metadata.focusKey=focusedEditBox and state(focusedEditBox).key or 0
      metadata.focusEpoch=editFocusEpoch
      metadata.textInputEnabled=active and not contextHidden and inputContextName==contextName and
        focusedEditBox~=nil and gameMenuInputAllowed(focusedEditBox) and not inheritedDisabled(focusedEditBox)
      metadata.textInputFocusToken=metadata.textInputEnabled and editFocusEpoch or 0
      metadata.name=name.label;metadata.nameAvailable=saveMenuCanCreate();metadata.saveActionAvailable=saveMenuCanSave()
      metadata.catalogCount=type(g_SavedGames)=='table' and #g_SavedGames or 0
      metadata.localDeleteImplemented=true
      metadata.localDeleteBackendBound=ownedSaveDelete.supported
      metadata.selectedFileCanDelete=ownedSaveDelete.canDelete()
      metadata.deleteConfirmationVisible=not controls.DeleteConfirm:IsHidden()
      metadata.deleteConfirmationArmed=ownedSaveDelete.confirmationPath~=nil
      metadata.localOverwriteImplemented=true;metadata.localOverwriteBackendBound=ownedSaveOverwrite.supported
      metadata.mapMenuSourceBound=true
      metadata.overwriteEligible=ownedSaveOverwrite.eligible();metadata.overwriteConfirmationArmed=ownedSaveOverwrite.armed()
      metadata.confirmationOp=ownedSaveOverwrite.operation()
      metadata.unsupportedActions={}
      if not ownedSaveOverwrite.supported then metadata.unsupportedActions[#metadata.unsupportedActions+1]='overwrite' end
      if not ownedSaveDelete.supported then metadata.unsupportedActions[#metadata.unsupportedActions+1]='delete' end
      metadata.unsupportedActions[#metadata.unsupportedActions+1]='cloud'
      metadata.retailTextEditingVerified=false
      metadata.cloudCheckGeometryVerified=false
      metadata.unsupportedCloudCheckHidden=true
      snapshot.saveMenu=metadata;snapshot.contextHidden=contextHidden
    end
    if hasRetainedTradeRouteUi then
      local provenance=assert(layout.tradeRoute,'TradeRoute source provenance is required')
      local stack=state(assert(controls.MainStack,'TradeRoute MainStack control is missing'))
      local scroll=state(assert(controls.MainScroll,'TradeRoute MainScroll control is missing'))
      assert(type(g_CurrentTab)=='string' and
        (g_CurrentTab=='YourTR' or g_CurrentTab=='AvailableTR' or g_CurrentTab=='TRWithYou'),
        'TradeRoute current tab is not an original supported tab')
      snapshot.tradeRoute={activePlayer=Game.GetActivePlayer(),selectedTab=g_CurrentTab,
        visibleRowCount=#stack.children,modal=true,timerSemaphore=timer,
        mainScroll={key=scroll.key,id=scroll.attributes.ID,event='Scroll',orientation='vertical',
          bounds={x=scroll.x,y=scroll.y,width=scroll.w,height=scroll.h},
          clippedBounds=assert(clippedTargetBounds(scroll,{}),'TradeRoute MainScroll is outside the viewport'),
          scrollY=scroll.scrollY,
          contentHeight=assert(scroll.contentH,'TradeRoute MainScroll content size is missing'),
          viewportHeight=scroll.h,maximumScroll=math.max(0,scroll.contentH-scroll.h)},
        rowTemplate=assert(provenance.rowTemplate,'TradeRoute row template identity is required'),
        originalLayoutXml=assert(provenance.originalLayoutXml,'TradeRoute original XML provenance is required'),
        originalLayoutLua=assert(provenance.originalLayoutLua,'TradeRoute original Lua provenance is required'),
        originalHelpersLua=assert(provenance.originalHelpersLua,'TradeRoute helper Lua provenance is required'),
        rowSelectionPresent=false}
    end
    if hasRetainedSocialPolicyUi then
      local activePlayer=Game.GetActivePlayer()
      local player=assert(Players[activePlayer],'SocialPolicy requires the actual active SDK player')
      local policyInfo=OptionsManager.GetPolicyInfo()
      assert(type(policyInfo)=='boolean' and Controls.PolicyInfo:IsChecked()==policyInfo,
        'SocialPolicy option metadata disagrees with the original checkbox state')
      local currentTab
      if g_CurrentTab==g_Tabs.SocialPolicies then currentTab='SocialPolicies'
      elseif g_CurrentTab==g_Tabs.Ideologies then currentTab='Ideologies' end
      assert(currentTab~=nil,'SocialPolicy current tab is not one of the original tabs')
      local policies=array()
      for row in GameInfo.Policies() do
        local id=row.ID
        assert(type(id)=='number' and id>=0 and id==math.floor(id),
          'SocialPolicy policy metadata requires original SDK row IDs')
        policies[#policies+1]={id=id,branch=row.PolicyBranchType or '',has=player:HasPolicy(id),
          canAdopt=player:CanAdoptPolicy(id),blocked=player:IsPolicyBlocked(id)}
      end
      local branches=array()
      for row in GameInfo.PolicyBranchTypes() do
        local id=row.ID
        assert(type(id)=='number' and id>=0 and id==math.floor(id),
          'SocialPolicy branch metadata requires original SDK row IDs')
        branches[#branches+1]={id=id,type=row.Type,unlocked=player:IsPolicyBranchUnlocked(id),
          canUnlock=player:CanUnlockPolicyBranch(id),blocked=player:IsPolicyBranchBlocked(id)}
      end
      -- The stock policy tab visits consecutive numeric rows only up to the
      -- first PurchaseByLevel branch. CanUnlockPolicyBranch itself neither
      -- excludes owned branches nor checks the stock at-least-one-city gate.
      local policyTabBranchIds=array()
      local policyTabBranchId=0
      local policyTabBranch=GameInfo.PolicyBranchTypes[policyTabBranchId]
      while policyTabBranch and not policyTabBranch.PurchaseByLevel do
        assert(policyTabBranchId<100 and policyTabBranch.ID==policyTabBranchId,
          'SocialPolicy tab branch metadata differs from the original numeric row iteration')
        policyTabBranchIds[#policyTabBranchIds+1]=policyTabBranchId
        policyTabBranchId=policyTabBranchId+1
        policyTabBranch=GameInfo.PolicyBranchTypes[policyTabBranchId]
      end
      local provenance=assert(layout.socialPolicy,'SocialPolicy source provenance is required')
      snapshot.socialPolicy={activePlayer=activePlayer,currentTab=currentTab,policyInfo=policyInfo,
        hasCity=player:GetNumCities()>0,policyTabBranchIds=policyTabBranchIds,
        ideology=player:GetLateGamePolicyTree(),freeTenets=player:GetNumFreeTenets(),
        selectedTenet=Controls.TenetConfirm:IsHidden() and -1 or g_SelectedTenet,
        policies=policies,branches=branches,branchSwitchConfirmationPresent=false,
        ideologyChangePresent=not Controls.ChangeIdeologyConfirm:IsHidden(),
        ideologyPaneVisible=not Controls.IdeologyPane:IsHidden(),
        originalLayoutXml=assert(provenance.originalLayoutXml,'SocialPolicy original XML provenance is required'),
        originalLayoutLua=assert(provenance.originalLayoutLua,'SocialPolicy original Lua provenance is required')}
    end
    if hasRetainedEconomicUi then
      snapshot.contextHidden=contextHidden
      snapshot.economicOverview=assert(layout.economicOverview,'Economic source provenance is required')
    end
    -- Preserve the complete retained tree; native encoding has independent
    -- depth/value/output bounds and does not spend Lua opcodes sorting JSON keys.
    return native('snapshotJson',snapshot,arrayType)
  end,
  Close=function()
    assert(active and inputHandler, 'No popup to close')
    local before=native('randomSeed')
    if hasRetainedGameMenuUi then
      ZeroSisUi.CloseGameMenu()
    elseif hasRetainedSaveMenuUi then
      ZeroSisUi.CloseSaveMenu()
    elseif hasRetainedCityUi then
      -- A host/window close means leave the city. Stock Escape in purchase
      -- mode only cancels that mode, so use the stock full-exit event here.
      Events.SerialEventExitCityScreen.CallImmediate()
    else
      assert(inputHandler(KeyEvents.KeyDown,Keys.VK_ESCAPE,0)==true, 'Popup did not accept Escape')
    end
    assert(not active and timer==0, 'Popup did not close with its timer semaphore released')
    assert(native('randomSeed')==before, 'Informational popup close consumed gameplay RNG')
  end,
  AbortCapture=function()
    assert(hasRetainedCaptureUi and active and timer==0,'No capture context to abandon on session shutdown')
    assert(type(HideWindow)=='function','Original GenericPopup hide handler is missing')
    HideWindow()
    assert(not active and timer==0,'Abandoned capture popup failed to close')
  end,
  AbortLeader=function()
    assert(hasRetainedLeaderUi and active and timer==0 and inputHandler,
      'No LeaderHead context to abandon on session shutdown')
    assert(inputHandler(KeyEvents.KeyDown,Keys.VK_ESCAPE,0)==true,
      'Original LeaderHead handler did not accept shutdown Escape')
    assert(not active and timer==0 and not UI.GetLeaderHeadRootUp(),
      'Abandoned LeaderHead popup failed to close cleanly')
  end,
  IsActive=function() return active end,
  FlushLayout=flushLayout,
  ContextName=contextName,
  PopupKind=popupKind,
}
