"""Read-only PE and compile/link attestation for camera and civilian art sources.

Reuse the sealed overwrite wrapper and common raw-byte PE parser.  C++ source
approval, compiler profiles and per-TU consumers are additional contracts; no
native behavior is inferred from a source signature or an embedded UI payload.
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
import sys

PROJECT = Path(__file__).absolute().parents[3]
STAGE = Path(__file__).absolute().parent
SCOPE_SHA256 = 'c63aaa0a5d6dac258c430d719418db0948e8f1b36b73e0fd947ea5834d738f22'
DONOR = '20261016T122615Z_1af4a5449cf1'
SCHEMA = 'zerosis.world_camera_civilian_linked_pe_attestation.v1'
DEPENDENCIES = {
    'overwrite_wrapper': ('evidence/save_overwrite/linked_candidate/verify_candidate.py',
                          '98622bfbdd93fe19c0863fec397a5390272bc5a6f060cb26ed6babcf22009686'),
    'common_pe': ('evidence/save_delete/linked_candidate/verify_candidate.py',
                  'dd06ea0c0b31faa2423639eb2f95fdd11c3ffcd6ae1ae48a9505280e3d6ba4da'),
    'pe_base': ('Tests/verify_load_menu_linked_candidate.py',
                '54388cfc99f1e00e6143da71a64439d165f502b099d6c9e019524e48743aa3a2'),
}
APPROVALS = {
    'overwrite': ('evidence/save_overwrite/source_contract/conformance.json',
                  '7b69f3fca41b188d7ff6b403183f0cc2964d47d2e9f135ad9b339f7ff04e43cb',
                  'PASS_SOURCE_AND_COMPONENT_ONLY'),
    'camera': ('evidence/world_camera/controls/conformance.json',
               '9c21c35700576ed4aa4c6e8264f88571e1531624770c53a21057cd42306fbca2',
               'PASS_SOURCE_AND_HEADLESS_CONTROLS_ONLY'),
    'civilian': ('evidence/unit_models/civilian_start/conformance.json',
                 'c8417ed25b5949af2a7e7ab1fdb28c744e6d126fb83a32692f0dacb8d909d57d',
                 'PASS_SOURCE_COMPONENT_AND_ASSET_PREPARATION_ONLY'),
}
CPP_CONSUMERS = {
    'Source/Presentation/WorldCameraControls.h': ('host_main', 'world_renderer', 'terrain_renderer'),
    'Source/Presentation/WorldViewRenderer.h': ('host_main', 'world_renderer', 'terrain_renderer'),
    'Source/Host/InteractiveGameLoop.h': ('host_main',),
    'Source/Presentation/WorldViewRenderer.cpp': ('world_renderer',),
    'Source/Presentation/WorldTerrainRenderer.cpp': ('terrain_renderer',),
    'Source/Presentation/WorldUnitArtSelection.h': ('terrain_renderer',),
}
TUS = {
    'host_main': ('Source/Host/HostMain.cpp', 'HostMain'),
    'window': ('Source/Presentation/BitmapWindow.cpp', 'BitmapWindow'),
    'renderer': ('Source/Presentation/BitmapRenderer.cpp', 'BitmapRenderer'),
    'world_renderer': ('Source/Presentation/WorldViewRenderer.cpp', 'WorldViewRenderer'),
    'terrain_renderer': ('Source/Presentation/WorldTerrainRenderer.cpp', 'WorldTerrainRenderer'),
}
TERRAIN = 'Source/Presentation/WorldTerrainRenderer.cpp'
NEW_HEADERS = {'Source/Presentation/WorldCameraControls.h', 'Source/Presentation/WorldUnitArtSelection.h'}
PHASES = ('dependency_discovery', 'final_compilation')
RETIRED_LIVE_IDS = ('20261016T110835Z_800f48fd88c0', '20261016T111333Z_1c377d9577e6')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def same_ref(shared, left, right):
    """Compare identity; donor report references can legitimately omit bytes."""
    return (shared.norm(left['path']) == shared.norm(right['path']) and
            left['sha256'] == right['sha256'] and
            ('bytes' not in left or 'bytes' not in right or left['bytes'] == right['bytes']))


def ledger(shared, rows):
    result = {}
    require(type(rows) is list, 'Expected a sealed artifact list')
    for row in rows:
        require(type(row) is dict and type(row.get('bytes')) is int and row['bytes'] >= 0 and
                re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', '')) is not None,
                'Artifact list has an invalid size or digest')
        key = shared.norm(row['path'])
        require(key not in result, 'Duplicate normalized artifact path')
        result[key] = row
    return result


def same_ledger(shared, left, right):
    return set(left) == set(right) and all(same_ref(shared, left[key], right[key]) for key in left)


def relative(path):
    value = os.path.relpath(path, PROJECT).replace('\\', '/')
    require(value != '..' and not value.startswith('../') and not os.path.isabs(value),
            'Approved source escaped the current project')
    return value


def document_ref(inputs, row, expected=None):
    return json.loads(inputs.ref(row, expected).decode('utf-8-sig'))


def donor_project_sources(shared, donor):
    prefix = shared.norm(PROJECT / 'Source') + os.sep
    result = {}
    for row in donor['compiler_inputs']:
        key = shared.norm(row['original_path'])
        # SDK inputs also live beneath Source, but retain their own root role.
        # Their current/frozen bytes remain covered by the complete TU closure.
        if row.get('root_name') == 'project' and key.startswith(prefix):
            require(key not in result, 'Duplicate donor project dependency')
            result[key] = row
    return result


def translation_rows(report, phase):
    rows = report[phase]['translation_units']
    result = {row['translation_unit']: row for row in rows}
    require(len(result) == len(rows) and set(result) == set(TUS), 'Wrong exact translation-unit set')
    return result


def check_profile(lines, expected):
    require(lines and all(line and line == line.strip() for line in lines), 'Malformed compiler response lines')
    require([line for line in lines if line.startswith('/std:')] == [expected['language']] and
            [line for line in lines if line.startswith('/source-charset:')] == [expected['source_charset']],
            'Actual compiler language or source charset differs from its scoped profile')
    for flag in expected['required_flags']:
        require(lines.count(flag) == 1, 'Required compiler flag absent or duplicated: ' + flag)
    require(not any(line.startswith(flag) for flag in expected['forbidden_flags'] for line in lines),
            'Forbidden compiler flag is present')
    require([line for line in lines if line.startswith('/D')] == expected['defines_exact'],
            'Actual preprocessor definitions differ from their exact scoped order/content')


def nonpath_flags(lines):
    result = []
    for line in lines:
        if (re.fullmatch(r'/(?:external:I|I|Fo)"[^"\r\n]+"', line) or
                re.fullmatch(r'/sourceDependencies "[^"\r\n]+"', line) or
                re.fullmatch(r'"[^"\r\n]+\.(?:cpp|cxx|cc|c)"', line, re.I)):
            continue
        result.append(line)
    return result


def read_feature_scope(shared, inputs, state):
    scope_path = STAGE / 'scope.json'
    raw = inputs.read(scope_path)
    require(shared.digest(raw) == SCOPE_SHA256, 'Combined candidate scope changed')
    scope = json.loads(raw.decode('utf-8-sig'))
    require(scope['schema'] == 'zerosis.world_camera_civilian_linked_scope.v1' and
            scope['original_game_new_mod_test_hold'] is True and scope['retail_mod_test_hold_active'] is True and
            all(scope[key] is False for key in ('default_promoted', 'execution_allowed',
                                               'host_gamecore_hwnd_executed', 'full_engine_goal_complete')),
            'Combined candidate scope does not preserve the native/retail hold')
    inputs.read(Path(__file__))
    require(set(scope['verifier_dependencies']) == set(DEPENDENCIES), 'Verifier dependency ledger differs')
    for role, (name, expected_hash) in DEPENDENCIES.items():
        row = scope['verifier_dependencies'][role]
        require(row['sha256'] == expected_hash, 'Unapproved common verifier dependency')
        inputs.ref(row, PROJECT / name)
    for row in ledger(shared, scope['protected_artifacts']).values():
        inputs.ref(row)
    for key in ('header_recovery', 'prepared_assets_recovery', 'progress_before', 'progress_backup', 'builder', 'common_helper'):
        inputs.ref(scope[key])
    require(shared.norm(scope['builder']['path']) == shared.norm(PROJECT / 'tools/build_ui_window_host.py'),
            'Current Host builder lineage differs')
    require(same_ref(shared, scope['progress_before'], scope['progress_backup']) is False and
            scope['progress_before']['sha256'] == scope['progress_backup']['sha256'] and
            scope['progress_before']['bytes'] == scope['progress_backup']['bytes'],
            'Progress backup is not the distinct exact source-stage checkpoint')

    approvals = {}
    require(set(scope['prior_source_conformances']) == set(APPROVALS), 'Source approval roles differ')
    for role, (name, expected_hash, status) in APPROVALS.items():
        row = scope['prior_source_conformances'][role]
        require(row['sha256'] == expected_hash, 'Approved source-stage receipt changed')
        approvals[role] = document_ref(inputs, row, PROJECT / name)
        require(approvals[role]['status'] == status, 'Source-stage receipt has the wrong acceptance boundary')
    overwrite = ledger(shared, approvals['overwrite']['sources'])
    require(same_ledger(shared, overwrite, ledger(shared, scope['source19_seals'])),
            'Current overwrite source ledger differs from its preserved approval')
    for row in overwrite.values():
        inputs.ref(row)
    require({shared.norm(PROJECT / name) for name in shared.REQUIRED_FEATURE_SOURCES} <= set(overwrite),
            'The original seven overwrite feature inputs are not all approved')

    camera = ledger(shared, approvals['camera']['current_inputs'])
    civilian = ledger(shared, approvals['civilian']['current_source_files'])
    precedence = scope['source_precedence']
    require(len(precedence) == 1 and precedence[0]['relative'] == TERRAIN, 'Unexpected source-approval override')
    transition = precedence[0]
    terrain_key = shared.norm(PROJECT / TERRAIN)
    require(same_ref(shared, transition['superseded'], camera[terrain_key]) and
            same_ref(shared, transition['current'], civilian[terrain_key]) and
            same_ref(shared, transition['approval'], scope['prior_source_conformances']['civilian']),
            'Terrain source precedence is not the original camera-to-civilian approval chain')
    civilian_scope = document_ref(inputs, approvals['civilian']['proofs']['scope'])
    before = [row for row in civilian_scope['existing_files_before']
              if shared.norm(row['source']['path']) == terrain_key]
    require(len(before) == 1 and same_ref(shared, before[0]['source'], transition['superseded']) and
            same_ref(shared, before[0]['backup'], transition['superseded_backup']),
            'Civilian scope does not retain the original camera-approved terrain bytes')
    backup = inputs.ref(transition['superseded_backup'])
    require(len(backup) == transition['superseded']['bytes'] and
            shared.digest(backup) == transition['superseded']['sha256'], 'Superseded terrain backup changed')
    for key, row in camera.items():
        if key != terrain_key:
            inputs.ref(row)
    for row in civilian.values():
        inputs.ref(row)
    cpp = ledger(shared, scope['cpp_feature_seals'])
    require(set(cpp) == {shared.norm(PROJECT / name) for name in CPP_CONSUMERS}, 'Wrong exact C++ feature source set')
    for name in CPP_CONSUMERS:
        key = shared.norm(PROJECT / name)
        approved = civilian if name in (TERRAIN, 'Source/Presentation/WorldUnitArtSelection.h') else camera
        require(same_ref(shared, cpp[key], approved[key]), 'C++ input has no exact source-stage approval: ' + name)
        inputs.ref(cpp[key], PROJECT / name)

    syntax = document_ref(inputs, approvals['civilian']['proofs']['actual_current_consumer_syntax'])
    require(syntax['status'] == 'PASS' and syntax['linked'] is False and
            syntax['host_gamecore_hwnd_executed'] is False and
            syntax['retail_mods_user_saves_settings_or_processes_accessed'] is False,
            'Current civilian syntax proof exceeds its approved scope')
    syntax_before = ledger(shared, list(syntax['project_inputs_before'].values()))
    syntax_after = ledger(shared, list(syntax['project_inputs_after'].values()))
    require(same_ledger(shared, syntax_before, syntax_after) and
            len(syntax_before) == approvals['civilian']['verification']['current_cpp_dependencies'],
            'Current source syntax dependency accounting differs')
    for key, row in syntax_before.items():
        require(shared.norm(row['path']) == key, 'Invalid normalized syntax input identity')
        inputs.ref(row)
    require(set(cpp) <= set(syntax_before) and
            all(same_ref(shared, cpp[key], syntax_before[key]) for key in cpp),
            'Syntax receipt did not consume all six exact current C++ source inputs')

    donor = document_ref(inputs, scope['donor_build'],
                         PROJECT / 'evidence/ui_window_host' / DONOR / 'build_result.json')
    require(donor['build_id'] == DONOR and donor['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
            same_ref(shared, scope['donor_build'], scope['frozen_input_reuse_donor']) and
            same_ref(shared, scope['donor_build'], scope['cpp_negative_control']['build']),
            'Reuse and typed-negative donors are not the same protected B7 build')
    old_project = donor_project_sources(shared, donor)
    unchanged = ledger(shared, scope['unchanged_project_source_seals'])
    changed = scope['cpp_negative_control']['expected_changed_existing']
    changed_keys = {shared.norm(PROJECT / row['relative']) for row in changed}
    require(len(changed_keys) == len(changed) and changed_keys == set(cpp) -
            {shared.norm(PROJECT / name) for name in NEW_HEADERS} and
            set(unchanged) == set(old_project) - changed_keys,
            'Unchanged donor source closure does not exclude exactly the four approved modifications')
    for key, row in unchanged.items():
        require(inputs.ref(row) == inputs.ref(old_project[key]), 'A supposedly unchanged B7 source changed')
    baselines = scope['unchanged_baseline_seals']
    require(set(baselines) == {'Source/Host/UiLoadMenuContract.h', 'tools/prepare_ui_popup_assets.py'},
            'Unexpected unchanged overwrite baseline')
    donor_sources = {shared.norm(row['original_source']): row for row in donor['sources']}
    for name, row in baselines.items():
        current = inputs.ref(row, PROJECT / name)
        if name == 'Source/Host/UiLoadMenuContract.h':
            frozen = inputs.ref(donor_sources[shared.norm(PROJECT / name)])
        else:
            # The preparer is a frozen build tool, not a compiler-owned source.
            require(row['sha256'] == donor['source_hashes_before']['popup_asset_preparer'],
                    'Unchanged popup preparer differs from the B7 tool seal')
            frozen = inputs.read(PROJECT / 'Build/UiWindowHost' / DONOR / 'frozen/project' / name)
        require(current == frozen, 'Unchanged overwrite baseline differs from B7 frozen/current bytes')

    linked = document_ref(inputs, scope['prior_linked_conformance'])
    historical = document_ref(inputs, scope['historical_ui_attestation'])
    require(linked['status'].startswith('PASS') and historical['status'] == 'PASS' and
            historical['build_id'] == DONOR and historical['actual_pe_inspected'] is True and
            same_ref(shared, historical['build_report'], scope['donor_build']) and
            same_ref(shared, historical['executable'], donor['executable']),
            'Historical overwrite/UI receipt is not the protected B7 attestation')
    assets = scope['current_unit_assets']
    package = inputs.ref(assets['binary'])
    manifest = document_ref(inputs, assets['manifest'])
    preparation = document_ref(inputs, assets['preparation_contract'])
    require(package[:8] == b'ZSUNIT02' and manifest['status'] == 'PASS_ORIGINAL_UNIT_PACKAGE' and
            same_ref(shared, manifest['package'], assets['binary']) and
            same_ref(shared, approvals['civilian']['current_asset_package'], assets['binary']) and
            same_ref(shared, approvals['civilian']['proofs']['combined_asset_manifest'], assets['manifest']) and
            same_ref(shared, approvals['civilian']['proofs']['existing_preparation_contract'], assets['preparation_contract']) and
            preparation['status'] == 'PASS_EXISTING_PYTHON_PREPARATION_READERS_ONLY' and
            same_ref(shared, preparation['package'], assets['binary']) and
            same_ref(shared, preparation['manifest'], assets['manifest']) and
            preparation['host_gamecore_gpu_hwnd_executed'] is False and preparation['runtime_materialized'] is False and
            type(preparation['process_or_ctypes_library_calls_after_guard']) is int and
            preparation['process_or_ctypes_library_calls_after_guard'] == 0 and preparation['forbidden_attempts'] == [],
            'External civilian package is not the exact approved preparation-only input')
    require(set(scope['expected_cpp_consumers']) == set(CPP_CONSUMERS) and
            all(set(scope['expected_cpp_consumers'][key]) == set(value) and
                len(scope['expected_cpp_consumers'][key]) == len(value) for key, value in CPP_CONSUMERS.items()),
            'Scoped C++ consumer roles differ from the approved production include graph')
    require(set(scope['expected_compile_profile']['by_tu']) == set(TUS), 'Wrong compiler-profile TU set')
    pinned = {relative(row['path']): row for row in [*overwrite.values(), *cpp.values(), *baselines.values()]}
    require(len(pinned) == len(overwrite) + len(cpp) + len(baselines), 'Feature approval sets overlap')
    state.update(scope=scope, cpp=cpp, donor=donor, historical=historical,
                 source_approval=dict(source_precedence=precedence, syntax_receipt=approvals['civilian']['proofs']['actual_current_consumer_syntax'],
                                      current_syntax_dependency_count=len(syntax_before), external_unit_assets=assets))
    return scope_path, scope, pinned


def verify_compilation(shared, original, inputs, report, frozen_root, build_id, state):
    result = original(inputs, report, frozen_root, build_id)
    sources, generated, final_sets = result
    scope = state['scope']
    require(report['frozen_input_reuse']['donor_build_id'] == DONOR and
            report['frozen_input_reuse']['donor_report_sha256'] == scope['frozen_input_reuse_donor']['sha256'] and
            report['frozen_input_reuse']['donor_content_and_metadata_preserved'] is True,
            'New candidate did not preserve its declared frozen-input reuse donor')
    by_original = {shared.norm(row['original_path']): row for row in report['compiler_inputs']}
    rows_by_phase = {phase: translation_rows(report, phase) for phase in PHASES}
    donor_rows = {phase: translation_rows(state['donor'], phase) for phase in PHASES}
    dependency_sets, profiles = {}, {}
    for phase in PHASES:
        dependency_sets[phase], profiles[phase] = {}, {}
        for index, (role, (name, stem)) in enumerate(TUS.items()):
            row = rows_by_phase[phase][role]
            data = document_ref(inputs, row['dependency_report'])
            data = data.get('Data', data)
            dependency_sets[phase][role] = {shared.norm(path) for path in (data['Source'], *data['Includes'])}
            expected = scope['expected_compile_profile']['by_tu'][role]
            baseline_ref = expected['baseline_responses'][phase]
            require(same_ref(shared, baseline_ref, donor_rows[phase][role]['response']),
                    'Compiler profile baseline is not the declared B7 response')
            baseline = inputs.ref(baseline_ref).decode('utf-8-sig').splitlines()
            lines = inputs.ref(row['response']).decode('utf-8-sig').splitlines()
            check_profile(baseline, expected[phase])
            check_profile(lines, expected[phase])
            require(nonpath_flags(lines) == nonpath_flags(baseline), 'Compiler profile gained an unapproved flag or override')
            source = PROJECT / name if phase == 'dependency_discovery' else Path(by_original[shared.norm(PROJECT / name)]['path'])
            quoted_sources = [line[1:-1] for line in lines if re.fullmatch(r'"[^"\r\n]+\.(?:cpp|cxx|cc|c)"', line, re.I)]
            require(len(quoted_sources) == 1 and shared.norm(quoted_sources[0]) == shared.norm(source) == shared.norm(data['Source']),
                    'Compiler response/dependency source does not match its exact TU role')
            deps = [line[len('/sourceDependencies "'):-1] for line in lines if line.startswith('/sourceDependencies "') and line.endswith('"')]
            require(len(deps) == 1 and shared.norm(deps[0]) == shared.norm(row['dependency_report']['path']),
                    'Compiler dependency-output path differs from its recorded result')
            directory = 'dependency_discovery' if phase == 'dependency_discovery' else 'final'
            object_dir = PROJECT / 'Build/UiWindowHost' / build_id / directory / ('tu_%02d_%s' % (index, role)) / 'obj'
            destinations = [line[4:-1] for line in lines if line.startswith('/Fo"') and line.endswith('"')]
            require(len(destinations) == 1 and shared.norm(destinations[0]) == shared.norm(object_dir),
                    'Compiler output objects escape their exact private TU directory')
            profiles[phase][role] = dict(response=row['response'], baseline_response=baseline_ref,
                                         language=expected[phase]['language'], source_charset=expected[phase]['source_charset'],
                                         exact_defines=True, exact_nonpath_flag_sequence=True)
    consumers = {}
    for name, roles in CPP_CONSUMERS.items():
        key = shared.norm(PROJECT / name)
        require(key in by_original and inputs.ref(by_original[key]) == inputs.ref(state['cpp'][key]),
                'New frozen compiler closure does not contain the exact approved C++ input')
        frozen_key = shared.norm(by_original[key]['path'])
        actual_discovery = {role for role, paths in dependency_sets['dependency_discovery'].items() if key in paths}
        actual_final = {role for role, paths in final_sets.items() if frozen_key in paths}
        require(actual_discovery == actual_final == set(roles), 'C++ input was consumed by a different exact TU set: ' + name)
        consumers[name] = dict(current=state['cpp'][key], frozen=by_original[key],
                               discovery_consumers=sorted(actual_discovery), final_consumers=sorted(actual_final))
    objects = {}
    for index, (role, (_, stem)) in enumerate(TUS.items()):
        path = PROJECT / 'Build/UiWindowHost' / build_id / 'final' / ('tu_%02d_%s' % (index, role)) / 'obj' / (stem + '.obj')
        raw = inputs.read(path)
        require(len(raw) >= 20 and int.from_bytes(raw[:2], 'little') == 0x8664,
                'Linked final object is not an actual AMD64 COFF object')
        objects[role] = shared.artifact(path, inputs)
    state['cpp_compilation'] = dict(exact_source_consumers=consumers, actual_compile_profiles=profiles,
                                    final_amd64_objects=objects, exact_five_object_link_response=True,
                                    source_to_compile_link_lineage_verified=True, native_feature_behavior_verified=False)
    return result


def verify_historical_negative(shared, inputs, scope, current_scene, state):
    negative = scope['cpp_negative_control']
    require(negative['historical_ui_feature_remains_valid'] is True and set(negative['expected_missing_new']) == NEW_HEADERS and
            len(negative['expected_missing_new']) == len(NEW_HEADERS), 'Invalid typed historical negative contract')
    donor = state['donor']
    old = donor_project_sources(shared, donor)
    changed = []
    for row in negative['expected_changed_existing']:
        key = shared.norm(PROJECT / row['relative'])
        require(key in old and same_ref(shared, row['before'], old[key]) and
                same_ref(shared, row['current'], state['cpp'][key]), 'Historical C++ delta has the wrong before/current lineage')
        before, current = inputs.ref(row['before']), inputs.ref(row['current'])
        require(before != current, 'Declared historical C++ source did not change')
        changed.append(dict(relative=row['relative'], before=row['before'], current=row['current']))
    all_old = {shared.norm(row['original_path']) for row in donor['compiler_inputs']} | {
        shared.norm(row['original_source']) for row in donor['sources']}
    require(all(shared.norm(PROJECT / name) not in all_old for name in NEW_HEADERS),
            'Historical donor already declares a supposedly new feature header')
    image = inputs.ref(donor['executable'], PROJECT / 'Build/UiWindowHost' / DONOR / 'final/ZeroSisHost_x64.exe')
    pe = shared.PE(image)
    actual_pe = shared.image_metadata(image, pe)
    require(actual_pe == donor['executable']['pe'] and actual_pe == state['historical']['executable']['pe'],
            'Historical donor PE identity differs from its preserved build and UI receipt')
    imports = pe.imports()
    require(set(imports) == {name.casefold() for name in donor['imports']['dependencies']} and
            not any('gamecore' in name or 'civilization' in name for name in imports), 'Historical donor import identity differs')
    require(shared.digest(current_scene) == state['historical']['pe_catalog']['exact_payloads']['ZeroSisUiScene']['sha256'],
            'Unchanged overwrite UI receipt does not describe the current assembled Scene')
    return dict(type='B7_CPP_FEATURE_SOURCE_CLOSURE_NEGATIVE', build_id=DONOR, executable=donor['executable'],
                actual_historical_pe_checked=True, actual_pe=actual_pe, actual_pe_imports=imports,
                changed_existing_sources=changed, missing_new_headers=sorted(NEW_HEADERS),
                rejected_as_current_camera_civilian_cpp_feature=True, historical_overwrite_ui_feature_remains_valid=True,
                historical_ui_attestation=scope['historical_ui_attestation'], historical_ui_receipt_replayed=False,
                old_lua_difference_required=False, retired_b6_live_inputs=0,
                rejection='Four exact frozen C++ sources differ and both new feature headers are absent; the older UI feature remains valid')


def load_shared():
    raw = (STAGE / 'scope.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SCOPE_SHA256, 'Combined scope changed before verifier import')
    scope = json.loads(raw.decode('utf-8-sig'))
    for role, (name, expected_hash) in DEPENDENCIES.items():
        path = PROJECT / name
        require(sha(path) == expected_hash and scope['verifier_dependencies'][role]['sha256'] == expected_hash and
                os.path.normcase(os.path.abspath(scope['verifier_dependencies'][role]['path'])) == os.path.normcase(str(path)),
                'Sealed common verifier dependency changed before import')
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('zerosis_preserved_overwrite_pe_attestor', PROJECT / DEPENDENCIES['overwrite_wrapper'][0])
    overwrite = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(overwrite)
    overwrite.STAGE = STAGE
    shared = overwrite.load_shared()
    require(shared.norm(shared.PROJECT) == shared.norm(PROJECT) and
            shared.norm(shared.base.__file__) == shared.norm(PROJECT / DEPENDENCIES['pe_base'][0]),
            'Imported common verifier points to an unexpected project or base module')
    state = {}
    original_inputs = shared.Inputs

    class CurrentInputs(original_inputs):
        def __init__(self):
            super().__init__()
            state['inputs'] = self

        def read(self, path):
            require(not any(value.casefold() in shared.norm(path) for value in RETIRED_LIVE_IDS),
                    'Retired B6/R6 artifacts are historical receipt data, not live inputs to this stage')
            return super().read(path)

    shared.Inputs = CurrentInputs
    shared.STAGE = STAGE
    # Keep only the seven original host/UI feature requirements.  Art headers
    # are validated separately against their actual terrain-renderer consumer.
    shared.REQUIRED_FEATURE_SOURCES = overwrite.REQUIRED_CURRENT_FEATURE
    shared.read_feature_scope = lambda inputs: read_feature_scope(shared, inputs, state)
    original_compile = shared.verify_compilation
    shared.verify_compilation = lambda inputs, report, frozen, build_id: verify_compilation(
        shared, original_compile, inputs, report, frozen, build_id, state)
    # Fully replace L's different-Lua negative. B7 deliberately has the same UI.
    shared.verify_historical_negative = lambda inputs, scope, scene: verify_historical_negative(shared, inputs, scope, scene, state)
    return shared, state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--build-id')
    mode.add_argument('--readiness-only', action='store_true')
    args = parser.parse_args()
    shared, state = load_shared()
    if args.build_id:
        require(re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id) is not None and args.build_id != DONOR,
                'A fresh immutable build ID is required')
        require(not (STAGE / ('attestation_' + args.build_id + '.json')).exists(), 'Successful attestation already exists')
    boundaries = dict(host_executed=False, gamecore_loaded=False, dll_loaded=False, hwnd_created=False,
                      mods_or_user_saves_accessed=False, retail_user_settings_accessed=False, game_process_queries=0,
                      default_promoted=False, binary_modified=False, shared_attestor_or_historical_evidence_modified=False,
                      native_camera_controls_verified=False, native_civilian_rendering_verified=False,
                      native_binding_execution_verified=False, native_overwrite_verified=False,
                      retail_save_mod_compatibility_verified=False, full_engine_goal_complete=False)
    try:
        if args.readiness_only:
            inputs = shared.Inputs()
            scope_path, scope, pinned = read_feature_scope(shared, inputs, state)
            inputs.finish()
            result = dict(status='PASS_READ_ONLY_SOURCE_SCOPE_READY_NO_PE_INSPECTION', actual_pe_inspected=False,
                          candidate_scope=shared.artifact(scope_path, inputs), approved_feature_sources=pinned,
                          source_approval=state['source_approval'], retired_b6_live_inputs=0)
            filename = 'readiness_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json'
        else:
            result = shared.verify(args.build_id)
            result['executable'] = {**result['executable'], **shared.artifact(result['executable']['path'], state['inputs'])}
            result.update(status='PASS', actual_pe_inspected=True, source_approval=state['source_approval'],
                          cpp_compilation=state['cpp_compilation'], external_unit_assets=state['scope']['current_unit_assets'],
                          unit_package_embedded_in_pe=False, native_unit_package_consumption_verified=False,
                          retired_b6_live_inputs=0,
                          feature_scope='CURRENT_CAMERA_CIVILIAN_CPP_COMPILE_LINK_LINEAGE_AND_EXACT_ORIGINAL_UI_PE_PAYLOADS',
                          acceptance='PRIVATE_COMPILE_LINK_RAW_PE_UI_CATALOG_AND_EXTERNAL_UNIT_PACKAGE_IDENTITY_ONLY')
            filename = 'attestation_' + args.build_id + '.json'
    except Exception as error:
        failure = dict(schema=SCHEMA, status='FAIL', build_id=args.build_id, utc=datetime.now(timezone.utc).isoformat(),
                       error_type=type(error).__name__, error=str(error), verifier_sha256=sha(Path(__file__)), **boundaries)
        output = shared.write_new('failure_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ') + '.json', failure)
        print(json.dumps(dict(status='FAIL', report=str(output), error=str(error))))
        raise
    result.update(schema=SCHEMA, utc=datetime.now(timezone.utc).isoformat(), verifier_sha256=sha(Path(__file__)),
                  verifier_dependencies=state['scope']['verifier_dependencies'], **boundaries)
    output = shared.write_new(filename, result)
    print(json.dumps(dict(status=result['status'], build_id=args.build_id, report=str(output), sha256=sha(output),
                          payloads=len(result.get('pe_catalog', {}).get('exact_payloads', {})),
                          cpp_inputs=len(state['cpp']), host_executed=False)))


if __name__ == '__main__':
    main()
