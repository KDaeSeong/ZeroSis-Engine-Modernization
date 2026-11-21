"""Seal this exact superseded TradeRoute pair; applying remains a separate operation."""
from __future__ import annotations
import gzip
import json
from pathlib import Path
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as retirement

OLD_RUNS = ('20261008T140841Z_97c557fe4a26', '20261008T161612Z_f12596e7c414')
OLD_HOST = '20261008T135705Z_418f41986ec2'
NEW_RUNS = ('20261008T225105Z_a09bb643b908', '20261008T233650Z_5cfa5136b39e')
NEW_HOST = '20261008T224629Z_ee41544939ef'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def project_files():
    # The retirement utility intentionally rejects ROOT as a deletion boundary.
    # Read each validated child instead; keep that deletion guard unchanged.
    for child in ROOT.iterdir():
        child = retirement.boundary(child)
        if child.is_dir():
            yield from retirement.inventory(child)
        else:
            yield child, retirement.regular(child)


def main():
    retirement.require(not (HERE / 'plan.json').exists(), 'Never overwrite a prepared retirement plan')
    retirement.require(retirement.ROOT == ROOT, 'Retirement utility root differs')
    retirement.no_active_host()
    latest_proofs = []
    for run in NEW_RUNS:
        evidence = ROOT / 'evidence/interactive_game' / run
        result_path = evidence / 'result.json'
        proof_path = evidence / 'trade_route_validation.json'
        result, proof = read(result_path), read(proof_path)
        retirement.require(result['status'].endswith('_PASS') and result['returncode'] == 0
                           and result['runtime_inputs_unchanged'] is True and not result['failures'],
                           'Replacement runtime has not passed')
        retirement.require(proof['status'] == 'PASS_INTERACTIVE_TRADE_ROUTE_NATIVE_SDK_SMOKE',
                           'Replacement independent TradeRoute proof has not passed')
        if run == NEW_RUNS[1]:
            lineage = proof['evidence']['resume_lineage']
            retirement.require(lineage['source_run_id'] == NEW_RUNS[0]
                               and lineage['startup_state_byte_equal'] is True
                               and lineage['post_restore_turn'] == 2,
                               'Replacement restore lineage differs')
        latest_proofs.append({'path': str(proof_path), 'sha256': retirement.digest(proof_path)})
    manual = list(dict.fromkeys(retirement.RUN.findall((ROOT / 'tools/Start-Engine.ps1').read_text(encoding='utf8'))))
    retirement.require(not set(OLD_RUNS) & set(manual), 'Retired runtime is a manual save dependency')
    targets = [ROOT / category / run for run in OLD_RUNS
               for category in ('Build/InteractiveGameRuntime', 'evidence/interactive_game')]
    targets += [ROOT / 'Build/UiWindowHost' / OLD_HOST, ROOT / 'evidence/ui_window_host' / OLD_HOST]
    targets = [retirement.legal_target(path) for path in targets]
    retirement.require(len(targets) == len(set(targets)) == 6, 'Exact six-folder scope differs')

    # All other project files are protected, including manual bundles, source,
    # current pair, providers, raw CPU traces and the current component baselines.
    protected, hashes = {}, {}
    # Checkpoint only hash work in this excluded planning folder. Apply still
    # independently rehashes every protected file before and after deletion.
    cache_path = HERE / 'planning-hashes.jsonl'
    if cache_path.exists():
        for line in cache_path.read_text(encoding='utf8').splitlines():
            try:
                row = json.loads(line)
                key = tuple(row['identity'])
                if len(key) == 4 and retirement.SHA.fullmatch(row['sha256']):
                    hashes[key] = row['sha256']
            except (ValueError, KeyError, TypeError):
                continue
    cache_stream = cache_path.open('a', encoding='utf8', buffering=1)
    started = time.monotonic()

    def ensure_hash(path, identity):
        if identity not in hashes:
            hashes[identity] = retirement.digest(path)
            cache_stream.write(json.dumps({'identity': identity, 'sha256': hashes[identity]}, separators=(',', ':')) + '\n')
        return hashes[identity]

    print(json.dumps({'phase': 'begin_protected', 'cached_identities': len(hashes)}), flush=True)
    for path, info in project_files():
        if path.is_relative_to(HERE) or any(path.is_relative_to(target) for target in targets):
            continue
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        protected[str(path)] = ensure_hash(path, identity)
        if len(protected) % 500 == 0:
            print(json.dumps({'phase': 'protected_progress', 'files': len(protected),
                              'unique_identities': len(hashes), 'elapsed_seconds': round(time.monotonic() - started, 1)}), flush=True)
    baseline = read(ROOT / 'evidence/storage/20261008T164816Z_2268d33ad2b9_cold/post_cleanup_validation.json')
    retirement.require(len(baseline['saves']) == 8, 'Manual save baseline differs')
    for row in baseline['saves']:
        retirement.require(protected.get(row['path']) == row['sha256'], 'User save differs or is not protected')
    print(json.dumps({'phase': 'protected', 'files': len(protected)}), flush=True)
    protected_path = HERE / 'protected.json.gz'
    with gzip.open(protected_path, 'wt', encoding='utf8') as stream:
        json.dump(protected, stream, separators=(',', ':'))

    ledger_path = HERE / 'retired-files.jsonl.gz'
    directories, identities, file_count, logical_bytes = [], {}, 0, 0
    with gzip.open(ledger_path, 'wt', encoding='utf8') as stream:
        for target in targets:
            count = size = 0
            for path, info in retirement.inventory(target):
                identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                ensure_hash(path, identity)
                tracked = identities.setdefault((info.st_dev, info.st_ino),
                    {'links': info.st_nlink, 'count': 0, 'stored': retirement.stored(path)})
                tracked['count'] += 1
                row = {'path': str(path.relative_to(ROOT)), 'sha256': hashes[identity], 'bytes': info.st_size,
                       'mtime_ns': info.st_mtime_ns, 'device': info.st_dev, 'file_id': info.st_ino}
                stream.write(json.dumps(row, separators=(',', ':')) + '\n')
                count += 1
                size += info.st_size
            directories.append({'path': str(target.relative_to(ROOT)), 'files': count, 'logical_bytes': size})
            file_count += count
            logical_bytes += size
            print(json.dumps({'phase': 'target', **directories[-1]}), flush=True)
    cache_stream.close()

    diagnostics = []
    for run in OLD_RUNS:
        folder = ROOT / 'evidence/interactive_game' / run
        for name in ('result.json', 'trade_route_dispatch_revalidation.json'):
            path = folder / name
            if path.is_file():
                data = read(path)
                diagnostics.append({'path': str(path), 'sha256': retirement.digest(path),
                    'status': data.get('status'), 'returncode': data.get('returncode'),
                    'failures': data.get('failures'), 'retained_raw_artifacts': False,
                    'dispatch_revalidation': data if name == 'trade_route_dispatch_revalidation.json' else None})
    host_report = ROOT / 'evidence/ui_window_host' / OLD_HOST / 'build_result.json'
    diagnostics.append({'path': str(host_report), 'sha256': retirement.digest(host_report),
                        'status': read(host_report)['status'], 'retained_raw_artifacts': False})
    diagnostics_path = HERE / 'retired-statuses.json.gz'
    with gzip.open(diagnostics_path, 'wt', encoding='utf8') as stream:
        json.dump(diagnostics, stream, ensure_ascii=False, separators=(',', ':'))
    plan = {'status': 'PREVIEW_ONLY', 'scope': 'EXACT_SIX_SUPERSEDED_TRADE_ROUTE_RUNTIME_AND_HOST_FOLDERS',
            'root': str(ROOT), 'manual_runtimes': manual, 'latest_runtime_pair': list(NEW_RUNS),
            'latest_host_build': NEW_HOST, 'latest_independent_proofs': latest_proofs,
            'protected': {'path': str(protected_path), 'sha256': retirement.digest(protected_path)},
            'ledger': {'path': str(ledger_path), 'sha256': retirement.digest(ledger_path)},
            'retired_statuses': {'path': str(diagnostics_path), 'sha256': retirement.digest(diagnostics_path)},
            'directories': directories, 'files': file_count, 'logical_bytes': logical_bytes,
            'current_dependency_files': len(protected), 'protected_user_saves': 8,
            'estimated_reclaimable_file_storage': sum(row['stored'] for row in identities.values()
                                                     if row['links'] == row['count']),
            'historical_retention_policy': 'Retire replaced raw data and reports together; retain compact status and file-SHA ledgers.',
            'source_tools_tests_game_mods_user_saves_deleted': False,
            'script_sha256': retirement.digest(Path(retirement.__file__)),
            'planner_sha256': retirement.digest(Path(__file__))}
    destination = HERE / 'plan.json'
    destination.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': plan['status'], 'plan': str(destination), 'plan_sha256': retirement.digest(destination),
                      'files': file_count, 'logical_bytes': logical_bytes,
                      'estimated_reclaimable_bytes': plan['estimated_reclaimable_file_storage'],
                      'protected_files': len(protected)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
