-- One retained scene per original Lua VM. The C++ owner composes the parent
-- and two children after callbacks unwind; this file never shares Lua globals.
assert(hasRetainedEconomicUi,'Economic addendum requires an original economic context')
local economicProvenance=assert(layout.economicOverview,'Economic layout provenance is missing')
local economicRole=hasRetainedEconomicParentUi and 'parent' or
  hasRetainedEconomicGeneralUi and 'general' or 'happiness'
assert(economicProvenance.role==economicRole and
  type(economicProvenance.originalLua)=='table' and
  type(economicProvenance.originalXml)=='table' and
  type(economicProvenance.originalLua.sha256)=='string' and
  #economicProvenance.originalLua.sha256==64 and
  type(economicProvenance.originalXml.sha256)=='string' and
  #economicProvenance.originalXml.sha256==64,
  'Economic role or original source identity is invalid')

if hasRetainedEconomicChildUi then
  Locale.ToNumber=function(value,pattern)
    assert(type(value)=='number' and pattern=='#.##',
      'Economic number formatting requires the original numeric argument and pattern')
    -- The original upkeep tooltip can divide by zero when there are no paid
    -- units. Preserve non-finite numbers for the actual localization provider,
    -- whose formatter defines their text; never coerce them to a made-up zero.
    return text(native('localeNumber',value,pattern))
  end
end

function ZeroSisEconomicSetVisible(visible,bInitState)
  assert(hasRetainedEconomicChildUi and type(visible)=='boolean' and type(bInitState)=='boolean',
    'Only an embedded Economic child accepts a native visibility request')
  assert(type(showHide)=='function' and timer==0,
    'Economic child requires its original show/hide handler and no popup semaphore')
  -- Stock SetHide(false) refreshes even when the selected tab was already shown.
  -- New instances replace the old ones, with fresh monotonic keys; stale input
  -- keys cannot address a newly rebuilt city or resource row.
  if visible then draws=array() end
  active=visible;contextHidden=not visible
  inputContextName=visible and contextName or nil
  updateAnimations(root,visible,true,frameTime())
  local ok,err=pcall(showHide,not visible,bInitState)
  if not ok then
    active=false;contextHidden=true;inputContextName=nil
    updateAnimations(root,false,true,frameTime())
    error(err,0)
  end
  assert(timer==0,'Embedded Economic child changed the parent popup semaphore')
  layoutDirty=true
  flushLayout()
  lifecycle[#lifecycle+1]=visible and 'economic-child-refreshed' or 'economic-child-hidden'
end

function ZeroSisEconomicRefresh()
  assert(hasRetainedEconomicParentUi and active and not contextHidden and timer==1,
    'Economic refresh requires the active original parent')
  local general=assert(controls.EconomicGeneralInfo)
  local happiness=assert(controls.HappinessInfo)
  assert(general:IsHidden()~=happiness:IsHidden(),
    'Economic parent must preserve exactly one selected original child tab')
  local selected=general:IsHidden() and happiness or general
  -- Calling the parent's ShowHideHandler again would increment its timer twice.
  -- Re-show the selected original child just as that handler does on opening.
  selected:SetHide(false)
  flushLayout()
end
