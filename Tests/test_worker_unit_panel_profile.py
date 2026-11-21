"""Synthetic reuse/read boundaries only; no Host execution or native-play claim."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS.parent / "tools"))
import run_interactive_game as runner
import verify_interactive_decisions as verifier


def load_fixture(name, function="fixture"):
    spec = importlib.util.spec_from_file_location("worker_profile_" + name, TESTS / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, function)


hud_fixture = load_fixture("action_info_panel_timeline")
worker_hud_fixture = load_fixture("action_info_panel_timeline", "worker_fixture")
notification_fixture = load_fixture("notification_panel_timeline")
RUN = "20261010T000000Z_000000000001"
SOURCE = "20261009T000000Z_000000000001"
CAPABILITY = "INTERACTIVE_ORIGINAL_UNIT_PANEL_CONTRACT=1\n"
REQUEST_FLAGS = ("smoke", "decisions", "research_tree", "unit_actions", "worker_build",
                 "top_panel", "action_info_panel", "notification_panel")
RESULT_FLAGS = ("worker_build_requested", "worker_build_sequence_verified", "unit_actions_requested",
                "unit_action_sequence_verified", "unit_action_evidence_verified",
                "decision_ui_smoke_requested", "decision_ui_sequence_verified", "research_tree_requested",
                "research_tree_sequence_verified", "action_info_panel_requested",
                "action_info_panel_sequence_verified", "action_info_panel_dispatch_verified",
                "notification_panel_requested", "notification_panel_sequence_verified",
                "notification_panel_native_sequence_verified", "original_unit_panel_contract_required",
                "original_unit_panel_integration_verified", "native_window_posted_input_verified",
                "runtime_inputs_unchanged")


def profile(restored=False):
    request = {name: True for name in REQUEST_FLAGS}
    request.update(run_id=RUN, input_profile="POSTED_HWND_CONTINUOUS_TREE_DECISION_UI_LOOP",
                   stage_or_mods_changed=False, resume_from={"run_id": SOURCE} if restored else None)
    result = {name: True for name in RESULT_FLAGS}
    result.update(status="CONTINUOUS_INTERACTIVE_SDK_WORKER_BUILD_" +
                  ("RESTORE_SMOKE_PASS" if restored else "SMOKE_PASS"), run_id=RUN,
                  returncode=0, timed_out=False, failures=[], stage_or_mods_changed=False,
                  driver_pid=123, original_unit_panel_integration_failure=None,
                  original_unit_panel_integration={"contract_version": 1,
                      "initial": {"scope": "restore" if restored else "fresh"}},
                  resume_from_run=SOURCE if restored else None,
                  fresh_process_restore_verified=restored, checkpoint_input_unchanged=True,
                  semantic_restore_equal=True, notification_panel_input_verified=not restored,
                  notification_panel_verification_scope="RESTORED_SDK_LIST_PRESENTATION" if restored else
                  "FRESH_INPUT_AND_SDK_REMOVAL")
    text = CAPABILITY + worker_hud_fixture(restored) + notification_fixture(restored)
    return request, result, text


class WorkerProfile(unittest.TestCase):
    def test_exact_fresh_restore(self):
        for restored in (False, True):
            self.assertTrue(verifier.verify_original_unit_panel_worker_profile(*profile(restored)))

    def test_each_required_boolean_is_strict(self):
        for container, names in ((0, REQUEST_FLAGS), (1, RESULT_FLAGS)):
            for name in names:
                for value in (None, False, 1, "true"):
                    values = list(profile()); values[container][name] = value
                    with self.subTest(name=name, value=value), self.assertRaises(RuntimeError):
                        verifier.verify_original_unit_panel_worker_profile(*values)

    def test_version_and_exact_native_capability(self):
        for version in (None, 0, 2, True, "1"):
            request, result, text = profile()
            result["original_unit_panel_integration"]["contract_version"] = version
            with self.subTest(version=version), self.assertRaises(RuntimeError):
                verifier.verify_original_unit_panel_worker_profile(request, result, text)
        for replacement in ("", CAPABILITY * 2, CAPABILITY.replace("=1", "=2"), CAPABILITY + "INTERACTIVE_ORIGINAL_UNIT_PANEL_CONTRACT=garbage\n"):
            request, result, text = profile()
            with self.subTest(marker=replacement), self.assertRaises(RuntimeError):
                verifier.verify_original_unit_panel_worker_profile(request, result, text.replace(CAPABILITY, replacement))

    def test_fresh_restore_and_notification_scope_cannot_mix(self):
        for restored in (False, True):
            for change in ("initial", "resume_id", "notification_input", "notification_scope", "restore_verified"):
                request, result, text = profile(restored)
                if change == "initial": result["original_unit_panel_integration"]["initial"]["scope"] = "fresh" if restored else "restore"
                if change == "resume_id": result["resume_from_run"] = "invalid"
                if change == "notification_input": result["notification_panel_input_verified"] = restored
                if change == "notification_scope": result["notification_panel_verification_scope"] = "unknown"
                if change == "restore_verified": result["fresh_process_restore_verified"] = not restored
                with self.subTest(restored=restored, change=change), self.assertRaises(RuntimeError):
                    verifier.verify_original_unit_panel_worker_profile(request, result, text)

    def test_mixed_profile_failed_metadata_and_missing_timeline(self):
        for field, value in (("input_profile", "POSTED_HWND_ORIGINAL_GAME_MENU_SMOKE"),
                             ("game_menu_smoke", True), ("combat_smoke", True)):
            request, result, text = profile(); request[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                verifier.verify_original_unit_panel_worker_profile(request, result, text)
        for field, value in (("returncode", 1), ("returncode", False), ("timed_out", True),
                             ("failures", ["failed"]), ("original_unit_panel_integration_failure", "bad")):
            request, result, text = profile(); result[field] = value
            with self.subTest(field=field), self.assertRaises(RuntimeError):
                verifier.verify_original_unit_panel_worker_profile(request, result, text)
        for marker in ("INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE=1", "INTERACTIVE_NOTIFICATION_PANEL_SMOKE_COMPLETE=FRESH_INPUT_AND_SDK_REMOVAL"):
            request, result, text = profile()
            with self.subTest(marker=marker), self.assertRaises(RuntimeError):
                verifier.verify_original_unit_panel_worker_profile(request, result, text.replace(marker, "MISSING"))


class WorkerReadAndReuse(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="zerosis-worker-reuse-contract-", dir=TESTS)
        self.root = Path(self.directory.name).resolve(strict=True)
        self.assertEqual(self.root.parent, TESTS)
        self.addCleanup(self.directory.cleanup)
        self.evidence = self.root / "evidence/interactive_game" / RUN
        self.runtime = self.root / "Build/InteractiveGameRuntime" / RUN
        self.evidence.mkdir(parents=True); self.runtime.mkdir(parents=True)

    @staticmethod
    def artifact(path):
        return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}

    def json_file(self, path, value):
        path.write_text(json.dumps(value), encoding="utf-8")
        return self.artifact(path)

    def materialize(self, restored=False, mutate=None):
        request, result, text = profile(restored)
        if mutate: request, result, text = mutate(request, result, text)
        request["cwd"] = str(self.runtime)
        host = self.runtime / "ZeroSisHost_x64.exe"; host.write_bytes(b"synthetic-not-executable")
        request["runtime_inputs"] = [self.artifact(host)]; request["unit_assets"] = None
        support = self.runtime / "interactive_ui_support"
        (support / "tools").mkdir(parents=True, exist_ok=True)
        (support / "assets").mkdir(exist_ok=True)
        record = {"tools": {}, "sdk_session_profile": {"ZEROSIS_UI_SMALL_ASSETS": "1"}}
        manifest = {"tools": {}}
        for name in ("interactive_ui_driver.py", "render_ui_popup.py", "ui_pixel_scene.py", "ui_bitmap_fonts.py", "civ5_ui_assets.py"):
            path = support / "tools" / name; path.write_bytes(b"# synthetic fixture\n")
            row = self.artifact(path); record["tools"][name] = {"frozen": row}; manifest["tools"][name] = row
        for key, name in (("inline_icons", "inline_icons.json"), ("asset_preparation_provenance", "prepared.json")):
            row = self.json_file(support / "assets" / name, {})
            record[key] = {"frozen": row}; manifest[key] = row
        record["frozen_support_manifest"] = self.json_file(support / "support_manifest.json", manifest)
        request["interactive_ui_support_inventory"] = copy.deepcopy(record)
        request["interactive_ui_support"] = self.json_file(self.evidence / "interactive_ui_support.json", record)
        result["request"] = self.json_file(self.evidence / "request.json", request)
        result["attempt"] = self.json_file(self.evidence / "attempt.json", {"status": "FINISHED", "returncode": 0, "timed_out": False, "pid": 123})
        for name, data in (("stdout", text), ("stderr", "")):
            path = self.evidence / (name + ".log"); path.write_text(data, encoding="utf-8")
            result[name] = self.artifact(path)
        self.json_file(self.evidence / "result.json", result)
        return request, result

    def read(self):
        with patch.object(verifier, "EVIDENCE", self.root / "evidence/interactive_game"), \
             patch.object(verifier, "RUNTIME", self.root / "Build/InteractiveGameRuntime"):
            return verifier.read_run(RUN, research_tree=True)

    def reuse(self):
        with patch.object(runner, "PROJECT", self.root):
            return runner.frozen_ui_support_source(RUN)

    def test_both_consumers_accept_exact_fresh_restore(self):
        for restored in (False, True):
            self.materialize(restored)
            self.assertEqual(self.read()[1]["status"], profile(restored)[1]["status"])
            self.assertEqual(self.reuse()["status"], profile(restored)[1]["status"])

    def test_both_consumers_reject_unknown_failed_and_forged_worker(self):
        for bad in ("UNKNOWN_PASS", "CONTINUOUS_INTERACTIVE_SDK_WORKER_BUILD_SMOKE_FAILED", "missing-contract", "missing-profile"):
            def mutate(request, result, text):
                if bad == "missing-contract": result["original_unit_panel_integration"] = {}
                elif bad == "missing-profile": request["top_panel"] = False
                else: result["status"] = bad
                return request, result, text
            self.materialize(mutate=mutate)
            for call in (self.read, self.reuse):
                with self.subTest(bad=bad, call=call.__name__), self.assertRaises(RuntimeError): call()

    def test_both_consumers_reject_incomplete_native_timelines(self):
        for marker in ("INTERACTIVE_ACTION_INFO_PANEL_SMOKE_COMPLETE", "INTERACTIVE_NOTIFICATION_PANEL_SMOKE_COMPLETE"):
            self.materialize(mutate=lambda request, result, text: (request, result, text.replace(marker, "MISSING")))
            for call in (self.read, self.reuse):
                with self.subTest(marker=marker, call=call.__name__), self.assertRaises(RuntimeError): call()

    def test_pinned_artifacts_and_support_profile_still_enforced(self):
        self.materialize()
        (self.evidence / "stdout.log").write_text("altered", encoding="utf-8")
        for call in (self.read, self.reuse):
            with self.assertRaisesRegex(RuntimeError, "Changed map object input"): call()
        self.materialize()
        (self.runtime / "interactive_ui_support/tools/ui_pixel_scene.py").write_text("altered", encoding="utf-8")
        with self.assertRaisesRegex(RuntimeError, "Changed map object input"): self.reuse()

    def test_legacy_tree_acceptance_remains(self):
        def legacy(request, result, text):
            result["status"] = "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS"
            request["worker_build"] = request["unit_actions"] = False
            result.pop("original_unit_panel_integration")
            return request, result, hud_fixture() + notification_fixture()
        self.materialize(mutate=legacy)
        self.assertEqual(self.read()[1]["status"], self.reuse()["status"])


if __name__ == "__main__":
    unittest.main()
