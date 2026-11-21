"""One-shot read-only protection and allocation baseline for the ExitConfirm build.

Only the two named evidence receipts are written. No process is launched and no
existing project file is changed or removed. Real os.stat identities are used:
Windows Python 3.14 DirEntry.stat identities are not used for deduplication.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import time

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/game_menu/exit_host_build'
PARENT_ID = '20261024T082423Z_b604cddf0d2d'
PARENT_ROOT = PROJECT / 'Build/UiWindowHost' / PARENT_ID
PARENT_REPORT = PROJECT / 'evidence/ui_window_host' / PARENT_ID / 'build_result.json'
SDK_REPORT = PROJECT / 'evidence/serialization/unit_great_work_save/sdk_2bdcdf80a1695780f864/result.json'
SDK_SHA = '430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9'
THRESHOLD = 10 * 1024 ** 3


def key(path):
    return os.path.normcase(os.path.abspath(path))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def ordinary(path):
    path = Path(os.path.abspath(path))
    for parent in (path, *path.parents):
        if parent.exists():
            assert not os.stat(parent, follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT, parent
    value = os.stat(path, follow_symlinks=False)
    assert stat.S_ISREG(value.st_mode) and value.st_dev and value.st_ino, path
    return value


def metadata(value):
    return dict(bytes=value.st_size, file_identity=[value.st_dev, value.st_ino],
                mtime_ns=value.st_mtime_ns, file_attributes=value.st_file_attributes,
                links=value.st_nlink)


class FILE_STANDARD_INFO(ctypes.Structure):
    _fields_ = [('AllocationSize', ctypes.c_longlong), ('EndOfFile', ctypes.c_longlong),
                ('NumberOfLinks', wintypes.DWORD), ('DeletePending', ctypes.c_ubyte),
                ('Directory', ctypes.c_ubyte)]


kernel = ctypes.WinDLL('kernel32', use_last_error=True)
kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD,
                              wintypes.LPVOID, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
kernel.CreateFileW.restype = wintypes.HANDLE
kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
kernel.CloseHandle.restype = wintypes.BOOL


def allocated(path):
    path = os.path.abspath(path)
    extended = path if path.startswith('\\\\?\\') else '\\\\?\\' + path
    handle = kernel.CreateFileW(extended, 0x80, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        value = FILE_STANDARD_INFO()
        if not kernel.GetFileInformationByHandleEx(handle, 1, ctypes.byref(value), ctypes.sizeof(value)):
            raise ctypes.WinError(ctypes.get_last_error())
        assert not value.Directory and not value.DeletePending, path
        return value.AllocationSize
    finally:
        kernel.CloseHandle(handle)


def path_rows(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and isinstance(value.get('sha256'), str):
            yield value
        for child in value.values():
            yield from path_rows(child)
    elif isinstance(value, list):
        for child in value:
            yield from path_rows(child)


def make_references():
    requirements = read(STAGE / 'requirements.json')
    source_before = read(STAGE / 'source_before.json')
    assert digest(PARENT_REPORT) == requirements['inputs']['parent_report_sha256']
    parent = read(PARENT_REPORT)
    previous = read(PROJECT / 'evidence/game_menu/offline_exit/before.json')
    mutable = {key(source_before[name]['path']) for name in ('mutable_header', 'mutable_prepared_report')}
    refs, groups = {}, {}

    def add(row, group):
        path = Path(row['path'])
        path = path if path.is_absolute() else PROJECT / path
        identity = key(path)
        assert identity not in mutable, ('Mutable derived input cannot be an immutable protected file', path)
        row = dict(row, path=str(path))
        if identity in refs:
            assert refs[identity]['sha256'] == row['sha256'], ('Conflicting pinned content', path)
        else:
            refs[identity] = row
        groups.setdefault(identity, set()).add(group)

    def fresh(path, group):
        add(dict(path=str(path), sha256=digest(path)), group)

    for row in previous['protected']:
        add(row, 'previous_current_prior_runtime_and_hold')
    frozen = {key(row['path']): row for row in path_rows(parent)
              if Path(row['path']).is_relative_to(PARENT_ROOT / 'frozen')}
    assert len(frozen) == 593
    for row in frozen.values():
        add(row, 'parent_frozen_closure')
    add(parent['executable'], 'parent_final_host')
    fresh(PARENT_REPORT, 'parent_build_report')
    add(parent['started'], 'parent_started_report')
    for name in ('compiler', 'linker', 'dumpbin'):
        add(parent[name], 'vc_toolchain')
    for row in read(parent['started']['path'])['toolchain_inputs']:
        add(row, 'vc_toolchain')
    prior_parent = read(parent['baseline_build']['path'])
    vcvars = [row for row in prior_parent['protected_artifacts']
              if Path(row['path']).name.casefold() == 'vcvars64.bat']
    assert len(vcvars) == 1
    add(vcvars[0], 'vc_toolchain')
    extra_native = [row for row in parent['protected_artifacts']
                    if row['path'].endswith('.zssave') and key(row['path']) not in refs]
    assert len(extra_native) == 4
    for row in extra_native:
        add(row, 'additional_native_save')

    release = read(PROJECT / 'Play/EarlyAccess/release.json')
    request_path = PROJECT / release['request']['path']
    add(release['request'], 'default_request')
    default = read(request_path)
    assert default['run_id'] == release['runtime_id'] == '20261012T121847Z_732a6d5f07ea'
    for row in default['runtime_inputs']:
        add(row, 'default_runtime_input')
    for name in ('launcher', 'resume_launcher'):
        add(default[name], 'default_runtime_launcher')
    for row in path_rows(default['interactive_ui_support_inventory']):
        add(row, 'default_frozen_ui_support')
    add(release['shared_launcher'], 'default_shared_launcher')
    for row in release['launchers'].values():
        add(row, 'default_user_launcher')

    sdk = read(SDK_REPORT)
    sdk_dll = sdk['artifacts']['CvGameCoreDLL_Expansion2_x64.dll']
    assert sdk_dll['sha256'] == SDK_SHA
    add(sdk_dll, 'selected_sdk_original')
    add(dict(path=str(PROJECT / 'Build/RuntimeInputCache/43' / SDK_SHA), sha256=SDK_SHA), 'selected_sdk_cache')
    fresh(SDK_REPORT, 'selected_sdk_report')
    for name in ('requirements.json', 'source_before.json'):
        fresh(STAGE / name, 'task_immutable_baseline_control')
    fresh(Path(__file__), 'storage_baseline_helper')
    allowances = []
    for name, recovery in (('mutable_header', 'header_recovery_ref'), ('mutable_prepared_report', 'prepared_recovery_ref')):
        row = source_before[name]
        actual = metadata(ordinary(row['path']))
        assert actual['bytes'] == row['bytes'] and digest(row['path']) == row['sha256']
        assert actual['file_identity'] == row['file_identity'] and actual['mtime_ns'] == row['mtime_ns']
        add(source_before[recovery], 'mutable_derived_recovery_donor')
        allowances.append(dict(path=row['path'], before=dict(row, **actual, allocated_bytes=allocated(row['path'])),
                               recovery_ref=source_before[recovery], allowed_change='Atomic replacement by the source-only asset refresh; immutable recovery donor must remain unchanged.'))
    return refs, groups, allowances


def seal_protection():
    refs, groups, allowances = make_references()
    rows, by_id = [], {}
    for identity in sorted(refs):
        expected = refs[identity]
        before = ordinary(expected['path'])
        current = metadata(before)
        file_id = tuple(current['file_identity'])
        if file_id not in by_id:
            by_id[file_id] = dict(sha256=digest(expected['path']), allocated_bytes=allocated(expected['path']))
        assert by_id[file_id]['sha256'] == expected['sha256'], ('Pinned SHA mismatch', expected['path'])
        after = ordinary(expected['path'])
        assert metadata(before) == metadata(after), ('File changed while sealing', expected['path'])
        for field in ('bytes', 'file_identity', 'mtime_ns'):
            if field in expected:
                assert current[field] == expected[field], (expected['path'], field)
        expected_attrs = expected.get('file_attributes', expected.get('attributes'))
        if expected_attrs is not None:
            assert current['file_attributes'] == expected_attrs, (expected['path'], 'file_attributes')
        rows.append(dict(path=expected['path'], **current, **by_id[file_id], roles=sorted(groups[identity])))
    for row in rows:
        assert metadata(ordinary(row['path'])) == {name: row[name] for name in ('bytes', 'file_identity', 'mtime_ns', 'file_attributes', 'links')}
    aliases = {}
    for row in rows:
        aliases.setdefault(tuple(row['file_identity']), []).append(row['path'])
    return dict(schema='zerosis.exit_host_build.protection_before.v1',
                status='PASS_DIRECT_HASH_SEALED_PROTECTED_BASELINE',
                utc=datetime.now(timezone.utc).isoformat(), protected_artifacts=rows,
                mutable_allowances=allowances, protected_paths=len(rows), unique_file_ids=len(by_id),
                hardlink_aliases_deduplicated=len(rows)-len(by_id),
                protected_path_logical_bytes=sum(row['bytes'] for row in rows),
                unique_allocated_bytes=sum(row['allocated_bytes'] for row in by_id.values()),
                same_identity_aliases=[dict(file_identity=list(k), paths=v) for k,v in aliases.items() if len(v)>1],
                link_count_policy='Record intentional donor hardlink increments from the new builder separately. Bytes, identity, mtime, attributes and allocation must remain unchanged; unplanned link-count differences fail.',
                hash_measurement='Every protected identity read and SHA-256 sealed in this baseline run; aliases retain separate path/metadata rows.',
                original_game_installation_settings_or_user_saves_modified=False, child_processes_started=0)


def measure_storage():
    started = time.monotonic()
    ids, stack, errors, reparse = {}, [PROJECT], [], []
    file_paths = path_bytes = 0
    while stack:
        directory = stack.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    try:
                        value = os.stat(entry.path, follow_symlinks=False)
                        if value.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
                            reparse.append(entry.path)
                        elif stat.S_ISDIR(value.st_mode):
                            stack.append(Path(entry.path))
                        elif stat.S_ISREG(value.st_mode):
                            assert value.st_dev and value.st_ino, entry.path
                            file_paths += 1
                            path_bytes += value.st_size
                            identity = (value.st_dev, value.st_ino)
                            if identity not in ids:
                                ids[identity] = (value.st_size, allocated(entry.path))
                    except (OSError, AssertionError) as error:
                        errors.append(dict(path=entry.path, error=str(error)))
        except OSError as error:
            errors.append(dict(path=str(directory), error=str(error)))
    assert not errors and not reparse, (errors, reparse)
    return dict(schema='zerosis.exit_host_build.storage_before.v1', status='PASS_TRUE_ID_DEDUPLICATED_STORAGE_BASELINE',
                utc=datetime.now(timezone.utc).isoformat(), scope=str(PROJECT), file_paths=file_paths,
                path_logical_bytes=path_bytes, unique_file_ids=len(ids), hardlink_aliases_deduplicated=file_paths-len(ids),
                unique_logical_bytes=sum(size for size, allocation in ids.values()),
                unique_allocated_bytes=sum(allocation for size, allocation in ids.values()),
                confirmed_disposable_bytes=0, threshold_bytes=THRESHOLD, disposable_threshold_exceeded=False,
                errors=errors, reparse_skipped=reparse, elapsed_seconds=round(time.monotonic()-started,3),
                measurement='os.stat real nonzero file identities; FileStandardInfo.AllocationSize; each identity counted once. Directory allocation excluded.',
                scope_note='Includes all then-existing project files, this new stage, protection_before.json and audit_exit_host_storage.py. storage_before.json is written after the scan and is excluded by timing; later root documentation changes are not included. This is project allocation, not volume free space.',
                source_replacement_released_after_this_receipt=True, child_processes_started=0)


def write_new(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def main():
    protection_path, storage_path = STAGE / 'protection_before.json', STAGE / 'storage_before.json'
    assert not protection_path.exists() and not storage_path.exists(), 'Never overwrite or replay an existing baseline.'
    protection = seal_protection()
    write_new(protection_path, protection)
    print(json.dumps(dict(phase='protection_sealed', paths=protection['protected_paths'], unique_file_ids=protection['unique_file_ids'],
                          path=str(protection_path), sha256=digest(protection_path))), flush=True)
    storage = measure_storage()
    write_new(storage_path, storage)
    print(json.dumps(dict(phase='baseline_complete', storage=storage, protection_sha256=digest(protection_path),
                          storage_sha256=digest(storage_path))), flush=True)


if __name__ == '__main__':
    main()
