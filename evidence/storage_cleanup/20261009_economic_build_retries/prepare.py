"""Fresh one-use retirement plan for exactly four unexecuted economic Hosts.

Default: inventory and small exact-byte diagnostic archives only. A later seal
requires a successful replacement and no active Host/compiler. Application is
explicit, hash-pinned, one-use, and limited to the eight literal directories below.
No previous cleanup plan is read or replayed.
"""
from __future__ import annotations
import argparse
import base64
import ctypes
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as p

IDS = ('20261009T095944Z_69db988e03ae', '20261009T100903Z_f17699843268', '20261009T101239Z_5ca855aa154e',
       '20261009T101731Z_2d8009cc967c')
DIRS = tuple(ROOT / group / build for build in IDS for group in ('Build/UiWindowHost', 'evidence/ui_window_host'))
EXPECTED = ('UI_WINDOW_HOST_CANDIDATE_BUILT', 'UI_WINDOW_HOST_BUILD_FAILED', 'UI_WINDOW_HOST_BUILD_FAILED', 'UI_WINDOW_HOST_CANDIDATE_BUILT')
HELPER = ROOT / 'tools/prune_superseded_runtime_artifacts.py'
ROUTES = (ROOT / 'tools/Start-Engine.ps1', ROOT / 'docs/CONTINUOUS_PLAY.md', ROOT / 'docs/ENGINE_COMPLETION_STATUS.md')


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(path, value):
    with Path(path).open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def gzwrite_new(path, value):
    with Path(path).open('xb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=9, mtime=0) as stream:
        stream.write(json.dumps(value, ensure_ascii=False, separators=(',', ':')).encode('utf8'))


def gzread(path):
    with gzip.open(path, 'rt', encoding='utf8') as stream:
        return json.load(stream)


def inside_targets(path):
    return any(path.is_relative_to(target) for target in DIRS)


def check_roots():
    p.require(ROOT == p.ROOT and OUT == ROOT / 'evidence/storage_cleanup/20261009_economic_build_retries', 'Unexpected project/output root')
    p.boundary(OUT)
    for target in DIRS:
        p.legal_target(target)
        p.require(target.is_dir(), 'Missing exact target: ' + str(target))


def target_processes_clear():
    # Inventory may overlap a DIFFERENT new build; nothing from these IDs may run.
    command = "@(Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('ZeroSisHost_x64.exe','cl.exe','link.exe','c1xx.exe') } | Select-Object ProcessId,Name,ExecutablePath,CommandLine) | ConvertTo-Json -Compress"
    process = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True, text=True,
                             timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
    p.require(process.returncode == 0, 'Cannot establish Host/compiler process state')
    records = json.loads(process.stdout) if process.stdout.strip() else []
    records = records if isinstance(records, list) else [records]
    for row in records:
        p.require(row.get('ExecutablePath') and row.get('CommandLine'), 'A Host/compiler command line is inaccessible')
        text = (row['ExecutablePath'] + ' ' + row['CommandLine']).casefold()
        p.require(not any(build.casefold() in text for build in IDS), 'Retired Host/compiler is still active')
    return [{'pid': row['ProcessId'], 'name': row['Name'], 'target_match': False} for row in records]


def unused(path):
    # Probe without changing attributes. A reader/writer or executing image
    # that conflicts with exclusive READ+DELETE ownership rejects the plan.
    handle = p.K.CreateFileW(str(path), 0x80010000, 0, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    p.K.CloseHandle(handle)


def identity(info):
    return int(info.st_dev), int(info.st_ino), info.st_size, info.st_mtime_ns, info.st_nlink


def file_row(path, info, hashed):
    key = identity(info)
    value = hashed.get(key)
    if value is None:
        value = p.digest(path)
        hashed[key] = value
    p.require(identity(p.regular(path)) == key, 'File changed during inventory: ' + str(path))
    return {'path': str(path.relative_to(ROOT)), 'device': key[0], 'file_id': key[1], 'bytes': key[2],
            'mtime_ns': key[3], 'links': key[4], 'sha256': value, 'stored_bytes': p.stored(path)}


def reference_audit():
    reports, host_hashes = [], set()
    for build, expected in zip(IDS, EXPECTED):
        path = ROOT / 'evidence/ui_window_host' / build / 'build_result.json'
        value = read(path)
        p.require(value.get('build_id') == build and value.get('status') == expected and
                  value.get('host_runtime_executed') is False and value.get('gamecore_loaded') is False and
                  value.get('stage_updated') is False and value.get('mods_updated') is False,
                  'Target Host is not the exact terminal unexecuted candidate/failure')
        executable = value.get('executable')
        if executable:
            path_exe = p.boundary(Path(executable['path']))
            p.require(inside_targets(path_exe) and p.digest(path_exe) == executable['sha256'], 'Candidate Host executable changed')
            host_hashes.add(executable['sha256'])
        reports.append({'path': str(path.relative_to(ROOT)), 'sha256': p.digest(path), 'status': expected, 'native_executed': False})
    inspected = []
    documents = set(ROUTES) | set((ROOT / 'evidence').glob('*/*/request.json'))
    # Surviving build records can contain dependencies too. In-progress output
    # is rechecked after the replacement completes, before any plan is sealed.
    documents |= set((ROOT / 'evidence/ui_window_host').glob('*/build_result.json'))
    for path in sorted(documents):
        if inside_targets(path) or path.is_relative_to(OUT):
            continue
        p.boundary(path)
        content = path.read_bytes()
        text = content.decode('utf-8-sig')
        p.require(not any(build in text for build in IDS), 'Surviving runtime/request/build route references target: ' + str(path))
        p.require(not any(value in text for value in host_hashes), 'Surviving request references retired executable hash: ' + str(path))
        inspected.append({'path': str(path.relative_to(ROOT)), 'bytes': len(content), 'sha256': hashlib.sha256(content).hexdigest()})
    runtimes = ROOT / 'Build/InteractiveGameRuntime'
    runtime_hosts, saves = [], []
    for path in sorted(runtimes.glob('*/ZeroSisHost_x64.exe')):
        p.boundary(path)
        sha = p.digest(path)
        p.require(sha not in host_hashes, 'A current runtime executes this candidate Host')
        runtime_hosts.append({'path': str(path.relative_to(ROOT)), 'sha256': sha})
    manual_ids = set(p.RUN.findall(ROUTES[0].read_text(encoding='utf8')))
    for path in sorted(runtimes.rglob('*.zssave')):
        p.boundary(path)
        with path.open('rb') as stream:
            header = stream.read(60)
            p.require(len(header) == 60 and header[:16] == b'ZEROSIS_SAVE_V1\0', 'Unexpected native save identity')
            kind, index, length = struct.unpack_from('<3I', header, 48)
            p.require((kind, index) == (1, 0) and 0 < length <= 65536, 'Invalid native saved bundle identity')
            bundle = stream.read(length).decode('ascii')
            p.require(not any(value in bundle for value in host_hashes), 'An existing save requires the retired Host')
        saves.append({'path': str(path.relative_to(ROOT)), 'sha256': p.digest(path), 'bytes': path.stat().st_size,
                      'manual_runtime': path.relative_to(runtimes).parts[0] in manual_ids})
    p.require(runtime_hosts and len([row for row in saves if row['manual_runtime']]) >= 8,
              'Current manual runtime/save preservation inventory is unexpectedly incomplete')
    return {'target_build_reports': reports, 'surviving_documents': inspected, 'runtime_hosts': runtime_hosts, 'native_saves': saves,
            'manual_runtime_ids': sorted(manual_ids), 'target_references': [], 'native_save_host_matches': [],
            'manual_native_save_count': sum(row['manual_runtime'] for row in saves)}


def inventory():
    check_roots()
    p.require(not any((OUT / name).exists() for name in ('inventory.json', 'retired-files.json.gz', 'diagnostics.json.gz', 'plan.json')),
              'Inventory already exists; never replay or overwrite it')
    processes = target_processes_clear()
    references = reference_audit()
    hashed, rows, directories = {}, [], []
    diagnostic_names = set()
    for build in IDS:
        folder = ROOT / 'evidence/ui_window_host' / build
        diagnostic_names.update(path for path in folder.iterdir() if path.is_file() and path.suffix.lower() in ('.json', '.txt', '.log'))
        diagnostic_names.add(ROOT / 'Build/UiWindowHost' / build / 'final/link.rsp')
        for source in read(folder / 'build_result.json')['sources']:
            if Path(source['path']).name in ('UiPopupContext.h', 'UiScene.lua', 'UiEconomicOverview.lua'):
                diagnostic_names.add(Path(source['path']))
    for target in DIRS:
        for current, folders, files in os.walk(target, followlinks=False):
            current = p.boundary(Path(current)); info = current.lstat()
            directories.append({'path': str(current.relative_to(ROOT)), 'device': int(info.st_dev), 'file_id': int(info.st_ino),
                                'mtime_ns': info.st_mtime_ns})
            for name in folders:
                p.boundary(current / name)
            for name in files:
                path = current / name; info = p.regular(path)
                p.require(path.suffix.lower() != '.zssave', 'A user/native save appeared inside an unexecuted Host target')
                unused(path)
                rows.append(file_row(path, info, hashed))
    rows.sort(key=lambda row: row['path'].casefold())
    row_by_path = {ROOT / row['path']: row for row in rows}
    diagnostics = []
    for path in sorted(diagnostic_names):
        p.require(path in row_by_path and inside_targets(path), 'Diagnostic source escaped the exact target ledger')
        row = row_by_path[path]; raw = path.read_bytes()
        p.require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Diagnostic changed during preservation')
        diagnostics.append({'path': row['path'], 'bytes': len(raw), 'sha256': row['sha256'], 'base64': base64.b64encode(raw).decode('ascii')})
    p.require(sum(row['bytes'] for row in diagnostics) < 8 * 1024**2, 'Unexpectedly large diagnostic source set')
    gzwrite_new(OUT / 'diagnostics.json.gz', diagnostics)
    recovered = gzread(OUT / 'diagnostics.json.gz')
    p.require(recovered == diagnostics, 'Compressed diagnostic metadata changed')
    for row in recovered:
        raw = base64.b64decode(row['base64'], validate=True)
        p.require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Diagnostic archive cannot restore original bytes')
    p.require((OUT / 'diagnostics.json.gz').stat().st_size < 2 * 1024**2, 'Diagnostic gzip exceeds its small archive bound')
    gzwrite_new(OUT / 'retired-files.json.gz', rows)
    gzwrite_new(OUT / 'retired-directories.json.gz', directories)
    gzwrite_new(OUT / 'references.json.gz', references)
    identities = {}
    for row in rows:
        key = row['device'], row['file_id']
        item = identities.setdefault(key, {'links': row['links'], 'count': 0, 'stored': row['stored_bytes']})
        p.require(item['links'] == row['links'] and item['stored'] == row['stored_bytes'], 'Hardlink/storage identity changed')
        item['count'] += 1
    groups = []
    for target in DIRS:
        subset = [row for row in rows if (ROOT / row['path']).is_relative_to(target)]
        group_ids = {(row['device'], row['file_id']) for row in subset}
        groups.append({'path': str(target.relative_to(ROOT)), 'absolute_path': str(target), 'files': len(subset),
                       'logical_bytes': sum(row['bytes'] for row in subset),
                       'unique_file_storage_bytes': sum(identities[key]['stored'] for key in group_ids)})
    report = {'status': 'INVENTORY_ONLY_NOT_SEALED', 'created_utc': datetime.now(timezone.utc).isoformat(), 'root': str(ROOT),
              'exact_host_ids': list(IDS), 'targets': groups, 'file_count': len(rows), 'logical_bytes': sum(row['bytes'] for row in rows),
              'unique_file_storage_bytes': sum(item['stored'] for item in identities.values()),
              'estimated_reclaimable_file_storage_bytes': sum(item['stored'] for item in identities.values() if item['count'] == item['links']),
              'externally_linked_file_identities': sum(item['count'] < item['links'] for item in identities.values()),
              'diagnostic_files': len(diagnostics), 'diagnostic_source_bytes': sum(row['bytes'] for row in diagnostics),
              'diagnostic_compressed_bytes': (OUT / 'diagnostics.json.gz').stat().st_size,
              'manual_native_save_count': references['manual_native_save_count'], 'processes_during_inventory': processes,
              'script_sha256': p.digest(Path(__file__)), 'helper_sha256': p.digest(HELPER),
              'artifacts': {name: p.digest(OUT / name) for name in ('diagnostics.json.gz', 'retired-files.json.gz', 'retired-directories.json.gz', 'references.json.gz')},
              'seal_status': 'NOT_RUN_REPLACEMENT_BUILD_AND_FULL_PROTECTION_REQUIRED', 'apply_status': 'NOT_RUN_NO_DELETION'}
    write_new(OUT / 'inventory.json', report)
    print(json.dumps({key: report[key] for key in ('status', 'file_count', 'logical_bytes', 'estimated_reclaimable_file_storage_bytes',
          'diagnostic_files', 'diagnostic_compressed_bytes', 'manual_native_save_count')}, ensure_ascii=False), flush=True)


def verify_inventory():
    check_roots()
    report = read(OUT / 'inventory.json')
    p.require(report['root'] == str(ROOT) and report['exact_host_ids'] == list(IDS) and
              {row['absolute_path'] for row in report['targets']} == {str(path) for path in DIRS}, 'Inventory target set changed')
    p.require(report['script_sha256'] == p.digest(Path(__file__)) and report['helper_sha256'] == p.digest(HELPER), 'Reviewed cleanup code changed')
    for name, sha in report['artifacts'].items():
        p.require(Path(name).name == name and p.digest(OUT / name) == sha, 'Inventory artifact changed')
    rows = gzread(OUT / 'retired-files.json.gz')
    expected = {row['path'] for row in rows}
    p.require(len(expected) == len(rows) == report['file_count'], 'Ledger has duplicate or omitted paths')
    observed = set()
    for target in DIRS:
        for path, info in p.inventory(target):
            observed.add(str(path.relative_to(ROOT)))
    p.require(observed == expected, 'Exact target file membership changed since inventory')
    for row in rows:
        path = p.boundary(ROOT / row['path']); info = p.regular(path)
        p.require(inside_targets(path) and identity(info) == (row['device'], row['file_id'], row['bytes'], row['mtime_ns'], row['links']),
                  'Target identity/link count changed: ' + str(path))
        p.require(p.digest(path) == row['sha256'], 'Target bytes changed: ' + str(path))
        unused(path)
    for row in gzread(OUT / 'retired-directories.json.gz'):
        path = p.boundary(ROOT / row['path']); info = path.lstat()
        p.require(inside_targets(path) and stat.S_ISDIR(info.st_mode) and
                  (int(info.st_dev), int(info.st_ino), info.st_mtime_ns) == (row['device'], row['file_id'], row['mtime_ns']), 'Target directory identity changed')
    for row in gzread(OUT / 'diagnostics.json.gz'):
        raw = base64.b64decode(row['base64'], validate=True)
        p.require(row['path'] in expected and len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Preserved diagnostic is corrupt')
    return report, rows


def project_files():
    for child in ROOT.iterdir():
        p.boundary(child)
        if child == OUT or inside_targets(child):
            continue
        if child.is_dir():
            for path, info in p.inventory(child):
                if not inside_targets(path) and not path.is_relative_to(OUT):
                    yield path, info
        else:
            yield child, p.regular(child)


def verify_protected(rows):
    hashed = {}
    observed = {str(path.relative_to(ROOT)) for path, _ in project_files()}
    p.require(observed == {row['path'] for row in rows}, 'Surviving project membership changed after seal')
    for row in rows:
        path = p.boundary(ROOT / row['path']); info = p.regular(path)
        # Outside hardlink counts may legitimately fall after deletion. Content,
        # file ID, modification time and size must remain exactly unchanged.
        p.require(not inside_targets(path) and not path.is_relative_to(OUT) and
                  identity(info)[:4] == (row['device'], row['file_id'], row['bytes'], row['mtime_ns']), 'Protected file identity changed')
        key = identity(info)[:4]
        if key not in hashed:
            hashed[key] = p.digest(path)
        p.require(hashed[key] == row['sha256'], 'Protected file bytes changed: ' + str(path))


def seal(replacement):
    p.no_active_host()
    p.require(p.RUN.fullmatch(replacement) and replacement not in IDS and not (OUT / 'plan.json').exists(), 'Invalid replacement or already sealed plan')
    report, rows = verify_inventory()
    target_processes_clear(); references = reference_audit()
    replacement_report = p.boundary(ROOT / 'evidence/ui_window_host' / replacement / 'build_result.json')
    value = read(replacement_report)
    p.require(value.get('build_id') == replacement and value.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
              value.get('source_inputs_unchanged') is True, 'Replacement Host is not a successful terminal sealed build')
    replacement_exe = p.boundary(Path(value['executable']['path']))
    p.require(replacement_exe.is_relative_to(ROOT / 'Build/UiWindowHost' / replacement) and
              p.digest(replacement_exe) == value['executable']['sha256'], 'Replacement executable provenance changed')
    hashed, guards = {}, []
    for path, info in project_files():
        guards.append(file_row(path, info, hashed))
    gzwrite_new(OUT / 'protected-final.json.gz', guards)
    gzwrite_new(OUT / 'references-final.json.gz', references)
    verify_protected(guards)
    p.no_active_host()
    plan = {'status': 'SEALED_EXACT_FOUR_UNEXECUTED_HOSTS', 'root': str(ROOT), 'exact_host_ids': list(IDS),
            'inventory_sha256': p.digest(OUT / 'inventory.json'), 'script_sha256': p.digest(Path(__file__)), 'helper_sha256': p.digest(HELPER),
            'replacement_host': replacement, 'replacement_report_sha256': p.digest(replacement_report),
            'protected_files': len(guards), 'files': len(rows), 'logical_bytes': report['logical_bytes'],
            'estimated_reclaimable_file_storage_bytes': report['estimated_reclaimable_file_storage_bytes'],
            'artifacts': {**report['artifacts'], **{name: p.digest(OUT / name) for name in ('protected-final.json.gz', 'references-final.json.gz')}}}
    write_new(OUT / 'plan.json', plan)
    print(json.dumps({'status': plan['status'], 'plan_sha256': p.digest(OUT / 'plan.json'), 'protected_files': len(guards)}, ensure_ascii=False), flush=True)


def apply(expected):
    p.no_active_host()
    p.require(not (OUT / 'cleanup.json').exists() and p.digest(OUT / 'plan.json') == expected, 'Already applied/started or unreviewed plan')
    plan = read(OUT / 'plan.json')
    p.require(plan['status'] == 'SEALED_EXACT_FOUR_UNEXECUTED_HOSTS' and plan['root'] == str(ROOT) and plan['exact_host_ids'] == list(IDS) and
              plan['inventory_sha256'] == p.digest(OUT / 'inventory.json') and plan['script_sha256'] == p.digest(Path(__file__)) and
              plan['helper_sha256'] == p.digest(HELPER), 'Plan code, inventory or scope changed')
    for name, sha in plan['artifacts'].items():
        p.require(Path(name).name == name and p.digest(OUT / name) == sha, 'Sealed protection/diagnostic archive changed')
    _, rows = verify_inventory()
    reference_audit(); target_processes_clear()
    guards = gzread(OUT / 'protected-final.json.gz'); verify_protected(guards)
    status = {'status': 'APPLY_STARTED_DO_NOT_REPLAY', 'plan_sha256': expected, 'removed_files': 0, 'removed_logical_bytes': 0,
              'volume_free_bytes_before': shutil.disk_usage(ROOT).free, 'protected_hashes_verified_before': True,
              'source_tools_tests_current_builds_runtime_and_saves_deleted': False, 'errors': []}
    write_new(OUT / 'cleanup.json', status)
    try:
        p.no_active_host()
        for row in rows:
            path = p.boundary(ROOT / row['path']); info = p.regular(path)
            # Other links in this approved set may have been removed already.
            p.require(inside_targets(path) and identity(info)[:4] == (row['device'], row['file_id'], row['bytes'], row['mtime_ns']) and
                      1 <= info.st_nlink <= row['links'] and p.digest(path) == row['sha256'], 'Target changed immediately before unlink')
            unused(path)
            p.unlink_without_attribute_changes(path)
            p.require(not path.exists(), 'Retired file remains')
            status['removed_files'] += 1; status['removed_logical_bytes'] += row['bytes']
        folders = gzread(OUT / 'retired-directories.json.gz')
        for row in sorted(folders, key=lambda item: len(Path(item['path']).parts), reverse=True):
            path = p.boundary(ROOT / row['path']); info = path.lstat()
            p.require(inside_targets(path) and (int(info.st_dev), int(info.st_ino)) == (row['device'], row['file_id']), 'Retired directory identity changed')
            path.rmdir()  # Empty-only removal; no recursive wildcard deletion.
        verify_protected(guards)
        p.require(status['removed_files'] == plan['files'] and not any(path.exists() for path in DIRS), 'Cleanup membership/count differs')
        status.update(status='PASS_EXACT_FOUR_UNEXECUTED_HOST_RETIREMENT', protected_hashes_verified_after=True)
    except BaseException as exc:
        status.update(status='PARTIAL_FAILURE_DO_NOT_REPLAY', errors=[str(exc)])
        raise
    finally:
        status['volume_free_bytes_after'] = shutil.disk_usage(ROOT).free
        (OUT / 'cleanup.json').write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
        print(json.dumps(status, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--seal-replacement-host')
    modes.add_argument('--apply-plan-sha256')
    args = parser.parse_args()
    if args.seal_replacement_host:
        seal(args.seal_replacement_host)
    elif args.apply_plan_sha256:
        apply(args.apply_plan_sha256)
    else:
        inventory()
