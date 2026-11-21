-- Actual original popup callbacks plus production retained scene/input code.
-- SDK queries below are explicit component fixtures. No SDK command is applied.
local source=@@SOURCES@@
local layout=@@LAYOUT@@
local popupTypes=@@POPUP_TYPES@@
local checks,cases=0,{}
local arrayTypes={}
local function check(value,message) assert(value,message);checks=checks+1 end
local function clone(value)
  if type(value)~='table' then return value end
  local result={};for key,item in pairs(value) do result[key]=clone(item) end
  return setmetatable(result,getmetatable(value))
end
local function json(value)
  local kind=type(value)
  if kind=='nil' then return 'null' end
  if kind=='boolean' then return tostring(value) end
  if kind=='number' then return string.format('%.17g',value) end
  if kind=='string' then return '"'..value:gsub('[%z\1-\31\\"]',function(ch)
    if ch=='"' then return '\\"' elseif ch=='\\' then return '\\\\' end
    return string.format('\\u%04x',string.byte(ch)) end)..'"' end
  assert(kind=='table','Fixture report accepts no functions or userdata')
  local parts={}
  if arrayTypes[getmetatable(value)] or #value>0 then
    for _,item in ipairs(value) do parts[#parts+1]=json(item) end
    return '['..table.concat(parts,',')..']'
  end
  local names={};for name in pairs(value) do assert(type(name)=='string');names[#names+1]=name end
  table.sort(names);for _,name in ipairs(names) do parts[#parts+1]=json(name)..':'..json(value[name]) end
  return '{'..table.concat(parts,',')..'}'
end
local function node(root,id)
  if root.id==id then return root end
  for _,child in ipairs(root.children or {}) do local found=node(child,id);if found then return found end end
end
local function initialize(options)
  local budget=0
  debug.sethook(function() budget=budget+1000;assert(budget<=8000000,'Pantheon component exceeded instruction budget') end,'',1000)
  options=options or {}
  local state={owner=0,turn=7,generation=11,contextOwner=0,contextTurn=7,applied=0,timer=0,
    requests={},sequence={},hud={},audio={},available=options.empty and {} or {10,11},
    notification={id=71,mandatory=true},capitalPresent=not options.noCapital}
  local beliefRows={[10]={ID=10,ShortDescription='Alpha belief',Description='First original row'},
    [11]={ID=11,ShortDescription='Beta belief',Description='Second original row'},
    [13]={ID=13,ShortDescription='Unavailable belief',Description='Not available'}}
  local env=setmetatable({ZeroSisUiLayout=clone(layout),ButtonPopupTypes=clone(popupTypes),Players={},Teams={[0]={}},
    print=function() end,
    GameDefines={MAX_MAJOR_CIVS=22},GameInfo={Beliefs=beliefRows,Civilizations={},
      IconTextureAtlases=function() return function() return nil end end},
    Game={GetActivePlayer=function() return state.owner end,GetGameTurn=function() return state.turn end,
      Rand=function() error('Pantheon UI must not consume game RNG') end,
      GetAvailablePantheonBeliefs=function() return clone(state.available) end,
      GetAvailableReformationBeliefs=function() error('Reformation is not supported by this component') end}},
    {__index=_G})
  env._G=env
  for id=0,1 do
    local fixed=id
    env.Players[id]={GetID=function() return fixed end,IsHuman=function() return true end,
      IsAlive=function() return true end,IsTurnActive=function() return true end,
      GetCapitalCity=function() return state.capitalPresent and {} or nil end}
  end
  local function run(text,name)
    local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
  end
  env.include=function(name) return run(assert(source[name],'Missing original include '..name),name) end
  env.ZeroSisUiNative=function(operation,...)
    if operation=='uiFrameTime' then return 0.375 end
    if operation=='screenSize' then return 1920,1080 end
    if operation=='randomSeed' then return 17 end
    if operation=='locale' then local value=(...);return tostring(value or '') end
    if operation=='localeCompare' then local a,b=...;return a==b and 0 or a<b and -1 or 1 end
    if operation=='localeLength' then return string.len((...)) end
    if operation=='noBasicHelp' then return false end
    if operation=='civilization' then return -1 end
    if operation=='snapshotJson' then local snapshot,marker=...;arrayTypes[marker]=true;return clone(snapshot) end
    if operation=='timer' then
      local delta=(...);check(delta==1 or delta==-1,'Unexpected timer delta')
      state.timer=state.timer+delta;check(state.timer==0 or state.timer==1,'Unbalanced original popup timer')
      state.sequence[#state.sequence+1]=delta==1 and 'timer:1' or 'timer:0';return
    end
    if operation=='pantheonContext' then return state.contextOwner,state.contextTurn,state.generation,state.applied end
    if operation=='pantheonHudVisibility' then
      local path,hidden=...
      check((path=='/InGame/WorldView/UnitPanel/Base' or path=='/InGame/WorldView/InfoCorner') and
        type(hidden)=='boolean','Original HUD lookup/visibility tuple changed')
      state.hud[path]=hidden;return
    end
    if operation=='foundPantheon' then
      local owner,belief=...
      check(select('#',...)==2 and state.timer==1,'Pantheon request changed tuple or ran after its original callback')
      state.requests[#state.requests+1]={owner=owner,belief=belief,timerAtRequest=state.timer}
      state.sequence[#state.sequence+1]='deferred-request';return
    end
    if operation=='pantheonAudio' then
      check(select('#',...)==1 and (...)=='AS2D_INTERFACE_POLICY','Original policy sound changed')
      state.audio[#state.audio+1]=(...);return
    end
    error('Unexpected native operation in original pantheon fixture: '..tostring(operation))
  end
  run(source.scene..'\n'..source.input,'production-Pantheon-scene')
  run(source.stock,'unchanged-original-BNW-ChoosePantheonPopup.lua')
  env.Events.SerialEventGameMessagePopupProcessed.Add(function(kind,result)
    check(state.timer==1 and result==0,'Original Processed must precede timer release')
    state.sequence[#state.sequence+1]='processed:timer1'
  end)
  local function snapshot() return env.ZeroSisUi.Snapshot() end
  local function target(id)
    local result
    for _,row in ipairs(env.ZeroSisUi.GetInputTargets(env.Mouse.eLClick)) do
      if row.id==id then check(not result,'Duplicate original input target '..id);result=row end
    end
    return assert(result,'Missing original input target '..id)
  end
  local function submit(data2)
    env.ZeroSisUi.Submit({Type=env.ButtonPopupTypes.BUTTONPOPUP_FOUND_PANTHEON,Data1=0,Data2=data2 or 1})
    check(state.timer==1 and snapshot().active,'Original popup failed to acquire its modal lifetime')
  end
  local function click(key)
    return env.ZeroSisUi.DispatchLeftClick(key)
  end
  local function firstRow()
    local result={}
    for _,row in ipairs(env.ZeroSisUi.GetInputTargets(env.Mouse.eLClick)) do
      if row.id=='Button' then result[#result+1]=row end
    end
    table.sort(result,function(a,b) return a.key<b.key end)
    return result[1],#result
  end
  local function selectFirst()
    local first,count=firstRow();check(first and count==2,'Original available belief list changed')
    check(click(first.key),'Original belief callback was not dispatched')
    local shown=snapshot();check(shown.pantheon.confirmationVisible and shown.pantheon.selectedBelief==10,
      'Original selected belief or confirmation state was lost')
    return first,target('Yes'),target('No')
  end
  return {env=env,state=state,snapshot=snapshot,target=target,submit=submit,click=click,firstRow=firstRow,selectFirst=selectFirst}
end
local function completed(name) cases[#cases+1]=name end
local snapshots={}

do
  local c=initialize()
  c.env.OnPopupMessage({Type=c.env.ButtonPopupTypes.BUTTONPOPUP_FOUND_PANTHEON+1,Data1=0,Data2=1})
  check(c.state.timer==0 and #c.state.requests==0,
    'Original popup Type filter accepted a different SDK source enum value')
  completed('original_popup_type_filter_uses_sdk_source_enum')
end
do
  local c=initialize();c.submit()
  snapshots.list=c.snapshot()
  local close=c.target('CloseButton');local row,yes,no=c.selectFirst()
  snapshots.confirmation=c.snapshot()
  check(c.env.ZeroSisUi.PantheonInputObservation(yes.key)==10,'Native input observation lost the actual Yes-entry belief')
  check(not c.click(row.key) and not c.click(close.key) and #c.state.requests==0,
    'Original list or Close callback leaked through the confirmation barrier')
  for _,target in ipairs(c.env.ZeroSisUi.GetInputTargets(c.env.Mouse.eLClick)) do
    check(target.id=='Yes' or target.id=='No','Covered original control remained an input target id='..
      tostring(target.id)..' event='..tostring(target.event)..' key='..tostring(target.key))
  end
  check(c.click(yes.key),'Original OnYes was not dispatched')
  snapshots.closed=c.snapshot()
  check(#c.state.requests==1 and c.state.requests[1].owner==0 and c.state.requests[1].belief==10,
    'Original Network.SendFoundPantheon tuple changed')
  check(not snapshots.closed.active and snapshots.closed.timerSemaphore==0 and c.state.timer==0 and
    c.state.applied==0 and c.state.notification.mandatory,
    'Deferred component fabricated SDK mutation, notification expiration or an open popup')
  check(c.state.sequence[#c.state.sequence-1]=='processed:timer1' and c.state.sequence[#c.state.sequence]=='timer:0',
    'Original Processed/timer release ordering changed')
  check(c.state.hud['/InGame/WorldView/UnitPanel/Base']==false and snapshots.closed.pantheon.hudInfoCornerPresent==false and
    c.state.hud['/InGame/WorldView/InfoCorner']==nil,'Original close lost UnitPanel restoration or fabricated absent InfoCorner')
  check(not c.click(yes.key) and #c.state.requests==1,'Destroyed Yes callback duplicated its request')
  local ok=pcall(c.env.Network.SendFoundPantheon,0,10)
  check(not ok and #c.state.requests==1,'Direct post-close Network call bypassed callback admission')
  completed('original_list_confirmation_yes_exact_deferred_tuple_and_close')
end
do
  local c=initialize();c.submit();local row,yes,no=c.selectFirst()
  check(c.click(no.key) and not c.snapshot().pantheon.confirmationVisible and #c.state.requests==0,
    'Original No emitted a command or retained confirmation')
  check(not c.click(yes.key) and #c.state.requests==0,'Hidden Yes accepted an old key after No')
  check(c.click(c.target('CloseButton').key) and c.state.timer==0,'Original Close failed after No')
  completed('original_no_and_hidden_yes_are_command_free')
end
for _,mode in ipairs({'escape-confirm','escape-close','close','dirty'}) do
  local c=initialize();c.submit()
  if mode=='escape-confirm' then
    c.selectFirst();check(c.env.ZeroSisUi.DispatchKeyDown(c.env.Keys.VK_ESCAPE),'Original confirmation Escape failed')
    check(c.snapshot().active and not c.snapshot().pantheon.confirmationVisible,'Escape did not dismiss only the confirmation')
    c.env.ZeroSisUi.DispatchKeyDown(c.env.Keys.VK_ESCAPE)
  elseif mode=='escape-close' then c.env.ZeroSisUi.DispatchKeyDown(c.env.Keys.VK_ESCAPE)
  elseif mode=='close' then c.click(c.target('CloseButton').key)
  else c.env.Events.UnitSelectionChanged(0,1,true,false) end
  check(not c.snapshot().active and c.state.timer==0 and #c.state.requests==0,'Cancel/dirty callback issued a command or retained modal state')
  completed('original_'..mode..'_command_free')
end
for _,mode in ipairs({'owner','turn','generation','owner-event'}) do
  local c=initialize();c.submit();local row,yes=c.selectFirst()
  if mode=='owner' then c.state.owner=1
  elseif mode=='turn' then c.state.turn=8
  elseif mode=='generation' then c.state.generation=12
  else c.state.owner=1;c.env.Events.GameplaySetActivePlayer(1,0) end
  local ok,result=pcall(c.click,yes.key)
  check((not ok or result==false) and #c.state.requests==0,'Stale owner/turn/generation reached deferred command boundary')
  completed('actual_production_'..mode..'_stale_admission_reject')
end
do
  local c=initialize()
  local ok=pcall(c.submit,0)
  check(not ok and c.state.timer==0 and #c.state.requests==0,'Reformation Data2=0 entered pantheon mode')
  completed('reformation_mode_rejected')
end
do
  local c=initialize();c.submit()
  for _,args in ipairs({{0,10},{0,-1},{-1,10},{0,10.5},{0,999},{1,10},{0,10,7}}) do
    local ok=pcall(c.env.Network.SendFoundPantheon,unpack(args))
    check(not ok and #c.state.requests==0,'Direct, invalid or extra-argument Network call bypassed original Yes entry')
  end
  completed('direct_network_calls_cannot_manufacture_yes_entry')
end
do
  local c=initialize();c.submit()
  local ok=pcall(c.env.SelectPantheon,999)
  check(not ok and #c.state.requests==0,'Unknown GameInfo belief fabricated a request')
  local row,yes=c.selectFirst();c.env.g_BeliefID=-1
  ok=pcall(c.click,yes.key)
  check(not ok and #c.state.requests==0,'Malformed selected belief reached native boundary')
  completed('unknown_and_negative_selected_belief_rejected')
end
do
  local c=initialize({empty=true});c.submit()
  local first,count=c.firstRow();check(not first and count==0,'Unavailable beliefs acquired original row callbacks')
  check(not c.snapshot().pantheon.confirmationVisible and #c.state.requests==0,'Empty list fabricated confirmation')
  c.click(c.target('CloseButton').key);completed('empty_available_belief_list_has_no_selection')
end
do
  local c=initialize({noCapital=true});c.submit();local row,yes=c.selectFirst();c.click(yes.key)
  check(#c.state.requests==1 and c.state.applied==0,'Missing-capital fixture must remain deferred and must not manufacture SDK success')
  completed('capital_absent_fixture_is_not_sdk_acceptance')
end
local report=json({checks=checks,cases=cases,snapshots=snapshots,actual_original_callbacks=true,
  production_scene_and_input_executed=true,network_payload_is_deferred=true,
  nativeSdkReceiverExecuted=false,commandsApplied=0,notificationExpirationVerified=false,
  backend_live_cases_unverified={'capital_absent','canCreatePantheon_false','belief_no_longer_available',
    'already_has_pantheon','faith_consumption','notification_expiration','SDK_RNG_state'}})
debug.sethook()
return report
