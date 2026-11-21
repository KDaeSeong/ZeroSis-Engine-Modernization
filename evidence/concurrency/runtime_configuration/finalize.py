"""Verify the current bounded evidence and publish engine-only progress atomically."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
PROGRESS = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
BUILD = '20261016T142908Z_fc2e23c1fd1e'
RUN = '20261017T005450Z_9e280ca26b49'
RUNTIME = PROJECT / 'Build/InteractiveGameRuntime' / RUN
EVIDENCE = PROJECT / 'evidence/interactive_game' / RUN
PINS = {
    'scope': ('scope.json', '3442c84392c969f37df3d6d6a00576a0df0df96d365586db73edf99158d45bc5'),
    'tests': ('test_result.json', '29543dc0570fbb5e7f69a79275016469cc9f18fac395dbbeef674dc0717eb2e8'),
    'prepared': ('prepared.json', '9409ca2984b12587686c2e97916cc1b582a90c303fd728b874088a858ce76fa3'),
    'identity': ('preparation_identity_audit.json', '56bc2a13be9891e67ae33ffa0b03a2be6c640521b2a2d0043a10c2b879fb9148'),
    'preparer': ('prepare_candidate.py', 'fc2d186c5d9ace093ff083aea1c1b3d08bb2a42ca47f51de3961ebd850728999'),
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def artifact(path):
    path = Path(os.path.abspath(path))
    require(path.is_relative_to(PROJECT), 'Evidence escaped the engine project')
    for parent in (path, *path.parents):
        info = parent.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Reparse point in engine evidence')
        if parent == PROJECT:
            break
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Expected a regular evidence file')
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Evidence changed while hashing')
    return {'path': str(path), 'bytes': after.st_size, 'sha256': digest}


def verify(row, path=None):
    actual = artifact(path or row.get('path') or row['original_path'])
    require(actual['sha256'] == row['sha256'] and
            ('bytes' not in row or type(row['bytes']) is int and row['bytes'] == actual['bytes']),
            'Evidence digest differs: ' + actual['path'])
    return actual


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def publish(path, value, expected=None):
    if expected is not None:
        require(artifact(path) == expected, 'Progress changed before atomic publication')
    else:
        require(not os.path.lexists(path), 'Inspect the existing publication before continuing')
    temporary = path.with_name(path.name + '.publishing.tmp')
    require(not os.path.lexists(temporary), 'Inspect the existing publication temporary file')
    payload = (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode('utf8')
    with temporary.open('xb') as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    require(path.read_bytes() == payload, 'Published bytes differ')
    return artifact(path)


def main():
    retail = os.path.normcase(os.path.abspath(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5"))
    denied = []

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = os.path.normcase(os.path.abspath(os.fsdecode(arguments[0])))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if target == retail or target.startswith(retail + os.sep):
                denied.append(event)
                raise RuntimeError('Retail state access forbidden')
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2', 'os.exec',
                     'os.spawn', 'os.posix_spawn', 'ctypes.dlopen'):
            denied.append(event)
            raise RuntimeError('Native/process execution forbidden')

    sys.addaudithook(audit)
    refs = {}
    for name, (relative, digest) in PINS.items():
        refs[name] = artifact(STAGE / relative)
        require(refs[name]['sha256'] == digest, 'Reviewed input changed: ' + name)
    scope, tests, prepared, identity = [read(refs[name]['path']) for name in ('scope', 'tests', 'prepared', 'identity')]
    old_progress = artifact(PROGRESS)
    require(old_progress['sha256'] == '0cca5a5e5ba201bdba36659817800f558fe18e3bf845337748fa8cbbd97dc36b',
            'The reviewed intermediate progress changed')
    progress = read(PROGRESS)
    require(progress['full_engine_goal_complete'] is False and progress['full_goal_redefined'] is False,
            'Full engine scope changed')
    for key in ('host_execution_allowed', 'gamecore_execution_allowed', 'native_window_execution_allowed',
                'retail_user_state_access_allowed', 'game_process_access_allowed', 'default_promoted'):
        require(scope[key] is False, 'User test hold changed')
    require(scope['retail_mod_test_hold_active'] is True, 'Retail test hold released unexpectedly')
    protected = [verify(row) for row in scope['protected_artifacts']]
    for row in identity['protected_artifacts']:
        verify(row)
    backup = verify(scope['progress_backup'])
    source_backups = [verify(row['backup']) for row in scope['source_changes']]
    sources = {name: verify(row) for name, row in tests['source_inputs'].items()}
    for row in tests['regression_inputs'].values():
        verify(row)
    require(tests['status'] == 'PASS_FOUND_VALUE_RUNTIME_OPTIONS_HEADLESS_ONLY' and tests['test_count'] == 52 and
            tests['failure_count'] == tests['error_count'] == tests['skipped_count'] == 0 and tests['harness_error'] is None and
            tests['controlled_host_popen_calls'] == 6 and tests['actual_process_or_ctypes_calls'] == tests['game_process_queries'] == 0,
            'Actual guarded headless result did not pass')
    require(all(tests[key] is True for key in ('sources_unchanged', 'regression_inputs_unchanged', 'protected_unchanged', 'owned_scratch_cleaned'))
            and tests['forbidden_access_attempts'] == [], 'Headless integrity/cleanup changed')
    require(prepared['run_id'] == identity['run_id'] == RUN and prepared['host_build_id'] == identity['host_build_id'] == BUILD and
            prepared['status'] == 'PREPARED_NOT_EXECUTED' and identity['status'] == 'PASS_PREPARED_NOT_EXECUTED' and
            prepared['runtime_inputs'] == identity['runtime_inputs'] == 24 and prepared['hardlinks'] == prepared['cache_hits'] == 15 and
            prepared['new_cache_objects'] == 0 and prepared['current_python_support_count'] == 6 and
            prepared['policy_resolution_calls'] == identity['policy_resolution_calls'] == 1 and
            prepared['native_process_or_ctypes_calls'] == identity['outer_process_or_ctypes_calls'] == 0 and
            prepared['source_inputs'] == identity['source_inputs'] == tests['source_inputs'] and
            prepared['test_result'] == identity['test_result'] == refs['tests'] and
            identity['native_execution_outputs_absent'] is True and identity['inputs_unchanged'] is True and
            prepared['forbidden_access_attempts'] == identity['forbidden_access_attempts'] == [], 'Private preparation lineage differs')
    for key in ('host_executed', 'gamecore_loaded', 'hwnd_created', 'retail_user_state_accessed', 'default_promoted',
                'actual_sdk_worker_selection_verified', 'physical_multicore_verified', 'performance_improvement_verified', 'full_engine_goal_complete'):
        require(identity[key] is False, 'Unproven native acceptance claim')
    request_ref = verify(prepared['request'])
    request = read(request_ref['path'])
    require(len(request['runtime_inputs']) == 24 and Path(request['cwd']) == RUNTIME and request['smoke'] is False and
            request['resume_from'] is None and request['stage_or_mods_changed'] is False, 'Fresh private request differs')
    policy = request['found_value_worker_policy']
    expected = {'schema': 'zerosis.found_value_worker_policy.v1', 'requested': 'auto', 'resolved_workers': 4,
                'cpu_hint': {'source': 'process_cpu_count', 'available_logical_cpus': 12}, 'trace_enabled': False, 'cpu_trace_enabled': False}
    require(policy == expected == prepared['found_value_worker_policy'] == prepared['policy_bridge']['policy'] == identity['policy_bridge']['policy'],
            'Sealed worker policy differs')
    manifest_ref = verify(prepared['policy_bridge']['support_manifest'])
    manifest = read(manifest_ref['path'])
    support = read(verify(request['interactive_ui_support'])['path'])
    inventory = request['interactive_ui_support_inventory']
    names = set(scope['expected_frozen_python_support'])
    require(len(names) == 6 and all(set(row['tools']) == names and row['found_value_worker_policy'] == policy
                                  for row in (manifest, support, inventory)), 'Frozen support policy/tool set differs')
    frozen_support = {}
    for name in sorted(names):
        frozen = verify(manifest['tools'][name])
        current = artifact(PROJECT / 'tools' / name)
        require(Path(frozen['path']) == RUNTIME / 'interactive_ui_support/tools' / name and
                (frozen['bytes'], frozen['sha256']) == (current['bytes'], current['sha256']) and
                verify(inventory['tools'][name]['frozen']) == verify(support['tools'][name]['frozen']) == frozen,
                'Frozen support is not current: ' + name)
        frozen_support[name] = frozen
    for name in ('runner', 'frozen_runner', 'found_value_runtime_options', 'frozen_found_value_runtime_options'):
        row = verify(request['provenance'][name])
        source = sources['runner' if 'runner' in name else 'options_helper']
        require((row['bytes'], row['sha256']) == (source['bytes'], source['sha256']), 'Frozen runner/helper differs')
    flag, command = '--found-value-workers', request['command']
    require(command.count(flag) == 1 and command[command.index(flag) + 1] == '4', 'Driver flag differs')
    for filename, key in (('Play.ps1', 'play'), ('Resume.ps1', 'resume')):
        path = RUNTIME / filename
        verify(request['launcher_control_metadata'][key], path)
        require(re.findall(r'--found-value-workers\s+([^\s]+)', path.read_text(encoding='utf-8-sig')) == ['4'], 'Launcher flag differs')
    require(verify(request['launcher_control_metadata']['found_value_worker_policy_manifest']) == manifest_ref, 'Control seal differs')
    require(len(identity['private_databases']) == 2 and len(identity['immutable_cache_links']) == 15, 'Private/shared input closure differs')
    db_bytes = 0
    for row in identity['private_databases']:
        db = verify(row['database'])
        info = Path(db['path']).stat()
        require(Path(db['path']).is_relative_to(RUNTIME) and info.st_nlink == 1 and
                [info.st_dev, info.st_ino] == row['private_identity'] and row['private_identity'] != row['source_identity'],
                'Database is not a separate private copy')
        db_bytes += db['bytes']
    for root in (RUNTIME, EVIDENCE):
        for name in ('sessions', 'attempt.json', 'result.json', 'driver_result.json'):
            require(not os.path.lexists(root / name), 'Native output appeared')
    require(all(not os.path.lexists(path) for path in scope['task_start_cleanup']['B8_objects_absent']), 'Compiler objects reappeared')
    build_ref = verify(prepared['host_build'])
    build = read(build_ref['path'])
    native = [row for row in build['compiler_inputs'] if row['root_name'] in ('project', 'sdk')]
    counts = {name: sum(row['root_name'] == name for row in native) for name in ('project', 'sdk')}
    require(counts == {'project': 75, 'sdk': 144} and len(native) == 219, 'Unexpected current native input closure')
    native_refs = []
    for row in native:
        current, frozen = artifact(row['original_path']), verify(row)
        require((current['bytes'], current['sha256']) == (frozen['bytes'], frozen['sha256']), 'Current native source differs from B8')
        native_refs.append(current)
    native_sha = hashlib.sha256(json.dumps(native_refs, sort_keys=True, separators=(',', ':')).encode('utf8')).hexdigest()
    failed = []
    for name, digest in (('test_result_failed_import.json', '9b146ae2ee9870599b04806544a44e91e94081b59fbe53b3e29f0f688be9e94f'),
                         ('test_result_failed_driver_role.json', 'c8fca7866b4a9b95da93937300f2454ec65c642c91028260de68c2cb1fd4b171')):
        row = artifact(STAGE / name)
        require(row['sha256'] == digest, 'Earlier failure evidence changed')
        failed.append(row)
    temporary = set()
    temporary_files = set()
    for attempt in [read(row['path']) for row in failed] + [tests]:
        require(attempt['owned_scratch_cleaned'] is True and attempt['forbidden_access_attempts'] == [] and
                attempt['actual_process_or_ctypes_calls'] == 0, 'Earlier attempt left unsafe state')
        for value in attempt['temporary_directories']:
            path = Path(value)
            require(path.is_relative_to(PROJECT) and not os.path.lexists(path), 'Owned scratch remains')
            temporary.add(str(path))
        temporary_files.update(row['path'] for row in attempt['temporary_artifacts'])
    require(len(temporary) == 64, 'Unexpected temporary directory count')
    before_ref = verify(scope['storage_before'])
    after_ref = artifact(PROJECT / 'evidence/storage/20261017T005803Z.json')
    require(after_ref['sha256'] == '48c004a9823f365f8bcf3b94040364f0a2677c39492c7b9a3a1d66748f5def0c', 'Storage audit changed')
    before, after = read(before_ref['path']), read(after_ref['path'])
    require(all(row['status'] == 'COMPLETE_METADATA_AUDIT' and not row['errors'] and not row['skipped'] for row in (before, after)),
            'Incomplete storage audit')
    files = [path for path in RUNTIME.rglob('*') if path.is_file()]
    storage = {'before': before_ref, 'after': after_ref,
        'before_unique_GetCompressedFileSizeW_bytes': before['unique_allocated_bytes'],
        'after_unique_GetCompressedFileSizeW_bytes': after['unique_allocated_bytes'],
        'net_unique_change_bytes': after['unique_allocated_bytes'] - before['unique_allocated_bytes'],
        'before_logical_path_bytes': before['logical_path_bytes'], 'after_logical_path_bytes': after['logical_path_bytes'],
        'after_GiB': after['unique_allocated_bytes'] / 1024**3, 'runtime_file_count': len(files),
        'runtime_logical_path_bytes': sum(path.stat().st_size for path in files),
        'runtime_shared_hardlink_logical_bytes': sum(path.stat().st_size for path in files if path.stat().st_nlink > 1),
        'private_database_bytes': db_bytes, 'full_project_copies_created': 0, 'owned_scratch_remaining': 0,
        'limits': ['GetCompressedFileSizeW counted once per NTFS identity; directory/MFT overhead and volume free space excluded.',
                   'The interval includes reports and changed-file backups; this is not an exact allocation trace.',
                   'This audit receipt, finalizer, conformance and progress publication are outside the final metadata snapshot.',
                   'Retained project allocation is not disposable-build volume.']}
    cleanup = {'temporary_directories_removed': len(temporary), 'temporary_unique_file_paths_recorded_removed': len(temporary_files),
        'owned_scratch_remaining': 0, 'new_native_builds': 0, 'new_full_project_copies': 0, 'new_cache_objects': 0,
        'new_large_disposable_artifacts_found': 0, 'prior_cleanup_plan_replayed': False, 'failed_attempts_retained': failed,
        'retained_comparison_runtime_ids': ['20261016T143731Z_bc358fc8d62a', '20261016T123256Z_fae85fb9fe79'],
        'comparison_retention_reason': 'R9 is unexecuted; retain legacy-policy R8 and prior render baseline R7 until native acceptance, plus the unchanged default/recovery.',
        'physical_space_reclaimed_by_fixture_cleanup_measured': False}
    remaining = ['After explicit human release of the retail mod-test hold, verify actual SDK worker selection and scalar-shadow checks with the sealed initial child environment.',
                 'Verify the current x64 original UI/3D, camera, units, new game, turns and named save/load/overwrite/delete.',
                 'Verify original Civ5Save and active-mod compatibility, full campaign, useful deterministic multicore performance and long-run stability.']
    proofs = {**refs, 'request': request_ref, 'host_build': build_ref, 'support_manifest': manifest_ref, 'finalizer': artifact(__file__)}
    result = {'schema': 'zerosis.found_value_runtime_configuration.conformance.v1', 'utc': datetime.now(timezone.utc).isoformat(),
        'status': 'PASS_HEADLESS_CONFIGURATION_AND_PRIVATE_PREPARATION_ONLY', 'requirements': scope['requirements'], 'proofs': proofs,
        'source_inputs': sources, 'source_backups': source_backups, 'progress_backup': backup,
        'protected_artifacts': protected, 'protected_unchanged': True, 'worker_policy': policy, 'current_frozen_support': frozen_support,
        'current_native_compiler_input_count': len(native), 'current_native_compiler_input_roots': counts,
        'current_native_compiler_input_sha256': native_sha, 'current_cpp_matches_existing_host': True,
        'tests_passed': 52, 'controlled_child_process_boundaries': 6, 'actual_native_or_process_calls': 0,
        'policy_resolution_calls': 1, 'runtime_inputs': 24, 'shared_hardlinks': 15, 'cache_hits': 15, 'new_cache_objects': 0,
        'private_databases': 2, 'frozen_python_support': 6, 'cleanup': cleanup, 'storage': storage,
        'retail_mod_test_hold_active': True, 'retail_mods_saves_settings_or_processes_accessed': False,
        'host_executed': False, 'gamecore_loaded': False, 'hwnd_created': False, 'default_promoted': False,
        'actual_sdk_worker_selection_verified': False, 'physical_multicore_verified': False, 'performance_improvement_verified': False,
        'full_engine_goal_complete': False, 'full_goal_redefined': False, 'remaining_full_goal_gates': remaining,
        'verification_limits': ['No real smoke/game session executed; the smoke source branch shares the tested configuration helpers.',
                                'Logical CPU availability is not physical-core evidence or measured speedup.',
                                'Historical frozen launchers remain unchanged; new code reading a missing legacy policy selects scalar0.',
                                'The unchanged preparer read original terrain FPK hashes; retail user settings were not accessed.'],
        'repairs': ['Added guarded Tests sibling-fixture lookup.', 'Supplied the missing existing reparse-check role argument.',
                    'Excluded programming TypeError from expected driver rejection exceptions.',
                    'Final source audit counts project75 and sdk144 separately; their combined closure is219.'],
        'publication_input_progress': old_progress}
    require(not denied, 'Forbidden access during final verification')
    conformance_ref = publish(STAGE / 'conformance.json', result)
    progress.update(utc=datetime.now(timezone.utc).isoformat(), status='FOUND_VALUE_RUNTIME_CONFIGURATION_HEADLESS_AND_PRIVATE_PREPARATION_PASS_NATIVE_PENDING',
        prior_goal_turn_classification='PROGRESS', prepared_runtime_matches_latest_source=True,
        prepared_runtime_matches_current_linked_candidate=True, current_host_build_id=BUILD, latest_source_matches_linked_candidate=True,
        latest_full_source_embedding_limit='B8 matches current project75+sdk144 compiler inputs. R9 freezes all6 current Python support files and current runner provenance. Headless configuration/private preparation only; native SDK/UI/gameplay, original saves/mods and performance acceptance remain pending.')
    progress['current_prepared_runtime'] = {'run_id': RUN, 'host_build_id': BUILD, 'status': 'PREPARED_NOT_EXECUTED',
        'request': request_ref, 'prepared': refs['prepared'], 'runtime_identity_audit': refs['identity'],
        'shared_input_hardlinks': 15, 'existing_cache_hits': 15, 'new_host_and_unit_cache_objects': 0,
        'private_databases': 2, 'current_python_support_count': 6, 'current_source_candidate': True, 'found_value_worker_policy': policy,
        'private_policy_info_settings': verify(prepared['private_policy']), 'process_or_ctypes_library_calls': 0,
        'retail_mods_saves_settings_or_processes_accessed_this_stage': False, 'gamecore_or_windows_executed': False,
        'native_result_created': False, 'default_promoted': False, 'actual_sdk_worker_selection_verified': False, 'native_runtime_acceptance': False}
    progress['runtime_worker_policy_stage'] = {'status': result['status'], 'conformance': conformance_ref, **proofs,
        'worker_policy': policy, 'tests_passed': 52, 'controlled_child_process_boundaries': 6, 'actual_native_or_process_calls': 0,
        'current_cpp_matches_existing_host': True, 'current_native_compiler_input_count': len(native), 'cleanup': cleanup, 'storage': storage,
        'retail_mod_test_hold_active': True, 'actual_sdk_worker_selection_verified': False, 'physical_multicore_verified': False,
        'performance_improvement_verified': False, 'default_promoted': False, 'full_engine_goal_complete': False, 'remaining': remaining}
    progress['latest_storage_audit'] = after_ref
    progress['storage'].update(runtime_worker_policy_stage=storage,
        latest_measured_unique_GetCompressedFileSizeW_bytes=after['unique_allocated_bytes'], latest_measured_utc=after['utc'])
    if isinstance(progress.get('proofs'), dict):
        progress['proofs']['runtime_worker_policy'] = conformance_ref
    progress['user_mod_test_isolation'].update(retail_test_hold_still_active=True, native_window_tests_held=True,
        retail_MODS_user_saves_or_game_processes_accessed_this_stage=False,
        game_Host_GameCore_HWND_or_component_windows_executed_this_stage=False, retail_settings_accessed_this_stage=False,
        original_user_settings_read_this_stage=False, current_stage_policy_source='EXPLICIT_PRIVATE_POLICY_INFO_INI',
        current_stage_actual_native_or_process_calls=0)
    if remaining[0] not in progress['next_native_gates']:
        progress['next_native_gates'].append(remaining[0])
    for row in [*protected, *sources.values()]:
        verify(row)
    require(not denied and progress['full_engine_goal_complete'] is False, 'Unexpected completion/access claim')
    progress_ref = publish(PROGRESS, progress, old_progress)
    print(json.dumps({'status': result['status'], 'conformance': conformance_ref, 'progress': progress_ref,
        'runtime': RUN, 'current_native_inputs_verified': len(native), 'tests': 52, 'temporary_directories_removed': len(temporary),
        'runtime_files': len(files), 'runtime_logical_bytes': storage['runtime_logical_path_bytes'],
        'shared_logical_bytes': storage['runtime_shared_hardlink_logical_bytes'], 'private_database_bytes': db_bytes,
        'net_unique_change_bytes': storage['net_unique_change_bytes'], 'after_unique_GiB': storage['after_GiB'],
        'retail_mod_test_hold_active': True, 'full_engine_goal_complete': False}, ensure_ascii=False))


if __name__ == '__main__':
    main()
