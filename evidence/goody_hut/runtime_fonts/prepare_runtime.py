"""Prepare one B11 private runtime, with its owned-font frontend binding.

The production runner supplies the real result. No native candidate is executed.
"""
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
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
OWNED = PROJECT / 'evidence/goody_hut/owned_fonts'
HELPER = PROJECT / 'evidence/concurrency/runtime_configuration/prepare_candidate.py'
HELPER_SHA = 'fc2d186c5d9ace093ff083aea1c1b3d08bb2a42ca47f51de3961ebd850728999'
LEGACY_SHA = 'f28dbf303b8e5ae653fff70a923c86c62a77e0fbd64c92633eefc619d6039d2f'
TOOLS = ('interactive_ui_driver.py', 'render_ui_popup.py', 'ui_pixel_scene.py',
         'ui_bitmap_fonts.py', 'civ5_ui_assets.py', 'found_value_runtime_options.py')
OUTPUTS = ('preparation_started.json', 'prepared.json', 'preparation_identity_audit.json',
           'materializer.stdout.log', 'materializer.stderr.log')


def key(path):
    return os.path.normcase(os.path.abspath(path))


def within(path, root):
    return key(path) == key(root) or key(path).startswith(key(root) + os.sep)


def reuse_existing_directory_mkdir(directory, require):
    directory = Path(directory)
    require(directory.is_absolute() and directory.resolve(strict=True) == directory and
            all(stat.S_ISDIR(p.lstat().st_mode) and not p.lstat().st_file_attributes & 0x400
                for p in (directory, *directory.parents)), 'Noncanonical or reparse shared directory')

    def identity():
        info = directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400,
                'Shared directory was replaced with a non-directory or reparse point')
        return info.st_dev, info.st_ino, info.st_mtime_ns

    before = identity()
    original_mkdir = Path.mkdir
    observation = dict(path=str(directory), identity_before=before, mkdir_noop_calls=0)

    def mkdir(path, mode=0o777, parents=False, exist_ok=False):
        if key(path) != key(directory):
            return original_mkdir(path, mode=mode, parents=parents, exist_ok=exist_ok)
        require(mode == 0o777 and parents is True and exist_ok is True and
                Path(path).resolve(strict=True) == directory and identity() == before,
                'Unexpected shared-directory mkdir call or changed directory identity')
        observation['mkdir_noop_calls'] += 1
        return None

    return mkdir, observation, identity


def install_guard(denied):
    retail = (r'C:\Users\home\OneDrive\Documents\My Games', r'C:\Users\home\Documents\My Games')
    write_roots = tuple(PROJECT / name for name in ('Build/InteractiveGameRuntime', 'evidence/interactive_game', 'Build/RuntimeInputCache'))

    def owned_write(path):
        return key(path) in {key(STAGE / name) for name in OUTPUTS} or any(within(path, root) for root in write_roots)

    def audit(event, args):
        if event in ('open', 'os.listdir', 'os.scandir', 'os.chdir') and args and isinstance(args[0], (str, bytes, os.PathLike)):
            target = key(os.fsdecode(args[0])).removeprefix('\\\\?\\')
            if any(within(target, root) for root in retail):
                denied.append(event);raise RuntimeError('Retail user state is outside this preparation')
            if event == 'open':
                mode, flags = args[1:3]
                writing = isinstance(mode, str) and any(c in mode for c in 'wax+') or (
                    type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                if writing and not owned_write(target):
                    denied.append(event);raise RuntimeError('Preparation write escaped owned runtime outputs')
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.chmod', 'os.utime', 'os.link', 'os.symlink', 'os.rename'):
            paths = args[:2] if event in ('os.rename', 'os.link', 'os.symlink') else args[:1]
            if any(isinstance(path, (str, bytes, os.PathLike)) and not owned_write(os.fsdecode(path)) for path in paths):
                denied.append(event);raise RuntimeError('Preparation mutation escaped owned runtime outputs')
        if event.startswith(('subprocess.', 'os.exec', 'os.spawn', 'ctypes.dlopen', 'socket.', 'urllib.', 'http.client.')) or event in (
                'os.system', 'os.startfile', 'os.startfile/2', 'os.posix_spawn', 'os.posix_spawnp', 'os.kill', 'os.killpg', 'os.fork', 'os.forkpty'):
            denied.append(event);raise RuntimeError('Processes, native loading and network access are forbidden')
    sys.addaudithook(audit)


def load_helpers():
    if hashlib.sha256(HELPER.read_bytes()).hexdigest() != HELPER_SHA:
        raise RuntimeError('The preserved runtime helper changed')
    spec = importlib.util.spec_from_file_location('_goody_font_runtime_helpers', HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError('Cannot load the exact runtime helper')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def font_contract(scope, capture, helper):
    require = helper.require
    root = Path(scope['font_asset_root'])
    require(root.is_absolute() and root.parent == PROJECT / 'Build/SharedUiFontInputs' and
            re.fullmatch('[0-9a-f]{64}', root.name) and root.resolve(strict=True) == root and
            not root.lstat().st_file_attributes & 0x400, 'Owned font root differs')
    rows = scope['font_inputs']
    require(capture['schema'] == 'zerosis.ui.owned_font_inputs_capture.v1' and capture['status'] == 'PASS' and
            capture['cache_root'] == str(root) and capture['content_id'] == root.name and capture['selected_files'] == 15 and
            capture['source_and_cache_byte_identical'] is True and capture['source_inputs_unchanged'] is True and
            capture['source_file_hardlinks_created'] == 0 and capture['original_game_files_modified'] is False,
            'Owned font capture did not prove independent exact inputs')
    ordered = sorted(rows, key=lambda row: Path(row['path']).relative_to(root).as_posix())
    require(len(rows) == len({key(row['path']) for row in rows}) == 15 and
            {key(row['path']): row for row in rows} == {key(row['path']): row for row in capture['owned_inputs']} and
            capture['profile'] == scope['font_profile'] and capture['owned_profile']['asset_root'] == str(root) and
            capture['owned_profile']['profile_id'] == scope['font_profile_id'], 'Scope and capture font/profile refs differ')
    inventory = [(Path(row['path']).relative_to(root).as_posix(), row['bytes'], row['sha256']) for row in ordered]
    original_root = Path(capture['original_profile']['asset_root'])
    original_inventory = sorted((Path(row['path']).relative_to(original_root).as_posix(), row['bytes'], row['sha256'])
                                for row in capture['original_inputs'])
    require(inventory == original_inventory and hashlib.sha256(json.dumps(inventory, separators=(',', ':'),
            ensure_ascii=True).encode('ascii')).hexdigest() == root.name, 'Original/owned relative inventory differs')
    expected = {'Assets/UI/ColorAtlas.xml', *('Assets/UI/Fonts/Tw Cent MT/TwCenMT%d.ggxml' % size for size in (14, 16, 18, 20, 22, 24)),
                *('kTwCenMT%d%s.dds' % (size, suffix) for size in (14, 18, 20, 22) for suffix in ('', 'Shadow'))}
    require({row[0] for row in inventory} == expected, 'Owned font selection is not six GGXML, eight DDS and one color atlas')
    return dict(schema='zerosis.ui.owned_font_binding.v1', asset_root=str(root), profile_id=scope['font_profile_id'],
                cache_content_id=root.name, inputs=ordered)


def main():
    incident = json.loads((STAGE / 'system_freeze_hold.json').read_text(encoding='utf-8'))
    if type(incident) is not dict or incident.get('engine_build_preparation_and_large_io_stopped') is not False:
        raise RuntimeError('Original Windows freeze hold is active; heavy engine work is forbidden')
    denied, guards = [], []
    install_guard(denied)
    with ExitStack() as stack:
        for name in ('subprocess.Popen', 'os.startfile', 'ctypes.CDLL', 'ctypes.WinDLL'):
            guards.append(stack.enter_context(patch(name, side_effect=RuntimeError('Execution forbidden: ' + name))))
        helper = load_helpers()
        require, read, artifact = helper.require, helper.read, helper.artifact
        require(not sys.flags.optimize and len(sys.argv) == 1 and STAGE == PROJECT / 'evidence/goody_hut/runtime_fonts', 'Wrong unoptimized stage or unexpected CLI arguments')
        stack.enter_context(patch.object(helper, 'STAGE', STAGE))
        scope_path = STAGE / 'scope.json'
        scope = read(scope_path)
        require(scope['schema'] == 'zerosis.goody_hut.font_runtime_preparation.scope.v1' and
                scope['private_preparation_allowed'] is True and scope['retail_mod_test_hold_active'] is True and
                all(scope[name] is False for name in ('native_host_gamecore_hwnd_execution_allowed',
                    'retail_user_state_or_game_process_access_allowed', 'default_promotion_allowed', 'full_engine_goal_complete')),
                'Wrong private preparation authorization')
        build_id = scope['host_build_id']
        require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', build_id), 'Malformed Host build ID')
        paths = {'helper_module': HELPER, 'preserved_identity_guard': helper.PRESERVED,
                 'preparation_guard': Path(__file__).absolute(), 'host_build': PROJECT / f'evidence/ui_window_host/{build_id}/build_result.json',
                 'pe_attestation': OWNED / 'attestation_retry.json', 'raw_objects_retired': OWNED / 'build_objects_retired.json',
                 'owned_font_capture': OWNED / 'capture_result.json', 'font_profile': PROJECT / 'Source/Assets/UI/font_input_profile.json',
                 'private_policy': HELPER.parent / 'PolicyInfo.ini', 'expected_inline_icons': PROJECT / 'evidence/ui_popup/assets/inline_icons.json'}
        require(all(key(scope[name]['path']) == key(path) for name, path in paths.items()), 'Scoped input path differs')
        require(scope['helper_module']['sha256'] == HELPER_SHA and scope['preserved_identity_guard']['sha256'] == LEGACY_SHA,
                'Preserved helper pin differs')
        source_inputs = scope['source_inputs']
        require(set(source_inputs) == {'tools/' + name for name in (*TOOLS, 'run_interactive_game.py')} and
                all(key(PROJECT / relative) == key(row['path']) for relative, row in source_inputs.items()), 'Wrong exact seven-source frontend closure')

        def seal(row):
            return helper.verify(row) if 'bytes' in row else helper.verify_digest(row, row['path'])

        top = [scope[name] for name in (*paths, 'existing_runtime', 'unit_manifest', 'unit_package', 'progress_before', 'expected_frozen_prepared')]
        for row in top:
            seal(row)
        build, pe, retired, capture, prior = [read(scope[name]['path']) for name in
                                             ('host_build', 'pe_attestation', 'raw_objects_retired', 'owned_font_capture', 'existing_runtime')]
        require(build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build['build_id'] == build_id and build['error'] is None and
                pe['schema'] == 'zerosis.goody_hut.shared_font_linked_pe_attestation.v1' and
                pe['status'] == 'PASS_READONLY_LINKED_PE_67_EXACT_PAYLOADS_NATIVE_PENDING' and pe['build_id'] == build_id and
                pe['build_result'] == scope['host_build'] and pe['inputs_unchanged'] is True and pe['catalog']['entry_count'] == 67 and
                len(pe['compilation']['actual_coff_objects']) == 10 and not pe['forbidden_access_attempts'] and
                pe['game_process_queries'] == 0 and all(pe[name] is False for name in ('candidate_native_code_loaded_or_executed',
                    'host_gamecore_hwnd_executed', 'retail_user_state_accessed', 'default_promoted', 'full_engine_goal_complete')),
                'B11 build/readonly PE approval differs')
        require(retired['schema'] == 'zerosis.goody_hut.build_objects_retired.v1' and
                retired['status'] == 'PASS_RETIRED_EXACT_TEN_OBJECTS' and retired['build_id'] == build_id and
                retired['pe'] == scope['pe_attestation'] and retired['removed_count'] == 10 and retired['protected_unchanged'] is True and
                not retired['forbidden_access_attempts'] and all(not os.path.lexists(row['path']) for row in retired['objects_before']),
                'B11 raw-object retirement differs')
        coff = pe['compilation']['actual_coff_objects']
        require(all(row['returncode'] == 0 and row['machine_hex'] == '0x8664' for row in coff) and
                len(pe['compilation']['link_objects_before']) == 5 and pe['compilation']['link_objects_before'] == pe['compilation']['link_objects_after'] and
                {(key(row['object']['path']), row['object']['bytes'], row['object']['sha256']) for row in coff} ==
                {(key(row['path']), row['bytes'], row['sha256']) for row in retired['objects_before']}, 'Retired objects differ from the actual ten-COFF/five-object-link proof')
        expected_font = font_contract(scope, capture, helper)
        frozen_prep = seal(scope['expected_frozen_prepared'])
        require(frozen_prep == seal(build['ui_assets']) and
                scope['unit_package']['sha256'] == 'fbb3b9ec4b43242cbee022b9cdf712f37ccbdf6290015ee2ee27b6547a570573' and
                scope['unit_manifest']['sha256'] == '5fcfbdc669ffd233c4ec64118e8e938656079527028a7ac052659421c6b24e7a',
                'Frozen UI catalog or original unit inputs differ')
        require(Path(scope['private_policy']['path']).read_bytes() == helper.POLICY_BYTES, 'Private PolicyInfo bytes differ')
        require(prior['smoke'] is False and prior['resume_from'] is None and prior['ui_support_from_run'] is None and
                not (PROJECT / 'Build/InteractiveGameRuntime' / prior['run_id'] / 'sessions').exists(), 'Prior runtime is not an unused private reference')
        rows = [artifact(scope_path), *top, *source_inputs.values(), *scope['preservation'], *scope['font_inputs'],
                pe['actual_build_run'], pe['actual_catalog'], pe['source_seal'],
                seal(build['executable']), artifact(PROJECT / 'evidence/ui_popup/assets/prepared.json'), *prior['runtime_inputs']]
        inventory = prior['interactive_ui_support_inventory']
        rows.extend(row['frozen'] for row in inventory['tools'].values())
        rows.extend((inventory['inline_icons']['frozen'], inventory['asset_preparation_provenance']['frozen'], inventory['frozen_support_manifest']))
        rows.extend(row for row in prior['launcher_control_metadata'].values() if within(row['path'], PROJECT))
        protected = {}
        for row in rows:
            current = seal(row);old = protected.setdefault(key(current['path']), current)
            require(old == current, 'Conflicting preservation refs')
        protected = list(protected.values())
        require(artifact(PROJECT / 'evidence/ui_popup/assets/prepared.json')['sha256'] == frozen_prep['sha256'], 'Runner would freeze a different current prepared UI')
        require(all(not os.path.lexists(STAGE / name) for name in OUTPUTS), 'Preparation is single-use; inspect existing outputs')
        legacy = helper.load_preserved()
        for name, value in (('PROJECT', PROJECT), ('STAGE', STAGE), ('TOOLS', TOOLS)):
            stack.enter_context(patch.object(legacy, name, value))
        stack.enter_context(patch.object(sys, 'path', [str(PROJECT / 'tools'), *sys.path]))
        import found_value_runtime_options as options
        import run_interactive_game as runner
        import render_ui_popup as renderer
        import ui_pixel_scene as pixels
        require(tuple(runner.FOUND_VALUE_SUPPORT_TOOLS) == TOOLS and
                renderer.owned_font_input_binding is pixels.owned_font_input_binding, 'Wrong production frontend binding')
        for relative, row in source_inputs.items():
            module = sys.modules.get(Path(relative).stem)
            require(module is None or key(module.__file__) == key(row['path']), 'Imported source mapping differs')
        prepared_source = read(frozen_prep['path'])
        require(renderer.owned_font_input_binding(prepared_source) == expected_font, 'Production binder differs from the captured owned-font contract')
        require(prepared_source['compiled_assets']['sha256'] == pe['generated_header']['sha256'], 'Prepared font bank belongs to another compiled header')
        command = [str(PROJECT / 'tools/run_interactive_game.py'), '--host-build', scope['host_build']['path'],
                   '--unit-assets-manifest', scope['unit_manifest']['path'], '--policy-info-settings', scope['private_policy']['path'],
                   '--language', 'ko_KR', '--top-panel', '--action-info-panel', '--notification-panel']
        terrain_manifest = prior['terrain_assets']['source_manifest']
        terrain_row = next(row for row in prior['runtime_inputs'] if Path(row['path']).name == 'terrain-assets.bin')
        terrain_root = Path(terrain_manifest['path']).parent
        require(terrain_root.parent == PROJECT / 'Build/TerrainAssets' and
                re.fullmatch('[0-9a-f]{64}', terrain_root.name) and
                Path(terrain_row['source']) == terrain_root / 'terrain-assets.bin' and
                terrain_root.name == terrain_row['sha256'], 'Prior terrain cache identity differs')
        terrain_refs = [seal(terrain_manifest), artifact(terrain_row['source'])]
        require(terrain_refs[1]['sha256'] == terrain_row['sha256'], 'Retained terrain package differs')
        shared_mkdir, terrain_reuse, terrain_identity = reuse_existing_directory_mkdir(terrain_root, require)
        parents = [PROJECT / 'Build/InteractiveGameRuntime', PROJECT / 'evidence/interactive_game']
        old_ids = [{path.name for path in parent.iterdir()} for parent in parents]
        helper.write_new(STAGE / 'preparation_started.json', dict(schema='zerosis.goody_hut.font_runtime_preparation.started.v1',
            scope=artifact(scope_path), argv=command, host_build_id=build_id, runtime_ids_before=sorted(old_ids[0]),
            evidence_ids_before=sorted(old_ids[1]), preserved_helper_main_called=False))
        stdout, stderr = helper.Capture(), helper.Capture()
        try:
            with patch.object(sys, 'argv', command.copy()), redirect_stdout(stdout), redirect_stderr(stderr), \
                    patch.object(Path, 'mkdir', shared_mkdir), \
                    patch.object(runner, 'select_found_value_policy', wraps=runner.select_found_value_policy) as selection:
                actual_argv = list(sys.argv);code = runner.main()
                require(code in (None, 0) and selection.call_count == 1, 'Actual production preparation/policy call failed')
        finally:
            for name, captured in (('materializer.stdout.log', stdout), ('materializer.stderr.log', stderr)):
                with (STAGE / name).open('x', encoding='utf-8') as stream:
                    stream.write(captured.getvalue())
        summaries = [json.loads(line) for line in stdout.getvalue().splitlines() if line.startswith('{')]
        require(len(summaries) == 1 and summaries[0]['status'] == 'PRIVATE_CONTINUOUS_GAME_PREPARED', 'No unique actual preparation-only result')
        run_id = summaries[0]['run_id']
        require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', run_id) and actual_argv == command and
                all({path.name for path in parent.iterdir()} - before == {run_id} for parent, before in zip(parents, old_ids)), 'Unexpected runtime allocation or argv')
        runtime, evidence = [parent / run_id for parent in parents]
        request_path = evidence / 'request.json';request = read(request_path)
        current = {Path(row['path']).name: row for row in request['runtime_inputs']}
        old = {Path(row['path']).name: row for row in prior['runtime_inputs']}
        require(len(request['runtime_inputs']) == len(current) == len(prior['runtime_inputs']) == len(old) == 24 and current.keys() == old.keys() and
                {name for name in current if current[name]['sha256'] != old[name]['sha256']} == {'ZeroSisHost_x64.exe', 'bundle.manifest'}, 'Unexpected native input delta from R10')
        require(current['ZeroSisHost_x64.exe']['sha256'] == build['executable']['sha256'] == pe['executable']['sha256'] and
                key(current['ZeroSisHost_x64.exe']['source']) == key(build['executable']['path']) and
                request['provenance']['host_build']['sha256'] == scope['host_build']['sha256'] and
                request['provenance']['frozen_runner']['sha256'] == source_inputs['tools/run_interactive_game.py']['sha256'], 'Prepared Host/runner provenance differs')
        manifest = 'ZEROSIS_HOST_BUNDLE_V4\n' + ''.join(Path(row['path']).name + '|' + row['sha256'] + '\n'
                    for row in request['runtime_inputs'] if Path(row['path']).name != 'bundle.manifest')
        require((runtime / 'bundle.manifest').read_text(encoding='ascii') == manifest and request['run_id'] == run_id and
                request['input_profile'] == 'MANUAL_CONTINUOUS_GAME_LOOP' and request['smoke'] is False and
                request['resume_from'] is None and request['ui_support_from_run'] is None and request['stage_or_mods_changed'] is False and
                all(request[name] is True for name in ('top_panel', 'action_info_panel', 'notification_panel')), 'Wrong private preparation profile or native bundle')
        validation = request['host_runtime_validation']
        require(validation['scope'] == 'RETAINED_HOST_RUNTIME_INPUTS' and len(validation['absent_discovery_objects']) == 5 and
                {(key(row['original_path']), row['sha256']) for row in validation['absent_discovery_objects']} ==
                {(key(row['object']['path']), row['object']['sha256']) for row in coff if row['phase'] == 'dependency_discovery'},
                'Runner retirement projection differs from the approved absent discovery objects')
        policy = request['policy_info_options']
        require(policy['origin'] == 'EXPLICIT_POLICY_SETTINGS_READ_ONLY' and policy['original_user_settings'] is None and
                policy['original_policy_info'] is None and policy['policy_info'] == 1 and policy['run_id'] is None, 'Wrong explicit policy origin')
        for name in ('source', 'settings_input'):
            helper.annotation(policy[name], scope['private_policy'])
        helper.annotation(request['unit_assets']['source_package'], scope['unit_package'])
        helper.annotation(request['unit_assets']['source_manifest'], scope['unit_manifest'])
        require(request['unit_assets']['reused_from_run'] is None, 'Unit assets unexpectedly inherited a prior run')
        bridge = helper.validate_policy_records(request, runtime, evidence, options)
        require(bridge['policy']['resolved_workers'] == 4, 'Actual auto policy did not resolve to the scoped four-worker preparation')
        runner.check_artifacts(request)
        methods = request['materializations']
        hits = sum(row.get('cache_method') == 'cache-hit' for row in methods)
        created = sum(str(row.get('cache_method', '')).startswith('cache-created') for row in methods)
        links = sum(row.get('materialization_method') == 'hardlink' for row in methods)
        require(links == 15 and (hits, created) in ((14, 1), (15, 0)), 'Unexpected native immutable-cache observations')
        support = request['interactive_ui_support_inventory']
        require(support['asset_preparation_provenance']['frozen']['sha256'] == frozen_prep['sha256'] and
                support['inline_icons']['frozen']['sha256'] == scope['expected_inline_icons']['sha256'], 'Frozen frontend assets differ')
        runtime_prepared = read(support['asset_preparation_provenance']['frozen']['path'])
        require(renderer.owned_font_input_binding(runtime_prepared) == expected_font, 'Actual frozen runtime font binding differs')
        require(terrain_reuse['mkdir_noop_calls'] == 1 and
                terrain_identity() == terrain_reuse['identity_before'] and
                [seal(row) for row in terrain_refs] == terrain_refs,
                'Retained terrain cache was not reused unchanged exactly once')
        terrain_reuse['identity_after'] = terrain_identity()
        imported = {relative: str(sys.modules[Path(relative).stem].__file__) for relative in source_inputs if Path(relative).stem in sys.modules}
        require(all(key(path) == key(source_inputs[relative]['path']) for relative, path in imported.items()) and
                not denied and all(guard.call_count == 0 for guard in guards), 'Wrong import or forbidden operation')
        require([seal(row) for row in protected] == protected, 'Protected input changed during actual preparation')
        helper.write_new(STAGE / 'prepared.json', dict(schema='zerosis.goody_hut.font_runtime_preparation.prepared.v1',
            status='PREPARED_NOT_EXECUTED', host_build_id=build_id, run_id=run_id,
            request=artifact(request_path), host_build=artifact(scope['host_build']['path']), runtime_inputs=24, hardlinks=links,
            cache_hits=hits, new_cache_objects=created, native_process_or_ctypes_calls=0, forbidden_access_attempts=denied))
        identity = legacy.verify_private_identity(SimpleNamespace(artifact=artifact, read=read, require=require), build_id)
        require(len(identity['private_databases']) == 2 and len(identity['current_frozen_manifest_support']) == 6 and
                [seal(row) for row in protected] == protected and renderer.owned_font_input_binding(runtime_prepared) == expected_font and
                not denied and all(guard.call_count == 0 for guard in guards), 'Final identity/font/preservation check failed')
        identity.update(schema='zerosis.goody_hut.font_runtime_preparation.identity.v1', status='PASS_PREPARED_NOT_EXECUTED',
            scope=artifact(scope_path), actual_runner_argv=actual_argv, imported_sources=imported, policy_bridge=bridge,
            owned_font_binding=expected_font, owned_font_capture=scope['owned_font_capture'], font_payloads_copied=0,
            font_cache_readonly_attribute_not_claimed=True, source_profile_required_for_runtime_rendering=False,
            cache_hits=hits, new_cache_objects=created, protected_input_count=len(protected), inputs_unchanged=True,
            shared_terrain_directory_reuse=terrain_reuse, shared_terrain_inputs=terrain_refs,
            protected_ledger_sha256=hashlib.sha256(json.dumps(protected, sort_keys=True).encode('utf-8')).hexdigest(),
            actual_runner_main_calls=1, preserved_helper_main_called=False, preserved_guard_main_called=False,
            forbidden_access_attempts=denied, host_executed=False, gamecore_loaded=False, hwnd_created=False,
            retail_user_state_or_game_processes_accessed=False, game_process_queries=0, default_promoted=False,
            retail_mod_test_hold_active=True, sdk_consumption_verified=False, full_engine_goal_complete=False)
        audit_path = STAGE / 'preparation_identity_audit.json'
        helper.write_new(audit_path, identity)
        print(json.dumps(dict(status=identity['status'], run_id=run_id, runtime_inputs=24, readonly_native_links=links,
            owned_font_inputs=len(expected_font['inputs']), cache_hits=hits, new_cache_objects=created, identity=artifact(audit_path))))


if __name__ == '__main__':
    main()
