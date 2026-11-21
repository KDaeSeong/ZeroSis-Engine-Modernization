"""Seal the reviewed Host10/Fresh08 inventory after all source edits stop."""
import gzip
import json
from pathlib import Path
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as p

p.no_active_host()
assert not (FOLDER / 'plan.json').exists()
inventory = json.loads((FOLDER / 'inventory.json').read_text(encoding='utf8'))
assert inventory['status'] == 'INVENTORY_ONLY_NOT_SEALED'
assert p.digest(Path(inventory['ledger']['path'])) == inventory['ledger']['sha256']
targets = [p.legal_target(ROOT / row['path']) for row in inventory['targets']]
assert len(targets) == 4
base = ROOT / 'evidence/storage_cleanup/20261009_failed_policy_render_044447/protected-final.json.gz'
with gzip.open(base, 'rt', encoding='utf8') as stream:
    previous = json.load(stream)
retired_protected = [name for name in previous if any(Path(name).is_relative_to(t) for t in targets)]
names = {name for name in previous if name not in retired_protected}
for group in ('Source', 'Tests', 'tools',
              'Build/UiWindowHost/20261009T053807Z_9b02197a2dc5',
              'evidence/ui_window_host/20261009T053807Z_9b02197a2dc5',
              'Build/InteractiveGameRuntime/20261009T054455Z_d49bca51b672',
              'evidence/interactive_game/20261009T054455Z_d49bca51b672',
              'evidence/social_policy_scene/20261009_policy_input_layout',
              'evidence/social_policy_scene/20261009_policy_refresh_batch'):
    directory = p.boundary(ROOT / group)
    for path, info in p.inventory(directory):
        names.add(str(path))
for row in inventory['preserved_compressed_evidence']:
    path = p.boundary(Path(row['path']))
    assert p.digest(path) == row['sha256']
    import hashlib
    with gzip.open(path, 'rb') as stream:
        assert hashlib.file_digest(stream, 'sha256').hexdigest() == row['uncompressed_sha256']
    names.add(str(path))
hashes, protected = {}, {}
for name in sorted(names):
    path = p.boundary(Path(name))
    assert not any(path.is_relative_to(t) for t in targets)
    info = p.regular(path)
    identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
    if identity not in hashes:
        hashes[identity] = p.digest(path)
    protected[name] = hashes[identity]
destination = FOLDER / 'protected-final.json.gz'
with gzip.open(destination, 'wt', encoding='utf8') as stream:
    json.dump(protected, stream)
plan = {
    'root': str(ROOT), 'status': 'PREVIEW_ONLY',
    'scope': 'EXACT_SUPERSEDED_HOST10_AND_FAILED_POLICY_INPUT_FRESH08',
    'script_sha256': p.digest(ROOT / 'tools/prune_superseded_runtime_artifacts.py'),
    'ledger': inventory['ledger'], 'directories': inventory['targets'],
    'files': inventory['file_count'], 'logical_bytes': inventory['logical_bytes'],
    'estimated_reclaimable_file_storage': inventory['estimated_reclaimable_file_storage_bytes'],
    'preserved_compressed_inputs_and_diagnostics': inventory['preserved_compressed_evidence'],
    'protected': {'path': str(destination), 'sha256': p.digest(destination)},
    'protected_files': len(protected), 'previous_protected': {'path': str(base), 'sha256': p.digest(base)},
    'explicitly_retired_previous_protected_paths': retired_protected,
    'replacement_host': inventory['current_replacement_host'], 'replacement_run': inventory['replacement_run'],
    'replacement_run_passed': False,
    'replacement_scope': 'Native BranchButton0/No/Yes dispatch and SDK branch-zero command reached; policy-dirty exhausted unchanged instruction limit.',
    'user_saves_or_manual_runtime_deleted': False,
}
(FOLDER / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2)+'\n', encoding='utf8')
print(json.dumps({'status': plan['status'], 'files': plan['files'], 'protected_files': len(protected),
                  'retired_previous_protected_paths': len(retired_protected), 'directories': plan['directories']}))
