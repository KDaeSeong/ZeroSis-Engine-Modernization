from __future__ import annotations

import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from collect_baseline import PROJECT  # noqa: E402
from prepare_ui_popup_assets import (  # noqa: E402
    DECLARE_WAR_XML,
    GAME,
    ICON_MAPPING_FILES,
    inline_icon_catalog,
)


class InstalledInlineIconCatalogTests(unittest.TestCase):
    @unittest.skipUnless(GAME.is_dir(), "Civ V installation is unavailable")
    def test_every_official_resource_icon_has_its_exact_catalog_glyph(self) -> None:
        evidence = PROJECT / "evidence"
        evidence.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="inline-icon-catalog-", dir=evidence) as directory:
            snapshots = Path(directory)
            catalog, _ = inline_icon_catalog(snapshots)

            resource_names: set[str] = set()
            for relative in ICON_MAPPING_FILES:
                root = ET.parse(GAME / relative).getroot()
                resource_names.update(
                    name
                    for name in (row.findtext("IconName") for row in root.findall("./IconFontMapping/*"))
                    if name and name.startswith("ICON_RES_")
                )

            self.assertGreater(len(resource_names), 0)
            self.assertTrue(resource_names.issubset(catalog.keys()))
            for name in resource_names:
                with self.subTest(icon=name):
                    entry = catalog[name]
                    self.assertGreater(entry["glyph"]["width"], 0)
                    self.assertGreater(entry["glyph"]["height"], 0)
                    self.assertTrue(entry["mapping_source"]["sha256"])
                    self.assertTrue(entry["font_source"]["sha256"])

            popup_root = ET.parse(GAME / DECLARE_WAR_XML).getroot()
            popup_text = " ".join(
                element.get("String", "")
                for element in popup_root.iter("Label")
            )
            self.assertIn("[ICON_RES_ALUMINNUM]", popup_text)
            self.assertNotIn("ICON_RES_ALUMINNUM", resource_names)
            self.assertIn("ICON_RES_ALUMINUM", resource_names)


if __name__ == "__main__":
    unittest.main()
