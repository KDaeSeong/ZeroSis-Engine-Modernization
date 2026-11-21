"""Read-only preservation/storage audit and small final receipts; no engine run."""
import ctypes
from ctypes import wintypes
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import time

STAGE=Path(__file__).resolve().parent
PROJECT=STAGE.parents[2]


def read(path):
    return json.loads(path.read_bytes())


def seal(path):
    raw=path.read_bytes()
    return dict(path=str(path),bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


class Standard(ctypes.Structure):
    _fields_=[('AllocationSize',ctypes.c_longlong),('EndOfFile',ctypes.c_longlong),
              ('NumberOfLinks',wintypes.DWORD),('DeletePending',wintypes.BOOLEAN),('Directory',wintypes.BOOLEAN)]


kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.CreateFileW.argtypes=[wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
kernel.CreateFileW.restype=wintypes.HANDLE
kernel.GetFileInformationByHandleEx.argtypes=[wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]
kernel.GetFileInformationByHandleEx.restype=wintypes.BOOL
kernel.CloseHandle.argtypes=[wintypes.HANDLE]


def allocation(path):
    handle=kernel.CreateFileW(str(path),0x80,7,None,3,0,None)
    if handle==wintypes.HANDLE(-1).value:
        raise OSError(ctypes.get_last_error(),str(path))
    try:
        value=Standard()
        if not kernel.GetFileInformationByHandleEx(handle,1,ctypes.byref(value),ctypes.sizeof(value)):
            raise OSError(ctypes.get_last_error(),str(path))
        return value.AllocationSize
    finally:
        kernel.CloseHandle(handle)


def main():
    assert sys.dont_write_bytecode
    assert not (STAGE/'final_audit.json').exists(), 'Do not overwrite a completed audit'
    before=read(STAGE/'before.json')
    for row in before['protected']:
        path=Path(row['path']);current=seal(path);info=path.stat()
        assert current['bytes']==row['bytes'] and current['sha256']==row['sha256'], str(path)
        assert [info.st_dev,info.st_ino]==row['file_identity']
        assert (info.st_mtime_ns,info.st_file_attributes,info.st_nlink)==(row['mtime_ns'],row['attributes'],row['links'])
        assert not info.st_file_attributes&0x400
        assert allocation(path)==row['allocated_bytes']
    for row in before['sources']:
        backup=row['backup'];blob=Path(backup['path']).read_bytes()
        assert len(blob)==backup['bytes'] and hashlib.sha256(blob).hexdigest()==backup['sha256']
        original=gzip.decompress(blob)
        assert len(original)==row['bytes'] and hashlib.sha256(original).hexdigest()==row['sha256']
    manifest=read(STAGE/'source_manifest.json')
    for row in [*manifest['production_sources'],*manifest['test_sources']]:
        assert seal(Path(row['path']))==row
    for row in manifest['proofs'].values():
        assert seal(Path(row['path']))==row
    publication=read(STAGE/'publication.json')
    for row in publication['after_metadata']:
        assert seal(Path(row['path']))==row
    progress=read(PROJECT/'evidence/save_menu/20261013_original_screen/current_progress.json')
    assert progress['latest_source_matches_linked_candidate'] is False
    assert progress['prepared_runtime_matches_latest_source'] is False
    assert progress['current_prepared_runtime']['working_host_source_differs_from_runtime'] is True
    assert progress['current_native_or_screen_relaunch_allowed'] is False
    assert progress['screen_verification_deferred'] is True
    assert progress['full_engine_goal_complete'] is False
    cleanup=read(STAGE/'cleanup_result.json')
    plan=read(STAGE/'cleanup_plan.json')
    assert seal(STAGE/'cleanup_plan.json')['sha256']==cleanup['plan_sha256']
    for row in plan['candidates']:
        assert not os.path.lexists(row['path'])
    for row in plan['protected_success']:
        current=seal(Path(row['path']))
        assert (current['bytes'],current['sha256'])==(row['bytes'],row['sha256'])
    dds=read(STAGE/'driver_shown_source_gate.json')
    assert dds['cleanup_status']=='DELETED_EXACT_OWN_TEMPORARY_FILE'
    assert not os.path.lexists(dds['temporary_regenerated_font_dds']['path'])
    assert not (STAGE/'driver_shown_candidate').exists()
    assert not (STAGE/'driver_empty_candidate').exists()
    assert not list((PROJECT/'Build').glob('game-menu-assets-test-*'))
    preserved=dict(status='PASS_PROTECTED_RUNTIME_SAVES_AND_SOURCE_BACKUPS',
                   protected_paths=len(before['protected']),source_backups=len(before['sources']),
                   all_runtime_bytes_ids_mtimes_attributes_links_and_allocation_unchanged=True,
                   all_source_backups_verified_roundtrip=True,all_current_source_and_proof_hashes_match=True,
                   original_install_MODS_settings_or_user_saves_written=False,
                   current_native_or_screen_relaunch_allowed=False)
    (STAGE/'preservation_audit.json').write_text(json.dumps(preserved,indent=2)+'\n',encoding='utf-8')

    start=time.monotonic();seen=set();paths=aliases=logical=allocated=0;skipped=[];errors=[]
    def scan(directory):
        nonlocal paths,aliases,logical,allocated
        with os.scandir(directory) as entries:
            for entry in entries:
                try:
                    # Windows DirEntry.stat() yields zero file IDs on Python 3.14.
                    info=os.stat(entry.path,follow_symlinks=False)
                    if info.st_file_attributes&0x400:
                        skipped.append(entry.path);continue
                    if stat.S_ISDIR(info.st_mode):
                        scan(entry.path)
                    elif stat.S_ISREG(info.st_mode):
                        assert info.st_dev and info.st_ino and info.st_nlink
                        paths+=1;identity=(info.st_dev,info.st_ino)
                        if identity in seen:
                            aliases+=1;continue
                        seen.add(identity);logical+=info.st_size;allocated+=allocation(entry.path)
                except OSError as error:
                    errors.append(dict(path=entry.path,error=str(error)))
    scan(PROJECT)
    assert not errors and not skipped
    previous=read(STAGE/'storage_before.json')
    assert previous['unique_file_ids']>100000 and previous['unique_allocated_bytes']>10*1024**3
    storage=dict(schema='zerosis.game_menu.offline_exit.storage_after.v1',scope=str(PROJECT),
                 file_paths=paths,unique_file_ids=len(seen),hardlink_aliases_deduplicated=aliases,
                 unique_logical_bytes=logical,unique_allocated_bytes=allocated,
                 previous_unique_logical_bytes=previous['unique_logical_bytes'],
                 previous_unique_allocated_bytes=previous['unique_allocated_bytes'],
                 net_logical_bytes=logical-previous['unique_logical_bytes'],
                 net_allocated_bytes=allocated-previous['unique_allocated_bytes'],
                 deleted_temporary_files=cleanup['deleted_files']+1,
                 deleted_temporary_directories=cleanup['deleted_directories']+dds['temporary_directories_removed'],
                 temporary_logical_bytes_removed=cleanup['freed_logical_bytes']+dds['logical_bytes_removed'],
                 temporary_allocated_bytes_released=cleanup['freed_allocated_bytes']+dds['allocated_bytes_released'],
                 task_disposable_payload_remaining_bytes=0,
                 threshold_bytes=10*1024**3,task_disposable_threshold_exceeded=False,
                 errors=errors,reparse_skipped=skipped,elapsed_seconds=round(time.monotonic()-start,3),
                 measurement='Real os.stat file identities; FileStandardInfo.AllocationSize; hardlink aliases counted once. Directory allocation excluded.',
                 scope_note='Before excludes this then-new task stage; after includes it. This is the project total, not volume free space. This storage receipt and final audit are written after the scan and add small overhead.')
    (STAGE/'storage_after.json').write_text(json.dumps(storage,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    final=dict(schema='zerosis.game_menu.offline_exit.final_audit.v1',
               status='PASS_SOURCE_ONLY_EXIT_MENU_AND_OFFLINE_CHECKS_CURRENT_RUNTIME_PRESERVED',
               source_manifest=seal(STAGE/'source_manifest.json'),publication=seal(STAGE/'publication.json'),
               preservation=seal(STAGE/'preservation_audit.json'),storage=seal(STAGE/'storage_after.json'),
               cleanup=[seal(STAGE/'cleanup_result.json'),seal(STAGE/'driver_shown_source_gate.json')],
               completed_scope='Separate unchanged original ExitConfirm source, callback/owner lifecycle and complete input/driver/render/pixel source routing with explicit offline evidence.',
               actual_original_ui_native_exit_or_shutdown_verified=False,
               new_current_source_host_embedded_or_linked=False,
               old_runtime_or_default_promoted=False,full_engine_goal_complete=False,
               screen_verification_deferred=True,current_native_or_screen_relaunch_allowed=False,
               remaining=['Other unsupported menus remain unfinished.','Generate/embed/link and freeze a new current-source Host before using this feature.','After explicit human release, verify actual modal display, No/Escape/Yes, WM_CLOSE order, SDK teardown and save preservation.'])
    (STAGE/'final_audit.json').write_text(json.dumps(final,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=final['status'],preserved_paths=preserved['protected_paths'],
                         project_allocated_bytes=allocated,project_net_allocated_bytes=storage['net_allocated_bytes'],
                         temporary_files_deleted=storage['deleted_temporary_files'],
                         temporary_allocated_bytes_released=storage['temporary_allocated_bytes_released']),ensure_ascii=False))


if __name__=='__main__':
    main()
