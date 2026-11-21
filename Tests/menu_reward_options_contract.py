"""SDK-free V3 reward preference migration and confirmed atomic publication."""
from __future__ import annotations
import gzip
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
STAGE=PROJECT/'evidence/game_menu/options_reward_popups/contract'
BUILD=PROJECT/'Build/MenuRewardOptionsContract/current'
HEADER=PROJECT/'Source/Host/MenuOptionsContract.h'
STORE=PROJECT/'Source/Host/MenuOptionsStore.h'
CPP=PROJECT/'Tests/menu_reward_options_contract.cpp'
MIGRATION=PROJECT/'evidence/game_menu/options_reward_popups/migration_plan.json'
BACKUP=PROJECT/'evidence/game_menu/options_reward_popups/source_before/Source__Host__MenuOptionsContract.h.16c6d764726bd38c.gz'
STORE_BACKUP=PROJECT/'evidence/game_menu/options_reward_popups/source_before/Source__Host__MenuOptionsStore.h.01ebd1393baa12e0.gz'


def source_scope():
    old=gzip.decompress(BACKUP.read_bytes()).decode('utf8').replace('\r\n','\n');current=HEADER.read_text('utf8');start='class MenuOptionsSession final {'
    original=old[old.index(start):];adapted=current[current.index(start):]
    begin=adapted.index("    // Bind the Host's stable confirmed snapshot");end=adapted.index('    void Begin(',begin);adapted=adapted[:begin]+adapted[end:]
    for line in ['            else if(key=="noRewardPopups")next.noRewardPopups=value!=0;\n','        if(key=="noRewardPopups")return v.noRewardPopups?1:0;\n','        if(caps_.noRewardPopups)cached_.noRewardPopups=defaults.noRewardPopups;\n','    std::shared_ptr<std::atomic<bool>> noRewardPopupsSnapshot_;\n']:adapted=adapted.replace(line,'')
    begin=adapted.index('    void PublishNoRewardPopups() noexcept');end=adapted.index('    class BackendOperation',begin);adapted=adapted[:begin]+adapted[end:]
    adapted=adapted.replace('committed_=resolutionCandidate_;PublishNoRewardPopups();ClearPreview();','committed_=resolutionCandidate_;ClearPreview();').replace('committed_=candidate;PublishNoRewardPopups();','committed_=candidate;')
    if adapted!=original:raise ValueError('Transient20second session changed beyond explicit reward binding/publication/accessors')
    old_store=gzip.decompress(STORE_BACKUP.read_bytes()).decode('utf8').replace('\r\n','\n');new_store=STORE.read_text('utf8')
    restored=new_store.replace('only WriteAtomic publishes V3.','only WriteAtomic publishes V2.').replace('const auto bytes=MenuOptionsValues::Encode(value);const int publishedVersion=MenuOptionsValues::SchemaVersion(bytes);auto published=bytes;','const auto bytes=MenuOptionsValues::Encode(value);auto published=bytes;').replace('schemaVersion_=publishedVersion;','schemaVersion_=2;')
    if restored!=old_store:raise ValueError('Store changed beyond pre-publication encoded schema bookkeeping')
    return dict(contract_backup=artifact(BACKUP),store_backup=artifact(STORE_BACKUP),explicit_migration_plan=artifact(MIGRATION),
        existing_transient_session_byte_identical_except_new_reward_binding_publication_accessors=True,existing_store_byte_identical_except_prepublish_version_bookkeeping=True,
        no_user_callback_after_persist=True,initial_bind_healthy_inactive_owner_once=True,publication='Private noexcept release-store after successful persistence and committed assignment; reader acquire-loads the same retained atomic.',
        native_host_sdk_hwnd_gpu_audio_or_original_preferences_changed=False)


def main():
    STAGE.mkdir(parents=True,exist_ok=True);BUILD.mkdir(parents=True,exist_ok=True);scope=source_scope()
    inputs=[HEADER,STORE,CPP,Path(__file__),MIGRATION,BACKUP,STORE_BACKUP,PROJECT/'Source/Host/MenuResolutionCountdown.h',PROJECT/'Source/Host/MenuResolutionPreviewClock.h',PROJECT/'tools/native_build.py',PROJECT/'Tests/menu_replay_restoration.py']
    before=[artifact(path) for path in inputs];recipe=inspect.getsource(build_cxx14);signature=hashlib.sha256(json.dumps(before,sort_keys=True).encode()+recipe.encode()).hexdigest()[:20]
    evidence=STAGE/('attempt_'+signature);receipt=evidence/'result.json'
    if receipt.exists():
        old=json.loads(receipt.read_text('utf8'))
        if old.get('status')=='PASS_REWARD_V3_LEGACY_READ_AND_CONFIRMED_ATOMIC_PUBLICATION' and old.get('inputs_before')==before and artifact(old['build']['path'])['sha256']==old['build']['sha256']:
            print(json.dumps(dict(status=old['status'],report=str(receipt),reused_identical_inputs=True)));return 0
        raise ValueError('Existing reward contract proof cannot be overwritten')
    evidence.mkdir();owned=BUILD/('owned_preferences_'+signature)
    if owned.exists():raise ValueError('Unresolved prior owned reward preferences exist')
    owned.mkdir();report=dict(schema='zerosis.menu_reward_options.contract.v1',input_signature=signature,inputs_before=before,source_scope=scope,compile_recipe_sha256=hashlib.sha256(recipe.encode()).hexdigest(),cpp_dialect='c++14',
        native_host_sdk_window_gpu_or_audio_executed=False,actual_owned_file_store=True,owned_file_store_root=str(owned),retail_gameplay_acceptance=False,
        limitations=['Fake applied staging and a real shared atomic validate publication ordering; no SDK/game/display/audio backend executes.',
                    'Actual Store IO is restricted to this newly created owned directory; original preferences, installed mods and user saves are untouched.',
                    'Existing countdown behavior is exercised inside the preview workflows without rerunning the unchanged standalone countdown or view suites.'])
    try:
        if any(any(byte>127 for byte in path.read_bytes()) for path in (HEADER,CPP)):raise ValueError('Reward contract C++14 source must remain ASCII')
        report['build']=build_cxx14('MenuRewardOptionsContract',BUILD,evidence,CPP,[PROJECT/'Source/Host']);compiled=report['build']
        deps=run([Path(compiled['compiler']).with_name('dumpbin.exe'),'/dependents',compiled['path']],cwd=BUILD,timeout=30);names=sorted(set(re.findall(r'^\s+([A-Za-z0-9_.-]+\.dll)\s*$',deps.stdout.decode('mbcs',errors='replace'),re.M)))
        if deps.returncode or {name.lower() for name in names}!={'kernel32.dll'}:raise ValueError('Unexpected reward console imports '+repr(names))
        report['component_imported_dlls']=names;result=run([compiled['path'],str(owned)],cwd=BUILD,timeout=60)
        if result.returncode:raise ValueError((result.stdout+result.stderr).decode('utf8',errors='replace'))
        report.update(json.loads(result.stdout));report['inputs_after']=[artifact(path) for path in inputs]
        if before!=report['inputs_after']:raise ValueError('Reward contract inputs changed during fixture')
    except Exception as error:
        report.update(status='FAIL_REWARD_V3_LEGACY_READ_AND_CONFIRMED_ATOMIC_PUBLICATION',error=str(error));raise
    finally:
        removed=[];directories=[];children={'legacy_v1','legacy_v2','blocked_pending','display_only','partial_then_timeout','unknown_schema'};names={'menu-options.lock','menu-options.pending','menu-options.zssettings'}
        for directory,dirs,files in os.walk(owned):
            directory=Path(directory)
            if directory!=owned and (directory.parent!=owned or directory.name not in children):raise ValueError('Unexpected owned reward preference subdirectory')
            if os.stat(directory,follow_symlinks=False).st_file_attributes&0x400:raise ValueError('Owned preference path is a reparse directory')
            directories.append(directory)
            for name in files:
                path=directory/name
                if directory==owned or name not in names:raise ValueError('Unexpected owned reward preference data')
                info=storage.ordinary(path)
                if info.st_nlink!=1:raise ValueError('Owned reward preference data unexpectedly hardlinked')
                row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,file_attributes=info.st_file_attributes,links=info.st_nlink,allocated_bytes=storage.allocated(path))
                if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Owned preference changed before cleanup')
                path.unlink();row['result']='DELETED_EXACT_OWNED_REWARD_PREFERENCE_TEST_DATA';removed.append(row)
        for directory in sorted(directories,key=lambda path:len(path.parts),reverse=True):
            if any(directory.iterdir()):raise ValueError('Owned reward preference directory is not empty')
            directory.rmdir()
        for name in ['MenuRewardOptionsContract.obj','MenuRewardOptionsContract.map','compile.rsp','read_build_environment.cmd']:
            path=BUILD/name
            if not path.exists():continue
            info=storage.ordinary(path)
            if path.absolute().parent!=BUILD.absolute() or info.st_nlink!=1:raise ValueError('Unsafe owned reward intermediate cleanup')
            row=dict(artifact(path),file_identity=[info.st_dev,info.st_ino],mtime_ns=info.st_mtime_ns,file_attributes=info.st_file_attributes,links=info.st_nlink,allocated_bytes=storage.allocated(path))
            if storage.metadata(info)!=storage.metadata(storage.ordinary(path)):raise ValueError('Reward intermediate changed before cleanup')
            path.unlink();row['result']='DELETED_EXACT_OWNED_REGENERABLE_REWARD_CONTRACT_INTERMEDIATE';removed.append(row)
        report['owned_intermediate_cleanup']=removed;report['owned_intermediate_bytes_removed']=sum(row['bytes'] for row in removed);report['owned_intermediate_allocated_bytes_removed']=sum(row['allocated_bytes'] for row in removed);report['owned_store_directory_removed']=not owned.exists()
        receipt.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(dict(status=report['status'],checks=report['checks'],report=str(receipt),cleaned_allocated_bytes=report['owned_intermediate_allocated_bytes_removed'])));return 0


if __name__=='__main__':raise SystemExit(main())
