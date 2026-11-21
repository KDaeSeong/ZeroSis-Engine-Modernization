"""Build-only evidence boundaries without compiling or running native code."""
from __future__ import annotations

from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

import verify_bitmap_window as verifier


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BitmapWindowBuildOnlyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.native_test = self.start_patch(
            "run_owned_test", side_effect=AssertionError("Native execution is forbidden"))
        self.native_run = self.start_patch(
            "run", side_effect=AssertionError("Compiler subprocess execution is forbidden"))
        self.native_process = patch.object(
            verifier.subprocess, "Popen", side_effect=AssertionError("Subprocess launch is forbidden"))
        self.process_start = self.native_process.start()
        self.addCleanup(self.native_process.stop)
        dll_patch = patch.object(
            verifier.ctypes, "WinDLL", create=True,
            side_effect=AssertionError("Native DLL loading is forbidden"))
        self.dll_load = dll_patch.start()
        self.addCleanup(dll_patch.stop)

        self.fixture_base = PROJECT / "evidence/save_menu/20261013_original_screen"
        self.fixture_base = self.fixture_base.resolve(strict=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="tiny_bw_build_only_", dir=self.fixture_base)
        self.fixture = Path(self.temporary.name).resolve(strict=True)
        self.assertEqual(self.fixture.parent, self.fixture_base)
        self.addCleanup(self.cleanup_fixture)

        self.project = self.fixture / "source"
        self.project.mkdir()
        self.owned = {}
        for key, relative in {
            "renderer_header": "Source/Presentation/BitmapRenderer.h",
            "renderer": "Source/Presentation/BitmapRenderer.cpp",
            "window_header": "Source/Presentation/BitmapWindow.h",
            "editor_input_header": "Source/Presentation/BitmapEditorInput.h",
            "window": "Source/Presentation/BitmapWindow.cpp",
            "test": "Tests/bitmap_window.cpp",
            "verifier": "tools/verify_bitmap_window.py",
        }.items():
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((key + " fixture\n").encode())
            self.owned[key] = path
        self.source_hashes = {key: digest(path) for key, path in self.owned.items()}
        self.dependency = self.project / "shared.h"
        self.dependency.write_bytes(b"tiny shared dependency\n")
        self.library = self.project / "fixture.lib"
        self.library.write_bytes(b"tiny fixture library, not a native library\n")
        self.compiler = self.project / "compiler.txt"
        self.compiler.write_bytes(b"mock compiler, never executed\n")
        self.build = self.fixture / "build"
        self.evidence = self.fixture / "evidence"
        self.build.mkdir()
        self.evidence.mkdir()
        self.start_patch("PROJECT", self.project)
        self.start_patch("OWNED", self.owned)
        self.start_patch("allocate", return_value=("tiny-build-only", self.build, self.evidence))
        self.environment = self.start_patch(
            "environment_for", side_effect=lambda *_: (
                {"PATH": "fixture-only", "ZEROSIS_FOUND_VALUE_CPU_TRACE": "disabled"},
                str(self.compiler)))
        self.compile = self.start_patch("compile_binary", side_effect=self.fake_compile)

    def start_patch(self, name: str, *args, **kwargs):
        patcher = patch.object(verifier, name, *args, **kwargs)
        mocked = patcher.start()
        self.addCleanup(patcher.stop)
        return mocked

    def cleanup_fixture(self) -> None:
        resolved = self.fixture.resolve(strict=True)
        self.assertEqual(resolved.parent, self.fixture_base)
        self.assertTrue(resolved.name.startswith("tiny_bw_build_only_"))
        self.temporary.cleanup()
        self.assertFalse(resolved.exists())

    def tearDown(self) -> None:
        self.native_test.assert_not_called()
        self.native_run.assert_not_called()
        self.process_start.assert_not_called()
        self.dll_load.assert_not_called()

    def fake_compile(self, compiler, env, build, name, sources, optimization):
        self.assertEqual(compiler, str(self.compiler))
        self.assertNotIn("ZEROSIS_FOUND_VALUE_CPU_TRACE", env)
        self.assertEqual(optimization, "/" + build.name)
        executable = build / (name + ".exe")
        executable.write_bytes(b"mock build output, not a PE executable\n")
        return {
            "optimization": optimization,
            "compiler": compiler,
            "compiler_sha256": digest(self.compiler),
            "translation_units": [
                {"source": str(path), "source_sha256": digest(path),
                 "dependencies": [str(path), str(self.dependency)]}
                for path in sources
            ],
            "resolved_libraries": {
                self.library.name: {"path": str(self.library), "sha256": digest(self.library)}
            },
            "executable": str(executable),
            "executable_sha256": digest(executable),
        }, "mock build only\n"

    def run_build_only(self):
        output = io.StringIO()
        with patch.object(sys, "argv", ["verify_bitmap_window.py", "--build-only"]), redirect_stdout(output):
            code = verifier.main()
        report_path = self.evidence / "conformance.json"
        report = json.loads(report_path.read_text(encoding="utf-8"))
        receipt = json.loads(output.getvalue())
        self.assertEqual(receipt["status"], report["status"])
        self.assertEqual(receipt["report"], str(report_path))
        self.assertEqual(receipt["report_sha256"], digest(report_path))
        self.assertFalse(report_path.with_suffix(".json.tmp").exists())
        self.assertTrue(report["build_only_requested"])
        self.assertFalse(report["native_test_executed"])
        self.assertEqual(report["test_runs"], [])
        return code, report

    def test_build_only_retains_both_builds_and_seals_inputs_without_running(self) -> None:
        code, report = self.run_build_only()

        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "BITMAP_WINDOW_TEST_BINARIES_BUILT_NOT_EXECUTED")
        self.assertNotEqual(report["status"], "BITMAP_WINDOW_COMPONENT_PASS")
        self.assertIsNone(report["error"])
        self.assertEqual(report["native_checks_completed"], 0)
        self.assertEqual(report["expected_native_checks"], 234)
        self.assertFalse(report["native_window_acceptance_complete"])
        self.assertEqual(list(report["builds"]), ["O2", "Od"])
        self.assertEqual(self.compile.call_count, 2)
        self.assertEqual([call.args[-1] for call in self.compile.call_args_list], ["/O2", "/Od"])
        self.assertEqual(self.environment.call_count, 2)
        self.assertEqual(report["source_hashes_before"], self.source_hashes)
        self.assertEqual(report["source_hashes_after"], self.source_hashes)
        self.assertTrue(report["source_inputs_unchanged"])
        self.assertEqual(report["compiler_dependency_hashes_before"],
                         report["compiler_dependency_hashes_after"])
        self.assertEqual(report["source_dependency_count"], 4)
        self.assertEqual(len(report["compiler_dependencies"]), 4)
        for row in [*report["compiler_dependencies"], *report["resolved_libraries"].values()]:
            self.assertEqual(row["sha256"], digest(Path(row["original_path"])))
            self.assertEqual(row["frozen_sha256"], row["sha256"])
            self.assertEqual(digest(Path(row["frozen_path"])), row["sha256"])
            Path(row["frozen_path"]).resolve(strict=True).relative_to(self.build / "frozen")
        for row in report["frozen_inputs"].values():
            self.assertEqual(row["sha256"], digest(Path(row["path"])))
        for label, row in report["builds"].items():
            self.assertEqual(row["optimization"], "/" + label)
            self.assertEqual(row["executable_sha256"], digest(Path(row["executable"])))
            self.assertFalse((self.build / label / "test_inputs").exists())
        for field in ("gamecore_loaded", "sdk_linked", "wpr_capture_started", "stage_promoted",
                      "mods_written", "real_user_click_verified"):
            self.assertFalse(report[field], field)

    def test_failed_second_build_is_not_reported_as_built_or_passed(self) -> None:
        def fail_second(*args):
            if args[-1] == "/Od":
                raise RuntimeError("fixture Od compile failed")
            return self.fake_compile(*args)

        self.compile.side_effect = fail_second
        code, report = self.run_build_only()

        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "BITMAP_WINDOW_BUILD_FAILED")
        self.assertEqual(report["error"], "fixture Od compile failed")
        self.assertEqual(list(report["builds"]), ["O2"])
        self.assertEqual(self.compile.call_count, 2)
        self.assertNotIn("source_inputs_unchanged", report)

    def test_library_hash_mismatch_rejects_build_only_success(self) -> None:
        def invalid_library(*args):
            record, output = self.fake_compile(*args)
            record["resolved_libraries"][self.library.name]["sha256"] = "0" * 64
            return record, output

        self.compile.side_effect = invalid_library
        code, report = self.run_build_only()

        self.assertEqual(code, 1)
        self.assertEqual(report["status"], "BITMAP_WINDOW_BUILD_FAILED")
        self.assertIn("Frozen library differs", report["error"])
        self.assertEqual(list(report["builds"]), ["O2", "Od"])
        self.assertNotIn("source_inputs_unchanged", report)


if __name__ == "__main__":
    unittest.main()
