"""Read-only retained SDK gate regression tests; no SDK or Host is loaded."""
from __future__ import annotations

import copy
import ctypes
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest import mock


PROJECT = Path(__file__).absolute().parents[1]
SPEC = importlib.util.spec_from_file_location("sdk_input_under_test", PROJECT / "tools/current_runtime_sdk_input.py")
GATE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GATE)
REPORT = PROJECT / "evidence/serialization/unit_great_work_save/sdk_2bdcdf80a1695780f864/result.json"
REPORT_SHA = "4b6310ce04dc6d1b155c406ac470b855682c2934eb03f6742ab1f065a6ef12ec"


class RetainedStaticDeltaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw = REPORT.read_bytes()
        if hashlib.sha256(raw).hexdigest() != REPORT_SHA:
            raise AssertionError("The independent retained report oracle changed")
        cls.build = json.loads(raw)
        cls.parent = json.loads(Path(cls.build["parent"]["path"]).read_bytes())
        cls.map_text = Path(cls.build["artifacts"]["CvGameCoreDLL_Expansion2_x64.map"]["path"]).read_text(
            encoding="utf-8", errors="replace")
        cls.object_names = {Path(r["path"]).name for r in cls.build["current_objects"]}

    def test_actual_public_gate_is_read_only_and_preserves_unknown_exit_codes(self):
        with mock.patch("subprocess.Popen", side_effect=AssertionError("No child process")), \
             mock.patch.object(ctypes, "CDLL", side_effect=AssertionError("No DLL load")), \
             mock.patch.object(ctypes, "WinDLL", side_effect=AssertionError("No DLL load")):
            result = GATE.validate_current_runtime_sdk(REPORT, REPORT_SHA)
        self.assertEqual(result["gamecore"]["bytes"], 6945792)
        self.assertEqual(result["gamecore"]["sha256"], "430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9")
        self.assertEqual(result["validation"], result["report"])
        self.assertEqual(result["input_schema"], "zerosis.unit_great_work_sdk.retained_static.v1")
        self.assertEqual(result["process_exit_code_evidence"], "not_retained")
        self.assertIsNone(result["compile_process_exit_code"])
        self.assertIsNone(result["link_process_exit_code"])
        self.assertEqual(result["static_delta_provenance"]["reused_parent_objects"], 164)
        self.assertEqual(result["static_delta_provenance"]["unique_compiler_inputs"], 402)
        before = result["static_delta_provenance"]["source_before"]
        self.assertEqual(set(before), {"original_path", "bytes", "sha256"})
        self.assertEqual(before["sha256"], "e2fbfa20b3f2c4ecc6e37cf7cce3ea894272098b4bce50da08c8874900a4823b")
        for flag in ("gamecore_loaded", "host_executed", "windows_created", "runtime_updated",
                     "default_promoted", "restore_approved", "ruleset_compatibility_verified", "full_engine_goal_complete"):
            self.assertIs(result[flag], False)

    def test_public_path_sha_and_legacy_dispatch(self):
        with self.assertRaises(GATE.CurrentRuntimeSdkInputError):
            GATE.validate_current_runtime_sdk(REPORT, "0" * 64)
        with self.assertRaises(GATE.CurrentRuntimeSdkInputError):
            GATE.validate_current_runtime_sdk(REPORT.with_name("unreviewed.json"), REPORT_SHA)
        legacy = PROJECT / "evidence/sdk_runtime_current/build_result.json"
        sentinel = {"gamecore": object(), "report": object(), "validation": object(), "shared_lua_dll": object()}
        with mock.patch.object(GATE, "_validate", return_value=sentinel) as old, \
             mock.patch.object(GATE, "_validate_static", side_effect=AssertionError("Wrong schema branch")):
            self.assertIs(GATE.validate_current_runtime_sdk(legacy, GATE.PARENT_SHA), sentinel)
            old.assert_called_once_with(legacy, GATE.PARENT_SHA)
        self.assertIsNone(GATE._Artifacts().source_delta)
        self.assertEqual(GATE._Artifacts().historical_tools, {})

    def test_source_override_is_exact_and_absent_from_the_legacy_gate(self):
        after = self.build["source"]
        before = next(r for r in self.parent["inputs"] if GATE._key(r["path"]) == GATE._key(after["path"]))
        with self.assertRaises(GATE.CurrentRuntimeSdkInputError):
            GATE._Artifacts().verify(before)
        files = GATE._Artifacts()
        files.source_delta = before, after
        self.assertEqual(files.verify(before)["sha256"], after["sha256"])
        invalid = dict(before, sha256="0" * 64)
        with self.assertRaises(GATE.CurrentRuntimeSdkInputError):
            files.effective(invalid)
        unrelated = dict(before, path=str(PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPlayer.cpp"))
        self.assertIs(files.effective(unrelated), unrelated)

    def test_static_shape_rejects_independent_manifest_controls(self):
        controls = [
            ("schema", lambda b: b.update(schema="zerosis.sdk.current_runtime_candidate.v1")),
            ("status", lambda b: b.update(status="PASS")),
            ("fingerprint", lambda b: b.update(fingerprint="unreviewed")),
            ("parent", lambda b: b["parent"].update(sha256="0" * 64)),
            ("unit", lambda b: b["source"].update(sha256="0" * 64)),
            ("helper", lambda b: b["header"].update(sha256="0" * 64)),
            ("other source", lambda b: b["source"].update(path=str(PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPlayer.cpp"))),
            ("two deltas", lambda b: b.update(inherited_source_deltas=2)),
            ("boolean count", lambda b: b.update(new_header_count=True)),
            ("object count", lambda b: b.update(object_count=164)),
            ("consumed rows", lambda b: b["consumed_inputs"].pop()),
            ("compile rc fabricated", lambda b: b.update(compile_process_exit_code=0)),
            ("link rc fabricated", lambda b: b.update(link_process_exit_code=0)),
            ("exit evidence", lambda b: b.update(process_exit_code_evidence="PASS")),
            ("new command", lambda b: b["new_child_commands"].append(["host.exe"])),
            ("history deleted", lambda b: b["historical_child_commands"].pop()),
            ("loaded", lambda b: b.update(dll_or_sdk_reference_loaded=True)),
            ("restore", lambda b: b.update(restore_approved=True)),
            ("full goal", lambda b: b.update(full_engine_goal_complete=True)),
            ("input proof", lambda b: b.update(all_compiler_dependencies_prehashed=False)),
            ("PCH", lambda b: b.update(no_pch_consumed=False)),
            ("ABI", lambda b: b["compile_flags"].remove("/MD")),
            ("extra output", lambda b: b["artifacts"].update(extra=b["artifacts"]["CvUnit.obj"])),
            ("escaped output", lambda b: b["artifacts"]["CvUnit.obj"].update(path=str(PROJECT / "other.obj"))),
        ]
        for name, change in controls:
            with self.subTest(name=name):
                build = copy.deepcopy(self.build)
                change(build)
                with self.assertRaises(GATE.CurrentRuntimeSdkInputError):
                    GATE._static_shape(build)

    def test_only_one_parent_object_can_be_replaced(self):
        self.assertEqual(len(GATE._static_objects(self.build, self.parent)), 165)
        for case in range(5):
            with self.subTest(case=case):
                build = copy.deepcopy(self.build)
                if case == 0: build["current_objects"].pop()
                elif case == 1: build["current_objects"][1] = dict(build["current_objects"][0])
                elif case == 2:
                    target = next(r for r in build["current_objects"] if Path(r["path"]).name != "CvUnit.obj")
                    target["sha256"] = "0" * 64
                elif case == 3: build["replaced_parent_object"]["sha256"] = "0" * 64
                else: build["artifacts"]["CvUnit.obj"]["bytes"] += 1
                with self.assertRaises(GATE.CurrentRuntimeSdkInputError):
                    GATE._static_objects(build, self.parent)

    def test_dependency_transcript_and_conflicting_duplicate(self):
        dependency = json.loads(Path(self.build["artifacts"]["CvUnit.dependencies.json"]["path"]).read_bytes())["Data"]
        paths = {GATE._key(dependency["Source"]), *(GATE._key(x) for x in dependency["Includes"])}
        rows = self.build["consumed_inputs"]
        self.assertEqual(len(rows), 434)
        self.assertEqual(len(paths), 402)
        self.assertEqual(paths, {GATE._key(r["path"]) for r in rows})
        files = GATE._Artifacts()
        files.verify(self.build["source"])
        with self.assertRaises(GATE.CurrentRuntimeSdkInputError):
            files.verify(dict(self.build["source"], sha256="0" * 64))

    def test_actual_map_and_independent_negative_controls(self):
        GATE._static_map(self.map_text, self.build, self.object_names)
        named = next(line for line in self.map_text.splitlines() if " ??$UnitGreatWorkHashForSave@" in line)
        controls = [
            (self.map_text.replace(named, ""), self.build, self.object_names),
            (self.map_text.replace(named, named.replace("CvUnit.obj", "CvPlayer.obj")), self.build, self.object_names),
            (self.map_text, self.build, self.object_names - {"CvUnit.obj"}),
        ]
        registry = self.build["map_contract"]["borrowed_registry"]
        extra = "\n 0003:00000000 " + registry["symbol"] + " 0000000180001000 f CvArea.obj\n"
        controls.append((self.map_text + extra, self.build, self.object_names))
        for i, args in enumerate(controls):
            with self.subTest(case=i), self.assertRaises(GATE.CurrentRuntimeSdkInputError):
                GATE._static_map(*args)

    def test_historical_helper_requires_exact_roundtrip(self):
        files = GATE._Artifacts()
        backup = GATE._historical_validator_backup(files, self.build)
        self.assertEqual(backup["sha256"], "648ba2373a2f92ea7dd707fa7a88604afa0900c7e678140fd61c0526b8c96f21")
        invalid = copy.deepcopy(self.build)
        row = next(r for r in invalid["helpers"] if Path(r["path"]).name == "current_runtime_sdk_input.py")
        row["sha256"] = "0" * 64
        with self.assertRaises(GATE.CurrentRuntimeSdkInputError):
            GATE._historical_validator_backup(GATE._Artifacts(), invalid)
        with mock.patch.object(GATE.gzip, "open", return_value=io.BytesIO(b"wrong historical bytes")), \
             self.assertRaises(GATE.CurrentRuntimeSdkInputError):
            GATE._historical_validator_backup(GATE._Artifacts(), self.build)


if __name__ == "__main__":
    unittest.main(verbosity=2)
