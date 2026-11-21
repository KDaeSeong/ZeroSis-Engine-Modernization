"""Transient display preview regression with legacy reads and explicit V3 writes.

Executes only a C++14 Kernel32 console with fake display/audio backends and the
real file store in one newly created owned directory. No native window, SDK,
GPU, audio device or UI inspection runs.
"""
from __future__ import annotations
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import sys

sys.dont_write_bytecode=True
PROJECT=Path(__file__).absolute().parents[1]
sys.path.insert(0,str(PROJECT/'tools'));sys.path.insert(0,str(PROJECT/'Tests'))
from menu_replay_restoration import build_cxx14
from menu_frontend_assets import artifact
from menu_suite_storage import storage
from native_build import run
from menu_reward_options_contract import source_scope as reward_source_scope

STAGE=PROJECT/'evidence/game_menu/options_reward_popups/contract/preview_regression'
BUILD=PROJECT/'Build/MenuResolutionPreview/current'
HEADER=PROJECT/'Source/Host/MenuOptionsContract.h'
STORE=PROJECT/'Source/Host/MenuOptionsStore.h'
CPP=PROJECT/'Tests/menu_resolution_preview.cpp'
BACKUP=PROJECT/'evidence/game_menu/options_reward_popups/source_before/Source__Host__MenuOptionsContract.h.16c6d764726bd38c.gz'


def source_scope():
    scope=reward_source_scope()
    scope.update(original_20second_session_preserved_with_only_explicit_reward_extensions=True,
        exact_legacy_v1_v2_read_literals_retained=True,explicit_new_write_version=3,preview_state_serialized=False,
        backend_snapshot_lifetime='Retained only during the active owned preview; all completion/failure paths clear it before controller/window destruction.',
        destructor_policy='Owner-thread Discard restores/fails closed without throwing restore failure; wrong-thread/reentrant use remains an ownership violation.')
    return scope


def main():
    STAGE.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True)
    scope=source_scope();inputs=[HEADER,STORE,CPP,Path(__file__),BACKUP,PROJECT/'Tests/menu_reward_options_contract.py',PROJECT/'evidence/game_menu/options_reward_popups/migration_plan.json',PROJECT/'tools/native_build.py',PROJECT/'Tests/menu_replay_restoration.py']
    before=[artifact(path) for path in inputs];recipe=inspect.getsource(build_cxx14)
    signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()+recipe.encode()).hexdigest()[:20]
    evidence=STAGE/('attempt_'+signature);receipt=evidence/'result.json'
    if receipt.exists():
        old=json.loads(receipt.read_text('utf8'))
        if old.get('status')=='PASS_TRANSIENT_RESOLUTION_PREVIEW_AND_CANONICAL_V3_STORE' and old.get('inputs_before')==before and artifact(old['build']['path'])['sha256']==old['build']['sha256']:
            print(json.dumps(dict(status=old['status'],report=str(receipt),reused_existing_identical_inputs=True)));return 0
        raise ValueError('Existing resolution-preview evidence cannot be overwritten or replayed')
    evidence.mkdir();owned=BUILD/('owned_preferences_'+signature)
    if owned.exists():raise ValueError('Unresolved prior owned preference directory exists')
    owned.mkdir()
    report=dict(schema='zerosis.menu_resolution_preview.reward_v3_regression.v1',input_signature=signature,inputs_before=before,source_scope=scope,
        compile_recipe_sha256=hashlib.sha256(recipe.encode()).hexdigest(),cpp_dialect='c++14',source_encoding='ASCII / windows-1252',
        native_host_sdk_window_gpu_or_audio_executed=False,actual_file_store_executed=True,owned_file_store_root=str(owned),
        flow_contract=dict(direct_resolution_button='Preview committed values with only cached width/height/fullscreen; Yes persists that canonical display and retains unrelated drafts; No restores the last confirmed display.',
            original_ok_button='Commit cached non-display fields with old display first, retain pending display and active owner, then preview resolution. No/timeout retains the prior successful non-display commit.',
            confirm='Read back the exact preview and atomically persist canonical V3, then replace confirmed display baseline without closing the options transaction.',
            failure='Recoverable failure restores exact committed backend, resets cached display and retains other drafts; failed restore faults/closes and clears the callback.',
            shutdown='Cancel restores before discarding all drafts; owner-thread Discard restores without requiring a live player/turn and never propagates restore failure into controller destruction.'),
        limitations=['Fake backend requests and readbacks prove transaction ordering/ownership; they are not actual display, audio, HWND, GPU or game acceptance.',
                    'The real MenuOptionsStore executes only inside this newly created owned directory; original preferences, saves and runtime settings are untouched.',
                    'The controller owns the20-second timer and its actual modal UI/lifetime integration; this component supplies transient transaction behavior and destructor-pattern regression only.'])
    cleanup_names=['MenuResolutionPreview.obj','MenuResolutionPreview.map','compile.rsp','read_build_environment.cmd']
    try:
        old_exe=BUILD/'MenuResolutionPreview.exe'
        if old_exe.exists():
            info=storage.ordinary(old_exe)
            if info.st_nlink!=1:raise ValueError('Prior preview console unexpectedly has aliases')
            old_row=dict(artifact(old_exe),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,file_attributes=info.st_file_attributes,links=info.st_nlink,allocated_bytes=storage.allocated(old_exe))
            previous=[PROJECT/'evidence/game_menu/options_video_preview/session/attempt_ab261319b85a55f59e60/result.json',*STAGE.rglob('result.json')]
            matches=[]
            for path in previous:
                if not path.exists():continue
                proof=json.loads(path.read_text('utf8'))
                if proof.get('build',{}).get('path','').casefold()==str(old_exe).casefold() and proof['build'].get('sha256')==old_row['sha256']:matches.append(artifact(path))
            if not matches:raise ValueError('Prior preview console is not an exact known owned proof')
            report['prior_current_console_reused_after_exact_precheck']=dict(executable=old_row,proofs=matches,old_intermediates_absent=all(not (BUILD/name).exists() for name in cleanup_names),physical_copy_created=False)
            if not report['prior_current_console_reused_after_exact_precheck']['old_intermediates_absent']:raise ValueError('Unresolved prior preview intermediates')
        if any(any(byte>127 for byte in path.read_bytes()) for path in (HEADER,CPP)):raise ValueError('C++14 preview source must remain ASCII')
        report['build']=build_cxx14('MenuResolutionPreview',BUILD,evidence,CPP,[PROJECT/'Source/Host'])
        compiled=report['build'];dependencies=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=BUILD,timeout=30)
        names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',dependencies.stdout.decode('mbcs',errors='replace'),re.M)))
        if dependencies.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected SDK-free resolution preview imports '+repr(names))
        report['component_imported_dlls']=names;result=run([compiled['path'],str(owned)],cwd=BUILD,timeout=60)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout));report['inputs_after']=[artifact(path) for path in inputs]
        if before!=report['inputs_after']:raise ValueError('Owned session/store inputs changed during fixture')
    except Exception as error:
        report.update(status='FAIL_TRANSIENT_RESOLUTION_PREVIEW_AND_CANONICAL_V3_STORE',error=str(error));raise
    finally:
        removed=[];directories=[]
        store_names={'menu-options.zssettings','menu-options.lock','menu-options.pending'}
        allowed_children={'v1_confirm','blocked_atomic','original_ok_then_no'}
        for directory,dirs,names in os.walk(owned):
            directory=Path(directory)
            if directory!=owned and (directory.parent!=owned or directory.name not in allowed_children):raise ValueError('Unexpected owned store subdirectory; preserve for review')
            st=os.stat(directory,follow_symlinks=False)
            if st.st_file_attributes&0x400:raise ValueError('Owned preference fixture encountered a reparse point')
            directories.append(directory)
            for name in names:
                path=directory/name
                if name not in store_names or directory==owned:raise ValueError('Unexpected owned store data; preserve for review')
                info=storage.ordinary(path)
                if info.st_nlink!=1:raise ValueError('Owned store fixture file unexpectedly has hardlinks')
                row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,file_attributes=info.st_file_attributes,links=info.st_nlink,allocated_bytes=storage.allocated(path))
                if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Owned store fixture changed before cleanup')
                path.unlink();row['result']='DELETED_EXACT_OWNED_PRIVATE_SETTINGS_TEST_DATA';removed.append(row)
        for directory in sorted(directories,key=lambda path:len(path.parts),reverse=True):
            if any(directory.iterdir()):raise ValueError('Owned store directory is not empty after exact cleanup')
            directory.rmdir()
        for name in cleanup_names:
            path=BUILD/name
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=BUILD.absolute() or info.st_nlink!=1:raise ValueError('Unsafe resolution preview intermediate cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,file_attributes=info.st_file_attributes,links=info.st_nlink,allocated_bytes=storage.allocated(path))
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Resolution preview intermediate changed before cleanup')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_RESOLUTION_PREVIEW_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed;report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in removed);report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in removed)
        report['owned_store_directory_removed']=not owned.exists();receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],report=str(receipt),cleaned_allocated_bytes=report['owned_intermediate_allocated_bytes_removed'])));return 0


if __name__=='__main__':raise SystemExit(main())
