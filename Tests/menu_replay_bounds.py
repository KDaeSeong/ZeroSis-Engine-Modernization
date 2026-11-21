"""Actual SDK-writer-format adversarial display bounds; no Host/SDK/window/GPU."""
from __future__ import annotations
import json
from pathlib import Path
import re
import sys

PROJECT=Path(__file__).absolute().parents[1]
sys.dont_write_bytecode=True
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
from native_build import build_program,run
from menu_replay_assets import artifact
from menu_suite_storage import storage
import menu_replay_offline as writer

BUILD=PROJECT/'Build/MenuReplayBoundsComponent/current'
STAGE=PROJECT/'evidence/game_menu/original_menu_followup/replay/bounds'


def main():
    BUILD.mkdir(parents=True,exist_ok=True);STAGE.mkdir(parents=True,exist_ok=True)
    receipt=STAGE/'result.json'
    if receipt.exists():raise ValueError('Inspect existing bounds proof before repeating')
    inputs=[PROJECT/'Source/Host'/name for name in ('MenuReplayData.h','MenuReplayTimeline.h','MenuReplayPresentation.h','MenuFrontEndAssets.h')]
    before=[artifact(path) for path in inputs]
    report=dict(schema='zerosis.menu_replay.display_bound_fixture.v1',inputs_before=before,
        synthetic_fixture_history=True,host_or_sdk_executed=False,window_or_gpu_created=False)
    try:
        writer.BUILD=BUILD;report['actual_sdk_writer_extraction']=writer.extract_writer()
        built=build_program(name='MenuReplayBoundsComponent',architecture='x64',
            vs=Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community'),directory=BUILD,evidence=STAGE,
            source=Path(__file__).with_suffix('.cpp'),includes=[PROJECT/'Source/Host',PROJECT/'Tests',BUILD])
        report['build']=built
        imported=run([Path(built['compiler']).with_name('dumpbin.exe'),'/dependents',built['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        if imported.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected component dependency: '+repr(names))
        report['imported_dlls']=names
        result=run([built['path'],PROJECT/'Source/Assets/UIFrontEnd'],cwd=BUILD,timeout=30)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout));after=[artifact(path) for path in inputs]
        if before!=after:raise ValueError('Production changed while exercising scene bounds')
        report['inputs_after']=after
    except Exception as error:
        report.update(status='FAIL_SDK_FREE_REPLAY_DISPLAY_BOUNDS',error=str(error));raise
    finally:
        removed=[]
        for name in ('MenuReplayBoundsComponent.obj','MenuReplayBoundsComponent.map','compile.rsp','read_build_environment.cmd','sdk_replay_writer.inc'):
            path=BUILD/name
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.parent!=BUILD or info.st_nlink!=1:raise ValueError('Bounds cleanup target escaped owned scope')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path));path.unlink()
            row['result']='DELETED_EXACT_OWNED_REGENERABLE_COMPONENT_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed;receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],scene_sprites=report['scene_sprites'],markers=report['rendered_point_markers'],report=str(receipt))))
    return 0


if __name__=='__main__':raise SystemExit(main())
