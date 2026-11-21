"""Verify a sealed 67-script shared-font catalog; Lua is used for parsing only.

No previous checker's main or source binding is imported or executed. The exact
hexadecimal catalog reader, literal grammar and four-symbol parser boundary are
retained here; font values are independently reconstructed from original GGXML.
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
MAX_JSON = 2 * 1024 * 1024
MAX_PREPARED = 64 * 1024 * 1024
MAX_HEADER = 128 * 1024 * 1024
MAX_SCRIPT = 32 * 1024 * 1024
MAX_INTEGER = 9007199254740991
LUA_SHA = '4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944'
LUA_BYTES = 166912
PASS_STATUS = 'PASS_SHARED_FONT_CATALOG_67_LUA51_PARSE_ONLY_NATIVE_PENDING'
SCOPE_SCHEMA = 'zerosis.goody_hut.shared_font_catalog.scope.v1'
BANK_SCHEMA = 'zerosis.ui.shared_font_metrics.v1'
STORAGE_TAG = 'ZEROSIS_UI_SHARED_GLYPH_SETS_V1'
TRANSPORT_FIELDS = {'glyphSetStorage', 'sharedProfileId', 'glyphSetRefs'}
GLYPH_FIELDS = {'advance', 'width', 'height', 'originX', 'originY'}
FONT_IDS = {'TwCenMT14', 'TwCenMT16', 'TwCenMT18', 'TwCenMT20', 'TwCenMT22', 'TwCenMT24'}
PARSER_FUNCTIONS = {'luaL_newstate', 'luaL_loadbuffer', 'lua_tolstring', 'lua_close'}
ADDED_RECORDS = {'GoodyHutPopup', 'GoodyHutRewardLayout', 'SharedFontMetrics'}
ADDENDA = (
    ('hasRetainedCityUi', 'Source/Presentation/UiCityView.lua'),
    ('hasRetainedUnitUi', 'Source/Presentation/UiUnitPanel.lua'),
    ('hasRetainedSocialPolicyUi', 'Source/Presentation/UiSocialPolicy.lua'),
    ('hasRetainedEconomicUi', 'Source/Presentation/UiEconomicOverview.lua'),
    ('hasRetainedActionInfoUi', 'Source/Presentation/UiActionInfoPanel.lua'),
    ('hasRetainedNotificationUi', 'Source/Presentation/UiNotificationPanel.lua'),
)
RETAIL_USER_ROOTS = (r'C:\Users\home\OneDrive\Documents\My Games',
                     r'C:\Users\home\Documents\My Games')


def require(value, reason):
    if not value:
        raise ValueError(reason)


def key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def within(path, root):
    value, parent = key(path), key(root)
    return value == parent or value.startswith(parent + os.sep)


def is_sha(value):
    return isinstance(value, str) and re.fullmatch('[0-9a-f]{64}', value) is not None


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
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            'Input changed while hashing')
    return {'path': str(path), 'bytes': before.st_size, 'sha256': digest.hexdigest()}


def valid_ref(row):
    require(type(row) is dict and set(row) == {'path', 'bytes', 'sha256'} and
            isinstance(row['path'], str) and Path(row['path']).is_absolute() and
            type(row['bytes']) is int and row['bytes'] >= 0 and is_sha(row['sha256']),
            'Malformed artifact identity')
    return row


def report_reference_matches(row, expected):
    """Accept the production artifact API while retaining scoped size checks."""
    valid_ref(expected)
    if type(row) is not dict or set(row) not in ({'path', 'sha256'}, {'path', 'bytes', 'sha256'}):
        return False
    return (isinstance(row.get('path'), str) and Path(row['path']).is_absolute() and
            key(row['path']) == key(expected['path']) and row.get('sha256') == expected['sha256'] and
            ('bytes' not in row or type(row['bytes']) is int and row['bytes'] == expected['bytes']))


def sealed(row, limit=MAX_HEADER):
    valid_ref(row)
    ref = artifact(row['path'], limit)
    require(key(ref['path']) == key(row['path']) and ref['bytes'] == row['bytes'] and
            ref['sha256'] == row['sha256'], 'Sealed artifact identity changed')
    return ref


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        require(name not in result, 'Duplicate JSON field')
        result[name] = value
    return result


def reject_constant(value):
    raise ValueError('Nonfinite JSON constant')


def read_bytes(path, limit=MAX_JSON):
    require(ordinary(path).st_size <= limit, 'Text input exceeds its bounded size')
    with Path(path).open('rb') as stream:
        raw = stream.read(limit + 1)
    require(len(raw) <= limit, 'Text input grew beyond its bounded size')
    return raw


def read_json(path, limit=MAX_JSON):
    require(limit == MAX_JSON or limit == MAX_PREPARED and
            key(path) == key(PROJECT / 'evidence/ui_popup/assets/prepared.json'),
            'Only the exact prepared-assets JSON may exceed the default JSON limit')
    return json.loads(read_bytes(path, limit).decode('utf-8-sig'),
                      object_pairs_hook=unique_object, parse_constant=reject_constant)


def install_guard(scope_path, output):
    counts = dict(explicit_lua_provider_loads=0, blocked_process_attempts=0,
                  blocked_retail_attempts=0, blocked_write_attempts=0,
                  blocked_dll_attempts=0, blocked_read_attempts=0,
                  blocked_network_attempts=0)
    control = {'dll': None, 'library': None, 'symbols': set(), 'output_opened': False,
               'reads': {key(scope_path), key(__file__)}}

    def guard(event, args):
        if event.startswith(('subprocess.', 'os.exec', 'os.spawn')) or event in (
                'os.system', 'os.fork', 'os.forkpty', 'os.startfile', 'os.posix_spawn',
                'os.posix_spawnp', 'os.kill', 'os.killpg'):
            counts['blocked_process_attempts'] += 1
            raise PermissionError('Additional processes and process queries are forbidden')
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
                raise PermissionError('Only four parser/state-lifetime symbols may be resolved')
            control['symbols'].add(name)
        if event in ('open', 'os.listdir', 'os.scandir', 'os.chdir') and args:
            path = args[0]
            if not isinstance(path, (str, bytes, os.PathLike)):
                counts['blocked_read_attempts'] += 1
                raise PermissionError('Unscoped file-descriptor access is forbidden')
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
            if writing:
                exclusive = isinstance(flags, int) and flags & os.O_EXCL and flags & os.O_CREAT
                if key(path) != key(output) or not exclusive or control['output_opened']:
                    counts['blocked_write_attempts'] += 1
                    raise PermissionError('Only one fresh exclusive JSON receipt may be written')
                control['output_opened'] = True
            elif key(path) not in control['reads']:
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
    require(ordinary(path).st_size <= MAX_HEADER, 'Generated header exceeds 128 MiB')
    with Path(path).open('rb') as stream:
        while True:
            line = stream.readline(4097)
            if not line:
                break
            require(len(line) <= 4096, 'Generated header line exceeds its format bound')
            match = declaration.fullmatch(line)
            if match:
                name = match.group(1).decode('ascii')
                require(name not in arrays and len(arrays) < 256 and order is None,
                        'Duplicate or misplaced char array')
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
                    require(name == symbol and name not in order and name in arrays,
                            'Registry symbol does not resolve uniquely')
                    order.append(name)
    require(order and set(order) == set(arrays), 'Registry and char-array inventory differ')
    return arrays, order


class LayoutLiteral:
    """Parse serializer literals and retain exact top-level source byte spans."""
    PREFIX = b'ZeroSisUiLayout='
    NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?')

    def __init__(self, raw):
        require(raw.startswith(self.PREFIX) and len(raw) <= MAX_SCRIPT, 'Invalid layout assignment')
        self.text, self.pos, self.values = raw[len(self.PREFIX):].decode('ascii'), 0, 0
        self.entries = []

    def whitespace(self):
        while self.pos < len(self.text) and self.text[self.pos] in ' \t\r\n':
            self.pos += 1

    def take(self, token):
        self.whitespace()
        require(self.text.startswith(token, self.pos), 'Unexpected layout literal token')
        self.pos += len(token)

    def value(self, depth=0):
        self.whitespace();self.values += 1
        require(depth <= 64 and self.values <= 2000000 and self.pos < len(self.text),
                'Layout literal exceeded bounds')
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
                self.whitespace();start = self.pos
                if mapping:
                    self.take('[');field = self.value(depth+1);self.take(']');self.take('=')
                    require(type(field) in (str, int) and field not in result, 'Duplicate/invalid literal table key')
                    result[field] = self.value(depth+1)
                    if depth == 0:
                        self.entries.append((field, start, self.pos))
                else:
                    result.append(self.value(depth+1))
                self.whitespace()
                if self.text.startswith('}', self.pos):
                    self.take('}');return result
                self.take(',')
        for literal, value in (('true', True), ('false', False)):
            if self.text.startswith(literal, self.pos):
                self.pos += len(literal);return value
        number = self.NUMBER.match(self.text, self.pos)
        require(number, 'Layout data contains an expression, call or unsupported value')
        self.pos = number.end()
        value = float(number.group()) if any(c in number.group() for c in '.eE') else int(number.group())
        require(type(value) is int or math.isfinite(value), 'Nonfinite layout number')
        return value

    def parse(self):
        result = self.value();self.whitespace()
        require(self.pos == len(self.text) and type(result) is dict,
                'Trailing layout source or missing root table')
        return result

    def without_font_metrics(self):
        matches = [(index, row) for index, row in enumerate(self.entries) if row[0] == 'fontMetrics']
        require(len(matches) <= 1, 'Duplicate root font metrics')
        if not matches:
            return self.PREFIX + self.text.encode('ascii')
        index, (_, start, end) = matches[0]
        if index:
            start = self.entries[index-1][2]
        elif len(self.entries) > 1:
            end = self.entries[1][1]
        return self.PREFIX + (self.text[:start] + self.text[end:]).encode('ascii')


def lua_string(value):
    # Escape every non-ASCII byte so generated C++ has no source-codepage dependency.
    return '"' + ''.join(chr(b) if 32 <= b < 127 and b not in (34, 92)
                         else '\\%03d' % b for b in value.encode('utf8')) + '"'


def lua_value(value):
    if isinstance(value, str):
        return lua_string(value)
    if isinstance(value, bool):
        return 'true' if value else 'false'
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError('nonfinite number in production UI layout')
        return repr(value)
    if isinstance(value, list):
        return '{' + ','.join(lua_value(v) for v in value) + '}'
    if isinstance(value, dict):
        def key_literal(key):
            if isinstance(key, str):
                return '[' + lua_string(key) + ']'
            if isinstance(key, int) and not isinstance(key, bool) and key >= 0:
                return '[' + str(key) + ']'
            raise TypeError('unsupported Lua table key: ' + repr(key))
        return '{' + ','.join(key_literal(k) + '=' + lua_value(v)
                              for k, v in sorted(value.items(), key=lambda row: (type(row[0]).__name__, row[0]))) + '}'
    raise TypeError('unsupported Lua layout value: ' + type(value).__name__)


def serializer_source_bound(preparer, checker):
    def definitions(raw):
        result = {}
        for node in ast.parse(raw).body:
            if isinstance(node, ast.FunctionDef) and node.name in ('lua_string', 'lua_value'):
                require(node.name not in result, 'Duplicate serializer function')
                result[node.name] = ast.dump(node, include_attributes=False)
        require(set(result) == {'lua_string', 'lua_value'}, 'Missing pure serializer definitions')
        return result
    require(definitions(preparer) == definitions(checker),
            'Checker serializer is not AST-exact to the sealed preparer pure functions')


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
    names = [row[0] for row in scripts + layouts] + [
        'SharedFontMetrics', 'ZeroSisUiScene', 'ProductionCommandGuard', 'ResearchCommandGuard']
    require(len(names) == len(set(names)), 'Duplicate source catalog name')
    return names, {row[0] for row in layouts}


def xml_root(raw):
    require(b'<!DOCTYPE' not in raw.upper() and b'<!ENTITY' not in raw.upper(),
            'Original XML must not contain a DTD or entity declaration')
    return ET.fromstring(raw)


def xml_tree(raw):
    def visit(element):
        require(not element.text or not element.text.strip(), 'Unexpected mixed original XML content')
        return {'kind': element.tag, 'attributes': dict(element.attrib),
                'children': [visit(child) for child in element]}
    return visit(xml_root(raw))


def safe_integer(value, name):
    require(type(value) is int and abs(value) <= MAX_INTEGER, 'Unsafe integer metric: ' + name)
    return value


def xml_integer(attributes, name):
    raw = attributes.get(name)
    require(isinstance(raw, str) and re.fullmatch(r'[+-]?[0-9]+', raw), 'Missing/inexact original XML integer: ' + name)
    return safe_integer(int(raw), name)


def profile_inputs(profile):
    require(type(profile) is dict and set(profile) == {'schema', 'asset_root', 'fonts', 'color_atlas', 'profile_id'} and
            profile['schema'] == 'zerosis.ui.font_input_profile.v1' and is_sha(profile['profile_id']) and
            isinstance(profile['asset_root'], str) and Path(profile['asset_root']).is_absolute() and
            type(profile['fonts']) is dict and set(profile['fonts']) == FONT_IDS,
            'Invalid selected original font profile')
    payload = {name: value for name, value in profile.items() if name != 'profile_id'}
    identity = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(',', ':'),
                                        ensure_ascii=True).encode('ascii')).hexdigest()
    require(identity == profile['profile_id'], 'Font profile ID differs from its exact manifest payload')
    game_root = Path(profile['asset_root'])
    rows = [profile['color_atlas']]
    require(key(profile['color_atlas']['path']) == key(game_root / 'Assets/UI/ColorAtlas.xml'),
            'Font color atlas is not the selected original source')
    for font_id, entry in profile['fonts'].items():
        require(type(entry) is dict and set(entry) == {'ggxml', 'glyph_count', 'textures'} and
                type(entry['glyph_count']) is int and entry['glyph_count'] > 0 and
                type(entry['textures']) is dict and entry['textures'], 'Malformed selected font profile entry')
        require(key(entry['ggxml']['path']) == key(game_root / 'Assets/UI/Fonts/Tw Cent MT' / (font_id + '.ggxml')),
                'Selected GGXML source path differs')
        rows.extend((entry['ggxml'], *entry['textures'].values()))
    unique = {}
    for row in rows:
        valid_ref(row)
        identity = key(row['path'])
        require(within(row['path'], game_root) and row['bytes'] > 0 and
                (identity not in unique or unique[identity] == row), 'Aliased or escaped original font input')
        unique[identity] = row
    require(len(unique) == 15, 'Font profile must bind exactly 15 unique original inputs')
    return unique


def original_font(entry, font_id, game_root):
    root = xml_root(read_bytes(entry['ggxml']['path'], 8 * 1024 * 1024))
    require(root.tag == 'glyphgen', 'Unexpected original GGXML root')
    sections = {name: root.findall(name) for name in ('textures', 'styles', 'glyphs', 'imports')}
    require(all(len(nodes) == 1 for nodes in sections.values()), 'Missing/duplicate original GGXML section')
    textures, styles, glyphs_node, imports = (sections[name][0] for name in sections)
    require(not list(imports) and all(child.tag == 'glyph' for child in glyphs_node),
            'Imported/extended original glyph data is unsupported')
    texture_width = xml_integer(textures.attrib, 'width')
    texture_height = xml_integer(textures.attrib, 'height')
    require(texture_width > 0 and texture_height > 0, 'Invalid source font atlas size')
    texture_aliases = {}
    for texture in textures:
        alias, relative = texture.get('name'), texture.get('src')
        require(texture.tag == 'texture' and isinstance(alias, str) and alias not in texture_aliases and
                isinstance(relative, str) and not Path(relative).is_absolute() and '..' not in Path(relative).parts,
                'Invalid original font texture alias/path')
        require(alias in entry['textures'] and
                key(entry['textures'][alias]['path']) == key(game_root / relative),
                'GGXML font texture alias differs from the exact profile source')
        texture_aliases[alias] = relative
    require(set(texture_aliases) == set(entry['textures']), 'GGXML font texture aliases differ from the profile')
    style_names = set()
    for style in styles:
        name, layers = style.get('name'), style.findall('layers')
        require(style.tag == 'style' and isinstance(name, str) and name not in style_names and len(layers) == 1,
                'Invalid original GGXML style')
        names = [layer.get('tex', '') for layer in layers[0]]
        require(len(names) == xml_integer(layers[0].attrib, 'count') and names and
                all(layer.tag == 'layer' for layer in layers[0]) and
                all(alias in texture_aliases for alias in names), 'GGXML style layer identity differs')
        style_names.add(name)
    require('Base' in style_names and len(style_names) == xml_integer(styles.attrib, 'count'),
            'Original GGXML style count/Base style differs')
    vertical = {name: xml_integer(glyphs_node.attrib, name)
                for name in ('height', 'ascent', 'descent', 'ascadj', 'spacing', 'fudgeadv', 'count')}
    require(vertical['height'] > 0 and vertical['ascent'] >= 0 and vertical['descent'] >= 0,
            'Invalid original GGXML vertical metrics')
    glyphs = {}
    for glyph in glyphs_node:
        codepoint = xml_integer(glyph.attrib, 'ch')
        require(0 <= codepoint <= 0x10ffff and not 0xd800 <= codepoint <= 0xdfff and codepoint not in glyphs,
                'Duplicate/invalid original glyph codepoint')
        values = {name: xml_integer(glyph.attrib, name)
                  for name in ('u', 'v', 'width', 'height', 'a', 'b', 'c', 'originx', 'originy')}
        require(min(values['u'], values['v'], values['width'], values['height']) >= 0 and
                values['u'] + values['width'] <= texture_width and
                values['v'] + values['height'] <= texture_height, 'Original glyph lies outside its source atlas')
        glyphs[codepoint] = {'advance': safe_integer(values['a'] + values['b'] + values['c'], 'a+b+c'),
                             'width': values['width'], 'height': values['height'],
                             'originX': values['originx'], 'originY': values['originy']}
    require(len(glyphs) == vertical['count'] == entry['glyph_count'],
            'Original glyph count differs from the exact selected profile')
    digest = entry['ggxml']['sha256']
    metadata = {'lineAdvance': safe_integer(vertical['ascent'] + vertical['descent'], 'ascent+descent'),
                'baselineOffset': safe_integer(vertical['ascent'] + vertical['ascadj'], 'ascent+ascadj'),
                'spacing': vertical['spacing'], 'fudgeadv': vertical['fudgeadv'],
                'ggxmlPath': Path(entry['ggxml']['path']).relative_to(game_root).as_posix(),
                'sha256': digest, 'glyphSet': digest}
    require(metadata['lineAdvance'] > 0, 'Original font has no positive line advance')
    return metadata, glyphs


def canonical_prepared_glyphs(raw):
    require(type(raw) is dict and raw, 'Prepared shared glyph map is missing')
    result = {}
    for raw_key, glyph in raw.items():
        require(isinstance(raw_key, str) and re.fullmatch('0|[1-9][0-9]*', raw_key),
                'Prepared glyph codepoint is not canonical decimal')
        codepoint = int(raw_key)
        require(0 <= codepoint <= 0x10ffff and not 0xd800 <= codepoint <= 0xdfff and
                codepoint not in result and type(glyph) is dict and set(glyph) == GLYPH_FIELDS,
                'Prepared glyph codepoint/fields differ')
        for field, number in glyph.items():
            safe_integer(number, field)
        require(glyph['width'] >= 0 and glyph['height'] >= 0, 'Prepared glyph dimensions are negative')
        result[codepoint] = glyph
    return result


def validate_compact(metrics, profile_id, fonts, bank):
    require(type(metrics) is dict and 'glyphSets' not in metrics and
            TRANSPORT_FIELDS <= set(metrics) and metrics['glyphSetStorage'] == STORAGE_TAG and
            metrics['sharedProfileId'] == profile_id and type(metrics['glyphSetRefs']) is list and
            type(metrics.get('fonts')) is dict and metrics['fonts'], 'Invalid/mixed compact font metrics')
    require(metrics.get('policy') == 'CIV5_GLYPHGEN_GGXML_LAYOUT_V1' and
            metrics.get('retailMetricSemanticsVerified') is False, 'Changed font measurement boundary')
    refs = metrics['glyphSetRefs']
    require(refs and all(is_sha(identity) for identity in refs) and refs == sorted(set(refs)) and
            set(refs) <= set(bank), 'Missing, duplicate or unsorted compact glyph reference')
    for font_id, metadata in metrics['fonts'].items():
        require(font_id in fonts and type(metadata) is dict and metadata == fonts[font_id],
                'Compact font metadata differs from independent original GGXML: ' + str(font_id))
        for field in ('lineAdvance', 'baselineOffset', 'spacing', 'fudgeadv'):
            safe_integer(metadata[field], field)
        require(metadata['sha256'] == metadata['glyphSet'] and metadata['glyphSet'] in refs,
                'Compact font digest is not its selected glyph-set identity')
    require(refs == sorted({metadata['glyphSet'] for metadata in metrics['fonts'].values()}),
            'Compact glyph references include an unused/missing font map')


def normalized_tree(node):
    attributes = node['attributes']
    require(type(attributes) is dict or attributes == [], 'Invalid XML attribute table')
    return {'kind': node['kind'], 'attributes': {} if attributes == [] else attributes,
            'children': [normalized_tree(child) for child in node['children']]}


def walk(node):
    yield node
    for child in node['children']:
        yield from walk(child)


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
    parser.add_argument('--scope', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    scope_path, output = args.scope.absolute(), args.output.absolute()
    require(key(scope_path.parent) == key(STAGE) and scope_path.suffix == '.json',
            'Scope must be a JSON directly below the shared-font stage')
    require(key(output.parent) == key(STAGE) and
            re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}\.json', output.name) and
            key(output) != key(scope_path) and not os.path.lexists(output),
            'Receipt must be a fresh JSON directly below the shared-font stage')
    ordinary(scope_path)
    b'x'.decode('utf-8-sig')  # Warm this codec before the exact input-open guard.
    b'x'.decode('ascii');b'x'.decode('utf-8')
    counts, control = install_guard(scope_path, output)
    before, limits = {}, {}

    def allow(row):
        valid_ref(row)
        require(key(row['path']) != key(output), 'Output overlaps a sealed input')
        control['reads'].add(key(row['path']))
        return row

    def record(row, limit=MAX_HEADER):
        ref = sealed(allow(row), limit)
        identity = key(ref['path'])
        require(identity not in before or before[identity] == ref, 'Conflicting pins for the same input')
        before[identity] = ref;limits[identity] = min(limits.get(identity, limit), limit)
        return ref

    def current(path, limit=MAX_HEADER):
        require(key(path) in control['reads'], 'Current identity escaped the initial read set')
        ref = artifact(path, limit);before[key(path)] = ref;limits[key(path)] = limit
        return ref

    def source_ref(seal, relative):
        matches = [group[relative] for group in (seal['production_sources'], seal['new_assets_and_tests'])
                   if relative in group]
        require(len(matches) == 1, 'Missing/duplicate sealed source: ' + relative)
        return matches[0]

    report = {'schema': 'zerosis.goody_hut.shared_font_catalog_precompile.v1', 'status': 'FAILED_PRECONDITION',
              'scripts_executed': False, 'lua_openlibs_called': False, 'lua_pcall_called': False,
              'host_executed': False, 'gamecore_loaded': False, 'hwnd_created': False,
              'retail_user_state_accessed': False, 'additional_processes_started': 0,
              'native_acceptance_verified': False, 'default_promoted': False, 'full_engine_goal_complete': False,
              'catalog_count': 0, 'scripts': [], 'parsed_count': 0, 'failed_count': None,
              'prepared_json_limit_bytes': MAX_PREPARED, 'default_json_limit_bytes': MAX_JSON,
              'header_limit_bytes': MAX_HEADER}
    exit_code = 1
    try:
        report['scope'] = current(scope_path, MAX_JSON)
        checker_ref = current(__file__, MAX_JSON)
        scope = read_json(scope_path)
        require(type(scope) is dict and scope.get('schema') == SCOPE_SCHEMA and
                scope.get('pure_lua_dll_syntax_only_allowed') is True and
                scope.get('host_execution_allowed') is False and scope.get('gamecore_execution_allowed') is False and
                scope.get('hwnd_execution_allowed') is False and
                scope.get('retail_user_state_or_game_process_access_allowed') is False and
                scope.get('retail_mod_test_hold_active') is True and
                scope.get('expected_catalog_status') == PASS_STATUS,
                'Scope does not authorize exactly the parser-only boundary')
        for field in ('source_seal', 'font_profile', 'font_profile_helper', 'baseline_build',
                      'baseline_generated_header', 'generated_header', 'prepared_assets',
                      'pure_lua_provider', 'script_loader', 'checker', 'preparer', 'generation_run'):
            limit = MAX_PREPARED if field == 'prepared_assets' else MAX_HEADER if field in (
                'baseline_generated_header', 'generated_header') else MAX_JSON
            record(scope[field], limit)
        require(scope['checker'] == checker_ref, 'Checker differs from its explicit self pin')
        provider = scope['pure_lua_provider']
        require(provider['bytes'] == LUA_BYTES and provider['sha256'] == LUA_SHA and
                key(provider['path']) == key(PROJECT / 'Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll'),
                'Lua provider is not the approved pure parser binary')
        require(key(scope['generated_header']['path']) == key(PROJECT / 'Source/Host/UiPopupAssets.generated.h') and
                key(scope['prepared_assets']['path']) == key(PROJECT / 'evidence/ui_popup/assets/prepared.json') and
                key(scope['preparer']['path']) == key(PROJECT / 'tools/prepare_ui_popup_assets.py') and
                key(scope['font_profile']['path']) == key(PROJECT / 'Source/Assets/UI/font_input_profile.json') and
                key(scope['font_profile_helper']['path']) == key(PROJECT / 'tools/ui_font_profile.py') and
                key(scope['script_loader']['path']) == key(PROJECT / 'Source/Host/ScriptSystem.h'),
                'Current source/generated path escaped its exact workspace target')
        seal = read_json(scope['source_seal']['path'])
        require(seal.get('schema') == 'zerosis.goody_hut.shared_font_source_seal.v1' and
                type(seal.get('production_sources')) is dict and type(seal.get('new_assets_and_tests')) is dict,
                'Wrong shared-font source seal schema')
        for group in ('production_sources', 'new_assets_and_tests'):
            for relative, row in seal[group].items():
                require(isinstance(relative, str) and key(PROJECT / relative) == key(row['path']),
                        'Source seal escaped its exact workspace path')
                record(row, MAX_JSON)
        require(source_ref(seal, 'tools/prepare_ui_popup_assets.py') == scope['preparer'] and
                source_ref(seal, 'tools/ui_font_profile.py') == scope['font_profile_helper'] and
                source_ref(seal, 'Source/Assets/UI/font_input_profile.json') == scope['font_profile'] and
                seal.get('font_profile') == scope['font_profile'] and
                seal.get('generation_run') == scope['generation_run'] and
                seal.get('generated_catalog_expected_count') == 67 and
                seal.get('current_cpp_compiled_or_linked') is False and
                seal.get('current_runtime_prepared') is False and seal.get('native_acceptance') is False and
                seal.get('default_promoted') is False,
                'Font/preparer scope pins differ from the complete current source seal')
        base = read_json(scope['baseline_build']['path'])
        require(base.get('status') == 'UI_WINDOW_HOST_CANDIDATE_BUILT' and isinstance(base.get('build_id'), str),
                'Baseline does not identify an immutable built candidate')
        if 'frozen_build' in seal:
            require(seal['frozen_build'] == base['build_id'], 'Source seal names another frozen baseline')
        old_rows = [row for row in base.get('compiler_inputs', [])
                    if row.get('relative_path', '').replace('\\', '/') == 'Source/Host/UiPopupAssets.generated.h']
        require(len(old_rows) == 1 and all(scope['baseline_generated_header'][field] == old_rows[0][field]
                                         for field in ('path', 'bytes', 'sha256')),
                'Baseline header is not the exact immutable compiler input')
        generation = read_json(scope['generation_run']['path'])
        require(generation.get('schema') == 'zerosis.goody_hut.shared_font_generation.v1' and
                generation.get('status') == 'PASS' and generation.get('returncode') == 0 and
                generation.get('protected_inputs_unchanged') is True and generation.get('protected_count') == 653 and
                generation.get('actual_preparer_subprocess_result_unmodified') is True and
                generation.get('font_original_payload_copies') == 0 and
                generation.get('host_gamecore_hwnd_executed') is False and
                generation.get('retail_user_state_or_game_processes_accessed') is False and
                generation.get('default_promoted') is False, 'Generation receipt changed its preservation boundary')
        require(generation.get('targets_after') == [scope['generated_header'], scope['prepared_assets']],
                'Generated catalog/prepared identities differ from the successful actual generation')
        generation_sources = {key(row['path']): valid_ref(row) for row in generation.get('source_inputs', [])}
        for row in (scope['preparer'], scope['font_profile_helper'], scope['font_profile'],
                    source_ref(seal, 'Source/Host/UiScene.lua'),
                    source_ref(seal, 'Source/Presentation/UiPresentationInput.lua')):
            require(generation_sources.get(key(row['path'])) == row,
                    'Successful generation was not bound to the current exact source inputs')
        old_arrays, old_order = parse_catalog(scope['baseline_generated_header']['path'])
        arrays, order = parse_catalog(scope['generated_header']['path'])
        require(scope.get('baseline_catalog_count') == len(old_order) == 64 and
                scope.get('expected_catalog_count') == len(order) == 67 and
                set(order) - set(old_order) == ADDED_RECORDS and not set(old_order) - set(order) and
                [name for name in order if name not in ADDED_RECORDS] == old_order,
                'Catalog must preserve old64 names/order and add exactly Goody2 plus SharedFontMetrics1')
        prep_source = read_bytes(scope['preparer']['path'])
        serializer_source_bound(prep_source, read_bytes(__file__))
        expected_order, layout_names = declared_registry(prep_source)
        require(order == expected_order, 'Actual 67 registry names/order differ from sealed preparer declarations')
        report.update(catalog_count=len(order), baseline_catalog_count=len(old_order),
                      added_catalog_records=sorted(ADDED_RECORDS), generated_header=scope['generated_header'],
                      prepared_assets=scope['prepared_assets'], baseline_build_id=base['build_id'])
        scene = read_bytes(source_ref(seal, 'Source/Host/UiScene.lua')['path']) + b'\n' + \
            read_bytes(source_ref(seal, 'Source/Presentation/UiPresentationInput.lua')['path'])
        require(type(scope.get('scene_addenda')) is dict and
                set(scope['scene_addenda']) == {relative for _, relative in ADDENDA},
                'Expected exactly six current scene addenda')
        for flag, relative in ADDENDA:
            row = record(scope['scene_addenda'][relative], MAX_JSON)
            require(key(row['path']) == key(PROJECT / relative) and
                    generation_sources.get(key(row['path'])) == row, 'Scene addendum escaped current generation pins')
            old_source = [item for item in base.get('sources', [])
                          if item.get('relative_path', '').replace('\\', '/') == relative]
            require(len(old_source) == 1 and all(row[field] == old_source[0][field] for field in ('bytes', 'sha256')),
                    'Scene addendum differs from its preserved baseline source')
            scene += b'\nif ' + flag.encode('ascii') + b' then\n' + read_bytes(row['path']) + b'\nend\n'
        require(arrays['ZeroSisUiScene'] == scene, 'Catalog omits or changes current scene/Input/six-addenda assembly')
        loader = read_bytes(scope['script_loader']['path'])
        require(b'if(length>=3 && std::memcmp(data,"\\xef\\xbb\\xbf",3)==0){data+=3;length-=3;}' in loader,
                'Current script loader no longer has exact inspected BOM-only preprocessing')
        popup_source = read_bytes(source_ref(seal, 'Source/Host/UiPopupContext.h')['path'])
        bank_load = popup_source.find(b'!scripts_.LoadFile(vm_,"SharedFontMetrics")')
        layout_load = popup_source.find(b'!scripts_.LoadFile(vm_,kind_==UiPopupKind::GoodyHutReward?"GoodyHutRewardLayout"')
        scene_load = popup_source.find(b'!scripts_.LoadFile(vm_,"ZeroSisUiScene")')
        require(0 <= bank_load < layout_load < scene_load, 'Shared bank must load before selected layout and scene')
        profile = read_json(scope['font_profile']['path'])
        profile_rows = profile_inputs(profile)
        record(scope['owned_font_capture'])
        capture = read_json(scope['owned_font_capture']['path'])
        font_root = Path(profile['asset_root'])
        require(font_root.parent == PROJECT / 'Build/SharedUiFontInputs' and
                re.fullmatch('[0-9a-f]{64}', font_root.name) and
                capture.get('schema') == 'zerosis.ui.owned_font_inputs_capture.v1' and capture.get('status') == 'PASS' and
                capture.get('owned_profile') == profile and capture.get('cache_root') == str(font_root) and
                capture.get('content_id') == font_root.name and capture.get('source_and_cache_byte_identical') is True and
                capture.get('source_inputs_unchanged') is True and capture.get('original_game_files_modified') is False and
                capture.get('source_file_hardlinks_created') == 0,
                'Owned font capture differs from its exact selected profile')
        installed_root = Path(capture['original_profile']['asset_root'])
        require(installed_root == Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V"),
                'Captured original font root differs')
        captured_originals = profile_inputs(capture['original_profile'])
        require({key(valid_ref(row)['path']): row for row in capture['original_inputs']} == captured_originals and
                {key(valid_ref(row)['path']): row for row in capture['owned_inputs']} == profile_rows,
                'Capture receipt inventory differs from its exact profiles')
        original_inventory = sorted((Path(row['path']).relative_to(installed_root).as_posix(), row['bytes'], row['sha256'])
                                    for row in captured_originals.values())
        owned_inventory = sorted((Path(row['path']).relative_to(font_root).as_posix(), row['bytes'], row['sha256'])
                                 for row in profile_rows.values())
        require(original_inventory == owned_inventory and
                hashlib.sha256(json.dumps(owned_inventory, separators=(',', ':'), ensure_ascii=True).encode('ascii')).hexdigest() == font_root.name,
                'Owned input bytes differ from captured originals or their content address')
        require({name: row['glyph_count'] for name, row in capture['original_profile']['fonts'].items()} ==
                {name: row['glyph_count'] for name, row in profile['fonts'].items()}, 'Owned cache lost captured glyph records')
        require(type(scope.get('font_original_inputs')) is list and len(scope['font_original_inputs']) == 15,
                'Scope must declare exactly 15 original font input refs')
        explicit_rows = {}
        for row in scope['font_original_inputs']:
            valid_ref(row)
            require(key(row['path']) not in explicit_rows, 'Duplicate explicit original font input')
            explicit_rows[key(row['path'])] = row
        require(explicit_rows == profile_rows, 'Explicit original font inputs differ from the exact manifest')
        sealed_originals = seal.get('font_original_inputs')
        require(type(sealed_originals) is list and len(sealed_originals) == 15 and
                {key(valid_ref(row)['path']): row for row in sealed_originals} == explicit_rows,
                'Source seal original font inputs differ from the exact manifest/scope')
        for row in explicit_rows.values():
            record(row)
        font_metadata, bank_maps, font_counts = {}, {}, {}
        for font_id, entry in sorted(profile['fonts'].items()):
            metadata, glyphs = original_font(entry, font_id, Path(profile['asset_root']))
            identity = metadata['glyphSet']
            require(identity not in bank_maps or bank_maps[identity] == glyphs,
                    'Identical original GGXML hashes reconstructed different glyph values')
            bank_maps.setdefault(identity, glyphs)
            font_metadata[font_id] = metadata;font_counts[font_id] = len(glyphs)
        expected_bank = {'schema': BANK_SCHEMA, 'profileId': profile['profile_id'], 'glyphSets': bank_maps}
        expected_bank_bytes = ('ZeroSisUiSharedFontMetrics=' + lua_value(expected_bank) + '\n').encode('ascii')
        require(arrays['SharedFontMetrics'] == expected_bank_bytes,
                'Actual shared bank bytes differ from independently reconstructed full original glyph metrics')
        prepared = read_json(scope['prepared_assets']['path'], MAX_PREPARED)
        require(report_reference_matches(prepared.get('compiled_assets'), scope['generated_header']), 'Prepared metadata names a different header')
        prepared_profile = prepared.get('font_input_profile')
        require(type(prepared_profile) is dict and report_reference_matches(prepared_profile.get('manifest'), scope['font_profile']) and
                report_reference_matches(prepared_profile.get('helper'), scope['font_profile_helper']) and
                prepared_profile.get('profile_id') == profile['profile_id'] and
                prepared_profile.get('source_files_copied') == 0,
                'Prepared font profile provenance differs from current exact source pins')
        prepared_originals = prepared_profile.get('original_inputs')
        require(type(prepared_originals) is list and len(prepared_originals) == 15 and
                {key(valid_ref(row)['path']): row for row in prepared_originals} == explicit_rows,
                'Prepared original font provenance differs from the exact15 inputs')
        prepared_bank = prepared.get('shared_font_metrics')
        require(type(prepared_bank) is dict and set(prepared_bank) == {'schema', 'profileId', 'glyphSets'} and
                prepared_bank['schema'] == BANK_SCHEMA and prepared_bank['profileId'] == profile['profile_id'] and
                type(prepared_bank['glyphSets']) is dict and set(prepared_bank['glyphSets']) == set(bank_maps),
                'Prepared shared bank schema/profile/set inventory differs')
        for identity, glyphs in prepared_bank['glyphSets'].items():
            require(canonical_prepared_glyphs(glyphs) == bank_maps[identity],
                    'Prepared bank does not preserve every original glyph value')
        trees = prepared.get('xml_control_trees')
        require(type(trees) is dict and set(trees) == layout_names, 'Prepared layout name inventory differs')
        layouts, compact_names, layout_proof = {}, [], []
        old_fonts, old_glyph_counts, old_font_uses = {}, {}, {}
        for name in sorted(layout_names):
            require(arrays[name] == ('ZeroSisUiLayout=' + lua_value(trees[name]) + '\n').encode('ascii'),
                    'Prepared layout differs from actual catalog serialization: ' + name)
            reader = LayoutLiteral(arrays[name]);layout = reader.parse();layouts[name] = layout
            metrics = layout.get('fontMetrics')
            if metrics is not None:
                validate_compact(metrics, profile['profile_id'], font_metadata, bank_maps)
                compact_names.append(name)
            if name not in old_arrays:
                require(name == 'GoodyHutRewardLayout', 'Unexpected non-baseline layout')
                continue
            old_reader = LayoutLiteral(old_arrays[name]);old_layout = old_reader.parse()
            old_nonfont, new_nonfont = old_reader.without_font_metrics(), reader.without_font_metrics()
            require(old_nonfont == new_nonfont,
                    'An old layout changed bytes outside top-level fontMetrics: ' + name)
            old_metrics = old_layout.get('fontMetrics')
            require((old_metrics is None) == (metrics is None), 'Existing layout gained/lost its font metric contract')
            if old_metrics is not None:
                require(type(old_metrics) is dict and type(old_metrics.get('fonts')) is dict and
                        type(old_metrics.get('glyphSets')) is dict and not TRANSPORT_FIELDS & set(old_metrics),
                        'Immutable baseline is not the original inline font representation')
                old_other = {field: value for field, value in old_metrics.items() if field not in ('fonts', 'glyphSets')}
                new_other = {field: value for field, value in metrics.items()
                             if field not in {'fonts', 'glyphSets'} | TRANSPORT_FIELDS}
                require(lua_value(old_other) == lua_value(new_other),
                        'Font policy, inline icons or non-font source metadata changed: ' + name)
                require(set(old_metrics['fonts']) == set(metrics['fonts']), 'Existing layout font-ID set changed')
                old_refs = set()
                for font_id, metadata in old_metrics['fonts'].items():
                    require(font_id in font_metadata and type(metadata) is dict and is_sha(metadata.get('sha256')) and
                            metadata.get('glyphSet') == metadata['sha256'] and
                            metadata.get('ggxmlPath') == font_metadata[font_id]['ggxmlPath'] and
                            (font_id not in old_fonts or old_fonts[font_id] == metadata),
                            'Baseline font source identity/path is inconsistent')
                    old_fonts[font_id] = metadata;old_refs.add(metadata['glyphSet'])
                    old_font_uses.setdefault(font_id, []).append(name)
                require(set(old_metrics['glyphSets']) == old_refs, 'Baseline inline map inventory differs from its fonts')
                for identity, glyphs in old_metrics['glyphSets'].items():
                    require(type(glyphs) is dict and glyphs and
                            (identity not in old_glyph_counts or old_glyph_counts[identity] == len(glyphs)),
                            'Baseline inline glyph count is inconsistent')
                    old_glyph_counts[identity] = len(glyphs)
            layout_proof.append({'name': name, 'non_font_serialized_bytes': len(new_nonfont),
                                 'non_font_sha256': hashlib.sha256(new_nonfont).hexdigest(),
                                 'non_font_bytes_exact': True})
        require(set(old_fonts) == FONT_IDS and
                {font_id for name in compact_names for font_id in layouts[name]['fontMetrics']['fonts']} == FONT_IDS and
                {identity for name in compact_names for identity in layouts[name]['fontMetrics']['glyphSetRefs']} == set(bank_maps),
                'Old/current font union or bank use differs from the exact six selected originals')
        for name in old_order:
            if name not in layout_names and name != 'ZeroSisUiScene':
                require(arrays[name] == old_arrays[name], 'An unchanged original/guard script changed: ' + name)
        originals = {}
        for group, names in (('original_goody_assets', ('GoodyHutPopup.lua', 'GoodyHutPopup.xml')),
                             ('original_pantheon_assets', ('ChoosePantheonPopup.lua', 'ChoosePantheonPopup.xml'))):
            require(type(scope.get(group)) is dict and set(scope[group]) == {'lua', 'xml'},
                    'Original popup group needs exact Lua/XML refs')
            originals[group] = {}
            for field, filename in zip(('lua', 'xml'), names):
                row = record(scope[group][field], MAX_JSON)
                relative = 'Assets/DLC/Expansion2/UI/InGame/Popups/' + filename
                require(key(row['path']) == key(installed_root / relative),
                        'Original popup source is not the exact installed static path')
                copied = PROJECT / 'Source/Assets/UI' / relative
                record({'path': str(copied), 'bytes': row['bytes'], 'sha256': row['sha256']}, MAX_JSON)
                originals[group][field] = row
        goody, pantheon = originals['original_goody_assets'], originals['original_pantheon_assets']
        require(arrays['GoodyHutPopup'] == read_bytes(goody['lua']['path']) and
                arrays['ChoosePantheonPopup'] == read_bytes(pantheon['lua']['path']),
                'Actual original Goody/Pantheon Lua bytes differ')
        goody_layout, pantheon_layout = layouts['GoodyHutRewardLayout'], layouts['PantheonLayout']
        original_tree = xml_tree(read_bytes(goody['xml']['path']))
        require(normalized_tree(goody_layout) == original_tree and
                (goody_layout.get('contextName'), goody_layout.get('popupKind')) == ('GoodyHutPopup', 'GoodyHutReward'),
                'Goody layout changed original XML tree/context identity')
        nodes = list(walk(original_tree));close = [node for node in nodes if node['attributes'].get('ID') == 'CloseButton']
        require(len(nodes) == 12 and len(close) == 1 and close[0]['kind'] == 'GridButton' and
                close[0]['attributes'].get('Size') == '200,36' and close[0]['attributes'].get('Anchor') == 'C,B' and
                close[0]['attributes'].get('AnchorSide') == 'I.O' and close[0]['attributes'].get('Offset') == '0,0',
                'Original Goody12 controls/unique outside-grid CloseButton changed')
        goody_metadata, pantheon_metadata = goody_layout.get('goodyHutReward'), pantheon_layout.get('pantheon')
        require(type(goody_metadata) is dict and
                goody_metadata.get('policy') == 'ORIGINAL_BNW_GOODY_HUT_REWARD_INFORMATIONAL_V1' and
                goody_metadata.get('originalLayoutLua') == goody['lua'] and
                goody_metadata.get('originalLayoutXml') == goody['xml'] and
                goody_metadata.get('rewardAlreadyApplied') is True and
                goody_metadata.get('nativeAcceptanceVerified') is False, 'Goody original provenance/native boundary differs')
        require(type(pantheon_metadata) is dict and
                pantheon_metadata.get('policy') == 'ORIGINAL_BNW_PANTHEON_ONLY_V1' and
                pantheon_metadata.get('originalLayoutLua') == pantheon['lua'] and
                pantheon_metadata.get('originalLayoutXml') == pantheon['xml'],
                'Pantheon original Lua/XML source provenance differs')
        styles = goody_layout.get('styleDefaultsSource')
        require(type(styles) is dict and set(styles) == {'path', 'sha256'} and
                styles['path'] == 'Assets/UI/Styles.xml' and is_sha(styles['sha256']) and
                styles == pantheon_layout.get('styleDefaultsSource'),
                'Goody/Pantheon original Styles.xml provenance differs')
        # The production style record deliberately uses a game-relative path.
        frozen_style = PROJECT / 'Source/Assets/UI' / styles['path']
        style_bytes = ordinary(frozen_style).st_size
        for style_path in (frozen_style, installed_root / styles['path']):
            record({'path': str(style_path), 'bytes': style_bytes, 'sha256': styles['sha256']},
                   4 * 1024 * 1024)
        transitions = []
        for font_id in sorted(FONT_IDS):
            old, new = old_fonts[font_id], font_metadata[font_id]
            transitions.append({'font_id': font_id, 'original_ggxml_path_unchanged': True,
                                'baseline_metadata': old, 'current_metadata': new,
                                'baseline_glyph_count': old_glyph_counts[old['glyphSet']],
                                'current_glyph_count': font_counts[font_id],
                                'changed_source_sha256': old['sha256'] != new['sha256']})
        # The current installation may legitimately match the baseline font bytes.
        report['source_binding'] = {
            'exact_current_scene_input_and_six_addenda': True, 'shared_bank_loaded_before_layout': True,
            'exact_catalog_names_and_order_from_source': True, 'serializer_ast_exact_to_sealed_preparer': True,
            'original_goody_lua_bytes_exact': True, 'original_goody_xml_tree_exact': True,
            'goody_control_count': len(nodes), 'unique_original_close_button': True,
            'goody_metadata_source_bound': True, 'original_pantheon_lua_bytes_exact': True,
            'original_goody_and_pantheon_xml_snapshots_bytes_exact': True,
            'all_old_layout_geometry_style_and_provenance_serialized_bytes_exact': True,
            'all_old_non_scene_original_scripts_bytes_exact': True,
            'utf8_bom_rule_bound_to_current_script_loader': True,
            'prepared_matches_actual_catalog': True,
        }
        report['font_profile_transition'] = {
            'full_pantheon_layout_byte_equality_claimed': False,
            'comparison': 'EXACT_NON_FONT_SERIALIZED_LAYOUT_BYTES_PLUS_EXPLICIT_FONT_PROFILE_TRANSITION',
            'baseline_profile_basis': 'IMMUTABLE_BASELINE_CATALOG_INLINE_METADATA_AND_GLYPH_COUNTS',
            'baseline_font_profile_manifest_available': False,
            'current_profile_manifest': scope['font_profile'], 'current_profile_id': profile['profile_id'],
            'original_abc_components_read_as_exact_integers': True,
            'all_original_abc_sums_and_retained_glyph_metrics_independently_verified': True,
            'all_original_integer_metrics_within_binary64_exact_integer_range': True,
            'shared_bank_bytes_exact_to_independent_original_metrics': True,
            'prepared_bank_values_exact_to_independent_original_metrics': True,
            'original_font_files_preserved': True, 'original_payload_files_copied': len(capture['copied_inputs']),
            'owned_font_capture': scope['owned_font_capture'], 'owned_font_input_root': str(font_root),
            'live_installed_font_dependency': False,
            'selected_original_input_count': len(explicit_rows), 'selected_font_count': len(font_metadata),
            'unique_glyph_set_count': len(bank_maps), 'unique_glyph_count': sum(map(len, bank_maps.values())),
            'glyph_counts_by_font': font_counts, 'fonts': transitions,
            'runtime_full_glyph_walk_added': False,
        }
        report['old_layout_non_font_proof'] = layout_proof
        report['compact_layouts_verified'] = compact_names
        report['scripts'] = parse_scripts(provider, arrays, order, control)
        failed = sum(row['lua_status'] != 0 for row in report['scripts'])
        report.update(parsed_count=len(report['scripts']), failed_count=failed)
        require(report['parsed_count'] == 67, 'Lua parser did not inspect every actual catalog script')
        report['status'] = PASS_STATUS if not failed else 'FAILED_SHARED_FONT_CATALOG_LUA51_PARSE_ONLY'
        exit_code = 0 if not failed else 1
    except Exception as error:
        report['error_type'] = type(error).__name__
        report['error'] = str(error)[:240] if isinstance(error, (ValueError, PermissionError)) else \
            'Bounded shared-font catalog precompile check failed'
    try:
        require(before, 'No input seal was established')
        report['inputs_before'] = list(before.values())
        report['inputs_after'] = [sealed(row, limits[identity]) for identity, row in before.items()]
        report['inputs_unchanged'] = report['inputs_before'] == report['inputs_after']
        require(report['inputs_unchanged'], 'Input preservation check failed')
        require(not any(value for name, value in counts.items() if name.startswith('blocked_')),
                'A forbidden operation was attempted')
        if exit_code == 0:
            require(counts['explicit_lua_provider_loads'] == 1 and control['symbols'] == PARSER_FUNCTIONS,
                    'Parser-only DLL/symbol boundary changed')
    except Exception as error:
        exit_code = 1;report['status'] = 'FAILED_INPUT_PRESERVATION_OR_AUDIT_GUARD'
        report['preservation_error_type'] = type(error).__name__;report['inputs_unchanged'] = False
    report['guard'] = counts
    report['resolved_parser_functions'] = sorted(control['symbols'])
    report['receipt_write_policy'] = 'ONE_FRESH_EXCLUSIVE_JSON_DIRECTLY_BELOW_SHARED_FONT_STAGE'
    encoded = json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2) + '\n'
    require(len(encoded.encode('utf-8')) <= 256 * 1024, 'Catalog receipt exceeded its bounded size')
    with output.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(encoded)
    print(json.dumps({'status': report['status'], 'exit_code': exit_code, 'catalog_count': report['catalog_count'],
                      'failed_count': report['failed_count'], 'report': str(output)}, ensure_ascii=False))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
