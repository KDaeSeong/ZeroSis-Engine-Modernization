"""Inventory only the failed tenet-stage-17 runtime pair; never seal or delete.

Run only after the replacement fresh/restore pair passes and no Host is active.
The retained Host is not a retirement target. Only small diagnostic files are
compressed; runtime binaries, databases, textures, frames, and saves are not.
"""
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

RUN_ID = '20261009T075113Z_315e609b50e6'
SESSION_ID = '69d318a024efdf06d7893a75e3c11e18'
RETAINED_HOST = '20261009T074845Z_3b9099f7c315'
FROZEN_TIMELINE_SHA256 = '028e0b4136526cc1940d3028a95e4f8166cc98d5ba3cfc1ab0f837a056f29fa9'
CORRECTED_TIMELINE_SHA256 = 'd1f9ee631f0480bb352a8c04b371437b1c8dc860dc7017c07dd93728eae0bf45'


def write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf8')


def inventory_only() -> None:
    if (FOLDER / 'inventory.json').exists() or (FOLDER / 'retired-files.jsonl.gz').exists():
        raise RuntimeError('Inventory output already exists; refusing to overwrite it')
    p.no_active_host()
    p.boundary(FOLDER)

    targets = [
        ROOT / 'Build/InteractiveGameRuntime' / RUN_ID,
        ROOT / 'evidence/interactive_game' / RUN_ID,
    ]
    targets = [p.legal_target(path) for path in targets]
    for target in targets:
        if not target.is_dir():
            raise RuntimeError('Expected exact cleanup target is missing: ' + str(target))

    runtime, evidence = targets
    session = runtime / 'sessions' / SESSION_ID
    support_tools = runtime / 'interactive_ui_support/tools'
    preserve_map = [
        (evidence / 'result.json', 'failed-tenet-result.json.gz'),
        (evidence / 'request.json', 'failed-tenet-request.json.gz'),
        (evidence / 'driver_result.json', 'failed-tenet-driver-result.json.gz'),
        (evidence / 'stdout.log', 'failed-tenet-stdout.log.gz'),
        (evidence / 'stderr.log', 'failed-tenet-stderr.log.gz'),
        (evidence / 'social_policy_tenet_timeline.py', 'failed-tenet-frozen-timeline.py.gz'),
        (evidence / 'runner.py', 'failed-tenet-frozen-runner.py.gz'),
        (evidence / 'host_build.json', 'failed-tenet-host-build.json.gz'),
        (evidence / 'interactive_ui_support.json', 'failed-tenet-ui-support.json.gz'),
        (support_tools / 'interactive_ui_driver.py', 'failed-tenet-frozen-ui-driver.py.gz'),
    ]
    inventory_names = [
        'tenet-initial-inventory.json',
        'tenet-before-inventory.json',
        'tenet-cancelled-inventory.json',
        'tenet-free-1-inventory.json',
        'tenet-free-2-inventory.json',
        'tenet-funded-inventory.json',
        'tenet-adopted-inventory.json',
        'tenet-returned-inventory.json',
        'tenet-next-turn-inventory.json',
    ]
    preserve_map.extend((session / name, 'failed-' + name + '.gz') for name in inventory_names)

    frozen_timeline = p.boundary(evidence / 'social_policy_tenet_timeline.py')
    p.regular(frozen_timeline)
    if p.digest(frozen_timeline) != FROZEN_TIMELINE_SHA256:
        raise RuntimeError('The failed run frozen timeline differs from the reviewed source')
    corrected_timeline = p.boundary(ROOT / 'tools/social_policy_tenet_timeline.py')
    corrected_info = p.regular(corrected_timeline)
    if p.digest(corrected_timeline) != CORRECTED_TIMELINE_SHA256:
        raise RuntimeError('The retained corrected timeline changed; update provenance before inventory')

    # Both frozen runner paths contain identical bytes; archive one copy only.
    runner_alias = p.boundary(evidence / 'frozen_inputs/run_interactive_game.py')
    runner_alias_info = p.regular(runner_alias)
    runner_alias_sha = p.digest(runner_alias)
    runner = p.boundary(evidence / 'runner.py')
    p.regular(runner)
    if p.digest(runner) != runner_alias_sha:
        raise RuntimeError('Frozen runner paths differ; review both before inventory')

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
    if p.digest(corrected_timeline) != CORRECTED_TIMELINE_SHA256 or p.digest(runner_alias) != runner_alias_sha:
        raise RuntimeError('Retained timeline or duplicate frozen runner changed during inventory')
    report = {
        'status': 'INVENTORY_ONLY_NOT_SEALED',
        'scope': 'EXACT_FAILED_TENET_STAGE17_RUNTIME_AND_EVIDENCE_DIRECTORIES',
        'project_root': str(ROOT), 'run_id': RUN_ID, 'session_id': SESSION_ID,
        'targets': directory_rows,
        'file_count': total_files, 'logical_bytes': total_logical,
        'estimated_reclaimable_file_storage_bytes': reclaimable,
        'physical_reclaim_estimate_policy': 'sum NTFS stored bytes only for identities whose links all lie in these targets',
        'ledger': {'path': str(ledger), 'sha256': ledger_sha, 'rows': total_files,
                   'row_schema': ['path', 'sha256', 'bytes', 'mtime_ns', 'device', 'file_id']},
        'preserved_compressed_evidence': preserved,
        'preserved_total_source_bytes': sum(row['source_bytes'] for row in preserved),
        'preserved_total_compressed_bytes': sum(row['compressed_bytes'] for row in preserved),
        'preserved_source_aliases': [{
            'source': str(runner_alias.relative_to(ROOT)), 'source_bytes': runner_alias_info.st_size,
            'uncompressed_sha256': runner_alias_sha,
            'preserved_as': str(FOLDER / 'failed-tenet-frozen-runner.py.gz'),
        }],
        'stage17_diagnostic_provenance': {
            'failure': 'Tenet stage 17 has the wrong key kind, modal lifecycle, or command count',
            'frozen_timeline_sha256': FROZEN_TIMELINE_SHA256,
            'retained_corrected_timeline': {
                'path': str(corrected_timeline.relative_to(ROOT)), 'bytes': corrected_info.st_size,
                'sha256': CORRECTED_TIMELINE_SHA256, 'copied': False,
            },
            'stdout_action': 'INTERACTIVE_SOCIAL_POLICY_TENET_ACTION=17|CloseButton|318|29|36|-1',
            'stdout_input': 'INTERACTIVE_SOCIAL_POLICY_INPUT=2|318|0|1|0|0|0|0',
            'corrected_contract': {'close_active': 1, 'close_timer': 0, 'close_modal': 0,
                                   'original_shown_data1': -1, 'original_shown_data2': -1},
            'diagnostic_note': 'Frozen checker expected active=0 on close; native record remains active=1 with timer=0 and modal=0. This inventory does not rerun or reclassify the failed run.',
        },
        'retained_host': RETAINED_HOST,
        'retained_host_is_cleanup_target': False,
        'seal_status': 'NOT_RUN_CURRENT_SOURCE_SAVE_AND_RESTORE_DEPENDENCY_REHASH_NOT_CREATED',
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
