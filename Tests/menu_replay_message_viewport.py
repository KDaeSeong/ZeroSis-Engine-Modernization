"""Real paragraph catalog plus independent continuous viewport geometry proof."""
from __future__ import annotations
import hashlib
import inspect
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
from menu_replay_restoration import build_cxx14
from menu_replay_assets import artifact
from menu_suite_storage import storage
from native_build import run

GAME=Path(r"C:/Program Files (x86)/Steam/steamapps/common/Sid Meier's Civilization V")
BUILD=PROJECT/'Build/MenuReplayMessageViewport/current'
EVIDENCE=PROJECT/'evidence/game_menu/replay_scroll_graph/message_viewport'
HEADER=PROJECT/'Source/Host/MenuReplayMessageViewport.h'
CPP=PROJECT/'Tests/menu_replay_message_viewport.cpp'
LUA=PROJECT/'Source/Assets/UI/Assets/UI/InGame/Popups/ReplayViewer.lua'
XML=PROJECT/'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml'


def original_geometry():
    lua=LUA.read_text('utf-8-sig');assert 'local newHeight = msgHeight + 10;' in lua
    beginning=lua.index('-- Add empty text to padd the bottom.')
    ending=lua.index('Controls.ReplayMessageStack:CalculateSize();',beginning)
    bottom=lua[beginning:ending]
    assert 'GetInstance()' in bottom and 'SetText(" ")' in bottom and 'SetSizeVal' not in bottom
    assert LUA.read_bytes()==(GAME/'Assets/UI/InGame/Popups/ReplayViewer.lua').read_bytes()
    assert XML.read_bytes()==(GAME/'Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml').read_bytes()
    skins=[]
    for path in (GAME/'Assets/UI/InGame/Popups/ReplayViewer.xml',XML):
        root=ET.parse(path).getroot();base=root.find("./Instance[@Name='ReplayMessageInstance']/Box[@ID='Base']")
        text=base.find("Label[@ID='MessageText']");stack=root.find(".//*[@ID='ReplayMessageStack']")
        assert base.attrib['Size']=='890,63' and text.attrib['Offset']=='0,5' and stack.attrib['Padding']=='1'
        skins.append(dict(source=artifact(path),paragraph_base=dict(base.attrib),text=dict(text.attrib),stack=dict(stack.attrib)))
    return dict(base_and_active_skin=skins,original_lua=artifact(LUA),
        source_top_padding_px=5,source_bottom_padding_px=5,source_stack_gap_px=1,source_final_empty_instance_px=63,
        derivation='Lua sets each nonempty Base to measured text height+10; XML label starts5px below top and stack has1px gap. The final empty instance retains its XML63px Base because Lua never resizes it.',
        native_control_metrics_executed=False)


def main():
    EVIDENCE.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    inputs=[HEADER,CPP,Path(__file__),PROJECT/'Source/Host/MenuReplayText.h',PROJECT/'Source/Host/MenuReplayData.h',
        PROJECT/'Source/Host/MenuReplayScrollModel.h',PROJECT/'Source/Host/MenuFrontEndAssets.h',
        PROJECT/'Source/Presentation/BitmapRenderer.h',PROJECT/'tools/native_build.py',LUA,XML,
        GAME/'Assets/UI/InGame/Popups/ReplayViewer.lua',GAME/'Assets/UI/InGame/Popups/ReplayViewer.xml',
        GAME/'Assets/DLC/Expansion2/UI/InGame/Popups/ReplayViewer.xml']
    before=[artifact(path) for path in inputs];recipe=inspect.getsource(build_cxx14)
    signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()+recipe.encode()).hexdigest()[:16]
    receipt=EVIDENCE/'result.json'
    if receipt.exists():
        old=json.loads(receipt.read_text('utf8'));exe=Path(old.get('build',{}).get('path','NO_RETAINED_FIXTURE'))
        if old.get('input_signature')==signature and old.get('status')=='PASS_SDK_FREE_MESSAGE_CONTINUOUS_VIEWPORT' and exe.is_file() and artifact(exe)['sha256']==old.get('build',{}).get('sha256'):
            print(json.dumps(dict(status=old['status'],reused_existing_identical_inputs=True,report=str(receipt))));return 0
    report=dict(schema='zerosis.menu_replay.message_viewport.v1',input_signature=signature,inputs_before=before,
        compile_recipe_sha256=hashlib.sha256(recipe.encode()).hexdigest(),source_modified_by_fixture=False,
        source_encoding='ASCII / windows-1252',cpp_dialect='c++14',native_host_sdk_window_gpu_executed=False,
        independent_oracles=['Literal source-derived rectangle tops[0,15,31,72]/ends[15,31,72,93] from real two-line/icon/one-line paragraphs;700 brute rectangle-intersection samples.',
            'Independent tall icon ascent24+descent6 produces30px line; actual ParagraphLayout.Place preserves fractional10.25px scroll.',
            '1MiB ASCII +4 prefix scalars, actual4096-atom emergency line limit:257 rows,257*4+5+6+63=1102px, maximum697px for405 viewport.',
            'Exact midpoint range[123,226), actual421888 visible atoms beyond legacy32768/page boundary; exact bottom range[173,257) and last glyph row leaves69px below.',
            '100k all-empty records have no rows and63px tail; owned index remains valid after actual paragraph/font/catalog/document destruction.',
            'Owned malformed-row fault injection tests negative/zero/NaN/Inf and unrepresentable row/tail/viewport arithmetic; production inputs remain immutable.'],
        limitations=['Synthetic fonts isolate geometry; these are not native text metrics or actual screen acceptance.',
            'The wide1MiB stress intentionally exceeds a legacy page atom limit and tests indexing only; it does not claim that rendering421888 synthetic glyphs is within Scene budgets.',
            'Root owns continuous presentation integration and the full Scene/raw-history validation.'])
    cleanup_names=['MenuReplayMessageViewport.obj','MenuReplayMessageViewport.map','compile.rsp','read_build_environment.cmd']
    try:
        if any(any(value>127 for value in path.read_bytes()) for path in (CPP,HEADER)):raise ValueError('Viewport C++14 source must remain ASCII')
        assert artifact(PROJECT/'Source/Host/MenuReplayScrollModel.h')['sha256']=='bb18673737215000bbe8dff89d9dc2c6794028ec9cfa04e522e8243f27703e51'
        report['original_geometry']=original_geometry()
        report['build']=build_cxx14('MenuReplayMessageViewport',BUILD,EVIDENCE,CPP,[PROJECT/'Source/Host'])
        compiled=report['build'];imports=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imports.stdout.decode('mbcs',errors='replace'),re.M)))
        if imports.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected SDK-free viewport DLL import '+repr(names))
        report['component_imported_dlls']=names
        result=run([compiled['path']],cwd=BUILD,timeout=60)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout));report['inputs_after']=[artifact(path) for path in inputs]
        if report['inputs_after']!=before:raise ValueError('Viewport/immutable source inputs changed during fixture')
    except Exception as error:
        report.update(status='FAIL_SDK_FREE_MESSAGE_CONTINUOUS_VIEWPORT',error=str(error));raise
    finally:
        removed=[]
        for name in cleanup_names:
            path=BUILD/name
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=BUILD.absolute() or info.st_nlink!=1:raise ValueError('Unsafe viewport intermediate cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Viewport cleanup identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_VIEWPORT_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed
        report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in removed)
        report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in removed)
        receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],report=str(receipt))))
    return 0


if __name__=='__main__':raise SystemExit(main())
