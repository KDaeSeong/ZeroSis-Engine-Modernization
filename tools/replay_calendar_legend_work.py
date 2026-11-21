"""Owned offline replay wave receipts; never loads the Host or GameCore."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / 'tools'))
from menu_suite_storage import storage

STAGE = PROJECT / 'evidence/game_menu/replay_calendar_legend'
PREVIOUS = PROJECT / 'evidence/game_menu/menu_runtime_ui_followup'


def read(path):
    return json.loads(Path(path).read_text('utf8'))


def write_new(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='utf8', newline='\n') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')


def ref(path):
    info = storage.ordinary(path)
    return dict(path=str(path), sha256=storage.digest(path), **storage.metadata(info))


def backup(relative):
    path = PROJECT / relative
    row = ref(path)
    out = STAGE / 'source_before' / (relative.replace('/', '__') + '.' + row['sha256'][:16] + '.gz')
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open('xb') as stream:
            stream.write(gzip.compress(path.read_bytes(), mtime=0))
    if hashlib.sha256(gzip.decompress(out.read_bytes())).hexdigest() != row['sha256']:
        raise ValueError('Changed-file backup does not restore exact source')
    row['backup'] = ref(out)
    return row


def baseline():
    output = STAGE / 'protection_before.json.gz'
    if output.exists():
        raise ValueError('Existing baseline must be inspected, not overwritten')
    refs = {}
    old = read(PREVIOUS / 'protection_before.json')
    extra = read(PREVIOUS / 'retention/20261103T134638Z_59c8f213b4f0/protection_supplement.json')
    for row in old['protected_artifacts'] + extra['additional_protected_artifacts']:
        key = storage.key(row['path'])
        if key in refs and refs[key]['sha256'] != row['sha256']:
            raise ValueError('Contradictory protected source identity')
        refs[key] = row
    rows, ids = [], {}
    for expected in refs.values():
        path = Path(expected['path'])
        before = storage.ordinary(path)
        ident = (before.st_dev, before.st_ino)
        if ident not in ids:
            ids[ident] = (storage.digest(path), storage.allocated(path))
        sha, allocation = ids[ident]
        for key in ('bytes', 'file_identity', 'mtime_ns', 'file_attributes'):
            if storage.metadata(before)[key] != expected[key]:
                raise ValueError('Protected metadata changed before wave: ' + str(path))
        if sha != expected['sha256']:
            raise ValueError('Protected bytes changed before wave: ' + str(path))
        if storage.metadata(before) != storage.metadata(storage.ordinary(path)):
            raise ValueError('Protected path changed while hashing')
        rows.append(dict(path=str(path), sha256=sha, allocated_bytes=allocation, **storage.metadata(before)))
    value = dict(schema='zerosis.replay_calendar_legend.protection.v1',
        utc=datetime.now(timezone.utc).isoformat(), status='PASS_FRESH_PROTECTED_BASELINE',
        protected_paths=len(rows), unique_file_ids=len(ids),
        unique_allocated_bytes=sum(v[1] for v in ids.values()), protected_artifacts=rows,
        previous_baseline=ref(PREVIOUS / 'protection_before.json'),
        additional_baseline=ref(PREVIOUS / 'retention/20261103T134638Z_59c8f213b4f0/protection_supplement.json'),
        native_execution=False)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream:
        stream.write(gzip.compress((json.dumps(value, ensure_ascii=False, indent=2)+'\n').encode('utf8'), mtime=0))
    return dict(status=value['status'], protected_paths=len(rows), unique_file_ids=len(ids), compressed_manifest=ref(output))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('begin', 'measure', 'verify', 'backup'))
    parser.add_argument('paths', nargs='*')
    parser.add_argument('--label', default='before')
    args = parser.parse_args()
    if args.action == 'begin':
        req = dict(schema='zerosis.replay_calendar_legend.requirements.v1',
            scope=['Bind the newest compiled UI and required immutable sidecar into one explicit prepared runtime.',
                   'Restore ReplayViewer five original calendar ticks and the identical padded graph point domain.',
                   'Restore 14px Shadow graph legend font, original geometry, colors and toggle input.',
                   'Resolve active Expansion2 frontend skin through original package priority and fallback.',
                   'Retain all original replay bytes, IDs, save keys and SDK balance; no save-schema migration.',
                   'Keep originals, MODS, user saves, default launcher and global registered profile unchanged.',
                   'Compile C++14 and verify file-only/SDK-free controlled components; never native Host/SDK/window/GPU.',
                   'Reuse immutable data; remove owned regenerable intermediates and measure true-ID-deduplicated allocation.'],
            affected_modules=['Host replay presentation/layout/catalog binding', 'immutable frontend asset reader/producer',
                              'frontend source-skin resolver', 'explicit prepared runtime file pipeline'],
            save_compatibility='Replay/raw save formats and existing IDs unchanged; no retail restore acceptance claimed.',
            deployment='Explicit prepared profile only; global/default/original game unchanged.',
            native_execution=False, screen_verification_deferred=True, full_engine_goal_complete=False)
        write_new(STAGE / 'requirements.json', req)
        backups = [backup(name) for name in ('Source/Host/MenuReplayPresentation.h', 'Source/Host/MenuReplayLayout.h',
            'Source/Host/HostRun.h', 'Tests/menu_replay_restored_scene.cpp', 'Tests/menu_replay_restoration.py',
            'tools/build_menu_suite_host.py', 'tools/attest_prepared_menu_host.py',
            'evidence/save_menu/20261013_original_screen/current_progress.json')]
        write_new(STAGE / 'source_before.json', dict(changed_file_backups=backups, full_project_copy=False))
        result = baseline()
        write_new(STAGE / 'startup.json', dict(**result, previous_final_storage=ref(PREVIOUS / 'storage_after.json'),
            cleanup_precheck='Previous owned superseded 59c root and six current objects already removed; no confirmed disposable pool above 10GiB.',
            working_source_may_differ_from_previous_prepared_runtime=True, native_execution=False))
        print(json.dumps(result))
    elif args.action == 'backup':
        print(json.dumps([backup(name) for name in args.paths]))
    elif args.action == 'measure':
        value = storage.measure_storage()
        value.update(schema='zerosis.replay_calendar_legend.storage.v1', label=args.label,
                     utc=datetime.now(timezone.utc).isoformat(), native_execution=False,
                     confirmed_disposable_bytes=0, threshold_bytes=10*1024**3,
                     scope_note='Whole project allocation counted once per real file identity; directories excluded. The receipt is written after the scan. Concurrent small source edits may occur; native execution remains forbidden.')
        target = STAGE / ('storage_' + args.label + '.json')
        write_new(target, value)
        print(json.dumps({key:value.get(key) for key in ('status','file_paths','unique_allocated_bytes','confirmed_disposable_bytes')}))
    else:
        before = json.loads(gzip.decompress((STAGE / 'protection_before.json.gz').read_bytes()))
        differences, links, ids = [], [], {}
        for row in before['protected_artifacts']:
            current = storage.metadata(storage.ordinary(row['path']))
            identity = tuple(current['file_identity'])
            if identity not in ids:
                ids[identity] = (storage.digest(row['path']), storage.allocated(row['path']))
            if any(current[k] != row[k] for k in ('bytes','file_identity','mtime_ns','file_attributes')) or ids[identity] != (row['sha256'], row['allocated_bytes']):
                differences.append(row['path'])
            if current['links'] != row['links']:
                links.append(dict(path=row['path'], before=row['links'], after=current['links']))
        result = dict(status='PASS' if not differences else 'FAIL', protected_paths=before['protected_paths'],
            content_identity_mtime_attributes_differences=differences, observed_alias_count_changes=links,
            native_execution=False)
        write_new(STAGE / ('protection_' + args.label + '.json'), result)
        print(json.dumps(dict(status=result['status'],protected_paths=before['protected_paths'],differences=len(differences),alias_changes=len(links))))
        if differences:
            raise ValueError('Protected data drift')


if __name__ == '__main__':
    main()
