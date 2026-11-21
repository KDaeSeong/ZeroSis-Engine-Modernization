"""Append original civilian idle t=0 geometry to the sealed animated Warrior v2.

Pure asset preparation: no helper launch, DLL loading, Host, SDK GameCore, GPU,
window, retail MODS, saves or settings access. Original archives are read only
through their bounded indexes and selected records, never whole-FPK hashing.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat
import struct
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
import pack_unit_models as original_math
from civ5_ui_assets import Fpk
import unit_animation_assets

PROJECT = Path(__file__).absolute().parents[1]
GAME = original_math.DEFAULT_GAME
SCOPE = PROJECT / 'evidence/unit_models/civilian_start/scope.json'
SCOPE_SHA = '943746d6cc04cd175bc5f63d95bbf94d7bc0efd6a186bfabd2578a1444853785'
BASE_SHA = '480678966a78bedbee642040285010aa86f8a2cc34b0929c2774dcee8ab54266'
BASE_MANIFEST_SHA = 'd6df7f9123075e7cd328712c968b1ef8023f1e32da16ced2d95651f4ffa0c3f1'
BASE_ROOT = PROJECT / 'Build/UnitAssets' / BASE_SHA
BASE_MANIFEST = BASE_ROOT / 'unit-assets.manifest.json'
BASE_PACKAGE = BASE_ROOT / 'unit-assets.bin'
SHARED_GSD = PROJECT / 'Build/StockUnitExports/20261005T072135Z/unitmodels_stringdatabase.gsd'
GSD_SHA = 'f063955e71728fc76fdc097b9759e291f203c895d32f5f6eeaf5e4f78f73a959'
HELPER = PROJECT / 'Build/UnitModelTools/stock_e473bff5e7a5185057d5/StockUnitExporter.exe'
HELPER_SHA = '2dec7239b15eaecfec63727a0c4232ae8c1653cb9f5c8e45050a959e7aa76812'
PRIVATE_SDK = HELPER.parent
MODEL_FPK = GAME / 'Resource/Common/UnitModels.fpk'
TEXTURE_FPK = GAME / 'Resource/DX9/UnitsTextures.fpk'
XML_FILES = (GAME / 'Assets/Units/Civ5ArtDefines_Units.xml',
             GAME / 'Assets/Units/Civ5ArtDefines_UnitMembers.xml',
             GAME / 'Assets/Gameplay/XML/Civilizations/CIV5Civilizations.xml')
FORMATION_XML = GAME / 'Assets/Units/UnitFormations.xml'
SETTLER_MEMBERS = tuple('ART_DEF_UNIT_MEMBER_' + name for name in (
    'EURODONKEY', 'EUROFEMALE18', 'EUROFEMALE25', 'EUROFEMALE35', 'EUROFEMALE40',
    'EUROMALE20', 'EUROMALE25', 'EUROMALE35', 'EUROMALE45'))
UNITS = (
    {'art_tag': 'ART_DEF_UNIT__SETTLER', 'formation_original': 'LooseCivilian',
     'members': [{'member_type': name, 'member_count': 1, 'scale': 0.12} for name in SETTLER_MEMBERS]},
    {'art_tag': 'ART_DEF_UNIT__WORKER', 'formation_original': 'LooseCivilian',
     'members': [{'member_type': 'ART_DEF_UNIT_MEMBER_WORKER_EURO', 'member_count': 8, 'scale': 0.14}]},
)
FORMATION_KEYS = ('SpacingX', 'SpacingY', 'SpacingMultiplier', 'PerRowInc', 'YOffsetInc',
                  'YOffsetCurved', 'Stagger', 'UnitRandomness', 'BlockRandomness', 'TotalWidth',
                  'XBlockSize', 'XBlockSpacingCount', 'YBlockSize', 'YBlockSpacingCount', 'CenterWidth')
MAX_PACKAGE = 64 * 1024 * 1024
MAX_JSON = 64 * 1024 * 1024
MAX_SELECTED = 64 * 1024 * 1024
MAX_INDEX = 32 * 1024 * 1024
SHA = re.compile(r'[0-9a-f]{64}')
TAG = re.compile(r'[A-Z0-9_]{1,256}')
CODE_INPUTS = (
    'tools/append_civilian_unit_models.py', 'tools/export_civilian_units.py',
    'tools/pack_unit_models.py', 'tools/civ5_ui_assets.py', 'tools/unit_animation_assets.py',
    'tools/StockUnitExporter.cs', 'Source/Presentation/WorldUnitAssets.h', 'Source/Animation/UnitAnimation.h',
)


def require(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def path_key(path):
    return os.path.normcase(os.path.abspath(path))


def checked_file(path, parent=None):
    path = Path(os.path.abspath(path))
    require(path.resolve(strict=True) == path, 'Input resolves through another path: ' + str(path))
    if parent is not None:
        require(path.is_relative_to(parent) and path != parent, 'Input escaped its declared root')
    for item in (path, *path.parents):
        info = item.lstat()
        require(not getattr(info, 'st_file_attributes', 0) & 0x400 and not stat.S_ISLNK(info.st_mode), 'Reparse input: ' + str(item))
        if item == PROJECT or item == GAME:
            break
    require(stat.S_ISREG(path.lstat().st_mode), 'Input is not an ordinary file')
    return path


def metadata(path):
    info = checked_file(path).stat()
    require(info.st_ino and info.st_size >= 0, 'Input has no stable identity')
    return {'path': str(Path(path)), 'device': info.st_dev, 'file_id': info.st_ino,
            'bytes': info.st_size, 'mtime_ns': info.st_mtime_ns}


def matches_open_file(info, expected):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns) == (
        expected['device'], expected['file_id'], expected['bytes'], expected['mtime_ns'])


def bounded_bytes(path, limit, allow_empty=False):
    path = checked_file(path)
    before = metadata(path)
    require((0 if allow_empty else 1) <= before['bytes'] <= limit, 'Input exceeds its byte bound: ' + str(path))
    with path.open('rb') as stream:
        require(matches_open_file(os.fstat(stream.fileno()), before), 'Input open resolved to another identity')
        data = stream.read(limit + 1)
        require(matches_open_file(os.fstat(stream.fileno()), before), 'Opened input changed while reading')
    require(len(data) == before['bytes'] and metadata(path) == before, 'Input changed while reading')
    return data


def artifact(path, limit=MAX_JSON):
    data = bounded_bytes(path, limit)
    return {'path': str(Path(path)), 'bytes': len(data), 'sha256': digest(data)}


def json_document(path):
    data = bounded_bytes(path, MAX_JSON)
    value = json.loads(data.decode('utf-8-sig'))
    require(isinstance(value, dict), 'JSON root must be an object')
    return value


def verify_artifact(row, parent=None, limit=MAX_JSON, allow_empty=False):
    require(isinstance(row, dict) and isinstance(row.get('path'), str) and
            SHA.fullmatch(str(row.get('sha256', ''))), 'Invalid sealed artifact')
    path = checked_file(row['path'], parent)
    observed = metadata(path)
    require(all(observed[k] == row[k] for k in ('device', 'file_id', 'mtime_ns') if k in row), 'Sealed artifact identity/mtime differs')
    data = bounded_bytes(path, limit, allow_empty)
    require(len(data) == row.get('bytes') and digest(data) == row['sha256'], 'Sealed artifact differs: ' + str(path))
    return data


def finite(value, label):
    require(isinstance(value, (int, float)) and not isinstance(value, bool), 'Not a number: ' + label)
    value = float(value)
    require(math.isfinite(value), 'Nonfinite value: ' + label)
    return value


def integer(value, low, high, label):
    require(isinstance(value, int) and not isinstance(value, bool) and low <= value <= high, 'Invalid integer: ' + label)
    return value


def vector(value, size, label):
    require(isinstance(value, list) and len(value) == size, 'Invalid array: ' + label)
    return [finite(item, label) for item in value]


class Reader:
    def __init__(self, data):
        require(isinstance(data, bytes) and 20 <= len(data) <= MAX_PACKAGE, 'Invalid package size')
        self.data, self.at = data, 0

    def take(self, count):
        require(isinstance(count, int) and 0 <= count <= len(self.data) - self.at, 'Truncated unit package')
        start = self.at
        self.at += count
        return self.data[start:self.at]

    def u32(self, high=0xffffffff, low=0):
        value, = struct.unpack('<I', self.take(4))
        require(low <= value <= high, 'Unit package count/reference exceeds its bound')
        return value

    def f32(self):
        value, = struct.unpack('<f', self.take(4))
        require(math.isfinite(value), 'Nonfinite unit package float')
        return value

    def text(self, maximum, art=False):
        text = self.take(self.u32(maximum, 1)).decode('ascii')
        require(all(0x20 <= ord(c) <= 0x7e for c in text), 'Invalid package ASCII')
        if art:
            require(TAG.fullmatch(text), 'Invalid unit art identifier')
        return text


def parse_package(data):
    """Bound the complete v2 layout without loading any rendering/runtime code."""
    r = Reader(data)
    require(r.take(8) == b'ZSUNIT02' and r.u32() == 2, 'Expected ZSUNIT02 version 2')
    textures, arts, art_names = [], [], set()
    texture_count = r.u32(64, 1)
    for index in range(texture_count):
        start = r.at
        dds = r.take(r.u32(16 * 1024 * 1024, 128))
        info = original_math.dds_info(dds, 'package texture ' + str(index))
        textures.append({'raw': data[start:r.at], 'payload': dds, 'info': info, 'offset': start})
    art_count_offset = r.at
    art_count = r.u32(64, 1)
    total_vertices = total_indices = 0
    for unused in range(art_count):
        start = r.at
        tag = r.text(256, art=True)
        require(tag not in art_names, 'Duplicate unit art identifier')
        art_names.add(tag)
        meshes = []
        for unused_mesh in range(r.u32(128, 1)):
            mesh_start = r.at
            texture = r.u32(texture_count - 1)
            vc, ic = r.u32(200000, 1), r.u32(600000, 1)
            require(ic % 3 == 0, 'Triangle index count is not divisible by three')
            total_vertices += vc
            total_indices += ic
            require(total_vertices <= 1000000 and total_indices <= 3000000, 'Aggregate unit geometry exceeds its bound')
            vertex_offset = r.at
            vertices = r.take(vc * 32)
            for v in struct.iter_unpack('<8f', vertices):
                require(all(math.isfinite(x) and abs(x) <= 10000 for x in v) and
                        all(abs(x) <= 2 for x in v[:3]), 'Nonfinite or unbounded static geometry')
                require(0.5 <= sum(x*x for x in v[3:6]) <= 1.5, 'Invalid static normal')
            index_offset = r.at
            indices = r.take(ic * 4)
            require(all(i[0] < vc for i in struct.iter_unpack('<I', indices)), 'Static index exceeds its mesh')
            meshes.append({'texture': texture, 'vertices': vc, 'indices': ic, 'offset': mesh_start,
                           'vertex_offset': vertex_offset, 'index_offset': index_offset})
        arts.append({'tag': tag, 'meshes': meshes, 'raw': data[start:r.at], 'offset': start})
    extension_offset = r.at
    files, names = [], set()
    file_count = r.u32(16, 1)
    for unused in range(file_count):
        name = r.text(128)
        require(name not in ('.', '..') and not any(x in name for x in '/\\:') and '.' in name and
                name.casefold() not in names, 'Unsafe/duplicate embedded filename')
        names.add(name.casefold())
        offset = r.at + 4
        payload = r.take(r.u32(32 * 1024 * 1024, 1))
        files.append({'name': name, 'bytes': len(payload), 'sha256': digest(payload), 'payload_offset': offset})
    rig_bones, parent_offsets = [], []
    rig_count = r.u32(16, 1)
    for unused in range(rig_count):
        for role in range(3):
            r.u32(file_count - 1)
        r.u32(1)
        require(0 < r.f32() <= 3600, 'Invalid animation duration')
        bone_count = r.u32(512, 1)
        parents, bone_names = [], set()
        for bi in range(bone_count):
            name = r.text(128)
            require(name not in bone_names, 'Duplicate skeleton bone')
            bone_names.add(name)
            parent_offsets.append(r.at)
            parent, = struct.unpack('<i', r.take(4))
            require(-1 <= parent < bone_count and parent != bi, 'Invalid skeleton parent')
            parents.append(parent)
            for unused_float in range(19):
                r.f32()  # inverse matrix + local position
            quaternion = [r.f32() for unused_float in range(4)]
            require(0.9801 <= sum(x*x for x in quaternion) <= 1.0201, 'Invalid bind quaternion')
            for unused_float in range(9):
                r.f32()
        for bi in range(bone_count):
            visited, parent = set(), bi
            while parent != -1:
                require(parent not in visited, 'Skeleton cycle')
                visited.add(parent)
                parent = parents[parent]
        rig_bones.append(bone_count)
    animated_offset = r.at
    animated_count = r.u32(4096, 1)
    animated_vertices = 0
    mapped, first_weight_offset = set(), None
    for unused in range(animated_count):
        art, mesh, rig, slot = r.u32(art_count - 1), r.u32(), r.u32(rig_count - 1), r.u32(11)
        vc = r.u32(200000, 1)
        animated_vertices += vc
        require(mesh < len(arts[art]['meshes']) and vc == arts[art]['meshes'][mesh]['vertices'] and
                (art, mesh) not in mapped, 'Invalid/duplicate animated mesh mapping')
        mapped.add((art, mesh))
        if first_weight_offset is None:
            first_weight_offset = r.at + 48
        for vertex in struct.iter_unpack('<8f4I4B', r.take(vc * 52)):
            require(all(math.isfinite(x) for x in vertex[:8]) and all(i < rig_bones[rig] for i in vertex[8:12])
                    and sum(vertex[12:]) == 255, 'Invalid animated vertex/bone/weights')
    require(r.at == len(data), 'Trailing unit package bytes')
    return {'textures': textures, 'arts': arts, 'art_count_offset': art_count_offset,
            'vertices': total_vertices, 'indices': total_indices, 'extension_offset': extension_offset,
            'extension': data[extension_offset:], 'files': files, 'rig_bones': rig_bones,
            'animated_count': animated_count, 'animated_vertices': animated_vertices, 'animated_offset': animated_offset,
            'parent_offsets': parent_offsets, 'first_weight_offset': first_weight_offset}


def assert_preserved(base, candidate):
    require(len(candidate['textures']) >= 3 and len(candidate['arts']) == 3, 'Civilian composition has an invalid table layout')
    require([x['raw'] for x in candidate['textures'][:3]] == [x['raw'] for x in base['textures']], 'Existing DDS records changed')
    require(candidate['arts'][0]['raw'] == base['arts'][0]['raw'], 'Existing Warrior art/mesh/float/index records changed')
    require(candidate['extension'] == base['extension'] and len(candidate['extension']) == 793226,
            'Existing animation extension changed')
    require([x['tag'] for x in candidate['arts']] == ['ART_DEF_UNIT__WARRIOR', *(x['art_tag'] for x in UNITS)],
            'Original/new art ordering differs')


def parser_regressions(base_data, base, composed_data, composed):
    """Meaningful rejection checks execute only when the owning CLI is run."""
    rejected = []
    def reject(name, payload):
        try:
            parse_package(payload)
        except (ValueError, UnicodeError, struct.error):
            rejected.append(name)
            return
        raise ValueError('Malformed binary was accepted: ' + name)
    def replace(offset, content):
        data = bytearray(base_data)
        data[offset:offset + len(content)] = content
        return bytes(data)
    reject('truncated_header', base_data[:10])
    reject('wrong_magic', replace(0, b'NOTUNIT2'))
    reject('unbounded_texture_count', replace(12, struct.pack('<I', 0xffffffff)))
    reject('short_dds', replace(16, struct.pack('<I', 127)))
    reject('zero_art_count', replace(base['art_count_offset'], struct.pack('<I', 0)))
    reject('invalid_art_tag', replace(base['arts'][0]['offset'] + 4, b'a'))
    mesh = base['arts'][0]['meshes'][0]
    reject('invalid_texture_reference', replace(mesh['offset'], struct.pack('<I', len(base['textures']))))
    reject('nonfinite_vertex', replace(mesh['vertex_offset'], struct.pack('<f', float('nan'))))
    reject('outside_tile_vertex', replace(mesh['vertex_offset'], struct.pack('<f', 3)))
    reject('invalid_triangle_index', replace(mesh['index_offset'], struct.pack('<I', mesh['vertices'])))
    reject('unbounded_embedded_file_count', replace(base['extension_offset'], struct.pack('<I', 17)))
    reject('unsafe_embedded_name', replace(base['extension_offset'] + 8, b'/'))
    reject('self_parent_bone', replace(base['parent_offsets'][0], struct.pack('<i', 0)))
    reject('invalid_animated_art', replace(base['animated_offset'] + 4, struct.pack('<I', 1)))
    reject('invalid_animated_weight_sum', replace(base['first_weight_offset'], bytes(4)))
    reject('trailing_record', base_data + b'\0')
    preservation = []
    for name, offset, patch in (
        ('dds_payload_change', composed['textures'][0]['offset'] + len(composed['textures'][0]['raw']) - 1, b'\x93'),
        ('warrior_uv_change', composed['arts'][0]['meshes'][0]['vertex_offset'] + 24, struct.pack('<f', 0.123456)),
        ('embedded_model_byte_change', composed['files'][1]['payload_offset'], b'\x17')):
        altered = bytearray(composed_data)
        if bytes(altered[offset:offset + len(patch)]) == patch:
            patch = bytes([patch[0] ^ 1]) + patch[1:]
        altered[offset:offset + len(patch)] = patch
        try:
            assert_preserved(base, parse_package(bytes(altered)))
        except (ValueError, UnicodeError, struct.error):
            preservation.append(name)
        else:
            raise ValueError('Changed preserved content was accepted: ' + name)
    return {'malformed_binary_rejections': rejected, 'preserved_content_mutation_rejections': preservation,
            'valid_base_and_composition_parsed': True, 'native_or_gpu_execution': False}


def origin_key(row):
    require(isinstance(row, dict) and isinstance(row.get('pack_path'), str) and isinstance(row.get('entry'), str)
            and SHA.fullmatch(str(row.get('sha256', ''))), 'Invalid selected FPK record')
    integer(row.get('bytes'), 1, MAX_SELECTED, 'selected bytes')
    integer(row.get('offset'), 0, 0xffffffff, 'selected offset')
    require(path_key(row['pack_path']) in {path_key(MODEL_FPK), path_key(TEXTURE_FPK)}, 'Selected record escaped authorized archives')
    return path_key(row['pack_path']), row['entry'].casefold()


def archive_seals(expected, wanted):
    require(isinstance(expected, list) and len(expected) == 2, 'Expected two selected-archive seals')
    observed, payloads, packs = [], {}, {}
    total = 0
    for path, seal in zip((MODEL_FPK, TEXTURE_FPK), expected):
        require(path_key(seal.get('path', '')) == path_key(path), 'Archive seal order/path differs')
        before = metadata(path)
        require(all(before[k] == seal.get(k) for k in before), 'Archive identity/metadata changed')
        pack = Fpk(path)
        packs[path_key(path)] = pack
        require(pack.table_end <= MAX_INDEX and pack.table_end == seal.get('index_bytes'), 'Archive index length changed')
        with path.open('rb') as stream:
            require(matches_open_file(os.fstat(stream.fileno()), before), 'Archive index open identity changed')
            index = stream.read(pack.table_end)
            require(matches_open_file(os.fstat(stream.fileno()), before), 'Opened archive changed while reading its index')
        require(len(index) == pack.table_end and digest(index) == seal.get('index_sha256'), 'Archive index changed')
        selected = seal.get('selected')
        require(isinstance(selected, list) and selected == sorted(selected, key=lambda row: row['entry'].casefold()), 'Selected archive records are not ordered')
        expected_names = {entry for pack_name, entry in wanted if pack_name == path_key(path)}
        require({row['entry'].casefold() for row in selected} == expected_names and len(selected) == len(expected_names), 'Missing or unexpected selected archive record')
        current = []
        for item in selected:
            target = wanted[(path_key(path), item['entry'].casefold())]
            require(all(item.get(k) == target[k] for k in ('entry', 'offset', 'bytes', 'sha256')), 'Selected seal differs from source origin')
            entry = pack.entries.get(item['entry'].casefold())
            require(entry and entry.name == item['entry'] and entry.offset == item['offset'] and entry.size == item['bytes'], 'Selected record no longer matches archive index')
            total += entry.size
            require(total <= MAX_SELECTED, 'Selected archive closure exceeds 64 MiB')
            with path.open('rb') as stream:
                require(matches_open_file(os.fstat(stream.fileno()), before), 'Selected archive open identity changed')
                stream.seek(entry.offset)
                payload = stream.read(entry.size)
                require(len(payload) == entry.size and matches_open_file(os.fstat(stream.fileno()), before), 'Selected archive body changed while reading')
            actual = {'entry': entry.name, 'offset': entry.offset, 'bytes': len(payload), 'sha256': digest(payload)}
            require(all(actual[k] == target[k] for k in ('entry', 'offset', 'bytes', 'sha256')), 'Selected archive payload changed')
            payloads[(path_key(path), item['entry'].casefold())] = payload
            current.append({k: actual[k] for k in ('entry', 'offset', 'bytes', 'sha256')})
        require(metadata(path) == before, 'Archive changed while reading selected records')
        observed.append({**before, 'index_bytes': pack.table_end, 'index_sha256': digest(index), 'selected': current})
    return observed, payloads, packs


def small_xml_seals(rows):
    require(isinstance(rows, list) and len(rows) == 3, 'Expected Units/UnitMembers/Civilizations XML seals')
    observed, documents = [], []
    for path, row in zip(XML_FILES, rows):
        require(path_key(row.get('path', '')) == path_key(path), 'Unexpected original XML path/order')
        before = metadata(path)
        require(all(before[k] == row.get(k) for k in before), 'Original XML identity/metadata changed')
        data = bounded_bytes(path, 4 * 1024 * 1024)
        require(digest(data) == row.get('sha256'), 'Original XML content changed')
        observed.append({**before, 'sha256': digest(data)})
        documents.append(ET.fromstring(data))
    return observed, documents


def validate_xml_units(documents, units):
    require(units == list(UNITS), 'Civilian unit/member order, count or scale differs from scope')
    unit_root, member_root, civilization_root = documents
    members = {}
    for unit in UNITS:
        matching = [row for row in unit_root.findall('.//UnitArtInfo') if row.findtext('Type') == unit['art_tag']]
        require(len(matching) == 1 and matching[0].findtext('Formation') == 'LooseCivilian', 'Original civilian art/formation differs')
        actual = [(row.findtext('MemberType'), int(row.findtext('MemberCount', '0'))) for row in matching[0].findall('UnitMemberArt')]
        require(actual == [(x['member_type'], x['member_count']) for x in unit['members']], 'Original member order/count differs')
        for member in unit['members']:
            rows = [row for row in member_root.findall('.//UnitMemberArtInfo') if row.findtext('Type') == member['member_type']]
            require(len(rows) == 1, 'Missing/duplicate original civilian member')
            row = rows[0]
            require(abs(finite(float(row.findtext('fScale', 'nan')), 'original member scale') - member['scale']) < 1e-9,
                    'Original civilian scale differs')
            members[member['member_type']] = {'fxsxml': row.findtext('Granny', ''), **member}
    americans = [row for row in civilization_root.findall('.//Civilizations/Row') if row.findtext('Type') == 'CIVILIZATION_AMERICA']
    require(len(americans) == 1 and americans[0].findtext('ArtStyleType') == 'ARTSTYLE_EUROPEAN' and
            americans[0].findtext('ArtStyleSuffix') == '_EURO' and
            americans[0].findtext('ArtStylePrefix', '').strip() == 'EUROPEAN', 'Grounded initial American art-style source differs')
    return members


def formation_record():
    before = {**metadata(FORMATION_XML), **artifact(FORMATION_XML, 4 * 1024 * 1024)}
    root = ET.fromstring(bounded_bytes(FORMATION_XML, 4 * 1024 * 1024))
    matches = [row for row in root.findall('.//Formation') if row.findtext('Name') == 'LooseCivilian']
    require(len(matches) == 1, 'LooseCivilian formation source is missing/ambiguous')
    values = {name: matches[0].findtext(name) for name in FORMATION_KEYS}
    require(all(value is not None for value in values.values()), 'Incomplete LooseCivilian formation')
    require(float(values['SpacingX']) == 12 and float(values['SpacingY']) == 14 and int(values['TotalWidth']) == 4,
            'Original LooseCivilian spacing differs')
    require({**metadata(FORMATION_XML), **artifact(FORMATION_XML, 4 * 1024 * 1024)} == before, 'Formation input changed during read')
    return values, before


def pose_from_curves(exported):
    require(isinstance(exported.get('models'), list) and len(exported['models']) == 1, 'Expected one exported original model')
    bones = exported['models'][0].get('bones')
    require(isinstance(bones, list) and 0 < len(bones) <= 512, 'Invalid civilian skeleton size')
    names, parents = [], []
    for bi, bone in enumerate(bones):
        name = bone.get('name')
        require(isinstance(name, str) and 0 < len(name) <= 128 and name not in names, 'Missing/duplicate civilian bone name')
        names.append(name)
        parent = integer(bone.get('parent'), -1, len(bones) - 1, 'bone parent')
        require(parent != bi, 'Self-parent civilian bone')
        parents.append(parent)
        vector(bone.get('inverse'), 16, 'inverse bind')
    pose = exported.get('pose')
    require(isinstance(pose, dict) and pose.get('method') == 'original_track_curve_samples' and
            finite(pose.get('time'), 'pose time') == 0 and 0 < finite(pose.get('duration'), 'pose duration') <= 3600 and
            isinstance(pose.get('scale_shear_transposed'), bool) and pose.get('bone_names') == names,
            'Civilian pose is not an original ordered IdleA t=0 curve sample')
    transpose = pose['scale_shear_transposed']
    tracks = pose.get('sampled_tracks')
    require(isinstance(tracks, list) and len(tracks) <= len(bones), 'Invalid sampled civilian curve count')
    by_name = {}
    for track in tracks:
        name = track.get('name')
        require(name in names and name not in by_name, 'Unknown/duplicate civilian sampled curve')
        for field, count, identity, flag in (
            ('position', 3, [0, 0, 0], 'position_identity'),
            ('orientation', 4, [0, 0, 0, 1], 'orientation_identity'),
            ('scale_shear', 9, [1, 0, 0, 0, 1, 0, 0, 0, 1], 'scale_identity')):
            values = vector(track.get(field), count, 'sampled ' + field)
            require(isinstance(track.get(flag), bool), 'Missing curve identity evidence')
            if track[flag]:
                require(all(abs(a - b) <= 1e-7 for a, b in zip(values, identity)), 'Claimed identity curve differs')
        by_name[name] = track
    bind_local = [original_math.local_matrix(b['local_position'], b['local_orientation'], b['local_scale_shear'], transpose) for b in bones]
    bind_world = original_math.compose_world(bind_local, parents)
    identity = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1]
    bind_error = max(original_math.matrix_max_error(original_math.matrix_multiply(world, vector(b['inverse'], 16, 'inverse')), identity)
                     for world, b in zip(bind_world, bones))
    require(bind_error < 0.002 and abs(bind_error - finite(pose.get('bind_matrix_max_error'), 'recorded bind error')) < 0.002,
            'Independent civilian bind composition differs')
    locals_ = []
    for bone in bones:
        track = by_name.get(bone['name'])
        values = ((track['position'], track['orientation'], track['scale_shear']) if track else
                  (bone['local_position'], bone['local_orientation'], bone['local_scale_shear']))
        locals_.append(original_math.local_matrix(*values, transpose))
    world = original_math.compose_world(locals_, parents)
    given = pose.get('matrices')
    require(isinstance(given, list) and len(given) == len(bones), 'Civilian sampled pose matrix count differs')
    error = max(original_math.matrix_max_error(actual, vector(expected, 16, 'pose matrix')) for actual, expected in zip(world, given))
    require(error < 0.002, 'Independent civilian curve-to-pose composition differs')
    palette = [original_math.matrix_multiply(actual, vector(b['inverse'], 16, 'inverse')) for actual, b in zip(world, bones)]
    return bones, palette, {'method': pose['method'], 'sample_time': 0, 'duration': pose['duration'],
        'curve_tracks': len(tracks), 'bind_fallback_bones': len(bones) - len(tracks),
        'bind_matrix_max_error_independent': bind_error, 'pose_matrix_max_error_independent': error,
        'source_extent_human_shape_assumption': False}


def skin_vertex(vertex, binding_indices, palette, scale, offset):
    position = [*vector(vertex.get('position'), 3, 'source position'), 1]
    normal = vector(vertex.get('normal'), 3, 'source normal')
    uv = vector(vertex.get('uv'), 2, 'source UV')
    indices, weights = vertex.get('boneIndices'), vertex.get('boneWeights')
    require(isinstance(indices, list) and len(indices) == 4 and isinstance(weights, list) and len(weights) == 4, 'Invalid civilian skin lanes')
    pos, n = [0.0] * 4, [0.0] * 3
    for raw_index, raw_weight in zip(indices, weights):
        index = integer(raw_index, 0, len(binding_indices) - 1, 'skin index')
        weight = integer(raw_weight, 0, 255, 'skin weight')
        if not weight:
            continue
        matrix = palette[binding_indices[index]]
        p, nn = original_math.mat_vec(matrix, position), original_math.linear_vec(matrix, normal)
        for axis in range(4):
            pos[axis] += p[axis] * (weight / 255)
        for axis in range(3):
            n[axis] += nn[axis] * (weight / 255)
    require(sum(weights) == 255 and all(math.isfinite(v) for v in pos) and abs(pos[3]) > 1e-8, 'Invalid skinned homogeneous position/weights')
    x, y, z = (pos[i] / pos[3] for i in range(3))
    transformed = [(x * scale + offset[0]) / 80, z * scale / 80, (-y * scale + offset[1]) / 80]
    result = [*transformed, *original_math.normalized([n[0], n[2], -n[1]], 'civilian normal'), *uv]
    require(all(math.isfinite(v) and abs(v) <= 10000 for v in result) and all(abs(v) <= 2 for v in result[:3]), 'Civilian static geometry exceeds its bounds')
    return result


def placement(slot, count, formation):
    columns = min(int(formation['TotalWidth']), count)
    rows = (count + columns - 1) // columns
    row, column = divmod(slot, columns)
    width = min(columns, count - row * columns)
    return ((column - (width - 1) / 2) * float(formation['SpacingX']),
            (row - (rows - 1) / 2) * float(formation['SpacingY']))


def material_reference_basename(reference):
    require(isinstance(reference, str) and 0 < len(reference) <= 1024 and '\0' not in reference, 'Invalid source material/model reference')
    name = reference.replace('\\', '/').rsplit('/', 1)[-1]
    require(re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', name) and name not in ('.', '..'), 'Invalid material metadata basename')
    return name


def virtual_reference(reference):
    require(isinstance(reference, str) and 0 < len(reference) <= 1024 and '\0' not in reference, 'Invalid virtual reference')
    value = reference.replace('\\', '/')
    require(not value.startswith('/') and ':' not in value and all(part not in ('', '.', '..') for part in value.split('/')),
            'Virtual archive reference contains an absolute/traversal path')
    material_reference_basename(value)
    return value


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exports', type=Path, required=True, help='New sealed civilian export directory under project Build')
    args = parser.parse_args(argv)
    exports = args.exports.absolute()
    require(exports.resolve(strict=True) == exports and exports.is_relative_to(PROJECT / 'Build'), 'Civilian exports must stay in their exact private Build directory')
    require(artifact(SCOPE)['sha256'] == SCOPE_SHA, 'Reviewed civilian scope changed')
    scope = json_document(SCOPE)
    require(scope['original_game_new_mod_test_hold'] and not any(scope['deployment'][name] for name in
        ('retail_mods_access_allowed', 'default_promotion_allowed', 'host_execution_allowed', 'gamecore_execution_allowed', 'native_window_execution_allowed')),
        'Civilian source-only hold differs')
    require(artifact(BASE_MANIFEST)['sha256'] == BASE_MANIFEST_SHA and artifact(BASE_PACKAGE)['sha256'] == BASE_SHA,
            'Current animated Warrior baseline changed')
    require(artifact(HELPER)['sha256'] == HELPER_SHA, 'Pinned existing stock exporter changed')
    base_manifest = json_document(BASE_MANIFEST)
    base_data = bounded_bytes(BASE_PACKAGE, MAX_PACKAGE)
    base = parse_package(base_data)
    require(len(base['textures']) == 3 and len(base['arts']) == 1 and base['arts'][0]['tag'] == 'ART_DEF_UNIT__WARRIOR' and
            len(base['arts'][0]['meshes']) == 12 and len(base['extension']) == 793226 and base['rig_bones'] == [23, 23, 23] and
            base['animated_count'] == 12, 'Current Warrior v2 structure differs')
    require({row['name'] for row in base['files']} == unit_animation_assets.RAW_NAMES, 'Current Warrior embedded closure differs')
    for actual, expected in zip(base['textures'], base_manifest['textures']):
        require(actual['info']['sha256'] == expected['sha256'] and len(actual['payload']) == expected['bytes'], 'Current manifest DDS record differs')
    old_embedded = unit_animation_assets.embedded_assets(BASE_PACKAGE)
    export_path = exports / 'export-manifest.json'
    export_ref = artifact(export_path)
    source = json_document(export_path)
    require(source.get('schema') == 1 and source.get('status') == 'PASS_CIVILIAN_UNIT_EXPORT' and
            source.get('gamecore_loaded') is False and source.get('host_executed') is False and source.get('hwnd_created') is False,
            'Civilian exporter has no passing isolated asset result')
    require(source['archives_before'] == source['archives_after'] and source['original_inputs_before'] == source['original_inputs_after'],
            'Civilian export observed source mutation')
    outputs = source.get('outputs')
    require(isinstance(outputs, list) and len(outputs) == 10 and source.get('units') == list(UNITS), 'Civilian exported member/unit set differs')
    expected_rows = [(unit['art_tag'], member) for unit in UNITS for member in unit['members']]
    wanted = {}
    for row, (art_tag, member) in zip(outputs, expected_rows):
        require(all(row.get(k) == member[k] for k in ('member_type', 'member_count', 'scale')) and row.get('art_tag') == art_tag and row.get('idle_event_code') == 1000,
                'Civilian output art/member/scale/IdleA order differs')
        for name in ('fxsxml', 'model', 'idle', 'diffuse', 'sref'):
            item = row[name]
            k = origin_key(item)
            require(k not in wanted or all(wanted[k][name_] == item[name_] for name_ in ('entry', 'offset', 'bytes', 'sha256')), 'Conflicting selected FPK origins')
            wanted[k] = {name_: item[name_] for name_ in ('entry', 'offset', 'bytes', 'sha256')}
    gsd = source.get('gsd')
    require(isinstance(gsd, dict) and gsd.get('reused') is True and path_key(gsd.get('path', '')) == path_key(SHARED_GSD) and gsd.get('sha256') == GSD_SHA,
            'Civilian export must reuse the exact existing GSD')
    gsd_bytes = verify_artifact(gsd, PROJECT / 'Build')
    k = origin_key(gsd['origin'])
    wanted[k] = {name: gsd['origin'][name] for name in ('entry', 'offset', 'bytes', 'sha256')}
    archive_before, payloads, packs = archive_seals(source['archives_before'], wanted)
    require(payloads[k] == gsd_bytes, 'Shared GSD differs from its selected original entry')
    xml_before, documents = small_xml_seals(source['original_inputs_before'])
    xml_members = validate_xml_units(documents, source['units'])
    formation, formation_before = formation_record()
    code_before = [artifact(PROJECT / name) for name in CODE_INPUTS]
    fixed_inputs_before = [artifact(SCOPE), artifact(BASE_PACKAGE), artifact(BASE_MANIFEST), artifact(HELPER), export_ref, artifact(SHARED_GSD)]
    calls = source.get('helper_calls')
    require(isinstance(calls, list) and len(calls) == 10, 'Expected ten bounded original asset helper calls')
    selected_artifacts = []
    require(sum(integer(row['json'].get('bytes'), 1, MAX_JSON, 'export JSON bytes') for row in outputs) <= MAX_JSON,
            'Total frozen civilian JSON closure exceeds 64 MiB')
    for row, call in zip(outputs, calls):
        for name in ('model', 'idle', 'fxsxml'):
            blob = verify_artifact(row[name]['extracted'], exports)
            require(blob == payloads[origin_key(row[name])], 'Extracted original payload differs from selected FPK source')
            selected_artifacts.append(copy.deepcopy(row[name]['extracted']))
        verify_artifact(row['json'], exports)
        selected_artifacts.append(copy.deepcopy(row['json']))
        require(call.get('exit_code') == 0 and call.get('timed_out') is False and
                call.get('argv') == [str(HELPER), str(PRIVATE_SDK), str(SHARED_GSD), row['model']['extracted']['path'],
                                    row['idle']['extracted']['path'], row['json']['path']], 'Export helper execution receipt differs')
        require(call.get('output_overflow') is False and call.get('reader_threads_finished') is True and call.get('reader_errors') == [],
                'Export helper capture failed or overflowed')
        limit = integer(call.get('log_limit_bytes_each'), 1, 4 * 1024 * 1024, 'bounded helper log limit')
        for name in ('stdout', 'stderr'):
            verify_artifact(call[name], exports, limit=limit, allow_empty=True)
            selected_artifacts.append(copy.deepcopy(call[name]))
    textures = copy.deepcopy(base_manifest['textures'])
    texture_raw = [row['raw'] for row in base['textures']]
    texture_ids = {row['sha256']: index for index, row in enumerate(textures)}
    arts, art_raw, source_models, transform_checks = copy.deepcopy(base_manifest['arts']), [base['arts'][0]['raw']], [], []
    by_member = {row['member_type']: row for row in outputs}
    total_vertices, total_indices = base['vertices'], base['indices']
    for unit in UNITS:
        meshes, mesh_metadata = [], []
        instance_count = sum(x['member_count'] for x in unit['members'])
        slot_start = 0
        for member in unit['members']:
            row = by_member[member['member_type']]
            model = json_document(row['json']['path'])
            require(model.get('source_sha256') == row['model']['sha256'] and model.get('animation_sha256') == row['idle']['sha256'] and
                    model.get('gsd_sha256') == GSD_SHA, 'Civilian model/IdleA/GSD JSON identity differs')
            model_pack = packs[path_key(MODEL_FPK)]
            require(original_math.resolve_pack_name(model_pack, virtual_reference(xml_members[member['member_type']]['fxsxml'])) == row['fxsxml']['entry'], 'Original XML/FXSXML reference differs')
            fxs = ET.fromstring(payloads[origin_key(row['fxsxml'])])
            mesh_refs = [node.attrib.get('file', '') for node in fxs.findall('.//Mesh')]
            idle_refs = [node.attrib.get('file', '') for node in fxs.findall('.//Animation') if node.attrib.get('ec') == '1000']
            require(len(mesh_refs) == len(idle_refs) == 1 and original_math.resolve_pack_name(model_pack, virtual_reference(mesh_refs[0])) == row['model']['entry'] and
                    original_math.resolve_pack_name(model_pack, virtual_reference(idle_refs[0])) == row['idle']['entry'] and
                    material_reference_basename(idle_refs[0]).casefold().endswith('_idlea.gr2'),
                    'Original model/IdleA event reference differs')
            declared = {material_reference_basename(virtual_reference(node.attrib['file'])).casefold() for node in fxs.findall('.//Texture') if node.attrib.get('file')}
            bones, palette, proof = pose_from_curves(model)
            transform_checks.append({'member_type': member['member_type'], **proof})
            bone_ids = {bone['name']: i for i, bone in enumerate(bones)}
            original_meshes = model.get('meshes')
            require(isinstance(original_meshes, list) and 0 < len(original_meshes) <= 64, 'Invalid civilian source mesh count')
            prepared, mesh_names = [], set()
            for source_mesh in original_meshes:
                name = source_mesh.get('name')
                require(isinstance(name, str) and name and name not in mesh_names, 'Missing/duplicate civilian mesh name')
                mesh_names.add(name)
                bindings = source_mesh.get('bindings')
                require(isinstance(bindings, list) and 0 < len(bindings) <= 256 and len(set(bindings)) == len(bindings) and all(x in bone_ids for x in bindings), 'Invalid civilian skin binding names')
                materials = source_mesh.get('materials')
                require(isinstance(materials, list) and len(materials) == 1, 'Civilian mesh needs one preserved original material; no implicit first-material fallback')
                material = materials[0]
                for role in ('diffuse', 'sref'):
                    reference = material_reference_basename(material.get(role))
                    require(reference.casefold() in declared and original_math.resolve_pack_name(packs[path_key(TEXTURE_FPK)], reference) == row[role]['entry'], 'Civilian FXSXML/material DIFF/SREF reference differs')
                    original_math.dds_info(payloads[origin_key(row[role])], member['member_type'] + ' ' + role)
                dds = payloads[origin_key(row['diffuse'])]
                sha = digest(dds)
                if sha not in texture_ids:
                    require(len(textures) < 64, 'Combined texture count exceeds native limit')
                    texture_ids[sha] = len(textures)
                    info = original_math.dds_info(dds, member['member_type'])
                    textures.append({**row['diffuse'], **info, 'filename': material_reference_basename(material['diffuse']),
                                     'source_aliases': [material_reference_basename(material['diffuse'])]})
                    texture_raw.append(struct.pack('<I', len(dds)) + dds)
                    require(sum(len(x) for x in texture_raw) + len(base['arts'][0]['raw']) + len(base['extension']) + 20 <= MAX_PACKAGE,
                            'Selected DDS records exhaust the package byte budget')
                vertices, triangles = source_mesh.get('vertices'), source_mesh.get('triangles')
                require(isinstance(vertices, list) and 0 < len(vertices) <= 200000 and isinstance(triangles, list) and 0 < len(triangles) <= 200000, 'Invalid civilian source geometry size')
                indices = []
                for triangle in triangles:
                    require(isinstance(triangle, list) and len(triangle) == 3, 'Civilian triangle is not a triangle')
                    indices.extend(integer(x, 0, len(vertices) - 1, 'triangle index') for x in triangle)
                prepared.append((source_mesh, [bone_ids[x] for x in bindings], texture_ids[sha], indices, material))
            for within_member in range(member['member_count']):
                slot = slot_start + within_member
                offset = placement(slot, instance_count, formation)
                for source_mesh, bindings, texture, indices, material in prepared:
                    total_vertices += len(source_mesh['vertices'])
                    total_indices += len(indices)
                    require(total_vertices <= 1000000 and total_indices <= 3000000 and len(meshes) < 128,
                            'Combined civilian geometry exceeds native aggregate/art bounds')
                    vertices = [skin_vertex(v, bindings, palette, member['scale'], offset) for v in source_mesh['vertices']]
                    record = bytearray(struct.pack('<III', texture, len(vertices), len(indices)))
                    for vertex in vertices:
                        record += struct.pack('<8f', *vertex)
                    record += struct.pack('<' + 'I' * len(indices), *indices)
                    meshes.append(bytes(record))
                    mesh_metadata.append({'name': source_mesh['name'], 'member_type': member['member_type'], 'formation_slot': slot,
                        'texture_index': texture, 'vertices': len(vertices), 'indices': len(indices),
                        'diffuse': material['diffuse'], 'sref': material['sref'], 'material': copy.deepcopy(material),
                        'member_scale': member['scale'], 'static_pose_time': 0})
            slot_start += member['member_count']
            source_models.append({'art_tag': unit['art_tag'], 'member_type': member['member_type'], 'member_count': member['member_count'],
                'export_json': row['json']['path'], 'export_json_sha256': row['json']['sha256'], 'source_gr2': copy.deepcopy(row['model']),
                'idle_gr2': copy.deepcopy(row['idle']), 'fxsxml': copy.deepcopy(row['fxsxml']), 'diffuse': copy.deepcopy(row['diffuse']),
                'sref': copy.deepcopy(row['sref']), 'source_scale': member['scale'], 'pose_time': 0, 'civilian_animation_playback': False})
        require(slot_start == instance_count and 0 < len(meshes) <= 128, 'Civilian art mesh/member count exceeds native bound')
        tag = unit['art_tag'].encode('ascii')
        art_raw.append(struct.pack('<I', len(tag)) + tag + struct.pack('<I', len(meshes)) + b''.join(meshes))
        arts.append({'tag': unit['art_tag'], 'mesh_count': len(meshes), 'instances': instance_count, 'meshes': mesh_metadata})
    package = b'ZSUNIT02' + struct.pack('<II', 2, len(textures)) + b''.join(texture_raw) + struct.pack('<I', len(arts)) + b''.join(art_raw) + base['extension']
    candidate = parse_package(package)
    assert_preserved(base, candidate)
    regressions = parser_regressions(base_data, base, package, candidate)
    require(all(metadata(row['path']) == {k: row[k] for k in ('path', 'device', 'file_id', 'bytes', 'mtime_ns')} for row in archive_before),
            'Original archives changed before output publication')
    require(formation_record()[1] == formation_before, 'LooseCivilian source changed during packaging')
    require(artifact(export_path) == export_ref and [artifact(PROJECT / name) for name in CODE_INPUTS] == code_before[:len(CODE_INPUTS)], 'Exporter/source code changed during packaging')
    for row in selected_artifacts:
        verify_artifact(row, exports, allow_empty=True)
    require(artifact(BASE_PACKAGE)['sha256'] == BASE_SHA and artifact(BASE_MANIFEST)['sha256'] == BASE_MANIFEST_SHA and
            artifact(HELPER)['sha256'] == HELPER_SHA and artifact(SHARED_GSD)['sha256'] == GSD_SHA and artifact(SCOPE)['sha256'] == SCOPE_SHA,
            'Protected current package/helper/GSD/scope changed')
    package_sha = digest(package)
    output = PROJECT / 'Build/UnitAssets' / package_sha
    require(not output.exists() and output.resolve().is_relative_to(PROJECT / 'Build/UnitAssets') and output.resolve() == output.absolute(),
            'Immutable content-addressed output exists or crosses a reparse boundary')
    output.mkdir(exist_ok=False)
    package_path = output / 'unit-assets.bin'
    with package_path.open('xb') as stream:
        stream.write(package)
        stream.flush()
        os.fsync(stream.fileno())
    require(artifact(package_path)['sha256'] == package_sha, 'Written civilian package differs')
    require(unit_animation_assets.embedded_assets(package_path) == old_embedded, 'Existing animation materializer closure changed')
    archive_after, unused_payloads, unused_packs = archive_seals(source['archives_after'], wanted)
    xml_after, unused_documents = small_xml_seals(source['original_inputs_after'])
    require(archive_after == archive_before and xml_after == xml_before and formation_record()[1] == formation_before,
            'Original selected asset/formation inputs changed during output publication')
    code_after = [artifact(PROJECT / name) for name in CODE_INPUTS]
    fixed_inputs_after = [artifact(Path(row['path'])) for row in fixed_inputs_before]
    require(code_after == code_before and fixed_inputs_after == fixed_inputs_before, 'Exact source/fixed inputs changed during output publication')
    for row in selected_artifacts:
        verify_artifact(row, exports, allow_empty=True)
    require(artifact(BASE_PACKAGE)['sha256'] == BASE_SHA and artifact(BASE_MANIFEST)['sha256'] == BASE_MANIFEST_SHA,
            'Existing Warrior package/manifest changed during output')
    manifest = {
        'schema': 1, 'status': 'PASS_ORIGINAL_UNIT_PACKAGE', 'utc': datetime.now(timezone.utc).isoformat(),
        'package': {**artifact(package_path), 'format': 'ZSUNIT02 v2'}, 'art_tag': 'ART_DEF_UNIT__WARRIOR',
        'art_tags': [row['tag'] for row in arts], 'source_base_package': artifact(BASE_PACKAGE), 'source_base_manifest': artifact(BASE_MANIFEST),
        'source_export_manifest': {**export_ref, 'status': source['status'], 'run_id': source.get('run_id')},
        'scope': artifact(SCOPE), 'exact_code_inputs_before': code_before, 'exact_code_inputs_after': code_after,
        'fixed_inputs_before': fixed_inputs_before, 'fixed_inputs_after': fixed_inputs_after,
        'original_inputs_before': xml_before, 'original_inputs_after': xml_after,
        'selected_archives_before': archive_before, 'selected_archives_after': archive_after, 'whole_FPK_hashes_computed': 0,
        'formation_input': formation_before, 'formation_original': copy.deepcopy(base_manifest['formation_original']),
        'civilian_formation_original': {'name': 'LooseCivilian', **formation},
        'civilian_formation_candidate': {'layout': 'center each row, original member order, up to original TotalWidth columns',
            'spacingX': 12, 'spacingY': 14, 'columns': 4, 'randomness': 0, 'stagger': 0, 'curve': 0,
            'source_randomness_stagger_and_curvature_reproduced': False},
        'civilian_unit_selection': list(UNITS), 'unit_selection': copy.deepcopy(base_manifest['unit_selection']),
        'legacy_warrior_metadata': {'art_tag': 'ART_DEF_UNIT__WARRIOR',
            'note': 'Top-level singular art_tag and unit_selection retain the legacy Warrior compatibility fields only; arts/art_tags are the complete three-art catalog.',
            'source_base_manifest': artifact(BASE_MANIFEST)},
        'textures': textures, 'arts': arts, 'source_models': [*copy.deepcopy(base_manifest['source_models']), *source_models],
        'animation': copy.deepcopy(base_manifest['animation']), 'serialized_extension_validation': copy.deepcopy(base_manifest['serialized_extension_validation']),
        'base_preservation': {'package_unchanged': True, 'manifest_unchanged': True, 'old_DDS_raw_records_equal': True,
            'warrior_art_index': 0, 'old_mesh_float8_and_index_records_equal': True, 'whole_animation_extension_equal': True,
            'animation_extension_bytes': len(base['extension']), 'animation_extension_sha256': digest(base['extension']),
            'existing_materializer_embedded_assets_equal': True},
        'civilian_transform_checks': transform_checks, 'binary_validation': regressions,
        'geometry': {'vertices': candidate['vertices'], 'indices': candidate['indices'], 'art_count': len(arts), 'texture_count': len(textures)},
        'serialized_counts': {'arts': len(candidate['arts']), 'textures': len(candidate['textures']),
            'meshes_per_art': {art['tag']: len(art['meshes']) for art in candidate['arts']},
            'source_models': len(base_manifest['source_models']) + len(source_models), 'new_civilian_source_models': len(source_models),
            'new_civilian_member_instances': 17, 'embedded_files': len(candidate['files']), 'rigs': len(candidate['rig_bones']),
            'animated_meshes': candidate['animated_count'], 'animated_vertices': candidate['animated_vertices'],
            'new_civilian_animated_meshes': 0},
        'coordinate_and_skinning_policy': {'matrix_layout': 'column-major; independently recomposed source bind/curve pose',
            'position': 'poseWorld * inverseBind, weights/255, XYZ -> X,Z,-Y, member scale 0.12/0.14, then 1/80',
            'normal': 'weighted 3x3 skin transform, XYZ -> X,Z,-Y, normalized',
            'topology': 'each original source mesh and original index order retained for each declared member instance'},
        'civilian_animation_playback': False, 'actual_screen_verified': False,
        'host_executed': False, 'gamecore_loaded': False, 'hwnd_created': False, 'gpu_used': False,
        'retail_mods_saves_settings_or_processes_accessed': False, 'default_promoted': False, 'save_schema_changed': False,
        'limits': ['Civilian meshes are original IdleA t=0 geometry, not animated civilian playback.',
            'Formation placement, yaw and on-screen scale calibration remain candidate policy; source randomness/stagger/curve are not reproduced.',
            'Diffuse is packaged; original SREF/shader/alpha references are retained as provenance, not complete material rendering.',
            'Asset CLI/binary checks do not establish actual GPU display, game/mod/save compatibility, or full engine completion.'],
    }
    manifest_path = output / 'unit-assets.manifest.json'
    with manifest_path.open('x', encoding='utf8') as stream:
        json.dump(manifest, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    print(json.dumps({'status': manifest['status'], 'package': manifest['package'], 'manifest': artifact(manifest_path),
        'arts': manifest['art_tags'], 'civilian_instances': [9, 8], 'existing_animation_extension_preserved': True,
        'civilian_animation_playback': False, 'gpu_used': False, 'whole_FPK_hashes_computed': 0}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
