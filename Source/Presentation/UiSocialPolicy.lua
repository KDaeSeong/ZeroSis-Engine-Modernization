-- Bind the installed BNW SocialPolicyPopup to its real SDK option and command
-- paths. This file is appended to UiScene.lua in the same VM/chunk so the
-- native bridge and live SDK bindings remain owned by the active popup.
assert(hasRetainedSocialPolicyUi and popupKind=='SocialPolicy' and
  contextName=='SocialPolicyPopup',
  'SocialPolicy addendum requires the original SocialPolicyPopup context')

OptionsManager.GetPolicyInfo=function()
  local value=native('policyInfo')
  assert(type(value)=='boolean','policyInfo native operation must return a boolean')
  return value
end

OptionsManager.SetPolicyInfo_Cached=function(value)
  assert(type(value)=='boolean','SetPolicyInfo_Cached requires a boolean')
  native('cachePolicyInfo',value)
end

OptionsManager.CommitGameOptions=function()
  native('commitPolicyInfo')
end

-- The host calls these immediately before touching the SDK receiver, after
-- any Lua callback has unwound. Re-read the active live SDK player and source
-- GameInfo rows each time; never authorize from the renderer snapshot.
function ZeroSisPolicyValidateCommand(id,isPolicy,value)
  if type(id)~='number' or id<0 or id~=math.floor(id) or
     type(isPolicy)~='boolean' or value~=true or not active or contextHidden or timer~=1 then
    return false
  end
  local playerID=Game.GetActivePlayer()
  local player=playerID~=nil and Players[playerID] or nil
  if not player or not player:IsAlive() or not player:IsHuman() then return false end
  if isPolicy then
    return GameInfo.Policies[id]~=nil and player:CanAdoptPolicy(id)
  end
  return GameInfo.PolicyBranchTypes[id]~=nil and player:CanUnlockPolicyBranch(id)
end

function ZeroSisPolicyValidateIdeologyChange()
  if not active or contextHidden or timer~=1 then return false end
  local playerID=Game.GetActivePlayer()
  local player=playerID~=nil and Players[playerID] or nil
  if not player or not player:IsAlive() or not player:IsHuman() then return false end
  local current=player:GetLateGamePolicyTree()
  local preferred=player:GetPublicOpinionPreferredIdeology()
  return type(current)=='number' and current>=0 and current==math.floor(current) and
    type(preferred)=='number' and preferred>=0 and preferred==math.floor(preferred) and
    current~=preferred and GameInfo.PolicyBranchTypes[current]~=nil and
    GameInfo.PolicyBranchTypes[preferred]~=nil and player:GetPublicOpinionUnhappiness()>0
end

-- Read the selection retained by the original ChooseTenet callback. This is
-- diagnostic input provenance; authorization still re-reads the live SDK at
-- the deferred command boundary below.
function ZeroSisPolicySelectedTenet()
  assert(active and not contextHidden and timer==1 and not Controls.TenetConfirm:IsHidden(),
    'Selected tenet requires the original visible confirmation')
  local id=g_SelectedTenet
  assert(type(id)=='number' and id>=0 and id==math.floor(id) and
    GameInfo.Policies[id] and GameInfo.Policies[id].Level>0 and
    ZeroSisPolicyValidateCommand(id,true,true), 'Original selected tenet is not SDK-adoptable')
  return id
end

Network=Network or {}
Network.SendUpdatePolicies=function(...)
  assert(select('#',...)==3,'SendUpdatePolicies requires the original ID/isPolicy/value tuple')
  local id,isPolicy,value=...
  assert(type(id)=='number' and id==math.floor(id) and id>=0 and
    type(isPolicy)=='boolean' and type(value)=='boolean',
    'SendUpdatePolicies requires a nonnegative SDK ID and two booleans')
  assert(ZeroSisPolicyValidateCommand(id,isPolicy,value),
    'Policy request does not match live SDK adoption eligibility')
  return native('updatePolicies',id,isPolicy,value)
end

Network.SendChangeIdeology=function(...)
  assert(select('#',...)==0,'SendChangeIdeology takes no arguments')
  assert(ZeroSisPolicyValidateIdeologyChange(),
    'Ideology change does not match live SDK public-opinion eligibility')
  return native('changeIdeology')
end
