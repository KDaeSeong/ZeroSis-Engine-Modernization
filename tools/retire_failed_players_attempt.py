"""Retire exactly one terminal failed owned Players component attempt."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import stat
import sys

sys.dont_write_bytecode = True
from verify_retail_save_header import artifact, require, within, key
from publish_retail_player_units import allocation, read, same

PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / 'evidence/retail_save_container/players'


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--failure-sha', required=True)
    parser.add_argument('--number', required=True, type=int)
    args = parser.parse_args()
    require(1 <= args.number <= 9, 'Unexpected attempt number')
    failure_path = STAGE / 'failed_attempt.json'
    failure_artifact = artifact(failure_path)
    require(failure_artifact['sha256'] == args.failure_sha, 'Failure changed before review')
    failure = read(failure_path)
    require(failure['status'] == 'FAILED_RETAIL_PLAYERS_COMPONENT' and
            failure['native_engine_executed'] is False and not failure['forbidden_access_attempts'],
            'Only an isolated failed component may be retired')
    require(not (STAGE / 'build_result.json').exists(), 'Successful component retirement is forbidden')
    root = Path(failure['build_root']).resolve(strict=True)
    require(within(root, PROJECT / 'Build/RetailSavePlayers') and root.parent ==
            (PROJECT / 'Build/RetailSavePlayers').resolve(), 'Unexpected owned build root')
    receipt_path = STAGE / ('failure_%02d_retirement.json' % args.number)
    require(not receipt_path.exists(), 'This reviewed retirement is one-use')
    started = read(STAGE / 'build_started.json')
    for row in started['protected']:
        same(row)
    changed_sources = []
    for row in failure['inputs']:
        current = artifact(row['path'])
        if current != row:
            require(key(row['path']) == key(PROJECT / 'Tests/retail_players.cpp'),
                    'A non-owned failed-attempt input changed')
            changed_sources.append({'before': row, 'after': current})
    names = {'read_build_environment.cmd', 'RetailSavePlayersTests.exe',
             'retail_players.obj', 'compile.rsp', 'dependencies.json'}
    build_files = []
    for path in root.rglob('*'):
        info = path.lstat()
        require(not getattr(info, 'st_file_attributes', 0) & 0x400, 'Reparse failed build path')
        if path.is_file():
            require(path.name in names, 'Unreviewed file in failed build')
            build_files.append(path)
    stage_files = [STAGE / name for name in ('build_started.json', 'failed_attempt.json',
        'source_conformance.json', 'compile_O2.log', 'compile_Od.log', 'test_O2.log', 'test_Od.log')
        if (STAGE / name).exists()]
    paths = build_files + stage_files
    rows = []
    for path in paths:
        for parent in (path, *path.parents):
            if parent.exists():
                require(not getattr(parent.lstat(), 'st_file_attributes', 0) & 0x400, 'Reparse retirement path')
        info = path.lstat()
        require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and
                (within(path, root) or path in stage_files), 'Unexpected retirement identity')
        rows.append({**artifact(path), 'file_identity': [info.st_dev, info.st_ino],
                     'mtime_ns': info.st_mtime_ns, 'allocated_bytes': allocation(path)})
    observations = {path.name: read(path) for path in stage_files if path.name.startswith('test_')}
    report = {'schema': 'zerosis.retail.players.failed_retirement.v1',
        'status': 'REVIEWED_TERMINAL_FAILED_COMPONENT_RETIREMENT',
        'utc': datetime.now(timezone.utc).isoformat(), 'failure': failure_artifact,
        'failure_reason': failure['error'], 'build_root': str(root),
        'test_observations': observations, 'changed_owned_test_sources': changed_sources,
        'protected_input_count': len(started['protected']), 'protected_unchanged': True,
        'retired': rows, 'retired_logical_bytes': sum(x['bytes'] for x in rows),
        'retired_unique_allocated_bytes': sum(x['allocated_bytes'] for x in rows),
        'host_gamecore_or_hwnd_executed': False, 'full_engine_goal_complete': False}
    receipt_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    for row in rows:
        path = Path(row['path']); info = path.lstat()
        require([info.st_dev, info.st_ino] == row['file_identity'] and
                info.st_size == row['bytes'] and info.st_mtime_ns == row['mtime_ns'] and
                info.st_nlink == 1 and artifact(path)['sha256'] == row['sha256'],
                'Failed output changed before deletion')
        path.unlink()
    for path in sorted((x for x in root.rglob('*') if x.is_dir()), key=lambda x: len(x.parts), reverse=True):
        path.rmdir()
    root.rmdir()
    require(not root.exists() and all(not Path(x['path']).exists() for x in rows), 'Retirement incomplete')
    for row in started['protected']:
        same(row)
    report['status'] = 'RETIRED_TERMINAL_FAILED_PLAYERS_COMPONENT'
    receipt_path.write_text(json.dumps(report, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'receipt': artifact(receipt_path),
        'retired_logical_bytes': report['retired_logical_bytes'],
        'retired_unique_allocated_bytes': report['retired_unique_allocated_bytes']}))


if __name__ == '__main__':
    main()
