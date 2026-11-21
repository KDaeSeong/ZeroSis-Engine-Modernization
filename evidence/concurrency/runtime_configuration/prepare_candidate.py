"""Prepare one B8-based private worker-policy runtime without native execution.

The reviewed headless test receipt pins the current three production tools.
This is initial-child-environment configuration proof, not SDK consumption,
physical multicore execution, performance, or complete engine acceptance.
"""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from datetime import datetime, timezone
import argparse
import ctypes
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
from types import SimpleNamespace
from unittest.mock import patch

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
SCOPE = STAGE / 'scope.json'
SCOPE_SHA = '3442c84392c969f37df3d6d6a00576a0df0df96d365586db73edf99158d45bc5'
BUILD_ID = '20261016T142908Z_fc2e23c1fd1e'
PRESERVED = PROJECT / 'evidence/save_overwrite/linked_candidate/prepare_candidate.py'
PRESERVED_SHA = 'f28dbf303b8e5ae653fff70a923c86c62a77e0fbd64c92633eefc619d6039d2f'
RUNNER = PROJECT / 'tools/run_interactive_game.py'
PACKAGE_SHA = 'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573'
MANIFEST_SHA = '5fcfbdc669ffd233c4ec64118e8e938656079527028a7ac052659421c6b24e7a'
TOOLS = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
         'ui_bitmap_fonts.py', 'civ5_ui_assets.py', 'found_value_runtime_options.py')
SOURCE_PATHS = {'options_helper': 'tools/found_value_runtime_options.py',
                'runner': 'tools/run_interactive_game.py',
                'driver': 'tools/interactive_ui_driver.py',
                'tests': 'Tests/found_value_runtime_options.py',
                'verifier': 'tools/verify_found_value_runtime_options.py'}
HELPER_PINS = {
    'tools/runtime_input_cache.py': 'cc9a819989a6d5191352001e0cf3b618bd08a3acf781caf744b4fc52182f2f19',
    'tools/unit_animation_assets.py': 'e7fb3b528f59fda2aa0cd5be22498b7f84ec123942b3ebc46edba93b77ddd1f3'}
POLICY_BYTES = b'[UserSettings]\r\nPolicyInfo = 1\r\n'
FIELD = 'found_value_worker_policy'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def ordinary(path):
    path = Path(os.path.abspath(path))
    require(key(path).startswith(key(PROJECT) + os.sep), 'Input escaped the project')
    require(key(path.resolve(strict=True)) == key(path), 'Input resolves through another path')
    for item in (path, *path.parents):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Input contains a reparse point')
        if key(item) == key(PROJECT):
            break
    require(stat.S_ISREG(path.lstat().st_mode), 'Expected an ordinary project file')
    return path


def stable(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def artifact(path):
    path = ordinary(path)
    before = path.stat()
    with path.open('rb') as stream:
        require(stable(os.fstat(stream.fileno())) == stable(before), 'Input changed while opening')
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(stable(os.fstat(stream.fileno())) == stable(before), 'Input changed while hashing')
    require(stable(path.stat()) == stable(before), 'Input path changed while hashing')
    return {'path': str(path), 'bytes': before.st_size, 'sha256': sha}


def verify(row):
    require(type(row) is dict and type(row.get('path')) is str and type(row.get('bytes')) is int and
            row['bytes'] >= 0 and re.fullmatch(r'[0-9a-f]{64}', str(row.get('sha256', ''))), 'Malformed artifact')
    observed = artifact(row['path'])
    require(key(observed['path']) == key(row['path']) and observed['bytes'] == row['bytes'] and
            observed['sha256'] == row['sha256'], 'Sealed input changed: ' + row['path'])
    return observed


def verify_digest(row, expected_path):
    require(type(row) is dict and key(row.get('path', '')) == key(expected_path), 'Unexpected artifact path')
    observed = artifact(expected_path)
    require(observed['sha256'] == row.get('sha256') and
            ('bytes' not in row or observed['bytes'] == row['bytes']), 'Artifact payload differs')
    return observed


def annotation(row, expected):
    require(type(row) is dict and set(row) == {'original_path', 'bytes', 'sha256'} and
            type(row['original_path']) is str and type(row['bytes']) is int and
            key(row['original_path']) == key(expected['path']) and row['bytes'] == expected['bytes'] and
            row['sha256'] == expected['sha256'], 'Original-path source annotation differs')


def read(path):
    path = ordinary(path)
    before = path.stat()
    require(before.st_size <= 8 * 1024 * 1024, 'JSON receipt exceeds its bound')
    with path.open('rb') as stream:
        require(stable(os.fstat(stream.fileno())) == stable(before), 'JSON changed while opening')
        raw = stream.read(8 * 1024 * 1024 + 1)
        require(len(raw) == before.st_size and stable(os.fstat(stream.fileno())) == stable(before),
                'JSON changed while reading')
    require(stable(path.stat()) == stable(before), 'JSON path changed while reading')
    return json.loads(raw.decode('utf-8-sig'))


def write_new(path, value):
    require(path.parent == STAGE and not os.path.lexists(path), 'Preparation evidence is single-use')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def install_outer_guard(denied):
    retail = key(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = key(os.fsdecode(arguments[0]))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if target == retail or target.startswith(retail + os.sep):
                denied.append(event)
                raise RuntimeError('Retail user settings, MODS and saves are forbidden')
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2',
                     'os.exec', 'os.posix_spawn', 'os.spawn', 'ctypes.dlopen'):
            denied.append(event)
            raise RuntimeError('Process, native window and ctypes library execution are forbidden')

    sys.addaudithook(audit)


def load_preserved():
    require(artifact(PRESERVED)['sha256'] == PRESERVED_SHA, 'Preserved identity guard changed')
    spec = importlib.util.spec_from_file_location('_worker_policy_preserved_identity', PRESERVED)
    require(spec is not None and spec.loader is not None, 'Cannot load the preserved identity guard')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Capture(io.StringIO):
    def write(self, value):
        require(self.tell() + len(value) <= 1024 * 1024, 'Materializer output exceeds its bound')
        return super().write(value)


def scope_and_tests(args):
    require(artifact(SCOPE)['sha256'] == SCOPE_SHA, 'Reviewed scope changed')
    scope = read(SCOPE)
    require(scope['schema'] == 'zerosis.found_value_runtime_configuration.scope.v1' and
            scope['current_host_build_id'] == BUILD_ID and scope['private_preparation_allowed'] is True and
            scope['retail_mod_test_hold_active'] is True and scope['current_host_source_unchanged'] is True and
            scope['policy_field'] == FIELD and scope['policy_schema'] == 'zerosis.found_value_worker_policy.v1' and
            scope['expected_frozen_python_support'] == list(TOOLS), 'Private preparation scope differs')
    for name in ('game_process_access_allowed', 'gamecore_execution_allowed', 'host_execution_allowed',
                 'native_window_execution_allowed', 'retail_user_state_access_allowed', 'default_promoted',
                 'actual_sdk_worker_selection_verified', 'physical_multicore_verified',
                 'performance_improvement_verified', 'full_engine_goal_complete'):
        require(scope[name] is False, 'Scope unexpectedly permits or claims native acceptance: ' + name)
    require(type(scope['protected_artifacts']) is list and len(scope['protected_artifacts']) == 19,
            'Expected the exact protected source/provider/default ledger')
    protected = [verify(row) for row in scope['protected_artifacts']]
    for row in scope['source_changes']:
        backup = verify(row['backup'])
        require(backup['sha256'] == row['before']['sha256'] and backup['bytes'] == row['before']['bytes'] and
                key(backup['path']) == key(STAGE / 'source_before' / Path(row['relative']).name),
                'Changed-file historical backup differs')
        protected.append(backup)
    backup = verify(scope['progress_backup'])
    require(backup['sha256'] == scope['progress_before']['sha256'] and
            backup['bytes'] == scope['progress_before']['bytes'], 'Historical progress backup differs')
    protected.extend([backup, verify(scope['storage_before']), verify(scope['task_start_cleanup']['previous_result']),
                      verify(scope['task_start_cleanup']['post_retirement'])])
    require(all(not os.path.lexists(path) for path in scope['task_start_cleanup']['B8_objects_absent']),
            'Previously retired B8 objects reappeared')
    require(key(args.test_result) == key(STAGE / 'test_result.json') and
            re.fullmatch(r'[0-9a-f]{64}', args.test_result_sha256), 'An exact reviewed test receipt is required')
    test_ref = artifact(args.test_result)
    require(test_ref['sha256'] == args.test_result_sha256, 'Reviewed actual test receipt changed')
    tests = read(args.test_result)
    require(tests['schema'] == 'zerosis.found_value_runtime_options.headless_tests.v1' and
            tests['status'] == 'PASS_FOUND_VALUE_RUNTIME_OPTIONS_HEADLESS_ONLY' and
            tests['sources_unchanged'] is True and tests['protected_unchanged'] is True and
            tests['scope'] == artifact(SCOPE) and tests['protected_artifacts'] == scope['protected_artifacts'] and
            tests['progress_backup'] == backup, 'Headless test profile/protected lineage differs')
    for name in ('failure_count', 'error_count', 'actual_process_or_ctypes_calls', 'game_process_queries'):
        require(type(tests[name]) is int and tests[name] == 0, 'Headless tests recorded failure/native access: ' + name)
    require(type(tests['test_count']) is int and tests['test_count'] > 0 and tests['forbidden_access_attempts'] == [] and
            type(tests['controlled_host_popen_calls']) is int and tests['controlled_host_popen_calls'] > 0,
            'Headless tests lack actual controlled production-driver coverage')
    for name in ('host_executed', 'gamecore_loaded', 'hwnd_created', 'retail_user_state_accessed', 'default_promoted'):
        require(tests[name] is False, 'Headless receipt unexpectedly claims native execution: ' + name)
    require(set(tests['source_inputs']) == set(SOURCE_PATHS), 'Wrong headless source closure')
    sources = {}
    for name, relative in SOURCE_PATHS.items():
        row = tests['source_inputs'][name]
        require(key(row['path']) == key(PROJECT / relative), 'Wrong tested production/test source: ' + name)
        sources[name] = verify(row)
    return scope, tests, test_ref, sources, protected


def validate_policy_records(request, runtime, evidence, helper):
    policy = helper.validate_policy(request[FIELD])
    require(policy['requested'] == 'auto' and policy['resolved_workers'] in (0, 2, 4) and
            request['found_value_sdk_consumption_verified'] is False, 'Unexpected preparation policy/acceptance')
    inventory = request['interactive_ui_support_inventory']
    support = read(evidence / 'interactive_ui_support.json')
    manifest_path = runtime / 'interactive_ui_support/support_manifest.json'
    manifest = read(manifest_path)
    for record in (inventory, support, manifest):
        require(record[FIELD] == policy and helper.validate_policy(record[FIELD]) == policy,
                'Request/support/manifest policy differs')
    manifest_ref = artifact(manifest_path)
    verify_digest(request['interactive_ui_support'], evidence / 'interactive_ui_support.json')
    for row in (inventory['frozen_support_manifest'], support['frozen_support_manifest'],
                request['launcher_control_metadata']['found_value_worker_policy_manifest']):
        verify_digest(row, manifest_path)
    require(set(inventory['tools']) == set(support['tools']) == set(manifest['tools']) == set(TOOLS),
            'Expected exactly six frozen frontend helpers')
    command = request['command']
    flag = '--found-value-workers'
    resolved = str(policy['resolved_workers'])
    require(type(command) is list and command.count(flag) == 1 and
            command[command.index(flag) + 1] == resolved, 'Driver command differs from resolved policy')
    for name in ('Play.ps1', 'Resume.ps1'):
        text = ordinary(runtime / name).read_text(encoding='utf-8-sig')
        require(re.findall(r'--found-value-workers\s+([^\s]+)', text) == [resolved],
                'Manual launcher differs from resolved policy: ' + name)
        verify_digest(request['launcher_control_metadata']['play' if name == 'Play.ps1' else 'resume'], runtime / name)
    require(request['sdk_session_profile'] == support['sdk_session_profile'] == {
        'ZEROSIS_UI_SMALL_ASSETS': '1',
        'policy': 'interactive_ui_driver.drive overwrites inherited environment for every Host session'},
        'Existing SDK UI profile changed')
    options_ref = artifact(PROJECT / 'tools/found_value_runtime_options.py')
    for name in ('found_value_runtime_options', 'frozen_found_value_runtime_options'):
        row = request['provenance'][name]
        require(verify_digest(row, row['path'])['sha256'] == options_ref['sha256'], 'Runner policy helper differs')
    return {'policy': policy, 'support_manifest': manifest_ref, 'driver_resolved_flag': resolved,
            'policy_records_equal': True, 'manual_launchers_match': True, 'initial_child_environment_only': True,
            'sdk_consumption_verified': False, 'physical_multicore_verified': False,
            'performance_improvement_verified': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--test-result', type=Path, required=True)
    parser.add_argument('--test-result-sha256', required=True)
    args = parser.parse_args()
    for name in ('PolicyInfo.ini', 'preparation_started.json', 'prepared.json', 'preparation_identity_audit.json',
                 'materializer.stdout.log', 'materializer.stderr.log'):
        require(not os.path.lexists(STAGE / name), 'Inspect the existing attempt instead of repeating preparation')
    denied, guards = [], []
    install_outer_guard(denied)
    with ExitStack() as stack:
        for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL'):
            guards.append(stack.enter_context(patch(name, side_effect=RuntimeError('Execution forbidden: ' + name))))
        scope, tests, test_ref, sources, protected = scope_and_tests(args)
        build_path = PROJECT / f'evidence/ui_window_host/{BUILD_ID}/build_result.json'
        build = read(build_path)
        pe_path = PROJECT / f'evidence/world_render/linked_candidate/attestation_{BUILD_ID}.json'
        pe = read(pe_path)
        require(build['build_id'] == BUILD_ID and build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
                build['error'] is None and pe['status'] == 'PASS' and pe['build_id'] == BUILD_ID and
                pe['schema'] == 'zerosis.world_camera_civilian_linked_pe_attestation.v1' and
                pe['host_executed'] is False and pe['gamecore_loaded'] is False and pe['hwnd_created'] is False,
                'Existing B8 build/PE proof differs')
        exe = verify(pe['executable'])
        unit_dir = PROJECT / 'Build/UnitAssets' / PACKAGE_SHA
        unit_refs = {'binary': artifact(unit_dir / 'unit-assets.bin'),
                     'manifest': artifact(unit_dir / 'unit-assets.manifest.json')}
        require(unit_refs['binary']['sha256'] == PACKAGE_SHA and unit_refs['manifest']['sha256'] == MANIFEST_SHA and
                read(unit_refs['manifest']['path'])['status'] == 'PASS_ORIGINAL_UNIT_PACKAGE', 'Current unit package differs')
        prior = read(scope['existing_runtime']['path'])
        verify(scope['existing_runtime'])
        prior_inputs = {Path(row['path']).name: row['sha256'] for row in prior['runtime_inputs']}
        require(len(prior_inputs) == 24, 'Current R8 input inventory differs')
        for row in prior['runtime_inputs']:
            protected.append(verify_digest(row, row['path']))
        for row in prior['interactive_ui_support_inventory']['tools'].values():
            protected.append(verify_digest(row['frozen'], row['frozen']['path']))
        protected.extend(verify_digest(row, row['path']) for row in prior['launcher_control_metadata'].values()
                         if key(row['path']).startswith(key(PROJECT) + os.sep))
        for relative, sha in HELPER_PINS.items():
            row = artifact(PROJECT / relative)
            require(row['sha256'] == sha, 'Immutable materializer helper changed')
            protected.append(row)
        frontend = {name: artifact(PROJECT / 'tools' / name) for name in TOOLS}
        provenance = {'wrapper': artifact(Path(__file__).absolute()), 'scope': artifact(SCOPE),
                      'preserved_identity_guard': artifact(PRESERVED), 'actual_headless_test_result': test_ref,
                      'host_build': artifact(build_path), 'pe_attestation': artifact(pe_path)}
        protected.extend([*sources.values(), *frontend.values(), *provenance.values(), exe, *unit_refs.values()])
        protected = list({key(row['path']): row for row in protected}.values())
        for row in protected:
            verify(row)
        legacy = load_preserved()
        legacy.install_audit_guard(denied)
        for name, value in (('PROJECT', PROJECT), ('STAGE', STAGE), ('TOOLS', TOOLS)):
            stack.enter_context(patch.object(legacy, name, value))
        stack.enter_context(patch.object(sys, 'path', [str(PROJECT / 'tools'), *sys.path]))
        import found_value_runtime_options as helper
        import run_interactive_game as runner
        require(key(helper.__file__) == key(sources['options_helper']['path']) and
                key(runner.__file__) == key(sources['runner']['path']), 'Imported a different production tool')
        for row in sources.values():
            verify(row)
        policy_path = STAGE / 'PolicyInfo.ini'
        command = [str(RUNNER), '--host-build', str(build_path), '--unit-assets-manifest', unit_refs['manifest']['path'],
                   '--policy-info-settings', str(policy_path), '--language', 'ko_KR', '--top-panel',
                   '--action-info-panel', '--notification-panel']
        runtime_parent, evidence_parent = PROJECT / 'Build/InteractiveGameRuntime', PROJECT / 'evidence/interactive_game'
        before_runtime = {row.name for row in runtime_parent.iterdir()}
        before_evidence = {row.name for row in evidence_parent.iterdir()}
        write_new(STAGE / 'preparation_started.json', {'utc': datetime.now(timezone.utc).isoformat(),
            'argv': command, 'provenance': provenance, 'source_inputs': sources, 'protected': protected,
            'runtime_ids_before': sorted(before_runtime), 'evidence_ids_before': sorted(before_evidence),
            'retail_mod_test_hold_active': True, 'preserved_guard_main_called': False,
            'proof_scope': 'INITIAL_CHILD_ENVIRONMENT_CONFIGURATION_ONLY'})
        with policy_path.open('xb') as stream:
            stream.write(POLICY_BYTES)
            stream.flush()
            os.fsync(stream.fileno())
        policy_ref = artifact(policy_path)
        require(policy_ref['bytes'] == 32 and ordinary(policy_path).read_bytes() == POLICY_BYTES, 'Private policy file differs')
        stdout, stderr = Capture(), Capture()
        actual_argv = None
        try:
            with patch.object(sys, 'argv', command.copy()), redirect_stdout(stdout), redirect_stderr(stderr), \
                 patch.object(runner, 'select_found_value_policy', wraps=runner.select_found_value_policy) as selection:
                actual_argv = list(sys.argv)
                code = runner.main()
                require(code in (None, 0), 'Private runtime preparation failed')
                require(selection.call_count == 1, 'Fresh policy was not resolved exactly once')
        finally:
            for name, captured in (('materializer.stdout.log', stdout), ('materializer.stderr.log', stderr)):
                with (STAGE / name).open('x', encoding='utf-8') as stream:
                    stream.write(captured.getvalue())
        require(actual_argv == command and not denied and all(guard.call_count == 0 for guard in guards),
                'Preparation arguments or execution guard differ')
        summaries = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith('{')]
        require(len(summaries) == 1 and summaries[0]['status'] == 'PRIVATE_CONTINUOUS_GAME_PREPARED',
                'Missing preparation-only return')
        run_id = summaries[0]['run_id']
        require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id) and
                {row.name for row in runtime_parent.iterdir()} - before_runtime == {run_id} and
                {row.name for row in evidence_parent.iterdir()} - before_evidence == {run_id}, 'Unexpected new run inventory')
        runtime, evidence = runtime_parent / run_id, evidence_parent / run_id
        request_path = evidence / 'request.json'
        request = read(request_path)
        require(request['run_id'] == run_id and request['smoke'] is False and request['resume_from'] is None and
                request['ui_support_from_run'] is None and request['input_profile'] == 'MANUAL_CONTINUOUS_GAME_LOOP' and
                request['top_panel'] is True and request['action_info_panel'] is True and request['notification_panel'] is True and
                request['stage_or_mods_changed'] is False, 'Wrong private preparation profile')
        options = request['policy_info_options']
        require(options['origin'] == 'EXPLICIT_POLICY_SETTINGS_READ_ONLY' and options['original_user_settings'] is None and
                options['original_policy_info'] is None and options['policy_info'] == 1 and options['run_id'] is None,
                'Original user settings were selected')
        annotation(options['source'], policy_ref)
        annotation(options['settings_input'], policy_ref)
        require(request['host_runtime_validation']['scope'] == 'RETAINED_HOST_RUNTIME_INPUTS' and
                request['provenance']['host_build']['sha256'] == artifact(build_path)['sha256'] and
                {Path(row['path']).name: row['sha256'] for row in request['runtime_inputs']} == prior_inputs,
                'New runtime differs from the retained B8/R8 native input closure')
        unit = request['unit_assets']
        require(unit['status'] == 'PASS_ORIGINAL_UNIT_PACKAGE' and unit['reused_from_run'] is None and
                verify(unit['package'])['sha256'] == PACKAGE_SHA and verify(unit['manifest'])['sha256'] == MANIFEST_SHA,
                'Private unit package or copied manifest differs')
        annotation(unit['source_package'], unit_refs['binary'])
        annotation(unit['source_manifest'], unit_refs['manifest'])
        policy_record = validate_policy_records(request, runtime, evidence, helper)
        require(not (runtime / 'sessions').exists() and not any((evidence / name).exists()
                for name in ('attempt.json', 'result.json', 'driver_result.json')), 'Native execution outputs exist')
        runner.check_artifacts(request)
        methods = request['materializations']
        prepared = {'schema': 'zerosis.found_value_runtime_configuration.private_prepared.v1',
            'status': 'PREPARED_NOT_EXECUTED', 'utc': datetime.now(timezone.utc).isoformat(),
            'run_id': run_id, 'host_build_id': BUILD_ID, 'request': artifact(request_path),
            'host_build': artifact(build_path), 'guard': provenance['wrapper'], 'actual_runner_argv': actual_argv,
            'started': artifact(STAGE / 'preparation_started.json'), 'test_result': test_ref, 'source_inputs': sources,
            'runtime_inputs': len(request['runtime_inputs']),
            'hardlinks': sum(row.get('materialization_method') == 'hardlink' for row in methods),
            'cache_hits': sum(row.get('cache_method') == 'cache-hit' for row in methods),
            'new_cache_objects': sum(str(row.get('cache_method', '')).startswith('cache-created') for row in methods),
            'current_python_support_count': len(TOOLS), FIELD: policy_record['policy'],
            'policy_bridge': policy_record, 'policy_resolution_calls': 1, 'private_policy': policy_ref,
            'forbidden_access_attempts': denied, 'native_process_or_ctypes_calls': sum(guard.call_count for guard in guards),
            'native_execution_outputs_absent': True, 'retail_mod_test_hold_active': True,
            'host_gamecore_hwnd_executed': False, 'retail_user_state_or_processes_accessed': False,
            'default_release_promoted': False, 'sdk_consumption_verified': False,
            'physical_multicore_verified': False, 'performance_improvement_verified': False,
            'terrain_preparation_policy': 'The unmodified runner rereads installed original terrain FPK hashes before/after while reusing its cached package; installed assets are read only.'}
        require(prepared['runtime_inputs'] == 24 and prepared['hardlinks'] == prepared['cache_hits'] == 15 and
                prepared['new_cache_objects'] == 0, 'Expected reuse of all 15 immutable cache inputs')
        for row in [*protected, policy_ref]:
            verify(row)
        write_new(STAGE / 'prepared.json', prepared)
        identity = legacy.verify_private_identity(SimpleNamespace(artifact=artifact, read=read, require=require), BUILD_ID)
        require(len(identity['private_databases']) == 2 and len(identity['current_frozen_manifest_support']) == 6 and
                not denied and all(guard.call_count == 0 for guard in guards), 'Six-helper private identity/guard failed')
        for row in [*protected, policy_ref]:
            verify(row)
        identity.update(schema='zerosis.found_value_runtime_configuration.private_preparation_identity.v1',
            status='PASS_PREPARED_NOT_EXECUTED', utc=datetime.now(timezone.utc).isoformat(),
            provenance=provenance, actual_runner_argv=actual_argv, source_inputs=sources, test_result=test_ref,
            policy_bridge=policy_record, policy_resolution_calls=1, protected_artifacts=protected, inputs_unchanged=True,
            forbidden_access_attempts=denied, outer_process_or_ctypes_calls=sum(guard.call_count for guard in guards),
            preserved_guard_main_called=False, preserved_guard_and_reports_unmodified=True,
            retail_mod_test_hold_active=True, host_executed=False, gamecore_loaded=False, hwnd_created=False,
            retail_user_state_accessed=False, game_process_queries=0, default_promoted=False,
            actual_sdk_worker_selection_verified=False, physical_multicore_verified=False,
            performance_improvement_verified=False, full_engine_goal_complete=False,
            terrain_preparation_policy=prepared['terrain_preparation_policy'])
        audit_path = STAGE / 'preparation_identity_audit.json'
        write_new(audit_path, identity)
        print(json.dumps({'status': identity['status'], 'run_id': run_id, 'host_build_id': BUILD_ID,
            'runtime_inputs': 24, 'hardlinks': 15, 'private_databases': 2, 'frozen_python_helpers': 6,
            'policy': policy_record['policy'], 'cache_hits': prepared['cache_hits'], 'new_cache_objects': 0,
            'identity_audit': artifact(audit_path)}))


if __name__ == '__main__':
    main()
