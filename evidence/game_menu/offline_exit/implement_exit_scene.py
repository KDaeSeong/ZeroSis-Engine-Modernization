"""One-use retained Lua adapter edit; original UI scripts remain unchanged."""
from pathlib import Path
import hashlib
import json
import os

STAGE = Path(__file__).resolve().parent
PROJECT = STAGE.parents[2]
path = PROJECT / 'Source/Host/UiScene.lua'
pin = next(row for row in json.loads((STAGE / 'before.json').read_bytes())['sources'] if row['path'] == str(path))
raw = path.read_bytes()
assert hashlib.sha256(raw).hexdigest() == pin['sha256']
assert path.stat().st_nlink == 1
text = raw.decode('utf-8-sig').replace('\r\n', '\n')


def change(old, new, count=1):
    global text
    assert text.count(old) == count, old[:160]
    text = text.replace(old, new)


change("local hasRetainedGameMenuUi = popupKind=='GameMenu'", """local hasRetainedGameMenuUi = popupKind=='GameMenu'
local hasRetainedExitConfirmUi = popupKind=='ExitConfirm'
local exitConfirmState={opened=false,opening=false,closed=false,submitted=false,dispatch=nil}
if hasRetainedExitConfirmUi then
  assert(contextName=='ExitConfirm','ExitConfirm context identity mismatch')
end""")
change('or hasRetainedGameMenuUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi',
       'or hasRetainedGameMenuUi or hasRetainedExitConfirmUi or hasRetainedSaveMenuUi or hasRetainedLoadMenuUi', 3)
change("      gameMenuUnavailable(name=='UserRequestClose' and 'ExitGame' or 'ExitToMainMenu')", """      if name=='UserRequestClose' then native('gameMenuExitConfirm')
      else gameMenuUnavailable('ExitToMainMenu') end""")
change("if hasRetainedGameMenuUi then event('UserRequestClose');event('ExitToMainMenu') end", """if hasRetainedGameMenuUi then event('UserRequestClose');event('ExitToMainMenu') end
if hasRetainedExitConfirmUi then event('UserRequestClose') end""")
change("  UI.ExitGame=function() return gameMenuUnavailable('ExitGame') end", """  UI.ExitGame=function() error('GameMenu must request its separate original ExitConfirm modal') end""")
change("\nif hasRetainedSaveMenuUi then\n  ownedSaveDelete.prefix=", """
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
  ownedSaveDelete.prefix=""")
change('function context:LookUpControl(path)\n  if hasRetainedPantheonUi then', """function context:LookUpControl(path)
  if hasRetainedExitConfirmUi then
    assert(path=='/InGame','ExitConfirm queried an undeclared context path')
    assert(native('exitConfirmInGame')==true,'ExitConfirm requires the actual owned in-game session')
    return context
  end
  if hasRetainedPantheonUi then""")
change('function UIManager:IsModal(ctx)\n', """function UIManager:PushModal(ctx,...)
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
""")
change("function UIManager:PopModal(ctx)\n  assert(hasRetainedSaveMenuUi and ctx==context,'PopModal requires the original SaveMenu context')\n  return self:DequeuePopup(ctx)\nend", """function UIManager:PopModal(ctx,...)
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
end""")
change('  OpenGameMenu=function()\n', """  OpenExitConfirm=function()
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
""")
change('    if not handle or not invokeCallback(handle,Mouse.eLClick) then return false end\n    if hasRetainedPopupUi then flushLayout() end', """    if hasRetainedExitConfirmUi then
      assert((handle==controls.Yes or handle==controls.No) and not exitConfirmState.dispatch,
        'ExitConfirm input must be one original Yes or No callback')
      exitConfirmState.dispatch=handle==controls.Yes and 'Yes' or 'No'
      local ok,consumed=pcall(invokeCallback,handle,Mouse.eLClick)
      exitConfirmState.dispatch=nil
      if not ok then error(consumed,0) end
      if not consumed then return false end
    elseif not handle or not invokeCallback(handle,Mouse.eLClick) then return false end
    if hasRetainedPopupUi then flushLayout() end""")
change("  if hasRetainedNotificationUi then\n    return value.kind=='Container' and value.sourceAttributes.ConsumeMouseButton=='1'", """  if hasRetainedExitConfirmUi and value.kind=='Box' and value.attributes.ID=='ExitConfirm' and
    value.sourceAttributes.ConsumeMouseOver=='1' then return true end
  if hasRetainedNotificationUi then
    return value.kind=='Container' and value.sourceAttributes.ConsumeMouseButton=='1'""")
change('    if not inputHandler then return false end\n    return inputHandler(KeyEvents.KeyDown,key,0)==true', """    if not inputHandler then return false end
    if hasRetainedExitConfirmUi then
      assert(not exitConfirmState.dispatch,'ExitConfirm keyboard callback is already active')
      exitConfirmState.dispatch=key==Keys.VK_ESCAPE and 'Escape' or nil
      local ok,consumed=pcall(inputHandler,KeyEvents.KeyDown,key,0)
      exitConfirmState.dispatch=nil
      if not ok then error(consumed,0) end
      return consumed==true
    end
    return inputHandler(KeyEvents.KeyDown,key,0)==true""")
change('    if hasRetainedSaveMenuUi then\n      local provenance=assert(layout.saveMenu', """    if hasRetainedExitConfirmUi then
      local metadata={}
      for key,value in pairs(assert(layout.exitConfirm,'ExitConfirm source provenance is required')) do metadata[key]=value end
      metadata.modal=true;metadata.timerSemaphore=timer
      metadata.closed=exitConfirmState.closed;metadata.exitSubmitted=exitConfirmState.submitted
      snapshot.exitConfirm=metadata;snapshot.contextHidden=contextHidden
    end
    if hasRetainedSaveMenuUi then
      local provenance=assert(layout.saveMenu""")

data=text.replace('\n','\r\n').encode('utf-8')
if raw.startswith(b'\xef\xbb\xbf'):
    data=b'\xef\xbb\xbf'+data
temporary=path.with_name(path.name+'.offline-exit-tmp')
assert not temporary.exists()
temporary.write_bytes(data)
os.replace(temporary,path)
print(path.relative_to(PROJECT),len(data),hashlib.sha256(data).hexdigest())
