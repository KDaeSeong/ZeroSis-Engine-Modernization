"""Filesystem-only boundaries for the private Host frozen-input reuse helper."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest import mock
import uuid


PROJECT = Path(__file__).resolve().parents[1]
BUILDER_PATH = PROJECT / "tools/build_ui_window_host.py"
EVIDENCE = PROJECT / "evidence/save_menu/20261013_original_screen/frozen_reuse"
BUILD_ID = "20261013T000000Z_aaaaaaaaaaaa"
PAYLOAD = b"independent frozen input v1\n"
sys.dont_write_bytecode = True


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


BUILDER_SHA_LOADED = sha(BUILDER_PATH)
sys.path.insert(0, str(PROJECT / "tools"))
spec = importlib.util.spec_from_file_location("frozen_reuse_builder_under_test", BUILDER_PATH)
assert spec and spec.loader
BUILDER = importlib.util.module_from_spec(spec)
spec.loader.exec_module(BUILDER)
if sha(BUILDER_PATH) != BUILDER_SHA_LOADED:
    raise RuntimeError("Builder changed while importing the filesystem-only helpers")


def identity(path: Path) -> tuple[int, int]:
    info = path.stat()
    return info.st_dev, info.st_ino


def receipt(path: Path) -> dict:
    info = path.stat()
    return {"identity": identity(path), "sha256": sha(path), "bytes": info.st_size,
            "mtime_ns": info.st_mtime_ns, "attributes": getattr(info, "st_file_attributes", 0),
            "mode": info.st_mode, "links": info.st_nlink}


class FrozenReuseTests(unittest.TestCase):
    def setUp(self):
        EVIDENCE.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="tiny_", dir=EVIDENCE)
        self.root = Path(self.temp.name)
        self.donor_root = self.root / "old/frozen"
        self.target_root = self.root / "new/frozen"
        self.donor_root.mkdir(parents=True)
        self.target_root.mkdir(parents=True)
        self.source = self.root / "Source/input.h"
        self.source.parent.mkdir()
        self.source.write_bytes(PAYLOAD)
        self.donor = self.donor_root / "include/input.h"
        self.donor.parent.mkdir()
        self.donor.write_bytes(PAYLOAD)
        os.utime(self.donor, ns=(1_700_000_000_000_000_000, 1_700_000_000_000_000_000))
        self.report = self.root / "old/build_result.json"
        self.write_report()
        self.guards = []
        for name in ("main", "run", "checked_run", "environment_for", "check_trade_route_lua_syntax"):
            patcher = mock.patch.object(BUILDER, name, side_effect=AssertionError("Execution is forbidden"))
            self.guards.append((patcher, patcher.start()))
        BUILDER.FROZEN_INPUT_REUSE = None

    def tearDown(self):
        BUILDER.FROZEN_INPUT_REUSE = None
        for patcher, guard in reversed(self.guards):
            try:
                guard.assert_not_called()
            finally:
                patcher.stop()
        # Every file/link is a tiny fixture created under this exact temporary root.
        self.temp.cleanup()
        self.assertFalse(self.root.exists())

    def write_report(self, donor=None, status="UI_WINDOW_HOST_CANDIDATE_BUILT", build_id=BUILD_ID):
        donor = donor or self.donor
        row = {"path": str(donor), "sha256": sha(donor), "bytes": donor.stat().st_size}
        report = {"status": status, "build_id": build_id, "compiler_inputs": [row]}
        self.report.write_text(json.dumps(report), encoding="utf-8")

    def enable(self):
        reuse = BUILDER.FrozenInputReuse(self.report, self.donor_root, self.target_root, BUILD_ID)
        BUILDER.FROZEN_INPUT_REUSE = reuse
        return reuse

    def assert_preserved(self, before, path, added_links=0):
        after = receipt(path)
        expected = dict(before, links=before["links"] + added_links)
        self.assertEqual(after, expected)

    def test_attested_readonly_donor_survives_mutable_source_edit(self):
        os.chmod(self.donor, stat.S_IREAD)
        before = receipt(self.donor)
        self.assertTrue(before["attributes"] & stat.FILE_ATTRIBUTE_READONLY)
        reuse = self.enable()
        target = self.target_root / "include/input.h"
        row = BUILDER.freeze_artifact(self.source, target)
        self.assertEqual(row["materialization"], "hardlink")
        self.assertEqual(row["reused_from_path"], str(self.donor))
        self.assertEqual(identity(self.donor), identity(target))
        self.assertNotEqual(identity(self.source), identity(target))
        self.assert_preserved(before, self.donor, added_links=1)
        self.source.write_bytes(b"new mutable source revision\n")
        self.assertEqual(target.read_bytes(), PAYLOAD)
        self.assert_preserved(before, self.donor, added_links=1)
        reuse.verify()
        self.assertTrue(reuse.summary["donor_content_and_metadata_preserved"])

    def test_changed_input_copies_then_same_build_duplicate_hardlinks(self):
        before = receipt(self.donor)
        self.source.write_bytes(b"changed input with new content\n")
        reuse = self.enable()
        first = self.target_root / "project/input.h"
        second = self.target_root / "include/input.h"
        first_row = BUILDER.freeze_artifact(self.source, first)
        first_before = receipt(first)
        second_row = BUILDER.freeze_artifact(self.source, second)
        self.assertEqual(first_row["materialization"], "copy")
        self.assertEqual(second_row["materialization"], "hardlink")
        self.assertEqual(second_row["reused_from_path"], str(first))
        self.assertNotEqual(identity(self.source), identity(first))
        self.assertNotEqual(identity(self.donor), identity(first))
        self.assertEqual(identity(first), identity(second))
        self.assert_preserved(first_before, first, added_links=1)
        self.assert_preserved(before, self.donor)
        reuse.verify()
        self.assertEqual(reuse.summary["copied_files"], 1)
        self.assertEqual(reuse.summary["hardlinked_files"], 1)

    def test_repeated_prior_reuse_counts_exact_links(self):
        before = receipt(self.donor)
        reuse = self.enable()
        for name in ("project/input.h", "include/input.h"):
            row = BUILDER.freeze_artifact(self.source, self.target_root / name)
            self.assertEqual(row["materialization"], "hardlink")
        self.assert_preserved(before, self.donor, added_links=2)
        reuse.verify()
        self.assertEqual(reuse.summary["hardlinked_files"], 2)
        self.assertEqual(reuse.summary["hardlinked_bytes"], 2 * len(PAYLOAD))

    def test_corrupted_matching_donor_is_rejected_and_preserved(self):
        self.enable()
        self.donor.write_bytes(b"X" * len(PAYLOAD))
        corrupted = receipt(self.donor)
        source_before = receipt(self.source)
        target = self.target_root / "corrupted.h"
        with self.assertRaises(RuntimeError):
            BUILDER.freeze_artifact(self.source, target)
        self.assertFalse(target.exists())
        self.assert_preserved(corrupted, self.donor)
        self.assert_preserved(source_before, self.source)

    def test_report_donor_outside_frozen_root_is_rejected(self):
        outside = self.root / "outside.h"
        outside.write_bytes(PAYLOAD)
        before = receipt(outside)
        self.write_report(donor=outside)
        with self.assertRaises((RuntimeError, ValueError)):
            self.enable()
        self.assert_preserved(before, outside)
        self.assertEqual(list(self.target_root.iterdir()), [])

    def test_donor_aliasing_mutable_source_is_rejected(self):
        self.donor.unlink()
        os.link(self.source, self.donor)
        self.write_report()
        before = receipt(self.source)
        self.enable()
        target = self.target_root / "alias.h"
        with self.assertRaises(RuntimeError):
            BUILDER.freeze_artifact(self.source, target)
        self.assertFalse(target.exists())
        self.assert_preserved(before, self.source)

    def test_existing_target_is_rejected_without_overwrite_or_link_change(self):
        before = receipt(self.donor)
        self.enable()
        target = self.target_root / "existing.h"
        target.write_bytes(b"existing target must survive\n")
        target_before = receipt(target)
        with self.assertRaises(RuntimeError):
            BUILDER.freeze_artifact(self.source, target)
        self.assert_preserved(target_before, target)
        self.assert_preserved(before, self.donor)

    def test_target_outside_new_frozen_root_is_rejected_before_creation(self):
        before = receipt(self.donor)
        self.enable()
        for target in (self.root / "outside/new.h", self.target_root / "../escaped.h"):
            with self.subTest(target=str(target)):
                with self.assertRaises((RuntimeError, ValueError)):
                    BUILDER.freeze_artifact(self.source, target)
                self.assertFalse(target.exists())
                self.assertFalse(target.parent.exists() if target.parent.name == "outside" else False)
        self.assert_preserved(before, self.donor)

    def test_unsuccessful_or_wrong_build_report_is_rejected(self):
        before = receipt(self.donor)
        for status, build_id in (("UI_WINDOW_HOST_BUILD_FAILED", BUILD_ID),
                                 ("UI_WINDOW_HOST_CANDIDATE_BUILT", "another_build")):
            with self.subTest(status=status, build_id=build_id):
                self.write_report(status=status, build_id=build_id)
                report_before = receipt(self.report)
                with self.assertRaises(RuntimeError):
                    self.enable()
                self.assert_preserved(report_before, self.report)
        self.assert_preserved(before, self.donor)

    def test_unaccounted_hardlink_increment_fails_final_verification(self):
        reuse = self.enable()
        BUILDER.freeze_artifact(self.source, self.target_root / "input.h")
        os.link(self.donor, self.root / "unaccounted.h")
        before = receipt(self.donor)
        with self.assertRaises(RuntimeError):
            reuse.verify()
        self.assert_preserved(before, self.donor)
        self.assertFalse(reuse.summary["donor_content_and_metadata_preserved"])

    def test_donor_mtime_drift_fails_final_verification(self):
        reuse = self.enable()
        BUILDER.freeze_artifact(self.source, self.target_root / "input.h")
        info = self.donor.stat()
        os.utime(self.donor, ns=(info.st_atime_ns, info.st_mtime_ns + 2_000_000_000))
        before = receipt(self.donor)
        with self.assertRaises(RuntimeError):
            reuse.verify()
        self.assert_preserved(before, self.donor)

    def test_success_report_drift_fails_final_verification(self):
        reuse = self.enable()
        BUILDER.freeze_artifact(self.source, self.target_root / "input.h")
        self.report.write_text(self.report.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        before = receipt(self.report)
        with self.assertRaises(RuntimeError):
            reuse.verify()
        self.assert_preserved(before, self.report)


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes.append({"test": test._testMethodName, "status": "PASS"})

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes.append({"test": test._testMethodName, "status": "FAIL", "error": str(err[1])})

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes.append({"test": test._testMethodName, "status": "ERROR", "error": str(err[1])})


if __name__ == "__main__":
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FrozenReuseTests)
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    builder_after = sha(BUILDER_PATH)
    passed = result.wasSuccessful() and builder_after == BUILDER_SHA_LOADED
    report = {"schema": "ZEROSIS_FROZEN_INPUT_REUSE_FILESYSTEM_TEST_V1",
              "status": "PASS" if passed else "FAIL_OR_BUILDER_CHANGED",
              "recorded_utc": datetime.now(timezone.utc).isoformat(),
              "builder_path": str(BUILDER_PATH), "builder_sha256_loaded": BUILDER_SHA_LOADED,
              "builder_sha256_after": builder_after, "builder_unchanged_during_tests": builder_after == BUILDER_SHA_LOADED,
              "test_path": str(Path(__file__).resolve()), "test_sha256": sha(Path(__file__)),
              "tests_run": result.testsRun, "failures": len(result.failures),
              "errors": len(result.errors), "skipped": len(result.skipped), "cases": result.outcomes,
              "scope": "tiny independent filesystem fixtures only; no builder main, compiler, window, SDK or GameCore execution",
              "temporary_fixture_cleanup_asserted_per_test": True}
    name = datetime.now(timezone.utc).strftime("result_%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8] + ".json"
    output = EVIDENCE / name
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "tests": result.testsRun,
                      "report": str(output), "report_sha256": sha(output)}, ensure_ascii=False))
    raise SystemExit(0 if passed else 1)
