"""Prepare a preview seal for failed Fresh12; never applies cleanup."""
import gzip
import hashlib
import json
from pathlib import Path
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as p


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf8'))


def seal_preview() -> None:
    p.no_active_host()
    if (FOLDER / 'plan.json').exists() or (FOLDER / 'protected-final.json.gz').exists():
        raise RuntimeError('Seal outputs already exist; refusing to overwrite them')
    inventory = load_json(FOLDER / 'inventory.json')
    if inventory.get('status') != 'INVENTORY_ONLY_NOT_SEALED':
        raise RuntimeError('Expected the exact unsealed inventory')
    ledger = Path(inventory['ledger']['path'])
    if p.digest(ledger) != inventory['ledger']['sha256']:
        raise RuntimeError('Retired-files ledger changed after inventory')

    targets = [p.legal_target(ROOT / row['path']) for row in inventory['targets']]
    expected_targets = {
        ROOT / 'Build/InteractiveGameRuntime/20261009T064236Z_270107c2b878',
        ROOT / 'evidence/interactive_game/20261009T064236Z_270107c2b878',
    }
    if len(targets) != 2 or set(targets) != expected_targets:
        raise RuntimeError('Inventory targets differ from the two authorized failed Fresh12 directories')
    base = p.boundary(ROOT / 'evidence/storage_cleanup/20261009_failed_policy_driver_060253/protected-final.json.gz')
    with gzip.open(base, 'rt', encoding='utf8') as stream:
        previous = json.load(stream)
    retired_protected = [name for name in previous if any(Path(name).is_relative_to(t) for t in targets)]
    names = {name for name in previous if name not in retired_protected}

    host_id = '20261009T063449Z_4cc92cfed9b4'
    run_id = '20261009T065612Z_717e525d9e22'
    restore_id = '20261009T070344Z_3ac99a0df5c9'
    groups = [
        'Source', 'Tests', 'tools',
        f'Build/UiWindowHost/{host_id}', f'evidence/ui_window_host/{host_id}',
        f'Build/InteractiveGameRuntime/{run_id}', f'evidence/interactive_game/{run_id}',
        f'Build/InteractiveGameRuntime/{restore_id}', f'evidence/interactive_game/{restore_id}',
        'evidence/social_policy_scene/20261009_policy_refresh_batch',
        'evidence/social_policy_scene/20261009_policy_input_layout',
        'evidence/social_policy_scene/20261009_culture_exhausted',
        'evidence/social_policy_scene/20261009_policy_branch_eligibility',
        'evidence/social_policy_scene/20261009_policy_tenet_alpha',
        'evidence/storage_cleanup/20261009_failed_policy_driver_060253',
    ]
    for group in groups:
        directory = p.boundary(ROOT / group)
        for path, _info in p.inventory(directory):
            names.add(str(path))

    # Require both the runner result and its independent SocialPolicy verifier report.
    result_path = p.boundary(ROOT / 'evidence/interactive_game' / run_id / 'result.json')
    verifier_path = p.boundary(ROOT / 'evidence/interactive_game' / run_id / 'social_policy_validation.json')
    result = load_json(result_path)
    verifier = load_json(verifier_path)
    if result.get('run_id') != run_id or verifier.get('run_id') != run_id:
        raise RuntimeError('Fresh13 runner and independent verifier must identify the requested run')
    native_pass = (
        result.get('status') == 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS'
        and result.get('returncode') == 0 and result.get('timed_out') is False
    )
    verifier_pass = verifier.get('status') == 'PASS_INTERACTIVE_SOCIAL_POLICY_NATIVE_SDK_SMOKE'
    replacement_passed = native_pass and verifier_pass
    restore_result_path = p.boundary(ROOT / 'evidence/interactive_game' / restore_id / 'result.json')
    restore_verifier_path = p.boundary(ROOT / 'evidence/interactive_game' / restore_id / 'social_policy_validation.json')
    restore_result = load_json(restore_result_path)
    restore_verifier = load_json(restore_verifier_path)
    restore_pass = (
        restore_result.get('run_id') == restore_id
        and restore_result.get('status') == 'CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS'
        and restore_result.get('returncode') == 0 and restore_result.get('timed_out') is False
        and restore_verifier.get('run_id') == restore_id
        and restore_verifier.get('status') == 'PASS_INTERACTIVE_SOCIAL_POLICY_NATIVE_SDK_SMOKE'
        and restore_verifier.get('restore', {}).get('source_run_id') == run_id
    )
    if not replacement_passed or not restore_pass:
        raise RuntimeError('Both the fresh and distinct-process restore policy runs must independently pass')

    for row in inventory['preserved_compressed_evidence']:
        path = p.boundary(Path(row['path']))
        if p.digest(path) != row['sha256']:
            raise RuntimeError('Preserved gzip hash differs from inventory: ' + str(path))
        with gzip.open(path, 'rb') as stream:
            if hashlib.file_digest(stream, 'sha256').hexdigest() != row['uncompressed_sha256']:
                raise RuntimeError('Preserved source hash differs from inventory: ' + str(path))
        names.add(str(path))

    protected_hashes = {}
    by_identity = {}
    for name in sorted(names):
        path = p.boundary(Path(name))
        if any(path.is_relative_to(target) for target in targets):
            raise RuntimeError('A retired path remains in the protected set: ' + str(path))
        info = p.regular(path)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in by_identity:
            by_identity[identity] = p.digest(path)
        protected_hashes[str(path)] = by_identity[identity]

    protected_path = FOLDER / 'protected-final.json.gz'
    with gzip.open(protected_path, 'wt', encoding='utf8') as stream:
        json.dump(protected_hashes, stream)
    plan = {
        'root': str(ROOT), 'status': 'PREVIEW_ONLY',
        'scope': 'EXACT_SUPERSEDED_FAILED_POLICY_FRESH12',
        'script_sha256': p.digest(ROOT / 'tools/prune_superseded_runtime_artifacts.py'),
        'ledger': inventory['ledger'], 'directories': inventory['targets'],
        'files': inventory['file_count'], 'logical_bytes': inventory['logical_bytes'],
        'estimated_reclaimable_file_storage': inventory['estimated_reclaimable_file_storage_bytes'],
        'preserved_compressed_inputs_and_diagnostics': inventory['preserved_compressed_evidence'],
        'protected': {'path': str(protected_path), 'sha256': p.digest(protected_path)},
        'protected_files': len(protected_hashes),
        'previous_protected': {'path': str(base), 'sha256': p.digest(base)},
        'explicitly_retired_previous_protected_paths': retired_protected,
        'replacement_host': host_id, 'replacement_run': run_id,
        'replacement_run_result': {'path': str(result_path), 'sha256': p.digest(result_path),
                                   'status': result.get('status'), 'returncode': result.get('returncode'),
                                   'timed_out': result.get('timed_out')},
        'independent_verifier': {'path': str(verifier_path), 'sha256': p.digest(verifier_path),
                                 'tool': str(ROOT / 'tools/verify_interactive_social_policy.py'),
                                 'tool_sha256': p.digest(ROOT / 'tools/verify_interactive_social_policy.py'),
                                 'status': verifier.get('status')},
        'replacement_run_passed': replacement_passed,
        'replacement_restore': restore_id, 'replacement_restore_passed': restore_pass,
        'restore_result': {'path': str(restore_result_path), 'sha256': p.digest(restore_result_path)},
        'restore_verifier': {'path': str(restore_verifier_path), 'sha256': p.digest(restore_verifier_path)},
        'user_saves_or_manual_runtime_deleted': False,
        'seal_status': 'PREVIEW_ONLY_NO_APPLY',
    }
    (FOLDER / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': plan['status'], 'replacement_run_passed': replacement_passed,
                      'native_status': result.get('status'), 'verifier_status': verifier.get('status'),
                      'protected_files': len(protected_hashes), 'retired_previous_protected_paths': len(retired_protected)},
                     ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    seal_preview()
