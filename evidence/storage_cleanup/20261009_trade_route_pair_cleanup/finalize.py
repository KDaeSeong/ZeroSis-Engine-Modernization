"""Summarize this retirement only after its live preservation checks pass."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ACTIVE = HERE / 'recovery_01'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def artifact(path):
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': sha, 'bytes': path.stat().st_size}


def main():
    destination = HERE / 'summary.json'
    if destination.exists():
        raise RuntimeError('Do not overwrite the completed retirement summary')
    audit_path = Path(sys.argv[1]).resolve(strict=True)
    if audit_path.parent != ROOT / 'evidence/storage':
        raise RuntimeError('Expected a fresh project storage audit')
    plan = read(ACTIVE / 'plan.json')
    cleanup = read(ACTIVE / 'cleanup.json')
    validation = read(HERE / 'post_cleanup_validation.json')
    audit = read(audit_path)
    compression_path = ROOT / 'evidence/storage/20261008T235958Z_ae3785675da6/compression.json'
    compression = read(compression_path)
    previous_path = ROOT / 'evidence/storage_cleanup/20261008T232529Z_final_state/summary.json'
    previous = read(previous_path)
    assert cleanup['status'] == 'PASS_OBSOLETE_ARTIFACT_RETIREMENT' and not cleanup['errors']
    assert cleanup['protected_hashes_verified_before'] and cleanup['protected_hashes_verified_after']
    assert cleanup['plan_sha256'] == artifact(ACTIVE / 'plan.json')['sha256']
    assert cleanup['removed_files'] == plan['files']
    assert len(cleanup['completed_directories']) == len(plan['directories']) == 6
    assert all(not (ROOT / row['path']).exists() for row in plan['directories'])
    assert validation['status'] == 'PASS_MANUAL_NEW_CONTINUE_AND_ALL_SAVED_BUNDLES'
    assert validation['count'] == 10 and validation['user_saves'] == 8 and validation['saves_unchanged']
    assert not validation['errors']
    assert audit['status'] == 'COMPLETE_METADATA_AUDIT' and not audit['errors'] and not audit['skipped']
    assert compression['status'] == 'PASS_RETAINED_CONTENT_COMPRESSION' and not compression['errors']
    assert compression['selected_files'] == 416 and compression['deleted_files'] == 0
    evidence = {name: artifact(path) for name, path in {
        'plan': ACTIVE / 'plan.json', 'retirement': ACTIVE / 'cleanup.json',
        'zero_deletion_interruption': HERE / 'cleanup.json',
        'launcher_validation': HERE / 'post_cleanup_validation.json',
        'fresh_storage_audit': audit_path, 'restore_compression': compression_path,
        'previous_summary': previous_path,
    }.items()}
    for name, run in zip(('fresh_trade_route', 'restore_trade_route'), plan['latest_runtime_pair']):
        proof_path = ROOT / 'evidence/interactive_game' / run / 'trade_route_validation.json'
        proof = read(proof_path)
        assert proof['status'] == 'PASS_INTERACTIVE_TRADE_ROUTE_NATIVE_SDK_SMOKE'
        evidence[name] = artifact(proof_path)
        if name == 'restore_trade_route':
            lineage = proof['evidence']['resume_lineage']
            assert lineage['source_run_id'] == plan['latest_runtime_pair'][0]
            assert lineage['startup_state_byte_equal'] and lineage['post_restore_turn'] == 2
    host = ROOT / 'Build/UiWindowHost' / plan['latest_host_build'] / 'final/ZeroSisHost_x64.exe'
    build_report = ROOT / 'evidence/ui_window_host' / plan['latest_host_build'] / 'build_result.json'
    evidence['host'] = artifact(host)
    evidence['host_build'] = artifact(build_report)
    assert evidence['host']['sha256'] == '1a17375383ccf79d595f1132f78780eb5b0edd46fa30c39271d3ad02235621e0'
    assert evidence['host_build']['sha256'] == previous['evidence']['host_build']['sha256']
    for save in validation['saves']:
        assert artifact(Path(save['path']))['sha256'] == save['sha256']
    initial = previous['unique_ntfs_file_allocation']['initial_before_bytes']
    current = audit['unique_allocated_bytes']
    summary = {
        'status': 'PASS_TRADE_ROUTE_PAIR_RETIREMENT_AND_PRESERVATION',
        'utc': datetime.now(timezone.utc).isoformat(), 'root': str(ROOT),
        'evidence': evidence,
        'unique_ntfs_file_allocation': {
            'initial_before_bytes': initial,
            'previous_checkpoint_bytes': previous['unique_ntfs_file_allocation']['final_bytes'],
            'final_bytes': current, 'total_reduction_bytes': initial - current,
            'total_reduction_percent': (initial - current) / initial * 100,
        },
        'logical_path_bytes': audit['logical_path_bytes'],
        'retirement': {
            'top_level_folders': 6, 'file_paths': cleanup['removed_files'],
            'logical_bytes': cleanup['removed_logical_bytes'],
            'estimated_reclaimable_file_storage': plan['estimated_reclaimable_file_storage'],
            'protected_files_hashed_before_and_after': plan['current_dependency_files'],
            'protected_hashes_unchanged': True,
            'retired_raw_paths_are_no_longer_available': True,
        },
        'restore_compression': {
            'files': compression['selected_files'],
            'stored_reduction_bytes': compression['stored_reduction'],
            'status': compression['status'],
        },
        'preservation': {
            'manual_launcher_and_ten_routes_unchanged': True,
            'user_saves_unchanged': 8, 'latest_host_and_build_report_unchanged': True,
            'gameplay_launched_by_cleanup_validation': False,
        },
        'engine_evidence_boundary': {
            'fresh_trade_route_independent_pass': True,
            'separate_process_restore_independent_pass': True,
            'restored_initial_sdk_state_byte_equal': True,
            'post_restore_turn': 2,
            'game_section_reload_metadata_or_rng_equivalence_proven': False,
            'manual_default_promoted': False, 'full_engine_complete': False,
        },
        'limits': [
            'Allocation counts unique NTFS file identities with compression, not volume free-space delta.',
            'The previous checkpoint predates the restore run; the final audit includes its retained artifacts.',
            'This summary and later small documentation edits are not included in the byte-exact audit total.',
            'Launcher PlanOnly checks and file hashes do not establish full-game playability.',
        ],
        'errors': [],
    }
    destination.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': summary['status'], 'summary': str(destination),
                      'unique_ntfs_file_allocation': summary['unique_ntfs_file_allocation'],
                      'retirement': summary['retirement']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
