"""Publish source and headless camera evidence while retaining native gates."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def seal(path):
    path = Path(path)
    with path.open('rb') as stream:
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha}


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8')


def publish(path, value, previous=None):
    data = encoded(value)
    if path.exists() and path.read_bytes() == data:
        return
    require(seal(path) == previous if previous is not None else not path.exists(), 'Publication target differs')
    temporary = path.with_name(path.name + '.camera-publish.tmp')
    if temporary.exists():
        require(temporary.read_bytes() == data, 'Unknown publication temporary file')
    else:
        with temporary.open('xb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    require(seal(path) == previous if previous is not None else not path.exists(), 'Publication target changed')
    os.replace(temporary, path)


def main(storage_path):
    output = STAGE / 'conformance.json'
    pending = output.with_name(output.name + '.camera-publish.tmp')
    prior = read(output) if output.exists() else (read(pending) if pending.exists() else None)
    scope, invocation = read(STAGE / 'scope.json'), read(STAGE / 'component_invocation.json')
    component_path = Path(invocation['result']['path'])
    component, syntax = read(component_path), read(STAGE / 'syntax/result.json')
    cleanup = read(STAGE / 'cleanup.json')
    require(invocation['exit_code'] == 0 and seal(component_path) == invocation['result'] and
            component['status'] == 'PASS_HEADLESS_PRODUCTION_WORLD_CAMERA_CONTROLS' and
            component['scope'] == seal(STAGE / 'scope.json'), 'Headless controls proof failed')
    require(syntax['status'] == 'PASS' and len(syntax['translation_units']) == 3 and
            syntax['project_inputs_before'] == syntax['project_inputs_after'] and syntax['linked'] is False and
            syntax['host_gamecore_hwnd_executed'] is False and syntax['generated_code_artifacts'] == [],
            'Actual consumer syntax proof failed')
    require(all(row['exit_code'] == 0 and row['warnings'] == [] and row['camera_header_consumed'] is True
                for row in syntax['translation_units']), 'A consumer failed or omitted current controls')
    require(component['compiler'] == syntax['compiler'] and all('/std:c++14' in
            Path(row['response']['path']).read_text(encoding='utf8').splitlines() for row in component['variants']),
            'Headless controls and current consumers used different compiler profiles')
    for row in syntax['project_inputs_after'].values():
        require(seal(Path(row['path'])) == row, 'Syntax input changed')
    for row in component['inputs']:
        require(seal(Path(row['path'])) == row, 'Component input changed')
    require(len(component['variants']) == 2 and {row['optimization'] for row in component['variants']} == {'/O2', '/Od'} and
            all(row['checks'] == 3139 and row['cases'] == 51 and row['exit_code'] == 0 and
                row['compiler_and_linker_warnings'] == 0 for row in component['variants']), 'Component coverage differs')
    require(all(component[name] is False for name in ('gamecore_loaded', 'host_executed', 'hwnd_created', 'gpu_used',
            'retail_user_state_accessed', 'game_process_queried', 'full_host_compiled', 'native_acceptance_verified')),
            'Component proof exceeded its isolation scope')
    for row in component['variants']:
        require(seal(Path(row['executable']['path']))['sha256'] == row['executable']['sha256'], 'Component executable changed')
    for row in scope['protected'].values():
        require(seal(Path(row['path'])) == row, 'Protected current/default artifact changed')
    for row in scope['source_before']:
        require(seal(Path(row['backup']['path'])) == row['backup'], 'Changed-file backup changed')
    require(seal(Path(scope['original_world_view']['path'])) == scope['original_world_view'], 'Original UI source changed')
    require(cleanup['status'] == 'COMPLETE' and cleanup['removed_files'] == 4 and cleanup['protected_unchanged'] is True and
            all(not os.path.lexists(row['path']) for row in cleanup['removed']), 'Intermediate cleanup failed')
    after, before = read(storage_path), read(Path(scope['storage_before']['path']))
    require(after['status'] == 'COMPLETE_METADATA_AUDIT' and not after['errors'] and not after['skipped'] and
            before['root'] == after['root'] == str(PROJECT), 'Storage audit incomplete')
    proofs = {key: seal(path) for key, path in {
        'scope': STAGE / 'scope.json', 'component': component_path,
        'component_invocation': STAGE / 'component_invocation.json', 'actual_consumer_syntax': STAGE / 'syntax/result.json',
        'cleanup_plan': STAGE / 'cleanup_plan.json', 'cleanup': STAGE / 'cleanup.json', 'storage_after': storage_path,
    }.items()}
    storage = {'before_unique_GetCompressedFileSizeW_bytes': before['unique_allocated_bytes'],
               'after_unique_GetCompressedFileSizeW_bytes': after['unique_allocated_bytes'],
               'net_unique_change_bytes': after['unique_allocated_bytes'] - before['unique_allocated_bytes'],
               'after_GiB': after['unique_allocated_bytes'] / 1024**3,
               'removed_generated_files': cleanup['removed_files'], 'removed_logical_bytes': cleanup['removed_logical_bytes'],
               'removed_unique_GetCompressedFileSizeW_bytes': cleanup['removed_unique_GetCompressedFileSizeW_bytes'],
               'full_project_copies_created': 0,
               'limits': 'Unique named-file allocation, not volume free space. Final conformance and progress bytes follow the audit.'}
    remaining = [
        'Compile/link one current Host and attest the current compiler closure before native camera acceptance; unchanged B7/R7 contain the prior overwrite code.',
        'After explicit human retail-mod test end, verify physical PageUp/+ and PageDown/- keys, modal/stale/close routing, menu round trip and same-frame GPU picking on wrap and nonwrap maps.',
        'Complete actual save/overwrite/delete/close/fresh-SDK restore acceptance, original UI/3D/campaign, original Civ5Save/active-mod compatibility and measured useful multicore performance.',
    ]
    record = {'schema': 'zerosis.world_camera.controls_conformance.v1',
              'status': 'PASS_SOURCE_AND_HEADLESS_CONTROLS_ONLY',
              'utc': prior['utc'] if prior is not None else datetime.now(timezone.utc).isoformat(),
              'requirements': scope['requirements'], 'current_inputs': component['inputs'], 'proofs': proofs,
              'verification': {'headless_variants': [{'optimization': row['optimization'], 'checks': row['checks'], 'cases': row['cases']}
                                                    for row in component['variants']],
                               'actual_syntax_translation_units': 3, 'current_project_inputs': len(syntax['project_inputs_after']),
                               'source_connections': component['source_connections'], 'host_linked': False,
                               'native_camera_acceptance': False, 'retail_mod_test_hold_active': True,
                               'default_promoted': False, 'full_engine_goal_complete': False},
              'independent_review': {'agent': '/root/delete_storage_review', 'scope': 'READ_ONLY_SOURCE_AND_RUNNER_REVIEW',
                                     'production_and_fixture_runner_findings': 0, 'native_execution_by_reviewer': False},
              'storage': storage, 'protected_artifacts_unchanged': True, 'remaining_gates': remaining,
              'limits': ['Candidate scale24..112/default56/step8 and pan step3 are not original camera calibration.',
                         'Wheel input is unchanged. No current Host/GameCore/window/GPU or physical-key execution occurred.',
                         'The component object paths are historical build artifacts intentionally retired by the linked cleanup.']}
    require(prior is None or prior == record, 'A different result was already published')
    conformance = {'path': str(output), 'bytes': len(encoded(record)), 'sha256': hashlib.sha256(encoded(record)).hexdigest()}
    progress_before = seal(PROGRESS)
    progress = read(PROGRESS)
    require(progress['world_camera_controls_stage']['scope'] == proofs['scope'] and
            progress['full_engine_goal_complete'] is False, 'Current progress has a different scope')
    progress.update(utc=record['utc'], status='WORLD_CAMERA_CONTROLS_SOURCE_COMPONENTS_PASS_LINK_AND_NATIVE_PENDING',
                    prior_goal_turn_classification='progress: added real camera zoom key and wrapped-pan production paths, compiled three current consumers, executed isolated O2/Od controls and retired four intermediates',
                    latest_source_matches_linked_candidate=False, prepared_runtime_matches_latest_source=False,
                    latest_cpp_source_matches_actual_host_syntax_proof=True, latest_integrated_syntax_proof=proofs['actual_consumer_syntax'],
                    latest_storage_audit=proofs['storage_after'], full_goal_redefined=False, full_engine_goal_complete=False,
                    latest_full_source_embedding_limit='Current camera C++ passes actual Host/renderer syntax and pure controls execution. B7/R7 remain unchanged prior overwrite candidates; a current link and actual key/GPU/gameplay acceptance are pending.')
    if progress.get('latest_current_source_compile_link_proof') is not None:
        progress['last_linked_candidate_compile_link_proof'] = progress['latest_current_source_compile_link_proof']
    if progress.get('latest_current_source_pe_attestation') is not None:
        progress['last_linked_candidate_pe_attestation'] = progress['latest_current_source_pe_attestation']
    progress['latest_current_source_compile_link_proof'] = None
    progress['latest_current_source_pe_attestation'] = None
    progress['current_prepared_runtime']['current_source_candidate'] = False
    progress['world_camera_controls_stage'] = {'scope': proofs['scope'], 'conformance': conformance,
                                               'status': record['status'], 'native_acceptance': False, 'default_promoted': False}
    progress['proofs']['world_camera_controls_conformance'] = conformance
    progress['next_native_gates'] = remaining
    progress['storage'].update(latest_measured_unique_GetCompressedFileSizeW_bytes=after['unique_allocated_bytes'],
                               latest_measured_utc=after['utc'], world_camera_controls_stage=storage)
    progress['user_mod_test_isolation'].update(retail_test_hold_still_active=True, native_window_tests_held=True,
        retail_MODS_user_saves_or_game_processes_accessed_this_stage=False,
        game_Host_GameCore_HWND_or_component_windows_executed_this_stage=False,
        retail_settings_accessed_this_stage=False, original_user_settings_read_this_stage=False)
    publish(output, record)
    publish(PROGRESS, progress, progress_before)
    print(json.dumps({'status': record['status'], 'conformance': seal(output), 'progress': seal(PROGRESS), 'storage': storage}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--storage', type=Path, required=True)
    args = parser.parse_args()
    require(args.storage.is_absolute(), 'Exact storage report path required')
    main(args.storage)
