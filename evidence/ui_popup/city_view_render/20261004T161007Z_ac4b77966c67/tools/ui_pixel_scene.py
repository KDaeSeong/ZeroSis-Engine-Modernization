"""Compile an owned retained UI tree into bounded original-atlas paint commands.

This is a selected popup presentation candidate. It does not run Lua/GameCore,
generate another popup, change game state, or assert retail pixel equivalence.
"""
from __future__ import annotations

import copy
import hashlib
import math
from pathlib import Path
import re
import shutil
import struct
import xml.etree.ElementTree as ET

from civ5_ui_assets import UiAssets, require, sha256, candidate_directory, header, rgba32, normalized_header
from ui_bitmap_fonts import Glyph, load_font, layout_text

SOLID = 0xffffffff
KINDS = {'Context', 'Instance', 'AlphaAnim', 'Box', 'Button', 'Container', 'DownButton',
         'Grid', 'GridButton', 'Image', 'Label', 'Meter', 'ScrollAnim', 'ScrollBar',
         'ScrollPanel', 'ShowOnMouseOver', 'Stack', 'TextureBar', 'UpButton', 'TextButton', 'LuaContext',
         'CheckBox', 'RadioButton', 'WorldAnchor', 'FlipAnim'}
# BUTTONPOPUP_CHOOSETECH is ordinal 11 in Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h.
RESEARCH_POPUP_ENUM_VALUE = 11
# BUTTONPOPUP_TECH_TREE is ordinal 67 in the same SDK enum.
RESEARCH_TREE_POPUP_ENUM_VALUE = 67
# DIPLO_UI_STATE_DEFAULT_ROOT is ordinal 0 in DiploUIStateTypes in the frozen BNW CvEnums.h.
DIPLO_UI_STATE_DEFAULT_ROOT_ENUM_VALUE = 0
# LEADERHEAD_ANIM_INTRO is explicitly 1 in LeaderheadAnimationTypes in that same header.
LEADERHEAD_ANIM_INTRO_ENUM_VALUE = 1
SCENE_CONTEXTS = ('production', 'research', 'research-tree', 'city-capture', 'diplomacy', 'city-view')
RESEARCH_CONTEXTS = ('research', 'research-tree')


def pair(raw, default='0,0'):
    values = (raw if raw is not None else default).replace('.', ',').split(',')
    require(len(values) == 2 and all(re.fullmatch(r'-?\d+', value) for value in values), 'Unsupported coordinate pair')
    return tuple(int(value) for value in values)


def intersect(a, b):
    return (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))


def positive(rect):
    return rect[2] > rect[0] and rect[3] > rect[1]


def anchor(attrs, parent, width, height, offset_y=0):
    ax, ay = (part.upper() for part in attrs.get('Anchor', 'L,T').split(','))
    sx, sy = (part.upper() for part in attrs.get('AnchorSide', 'I,I').replace('.', ',').split(','))
    require(ax in ('L', 'C', 'R') and ay in ('T', 'C', 'B') and sx in ('I', 'O') and sy in ('I', 'O'),
            'Unsupported anchor')
    dx, dy = pair(attrs.get('Offset'))
    px, py, pw, ph = parent
    x = dx if ax == 'L' else (pw - width) / 2 + dx if ax == 'C' else pw - width - dx
    y = dy if ay == 'T' else (ph - height) / 2 + dy if ay == 'C' else ph - height - dy
    # The source UI runtime treats an outside side on a centered axis as
    # inapplicable: centering still determines that axis' position.
    if sx == 'O' and ax != 'C':
        x = pw + dx if ax == 'R' else -width - dx
    if sy == 'O' and ay != 'C':
        y = ph + dy if ay == 'B' else -height - dy
    return px + x, py + y + offset_y, width, height


def rect(bounds):
    x, y, w, h = bounds
    return x, y, x + w, y + h


def image_regions(u, v, bounds, texture_size, *, stretch_full_texture=False,
                  source_extent=None):
    """Resolve a source region and target for a retained Image control."""
    texture_width, texture_height = texture_size
    x, y, width, height = bounds
    extent_width, extent_height = source_extent or (width, height)
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (u, v, x, y, width, height, texture_width, texture_height,
                              extent_width, extent_height)) and
            u >= 0 and v >= 0 and width > 0 and height > 0 and
            texture_width > 0 and texture_height > 0 and
            extent_width > 0 and extent_height > 0,
            'Invalid retained Image source or target geometry')
    if stretch_full_texture:
        require(u == 0 and v == 0,
                'Full-texture Image stretch requires the captured zero texture offset')
        return (0, 0, texture_width, texture_height), rect(bounds), \
               'ZEROSIS_CANDIDATE_STRETCH_FULL_TECHPIPE_TEXTURE_TO_RETAINED_BOUNDS'
    require(u + extent_width <= texture_width and v + extent_height <= texture_height,
            'Image region outside restored original atlas')
    policy = ('ZEROSIS_CANDIDATE_STRETCH_TECHBRANCH_32PX_ATLAS_CELL_TO_RETAINED_BOUNDS'
              if source_extent is not None and (extent_width, extent_height) != (width, height)
              else 'SOURCE_REGION_MATCHES_RETAINED_BOUNDS')
    return (u, v, u + extent_width, v + extent_height), rect(bounds), policy


def bounds_size(bounds):
    """Return width/height from retained x/y/width/height geometry."""
    require(type(bounds) in (tuple, list) and len(bounds) == 4 and
            all(type(value) in (int, float) and math.isfinite(value) for value in bounds) and
            bounds[2] >= 0 and bounds[3] >= 0,
            'Invalid retained x/y/width/height bounds')
    return bounds[2], bounds[3]


def scroll_extent(bounds, content_height):
    _, height = bounds_size(bounds)
    require(type(content_height) in (int, float) and math.isfinite(content_height) and content_height >= 0,
            'Invalid captured scroll content height')
    return max(0.0, content_height - height)


def production_line_advance(font, attrs):
    """Apply the retained control's XML LeadingOffset to the original GGXML line box."""
    raw = attrs.get('LeadingOffset', 0)
    try:
        leading = float(raw)
    except (TypeError, ValueError) as error:
        raise ValueError('Invalid production label LeadingOffset') from error
    require(math.isfinite(leading), 'Invalid production label LeadingOffset')
    result = font.line_advance + leading
    require(math.isfinite(result) and result > 0, 'Production label line advance is not positive')
    return result


def font_layer_colors(layer_colors, layer_count, *, font_style, color_set):
    """Resolve the original UI layer palette without silently dropping effects.

    Original UI layouts use both Beige_Black and Beige_Black_Alpha (each with
    Color0/Color1 only) with the three-layer SoftShadow GGXML style. The style
    defines the glyph, shadow, and soft-shadow texture layers; the candidate
    maps Color0 to the glyph and the declared effect Color1 to both effect
    layers. Retail renderer color fallback is not verified.
    """
    require(type(layer_colors) in (tuple, list) and layer_count > 0 and
            all(type(color) in (tuple, list) and len(color) == 4 and
                all(type(channel) in (int, float) and math.isfinite(channel) and 0 <= channel <= 1
                    for channel in color) for color in layer_colors),
            'Invalid font layer color palette')
    if len(layer_colors) >= layer_count:
        policy = ('SOURCE_COLORSET_EXACT_LAYER_COUNT' if len(layer_colors) == layer_count else
                  'SOURCE_COLORSET_UNUSED_TRAILING_COLORS')
        return tuple(tuple(color) for color in layer_colors[:layer_count]), policy
    if (color_set in ('Beige_Black', 'Beige_Black_Alpha') and font_style == 'SoftShadow' and
            layer_count == 3 and len(layer_colors) == 2):
        return (tuple(layer_colors[0]), tuple(layer_colors[1]), tuple(layer_colors[1])), \
               'ZEROSIS_CANDIDATE_REPEAT_LAST_EFFECT_COLOR_FOR_SOFTSHADOW'
    raise ValueError('Font ColorSet layer count differs from its original GGXML style')


def centered_button_text_bounds(button_bounds, text_width, text_height, text_offset):
    """Place original direct GridButton text at the control center plus TextOffset."""
    require(type(button_bounds) in (tuple, list) and len(button_bounds) == 4 and
            all(type(value) in (int, float) and math.isfinite(value) for value in button_bounds),
            'Invalid original button bounds for direct text')
    x, y, width, height = button_bounds
    require(width > 0 and height > 0 and
            all(type(value) in (int, float) and math.isfinite(value) for value in
                (text_width, text_height, *text_offset)) and
            0 < text_width <= width and 0 < text_height <= height,
            'Original GridButton text does not fit its retained control bounds')
    offset_x, offset_y = text_offset
    return (x + (width - text_width) / 2 + offset_x,
            y + (height - text_height) / 2 + offset_y,
            text_width, text_height)


def texture_bar_regions(bounds, direction, percent, texture_width, texture_height):
    """Return source xyxy and target xyxy for one captured TextureBar fraction."""
    x, y, width, height = bounds
    require(direction in ('Up', 'Down', 'Left', 'Right') and
            all(type(value) in (int, float) and math.isfinite(value)
                for value in (x, y, width, height, percent, texture_width, texture_height)) and
            width > 0 and height > 0 and 0 <= percent <= 1 and
            texture_width > 0 and texture_height > 0,
            'Invalid captured TextureBar geometry')
    if direction in ('Up', 'Down'):
        filled = height * percent
        target = (x, y + height - filled if direction == 'Up' else y, x + width,
                  y + height if direction == 'Up' else y + filled)
        source = (0, texture_height * (1 - percent) if direction == 'Up' else 0,
                  texture_width, texture_height if direction == 'Up' else texture_height * percent)
    else:
        filled = width * percent
        target = (x + width - filled if direction == 'Right' else x, y,
                  x + width if direction == 'Right' else x + filled, y + height)
        source = (texture_width * (1 - percent) if direction == 'Right' else 0, 0,
                  texture_width if direction == 'Right' else texture_width * percent, texture_height)
    return source, target


def scrollbar_thumb_bounds(bounds, scroll, content_height, minimum_thumb):
    """Return the scroll thumb as an edge rectangle from retained geometry."""
    x, y, width, height = bounds
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (x, y, width, height, scroll, content_height, minimum_thumb)) and
            width > 0 and height > 0 and content_height > 0 and minimum_thumb > 0 and
            0 <= scroll <= content_height - height,
            'Invalid captured ScrollBar thumb geometry')
    thumb_height = min(height, max(minimum_thumb, height * height / content_height))
    extent = content_height - height
    travel = max(0, height - thumb_height)
    thumb_top = y + travel * scroll / extent if extent else y
    return x, thumb_top, x + width, thumb_top + thumb_height


def production_scrollbar_thumb_bounds(bounds, scroll, content_height, viewport_height, minimum_thumb):
    """Draw the Production vertical shuttle from its retained panel range.

    A panel with no overflow uses a full-track thumb at the origin. Overflow
    scales the thumb by viewport/content and positions it by the captured
    scroll/max-scroll ratio. This is an owned frontend candidate policy.
    """
    x, y, width, height = bounds
    values = (x, y, width, height, scroll, content_height, viewport_height, minimum_thumb)
    require(all(type(value) in (int, float) and math.isfinite(value) for value in values) and
            width > 0 and height > 0 and content_height >= 0 and viewport_height > 0 and minimum_thumb > 0,
            'Invalid retained Production ScrollBar geometry or range')
    maximum_scroll = max(0.0, content_height - viewport_height)
    require(0 <= scroll <= maximum_scroll,
            'Production ScrollBar offset exceeds its captured ScrollPanel range')
    if content_height <= viewport_height:
        require(scroll == 0, 'Production ScrollBar with short content must have zero offset')
        return x, y, x + width, y + height
    thumb_height = min(height, max(minimum_thumb, height * viewport_height / content_height))
    thumb_travel = max(0.0, height - thumb_height)
    thumb_top = y + thumb_travel * scroll / maximum_scroll
    return x, thumb_top, x + width, thumb_top + thumb_height


def research_scrollbar_thumb_bounds(bounds, scroll, content_height, minimum_thumb):
    """Owned TechPopup thumb candidate from captured scroll range and original shuttle minimum size."""
    x, y, width, height = bounds
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (x, y, width, height, scroll, content_height, minimum_thumb)) and
            width > 0 and height > 0 and content_height >= 0 and minimum_thumb > 0,
            'Invalid retained Research ScrollBar geometry')
    maximum_scroll = max(0.0, content_height - height)
    require(0 <= scroll <= maximum_scroll, 'Research ScrollBar scroll exceeds captured range')
    if content_height <= height:
        require(scroll == 0, 'Research ScrollBar with short content must have zero scroll')
        return x, y, x + width, y + height
    return scrollbar_thumb_bounds(bounds, scroll, content_height, minimum_thumb)


def research_tree_scrollbar_thumb_bounds(bounds, scroll, content_width, viewport_width, minimum_thumb):
    """Owned TechTree horizontal thumb candidate from original shuttle size/range."""
    x, y, width, height = bounds
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (x, y, width, height, scroll, content_width, viewport_width, minimum_thumb)) and
            width > 0 and height > 0 and content_width >= 0 and viewport_width > 0 and minimum_thumb > 0,
            'Invalid retained ResearchTree ScrollBar geometry')
    maximum_scroll = max(0.0, content_width - viewport_width)
    require(0 <= scroll <= maximum_scroll, 'ResearchTree ScrollBar scroll exceeds captured range')
    if content_width <= width:
        require(scroll == 0, 'ResearchTree ScrollBar with short content must have zero scroll')
        return x, y, x + width, y + height
    thumb_width = min(width, max(minimum_thumb, width * viewport_width / content_width))
    travel = max(0.0, width - thumb_width)
    thumb_left = x + travel * scroll / maximum_scroll if maximum_scroll else x
    return thumb_left, y, thumb_left + thumb_width, y + height


def city_view_hex_center(hex_x, hex_y, projection):
    """Map a CityView axial hex to the official world-view odd-row screen center."""
    require(type(projection) is dict and projection.get('policy') == 'ZEROSIS_2D_CITY_VIEW_V1',
            'CityView projection policy differs from the retained map renderer contract')
    values = ('cameraX', 'cameraY', 'gridWidth', 'gridHeight', 'tileWidth', 'centerX', 'centerY')
    require(all(type(projection.get(name)) in (int, float) and math.isfinite(projection[name])
                for name in values), 'CityView projection lacks finite camera/grid geometry')
    camera_x, camera_y = int(projection['cameraX']), int(projection['cameraY'])
    grid_width, grid_height = int(projection['gridWidth']), int(projection['gridHeight'])
    require(grid_width > 0 and grid_height > 0 and projection['tileWidth'] > 0 and
            type(projection.get('wrapX')) is bool and type(projection.get('wrapY')) is bool and
            type(hex_x) is int and type(hex_y) is int,
            'CityView projection or axial hex coordinate is invalid')
    grid_x = hex_x + math.floor(hex_y / 2)
    grid_y = hex_y
    require(0 <= grid_x < grid_width and 0 <= grid_y < grid_height,
            'CityView axial hex resolves outside the retained map grid')
    dx, dy = grid_x - camera_x, grid_y - camera_y
    if projection['wrapX']:
        if dx > grid_width // 2:
            dx -= grid_width
        elif dx < -(grid_width // 2):
            dx += grid_width
    if projection['wrapY']:
        if dy > grid_height // 2:
            dy -= grid_height
        elif dy < -(grid_height // 2):
            dy += grid_height
    tile_width = float(projection['tileWidth'])
    tile_height = tile_width * 1.15470053838
    row_pitch = tile_height * 0.75
    center_x = projection['centerX'] + dx * tile_width + (((grid_y & 1) - (camera_y & 1)) * tile_width * 0.5)
    center_y = projection['centerY'] + dy * row_pitch
    require(math.isfinite(center_x) and math.isfinite(center_y), 'CityView projected hex center is nonfinite')
    return center_x, center_y, tile_width, tile_height


def city_view_hex_outline_rgba(width, height, line_width=0.7, samples=4):
    """Rasterize the WorldViewRenderer.cpp pointy-hex outline as an alpha mask."""
    require(type(width) is int and type(height) is int and width > 0 and height > 0 and
            type(samples) is int and 1 <= samples <= 8 and
            type(line_width) in (int, float) and math.isfinite(line_width) and line_width > 0,
            'Invalid CityView hex outline raster geometry')
    cx, cy = width / 2, height / 2
    tile_height = width * 1.15470053838
    points = ((cx, cy - tile_height / 2), (cx + width / 2, cy - tile_height / 4),
              (cx + width / 2, cy + tile_height / 4), (cx, cy + tile_height / 2),
              (cx - width / 2, cy + tile_height / 4), (cx - width / 2, cy - tile_height / 4))
    rgba = bytearray(width * height * 4)
    segments = tuple((points[i], points[(i + 1) % len(points)]) for i in range(len(points)))
    radius = line_width / 2
    for y in range(height):
        for x in range(width):
            covered = 0
            for sy in range(samples):
                py = y + (sy + 0.5) / samples
                for sx in range(samples):
                    px = x + (sx + 0.5) / samples
                    for (ax, ay), (bx, by) in segments:
                        vx, vy = bx - ax, by - ay
                        denom = vx * vx + vy * vy
                        t = max(0.0, min(1.0, ((px - ax) * vx + (py - ay) * vy) / denom))
                        if (px - (ax + t * vx)) ** 2 + (py - (ay + t * vy)) ** 2 <= radius * radius:
                            covered += 1
                            break
            if covered:
                at = (y * width + x) * 4
                rgba[at:at + 4] = bytes((255, 255, 255, round(255 * covered / (samples * samples))))
    return bytes(rgba)


def button_source_rect(u, v, target_width, target_height, texture_width, texture_height):
    """Use the available original button cell and let the target bounds scale it."""
    require(all(type(value) in (int, float) and math.isfinite(value)
                for value in (u, v, target_width, target_height, texture_width, texture_height)) and
            u >= 0 and v >= 0 and target_width > 0 and target_height > 0 and
            texture_width > u and texture_height > v,
            'Invalid original button texture region')
    source_width = min(target_width, texture_width - u)
    source_height = min(target_height, texture_height - v)
    require(source_width > 0 and source_height > 0, 'Button state has no original texture pixels')
    return u, v, u + source_width, v + source_height


def validate_hit_regions(context, hits, geometry):
    """Validate callback-backed input regions against the retained controls."""
    grid_buttons = [row for row in geometry if row.get('kind') == 'GridButton' and
                    not row.get('style_decoration')]
    if context in SCENE_CONTEXTS:
        targets = [row for row in geometry if row.get('input_target')]
        require(len(hits) == len(targets) and
                {hit[0] for hit in hits} == {row['key'] for row in targets},
                'Production hit regions differ from registered visible LeftClick targets')
        close_keys = [row['key'] for row in targets if row.get('id') == 'CloseButton']
        if context == 'production':
            require(len(close_keys) == 1, 'Production popup needs exactly one registered CloseButton target')
        elif context == 'research-tree':
            require(len(close_keys) == 1, 'Research tree needs exactly one registered CloseButton target')
        elif context == 'city-capture':
            require(not close_keys, 'CityCapture retains no close button callback; stock ESC consumes without closing')
        elif context == 'city-view':
            return_keys = [row['key'] for row in targets if row.get('id') == 'ReturnToMapButton']
            require(not close_keys and len(return_keys) == 1 and
                    all(row.get('input_targets') == ['LeftClick'] for row in targets
                        if row.get('id') == 'ReturnToMapButton'),
                    'CityView requires its unique original ReturnToMapButton left-click callback')
        elif context == 'diplomacy':
            back_keys = [row['key'] for row in targets if row.get('id') == 'BackButton']
            require(not close_keys and len(back_keys) == 1 and
                    all(row.get('input_targets') == ['LeftClick'] for row in geometry if row.get('input_targets')),
                    'LeaderHead intro requires one original BackButton callback and left-click targets')
        else:
            require(not close_keys, 'Research popup unexpectedly requires a Production CloseButton')
    else:
        require(all(any(hit[0] == row['key'] for row in grid_buttons) for hit in hits),
                'Hit region has no retained GridButton')
        require(context == 'ranking' and len(hits) == 1,
                'Selected ranking popup needs exactly one close-button hit region')
    require(hits, 'Selected popup has no retained hit regions')


def style_signature(node):
    # XML indentation and attribute ordering are not meaningful duplicate differences.
    return node.tag, tuple(sorted(node.attrib.items())), tuple(style_signature(child) for child in node)


def markup(text, colors, icons=None):
    """Preserve exact text/color runs, rejecting missing or unbalanced tokens."""
    chunks, tint, stack, cursor = [], [], [], 0
    icon_occurrences = {}
    for token in re.finditer(r'\[((?:[A-Z][A-Z_0-9]*)|(?:COLOR:[^\[\]]*))\]', text):
        prefix = text[cursor:token.start()]
        chunks.append(prefix)
        tint.extend([stack[-1] if stack else None] * len(prefix))
        name = token.group(1)
        if name.startswith('COLOR:'):
            channels = name[6:].split(':')
            require(len(channels) == 4 and all(re.fullmatch(r'\d+', channel) for channel in channels),
                    'Invalid original numeric inline RGBA color')
            rgba = tuple(int(channel) for channel in channels)
            require(all(0 <= channel <= 255 for channel in rgba),
                    'Out of range original numeric inline RGBA color')
            require(len(stack) < 16, 'Unknown/too deeply nested original inline color')
            stack.append(tuple(channel / 255 for channel in rgba))
        elif name.startswith('COLOR_'):
            require(name in colors and len(stack) < 16, 'Unknown/too deeply nested original inline color')
            stack.append(colors[name])
        elif name == 'ENDCOLOR':
            require(stack, 'Unbalanced original ENDCOLOR')
            stack.pop()
        elif name == 'NEWLINE':
            chunks.append('\n')
            tint.append(stack[-1] if stack else None)
        elif name.startswith('ICON_') and icons is not None:
            require(name in icons, 'Missing original inline icon mapping: ' + name)
            codepoint = 0xF0000 + len(icon_occurrences)
            icon_occurrences[codepoint] = icons[name]
            chunks.append(chr(codepoint))
            tint.append(stack[-1] if stack else None)
        else:
            raise ValueError('Unsupported original inline presentation token: ' + name)
        cursor = token.end()
    prefix = text[cursor:]
    chunks.append(prefix)
    tint.extend([stack[-1] if stack else None] * len(prefix))
    require(not stack, 'Unclosed original inline color')
    return (''.join(chunks), tint, icon_occurrences) if icons is not None else (''.join(chunks), tint)


def wrap_production_text(text, font, inline_glyphs, wrap_width):
    """Reflow captured post-token text using only original GGXML ABC advances."""
    def advance(value):
        total = 0
        for index, char in enumerate(value):
            glyph = inline_glyphs.get(ord(char), font.glyphs.get(ord(char)))
            require(glyph is not None, f'Production text has no exact GGXML glyph U+{ord(char):04X} at {index}')
            total += glyph.abc_advance
        return total

    # The owned Lua layout contract uses WrapWidth=0 when the source XML has
    # no WrapWidth attribute. That means natural/unwrapped text width; it does
    # not mean a zero-pixel wrapping box. Keep explicit newlines and all
    # authored spaces intact in this mode.
    if wrap_width == 0:
        return [(line, advance(line)) for line in
                text.replace('\r\n', '\n').replace('\r', '\n').split('\n')]

    result = []
    # Split explicit newlines while preserving empty lines, then apply the
    # documented ASCII-space word-wrap and codepoint split for long tokens.
    for explicit in text.replace('\r\n', '\n').replace('\r', '\n').split('\n'):
        words = explicit.split(' ')
        current = ''
        for word_index, word in enumerate(words):
            if not word:
                continue
            fragments = []
            fragment = ''
            for char in word:
                candidate = fragment + char
                if fragment and advance(candidate) > wrap_width:
                    fragments.append(fragment)
                    fragment = char
                else:
                    fragment = candidate
            if fragment:
                fragments.append(fragment)
            for fragment_index, piece in enumerate(fragments):
                candidate = piece if not current else current + ' ' + piece
                if current and advance(candidate) > wrap_width:
                    result.append((current, advance(current)))
                    current = piece
                else:
                    current = candidate
                if fragment_index + 1 < len(fragments):
                    result.append((current, advance(current)))
                    current = ''
        result.append((current, advance(current)))
    return result


def xywh_dict(value, label):
    require(type(value) is dict and all(type(value.get(name)) in (int, float) and
            math.isfinite(value[name]) for name in ('x', 'y', 'width', 'height')) and
            value['width'] >= 0 and value['height'] >= 0,
            'Invalid ' + label + ' XYWH bounds')
    return (value['x'], value['y'], value['x'] + value['width'], value['y'] + value['height'])


def glyph_quad(glyph, font):
    # DDS pixel inspection establishes that the authored glyph masks extend
    # beyond GGXML width/height inside its spacing border (e.g. lower-case l).
    # Keep that border in the sampled quad without adding it to ABC advance.
    # The half-border placement is a candidate convention, not retail calibration.
    u, v, width, height = glyph.texture_rect
    require(0 <= font.spacing <= 32, 'Unbounded glyph atlas border')
    return (u, v, width + font.spacing, height + font.spacing), font.spacing / 2


def grid_targets(sizes, bounds):
    x, y, w, h = bounds
    ul, uc, ur, left, center, right, ll, lc, lr = [sizes[n] for n in ('UL', 'UC', 'UR', 'L', 'C', 'R', 'LL', 'LC', 'LR')]
    dimensions = ((ul[0], ul[1]), (w - ul[0] - ur[0], uc[1]), (ur[0], ur[1]),
                  (left[0], h - ul[1] - ll[1]), (w - left[0] - right[0], h - uc[1] - lc[1]),
                  (right[0], h - ur[1] - lr[1]), (ll[0], ll[1]),
                  (w - ll[0] - lr[0], lc[1]), (lr[0], lr[1]))
    positions = ((x, y), (x + ul[0], y), (x + w - ur[0], y),
                 (x, y + ul[1]), (x + left[0], y + uc[1]), (x + w - right[0], y + ur[1]),
                 (x, y + h - ll[1]), (x + ll[0], y + h - lc[1]), (x + w - lr[0], y + h - lr[1]))
    require(all(a >= 0 and b >= 0 for a, b in dimensions), 'Grid too small for original edge sizes')
    return [(px, py, px + sw, py + sh) for (px, py), (sw, sh) in zip(positions, dimensions)]


def scroll_mask_rgba(texture_pixels, texture_width, texture_height, mask_pixels, mask_width, mask_height,
                     width, height, phase, offset_x=0, offset_y=0):
    """Build a bounded nearest-sampled ScrollAnim candidate from original DDS pixels.

    ScrollAnim Size is the output/control size, while TextureOffset selects an
    origin in the foreground atlas. The remaining foreground image is sampled
    through a phase-positioned viewport, then stretched to Size; the full mask
    is stretched to the same output rectangle. This is an explicit frontend
    sampling policy, not a claim about retail shader/filter equivalence.
    """
    require(all(type(value) is int and value > 0 for value in
                (texture_width, texture_height, mask_width, mask_height, width, height)),
            'Invalid ScrollAnim source dimensions')
    require(width <= 32768 and height <= 32768 and width * height <= 16_777_216,
            'ScrollAnim output exceeds the bounded frontend raster limit')
    require(len(texture_pixels) == texture_width * texture_height * 4 and
            len(mask_pixels) == mask_width * mask_height * 4,
            'ScrollAnim source/mask payload size differs from DDS dimensions')
    require(type(phase) in (int, float) and math.isfinite(phase) and 0 <= phase <= 1,
            'ScrollAnim phase is outside the captured timeline')
    require(type(offset_x) is int and type(offset_y) is int, 'ScrollAnim TextureOffset is invalid')
    require(0 <= offset_x < texture_width and 0 <= offset_y < texture_height,
            'ScrollAnim TextureOffset escapes the original foreground texture')
    source_width = texture_width - offset_x
    source_height = texture_height - offset_y
    sample_height = min(height, source_height)
    out = bytearray(width * height * 4)
    travel = source_height - sample_height
    for y in range(height):
        sy = offset_y + int(math.floor(phase * travel + (y + 0.5) * sample_height / height))
        sy = min(texture_height - 1, sy)
        my = min(mask_height - 1, int((y + 0.5) * mask_height / height))
        for x in range(width):
            sx = offset_x + min(source_width - 1, int((x + 0.5) * source_width / width))
            mx = min(mask_width - 1, int((x + 0.5) * mask_width / width))
            source_at = (sy * texture_width + sx) * 4
            mask_at = (my * mask_width + mx) * 4
            dest_at = (y * width + x) * 4
            out[dest_at:dest_at + 3] = texture_pixels[source_at:source_at + 3]
            out[dest_at + 3] = (texture_pixels[source_at + 3] * mask_pixels[mask_at + 3] + 127) // 255
    return bytes(out)


def meter_arc_rgba(texture_pixels, width, height, percent, percent_plus=0):
    """Keep the source meter art in captured clockwise progress arcs from twelve o'clock."""
    require(type(width) is int and type(height) is int and width > 0 and height > 0 and
            len(texture_pixels) == width * height * 4, 'Invalid original Meter texture payload')
    require(all(type(value) in (int, float) and math.isfinite(value) and 0 <= value <= 1
                for value in (percent, percent_plus)),
            'Meter fractions are outside the captured normalized range')
    out = bytearray(texture_pixels)
    cx, cy = width / 2, height / 2
    total = min(1.0, percent + percent_plus)
    for y in range(height):
        for x in range(width):
            dx, dy = x + .5 - cx, y + .5 - cy
            angle = (math.atan2(dx, -dy) / (2 * math.pi)) % 1.0
            if angle >= total:
                out[(y * width + x) * 4 + 3] = 0
    return bytes(out)


class Compiler:
    def __init__(self, game_root, destination, *, width=1920, height=1080, inline_colors=None,
                 inline_icons=None, context='ranking', snapshot_clock=0,
                 city_view_layout_variant='default'):
        require((width, height) == (1920, 1080), 'Selected popup currently requires the verified 1920x1080 viewport')
        self.game_root = Path(game_root).resolve(strict=True)
        self.destination = candidate_directory(destination, self.game_root)
        self.width, self.height = width, height
        require(context in ('ranking', 'production', 'research', 'research-tree', 'city-capture', 'diplomacy', 'city-view'), 'Unsupported selected UI context')
        require(type(snapshot_clock) in (int, float) and math.isfinite(snapshot_clock) and snapshot_clock >= 0,
                'Invalid selected presentation clock')
        require(city_view_layout_variant in ('default', 'small') and
                (context == 'city-view' or city_view_layout_variant == 'default'),
                'Invalid CityView layout variant for the selected UI context')
        self.context, self.snapshot_clock = context, snapshot_clock
        self.city_view_layout_variant = city_view_layout_variant if context == 'city-view' else None
        self.inline_colors = dict(inline_colors or {})
        self.inline_icons = dict(inline_icons or {})
        self.assets = UiAssets(self.game_root)
        self.styles_path = self.game_root / 'Assets/UI/Styles.xml'
        self.styles_hash = sha256(self.styles_path)
        layout_relative = {'production': 'Assets/DLC/Expansion2/UI/InGame/Popups/ProductionPopup.xml',
                           'research': 'Assets/DLC/Expansion2/UI/InGame/TechPopup.xml',
                           'research-tree': 'Assets/DLC/Expansion2/UI/InGame/TechTree/TechTree.xml',
                           'ranking': 'Assets/DLC/Expansion2/UI/InGame/Popups/WhosWinningPopup.xml',
                           'city-capture': 'Assets/UI/InGame/Popups/GenericPopup.xml',
                           'diplomacy': 'Assets/DLC/Expansion2/UI/InGame/LeaderHead/LeaderHeadRoot.xml',
                           'city-view': ('Assets/DLC/Expansion2/UI/InGame/CityView/CityView_small.xml'
                                         if city_view_layout_variant == 'small' else
                                         'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.xml')}[context]
        self.layout_path = self.game_root / layout_relative
        self.leader_button_sources = {}
        if context == 'diplomacy':
            leader_root = ET.parse(self.layout_path).getroot()
            require(leader_root.tag == 'Context' and leader_root.attrib.get('Name') == 'LeaderHeadRoot',
                    'Selected diplomacy layout is not original LeaderHeadRoot')
            button_ids = {'BackButton', 'DiscussButton', 'DemandButton', 'TradeButton', 'WarButton'}
            self.leader_button_sources = {
                element.attrib['ID']: dict(element.attrib)
                for element in leader_root.iter('GridButton')
                if element.attrib.get('ID') in button_ids}
            require(set(self.leader_button_sources) == button_ids and
                    all('String' in self.leader_button_sources[name] for name in button_ids),
                    'Original LeaderHeadRoot direct button text contract differs from the selected XML')
        self.script_path = (self.game_root / 'Assets/DLC/Expansion2/UI/TechTree/TechTree.lua'
                            if context == 'research-tree' else
                            self.game_root / 'Assets/DLC/Expansion2/UI/InGame/PopupsGeneric/PuppetCityPopup.lua'
                            if context == 'city-capture' else
                            self.game_root / 'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.lua'
                            if context == 'city-view' else self.layout_path.with_suffix('.lua'))
        self.context_sources = {self.layout_path: sha256(self.layout_path), self.script_path: sha256(self.script_path)}
        self.city_view_context_font_policy = None
        self.city_view_source_context_attributes = None
        if context == 'city-view':
            city_view_root = ET.parse(self.layout_path).getroot()
            require(city_view_root.tag == 'Context', 'Selected original CityView layout has no Context root')
            self.city_view_source_context_attributes = dict(city_view_root.attrib)
        if context == 'city-view' and city_view_layout_variant == 'small':
            standard_layout = self.game_root / 'Assets/DLC/Expansion2/UI/InGame/CityView/CityView.xml'
            standard_hash = sha256(standard_layout)
            standard_root = ET.parse(standard_layout).getroot()
            require(standard_root.tag == 'Context' and
                    standard_root.attrib.get('Font') == 'TwCenMT20' and
                    standard_root.attrib.get('FontStyle') == 'Shadow',
                    'Original standard CityView Context font fallback source differs')
            self.context_sources[standard_layout] = standard_hash
            self.city_view_context_font_policy = {
                'policy': 'ORIGINAL_CITY_VIEW_CONTEXT_FONT_FALLBACK_CANDIDATE_V1',
                'retail_default_font_verified': False,
                'attributes': {'Font': 'TwCenMT20', 'FontStyle': 'Shadow'},
                'source': {'path': str(standard_layout.resolve()), 'sha256': standard_hash,
                           'bytes': standard_layout.stat().st_size},
            }
        if context == 'city-capture':
            for relative in ('Assets/UI/InGame/Popups/GenericPopup.lua',
                             'Assets/UI/InGame/Popups/EmptyPopup.lua',
                             'Assets/UI/InGame/Popups/EmptyPopup.xml'):
                source = self.game_root / relative
                self.context_sources[source] = sha256(source)
        if context in SCENE_CONTEXTS:
            relatives = (() if context == 'city-capture' else
                         ('Assets/Gameplay/Lua/GameplayUtilities.lua',
                          'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                          'Assets/UI/IconSupport.lua',
                          'Assets/DLC/Expansion2/UI/InGame/LeaderHead/DiscussionDialog.lua',
                          'Assets/DLC/Expansion2/UI/InGame/LeaderHead/DiscussionDialog.xml',
                          'Assets/UI/InGame/LeaderHead/DiploTrade.lua',
                          'Assets/DLC/Expansion2/UI/InGame/LeaderHead/DiploTrade.xml',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'diplomacy' else
                         ('Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                          'Assets/UI/IconSupport.lua', 'Assets/Gameplay/Lua/FLuaVector.lua',
                          'Assets/UI/InstanceManager.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'production' else
                         ('Assets/UI/SupportFunctions.lua', 'Assets/UI/IconSupport.lua',
                          'Assets/UI/InstanceManager.lua',
                          'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                          'Assets/Gameplay/Lua/FLuaVector.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml')
                         if context == 'city-view' else
                         ('Assets/DLC/Expansion2/UI/InGame/TechTree/TechButtonInclude.lua',
                          'Assets/DLC/Expansion2/UI/InGame/TechTree/TechHelpInclude.lua',
                          'Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua',
                          'Assets/UI/IconSupport.lua', 'Assets/Gameplay/Lua/FLuaVector.lua',
                          'Assets/UI/InstanceManager.lua',
                          'Assets/Gameplay/XML/GameInfo/CIV5IconFontMapping.xml',
                          'Assets/DLC/Expansion2/Gameplay/XML/GameInfo/CIV5IconFontMapping_Expansion2.xml'))
            for relative in relatives:
                source = self.game_root / relative
                self.context_sources[source] = sha256(source)
            for icon in self.inline_icons.values():
                require(type(icon) is dict, 'Malformed prepared icon mapping entry')
                for field in ('mapping_source', 'font_source'):
                    source = icon.get(field)
                    require(type(source) is dict and isinstance(source.get('path'), str) and
                            isinstance(source.get('sha256'), str),
                            'Prepared icon mapping lacks original source provenance: ' + field)
                    source_path = Path(source['path'])
                    path = (source_path if source_path.is_absolute() else self.game_root / source_path).resolve(strict=True)
                    digest = sha256(path)
                    require(digest == source['sha256'], 'Prepared icon source hash differs: ' + str(path))
                    self.context_sources[path] = digest
        root = ET.parse(self.styles_path).getroot()
        self.styles = {}
        for node in root:
            if node.tag in self.styles:
                require(style_signature(self.styles[node.tag]) == style_signature(node), 'Conflicting original style definitions')
            else:
                self.styles[node.tag] = node
        self.textures, self.texture_ids = [], {}
        self.sprites, self.hits, self.scroll_regions, self.geometry, self.labels = [], [], [], [], []
        self.fonts, self.font_records, self.sources = {}, [], {}
        self.derived_textures = []
        self.scroll_texture_cache = {}
        self.production_font_metrics = None
        self.production_input_targets = None
        self.production_scroll_targets = None
        self.production_scroll_targets_by_key = {}
        self.city_view_projection = None
        self.city_view_hexes = []
        self.city_view_policy = None
        self.research_tree_scroll_targets = None
        self.icon_font_glyphs = {}
        self.keys = set()
        for name, color in self.inline_colors.items():
            require(name.startswith('COLOR_') and len(color) == 4 and all(math.isfinite(v) and 0 <= v <= 1 for v in color),
                    'Invalid original database text color')

    def texture(self, texture_name):
        record = self.assets.resolve(texture_name, self.destination / 'textures')
        path = Path(record['output']['path'])
        conversion = record['conversion']
        return self.register_texture(path, conversion['width'], conversion['height'])

    def register_texture(self, path, width, height):
        name = str(path.resolve())
        if name not in self.texture_ids:
            self.texture_ids[name] = len(self.textures)
            self.textures.append(name)
        return self.texture_ids[name], width, height

    def paint(self, key, texture, source, target, clip, color=(1, 1, 1, 1)):
        require(all(math.isfinite(v) for v in (*source, *target, *clip, *color)), 'Nonfinite paint geometry')
        require(all(0 <= v <= 1 for v in color), 'Out of range paint tint')
        if not positive(target) or not positive(clip) or color[3] == 0:
            return
        if texture != SOLID:
            require(positive(source) and source[0] >= 0 and source[1] >= 0, 'Invalid original atlas source rect')
        self.sprites.append((texture, key, *source, *target, *clip, *color))

    def production_hits(self, root):
        require(self.context in SCENE_CONTEXTS and type(self.production_input_targets) is list,
                'Retained input target validation was not initialized')
        nodes = {}
        def collect(node, clip, visible, hover_visible):
            visible = visible and not node.get('hidden', True)
            if not visible:
                return
            kind = node.get('kind')
            bounds = (node.get('x'), node.get('y'), node.get('width'), node.get('height'))
            if kind == 'ShowOnMouseOver':
                hovered = node.get('hovered')
                require(type(hovered) is bool, 'ShowOnMouseOver lacks captured hover state for hit testing')
                hover_visible = hover_visible and hovered
            if kind == 'ScrollPanel':
                clip = intersect(clip, rect(bounds))
            nodes[node['key']] = (node, clip, hover_visible)
            for child in node.get('children', []):
                collect(child, clip, visible, hover_visible)

        collect(root, (0, 0, self.width, self.height), True, True)
        seen = set()
        left_keys = set()
        geometry_by_key = {row['key']: row for row in self.geometry if not row.get('style_decoration')}
        for target in self.production_input_targets:
            allowed_events = ('LeftClick', 'RightClick')
            require(type(target) is dict and target.get('event') in allowed_events and
                    target.get('visible') is True and target.get('disabled') is False and
                    type(target.get('key')) is int and (target['key'], target['event']) not in seen,
                    'Retained input target is malformed, duplicated, hidden, disabled, or unsupported')
            if self.context in SCENE_CONTEXTS:
                require(all(name not in target or type(target[name]) in (int, float) and
                            math.isfinite(target[name]) for name in ('void1', 'void2')),
                        'Popup callback payload must preserve scalar numeric arguments')
            seen.add((target['key'], target['event']))
            require(target['key'] in nodes and target['key'] in geometry_by_key,
                    'Retained input target has no retained/rendered control')
            node, clip, hover_visible = nodes[target['key']]
            geometry = geometry_by_key[target['key']]
            allowed_kinds = ('Button', 'GridButton', 'TextButton', 'UpButton', 'DownButton')
            if self.context == 'city-view':
                allowed_kinds += ('CheckBox', 'RadioButton')
            require(hover_visible and node.get('kind') in allowed_kinds and
                    node.get('id', '') == target.get('id', ''),
                    'Retained input target disagrees with retained button kind/id or hover visibility')
            require(node.get('buttonState') in ('normal', 'hover'),
                    'Retained input target has missing/disabled/pressed retained button state')
            if self.context in RESEARCH_CONTEXTS and node.get('id') in ('TechButton', 'B1', 'B2', 'B3', 'B4', 'B5'):
                require(type(target.get('void1')) is int and type(target.get('void2')) is int,
                        'Tech selection callback lacks its retained scalar techID/freeCount tuple')
            target_bounds = xywh_dict(target.get('bounds'), 'input target')
            node_bounds = rect((node['x'], node['y'], node['width'], node['height']))
            require(all(abs(a - b) <= 1e-6 for a, b in zip(target_bounds, node_bounds)),
                    'Retained input target bounds differ from retained button bounds')
            clipped = intersect(node_bounds, clip)
            captured_clipped = xywh_dict(target.get('clippedBounds'), 'clipped input target')
            require(positive(clipped) and all(abs(a - b) <= 1e-6 for a, b in zip(clipped, captured_clipped)),
                    'Retained input target clipping differs from retained viewport ancestry')
            geometry.setdefault('input_targets', []).append(target['event'])
            if target['event'] == 'LeftClick':
                require(target['key'] not in left_keys, 'Duplicate LeftClick hit target')
                left_keys.add(target['key'])
                geometry['input_target'] = True
                self.hits.append((node['key'], *clipped))
        validate_hit_regions(self.context, self.hits, self.geometry)

    def production_scrolls(self, root):
        require(self.context in SCENE_CONTEXTS and type(self.production_scroll_targets) is list,
                'Retained scroll target validation was not initialized')
        panels = {}

        def collect(node, clip, visible):
            visible = visible and not node.get('hidden', True)
            if not visible:
                return
            kind = node.get('kind')
            bounds = (node.get('x'), node.get('y'), node.get('width'), node.get('height'))
            if kind == 'ScrollPanel':
                panel_bounds = rect(bounds)
                clipped = intersect(panel_bounds, clip)
                if positive(clipped):
                    attrs = node.get('attributes')
                    horizontal = self.context == 'research-tree'
                    axis = 'X' if horizontal else 'Y'
                    content_name = 'contentWidth' if horizontal else 'contentHeight'
                    viewport = bounds[2] if horizontal else bounds[3]
                    require(type(attrs) is dict and attrs.get('Vertical') == ('0' if horizontal else '1'),
                            'Retained scroll target has the wrong original ScrollPanel orientation')
                    scroll = node.get('scrollX' if horizontal else 'scrollY')
                    content = node.get(content_name)
                    require(type(scroll) in (int, float) and math.isfinite(scroll) and
                            type(content) in (int, float) and math.isfinite(content) and
                            content >= 0 and viewport > 0,
                            'Visible retained ScrollPanel lacks finite captured scroll geometry')
                    maximum_scroll = max(0.0, content - viewport)
                    require(0 <= scroll <= maximum_scroll,
                            'Visible ScrollPanel offset exceeds its captured content range')
                    panels[node['key']] = (node, panel_bounds, clipped, axis, scroll,
                                           content, viewport, maximum_scroll)
                clip = intersect(clip, panel_bounds)
            for child in node.get('children', []):
                collect(child, clip, visible)

        collect(root, (0, 0, self.width, self.height), True)
        targets = {}
        horizontal = self.context == 'research-tree'
        state_fields = (('orientation', 'scrollX', 'contentWidth', 'viewportWidth') if horizontal else
                        ('scrollY', 'contentHeight', 'viewportHeight'))
        required = ('key', 'id', 'event', 'visible', 'disabled', 'bounds', 'clippedBounds', *state_fields,
                    'maximumScroll')
        for target in self.production_scroll_targets:
            require(type(target) is dict and all(field in target for field in required) and
                    target.get('event') == 'Scroll' and target.get('visible') is True and
                    target.get('disabled') is False and type(target.get('key')) is int and
                    target['key'] not in targets,
                    'Retained scroll target is malformed, duplicated, hidden, disabled, or not Scroll')
            targets[target['key']] = target
        require(set(targets) == set(panels),
                'Scroll targets differ from visible clipped oriented ScrollPanels')
        if horizontal:
            require(len(targets) == 1 and next(iter(targets.values())).get('id') == 'TechTreeScrollPanel',
                    'TechTree must expose exactly its original TechTreeScrollPanel target')
            self.research_tree_scroll_targets = targets
        if self.context == 'city-view':
            require(all(target.get('orientation', 'vertical') == 'vertical' for target in targets.values()),
                    'CityView only supports original vertical ScrollPanel targets')
        self.production_scroll_targets_by_key = targets
        for key, (node, bounds, clipped, axis, scroll, content, viewport, maximum_scroll) in panels.items():
            target = targets[key]
            require(target.get('id') == node.get('id', ''),
                    'Scroll target id differs from retained ScrollPanel')
            if horizontal:
                require(target.get('orientation') == 'horizontal',
                        'TechTree scroll target is not marked horizontal')
            captured_bounds = xywh_dict(target.get('bounds'), 'scroll target')
            captured_clip = xywh_dict(target.get('clippedBounds'), 'clipped scroll target')
            expected_bounds = bounds
            expected_clip = clipped
            require(all(abs(a - b) <= 1e-6 for a, b in zip(captured_bounds, expected_bounds)) and
                    all(abs(a - b) <= 1e-6 for a, b in zip(captured_clip, expected_clip)),
                    'Scroll target bounds/clipping differ from retained viewport ancestry')
            names = (('scrollX', scroll), ('contentWidth', content), ('viewportWidth', viewport),
                     ('maximumScroll', maximum_scroll)) if horizontal else (
                     ('scrollY', scroll), ('contentHeight', content), ('viewportHeight', viewport),
                     ('maximumScroll', maximum_scroll))
            for field, expected in names:
                actual = target.get(field)
                require(type(actual) in (int, float) and math.isfinite(actual) and
                        abs(actual - expected) <= 1e-6,
                        'Scroll target ' + field + ' differs from retained ScrollPanel state')
            self.scroll_regions.append((key, *clipped))
        self.scroll_regions.sort(key=lambda row: row[0])
        require(len(self.scroll_regions) <= 10000, 'Unbounded retained scroll region list')

    def validate_icon_glyph(self, icon):
        require(type(icon) is dict and type(icon.get('glyph')) is dict and
                type(icon.get('mapping')) is int and type(icon.get('font_source')) is dict,
                'Malformed prepared original inline icon record')
        source = icon['font_source']
        relative = source.get('path')
        require(type(relative) is str and type(source.get('sha256')) is str,
                'Inline icon font provenance is incomplete')
        path = Path(relative)
        path = path if path.is_absolute() else self.game_root / path
        path = path.resolve(strict=True)
        digest = sha256(path)
        require(digest == source['sha256'], 'Inline icon GGXML source hash changed')
        glyphs = self.icon_font_glyphs.get(str(path))
        if glyphs is None:
            root = ET.parse(path).getroot()
            glyphs = {int(element.attrib['ch']): element.attrib for element in root.findall('./glyphs/glyph')}
            self.icon_font_glyphs[str(path)] = glyphs
        original = glyphs.get(icon['mapping'])
        captured = icon['glyph']
        require(original is not None and
                (int(original['u']), int(original['v']), int(original['width']), int(original['height']),
                 int(original['a']) + int(original['b']) + int(original['c']),
                 int(original['originx']), int(original['originy'])) ==
                (captured.get('u'), captured.get('v'), captured.get('width'), captured.get('height'),
                 captured.get('advance'), captured.get('originx'), captured.get('originy')),
                'Prepared inline icon metrics differ from its original GGXML glyph')

    def color(self, raw):
        # Original palette values are loaded through the same font asset parser.
        if not self.fonts:
            self.font('TwCenMT14', 'Base')
        palette = next(iter(self.fonts.values())).colors
        parts = raw.replace('.', ',').split(',')
        if len(parts) == 4 and all(re.fullmatch(r'\d+', p) for p in parts):
            values = tuple(int(p) for p in parts)
        else:
            require(len(parts) in (1, 2) and parts[0] in palette, 'Unknown original color ' + raw)
            values = palette[parts[0]].rgba
            if len(parts) == 2:
                require(re.fullmatch(r'\d+', parts[1]), 'Invalid color alpha')
                values = (*values[:3], int(parts[1]))
        require(all(0 <= v <= 255 for v in values), 'Out of range original color')
        return tuple(v / 255 for v in values)

    def font(self, font_id, style):
        key = font_id, style
        if key not in self.fonts:
            font = load_font(self.game_root, font_id, style)
            self.fonts[key] = font
            sheets = []
            for layer in font.layers:
                source = layer.sheet.path
                output = candidate_directory(self.destination / 'textures', self.game_root) / source.name
                require(output.resolve().is_relative_to(self.destination) and not output.is_symlink(), 'Font candidate escaped scene directory')
                if not output.exists():
                    with source.open('rb') as src, output.open('xb') as dst:
                        shutil.copyfileobj(src, dst)
                require(sha256(output) == layer.sheet.sha256, 'Font atlas copy differs from source')
                sheets.append({'order': layer.order, 'alias': layer.texture_alias, 'source_path': str(source),
                               'source_sha256': layer.sheet.sha256,
                               'path': str(output), 'sha256': sha256(output)})
            self.font_records.append({'font_id': font_id, 'style': style,
                'ggxml_path': str(font.ggxml_path), 'ggxml_sha256': font.ggxml_sha256,
                'color_atlas_path': str(font.color_atlas_path), 'color_atlas_sha256': font.color_atlas_sha256,
                'height': font.height, 'ascent': font.ascent, 'descent': font.descent,
                'ascadj': font.ascadj, 'fudgeadv': font.fudgeadv, 'spacing': font.spacing,
                'horizontal_policy': 'ABC_ADVANCE_NO_UNPROVEN_SPACING',
                'vertical_policy': 'CANDIDATE_ASCENT_DESCENT_PLUS_ASCADJ',
                'glyph_quad_policy': 'GGXML_SPACING_BORDER_NO_EXTRA_CHARACTER_ADVANCE',
                'border_placement_policy': 'CANDIDATE_HALF_BORDER_OFFSET',
                'retail_metric_semantics_verified': False, 'sheets': sheets})
        return self.fonts[key]

    def grid(self, key, style, bounds, clip):
        attrs = style.attrib
        texture, tw, th = self.texture(attrs['Texture'])
        sizes = {name: pair(attrs[name + 'Size']) for name in ('UL', 'UC', 'UR', 'L', 'C', 'R', 'LL', 'LC', 'LR')}
        targets = grid_targets(sizes, bounds)
        for n, name in enumerate(('UL', 'UC', 'UR', 'L', 'C', 'R', 'LL', 'LC', 'LR')):
            u, v = pair(attrs[name + 'TexStart'])
            w, h = sizes[name]
            require(u >= 0 and v >= 0 and u + w <= tw and v + h <= th, 'Grid piece outside original atlas')
            self.paint(key, texture, (u, v, u + w, v + h), targets[n], clip)

    def style_control(self, element, owner_key, *, hovered=False):
        """Build one original Styles.xml decoration as a candidate retained control."""
        attrs = dict(element.attrib)
        size = attrs.get('Size', '0,0').replace('.', ',').split(',')
        require(len(size) == 2, 'Unsupported original style decoration size')
        dimensions = []
        for raw, full in zip(size, (self.width, self.height)):
            dimensions.append(float(full if raw == 'Full' else raw))
        hidden = attrs.get('Hidden', '0') in ('1', 'True', 'true')
        offset_x, offset_y = pair(attrs.get('TextureOffset', '0,0'))
        children = [self.style_control(child, owner_key, hovered=hovered) for child in element]
        node = {'key': owner_key, 'kind': element.tag, 'attributes': attrs,
                'width': dimensions[0], 'height': dimensions[1], 'hidden': hidden,
                'children': children, 'id': '', 'text': attrs.get('String', ''),
                'texture': attrs.get('Texture', ''), 'textureX': offset_x, 'textureY': offset_y,
                'hovered': hovered, 'buttonState': 'hover' if hovered else 'normal'}
        if element.tag == 'AlphaAnim':
            start, finish = float(attrs['AlphaStart']), float(attrs['AlphaEnd'])
            speed, pause = float(attrs['Speed']), float(attrs.get('Pause', '0'))
            require(speed > 0 and pause >= 0 and attrs.get('Cycle') == 'Bounce',
                    'Unsupported original style AlphaAnim timing contract')
            period = 2 * (speed + pause)
            time = self.snapshot_clock % period
            if time < pause:
                alpha = start
            elif time < pause + speed:
                alpha = start + (finish - start) * ((time - pause) / speed)
            elif time < 2 * pause + speed:
                alpha = finish
            else:
                alpha = finish + (start - finish) * ((time - 2 * pause - speed) / speed)
            node['animation'] = {'clock': self.snapshot_clock, 'alpha': max(0.0, min(1.0, alpha))}
        return node

    def render_style_children(self, style, owner_key, bounds, inherited, clip, *, hovered=False):
        for child in style:
            synthetic = self.style_control(child, owner_key, hovered=hovered)
            self.node(synthetic, bounds, inherited, clip, decoration=True)

    def vertical_strip(self, key, style, bounds, clip):
        """Paint an original vertical 9-slice strip with its center stretched."""
        attrs = style.attrib
        texture, tw, th = self.texture(attrs['Texture'])
        x0, y0, x1, y1 = bounds
        top_h = pair(attrs.get('UCSize', '0,0'))[1]
        center_w, center_h = pair(attrs['CSize'])
        bottom_h = pair(attrs.get('LCSize', '0,0'))[1]
        require(y1 - y0 >= top_h + bottom_h and center_w <= x1 - x0,
                'Vertical strip is smaller than its original caps')
        for size_key, start_key, target_y, target_h in (
                ('UCSize', 'UCTexStart', y0, top_h),
                ('CSize', 'CTexStart', y0 + top_h, y1 - y0 - top_h - bottom_h),
                ('LCSize', 'LCTexStart', y1 - bottom_h, bottom_h)):
            w, source_h = pair(attrs.get(size_key, '0,0'))
            if w == 0 or source_h == 0 or target_h == 0:
                continue
            u, v = pair(attrs[start_key])
            require(u + w <= tw and v + source_h <= th, 'Vertical strip region escapes original texture')
            self.paint(key, texture, (u, v, u + w, v + source_h),
                       (x0, target_y, x0 + w, target_y + target_h), clip)

    def horizontal_strip(self, key, style, bounds, clip):
        """Paint original horizontal left/center/right texture regions."""
        attrs = style.attrib
        texture, tw, th = self.texture(attrs['Texture'])
        x0, y0, x1, y1 = bounds
        left_w, left_h = pair(attrs.get('LSize', '0,0'))
        center_w, center_h = pair(attrs['CSize'])
        right_w, right_h = pair(attrs.get('RSize', '0,0'))
        require(x1 - x0 >= left_w + right_w and max(left_h, center_h, right_h) <= y1 - y0,
                'Horizontal strip is smaller than its original caps')
        for size_key, start_key, target_x, target_w in (
                ('LSize', 'LTexStart', x0, left_w),
                ('CSize', 'CTexStart', x0 + left_w, x1 - x0 - left_w - right_w),
                ('RSize', 'RTexStart', x1 - right_w, right_w)):
            source_w, source_h = pair(attrs.get(size_key, '0,0'))
            if source_w == 0 or source_h == 0 or target_w == 0:
                continue
            u, v = pair(attrs[start_key])
            require(u + source_w <= tw and v + source_h <= th,
                    'Horizontal strip region escapes original texture')
            self.paint(key, texture, (u, v, u + source_w, v + source_h),
                       (target_x, y0, target_x + target_w, y1), clip)

    def image(self, key, texture_name, u, v, bounds, clip, color, *, stretch_full_texture=False,
              source_extent=None):
        texture, tw, th = self.texture(texture_name)
        name = texture_name.replace('\\', '/').rsplit('/', 1)[-1].casefold()
        scalable = self.assets.outputs[name]['conversion']['source_scalable']
        if scalable and (u != 0 or v != 0):
            require(self.context == 'city-view', 'Scalable images with atlas offsets need separate verification')
            source, target, policy = image_regions(u, v, bounds, (tw, th), source_extent=source_extent)
            policy = 'CITY_VIEW_SCALABLE_EXPLICIT_ATLAS_SUBREGION_CANDIDATE'
        elif scalable:
            source, target, policy = image_regions(u, v, bounds, (tw, th), stretch_full_texture=True)
            policy = 'SOURCE_ASSET_MARKED_SCALABLE_TEXTURE'
        else:
            extent = source_extent or bounds[2:]
            require(stretch_full_texture or (u + extent[0] <= tw and v + extent[1] <= th),
                    f'Image {key}/{texture_name}: source {u},{v}+{extent} exceeds original atlas {tw}x{th}')
            source, target, policy = image_regions(
                u, v, bounds, (tw, th), stretch_full_texture=stretch_full_texture,
                source_extent=source_extent)
        self.paint(key, texture, source, target, clip, color)
        return policy

    def scroll_animation_texture(self, node, attrs, width, height):
        animation = node.get('animation')
        require(type(animation) is dict and animation.get('clock') == self.snapshot_clock and
                type(animation.get('phase')) in (int, float) and math.isfinite(animation['phase']) and
                0 <= animation['phase'] <= 1,
                'ScrollAnim lacks captured phase at the selected presentation clock')
        texture_name = node.get('texture') or attrs.get('Texture')
        mask_name = attrs.get('MaskTexture')
        require(isinstance(texture_name, str) and texture_name and isinstance(mask_name, str) and mask_name,
                'ScrollAnim lacks its original texture or mask')
        texture_record = self.assets.resolve(texture_name, self.destination / 'textures')
        mask_record = self.assets.resolve(mask_name, self.destination / 'textures')
        texture_path = Path(texture_record['output']['path'])
        mask_path = Path(mask_record['output']['path'])
        texture_dds, mask_dds = texture_path.read_bytes(), mask_path.read_bytes()
        texture_header, mask_header = header(texture_dds), header(mask_dds)
        rgba32(texture_header); rgba32(mask_header)
        texture_width, texture_height = texture_header[4], texture_header[3]
        mask_width, mask_height = mask_header[4], mask_header[3]
        size = attrs.get('Size', f'{width},{height}').replace('.', ',').split(',')
        require(len(size) == 2 and all(item.isdigit() for item in size), 'Invalid original ScrollAnim size')
        out_width, out_height = int(size[0]), int(size[1])
        # XML Offset has already positioned the retained control bounds. It is
        # never a texture sample origin; only the retained TextureOffset is.
        offset_x = node.get('textureX', 0)
        offset_y = node.get('textureY', 0)
        require(type(offset_x) is int and type(offset_y) is int,
                'ScrollAnim captured TextureOffset is invalid')
        pixels = scroll_mask_rgba(texture_dds[128:], texture_width, texture_height,
                                  mask_dds[128:], mask_width, mask_height,
                                  out_width, out_height, animation['phase'], offset_x, offset_y)
        cache_key = hashlib.sha256(
            (texture_record['output']['sha256'] + mask_record['output']['sha256'] +
             f"|{animation['clock']:.9g}|{animation['phase']:.9g}|{offset_x},{offset_y}|"
             f"{out_width}x{out_height}|SCROLLANIM_STRETCHED_NEAREST_V1").encode()).hexdigest()
        if cache_key in self.scroll_texture_cache:
            return self.scroll_texture_cache[cache_key]
        output = self.destination / 'textures' / ('scrollmask_' + cache_key[:24] + '.dds')
        require(not output.exists() and not output.is_symlink(), 'Refusing to overwrite a derived ScrollAnim texture')
        output.write_bytes(normalized_header(texture_header, out_width, out_height) + pixels)
        record = {'path': str(output.resolve()), 'sha256': sha256(output), 'width': out_width, 'height': out_height,
                  'texture': texture_record, 'mask': mask_record, 'clock': animation['clock'],
                  'phase': animation['phase'], 'texture_offset': [offset_x, offset_y],
                  'pixel_policy': 'SCROLLANIM_STRETCHED_NEAREST_V1: phase-window-remaining-source-nearest-stretched-to-size; full-mask-nearest-stretched; source-alpha-times-mask-alpha',
                  'retail_sampling_equivalence_verified': False}
        self.derived_textures.append(record)
        value = self.register_texture(output, out_width, out_height)
        self.scroll_texture_cache[cache_key] = value
        return value

    def meter_texture(self, node, attrs):
        percent, plus = node.get('percent'), node.get('percentPlus')
        require(type(percent) in (int, float) and type(plus) in (int, float),
                'Meter lacks captured percent/percentPlus values')
        texture_name = node.get('texture') or attrs.get('Texture')
        require(isinstance(texture_name, str) and texture_name, 'Meter lacks its original texture')
        record = self.assets.resolve(texture_name, self.destination / 'textures')
        source_path = Path(record['output']['path'])
        data = source_path.read_bytes()
        words = header(data)
        rgba32(words)
        width, height = words[4], words[3]
        pixels = meter_arc_rgba(data[128:], width, height, percent, plus)
        cache_key = hashlib.sha256((record['output']['sha256'] + f'|{percent:.9g}|{plus:.9g}').encode()).hexdigest()
        if cache_key in self.scroll_texture_cache:
            return self.scroll_texture_cache[cache_key]
        output = self.destination / 'textures' / ('meterarc_' + cache_key[:24] + '.dds')
        require(not output.exists() and not output.is_symlink(), 'Refusing to overwrite a derived Meter texture')
        output.write_bytes(normalized_header(words, width, height) + pixels)
        derived = {'path': str(output.resolve()), 'sha256': sha256(output), 'width': width, 'height': height,
                   'texture': record, 'percent': percent, 'percentPlus': plus,
                   'pixel_policy': 'original_meter_rgba_clipped_to_clockwise_arc_from_twelve_oclock',
                   'retail_meter_semantics_verified': False}
        self.derived_textures.append(derived)
        value = self.register_texture(output, width, height)
        self.scroll_texture_cache[cache_key] = value
        return value

    def label(self, node, attrs, parent, inherited, clip, stack_y, stack_x=0, *,
              button_bounds=None, captured_metrics=True, button_text_meta=None):
        text = node['text']
        if '[ICON_' in text:
            plain, inline_tints, icon_occurrences = markup(text, self.inline_colors, self.inline_icons)
        else:
            plain, inline_tints = markup(text, self.inline_colors)
            icon_occurrences = {}
        font_id = attrs.get('Font', inherited['Font'])
        font_style = attrs.get('FontStyle', inherited['FontStyle'])
        font = self.font(font_id, font_style)
        inline_glyphs = {}
        for codepoint, icon in icon_occurrences.items():
            if self.context in SCENE_CONTEXTS:
                self.validate_icon_glyph(icon)
            glyph = icon.get('glyph', icon) if type(icon) is dict else None
            require(type(icon) is dict and
                    type(glyph) is dict and
                    all(type(glyph.get(name)) is int for name in ('u', 'v', 'width', 'height', 'advance', 'originx', 'originy')) and
                    isinstance(icon.get('texture'), str) and icon['texture'],
                    'Invalid original inline icon glyph record')
            inline_glyphs[codepoint] = Glyph(codepoint, glyph['u'], glyph['v'], glyph['width'], glyph['height'],
                                             0, glyph['advance'], 0, glyph['originx'], glyph['originy'])
        if self.context in SCENE_CONTEXTS and captured_metrics:
            text_frame = node.get('textFrame')
            metric_source = node.get('fontMetricSource')
            require(type(text_frame) is dict and type(metric_source) is dict,
                    'Retained label lacks its captured textFrame/fontMetricSource')
            font_rows = self.production_font_metrics.get('fonts', {})
            source = font_rows.get(font_id)
            require(type(source) is dict and source.get('sha256') == font.ggxml_sha256 and
                    source.get('ggxmlPath') == str(font.ggxml_path.relative_to(self.game_root)).replace('\\', '/') and
                    metric_source.get('sha256') == font.ggxml_sha256 and
                    metric_source.get('ggxmlPath') == source.get('ggxmlPath'),
                    'Retained label font provenance differs from installed GGXML')
            require(source.get('lineAdvance') == font.line_advance and
                    source.get('baselineOffset') == font.baseline_offset and
                    source.get('spacing') == font.spacing and source.get('fudgeadv') == font.fudgeadv,
                    'Retained captured font metrics differ from original GGXML')
            wrap_width = text_frame.get('wrapWidth')
            lines = text_frame.get('lines')
            require(type(wrap_width) in (int, float) and math.isfinite(wrap_width) and wrap_width >= 0 and
                    type(lines) is list and lines and all(type(line) is dict for line in lines),
                    'Retained label textFrame has invalid wrap width or line list')
            wrapped = wrap_production_text(plain, font, inline_glyphs, wrap_width)
            require(len(wrapped) == len(lines), 'Retained label wrapped line count differs from captured textFrame')
            for index, (actual_line, captured_line) in enumerate(zip(wrapped, lines)):
                require(captured_line.get('text') == actual_line[0] and
                        captured_line.get('advanceWidth') == actual_line[1],
                    f'Retained label line {index} differs from exact GGXML wrap/advance')
            wrapped_plain = '\n'.join(line[0] for line in wrapped)
            layout = layout_text(wrapped_plain, font, inline_glyphs=inline_glyphs)
            effective_line_advance = production_line_advance(font, attrs)
            require(text_frame.get('lineAdvance') == effective_line_advance and
                    text_frame.get('baselineOffset') == font.baseline_offset,
                    'Retained textFrame vertical metrics differ from original GGXML')
            bounds = tuple(text_frame.get(name) for name in ('x', 'y', 'width', 'height'))
            require(len(bounds) == 4 and all(type(v) in (int, float) and math.isfinite(v) for v in bounds) and
                    bounds[0] == node.get('x') and bounds[1] == node.get('y') and
                    bounds[2] == node.get('width') and bounds[3] == node.get('height') and
                    bounds[2] >= 0 and bounds[3] >= 0,
                    'Retained textFrame geometry differs from retained label bounds')
            require(text_frame['height'] >= len(lines) * effective_line_advance,
                    'Retained textFrame height cannot contain its captured GGXML lines')
        else:
            layout = layout_text(plain, font, inline_glyphs=inline_glyphs)
            if button_bounds is not None:
                bounds = centered_button_text_bounds(button_bounds, layout.width, layout.height,
                                                     pair(attrs.get('TextOffset', '0,0')))
            else:
                bounds = anchor(attrs, parent, layout.width, layout.height, stack_y)
        x, y, _, _ = bounds
        color_set = attrs.get('ColorSet', inherited.get('ColorSet'))
        if color_set:
            require(color_set in font.color_sets, 'Unknown original label ColorSet')
            colors, layer_color_policy = font_layer_colors(
                tuple(tuple(c / 255 for c in entry.rgba)
                      for entry in font.color_sets[color_set].layer_colors),
                len(font.layers), font_style=font_style, color_set=color_set)
        elif self.context == 'city-view' and any(name in attrs for name in
                                                  ('ColorLayer0', 'ColorLayer1', 'ColorLayer2')):
            colors = tuple(self.color(attrs.get('ColorLayer' + str(index),
                                                attrs.get('ColorLayer0', 'Beige')))
                           for index in range(len(font.layers)))
            layer_color_policy = 'CITYVIEW_ORIGINAL_COLORLAYER_ATTRIBUTES'
        elif any(name in attrs for name in ('Color0', 'Color1', 'Color2')):
            layer_count = len(font.layers)
            colors = tuple(self.color(attrs.get('Color' + str(index), attrs.get('Color', inherited.get('Color', 'Beige'))))
                           for index in range(layer_count))
            layer_color_policy = 'EXPLICIT_LABEL_COLOR_ATTRIBUTES'
        else:
            colors = (self.color(attrs.get('Color', inherited.get('Color', 'Beige'))),
                      self.color(attrs.get('Color1', inherited.get('Color1', 'Black'))))
            layer_color_policy = 'FRONTEND_DEFAULT_BASE_AND_EFFECT_COLORS'
        require(len(colors) >= len(font.layers), 'Missing font layer color')
        # XML assigns base Color0 and shadow Color1. Candidate compositing draws
        # later effect layers behind the base, retaining their original indices.
        for layer in reversed(font.layers):
            path = self.destination / 'textures' / layer.sheet.path.name
            texture, tw, th = self.register_texture(path, layer.sheet.width, layer.sheet.height)
            for glyph in layout.placements:
                if glyph.codepoint in icon_occurrences:
                    continue
                (u, v, w, h), border = glyph_quad(glyph, font)
                require(u + w <= tw and v + h <= th, 'Glyph outside original atlas')
                if glyph.texture_rect[2] and glyph.texture_rect[3]:
                    color = inline_tints[glyph.text_index] if layer.order == 0 and inline_tints[glyph.text_index] else colors[layer.order]
                    self.paint(node['key'], texture, (u, v, u + w, v + h),
                               (x + glyph.draw_x - border, y + glyph.draw_y - border,
                                x + glyph.draw_x - border + w, y + glyph.draw_y - border + h), clip, color)
        for glyph in layout.placements:
            icon = icon_occurrences.get(glyph.codepoint)
            if icon is None or not glyph.texture_rect[2] or not glyph.texture_rect[3]:
                continue
            texture, tw, th = self.texture(icon['texture'])
            u, v, w, h = glyph.texture_rect
            require(u + w <= tw and v + h <= th, 'Inline icon glyph escapes its original icon font atlas')
            tint = inline_tints[glyph.text_index] if inline_tints[glyph.text_index] else colors[0]
            self.paint(node['key'], texture, (u, v, u + w, v + h),
                       (x + glyph.draw_x, y + glyph.draw_y, x + glyph.draw_x + w, y + glyph.draw_y + h),
                       clip, tint)
        self.labels.append({'key': node['key'], 'text': text, 'font': font_id, 'style': font_style,
                            'plain_text': plain, 'inline_colors_preserved': text != plain,
                            'inline_icons': [{'codepoint': cp, **record} for cp, record in sorted(icon_occurrences.items())],
                            'bounds': bounds, 'glyph_count': len(layout.placements),
                            'text_frame': node.get('textFrame') if self.context in SCENE_CONTEXTS and captured_metrics else None,
                            'font_metric_source': node.get('fontMetricSource') if self.context in SCENE_CONTEXTS and captured_metrics else None,
                            'font_layer_color_policy': layer_color_policy,
                            'font_layer_colors_rgba': [list(color) for color in colors],
                            **(button_text_meta or {}),
                            'retail_font_layer_color_mapping_verified': False,
                            'captured_ggxml_layout_recomputed': self.context in SCENE_CONTEXTS and captured_metrics,
                            'retail_metric_semantics_verified': False,
                            'retail_pixel_equivalence_verified': False})
        return bounds

    def city_view_toggle_text(self, node, attrs, inherited, control_bounds, clip):
        require(self.context == 'city-view' and node.get('kind') in ('CheckBox', 'RadioButton') and
                isinstance(node.get('text'), str) and node['text'],
                'CityView check control lacks its original resolved String')
        text_attrs = dict(attrs)
        text_attrs['Anchor'] = attrs.get('TextAnchor', 'R,C')
        text_attrs['AnchorSide'] = attrs.get('TextAnchorSide', 'O,O')
        text_attrs['Offset'] = attrs.get('TextOffset', '0,0')
        text_attrs.pop('Size', None)
        return self.label(node, text_attrs, control_bounds, inherited, clip, 0,
                          captured_metrics=False,
                          button_text_meta={'text_control': node['kind'],
                                            'text_control_id': node.get('id', ''),
                                            'text_placement_policy': 'original TextAnchor/TextAnchorSide/TextOffset relative to retained checkbox bounds',
                                            'retail_text_alignment_verified': False})

    def leader_button_text(self, node, attrs, inherited, button_bounds, clip):
        """Paint only the five direct String controls in the original LeaderHeadRoot XML."""
        control_id = node.get('id')
        source = self.leader_button_sources.get(control_id)
        require(type(source) is dict and node.get('sourceAttributes') == source and
                source.get('String') == attrs.get('String') and isinstance(node.get('text'), str) and
                node['text'].strip(),
                'LeaderHead GridButton text differs from its original direct XML String')
        if source.get('Style') == 'FrameButton200':
            style = self.styles.get('FrameButton200')
            require(style is not None and style.attrib.get('Size') == '200,32' and
                    style.attrib.get('TextOffset') == '0,-2' and attrs.get('Size') == '200,32' and
                    attrs.get('TextOffset') == '0,-2',
                    'LeaderHead FrameButton200 text geometry differs from original Styles.xml')
        else:
            require(control_id == 'WarButton' and source.get('Size') == '200,32' and
                    source.get('TextOffset') == '0,-2' and attrs.get('Size') == '200,32' and
                    attrs.get('TextOffset') == '0,-2',
                    'LeaderHead WarButton text geometry differs from its original inline XML')
        disabled_raw = attrs.get('Disabled', '0')
        require(disabled_raw in ('0', '1', 'True', 'true'),
                'LeaderHead GridButton has an unsupported disabled state')
        disabled = disabled_raw in ('1', 'True', 'true')
        return self.label(node, attrs, button_bounds, inherited, clip, 0,
                          button_bounds=button_bounds, captured_metrics=False,
                          button_text_meta={'text_control': 'GridButton', 'text_control_id': control_id,
                                            'button_disabled': disabled,
                                            'text_placement_policy': 'retained GridButton bounds center plus original XML TextOffset; retail text alignment unverified',
                                            'disabled_text_color_policy': 'original inherited ColorSet and GGXML layers retained without invented state tint'})

    def city_view_hex_overlay(self, city_view):
        require(type(city_view) is dict and city_view.get('viewingMode') is True and
                city_view.get('retailWorldProjectionVerified') is False and
                type(city_view.get('projection')) is dict,
                'CityView lacks its original view-mode/projection proof boundary')
        projection = city_view['projection']
        require(projection.get('policy') == 'ZEROSIS_2D_CITY_VIEW_V1' and
                projection.get('tileWidth') == 84 and
                projection.get('centerX') == 960 and projection.get('centerY') == 540,
                'CityView projection differs from the selected 1920x1080 world renderer profile')
        highlights = city_view.get('hexHighlights')
        require(type(highlights) is list and len(highlights) <= 10000 and
                city_view.get('hexCoordinatePolicy') == 'ZEROSIS_GRID_TO_AXIAL_ROW_ODD_V1',
                'CityView lacks the captured original highlight list/coordinate policy')
        previous = None
        normalized = []
        for item in highlights:
            require(type(item) is dict and type(item.get('hex')) is dict and
                    type(item.get('color')) is dict,
                    'Malformed original CityView hex highlight')
            hx, hy = item['hex'].get('x'), item['hex'].get('y')
            require(type(hx) is int and type(hy) is int and
                    all(type(item['color'].get(name)) in (int, float) and
                        math.isfinite(item['color'][name]) and 0 <= item['color'][name] <= 1
                        for name in ('x', 'y', 'z', 'w')),
                    'CityView highlight has invalid axial coordinates or retained RGBA color')
            order = (hy, hx)
            require(previous is None or previous < order,
                    'CityView hex highlights are not unique deterministic y/x order')
            previous = order
            center_x, center_y, tile_width, tile_height = city_view_hex_center(hx, hy, projection)
            normalized.append({'hex': {'x': hx, 'y': hy}, 'center': [center_x, center_y],
                               'color': [item['color'][name] for name in ('x', 'y', 'z', 'w')]})
        self.city_view_projection = copy.deepcopy(projection)
        self.city_view_hexes = normalized
        self.city_view_policy = {
            'coordinate_policy': city_view['hexCoordinatePolicy'],
            'projection_policy': projection['policy'],
            'tile_width': projection['tileWidth'],
            'tile_height': projection['tileWidth'] * 1.15470053838,
            'outline_width': 0.7,
            'pixel_policy': 'ZEROSIS_CITYVIEW_D2D_HEX_OUTLINE_RGBA_COVERAGE_V1',
            'retail_world_projection_verified': False,
            'retail_shader_equivalence_verified': False,
            'hex_count': len(normalized),
        }
        if not normalized:
            return
        width, height = 84, math.ceil(84 * 1.15470053838)
        pixels = city_view_hex_outline_rgba(width, height)
        words = [0] * 32
        words[0:8] = [0x20534444, 124, 0x100f, height, width, width * 4, 0, 1]
        words[19:27] = [32, 0x41, 0, 32, 0xff0000, 0xff00, 0xff, 0xff000000]
        words[27] = 0x1000
        cache_key = hashlib.sha256(pixels + repr((width, height, .7, 4)).encode()).hexdigest()
        output = self.destination / 'textures' / ('cityhex_' + cache_key[:24] + '.dds')
        require(not output.exists() and not output.is_symlink(),
                'Refusing to overwrite a derived CityView hex texture')
        candidate_directory(output.parent, self.game_root)
        output.write_bytes(struct.pack('<32I', *words) + pixels)
        derived = {'path': str(output.resolve()), 'sha256': sha256(output), 'width': width, 'height': height,
                   'pixel_policy': self.city_view_policy['pixel_policy'],
                   'outline_width': 0.7, 'supersample_grid': 4,
                   'source_geometry': 'Source/Presentation/WorldViewRenderer.cpp Hex() six point outline',
                   'retail_shader_equivalence_verified': False}
        self.derived_textures.append(derived)
        texture = self.register_texture(output, width, height)
        for item in normalized:
            cx, cy = item['center']
            self.paint(0, texture[0], (0, 0, width, height),
                       (cx - 42, cy - height / 2, cx + 42, cy + height / 2),
                       (0, 0, self.width, self.height), tuple(item['color']))

    def validate_city_view_payload(self, snapshot):
        city_view = snapshot.get('cityView')
        require(type(city_view) is dict and city_view.get('viewingMode') is True and
                city_view.get('retailWorldProjectionVerified') is False and
                type(city_view.get('projection')) is dict,
                'CityView snapshot lacks its native view/projection contract')
        yield_display = city_view.get('yieldDisplay')
        if yield_display is not None:
            require(type(yield_display) is dict and
                    yield_display.get('kind') in ('CityOwned', 'CityWorked', 'CityPurchasable') and
                    all(type(yield_display.get(name)) in (int, float) and math.isfinite(yield_display[name])
                        for name in ('x', 'y')) and yield_display.get('rendererVerified') is False,
                    'CityView yield-display request differs from the retained native contract')
        tutorials = city_view.get('tutorialRequests')
        require(type(tutorials) is list and city_view.get('tutorialExecutionVerified') is False,
                'CityView lacks the retained tutorial request/proof boundary')
        for request in tutorials:
            require(type(request) is dict and isinstance(request.get('kind'), str) and request['kind'] and
                    type(request.get('queued')) is bool and type(request.get('force')) is bool,
                    'CityView has a malformed original tutorial request')
        self.city_view_hex_overlay(city_view)

    def validate_city_view_context_font_defaults(self, snapshot):
        tree = snapshot.get('tree')
        require(type(tree) is dict and tree.get('kind') == 'Context',
                'CityView context font policy has no original Context node')
        defaults = tree.get('contextFontDefaults')
        if self.city_view_layout_variant == 'small':
            expected = self.city_view_context_font_policy
            require(type(defaults) is dict and
                    defaults.get('policy') == expected['policy'] and
                    defaults.get('retailDefaultFontVerified') is False and
                    defaults.get('attributes') == expected['attributes'],
                    'CityView small-layout font defaults differ from the retained candidate policy')
            source = defaults.get('source')
            retained_source = Path(source.get('path', '')).resolve(strict=True) if type(source) is dict else None
            require(type(source) is dict and
                    retained_source.is_file() and retained_source.name == 'CityView.xml' and
                    sha256(retained_source) == expected['source']['sha256'] and
                    source.get('sha256') == expected['source']['sha256'] and
                    retained_source.stat().st_size == expected['source']['bytes'] and
                    ('bytes' not in source or source['bytes'] == expected['source']['bytes']),
                    'CityView small-layout font fallback is not bound to the exact standard Context XML')
            self.city_view_context_font_policy['retained_source'] = dict(source)
            attributes = tree.get('attributes')
            source_attributes = tree.get('sourceAttributes')
            require(type(attributes) is dict and
                    attributes.get('Font') == expected['attributes']['Font'] and
                    attributes.get('FontStyle') == expected['attributes']['FontStyle'] and
                    type(source_attributes) is dict and
                    source_attributes == self.city_view_source_context_attributes and
                    'Font' not in source_attributes and 'FontStyle' not in source_attributes,
                    'CityView small Context did not inherit the candidate without changing source attributes')
        else:
            require(defaults is None,
                    'Default CityView layout unexpectedly carries a small-layout font fallback')

    def node(self, node, parent, inherited, clip, stack_y=0, *, stack_x=0,
             scroll_panel_state=None, decoration=False):
        require(type(node) is dict and node.get('kind') in KINDS and type(node.get('key')) is int,
                'Unsupported retained control schema')
        key, kind = node['key'], node['kind']
        require(0 < key < (1 << 64), 'Invalid retained control key')
        if not decoration:
            require(key not in self.keys, 'Duplicate retained control key')
            self.keys.add(key)
        require(type(node.get('hidden')) is bool and type(node.get('children')) is list and type(node.get('attributes')) is dict,
                'Invalid retained control state')
        if node['hidden']:
            return
        require(kind != 'LuaContext', 'Visible LuaContext has no pixel representation')
        if kind == 'Instance':
            raise ValueError('Instance declarations are templates, not retained controls; expected the source popup instance children')
        attrs = dict(node['attributes'])
        zero_source_extent = False
        world_position = None
        check_default_size = None
        style = None
        if 'Style' in attrs:
            require(attrs['Style'] in self.styles, 'Missing original UI style')
            style = self.styles[attrs['Style']]
            attrs = {**style.attrib, **attrs}
        inherited = {**inherited, **{k: attrs[k] for k in ('Font', 'FontStyle', 'Color', 'Color1', 'ColorSet') if k in attrs}}
        width, height = node['width'], node['height']
        require(all(type(v) in (int, float) and math.isfinite(v) and v >= 0 for v in (width, height)), 'Invalid retained size')
        if self.context == 'city-view' and kind in ('CheckBox', 'RadioButton'):
            require('Size' not in attrs and 'Size' not in node.get('sourceAttributes', {}),
                    'CityView atlas-derived check size is only valid when the original XML omits Size')
            check_default_size = node.get('defaultSize')
            require(type(check_default_size) is dict and
                    check_default_size.get('policy') == 'CIV5_CHECK_ATLAS_SQUARE_FRAME_CANDIDATE_V1' and
                    check_default_size.get('retailWidgetGeometryVerified') is False and
                    check_default_size.get('width') == 32 and check_default_size.get('height') == 32 and
                    check_default_size.get('frameCount') == 4 and
                    width == check_default_size['width'] and height == check_default_size['height'],
                    'CityView check control lacks its captured source-backed atlas-frame candidate size')
            button_texture_name = attrs.get('ButtonTexture')
            require(isinstance(button_texture_name, str) and button_texture_name,
                    'Original CityView check control lacks its original ButtonTexture')
            source_record = self.assets.resolve(button_texture_name, self.destination / 'textures')
            recorded_texture = check_default_size.get('texture')
            recorded_conversion = recorded_texture.get('conversion', {}) if type(recorded_texture) is dict else {}
            source_conversion = source_record.get('conversion', {})
            require(type(recorded_texture) is dict and
                    str(recorded_texture.get('requested_name', '')).replace('\\', '/').rsplit('/', 1)[-1].casefold() ==
                    button_texture_name.replace('\\', '/').rsplit('/', 1)[-1].casefold() and
                    recorded_texture.get('source') == source_record.get('source') and
                    recorded_texture.get('index_source') == source_record.get('index_source') and
                    recorded_texture.get('output', {}).get('sha256') == source_record.get('output', {}).get('sha256') and
                    recorded_conversion.get('width') == source_conversion.get('width') and
                    recorded_conversion.get('height') == source_conversion.get('height') and
                    source_record.get('conversion', {}).get('width') == 32 and
                    source_record.get('conversion', {}).get('height') == 128,
                    'CityView check default size is not bound to its exact decoded 32x128 source atlas')
        if self.context in SCENE_CONTEXTS:
            if kind == 'Context':
                require((width, height) == (self.width, self.height), 'Retained viewport mismatch')
                bounds = (0, 0, width, height)
            elif kind in ('Label', 'TextButton'):
                bounds = self.label(node, attrs, parent, inherited, clip, stack_y, stack_x)
            else:
                if not decoration:
                    require(type(node.get('x')) in (int, float) and type(node.get('y')) in (int, float),
                            'Production control lacks captured retained coordinates: ' + kind)
                if decoration and kind in ('ShowOnMouseOver', 'Container') and width == 0 and height == 0:
                    bounds = parent
                elif decoration:
                    bounds = anchor(attrs, parent, width, height, stack_y)
                elif kind == 'ShowOnMouseOver' and width == 0 and height == 0:
                    bounds = parent
                elif kind in ('Stack', 'Box', 'WorldAnchor') and width == 0 and height == 0:
                    # Zero-area production containers still recurse through captured
                    # descendants; no child is hidden or omitted by this allowance.
                    bounds = (node['x'], node['y'], 0, 0)
                    if kind == 'WorldAnchor':
                        position = node.get('worldPosition')
                        require(type(position) is dict and
                                all(type(position.get(name)) in (int, float) and math.isfinite(position[name])
                                    for name in ('x', 'y', 'z')),
                                'CityView WorldAnchor lacks its original finite world position')
                        world_position = dict(position)
                elif (self.context == 'research' and kind in ('Image', 'Meter') and
                      node.get('id') in ('ProgressMeter', 'ProgressMeterInternal') and
                      width == 0 and height == 0):
                    source_attrs = node.get('sourceAttributes')
                    children = node.get('children')
                    allowed_children = (not children if node.get('id') == 'ProgressMeterInternal' else
                                        type(children) is list and len(children) == 1 and
                                        children[0].get('kind') == 'Meter' and
                                        children[0].get('id') == 'ProgressMeterInternal' and
                                        children[0].get('width') == 0 and children[0].get('height') == 0)
                    require(attrs.get('Size') in ('0.0', '0,0') and
                            type(source_attrs) is dict and source_attrs.get('Size') in ('0.0', '0,0') and
                            allowed_children,
                            'Zero-area Research progress control differs from its explicit original XML geometry')
                    # The stock TechPopup Lua can activate these progress controls,
                    # while the captured XML geometry remains Size=0.0. Preserve
                    # their state with no raster area in this frontend model;
                    # retail intrinsic-size and alpha semantics remain unverified.
                    zero_source_extent = True
                    bounds = (node['x'], node['y'], 0, 0)
                else:
                    require(width > 0 and height > 0,
                            'Production control lacks resolved style dimensions: ' + kind + '/' + node.get('id', ''))
                    bounds = (node['x'], node['y'], width, height)
            if kind == 'ShowOnMouseOver':
                hovered = node.get('hovered')
                require(type(hovered) is bool, 'ShowOnMouseOver lacks captured hovered state')
                if not hovered:
                    self.geometry.append({'key': key, 'kind': kind, 'id': node.get('id', ''), 'bounds': bounds,
                                          'clip': clip, 'style_decoration': decoration, 'hovered': False,
                                          'children_drawn': False})
                    return
        else:
            if kind == 'Context':
                require((width, height) == (self.width, self.height), 'Retained viewport mismatch')
                bounds = (0, 0, width, height)
            elif kind in ('Label', 'TextButton'):
                bounds = self.label(node, attrs, parent, inherited, clip, stack_y, stack_x)
            elif kind in ('Container', 'ShowOnMouseOver'):
                bounds = anchor(attrs, parent, width, height, stack_y)
            else:
                if style is not None or decoration:
                    sizes = attrs.get('Size', f'{width},{height}').replace('.', ',').split(',')
                    require(len(sizes) == 2, 'Unsupported style size')
                    width, height = [full if raw == 'Full' else float(raw)
                                     for raw, full in zip(sizes, (self.width, self.height))]
                if kind == 'ScrollBar':
                    require('Length' in attrs and attrs.get('Vertical') == '1', 'Unsupported scrollbar')
                    height = int(attrs['Length'])
                bounds = anchor(attrs, parent, width, height, stack_y)
        require(all(math.isfinite(v) and abs(v) < 1e6 for v in bounds), 'Unbounded retained control geometry')
        if self.context in ('research', 'research-tree', 'city-capture', 'diplomacy', 'city-view') and kind in (
                'Button', 'GridButton', 'TextButton', 'UpButton', 'DownButton'):
            require(node.get('buttonState') in ('normal', 'hover', 'pressed', 'disabled'),
                    'Research button lacks its captured retained visual state: ' + node.get('id', ''))
        self.geometry.append({'key': key, 'kind': kind, 'id': node.get('id', ''), 'bounds': bounds,
                              'clip': clip, 'style_decoration': decoration})
        if kind == 'WorldAnchor':
            if world_position is None:
                world_position = node.get('worldPosition')
                require(type(world_position) is dict and
                        all(type(world_position.get(name)) in (int, float) and math.isfinite(world_position[name])
                            for name in ('x', 'y', 'z')),
                        'CityView WorldAnchor lacks its original finite world position')
            self.geometry[-1]['world_position'] = dict(world_position)
            self.geometry[-1]['world_position_policy'] = 'captured native world anchor; screen XYWH retained as supplied'
        if zero_source_extent:
            pass
        elif kind == 'Image':
            if 'color' in node:
                c = node['color']
                color = tuple(c[channel] for channel in ('x', 'y', 'z', 'w'))
            else:
                color = self.color(attrs['Color']) if 'Color' in node['attributes'] else (1, 1, 1, 1)
            texture_name = node['texture'].replace('\\', '/').rsplit('/', 1)[-1].casefold()
            stretch_tech_pipe = (self.context == 'research-tree' and node.get('id') == 'TechPipeIcon' and
                                 texture_name in ('techbranchh.dds', 'techbranchv.dds'))
            tech_branch_cell = (self.context == 'research-tree' and node.get('id') == 'TechPipeIcon' and
                                texture_name == 'techbranches.dds')
            source_extent = None
            if tech_branch_cell:
                # TechBranches uses a 36-pixel lattice of 32x32 cells in its
                # 105x105 decoded atlas. Lua changes the cell offset, while
                # the XML's 32x42 control size remains the draw destination.
                require(node['textureX'] % 36 == 0 and node['textureY'] % 36 == 0 and
                        node['textureX'] + 32 <= 105 and node['textureY'] + 32 <= 105 and
                        bounds[2:] == (32, 42),
                        'TechBranches cell does not match the retained source lattice/destination')
                source_extent = (32, 32)
            image_policy = self.image(key, node['texture'], node['textureX'], node['textureY'],
                                      bounds, clip, color,
                                      stretch_full_texture=stretch_tech_pipe,
                                      source_extent=source_extent)
            if stretch_tech_pipe or tech_branch_cell:
                self.geometry[-1]['original_texture_source_policy'] = image_policy
                self.geometry[-1]['retail_texture_stretch_verified'] = False
                if tech_branch_cell:
                    self.geometry[-1]['original_texture_source_extent'] = [32, 32]
                    self.geometry[-1]['texture_atlas_lattice'] = 36
        elif kind == 'Box' and 'Color' in attrs:
            self.paint(key, SOLID, (0, 0, 0, 0), rect(bounds), clip, self.color(attrs['Color']))
        elif kind in ('Grid', 'GridButton'):
            if kind == 'GridButton':
                # Civ V GridButton stores its nine-slice descriptor as an
                # inline retained GridData child. It is draw data, not a
                # separately positioned control; use its original source
                # rectangles over the GridButton's retained bounds.
                grid_data_nodes = [child for child in node['children']
                                   if child.get('kind') == 'GridData']
                if style is not None:
                    styled_grid_data = style.find('GridData')
                    require(styled_grid_data is not None and
                            styled_grid_data.attrib.get('Style') in self.styles,
                            'Unsupported styled original button grid')
                    grid_style = self.styles[styled_grid_data.attrib['Style']]
                    require(not grid_data_nodes, 'GridButton has duplicate inline and styled GridData')
                else:
                    require(len(grid_data_nodes) == 1,
                            'GridButton lacks exactly one original inline GridData descriptor')
                    descriptor = grid_data_nodes[0]
                    grid_attrs = descriptor.get('attributes')
                    require(type(grid_attrs) is dict and descriptor.get('hidden') is False and
                            type(descriptor.get('children')) is list and not descriptor['children'] and
                            descriptor.get('width') == 0 and descriptor.get('height') == 0,
                            'Invalid retained inline GridData descriptor')
                    required_grid_attrs = {'Texture'} | {
                        f'{part}{field}' for part in ('UL', 'UC', 'UR', 'L', 'C', 'R', 'LL', 'LC', 'LR')
                        for field in ('Size', 'TexStart')}
                    require(required_grid_attrs <= grid_attrs.keys(),
                            'Inline GridData lacks original nine-slice texture regions')
                    grid_style = ET.Element('GridData', attrib=grid_attrs)
                    require('Style' in grid_attrs and grid_attrs['Style'] in self.styles,
                            'Inline GridData references a missing original style')
                self.grid(key, grid_style, bounds, clip)
            else:
                require(style is not None, 'Unstyled grid unsupported')
                self.grid(key, style, bounds, clip)
        elif kind == 'ScrollBar':
            require(style is not None, 'ScrollBar lacks its original style')
            shuttle = style.find('Shuttle')
            require(shuttle is not None and shuttle.attrib.get('Style') in self.styles,
                    'ScrollBar lacks its original shuttle style')
            shuttle_style = self.styles[shuttle.attrib['Style']]
            if self.context == 'research-tree':
                require(style.tag == 'ScrollBar' and attrs.get('Vertical') == '0',
                        'TechTree requires the original horizontal ScrollBar style')
                self.horizontal_strip(key, style, rect(bounds), clip)
                scroll = node.get('scrollX')
                content_width = node.get('contentWidth')
                viewport_width = node.get('viewportWidth')
                require(type(scroll) in (int, float) and math.isfinite(scroll) and
                        type(content_width) in (int, float) and math.isfinite(content_width) and
                        type(viewport_width) in (int, float) and math.isfinite(viewport_width) and
                        content_width >= 0 and viewport_width > 0,
                        'TechTree ScrollBar lacks its retained horizontal range')
                maximum_scroll = max(0.0, content_width - viewport_width)
                captured_maximum = node.get('maximumScroll')
                require(type(captured_maximum) in (int, float) and math.isfinite(captured_maximum) and
                        abs(captured_maximum - maximum_scroll) <= 1e-6 and
                        0 <= scroll <= maximum_scroll and
                        type(self.research_tree_scroll_targets) is dict and
                        len(self.research_tree_scroll_targets) == 1,
                        'TechTree ScrollBar maximum/range differs from retained TechTreeScrollPanel')
                panel_state = next(iter(self.research_tree_scroll_targets.values()))
                require(abs(scroll - panel_state['scrollX']) <= 1e-6 and
                        abs(content_width - panel_state['contentWidth']) <= 1e-6 and
                        abs(viewport_width - panel_state['viewportWidth']) <= 1e-6 and
                        abs(maximum_scroll - panel_state['maximumScroll']) <= 1e-6,
                        'TechTree ScrollBar range differs from captured ScrollPanel state')
                minimum_thumb = float(shuttle.attrib['Size'].replace('.', ',').split(',')[0])
                captured_shuttle = node.get('shuttleBounds')
                require(type(captured_shuttle) is dict,
                        'TechTree ScrollBar lacks its retained frontend-model shuttle bounds')
                require(node.get('shuttlePolicy') == 'ZEROSIS_RETAINED_VIEWPORT_PROPORTIONAL_V1' and
                        node.get('retailScrollbarGeometryVerified') is False,
                        'TechTree ScrollBar frontend model/proof boundary is missing or overstated')
                modeled_shuttle = research_tree_scrollbar_thumb_bounds(
                    bounds, scroll, content_width, viewport_width, minimum_thumb)
                captured = tuple(captured_shuttle.get(name) for name in ('x', 'y', 'width', 'height'))
                require(all(type(value) in (int, float) and math.isfinite(value) for value in captured) and
                        all(abs(a - b) <= 1e-6 for a, b in zip(rect(captured), modeled_shuttle)),
                        'TechTree ScrollBar shuttle differs from captured style/content frontend model')
                self.horizontal_strip(key, shuttle_style, rect(captured), clip)
            else:
                require(style.tag == 'VertSlider', 'Unsupported scrollbar style')
                self.vertical_strip(key, style, rect(bounds), clip)
                scroll = node.get('scrollY')
                require(type(scroll) in (int, float) and math.isfinite(scroll) and scroll >= 0,
                        'ScrollBar lacks captured scrollY state')
                content_height = node.get('contentHeight')
                require(type(content_height) in (int, float) and math.isfinite(content_height) and
                        content_height >= 0, 'ScrollBar lacks a valid retained content extent')
                minimum_thumb = float(shuttle.attrib['Size'].replace('.', ',').split(',')[1])
                if self.context == 'research':
                    captured_shuttle = node.get('shuttleBounds')
                    require(type(captured_shuttle) is dict,
                            'Research ScrollBar lacks its retained frontend-model shuttle bounds')
                    require(node.get('shuttlePolicy') == 'ZEROSIS_RETAINED_VIEWPORT_PROPORTIONAL_V1' and
                            node.get('retailScrollbarGeometryVerified') is False,
                            'Research ScrollBar frontend model/proof boundary is missing or overstated')
                    modeled_shuttle = research_scrollbar_thumb_bounds(bounds, scroll, content_height, minimum_thumb)
                    captured = tuple(captured_shuttle.get(name) for name in ('x', 'y', 'width', 'height'))
                    require(all(type(value) in (int, float) and math.isfinite(value) for value in captured) and
                            all(abs(a - b) <= 1e-6 for a, b in zip(rect(captured), modeled_shuttle)),
                            'Research ScrollBar shuttle differs from captured style/content frontend model')
                    shuttle_bounds = rect(captured)
                elif self.context == 'city-view':
                    require(type(scroll_panel_state) is dict and
                            scroll_panel_state.get('kind') == 'ScrollPanel' and
                            scroll_panel_state.get('attributes', {}).get('Vertical') == '1',
                            'CityView ScrollBar has no retained vertical ScrollPanel owner')
                    parent_key = scroll_panel_state.get('key')
                    parent_target = self.production_scroll_targets_by_key.get(parent_key)
                    require(type(parent_target) is dict and parent_target.get('key') == parent_key and
                            parent_target.get('id') == scroll_panel_state.get('id', '') and
                            parent_target.get('visible') is True and parent_target.get('disabled') is False,
                            'CityView ScrollBar has no matching visible original ScrollPanel target')
                    panel_bounds = tuple(scroll_panel_state.get(name) for name in ('x', 'y', 'width', 'height'))
                    target_bounds = xywh_dict(parent_target.get('bounds'), 'CityView ScrollPanel bounds')
                    require(all(type(value) in (int, float) and math.isfinite(value) for value in panel_bounds) and
                            all(abs(a - b) <= 1e-6 for a, b in zip(target_bounds, rect(panel_bounds))),
                            'CityView ScrollBar owner viewport differs from retained target bounds')
                    scroll = scroll_panel_state.get('scrollY')
                    content_height = scroll_panel_state.get('contentHeight')
                    viewport_height = panel_bounds[3]
                    target_range = tuple(parent_target.get(name) for name in
                                         ('scrollY', 'contentHeight', 'viewportHeight'))
                    require(type(scroll) in (int, float) and math.isfinite(scroll) and
                            type(content_height) in (int, float) and math.isfinite(content_height) and
                            all(type(value) in (int, float) and math.isfinite(value) for value in target_range) and
                            abs(target_range[0] - scroll) <= 1e-6 and
                            abs(target_range[1] - content_height) <= 1e-6 and
                            abs(target_range[2] - viewport_height) <= 1e-6 and
                            0 <= scroll <= max(0.0, content_height - viewport_height),
                            'CityView ScrollBar range differs from its captured ScrollPanel target')
                    shuttle_bounds = production_scrollbar_thumb_bounds(
                        bounds, scroll, content_height, viewport_height, minimum_thumb)
                    self.geometry[-1]['scrollbar_geometry_policy'] = 'ZEROSIS_CITYVIEW_VERTICAL_THUMB_FROM_RETAINED_RANGE_V1'
                    self.geometry[-1]['retail_scrollbar_geometry_verified'] = False
                elif self.context == 'production':
                    require(type(scroll_panel_state) is dict and
                            scroll_panel_state.get('kind') == 'ScrollPanel' and
                            scroll_panel_state.get('attributes', {}).get('Vertical') == '1',
                            'Production ScrollBar has no retained vertical ScrollPanel owner')
                    parent_key = scroll_panel_state.get('key')
                    parent_target = self.production_scroll_targets_by_key.get(parent_key)
                    require(type(parent_target) is dict and parent_target.get('key') == parent_key and
                            parent_target.get('id') == scroll_panel_state.get('id', '') and
                            parent_target.get('visible') is True and parent_target.get('disabled') is False,
                            'Production ScrollBar has no matching visible ScrollPanel target')
                    panel_bounds = tuple(scroll_panel_state.get(name) for name in ('x', 'y', 'width', 'height'))
                    target_bounds = xywh_dict(parent_target.get('bounds'), 'Production ScrollPanel bounds')
                    require(all(type(value) in (int, float) and math.isfinite(value) for value in panel_bounds) and
                            all(abs(a - b) <= 1e-6 for a, b in zip(target_bounds, rect(panel_bounds))),
                            'Production ScrollBar owner viewport bounds differ from scrollTargets')
                    viewport_height = panel_bounds[3]
                    panel_scroll = scroll_panel_state.get('scrollY')
                    panel_content = scroll_panel_state.get('contentHeight')
                    target_scroll = parent_target.get('scrollY')
                    target_content = parent_target.get('contentHeight')
                    target_viewport = parent_target.get('viewportHeight')
                    target_maximum = parent_target.get('maximumScroll')
                    scroll = node.get('scrollY')
                    content_height = node.get('contentHeight')
                    numeric = (panel_scroll, panel_content, target_scroll, target_content,
                               target_viewport, target_maximum, scroll, content_height)
                    require(all(type(value) in (int, float) and math.isfinite(value) for value in numeric) and
                            panel_content >= 0 and content_height >= 0 and
                            abs(panel_scroll - target_scroll) <= 1e-6 and
                            abs(panel_content - target_content) <= 1e-6 and
                            abs(viewport_height - target_viewport) <= 1e-6 and
                            abs(scroll - panel_scroll) <= 1e-6 and abs(content_height - panel_content) <= 1e-6,
                            'Production ScrollBar content/offset differs from its retained ScrollPanel')
                    maximum_scroll = max(0.0, content_height - viewport_height)
                    require(abs(target_maximum - maximum_scroll) <= 1e-6 and
                            0 <= scroll <= maximum_scroll,
                            'Production ScrollBar maximum/range differs from scrollTargets')
                    shuttle_bounds = production_scrollbar_thumb_bounds(
                        bounds, scroll, content_height, viewport_height, minimum_thumb)
                else:
                    require(content_height >= bounds[3] and 0 <= scroll <= content_height - bounds[3],
                            'ScrollBar lacks a valid retained viewport/content/offset range')
                    shuttle_bounds = scrollbar_thumb_bounds(bounds, scroll, content_height, minimum_thumb)
                self.vertical_strip(key, shuttle_style, shuttle_bounds, clip)
        elif kind in ('Button', 'UpButton', 'DownButton'):
            button_state = node.get('buttonState')
            require(button_state in ('normal', 'hover', 'pressed', 'disabled'),
                    kind + ' lacks captured buttonState')
            texture_name = node.get('texture') or attrs.get('Texture')
            if texture_name:
                texture, tw, th = self.texture(texture_name)
                u, v = node.get('textureX', 0), node.get('textureY', 0)
                increment = pair(attrs.get('StateOffsetIncrement', '0,0'))
                state_index = {'normal': 0, 'hover': 1, 'pressed': 2, 'disabled': 3}[button_state]
                u += increment[0] * state_index
                v += increment[1] * state_index
                source = button_source_rect(u, v, width, height, tw, th)
                self.paint(key, texture, source, rect(bounds), clip)
        elif kind in ('CheckBox', 'RadioButton'):
            require(self.context == 'city-view' and type(node.get('checked')) is bool and
                    type(node.get('disabled')) is bool and
                    node.get('buttonState') in ('normal', 'hover', 'pressed', 'disabled'),
                    'CityView check control lacks its original checked/disabled/button state')
            button_texture = node.get('texture') or attrs.get('ButtonTexture')
            require(isinstance(button_texture, str) and button_texture,
                    'Original CityView check control lacks its original ButtonTexture')
            texture, tw, th = self.texture(button_texture)
            u, v = node.get('textureX', 0), node.get('textureY', 0)
            state_index = {'normal': 0, 'hover': 1, 'pressed': 2, 'disabled': 3}[node['buttonState']]
            frame_height = check_default_size['height']
            require(state_index < check_default_size['frameCount'] and
                    v + (state_index + 1) * frame_height <= th,
                    'CityView check button-state frame escapes its inspected original atlas')
            v += state_index * frame_height
            source = button_source_rect(u, v, width, height, tw, th)
            self.paint(key, texture, source, rect(bounds), clip)
            check_texture = attrs.get('CheckTexture')
            if node['checked'] and check_texture:
                check, cw, ch = self.texture(check_texture)
                check_source = button_source_rect(node.get('checkTextureX', 0),
                                                  node.get('checkTextureY', 0),
                                                  width, height, cw, ch)
                self.paint(key, check, check_source, rect(bounds), clip)
            self.geometry[-1]['checked'] = node['checked']
            self.geometry[-1]['disabled'] = node['disabled']
            self.geometry[-1]['checked_art_policy'] = ('original ButtonTexture plus CheckTexture at retained checked state'
                                                        if check_texture else
                                                        'original ButtonTexture at retained state; source widget atlas state mapping unresolved')
            self.geometry[-1]['retail_check_art_verified'] = False
            self.geometry[-1]['check_atlas_frame_policy'] = 'original Button state offset applied to inspected four-frame vertical atlas candidate; retail widget ordering unverified'
        elif kind == 'TextureBar':
            percent = node.get('percent')
            require(type(percent) in (int, float) and math.isfinite(percent) and 0 <= percent <= 1,
                    'TextureBar lacks a captured normalized percent')
            direction = attrs.get('Direction')
            require(direction in ('Up', 'Down', 'Left', 'Right'), 'Unsupported original TextureBar direction')
            texture, tw, th = self.texture(node.get('texture') or attrs['Texture'])
            source, target = texture_bar_regions(bounds, direction, percent, tw, th)
            if percent > 0:
                self.paint(key, texture, source, target, clip)
        elif kind == 'AlphaAnim':
            animation = node.get('animation')
            require(type(animation) is dict and animation.get('clock') == self.snapshot_clock and
                    type(animation.get('alpha')) in (int, float) and math.isfinite(animation['alpha']) and
                    animation['alpha'] >= 0, 'AlphaAnim lacks captured value at the selected presentation clock')
            texture_name = node.get('texture') or attrs.get('Texture')
            if texture_name:
                texture, tw, th = self.texture(texture_name)
                u, v = node.get('textureX', 0), node.get('textureY', 0)
                self.paint(key, texture, (u, v, u + width, v + height), rect(bounds), clip,
                           (1, 1, 1, min(1, animation['alpha'])))
            else:
                require(node.get('children'), 'AlphaAnim has neither original texture nor children')
        elif kind == 'FlipAnim':
            animation = node.get('animation')
            require(type(animation) is dict and animation.get('clock') == self.snapshot_clock and
                    type(animation.get('frame')) is int and animation.get('retailTimingVerified') is False,
                    'FlipAnim lacks its captured source-timeline frame')
            frame_count = int(attrs.get('FrameCount', '0'))
            source_pause = float(attrs.get('Pause', '0'))
            end_pause = float(attrs.get('EndPause', abs(source_pause)))
            speed = float(attrs.get('Speed', '0'))
            require(math.isfinite(source_pause) and math.isfinite(end_pause) and end_pause >= 0 and
                    speed > 0 and math.isfinite(speed) and frame_count > 0 and
                    animation.get('timingPolicy') == 'CIV5_FLIP_NEGATIVE_PAUSE_END_HOLD_CANDIDATE_V1' and
                    animation.get('sourcePause') == source_pause and animation.get('endPause') == end_pause,
                    'FlipAnim lacks its explicit original signed-Pause interpretation')
            expected_frame = min(frame_count - 1,
                                 math.floor((self.snapshot_clock % (frame_count / speed + end_pause)) * speed))
            require(animation['frame'] == expected_frame, 'FlipAnim frame differs from its recorded candidate clock')
            columns = int(attrs.get('Columns', '0'))
            step_x, step_y = pair(attrs.get('StepSize', '0,0'))
            require(frame_count > 0 and columns > 0 and columns <= frame_count and
                    0 <= animation['frame'] < frame_count and width > 0 and height > 0,
                    'FlipAnim frame differs from its original XML frame grid')
            frame = animation['frame']
            u = node.get('textureX', 0) + (frame % columns) * step_x
            v = node.get('textureY', 0) + (frame // columns) * step_y
            texture, tw, th = self.texture(node.get('texture') or attrs['Texture'])
            require(u >= 0 and v >= 0 and u + width <= tw and v + height <= th,
                    'Original FlipAnim frame escapes its atlas')
            self.paint(key, texture, (u, v, u + width, v + height), rect(bounds), clip)
            self.geometry[-1]['animation_policy'] = 'captured original FlipAnim frame at selected frontend clock'
            self.geometry[-1]['source_pause'] = source_pause
            self.geometry[-1]['end_pause'] = end_pause
            self.geometry[-1]['timing_policy'] = animation['timingPolicy']
            self.geometry[-1]['retail_timing_verified'] = False
        elif kind == 'ScrollAnim':
            texture, tw, th = self.scroll_animation_texture(node, attrs, width, height)
            self.paint(key, texture, (0, 0, tw, th), rect(bounds), clip)
        elif kind == 'Meter':
            texture, tw, th = self.meter_texture(node, attrs)
            self.paint(key, texture, (0, 0, tw, th), rect(bounds), clip)
        if style is not None and kind == 'Box':
            if self.context in ('city-capture', 'city-view'):
                self.render_style_children(style, key, bounds, inherited, clip)
            else:
                for child in style:
                    require(child.tag == 'Box', 'Unsupported style child')
                    synthetic = {'key': key, 'kind': child.tag, 'attributes': child.attrib,
                                 'width': 0, 'height': 0, 'hidden': False, 'children': [], 'id': '', 'text': ''}
                    self.node(synthetic, bounds, inherited, clip, decoration=True)
        if self.context in ('city-capture', 'city-view') and kind == 'GridButton' and style is not None and node.get('buttonState') == 'hover':
            hover_style = style.find('ShowOnMouseOver')
            if hover_style is not None:
                self.render_style_children(hover_style, key, bounds, inherited, clip, hovered=True)
        child_clip = intersect(clip, rect(bounds)) if kind == 'ScrollPanel' else clip
        scroll_y = 0
        if kind == 'ScrollPanel':
            if self.context == 'research-tree':
                content_width = node.get('contentWidth')
                scroll_x = node.get('scrollX')
                scroll_y = node.get('scrollY')
                maximum_scroll = max(0.0, content_width - bounds[2]) if type(content_width) in (int, float) else 0
                require(attrs.get('Vertical') == '0' and type(scroll_x) in (int, float) and
                        math.isfinite(scroll_x) and type(scroll_y) in (int, float) and
                        math.isfinite(scroll_y) and scroll_y == 0,
                        'TechTree ScrollPanel lacks captured horizontal-only scroll state')
                require(type(content_width) in (int, float) and math.isfinite(content_width) and
                        content_width >= 0 and 0 <= scroll_x <= maximum_scroll,
                        'TechTree ScrollPanel offset/content range is invalid')
            else:
                content_height = node.get('contentHeight')
                scroll_x = node.get('scrollX')
                scroll_y = node.get('scrollY')
                maximum_scroll = scroll_extent(bounds, content_height) if content_height is not None else 0
                require(type(scroll_x) in (int, float) and math.isfinite(scroll_x) and scroll_x == 0,
                        'Vertical popup ScrollPanel lacks captured zero scrollX')
                if content_height is not None and maximum_scroll > 0:
                    require(type(scroll_y) in (int, float) and math.isfinite(scroll_y) and
                            0 <= scroll_y <= maximum_scroll, 'ScrollPanel lacks captured scrollY state')
        offset = 0
        child_scroll_panel_state = scroll_panel_state
        if self.context in ('production', 'city-view') and kind == 'ScrollPanel':
            child_scroll_panel_state = node
        for child in node['children']:
            if child.get('kind') == 'GridData':
                require(kind == 'GridButton',
                        'Original GridData is only supported as a GridButton draw descriptor')
                continue
            is_scrollbar = child['kind'] == 'ScrollBar'
            direction = attrs.get('StackGrowth', 'B') if kind == 'Stack' else None
            stack_y = offset if self.context == 'ranking' and direction in ('B', 'Bottom', 'T', 'Top') else 0
            stack_x = offset if self.context == 'ranking' and direction in ('L', 'Left', 'R', 'Right') else 0
            # Host snapshot x/y already includes the retained ScrollPanel's
            # scroll translation. Only the legacy ranking packet synthesizes
            # its own stack offsets here.
            if kind == 'ScrollPanel' and self.context == 'ranking' and not is_scrollbar:
                stack_y -= scroll_y or 0
            self.node(child, bounds, inherited, clip if is_scrollbar else child_clip,
                      stack_y, stack_x=stack_x, scroll_panel_state=child_scroll_panel_state)
            if kind == 'Stack' and not child['hidden']:
                offset += (child['width'] if direction in ('L', 'Left', 'R', 'Right') else child['height']) + int(attrs.get('Padding', '0'))
        if (self.context == 'diplomacy' and kind == 'GridButton' and
                isinstance(node.get('text'), str) and node['text']):
            self.leader_button_text(node, attrs, inherited, bounds, clip)
        if (self.context == 'city-view' and kind in ('CheckBox', 'RadioButton') and
                attrs.get('String') and isinstance(node.get('text'), str) and node['text']):
            self.city_view_toggle_text(node, attrs, inherited, bounds, clip)

    def compile(self, snapshot, *, closed=False):
        require(type(snapshot) is dict and type(closed) is bool, 'Invalid popup scene compilation request')
        if closed:
            require(snapshot.get('active') is False and type(snapshot.get('timerSemaphore')) is int and
                    snapshot['timerSemaphore'] == 0, 'Closed popup still has an active context or timer')
            lifecycle = snapshot.get('lifecycle')
            require(type(lifecycle) is list and all(type(value) is str for value in lifecycle),
                    'Closed popup lacks its official completed lifecycle')
            if self.context in SCENE_CONTEXTS:
                if self.context == 'production':
                    require(snapshot.get('contextName') == 'ProductionPopup' and
                            snapshot.get('popupKind') == 'Production' and
                            lifecycle == ['queued', 'shown:16', 'processed:16',
                                          'context-hidden:ProductionPopup'],
                            'ProductionPopup did not complete its official lifecycle')
                elif self.context == 'research':
                    require(snapshot.get('contextName') == 'TechPopup' and snapshot.get('popupKind') == 'Research' and
                            len(lifecycle) == 4 and lifecycle[0] == 'queued' and
                            lifecycle[1] == f'shown:{RESEARCH_POPUP_ENUM_VALUE}' and
                            lifecycle[2:] == ['context-hidden:TechPopup',
                                              f'processed:{RESEARCH_POPUP_ENUM_VALUE}'],
                            'TechPopup did not complete its context-hidden lifecycle for BUTTONPOPUP_CHOOSETECH (11)')
                elif self.context == 'city-capture':
                    require(snapshot.get('contextName') == 'GenericPopup' and
                            snapshot.get('popupKind') == 'CityCapture' and
                            len(lifecycle) >= 4 and lifecycle[0] == 'queued' and lifecycle[-1] == 'closed',
                            'GenericPopup CityCapture did not complete its closed lifecycle')
                elif self.context == 'diplomacy':
                    require(snapshot.get('contextName') == 'diplomacy' and
                            snapshot.get('popupKind') == 'LeaderHead' and
                            lifecycle == ['queued', 'closed'],
                            'LeaderHead did not complete its original return lifecycle')
                elif self.context == 'city-view':
                    require(snapshot.get('contextName') == 'CityView' and
                            snapshot.get('popupKind') == 'CityView' and
                            lifecycle == ['queued', 'context-hidden:CityView'],
                            'CityView did not complete its original CityView close lifecycle')
                else:
                    require(snapshot.get('contextName') == 'TechTree' and snapshot.get('popupKind') == 'ResearchTree' and
                            lifecycle == ['queued', f'shown:{RESEARCH_TREE_POPUP_ENUM_VALUE}', 'closed',
                                          f'processed:{RESEARCH_TREE_POPUP_ENUM_VALUE}'],
                            'TechTree did not complete the original BUTTONPOPUP_TECH_TREE lifecycle (67)')
                require(snapshot.get('inputTargets') == [],
                        'Closed popup still exposes registered input targets')
                require(snapshot.get('scrollTargets') == [],
                        'Closed popup still exposes scroll targets')
            else:
                require(len(lifecycle) >= 4 and lifecycle[0] == 'queued' and lifecycle[-1] == 'closed',
                        'Closed popup lacks its official completed lifecycle')
            root = snapshot.get('tree')
            require(type(root) is dict and root.get('kind') == 'Context' and
                    (root.get('width'), root.get('height')) == (self.width, self.height),
                    'Closed popup lacks its original viewport')
            require(not any((self.textures, self.sprites, self.hits, self.scroll_regions,
                             self.geometry, self.labels)),
                    'Closed context compilation requires an unused compiler')
            # Dequeued contexts contribute no paint or input regions. Keep the
            # retained tree untouched; do not fake a hidden-control mutation.
            if self.context in SCENE_CONTEXTS:
                return b'ZSUPIX02' + struct.pack('<6I', self.width, self.height, 0, 0, 0, 0)
            return b'ZSUPIX01' + struct.pack('<5I', self.width, self.height, 0, 0, 0)
        expected_timer = 1 if self.context in ('ranking', 'research-tree') else 0
        require(snapshot.get('active') is True and snapshot.get('timerSemaphore') == expected_timer,
                'Snapshot is not a shown active popup for the selected context')
        if self.context in SCENE_CONTEXTS:
            expected_name, expected_kind = (('ProductionPopup', 'Production') if self.context == 'production'
                                            else ('TechPopup', 'Research') if self.context == 'research'
                                            else ('TechTree', 'ResearchTree') if self.context == 'research-tree'
                                            else ('GenericPopup', 'CityCapture') if self.context == 'city-capture'
                                            else ('diplomacy', 'LeaderHead') if self.context == 'diplomacy'
                                            else ('CityView', 'CityView'))
            require(snapshot.get('contextName') == expected_name and snapshot.get('popupKind') == expected_kind,
                    'Snapshot does not identify the selected official popup context')
            if self.context == 'research-tree':
                lifecycle = snapshot.get('lifecycle')
                require(lifecycle == ['queued', f'shown:{RESEARCH_TREE_POPUP_ENUM_VALUE}'],
                        'TechTree active lifecycle differs from original BUTTONPOPUP_TECH_TREE (67)')
            elif self.context == 'diplomacy':
                require(snapshot.get('lifecycle') == ['queued'],
                        'LeaderHead intro must remain in its original queued active state')
            elif self.context == 'city-view':
                require(snapshot.get('lifecycle') == ['queued'],
                        'CityView lifecycle differs from its original enter-city-screen path')
            require(snapshot.get('presentationClock') == self.snapshot_clock,
                    'Popup snapshot clock differs from the selected compiler clock')
            require(snapshot.get('animationPolicy') == 'ZEROSIS_FRONTEND_XML_TIMELINE_V1' and
                    snapshot.get('retailTimingVerified') is False,
                    'Popup snapshot animation policy/proof boundary is missing or overstated')
            metrics = snapshot.get('fontMetrics')
            require(type(metrics) is dict and metrics.get('policy') == 'CIV5_GLYPHGEN_GGXML_LAYOUT_V1' and
                    metrics.get('retailMetricSemanticsVerified') is False and
                    metrics.get('wrapPolicy') == 'GREEDY_ASCII_SPACE_WORD_WRAP_SPLIT_LONG_WORD_AT_CODEPOINT',
                    'Popup snapshot font metric policy/proof boundary is missing or overstated')
            targets = snapshot.get('inputTargets')
            require(type(targets) is list, 'Popup snapshot lacks registered inputTargets')
            self.production_font_metrics = metrics
            self.production_input_targets = targets
            scroll_targets = snapshot.get('scrollTargets')
            require(type(scroll_targets) is list, 'Popup snapshot lacks captured scrollTargets')
            self.production_scroll_targets = scroll_targets
        before = copy.deepcopy(snapshot)
        if self.context == 'city-view':
            self.validate_city_view_context_font_defaults(snapshot)
        if self.context in SCENE_CONTEXTS:
            # Scrollbar rendering crosschecks its captured range against the
            # already validated owning ScrollPanel target.
            self.production_scrolls(snapshot['tree'])
            if self.context == 'city-view':
                self.validate_city_view_payload(snapshot)
        self.node(snapshot['tree'], (0, 0, self.width, self.height), {}, (0, 0, self.width, self.height))
        if self.context in SCENE_CONTEXTS:
            self.production_hits(snapshot['tree'])
        require(snapshot == before, 'Presentation modified retained GameCore UI state')
        validate_hit_regions(self.context, self.hits, self.geometry)
        require(len(self.textures) <= 64 and len(self.sprites) <= 10000, 'Unbounded scene packet')
        if self.context in SCENE_CONTEXTS:
            blob = bytearray(b'ZSUPIX02' + struct.pack('<6I', self.width, self.height,
                              len(self.textures), len(self.sprites), len(self.hits), len(self.scroll_regions)))
        else:
            blob = bytearray(b'ZSUPIX01' + struct.pack('<5I', self.width, self.height,
                              len(self.textures), len(self.sprites), len(self.hits)))
        for path in self.textures:
            # Keep the scene relocatable together with its bounded candidate atlases.
            raw = str(Path(path).relative_to(self.destination)).replace('\\', '/').encode('utf-8')
            require(0 < len(raw) < 4096, 'Invalid scene texture path length')
            blob += struct.pack('<I', len(raw)) + raw
        for sprite in self.sprites:
            blob += struct.pack('<IQ16f', *sprite)
        for hit in self.hits:
            blob += struct.pack('<Q4f', *hit)
        for region in self.scroll_regions:
            blob += struct.pack('<Q4f', *region)
        return bytes(blob)

    def unchanged(self):
        if (not self.assets.unchanged() or sha256(self.styles_path) != self.styles_hash or
                any(sha256(path) != digest for path, digest in self.context_sources.items())):
            return False
        return all(Path(row['path']).is_file() and sha256(row['path']) == row['sha256']
                   for row in self.derived_textures) and all(sha256(row['ggxml_path']) == row['ggxml_sha256'] and
                   sha256(row['color_atlas_path']) == row['color_atlas_sha256'] and
                   all(sha256(sheet['source_path']) == sheet['source_sha256'] for sheet in row['sheets'])
                   for row in self.font_records)
