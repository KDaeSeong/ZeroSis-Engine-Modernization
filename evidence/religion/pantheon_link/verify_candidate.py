"""Attest the source-matched Pantheon Host using preserved raw-byte PE parsers.

This wrapper does not map or execute an image, load a DLL, prepare a runtime,
or contact the installed game's user state. Historical scopes stay immutable.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
SCOPE = STAGE / 'scope.json'
SCOPE_SHA = '747c8710329e4b2a3a3905dc90b88ce9b9e2f106a0eed0c9ac918f35e6c0f99a'
SCHEMA = 'zerosis.pantheon_linked_pe_attestation.v1'
BASE_BUILD = '20261016T142908Z_fc2e23c1fd1e'
GENERATED = 'Source/Host/UiPopupAssets.generated.h'
CPP = (
    'Source/Host/UiPopupContext.h', 'Source/Host/InteractiveUiSession.h',
    'Source/Host/InteractiveGameLoop.h', 'Source/Host/LocalGameCommands.h',
    'Source/Host/LocalSdkSession.h', 'Source/Host/HostServices.h',
    'Source/Host/InteractiveGameSession.h',
)
FEATURE = {*CPP, 'Source/Host/UiScene.lua', 'Source/Presentation/UiPresentationInput.lua',
           'tools/prepare_ui_popup_assets.py', 'tools/ui_pixel_scene.py'}
DEPENDENCIES = {
    'world_wrapper': ('evidence/world_render/linked_candidate/verify_candidate.py',
                      '4ec6f240a8453681aa829fa36a529b5fffb580299c79f5f68687c1ba71f26a3c'),
    'overwrite_wrapper': ('evidence/save_overwrite/linked_candidate/verify_candidate.py',
                          '98622bfbdd93fe19c0863fec397a5390272bc5a6f060cb26ed6babcf22009686'),
    'common_pe': ('evidence/save_delete/linked_candidate/verify_candidate.py',
                  'dd06ea0c0b31faa2423639eb2f95fdd11c3ffcd6ae1ae48a9505280e3d6ba4da'),
    'pe_base': ('Tests/verify_load_menu_linked_candidate.py',
                '54388cfc99f1e00e6143da71a64439d165f502b099d6c9e019524e48743aa3a2'),
}
DEPENDENCY_PATHS = {
    **{key: value[0] for key, value in DEPENDENCIES.items()},
    'builder': 'tools/build_ui_window_host.py', 'host_builder': 'tools/build_native_host.py',
    'native_build': 'tools/native_build.py', 'collector': 'tools/collect_baseline.py',
    'ui_preparer': 'tools/prepare_ui_popup_assets.py', 'ui_codec': 'tools/civ5_ui_assets.py',
}
ORIGINAL_REL = 'Assets/DLC/Expansion2/UI/InGame/Popups/ChoosePantheonPopup.'
PANTHEON_NAMES = {'ChoosePantheonPopup', 'PantheonLayout'}
PHASES = ('dependency_discovery', 'final_compilation')
RETIRED_IDS = ('20261016T110835Z_800f48fd88c0', '20261016T111333Z_1c377d9577e6')
PRIOR_ATTEMPT = {
    'prior_catalog_preflight_scope': ('catalog_preflight_scope.json',
        '72e5f9814e5c27e4beb85bb8d1a0a6c14769e1193aa1f30b7c4a7c6f63f36cbb'),
    'prior_build_run': ('build_run.json',
        '1d5891b4b38c24dd62b4be20ee24ff31b32f146249dc5ec41c0edca73e73394d'),
    'prior_build_started': ('build_started.json',
        '2492463f9ae44a927f7d84bee8415f8283c5639ca15858ea9c1fb33bb662590e'),
    'prior_catalog_syntax': ('catalog_syntax.json',
        '2b32df5fada37bb0ae81d5c356979d0d27bf8ca33385d03350071febdc9a23fa'),
}
RETRY_CHECKER_SHA = '2e4c37cb030e0078235491a0a7facda9584643c04e1f91534b8fc1187f616e71'
FAILED_RETRY_BUILD_ID = '20261017T231135Z_74a2e2597839'


def require(value, message):
    if not value:
        raise RuntimeError(message)


def norm(path):
    return os.path.normcase(os.path.abspath(path))


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def exact_ref(inputs, row, expected):
    require(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'} and
            type(row['path']) is str and type(row['bytes']) is int and row['bytes'] >= 0 and
            re.fullmatch(r'[0-9a-f]{64}', row['sha256']) is not None,
            'A new build-scope reference lacks an exact path/size/digest identity')
    return inputs.ref(row, expected)


def attempt_paths(attempt):
    require(attempt in (None, 'retry_01', 'retry_02'), 'An unsupported build attempt was selected')
    if attempt is not None:
        names = dict(scope=attempt + '_scope.json', started='build_' + attempt + '_started.json',
            run='build_' + attempt + '_run.json', catalog='catalog_' + attempt + '.json', wrapper='build_' + attempt + '.py',
            catalog_stdout='catalog_' + attempt + '.stdout.log', catalog_stderr='catalog_' + attempt + '.stderr.log')
    else:
        names = dict(scope='catalog_preflight_scope.json', started='build_started.json',
            run='build_run.json', catalog='catalog_syntax.json', wrapper='build_once.py',
            catalog_stdout='catalog_preflight.stdout.log', catalog_stderr='catalog_preflight.stderr.log')
    return {role: STAGE / name for role, name in names.items()}


def bootstrap_ref(row, expected=None):
    require(type(row) is dict and type(row.get('path')) is str, 'Missing scoped dependency')
    path = Path(os.path.abspath(row['path']))
    require(expected is None or norm(path) == norm(expected), 'Unexpected bootstrap dependency path')
    require(path.is_relative_to(PROJECT), 'Bootstrap dependency escaped the project')
    for parent in (path, *path.parents):
        info = parent.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Bootstrap dependency contains a reparse point')
        if parent == PROJECT:
            break
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and type(row.get('bytes')) is int and info.st_size == row['bytes'],
            'Bootstrap dependency is not the sealed regular file')
    raw = path.read_bytes()
    require(len(raw) == row['bytes'] and digest(raw) == row['sha256'], 'Bootstrap dependency changed')
    after = path.stat()
    require((info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Bootstrap dependency changed while read')
    return raw


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, 'Cannot import a sealed byte-parser module')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def install_guard(allowed_outputs, forbidden):
    retail = (
        norm(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5"),
        norm(r"C:\Users\home\Documents\My Games\Sid Meier's Civilization 5"),
    )

    def audit(event, arguments):
        if event in ('open', 'os.listdir', 'os.scandir') and arguments and isinstance(arguments[0], (str, bytes, os.PathLike)):
            target = norm(os.fsdecode(arguments[0]))
            if target.startswith('\\\\?\\'):
                target = target[4:]
            if any(target == root or target.startswith(root + os.sep) for root in retail):
                forbidden.append('retail-user-state:' + event)
                raise RuntimeError('Retail MODS, settings and saves are forbidden')
            if event == 'open':
                mode = arguments[1] if len(arguments) > 1 else ''
                flags = arguments[2] if len(arguments) > 2 else 0
                writing = (isinstance(mode, str) and any(ch in mode for ch in 'wax+')) or (
                    type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                if writing and target not in allowed_outputs:
                    forbidden.append('write-outside-new-attestation')
                    raise RuntimeError('Only a new attestation or failure receipt may be written')
        if event in ('subprocess.Popen', 'os.system', 'os.startfile', 'os.startfile/2',
                     'os.exec', 'os.posix_spawn', 'os.spawn', 'ctypes.dlopen',
                     'os.remove', 'os.rmdir', 'os.rename', 'os.link', 'os.symlink'):
            forbidden.append(event)
            raise RuntimeError('Process/native execution and filesystem mutation are forbidden')

    sys.addaudithook(audit)


def scoped_bootstrap(attempt=None):
    raw = SCOPE.read_bytes()
    require(digest(raw) == SCOPE_SHA, 'Approved Pantheon linked scope changed')
    scope = json.loads(raw.decode('utf-8-sig'))
    require(scope['schema'] == 'zerosis.pantheon_link.scope.v1', 'Unexpected linked scope schema')
    require(set(scope['verifier_dependencies']) == set(DEPENDENCY_PATHS), 'Wrong exact parser/builder dependency set')
    for role, relative in DEPENDENCY_PATHS.items():
        row = scope['verifier_dependencies'][role]
        bootstrap_ref(row, PROJECT / relative)
        if role in DEPENDENCIES:
            require(row['sha256'] == DEPENDENCIES[role][1], 'Unapproved preserved parser dependency')
    world = load('pantheon_preserved_compile_helpers', PROJECT / DEPENDENCIES['world_wrapper'][0])
    overwrite = load('pantheon_preserved_overwrite_parser', PROJECT / DEPENDENCIES['overwrite_wrapper'][0])
    overwrite.STAGE = STAGE
    shared = overwrite.load_shared()
    require(norm(shared.PROJECT) == norm(PROJECT) and
            norm(shared.__file__) == norm(PROJECT / DEPENDENCIES['common_pe'][0]) and
            norm(shared.base.__file__) == norm(PROJECT / DEPENDENCIES['pe_base'][0]),
            'Preserved parser import resolved to different code')
    state = {'attempt': attempt}
    original_inputs = shared.Inputs

    class CurrentInputs(original_inputs):
        def __init__(self):
            super().__init__()
            state['inputs'] = self

        def read(self, path):
            require(not any(value in norm(path) for value in RETIRED_IDS),
                    'Retired B6/R6 roots cannot become live inputs')
            return super().read(path)

    shared.Inputs = CurrentInputs
    shared.STAGE = STAGE
    shared.REQUIRED_FEATURE_SOURCES = tuple(sorted(FEATURE))
    shared.read_feature_scope = lambda inputs: read_scope(shared, world, inputs, state)
    original_compile, original_payloads = shared.verify_compilation, shared.prepare_payloads
    shared.verify_compilation = lambda inputs, report, frozen, build_id: compilation(
        shared, world, original_compile, inputs, report, frozen, build_id, state)
    shared.prepare_payloads = lambda inputs, sources, prepared: payloads(
        shared, original_payloads, inputs, sources, prepared, state)
    shared.verify_historical_negative = lambda inputs, approved_scope, scene: historical(
        shared, inputs, approved_scope, scene, state)
    return shared, state


def read_scope(shared, world, inputs, state):
    raw = inputs.read(SCOPE)
    require(digest(raw) == SCOPE_SHA, 'Approved linked scope changed after import')
    scope = json.loads(raw.decode('utf-8-sig'))
    require(scope['schema'] == 'zerosis.pantheon_link.scope.v1' and
            scope['retail_mod_test_hold_active'] is True and scope['compile_link_allowed'] is True and
            all(scope[key] is False for key in ('host_execution_allowed', 'gamecore_execution_allowed',
                'hwnd_execution_allowed', 'retail_user_state_or_game_process_access_allowed',
                'default_promoted', 'full_engine_goal_complete')), 'Scope does not retain the native/retail hold')
    inputs.read(Path(__file__))
    for role, relative in DEPENDENCY_PATHS.items():
        inputs.ref(scope['verifier_dependencies'][role], PROJECT / relative)
    protected = world.ledger(shared, scope['protected_artifacts'])
    for row in protected.values():
        inputs.ref(row)
    for key in ('headless_lua_provider', 'storage_before'):
        inputs.ref(scope[key])
    # progress_before is a sealed historical observation of a mutable pointer.
    # Keep that observation as data and seal the legitimate current document.
    progress_path = PROJECT / 'evidence/save_menu/20261013_original_screen/current_progress.json'
    require(norm(scope['progress_before']['path']) == norm(progress_path), 'Unexpected mutable progress pointer')
    progress = json.loads(inputs.read(progress_path).decode('utf-8-sig'))
    link_progress = progress['pantheon_link_stage']
    require(progress['schema'] == 'ZEROSIS_SAVEMENU_CURRENT_PROGRESS_V1' and
            progress['status'] == 'PANTHEON_PACKAGING_AND_LINK_IN_PROGRESS' and
            progress['full_goal_redefined'] is False and progress['full_engine_goal_complete'] is False and
            link_progress['status'] == 'PACKAGING_AND_LINK_IN_PROGRESS' and
            link_progress['retail_mod_test_hold_active'] is True and
            link_progress['native_sdk_pantheon_created_verified'] is False,
            'Current progress does not preserve the scoped Pantheon/native/retail boundary')
    exact_ref(inputs, link_progress['scope'], SCOPE)
    require(link_progress['scope']['sha256'] == SCOPE_SHA, 'Current progress binds a different linked scope')
    state['progress_observation'] = dict(historical_before=scope['progress_before'],
        current=shared.artifact(progress_path, inputs), historical_observation_reasserted_as_current=False,
        current_scope_and_hold_verified=True)
    stage = json.loads(inputs.ref(scope['source_stage']).decode('utf-8-sig'))
    require(stage['schema'] == 'zerosis.pantheon_source.conformance.v1' and
            stage['status'] == 'PASS_SOURCE_HEADLESS_AND_CPP_SYNTAX_NATIVE_PENDING' and
            stage['source_stage_complete'] is True and stage['feature_native_acceptance_complete'] is False and
            stage['full_engine_goal_complete'] is False and stage['default_promoted'] is False and
            type(stage['host_gamecore_or_hwnd_execution_count']) is int and
            stage['host_gamecore_or_hwnd_execution_count'] == 0 and
            stage['retail_MODS_saves_settings_or_game_processes_accessed'] is False,
            'Pantheon source-stage acceptance differs')
    require(set(scope['source_seals']) == FEATURE and len(scope['source_seals']) == len(FEATURE),
            'Wrong exact Pantheon production-source set')
    require(set(stage['current_source_files']) == set(scope['all_source_and_test_seals']),
            'Source/test approval closure differs')
    for relative, row in scope['all_source_and_test_seals'].items():
        require(relative in stage['current_source_files'] and
                world.same_ref(shared, row, stage['current_source_files'][relative]),
                'Scoped source/test input has no exact source-stage approval')
        inputs.ref(row, PROJECT / relative)
    for relative, row in scope['source_seals'].items():
        require(world.same_ref(shared, row, scope['all_source_and_test_seals'][relative]),
                'Production source differs from its approved source/test ledger')
    require(set(scope['cpp_changed_headers']) == set(CPP) and len(scope['cpp_changed_headers']) == len(CPP) and
            set(scope['cpp_consumers']) == set(CPP) and
            all(value == ['host_main'] for value in scope['cpp_consumers'].values()) and
            scope['generated_header_consumer'] == ['host_main'], 'Wrong exact new C++ consumer contract')
    require(scope['base_build_id'] == BASE_BUILD, 'The approved frozen donor is not B8')
    donor = json.loads(inputs.ref(scope['base_build'],
        PROJECT / f'evidence/ui_window_host/{BASE_BUILD}/build_result.json').decode('utf-8-sig'))
    require(donor['build_id'] == BASE_BUILD and donor['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
            donor['error'] is None and donor['source_inputs_unchanged'] is True and
            donor['provider_inputs_unchanged'] is True, 'Frozen B8 donor is not a successful preserved build')
    require(scope['old_generated_header']['sha256'] == scope['old_generated_header_recovery']['sha256'] and
            scope['old_generated_header']['bytes'] == scope['old_generated_header_recovery']['bytes'] and
            norm(scope['old_generated_header']['path']) == norm(PROJECT / GENERATED),
            'Generated-header rollback identity differs')
    inputs.ref(scope['old_generated_header_recovery'])
    inputs.ref(scope['old_prepared_recovery'])
    expected_derived = {norm(PROJECT / GENERATED),
                        norm(PROJECT / 'evidence/ui_popup/assets/prepared.json'),
                        norm(PROJECT / 'evidence/ui_popup/assets/inline_icons.json')}
    require({norm(path) for path in scope['mutable_derived_paths']} == expected_derived and
            len(scope['mutable_derived_paths']) == len(expected_derived), 'Unexpected mutable derived-output paths')
    original = {Path(row['path']).suffix.casefold()[1:]: row for row in scope['original_assets']}
    require(set(original) == {'lua', 'xml'} and len(scope['original_assets']) == 2, 'Wrong original Pantheon input set')
    for extension, row in original.items():
        inputs.ref(row, shared.GAME / (ORIGINAL_REL + extension))
    snapshots = {norm(PROJECT / 'Source/Assets/UI' / (ORIGINAL_REL + extension)): extension for extension in original}
    require(set(map(norm, scope['new_source_snapshots'])) == set(snapshots) and
            len(scope['new_source_snapshots']) == len(snapshots), 'Wrong original-source snapshot paths')
    for path, extension in snapshots.items():
        require(inputs.read(path) == inputs.ref(original[extension]), 'New original UI snapshot is not byte exact')
    profiles = {}
    for role in world.TUS:
        profile = {'baseline_responses': {}}
        for phase in PHASES:
            row = world.translation_rows(donor, phase)[role]['response']
            lines = inputs.ref(row).decode('utf-8-sig').splitlines()
            expected = dict(language='/std:c++17' if role == 'terrain_renderer' else '/std:c++14',
                            source_charset='/source-charset:utf-8' if role == 'world_renderer' else '/source-charset:windows-1252',
                            required_flags=['/nologo', '/EHsc', '/W4', '/WX', '/O2', '/MD', '/fp:strict', '/c'],
                            forbidden_flags=['/Yu', '/Yc', '/Gm', '/GL'],
                            defines_exact=[line for line in lines if line.startswith('/D')])
            world.check_profile(lines, expected)
            profile[phase], profile['baseline_responses'][phase] = expected, row
        profiles[role] = profile
    effective_scope = dict(scope, expected_compile_profile={'by_tu': profiles},
                           frozen_input_reuse_donor=scope['base_build'])
    state.update(scope=scope, donor=donor, original=original, protected=protected,
                 cpp={norm(PROJECT / name): scope['source_seals'][name] for name in CPP},
                 compile_state={'scope': effective_scope, 'donor': donor,
                                'cpp': {norm(PROJECT / name): scope['source_seals'][name] for name in CPP}})
    return SCOPE, scope, scope['source_seals']


def previous_retry_receipts(shared, world, inputs, extension, started, run, state):
    previous = extension['previous_failed_attempt']
    require(previous['attempt'] == 'retry_01' and previous['failed_build_id'] == FAILED_RETRY_BUILD_ID and
            started['previous_failed_attempt'] == run['previous_failed_attempt'] == previous,
            'Retry 02 does not bind the exact preserved failed retry 01')
    expected = {
        'wrapper': (STAGE / 'build_retry_01.py', '93c55bcc99b0d51340827a86fd26f6a6b24b0cdd7a1db761ebd099488b29ee24'),
        'scope': (STAGE / 'retry_01_scope.json', 'f0d27ae542b02652343421fea58ccc315a392bfc890cce0fdcd0f031bad72d2c'),
        'started': (STAGE / 'build_retry_01_started.json', 'b3fa644cc721bc39ae51e30691791a4a753dec686ff4d00284df1340504e89fb'),
        'run': (STAGE / 'build_retry_01_run.json', '91785b1c8f0283749cc03df31b7f69d6f45581ba4c3096bb4fc5cf18f259bec2'),
        'catalog': (STAGE / 'catalog_retry_01.json', 'fd00dbbaca114da57690d46efd07299eee612bd2fe8f2f102af5dea6696101e7'),
        'build_report': (PROJECT / 'evidence/ui_window_host' / FAILED_RETRY_BUILD_ID / 'build_result.json',
                         'b530812e2ef8730242da62b98d2a9231200d31058b15efa0292f79f6d8e3bd97'),
    }
    documents = {}
    for role, (path, sha256) in expected.items():
        raw = exact_ref(inputs, previous[role], path)
        require(previous[role]['sha256'] == sha256, 'A preserved retry 01 artifact was replaced')
        if role != 'wrapper':
            documents[role] = json.loads(raw.decode('utf-8-sig'))
    artifacts = world.ledger(shared, previous['artifacts'])
    require(set(artifacts) == {norm(path) for path, _ in expected.values()} |
            {norm(STAGE / name) for name in ('catalog_retry_01.stdout.log', 'catalog_retry_01.stderr.log')},
            'Retry 02 does not preserve the exact eight previous-attempt artifacts')
    for row in artifacts.values():
        exact_ref(inputs, row, row['path'])
    old_scope, old_started, old_run, old_catalog, failed = (documents[role] for role in
        ('scope', 'started', 'run', 'catalog', 'build_report'))
    for row in (old_scope['parent_scope'], old_started['scope'], old_run['scope']):
        exact_ref(inputs, row, SCOPE)
        require(row['sha256'] == SCOPE_SHA, 'The failed retry changed the original parent scope')
    for row in (old_started['catalog_preflight_scope'], old_run['catalog_preflight_scope']):
        require(world.same_ref(shared, row, previous['scope']), 'The failed retry marker/run has different scope lineage')
        exact_ref(inputs, row, expected['scope'][0])
    for row in (old_scope['root_build_wrapper'], old_started['wrapper'], old_run['wrapper']):
        require(world.same_ref(shared, row, previous['wrapper']), 'The failed retry marker/run has different wrapper lineage')
        exact_ref(inputs, row, expected['wrapper'][0])
    require(old_scope['retry_attempt'] == old_started['retry_attempt'] == old_run['retry_attempt'] == 'retry_01' and
            old_run['schema'] == 'zerosis.pantheon_link.actual_build_run.v1' and old_run['status'] == 'FAIL' and
            old_run['new_build_ids'] == old_run['new_evidence_ids'] == [FAILED_RETRY_BUILD_ID] and
            old_run['state'] == dict(preparations=1, catalog_preflights=1, catalog_verified=True) and
            old_run['compiled_objects'] == {} and old_run['actual_link_snapshot'] == {} and
            len(old_run['processes']) == 2 and
            all(Path(row['executable']).name.casefold() == 'python.exe' for row in old_run['processes']) and
            old_run['forbidden_access_attempts'] == [] and old_run['actual_builder_subprocess_results_unmodified'] is True and
            all(old_run[key] is False for key in ('host_executed', 'gamecore_loaded', 'hwnd_created',
                'retail_user_state_or_game_processes_accessed', 'default_promoted')),
            'The previous retry is not the preserved post-catalog, pre-compiler/link failure')
    require(failed['status'] == 'UI_WINDOW_HOST_BUILD_FAILED' and failed['build_id'] == FAILED_RETRY_BUILD_ID and
            '[WinError 5]' in failed['error'] and 'HostMain.cpp' in failed['error'] and
            failed['source_hashes_before'] == failed['source_hashes_after'] and
            failed['source_hashes_before']['builder'] == state['scope']['verifier_dependencies']['builder']['sha256'] and
            failed['compiler_inputs'] == failed['provider_inputs'] == failed['sources'] == [] and
            failed.get('dependency_discovery') is None and failed.get('final_compilation') is None and
            failed['executable'] is None and
            all(failed[key] is False for key in ('gamecore_loaded', 'host_runtime_executed', 'mods_updated', 'sdk_linked', 'stage_updated')),
            'The actual failed build does not prove unchanged source and a frozen-input hardlink-only failure')
    require(old_catalog['status'] == 'PASS_GENERATED_SCRIPT_CATALOG_LUA51_SYNTAX_ONLY' and
            old_catalog['catalog_count'] == old_catalog['parsed_count'] == 64 and old_catalog['failed_count'] == 0 and
            old_catalog['inputs_unchanged'] is True and old_catalog['inputs_before'] == old_catalog['inputs_after'] and
            all(old_catalog[key] is False for key in ('scripts_executed', 'lua_openlibs_called', 'host_executed',
                'gamecore_loaded', 'hwnd_created', 'retail_user_state_accessed', 'default_promoted')),
            'The previous retry did not retain its successful 64-script parser-only catalog receipt')
    require(world.same_ledger(shared, world.ledger(shared, old_scope['additional_protected_artifacts']),
                             world.ledger(shared, extension['additional_protected_artifacts'])),
            'Retry 02 changed the original fourteen immutable backups')
    for field, base_field in (('observed_build_identifiers_before', 'build_identifiers_before'),
                              ('observed_evidence_identifiers_before', 'evidence_identifiers_before')):
        values = extension[field]
        require(type(values) is list and len(values) == len(set(values)) and
                set(values) == set(state['scope'][base_field]) | {FAILED_RETRY_BUILD_ID},
                'Retry 02 silently changes the observed pre-attempt build/evidence identifiers')
    probes = extension['hardlink_permission_probes']
    require(type(probes) is dict and set(probes) == {'sandbox_denied', 'approved_allowed'}, 'Missing exact hardlink permission probes')
    denied = json.loads(exact_ref(inputs, probes['sandbox_denied'], STAGE / 'hardlink_capability_probe.json').decode('utf-8-sig'))
    allowed = json.loads(exact_ref(inputs, probes['approved_allowed'], STAGE / 'hardlink_unsandboxed_probe.json').decode('utf-8-sig'))
    require(denied['schema'] == 'zerosis.pantheon_link.hardlink_capability_probe.v1' and
            denied['status'] == 'HARDLINK_DENIED' and denied['winerror'] == 5 and denied['target_created'] is False and
            denied['dlls_loaded'] == 0 and allowed['schema'] == 'zerosis.pantheon_link.hardlink_unsandboxed_probe.v1' and
            allowed['status'] == 'HARDLINK_ALLOWED' and allowed['links'] == 2 and allowed['host_executed'] is False and
            denied['bytes'] == allowed['bytes'] == 26 and denied['sha256'] == allowed['sha256'] and
            all(probe['temporary_files_removed'] is True and probe['retail_accessed'] is False for probe in (denied, allowed)),
            'The preserved owned-file probes do not support the approved sandbox-permission retry')
    state['previous_failed_attempt'] = dict(receipts=previous, hardlink_permission_probes=probes,
        source_hashes_before_after_equal=True, production_builder_unchanged=True,
        actual_compiler_and_linker_invocations=0, historical_parser_count=64,
        preserved_failed_build_id=FAILED_RETRY_BUILD_ID, failed_build_is_not_a_successful_candidate=True)


def retry_receipts(shared, world, inputs, extension, started, run, paths, state):
    require(extension['retry_manifest_schema'] == 'zerosis.pantheon_link.retry_manifest.v1' and
            extension['retry_attempt'] == started['retry_attempt'] == run['retry_attempt'] == state['attempt'] and
            extension['retail_mod_test_hold_active'] is True and extension['runtime_preparation_allowed'] is False and
            extension['game_process_queries_allowed'] is False and
            extension['game_process_priority_or_affinity_changes_allowed'] is False and
            extension['own_builder_priority'] == 'BELOW_NORMAL_PRIORITY_CLASS' and
            extension['intended_affinity'] == 'UNCHANGED',
            'Retry receipts do not identify the explicitly selected attempt')
    outputs = {role: paths[role] for role in ('started', 'run', 'catalog', 'catalog_stdout', 'catalog_stderr')}
    require(type(extension['output_paths']) is dict and set(extension['output_paths']) == set(outputs) and
            all(type(extension['output_paths'][role]) is str and
                norm(extension['output_paths'][role]) == norm(path) for role, path in outputs.items()),
            'Retry output paths differ from the exact create-only attempt paths')
    prior = {}
    for role, (filename, sha256) in PRIOR_ATTEMPT.items():
        row = extension[role]
        raw = exact_ref(inputs, row, STAGE / filename)
        require(row['sha256'] == sha256, 'A preserved initial-attempt receipt was replaced')
        prior[role] = json.loads(raw.decode('utf-8-sig'))
    old_extension = prior['prior_catalog_preflight_scope']
    old_started, old_run, old_catalog = (prior[role] for role in
        ('prior_build_started', 'prior_build_run', 'prior_catalog_syntax'))
    for row in (old_extension['parent_scope'], old_started['scope'], old_run['scope']):
        exact_ref(inputs, row, SCOPE)
        require(row['sha256'] == SCOPE_SHA, 'Initial-attempt receipts bind a different parent scope')
    for row in (old_started['catalog_preflight_scope'], old_run['catalog_preflight_scope']):
        exact_ref(inputs, row, STAGE / 'catalog_preflight_scope.json')
        require(world.same_ref(shared, row, extension['prior_catalog_preflight_scope']),
                'The initial marker/run is detached from its preserved original extension')
    for row in (old_extension['root_build_wrapper'], old_started['wrapper'], old_run['wrapper']):
        exact_ref(inputs, row, STAGE / 'build_once.py')
    require(old_run['schema'] == 'zerosis.pantheon_link.actual_build_run.v1' and old_run['status'] == 'FAIL' and
            old_started['schema'] == 'zerosis.pantheon_link.actual_build_started.v1' and
            old_run['new_build_ids'] == old_run['new_evidence_ids'] == [] and
            len(old_run['processes']) == 2 and
            all(Path(row['executable']).name.casefold() == 'python.exe' and norm(row['cwd']) == norm(PROJECT)
                for row in old_run['processes']) and
            old_run['compiled_objects'] == {} and old_run['actual_link_snapshot'] == {} and
            old_run['state'] == dict(preparations=1, catalog_preflights=1, catalog_verified=False) and
            old_run['actual_builder_subprocess_results_unmodified'] is True and
            type(old_run['python_optimization_level']) is int and old_run['python_optimization_level'] == 0 and
            old_run['forbidden_access_attempts'] == [] and
            all(old_run[key] is False for key in ('host_executed', 'gamecore_loaded', 'hwnd_created',
                'retail_user_state_or_game_processes_accessed', 'default_promoted')),
            'The original failure is not the preserved preparer/checker-only attempt with zero compilation/linking')
    require(old_catalog['schema'] == 'zerosis.pantheon_link.generated_script_catalog_syntax.v1' and
            old_catalog['status'] == 'FAILED_INPUT_PRESERVATION_OR_GUARD' and
            old_catalog['error_type'] == 'PermissionError' and old_catalog['inputs_unchanged'] is False and
            old_catalog['guard'] == dict(explicit_lua_provider_loads=0, blocked_process_attempts=0,
                blocked_retail_attempts=0, blocked_write_attempts=0, blocked_dll_attempts=0, blocked_read_attempts=2) and
            old_catalog['scripts'] == [] and old_catalog['additional_processes_started'] == 0 and
            all(old_catalog[key] is False for key in ('scripts_executed', 'lua_openlibs_called', 'host_executed',
                'gamecore_loaded', 'hwnd_created', 'retail_user_state_accessed', 'default_promoted')),
            'The preserved catalog failure does not match the pre-parser codec-guard diagnosis')
    failure = extension['prior_failure']
    require(failure['status'] == old_run['status'] and failure['process_count'] == len(old_run['processes']) and
            failure['new_build_ids'] == old_run['new_build_ids'] and
            failure['new_evidence_ids'] == old_run['new_evidence_ids'] and
            failure['state'] == old_run['state'] and failure['catalog_status'] == old_catalog['status'] and
            failure['catalog_error'] == old_catalog['error'] and failure['catalog_guard'] == old_catalog['guard'] and
            failure['compiled_object_count'] == 0 and failure['link_snapshot_empty'] is True and
            type(failure['diagnosis']) is str and failure['diagnosis'], 'Retry scope misstates the initial failure')
    for row in (started['prior_build_run'], run['prior_build_run']):
        exact_ref(inputs, row, STAGE / 'build_run.json')
        require(world.same_ref(shared, row, extension['prior_build_run']), 'Retry marker/run references a different initial failure')
    require(run['prior_failure'] == failure and
            run['mutable_derived_before_retry'] == extension['mutable_derived_before_retry'] and
            run['new_source_snapshots_before_retry'] == extension['new_source_snapshots_before_retry'],
            'Retry run changed its historical failure or pre-retry derived-output observations')
    # Derived pre-retry identities are historical data, not current-file seals.
    observed_derived = world.ledger(shared, extension['mutable_derived_before_retry'])
    observed_snapshots = world.ledger(shared, extension['new_source_snapshots_before_retry'])
    require(set(observed_derived) == {norm(path) for path in state['scope']['mutable_derived_paths']} and
            set(observed_snapshots) == {norm(path) for path in state['scope']['new_source_snapshots']},
            'Retry historical derived/snapshot path inventory differs from its original approved scope')
    for row in observed_snapshots.values():
        exact_ref(inputs, row, row['path'])
    priority = run['own_builder_priority']
    require(started['own_builder_priority'] == priority and priority['requested'] == extension['own_builder_priority'] and
            priority['applied'] is True and priority['target'] == 'GetCurrentProcess pseudo handle only' and
            priority['affinity_changed'] is False and type(priority['game_process_queries']) is int and
            priority['game_process_queries'] == 0 and priority['game_process_priority_or_affinity_changed'] is False,
            'Retry priority receipt does not retain its own-process-only policy')

    backup_path = STAGE / 'check_catalog_syntax.pre_codec_fix.py'
    backup = exact_ref(inputs, extension['prior_checker_backup'], backup_path)
    old_checker = old_extension['checker']
    require(norm(old_checker['path']) == norm(STAGE / 'check_catalog_syntax.py') and
            old_checker['bytes'] == len(backup) and old_checker['sha256'] == digest(backup) and
            extension['checker']['sha256'] == RETRY_CHECKER_SHA,
            'The original checker backup or approved repaired checker identity differs')
    repaired = exact_ref(inputs, extension['checker'], STAGE / 'check_catalog_syntax.py')
    require(backup.count(b"b''.decode('utf-8-sig')") == 1 and
            repaired == backup.replace(b"b''.decode('utf-8-sig')", b"b'x'.decode('utf-8-sig')", 1),
            'The retry checker changed more than the approved nonempty codec warm-up')
    repair_path = STAGE / 'codec_guard_repair.json'
    repair = json.loads(exact_ref(inputs, extension['checker_repair_evidence'], repair_path).decode('utf-8-sig'))
    require(repair['schema'] == 'zerosis.pantheon_link.codec_guard_repair.v1' and
            repair['status'] == 'PASS_MINIMAL_CODEC_PRELOAD_FIX' and repair['changed_lines'] == 1 and
            repair['guard_allowlist_unchanged'] is True and repair['dlls_loaded'] == repair['additional_processes'] == 0 and
            repair['retail_state_accessed'] is False and repair['host_executed'] is False,
            'Codec repair evidence exceeds the approved no-guard-change boundary')
    for role, expected in (('first_failed_build', extension['prior_build_run']),
                           ('first_failed_catalog', extension['prior_catalog_syntax']),
                           ('checker_before', extension['prior_checker_backup']), ('checker_after', extension['checker'])):
        require(world.same_ref(shared, repair[role], expected) and repair[role]['bytes'] == expected['bytes'],
                'Codec repair evidence is detached from the preserved failure/current repair')
        exact_ref(inputs, repair[role], expected['path'])
    validation_path = STAGE / 'catalog_codec_fixed.json'
    validation = json.loads(exact_ref(inputs, extension['checker_repair_validation'], validation_path).decode('utf-8-sig'))
    require(validation['schema'] == 'zerosis.pantheon_link.generated_script_catalog_syntax.v1' and
            validation['status'] == 'PASS_GENERATED_SCRIPT_CATALOG_LUA51_SYNTAX_ONLY' and
            validation['inputs_unchanged'] is True and validation['failed_count'] == 0 and
            all(validation[key] is False for key in ('scripts_executed', 'lua_openlibs_called', 'host_executed',
                'gamecore_loaded', 'hwnd_created', 'retail_user_state_accessed', 'default_promoted')) and
            validation['additional_processes_started'] == 0,
            'The repaired codec guard lacks its preserved parser-only validation')
    validation_inputs = world.ledger(shared, validation['inputs_before'])
    require(world.same_ref(shared, validation_inputs[norm(STAGE / 'check_catalog_syntax.py')], extension['checker']),
            'The repaired guard validation inspected different checker bytes')
    historical = world.ledger(shared, extension['prior_attempt_artifacts'])
    repairs = world.ledger(shared, extension['repair_artifacts'])
    expected_historical = {norm(STAGE / filename) for filename in (
        'catalog_preflight_scope.json', 'build_run.json', 'build_started.json', 'catalog_syntax.json',
        'build_once.py', 'catalog_preflight.stdout.log', 'catalog_preflight.stderr.log',
        'check_catalog_syntax.pre_codec_fix.py', 'codec_guard_repair.json')}
    require(set(historical) == expected_historical and set(repairs) == {norm(backup_path), norm(repair_path), norm(validation_path)},
            'Retry scope does not protect the exact historical attempt and repair evidence sets')
    for row in (*historical.values(), *repairs.values()):
        exact_ref(inputs, row, row['path'])
    original_backups = world.ledger(shared, old_extension['additional_protected_artifacts'])
    current_backups = world.ledger(shared, extension['additional_protected_artifacts'])
    require(world.same_ledger(shared, original_backups, current_backups), 'Retry changed the fourteen original immutable backups')
    for role in ('catalog_stdout', 'catalog_stderr'):
        inputs.read(paths[role])
    state['retry_observation'] = dict(attempt=state['attempt'], retry_scope=shared.artifact(paths['scope'], inputs),
        prior_receipts={role: extension[role] for role in PRIOR_ATTEMPT}, prior_failure=failure,
        prior_attempt_artifacts=list(historical.values()), repair_artifacts=list(repairs.values()),
        own_builder_priority=priority, mutable_derived_before_retry=extension['mutable_derived_before_retry'],
        new_source_snapshots_before_retry=extension['new_source_snapshots_before_retry'],
        original_checker_reference_preserved_as_historical_data=True, failed_initial_attempt_not_overwritten=True)
    if state['attempt'] == 'retry_02':
        previous_retry_receipts(shared, world, inputs, extension, started, run, state)
        state['retry_observation']['previous_failed_attempt'] = state['previous_failed_attempt']


def build_receipts(shared, world, inputs, build_id, generated, state):
    paths = attempt_paths(state['attempt'])
    extension_path, started_path, run_path = (paths[role] for role in ('scope', 'started', 'run'))
    checker_path, wrapper_path = STAGE / 'check_catalog_syntax.py', paths['wrapper']
    catalog_path = paths['catalog']
    extension, started, run = (inputs.document(path) for path in (extension_path, started_path, run_path))
    if state['attempt'] in ('retry_01', 'retry_02'):
        retry_receipts(shared, world, inputs, extension, started, run, paths, state)
    require(extension['schema'] == 'zerosis.pantheon_link.catalog_preflight_scope.v1' and
            extension['expected_status'] == 'PASS_GENERATED_SCRIPT_CATALOG_LUA51_SYNTAX_ONLY' and
            extension['expected_checker_inputs_unchanged'] is True and
            type(extension['expected_failed_count']) is int and extension['expected_failed_count'] == 0 and
            type(extension['python_optimization_level_required']) is int and
            extension['python_optimization_level_required'] == 0 and
            extension['native_game_Host_GameCore_HWND_execution_allowed'] is False and
            extension['retail_user_state_or_game_process_access_allowed'] is False and
            type(extension['full_project_copies_created']) is int and extension['full_project_copies_created'] == 0 and
            started['schema'] == 'zerosis.pantheon_link.actual_build_started.v1' and
            run['schema'] == 'zerosis.pantheon_link.actual_build_run.v1' and run['status'] == 'PASS' and
            run['new_build_ids'] == [build_id] and run['new_evidence_ids'] == [build_id] and
            type(run['python_optimization_level']) is int and run['python_optimization_level'] == 0 and
            run['actual_builder_subprocess_results_unmodified'] is True and
            run['forbidden_access_attempts'] == [] and run['error'] is None and
            all(run[key] is False for key in ('host_executed', 'gamecore_loaded', 'hwnd_created',
                'retail_user_state_or_game_processes_accessed', 'default_promoted')),
            'Actual root build receipt does not prove this exact guarded build')
    require(type(started['pid']) is int and started['pid'] > 0, 'Actual build marker has no process identity')
    build_state = run['state']
    require(set(build_state) == {'preparations', 'catalog_preflights', 'catalog_verified'} and
            type(build_state['preparations']) is int and build_state['preparations'] == 1 and
            type(build_state['catalog_preflights']) is int and build_state['catalog_preflights'] == 1 and
            build_state['catalog_verified'] is True, 'The actual preparer/catalog/compiler sequence differs')
    for row in (extension['parent_scope'], started['scope'], run['scope']):
        exact_ref(inputs, row, SCOPE)
        require(row['sha256'] == SCOPE_SHA, 'A build receipt binds a different original linked scope')
    for row in (started['catalog_preflight_scope'], run['catalog_preflight_scope']):
        exact_ref(inputs, row, extension_path)
    for row in (extension['root_build_wrapper'], started['wrapper'], run['wrapper']):
        exact_ref(inputs, row, wrapper_path)
    exact_ref(inputs, extension['checker'], checker_path)
    additional = world.ledger(shared, extension['additional_protected_artifacts'])
    require(len(additional) == 14, 'The exact additional immutable source-backup set differs')
    for row in additional.values():
        exact_ref(inputs, row, row['path'])

    catalog = inputs.document(catalog_path)
    require(catalog['schema'] == 'zerosis.pantheon_link.generated_script_catalog_syntax.v1' and
            catalog['status'] == extension['expected_status'] and catalog['inputs_unchanged'] is True and
            type(catalog['failed_count']) is int and catalog['failed_count'] == 0 and
            all(catalog[key] is False for key in ('scripts_executed', 'lua_openlibs_called', 'host_executed',
                'gamecore_loaded', 'hwnd_created', 'retail_user_state_accessed', 'default_promoted')) and
            type(catalog['additional_processes_started']) is int and catalog['additional_processes_started'] == 0,
            'Generated Lua catalog preflight did not pass within its parser-only boundary')
    before = world.ledger(shared, catalog['inputs_before'])
    after = world.ledger(shared, catalog['inputs_after'])
    require(catalog['inputs_before'] == catalog['inputs_after'] and world.same_ledger(shared, before, after),
            'Catalog preflight input identities changed')
    for row in before.values():
        exact_ref(inputs, row, row['path'])
    required_catalog_inputs = {
        norm(SCOPE): extension['parent_scope'], norm(checker_path): extension['checker'],
        norm(PROJECT / GENERATED): shared.artifact(PROJECT / GENERATED, inputs),
        norm(state['scope']['headless_lua_provider']['path']): state['scope']['headless_lua_provider'],
        norm(state['scope']['source_stage']['path']): state['scope']['source_stage'],
        **{norm(row['path']): row for row in state['scope']['source_seals'].values()},
    }
    for path, row in required_catalog_inputs.items():
        require(path in before and world.same_ref(shared, before[path], row) and
                before[path]['bytes'] == row['bytes'], 'Catalog preflight used a different scoped current input')
    generated_ref = before[norm(PROJECT / GENERATED)]
    require(generated_ref['bytes'] == len(generated) and generated_ref['sha256'] == digest(generated),
            'Preflight did not inspect the exact compiled generated header')
    guard = catalog['guard']
    require(set(guard) == {'explicit_lua_provider_loads', 'blocked_process_attempts', 'blocked_retail_attempts',
                          'blocked_write_attempts', 'blocked_dll_attempts', 'blocked_read_attempts'} and
            all(type(value) is int for value in guard.values()) and guard['explicit_lua_provider_loads'] == 1 and
            all(value == 0 for key, value in guard.items() if key.startswith('blocked_')),
            'Catalog preflight attempted a forbidden operation or changed parser-load count')
    compiled = run['compiled_objects']
    require(type(compiled) is dict, 'Actual compilation object receipts are missing')
    state.update(actual_build_run=run, compiled_objects=compiled, catalog_preflight=catalog,
        build_sequence=dict(attempt=state['attempt'] or 'initial', build_run=shared.artifact(run_path, inputs),
            started_marker=shared.artifact(started_path, inputs),
            catalog_preflight_scope=shared.artifact(extension_path, inputs),
            root_build_wrapper=run['wrapper'], checker=extension['checker'],
            catalog_syntax=shared.artifact(catalog_path, inputs),
            additional_protected_artifacts=list(additional.values()),
            guarded_preparer_then_catalog_then_compiler=True, python_optimization_level=0))
    if state['attempt'] in ('retry_01', 'retry_02'):
        state['build_sequence']['retry_observation'] = state['retry_observation']


def compilation(shared, world, original, inputs, report, frozen, build_id, state):
    require(report['error'] is None and build_id != BASE_BUILD, 'A fresh successful candidate is required')
    require(report['toolchain']['target'] == 'x64' and report['toolchain']['optimization'] == '/O2' and
            report['toolchain']['runtime'] == '/MD' and report['toolchain']['pch_used'] is False and
            report['toolchain']['brepro'] is True, 'Compiler/linker target policy differs')
    # Rebind only the explicitly scoped roles in this newly imported helper
    # instance. Its historical scope reader, negative and main are never called.
    world.DONOR = BASE_BUILD
    world.CPP_CONSUMERS = {name: ('host_main',) for name in CPP}
    result = world.verify_compilation(shared, original, inputs, report, frozen, build_id, state['compile_state'])
    sources, generated, final_sets = result
    current = {norm(row['original_path']): row for row in report['compiler_inputs']}
    baseline = {norm(row['original_path']): row for row in state['donor']['compiler_inputs']}
    require(len(current) == len(report['compiler_inputs']) and len(baseline) == len(state['donor']['compiler_inputs']) and
            set(current) == set(baseline), 'New compiler input path closure differs from the approved B8 closure')
    changed = set(state['cpp']) | {norm(PROJECT / GENERATED)}
    for path, row in current.items():
        old = baseline[path]
        require(row['root_name'] == old['root_name'], 'Compiler input root classification changed')
        if path not in changed:
            require((row['sha256'], row['bytes']) == (old['sha256'], old['bytes']),
                    'An unapproved project/SDK/system compiler input changed')
    generated_row = current[norm(PROJECT / GENERATED)]
    require(shared.norm(generated_row['path']) in final_sets['host_main'] and
            inputs.ref(generated_row) == generated and
            digest(generated) != state['scope']['old_generated_header_recovery']['sha256'],
            'The new generated catalog was not consumed or still equals B8')
    build_receipts(shared, world, inputs, build_id, generated, state)
    generated_consumers = {}
    for phase in PHASES:
        consumed = []
        for role, row in world.translation_rows(report, phase).items():
            require(type(row['returncode']) is int and row['returncode'] == 0, 'Compiler did not return integer zero')
            doc = json.loads(inputs.ref(row['dependency_report']).decode('utf-8-sig'))
            data = doc.get('Data', doc)
            paths = {norm(path) for path in (data['Source'], *data['Includes'])}
            target = norm(PROJECT / GENERATED) if phase == 'dependency_discovery' else norm(generated_row['path'])
            if target in paths:
                consumed.append(role)
        require(consumed == ['host_main'], 'Generated catalog has an unexpected exact TU consumer set')
        generated_consumers[phase] = consumed
    objects, final_paths = {}, []
    expected_object_keys = set()
    for phase in PHASES:
        directory = 'dependency_discovery' if phase == 'dependency_discovery' else 'final'
        for index, (role, (_, stem)) in enumerate(world.TUS.items()):
            path = PROJECT / 'Build/UiWindowHost' / build_id / directory / f'tu_{index:02d}_{role}' / 'obj' / (stem + '.obj')
            raw = inputs.read(path)
            require(len(raw) >= 20 and int.from_bytes(raw[:2], 'little') == 0x8664 and
                    int.from_bytes(raw[2:4], 'little') > 0, 'An actual discovery/final object is not AMD64 COFF')
            row = world.translation_rows(report, phase)[role]
            key = norm(path)
            expected_object_keys.add(key)
            require(key in state['compiled_objects'], 'Actual compiler receipt omits an exact COFF object')
            compiled = state['compiled_objects'][key]
            require(compiled['phase'] == directory and compiled['translation_unit'] == role and
                    type(compiled['returncode']) is int and compiled['returncode'] == 0 and
                    exact_ref(inputs, compiled['object'], path) == raw and
                    world.same_ref(shared, compiled['response'], row['response']),
                    'Actual successful compiler output differs from this TU response/object identity')
            exact_ref(inputs, compiled['response'], row['response']['path'])
            if phase == 'dependency_discovery':
                require(len(row['objects']) == 1 and norm(row['objects'][0]['path']) == norm(path) and
                        inputs.ref(row['objects'][0]) == raw, 'Discovery COFF object differs from its exact build receipt')
            else:
                final_paths.append(path)
            objects[phase + ':' + role] = shared.artifact(path, inputs)
    require(len(objects) == 2 * len(world.TUS) and set(state['compiled_objects']) == expected_object_keys,
            'Discovery/final actual compiler COFF object coverage differs')
    link = state['actual_build_run']['actual_link_snapshot']
    require(type(link['returncode']) is int and link['returncode'] == 0 and
            world.same_ref(shared, link['response'], report['link_response']),
            'Actual successful link receipt binds a different link response')
    exact_ref(inputs, link['response'], report['link_response']['path'])
    link_before, link_after = (world.ledger(shared, link[key]) for key in ('objects_before', 'objects_after'))
    require(len(link_before) == len(link_after) == len(world.TUS) and
            set(link_before) == {norm(path) for path in final_paths} and
            world.same_ledger(shared, link_before, link_after), 'Actual link object identities changed or omit a TU')
    for path in final_paths:
        before, after = link_before[norm(path)], link_after[norm(path)]
        require(exact_ref(inputs, before, path) == exact_ref(inputs, after, path) and
                world.same_ref(shared, before, state['compiled_objects'][norm(path)]['object']),
                'A final COFF object differs between actual compile and link before/after seals')
    for field in ('provider_inputs', 'system_libraries', 'build_tools'):
        rows, old_rows = report[field], state['donor'][field]
        left, right = {norm(row['original_path']): row for row in rows}, {norm(row['original_path']): row for row in old_rows}
        require(len(left) == len(rows) and len(right) == len(old_rows) and set(left) == set(right),
                'Provider/system/tool input coverage changed')
        for path, row in left.items():
            require((row['sha256'], row['bytes']) == (right[path]['sha256'], right[path]['bytes']) and
                    inputs.ref(row) == inputs.read(row['original_path']), 'Provider/system/tool current/frozen identity changed')
    require(set(report['provider_reports']) == set(state['donor']['provider_reports']), 'Provider report roles changed')
    for key, row in report['provider_reports'].items():
        old = state['donor']['provider_reports'][key]
        require((row['sha256'], row['bytes']) == (old['sha256'], old['bytes']) and
                inputs.ref(row) == inputs.read(row['original_path']), 'Provider report current/frozen identity changed')
    for key in ('compiler', 'linker', 'dumpbin'):
        require(world.same_ref(shared, report[key], state['donor'][key]), 'The actual build tool differs from B8')
        inputs.ref(report[key])
    for key in ('link_response', 'link_log', 'map'):
        inputs.ref(report[key])
    state['cpp_compilation'] = dict(state['compile_state']['cpp_compilation'],
        generated_header_consumers=generated_consumers, actual_ten_amd64_coff_objects=objects,
        actual_compile_return_object_seals_verified=True, actual_link_before_after_object_seals_verified=True,
        actual_link_response=link['response'],
        unchanged_project_sdk_system_input_count=len(current) - len(changed),
        full_compiler_input_count=len(current), providers_system_libraries_and_build_tools_unchanged=True)
    state['report'] = report
    return result


def payloads(shared, original, inputs, sources, prepared, state):
    result = original(inputs, sources, prepared)
    expected, _, _, _, _, _ = result
    catalog = state['catalog_preflight']
    scripts = catalog['scripts']
    parsed = {row['name']: row for row in scripts}
    require(len(parsed) == len(scripts) == len(expected) and set(parsed) == set(expected) and
            type(catalog['catalog_count']) is int and catalog['catalog_count'] == len(expected) and
            type(catalog['parsed_count']) is int and catalog['parsed_count'] == len(expected),
            'The parser-only preflight and actual PE expected payload inventories differ')
    for name, raw in expected.items():
        row = parsed[name]
        require(type(row['raw_bytes']) is int and row['raw_bytes'] == len(raw) and
                row['raw_sha256'] == digest(raw) and row['status'] == 'PASS_PARSE_ONLY' and
                type(row['lua_status']) is int and row['lua_status'] == 0,
                'The actual PE expected payload differs from its successful Lua preflight: ' + name)
    state['build_sequence'].update(catalog_all_registered_payload_digests_verified=True,
                                   catalog_registered_payload_count=len(expected))
    require(PANTHEON_NAMES <= set(expected), 'Complete current catalog omits Pantheon Lua/layout')
    raw_lua, raw_xml = inputs.ref(state['original']['lua']), inputs.ref(state['original']['xml'])
    require(expected['ChoosePantheonPopup'] == raw_lua, 'Registered Pantheon Lua differs from original raw bytes')
    tree = prepared['xml_control_trees']['PantheonLayout']
    require(shared.base.strip_tree(tree) == shared.base.xml_tree(ET.fromstring(raw_xml)) and
            tree['contextName'] == 'ChoosePantheonPopup' and tree['popupKind'] == 'Pantheon',
            'Pantheon serialized layout changed an original XML node, attribute or order')
    metadata = tree['pantheon']
    require(set(metadata) == {'policy', 'originalLayoutLua', 'originalLayoutXml', 'rowTemplate',
                              'reformationSupported', 'nativeAcceptanceVerified'} and
            metadata['policy'] == 'ORIGINAL_BNW_PANTHEON_ONLY_V1' and metadata['rowTemplate'] == 'ItemInstance' and
            metadata['reformationSupported'] is False and metadata['nativeAcceptanceVerified'] is False,
            'Pantheon layout metadata exceeds its actual supported/verified scope')
    for key, extension in (('originalLayoutLua', 'lua'), ('originalLayoutXml', 'xml')):
        require(shared.norm(metadata[key]['path']) == shared.norm(state['original'][extension]['path']) and
                inputs.ref(metadata[key]) == inputs.ref(state['original'][extension]), 'Pantheon layout original-source binding differs')
    policy = prepared['pantheon_policy']
    require(policy['context_name'] == 'ChoosePantheonPopup' and policy['popup_kind'] == 'Pantheon' and
            policy['layout_asset'] == 'PantheonLayout' and policy['lua_asset'] == 'ChoosePantheonPopup' and
            policy['row_template'] == 'ItemInstance' and type(policy['mode']) is int and policy['mode'] == 1 and
            policy['reformation_supported'] is False and policy['native_acceptance_verified'] is False and
            policy['renderer_verified'] is False, 'Prepared Pantheon policy differs')
    for key, extension in (('original_layout_lua', 'lua'), ('original_layout_xml', 'xml')):
        require(inputs.ref(policy[key]) == inputs.ref(state['original'][extension]), 'Prepared original Pantheon policy differs')
    report = state['report']
    require(inputs.read(PROJECT / 'evidence/ui_popup/assets/prepared.json') == inputs.ref(report['ui_assets']),
            'Current prepared UI report differs from its compiled frozen input')
    inputs.ref(prepared['inline_icon_catalog'], PROJECT / 'evidence/ui_popup/assets/inline_icons.json')
    state['pantheon_payloads'] = dict(original_lua=state['original']['lua'], original_xml=state['original']['xml'],
        original_xml_tree_equal=True, original_control_count=sum(1 for _ in ET.fromstring(raw_xml).iter()),
        original_lua_bytes_equal=True, metadata=metadata, expected_names=sorted(PANTHEON_NAMES),
        complete_catalog_count=len(expected), native_acceptance_verified=False)
    return result


def historical(shared, inputs, scope, current_scene, state):
    donor = state['donor']
    rows = {norm(row['original_path']): row for row in donor['compiler_inputs'] if row['root_name'] == 'project'}
    changes = {}
    for name in CPP:
        old, current = rows[norm(PROJECT / name)], scope['source_seals'][name]
        require(inputs.ref(old) != inputs.ref(current), 'B8 is not the declared changed-header negative')
        changes[name] = {'before': old, 'current': current}
    old_header = inputs.ref(scope['old_generated_header_recovery'])
    lengths, decoded, names = shared.base.generated_catalog(old_header, {'ZeroSisUiScene'})
    require(PANTHEON_NAMES.isdisjoint(names), 'B8 already declares a supposedly absent Pantheon script/layout')
    old_scene = decoded['ZeroSisUiScene']
    require(old_scene and old_scene != current_scene, 'B8 is not a different-current-Scene negative')
    image = inputs.ref(donor['executable'], PROJECT / 'Build/UiWindowHost' / BASE_BUILD / 'final/ZeroSisHost_x64.exe')
    pe = shared.PE(image)
    actual = shared.image_metadata(image, pe)
    require(actual == donor['executable']['pe'], 'Actual preserved B8 PE identity differs')
    imports = pe.imports()
    require(set(imports) == {name.casefold() for name in donor['imports']['dependencies']} and
            not any('gamecore' in name or 'civilization' in name for name in imports), 'Preserved B8 imports differ')
    catalog = pe.catalog(names, lengths, {'ZeroSisUiScene': old_scene})
    attestation_path = PROJECT / f'evidence/world_render/linked_candidate/attestation_{BASE_BUILD}.json'
    historical_ref = state['protected'].get(norm(attestation_path))
    require(historical_ref is not None, 'B8 historical PE receipt is not protected by this scope')
    receipt = json.loads(inputs.ref(historical_ref).decode('utf-8-sig'))
    require(receipt['status'] == 'PASS' and receipt['build_id'] == BASE_BUILD and
            receipt['executable']['sha256'] == donor['executable']['sha256'] and
            receipt['pe_catalog']['entry_count'] == len(names) and
            receipt['pe_catalog']['exact_payloads']['ZeroSisUiScene']['sha256'] == digest(old_scene),
            'B8 raw-byte negative differs from its preserved valid historical receipt')
    return dict(type='B8_PANTHEON_SOURCE_AND_REGISTERED_CATALOG_NEGATIVE', build_id=BASE_BUILD,
        actual_historical_pe_checked=True, actual_pe=actual, actual_pe_imports=imports,
        changed_existing_headers=changes, old_registered_catalog_count=len(names),
        missing_new_registered_names=sorted(PANTHEON_NAMES), historical_scene_sha256=digest(old_scene),
        current_scene_sha256=digest(current_scene), actual_old_catalog_table_rva=catalog['table_rva'],
        old_registered_scene_checked=True, historical_success_receipt=historical_ref,
        rejected_as_current_pantheon_feature=True, historical_camera_civilian_ui_feature_remains_valid=True,
        historical_full_catalog_receipt_replayed=False, native_execution_verified=False)


def publish(path, document, allowed_outputs):
    require(path.parent == STAGE and not os.path.lexists(path), 'Attestation publication must be fresh')
    allowed_outputs.add(norm(path))
    with path.open('x', encoding='utf8') as stream:
        json.dump(document, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    return {'path': str(path), 'bytes': path.stat().st_size, 'sha256': digest(path.read_bytes())}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--attempt', choices=('retry_01', 'retry_02'), default=None,
                        help='Explicitly select the separately scoped retry; omitted retains the initial attempt')
    args = parser.parse_args()
    require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id) and args.build_id != BASE_BUILD,
            'An exact fresh immutable build ID is required')
    output = STAGE / f'attestation_{args.build_id}.json'
    require(not os.path.lexists(output), 'Successful attestation already exists')
    allowed_outputs, forbidden = set(), []
    install_guard(allowed_outputs, forbidden)
    boundaries = dict(host_executed=False, gamecore_loaded=False, dll_loaded=False, hwnd_created=False,
        retail_MODS_saves_settings_or_game_processes_accessed=False, game_process_queries=0,
        actual_process_or_ctypes_library_calls=0, default_promoted=False, binary_modified=False,
        prior_scope_or_evidence_modified=False, runtime_prepared=False,
        native_sdk_pantheon_created_verified=False, native_pantheon_screen_verified=False,
        native_turn_blocker_release_verified=False, retail_ui_verified=False,
        retail_save_mod_compatibility_verified=False, full_engine_goal_complete=False)
    try:
        shared, state = scoped_bootstrap(args.attempt)
        result = shared.verify(args.build_id)
        require(not forbidden, 'Read-only verifier attempted a forbidden operation')
        seals = state['inputs'].finish()
        result.update(schema=SCHEMA, status='PASS', attempt=args.attempt or 'initial', utc=datetime.now(timezone.utc).isoformat(),
            actual_pe_inspected=True, source_stage=state['scope']['source_stage'],
            cpp_compilation=state['cpp_compilation'], pantheon=state['pantheon_payloads'],
            actual_build_sequence=state['build_sequence'], progress_observation=state['progress_observation'],
            source_inputs=state['scope']['source_seals'], verifier_dependencies=state['scope']['verifier_dependencies'],
            verifier_sha256=digest(Path(__file__).read_bytes()), forbidden_access_attempts=forbidden,
            read_input_count=len(seals), inputs_unchanged=True,
            read_input_seals_sha256=digest(json.dumps(seals, sort_keys=True).encode('utf8')),
            acceptance='CURRENT_SOURCE_COMPILE_LINK_AND_RAW_PE_ORIGINAL_PANTHEON_CATALOG_ONLY',
            external_pixel_renderer_embedded_in_pe=False, **boundaries)
        ref = publish(output, result, allowed_outputs)
        print(json.dumps(dict(status='PASS', build_id=args.build_id, report=ref,
            payloads=result['pe_catalog']['entry_count'], cpp_headers=len(CPP),
            actual_coff_objects=len(state['cpp_compilation']['actual_ten_amd64_coff_objects']),
            host_executed=False), ensure_ascii=False))
        return 0
    except Exception as error:
        failure = dict(schema=SCHEMA, status='FAIL', build_id=args.build_id, attempt=args.attempt or 'initial',
            utc=datetime.now(timezone.utc).isoformat(), scope_sha256=SCOPE_SHA,
            verifier_sha256=digest(Path(__file__).read_bytes()),
            error_type=type(error).__name__, error=str(error)[:2400],
            forbidden_access_attempts=forbidden, **boundaries)
        ref = publish(STAGE / ('failure_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'),
                      failure, allowed_outputs)
        print(json.dumps(dict(status='FAIL', build_id=args.build_id, report=ref, error=failure['error']), ensure_ascii=False))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
