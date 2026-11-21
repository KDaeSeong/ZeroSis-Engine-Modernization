"""Compare label batching on an observed CityView tree in the shared Lua 5.1 VM.

This is a bounded frontend component regression, not a replay of CityView's SDK
queries, the failed native callback, native pixels, or a save/load proof. The
input snapshot supplies the same finite controls and click registrations to both
versions. All label sizes, final geometry, scroll state and input targets must
match, while a dirty-event boundary replaces per-label whole-tree anchoring.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from economic_overview_scene import execute_lua
from prepare_ui_popup_assets import lua_value, production_font_metrics


CASE = r'''
local fixture=assert(ZeroSisCityFixture)
local byKey,labels={},{}
local function seed(handle,node)
 local value=state(handle);byKey[node.key]=handle;value.key=node.key
 value.w=node.width;value.h=node.height;value.hidden=node.hidden
 value.x=node.x;value.y=node.y;value.disabled=node.disabled
 value.worldPosition=node.worldPosition
 if node.kind=='Label' then labels[#labels+1]=handle end
 assert(#value.children==#node.children,'Observed control tree changed')
 for index,child in ipairs(value.children) do seed(child,node.children[index]) end
end
seed(root,fixture.tree)
local clicks=0
for _,target in ipairs(fixture.inputTargets) do
 if target.event=='LeftClick' then
  local handle=assert(byKey[target.key]);local value=state(handle)
  value.void1=target.void1;value.void2=target.void2
  handle:RegisterCallback(Mouse.eLClick,function() clicks=clicks+1 end)
 end
end
context:SetHide(false)
local anchors=0
local originalAnchor=anchor
anchor=function(handle)
 if handle==root then anchors=anchors+1 end
 return originalAnchor(handle)
end
local immediate={}
Events.SerialEventCityScreenDirty.Add(function()
 for _,handle in ipairs(labels) do
  -- Change text as well as reassign it; GetSize must reflect new glyph metrics
  -- before the event flush, as the original TruncateString/GetSizeX paths do.
  local old=handle:GetText()
  handle:SetText(old..' 123')
  immediate[#immediate+1]={handle:GetSizeX(),handle:GetSizeY()}
 end
end)
local instructions=0
debug.sethook(function()
 instructions=instructions+1000
 assert(instructions<=32000000,'Bounded component operation failed to finish')
end,'',1000)
Events.SerialEventCityScreenDirty.CallImmediate()
debug.sethook()
local eventAnchors=anchors
local snap=ZeroSisUi.Snapshot()
assert(#snap.inputTargets>0,'Observed city has no retained click targets')
local target
for _,row in ipairs(snap.inputTargets) do
 if row.event=='LeftClick' then target=row;break end
end
assert(target and ZeroSisUi.DispatchLeftClick(target.key) and clicks==1,
 'The committed click target no longer dispatches')
return {snapshot=snap,immediate=immediate,labels=#labels,anchors=eventAnchors,
 instructions=instructions,targets=#snap.inputTargets,clicks=clicks}
'''


HARNESS = r'''
local oldSource,newSource,layout,fixture=@@OLD@@,@@NEW@@,@@LAYOUT@@,@@FIXTURE@@
local function copy(value)
 if type(value)~='table' then return value end
 local result={};for k,v in pairs(value) do result[k]=copy(v) end;return result
end
local function same(a,b,path)
 assert(type(a)==type(b),'Type changed: '..path)
 if type(a)~='table' then assert(a==b,'Value changed: '..path);return end
 for k,v in pairs(a) do assert(b[k]~=nil,'Key removed: '..path..'.'..tostring(k));same(v,b[k],path..'.'..tostring(k)) end
 for k in pairs(b) do assert(a[k]~=nil,'Key added: '..path..'.'..tostring(k)) end
end
local function run(source)
 local env=setmetatable({ZeroSisUiLayout=copy(layout),ZeroSisCityFixture=copy(fixture)}, {__index=_G})
 env._G=env
 env.Game={Rand=function() error('Unexpected gameplay RNG in layout component') end}
 env.ZeroSisUiNative=function(op,...)
  if op=='screenSize' then return 1920,1080 end
  if op=='uiFrameTime' then return 1 end
  if op=='locale' then return (...) end
  if op=='snapshotJson' then return copy((...)) end
  error('Unmodeled native operation: '..tostring(op))
 end
 local fn=assert(loadstring(source..'\n'..@@CASE@@,'@CityView-label-batch-component.lua'))
 setfenv(fn,env);return fn()
end
local old,new=run(oldSource),run(newSource)
same(old.snapshot,new.snapshot,'snapshot')
same(old.immediate,new.immediate,'immediate-label-size')
assert(old.labels==new.labels and old.labels>1,'Fixture does not exercise a label batch')
assert(old.anchors==old.labels and new.anchors==1,'Dirty-event anchoring was not batched')
assert(new.instructions<old.instructions/2,'Expected instruction reduction was not observed')
return string.format('{"status":"PASS_CITY_VIEW_LABEL_BATCH_COMPONENT_ONLY","labels":%d,"targets":%d,"old_root_anchors":%d,"new_root_anchors":%d,"old_opcodes_approx":%d,"new_opcodes_approx":%d,"geometry_and_hits_equal":true,"immediate_label_sizes_equal":true,"clicks_each":1,"native_restore_verified":false}',
 new.labels,new.targets,old.anchors,new.anchors,old.instructions,new.instructions)
'''


def verify(snapshot_path: Path, before_path: Path) -> dict:
    snapshot_bytes = snapshot_path.read_bytes()
    snapshot = json.loads(snapshot_bytes)
    if (snapshot.get('contextName'), snapshot.get('popupKind'), snapshot.get('active')) != ('CityView', 'CityView', True):
        raise ValueError('An actual active CityView snapshot is required')
    old = before_path.read_text(encoding='utf-8-sig')
    new = (PROJECT / 'Source/Host/UiScene.lua').read_text(encoding='utf-8-sig')
    old_condition = 'if hasRetainedTreeUi or hasRetainedTechUi or hasRetainedSocialPolicyUi or hasRetainedEconomicUi or hasRetainedNotificationUi then\n      -- Stock tech lists'
    new_condition = old_condition.replace('hasRetainedTechUi or ', 'hasRetainedTechUi or hasRetainedCityUi or ')
    if old.count(old_condition) != 1 or new != old.replace(old_condition, new_condition):
        raise ValueError('Expected exactly the CityView label batching condition change')

    seen = set()
    default_sizes = {}
    def retained(node: dict) -> dict:
        if node['key'] in seen:
            raise ValueError('Observed CityView tree repeats a retained control key')
        seen.add(node['key'])
        attrs = dict(node['attributes'])
        if node.get('defaultSize') and attrs.get('ButtonTexture'):
            basename = attrs['ButtonTexture'].replace('\\', '/').rsplit('/', 1)[-1].lower()
            default_sizes[basename] = node['defaultSize']
        # Instances have local ID namespaces. This flat component layout gives
        # them unique fixture IDs; actual keys/tree/attributes are otherwise kept.
        attrs['ID'] = 'ObservedCityControl' + str(node['key'])
        attrs['String'] = node.get('text', '')
        attrs['Text'] = node.get('text', '')
        attrs['Hidden'] = '1' if node.get('hidden') else '0'
        return {'kind': node['kind'], 'attributes': attrs,
                'children': [retained(child) for child in node['children']]}

    layout = retained(snapshot['tree'])
    layout.update({'contextName': 'CityView', 'popupKind': 'CityView',
                   'controlDefaultSizes': default_sizes,
                   'styleDefaults': snapshot['styleDefaults'],
                   'styleDefaultsSource': snapshot['styleDefaultsSource'],
                   'styleDefaultsPolicy': snapshot['styleDefaultsPolicy']})
    icon_path = snapshot_path.parent.parent.parent / 'interactive_ui_support/assets/inline_icons.json'
    icons = json.loads(icon_path.read_text(encoding='utf-8-sig'))['icons']
    layout['fontMetrics'] = production_font_metrics(layout, icons)
    fixture = {'tree': snapshot['tree'], 'inputTargets': snapshot['inputTargets']}
    harness = HARNESS
    for token, value in {'@@OLD@@': old, '@@NEW@@': new, '@@LAYOUT@@': layout,
                         '@@FIXTURE@@': fixture, '@@CASE@@': CASE}.items():
        harness = harness.replace(token, lua_value(value))
    result = execute_lua(harness)
    result.update({'observed_controls': len(seen), 'snapshot': str(snapshot_path),
                   'snapshot_sha256': hashlib.sha256(snapshot_bytes).hexdigest(),
                   'before_source_sha256': hashlib.sha256(before_path.read_bytes()).hexdigest(),
                   'after_source_sha256': hashlib.sha256((PROJECT / 'Source/Host/UiScene.lua').read_bytes()).hexdigest(),
                   'scope': 'All observed label controls receive one bounded text update on the same tree. This is not the exact original SDK callback or native restore replay.'})
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--snapshot', required=True, type=Path)
    parser.add_argument('--before-source', required=True, type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = verify(args.snapshot, args.before_source)
    encoded = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.output:
        if args.output.exists():
            raise FileExistsError('Never overwrite an earlier component report')
        args.output.write_text(encoded, encoding='utf-8')
    print(encoded, end='')
