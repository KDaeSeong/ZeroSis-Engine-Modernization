from __future__ import annotations

import hashlib
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from ui_bitmap_fonts import (  # noqa: E402
    FontAssetError,
    Glyph,
    UnsupportedFontStyleError,
    UnsupportedGlyphError,
    layout_text,
    load_font,
)


GAME_ROOT = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")


def dds_alpha8(width: int, height: int) -> bytes:
    data = bytearray(128 + width * height)
    data[:4] = b"DDS "
    struct.pack_into("<IIII", data, 4, 124, 0x0002100F, height, width)
    struct.pack_into("<I", data, 76, 32)
    struct.pack_into("<IIIIIIII", data, 76, 32, 0x2, 0, 8, 0, 0, 0, 0xFF)
    return bytes(data)


def fixture_game_root(parent: Path) -> Path:
    root = parent / "game"
    (root / "Assets/UI/Fonts/Tw Cent MT").mkdir(parents=True)
    (root / "Assets/UI").mkdir(parents=True, exist_ok=True)
    (root / "font.dds").write_bytes(dds_alpha8(8, 8))
    (root / "shadow.dds").write_bytes(dds_alpha8(8, 8))
    ggxml = '''<?xml version="1.0"?>
<glyphgen>
  <textures width="8" height="8">
    <texture name="Font" src="font.dds" allowcolor="1" alloweffects="1" inuse="1" />
    <texture name="Shadow" src="shadow.dds" allowcolor="1" alloweffects="1" inuse="1" />
  </textures>
  <styles count="3">
    <style name="Base"><layers count="1"><layer tex="Font" /></layers></style>
    <style name="Shadow"><layers count="2"><layer tex="Font" /><layer tex="Shadow" /></layers></style>
    <style name="Stroke"><layers count="2"><layer tex="Font" /><layer tex="Shadow" /></layers></style>
  </styles>
  <glyphs fudgeadv="1" ascadj="2" spacing="2" count="4" height="6" ascent="5" descent="2">
    <glyph ch="32" u="0" v="0" width="0" height="0" a="0" b="2" c="0" originx="0" originy="0" />
    <glyph ch="65" u="0" v="0" width="3" height="5" a="1" b="3" c="1" originx="-1" originy="5" />
    <glyph ch="66" u="3" v="0" width="3" height="5" a="0" b="3" c="0" originx="0" originy="5" />
    <glyph ch="47928" u="0" v="5" width="5" height="3" a="0" b="4" c="0" originx="0" originy="2" />
  </glyphs>
  <imports count="0" />
</glyphgen>
'''
    (root / "Assets/UI/Fonts/Tw Cent MT/TwCenMT22.ggxml").write_text(ggxml, encoding="utf-8")
    (root / "Assets/UI/ColorAtlas.xml").write_text('''<?xml version="1.0"?>
<ColorAtlas>
  <Color Name="Beige" Color="255,255,200,255" />
  <Color Name="Black" Color="0,0,0,255" />
  <ColorSet Name="Beige_Black_Alpha" Color0="Beige" Color1="Black,200" />
</ColorAtlas>
''', encoding="utf-8")
    return root


class BitmapFontFixtureTests(unittest.TestCase):
    def test_source_metrics_layers_colors_and_texture_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = fixture_game_root(Path(directory))
            font = load_font(game, "TwCenMT22", "Shadow")
            self.assertEqual(font.layers[0].texture_alias, "Font")
            self.assertEqual(font.layers[1].texture_alias, "Shadow")
            self.assertEqual(font.line_advance, 7)
            self.assertEqual(font.baseline_offset, 7)
            self.assertEqual(font.glyphs[65].texture_rect, (0, 0, 3, 5))
            self.assertEqual(font.glyphs[65].abc_advance, 5)
            self.assertEqual(font.color_sets["Beige_Black_Alpha"].layer_colors[0].rgba,
                             (255, 255, 200, 255))
            self.assertEqual(font.color_sets["Beige_Black_Alpha"].layer_colors[1].rgba,
                             (0, 0, 0, 200))
            self.assertEqual(font.color_atlas_sha256,
                             hashlib.sha256(font.color_atlas_path.read_bytes()).hexdigest())
            sheet = font.sheets["Font"]
            self.assertEqual((sheet.width, sheet.height, sheet.format),
                             (8, 8, "alpha8(flags=0x2,bits=8,alpha=0xff)"))
            self.assertEqual(sheet.sha256, hashlib.sha256((game / "font.dds").read_bytes()).hexdigest())
            self.assertEqual(font.kerning, {})

    def test_stroke_style_is_loaded_as_its_authored_ordered_layers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            font = load_font(fixture_game_root(Path(directory)), "TwCenMT22", "Stroke")
            self.assertEqual([layer.texture_alias for layer in font.layers], ["Font", "Shadow"])
            self.assertEqual(font.styles["Stroke"], ("Font", "Shadow"))

    def test_text_positions_tracking_and_explicit_newlines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            font = load_font(fixture_game_root(Path(directory)), "TwCenMT22", "Base")
            result = layout_text("AB\r\n문", font)
            self.assertEqual(len(result.lines), 2)
            self.assertEqual([(item.codepoint, item.text_index) for item in result.placements],
                             [(65, 0), (66, 1), (47928, 4)])
            first, second, third = result.placements
            self.assertEqual((first.pen_x, first.draw_x, first.baseline_y, first.draw_y), (0, 0, 7, 2))
            self.assertEqual((first.advance, first.tracking_after), (5, 0))
            self.assertEqual(second.pen_x, 5)
            self.assertEqual(third.line_index, 1)
            self.assertEqual(third.baseline_y, 14)
            self.assertEqual(font.spacing, 2)
            self.assertEqual(font.fudgeadv, 1)
            self.assertFalse(result.retail_metric_semantics_verified)
            self.assertEqual(result.width, max(line.advance_width for line in result.lines))
            self.assertEqual(result.height, 14)

    def test_official_icon_glyph_can_share_text_layout_without_host_font_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            font = load_font(fixture_game_root(Path(directory)), "TwCenMT22", "Base")
            icon = Glyph(0xF0000, 1, 2, 4, 5, 0, 22, 0, 0, 5)
            result = layout_text("A\U000f0000B", font, inline_glyphs={icon.codepoint: icon})
            self.assertEqual([row.codepoint for row in result.placements], [65, icon.codepoint, 66])
            self.assertEqual([row.advance for row in result.placements], [5, 22, 3])
            self.assertEqual(result.placements[1].texture_rect, (1, 2, 4, 5))

    def test_missing_glyph_is_explicit_without_os_fallback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            font = load_font(fixture_game_root(Path(directory)), "TwCenMT22")
            with self.assertRaises(UnsupportedGlyphError) as caught:
                layout_text("A☃", font)
            self.assertEqual((caught.exception.codepoint, caught.exception.index), (0x2603, 1))

    def test_unknown_style_and_external_glyph_import_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = fixture_game_root(Path(directory))
            with self.assertRaises(UnsupportedFontStyleError):
                load_font(game, "TwCenMT22", "Soft")
            path = game / "Assets/UI/Fonts/Tw Cent MT/TwCenMT22.ggxml"
            path.write_text(path.read_text(encoding="utf-8").replace(
                '<imports count="0" />', '<imports count="1"><import src="other.ggxml" /></imports>'),
                encoding="utf-8")
            with self.assertRaisesRegex(FontAssetError, "imported glyph data"):
                load_font(game, "TwCenMT22")

    def test_wrong_dds_dimensions_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            game = fixture_game_root(Path(directory))
            (game / "font.dds").write_bytes(dds_alpha8(7, 8))
            with self.assertRaisesRegex(FontAssetError, "dimensions"):
                load_font(game, "TwCenMT22")


class InstalledTwCenFontTests(unittest.TestCase):
    @unittest.skipUnless(GAME_ROOT.is_dir(), "Civ V installation is unavailable")
    def test_installed_sizes_english_korean_and_shadow_layers(self) -> None:
        for font_id in ("TwCenMT14", "TwCenMT16", "TwCenMT18", "TwCenMT22"):
            with self.subTest(font_id=font_id):
                base = load_font(GAME_ROOT, font_id, "Base")
                shadow = load_font(GAME_ROOT, font_id, "Shadow")
                stroke = load_font(GAME_ROOT, font_id, "Stroke")
                self.assertEqual((base.texture_width, base.texture_height), (2048, 1280))
                self.assertEqual(len(base.layers), 1)
                self.assertEqual(len(shadow.layers), 2)
                self.assertEqual(len(stroke.layers), 2)
                self.assertTrue(all(layer.sheet.format.startswith("alpha8") for layer in shadow.layers))
                self.assertTrue(all(layer.sheet.path.is_file() and len(layer.sheet.sha256) == 64
                                    for layer in shadow.layers))
                self.assertEqual(base.glyphs[32].width, 0)
                self.assertEqual(layout_text("English 123", base).placements[0].codepoint, ord("E"))
                korean = layout_text("문명", base)
                self.assertEqual([item.codepoint for item in korean.placements], [ord("문"), ord("명")])
                self.assertEqual(base.kerning, {})
                self.assertEqual(base.color_sets["MenuTitleColors"].layer_colors[0].rgba,
                                 (30, 50, 80, 255))
                if font_id == "TwCenMT22":
                    title = "The World's Most Well Fed People"
                    layout = layout_text(title, base)
                    self.assertEqual(layout.width, sum(base.glyphs[ord(char)].abc_advance for char in title))
                    self.assertEqual(layout.width, 280)
                    self.assertEqual(base.spacing, 5)
                    self.assertFalse(layout.retail_metric_semantics_verified)
        size16 = load_font(GAME_ROOT, "TwCenMT16", "Base")
        self.assertEqual(size16.layers[0].sheet.source_name, "kTwCenMT14.dds")

    @unittest.skipUnless(GAME_ROOT.is_dir(), "Civ V installation is unavailable")
    def test_unsupported_installed_glyph_reports_exact_index(self) -> None:
        font = load_font(GAME_ROOT, "TwCenMT22", "Base")
        with self.assertRaises(UnsupportedGlyphError) as caught:
            layout_text("문☃", font)
        self.assertEqual((caught.exception.codepoint, caught.exception.index), (0x2603, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
