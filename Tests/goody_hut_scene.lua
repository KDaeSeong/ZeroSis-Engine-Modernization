-- Execute the unchanged BNW popup against production retained scene/input code.
-- GameInfo and localization are explicit component fixtures, never SDK proof.
local source,layout,popupTypes=@@SOURCES@@,@@LAYOUT@@,@@POPUP_TYPES@@
local sharedFonts,selectedGlyphCount=@@SHARED_FONTS@@,@@SELECTED_GLYPH_COUNT@@
local checks,cases,arrayTypes=0,{},{}
local function check(value,message) assert(value,message);checks=checks+1 end
local sharedChecks=0
local function checkShared(value,message) assert(value,message);sharedChecks=sharedChecks+1 end
local function clone(value)
  if type(value)~='table' then return value end
  local result={};for key,item in pairs(value) do result[key]=clone(item) end
  return setmetatable(result,getmetatable(value))
end
local function equal(left,right)
  if type(left)~=type(right) then return false end
  if type(left)~='table' then return left==right end
  for key,value in pairs(left) do if not equal(value,right[key]) then return false end end
  for key in pairs(right) do if left[key]==nil then return false end end
  return true
end
local sharedMode=layout.fontMetrics.glyphSetStorage=='ZEROSIS_UI_SHARED_GLYPH_SETS_V1'
local sharedBankBefore=sharedMode and clone(sharedFonts) or nil
local sharedProof={used=sharedMode,private_layout_resolved=false,selected_glyph_count=0,
  input_layout_and_bank_unchanged=true}
local function inspectSharedResolution(env)
  if not sharedMode then return end
  checkShared(env.ZeroSisUiLayout.fontMetrics.glyphSets==nil and
    equal(env.ZeroSisUiLayout,layout),'Production scene mutated its compact global layout')
  if sharedProof.private_layout_resolved then return end
  -- Inspect the production closure, never substitute an expanded fixture layout.
  local privateLayout
  for index=1,60 do
    local name,value=debug.getupvalue(env.ZeroSisUi.Snapshot,index)
    if name==nil then break end
    if name=='layout' then privateLayout=value;break end
  end
  checkShared(type(privateLayout)=='table' and privateLayout~=env.ZeroSisUiLayout,
    'Shared metrics were not normalized into the production private layout')
  local resolved=assert(privateLayout.fontMetrics.glyphSets)
  local count,sets=0,0
  for identity,glyphs in pairs(resolved) do
    sets=sets+1
    checkShared(rawequal(glyphs,sharedFonts.glyphSets[identity]),
      'Production normalization changed or copied a shared glyph map')
    for codepoint in pairs(glyphs) do
      checkShared(type(codepoint)=='number' and codepoint==math.floor(codepoint),
        'Actual Lua shared bank retained a JSON string codepoint')
      count=count+1
    end
  end
  checkShared(sets==#layout.fontMetrics.glyphSetRefs and count==selectedGlyphCount,
    'Production normalization dropped selected source glyphs or added unrelated sets')
  sharedProof.private_layout_resolved=true;sharedProof.selected_glyph_count=count
end
local function json(value)
  local kind=type(value)
  if kind=='nil' then return 'null' end
  if kind=='boolean' then return tostring(value) end
  if kind=='number' then return string.format('%.17g',value) end
  if kind=='string' then return '"'..value:gsub('[%z\1-\31\\"]',function(ch)
    if ch=='"' then return '\\"' elseif ch=='\\' then return '\\\\' end
    return string.format('\\u%04x',string.byte(ch)) end)..'"' end
  assert(kind=='table','Component report accepts tables and scalar values only')
  local parts={}
  if arrayTypes[getmetatable(value)] or #value>0 then
    for _,item in ipairs(value) do parts[#parts+1]=json(item) end
    return '['..table.concat(parts,',')..']'
  end
  local keys={};for key in pairs(value) do assert(type(key)=='string');keys[#keys+1]=key end
  table.sort(keys);for _,key in ipairs(keys) do parts[#parts+1]=json(key)..':'..json(value[key]) end
  return '{'..table.concat(parts,',')..'}'
end
local function node(root,id)
  if root.id==id then return root end
  for _,child in ipairs(root.children or {}) do local found=node(child,id);if found then return found end end
end
local function frame(root)
  if root.kind=='Grid' and root.sourceAttributes.Size=='400,270' then return root end
  for _,child in ipairs(root.children or {}) do local found=frame(child);if found then return found end end
end
local rewards={
  {id=0,kind='GOODY_GOLD',value=75,text='Recovered %d Gold',expected='Recovered 75 Gold'},
  {id=2,kind='GOODY_CULTURE',value=30,text='Recovered %d Culture',expected='Recovered 30 Culture'},
  {id=3,kind='GOODY_PANTHEON_FAITH',value=20,text='Recovered %d Pantheon Faith',expected='Recovered 20 Pantheon Faith'},
  {id=4,kind='GOODY_PROPHET_FAITH',value=60,text='Recovered %d Prophet Faith',expected='Recovered 60 Prophet Faith'},
  {id=5,kind='GOODY_MAP',value=999,text='Nearby land revealed',expected='Nearby land revealed'},
}
local costs={}
local function budget(name,fn)
  local count=0
  debug.sethook(function() count=count+1000;assert(count<=8000000,'GoodyHut component exceeded instruction budget') end,'',1000)
  local ok,result=pcall(fn);debug.sethook();costs[name]=math.max(costs[name] or 0,count)
  if not ok then error(result,0) end
  return result
end
local function initialize()
  local state={timer=0,increments=0,decrements=0,shown=0,processed=0,seed=1789,rngCalls=0,
    commands=0,locale={},sequence={}}
  local function forbidden(name)
    return function() state.commands=state.commands+1;error('Informational reward attempted '..name) end
  end
  local rows,translations={},{}
  for _,reward in ipairs(rewards) do
    local key='FIXTURE_'..reward.kind
    rows[reward.id]={ID=reward.id,Type=reward.kind,Description=key}
    translations[key]=reward.text
  end
  local game={GetActivePlayer=function() return 0 end,GetGameTurn=function() return 0 end,
    Rand=function() state.rngCalls=state.rngCalls+1;error('Reward popup consumed game RNG') end}
  setmetatable(game,{__index=function(_,name) return forbidden('Game.'..tostring(name)) end})
  local env=setmetatable({ZeroSisUiLayout=clone(layout),ButtonPopupTypes=clone(popupTypes),
    GameInfo={GoodyHuts=rows},Game=game,Players={},Teams={},
    Network=setmetatable({},{__index=function(_,name) return forbidden('Network.'..tostring(name)) end}),
    print=function() end},{__index=_G})
  env._G=env
  if sharedMode then env.ZeroSisUiSharedFontMetrics=sharedFonts end
  -- Native Lua io/package/os entry points would bypass Python's audit hook.
  for _,library in ipairs({'io','os','package'}) do
    env[library]=setmetatable({},{__index=function(_,name) return forbidden(library..'.'..tostring(name)) end})
  end
  env.require=forbidden('require');env.dofile=forbidden('dofile');env.loadfile=forbidden('loadfile')
  local function run(text,name)
    local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
  end
  env.include=function(name) error('Unchanged GoodyHutPopup requires no includes: '..tostring(name)) end
  env.ZeroSisUiNative=function(operation,...)
    if operation=='screenSize' then return 1920,1080 end
    if operation=='uiFrameTime' then return 0.25 end
    if operation=='randomSeed' then return state.seed end
    if operation=='snapshotJson' then
      local snapshot,marker=...;arrayTypes[marker]=true;return clone(snapshot)
    end
    if operation=='locale' then
      local key,value=...
      if translations[key] then
        state.locale[#state.locale+1]={key=key,count=select('#',...)-1,value=value}
        return string.format(translations[key],select(2,...))
      end
      if key=='TXT_KEY_CLOSE' then return 'Close' end
      if key=='TXT_KEY_POP_RUINS_EXPLORED' then return 'Ancient ruins explored' end
      return tostring(key or '')
    end
    if operation=='timer' then
      local delta=(...)
      check(select('#',...)==1 and (delta==1 or delta==-1),'Original timer tuple changed')
      state.timer=state.timer+delta
      if delta==1 then state.increments=state.increments+1 else state.decrements=state.decrements+1 end
      check(state.timer==0 or state.timer==1,'Original popup timer became unbalanced')
      state.sequence[#state.sequence+1]=delta==1 and 'increment' or 'decrement';return
    end
    state.commands=state.commands+1;error('Unexpected reward native operation: '..tostring(operation))
  end
  budget('initialization',function()
    run(source.scene..'\n'..source.input,'production-GoodyHutReward-scene')
    run(source.stock,'unchanged-original-GoodyHutPopup.lua')
  end)
  inspectSharedResolution(env)
  env.Events.SerialEventGameMessagePopupShown.Add(function(info)
    check(info==state.submitted and info.Data1==state.submitted.Data1 and info.Data2==state.submitted.Data2,
      'Original Shown lost the exact SDK reward packet')
    check(info.Data3==-1 and info.Option1==false and info.Option2==false and state.timer==1,
      'Original ignored fields or Shown/timer ordering changed')
    state.shown=state.shown+1;state.sequence[#state.sequence+1]='shown'
  end)
  env.Events.SerialEventGameMessagePopupProcessed.Add(function(kind,result)
    check(kind==popupTypes.BUTTONPOPUP_GOODY_HUT_REWARD and result==0 and state.timer==0 and env.ZeroSisUi.IsActive(),
      'Original Processed(type,0) must occur after decrement inside its one close')
    state.processed=state.processed+1;state.sequence[#state.sequence+1]='processed'
  end)
  local function snapshot() return budget('snapshot',env.ZeroSisUi.Snapshot) end
  local function submit(reward)
    local packet={Type=popupTypes.BUTTONPOPUP_GOODY_HUT_REWARD,Data1=reward.id,Data2=reward.value,
      Data3=-1,Option1=false,Option2=false}
    state.submitted=packet;budget('submit',function() env.ZeroSisUi.Submit(packet) end)
    return packet
  end
  local function closeTarget()
    local found,targets=nil,env.ZeroSisUi.GetInputTargets(env.Mouse.eLClick)
    for _,target in ipairs(targets) do
      check(target.id=='CloseButton','Informational reward invented a choice or action')
      check(not found,'Original CloseButton has duplicate callbacks');found=target
    end
    return assert(found,'Original CloseButton callback is missing')
  end
  return {env=env,state=state,snapshot=snapshot,submit=submit,closeTarget=closeTarget}
end
local function noMutation(c)
  check(c.state.commands==0 and c.state.rngCalls==0 and c.state.seed==1789,
    'Informational reward mutated an SDK command, reward or RNG')
end
local snapshots,snapshotPacket={},nil
for index,reward in ipairs(rewards) do
  for _,close in ipairs({'button','escape','return'}) do
    local c=initialize()
    check(not c.env.ZeroSisUi.DispatchKeyDown(27) and not c.env.ZeroSisUi.DispatchLeftClick(1),
      'Unshown reward admitted input')
    local packet=c.submit(reward);local shown=c.snapshot();local target=c.closeTarget()
    check(shown.active and shown.timerSemaphore==1 and shown.contextName=='GoodyHutPopup' and
      shown.popupKind=='GoodyHutReward' and shown.rendererVerified==false,'Reward context or native acceptance changed')
    check(shown.goodyHutReward.rewardId==reward.id and shown.goodyHutReward.specialValue==reward.value and
      shown.goodyHutReward.rewardAlreadyApplied and shown.goodyHutReward.nativeAcceptanceVerified==false,
      'Reward metadata lost the actual tuple or overstated native acceptance')
    checkShared(shown.fontMetrics.glyphSets==nil and shown.fontMetrics.glyphSetRefs==nil and
      shown.fontMetrics.glyphSetStorage==nil and shown.fontMetrics.sharedProfileId==nil,
      'Runtime snapshot leaked shared transport or full glyph tables')
    check(node(shown.tree,'DescriptionLabel').text==reward.expected,'Original reward description changed: '..reward.kind)
    local localized=c.state.locale[#c.state.locale]
    check(localized and localized.key=='FIXTURE_'..reward.kind and
      localized.count==(reward.kind=='GOODY_MAP' and 0 or 1) and
      (reward.kind=='GOODY_MAP' or localized.value==reward.value),'Original Data2 localization arguments changed')
    check(packet.Data1==reward.id and packet.Data2==reward.value and c.state.shown==1 and
      c.state.increments==1 and c.state.decrements==0 and c.state.processed==0,'Reward tuple or one-show contract changed')
    local box,button=assert(frame(shown.tree)),assert(node(shown.tree,'CloseButton'))
    check(button.y>=box.y+box.height-0.001 and button.width==200 and button.height==36,
      'Original CloseButton outside the 400x270 grid was clipped or moved')
    local hit
    for _,candidate in ipairs(shown.inputTargets) do
      if candidate.key==target.key and candidate.event==c.env.Mouse.eLClick then
        check(not hit,'Original CloseButton has duplicate physical hit targets');hit=candidate
      end
    end
    check(hit and target.key==button.key and hit.bounds.x==button.x and hit.bounds.y==button.y and
      hit.bounds.width==button.width and hit.bounds.height==button.height and
      button.x>=0 and button.y>=0 and button.x+button.width<=1920 and button.y+button.height<=1080,
      'Original outside-grid close hit did not retain its 1920x1080 control bounds')
    check(not c.env.ZeroSisUi.DispatchLeftClick(target.key+1000000) and
      not c.env.ZeroSisUi.DispatchLeftClick(target.key,c.env.Mouse.eRClick) and
      not c.env.ZeroSisUi.DispatchKeyDown(65),'Stale key, unsupported right click or unrelated key closed the reward')
    check(not pcall(c.env.ZeroSisUi.Submit,packet),'Repeated active reward submission was accepted')
    check(not pcall(c.env.Events.SerialEventGameMessagePopupProcessed.CallImmediate,
      popupTypes.BUTTONPOPUP_GOODY_HUT_REWARD,0),'Processed was accepted before its original close/decrement')
    check(c.snapshot().active and c.state.shown==1 and c.state.increments==1 and c.state.processed==0,
      'Rejected repeated input changed the active reward lifetime')
    if close=='button' then check(c.env.ZeroSisUi.DispatchLeftClick(target.key),'Original CloseButton failed')
    else check(c.env.ZeroSisUi.DispatchKeyDown(close=='escape' and 27 or 13),'Original Escape/Return failed') end
    local closed=c.snapshot()
    check(not closed.active and closed.timerSemaphore==0 and c.state.timer==0 and c.state.shown==1 and
      c.state.increments==1 and c.state.decrements==1 and c.state.processed==1,'Original reward did not close exactly once')
    check(table.concat(c.state.sequence,',')=='increment,shown,decrement,processed','Original lifecycle ordering changed')
    check(not c.env.ZeroSisUi.DispatchLeftClick(target.key) and not c.env.ZeroSisUi.DispatchKeyDown(27) and
      not c.env.ZeroSisUi.DispatchKeyDown(13) and not c.env.ZeroSisUi.DispatchPointerMove(target.key) and
      #c.env.ZeroSisUi.GetInputTargets()==0,'Closed reward accepted retained input')
    c.env.OnCloseButtonClicked();c.env.Events.GameplaySetActivePlayer(1)
    check(c.state.decrements==1 and c.state.processed==1,'Repeated original close duplicated timer or Processed')
    check(not pcall(c.env.Events.SerialEventGameMessagePopupProcessed.CallImmediate,
      popupTypes.BUTTONPOPUP_GOODY_HUT_REWARD,0) and c.state.processed==1,
      'Duplicate closed Processed event was admitted')
    noMutation(c)
    cases[#cases+1]=reward.kind..'_'..close
    if index==1 and close=='button' then
      snapshots.shown=shown;snapshots.closed=closed;snapshotPacket=clone(packet)
    end
  end
end
local malformed={
  {name='wrong_type',Type=popupTypes.BUTTONPOPUP_GOODY_HUT_REWARD+1,Data1=0,Data2=75},
  {name='negative_id',Data1=-1,Data2=75},{name='fractional_id',Data1=0.5,Data2=75},
  {name='missing_id',Data2=75},{name='string_id',Data1='0',Data2=75},
  {name='unknown_row',Data1=99,Data2=75},{name='negative_amount',Data1=0,Data2=-1},
  {name='fractional_amount',Data1=0,Data2=1.5},{name='missing_amount',Data1=0},
  {name='string_amount',Data1=0,Data2='75'},{name='nan_amount',Data1=0,Data2=0/0},
  {name='infinite_amount',Data1=0,Data2=math.huge},
  {name='nan_id',Data1=0/0,Data2=75},{name='overflow_id',Data1=2147483648,Data2=75},
  {name='overflow_amount',Data1=0,Data2=2147483648},{name='boolean_amount',Data1=0,Data2=true},
}
for _,packet in ipairs(malformed) do
  local c=initialize();packet.Type=packet.Type or popupTypes.BUTTONPOPUP_GOODY_HUT_REWARD
  packet.Data3=-1;packet.Option1=false;packet.Option2=false
  check(not pcall(c.env.ZeroSisUi.Submit,packet),'Malformed reward was accepted: '..packet.name)
  check(not c.env.ZeroSisUi.IsActive() and c.state.timer==0 and c.state.shown==0 and c.state.processed==0 and
    c.state.increments==0 and c.state.decrements==0,'Malformed reward partially acquired a popup lifetime: '..packet.name)
  noMutation(c);cases[#cases+1]='reject_'..packet.name
end
do
  local c=initialize()
  c.env.OnPopup({Type=popupTypes.BUTTONPOPUP_GOODY_HUT_REWARD+1,Data1=0,Data2=75})
  check(not c.env.ZeroSisUi.IsActive() and c.state.timer==0,'Unchanged original popup lost its Type filter')
  noMutation(c);cases[#cases+1]='original_type_filter'
end
if sharedMode then
  sharedProof.input_layout_and_bank_unchanged=equal(sharedFonts,sharedBankBefore)
  checkShared(sharedProof.input_layout_and_bank_unchanged,'Production scene mutated the shared bank')
end
return json({checks=checks,cases=cases,snapshots=snapshots,snapshot_reward_packet=snapshotPacket,instruction_counts=costs,
  shared_font_transport=sharedProof,shared_font_checks=sharedChecks,
  actual_original_popup_executed=true,production_scene_and_input_executed=true,
  reward_already_applied_fixture=true,reward_grants=0,sdk_commands=0,rng_calls=0,
  native_scene_generation_verified=false,native_pixels_verified=false,live_sdk_verified=false})
