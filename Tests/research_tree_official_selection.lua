-- Execute the exact stock TechSelected function with a guarded local SDK mock.
local SOURCE_GUARD = @@SOURCE_GUARD@@
local STOCK_TECH_SELECTED = @@STOCK_TECH_SELECTED@@

local active=true
local nativeTimer=1
local turn=0
local clock=0.25
local seed=9281
local freeTechs=0
local shifted=false
local stealsFrom=-1
local dispatches={}
local dequeueCalls=0
ZeroSisUi={PopupKind='ResearchTree',ContextName='TechTree',
  IsActive=function() return active end}
ZeroSisUiNative=function(...)
  dispatches[#dispatches+1]={...}
  return true
end
Game={GetActivePlayer=function() return 0 end}
player={
  GetNumFreeTechs=function() return freeTechs end,
  IsHuman=function() return true end,
  IsAlive=function() return true end,
  IsTurnActive=function() return true end,
  CanResearch=function(self,tech) return tech==7 end,
}
Players={[0]=player}
GameInfo={Technologies={[7]={ID=7},[8]={ID=8}}}
Network={}
UIManager={GetShift=function() return shifted end,
  DequeuePopup=function() dequeueCalls=dequeueCalls+1;active=false;nativeTimer=0 end}
stealingTechTargetPlayerID=stealsFrom
assert(loadstring(SOURCE_GUARD,'@ResearchCommandGuard.lua'))()
assert(loadstring(STOCK_TECH_SELECTED,'@stock-TechTree-TechSelected.lua'))()

local function state()
  return table.concat({tostring(active),nativeTimer,turn,clock,seed},'|')
end
local before=state()
TechSelected(7,0)
assert(#dispatches==1 and #dispatches[1]==5 and dispatches[1][1]=='sendResearch' and
  dispatches[1][2]==7 and dispatches[1][3]==0 and dispatches[1][4]==-1 and dispatches[1][5]==false,
  'stock TechTree callback did not preserve the exact normal receiver tuple')
assert(state()==before and dequeueCalls==0,
  'stock normal TechTree selection closed or mutated turn, timer, clock or RNG state')

local function rejected(label,callback)
  local count=#dispatches;local snapshot=state();local ok=pcall(callback)
  assert(not ok and #dispatches==count and state()==snapshot and dequeueCalls==0,
    label..' was not rejected before SDK dispatch without mutating popup state')
end
rejected('future tech outside CanResearch',function() TechSelected(8,0) end)
freeTechs=1
rejected('free research selection unsupported by LocalSdkSession',function() TechSelected(7,0) end)
freeTechs=0;shifted=true
rejected('Shift research queue unsupported by LocalSdkSession',function() TechSelected(7,0) end)
shifted=false;stealsFrom=1;stealingTechTargetPlayerID=1
rejected('technology theft unsupported by LocalSdkSession',function() TechSelected(7,0) end)

__uiSceneComponentReport='{"status":"PASS_RESEARCH_TREE_OFFICIAL_SELECTION_PROBE","dispatches":'..
  tostring(#dispatches)..',"rejectedCases":4,"popupRemainedOpen":'..tostring(active)..
  ',"timer":'..tostring(nativeTimer)..',"turn":'..tostring(turn)..',"clock":'..tostring(clock)..
  ',"seed":'..tostring(seed)..',"nativeMock":true,"sdkReceiverExecuted":false,"gamecoreExecuted":false}'
