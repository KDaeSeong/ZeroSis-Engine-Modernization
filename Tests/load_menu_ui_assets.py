"""Read-only stock LoadMenu asset contracts, with no runtime or pixel proof.

XML mutations exist only in memory. No source copy, temporary directory, Lua VM,
native library, compiler, GameCore, game process, or save archive is used.
"""
from contextlib import ExitStack
from copy import deepcopy
import ctypes
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET


PROJECT = Path(__file__).absolute().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

LOAD_LUA = "Assets/UI/FrontEnd/LoadMenu.lua"
LOAD_XML = "Assets/UI/FrontEnd/LoadMenu.xml"
INCLUDES = ["InstanceManager", "IconSupport", "SupportFunctions", "UniqueBonuses", "MapUtilities"]
BUTTON_CALLBACKS = {
    "StartButton", "Delete", "Yes", "No", "BackButton", "ShowModsButton",
    "ShowDLCButton", "CloseReferencedPackagesButton",
}
BUTTON_KINDS = {"Button", "GridButton", "TextButton"}
PULL_DOWN_STYLE_NAMES = {
    "GenericPullDown", "SquareButton", "Grid9Frame27Square", "Grid9Frame27SquareBlack",
    "VertSlider", "VertShuttle", "ScrollBarUp", "ScrollBarDown", "ZoomButton",
    "Grid9FrameTurnsButton",
}


def independent_tree(element):
    return {"kind": element.tag, "attributes": dict(element.attrib),
            "children": [independent_tree(child) for child in element]}


def artifact(path: Path):
    return {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


class LoadMenuAssetTests(unittest.TestCase):
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
        import native_build
        import probe_world_builder
        cls.freezer = freezer
        for module, names in (
            (freezer, ("main", "freeze_source")),
            (native_build, ("run", "checked_run", "environment_for")),
            (probe_world_builder, ("main", "run", "checked_run", "environment_for")),
        ):
            for name in names:
                guard(module, name)
        cls.addClassCleanup(cls.verify_forbidden_calls)

        cls.registry = dict(freezer.SCRIPTS)
        cls.paths = {
            "LoadMenu": freezer.GAME / LOAD_LUA,
            "LoadMenuLayout": freezer.GAME / LOAD_XML,
            "GameMenuLayout": freezer.GAME / freezer.GAME_MENU_XML,
            "Styles": freezer.GAME / freezer.STYLE_SOURCE,
            "freezer": PROJECT / "tools/prepare_ui_popup_assets.py",
        }
        cls.paths.update({name: freezer.GAME / cls.registry[name] for name in INCLUDES})
        cls.before = {name: artifact(path) for name, path in cls.paths.items()}
        cls.addClassCleanup(cls.verify_sources_unchanged)
        cls.lua = cls.paths["LoadMenu"].read_text(encoding="utf-8-sig")
        cls.xml_bytes = cls.paths["LoadMenuLayout"].read_bytes()

    @classmethod
    def verify_forbidden_calls(cls):
        for mocked in cls.forbidden_calls:
            mocked.assert_not_called()

    @classmethod
    def verify_sources_unchanged(cls):
        after = {name: artifact(path) for name, path in cls.paths.items()}
        if after != cls.before:
            raise AssertionError("A source changed during read-only LoadMenu asset checks")

    def original_xml(self):
        return ET.fromstring(self.xml_bytes)

    def metadata(self):
        return self.freezer.load_menu_control_tree(self.original_xml())["loadMenu"]

    def style_contract(self, *, tree=None, styles=None):
        """Reuse the installed Styles.xml read-only instead of freezing a copy."""
        if tree is None:
            tree = self.freezer.load_menu_control_tree(self.original_xml())
        snapshots = PROJECT / "Source/Assets/UI"
        source = self.paths["Styles"]
        with ExitStack() as patches:
            reused = patches.enter_context(patch.object(
                self.freezer, "freeze_source", return_value=(source, source)))
            if styles is not None:
                patches.enter_context(patch.object(
                    self.freezer.ET, "parse", return_value=ET.ElementTree(styles)))
            result = self.freezer.production_style_defaults(snapshots, tree)
            reused.assert_called_once_with(self.freezer.STYLE_SOURCE, snapshots)
        return result

    def test_exact_base_registration_includes_and_parent_child_path(self):
        freezer = self.freezer
        self.assertEqual(freezer.LOAD_MENU_LUA, LOAD_LUA)
        self.assertEqual(freezer.LOAD_MENU_XML, LOAD_XML)
        self.assertIn(("LoadMenu", LOAD_LUA), freezer.SCRIPTS)
        self.assertIn(("LoadMenuLayout", LOAD_XML, "LoadMenu"), freezer.LAYOUTS)
        self.assertEqual(sum(name == "LoadMenu" for name, _ in freezer.SCRIPTS), 1)
        self.assertEqual(sum(name == "LoadMenuLayout" for name, *_ in freezer.LAYOUTS), 1)
        includes = re.findall(r'^include\s*\(\s*"([^"\n]+)"\s*\)\s*;', self.lua, re.MULTILINE)
        self.assertEqual(includes, INCLUDES)
        for name in includes:
            self.assertEqual(self.registry[name], str(self.paths[name].relative_to(freezer.GAME)).replace("\\", "/"))
            self.assertTrue(self.paths[name].is_file(), name)
        unique_bonuses = self.paths["UniqueBonuses"].read_text(encoding="utf-8-sig")
        self.assertRegex(unique_bonuses, r'include\s*\(\s*"InfoTooltipInclude"\s*\)')
        self.assertIn("InfoTooltipInclude", self.registry)
        game_menu = ET.parse(self.paths["GameMenuLayout"]).getroot()
        first_child = game_menu.findall("LuaContext")[0]
        self.assertEqual(first_child.attrib, {
            "FileName": "Assets/UI/FrontEnd/LoadMenu", "ID": "LoadMenu", "Hidden": "True",
        })
        self.assertEqual(first_child.get("FileName") + ".lua", LOAD_LUA)
        self.assertEqual(first_child.get("FileName") + ".xml", LOAD_XML)
        self.assertEqual(self.metadata()["parentContext"], "GameMenu")

    def test_complete_original_tree_and_source_evidence_are_retained(self):
        original = self.original_xml()
        before = ET.tostring(original)
        tree = self.freezer.load_menu_control_tree(original)
        metadata = tree.pop("loadMenu")
        self.assertEqual(ET.tostring(original), before)
        self.assertEqual(tree, independent_tree(original))
        self.assertEqual(metadata["retainedControlCount"], len(list(original.iter())))
        self.assertEqual(metadata["instanceNames"], ["LoadButton", "ReferencedPackageInstance"])
        self.assertEqual(metadata["includeNames"], INCLUDES)
        self.assertEqual(metadata["unconnectedLuaContexts"], [])
        for field, name in (("originalLua", "LoadMenu"), ("originalXml", "LoadMenuLayout"),
                            ("originalUniqueBonusesLua", "UniqueBonuses"), ("originalMapUtilitiesLua", "MapUtilities")):
            self.assertEqual(metadata[field], self.before[name])
        self.assertTrue(metadata["sourceBytesPreserved"])
        for field in ("runtimeIntegrationVerified", "pullDownRuntimeVerified",
                      "retailSaveCompatibilityVerified", "retailLayoutVerified"):
            self.assertIs(metadata[field], False)

    def test_every_original_lua_control_and_callback_has_the_correct_xml_kind(self):
        original = self.original_xml()
        controls = {node.get("ID"): node for node in original.iter() if node.get("ID")}
        direct_controls = set(re.findall(r'\bControls\.([A-Za-z_][A-Za-z0-9_]*)', self.lua))
        self.assertTrue(direct_controls)
        self.assertFalse(direct_controls - controls.keys())
        callbacks = set(re.findall(r'Controls\.([A-Za-z_][A-Za-z0-9_]*):RegisterCallback\s*\(', self.lua))
        self.assertEqual(callbacks, BUTTON_CALLBACKS)
        for name in callbacks:
            self.assertIn(controls[name].tag, BUTTON_KINDS, name)
        checks = set(re.findall(r'Controls\.([A-Za-z_][A-Za-z0-9_]*):RegisterCheckHandler\s*\(', self.lua))
        self.assertEqual(checks, {"AutoCheck", "CloudCheck"})
        for name in checks:
            self.assertEqual(controls[name].tag, "CheckBox")
        load_button = original.find("Instance[@Name='LoadButton']")
        self.assertIsNotNone(load_button)
        self.assertEqual(load_button.find(".//*[@ID='Button']").tag, "GridButton")
        self.assertEqual(load_button.find(".//*[@ID='InstanceRoot']").tag, "Container")
        self.assertEqual(load_button.find(".//*[@ID='ButtonText']").tag, "Label")
        package = original.find("Instance[@Name='ReferencedPackageInstance']")
        self.assertIsNotNone(package)
        self.assertEqual(package.find(".//*[@ID='Label']").tag, "Label")

    def test_sorting_template_uses_the_actual_existing_styles_source(self):
        pulldown = self.original_xml().find(".//PullDown[@ID='SortByPullDown']")
        self.assertIsNotNone(pulldown)
        self.assertIn("PullDown", self.freezer.KINDS)
        self.assertEqual(pulldown.get("Style"), "GenericPullDown")
        styles = ET.parse(self.paths["Styles"]).getroot()
        style = styles.find("GenericPullDown")
        self.assertIsNotNone(style)
        instance = style.find("InstanceData[@Name='InstanceOne']")
        self.assertIsNotNone(instance)
        self.assertEqual(instance.find(".//*[@ID='Button']").tag, "GridButton")
        self.assertRegex(self.lua, r'local\s+sortByPulldown\s*=\s*Controls\.SortByPullDown\s*;')
        self.assertRegex(self.lua, r'sortByPulldown:BuildEntry\s*\(\s*"InstanceOne"\s*,\s*controlTable\s*\)')
        self.assertRegex(self.lua, r'controlTable\.Button:RegisterCallback\s*\(\s*Mouse\.eLClick')
        self.assertIs(self.metadata()["pullDownRuntimeVerified"], False)

    def test_composite_style_retains_all_original_blocks_and_nested_style_definitions(self):
        prepared = self.style_contract()
        captured = prepared["controls"]
        originals = {node.tag: node for node in ET.parse(self.paths["Styles"]).getroot()}
        self.assertTrue(PULL_DOWN_STYLE_NAMES <= captured.keys())
        self.assertEqual(prepared["source"], {
            "path": self.freezer.STYLE_SOURCE, "sha256": self.before["Styles"]["sha256"],
        })

        def original_view(node):
            return {"kind": node["kind"], "attributes": node["sourceAttributes"],
                    "children": [original_view(child) for child in node["children"]]}

        for name in sorted(PULL_DOWN_STYLE_NAMES):
            with self.subTest(style=name):
                self.assertEqual(original_view(captured[name]), independent_tree(originals[name]))
        blocks = captured["GenericPullDown"]["children"]
        self.assertEqual([node["kind"] for node in blocks], [
            "ButtonData", "GridData", "ScrollPanelData", "StackData", "InstanceData",
        ])
        self.assertEqual(blocks[4]["sourceAttributes"], {"Name": "InstanceOne"})
        self.assertEqual(blocks[4]["children"][0]["sourceAttributes"], {
            "Size": "200.24", "Style": "ZoomButton", "Anchor": "C,C", "ID": "Button",
        })
        self.assertEqual(blocks[1]["sourceAttributes"]["Padding"], "5,5")
        self.assertNotIn("Texture", blocks[1]["sourceAttributes"])
        self.assertEqual(blocks[1]["attributes"]["Texture"],
                         originals["Grid9Frame27SquareBlack"].get("Texture"))
        self.assertEqual(blocks[1]["attributes"]["Padding"], "5,5")
        scrollbar = blocks[2]["children"][0]
        self.assertEqual(scrollbar["sourceAttributes"], dict(originals["GenericPullDown"].find(
            "ScrollPanelData/ScrollBar").attrib))
        self.assertEqual(scrollbar["attributes"]["Vertical"], "1")
        self.assertEqual(scrollbar["attributes"]["Texture"], originals["VertSlider"].get("Texture"))
        for name, grid in (("SquareButton", "Grid9Frame27Square"),
                           ("ZoomButton", "Grid9FrameTurnsButton")):
            child = captured[name]["children"][0]
            self.assertEqual(child["sourceAttributes"], {"Style": grid})
            self.assertEqual(child["attributes"]["Texture"], originals[grid].get("Texture"))
        shuttle = captured["VertSlider"]["children"][0]
        self.assertEqual(shuttle["sourceAttributes"], {"Style": "VertShuttle", "Size": "18,18"})
        self.assertEqual(shuttle["attributes"]["Texture"], originals["VertShuttle"].get("Texture"))
        self.assertEqual(shuttle["children"], [])
        for field in ("runtimeIntegrationVerified", "pullDownRuntimeVerified", "retailLayoutVerified"):
            self.assertIs(self.metadata()[field], False)

    def test_style_inheritance_keeps_raw_attributes_and_applies_control_overrides_last(self):
        styles = ET.parse(self.paths["Styles"]).getroot()
        square = styles.find("SquareButton")
        square.set("Style", "InheritedPullDownButton")
        square.set("Size", "222,29")
        ET.SubElement(styles, "InheritedPullDownButton", {
            "Style": "InheritedPullDownBase", "Font": "TwCenMT18", "Size": "300,31",
        })
        ET.SubElement(styles, "InheritedPullDownBase", {
            "FontStyle": "Shadow", "Anchor": "R,T", "Size": "400,39",
        })
        prepared = self.style_contract(styles=styles)["controls"]
        self.assertTrue({"InheritedPullDownButton", "InheritedPullDownBase"} <= prepared.keys())
        button = prepared["GenericPullDown"]["children"][0]["children"][0]
        self.assertEqual(button["sourceAttributes"], {"Style": "SquareButton", "Anchor": "L,C"})
        self.assertEqual({key: button["attributes"][key] for key in (
            "Style", "Font", "FontStyle", "Anchor", "Size")}, {
            "Style": "SquareButton", "Font": "TwCenMT18", "FontStyle": "Shadow",
            "Anchor": "L,C", "Size": "222,29",
        })
        self.assertEqual(prepared["SquareButton"]["sourceAttributes"], {
            "Style": "InheritedPullDownButton", "Size": "222,29",
        })
        self.assertEqual([node["kind"] for node in prepared["SquareButton"]["children"]], ["GridData"])

    def test_missing_or_cyclic_nested_styles_are_rejected_without_artifact_creation(self):
        for mutation in ("missing", "inheritance_cycle", "composite_cycle"):
            styles = ET.parse(self.paths["Styles"]).getroot()
            if mutation == "missing":
                styles.find("GenericPullDown/ScrollPanelData/ScrollBar").set("Style", "MissingSlider")
                message = "missing style: MissingSlider"
            elif mutation == "inheritance_cycle":
                styles.find("SquareButton").set("Style", "SquareButton")
                message = "cycle:.*SquareButton"
            else:
                styles.find("SquareButton").set("Style", "GenericPullDown")
                message = "cycle:.*GenericPullDown"
            with self.subTest(mutation=mutation), self.assertRaisesRegex(RuntimeError, message):
                self.style_contract(styles=styles)

    def test_font_metrics_include_fonts_used_only_by_style_instance_templates(self):
        tree = {"kind": "Context", "attributes": {}, "children": [], "styleDefaults": {
            "GenericPullDown": {"kind": "GenericPullDown", "attributes": {}, "children": [{
                "kind": "InstanceData", "attributes": {"Name": "InstanceOne"}, "children": [{
                    "kind": "GridButton", "attributes": {"ID": "Button", "Style": "LabelledButton"},
                    "children": [],
                }],
            }]},
            "LabelledButton": {"kind": "LabelledButton", "attributes": {
                "Font": "TwCenMT18", "FontStyle": "Shadow",
            }, "children": [{"kind": "Label", "attributes": {
                "Font": "TwCenMT20", "FontStyle": "Base",
            }, "children": []}]},
        }}

        def fake_font(_game, font_id, _style):
            return SimpleNamespace(
                font_style="Base", styles={"Base": (), "Shadow": ()},
                ggxml_sha256=hashlib.sha256(font_id.encode("ascii")).hexdigest(), glyphs={},
                line_advance=20, baseline_offset=1, spacing=0, fudgeadv=0,
                ggxml_path=self.freezer.GAME / f"Assets/UI/Fonts/Tw Cent MT/{font_id}.ggxml",
            )

        with patch.object(self.freezer, "load_font", side_effect=fake_font) as loader:
            metrics = self.freezer.production_font_metrics(tree, {})
        self.assertEqual([call.args[1:] for call in loader.call_args_list], [
            ("TwCenMT18", "Base"), ("TwCenMT20", "Base"),
        ])
        self.assertEqual(set(metrics["fonts"]), {"TwCenMT18", "TwCenMT20"})
        self.assertIs(metrics["retailMetricSemanticsVerified"], False)
        self.assertEqual(metrics["inlineIcons"], {})
        tree["styleDefaults"]["LabelledButton"]["attributes"]["FontStyle"] = "MissingStyle"
        with patch.object(self.freezer, "load_font", side_effect=fake_font), self.assertRaisesRegex(
                RuntimeError, "lacks referenced styles: TwCenMT18/MissingStyle"):
            self.freezer.production_font_metrics(tree, {})

    def test_memory_only_xml_mutations_cannot_hide_relabel_repoint_or_drop_controls(self):
        for change in ("caption", "hidden", "id", "kind", "checkbox", "pulldown_style", "pulldown_id",
                       "template_name", "template_drop", "template_order", "confirmation", "child", "root_attribute"):
            candidate = deepcopy(self.original_xml())
            controls = {node.get("ID"): node for node in candidate.iter() if node.get("ID")}
            if change == "caption":
                controls["StartButton"].set("String", "Replacement load caption")
            elif change == "hidden":
                controls["StartButton"].set("Hidden", "1")
            elif change == "id":
                controls["StartButton"].set("ID", "ReplacementStart")
            elif change == "kind":
                controls["StartButton"].tag = "Image"
            elif change == "checkbox":
                controls["AutoCheck"].tag = "Label"
            elif change == "pulldown_style":
                controls["SortByPullDown"].set("Style", "ReplacementPullDown")
            elif change == "pulldown_id":
                controls["SortByPullDown"].set("ID", "ReplacementSort")
            elif change == "template_name":
                candidate.find("Instance[@Name='LoadButton']").set("Name", "ReplacementEntry")
            elif change == "template_drop":
                candidate.remove(candidate.find("Instance[@Name='ReferencedPackageInstance']"))
            elif change == "template_order":
                first = candidate.find("Instance[@Name='LoadButton']")
                candidate.remove(first)
                candidate.append(first)
            elif change == "confirmation":
                controls["DeleteConfirm"].set("Hidden", "0")
            elif change == "child":
                ET.SubElement(candidate, "LuaContext", {"ID": "ForeignContext", "FileName": "Foreign", "Hidden": "1"})
            else:
                candidate.set("ColorSet", "ReplacementColors")
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.freezer.load_menu_control_tree(candidate)

    def test_stock_paths_and_optional_owned_delete_keep_the_runtime_proof_boundary(self):
        metadata = self.metadata()
        self.assertEqual(set(metadata["unsupportedActions"]), {
            "loadDispatch", "delete", "cloud", "multiplayer", "retailSaveImport",
        })
        self.assertRegex(self.lua, r'Events\.PlayerChoseToLoadGame\s*\(\s*thisLoadFile\s*\)')
        self.assertRegex(self.lua, r'UI\.DeleteSavedGame\s*\(\s*g_FileList\s*\[\s*g_iSelected\s*\]\s*\)')
        self.assertRegex(self.lua, r'Steam\.GetCloudSaves\s*\(\s*\)')
        self.assertIn("Steam.GetCloudSaveFileName", self.lua)
        self.assertIn("Modding.CanLoadCloudSave", self.lua)
        self.assertIn("Modding.GetCloudSaveRequirements", self.lua)
        self.assertIn("Modding.CanLoadSavedGame", self.lua)
        self.assertIn("Modding.GetSavedGameRequirements", self.lua)
        self.assertIn("ContextPtr:LookUpControl(\"..\"):GetID()", self.lua)
        self.assertIn('g_IsInGame = (contextID == "GameMenu")', self.lua)
        self.assertNotRegex(self.lua, r'UI\.(?:inc|dec)TurnTimerSemaphore')
        self.assertIn("Events.PlayerChoseToLoadGame", metadata["requiredNativeApis"])
        self.assertIn("Steam.GetCloudSaves", metadata["requiredNativeApis"])
        self.assertIn("UNCONNECTED", metadata["loadEventPolicy"])
        self.assertIn("OPTIONAL_OWNED_CATALOG_CAPABILITY", metadata["deletePolicy"])
        self.assertIn("NO_RUNTIME_PROOF", metadata["deletePolicy"])
        self.assertIs(metadata["deleteRuntimeVerified"], False)
        self.assertIn("UI.DeleteSavedGame", metadata["requiredNativeApis"])
        self.assertIn("UNCONNECTED", metadata["cloudPolicy"])


if __name__ == "__main__":
    unittest.main()
