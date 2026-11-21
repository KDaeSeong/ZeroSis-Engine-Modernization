-- Preserve the stock Network.SendResearch surface while routing normal local
-- selections through the owner-scoped Host command. The current local SDK
-- receiver supports only (tech, 0, -1, false); unsupported stock free/steal
-- variants are rejected before any native receiver can mutate state.
local function integer(value,minimum,maximum,message)
  assert(type(value)=='number' and value==math.floor(value) and
    value>=minimum and value<=maximum,message)
  return value
end

local function isOwnedResearchContext()
  if not (ZeroSisUi and type(ZeroSisUi.IsActive)=='function' and ZeroSisUi.IsActive()) then
    return false
  end
  return (ZeroSisUi.PopupKind=='Research' and ZeroSisUi.ContextName=='TechPopup') or
    (ZeroSisUi.PopupKind=='ResearchTree' and ZeroSisUi.ContextName=='TechTree')
end

Network=Network or {}
Network.SendResearch=function(tech,discover,stealFrom,shift,...)
  assert(select('#',...)==0,'Network.SendResearch requires its four original arguments')
  tech=integer(tech,0,2147483647,'Invalid research technology ID')
  discover=integer(discover,0,2147483647,'Invalid free research count')
  stealFrom=integer(stealFrom,-1,2147483647,'Invalid research steal player ID')
  assert(type(shift)=='boolean','Invalid research shift flag')

  assert(isOwnedResearchContext(),
    'Research requires the active owned TechPopup or TechTree')
  local owner=integer(Game.GetActivePlayer(),0,2147483647,'Invalid active research owner')
  local player=assert(Players[owner],'Active research player is missing')
  assert(player:IsHuman() and player:IsAlive() and player:IsTurnActive(),
    'Research owner is not an active human')
  assert(GameInfo.Technologies and GameInfo.Technologies[tech]~=nil,
    'Research technology has no actual rules entry')

  -- Do not coerce free research, espionage theft, or queued selection into a
  -- normal pick. LocalSdkSession currently rejects these tuples pre-dispatch.
  assert(discover==0 and stealFrom==-1 and shift==false,
    'Only normal local research selection is supported')
  assert(player:CanResearch(tech),'Research technology is no longer legal')

  local native=assert(ZeroSisUiNative,'Research native command is unbound')
  return native('sendResearch',tech,discover,stealFrom,shift)
end
