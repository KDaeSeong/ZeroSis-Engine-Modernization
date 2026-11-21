"""Run unchanged BNW NotificationPanel Lua/XML with explicit SDK-row fixtures.

This component verifies retained lifecycle, source trees and input payloads.
It does not run the game or prove original pixels, destination routes or timing.
"""
from __future__ import annotations

import hashlib
import json
import copy
from pathlib import Path
import re
import sys
import tempfile
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from economic_overview_scene import execute_lua
from prepare_ui_popup_assets import (GAME, notification_panel_control_tree, lua_value,
                                     production_font_metrics, production_style_defaults)


HARNESS = r'''
local source=@@SOURCES@@
local layout=@@LAYOUT@@
local types=@@TYPES@@
local checks=0
local function check(value,message) assert(value,message);checks=checks+1 end
local arrayTypes={}
local function json(value)
  local kind=type(value)
  if kind=='nil' then return 'null' end
  if kind=='boolean' then return tostring(value) end
  if kind=='number' then return string.format('%.17g',value) end
  if kind=='string' then return '"'..value:gsub('[%z\1-\31\\"]',function(ch)
    if ch=='"' then return '\\"' elseif ch=='\\' then return '\\\\' end
    return string.format('\\u%04x',string.byte(ch)) end)..'"' end
  assert(kind=='table')
  local parts={}
  if arrayTypes[getmetatable(value)] or #value>0 then
    for _,item in ipairs(value) do parts[#parts+1]=json(item) end
    return '['..table.concat(parts,',')..']'
  end
  local keys={};for key in pairs(value) do assert(type(key)=='string');keys[#keys+1]=key end
  table.sort(keys);for _,key in ipairs(keys) do parts[#parts+1]=json(key)..':'..json(value[key]) end
  return '{'..table.concat(parts,',')..'}'
end
local now,owner,turn=0,0,7
local nativeRows,requests={},{}
local function row(id,kind,summary)
  return {id=id,type=kind,tooltip='알림 설명 '..id,summary=summary or ('알림 '..id),
    gameData=-1,extraGameData=-1,player=owner,x=-1,y=-1}
end
nativeRows={row(0,types.NOTIFICATION_PRODUCTION),row(1,types.NOTIFICATION_TECH),
  row(2,types.NOTIFICATION_CITY_GROWTH),row(3,-777),row(4,types.NOTIFICATION_CITY_LOST)}
local env=setmetatable({ZeroSisUiLayout=layout,NotificationTypes=types,
  Players={[0]={},[1]={}},Teams={[0]={}},GameInfo={},
  Game={Rand=function() return 0 end,GetActivePlayer=function() return owner end,
    GetGameTurn=function() return turn end}}, {__index=_G})
env._G=env
local function run(text,name)
  local fn=assert(loadstring(text,'@'..name));setfenv(fn,env);return fn()
end
env.include=function(name) return run(assert(source[name],'Missing original include '..name),name) end
env.ZeroSisUiNative=function(operation,...)
  if operation=='uiFrameTime' then return now end
  if operation=='screenSize' then return 1920,1080 end
  if operation=='randomSeed' then return 17 end
  if operation=='locale' then return (...) end
  if operation=='noBasicHelp' then return false end
  if operation=='notificationPanelRows' then return nativeRows end
  if operation=='notificationPanelTouchScreen' then return false end
  if operation=='snapshotJson' then local snapshot,marker=...;arrayTypes[marker]=true;return snapshot end
  if operation=='notificationPanelActivateNotification' or operation=='notificationPanelRemoveNotification' then
    requests[#requests+1]={operation=operation,id=(...)};return
  end
  error('Unexpected native operation '..operation)
end
local costs={}
local function budget(name,fn)
  local count=0
  debug.sethook(function() count=count+1000;assert(count<=8000000,'Notification component exceeded native 8M instruction budget') end,'',1000)
  local ok,result=pcall(fn)
  debug.sethook()
  costs[name]=math.max(costs[name] or 0,count)
  if not ok then error(result,0) end
  return result
end
budget('original_initialization',function()
  run(source.scene..'\n'..source.input..'\n'..source.addon,'retained-NotificationPanel')
  run(source.stock,'original-BNW-NotificationPanel.lua')
end)
local function snapshot() return budget('snapshot_max',env.ZeroSisUi.Snapshot) end
local function find(root,id)
  if root.id==id then return root end
  for _,child in ipairs(root.children) do local found=find(child,id);if found then return found end end
end
local function instance(root,name)
  if root.instanceTemplate==name then return root end
  for _,child in ipairs(root.children) do local found=instance(child,name);if found then return found end end
end
local function target(id,event)
  local found
  for _,candidate in ipairs(env.ZeroSisUi.GetInputTargets(event)) do
    if candidate.void1==id then check(not found,'Duplicate visible callback for one notification');found=candidate end
  end
  return assert(found,'Missing visible notification target '..id)
end
local s=snapshot()
local initialGrowth=assert(instance(s.tree,'CityGrowthItem'))
check(find(initialGrowth,'NotificationSlide').animation.offsetY==500 and
  find(initialGrowth,'FingerRoot').animation.alpha==0,'Original branch animation did not start at its declared endpoints')
local consumer
for _,item in ipairs(s.inputTargets) do
  if item.key==initialGrowth.key then consumer=item end
end
check(consumer and consumer.event=='ConsumeMouse' and consumer.consumeMouse and consumer.void1==nil and
  consumer.id==initialGrowth.id and consumer.bounds.width==80 and consumer.bounds.height==80,
  'Original blank notification slot lost its independent mouse consumer during SlideAnim')
check(not env.ZeroSisUi.DispatchLeftClick(initialGrowth.key) and #requests==0,
  'Consumer-only slot fabricated an SDK notification callback')
now=0.125;s=snapshot()
local middleGrowth=assert(instance(s.tree,'CityGrowthItem'))
check(math.abs(find(middleGrowth,'NotificationSlide').animation.offsetY-375)<0.000001 and
  find(middleGrowth,'FingerRoot').animation.alpha==0.125,'Retained Root/OneBounce candidate timeline changed')
now=1;s=snapshot()
check(s.contextName=='NotificationPanel' and s.popupKind=='NotificationPanel' and s.active and
  s.nonmodal and s.timerSemaphore==0 and #s.lifecycle==1,'Original notification lifecycle changed')
check(s.notificationPanel.owner==0 and s.notificationPanel.turn==7 and #s.notificationPanel.notifications==5 and
  s.notificationPanel.allNotificationDestinationsIntegrated==false,'Actual row metadata is missing or overstated')
check(find(s.tree,'OuterStack').sourceAttributes.Offset=='0,246','Original panel anchor was replaced')
check(find(s.tree,'SmallScrollPanel').sourceAttributes.AutoScollbar=='1','Original scroll spelling changed')
local growth=assert(instance(s.tree,'CityGrowthItem'))
check(find(growth,'FingerTitle').text==nativeRows[3].summary,'Original NewFinger style child did not receive its title')
check(find(growth,'FingerTitle').styleChildSource.style=='NewFinger' and
  #find(growth,'FingerTitle').styleChildSource.indices>0,'Style child provenance was discarded')
local slide=assert(find(growth,'NotificationSlide'))
check(slide.sourceAttributes.Size==nil and slide.animation.offsetY==0 and slide.width==growth.width and
  slide.animation.retailGeometryVerified==false,'Source-derived slide frame was lost or retail geometry overstated')
local finger=assert(find(growth,'FingerRoot'))
check(finger.attributes.Speed==nil and finger.animation.effectiveSpeed==1 and
  finger.animation.defaultSpeedUsed and finger.animation.retailTimingVerified==false and
  finger.animation.alpha==1,'Omitted original Speed was rewritten or its candidate timing overstated')
local capitalLost=assert(instance(s.tree,'CapitalLostItem'))
local function findKind(root,kind)
  if root.kind==kind then return root end
  for _,child in ipairs(root.children) do local found=findKind(child,kind);if found then return found end end
end
local flip=assert(findKind(capitalLost,'FlipAnim'))
check(flip.animation.frame==20 and flip.animation.elapsed==1 and flip.animation.retailTimingVerified==false,
  'Original FlipAnim frame did not follow the branch reset and declared timing')
local animationSnapshotJson=json(s)
local left=target(0,'LeftClick');local right=target(0,'RightClick')
check(left.key==right.key and left.void1==0,'Notification ID zero or original left/right callbacks were lost')
local unhoveredSnapshotJson=json(snapshot())
check(json(snapshot())==unhoveredSnapshotJson,
  'Notification animation snapshot was not stable at fixed owner clock one')
check(env.ZeroSisUi.DispatchPointerMove(left.key),'Notification button hover was not accepted')
local hoveredSnapshotJson=json(snapshot())
check(env.ZeroSisUi.DispatchPointerMove(left.key) and json(snapshot())==hoveredSnapshotJson,
  'Repeated notification hover changed its retained animation snapshot at the same owner clock')
check(env.ZeroSisUi.DispatchPointerMove(0),'Notification pointer leave was not accepted')
local clearedHoverSnapshot=snapshot()
local clearedHoverJson=json(clearedHoverSnapshot)
check(clearedHoverJson~=hoveredSnapshotJson and clearedHoverJson==unhoveredSnapshotJson,
  'Notification pointer leave lost its visual change or failed to restore retained animation state')
check(env.ZeroSisUi.DispatchPointerMove(0) and json(snapshot())==clearedHoverJson,
  'Repeated notification key-zero clear changed its retained animation snapshot')
check(now==1 and clearedHoverSnapshot.presentationClock==1 and #requests==0,
  'Notification hover advanced owner time or added an SDK command')
budget('actual_input_addon',function()
  check(env.ZeroSisUi.DispatchLeftClick(left.key),'Original activate input failed')
  check(env.ZeroSisUi.DispatchRightClick(right.key),'Original dismiss input failed')
end)
check(#requests==2 and requests[1].operation=='notificationPanelActivateNotification' and requests[1].id==0 and
  requests[2].operation=='notificationPanelRemoveNotification' and requests[2].id==0,'Original callbacks changed native payloads')
check(#snapshot().notificationPanel.notifications==5,'Deferred dismiss fabricated an SDK removal before refresh')
local key=target(3,'LeftClick').key
budget('unchanged_refresh',function() check(env.ZeroSisUi.notificationPanelRefresh(),'Panel refresh closed its context') end)
check(target(3,'LeftClick').key==key,'Unchanged SDK rows recreated controls or reset animations')
local originalRows=nativeRows
nativeRows={originalRows[1],originalRows[1]}
check(not pcall(env.ZeroSisUi.notificationPanelRefresh),'Duplicate native IDs were accepted')
nativeRows=originalRows
check(target(3,'LeftClick').key==key,'Invalid SDK rows partially mutated the live tree')
now=6.5;s=snapshot()
check(find(assert(instance(s.tree,'CityGrowthItem')),'FingerRoot').animation.alpha==0.5,
  'OneBounce candidate lost the original end pause and return phase')
now=7;s=snapshot()
check(find(assert(instance(s.tree,'CityGrowthItem')),'FingerRoot').animation.alpha==0,
  'OneBounce candidate replayed after its declared single bounce')
nativeRows[4]=row(3,-777,'갱신된 알림')
budget('changed_row_refresh',function() env.ZeroSisUi.notificationPanelRefresh() end)
local restarted=assert(instance(snapshot().tree,'GenericItem'))
check(find(restarted,'NotificationSlide').animation.offsetY==500 and
  find(restarted,'FingerRoot').animation.alpha==0,'Changed row did not invoke original BranchResetAnimation')
now=8
s=snapshot()
local changed=target(3,'LeftClick').key
check(changed~=key and not env.ZeroSisUi.DispatchLeftClick(key),'Changed row retained a destroyed stale key')
check(find(assert(instance(s.tree,'GenericItem')),'FingerTitle').text=='갱신된 알림','Changed original title was not refreshed')
nativeRows={row(1,types.NOTIFICATION_TECH)}
env.ZeroSisUi.notificationPanelRefresh()
s=snapshot()
check(find(s.tree,'ProductionButton').hidden and not instance(s.tree,'GenericItem'),
  'Original removal did not hide the static button and release the dynamic instance')
check(not env.ZeroSisUi.DispatchLeftClick(changed),'Removed row remained an input target')

-- Exercise every original template through the public instance factory without
-- inventing GameInfo data for unrelated notification destination types.
local templates=0
budget('all_70_original_templates',function()
  for _,item in ipairs(layout.children) do
    if item.kind=='Instance' then
      local names={};env.ContextPtr:BuildInstanceForControl(item.attributes.Name,names,env.Controls.SmallStack)
      local rootName=assert(item.children[1].attributes.ID)
      local handle=assert(names[rootName]);handle:BranchResetAnimation()
      env.Controls.SmallStack:ReleaseChild(handle)
      check(not pcall(function() handle:GetSizeY() end),'Released original template retained a live handle')
      templates=templates+1
    end
  end
end)
check(templates==70,'Original unnamed or named notification template was discarded')

nativeRows={}
for id=100,111 do nativeRows[#nativeRows+1]=row(id,-777) end
budget('overflow_refresh',function() env.ZeroSisUi.notificationPanelRefresh() end)
now=9;s=snapshot()
budget('input_targets_overflow',env.ZeroSisUi.GetInputTargets)
budget('scroll_targets_overflow',env.ZeroSisUi.GetScrollTargets)
local panel=assert(find(s.tree,'SmallScrollPanel'))
check(panel.contentHeight==12*80-11*6 and panel.height==714 and panel.x==1820,
  'Original stack padding, screen-dependent viewport or overflow offset changed')
check(env.Controls.SmallScrollPanel:GetRatio()==714/894 and not find(s.tree,'ScrollBar').hidden,
  'Original measured overflow ratio or automatic scrollbar visibility changed')
check(env.ZeroSisUi.DispatchScroll(panel.key,30000),'Original panel scroll input was not accepted')
s=snapshot();panel=find(s.tree,'SmallScrollPanel')
check(panel.scrollY==180,'Original notification scroll did not clamp to its measured maximum')
for _,t in ipairs(s.inputTargets) do
  check(t.clippedBounds.x>=panel.x and t.clippedBounds.y>=panel.y and
    t.clippedBounds.x+t.clippedBounds.width<=panel.x+panel.width and
    t.clippedBounds.y+t.clippedBounds.height<=panel.y+panel.height,
    'Notification callback escaped the actual scroll clip')
end
local retainedSnapshotJson=json(s)
check(env.ZeroSisUi.DispatchScroll(panel.key,-30000),'Reverse notification scroll was rejected')
check(snapshot().tree~=nil and env.Controls.SmallScrollPanel:GetScrollValue()==0,'Reverse scroll did not clamp to zero')
nativeRows={};env.ZeroSisUi.notificationPanelRefresh();s=snapshot()
check(env.Controls.SmallScrollPanel:GetRatio()==1 and find(s.tree,'ScrollBar').hidden and
  #s.inputTargets==0,'Empty SDK inventory left stale inputs, scroll range or decorations')
owner=1;turn=8;nativeRows={row(0,types.NOTIFICATION_PRODUCTION)}
env.ZeroSisUi.notificationPanelRefresh();s=snapshot()
check(s.notificationPanel.owner==1 and s.notificationPanel.turn==8 and target(0,'LeftClick').void1==0,
  'Original active-player clear/rebroadcast handlers lost the new owner inventory')
check(#requests==2,'Read-only refreshes issued an activation or removal command')
env.ZeroSisUi.notificationPanelStop();env.ZeroSisUi.notificationPanelStop()
check(not env.ZeroSisUi.IsActive() and #env.ZeroSisUi.GetInputTargets()==0 and
  not env.ZeroSisUi.DispatchLeftClick(left.key),'Stopped original panel retained active input')
check(not pcall(env.ZeroSisUi.notificationPanelRefresh),'Stopped panel was resurrected')
return json({status='PASS_ORIGINAL_NOTIFICATION_PANEL_LUA_COMPONENT',componentOnly=true,checks=checks,
  fixedClockRepeatedHoverUnchanged=true,fixedClockKeyZeroUnchanged=true,hoverLeaveChangesSnapshot=true,
  originalTemplates=templates,instructionBudget=8000000,instructionCounts=costs,
  unchangedOriginalLoaded=true,nativeSdkVerified=false,nativePixelsVerified=false,retailTimingVerified=false,
  allNotificationDestinationsIntegrated=false,retainedSnapshotJson=retainedSnapshotJson,
  animationSnapshotJson=animationSnapshotJson})
'''


def verify_asset_contract(original: ET.Element, tree: dict, styles: dict) -> dict:
    """Catch original/template/style child loss before the Lua VM is created."""
    def same_source(xml: ET.Element, node: dict, *, materialized=False) -> int:
        assert node['kind'] == xml.tag
        assert node['sourceAttributes' if materialized else 'attributes'] == xml.attrib
        assert len(node['children']) == len(xml)
        return 1 + sum(same_source(child, captured, materialized=materialized)
                       for child, captured in zip(xml, node['children']))

    xml_nodes = same_source(original, tree)
    style_xml = ET.parse(GAME / 'Assets/UI/Styles.xml').getroot()
    style_nodes = 0
    for name in ('NewFinger', 'NewFingerRed'):
        source = style_xml.find(name)
        captured = styles['controls'][name]
        assert source is not None and 'Speed' not in source.attrib and 'Speed' not in captured['attributes']
        assert captured['sourceAttributes'] == source.attrib
        for child, materialized in zip(source, captured['children']):
            style_nodes += same_source(child, materialized, materialized=True)
        assert len(source) == len(captured['children'])
    rejected = []
    for mutation in ('removed_template', 'duplicate_name', 'new_lua_context'):
        candidate = copy.deepcopy(original)
        instances = [child for child in candidate if child.tag == 'Instance']
        if mutation == 'removed_template':
            candidate.remove(instances[0])
        elif mutation == 'duplicate_name':
            instances[1].set('Name', instances[0].get('Name'))
        else:
            ET.SubElement(candidate, 'LuaContext', {'FileName': 'UnownedContext'})
        try:
            notification_panel_control_tree(candidate)
        except ValueError:
            rejected.append(mutation)
        else:
            raise AssertionError('Notification preparer accepted ' + mutation)
    return {'status': 'PASS_ORIGINAL_NOTIFICATION_ASSET_COMPONENT',
            'xml_nodes_preserved': xml_nodes, 'style_child_nodes_preserved': style_nodes,
            'rejected_mutations': rejected}


def verify_component(*, include_snapshot: bool = False) -> dict:
    folder = GAME / 'Assets/DLC/Expansion2/UI/InGame/WorldView'
    paths = {
        'scene': PROJECT / 'Source/Host/UiScene.lua',
        'input': PROJECT / 'Source/Presentation/UiPresentationInput.lua',
        'addon': PROJECT / 'Source/Presentation/UiNotificationPanel.lua',
        'stock': folder / 'NotificationPanel.lua',
        'IconSupport': GAME / 'Assets/UI/IconSupport.lua',
        'InstanceManager': GAME / 'Assets/UI/InstanceManager.lua',
        'FLuaVector': GAME / 'Assets/Gameplay/Lua/FLuaVector.lua',
    }
    sources = {name: path.read_text(encoding='utf-8-sig') for name, path in paths.items()}
    # Named values are deliberately component-only; the Host uses SDK enum bindings.
    names = sorted(set(re.findall(r'NotificationTypes\.(NOTIFICATION_\w+)', sources['stock'])))
    types = {name: index + 1 for index, name in enumerate(names)}
    original = ET.parse(folder / 'NotificationPanel.xml').getroot()
    tree = notification_panel_control_tree(original)
    tree.update(contextName='NotificationPanel', popupKind='NotificationPanel')
    inline = json.loads((PROJECT / 'evidence/ui_popup/assets/inline_icons.json').read_text(encoding='utf-8'))['icons']
    with tempfile.TemporaryDirectory(prefix='zerosis-notification-component-') as temporary:
        styles = production_style_defaults(Path(temporary), tree)
        asset_result = verify_asset_contract(original, tree, styles)
        tree.update(styleDefaults=styles['controls'], styleDefaultsSource=styles['source'],
                    styleDefaultsPolicy=styles['policy'])
        tree['fontMetrics'] = production_font_metrics(tree, inline)
        source = (HARNESS.replace('@@SOURCES@@', lua_value(sources)).replace('@@LAYOUT@@', lua_value(tree))
                  .replace('@@TYPES@@', lua_value(types)))
        result = execute_lua(source)
    snapshot = json.loads(result.pop('retainedSnapshotJson'))
    animation_snapshot = json.loads(result.pop('animationSnapshotJson'))
    if include_snapshot:
        result['retained_snapshot'] = snapshot
        result['animation_snapshot'] = animation_snapshot
    paths['originalXml'] = folder / 'NotificationPanel.xml'
    result['source_sha256'] = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}
    result['original_source_refs'] = tree['notificationPanel']
    result['asset_component'] = asset_result
    return result


if __name__ == '__main__':
    print(json.dumps(verify_component(), ensure_ascii=False))
