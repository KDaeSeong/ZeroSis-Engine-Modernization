"""Publish the bounded overwrite integration result without running a game."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys

from run_stage import PROJECT, STAGE, PROGRESS, artifact, read, require, write

BUILD_ID = '20261016T122615Z_1af4a5449cf1'
RUN_ID = '20261016T123256Z_fae85fb9fe79'
BUILD_REPORT = PROJECT / f'evidence/ui_window_host/{BUILD_ID}/build_result.json'
ATTESTATION = STAGE / f'attestation_{BUILD_ID}.json'
BASE_AUDIT = PROJECT / 'evidence/save_delete/linked_candidate/finalize_candidate.py'
BASE_AUDIT_SHA = 'f492406e2d4c2d73d2b01b7f28ccb357f11578364b73670902429de70e329a03'
BASE_BUILD_ID = '20261016T110835Z_800f48fd88c0'
BASE_RUN_ID = '20261016T111333Z_1c377d9577e6'


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8')


def publish(path, value, previous=None):
    payload = json_bytes(value)
    if path.exists() and path.read_bytes() == payload:
        return
    require(artifact(path) == previous if previous is not None else not path.exists(),
            'Unexpected publication target content')
    temporary = path.with_name(path.name + '.overwrite-publish.tmp')
    if temporary.exists():
        require(temporary.read_bytes() == payload, 'Unknown publication temporary file')
    else:
        with temporary.open('xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    require(artifact(path) == previous if previous is not None else not path.exists(),
            'Publication target changed before atomic replacement')
    os.replace(temporary, path)
    require(path.read_bytes() == payload, 'Publication did not preserve the full JSON document')


def verify_source_and_baselines():
    scope = read(STAGE / 'scope.json')
    for row in scope['source19_seals']:
        require(artifact(Path(row['path'])) == row, 'Approved source drifted')
    for row in scope['unchanged_baseline_seals'].values():
        require(artifact(Path(row['path'])) == row, 'Unchanged baseline drifted')
    for row in scope['protected_artifacts'].values():
        require(artifact(Path(row['path'])) == row, 'Protected artifact drifted')
    require(artifact(Path(scope['common_helper']['path'])) == scope['common_helper'],
            'Preserved stage helper changed')
    require(artifact(Path(scope['progress_backup']['path'])) == scope['progress_backup'],
            'Preserved progress snapshot changed')
    require(artifact(BASE_AUDIT)['sha256'] == BASE_AUDIT_SHA, 'Preserved audit helper changed')
    return scope


def audit():
    output = STAGE / 'post_retirement_summary.json'
    require(not output.exists(), 'Do not replay the post-retirement audit')
    verify_source_and_baselines()
    spec = importlib.util.spec_from_file_location('_preserved_delete_audit', BASE_AUDIT)
    base = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(base)
    base.PROJECT, base.STAGE = PROJECT, STAGE
    base.BUILD_ID, base.BUILD_REPORT = BUILD_ID, BUILD_REPORT
    base.ATTESTATION, base.AUDIT = ATTESTATION, STAGE / 'post_retirement_audit.json'
    # Only the retained typed runtime audit is reused; its old finalizer is not.
    base.audit()
    previous_build = PROJECT / f'evidence/ui_window_host/{BASE_BUILD_ID}/build_result.json'
    previous_request = PROJECT / f'evidence/interactive_game/{BASE_RUN_ID}/request.json'
    previous_validation = base.check_host_runtime_artifacts(read(previous_build))
    base.check_artifacts(read(previous_request))
    verify_source_and_baselines()
    record = {
        'schema': 'zerosis.owned_save_overwrite.post_retirement_summary.v1',
        'status': 'PASS', 'utc': datetime.now(timezone.utc).isoformat(),
        'build_id': BUILD_ID, 'run_id': RUN_ID,
        'core_audit': artifact(base.AUDIT),
        'core_audit_schema_reused_without_relabelling': read(base.AUDIT)['schema'],
        'previous_build': artifact(previous_build), 'previous_request': artifact(previous_request),
        'previous_runtime_preflight': previous_validation,
        'source19_and_protected_artifacts_unchanged': True,
        'previous_runtime_artifacts_still_valid': True,
        'retail_mod_test_hold_active': True, 'host_gamecore_hwnd_executed': False,
        'retail_mods_saves_settings_or_processes_accessed': False,
    }
    write(output, record)
    print({'status': record['status'], 'summary': artifact(output)})


def finalize(storage_path):
    output = STAGE / 'conformance.json'
    pending_output = output.with_name(output.name + '.overwrite-publish.tmp')
    published = read(output) if output.exists() else (read(pending_output) if pending_output.exists() else None)
    scope = verify_source_and_baselines()
    prepared, identity = read(STAGE / 'prepared.json'), read(STAGE / 'preparation_identity_audit.json')
    attestation, build = read(ATTESTATION), read(BUILD_REPORT)
    summary = read(STAGE / 'post_retirement_summary.json')
    core_path = STAGE / 'post_retirement_audit.json'
    core = read(core_path)
    cleanup = read(STAGE / 'cleanup/result.json')
    require(summary['status'] == core['status'] == attestation['status'] == 'PASS' and cleanup['status'] == 'COMPLETE',
            'Candidate or retirement validation failed')
    require(summary['build_id'] == BUILD_ID and summary['run_id'] == core['run_id'] == RUN_ID and
            summary['core_audit'] == artifact(core_path) and core['build'] == artifact(BUILD_REPORT) and
            core['request'] == prepared['request'] == artifact(Path(prepared['request']['path'])) and
            core['attestation'] == artifact(ATTESTATION) and
            identity['prepared'] == artifact(STAGE / 'prepared.json') and identity['request'] == prepared['request'] and
            identity['host_build'] == prepared['host_build'] == artifact(BUILD_REPORT),
            'Current proof references are not linked to the same candidate')
    runtime = PROJECT / 'Build/InteractiveGameRuntime' / RUN_ID
    runtime_evidence = PROJECT / 'evidence/interactive_game' / RUN_ID
    require(not (runtime / 'sessions').exists() and not any((runtime_evidence / name).exists() for name in
            ('attempt.json', 'result.json', 'driver_result.json')), 'Unexpected current native execution output')
    require(prepared['run_id'] == identity['run_id'] == RUN_ID and
            prepared['host_build_id'] == identity['host_build_id'] == BUILD_ID,
            'Preparation belongs to a different candidate')
    require(prepared['status'] == 'PREPARED_NOT_EXECUTED' and identity['status'] == 'PASS_PREPARED_NOT_EXECUTED' and
            type(prepared['native_process_or_ctypes_calls']) is int and prepared['native_process_or_ctypes_calls'] == 0 and prepared['forbidden_access_attempts'] == [] and
            prepared['host_gamecore_or_windows_executed'] is False and identity['host_gamecore_hwnd_executed'] is False and
            type(identity['outer_process_or_ctypes_calls']) is int and identity['outer_process_or_ctypes_calls'] == 0 and identity['forbidden_access_attempts'] == [] and
            identity['retail_user_state_or_processes_accessed'] is False and identity['native_execution_outputs_absent'] is True,
            'Preparation isolation is unproven')
    require(build['build_id'] == BUILD_ID and build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
            build['source_hashes_before'] == build['source_hashes_after'] and
            build['source_inputs_unchanged'] is True and build['provider_inputs_unchanged'] is True and
            build['host_runtime_executed'] is False and build['gamecore_loaded'] is False, 'Build did not preserve its scope')
    for row in build['sources']:
        require(artifact(Path(row['original_source']))['sha256'] == row['sha256'],
                'A current named build input drifted, including the generated UI header')
    require(artifact(Path(build['ui_assets']['original_path']))['sha256'] == build['ui_assets']['sha256'],
            'Current UI asset catalog drifted')
    for row in identity['current_frozen_manifest_support'].values():
        require(artifact(Path(row['current']['path'])) == row['current'] and
                artifact(Path(row['frozen']['path'])) == row['frozen'] and
                row['current']['sha256'] == row['frozen']['sha256'] == row['manifest_sha256'],
                'Current or frozen Python support drifted')
    require(attestation['build_report']['sha256'] == artifact(BUILD_REPORT)['sha256'] and
            attestation['executable']['sha256'] == artifact(Path(build['executable']['path']))['sha256'],
            'Attestation belongs to a different linked image')
    after, before = read(storage_path), read(Path(scope['storage_before']['path']))
    require(after['status'] == 'COMPLETE_METADATA_AUDIT' and not after['errors'] and not after['skipped'] and
            after['root'] == before['root'] == str(PROJECT), 'Storage audit is incomplete or outside this project')
    proof_paths = {
        'scope': STAGE / 'scope.json', 'source_conformance': Path(scope['prior_source_conformance']['path']),
        'build': BUILD_REPORT, 'build_invocation': STAGE / 'build_invocation.json', 'pe_attestation': ATTESTATION,
        'prepare_invocation': STAGE / 'prepare_invocation.json', 'prepared': STAGE / 'prepared.json',
        'preparation_identity': STAGE / 'preparation_identity_audit.json',
        'post_retirement_audit': STAGE / 'post_retirement_audit.json',
        'post_retirement_summary': STAGE / 'post_retirement_summary.json',
        'cleanup_plan': STAGE / 'cleanup/plan.json.gz', 'cleanup_result': STAGE / 'cleanup/result.json',
        'retirement_preflight': STAGE / 'retirement_preflight.json', 'storage_after': storage_path,
    }
    proofs = {key: artifact(path) for key, path in proof_paths.items()}
    storage = {
        'before_unique_GetCompressedFileSizeW_bytes': before['unique_allocated_bytes'],
        'after_unique_GetCompressedFileSizeW_bytes': after['unique_allocated_bytes'],
        'net_unique_change_bytes': after['unique_allocated_bytes'] - before['unique_allocated_bytes'],
        'after_GiB': after['unique_allocated_bytes'] / 1024**3,
        'cleanup_result': proofs['cleanup_result'], 'full_project_copies_created': 0,
        'limits': 'Unique NTFS identities, not measured volume free space. Final conformance and progress publication follow this audit.',
    }
    verification = {
        'compile_link': build['status'], 'actual_architecture': build['executable']['pe'],
        'actual_pe_catalog_entries': attestation['pe_catalog']['entry_count'],
        'actual_pe_payloads_matched': len(attestation['pe_catalog']['exact_payloads']),
        'attestation_rehashed_input_count': attestation['read_input_count'],
        'current_cpp_generated_header_lua_and_input_embedded': True,
        'current_frozen_python_support_files': prepared['current_python_support_count'],
        'private_runtime_inputs': prepared['runtime_inputs'], 'immutable_cache_links': prepared['hardlinks'],
        'private_database_count': len(identity['private_databases']),
        'native_process_or_ctypes_calls_during_preparation': 0,
        'host_gamecore_hwnd_executed': False, 'native_overwrite_acceptance': False,
        'original_game_save_mod_compatibility_verified': False,
        'retail_mod_test_hold_active': True, 'default_promoted': False, 'full_engine_goal_complete': False,
    }
    remaining = [
        'After explicit human mod-test end, verify the actual x64 Host/Lua/SDK window, original menu lifecycle and physical Korean IME.',
        f'Use Host {BUILD_ID} and private runtime {RUN_ID} for actual named save, overwrite confirmation/cancel/recovery, delete/refresh, close and fresh SDK restore.',
        'Complete original UI/3D/campaign, original Civ5Save and active-mod compatibility, multicore performance and long-run stability.',
    ]
    record = {
        'schema': 'zerosis.owned_save_overwrite.linked_candidate_conformance.v1',
        'status': 'PASS_CURRENT_X64_LINK_PE_PAYLOAD_AND_PRIVATE_PREPARATION_ONLY',
        'utc': published['utc'] if published is not None else datetime.now(timezone.utc).isoformat(), 'build_id': BUILD_ID, 'run_id': RUN_ID,
        'proofs': proofs, 'verification': verification, 'storage': storage, 'remaining_gates': remaining,
        'native_result_created': False, 'default_and_recovery_artifacts_unchanged': True,
        'retail_mods_user_saves_settings_or_processes_accessed': False,
        'limits': [
            'Compiled linked image bytes and guarded private preparation do not prove actual runtime overwrite or gameplay.',
            'Prior source/component receipts keep their original scope; old syntax proof used the preserved previous generated header.',
            'Retired old build/runtime pathnames remain only as historical records and do not describe complete current build closures.',
            'EA0.6 remains the default; B6/R6 and B3/R3 recovery inputs remain protected.',
        ],
    }
    require(published is None or published == record, 'A different final result was already published')
    import hashlib
    conformance = {'path': str(output), 'bytes': len(json_bytes(record)),
                   'sha256': hashlib.sha256(json_bytes(record)).hexdigest()}
    progress = read(Path(scope['progress_backup']['path']))
    progress.update(
        utc=record['utc'], status='CURRENT_OVERWRITE_UI_X64_CANDIDATE_PREPARED_NATIVE_ACCEPTANCE_PENDING',
        full_goal_redefined=False, full_engine_goal_complete=False,
        prior_goal_turn_classification='progress: current overwrite UI compiled and linked once, all actual PE payloads attested, matching isolated runtime prepared, superseded owned artifacts retired and retained inputs revalidated',
        current_host_build_id=BUILD_ID, latest_source_matches_linked_candidate=True,
        latest_source_matches_integrated_syntax_proof=False, latest_cpp_source_matches_actual_host_syntax_proof=False,
        latest_current_source_compile_link_proof=proofs['build'], latest_current_source_pe_attestation=proofs['pe_attestation'],
        prepared_runtime_matches_current_linked_candidate=True, prepared_runtime_matches_latest_source=True,
        latest_storage_audit=proofs['storage_after'],
        latest_full_source_embedding_limit='Current C++/generated UI header/Lua/presentation input match B7 actual PE, and five current frozen support files match R7. Actual Host/SDK/window/save overwrite acceptance is still unexecuted; EA0.6 default is unchanged.',
    )
    progress['current_prepared_runtime'] = {
        'run_id': RUN_ID, 'host_build_id': BUILD_ID, 'status': 'PREPARED_NOT_EXECUTED',
        'request': prepared['request'], 'prepared': proofs['prepared'],
        'runtime_identity_audit': proofs['post_retirement_audit'],
        'runtime_retirement_summary': proofs['post_retirement_summary'],
        'shared_input_hardlinks': prepared['hardlinks'], 'existing_cache_hits': prepared['cache_hits'],
        'new_host_cache_objects': prepared['new_cache_objects'], 'current_source_candidate': True,
        'process_or_ctypes_library_calls': 0, 'retail_mods_saves_settings_or_processes_accessed_this_stage': False,
        'gamecore_or_windows_executed': False, 'native_result_created': False, 'default_promoted': False,
        'native_runtime_acceptance': False, 'private_policy_info_settings': artifact(STAGE / 'PolicyInfo.ini'),
    }
    progress['owned_save_overwrite_linked_candidate_stage'] = {
        'conformance': conformance, 'verification': verification, 'remaining_gates': remaining,
    }
    progress['next_native_gates'] = remaining
    progress['proofs']['owned_save_overwrite_linked_conformance'] = conformance
    progress['proofs']['owned_save_overwrite_linked_storage_after'] = proofs['storage_after']
    progress['storage'].update(latest_measured_unique_GetCompressedFileSizeW_bytes=after['unique_allocated_bytes'],
                               latest_measured_utc=after['utc'], owned_save_overwrite_linked_stage=storage)
    progress['user_mod_test_isolation'].update(
        retail_test_hold_still_active=True, native_window_tests_held=True,
        retail_MODS_user_saves_or_game_processes_accessed_this_stage=False,
        game_Host_GameCore_HWND_or_component_windows_executed_this_stage=False,
        retail_settings_accessed_this_stage=False, original_user_settings_read_this_stage=False,
        current_stage_policy_source='EXPLICIT_PRIVATE_POLICY_INFO_INI',
    )
    require(artifact(PROGRESS) == scope['progress_before'] or PROGRESS.read_bytes() == json_bytes(progress),
            'Progress changed before publication')
    publish(output, record)
    publish(PROGRESS, progress, scope['progress_before'])
    print({'status': record['status'], 'conformance': conformance, 'progress': artifact(PROGRESS), 'storage': storage})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('audit', 'finalize'))
    parser.add_argument('--storage', type=Path)
    args = parser.parse_args()
    if args.action == 'audit':
        audit()
    else:
        require(args.storage is not None and args.storage.is_absolute(), 'Exact absolute storage report required')
        finalize(args.storage)
