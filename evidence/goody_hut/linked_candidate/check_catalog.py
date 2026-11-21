"""Check the current Goody catalog with sealed source inputs and Lua 5.1 parsing only.

The hexadecimal catalog reader and parser-only ctypes surface follow the reviewed
Pantheon checker. No prior checker module, main, or scope-specific binding runs.
"""
from __future__ import annotations

import argparse
import ast
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import sys
import xml.etree.ElementTree as ET


STAGE = Path(__file__).absolute().parent
PROJECT = STAGE.parents[2]
SCOPE = STAGE / 'scope.json'
HEADER = PROJECT / 'Source/Host/UiPopupAssets.generated.h'
MAX_HEADER = 128 * 1024 * 1024
MAX_SCRIPT = 32 * 1024 * 1024
SEAL_SHA = 'a9eda8a585d65c8a1e34eb4738e8d43be43be0e1e2acf590d7d9e4af7b230a24'
CONFORMANCE_SHA = 'db111c175358cc15d61b14eda74e33c1c981826f4b69cb035ba5e3f106fce6d3'
LUA_SHA = '4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944'
LUA_BYTES = 166912
HELPER_SHA = '2e4c37cb030e0078235491a0a7facda9584643c04e1f91534b8fc1187f616e71'
PASS_STATUS = 'PASS_GOODY_GENERATED_CATALOG_LUA51_PARSE_ONLY_NATIVE_PENDING'
PARSER_FUNCTIONS = {'luaL_newstate', 'luaL_loadbuffer', 'lua_tolstring', 'lua_close'}
ADDENDA = (
    ('hasRetainedCityUi', 'Source/Presentation/UiCityView.lua'),
    ('hasRetainedUnitUi', 'Source/Presentation/UiUnitPanel.lua'),
    ('hasRetainedSocialPolicyUi', 'Source/Presentation/UiSocialPolicy.lua'),
    ('hasRetainedEconomicUi', 'Source/Presentation/UiEconomicOverview.lua'),
    ('hasRetainedActionInfoUi', 'Source/Presentation/UiActionInfoPanel.lua'),
    ('hasRetainedNotificationUi', 'Source/Presentation/UiNotificationPanel.lua'),
)
RETAIL_USER_ROOTS = (r'C:\Users\home\OneDrive\Documents\My Games', r'C:\Users\home\Documents\My Games')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def within(path, root):
    value, parent = key(path), key(root)
    return value == parent or value.startswith(parent + os.sep)


def ordinary(path):
    path = Path(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400,
            'Input must be an ordinary non-reparse file')
    for parent in path.absolute().parents:
        attrs = parent.lstat()
        require(stat.S_ISDIR(attrs.st_mode) and not getattr(attrs, 'st_file_attributes', 0) & 0x400,
                'Input ancestor must be an ordinary directory')
    return info


def artifact(path, limit=MAX_HEADER):
    path = Path(path).absolute()
    before = ordinary(path)
    require(0 <= before.st_size <= limit, 'Input exceeds its bounded size')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    after = ordinary(path)
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), 'Input changed while hashing')
    return {'path': str(path), 'bytes': before.st_size, 'sha256': digest.hexdigest()}


def sealed(row, limit=MAX_HEADER):
    require(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'} and
            isinstance(row['path'], str) and Path(row['path']).is_absolute() and
            type(row['bytes']) is int and isinstance(row['sha256'], str) and
            re.fullmatch('[0-9a-f]{64}', row['sha256']), 'Malformed artifact identity')
    ref = artifact(row['path'], limit)
    require(key(ref['path']) == key(row['path']) and ref['bytes'] == row['bytes'] and ref['sha256'] == row['sha256'],
            'Sealed artifact identity changed')
    return ref


def read_json(path):
    require(ordinary(path).st_size <= 2 * 1024 * 1024, 'JSON exceeds its bounded size')
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def install_guard(output):
    counts = dict(explicit_lua_provider_loads=0, blocked_process_attempts=0, blocked_retail_attempts=0,
                  blocked_write_attempts=0, blocked_dll_attempts=0, blocked_read_attempts=0,
                  blocked_network_attempts=0)
    control = {'dll': None, 'library': None, 'symbols': set(),
               'reads': {key(SCOPE), key(HEADER), key(__file__)}}

    def guard(event, args):
        if event.startswith(('subprocess.', 'os.exec', 'os.spawn')) or event in (
                'os.system', 'os.fork', 'os.forkpty', 'os.startfile', 'os.posix_spawn', 'os.posix_spawnp'):
            counts['blocked_process_attempts'] += 1
            raise PermissionError('Additional processes are forbidden')
        if event.startswith(('socket.', 'urllib.', 'http.client.')):
            counts['blocked_network_attempts'] += 1
            raise PermissionError('Network access is forbidden')
        if event == 'ctypes.dlopen':
            name = args[0] if args else None
            if not isinstance(name, (str, bytes, os.PathLike)) or control['dll'] is None or \
                    key(os.fsdecode(name)) != control['dll'] or counts['explicit_lua_provider_loads']:
                counts['blocked_dll_attempts'] += 1
                raise PermissionError('Only the single sealed pure Lua parser provider may be loaded')
            counts['explicit_lua_provider_loads'] += 1
        if event in ('ctypes.dlsym', 'ctypes.dlsym/handle'):
            name = args[1] if len(args) > 1 else None
            if event != 'ctypes.dlsym' or not args or args[0] is not control['library'] or name not in PARSER_FUNCTIONS:
                counts['blocked_dll_attempts'] += 1
                raise PermissionError('Only the four parser/state-lifetime symbols may be resolved')
            control['symbols'].add(name)
        if event in ('open', 'os.listdir', 'os.scandir', 'os.chdir') and args:
            path = args[0]
            if isinstance(path, (str, bytes, os.PathLike)):
                path = os.fsdecode(path)
                if any(within(path, root) for root in RETAIL_USER_ROOTS):
                    counts['blocked_retail_attempts'] += 1
                    raise PermissionError('Retail user state is forbidden')
                if event != 'open':
                    counts['blocked_read_attempts'] += 1
                    raise PermissionError('Directory enumeration and working-directory changes are forbidden')
                mode = args[1] if len(args) > 1 else None
                flags = args[2] if len(args) > 2 else 0
                writing = isinstance(mode, str) and any(c in mode for c in 'wax+') or \
                    isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC))
                if writing and key(path) != key(output):
                    counts['blocked_write_attempts'] += 1
                    raise PermissionError('Only the fresh bounded JSON receipt may be written')
                if not writing and key(path) not in control['reads']:
                    counts['blocked_read_attempts'] += 1
                    raise PermissionError('Read escaped the sealed input set')
        if event in ('os.remove', 'os.unlink', 'os.rename', 'os.replace', 'os.rmdir', 'os.mkdir',
                     'os.link', 'os.symlink', 'os.chmod', 'os.utime', 'os.add_dll_directory'):
            counts['blocked_write_attempts'] += 1
            raise PermissionError('Filesystem mutations other than exclusive receipt creation are forbidden')

    sys.addaudithook(guard)
    return counts, control


def parse_catalog(path):
    arrays, order = {}, None
    declaration = re.compile(rb'static const char ([A-Za-z_][A-Za-z0-9_]*)\[\]=\n')
    chunk = re.compile(rb'"(?:\\x[0-9a-f]{2}){0,64}"')
    catalog_row = re.compile(rb'\{"([A-Za-z_][A-Za-z0-9_]*)",([A-Za-z_][A-Za-z0-9_]*),sizeof\(\2\)-1\},\n')
    with Path(path).open('rb') as stream:
        while True:
            line = stream.readline(4097)
            if not line:
                break
            require(len(line) <= 4096, 'Generated header line exceeds its format bound')
            match = declaration.fullmatch(line)
            if match:
                name = match.group(1).decode('ascii')
                require(name not in arrays and len(arrays) < 256 and order is None, 'Duplicate or misplaced char array')
                raw, previous_size = bytearray(), None
                while True:
                    line = stream.readline(4097)
                    require(line and len(line) <= 4096 and line.endswith(b'\n'), 'Truncated generated char array')
                    final = line.endswith(b';\n')
                    literal = line[:-2] if final else line[:-1]
                    require(chunk.fullmatch(literal) and (previous_size is None or previous_size == 64),
                            'Generated char array is not exact 64-byte hexadecimal chunks')
                    value = bytes.fromhex(literal[1:-1].replace(b'\\x', b'').decode('ascii'))
                    require(value or final and previous_size is None, 'Empty nonterminal generated chunk')
                    raw.extend(value)
                    require(len(raw) <= MAX_SCRIPT, 'Registered script exceeds its bounded size')
                    previous_size = len(value)
                    if final:
                        break
                require(b'\0' not in raw, 'NUL in registered script')
                arrays[name] = bytes(raw)
            elif line == b'static const Script scripts[]={\n':
                require(order is None, 'Duplicate script registry')
                order = []
                while True:
                    line = stream.readline(4097)
                    if line == b'};\n':
                        break
                    match = catalog_row.fullmatch(line)
                    require(match and len(order) < 256, 'Malformed script registry row')
                    name, symbol = (part.decode('ascii') for part in match.groups())
                    require(name == symbol and name not in order and name in arrays, 'Registry symbol does not resolve uniquely')
                    order.append(name)
    require(order and set(order) == set(arrays), 'Registry and char-array inventory differ')
    return arrays, order


class LayoutLiteral:
    """Read only the serializer's literal data grammar, without executing Lua."""
    def __init__(self, raw):
        require(raw.startswith(b'ZeroSisUiLayout=') and len(raw) <= MAX_SCRIPT, 'Invalid layout assignment')
        self.text, self.pos, self.values = raw[len(b'ZeroSisUiLayout='):].decode('ascii'), 0, 0

    def whitespace(self):
        while self.pos < len(self.text) and self.text[self.pos] in ' \t\r\n':
            self.pos += 1

    def take(self, token):
        self.whitespace()
        require(self.text.startswith(token, self.pos), 'Unexpected layout literal token')
        self.pos += len(token)

    def value(self, depth=0):
        self.whitespace();self.values += 1
        require(depth <= 64 and self.values <= 2000000 and self.pos < len(self.text), 'Layout literal exceeded bounds')
        char = self.text[self.pos]
        if char == '"':
            self.pos += 1;raw = bytearray()
            while self.pos < len(self.text) and self.text[self.pos] != '"':
                char = self.text[self.pos];self.pos += 1
                if char == '\\':
                    digits = self.text[self.pos:self.pos+3]
                    require(len(digits) == 3 and digits.isascii() and digits.isdigit() and int(digits) <= 255,
                            'Layout string escape is not a serialized byte')
                    raw.append(int(digits));self.pos += 3
                else:
                    require(32 <= ord(char) < 127, 'Unescaped layout string byte')
                    raw.append(ord(char))
            self.take('"')
            return raw.decode('utf-8')
        if char == '{':
            self.take('{');self.whitespace()
            if self.text.startswith('}', self.pos):
                self.take('}');return []
            mapping = self.text.startswith('[', self.pos)
            result = {} if mapping else []
            while True:
                if mapping:
                    self.take('[');field = self.value(depth+1);self.take(']');self.take('=')
                    require(type(field) in (str, int) and field not in result, 'Duplicate/invalid literal table key')
                    result[field] = self.value(depth+1)
                else:
                    result.append(self.value(depth+1))
                self.whitespace()
                if self.text.startswith('}', self.pos):
                    self.take('}');return result
                self.take(',')
        for literal, value in (('true', True), ('false', False)):
            if self.text.startswith(literal, self.pos):
                self.pos += len(literal);return value
        number = re.match(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?', self.text[self.pos:])
        require(number, 'Layout data contains an expression, call or unsupported value')
        self.pos += len(number.group())
        value = float(number.group()) if any(c in number.group() for c in '.eE') else int(number.group())
        require(type(value) is int or math.isfinite(value), 'Nonfinite layout number')
        return value

    def parse(self):
        result = self.value();self.whitespace()
        require(self.pos == len(self.text) and type(result) is dict, 'Trailing layout source or missing root table')
        return result


def xml_tree(raw):
    def visit(element):
        return {'kind': element.tag, 'attributes': dict(element.attrib), 'children': [visit(child) for child in element]}
    return visit(ET.fromstring(raw))


def source_literal(node, env):
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, (ast.Tuple, ast.List)):
        return [source_literal(child, env) for child in node.elts]
    if isinstance(node, ast.Dict):
        return {source_literal(k, env): source_literal(v, env) for k, v in zip(node.keys, node.values)}
    if isinstance(node, ast.Name) and node.id in env:
        return env[node.id]
    if isinstance(node, ast.Subscript):
        return source_literal(node.value, env)[source_literal(node.slice, env)]
    raise ValueError('Not a static catalog declaration')


def declared_registry(source):
    env = {}
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                env[node.targets[0].id] = source_literal(node.value, env)
            except (ValueError, KeyError, TypeError):
                continue
    scripts, layouts = env.get('SCRIPTS'), env.get('LAYOUTS')
    require(type(scripts) is list and type(layouts) is list, 'Missing static source catalog declarations')
    return [row[0] for row in scripts + layouts] + ['ZeroSisUiScene', 'ProductionCommandGuard', 'ResearchCommandGuard']


def parse_scripts(provider, arrays, order, control):
    sealed(provider, 1024 * 1024)
    control['dll'] = key(provider['path'])
    lua = ctypes.CDLL(str(Path(provider['path']).absolute()))
    control['library'] = lua
    lua.luaL_newstate.argtypes = [];lua.luaL_newstate.restype = ctypes.c_void_p
    lua.luaL_loadbuffer.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t, ctypes.c_char_p]
    lua.luaL_loadbuffer.restype = ctypes.c_int
    lua.lua_tolstring.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.POINTER(ctypes.c_size_t)]
    lua.lua_tolstring.restype = ctypes.c_void_p
    lua.lua_close.argtypes = [ctypes.c_void_p];lua.lua_close.restype = None
    rows = []
    for name in order:
        raw = arrays[name];bom = raw.startswith(b'\xef\xbb\xbf');code = raw[3:] if bom else raw
        row = {'name': name, 'raw_bytes': len(raw), 'raw_sha256': hashlib.sha256(raw).hexdigest(),
               'parse_input_bytes': len(code), 'parse_input_sha256': hashlib.sha256(code).hexdigest(),
               'utf8_bom_removed_for_parse': bom}
        state = lua.luaL_newstate()
        require(state, 'Cannot allocate pure Lua parser state')
        try:
            status = lua.luaL_loadbuffer(state, code, len(code), name.encode('ascii'))
            row.update(lua_status=status, status='PASS_PARSE_ONLY' if status == 0 else 'FAILED_PARSE_ONLY')
            if status:
                length = ctypes.c_size_t()
                pointer = lua.lua_tolstring(state, -1, ctypes.byref(length))
                message = ctypes.string_at(pointer, min(length.value, 4096)) if pointer else b''
                line = re.search(rb':([0-9]+):', message)
                row.update(diagnostic_sha256=hashlib.sha256(message).hexdigest(),
                           diagnostic_line=int(line.group(1)) if line else None,
                           diagnostic_kind='UPVALUE_LIMIT' if b'upvalues' in message else 'LUA_LOAD_ERROR')
        finally:
            lua.lua_close(state)
        rows.append(row)
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    output = args.output.absolute()
    require(key(output.parent) == key(STAGE) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\.json', output.name) and
            not os.path.lexists(output), 'Receipt must be a fresh JSON directly below the linked stage')
    ordinary(SCOPE)
    b'x'.decode('utf-8-sig')  # Load this codec before the exact input-open guard.
    b'x'.decode('ascii')
    counts, control = install_guard(output)
    before = {}

    def record(row, limit=MAX_HEADER):
        ref = sealed(row, limit);before[key(ref['path'])] = ref;return ref

    def allow(row):
        require(type(row) is dict and isinstance(row.get('path'), str), 'Missing scoped input reference')
        control['reads'].add(key(row['path']))
        return row

    def current(path):
        control['reads'].add(key(path))
        ref = artifact(path);before[key(ref['path'])] = ref;return ref

    report = {'schema': 'zerosis.goody_hut.generated_catalog_precompile.v1', 'status': 'FAILED_PRECONDITION',
              'scripts_executed': False, 'lua_openlibs_called': False, 'lua_pcall_called': False,
              'host_executed': False, 'gamecore_loaded': False, 'hwnd_created': False,
              'retail_user_state_accessed': False, 'additional_processes_started': 0,
              'native_acceptance_verified': False, 'default_promoted': False, 'full_engine_goal_complete': False,
              'scripts': [], 'catalog_count': 0, 'parsed_count': 0, 'failed_count': None}
    exit_code = 1
    try:
        current(SCOPE);current(__file__)
        scope = read_json(SCOPE)
        require(scope.get('schema') == 'zerosis.goody_hut.link_scope.v1' and
                scope.get('pure_lua_dll_syntax_only_allowed') is True and scope.get('host_execution_allowed') is False and
                scope.get('gamecore_execution_allowed') is False and scope.get('hwnd_execution_allowed') is False and
                scope.get('retail_user_state_or_game_process_access_allowed') is False and
                scope.get('retail_mod_test_hold_active') is True, 'Scope does not authorize the pure parser boundary')
        require(scope.get('expected_catalog_status') == PASS_STATUS, 'Scope expects a different catalog proof boundary')
        for field in ('source_seal', 'source_conformance', 'baseline_build', 'baseline_generated_header',
                      'pure_lua_provider', 'catalog_parser_helper', 'script_loader'):
            record(allow(scope[field]))
        require(scope['source_seal']['sha256'] == SEAL_SHA and scope['source_conformance']['sha256'] == CONFORMANCE_SHA,
                'Current source seal or source conformance pin differs')
        require(scope['catalog_parser_helper']['sha256'] == HELPER_SHA and
                scope['catalog_parser_helper']['bytes'] == 20464,
                'Reviewed catalog parser helper identity differs')
        provider = scope['pure_lua_provider']
        require(provider['bytes'] == LUA_BYTES and provider['sha256'] == LUA_SHA and
                key(provider['path']) == key(PROJECT / 'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'),
                'Lua provider is not the approved pure parser binary')
        seal = read_json(scope['source_seal']['path'])
        require(seal.get('schema') == 'zerosis.goody_hut.source_seal.v1', 'Wrong source seal schema')
        conformance = read_json(scope['source_conformance']['path'])
        require(conformance.get('status') == 'PASS_SOURCE_LUA_COMPONENT_RENDERER_CONTRACT_AND_DRIVER_PARSER_BUILD_NATIVE_PENDING',
                'Source conformance does not retain its build/native boundary')
        for group in ('production_sources', 'new_assets_and_tests'):
            for relative, row in seal[group].items():
                require(key(PROJECT / relative) == key(row['path']), 'Source seal escaped its exact workspace path')
                record(allow(row))
        base = read_json(scope['baseline_build']['path'])
        require(base.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and
                base.get('build_id') == seal['frozen_build'], 'Baseline build differs from the source seal')
        old_header_rows = [row for row in base.get('compiler_inputs', [])
                           if row.get('relative_path', '').replace('\\', '/') == 'Source/Host/UiPopupAssets.generated.h']
        require(len(old_header_rows) == 1 and all(scope['baseline_generated_header'][field] == old_header_rows[0][field]
                                               for field in ('path', 'bytes', 'sha256')),
                'Old catalog is not the exact immutable baseline compiler input')
        require(key(scope['generated_header']['path']) == key(HEADER), 'Mutable generated-header path escaped Source/Host')
        header_ref = current(HEADER)
        old_arrays, old_order = parse_catalog(scope['baseline_generated_header']['path'])
        arrays, order = parse_catalog(HEADER)
        require(scope.get('baseline_catalog_count') == len(old_order) == 64 and
                scope.get('expected_catalog_count') == len(order) == 66 and
                set(order) - set(old_order) == {'GoodyHutPopup', 'GoodyHutRewardLayout'} and
                set(old_order) - set(order) == set() and
                [name for name in order if name not in {'GoodyHutPopup', 'GoodyHutRewardLayout'}] == old_order,
                'Catalog must preserve the old 64 names/order and add exactly the two Goody records')
        prep = seal['production_sources']['tools/prepare_ui_popup_assets.py']
        require(order == declared_registry(Path(prep['path']).read_bytes()),
                'Actual registry differs from the exact sealed preparation source declarations')
        addenda = scope['scene_addenda']
        require(set(addenda) == {relative for _, relative in ADDENDA}, 'Expected the six current scene addenda')
        scene = Path(seal['production_sources']['Source/Host/UiScene.lua']['path']).read_bytes() + b'\n' + \
            Path(seal['production_sources']['Source/Presentation/UiPresentationInput.lua']['path']).read_bytes()
        for flag, relative in ADDENDA:
            row = record(allow(addenda[relative]))
            matches = [entry for entry in base.get('sources', []) if entry.get('relative_path', '').replace('\\', '/') == relative]
            require(key(row['path']) == key(PROJECT / relative) and len(matches) == 1 and
                    all(row[field] == matches[0][field] for field in ('bytes', 'sha256')),
                    'Scene addendum differs from its sealed unchanged baseline')
            scene += b'\nif ' + flag.encode('ascii') + b' then\n' + Path(row['path']).read_bytes() + b'\nend\n'
        require(arrays.get('ZeroSisUiScene') == scene, 'Catalog must contain the exact complete current scene and all six addenda')
        for name, relative in (('ProductionCommandGuard', 'Source/Host/ProductionCommandGuard.lua'),
                               ('ResearchCommandGuard', 'Source/Host/ResearchCommandGuard.lua'),
                               ('ScriptSystem', 'Source/Host/ScriptSystem.h')):
            rows = [entry for entry in base.get('sources', []) if entry.get('relative_path', '').replace('\\', '/') == relative]
            require(len(rows) == 1, 'Missing original source baseline: ' + name)
            row = record(allow({'path': str(PROJECT / relative), 'bytes': rows[0]['bytes'], 'sha256': rows[0]['sha256']}))
            raw = Path(row['path']).read_bytes()
            if name != 'ScriptSystem':
                require(arrays.get(name) == raw, 'Command guard differs from its exact source: ' + name)
            else:
                require(row == scope['script_loader'], 'Current script loader differs from its explicit scope reference')
                require(b'if(length>=3 && std::memcmp(data,"\\xef\\xbb\\xbf",3)==0){data+=3;length-=3;}' in raw,
                        'Current script loader no longer has the inspected BOM-only preprocessing')
        original_refs = {}
        for group, names in (('original_goody_assets', ('GoodyHutPopup.lua', 'GoodyHutPopup.xml')),
                             ('original_pantheon_assets', ('ChoosePantheonPopup.lua', 'ChoosePantheonPopup.xml'))):
            require(set(scope[group]) == {'lua', 'xml'}, 'Original asset group must contain exact Lua/XML references')
            refs = {}
            for field, name in zip(('lua', 'xml'), names):
                row = record(allow(scope[group][field]), 1024 * 1024)
                require(Path(row['path']).name == name and row['path'].replace('\\', '/').endswith(
                    '/Assets/DLC/Expansion2/UI/InGame/Popups/' + name), 'Original popup source path differs')
                copied = PROJECT / 'Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups' / name
                record(allow({'path': str(copied), 'bytes': row['bytes'], 'sha256': row['sha256']}), 1024 * 1024)
                refs[field] = row
            original_refs[group] = refs
        goody, pantheon = original_refs['original_goody_assets'], original_refs['original_pantheon_assets']
        require(arrays.get('GoodyHutPopup') == Path(goody['lua']['path']).read_bytes() and
                arrays.get('ChoosePantheonPopup') == Path(pantheon['lua']['path']).read_bytes(), 'Original popup Lua bytes differ')
        require(arrays['ChoosePantheonPopup'] == old_arrays['ChoosePantheonPopup'] and
                arrays.get('PantheonLayout') == old_arrays['PantheonLayout'], 'Existing Pantheon catalog content changed')
        layout = LayoutLiteral(arrays['GoodyHutRewardLayout']).parse()
        old_pantheon = LayoutLiteral(old_arrays['PantheonLayout']).parse()
        def normalized(node):
            return {'kind': node['kind'], 'attributes': node['attributes'],
                    'children': [normalized(child) for child in node['children']]}
        original_tree = xml_tree(Path(goody['xml']['path']).read_bytes())
        require(normalized(layout) == original_tree and
                (layout.get('contextName'), layout.get('popupKind')) == ('GoodyHutPopup', 'GoodyHutReward'),
                'Generated Goody layout changed the original XML control tree or context identity')
        def walk(node):
            yield node
            for child in node['children']:
                yield from walk(child)
        nodes = list(walk(original_tree))
        close = [node for node in nodes if node['attributes'].get('ID') == 'CloseButton']
        require(len(nodes) == 12 and len(close) == 1 and close[0]['kind'] == 'GridButton' and
                close[0]['attributes'].get('Size') == '200,36' and close[0]['attributes'].get('AnchorSide') == 'I.O',
                'Original Goody XML must retain all 12 controls and its unique outside-grid CloseButton')
        metadata = layout.get('goodyHutReward')
        require(type(metadata) is dict and metadata.get('policy') == 'ORIGINAL_BNW_GOODY_HUT_REWARD_INFORMATIONAL_V1' and
                metadata.get('originalLayoutLua') == goody['lua'] and metadata.get('originalLayoutXml') == goody['xml'] and
                metadata.get('rewardAlreadyApplied') is True and metadata.get('nativeAcceptanceVerified') is False,
                'Goody layout provenance or informational/native boundary differs')
        old_metadata = old_pantheon.get('pantheon')
        require(type(old_metadata) is dict and old_metadata.get('originalLayoutLua') == pantheon['lua'] and
                old_metadata.get('originalLayoutXml') == pantheon['xml'] and
                old_metadata.get('policy') == 'ORIGINAL_BNW_PANTHEON_ONLY_V1', 'Baseline Pantheon metadata differs from original pins')
        styles = layout.get('styleDefaultsSource')
        require(styles == old_pantheon.get('styleDefaultsSource') and type(styles) is dict,
                'Goody style metadata differs from the original baseline Styles.xml source')
        record(allow(styles), 4 * 1024 * 1024)
        report['source_binding'] = {'exact_current_scene_input_and_six_addenda': True,
            'original_goody_lua_exact': True, 'original_goody_xml_tree_exact': True, 'goody_control_count': len(nodes),
            'unique_original_close_button': True, 'goody_metadata_source_bound': True,
            'original_pantheon_lua_and_layout_unchanged': True, 'original_snapshots_exact': True,
            'utf8_bom_rule_bound_to_current_script_loader': True, 'exact_catalog_names_and_order_from_source': True}
        report.update(generated_header=header_ref, baseline_catalog_count=len(old_order), catalog_count=len(order),
                      added_catalog_records=sorted(set(order) - set(old_order)))
        report['scripts'] = parse_scripts(provider, arrays, order, control)
        failed = sum(row['lua_status'] != 0 for row in report['scripts'])
        report.update(parsed_count=len(report['scripts']), failed_count=failed)
        report['status'] = PASS_STATUS if not failed else \
            'FAILED_GOODY_GENERATED_CATALOG_LUA51_PARSE_ONLY'
        exit_code = 0 if not failed else 1
    except Exception as error:
        report['error_type'] = type(error).__name__
        report['error'] = str(error)[:240] if isinstance(error, (ValueError, PermissionError)) else 'Bounded catalog precompile check failed'
    try:
        require(before, 'No input seal was established')
        report['inputs_before'] = list(before.values())
        report['inputs_after'] = [sealed(row) for row in before.values()]
        report['inputs_unchanged'] = report['inputs_before'] == report['inputs_after']
        require(not any(value for name, value in counts.items() if name.startswith('blocked_')), 'A forbidden operation was attempted')
        if exit_code == 0:
            require(counts['explicit_lua_provider_loads'] == 1 and control['symbols'] == PARSER_FUNCTIONS,
                    'Parser-only DLL/symbol boundary changed')
    except Exception as error:
        exit_code = 1;report['status'] = 'FAILED_INPUT_PRESERVATION_OR_AUDIT_GUARD'
        report['preservation_error_type'] = type(error).__name__;report['inputs_unchanged'] = False
    report['guard'] = counts
    report['resolved_parser_functions'] = sorted(control['symbols'])
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    require(len(encoded.encode('utf-8')) <= 256 * 1024, 'Bounded catalog receipt exceeded its limit')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(encoded)
    print(json.dumps({'status': report['status'], 'exit_code': exit_code, 'catalog_count': report.get('catalog_count'),
                      'failed_count': report.get('failed_count'), 'report': str(output)}, ensure_ascii=False))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
