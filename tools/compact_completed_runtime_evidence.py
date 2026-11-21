"""Lossless NTFS compression of hash-sealed, completed private runtime evidence.

Never deletes a file or writes its content. Excludes saves, manual runtimes,
incomplete runs, hardlinks and readonly/reparse files. Preview by default.
"""
from __future__ import annotations
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid

PROJECT = Path(__file__).resolve().parents[1]
RUN = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}')
HASH = re.compile(r'[0-9a-f]{64}')
KERNEL = ctypes.WinDLL('kernel32', use_last_error=True)
KERNEL.GetCompressedFileSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
KERNEL.GetCompressedFileSizeW.restype = wintypes.DWORD
KERNEL.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
KERNEL.CreateFileW.restype = wintypes.HANDLE
KERNEL.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                  ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
KERNEL.DeviceIoControl.restype = wintypes.BOOL
KERNEL.CloseHandle.argtypes = [wintypes.HANDLE]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def artifact(path):
    path = Path(path)
    return {'path': str(path), 'sha256': digest(path), 'bytes': path.stat().st_size}


def stored(path):
    high = wintypes.DWORD()
    ctypes.set_last_error(0)
    low = KERNEL.GetCompressedFileSizeW(str(path), ctypes.byref(high))
    if low == 0xffffffff and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    return (high.value << 32) | low


def safe_file(path, runtime):
    require(path.is_absolute() and path.is_relative_to(runtime), 'File escaped exact completed runtime')
    require(path.suffix.lower() in ('.db', '.dds'), 'Only private DB/DDS evidence is eligible')
    for node in [path, *path.parents]:
        info = os.lstat(node)
        require(not (getattr(info, 'st_file_attributes', 0) & 0x400), 'Reparse point in candidate path')
        if node == runtime:
            break
    info = os.lstat(path)
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'Candidate is not a single-link regular file')
    require(not (getattr(info, 'st_file_attributes', 0) & 1), 'Readonly runtime input is excluded')
    return info


def no_active_host():
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        "@(Get-Process -Name ZeroSisHost_x64 -ErrorAction SilentlyContinue).Count"],
        capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0 and result.stdout.strip() == '0', 'A Host is active or its absence could not be verified')


def compress(path):
    # FSCTL_SET_COMPRESSION with COMPRESSION_FORMAT_DEFAULT; file bytes stay intact.
    handle = KERNEL.CreateFileW(str(path), 0xC0000000, 1, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        mode = ctypes.c_ushort(1)
        returned = wintypes.DWORD()
        if not KERNEL.DeviceIoControl(handle, 0x0009C040, ctypes.byref(mode), 2,
                                      None, 0, ctypes.byref(returned), None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        KERNEL.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--max-gib', type=float, default=8.0, help='Bound each compression batch by logical bytes')
    parser.add_argument('--run-id', action='append', default=[],
                        help='Limit candidates to this exact completed run; repeat for a bounded run set')
    args = parser.parse_args()
    require(0 < args.max_gib <= 32, 'Batch limit must be in (0,32] GiB')
    requested_runs = set(args.run_id)
    require(len(requested_runs) == len(args.run_id) and all(RUN.fullmatch(run) for run in requested_runs),
            'Explicit run IDs must be unique immutable run identities')
    no_active_host()
    started = time.monotonic()
    manual_text = (PROJECT / 'tools/Start-Engine.ps1').read_text(encoding='utf8')
    manual_ids = set(re.findall(RUN.pattern, manual_text))
    categories = {'interactive_game': 'InteractiveGameRuntime', 'new_game': 'NewGameRuntime',
                  'first_turn': 'NewGameRuntime', 'turn_cycle': 'NewGameRuntime', 'save_restore': 'NewGameRuntime'}
    files, skipped_runs, skipped_files, records = {}, [], [], []
    matched_runs = set()
    for category, group in categories.items():
        for result_path in sorted((PROJECT / 'evidence' / category).glob('*/result.json')):
            run_id = result_path.parent.name
            if not RUN.fullmatch(run_id):
                continue
            if requested_runs and run_id not in requested_runs:
                continue
            matched_runs.add(run_id)
            result = json.loads(result_path.read_text(encoding='utf-8-sig'))
            code = result.get('returncode', result.get('exit_code'))
            if (not str(result.get('status', '')).endswith('_PASS') or code != 0 or result.get('timed_out')
                    or run_id in manual_ids or result.get('failures') or result.get('host_failures')):
                require(not requested_runs, 'Explicit run is not a successful non-manual completed run: ' + run_id)
                skipped_runs.append({'run_id': run_id, 'status': result.get('status')})
                continue
            runtime = PROJECT / 'Build' / group / run_id
            if not runtime.is_dir():
                require(not requested_runs, 'Explicit completed runtime is unavailable: ' + run_id)
                skipped_runs.append({'run_id': run_id, 'reason': 'Runtime unavailable'})
                continue
            request_ref = result.get('request')
            require(isinstance(request_ref, dict) and HASH.fullmatch(request_ref.get('sha256', '')),
                    'Completed result lacks request identity')
            request_path = Path(request_ref['path'])
            require(request_path.parent == result_path.parent and digest(request_path) == request_ref['sha256'],
                    'Completed request path/hash differs')
            request = json.loads(request_path.read_text(encoding='utf-8-sig'))
            require(Path(request['cwd']) == runtime and request['run_id'] == run_id, 'Runtime identity mismatch')
            record = {'result': artifact(result_path), 'request': artifact(request_path), 'run_id': run_id}
            rows = [*result.get('generated_files', []), *request.get('runtime_inputs', request.get('inputs', []))]
            used = False
            for row in rows:
                path = Path(row.get('path', ''))
                if path.suffix.lower() not in ('.db', '.dds'):
                    continue
                require(HASH.fullmatch(row.get('sha256', '')) is not None, 'Candidate lacks a retained hash')
                try:
                    info = safe_file(path, runtime)
                except (OSError, ValueError) as error:
                    skipped_files.append({'path': str(path), 'reason': str(error)})
                    continue
                if info.st_size < 65536 or getattr(info, 'st_file_attributes', 0) & 0x800:
                    continue
                key = str(path)
                entry = {'path': key, 'sha256': row['sha256'], 'bytes': info.st_size,
                         'stored_before': stored(path), 'run_id': run_id, 'runtime': str(runtime),
                         'result_sha256': record['result']['sha256'], 'request_sha256': record['request']['sha256']}
                if key in files:
                    require(files[key]['sha256'] == row['sha256'], 'Conflicting retained hashes')
                else:
                    files[key] = entry
                used = True
            if used:
                records.append(record)
    require(not requested_runs or matched_runs == requested_runs,
            'One or more explicit run IDs have no retained completion result')
    selected, selected_size = [], 0
    # Databases have much higher expected compression than already-block-compressed textures.
    for entry in sorted(files.values(), key=lambda r: (Path(r['path']).suffix.lower() != '.db', -r['bytes'], r['path'])):
        if selected_size + entry['bytes'] <= args.max_gib * 1024**3:
            selected.append(entry)
            selected_size += entry['bytes']
    output_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:12]
    output = PROJECT / 'evidence' / 'storage' / output_id
    output.mkdir(parents=True)
    report_path = output / 'compression.json'
    report = {'status': 'PREVIEW_ONLY', 'apply': args.apply, 'scope': 'hash_preserving_NTFS_compression_completed_runtime_DB_DDS',
              'requested_run_ids': sorted(requested_runs),
              'script': artifact(Path(__file__)), 'eligible_files': len(files), 'eligible_bytes': sum(r['bytes'] for r in files.values()),
              'selected_files': len(selected), 'selected_bytes': selected_size, 'planned': selected, 'records': records,
              'completed': [], 'errors': [], 'skipped_runs': skipped_runs, 'skipped_files': skipped_files,
              'excluded_manual_runs': sorted(manual_ids), 'deleted_files': 0, 'saved_game_content_modified': False,
              'game_install_or_mods_modified': False, 'volume_free_space_increase_measured': False}

    def checkpoint():
        report['elapsed_seconds'] = round(time.monotonic()-started, 3)
        report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf8')

    checkpoint()
    if args.apply:
        no_active_host()
        try:
            for record in records:
                for kind in ('result', 'request'):
                    require(digest(record[kind]['path']) == record[kind]['sha256'], 'Retained report changed before compression')
            for index, entry in enumerate(selected):
                path, runtime = Path(entry['path']), Path(entry['runtime'])
                info = safe_file(path, runtime)
                require(info.st_size == entry['bytes'] and digest(path) == entry['sha256'], 'Candidate changed or differs from retained hash')
                require(stored(path) == entry['stored_before'], 'Candidate allocation changed after selection')
                compress(path)
                after = digest(path)
                require(after == entry['sha256'], 'File content changed during NTFS compression')
                report['completed'].append({**entry, 'stored_after': stored(path), 'sha256_after': after})
                if (index + 1) % 25 == 0:
                    checkpoint()
                    print(json.dumps({'compressed': index+1, 'selected': len(selected)}, separators=(',', ':')), flush=True)
            for record in records:
                for kind in ('result', 'request'):
                    require(digest(record[kind]['path']) == record[kind]['sha256'], 'Retained report changed during compression')
            report['status'] = 'PASS_RETAINED_CONTENT_COMPRESSION'
        except Exception as error:
            report['status'] = 'FAILED_COMPRESSION_PARTIAL_PRESERVED'
            report['errors'].append(type(error).__name__ + ': ' + str(error))
        finally:
            report['stored_reduction'] = sum(r['stored_before']-r['stored_after'] for r in report['completed'])
            checkpoint()
    print(json.dumps({'status': report['status'], 'eligible_files': len(files),
                      'eligible_gib': round(report['eligible_bytes']/1024**3, 3),
                      'selected_files': len(selected), 'selected_gib': round(selected_size/1024**3, 3),
                      'compressed_files': len(report['completed']),
                      'stored_reduction': report.get('stored_reduction', 0),
                      'errors': report['errors'], 'report': str(report_path)}, ensure_ascii=False), flush=True)
    return 0 if report['status'] in ('PREVIEW_ONLY', 'PASS_RETAINED_CONTENT_COMPRESSION') else 1


if __name__ == '__main__':
    raise SystemExit(main())
