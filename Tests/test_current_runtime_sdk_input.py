"""Static SDK input gates: malformed evidence, byte drift, and retained success."""
from __future__ import annotations

import copy
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import current_runtime_sdk_input as candidate


REPORT = PROJECT / "evidence/sdk_runtime_current/build_result.json"
REPORT_SHA = "dc7dd791816a870a1e6b55778b5f718ebf8f04418edf9e9a7eac5527f82bd303"


def artifact(path):
    raw = path.read_bytes()
    return dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())


def independent_pe():
    """One executable section with three ordinary lifecycle exports, no loader."""
    data = bytearray(2048)
    data[:2] = b"MZ"
    struct.pack_into("<I", data, 60, 128)
    data[128:132] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, 132, 0x8664, 1, 0, 0, 0, 240, 0x2022)
    optional = 152
    struct.pack_into("<H", data, optional, 0x20b)
    struct.pack_into("<Q", data, optional + 24, 0x180000000)
    struct.pack_into("<I", data, optional + 60, 512)
    struct.pack_into("<H", data, optional + 70, 0x140)
    struct.pack_into("<I", data, optional + 108, 16)
    struct.pack_into("<II", data, optional + 112, 0x1000, 0x200)
    section = optional + 240
    data[section:section + 5] = b".text"
    struct.pack_into("<IIII", data, section + 8, 1536, 0x1000, 1536, 512)
    struct.pack_into("<I", data, section + 36, 0x60000020)
    struct.pack_into("<IIIII", data, 512 + 20, 3, 3, 0x1040, 0x1050, 0x1060)
    struct.pack_into("<III", data, 576, 0x1400, 0x1410, 0x1420)
    struct.pack_into("<HHH", data, 608, 0, 1, 2)
    position = 640
    names = ("DllGetGameContext", "ZeroSisShutdownGameCore", "ZeroSisGetBootstrapError")
    for index, name in enumerate(names):
        encoded = name.encode("ascii") + b"\0"
        struct.pack_into("<I", data, 592 + 4 * index, 0x1000 + position - 512)
        data[position:position + len(encoded)] = encoded
        position += len(encoded)
    return data


class PeTests(unittest.TestCase):
    def test_independent_amd64_lifecycle_exports(self):
        self.assertEqual(candidate._pe(independent_pe()), {
            "DllGetGameContext": 0x1400, "ZeroSisShutdownGameCore": 0x1410,
            "ZeroSisGetBootstrapError": 0x1420})

    def test_machine_executable_kind_magic_and_export_errors(self):
        mutations = (
            (132, "<H", 0x14c),
            (150, "<H", 0x22),
            (152, "<H", 0x10b),
            (512 + 20, "<I", 4),
            (576, "<I", 0x1040),
            (592, "<I", 0x7fffffff),
            (608, "<H", 3),
            (610, "<H", 0),
        )
        for offset, codec, value in mutations:
            with self.subTest(offset=offset, value=value):
                data = independent_pe()
                struct.pack_into(codec, data, offset, value)
                with self.assertRaises(candidate.CurrentRuntimeSdkInputError):
                    candidate._pe(data)

    def test_missing_required_export_name(self):
        data = independent_pe()
        data[640] = ord("X")
        with self.assertRaises(candidate.CurrentRuntimeSdkInputError):
            candidate._pe(data)

    def test_truncated_pe(self):
        for length in (0, 63, 128, 151, 391, 511):
            with self.subTest(length=length), self.assertRaises(candidate.CurrentRuntimeSdkInputError):
                candidate._pe(independent_pe()[:length])


class ArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="sdk_input_", dir=PROJECT / "tests")
        self.root = Path(self.temp.name)
        self.project_patch = mock.patch.object(candidate, "PROJECT", self.root)
        self.project_patch.start()
        self.path = self.root / "small-input.bin"
        self.path.write_bytes(b"independent input\n")

    def tearDown(self):
        self.project_patch.stop()
        self.temp.cleanup()

    def test_exact_hash_and_size(self):
        row = artifact(self.path)
        self.assertEqual(candidate._Artifacts().verify(row), row)
        row["bytes"] += 1
        with self.assertRaises(candidate.CurrentRuntimeSdkInputError):
            candidate._Artifacts().verify(row)

    def test_byte_tamper_and_missing_artifact(self):
        row = artifact(self.path)
        self.path.write_bytes(b"independent INPUT\n")
        with self.assertRaises(candidate.CurrentRuntimeSdkInputError):
            candidate._Artifacts().verify(row)
        self.path.unlink()
        with self.assertRaises(OSError):
            candidate._Artifacts().verify(row)

    def test_changed_cached_artifact_is_rejected(self):
        files = candidate._Artifacts()
        files.verify(artifact(self.path))
        self.path.write_bytes(b"changed and longer\n")
        with self.assertRaises(candidate.CurrentRuntimeSdkInputError):
            files.finish()

    def test_path_escape_is_rejected_before_reading(self):
        row = artifact(self.path)
        row["path"] = str(self.root.parent / "unapproved-input.bin")
        with mock.patch.object(Path, "open", side_effect=AssertionError("Unexpected read")):
            with self.assertRaises(candidate.CurrentRuntimeSdkInputError):
                candidate._Artifacts().verify(row)

    def test_malformed_hash_is_rejected_before_reading(self):
        row = artifact(self.path)
        row["sha256"] = "not-a-sha"
        with mock.patch.object(Path, "open", side_effect=AssertionError("Unexpected read")):
            with self.assertRaises(candidate.CurrentRuntimeSdkInputError):
                candidate._Artifacts().verify(row)


class ImportAndBoundaryTests(unittest.TestCase):
    def test_import_has_no_input_reads_or_native_calls(self):
        path = PROJECT / "tools/current_runtime_sdk_input.py"
        spec = importlib.util.spec_from_file_location("pure_sdk_validator_import_test", path)
        loaded = importlib.util.module_from_spec(spec)
        denied = AssertionError("Import attempted input IO or native execution")
        with mock.patch.object(Path, "open", side_effect=denied), \
                mock.patch.object(Path, "read_bytes", side_effect=denied), \
                mock.patch.object(subprocess, "Popen", side_effect=denied), \
                mock.patch.object(ctypes, "CDLL", side_effect=denied), \
                mock.patch.object(os, "system", side_effect=denied):
            spec.loader.exec_module(loaded)
        self.assertTrue(callable(loaded.validate_current_runtime_sdk))

    def test_invalid_hash_and_report_path_fail_before_io(self):
        denied = AssertionError("Invalid boundary reached file IO")
        for path, sha in ((REPORT, ""), (REPORT, "A" * 64),
                          (PROJECT / "wrong.json", REPORT_SHA)):
            with self.subTest(path=path, sha=sha), \
                    mock.patch.object(candidate._Artifacts, "verify", side_effect=denied):
                with self.assertRaises(candidate.CurrentRuntimeSdkInputError):
                    candidate.validate_current_runtime_sdk(path, sha)


@unittest.skipUnless(REPORT.is_file(), "Retained current SDK evidence is unavailable")
class RetainedEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = REPORT.read_bytes()
        if hashlib.sha256(raw).hexdigest() != REPORT_SHA:
            raise AssertionError("Actual retained fixture no longer has its reviewed SHA-256")
        cls.build = json.loads(raw)

    def test_actual_current_report_static_validation(self):
        denied = AssertionError("Static validation attempted native execution")
        with mock.patch.object(subprocess, "Popen", side_effect=denied), \
                mock.patch.object(ctypes, "CDLL", side_effect=denied), \
                mock.patch.object(os, "system", side_effect=denied):
            validated = candidate.validate_current_runtime_sdk(REPORT, REPORT_SHA)
        self.assertEqual(set(validated), {"gamecore", "report", "validation", "shared_lua_dll"})
        self.assertEqual(validated["gamecore"]["sha256"],
                         "60984b68246d16bef42a4d0f5a159ae51104edb356a26c85ff917493279cbfe5")
        self.assertEqual(validated["shared_lua_dll"]["sha256"],
                         "4873cded3ddf52366abc7964e3d3e10546f88e983d966be93bce3465ef85d944")

    def test_incorrect_report_hash(self):
        with self.assertRaises(candidate.CurrentRuntimeSdkInputError):
            candidate.validate_current_runtime_sdk(REPORT, "0" * 64)

    def test_false_status_scope_and_dependency_claims(self):
        cases = (("status", "CURRENT_RUNTIME_SDK_OVERLAY_PREPARED_NOT_COMPILED"),
                 ("gamecore_loaded", True), ("runtime_updated", True),
                 ("full_engine_goal_complete", True), ("object_count", 164),
                 ("all_compiler_dependencies_prehashed", False),
                 ("shared_lua_import_library_substituted", False))
        for field, value in cases:
            build = copy.deepcopy(self.build)
            build[field] = value
            with self.subTest(field=field), self.assertRaises(candidate.CurrentRuntimeSdkInputError):
                candidate._report_shape(build)

    def test_wrong_language_role_and_unsealed_compile_are_rejected(self):
        for field, value in (("language_standard", "c++17"),
                             ("all_dependencies_prehashed", False),
                             ("returncode", 1), ("role", "historical_overlay")):
            build = copy.deepcopy(self.build)
            build["compiled_units"][0][field] = value
            with self.subTest(field=field), self.assertRaises(candidate.CurrentRuntimeSdkInputError):
                candidate._report_shape(build)

    def test_only_two_attested_metadata_paths_can_float(self):
        files = candidate._Artifacts()
        original = files.path
        metadata = {_key for _key in (
            candidate._key(PROJECT / "evidence/save_menu/20261013_original_screen/current_progress.json"),
            candidate._key(PROJECT / "docs/M7_RETAIL_SAVE_BOUNDARY.md"))}

        def forbid_live_metadata(path):
            if candidate._key(path) in metadata:
                raise AssertionError("Historical validation read live publication metadata")
            return original(path)

        with mock.patch.object(files, "path", side_effect=forbid_live_metadata):
            candidate._published_revisions(files, artifact(REPORT))
            self.assertEqual(set(files.revisions), metadata)
            for before, after in files.revisions.values():
                self.assertEqual(files.verify(before), after)
                self.assertEqual(files.verify(after), after)
                forged = dict(before, sha256="0" * 64)
                with self.assertRaises(candidate.CurrentRuntimeSdkInputError):
                    files.verify(forged)
            files.finish()


if __name__ == "__main__":
    unittest.main()
