"""Create an unsealed inventory for exactly the failed Fresh12 runtime pair."""
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

FOLDER = Path(__file__).resolve().parent
ROOT = FOLDER.parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import prune_superseded_runtime_artifacts as p


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf8')


def inventory_only() -> None:
    if (FOLDER / 'inventory.json').exists() or (FOLDER / 'retired-files.jsonl.gz').exists():
        raise RuntimeError('Inventory output already exists; refusing to overwrite it')
    p.no_active_host()

    run_id = '20261009T064236Z_270107c2b878'
    session_id = 'ba0135cefbff8d0478595f37a853ec90'
    targets = [
        ROOT / 'Build/InteractiveGameRuntime' / run_id,
        ROOT / 'evidence/interactive_game' / run_id,
    ]
    targets = [p.legal_target(path) for path in targets]
    for target in targets:
        if not target.is_dir():
            raise RuntimeError('Expected exact cleanup target is missing: ' + str(target))

    runtime, evidence = targets
    session = runtime / 'sessions' / session_id
    support_tools = runtime / 'interactive_ui_support/tools'
    preserve_map = [
        (evidence / 'result.json', 'fresh12-result.json.gz'),
        (evidence / 'request.json', 'fresh12-request.json.gz'),
        (evidence / 'driver_result.json', 'fresh12-driver-result.json.gz'),
        (evidence / 'stdout.log', 'fresh12-stdout.log.gz'),
        (evidence / 'stderr.log', 'fresh12-stderr.log.gz'),
        (evidence / 'social_policy_validation.json', 'fresh12-policy-validation.json.gz'),
        (evidence / 'policy_progress_review.json', 'fresh12-policy-progress-review.json.gz'),
        (session / 'play-ui-29.json', 'fresh12-play-ui-29.json.gz'),
        (session / 'play-ui-29/prepare.log', 'fresh12-play-ui-29-prepare.log.gz'),
        (session / 'social-policy-before-inventory.json', 'fresh12-policy-before-inventory.json.gz'),
        (session / 'social-policy-cancelled-inventory.json', 'fresh12-policy-cancelled-inventory.json.gz'),
        (session / 'social-policy-branch-inventory.json', 'fresh12-policy-branch-inventory.json.gz'),
        (session / 'social-policy-funded-inventory.json', 'fresh12-policy-funded-inventory.json.gz'),
        (session / 'social-policy-adopted-inventory.json', 'fresh12-policy-adopted-inventory.json.gz'),
        (support_tools / 'ui_pixel_scene.py', 'fresh12-frozen-ui-pixel-scene.py.gz'),
    ]
    optional_map = [
        (session / 'play-ui-29/preparation_failure.json', 'fresh12-play-ui-29-preparation-failure.json.gz'),
    ]
    preserve_map.extend((source, name) for source, name in optional_map if source.exists())

    preserved = []
    for source, name in preserve_map:
        source = p.boundary(source)
        info = p.regular(source)
        if not any(source.is_relative_to(target) for target in targets):
            raise RuntimeError('Preservation source is outside the two exact targets: ' + str(source))
        before = p.digest(source)
        destination = FOLDER / name
        if destination.exists():
            raise RuntimeError('Refusing to overwrite preserved evidence: ' + str(destination))
        with source.open('rb') as inp, gzip.open(destination, 'wb', compresslevel=9) as out:
            shutil.copyfileobj(inp, out)
        with gzip.open(destination, 'rb') as stream:
            decoded = hashlib.file_digest(stream, 'sha256').hexdigest()
        if decoded != before or p.digest(source) != before:
            raise RuntimeError('Compressed copy or original source hash changed: ' + str(source))
        preserved.append({
            'source': str(source.relative_to(ROOT)), 'source_bytes': info.st_size,
            'uncompressed_sha256': before, 'path': str(destination),
            'sha256': p.digest(destination), 'compressed_bytes': destination.stat().st_size,
        })

    ledger = FOLDER / 'retired-files.jsonl.gz'
    identities, hashed = {}, {}
    directory_rows = []
    total_files = total_logical = 0
    with gzip.open(ledger, 'wt', encoding='utf8', newline='\n') as stream:
        for target in targets:
            count = logical = 0
            rows = sorted(p.inventory(target), key=lambda item: str(item[0]).casefold())
            for path, info in rows:
                digest_key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                if digest_key not in hashed:
                    hashed[digest_key] = p.digest(path)
                identity = (info.st_dev, info.st_ino)
                stored = identities.setdefault(identity, {
                    'links': info.st_nlink, 'count': 0, 'stored_bytes': p.stored(path),
                })
                if stored['links'] != info.st_nlink:
                    raise RuntimeError('Hardlink count changed during inventory: ' + str(path))
                stored['count'] += 1
                stream.write(json.dumps({
                    'path': str(path.relative_to(ROOT)), 'sha256': hashed[digest_key],
                    'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns,
                    'device': int(info.st_dev), 'file_id': int(info.st_ino),
                }, ensure_ascii=False, sort_keys=True) + '\n')
                count += 1
                logical += info.st_size
            directory_rows.append({
                'path': str(target.relative_to(ROOT)), 'files': count, 'logical_bytes': logical,
            })
            total_files += count
            total_logical += logical

    reclaimable = sum(v['stored_bytes'] for v in identities.values() if v['count'] == v['links'])
    ledger_sha = p.digest(ledger)
    report = {
        'status': 'INVENTORY_ONLY_NOT_SEALED',
        'scope': 'EXACT_FAILED_FRESH12_RUNTIME_AND_EVIDENCE_DIRECTORIES',
        'project_root': str(ROOT), 'targets': directory_rows,
        'file_count': total_files, 'logical_bytes': total_logical,
        'estimated_reclaimable_file_storage_bytes': reclaimable,
        'physical_reclaim_estimate_policy': 'sum NTFS stored bytes only for identities whose links all lie in these targets',
        'ledger': {'path': str(ledger), 'sha256': ledger_sha, 'rows': total_files,
                   'row_schema': ['path', 'sha256', 'bytes', 'mtime_ns', 'device', 'file_id']},
        'preserved_compressed_evidence': preserved,
        'preserved_total_source_bytes': sum(row['source_bytes'] for row in preserved),
        'preserved_total_compressed_bytes': sum(row['compressed_bytes'] for row in preserved),
        'replacement_host': '20261009T063449Z_4cc92cfed9b4',
        'replacement_run': '20261009T065612Z_717e525d9e22',
        'protected_final_base_for_later_seal': 'evidence/storage_cleanup/20261009_failed_policy_driver_060253/protected-final.json.gz',
        'seal_status': 'NOT_RUN_SOURCE_AND_RESTORE_DEPENDENCY_REHASH_NOT_CREATED',
        'apply_status': 'NOT_RUN_NO_TARGET_DELETED',
    }
    write(FOLDER / 'inventory.json', report)
    if p.digest(ledger) != ledger_sha:
        raise RuntimeError('Retired-files ledger hash changed after inventory write')
    print(json.dumps({
        'status': report['status'], 'files': total_files, 'logical_bytes': total_logical,
        'estimated_reclaimable_file_storage_bytes': reclaimable,
        'preserved_files': len(preserved), 'ledger_sha256': ledger_sha,
    }, ensure_ascii=False, sort_keys=True))


if __name__ == '__main__':
    inventory_only()
