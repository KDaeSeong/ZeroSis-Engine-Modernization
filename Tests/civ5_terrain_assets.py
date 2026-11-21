from __future__ import annotations

import csv
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
from civ5_terrain_assets import (FIELDS, HEIGHT_PIECES, MAGIC, SUPPORTED_IDS, parse_terrain_csv,
                                 prepare, validate_dxt5_dds, validate_height_dds)
from civ5_ui_assets import Fpk


def make_dds(width, height, fourcc, mips=1, pixel=None):
    words = [0] * 32
    words[1] = 124
    words[2] = 0x1007
    words[3], words[4] = height, width
    words[6], words[7] = 0, mips
    words[19] = 32
    words[20], words[21] = 4, fourcc
    words[28] = 0
    body = bytearray()
    for level in range(mips):
        w, h = max(1, width >> level), max(1, height >> level)
        if fourcc == int.from_bytes(b"DXT5", "little"):
            body.extend(bytes(((w + 3) // 4) * ((h + 3) // 4) * 16))
        else:
            for index in range(w * h):
                body.extend(struct.pack("<4H", *(pixel(index) if pixel else (100, 100, 100, 100))))
    return b"DDS " + struct.pack("<31I", *words[1:]) + body


def write_fpk(path, entries):
    rows = []
    table_bytes = bytearray(struct.pack("<I", 6) + b"FPK_\0\0" + struct.pack("<I", len(entries)))
    table_lengths = []
    for name, data in entries.items():
        encoded = name.encode("utf-8")
        padding = (-len(encoded)) % 4
        raw = encoded + (bytes([padding]) + bytes(padding - 1) if padding else b"")
        row = struct.pack("<I", len(encoded)) + raw + struct.pack("<QII", 1, len(data), 0)
        table_lengths.append(len(row))
        rows.append((name, data, row))
    offset = len(table_bytes) + sum(table_lengths)
    for name, data, row in rows:
        mutable = bytearray(row)
        struct.pack_into("<I", mutable, len(mutable) - 4, offset)
        table_bytes.extend(mutable)
        offset += len(data)
    with path.open("wb") as stream:
        stream.write(table_bytes)
        for _name, data, _row in rows:
            stream.write(data)


def csv_row(continent, material_id, diffuse):
    return [str(continent), diffuse, "height.dds", "NULL", "0", "0.014", "0", str(material_id)]


class TerrainAssetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=PROJECT)
        self.root = Path(self.temp.name) / "game"
        self.csv_path = self.root / "Assets/DLC/Shared/Terrain/TerrainDef.csv"
        self.pack_path = self.root / "Resource/DX9/TerrainTextures.fpk"
        self.csv_path.parent.mkdir(parents=True)
        self.pack_path.parent.mkdir(parents=True)

    def tearDown(self):
        self.temp.cleanup()

    def write_csv(self, rows):
        with self.csv_path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(FIELDS)
            writer.writerows(rows)

    def make_fixture(self, ids=None, diffuse_override=None):
        ids = sorted(SUPPORTED_IDS if ids is None else ids)
        entries = {}
        rows = []
        for material_id in ids:
            name = diffuse_override or f"material_{material_id}.dds"
            rows.append(csv_row(0, material_id, name))
            entries[name] = make_dds(4, 4, int.from_bytes(b"DXT5", "little"))
        self.write_csv(rows)
        write_fpk(self.pack_path, entries)
        for _kind, relative in HEIGHT_PIECES:
            path = self.root / Path(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            # Verify alpha preservation and channel statistics from real top-mip texels.
            path.write_bytes(make_dds(128, 128, 36, pixel=lambda i: (100 + i % 4, 100 + i % 4,
                                                                       100 + i % 4, 200 + i % 5)))

    def test_csv_is_strict_sorted_and_filters_materials(self):
        self.write_csv([csv_row(4, 2, "plains.dds"), csv_row(0, 2, "grass.dds"),
                        csv_row(1, 99, "ignored.dds")])
        self.assertEqual([(r["continent"], r["material_id"]) for r in parse_terrain_csv(self.csv_path, {2})],
                         [(0, 2), (4, 2)])

    def test_csv_rejects_invalid_numbers_duplicate_keys_and_unsafe_paths(self):
        for rows, requested, pattern in (
                ([csv_row("+1", 2, "x.dds")], {2}, "continent"),
                ([csv_row(0, 2, "x.dds"), csv_row(0, 2, "y.dds")], {2}, "Duplicate"),
                ([csv_row(0, 2, "..\\evil.dds")], {2}, "Unsafe"),
                ([csv_row(0, 2, "C:evil.dds")], {2}, "Unsafe")):
            self.write_csv(rows)
            with self.subTest(pattern=pattern), self.assertRaisesRegex(ValueError, pattern):
                parse_terrain_csv(self.csv_path, requested)

    def test_dxt5_requires_exact_all_mip_payload(self):
        valid = make_dds(8, 8, int.from_bytes(b"DXT5", "little"), mips=4)
        self.assertEqual(validate_dxt5_dds(valid)["mips"], 4)
        with self.assertRaisesRegex(ValueError, "payload length"):
            validate_dxt5_dds(valid[:-1])
        with self.assertRaisesRegex(ValueError, "DXT5"):
            validate_dxt5_dds(make_dds(4, 4, 36))

    def test_height_validator_checks_format_length_and_records_channels(self):
        data = make_dds(128, 128, 36, pixel=lambda _i: (1234, 1234, 1234, 2345))
        result = validate_height_dds(data)
        self.assertEqual(result["top_mip_channel_stats_u16"]["R"], {"min": 1234, "max": 1234})
        self.assertEqual(result["alpha_differs_from_r_texels"], 128 * 128)
        with self.assertRaisesRegex(ValueError, "payload/mip chain"):
            validate_height_dds(data[:-1])

    def test_package_contract_payload_order_and_content_addressing(self):
        self.make_fixture()
        out_root = Path(self.temp.name) / "Build/TerrainAssets"
        first = prepare(self.root, out_root)
        second = prepare(self.root, out_root)
        self.assertEqual(first["package_sha256"], second["package_sha256"])
        self.assertTrue(first["originals_unchanged"])
        package = Path(first["package_path"]).read_bytes()
        self.assertEqual(package[:8], MAGIC)
        version, count = struct.unpack_from("<II", package, 8)
        self.assertEqual((version, count), (1, len(SUPPORTED_IDS)))
        offset = 16
        for _ in range(count):
            _continent, _material, size = struct.unpack_from("<III", package, offset)
            offset += 12
            dds = package[offset:offset + size]
            self.assertEqual(validate_dxt5_dds(dds)["encoding"], "DXT5_BC3")
            offset += size
        pieces, = struct.unpack_from("<I", package, offset)
        self.assertEqual(pieces, 5)
        offset += 4
        for kind in range(5):
            actual_kind, size = struct.unpack_from("<II", package, offset)
            offset += 8
            self.assertEqual(actual_kind, kind)
            data = package[offset:offset + size]
            self.assertEqual(validate_height_dds(data)["encoding"], "A16B16G16R16_UNORM_CANDIDATE")
            offset += size
        self.assertEqual(offset, len(package))
        report = json.loads(Path(first["manifest_path"]).read_text(encoding="utf-8"))
        self.assertTrue(report["originals_unchanged"])
        self.assertEqual(len(report["height_pieces"]), 5)

    def test_missing_fpk_entry_is_rejected(self):
        self.write_csv([csv_row(0, 2, "not-in-pack.dds")])
        write_fpk(self.pack_path, {"dummy.dds": make_dds(4, 4, int.from_bytes(b"DXT5", "little"))})
        for _kind, relative in HEIGHT_PIECES:
            path = self.root / Path(relative)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(make_dds(128, 128, 36))
        with self.assertRaisesRegex(ValueError, "Missing diffuse FPK entry"):
            prepare(self.root, Path(self.temp.name) / "Build/TerrainAssets")

    def test_output_inside_installation_is_rejected(self):
        self.make_fixture(ids={2})
        with self.assertRaisesRegex(ValueError, "inside the game installation"):
            prepare(self.root, self.root / "Build")


if __name__ == "__main__":
    unittest.main(verbosity=2)
