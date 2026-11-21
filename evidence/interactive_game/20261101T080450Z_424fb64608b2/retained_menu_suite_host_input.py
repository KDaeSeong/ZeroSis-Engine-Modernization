"""File-only input gate for registered ExitConfirm and later menu-suite Hosts.

Registration seals a build, not whichever source happens to be current. Every
compiled dependency and catalog payload is recovered from that build's frozen
closure. Preparation separately rehashes the actual source closure; a stale Host
cannot become the latest pair merely because its old snapshot still verifies.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct


EXIT_BUILD_ID = '20261026T133507Z_ea39cdb67229'
PROFILE_ROOT = 'evidence/game_menu/offline_menu_suite/pair_preparation'
FROZEN_PROFILE_NAME = 'retained_menu_suite_host_input.profile.json'
TUS = ('host_main', 'window', 'renderer', 'world_renderer', 'terrain_renderer')
STEMS = ('HostMain', 'BitmapWindow', 'BitmapRenderer', 'WorldViewRenderer', 'WorldTerrainRenderer')
FROZEN_GROUPS = ('compiler_inputs', 'sources', 'provider_inputs', 'system_libraries',
                 'build_tools', 'implicit_libraries')
MARKER = b'NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|'
OFFLINE_FIELDS = ('host_runtime_executed', 'gamecore_loaded', 'sdk_linked', 'mods_updated',
                  'stage_updated', 'default_promoted', 'sdk_restore_verified',
                  'native_restore_approved', 'full_engine_goal_complete')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def pair(row):
    require(type(row) is dict and type(row.get('path')) is str and
            type(row.get('bytes')) is int and row['bytes'] >= 0 and
            re.fullmatch(r'[0-9a-f]{64}', row.get('sha256', '')),
            'Malformed retained menu Host artifact')
    require(Path(row['path']).is_absolute() and '..' not in Path(row['path']).parts,
            'Noncanonical retained menu Host artifact')
    return key(row['path']), row['sha256']


def same(left, right):
    return pair(left) == pair(right) and left['bytes'] == right['bytes']


def rows(value):
    require(type(value) is list, 'Menu Host inventory must be a list')
    result = {}
    for row in value:
        path = pair(row)[0]
        require(path not in result, 'Duplicate menu Host inventory path')
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


def _profile_path(relative):
    directory = Path(__file__).absolute().parent
    if directory.name == 'tools':
        return directory.parent / PROFILE_ROOT / relative
    # A frozen preparation must carry its own authenticated registration. It
    # never searches an active tools directory for a more convenient profile.
    return directory / FROZEN_PROFILE_NAME


def registration_reference(build_id):
    # Registration lives in the noncompiled dispatcher. Adding the final build
    # does not edit this parser after it has become a frozen producer input.
    from retained_host_runtime_input import MENU_PROFILE_PINS
    pinned = MENU_PROFILE_PINS.get(build_id)
    require(pinned is not None, 'Unregistered retained menu Host build')
    relative, digest = pinned
    require(re.fullmatch(r'[0-9a-f]{64}', digest) and not Path(relative).is_absolute() and
            '..' not in Path(relative).parts, 'Menu Host registration is not sealed')
    return dict(path=str(_profile_path(relative)), sha256=digest)


def registered_host_spec(build_id, files):
    """Read only the exact profile authorized by the authenticated helper."""
    from retained_host_runtime_input import MENU_PROFILE_PINS
    if build_id not in MENU_PROFILE_PINS:
        return None
    reference = registration_reference(build_id)
    profile = files.json(reference)
    require(type(profile) is dict and profile.get('schema') == 'zerosis.retained_menu_host.profile.v1' and
            profile.get('kind') == 'retained_menu_suite' and profile.get('build_id') == build_id,
            'Retained menu Host registration identity differs')
    for name in ('report', 'attestation', 'run', 'audit', 'cleanup_plan', 'cleanup_result', 'retirement_ledger'):
        relative = Path(profile.get(name + '_path', ''))
        require(str(relative) not in ('', '.') and not relative.is_absolute() and '..' not in relative.parts and
                re.fullmatch(r'[0-9a-f]{64}', profile.get(name + '_sha256', '')),
                'Malformed registered menu Host proof: ' + name)
    require(type(profile.get('executable_bytes')) is int and profile['executable_bytes'] > 0 and
            re.fullmatch(r'[0-9a-f]{64}', profile.get('executable_sha256', '')) and
            type(profile.get('catalog')) is dict and type(profile.get('required_payloads')) is list and
            set(('ZeroSisUiScene', 'ExitConfirm', 'ExitConfirmLayout')) <= set(profile['required_payloads']),
            'Incomplete registered menu Host payload contract')
    files.finish()
    return profile


def reference(project, spec, name):
    return dict(path=str(project / spec[name + '_path']), sha256=spec[name + '_sha256'])


def read(files, row, maximum=32 * 1024 * 1024):
    actual = files.verify(row)
    require(actual['bytes'] <= maximum, 'Retained menu Host read exceeds its bound')
    raw = Path(actual['path']).read_bytes()
    require(len(raw) == actual['bytes'] and hashlib.sha256(raw).hexdigest() == actual['sha256'],
            'Retained menu Host input changed while reading')
    return raw


def frozen_rows(build):
    """Normalize the original-source alias without trusting a donor as source."""
    result = {}
    source_paths = set(rows(build['sources']))
    values = [row for group in FROZEN_GROUPS for row in build[group]]
    values += [*build['provider_reports'].values(), build['shared_lua_build'], build['ui_assets']]
    for original in values:
        row = dict(original)
        path = pair(row)[0]
        alias = row.get('original_source')
        if alias is not None:
            require(path in source_paths and type(alias) is str and
                    (not row.get('original_path') or key(row['original_path']) == key(alias) or
                     Path(alias).suffix.casefold() == '.lua'),
                    'Only a Lua source-manifest row may change its donor original-path alias')
            # ExitConfirm's eight inherited Lua rows retain a donor original_path.
            # original_source is their actual source identity and must separately
            # match the sealed current-source inventory below.
            row['origin'] = alias
        else:
            row['origin'] = row.get('original_path')
        require(type(row['origin']) is str and Path(row['origin']).is_absolute() and
                '..' not in Path(row['origin']).parts,
                'Frozen menu Host input lacks a canonical original source')
        if path in result:
            previous = result[path]
            require(same(previous, row) and key(previous['origin']) == key(row['origin']) and
                    all(previous.get(field) == row.get(field) for field in
                        ('file_identity', 'mtime_ns', 'file_attributes', 'materialization')),
                    'Conflicting frozen menu Host aliases')
        else:
            result[path] = row
    return result


def parse_catalog(raw, expected_count, required):
    """Parse the generated registry at its sealed count, without source rewriting."""
    require(type(expected_count) is int and 3 <= expected_count <= 1024,
            'Invalid sealed menu catalog count')
    require(len(raw) <= 32 * 1024 * 1024 and b'\r' not in raw,
            'Generated menu catalog is not bounded canonical LF text')
    arrays, order, index = {}, None, 0
    lines = raw.splitlines(keepends=True)
    while index < len(lines):
        line = lines[index]
        index += 1
        match = re.fullmatch(rb'static const char ([A-Za-z_][A-Za-z0-9_]*)\[\]=\n', line)
        if match:
            name = match[1].decode('ascii')
            require(name not in arrays and order is None, 'Duplicate or misplaced menu source array')
            value, previous = bytearray(), None
            while True:
                require(index < len(lines), 'Truncated menu source array')
                line = lines[index]
                index += 1
                final = line.endswith(b';\n')
                chunk = line[:-2] if final else line[:-1]
                require(re.fullmatch(rb'"(?:\\x[0-9a-f]{2}){0,64}"', chunk) and
                        (previous is None or previous == 64), 'Menu source array is not exact hex64 chunks')
                data = bytes.fromhex(chunk[1:-1].replace(b'\\x', b'').decode('ascii'))
                require(data or final and previous is None, 'Empty nonterminal menu source chunk')
                value.extend(data)
                previous = len(data)
                require(len(value) <= 32 * 1024 * 1024, 'Menu source payload exceeds its bound')
                if final:
                    break
            require(b'\0' not in value, 'NUL in menu source payload')
            arrays[name] = bytes(value)
        elif line == b'static const Script scripts[]={\n':
            require(order is None, 'Repeated menu source registry')
            order = []
            while index < len(lines) and lines[index] != b'};\n':
                match = re.fullmatch(rb'\{"([A-Za-z_][A-Za-z0-9_]*)",\1,sizeof\(\1\)-1\},\n', lines[index])
                require(match, 'Malformed menu source registry row')
                name = match[1].decode('ascii')
                require(name in arrays and name not in order, 'Missing or repeated menu registry symbol')
                order.append(name)
                index += 1
            require(index < len(lines), 'Truncated menu source registry')
            index += 1
    require(order and len(order) == len(arrays) == expected_count and set(order) == set(arrays) and
            set(required) <= set(order), 'Generated menu catalog differs from its sealed count or payloads')
    return arrays, order


class PE:
    """Bounded AMD64 image parsing using bytes; it never loads a module."""
    def __init__(self, raw):
        self.data = raw
        require(len(raw) >= 64 and raw[:2] == b'MZ', 'Menu Host lacks a DOS header')
        offset = self.number(0x3c, '<I')
        require(raw[offset:offset + 4] == b'PE\0\0' and self.number(offset + 4, '<H') == 0x8664,
                'Menu Host is not an AMD64 PE')
        count, size = self.number(offset + 6, '<H'), self.number(offset + 20, '<H')
        flags, optional = self.number(offset + 22, '<H'), offset + 24
        require(flags & 0x20 and not flags & 0x2000 and 0 < count <= 96 and size >= 128 and
                self.number(optional, '<H') == 0x20b and self.number(optional + 108, '<I') >= 2,
                'Menu Host is not a PE32+ executable with imports')
        self.base, self.sections = self.number(optional + 24, '<Q'), []
        for index in range(count):
            at = optional + size + index * 40
            require(at + 40 <= len(raw), 'Truncated menu Host section table')
            length, pointer = self.number(at + 16, '<I'), self.number(at + 20, '<I')
            require(pointer <= len(raw) and length <= len(raw) - pointer, 'Truncated menu Host section')
            self.sections.append(dict(name=raw[at:at + 8].split(b'\0', 1)[0].decode('ascii'),
                rva=self.number(at + 12, '<I'), raw=pointer, size=length, flags=self.number(at + 36, '<I')))
        self.import_rva, self.import_size = struct.unpack_from('<II', raw, optional + 120)

    def number(self, offset, format):
        require(0 <= offset <= len(self.data) - struct.calcsize(format), 'PE scalar exceeds image')
        return struct.unpack_from(format, self.data, offset)[0]

    def mapped(self, rva, size, readonly=False):
        matches = [row for row in self.sections if row['rva'] <= rva and
                   rva - row['rva'] <= row['size'] and size <= row['size'] - (rva - row['rva'])]
        require(len(matches) == 1, 'PE address lacks one file-backed section')
        row = matches[0]
        require(not readonly or row['flags'] & 0x40000000 and not row['flags'] & 0xa0000000,
                'Menu catalog is not readonly nonexecutable data')
        return row['raw'] + rva - row['rva'], row

    def occurrences(self, value):
        require(value, 'Empty PE byte search is forbidden')
        result = []
        for row in self.sections:
            if not row['flags'] & 0x40000000 or row['flags'] & 0xa0000000:
                continue
            end = row['raw'] + row['size']
            at = self.data.find(value, row['raw'], end)
            while at >= 0:
                result.append(row['rva'] + at - row['raw'])
                at = self.data.find(value, at + 1, end)
        return result

    def cstring(self, rva):
        at, row = self.mapped(rva, 1)
        end = self.data.find(b'\0', at, min(at + 4096, row['raw'] + row['size']))
        require(end >= at, 'Unterminated PE string')
        return self.data[at:end]

    def imports(self):
        require(self.import_rva and self.import_size >= 20, 'Menu Host lacks imports')
        names = []
        for index in range(min(1024, self.import_size // 20)):
            at, _ = self.mapped(self.import_rva + index * 20, 20)
            descriptor = struct.unpack_from('<5I', self.data, at)
            if not any(descriptor):
                require(len(names) == len(set(names)), 'Duplicate PE import names')
                return names
            names.append(self.cstring(descriptor[3]).decode('ascii').casefold())
        raise RuntimeError('Unterminated PE import directory')

    def catalog(self, arrays, order):
        anchor, candidates = 'ZeroSisUiScene', set()
        require(arrays.get(anchor), 'Menu catalog lacks its nonempty scene anchor')
        for name_rva in self.occurrences(anchor.encode('ascii') + b'\0'):
            for data_rva in self.occurrences(arrays[anchor] + b'\0'):
                record = struct.pack('<QQQ', self.base + name_rva, self.base + data_rva, len(arrays[anchor]))
                candidates.update(rva - order.index(anchor) * 24 for rva in self.occurrences(record) if rva % 8 == 0)
        require(len(candidates) == 1, 'Menu Host lacks one exact source registration table')
        table = candidates.pop()
        at, section = self.mapped(table, len(order) * 24, True)
        proof = []
        for index, name in enumerate(order):
            name_va, data_va, size = struct.unpack_from('<QQQ', self.data, at + 24 * index)
            require(name_va >= self.base and data_va >= self.base, 'Foreign menu catalog address')
            name_rva, data_rva = name_va - self.base, data_va - self.base
            self.mapped(name_rva, len(name) + 1, True)
            payload, _ = self.mapped(data_rva, size + 1, True)
            require(self.cstring(name_rva) == name.encode('ascii') and size == len(arrays[name]) and
                    self.data[payload:payload + size] == arrays[name] and self.data[payload + size] == 0,
                    'PE menu payload differs from frozen source: ' + name)
            proof.append(dict(name=name, index=index, bytes=size, sha256=hashlib.sha256(arrays[name]).hexdigest()))
        return dict(entry_count=len(order), table_rva=table, table_section=section['name'], stride=24,
            total_payload_bytes=sum(row['bytes'] for row in proof), ordered_payload_manifest_sha256=hashlib.sha256(
                json.dumps(proof, sort_keys=True, separators=(',', ':')).encode('ascii')).hexdigest())


def _retirement(build, project, spec, proof, files):
    root = project / 'Build/UiWindowHost' / build['build_id']
    ledger, plan, result = (proof[name] for name in ('retirement_ledger', 'cleanup_plan', 'cleanup_result'))
    require(ledger.get('schema') == 'zerosis.menu_host.typed_retirement.v1' and
            ledger.get('build_id') == build['build_id'] and ledger.get('native_execution') is False and
            ledger.get('historical_only') is True and ledger.get('missing_input_exception_scope') == 'EXACT_TYPED_SIX_INTERMEDIATES' and
            all(same(ledger[name], files.verify(reference(project, spec, name))) for name in
                ('report', 'attestation', 'cleanup_plan', 'cleanup_result')),
            'Retired menu intermediates lack their sealed typed provenance')
    candidates, typed = rows(plan['candidates']), rows(ledger['retired'])
    units = build['final_compilation']['translation_units']
    require(len(units) == 5 and len(candidates) == len(typed) == 6 and set(candidates) == set(typed) and
            result.get('status') == spec['cleanup_status'] and result.get('files_deleted') == 6 and
            result.get('plan_sha256') == spec['cleanup_plan_sha256'] and
            result.get('all_candidates_absent') is True and result.get('current_image_unchanged') is True and
            result.get('protected_objects_or_sources_deleted') is False and
            result.get('runtime_default_or_saves_deleted') is False and
            plan.get('historical_object_refs_retired_after_verification') is True and
            same(plan['retained_current_executable'], build['executable']),
            'Menu intermediate retirement differs from the exact absent six-file plan')
    expected = {}
    for index, (unit, name, stem) in enumerate(zip(units, TUS, STEMS)):
        artifact = unit['object']
        path = key(root / f'final/tu_{index:02d}_{name}/obj/{stem}.obj')
        require(pair(artifact)[0] == path and path in typed and
                typed[path].get('role') == 'FINAL_COFF_OBJECT' and typed[path].get('translation_unit') == name and
                same(artifact, typed[path]) and same(artifact, candidates[path]),
                'Retired object escaped its exact final-compilation role')
        expected[path] = artifact
    setup = key(root / 'read_build_environment.cmd')
    require(setup in typed and typed[setup].get('role') == 'BUILD_ENVIRONMENT_SCRIPT' and
            typed[setup].get('translation_unit') is None and same(typed[setup], candidates[setup]),
            'Retired environment script escaped its exact build-only role')
    expected[setup] = candidates[setup]
    require(set(expected) == set(typed) and all(not os.path.lexists(row['path']) for row in typed.values()),
            'A retired menu intermediate reappeared or an extra path was waived')
    for row in typed.values():
        for ancestor in Path(row['path']).parents:
            try:
                info = ancestor.lstat()
            except FileNotFoundError:
                continue
            require(stat.S_ISDIR(info.st_mode) and not stat.S_ISLNK(info.st_mode) and
                    not getattr(info, 'st_file_attributes', 0) & 0x400,
                    'Retired menu artifact has a nonordinary ancestor')
    return expected


def _closure(build, project, spec, run, files):
    root = project / 'Build/UiWindowHost' / build['build_id']
    frozen, current = frozen_rows(build), rows(build['current_source_inputs'])
    compiler, sources = rows(build['compiler_inputs']), rows(build['sources'])
    materialized = rows(run['materialized'])
    require(len(frozen) == spec['materialized_input_count'] and len(current) == spec['current_source_count'] and
            len(compiler) == build['compiler_dependency_count'] == spec['compiler_dependency_count'] and
            len(sources) == spec['source_manifest_count'] and set(materialized) == set(frozen) and
            rows(run['current_inputs']) == current,
            'Frozen/current menu source closure inventory differs')
    origins, live_aliases, copies, hardlinks = set(), {}, 0, 0
    implicit = set(rows(build['implicit_libraries']))
    for path, row in frozen.items():
        actual = files.verify(row)
        origin = key(row['origin'])
        require(Path(row['path']).is_relative_to(root / 'frozen') and origin not in origins and
                same(materialized[path], row) and
                all(materialized[path].get(field) == row.get(field) for field in
                    ('file_identity', 'mtime_ns', 'file_attributes', 'materialization', 'reused_from_path')),
                'Duplicate or escaped frozen menu Host source')
        origins.add(origin)
        if origin in current:
            require((actual['bytes'], actual['sha256']) == (current[origin]['bytes'], current[origin]['sha256']),
                    'Frozen menu Host bytes differ from the sealed actual-source snapshot')
            live_aliases[origin] = row
        else:
            require(path in implicit, 'Only sealed implicit libraries may lack an actual-source snapshot')
        method = row.get('materialization')
        if method == 'attested_snapshot_hardlink':
            donor_path = row.get('reused_from_path')
            require(type(donor_path) is str and Path(donor_path).is_relative_to(project / 'Build/UiWindowHost') and
                    not Path(donor_path).is_relative_to(root), 'Frozen menu hardlink lacks a distinct attested donor')
            donor = files.verify(dict(path=donor_path, bytes=row['bytes'], sha256=row['sha256']))
            require(actual['file_identity'] == donor['file_identity'], 'Frozen menu input is not its declared donor hardlink')
            hardlinks += 1
        else:
            require(method in ('owned_changed_source_copy', 'owned_added_source_copy') and
                    'reused_from_path' not in row and files.ordinary(row['path']).st_nlink == 1,
                    'Frozen menu source copy is not independently owned')
            copies += 1
    require(hardlinks == spec['donor_hardlinks'] and copies == spec['private_source_copies'] and
            hardlinks + copies == len(frozen), 'Frozen menu Host materialization methods differ')
    extras = set(current) - set(live_aliases)
    expected_extras = {key(project / relative) if not Path(relative).is_absolute() else key(relative)
                       for relative in spec['nonfrozen_current_inputs']}
    require(extras == expected_extras, 'Menu current-source closure has an unaccounted nonfrozen input')
    for path in extras:
        files.verify(current[path])
    return frozen, current, compiler, live_aliases


def validate_retained_menu_suite_host_runtime(build, project, spec, files):
    """Validate the sealed frozen Host without any native execution permission."""
    project = Path(project).absolute()
    require(getattr(files, 'check_metadata', False) is True, 'Menu Host gate requires metadata-aware sealed files')
    expected = registered_host_spec(build.get('build_id'), files)
    require(expected is not None and all(spec.get(name) == value for name, value in expected.items()),
            'Unregistered or changed retained menu Host specification')
    report_ref = reference(project, spec, 'report')
    sealed = files.json(report_ref)
    require(json.dumps(build, sort_keys=True, separators=(',', ':')) == json.dumps(sealed, sort_keys=True, separators=(',', ':')) and
            build.get('build_id') == spec['build_id'] and build.get('schema') == 'zerosis.ui_window_host_build.v1' and
            build.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and build.get('source_inputs_unchanged') is True and
            build.get('provider_inputs_unchanged') is True and all(build.get(name) is False for name in OFFLINE_FIELDS),
            'Menu Host report is not its sealed successful offline build')
    proof = {name: files.json(reference(project, spec, name)) for name in
             ('attestation', 'run', 'audit', 'cleanup_plan', 'cleanup_result', 'retirement_ledger')}
    att, run, audit = (proof[name] for name in ('attestation', 'run', 'audit'))
    require(att.get('schema') == spec['attestation_schema'] and att.get('status') == spec['attestation_status'] and
            run.get('schema') == spec['run_schema'] and run.get('status') == spec['run_status'] and
            audit.get('schema') == spec['audit_schema'] and audit.get('status') == spec['audit_status'] and
            run.get('build_id') == audit.get('build_id') == spec['build_id'] and
            same(run['build_result'], files.verify(report_ref)) and
            key(project / att['build_result']['path']) == key(report_ref['path']) and
            att['build_result']['sha256'] == spec['report_sha256'] and
            att['build_result']['bytes'] == files.verify(report_ref)['bytes'] and
            same(audit['build_result'], files.verify(report_ref)) and
            same(audit['independent_static_attestation'], files.verify(reference(project, spec, 'attestation'))) and
            same(audit['cleanup'], files.verify(reference(project, spec, 'cleanup_result'))) and
            run.get('host_sdk_clr_window_gpu_or_dll_executed') is False and
            att.get('host_or_sdk_or_dll_or_window_execution') is False and
            att.get('full_native_or_original_ui_acceptance') is False and
            audit.get('original_Host_SDK_game_window_or_GPU_execution') is False and
            audit.get('current_native_or_screen_relaunch_allowed') is False and
            audit.get('screen_verification_deferred') is True and
            audit.get('default_promoted') is False and audit.get('full_engine_goal_complete') is False,
            'Menu Host proof graph or offline boundary differs')
    retired = _retirement(build, project, spec, proof, files)
    frozen, current, compiler, aliases = _closure(build, project, spec, run, files)
    units, union = build['final_compilation']['translation_units'], set()
    discovery = build.get('dependency_discovery', {})
    expected_phases = ['environment']
    if discovery.get('executed') is True:
        expected_phases += ['discover_' + name for name in TUS]
    expected_phases += ['compile_' + name for name in TUS] + ['link']
    compile_commands = [command for command in run['commands'] if command.get('phase', '').startswith('compile_')]
    require(run['compilation'] == units and len(run['commands']) == len(expected_phases) and
            [command.get('phase') for command in run['commands']] == expected_phases and
            len(compile_commands) == 5 and not run.get('denied_operations') and
            all(type(command.get('returncode')) is int and command['returncode'] == 0 and
                not command.get('timed_out', False) and 'error_type' not in command for command in run['commands']),
            'Menu Host compile/link command completion differs')
    if discovery.get('executed') is True:
        discovered = discovery.get('translation_units')
        require(discovery.get('syntax_only') is True and type(discovered) is list and len(discovered) == 5 and
                run.get('discovery') == discovered, 'Menu Host actual syntax-discovery inventory differs')
        for index, (unit, name) in enumerate(zip(discovered, TUS)):
            data = files.json(unit['dependency_report'])
            fields = data.get('Data', {})
            require(data.get('Version') == '1.2' and type(fields.get('Source')) is str and
                    type(fields.get('Includes')) is list and not unit.get('objects') and unit.get('returncode') == 0 and
                    unit.get('translation_unit') == name, 'Menu Host discovery is not bounded syntax-only compilation')
            actual = {key(path) for path in (fields['Source'], *fields['Includes'])}
            expected_origins = {key(frozen[path]['origin']) for path in
                                rows(build['compiler_inputs']) if key(frozen[path]['origin']) in actual}
            require(actual == expected_origins == {key(path) for path in unit['actual_paths']} and
                    actual <= set(current) and len(actual) == unit['actual_dependency_count'] and
                    run['commands'][1 + index]['command'] == [build['compiler']['path'], '@' + unit['response']['path']] and
                    '/Zs' in read(files, unit['response']).decode('utf-8-sig').splitlines(),
                    'Actual menu syntax discovery escaped its sealed original-source closure')
    for index, (unit, name) in enumerate(zip(units, TUS)):
        data = files.json(unit['dependency_report'])
        fields = data.get('Data', {})
        require(data.get('Version') == '1.2' and type(fields.get('Source')) is str and
                type(fields.get('Includes')) is list and all(type(path) is str for path in fields['Includes']) and
                not any(fields.get(field) for field in ('ProvidedModule', 'ImportedModules', 'ImportedHeaderUnits')),
                'Unexpected menu Host actual compiler dependency schema')
        actual = {key(path) for path in (fields['Source'], *fields['Includes'])}
        require(actual <= set(compiler) and len(actual) == unit['actual_dependency_count'] ==
                unit['expected_dependency_count'] == spec['dependency_counts'][index] and
                unit['translation_unit'] == name and unit['returncode'] == 0 and unit['coff_machine'] == '0x8664' and
                unit['command'] == [build['compiler']['path'], '@' + unit['response']['path']] and
                compile_commands[index]['command'] == unit['command'] and
                same(compile_commands[index]['log'], unit['log']), 'Menu Host five-TU dependency/command binding differs')
        response = read(files, unit['response']).decode('utf-8-sig').replace('\r\n', '\n')
        output = re.findall(r'^/Fo"([^"\r\n]+)"$', response, re.M | re.I)
        dependency = re.findall(r'^/sourceDependencies "([^"\r\n]+)"$', response, re.M | re.I)
        source = re.findall(r'^"([^"\r\n]+\.(?:cpp|c))"$', response, re.M | re.I)
        require(len(output) == len(dependency) == 1 and
                len(source) == 1 and key(source[0]) == key(fields['Source']) and
                key(output[0]) in (key(unit['object']['path']), key(Path(unit['object']['path']).parent)) and
                key(dependency[0]) == pair(unit['dependency_report'])[0] and
                '/c' in response.splitlines() and
                '/Zs' not in response.splitlines(),
                'Menu Host response is not bound to its actual source/object')
        union.update(actual)
    root = project / 'Build/UiWindowHost' / spec['build_id']
    require(union == set(compiler) and
            run['commands'][0]['command'][1:] == ['/d', '/c', str(root / 'read_build_environment.cmd')] and
            run['commands'][-1]['command'] == [build['linker']['path'], '@' + build['link_response']['path']],
            'Menu Host environment or compiler dependency union differs')
    linked = re.findall(r'^"([^"\r\n]+\.obj)"$',
                        read(files, build['link_response']).decode('utf-8-sig').replace('\r\n', '\n'), re.I | re.M)
    require([key(path) for path in linked] == [pair(unit['object'])[0] for unit in units],
            'Menu Host link response did not consume exactly its five attested objects')
    image = build['executable']
    require(pair(image)[0] == key(root / 'final/ZeroSisHost_x64.exe') and
            (image['bytes'], image['sha256']) == (spec['executable_bytes'], spec['executable_sha256']) and
            image.get('pe') == dict(architecture='x64', pe_format='PE32+', is_dll=False) and
            all(same(row, image) for row in (att['image'], audit['executable'])), 'Registered menu Host image identity differs')
    pe = PE(read(files, image))
    imports = files.json(build['imports']['log'])
    require(pe.imports() == build['imports']['dependencies'] == att['imports'] == imports['dependencies'] and
            len(pe.imports()) == spec['import_count'] and same(imports['image'], image) and
            imports.get('source') == 'PURE_FILE_BACKED_PE_AND_COFF' and
            imports.get('executable_or_dll_loaded') is False and
            imports.get('clr_directory_empty') is True and imports.get('delay_import_directory_empty') is True and
            len(pe.occurrences(MARKER)) == 1 and
            att.get('restore_marker_readonly_occurrences') == 1 and
            build['restore_contract_marker'].get('ascii') == MARKER.decode('ascii') and
            build['restore_contract_marker'].get('inclusion_evidence_only') is True,
            'Menu Host file-backed PE/import/restore marker provenance differs')
    header = aliases.get(key(project / 'Source/Host/UiPopupAssets.generated.h'))
    require(header is not None and pair(header)[0] in compiler and
            same(att['header'], current[key(project / 'Source/Host/UiPopupAssets.generated.h')]),
            'Menu Host catalog is not its attested frozen compiler dependency')
    arrays, order = parse_catalog(read(files, header), spec['catalog']['entry_count'], spec['required_payloads'])
    catalog = pe.catalog(arrays, order)
    require(catalog == spec['catalog'] == build['catalog'] == att['catalog'],
            'Menu Host actual catalog differs from its frozen header and sealed profile')
    # An artifact may be historical only at its typed compile object location.
    # Mutable actual-source references are satisfied by that exact frozen input;
    # preparation must additionally pass check_current_source_closure below.
    retired_visits = set()
    historical_fields = {'current_source_inputs', 'sources_changed_from_baseline', 'new_source_inputs',
                         'source_revision_provenance'}
    for field, value in build.items():
        if field in historical_fields:
            continue
        for row in walk(value):
            path = pair(row)[0]
            if path in retired:
                require(field == 'final_compilation' and same(row, retired[path]),
                        'Retired artifact exceeds its exact compile-only role')
                retired_visits.add(path)
            elif field != 'protected_artifacts' and path in aliases:
                require(same(row, current[path]), 'Artifact source alias differs from the sealed actual-source identity')
                files.verify(aliases[path])
            else:
                files.verify(row)
    require(retired_visits == {pair(unit['object'])[0] for unit in units}, 'Incomplete retired-object reference coverage')
    for field in ('sources_changed_from_baseline', 'new_source_inputs'):
        for path, row in rows(build.get(field, [])).items():
            require(path in current and same(row, current[path]), 'Build source revision differs from its sealed source snapshot')
    for revision in build.get('source_revision_provenance', []):
        before, after, backup = revision['before'], revision['after'], revision['backup']
        path = pair(after)[0]
        require(path in current and same(after, current[path]) and key(before['original_path']) == path and
                (backup['bytes'], backup['sha256']) == (before['bytes'], before['sha256']),
                'Historical menu source revision lacks its exact preserved predecessor')
        files.verify(backup)
    require(att.get('compiler_input_count') == len(compiler) and att.get('current_input_count') == len(current) and
            att.get('frozen_input_count') == len(frozen) and att.get('actual_tu_dependency_counts') == list(spec['dependency_counts']) and
            att.get('code_objects_checked') == 5,
            'Independent menu Host source/dependency attestation differs')
    files.finish()
    return dict(scope='RETAINED_MENU_SUITE_HOST_FROZEN_INPUTS_PREPARATION_ONLY', registered_build_id=spec['build_id'],
        build_result=files.verify(report_ref), attestation=files.verify(reference(project, spec, 'attestation')),
        retirement=files.verify(reference(project, spec, 'retirement_ledger')),
        retained_artifact_identities_verified=len(files.checked), compiler_dependency_count=len(compiler),
        current_source_count=len(current), source_manifest_count=len(build['sources']), materialized_input_count=len(frozen),
        private_source_copies=spec['private_source_copies'], donor_hardlinks=spec['donor_hardlinks'],
        static_catalog_payloads=len(order), actual_import_count=spec['import_count'], absent_discovery_objects=[],
        absent_final_objects=[dict(original_path=unit['object']['path'], bytes=unit['object']['bytes'],
                                   sha256=unit['object']['sha256']) for unit in units],
        frozen_source_closure_verified=True, actual_current_source_recheck_required_for_preparation=True,
        actual_current_source_closure_verified=False, host_executed=False, sdk_restore_verified=False,
        native_restore_approved=False, save_compatibility_verified=False, live_ui_verified=False,
        native_execution=False, execution_authorized=False, full_engine_goal_complete=False)


def check_current_source_closure(build, project, spec, files):
    """Reject stale actual sources immediately before latest-pair materialization."""
    require(build.get('build_id') == spec['build_id'], 'Current-source check belongs to another menu Host')
    sealed = files.json(reference(Path(project).absolute(), spec, 'report'))
    require(build == sealed, 'Current-source check requires the exact registered report')
    current = rows(build['current_source_inputs'])
    require(len(current) == spec['current_source_count'], 'Current-source closure count differs')
    verified = [files.verify(row) for row in current.values()]
    files.finish()
    return dict(scope='ACTUAL_CURRENT_MENU_HOST_SOURCE_CLOSURE_PREPARATION_ONLY',
        build_id=spec['build_id'], actual_current_source_closure_verified=True,
        source_count=len(verified), verified_inputs=verified, native_execution=False,
        host_or_sdk_executed=False, default_promoted=False, full_engine_goal_complete=False)
