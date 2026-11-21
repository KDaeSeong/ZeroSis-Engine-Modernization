"""Generate a bounded preview seal for the failed Fresh/Host tenet attempt.

This script only writes protected-final.json.gz and plan.json. It never deletes,
compresses, or rewrites source, runtime, inventory, or preserved evidence.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
RUN = re.compile(r'[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}')
FAILED_RUN = '20261009T075113Z_315e609b50e6'
HOST_ID = '20261009T074845Z_3b9099f7c315'
BASE_MAP = ROOT / 'evidence/storage_cleanup/20261009_failed_policy_tenet_064236/protected-final.json.gz'
SCROLLBAR_COMPONENT = 'evidence/social_policy_scene/20261009_auto_scroll_visibility'
SCROLLBAR_BINARY_EVIDENCE = 'evidence/social_policy_scene/20261009_original_scrollbar_default'

sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as p


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf8'))


def add_inventory(names: set[str], directory: Path) -> None:
    directory = p.boundary(directory)
    for path, _info in p.inventory(directory):
        names.add(str(path))


def verify_request_host(result: dict, run_id: str, host_sha: str) -> None:
    evidence = p.boundary(ROOT / 'evidence/interactive_game' / run_id)
    request_path = p.boundary(evidence / 'request.json')
    request_ref = result.get('request')
    if not isinstance(request_ref, dict) or Path(request_ref.get('path', '')).resolve(strict=True) != request_path or \
            p.digest(request_path) != request_ref.get('sha256'):
        raise RuntimeError('Runner result does not pin the exact request for run ' + run_id)
    request = load_json(request_path)
    runtime = p.boundary(ROOT / 'Build/InteractiveGameRuntime' / run_id)
    if request.get('run_id') != run_id or request.get('social_policy_tenets') is not True or \
            Path(request.get('cwd', '')).resolve(strict=True) != runtime:
        raise RuntimeError('Request identity, tenet profile, or runtime differs for run ' + run_id)
    host_rows = [row for row in request.get('runtime_inputs', []) if isinstance(row, dict) and
                 Path(row.get('path', '')).name == 'ZeroSisHost_x64.exe']
    if len(host_rows) != 1 or host_rows[0].get('sha256') != host_sha:
        raise RuntimeError('Run does not use the exact sealed Host in its immutable runtime: ' + run_id)
    host_path = p.boundary(Path(host_rows[0]['path']))
    if host_path.parent != runtime or p.digest(host_path) != host_rows[0]['sha256']:
        raise RuntimeError('Actual runtime Host bytes do not match the sealed input row: ' + run_id)


def verify_passing_pair(fresh_id: str, restore_id: str) -> tuple[Path, Path, dict, dict]:
    if not RUN.fullmatch(fresh_id) or not RUN.fullmatch(restore_id) or fresh_id == restore_id:
        raise RuntimeError('Fresh and restore run IDs must be distinct immutable run identities')
    if FAILED_RUN in (fresh_id, restore_id):
        raise RuntimeError('The failed stage17 run cannot be reused as replacement evidence')

    host_build_path = p.boundary(ROOT / 'evidence/ui_window_host' / HOST_ID / 'build_result.json')
    host_build = load_json(host_build_path)
    if host_build.get('build_id') != HOST_ID or host_build.get('status') != 'UI_WINDOW_HOST_CANDIDATE_BUILT' or \
            host_build.get('source_inputs_unchanged') is not True:
        raise RuntimeError('Exact replacement Host build is not a sealed successful candidate')
    host_executable = p.boundary(Path(host_build['executable']['path']))
    host_sha = host_build['executable']['sha256']
    if p.digest(host_executable) != host_sha:
        raise RuntimeError('Replacement Host executable differs from its sealed build result')

    fresh_result_path = p.boundary(ROOT / 'evidence/interactive_game' / fresh_id / 'result.json')
    fresh_validation_path = p.boundary(ROOT / 'evidence/interactive_game' / fresh_id / 'policy_tenets_validation.json')
    fresh_result, fresh_validation = load_json(fresh_result_path), load_json(fresh_validation_path)
    fresh_pass = (
        fresh_result.get('run_id') == fresh_id
        and fresh_result.get('status') == 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS'
        and fresh_result.get('returncode') == 0 and fresh_result.get('timed_out') is False
        and fresh_result.get('runtime_inputs_unchanged') is True
        and fresh_result.get('social_policy_requested') is True
        and fresh_result.get('social_policy_tenets_requested') is True
        and fresh_result.get('social_policy_dispatch_verified') is True
        and fresh_result.get('social_policy_tenets_sequence_verified') is True
        and not fresh_result.get('failures') and not fresh_result.get('host_failures')
        and fresh_validation.get('run_id') == fresh_id
        and fresh_validation.get('status') == 'PASS_INTERACTIVE_POLICY_TENETS_NATIVE_SDK_SMOKE'
        and fresh_validation.get('result', {}).get('path') == str(fresh_result_path)
        and fresh_validation.get('result', {}).get('sha256') == p.digest(fresh_result_path)
    )
    if not fresh_pass:
        raise RuntimeError('Fresh replacement lacks runner PASS and independent native tenet verifier PASS')
    verify_request_host(fresh_result, fresh_id, host_sha)

    restore_result_path = p.boundary(ROOT / 'evidence/interactive_game' / restore_id / 'result.json')
    restore_validation_path = p.boundary(ROOT / 'evidence/interactive_game' / restore_id / 'policy_tenets_validation.json')
    restore_result, restore_validation = load_json(restore_result_path), load_json(restore_validation_path)
    restore_pass = (
        restore_result.get('run_id') == restore_id
        and restore_result.get('status') == 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS'
        and restore_result.get('returncode') == 0 and restore_result.get('timed_out') is False
        and restore_result.get('runtime_inputs_unchanged') is True
        and restore_result.get('social_policy_requested') is True
        and restore_result.get('social_policy_tenets_requested') is True
        and restore_result.get('social_policy_dispatch_verified') is True
        and restore_result.get('social_policy_tenets_sequence_verified') is True
        and restore_result.get('resume_from_run') == fresh_id
        and not restore_result.get('failures') and not restore_result.get('host_failures')
        and restore_validation.get('run_id') == restore_id
        and restore_validation.get('status') == 'PASS_INTERACTIVE_POLICY_TENETS_NATIVE_SDK_SMOKE'
        and restore_validation.get('result', {}).get('path') == str(restore_result_path)
        and restore_validation.get('result', {}).get('sha256') == p.digest(restore_result_path)
        and restore_validation.get('restore', {}).get('source_run_id') == fresh_id
    )
    if not restore_pass:
        raise RuntimeError('Restore replacement is not a distinct independent PASS sourced from the fresh run')
    verify_request_host(restore_result, restore_id, host_sha)
    return fresh_result_path, restore_result_path, fresh_validation, restore_validation


def seal_preview(fresh_id: str, restore_id: str) -> None:
    p.no_active_host()
    plan_path = FOLDER / 'plan.json'
    protected_path = FOLDER / 'protected-final.json.gz'
    if plan_path.exists() or protected_path.exists():
        raise RuntimeError('Seal outputs already exist; refusing to overwrite or reseed them')

    inventory_path = p.boundary(FOLDER / 'inventory.json')
    inventory = load_json(inventory_path)
    if inventory.get('status') != 'INVENTORY_ONLY_NOT_SEALED':
        raise RuntimeError('Expected the exact unsealed stage17 failure inventory')
    ledger = p.boundary(Path(inventory['ledger']['path']))
    if p.digest(ledger) != inventory['ledger']['sha256']:
        raise RuntimeError('Retired-files ledger changed after inventory')

    targets = [p.legal_target(ROOT / row['path']) for row in inventory['targets']]
    expected_targets = {
        p.boundary(ROOT / 'Build/InteractiveGameRuntime' / FAILED_RUN),
        p.boundary(ROOT / 'evidence/interactive_game' / FAILED_RUN),
    }
    if len(targets) != 2 or set(targets) != expected_targets:
        raise RuntimeError('Inventory is not limited to the failed Fresh stage17 Build/evidence pair')

    base = p.boundary(BASE_MAP)
    with gzip.open(base, 'rt', encoding='utf8') as stream:
        previous = json.load(stream)
    if not isinstance(previous, dict) or not previous:
        raise RuntimeError('Previous protected map is invalid or empty')
    retired_previous = [name for name in previous if any(Path(name).is_relative_to(t) for t in targets)]
    names: set[str] = set()
    already_removed_generated_cache = []
    # Rehash every still-live prior protected path at current contents. The previous
    # hashes are historical evidence, not a reason to preserve stale source hashes.
    for name in previous:
        path = Path(name)
        if any(path.is_relative_to(target) for target in targets):
            continue
        if not path.exists() and path == ROOT / 'tools/__pycache__/run_interactive_game.cpython-314.pyc' and \
                previous[name] == '72b5b3206f569e5619af3c28986238bd598667e2014be10a25608d497c5876cc':
            p.regular(p.boundary(ROOT / 'tools/run_interactive_game.py'))
            already_removed_generated_cache.append({'path': name, 'previous_sha256': previous[name],
                'reason': 'Generated Python bytecode cache was removed during current source checks; source is retained.'})
            continue
        path = p.boundary(path)
        p.regular(path)
        names.add(str(path))
    names.add(str(base))

    fresh_result_path, restore_result_path, fresh_validation, restore_validation = verify_passing_pair(
        fresh_id, restore_id)
    fresh_dirs = [
        ROOT / 'Build/InteractiveGameRuntime' / fresh_id,
        ROOT / 'evidence/interactive_game' / fresh_id,
        ROOT / 'Build/InteractiveGameRuntime' / restore_id,
        ROOT / 'evidence/interactive_game' / restore_id,
    ]
    host_dirs = [ROOT / 'Build/UiWindowHost' / HOST_ID, ROOT / 'evidence/ui_window_host' / HOST_ID]
    protected_dirs = [
        ROOT / 'Source', ROOT / 'Tests', ROOT / 'tools',
        *host_dirs, *fresh_dirs,
        ROOT / SCROLLBAR_COMPONENT, ROOT / SCROLLBAR_BINARY_EVIDENCE,
    ]
    for directory in protected_dirs:
        add_inventory(names, directory)

    # Preserve this failed attempt's compact source/diagnostic archive and new
    # inventory artifacts, including prepare.py and this reviewed generator.
    for path, _info in p.inventory(p.boundary(FOLDER)):
        if path in (plan_path, protected_path):
            raise RuntimeError('Seal output unexpectedly exists inside its own protected inventory')
        names.add(str(path))

    for row in inventory.get('preserved_compressed_evidence', []):
        path = p.boundary(Path(row['path']))
        if p.digest(path) != row['sha256']:
            raise RuntimeError('Preserved evidence gzip differs from inventory: ' + str(path))
        with gzip.open(path, 'rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != row['uncompressed_sha256']:
                raise RuntimeError('Preserved evidence source hash differs: ' + str(path))
        names.add(str(path))

    protected_hashes: dict[str, str] = {}
    identity_hashes: dict[tuple[int, int, int, int], str] = {}
    for name in sorted(names):
        path = p.boundary(Path(name))
        if any(path.is_relative_to(target) for target in targets):
            raise RuntimeError('Retired failure target remains in the protected set: ' + str(path))
        info = p.regular(path)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in identity_hashes:
            identity_hashes[identity] = p.digest(path)
        protected_hashes[str(path)] = identity_hashes[identity]

    with gzip.open(protected_path, 'xt', encoding='utf8') as stream:
        json.dump(protected_hashes, stream, separators=(',', ':'))
    plan = {
        'root': str(ROOT), 'status': 'PREVIEW_ONLY',
        'scope': 'EXACT_FAILED_TENET_STAGE17_FRESH_RUN',
        'script_sha256': p.digest(ROOT / 'tools/prune_superseded_runtime_artifacts.py'),
        'seal_generator_sha256': p.digest(Path(__file__)),
        'ledger': inventory['ledger'], 'directories': inventory['targets'],
        'files': inventory['file_count'], 'logical_bytes': inventory['logical_bytes'],
        'estimated_reclaimable_file_storage': inventory['estimated_reclaimable_file_storage_bytes'],
        'preserved_compressed_evidence': inventory['preserved_compressed_evidence'],
        'protected': {'path': str(protected_path), 'sha256': p.digest(protected_path)},
        'protected_files': len(protected_hashes),
        'previous_protected': {'path': str(base), 'sha256': p.digest(base)},
        'retired_previous_protected_paths': retired_previous,
        'already_removed_generated_cache': already_removed_generated_cache,
        'replacement_host': HOST_ID, 'replacement_fresh_run': fresh_id,
        'replacement_restore_run': restore_id,
        'fresh_result': {'path': str(fresh_result_path), 'sha256': p.digest(fresh_result_path),
                         'status': 'PASS', 'independent_verifier_sha256': p.digest(
                             ROOT / 'evidence/interactive_game' / fresh_id / 'policy_tenets_validation.json'),
                         'independent_verifier_status': fresh_validation.get('status')},
        'restore_result': {'path': str(restore_result_path), 'sha256': p.digest(restore_result_path),
                           'status': 'PASS', 'independent_verifier_sha256': p.digest(
                               ROOT / 'evidence/interactive_game' / restore_id / 'policy_tenets_validation.json'),
                           'independent_verifier_status': restore_validation.get('status'),
                           'source_run_id': restore_validation.get('restore', {}).get('source_run_id')},
        'replacement_runs_passed': True,
        'user_saves_or_manual_runtime_deleted': False,
        'seal_status': 'PREVIEW_ONLY_NO_APPLY',
    }
    with plan_path.open('x', encoding='utf8') as stream:
        json.dump(plan, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'status': plan['status'], 'fresh_run': fresh_id, 'restore_run': restore_id,
                      'replacement_runs_passed': True, 'protected_files': len(protected_hashes),
                      'retired_previous_paths': len(retired_previous)}, ensure_ascii=False, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fresh-run', required=True)
    parser.add_argument('--restore-run', required=True)
    args = parser.parse_args()
    seal_preview(args.fresh_run, args.restore_run)


if __name__ == '__main__':
    main()
