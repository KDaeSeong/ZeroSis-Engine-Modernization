"""Small, explicit storage receipts for the offline menu implementation."""
from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import os
from pathlib import Path

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/game_menu/offline_menu_suite'
spec = importlib.util.spec_from_file_location('exit_storage', PROJECT / 'tools/audit_exit_host_storage.py')
storage = importlib.util.module_from_spec(spec)
spec.loader.exec_module(storage)


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def baseline():
    target = STAGE / 'protection_before.json'
    if target.exists():
        return storage.read(target)
    old = storage.read(PROJECT / 'evidence/game_menu/exit_host_build/protection_before.json')
    refs = {storage.key(row['path']): row for row in old['protected_artifacts']}
    report_path = PROJECT / 'evidence/ui_window_host/20261026T133507Z_ea39cdb67229/build_result.json'
    report = storage.read(report_path)
    frozen = PROJECT / 'Build/UiWindowHost/20261026T133507Z_ea39cdb67229/frozen'
    for row in storage.path_rows(report):
        path = Path(row['path'])
        if path.is_absolute() and path.is_relative_to(frozen):
            refs[storage.key(path)] = row
    for row in (report['executable'], dict(path=str(report_path), sha256=storage.digest(report_path))):
        refs[storage.key(row['path'])] = row
    rows, ids = [], {}
    for expected in refs.values():
        path = expected['path']
        before = storage.ordinary(path)
        identity = (before.st_dev, before.st_ino)
        if identity not in ids:
            ids[identity] = (storage.digest(path), storage.allocated(path))
        sha, allocation = ids[identity]
        assert sha == expected['sha256'], path
        assert storage.metadata(before) == storage.metadata(storage.ordinary(path)), path
        rows.append(dict(path=path, sha256=sha, allocated_bytes=allocation, **storage.metadata(before)))
    result = dict(schema='zerosis.menu_suite.protection.v1', protected_artifacts=rows,
                  protected_paths=len(rows), unique_file_ids=len(ids),
                  unique_allocated_bytes=sum(item[1] for item in ids.values()),
                  native_execution=False)
    write_new(target, result)
    return result


def backup(relative):
    path = PROJECT / relative
    storage.ordinary(path)
    sha = storage.digest(path)
    target = STAGE / 'source_backups' / (relative.replace('\\', '__').replace('/', '__') + '.' + sha[:12] + '.gz')
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(gzip.compress(path.read_bytes(), mtime=0))
        write_new(target.with_suffix('.json'), dict(path=str(path), sha256=sha,
                  **storage.metadata(storage.ordinary(path)), backup=str(target), backup_sha256=storage.digest(target)))
    return dict(path=str(path), sha256=sha, backup=str(target))


def verify():
    before = storage.read(STAGE / 'protection_before.json')
    differences, link_changes = [], []
    seen = {}
    for row in before['protected_artifacts']:
        current = storage.metadata(storage.ordinary(row['path']))
        identity = tuple(current['file_identity'])
        if identity not in seen:
            seen[identity] = (storage.digest(row['path']), storage.allocated(row['path']))
        if any(current[key] != row[key] for key in ('bytes', 'file_identity', 'mtime_ns', 'file_attributes')) or seen[identity] != (row['sha256'], row['allocated_bytes']):
            differences.append(row['path'])
        if current['links'] != row['links']:
            link_changes.append(dict(path=row['path'], before=row['links'], after=current['links']))
    return dict(status='PASS' if not differences else 'FAIL', protected_paths=before['protected_paths'],
                content_or_identity_differences=differences, observed_link_count_changes=link_changes,
                native_execution=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('baseline', 'backup', 'verify', 'measure'))
    parser.add_argument('paths', nargs='*')
    args = parser.parse_args()
    if args.action == 'baseline':
        value = baseline()
        print(json.dumps({key: value[key] for key in ('protected_paths', 'unique_file_ids', 'unique_allocated_bytes')}))
    elif args.action == 'backup':
        print(json.dumps([backup(item) for item in args.paths]))
    elif args.action == 'verify':
        value = verify()
        write_new(STAGE / 'protection_after.json', value)
        print(json.dumps(value))
        assert value['status'] == 'PASS'
    else:
        value = storage.measure_storage()
        write_new(STAGE / 'storage_after.json', value)
        print(json.dumps({key: value[key] for key in ('file_paths', 'unique_allocated_bytes', 'hardlink_aliases_deduplicated')}))


if __name__ == '__main__':
    main()
