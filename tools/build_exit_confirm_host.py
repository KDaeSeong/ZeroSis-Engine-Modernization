"""Freeze and build one ExitConfirm Host without loading a game image.

Preflight reads sealed inputs only. A build consumes the exact saved preflight
once, invokes one environment command, five compiler commands and one linker
command, and retains its objects for independent attestation and cleanup.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import types


PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / 'evidence/game_menu/exit_host_build'
PARENT_ID = '20261024T082423Z_b604cddf0d2d'
PARENT_ROOT = PROJECT / 'Build/UiWindowHost' / PARENT_ID
PARENT_REPORT = PROJECT / 'evidence/ui_window_host' / PARENT_ID / 'build_result.json'
PARENT_SHA = '6d771614f6a696b260e8aa8e401a3a5b8fd63295346f171eec6a9807a9d01844'
PARENT_STARTED_SHA = '0ee77ea1cad3f010dd1fa5ff30c1e3b3ece4cf99f4d5eefc1910aee5e5952613'
FIRST_PREFLIGHT_SHA = '83b295db74fe1060d6fed7f1e016151dca0f1bf56d21f3c34a557e5e3668f4b5'
FIRST_BUILDER_SHA = 'ff957d92a7437ac906e7d604ac03695b6b2c7e29454d992fd87855aff233cd7e'
FIRST_FAILURE_SHA = '4ace078a31d0cbf588b58d08d36ce7be9e1bc5a92a448eefb88b405a835a4d5e'
PARSER_PATH = PROJECT / 'evidence/goody_hut/owned_fonts/verify_candidate.py'
PARSER_SHA = '723e8d4594ce148336149f34c2ee535512c14ad283165b4fd729473eb302123f'
HELPER_PATH = PROJECT / 'tools/build_native_restore_host.py'
HELPER_SHA = '07f50b1ab7482591792b44cc8767f27c709884f5f487b0eada7459f28c8da558'
VCVARS_SHA = '6b516d8fcf543c14b2d861e1f45661e0029230fe0dc48e86ce78522801822209'
SOURCE_MANIFEST = PROJECT / 'evidence/game_menu/offline_exit/source_manifest.json'
SOURCE_AUDIT = PROJECT / 'evidence/game_menu/offline_exit/final_audit.json'
UNITS = ('host_main', 'window', 'renderer', 'world_renderer', 'terrain_renderer')
STEMS = ('HostMain', 'BitmapWindow', 'BitmapRenderer', 'WorldViewRenderer', 'WorldTerrainRenderer')
COUNTS = (466, 266, 270, 279, 301)
IMPLICIT = {'msvcrt.lib', 'msvcprt.lib', 'vcruntime.lib', 'oldnames.lib',
            'bcrypt.lib', 'kernel32.lib', 'ucrt.lib', 'uuid.lib'}
GROUPS = ('compiler_inputs', 'sources', 'provider_inputs', 'system_libraries',
          'implicit_libraries', 'build_tools')
MARKER = b'NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|'
HEADER = PROJECT / 'Source/Host/UiPopupAssets.generated.h'
PREPARED = PROJECT / 'evidence/ui_popup/assets/prepared.json'
ASSETS = ('Source/Assets/UI/Assets/UI/FrontEnd/ExitConfirm.lua',
          'Source/Assets/UI/Assets/UI/FrontEnd/ExitConfirm.xml')
SUPPORT = ('tools/prepare_ui_popup_assets.py', 'tools/interactive_ui_driver.py',
           'tools/ui_pixel_scene.py', 'tools/render_ui_popup.py',
           'tools/refresh_exit_confirm_ui_assets.py', 'tools/build_exit_confirm_host.py')
REPLACED = ('Source/Host/UiPopupContext.h', 'Source/Host/InteractiveGameLoop.h',
            'Source/Host/InteractiveGameSession.h', 'Source/Host/InteractiveUiSession.h',
            'Source/Host/UiScene.lua', 'Source/Presentation/UiPresentationInput.lua',
            'Source/Host/UiPopupAssets.generated.h', 'evidence/ui_popup/assets/prepared.json')
ADDENDA = (('Source/Presentation/UiCityView.lua', 'hasRetainedCityUi'),
           ('Source/Presentation/UiUnitPanel.lua', 'hasRetainedUnitUi'),
           ('Source/Presentation/UiSocialPolicy.lua', 'hasRetainedSocialPolicyUi'),
           ('Source/Presentation/UiEconomicOverview.lua', 'hasRetainedEconomicUi'),
           ('Source/Presentation/UiActionInfoPanel.lua', 'hasRetainedActionInfoUi'),
           ('Source/Presentation/UiNotificationPanel.lua', 'hasRetainedNotificationUi'))
ACTIVE_GUARD = None


def require(condition, message):
    if not condition:
        raise ValueError(message)


def key(path):
    return os.path.normcase(os.path.abspath(path))


def inside(path, root):
    return Path(key(path)).is_relative_to(Path(key(root)))


def ordinary(path):
    path = Path(os.path.abspath(path))
    for item in (path, *path.parents):
        if os.path.lexists(item):
            require(not item.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    'Reparse point in input or output path: ' + str(item))
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), 'Not an ordinary file: ' + str(path))
    return info


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_file_attributes)


def artifact(path):
    path = Path(os.path.abspath(path))
    before = ordinary(path)
    if ACTIVE_GUARD is not None:
        ACTIVE_GUARD.reads.add(key(path))
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    after = ordinary(path)
    require(identity(before) == identity(after) and before.st_nlink == after.st_nlink,
            'Input changed while hashing: ' + str(path))
    return dict(path=str(path), bytes=after.st_size, sha256=digest,
                file_identity=[after.st_dev, after.st_ino], mtime_ns=after.st_mtime_ns,
                file_attributes=after.st_file_attributes, links=after.st_nlink)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True).encode('ascii')


def digest_json(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def normalized(row, metadata=True):
    require(type(row) is dict, 'Artifact row is not an object')
    result = dict(row)
    require(type(result.get('path')) is str and Path(result['path']).is_absolute(), 'Artifact path is not absolute')
    require(type(result.get('bytes')) is int and result['bytes'] >= 0, 'Artifact size is missing or invalid')
    require(type(result.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', result['sha256']),
            'Artifact hash is missing or invalid')
    if 'attributes' in result:
        require('file_attributes' not in result or result['file_attributes'] == result['attributes'],
                'Conflicting file attribute aliases')
        result['file_attributes'] = result.pop('attributes')
    if 'link_count' in result:
        require('links' not in result or result['links'] == result['link_count'], 'Conflicting link count aliases')
        result['links'] = result.pop('link_count')
    if metadata:
        require(type(result.get('file_identity')) is list and len(result['file_identity']) == 2 and
                all(type(part) is int and part >= 0 for part in result['file_identity']),
                'Artifact file identity is missing or invalid: ' + result['path'])
        require(type(result.get('mtime_ns')) is int and type(result.get('file_attributes')) is int,
                'Artifact timestamp or attributes are missing: ' + result['path'])
    if 'links' in result:
        require(type(result['links']) is int and result['links'] >= 1, 'Invalid artifact link count')
    return result


def sealed(row, metadata=True, links=False):
    row = normalized(row, metadata)
    current = artifact(row['path'])
    names = ['bytes', 'sha256'] + (['file_identity', 'mtime_ns', 'file_attributes'] if metadata else [])
    if links:
        require('links' in row, 'Expected link count is missing: ' + row['path'])
        names.append('links')
    for name in names:
        require(current[name] == row[name], 'Artifact ' + name + ' differs: ' + row['path'])
    return current


def pin(path, digest):
    current = artifact(path)
    require(current['sha256'] == digest, 'Pinned input differs: ' + str(path))
    return current


def read_bytes(row, maximum=32 * 1024 * 1024):
    row = normalized(row)
    require(row['bytes'] <= maximum, 'Input exceeds the read bound: ' + row['path'])
    raw = Path(row['path']).read_bytes()
    require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
            'Input changed while reading: ' + row['path'])
    sealed(row)
    return raw


def unique_object(pairs):
    value = {}
    for name, item in pairs:
        require(name not in value, 'Duplicate JSON key: ' + name)
        value[name] = item
    return value


def document(path, digest=None):
    row = pin(path, digest) if digest else artifact(path)
    value = json.loads(read_bytes(row).decode('utf-8-sig'), object_pairs_hook=unique_object,
                       parse_constant=lambda token: require(False, 'Nonfinite JSON number: ' + token))
    require(type(value) is dict, 'JSON document is not an object: ' + str(path))
    return value, row


def load_pure(path, digest, name):
    row = pin(path, digest)
    raw = read_bytes(row)
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    sealed(row)
    return module, row


def parser69(parser):
    """Change only the authenticated parser's one catalog count AST constant."""
    raw = read_bytes(pin(PARSER_PATH, PARSER_SHA))
    tree = ast.parse(raw, filename=str(PARSER_PATH))
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'parse_catalog']
    require(len(functions) == 1, 'Authenticated catalog parser definition is ambiguous')
    original = ast.dump(functions[0], include_attributes=False)
    matches = [node for node in ast.walk(functions[0]) if isinstance(node, ast.Constant) and type(node.value) is int and node.value == 67]
    require(len(matches) == 1, 'Authenticated parser no longer has one 67-entry count')
    matches[0].value = 69
    modified = ast.dump(functions[0], include_attributes=False)
    matches[0].value = 67
    require(ast.dump(functions[0], include_attributes=False) == original, 'Catalog parser inverse AST differs')
    matches[0].value = 69
    env = {'re': re, 'require': parser.require}
    exec(compile(ast.fix_missing_locations(ast.Module(body=functions, type_ignores=[])),
                 str(PARSER_PATH) + ':count69', 'exec'), env)
    return env['parse_catalog'], dict(original_ast_sha256=hashlib.sha256(original.encode()).hexdigest(),
                                    adapted_ast_sha256=hashlib.sha256(modified.encode()).hexdigest(),
                                    changed_integer_constants=[dict(before=67, after=69)], inverse_ast_equal=True)


def dependency_paths(row):
    value, _ = document(row['path'], row['sha256'])
    require(value.get('Version') == '1.2' and type(value.get('Data')) is dict, 'Unexpected dependency schema')
    data = value['Data']
    require(type(data.get('Source')) is str and type(data.get('Includes')) is list and
            all(type(item) is str for item in data['Includes']) and not data.get('ProvidedModule') and
            not data.get('ImportedModules') and not data.get('ImportedHeaderUnits'), 'Malformed dependency paths')
    visits = [data['Source'], *data['Includes']]
    return {key(item) for item in visits}, len(visits)


def rows_by_path(rows, original=None):
    result = {}
    for row in rows:
        normalized(row)
        name = row[original] if original else row['path']
        require(type(name) is str and key(name) not in result, 'Duplicate input mapping: ' + str(name))
        result[key(name)] = row
    return result


def ensure_scene(arrays, current):
    def raw(relative):
        return read_bytes(current[key(PROJECT / relative)])
    scene = raw('Source/Host/UiScene.lua') + b'\n' + raw('Source/Presentation/UiPresentationInput.lua')
    for relative, flag in ADDENDA:
        scene += ('\nif ' + flag + ' then\n').encode('ascii') + raw(relative) + b'\nend\n'
    require(arrays['ZeroSisUiScene'] == scene, 'Generated scene is not the exact current eight-file composition')
    for symbol in ('ProductionCommandGuard', 'ResearchCommandGuard'):
        require(arrays[symbol] == raw('Source/Host/' + symbol + '.lua'), 'Generated current Lua guard differs: ' + symbol)
    # The production generator appends each snapshot's read_bytes() payload.
    require(arrays['ExitConfirm'] == raw(ASSETS[0]), 'Generated ExitConfirm Lua differs from preserved original bytes')


def storage_gate(value):
    require(value.get('schema') == 'zerosis.exit_host_build.storage_before.v1' and
            value.get('status') == 'PASS_TRUE_ID_DEDUPLICATED_STORAGE_BASELINE',
            'Storage baseline schema or completion status differs')
    require(value.get('errors') == [] and value.get('disposable_threshold_exceeded') is False and
            value.get('source_replacement_released_after_this_receipt') is True,
            'Storage baseline has unresolved errors or has not released source replacement')
    candidates = []
    def visit(node):
        if isinstance(node, dict):
            for name, item in node.items():
                if name in ('disposable_bytes', 'confirmed_disposable_bytes', 'disposable_unique_bytes', 'dummy_bytes'):
                    require(type(item) is int and item >= 0, 'Invalid disposable byte count')
                    candidates.append(item)
                elif isinstance(item, (dict, list)):
                    visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)
    visit(value)
    require(candidates and max(candidates) <= 10 * 1024 ** 3, 'Storage baseline lacks a bounded disposable-byte inventory')
    return dict(disposable_byte_values=candidates, threshold_bytes=10 * 1024 ** 3)


def permission_context(path):
    """Validate one explicit new attempt after the zero-child permission failure."""
    failures = {key(item) for item in (STAGE / 'attempts').glob('*/failure.json')}
    if path is None:
        require(not failures, 'A terminal attempt exists; an explicit pinned permission-resolution context is required')
        return None, None, []
    require(inside(path, STAGE), 'Permission resolution must be inside this stage')
    resolution, resolution_ref = document(path)
    require(resolution.get('schema') == 'zerosis.exit_host_build.permission_resolution.v1' and
            resolution.get('status') == 'EXPLICIT_ROOT_RESUME_AFTER_PERMISSION_RESOLUTION' and
            resolution.get('explicit_root_resume') is True and type(resolution.get('authorization_source')) is str and
            resolution['authorization_source'], 'Permission resolution lacks an explicit root resume instruction')
    execution = resolution.get('execution', {})
    require(execution == dict(required_sandbox_permissions='require_escalated', new_signature_required=True,
                              reuse_previous_attempt_allowed=False, automatic_retry_allowed=False,
                              native_host_sdk_clr_window_gpu_or_dll_execution_allowed=False),
            'Permission resolution changed execution, reuse or retry policy')
    require(resolution.get('preservation') == dict(previous_attempt_must_remain=True,
                previous_source_must_reconstruct_from_gzip=True, copy_all_fallback_allowed=False),
            'Permission resolution changed preservation or copy fallback policy')
    old_ref = sealed(resolution['previous_preflight'], links=True)
    require(old_ref['sha256'] == FIRST_PREFLIGHT_SHA and key(old_ref['path']) == key(STAGE / 'builder_preflight.json'),
            'Permission resolution references an unknown earlier preflight')
    old, _ = document(old_ref['path'], FIRST_PREFLIGHT_SHA)
    old_signature = digest_json(old)
    original = normalized(resolution['previous_builder_source'], metadata=False)
    require(key(original['path']) == key(Path(__file__)) and original['sha256'] == FIRST_BUILDER_SHA and
            old['inputs']['builder']['sha256'] == FIRST_BUILDER_SHA and old['inputs']['builder']['bytes'] == original['bytes'],
            'Earlier builder identity does not match the saved original source')
    backup_ref = sealed(resolution['previous_builder_backup'], links=True)
    require(inside(backup_ref['path'], STAGE / 'source_backups') and backup_ref['bytes'] < 1024 * 1024,
            'Original builder backup is outside the narrow recovery scope')
    restored = gzip.decompress(read_bytes(backup_ref, 1024 * 1024))
    require(len(restored) == original['bytes'] and hashlib.sha256(restored).hexdigest() == FIRST_BUILDER_SHA,
            'Original builder source does not reconstruct exactly')
    prior_root = STAGE / 'attempts' / old_signature[:20]
    failure_ref = sealed(resolution['previous_failure'], links=True)
    started_ref = sealed(resolution['previous_started'], links=True)
    require(key(failure_ref['path']) == key(prior_root / 'failure.json') and failure_ref['sha256'] == FIRST_FAILURE_SHA and
            key(started_ref['path']) == key(prior_root / 'started.json') and failures == {key(failure_ref['path'])},
            'Terminal failure history differs; review a fresh resolution rather than retrying')
    failure, _ = document(failure_ref['path'], FIRST_FAILURE_SHA)
    started, _ = document(started_ref['path'], started_ref['sha256'])
    require(failure.get('status') == 'FAILED_DO_NOT_REPLAY' and failure.get('signature') == old_signature and
            failure.get('commands') == [] and failure.get('completed_translation_units') == [] and
            failure.get('materialized') == [] and failure.get('denied_operations') == [] and
            failure.get('compilation_retry_allowed') is False and
            failure.get('host_sdk_clr_window_gpu_or_dll_executed') is False and
            '[WinError 5]' in failure.get('error', ''), 'Previous failure is not the zero-child OS hardlink denial')
    require(started.get('signature') == old_signature and started.get('build_id') == failure['build_id'] and
            started['reviewed_preflight']['sha256'] == FIRST_PREFLIGHT_SHA and
            started['inputs']['builder']['sha256'] == FIRST_BUILDER_SHA,
            'Previous started record differs from the terminal attempt')
    previous_build = PROJECT / 'Build/UiWindowHost' / failure['build_id']
    require(previous_build.is_dir() and previous_build.name.endswith(old_signature[:12]), 'Previous build identity differs')
    previous_files = []
    for parent, directories, filenames in os.walk(previous_build, followlinks=False):
        for item in (Path(parent), *(Path(parent) / name for name in directories)):
            require(not item.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    'Previous attempt has a reparse point; do not reuse it')
        previous_files.extend(str(Path(parent) / name) for name in filenames)
    require(not previous_files, 'Previous attempt contains files; review separately and never reuse partial outputs')
    probe_ref = sealed(resolution['hardlink_permission_probe'], links=True)
    require(key(probe_ref['path']) == key(STAGE / 'hardlink_permission_probe.json'), 'Unknown permission probe path')
    probe, _ = document(probe_ref['path'], probe_ref['sha256'])
    donor = old['frozen_plan'][0]['source']
    require(old['frozen_plan'][0]['method'] == 'attested_snapshot_hardlink' and
            probe.get('status') == 'PASS_HARDLINK_CREATE_AND_EXACT_UNLINK' and
            key(probe['source']) == key(donor['path']) and probe.get('source_sha256') == donor['sha256'] and
            probe.get('source_id') == donor['file_identity'] and probe.get('before_links') == donor['links'] and
            probe.get('source_unchanged') is True and probe.get('target_deleted') is True and
            probe.get('game_host_sdk_or_window_executed') is False,
            'Escalated same-donor permission probe did not preserve the original')
    require(inside(probe['target'], STAGE / 'hardlink_probe') and not os.path.lexists(probe['target']),
            'Permission probe target remains or is outside the exact probe scope')
    sealed(donor, links=True)
    evidence = [old_ref, backup_ref, failure_ref, started_ref, probe_ref]
    summary = dict(status='PASS_EXPLICIT_PERMISSION_RESOLUTION_NEW_ATTEMPT_ONLY', previous_signature=old_signature,
                   previous_build_id=failure['build_id'], previous_build_file_count=0, previous_direct_child_commands=0,
                   previous_materialized_files=0, previous_guard_denials=0, original_builder_reconstruction_exact=True,
                   same_donor_probe_pass=True, source_metadata_and_links_preserved=True,
                   required_sandbox_permissions='require_escalated', automatic_retry_allowed=False,
                   previous_attempt_reuse_allowed=False, copy_all_fallback_allowed=False)
    return summary, resolution_ref, evidence


def prepare_plan(permission_resolution=None):
    require(os.name == 'nt' and sys.dont_write_bytecode and __debug__, 'Use Windows Python with -B and without -O')
    require(not any(value for name, value in os.environ.items() if name.upper() in ('CL', '_CL_', 'LINK')),
            'Ambient compiler or linker injection options are not allowed')
    resume, resume_ref, resume_evidence = permission_context(permission_resolution)
    requirements, requirements_ref = document(STAGE / 'requirements.json')
    require(requirements.get('schema') == 'zerosis.exit_host_build.requirements.v1' and
            requirements['inputs']['parent_host_id'] == PARENT_ID and
            requirements['inputs']['parent_report_sha256'] == PARENT_SHA, 'Requirements parent identity differs')
    require(requirements['runtime_approval']['native_or_screen_execution_allowed'] is False and
            requirements['runtime_approval']['game_Host_GameCore_SDK_CLR_HWND_GPU_execution'] is False,
            'Requirements no longer preserve the execution hold')
    source_before, source_before_ref = document(STAGE / 'source_before.json')
    require(source_before.get('schema') == 'zerosis.exit_host_build.source_before.v1', 'Unexpected recovery schema')
    embedding, embedding_ref = document(STAGE / 'ui_embedding_result.json')
    protection, protection_ref = document(STAGE / 'protection_before.json')
    storage, storage_ref = document(STAGE / 'storage_before.json')
    storage_check = storage_gate(storage)
    names = [name for name in ('protected_artifacts', 'protected') if name in protection]
    require(protection.get('schema') == 'zerosis.exit_host_build.protection_before.v1' and
            protection.get('status') == 'PASS_DIRECT_HASH_SEALED_PROTECTED_BASELINE' and
            len(names) == 1 and type(protection[names[0]]) is list and
            protection[names[0]], 'Protected-input manifest is missing or ambiguous')
    protected = [sealed(row, links=True) for row in protection[names[0]]]
    require(len({key(row['path']) for row in protected}) == len(protected), 'Duplicate protected path')
    base, parent_ref = document(PARENT_REPORT, PARENT_SHA)
    require(base.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and base.get('build_id') == PARENT_ID,
            'Parent is not the expected successful offline build')
    require((len(base['compiler_inputs']), len(base['sources']), len(base['current_source_inputs'])) == (550, 86, 593),
            'Attested parent cardinalities differ')
    manifest, manifest_ref = document(SOURCE_MANIFEST, requirements['inputs']['source_manifest_sha256'])
    source_audit, audit_ref = document(SOURCE_AUDIT, requirements['inputs']['source_audit_sha256'])
    require(manifest.get('status') == 'SOURCE_AND_OFFLINE_CHECKS_COMPLETE_RUNTIME_NOT_BUILT' and
            source_audit.get('current_native_or_screen_relaunch_allowed') is False,
            'Completed source-only evidence or native hold differs')
    production = {key(row['path']): sealed(row, metadata=False) for row in manifest['production_sources']}
    require(len(production) == 12, 'Completed ExitConfirm source inventory differs')
    expected_production = {key(PROJECT / name) for name in (*REPLACED[:6], *ASSETS, *SUPPORT[:4])}
    require(set(production) == expected_production, 'ExitConfirm production source paths differ')
    donors = {}
    for group in GROUPS:
        for row in base[group]:
            require(inside(row['path'], PARENT_ROOT / 'frozen'), 'Parent input is outside its frozen root')
            actual = sealed(row)
            if key(row['path']) in donors:
                require(donors[key(row['path'])] == actual, 'Conflicting duplicate donor metadata')
            donors[key(row['path'])] = actual
    for row in [*base['provider_reports'].values(), base['shared_lua_build'], base['ui_assets']]:
        require(inside(row['path'], PARENT_ROOT / 'frozen'), 'Parent report is outside its frozen root')
        actual = sealed(row)
        require(key(row['path']) not in donors or donors[key(row['path'])] == actual, 'Conflicting duplicate donor report')
        donors[key(row['path'])] = actual
    require(len(donors) == len(base['current_source_inputs']), 'Parent donor/source closure correspondence differs')
    old_compiler = rows_by_path(base['compiler_inputs'], 'original_path')
    old_sources = rows_by_path(base['sources'], 'original_source')
    old_current = rows_by_path(base['current_source_inputs'])
    for label, current_path, backup in (('header', HEADER, old_compiler[key(HEADER)]),
                                        ('prepared', PREPARED, base['ui_assets'])):
        old = normalized(source_before['mutable_header' if label == 'header' else 'mutable_prepared_report'])
        recovery = normalized(source_before['header_recovery_ref' if label == 'header' else 'prepared_recovery_ref'])
        require(key(old['path']) == key(current_path) and old.get('links') == 1 and
                key(recovery['path']) == key(backup['path']), 'Recovery path or mutable ownership differs')
        require((old['bytes'], old['sha256']) == (backup['bytes'], backup['sha256']) and
                recovery['file_identity'] != old['file_identity'], 'Recovery aliases or differs from mutable old input')
        sealed(recovery)
    require(embedding.get('schema') == 'zerosis.exit_ui_embedding.v1' and
            embedding.get('status') == 'PASS_FILE_ONLY_UI_ASSETS_EMBEDDED_NOT_HOST_LINKED_OR_EXECUTED' and
            embedding.get('new_catalog_payload_count') == 69 and embedding.get('new_layout_count') == 27 and
            embedding.get('current_host_lua_count') == 10 and embedding.get('native_code_executed') is False and
            embedding.get('full_asset_preparer_main_executed') is False and
            embedding.get('installed_game_or_mods_or_saves_written') is False and
            embedding.get('pending_output_files_remaining') is False,
            'UI embedding report schema, completion, source counts or execution hold differs')
    for name, expected in (('requirements', requirements_ref), ('source_before', source_before_ref), ('storage_baseline', storage_ref)):
        require(name in embedding and key(embedding[name]['path']) == key(expected['path']) and
                embedding[name]['sha256'] == expected['sha256'], 'Embedding input receipt differs: ' + name)
    for name, path in (('generated_header', HEADER), ('prepared_report', PREPARED),
                       ('producer', PROJECT / SUPPORT[-2])):
        require(name in embedding and key(embedding[name]['path']) == key(path), 'Embedding output/producer reference differs: ' + name)
        sealed(embedding[name], metadata=False)
    changed = {key(PROJECT / name): artifact(PROJECT / name) for name in REPLACED}
    require(set(changed) <= set(old_current), 'A planned replacement is absent from the parent current-input inventory')
    require(all((changed[name]['bytes'], changed[name]['sha256']) !=
                (old_current[name]['bytes'], old_current[name]['sha256']) for name in changed),
            'A planned replacement still contains its parent bytes')
    additions = {key(PROJECT / name): artifact(PROJECT / name) for name in (*ASSETS, *SUPPORT)}
    require(not set(additions) & set(old_current), 'An added source already exists in parent current inputs')
    live = {}
    for row in base['current_source_inputs']:
        live[key(row['path'])] = changed[key(row['path'])] if key(row['path']) in changed else sealed(row)
    live.update(additions)
    require(all(production[name]['sha256'] == live[name]['sha256'] for name in production),
            'Completed production source changed during planning')
    parser, parser_ref = load_pure(PARSER_PATH, PARSER_SHA, 'zerosis_exit_static_pe')
    helper, helper_ref = load_pure(HELPER_PATH, HELPER_SHA, 'zerosis_exit_build_functions')
    parse69, adapter = parser69(parser)
    old_arrays, old_order = parser.parse_catalog(read_bytes(donors[key(old_compiler[key(HEADER)]['path'])]))
    arrays, order = parse69(read_bytes(changed[key(HEADER)]))
    require(set(order) == set(old_order) | {'ExitConfirm', 'ExitConfirmLayout'} and
            [name for name in order if name not in ('ExitConfirm', 'ExitConfirmLayout')] == old_order,
            'Generated 69-entry catalog does not preserve the prior registry')
    require(sum(name.endswith('Layout') for name in order) == 27, 'Generated layout count differs')
    ensure_scene(arrays, live)
    parent_pe = parser.PE(read_bytes(sealed(base['executable'])))
    require(helper.catalog_summary(parent_pe.catalog(old_arrays, old_order)) == base['catalog'],
            'Parent catalog attestation differs')
    require(len(parent_pe.imports()) == 24 and set(parent_pe.imports()) == set(base['imports']['dependencies']),
            'Parent import attestation differs')
    require(len(parent_pe.occurrences(MARKER)) == 1, 'Parent restore marker differs')
    catalog_rows = [dict(name=name, index=index, bytes=len(arrays[name]), sha256=hashlib.sha256(arrays[name]).hexdigest())
                    for index, name in enumerate(order)]
    catalog_expected = dict(entry_count=len(order), stride=24, total_payload_bytes=sum(row['bytes'] for row in catalog_rows),
                            ordered_payload_manifest_sha256=digest_json(catalog_rows))
    units = base['final_compilation']['translation_units']
    require(tuple(row['translation_unit'] for row in units) == UNITS, 'Parent TU sequence differs')
    dependency_sets, responses = {}, {}
    for index, row in enumerate(units):
        response = sealed(row['response'])
        dependency = sealed(row['dependency_report'])
        paths, _ = dependency_paths(dependency)
        require(len(paths) == COUNTS[index] and all(inside(path, PARENT_ROOT / 'frozen') for path in paths),
                'Parent TU dependency shape differs: ' + UNITS[index])
        dependency_sets[UNITS[index]] = sorted(paths)
        responses[UNITS[index]] = read_bytes(response).decode('utf-8-sig')
        require(not Path(row['object']['path']).exists(), 'Parent object retirement state differs; inspect before building')
    require(set.union(*(set(paths) for paths in dependency_sets.values())) == {key(row['path']) for row in base['compiler_inputs']},
            'Parent dependency union differs from its frozen compiler closure')
    sealed(base['link_response'])
    link_text = read_bytes(normalized(base['link_response'])).decode('utf-8-sig')
    require({row['name'].casefold() for row in base['implicit_libraries']} == IMPLICIT, 'Implicit library contract differs')
    started, started_ref = document(base['started']['path'], PARENT_STARTED_SHA)
    require(started['build_id'] == PARENT_ID, 'Parent started record identity differs')
    toolchain_inputs = [sealed(row) for row in started['toolchain_inputs']]
    require({Path(row['path']).name.casefold() for row in toolchain_inputs} == {'c1xx.dll', 'c2.dll', 'cmd.exe'},
            'Compiler helper or environment tool inventory differs')
    tools = {name: sealed(base[name]) for name in ('compiler', 'linker', 'dumpbin')}
    vcvars = pin(Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat'), VCVARS_SHA)
    materialization = {}
    for path, donor in donors.items():
        originals = set()
        for group in GROUPS:
            for row in base[group]:
                if key(row['path']) == path:
                    originals.update(row[name] for name in ('original_path', 'original_source') if name in row)
        if path == key(base['ui_assets']['path']):
            originals.add(str(PREPARED))
        replacements = [changed[key(original)] for original in originals if key(original) in changed]
        require(len({key(row['path']) for row in replacements}) <= 1, 'Conflicting donor replacement mapping')
        replacement = replacements[0] if replacements else None
        materialization[path] = dict(relative_path=str(Path(donor['path']).relative_to(PARENT_ROOT)),
                                    method='owned_changed_source_copy' if replacement else 'attested_snapshot_hardlink',
                                    donor=donor, source=replacement or donor)
    for name in (*ASSETS, *SUPPORT):
        row = additions[key(PROJECT / name)]
        target = str(Path('frozen/project') / name)
        require(target.casefold() not in {item['relative_path'].casefold() for item in materialization.values()},
                'New source target collides with a parent target')
        materialization['added:' + key(row['path'])] = dict(relative_path=target, method='owned_added_source_copy', source=row)
    frozen_plan = list(materialization.values())
    copies = [row for row in frozen_plan if row['method'] != 'attested_snapshot_hardlink']
    links = [row for row in frozen_plan if row['method'] == 'attested_snapshot_hardlink']
    require(len([row for row in copies if row['method'] == 'owned_changed_source_copy']) == len(changed),
            'Not every planned changed source maps to exactly one frozen file')
    revisions = []
    for name, after in changed.items():
        matches = [row for row in frozen_plan if row['method'] == 'owned_changed_source_copy' and key(row['source']['path']) == name]
        require(len(matches) == 1, 'Missing unique replacement recovery reference')
        before = old_current[name]
        backup = matches[0]['donor']
        require((before['bytes'], before['sha256']) == (backup['bytes'], backup['sha256']), 'Source revision backup differs')
        revisions.append(dict(before=dict(original_path=before['path'], bytes=before['bytes'], sha256=before['sha256']),
                              backup=backup, after=after, preservation='EXISTING_IMMUTABLE_PARENT_FROZEN_INPUT'))
    inputs = dict(requirements=requirements_ref, source_before=source_before_ref, ui_embedding=embedding_ref,
                  protection_before=protection_ref, storage_before=storage_ref, parent_build=parent_ref,
                  parent_started=started_ref, source_manifest=manifest_ref, source_audit=audit_ref,
                  static_pe_parser=parser_ref, pure_build_helper=helper_ref, builder=additions[key(Path(__file__))])
    if resume_ref is not None:
        inputs['permission_resolution'] = resume_ref
    plan = dict(schema='zerosis.exit_host_build.preflight.v1', status='PASS_OFFLINE_EXIT_HOST_PREFLIGHT_NO_CHILDREN',
                inputs=inputs, parent_host_id=PARENT_ID, current_source_inputs=list(live.values()),
                frozen_donors=list(donors.values()), frozen_plan=frozen_plan, source_revisions=revisions,
                protected_artifacts=protected, tools=tools, toolchain_inputs=toolchain_inputs, vcvars=vcvars,
                parent_dependency_sets=dependency_sets, catalog_expected=catalog_expected, catalog_parser_adapter=adapter,
                counts=dict(compiler_inputs=len(base['compiler_inputs']), source_manifest=len(base['sources']) + len(ASSETS),
                            current_source_inputs=len(live), unique_frozen_files=len(frozen_plan),
                            planned_hardlinks=len(links), planned_private_copies=len(copies),
                            private_copy_bytes=sum(row['source']['bytes'] for row in copies),
                            build_tools=len(base['build_tools']) + len(SUPPORT), tu_dependencies=list(COUNTS)),
                storage_gate=storage_check, planned_direct_child_phases=['environment', *('compile_' + name for name in UNITS), 'link'],
                permission_resume_validation=resume, permission_resume_evidence=resume_evidence,
                host_sdk_clr_window_gpu_or_dll_execution_allowed=False, no_automatic_retry=True,
                full_engine_goal_complete=False)
    require(shutil.disk_usage(PROJECT).free >= 384 * 1024 * 1024, 'Insufficient free space for the bounded offline build')
    context = dict(base=base, parser=parser, helper=helper, arrays=arrays, order=order,
                   responses=responses, link_text=link_text)
    return plan, context


class BuildGuard:
    """Restrict direct children and all writes to the new private attempt."""
    def __init__(self, roots, commands):
        self.roots = roots
        self.reads, self.links, self.copies = set(), {}, set()
        self.allowed = {(tuple(command), key(cwd)) for command, cwd in commands}
        self.pending = None
        self.denied = []
        sys.addaudithook(self.audit)

    def owns(self, path):
        return any(inside(path, root) for root in self.roots)

    def audit(self, event, values):
        def deny():
            self.denied.append(dict(event=event, target=str(values[0])[:240] if values else ''))
            raise PermissionError('Offline ExitConfirm build forbids ' + event)
        if event == 'open' and values and isinstance(values[0], (str, bytes, os.PathLike)):
            path, _, flags = values
            path = key(os.fsdecode(path))
            writing = flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing and (not self.owns(path) or path in self.links):
                deny()
        elif event == 'subprocess.Popen':
            executable, words, cwd, _ = values
            if self.pending is None:
                deny()
            expected, expected_cwd = self.pending
            if key(cwd) != key(expected_cwd) or (list(words) != expected if isinstance(words, (list, tuple)) else words != subprocess.list2cmdline(expected)):
                deny()
            if executable is not None and key(executable) != key(expected[0]):
                deny()
            signature = (tuple(expected), key(cwd))
            if signature not in self.allowed:
                deny()
            self.allowed.remove(signature)
        elif event == 'os.mkdir':
            if not self.owns(values[0]):
                deny()
        elif event == 'os.link':
            source, target = map(key, values[:2])
            if self.links.get(target) != source or not self.owns(target):
                deny()
        elif event == 'os.chmod':
            if key(values[0]) not in self.copies:
                deny()
        elif event.startswith(('socket.', 'ctypes.', 'urllib.', 'http.client.', 'os.exec', 'os.spawn')) or event in (
                'os.system', 'os.startfile', 'os.startfile/2', 'os.posix_spawn', 'os.posix_spawnp',
                'os.remove', 'os.rmdir', 'os.rename', 'os.symlink', 'os.truncate', 'os.utime',
                'os.chdir', 'os.fork', 'os.kill', 'os.killpg'):
            deny()


def build(plan, context, preflight_ref):
    global ACTIVE_GUARD
    signature = digest_json(plan)
    identifier = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_') + signature[:12]
    build_root = PROJECT / 'Build/UiWindowHost' / identifier
    output = PROJECT / 'evidence/ui_window_host' / identifier
    attempt = STAGE / 'attempts' / signature[:20]
    roots = (build_root, output, attempt)
    for path in roots:
        require(not os.path.lexists(path), 'A single-use attempt already exists; inspect it and do not replay')
        for parent in path.parents:
            if parent.exists():
                require(not parent.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT, 'Output ancestor is a reparse point')
    # All encoding imports are resolved before installing the execution guard.
    b''.decode('mbcs')
    def relocate(path):
        require(inside(path, PARENT_ROOT), 'Cannot relocate a path outside the parent build')
        return build_root / Path(path).relative_to(PARENT_ROOT)
    def replace_root(text):
        value = text.replace(str(PARENT_ROOT), str(build_root)).replace(PARENT_ROOT.as_posix(), build_root.as_posix())
        require(str(PARENT_ROOT) not in value and PARENT_ROOT.as_posix() not in value, 'Unrelocated parent root')
        return value
    base = context['base']
    compile_commands = [(plan['tools']['compiler']['path'], '@' + str(relocate(row['response']['path'])))
                        for row in base['final_compilation']['translation_units']]
    cmd = next(row['path'] for row in plan['toolchain_inputs'] if Path(row['path']).name.casefold() == 'cmd.exe')
    environment_script = build_root / 'read_build_environment.cmd'
    env_command = [cmd, '/d', '/c', str(environment_script)]
    link_command = [plan['tools']['linker']['path'], '@' + str(relocate(base['link_response']['path']))]
    allowed = [(env_command, build_root), *[(list(command), relocate(row['response']['path']).parent)
               for command, row in zip(compile_commands, base['final_compilation']['translation_units'])],
               (link_command, relocate(base['link_response']['path']).parent)]
    # The attempt parent is a narrow new container; no older attempt is touched.
    (STAGE / 'attempts').mkdir(exist_ok=True)
    for root in roots:
        root.mkdir(parents=True)
    guard = BuildGuard(roots, allowed)
    ACTIVE_GUARD = guard
    def writable(path):
        path = Path(path)
        require(guard.owns(path) and not os.path.lexists(path), 'Output is not new and private: ' + str(path))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    def write_raw(path, raw):
        with writable(path).open('xb') as stream:
            stream.write(raw)
    def write(path, value):
        write_raw(path, (json.dumps(value, indent=2, ensure_ascii=True) + '\n').encode('ascii'))
    completed, commands, materialized = [], [], {}
    failure = attempt / 'failure.json'
    started_path = attempt / 'started.json'
    try:
        write(started_path, dict(schema='zerosis.exit_host_build.started.v1', build_id=identifier,
                                signature=signature, reviewed_preflight=preflight_ref, requirements=plan['inputs']['requirements'],
                                inputs=plan['inputs'], no_automatic_retry=True,
                                host_sdk_clr_window_gpu_or_dll_execution_allowed=False))
        for item in plan['frozen_plan']:
            target = build_root / item['relative_path']
            source = sealed(item['source'])
            writable(target)
            if item['method'] == 'attested_snapshot_hardlink':
                guard.links[key(target)] = key(source['path'])
                os.link(source['path'], target)
            else:
                guard.copies.add(key(target))
                write_raw(target, read_bytes(source))
                os.chmod(target, stat.S_IREAD)
            actual = artifact(target)
            require((actual['bytes'], actual['sha256']) == (source['bytes'], source['sha256']), 'Frozen source content differs')
            require((actual['file_identity'] == source['file_identity']) == (item['method'] == 'attested_snapshot_hardlink'),
                    'Frozen source ownership differs')
            materialized[key(target)] = dict(**actual, materialization=item['method'], original_path=source['path'],
                                             **({'reused_from_path': source['path']} if item['method'] == 'attested_snapshot_hardlink' else {}))
        require(len(materialized) == plan['counts']['unique_frozen_files'], 'Actual frozen cardinality differs from preflight')
        # Multiple retained paths can share one file identity. Record link counts
        # only after every intentional link has been added.
        for name, row in list(materialized.items()):
            materialized[name] = {**row, **artifact(row['path'])}
        def frozen(row):
            result = materialized[key(relocate(row['path']))]
            value = {**row, **result}
            if 'original_path' in row:
                value['original_path'] = row['original_path']
            if 'original_source' in row:
                value['original_source'] = row['original_source']
            if result['materialization'] != 'attested_snapshot_hardlink':
                value.pop('reused_from_path', None)
            return value
        compiler_inputs = [frozen(row) for row in base['compiler_inputs']]
        sources = [frozen(row) for row in base['sources']]
        for name in ASSETS:
            row = materialized[key(build_root / 'frozen/project' / name)]
            sources.append({**row, 'original_source': str(PROJECT / name), 'relative_path': name})
        build_tools = [frozen(row) for row in base['build_tools']]
        for name in SUPPORT:
            row = materialized[key(build_root / 'frozen/project' / name)]
            build_tools.append({**row, 'role': Path(name).stem, 'relative_path': name})
        providers, systems, implicit = ([frozen(row) for row in base[group]] for group in
                                       ('provider_inputs', 'system_libraries', 'implicit_libraries'))
        assets = frozen(base['ui_assets'])
        provider_reports = {name: frozen(row) for name, row in base['provider_reports'].items()}
        write_raw(environment_script, ('@echo off\ncall "' + plan['vcvars']['path'] + '" >nul\n'
                                       'if errorlevel 1 exit /b %errorlevel%\nset\n').encode('ascii'))
        def execute(command, cwd, log, phase, env=None):
            require(guard.pending is None, 'Overlapping direct child execution')
            record = dict(command=list(command), cwd=str(cwd), phase=phase)
            commands.append(record)
            guard.pending = (list(command), str(cwd))
            try:
                result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=300,
                                        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
            except subprocess.TimeoutExpired as error:
                write_raw(log, (error.stderr or b'') if phase == 'environment' else (error.stdout or b'') + (error.stderr or b''))
                record.update(error_type='TimeoutExpired', timed_out=True, log=artifact(log))
                raise
            except OSError as error:
                write_raw(log, (type(error).__name__ + ': ' + str(error)).encode('utf-8'))
                record.update(error_type=type(error).__name__, log=artifact(log))
                raise
            finally:
                guard.pending = None
            write_raw(log, result.stderr if phase == 'environment' else result.stdout + result.stderr)
            record.update(returncode=result.returncode, log=artifact(log))
            require(result.returncode == 0, 'Direct child failed: ' + phase)
            require(phase == 'environment' or not re.search(rb'\bwarning\s+(?:C|LNK)\d+', result.stdout + result.stderr, re.I),
                    'Compiler/linker warning: ' + phase)
            return result
        raw_env = execute(env_command, build_root, attempt / 'environment.stderr.log', 'environment')
        env = os.environ.copy()
        for line in raw_env.stdout.decode('mbcs').splitlines():
            if '=' in line and not line.startswith('='):
                name, value = line.split('=', 1)
                env[name] = value
        env.update({name: replace_root(value) for name, value in base['final_environment'].items()})
        (build_root / 'tmp').mkdir()
        closure = {key(row['path']) for row in compiler_inputs}
        union = set()
        libraries = IMPLICIT | {Path(row['path']).name.casefold() for row in providers + systems}
        for index, (unit, stem, parent, command) in enumerate(zip(UNITS, STEMS, base['final_compilation']['translation_units'], compile_commands)):
            response = relocate(parent['response']['path'])
            write_raw(response, replace_root(context['responses'][unit]).encode('utf-8'))
            (response.parent / 'obj').mkdir()
            execute(list(command), response.parent, attempt / ('compile_' + unit + '.log'), 'compile_' + unit, env)
            dependency = relocate(parent['dependency_report']['path'])
            actual, visits = dependency_paths(artifact(dependency))
            expected = {key(relocate(path)) for path in plan['parent_dependency_sets'][unit]}
            require(actual == expected and actual <= closure and len(actual) == COUNTS[index], 'Actual dependency set differs: ' + unit)
            union.update(actual)
            obj = response.parent / 'obj' / (stem + '.obj')
            obj_ref = artifact(obj)
            raw = read_bytes(obj_ref)
            coff = context['parser'].coff(raw)
            defaults = context['helper'].object_defaults(raw)
            require(coff['machine_hex'] == '0x8664' and set(defaults) <= libraries, 'Object machine or default libraries differ')
            record = dict(translation_unit=unit, command=list(command), response=artifact(response),
                          dependency_report=artifact(dependency), object=obj_ref, log=artifact(attempt / ('compile_' + unit + '.log')),
                          returncode=0, actual_dependency_count=len(actual), expected_dependency_count=len(expected),
                          dependency_visits=visits, default_libraries=defaults, coff_machine=coff['machine_hex'])
            completed.append(record)
            write(attempt / ('compiled_' + unit + '.json'), record)
            print(json.dumps(dict(phase='compiled', translation_unit=unit, object_bytes=obj_ref['bytes'])), flush=True)
        require(union == closure and len(union) == plan['counts']['compiler_inputs'], 'Final dependency union differs')
        link_response = relocate(base['link_response']['path'])
        rewritten = replace_root(context['link_text'])
        linked_objects = re.findall(r'^"([^"\n]+\.obj)"$', rewritten.replace('\r\n', '\n'), re.I | re.M)
        require([key(path) for path in linked_objects] == [key(row['object']['path']) for row in completed],
                'Link does not consume exactly the five new objects')
        write_raw(link_response, rewritten.encode('utf-8'))
        objects_before = [sealed(row['object']) for row in completed]
        execute(link_command, link_response.parent, attempt / 'link.log', 'link', env)
        require([sealed(row['object']) for row in completed] == objects_before, 'Link changed an input object')
        executable, mapfile = relocate(base['executable']['path']), relocate(base['map']['path'])
        executable_ref, map_ref = artifact(executable), artifact(mapfile)
        pe = context['parser'].PE(read_bytes(executable_ref))
        catalog_detail = pe.catalog(context['arrays'], context['order'])
        catalog = context['helper'].catalog_summary(catalog_detail)
        require(all(catalog[name] == value for name, value in plan['catalog_expected'].items()), 'Linked 69-payload catalog differs')
        imports = pe.imports()
        require(len(imports) == len(set(imports)) == 24 and set(imports) == set(base['imports']['dependencies']),
                'Linked import set differs from the expected 24 imports')
        raw = pe.data
        optional = struct.unpack_from('<I', raw, 0x3c)[0] + 24
        require(struct.unpack_from('<I', raw, optional + 108)[0] >= 16, 'PE lacks the complete directory table')
        for directory, label in ((13, 'delay import'), (14, 'CLR')):
            require(struct.unpack_from('<II', raw, optional + 112 + 8 * directory) == (0, 0), 'Unexpected ' + label + ' directory')
        markers = pe.occurrences(MARKER)
        require(len(markers) == 1, 'Native restore read-only marker is not unique')
        map_text = read_bytes(map_ref).decode('mbcs')
        mapped = {match.casefold().removesuffix('.lib') + '.lib' for match in re.findall(
            r'\s([\w.-]+):\S+\.(?:obj|dll)\s*$', map_text, re.I | re.M)}
        require(mapped <= libraries, 'Map consumed an unattested library')
        link_additions = {}
        for item in plan['frozen_plan']:
            if item['method'] == 'attested_snapshot_hardlink':
                inode = tuple(item['source']['file_identity'])
                link_additions[inode] = link_additions.get(inode, 0) + 1
        for row in [*plan['current_source_inputs'], *plan['frozen_donors'], *plan['protected_artifacts'],
                    *plan['tools'].values(), *plan['toolchain_inputs'], plan['vcvars'], *plan['inputs'].values(),
                    *plan['permission_resume_evidence'], preflight_ref]:
            actual = sealed(row)
            if 'links' in row:
                require(actual['links'] == row['links'] + link_additions.get(tuple(row['file_identity']), 0),
                        'Input link-count delta differs: ' + row['path'])
        for row in materialized.values():
            sealed(row)
        require(len(commands) == 7 and not guard.allowed and not guard.denied and
                [row['phase'] for row in commands] == plan['planned_direct_child_phases'] and
                all(row['returncode'] == 0 for row in commands), 'Actual direct-child execution differs from reviewed preflight')
        static_path = attempt / 'static_pe.json'
        write(static_path, dict(schema='zerosis.exit_host_build.static_pe.v1', source='PURE_FILE_BACKED_PE_AND_COFF',
                                image=executable_ref, catalog=catalog, exact_payloads=catalog_detail['exact_payloads'],
                                dependencies=imports, clr_directory_empty=True, delay_import_directory_empty=True,
                                restore_contract_marker=dict(ascii=MARKER.decode('ascii'), rva=markers[0], read_only=True),
                                executable_or_dll_loaded=False, catalog_parser_adapter=plan['catalog_parser_adapter']))
        by_original = {key(row['original_source']): row for row in sources}
        report = dict(schema=base['schema'], status='UI_WINDOW_HOST_CANDIDATE_BUILT', build_id=identifier,
            baseline_build=plan['inputs']['parent_build'], profile=plan['inputs']['source_audit'], exit_confirm_builder=plan['inputs']['builder'],
            exit_confirm_component=plan['inputs']['source_manifest'], native_restore_contract_component=base['native_restore_contract_component'],
            compiler=plan['tools']['compiler'], linker=plan['tools']['linker'], dumpbin=plan['tools']['dumpbin'],
            compiler_version=base['compiler_version'], toolchain=base['toolchain'], toolchain_inputs=plan['toolchain_inputs'], vcvars=plan['vcvars'],
            definitions=base['definitions'], system_include_roots=base['system_include_roots'], compiler_inputs=compiler_inputs,
            compiler_dependency_count=len(closure), sources=sources,
            window_sources=[by_original[key(row['original_source'])] for row in base['window_sources']],
            provider_inputs=providers, system_libraries=systems, libraries=providers + systems,
            system_library_names=base['system_library_names'], implicit_libraries=implicit,
            implicit_libraries_before=base['implicit_libraries'], implicit_libraries_after=implicit,
            actual_implicit_library_namesfrommap=sorted(mapped & IMPLICIT), build_tools=build_tools,
            provider_reports=provider_reports, shared_lua_build=frozen(base['shared_lua_build']), ui_assets=assets,
            ui_asset_preparation=dict(executed_by_builder=False, report=plan['inputs']['ui_embedding'],
                                      status='CURRENT_69_PAYLOAD_CATALOG_FROM_ATTESTED_NARROW_PRODUCER'),
            dependency_discovery=dict(executed=False, reason='Current source shape established offline; exact retained dependency sets rechecked by all five final compilations.'),
            final_compilation=dict(translation_units=completed), final_dependency_reports={row['translation_unit']: row['dependency_report'] for row in completed},
            response=completed[0]['response'], dependency_report=completed[0]['dependency_report'],
            link_response=artifact(link_response), link_log=artifact(attempt / 'link.log'), map=map_ref,
            executable={**executable_ref, 'pe': dict(architecture='x64', pe_format='PE32+', is_dll=False)},
            imports=dict(dependencies=imports, log=artifact(static_path), source='PURE_PYTHON_STATIC_PE'),
            catalog=catalog, restore_contract_marker=dict(ascii=MARKER.decode('ascii'), rva=markers[0], inclusion_evidence_only=True),
            current_source_inputs=plan['current_source_inputs'], protected_artifacts=plan['protected_artifacts'],
            started=artifact(started_path), reviewed_preflight=preflight_ref, source_revision_provenance=plan['source_revisions'],
            sources_changed_from_baseline=[row['after'] for row in plan['source_revisions']],
            new_source_inputs=[row['source'] for row in plan['frozen_plan'] if row['method'] == 'owned_added_source_copy'],
            final_environment={name: env.get(name, '') for name in base['final_environment']},
            frozen_input_reuse=dict(hardlinked_files=plan['counts']['planned_hardlinks'], copied_files=plan['counts']['planned_private_copies'],
                                    copied_source_bytes=plan['counts']['private_copy_bytes'], donor_content_and_metadata_preserved=True,
                                    intentional_link_additions=[dict(file_identity=list(inode), added_links=count) for inode, count in sorted(link_additions.items())]),
            scope='Five current frozen ExitConfirm Host object compilations and one offline x64 link with byte-only PE/COFF attestation.',
            source_inputs_unchanged=True, provider_inputs_unchanged=True, host_runtime_executed=False, gamecore_loaded=False,
            sdk_linked=False, mods_updated=False, stage_updated=False, default_promoted=False,
            sdk_restore_verified=False, native_restore_approved=False, full_engine_goal_complete=False)
        require(len(sources) == plan['counts']['source_manifest'] and len(build_tools) == plan['counts']['build_tools'],
                'Final source or producer-tool manifest cardinality differs')
        report_path = output / 'build_result.json'
        write(report_path, report)
        run = dict(schema='zerosis.exit_host_build.run.v1', status='PASS_CURRENT_EXIT_CONFIRM_HOST_OFFLINE_BUILD_ONLY',
                   utc=datetime.now(timezone.utc).isoformat(), signature=signature, build_id=identifier,
                   inputs=plan['inputs'], reviewed_preflight=preflight_ref, build_result=artifact(report_path),
                   commands=commands, compilation=completed, materialized=list(materialized.values()),
                   frozen_donors=plan['frozen_donors'], current_inputs=plan['current_source_inputs'],
                   protected_runtime_inputs=plan['protected_artifacts'], source_revisions=plan['source_revisions'],
                   actual_counts=plan['counts'], static_pe=artifact(static_path), denied_operations=guard.denied,
                   host_sdk_clr_window_gpu_or_dll_executed=False, no_automatic_retry=True, full_engine_goal_complete=False)
        write(attempt / 'run.json', run)
        print(json.dumps(dict(status=run['status'], build_id=identifier, run=artifact(attempt / 'run.json'),
                              build_result=artifact(report_path), executable=executable_ref)), flush=True)
    except BaseException as error:
        if not failure.exists():
            write(failure, dict(status='FAILED_DO_NOT_REPLAY', build_id=identifier, signature=signature,
                                error=type(error).__name__ + ': ' + str(error), commands=commands,
                                completed_translation_units=completed, materialized=list(materialized.values()),
                                denied_operations=guard.denied, compilation_retry_allowed=False,
                                host_sdk_clr_window_gpu_or_dll_executed=False))
        raise


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    action = cli.add_mutually_exclusive_group(required=True)
    action.add_argument('--preflight', action='store_true', help='Read inputs and print the complete reviewable plan; create nothing')
    action.add_argument('--build', action='store_true', help='Consume one exact saved preflight and build once')
    cli.add_argument('--preflight-file', type=Path)
    cli.add_argument('--preflight-sha256')
    cli.add_argument('--preflight-output', type=Path, help='Write a new complete preflight inside the stage and print a compact receipt')
    cli.add_argument('--permission-resolution', type=Path, help='Explicit pinned context for a new attempt after the zero-child permission failure')
    options = cli.parse_args()
    if options.build:
        require(options.preflight_file is not None and options.preflight_sha256 is not None,
                'Build requires a saved reviewed preflight path and SHA-256')
        require(inside(options.preflight_file, STAGE) and re.fullmatch('[0-9a-f]{64}', options.preflight_sha256),
                'Reviewed preflight must be a pinned file inside this stage')
        require(options.preflight_output is None, 'Build cannot write a replacement preflight')
    else:
        require(options.preflight_file is None and options.preflight_sha256 is None, 'Preflight does not consume build approval options')
    plan, context = prepare_plan(options.permission_resolution)
    if options.preflight:
        receipt = dict(status=plan['status'], input_signature=digest_json(plan), counts=plan['counts'],
                       planned_direct_child_phases=plan['planned_direct_child_phases'],
                       created_files=0, child_commands=0, host_sdk_clr_window_gpu_or_dll_executed=False)
        if options.preflight_output is not None:
            path = options.preflight_output.absolute()
            require(inside(path, STAGE) and not os.path.lexists(path) and path.parent.is_dir(),
                    'Preflight output must be a new file in an existing stage directory')
            for parent in path.parents:
                if parent.exists():
                    require(not parent.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                            'Preflight output ancestor is a reparse point')
            with path.open('x', encoding='ascii', newline='\n') as stream:
                json.dump(plan, stream, indent=2, ensure_ascii=True)
                stream.write('\n')
            receipt.update(preflight=artifact(path), created_files=1)
        print(json.dumps(receipt))
        return
    reviewed, reviewed_ref = document(options.preflight_file, options.preflight_sha256)
    require(canonical(reviewed) == canonical(plan), 'Current inputs or builder differ from the reviewed preflight; review a fresh plan')
    build(plan, context, reviewed_ref)


if __name__ == '__main__':
    main()
