"""Prepare the current camera/civilian candidate without native execution.

Only the new private runtime and this stage's preparation receipts are written.
The preserved identity checker and execution/access guards remain unchanged.
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
SCOPE_SHA = 'c63aaa0a5d6dac258c430d719418db0948e8f1b36b73e0fd947ea5834d738f22'
PRESERVED = PROJECT / 'evidence/save_overwrite/linked_candidate/prepare_candidate.py'
PRESERVED_SHA = 'f28dbf303b8e5ae653fff70a923c86c62a77e0fbd64c92633eefc619d6039d2f'
STAGE_COMMON_SHA = '2d7ffaa1e42ace8d66d02d1a16b6c291008a7d7513d53d58407d3733ab0a1ad5'
RUNNER = PROJECT / 'tools/run_interactive_game.py'
RUNNER_SHA = 'b625fd17b3c7b1315696e7caaf63724fb6aad8dd75460921f93843a9974d4311'
PACKAGE_SHA = 'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573'
MANIFEST_SHA = '5fcfbdc669ffd233c4ec64118e8e938656079527028a7ac052659421c6b24e7a'
TOOLS = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
         'ui_bitmap_fonts.py', 'civ5_ui_assets.py')
HELPER_PINS = {
    'tools/runtime_input_cache.py': 'cc9a819989a6d5191352001e0cf3b618bd08a3acf781caf744b4fc52182f2f19',
    'tools/unit_animation_assets.py': 'e7fb3b528f59fda2aa0cd5be22498b7f84ec123942b3ebc46edba93b77ddd1f3',
}
POLICY_BYTES = b'[UserSettings]\r\nPolicyInfo = 1\r\n'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def ordinary_project_file(path):
    path = Path(os.path.abspath(path))
    require(path.is_relative_to(PROJECT) and path != PROJECT, 'Input escaped the private project')
    require(key(path.resolve(strict=True)) == key(path), 'Input resolves through another path')
    for item in (path, *path.parents):
        info = item.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Private preparation input contains a reparse point')
        if key(item) == key(PROJECT):
            break
    require(stat.S_ISREG(path.lstat().st_mode), 'Input is not an ordinary file')
    return path


def artifact(path):
    path = ordinary_project_file(path)
    before = path.stat()
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        identity = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        require(identity(opened) == identity(before), 'Input identity changed while opening')
        sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(identity(os.fstat(stream.fileno())) == identity(before), 'Opened input changed while hashing')
    require(identity(path.stat()) == identity(before), 'Input path changed while hashing')
    return {'path': str(path), 'bytes': before.st_size, 'sha256': sha}


def read(path):
    path = ordinary_project_file(path)
    require(path.stat().st_size <= 8 * 1024 * 1024, 'Private JSON receipt exceeds its bound')
    return json.loads(path.read_text(encoding='utf-8-sig'))


def verify(row):
    require(isinstance(row, dict) and isinstance(row.get('path'), str) and
            re.fullmatch(r'[0-9a-f]{64}', str(row.get('sha256', ''))), 'Invalid sealed input')
    observed = artifact(Path(row['path']))
    require(observed == {name: row[name] for name in ('path', 'bytes', 'sha256')},
            'A sealed preparation input changed: ' + row['path'])
    return observed


def write_new(path, value):
    require(path.parent == STAGE and not os.path.lexists(path), 'Preparation receipts are single-use')
    with path.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def install_outer_guard(denied):
    # This stdlib-only guard precedes every project import, including the
    # preserved guard module. Its guard is then installed unchanged as well.
    retail = key(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5")

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = key(os.fsdecode(arguments[0]))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if target == retail or target.startswith(retail + os.sep):
                denied.append(event)
                raise RuntimeError('Retail user configuration, MODS and saves are forbidden')
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2',
                     'os.exec', 'os.posix_spawn', 'os.spawn', 'ctypes.dlopen'):
            denied.append(event)
            raise RuntimeError('Native/process execution and ctypes library loading are forbidden')

    sys.addaudithook(audit)


def load_preserved():
    require(artifact(PRESERVED)['sha256'] == PRESERVED_SHA, 'Preserved preparation guard changed')
    spec = importlib.util.spec_from_file_location('_world_render_preserved_preparation_guard', PRESERVED)
    require(spec is not None and spec.loader is not None, 'Cannot import the exact preserved guard')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-id', required=True)
    args = parser.parse_args()
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id), 'An exact owned Host build ID is required')
    for name in ('preparation_started.json', 'prepared.json', 'preparation_identity_audit.json',
                 'materializer.stdout.log', 'materializer.stderr.log'):
        require(not os.path.lexists(STAGE / name), 'Inspect the existing preparation instead of repeating it')
    denied, guards = [], []
    install_outer_guard(denied)
    with ExitStack() as stack:
        for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL'):
            guards.append(stack.enter_context(patch(name, side_effect=RuntimeError('Execution forbidden: ' + name))))
        require(artifact(SCOPE)['sha256'] == SCOPE_SHA, 'Reviewed linked-stage scope changed')
        scope = read(SCOPE)
        require(scope['schema'] == 'zerosis.world_camera_civilian_linked_scope.v1' and
                scope['original_game_new_mod_test_hold'] is True and scope['retail_mod_test_hold_active'] is True and
                scope['execution_allowed'] is False and scope['default_promoted'] is False,
                'Source-only private preparation hold differs')
        require(isinstance(scope['protected_artifacts'], list), 'Expected the scoped protection list')
        invocation_path = STAGE / 'build_invocation.json'
        invocation = read(invocation_path)
        require(invocation['status'] == 'PASS' and type(invocation['exit_code']) is int and
                invocation['exit_code'] == 0 and invocation['result']['build_id'] == args.build_id,
                'Private preparation requires this stage successful actual build')
        report_path = PROJECT / f'evidence/ui_window_host/{args.build_id}/build_result.json'
        build = read(report_path)
        require(build['build_id'] == args.build_id and build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
                build['source_inputs_unchanged'] is True and build['provider_inputs_unchanged'] is True and
                build['error'] is None, 'Actual Host build did not pass')
        attestation_path = STAGE / f'attestation_{args.build_id}.json'
        attestation = read(attestation_path)
        require(attestation['schema'] == 'zerosis.world_camera_civilian_linked_pe_attestation.v1' and
                attestation['status'] == 'PASS' and attestation['build_id'] == args.build_id and
                attestation['inputs_unchanged'] is True and attestation['exact_final_dependency_closure'] is True and
                attestation['actual_pe_inspected'] is True, 'Current linked PE attestation did not pass')
        require(verify(attestation['build_report']) == artifact(report_path) and
                verify(attestation['candidate_scope']) == artifact(SCOPE), 'PE report/scope lineage differs')
        exe_ref = verify(attestation['executable'])
        require(exe_ref['path'] == build['executable']['path'] and exe_ref['sha256'] == build['executable']['sha256'],
                'Attested executable differs from the actual build')
        require(key(exe_ref['path']) == key(PROJECT / 'Build/UiWindowHost' / args.build_id / 'final/ZeroSisHost_x64.exe'),
                'Attested executable escaped this exact Host build')
        require(all(attestation[name] is False for name in ('host_executed', 'gamecore_loaded', 'dll_loaded',
                'hwnd_created', 'mods_or_user_saves_accessed', 'retail_user_settings_accessed', 'default_promoted',
                'native_camera_controls_verified', 'native_civilian_rendering_verified',
                'native_binding_execution_verified', 'native_overwrite_verified', 'retail_save_mod_compatibility_verified',
                'unit_package_embedded_in_pe', 'native_unit_package_consumption_verified')) and
                attestation['game_process_queries'] == 0, 'Attestation exceeds the static no-execution boundary')
        unit_inputs = scope['current_unit_assets']
        require(set(unit_inputs) == {'binary', 'manifest', 'preparation_contract'}, 'Wrong scoped civilian inputs')
        require(attestation['external_unit_assets'] == unit_inputs, 'PE proof names a different external unit package')
        unit_refs = {name: verify(row) for name, row in unit_inputs.items()}
        require(unit_refs['binary']['sha256'] == PACKAGE_SHA and unit_refs['manifest']['sha256'] == MANIFEST_SHA,
                'The new three-art civilian package differs')
        unit_manifest = read(Path(unit_refs['manifest']['path']))
        require(unit_manifest['status'] == 'PASS_ORIGINAL_UNIT_PACKAGE' and
                verify(unit_manifest['package']) == unit_refs['binary'] and
                unit_manifest['art_tags'] == ['ART_DEF_UNIT__WARRIOR', 'ART_DEF_UNIT__SETTLER', 'ART_DEF_UNIT__WORKER'],
                'Wrong external unit asset identity/catalog')
        policy = STAGE / 'PolicyInfo.ini'
        require(ordinary_project_file(policy).read_bytes() == POLICY_BYTES, 'Expected the parent-created private PolicyInfo file')
        require(artifact(RUNNER)['sha256'] == RUNNER_SHA, 'Current interactive runner changed')
        helper_refs = [artifact(PROJECT / name) for name in HELPER_PINS]
        require(all(row['sha256'] == HELPER_PINS[str(Path(row['path']).relative_to(PROJECT)).replace('\\', '/')]
                    for row in helper_refs), 'Immutable cache/animation helper changed')
        frontend = {name: artifact(PROJECT / 'tools' / name) for name in TOOLS}
        provenance = {'wrapper': artifact(Path(__file__).absolute()), 'stage_common': artifact(STAGE / 'run_stage.py'),
                      'preserved_guard': artifact(PRESERVED), 'preserved_common': verify(scope['common_helper']),
                      'runner': artifact(RUNNER), 'scope': artifact(SCOPE), 'build_invocation': artifact(invocation_path),
                      'pe_attestation': artifact(attestation_path)}
        require(provenance['stage_common']['sha256'] == STAGE_COMMON_SHA, 'Approved stage parent changed')
        protected = list({row['path']: row for row in [*scope['protected_artifacts'], *provenance.values(),
            artifact(report_path), exe_ref, artifact(policy), *unit_refs.values(), *frontend.values(), *helper_refs]}.values())
        for row in protected:
            verify(row)
        legacy = load_preserved()
        legacy.install_audit_guard(denied)
        stack.enter_context(patch.object(legacy, 'PROJECT', PROJECT))
        stack.enter_context(patch.object(legacy, 'STAGE', STAGE))
        sys.path.insert(0, str(PROJECT / 'tools'))
        import run_interactive_game as runner
        require(key(runner.__file__) == key(RUNNER) and artifact(RUNNER)['sha256'] == RUNNER_SHA,
                'Imported a different interactive runner')
        command = [str(RUNNER), '--host-build', str(report_path), '--unit-assets-manifest', unit_refs['manifest']['path'],
                   '--policy-info-settings', str(policy), '--language', 'ko_KR', '--top-panel',
                   '--action-info-panel', '--notification-panel']
        runtime_parent, evidence_parent = PROJECT / 'Build/InteractiveGameRuntime', PROJECT / 'evidence/interactive_game'
        before_runtime = {row.name for row in runtime_parent.iterdir()}
        before_evidence = {row.name for row in evidence_parent.iterdir()}
        write_new(STAGE / 'preparation_started.json', {'utc': datetime.now(timezone.utc).isoformat(),
            'argv': command, 'provenance': provenance, 'protected': protected,
            'runtime_ids_before': sorted(before_runtime), 'evidence_ids_before': sorted(before_evidence),
            'preserved_guard_main_called': False, 'retail_mod_test_hold_active': True})
        stdout, stderr, actual_argv = io.StringIO(), io.StringIO(), None
        try:
            with patch.object(sys, 'argv', command.copy()), redirect_stdout(stdout), redirect_stderr(stderr):
                actual_argv = list(sys.argv)
                code = runner.main()
                require(code in (None, 0), 'Private runtime materializer failed')
        finally:
            for name, captured in (('materializer.stdout.log', stdout), ('materializer.stderr.log', stderr)):
                with (STAGE / name).open('x', encoding='utf-8') as stream:
                    stream.write(captured.getvalue())
        require(actual_argv == command and not denied and all(guard.call_count == 0 for guard in guards),
                'Runner arguments or no-execution guard differ')
        summaries = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith('{')]
        require(len(summaries) == 1 and summaries[0]['status'] == 'PRIVATE_CONTINUOUS_GAME_PREPARED', 'Missing preparation-only return')
        run_id = summaries[0]['run_id']
        require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id) and
                {row.name for row in runtime_parent.iterdir()} - before_runtime == {run_id} and
                {row.name for row in evidence_parent.iterdir()} - before_evidence == {run_id}, 'Unexpected new private run inventory')
        runtime, evidence = runtime_parent / run_id, evidence_parent / run_id
        request_path = evidence / 'request.json'
        request = read(request_path)
        require(request['run_id'] == run_id and request['smoke'] is False and request['resume_from'] is None and
                request['ui_support_from_run'] is None and request['input_profile'] == 'MANUAL_CONTINUOUS_GAME_LOOP' and
                request['top_panel'] is True and request['action_info_panel'] is True and request['notification_panel'] is True,
                'Wrong private no-smoke/no-resume preparation profile')
        options = request['policy_info_options']
        require(options['origin'] == 'EXPLICIT_POLICY_SETTINGS_READ_ONLY' and options['original_user_settings'] is None and
                options['policy_info'] == 1 and options['source'] == artifact(policy), 'Wrong private policy source')
        require(request['host_runtime_validation']['scope'] == 'RETAINED_HOST_RUNTIME_INPUTS' and
                request['provenance']['host_build']['sha256'] == artifact(report_path)['sha256'], 'Wrong actual Host provenance')
        runtime_host = [row for row in request['runtime_inputs'] if Path(row['path']).name == 'ZeroSisHost_x64.exe']
        runtime_unit = [row for row in request['runtime_inputs'] if Path(row['path']).name == 'unit-assets.bin']
        require(len(runtime_host) == len(runtime_unit) == 1 and runtime_host[0]['sha256'] == exe_ref['sha256'] and
                runtime_unit[0]['sha256'] == PACKAGE_SHA, 'Runtime Host/unit inputs differ from the attested candidate')
        unit = request['unit_assets']
        require(unit['status'] == 'PASS_ORIGINAL_UNIT_PACKAGE' and unit['reused_from_run'] is None and
                verify(unit['package']) == artifact(runtime / 'unit-assets.bin') and unit['package']['sha256'] == PACKAGE_SHA and
                key(unit['source_package']['original_path']) == key(unit_refs['binary']['path']) and
                unit['source_package']['sha256'] == PACKAGE_SHA and
                key(unit['source_manifest']['original_path']) == key(unit_refs['manifest']['path']) and
                unit['source_manifest']['sha256'] == MANIFEST_SHA and
                key(unit['manifest']['path']) == key(evidence / 'unit-assets-source-manifest.json') and
                verify(unit['manifest'])['sha256'] == MANIFEST_SHA and
                unit['manifest']['bytes'] == unit_refs['manifest']['bytes'], 'Source/runtime/copied unit manifest lineage differs')
        require(not (runtime / 'sessions').exists() and not any((evidence / name).exists()
                for name in ('attempt.json', 'result.json', 'driver_result.json')), 'Native execution output unexpectedly exists')
        runner.check_artifacts(request)
        for row in protected:
            verify(row)
        methods = request['materializations']
        prepared = {'schema': 'zerosis.world_camera_civilian.private_prepared.v1', 'status': 'PREPARED_NOT_EXECUTED',
            'utc': datetime.now(timezone.utc).isoformat(), 'run_id': run_id, 'host_build_id': args.build_id,
            'request': artifact(request_path), 'host_build': artifact(report_path), 'guard': provenance['wrapper'],
            'actual_runner_argv': actual_argv, 'started': artifact(STAGE / 'preparation_started.json'),
            'runtime_executable': runtime_host[0], 'unit_assets': unit, 'external_unit_inputs': unit_refs,
            'protected': protected, 'current_python_support_count': len(TOOLS),
            'runtime_inputs': len(request['runtime_inputs']),
            'hardlinks': sum(row.get('materialization_method') == 'hardlink' for row in methods),
            'cache_hits': sum(row.get('cache_method') == 'cache-hit' for row in methods),
            'new_cache_objects': sum(str(row.get('cache_method', '')).startswith('cache-created') for row in methods),
            'forbidden_access_attempts': denied, 'native_process_or_ctypes_calls': sum(guard.call_count for guard in guards),
            'native_execution_outputs_absent': True, 'retail_mod_test_hold_active': True,
            'host_gamecore_hwnd_executed': False, 'retail_user_state_or_processes_accessed': False,
            'default_release_promoted': False, 'native_camera_or_civilian_acceptance': False,
            'terrain_preparation_policy': 'Unmodified runner rereads original terrain FPK hashes before/after and reuses its content-addressed package; no whole input copy is created.'}
        write_new(STAGE / 'prepared.json', prepared)
        helpers = SimpleNamespace(artifact=artifact, read=read, require=require)
        identity = legacy.verify_private_identity(helpers, args.build_id)
        require(len(request['runtime_inputs']) == 24 and prepared['hardlinks'] == 15 and
                len(identity['private_databases']) == 2 and len(identity['current_frozen_manifest_support']) == 5,
                'Expected exactly 24 sealed inputs, 15 immutable links, two private databases and five frontend files')
        require(not denied and all(guard.call_count == 0 for guard in guards), 'Forbidden operation during identity audit')
        for row in protected:
            verify(row)
        identity.update(schema='zerosis.world_camera_civilian.private_preparation_identity.v1',
            status='PASS_PREPARED_NOT_EXECUTED', utc=datetime.now(timezone.utc).isoformat(),
            provenance=provenance, actual_runner_argv=actual_argv, external_unit_inputs=unit_refs,
            runtime_unit_assets=unit, inputs_unchanged=True, forbidden_access_attempts=denied,
            outer_process_or_ctypes_calls=sum(guard.call_count for guard in guards),
            preserved_guard_and_reports_unmodified=True, preserved_guard_main_called=False,
            retail_mod_test_hold_active=True, host_gamecore_hwnd_executed=False,
            retail_user_state_or_processes_accessed=False, default_release_promoted=False,
            native_camera_controls_verified=False, native_civilian_rendering_verified=False,
            native_overwrite_verified=False, retail_save_mod_compatibility_verified=False,
            terrain_preparation_policy=prepared['terrain_preparation_policy'])
        audit_path = STAGE / 'preparation_identity_audit.json'
        write_new(audit_path, identity)
        print(json.dumps({'status': identity['status'], 'run_id': run_id, 'host_build_id': args.build_id,
            'runtime_inputs': prepared['runtime_inputs'], 'hardlinks': prepared['hardlinks'],
            'private_databases': len(identity['private_databases']), 'unit_package_sha256': PACKAGE_SHA,
            'cache_hits': prepared['cache_hits'], 'new_cache_objects': prepared['new_cache_objects'],
            'identity_audit': artifact(audit_path)}))


if __name__ == '__main__':
    main()
