"""Preview or hash-sealed NTFS compression for explicitly selected private IDs.

Only selected Host/runtime Build directories and their paired evidence trees are
eligible. This tool never deletes or renames files and never touches game saves.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import time
import uuid

from compact_completed_runtime_evidence import PROJECT, compress, digest, stored, require

RUN = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}')
TEXT_EXTENSIONS = {'.h', '.hpp', '.cpp', '.inl', '.lua', '.xml', '.ggxml', '.json',
                   '.jsonl', '.log', '.map', '.txt', '.packet', '.py', '.rsp'}
MAX_BYTES = 8 * 1024**3
MIN_BYTES = 16 * 1024
REPARSE = 0x400
READONLY = 0x1
COMPRESSED = 0x800
OUTPUT_ROOT = PROJECT / 'evidence' / 'storage'


def no_active_work():
    result = subprocess.run(
        ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command',
         "@(Get-Process -Name ZeroSisHost_x64,cl,link,ninja,compact -ErrorAction SilentlyContinue).Count"],
        capture_output=True, text=True, timeout=15,
        creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0 and result.stdout.strip() == '0',
            'Host, compiler, linker, ninja, or compressor is active or its absence could not be verified')


def boundary(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    require(path.is_absolute() and path != PROJECT and path.is_relative_to(PROJECT),
            'Path escaped the engine project')
    resolved = path.resolve(strict=True)
    require(resolved == path, 'Path resolves through a reparse point or alias: ' + str(path))
    for ancestor in (path, *path.parents):
        info = ancestor.lstat()
        require(not info.st_file_attributes & REPARSE, 'Reparse point in selected path: ' + str(ancestor))
        if ancestor == PROJECT:
            break
    return path


def file_identity(path: Path, allow_compressed: bool = False) -> dict:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), 'Candidate is not a regular file: ' + str(path))
    require(info.st_nlink == 1, 'Candidate is hardlinked: ' + str(path))
    require(not info.st_file_attributes & READONLY, 'Candidate is readonly: ' + str(path))
    require(allow_compressed or not info.st_file_attributes & COMPRESSED,
            'Candidate is already NTFS-compressed: ' + str(path))
    return {'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns,
            'device': info.st_dev, 'file_id': info.st_ino,
            'attributes': info.st_file_attributes, 'links': info.st_nlink}


def is_utf8_text(path: Path) -> bool:
    try:
        with path.open('rb') as stream:
            data = stream.read()
        if b'\0' in data:
            return False
        data.decode('utf-8', errors='strict')
        return True
    except (OSError, UnicodeDecodeError):
        return False


def candidate_kind(path: Path, host_build: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS:
        return 'utf8-text' if is_utf8_text(path) else None
    if suffix == '.db':
        if any(Path(str(path) + ending).exists() for ending in ('-wal', '-shm', '-journal')):
            return None
        return 'database'
    if suffix:
        return None
    include_roots = host_build / 'frozen' / 'include_roots'
    try:
        if path.is_relative_to(include_roots) and path != include_roots and is_utf8_text(path):
            return 'utf8-extensionless-header'
    except (OSError, ValueError):
        return None
    return None


def walk_regular(root: Path):
    root = boundary(root)
    for current, dirs, files in os.walk(root, topdown=True, followlinks=False):
        parent = boundary(Path(current))
        for name in dirs:
            directory = parent / name
            info = directory.lstat()
            require(stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & REPARSE,
                    'Non-directory or reparse directory in selected tree: ' + str(directory))
            boundary(directory)
        for name in files:
            path = parent / name
            info = path.lstat()
            require(not info.st_file_attributes & REPARSE, 'Reparse file in selected tree: ' + str(path))
            if stat.S_ISREG(info.st_mode):
                yield path


def load_json(path: Path) -> dict:
    with path.open('r', encoding='utf-8-sig') as stream:
        value = json.load(stream)
    require(isinstance(value, dict), 'Expected JSON object: ' + str(path))
    return value


def validate_host(host_id: str) -> tuple[Path, Path]:
    build = boundary(PROJECT / 'Build' / 'UiWindowHost' / host_id)
    evidence = boundary(PROJECT / 'evidence' / 'ui_window_host' / host_id)
    report_path = boundary(evidence / 'build_result.json')
    report = load_json(report_path)
    require(report.get('build_id') == host_id and
            report.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
            report.get('source_inputs_unchanged') is True,
            'Selected Host is not a sealed completed build: ' + host_id)
    executable = report.get('executable')
    require(isinstance(executable, dict) and isinstance(executable.get('path'), str) and
            re.fullmatch(r'[0-9a-f]{64}', str(executable.get('sha256', ''))) is not None,
            'Host build report lacks an executable identity')
    exe_path = boundary(Path(executable['path']))
    require(exe_path.is_relative_to(build) and digest(exe_path) == executable['sha256'],
            'Selected Host executable differs from its build report')
    return build, evidence


def validate_run(run_id: str) -> tuple[Path, Path]:
    build = boundary(PROJECT / 'Build' / 'InteractiveGameRuntime' / run_id)
    evidence = boundary(PROJECT / 'evidence' / 'interactive_game' / run_id)
    request_path = boundary(evidence / 'request.json')
    result_path = boundary(evidence / 'result.json')
    request = load_json(request_path)
    result = load_json(result_path)
    require(request.get('run_id') == run_id and request.get('smoke') is True,
            'Selected runtime request is not an explicit smoke run: ' + run_id)
    require(Path(request.get('cwd', '')).resolve(strict=True) == build,
            'Selected request cwd differs from its exact runtime directory')
    code = result.get('returncode', result.get('exit_code'))
    require(isinstance(code, int) and not isinstance(code, bool) and
            isinstance(result.get('status'), str) and result.get('timed_out') is not True,
            'Selected runtime has no completed result/return code: ' + run_id)
    request_ref = result.get('request')
    if request_ref is not None:
        require(isinstance(request_ref, dict) and
                Path(request_ref.get('path', '')).resolve(strict=True) == request_path and
                request_ref.get('sha256') == digest(request_path),
                'Completed result request provenance differs: ' + run_id)
    return build, evidence


def inventory_selected(host_ids: list[str], run_ids: list[str]) -> dict:
    require(host_ids or run_ids, 'At least one explicit --host-id or --run-id is required')
    require(len(host_ids) == len(set(host_ids)) and all(RUN.fullmatch(value) for value in host_ids),
            'Host IDs must be unique exact existing run-shaped IDs')
    require(len(run_ids) == len(set(run_ids)) and all(RUN.fullmatch(value) for value in run_ids),
            'Runtime IDs must be unique exact existing run IDs')
    launcher_text = (PROJECT / 'tools' / 'Start-Engine.ps1').read_text(encoding='utf-8-sig')
    manual_ids = set(RUN.findall(launcher_text))
    require(not (manual_ids & set(host_ids + run_ids)),
            'Manual Start-Engine runtime IDs cannot be compressed by this tool')

    roots = []
    for host_id in host_ids:
        roots.extend(validate_host(host_id))
    for run_id in run_ids:
        roots.extend(validate_run(run_id))
    require(len(roots) == len(set(roots)), 'Duplicate selected directory roots')
    host_builds = [root for root in roots
                   if root.parent.name == 'UiWindowHost' and root.parent.parent.name == 'Build']
    rows, seen = [], set()
    total_bytes = 0
    for root in roots:
        host_build = root if root in host_builds else next(
            (candidate for candidate in host_builds if root.is_relative_to(candidate)), root)
        for path in walk_regular(root):
            info = path.lstat()
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or
                    info.st_file_attributes & (READONLY | COMPRESSED) or info.st_size < MIN_BYTES):
                continue
            kind = candidate_kind(path, host_build) if host_build is not None else candidate_kind(path, root)
            if kind is None:
                continue
            identity = file_identity(path)
            if identity['bytes'] < MIN_BYTES:
                continue
            key = (identity['device'], identity['file_id'])
            require(key not in seen, 'Selected roots contain duplicate hardlink identity: ' + str(path))
            seen.add(key)
            before_sha = digest(path)
            # Detect concurrent change between metadata, contents and allocation reads.
            after = file_identity(path)
            require(all(after[key_name] == identity[key_name]
                        for key_name in ('bytes', 'mtime_ns', 'device', 'file_id', 'attributes', 'links')) and
                    digest(path) == before_sha,
                    'Candidate changed while preparing the compression plan: ' + str(path))
            allocation = stored(path)
            row = {'path': str(path), **identity, 'sha256': before_sha,
                   'stored_before': allocation, 'kind': kind}
            rows.append(row)
            total_bytes += identity['bytes']
            require(total_bytes <= MAX_BYTES, 'Selected logical bytes exceed the 8 GiB plan limit')
    rows.sort(key=lambda item: item['path'].casefold())
    require(rows, 'No eligible uncompressed single-link files exist in the selected directories')
    return {'files': rows, 'logical_bytes': total_bytes, 'manual_ids_excluded': sorted(manual_ids)}


def write_gzip_exclusive(path: Path, value: dict):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'wb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as stream:
            stream.write(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode('utf-8'))


def preview(args):
    no_active_work()
    inventory = inventory_selected(args.host_id, args.run_id)
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    boundary(OUTPUT_ROOT)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '_' + uuid.uuid4().hex[:12]
    output = OUTPUT_ROOT / (stamp + '_selected')
    output.mkdir(parents=True, exist_ok=False)
    boundary(output)
    plan_path = output / 'plan.json.gz'
    summary_path = output / 'preview.json'
    plan = {'schema': 'ZEROSIS_SELECTED_ENGINE_COMPRESSION_PLAN_V1',
            'status': 'PREVIEW_ONLY', 'root': str(PROJECT),
            'tool': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__))},
            'selected_host_ids': args.host_id, 'selected_run_ids': args.run_id,
            'files': inventory['files'], 'logical_bytes': inventory['logical_bytes'],
            'manual_ids_excluded': inventory['manual_ids_excluded'],
            'max_logical_bytes': MAX_BYTES}
    write_gzip_exclusive(plan_path, plan)
    plan_sha = digest(plan_path)
    summary = {'schema': 'ZEROSIS_SELECTED_ENGINE_COMPRESSION_PREVIEW_V1',
               'status': 'PREVIEW_ONLY', 'plan': {'path': str(plan_path), 'sha256': plan_sha,
                                                  'bytes': plan_path.stat().st_size},
               'tool_sha256': plan['tool']['sha256'], 'host_ids': args.host_id,
               'run_ids': args.run_id, 'files': len(plan['files']),
               'logical_bytes': plan['logical_bytes'],
               'stored_before_bytes': sum(row['stored_before'] for row in plan['files']),
               'max_logical_bytes': MAX_BYTES,
               'manual_ids_excluded': inventory['manual_ids_excluded']}
    with summary_path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return 0


def verify_row(row: dict, expected_compressed: bool = False) -> Path:
    path = boundary(Path(row['path']))
    info = path.lstat()
    attrs = info.st_file_attributes
    expected_attrs = row['attributes']
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == row['links'] == 1 and
            info.st_size == row['bytes'] and info.st_mtime_ns == row['mtime_ns'] and
            info.st_dev == row['device'] and info.st_ino == row['file_id'],
            'Candidate identity or timestamps changed: ' + str(path))
    if expected_compressed:
        require(attrs & COMPRESSED and (attrs & ~COMPRESSED) == (expected_attrs & ~COMPRESSED),
                'Candidate compression attributes changed unexpectedly: ' + str(path))
    else:
        require(attrs == expected_attrs and not attrs & (READONLY | COMPRESSED),
                'Candidate attributes changed or file is no longer eligible: ' + str(path))
    require(digest(path) == row['sha256'], 'Candidate content hash changed: ' + str(path))
    return path


def apply(plan_path: Path, expected_sha: str) -> int:
    no_active_work()
    plan_path = boundary(plan_path)
    require(plan_path.is_relative_to(OUTPUT_ROOT) and plan_path.name == 'plan.json.gz',
            'Plan must be an exact generated selected-compression plan under evidence/storage')
    require(re.fullmatch(r'[0-9a-f]{64}', expected_sha) is not None and digest(plan_path) == expected_sha,
            'Plan SHA-256 does not match the reviewed value')
    with gzip.open(plan_path, 'rt', encoding='utf-8') as stream:
        plan = json.load(stream)
    require(plan.get('schema') == 'ZEROSIS_SELECTED_ENGINE_COMPRESSION_PLAN_V1' and
            plan.get('status') == 'PREVIEW_ONLY' and plan.get('root') == str(PROJECT),
            'Invalid plan identity or status')
    require(plan.get('tool', {}).get('path') == str(Path(__file__).resolve()) and
            plan['tool'].get('sha256') == digest(Path(__file__)),
            'Compression tool changed after preview')
    started = plan_path.parent / 'apply.started'
    journal_path = plan_path.parent / 'compressed-files.jsonl'
    report_path = plan_path.parent / 'compression.json'
    require(not started.exists() and not journal_path.exists() and not report_path.exists(),
            'This plan already has an apply attempt; inspect its one-shot journal')
    require(plan['selected_host_ids'] or plan['selected_run_ids'], 'Plan has no explicit selected IDs')
    require(len(plan['files']) == len({row['path'] for row in plan['files']}) and
            sum(row['bytes'] for row in plan['files']) == plan['logical_bytes'] <= MAX_BYTES,
            'Plan file list or logical byte bound is invalid')
    # Revalidate selection provenance and the full candidate set before creating the one-shot start marker.
    fresh = inventory_selected(plan['selected_host_ids'], plan['selected_run_ids'])
    require(fresh['files'] == plan['files'] and fresh['logical_bytes'] == plan['logical_bytes'],
            'Selected files changed since preview; create and review a fresh plan')
    for row in plan['files']:
        verify_row(row)
        require(stored(Path(row['path'])) == row['stored_before'],
                'Candidate allocation changed since preview: ' + row['path'])

    boundary(plan_path.parent)
    with started.open('x', encoding='utf-8', newline='\n') as marker:
        marker.write(json.dumps({'status': 'APPLYING', 'plan_sha256': expected_sha,
                                 'started_utc': datetime.now(timezone.utc).isoformat()},
                                ensure_ascii=False) + '\n')
        marker.flush()
        os.fsync(marker.fileno())
    completed, reduction = 0, 0
    errors = []
    try:
        next_process_check = 0.0
        with journal_path.open('x', encoding='utf-8', newline='\n') as journal:
            for row in plan['files']:
                # Keep checking for a newly started build without spawning a
                # PowerShell process once per file (thousands of times).
                if time.monotonic() >= next_process_check:
                    no_active_work()
                    next_process_check = time.monotonic() + 5.0
                path = verify_row(row)
                require(stored(path) == row['stored_before'], 'Candidate allocation changed before compression: ' + str(path))
                compress(path)
                after_sha = digest(path)
                after = file_identity(path, allow_compressed=True)
                require(after_sha == row['sha256'] and
                        all(after[key] == row[key] for key in ('bytes', 'mtime_ns', 'device', 'file_id', 'links')),
                        'Compression changed candidate content or identity: ' + str(path))
                attrs = path.lstat().st_file_attributes
                require(attrs & COMPRESSED and (attrs & ~COMPRESSED) == (row['attributes'] & ~COMPRESSED),
                        'Compression changed unexpected file attributes: ' + str(path))
                stored_after = stored(path)
                entry = {'path': row['path'], 'bytes': row['bytes'], 'sha256': after_sha,
                         'device': row['device'], 'file_id': row['file_id'],
                         'mtime_ns': row['mtime_ns'], 'stored_before': row['stored_before'],
                         'stored_after': stored_after,
                         'reclaimed_bytes': row['stored_before'] - stored_after}
                journal.write(json.dumps(entry, ensure_ascii=False, separators=(',', ':')) + '\n')
                journal.flush()
                os.fsync(journal.fileno())
                completed += 1
                reduction += entry['reclaimed_bytes']
        for row in plan['files']:
            verify_row(row, expected_compressed=True)
        report = {'schema': 'ZEROSIS_SELECTED_ENGINE_COMPRESSION_RESULT_V1',
                  'status': 'PASS_SELECTED_CONTENT_HASH_PRESERVING_COMPRESSION',
                  'plan': {'path': str(plan_path), 'sha256': expected_sha},
                  'tool_sha256': digest(Path(__file__)), 'files_compressed': completed,
                  'logical_bytes': plan['logical_bytes'], 'stored_reduction_bytes': reduction,
                  'content_hashes_and_file_identity_preserved': True,
                  'selected_host_ids': plan['selected_host_ids'],
                  'selected_run_ids': plan['selected_run_ids'],
                  'journal': {'path': str(journal_path), 'sha256': digest(journal_path),
                              'bytes': journal_path.stat().st_size},
                  'errors': errors}
        with report_path.open('x', encoding='utf-8', newline='\n') as stream:
            json.dump(report, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        with started.open('a', encoding='utf-8', newline='\n') as marker:
            marker.write(json.dumps({'status': report['status'], 'finished_utc': datetime.now(timezone.utc).isoformat(),
                                     'files_compressed': completed}, ensure_ascii=False) + '\n')
        print(json.dumps(report, ensure_ascii=False), flush=True)
        return 0
    except Exception as error:
        errors.append(type(error).__name__ + ': ' + str(error))
        failure = {'schema': 'ZEROSIS_SELECTED_ENGINE_COMPRESSION_RESULT_V1',
                   'status': 'FAILED_PARTIAL_COMPRESSION_NO_REPLAY',
                   'plan': {'path': str(plan_path), 'sha256': expected_sha},
                   'tool_sha256': digest(Path(__file__)), 'files_compressed': completed,
                   'logical_bytes': plan['logical_bytes'], 'stored_reduction_bytes': reduction,
                   'content_hashes_and_file_identity_preserved': False,
                   'journal': ({'path': str(journal_path), 'sha256': digest(journal_path),
                                'bytes': journal_path.stat().st_size}
                               if journal_path.exists() else None), 'errors': errors}
        if not report_path.exists():
            with report_path.open('x', encoding='utf-8', newline='\n') as stream:
                json.dump(failure, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
        with started.open('a', encoding='utf-8', newline='\n') as marker:
            marker.write(json.dumps({'status': failure['status'], 'error': errors[-1],
                                     'finished_utc': datetime.now(timezone.utc).isoformat()},
                                    ensure_ascii=False) + '\n')
        print(json.dumps(failure, ensure_ascii=False), flush=True)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--host-id', action='append', default=[],
                        help='Exact existing Build/UiWindowHost and evidence ID; repeat to select more')
    parser.add_argument('--run-id', action='append', default=[],
                        help='Exact completed smoke Build/InteractiveGameRuntime and evidence ID; repeat')
    parser.add_argument('--apply', type=Path, help='Apply one exact reviewed plan.json.gz')
    parser.add_argument('--expect-plan-sha256', help='Required SHA-256 for --apply')
    args = parser.parse_args()
    require(args.apply is None or args.expect_plan_sha256 is not None,
            '--apply requires --expect-plan-sha256')
    require(args.apply is not None or args.expect_plan_sha256 is None,
            '--expect-plan-sha256 is valid only with --apply')
    if args.apply is not None:
        require(not args.host_id and not args.run_id,
                'Do not combine explicit selection IDs with an apply plan')
        return apply(args.apply, args.expect_plan_sha256)
    no_active_work()
    return preview(args)


if __name__ == '__main__':
    raise SystemExit(main())
