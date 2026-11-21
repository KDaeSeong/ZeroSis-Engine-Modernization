"""Read-only preparation gate for the single attested hover-repaint Host.

The retired objects and the two publication documents have exact historical
roles. Every current compiler input, source, provider and runtime file remains
required. This gate neither runs a linked image nor authorizes runtime use.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct


BUILD_ID = '20261024T082423Z_b604cddf0d2d'
PARENT_ID = '20261024T055841Z_974a5be57533'
ROOT = 'evidence/original_world_hud/hover_repaint'
STAGE = ROOT + '/host_build/b604cddf0d2d34d1c183'
REPORT_SHA = '6d771614f6a696b260e8aa8e401a3a5b8fd63295346f171eec6a9807a9d01844'
EXE_SHA = '8e24b066b8f00c1c473def10da9d11c920ee460f03ef223123fcecc1b8fc4741'
PARENT_SHA = '6aa2ccdb8ce1308521fc01f88fa45745153244b6931754a0b3111dc2129d1302'
TUS = ('host_main', 'window', 'renderer', 'world_renderer', 'terrain_renderer')
STEMS = ('HostMain', 'BitmapWindow', 'BitmapRenderer', 'WorldViewRenderer', 'WorldTerrainRenderer')
COUNTS = (466, 266, 270, 279, 301)
LIBRARIES = {'msvcrt.lib', 'msvcprt.lib', 'vcruntime.lib', 'oldnames.lib', 'bcrypt.lib',
             'kernel32.lib', 'ucrt.lib', 'uuid.lib'}
MAP_LIBRARIES = LIBRARIES - {'oldnames.lib', 'uuid.lib'}
MARKER = b'NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|'
SOURCE_NAMES = ('UiPanelRepaint.h', 'InteractiveUiSession.h', 'InteractiveGameSession.h', 'InteractiveGameLoop.h')
METADATA = ('evidence/save_menu/20261013_original_screen/current_progress.json', 'docs/ORIGINAL_WORLD_HUD.md')
PINS = {
    'run': (STAGE + '/run.json', 'd4dc27b269ce8d8ce664aa0a9448ea602f5a24fe7489ce1fbc94d71ae2d37a7d'),
    'attestation': (STAGE + '/attestation.json', '218cafe3a932c50f545da8d238e27c71dc67cb38afdb140f305362c878672cf3'),
    'plan': (ROOT + '/link_cleanup_plan.json', '9ad838b9ecec6af8bbd4b47d01ccdfa6a9cdc646a25f8a38cfa604fd4d56b2a2'),
    'retirement': (ROOT + '/link_cleanup_result.json', 'e894d68731e773505597a6992b8a332c0949d424ccda1b19ee8802a66abd8a78'),
    'publication': (ROOT + '/publication.json', '22e63c43211e8c709c6290b7595623609ee0190c0cc9200846bbbb7f02509b56'),
    'audit': (ROOT + '/final_audit.json', 'd61742a7e653b8f03d03a518722a63789c64e8d992d3c2857bee9748682fe956'),
    'component': (ROOT + '/component_audit.json', '80f806d06fc519005579ae421ebfcbbe8377173d2a11d4057f674e0f60e170de'),
    'protection': (ROOT + '/cleanup_plan.json', 'e408298ba15ba4e5559753db1c8d1a431fabe26f0573a830aed4d610c7be67fc'),
}


def registered_host_spec():
    """Return a fresh immutable-build specification, without opening files."""
    spec = dict(kind='hover_repaint', build_id=BUILD_ID,
        report_path=f'evidence/ui_window_host/{BUILD_ID}/build_result.json', report_sha256=REPORT_SHA,
        executable_sha256=EXE_SHA, compiler_dependency_count=550, current_source_count=593,
        source_manifest_count=86, protected_artifact_count=41, dependency_counts=COUNTS,
        materialized_input_count=593, private_source_copies=4, donor_hardlinks=589)
    for name, (relative, digest) in PINS.items():
        spec[name + '_path'], spec[name + '_sha256'] = relative, digest
    return spec


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def pair(row):
    require(type(row) is dict and type(row.get('path')) is str and type(row.get('sha256')) is str and
            re.fullmatch(r'[0-9a-f]{64}', row['sha256']), 'Malformed hover Host artifact')
    return key(row['path']), row['sha256']


def same(left, right):
    return pair(left) == pair(right) and left.get('bytes', right.get('bytes')) == right.get('bytes', left.get('bytes'))


def rows(value):
    require(type(value) is list, 'Hover Host inventory is not a list')
    result = {}
    for row in value:
        path = pair(row)[0]
        require(path not in result, 'Duplicate hover Host artifact path')
        result[path] = row
    return result


def walk(value):
    if type(value) is dict:
        if type(value.get('path')) is str and 'sha256' in value:
            yield value
        for child in value.values():
            yield from walk(child)
    elif type(value) is list:
        for child in value:
            yield from walk(child)


def reference(project, spec, name):
    relative = Path(spec[name + '_path'])
    require(not relative.is_absolute() and '..' not in relative.parts, 'Invalid registered hover Host proof path')
    return dict(path=str(project / relative), sha256=spec[name + '_sha256'])


def read(files, row, maximum=8 * 1024 * 1024):
    actual = files.verify(row)
    require(actual['bytes'] <= maximum, 'Hover Host input exceeds its read bound')
    raw = Path(actual['path']).read_bytes()
    require(len(raw) == actual['bytes'] and hashlib.sha256(raw).hexdigest() == actual['sha256'], 'Hover Host input changed while reading')
    return raw


def recover(files, backup, before, backup_root):
    require(type(before) is dict and 'path' not in before and type(before.get('original_path')) is str and
            type(before.get('bytes')) is int and 0 <= before['bytes'] <= 8 * 1024 * 1024 and
            re.fullmatch(r'[0-9a-f]{64}', before.get('sha256', '')) and
            Path(backup['path']).is_relative_to(backup_root), 'Historical hover backup exceeds its exact role')
    files.verify(backup)
    with gzip.open(backup['path'], 'rb') as stream:
        raw = stream.read(before['bytes'] + 1)
    require((len(raw), hashlib.sha256(raw).hexdigest()) == (before['bytes'], before['sha256']),
            'Historical hover backup does not recover the declared bytes')


def frozen_rows(build):
    result = {}
    source_paths = set(rows(build['sources']))
    values = [row for group in ('compiler_inputs', 'sources', 'provider_inputs', 'system_libraries', 'build_tools', 'implicit_libraries')
              for row in build[group]]
    values += [*build['provider_reports'].values(), build['shared_lua_build'], build['ui_assets']]
    for row in values:
        path = pair(row)[0]
        if 'original_path' not in row:
            require(path in source_paths and type(row.get('original_source')) is str and
                    Path(row['original_source']).suffix.casefold() == '.lua', 'Only Lua source rows may use the sole source alias')
            row = dict(row, original_path=row['original_source'])
        require(type(row['original_path']) is str and ('original_source' not in row or
                key(row['original_source']) == key(row['original_path'])), 'Frozen hover source aliases differ')
        if path in result:
            previous = result[path]
            require(same(previous, row) and key(previous['original_path']) == key(row['original_path']) and
                    all(previous.get(name) == row.get(name) for name in
                        ('file_identity', 'mtime_ns', 'file_attributes', 'materialization')), 'Conflicting frozen hover aliases')
        else:
            result[path] = row
    return result


def pe_observations(raw):
    """Read the retained AMD64 PE/import directory; never load the image."""
    def number(at, fmt):
        require(0 <= at <= len(raw) - struct.calcsize(fmt), 'PE scalar exceeds the retained image')
        return struct.unpack_from(fmt, raw, at)[0]
    require(len(raw) >= 64 and raw[:2] == b'MZ', 'Retained Host lacks a DOS header')
    at = number(0x3c, '<I')
    require(raw[at:at + 4] == b'PE\0\0' and number(at + 4, '<H') == 0x8664, 'Retained Host is not AMD64 PE')
    count, size, flags = number(at + 6, '<H'), number(at + 20, '<H'), number(at + 22, '<H')
    optional = at + 24
    require(0 < count <= 96 and size >= 128 and flags & 0x20 and not flags & 0x2000 and
            number(optional, '<H') == 0x20b and number(optional + 108, '<I') >= 2, 'Retained Host is not PE32+ executable')
    sections = []
    for index in range(count):
        start = optional + size + index * 40
        require(start + 40 <= len(raw), 'Truncated PE section table')
        length, pointer = number(start + 16, '<I'), number(start + 20, '<I')
        require(pointer <= len(raw) and length <= len(raw) - pointer, 'Truncated PE raw section')
        sections.append((number(start + 12, '<I'), length, pointer, number(start + 36, '<I')))
    def mapped(rva, length):
        matches = [section for section in sections if section[0] <= rva and rva - section[0] <= section[1] and
                   length <= section[1] - (rva - section[0])]
        require(len(matches) == 1, 'PE address lacks one file-backed section')
        section = matches[0]
        return section[2] + rva - section[0], section
    directory, length = number(optional + 120, '<I'), number(optional + 124, '<I')
    require(directory and length >= 20, 'Retained Host lacks imports')
    imports = []
    terminated = False
    for index in range(min(1024, length // 20)):
        start, _ = mapped(directory + index * 20, 20)
        item = struct.unpack_from('<5I', raw, start)
        if not any(item):
            terminated = True
            break
        start, section = mapped(item[3], 1)
        end = raw.find(b'\0', start, min(start + 4096, section[2] + section[1]))
        require(end >= start, 'Unterminated PE import name')
        imports.append(raw[start:end].decode('ascii').casefold())
    require(terminated and len(imports) == len(set(imports)) == 24, 'Retained Host import count/termination differs')
    markers = 0
    for _, length, pointer, attributes in sections:
        if attributes & 0x40000000 and not attributes & 0xa0000000:
            markers += raw[pointer:pointer + length].count(MARKER)
    require(markers == 1, 'Retained native restore marker is not unique readonly data')
    return imports


def validate_retained_hover_repaint_host_runtime(build, project, spec, files):
    project = Path(project).absolute()
    require(getattr(files, 'check_metadata', False) is True, 'The hover Host gate requires metadata-aware sealed files')
    expected_spec = registered_host_spec()
    require(type(spec) is dict and all(spec.get(name) == value for name, value in expected_spec.items()),
            'Unregistered or changed hover Host specification')
    report_ref = reference(project, spec, 'report')
    sealed = files.json(report_ref)
    require(json.dumps(build, sort_keys=True, separators=(',', ':')) == json.dumps(sealed, sort_keys=True, separators=(',', ':')) and
            build.get('build_id') == BUILD_ID and build.get('schema') == 'zerosis.ui_window_host_build.v1' and
            build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build.get('source_inputs_unchanged') is True and
            build.get('provider_inputs_unchanged') is True, 'Hover Host report is not its registered immutable build')
    refs = {name: reference(project, spec, name) for name in PINS}
    proof = {name: files.json(row) for name, row in refs.items()}
    run, att, plan, retirement = (proof[name] for name in ('run', 'attestation', 'plan', 'retirement'))
    publication, audit, component = (proof[name] for name in ('publication', 'audit', 'component'))
    require(run.get('schema') == 'zerosis.hover_host.run.v1' and run.get('status') == 'PASS_CURRENT_HOVER_HOST_BUILD_ONLY' and
            att.get('schema') == 'zerosis.hover_host.independent_attestation.v1' and
            att.get('status') == 'PASS_CURRENT_HOVER_HOST_STATIC_ATTESTATION' and
            plan.get('schema') == 'zerosis.hover_host.exact_retirement_plan.v1' and
            retirement.get('status') == 'PASS_EXACT_TWELVE_INTERMEDIATES_RETIRED' and retirement.get('error') is None and
            publication.get('status') == 'PASS_OFFLINE_HOST_LINK_PUBLICATION' and
            audit.get('status') == 'PASS_CURRENT_HOVER_HOST_LINK_PUBLICATION_AND_EXACT_RETIREMENT', 'Hover Host proof status differs')
    require(run.get('build_id') == att.get('build_id') == BUILD_ID and same(run['build_result'], report_ref) and
            same(att['build_result'], report_ref) and same(audit['build'], report_ref) and same(publication['build'], report_ref) and
            same(att['run'], refs['run']) and same(audit['build_run'], refs['run']) and
            same(audit['attestation'], refs['attestation']) and same(publication['attestation'], refs['attestation']) and
            same(audit['publication'], refs['publication']) and same(audit['cleanup'], refs['retirement']) and
            same(retirement['plan'], refs['plan']) and same(run['component_audit'], refs['component']) and
            same(att['component_audit'], refs['component']) and same(build['hover_repaint_component'], refs['component']),
            'Hover Host proof graph belongs to another build')
    for field in ('host_runtime_executed', 'gamecore_loaded', 'sdk_linked', 'mods_updated', 'stage_updated', 'default_promoted',
                  'sdk_restore_verified', 'native_restore_approved', 'full_engine_goal_complete'):
        require(build.get(field) is False, 'Hover Host build-only scope differs: ' + field)
    require(run.get('host_sdk_or_window_executed') is False and retirement.get('host_sdk_or_window_executed') is False and
            publication.get('host_sdk_or_window_executed') is False and audit.get('native_sdk_host_or_window_execution') is False and
            audit.get('current_runtime_contains_new_hover_fix') is False and audit.get('screen_verification_deferred') is True and
            publication.get('current_runtime_contains_new_host') is False and audit.get('full_engine_goal_complete') is False and
            att.get('host_executed') is False and att.get('sdk_loaded') is False and att.get('window_created') is False and
            att.get('live_ui_verified') is False and att.get('full_engine_goal_complete') is False,
            'Hover Host proof exceeds offline preparation')
    root, parent_root = project / 'Build/UiWindowHost' / BUILD_ID, project / 'Build/UiWindowHost' / PARENT_ID
    require(pair(build['baseline_build']) == (key(project / f'evidence/ui_window_host/{PARENT_ID}/build_result.json'), PARENT_SHA) and
            same(run['baseline_build'], build['baseline_build']) and same(att['baseline_build'], build['baseline_build']),
            'Hover Host retained parent differs')
    # The parent report is authenticated context. Its old prepared-pair payload
    # fields are not traversed or used as inputs to this new linked image.
    parent = files.json(build['baseline_build'])
    require(parent.get('build_id') == PARENT_ID, 'Hover Host parent identity differs')
    started = files.json(run['started'])
    require(same(run['started'], build['started']) and started.get('build_id') == BUILD_ID and
            started.get('schema') == 'zerosis.hover_host.started.v1' and started.get('no_automatic_retry') is True and
            started.get('host_sdk_or_window_execution_allowed') is False and
            same(run['builder'], build['hover_repaint_builder']) and same(att['builder'], run['builder']) and
            same(started['builder'], run['builder']), 'Hover Host started/builder binding differs')
    files.verify(run['builder']); files.verify(att['verifier']); files.verify(att['static_pe_parser'])
    compiler, sources, current = (rows(build[name]) for name in ('compiler_inputs', 'sources', 'current_source_inputs'))
    frozen, parent_frozen = frozen_rows(build), frozen_rows(parent)
    require(len(compiler) == build['compiler_dependency_count'] == att['compiler_dependency_union'] == 550 and
            len(sources) == att['source_manifest_count'] == 86 and len(current) == att['current_input_count'] == 593 and
            len(frozen) == att['frozen_input_count'] == 593 and len(parent_frozen) == 592 and
            rows(run['current_inputs']) == rows(started['current_inputs']) == current, 'Hover Host current/frozen input counts differ')
    for row in current.values():
        files.verify(row)
    changes = {key(project / 'Source/Host' / name) for name in SOURCE_NAMES}
    production = rows(component['production_sources'])
    require(set(production) == changes and all(same(row, current[path]) for path, row in production.items()),
            'Hover Host component production sources differ from current inputs')
    metadata_paths = {key(project / name) for name in METADATA}
    require(not metadata_paths & (set(current) | {key(row['original_path']) for row in frozen.values()}),
            'Publication documents must not be executable or compiler inputs')
    metadata = {}
    require(type(publication['changed_metadata']) is list and len(publication['changed_metadata']) == 2, 'Publication metadata count differs')
    for revision in publication['changed_metadata']:
        before, after = revision['before'], revision['after']
        path = key(before['original_path'])
        require(path in metadata_paths and path not in metadata and pair(after)[0] == path and
                revision.get('gzip_roundtrip_verified') is True, 'Publication exceeds its two metadata-only roles')
        recover(files, revision['backup'], before, project / ROOT / 'source_backups')
        metadata[path] = before
    require(set(metadata) == metadata_paths, 'Publication metadata role is incomplete')
    protected = rows(build['protected_artifacts'])
    original_protection = rows(proof['protection']['protected'])
    require(len(protected) == att['protected_artifact_count'] == 41 and len(original_protection) == 38 and
            rows(run['protected_runtime_inputs']) == rows(started['protected_runtime_inputs']) == protected,
            'Hover Host protection inventory differs')
    deferred_path = key(project / 'evidence/original_world_hud/pair_preparation/execution/screen_verification_deferred.json')
    require(set(protected) == set(original_protection) | metadata_paths | {deferred_path}, 'Hover Host protected paths differ')
    for path, row in protected.items():
        if path in metadata:
            require((row['bytes'], row['sha256']) == (metadata[path]['bytes'], metadata[path]['sha256']),
                    'Historical document does not bind the exact build-time protected identity')
        else:
            files.verify(row)
            if path in original_protection:
                require(same(row, original_protection[path]), 'Current protection differs from the fixed runtime/save contract')
    runtime_root = project / 'Build/InteractiveGameRuntime/20261024T070230Z_cbbd79f1cbb6'
    runtime = {path: row for path, row in protected.items() if Path(row['path']).parent == runtime_root}
    native = [row for row in protected.values() if Path(row['path']).suffix == '.zssave']
    require(len(runtime) == att['protected_runtime_inputs'] == 24 and len(native) == att['protected_native_saves'] == 6 and
            set(rows(build['prepared_runtime_inputs'])) == set(runtime) and
            all(same(row, runtime[pair(row)[0]]) for row in build['prepared_runtime_inputs']), 'Retained cbbd24/native6 protection differs')
    revisions = build['source_revision_provenance']
    require(revisions == att['source_revisions'] == started['source_revisions'] and len(revisions) == 3, 'Hover source revision count differs')
    seen = set()
    for revision in revisions:
        before, after = revision['before'], revision['after']
        path = key(before['original_path'])
        require(path in changes - {key(project / 'Source/Host/UiPanelRepaint.h')} and path not in seen and same(after, current[path]),
                'Unrelated hover source revision')
        recover(files, revision['backup'], before, project / ROOT / 'source_backups')
        seen.add(path)
    require(len(seen) == 3, 'Incomplete hover source revision proof')
    relocate = lambda path: root / Path(path).relative_to(parent_root)
    added = key(root / 'frozen/include_roots/project/Source/Host/UiPanelRepaint.h')
    require(set(frozen) == {key(relocate(row['path'])) for row in parent_frozen.values()} | {added},
            'Frozen hover inventory differs from the exact parent plus one header')
    materialized, donors = rows(run['materialized']), rows(run['frozen_donors'])
    require(set(materialized) == set(frozen) and donors == rows(started['frozen_donors']) and set(donors) == set(parent_frozen),
            'Hover materialization/donor inventories differ')
    for path, row in donors.items():
        require(same(row, parent_frozen[path]), 'Hover donor differs from the pinned parent')
        files.verify(row)
    implicit, parent_implicit = rows(build['implicit_libraries']), rows(parent['implicit_libraries'])
    require(len(implicit) == len(parent_implicit) == 8 and {row['name'].casefold() for row in implicit.values()} == LIBRARIES and
            {key(row['reused_from_path']) for row in implicit.values()} == set(parent_implicit), 'Exact eight implicit donors differ')
    copied, links, copied_bytes, missing, origins = set(), 0, 0, set(), set()
    by_target = {key(relocate(row['path'])): row for row in parent_frozen.values()}
    for path, row in frozen.items():
        material = materialized[path]
        alias = material.get('original_path', material.get('original_source'))
        require(type(alias) is str and ('original_path' in material or path in sources and Path(alias).suffix.casefold() == '.lua') and
                ('original_source' not in material or key(material['original_source']) == key(alias)) and
                same(material, row) and key(alias) == key(row['original_path']), 'Materialized hover source aliases differ')
        actual, origin = files.verify(row), key(row['original_path'])
        require(origin not in origins and Path(row['path']).is_relative_to(root / 'frozen'), 'Duplicate or escaped frozen hover origin')
        origins.add(origin)
        previous = by_target.get(path)
        if previous is not None:
            require(origin == key(previous['original_path']), 'Frozen hover origin changed')
        else:
            require(path == added and origin == key(project / 'Source/Host/UiPanelRepaint.h'), 'Unregistered new frozen source')
        if origin in current:
            require((actual['bytes'], actual['sha256']) == (current[origin]['bytes'], current[origin]['sha256']),
                    'Frozen hover bytes differ from the actual current source')
        else:
            require(path in implicit and previous is not None and key(previous['path']) in parent_implicit and
                    same(previous, parent_implicit[key(previous['path'])]) and
                    (row['bytes'], row['sha256']) == (previous['bytes'], previous['sha256']),
                    'Only exact implicit libraries may lack a current original')
            missing.add(path)
        if origin in changes:
            require(row.get('materialization') == material.get('materialization') == 'owned_changed_source_copy' and
                    'reused_from_path' not in material and actual['file_identity'] != files.verify(current[origin])['file_identity'] and
                    files.ordinary(row['path']).st_nlink == 1 and actual['file_attributes'] & stat.FILE_ATTRIBUTE_READONLY and
                    (previous is None or actual['file_identity'] != previous['file_identity']), 'Hover source is not an independent readonly copy')
            copied.add(origin)
            copied_bytes += actual['bytes']
        else:
            require(previous is not None and row.get('materialization') == material.get('materialization') == 'attested_snapshot_hardlink' and
                    key(material['reused_from_path']) == key(previous['path']) and
                    all(actual[name] == files.verify(previous)[name] for name in ('file_identity', 'mtime_ns', 'file_attributes')),
                    'Hover input is not the exact unchanged parent hardlink')
            links += 1
    require(copied == changes and links == 589 and copied_bytes == 420065 and missing == set(implicit) and
            len(set(current) - origins) == 8 and origins - set(current) == {key(row['original_path']) for row in implicit.values()} and
            att['frozen_reuse'] == dict(donor_hardlinks=589, private_source_copies=4, copied_source_bytes=420065,
                                       donor_content_and_metadata_preserved=True), 'Hover private/shared/current/implicit counts differ')
    units, attest_units = build['final_compilation']['translation_units'], att['compilation']
    require(len(units) == len(attest_units) == 5 and run['compilation'] == units and
            run['actual_dependency_counts'] == list(COUNTS), 'Hover five-TU contract differs')
    targets, deleted = rows(plan['targets']), rows(retirement['deleted'])
    require(len(targets) == len(deleted) == audit['deleted_files'] == 12 and set(targets) == set(deleted) and
            all(same(row, deleted[path]) for path, row in targets.items()) and
            not any(os.path.lexists(row['path']) for row in targets.values()) and
            plan.get('recursive_deletion') is False and plan.get('user_originals_or_saves_or_current_executable_deleted') is False,
            'Hover retirement is not the exact absent twelve-file plan')
    retired, union = {}, set()
    commands = run['commands']
    require(len(commands) == att['actual_commands'] == 7 and att['command_returncodes'] == [0] * 7 and
            [item['phase'] for item in commands] == ['environment', *('compile_' + name for name in TUS), 'link'] and
            all(type(item['returncode']) is int and item['returncode'] == 0 and not item.get('timed_out', False) and
                'error_type' not in item for item in commands), 'Hover seven-command result differs')
    rewrite = lambda raw: raw.decode('utf-8-sig').replace('\r\n', '\n').replace(str(parent_root), str(root)).replace(parent_root.as_posix(), root.as_posix())
    for index, (unit, observed, name, stem, old) in enumerate(zip(units, attest_units, TUS, STEMS,
                                                                 parent['final_compilation']['translation_units'])):
        obj = unit['object']; expected = root / f'final/tu_{index:02d}_{name}/obj/{stem}.obj'
        require(unit['translation_unit'] == observed['translation_unit'] == name and
                unit['returncode'] == observed['returncode'] == 0 and unit['coff_machine'] == observed['coff_machine'] == '0x8664' and
                observed['object_bytes'] == obj['bytes'] and pair(obj)[0] == key(expected) and key(expected) in targets and
                same(obj, targets[key(expected)]), 'Retired hover object lacks exact compile/attestation provenance')
        retired[pair(obj)] = obj
        data = files.json(unit['dependency_report'])
        fields = data.get('Data', {})
        require(data.get('Version') == '1.2' and type(fields.get('Source')) is str and type(fields.get('Includes')) is list and
                all(type(path) is str for path in fields['Includes']) and not fields.get('ProvidedModule') and
                not fields.get('ImportedModules') and not fields.get('ImportedHeaderUnits'), 'Unexpected hover dependency schema')
        actual = {key(path) for path in (fields['Source'], *fields['Includes'])}
        require(actual <= set(compiler) and len(actual) == unit['actual_dependency_count'] == unit['expected_dependency_count'] ==
                observed['dependencies'] == COUNTS[index] and Path(unit['response']['path']) == relocate(old['response']['path']) and
                Path(unit['dependency_report']['path']) == relocate(old['dependency_report']['path']) and
                commands[index + 1]['command'] == [build['compiler']['path'], '@' + unit['response']['path']] and
                key(commands[index + 1]['cwd']) == key(Path(unit['response']['path']).parent) and
                same(commands[index + 1]['log'], unit['log']), 'Hover actual dependency/command binding differs')
        response = read(files, unit['response']).decode('utf-8-sig').replace('\r\n', '\n')
        require(response == rewrite(read(files, old['response'])), 'Hover response changed beyond exact parent root relocation')
        union.update(actual)
        files.verify(unit['log'])
    require(union == set(compiler) and len(union) == 550 and build['final_dependency_reports'] ==
            {unit['translation_unit']: unit['dependency_report'] for unit in units} and
            build['response'] == units[0]['response'] and build['dependency_report'] == units[0]['dependency_report'],
            'Hover actual compiler union or dependency aliases differ')
    setup_path = key(root / 'read_build_environment.cmd')
    require(setup_path in targets and targets[setup_path]['bytes'] == 151 and targets[setup_path]['sha256'] ==
            '2feb75fb87e27677dcc5a815af9b4a766c8500c8e11860ed668c8f405e2d0b90' and
            key(commands[0]['command'][0]) == key(Path(r'C:\Windows\System32\cmd.exe')) and
            commands[0]['command'][1:] == ['/d', '/c', str(root / 'read_build_environment.cmd')] and
            key(commands[0]['cwd']) == key(root), 'Retired environment setup or command differs')
    toolchain = rows(started['toolchain_inputs'])
    require({Path(row['path']).name.casefold() for row in toolchain.values()} == {'c1xx.dll', 'c2.dll', 'cmd.exe'} and len(toolchain) == 3,
            'Hover compiler backend/toolchain inventory differs')
    for row in toolchain.values():
        files.verify(row)
    require(key(commands[0]['command'][0]) in toolchain and
            commands[-1]['command'] == [build['linker']['path'], '@' + build['link_response']['path']] and
            key(commands[-1]['cwd']) == key(Path(build['link_response']['path']).parent) and
            same(commands[-1]['log'], build['link_log']), 'Hover environment/link executable lacks its sealed recipe')
    for item in commands:
        files.verify(item['log'])
    require(read(files, build['link_response']).decode('utf-8-sig').replace('\r\n', '\n') == rewrite(read(files, parent['link_response'])),
            'Hover link response changed beyond exact root relocation')
    linked = re.findall(r'^"([^"\n]+\.obj)"$', read(files, build['link_response']).decode('utf-8-sig').replace('\r\n', '\n'), re.I | re.M)
    require([key(path) for path in linked] == [pair(unit['object'])[0] for unit in units], 'Hover link did not consume exactly five attested objects')
    image = build['executable']
    actual_imports = pe_observations(read(files, image, 32 * 1024 * 1024))
    imports = files.json(build['imports']['log'])
    require(image['sha256'] == EXE_SHA and pair(image)[0] == key(root / 'final/ZeroSisHost_x64.exe') and
            image['bytes'] == 6517248 and image['pe'] == dict(architecture='x64', pe_format='PE32+', is_dll=False) and
            all(same(value, image) for value in (att['executable'], audit['executable'], publication['current_host'])) and
            actual_imports == build['imports']['dependencies'] == att['imports'] == imports['dependencies'] and
            same(imports['image'], image) and imports.get('source') == 'PURE_FILE_BACKED_PE_IMPORT_DIRECTORY' and
            build['catalog'] == att['generated_catalog'] and build['catalog']['entry_count'] == 67 and
            build['catalog']['ordered_payload_manifest_sha256'] == 'db76873a3dff1360b89a4b57cc6c0da51893ace2efb234c5f83b739227bb411c' and
            att['restore_contract_marker_count'] == 1 and att['marker_inclusion_evidence_only'] is True and
            build['restore_contract_marker']['ascii'] == MARKER.decode('ascii') and
            build['restore_contract_marker']['inclusion_evidence_only'] is True and
            build['actual_implicit_library_namesfrommap'] == att['actual_map_implicit_libraries'] == sorted(MAP_LIBRARIES),
            'Hover retained PE/import/catalog/marker provenance differs')
    # Only the report's protection field contains the two build-time document
    # identities. Current publication text is not an executable dependency and
    # may be revised by later preparation publication. No after-SHA is imposed.
    retired_visits = set()
    for field, value in build.items():
        if field == 'protected_artifacts':
            continue
        for row in walk(value):
            identity = pair(row)
            if identity in retired:
                require(field == 'final_compilation' and row['bytes'] == retired[identity]['bytes'], 'Retired object exceeds its compile-only role')
                retired_visits.add(identity)
            else:
                files.verify(row)
    require(retired_visits == set(retired), 'Incomplete exact five-object retirement reference coverage')
    files.finish()
    environment = targets[setup_path]
    return dict(scope='RETAINED_HOVER_REPAINT_HOST_RUNTIME_PREPARATION_ONLY', registered_build_id=BUILD_ID,
        build_result=files.verify(report_ref), attestation=files.verify(refs['attestation']),
        retirement=files.verify(refs['retirement']), publication_audit=files.verify(refs['audit']),
        retained_artifact_identities_verified=len(files.checked), compiler_dependency_count=550,
        current_source_count=593, source_manifest_count=86, materialized_input_count=593,
        private_source_copies=4, donor_hardlinks=589, copied_source_bytes=420065, absent_discovery_objects=[],
        absent_final_objects=[dict(original_path=row['path'], bytes=row['bytes'], sha256=row['sha256']) for row in retired.values()],
        absent_environment_setup=dict(original_path=environment['path'], bytes=environment['bytes'], sha256=environment['sha256']),
        historical_source_backups_verified=3, historical_metadata_backups_verified=2,
        historical_metadata=[dict(before=row, purpose='BUILD_TIME_NONCOMPILED_PUBLICATION_METADATA') for row in metadata.values()],
        current_metadata_after_sha_pinned=False, parent_report_context_only=True,
        protected_runtime_inputs=24, protected_native_saves=6, protected_artifact_count=41,
        current_hover_repaint_host_linked=True, static_catalog_payloads=67, actual_import_count=24, restore_marker_count=1,
        host_executed=False, sdk_restore_verified=False, native_restore_approved=False, save_compatibility_verified=False,
        actual_window_wheel_routing_verified=False, live_ui_verified=False, execution_authorized=False, full_engine_goal_complete=False)
