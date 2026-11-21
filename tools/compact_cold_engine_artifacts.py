"""Hash-preserving, explicit-plan NTFS compression of cold engine artifacts.

No content deletion, renaming, save changes, or directory-wide compression.
Preview freezes the exact file list; apply refuses a changed plan or file.
"""
from __future__ import annotations
import argparse
from collections import Counter
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import uuid

from compact_completed_runtime_evidence import PROJECT, KERNEL, artifact, compress, digest, require, stored

EXTENSIONS = {'.db', '.dds', '.json', '.jsonl', '.log', '.map', '.ggxml',
              '.bin', '.dat', '.h', '.cpp', '.lua', '.obj', '.pch', '.lib', '.pdb'}
HOT_GROUPS = {'SDKIncremental', 'SDK_x64', 'SDK_Reference', 'LuaBorrowed',
              'ICU44', 'RuntimeInputCache', 'UiWindowHost', 'UnitAssets'}
RUN = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}')


def idle():
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
        '@(Get-Process -Name ZeroSisHost_x64,cl,link,compact -ErrorAction SilentlyContinue).Count'],
        capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0 and result.stdout.strip() == '0', 'Host/compiler/compressor active or unknown')


def files_under(root):
    for folder, dirs, names in os.walk(root, followlinks=False):
        parent = Path(folder)
        require(not parent.lstat().st_file_attributes & 0x400, 'Reparse directory')
        for name in dirs:
            require(not (parent / name).lstat().st_file_attributes & 0x400, 'Reparse subtree')
        for name in names:
            yield parent / name


def validate(path, exclusions, allow_compressed=False):
    path = Path(path)
    require(path.is_absolute() and path.is_relative_to(PROJECT), 'Outside project')
    relative = path.relative_to(PROJECT)
    require(relative.parts[0] in ('Build', 'evidence'), 'Outside Build/evidence')
    require(path.suffix.lower() in EXTENSIONS, 'Unapproved extension')
    require(not any(path.is_relative_to(item) for item in exclusions), 'Protected current/manual dependency')
    require(not any(part.lower() in ('saves', 'savedgames', 'savegames') for part in relative.parts), 'Save path')
    for node in (path, *path.parents):
        require(not node.lstat().st_file_attributes & 0x400, 'Reparse ancestor')
        if node == PROJECT:
            break
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'Not a single-link regular file')
    require(not info.st_file_attributes & 1, 'Readonly input')
    require(info.st_size >= 65536, 'Small file')
    require(allow_compressed or not info.st_file_attributes & 0x800, 'Already compressed')
    if path.suffix.lower() == '.db':
        require(not any(Path(str(path) + suffix).exists() for suffix in ('-wal', '-shm', '-journal')),
                'Database has a journal or shared-memory sidecar')
    return info


def identity(info):
    return {'device': info.st_dev, 'file_id': info.st_ino, 'bytes': info.st_size,
            'mtime_ns': info.st_mtime_ns, 'links': info.st_nlink}


def write_gz(path, value):
    with gzip.open(path, 'wt', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(',', ':'))


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


def decompress(path):
    handle = KERNEL.CreateFileW(str(path), 0xC0000000, 1, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        mode, returned = ctypes.c_ushort(0), wintypes.DWORD()
        if not KERNEL.DeviceIoControl(handle, 0x0009C040, ctypes.byref(mode), 2,
                                      None, 0, ctypes.byref(returned), None):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        KERNEL.CloseHandle(handle)


def preview():
    idle()
    launcher = PROJECT / 'tools/Start-Engine.ps1'
    manual_ids = set(RUN.findall(launcher.read_text(encoding='utf8')))
    exclusions = [PROJECT / 'Build' / group for group in HOT_GROUPS]
    exclusions += [PROJECT / 'Build/InteractiveGameRuntime' / run for run in manual_ids]
    exclusions += [PROJECT / 'evidence/interactive_game' / run for run in manual_ids]
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:12]
    output = PROJECT / 'evidence/storage' / (stamp + '_cold')
    output.mkdir(parents=True)
    exclusions.append(output)
    selected, skipped = [], Counter()
    for scope in ('Build', 'evidence'):
        for path in files_under(PROJECT / scope):
            if path.suffix.lower() not in EXTENSIONS:
                continue
            try:
                info = validate(path, exclusions)
            except ValueError as error:
                skipped[str(error)] += 1
                continue
            selected.append({'path': str(path), **identity(info), 'sha256': digest(path), 'stored_before': stored(path)})
    # Protect working source/tools/tests and all executable/save bytes. These
    # are never selected, and are rechecked independently after compression.
    guards = {}
    for group in ('Source', 'Tests', 'tools'):
        for path in files_under(PROJECT / group):
            if path.suffix.lower() != '.pyc':
                guards[str(path)] = artifact(path)
    for path in files_under(PROJECT / 'Build'):
        if path.suffix.lower() in ('.exe', '.dll', '.zssave'):
            guards[str(path)] = artifact(path)
    plan = {'scope': 'lossless_NTFS_cold_Build_evidence_only', 'script': artifact(Path(__file__)),
            'helper': artifact(PROJECT / 'tools/compact_completed_runtime_evidence.py'),
            'excluded_manual_runs': sorted(manual_ids), 'exclusions': list(map(str, exclusions)),
            'selected': selected, 'guards': list(guards.values()), 'skipped': dict(skipped)}
    plan_path = output / 'plan.json.gz'
    write_gz(plan_path, plan)
    groups = Counter()
    for row in selected:
        parts = Path(row['path']).relative_to(PROJECT).parts
        groups['/'.join(parts[:2])] += row['bytes']
    summary = {'status': 'PREVIEW_ONLY', 'plan': artifact(plan_path), 'selected_files': len(selected),
               'selected_bytes': sum(row['bytes'] for row in selected), 'protected_files': len(guards),
               'groups': dict(groups.most_common()), 'skipped': dict(skipped),
               'excluded_manual_runs': sorted(manual_ids)}
    write_json(output / 'preview.json', summary)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


def apply(plan_path, expected_hash):
    plan_path = plan_path.resolve(strict=True)
    require(plan_path.is_relative_to(PROJECT / 'evidence/storage'), 'Plan outside storage evidence')
    require(digest(plan_path) == expected_hash, 'Unreviewed or changed plan')
    with gzip.open(plan_path, 'rt', encoding='utf8') as stream:
        plan = json.load(stream)
    for ref in (plan['script'], plan['helper']):
        require(digest(ref['path']) == ref['sha256'], 'Compression code changed')
    exclusions = list(map(Path, plan['exclusions']))
    output = plan_path.parent
    report_path = output / 'compression.json'
    require(not report_path.exists(), 'One-shot plan has already been applied')
    idle()
    for row in plan['guards']:
        require(digest(row['path']) == row['sha256'], 'Protected file changed before apply: ' + row['path'])
    # Validate all targets before any change, not merely one at a time.
    for row in plan['selected']:
        path = Path(row['path'])
        info = validate(path, exclusions)
        require(identity(info) == {key: row[key] for key in identity(info)}, 'Candidate identity changed')
        require(stored(path) == row['stored_before'] and digest(path) == row['sha256'], 'Candidate changed')
    report = {'status': 'COMPRESSING', 'plan': artifact(plan_path), 'selected_files': len(plan['selected']),
              'completed_files': 0, 'stored_reduction_bytes': 0, 'reverted_without_savings': 0,
              'deleted_files': 0, 'content_hashes_unchanged': False, 'protected_files_unchanged': False,
              'errors': []}
    write_json(report_path, report)
    ledger_path = output / 'compressed-files.jsonl.gz'
    try:
        with gzip.open(ledger_path, 'wt', encoding='utf8') as ledger:
            for index, row in enumerate(plan['selected'], 1):
                path = Path(row['path'])
                info = validate(path, exclusions)
                require(identity(info) == {key: row[key] for key in identity(info)}, 'Candidate changed during apply')
                require(digest(path) == row['sha256'] and stored(path) == row['stored_before'], 'Candidate content/allocation changed')
                compress(path)
                after = stored(path)
                if after >= row['stored_before']:
                    decompress(path)
                    after = stored(path)
                    report['reverted_without_savings'] += 1
                info = validate(path, exclusions, allow_compressed=True)
                require(identity(info) == {key: row[key] for key in identity(info)}, 'File identity/mtime changed')
                require(digest(path) == row['sha256'], 'Content changed during NTFS compression')
                require(after <= row['stored_before'], 'Allocation increased')
                ledger.write(json.dumps({**row, 'stored_after': after}, ensure_ascii=False) + '\n')
                ledger.flush()
                report['completed_files'] = index
                report['stored_reduction_bytes'] += row['stored_before'] - after
                if index % 100 == 0:
                    write_json(report_path, report)
                    print(json.dumps({'completed': index, 'selected': len(plan['selected']),
                                      'saved_bytes': report['stored_reduction_bytes']}), flush=True)
        for row in plan['guards']:
            require(digest(row['path']) == row['sha256'], 'Protected file changed: ' + row['path'])
        report.update(status='PASS_COLD_ARTIFACTS_LOSSLESS_COMPRESSION', content_hashes_unchanged=True,
                      protected_files_unchanged=True, protected_file_count=len(plan['guards']),
                      ledger=artifact(ledger_path))
    except Exception as error:
        report['status'] = 'FAILED_PARTIAL_COMPRESSION_CONTENT_PRESERVED'
        report['errors'].append(type(error).__name__ + ': ' + str(error))
    write_json(report_path, report)
    print(json.dumps({**report, 'report': str(report_path)}, ensure_ascii=False), flush=True)
    return 0 if report['status'].startswith('PASS_') else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', type=Path, help='Exact reviewed plan.json.gz')
    parser.add_argument('--expect-plan-sha256')
    args = parser.parse_args()
    if args.apply:
        require(args.expect_plan_sha256 is not None, 'Plan SHA required')
        return apply(args.apply, args.expect_plan_sha256)
    require(args.expect_plan_sha256 is None, 'Unexpected plan SHA in preview')
    preview()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
