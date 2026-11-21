"""Audit the prepared candidate after retirement and publish scoped progress."""
import argparse
from datetime import datetime, timezone
import gzip
import json
import os
from pathlib import Path
import sys

from run_stage import PROJECT, STAGE, PROGRESS, artifact, read, require, write
sys.path.insert(0, str(PROJECT / 'tools'))
from run_interactive_game import check_host_runtime_artifacts
from verify_world_builder_map_object import check_artifacts

BUILD_ID = '20261016T110835Z_800f48fd88c0'
ATTESTATION = STAGE / f'attestation_{BUILD_ID}.json'
BUILD_REPORT = PROJECT / f'evidence/ui_window_host/{BUILD_ID}/build_result.json'
AUDIT = STAGE / 'post_retirement_audit.json'


def audit():
    require(not AUDIT.exists(), 'Refusing to overwrite the post-retirement audit')
    build, prepared, scope = read(BUILD_REPORT), read(STAGE / 'prepared.json'), read(STAGE / 'scope.json')
    require(read(STAGE / 'cleanup/result.json')['status'] == 'COMPLETE', 'Cleanup is incomplete')
    plan = json.loads(gzip.decompress((STAGE / 'cleanup/plan.json.gz').read_bytes()))
    retired = {row['path']: row for row in plan['files']}
    validation = check_host_runtime_artifacts(build)
    absent = validation['absent_discovery_objects']
    require(len(absent) == 5 and all(row['original_path'] in retired and
            row['sha256'] == retired[row['original_path']]['sha256'] for row in absent),
            'Runtime preflight does not match the exact retired discovery objects')
    request_path = Path(prepared['request']['path'])
    request = read(request_path)
    check_artifacts(request)
    for row in scope['protected_artifacts'].values():
        require(artifact(Path(row['path'])) == row, 'Protected current/recovery artifact changed')
    runtime = PROJECT / 'Build/InteractiveGameRuntime' / prepared['run_id']
    evidence = PROJECT / 'evidence/interactive_game' / prepared['run_id']
    require(not (runtime / 'sessions').exists() and not any((evidence / name).exists() for name in
            ('attempt.json', 'result.json', 'driver_result.json')), 'Unexpected native execution outputs')
    by_path = {row['path']: row for row in request['runtime_inputs']}
    immutable = []
    for row in request['materializations']:
        if row.get('materialization_method') != 'hardlink':
            continue
        target, cache = Path(row['target']), Path(row['cache'])
        ti, ci = target.stat(), cache.stat()
        require(ti.st_ino and (ti.st_dev, ti.st_ino) == (ci.st_dev, ci.st_ino) and
                ti.st_nlink >= 2 and ci.st_nlink >= 2 and ti.st_file_attributes & 1 and ci.st_file_attributes & 1,
                'Immutable runtime/cache identity or readonly policy changed')
        require(artifact(target)['sha256'] == artifact(cache)['sha256'] == row['sha256'] == by_path[str(target)]['sha256'],
                'Runtime/cache payload mismatch')
        immutable.append({'target': artifact(target), 'cache': artifact(cache),
                          'identity': [ti.st_dev, ti.st_ino], 'link_count': ti.st_nlink,
                          'readonly': True, 'cache_method': row['cache_method']})
    require(len(immutable) == 15, 'Unexpected immutable cache-link set')
    databases = []
    for row in request['runtime_inputs']:
        if Path(row['path']).suffix.lower() != '.db':
            continue
        si, ti = Path(row['source']).stat(), Path(row['path']).stat()
        require((si.st_dev, si.st_ino) != (ti.st_dev, ti.st_ino) and not ti.st_file_attributes & 1,
                'Private database is aliased or readonly')
        databases.append({'path': row['path'], 'bytes': ti.st_size,
                          'source_identity': [si.st_dev, si.st_ino], 'private_identity': [ti.st_dev, ti.st_ino]})
    require(len(databases) == 2, 'Expected two isolated writable databases')
    leftovers = []
    for root in (runtime, PROJECT / 'Build/RuntimeInputCache'):
        leftovers.extend(str(path) for path in root.rglob('*')
                         if '.tmp-' in path.name or path.name.endswith('.tmp') or path.name.startswith('.publish-'))
    require(not leftovers, 'Owned runtime/cache publication temporary files remain')
    attestation = read(ATTESTATION)
    require(attestation['status'] == 'PASS' and attestation['build_report']['sha256'] == artifact(BUILD_REPORT)['sha256'] and
            attestation['executable']['sha256'] == artifact(Path(build['executable']['path']))['sha256'], 'Wrong PE attestation')
    for relative, row in attestation['approved_feature_sources'].items():
        require(artifact(PROJECT / relative)['sha256'] == row['sha256'], 'Feature source drifted after PE attestation')
    record = {'schema': 'zerosis.owned_save_delete.post_retirement_audit.v1', 'status': 'PASS',
        'utc': datetime.now(timezone.utc).isoformat(), 'run_id': prepared['run_id'],
        'build': artifact(BUILD_REPORT), 'request': artifact(request_path), 'attestation': artifact(ATTESTATION),
        'runtime_preflight_after_object_retirement': validation, 'immutable_cache_links': immutable,
        'private_databases': databases, 'owned_temp_or_cache_publish_leftovers': leftovers,
        'runtime_and_request_artifacts_still_valid': True, 'protected_artifacts_unchanged': True,
        'host_gamecore_hwnd_executed': False, 'retail_mods_saves_settings_or_processes_accessed': False}
    write(AUDIT, record)
    print(json.dumps({'status': record['status'], 'retired_discovery_objects': len(absent),
                      'cache_links': len(immutable), 'private_databases': len(databases), 'audit': artifact(AUDIT)}))


def finalize(storage_path):
    output = STAGE / 'conformance.json'
    require(not output.exists(), 'Refusing to overwrite final conformance')
    scope, prepared, attestation = read(STAGE / 'scope.json'), read(STAGE / 'prepared.json'), read(ATTESTATION)
    audit_result, cleanup, build = read(AUDIT), read(STAGE / 'cleanup/result.json'), read(BUILD_REPORT)
    require(artifact(PROGRESS) == scope['progress_before'], 'Progress changed since this stage was scoped')
    require(attestation['status'] == audit_result['status'] == 'PASS' and cleanup['status'] == 'COMPLETE', 'Candidate proofs failed')
    require(prepared['native_process_or_ctypes_calls'] == 0 and prepared['forbidden_access_attempts'] == [] and
            prepared['host_gamecore_or_windows_executed'] is False, 'Preparation isolation proof failed')
    require(build['source_hashes_before'] == build['source_hashes_after'], 'Build input drift')
    after, before = read(storage_path), read(Path(scope['storage_before']['path']))
    require(after['status'] == 'COMPLETE_METADATA_AUDIT' and not after['errors'] and not after['skipped'] and
            after['root'] == before['root'] == str(PROJECT), 'Final storage audit incomplete or outside project')
    proofs = {name: artifact(path) for name, path in {
        'scope': STAGE / 'scope.json', 'build': BUILD_REPORT, 'build_invocation': STAGE / 'build_invocation.json',
        'pe_attestation': ATTESTATION, 'prepare_invocation': STAGE / 'prepare_invocation.json',
        'prepared': STAGE / 'prepared.json', 'post_retirement_audit': AUDIT,
        'cleanup_plan': STAGE / 'cleanup/plan.json.gz', 'cleanup_result': STAGE / 'cleanup/result.json',
        'retirement_preflight': STAGE / 'retirement_preflight.json', 'storage_after': storage_path,
    }.items()}
    storage = {'before_unique_GetCompressedFileSizeW_bytes': before['unique_allocated_bytes'],
        'after_unique_GetCompressedFileSizeW_bytes': after['unique_allocated_bytes'],
        'net_unique_increase_bytes': after['unique_allocated_bytes'] - before['unique_allocated_bytes'],
        'after_GiB': after['unique_allocated_bytes'] / 1024**3,
        'removed_files': cleanup['removed_files'], 'removed_logical_path_bytes': cleanup['removed_logical_bytes'],
        'removed_standard_allocation_bytes': cleanup['removed_standard_allocation_bytes'],
        'removed_GetCompressedFileSizeW_bytes': cleanup['removed_get_compressed_file_size_bytes'],
        'full_project_copies_created': 0,
        'limits': 'Per unique NTFS identity. Standard allocation and GetCompressedFileSizeW are separate metrics; neither is measured volume free space. Final conformance/progress publication follows the audit.'}
    verification = {'compile_link': build['status'], 'actual_architecture': build['executable']['pe'],
        'actual_pe_catalog_entries': attestation['pe_catalog']['entry_count'],
        'actual_pe_payloads_matched': len(attestation['pe_catalog']['exact_payloads']),
        'attestation_rehashed_input_count': attestation['read_input_count'],
        'current_cpp_lua_header_embedded': True, 'current_frozen_python_support_files': prepared['current_python_support_count'],
        'private_runtime_inputs': prepared['runtime_inputs'], 'immutable_cache_links': len(audit_result['immutable_cache_links']),
        'native_process_or_ctypes_calls_during_preparation': 0,
        'host_gamecore_hwnd_executed': False, 'native_delete_verified': False,
        'retail_ui_or_save_mod_compatibility_verified': False, 'default_promoted': False,
        'retail_mod_test_hold_active': True, 'full_engine_goal_complete': False}
    remaining = ['After explicit human mod-test end, verify actual x64 Host/Lua/SDK window, original menu lifecycle and physical Korean IME.',
        'Verify actual named save, confirmation/cancel/delete/refresh, normal close and fresh SDK restore using B6 20261016T110835Z_800f48fd88c0 and R6 20261016T111333Z_1c377d9577e6.',
        'Complete remaining original UI/3D/campaign, original Civ5Save and active-mod compatibility, multicore performance and long-run stability.']
    record = {'schema': 'zerosis.owned_save_delete.linked_candidate_conformance.v1',
        'utc': datetime.now(timezone.utc).isoformat(), 'status': 'PASS_CURRENT_X64_LINK_PE_PAYLOAD_AND_PRIVATE_PREPARATION_ONLY',
        'previous_interrupted_goal_turn': 'NO_COMPLETED_BUILD: invocation absent, no newer Host and exact owned process query returned zero; this turn performed the real build.',
        'build_id': BUILD_ID, 'run_id': prepared['run_id'], 'proofs': proofs, 'verification': verification, 'storage': storage,
        'retired_older_component': {'id': '20261014T215629Z_9b67a5d13f24', 'duplicate_inputs_and_executables_removed': 395,
            'unique_old_sources_retained': 3, 'historical_reports_are_not_complete_live_build_closures': True},
        'native_result_created': False, 'default_and_recovery_artifacts_unchanged': True,
        'retail_mods_user_saves_settings_or_processes_accessed': False, 'remaining_gates': remaining,
        'limits': ['Exact linked PE bytes and guarded private preparation do not prove live native deletion or gameplay.',
            'Existing component/Lua/frozen CPU tests retain their source-stage scope and were not rerun or relabelled as native acceptance.',
            'The prior EA0.6 default is retained; this candidate is not a default promotion.']}
    write(output, record)
    progress = read(PROGRESS)
    progress.update(utc=record['utc'], status='CURRENT_DELETE_UI_X64_CANDIDATE_PREPARED_NATIVE_ACCEPTANCE_PENDING',
        prior_goal_turn_classification='progress: regenerated latest UI, built and linked one current x64 candidate, verified all actual PE payloads, prepared isolated matching runtime, retired 405 generated files and revalidated runtime inputs',
        current_host_build_id=BUILD_ID, latest_source_matches_linked_candidate=True,
        latest_source_matches_integrated_syntax_proof=False, latest_cpp_source_matches_actual_host_syntax_proof=False,
        latest_current_source_compile_link_proof=proofs['build'], latest_current_source_pe_attestation=proofs['pe_attestation'],
        prepared_runtime_matches_current_linked_candidate=True, prepared_runtime_matches_latest_source=True,
        latest_full_source_embedding_limit='Current C++/generated header/Lua match the B6 actual PE, and current five-file Python support matches R6. Native Host/SDK/window/delete acceptance remains unexecuted; EA0.6 default and B5/R4 recovery are unchanged.')
    progress['current_prepared_runtime'] = {'run_id': prepared['run_id'], 'host_build_id': BUILD_ID,
        'status': 'PREPARED_NOT_EXECUTED', 'request': prepared['request'], 'prepared': proofs['prepared'],
        'runtime_identity_audit': proofs['post_retirement_audit'], 'shared_input_hardlinks': prepared['hardlinks'],
        'existing_cache_hits': prepared['cache_hits'], 'new_host_cache_objects': prepared['new_cache_objects'],
        'current_source_candidate': True, 'process_or_ctypes_library_calls': 0,
        'retail_mods_saves_settings_or_processes_accessed_this_stage': False,
        'gamecore_or_windows_executed': False, 'native_result_created': False, 'default_promoted': False,
        'native_runtime_acceptance': False, 'private_policy_info_settings': artifact(STAGE / 'PolicyInfo.ini')}
    progress['owned_save_delete_linked_candidate_stage'] = {'conformance': artifact(output),
        'verification': verification, 'remaining_gates': remaining}
    progress['next_native_gates'] = remaining
    progress['proofs']['owned_save_delete_linked_conformance'] = artifact(output)
    progress['proofs']['owned_save_delete_linked_storage_after'] = proofs['storage_after']
    progress['storage'].update(latest_measured_unique_GetCompressedFileSizeW_bytes=after['unique_allocated_bytes'],
        latest_measured_utc=after['utc'], owned_save_delete_linked_stage=storage)
    progress['user_mod_test_isolation'].update(retail_test_hold_still_active=True,
        retail_MODS_user_saves_or_game_processes_accessed_this_stage=False,
        game_Host_GameCore_HWND_or_component_windows_executed_this_stage=False,
        retail_settings_accessed_this_stage=False, original_user_settings_read_this_stage=False,
        current_stage_policy_source='EXPLICIT_PRIVATE_POLICY_INFO_INI')
    require(artifact(PROGRESS) == scope['progress_before'], 'Progress changed during final publication')
    write(PROGRESS, progress)
    print(json.dumps({'status': record['status'], 'conformance': artifact(output), 'progress': artifact(PROGRESS), 'storage': storage}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('audit', 'finalize'))
    parser.add_argument('--storage', type=Path)
    args = parser.parse_args()
    if args.action == 'audit':
        audit()
    else:
        require(args.storage is not None, 'Final storage report is required')
        finalize(args.storage.resolve(strict=True))
