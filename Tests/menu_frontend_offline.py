"""Actual SDK-free asset/parser/scene fixture and one CPU-only visual proof.

Only a /MT console component with Kernel32 imports is executed. It links no
Host, GameCore, SDK, CLR, WIC, D2D/D3D or window library. Standard Python rasterizes
the component's actual sprite output; that image is not runtime pixel evidence.
"""
from __future__ import annotations
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import sys

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'tools'))
from native_build import build_program,run
from menu_suite_storage import storage
from menu_frontend_assets import artifact

EVIDENCE=PROJECT/'evidence/game_menu/original_menu_followup/frontend'
BUILD=PROJECT/'Build/MenuFrontEndComponent/current'
ASSETS=PROJECT/'Source/Assets/UIFrontEnd'
LOCALIZATION=PROJECT/'Build/InteractiveGameRuntime/20261101T080450Z_424fb64608b2/localization.db'


def seal(path):
    info=storage.ordinary(path)
    return dict(path=str(path.absolute()),sha256=storage.digest(path),allocated_bytes=storage.allocated(path),**storage.metadata(info))


def labels(destination):
    metadata=json.loads((EVIDENCE/'assets.json').read_text('utf8'))
    keys=sorted({row['text'] for row in metadata['controls'] if row['text']})
    database=sqlite3.connect(LOCALIZATION.as_uri()+'?mode=ro&immutable=1',uri=True)
    blob=bytearray(struct.pack('<I',len(keys)))
    for source_key in keys:
        key=source_key.strip('{}').split(':')[0]
        row=database.execute('SELECT Text FROM Language_ko_KR WHERE Tag=?',(key,)).fetchone()
        if row is None or not row[0] or row[0].startswith('TXT_KEY_'):
            raise ValueError('Original Korean label is unavailable: '+key)
        for value in (source_key,row[0]):
            raw=value.encode('utf8');blob+=struct.pack('<I',len(raw))+raw
    database.close();destination.write_bytes(blob)
    return keys


def cpu_render(packet,png):
    from menu_frontend_cpu import render
    return render(packet,png,ASSETS)


def main():
    BUILD.mkdir(parents=True,exist_ok=True);EVIDENCE.mkdir(parents=True,exist_ok=True)
    temporary=[BUILD/'labels.bin',BUILD/'cpu_main.packet']
    if any(path.exists() for path in temporary):raise ValueError('Prior fixture files are preserved; refusing replacement')
    files=[Path(__file__),Path(__file__).with_suffix('.cpp'),PROJECT/'Source/Host/MenuFrontEndAssets.h',
           PROJECT/'Source/Host/MenuLifecycleWindow.h',PROJECT/'tools/menu_frontend_assets.py',PROJECT/'tools/menu_frontend_cpu.py',PROJECT/'Tests/menu_frontend_scene_fixture.h',LOCALIZATION]
    files+=sorted(path for path in ASSETS.rglob('*') if path.is_file())
    before=[seal(path) for path in files]
    report=dict(schema='zerosis.original_frontend.offline_component.v1',scope='SDK_FREE_ORIGINAL_ASSET_SCENE_AND_BYTE_PARSER',
                native_window_execution=False,host_or_sdk_executed=False,gpu_execution=False,retail_pixel_acceptance=False,inputs_before=before)
    previous_path=EVIDENCE/'component_result.json'
    history_path=EVIDENCE/'component_cleanup.json'
    history=json.loads(history_path.read_text('utf8')) if history_path.exists() else (
        json.loads(previous_path.read_text('utf8')).get('cleanup',[]) if previous_path.exists() else [])
    try:
        window=(PROJECT/'Source/Host/MenuLifecycleWindow.h').read_text('utf8')
        native_window=(PROJECT/'Source/Presentation/BitmapWindow.cpp').read_text('utf8')
        source_checks={
            'backward_compatible_fourth_hook':'const MenuFrontEndHooks& hooks=MenuFrontEndHooks{}' in window,
            'old_scene_generation_inputs_rejected':'if(input.sceneGeneration!=window.SceneGeneration())continue;' in window,
            'owned_controls_captured_refresh':'created && (page==Page::Replay || page==Page::Options) && window.HasControlDragCapture()' in window,
            'captured_refresh_renders_actual_candidate':window.index('window.PrepareGpuFrame')<window.index('window.RefreshPreparedGpuFrame')<window.index('window.UpdatePreparedGpuSceneRetainingInput'),
            'changed_geometry_uses_normal_commit':'else if(!dragVisual)' in window and 'prepared?window.UpdatePreparedGpuSceneRetainingInput' in window,
            'actual_window_checks_all_input_geometry':all(term in native_window for term in ('sameHits(scene.hits,hits_)','sameHits(scene.scrolls,scrolls_)','scene.pixelHits.indices!=pixelHits_.indices','scene.pixelHits.keys!=pixelHits_.keys')),
            'no_unowned_system_font':'DWriteCreateFactory' not in window and 'Malgun Gothic' not in window,
        }
        if not all(source_checks.values()):raise ValueError('Front-end source/geometry contract differs: '+repr(source_checks))
        report['source_only_contract_checks']=source_checks
        report['localized_release_labels']=labels(temporary[0])
        built=build_program(name='MenuFrontEndComponent',architecture='x64',
            vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),directory=BUILD,evidence=EVIDENCE,
            source=Path(__file__).with_suffix('.cpp'),includes=[PROJECT/'Source/Host'])
        imported=run([Path(built['compiler']).with_name('dumpbin.exe'),'/dependents',built['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)),key=str.lower)
        if imported.returncode or not names or {name.lower() for name in names}!={'kernel32.dll'}:raise RuntimeError('Unexpected SDK-free component import: '+repr(names))
        report.update(build=built,imported_dlls=names)
        result=run([built['path'],ASSETS,*temporary],cwd=BUILD,timeout=30)
        if result.returncode:raise RuntimeError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout.decode('utf8')))
        report['cpu_proof']=cpu_render(temporary[1],EVIDENCE/'cpu_main_original_assets.png')
        after=[seal(path) for path in files]
        if [(row['bytes'],row['sha256']) for row in before]!=[(row['bytes'],row['sha256']) for row in after]:raise ValueError('Read-only original/production inputs changed during component fixture')
        report['inputs_after']=after;report['protected_inputs_unchanged']=True
    except Exception as error:
        report.update(status='FAIL_ORIGINAL_FRONTEND_OFFLINE_COMPONENT',error=str(error));raise
    finally:
        removed=[]
        for path in temporary+[BUILD/name for name in ('MenuFrontEndComponent.obj','MenuFrontEndComponent.map','compile.rsp','read_build_environment.cmd')]:
            if not path.exists():continue
            if path.absolute().parent!=BUILD.absolute():raise ValueError('Cleanup escaped the exact owned component directory')
            row=seal(path)
            if path.stat().st_nlink!=1:raise ValueError('Component intermediate acquired an unexpected hardlink')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_INTERMEDIATE';removed.append(row)
        report['cleanup']=removed
        history+=removed;history_path.write_text(json.dumps(history,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
        (EVIDENCE/'component_result.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps({key:report[key] for key in ('status','checks','controls','texture_bank','protected_inputs_unchanged','native_window_execution','gpu_execution')}))


if __name__=='__main__':main()
