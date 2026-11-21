"""Filesystem tests for sealed reuse; these are not renderer or game tests."""
from pathlib import Path
import copy
import hashlib
import json
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import sealed_terrain_input as terrain


RUN = "20261020T110323Z_27da680b90f1"


class SealedTerrainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sealed-terrain-", dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name).resolve()
        self.runtime = self.project / "Build/InteractiveGameRuntime" / RUN
        self.runtime.mkdir(parents=True)
        self.payload = b"ZSTERR01" + struct.pack("<II", 1, 1) + b"synthetic package payload"
        self.sha = hashlib.sha256(self.payload).hexdigest()
        self.source = self.project / "Build/TerrainAssets" / self.sha / "terrain-assets.bin"
        self.source.parent.mkdir(parents=True)
        self.source.write_bytes(self.payload)
        self.runtime_package = self.runtime / "terrain-assets.bin"
        self.runtime_package.write_bytes(self.payload)
        self.manifest_path = self.source.with_name("terrain-assets.manifest.json")
        self.manifest = {"format": "ZEROSIS_CIV5_TERRAIN_DIFFUSE_PACKAGE_V1",
            "package": {"path": str(self.source), "bytes": len(self.payload), "sha256": self.sha,
                        "magic": "ZSTERR01", "version": 1, "material_count": 1,
                        "ordering": "continent_then_material_id"},
            "originals_unchanged": True, "records": [{}], "height_pieces": [{}] * 5,
            "inputs": {"original": {"path": "Z:/MUST_NOT_BE_OPENED/retail.fpk", "sha256": "0" * 64}}}
        self.request_path = self.project / "evidence/interactive_game" / RUN / "request.json"
        self.request_path.parent.mkdir(parents=True)
        self.request = {"run_id": RUN, "cwd": str(self.runtime),
            "runtime_inputs": [{"path": str(self.runtime_package), "source": str(self.source), "sha256": self.sha}],
            "terrain_assets": {"package": {"path": str(self.runtime_package), "sha256": self.sha},
                "preparer": {"original_path": str(self.project / "tools/civ5_terrain_assets.py"),
                             "bytes": 10, "sha256": "1" * 64}, "originals_unchanged": True}}
        self.save_manifest()

    def save_request(self):
        self.request_path.write_text(json.dumps(self.request), encoding="utf-8")

    def save_manifest(self):
        self.manifest_path.write_text(json.dumps(self.manifest), encoding="utf-8")
        self.request["terrain_assets"]["source_manifest"] = {
            "path": str(self.manifest_path), "sha256": hashlib.sha256(self.manifest_path.read_bytes()).hexdigest()}
        self.save_request()

    def validate(self):
        return terrain.validate_sealed_terrain(RUN, self.project)

    def test_valid_and_exact_return_shape_without_opening_original_refs(self):
        result = self.validate()
        self.assertEqual(set(result), {"package_source", "source_manifest", "preparer",
                                      "originals_unchanged", "reused_from_run", "source_request"})
        self.assertEqual(result["package_source"], self.source)
        self.assertEqual(result["source_manifest"]["bytes"], self.manifest_path.stat().st_size)
        self.assertEqual(result["source_request"]["sha256"], hashlib.sha256(self.request_path.read_bytes()).hexdigest())
        self.assertTrue(result["originals_unchanged"])
        self.assertFalse((self.project / "tools/civ5_terrain_assets.py").exists())

    def test_originals_unchanged_is_only_historical(self):
        self.manifest["originals_unchanged"] = False
        self.request["terrain_assets"]["originals_unchanged"] = False
        self.save_manifest()
        self.assertFalse(self.validate()["originals_unchanged"])

    def test_preparer_provenance_cannot_forward_unchecked_artifact_paths(self):
        self.request["terrain_assets"]["preparer"]["path"] = "Z:/MUST_NOT_BE_OPENED/retail.exe"
        self.save_request()
        self.assertEqual(set(self.validate()["preparer"]), {"original_path", "bytes", "sha256"})

    def test_bad_run_ids(self):
        for run in ("../escape", RUN + "/child", RUN + "\n", "", None):
            with self.subTest(run=run), self.assertRaises(RuntimeError):
                terrain.validate_sealed_terrain(run, self.project)

    def test_request_identity(self):
        for key, value in (("run_id", "20260101T000000Z_000000000000"),
                           ("cwd", str(self.project / "elsewhere"))):
            before = copy.deepcopy(self.request)
            self.request[key] = value
            self.save_request()
            with self.subTest(key=key), self.assertRaises(RuntimeError):
                self.validate()
            self.request = before

    def test_duplicate_terrain_input(self):
        self.request["runtime_inputs"].append(dict(self.request["runtime_inputs"][0]))
        self.save_request()
        with self.assertRaisesRegex(RuntimeError, "Exactly one"):
            self.validate()

    def test_package_path_escape(self):
        self.request["runtime_inputs"][0]["path"] = str(self.project / "terrain-assets.bin")
        self.save_request()
        with self.assertRaisesRegex(RuntimeError, "escaped"):
            self.validate()

    def test_manifest_path_escape(self):
        self.request["terrain_assets"]["source_manifest"]["path"] = "Z:/MUST_NOT_BE_OPENED/manifest.json"
        self.save_request()
        with self.assertRaisesRegex(RuntimeError, "escaped"):
            self.validate()

    def test_stale_cache_source_path(self):
        self.request["runtime_inputs"][0]["source"] = str(self.project / "old/terrain-assets.bin")
        self.save_request()
        with self.assertRaisesRegex(RuntimeError, "source escaped"):
            self.validate()

    def test_digest_mismatch(self):
        self.source.write_bytes(self.payload[:-1] + b"!")
        with self.assertRaisesRegex(RuntimeError, "digest"):
            self.validate()

    def test_stale_runtime_copy(self):
        self.runtime_package.write_bytes(self.payload + b"!")
        with self.assertRaisesRegex(RuntimeError, "digest|byte count"):
            self.validate()

    def test_stale_manifest_digest(self):
        self.manifest_path.write_text("{}", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "digest"):
            self.validate()

    def test_manifest_metadata(self):
        mutations = (("version", 2), ("version", True), ("material_count", 0),
                     ("material_count", 97), ("bytes", True), ("bytes", len(self.payload) + 1),
                     ("magic", "INVALID!"), ("ordering", "unknown"))
        original = copy.deepcopy(self.manifest)
        for key, value in mutations:
            self.manifest = copy.deepcopy(original)
            self.manifest["package"][key] = value
            self.save_manifest()
            with self.subTest(key=key, value=value), self.assertRaises(RuntimeError):
                self.validate()

    def test_header_matches_manifest_material_count(self):
        self.manifest["package"]["material_count"] = 2
        self.manifest["records"] = [{}, {}]
        self.save_manifest()
        with self.assertRaisesRegex(RuntimeError, "header"):
            self.validate()

    def test_changed_during_validation(self):
        original = terrain._artifact
        counts = {}
        def changed(path, maximum):
            result = original(path, maximum)
            counts[path] = counts.get(path, 0) + 1
            if path == self.source and counts[path] == 2:
                return {**result, "sha256": "0" * 64}
            return result
        with patch.object(terrain, "_artifact", changed), self.assertRaisesRegex(RuntimeError, "changed during"):
            self.validate()

    def test_malformed_digest_and_byte_types(self):
        original = copy.deepcopy(self.request)
        for field, value in (("sha256", 123), ("sha256", None), ("bytes", True), ("bytes", -1)):
            self.request = copy.deepcopy(original)
            self.request["runtime_inputs"][0][field] = value
            self.save_request()
            with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                self.validate()

    def test_original_observation_conflict(self):
        self.request["terrain_assets"]["originals_unchanged"] = False
        self.save_request()
        with self.assertRaisesRegex(RuntimeError, "Historical"):
            self.validate()

    def test_noncanonical_project(self):
        with self.assertRaisesRegex(RuntimeError, "absolute"):
            terrain.validate_sealed_terrain(RUN, Path("relative-project"))


class RetainedR11ReadOnlyTest(unittest.TestCase):
    def test_actual_r11_when_available(self):
        project = Path(__file__).resolve().parents[1]
        request = project / "evidence/interactive_game" / RUN / "request.json"
        if not request.is_file():
            self.skipTest("Retained private R11 fixture is absent")
        self.assertEqual(hashlib.sha256(request.read_bytes()).hexdigest(),
                         "7b04270096d0815c1ad682b3f99db2496b713db9cc7c5f5af05956d1744020f1")
        result = terrain.validate_sealed_terrain(RUN, project)
        self.assertEqual(result["source_manifest"]["sha256"],
                         "defaadf937ced6ed93fd0fb8046a532c6a39a89b02512866363de39642a21527")
        self.assertEqual(result["package_source"].parent.name,
                         "2bee85c22c77b0342896f827989ca7d6f4ca3ae8f4dfe3a2179faaab4d689b13")
        self.assertTrue(result["originals_unchanged"])


if __name__ == "__main__":
    unittest.main()
