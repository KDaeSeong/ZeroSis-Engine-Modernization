"""Apply only this sealed retirement plan; never recursively delete an open-ended tree."""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes as W
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import uuid

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
K = ctypes.WinDLL('kernel32', use_last_error=True)

class FILEINFO(ctypes.Structure):
    _fields_ = [('attributes', W.DWORD), ('created', W.FILETIME), ('accessed', W.FILETIME),
                ('written', W.FILETIME), ('volume', W.DWORD), ('sizehi', W.DWORD),
                ('sizelo', W.DWORD), ('links', W.DWORD), ('indexhi', W.DWORD), ('indexlo', W.DWORD)]

K.CreateFileW.argtypes = [W.LPCWSTR, W.DWORD, W.DWORD, ctypes.c_void_p, W.DWORD, W.DWORD, W.HANDLE]
K.CreateFileW.restype = W.HANDLE
K.GetFileInformationByHandle.argtypes = [W.HANDLE, ctypes.POINTER(FILEINFO)]
K.GetFileInformationByHandle.restype = W.BOOL
K.SetFileInformationByHandle.argtypes = [W.HANDLE, ctypes.c_int, ctypes.c_void_p, W.DWORD]
K.SetFileInformationByHandle.restype = W.BOOL
K.CloseHandle.argtypes = [W.HANDLE]
K.CloseHandle.restype = W.BOOL

def require(value, message):
    if not value:
        raise ValueError(message)

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def timestamp():
    return datetime.now(timezone.utc).isoformat()

def atomic_json(path, value):
    temp = path.with_name(path.name + '.tmp')
    with temp.open('w', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temp, path)

def utc_ticks(text):
    require(text.endswith('Z'), 'Manifest timestamp is not UTC')
    moment = datetime.strptime(text[:19], '%Y-%m-%dT%H:%M:%S')
    fraction = text[19:-1]
    require(not fraction or (fraction.startswith('.') and fraction[1:].isdigit()), 'Invalid manifest fraction')
    delta = moment - datetime(1601, 1, 1)
    return (delta.days * 86400 + delta.seconds) * 10_000_000 + int((fraction[1:] + '0000000')[:7])

def absolute(path):
    value = Path(path)
    require(value.is_absolute(), 'Manifest path is not absolute: ' + str(path))
    require('..' not in value.parts, 'Manifest contains parent traversal')
    return Path(os.path.abspath(value))

def safe_chain(path, ancestor_cache=None):
    path = absolute(path)
    require(path.is_relative_to(ROOT), 'Path escaped the exact project: ' + str(path))
    checked_directories = []
    for node in [path, *path.parents]:
        if node != path and ancestor_cache is not None and node in ancestor_cache:
            ancestor_cache.update(checked_directories)
            return path
        attributes = os.lstat(node).st_file_attributes
        require(not attributes & 0x400, 'Reparse point: ' + str(node))
        if attributes & 0x10:
            checked_directories.append(node)
        if node == ROOT:
            if ancestor_cache is not None:
                ancestor_cache.update(checked_directories)
            return path
    raise ValueError('Project boundary is absent')

def open_handle(path, access=0, sharing=7):
    handle = K.CreateFileW(str(path), access, sharing, None, 3, 0x02200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    return handle

def handle_info(handle):
    value = FILEINFO()
    if not K.GetFileInformationByHandle(handle, ctypes.byref(value)):
        raise ctypes.WinError(ctypes.get_last_error())
    return {'file_id': f'{value.volume:08X}:{value.indexhi:08X}{value.indexlo:08X}',
            'size': (value.sizehi << 32) | value.sizelo,
            'ticks': (value.written.dwHighDateTime << 32) | value.written.dwLowDateTime,
            'attributes': value.attributes, 'links': value.links}

def file_info(path):
    handle = open_handle(path)
    try:
        return handle_info(handle)
    finally:
        K.CloseHandle(handle)

def verify(row, *, content=True, directory=False, directory_mtime=True, initial_links=False, read_cache=None):
    # Only read-only sweeps share checked ancestors. Each actual unlink and
    # directory removal still rechecks the complete ancestry without a cache.
    path = safe_chain(row['path'], ancestor_cache=read_cache)
    meta = file_info(path)
    require(bool(meta['attributes'] & 0x10) == directory, 'File/directory type differs: ' + str(path))
    require(meta['file_id'] == row['file_id'], 'File identity changed: ' + str(path))
    require(meta['attributes'] == int(row['attributes']), 'File attributes changed: ' + str(path))
    if initial_links and 'hardlink_count' in row:
        require(meta['links'] == int(row['hardlink_count']), 'Initial hardlink count changed: ' + str(path))
    if not directory or directory_mtime:
        require(meta['ticks'] == utc_ticks(row['mtime_utc']), 'File timestamp changed: ' + str(path))
    if not directory:
        require(meta['size'] == int(row['size']), 'File length changed: ' + str(path))
        if content:
            require(sha(path) == row['sha256'], 'File content changed: ' + str(path))
            after = file_info(path)
            require(all(after[k] == meta[k] for k in ('file_id', 'size', 'ticks', 'attributes')),
                    'File mutated while hashing: ' + str(path))
    return path

def unlink(path, expected=None):
    # Delete exactly one directory entry. IGNORE_READONLY avoids changing the
    # shared attributes of surviving immutable cache hardlinks.
    handle = open_handle(path, 0x10000, sharing=5)
    try:
        current = handle_info(handle)
        require(not current['attributes'] & (0x400 | 0x10), 'Unlink handle is not a regular file')
        if expected is not None:
            require(current['file_id'] == expected['file_id'] and current['size'] == int(expected['size']) and
                    current['ticks'] == utc_ticks(expected['mtime_utc']) and
                    current['attributes'] == int(expected['attributes']),
                    'Deletion handle no longer identifies its verified target: ' + str(path))
            if 'expected_remaining_links' in expected:
                require(current['links'] == expected['expected_remaining_links'], 'Live hardlink count changed before unlink')
        flags = W.DWORD(0x13)  # DELETE | POSIX_SEMANTICS | IGNORE_READONLY_ATTRIBUTE
        if not K.SetFileInformationByHandle(handle, 21, ctypes.byref(flags), ctypes.sizeof(flags)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        K.CloseHandle(handle)
    require(not path.exists(), 'Native unlink left its target: ' + str(path))

def self_check():
    directory = HERE / ('unlink-check-' + uuid.uuid4().hex)
    directory.mkdir()
    original, alias = directory / 'original.bin', directory / 'alias.bin'
    original.write_bytes(b'bounded-readonly-hardlink-check')
    os.link(original, alias)
    os.chmod(original, stat.S_IREAD)
    before, digest = file_info(original), sha(original)
    unlink(safe_chain(alias))
    after = file_info(original)
    require(all(before[k] == after[k] for k in ('file_id', 'size', 'ticks', 'attributes')) and sha(original) == digest,
            'Readonly hardlink survivor changed in native self-check')
    unlink(safe_chain(original))
    directory.rmdir()

def expected_targets():
    groups = {
        ('Build/UiWindowHost', 'evidence/ui_window_host'): [
            '20261008T115702Z_523eb1f915f7','20261008T120709Z_c737cd93492c','20261008T121532Z_24c429e9471c',
            '20261008T122918Z_53fb8e56e828','20261008T124658Z_e60128cb38e9','20261008T130412Z_3af27daab86b',
            '20261008T134026Z_23f553b03f27','20261008T134854Z_356cd1d99f4f','20261008T135242Z_16cf2c83686e',
            '20261005T124208Z_65c9f8ce7280'],
        ('Build/InteractiveGameRuntime', 'evidence/interactive_game'): [
            '20261008T115935Z_1dd44881d206','20261008T121002Z_4d405b3116b4','20261008T121756Z_99e3474b81cb',
            '20261008T123223Z_1146c1ab118c','20261008T123912Z_e66964a29ab4','20261008T125043Z_fbc4deb89adb',
            '20261008T131315Z_92ba52e42080','20261006T132933Z_c6976cdbae5b','20261006T133311Z_b83e6f290c55',
            '20261005T124511Z_ad7083cc8304','20261005T125355Z_d882b8fab075'],
        ('Build/TradeRouteFixtureRuntime', 'evidence/trade_route_fixture'): [
            '20261008T134307Z_1c98d757cdc4','20261008T134355Z_ba95de7f7cca',
            '20261008T134609Z_70e81b97c5ca','20261008T135127Z_4acb6d269986'],
    }
    return {ROOT / prefix / run for prefixes, runs in groups.items() for prefix in prefixes for run in runs}

def no_target_processes(targets):
    command = "Get-CimInstance Win32_Process -ErrorAction Stop | Select-Object ProcessId,Name,ExecutablePath,CommandLine | ConvertTo-Json -Compress"
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            capture_output=True, text=True, encoding='utf8', errors='replace', timeout=30,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0, 'Process inventory failed: ' + result.stderr[-500:])
    rows = json.loads(result.stdout.lstrip('\ufeff'))
    rows = rows if isinstance(rows, list) else [rows]
    dangerous = []
    for row in rows:
        combined = ((row.get('ExecutablePath') or '') + '\n' + (row.get('CommandLine') or '')).casefold()
        if any(str(target).casefold() in combined for target in targets):
            dangerous.append({'pid': row['ProcessId'], 'name': row['Name']})
        if row.get('Name', '').casefold() == 'zerosisHost_x64.exe'.casefold():
            dangerous.append({'pid': row['ProcessId'], 'name': row['Name']})
    require(not dangerous, 'A target or game Host process remains active: ' + json.dumps(dangerous))
    return {'process_count': len(rows), 'target_processes': 0, 'host_processes': 0, 'utc': timestamp()}

def read_ledger(plan, key):
    name = plan[key]
    require(Path(name).name == name, 'Ledger must be local to this sealed plan')
    path = HERE / name
    pin = plan['ledgers'][name]
    require(path.stat().st_size == pin['bytes'] and sha(path) == pin['sha256'], 'Ledger seal changed: ' + name)
    with gzip.open(path, 'rt', encoding='utf8') as stream:
        return [json.loads(line) for line in stream if line.strip()]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    plan_path, receipt = HERE / 'plan.json', HERE / 'cleanup.json'
    journal_path = HERE / 'cleanup-success.jsonl'
    require(not receipt.exists() and not journal_path.exists(), 'Cleanup latch exists; never replay a started plan')
    require(sha(plan_path) == args.plan_sha256, 'Explicit reviewed plan hash differs')
    plan = json.loads(plan_path.read_text(encoding='utf-8-sig'))
    require(absolute(plan['root']) == ROOT and plan['mode'] == 'PLAN_ONLY', 'Plan root or mode differs')
    require(not plan.get('protected_prefixes_pending', False) and plan.get('protected_count'), 'Protection manifest is not sealed')
    for name, pin in plan['ledgers'].items():
        require(Path(name).name == name, 'Sealed evidence escaped the plan directory')
        path = safe_chain(HERE / name)
        require(path.stat().st_size == pin['bytes'] and sha(path) == pin['sha256'], 'Sealed evidence changed: ' + name)
    targets = {absolute(path) for path in plan['targets']}
    require(len(plan['targets']) == 50 and targets == expected_targets(), 'Plan is not the reviewed exact 50-folder scope')
    retired = read_ledger(plan, 'files_manifest')
    directories = read_ledger(plan, 'directories_manifest')
    protected = read_ledger(plan, 'protected_manifest')
    statuses = read_ledger(plan, 'statuses_manifest')
    roots = read_ledger(plan, 'target_roots_manifest')
    require(len(roots) == 50 and {absolute(row['path']) for row in roots} == targets, 'Root ledger differs from exact targets')
    require(len(statuses) == 25, 'Expected the preserved status of all 25 retired builds/runs')
    for row in statuses:
        report_path = safe_chain(row['report_path'])
        require(any(report_path.is_relative_to(target) for target in targets), 'Retired status escaped its target')
        require(sha(report_path) == row['report_sha256'], 'Original retired status report changed')
    require(len(retired) == plan['target_file_count'] and len(protected) == plan['protected_count'], 'Manifest row count differs')
    require(sum(int(row['size']) for row in retired) == plan['target_logical_bytes'], 'Target byte total differs')
    require(sum('user_save' in row.get('kind', '').split(';') for row in protected) == 8, 'Expected eight protected user saves')
    require(sum('saved_bundle' in row.get('kind', '').split(';') for row in protected) == 3, 'Expected three protected save bundles')
    prefixes = [absolute(path) for path in plan['protected_prefixes']]
    for prefix in prefixes:
        safe_chain(prefix)
        require(not any(prefix == target or prefix.is_relative_to(target) or target.is_relative_to(prefix) for target in targets),
                'Protected prefix overlaps deletion scope: ' + str(prefix))
    retired_paths = {absolute(row['path']) for row in retired}
    directory_paths = {absolute(row['path']) for row in directories}
    require(len(retired_paths) == len(retired) and len(directory_paths) == len(directories), 'Duplicate manifest paths')
    actual_files, actual_dirs = set(), set()
    inventory_cache = set()
    preflight = HERE / 'preflight-status.json'
    def progress(phase, checked, total):
        record = {'phase': phase, 'checked': checked, 'total': total, 'utc': timestamp(),
                  'plan_sha256': args.plan_sha256, 'deletion_started': False}
        atomic_json(preflight, record)
        print(json.dumps(record), flush=True)
    progress('inventory', 0, len(retired))
    for target in targets:
        safe_chain(target, ancestor_cache=inventory_cache)
        for current, dirs, files in os.walk(target, followlinks=False):
            current = Path(current)
            safe_chain(current, ancestor_cache=inventory_cache)
            actual_dirs.add(current)
            for name in dirs + files:
                safe_chain(current / name, ancestor_cache=inventory_cache)
            actual_files.update(current / name for name in files)
    require(actual_files == retired_paths and actual_dirs == directory_paths, 'Live target path sets differ from sealed inventory')
    for row in protected:
        path = absolute(row['path'])
        require(not any(ancestor in targets for ancestor in [path, *path.parents]), 'Protected file overlaps target')
    process_proof = no_target_processes(targets)
    for label, rows in (('protected', protected), ('retired', retired)):
        read_cache = set()
        for index, row in enumerate(rows, 1):
            verify(row, initial_links=True, read_cache=read_cache)
            if index % 5000 == 0:
                progress('preflight_' + label, index, len(rows))
    for row in directories:
        verify(row, content=False, directory=True)
    require(sha(plan_path) == args.plan_sha256, 'Plan changed during preflight')
    if not args.apply:
        print(json.dumps({'status': 'PASS_REVIEW_ONLY', 'files': len(retired), 'protected': len(protected)}), flush=True)
        return
    self_check()
    process_proof = no_target_processes(targets)
    progress('preflight_complete', len(retired), len(retired))
    state = {'status': 'REMOVING', 'plan_sha256': args.plan_sha256, 'script_sha256': sha(__file__),
             'target_folders': 50, 'target_files': len(retired), 'removed_files': 0, 'removed_logical_bytes': 0,
             'protected_count': len(protected), 'protected_hashes_verified_before': True,
             'protected_hashes_verified_after': False, 'readonly_hardlink_survivor_check': 'PASS',
             'process_proof': process_proof, 'started_utc': timestamp(), 'pending_batch_start': None,
             'removed_directories': 0, 'volume_free_bytes_before': shutil.disk_usage(ROOT).free, 'errors': []}
    # Exclusive latch is written before the first real deletion. The append-only
    # fsynced success journal identifies every committed unlink on partial failure.
    with receipt.open('x', encoding='utf8') as stream:
        json.dump(state, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    try:
        unlinked_by_id = {}
        with journal_path.open('x', encoding='utf8', newline='\n') as journal:
            for index, row in enumerate(retired):
                if index % 250 == 0:
                    state['pending_batch_start'] = index
                    atomic_json(receipt, state)
                path = verify(row)
                guarded = dict(row)
                if 'hardlink_count' in row:
                    guarded['expected_remaining_links'] = int(row['hardlink_count']) - unlinked_by_id.get(row['file_id'], 0)
                unlink(path, guarded)
                unlinked_by_id[row['file_id']] = unlinked_by_id.get(row['file_id'], 0) + 1
                json.dump({'path': str(path), 'file_id': row['file_id'], 'sha256': row['sha256'],
                           'bytes': row['size'], 'utc': timestamp()}, journal, ensure_ascii=False, separators=(',', ':'))
                journal.write('\n')
                journal.flush()
                os.fsync(journal.fileno())
                state['removed_files'] += 1
                state['removed_logical_bytes'] += int(row['size'])
                if (index + 1) % 2500 == 0:
                    print(json.dumps({'phase': 'remove', 'removed': index + 1, 'total': len(retired)}), flush=True)
        for row in sorted(directories, key=lambda entry: len(absolute(entry['path']).parts), reverse=True):
            path = verify(row, content=False, directory=True, directory_mtime=False)
            path.rmdir()  # Nonrecursive: an unexpected child must make deletion fail.
            state['removed_directories'] += 1
        require(not any(path.exists() for path in targets), 'A planned target remains')
        read_cache = set()
        for index, row in enumerate(protected, 1):
            verify(row, read_cache=read_cache)
            if index % 5000 == 0:
                print(json.dumps({'phase': 'verify_protected_after', 'checked': index, 'total': len(protected)}), flush=True)
        state.update(status='PASS_OBSOLETE_ARTIFACT_RETIREMENT', protected_hashes_verified_after=True,
                     pending_batch_start=None, volume_free_bytes_after=shutil.disk_usage(ROOT).free,
                     completed_utc=timestamp())
        atomic_json(receipt, state)
    except BaseException as error:
        state['status'] = 'FAILED_PARTIAL_RETIREMENT_RETAINED'
        state['errors'].append(type(error).__name__ + ': ' + str(error))
        state['completed_utc'] = timestamp()
        atomic_json(receipt, state)
        raise
    print(json.dumps(state, ensure_ascii=False), flush=True)

if __name__ == '__main__':
    main()
