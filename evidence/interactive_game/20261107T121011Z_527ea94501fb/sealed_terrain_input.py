"""Validate a retained private terrain input without consulting retail assets.

The manifest's original-input records and preparer annotation are historical
provenance, not files to reopen.  In particular, ``originals_unchanged`` in the
return value describes the prior packaging observation only.  This helper does
not revalidate the original installation, parse every texture, or execute code.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import struct


_RUN = re.compile(r"[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}\Z", re.ASCII)
_SHA = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_MAX_PACKAGE = 128 * 1024 * 1024
_MAX_JSON = 8 * 1024 * 1024


def _require(value, message):
    if not value:
        raise RuntimeError(message)


def _regular(path: Path):
    """Inspect only a lexically selected project path, never a manifest input."""
    _require(path.is_absolute() and ".." not in path.parts, "Noncanonical terrain input path")
    try:
        for item in (path, *path.parents):
            info = item.lstat()
            _require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                     "Terrain input contains a symlink or reparse point")
        info = path.stat()
        _require(stat.S_ISREG(info.st_mode), "Terrain input is not a regular file")
        _require(path.resolve(strict=True) == path, "Terrain input path is not canonical")
        return info
    except OSError as error:
        raise RuntimeError("Missing or unreadable sealed terrain input: " + str(path)) from error


def _identity(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _artifact(path: Path, maximum: int) -> dict:
    before = _regular(path)
    _require(0 < before.st_size <= maximum, "Sealed terrain input exceeds its byte bound")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        _require(_identity(os.fstat(stream.fileno())) == _identity(before), "Terrain input changed while opening")
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            _require(size <= maximum, "Sealed terrain input grew beyond its byte bound")
            digest.update(block)
    _require(_identity(before) == _identity(_regular(path)) and size == before.st_size,
             "Terrain input changed while hashing")
    return {"path": str(path), "bytes": size, "sha256": digest.hexdigest()}


def _object(path: Path) -> tuple[dict, dict]:
    reference = _artifact(path, _MAX_JSON)
    with path.open("rb") as stream:
        data = stream.read(_MAX_JSON + 1)
    _require(len(data) == reference["bytes"] and hashlib.sha256(data).hexdigest() == reference["sha256"],
             "Terrain JSON changed while reading")
    try:
        result = json.loads(data.decode("utf-8-sig"))
    except (UnicodeError, ValueError) as error:
        raise RuntimeError("Invalid sealed terrain JSON") from error
    _require(isinstance(result, dict), "Sealed terrain JSON must be an object")
    return result, reference


def _reference(row, expected: Path) -> dict:
    _require(isinstance(row, dict) and isinstance(row.get("path"), str) and
             Path(row["path"]) == expected and isinstance(row.get("sha256"), str) and
             _SHA.fullmatch(row["sha256"]),
             "Sealed terrain reference escaped its expected path or has an invalid digest")
    if "bytes" in row:
        _require(type(row["bytes"]) is int and row["bytes"] > 0, "Invalid terrain reference byte count")
    return row


def _matches(actual: dict, expected: dict):
    _require(actual["sha256"] == expected["sha256"] and
             ("bytes" not in expected or actual["bytes"] == expected["bytes"]),
             "Sealed terrain digest or byte count differs")


def validate_sealed_terrain(run_id: str, project: Path) -> dict:
    """Return a verified existing package from one exact private preparation.

    The caller authenticates the source request separately when it needs a
    particular approved baseline.  This function binds every terrain reference
    inside that request and never expands original-game provenance records.
    """
    _require(isinstance(run_id, str) and _RUN.fullmatch(run_id), "Invalid sealed terrain run ID")
    project = Path(project)
    _require(project.is_absolute() and ".." not in project.parts, "Project path must be absolute and canonical")
    runtime = project / "Build/InteractiveGameRuntime" / run_id
    request_path = project / "evidence/interactive_game" / run_id / "request.json"
    request, request_ref = _object(request_path)
    _require(request.get("run_id") == run_id and isinstance(request.get("cwd"), str) and
             Path(request["cwd"]) == runtime, "Sealed terrain request identity differs")
    rows = request.get("runtime_inputs")
    _require(isinstance(rows, list) and all(isinstance(row, dict) and isinstance(row.get("path"), str)
                                         for row in rows), "Invalid sealed terrain runtime inventory")
    terrain_rows = [row for row in rows if Path(row["path"]).name.casefold() == "terrain-assets.bin"]
    _require(len(terrain_rows) == 1, "Exactly one sealed terrain runtime input is required")
    runtime_path = runtime / "terrain-assets.bin"
    row = _reference(terrain_rows[0], runtime_path)
    terrain = request.get("terrain_assets")
    _require(isinstance(terrain, dict), "Sealed terrain record is missing")
    package_ref = _reference(terrain.get("package"), runtime_path)
    _require(row["sha256"] == package_ref["sha256"], "Request terrain package identities differ")
    source = project / "Build/TerrainAssets" / row["sha256"] / "terrain-assets.bin"
    _require(isinstance(row.get("source"), str) and Path(row["source"]) == source,
             "Sealed terrain source escaped its content-addressed cache")
    manifest_path = source.with_name("terrain-assets.manifest.json")
    manifest_ref = _reference(terrain.get("source_manifest"), manifest_path)
    manifest, observed_manifest = _object(manifest_path)
    _matches(observed_manifest, manifest_ref)
    _require(manifest.get("format") == "ZEROSIS_CIV5_TERRAIN_DIFFUSE_PACKAGE_V1",
             "Unsupported retained terrain manifest format")
    package = _reference(manifest.get("package"), source)
    _require(package["sha256"] == row["sha256"] and type(package.get("bytes")) is int and
             16 <= package["bytes"] <= _MAX_PACKAGE and package.get("magic") == "ZSTERR01" and
             type(package.get("version")) is int and package["version"] == 1 and
             type(package.get("material_count")) is int and 1 <= package["material_count"] <= 96 and
             package.get("ordering") == "continent_then_material_id", "Invalid retained terrain package metadata")
    _require(isinstance(manifest.get("records"), list) and
             len(manifest["records"]) == package["material_count"] and
             isinstance(manifest.get("height_pieces"), list) and len(manifest["height_pieces"]) == 5,
             "Retained terrain record counts differ")
    historical = terrain.get("originals_unchanged")
    _require(type(historical) is bool and type(manifest.get("originals_unchanged")) is bool and
             historical == manifest["originals_unchanged"], "Historical terrain observation differs")
    preparer = terrain.get("preparer")
    _require(isinstance(preparer, dict) and isinstance(preparer.get("original_path"), str) and
             Path(preparer["original_path"]) == project / "tools/civ5_terrain_assets.py" and
             isinstance(preparer.get("sha256"), str) and _SHA.fullmatch(preparer["sha256"]) and
             type(preparer.get("bytes")) is int and
             preparer["bytes"] > 0, "Invalid historical terrain preparer annotation")
    observed_source = _artifact(source, _MAX_PACKAGE)
    observed_runtime = _artifact(runtime_path, _MAX_PACKAGE)
    for expected in (package, row, package_ref):
        _matches(observed_source, expected)
        _matches(observed_runtime, expected)
    with source.open("rb") as stream:
        header = stream.read(16)
    _require(header == b"ZSTERR01" + struct.pack("<II", 1, package["material_count"]),
             "Retained terrain package header differs")
    for path, reference, maximum in ((request_path, request_ref, _MAX_JSON),
                                    (manifest_path, observed_manifest, _MAX_JSON),
                                    (source, observed_source, _MAX_PACKAGE),
                                    (runtime_path, observed_runtime, _MAX_PACKAGE)):
        _require(_artifact(path, maximum) == reference, "Sealed terrain input changed during validation")
    annotation = {key: preparer[key] for key in ("original_path", "bytes", "sha256")}
    return {"package_source": source, "source_manifest": observed_manifest, "preparer": annotation,
            "originals_unchanged": historical, "reused_from_run": run_id, "source_request": request_ref}
