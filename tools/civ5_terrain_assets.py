"""Bounded Civ V terrain diffuse packaging from TerrainDef.csv and TerrainTextures.fpk."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import re
import struct
from typing import Iterable

from civ5_ui_assets import Fpk, require, sha256

MAGIC = b"ZSTERR01"
VERSION = 1
MAX_PACKAGE_BYTES = 128 * 1024 * 1024
SUPPORTED_IDS = {0, 2, 5, 8, 10, 15, 26, 27, 30, 32, 35, 44}
HEIGHT_PIECES = (
    (0, "Assets/terrain/pieces/Grass/Europe/Grass 01_H.dds"),
    (1, "Assets/terrain/pieces/Grass Hill/Europe/Grass_Hill_01_H.dds"),
    (2, "Assets/terrain/pieces/Mountain/Europe/Euro_Moun_1_1_H.dds"),
    (3, "Assets/terrain/pieces/Coast/Generic/Coast 21_H.dds"),
    (4, "Assets/terrain/pieces/Ocean/Generic/Ocean 21_H.dds"),
)
CSV_RELATIVE = Path("Assets/DLC/Shared/Terrain/TerrainDef.csv")
PACK_RELATIVE = Path("Resource/DX9/TerrainTextures.fpk")
FIELDS = ("Continent ID", "Diffuse", "Heightmap", "Specmap", "BaseDominance",
          "Texture Scale", "Projection(0=horizontal 1=vertical)", " ID (unique for continent)")
_DECIMAL = re.compile(r"(?:0|[1-9][0-9]*)\Z", re.ASCII)
_BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_. -]*\.dds\Z", re.ASCII | re.IGNORECASE)


def _number(value: str, label: str) -> int:
    require(bool(_DECIMAL.fullmatch(value)), f"Invalid {label}: expected unsigned decimal integer")
    return int(value)


def parse_terrain_csv(path: Path, material_ids: Iterable[int] = SUPPORTED_IDS):
    requested = set(material_ids)
    require(requested and all(type(item) is int and item >= 0 for item in requested),
            "Invalid requested material ID set")
    rows = []
    keys = set()
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        require(reader.fieldnames == list(FIELDS), "Unexpected TerrainDef.csv header")
        for line, row in enumerate(reader, 2):
            require(None not in row and all(value is not None for value in row.values()),
                    f"Malformed TerrainDef.csv row {line}")
            continent = _number(row["Continent ID"], f"continent at row {line}")
            material_id = _number(row[" ID (unique for continent)"], f"material ID at row {line}")
            require(continent in range(5), f"Unsupported continent ID at row {line}: {continent}")
            key = (continent, material_id)
            require(key not in keys, f"Duplicate terrain key {key}")
            keys.add(key)
            diffuse = row["Diffuse"]
            require(bool(_BASENAME.fullmatch(diffuse)) and "/" not in diffuse and "\\" not in diffuse and
                    ":" not in diffuse and diffuse not in (".", ".."),
                    f"Unsafe diffuse filename at row {line}: {diffuse!r}")
            require(diffuse.casefold().endswith(".dds"), f"Diffuse is not DDS at row {line}")
            if material_id not in requested:
                continue
            rows.append({"continent": continent, "material_id": material_id, "diffuse": diffuse,
                         "csv_line": line})
    require(rows, "TerrainDef.csv declares none of the requested material IDs")
    return sorted(rows, key=lambda row: (row["continent"], row["material_id"]))


def validate_dxt5_dds(data: bytes, name: str = "DDS"):
    require(len(data) >= 128 and data[:4] == b"DDS ", f"{name}: missing DDS header")
    words = struct.unpack_from("<32I", data)
    require(words[1] == 124 and words[19] == 32, f"{name}: invalid DDS header sizes")
    require(words[2] & 0x1007 == 0x1007 and words[28] == 0, f"{name}: unsupported DDS shape/caps")
    height, width = words[3], words[4]
    require(0 < width <= 16384 and 0 < height <= 16384, f"{name}: invalid DDS dimensions")
    require(words[6] == 0 and words[7] > 0, f"{name}: volume textures are unsupported")
    require(words[20] & 0x4 and words[21] == int.from_bytes(b"DXT5", "little"),
            f"{name}: expected DXT5/BC3 compressed diffuse")
    require(words[7] <= max(width, height).bit_length(), f"{name}: invalid mip count")
    expected = 128
    for level in range(words[7]):
        w, h = max(1, width >> level), max(1, height >> level)
        expected += ((w + 3) // 4) * ((h + 3) // 4) * 16
    require(len(data) == expected, f"{name}: DDS payload length/mip chain mismatch")
    return {"width": width, "height": height, "mips": words[7], "payload_bytes": len(data) - 128,
            "encoding": "DXT5_BC3", "validated_full_mip_chain": True}


def validate_height_dds(data: bytes, name: str = "height DDS"):
    require(len(data) >= 128 and data[:4] == b"DDS ", f"{name}: missing DDS header")
    words = struct.unpack_from("<32I", data)
    require(words[1] == 124 and words[19] == 32, f"{name}: invalid DDS header sizes")
    require(words[2] & 0x1007 == 0x1007 and words[28] == 0, f"{name}: unsupported DDS shape/caps")
    width, height = words[4], words[3]
    require((width, height) == (128, 128), f"{name}: expected 128x128 height piece")
    require(words[20] & 0x4 and words[21] == 36, f"{name}: expected A16B16G16R16 height data")
    mips = max(words[7], 1)
    require(mips <= max(width, height).bit_length(), f"{name}: invalid mip count")
    expected = 128 + sum(max(1, width >> i) * max(1, height >> i) * 8 for i in range(mips))
    require(len(data) == expected, f"{name}: height DDS payload/mip chain mismatch")
    channels = [(0xffff, 0, 0) for _ in range(4)]
    alpha_differs = 0
    for offset in range(128, 128 + width * height * 8, 8):
        values = struct.unpack_from("<4H", data, offset)
        for i, value in enumerate(values):
            low, high, _count = channels[i]
            channels[i] = (min(low, value), max(high, value), _count + 1)
        if values[3] != values[0]:
            alpha_differs += 1
    channel_names = ("R", "G", "B", "A")
    stats = {channel_names[i]: {"min": item[0], "max": item[1]} for i, item in enumerate(channels)}
    return {"width": width, "height": height, "mips": mips, "payload_bytes": len(data) - 128,
            "encoding": "A16B16G16R16_UNORM_CANDIDATE", "validated_full_mip_chain": True,
            "top_mip_channel_stats_u16": stats, "alpha_differs_from_r_texels": alpha_differs,
            "top_mip_texels": width * height}


def _safe_output_root(root: Path, game_root: Path):
    resolved_root = root.resolve()
    resolved_game = game_root.resolve(strict=True)
    require(not resolved_root.is_relative_to(resolved_game), "Output may not be inside the game installation")
    return resolved_root


def prepare(game_root: Path, output_root: Path):
    game_root = game_root.resolve(strict=True)
    require(game_root.is_dir(), "Game root must be a directory")
    output_root = _safe_output_root(output_root, game_root)
    csv_path = (game_root / CSV_RELATIVE).resolve(strict=True)
    pack_path = (game_root / PACK_RELATIVE).resolve(strict=True)
    require(csv_path.is_relative_to(game_root) and pack_path.is_relative_to(game_root),
            "Terrain inputs escaped the game root")
    csv_before, pack_before = sha256(csv_path), sha256(pack_path)
    rows = parse_terrain_csv(csv_path)
    pack = Fpk(pack_path)
    pack_entries = []
    package = bytearray(MAGIC + struct.pack("<II", VERSION, len(rows)))
    for row in rows:
        entry_name = row["diffuse"]
        require(entry_name.casefold() in pack.entries,
                f"Missing diffuse FPK entry for terrain {(row['continent'], row['material_id'])}: {entry_name}")
        data, provenance = pack.read(entry_name)
        dds_info = validate_dxt5_dds(data, entry_name)
        record = {**row, "entry": provenance["entry"], "fpk_offset": provenance["offset"],
                  "dds_bytes": provenance["bytes"], "dds_sha256": provenance["sha256"], **dds_info}
        pack_entries.append(record)
        package.extend(struct.pack("<III", row["continent"], row["material_id"], len(data)))
        package.extend(data)
        require(len(package) <= MAX_PACKAGE_BYTES, "Terrain package exceeds 128 MiB limit")
    piece_records = []
    package.extend(struct.pack("<I", len(HEIGHT_PIECES)))
    for kind, relative in HEIGHT_PIECES:
        source_path = (game_root / Path(relative)).resolve(strict=True)
        require(source_path.is_relative_to(game_root), f"Height asset escaped game root: {relative}")
        source_hash_before = sha256(source_path)
        data = source_path.read_bytes()
        require(hashlib.sha256(data).hexdigest() == source_hash_before,
                f"Height source changed while being read: {relative}")
        info = validate_height_dds(data, relative)
        package.extend(struct.pack("<II", kind, len(data)))
        package.extend(data)
        piece_records.append({"kind": kind, "source_path": str(source_path), "source_sha256_before": source_hash_before,
                              "source_sha256_payload": hashlib.sha256(data).hexdigest(),
                              "dds_bytes": len(data), **info})
        require(len(package) <= MAX_PACKAGE_BYTES, "Terrain package exceeds 128 MiB limit")
    package_hash = hashlib.sha256(package).hexdigest()
    package_dir = output_root / package_hash
    package_dir.mkdir(parents=True, exist_ok=True)
    package_path = package_dir / "terrain-assets.bin"
    if package_path.exists():
        require(package_path.is_file() and not package_path.is_symlink() and sha256(package_path) == package_hash,
                "Existing content-addressed package has unexpected bytes")
    else:
        with package_path.open("xb") as stream:
            stream.write(package)
        require(sha256(package_path) == package_hash, "Written package hash mismatch")
    csv_after, pack_after = sha256(csv_path), sha256(pack_path)
    for record in piece_records:
        record["source_sha256_after"] = sha256(Path(record["source_path"]))
    require(csv_before == csv_after and pack_before == pack_after and
            all(item["source_sha256_before"] == item["source_sha256_after"] == item["source_sha256_payload"]
                for item in piece_records), "Original terrain CSV, FPK, or height DDS changed during packaging")
    manifest = {
        "format": "ZEROSIS_CIV5_TERRAIN_DIFFUSE_PACKAGE_V1",
        "package": {"path": str(package_path.resolve()), "sha256": package_hash,
                    "bytes": len(package), "magic": MAGIC.decode("ascii"), "version": VERSION,
                    "material_count": len(rows), "ordering": "continent_then_material_id"},
        "inputs": {"terrain_csv": {"path": str(csv_path), "sha256_before": csv_before,
                                     "sha256_after": csv_after},
                   "terrain_fpk": {"path": str(pack_path), "sha256_before": pack_before,
                                   "sha256_after": pack_after, "entries": len(pack.entries)}},
        "originals_unchanged": csv_before == csv_after and pack_before == pack_after and
                               all(item["source_sha256_before"] == item["source_sha256_after"] == item["source_sha256_payload"]
                                   for item in piece_records),
        "records": pack_entries, "height_pieces": piece_records,
    }
    manifest_path = package_dir / "terrain-assets.manifest.json"
    payload = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    if manifest_path.exists():
        require(manifest_path.is_file() and not manifest_path.is_symlink() and
                manifest_path.read_text(encoding="utf-8") == payload,
                "Existing package manifest differs from current source evidence")
    else:
        with manifest_path.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
    return {"package_path": str(package_path.resolve()), "package_sha256": package_hash,
            "manifest_path": str(manifest_path.resolve()), "material_count": len(rows),
            "package_bytes": len(package), "originals_unchanged": True}
