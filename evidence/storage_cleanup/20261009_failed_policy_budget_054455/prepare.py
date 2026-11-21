"""Create an unsealed inventory for exactly Host11 and failed Fresh09."""
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

    host_id = '20261009T053807Z_9b02197a2dc5'
    run_id = '20261009T054455Z_d49bca51b672'
    session_id = 'cf9c5cfb46c19f1d79c20eead31d56df'
    targets = [
        ROOT / 'Build/UiWindowHost' / host_id,
        ROOT / 'evidence/ui_window_host' / host_id,
        ROOT / 'Build/InteractiveGameRuntime' / run_id,
        ROOT / 'evidence/interactive_game' / run_id,
    ]
    targets = [p.legal_target(path) for path in targets]
    for target in targets:
        if not target.is_dir():
            raise RuntimeError('Expected exact cleanup target is missing: ' + str(target))

    host_evidence, evidence = targets[1], targets[3]
    session = targets[2] / 'sessions' / session_id
    preserve_map = [
        (host_evidence / 'build_result.json', 'host11-build-result.json.gz'),
        (targets[0] / 'frozen/ui_assets/prepared.json', 'host11-prepared-ui-assets.json.gz'),
        (targets[0] / 'frozen/project/Source/Host/UiScene.lua', 'host11-frozen-UiScene.lua.gz'),
        (targets[0] / 'frozen/project/Source/Presentation/UiPresentationInput.lua', 'host11-frozen-UiPresentationInput.lua.gz'),
        (evidence / 'result.json', 'fresh09-result.json.gz'),
        (evidence / 'request.json', 'fresh09-request.json.gz'),
        (evidence / 'driver_result.json', 'fresh09-driver-result.json.gz'),
        (evidence / 'stdout.log', 'fresh09-stdout.log.gz'),
        (evidence / 'stderr.log', 'fresh09-stderr.log.gz'),
        (evidence / 'social_policy_validation.json', 'fresh09-policy-validation.json.gz'),
        (session / 'play-ui-21/scene_manifest.json', 'fresh09-initial-play-ui-21-scene-manifest.json.gz'),
        (session / 'play-scene-14-gpu.png', 'fresh09-gpu-frame-14.png.gz'),
    ]
    preserved = []
    for source, name in preserve_map:
        source = p.boundary(source)
        info = p.regular(source)
        if not any(source.is_relative_to(target) for target in targets):
            raise RuntimeError('Preservation source is outside the four exact targets: ' + str(source))
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
        'scope': 'EXACT_HOST11_AND_FAILED_FRESH09_FOUR_DIRECTORIES',
        'project_root': str(ROOT), 'targets': directory_rows,
        'file_count': total_files, 'logical_bytes': total_logical,
        'estimated_reclaimable_file_storage_bytes': reclaimable,
        'physical_reclaim_estimate_policy': 'sum NTFS stored bytes only for identities whose links all lie in these targets',
        'ledger': {'path': str(ledger), 'sha256': ledger_sha, 'rows': total_files,
                   'row_schema': ['path', 'sha256', 'bytes', 'mtime_ns', 'device', 'file_id']},
        'preserved_compressed_evidence': preserved,
        'preserved_total_source_bytes': sum(row['source_bytes'] for row in preserved),
        'preserved_total_compressed_bytes': sum(row['compressed_bytes'] for row in preserved),
        'replacement_host': '20261009T060050Z_08e7af2cdffa',
        'replacement_run': '20261009T060253Z_512de85593a8',
        'protected_final_base_for_later_seal': 'evidence/storage_cleanup/20261009_failed_policy_input_051138/protected-final.json.gz',
        'seal_status': 'NOT_RUN_SOURCE_REHASH_AND_PROTECTED_SET_NOT_CREATED',
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
