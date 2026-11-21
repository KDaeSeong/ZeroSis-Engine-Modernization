"""Adversarial prepared-build validation using tiny, non-executable fixtures."""
from __future__ import annotations

from contextlib import redirect_stderr, redirect_stdout
import copy
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

import verify_bitmap_window as verifier


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class BitmapWindowPreparedBuildTests(unittest.TestCase):
    RUN_ID = "20261014T120000Z_0123456789ab"

    def setUp(self) -> None:
        self.forbidden = []
        for name in ("allocate", "environment_for", "compile_binary", "run_component_test", "run_owned_test", "run"):
            self.forbid(verifier, name)
        for name in ("Popen", "run"):
            self.forbid(verifier.subprocess, name)
        self.forbid(verifier.ctypes, "WinDLL", create=True)

        self.fixture_base = (PROJECT / "evidence/save_menu/20261013_original_screen").resolve(strict=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="tiny_bw_prepared_", dir=self.fixture_base)
        self.fixture = Path(self.temporary.name).resolve(strict=True)
        self.assertEqual(self.fixture.parent, self.fixture_base)
        self.addCleanup(self.cleanup_fixture)
        self.project = self.fixture / "p"
        self.build = self.project / "Build/BitmapWindow" / self.RUN_ID
        self.frozen = self.build / "frozen"
        self.report_path = self.project / "evidence/bitmap_window" / self.RUN_ID / "conformance.json"
        self.owned = {}
        self.frozen_inputs = {}
        for key, relative in {
            "renderer_header": "Source/Presentation/BitmapRenderer.h",
            "renderer": "Source/Presentation/BitmapRenderer.cpp",
            "window_header": "Source/Presentation/BitmapWindow.h",
            "editor_input_header": "Source/Presentation/BitmapEditorInput.h",
            "window": "Source/Presentation/BitmapWindow.cpp",
            "test": "Tests/bitmap_window.cpp",
            "verifier": "tools/verify_bitmap_window.py",
        }.items():
            content = (key + " fixture\n").encode()
            current = self.write(self.project / relative, content)
            frozen = self.write(self.frozen / relative, content)
            self.owned[key] = current
            self.frozen_inputs[key] = {"path": str(frozen), "sha256": digest(frozen)}
        self.compiler = self.write(self.project / "compiler.txt", b"mock compiler, never run\n")
        self.linker = self.write(self.project / "linker.txt", b"mock linker, never run\n")
        self.dependency = self.write(self.project / "shared.h", b"tiny external header\n")
        self.frozen_dependency = self.write(self.frozen / "dependencies/shared.h", self.dependency.read_bytes())

        self.library_rows = {}
        for name in verifier.LIBRARIES:
            content = ("not a native library: " + name + "\n").encode()
            original = self.write(self.project / "libraries" / name, content)
            frozen = self.write(self.frozen / "libraries" / name, content)
            self.library_rows[name] = {
                "original_path": str(original), "sha256": digest(original),
                "frozen_path": str(frozen), "frozen_sha256": digest(frozen),
            }

        dependency_paths = [Path(self.frozen_inputs[key]["path"]) for key in
                            ("test", "window", "renderer", "renderer_header", "window_header", "editor_input_header")]
        dependency_paths.append(self.dependency)
        dependencies = [{"original_path": str(path), "sha256": digest(path),
                         "frozen_path": str(self.frozen_dependency if path == self.dependency else path),
                         "frozen_sha256": digest(self.frozen_dependency if path == self.dependency else path)}
                        for path in dependency_paths]
        self.report = {
            "schema": "zerosis.bitmap_window_conformance.v1", "run_id": self.RUN_ID,
            "status": "BITMAP_WINDOW_TEST_BINARIES_BUILT_NOT_EXECUTED",
            "build_only_requested": True, "native_test_executed": False, "test_runs": [],
            "native_checks_completed": 0, "expected_native_checks": 234,
            "native_window_acceptance_complete": False, "source_inputs_unchanged": True,
            "source_hashes_before": {key: digest(path) for key, path in self.owned.items()},
            "source_hashes_after": {key: digest(path) for key, path in self.owned.items()},
            "frozen_inputs": self.frozen_inputs,
            "compiler_dependencies": dependencies,
            "compiler_dependency_hashes_before": {row["original_path"]: row["sha256"] for row in dependencies},
            "compiler_dependency_hashes_after": {row["original_path"]: row["sha256"] for row in dependencies},
            "source_dependency_count": len(dependencies), "resolved_libraries": self.library_rows,
            "builds": {label: self.make_build(label) for label in ("O2", "Od")}, "error": None,
            "gamecore_loaded": False, "sdk_linked": False, "wpr_capture_started": False,
            "stage_promoted": False, "mods_written": False, "real_user_click_verified": False,
        }
        self.expected_sha = self.save_report()
        self.patch_value("PROJECT", self.project)
        self.patch_value("OWNED", self.owned)

    def write(self, path: Path, content: bytes) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path

    def forbid(self, owner, name: str, **kwargs) -> None:
        patcher = patch.object(owner, name, side_effect=AssertionError(name + " must not be called"), **kwargs)
        self.forbidden.append((name, patcher.start()))
        self.addCleanup(patcher.stop)

    def patch_value(self, name: str, value) -> None:
        patcher = patch.object(verifier, name, value)
        patcher.start()
        self.addCleanup(patcher.stop)

    def cleanup_fixture(self) -> None:
        resolved = self.fixture.resolve(strict=True)
        self.assertEqual(resolved.parent, self.fixture_base)
        self.assertTrue(resolved.name.startswith("tiny_bw_prepared_"))
        self.temporary.cleanup()
        self.assertFalse(resolved.exists())

    def tearDown(self) -> None:
        for name, mocked in self.forbidden:
            with self.subTest(forbidden_call=name):
                mocked.assert_not_called()

    def make_build(self, label: str) -> dict:
        directory = self.build / label
        directory.mkdir(parents=True)
        executable = self.write(directory / ("bitmap_window_" + label + ".exe"),
                                ("not a PE executable: " + label + "\n").encode())
        units = []
        for index, key in enumerate(("test", "window", "renderer")):
            source = Path(self.frozen_inputs[key]["path"])
            prefix = directory / ("bitmap_window_" + label + "_" + str(index))
            response = self.write(prefix.with_suffix(".rsp"), b"mock compile arguments\n")
            obj = self.write(prefix.with_suffix(".obj"), b"not a native object\n")
            included = [Path(self.frozen_inputs[name]["path"]) for name in
                        ("renderer_header", "window_header", "editor_input_header")]
            included.append(self.dependency)
            document = self.write(prefix.with_suffix(".sourceDependencies.json"),
                                  json.dumps({"Data": {"Source": str(source),
                                                       "Includes": [str(path) for path in included]}}).encode())
            log = self.write(prefix.with_suffix(".compile.log"), b"mock compile log\n")
            units.append({
                "source": str(source), "source_sha256": digest(source),
                "response": str(response), "response_sha256": digest(response),
                "object": str(obj), "object_sha256": digest(obj),
                "dependency_document": str(document), "dependency_document_sha256": digest(document),
                "compile_log": str(log), "compile_log_sha256": digest(log),
                "dependencies": [str(source), *[str(path) for path in included]],
                "arguments": ["/" + label, "/WX", "/DZEROSIS_BITMAP_WINDOW_DIAGNOSTICS", "/c", str(source)],
            })
        link_arguments = ["/MACHINE:X64", "/WX", '/OUT:"' + str(executable) + '"', *verifier.LIBRARIES]
        response = self.write(directory / ("bitmap_window_" + label + ".link.rsp"),
                              ("\n".join(link_arguments) + "\n").encode())
        log = self.write(directory / ("bitmap_window_" + label + ".link.log"), b"mock link log\n")
        return {
            "optimization": "/" + label, "compiler": str(self.compiler), "compiler_sha256": digest(self.compiler),
            "linker": str(self.linker), "linker_sha256": digest(self.linker),
            "translation_units": units, "link_arguments": link_arguments,
            "link_response": str(response), "link_response_sha256": digest(response),
            "link_log": str(log), "link_log_sha256": digest(log),
            "resolved_libraries": {name: {"path": row["original_path"], "sha256": row["sha256"]}
                                   for name, row in self.library_rows.items()},
            "executable": str(executable), "executable_sha256": digest(executable),
        }

    def save_report(self) -> str:
        self.write(self.report_path, (json.dumps(self.report, sort_keys=True, indent=2) + "\n").encode())
        return digest(self.report_path)

    def run_validate_only(self, *, run_id=None, expected_sha=None):
        output = io.StringIO()
        arguments = ["verify_bitmap_window.py", "--prepared-build", self.RUN_ID if run_id is None else run_id,
                     "--build-report-sha256", self.expected_sha if expected_sha is None else expected_sha,
                     "--validate-only"]
        with patch.object(sys, "argv", arguments), redirect_stdout(output):
            code = verifier.main()
        receipt = json.loads(output.getvalue())
        self.assertFalse(receipt.get("native_test_executed", False))
        return code, receipt

    def assert_rejected(self, **arguments) -> None:
        code, receipt = self.run_validate_only(**arguments)
        self.assertEqual(code, 1)
        self.assertEqual(receipt["status"], "BITMAP_WINDOW_PREPARED_BUILD_REJECTED")
        self.assertTrue(receipt["error"])

    def file_state(self) -> dict:
        return {str(path): (path.stat().st_size, path.stat().st_mtime_ns, digest(path))
                for path in self.fixture.rglob("*") if path.is_file()}

    def test_validate_only_checks_exact_prepared_bundle_without_writes_or_execution(self) -> None:
        before = self.file_state()
        proof = verifier.validate_prepared_build(self.RUN_ID, self.expected_sha)
        self.assertEqual(proof["run_id"], self.RUN_ID)
        self.assertEqual(proof["report"], str(self.report_path))
        self.assertEqual(proof["report_sha256"], self.expected_sha)
        self.assertEqual(proof["build_root"], str(self.build))
        self.assertEqual(proof["conformance"], self.report)
        self.assertGreater(proof["checked_file_count"], 0)
        self.assertTrue(proof["current_component_sources_match"])
        self.assertFalse(proof["verifier_changed_since_build"])

        code, receipt = self.run_validate_only()
        self.assertEqual(code, 0)
        self.assertEqual(receipt["status"], "BITMAP_WINDOW_PREPARED_BUILD_VALIDATED_NOT_EXECUTED")
        self.assertFalse(receipt["native_test_executed"])
        self.assertEqual(receipt["native_checks_completed"], 0)
        self.assertEqual(receipt["expected_native_checks"], 234)
        self.assertEqual(receipt["report_sha256"], self.expected_sha)
        self.assertEqual(receipt["run_id"], self.RUN_ID)
        self.assertEqual(self.file_state(), before)

    def test_exact_report_bytes_and_supplied_sha_are_required(self) -> None:
        self.assert_rejected(expected_sha="0" * 64)
        self.report_path.write_bytes(self.report_path.read_bytes() + b" \n")
        self.assert_rejected()

    def test_empty_options_cannot_fall_back_to_default_native_execution(self) -> None:
        for run_id, report_sha in (("", self.expected_sha), (self.RUN_ID, "")):
            with self.subTest(run_id=run_id, report_sha=report_sha):
                output = io.StringIO()
                arguments = ["verify_bitmap_window.py", "--prepared-build", run_id,
                             "--build-report-sha256", report_sha]
                with patch.object(sys, "argv", arguments), redirect_stdout(output):
                    code = verifier.main()
                receipt = json.loads(output.getvalue())
                self.assertEqual(code, 1)
                self.assertEqual(receipt["status"], "BITMAP_WINDOW_PREPARED_BUILD_REJECTED")
                self.assertFalse(receipt["native_test_executed"])
                self.assertTrue(receipt["error"])

        output, errors = io.StringIO(), io.StringIO()
        arguments = ["verify_bitmap_window.py", "--build-report-sha256", ""]
        with patch.object(sys, "argv", arguments), redirect_stdout(output), redirect_stderr(errors):
            with self.assertRaises(SystemExit) as rejected:
                verifier.main()
        self.assertEqual(rejected.exception.code, 2)
        self.assertEqual(output.getvalue(), "")
        self.assertIn("require --prepared-build", errors.getvalue())

    def test_valid_run_id_must_match_report_and_actual_directory(self) -> None:
        for run_id in ("../" + self.RUN_ID, "not-an-id"):
            with self.subTest(run_id=run_id):
                self.assert_rejected(run_id=run_id)
        self.report["run_id"] = "20261014T120000Z_abcdef012345"
        self.expected_sha = self.save_report()
        self.assert_rejected()

    def test_both_executable_hashes_are_checked(self) -> None:
        for label, record in self.report["builds"].items():
            with self.subTest(optimization=label):
                path = Path(record["executable"])
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"changed\n")
                    self.assert_rejected()
                finally:
                    path.write_bytes(original)

    def test_all_frozen_input_dependency_and_library_hashes_are_checked(self) -> None:
        artifacts = [("owned:" + key, Path(row["path"])) for key, row in self.frozen_inputs.items()]
        artifacts.append(("external-dependency", self.frozen_dependency))
        artifacts.extend(("library:" + key, Path(row["frozen_path"])) for key, row in self.library_rows.items())
        for name, path in artifacts:
            with self.subTest(artifact=name):
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"changed\n")
                    self.assert_rejected()
                finally:
                    path.write_bytes(original)

    def test_translation_unit_and_link_metadata_hashes_are_checked(self) -> None:
        artifacts = []
        for label, record in self.report["builds"].items():
            for index, unit in enumerate(record["translation_units"]):
                artifacts.extend((f"{label}:{index}:{key}", Path(unit[key])) for key in
                                 ("response", "object", "dependency_document", "compile_log"))
            artifacts.extend((label + ":" + key, Path(record[key])) for key in ("link_response", "link_log"))
        for name, path in artifacts:
            with self.subTest(artifact=name):
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b"changed\n")
                    self.assert_rejected()
                finally:
                    path.write_bytes(original)

    def test_current_component_source_change_is_rejected(self) -> None:
        self.owned["window"].write_bytes(b"changed current window source\n")
        self.assert_rejected()

    def test_only_current_verifier_change_is_allowed_and_reported(self) -> None:
        self.owned["verifier"].write_bytes(b"changed current verifier\n")
        proof = verifier.validate_prepared_build(self.RUN_ID, self.expected_sha)
        self.assertTrue(proof["current_component_sources_match"])
        self.assertTrue(proof["verifier_changed_since_build"])
        code, receipt = self.run_validate_only()
        self.assertEqual(code, 0)
        self.assertEqual(receipt["status"], "BITMAP_WINDOW_PREPARED_BUILD_VALIDATED_NOT_EXECUTED")

    def test_reparse_file_attribute_is_rejected(self) -> None:
        original_lstat = Path.lstat

        def reparse_stat(path, *args, **kwargs):
            info = original_lstat(path, *args, **kwargs)
            if path == self.frozen_dependency:
                return SimpleNamespace(st_file_attributes=getattr(info, "st_file_attributes", 0) | 0x400,
                                       st_mode=info.st_mode)
            return info

        with patch.object(Path, "lstat", autospec=True, side_effect=reparse_stat):
            code, receipt = self.run_validate_only()
        self.assertEqual(code, 1)
        self.assertEqual(receipt["status"], "BITMAP_WINDOW_PREPARED_BUILD_REJECTED")
        self.assertIn("reparse", receipt["error"])

    def test_manifest_scope_dependency_closure_and_library_keys_are_required(self) -> None:
        original = copy.deepcopy(self.report)
        changes = ("outside-frozen-input", "outside-executable", "missing-dependency", "missing-library", "wrong-machine")
        for name in changes:
            with self.subTest(change=name):
                self.report = copy.deepcopy(original)
                if name == "outside-frozen-input":
                    self.report["frozen_inputs"]["renderer_header"]["path"] = str(self.owned["renderer_header"])
                elif name == "outside-executable":
                    self.report["builds"]["O2"].update(executable=str(self.compiler), executable_sha256=digest(self.compiler))
                elif name == "missing-dependency":
                    self.report["compiler_dependencies"] = [row for row in self.report["compiler_dependencies"]
                                                            if row["original_path"] != str(self.dependency)]
                    self.report["source_dependency_count"] -= 1
                    for field in ("compiler_dependency_hashes_before", "compiler_dependency_hashes_after"):
                        self.report[field].pop(str(self.dependency))
                elif name == "missing-library":
                    self.report["resolved_libraries"].pop(verifier.LIBRARIES[0])
                elif name == "wrong-machine":
                    self.report["builds"]["Od"]["link_arguments"][0] = "/MACHINE:X86"
                self.expected_sha = self.save_report()
                self.assert_rejected()


if __name__ == "__main__":
    unittest.main()
