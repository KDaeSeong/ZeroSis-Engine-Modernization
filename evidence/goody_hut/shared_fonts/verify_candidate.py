"""Attest one new shared-font Host candidate by reading sealed files only.

No builder, catalog checker, provider, PE image or historical verifier is run.
"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct
import sys

sys.dont_write_bytecode = True
STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
SEAL_SHA = 'c0a2cc050f6f8d73da371200207396f7ba02cbf56eb4d1eed524b804729ffc9c'
WRAPPER_SHA = '74a057785ef50aaacf93e58993f903a7f01ff7be1f5d9c58105017419eb1f1c9'
CATALOG_PASS = 'PASS_SHARED_FONT_CATALOG_67_LUA51_PARSE_ONLY_NATIVE_PENDING'
TUS = ('host_main', 'window', 'renderer', 'world_renderer', 'terrain_renderer')
PHASES = ('dependency_discovery', 'final')
GENERATED = 'Source/Host/UiPopupAssets.generated.h'
USER_ROOTS = (r'C:\Users\home\OneDrive\Documents\My Games', r'C:\Users\home\Documents\My Games')


def require(value, message):
    if not value:
        raise RuntimeError(message)


def norm(path):
    return os.path.normcase(os.path.abspath(path))


def within(path, root):
    return norm(path) == norm(root) or norm(path).startswith(norm(root) + os.sep)


def ordinary(path):
    path = Path(path)
    require(path.is_absolute() and str(path) == os.path.abspath(path), 'Noncanonical input path')
    require(not any(within(path, root) for root in USER_ROOTS), 'Retail user state is forbidden')
    for ancestor in (path, *path.parents):
        info = ancestor.lstat()
        require(not getattr(info, 'st_file_attributes', 0) & 0x400, 'Reparse input or ancestor')
    info = path.stat()
    require(stat.S_ISREG(info.st_mode), 'Input is not an ordinary file: ' + str(path))
    return info


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, 'Duplicate JSON key: ' + name)
        result[name] = value
    return result


class Inputs:
    def __init__(self, reads):
        self.reads, self.rows = reads, {}

    def ref(self, path, expected=None):
        path = Path(path)
        before = ordinary(path)
        self.reads.add(norm(path))
        with path.open('rb') as stream:
            sha = hashlib.file_digest(stream, 'sha256').hexdigest()
        require(identity(before) == identity(path.stat()), 'Input changed while hashing')
        row = dict(path=str(path), bytes=before.st_size, sha256=sha)
        if expected is not None:
            require(type(expected) is dict and norm(expected['path']) == norm(path) and
                    expected['sha256'] == sha and expected.get('bytes', before.st_size) == before.st_size,
                    'Artifact identity differs: ' + str(path))
        require(norm(path) not in self.rows or self.rows[norm(path)] == row, 'Input changed between reads')
        self.rows[norm(path)] = row
        return row

    def sealed(self, row, expected_path=None):
        require(type(row) is dict and isinstance(row.get('path'), str) and
                re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')) and
                ('bytes' not in row or type(row['bytes']) is int and row['bytes'] >= 0), 'Malformed artifact reference')
        return self.ref(expected_path or row['path'], row)

    def read(self, path, limit=16 * 1024 * 1024):
        row = self.ref(path)
        require(row['bytes'] <= limit, 'Input exceeds its size bound: ' + str(path))
        raw = Path(path).read_bytes()
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'], 'Input changed while reading')
        return raw

    def document(self, path):
        return json.loads(self.read(path).decode('utf-8-sig'), object_pairs_hook=unique_object,
                          parse_constant=lambda value: require(False, 'Nonfinite JSON number'))

    def stable(self):
        for row in list(self.rows.values()):
            self.sealed(row)


def install_guard(output):
    reads, denied = set(), []
    published = False

    def audit(event, args):
        nonlocal published
        if event == 'open' and (not args or not isinstance(args[0], (str, bytes, os.PathLike))):
            denied.append('open');raise RuntimeError('Unscoped file descriptor open denied')
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            target = norm(os.fsdecode(args[0])).removeprefix('\\\\?\\')
            mode, flags = args[1:3]
            writing = isinstance(mode, str) and any(c in mode for c in 'wax+') or (
                type(flags) is int and flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            permitted = not any(within(target, root) for root in USER_ROOTS) and (
                target == norm(output) and not published and type(flags) is int and flags & os.O_EXCL and flags & os.O_CREAT
                if writing else target in reads)
            if not permitted:
                denied.append('open');raise RuntimeError('Unapproved verifier file open')
            if writing:
                published = True
        if event.startswith(('subprocess.', 'os.exec', 'os.spawn', 'ctypes.', 'socket.', 'urllib.', 'http.client.')) or event in (
                     'os.system', 'os.startfile', 'os.startfile/2', 'os.posix_spawn', 'os.posix_spawnp',
                     'os.fork', 'os.forkpty', 'os.kill', 'os.killpg', 'os.listdir', 'os.scandir', 'os.chdir',
                     'os.remove', 'os.rmdir', 'os.rename', 'os.mkdir', 'os.link', 'os.symlink', 'os.chmod'):
            denied.append(event)
            raise RuntimeError('Read-only PE attestor forbids: ' + event)
    sys.addaudithook(audit)
    return reads, denied


def literal(node, env, builder):
    """Read the signed builder's constant path/flag declarations without eval."""
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return literal(node.left, env, builder) / literal(node.right, env, builder)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [literal(item, env, builder) for item in node.elts]
    if isinstance(node, ast.Dict):
        return {literal(k, env, builder): literal(v, env, builder) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == 'Path' and not node.keywords:
        require(len(node.args) == 1, 'Unexpected Path constant')
        return Path(literal(node.args[0], env, builder))
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'resolve' and not node.args and not node.keywords:
        require(isinstance(node.func.value, ast.Call) and ast.dump(node.func.value) ==
                ast.dump(ast.parse('Path(__file__)', mode='eval').body), 'Unexpected resolved builder constant')
        return builder
    raise RuntimeError('Unsupported signed builder constant')


def builder_contract(raw, builder):
    tree, env = ast.parse(raw), {'PROJECT': PROJECT, '__file__': str(builder)}
    wanted = ('SDK_ROOT', 'SDK_INCLUDE_RELS', 'PROJECT_INCLUDE_DIRS', 'PROVIDER_REPORTS', 'OWNED',
              'TRANSLATION_UNITS', 'SYSTEM_LIBRARIES', 'ALLOWED_IMPORTS', 'expected_provider_status', 'common')
    for name in wanted:
        nodes = [n.value for n in ast.walk(tree) if isinstance(n, ast.Assign) and
                 any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
        require(len(nodes) == 1, 'Missing or ambiguous signed builder declaration: ' + name)
        env[name] = literal(nodes[0], env, builder)
    require(tuple(env['TRANSLATION_UNITS']) == TUS and all(flag in env['common'] for flag in ('/W4', '/WX', '/O2', '/MD')),
            'Wrong five-TU warning/optimization contract')
    return env


def parse_catalog(raw):
    arrays, order, index = {}, None, 0
    lines = raw.splitlines(keepends=True)
    while index < len(lines):
        line = lines[index];index += 1
        match = re.fullmatch(rb'static const char ([A-Za-z_][A-Za-z0-9_]*)\[\]=\n', line)
        if match:
            name = match[1].decode('ascii')
            require(name not in arrays and order is None, 'Duplicate or misplaced source array')
            value, previous = bytearray(), None
            while True:
                require(index < len(lines), 'Truncated source array')
                line = lines[index];index += 1
                final = line.endswith(b';\n')
                chunk = line[:-2] if final else line[:-1]
                require(re.fullmatch(rb'"(?:\\x[0-9a-f]{2}){0,64}"', chunk) and
                        (previous is None or previous == 64), 'Source array is not exact hex64 chunks')
                data = bytes.fromhex(chunk[1:-1].replace(b'\\x', b'').decode('ascii'))
                require(data or final and previous is None, 'Empty nonterminal source chunk')
                value.extend(data);previous = len(data)
                require(len(value) <= 32 * 1024 * 1024, 'Source script exceeds its size bound')
                if final:
                    break
            require(b'\0' not in value, 'NUL in source script')
            arrays[name] = bytes(value)
        elif line == b'static const Script scripts[]={\n':
            require(order is None, 'Repeated source registry')
            order = []
            while index < len(lines) and lines[index] != b'};\n':
                match = re.fullmatch(rb'\{"([A-Za-z_][A-Za-z0-9_]*)",\1,sizeof\(\1\)-1\},\n', lines[index])
                require(match, 'Malformed source registry row')
                name = match[1].decode('ascii')
                require(name in arrays and name not in order, 'Missing or repeated source registry symbol')
                order.append(name);index += 1
            require(index < len(lines), 'Truncated source registry')
            index += 1
    require(order and len(order) == len(arrays) == 67 and set(order) == set(arrays) and
            {'ZeroSisUiScene', 'GoodyHutPopup', 'GoodyHutRewardLayout', 'SharedFontMetrics'} <= set(order),
            'Source is not the exact 67-entry shared-font catalog')
    return arrays, order


class PE:
    """Pure file-backed PE32+ parser, adapted from the existing linked verifier."""
    def __init__(self, data):
        self.data = data
        require(len(data) >= 64 and data[:2] == b'MZ', 'Missing DOS header')
        offset = self.number(0x3c, '<I')
        require(data[offset:offset + 4] == b'PE\0\0' and self.number(offset + 4, '<H') == 0x8664, 'Not an AMD64 PE')
        count, size = self.number(offset + 6, '<H'), self.number(offset + 20, '<H')
        flags, optional = self.number(offset + 22, '<H'), offset + 24
        require(flags & 0x20 and not flags & 0x2000 and 0 < count <= 96, 'Not a large-address-aware executable')
        require(size >= 128 and self.number(optional, '<H') == 0x20b and
                self.number(optional + 108, '<I') >= 2, 'Not PE32+ with import directory')
        self.base, self.sections = self.number(optional + 24, '<Q'), []
        for index in range(count):
            at = optional + size + index * 40
            require(at + 40 <= len(data), 'Truncated PE section table')
            length, raw = self.number(at + 16, '<I'), self.number(at + 20, '<I')
            require(raw + length <= len(data), 'Truncated PE raw section')
            self.sections.append(dict(name=data[at:at + 8].split(b'\0', 1)[0].decode('ascii'),
                                      rva=self.number(at + 12, '<I'), raw=raw, size=length, flags=self.number(at + 36, '<I')))
        self.import_rva, self.import_size = struct.unpack_from('<II', data, optional + 120)

    def number(self, offset, fmt):
        require(0 <= offset <= len(self.data) - struct.calcsize(fmt), 'PE scalar outside file')
        return struct.unpack_from(fmt, self.data, offset)[0]

    def mapped(self, rva, size, readonly=False):
        rows = [row for row in self.sections if row['rva'] <= rva and rva - row['rva'] + size <= row['size']]
        require(len(rows) == 1, 'PE address lacks one file-backed section')
        row = rows[0]
        if readonly:
            require(row['flags'] & 0x40000000 and not row['flags'] & 0xa0000000, 'Catalog data is writable or executable')
        return row['raw'] + rva - row['rva'], row

    def occurrences(self, value):
        require(value, 'Empty byte search is forbidden')
        result = []
        for row in self.sections:
            if not row['flags'] & 0x40000000 or row['flags'] & 0xa0000000:
                continue
            end = row['raw'] + row['size'];at = self.data.find(value, row['raw'], end)
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
        require(self.import_rva and self.import_size >= 20, 'No PE import directory')
        names = []
        for index in range(min(1024, self.import_size // 20)):
            at, _ = self.mapped(self.import_rva + index * 20, 20)
            row = struct.unpack_from('<5I', self.data, at)
            if not any(row):
                return names
            names.append(self.cstring(row[3]).decode('ascii').casefold())
        raise RuntimeError('Unterminated PE import directory')

    def catalog(self, arrays, order):
        anchor = 'ZeroSisUiScene';candidates = set()
        require(arrays[anchor], 'Complete source scene must be a nonempty catalog anchor')
        for name_rva in self.occurrences(anchor.encode('ascii') + b'\0'):
            for data_rva in self.occurrences(arrays[anchor] + b'\0'):
                record = struct.pack('<QQQ', self.base + name_rva, self.base + data_rva, len(arrays[anchor]))
                candidates.update(rva - order.index(anchor) * 24 for rva in self.occurrences(record) if rva % 8 == 0)
        require(len(candidates) == 1, 'No unique actual name/data/size registration table')
        base = candidates.pop();at, section = self.mapped(base, 24 * len(order), True);proof = []
        for index, name in enumerate(order):
            name_va, data_va, size = struct.unpack_from('<QQQ', self.data, at + index * 24)
            require(name_va >= self.base and data_va >= self.base, 'Foreign catalog address')
            name_rva, data_rva = name_va - self.base, data_va - self.base
            self.mapped(name_rva, len(name) + 1, True)
            payload_at, payload_section = self.mapped(data_rva, size + 1, True)
            require(self.cstring(name_rva) == name.encode('ascii') and size == len(arrays[name]) and
                    self.data[payload_at:payload_at + size] == arrays[name] and self.data[payload_at + size] == 0,
                    'Actual PE registration differs from source bytes: ' + name)
            proof.append(dict(name=name, index=index, row_rva=base + index * 24, name_rva=name_rva,
                              payload_rva=data_rva, bytes=size, sha256=hashlib.sha256(arrays[name]).hexdigest(),
                              payload_section=payload_section['name']))
        return dict(table_rva=base, table_section=section['name'], stride=24, entry_count=len(order),
                    exact_payloads=proof, location_anchor='NONEMPTY_COMPLETE_SOURCE_SCENE_BYTES')


def coff(raw):
    require(len(raw) >= 20, 'Truncated COFF object')
    machine, count, _, symbols, symbol_count, optional, _ = struct.unpack_from('<HHIIIHH', raw)
    require(machine == 0x8664 and optional == 0 and 0 < count < 65535 and 20 + count * 40 <= len(raw),
            'Not an actual AMD64 COFF object with bounded sections')
    require(not symbol_count or symbols >= 20 + count * 40 and symbols + symbol_count * 18 <= len(raw), 'Truncated COFF symbols')
    sections = []
    for index in range(count):
        at = 20 + index * 40
        size, pointer, relocations, _, reloc_count, _, flags = struct.unpack_from('<IIIIHHI', raw, at + 16)
        require(not size or pointer >= 20 + count * 40 and pointer + size <= len(raw), 'Truncated COFF raw section')
        require(not reloc_count or relocations and relocations + reloc_count * 10 <= len(raw), 'Truncated COFF relocations')
        sections.append(dict(name=raw[at:at + 8].split(b'\0', 1)[0].decode('ascii'), bytes=size, flags=flags))
    return dict(machine_hex='0x8664', section_count=count, sections=sections)


def verify_compilation(inputs, build, run, scope, contract, build_id):
    root = PROJECT / 'Build/UiWindowHost' / build_id
    frozen = root / 'frozen'
    donor_root = PROJECT / 'Build/UiWindowHost' / scope['baseline_build_id'] / 'frozen'
    reuse = build['frozen_input_reuse']
    require(reuse['donor_build_id'] == scope['baseline_build_id'] and
            norm(reuse['donor_report_path']) == norm(scope['baseline_build']['path']) and
            reuse['donor_report_sha256'] == scope['baseline_build']['sha256'] and
            reuse['donor_content_and_metadata_preserved'] is True, 'Frozen donor lineage differs')

    def frozen_row(row):
        require(within(row['path'], frozen), 'Input escaped the new frozen root')
        inputs.sealed(row)
        original = inputs.ref(row.get('original_path', row.get('original_source')))
        require((original['bytes'], original['sha256']) == (row['bytes'], row['sha256']), 'Live/frozen input differs')
        require(identity(Path(original['path']).stat())[:2] != identity(Path(row['path']).stat())[:2], 'Frozen input aliases mutable original')
        if row.get('materialization') == 'hardlink':
            donor = row['reused_from_path']
            require(within(donor, donor_root) or within(donor, frozen), 'Hardlink donor escaped declared lineage')
            require(inputs.ref(donor)['sha256'] == row['sha256'] and
                    identity(Path(donor).stat())[:2] == identity(Path(row['path']).stat())[:2], 'Frozen hardlink identity differs')
        elif 'materialization' in row:
            require(row['materialization'] == 'copy' and 'reused_from_path' not in row, 'Unknown frozen materialization')

    rows = build['compiler_inputs']
    by_original, by_frozen = {}, {}
    roots = dict(project=PROJECT, sdk=contract['SDK_ROOT'])
    roots.update(('system_%02d' % index, Path(path)) for index, path in enumerate(build['system_include_roots']))
    for row in rows:
        original, target = norm(row['original_path']), norm(row['path'])
        require(original not in by_original and target not in by_frozen and
                row['root_name'] in roots and not Path(row['relative_path']).is_absolute() and '..' not in Path(row['relative_path']).parts and
                within(original, roots[row['root_name']]) and norm(row['original_path']) == norm(roots[row['root_name']] / row['relative_path']) and
                norm(row['path']) == norm(frozen / 'include_roots' / row['root_name'] / row['relative_path']), 'Duplicate or misplaced compiler input')
        frozen_row(row);by_original[original] = row;by_frozen[target] = row
    require(len(rows) == build['compiler_dependency_count'] and rows, 'Compiler closure count differs')
    require(build['compiler_dependency_live_hashes_after'] == {row['original_path']: row['sha256'] for row in rows}, 'Compiler post-build hash closure differs')
    require(build['source_hashes_before'] == build['source_hashes_after'] and
            set(build['source_hashes_before']) == set(contract['OWNED']), 'Owned builder input closure differs')
    for role, original in contract['OWNED'].items():
        sha = build['source_hashes_before'][role]
        require(inputs.ref(original)['sha256'] == sha and inputs.ref(frozen / 'project' / original.relative_to(PROJECT))['sha256'] == sha,
                'Owned source or initial frozen snapshot differs: ' + role)
    expected_sources = {norm(row['original_path']): row['path'] for row in rows if row['root_name'] == 'project' and
                        row['relative_path'].replace('\\', '/').casefold().startswith(('source/host/', 'source/presentation/'))}
    for original in contract['OWNED'].values():
        if original.parent.name.casefold() in ('host', 'presentation'):
            expected_sources.setdefault(norm(original), str(frozen / 'project' / original.relative_to(PROJECT)))
    require(len(build['sources']) == len(expected_sources) and
            {norm(row['original_source']) for row in build['sources']} == set(expected_sources), 'Host/presentation frozen source closure differs')
    for row in build['sources']:
        require(norm(row['path']) == norm(expected_sources[norm(row['original_source'])]) and
                norm(PROJECT / row['relative_path']) == norm(row['original_source']), 'Misplaced Host/presentation source snapshot')
        frozen_row(row)
    for row in build['build_tools']:
        frozen_row(row)
    require({row['role'] for row in build['build_tools']} == {'builder', 'host_builder'}, 'Build tool closure differs')

    provider_documents = {}
    require(set(build['provider_reports']) == set(contract['PROVIDER_REPORTS']), 'Provider report closure differs')
    for role, row in build['provider_reports'].items():
        frozen_row(row)
        require(norm(row['original_path']) == norm(contract['PROVIDER_REPORTS'][role]) and
                build['provider_report_hashes_after'][role] == row['sha256'], 'Provider source/post-build identity differs')
        doc = inputs.document(row['path'])
        require(doc['status'] == contract['expected_provider_status'][role], 'Unsuccessful provider: ' + role)
        provider_documents[role] = doc
    require(build['shared_lua_build'] == build['provider_reports']['shared_lua'], 'Shared Lua provider reference differs')
    for row in (provider_documents['database']['dll'], provider_documents['localization']['dll'], provider_documents['shared_lua']['lua_dll']):
        inputs.sealed(row)
    expected_libs = [provider_documents['database']['library'], provider_documents['localization']['library'],
                     provider_documents['shared_lua']['lua_library'], provider_documents['streams']['library'],
                     *provider_documents['temp_heap']['x64']['libraries']]
    require(len(build['provider_inputs']) == len(expected_libs), 'Provider library count differs')
    for index, (row, expected) in enumerate(zip(build['provider_inputs'], expected_libs)):
        frozen_row(row);inputs.sealed(expected)
        require(norm(row['original_path']) == norm(expected['path']) and row['sha256'] == expected['sha256'] and
                norm(row['path']) == norm(frozen / 'libraries' / ('%02d_' % index + Path(expected['path']).name)), 'Provider linker input differs')
    require(tuple(build['system_library_names']) == tuple(contract['SYSTEM_LIBRARIES']) and
            [row['name'] for row in build['system_libraries']] == list(contract['SYSTEM_LIBRARIES']), 'System library closure differs')
    for row in build['system_libraries']:
        frozen_row(row)
        require(norm(row['path']) == norm(frozen / 'libraries' / row['name']), 'Misplaced system library')
    require(build['libraries'] == build['provider_inputs'] + build['system_libraries'], 'Recorded linker library sequence differs')
    frozen_row(build['ui_assets'])

    actual = run['actual_objects']
    require(len(actual) == 10 and len({norm(row['object']['path']) for row in actual}) == 10, 'Not ten distinct actual compiler objects')
    object_rows = {(row['phase'], row['translation_unit']): row for row in actual}
    require(len(object_rows) == 10, 'Repeated compiler phase/TU object')
    dependencies, proofs, final_objects = {}, [], []
    for phase in PHASES:
        key = 'final_compilation' if phase == 'final' else phase
        translations = build[key]['translation_units']
        require([row['translation_unit'] for row in translations] == list(TUS), 'Wrong ordered five-TU compilation phase')
        dependencies[phase] = {}
        for index, row in enumerate(translations):
            role = row['translation_unit'];directory = root / phase / ('tu_%02d_%s' % (index, role))
            witness = object_rows[(phase, directory.name)]
            require(row['returncode'] == witness['returncode'] == 0, 'Actual compile returned nonzero')
            source = contract['OWNED'][role] if phase == 'dependency_discovery' else Path(by_original[norm(contract['OWNED'][role])]['path'])
            response = directory / (role + ('.discover.rsp' if phase == 'dependency_discovery' else '.compile.rsp'))
            dependency = directory / (role + '.sourceDependencies.json')
            inputs.sealed(row['response'], response);inputs.sealed(witness['response'], response)
            inputs.sealed(row['dependency_report'], dependency)
            raw = inputs.read(row['log']['path']);inputs.sealed(row['log'])
            require(not re.search(rb'\bwarning\s+C[0-9]+', raw, re.I), 'Compiler log contains a warning')
            common = ['/std:c++17' if role == 'terrain_renderer' and flag == '/std:c++14' else
                      '/source-charset:utf-8' if role == 'world_renderer' and flag == '/source-charset:windows-1252' else flag
                      for flag in contract['common']]
            sdk = [contract['SDK_ROOT'] / part for part in contract['SDK_INCLUDE_RELS']]
            project_includes = contract['PROJECT_INCLUDE_DIRS']
            system = []
            if phase == 'final':
                sdk = [frozen / 'include_roots/sdk' / part for part in contract['SDK_INCLUDE_RELS']]
                project_includes = [frozen / 'include_roots/project' / part.relative_to(PROJECT) for part in project_includes]
                system = [frozen / 'include_roots' / ('system_%02d' % number) for number, _ in enumerate(build['system_include_roots'])]
            expected = [*common, *(f'/external:I"{path}"' for path in sdk), *(f'/I"{path}"' for path in project_includes),
                        *(f'/I"{path}"' for path in system), '/c', f'"{source}"', f'/Fo"{(directory / "obj").as_posix()}/"',
                        f'/sourceDependencies "{dependency}"']
            require(inputs.read(response).decode('utf-8-sig').splitlines() == expected, 'Actual compiler response differs from the signed builder contract')
            data = inputs.document(dependency);data = data.get('Data', data)
            require(norm(data['Source']) == norm(source) and isinstance(data['Includes'], list), 'Wrong sourceDependencies translation unit')
            deps = {norm(path) for path in (data['Source'], *data['Includes'])}
            require(deps <= set(by_original if phase == 'dependency_discovery' else by_frozen), 'Compiler consumed an unsealed dependency')
            dependencies[phase][role] = deps
            path = directory / 'obj' / (contract['OWNED'][role].stem + '.obj')
            inputs.sealed(witness['object'], path)
            parsed = coff(inputs.read(path, 256 * 1024 * 1024))
            if phase == 'dependency_discovery':
                require([inputs.sealed(item) for item in row['objects']] == [inputs.sealed(witness['object'])],
                        'Discovery object receipt differs from actual witness')
            else:
                final_objects.append(witness['object'])
            proofs.append(dict(phase=phase, translation_unit=role, object=witness['object'], response=row['response'],
                               machine_hex=parsed['machine_hex'], section_count=parsed['section_count'], returncode=0))
    require(set.union(*dependencies['dependency_discovery'].values()) == set(by_original), 'Discovery union does not equal frozen compiler closure')
    for role in TUS:
        require({norm(by_original[path]['path']) for path in dependencies['dependency_discovery'][role]} == dependencies['final'][role],
                'Final compiler consumed a different exact dependency closure')
    consumers = {}
    for relative in (*scope['_source']['cpp_changed_headers'], GENERATED):
        original = norm(PROJECT / relative)
        require(original in by_original, 'Changed C++ input missing from compiler closure: ' + relative)
        roles = [role for role in TUS if original in dependencies['dependency_discovery'][role]]
        require(roles == ['host_main'], 'Changed C++ header has an unexpected consumer set')
        consumers[relative] = dict(frozen=by_original[original], consumers=roles)
    for phase, field in (('dependency_discovery', 'dependency_discovery_reports'), ('final', 'final_dependency_reports')):
        require(set(build[field]) == set(TUS) and all(build[field][row['translation_unit']] == row['dependency_report'] for row in
                build['final_compilation' if phase == 'final' else phase]['translation_units']), 'Dependency report map differs')
    require(build['response'] == build['final_compilation']['translation_units'][0]['response'] and
            build['dependency_report'] == build['final_compilation']['translation_units'][0]['dependency_report'], 'Primary host compile receipt differs')
    snapshot = run['link_snapshot']
    require(snapshot['returncode'] == 0 and snapshot['objects_before'] == snapshot['objects_after'] == final_objects,
            'Link-time five-object identities changed or differ from actual final compiles')
    response = root / 'final/link.rsp'
    inputs.sealed(snapshot['response'], response);inputs.sealed(build['link_response'], response)
    executable, map_path = root / 'final/ZeroSisHost_x64.exe', root / 'final/ZeroSisHost_x64.map'
    expected = [*(f'"{row["path"]}"' for row in final_objects), *(f'"{row["path"]}"' for row in build['libraries']),
                f'/OUT:"{executable}"', f'/MAP:"{map_path}"', '/INCREMENTAL:NO', '/MACHINE:X64', '/Brepro',
                '/WX', '/OPT:REF', '/OPT:ICF', '/SUBSYSTEM:CONSOLE']
    require(inputs.read(response).decode('utf-8-sig').splitlines() == expected, 'Actual link response differs from exact five-object/library contract')
    inputs.sealed(build['map'], map_path);inputs.sealed(build['executable'], executable)
    inputs.sealed(build['link_log'])
    require(not re.search(rb'\bwarning\s+LNK[0-9]+', inputs.read(build['link_log']['path']), re.I), 'Link log contains a warning')
    return dict(actual_coff_objects=proofs, exact_cpp_consumers=consumers, link_objects_before=final_objects,
                link_objects_after=snapshot['objects_after'], exact_link_response=build['link_response'],
                compiler_dependency_count=len(rows), frozen_input_reuse=reuse)


def verify(inputs, build_id):
    scope_path = STAGE / 'build_scope.json'
    scope_ref = inputs.ref(scope_path);scope = inputs.document(scope_path)
    require(scope['schema'] == 'zerosis.goody_hut.shared_font_link_scope.v1' and scope['compile_link_allowed'] is True and
            scope['retail_mod_test_hold_active'] is True and not any(scope[name] for name in
            ('host_gamecore_hwnd_execution_allowed', 'retail_user_state_or_game_process_access_allowed', 'default_promotion_allowed', 'full_engine_goal_complete')),
            'Wrong private compile/link scope')
    inputs.sealed(scope['build_wrapper'], STAGE / 'build_once.py')
    require(scope['build_wrapper']['sha256'] == WRAPPER_SHA, 'Actual wrapper differs from the reviewed witness code')
    inputs.sealed(scope['source_seal'], STAGE / 'source_seal.json')
    require(scope['source_seal']['sha256'] == SEAL_SHA, 'Current shared-font source approval differs')
    source = inputs.document(scope['source_seal']['path'])
    require(source['schema'] == 'zerosis.goody_hut.shared_font_source_seal.v1' and len(source['production_sources']) == 13 and
            len(source['new_assets_and_tests']) == 5 and source['generated_catalog_expected_count'] == 67 and
            source['cpp_changed_headers'] == ['Source/Host/UiPopupContext.h', 'Source/Host/InteractiveUiSession.h', 'Source/Host/InteractiveGameLoop.h'],
            'Source approval closure differs')
    for group in ('production_sources', 'new_assets_and_tests'):
        for relative, row in source[group].items():
            inputs.sealed(row, PROJECT / relative)
    for name in ('source_conformance', 'baseline_build', 'baseline_generated_header', 'pure_lua_provider',
                 'catalog_checker', 'storage_prebuild', 'frozen_preservation', 'catalog_parser_helper', 'script_loader', 'font_catalog_scope'):
        inputs.sealed(scope[name])
    for name in ('scene_addenda', 'original_goody_assets', 'original_pantheon_assets'):
        for row in scope[name].values():
            inputs.sealed(row)
    for name in ('build_tool_seals', 'source_backup_refs', 'font_original_inputs'):
        for row in scope[name]:
            inputs.sealed(row)
    conformance = inputs.document(scope['source_conformance']['path'])
    require(conformance['schema'] == 'zerosis.goody_hut.shared_font_source_conformance.v1' and
            conformance['status'] == 'PASS_SHARED_FONT_SOURCE_GENERATION_AND_COMPONENTS_CPP_NATIVE_PENDING' and
            conformance['source_seal'] == scope['source_seal'] and conformance['generation'] == source['generation_run'] and
            conformance['storage_prebuild'] == scope['storage_prebuild'] and conformance['source_inputs_unchanged'] is True and
            conformance['retail_mod_test_hold_active'] is True, 'Source conformance does not bind this approval and generation')
    inputs.sealed(source['generation_run'])
    generation = inputs.document(source['generation_run']['path'])
    require(generation['schema'] == 'zerosis.goody_hut.shared_font_generation.v1' and generation['status'] == 'PASS' and
            generation['returncode'] == 0 and generation['protected_inputs_unchanged'] is True and
            generation['actual_preparer_subprocess_result_unmodified'] is True, 'Source generation evidence did not pass')
    require(source['frozen_build'] == scope['baseline_build_id'], 'Source approval and frozen donor differ')
    baseline = inputs.document(scope['baseline_build']['path'])
    require(baseline['build_id'] == scope['baseline_build_id'] and baseline['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT', 'Invalid declared frozen donor')
    run_ref = inputs.ref(STAGE / 'build_run.json');run = inputs.document(run_ref['path'])
    require(run['schema'] == 'zerosis.goody_hut.actual_build_run.v1' and run['status'] == 'PASS' and run['scope'] == scope_ref and
            run['result'] == 0 and run['error'] is None and run['new_build_ids'] == run['new_evidence_ids'] == [build_id] and
            run['protected_unchanged'] is True and run['actual_builder_subprocess_results_unmodified'] is True and not run['forbidden_access_attempts'] and
            run['game_process_queries'] == 0 and all(run[name] is False for name in ('host_gamecore_hwnd_executed',
            'retail_user_state_or_game_processes_accessed', 'default_promoted', 'full_engine_goal_complete')), 'Actual single build witness did not pass')
    require(build_id not in scope['build_identifiers_before'] and build_id not in scope['evidence_identifiers_before'], 'Attested build is not the new allocated candidate')
    require(run['catalog_state']['preparations'] == run['catalog_state']['catalog_preflights'] == 1 and
            run['catalog_state']['catalog_verified'] is True, 'Build did not follow one real preparer and catalog preflight')
    catalog_ref = inputs.ref(STAGE / 'catalog.json');catalog = inputs.document(catalog_ref['path'])
    require(catalog['status'] == scope['expected_catalog_status'] == CATALOG_PASS and catalog['inputs_unchanged'] is True and
            catalog['catalog_count'] == catalog['parsed_count'] == scope['expected_catalog_count'] == 67 and catalog['failed_count'] == 0 and
            all(catalog[name] is False for name in ('scripts_executed', 'lua_openlibs_called', 'lua_pcall_called', 'host_executed',
            'gamecore_loaded', 'hwnd_created', 'retail_user_state_accessed', 'default_promoted', 'full_engine_goal_complete')), 'Actual 67-script preflight did not pass privately')
    require(catalog['scope'] == scope['font_catalog_scope'] and catalog['inputs_before'] == catalog['inputs_after'], 'Catalog input lineage differs')
    require(catalog['additional_processes_started'] == 0 and catalog['guard']['explicit_lua_provider_loads'] == 1 and
            not any(value for name, value in catalog['guard'].items() if name.startswith('blocked_')) and
            set(catalog['resolved_parser_functions']) == {'luaL_newstate', 'luaL_loadbuffer', 'lua_tolstring', 'lua_close'},
            'Actual catalog parser-only guard differs')
    for row in catalog['inputs_before']:
        inputs.sealed(row)
    catalog_scope = inputs.document(scope['font_catalog_scope']['path'])
    require(catalog_scope['source_seal'] == scope['source_seal'] and catalog_scope['generation_run'] == source['generation_run'] and
            norm(scope['generated_header']['path']) == norm(PROJECT / GENERATED), 'Catalog source/generated lineage differs')
    header_ref = inputs.sealed(catalog_scope['generated_header'], PROJECT / GENERATED)
    require(catalog['generated_header'] == header_ref == run['catalog_state']['checked_header'], 'Preflight and actual generated header differ')
    arrays, order = parse_catalog(inputs.read(PROJECT / GENERATED, 128 * 1024 * 1024))
    require([row['name'] for row in catalog['scripts']] == order, 'Preflight script order differs from source registry')
    for row in catalog['scripts']:
        raw = arrays[row['name']];code = raw[3:] if raw.startswith(b'\xef\xbb\xbf') else raw
        require(row['lua_status'] == 0 and row['status'] == 'PASS_PARSE_ONLY' and row['raw_bytes'] == len(raw) and
                row['raw_sha256'] == hashlib.sha256(raw).hexdigest() and row['parse_input_bytes'] == len(code) and
                row['parse_input_sha256'] == hashlib.sha256(code).hexdigest() and row['utf8_bom_removed_for_parse'] == (raw != code),
                'Catalog parse witness differs from exact source script')
    build_ref = inputs.ref(PROJECT / 'evidence/ui_window_host' / build_id / 'build_result.json')
    build = inputs.document(build_ref['path'])
    require(build['schema'] == 'zerosis.ui_window_host_build.v1' and build['status'] == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
            build['build_id'] == build_id and build['error'] is None and build['source_inputs_unchanged'] is True and
            build['provider_inputs_unchanged'] is True and all(build[name] is False for name in
            ('gamecore_loaded', 'sdk_linked', 'stage_updated', 'mods_updated', 'host_runtime_executed')), 'Actual private build did not complete')
    preparation = build['ui_asset_preparation']
    require(preparation['returncode'] == 0 and preparation['command'] ==
            [preparation['command'][0], '-B', '-X', 'utf8', str(PROJECT / 'tools/prepare_ui_popup_assets.py')], 'Actual preparer command/result differs')
    inputs.sealed(preparation['stdout']);inputs.sealed(preparation['stderr'])
    for name in ('compiler', 'linker', 'dumpbin'):
        inputs.sealed(build[name]);inputs.sealed(baseline[name])
        require(build[name] == baseline[name], 'Actual toolchain differs from declared frozen donor')
    processes = run['processes']
    require(len(processes) == 15, 'Unexpected actual builder child count')
    expected_processes = [(build['ui_asset_preparation']['command'][0], PROJECT),
                          (build['ui_asset_preparation']['command'][0], PROJECT),
                          ('cmd.exe', PROJECT / 'Build/UiWindowHost' / build_id)]
    for phase in PHASES:
        expected_processes.extend((build['compiler']['path'], PROJECT / 'Build/UiWindowHost' / build_id / phase / ('tu_%02d_%s' % (index, role)))
                                  for index, role in enumerate(TUS))
    expected_processes.extend((build[name]['path'], PROJECT / 'Build/UiWindowHost' / build_id / 'final') for name in ('linker', 'dumpbin'))
    require([(norm(row['executable']), norm(row['cwd'])) for row in processes] ==
            [(norm(executable), norm(cwd)) for executable, cwd in expected_processes], 'Actual compiler/process path sequence differs')
    require(run['pure_lua_dll_loads'] == [scope['pure_lua_provider']['path']], 'Actual builder loaded an unexpected provider')
    contract = builder_contract(inputs.read(PROJECT / 'tools/build_ui_window_host.py'), PROJECT / 'tools/build_ui_window_host.py')
    scope['_source'] = source
    compilation = verify_compilation(inputs, build, run, scope, contract, build_id)
    require(build['system_include_roots'] == baseline['system_include_roots'], 'System include environment differs from declared donor')
    compiled_header = compilation['exact_cpp_consumers'][GENERATED]['frozen']
    require(run['checked_compiler_header'] == {key: compiled_header[key] for key in ('path', 'bytes', 'sha256')} and
            (compiled_header['sha256'], compiled_header['bytes']) == (header_ref['sha256'], header_ref['bytes']), 'Actual compiler did not consume the parse-checked header')
    pe = PE(inputs.read(build['executable']['path'], 256 * 1024 * 1024))
    imports = pe.imports()
    require(imports and len(imports) == len(set(imports)) and set(imports) == {name.casefold() for name in build['imports']['dependencies']} and
            'zerosislua51_x64.dll' in imports and all(name in contract['ALLOWED_IMPORTS'] or name.startswith('api-ms-win-crt-') for name in imports),
            'Actual PE import table differs from allowed component providers')
    inputs.sealed(build['imports']['log'])
    exact = pe.catalog(arrays, order)
    return dict(scope=scope_ref, source_seal=scope['source_seal'], actual_build_run=run_ref, actual_catalog=catalog_ref,
                build_result=build_ref, generated_header=header_ref, compilation=compilation, executable=inputs.sealed(build['executable']),
                pe=dict(machine_hex='0x8664', format='PE32+', large_address_aware=True, is_dll=False,
                        section_count=len(pe.sections), imports=imports), catalog=exact,
                approved_production_sources=13, approved_assets_and_tests=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-id', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args();output = args.output.absolute()
    require(not sys.flags.optimize and re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.build_id), 'Invalid unoptimized build attestation request')
    require(STAGE == PROJECT / 'evidence/goody_hut/shared_fonts' and norm(output.parent) == norm(STAGE) and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\.json', output.name) and not os.path.lexists(output),
            'Output must be one fresh JSON directly below the owned shared-font stage')
    require(output.name not in ('build_scope.json', 'source_seal.json', 'build_run.json', 'catalog.json'), 'Output conflicts with an attestation input')
    # Warm the codec before exact input-open enforcement; no target module is imported.
    b'x'.decode('utf-8-sig');b'x'.decode('ascii')
    reads, denied = install_guard(output);inputs = Inputs(reads)
    result = dict(schema='zerosis.goody_hut.shared_font_linked_pe_attestation.v1', status='FAIL', build_id=args.build_id,
                  utc=datetime.now(timezone.utc).isoformat(), verifier=inputs.ref(Path(__file__).absolute()),
                  candidate_native_code_loaded_or_executed=False, host_gamecore_hwnd_executed=False, game_process_queries=0,
                  retail_user_state_accessed=False, default_promoted=False, retail_mod_test_hold_active=True,
                  native_feature_behavior_verified=False, full_engine_goal_complete=False)
    code = 1
    try:
        result.update(verify(inputs, args.build_id));inputs.stable()
        require(not denied, 'A forbidden operation was attempted')
        result.update(status='PASS_READONLY_LINKED_PE_67_EXACT_PAYLOADS_NATIVE_PENDING', inputs_unchanged=True,
                      verified_input_count=len(inputs.rows));code = 0
    except Exception as error:
        result.update(error=type(error).__name__ + ': ' + str(error), inputs_unchanged=False)
    result['forbidden_access_attempts'] = denied
    encoded = json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    require(len(encoded.encode('utf-8')) <= 256 * 1024, 'Attestation receipt exceeds its bounded size')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(encoded);stream.flush();os.fsync(stream.fileno())
    print(json.dumps(dict(status=result['status'], build_id=args.build_id, output=str(output),
                          catalog_count=result.get('catalog', {}).get('entry_count', 0), error=result.get('error')), ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
