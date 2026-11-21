"""Plan and retire explicitly selected, superseded interactive smoke runs.

Reuses the existing boundary/hash/identity-safe deletion implementation. It
never uses the old tool's dated automatic selection or its old cleanup plans.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import uuid

import prune_superseded_runtime_artifacts as base

ROOT = base.ROOT
KEEP_RUNS = ('20261010T061414Z_954a8fa83ad8', '20261010T064159Z_2bc04e2b7a20',
             '20261010T065253Z_25bd25e6bca5', '20261010T083559Z_cf284b981096',
             '20261010T084745Z_5475b643b0fd')
# Retain the component-test input baseline; current Host inputs are also
# protected through the latest fresh/restore request and result closures.
KEEP_HOST = '20261010T072241Z_8a97a1f4381e'
AUTHORIZATION = '불필요한 작업물 지워.'


def plan(run_ids):
    base.no_active_host()
    base.require(run_ids and len(run_ids) == len(set(run_ids)), 'Missing or duplicate selected runs')
    base.require(all(base.RUN.fullmatch(run) for run in run_ids), 'Invalid selected run ID')
    manual = list(dict.fromkeys(base.RUN.findall((ROOT / 'tools/Start-Engine.ps1').read_text(encoding='utf8'))))
    keep = set(manual) | set(KEEP_RUNS)
    base.require(not keep.intersection(run_ids), 'Selected run is required for play, saves or current validation')
    targets = [base.legal_target(ROOT / parent / run) for run in run_ids
               for parent in ('Build/InteractiveGameRuntime', 'evidence/interactive_game')]
    for run in run_ids:
        request_path = ROOT / 'evidence/interactive_game' / run / 'request.json'
        request = json.loads(request_path.read_text(encoding='utf-8-sig'))
        base.require(request.get('smoke') is True, 'Selected run is not a disposable smoke test')
    # A kept request is operational provenance. Historical narrative reports do
    # not retain superseded raw scenes forever; they are recorded as retired.
    for path in (ROOT / 'evidence/interactive_game').glob('*/request.json'):
        if path.parent.name not in run_ids:
            body = path.read_text(encoding='utf-8-sig')
            base.require(not any(run in body for run in run_ids), 'A retained request still refers to a selected run: ' + str(path))
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + uuid.uuid4().hex[:12]
    output = ROOT / 'evidence/storage_cleanup' / stamp
    output.mkdir(parents=True)
    seeds = [ROOT / 'evidence/ui_window_host' / KEEP_HOST / 'build_result.json']
    for run in sorted(keep):
        request = ROOT / 'evidence/interactive_game' / run / 'request.json'
        base.require(request.is_file(), 'Retained request missing: ' + str(request))
        seeds.append(request)
        result = request.with_name('result.json')
        if result.is_file():
            seeds.append(result)
    protected, documents = base.closure(seeds)
    protected[str(ROOT / 'tools/Start-Engine.ps1')] = None
    # Protect release manifests and all user saves without following historical
    # prose references as if they were active execution dependencies.
    for path in (ROOT / 'Play').rglob('*'):
        if path.is_file():
            protected[str(path)] = None
    saves = []
    for run in manual:
        for path in (ROOT / 'Build/InteractiveGameRuntime' / run).rglob('*.zssave'):
            protected[str(path)] = None
            saves.append(str(path.relative_to(ROOT)))
    for directory in targets:
        base.require(not any(Path(name).is_relative_to(directory) for name in protected),
                     'Selected run intersects retained execution dependencies: ' + str(directory))
    hashes = {}

    def hash_once(path, info):
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in hashes:
            hashes[identity] = base.digest(path)
        return hashes[identity]

    preserved_metadata = {}
    for name in protected:
        path = Path(name)
        info = base.regular(path)
        protected[name] = hash_once(path, info)
        preserved_metadata[name] = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
                                    getattr(info, 'st_file_attributes', 0)]
    protected_path = output / 'protected.json.gz'
    metadata_path = output / 'protected-metadata.json.gz'
    for path, content in ((protected_path, protected), (metadata_path, preserved_metadata)):
        with gzip.open(path, 'wt', encoding='utf8') as stream:
            json.dump(content, stream, separators=(',', ':'))
    ledger = output / 'retired-files.jsonl.gz'
    identities = {}
    directories = []
    with gzip.open(ledger, 'wt', encoding='utf8') as stream:
        for directory in targets:
            count = logical = 0
            for path, info in base.inventory(directory):
                item = identities.setdefault((info.st_dev, info.st_ino),
                    {'links': info.st_nlink, 'count': 0, 'stored': base.stored(path)})
                item['count'] += 1
                row = {'path': str(path.relative_to(ROOT)), 'sha256': hash_once(path, info),
                       'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns,
                       'device': info.st_dev, 'file_id': info.st_ino}
                stream.write(json.dumps(row, separators=(',', ':')) + '\n')
                count += 1
                logical += info.st_size
            directories.append({'path': str(directory.relative_to(ROOT)), 'files': count, 'logical_bytes': logical})
    retired = []
    for run in run_ids:
        directory = ROOT / 'evidence/interactive_game' / run
        terminal = directory / 'result.json'
        record = json.loads(terminal.read_text(encoding='utf-8-sig')) if terminal.is_file() else {}
        retired.append({'run_id': run, 'historical_status': record.get('status', 'NO_TERMINAL_RESULT'),
                        'result_sha256': base.digest(terminal) if terminal.is_file() else None,
                        'failures': record.get('failures', []), 'retained_raw_artifacts': False})
    report = {'schema': 1, 'status': 'PREVIEW_ONLY', 'root': str(ROOT),
              'scope': 'SELECTED_SUPERSEDED_INTERACTIVE_SMOKE_RUNS_ONLY',
              'user_instruction': AUTHORIZATION, 'selected_runs': run_ids,
              'manual_runtimes': manual, 'user_save_paths': saves,
              'retained_current_runs': list(KEEP_RUNS), 'retained_candidate_host': KEEP_HOST,
              'protected_files': len(protected), 'protected_json_documents': len(documents),
              'protected': {'path': str(protected_path), 'sha256': base.digest(protected_path)},
              'protected_metadata': {'path': str(metadata_path), 'sha256': base.digest(metadata_path)},
              'ledger': {'path': str(ledger), 'sha256': base.digest(ledger)},
              'directories': directories, 'retired_runs': retired,
              'files': sum(row['files'] for row in directories),
              'logical_bytes': sum(row['logical_bytes'] for row in directories),
              'estimated_reclaimable_file_storage': sum(row['stored'] for row in identities.values() if row['links'] == row['count']),
              'externally_shared_file_id_count': sum(row['links'] > row['count'] for row in identities.values()),
              'source_tools_tests_game_mods_user_saves_deleted': False,
              'old_plan_reused': False, 'script_sha256': base.digest(Path(base.__file__)),
              'selected_script_sha256': base.digest(Path(__file__))}
    destination = output / 'plan.json'
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'plan': str(destination), 'sha256': base.digest(destination),
                      'files': report['files'], 'directories': len(targets), 'user_saves': len(saves),
                      'logical_bytes': report['logical_bytes'],
                      'estimated_reclaimable_file_storage': report['estimated_reclaimable_file_storage']}, ensure_ascii=False), flush=True)


def apply(path, expected):
    path = base.boundary(path)
    base.require(expected and base.digest(path) == expected, 'Reviewed plan hash differs')
    report = json.loads(path.read_text(encoding='utf8'))
    base.require(report['scope'] == 'SELECTED_SUPERSEDED_INTERACTIVE_SMOKE_RUNS_ONLY' and
                 report['selected_script_sha256'] == base.digest(Path(__file__)), 'Selected scope/script differs')
    exact = {str(Path(parent) / run) for run in report['selected_runs']
             for parent in ('Build/InteractiveGameRuntime', 'evidence/interactive_game')}
    base.require({row['path'] for row in report['directories']} == exact, 'Unselected deletion root')
    metadata = base.boundary(Path(report['protected_metadata']['path']))
    base.require(metadata.parent == path.parent and base.digest(metadata) == report['protected_metadata']['sha256'], 'Protected metadata changed')
    with gzip.open(metadata, 'rt', encoding='utf8') as stream:
        preserved = json.load(stream)
    for name, expected_metadata in preserved.items():
        info = base.regular(Path(name))
        actual = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, getattr(info, 'st_file_attributes', 0)]
        base.require(actual == expected_metadata, 'Protected identity/attributes changed before cleanup: ' + name)
    base.apply(path)
    for name, expected_metadata in preserved.items():
        info = base.regular(Path(name))
        actual = [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, getattr(info, 'st_file_attributes', 0)]
        base.require(actual == expected_metadata, 'Protected identity/attributes changed after cleanup: ' + name)
    (path.parent / 'protected-identity-check.json').write_text(json.dumps({
        'status': 'PASS_PROTECTED_IDENTITIES_AND_ATTRIBUTES_UNCHANGED', 'files': len(preserved),
        'user_saves': len(report['user_save_paths']), 'plan_sha256': base.digest(path)}, indent=2) + '\n', encoding='utf8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-id', action='append')
    parser.add_argument('--apply', type=Path)
    parser.add_argument('--plan-sha256')
    args = parser.parse_args()
    if args.apply:
        base.require(not args.run_id, 'Apply cannot add new selected runs')
        apply(args.apply, args.plan_sha256)
    else:
        base.require(not args.plan_sha256, 'Plan hash applies only to apply')
        plan(args.run_id)
