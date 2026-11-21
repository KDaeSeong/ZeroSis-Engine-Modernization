"""Selected-layout geometry examples, rather than renderer implementation mirrors."""
from pathlib import Path
import json
import os
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from ui_pixel_scene import (KINDS, anchor, intersect, positive, pair, rect, markup, glyph_quad, grid_targets,
                            scroll_mask_rgba, meter_arc_rgba, scrollbar_thumb_bounds,
                            button_source_rect, validate_hit_regions, bounds_size,
                            scroll_extent, texture_bar_regions, wrap_production_text,
                            production_line_advance, research_scrollbar_thumb_bounds,
                            research_tree_scrollbar_thumb_bounds, RESEARCH_POPUP_ENUM_VALUE,
                            RESEARCH_TREE_POPUP_ENUM_VALUE, DIPLO_UI_STATE_DEFAULT_ROOT_ENUM_VALUE,
                            LEADERHEAD_ANIM_INTRO_ENUM_VALUE, close_stock_top_panel_negative_gold_label,
                            font_layer_colors, image_regions,
                            centered_button_text_bounds, inline_tab_glyph, Compiler, owned_font_input_binding)
from ui_bitmap_fonts import load_font, layout_text
from civ5_ui_assets import Fpk, PACK_POLICY, decode_dds
from render_ui_popup import retained_bounds

PROJECT = Path(__file__).resolve().parents[1]
FONT_BINDING = owned_font_input_binding(json.loads(
    (PROJECT / 'evidence/ui_popup/assets/prepared.json').read_text(encoding='utf-8')))
assert FONT_BINDING is not None, 'Candidate geometry tests require their frozen owned font inputs'
FONTS_ROOT = Path(FONT_BINDING['asset_root'])


def owned_compiler(game_root, destination, **kwargs):
    return Compiler(game_root, destination, font_root=FONTS_ROOT, font_binding=FONT_BINDING, **kwargs)


checks = 0


def check(ok):
    global checks
    assert ok
    checks += 1


check(DIPLO_UI_STATE_DEFAULT_ROOT_ENUM_VALUE == 0 and LEADERHEAD_ANIM_INTRO_ENUM_VALUE == 1)
check(centered_button_text_bounds((10, 20, 200, 32), 100, 20, (0, -2)) == (60.0, 24.0, 100, 20))


def reject(call):
    try:
        call()
    except (ValueError, TypeError):
        check(True)
    else:
        raise AssertionError('Bad geometry was accepted')


reject(lambda: centered_button_text_bounds((10, 20, 200, 32), 201, 20, (0, -2)))
reject(lambda: centered_button_text_bounds((10, 20, 200, 32), 100, 33, (0, -2)))


check(anchor({'Anchor': 'C,C', 'Offset': '0.0'}, (0, 0, 1920, 1080), 493, 700) == (713.5, 190, 493, 700))
grid = (713.5, 190, 493, 700)
check(anchor({'Anchor': 'L,T', 'Offset': '14,44'}, grid, 466, 60) == (727.5, 234, 466, 60))
check(anchor({'Anchor': 'C,C', 'Offset': '0,-3'}, (727.5, 234, 466, 60), 280, 25) == (820.5, 248.5, 280, 25))
check(anchor({'Anchor': 'R,C', 'Offset': '0,0'}, (731.5, 286, 420, 60), 12, 25) == (1139.5, 303.5, 12, 25))
check(anchor({'Anchor': 'L,C', 'Offset': '0,0'}, (731.5, 286, 420, 60), 64, 64) == (731.5, 284, 64, 64))
check(anchor({'Anchor': 'L,C', 'Offset': '0,0'}, (731.5, 346, 420, 60), 64, 64) == (731.5, 344, 64, 64))
check(anchor({'Anchor': 'C,B', 'Offset': '0,54'}, grid, 458, 70) == (731, 766, 458, 70))
check(anchor({'Anchor': 'L,B', 'Offset': '14,0'}, (731, 766, 458, 70), 150, 32) == (745, 804, 150, 32))
check(anchor({'Anchor': 'R,C', 'AnchorSide': 'O,I', 'Offset': '3,0'}, (731.5, 286, 428, 490), 18, 488) == (1162.5, 287, 18, 488))
check(anchor({'Anchor': 'R,B', 'AnchorSide': 'i,o', 'Offset': '19,0'},
             (100, 200, 500, 300), 18, 18) == (563, 500, 18, 18))
check(intersect((731.5, 284, 795.5, 348), (731.5, 286, 1159.5, 776)) == (731.5, 286, 795.5, 348))
check(intersect((773.5, 345, 1173.5, 346), (731.5, 286, 1159.5, 776)) == (773.5, 345, 1159.5, 346))
check(positive((0, 0, 1, 1)) and not positive((0, 0, 0, 1)))
check(not positive(intersect((0, 0, 1, 1), (2, 2, 3, 3))))
production_thumb = scrollbar_thumb_bounds((2, 214, 18, 680), 0, 684, 18)
check(production_thumb == (2, 214, 20, 214 + 680 * 680 / 684))
check(production_thumb[2] - production_thumb[0] == 18 and
      production_thumb[3] - production_thumb[1] >= 6)
reject(lambda: scrollbar_thumb_bounds((2, 214, 18, 680), -1, 684, 18))
check(bounds_size((35, 196, 340, 684)) == (340, 684))
check(scroll_extent((2, 214, 18, 680), 684) == 4)
check(scroll_extent((35, 196, 340, 684), 684) == 0)
check(research_scrollbar_thumb_bounds((2, 214, 18, 680), 0, 640, 18) ==
      (2, 214, 20, 894))
research_thumb = research_scrollbar_thumb_bounds((2, 214, 18, 680), 40, 1000, 18)
check(research_thumb[0] == 2 and research_thumb[2] == 20 and
      research_thumb[1] > 214 and research_thumb[3] < 894)
tree_thumb = research_tree_scrollbar_thumb_bounds((100, 40, 500, 18), 0, 1000, 600, 18)
check(tree_thumb == (100, 40, 400, 58))
tree_thumb_mid = research_tree_scrollbar_thumb_bounds((100, 40, 500, 18), 200, 1000, 600, 18)
check(tree_thumb_mid == (200, 40, 500, 58))
check(research_tree_scrollbar_thumb_bounds((100, 40, 500, 18), 0, 400, 600, 18) ==
      (100, 40, 600, 58))
reject(lambda: research_tree_scrollbar_thumb_bounds((100, 40, 500, 18), 401, 1000, 600, 18))
reject(lambda: research_scrollbar_thumb_bounds((2, 214, 18, 680), 1, 640, 18))
growth_source, growth_target = texture_bar_regions((15, 80, 54, 54), 'Up', .5, 54, 54)
check(growth_source == (0, 27, 54, 54) and growth_target == (15, 107, 69, 134))
check(rect((8, 906, 128, 128)) == (8, 906, 136, 1034))
fixture_buttons = [{'key': 201, 'kind': 'GridButton', 'id': 'CloseButton', 'style_decoration': False},
                    {'key': 202, 'kind': 'GridButton', 'id': 'PurchaseButton', 'style_decoration': False}]
fixture_buttons[0]['input_target'] = fixture_buttons[1]['input_target'] = True
validate_hit_regions('production', [(201, 1, 1, 2, 2), (202, 3, 3, 4, 4)], fixture_buttons)
validate_hit_regions('ranking', [(201, 1, 1, 2, 2)], fixture_buttons)
reject(lambda: validate_hit_regions('production', [(202, 3, 3, 4, 4)], fixture_buttons))
reject(lambda: validate_hit_regions('ranking', [(201, 1, 1, 2, 2), (202, 3, 3, 4, 4)], fixture_buttons))
leader_buttons = [dict(key=13, kind='GridButton', id='BackButton', style_decoration=False,
                       input_target=True, input_targets=['LeftClick']),
                  dict(key=17, kind='GridButton', id='WarButton', style_decoration=False,
                       input_target=True, input_targets=['LeftClick'])]
leader_hits = [(13, 1680, 1008, 1880, 1040), (17, 1680, 840, 1880, 872)]
validate_hit_regions('diplomacy', leader_hits, leader_buttons)
check(True)
reject(lambda: validate_hit_regions('diplomacy', leader_hits,
    [dict(leader_buttons[0], id='CloseButton'), leader_buttons[1]]))
reject(lambda: validate_hit_regions('diplomacy', leader_hits,
    [dict(leader_buttons[0], input_targets=['LeftClick', 'RightClick']), leader_buttons[1]]))
reject(lambda: validate_hit_regions('diplomacy', leader_hits,
    [leader_buttons[0], dict(leader_buttons[1], id='BackButton')]))
check(pair('32.32') == (32, 32) and pair('0,-3') == (0, -3))
reject(lambda: pair('Full,2'))
reject(lambda: pair('0,0,0'))
base_color = (0.93, 0.83, 0.52, 1.0)
effect_color = (0.0, 0.0, 0.0, 200 / 255)
resolved, layer_policy = font_layer_colors((base_color, effect_color), 3,
                                            font_style='SoftShadow', color_set='Beige_Black_Alpha')
check(resolved == (base_color, effect_color, effect_color) and
      layer_policy == 'ZEROSIS_CANDIDATE_REPEAT_LAST_EFFECT_COLOR_FOR_SOFTSHADOW')
check(font_layer_colors((base_color, effect_color), 2,
                        font_style='Shadow', color_set='Beige_Black_Alpha') ==
      ((base_color, effect_color), 'SOURCE_COLORSET_EXACT_LAYER_COUNT'))
check(font_layer_colors((base_color, effect_color, (1.0, 0.0, 0.0, 1.0)), 2,
                        font_style='Shadow', color_set='Beige_Black_Alpha') ==
      ((base_color, effect_color), 'SOURCE_COLORSET_UNUSED_TRAILING_COLORS'))
reject(lambda: font_layer_colors((base_color, effect_color), 3,
                                 font_style='SoftShadow', color_set='OtherTwoColorSet'))
reject(lambda: font_layer_colors((base_color,), 3,
                                 font_style='SoftShadow', color_set='Beige_Black_Alpha'))
reject(lambda: font_layer_colors((base_color, effect_color), 4,
                                 font_style='Shadow', color_set='Beige_Black_Alpha'))
check(image_regions(0, 0, (10, 20, 32, 212), (21, 84), stretch_full_texture=True) ==
      ((0, 0, 21, 84), (10, 20, 42, 232),
       'ZEROSIS_CANDIDATE_STRETCH_FULL_TECHPIPE_TEXTURE_TO_RETAINED_BOUNDS'))
check(image_regions(72, 0, (10, 20, 32, 42), (105, 420)) ==
       ((72, 0, 104, 42), (10, 20, 42, 62), 'SOURCE_REGION_MATCHES_RETAINED_BOUNDS'))
check(image_regions(72, 72, (10, 20, 32, 42), (105, 105),
                    source_extent=(32, 32)) ==
      ((72, 72, 104, 104), (10, 20, 42, 62),
       'ZEROSIS_CANDIDATE_STRETCH_TECHBRANCH_32PX_ATLAS_CELL_TO_RETAINED_BOUNDS'))
reject(lambda: image_regions(1, 0, (10, 20, 32, 212), (21, 84), stretch_full_texture=True))
reject(lambda: image_regions(0, 0, (10, 20, 32, 212), (21, 84)))
reject(lambda: image_regions(72, 72, (10, 20, 32, 42), (105, 105)))
reject(lambda: image_regions(72, 72, (10, 20, 32, 42), (105, 105),
                            source_extent=(32, 42)))
check(anchor({'Anchor': 'C,C', 'AnchorSide': 'O.I', 'Offset': '0,-2'},
             (0, 0, 70, 24), 54, 25) == (8, -2.5, 54, 25))
reject(lambda: anchor({'Anchor': 'L,Z'}, (0, 0, 100, 100), 20, 20))
green = (0.0, 1.0, 0.0, 1.0)
plain, colors = markup('[COLOR_POSITIVE_TEXT]1.[ENDCOLOR] 당신', {'COLOR_POSITIVE_TEXT': green})
check(plain == '1. 당신' and colors == [green, green, None, None, None])
plain, colors = markup('A[NEWLINE]B', {})
check(plain == 'A\nB' and colors == [None] * 3)
plain, colors = markup('[NEWLINE][TAB][TAB]A[NEWLINE][TAB][TAB]B', {})
check(plain == '\n\t\tA\n\t\tB' and colors == [None] * len(plain))
reject(lambda: markup('[COLOR_MISSING]A[ENDCOLOR]', {}))
reject(lambda: markup('[UNSUPPORTED_TOKEN]A', {}))
reject(lambda: markup('A[ENDCOLOR]', {}))
reject(lambda: markup('[COLOR_POSITIVE_TEXT]A', {'COLOR_POSITIVE_TEXT': green}))
rome_rgba = (150 / 255, 120 / 255, 255 / 255, 255 / 255)
plain, colors = markup(
    '[COLOR:150:120:255:255]로마[ENDCOLOR]의 [COLOR_POSITIVE_TEXT]아우구스투스[ENDCOLOR]',
    {'COLOR_POSITIVE_TEXT': green})
check(plain == '로마의 아우구스투스' and
      colors == [rome_rgba, rome_rgba, None, None, green, green, green, green, green, green])
plain, colors = markup('X[COLOR:150:120:255:255]로마[COLOR_POSITIVE_TEXT]의[ENDCOLOR] [ENDCOLOR]A',
                       {'COLOR_POSITIVE_TEXT': green})
check(plain == 'X로마의 A' and colors == [None, rome_rgba, rome_rgba, green, rome_rgba, None])
plain, colors = markup('[COLOR:0:128:255:0]Z[ENDCOLOR]', {})
check(plain == 'Z' and colors == [(0.0, 128 / 255, 1.0, 0.0)])
for invalid_rgba in ('[COLOR:1:2:3]X[ENDCOLOR]', '[COLOR:1:2:3:4:5]X[ENDCOLOR]',
                     '[COLOR:-1:2:3:4]X[ENDCOLOR]', '[COLOR:1:2:3.5:4]X[ENDCOLOR]',
                     '[COLOR:1:2:NaN:4]X[ENDCOLOR]', '[COLOR:1:2::4]X[ENDCOLOR]',
                     '[COLOR:1:2:3:256]X[ENDCOLOR]', '[COLOR:999999999999999999999999999999:2:3:4]X[ENDCOLOR]'):
    reject(lambda invalid_rgba=invalid_rgba: markup(invalid_rgba, {}))
reject(lambda: markup('[COLOR:1:2:3:4]X[ENDCOLOR]Y[ENDCOLOR]', {}))
reject(lambda: markup('[ICON_FOOD]', {}))
food = {'texture': 'FontIcons.dds', 'mapping': 5, 'u': 88, 'v': 0, 'width': 22, 'height': 22,
        'advance': 22, 'originx': 0, 'originy': 22}
plain, colors, icons = markup('A[ICON_FOOD]B', {}, {'ICON_FOOD': food})
check(plain == 'A\U000f0000B' and colors == [None, None, None] and icons == {0xF0000: food})
stock_negative_gold = '[ICON_GOLD][COLOR:255:235:0:255]"4180" [COLOR:255:60:60:255](-1)"[ENDCOLOR]'
balanced_negative_gold = close_stock_top_panel_negative_gold_label(
    stock_negative_gold, context='top-panel', control_id='GoldPerTurn', kind='TextButton')
plain, colors, icons = markup(balanced_negative_gold, {}, {'ICON_GOLD': food})
yellow = (1.0, 235 / 255, 0.0, 1.0)
red = (1.0, 60 / 255, 60 / 255, 1.0)
check(stock_negative_gold == '[ICON_GOLD][COLOR:255:235:0:255]"4180" [COLOR:255:60:60:255](-1)"[ENDCOLOR]' and
      plain == '\U000f0000"4180" (-1)"' and
      colors == [None] + [yellow] * 7 + [red] * 5 and icons == {0xF0000: food})
unquoted_negative_gold = '[ICON_GOLD][COLOR:255:235:0:255]4180 [COLOR:255:60:60:255](-1)[/COLOR]'
plain, colors, _ = markup(close_stock_top_panel_negative_gold_label(
    unquoted_negative_gold, context='top-panel', control_id='GoldPerTurn', kind='TextButton'),
    {}, {'ICON_GOLD': food})
check(plain == '\U000f00004180 (-1)' and colors == [None] + [yellow] * 5 + [red] * 4)
for rejected_gold_markup, context, control_id, kind in (
        (stock_negative_gold.replace('255:60:60:255', '255:60:61:255'), 'top-panel', 'GoldPerTurn', 'TextButton'),
        (stock_negative_gold, 'production', 'GoldPerTurn', 'TextButton'),
        (stock_negative_gold, 'top-panel', 'SciencePerTurn', 'TextButton'),
        (stock_negative_gold.replace('[ENDCOLOR]', '[ENDCOLOR]tail'), 'top-panel', 'GoldPerTurn', 'TextButton'),
        (stock_negative_gold.replace('[COLOR:255:60:60:255]',
                                      '[COLOR:255:60:60:255][COLOR:0:0:0:255]'),
         'top-panel', 'GoldPerTurn', 'TextButton')):
    unmodified = close_stock_top_panel_negative_gold_label(
        rejected_gold_markup, context=context, control_id=control_id, kind=kind)
    check(unmodified == rejected_gold_markup)
    reject(lambda unmodified=unmodified: markup(unmodified, {}, {'ICON_GOLD': food}))
reject(lambda: markup('[ICON_MISSING]', {}, {}))
texture = bytes([1, 2, 3, 200] * 2 + [4, 5, 6, 100] * 2 + [7, 8, 9, 80] * 2 + [10, 11, 12, 40] * 2)
mask = bytes([0, 0, 0, 255] * 2 + [0, 0, 0, 128] * 2)
masked = scroll_mask_rgba(texture, 2, 4, mask, 2, 2, 2, 2, .5)
check(masked == bytes([4, 5, 6, 100] * 2 + [7, 8, 9, 40] * 2))
stretched = scroll_mask_rgba(texture, 2, 4, mask, 2, 2, 4, 3, .5)
check(len(stretched) == 4 * 3 * 4 and
      [stretched[i] for i in range(0, len(stretched), 4)] ==
      [4] * 4 + [7] * 4 + [10] * 4)
wide_texture = bytes([1,0,0,255, 2,0,0,255, 3,0,0,255, 4,0,0,255])
one_pixel_mask = bytes([0,0,0,255])
wide_output = scroll_mask_rgba(wide_texture, 2, 2, one_pixel_mask, 1, 1, 4, 2, 0)
check([wide_output[i] for i in range(0, len(wide_output), 4)] == [1, 1, 2, 2, 3, 3, 4, 4])
offset_sample = scroll_mask_rgba(texture, 2, 4, mask, 2, 2, 2, 2, 1, 0, 1)
check(offset_sample == bytes([7, 8, 9, 80] * 2 + [10, 11, 12, 20] * 2))
reject(lambda: scroll_mask_rgba(texture, 2, 4, mask, 2, 2, 2, 2, 1.1))
reject(lambda: scroll_mask_rgba(texture, 2, 4, mask, 2, 2, 2, 2, 0, 2, 0))
reject(lambda: scroll_mask_rgba(texture, 2, 4, mask, 2, 2, 2, 2, 0, 0, 4))
reject(lambda: scroll_mask_rgba(texture, 2, 4, mask, 2, 2, 2, 2, 0, -1, 0))
reject(lambda: scroll_mask_rgba(texture, 2, 4, mask, 2, 2, 32768, 32768, 0))
meter = bytes([1, 2, 3, 255] * 4)
arc = meter_arc_rgba(meter, 2, 2, .25, .25)
check([arc[i + 3] for i in range(0, len(arc), 4)] == [0, 255, 0, 255])
reject(lambda: meter_arc_rgba(meter, 2, 2, -0.1, 0))
# The sealed candidate atlas proves that sampling only the declared glyph width erases
# the lower-case l. Verify every nonzero mask pixel in that authored cell is
# retained by the padded quad, without changing its ABC advance.
font = load_font(FONTS_ROOT, 'TwCenMT22', 'Shadow')
glyph = layout_text('l', font).placements[0]
(u, v, qw, qh), border = glyph_quad(glyph, font)
data = font.layers[0].sheet.path.read_bytes()
points = [(x, y) for y in range(32) for x in range(32)
          if data[128 + (v + y) * font.texture_width + u + x] > 0]
check(points and all(x < qw and y < qh for x, y in points))
check(any(x >= glyph.texture_rect[2] for x, y in points))
# Effect masks may bleed between padded cells. Their exact retail sampling
# convention has not been established; do not attribute a whole shadow cell
# to this glyph or claim shadow-mask pixel equivalence from this base check.
check(glyph.advance == font.glyphs[ord('l')].abc_advance and border == 2.5)
# Real GlyphGen inputs keep the same compiler provenance and authored atlas bytes.
with tempfile.TemporaryDirectory(prefix='zeros-font-scenes-') as font_temp:
    font_build = Path(font_temp) / 'Build'
    font_run = font_build / 'InteractiveGameRuntime' / ('20261010T120000Z_' + 'a' * 12) / 'sessions' / ('b' * 32)
    compilers = []
    for destination in (font_run / 'play-ui-1', font_run / 'play-ui-2', Path(font_temp) / 'standalone'):
        compiler = Compiler.__new__(Compiler)
        compiler.game_root = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
        compiler.font_root = FONTS_ROOT
        compiler.font_input_refs = {Path(row['path']): dict(row) for row in FONT_BINDING['inputs']}
        compiler.destination = destination.resolve()
        compiler.fonts, compiler.font_records = {}, []
        compiler.font('TwCenMT22', 'Shadow')
        compilers.append(compiler)
    records = [compiler.font_records[0] for compiler in compilers]
    check(all({k: v for k, v in row.items() if k != 'sheets'} ==
              {k: v for k, v in records[0].items() if k != 'sheets'} for row in records))
    for index, first in enumerate(records[0]['sheets']):
        second, standalone = records[1]['sheets'][index], records[2]['sheets'][index]
        check(set(first) == {'order', 'alias', 'source_path', 'source_sha256', 'path', 'sha256'})
        check({k: v for k, v in first.items() if k != 'path'} ==
              {k: v for k, v in second.items() if k != 'path'} ==
              {k: v for k, v in standalone.items() if k != 'path'})
        check(Path(first['path']).name == Path(second['path']).name == Path(first['source_path']).name)
        check(os.path.samefile(first['path'], second['path']) and not os.path.samefile(first['path'], first['source_path']))
        check(Path(first['path']).read_bytes() == Path(standalone['path']).read_bytes() == Path(first['source_path']).read_bytes())
sizes = dict(zip(('UL','UC','UR','L','C','R','LL','LC','LR'),
                 ((70,50),(1,50),(70,50),(70,1),(1,1),(70,1),(70,50),(1,70),(70,50))))
targets = grid_targets(sizes, (713.5,190,493,700))
check(targets[6] == (713.5,840,783.5,890))
check(targets[7] == (783.5,820,1136.5,890))
check(targets[4] == (783.5,240,1136.5,820))
check(targets[6][3] == targets[7][3] == targets[8][3])
reject(lambda: grid_targets(sizes, (0,0,100,100)))
production = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\Assets\DLC\Expansion2\UI\InGame\Popups\ProductionPopup.xml")
if production.is_file():
    import xml.etree.ElementTree as ET
    layout = ET.parse(production).getroot()
    original_kinds = {node.tag for node in layout.iter()}
    check(original_kinds <= KINDS)
    check({node.attrib['FontStyle'] for node in layout.iter() if 'FontStyle' in node.attrib} <=
          {'Base', 'Shadow', 'Stroke'})
    check(layout.find("Instance[@Name='ProdButton']") is not None)
    unit_button = layout.find(".//Button[@ID='UnitButton']")
    check(unit_button is not None and unit_button.attrib.get('Texture') == 'CivilopediaButtons272x27.dds' and
          unit_button.attrib.get('Size') == '342,27')
    install = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
    button_texture = unit_button.attrib['Texture'].casefold()
    resolved = None
    for pack_name in PACK_POLICY:
        pack = Fpk(install / 'Resource' / 'DX9' / pack_name)
        if button_texture in pack.entries:
            source_data, _ = pack.read(button_texture)
            marker = source_data[32:76].split(b'\0', 1)[0]
            index_data = None
            if marker == b'FTXTInterface' and source_data[116:124].startswith(b'BC00'):
                index_data, _ = pack.read(button_texture[:-4] + '-index.dds')
            _, button_meta = decode_dds(source_data, index_data)
            resolved = (pack_name, button_meta)
            break
    check(resolved is not None and resolved[0] == 'Expansion2UITextures.fpk' and
          (resolved[1]['width'], resolved[1]['height']) == (272, 108))
    src_w, src_h = (int(v) for v in unit_button.attrib['Size'].split(','))
    source_rect = button_source_rect(0, 0, src_w, src_h,
                                     resolved[1]['width'], resolved[1]['height'])
    check(source_rect == (0, 0, 272, 27) and source_rect[2] - source_rect[0] < src_w)
    food = layout.find(".//Label[@ID='Food']")
    check(food is not None and food.attrib.get('Anchor') == 'C,C' and
          food.attrib.get('AnchorSide') == 'O.I' and food.attrib.get('Offset') == '0,-2')
    food_font = load_font(FONTS_ROOT,
                          food.attrib['Font'], food.attrib['FontStyle'])
    food_layout = layout_text(food.attrib['String'], food_font)
    check((food_layout.width, food_layout.height) == (54, 25))
    check(anchor(food.attrib, (0, 0, 70, 24), food_layout.width, food_layout.height) ==
          (8, -2.5, 54, 25))
    growth_label = layout.find(".//Label[@ID='CityGrowthLabel']")
    growth_font = load_font(FONTS_ROOT, growth_label.attrib['Font'], growth_label.attrib['FontStyle'])
    check(growth_font.line_advance == 22 and production_line_advance(growth_font, growth_label.attrib) == 18)
    check(production_line_advance(growth_font, {}) == growth_font.line_advance)
    hover_child = {'key': 303, 'kind': 'AlphaAnim', 'id': 'HoverDecoration', 'hidden': False,
                   'x': 40, 'y': 50, 'width': 20, 'height': 20, 'children': []}
    hover_group = {'key': 302, 'kind': 'ShowOnMouseOver', 'id': 'HoverGroup', 'hidden': False,
                   'hovered': False, 'x': 30, 'y': 40, 'width': 340, 'height': 42,
                   'children': [hover_child]}
    close_button = {'key': 304, 'kind': 'GridButton', 'id': 'CloseButton', 'hidden': False,
                    'x': 1800, 'y': 1000, 'width': 100, 'height': 50, 'children': []}
    hover_fixture = {'tree': {'key': 301, 'kind': 'Context', 'id': 'Root', 'hidden': False,
                              'x': 0, 'y': 0, 'width': 1920, 'height': 1080,
                              'children': [hover_group, close_button]}}
    hover_geometry = [
        {'key': 301, 'kind': 'Context', 'id': 'Root', 'bounds': (0, 0, 1920, 1080), 'style_decoration': False},
        {'key': 302, 'kind': 'ShowOnMouseOver', 'id': 'HoverGroup', 'bounds': (30, 40, 340, 42), 'style_decoration': False},
        {'key': 304, 'kind': 'GridButton', 'id': 'CloseButton', 'bounds': (1800, 1000, 100, 50), 'style_decoration': False},
    ]
    hover_bounds = retained_bounds(hover_fixture, hover_geometry, context='production')
    check([row['key'] for row in hover_bounds['checked']] == [301, 302, 304])
    check(303 not in [row['key'] for row in hover_bounds['checked']])
research = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\Assets\DLC\Expansion2\UI\InGame\TechPopup.xml")
if research.is_file():
    import xml.etree.ElementTree as ET
    tech_layout = ET.parse(research).getroot()
    tech_kinds = {node.tag for node in tech_layout.iter() if node.tag != 'GridData'}
    check(tech_kinds <= KINDS and tech_layout.tag == 'Context')
    check(tech_layout.find(".//Container[@ID='TechButtonContainer']") is not None)
    check(tech_layout.find(".//Stack[@ID='ButtonStack']") is not None)
    check(tech_layout.find(".//ScrollPanel[@ID='ScrollPanel']") is not None)
    check(tech_layout.find(".//GridButton[@ID='OpenTTButton']") is not None)
    check({node.attrib.get('Style') for node in tech_layout.iter() if node.attrib.get('Style')} <=
          {'Grid9DarkBlue8Button', 'Grid9Frame', 'Grid9Science8', 'Grid9Green8',
           'Grid9Production8', 'Grid9Yellow8', 'GridBlackIndent8', 'Grid9Frame27',
           'Grid9DetailFive140', 'ScrollBarUp', 'VertSlider', 'ScrollBarDown'})
    tech_lua = research.with_suffix('.lua').read_text(encoding='utf-8')
    tech_button_include = research.parent / 'TechTree' / 'TechButtonInclude.lua'
    include_text = tech_button_include.read_text(encoding='utf-8')
    check("Mouse.eRClick" in include_text and "Mouse.eLClick" in tech_lua)
    check("TechSelected" in tech_lua and "AddTechButton" in tech_lua)
    enums_path = Path(__file__).resolve().parents[1] / 'Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h'
    enums_text = enums_path.read_text(encoding='utf-8')
    enum_body = enums_text.split('enum ButtonPopupTypes', 1)[1].split('};', 1)[0]
    enum_names = [line.split('//', 1)[0].strip().rstrip(',') for line in enum_body.splitlines()]
    enum_names = [name for name in enum_names if name and name != '{']
    check(enum_names.index('BUTTONPOPUP_CHOOSETECH') == RESEARCH_POPUP_ENUM_VALUE)
tech_tree = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\Assets\DLC\Expansion2\UI\InGame\TechTree\TechTree.xml")
if tech_tree.is_file():
    import xml.etree.ElementTree as ET
    tech_tree_layout = ET.parse(tech_tree).getroot()
    tech_tree_kinds = {node.tag for node in tech_tree_layout.iter() if node.tag != 'GridData'}
    check(tech_tree_kinds <= KINDS and tech_tree_layout.tag == 'Context')
    check(tech_tree_layout.find(".//ScrollPanel[@ID='TechTreeScrollPanel']").attrib['Vertical'] == '0')
    check(tech_tree_layout.find(".//GridButton[@ID='CloseButton']") is not None)
    check({'TechButtonInstance', 'TechPipeInstance', 'EraBlockInstance'} <=
          {node.attrib.get('Name') for node in tech_tree_layout.iter('Instance')})
    tech_tree_styles = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\Assets\UI\Styles.xml")
    styles_root = ET.parse(tech_tree_styles).getroot()
    style_names = {node.tag for node in styles_root}
    check({node.attrib['Style'] for node in tech_tree_layout.iter() if 'Style' in node.attrib} <= style_names)
    tech_tree_lua = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V\Assets\DLC\Expansion2\UI\TechTree\TechTree.lua")
    lua_text = tech_tree_lua.read_text(encoding='utf-8')
    check('include( "TechButtonInclude" );' in lua_text and 'include( "TechHelpInclude" );' in lua_text and
          'TechTreeScrollBar:SetSizeX' in lua_text)
    enum_index = enum_names.index('BUTTONPOPUP_TECH_TREE')
    check(enum_index == RESEARCH_TREE_POPUP_ENUM_VALUE)
with tempfile.TemporaryDirectory() as temp:
        award_compiler = owned_compiler(install, Path(temp) / 'tech_award_side_treatments',
                                  context='tech-award', snapshot_clock=0.5)
        for key, style_name, x in ((901, 'MenuLeftSideTreatment', 680),
                                   (902, 'MenuRightSideTreatment', 1240)):
            award_compiler.node({'key': key, 'kind': 'Box', 'id': '', 'hidden': False,
                                 'attributes': {'Style': style_name}, 'x': x, 'y': 550,
                                 'width': 0, 'height': 0, 'children': [], 'text': ''},
                                (680, 285, 560, 530), {}, (0, 0, 1920, 1080))
        check([(row['key'], row['kind'], row['style_decoration'])
               for row in award_compiler.geometry] ==
              [(901, 'Box', False), (901, 'AlphaAnim', True), (901, 'Image', True),
               (902, 'Box', False), (902, 'AlphaAnim', True), (902, 'Image', True)])
        check({'buttonsides.dds', 'buttonsidesglow.dds'} <= award_compiler.assets.outputs.keys())
        compiler = owned_compiler(install, Path(temp) / 'zero_area_stack_fixture', context='production')
        _, branches_width, branches_height = compiler.texture('TechBranches.dds')
        branches_record = compiler.assets.outputs['techbranches.dds']
        check((branches_width, branches_height) == (105, 105) and
              (branches_record['conversion']['width'], branches_record['conversion']['height']) == (105, 105))
        check(PACK_POLICY[:3] == ('Expansion2UITextures.fpk', 'Expansion1UITextures.fpk',
                                  'UITextures.fpk') and PACK_POLICY[3] == 'Upgrade1Textures.fpk')
        check(branches_record['source']['pack_path'].endswith('Expansion2UITextures.fpk'))
        upgrade_atlases = ('Building_Aqueduct45.dds', 'NationalWonders45_Dec2010Patch.dds',
                           'NationalWonder_GrandTemple45_Expansion.dds', 'TechAtlas_Shared64.dds')
        for atlas_name in upgrade_atlases:
            record = compiler.assets.resolve(atlas_name, Path(temp) / 'upgrade_icons')
            check(record['source']['pack_path'].endswith('Upgrade1Textures.fpk') and
                  record['source']['entry'].casefold() == atlas_name.casefold() and
                  len(record['source']['sha256']) == 64 and len(record['output']['sha256']) == 64)
        nested = {'key': 102, 'kind': 'Stack', 'id': 'CapturedChildStack', 'attributes': {},
                  'children': [], 'width': 0, 'height': 0, 'hidden': False,
                  'x': 25, 'y': 41, 'text': ''}
        box = {'key': 103, 'kind': 'Box', 'id': 'CapturedZeroAreaWrapper',
               'attributes': {'Color': '255,255,255,0'}, 'children': [nested],
               'width': 0, 'height': 0, 'hidden': False, 'x': 23, 'y': 37, 'text': ''}
        container = {'key': 101, 'kind': 'Stack', 'id': 'CapturedParentStack',
                     'attributes': {'StackGrowth': 'B'}, 'children': [box],
                     'width': 0, 'height': 0, 'hidden': False, 'x': 20, 'y': 34, 'text': ''}
        compiler.node(container, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
        check([row['key'] for row in compiler.geometry] == [101, 103, 102])
        check([row['bounds'] for row in compiler.geometry] ==
              [(20, 34, 0, 0), (23, 37, 0, 0), (25, 41, 0, 0)])
        font = load_font(FONTS_ROOT, 'TwCenMT22', 'Base')
        advance = font.glyphs[ord('A')].abc_advance
        check(wrap_production_text('AA BB', font, {}, advance * 3) ==
              [('AA', advance * 2), ('BB', font.glyphs[ord('B')].abc_advance * 2)])
        check(wrap_production_text('AAAA', font, {}, advance * 2) ==
              [('AA', advance * 2), ('AA', advance * 2)])
        unwrapped = 'A  BB'
        unwrapped_width = sum(font.glyphs[ord(char)].abc_advance for char in unwrapped)
        check(wrap_production_text(unwrapped + '\n', font, {}, 0) ==
               [(unwrapped, unwrapped_width), ('', 0)])
        tab_glyphs = {9: inline_tab_glyph(font)}
        tab_width = 8 * font.glyphs[32].abc_advance + advance
        check(wrap_production_text('\t\tA', font, tab_glyphs, 500) == [('\t\tA', tab_width)])
        tab_layout = layout_text('\t\tA', font, inline_glyphs=tab_glyphs)
        check(tab_layout.width == tab_width and tab_layout.placements[2].pen_x == 8 * font.glyphs[32].abc_advance)
        check(all(row.texture_rect[2:] == (0, 0) for row in tab_layout.placements[:2]))
        compiler.production_input_targets = [
            {'key': 401, 'id': 'CloseButton', 'event': 'LeftClick', 'visible': True, 'disabled': False,
             'bounds': {'x': 1800, 'y': 1000, 'width': 100, 'height': 50},
             'clippedBounds': {'x': 1800, 'y': 1000, 'width': 100, 'height': 50}},
            {'key': 403, 'id': 'ProductionRow', 'event': 'LeftClick', 'visible': True, 'disabled': False,
             'bounds': {'x': 20, 'y': 205, 'width': 340, 'height': 42},
             'clippedBounds': {'x': 35, 'y': 205, 'width': 325, 'height': 42}},
            {'key': 403, 'id': 'ProductionRow', 'event': 'RightClick', 'visible': True, 'disabled': False,
             'bounds': {'x': 20, 'y': 205, 'width': 340, 'height': 42},
             'clippedBounds': {'x': 35, 'y': 205, 'width': 325, 'height': 42}, 'void1': 6, 'void2': 1},
            {'key': 404, 'id': 'CategoryButton', 'event': 'LeftClick', 'visible': True, 'disabled': False,
             'bounds': {'x': 40, 'y': 150, 'width': 100, 'height': 25},
             'clippedBounds': {'x': 40, 'y': 150, 'width': 100, 'height': 25}},
            {'key': 405, 'id': 'ScrollUp', 'event': 'LeftClick', 'visible': True, 'disabled': False,
             'bounds': {'x': 355, 'y': 214, 'width': 18, 'height': 18},
             'clippedBounds': {'x': 355, 'y': 214, 'width': 18, 'height': 18}},
            {'key': 406, 'id': 'ScrollDown', 'event': 'LeftClick', 'visible': True, 'disabled': False,
             'bounds': {'x': 360, 'y': 870, 'width': 18, 'height': 18},
             'clippedBounds': {'x': 360, 'y': 870, 'width': 15, 'height': 10}},
        ]
        compiler.hits = []
        compiler.geometry = [
            {'key': 401, 'kind': 'GridButton', 'id': 'CloseButton', 'bounds': (1800, 1000, 100, 50),
             'input_target': False},
            {'key': 402, 'kind': 'ScrollPanel', 'id': 'ProductionPanel', 'bounds': (35, 196, 340, 684),
             'input_target': False},
            {'key': 403, 'kind': 'Button', 'id': 'ProductionRow', 'bounds': (20, 205, 340, 42),
             'input_target': False},
            {'key': 404, 'kind': 'Button', 'id': 'CategoryButton', 'bounds': (40, 150, 100, 25),
             'input_target': False},
            {'key': 405, 'kind': 'UpButton', 'id': 'ScrollUp', 'bounds': (355, 214, 18, 18),
             'input_target': False},
            {'key': 406, 'kind': 'DownButton', 'id': 'ScrollDown', 'bounds': (360, 870, 18, 18),
             'input_target': False},
        ]
        clip_tree = {'key': 300, 'kind': 'Context', 'hidden': False, 'x': 0, 'y': 0, 'width': 1920,
                     'height': 1080, 'children': [
            {'key': 401, 'kind': 'GridButton', 'id': 'CloseButton', 'hidden': False, 'buttonState': 'normal',
             'x': 1800, 'y': 1000, 'width': 100, 'height': 50, 'children': []},
            {'key': 402, 'kind': 'ScrollPanel', 'id': 'ProductionPanel', 'hidden': False,
             'x': 35, 'y': 196, 'width': 340, 'height': 684, 'children': [
                {'key': 403, 'kind': 'Button', 'id': 'ProductionRow', 'hidden': False, 'buttonState': 'normal',
                 'x': 20, 'y': 205, 'width': 340, 'height': 42, 'children': []},
                {'key': 405, 'kind': 'UpButton', 'id': 'ScrollUp', 'hidden': False, 'buttonState': 'normal',
                 'x': 355, 'y': 214, 'width': 18, 'height': 18, 'children': []},
                {'key': 406, 'kind': 'DownButton', 'id': 'ScrollDown', 'hidden': False, 'buttonState': 'normal',
                 'x': 360, 'y': 870, 'width': 18, 'height': 18, 'children': []}]},
            {'key': 404, 'kind': 'Button', 'id': 'CategoryButton', 'hidden': False, 'buttonState': 'normal',
             'x': 40, 'y': 150, 'width': 100, 'height': 25, 'children': []}]}
        compiler.production_hits(clip_tree)
        check(compiler.hits == [(401, 1800, 1000, 1900, 1050), (403, 35, 205, 360, 247),
                                (404, 40, 150, 140, 175), (405, 355, 214, 373, 232),
                                (406, 360, 870, 375, 880)])
        check(compiler.geometry[2]['input_targets'] == ['LeftClick', 'RightClick'] and
              len([hit for hit in compiler.hits if hit[0] == 403]) == 1)
        scroll_tree = {'key': 500, 'kind': 'Context', 'hidden': False, 'x': 0, 'y': 0,
                       'width': 1920, 'height': 1080, 'children': [
            {'key': 501, 'kind': 'ScrollPanel', 'id': 'ProductionPanel', 'hidden': False,
             'attributes': {'Vertical': '1'}, 'x': 35, 'y': 196, 'width': 340, 'height': 684,
             'scrollY': 40, 'contentHeight': 1000, 'children': [
                {'key': 502, 'kind': 'ScrollPanel', 'id': 'NestedPanel', 'hidden': False,
                 'attributes': {'Vertical': '1'}, 'x': 360, 'y': 850, 'width': 40, 'height': 50,
                 'scrollY': 5, 'contentHeight': 70, 'children': []}]},
            {'key': 503, 'kind': 'ScrollPanel', 'id': 'ClippedAway', 'hidden': False,
             'attributes': {'Vertical': '1'}, 'x': 2000, 'y': 20, 'width': 100, 'height': 100,
             'scrollY': 0, 'contentHeight': 150, 'children': []}]}
        compiler.production_scroll_targets = [
            {'key': 501, 'id': 'ProductionPanel', 'event': 'Scroll', 'visible': True, 'disabled': False,
             'bounds': {'x': 35, 'y': 196, 'width': 340, 'height': 684},
             'clippedBounds': {'x': 35, 'y': 196, 'width': 340, 'height': 684},
             'scrollY': 40, 'contentHeight': 1000, 'viewportHeight': 684, 'maximumScroll': 316},
            {'key': 502, 'id': 'NestedPanel', 'event': 'Scroll', 'visible': True, 'disabled': False,
             'bounds': {'x': 360, 'y': 850, 'width': 40, 'height': 50},
             'clippedBounds': {'x': 360, 'y': 850, 'width': 15, 'height': 30},
             'scrollY': 5, 'contentHeight': 70, 'viewportHeight': 50, 'maximumScroll': 20}]
        compiler.scroll_regions = []
        compiler.production_scrolls(scroll_tree)
        check(compiler.scroll_regions == [(501, 35, 196, 375, 880),
                                          (502, 360, 850, 375, 880)])
        bad_scroll_targets = list(compiler.production_scroll_targets)
        compiler.production_scroll_targets = bad_scroll_targets[:1]
        reject(lambda: compiler.production_scrolls(scroll_tree))
        compiler.production_scroll_targets = [dict(row) for row in bad_scroll_targets]
        compiler.production_scroll_targets[1]['maximumScroll'] = 21
        reject(lambda: compiler.production_scrolls(scroll_tree))
        compiler.production_scroll_targets = bad_scroll_targets
        production_closed = owned_compiler(install, Path(temp) / 'production_closed_packet_fixture', context='production')
        production_packet = production_closed.compile({
            'active': False, 'timerSemaphore': 0, 'contextName': 'ProductionPopup', 'popupKind': 'Production',
            'lifecycle': ['queued', 'shown:16', 'processed:16', 'context-hidden:ProductionPopup'],
            'inputTargets': [], 'scrollTargets': [],
            'tree': {'kind': 'Context', 'width': 1920, 'height': 1080}}, closed=True)
        check(production_packet[:8] == b'ZSUPIX02' and len(production_packet) == 32 and
              int.from_bytes(production_packet[28:32], 'little') == 0)
        ranking_closed = owned_compiler(install, Path(temp) / 'ranking_closed_packet_fixture', context='ranking')
        ranking_packet = ranking_closed.compile({
            'active': False, 'timerSemaphore': 0,
            'lifecycle': ['queued', 'shown:54', 'processed:54', 'closed'],
            'tree': {'kind': 'Context', 'width': 1920, 'height': 1080}}, closed=True)
        check(ranking_packet[:8] == b'ZSUPIX01' and len(ranking_packet) == 28)
        research_compiler = owned_compiler(install, Path(temp) / 'research_packet_fixture', context='research')
        research_sources = {path.relative_to(install).as_posix()
                            for path in research_compiler.context_sources}
        check({'Assets/DLC/Expansion2/UI/InGame/TechPopup.xml',
               'Assets/DLC/Expansion2/UI/InGame/TechPopup.lua',
               'Assets/DLC/Expansion2/UI/InGame/TechTree/TechButtonInclude.lua',
               'Assets/DLC/Expansion2/UI/InGame/TechTree/TechHelpInclude.lua',
               'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
               'Assets/UI/IconSupport.lua', 'Assets/Gameplay/Lua/FLuaVector.lua',
               'Assets/UI/InstanceManager.lua'} <= research_sources)
        open_tree_button = tech_layout.find(".//GridButton[@ID='OpenTTButton']")
        inline_grid_data = open_tree_button.find('GridData')
        inline_grid_attrs = dict(research_compiler.styles['Grid9DarkBlue8Button'].attrib)
        inline_grid_attrs['Style'] = inline_grid_data.attrib['Style']
        check(open_tree_button is not None and inline_grid_data is not None and
              'Style' not in open_tree_button.attrib and
              inline_grid_data.attrib.get('Style') == 'Grid9DarkBlue8Button' and
              all(f'{part}{field}' in inline_grid_attrs
                  for part in ('UL', 'UC', 'UR', 'L', 'C', 'R', 'LL', 'LC', 'LR')
                  for field in ('Size', 'TexStart')))
        descriptor_grid_calls = []
        research_compiler.grid = lambda key, style, bounds, clip: descriptor_grid_calls.append(
            (key, style.tag, dict(style.attrib), bounds, clip))
        open_button_node = {
            'key': 700, 'kind': 'GridButton', 'id': 'OpenTTButton', 'hidden': False,
            'buttonState': 'normal', 'attributes': {'Anchor': 'C,C', 'Size': '310,36'},
            'x': 805, 'y': 260, 'width': 310, 'height': 36,
            'children': [{'key': 701, 'kind': 'GridData', 'id': '', 'hidden': False,
                          'attributes': inline_grid_attrs, 'width': 0, 'height': 0,
                          'children': []}], 'text': ''}
        research_compiler.node(open_button_node, (0, 0, 1920, 1080), {}, (0, 0, 1920, 1080))
        check(len(descriptor_grid_calls) == 1 and descriptor_grid_calls[0][0] == 700 and
              descriptor_grid_calls[0][1] == 'GridData' and
              descriptor_grid_calls[0][2] == inline_grid_attrs and
              descriptor_grid_calls[0][3] == (805, 260, 310, 36) and
              [row['key'] for row in research_compiler.geometry] == [700])
        griddata_bounds = retained_bounds(
            {'tree': {'key': 702, 'kind': 'Context', 'hidden': False, 'width': 1920, 'height': 1080,
                      'x': 0, 'y': 0, 'children': [
                          {'key': 700, 'kind': 'GridButton', 'id': 'OpenTTButton', 'hidden': False,
                           'width': 310, 'height': 36, 'x': 805, 'y': 260,
                           'children': [{'key': 701, 'kind': 'GridData', 'hidden': False,
                                         'width': 0, 'height': 0, 'children': []}]}]}},
            [{'key': 702, 'kind': 'Context', 'id': 'TechPopup', 'bounds': (0, 0, 1920, 1080),
              'style_decoration': False},
             {'key': 700, 'kind': 'GridButton', 'id': 'OpenTTButton', 'bounds': (805, 260, 310, 36),
              'style_decoration': False}], context='research')
        check(any(row['key'] == 700 for row in griddata_bounds['checked']) and
              all(row['key'] != 701 for row in griddata_bounds['checked']))
        research_compiler.geometry.clear()
        research_compiler.keys.clear()
        research_button = {'key': 601, 'kind': 'Button', 'id': 'TechButton', 'hidden': False,
                           'buttonState': 'normal', 'attributes': {}, 'x': 100, 'y': 200,
                           'width': 270, 'height': 60, 'children': [], 'text': ''}
        research_panel = {'key': 602, 'kind': 'ScrollPanel', 'id': 'ScrollPanel', 'hidden': False,
                          'attributes': {'Vertical': '1'}, 'x': 80, 'y': 180, 'width': 300,
                          'height': 400, 'scrollX': 0, 'scrollY': 10, 'contentHeight': 600,
                          'children': [], 'text': ''}
        research_root = {'key': 600, 'kind': 'Context', 'id': 'TechPopup', 'hidden': False,
                         'attributes': {}, 'x': 0, 'y': 0, 'width': 1920, 'height': 1080,
                         'children': [research_button, research_panel], 'text': ''}
        research_targets = [
            {'key': 601, 'id': 'TechButton', 'event': event, 'visible': True, 'disabled': False,
             'bounds': {'x': 100, 'y': 200, 'width': 270, 'height': 60},
             'clippedBounds': {'x': 100, 'y': 200, 'width': 270, 'height': 60}, 'void1': 17, 'void2': 0}
            for event in ('LeftClick', 'RightClick')]
        research_snapshot = {
            'active': True, 'timerSemaphore': 0, 'contextName': 'TechPopup', 'popupKind': 'Research',
            'presentationClock': 0, 'animationPolicy': 'ZEROSIS_FRONTEND_XML_TIMELINE_V1',
            'retailTimingVerified': False,
            'fontMetrics': {'policy': 'CIV5_GLYPHGEN_GGXML_LAYOUT_V1',
                            'retailMetricSemanticsVerified': False,
                            'wrapPolicy': 'GREEDY_ASCII_SPACE_WORD_WRAP_SPLIT_LONG_WORD_AT_CODEPOINT',
                            'fonts': {}},
            'inputTargets': research_targets,
            'scrollTargets': [{'key': 602, 'id': 'ScrollPanel', 'event': 'Scroll', 'visible': True,
                               'disabled': False, 'bounds': {'x': 80, 'y': 180, 'width': 300, 'height': 400},
                               'clippedBounds': {'x': 80, 'y': 180, 'width': 300, 'height': 400},
                               'scrollY': 10, 'contentHeight': 600, 'viewportHeight': 400,
                               'maximumScroll': 200}],
            'tree': research_root}
        research_packet = research_compiler.compile(research_snapshot)
        check(research_packet[:8] == b'ZSUPIX02' and len(research_packet) == 32 + 24 + 24)
        check(research_compiler.hits == [(601, 100, 200, 370, 260)])
        check(research_compiler.scroll_regions == [(602, 80, 180, 380, 580)])
        check(research_compiler.geometry[1]['input_targets'] == ['LeftClick', 'RightClick'])
        reject(lambda: owned_compiler(install, Path(temp) / 'research_closed_bad', context='research').compile({
            'active': False, 'timerSemaphore': 0, 'contextName': 'TechPopup', 'popupKind': 'Research',
            'lifecycle': ['queued', 'shown:11', 'processed:11', 'context-hidden:TechPopup'],
            'inputTargets': [], 'scrollTargets': [],
            'tree': {'kind': 'Context', 'width': 1920, 'height': 1080}}, closed=True))
        research_closed_compiler = owned_compiler(install, Path(temp) / 'research_closed_packet_fixture', context='research')
        research_closed_packet = research_closed_compiler.compile({
            'active': False, 'timerSemaphore': 0, 'contextName': 'TechPopup', 'popupKind': 'Research',
            'lifecycle': ['queued', 'shown:11', 'context-hidden:TechPopup', 'processed:11'],
            'inputTargets': [], 'scrollTargets': [],
            'tree': {'kind': 'Context', 'width': 1920, 'height': 1080}}, closed=True)
        check(research_closed_packet[:8] == b'ZSUPIX02' and len(research_closed_packet) == 32 and
              int.from_bytes(research_closed_packet[28:32], 'little') == 0)
        for invalid_lifecycle in (
                ['queued', 'shown:10', 'context-hidden:TechPopup', 'processed:10'],
                ['queued', 'shown:11', 'context-hidden:TechPopup', 'processed:12'],
                ['queued', 'shown:11', 'processed:11', 'context-hidden:TechPopup'],
                ['queued', 'shown:11', 'context-hidden:TechPopup', 'processed:CHOOSETECH']):
            reject(lambda lifecycle=invalid_lifecycle: owned_compiler(
                install, Path(temp) / ('research_closed_bad_' + str(len(research_compiler.keys))),
                context='research').compile({
                    'active': False, 'timerSemaphore': 0, 'contextName': 'TechPopup', 'popupKind': 'Research',
                    'lifecycle': lifecycle, 'inputTargets': [], 'scrollTargets': [],
                    'tree': {'kind': 'Context', 'width': 1920, 'height': 1080}}, closed=True))
        tree_compiler = owned_compiler(install, Path(temp) / 'research_tree_packet_fixture', context='research-tree')
        tree_sources = {path.relative_to(install).as_posix() for path in tree_compiler.context_sources}
        check({'Assets/DLC/Expansion2/UI/InGame/TechTree/TechTree.xml',
               'Assets/DLC/Expansion2/UI/TechTree/TechTree.lua',
               'Assets/DLC/Expansion2/UI/InGame/TechTree/TechButtonInclude.lua',
               'Assets/DLC/Expansion2/UI/InGame/TechTree/TechHelpInclude.lua',
               'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
               'Assets/UI/IconSupport.lua', 'Assets/UI/InstanceManager.lua'} <= tree_sources)
        tree_compiler.production_scroll_targets = [{
            'key': 850, 'id': 'TechTreeScrollPanel', 'event': 'Scroll', 'visible': True, 'disabled': False,
            'orientation': 'horizontal',
            'bounds': {'x': 0, 'y': 180, 'width': 1650, 'height': 705},
            'clippedBounds': {'x': 0, 'y': 180, 'width': 1650, 'height': 705},
            'scrollX': 120, 'contentWidth': 4200, 'viewportWidth': 1650, 'maximumScroll': 2550}]
        tree_compiler.production_scrolls({
            'key': 849, 'kind': 'Context', 'hidden': False, 'x': 0, 'y': 0, 'width': 1920, 'height': 1080,
            'children': [{'key': 850, 'kind': 'ScrollPanel', 'id': 'TechTreeScrollPanel', 'hidden': False,
                          'attributes': {'Vertical': '0'}, 'x': 0, 'y': 180, 'width': 1650, 'height': 705,
                          'scrollX': 120, 'scrollY': 0, 'contentWidth': 4200, 'children': []}]})
        check(tree_compiler.scroll_regions == [(850, 0, 180, 1650, 885)])
        reject(lambda: tree_compiler.production_scrolls({
            'key': 849, 'kind': 'Context', 'hidden': False, 'x': 0, 'y': 0, 'width': 1920, 'height': 1080,
            'children': [{'key': 850, 'kind': 'ScrollPanel', 'id': 'TechTreeScrollPanel', 'hidden': False,
                          'attributes': {'Vertical': '1'}, 'x': 0, 'y': 180, 'width': 1650, 'height': 705,
                          'scrollX': 120, 'scrollY': 0, 'contentWidth': 4200, 'children': []}]}))
        tree_compiler.scroll_regions.clear()
        strip_calls = []
        tree_compiler.texture = lambda name: (7, 128, 18)
        tree_compiler.paint = lambda key, texture, source, target, clip, color=(1, 1, 1, 1): \
            strip_calls.append((key, source, target, clip))
        tree_compiler.horizontal_strip(860, tree_compiler.styles['Grid3Shuttle'],
                                      (100, 40, 400, 58), (0, 0, 1920, 1080))
        check([(row[1], row[2]) for row in strip_calls] == [
            ((0, 0, 3, 18), (100, 40, 103, 58)),
            ((3, 0, 15, 18), (103, 40, 397, 58)),
            ((15, 0, 18, 18), (397, 40, 400, 58))])
        tree_compiler.texture = Compiler.texture.__get__(tree_compiler, Compiler)
        tree_compiler.paint = Compiler.paint.__get__(tree_compiler, Compiler)
        tree_button = {'key': 801, 'kind': 'Button', 'id': 'CloseButton', 'hidden': False,
                       'buttonState': 'normal', 'attributes': {}, 'x': 900, 'y': 1000,
                       'width': 100, 'height': 32, 'children': [], 'text': ''}
        future_tech_button = {'key': 803, 'kind': 'Button', 'id': 'TechButton', 'hidden': False,
                              'buttonState': 'normal', 'attributes': {}, 'x': 100, 'y': 200,
                              'width': 270, 'height': 60, 'children': [], 'text': ''}
        tree_panel = {'key': 802, 'kind': 'ScrollPanel', 'id': 'TechTreeScrollPanel', 'hidden': False,
                      'attributes': {'Vertical': '0'}, 'x': 0, 'y': 180, 'width': 1650, 'height': 705,
                      'scrollX': 120, 'scrollY': 0, 'contentWidth': 4200, 'children': [], 'text': ''}
        tree_snapshot = {
            'active': True, 'timerSemaphore': 1, 'contextName': 'TechTree', 'popupKind': 'ResearchTree',
            'presentationClock': 0, 'lifecycle': ['queued', 'shown:67'],
            'animationPolicy': 'ZEROSIS_FRONTEND_XML_TIMELINE_V1', 'retailTimingVerified': False,
            'fontMetrics': {'policy': 'CIV5_GLYPHGEN_GGXML_LAYOUT_V1',
                            'retailMetricSemanticsVerified': False,
                            'wrapPolicy': 'GREEDY_ASCII_SPACE_WORD_WRAP_SPLIT_LONG_WORD_AT_CODEPOINT',
                            'fonts': {}},
            'inputTargets': [{'key': 801, 'id': 'CloseButton', 'event': 'LeftClick', 'visible': True,
                              'disabled': False, 'bounds': {'x': 900, 'y': 1000, 'width': 100, 'height': 32},
                              'clippedBounds': {'x': 900, 'y': 1000, 'width': 100, 'height': 32}},
                             {'key': 803, 'id': 'TechButton', 'event': 'LeftClick', 'visible': True,
                              'disabled': False, 'void1': -1, 'void2': 0,
                              'bounds': {'x': 100, 'y': 200, 'width': 270, 'height': 60},
                              'clippedBounds': {'x': 100, 'y': 200, 'width': 270, 'height': 60}},
                             {'key': 803, 'id': 'TechButton', 'event': 'RightClick', 'visible': True,
                              'disabled': False, 'void1': -1, 'void2': 0,
                              'bounds': {'x': 100, 'y': 200, 'width': 270, 'height': 60},
                              'clippedBounds': {'x': 100, 'y': 200, 'width': 270, 'height': 60}}],
            'scrollTargets': [{'key': 802, 'id': 'TechTreeScrollPanel', 'event': 'Scroll',
                               'visible': True, 'disabled': False, 'orientation': 'horizontal',
                               'bounds': {'x': 0, 'y': 180, 'width': 1650, 'height': 705},
                               'clippedBounds': {'x': 0, 'y': 180, 'width': 1650, 'height': 705},
                               'scrollX': 120, 'contentWidth': 4200, 'viewportWidth': 1650,
                               'maximumScroll': 2550}],
            'tree': {'key': 800, 'kind': 'Context', 'id': 'TechTree', 'hidden': False,
                     'attributes': {}, 'x': 0, 'y': 0, 'width': 1920, 'height': 1080,
                     'children': [tree_button, future_tech_button, tree_panel]}}
        tree_packet = tree_compiler.compile(tree_snapshot)
        check(tree_packet[:8] == b'ZSUPIX02' and len(tree_packet) == 32 + 48 + 24 and
              int.from_bytes(tree_packet[24:28], 'little') == 2 and
              int.from_bytes(tree_packet[28:32], 'little') == 1)
        check(next(row for row in tree_compiler.geometry if row['key'] == 803)['input_targets'] ==
              ['LeftClick', 'RightClick'])
        tree_closed = {'active': False, 'timerSemaphore': 0, 'contextName': 'TechTree',
                       'popupKind': 'ResearchTree',
                       'lifecycle': ['queued', 'shown:67', 'closed', 'processed:67'],
                       'inputTargets': [], 'scrollTargets': [],
                       'tree': {'kind': 'Context', 'width': 1920, 'height': 1080}}
        tree_closed_packet = owned_compiler(install, Path(temp) / 'research_tree_closed_fixture',
                                      context='research-tree').compile(tree_closed, closed=True)
        check(tree_closed_packet[:8] == b'ZSUPIX02' and len(tree_closed_packet) == 32 and
              int.from_bytes(tree_closed_packet[28:32], 'little') == 0)
        for invalid_lifecycle in (
                ['queued', 'shown:66', 'closed', 'processed:66'],
                ['queued', 'shown:67', 'closed', 'processed:68'],
                ['queued', 'shown:67', 'processed:67', 'closed'],
                ['queued', 'shown:67', 'context-hidden:TechTree', 'processed:67']):
            reject(lambda lifecycle=invalid_lifecycle: owned_compiler(
                install, Path(temp) / ('research_tree_closed_bad_' + str(len(lifecycle))),
                context='research-tree').compile({**tree_closed, 'lifecycle': lifecycle}, closed=True))
print(json.dumps({'status': 'SELECTED_POPUP_GEOMETRY_COMPONENT_PASS', 'checks': checks,
                  'retail_layout_equivalence_proven': False}))
