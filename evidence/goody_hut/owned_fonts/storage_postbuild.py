"""One engine-only metadata audit; redirect the unchanged auditor's file to RAM."""
from __future__ import annotations

import argparse
import contextlib
import ctypes
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
from unittest.mock import patch

sys.dont_write_bytecode = True
SELF = Path(__file__).absolute()
STAGE = SELF.parent
PROJECT = STAGE.parents[2]
TOOL = PROJECT / 'tools/audit_working_storage.py'
REPORT = STAGE / 'storage_postbuild.json'
CONFORMANCE = PROJECT / 'evidence/goody_hut/owned_fonts/build_objects_retired.json'
TOOL_SHA = '830f512a02d8d8c5e352c9fd4cb8cbb359957420036f2cede743fe2699ab2308'
CONFORMANCE_SHA = '8b7ffe059e69a4868c830348af1ae099fb245fc90607e4efef505af5e0d2cdf4'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def reference(path):
    require(path.is_file(), 'Missing bounded audit input: ' + str(path))
    data = path.read_bytes()
    return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def save(value, mode='w'):
    with REPORT.open(mode, encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n');stream.flush();os.fsync(stream.fileno())


def main():
    require(sys.flags.optimize == 0, 'Run this audit without Python optimization')
    require(STAGE == PROJECT / 'evidence/goody_hut/owned_fonts', 'Unexpected owned audit stage')
    for ancestor in (STAGE, *STAGE.parents):
        info = ancestor.lstat()
        require(stat.S_ISDIR(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Reparse or non-directory audit ancestor: ' + str(ancestor))
    require(not os.path.lexists(REPORT), 'One-use audit report already exists')
    tool, wrapper, conformance = reference(TOOL), reference(SELF), reference(CONFORMANCE)
    require(tool['sha256'] == TOOL_SHA and conformance['sha256'] == CONFORMANCE_SHA,
            'Reviewed audit tool or source conformance changed')
    auditor_code = compile(TOOL.read_text(encoding='utf-8'), str(TOOL), 'exec')
    receipt = {'schema': 'zerosis.goody_hut.prebuild_storage_audit.v1', 'status': 'RUNNING_METADATA_ONLY',
        'started_utc': datetime.now(timezone.utc).isoformat(), 'project_root': str(PROJECT),
        'auditor': tool, 'wrapper': wrapper, 'source_conformance': conformance,
        'engine_only': True, 'retail_mod_test_hold_active': True,
        'host_gamecore_hwnd_executed': False, 'game_process_queries': 0,
        'retail_user_state_accessed': False, 'cleanup_performed': False,
        'default_release_modified': False, 'full_engine_goal_complete': False}
    save(receipt, 'x')
    denied, dll_loads, metadata_symbols, captured = [], [], [], []

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = key(os.fsdecode(arguments[0]))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            require(target == key(PROJECT) or target.startswith(key(PROJECT) + os.sep),
                    'Audit file access escaped the engine project')
            if event in ('os.listdir', 'os.scandir'):
                require(target == key(PROJECT) or target.startswith(key(PROJECT) + os.sep),
                        'Metadata inventory escaped the engine project')
            if event == 'open':
                mode, flags = arguments[1:3]
                writing = (isinstance(mode, str) and any(char in mode for char in 'wax+')) or (
                    type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                if writing and target != key(REPORT):
                    denied.append('unowned-write');raise RuntimeError('Only the new owned audit report may be written')
        if event in ('os.remove', 'os.rmdir', 'os.rename', 'os.mkdir', 'os.link', 'os.symlink', 'os.chmod'):
            denied.append(event);raise RuntimeError('Storage audit cannot mutate existing files or directories')
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2', 'os.exec', 'os.spawn', 'os.posix_spawn'):
            denied.append(event);raise RuntimeError('Storage audit cannot execute or query game processes')
        if event == 'ctypes.dlopen':
            require(arguments and str(arguments[0]).casefold() in ('kernel32', 'kernel32.dll'),
                    'Only kernel32 metadata access is permitted')
            dll_loads.append(str(arguments[0]))
        if event == 'ctypes.dlsym':
            require(len(arguments) == 2 and arguments[1] == 'GetCompressedFileSizeW',
                    'Only GetCompressedFileSizeW metadata lookup is permitted')
            metadata_symbols.append(arguments[1])

    def virtual_mkdir(path, *args, **kwargs):
        require(key(path) == key(PROJECT / 'evidence/storage') and kwargs.get('exist_ok') is True,
                'Auditor attempted an unexpected output directory')

    def virtual_write(path, value, *args, **kwargs):
        require(key(path.parent) == key(PROJECT / 'evidence/storage') and
                re.fullmatch(r'[0-9]{8}T[0-9]{6}Z\.json', path.name) and isinstance(value, str) and not captured,
                'Auditor attempted a repeated or unexpected output')
        report = json.loads(value)
        require(key(report['root']) == key(PROJECT), 'Auditor reported another root')
        captured.append(report)
        return len(value)

    sys.addaudithook(audit)
    stdout = io.StringIO()
    started = time.monotonic()
    try:
        with patch.object(sys, 'argv', [str(TOOL), '--root', str(PROJECT)]), \
             patch.object(Path, 'mkdir', virtual_mkdir), patch.object(Path, 'write_text', virtual_write), \
             contextlib.redirect_stdout(stdout):
            exec(auditor_code, {'__name__': '__main__', '__file__': str(TOOL)})
        require(len(captured) == 1 and not denied and dll_loads == ['kernel32'] and
                metadata_symbols == ['GetCompressedFileSizeW'], 'Metadata audit boundary failed')
        require(reference(TOOL) == tool and reference(SELF) == wrapper and reference(CONFORMANCE) == conformance,
                'Auditor, wrapper or source conformance changed during inventory')
        actual = captured[0]
        require(actual['path_count'] >= actual['unique_file_count'] >= 0 and
                actual['logical_path_bytes'] >= actual['unique_logical_bytes'] >= 0 and
                actual['allocated_path_bytes'] >= actual['unique_allocated_bytes'] >= 0,
                'Metadata audit produced inconsistent whole-root deduplication totals')
        raw = stdout.getvalue().encode('utf-8')
        receipt.update(status='PASS_METADATA_ONLY' if actual['status'] == 'COMPLETE_METADATA_AUDIT' else 'PARTIAL_METADATA_ONLY',
            completed_utc=datetime.now(timezone.utc).isoformat(), wrapper_elapsed_seconds=round(time.monotonic()-started, 3),
            audit=actual, full_stdout_captured_in_ram=True, stdout_file_created=False,
            stdout_bytes=len(raw), stdout_sha256=hashlib.sha256(raw).hexdigest(),
            original_default_audit_output_redirected_to_ram=True,
            unchanged_auditor_executed_from_pinned_source=True,
            permitted_metadata_dll_loads=dll_loads, permitted_metadata_symbols=metadata_symbols,
            forbidden_access_attempts=denied, sealed_inputs_unchanged=True,
            accounting_notes=[
                'Use audit.unique_allocated_bytes once for the entire engine root; nested/group hardlink allocations overlap and must not be summed.',
                'Logical and unique allocated totals describe the whole retained engine project; they are not disposable junk or deletion approval.',
                'GetCompressedFileSizeW excludes directory/MFT overhead and volume free space; external hardlink aliases are not traversed.',
                'MODS, saves, settings and game processes are outside this engine root and were not accessed.',
                'The running receipt and wrapper are included in metadata inventory; the receipt grows only after inventory completes.',
                'Metadata is observed during an interval; no full-content hash inventory or byte-exact default release verification is claimed.',
                'Concurrent source and small evidence additions may occur; publication overhead after the inventory snapshot is outside the measured interval.'])
        save(receipt)
    except BaseException as error:
        raw = stdout.getvalue().encode('utf-8')
        receipt.update(status='FAIL_METADATA_ONLY', error=type(error).__name__ + ': ' + str(error),
            wrapper_elapsed_seconds=round(time.monotonic()-started, 3),
            stdout_bytes=len(raw), stdout_sha256=hashlib.sha256(raw).hexdigest(),
            permitted_metadata_dll_loads=dll_loads, permitted_metadata_symbols=metadata_symbols,
            forbidden_access_attempts=denied)
        save(receipt)
        raise
    proof = reference(REPORT)
    print(json.dumps({'status': receipt['status'], 'report': proof,
        'paths': actual['path_count'], 'unique_files': actual['unique_file_count'],
        'logical_path_bytes': actual['logical_path_bytes'], 'unique_logical_bytes': actual['unique_logical_bytes'],
        'unique_GetCompressedFileSizeW_bytes': actual['unique_allocated_bytes'],
        'hardlinked_path_extra_count': actual['hardlinked_path_extra_count'],
        'errors': len(actual['errors']), 'skipped': len(actual['skipped']),
        'audit_elapsed_seconds': actual['elapsed_seconds'], 'wrapper_elapsed_seconds': receipt['wrapper_elapsed_seconds']},
        ensure_ascii=False))


if __name__ == '__main__':
    main()
