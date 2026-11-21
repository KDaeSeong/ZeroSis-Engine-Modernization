"""Resolve the explicit Expansion2 desktop front-end from original packages.

This is a file-only profile for the isolated Expansion2 backend. Installed DLC
does not activate mods, and package/source provenance does not prove the retail
engine's resource loader or native pixel geometry. No original files are copied.
"""
from __future__ import annotations

from copy import deepcopy
from contextlib import closing
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import stat
import struct
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
BACKEND = PROJECT / 'Build/InteractiveGameRuntime/20261103T140325Z_f127e4edebe9/bundle.manifest'
PROFILE = 'EXPANSION2_COMMON_ORIGINAL_FRONTEND_V1'
PACKAGE_SPECS = (
    ('Expansion2', 'Expansion2Primary', 'Assets/DLC/Expansion2/Expansion2.Civ5Pkg',
     '{6DA07636-4123-4018-B643-6575B4EC336B}', 200, 'Expansion2UITextures.fpk'),
    ('Expansion1', 'Expansion1Primary', 'Assets/DLC/Expansion/Expansion1.Civ5Pkg',
     '{0E3751A1-F840-4E1B-9706-519BF484E59D}', 100, 'Expansion1UITextures.fpk'),
)
DEFAULT_SOURCES = tuple('UI/FrontEnd/' + name for name in (
    'FrontEnd.xml', 'FrontEnd.lua', 'MainMenu.xml', 'MainMenu.lua',
    'SinglePlayer.xml', 'SinglePlayer.lua', 'ExitConfirm.xml', 'ExitConfirm.lua')) + (
    'UI/Options/OptionsMenu.xml', 'UI/Options/OptionsMenu.lua')
STYLE_NAMES = ('Grid9DetailFive140', 'Grid9FrameTurns', 'Grid9FrameTurnsHL',
    'Grid9Frame27SquareBlack', 'SmallButton', 'BaseButton', 'ZoomButton',
    'SquareButton', 'GenericPullDown', 'Button_16', 'Slider', 'Slider32',
    'VertSlider', 'VertShuttle', 'ScrollBarUp', 'ScrollBarDown')
OFFICIAL_RULE_ICON_SOURCES = {
    'civsymbolscolor32_dlc_01.dds': ('DLC_01/Mongol.Civ5Pkg',
        '{293C1EE3-1176-44F6-AC1F-59663826DE74}', 'MongolGehghis_KhanTextures.fpk'),
    'civsymbolscolor32_dlc_03.dds': ('DLC_03/Polynesia.Civ5Pkg',
        '{ECF7C605-BA11-4CAC-8D80-D71306AAC471}', 'PolynesiaTextures.fpk'),
    'civsymbolscolor32_dlc_04.dds': ('DLC_04/Denmark.Civ5Pkg',
        '{B3030D39-C0D8-4BC7-91B1-7AD1CAF585AB}', 'DenmarkTextures.fpk'),
    'civsymbolscolor32_dlc_korea.dds': ('DLC_05/Korea.Civ5Pkg',
        '{112C22B2-5308-42B6-B734-171CCAB3037B}', 'KoreaTextures.fpk'),
    'civsymbolscolor32_dlc_d.dds': ('DLC_Deluxe/Babylon.Civ5Pkg',
        '{7459BA32-5764-44AE-8E95-01AD0E0EFD48}', 'BabylonianNebuchadnezzarTextures.fpk'),
}


def require(ok, message):
    if not ok:
        raise ValueError(message)


def _ordinary_path(path):
    path = Path(os.path.abspath(os.fspath(path)))
    for item in [*reversed(path.parents), path]:
        try:
            info = os.lstat(item)
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and
                not getattr(info, 'st_file_attributes', 0) & 0x400,
                'Skin input contains a symlink or reparse point: ' + str(item))
    return path


def artifact(path):
    path = _ordinary_path(path)
    before = path.stat()
    require(stat.S_ISREG(before.st_mode), 'Skin input is not a regular file')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns),
            'Skin input changed while hashing: ' + str(path))
    return dict(path=str(path), bytes=after.st_size, sha256=digest.hexdigest(),
                file_identity=[after.st_dev, after.st_ino], mtime_ns=after.st_mtime_ns,
                file_attributes=getattr(after, 'st_file_attributes', 0))


def _relative(value):
    require(isinstance(value, str) and value and '\\' not in value and
            ':' not in value and '\0' not in value, 'Invalid skin-relative path')
    path = PurePosixPath(value)
    require(not path.is_absolute() and all(part not in ('', '.', '..') for part in value.split('/')),
            'Skin path escapes its declared mount')
    return path.as_posix()


def _lookup(root, relative):
    current = _ordinary_path(root)
    for part in _relative(relative).split('/'):
        if not current.is_dir():
            return None
        matches = [item for item in current.iterdir() if item.name.casefold() == part.casefold()]
        require(len(matches) <= 1, 'Ambiguous case-insensitive skin input: ' + relative)
        if not matches:
            return None
        current = _ordinary_path(matches[0])
    return current


def _signature(node):
    return (node.tag, tuple(sorted(node.attrib.items())), (node.text or '').strip(),
            tuple(_signature(child) for child in node))


class FrontEndSkin:
    """Read-only source/style/texture resolver; priority is explicit and bounded."""
    def __init__(self, game_root=GAME, backend_manifest=BACKEND):
        self.game_root = _ordinary_path(game_root)
        require(self.game_root.is_dir(), 'Original game directory is missing')
        self._pins = {}
        self._resolved = {}
        self._style_elements = None
        self._style_records = {}
        self._texture_records = {}
        self._packs = None
        self.backend = self._backend(backend_manifest)
        self.layers = [self._package(spec) for spec in PACKAGE_SPECS]
        self.layers.append(dict(name='BaseGame', skin='BUILT_IN_BASE_ASSETS', priority=None,
            priority_source='BUILT_IN_FALLBACK_NO_PACKAGE_PRIORITY_DECLARATION',
            root=str(self.game_root / 'Assets'), directories=['UI'],
            files=[], styles=['UI/Styles.xml'], colors=[], paks=['UITextures.fpk'],
            package=None, platform='Common'))
        require([row['priority'] for row in self.layers] == [200, 100, None],
                'Front-end package priority differs from the explicit Expansion2 profile')

    def _pin(self, path):
        row = artifact(path)
        old = self._pins.get(row['path'])
        require(old is None or old == row, 'Pinned skin input changed: ' + row['path'])
        self._pins[row['path']] = row
        return row

    def _xml(self, path):
        row = self._pin(path)
        require(row['bytes'] <= 8 * 1024 * 1024, 'Skin XML exceeds bounded size')
        root = ET.parse(path).getroot()
        self._pin(path)
        return root

    def _backend(self, manifest):
        manifest = _ordinary_path(manifest)
        row = self._pin(manifest)
        require(row['bytes'] <= 16384, 'Backend bundle manifest exceeds its host limit')
        lines = manifest.read_text('utf8').splitlines()
        require(lines and lines[0] == 'ZEROSIS_HOST_BUNDLE_V4', 'Unsupported backend manifest')
        entries = {}
        for line in lines[1:]:
            parts = line.split('|')
            require(len(parts) == 2 and re.fullmatch(r'[A-Za-z0-9_.-]+', parts[0]) and
                    re.fullmatch(r'[0-9a-f]{64}', parts[1]) and parts[0] not in entries,
                    'Invalid or duplicate backend manifest entry')
            entries[parts[0]] = parts[1]
        name = 'CvGameCoreDLL_Expansion2_x64.dll'
        require(name in entries and not any(key.startswith('CvGameCoreDLL') and key != name for key in entries),
                'Active front-end profile requires the isolated Expansion2 backend')
        dll = self._pin(manifest.parent / name)
        require(dll['sha256'] == entries[name], 'Backend GameCore bytes differ from bundle manifest')
        with Path(dll['path']).open('rb') as stream:
            header = stream.read(64)
            require(len(header) == 64 and header[:2] == b'MZ', 'Backend is not a PE image')
            offset, = struct.unpack_from('<I', header, 60)
            require(64 <= offset <= dll['bytes'] - 26, 'Backend PE offset is out of bounds')
            stream.seek(offset)
            pe = stream.read(26)
            require(pe[:4] == b'PE\0\0' and struct.unpack_from('<H', pe, 4)[0] == 0x8664 and
                    struct.unpack_from('<H', pe, 24)[0] == 0x20b and
                    struct.unpack_from('<H', pe, 22)[0] & 0x2000,
                    'Backend GameCore must be an AMD64 PE32+ DLL')
        self._pin(manifest)
        self._pin(dll['path'])
        require('rules.db' in entries, 'Expansion2 backend has no bound rules database')
        rules = self._pin(manifest.parent / 'rules.db')
        require(rules['sha256'] == entries['rules.db'], 'Backend rules database differs from bundle manifest')
        return dict(manifest=row, gamecore=dll, name=name, platform='Common',
            rules=rules,
            mod_activation='NONE_PERFORMED_BY_THIS_FILE_ONLY_RESOLVER',
            binding='EXACT_EXPANSION2_GAMECORE_ENTRY_AND_AMD64_DLL_BYTES', execution=False)

    def _package(self, spec):
        name, skin, relative, guid, priority, pak = spec
        path = _lookup(self.game_root, relative)
        require(path is not None, 'Required Expansion2 fallback package is missing: ' + relative)
        root = self._xml(path)
        require(root.tag == 'Civ5Package' and (root.findtext('GUID') or '').upper() == guid and
                root.findtext('Priority') == str(priority), 'Original expansion package identity/priority differs')
        matches = [node for node in root.findall('UISkin') if node.get('name') == skin and
                   node.get('set') == name and node.get('platform') == 'Common']
        require(len(matches) == 1, 'Original desktop skin declaration is missing or ambiguous')
        selected = matches[0].find('Skin')
        require(selected is not None, 'Original package has no front-end Skin block')
        def values(tag):
            return [_relative((node.text or '').strip()) for node in selected.findall(tag)]
        paks = values('Paks/File')
        require(paks == [pak], 'Original front-end texture pack declaration differs')
        return dict(name=name, skin=skin, priority=priority, root=str(path.parent),
            directories=values('Directory'), files=values('File'), styles=values('Style'),
            colors=values('Color'), paks=paks, package=self._pin(path), platform='Common')

    def resolve(self, logical_path):
        logical = _relative(logical_path)
        require(logical.casefold().startswith(('ui/frontend/', 'ui/options/')),
                'Only front-end/options source paths belong to this resolver; gameplay uses its own skin profile')
        candidates = []
        for layer in self.layers:
            mounted = any(logical.casefold().startswith(directory.casefold() + '/')
                          for directory in layer['directories'])
            mounted = mounted or logical.casefold() in [name.casefold() for name in layer['files'] if '*' not in name]
            path = _lookup(layer['root'], logical) if mounted else None
            found = path is not None and path.is_file()
            candidate = dict(layer=layer['name'], skin=layer['skin'], priority=layer['priority'],
                             mounted=mounted, exists=found)
            if found:
                candidate['source'] = self._pin(path)
            candidates.append(candidate)
        winner = next((row for row in candidates if row['exists']), None)
        require(winner is not None, 'Original skin resource is missing: ' + logical)
        result = dict(logical_path=logical, layer=winner['layer'], source=winner['source'],
                      candidates=candidates)
        self._resolved[logical] = result
        return deepcopy(result)

    def selected_style_elements(self):
        if self._style_elements is None:
            elements = {}
            records = {}
            for layer in reversed(self.layers):
                for relative in layer['styles']:
                    path = _lookup(layer['root'], relative)
                    require(path is not None, 'Declared original skin style file is missing')
                    root = self._xml(path)
                    seen = {}
                    for node in root:
                        signature = _signature(node)
                        require(node.tag not in seen or seen[node.tag] == signature,
                                'Conflicting duplicate original style: ' + node.tag)
                        seen[node.tag] = signature
                        elements[node.tag] = deepcopy(node)
                        records[node.tag] = dict(name=node.tag, layer=layer['name'],
                            source=self._pins[str(path)], attributes=dict(node.attrib),
                            element_sha256=hashlib.sha256(repr(signature).encode('utf8')).hexdigest())
            self._style_elements = elements
            self._style_records = records
        return deepcopy(self._style_elements)

    def _load_packs(self):
        if self._packs is not None:
            return
        from civ5_ui_assets import Fpk
        self._packs = []
        for layer in self.layers:
            for name in layer['paks']:
                path = _lookup(self.game_root, 'Resource/DX9/' + name)
                require(path is not None, 'Declared original UI texture pack is missing')
                pin = self._pin(path)
                self._packs.append((layer['name'], Fpk(path), pin))
        shared = _lookup(self.game_root, 'Assets/DLC/Shared/Upgrade1.Civ5Pkg')
        require(shared is not None, 'Shared official texture fallback package is missing')
        root = self._xml(shared)
        require((root.findtext('GUID') or '').upper() == '{8871E748-29A4-4910-8C57-8C99E32D0167}' and
                'Upgrade1Textures.fpk' in [node.text for node in root.findall('Paks/File')],
                'Shared official texture fallback declaration differs')
        path = _lookup(self.game_root, 'Resource/DX9/Upgrade1Textures.fpk')
        require(path is not None, 'Shared official texture fallback pack is missing')
        self._packs.append(('SharedOfficialFallback', Fpk(path), self._pin(path)))

    def texture(self, texture_name):
        require(isinstance(texture_name, str) and ':' not in texture_name and '\0' not in texture_name,
                'Invalid original UI texture name')
        basename = texture_name.replace('\\', '/').rsplit('/', 1)[-1].casefold()
        require(basename.endswith('.dds') and basename != '.dds', 'Expected an original DDS texture')
        if basename in self._texture_records:
            return deepcopy(self._texture_records[basename])
        self._load_packs()
        candidates = []
        selected = None
        for layer, pack, pin in self._packs:
            entry = pack.entries.get(basename)
            if entry is None:
                continue
            candidates.append(dict(layer=layer, pack=pin, entry=entry.name, bytes=entry.size, offset=entry.offset))
            if selected is None:
                data, source = pack.read(basename)
                selected = dict(kind='fpk-entry', layer=layer, pack=pin, source=source)
                private = (data[32:76].split(b'\0', 1)[0] in (b'FTXTInterface', b'FTXTInterface Scalable') and
                           data[116:124].split(b'\0', 1)[0].startswith(b'BC0'))
                if private:
                    _, index = pack.read(basename[:-4] + '-index.dds')
                    selected['index_source'] = index
        if selected is None and basename in OFFICIAL_RULE_ICON_SOURCES:
            selected = self._official_rule_icon(basename)
            candidates.append(dict(layer=selected['layer'], pack=selected['pack'],
                entry=selected['source']['entry'], bytes=selected['source']['bytes'],
                offset=selected['source']['offset']))
        if selected is None:
            from civ5_ui_assets import LOOSE_UI_TEXTURES
            loose = LOOSE_UI_TEXTURES.get(basename)
            require(isinstance(loose, dict), 'No declared original UI texture: ' + basename)
            path = _lookup(self.game_root, loose['relative_path'])
            require(path is not None, 'Pinned loose original texture is missing')
            pin = self._pin(path)
            require((pin['bytes'], pin['sha256']) == (loose['bytes'], loose['sha256']),
                    'Pinned loose original texture differs')
            source = dict(kind='loose-ui-texture', path=pin['path'], relative_path=loose['relative_path'],
                          bytes=pin['bytes'], sha256=pin['sha256'])
            selected = dict(kind='loose-ui-texture', layer='EXACT_OFFICIAL_LOOSE_FALLBACK', source=source)
            candidates.append(dict(layer=selected['layer'], source=pin))
        result = dict(basename=basename, **selected, candidates=candidates)
        self._texture_records[basename] = result
        return deepcopy(result)

    def _official_rule_icon(self, basename):
        # These exact original atlases are already referenced by the immutable
        # backend rules. Resolving their artwork does not activate DLC or mods.
        from civ5_ui_assets import Fpk
        rules = Path(self.backend['rules']['path'])
        self._pin(rules)
        with closing(sqlite3.connect(rules.as_uri() + '?mode=ro&immutable=1', uri=True)) as database:
            rows = database.execute('SELECT Atlas,IconSize,Filename,IconsPerRow,IconsPerColumn '
                'FROM IconTextureAtlases WHERE lower(Filename)=? AND IconSize=32 ORDER BY Atlas',
                (basename,)).fetchall()
        def positive_integer(value):
            if type(value) is int:
                return value if 0 < value <= 8192 else None
            if type(value) is str and re.fullmatch(r'[1-9][0-9]{0,3}', value):
                number = int(value)
                return number if number <= 8192 else None
            return None
        require(rows and all(positive_integer(row[1]) == 32 and row[2].casefold() == basename and
                positive_integer(row[3]) is not None and positive_integer(row[4]) is not None for row in rows),
                'Official civilization atlas is not bound by the current backend rules')
        relative, guid, name = OFFICIAL_RULE_ICON_SOURCES[basename]
        package = _lookup(self.game_root, 'Assets/DLC/' + relative)
        require(package is not None, 'Rules-referenced official atlas package is missing')
        root = self._xml(package)
        require((root.findtext('GUID') or '').upper() == guid and
                name in [node.text for node in root.findall('Paks/File')],
                'Rules-referenced atlas is not declared by its exact official package')
        path = _lookup(self.game_root, 'Resource/DX9/' + name)
        require(path is not None, 'Rules-referenced official atlas pack is missing')
        pin = self._pin(path)
        pack = Fpk(path)
        require(basename in pack.entries, 'Official atlas is missing from its declared pack')
        data, source = pack.read(basename)
        selected = dict(kind='fpk-entry', layer='RULES_REFERENCED_OFFICIAL_CIVILIZATION_ART',
            source=source, pack=pin, package=self._pins[str(package)],
            rules=self.backend['rules'], icon_atlas_rows=[dict(zip(
                ('Atlas', 'IconSize', 'Filename', 'IconsPerRow', 'IconsPerColumn'), row)) for row in rows],
            activates_dlc_or_mod=False)
        private = (data[32:76].split(b'\0', 1)[0] in (b'FTXTInterface', b'FTXTInterface Scalable') and
                   data[116:124].split(b'\0', 1)[0].startswith(b'BC0'))
        if private:
            _, selected['index_source'] = pack.read(basename[:-4] + '-index.dds')
        self._pin(rules)
        self._pin(path)
        return selected

    def verify_texture_records(self, records):
        for row in records:
            selected = self.texture(row['basename'])
            expected = selected['source']
            actual = row['source']
            require(actual.get('sha256') == expected['sha256'] and actual.get('bytes') == expected['bytes'],
                    'Inherited texture hides a different active skin winner: ' + row['basename'])
            if selected['kind'] == 'fpk-entry':
                require(Path(actual.get('pack_path', '')).absolute() == Path(expected['pack_path']).absolute() and
                        actual.get('entry', '').casefold() == expected['entry'].casefold(),
                        'Inherited texture provenance differs from its declared active skin pack')
            else:
                require(Path(actual.get('path', '')).absolute() == Path(expected['path']).absolute(),
                        'Inherited loose texture does not use its exact original source')
            require(row.get('index_source') == selected.get('index_source'),
                    'Inherited FTXT index must come from the same selected pack')
        return True

    def provenance(self, logical_paths=DEFAULT_SOURCES, style_names=STYLE_NAMES, texture_names=()):
        sources = [self.resolve(path) for path in logical_paths]
        self.selected_style_elements()
        styles = []
        for name in style_names:
            require(name in self._style_records, 'Original active skin style is missing: ' + name)
            styles.append(deepcopy(self._style_records[name]))
        textures = [self.texture(name) for name in texture_names]
        footers = []
        for logical, control in (('UI/FrontEnd/MainMenu.xml', 'ExitButton'),
                                 ('UI/FrontEnd/SinglePlayer.xml', 'BackButton')):
            source = self.resolve(logical)
            nodes = [node for node in self._xml(source['source']['path']).iter() if node.get('ID') == control]
            require(len(nodes) == 1, 'Original footer control is missing or ambiguous')
            footers.append(dict(logical_path=logical, control=control, layer=source['layer'],
                                attributes=dict(nodes[0].attrib), source=source['source']))
        return dict(schema='zerosis.original_frontend.active_skin.v1', profile=PROFILE,
            backend=self.backend, layers=deepcopy(self.layers), sources=sources, styles=styles,
            textures=textures, footer_controls=footers, native_execution=False, sdk_loaded=False,
            native_loader_verified=False, native_geometry_verified=False, mod_activation=False,
            limitations=['Explicit isolated Expansion2/Common profile; no retail resource-loader acceptance.',
                         'Base fallback is the existing built-in Assets/UI tree.',
                         'Shared Upgrade1 textures are an explicit official fallback after base UITextures.'])

    def unchanged(self):
        return all(artifact(path) == row for path, row in self._pins.items())


def resolve_frontend_skin(game_root=GAME, backend_manifest=BACKEND, logical_paths=DEFAULT_SOURCES):
    skin = FrontEndSkin(game_root, backend_manifest)
    result = skin.provenance(logical_paths)
    require(skin.unchanged(), 'Original package/source inputs changed during skin resolution')
    result['protected_inputs_unchanged'] = True
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game', type=Path, default=GAME)
    parser.add_argument('--backend-manifest', type=Path, default=BACKEND)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    result = resolve_frontend_skin(args.game, args.backend_manifest)
    if args.report:
        report = _ordinary_path(args.report)
        allowed = PROJECT / 'evidence/game_menu/replay_calendar_legend/skin'
        require(report.is_relative_to(allowed), 'Skin report must remain inside its exact owned evidence directory')
        report.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(result, indent=2, ensure_ascii=False) + '\n'
        if report.exists():
            require(report.read_text('utf8') == data, 'Refusing to replace an existing skin result')
        else:
            report.write_text(data, encoding='utf8')
    print(json.dumps(dict(status='PASS_EXPLICIT_EXPANSION2_SKIN_RESOLVED_FILE_ONLY',
        profile=result['profile'], sources=len(result['sources']), styles=len(result['styles']),
        footer_offsets=[row['attributes'].get('Offset') for row in result['footer_controls']],
        native_execution=False)))
