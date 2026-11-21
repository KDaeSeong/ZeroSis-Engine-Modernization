"""Plan or retire the exact superseded B5/R4 entries, never a historical closure.

This helper performs no process queries, launches, attribute changes, or retail
access. A plan is single-use, including after a partial failure. Plan creation is
read-only outside its new evidence files. Apply requires the reviewed gzip SHA.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import ctypes
from ctypes import wintypes as W
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

PROJECT = Path(__file__).absolute().parents[4]
STAGE = PROJECT / 'evidence/save_overwrite/linked_candidate'
CLEANUP = STAGE / 'cleanup'
PLAN = CLEANUP / 'plan.json.gz'
RESULT = CLEANUP / 'result.json'
JOURNAL = CLEANUP / 'removed.jsonl'
REVIEW = STAGE / 'retirement_review.json'
B5 = '20261015T134352Z_8bd70cf290e9'
R4 = '20261015T205926Z_208415de0fbc'
B6 = '20261016T110835Z_800f48fd88c0'
R6 = '20261016T111333Z_1c377d9577e6'
B7 = '20261016T122615Z_1af4a5449cf1'
R7 = '20261016T123256Z_fae85fb9fe79'
B3 = '20261014T110906Z_a60e98e7bde6'
R3 = '20261014T114953Z_5248d2dd93bc'
OLD_HOST_SHA = '3e83d2b773d689a8d86674318bf7f76963fc236debbd7f0086046f1d3307766e'
BUILD_SHA = '1c6e4f2640bca96c687fb118e47e48116d8162a48276ccc91405578a40ea170d'
PREPARATION_SHA = '00fff5218541789387ea55d8b43d415ad6fcb6815154c7a0bf973dd2f100453e'
RUN_ID = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}')
SHA = re.compile(r'[0-9a-f]{64}')
OLD_ROOTS = (PROJECT / f'Build/UiWindowHost/{B5}', PROJECT / f'Build/InteractiveGameRuntime/{R4}',
             PROJECT / f'evidence/ui_window_host/{B5}', PROJECT / f'evidence/interactive_game/{R4}')
KEEP = (OLD_ROOTS[2] / 'build_result.json', OLD_ROOTS[3] / 'request.json',
        OLD_ROOTS[0] / 'dependency_discovery/tu_00_host_main/host_main.discover.rsp',
        OLD_ROOTS[0] / 'dependency_discovery/tu_00_host_main/host_main.sourceDependencies.json')
ROLES = (('host_main', 'HostMain'), ('window', 'BitmapWindow'), ('renderer', 'BitmapRenderer'),
         ('world_renderer', 'WorldViewRenderer'), ('terrain_renderer', 'WorldTerrainRenderer'))
# Values verified in Windows SDK 10.0.26100.0 winbase.h and the Microsoft DDI.
DISPOSITION_CLASS = 21
DISPOSITION_FLAGS = 0x01 | 0x02 | 0x04 | 0x10
API_REFERENCE = 'https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntddk/ns-ntddk-_file_disposition_information_ex'
INVALID = ctypes.c_void_p(-1).value
K = ctypes.WinDLL('kernel32', use_last_error=True)
K.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
K.CreateFileW.restype = W.HANDLE
K.CloseHandle.argtypes = [W.HANDLE]
K.CloseHandle.restype = W.BOOL
K.GetFileInformationByHandleEx.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
K.GetFileInformationByHandleEx.restype = W.BOOL
K.GetFileInformationByHandle.argtypes = [W.HANDLE, ctypes.c_void_p]
K.GetFileInformationByHandle.restype = W.BOOL
K.GetFileType.argtypes = [W.HANDLE]
K.GetFileType.restype = W.DWORD
K.GetFinalPathNameByHandleW.argtypes = [W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD]
K.GetFinalPathNameByHandleW.restype = W.DWORD
K.GetCompressedFileSizeW.argtypes = [W.LPCWSTR, ctypes.POINTER(W.DWORD)]
K.GetCompressedFileSizeW.restype = W.DWORD
K.ReadFile.argtypes = [W.HANDLE, ctypes.c_void_p, W.DWORD, ctypes.POINTER(W.DWORD), ctypes.c_void_p]
K.ReadFile.restype = W.BOOL
K.SetFilePointerEx.argtypes = [W.HANDLE, ctypes.c_longlong, ctypes.c_void_p, W.DWORD]
K.SetFilePointerEx.restype = W.BOOL
K.SetFileInformationByHandle.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
K.SetFileInformationByHandle.restype = W.BOOL
K.FindFirstFileNameW.argtypes = [W.LPCWSTR, W.DWORD, ctypes.POINTER(W.DWORD), W.LPWSTR]
K.FindFirstFileNameW.restype = W.HANDLE
K.FindNextFileNameW.argtypes = [W.HANDLE, ctypes.POINTER(W.DWORD), W.LPWSTR]
K.FindNextFileNameW.restype = W.BOOL
K.FindClose.argtypes = [W.HANDLE]
K.GetVolumePathNameW.argtypes = [W.LPCWSTR, W.LPWSTR, W.DWORD]
K.GetVolumePathNameW.restype = W.BOOL


class ByHandle(ctypes.Structure):
    _fields_ = [('attributes', W.DWORD), ('creation', W.FILETIME), ('access', W.FILETIME),
                ('write', W.FILETIME), ('volume', W.DWORD), ('size_high', W.DWORD),
                ('size_low', W.DWORD), ('links', W.DWORD), ('index_high', W.DWORD), ('index_low', W.DWORD)]


class Standard(ctypes.Structure):
    _fields_ = [('allocation', ctypes.c_longlong), ('end', ctypes.c_longlong), ('links', W.DWORD),
                ('delete_pending', ctypes.c_ubyte), ('directory', ctypes.c_ubyte)]


class FileId(ctypes.Structure):
    _fields_ = [('volume', ctypes.c_ulonglong), ('identifier', ctypes.c_ubyte * 16)]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def write_result(value):
    temporary = RESULT.with_name('result.pending.json')
    with temporary.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, RESULT)


def artifact(path):
    path = Path(path)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha}


def boundary(path):
    path = Path(os.path.abspath(path))
    require(path != PROJECT and path.is_relative_to(PROJECT), 'Outside exact project boundary: ' + str(path))
    require(path.resolve(strict=True) == path, 'Resolved path changed: ' + str(path))
    for ancestor in (path, *path.parents):
        require(not ancestor.lstat().st_file_attributes & 0x400, 'Reparse path: ' + str(ancestor))
        if ancestor == PROJECT:
            break
    return path


def ft(value):
    return value.dwHighDateTime << 32 | value.dwLowDateTime


def handle_info(handle):
    base, standard, identity = ByHandle(), Standard(), FileId()
    require(K.GetFileType(handle) == 1, 'Only a disk file is accepted')
    if not K.GetFileInformationByHandle(handle, ctypes.byref(base)):
        raise ctypes.WinError(ctypes.get_last_error())
    for cls, value in ((1, standard), (18, identity)):
        if not K.GetFileInformationByHandleEx(handle, cls, ctypes.byref(value), ctypes.sizeof(value)):
            raise ctypes.WinError(ctypes.get_last_error())
    require(not base.attributes & 0x400 and not standard.delete_pending, 'Reparse or pending deletion')
    require(base.links == standard.links and standard.end == (base.size_high << 32 | base.size_low), 'Inconsistent file information')
    return {'file_id': [identity.volume, bytes(identity.identifier).hex()],
            'ntfs_file_id': {'volume_serial': base.volume, 'index_high': base.index_high, 'index_low': base.index_low},
            'bytes': standard.end, 'filetime_creation': ft(base.creation), 'filetime_last_write': ft(base.write),
            'links': base.links, 'attributes': base.attributes, 'directory': bool(standard.directory),
            'standard_allocation_bytes': standard.allocation}


def open_file(path, deleting=False, retained=False, directory=False):
    path = boundary(path)
    access = 0x80 if directory else 0x80000000 | (0x10000 if deleting else 0)
    # Retained witnesses deny writers while allowing this helper's DELETE access.
    sharing = 3 if directory else (5 if retained else (1 if deleting else 7))
    flags = 0x00200000 | (0x02000000 if directory else 0)
    handle = K.CreateFileW(str(path), access, sharing, None, 3, flags, None)
    if handle == INVALID:
        raise ctypes.WinError(ctypes.get_last_error(), 'Cannot open exact file: ' + str(path))
    try:
        name = ctypes.create_unicode_buffer(32768)
        length = K.GetFinalPathNameByHandleW(handle, name, len(name), 0)
        require(0 < length < len(name), 'Cannot verify opened final path')
        actual = name.value[4:] if name.value.startswith('\\\\?\\') else name.value
        require(key(actual) == key(path), 'Opened handle escaped the exact path: ' + name.value)
        info = handle_info(handle)
        require(info['directory'] == directory, 'Unexpected file/directory kind')
        return handle
    except BaseException:
        K.CloseHandle(handle)
        raise


def hash_handle(handle):
    if not K.SetFilePointerEx(handle, 0, None, 0):
        raise ctypes.WinError(ctypes.get_last_error())
    sha, buffer, count = hashlib.sha256(), ctypes.create_string_buffer(1024 * 1024), W.DWORD()
    while True:
        if not K.ReadFile(handle, buffer, len(buffer), ctypes.byref(count), None):
            raise ctypes.WinError(ctypes.get_last_error())
        if not count.value:
            return sha.hexdigest()
        sha.update(buffer.raw[:count.value])


def compressed(path):
    high = W.DWORD()
    ctypes.set_last_error(0)
    low = K.GetCompressedFileSizeW(str(path), ctypes.byref(high))
    if low == 0xffffffff and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    return high.value << 32 | low


def snapshot(path, cache=None, handle=None):
    path = boundary(path)
    initial = path.lstat()
    require(stat.S_ISREG(initial.st_mode) and initial.st_ino and initial.st_nlink, 'Not an identified ordinary file')
    owned_handle = handle is None
    handle = open_file(path) if owned_handle else handle
    try:
        before = handle_info(handle)
        require(initial.st_dev == before['file_id'][0] and
                initial.st_ino == int.from_bytes(bytes.fromhex(before['file_id'][1]), 'little'),
                'Path and opened handle identities disagree')
        cache_key = (tuple(before['file_id']), before['bytes'], before['filetime_last_write'], before['attributes'])
        if cache is not None and cache_key in cache:
            sha = cache[cache_key]
        else:
            sha = hash_handle(handle)
            if cache is not None:
                cache[cache_key] = sha
        stored = compressed(path)
        require(handle_info(handle) == before, 'Opened file changed while hashing: ' + str(path))
        after = path.lstat()
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_nlink', 'st_file_attributes')
        require(tuple(getattr(initial, f) for f in fields) == tuple(getattr(after, f) for f in fields), 'Named file changed during inventory')
        require(before['bytes'] == after.st_size and before['links'] == after.st_nlink and
                before['attributes'] == after.st_file_attributes and
                before['filetime_last_write'] == after.st_mtime_ns // 100 + 116444736000000000,
                'Path and opened file metadata disagree')
        return {'path': str(path), 'sha256': sha, 'identity': [after.st_dev, after.st_ino],
                'mtime_ns': after.st_mtime_ns, 'get_compressed_file_size_bytes': stored,
                **{name: value for name, value in before.items() if name != 'directory'}}
    finally:
        if owned_handle:
            K.CloseHandle(handle)


def aliases(path):
    path = boundary(path)
    volume = ctypes.create_unicode_buffer(32768)
    if not K.GetVolumePathNameW(str(path), volume, len(volume)):
        raise ctypes.WinError(ctypes.get_last_error())
    require(key(volume.value) == key(path.drive + '\\'), 'Mounted-volume hardlink names need separate review')
    buffer, length = ctypes.create_unicode_buffer(32768), W.DWORD(32768)
    handle = K.FindFirstFileNameW(str(path), 0, ctypes.byref(length), buffer)
    if handle == INVALID:
        raise ctypes.WinError(ctypes.get_last_error())
    result = []
    try:
        while True:
            require(buffer.value.startswith('\\') and not buffer.value.startswith('\\\\'), 'Malformed volume-relative hardlink name')
            result.append(str(Path(path.drive + buffer.value)))
            length.value = len(buffer)
            if not K.FindNextFileNameW(handle, ctypes.byref(length), buffer):
                code = ctypes.get_last_error()
                require(code == 38, 'Hardlink enumeration failed: ' + str(code))
                require(len(result) == len({key(x) for x in result}), 'Duplicate hardlink names')
                return sorted(result, key=key)
    finally:
        K.FindClose(handle)


def inventory(root):
    boundary(root)
    files, directories = [], []
    for parent, names, entries in os.walk(root, followlinks=False):
        path = Path(parent)
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400, 'Unknown/reparse directory')
        directories.append({'path': str(path), 'identity': [info.st_dev, info.st_ino], 'attributes': info.st_file_attributes})
        for name in names:
            child = path / name
            require(not child.lstat().st_file_attributes & 0x400, 'Reparse child directory')
        for name in entries:
            child = boundary(path / name)
            require(stat.S_ISREG(child.lstat().st_mode), 'Unexpected nonregular file')
            files.append(child)
    return sorted(files, key=key), sorted(directories, key=lambda row: key(row['path']))


def typed_rows(value):
    if isinstance(value, dict):
        if isinstance(value.get('path'), str) and SHA.fullmatch(str(value.get('sha256', ''))):
            yield value
        for child in value.values():
            yield from typed_rows(child)
    elif isinstance(value, list):
        for child in value:
            yield from typed_rows(child)


def same_snapshot(actual, expected, removed=0):
    require(actual == {**expected, 'links': expected['links'] - removed}, 'Sealed file changed: ' + expected['path'])


def donor_and_runtime_preflight():
    """Run actual read-only validators with every old-root Path API blocked."""
    sys.path.insert(0, str(PROJECT / 'tools'))
    import run_interactive_game as runner
    import build_ui_window_host as builder
    originals = {name: getattr(Path, name) for name in ('open', 'stat', 'lstat', 'resolve')}
    calls, blocked = Counter(), []
    def wrapper(name):
        def guarded(path, *args, **kwargs):
            absolute = key(path)
            if any(absolute == key(root) or absolute.startswith(key(root) + os.sep) for root in OLD_ROOTS):
                blocked.append({'operation': name, 'path': str(path)})
                raise RuntimeError('Current preflight attempted a retired root')
            calls[name] += 1
            return originals[name](path, *args, **kwargs)
        return guarded
    output = {}
    try:
        for name in originals:
            setattr(Path, name, wrapper(name))
        for build_id, runtime_id in ((B6, R6), (B7, R7)):
            report = PROJECT / f'evidence/ui_window_host/{build_id}/build_result.json'
            validation = runner.check_host_runtime_artifacts(read(report))
            runner.check_artifacts(read(PROJECT / f'evidence/interactive_game/{runtime_id}/request.json'))
            donor = builder.FrozenInputReuse(report, PROJECT / f'Build/UiWindowHost/{build_id}/frozen',
                    PROJECT / 'Build/RetirementReviewNoOutputWasCreated', build_id)
            for (sha, size), path in donor.index.items():
                require(artifact(path)['sha256'] == sha and path.stat().st_size == size, 'Current frozen donor differs')
            donor.verify()
            output[build_id] = {'runtime_id': runtime_id, 'host_runtime_validation': validation,
                                'frozen_index_unique_contents': len(donor.index), 'used_historical_old_paths': False}
    finally:
        for name, original in originals.items():
            setattr(Path, name, original)
    require(not blocked, 'An old path was required')
    return {'status': 'PASS', 'current': output, 'blocked_old_path_attempts': blocked,
            'path_api_call_counts': dict(calls), 'target_directory_created': False}


def allowed_retained_alias(path, immutable_names):
    # Only exact generated Build namespaces may witness shared owned inputs.
    # No path is opened until this textual check excludes user/source paths.
    path = Path(path)
    require(path.is_relative_to(PROJECT / 'Build'), 'Alias outside generated Build; hold for review: ' + str(path))
    parts = path.relative_to(PROJECT / 'Build').parts
    require(not any(x.casefold() in ('sessions', 'saves', 'save', 'userdata') for x in parts), 'Possible user data alias')
    require(path.suffix.casefold() not in ('.zssave', '.civ5save', '.save', '.bak'), 'Possible save alias')
    if parts[0] == 'UiWindowHost':
        require(len(parts) >= 4 and RUN_ID.fullmatch(parts[1]) and parts[2] == 'frozen', 'Unexpected frozen alias')
    elif parts[0] == 'RuntimeInputCache':
        require(len(parts) == 3 and SHA.fullmatch(parts[2]) and parts[1] == parts[2][:2], 'Unknown cache alias')
    elif parts[0] in ('InteractiveGameRuntime', 'TradeRouteFixtureRuntime'):
        require(len(parts) == 3 and RUN_ID.fullmatch(parts[1]) and parts[2] in immutable_names, 'Unknown runtime alias')
    elif parts[0] == 'terrain_renderer_validation':
        require(len(parts) >= 3 and path.name in immutable_names, 'Unknown provider fixture alias')
    else:
        raise RuntimeError('Unknown generated alias; hold for review: ' + str(path))


def prepare_plan():
    require(not any(path.exists() for path in (PLAN, RESULT, JOURNAL, REVIEW)), 'Inspect an existing plan; never silently replan')
    build_path = PROJECT / f'evidence/ui_window_host/{B7}/build_result.json'
    attestation_path = STAGE / f'attestation_{B7}.json'
    preparation_path = STAGE / 'preparation_identity_audit.json'
    require(artifact(build_path)['sha256'] == BUILD_SHA and artifact(preparation_path)['sha256'] == PREPARATION_SHA,
            'Reviewed B7/R7 receipts changed')
    build, prepared, scope, attestation = read(build_path), read(STAGE / 'prepared.json'), read(STAGE / 'scope.json'), read(attestation_path)
    require(build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and attestation['status'] == 'PASS' and
            prepared['status'] == 'PREPARED_NOT_EXECUTED' and prepared['run_id'] == R7 and prepared['host_build_id'] == B7,
            'Current compile/link/PE/private-preparation gate failed')
    require(attestation['build_report']['sha256'] == BUILD_SHA and
            artifact(build['executable']['path'])['sha256'] == attestation['executable']['sha256'], 'PE attestation mismatch')
    preflight = donor_and_runtime_preflight()
    old_build, old_request = read(KEEP[0]), read(KEEP[1])
    require(old_request['smoke'] is False, 'Old runtime was executed or changed')
    old_refs = {}
    for document in (old_build, old_request):
        for row in typed_rows(document):
            if any(Path(row['path']).is_relative_to(root) for root in OLD_ROOTS):
                old_refs.setdefault(key(row['path']), row['sha256'])
                require(old_refs[key(row['path'])] == row['sha256'], 'Conflicting historical artifact hashes')
    declared_inputs = {row['sha256'] for row in typed_rows(old_build)}
    generated_unreported = {key(OLD_ROOTS[0] / name) for name in
        ('read_build_environment.cmd', 'final/ZeroSisHost_x64.exp', 'final/ZeroSisHost_x64.lib')}
    cache, selected, old_inventory, directories, additional_replacements = {}, [], [], [], []
    keep_keys = {key(path) for path in KEEP}
    for root in OLD_ROOTS:
        root_files, root_directories = inventory(root)
        directories.extend(root_directories)
        require(not (root / 'sessions').exists(), 'Old runtime sessions must never be retired')
        for path in root_files:
            require(path.suffix.casefold() not in ('.zssave', '.civ5save', '.save', '.bak'), 'Possible user save in old root')
            row = snapshot(path, cache)
            old_inventory.append(row)
            if key(path) in keep_keys:
                continue
            if key(path) in old_refs:
                require(row['sha256'] == old_refs[key(path)], 'Old owned artifact differs from its receipt: ' + str(path))
                reason = 'superseded_attested_owned_artifact'
            elif key(path) in generated_unreported:
                reason = 'superseded_generated_environment_or_link_side_output'
            elif path.is_relative_to(OLD_ROOTS[0] / 'frozen/project') and row['sha256'] in declared_inputs:
                reason = 'superseded_frozen_project_duplicate_of_attested_input'
            elif path.is_relative_to(OLD_ROOTS[0] / 'frozen/project/tools'):
                replacement = PROJECT / f'Build/UiWindowHost/{B6}/frozen/project/tools' / path.name
                if snapshot(replacement, cache)['sha256'] != row['sha256']:
                    replacement = PROJECT / 'evidence/save_delete/source_contract/source_before' / ('tools__' + path.name + '.txt')
                require(snapshot(replacement, cache)['sha256'] == row['sha256'], 'Unique frozen tool must be retained')
                additional_replacements.append(str(replacement))
                reason = 'superseded_frozen_tool_exact_duplicate_of_retained_current_or_changed_file_backup'
            else:
                raise RuntimeError('Unmapped or unique old file must be held: ' + str(path))
            selected.append({**row, 'reason': reason})
    require(len(old_inventory) == 707 and len(selected) == 703, 'Old exact inventory changed; review unknown additions')
    # Old Python copies must have identical retained current copies.
    python_duplicates = []
    for row in old_inventory:
        path = Path(row['path'])
        if path.is_relative_to(OLD_ROOTS[3]) and path.suffix == '.py':
            replacement = PROJECT / f'evidence/interactive_game/{R6}' / path.relative_to(OLD_ROOTS[3])
            require(artifact(replacement)['sha256'] == row['sha256'], 'Unique historical Python source requires retention')
            python_duplicates.append(str(replacement))
    require(len(python_duplicates) == 11, 'Unexpected frozen Python inventory')
    # Retain the already-existing changed handwritten sources, not full copies.
    variants = {
        'UiPopupContext.h': 'b824147111989365fa0863914b2f3ed734f015b4161558c2aca06e6eddc7b5ba',
        'UiSaveMenuContract.h': '121ef54dd249dc0103d1f5da759f63be429288ba3598d1e44d9a31caed4434d1',
        'UiLoadMenuContract.h': '1b267f2206493c6a07f14079121f4536fe0a6e6f5bcd9eef67a29cfe6a8654c0',
        'InteractiveGameSession.h': '26a605fd14ec5b2883add057c55cce6fddc0480602fff713ebd10e5fb99d8b61',
        'NativeSaveCatalog.h': '9f1a3245c78645d31917944d2c6b9ad5de0a701e23876eb44104f96671d74f95',
        'UiScene.lua': '7c445d81244a1106b4145dfc149a09513578201f6e7ba279d652702b1c9e701c'}
    source_backups = []
    for name, sha in variants.items():
        path = PROJECT / 'evidence/save_delete/source_contract/source_before' / ('Source__Host__' + name + '.txt')
        require(artifact(path)['sha256'] == sha, 'Unique old source backup differs')
        source_backups.append(str(path))
    current_reports = [PROJECT / f'evidence/ui_window_host/{value}/build_result.json' for value in (B3, B6, B7, '20261011T124501Z_5bf7bf678d40')]
    current_reports += [PROJECT / f'evidence/interactive_game/{value}/request.json' for value in (R3, R6, R7, '20261012T121847Z_732a6d5f07ea')]
    current_reports += [PROJECT / 'Play/EarlyAccess/release.json']
    require(all(path.is_file() for path in current_reports), 'A retained current/recovery receipt is missing')
    cache_entries = [row for row in old_request['materializations'] if row.get('sha256') == OLD_HOST_SHA]
    require(len(cache_entries) == 1, 'Old Host cache ownership is ambiguous')
    entry = cache_entries[0]
    old_cache = PROJECT / f'Build/RuntimeInputCache/{OLD_HOST_SHA[:2]}/{OLD_HOST_SHA}'
    require(key(entry['cache']) == key(old_cache) and key(entry['target']) == key(OLD_ROOTS[1] / 'ZeroSisHost_x64.exe') and
            entry['materialization_method'] == 'hardlink', 'Unexpected old Host cache mapping')
    reference_hits = [str(path) for path in current_reports if OLD_HOST_SHA in path.read_text(encoding='utf-8-sig')]
    cache_aliases = aliases(old_cache)
    cache_scope = {'path': str(old_cache), 'sha256': OLD_HOST_SHA, 'current_report_hash_reference_hits': reference_hits,
                   'exact_link_names': cache_aliases, 'included': False}
    if not reference_hits and {key(x) for x in cache_aliases} == {key(old_cache), key(entry['target'])}:
        row = snapshot(old_cache, cache)
        require(row['sha256'] == OLD_HOST_SHA and row['links'] == 2 and row['attributes'] & 1, 'Old Host-only cache changed')
        selected.append({**row, 'reason': 'superseded_B5_Host_cache_with_only_R4_link_and_no_current_reference'})
        cache_scope['included'] = True
    # New compiler objects are exact outputs of the completed link/PE run.
    host_root = PROJECT / f'Build/UiWindowHost/{B7}'
    discovery = [row for tu in build['dependency_discovery']['translation_units'] for row in tu['objects']]
    require(len(discovery) == 5, 'Expected exactly five discovery objects')
    for row in discovery:
        path = Path(row['path'])
        require(path.is_relative_to(host_root / 'dependency_discovery') and path.suffix.lower() == '.obj', 'Unexpected discovery object')
        current = snapshot(path, cache)
        require(current['sha256'] == row['sha256'], 'Discovery object differs from successful actual build')
        selected.append({**current, 'reason': 'B7_completed_discovery_object'})
    link_text = Path(build['link_response']['path']).read_text(encoding='utf8')
    for index, (role, name) in enumerate(ROLES):
        path = host_root / f'final/tu_{index:02d}_{role}/obj/{name}.obj'
        require(str(path) in link_text, 'Completed final object was not linked')
        selected.append({**snapshot(path, cache), 'reason': 'B7_completed_final_object'})
    require(len(selected) == 713 + int(cache_scope['included']) and len({key(row['path']) for row in selected}) == len(selected), 'Unexpected or duplicate exact candidate set')
    selected_keys = {key(row['path']) for row in selected}
    protected_paths = set(str(path) for path in KEEP) | set(source_backups) | set(python_duplicates) | set(additional_replacements)
    protected_paths.update(row['path'] for row in scope['protected_artifacts'].values())
    protected_paths.update(str(path) for path in current_reports)
    protected_paths.update(str(path) for path in (Path(__file__).absolute(), STAGE / 'scope.json', STAGE / 'prepared.json',
        attestation_path, preparation_path, build_path, PROJECT / 'Source/Host/UiPopupAssets.generated.h'))
    for report_path in current_reports:
        for row in typed_rows(read(report_path)):
            path = Path(row['path'])
            if path.is_relative_to(PROJECT) and path.is_file() and key(path) not in selected_keys:
                # Historical provenance strings are deliberately not followed.
                protected_paths.add(str(path))
    require(not selected_keys.intersection(key(path) for path in protected_paths), 'Candidate is also a named protected path')
    immutable_names = {Path(row['path']).name for row in old_request['runtime_inputs'] if Path(row['path']).suffix.lower() != '.db'}
    groups = defaultdict(list)
    for row in selected:
        groups[tuple(row['file_id'])].append(row)
    group_rows = []
    for identity, targets in sorted(groups.items(), key=lambda item: key(item[1][0]['path'])):
        representative = targets[0]
        names = aliases(representative['path'])
        require(len(names) == representative['links'], 'Hardlink count changed during planning')
        target_names = {key(row['path']) for row in targets}
        require(target_names.issubset({key(name) for name in names}), 'Candidate name missing from link enumeration')
        retained_names = [name for name in names if key(name) not in selected_keys]
        for name in retained_names:
            allowed_retained_alias(name, immutable_names)
            protected_paths.add(name)
            retained = snapshot(name, cache)
            require(retained['file_id'] == representative['file_id'] and retained['sha256'] == representative['sha256'], 'Retained hardlink witness differs')
        require(len(targets) + len(retained_names) == len(names), 'Unaccounted candidate alias')
        group_rows.append({'file_id': list(identity), 'initial_links': representative['links'],
            'initial_link_names': names, 'target_names': [row['path'] for row in targets], 'retained_names': retained_names,
            'all_named_links_retired': not retained_names, 'logical_content_bytes': representative['bytes'],
            'standard_allocation_reclaim_bytes': representative['standard_allocation_bytes'] if not retained_names else 0,
            'get_compressed_reclaim_bytes': representative['get_compressed_file_size_bytes'] if not retained_names else 0})
    protected = [snapshot(path, cache) for path in sorted(protected_paths, key=key)]
    # The data and readonly policies of every current shared witness are sealed;
    # only an explicitly counted reduction in hardlink count is permitted.
    totals = {'files': len(selected), 'old_B5_R4_files': 703, 'B7_objects': 10,
        'old_Host_only_cache_files': int(cache_scope['included']), 'logical_path_bytes': sum(row['bytes'] for row in selected),
        'unique_target_file_ids': len(groups), 'unique_ids_with_all_named_links_retired': sum(group['all_named_links_retired'] for group in group_rows),
        'expected_unique_standard_allocation_reclaim_bytes': sum(group['standard_allocation_reclaim_bytes'] for group in group_rows),
        'expected_unique_GetCompressedFileSizeW_reclaim_bytes': sum(group['get_compressed_reclaim_bytes'] for group in group_rows),
        'protected_paths': len(protected), 'retained_old_metadata_files': len(KEEP)}
    review = {'schema': 'zerosis.owned_save_overwrite.retirement_review.v1', 'utc': datetime.now(timezone.utc).isoformat(),
        'status': 'EXACT_CANDIDATES_REVIEWED_NOT_APPLIED', 'current': {'build_id': B7, 'runtime_id': R7, 'prior_build_id': B6, 'prior_runtime_id': R6},
        'build': artifact(build_path), 'attestation': artifact(attestation_path), 'prepared': artifact(STAGE / 'prepared.json'),
        'current_dependency_preflight': preflight, 'four_small_old_files_retained': [artifact(path) for path in KEEP],
        'unique_old_handwritten_source_backups_retained': [artifact(path) for path in source_backups],
        'old_python_copies_match_retained_R6': python_duplicates, 'old_tool_copies_match_retained_B6': additional_replacements,
        'old_runtime_file_count': 34, 'old_runtime_sessions_or_saves': [],
        'old_runtime_inputs_and_launchers_hash_match_request': True, 'old_host_only_cache': cache_scope,
        'dependency_classification': {'B6_B7_donor_history': 'reused_from_path and donor_report_path are provenance strings, not paths opened by current preflight or FrozenInputReuse.',
            'runtime_requests': 'R6/R7 typed artifact paths require their own runtime/cache/current frozen inputs; no retired B5/R4 paths were opened.',
            'active_small_syntax_baseline': 'Tests/load_menu_host_syntax.py defaults to B5 and consumes only the retained response and dependency JSON.',
            'historical_receipts': 'Historical B5/N reports remain unchanged; their full old artifact closures will no longer replay after this exact retirement.',
            'old_unique_generated_files': 'Obsolete UiPopupAssets.generated.h and prepared.json are generated artifacts; six changed handwritten source versions already survive in source_before.'},
        'totals': totals, 'deletion_api': {'reference': API_REFERENCE, 'class': DISPOSITION_CLASS, 'flags': DISPOSITION_FLAGS,
            'flags_hex': '0x17', 'attribute_changes': False, 'same_handle_hash_identity_validation': True, 'mapped_image_refusal': True},
        'retail_mods_saves_settings_or_processes_accessed': False, 'host_gamecore_hwnd_executed': False,
        'limits': ['Expected unique named-file allocation is not measured free disk space; open handles can retain unlinked data.',
            'No live native/gameplay proof is added. An apply error is partial, fail closed, and never replayed.',
            'Current and prior runtime, default EA0.6, B3/R3 recovery, mutable Source, proofs and all other cache entries remain protected.']}
    write_new(REVIEW, review)
    payload = {'schema': 'zerosis.owned_save_overwrite.exact_superseded_cleanup.v1', 'utc': datetime.now(timezone.utc).isoformat(),
        'review': artifact(REVIEW), 'helper': artifact(Path(__file__).absolute()), 'files': selected, 'protected': protected,
        'hardlink_groups': group_rows, 'old_root_inventory': old_inventory, 'old_roots': [str(path) for path in OLD_ROOTS],
        'old_directories': directories, 'keep_old_paths': [str(path) for path in KEEP], 'totals': totals,
        'current_build_id': B7, 'current_runtime_id': R7, 'old_host_only_cache': cache_scope,
        'allowed_disposition_class': DISPOSITION_CLASS, 'allowed_disposition_flags': DISPOSITION_FLAGS,
        'no_process_queries_or_retail_access': True, 'historical_reports_unchanged': True,
        'shared_alias_guard': 'Exact path and identity/hash/size/time/attributes preserved; nlink may decline only by this plan removed entries for that same file ID.'}
    with PLAN.open('xb') as stream:
        stream.write(gzip.compress((json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf8'), mtime=0))
        stream.flush()
        os.fsync(stream.fileno())
    summary = {'status': 'PLANNED_NOT_APPLIED', 'plan': artifact(PLAN), 'review': artifact(REVIEW), 'totals': totals}
    write_new(CLEANUP / 'plan_summary.json', summary)
    write_new(STAGE / 'retirement_preflight.json', {
        'schema': 'zerosis.owned_save_overwrite.exact_retirement_preflight.v1',
        'status': 'REVIEWED_NOT_APPLIED', 'utc': datetime.now(timezone.utc).isoformat(),
        'review': artifact(REVIEW), 'plan': artifact(PLAN), 'helper': artifact(Path(__file__).absolute()),
        'totals': totals, 'protected_B5_R4_paths': [artifact(path) for path in KEEP],
        'current_build_id': B7, 'current_runtime_id': R7,
        'historical_reports_and_plans_modified': False, 'applied': False,
        'retail_mods_saves_settings_or_processes_accessed': False, 'host_gamecore_hwnd_executed': False})
    print(json.dumps(summary, ensure_ascii=False))


def row_snapshot(row):
    return {name: value for name, value in row.items() if name != 'reason'}


def validate_plan_shape(payload):
    require(payload['schema'] == 'zerosis.owned_save_overwrite.exact_superseded_cleanup.v1' and
            payload['current_build_id'] == B7 and payload['current_runtime_id'] == R7 and
            payload['allowed_disposition_class'] == DISPOSITION_CLASS and payload['allowed_disposition_flags'] == DISPOSITION_FLAGS,
            'Unsupported cleanup plan')
    require(artifact(Path(__file__).absolute()) == payload['helper'] and artifact(REVIEW) == payload['review'], 'Helper/review changed after exact plan')
    require(payload['old_roots'] == [str(path) for path in OLD_ROOTS] and payload['keep_old_paths'] == [str(path) for path in KEEP], 'Old root/retention policy differs')
    files = payload['files']
    require(len(files) == payload['totals']['files'] and len({key(row['path']) for row in files}) == len(files), 'Duplicate/invalid exact set')
    objects = set()
    for index, (role, name) in enumerate(ROLES):
        for phase in ('dependency_discovery', 'final'):
            objects.add(key(PROJECT / f'Build/UiWindowHost/{B7}/{phase}/tu_{index:02d}_{role}/obj/{name}.obj'))
    cache_key = key(PROJECT / f'Build/RuntimeInputCache/{OLD_HOST_SHA[:2]}/{OLD_HOST_SHA}')
    for row in files:
        path = Path(row['path'])
        allowed = any(path.is_relative_to(root) for root in OLD_ROOTS) or key(path) in objects or (
            key(path) == cache_key and payload['old_host_only_cache']['included'] and row['sha256'] == OLD_HOST_SHA)
        require(allowed and key(path) not in {key(x) for x in KEEP}, 'Plan contains an unknown/protected path')
        require(SHA.fullmatch(row['sha256']) and row['links'] >= 1, 'Invalid exact artifact row')
    require(objects.issubset({key(row['path']) for row in files}), 'Plan omitted a required current object')
    require(not {key(row['path']) for row in files}.intersection(key(row['path']) for row in payload['protected']), 'Protected exact path selected')


def apply(expected_sha):
    require(expected_sha and SHA.fullmatch(expected_sha) and artifact(PLAN)['sha256'] == expected_sha, 'Exact reviewed plan SHA is required')
    require(not RESULT.exists() and not JOURNAL.exists() and not RESULT.with_name('result.pending.json').exists(),
            'Never replay a completed or partially started cleanup plan')
    raw = gzip.decompress(PLAN.read_bytes())
    require(len(raw) < 32 * 1024 * 1024, 'Oversized exact plan')
    payload = json.loads(raw)
    validate_plan_shape(payload)
    files, protected = payload['files'], payload['protected']
    removed_by_id, removed_names = Counter(), set()
    cache, held, directory_handles = {}, {}, []
    record = {'status': 'PRECHECK', 'plan': artifact(PLAN), 'removed_files': 0, 'removed_logical_bytes': 0,
        'removed_standard_allocation_bytes': 0, 'removed_get_compressed_file_size_bytes': 0,
        'removed_path_standard_allocation_bytes': 0, 'removed_path_get_compressed_file_size_bytes': 0,
        'protected_unchanged': False, 'attributes_changed': False, 'shared_identity_link_counts_verified': False,
        'retail_mods_user_saves_settings_or_processes_accessed': False, 'host_gamecore_hwnd_executed': False,
        'limits': 'Unique allocation counts each identity once only after all its inventoried named links were removed; not measured volume free space.'}
    started = False
    try:
        ancestors = set()
        for row in [*files, *protected]:
            parent = Path(row['path']).parent
            while parent != PROJECT:
                require(parent.is_relative_to(PROJECT), 'Ancestor escaped exact project')
                ancestors.add(parent)
                parent = parent.parent
        # Pin generated namespaces against rename/reparse swaps during unlink.
        for path in [PROJECT, *sorted(ancestors, key=lambda p: (len(p.parts), key(p)))]:
            if path == PROJECT:
                require(not path.lstat().st_file_attributes & 0x400, 'Project became a reparse point')
                handle = K.CreateFileW(str(path), 0x80, 3, None, 3, 0x02200000, None)
                require(handle != INVALID and handle_info(handle)['directory'], 'Cannot pin exact project directory')
            else:
                handle = open_file(path, directory=True)
            directory_handles.append(handle)
        # Every candidate alias and protected witness is checked before mutation.
        for row in protected:
            identity = tuple(row['file_id'])
            if identity not in held:
                held[identity] = open_file(row['path'], retained=True)
                same_snapshot(snapshot(row['path'], handle=held[identity]), row)
            else:
                same_snapshot(snapshot(row['path'], cache), row)
        for row in files:
            same_snapshot(snapshot(row['path'], cache), row_snapshot(row))
        for group in payload['hardlink_groups']:
            require([key(name) for name in aliases(group['target_names'][0])] == [key(name) for name in group['initial_link_names']], 'Hardlink namespace changed after plan')
        for root in OLD_ROOTS:
            actual_files, actual_directories = inventory(root)
            expected = [row for row in payload['old_root_inventory'] if Path(row['path']).is_relative_to(root)]
            require({key(path) for path in actual_files} == {key(row['path']) for row in expected}, 'Unknown old-root file appeared; nothing retired')
            planned_dirs = [row for row in payload['old_directories'] if Path(row['path']).is_relative_to(root)]
            require(actual_directories == planned_dirs, 'Old directory namespace changed after plan')
        write_new(RESULT, record)
        started = True
        record['status'] = 'IN_PROGRESS'
        write_result(record)
        groups = {tuple(row['file_id']): row for row in payload['hardlink_groups']}
        # Executable and DLL entries (including the Host cache alias) go first.
        def order(row):
            suffix = Path(row['path']).suffix.lower()
            return (0 if suffix == '.exe' or row['sha256'] == OLD_HOST_SHA else (1 if suffix == '.dll' else 2), key(row['path']))
        with JOURNAL.open('x', encoding='utf8', newline='\n') as journal:
            for index, row in enumerate(sorted(files, key=order)):
                identity = tuple(row['file_id'])
                before_removed = removed_by_id[identity]
                handle = open_file(row['path'], deleting=True)
                accepted = False
                try:
                    same_snapshot(snapshot(row['path'], handle=handle), row_snapshot(row), before_removed)
                    expected_names = [name for name in groups[identity]['initial_link_names'] if key(name) not in removed_names]
                    require([key(name) for name in aliases(row['path'])] == [key(name) for name in expected_names], 'Hardlink names changed immediately before same-handle unlink')
                    flags = W.DWORD(DISPOSITION_FLAGS)
                    if not K.SetFileInformationByHandle(handle, DISPOSITION_CLASS, ctypes.byref(flags), ctypes.sizeof(flags)):
                        raise ctypes.WinError(ctypes.get_last_error(), 'Exact unlink refused; mapped image or sharing/permission state must be reviewed: ' + row['path'])
                    accepted = True
                finally:
                    require(K.CloseHandle(handle), 'Cannot close exact deletion handle')
                require(accepted and not os.path.lexists(row['path']), 'Unlink accepted but named path is not absent')
                removed_names.add(key(row['path']))
                removed_by_id[identity] += 1
                record['removed_files'] += 1
                record['removed_logical_bytes'] += row['bytes']
                record['removed_path_standard_allocation_bytes'] += row['standard_allocation_bytes']
                record['removed_path_get_compressed_file_size_bytes'] += row['get_compressed_file_size_bytes']
                group = groups[identity]
                if removed_by_id[identity] == group['initial_links']:
                    require(group['all_named_links_retired'], 'Protected named link was counted as reclaimed')
                    record['removed_standard_allocation_bytes'] += group['standard_allocation_reclaim_bytes']
                    record['removed_get_compressed_file_size_bytes'] += group['get_compressed_reclaim_bytes']
                receipt = {'sequence': index, 'path': row['path'], 'sha256': row['sha256'], 'bytes': row['bytes'],
                    'file_id': row['file_id'], 'previous_links': row['links'] - before_removed,
                    'expected_remaining_named_links': row['links'] - before_removed - 1,
                    'disposition_flags': DISPOSITION_FLAGS, 'attributes_changed': False, 'result': 'REMOVED_ABSENT'}
                journal.write(json.dumps(receipt, ensure_ascii=False, separators=(',', ':')) + '\n')
                journal.flush()
                os.fsync(journal.fileno())
                write_result(record)
        # No remaining protected bytes, identity, timestamp or readonly policy may drift.
        final_cache = {}
        for row in protected:
            same_snapshot(snapshot(row['path'], final_cache), row, removed_by_id[tuple(row['file_id'])])
        for group in payload['hardlink_groups']:
            expected = [name for name in group['initial_link_names'] if key(name) not in removed_names]
            require(removed_by_id[tuple(group['file_id'])] == len(group['target_names']), 'Not all exact names were removed')
            if expected:
                require([key(name) for name in aliases(expected[0])] == [key(name) for name in expected], 'Retained hardlink namespace differs after unlink')
        for root in OLD_ROOTS:
            actual_files, _ = inventory(root)
            require({key(path) for path in actual_files} == {key(path) for path in KEEP if path.is_relative_to(root)}, 'Unknown old-root file appeared during cleanup')
        require(all(not os.path.lexists(row['path']) for row in files), 'A removed name reappeared')
        record.update(status='COMPLETE', protected_unchanged=True, targets_absent=True,
            shared_identity_link_counts_verified=True, protected_paths_verified=len(protected),
            unique_shared_groups_verified=len(payload['hardlink_groups']), journal=artifact(JOURNAL))
    except BaseException as error:
        if started:
            record.update(status='PARTIAL_DO_NOT_REPLAY', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        for handle in held.values():
            K.CloseHandle(handle)
        for handle in reversed(directory_handles):
            K.CloseHandle(handle)
        if started:
            write_result(record)
    # Only known, empty directories are retired after namespace pins are closed.
    # Any nonempty/changed directory is preserved, never recursively removed.
    empty_removed, preserved = [], []
    for row in sorted(payload['old_directories'], key=lambda value: (-len(Path(value['path']).parts), key(value['path']))):
        path = Path(row['path'])
        if any(Path(kept).is_relative_to(path) for kept in KEEP):
            continue
        boundary(path)
        info = path.lstat()
        require([info.st_dev, info.st_ino] == row['identity'] and info.st_file_attributes == row['attributes'], 'Empty directory identity changed')
        try:
            path.rmdir()
            empty_removed.append(str(path))
        except OSError as error:
            preserved.append({'path': str(path), 'reason': str(error)})
    record['empty_directories_removed'] = empty_removed
    record['empty_directories_preserved'] = preserved
    write_result(record)
    print(json.dumps({**record, 'result': artifact(RESULT)}, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'apply'))
    parser.add_argument('--plan-sha256')
    arguments = parser.parse_args()
    prepare_plan() if arguments.action == 'plan' else apply(arguments.plan_sha256)
