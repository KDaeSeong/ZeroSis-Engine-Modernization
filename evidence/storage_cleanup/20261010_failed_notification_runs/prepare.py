"""One-shot, plan-only inventory of two terminal NotificationPanel failures.

Writes only this new evidence directory. No unlink/rmdir, compression of live
files, source edit, build, or native launch exists in this entry point. A later
reviewed apply must re-observe identities, aliases, use, and replacement proof.
"""
from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
EXPECTED_ROOT = Path(r"C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization")
HELPER = ROOT / 'tools/prune_superseded_runtime_artifacts.py'
HELPER_SHA = '99eed1b129e24139b435feb34e2a88172ba7332ffaf9a3e4d3d20f9dfa177baa'
assert ROOT == EXPECTED_ROOT and OUT == ROOT / 'evidence/storage_cleanup/20261010_failed_notification_runs'
assert hashlib.sha256(HELPER.read_bytes()).hexdigest() == HELPER_SHA
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as p

RUNS = {
    '20261009T144109Z_de7705b9790b': ('a40dbb40ebfb5fe584a9c6547a292810', 3, 1),
    '20261009T145225Z_edf44c8f1c55': ('518548090481356f52fa9dbfc04a32f9', 45, 12),
}
TARGETS = tuple(ROOT / group / run for run in RUNS for group in
                ('Build/InteractiveGameRuntime', 'evidence/interactive_game'))
KEEP_HOSTS = ('20261009T143755Z_7e325ee83c08', '20261009T152915Z_262e1edd772f',
              '20261009T155317Z_8f390480966b')
KEEP_RUNS = ('20261009T153212Z_24547e20f8c7', '20261009T155510Z_59a23754e9cf',
             '20261009T160013Z_804760e7018f')
CPU_ROOTS = ('Build/FoundValueCpuCapture', 'Build/CitySiteCpuCapture', 'Build/FoundValueCpuTrace',
             'evidence/found_value_cpu_capture', 'evidence/city_site_cpu_capture',
             'evidence/found_value_cpu_trace', 'evidence/city_site_cpu_trace')
ROUTES = ('tools/Start-Engine.ps1', 'docs/CONTINUOUS_PLAY.md', 'docs/ENGINE_COMPLETION_STATUS.md', 'AGENTS.md')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def artifact(path):
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': p.digest(path)}


def write_new(name, value, compressed=False):
    path = OUT / name
    p.require(path.parent == OUT, 'Output escaped the exact evidence folder')
    raw = json.dumps(value, ensure_ascii=False, separators=(',', ':') if compressed else None,
                     indent=None if compressed else 2).encode('utf-8') + b'\n'
    with path.open('xb') as stream:
        if compressed:
            with gzip.GzipFile(fileobj=stream, mode='wb', compresslevel=9, mtime=0) as packed:
                packed.write(raw)
        else:
            stream.write(raw)
    return artifact(path)


def inside(path):
    return any(Path(path).is_relative_to(target) for target in TARGETS)


def identity(info):
    return (int(info.st_dev), int(info.st_ino), info.st_size, info.st_mtime_ns,
            info.st_nlink, getattr(info, 'st_file_attributes', 0))


def walk_owned(directory):
    directory = p.boundary(directory)
    pending = [directory]
    while pending:
        current = pending.pop()
        info = current.lstat()
        p.require(stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400,
                  'Reparse/non-directory inside bounded traversal: ' + str(current))
        yield current, info, True
        with os.scandir(current) as entries:
            for entry in entries:
                path = Path(entry.path)
                value = entry.stat(follow_symlinks=False)
                p.require(path.is_relative_to(directory) and not value.st_file_attributes & 0x400,
                          'Traversal escaped root or encountered reparse: ' + str(path))
                if stat.S_ISDIR(value.st_mode):
                    pending.append(path)
                else:
                    p.require(stat.S_ISREG(value.st_mode), 'Nonregular bounded file: ' + str(path))
                    # DirEntry.stat omits the NTFS identity fields on Windows.
                    yield path, p.regular(path), False


def file_row(path, info, hashes, storage):
    key = identity(info)
    if key not in hashes:
        hashes[key] = p.digest(path)
    p.require(identity(p.regular(path)) == key, 'File changed during hashing: ' + str(path))
    pair = key[:2]
    if pair not in storage:
        storage[pair] = p.stored(path)
    return {'path': str(path.relative_to(ROOT)), 'device': key[0], 'file_id': key[1],
            'bytes': key[2], 'mtime_ns': key[3], 'links': key[4], 'attributes': key[5],
            'sha256': hashes[key], 'stored_bytes': storage[pair]}


def process_audit():
    command = "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); @(Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath,CommandLine) | ConvertTo-Json -Compress"
    run = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True,
                         encoding='utf-8', timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    p.require(run.returncode == 0, 'Process audit failed')
    values = json.loads(run.stdout) if run.stdout.strip() else []
    values = values if isinstance(values, list) else [values]
    active = []
    for row in values:
        text = str(row.get('ExecutablePath') or '') + ' ' + str(row.get('CommandLine') or '')
        hits = [identifier for identifier in RUNS if identifier.casefold() in text.casefold()]
        p.require(not hits, 'Exact retirement input is in use: ' + str(row.get('Name')))
        if row.get('Name', '').casefold() in ('zerosishost_x64.exe', 'cl.exe', 'link.exe', 'c1xx.exe', 'ninja.exe'):
            p.require(row.get('CommandLine') and row.get('ExecutablePath'), 'Host/compiler visibility is incomplete')
            active.append({'pid': row['ProcessId'], 'name': row['Name'],
                           'protected_id_hits': [x for x in (*KEEP_HOSTS, *KEEP_RUNS) if x in text]})
    return {'processes_observed': len(values), 'target_process_hits': [],
            'other_active_hosts_or_compilers': active,
            'mode': 'draft-only: unrelated current execution is observed and preserved'}


def hardlink_names(path):
    kernel = p.K
    kernel.FindFirstFileNameW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR]
    kernel.FindFirstFileNameW.restype = wintypes.HANDLE
    kernel.FindNextFileNameW.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR]
    kernel.FindNextFileNameW.restype = wintypes.BOOL
    kernel.FindClose.argtypes = [wintypes.HANDLE]
    kernel.FindClose.restype = wintypes.BOOL
    size = wintypes.DWORD(32768)
    buffer = ctypes.create_unicode_buffer(size.value)
    handle = kernel.FindFirstFileNameW(str(path), 0, ctypes.byref(size), buffer)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    result = []
    try:
        while True:
            result.append(Path(path.anchor) / buffer.value.lstrip('\\'))
            size.value = 32768
            if not kernel.FindNextFileNameW(handle, ctypes.byref(size), buffer):
                p.require(ctypes.get_last_error() == 38, 'Unexpected hardlink enumeration failure')
                break
    finally:
        kernel.FindClose(handle)
    return sorted(set(result), key=lambda item: str(item).casefold())


def link_audit(rows):
    groups = {}
    checked_alias_directories = set()
    for row in rows:
        pair = row['device'], row['file_id']
        group = groups.setdefault(pair, {'sample': row, 'target_paths': []})
        p.require(all(group['sample'][key] == row[key] for key in
                      ('bytes', 'mtime_ns', 'links', 'attributes', 'sha256', 'stored_bytes')),
                  'Target hardlink identity drifted')
        group['target_paths'].append(str(ROOT / row['path']))
    external = []
    for pair, group in groups.items():
        row = group['sample']
        if row['links'] == 1:
            continue
        names = hardlink_names(ROOT / row['path'])
        p.require(len(names) == row['links'], 'Named aliases and link count differ')
        p.require({str(x).casefold() for x in names if inside(x)} ==
                  {x.casefold() for x in group['target_paths']}, 'Target aliases differ from ledger')
        survivors = []
        # One fresh hash per NTFS identity in this phase; every alias still gets
        # its own path, reparse, file identity, size, timestamp and link check.
        phase_sha = None
        for alias in names:
            if inside(alias):
                continue
            p.require(alias == Path(os.path.abspath(alias)), 'External alias is not absolute and normalized')
            # Check every distinct ancestor once in this observation phase;
            # do not repeat full path resolution for thousands of aliases.
            for ancestor in alias.parents:
                if ancestor in checked_alias_directories:
                    break
                ancestor_info = ancestor.lstat()
                p.require(stat.S_ISDIR(ancestor_info.st_mode) and not ancestor_info.st_file_attributes & 0x400,
                          'External alias has a reparse/non-directory ancestor')
                checked_alias_directories.add(ancestor)
            info = p.regular(alias)
            p.require(identity(info) == (pair[0], pair[1], row['bytes'], row['mtime_ns'],
                                        row['links'], row['attributes']), 'External alias metadata differs')
            if phase_sha is None:
                phase_sha = p.digest(alias)
            p.require(phase_sha == row['sha256'] and identity(p.regular(alias)) == identity(info),
                      'External alias hash or identity changed')
            survivors.append({'path': str(alias), 'inside_project': alias.is_relative_to(ROOT),
                              'device': pair[0], 'file_id': pair[1], 'bytes': info.st_size,
                              'mtime_ns': info.st_mtime_ns, 'links': info.st_nlink,
                              'attributes': info.st_file_attributes, 'sha256': phase_sha})
        if survivors:
            external.append({'target_paths': group['target_paths'], 'links_before': row['links'],
                             'links_after_exact_unlinks': row['links'] - len(group['target_paths']),
                             'surviving_aliases': survivors})
    return groups, external


def diagnostic_sources():
    paths = set()
    missing_packets = []
    for run, (session_id, scene, frame) in RUNS.items():
        evidence = ROOT / 'evidence/interactive_game' / run
        for name in ('result.json', 'request.json', 'driver_result.json', 'stdout.log', 'stderr.log',
                     'runner.py', 'notification_panel_timeline.py', 'host_build.json',
                     'interactive_ui_support.json', 'bundle.json', 'attempt.json'):
            paths.add(evidence / name)
        runtime = ROOT / 'Build/InteractiveGameRuntime' / run
        session = runtime / 'sessions' / session_id
        paths.update((session / f'play-ui-{scene}.json',
                      session / 'play-notification-panel' / f'ui-popup-0-frame-{frame}.json',
                      session / 'play-initial-state.txt', session / 'rules.db'))
        support = runtime / 'interactive_ui_support'
        paths.update((support / 'tools').glob('*.py'))
        paths.update((support / 'support_manifest.json', support / 'assets/prepared.json',
                      support / 'assets/inline_icons.json'))
        failure = session / f'play-ui-{scene}'
        for name in ('inline_colors.json', 'inline_icons.json', 'preparation_inputs.json', 'prepare.log'):
            paths.add(failure / name)
        packet = failure / 'scene.packet'
        p.require(not packet.exists(), 'Unexpected failure packet: re-review preservation scope')
        missing_packets.append({'path': str(packet), 'reason': 'Original renderer preparation failed before packet emission'})
        if scene == 45:
            paths.update((session / 'play-ui-42.json', session / 'play-scene-11.json',
                          session / 'play-scene-11.pick', session / 'play-scene-11-gpu.png'))
            for name in ('scene.packet', 'scene_manifest.json', 'driver_record.json',
                         'inline_colors.json', 'inline_icons.json', 'preparation_inputs.json', 'prepare.log'):
                paths.add(session / 'play-ui-42' / name)
    return sorted(paths, key=lambda item: str(item).casefold()), missing_packets


def preserve_diagnostics(rows):
    by_path = {str(ROOT / row['path']): row for row in rows}
    paths, missing_packets = diagnostic_sources()
    blobs, records = {}, []
    for path in paths:
        p.require(inside(path) and str(path) in by_path, 'Diagnostic is not in exact inventoried targets')
        row = by_path[str(path)]
        p.boundary(path)
        p.require(row['bytes'] <= (32 if path.name == 'prepared.json' else 4) * 1024 * 1024,
                  'Diagnostic exceeds its bounded size cap')
        value = path.read_bytes()
        sha = hashlib.sha256(value).hexdigest()
        p.require(len(value) == row['bytes'] and sha == row['sha256'] and
                  identity(p.regular(path)) == (row['device'], row['file_id'], row['bytes'],
                                                row['mtime_ns'], row['links'], row['attributes']),
                  'Diagnostic bytes/identity differ from target inventory')
        blobs.setdefault(sha, base64.b64encode(value).decode('ascii'))
        records.append({'path': row['path'], 'bytes': len(value), 'sha256': sha})
    raw_unique_bytes = sum(len(base64.b64decode(value)) for value in blobs.values())
    p.require(raw_unique_bytes <= 48 * 1024 * 1024, 'Diagnostic archive exceeded 48 MiB raw unique cap')
    result = write_new('diagnostics.json.gz', {'schema': 1, 'encoding': 'base64-original-bytes',
                      'records': records, 'blobs_by_sha256': blobs, 'missing_failure_packets': missing_packets}, True)
    with gzip.open(result['path'], 'rt', encoding='utf-8') as stream:
        restored = json.load(stream)
    for row in restored['records']:
        raw = base64.b64decode(restored['blobs_by_sha256'][row['sha256']], validate=True)
        p.require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                  'Archived diagnostic original-byte restoration failed')
    result.update({'source_records': len(records), 'unique_blobs': len(blobs),
                   'source_bytes': sum(row['bytes'] for row in records),
                   'unique_source_bytes': raw_unique_bytes, 'round_trip': 'PASS_ORIGINAL_BYTES_SHA256',
                   'missing_failure_packets': missing_packets})
    return result


def reference_and_protection_audit():
    paths = set((ROOT / 'evidence').glob('*/*/request.json'))
    paths.update((ROOT / 'evidence/ui_window_host').glob('*/build_result.json'))
    paths.update(ROOT / name for name in ROUTES)
    paths.update((ROOT / 'evidence/notification_panel_scene').glob('*/*.json'))
    documents, holds = [], []
    for path in sorted(paths, key=lambda item: str(item).casefold()):
        if inside(path):
            continue
        p.boundary(path)
        raw = path.read_bytes()
        text = raw.decode('utf-8-sig')
        hits = [run for run in RUNS if run in text]
        row = {'path': str(path.relative_to(ROOT)), 'bytes': len(raw),
               'sha256': hashlib.sha256(raw).hexdigest(), 'target_id_hits': hits}
        documents.append(row)
        if hits:
            holds.append({'path': row['path'], 'ids': hits,
                          'kind': 'execution_dependency' if path.name in ('request.json', 'build_result.json')
                                  else 'historical_evidence_reference_requires_archive_mapping'})
    command = ['rg', '-l', '-F']
    for run in RUNS:
        command.extend(['-e', run])
    command.extend(['tools', 'Tests'])
    probe = subprocess.run(command, cwd=ROOT, capture_output=True, encoding='utf-8', timeout=30,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    p.require(probe.returncode in (0, 1), 'Code reference audit failed')
    for line in probe.stdout.splitlines():
        if line:
            holds.append({'path': line, 'kind': 'code_reference_requires_review'})

    launcher = (ROOT / 'tools/Start-Engine.ps1').read_text(encoding='utf-8-sig')
    manual_ids = list(dict.fromkeys(re.findall(r'\d{8}T\d{6}Z_[0-9a-f]{12}', launcher)))
    p.require(not set(manual_ids) & set(RUNS), 'Manual route points at a deletion target')
    all_runtime_ids = sorted(path.name for path in (ROOT / 'Build/InteractiveGameRuntime').iterdir()
                             if path.is_dir() and path.name not in RUNS)
    all_host_ids = sorted(path.name for path in (ROOT / 'Build/UiWindowHost').iterdir() if path.is_dir())
    p.require(set(KEEP_HOSTS) <= set(all_host_ids) and set(KEEP_RUNS) <= set(all_runtime_ids),
              'An explicitly protected Host/runtime is absent')
    scopes = [ROOT / name for name in ('Source', 'tools', 'Tests', *CPU_ROOTS)]
    scopes += [ROOT / group / item for group, ids in
               (('Build/InteractiveGameRuntime', all_runtime_ids), ('evidence/interactive_game', all_runtime_ids),
                ('Build/UiWindowHost', all_host_ids), ('evidence/ui_window_host', all_host_ids)) for item in ids]
    for scope in scopes:
        p.require(not any(scope.is_relative_to(target) or target.is_relative_to(scope) for target in TARGETS),
                  'Protected scope intersects an exact deletion target')

    critical = {ROOT / name for name in ROUTES}
    for name in ('Source', 'tools', 'Tests'):
        for path, _, is_dir in walk_owned(ROOT / name):
            if not is_dir:
                critical.add(path)
    saves = []
    for run in manual_ids:
        runtime = ROOT / 'Build/InteractiveGameRuntime' / run
        p.boundary(runtime)
        # All root provider/launcher/input files are immutable for these manual profiles.
        critical.update(path for path in runtime.iterdir() if path.is_file())
        for path in list(runtime.glob('*.zssave')) + list(runtime.glob('sessions/*/*.zssave')):
            if path not in saves:
                saves.append(path)
        evidence = ROOT / 'evidence/interactive_game' / run
        critical.update(evidence / name for name in ('request.json', 'bundle.json', 'host_build.json')
                        if (evidence / name).is_file())
    # Eight original manual saves plus the later EA automatic initial checkpoint.
    original_saves = [path for path in saves if '20261009T132430Z_a0a5dd8fd007' not in str(path)]
    p.require(len(original_saves) == 8 and len(saves) == 9, 'Manual save set changed: stop and re-review')
    critical.update(saves)
    for run in KEEP_RUNS:
        runtime = ROOT / 'Build/InteractiveGameRuntime' / run
        critical.update(path for path in runtime.iterdir() if path.is_file())
        evidence = ROOT / 'evidence/interactive_game' / run
        critical.update(evidence / name for name in ('request.json', 'bundle.json', 'host_build.json', 'result.json',
                                                     'driver_result.json', 'stdout.log', 'stderr.log')
                        if (evidence / name).is_file())
        request = read(evidence / 'request.json')
        for name, sha in p.refs(request):
            path = Path(name)
            if path.is_relative_to(runtime) and path.is_file():
                critical.add(path)
        for path in list(runtime.glob('*.zssave')) + list(runtime.glob('sessions/*/*.zssave')):
            critical.add(path)
        if request.get('resume_from'):
            for name, sha in p.refs(request['resume_from']):
                path = Path(name)
                p.require(path.is_relative_to(ROOT) and not inside(path) and p.digest(path) == sha,
                          'Protected restore lineage artifact differs')
                critical.add(path)
    for host in KEEP_HOSTS:
        path = ROOT / 'evidence/ui_window_host' / host / 'build_result.json'
        critical.add(path)
        build = read(path)
        p.require(build.get('build_id') == host and build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT',
                  'Protected Host build record is not the exact completed candidate')
        exe = build['executable']
        p.require(p.digest(Path(exe['path'])) == exe['sha256'], 'Protected Host executable SHA differs')
        critical.add(Path(exe['path']))
        host_root = ROOT / 'Build/UiWindowHost' / host
        for field in ('compiler_inputs', 'provider_inputs', 'ui_assets'):
            for name, sha in p.refs(build.get(field)):
                path = Path(name)
                if path.is_relative_to(host_root) and path.is_file():
                    critical.add(path)
    for name in CPU_ROOTS:
        for path, _, is_dir in walk_owned(ROOT / name):
            if not is_dir:
                critical.add(path)
    rows, hashes, storage = [], {}, {}
    for path in sorted(critical, key=lambda item: str(item).casefold()):
        p.boundary(path)
        p.require(not inside(path), 'Critical guard is in the deletion scope')
        rows.append(file_row(path, p.regular(path), hashes, storage))
    saved_rows = []
    for path in saves:
        with path.open('rb') as stream:
            header = stream.read(60)
            p.require(len(header) == 60 and header[:16] == b'ZEROSIS_SAVE_V1\0' and
                      struct.unpack_from('<I', header, 16)[0] == 1 and
                      struct.unpack_from('<II', header, 48) == (1, 0), 'Manual save identity header differs')
            count = struct.unpack_from('<I', header, 56)[0]
            p.require(1 <= count <= 16384, 'Manual save identity section size invalid')
            bundle = stream.read(count)
            p.require(len(bundle) == count, 'Manual save identity truncated')
        row = next(item for item in rows if ROOT / item['path'] == path)
        saved_rows.append({**row, 'bundle_identity_sha256': hashlib.sha256(bundle).hexdigest()})
    return {'documents': documents, 'reference_holds': holds, 'manual_runtime_ids': manual_ids,
            'manual_saves': saved_rows, 'original_manual_save_count': 8, 'additional_ea_save_count': 1,
            'protected_scope_roots': [str(path) for path in scopes],
            'explicit_hosts': list(KEEP_HOSTS), 'explicit_runs': list(KEEP_RUNS),
            'all_surviving_runtime_ids': all_runtime_ids, 'all_surviving_host_ids': all_host_ids,
            'critical_guards': rows, 'critical_unique_identities': len(hashes),
            'source_tools_tests_full_hash_inventory': True,
            'all_surviving_runtime_recursive_hash_seal': False,
            'seal_note': 'Draft SHA inventory covers all Source/tools/Tests plus explicit critical files and CPU evidence; final review and immediate guards must precede apply. All other paths are excluded from deletion.'}


def main():
    p.boundary(OUT)
    p.require(len(TARGETS) == 4 and p.digest(HELPER) == HELPER_SHA, 'Helper or target contract differs')
    for target in TARGETS:
        p.require(target == p.legal_target(target) and target.is_dir(), 'Exact target boundary failed')
    marker = write_new('prepare-started.json', {'utc': datetime.now(timezone.utc).isoformat(),
                       'script': artifact(Path(__file__)), 'plan_only': True, 'no_replay': True})
    try:
        processes_before = process_audit()
        results = []
        for run in RUNS:
            path = ROOT / 'evidence/interactive_game' / run / 'result.json'
            value = read(path)
            p.require(value.get('run_id') == run and value.get('status') ==
                      'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_FAILED' and
                      value.get('returncode') == 1 and value.get('timed_out') is False,
                      'Target is not the reviewed terminal failure')
            results.append({'run_id': run, 'result': artifact(path), 'status': value['status'],
                            'returncode': value['returncode'], 'timed_out': value['timed_out']})
        rows, directories, hashes, storage, summary = [], [], {}, {}, []
        for target in TARGETS:
            start = len(rows)
            for path, info, is_dir in walk_owned(target):
                if is_dir:
                    directories.append({'path': str(path.relative_to(ROOT)), 'device': int(info.st_dev),
                                        'file_id': int(info.st_ino), 'mtime_ns': info.st_mtime_ns,
                                        'attributes': info.st_file_attributes})
                else:
                    rows.append(file_row(path, info, hashes, storage))
            own = rows[start:]
            summary.append({'path': str(target), 'files': len(own),
                            'logical_bytes': sum(row['bytes'] for row in own),
                            'allocated_path_bytes': sum(row['stored_bytes'] for row in own)})
            print(json.dumps({'phase': 'target_inventoried', **summary[-1]}), flush=True)
        groups, aliases = link_audit(rows)
        inventory = write_new('inventory.json.gz', {'files': rows, 'directories': directories,
                              'external_hardlinks': aliases}, True)
        diagnostics = preserve_diagnostics(rows)
        protection = reference_and_protection_audit()
        protected = write_new('protection-draft.json.gz', protection, True)
        processes_after = process_audit()
        external_ids = {(group['sample']['device'], group['sample']['file_id']) for group in groups.values()
                        if group['sample']['links'] > len(group['target_paths'])}
        reclaimable = sum(group['sample']['stored_bytes'] for pair, group in groups.items() if pair not in external_ids)
        plan = {'schema': 1, 'status': 'DRAFT_ONLY_NOT_AUTHORIZED_FOR_APPLY',
                'utc': datetime.now(timezone.utc).isoformat(), 'root': str(ROOT),
                'script': artifact(Path(__file__)), 'helper': artifact(HELPER), 'start_marker': marker,
                'exact_targets': [str(target) for target in TARGETS], 'targets': summary,
                'target_count': 4, 'file_count': len(rows), 'directory_count': len(directories),
                'logical_bytes': sum(row['bytes'] for row in rows),
                'allocated_path_bytes': sum(row['stored_bytes'] for row in rows),
                'unique_target_file_identities': len(groups),
                'unique_target_allocated_bytes': sum(group['sample']['stored_bytes'] for group in groups.values()),
                'reclaimable_allocated_bytes_if_all_exact_unlinks_succeed': reclaimable,
                'outside_alias_groups': len(aliases),
                'outside_alias_path_count': sum(len(item['surviving_aliases']) for item in aliases),
                'inventory': inventory, 'diagnostics': diagnostics, 'protection': protected,
                'terminal_failed_results': results, 'processes_before': processes_before,
                'processes_after': processes_after, 'reference_holds': protection['reference_holds'],
                'manual_save_count': len(protection['manual_saves']),
                'critical_guard_count': len(protection['critical_guards']),
                'application_implemented': False, 'deletion_performed': False,
                'required_before_apply': [
                    'Root review of this exact plan SHA and a newly written one-use apply entry point.',
                    'Replacement Notification fresh and restore native results accepted by root; final exact IDs and lineage pinned.',
                    'No active native Host/compiler/linker; reject every process name whose executable/command line references either exact retired run.',
                    'Fresh four-root inventory/set equality, absolute containment and ancestor reparse checks; file ID, size, mtime, SHA and use check immediately before each unlink.',
                    'Fresh external hardlink names/counts/identity/hash guard; changed link counts while replacement runs were created require a reviewed new inventory, never a stale apply.',
                    'Resolve historical document references to this byte-restorable archive, and any execution/code reference holds.',
                    'Seal and compare critical/source/provider/manual/current/proof protection after live runs stop; retain all nine observed manual/EA saves and CPU evidence.',
                    'Single application-start marker, append-only removal journal, no replay after failure/partial application; verify all survivor aliases, critical saves and protected SHA after deletion.',
                ],
                'limits': ['No whole-project historical hash scan was run.',
                           'Allocated bytes are GetCompressedFileSizeW per NTFS file identity; directory/MFT overhead and actual free-space change are not claimed.',
                           'Failed smoke autosaves are inventoried test outputs, distinct from the nine explicitly protected manual/EA saves.',
                           'Source/tools/Tests and every sibling runtime/Host are outside these four deletion boundaries. Draft hashes are not a final protection seal.']}
        report = write_new('plan.json', plan)
        print(json.dumps({'status': plan['status'], 'plan': report, 'files': len(rows),
                          'logical_bytes': plan['logical_bytes'], 'reclaimable_allocated_bytes': reclaimable,
                          'diagnostics': diagnostics, 'reference_holds': protection['reference_holds'],
                          'manual_saves': len(protection['manual_saves'])}, ensure_ascii=False), flush=True)
    except Exception as exc:
        write_new('preparation-failed.json', {'status': 'FAILED_NO_DELETE_NO_REPLAY',
                  'utc': datetime.now(timezone.utc).isoformat(), 'error': str(exc), 'type': type(exc).__name__})
        raise


if __name__ == '__main__':
    main()
