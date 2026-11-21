"""Retire exact superseded inputs and compiler objects through a pinned plan."""
import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import re
import stat
import sys

from run_stage import PROJECT, STAGE, artifact, read, require, write
sys.path.insert(0, str(PROJECT / 'tools'))
import prune_superseded_runtime_artifacts as safety

BUILD_ID = '20261016T110835Z_800f48fd88c0'
OLD_ID = '20261014T215629Z_9b67a5d13f24'
CLEANUP = STAGE / 'cleanup'
PLAN = CLEANUP / 'plan.json.gz'
RESULT = CLEANUP / 'result.json'
JOURNAL = CLEANUP / 'removed.jsonl'


class StandardInfo(ctypes.Structure):
    _fields_ = [('allocation', ctypes.c_longlong), ('end', ctypes.c_longlong),
                ('links', wintypes.DWORD), ('delete_pending', ctypes.c_ubyte), ('directory', ctypes.c_ubyte)]


K = safety.K
K.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
K.GetFileInformationByHandleEx.restype = wintypes.BOOL


def snapshot(path):
    path = safety.boundary(Path(path))
    before = safety.regular(path)
    require(before.st_ino and before.st_nlink >= 1, 'No stable file identity')
    handle = K.CreateFileW(str(path), 0x80, 7, None, 3, 0x00200000, None)
    require(handle != ctypes.c_void_p(-1).value, 'Cannot read allocation: ' + str(path))
    try:
        info = StandardInfo()
        if not K.GetFileInformationByHandleEx(handle, 1, ctypes.byref(info), ctypes.sizeof(info)):
            raise ctypes.WinError(ctypes.get_last_error())
    finally:
        K.CloseHandle(handle)
    sha = safety.digest(path)
    after = safety.regular(path)
    fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_nlink', 'st_file_attributes')
    require(tuple(getattr(before, key) for key in fields) == tuple(getattr(after, key) for key in fields),
            'File changed during inventory: ' + str(path))
    return {'path': str(path), 'bytes': before.st_size, 'sha256': sha,
            'identity': [before.st_dev, before.st_ino], 'mtime_ns': before.st_mtime_ns,
            'links': before.st_nlink, 'attributes': before.st_file_attributes,
            'standard_allocation_bytes': info.allocation, 'get_compressed_file_size_bytes': safety.stored(path)}


def verify(rows):
    for row in rows:
        require(snapshot(row['path']) == row, 'Inventoried file changed: ' + row['path'])


def plan():
    require(not CLEANUP.exists(), 'Inspect an existing plan or partial result instead of replanning blindly')
    build_path = PROJECT / f'evidence/ui_window_host/{BUILD_ID}/build_result.json'
    build, prepared = read(build_path), read(STAGE / 'prepared.json')
    attestation_path = STAGE / f'attestation_{BUILD_ID}.json'
    attestation = read(attestation_path)
    require(build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and prepared['status'] == 'PREPARED_NOT_EXECUTED',
            'Current candidate is not ready')
    require(str(attestation['status']).startswith('PASS'), 'Actual PE attestation is required')
    preflight_path = STAGE / 'retirement_preflight.json'
    require(artifact(preflight_path)['sha256'] == '9d53ed339fe9926742aacc76e04fe77cffef94e456386a3a28539e9a5195253b',
            'Reviewed granular candidate list changed')
    preflight = read(preflight_path)
    old_root = PROJECT / f'Build/NativeSaveCatalog/{OLD_ID}'
    host_root = PROJECT / f'Build/UiWindowHost/{BUILD_ID}'
    protected_paths = {row['path'] for row in preflight['protected_named_artifacts']}
    protected_paths.update(row['path'] for row in preflight['retained_old_build']['unique_changed_sources'])
    protected_paths.update(row['path'] for row in preflight['retained_old_build']['small_metadata'])
    protected_paths.update(row['path'] for row in read(STAGE / 'scope.json')['protected_artifacts'].values())
    protected_paths.update((str(build_path), build['executable']['path'], prepared['request']['path'],
                            str(attestation_path), str(PROJECT / 'Source/Host/UiPopupAssets.generated.h')))
    request = read(Path(prepared['request']['path']))
    protected_paths.update(row['path'] for row in request['runtime_inputs'])
    files = []
    for group in preflight['candidates']:
        for row in group['files']:
            path = Path(row['path'])
            require(path.is_relative_to(old_root), 'Older candidate escaped its exact component Build root')
            current = snapshot(path)
            ntfs_id = row['ntfs_file_id']
            require(current['bytes'] == row['bytes'] and current['sha256'] == row['sha256'] and
                    current['identity'][1] == (ntfs_id['index_high'] << 32 | ntfs_id['index_low']) and
                    current['mtime_ns'] // 100 + 116444736000000000 == row['filetime_last_write'] and
                    current['links'] == row['hardlink_count'] == 1, 'Older candidate differs from review')
            if 'replacement' in row:
                replacement = row['replacement']
                require(artifact(Path(replacement['path']))['sha256'] == current['sha256'], 'Retained duplicate differs')
                protected_paths.add(replacement['path'])
            files.append({**current, 'reason': group['group']})
    require(len(files) == 395, 'Unexpected older granular candidate count')
    for tu in build['dependency_discovery']['translation_units']:
        for row in tu['objects']:
            path = Path(row['path'])
            require(path.is_relative_to(host_root / 'dependency_discovery') and path.suffix.lower() == '.obj',
                    'Unexpected discovery intermediate')
            current = snapshot(path)
            require(current['sha256'] == row['sha256'], 'Compiler object differs from build report')
            files.append({**current, 'reason': 'current_completed_discovery_object'})
    link_response = Path(build['link_response']['path']).read_text(encoding='utf8')
    roles = (('host_main', 'HostMain'), ('window', 'BitmapWindow'), ('renderer', 'BitmapRenderer'),
             ('world_renderer', 'WorldViewRenderer'), ('terrain_renderer', 'WorldTerrainRenderer'))
    for index, (role, name) in enumerate(roles):
        path = host_root / f'final/tu_{index:02d}_{role}/obj/{name}.obj'
        require(str(path) in link_response, 'Final intermediate is absent from actual link response')
        files.append({**snapshot(path), 'reason': 'current_completed_final_object'})
    require(len(files) == 405 and len({row['path'] for row in files}) == 405 and
            all(row['links'] == 1 for row in files), 'Unexpected or shared cleanup file set')
    protected = [snapshot(path) for path in sorted(protected_paths)]
    require(not {tuple(row['identity']) for row in files}.intersection(tuple(row['identity']) for row in protected),
            'Cleanup aliases protected content')
    CLEANUP.mkdir()
    payload = {'schema': 'zerosis.owned_save_delete.exact_cleanup.v1', 'utc': datetime.now(timezone.utc).isoformat(),
        'files': files, 'protected': protected, 'review': artifact(preflight_path), 'build': artifact(build_path),
        'attestation': artifact(attestation_path), 'prepared': artifact(STAGE / 'prepared.json'),
        'old_unique_sources_and_metadata_retained': True, 'retail_mods_saves_or_processes_accessed': False,
        'limits': 'Historical older-component reports lose executable/dependency reproducibility; current and prior component baselines are retained.'}
    PLAN.write_bytes(gzip.compress((json.dumps(payload, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf8'), mtime=0))
    print(json.dumps({'status': 'PLANNED', 'plan': artifact(PLAN), 'files': len(files),
                      'logical_bytes': sum(row['bytes'] for row in files),
                      'standard_allocation_bytes': sum(row['standard_allocation_bytes'] for row in files),
                      'protected': len(protected)}))


def apply(expected_sha):
    require(expected_sha and artifact(PLAN)['sha256'] == expected_sha, 'Exact plan SHA is required')
    require(not RESULT.exists() and not JOURNAL.exists(), 'Never replay a completed or partial cleanup plan')
    payload = json.loads(gzip.decompress(PLAN.read_bytes()))
    files, protected = payload['files'], payload['protected']
    verify(protected)
    verify([{key: value for key, value in row.items() if key != 'reason'} for row in files])
    record = {'status': 'IN_PROGRESS', 'plan': artifact(PLAN), 'removed_files': 0,
              'removed_logical_bytes': 0, 'removed_standard_allocation_bytes': 0,
              'removed_get_compressed_file_size_bytes': 0, 'protected_unchanged': False,
              'retail_mods_user_saves_or_processes_accessed': False}
    write(RESULT, record)
    try:
        with JOURNAL.open('x', encoding='utf8') as journal:
            for index, row in enumerate(files):
                require(snapshot(row['path']) == {key: value for key, value in row.items() if key != 'reason'},
                        'Target changed immediately before deletion')
                safety.unlink_without_attribute_changes(Path(row['path']))
                require(not os.path.lexists(row['path']), 'Retired target still exists')
                journal.write(json.dumps({'plan_index': index, 'path': row['path'], 'result': 'REMOVED_ABSENT'}) + '\n')
                journal.flush()
                record['removed_files'] += 1
                record['removed_logical_bytes'] += row['bytes']
                record['removed_standard_allocation_bytes'] += row['standard_allocation_bytes']
                record['removed_get_compressed_file_size_bytes'] += row['get_compressed_file_size_bytes']
                write(RESULT, record)
        verify(protected)
        record.update(status='COMPLETE', protected_unchanged=True,
                      targets_absent=all(not os.path.lexists(row['path']) for row in files), journal=artifact(JOURNAL))
    except Exception as error:
        record.update(status='PARTIAL_DO_NOT_REPLAY', error=type(error).__name__ + ': ' + str(error))
        raise
    finally:
        write(RESULT, record)
    print(json.dumps({**record, 'result': artifact(RESULT)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('plan', 'apply'))
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    plan() if args.action == 'plan' else apply(args.plan_sha256)
