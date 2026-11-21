"""Compile/run production press metadata helpers only; no window or SDK link."""
from __future__ import annotations
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
from menu_replay_restoration import build_cxx14
from menu_replay_assets import artifact
from menu_suite_storage import storage
from native_build import run

BUILD=PROJECT/'Build/BitmapPointerMetadata/current'
EVIDENCE=PROJECT/'evidence/game_menu/replay_calendar_legend/calendar/pointer_metadata'
SOURCE=PROJECT/'Source/Presentation'
BACKUPS=PROJECT/'evidence/game_menu/replay_calendar_legend/source_before'


def main():
    EVIDENCE.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    inputs=[SOURCE/'BitmapPointerPress.h',SOURCE/'BitmapWindow.h',SOURCE/'BitmapWindow.cpp',
        PROJECT/'Tests/bitmap_pointer_metadata.cpp',Path(__file__),PROJECT/'tools/native_build.py']
    before=[artifact(path) for path in inputs]
    backup_rows=[]
    for name,tag in [('BitmapWindow.h','216c19b5251f03ef'),('BitmapWindow.cpp','a2c40165a62c594f')]:
        path=BACKUPS/('Source__Presentation__'+name+'.'+tag+'.gz')
        original=gzip.decompress(path.read_bytes());backup_rows.append(dict(artifact(path),original_sha256=hashlib.sha256(original).hexdigest()))
    signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest()[:16]
    receipt=EVIDENCE/'result.json'
    if receipt.exists():
        old=json.loads(receipt.read_text('utf8'));retained=Path(old.get('build',{}).get('path','NO_RETAINED_FIXTURE'))
        if old.get('input_signature')==signature and old.get('status')=='PASS_SDK_FREE_BITMAP_POINTER_METADATA' and retained.is_file() and artifact(retained)['sha256']==old.get('build',{}).get('sha256'):
            print(json.dumps(dict(status=old['status'],reused_existing_identical_inputs=True,report=str(receipt))));return 0
    report=dict(schema='zerosis.bitmap.pointer_metadata.v1',input_signature=signature,inputs_before=before,
        changed_file_backups=backup_rows,source_encoding='ASCII / windows-1252',
        hwnd_host_sdk_gpu_executed=False,
        scope='Compile actual BitmapInputEvent declaration and execute production SDK-free identity/origin/stamping/coalescing/queue helpers. BitmapWindow.cpp/HWND are not linked or executed.',
        native_order_contract=['WM_LBUTTONDOWN allocates a nonzero per-window monotonic ID and logical origin before the first ControlDrag.',
            'A coalesced first move retains the physical down origin. Different IDs never coalesce, including missing/cancelled releases.',
            'WM_LBUTTONUP ControlClick carries the same original ID/origin. Existing hit-domain/generation filtering is unchanged.',
            'Cancellation clears active presses, not the sequence. Host must observe capture loss to finish a drag without a click.',
            'UINT64_MAX can be issued once; further presses fail and latch the existing queue overflow error instead of wrapping.'])
    cleanup_names=['BitmapPointerMetadata.obj','BitmapPointerMetadata.map','compile.rsp','read_build_environment.cmd']
    try:
        if any(any(value>127 for value in path.read_bytes()) for path in inputs[:5]):raise ValueError('Window metadata source must remain ASCII')
        compiled=build_cxx14('BitmapPointerMetadata',BUILD,EVIDENCE,PROJECT/'Tests/bitmap_pointer_metadata.cpp',[SOURCE])
        report['build']=compiled
        imported=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',imported.stdout.decode('mbcs',errors='replace'),re.M)))
        if imported.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected pure fixture dependency '+repr(names))
        report['component_imported_dlls']=names
        result=run([compiled['path']],cwd=BUILD,timeout=30)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout))
        report['inputs_after']=[artifact(path) for path in inputs]
        if report['inputs_after']!=before:raise ValueError('Production metadata inputs changed during component check')
    except Exception as error:
        report.update(status='FAIL_SDK_FREE_BITMAP_POINTER_METADATA',error=str(error));raise
    finally:
        removed=[]
        for name in cleanup_names:
            path=BUILD/name
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=BUILD.absolute() or info.st_nlink!=1:raise ValueError('Unsafe metadata intermediate cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],allocated_bytes=storage.allocated(path))
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Metadata cleanup identity changed')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_POINTER_METADATA_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed
        report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in removed)
        receipt.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],report=str(receipt))))
    return 0


if __name__=='__main__':raise SystemExit(main())
