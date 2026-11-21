"""Hash-lock and retire only the two unexecuted, failed pair preparations."""
from __future__ import annotations
import argparse
import collections
import json
import os
from pathlib import Path
import stat
import sys

PROJECT = Path(__file__).absolute().parents[4]
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT / 'tools'))
import menu_suite_storage as audit
from civ5_ui_assets import _unlink_font_target_without_attribute_changes

ROOT = Path(__file__).absolute().parent
PLAN = ROOT / 'failed_pair_cleanup_plan.json'
RESULT = ROOT / 'failed_pair_cleanup_result.json'
ADOPTION = ROOT / 'materialization_retry03_adoption_retry02'
CURRENT = '20261101T080450Z_424fb64608b2'
FAILED = (('materialization_retry01', '20261101T075405Z_fb66d603b588'),
          ('materialization_retry02', '20261101T080122Z_0083c4a7196b'))
storage = audit.storage


def require(value, message):
    if not value:
        raise RuntimeError(message)


def artifact(path):
    info = storage.ordinary(path)
    return dict(path=str(path), **storage.metadata(info), sha256=storage.digest(path),
                allocated_bytes=storage.allocated(path))


def verify(row, *, links=None):
    info = storage.metadata(storage.ordinary(row['path']))
    require(all(info[key] == row[key] for key in ('bytes', 'file_identity', 'mtime_ns', 'file_attributes')),
            'Cleanup file identity or metadata changed: ' + row['path'])
    require(info['links'] == (row['links'] if links is None else links) and
            storage.digest(row['path']) == row['sha256'], 'Cleanup file content/link count changed: ' + row['path'])


def create_plan():
    require(not PLAN.exists(), 'Inspect the existing cleanup plan instead of replacing it')
    adopted = storage.read(ADOPTION / 'result.json')
    require(adopted['run_id'] == CURRENT and adopted['native_attempts'] == 0 and adopted['guard_denials'] == [] and
            adopted['adopted_unexecuted_preparation'] is True, 'No accepted unexecuted current pair')
    request_path = PROJECT / 'evidence/interactive_game' / CURRENT / 'request.json'
    request = storage.read(request_path)
    require(storage.digest(request_path) == adopted['request']['sha256'], 'Accepted request changed')
    candidates, directories, failures, roots = [], [], [], []
    for attempt, identifier in FAILED:
        failure_path = ROOT / attempt / 'failure.json'
        failure = storage.read(failure_path)
        require(failure['status'] == 'FAILED_PREPARATION_ONLY' and failure['run_id'] == identifier and
                failure['native_attempts'] == 0 and failure['denied'] == [], 'Failed run has an execution or scope ambiguity')
        failures.append(dict(artifact(failure_path), retired_run_id=identifier, failure=failure))
        require(identifier not in json.dumps(request), 'Accepted pair references a failed run')
        for parent in (PROJECT / 'Build/InteractiveGameRuntime', PROJECT / 'evidence/interactive_game'):
            root = parent / identifier
            require(root.is_absolute() and root.resolve(strict=True).parent == parent.resolve(strict=True) and
                    root.name == identifier and identifier != CURRENT, 'Failed cleanup root escaped exact project scope')
            roots.append(str(root))
            require(not (root / 'attempt.json').exists() and not (root / 'driver_result.json').exists(),
                    'A failed preparation contains a native attempt')
            if (root / 'sessions').exists():
                require(not any((root / 'sessions').iterdir()), 'A failed preparation has generated sessions')
            for path in [root, *sorted(root.rglob('*'))]:
                info = path.lstat()
                require(not stat.S_ISLNK(info.st_mode) and not info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                        'Failed cleanup encountered a reparse point')
                require(path.resolve(strict=True).is_relative_to(root.resolve(strict=True)), 'Cleanup leaf escaped its exact root')
                if stat.S_ISREG(info.st_mode):
                    candidates.append(artifact(path))
                else:
                    require(stat.S_ISDIR(info.st_mode), 'Unexpected cleanup node type')
                    directories.append(str(path))
    protected = [artifact(request_path), artifact(ADOPTION / 'result.json'), artifact(ADOPTION / 'final_prepared_pair_audit.json')]
    for path in (PROJECT / 'Build/InteractiveGameRuntime' / CURRENT).rglob('*'):
        if path.is_file():
            protected.append(artifact(path))
    for row in request['materializations']:
        if row['materialization_method'] == 'hardlink':
            protected.append(artifact(Path(row['cache'])))
    for relative in ('tools/Start-Engine.ps1', 'Play/EarlyAccess/release.json'):
        protected.append(artifact(PROJECT / relative))
    grouped = collections.defaultdict(list)
    for row in candidates:
        grouped[tuple(row['file_identity'])].append(row)
    allocation = sum(rows[0]['allocated_bytes'] for rows in grouped.values() if rows[0]['links'] == len(rows))
    audit.write_new(PLAN, dict(schema='zerosis.menu_suite_pair.failed_preparation_cleanup_plan.v1',
        current_run_id=CURRENT, adopted_preparation=artifact(ADOPTION / 'result.json'), failed_preparation_evidence=failures,
        exact_owned_roots=roots, candidates=candidates, directories=directories, protected=protected,
        logical_bytes=sum(row['bytes'] for row in candidates), unique_file_identities=len(grouped),
        allocated_bytes_releasable=allocation, cache_payloads_are_not_candidates=True, native_execution=False,
        originals_saves_mods_defaults_are_not_candidates=True,
        allocation_basis='FileStandardInfo.AllocationSize counted once only when all identity links are exact candidates; directories excluded.'))
    print(json.dumps(dict(plan=str(PLAN),sha256=storage.digest(PLAN),files=len(candidates),
                          logical_bytes=sum(row['bytes'] for row in candidates),allocated_bytes_releasable=allocation)))


def execute(expected_sha):
    require(not RESULT.exists() and not (ROOT / 'failed_pair_cleanup_started.json').exists(), 'Cleanup is single-use')
    require(storage.digest(PLAN) == expected_sha, 'Cleanup plan pin changed')
    plan = storage.read(PLAN)
    expected_roots = {str(parent / identifier) for _,identifier in FAILED for parent in (
        PROJECT / 'Build/InteractiveGameRuntime', PROJECT / 'evidence/interactive_game')}
    require(set(plan['exact_owned_roots']) == expected_roots and plan['current_run_id'] == CURRENT, 'Cleanup plan roots differ')
    actual = {str(path) for root in expected_roots for path in Path(root).rglob('*') if path.is_file()}
    require(actual == {row['path'] for row in plan['candidates']}, 'Failed preparation tree has changed')
    for row in plan['candidates'] + plan['protected']:
        verify(row)
    counts = collections.Counter(tuple(row['file_identity']) for row in plan['candidates'])
    audit.write_new(ROOT / 'failed_pair_cleanup_started.json', dict(plan_sha256=expected_sha, current_run_id=CURRENT))
    removed = []
    for row in plan['candidates']:
        identity = tuple(row['file_identity'])
        already = sum(tuple(value['file_identity']) == identity for value in removed)
        verify(row, links=row['links']-already)
        path = Path(row['path'])
        require(any(path.resolve(strict=True).is_relative_to(Path(root).resolve(strict=True)) for root in expected_roots),
                'Exact candidate escaped before unlink')
        _unlink_font_target_without_attribute_changes(path)
        require(not os.path.lexists(path), 'Exact cleanup leaf remains')
        removed.append(row)
    for path in sorted((Path(value) for value in plan['directories']), key=lambda p: len(p.parts), reverse=True):
        require(str(path) in expected_roots or any(path.is_relative_to(Path(root)) for root in expected_roots),
                'Empty-directory cleanup escaped exact failed scope')
        path.rmdir()
    for row in plan['protected']:
        verify(row, links=row['links']-counts[tuple(row['file_identity'])])
    require(all(not os.path.lexists(root) for root in expected_roots), 'A retired failed root remains')
    audit.write_new(RESULT, dict(schema='zerosis.menu_suite_pair.failed_preparation_cleanup_result.v1',
        status='PASS_EXACT_UNEXECUTED_FAILED_PAIR_RETIREMENT', plan_sha256=expected_sha,
        current_run_id=CURRENT, files_deleted=len(removed), logical_bytes_removed=plan['logical_bytes'],
        allocated_bytes_released=plan['allocated_bytes_releasable'], exact_failed_roots_absent=sorted(expected_roots),
        path_size_identity_hash_ledger=str(PLAN), protected_artifacts_unchanged=len(plan['protected']),
        shared_cache_payloads_preserved=True, shared_readonly_attributes_unchanged=True,
        history_failures_started_logs_preserved=True, host_sdk_executed=False, native_execution=False,
        user_originals_saves_mods_defaults_deleted=False))
    print(json.dumps(dict(result=str(RESULT),sha256=storage.digest(RESULT),files_deleted=len(removed),
                          allocated_bytes_released=plan['allocated_bytes_releasable'])))


def main():
    require(not sys.flags.optimize, 'Run cleanup without optimization')
    parser = argparse.ArgumentParser(); parser.add_argument('--execute-sha256'); args = parser.parse_args()
    if args.execute_sha256:
        execute(args.execute_sha256)
    else:
        create_plan()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
