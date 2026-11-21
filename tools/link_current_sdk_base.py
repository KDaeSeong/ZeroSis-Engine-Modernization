"""Link current, authenticated AMD64 SDK objects; never load the resulting DLL.

This is a base-SDK link component. It uses no SaveRestore, shared-Lua or
FoundValue object overlay and does not update a Host, runtime or retail tree.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
from datetime import datetime, timezone

sys.dont_write_bytecode = True

PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / 'evidence/sdk_current'
OUT = PROJECT / 'Build/SDKIncremental/x64/base_link'
OBJECT_DIR = OUT.parent / 'obj'
PREBUILD = STAGE / 'prebuild.json'
LATEST = PROJECT / 'evidence/sdk_incremental/x64/latest.json'
STATE = OUT.parent / 'state.json'
ANALYSIS = PROJECT / 'evidence/sdk_x64/link_analysis.json'
DEFINITION = PROJECT / 'Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvGameCoreDLL.def'
VS = Path(r'C:\Program Files\Microsoft Visual Studio\2022\Community')
KITS = Path(r'C:\Program Files (x86)\Windows Kits')
COMPILER = VS / 'VC/Tools/MSVC/14.44.35207/bin/Hostx64/x64/cl.exe'
LINKER = COMPILER.with_name('link.exe')
CMD = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32/cmd.exe'
EXPORTS = {'DllGetGameContext', 'ZeroSisShutdownGameCore', 'ZeroSisGetBootstrapError'}
PROVIDER_NAMES = ('Lua51', 'Streams', 'Serialization', 'Foundation', 'TempHeap', 'AutoArchive',
                  'Database', 'FLua', 'Strings', 'Localization', 'WorldBuilderTypes',
                  'WorldBuilderModData', 'WorldBuilderMapBridge', 'FileSystem', 'Logging', 'Debug')
PLATFORM = ('kernel32.lib', 'user32.lib', 'gdi32.lib', 'winspool.lib', 'comdlg32.lib',
            'advapi32.lib', 'shell32.lib', 'ole32.lib', 'oleaut32.lib', 'uuid.lib',
            'odbc32.lib', 'odbccp32.lib', 'winmm.lib', 'dbghelp.lib')
PINS = {
    PREBUILD: 'd647c50a442aaa4594d5fc34409b54985c057879798dffbd9143a37f7ccfe39e',
    ANALYSIS: 'e3c0a96e62bb643d37cd6f1d083fe4ca4faf272056e8f390ef4067f62824eea0',
    DEFINITION: 'a43385eb224d8f1938289a997252aa0aad4561a1aadedd656d606412d24eb5c7',
    COMPILER: '8a547dfca2d7df1b6be1e2d212132c1b3b5a661caf5b2ecce481e21b3c1860a6',
    LINKER: '4408c812a3f5e68cba935b8550a90cfc932ec7242a9c39efcb5c0945a6006c9a',
    PROJECT / 'tools/native_build.py': 'c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21',
    PROJECT / 'tools/collect_baseline.py': '7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187',
    STAGE / 'compile_result.json': 'c59dcd8f844c347a0e0281f23ec456f4b677868332c469c6aa655315bd3ffd0e',
    STAGE / 'validation_pch_retirement.json': 'bf7e697d94befe0ecf5bec9c309951df27c27bc5397bf377070ca4aa032f41d0',
}
INPUTS: dict[str, dict] = {}
COFF: dict[str, dict] = {}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def within(path, root):
    return key(path) == key(root) or key(path).startswith(key(root) + os.sep)


def no_reparse(path):
    path = Path(path)
    for part in (path, *path.parents):
        if part.exists():
            require(not part.lstat().st_file_attributes & 0x400, 'Reparse path forbidden: ' + str(part))


def input_path(path):
    path = Path(path)
    allowed = (PROJECT, VS, KITS, Path(r'C:\Windows\System32'), Path(r'C:\Windows\Microsoft.NET'))
    require(path.is_absolute() and (any(within(path, root) for root in allowed) or
            key(path) == key(Path(r'C:\Windows\Globalization\Sorting\SortDefault.nls'))),
            'Input escaped copied source/toolchain roots: ' + str(path))
    no_reparse(path)
    return path


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(block)
    return result.hexdigest()


def artifact(path):
    path = Path(path)
    no_reparse(path)
    before = path.stat()
    require(path.is_file(), 'Required file missing: ' + str(path))
    result = {'path': str(path), 'bytes': before.st_size, 'sha256': digest(path)}
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            'Input changed while hashing: ' + str(path))
    return result


def pin(row):
    require(isinstance(row, dict) and isinstance(row.get('path'), str) and
            re.fullmatch('[0-9a-fA-F]{64}', row.get('sha256', '')),
            'Expected path/sha256 artifact')
    path = input_path(row['path'])
    actual = artifact(path)
    require(actual['sha256'] == row['sha256'].lower() and
            ('bytes' not in row or actual['bytes'] == row['bytes']),
            'Artifact identity differs: ' + str(path))
    old = INPUTS.setdefault(key(path), actual)
    require(old['sha256'] == actual['sha256'] and old['bytes'] == actual['bytes'],
            'Two input identities for one normalized path: ' + str(path))
    return old


def capture(path):
    return pin(artifact(input_path(path)))


def read_json(path, expected=None):
    row = pin({'path': str(path), 'sha256': expected}) if expected else capture(path)
    result = json.loads(Path(row['path']).read_text(encoding='utf-8-sig'))
    require(digest(path) == row['sha256'], 'JSON changed while reading: ' + str(path))
    return result


def verify_inputs():
    for row in list(INPUTS.values()):
        require(artifact(row['path']) == row, 'Sealed input changed: ' + row['path'])


def defaults(payload):
    return [next(x for x in pair if x).decode('ascii') for pair in
            re.findall(rb'(?i)(?:^|\s)[/-]DEFAULTLIB:(?:"([^"]+)"|([^\s]+))', payload)]


def neutral_weak_alias(payload):
    """Validate the observed MSVC CRT architecture-neutral weak-alias object.

    winnt.h defines MACHINE_UNKNOWN=0, WEAK_EXTERNAL=105 and SEARCH_ALIAS=3.
    These objects have no code/data definition or relocation: only discardable
    CodeView information, two absolute compiler metadata symbols, an undefined
    external, and its weak alias. Machine zero alone is never sufficient.
    """
    machine, sections, _, symbols, count, optional, characteristics = struct.unpack_from('<HHIIIHH', payload)
    require((machine, sections, count, optional, characteristics) == (0, 1, 5, 0, 0),
            'Unsupported machine-zero COFF header')
    require(len(payload) >= 60 and payload[20:28] == b'.debug$S', 'Neutral alias lacks its sole debug section')
    virtual_size, address, size, pointer, relocations, lines, relocation_count, line_count, flags = \
        struct.unpack_from('<IIIIIIHHI', payload, 28)
    require((virtual_size, address, pointer, relocations, lines, relocation_count, line_count, flags) ==
            (0, 0, 60, 0, 0, 0, 0, 0x42100040) and size >= 4 and
            symbols == pointer + size and payload[pointer:pointer + 4] == b'\x04\0\0\0',
            'Machine-zero object contains unsupported allocatable data/relocations')
    strings = symbols + 18 * count
    require(strings + 4 <= len(payload), 'Truncated neutral alias symbols')
    string_bytes = struct.unpack_from('<I', payload, strings)[0]
    require(string_bytes >= 4 and strings + string_bytes == len(payload), 'Invalid neutral alias string table')

    def symbol(index):
        offset = symbols + 18 * index
        raw = payload[offset:offset + 18]
        zero, string_offset = struct.unpack_from('<II', raw)
        if zero == 0:
            require(4 <= string_offset < string_bytes, 'Invalid neutral alias symbol name')
            end = payload.find(b'\0', strings + string_offset, strings + string_bytes)
            require(end >= 0, 'Unterminated neutral alias symbol name')
            name = payload[strings + string_offset:end]
        else:
            name = raw[:8].split(b'\0', 1)[0]
        require(name and all(32 <= value < 127 for value in name), 'Non-ASCII/empty neutral alias symbol')
        return name, struct.unpack_from('<IhHBB', raw, 8)

    for index, expected in enumerate((b'@comp.id', b'@feat.00')):
        name, (_, section, kind, storage, auxiliary) = symbol(index)
        require(name == expected and (section, kind, storage, auxiliary) == (-1, 0, 3, 0),
                'Neutral alias compiler metadata differs')
    target, target_fields = symbol(2)
    alias, alias_fields = symbol(3)
    require(target_fields == (0, 0, 0, 2, 0) and alias_fields == (0, 0, 0, 105, 1) and target != alias and
            payload[symbols + 72:symbols + 90] == struct.pack('<II', 2, 3) + bytes(10),
            'Neutral alias is not the observed undefined-target weak SEARCH_ALIAS record')


def coff_member(payload):
    require(len(payload) >= 20, 'Truncated COFF member')
    if payload[:4] == b'\x00\x00\xff\xff':
        machine = struct.unpack_from('<H', payload, 6)[0]
        require(machine == 0x8664, 'Non-AMD64 import/bigobj member: ' + hex(machine))
        if struct.unpack_from('<H', payload, 4)[0] < 2:
            return machine, []  # Short import-object header; no section table.
        require(len(payload) >= 56, 'Truncated bigobj header')
        sections, start = struct.unpack_from('<I', payload, 44)[0], 56
    else:
        machine, sections = struct.unpack_from('<HH', payload)
        start = 20 + struct.unpack_from('<H', payload, 16)[0]
        if machine == 0:
            neutral_weak_alias(payload)
            return machine, []
    require(machine == 0x8664, 'Non-AMD64 COFF member: ' + hex(machine))
    require(0 < sections <= 100000 and start + 40 * sections <= len(payload), 'Invalid COFF sections')
    libraries = []
    for offset in range(start, start + 40 * sections, 40):
        if payload[offset:offset + 8].rstrip(b'\0') == b'.drectve':
            size, pointer = struct.unpack_from('<II', payload, offset + 16)
            require(pointer + size <= len(payload), 'Truncated COFF directives')
            libraries.extend(defaults(payload[pointer:pointer + size]))
    return machine, libraries


def inspect_coff(path):
    path = Path(path)
    capture(path)
    if key(path) in COFF:
        return COFF[key(path)]
    data = path.read_bytes()
    machines, libraries, members, metadata, neutral = set(), [], 0, 0, 0
    if data.startswith(b'!<arch>\n'):
        position = 8
        while position < len(data):
            require(position + 60 <= len(data), 'Truncated archive header: ' + str(path))
            header = data[position:position + 60]
            require(header[58:60] == b'`\n', 'Invalid archive trailer: ' + str(path))
            size = int(header[48:58].decode('ascii').strip())
            name = header[:16].decode('ascii').strip()
            position += 60
            require(size >= 0 and position + size <= len(data), 'Truncated archive member: ' + str(path))
            payload = data[position:position + size]
            if name in ('/', '//', '/SYM64/'):
                metadata += 1
            else:
                machine, requested = coff_member(payload)
                if machine == 0:
                    require(key(path) in {key(COMPILER.parents[3] / 'lib/x64' / name)
                                          for name in ('msvcrt.lib', 'oldnames.lib')},
                            'Neutral alias appeared outside the two observed MSVC CRT archives')
                    neutral += 1
                machines.add(machine)
                libraries.extend(requested)
                members += 1
            position += size + (size & 1)
        require(position == len(data) and members > 0, 'Invalid/empty COFF archive: ' + str(path))
    else:
        machine, libraries = coff_member(data)
        require(machine == 0x8664, 'Standalone SDK/output object is not AMD64')
        machines.add(machine)
        members = 1
    require(machines and machines <= {0, 0x8664} and (0 not in machines or neutral > 0),
            'Archive contains an unsupported code-machine member: ' + str(path))
    row = {'path': str(path), 'machine': '0x8664' if 0x8664 in machines else 'neutral_weak_alias_only',
           'observed_machines': [hex(value) for value in sorted(machines)], 'coff_members': members,
           'amd64_members': members - neutral, 'neutral_weak_alias_members': neutral,
           'archive_metadata_members': metadata, 'default_libraries': sorted(set(libraries), key=str.casefold)}
    COFF[key(path)] = row
    return row


def inspect_pe(path):
    """Read only PE bytes, including imports and exports; no Windows loader API."""
    data = Path(path).read_bytes()
    require(len(data) >= 64 and data[:2] == b'MZ', 'Missing PE DOS header')
    nt = struct.unpack_from('<I', data, 60)[0]
    require(nt + 24 <= len(data) and data[nt:nt + 4] == b'PE\0\0', 'Missing PE signature')
    machine, count, _, _, _, optional_size, characteristics = struct.unpack_from('<HHIIIHH', data, nt + 4)
    optional = nt + 24
    require(machine == 0x8664 and characteristics & 0x2000 and characteristics & 0x20,
            'Expected AMD64 DLL with large-address awareness')
    require(optional_size >= 240 and optional + optional_size + count * 40 <= len(data) and
            struct.unpack_from('<H', data, optional)[0] == 0x20b, 'Expected complete PE32+ header')
    dll_characteristics = struct.unpack_from('<H', data, optional + 70)[0]
    image_base = struct.unpack_from('<Q', data, optional + 24)[0]
    header_bytes = struct.unpack_from('<I', data, optional + 60)[0]
    directories = struct.unpack_from('<I', data, optional + 108)[0]
    require(0 < count <= 96 and 14 <= directories <= (optional_size - 112) // 8, 'Invalid PE table dimensions')
    sections = []
    for offset in range(optional + optional_size, optional + optional_size + count * 40, 40):
        virtual_size, rva, raw_size, raw = struct.unpack_from('<IIII', data, offset + 8)
        flags = struct.unpack_from('<I', data, offset + 36)[0]
        require(raw + raw_size <= len(data) and not (flags & 0x20000000 and flags & 0x80000000),
                'Invalid or writable/executable PE section')
        sections.append((rva, virtual_size, raw, raw_size, flags))

    def at(rva, size):
        if rva < header_bytes and rva + size <= min(header_bytes, len(data)):
            return rva
        for first, _, raw, raw_size, _ in sections:
            if first <= rva and rva + size <= first + raw_size:
                return raw + rva - first
        raise RuntimeError('Unmapped PE file-backed RVA ' + hex(rva))

    def string(rva):
        output = bytearray()
        for index in range(4096):
            value = data[at(rva + index, 1)]
            if value == 0:
                return output.decode('ascii')
            output.append(value)
        raise RuntimeError('Unterminated PE string')

    def directory(index):
        return struct.unpack_from('<II', data, optional + 112 + 8 * index)

    export_rva, export_size = directory(0)
    export = at(export_rva, 40)
    functions, names, address_table, name_table, ordinal_table = struct.unpack_from('<IIIII', data, export + 20)
    require(functions == names == 3, 'Base SDK must expose exactly three named functions')
    exports = {}
    for index in range(names):
        name = string(struct.unpack_from('<I', data, at(name_table + 4 * index, 4))[0])
        ordinal = struct.unpack_from('<H', data, at(ordinal_table + 2 * index, 2))[0]
        require(ordinal < functions and name not in exports, 'Invalid duplicate export/ordinal')
        target = struct.unpack_from('<I', data, at(address_table + 4 * ordinal, 4))[0]
        require(target and not export_rva <= target < export_rva + export_size and
                any(first <= target < first + max(size, raw_size) and flags & 0x20000000
                    for first, size, _, raw_size, flags in sections), 'Export is forwarded or not executable')
        exports[name] = target
    require(set(exports) == EXPORTS, 'Unexpected base SDK exports')
    import_rva, import_size = directory(1)
    imports = {}
    require(import_rva and import_size >= 20, 'Missing import table')
    for index in range(min(import_size // 20, 4096)):
        descriptor = struct.unpack_from('<IIIII', data, at(import_rva + 20 * index, 20))
        if not any(descriptor):
            break
        lookup, _, _, name_rva, first_thunk = descriptor
        name = string(name_rva).lower()
        require(re.fullmatch(r'[a-z0-9_.-]+\.dll', name) and name not in imports, 'Invalid import DLL name')
        symbols = []
        for symbol_index in range(100000):
            thunk = struct.unpack_from('<Q', data, at((lookup or first_thunk) + symbol_index * 8, 8))[0]
            if not thunk:
                break
            symbols.append('#' + str(thunk & 0xffff) if thunk & (1 << 63) else string(thunk + 2))
        else:
            raise RuntimeError('Unterminated import thunks')
        imports[name] = symbols
    else:
        raise RuntimeError('Unterminated import descriptors')
    require(directory(13) == (0, 0), 'Unexpected delay imports')
    return {'machine': '0x8664', 'pe_format': 'PE32+', 'is_dll': True, 'image_base': image_base,
            'large_address_aware': True, 'dynamic_base': bool(dll_characteristics & 0x40),
            'nx_compatible': bool(dll_characteristics & 0x100), 'section_count': count,
            'exports': exports, 'imports': imports}


def verbose_library_searches(output):
    """Recognize only the observed English/Korean complete search-line forms."""
    events = []
    for line in output.splitlines():
        english = re.fullmatch(r'\s*Searching\s+(.+?\.lib):?\s*', line, re.I)
        korean = re.fullmatch(r'\s*(.+?\.lib)\s+검색 중:\s*', line, re.I)
        match = english or korean
        if match:
            events.append({'path': str(Path(match[1].strip().strip('"'))),
                           'locale': 'en' if english else 'ko'})
    return events


def map_archive_selection(map_text, sealed_coff, sealed_inputs, provider_keys, platform_keys, searched_keys):
    """Prove final archive/member selections by unique sealed library stems.

    Link-map owner labels and symbol rows are independent of UI language.
    This proves final owner/member labels, not every transient extraction.
    Repeated archive entries with identical member names are not distinguishable
    in this map representation and are not counted as separate physical entries.
    """
    owners = {}
    for owner, member in re.findall(
            r'(?im)^\s*[0-9a-f]{4}:[0-9a-f]{8}\s+\S+\s+[0-9a-f]{16}\s+(?:[fi]\s+){0,2}([^:\s]+):([^\s]+)\s*$',
            map_text):
        owners.setdefault(owner, set()).add(member)
    require(owners, 'Missing final archive/member owners in link map')
    selected, groups = {}, []
    for owner, members in sorted(owners.items()):
        candidates = [row for row in sealed_coff.values()
                      if Path(row['path']).suffix.lower() == '.lib' and
                      owner.lower() in (Path(row['path']).stem.lower(), Path(row['path']).name.lower())]
        require(len(candidates) == 1, 'Map archive owner is not a unique sealed library: ' + owner)
        library_key = key(candidates[0]['path'])
        require(library_key in searched_keys and library_key in sealed_inputs,
                'Map-selected library lacks sealed actual search evidence: ' + owner)
        category = 'provider' if library_key in provider_keys else \
                   'explicit_platform' if library_key in platform_keys else 'implicit_default_or_crt'
        row = selected.setdefault(library_key, {'library': sealed_inputs[library_key], 'members': set(),
            'map_owner_labels': [], 'category': category, 'evidence_source': 'link_map_section_owner_member'})
        row['members'].update(members)
        row['map_owner_labels'].append(owner)
        groups.append({'map_owner': owner, 'library': sealed_inputs[library_key], 'member_count': len(members),
                       'category': category, 'evidence_source': 'link_map_section_owner_member'})
    for row in selected.values():
        row['members'] = sorted(row['members'])
    return list(selected.values()), groups


def output_json(path, data):
    Path(path).write_text(json.dumps(data, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main():
    require(os.name == 'nt', 'Windows toolchain only')
    require(not OUT.exists(), 'Inspect existing base_link output before any retry')
    for path, expected in PINS.items():
        pin({'path': str(path), 'sha256': expected})
    capture(Path(__file__).resolve())
    prebuild = read_json(PREBUILD)
    require(isinstance(prebuild.get('builder_after'), dict), 'prebuild.builder_after must be an artifact')
    builder = pin(prebuild['builder_after'])
    allowed_stage = {key(PREBUILD), key(STAGE / 'compile_result.json'), key(STAGE / 'validation_pch_retirement.json')}
    for backup in prebuild['backups']:
        row = pin(backup['compressed'])
        require(within(row['path'], STAGE), 'Backup escaped current stage')
        allowed_stage.add(key(row['path']))
    for path in STAGE.iterdir():
        require(path.is_file() and key(path) in allowed_stage, 'Unknown/failed staged artifact: ' + str(path))
    for row in prebuild['protected']:
        pin(row)
    report = read_json(LATEST)
    require(report['status'] == 'SDK_INCREMENTAL_COMPILE_PASS' and report['exit_code'] == 0 and
            report['translation_units_expected'] == 161 and report['inputs_unchanged'] is True and
            report['linked'] is False and report['deployed'] is False and report['game_launched'] is False and
            not report['unique_error_lines'] and not report['numeric_warning_lines'], 'Current full SDK compile is not accepted')
    require('/p:CL_MPCount=1' in report['command'] and '/p:Platform=x64' in report['command'] and
            '/t:ClCompile' in report['command'], 'Unexpected current compile command scope')
    require(key(report['builder']['path']) == key(builder['path']) and
            report['builder']['sha256'] == builder['sha256'], 'Compile builder differs from authenticated prebuild')
    pin(report['builder']); pin(report['project']); pin(report['log'])
    run_report = Path(report['log']['path']).parent / 'build_result.json'
    require(read_json(run_report) == report, 'Latest pointer differs from immutable compile report')
    state = read_json(STATE)
    require(len(state['outputs']) == 162 and len(report['objects']) == 161, 'Expected 161 objects and one PCH')
    object_rows = {}
    for row in report['objects']:
        require(Path(row['path']).parent == OBJECT_DIR and Path(row['path']).suffix.lower() == '.obj' and
                row['machine'].lower() == '0x8664' and row['architecture'] == 'x64', 'Unexpected current SDK object')
        actual = pin(row)
        require(Path(row['path']).stem.casefold() not in object_rows, 'Duplicate current object stem')
        object_rows[Path(row['path']).stem.casefold()] = actual
        inspect_coff(row['path'])
    seen_outputs = set()
    for row in state['outputs']:
        require(Path(row['path']).parent == OBJECT_DIR and key(row['path']) not in seen_outputs, 'Unexpected/duplicate state output')
        seen_outputs.add(key(row['path'])); pin(row)
    require(seen_outputs == {key(row['path']) for row in object_rows.values()} |
            {key(OBJECT_DIR / 'GameCore_x64.pch')}, 'Compile state output set differs')
    for row in state['inputs'].values():
        pin(row)
    manifest = read_json(PROJECT / 'evidence/sdk_x64/port_manifest.json')
    for row in manifest:
        require(within(row['port'], PROJECT / 'Source/SDK_BNW_x64'), 'Port manifest escaped copied SDK')
        pin({'path': row['port'], 'sha256': row['port_sha256']})
    capture(PROJECT / 'Source/Porting/sdk_x64_patches.json')
    for path in (PROJECT / 'Source/Porting').rglob('*'):
        if path.is_file() and path.suffix.lower() in ('.h', '.hpp', '.inl'):
            capture(path)
    analysis = read_json(ANALYSIS)
    require(analysis['status'] == 'X64_LINK_PROBE_SUCCEEDED_UNTESTED' and analysis['link_exit_code'] == 0 and
            tuple(p['name'] for p in analysis['providers']) == PROVIDER_NAMES and
            tuple(analysis['platform_libraries']) == PLATFORM and key(analysis['linker']) == key(LINKER) and
            analysis['linker_sha256'] == PINS[LINKER], 'Base link recipe differs')
    providers = []
    for row in analysis['providers']:
        require(row['runtime'] == '/MD', 'Provider runtime differs')
        library = pin(row['library'])
        pin(row['build_report']); pin(row['conformance'])
        if row.get('dll'):
            pin(row['dll'])
        providers.append({'name': row['name'], 'library': library, 'coff': inspect_coff(library['path'])})
    pin(analysis['link_response']); pin(analysis['generated_dll'])
    old_pe = inspect_pe(analysis['generated_dll']['path'])
    old_lines = Path(analysis['link_response']['path']).read_text(encoding='utf-8').splitlines()
    old_objects = [line[1:-1] for line in old_lines if line.startswith('"') and line.endswith('.obj"')]
    require(len(old_objects) == 161 and len({key(path) for path in old_objects}) == 161 and
            {Path(path).stem.casefold() for path in old_objects} == set(object_rows) and
            all(Path(path).parent == PROJECT / 'Build/SDK_x64/attempt_037/obj' for path in old_objects),
            'Old response is not the finite 161-object base recipe')
    expected_tail = ['"' + row['library']['path'] + '"' for row in analysis['providers']] + list(PLATFORM)
    require(old_lines[-len(expected_tail):] == expected_tail, 'Old response provider/platform order differs')
    old_directory = Path(analysis['link_response']['path']).parent
    expected_prefix = ['/NOLOGO', '/DLL', '/MACHINE:X64', '/INCREMENTAL:NO', '/OPT:REF', '/OPT:ICF',
        f'/DEF:"{DEFINITION}"', f'/OUT:"{analysis["generated_dll"]["path"]}"',
        f'/IMPLIB:"{old_directory / "probe.lib"}"', f'/MAP:"{analysis["link_map"]["path"]}"']
    require(old_lines == expected_prefix + ['"' + path + '"' for path in old_objects] + expected_tail,
            'Unexpected option or overlay in old base response')
    require(set(DEFINITION.read_text(encoding='ascii').split()) == {'EXPORTS', *EXPORTS}, 'Definition exports differ')

    dll = OUT / 'CvGameCoreDLL_Expansion2_x64_base.dll'
    map_path, library, exp, response = dll.with_suffix('.map'), OUT / 'Base.lib', OUT / 'Base.exp', OUT / 'link.rsp'
    setup = OUT / 'read_build_environment.cmd'
    result_path, started_path, failed_path = (STAGE / ('base_link_' + name + '.json') for name in ('result', 'started', 'failed'))
    log_path, validation_path = STAGE / 'base_link.log', STAGE / 'base_link_validation.json'
    writable = {key(path) for path in (dll, map_path, library, exp, response, setup, result_path,
                                      started_path, failed_path, log_path, validation_path)}
    allowed_commands = {(str(CMD), '/d', '/c', str(setup))}
    calls = []

    def audit(event, args):
        if event == 'subprocess.Popen':
            command = next((row for row in allowed_commands if subprocess.list2cmdline(row) == args[1]), None) \
                if isinstance(args[1], str) else tuple(map(str, args[1]))
            require(command in allowed_commands and (args[0] is None or key(args[0]) == key(command[0])),
                    'Unapproved child process')
            calls.append(command)
        if event == 'open' and args and isinstance(args[0], (str, bytes, os.PathLike)):
            writing = isinstance(args[1], str) and any(c in args[1] for c in 'wax+') or \
                isinstance(args[2], int) and args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                require(key(os.fsdecode(args[0])) in writable, 'Write escaped exact output allowlist')
        if event in ('os.remove', 'os.rmdir', 'os.mkdir', 'os.rename', 'os.chmod', 'os.link', 'os.symlink'):
            targets = args[:2] if event in ('os.rename', 'os.link', 'os.symlink') else args[:1]
            for target in targets:
                if isinstance(target, (str, bytes, os.PathLike)):
                    require(event == 'os.mkdir' and key(os.fsdecode(target)) == key(OUT) or
                            event == 'os.remove' and key(os.fsdecode(target)) == key(setup),
                            'Unapproved filesystem mutation')
        if event.startswith(('ctypes.dlopen', 'socket.', 'urllib.', 'http.client.', 'winreg.')) or \
                event in ('os.system', 'os.startfile', 'os.startfile/2'):
            raise RuntimeError('Network, dynamic loading, registry access and interactive launches forbidden')

    sys.addaudithook(audit)
    verify_inputs()
    OUT.mkdir()
    native = importlib.import_module('native_build')
    original_run = native.run

    def run_low(command, *, cwd, env=None, timeout=60):
        command = [str(x) for x in command]
        if command[0].lower() == 'cmd.exe':
            command[0] = str(CMD)
            expected = '@echo off\ncall "' + str(VS / 'VC/Auxiliary/Build/vcvars64.bat') + '" >nul\nif errorlevel 1 exit /b 1\nset\n'
            require(setup.read_text(encoding='utf-8') == expected, 'Environment setup content differs')
        require(tuple(command) in allowed_commands, 'Command not registered before launch')
        return subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=timeout,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)

    native.run = run_low
    retired = []
    try:
        output_json(started_path, {'status': 'BASE_LINK_STARTED_NOT_LOADED', 'builder': artifact(__file__),
                                  'compile_report': INPUTS[key(LATEST)], 'output_root': str(OUT)})
        vcvars = VS / 'VC/Auxiliary/Build/vcvars64.bat'
        capture(vcvars); capture(vcvars.with_name('vcvarsall.bat')); capture(CMD)
        env, selected = native.environment_for(VS, 'x64', OUT)
        require(key(selected) == key(COMPILER), 'Environment selected a different compiler')
        env['VSLANG'] = '1033'; env['TMP'] = env['TEMP'] = str(OUT)
        lib_dirs = [Path(value.strip().strip('"')) for value in env.get('LIB', '').split(';') if value.strip()]
        require(lib_dirs and all(path.is_absolute() for path in lib_dirs), 'Invalid LIB search path')
        explicit = {Path(row['library']['path']).name.lower(): Path(row['library']['path']) for row in providers}
        resolutions = {}

        def resolve(name):
            require(re.fullmatch(r'[A-Za-z0-9_.-]+', name), 'Unexpected default library name: ' + name)
            name = name if name.lower().endswith('.lib') else name + '.lib'
            selected_path = explicit.get(name.lower()) or next((directory / name for directory in lib_dirs
                                                               if (directory / name).is_file()), None)
            require(selected_path is not None, 'Library missing from LIB search: ' + name)
            input_path(selected_path)
            return selected_path

        platform = []
        for name in PLATFORM:
            path = resolve(name); resolutions[name.lower()] = str(path)
            platform.append({'name': name, 'library': capture(path), 'coff': inspect_coff(path)})
        pending = [name for row in list(COFF.values()) for name in row['default_libraries']]
        defaults_seen = set()
        implicit = []
        while pending:
            name = pending.pop()
            canonical = (name if name.lower().endswith('.lib') else name + '.lib').lower()
            if canonical in defaults_seen:
                continue
            defaults_seen.add(canonical)
            path = resolve(name); resolutions[canonical] = str(path)
            detail = inspect_coff(path)
            implicit.append({'name': canonical, 'library': capture(path), 'coff': detail,
                             'scope': 'Pre-resolved DEFAULTLIB candidate; actual selection is reported separately'})
            pending.extend(detail['default_libraries'])
            require(len(defaults_seen) <= 128, 'Unbounded default-library graph')
        ordered_objects = [object_rows[Path(path).stem.casefold()] for path in old_objects]
        flags = ['/NOLOGO', '/DLL', '/MACHINE:X64', '/INCREMENTAL:NO', '/OPT:REF', '/OPT:ICF',
                 '/Brepro', '/DYNAMICBASE', '/NXCOMPAT', '/VERBOSE:LIB', f'/DEF:"{DEFINITION}"',
                 f'/OUT:"{dll}"', f'/IMPLIB:"{library}"', f'/MAP:"{map_path}"']
        flags += ['"' + row['path'] + '"' for row in ordered_objects]
        flags += ['"' + row['library']['path'] + '"' for row in providers + platform]
        response.write_text('\n'.join(flags) + '\n', encoding='utf-8')
        response_before = artifact(response)
        command = (str(LINKER), '@' + str(response))
        allowed_commands.add(command)
        verify_inputs()
        linked = run_low(command, cwd=OUT, env=env, timeout=180)
        output = (linked.stdout + linked.stderr).decode('mbcs', errors='replace')
        log_path.write_text(output, encoding='utf-8')
        require(linked.returncode == 0 and not re.search(r'\b(?:fatal\s+)?error\s+LNK\d+|\bwarning\s+LNK\d+', output, re.I),
                'Base link failed or emitted a linker diagnostic; inspect base_link.log')
        require(not re.search(r'\bLNK(?:2001|2019|1120)\b', output, re.I), 'Unresolved symbols remain')
        require(artifact(response) == response_before, 'Link response changed')
        for name, expected in resolutions.items():
            require(key(resolve(name)) == key(expected), 'LIB resolution changed during link: ' + name)
        searched, search_events = [], verbose_library_searches(output)
        for event in search_events:
            path = Path(event['path'])
            require(key(path) in COFF, 'Linker searched an unsealed library: ' + str(path))
            if key(path) not in {key(row['path']) for row in searched}:
                searched.append(INPUTS[key(path)])
        require(searched, 'Missing actual /VERBOSE:LIB search evidence')
        loaded_members = re.findall(r'(?im)^\s*Loaded\s+([^\r\n]+)', output)
        provider_keys = {key(row['library']['path']) for row in providers}
        platform_keys = {key(row['library']['path']) for row in platform}
        pe = inspect_pe(dll)
        require(pe['dynamic_base'] and pe['nx_compatible'], 'ASLR/NX flags missing')
        require(set(pe['imports']) == set(old_pe['imports']), 'Base DLL import-module set changed')
        map_text = map_path.read_text(encoding='mbcs', errors='strict')
        map_checks = {}
        for name, rva in pe['exports'].items():
            matches = re.findall(r'(?m)^\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}\s+' + re.escape(name) +
                                 r'\s+([0-9A-Fa-f]{16})\s+f\s+CvGameCoreDLL\.obj\s*$', map_text)
            require(len(matches) == 1 and int(matches[0], 16) == pe['image_base'] + rva,
                    'Export/map/COFF owner mismatch: ' + name)
            map_checks[name] = {'rva': rva, 'absolute_address': matches[0], 'object': 'CvGameCoreDLL.obj'}
        require(not re.search(r'SaveRestoreSDK[\\/]|FoundValue[^\s]*[\\/]|LuaBorrowedSDK[\\/]|attempt_037[\\/]obj',
                              map_text, re.I), 'Unexpected overlay/stale object origin in map')
        selected_libraries, mapped_groups = map_archive_selection(
            map_text, COFF, INPUTS, provider_keys, platform_keys, {key(row['path']) for row in searched})
        selected_member_count = sum(len(row['members']) for row in selected_libraries)
        import_library = inspect_output_coff(library)
        export_object = inspect_output_coff(exp)
        for name in EXPORTS:
            require(name.encode('ascii') + b'\0' in library.read_bytes(), 'Import library is missing an export')
        setup_before = artifact(setup)
        setup_stat = setup.stat()
        require(setup_stat.st_nlink == 1 and setup.parent == OUT and artifact(setup) == setup_before,
                'Temporary environment file identity changed')
        setup.unlink()
        retired.append({**setup_before, 'file_id': setup_stat.st_ino, 'links': setup_stat.st_nlink,
                        'result': 'deleted', 'reason': 'Regenerable environment setup; not a link output'})
        expected_outputs = {key(path) for path in (dll, map_path, library, exp, response)}
        require({key(path) for path in OUT.iterdir()} == expected_outputs, 'Unexpected base_link output artifact')
        verify_inputs()
        validation = {'pe': pe, 'exports_match_definition_and_map': map_checks,
            'import_module_set_matches_old_base': True, 'output_import_library': import_library,
            'output_export_object': export_object, 'library_search_order': [str(path) for path in lib_dirs],
            'pre_resolved_default_libraries': implicit, 'actual_searched_libraries': searched,
            'library_search_events': search_events, 'verbose_loaded_member_lines': loaded_members,
            'verbose_loaded_member_scope': 'Optional English Loaded lines only; an empty list is expected for the observed Korean log',
            'actual_selected_libraries': selected_libraries, 'final_map_library_groups': mapped_groups,
            'selection_evidence_source': 'link_map_section_owner_member', 'map_observed_owner_member_pair_count': selected_member_count,
            'selection_scope': 'Final map owner/member labels only; identical archive names may collapse; no transient/physical extraction count is claimed',
            'coff_checks': list(COFF.values()), 'retired': retired, 'allowed_commands': sorted(allowed_commands),
            'child_commands': calls, 'unresolved_symbols': 0, 'linker_warnings': 0}
        output_json(validation_path, validation)
        result = {'schema': 'zerosis.sdk.current_base_link.v1', 'status': 'PASS_CURRENT_BASE_SDK_LINK_NOT_LOADED',
            'utc': datetime.now(timezone.utc).isoformat(), 'generated_dll': artifact(dll),
            'pe': pe, 'objects': ordered_objects, 'object_count': 161, 'providers': providers, 'provider_count': 16,
            'platform_libraries': platform, 'platform_library_count': 14, 'implicit_library_candidates': implicit,
            'actual_searched_libraries': searched, 'library_search_event_count': len(search_events),
            'library_search_locales': sorted({event['locale'] for event in search_events}),
            'verbose_loaded_member_lines': loaded_members, 'verbose_loaded_member_line_count': len(loaded_members),
            'actual_selected_libraries': selected_libraries, 'final_map_library_groups': mapped_groups,
            'selection_evidence_source': 'link_map_section_owner_member', 'map_observed_owner_member_pair_count': selected_member_count,
            'unresolved_symbols': 0, 'linker_exit_code': linked.returncode, 'linker_warnings': 0,
            'compile_report': INPUTS[key(LATEST)], 'compile_state': INPUTS[key(STATE)],
            'link_response': response_before, 'link_log': artifact(log_path), 'link_map': artifact(map_path),
            'import_library': artifact(library), 'export_object': artifact(exp), 'validation': artifact(validation_path),
            'definition': INPUTS[key(DEFINITION)], 'compiler': INPUTS[key(COMPILER)], 'linker': INPUTS[key(LINKER)],
            'inputs': list(INPUTS.values()), 'inputs_unchanged': True, 'retired': retired,
            'hidden_below_normal_children': True, 'gamecore_loaded': False, 'host_executed': False,
            'windows_created': False, 'retail_accessed': False, 'sdk_source_copied': False,
            'overlays_used': False, 'full_host_integration': False, 'retail_save_accepted': False,
            'full_ui_accepted': False, 'multicore_accepted': False, 'full_engine_goal_complete': False,
            'runtime_updated': False, 'default_promoted': False,
            'scope': 'Current base SDK source compiled and linked with retained providers; DLL never loaded'}
        output_json(result_path, result)
        print(json.dumps({'status': result['status'], 'objects': 161, 'providers': 16, 'platform_libraries': 14,
                          'unresolved_symbols': 0, 'report': str(result_path)}))
    except Exception as error:
        output_json(failed_path, {'status': 'CURRENT_BASE_SDK_LINK_FAILED_PRESERVED',
            'error': str(error), 'output_root': str(OUT), 'child_commands': calls,
            'gamecore_loaded': False, 'runtime_updated': False})
        raise
    finally:
        native.run = original_run


def inspect_output_coff(path):
    """Validate a new linker output without treating it as a sealed input."""
    before = INPUTS.copy()
    try:
        row = inspect_coff(path)
        return row
    finally:
        INPUTS.clear()
        INPUTS.update(before)


if __name__ == '__main__':
    main()
