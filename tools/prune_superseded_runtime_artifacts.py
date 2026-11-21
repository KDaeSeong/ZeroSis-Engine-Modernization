"""Retire obsolete runtime/build evidence under the user's 2026-10-05 cleanup instruction.

Historical references are intentionally retired, not treated as perpetual retention.
The current/manual dependency closure and user saves remain protected. A compact
gzip file ledger records every deleted path, identity, byte count and SHA-256.
"""
from __future__ import annotations
import argparse
from collections import defaultdict, deque
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
RUN = re.compile(r'\d{8}T\d{6}Z_[0-9a-f]{12}')
SHA = re.compile(r'[0-9a-f]{64}', re.I)
LATEST = ['20261005T124511Z_ad7083cc8304', '20261005T125355Z_d882b8fab075']
BUILD = '20261005T124208Z_65c9f8ce7280'
WINDOW = '20261005T123839Z_6694ccd3719b'
PROOFS = ('20261005T125352Z_1af8a4f8a77f', '20261005T125715Z_e4b893bfa12a')
ANIMATION_PROOFS = ('20261005T125315Z_a906278c8d90', '20261005T125729Z_cf1ba850d111')
RETIRED_PROOFS = ('20261005T112411Z_3eeee19aa141', '20261005T112658Z_b53df3cd412b',
                  '20261005T124956Z_7def9fe9cd29')
# Preserve the exact historical loader without retaining its superseded test
# directory. Sealed manifests remain unchanged; this explicit relocation is
# recorded in each new cleanup plan and verified against their expected hash.
PROVENANCE_RELOCATIONS = {
    ROOT / 'Build/terrain_renderer_validation/20261005T114415Z/sources/WorldUnitAssets.h': (
        ROOT / 'Build/UnitAssets/b36aa9c2b78af7e597357275abaf9763abd7c252f6eb721d49921cf2a06f4b94/WorldUnitAssets.v1.h',
        '6d28737959b0b359636bdba4932145521245a63b060fc833fa5faca518b02de2'),
}
GROUPS = {
    'InteractiveGameRuntime': ['interactive_game'],
    'NewGameRuntime': ['new_game', 'first_turn', 'turn_cycle', 'save_restore'],
    'CityDecisionRuntime': ['city_decisions'],
    'CityProductionUiRuntime': ['city_production_ui'],
    'CityResearchTreeUiRuntime': ['city_research_tree_ui'],
    'CityResearchUiRuntime': ['city_research_ui'],
    'FoundCityRuntime': ['found_city'],
    'HostRuntime': ['host_runtime'],
    'UiWindowHost': ['ui_window_host'],
    'BitmapWindow': ['bitmap_window'],
}
K = ctypes.WinDLL('kernel32', use_last_error=True)
K.GetCompressedFileSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
K.GetCompressedFileSizeW.restype = wintypes.DWORD
K.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                        wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
K.CreateFileW.restype = wintypes.HANDLE
K.SetFileInformationByHandle.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
K.SetFileInformationByHandle.restype = wintypes.BOOL
K.CloseHandle.argtypes = [wintypes.HANDLE]


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def regular(path):
    info = path.lstat()
    require(not getattr(info, 'st_file_attributes', 0) & 0x400, 'Reparse point: ' + str(path))
    require(stat.S_ISREG(info.st_mode), 'Not a regular file: ' + str(path))
    return info


def boundary(path):
    absolute = Path(os.path.abspath(path))
    require(absolute.is_relative_to(ROOT) and absolute != ROOT, 'Outside project: ' + str(path))
    require(absolute.resolve(strict=True) == absolute, 'Resolved path differs: ' + str(path))
    for ancestor in [absolute, *absolute.parents]:
        require(not getattr(ancestor.lstat(), 'st_file_attributes', 0) & 0x400,
                'Reparse ancestor: ' + str(ancestor))
        if ancestor == ROOT:
            break
    return absolute


def stored(path):
    high = wintypes.DWORD()
    ctypes.set_last_error(0)
    low = K.GetCompressedFileSizeW(str(path), ctypes.byref(high))
    if low == 0xffffffff and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    return (high.value << 32) | low


def no_active_host():
    bundled = Path(r'C:\Users\home\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe')
    shell = str(bundled) if bundled.is_file() else 'powershell.exe'
    result = subprocess.run([shell, '-NoLogo', '-NoProfile', '-Command',
        "@(Get-Process -Name ZeroSisHost_x64,cl,link,Civ5,CivilizationV -ErrorAction SilentlyContinue).Count"],
        capture_output=True, text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0 and result.stdout.strip() == '0', 'Host/compiler is active or status is unknown')


def refs(node):
    if isinstance(node, list):
        for child in node:
            yield from refs(child)
    elif isinstance(node, dict):
        if isinstance(node.get('path'), str) and SHA.fullmatch(str(node.get('sha256', ''))):
            yield node['path'], node['sha256'].lower()
        for key, child in node.items():
            if isinstance(child, str) and os.path.isabs(key) and SHA.fullmatch(child):
                yield key, child.lower()
            elif isinstance(child, (dict, list)):
                yield from refs(child)


def closure(seeds):
    pending, visited, protected = deque(seeds), set(), {}
    while pending:
        path = Path(pending.popleft()).resolve(strict=True)
        if path in visited:
            continue
        visited.add(path)
        protected[str(path)] = digest(path)
        document = json.loads(path.read_text(encoding='utf-8-sig'))
        for name, expected in refs(document):
            target = Path(name)
            if target in PROVENANCE_RELOCATIONS:
                relocated, sha = PROVENANCE_RELOCATIONS[target]
                require(expected == sha and digest(boundary(relocated)) == sha,
                        'Historical source relocation differs from sealed provenance')
                if target.exists():
                    require(digest(boundary(target)) == sha, 'Historical source was edited before retirement')
                target = relocated
            if not target.is_absolute() or not target.is_relative_to(ROOT) or not target.is_file():
                continue
            # Source annotations from past builds are not execution artifacts;
            # preserve the tree but use current bytes for before/after checks.
            protected.setdefault(str(target), None)
            if target.suffix.lower() == '.json' and target not in visited:
                pending.append(target)
    return protected, visited


def inventory(directory):
    for current, dirs, files in os.walk(directory, followlinks=False):
        current = boundary(Path(current))
        for name in dirs:
            boundary(current / name)
        for name in files:
            path = current / name
            yield path, regular(path)


def legal_target(path):
    path = boundary(path)
    parts = path.relative_to(ROOT).parts
    if len(parts) == 2 and parts[0] == 'validators':
        require(parts[1] in RETIRED_PROOFS, 'Unreviewed retired validator: ' + str(path))
        return path
    require(len(parts) == 3 and RUN.fullmatch(parts[2]), 'Unexpected retired directory: ' + str(path))
    require((parts[0] == 'Build' and parts[1] in GROUPS) or
            (parts[0] == 'evidence' and parts[1] in {x for names in GROUPS.values() for x in names}),
            'Unapproved retirement group: ' + str(path))
    return path


def plan():
    no_active_host()
    manual = list(dict.fromkeys(RUN.findall((ROOT / 'tools/Start-Engine.ps1').read_text(encoding='utf8'))))
    # Retention seeds are an explicit approved baseline, not a license to remove future work.
    newer = [str(path.relative_to(ROOT)) for path in (ROOT / 'Build/InteractiveGameRuntime').iterdir()
             if path.is_dir() and RUN.fullmatch(path.name) and path.name > max(LATEST) and path.name not in manual]
    newer += [str(path.relative_to(ROOT)) for path in (ROOT / 'Build/UiWindowHost').iterdir()
              if path.is_dir() and RUN.fullmatch(path.name) and path.name > BUILD]
    newer += [str(path.relative_to(ROOT)) for path in (ROOT / 'Build/BitmapWindow').iterdir()
              if path.is_dir() and RUN.fullmatch(path.name) and path.name > WINDOW]
    require(not newer, 'Newer work requires refreshed retention seeds before planning: ' + ', '.join(newer))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    output = ROOT / 'evidence/storage_cleanup' / stamp
    output.mkdir(parents=True)
    seeds = [ROOT / 'evidence' / name for name in (
        'shared_lua_runtime/build_result.json', 'explore_sdk/build_result.json',
        'city_site_sdk/build_result.json', 'found_value_shared_sdk/build_result.json', 'host/bundle.json',
        'database/candidate/build_result.json', 'localization/provider/build_result.json',
        'streams/provider/build_result.json', 'temp_heap/build_result.json',
        f'ui_window_host/{BUILD}/build_result.json',
        f'bitmap_window/{WINDOW}/conformance.json')]
    for run in [*manual, *LATEST]:
        seeds.append(ROOT / 'evidence/interactive_game' / run / 'request.json')
        result = ROOT / 'evidence/interactive_game' / run / 'result.json'
        if result.is_file():
            seeds.append(result)
    seeds += [ROOT / 'validators' / run / 'conformance.json' for run in PROOFS]
    seeds += [ROOT / 'validators' / run / 'animation.json' for run in ANIMATION_PROOFS]
    protected, documents = closure(seeds)
    protected[str(ROOT / 'tools/Start-Engine.ps1')] = None
    require(len(protected) > 100 and len(documents) > 20, 'Current artifact closure unexpectedly small')
    protected_roots = {Path(path).relative_to(ROOT).parts[:3] for path in protected}
    keep = {(group, Path(path).relative_to(ROOT).parts[2]) for path in protected
            if (parts := Path(path).relative_to(ROOT).parts) and len(parts) >= 3 and parts[0] == 'Build'
            for group in GROUPS if parts[1] == group}
    keep.update(('InteractiveGameRuntime', run) for run in [*manual, *LATEST])
    keep.add(('UiWindowHost', BUILD))
    keep.add(('BitmapWindow', WINDOW))
    candidates, retired = [], []
    for group, evidence_groups in GROUPS.items():
        for directory in sorted((ROOT / 'Build' / group).iterdir()):
            if not directory.is_dir() or not RUN.fullmatch(directory.name) or (group, directory.name) in keep:
                continue
            candidates.append(legal_target(directory))
            statuses = []
            for category in evidence_groups:
                evidence = ROOT / 'evidence' / category / directory.name
                if evidence.is_dir():
                    if evidence.relative_to(ROOT).parts in protected_roots:
                        raise RuntimeError('Retained metadata refers to a retired evidence directory: ' + str(evidence))
                    candidates.append(legal_target(evidence))
                    for name in ('result.json', 'build_result.json'):
                        report = evidence / name
                        if report.is_file():
                            record = json.loads(report.read_text(encoding='utf-8-sig'))
                            statuses.append({'category': category, 'status': record.get('status'), 'report_sha256': digest(report)})
            retired.append({'group': group, 'run_id': directory.name, 'historical_status': statuses,
                            'retained_raw_artifacts': False})
    for run in RETIRED_PROOFS:
        directory = ROOT / 'validators' / run
        if directory.is_dir():
            require(not any(Path(name).is_relative_to(directory) for name in protected),
                    'Current evidence still requires retired validator: ' + str(directory))
            candidates.append(legal_target(directory))
            proof = directory / 'conformance.json'
            record = json.loads(proof.read_text(encoding='utf-8-sig'))
            retired.append({'group': 'validators', 'run_id': run,
                            'historical_status': record.get('status'),
                            'report_sha256': digest(proof), 'retained_raw_artifacts': False})
    require(candidates and len(set(candidates)) == len(candidates), 'Empty or duplicate retirement candidates')
    for directory in candidates:
        require(directory.relative_to(ROOT).parts not in protected_roots, 'Candidate intersects the current dependency closure')
    # Hash retained files once per identity, including every actual manual save.
    for run in manual:
        session = ROOT / 'Build/InteractiveGameRuntime' / run / 'sessions'
        if session.is_dir():
            for path in session.rglob('*.zssave'):
                protected[str(path)] = None
    hash_cache = {}
    for name in protected:
        path = Path(name)
        info = regular(path)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in hash_cache:
            hash_cache[identity] = digest(path)
        protected[name] = hash_cache[identity]
    print(json.dumps({'phase': 'protected_current_dependencies', 'files': len(protected), 'json_documents': len(documents)}), flush=True)
    protected_file = output / 'protected.json.gz'
    with gzip.open(protected_file, 'wt', encoding='utf8') as stream:
        json.dump(protected, stream, separators=(',', ':'))
    ledger = output / 'retired-files.jsonl.gz'
    summaries, total, logical, identities = [], 0, 0, {}
    with gzip.open(ledger, 'wt', encoding='utf8') as stream:
        for index, directory in enumerate(candidates):
            count = size = 0
            for path, info in inventory(directory):
                identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                if identity not in hash_cache:
                    hash_cache[identity] = digest(path)
                item = identities.setdefault((info.st_dev, info.st_ino),
                    {'links': info.st_nlink, 'count': 0, 'stored': stored(path)})
                item['count'] += 1
                row = {'path': str(path.relative_to(ROOT)), 'sha256': hash_cache[identity], 'bytes': info.st_size,
                       'mtime_ns': info.st_mtime_ns, 'device': info.st_dev, 'file_id': info.st_ino}
                stream.write(json.dumps(row, separators=(',', ':')) + '\n')
                count += 1
                size += info.st_size
            summaries.append({'path': str(directory.relative_to(ROOT)), 'files': count, 'logical_bytes': size})
            total += count
            logical += size
            if index % 20 == 0:
                print(json.dumps({'phase': 'inventory', 'directories': index + 1, 'total_directories': len(candidates),
                                  'files': total, 'logical_gib': round(logical/1024**3, 3)}), flush=True)
    report = {'status': 'PREVIEW_ONLY', 'scope': 'USER_REQUESTED_RETIREMENT_OF_SUPERSEDED_PRIVATE_RUNTIME_AND_BUILD_EVIDENCE',
              'root': str(ROOT), 'user_instruction': '주요 자료 전부 정리해. 저 많은 파일을 다 들고 있을 이유가 전혀 없잖아?',
              'manual_runtimes': manual, 'latest_runtime_pair': LATEST, 'latest_host_build': BUILD,
              'latest_bitmap_window_component': WINDOW,
              'historical_source_relocations': [
                  {'retired_path': str(old), 'path': str(new), 'sha256': sha}
                  for old, (new, sha) in PROVENANCE_RELOCATIONS.items()],
              'kept_groups': sorted([list(x) for x in keep]), 'seed_documents': list(map(str, seeds)),
              'current_dependency_files': len(protected), 'current_json_documents': len(documents),
              'protected': {'path': str(protected_file), 'sha256': digest(protected_file)},
              'ledger': {'path': str(ledger), 'sha256': digest(ledger)},
              'directories': summaries, 'retired_runs': retired, 'files': total, 'logical_bytes': logical,
              'estimated_reclaimable_file_storage': sum(v['stored'] for v in identities.values() if v['links'] == v['count']),
              'historical_retention_policy': 'Obsolete reports and their raw files are retired together; old raw-file links are no longer available.',
              'source_tools_tests_game_mods_user_saves_deleted': False,
              'script_sha256': digest(Path(__file__))}
    destination = output / 'plan.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'plan': str(destination), 'files': total,
                      'logical_gib': round(logical/1024**3, 3),
                      'estimated_reclaimable_gib': round(report['estimated_reclaimable_file_storage']/1024**3, 3),
                      'directories': len(candidates)}, ensure_ascii=False), flush=True)


def unlink_without_attribute_changes(path):
    # SDK winbase.h: FileDispositionInfoEx=21; DELETE|POSIX|IGNORE_READONLY=0x13.
    handle = K.CreateFileW(str(path), 0x10000, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        flags = wintypes.DWORD(0x13)
        if not K.SetFileInformationByHandle(handle, 21, ctypes.byref(flags), 4):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        K.CloseHandle(handle)


def apply(plan_path):
    no_active_host()
    plan_path = boundary(plan_path)
    require(plan_path.is_relative_to(ROOT / 'evidence/storage_cleanup'), 'Plan outside cleanup evidence')
    require(not (plan_path.parent / 'cleanup.json').exists(), 'This plan was already started; review its cleanup report instead of replaying it')
    report = json.loads(plan_path.read_text(encoding='utf8'))
    require(report['root'] == str(ROOT) and report['status'] == 'PREVIEW_ONLY', 'Wrong root or plan status')
    require(report['script_sha256'] == digest(Path(__file__)), 'Cleanup script changed after review')
    for name in ('ledger', 'protected'):
        path = boundary(Path(report[name]['path']))
        require(path.parent == plan_path.parent and digest(path) == report[name]['sha256'], 'Cleanup ledger changed')
    targets = [legal_target(ROOT / row['path']) for row in report['directories']]
    with gzip.open(report['protected']['path'], 'rt', encoding='utf8') as stream:
        protected = json.load(stream)
    target_roots = {path.relative_to(ROOT).parts for path in targets}
    def in_targets(path):
        parts = path.relative_to(ROOT).parts
        return any(parts[:len(prefix)] == prefix for prefix in target_roots)
    require(not any(in_targets(Path(p)) for p in protected), 'Protected file in deletion set')
    verified = {}
    for name, expected in protected.items():
        path = Path(name)
        info = regular(path)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in verified:
            verified[identity] = digest(path)
        require(verified[identity] == expected, 'Preserved content changed before cleanup: ' + name)
    # Verify read-only hardlink deletion cannot alter the surviving link's attributes or bytes.
    test = plan_path.parent / 'readonly-hardlink-check'
    test.mkdir()
    source, alias = test / 'source', test / 'alias'
    source.write_bytes(b'preserved-readonly-hardlink')
    os.link(source, alias)
    os.chmod(source, stat.S_IREAD)
    attrs = source.stat().st_file_attributes
    unlink_without_attribute_changes(alias)
    require(not alias.exists() and source.read_bytes() == b'preserved-readonly-hardlink'
            and source.stat().st_file_attributes == attrs, 'Readonly hardlink deletion self-test failed')
    unlink_without_attribute_changes(source)
    test.rmdir()
    progress = {'status': 'REMOVING', 'plan_sha256': digest(plan_path), 'removed_files': 0, 'removed_logical_bytes': 0,
                'completed_directories': [], 'protected_hashes_verified_before': True,
                'readonly_hardlink_attribute_preservation_verified': True,
                'volume_free_bytes_before': shutil.disk_usage(ROOT).free, 'errors': []}
    output = plan_path.parent / 'cleanup.json'
    def checkpoint():
        output.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    checkpoint()
    try:
        no_active_host()
        with gzip.open(report['ledger']['path'], 'rt', encoding='utf8') as stream:
            for line in stream:
                row = json.loads(line)
                path = ROOT / row['path']
                require(path.is_relative_to(ROOT) and '..' not in path.parts and
                        in_targets(path), 'File outside approved target')
                info = regular(path)
                require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
                        (row['device'], row['file_id'], row['bytes'], row['mtime_ns']), 'Retired file identity changed: ' + str(path))
                require(info.st_nlink == row.get('links', info.st_nlink), 'Retired hardlink count changed: ' + str(path))
                require(info.st_file_attributes == row.get('attributes', info.st_file_attributes) and
                        info.st_mode == row.get('mode', info.st_mode), 'Retired file metadata changed: ' + str(path))
                require(digest(path) == row['sha256'], 'Retired file content changed: ' + str(path))
                unlink_without_attribute_changes(path)
                require(not path.exists(), 'Retired file remains: ' + str(path))
                progress['removed_files'] += 1
                progress['removed_logical_bytes'] += row['bytes']
                if progress['removed_files'] % 1000 == 0:
                    checkpoint()
                    print(json.dumps({'phase': 'delete', 'files': progress['removed_files'], 'planned': report['files']}), flush=True)
        for target in targets:
            for current, dirs, files in os.walk(target, topdown=False, followlinks=False):
                require(not files, 'Unplanned file remains in retired directory')
                boundary(Path(current)).rmdir()
            progress['completed_directories'].append(str(target.relative_to(ROOT)))
        verified.clear()
        for name, expected in protected.items():
            path = Path(name)
            info = regular(path)
            identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
            if identity not in verified:
                verified[identity] = digest(path)
            require(verified[identity] == expected, 'Preserved content changed after cleanup: ' + name)
        require(progress['removed_files'] == report['files'], 'Deletion count differs')
        progress['protected_hashes_verified_after'] = True
        progress['status'] = 'PASS_OBSOLETE_ARTIFACT_RETIREMENT'
    except Exception as error:
        progress['status'] = 'FAILED_PARTIAL_RETIREMENT_RETAINED'
        progress['errors'].append(type(error).__name__ + ': ' + str(error))
        raise
    finally:
        progress['volume_free_bytes_after'] = shutil.disk_usage(ROOT).free
        progress['volume_free_bytes_delta'] = progress['volume_free_bytes_after'] - progress['volume_free_bytes_before']
        checkpoint()
        print(json.dumps({'status': progress['status'], 'removed_files': progress['removed_files'],
                          'removed_logical_gib': round(progress['removed_logical_bytes']/1024**3, 3),
                          'report': str(output), 'errors': progress['errors']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--apply', type=Path)
    options = parser.parse_args()
    if options.apply:
        apply(options.apply)
    else:
        plan()
