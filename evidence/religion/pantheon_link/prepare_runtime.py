"""Prepare one scoped private runtime through the unchanged production runner."""
from contextlib import ExitStack, redirect_stderr, redirect_stdout
import ctypes
import hashlib
import importlib.util
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
LINK = Path(__file__).absolute().parent
STAGE = LINK / 'runtime'
HELPER = PROJECT / 'evidence/concurrency/runtime_configuration/prepare_candidate.py'
HELPER_SHA = 'fc2d186c5d9ace093ff083aea1c1b3d08bb2a42ca47f51de3961ebd850728999'
TOOLS = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
         'ui_bitmap_fonts.py', 'civ5_ui_assets.py', 'found_value_runtime_options.py')

def load_helpers():
    if hashlib.sha256(HELPER.read_bytes()).hexdigest() != HELPER_SHA:
        raise RuntimeError('The preserved runtime helper changed')
    spec = importlib.util.spec_from_file_location('_pantheon_runtime_helpers', HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot load the exact preserved runtime helper')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def install_guard(denied):
    roots = [os.path.normcase(os.path.abspath(path)) for path in (
        r'C:\Users\home\OneDrive\Documents\My Games', r'C:\Users\home\Documents\My Games')]
    def audit(event, args):
        if event in ('open', 'os.listdir', 'os.scandir', 'os.chdir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
            target = os.path.normcase(os.path.abspath(os.fsdecode(args[0])))
            target = target[4:] if target.startswith('\\\\?\\') else target
            if any(target == root or target.startswith(root + os.sep) for root in roots):
                denied.append(event)
                raise RuntimeError('Retail user files are outside this preparation')
        if event.startswith(('subprocess.', 'os.exec', 'os.spawn')) or event in (
                'os.system', 'os.startfile', 'os.startfile/2', 'os.posix_spawn', 'os.posix_spawnp', 'ctypes.dlopen'):
            denied.append(event)
            raise RuntimeError('Processes and ctypes library loading are forbidden')
    sys.addaudithook(audit)

def main():
    denied, guards = [], []
    install_guard(denied)
    with ExitStack() as stack:
        for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL'):
            guards.append(stack.enter_context(patch(name, side_effect=RuntimeError('Execution forbidden: ' + name))))
        helper = load_helpers()
        require, read, artifact = helper.require, helper.read, helper.artifact
        stack.enter_context(patch.object(helper, 'STAGE', STAGE))
        scope_path = STAGE / 'scope.json'
        scope = read(scope_path)
        require(scope['schema'] == 'zerosis.pantheon_runtime_preparation.scope.v1', 'Wrong preparation scope')
        require(scope['private_preparation_allowed'] is True and scope['retail_mod_test_hold_active'] is True and
                all(scope[name] is False for name in ('native_host_gamecore_hwnd_execution_allowed',
                    'retail_user_state_or_game_process_access_allowed', 'default_promotion_allowed')), 'Wrong execution boundary')
        build_id = scope['host_build_id']
        require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', build_id), 'Malformed Host build ID')
        expected = {'helper_module': HELPER, 'preserved_identity_guard': helper.PRESERVED,
                    'preparation_guard': Path(__file__).absolute(), 'private_policy': HELPER.parent / 'PolicyInfo.ini',
                    'link_scope': LINK / 'scope.json', 'link_retry_scope': LINK / 'retry_02_scope.json',
                    'host_build': PROJECT / f'evidence/ui_window_host/{build_id}/build_result.json',
                    'pe_attestation': LINK / f'attestation_{build_id}.json'}
        require(all(helper.key(scope[name]['path']) == helper.key(path) for name, path in expected.items()), 'Scoped path differs')
        link, retry, build, pe, prior = [read(scope[name]['path']) for name in
                                       ('link_scope', 'link_retry_scope', 'host_build', 'pe_attestation', 'existing_runtime')]
        require(scope['link_scope']['sha256'] == '747c8710329e4b2a3a3905dc90b88ce9b9e2f106a0eed0c9ac918f35e6c0f99a' and
                retry['parent_scope'] == scope['link_scope'], 'Wrong preserved link scope')
        require(build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build['build_id'] == build_id and build['error'] is None and
                pe['schema'] == 'zerosis.pantheon_linked_pe_attestation.v1' and pe['status'] == 'PASS' and pe['build_id'] == build_id and
                pe['actual_pe_inspected'] is True and pe['pe_catalog']['entry_count'] == 64 and
                all(pe[name] is False for name in ('host_executed', 'gamecore_loaded', 'hwnd_created', 'default_promoted')), 'Host/PE is not accepted')
        require(len(link['all_source_and_test_seals']) == 15 and len(link['protected_artifacts']) == 466 and
                len(link['original_assets']) == 2 and len(retry['additional_protected_artifacts']) == 14, 'Wrong parent preservation ledger')
        source_inputs = scope['source_inputs']
        require({'tools/' + name for name in (*TOOLS, 'run_interactive_game.py')} <= set(source_inputs), 'Missing current Python sources')
        require(all(helper.key(PROJECT / relative) == helper.key(row['path']) for relative, row in source_inputs.items()), 'Source mapping differs')
        rows = [artifact(scope_path), *[scope[name] for name in (*expected, 'existing_runtime', 'unit_manifest', 'unit_package')],
                *source_inputs.values(), *scope['additional_protected_artifacts'], *link['all_source_and_test_seals'].values(),
                *link['protected_artifacts'], *link['original_assets'], link['source_stage'], *retry['additional_protected_artifacts'],
                *retry['prior_attempt_artifacts'], *retry['repair_artifacts'], *retry['new_source_snapshots_before_retry'],
                *retry['previous_failed_attempt']['artifacts'], *retry['hardlink_permission_probes'].values(), *prior['runtime_inputs']]
        rows.extend(row['frozen'] for row in prior['interactive_ui_support_inventory']['tools'].values())
        rows.extend(row for row in prior['launcher_control_metadata'].values() if helper.key(row['path']).startswith(helper.key(PROJECT) + os.sep))
        mutable = {helper.key(path) for path in link['mutable_derived_paths']}
        def seal(row):
            path = Path(row['path'])
            if helper.key(path).startswith(helper.key(PROJECT) + os.sep):
                return helper.verify(row) if 'bytes' in row else helper.verify_digest(row, path)
            require(row in link['original_assets'], 'External input is not one of the two declared originals')
            before = path.stat()
            require(stat.S_ISREG(before.st_mode) and all(not item.lstat().st_file_attributes & 0x400 for item in (path, *path.parents)), 'Original is not ordinary')
            with path.open('rb') as stream:
                require(helper.stable(os.fstat(stream.fileno())) == helper.stable(before), 'Original changed while opening')
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
                require(helper.stable(os.fstat(stream.fileno())) == helper.stable(before), 'Original changed while hashing')
            require(helper.stable(path.stat()) == helper.stable(before) and before.st_size == row['bytes'] and digest == row['sha256'], 'Original identity differs')
            return row
        protected = [seal(row) for path, row in {helper.key(row['path']): row for row in rows}.items() if path not in mutable]
        require(Path(scope['private_policy']['path']).read_bytes() == helper.POLICY_BYTES, 'Private PolicyInfo input differs')
        require(scope['unit_package']['sha256'] == 'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573', 'Wrong original unit package')
        outputs = ('preparation_started.json', 'prepared.json', 'preparation_identity_audit.json', 'materializer.stdout.log', 'materializer.stderr.log')
        require(all(not os.path.lexists(STAGE / name) for name in outputs), 'Inspect the existing preparation instead of repeating it')
        legacy = helper.load_preserved()
        for name, value in (('PROJECT', PROJECT), ('STAGE', STAGE), ('TOOLS', TOOLS)):
            stack.enter_context(patch.object(legacy, name, value))
        stack.enter_context(patch.object(sys, 'path', [str(PROJECT / 'tools'), *sys.path]))
        import found_value_runtime_options as options
        import run_interactive_game as runner
        require(helper.key(runner.__file__) == helper.key(source_inputs['tools/run_interactive_game.py']['path']) and
                helper.key(options.__file__) == helper.key(source_inputs['tools/found_value_runtime_options.py']['path']), 'Wrong imported tools')
        require(tuple(runner.FOUND_VALUE_SUPPORT_TOOLS) == TOOLS, 'Runner frontend closure differs')
        command = [str(PROJECT / 'tools/run_interactive_game.py'), '--host-build', scope['host_build']['path'],
                   '--unit-assets-manifest', scope['unit_manifest']['path'], '--policy-info-settings', scope['private_policy']['path'],
                   '--language', 'ko_KR', '--top-panel', '--action-info-panel', '--notification-panel']
        parents = [PROJECT / 'Build/InteractiveGameRuntime', PROJECT / 'evidence/interactive_game']
        old_ids = [{item.name for item in path.iterdir()} for path in parents]
        helper.write_new(STAGE / 'preparation_started.json', {'schema': 'zerosis.pantheon_runtime_preparation.started.v1',
            'scope': artifact(scope_path), 'argv': command, 'host_build_id': build_id, 'runtime_ids_before': sorted(old_ids[0]),
            'evidence_ids_before': sorted(old_ids[1]), 'preserved_helper_main_called': False})
        stdout, stderr = helper.Capture(), helper.Capture()
        try:
            with patch.object(sys, 'argv', command.copy()), redirect_stdout(stdout), redirect_stderr(stderr), \
                    patch.object(runner, 'select_found_value_policy', wraps=runner.select_found_value_policy) as selection:
                actual_argv = list(sys.argv)
                code = runner.main()
                require(code in (None, 0) and selection.call_count == 1, 'Actual preparation/policy selection failed')
        finally:
            for name, captured in (('materializer.stdout.log', stdout), ('materializer.stderr.log', stderr)):
                with (STAGE / name).open('x', encoding='utf-8') as stream:
                    stream.write(captured.getvalue())
        summaries = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith('{')]
        require(len(summaries) == 1 and summaries[0]['status'] == 'PRIVATE_CONTINUOUS_GAME_PREPARED', 'No unique preparation-only result')
        run_id = summaries[0]['run_id']
        require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id) and actual_argv == command and
                all({item.name for item in path.iterdir()} - before == {run_id} for path, before in zip(parents, old_ids)), 'Unexpected runtime allocation/argv')
        runtime, evidence = [path / run_id for path in parents]
        request_path = evidence / 'request.json'
        request = read(request_path)
        require(request['provenance']['host_build']['sha256'] == scope['host_build']['sha256'] and
                request['provenance']['frozen_runner']['sha256'] == source_inputs['tools/run_interactive_game.py']['sha256'],
                'Prepared Host/runner provenance differs')
        current = {Path(row['path']).name: row for row in request['runtime_inputs']}
        old = {Path(row['path']).name: row for row in prior['runtime_inputs']}
        require(len(current) == len(old) == 24 and current.keys() == old.keys() and
                {name for name in current if current[name]['sha256'] != old[name]['sha256']} == {'ZeroSisHost_x64.exe', 'bundle.manifest'}, 'Unexpected R9 input delta')
        require(current['ZeroSisHost_x64.exe']['sha256'] == build['executable']['sha256'] == pe['executable']['sha256'] and
                helper.key(current['ZeroSisHost_x64.exe']['source']) == helper.key(build['executable']['path']), 'Runtime Host is not the accepted new PE')
        manifest = 'ZEROSIS_HOST_BUNDLE_V4\n' + ''.join(Path(row['path']).name + '|' + row['sha256'] + '\n'
                    for row in request['runtime_inputs'] if Path(row['path']).name != 'bundle.manifest')
        require((runtime / 'bundle.manifest').read_text(encoding='ascii') == manifest, 'Runtime bundle manifest differs')
        require(request['run_id'] == run_id and request['input_profile'] == 'MANUAL_CONTINUOUS_GAME_LOOP' and
                all(request[name] is True for name in ('top_panel', 'action_info_panel', 'notification_panel')) and
                request['stage_or_mods_changed'] is False and request['host_runtime_validation']['scope'] == 'RETAINED_HOST_RUNTIME_INPUTS', 'Wrong preparation profile')
        policy = request['policy_info_options']
        require(policy['origin'] == 'EXPLICIT_POLICY_SETTINGS_READ_ONLY' and policy['original_user_settings'] is None and
                policy['original_policy_info'] is None and policy['policy_info'] == 1 and policy['run_id'] is None, 'Wrong policy input')
        helper.annotation(policy['source'], scope['private_policy'])
        helper.annotation(policy['settings_input'], scope['private_policy'])
        helper.annotation(request['unit_assets']['source_package'], scope['unit_package'])
        helper.annotation(request['unit_assets']['source_manifest'], scope['unit_manifest'])
        require(request['unit_assets']['reused_from_run'] is None, 'Unexpected reused unit runtime')
        bridge = helper.validate_policy_records(request, runtime, evidence, options)
        runner.check_artifacts(request)
        methods = request['materializations']
        hits = sum(row.get('cache_method') == 'cache-hit' for row in methods)
        created = sum(str(row.get('cache_method', '')).startswith('cache-created') for row in methods)
        links = sum(row.get('materialization_method') == 'hardlink' for row in methods)
        require(links == 15 and (hits, created) in ((14, 1), (15, 0)), 'Unexpected immutable-cache observations')
        imported = {relative: str(sys.modules[Path(relative).stem].__file__) for relative in source_inputs if relative.startswith('tools/') and Path(relative).stem in sys.modules}
        require(all(helper.key(path) == helper.key(source_inputs[relative]['path']) for relative, path in imported.items()), 'Imported helper mapping differs')
        require(not denied and all(item.call_count == 0 for item in guards), 'A forbidden operation was attempted')
        require([seal(row) for row in protected] == protected, 'Protected input changed')
        helper.write_new(STAGE / 'prepared.json', {'status': 'PREPARED_NOT_EXECUTED', 'host_build_id': build_id, 'run_id': run_id,
            'request': artifact(request_path), 'host_build': artifact(scope['host_build']['path']), 'runtime_inputs': len(current),
            'hardlinks': links, 'cache_hits': hits, 'new_cache_objects': created, 'native_process_or_ctypes_calls': 0, 'forbidden_access_attempts': denied})
        identity = legacy.verify_private_identity(SimpleNamespace(artifact=artifact, read=read, require=require), build_id)
        require(len(identity['private_databases']) == 2 and len(identity['current_frozen_manifest_support']) == 6 and
                [seal(row) for row in protected] == protected and not denied and all(item.call_count == 0 for item in guards), 'Final identity/preservation failed')
        identity.update(schema='zerosis.pantheon_runtime_preparation.identity.v1', status='PASS_PREPARED_NOT_EXECUTED',
            scope=artifact(scope_path), actual_runner_argv=actual_argv, imported_sources=imported, policy_bridge=bridge,
            cache_hits=hits, new_cache_objects=created, protected_input_count=len(protected), inputs_unchanged=True,
            protected_ledger_sha256=hashlib.sha256(json.dumps(protected, sort_keys=True).encode('utf-8')).hexdigest(),
            preserved_helper_main_called=False, preserved_guard_main_called=False, forbidden_access_attempts=denied,
            host_executed=False, gamecore_loaded=False, hwnd_created=False, retail_user_state_or_game_processes_accessed=False,
            game_process_queries=0, default_promoted=False, retail_mod_test_hold_active=True, sdk_consumption_verified=False, full_engine_goal_complete=False)
        audit_path = STAGE / 'preparation_identity_audit.json'
        helper.write_new(audit_path, identity)
        print(json.dumps({'status': identity['status'], 'run_id': run_id, 'runtime_inputs': len(current), 'hardlinks': links,
                          'cache_hits': hits, 'new_cache_objects': created, 'identity': artifact(audit_path)}))

if __name__ == '__main__':
    main()
