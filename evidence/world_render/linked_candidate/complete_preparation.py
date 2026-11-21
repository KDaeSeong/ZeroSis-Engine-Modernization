"""Statically complete the existing R8 preparation; never materialize another run."""
from contextlib import ExitStack
from datetime import datetime, timezone
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
from types import SimpleNamespace
from unittest.mock import patch
import ctypes

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
HOST_ID = '20261016T142908Z_fc2e23c1fd1e'
RUN_ID = '20261016T143731Z_bc358fc8d62a'
SCOPE_SHA = 'c63aaa0a5d6dac258c430d719418db0948e8f1b36b73e0fd947ea5834d738f22'
PACKAGE_SHA = 'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573'
MANIFEST_SHA = '5fcfbdc669ffd233c4ec64118e8e938656079527028a7ac052659421c6b24e7a'
REPORT_SHA = 'f1353330edad0c93ed6e8ee42af996f87b052b6920404df3b8411b5ec4895d63'
REQUEST_SHA = 'b875fc29e58b9d53634cb70f6faed229837445d2d663670f12a352d597c4580f'
FAILURE = 'Wrong private policy source'
PINS = {
    'prepare_candidate.py': (21717, '9077f6583dbffddfd984d6678857fb97abcc6ea1096ce83708516703daec78c4'),
    'run_stage.py': (15274, '2d7ffaa1e42ace8d66d02d1a16b6c291008a7d7513d53d58407d3733ab0a1ad5'),
    'prepare_started.json': (912, 'd363b7aa65ee0e02e84f2fe9242542d858247320c10894b4288f6c3cda08c9a7'),
    'prepare_invocation.json': (1108, '6a7d897667ba403f53b3672f910715ed4b9e8026ab0c76eb0791ca29eecf6216'),
    'prepare.stdout.log': (0, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    'prepare.stderr.log': (1121, '5a0c1c3170d12b4955571c1bdecd324bbfeb4ff17db83d74378f119c4e6476a4'),
    'preparation_started.json': (13104, '04673de72e90f6623196e334924198d8cc92121318612e5d6c2fe1669a4dda77'),
    'materializer.stdout.log': (437, '7cfd9d0ec2d29788b802ecb1f12a96841bd0a5ac2c2047082e9636115dd0cc38'),
    'materializer.stderr.log': (0, 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'),
    'PolicyInfo.ini': (32, 'af852aac03c83306ba18fef78dddf7c4eec965db3d526fec5555feba25d98ad9'),
    'build_invocation.json': (1962, '372ef8dced86534fb190913a16e7516e2bbb6cc8c3fc18b58e007c58c4204c76'),
    'attestation_' + HOST_ID + '.json': (70256, '978ecb48269d4bcf3959895285f06f2ee75a3ab8d1bdb6b00d819d124b554452'),
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def artifact(path):
    path = Path(os.path.abspath(path))
    require(path.is_relative_to(PROJECT) and path != PROJECT, 'Completion input escaped the private project')
    for item in (path, *path.parents):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not info.st_file_attributes & 0x400,
                'Completion input contains a reparse point')
        if item == PROJECT:
            break
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode), 'Completion input is not ordinary')
    identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_file_attributes)
    with path.open('rb') as stream:
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Completion input changed while opening')
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Completion input changed while hashing')
    require(identity(path.lstat()) == identity(before), 'Completion input identity changed')
    return {'path': str(path), 'bytes': before.st_size, 'sha256': sha}


def read(path):
    ref = artifact(path)
    require(ref['bytes'] <= 8 * 1024 * 1024, 'Completion JSON exceeds its bound')
    return json.loads(Path(ref['path']).read_text(encoding='utf-8-sig'))


def verify(row):
    observed = artifact(row['path'])
    require(observed == {field: row[field] for field in ('path', 'bytes', 'sha256')},
            'A completion input changed: ' + row['path'])
    return observed


def write_new(path, value):
    require(path.parent == STAGE and not os.path.lexists(path), 'Completion outputs are single-use')
    with path.open('x', encoding='utf8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def install_guard(denied):
    retail = key(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = key(os.fsdecode(arguments[0]))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if target == retail or target.startswith(retail + os.sep):
                denied.append(event)
                raise RuntimeError('Retail MODS, saves and settings are forbidden during static completion')
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2',
                     'os.exec', 'os.posix_spawn', 'os.spawn', 'ctypes.dlopen'):
            denied.append(event)
            raise RuntimeError('Process execution and ctypes loading are forbidden during static completion')

    sys.addaudithook(audit)


def load(name, path):
    before = artifact(path)
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'Cannot import the sealed validation module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(artifact(path) == before, 'A validation module changed while importing')
    return module


def original_annotation(value, expected):
    require(isinstance(value, dict) and set(value) == {'original_path', 'sha256', 'bytes'},
            'Private policy source annotation must have exactly its original three keys')
    require(isinstance(value['original_path'], str) and type(value['bytes']) is int and
            key(value['original_path']) == key(expected['path']) and
            value['sha256'] == expected['sha256'] and value['bytes'] == expected['bytes'],
            'Private policy source annotation identity, SHA or size differs')
    require(artifact(value['original_path'])['sha256'] == expected['sha256'], 'Annotated private policy changed')
    return {'path': expected['path'], 'sha256': value['sha256'], 'bytes': value['bytes']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    require(args.build_id == HOST_ID and args.run_id == RUN_ID, 'Completion is restricted to the existing B8/R8 pair')
    for name in ('completion_start.json', 'prepared.json', 'preparation_identity_audit.json', 'preparation_completion.json'):
        require(not os.path.lexists(STAGE / name), 'Inspect the existing completion instead of replaying it')
    denied, guards = [], []
    install_guard(denied)
    with ExitStack() as stack:
        for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL'):
            guards.append(stack.enter_context(patch(name, side_effect=RuntimeError('Static completion forbids ' + name))))
        pinned = {}
        for name, (size, sha) in PINS.items():
            ref = artifact(STAGE / name)
            require(ref['bytes'] == size and ref['sha256'] == sha, 'An original preparation/failure input changed: ' + name)
            pinned[name] = ref
        checker = artifact(Path(__file__).absolute())
        require(artifact(STAGE / 'scope.json')['sha256'] == SCOPE_SHA, 'Approved linked scope changed')
        completion_start = STAGE / 'completion_start.json'
        write_new(completion_start, {'schema': 'zerosis.world_camera_civilian.static_completion_start.v1',
            'status': 'STATIC_VALIDATION_STARTED', 'utc': datetime.now(timezone.utc).isoformat(),
            'run_id': RUN_ID, 'host_build_id': HOST_ID, 'checker': checker, 'original_inputs': pinned,
            'runner_main_or_materializer_called': False, 'retail_mod_test_hold_active': True})
        old = load('_world_render_failed_preparation_for_static_completion', STAGE / 'prepare_candidate.py')
        old.install_outer_guard(denied)
        stage = load('_world_render_stage_for_static_completion', STAGE / 'run_stage.py')
        for module, name in ((old, 'main'), (stage, 'main'), (stage, 'run_command'), (stage.common, 'run_command')):
            guards.append(stack.enter_context(patch.object(module, name, side_effect=RuntimeError('Completion never executes ' + name))))
        scope = stage.verify_scope()
        build_invocation = read(STAGE / 'build_invocation.json')
        require(build_invocation['status'] == 'PASS' and type(build_invocation['exit_code']) is int and
                build_invocation['exit_code'] == 0 and build_invocation['result']['build_id'] == HOST_ID,
                'Completion requires the preserved successful B8 invocation')
        report_ref = stage.verify_build(HOST_ID, scope)
        require(report_ref['sha256'] == REPORT_SHA, 'Completion selected a different current build')
        report_path = Path(report_ref['path'])
        build = read(report_path)
        attestation_path = STAGE / ('attestation_' + HOST_ID + '.json')
        attestation = read(attestation_path)
        require(attestation['schema'] == 'zerosis.world_camera_civilian_linked_pe_attestation.v1' and
                attestation['status'] == 'PASS' and attestation['build_id'] == HOST_ID and
                attestation['inputs_unchanged'] is True and attestation['exact_final_dependency_closure'] is True and
                attestation['actual_pe_inspected'] is True, 'Current linked PE proof did not pass')
        require(verify(attestation['build_report']) == report_ref and verify(attestation['candidate_scope']) == artifact(STAGE / 'scope.json'),
                'PE report/scope lineage differs')
        exe_ref = verify(attestation['executable'])
        require(exe_ref['path'] == build['executable']['path'] and exe_ref['sha256'] == build['executable']['sha256'] and
                key(exe_ref['path']) == key(PROJECT / 'Build/UiWindowHost' / HOST_ID / 'final/ZeroSisHost_x64.exe'),
                'Attested executable differs from exact B8')
        require(all(attestation[name] is False for name in ('host_executed', 'gamecore_loaded', 'dll_loaded', 'hwnd_created',
                'mods_or_user_saves_accessed', 'retail_user_settings_accessed', 'default_promoted', 'native_camera_controls_verified',
                'native_civilian_rendering_verified', 'native_binding_execution_verified', 'native_overwrite_verified',
                'retail_save_mod_compatibility_verified', 'unit_package_embedded_in_pe', 'native_unit_package_consumption_verified')) and
                attestation['game_process_queries'] == 0, 'PE proof exceeds the static boundary')
        unit_inputs = scope['current_unit_assets']
        require(set(unit_inputs) == {'binary', 'manifest', 'preparation_contract'} and attestation['external_unit_assets'] == unit_inputs,
                'External unit package lineage differs')
        unit_refs = {name: verify(row) for name, row in unit_inputs.items()}
        require(unit_refs['binary']['sha256'] == PACKAGE_SHA and unit_refs['manifest']['sha256'] == MANIFEST_SHA,
                'The current civilian package changed')
        unit_manifest = read(unit_refs['manifest']['path'])
        require(unit_manifest['status'] == 'PASS_ORIGINAL_UNIT_PACKAGE' and verify(unit_manifest['package']) == unit_refs['binary'] and
                unit_manifest['art_tags'] == ['ART_DEF_UNIT__WARRIOR', 'ART_DEF_UNIT__SETTLER', 'ART_DEF_UNIT__WORKER'],
                'Wrong current external art catalog')
        started = read(STAGE / 'preparation_started.json')
        invocation = read(STAGE / 'prepare_invocation.json')
        parent = read(STAGE / 'prepare_started.json')
        require(invocation['status'] == parent['status'] == 'FAIL' and type(invocation['exit_code']) is int and
                invocation['exit_code'] == parent['exit_code'] == 1 and invocation['result'] is None and
                parent['scope_and_preserved_inputs_unchanged'] is True and started['preserved_guard_main_called'] is False,
                'The preserved failure is not the reviewed post-materialization policy check')
        require(invocation['argv'] == [sys.executable, '-B', '-X', 'utf8', str(STAGE / 'prepare_candidate.py'), '--build-id', HOST_ID],
                'The original preparation invocation changed')
        require((STAGE / 'prepare.stdout.log').read_bytes() == b'' and
                (STAGE / 'prepare.stderr.log').read_text(encoding='utf8').rstrip().endswith('RuntimeError: ' + FAILURE),
                'The reviewed private-policy assertion is not the original failure')
        policy_ref = artifact(STAGE / 'PolicyInfo.ini')
        require(Path(policy_ref['path']).read_bytes() == old.POLICY_BYTES, 'Private PolicyInfo content changed')
        command = [str(old.RUNNER), '--host-build', str(report_path), '--unit-assets-manifest', unit_refs['manifest']['path'],
                   '--policy-info-settings', policy_ref['path'], '--language', 'ko_KR', '--top-panel', '--action-info-panel', '--notification-panel']
        require(started['argv'] == command, 'The authoritative original runner arguments differ')
        success = (STAGE / 'materializer.stdout.log').read_text(encoding='utf8').splitlines()
        require(len(success) == 1 and (STAGE / 'materializer.stderr.log').read_bytes() == b'', 'Materializer logs changed shape')
        success = json.loads(success[0])
        runtime, evidence = PROJECT / 'Build/InteractiveGameRuntime' / RUN_ID, PROJECT / 'evidence/interactive_game' / RUN_ID
        request_path = evidence / 'request.json'
        require(success == {'status': 'PRIVATE_CONTINUOUS_GAME_PREPARED', 'run_id': RUN_ID,
                            'launcher': str(runtime / 'Play.ps1'), 'request': str(request_path)}, 'Materializer did not create exact R8')
        require({row.name for row in runtime.parent.iterdir()} - set(started['runtime_ids_before']) == {RUN_ID} and
                {row.name for row in evidence.parent.iterdir()} - set(started['evidence_ids_before']) == {RUN_ID},
                'The authoritative original inventory does not identify exactly one new R8')
        request_ref = artifact(request_path)
        require(request_ref['sha256'] == REQUEST_SHA and artifact(evidence / 'host_build.json')['sha256'] == REPORT_SHA,
                'Existing R8 request or frozen Host report changed')
        request = read(request_path)
        require(request['run_id'] == RUN_ID and request['smoke'] is False and request['resume_from'] is None and
                request['ui_support_from_run'] is None and request['input_profile'] == 'MANUAL_CONTINUOUS_GAME_LOOP' and
                request['top_panel'] is True and request['action_info_panel'] is True and request['notification_panel'] is True,
                'Existing R8 has a different preparation-only profile')
        options = request['policy_info_options']
        require(options['origin'] == 'EXPLICIT_POLICY_SETTINGS_READ_ONLY' and options['original_user_settings'] is None and
                type(options['policy_info']) is int and options['policy_info'] == 1 and options['run_id'] is None and
                options['original_policy_info'] is None, 'Wrong explicit private policy origin/value/null fields')
        normalized = original_annotation(options['source'], policy_ref)
        require(original_annotation(options['settings_input'], policy_ref) == normalized, 'Private policy settings input differs')
        provenance = started['provenance']
        require(provenance['wrapper'] == pinned['prepare_candidate.py'] and provenance['stage_common'] == pinned['run_stage.py'],
                'The original wrapper/parent provenance differs')
        protected = list({row['path']: row for row in [*started['protected'], *provenance.values(), *pinned.values(),
                          checker, artifact(completion_start), request_ref, report_ref, exe_ref, *unit_refs.values()]}.values())
        for row in protected:
            verify(row)
        require(artifact(old.RUNNER)['sha256'] == old.RUNNER_SHA and all(artifact(PROJECT / name)['sha256'] == sha
                for name, sha in old.HELPER_PINS.items()), 'Preserved runner/cache/animation helper changed')
        legacy = old.load_preserved()
        legacy.install_audit_guard(denied)
        stack.enter_context(patch.object(legacy, 'PROJECT', PROJECT))
        stack.enter_context(patch.object(legacy, 'STAGE', STAGE))
        guards.append(stack.enter_context(patch.object(legacy, 'main', side_effect=RuntimeError('No preserved materialization main'))))
        sys.path.insert(0, str(PROJECT / 'tools'))
        import run_interactive_game as runner
        require(key(runner.__file__) == key(old.RUNNER) and artifact(old.RUNNER)['sha256'] == old.RUNNER_SHA,
                'Imported a different validation-only runner')
        for name in ('main', 'materialize_immutable'):
            guards.append(stack.enter_context(patch.object(runner, name, side_effect=RuntimeError('Completion forbids runner.' + name))))
        require(request['host_runtime_validation'] == runner.check_host_runtime_artifacts(build) and
                request['provenance']['host_build']['sha256'] == REPORT_SHA and
                key(request['provenance']['host_build']['path']) == key(evidence / 'host_build.json'), 'Wrong existing Host provenance')
        runtime_host = [row for row in request['runtime_inputs'] if Path(row['path']).name == 'ZeroSisHost_x64.exe']
        runtime_unit = [row for row in request['runtime_inputs'] if Path(row['path']).name == 'unit-assets.bin']
        require(len(runtime_host) == len(runtime_unit) == 1 and runtime_host[0]['sha256'] == exe_ref['sha256'] and
                runtime_unit[0]['sha256'] == PACKAGE_SHA, 'Existing runtime Host/unit package differs')
        unit = request['unit_assets']
        require(unit['status'] == 'PASS_ORIGINAL_UNIT_PACKAGE' and unit['reused_from_run'] is None and
                verify(unit['package']) == artifact(runtime / 'unit-assets.bin') and unit['package']['sha256'] == PACKAGE_SHA and
                key(unit['source_package']['original_path']) == key(unit_refs['binary']['path']) and
                unit['source_package']['sha256'] == PACKAGE_SHA and
                key(unit['source_manifest']['original_path']) == key(unit_refs['manifest']['path']) and
                unit['source_manifest']['sha256'] == MANIFEST_SHA and key(unit['manifest']['path']) == key(evidence / 'unit-assets-source-manifest.json') and
                verify(unit['manifest'])['sha256'] == MANIFEST_SHA and unit['manifest']['bytes'] == unit_refs['manifest']['bytes'],
                'Existing source/runtime/copied unit manifest lineage differs')
        require(not (runtime / 'sessions').exists() and not any((evidence / name).exists() for name in
                ('attempt.json', 'result.json', 'driver_result.json')), 'Existing R8 has native execution output')
        runner.check_artifacts(request)
        methods = request['materializations']
        completion_provenance = {'checker': checker, 'started': artifact(completion_start), 'original_failure': pinned['prepare_invocation.json'],
            'original_failure_stderr': pinned['prepare.stderr.log'], 'original_preparation_started': pinned['preparation_started.json'],
            'original_materializer_success': pinned['materializer.stdout.log']}
        prepared = {'schema': 'zerosis.world_camera_civilian.private_prepared.v1', 'status': 'PREPARED_NOT_EXECUTED',
            'utc': datetime.now(timezone.utc).isoformat(), 'run_id': RUN_ID, 'host_build_id': HOST_ID,
            'request': request_ref, 'host_build': report_ref, 'guard': provenance['wrapper'], 'actual_runner_argv': command,
            'started': pinned['preparation_started.json'], 'runtime_executable': runtime_host[0], 'unit_assets': unit,
            'external_unit_inputs': unit_refs, 'protected': protected, 'current_python_support_count': len(old.TOOLS),
            'runtime_inputs': len(request['runtime_inputs']), 'hardlinks': sum(row.get('materialization_method') == 'hardlink' for row in methods),
            'cache_hits': sum(row.get('cache_method') == 'cache-hit' for row in methods),
            'new_cache_objects': sum(str(row.get('cache_method', '')).startswith('cache-created') for row in methods),
            'forbidden_access_attempts': denied, 'native_process_or_ctypes_calls': 0, 'native_execution_outputs_absent': True,
            'retail_mod_test_hold_active': True, 'host_gamecore_hwnd_executed': False, 'retail_user_state_or_processes_accessed': False,
            'default_release_promoted': False, 'native_camera_or_civilian_acceptance': False,
            'terrain_preparation_policy': 'The original runner already prepared R8; static completion does not reread original FPK archives or materialize inputs.',
            'static_completion': completion_provenance, 'original_failure_reason': FAILURE,
            'source_annotation_normalization': {'expected_keys': ['original_path', 'sha256', 'bytes'],
                'original': options['source'], 'normalized': normalized, 'expected_policy': policy_ref}}
        require(len(request['runtime_inputs']) == 24 and prepared['hardlinks'] == 15 and not denied and
                all(guard.call_count == 0 for guard in guards), 'Static validation violated a count or execution boundary')
        for row in protected:
            verify(row)
        write_new(STAGE / 'prepared.json', prepared)
        identity = legacy.verify_private_identity(SimpleNamespace(artifact=artifact, read=read, require=require), HOST_ID)
        require(len(identity['private_databases']) == 2 and len(identity['current_frozen_manifest_support']) == 5 and
                len(identity['immutable_cache_links']) == 15, 'Private DB/cache/frontend identity count differs')
        stage.verify_scope()
        runner.check_artifacts(request)
        for row in protected:
            verify(row)
        require(not denied and all(guard.call_count == 0 for guard in guards), 'A forbidden call occurred during static validation')
        require(not (runtime / 'sessions').exists() and not any((evidence / name).exists() for name in
                ('attempt.json', 'result.json', 'driver_result.json')), 'Native execution output appeared during static completion')
        identity.update(schema='zerosis.world_camera_civilian.private_preparation_identity.v1', status='PASS_PREPARED_NOT_EXECUTED',
            utc=datetime.now(timezone.utc).isoformat(), provenance={**provenance, 'static_completion_checker': checker},
            actual_runner_argv=command, external_unit_inputs=unit_refs, runtime_unit_assets=unit, inputs_unchanged=True,
            forbidden_access_attempts=denied, outer_process_or_ctypes_calls=0, preserved_guard_and_reports_unmodified=True,
            preserved_guard_main_called=False, retail_mod_test_hold_active=True, host_gamecore_hwnd_executed=False,
            retail_user_state_or_processes_accessed=False, default_release_promoted=False, native_camera_controls_verified=False,
            native_civilian_rendering_verified=False, native_overwrite_verified=False, retail_save_mod_compatibility_verified=False,
            terrain_preparation_policy=prepared['terrain_preparation_policy'], static_completion=completion_provenance,
            original_failure_reason=FAILURE, source_annotation_normalization=prepared['source_annotation_normalization'])
        audit_path = STAGE / 'preparation_identity_audit.json'
        write_new(audit_path, identity)
        completion = {'schema': 'zerosis.world_camera_civilian.static_preparation_completion.v1',
            'status': 'PASS_STATIC_COMPLETION_OF_EXISTING_PRIVATE_PREPARATION',
            'utc': datetime.now(timezone.utc).isoformat(), 'run_id': RUN_ID, 'host_build_id': HOST_ID,
            'checker': checker, 'original_inputs': pinned, 'original_failure_reason': FAILURE,
            'correction': 'Normalize the exact original_path/sha256/bytes source annotation to the artifact path schema; preserve all origin/value/null checks.',
            'prepared': artifact(STAGE / 'prepared.json'), 'identity_audit': artifact(audit_path),
            'request': request_ref, 'host_build': report_ref, 'pe_attestation': pinned['attestation_' + HOST_ID + '.json'],
            'static_completion': completion_provenance,
            'runtime_inputs': 24, 'immutable_cache_links': 15, 'private_databases': 2, 'frontend_files': 5,
            'new_runtime_created_by_completion': False, 'runner_main_calls': 0, 'materializer_calls': 0,
            'forbidden_access_attempts': denied, 'guard_call_counts': [guard.call_count for guard in guards],
            'original_failure_and_success_logs_unchanged': True, 'authoritative_original_inventory_preserved': True,
            'retail_mod_test_hold_active': True, 'host_gamecore_hwnd_executed': False,
            'retail_user_state_or_processes_accessed': False, 'default_release_promoted': False,
            'native_camera_or_civilian_acceptance': False}
        write_new(STAGE / 'preparation_completion.json', completion)
        print(json.dumps({'status': completion['status'], 'run_id': RUN_ID, 'host_build_id': HOST_ID,
                          'runtime_inputs': 24, 'hardlinks': 15, 'private_databases': 2,
                          'identity_audit': artifact(audit_path), 'completion': artifact(STAGE / 'preparation_completion.json')}))


if __name__ == '__main__':
    main()
