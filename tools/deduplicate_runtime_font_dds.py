"""Hash-sealed plan/apply for retained scene font copies; no rendering or source edits.

Only manifest-declared fonts with matching full SHA-256 are eligible. Existing
single-link candidates supply verified payloads for a bounded shared cache. A
pending replacement retains the old identity through a temporary hardlink.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
RUN = re.compile(r'20\d{6}T\d{6}Z_[0-9a-f]{12}')
SESSION = re.compile(r'[0-9a-f]{32}')
SCENE = re.compile(r'play-ui-[1-9][0-9]*')
SHA = re.compile(r'[0-9a-f]{64}')
REPARSE, READONLY, COMPRESSED = 0x400, 0x1, 0x800
LINK_CAP, MEMBERS_PER_SHARD, MAX_SHARDS = 1000, 999, 64
SCHEMA = 'runtime-font-dds-dedup-v1'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def io_path(path):
    value = os.path.abspath(os.fspath(path))
    return '\\\\?\\' + value if os.name == 'nt' and not value.startswith('\\\\?\\') else value


def plain_path(value):
    return Path(value[4:] if value.startswith('\\\\?\\') else value)


def checked(path, root=PROJECT, *, missing=False):
    """Check lexical and final boundaries, including every existing ancestor."""
    path, root = Path(os.path.abspath(path)), Path(os.path.abspath(root))
    require(path.is_relative_to(root), 'Path escapes approved root: ' + str(path))
    for item in (path, *path.parents):
        try:
            info = os.lstat(io_path(item))
        except FileNotFoundError:
            require(missing, 'Missing path: ' + str(item))
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & REPARSE,
                'Symlink or reparse point: ' + str(item))
    resolved = plain_path(os.path.realpath(io_path(path), strict=not missing))
    require(resolved == path and resolved.is_relative_to(root), 'Final path differs: ' + str(path))
    return path


def target_path(path, root=PROJECT, *, missing=False):
    path = checked(path, root, missing=missing)
    parts = path.relative_to(root).parts
    require(len(parts) == 8 and parts[:2] == ('Build', 'InteractiveGameRuntime') and
            RUN.fullmatch(parts[2]) and parts[3] == 'sessions' and
            SESSION.fullmatch(parts[4]) and SCENE.fullmatch(parts[5]) and
            parts[6] == 'textures' and parts[7].lower().endswith('.dds'),
            'Not an exact retained scene DDS path: ' + str(path))
    return path


def digest(path):
    h = hashlib.sha256()
    with open(io_path(path), 'rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def snapshot(path):
    entry = os.lstat(io_path(path))
    require(stat.S_ISREG(entry.st_mode) and entry.st_ino and
            not getattr(entry, 'st_file_attributes', 0) & REPARSE,
            'Not a regular file with stable identity: ' + str(path))
    with open(io_path(path), 'rb') as stream:
        info = os.fstat(stream.fileno())
    require((info.st_dev, info.st_ino) == (entry.st_dev, entry.st_ino), 'File identity changed while opening')
    disk = info.st_size
    if os.name == 'nt':
        fn = ctypes.WinDLL('kernel32', use_last_error=True).GetCompressedFileSizeW
        fn.argtypes = [ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
        fn.restype = ctypes.c_ulong
        high = ctypes.c_ulong()
        ctypes.set_last_error(0)
        low = fn(io_path(path), ctypes.byref(high))
        require(low != 0xffffffff or not ctypes.get_last_error(), 'Cannot read file allocation')
        disk = (high.value << 32) | low
    return {'bytes': info.st_size, 'device': info.st_dev, 'file_id': info.st_ino,
            'mtime_ns': info.st_mtime_ns, 'attributes': getattr(info, 'st_file_attributes', 0),
            'links': info.st_nlink, 'allocated_bytes': disk}


def full_record(path):
    before = snapshot(path)
    value = digest(path)
    require(snapshot(path) == before, 'File changed during full hash: ' + str(path))
    return {'path': str(path), **before, 'sha256': value}


def same_identity(a, b):
    return (a['device'], a['file_id']) == (b['device'], b['file_id'])


def read_json(path):
    with open(io_path(path), encoding='utf-8-sig') as stream:
        return json.load(stream)


def children(path):
    with os.scandir(io_path(path)) as entries:
        return sorted((path / item.name for item in entries), key=str)


def process_query(command, root, **environment):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', command],
                            env={**os.environ, 'ZS_FONT_ROOT': str(root) + os.sep,
                                 'ZS_FONT_PID': str(os.getpid()), **environment},
                            capture_output=True, text=True, timeout=20,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0, 'Could not check active native processes: ' + result.stderr[:300])
    rows = json.loads(result.stdout)
    require(isinstance(rows, list), 'Process query did not return a complete array')
    return rows


def no_active_work(root=PROJECT):
    require(os.name == 'nt', 'Native apply/plan process guard requires Windows')
    creation = "@{n='CreationTime';e={if ($_.CreationDate) { $_.CreationDate.ToUniversalTime().ToString('o') }}}"
    writer_pattern = '(?:^|[\\\\/\\s\"])(?:run_interactive_game|interactive_ui_driver|render_ui_popup)\\.py(?:[\\s\"]|$)'
    command = ("$ErrorActionPreference='Stop'; $p=@(Get-Process | Where-Object { "
               "$_.ProcessName -match '^(ZeroSisHost|BitmapRenderer|UiPixelScene)' -or "
               "($_.Path -and $_.Path.StartsWith($env:ZS_FONT_ROOT, [StringComparison]::OrdinalIgnoreCase)) }); "
               "$writers=@(Get-CimInstance Win32_Process | Where-Object { "
               "$_.ProcessId -ne [int]$env:ZS_FONT_PID -and $_.Name -match '^python(w|[0-9.]*)?\\.exe$' -and "
               "(!$_.CommandLine -or $_.CommandLine -match '" + writer_pattern + "') }); "
               "$found=@($p | Select-Object Id,ProcessName,Path); "
               "$found+=@($writers | Select-Object @{n='Id';e={$_.ProcessId}},@{n='ProcessName';e={$_.Name}},"
               + creation + ",@{n='Reason';e={if (!$_.CommandLine) {'PYTHON_COMMAND_LINE_UNAVAILABLE'} "
               "else {'PYTHON_RUNTIME_WRITER'}}}); "
               "ConvertTo-Json -Compress -InputObject $found")
    recheck = ("$ErrorActionPreference='Stop'; $live=@(Get-CimInstance Win32_Process -Filter "
               "('ProcessId = ' + [int]$env:ZS_FONT_RECHECK_PID)); $found=@($live | Select-Object "
               "@{n='Id';e={$_.ProcessId}},@{n='ProcessName';e={$_.Name}}," + creation + ","
               "@{n='Reason';e={if (!$_.CreationDate -or !$_.Name) {'PROCESS_IDENTITY_UNAVAILABLE'} "
               "elseif ($_.Name -match '^(ZeroSisHost|BitmapRenderer|UiPixelScene)' -or "
               "($_.ExecutablePath -and $_.ExecutablePath.StartsWith($env:ZS_FONT_ROOT, [StringComparison]::OrdinalIgnoreCase))) "
               "{'PROJECT_NATIVE_PROCESS'} elseif ($_.Name -match '^python(w|[0-9.]*)?\\.exe$') { "
               "if (!$_.CommandLine) {'PYTHON_COMMAND_LINE_UNAVAILABLE'} "
               "elseif ($_.CommandLine -match '" + writer_pattern + "') {'PYTHON_RUNTIME_WRITER'} "
               "else {'KNOWN_NON_WRITER'} } elseif (!$_.ExecutablePath) {'PROCESS_IDENTITY_UNAVAILABLE'} "
               "else {'KNOWN_NON_WRITER'} }}); ConvertTo-Json -Compress -InputObject $found")
    active, exited = [], 0
    for candidate in process_query(command, root):
        if not candidate.get('Reason', '').startswith('PYTHON_'):
            active.append(candidate)
            continue
        pid = candidate.get('Id')
        require(isinstance(pid, int) and pid > 0, 'Invalid candidate process identity')
        current = process_query(recheck, root, ZS_FONT_RECHECK_PID=str(pid))
        if not current:
            exited += 1
            continue
        require(len(current) == 1 and current[0].get('Id') == pid, 'Exact PID recheck was ambiguous')
        live = current[0]
        live['RecheckIdentity'] = ('SAME_INSTANCE' if live.get('CreationTime') and
                                   live['CreationTime'] == candidate.get('CreationTime') else 'REUSED_OR_UNKNOWN')
        if live.get('Reason') != 'KNOWN_NON_WRITER' or not live.get('CreationTime'):
            active.append(live)
    require(active == [], 'Project/native process is active: ' + json.dumps(active))
    return {'status': 'NO_ACTIVE_PROJECT_NATIVE_PROCESS', 'exited_candidates_rechecked': exited, 'utc': now()}


def now():
    return datetime.now(timezone.utc).isoformat()


def no_active_compression(root=PROJECT):
    command = ("$ErrorActionPreference='Stop'; $found=@(Get-CimInstance Win32_Process | Where-Object { "
               "$_.ProcessId -ne $PID -and ($_.Name -match '^(compact|compress|fsutil)\\.exe$' -or "
               "($_.CommandLine -and $_.CommandLine -match '(?:^|[\\\\/\\s\"])(?:compact|compress|fsutil)\\.exe(?:[\\s\"]|$)')) "
               "} | Select-Object @{n='Id';e={$_.ProcessId}},Name,CreationDate); "
               "ConvertTo-Json -Compress -InputObject $found")
    active = process_query(command, root)
    require(active == [], 'Compression process is active: ' + json.dumps(active))
    return {'status': 'NO_ACTIVE_STANDARD_COMPRESSION_PROCESS', 'utc': now()}


def check_protection(reference, root=PROJECT):
    path = checked(reference['path'], root)
    require(digest(path) == reference['sha256'], 'Protection ledger changed')
    value = read_json(path)
    require(Path(value['root']) == root and value['files'], 'Protection ledger root or rows invalid')
    for row in value['files']:
        candidate = root / row['path']
        # External originals are read-only guards, never mutation candidates.
        p = checked(candidate, root if candidate.is_relative_to(root) else Path(candidate.anchor))
        actual = full_record(p)
        for key in ('bytes', 'sha256', 'device', 'file_id', 'mtime_ns', 'attributes'):
            require(actual[key] == row[key], 'Protected file changed: ' + str(p) + ' (' + key + ')')
    return len(value['files'])


def discover(root=PROJECT):
    runtime = checked(root / 'Build/InteractiveGameRuntime', root)
    runs, manifests, targets, held = [], [], {}, []
    for run in children(runtime):
        checked(run, root)
        require(RUN.fullmatch(run.name) and os.path.isdir(io_path(run)), 'Unexpected runtime entry: ' + str(run))
        runs.append(str(run))
        session_root = run / 'sessions'
        if not os.path.exists(io_path(session_root)):
            continue
        checked(session_root, root)
        for session in children(session_root):
            checked(session, root)
            require(SESSION.fullmatch(session.name) and os.path.isdir(io_path(session)), 'Unexpected session entry')
            for scene in children(session):
                if not SCENE.fullmatch(scene.name):
                    continue
                checked(scene, root)
                manifest = scene / 'scene_manifest.json'
                if not os.path.isfile(io_path(manifest)):
                    held.append({'path': str(scene), 'reason': 'No scene manifest; no candidates selected'})
                    continue
                checked(manifest, root)
                doc = read_json(manifest)
                manifests.append({'path': str(manifest), 'sha256': digest(manifest)})
                for font in doc.get('font_sources', []):
                    for sheet in font.get('sheets', []):
                        p = target_path(Path(sheet['path']), root)
                        require(p.parent == scene / 'textures', 'Manifest font target belongs to a different scene')
                        expected = sheet.get('sha256')
                        require(isinstance(expected, str) and SHA.fullmatch(expected) and
                                expected == sheet.get('source_sha256'), 'Font source/output hashes disagree')
                        require(Path(sheet['source_path']).name == p.name, 'Font source/output basenames disagree')
                        if str(p) in targets:
                            require(targets[str(p)]['sha256'] == expected, 'Conflicting font declarations')
                            continue
                        row = full_record(p)
                        require(row['sha256'] == expected, 'Font bytes differ from manifest: ' + str(p))
                        with open(io_path(p), 'rb') as stream:
                            require(stream.read(4) == b'DDS ', 'Font file is not a DDS payload')
                        row['manifest'] = str(manifest)
                        row['font_id'] = font['font_id']
                        row['source_path_read_only_provenance'] = sheet['source_path']
                        targets[str(p)] = row
    return runs, manifests, list(targets.values()), held


def group_plan(rows, root=PROJECT):
    eligible, held, groups = {}, [], []
    for row in rows:
        if row['links'] != 1:
            held.append({'path': row['path'], 'reason': 'Already shared or externally linked; not modified'})
        elif row['attributes'] & READONLY:
            held.append({'path': row['path'], 'reason': 'Readonly independent copy; separate replacement policy required'})
        else:
            eligible.setdefault((row['sha256'], row['bytes']), []).append(row)
    assignments = []
    for (sha, size), members in sorted(eligible.items()):
        if len(members) < 2:
            held.append({'path': members[0]['path'], 'reason': 'No duplicate single-link payload'})
            continue
        count = math.ceil(len(members) / MEMBERS_PER_SHARD)
        require(count <= MAX_SHARDS, 'Payload needs too many cache shards')
        ordered = sorted(members, key=lambda row: row['path'])
        chunks = [ordered[index:index + MEMBERS_PER_SHARD] for index in range(0, len(ordered), MEMBERS_PER_SHARD)]
        for index, chunk in enumerate(chunks):
            source = chunk[0]
            anchor = root / 'Build/RuntimeInputCache/ui-font-atlases' / sha[:2] / sha / f'shard-{index:04d}.dds'
            checked(anchor, root, missing=True)
            require(not os.path.lexists(io_path(anchor)), 'Cache shard already exists; require a fresh compatible plan')
            group = {'anchor': str(anchor), 'source': source['path'], 'sha256': sha, 'bytes': size,
                     'members': len(chunk), 'final_links': len(chunk) + 1,
                     'planned_cache_allocated_bytes_upper_estimate': size,
                     'canonical_mtime_policy': 'New cache publication timestamp; individual prior mtimes are not preserved',
                     'canonical_attributes_policy': 'Readonly cache payload; NTFS compression may differ from each old file'}
            groups.append(group)
            for row in chunk:
                assignments.append({**row, 'anchor': str(anchor)})
    return groups, assignments, held


def write_plan(output, protections, root=PROJECT):
    print(json.dumps({'event': 'FONT_DEDUP_PLAN_START', 'pid': os.getpid(), 'utc': now(),
                      'output': str(output), 'mode': 'FULL_HASH_READ_ONLY_TARGET_SCAN'}), flush=True)
    process = no_active_work(root)
    output = checked(output, root / 'evidence/storage/font_dds_dedup', missing=True)
    require(not os.path.exists(io_path(output)), 'Plan output already exists')
    protected = [{'path': str(checked(p, root)), 'sha256': digest(p)} for p in protections]
    protected_count = sum(check_protection(reference, root) for reference in protected)
    runs, manifests, rows, held = discover(root)
    groups, assignments, additional = group_plan(rows, root)
    held.extend(additional)
    require(len({(row['device'], row['file_id']) for row in assignments}) == len(assignments),
            'Single-link targets unexpectedly share an identity')
    for row in rows:
        current = snapshot(Path(row['path']))
        require(current == {key: row[key] for key in current},
                'Candidate metadata changed while planning')
    no_active_work(root)
    os.makedirs(io_path(output))
    ledger = output / 'targets.jsonl.gz'
    with open(io_path(ledger), 'xb') as raw:
        with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as compressed:
            for row in assignments:
                compressed.write((json.dumps(row, separators=(',', ':')) + '\n').encode())
    old_allocation = sum(row['allocated_bytes'] for row in assignments)
    plan = {'schema': SCHEMA, 'status': 'PLAN_ONLY_FULL_HASH_VERIFIED', 'utc': now(), 'root': str(root),
            'tool': {'path': str(Path(__file__).resolve()), 'sha256': digest(Path(__file__))},
            'cache_helper': {'path': str(root / 'tools/civ5_ui_assets.py'), 'sha256': digest(root / 'tools/civ5_ui_assets.py')},
            'process_guard': process, 'runtime_paths': runs, 'runtime_count': len(runs),
            'protection': protected, 'protected_files': protected_count,
            'ledger': {'path': str(ledger), 'sha256': digest(ledger)},
            'manifests': manifests, 'verified_font_files': len(rows), 'target_files': len(assignments),
            'new_cache_shards': len(groups), 'replacements': len(assignments),
            'old_unique_allocated_bytes': old_allocation,
            'planned_cache_allocated_bytes_upper_estimate': sum(group['bytes'] for group in groups),
            'expected_file_allocation_reduction_bytes': old_allocation - sum(group['bytes'] for group in groups),
            'mtime_changes_expected': len(assignments),
            'groups': groups, 'held': held,
            'metadata_contract': 'Target paths and bytes remain identical. Each shard shares a newly published cache identity, mtime, read-only flag and compression state. Original per-file metadata remains in the sealed ledger; compressed inputs may become uncompressed shared cache files. Non-target protection metadata must remain identical.',
            'limits': ['File allocation excludes directory/MFT overhead and is not a volume-free-space promise.',
                       'Reduction estimates cover DDS identities only; new small lock/journal/plan files are excluded and require a final workspace audit.',
                       'Existing cache shards require a new compatible plan; this plan never overwrites a cache anchor.',
                       'Only manifest-declared, full-hash-matching, single-link fonts are changed.',
                       'Temporary old/new links are removed on success or pending-operation recovery; permanent evidence is outside sessions.']}
    path = output / 'plan.json'
    with open(io_path(path), 'x', encoding='utf8') as stream:
        json.dump(plan, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'plan': str(path), 'sha256': digest(path), 'targets': len(assignments),
                      'replacements': plan['replacements'], 'shards': len(groups),
                      'expected_file_allocation_reduction_bytes': plan['expected_file_allocation_reduction_bytes'],
                      'held': len(held), 'runtime_count': len(runs)}))


def load_plan(path, approved_sha, root=PROJECT, *, recovering=False, historical_tool=None):
    path = checked(path, root / 'evidence/storage/font_dds_dedup')
    require(SHA.fullmatch(approved_sha) and digest(path) == approved_sha, 'Approved plan SHA does not match')
    plan = read_json(path)
    require(plan['schema'] == SCHEMA and Path(plan['root']) == root, 'Wrong plan schema/root')
    tool = Path(__file__) if historical_tool is None else checked(historical_tool, root / 'evidence/storage/font_dds_dedup')
    require(plan['tool']['sha256'] == digest(tool), 'Tool changed after plan generation')
    require(plan['cache_helper']['sha256'] == digest(checked(plan['cache_helper']['path'], root)), 'Cache helper changed after plan generation')
    ledger = checked(plan['ledger']['path'], path.parent)
    require(digest(ledger) == plan['ledger']['sha256'], 'Target ledger changed')
    with gzip.open(io_path(ledger), 'rt', encoding='utf8') as stream:
        rows = [json.loads(line) for line in stream]
    require(len(rows) == plan['target_files'] and len({row['path'] for row in rows}) == len(rows), 'Target count/uniqueness changed')
    for row in rows:
        target_path(row['path'], root, missing=recovering)
    for group in plan['groups']:
        anchor = checked(group['anchor'], root / 'Build/RuntimeInputCache/ui-font-atlases', missing=True)
        sha = group['sha256']
        require(SHA.fullmatch(sha) and anchor.parent.name == sha and anchor.parent.parent.name == sha[:2] and
                re.fullmatch(r'shard-00[0-5][0-9]\.dds|shard-006[0-3]\.dds', anchor.name), 'Invalid cache shard path')
        members = [row for row in rows if row['anchor'] == str(anchor)]
        require(1 <= len(members) <= MEMBERS_PER_SHARD and len(members) == group['members'] and
                any(row['path'] == group['source'] for row in members) and
                all(row['sha256'] == sha and row['bytes'] == group['bytes'] for row in members), 'Invalid shard assignments')
    require({row['anchor'] for row in rows} == {g['anchor'] for g in plan['groups']}, 'Unassigned shard')
    return path, plan, rows


def read_ledger(reference, root=PROJECT):
    path = checked(reference['path'], root / 'evidence/storage/font_dds_dedup')
    require(digest(path) == reference['sha256'], 'Continuation ledger changed')
    with gzip.open(io_path(path), 'rt', encoding='utf8') as stream:
        return [json.loads(line) for line in stream]


def artifact(path):
    return {'path': str(path), 'sha256': digest(path)}


def check_completed(plan, root=PROJECT):
    """Hash each shared identity once, then verify every preserved alias."""
    continuation = plan.get('continuation')
    if not continuation:
        return [], {}
    for record in continuation['history']:
        require(digest(checked(record['path'], root / 'evidence/storage/font_dds_dedup')) == record['sha256'],
                'Original continuation history changed')
    anchors = {}
    for expected in continuation['existing_anchors']:
        p = checked(expected['path'], root / 'Build/RuntimeInputCache/ui-font-atlases')
        current = full_record(p)
        require(all(current[key] == expected[key] for key in current if key != 'links') and
                current['links'] <= LINK_CAP, 'Preserved canonical identity or payload changed')
        anchors[str(p)] = current
    rows = read_ledger(continuation['completed_ledger'], root)
    require(len(rows) == continuation['completed_files'] and len({r['path'] for r in rows}) == len(rows),
            'Preserved alias ledger count differs')
    for row in rows:
        current = snapshot(target_path(row['path'], root))
        require(all(current[key] == row[key] for key in current if key != 'links') and
                row['anchor'] in anchors and same_identity(current, anchors[row['anchor']]) and
                row['sha256'] == anchors[row['anchor']]['sha256'], 'Preserved completed alias changed')
    return rows, anchors


def compression_only_refresh(before, current):
    return (not before['attributes'] & COMPRESSED and
            current['attributes'] == before['attributes'] | COMPRESSED and
            0 < current['allocated_bytes'] < before['allocated_bytes'] and
            all(current[key] == before[key] for key in current if key not in ('attributes', 'allocated_bytes')))


def partition_remaining(plan, rows, events, root=PROJECT, *, accept_compression_only=False):
    require(events and events[-1]['event'] == 'APPLY_FAILED', 'Previous apply did not stop with a recorded failure')
    completed_paths = [e['path'] for e in events if e['event'] == 'REPLACE_DONE']
    require(completed_paths and completed_paths == [row['path'] for row in rows[:len(completed_paths)]],
            'Completed operations are not an exact prefix')
    for kind in ('REPLACE_BEGIN', 'REPLACE_PREPARED', 'REPLACE_VERIFIED'):
        require([e['path'] for e in events if e['event'] == kind] == completed_paths,
                'Pending or recovered operations need separate review before continuation')
    preserved, anchors = check_completed(plan, root)
    for group in plan['groups']:
        p = checked(group['anchor'], root / 'Build/RuntimeInputCache/ui-font-atlases', missing=True)
        if os.path.exists(io_path(p)):
            value = full_record(p)
            require(value['sha256'] == group['sha256'] and value['bytes'] == group['bytes'] and
                    value['attributes'] & READONLY, 'Existing anchor payload differs')
            anchors[str(p)] = value
    remaining, compression_changes = [], []
    for index, row in enumerate(rows):
        p = target_path(row['path'], root)
        require(not any(os.path.exists(io_path(t)) for t in temp_paths(p, events[0]['plan_sha256'])),
                'Previous plan still has temporary links')
        if index < len(completed_paths):
            current = snapshot(p)
            require(row['anchor'] in anchors and same_identity(current, anchors[row['anchor']]) and
                    anchors[row['anchor']]['sha256'] == row['sha256'], 'Completed target is not its recorded cache identity')
            preserved.append({'path': str(p), **current, 'sha256': row['sha256'], 'anchor': row['anchor']})
        else:
            current = full_record(p)
            if not all(current[key] == row[key] for key in current):
                require(accept_compression_only and compression_only_refresh(row, current),
                        'Remaining original changed since its full-hash plan: ' + str(p))
                compression_changes.append({'before': {key: row[key] for key in current}, 'after': current})
            remaining.append({**row, **current})
    for anchor, value in anchors.items():
        require(value['links'] == 1 + sum(row['anchor'] == anchor for row in preserved),
                'Anchor has an unaccounted hardlink')
    groups = []
    for old in plan['groups']:
        members = [row for row in remaining if row['anchor'] == old['anchor']]
        if not members:
            continue
        existing = anchors.get(old['anchor'])
        links = existing['links'] if existing else 1
        require(links + len(members) <= LINK_CAP, 'Remaining shard capacity is insufficient')
        groups.append({**old, 'source': members[0]['path'], 'members': len(members),
                       'starting_links': links, 'final_links': links + len(members),
                       'new_cache': existing is None})
    return remaining, preserved, list(anchors.values()), groups, compression_changes


def write_remaining_plan(old_path, approved_sha, historical_tool, output, root=PROJECT, *, accept_compression_only=False):
    print(json.dumps({'event': 'FONT_DEDUP_REMAINING_PLAN_START', 'pid': os.getpid(), 'utc': now(),
                      'output': str(output), 'mode': 'READ_ONLY_REMAINING_FULL_HASH'}), flush=True)
    process = no_active_work(root)
    compression_guard = no_active_compression(root) if accept_compression_only else None
    old_path, old, rows = load_plan(old_path, approved_sha, root, historical_tool=historical_tool)
    output = checked(output, root / 'evidence/storage/font_dds_dedup', missing=True)
    require(not os.path.exists(io_path(output)), 'Continuation output already exists')
    for reference in old['protection']:
        check_protection(reference, root)
    require([str(p) for p in children(root / 'Build/InteractiveGameRuntime')] == old['runtime_paths'], 'Runtime inventory changed')
    for record in old['manifests']:
        require(digest(checked(record['path'], root)) == record['sha256'], 'Scene manifest changed')
    old_journal = checked(old_path.parent / 'apply-journal.jsonl', root)
    journal_ref = artifact(old_journal)
    with open(io_path(old_journal), encoding='utf8') as stream:
        events = [json.loads(line) for line in stream]
    require(events[0]['event'] == 'APPLY_START' and events[0]['plan_sha256'] == approved_sha,
            'Journal is not for the sealed parent plan')
    remaining, preserved, anchors, groups, compression_changes = partition_remaining(
        old, rows, events, root, accept_compression_only=accept_compression_only)
    require(remaining, 'No remaining targets')
    no_active_work(root)
    if accept_compression_only:
        no_active_compression(root)
    require(digest(old_journal) == journal_ref['sha256'], 'Parent journal changed during continuation planning')
    os.makedirs(io_path(output))
    references = []
    ledgers = [('targets.jsonl.gz', remaining), ('completed.jsonl.gz', preserved)]
    if compression_changes:
        ledgers.append(('compression-refresh.jsonl.gz', compression_changes))
    for name, records in ledgers:
        path = output / name
        with open(io_path(path), 'xb') as raw:
            with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0) as compressed:
                for row in records:
                    compressed.write((json.dumps(row, separators=(',', ':')) + '\n').encode())
        references.append(artifact(path))
    history = old.get('continuation', {}).get('history', []) + [artifact(old_path), old['ledger'], journal_ref, artifact(historical_tool)]
    if old.get('continuation'):
        history.append(old['continuation']['completed_ledger'])
    if compression_changes:
        history.append(references[2])
    old_bytes = sum(row['allocated_bytes'] for row in remaining)
    new_bytes = sum(g['bytes'] for g in groups if g['new_cache'])
    plan = {**old, 'status': 'REMAINING_PLAN_ONLY_FULL_HASH_VERIFIED', 'utc': now(),
            'process_guard': process,
            'tool': artifact(Path(__file__).resolve()), 'ledger': references[0],
            'verified_font_files': len(remaining), 'target_files': len(remaining), 'replacements': len(remaining),
            'new_cache_shards': sum(g['new_cache'] for g in groups), 'groups': groups,
            'old_unique_allocated_bytes': old_bytes, 'planned_cache_allocated_bytes_upper_estimate': new_bytes,
            'expected_file_allocation_reduction_bytes': old_bytes - new_bytes, 'mtime_changes_expected': len(remaining),
            'continuation': {'parent_plan': artifact(old_path), 'history': history,
                'completed_ledger': references[1], 'completed_files': len(preserved), 'existing_anchors': anchors,
                'original_target_count': old.get('continuation', {}).get('original_target_count', old['target_files'])}}
    if accept_compression_only:
        plan['continuation']['compression_refresh'] = {
            'guard': compression_guard, 'files': len(compression_changes),
            'ledger': references[2] if compression_changes else None,
            'preexisting_allocation_reduction_bytes': sum(
                row['before']['allocated_bytes'] - row['after']['allocated_bytes'] for row in compression_changes),
            'contract': 'Full SHA-256, path, identity, bytes, mtime and link count are unchanged. Only exact addition of FILE_ATTRIBUTE_COMPRESSED and lower allocation are accepted during plan generation. Apply uses the strict refreshed ledger. Preexisting compression savings are excluded from deduplication savings.'}
    require(len(remaining) + len(preserved) == plan['continuation']['original_target_count'], 'Original coverage is incomplete')
    path = output / 'plan.json'
    with open(io_path(path), 'x', encoding='utf8') as stream:
        json.dump(plan, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'plan': str(path), 'sha256': digest(path), 'remaining': len(remaining),
                      'completed_preserved': len(preserved), 'new_cache_shards': plan['new_cache_shards'],
                      'expected_file_allocation_reduction_bytes': old_bytes - new_bytes}), flush=True)


def journal(path, event):
    with open(io_path(path), 'a', encoding='utf8') as stream:
        stream.write(json.dumps({'utc': now(), **event}, separators=(',', ':')) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def temp_paths(target, approved_sha):
    name_key = hashlib.sha256(target.name.encode('utf8')).hexdigest()[:8]
    prefix = '.fd-' + approved_sha[:8] + '-' + name_key
    return target.with_name(prefix + '.new'), target.with_name(prefix + '.old')


def remove_owned_link(path, expected):
    require(same_identity(snapshot(path), expected), 'Temporary identity differs; refusing removal')
    if os.name != 'nt':
        os.unlink(io_path(path))
        return
    # Same Windows primitive as prune_superseded_runtime_artifacts.py: remove
    # only this directory entry, preserving readonly flags on every sibling.
    from ctypes import wintypes
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                  wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    kernel.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.SetFileInformationByHandle.restype = wintypes.BOOL
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateFileW(io_path(path), 0x10000, 7, None, 3, 0x00200000, None)
    require(handle != ctypes.c_void_p(-1).value, 'Cannot open temporary link for disposition')
    try:
        flags = wintypes.DWORD(0x13)  # DELETE | POSIX_SEMANTICS | IGNORE_READONLY_ATTRIBUTE
        if not kernel.SetFileInformationByHandle(handle, 21, ctypes.byref(flags), 4):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        kernel.CloseHandle(handle)


def verify_replacement(target, anchor, expected_sha):
    require(same_identity(snapshot(target), snapshot(anchor)) and digest(target) == expected_sha,
            'Replacement verification failed')


def restore_pending(row, approved_sha, root=PROJECT):
    """Restore an interrupted old identity; completed entries remain valid shared files."""
    target = target_path(row['path'], root, missing=True)
    fresh, backup = temp_paths(target, approved_sha)
    anchor = checked(row['anchor'], root / 'Build/RuntimeInputCache/ui-font-atlases', missing=True)
    for p in (fresh, backup):
        checked(p, target.parent, missing=True)
    if os.path.exists(io_path(backup)):
        old = full_record(backup)
        require(same_identity(old, row) and old['sha256'] == row['sha256'], 'Backup is not the recorded original')
        current = full_record(target) if os.path.exists(io_path(target)) else None
        require(current is None or current['sha256'] == row['sha256'], 'Current target bytes changed; preserve all evidence')
        if current is None or not same_identity(current, old):
            if current is not None:
                require(os.path.exists(io_path(anchor)) and same_identity(current, snapshot(anchor)), 'Target has unexpected identity')
                remove_owned_link(target, current)
            os.replace(io_path(backup), io_path(target))
        else:
            remove_owned_link(backup, old)
    if os.path.exists(io_path(fresh)):
        require(os.path.exists(io_path(anchor)) and same_identity(snapshot(fresh), snapshot(anchor)), 'Unexpected new temporary link')
        remove_owned_link(fresh, snapshot(anchor))


def verify_inputs(plan, rows, root=PROJECT, *, resumed=False):
    no_active_work(root)
    for reference in plan['protection']:
        check_protection(reference, root)
    for run in plan['runtime_paths']:
        checked(run, root / 'Build/InteractiveGameRuntime')
    require([str(p) for p in children(root / 'Build/InteractiveGameRuntime')] == plan['runtime_paths'],
            'Runtime inventory changed since the plan')
    for record in plan['manifests']:
        require(digest(checked(record['path'], root)) == record['sha256'], 'Scene manifest changed')
    completed, existing = check_completed(plan, root)
    alias_counts = {}
    for row in completed:
        alias_counts[row['anchor']] = alias_counts.get(row['anchor'], 0) + 1
    for row in rows:
        actual = full_record(target_path(row['path'], root))
        require(actual['bytes'] == row['bytes'] and actual['sha256'] == row['sha256'], 'Target payload changed')
        anchor = Path(row['anchor'])
        shared = resumed and os.path.exists(io_path(anchor)) and same_identity(actual, snapshot(anchor))
        if shared:
            alias_counts[str(anchor)] = alias_counts.get(str(anchor), 0) + 1
            canonical = snapshot(anchor)
            require(actual['mtime_ns'] == canonical['mtime_ns'] and actual['attributes'] == canonical['attributes'] and actual['attributes'] & READONLY, 'Shared metadata changed')
        else:
            require(all(actual[key] == row[key] for key in snapshot(Path(row['path']))), 'Target metadata changed')
    for group in plan['groups']:
        anchor = checked(group['anchor'], root / 'Build/RuntimeInputCache/ui-font-atlases', missing=True)
        if os.path.exists(io_path(anchor)):
            require(resumed or str(anchor) in existing, 'Cache appeared since plan')
            current = full_record(anchor)
            require(current['sha256'] == group['sha256'] and current['bytes'] == group['bytes'] and
                    current['attributes'] & READONLY and current['links'] <= LINK_CAP, 'Existing cache anchor differs')
            require(current['links'] == alias_counts.get(str(anchor), 0) + 1, 'Cache has unaccounted aliases')
    for path, current in existing.items():
        require(current['links'] == alias_counts.get(path, 0) + 1, 'Preserved cache has unaccounted aliases')


def apply_plan(path, approved_sha, *, recover=False, root=PROJECT):
    path, plan, rows = load_plan(path, approved_sha, root, recovering=recover)
    log = path.parent / 'apply-journal.jsonl'
    no_active_work(root)
    for reference in plan['protection']:
        check_protection(reference, root)
    resumed = os.path.exists(io_path(log))
    if recover:
        require(resumed, 'No apply journal exists to recover')
        for row in rows:
            restore_pending(row, approved_sha, root)
        for reference in plan['protection']:
            check_protection(reference, root)
        journal(log, {'event': 'PENDING_OPERATIONS_RECOVERED', 'plan_sha256': approved_sha})
        print(json.dumps({'status': 'PENDING_OPERATIONS_RECOVERED', 'journal': str(log)}))
        return
    require(not any(os.path.exists(io_path(p)) for row in rows for p in temp_paths(Path(row['path']), approved_sha)),
            'Pending temporary links exist; use recover with the same approved plan first')
    verify_inputs(plan, rows, root, resumed=resumed)
    journal(log, {'event': 'APPLY_START', 'plan_sha256': approved_sha, 'resumed': resumed})
    from civ5_ui_assets import materialize_sharded_payload
    cache_root = root / 'Build/RuntimeInputCache/ui-font-atlases'
    changed = 0
    try:
        for index, row in enumerate(rows):
            target = target_path(row['path'], root)
            anchor = checked(row['anchor'], cache_root, missing=True)
            if os.path.exists(io_path(anchor)) and same_identity(snapshot(target), snapshot(anchor)):
                continue
            if index % 100 == 0:
                no_active_work(root)
            actual = full_record(target)
            require(all(actual[key] == row[key] for key in snapshot(target)) and actual['sha256'] == row['sha256'], 'Target changed immediately before replace')
            require(not os.path.exists(io_path(anchor)) or snapshot(anchor)['links'] < LINK_CAP, 'Cache hardlink cap reached')
            fresh, backup = temp_paths(target, approved_sha)
            checked(fresh, target.parent, missing=True)
            checked(backup, target.parent, missing=True)
            require(not os.path.lexists(io_path(fresh)) and not os.path.lexists(io_path(backup)), 'Temporary path exists')
            journal(log, {'event': 'REPLACE_BEGIN', 'path': str(target), 'anchor': str(anchor), 'old': actual})
            try:
                with open(io_path(target), 'rb') as stream:
                    payload = stream.read()
                require(hashlib.sha256(payload).hexdigest() == row['sha256'] and len(payload) == row['bytes'], 'Publisher payload changed')
                published = materialize_sharded_payload(payload, fresh, cache_root)
                require(published['cache_file'] == str(anchor), 'Publisher selected a different planned shard')
                os.link(io_path(target), io_path(backup))
                require(snapshot(anchor)['links'] <= LINK_CAP, 'Concurrent shard cap change')
                journal(log, {'event': 'REPLACE_PREPARED', 'path': str(target), 'fresh': str(fresh), 'backup': str(backup)})
                os.replace(io_path(fresh), io_path(target))
                verify_replacement(target, anchor, row['sha256'])
                journal(log, {'event': 'REPLACE_VERIFIED', 'path': str(target), 'after': snapshot(target)})
                remove_owned_link(backup, actual)
                journal(log, {'event': 'REPLACE_DONE', 'path': str(target)})
                changed += 1
            except BaseException:
                restore_pending(row, approved_sha, root)
                journal(log, {'event': 'REPLACE_RECOVERED_AFTER_ERROR', 'path': str(target)})
                raise
    except BaseException as error:
        journal(log, {'event': 'APPLY_FAILED', 'error': str(error), 'completed_this_attempt': changed})
        raise
    verify_inputs(plan, rows, root, resumed=True)
    require(not any(os.path.exists(io_path(p)) for row in rows for p in temp_paths(Path(row['path']), approved_sha)), 'Temporary links remain')
    result = {'status': 'PASS_CONTENT_PRESERVING_FONT_DEDUP', 'utc': now(), 'plan_sha256': approved_sha,
              'targets_verified': len(rows), 'replacements_this_attempt': changed,
              'protected_guard_rows_verified': sum(check_protection(reference, root) for reference in plan['protection']),
              'retained_unique_allocated_bytes': sum(snapshot(Path(g['anchor']))['allocated_bytes'] for g in plan['groups']),
              'new_cache_unique_allocated_bytes': sum(snapshot(Path(g['anchor']))['allocated_bytes'] for g in plan['groups'] if g.get('new_cache', True)),
              'old_unique_allocated_bytes': plan['old_unique_allocated_bytes'],
              'temporary_links_remaining': 0, 'metadata_changes': plan['metadata_contract']}
    result['preserved_completed_targets_verified'] = plan.get('continuation', {}).get('completed_files', 0)
    result['original_total_targets_verified'] = len(rows) + result['preserved_completed_targets_verified']
    result['file_allocation_reduction_bytes'] = result['old_unique_allocated_bytes'] - result['new_cache_unique_allocated_bytes']
    journal(log, {'event': 'APPLY_COMPLETE', **result})
    with open(io_path(path.parent / 'result.json'), 'w', encoding='utf8') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('plan', 'remaining-plan', 'apply', 'recover', 'verify'))
    parser.add_argument('--output', type=Path)
    parser.add_argument('--protection', type=Path, action='append')
    parser.add_argument('--plan', type=Path)
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--sealed-tool', type=Path)
    parser.add_argument('--accept-compression-only', action='store_true')
    args = parser.parse_args()
    require(not args.accept_compression_only or args.mode == 'remaining-plan',
            '--accept-compression-only is restricted to remaining-plan')
    if args.mode == 'plan':
        require(args.output and args.protection, 'plan requires --output and --protection')
        write_plan(args.output.absolute(), [p.absolute() for p in args.protection])
    elif args.mode == 'remaining-plan':
        require(args.plan and args.approved_plan_sha256 and args.output and args.sealed_tool,
                'remaining-plan requires parent plan SHA, output and its sealed tool backup')
        write_remaining_plan(args.plan.absolute(), args.approved_plan_sha256,
                             args.sealed_tool.absolute(), args.output.absolute(),
                             accept_compression_only=args.accept_compression_only)
    else:
        require(args.plan and args.approved_plan_sha256, 'Explicit approved plan SHA is required')
        if args.mode == 'verify':
            _, plan, rows = load_plan(args.plan.absolute(), args.approved_plan_sha256)
            verify_inputs(plan, rows, resumed=False)
            print(json.dumps({'status': 'PASS_READ_ONLY_APPLY_PREFLIGHT', 'targets': len(rows)}))
        else:
            from civ5_ui_assets import _font_cache_lock
            load_plan(args.plan.absolute(), args.approved_plan_sha256, recovering=args.mode == 'recover')
            no_active_work()
            with _font_cache_lock(PROJECT / 'Build/RuntimeInputCache/ui-font-atlases'):
                apply_plan(args.plan.absolute(), args.approved_plan_sha256, recover=args.mode == 'recover')


if __name__ == '__main__':
    main()
