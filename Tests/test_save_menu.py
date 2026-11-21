"""Focused original-screen and Unicode-input component checks."""
import copy
import unittest
import xml.etree.ElementTree as ET

from save_menu_scene import sdk_game_types, verify_component
from prepare_ui_popup_assets import (
    GAME, KINDS, LAYOUTS, SCRIPTS, SAVE_MENU_LUA, SAVE_MENU_XML,
    UNIQUE_BONUSES_LUA, save_menu_control_tree,
)


class SaveMenuTests(unittest.TestCase):
    def test_immutable_original_assets_and_real_includes_are_registered(self):
        self.assertIn(("SaveMenu", SAVE_MENU_LUA), SCRIPTS)
        self.assertIn(("UniqueBonuses", UNIQUE_BONUSES_LUA), SCRIPTS)
        self.assertIn(("SaveMenuLayout", SAVE_MENU_XML, "SaveMenu"), LAYOUTS)
        self.assertIn("EditBox", KINDS)
        tree = save_menu_control_tree(ET.parse(GAME / SAVE_MENU_XML).getroot())
        self.assertEqual(tree["saveMenu"]["instanceNames"], ["LoadButton"])
        self.assertEqual(tree["saveMenu"]["parentContext"], "GameMenu")
        self.assertFalse(tree["saveMenu"]["retailLayoutVerified"])
        self.assertEqual(tree["saveMenu"]["unsupportedActions"], ["overwrite", "delete", "cloud", "saveMap"])

    def test_changed_layout_names_length_and_contexts_are_rejected(self):
        original = ET.parse(GAME / SAVE_MENU_XML).getroot()
        for mode in ("length", "caption", "child", "template", "removed"):
            changed = copy.deepcopy(original)
            if mode == "length": changed.find(".//EditBox").set("MaxLength", "64")
            elif mode == "caption": changed.find(".//GridButton[@ID='SaveButton']").set("String", "Save")
            elif mode == "child": changed.find("LuaContext").set("FileName", "Other")
            elif mode == "template": changed.find("Instance").set("Name", "Replacement")
            else: changed.remove(changed.find("LuaContext"))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                save_menu_control_tree(changed)

    def test_original_save_list_edit_cancel_and_enter_components(self):
        result = verify_component(include_snapshot=True)
        self.assertEqual(result["status"], "PASS_ORIGINAL_SAVE_MENU_COMPONENT")
        self.assertGreater(result["checks"], 100)
        self.assertEqual(result["archiveWrites"], 0)
        self.assertEqual(result["timerChanges"], 0)
        self.assertFalse(result["nativeGameVerified"])
        self.assertTrue(result["temporary_styles_removed"])
        self.assertEqual(result["named_snapshot"]["saveMenu"]["name"], "검증 저장")
        self.assertFalse(result["closed_snapshot"]["saveMenu"]["textInputEnabled"])

    def test_missing_or_invalid_native_enum_binding_and_unsupported_session_fail_closed(self):
        self.assertEqual(sdk_game_types(), dict(GAME_TYPE_NONE=-1, GAME_SINGLE_PLAYER=0,
                          GAME_NETWORK_MULTIPLAYER=1, GAME_HOTSEAT_MULTIPLAYER=2, GAME_EMAIL_MULTIPLAYER=3))
        for mode in ("missing", "non_table", "wrong_value", "missing_field", "unsupported_header"):
            message = ("supported SDK single-player session" if mode == "unsupported_header"
                       else "actual SDK game type enum binding")
            with self.subTest(mode=mode), self.assertRaisesRegex(RuntimeError, message):
                verify_component(enum_fixture=mode)


if __name__ == "__main__":
    unittest.main()
