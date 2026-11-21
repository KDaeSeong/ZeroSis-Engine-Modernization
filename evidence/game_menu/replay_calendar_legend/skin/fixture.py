"""Stdlib file-only package/backend/style/cache regression checks."""
from __future__ import annotations

from copy import deepcopy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import struct
import sys
import tempfile
import xml.etree.ElementTree as ET

STAGE = Path(__file__).resolve().parent
PROJECT = STAGE.parents[3]
sys.path.insert(0, str(PROJECT / 'tools'))
from menu_frontend_skin import (FrontEndSkin, PACKAGE_SPECS, GAME, BACKEND,
    OFFICIAL_RULE_ICON_SOURCES, artifact, require)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data if isinstance(data, bytes) else data.encode('utf8'))


def fail(call):
    try:
        call()
    except (ValueError, KeyError):
        return
    raise AssertionError('Malformed fixture was accepted')


def package(spec):
    name, skin, _, guid, priority, pak = spec
    root = ET.Element('Civ5Package')
    ET.SubElement(root, 'GUID').text = guid
    ET.SubElement(root, 'Priority').text = str(priority)
    selected = ET.SubElement(ET.SubElement(root, 'UISkin', name=skin, set=name, platform='Common'), 'Skin')
    for tag, value in [('Directory', 'UI/Frontend'), ('Directory', 'UI/Options'),
                       ('Style', 'UI/Styles_' + name + '.xml')]:
        ET.SubElement(selected, tag).text = value
    ET.SubElement(ET.SubElement(selected, 'Paks'), 'File').text = pak
    # The tablet branch intentionally has a nonexistent directory and must not
    # participate in this explicit desktop/Common resource profile.
    tablet = ET.SubElement(ET.SubElement(root, 'UISkin', name=skin, set=name, platform='Tablet'), 'Skin')
    ET.SubElement(tablet, 'Directory').text = 'UI_Tablet'
    return ET.tostring(root)


def fpk(path, value, name=b'x.dds'):
    padding = (-len(name)) % 4
    encoded = name + (bytes([padding]) + bytes(padding - 1) if padding else b'')
    offset = 14 + 4 + len(encoded) + 16
    write(path, struct.pack('<I', 6) + b'FPK_\0\0' + struct.pack('<II', 1, len(name)) +
          encoded + struct.pack('<QII', 0, len(value), offset) + value)


def setup(root):
    game = root / 'game'
    backend = root / 'backend'
    for spec in PACKAGE_SPECS:
        folder = game / spec[2]
        write(folder, package(spec))
        write(folder.parent / ('UI/Styles_' + spec[0] + '.xml'),
              '<Styles><Shared Texture="' + spec[0] + '.dds"/><' + spec[0] + 'Only/></Styles>')
    write(game / 'Assets/UI/Styles.xml', '<Styles><Shared Texture="base.dds"/><BaseOnly/></Styles>')
    footer = '<Context><Button ID="%s" Offset="0,%d"/></Context>'
    for name, control in [('MainMenu.xml', 'ExitButton'), ('SinglePlayer.xml', 'BackButton')]:
        write(game / 'Assets/UI/FrontEnd' / name, footer % (control, 44))
        write(game / 'Assets/DLC/Expansion/UI/FrontEnd' / name, footer % (control, 60))
    write(game / 'Assets/UI/FrontEnd/FrontEnd.xml', '<Context/>')
    write(game / 'Assets/UI/Options/OptionsMenu.xml', '<Context/>')
    for name in ('Expansion2UITextures.fpk', 'Expansion1UITextures.fpk', 'UITextures.fpk', 'Upgrade1Textures.fpk'):
        fpk(game / 'Resource/DX9' / name, (name.encode('ascii') + bytes(128)))
    write(game / 'Assets/DLC/Shared/Upgrade1.Civ5Pkg',
          '<Civ5Package><GUID>{8871E748-29A4-4910-8C57-8C99E32D0167}</GUID>'
          '<Paks><File>Upgrade1Textures.fpk</File></Paks></Civ5Package>')
    image = bytearray(128)
    image[:2] = b'MZ'
    struct.pack_into('<I', image, 60, 64)
    image[64:68] = b'PE\0\0'
    struct.pack_into('<H', image, 68, 0x8664)
    struct.pack_into('<H', image, 86, 0x2000)
    struct.pack_into('<H', image, 88, 0x20b)
    write(backend / 'CvGameCoreDLL_Expansion2_x64.dll', bytes(image))
    with closing(sqlite3.connect(backend / 'rules.db')) as db:
        db.execute('CREATE TABLE IconTextureAtlases (Atlas TEXT,IconSize INTEGER,Filename TEXT,IconsPerRow TEXT,IconsPerColumn TEXT)')
        db.commit()
    manifest = backend / 'bundle.manifest'
    write(manifest, 'ZEROSIS_HOST_BUNDLE_V4\n' + '\n'.join(name + '|' + digest(backend / name)
          for name in ('CvGameCoreDLL_Expansion2_x64.dll', 'rules.db')) + '\n')
    return game, manifest


def synthetic(root):
    game, manifest = setup(root)
    checks = []
    skin = FrontEndSkin(game, manifest)
    require(skin.resolve('UI/FrontEnd/MainMenu.xml')['layer'] == 'Expansion1', 'Expansion1 fallback was not selected')
    require(skin.resolve('UI/Options/OptionsMenu.xml')['layer'] == 'BaseGame', 'Base options fallback was not selected')
    checks += ['COMMON_EXPANSION1_SOURCE_FALLBACK', 'BASE_OPTIONS_FALLBACK']
    write(game / 'Assets/DLC/Expansion2/UI/FrontEnd/MainMenu.xml', '<Context><Button ID="ExitButton" Offset="0,70"/></Context>')
    require(FrontEndSkin(game, manifest).resolve('UI/Frontend/MainMenu.xml')['layer'] == 'Expansion2', 'Priority200 was ignored')
    checks.append('PRIORITY200_CASE_INSENSITIVE_WINNER')
    fail(lambda: skin.resolve('../UI/FrontEnd/MainMenu.xml'))
    fail(lambda: skin.resolve('/UI/FrontEnd/MainMenu.xml'))
    fail(lambda: skin.resolve('UI/FrontEnd/../../settings.ini'))
    checks.append('ESCAPING_OR_ABSOLUTE_LOGICAL_PATHS_REJECTED')
    fail(lambda: skin.resolve('UI_Tablet/FrontEnd/MainMenu.xml'))
    fail(lambda: skin.resolve('UI/InGame/Popups/ReplayViewer.xml'))
    fail(lambda: skin.resolve('UI/FrontEnd/UninstalledMod.xml'))
    checks.append('TABLET_GAMEPLAY_AND_UNDECLARED_RESOURCES_EXCLUDED')
    styles = skin.selected_style_elements()
    require(styles['Shared'].get('Texture') == 'Expansion2.dds' and 'BaseOnly' in styles and 'Expansion1Only' in styles,
            'Original style overlay or fallback was lost')
    styles['Shared'].set('Texture', 'caller-mutation')
    require(skin.selected_style_elements()['Shared'].get('Texture') == 'Expansion2.dds', 'Style API leaked mutable state')
    checks += ['BASE_TO_EXPANSION2_STYLE_OVERLAY', 'STYLE_RESULTS_OWNED_BY_CALLER']
    selected = skin.texture('UI/Art/X.dds')
    require(selected['layer'] == 'Expansion2' and len(selected['candidates']) == 4, 'Texture priority omitted candidates')
    record = dict(basename='x.dds', source=selected['source'], index_source=None)
    require(skin.verify_texture_records([record]), 'Actual active texture cache rejected')
    bad = deepcopy(record)
    bad['source']['sha256'] = '0' * 64
    fail(lambda: skin.verify_texture_records([bad]))
    checks += ['DECLARED_TEXTURE_PRIORITY', 'CACHED_OLD_TEXTURE_CANNOT_HIDE_WINNER']
    manifest_bytes = manifest.read_bytes()
    write(manifest, manifest_bytes + b'CvGameCoreDLL_Expansion2_x64.dll|' + b'0' * 64 + b'\n')
    fail(lambda: FrontEndSkin(game, manifest))
    write(manifest, manifest_bytes)
    checks.append('DUPLICATE_BACKEND_BINDING_REJECTED')
    dll = manifest.parent / 'CvGameCoreDLL_Expansion2_x64.dll'
    old = dll.read_bytes()
    write(dll, old + b'changed')
    fail(lambda: FrontEndSkin(game, manifest))
    write(dll, old)
    checks.append('CHANGED_BACKEND_DLL_REJECTED')
    package_path = game / PACKAGE_SPECS[0][2]
    old = package_path.read_bytes()
    write(package_path, old.replace(b'<Priority>200</Priority>', b'<Priority>201</Priority>'))
    fail(lambda: FrontEndSkin(game, manifest))
    write(package_path, old)
    checks.append('CHANGED_ORIGINAL_PACKAGE_PRIORITY_REJECTED')
    style_path = game / 'Assets/DLC/Expansion2/UI/Styles_Expansion2.xml'
    write(style_path, '<Styles><Duplicate Texture="a"/><Duplicate Texture="b"/></Styles>')
    fail(lambda: FrontEndSkin(game, manifest).selected_style_elements())
    checks.append('CONFLICTING_STYLE_DUPLICATES_REJECTED')
    drift = FrontEndSkin(game, manifest)
    drift.resolve('UI/FrontEnd/FrontEnd.xml')
    require(drift.unchanged(), 'Fresh drift baseline was not stable')
    write(game / 'Assets/UI/FrontEnd/FrontEnd.xml', '<Context Changed="1"/>')
    require(not drift.unchanged(), 'Changed pinned original was not detected')
    checks.append('ORIGINAL_INPUT_DRIFT_DETECTED')
    basename = 'civsymbolscolor32_dlc_01.dds'
    relative, guid, pack = OFFICIAL_RULE_ICON_SOURCES[basename]
    write(game / 'Assets/DLC' / relative,
          '<Civ5Package><GUID>' + guid + '</GUID><Paks><File>' + pack + '</File></Paks></Civ5Package>')
    fpk(game / 'Resource/DX9' / pack, bytes(128), basename.encode('ascii'))
    for dimensions, valid in [(('1', '2'), True), (('1.0', '2'), False),
                              (('-1', '2'), False), (('01', '2'), False), (('1', '8193'), False)]:
        with closing(sqlite3.connect(manifest.parent / 'rules.db')) as db:
            db.execute('DELETE FROM IconTextureAtlases')
            db.execute('INSERT INTO IconTextureAtlases VALUES (?,?,?,?,?)',
                       ('MONGOL_COLOR_ATLAS', 32, basename, *dimensions))
            db.commit()
        write(manifest, 'ZEROSIS_HOST_BUNDLE_V4\n' + '\n'.join(name + '|' + digest(manifest.parent / name)
              for name in ('CvGameCoreDLL_Expansion2_x64.dll', 'rules.db')) + '\n')
        candidate = FrontEndSkin(game, manifest)
        if valid:
            require(candidate.texture(basename)['activates_dlc_or_mod'] is False,
                    'Rules-referenced artwork declared gameplay activation')
        else:
            fail(lambda: candidate.texture(basename))
    checks.append('CANONICAL_RULE_ATLAS_TEXT_DIMENSIONS_VALIDATED')
    return checks


def main():
    owned = Path(tempfile.mkdtemp(prefix='.fixture-', dir=STAGE))
    require(owned.resolve().is_relative_to(STAGE.resolve()) and owned.name.startswith('.fixture-'),
            'Fixture output escaped its exact evidence directory')
    temporary_rows = []
    try:
        checks = synthetic(owned)
        # Reuse every immutable V2 payload; inspect sources only, without
        # copying textures or invoking the renderer/compiler/native code.
        import civ5_ui_assets
        civ5_ui_assets.LOOSE_UI_TEXTURES['fonticons_dlc_07.dds'] = dict(
            relative_path='Assets/DLC/Shared/UI/Art/Fonts/Font Icons/FontIcons_DLC_07.dds',
            bytes=4000, sha256='ac3acd71484003d674ee85f1a95cfdb9c80e125c4307ae323d6e3d9bd28f53a9')
        original = json.loads((PROJECT / 'evidence/game_menu/menu_runtime_ui_followup/frontend/assets_v2.json').read_text('utf8'))
        skin = FrontEndSkin(GAME, BACKEND)
        active = skin.provenance()
        skin.verify_texture_records(original['original_texture_sources'])
        icons = [skin.texture(name) for name in OFFICIAL_RULE_ICON_SOURCES]
        require(all(row['activates_dlc_or_mod'] is False for row in icons), 'Artwork resolution declared content activation')
        require(skin.unchanged(), 'Actual original/backend sources changed during read-only fixture')
        actual = dict(resolved_sources=len(active['sources']), selected_styles=len(active['styles']),
            footer_offsets=[row['attributes']['Offset'] for row in active['footer_controls']],
            inherited_texture_records_verified=len(original['original_texture_sources']),
            additional_official_rule_atlases=len(icons), protected_original_inputs_unchanged=True)
        require(actual['footer_offsets'] == ['0,60', '0,60'], 'Installed active skin footer differs')
        for path in owned.rglob('*'):
            if path.is_file():
                temporary_rows.append(dict(path=str(path), bytes=path.stat().st_size, sha256=digest(path)))
        # Write only small provenance; FPK entries/fonts are never copied.
        for name, value in [('active_skin_resolution.json', active), ('official_rule_atlases.json', icons)]:
            (STAGE / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    finally:
        require(owned.resolve().is_relative_to(STAGE.resolve()), 'Fixture cleanup target escaped its owned directory')
        shutil.rmtree(owned)
    result = dict(schema='zerosis.original_frontend.skin.file_fixture.v1',
        status='PASS_EXPLICIT_EXPANSION2_SKIN_FILE_ONLY', checks=checks, actual=actual,
        cleanup=dict(files=len(temporary_rows), bytes=sum(row['bytes'] for row in temporary_rows),
                     deleted=not owned.exists(), records=temporary_rows),
        source_inputs=[artifact(PROJECT / 'tools/menu_frontend_skin.py'),
                       artifact(PROJECT / 'tools/menu_frontend_skin_pages.py'), artifact(__file__)],
        native_execution=False, host_or_sdk_or_window_executed=False, gpu_execution=False,
        original_game_settings_or_saves_written=False)
    (STAGE / 'fixture_result.json').write_text(json.dumps(result, indent=2, ensure_ascii=False) + '\n', encoding='utf8')
    print(json.dumps(dict(status=result['status'], checks=len(checks), **actual,
                          temporary_files_deleted=len(temporary_rows), native_execution=False)))


if __name__ == '__main__':
    main()
