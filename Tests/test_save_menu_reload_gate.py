"""Exercise the SaveMenu reload connection with tiny files and a mocked helper.

Only the production file-identity, SDK-sample and log-gate functions are loaded.
No native API, process, SDK, GameCore, SQLite or real save is used. These tests
prove the connection contract, not an actual game-byte restore or native run.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


ROOT = Path(__file__).absolute().parents[1]
EVIDENCE = ROOT / "evidence" / "save_menu" / "20261013_original_screen"
PROBE_SOURCE = EVIDENCE / "native" / "probe.py"
PROBE_BYTES = PROBE_SOURCE.read_bytes()
PROBE_SHA256 = hashlib.sha256(PROBE_BYTES).hexdigest()
SOURCE_TREE = ast.parse(PROBE_BYTES.decode("utf-8-sig"), filename=str(PROBE_SOURCE))
FUNCTION_NAMES = {
    "require", "ordinary", "digest", "artifact", "verify_reference",
    "compare_sdk_state", "inventory_archives",
}
SELECTED_FUNCTIONS = [
    node for node in SOURCE_TREE.body
    if isinstance(node, ast.FunctionDef) and node.name in FUNCTION_NAMES
]
if {node.name for node in SELECTED_FUNCTIONS} != FUNCTION_NAMES:
    raise RuntimeError("Production reload gate functions are missing or renamed")
PRODUCTION_CODE = compile(
    ast.Module(body=SELECTED_FUNCTIONS, type_ignores=[]), str(PROBE_SOURCE), "exec"
)
CLEANUP_RECEIPTS: list[dict] = []
SCOPE = "MOCKED_SAVEMENU_RELOAD_CONNECTION_ONLY; NO_NATIVE_SDK_OR_GAME_BYTE_PROOF"


def reference(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)}


class FakeLaunch:
    def __init__(self, session: Path, lines: list[str], row: dict | None = None):
        self.session = session
        self.lines = list(lines)
        self.row = {} if row is None else row

    def entries(self, prefix: str) -> list[str]:
        return [line[len(prefix):] for line in self.lines if line.startswith(prefix)]


class SaveMenuReloadGateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(
            prefix="tiny_save_reload_gate_", dir=EVIDENCE
        )
        self.fixture = Path(self.temporary.name).absolute()
        self.fixture_resolved = self.fixture.resolve(strict=True)
        self.evidence_resolved = EVIDENCE.resolve(strict=True)
        self.assertEqual(self.fixture_resolved.parent, self.evidence_resolved)
        self.assertTrue(self.fixture_resolved.name.startswith("tiny_save_reload_gate_"))
        self.addCleanup(self.clean_fixture)
        self.runtime = self.fixture / "runtime"
        first_session = self.runtime / "sessions" / "first-fixture"
        second_session = self.runtime / "sessions" / "second-fixture"
        first_session.mkdir(parents=True)
        second_session.mkdir()
        self.checkpoint = first_session / "named-fixture.zssave"
        self.restored = second_session / "play-restored-checkpoint.zssave"
        self.rules = first_session / "rules.db"
        self.localization = self.runtime / "localization.db"
        self.file_contents = {
            self.checkpoint: b"tiny mocked named archive\n",
            self.restored: b"tiny mocked pre-selection restored archive\n",
            self.rules: b"tiny mocked rules; not a database\n",
            self.localization: b"tiny mocked localization; not a database\n",
        }
        for path, contents in self.file_contents.items():
            path.write_bytes(contents)
        # A final archive is deliberately different and must never be sent to
        # the helper: post-load unit selection may change serialized fields.
        (second_session / "play-final-checkpoint.zssave").write_bytes(b"decoy final archive\n")
        self.sdk_bytes = (
            "G|sample\nM|sample\n" + "".join(f"P|{slot}\n" for slot in range(64))
            + "U|sample\nC|sample\nT|sample\n"
        ).encode("utf-8")
        (first_session / "play-final-state.txt").write_bytes(self.sdk_bytes)
        (second_session / "play-initial-state.txt").write_bytes(self.sdk_bytes)
        self.first = FakeLaunch(
            first_session, ["NEW_GAME_CONFIGURATION_VERIFIED", "LANGUAGE=ko_KR"],
            {"named_save": reference(self.checkpoint)},
        )
        self.second = FakeLaunch(second_session, [
            "INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=true",
            "INTERACTIVE_RESTORE_SECTIONS_EQUAL=132|133",
            "INTERACTIVE_RESTORE_SECTION_CHANGED=3|0",
            "LANGUAGE=ko_KR",
        ])
        self.helper_result = {
            "status": "CURRENT_ARCHIVE_GAME_RESTORE_METADATA_PASS",
            "changed_sections": [[3, 0]],
            "input_pair_game_byte_preservation_verified": True,
            "test_only_scope": SCOPE,
        }
        self.metadata = SimpleNamespace(SECTION_COUNT=133, verify_game_restore=None)
        self.namespace = {
            "Path": Path, "os": os, "hashlib": hashlib, "re": __import__("re"),
            "game_metadata": self.metadata, "ROOT": self.fixture,
            "ARCHIVE_EXTENSIONS": {".zssave", ".civ5save", ".civ5mpsave"},
        }
        # Imports, native class definitions, Launch and main are never loaded.
        exec(PRODUCTION_CODE, self.namespace)
        self.compare = self.namespace["compare_sdk_state"]
        self.spy_patch = mock.patch.object(
            self.metadata, "verify_game_restore", return_value=self.helper_result
        )
        self.spy = self.spy_patch.start()
        self.addCleanup(self.spy_patch.stop)

    def clean_fixture(self):
        path = Path(self.temporary.name).absolute()
        resolved = path.resolve(strict=True)
        if resolved != self.fixture_resolved or resolved.parent != self.evidence_resolved or \
                not resolved.name.startswith("tiny_save_reload_gate_"):
            raise RuntimeError("Refusing cleanup outside the exact owned tiny fixture")
        files = []
        for directory, subdirs, names in os.walk(resolved, followlinks=False):
            for name in subdirs:
                state = (Path(directory) / name).lstat()
                if getattr(state, "st_file_attributes", 0) & 0x400:
                    raise RuntimeError("Refusing cleanup through a fixture reparse directory")
            for name in names:
                item = Path(directory) / name
                state = item.lstat()
                if getattr(state, "st_file_attributes", 0) & 0x400:
                    raise RuntimeError("Refusing cleanup of a fixture reparse file")
                row = reference(item)
                files.append({"relative_path": str(item.relative_to(resolved)),
                              "bytes": row["bytes"], "sha256": row["sha256"]})
        files.sort(key=lambda row: row["relative_path"])
        receipt = {
            "path": str(resolved), "files": len(files),
            "removed_logical_bytes": sum(row["bytes"] for row in files),
            "file_inventory_sha256": hashlib.sha256(
                json.dumps(files, sort_keys=True, ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
        }
        shutil.rmtree(resolved)
        receipt["removed"] = not path.exists()
        CLEANUP_RECEIPTS.append(receipt)
        self.assertTrue(receipt["removed"])
        self.temporary.cleanup()

    def call_compare(self):
        return self.compare(self.first, self.second, runtime=self.runtime, language="ko_KR")

    def assert_rejected_before_helper(self, expression: str):
        self.spy.reset_mock()
        with self.assertRaisesRegex((RuntimeError, ValueError), expression):
            self.call_compare()
        self.spy.assert_not_called()

    def test_calls_exact_named_and_preselection_archives_with_bound_databases(self):
        result = self.call_compare()
        self.spy.assert_called_once_with(
            str(self.checkpoint), str(self.restored), rules_db_path=str(self.rules),
            localization_db_path=str(self.localization), language="ko_KR",
            configuration_verified=True, fixed_fixture=False,
        )
        self.assertIs(result["independent_reload_byte_check"], self.helper_result)
        self.assertEqual(result["named_checkpoint"], reference(self.checkpoint))
        self.assertEqual(result["restored_checkpoint"], reference(self.restored))
        self.assertEqual(result["source_rules_db"], reference(self.rules))
        self.assertEqual(result["localization_db"], reference(self.localization))
        self.assertEqual(result["sdk_snapshot_section_counts"],
                         {"G": 1, "M": 1, "P": 64, "U": 1, "C": 1, "T": 1})

    def test_sdk_sample_difference_rejects_before_metadata_call(self):
        (self.second.session / "play-initial-state.txt").write_bytes(self.sdk_bytes + b"G|extra\n")
        self.assert_rejected_before_helper("SDK snapshot differs")

    def test_incomplete_or_unknown_sdk_samples_reject_before_metadata_call(self):
        variants = [b"", self.sdk_bytes.replace(b"P|63\n", b""),
                    self.sdk_bytes.replace(b"U|sample\n", b""), self.sdk_bytes + b"X|unknown\n"]
        for data in variants:
            with self.subTest(data_bytes=len(data)):
                (self.first.session / "play-final-state.txt").write_bytes(data)
                (self.second.session / "play-initial-state.txt").write_bytes(data)
                self.assert_rejected_before_helper("SDK snapshot|SDK sections|section tag")

    def test_idle_and_section_markers_must_be_exact(self):
        original = list(self.second.lines)
        cases = [
            ("INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=", [], "idle boundary"),
            ("INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=", ["false"], "idle boundary"),
            ("INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=", ["true", "true"], "idle boundary"),
            ("INTERACTIVE_RESTORE_SECTIONS_EQUAL=", [], "identity check"),
            ("INTERACTIVE_RESTORE_SECTIONS_EQUAL=", ["132|133", "132|133"], "identity check"),
            ("INTERACTIVE_RESTORE_SECTIONS_EQUAL=", ["1|133"], "132 non-Game"),
            ("INTERACTIVE_RESTORE_SECTIONS_EQUAL=", ["133|133"], "132 non-Game"),
            ("INTERACTIVE_RESTORE_SECTIONS_EQUAL=", ["132|134"], "132 non-Game"),
            ("INTERACTIVE_RESTORE_SECTION_CHANGED=", [], "132 non-Game"),
            ("INTERACTIVE_RESTORE_SECTION_CHANGED=", ["3|1"], "132 non-Game"),
            ("INTERACTIVE_RESTORE_SECTION_CHANGED=", ["3|0", "6|0"], "132 non-Game"),
            ("INTERACTIVE_RESTORE_SECTION_CHANGED=", ["3|0", "3|0"], "132 non-Game"),
        ]
        for prefix, entries, message in cases:
            with self.subTest(prefix=prefix, entries=entries):
                self.second.lines = [line for line in original if not line.startswith(prefix)] + \
                    [prefix + entry for entry in entries]
                self.assert_rejected_before_helper(message)
        self.second.lines = original

    def test_configuration_marker_must_be_one_exact_standalone_line(self):
        for markers in ([], ["NEW_GAME_CONFIGURATION_VERIFIED"] * 2,
                        ["NEW_GAME_CONFIGURATION_VERIFIED=true"],
                        ["NEW_GAME_CONFIGURATION_VERIFIED_SUFFIX"]):
            with self.subTest(markers=markers):
                self.first.lines = ["LANGUAGE=ko_KR", *markers]
                self.assert_rejected_before_helper("exactly one verified")

    def test_both_host_language_markers_must_match_once(self):
        for target in (self.first, self.second):
            original = list(target.lines)
            for markers in ([], ["LANGUAGE=en_US"], ["LANGUAGE=ko_KR"] * 2):
                with self.subTest(source=target is self.first, markers=markers):
                    target.lines = [line for line in original if not line.startswith("LANGUAGE=")] + list(markers)
                    self.assert_rejected_before_helper("localization language")
            target.lines = original

    def test_named_archive_sha_cannot_change_before_helper_call(self):
        self.checkpoint.write_bytes(b"tampered tiny archive\n")
        self.assert_rejected_before_helper("Sealed artifact changed")

    def test_named_archive_must_be_directly_in_exact_source_session(self):
        escaped = self.runtime / "elsewhere-fixture.zssave"
        escaped.write_bytes(b"valid hash but wrong owning directory\n")
        self.first.row["named_save"] = reference(escaped)
        self.assert_rejected_before_helper("escaped its exact source session")

    def test_helper_pass_requires_current_pair_status_game_only_and_true_boolean(self):
        invalid_results = [
            {},
            {**self.helper_result, "status": "FIXTURE_GAME_RESTORE_METADATA_PASS"},
            {**self.helper_result, "changed_sections": [[3, 0], [6, 0]]},
            {**self.helper_result, "changed_sections": []},
            {**self.helper_result, "input_pair_game_byte_preservation_verified": False},
            {**self.helper_result, "input_pair_game_byte_preservation_verified": 1},
        ]
        for result in invalid_results:
            with self.subTest(result=result):
                self.spy.reset_mock()
                self.spy.return_value = result
                with self.assertRaisesRegex(RuntimeError, "Game-byte reload metadata check did not pass"):
                    self.call_compare()
                self.spy.assert_called_once()

    def test_independent_helper_exception_does_not_become_pass(self):
        self.spy.side_effect = RuntimeError("mock independent archive rejection")
        with self.assertRaisesRegex(RuntimeError, "mock independent archive rejection"):
            self.call_compare()
        self.spy.assert_called_once()

    def test_each_file_is_resealed_after_helper_returns(self):
        for path, original in self.file_contents.items():
            with self.subTest(file=path.name):
                self.spy.reset_mock()
                def mutate_and_return(*args, path=path, **kwargs):
                    path.write_bytes(path.read_bytes() + b"changed during mocked helper\n")
                    return self.helper_result
                self.spy.side_effect = mutate_and_return
                with self.assertRaisesRegex(RuntimeError, "Sealed artifact changed"):
                    self.call_compare()
                self.spy.assert_called_once()
                path.write_bytes(original)

    def test_inventory_walk_is_engine_only_without_user_game_global(self):
        engine_file = self.fixture / "tiny-engine-only.zssave"
        engine_file.write_bytes(b"engine inventory fixture\n")
        self.assertNotIn("USER_GAME", self.namespace)
        with mock.patch.object(os, "walk", return_value=[(str(self.fixture), [], [engine_file.name])]) as walk:
            result = self.namespace["inventory_archives"]()
        walk.assert_called_once_with(self.fixture, followlinks=False)
        self.assertEqual(result, {str(engine_file): reference(engine_file)})


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(SaveMenuReloadGateTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    unchanged = hashlib.sha256(PROBE_SOURCE.read_bytes()).hexdigest() == PROBE_SHA256
    cleanup_complete = len(CLEANUP_RECEIPTS) == result.testsRun and \
        all(row["removed"] for row in CLEANUP_RECEIPTS)
    passed = result.wasSuccessful() and unchanged and cleanup_complete
    print(json.dumps({
        "status": "SAVE_MENU_RELOAD_CONNECTION_TESTS_PASS" if passed else "SAVE_MENU_RELOAD_CONNECTION_TESTS_FAILED",
        "tests_run": result.testsRun, "scope": SCOPE,
        "probe_source": str(PROBE_SOURCE), "probe_source_sha256": PROBE_SHA256,
        "probe_source_unchanged": unchanged, "metadata_helper_was_mocked": True,
        "native_sdk_or_game_execution_performed": False,
        "all_owned_fixture_roots_removed": cleanup_complete,
        "removed_logical_bytes": sum(row["removed_logical_bytes"] for row in CLEANUP_RECEIPTS),
        "cleanup_receipts": CLEANUP_RECEIPTS,
    }, ensure_ascii=False, sort_keys=True), flush=True)
    raise SystemExit(0 if passed else 1)
