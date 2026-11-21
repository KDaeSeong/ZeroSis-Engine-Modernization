local SOURCE_GUARD=@@SOURCE_GUARD@@
local sends={}
local enabled=true
ZeroSisUi={IsActive=function() return enabled end,PopupKind='Research',ContextName='TechPopup'}
ZeroSisUiNative=function(...)
  sends[#sends+1]={...}
  return 'native-result'
end
Game={GetActivePlayer=function() return 0 end}
local player={
  IsHuman=function() return true end,
  IsAlive=function() return true end,
  IsTurnActive=function() return true end,
  CanResearch=function(self,tech) return tech==7 end,
}
Players={[0]=player}
GameInfo={Technologies={[7]={ID=7},[8]={ID=8}}}
Network={}
assert(loadstring(SOURCE_GUARD,'@ResearchCommandGuard.lua'))()

assert(Network.SendResearch(7,0,-1,false)=='native-result')
assert(#sends==1 and #sends[1]==5 and sends[1][1]=='sendResearch' and
  sends[1][2]==7 and sends[1][3]==0 and sends[1][4]==-1 and sends[1][5]==false,
  'normal research tuple changed before native dispatch')
ZeroSisUi.PopupKind='ResearchTree'
ZeroSisUi.ContextName='TechTree'
assert(Network.SendResearch(7,0,-1,false)=='native-result')
assert(#sends==2 and #sends[2]==5 and sends[2][1]=='sendResearch' and
  sends[2][2]==7 and sends[2][3]==0 and sends[2][4]==-1 and sends[2][5]==false,
  'normal TechTree selection did not preserve its exact false/non-free tuple')
ZeroSisUi.ContextName='TechPopup'
local beforeWrongTreeContext=#sends
local treeContextOk=pcall(Network.SendResearch,7,0,-1,false)
assert(not treeContextOk and #sends==beforeWrongTreeContext,
  'ResearchTree guard accepted a mismatched context name')
ZeroSisUi.PopupKind='Research'
ZeroSisUi.ContextName='TechPopup'

local function rejected(label,...)
  local before=#sends
  local ok,err=pcall(Network.SendResearch,...)
  assert(not ok and #sends==before,label..' was not rejected before native dispatch')
  return tostring(err)
end
local invalid={}
invalid.fractional=rejected('fractional tech',7.5,0,-1,false)
invalid.overflow=rejected('overflow tech',2147483648,0,-1,false)
invalid.unknown=rejected('unknown tech',8,0,-1,false)
invalid.future=rejected('future technology outside CanResearch',8,0,-1,false)
invalid.badDiscover=rejected('fractional discover',7,0.5,-1,false)
invalid.badSteal=rejected('fractional steal player',7,0,1.5,false)
invalid.badShift=rejected('nonboolean shift',7,0,-1,0)
invalid.extra=rejected('extra argument',7,0,-1,false,'extra')
invalid.free=rejected('unsupported free research',7,1,-1,false)
invalid.steal=rejected('unsupported research theft',7,0,1,false)
invalid.shift=rejected('unsupported shift queue',7,0,-1,true)

local savedActive=enabled
enabled=false
invalid.closed=rejected('closed context',7,0,-1,false)
enabled=savedActive
local savedTurn=player.IsTurnActive
player.IsTurnActive=function() return false end
invalid.inactive=rejected('inactive owner turn',7,0,-1,false)
player.IsTurnActive=savedTurn
local savedHuman=player.IsHuman
player.IsHuman=function() return false end
invalid.wrongOwnerKind=rejected('nonhuman owner',7,0,-1,false)
player.IsHuman=savedHuman
local savedLegal=player.CanResearch
player.CanResearch=function() return false end
invalid.illegal=rejected('illegal technology',7,0,-1,false)
player.CanResearch=savedLegal
local savedNative=ZeroSisUiNative
ZeroSisUiNative=nil
invalid.unbound=rejected('unbound native command',7,0,-1,false)
ZeroSisUiNative=savedNative

local rejectedCount=0
for _ in pairs(invalid) do rejectedCount=rejectedCount+1 end
__uiSceneComponentReport='{"status":"PASS_RESEARCH_COMMAND_GUARD_COMPONENT","dispatches":'..tostring(#sends)..
  ',"rejectedCases":'..tostring(rejectedCount)..',"nativeMock":true,"sdkReceiverExecuted":false,"gamecoreExecuted":false}'
