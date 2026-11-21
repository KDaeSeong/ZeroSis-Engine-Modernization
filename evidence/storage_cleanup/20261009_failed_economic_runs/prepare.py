"""Draft only: inventory exactly two failed economic runs and their first Host.

No seal, unlink, rmdir, attribute changes, build, or native launch is implemented.
Only this output directory is written. A new successful run and explicit review
must precede a separate one-use apply entry point and fresh protection hashes.
"""
from __future__ import annotations

import base64
from collections import Counter
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
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as p

HELPER = ROOT / 'tools/prune_superseded_runtime_artifacts.py'
HELPER_SHA = '99eed1b129e24139b435feb34e2a88172ba7332ffaf9a3e4d3d20f9dfa177baa'
RUNS = {
    '20261009T110155Z_694ab10d0e88': '9f6c07249787778b83c7ea873f1a3ad2',
    '20261009T111132Z_71b1a92021b1': '44e52173fe94248220ff193796857e10',
}
OLD_HOST = '20261009T102157Z_406019d0c3ef'
KEEP_HOST = '20261009T110943Z_83f88f1ab72f'
KEEP_NEW_RUNS = ('20261009T112544Z_22caa6e51793', '20261009T113226Z_8b96bad78523')
TARGETS = tuple(ROOT / group / run for run in RUNS for group in
                ('Build/InteractiveGameRuntime', 'evidence/interactive_game')) + tuple(
    ROOT / group / OLD_HOST for group in ('Build/UiWindowHost', 'evidence/ui_window_host'))
ROUTES = tuple(ROOT / name for name in
               ('tools/Start-Engine.ps1', 'docs/CONTINUOUS_PLAY.md', 'docs/ENGINE_COMPLETION_STATUS.md', 'AGENTS.md'))
SOURCE_NAMES = {'UiScene.lua', 'UiPopupContext.h', 'InteractiveGameLoop.h',
                'InteractiveGameSession.h', 'InteractiveUiSession.h', 'EconomicOverviewSmokeFixture.h',
                'UiEconomicOverview.lua', 'UiPresentationInput.lua'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def write_new(name, value, compressed=False):
    destination = OUT / name
    p.require(destination.parent == OUT, 'Output escaped exact cleanup folder')
    payload = json.dumps(value, ensure_ascii=False, separators=(',', ':') if compressed else None,
                         indent=None if compressed else 2).encode('utf-8') + b'\n'
    with destination.open('xb') as raw:
        if compressed:
            with gzip.GzipFile(fileobj=raw, mode='wb', compresslevel=9, mtime=0) as stream:
                stream.write(payload)
        else:
            raw.write(payload)
    return {'path': str(destination), 'bytes': destination.stat().st_size, 'sha256': p.digest(destination)}


def inside(path):
    return any(Path(path).is_relative_to(target) for target in TARGETS)


def identity(info):
    return (int(info.st_dev), int(info.st_ino), info.st_size, info.st_mtime_ns, info.st_nlink,
            getattr(info, 'st_file_attributes', 0))


def walk_owned(directory):
    """One bounded traversal; validate root and every descendant without re-resolving files."""
    directory = p.boundary(directory)
    pending = [directory]
    while pending:
        current = pending.pop()
        info = current.lstat()
        p.require(stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400,
                  'Reparse/non-directory in scoped traversal: ' + str(current))
        yield current, info, True
        with os.scandir(current) as entries:
            for entry in entries:
                path = Path(entry.path)
                p.require(path.is_relative_to(directory), 'Scoped traversal escaped its root')
                value = entry.stat(follow_symlinks=False)
                p.require(not value.st_file_attributes & 0x400, 'Reparse entry: ' + str(path))
                if stat.S_ISDIR(value.st_mode):
                    pending.append(path)
                else:
                    p.require(stat.S_ISREG(value.st_mode), 'Nonregular scoped file: ' + str(path))
                    # Windows DirEntry.stat omits st_dev/st_ino/st_nlink (all 0).
                    # Obtain the real identity once here; verify it again after hashing.
                    yield path, p.regular(path), False


def file_row(path, info, hashes, storage):
    key = identity(info)
    if key not in hashes:
        hashes[key] = p.digest(path)
    p.require(identity(p.regular(path)) == key, 'File changed during scoped hashing: ' + str(path))
    pair = key[:2]
    if pair not in storage:
        storage[pair] = p.stored(path)
    return {'path': str(path.relative_to(ROOT)), 'device': key[0], 'file_id': key[1],
            'bytes': key[2], 'mtime_ns': key[3], 'links': key[4], 'attributes': key[5],
            'sha256': hashes[key], 'stored_bytes': storage[pair]}


def validate_process_records(values, require_no_active=False):
    observed = []
    for row in values:
        text = str(row.get('ExecutablePath') or '') + ' ' + str(row.get('CommandLine') or '')
        hits = [identifier for identifier in (*RUNS, OLD_HOST) if identifier.casefold() in text.casefold()]
        p.require(not hits, 'Retirement input used by a running process: ' + str(row.get('Name')))
        if row.get('Name', '').casefold() in ('zerosisHost_x64.exe'.casefold(), 'cl.exe', 'link.exe', 'c1xx.exe', 'ninja.exe'):
            p.require(row.get('CommandLine') and row.get('ExecutablePath'), 'Host/compiler visibility is incomplete')
            p.require(not require_no_active, 'Final gate requires no active native Host/compiler/linker')
        observed.append({'pid': row['ProcessId'], 'name': row['Name'], 'target_ids': hits})
    return observed


def process_audit(require_no_active=False):
    # All process names, including Python/PowerShell and other driver wrappers.
    command = "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); @(Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath,CommandLine) | ConvertTo-Json -Compress"
    run = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command], capture_output=True,
                         text=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    p.require(run.returncode == 0, 'Process observation failed')
    values = json.loads(run.stdout) if run.stdout.strip() else []
    values = values if isinstance(values, list) else [values]
    return validate_process_records(values, require_no_active)


def terminal_result_contract(value, run_id, restored):
    wanted = 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_' + ('RESTORE_SMOKE_PASS' if restored else 'SMOKE_PASS')
    p.require(value.get('run_id') == run_id and value.get('status') == wanted and
              type(value.get('returncode')) is int and value['returncode'] == 0 and
              value.get('timed_out') is False and value.get('failures') == [],
              'Required replacement native terminal PASS/exit/timeout contract failed')


def final_gate():
    processes = process_audit(require_no_active=True)
    fresh_id, restore_id = KEEP_NEW_RUNS
    records, values, requests, proofs = [], [], [], []
    def verify_record(record):
        path = p.boundary(Path(record['path']))
        p.require(not inside(path) and p.digest(path) == record['sha256'], 'Final proof artifact changed')
        records.append({'path': str(path), 'sha256': record['sha256']})
    for index, run_id in enumerate(KEEP_NEW_RUNS):
        directory = ROOT / 'evidence/interactive_game' / run_id
        result_path, request_path = directory / 'result.json', directory / 'request.json'
        value, request = read(result_path), read(request_path)
        terminal_result_contract(value, run_id, bool(index))
        p.require(request.get('run_id') == run_id and request.get('economic_overview_smoke') is True,
                  'Replacement request is not the exact economic smoke')
        verify_record({'path': str(result_path), 'sha256': p.digest(result_path)})
        verify_record({'path': str(request_path), 'sha256': p.digest(request_path)})
        verify_record(value['request'])
        proof_path = directory / ('economic_overview_validation_followup.json' if index == 0 else 'economic_overview_validation.json')
        proof = read(proof_path)
        p.require(proof.get('status') == 'PASS_INTERACTIVE_ECONOMIC_OVERVIEW_NATIVE_SDK_SMOKE' and proof.get('run_id') == run_id,
                  'Both independent economic PASS reports are required, including the fresh followup')
        p.require(Path(proof['result']['path']) == result_path and proof['result']['sha256'] == p.digest(result_path),
                  'Independent economic proof is not attached to the exact native result')
        verify_record({'path': str(proof_path), 'sha256': p.digest(proof_path)})
        for name, sha in p.refs(proof):
            path = Path(name)
            if path.is_relative_to(ROOT):
                verify_record({'path': name, 'sha256': sha})
        values.append(value); requests.append(request); proofs.append(proof)
    fresh, restore = values
    lineage = requests[1].get('resume_from')
    p.require(requests[0].get('resume_from') is None and isinstance(lineage, dict) and
              lineage.get('run_id') == fresh_id and restore.get('resume_from_run') == fresh_id,
              'Restore must descend from the exact accepted fresh run')
    p.require(restore.get('checkpoint_input_unchanged') is True and restore.get('semantic_restore_equal') is True and
              restore.get('fresh_process_restore_verified') is True, 'Native restore/immutable checkpoint proof failed')
    p.require(proofs[1].get('restore', {}).get('source_run_id') == fresh_id and
              proofs[1]['restore'].get('saved_production_recovered') is True,
              'Independent restore lineage/production recovery proof failed')
    p.require(lineage['run_result']['sha256'] == p.digest(ROOT / 'evidence/interactive_game' / fresh_id / 'result.json'),
              'Restore source-result bytes differ from fresh result')
    for record in (lineage['run_result'], lineage['checkpoint_source'], lineage['checkpoint_input'],
                   lineage['expected_state'], lineage['checkpoint_source_state']):
        verify_record(record)
    p.require(lineage['checkpoint_source']['sha256'] == lineage['checkpoint_input']['sha256'] and
              Path(lineage['checkpoint_source']['path']).is_relative_to(ROOT / 'Build/InteractiveGameRuntime' / fresh_id) and
              Path(lineage['checkpoint_input']['path']).is_relative_to(ROOT / 'Build/InteractiveGameRuntime' / restore_id),
              'Restored checkpoint path/content lineage differs')
    return {'status': 'PASS_REQUIRED_ECONOMIC_FRESH_RESTORE_AND_PROVENANCE', 'runtime_ids': list(KEEP_NEW_RUNS),
            'artifacts': list({row['path']: row for row in records}.values()), 'processes_observed': len(processes),
            'native_capture_released_by_root': True, 'seal_or_delete_performed': False}


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
                p.require(ctypes.get_last_error() == 38, 'Hardlink enumeration did not end normally')
                break
    finally:
        kernel.FindClose(handle)
    return sorted(set(result), key=lambda value: str(value).casefold())


def link_audit(rows):
    groups = {}
    for row in rows:
        pair = row['device'], row['file_id']
        group = groups.setdefault(pair, {'sample': row, 'target_paths': []})
        p.require(group['sample']['links'] == row['links'] and group['sample']['sha256'] == row['sha256'],
                  'Hardlink identity changed inside target inventory')
        group['target_paths'].append(str(ROOT / row['path']))
    external = []
    for pair, group in groups.items():
        row = group['sample']
        if row['links'] == 1:
            continue
        names = hardlink_names(ROOT / row['path'])
        p.require(len(names) == row['links'], 'Hardlink count and named aliases differ')
        p.require({str(x).casefold() for x in names if inside(x)} ==
                  {x.casefold() for x in group['target_paths']}, 'Target aliases differ from exact inventory')
        survivors = []
        for alias in names:
            if inside(alias):
                continue
            info = p.regular(alias)
            p.require((info.st_dev, info.st_ino) == pair, 'External hardlink identity differs')
            sha = p.digest(alias)
            after = p.regular(alias)
            p.require(sha == row['sha256'] and identity(after) == identity(info),
                      'External hardlink content/identity changed: ' + str(alias) +
                      ' sha_matches=' + str(sha == row['sha256']) +
                      ' before=' + str(identity(info)) + ' after=' + str(identity(after)))
            survivors.append({'path': str(alias), 'inside_project': alias.is_relative_to(ROOT),
                              'device': pair[0], 'file_id': pair[1], 'bytes': info.st_size,
                              'mtime_ns': info.st_mtime_ns, 'attributes': info.st_file_attributes, 'sha256': sha})
        if survivors:
            external.append({'target_paths': group['target_paths'], 'links_before': row['links'],
                             'links_after_exact_unlinks': row['links'] - len(group['target_paths']),
                             'surviving_aliases': survivors})
    return groups, external


def diagnostic_sources():
    paths = set()
    for run, session_id in RUNS.items():
        evidence = ROOT / 'evidence/interactive_game' / run
        for name in ('result.json', 'request.json', 'driver_result.json', 'stdout.log', 'stderr.log',
                     'runner.py', 'economic_overview_timeline.py', 'host_build.json',
                     'interactive_ui_support.json', 'bundle.json', 'attempt.json'):
            paths.add(evidence / name)
        runtime = ROOT / 'Build/InteractiveGameRuntime' / run
        session = runtime / 'sessions' / session_id
        paths.update((session / 'play-ui-45.json', session / 'economic-before-state.txt'))
        paths.update(session.glob('economic-*-state.txt'))
        paths.update((runtime / 'interactive_ui_support/tools').glob('*.py'))
        paths.add(runtime / 'interactive_ui_support/support_manifest.json')
        paths.add(runtime / 'interactive_ui_support/assets/inline_icons.json')
        for name in ('inline_colors.json', 'inline_icons.json', 'preparation_inputs.json', 'scene_manifest.json'):
            candidate = session / 'play-ui-45' / name
            if candidate.is_file():
                paths.add(candidate)
        build = read(evidence / 'host_build.json')
        paths.update(Path(row['path']) for row in build['sources'] if Path(row['path']).name in SOURCE_NAMES)
    paths.add(ROOT / 'evidence/ui_window_host' / OLD_HOST / 'build_result.json')
    # The retained renderer replay names these exact failed-runtime inputs.
    # Preserve their original bytes; the replay output itself is not a target.
    replay = ROOT / 'evidence/economic_overview_scene/20261009_native_capture_render'
    manifest = read(replay / 'scene_manifest.json')
    preparation = read(replay / 'preparation_inputs.json')
    second = ROOT / 'Build/InteractiveGameRuntime/20261009T111132Z_71b1a92021b1'
    for record, expected in ((manifest['economic_overview_prepared_source'],
                              second / 'interactive_ui_support/assets/prepared.json'),
                             (preparation['support_manifest'],
                              second / 'interactive_ui_support/support_manifest.json')):
        p.require(Path(record['path']) == expected and p.digest(expected) == record['sha256'],
                  'Retained renderer replay input provenance differs')
        paths.add(expected)
    return sorted(paths, key=lambda value: str(value).casefold())


def preserve_diagnostics():
    blobs, records = {}, []
    for path in diagnostic_sources():
        path = p.boundary(path)
        p.require(inside(path) or path.is_relative_to(ROOT / 'Build/UiWindowHost' / KEEP_HOST),
                  'Diagnostic source is outside exact targets/retained Host')
        info = p.regular(path)
        prepared = ROOT / 'Build/InteractiveGameRuntime/20261009T111132Z_71b1a92021b1/interactive_ui_support/assets/prepared.json'
        bound = 32 * 1024**2 if path == prepared else 4 * 1024**2
        p.require(info.st_size <= bound, 'Unexpectedly large raw diagnostic')
        raw = path.read_bytes(); sha = hashlib.sha256(raw).hexdigest()
        p.require(len(raw) == info.st_size and identity(p.regular(path)) == identity(info), 'Diagnostic changed')
        blobs.setdefault(sha, base64.b64encode(raw).decode('ascii'))
        records.append({'path': str(path.relative_to(ROOT)), 'bytes': len(raw), 'sha256': sha,
                        'source_retained_outside_targets': not inside(path)})
    total = sum(len(base64.b64decode(value)) for value in blobs.values())
    p.require(total <= 48 * 1024**2, 'Raw diagnostics plus the one required prepared source exceed archive bound')
    payload = {'files': records, 'blobs_by_sha256': blobs}
    destination = OUT / 'diagnostics.json.gz'
    if destination.exists():
        # Diagnostics may be staged while a different live run adds shared
        # texture aliases. Re-read original bytes above; never overwrite them.
        with gzip.open(destination, 'rt', encoding='utf-8') as stream:
            p.require(json.load(stream) == payload, 'Previously staged raw diagnostic archive differs')
        artifact = {'path': str(destination), 'bytes': destination.stat().st_size, 'sha256': p.digest(destination)}
    else:
        artifact = write_new('diagnostics.json.gz', payload, True)
    with gzip.open(artifact['path'], 'rt', encoding='utf-8') as stream:
        recovered = json.load(stream)
    for row in recovered['files']:
        raw = base64.b64decode(recovered['blobs_by_sha256'][row['sha256']], validate=True)
        p.require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                  'Compressed original bytes did not round trip')
    return artifact, records, total


def reference_and_protection_audit(external_links):
    paths = {}
    protected_roots = [ROOT / name for name in ('Source', 'tools', 'Tests')]
    protected_roots.append(ROOT / 'Build/UiWindowHost' / KEEP_HOST)
    def add(path, reason, required=True):
        path = Path(path)
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_relative_to(ROOT):
            return
        p.require(not inside(path), 'Required surviving dependency intersects a retirement target: ' + str(path))
        if not path.is_file():
            p.require(not required, 'Required protected input is missing: ' + str(path))
            return
        paths.setdefault(path, set()).add(reason)

    documents = set(ROUTES) | set((ROOT / 'evidence').glob('*/*/request.json'))
    documents |= set((ROOT / 'evidence/ui_window_host').glob('*/build_result.json'))
    documents |= set((ROOT / 'evidence/economic_overview_scene').glob('*/*.json'))
    references, documentation_holds, execution_holds = [], [], []
    for path in sorted(documents):
        if inside(path):
            continue
        content = path.read_bytes()
        hits = [identifier for identifier in (*RUNS, OLD_HOST) if identifier.encode() in content]
        record = {'path': str(path.relative_to(ROOT)), 'bytes': len(content),
                  'sha256': hashlib.sha256(content).hexdigest(), 'target_ids': hits}
        references.append(record)
        if hits:
            (execution_holds if path.name == 'request.json' else documentation_holds).append(record)
        add(path, 'current_route_or_reference_document')

    manual_ids = set(p.RUN.findall(ROUTES[0].read_text(encoding='utf-8-sig')))
    runtime_records, saves, missing_historical_sources = [], [], []
    for runtime in sorted((ROOT / 'Build/InteractiveGameRuntime').iterdir()):
        if not runtime.is_dir() or runtime.name in RUNS:
            continue
        request = ROOT / 'evidence/interactive_game' / runtime.name / 'request.json'
        value = read(request)
        result_path = request.with_name('result.json')
        result = read(result_path) if result_path.is_file() else {}
        record = {'run_id': runtime.name, 'manual': runtime.name in manual_ids,
                  'status': result.get('status'), 'request': str(request.relative_to(ROOT))}
        runtime_records.append(record)
        add(request, 'retained_runtime_request')
        if result_path.is_file():
            add(result_path, 'accepted_or_retained_runtime_result')
        for path in runtime.iterdir():
            if path.is_file():
                add(path, 'retained_runtime_root_input')
        for path, sha in p.refs(value):
            add(path, 'retained_request_named_input', required=False)
        for materialization in value.get('materializations', []):
            for key in ('cache', 'target'):
                if materialization.get(key):
                    add(materialization[key], 'retained_runtime_materialization')
        for item in value['runtime_inputs']:
            path = Path(item['path'])
            p.require(p.digest(path) == item['sha256'], 'Retained runtime input differs from sealed request')
            if item.get('source'):
                source = Path(item['source'])
                if source.is_file():
                    add(source, 'current_provider_or_host_source')
                else:
                    missing_historical_sources.append({'request': str(request.relative_to(ROOT)), 'path': str(source),
                                                       'retained_runtime_copy': str(path), 'sha256': item['sha256']})
        support = runtime / 'interactive_ui_support'
        if support.is_dir():
            protected_roots.append(support)
        save_paths = set(runtime.glob('*.zssave')) | set((runtime / 'sessions').glob('*/*.zssave'))
        for path in sorted(save_paths):
            with path.open('rb') as stream:
                header = stream.read(60)
                p.require(len(header) == 60 and header[:16] == b'ZEROSIS_SAVE_V1\0', 'Unrecognized retained save')
                kind, index, length = struct.unpack_from('<3I', header, 48)
                p.require((kind, index) == (1, 0) and 0 < length <= 65536, 'Invalid save engine identity')
                bundle = stream.read(length).decode('ascii')
            add(path, 'manual_save' if record['manual'] else 'accepted_runtime_save')
            saves.append({'path': str(path.relative_to(ROOT)), 'manual': record['manual'], 'bundle_identity': bundle})
    p.require(sum(row['manual'] for row in saves) == 8, 'Expected eight current manual saves including root checkpoint')
    p.require(set(KEEP_NEW_RUNS) <= {row['run_id'] for row in runtime_records},
              'Latest fresh/restore runtime protection is incomplete')
    latest = ROOT / 'evidence/ui_window_host' / KEEP_HOST / 'build_result.json'
    build = read(latest)
    p.require(build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build['source_inputs_unchanged'], 'Latest Host is not sealed')
    p.require(p.digest(Path(build['executable']['path'])) == build['executable']['sha256'], 'Latest Host executable changed')
    for path, sha in p.refs(build):
        add(path, 'latest_host_named_build_input', required=False)
    for record in external_links:
        for alias in record['surviving_aliases']:
            if alias['inside_project']:
                add(alias['path'], 'surviving_external_hardlink')
    for path in ROUTES:
        add(path, 'current_route')
    hashes, storage, guards = {}, {}, []
    for directory in protected_roots:
        for path, info, is_dir in walk_owned(directory):
            if not is_dir:
                p.require(not inside(path), 'Protected root intersects exact targets')
                row = file_row(path, info, hashes, storage)
                row['reasons'] = sorted(paths.pop(path, set()) | {'scoped_root:' + str(directory.relative_to(ROOT))})
                guards.append(row)
    seen = {row['path'] for row in guards}
    for path, reasons in sorted(paths.items()):
        relative = str(path.relative_to(ROOT))
        if relative in seen:
            continue
        p.boundary(path)
        row = file_row(path, p.regular(path), hashes, storage)
        row['reasons'] = sorted(reasons); guards.append(row); seen.add(relative)
    return ({'documents': references, 'documentation_or_component_holds': documentation_holds,
             'execution_reference_holds': execution_holds, 'retained_runtime_records': runtime_records,
             'manual_runtime_ids': sorted(manual_ids), 'native_saves': saves,
             'manual_save_count': sum(row['manual'] for row in saves),
             'missing_historical_source_with_retained_runtime_copy': missing_historical_sources,
             'protected_roots': [str(x.relative_to(ROOT)) for x in protected_roots],
             'coverage': 'Current Source/tools/Tests, retained Host, named runtime/provider/cache inputs, support roots and saves; no whole-project historical traversal'}, guards)


def main():
    p.require(len(sys.argv) == 1, 'Inventory-only script has no seal/apply/replay options')
    p.require(ROOT == p.ROOT and OUT == ROOT / 'evidence/storage_cleanup/20261009_failed_economic_runs', 'Wrong root/output')
    p.boundary(OUT)
    p.require(p.digest(HELPER) == HELPER_SHA, 'Reusable safety helper changed')
    allowed_before_inventory = {'prepare.py', 'diagnostics.json.gz', 'preparation-observation.json'}
    p.require(not any(x.name not in allowed_before_inventory for x in OUT.iterdir()),
              'Draft inventory/plan already exists; never replay/overwrite')
    processes = process_audit()
    for target in TARGETS:
        p.legal_target(target)
    run_states = []
    for run, session in RUNS.items():
        evidence = ROOT / 'evidence/interactive_game' / run
        result, request, driver = read(evidence / 'result.json'), read(evidence / 'request.json'), read(evidence / 'driver_result.json')
        p.require(result['run_id'] == run and result['status'].endswith('_FAILED') and result['returncode'] == 1,
                  'Target no longer has the exact terminal failure')
        p.require(request['smoke'] and request['economic_overview_smoke'], 'Target is not the authorized smoke runtime')
        run_states.append({'run_id': run, 'session_id': session, 'result_status': result['status'],
                           'driver_status': driver['status'], 'driver_error': driver.get('error')})
    old_report = read(ROOT / 'evidence/ui_window_host' / OLD_HOST / 'build_result.json')
    old_sha = old_report['executable']['sha256']
    p.require(p.digest(Path(old_report['executable']['path'])) == old_sha, 'Old Host executable changed')
    rows, dirs, hashes, storage = [], [], {}, {}
    for target in TARGETS:
        for path, info, is_dir in walk_owned(target):
            if is_dir:
                dirs.append({'path': str(path.relative_to(ROOT)), 'device': int(info.st_dev),
                             'file_id': int(info.st_ino), 'mtime_ns': info.st_mtime_ns})
            else:
                if path.suffix.lower() == '.zssave':
                    p.require(any(path == ROOT / 'Build/InteractiveGameRuntime' / run / 'sessions' / session /
                                  'autosave-0-turn-0.zssave' for run, session in RUNS.items()),
                              'Unreviewed/user save appeared in exact targets')
                rows.append(file_row(path, info, hashes, storage))
        print(json.dumps({'phase': 'target_inventoried', 'path': str(target.relative_to(ROOT)), 'cumulative_files': len(rows)}), flush=True)
    rows.sort(key=lambda row: row['path'].casefold())
    identities, aliases = link_audit(rows)
    references, guards = reference_and_protection_audit(aliases)
    for save in references['native_saves']:
        p.require(old_sha not in save['bundle_identity'], 'A retained save requires the retired Host')
    diagnostic_artifact, diagnostics, diagnostic_bytes = preserve_diagnostics()
    artifacts = {'diagnostics': diagnostic_artifact}
    for name, value in (('retired-files.json.gz', rows), ('retired-directories.json.gz', dirs),
                        ('external-hardlinks.json.gz', aliases), ('references.json.gz', references),
                        ('protected-draft.json.gz', guards)):
        artifacts[name] = write_new(name, value, True)
    groups = []
    for target in TARGETS:
        subset = [row for row in rows if (ROOT / row['path']).is_relative_to(target)]
        keys = {(row['device'], row['file_id']) for row in subset}
        groups.append({'path': str(target.relative_to(ROOT)), 'absolute_path': str(target), 'files': len(subset),
                       'logical_bytes': sum(row['bytes'] for row in subset),
                       'unique_file_storage_bytes': sum(identities[key]['sample']['stored_bytes'] for key in keys)})
    reclaim = sum(value['sample']['stored_bytes'] for value in identities.values()
                  if len(value['target_paths']) == value['sample']['links'])
    report = {'status': 'DRAFT_INVENTORY_ONLY_NOT_SEALED_NO_DELETION', 'created_utc': datetime.now(timezone.utc).isoformat(),
              'root': str(ROOT), 'exact_runs': RUNS, 'retired_host': OLD_HOST, 'retained_host': KEEP_HOST,
              'explicit_retained_fresh_restore_runs': list(KEEP_NEW_RUNS),
              'targets': groups, 'files': len(rows), 'logical_bytes': sum(row['bytes'] for row in rows),
              'unique_file_storage_bytes': sum(value['sample']['stored_bytes'] for value in identities.values()),
              'estimated_reclaimable_file_storage_bytes': reclaim, 'external_linked_identities': len(aliases),
              'external_surviving_aliases': sum(len(row['surviving_aliases']) for row in aliases),
              'protected_draft_files': len(guards), 'manual_saves': references['manual_save_count'],
              'protected_reason_counts': dict(Counter(reason for row in guards for reason in row['reasons'])),
              'diagnostic_files': len(diagnostics), 'diagnostic_unique_source_bytes': diagnostic_bytes,
              'diagnostic_compressed_bytes': diagnostic_artifact['bytes'], 'run_states': run_states,
              'processes_observed': processes, 'source_snapshot_is_not_a_final_seal': True,
              'script_sha256': p.digest(Path(__file__)), 'safety_helper_sha256': HELPER_SHA, 'artifacts': artifacts}
    inventory = write_new('inventory.json', report)
    plan = {'status': 'DRAFT_HOLD_FOR_SUCCESS_AND_RENDERER_CAPTURE_RELEASE', 'deletion_implemented': False,
            'exact_absolute_targets': [str(x) for x in TARGETS], 'inventory': inventory,
            'retained_host': KEEP_HOST, 'draft_protected_files': len(guards), 'manual_saves': references['manual_save_count'],
            'explicit_retained_fresh_restore_runs': list(KEEP_NEW_RUNS),
            'holds': ['New successful economic native execution is not yet accepted for this draft',
                      'Root must release the second failed play-ui-45 capture after renderer regression work',
                      'Update current documentation/component provenance links that still point to retiring raw paths',
                      'Refresh current Source/tools/Tests/runtime/provider/save protection after source freeze; draft hashes are not a seal'],
            'execution_reference_holds': references['execution_reference_holds'],
            'documentation_or_component_holds': references['documentation_or_component_holds'],
            'apply_contract': [
                'A separately reviewed one-use entry point must pin this script/helper/inventory/artifact SHA and newly sealed plan SHA; refuse any existing apply marker',
                'Re-read surviving requests/current routes and accepted replacement result, all eight manual saves and their bundle dependencies; re-evaluate named dependencies without whole-project historical scanning',
                'Freshly hash the explicit protected set before application; no digest reuse across inventory, sealing, pre-delete and post-delete phases',
                'Re-enumerate exactly six target directories once; reject added/missing files/directories and any target path outside these literal resolved project Build/evidence boundaries',
                'Reject reparse files and ancestors; compare each target device/file ID/size/mtime/SHA/attributes and current hardlink name set with the sealed ledger',
                'Immediately before each unlink, re-check target path boundary, identity/mtime/SHA and exclusive READ+DELETE open; abort if any exact target Host/compiler/renderer is active',
                'Unlink only the named alias without changing shared file attributes; external hardlink paths must retain identity/content/mtime/attributes, allowing only the expected link-count decrement',
                'Remove only inventoried empty directories after child removal; never use broad recursive deletion',
                'Verify explicit protected paths/SHA and manual saves/current Host/runtime after deletion; distinguish removed logical bytes, actually unlinked storage and observed volume free-space changes',
                'Checkpoint once before mutation and after every removed path; a failed/partially applied plan must never be replayed'],
            'no_seal_or_apply_performed': True}
    draft = write_new('plan-draft.json', plan)
    print(json.dumps({'status': report['status'], 'files': len(rows), 'logical_bytes': report['logical_bytes'],
                      'estimated_reclaimable_file_storage_bytes': reclaim, 'external_linked_identities': len(aliases),
                      'protected_draft_files': len(guards), 'manual_saves': report['manual_saves'],
                      'diagnostic_files': len(diagnostics), 'diagnostic_compressed_bytes': diagnostic_artifact['bytes'],
                      'inventory': inventory, 'plan_draft': draft}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    if sys.argv[1:] == ['--check-final-gates']:
        print(json.dumps(final_gate(), ensure_ascii=False))
    else:
        main()
