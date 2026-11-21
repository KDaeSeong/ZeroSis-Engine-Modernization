-- Supported front-end and retirement routes on retained original control
-- trees. Host callbacks queue transitions; they never unload Core from Lua.
local MenuLifecycle={}
local function requireFunction(value,name)
  assert(type(value)=='function','Menu lifecycle provider is missing: '..name)
  return value
end
local function copyIdentity(value)
  assert(type(value)=='table' and type(value.owner)=='number' and value.owner>=0 and
    value.owner==math.floor(value.owner) and type(value.turn)=='number' and value.turn>=0 and
    value.turn==math.floor(value.turn) and type(value.generation)=='number' and value.generation>0 and
    value.generation==math.floor(value.generation),'Menu lifecycle identity is invalid')
  return {owner=value.owner,turn=value.turn,generation=value.generation}
end
local function hide(controls,id,value)
  if controls[id] then controls[id]:SetHide(value) end
end

-- Stock MainMenu.lua activates purchased DLC and reads user settings during
-- ShowHideHandler. This isolated host replaces that handler explicitly and
-- retains the shipped controls, textures, labels and ordinary button routes.
function MenuLifecycle.InstallFrontEnd(env,provider)
  assert(type(env)=='table' and type(provider)=='table','Front-end environment/provider missing')
  local controls=assert(env.Controls,'Original MainMenu controls are missing')
  local manager=assert(env.UIManager,'Original UI manager is missing')
  local context=assert(env.ContextPtr,'Original MainMenu context is missing')
  local single=requireFunction(provider.singlePlayer,'singlePlayer')
  local options=requireFunction(provider.options,'options')
  local exitConfirm=requireFunction(provider.exitConfirm,'exitConfirm')
  local cursor=requireFunction(provider.cursor,'cursor')
  local visible=false
  local function live()
    assert(visible and not context:IsHidden(),'Front-end callback requires its visible original menu')
  end
  local function show(isHide,isInit)
    assert(type(isHide)=='boolean' and type(isInit)=='boolean','Front-end visibility flags are invalid')
    visible=not isHide
    if visible then
      controls.Civ5Logo:SetTexture('CivilzationV_Logo.dds')
      cursor(0)
      -- No DLC activation, settings reload, network invitation, or user INI
      -- write occurs at this isolated front-end boundary.
      for _,id in ipairs({'MultiplayerButton','ModsButton','OtherButton','ExpansionRulesSwitch',
        'MapPack2PromoButton','MapPack3PromoButton','BeyondEarthButton'}) do hide(controls,id,true) end
      for _,id in ipairs({'SinglePlayerButton','OptionsButton','ExitButton'}) do
        assert(controls[id],'Original MainMenu button is missing: '..id)
        controls[id]:SetHide(false);controls[id]:SetDisabled(false)
      end
    else controls.Civ5Logo:UnloadTexture() end
  end
  env.SinglePlayerClick=function() live();return single() end
  env.OptionsClick=function() live();return options() end
  env.OnExitGame=function() live();return exitConfirm() end
  for _,row in ipairs({{'SinglePlayerButton','SinglePlayerClick'},{'OptionsButton','OptionsClick'},{'ExitButton','OnExitGame'}}) do
    controls[row[1]]:RegisterCallback(env.Mouse.eLClick,env[row[2]])
  end
  env.ShowHideHandler=show;context:SetShowHideHandler(show)
  return {Show=show,IsVisible=function() return visible end,Context=context,Manager=manager}
end

-- Rebind only GameMenu gameplay controls; original button visibility and
-- OnYes/OnNo confirmation behavior remain owned by the original script.
function MenuLifecycle.InstallGameMenu(env,provider,identity)
  local owner=copyIdentity(identity)
  local request=requireFunction(provider.request,'request')
  local current=requireFunction(provider.identity,'identity')
  local submitted=false
  local function send(action,confirmed)
    assert(not submitted,'A lifecycle command was already submitted from this menu')
    local actual=copyIdentity(current())
    assert(actual.owner==owner.owner and actual.turn==owner.turn and actual.generation==owner.generation,
      'GameMenu lifecycle command lost its opening player, turn, or generation')
    assert(action=='Restart' or action=='Retire' or action=='MainMenu','Unknown GameMenu lifecycle action')
    assert(action~='MainMenu' or confirmed,'Main-menu transition requires original confirmation')
    -- The provider owns availability and may reject without consuming the
    -- menu. It must return a boolean acceptance, never a fabricated success.
    local accepted=request(action,owner.owner,owner.turn,owner.generation)
    assert(type(accepted)=='boolean','Lifecycle provider did not return an acceptance result')
    submitted=accepted
    return accepted
  end
  local controls=assert(env.ControlTypes,'Original gameplay controls are missing')
  env.Game.DoControl=function(kind)
    assert(kind==controls.CONTROL_RESTART_GAME or kind==controls.CONTROL_RETIRE,'Non-menu gameplay control passed to lifecycle')
    return send(kind==controls.CONTROL_RESTART_GAME and 'Restart' or 'Retire',false)
  end
  return {ConfirmedMainMenu=function() return send('MainMenu',true) end,Submitted=function() return submitted end}
end

-- Stock EndGameMenu's fallback loss branch disables continuing a retired
-- game when no victory type is supplied. Child Ranking/Replay/Demographics
-- contexts retain their stock callbacks and require actual host providers.
function MenuLifecycle.InstallEndGame(env,provider,packet)
  local identity=copyIdentity(packet)
  assert(type(packet.finalScore)=='number' and packet.finalScore==math.floor(packet.finalScore) and
    packet.localVictoryRecorded==true and type(packet.replayPath)=='string' and #packet.replayPath>0,
    'End-game context requires a persisted genuine replay and final-score record')
  local request=requireFunction(provider.mainMenu,'mainMenu')
  requireFunction(provider.ranking,'ranking');requireFunction(provider.replay,'replay')
  requireFunction(provider.demographics,'demographics')
  local originalDisplay=requireFunction(env.OnDisplay,'original EndGameMenu.OnDisplay')
  local originalMainMenu=requireFunction(env.OnMainMenu,'original EndGameMenu.OnMainMenu')
  local controls=assert(env.Controls)
  local submitted=false
  local function live()
    assert(not submitted and not env.ContextPtr:IsHidden(),'End-game callback no longer owns its visible context')
  end
  env.OnMainMenu=function()
    live()
    -- The host intercepts the original Events.ExitToMainMenu event after
    -- DequeuePopup has balanced the stock end-game timer semaphore.
    return originalMainMenu()
  end
  local finalScore,replayPath=packet.finalScore,packet.replayPath
  env.OnRanking=function() live();return provider.ranking(copyIdentity(identity),finalScore) end
  env.OnReplay=function() live();return provider.replay(copyIdentity(identity),replayPath) end
  env.OnDemographics=function() live();return provider.demographics(copyIdentity(identity)) end
  for _,row in ipairs({{'MainMenuButton','OnMainMenu'},{'RankingButton','OnRanking'},
    {'ReplayButton','OnReplay'},{'DemographicsButton','OnDemographics'}}) do
    assert(controls[row[1]],'Original EndGameMenu button is missing: '..row[1])
    controls[row[1]]:RegisterCallback(env.Mouse.eLClick,env[row[2]])
  end
  -- Retirement is not a victory enum or a request to revive GAMESTATE_ON.
  controls.BackButton:SetDisabled(true);controls.BackButton:SetHide(true)
  env.OnBack=function() return false end
  controls.BackButton:RegisterCallback(env.Mouse.eLClick,env.OnBack)
  local function confirmed()
    assert(not submitted,'End-game main-menu event was already submitted')
    local accepted=request(identity.owner,identity.turn,identity.generation)
    assert(type(accepted)=='boolean','End-game transition did not return acceptance')
    submitted=accepted;return accepted
  end
  return {Show=function()
    originalDisplay(nil,-1)
    controls.BackButton:SetDisabled(true);controls.BackButton:SetHide(true)
  end,ConfirmedMainMenu=confirmed,Submitted=function() return submitted end}
end

return MenuLifecycle
