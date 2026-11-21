"""Read-only original ExitConfirm asset checks, without a game or native UI.

Mutated candidates exist only in memory. Sources and the existing font cache are
reused; this test creates no directory, asset copy, compiled header, or binary.
"""
from contextlib import ExitStack
from copy import deepcopy
import ast
import ctypes
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
sys.dont_write_bytecode = True

SOURCE_IDENTITIES = {
    "lua": ("Assets/UI/FrontEnd/ExitConfirm.lua", 1929,
            "7682db382ff5e1dc104165ba1d8a787d8e64e75fb1e550f223f2bb40ef08a5ae"),
    "xml": ("Assets/UI/FrontEnd/ExitConfirm.xml", 1510,
            "6d9794963c43a2df9de43974c219fb35d9423071ec1b98c8c2a24b696d09fe32"),
}


def identity(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def independent_tree(element):
    return {"kind": element.tag, "attributes": dict(element.attrib),
            "children": [independent_tree(child) for child in element]}


class ExitConfirmAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.guards = ExitStack()
        cls.addClassCleanup(cls.guards.close)
        cls.forbidden_calls = []

        def guard(owner, name, **keywords):
            mocked = cls.guards.enter_context(patch.object(
                owner, name, side_effect=AssertionError("Native execution and artifact creation are forbidden"),
                **keywords,
            ))
            cls.forbidden_calls.append(mocked)

        for name in ("Popen", "run", "call", "check_call", "check_output", "getoutput", "getstatusoutput"):
            guard(subprocess, name)
        for name in ("system", "startfile", "spawnl", "spawnle", "spawnlp", "spawnlpe",
                     "spawnv", "spawnve", "spawnvp", "spawnvpe"):
            if hasattr(os, name):
                guard(os, name)
        for name in ("CDLL", "WinDLL", "OleDLL", "PyDLL"):
            guard(ctypes, name, create=True)
        for name in ("cdll", "windll", "oledll", "pydll"):
            loader = getattr(ctypes, name, None)
            if loader is not None:
                guard(loader, "LoadLibrary")
        for name in ("copy", "copy2", "copyfile", "copytree"):
            guard(shutil, name)
        for name in ("mkdtemp", "TemporaryDirectory"):
            guard(tempfile, name)
        for name in ("write_bytes", "write_text", "mkdir"):
            guard(Path, name)
        for name in ("mkdir", "makedirs"):
            guard(os, name)

        import prepare_ui_popup_assets as freezer
        cls.freezer = freezer
        for name in ("main", "freeze_source"):
            guard(freezer, name)
        cls.addClassCleanup(cls.verify_forbidden_calls)
        cls.paths = {"original_" + key: freezer.GAME / row[0]
                     for key, row in SOURCE_IDENTITIES.items()}
        cls.paths.update({"snapshot_" + key: PROJECT / "Source/Assets/UI" / row[0]
                          for key, row in SOURCE_IDENTITIES.items()})
        cls.paths["styles"] = PROJECT / "Source/Assets/UI" / freezer.STYLE_SOURCE
        cls.paths["builder"] = PROJECT / "tools/prepare_ui_popup_assets.py"
        cls.paths["font_profile"] = freezer.PROFILE_PATH
        cls.before = {name: identity(path) for name, path in cls.paths.items()}
        cls.addClassCleanup(cls.verify_sources_unchanged)
        cls.lua = cls.paths["snapshot_lua"].read_text(encoding="utf-8-sig")
        cls.xml_bytes = cls.paths["snapshot_xml"].read_bytes()

    @classmethod
    def verify_forbidden_calls(cls):
        for mocked in cls.forbidden_calls:
            mocked.assert_not_called()

    @classmethod
    def verify_sources_unchanged(cls):
        if {name: identity(path) for name, path in cls.paths.items()} != cls.before:
            raise AssertionError("An ExitConfirm source changed during read-only asset checks")

    def original_xml(self):
        return ET.fromstring(self.xml_bytes)

    def prepared_tree(self):
        tree = self.freezer.exit_confirm_control_tree(self.original_xml())
        tree["contextName"] = "ExitConfirm"
        tree["popupKind"] = "ExitConfirm"
        return tree

    def style_contract(self, tree):
        source = self.paths["styles"]
        with patch.object(self.freezer, "freeze_source", return_value=(source, source)) as reused:
            result = self.freezer.production_style_defaults(PROJECT / "Source/Assets/UI", tree)
        reused.assert_called_once_with(self.freezer.STYLE_SOURCE, PROJECT / "Source/Assets/UI")
        return result

    def test_exact_original_identity_and_small_snapshot_bytes(self):
        self.assertEqual(self.freezer.EXIT_CONFIRM_SOURCE_IDENTITIES, SOURCE_IDENTITIES)
        original = self.freezer.exit_confirm_original_sources()
        for key, (relative, size, sha) in SOURCE_IDENTITIES.items():
            with self.subTest(key=key):
                self.assertEqual(original[key], self.before["original_" + key])
                self.assertEqual(original[key]["bytes"], size)
                self.assertEqual(original[key]["sha256"], sha)
                self.assertEqual(self.paths["original_" + key].read_bytes(),
                                 self.paths["snapshot_" + key].read_bytes())
                self.assertEqual((PROJECT / "Source/Assets/UI" / relative), self.paths["snapshot_" + key])

    def test_registry_and_main_asset_context_font_paths_are_connected(self):
        scripts = [relative for name, relative in self.freezer.SCRIPTS if name == "ExitConfirm"]
        layouts = [row for row in self.freezer.LAYOUTS if row[0] == "ExitConfirmLayout"]
        self.assertEqual(scripts, [SOURCE_IDENTITIES["lua"][0]])
        self.assertEqual(layouts, [("ExitConfirmLayout", SOURCE_IDENTITIES["xml"][0], "ExitConfirm")])
        module = ast.parse(self.paths["builder"].read_text(encoding="utf-8-sig"))
        main = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "main")
        mappings = [node for node in ast.walk(main) if isinstance(node, ast.Dict) and
                    any(isinstance(key, ast.Constant) and key.value == "ExitConfirmLayout" for key in node.keys)]
        self.assertEqual(len(mappings), 1)
        mapping = dict(zip((key.value for key in mappings[0].keys),
                           (value.value for value in mappings[0].values)))
        self.assertEqual(mapping["ExitConfirmLayout"], "ExitConfirm")
        selected = [node for node in ast.walk(main) if isinstance(node, ast.If) and
                    isinstance(node.test, ast.Compare) and isinstance(node.test.left, ast.Name) and
                    node.test.left.id == "kind" and any(isinstance(op, ast.In) for op in node.test.ops)]
        self.assertTrue(any("ExitConfirm" in ast.literal_eval(node.test.comparators[0]) and
                            "production_font_metrics" in ast.unparse(node) for node in selected))
        self.assertIn("exit_confirm_control_tree(source_root)", ast.unparse(main))

    def test_complete_raw_tree_and_original_name_are_retained_without_mutating_input(self):
        original = self.original_xml()
        before = ET.tostring(original)
        tree = self.freezer.exit_confirm_control_tree(original)
        metadata = tree.pop("exitConfirm")
        self.assertEqual(tree, independent_tree(original))
        self.assertEqual(before, ET.tostring(original))
        self.assertEqual(metadata["retainedControlCount"], 12)
        self.assertEqual(metadata["rawOriginalName"], "MainMenu")
        self.assertEqual(tree["attributes"]["Name"], "MainMenu")
        self.assertEqual(metadata["originalLua"], self.before["original_lua"])
        self.assertEqual(metadata["originalXml"], self.before["original_xml"])

    def test_original_modal_parent_timer_and_acceptance_boundaries_are_explicit(self):
        metadata = self.prepared_tree()["exitConfirm"]
        expected = {
            "policy": "ORIGINAL_EXIT_CONFIRM_MODAL_V1", "modal": True,
            "parentContext": "GameMenu", "timerSemaphores": 0,
            "parentTimerSemaphorePolicy": "PRESERVE_GAME_MENU_TIMER_WHILE_MODAL_OPEN",
            "openEvent": "UserRequestClose", "yesPolicy": "ORIGINAL_POP_MODAL_THEN_UI_EXIT_GAME",
            "cancelPolicy": "ORIGINAL_POP_MODAL_ON_NO_OR_ESCAPE",
            "originalButtonVisibilityPreserved": True,
            "nativeAcceptanceVerified": False, "retailLayoutVerified": False,
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(metadata[key], value)

    def test_original_callbacks_target_real_buttons_and_modal_api_order(self):
        controls = {node.get("ID"): node for node in self.original_xml().iter() if node.get("ID")}
        callbacks = re.findall(r"Controls\.([A-Za-z_][A-Za-z0-9_]*):RegisterCallback\(", self.lua)
        self.assertEqual(callbacks, ["Yes", "No"])
        for name in callbacks:
            self.assertEqual(controls[name].tag, "GridButton")
        source = re.sub(r"--[^\n]*", "", self.lua)
        self.assertIn("Events.UserRequestClose.Add( OnExitGame );", source)
        yes = source[source.index("function OnYes"):source.index("Controls.Yes:RegisterCallback")]
        self.assertLess(yes.index("UIManager:PopModal"), yes.index("UI.ExitGame"))
        self.assertIn('ContextPtr:LookUpControl("/InGame")', source)
        self.assertIn('"TXT_KEY_MENU_RETURN_EXIT_WARN" or "TXT_KEY_MENU_EXIT_WARN"', source)
        self.assertNotIn("incTurnTimerSemaphore", source)
        self.assertNotIn("decTurnTimerSemaphore", source)

    def test_xml_mutations_cannot_hide_relabel_reorder_or_replace_original_nodes(self):
        for change in ("raw_name", "hide_yes", "message", "remove_no", "reorder", "replace_button", "extra"):
            candidate = deepcopy(self.original_xml())
            controls = {node.get("ID"): node for node in candidate.iter() if node.get("ID")}
            if change == "raw_name":
                candidate.set("Name", "ExitConfirm")
            elif change == "hide_yes":
                controls["Yes"].set("Hidden", "1")
            elif change == "message":
                controls["Message"].set("String", "Replacement warning")
            elif change == "remove_no":
                controls["ButtonStack"].remove(controls["No"])
            elif change == "reorder":
                controls["ButtonStack"].remove(controls["Yes"])
                controls["ButtonStack"].append(controls["Yes"])
            elif change == "replace_button":
                controls["Yes"].tag = "Button"
            else:
                ET.SubElement(candidate, "Box", {"ID": "Invented"})
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.freezer.exit_confirm_control_tree(candidate)

    def test_source_identity_mutations_fail_before_assets_are_accepted(self):
        digest = self.freezer.digest
        for key in SOURCE_IDENTITIES:
            target = self.paths["original_" + key]
            with self.subTest(key=key), patch.object(
                    self.freezer, "digest", side_effect=lambda path: "0" * 64 if Path(path) == target else digest(path)):
                with self.assertRaisesRegex(ValueError, "Original ExitConfirm source identity changed"):
                    self.freezer.exit_confirm_original_sources()
                with self.assertRaises(ValueError):
                    self.freezer.exit_confirm_control_tree(self.original_xml())

    def test_existing_styles_and_sealed_font_profile_supply_the_modal(self):
        tree = self.prepared_tree()
        styles = self.style_contract(tree)
        self.assertTrue({"BaseButton", "Grid9DetailFive140", "PopupLeftSideTreatment",
                         "PopupRightSideTreatment", "PopupNotificationTopTreatment"}.issubset(styles["controls"]))
        tree["styleDefaults"] = styles["controls"]
        texture_names = self.freezer.game_menu_texture_names(tree)
        self.assertTrue(texture_names)
        self.assertEqual(texture_names, sorted(set(texture_names), key=str.casefold))
        font_root = self.freezer.profile_input_root(self.freezer.PROFILE_PATH)
        profile, fonts = self.freezer.load_font_profile(self.freezer.PROFILE_PATH, font_root)
        before = self.freezer.verify_profile_inputs(profile, font_root)
        metrics = self.freezer.production_font_metrics(tree, {}, fonts_by_id=fonts, font_root=font_root)
        self.assertEqual(set(metrics["fonts"]), {"TwCenMT22", "TwCenMT24"})
        for name in metrics["fonts"]:
            self.assertIn("Shadow", fonts[name].styles)
            self.assertEqual(metrics["fonts"][name]["sha256"], profile["fonts"][name]["ggxml"]["sha256"])
        self.assertIs(metrics["retailMetricSemanticsVerified"], False)
        self.assertEqual(before, self.freezer.verify_profile_inputs(profile, font_root))


if __name__ == "__main__":
    unittest.main()
