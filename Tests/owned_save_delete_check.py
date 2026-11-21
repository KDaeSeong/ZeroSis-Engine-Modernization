"""Original-Lua confirmation, ownership, refresh and failure regression checks."""
import json
import unittest

from owned_save_delete_scene import verify_component
from load_menu_scene import verify_component as verify_legacy_load_menu
from save_menu_scene import verify_component as verify_legacy_save_menu


class OwnedSaveDeleteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = verify_component()

    def test_original_confirmation_and_independent_mock_deletion_service(self):
        result = self.result
        self.assertEqual(result["status"], "PASS_ORIGINAL_OWNED_SAVE_DELETE_LUA_FIXTURES")
        self.assertEqual(len(result["cases"]), 10)
        for row in result["cases"]:
            with self.subTest(menu=row["menu"], case=row["case"]):
                self.assertGreater(row["checks"], 50)
                self.assertEqual(row["capabilityQueries"], 1)
                self.assertEqual(row["timerChanges"], 0)
                self.assertEqual(row["realArchiveDeletes"], 0)
                self.assertFalse(row["nativeHostOrGameCoreExecuted"])
                self.assertEqual(len(row["deleteCalls"]), 0 if row["case"] == "unsupported" else 1)
                self.assertEqual(row["remainingCount"], 0 if row["case"] == "empty-after-delete" else
                                 2 if row["case"] == "supported" else 3)

    def test_snapshot_support_is_the_bound_capability(self):
        for row in self.result["cases"]:
            meta = row["metadata"]
            with self.subTest(menu=row["menu"], case=row["case"]):
                self.assertTrue(meta["localDeleteImplemented"])
                bound = row["case"] != "unsupported"
                self.assertEqual(meta["localDeleteBackendBound"], bound)
                self.assertEqual("delete" in meta["unsupportedActions"], not bound)
                if row["menu"] == "SaveMenu":
                    self.assertIn("overwrite", meta["unsupportedActions"])
                self.assertFalse(meta.get("retailBackendVerified", False))

    def test_invalid_native_capability_and_eligibility_are_rejected(self):
        for menu in ("SaveMenu", "LoadMenu"):
            for case, message in (("invalid-capability", "delete capability must be a boolean"),
                                  ("invalid-eligibility", "deletion eligibility must be a boolean")):
                with self.subTest(menu=menu, case=case), self.assertRaisesRegex(RuntimeError, message):
                    verify_component(menus=(menu,), cases=(case,))

    def test_sources_and_temporary_files_are_preserved_or_removed_as_required(self):
        result = self.result
        self.assertTrue(result["original_sources_unchanged"])
        self.assertTrue(result["temporary_styles_removed"])
        self.assertTrue(all(row["result"] == "REMOVED_ABSENT" for row in result["temporary_cleanup"]))
        self.assertFalse(result["retail_user_state_accessed"])
        self.assertEqual(result["real_archive_deletes"], 0)

    def test_existing_save_menu_supported_false_regression(self):
        result = verify_legacy_save_menu()
        self.assertEqual(result["status"], "PASS_ORIGINAL_SAVE_MENU_COMPONENT")
        self.assertTrue(result["temporary_styles_removed"])
        self.assertEqual(result["archiveWrites"], 0)

    def test_existing_load_menu_supported_false_regression(self):
        result = verify_legacy_load_menu()
        self.assertEqual(result["status"], "PASS_COMPLETE_ORIGINAL_LOAD_MENU_LUA_FIXTURES")
        self.assertTrue(result["temporary_styles_removed"])
        self.assertEqual(result["archive_writes"], 0)


if __name__ == "__main__":
    program = unittest.main(exit=False)
    if program.result.wasSuccessful():
        result = OwnedSaveDeleteTests.result
        print(json.dumps({"status": result["status"], "checks": result["checks"],
                          "case_count": len(result["cases"]), "unit_tests": program.result.testsRun,
                          "compositor_stages": {row["menu"]: row["compositorContractStages"]
                                                for row in result["cases"] if "compositorContractStages" in row},
                          "source_sha256": result["source_sha256"]["scene"],
                          "temporary_styles_removed": result["temporary_styles_removed"],
                          "real_archive_deletes": result["real_archive_deletes"]}, ensure_ascii=False))
    raise SystemExit(0 if program.result.wasSuccessful() else 1)
