"""Read Civ V glyphgen bitmap fonts without substituting host fonts.

The loader is intentionally strict: it resolves the installed GGXML, its
root-relative alpha DDS sheets, and ColorAtlas.xml, then returns immutable
metrics and ordered layer metadata for a renderer to consume.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
import struct
from types import MappingProxyType
from typing import Mapping, Union
import xml.etree.ElementTree as ET

Pathish = Union[str, Path]


class FontAssetError(ValueError):
    """Installed font data is missing, malformed, or outside the supported schema."""


class UnsupportedFontStyleError(FontAssetError):
    pass


class UnsupportedGlyphError(FontAssetError):
    def __init__(self, codepoint: int, index: int):
        self.codepoint = codepoint
        self.index = index
        super().__init__(f"No exact glyph for U+{codepoint:04X} at text index {index}")


@dataclass(frozen=True)
class Glyph:
    codepoint: int
    u: int
    v: int
    width: int
    height: int
    a: int
    b: int
    c: int
    origin_x: int
    origin_y: int

    @property
    def abc_advance(self) -> int:
        return self.a + self.b + self.c

    @property
    def texture_rect(self) -> tuple[int, int, int, int]:
        return (self.u, self.v, self.width, self.height)


@dataclass(frozen=True)
class TextureSheet:
    alias: str
    source_name: str
    path: Path
    sha256: str
    size: int
    width: int
    height: int
    format: str
    allow_color: bool
    allow_effects: bool
    in_use: bool


@dataclass(frozen=True)
class FontLayer:
    order: int
    texture_alias: str
    sheet: TextureSheet


@dataclass(frozen=True)
class Color:
    name: str
    rgba: tuple[int, int, int, int]


@dataclass(frozen=True)
class ColorSet:
    name: str
    layer_colors: tuple[Color, ...]


@dataclass(frozen=True)
class FontAsset:
    game_root: Path
    font_id: str
    font_style: str
    ggxml_path: Path
    ggxml_sha256: str
    color_atlas_path: Path
    color_atlas_sha256: str
    texture_width: int
    texture_height: int
    height: int
    ascent: int
    descent: int
    ascadj: int
    spacing: int
    fudgeadv: int
    glyphs: Mapping[int, Glyph]
    sheets: Mapping[str, TextureSheet]
    layers: tuple[FontLayer, ...]
    styles: Mapping[str, tuple[str, ...]]
    colors: Mapping[str, Color]
    color_sets: Mapping[str, ColorSet]
    kerning: Mapping[tuple[int, int], int]

    @property
    def line_advance(self) -> int:
        # GGXML supplies ascent/descent as the font's line box dimensions.
        return self.ascent + self.descent

    @property
    def baseline_offset(self) -> int:
        # ascadj is retained as an explicit GGXML baseline adjustment.
        return self.ascent + self.ascadj


@dataclass(frozen=True)
class GlyphPlacement:
    codepoint: int
    text_index: int
    line_index: int
    pen_x: int
    draw_x: int
    baseline_y: int
    draw_y: int
    advance: int
    tracking_after: int
    texture_rect: tuple[int, int, int, int]


@dataclass(frozen=True)
class TextLine:
    index: int
    first_placement: int
    placement_count: int
    advance_width: int
    ink_left: int
    ink_right: int


@dataclass(frozen=True)
class TextLayout:
    font_id: str
    font_style: str
    text: str
    line_advance: int
    baseline_offset: int
    placements: tuple[GlyphPlacement, ...]
    lines: tuple[TextLine, ...]
    width: int
    height: int
    retail_metric_semantics_verified: bool = False


def _required_int(attributes: Mapping[str, str], name: str, label: str) -> int:
    raw = attributes.get(name)
    if raw is None or not re.fullmatch(r"-?\d+", raw):
        raise FontAssetError(f"Missing or invalid integer {name!r} in {label}")
    return int(raw)


def _bool_attribute(attributes: Mapping[str, str], name: str, label: str) -> bool:
    raw = attributes.get(name)
    if raw not in ("0", "1"):
        raise FontAssetError(f"Missing or invalid boolean {name!r} in {label}")
    return raw == "1"


def _read_color_asset(asset_root: Path) -> tuple[Mapping[str, Color], Mapping[str, ColorSet], Path, str]:
    path = asset_root / "Assets/UI/ColorAtlas.xml"
    try:
        color_bytes = path.read_bytes()
        root = ET.fromstring(color_bytes)
    except (OSError, ET.ParseError) as error:
        raise FontAssetError(f"Unable to parse installed ColorAtlas.xml: {error}") from error
    if root.tag != "ColorAtlas":
        raise FontAssetError("Unexpected ColorAtlas.xml root element")

    colors: dict[str, Color] = {}
    for element in root.findall("Color"):
        name = element.attrib.get("Name")
        raw = element.attrib.get("Color")
        if not name or name in colors or not raw:
            raise FontAssetError("Invalid or duplicate ColorAtlas color")
        channels = raw.split(",")
        if len(channels) != 4 or any(not re.fullmatch(r"\d+", item) for item in channels):
            raise FontAssetError(f"Unsupported ColorAtlas value for {name}")
        rgba = tuple(int(item) for item in channels)
        if any(channel > 255 for channel in rgba):
            raise FontAssetError(f"ColorAtlas channel out of range for {name}")
        colors[name] = Color(name, rgba)  # type: ignore[arg-type]

    def resolve(raw: str, set_name: str) -> Color:
        vector_separator = "," if "," in raw else "."
        pieces = raw.split(vector_separator)
        if len(pieces) == 4 and all(re.fullmatch(r"\d+", item) for item in pieces):
            rgba = tuple(int(item) for item in pieces)
            if any(channel > 255 for channel in rgba):
                raise FontAssetError(f"ColorSet channel out of range in {set_name}")
            return Color(raw, rgba)  # type: ignore[arg-type]
        base = colors.get(pieces[0])
        if base is None or len(pieces) > 2:
            raise FontAssetError(f"Unknown ColorSet layer reference {raw!r} in {set_name}")
        if len(pieces) == 1:
            return base
        if not re.fullmatch(r"\d+", pieces[1]) or int(pieces[1]) > 255:
            raise FontAssetError(f"Invalid alpha override in ColorSet {set_name}")
        rgba = (*base.rgba[:3], int(pieces[1]))
        return Color(raw, rgba)

    color_sets: dict[str, ColorSet] = {}
    for element in root.findall("ColorSet"):
        name = element.attrib.get("Name")
        if not name or name in color_sets:
            raise FontAssetError("Missing or duplicate ColorSet name")
        layer_names = [key for key in element.attrib if re.fullmatch(r"Color\d+", key)]
        layer_names.sort(key=lambda key: int(key[5:]))
        if not layer_names or layer_names != [f"Color{i}" for i in range(len(layer_names))]:
            raise FontAssetError(f"Non-contiguous ColorSet layers in {name}")
        color_sets[name] = ColorSet(name, tuple(resolve(element.attrib[key], name) for key in layer_names))
    return MappingProxyType(colors), MappingProxyType(color_sets), path.resolve(), hashlib.sha256(color_bytes).hexdigest()


def _read_dds(path: Path, declared_width: int, declared_height: int) -> tuple[str, str, int]:
    try:
        data = path.read_bytes()
    except OSError as error:
        raise FontAssetError(f"Unable to read bitmap font sheet {path}: {error}") from error
    if len(data) < 128 or data[:4] != b"DDS ":
        raise FontAssetError(f"Invalid DDS header: {path}")
    header_size, flags, height, width = struct.unpack_from("<IIII", data, 4)
    if header_size != 124:
        raise FontAssetError(f"Unsupported DDS header size in {path}")
    pf_size, pf_flags, fourcc, bit_count, red_mask, green_mask, blue_mask, alpha_mask = struct.unpack_from(
        "<IIIIIIII", data, 76)
    if pf_size != 32:
        raise FontAssetError(f"Unsupported DDS pixel-format header in {path}")
    # Installed Civ V glyph sheets are uncompressed 8-bit alpha masks.
    if pf_flags != 0x2 or bit_count != 8 or alpha_mask != 0xFF or any(
            (fourcc, red_mask, green_mask, blue_mask)):
        raise FontAssetError(f"Expected the installed alpha8 glyph atlas format: {path}")
    if width != declared_width or height != declared_height:
        raise FontAssetError(
            f"DDS dimensions {width}x{height} disagree with GGXML {declared_width}x{declared_height}: {path}")
    return (f"alpha8(flags=0x{pf_flags:x},bits={bit_count},alpha=0x{alpha_mask:x})",
            hashlib.sha256(data).hexdigest(), len(data))


def load_font(asset_root: Pathish, font_id: str, font_style: str = "Base") -> FontAsset:
    """Load an installed Firaxis glyphgen font from a Civ V game root.

    `asset_root` is the game install root. GGXML and ColorAtlas.xml live below
    Assets, while the GGXML texture src paths resolve at the game root.
    """
    game_root = Path(asset_root).resolve()
    if not re.fullmatch(r"TwCenMT\d+", font_id):
        raise FontAssetError(f"Unsupported font identifier: {font_id!r}")
    ggxml = game_root / "Assets/UI/Fonts/Tw Cent MT" / f"{font_id}.ggxml"
    try:
        raw = ggxml.read_bytes()
        root = ET.fromstring(raw)
    except OSError as error:
        raise FontAssetError(f"Unable to read installed font definition {ggxml}: {error}") from error
    except ET.ParseError as error:
        raise FontAssetError(f"Malformed GGXML {ggxml}: {error}") from error
    if root.tag != "glyphgen":
        raise FontAssetError("Unexpected GGXML root element")

    textures_element = root.find("textures")
    styles_element = root.find("styles")
    glyphs_element = root.find("glyphs")
    imports_element = root.find("imports")
    if textures_element is None or styles_element is None or glyphs_element is None or imports_element is None:
        raise FontAssetError("GGXML is missing a required section")
    if list(imports_element):
        raise FontAssetError("GGXML imported glyph data is unsupported")
    if any(child.tag != "glyph" for child in glyphs_element):
        raise FontAssetError("GGXML glyph extensions or kerning records are unsupported")

    texture_width = _required_int(textures_element.attrib, "width", "textures")
    texture_height = _required_int(textures_element.attrib, "height", "textures")
    if texture_width <= 0 or texture_height <= 0:
        raise FontAssetError("Nonpositive GGXML texture dimensions")

    texture_rows: dict[str, tuple[str, bool, bool, bool]] = {}
    for row in textures_element.findall("texture"):
        alias = row.attrib.get("name")
        source_name = row.attrib.get("src")
        if alias is None or source_name is None or alias in texture_rows:
            raise FontAssetError("Missing or duplicate GGXML texture alias")
        source_path = Path(source_name)
        if source_path.is_absolute() or ".." in source_path.parts:
            raise FontAssetError("GGXML texture path escapes the installed game root")
        texture_rows[alias] = (source_name, _bool_attribute(row.attrib, "allowcolor", alias),
                               _bool_attribute(row.attrib, "alloweffects", alias),
                               _bool_attribute(row.attrib, "inuse", alias))

    style_layers: dict[str, tuple[str, ...]] = {}
    for style_element in styles_element.findall("style"):
        name = style_element.attrib.get("name")
        layers_node = style_element.find("layers")
        if name is None or name in style_layers or layers_node is None:
            raise FontAssetError("Invalid or duplicate GGXML font style")
        layer_names = tuple(layer.attrib.get("tex", "") for layer in layers_node.findall("layer"))
        if len(layer_names) != _required_int(layers_node.attrib, "count", f"style {name}"):
            raise FontAssetError(f"Layer count mismatch in font style {name}")
        if not layer_names or any(layer not in texture_rows for layer in layer_names):
            raise FontAssetError(f"Unknown or empty texture layer in font style {name}")
        style_layers[name] = layer_names
    if len(style_layers) != _required_int(styles_element.attrib, "count", "styles"):
        raise FontAssetError("GGXML style count mismatch")
    if font_style not in style_layers:
        raise UnsupportedFontStyleError(f"Style {font_style!r} is not defined for {font_id}")

    sheets: dict[str, TextureSheet] = {}
    by_source: dict[str, tuple[str, int]] = {}
    for alias, (source_name, allow_color, allow_effects, in_use) in texture_rows.items():
        if source_name not in by_source:
            sheet_path = (game_root / Path(source_name)).resolve()
            if not sheet_path.is_relative_to(game_root):
                raise FontAssetError("Resolved texture path escapes the installed game root")
            texture_format, sha256, size = _read_dds(sheet_path, texture_width, texture_height)
            by_source[source_name] = (sha256, size)
        else:
            sha256, size = by_source[source_name]
            sheet_path = (game_root / Path(source_name)).resolve()
            texture_format = "alpha8(flags=0x2,bits=8,alpha=0xff)"
        sheets[alias] = TextureSheet(alias, source_name, sheet_path, sha256, size,
                                     texture_width, texture_height, texture_format,
                                     allow_color, allow_effects, in_use)

    global_metrics = glyphs_element.attrib
    height = _required_int(global_metrics, "height", "glyphs")
    ascent = _required_int(global_metrics, "ascent", "glyphs")
    descent = _required_int(global_metrics, "descent", "glyphs")
    ascadj = _required_int(global_metrics, "ascadj", "glyphs")
    spacing = _required_int(global_metrics, "spacing", "glyphs")
    fudgeadv = _required_int(global_metrics, "fudgeadv", "glyphs")
    if height <= 0 or ascent < 0 or descent < 0:
        raise FontAssetError("Invalid GGXML vertical metrics")
    glyphs: dict[int, Glyph] = {}
    for element in glyphs_element.findall("glyph"):
        attrs = element.attrib
        codepoint = _required_int(attrs, "ch", "glyph")
        if not 0 <= codepoint <= 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
            raise FontAssetError(f"Invalid Unicode codepoint in GGXML: {codepoint}")
        if codepoint in glyphs:
            raise FontAssetError(f"Duplicate glyph U+{codepoint:04X}")
        values = {key: _required_int(attrs, key, f"glyph U+{codepoint:04X}")
                  for key in ("u", "v", "width", "height", "a", "b", "c", "originx", "originy")}
        if min(values["u"], values["v"], values["width"], values["height"]) < 0:
            raise FontAssetError(f"Negative glyph texture rectangle for U+{codepoint:04X}")
        if values["u"] + values["width"] > texture_width or values["v"] + values["height"] > texture_height:
            raise FontAssetError(f"Glyph texture rectangle exceeds the atlas for U+{codepoint:04X}")
        glyphs[codepoint] = Glyph(codepoint, values["u"], values["v"], values["width"], values["height"],
                                  values["a"], values["b"], values["c"],
                                  values["originx"], values["originy"])
    if len(glyphs) != _required_int(global_metrics, "count", "glyphs"):
        raise FontAssetError("GGXML glyph count mismatch")

    colors, color_sets, color_atlas_path, color_atlas_sha256 = _read_color_asset(game_root)
    selected_layers = tuple(FontLayer(index, alias, sheets[alias])
                            for index, alias in enumerate(style_layers[font_style]))
    return FontAsset(game_root, font_id, font_style, ggxml, hashlib.sha256(raw).hexdigest(),
                     color_atlas_path, color_atlas_sha256,
                     texture_width, texture_height, height, ascent, descent, ascadj, spacing, fudgeadv,
                     MappingProxyType(glyphs), MappingProxyType(sheets), selected_layers,
                     MappingProxyType(style_layers), colors, color_sets, MappingProxyType({}))


def layout_text(text: str, font: FontAsset, *, inline_glyphs: Mapping[int, Glyph] | None = None) -> TextLayout:
    """Lay out exact codepoints using only the GGXML ABC advances.

    Newline, CRLF, and CR create lines. There is no wrapping, fallback font,
    Unicode normalization, shaping, tracking, or fabricated kerning. The
    GGXML ``spacing``, ``fudgeadv``, and vertical adjustment fields remain
    available on FontAsset but are not applied: their retail renderer meaning
    has not been established. Vertical positions use an explicitly provisional
    ascent/descent + ascadj convention and are not pixel-equivalence evidence.
    Missing codepoints raise UnsupportedGlyphError with the original index.
    """
    if not isinstance(text, str):
        raise TypeError("text must be str")
    chunks: list[list[tuple[str, int]]] = [[]]
    cursor = 0
    line_index = 0
    while cursor < len(text):
        character = text[cursor]
        if character == "\r":
            chunks.append([])
            line_index += 1
            cursor += 2 if cursor + 1 < len(text) and text[cursor + 1] == "\n" else 1
        elif character == "\n":
            chunks.append([])
            line_index += 1
            cursor += 1
        else:
            chunks[line_index].append((character, cursor))
            cursor += 1
    placements: list[GlyphPlacement] = []
    lines: list[TextLine] = []
    for line_index, chunk in enumerate(chunks):
        start_placement = len(placements)
        glyph_rows: list[tuple[int, int, Glyph]] = []
        for character, original_index in chunk:
            codepoint = ord(character)
            glyph = (inline_glyphs or {}).get(codepoint, font.glyphs.get(codepoint))
            if glyph is None:
                raise UnsupportedGlyphError(codepoint, original_index)
            glyph_rows.append((original_index, codepoint, glyph))
        pen_x = 0
        ink_left: int | None = None
        ink_right: int | None = None
        baseline_y = line_index * font.line_advance + font.baseline_offset
        for glyph_index, (text_index, codepoint, glyph) in enumerate(glyph_rows):
            draw_x = pen_x + glyph.a + glyph.origin_x
            draw_y = baseline_y - glyph.origin_y
            step_advance = glyph.abc_advance
            tracking_after = 0
            placements.append(GlyphPlacement(codepoint, text_index, line_index, pen_x, draw_x,
                                              baseline_y, draw_y, step_advance, tracking_after,
                                              glyph.texture_rect))
            ink_left = draw_x if ink_left is None else min(ink_left, draw_x)
            ink_right = draw_x + glyph.width if ink_right is None else max(ink_right, draw_x + glyph.width)
            pen_x += step_advance + tracking_after
        lines.append(TextLine(line_index, start_placement, len(glyph_rows), pen_x,
                              0 if ink_left is None else ink_left,
                              0 if ink_right is None else ink_right))
    return TextLayout(font.font_id, font.font_style, text, font.line_advance, font.baseline_offset,
                      tuple(placements), tuple(lines), max((line.advance_width for line in lines), default=0),
                      len(lines) * font.line_advance)
