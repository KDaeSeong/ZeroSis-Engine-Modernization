"""Exact source floor oracle and SDK-free scroll/press component checks."""
from __future__ import annotations
import hashlib
import inspect
import json
import math
from pathlib import Path
import random
import re
import struct
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
from menu_replay_restoration import build_cxx14
from menu_replay_assets import artifact
from menu_suite_storage import storage
from native_build import run
from economic_overview_scene import execute_lua
from prepare_ui_popup_assets import lua_value

GAME=Path(r"C:/Program Files (x86)/Steam/steamapps/common/Sid Meier's Civilization V")
VIEWER=PROJECT/'Source/Assets/UI/Assets/UI/InGame/Popups/ReplayViewer.lua'
ACTIVE=PROJECT/'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml'
STYLES=PROJECT/'Source/Assets/UI/Assets/UI/Styles.xml'
HEADER=PROJECT/'Source/Host/MenuReplayScrollModel.h'
CPP=PROJECT/'Tests/menu_replay_scroll_model.cpp'
BUILD=PROJECT/'Build/MenuReplayScrollModel/current'
EVIDENCE=PROJECT/'evidence/game_menu/replay_scroll_graph/scroll_model'
RETAIL_PROBE=PROJECT/'evidence/game_menu/replay_season_wheel/retail_static_probe.json'
RETAIL_EXE_SHA256='b7c8977ebab33ba6c1abf65d63fa310f8d096341465e0fc419f1b4da0fcd8818'


def source_proof():
    source=VIEWER.read_text('utf-8-sig')
    callback=re.search(r'function OnTurnSliderValueChanged\(newValue\).*?\nend',source,re.S).group(0)
    assert 'math.floor(newValue * (finalTurn - initialTurn)) + initialTurn' in callback
    original_xml=GAME/'Assets/UI/InGame/Popups/ReplayViewer.xml'
    installed_active=GAME/'Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml'
    assert VIEWER.read_bytes()==(GAME/'Assets/UI/InGame/Popups/ReplayViewer.lua').read_bytes()
    assert ACTIVE.read_bytes()==installed_active.read_bytes()
    assert STYLES.read_bytes()==(GAME/'Assets/UI/Styles.xml').read_bytes()
    skin=[]
    for path in (original_xml,ACTIVE):
        root=ET.parse(path).getroot();slider=root.find(".//*[@ID='TurnSlider']")
        messages=root.find(".//*[@ID='ReplayMessageScrollPanel']");track=messages.find('ScrollBar')
        assert slider is not None and slider.attrib['Length']=='500' and slider.attrib['Style']=='Slider'
        if path==ACTIVE:assert slider.attrib.get('WheelSteps')=='10'
        assert messages.attrib['Size']=='920,405' and messages.attrib['Vertical']=='1' and track.attrib['Length']=='369'
        skin.append(dict(source=artifact(path),map_slider=dict(slider.attrib),messages_panel=dict(messages.attrib),messages_track=dict(track.attrib)))
    styles=ET.parse(STYLES).getroot();slider=styles.find('Slider');thumb=slider.find('Shuttle')
    vertical=styles.find('VertSlider');vertical_thumb=vertical.find('Shuttle')
    assert thumb.attrib['Size']=='32,32' and thumb.attrib['Style']=='Slider32'
    assert vertical_thumb.attrib['Size']=='18,18' and vertical_thumb.attrib['Style']=='VertShuttle'
    return callback,dict(source_callback_sha256=hashlib.sha256(callback.encode()).hexdigest(),
        source_callback=callback,base_and_active_skin=skin,
        original_styles=dict(source=artifact(STYLES),map_slider=dict(slider.attrib),map_shuttle=dict(thumb.attrib),messages_track=dict(vertical.attrib),messages_shuttle=dict(vertical_thumb.attrib)),
        map_policy='Exact original floor(unit*(final-initial))+initial; no nearest rounding or epsilon.',
        messages_policy='The original uses a continuous native ScrollPanel. It has no Lua page-selection callback or page rounding rule.',
        authored_map_shuttle_px=32,authored_messages_shuttle_px=18,
        native_metric_scope='Styles declare these sizes and map Gutter=-5. Native gutter interpretation and dynamic thumb sizing are not executed/proven; the model consumes supplied geometry without hardcoded sizes.')


def floor_goldens(callback):
    intervals=[(0,0),(7,7),(7,9),(0,100),(0,1000),(7,1007),(0,1000000),(9999999,10000000),
        (-2147483648,2147483647),(-2147483648,-2147482648),(2147482647,2147483647)]
    cases=[];rng=random.Random(0x5343524f4c4c)
    for initial,final in intervals:
        span=final-initial;units={0.0,1.0,.5,.29,.014,.986,360/369,.6,math.nextafter(0.0,1.0),math.nextafter(1.0,0.0)}
        if span:
            for step in {0,1,2,3,7,11,29,50,127,span//3,span//2,span-1,span}:
                if step>span:continue
                unit=step/span
                for value in (math.nextafter(unit,-math.inf),unit,math.nextafter(unit,math.inf)):
                    if 0<=value<=1:units.add(value)
        units.update(rng.random() for _ in range(80))
        cases.extend((unit,initial,final) for unit in sorted(units))
    selected=source_callback(callback,cases)
    def cpp_int(value):return '(-2147483647-1)' if value==-2147483648 else str(value)
    lines=['static const FloorCase StockFloorGoldens[]={']
    for (unit,initial,final),expected in zip(cases,selected):
        bits=struct.unpack('<Q',struct.pack('<d',unit))[0]
        lines.append('{0x%016xull,%s,%s,%s},'%(bits,cpp_int(initial),cpp_int(final),cpp_int(expected)))
    lines.append('};\n');path=BUILD/'replay_scroll_stock_goldens.inc';path.write_text('\n'.join(lines),encoding='ascii',newline='\n')
    return dict(cases=len(cases),intervals=intervals,golden_payload=artifact(path),
        actual_controlled_lua51=True,sandbox='Exact original callback only: fixture replay interval, math.floor, and captured SetCurrentTurn; no game/UI APIs.',
        double_payload='C++ cases retain exact IEEE754 bits, including subnormal/boundary fractions; no decimal literal rounding in the comparison.')


def f32(value):
    """Round one double to IEEE754 binary32 (round to nearest even)."""
    return struct.unpack('<f',struct.pack('<f',value))[0]


def f32_bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]


def retail_wheel_value(stored,steps,positive):
    # 005e0832: divss 100/W; divss 1/that; subss or addss; 007af7c0 clamp.
    # binary32 +,-,/ evaluated in binary64 then rounded once are exact (53>=2*24+2).
    divisor=f32(f32(100.0)/f32(steps));step=f32(1.0/divisor)
    value=f32(stored-step) if positive else f32(step+stored)
    return 0.0 if 0.0>value else 1.0 if value>1.0 else value


def wheel_goldens(callback,wheel_steps):
    probe=json.loads(RETAIL_PROBE.read_text('utf8'))
    assert probe['exe']['sha256']==RETAIL_EXE_SHA256 and probe['executed'] is False
    semantics=probe['slider_wheel']['semantics']
    assert semantics['step'].startswith('float32 1.0f / (100.0f / WheelSteps)')
    assert semantics['direction'].startswith('HIWORD(wParam) > 0 (wheel away/up): value -= step')
    assert [row['method'] for row in probe['slider_wheel']['lua_methods']['rows']]==['SliderControl::SetValue','SliderControl::SetAndCall']
    viewer=VIEWER.read_text('utf-8-sig')
    assert 'local sliderValue = (currentTurn - initialTurn)/(finalTurn - initialTurn);' in viewer
    assert 'turnSlider:SetValue(sliderValue);' in viewer
    intervals=[(0,1),(0,2),(7,9),(0,3),(0,7),(0,9),(0,10),(0,11),(0,19),(0,30),(0,99),(0,100),(0,101),
        (0,330),(0,333),(0,500),(0,999),(7,1007),(9999990,10000000)]
    rng=random.Random(0x574845454c);turns=[]
    for initial,final in intervals:turns.extend((turn,initial,final) for turn in range(initial,final+1))
    for initial,final in ((0,1000000),(-2147483648,2147483647)):
        span=final-initial;picked={initial,final,initial+1,final-1,initial+span//10,initial+span//2}
        picked.update(initial+rng.randrange(span+1) for _ in range(120))
        turns.extend((turn,initial,final) for turn in sorted(picked))
    cases=[];values=[]
    for turn,initial,final in turns:
        stored=f32((turn-initial)/(final-initial))
        for positive in (False,True):
            cases.append((turn,initial,final,positive));values.append(retail_wheel_value(stored,wheel_steps,positive))
    selected=source_callback(callback,[(value,initial,final) for value,(_,initial,final,_) in zip(values,cases)])
    decimal=0;stalled=[]
    for (turn,initial,final,positive),expected in zip(cases,selected):
        span=final-initial;target=(turn-initial)/span+(-.1 if positive else .1)
        if math.floor(min(1.0,max(0.0,target))*span)+initial!=expected:decimal+=1
        if not positive and turn<final and expected==turn and (initial,final) not in stalled:stalled.append((initial,final))
    def cpp_int(value):return '(-2147483647-1)' if value==-2147483648 else str(value)
    lines=['static const float SourceTurnSliderWheelSteps=%.1ff;'%wheel_steps,'static const WheelCase StockWheelGoldens[]={']
    for (turn,initial,final,positive),value,expected in zip(cases,values,selected):
        lines.append('{%s,%s,%s,%d,%s,0x%08xu},'%(cpp_int(turn),cpp_int(initial),cpp_int(final),positive,cpp_int(expected),f32_bits(value)))
    lines.append('};\n');path=BUILD/'replay_scroll_wheel_goldens.inc';path.write_text('\n'.join(lines),encoding='ascii',newline='\n')
    return dict(cases=len(cases),intervals=intervals,sampled_large_intervals=[[0,1000000],[-2147483648,2147483647]],
        golden_payload=artifact(path),retail_probe=artifact(RETAIL_PROBE),authored_wheel_steps=wheel_steps,
        float32_results_differing_from_decimal_tenth=decimal,
        forward_stalled_intervals=[list(row) for row in stalled],
        source_policy='SetValue re-seeds float((turn-initial)/(final-initial)); one wheel message moves that float by 1/(100/WheelSteps) '
                      'in binary32 and clamps it; the original OnTurnSliderValueChanged floor runs in controlled Lua 5.1.',
        consequence='Where 0.1*(final-initial)<1 a forward step floors back to the same turn while a backward step still moves one turn; '
                    'this is the original re-seeded slider behaviour and is retained, not repaired.',
        gate_scope='Retail requires control state bit 0x10000 (meaning not proved). The engine routes the wheel through the slider rectangle hit test.')


def source_callback(callback,cases):
    script=r'''
local cases=@@CASES@@
local selected
local env={math={floor=math.floor},g_ReplayInfo={},Panels={[3]={SetCurrentTurn=function(_,turn) selected=turn end}}}
local fn=assert(loadstring(@@CALLBACK@@,'@original-ReplayViewer-OnTurnSliderValueChanged.lua'));setfenv(fn,env);fn()
local results={}
for _,case in ipairs(cases) do
 env.g_ReplayInfo.InitialTurn=case[2];env.g_ReplayInfo.FinalTurn=case[3]
 env.OnTurnSliderValueChanged(case[1]);assert(type(selected)=='number' and selected==math.floor(selected))
 results[#results+1]=string.format('%.0f',selected)
end
return '{"selected":['..table.concat(results,',')..']}'
'''
    script=script.replace('@@CASES@@',lua_value([list(case) for case in cases])).replace('@@CALLBACK@@',lua_value(callback))
    result=execute_lua(script);assert len(result['selected'])==len(cases)
    return [int(value) for value in result['selected']]


def main():
    EVIDENCE.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    inputs=[HEADER,CPP,Path(__file__),PROJECT/'Source/Presentation/BitmapPointerPress.h',VIEWER,ACTIVE,STYLES,
        GAME/'Assets/UI/InGame/Popups/ReplayViewer.lua',GAME/'Assets/UI/InGame/Popups/ReplayViewer.xml',
        GAME/'Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml',GAME/'Assets/UI/Styles.xml',
        PROJECT/'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll',PROJECT/'tools/native_build.py',
        PROJECT/'Tests/economic_overview_scene.py',PROJECT/'tools/prepare_ui_popup_assets.py',RETAIL_PROBE]
    before=[artifact(path) for path in inputs];recipe=inspect.getsource(build_cxx14)
    if any(any(value>127 for value in path.read_bytes()) for path in (HEADER,CPP)):raise ValueError('C++14/windows1252 source is not ASCII')
    signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()+recipe.encode()).hexdigest()[:16]
    receipt=EVIDENCE/'result.json'
    if receipt.exists():
        old=json.loads(receipt.read_text('utf8'));exe=Path(old.get('build',{}).get('path','NO_RETAINED_FIXTURE'))
        if old.get('input_signature')==signature and old.get('status')=='PASS_SDK_FREE_REPLAY_SCROLL_MODEL' and exe.is_file() and artifact(exe)['sha256']==old.get('build',{}).get('sha256'):
            print(json.dumps(dict(status=old['status'],reused_existing_identical_inputs=True,report=str(receipt))));return 0
    report=dict(schema='zerosis.menu_replay.scroll_model.v1',input_signature=signature,inputs_before=before,
        compile_recipe_sha256=hashlib.sha256(recipe.encode()).hexdigest(),native_host_sdk_window_gpu_executed=False,
        source_encoding='ASCII / windows-1252',cpp_dialect='c++14',
        model_contract=['Geometry/inverse use caller-supplied track and thumb sizes, with finite representable endpoints.',
            'A gesture belongs to one window monotonic press ID sequence. Zero IDs support legacy synthetic component events only.',
            'Drag preserves original grip/origin across coalesced input and changing current values. New IDs start a new grip.',
            'preserveCurrent means the pointer has not moved: keep the current authoritative value instead of quantizing it again.',
            'Release/cancel retires physical IDs; delayed stale events cannot resume them. Authored geometry change cancels the current press.',
            'Map uses exact source floor after real movement. Messages/legend use continuous offset without page rounding.',
            'Map wheel: one message moves the re-seeded binary32 turn fraction by 1/(100/WheelSteps), clamps, then applies the source floor.',
            'The pure model has no replay document/raw history access; Root integration verifies retained raw bytes.'])
    cleanup_names=['replay_scroll_stock_goldens.inc','replay_scroll_wheel_goldens.inc','MenuReplayScrollModel.obj','MenuReplayScrollModel.map','compile.rsp','read_build_environment.cmd']
    try:
        callback,report['original_source_proof']=source_proof();report['original_lua']=floor_goldens(callback)
        wheel_steps=float(report['original_source_proof']['base_and_active_skin'][1]['map_slider']['WheelSteps'])
        report['original_map_wheel']=wheel_goldens(callback,wheel_steps)
        report['build']=build_cxx14('MenuReplayScrollModel',BUILD,EVIDENCE,CPP,[PROJECT/'Source/Host',PROJECT/'Source/Presentation',BUILD])
        compiled=report['build'];imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        if imports.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected pure scroll DLL import '+repr(names))
        report['component_imported_dlls']=names
        result=run([compiled['path']],cwd=BUILD,timeout=30)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout));report['inputs_after']=[artifact(path) for path in inputs]
        if report['inputs_after']!=before:raise ValueError('Immutable source/model inputs changed during controlled check')
    except Exception as error:
        report.update(status='FAIL_SDK_FREE_REPLAY_SCROLL_MODEL',error=str(error));raise
    finally:
        removed=[]
        for name in cleanup_names:
            path=BUILD/name
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=BUILD.absolute() or info.st_nlink!=1:raise ValueError('Unsafe scroll fixture cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Scroll cleanup identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_SCROLL_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed
        report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in removed)
        report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in removed)
        receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],lua_goldens=report['source_lua_floor_goldens'],
        wheel_goldens=report['source_wheel_goldens'],report=str(receipt))))
    return 0


if __name__=='__main__':raise SystemExit(main())
