"""Publish current link/preparation receipts; never launch the candidate."""
from __future__ import annotations

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch


STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
BUILD_ID = '20261016T142908Z_fc2e23c1fd1e'
RUN_ID = '20261016T143731Z_bc358fc8d62a'
BUILD_SHA = 'f1353330edad0c93ed6e8ee42af996f87b052b6920404df3b8411b5ec4895d63'
PE_SHA = '978ecb48269d4bcf3959895285f06f2ee75a3ab8d1bdb6b00d819d124b554452'
OWNER_SHA = '2d7ffaa1e42ace8d66d02d1a16b6c291008a7d7513d53d58407d3733ab0a1ad5'
PREPARER_SHA = '9077f6583dbffddfd984d6678857fb97abcc6ea1096ce83708516703daec78c4'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf-8')


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'Cannot load the reviewed local helper')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        while data := stream.read(1024 * 1024):
            digest.update(data)
    return digest.hexdigest()


def publish(path, value, previous=None):
    temporary = path.with_name(path.name + '.world-link-publish.tmp')
    payload = encoded(value)
    if path.exists() and path.read_bytes() == payload:
        if os.path.lexists(temporary):
            require(temporary.read_bytes() == payload, 'Unknown publication temporary content')
            temporary.unlink()
        return
    require(not path.exists() if previous is None else sha(path) == previous['sha256'],
            'Publication target changed or already exists')
    if os.path.lexists(temporary):
        require(temporary.read_bytes() == payload, 'Unknown publication temporary content')
    else:
        with temporary.open('xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    require(not path.exists() if previous is None else sha(path) == previous['sha256'],
            'Publication target changed before replacement')
    os.replace(temporary, path)
    require(path.read_bytes() == payload, 'Publication bytes differ')


def verify_publication_scope(owner, scope, expected_progress):
    """Treat only an already byte-identical published progress row as historical."""
    artifact = owner.sealed_artifact
    target = Path(scope['progress_before']['path'])
    current = artifact(target)
    if current == scope['progress_before']:
        return owner.verify_scope()
    require(target.read_bytes() == encoded(expected_progress), 'Unexpected current progress content')
    backup = scope['progress_backup']
    require(artifact(Path(backup['path'])) == backup and
            backup['sha256'] == scope['progress_before']['sha256'] and
            backup['bytes'] == scope['progress_before']['bytes'], 'Historical progress backup differs')
    def historical_progress_only(path):
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(str(target)):
            require(artifact(target) == current and target.read_bytes() == encoded(expected_progress),
                    'Published progress changed during validation')
            return scope['progress_before']
        return artifact(path)
    with patch.object(owner, 'sealed_artifact', side_effect=historical_progress_only):
        return owner.verify_scope()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage-after', required=True, type=Path)
    args = parser.parse_args()
    require(sha(STAGE / 'run_stage.py') == OWNER_SHA and sha(STAGE / 'prepare_candidate.py') == PREPARER_SHA,
            'Preserved preparation or build wrapper changed')
    helper = load(STAGE / 'prepare_candidate.py', '_world_finalize_preparation_helpers')
    denied = []
    helper.install_outer_guard(denied)
    with ExitStack() as stack:
        guards = [stack.enter_context(patch(name, side_effect=RuntimeError('Execution forbidden: ' + name)))
                  for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL')]
        owner = load(STAGE / 'run_stage.py', '_world_finalize_build_owner')
        artifact, read = owner.sealed_artifact, owner.read
        require(artifact(owner.SCOPE)['sha256'] == owner.SCOPE_SHA256, 'Reviewed scope changed')
        scope = read(owner.SCOPE)
        output = STAGE / 'conformance.json'
        pending_output = output.with_name(output.name + '.world-link-publish.tmp')
        published = read(output) if output.exists() else (read(pending_output) if pending_output.exists() else None)
        if artifact(Path(scope['progress_before']['path'])) == scope['progress_before']:
            owner.verify_scope()
        else:
            require(published is not None, 'Progress changed without a recoverable publication receipt')
        build_path = PROJECT / f'evidence/ui_window_host/{BUILD_ID}/build_result.json'
        pe_path = STAGE / f'attestation_{BUILD_ID}.json'
        require(artifact(build_path)['sha256'] == BUILD_SHA and artifact(pe_path)['sha256'] == PE_SHA,
                'Current build or PE attestation changed')
        build, attestation = read(build_path), read(pe_path)
        prepared = read(STAGE / 'prepared.json')
        identity = read(STAGE / 'preparation_identity_audit.json')
        completion = read(STAGE / 'preparation_completion.json')
        cleanup = read(STAGE / 'cleanup/result.json')
        post = read(STAGE / 'post_retirement_preflight.json')
        require(build['build_id'] == BUILD_ID and build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
                build['source_inputs_unchanged'] is True and build['provider_inputs_unchanged'] is True and
                build['error'] is None and build['host_runtime_executed'] is False and build['gamecore_loaded'] is False,
                'Actual compile/link boundary differs')
        require(attestation['status'] == 'PASS' and attestation['build_id'] == BUILD_ID and
                attestation['inputs_unchanged'] is True and attestation['exact_final_dependency_closure'] is True and
                attestation['actual_pe_inspected'] is True and attestation['host_executed'] is False and
                attestation['hwnd_created'] is False and attestation['game_process_queries'] == 0 and
                attestation['build_report'] == artifact(build_path), 'PE receipt is outside the static boundary')
        require(all(attestation[name] is False for name in ('host_executed', 'gamecore_loaded', 'dll_loaded',
                'hwnd_created', 'mods_or_user_saves_accessed', 'retail_user_settings_accessed', 'default_promoted',
                'native_camera_controls_verified', 'native_civilian_rendering_verified',
                'native_binding_execution_verified', 'native_overwrite_verified', 'retail_save_mod_compatibility_verified',
                'unit_package_embedded_in_pe', 'native_unit_package_consumption_verified')) and
                type(attestation['game_process_queries']) is int and attestation['game_process_queries'] == 0,
                'Attestation exceeds file/byte inspection')
        require(prepared['run_id'] == identity['run_id'] == RUN_ID and
                prepared['host_build_id'] == identity['host_build_id'] == BUILD_ID and
                prepared['status'] == 'PREPARED_NOT_EXECUTED' and
                identity['status'] == 'PASS_PREPARED_NOT_EXECUTED' and
                identity['prepared'] == artifact(STAGE / 'prepared.json') and
                identity['request'] == prepared['request'] and
                identity['host_build'] == prepared['host_build'] == artifact(build_path),
                'Private preparation receipts name different candidates')
        require(prepared['runtime_inputs'] == 24 and prepared['hardlinks'] == 15 and
                len(identity['private_databases']) == 2 and len(identity['current_frozen_manifest_support']) == 5 and
                type(prepared['native_process_or_ctypes_calls']) is int and
                prepared['native_process_or_ctypes_calls'] == 0 and prepared['forbidden_access_attempts'] == [] and
                type(identity['outer_process_or_ctypes_calls']) is int and
                identity['outer_process_or_ctypes_calls'] == 0 and identity['forbidden_access_attempts'] == [] and
                prepared['host_gamecore_hwnd_executed'] is False and
                identity['host_gamecore_hwnd_executed'] is False and
                identity['retail_user_state_or_processes_accessed'] is False and
                prepared['default_release_promoted'] is False,
                'Private preparation isolation/counts differ')
        require(all(prepared[name] is False for name in ('host_gamecore_hwnd_executed',
                'retail_user_state_or_processes_accessed', 'default_release_promoted', 'native_camera_or_civilian_acceptance')) and
                all(identity[name] is False for name in ('host_gamecore_hwnd_executed',
                'retail_user_state_or_processes_accessed', 'default_release_promoted', 'native_camera_controls_verified',
                'native_civilian_rendering_verified', 'native_overwrite_verified', 'retail_save_mod_compatibility_verified')),
                'Preparation receipts imply unexecuted native acceptance')
        require(completion['schema'] == 'zerosis.world_camera_civilian.static_preparation_completion.v1' and
                completion['status'] == 'PASS_STATIC_COMPLETION_OF_EXISTING_PRIVATE_PREPARATION' and
                completion['run_id'] == RUN_ID and completion['host_build_id'] == BUILD_ID and
                completion['prepared'] == artifact(STAGE / 'prepared.json') and
                completion['identity_audit'] == artifact(STAGE / 'preparation_identity_audit.json') and
                completion['request'] == prepared['request'] and
                completion['host_build'] == artifact(build_path) and completion['pe_attestation'] == artifact(pe_path) and
                type(completion['runner_main_calls']) is int and completion['runner_main_calls'] == 0 and
                type(completion['materializer_calls']) is int and completion['materializer_calls'] == 0 and
                completion['new_runtime_created_by_completion'] is False,
                'Completion receipt is not a successful static validation of the same existing candidate')
        require(completion['forbidden_access_attempts'] == [] and
                all(type(count) is int and count == 0 for count in completion['guard_call_counts']) and
                completion['original_failure_and_success_logs_unchanged'] is True and
                completion['authoritative_original_inventory_preserved'] is True and
                all(completion[name] is False for name in ('host_gamecore_hwnd_executed',
                'retail_user_state_or_processes_accessed', 'default_release_promoted', 'native_camera_or_civilian_acceptance')),
                'Static completion boundary differs')
        for ref in (completion['checker'], completion['static_completion']['started']):
            require(artifact(Path(ref['path'])) == ref, 'Static completion checker/start receipt changed')
        require(cleanup['status'] == 'COMPLETE' and post['status'] == 'PASS' and
                BUILD_ID in post['current'] and post['current'][BUILD_ID]['runtime_id'] == RUN_ID and
                post['blocked_old_path_attempts'] == [] and post['target_directory_created'] is False,
                'Cleanup or retained-runtime/frozen-donor validation failed')
        runtime = PROJECT / 'Build/InteractiveGameRuntime' / RUN_ID
        evidence = PROJECT / 'evidence/interactive_game' / RUN_ID
        require(not (runtime / 'sessions').exists() and not any((evidence / name).exists()
                for name in ('attempt.json', 'result.json', 'driver_result.json')),
                'Unexpected native execution output')
        require(artifact(Path(prepared['request']['path'])) == prepared['request'], 'Prepared request changed')
        for row in build['sources']:
            require(artifact(Path(row['original_source']))['sha256'] == row['sha256'], 'Current build source drifted')
        for row in identity['current_frozen_manifest_support'].values():
            require(artifact(Path(row['current']['path'])) == row['current'] and
                    artifact(Path(row['frozen']['path'])) == row['frozen'], 'Frozen frontend support drifted')
        before_path = Path(scope['storage_before']['path'])
        before, after = read(before_path), read(args.storage_after)
        require(args.storage_after.is_relative_to(PROJECT / 'evidence/storage') and
                all(doc['status'] == 'COMPLETE_METADATA_AUDIT' and not doc['errors'] and not doc['skipped'] and
                    doc['root'] == str(PROJECT) for doc in (before, after)), 'Storage audit is incomplete')
        names = {'scope': STAGE / 'scope.json', 'build': build_path, 'pe_attestation': pe_path,
                 'prepare_failure': STAGE / 'prepare_invocation.json', 'prepared': STAGE / 'prepared.json',
                 'preparation_identity': STAGE / 'preparation_identity_audit.json',
                 'preparation_completion': STAGE / 'preparation_completion.json',
                 'cleanup_plan': STAGE / 'cleanup/plan.json.gz', 'cleanup_result': STAGE / 'cleanup/result.json',
                 'retained_preflight': STAGE / 'post_retirement_preflight.json', 'storage_after': args.storage_after,
                 'publication_helper': Path(__file__).absolute()}
        proofs = {name: artifact(path) for name, path in names.items()}
        now = published['utc'] if published is not None else datetime.now(timezone.utc).isoformat()
        storage = {'before_unique_GetCompressedFileSizeW_bytes': before['unique_allocated_bytes'],
                   'after_unique_GetCompressedFileSizeW_bytes': after['unique_allocated_bytes'],
                   'net_unique_change_bytes': after['unique_allocated_bytes'] - before['unique_allocated_bytes'],
                   'after_GiB': after['unique_allocated_bytes'] / 1024**3,
                   'cleanup_result': proofs['cleanup_result'], 'full_project_copies_created': 0,
                   'limits': 'Unique NTFS identities; excludes directory/MFT overhead, volume free space and subsequent report publication.'}
        verification = {'actual_compile_link': build['status'], 'actual_pe_payloads_matched': 62,
                        'current_cpp_feature_inputs': 6, 'private_runtime_inputs': prepared['runtime_inputs'],
                        'immutable_cache_links': prepared['hardlinks'], 'private_databases': 2,
                        'current_frontend_files': 5, 'external_unit_package': scope['current_unit_assets']['binary'],
                        'source_matches_current_linked_and_prepared_candidate': True,
                        'host_gamecore_hwnd_executed': False, 'native_camera_controls_verified': False,
                        'native_civilian_rendering_verified': False, 'native_unit_package_consumption_verified': False,
                        'civilian_animation_playback_verified': False, 'retail_mod_test_hold_active': True,
                        'default_promoted': False, 'full_engine_goal_complete': False}
        remaining = [
            'After explicit human mod-test end, inspect the actual current x64 Host/SDK/Lua window, camera pan/zoom, unit selection and original menus.',
            'Verify the real settler/worker appearance, scale, orientation, materials and movement; civilian animation is not implemented by the static IdleA package.',
            'Verify named save/load/overwrite/delete, new game, turns, original UI/3D/full campaign, original Civ5Save and active-mod compatibility.',
            'Connect useful deterministic multicore work and measure performance and long-run stability in the real runtime.']
        record = {'schema': 'zerosis.world_camera_civilian.linked_candidate_conformance.v1',
                  'status': 'PASS_CURRENT_X64_LINK_PE_AND_PRIVATE_PREPARATION_ONLY', 'utc': now,
                  'build_id': BUILD_ID, 'run_id': RUN_ID, 'proofs': proofs, 'verification': verification,
                  'storage': storage, 'remaining_gates': remaining,
                  'retail_mods_user_saves_settings_or_processes_accessed': False,
                  'native_result_created': False, 'default_and_recovery_artifacts_unchanged': True,
                  'limits': ['The preparation wrapper failed after materialization because path/original_path keys differ; its failure is preserved and a separate read-only completion validated the existing run.',
                             'Actual compiled bytes, a raw PE receipt and private file preparation do not establish playable runtime acceptance.',
                             'Old retired build/runtime reports are historical receipts, not replayable complete closures.']}
        require(published is None or published == record, 'A different conformance receipt already exists')
        conformance = {'path': str(output), 'bytes': len(encoded(record)), 'sha256': hashlib.sha256(encoded(record)).hexdigest()}
        progress_path = Path(scope['progress_before']['path'])
        progress = read(Path(scope['progress_backup']['path']))
        progress.update(utc=now, status='CURRENT_CAMERA_CIVILIAN_X64_CANDIDATE_PREPARED_NATIVE_ACCEPTANCE_PENDING',
                        full_goal_redefined=False, full_engine_goal_complete=False,
                        prior_goal_turn_classification='progress: compiled and linked current camera/civilian consumers, attested actual PE, validated matching existing private runtime, retired superseded owned artifacts',
                        current_host_build_id=BUILD_ID, latest_source_matches_linked_candidate=True,
                        latest_current_source_compile_link_proof=proofs['build'],
                        latest_current_source_pe_attestation=proofs['pe_attestation'],
                        prepared_runtime_matches_current_linked_candidate=True, prepared_runtime_matches_latest_source=True,
                        latest_storage_audit=proofs['storage_after'],
                        latest_full_source_embedding_limit='Current camera/civilian selector C++, original UI payloads and current frontend support match B8/R8; the three-art package is external. Native screen/gameplay acceptance remains unexecuted and EA0.6 remains the default.')
        progress['current_prepared_runtime'] = {
            'run_id': RUN_ID, 'host_build_id': BUILD_ID, 'status': 'PREPARED_NOT_EXECUTED',
            'request': prepared['request'], 'prepared': proofs['prepared'],
            'runtime_identity_audit': proofs['preparation_identity'], 'runtime_retirement_summary': proofs['retained_preflight'],
            'shared_input_hardlinks': prepared['hardlinks'], 'existing_cache_hits': prepared['cache_hits'],
            'new_host_and_unit_cache_objects': prepared['new_cache_objects'], 'current_source_candidate': True,
            'process_or_ctypes_library_calls': 0, 'retail_mods_saves_settings_or_processes_accessed_this_stage': False,
            'gamecore_or_windows_executed': False, 'native_result_created': False, 'default_promoted': False,
            'native_runtime_acceptance': False, 'private_policy_info_settings': artifact(STAGE / 'PolicyInfo.ini')}
        progress['world_camera_civilian_linked_candidate_stage'] = {'conformance': conformance,
            'verification': verification, 'remaining_gates': remaining}
        progress['proofs']['world_camera_civilian_linked_conformance'] = conformance
        progress['proofs']['world_camera_civilian_linked_storage_after'] = proofs['storage_after']
        progress['next_native_gates'] = remaining
        progress['storage'].update(latest_measured_unique_GetCompressedFileSizeW_bytes=after['unique_allocated_bytes'],
                                   latest_measured_utc=after['utc'], world_camera_civilian_linked_stage=storage)
        progress['user_mod_test_isolation'].update(retail_test_hold_still_active=True, native_window_tests_held=True,
            retail_MODS_user_saves_or_game_processes_accessed_this_stage=False,
            game_Host_GameCore_HWND_or_component_windows_executed_this_stage=False,
            retail_settings_accessed_this_stage=False, original_user_settings_read_this_stage=False,
            current_stage_policy_source='EXPLICIT_PRIVATE_POLICY_INFO_INI')
        require(not denied and all(guard.call_count == 0 for guard in guards), 'Forbidden publication operation')
        verify_publication_scope(owner, scope, progress)
        publish(output, record)
        publish(progress_path, progress, scope['progress_before'])
        print(json.dumps({'status': record['status'], 'conformance': conformance,
                          'progress': artifact(progress_path), 'storage': storage}))


if __name__ == '__main__':
    main()
