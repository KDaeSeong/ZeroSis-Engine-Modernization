"""Freeze selected installed BNW popups and compile their XML control trees.

Only the explicitly selected context is supported. This is asset preparation,
not evidence that the original UI engine's layout or dispatch order is matched.
"""
import json
import math
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from ui_bitmap_fonts import load_font

GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
SCRIPTS = (
    ('InstanceManager', 'Assets/UI/InstanceManager.lua'),
    ('IconSupport', 'Assets/UI/IconSupport.lua'),
    ('FLuaVector', 'Assets/Gameplay/Lua/FLuaVector.lua'),
    ('TechButtonInclude', 'Assets/DLC/Expansion2/UI/InGame/TechTree/TechButtonInclude.lua'),
    ('TechHelpInclude', 'Assets/DLC/Expansion2/UI/InGame/TechTree/TechHelpInclude.lua'),
    ('TechTree', 'Assets/DLC/Expansion2/UI/TechTree/TechTree.lua'),
    ('WhosWinningPopup', 'Assets/DLC/Expansion2/UI/InGame/Popups/WhosWinningPopup.lua'),
    ('InfoTooltipInclude', 'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua'),
    ('ProductionPopup', 'Assets/DLC/Expansion2/UI/InGame/Popups/ProductionPopup.lua'),
    ('TechPopup', 'Assets/DLC/Expansion2/UI/InGame/TechPopup.lua'),
)
XML = 'Assets/DLC/Expansion2/UI/InGame/Popups/WhosWinningPopup.xml'
LAYOUTS = (
    ('WhosWinningLayout', XML, None),
    ('ProductionLayout', 'Assets/DLC/Expansion2/UI/InGame/Popups/ProductionPopup.xml', 'Production'),
    ('TechLayout', 'Assets/DLC/Expansion2/UI/InGame/TechPopup.xml', 'Research'),
    ('TechTreeLayout', 'Assets/DLC/Expansion2/UI/InGame/TechTree/TechTree.xml', 'ResearchTree'),
)
KINDS = {'Context', 'Instance', 'Box', 'Image', 'Label', 'Grid', 'ScrollPanel',
         'Stack', 'ScrollBar', 'GridButton', 'Button', 'Container', 'AlphaAnim',
         'DownButton', 'UpButton', 'Meter', 'ScrollAnim', 'ShowOnMouseOver', 'TextureBar', 'GridData'}

ICON_MAPPING_FILES = (
    'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
    'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml',
)
STYLE_SOURCE = 'Assets/UI/Styles.xml'
ICON_FONTS = {
    'FontIcons': 'Assets/DLC/Expansion2/UI/Fonts/Font Icons/FontIcons.ggxml',
    'FontIcons_Expansion2': 'Assets/DLC/Expansion2/UI/Fonts/Font Icons/FontIcons_Expansion2.ggxml',
    'FontIcons_DLC_07': 'Assets/DLC/Shared/UI/Art/Fonts/Font Icons/FontIcons_DLC_07.ggxml',
}


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


def control_tree(element):
    if element.tag not in KINDS:
        raise ValueError('Unsupported selected-popup XML element: ' + element.tag)
    if element.text and element.text.strip():
        raise ValueError('Unexpected mixed XML content')
    return {'kind': element.tag, 'attributes': dict(element.attrib),
            'children': [control_tree(child) for child in element]}


def cpp_literal(data):
    # Adjacent short literals avoid MSVC's single-string token size limit.
    return '\n'.join('"' + ''.join('\\x%02x' % b for b in data[i:i + 64]) + '"'
                     for i in range(0, len(data), 64)) or '""'


def freeze_source(relative, snapshots):
    source = GAME / relative
    target = snapshots / relative
    expected = digest(source)
    if target.exists() and digest(target) != expected:
        raise RuntimeError('Installed UI asset changed from its frozen snapshot: ' + relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        shutil.copy2(source, target)
    if digest(source) != expected or digest(target) != expected:
        raise RuntimeError('UI asset changed during capture')
    return source, target


def inline_icon_catalog(snapshots):
    source_records = {}
    mapping_sources = []
    for relative in ICON_MAPPING_FILES:
        source, frozen = freeze_source(relative, snapshots)
        record = {'path': relative, 'sha256': digest(frozen)}
        source_records[relative] = record
        mapping_sources.append((ET.parse(frozen).getroot(), record))

    font_by_key = {}
    for root, _ in mapping_sources:
        for entry in root.findall('./IconFontTextures/Row'):
            key = entry.findtext('IconFontTexture')
            file_name = entry.findtext('IconFontTextureFile')
            if not key or not file_name:
                raise RuntimeError('Malformed official IconFontTextures Row')
            previous = font_by_key.get(key)
            if previous and previous != file_name:
                raise RuntimeError('Conflicting official icon font texture: ' + key)
            font_by_key[key] = file_name

    fonts = {}
    for file_name, relative in ICON_FONTS.items():
        source, frozen = freeze_source(relative, snapshots)
        font_record = {'path': relative, 'sha256': digest(frozen)}
        source_records[relative] = font_record
        root = ET.parse(frozen).getroot()
        textures = root.findall('./textures/texture')
        glyphs = root.findall('./glyphs/glyph')
        if len(textures) != 1 or not textures[0].get('src'):
            raise RuntimeError('Expected exactly one official font texture in ' + relative)
        glyph_map = {}
        for glyph in glyphs:
            ch = glyph.get('ch')
            if ch is None or ch in glyph_map:
                raise RuntimeError('Missing or duplicate glyph character in ' + relative)
            fields = ('u', 'v', 'width', 'height', 'a', 'b', 'c', 'originx', 'originy')
            if any(glyph.get(field) is None for field in fields):
                raise RuntimeError('Incomplete official glyph metrics in ' + relative)
            glyph_map[ch] = {
                'u': int(glyph.get('u')), 'v': int(glyph.get('v')),
                'width': int(glyph.get('width')), 'height': int(glyph.get('height')),
                'advance': int(glyph.get('a')) + int(glyph.get('b')) + int(glyph.get('c')),
                'originx': int(glyph.get('originx')), 'originy': int(glyph.get('originy')),
            }
        fonts[file_name] = {
            'texture': textures[0].get('src'), 'glyphs': glyph_map,
            'source': font_record,
        }

    catalog = {}
    for root, mapping_source in mapping_sources:
        table = root.find('./IconFontMapping')
        if table is None:
            raise RuntimeError('Missing official IconFontMapping table')
        for row in table:
            if row.tag not in ('Row', 'InsertOrAbort'):
                continue
            name = row.findtext('IconName')
            mapping_text = row.findtext('IconMapping')
            if not name or not name.startswith('ICON_') or not mapping_text:
                raise RuntimeError('Malformed official IconFontMapping ' + row.tag)
            try:
                mapping = int(mapping_text)
            except ValueError as error:
                raise RuntimeError('Noninteger official icon mapping: ' + name) from error
            texture_key = row.findtext('IconFontTexture') or 'ICON_FONT_TEXTURE_DEFAULT'
            if texture_key not in font_by_key:
                raise RuntimeError('Official icon references unknown font texture: ' + texture_key)
            file_name = font_by_key[texture_key]
            font = fonts.get(file_name)
            glyph = font and font['glyphs'].get(str(mapping))
            if glyph is None:
                raise RuntimeError('Official icon mapping has no matching GGXML glyph: ' + name)
            entry = {
                'mapping': mapping, 'texture': font['texture'], 'glyph': glyph,
                'mapping_source': mapping_source,
                'font_source': font['source'],
            }
            if name in catalog:
                # Base Rows are applied before BNW InsertOrAbort. A duplicate
                # InsertOrAbort retains the earlier database row; duplicate
                # Rows are ambiguous and therefore fail closed.
                if row.tag == 'InsertOrAbort':
                    continue
                raise RuntimeError('Duplicate official icon mapping Row: ' + name)
            catalog[name] = entry
    return dict(sorted(catalog.items())), source_records


def production_style_defaults(snapshots, production_tree):
    source, frozen = freeze_source(STYLE_SOURCE, snapshots)
    root = ET.parse(frozen).getroot()
    styles = {element.tag: element for element in root}

    def resolved_node(element, kind=None):
        attributes = {}
        style_name = element.get('Style')
        if style_name:
            style = styles.get(style_name)
            if style is None:
                raise RuntimeError('Production control references missing style: ' + style_name)
            attributes.update(style.attrib)
        attributes.update(element.attrib)
        result = {
            'kind': kind or element.tag,
            'attributes': attributes,
            'children': [resolved_node(child) for child in element],
        }
        if style_name:
            result['style'] = style_name
        return result

    style_names = set()
    def collect(node):
        style_name = node['attributes'].get('Style')
        if style_name:
            style_names.add(style_name)
        for child in node['children']:
            collect(child)
    collect(production_tree)
    result = {}
    for style_name in sorted(style_names):
        element = styles.get(style_name)
        if element is None:
            raise RuntimeError('Production control references missing style: ' + style_name)
        node = resolved_node(element, style_name)
        node['style'] = style_name
        # A slider style's nested Shuttle has its own Style reference and must
        # retain the resolved engine style attributes as source data.
        result[style_name] = node

    if production_tree.get('popupKind') == 'Production':
        for name, expected_size in (('ScrollBarUp', '18,18'), ('ScrollBarDown', '18,18'),
                                    ('VertSlider', '18,18'), ('VertShuttle', '18,18')):
            element = styles.get(name)
            if element is None or element.get('Size') != expected_size:
                raise RuntimeError('Unexpected official production control size for style ' + name)
        if styles['VertSlider'].get('Vertical') != '1' or styles['VertShuttle'].get('Vertical') != '1':
            raise RuntimeError('Unexpected official vertical slider style defaults')
    elif production_tree.get('popupKind') == 'ResearchTree':
        horizontal = styles.get('ScrollBar')
        shuttle = horizontal.find('Shuttle') if horizontal is not None else None
        grid_shuttle = styles.get('Grid3Shuttle')
        if (horizontal is None or horizontal.get('Vertical') != '0' or horizontal.get('Size') != '17,18' or
                shuttle is None or shuttle.get('Style') != 'Grid3Shuttle' or shuttle.get('Size') != '18,18' or
                grid_shuttle is None):
            raise RuntimeError('Unexpected official horizontal TechTree scrollbar defaults')
    return {
        'source': {'path': STYLE_SOURCE, 'sha256': digest(frozen)},
        'controls': result,
        'policy': 'OFFICIAL_STYLES_XML_ATTRIBUTES_WITH_CONTROL_XML_OVERRIDES',
    }


def production_font_metrics(production_tree, inline_icons):
    font_styles = {}
    def collect(node):
        font_id = node['attributes'].get('Font')
        if font_id:
            font_styles.setdefault(font_id, set()).add(node['attributes'].get('FontStyle', 'Base'))
        for child in node['children']:
            collect(child)
    collect(production_tree)

    fonts = {}
    glyph_sets = {}
    for font_id in sorted(font_styles):
        font = load_font(GAME, font_id, 'Base')
        if not font.font_style or 'Base' not in font.styles:
            raise RuntimeError('Production font has no supported Base style: ' + font_id)
        missing_styles = sorted(font_styles[font_id] - set(font.styles))
        if missing_styles:
            raise RuntimeError('Production font lacks referenced styles: ' + font_id + '/' + ','.join(missing_styles))
        glyph_key = font.ggxml_sha256
        if glyph_key not in glyph_sets:
            glyph_sets[glyph_key] = {
                codepoint: {
                    'advance': glyph.abc_advance,
                    'width': glyph.width,
                    'height': glyph.height,
                    'originX': glyph.origin_x,
                    'originY': glyph.origin_y,
                }
                for codepoint, glyph in font.glyphs.items()
            }
        fonts[font_id] = {
            'lineAdvance': font.line_advance,
            'baselineOffset': font.baseline_offset,
            'spacing': font.spacing,
            'fudgeadv': font.fudgeadv,
            'ggxmlPath': font.ggxml_path.relative_to(GAME).as_posix(),
            'sha256': font.ggxml_sha256,
            'glyphSet': glyph_key,
        }

    icons = {}
    for name, entry in inline_icons.items():
        glyph = entry['glyph']
        icons[name] = {
            'advance': glyph['advance'], 'width': glyph['width'], 'height': glyph['height'],
            'originX': glyph['originx'], 'originY': glyph['originy'],
            'texture': entry['texture'], 'mappingSource': entry['mapping_source'],
            'fontSource': entry['font_source'],
        }
    return {
        'policy': 'CIV5_GLYPHGEN_GGXML_LAYOUT_V1',
        'retailMetricSemanticsVerified': False,
        'wrapPolicy': 'GREEDY_ASCII_SPACE_WORD_WRAP_SPLIT_LONG_WORD_AT_CODEPOINT',
        'fonts': fonts,
        'glyphSets': glyph_sets,
        'inlineIcons': icons,
    }


def main():
    root = PROJECT / 'evidence/ui_popup/assets'
    root.mkdir(parents=True, exist_ok=True)
    snapshots = PROJECT / 'Source/Assets/UI'
    inline_icons, inline_sources = inline_icon_catalog(snapshots)
    rows = []
    texts = []
    layout_metadata = {name: kind for name, _, kind in LAYOUTS}
    trees = {}
    for name, relative in (*SCRIPTS, *((name, relative) for name, relative, _ in LAYOUTS)):
        source = GAME / relative
        target = snapshots / relative
        expected = digest(source)
        if target.exists() and digest(target) != expected:
            raise RuntimeError('Installed UI asset changed from its frozen snapshot: ' + relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(source, target)
        if digest(source) != expected or digest(target) != expected:
            raise RuntimeError('UI asset changed during capture')
        data = target.read_bytes()
        if b'\0' in data:
            raise RuntimeError('NUL in UI text asset')
        rows.append({'name': name, 'installed': artifact(source), 'snapshot': artifact(target)})
        if relative.endswith('.lua'):
            texts.append((name, data))
        else:
            tree = control_tree(ET.fromstring(data))
            trees[name] = tree
            kind = layout_metadata[name]
            if kind:
                tree['contextName'] = {
                    'WhosWinningLayout': 'main',
                    'ProductionLayout': 'ProductionPopup',
                    'TechLayout': 'TechPopup',
                    'TechTreeLayout': 'TechTree',
                }[name]
                tree['popupKind'] = kind
                if kind in ('Production', 'Research', 'ResearchTree'):
                    style_defaults = production_style_defaults(snapshots, tree)
                    tree['styleDefaults'] = style_defaults['controls']
                    tree['styleDefaultsSource'] = style_defaults['source']
                    tree['styleDefaultsPolicy'] = style_defaults['policy']
                if kind in ('Production', 'Research', 'ResearchTree'):
                    tree['fontMetrics'] = production_font_metrics(tree, inline_icons)
            texts.append((name, ('ZeroSisUiLayout=' + lua_value(tree) + '\n').encode('ascii')))
    runtime = PROJECT / 'Source/Host/UiScene.lua'
    input_addendum = PROJECT / 'Source/Presentation/UiPresentationInput.lua'
    # Same chunk is essential: input validation uses the retained scene's private
    # state, rather than a second VM or another set of module-local controls.
    texts.append(('ZeroSisUiScene', runtime.read_bytes() + b'\n' + input_addendum.read_bytes()))
    production_guard = PROJECT / 'Source/Host/ProductionCommandGuard.lua'
    texts.append(('ProductionCommandGuard', production_guard.read_bytes()))
    research_guard = PROJECT / 'Source/Host/ResearchCommandGuard.lua'
    texts.append(('ResearchCommandGuard', research_guard.read_bytes()))
    header = ['// Generated by tools/prepare_ui_popup_assets.py; installed originals are unchanged.',
              '#pragma once', '#include <cstddef>', 'namespace ZeroSisHost { namespace UiAssets {',
              'struct Script { const char* name; const char* data; std::size_t size; };']
    for name, data in texts:
        header.append('static const char ' + name + '[]=\n' + cpp_literal(data) + ';')
    header.append('static const Script scripts[]={')
    for name, _ in texts:
        header.append('{"' + name + '",' + name + ',sizeof(' + name + ')-1},')
    header.extend(['};', '} }', ''])
    output = PROJECT / 'Source/Host/UiPopupAssets.generated.h'
    encoded = '\n'.join(header).encode('ascii')
    if not output.exists() or output.read_bytes() != encoded:
        output.write_bytes(encoded)
    icons_output = root / 'inline_icons.json'
    icons_output.write_text(json.dumps({
        'status': 'OFFICIAL_XML_GGXML_STATIC_INDEX_NOT_RENDERER_VERIFIED',
        'icons': inline_icons,
        'source_priority_equivalence_verified': False,
        'atlas_shader_equivalence_verified': False,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    report = {'status': 'INSTALLED_UI_POPUP_ASSETS_PREPARED_NOT_RUNTIME_VERIFIED',
              'builder': artifact(Path(__file__).resolve()), 'inputs': rows,
              'host_ui_runtime': artifact(runtime), 'compiled_assets': artifact(output),
              'host_ui_input_addendum': artifact(input_addendum),
              'production_command_guard': artifact(production_guard),
              'research_command_guard': artifact(research_guard),
              'inline_icon_catalog': artifact(icons_output),
              'inline_icon_sources': inline_sources,
              'production_style_defaults_source': artifact(snapshots / STYLE_SOURCE),
              'xml_control_tree': trees['WhosWinningLayout'],
              'xml_control_trees': trees,
              'selection': 'EXPLICIT_BNW_WHOS_WINNING_PRODUCTION_AND_RESEARCH_POPUP_WITH_UI_DEPENDENCIES',
              'stock_asset_search_order_verified': False, 'renderer_verified': False}
    (root / 'prepared.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print(json.dumps({'status': report['status'], 'official_assets': len(rows),
                      'compiled_bytes': len(encoded)}))


if __name__ == '__main__':
    main()
