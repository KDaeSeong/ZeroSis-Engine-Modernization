from __future__ import annotations

import hashlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import sys
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
import verify_interactive_action_info_panel as verifier


def end_turn_target(event: str) -> dict:
    return {"key": 2, "id": "EndTurnButton", "visible": True, "disabled": False, "event": event,
            "bounds": {"x": 1584, "y": 844, "width": 320, "height": 36},
            "clippedBounds": {"x": 1584, "y": 844, "width": 320, "height": 36}}


class OriginalAssetReferenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.asset = Path(self.temp.name) / "Assets" / "DLC" / "Expansion2" / "UI" / "InGame" / "WorldView" / "ActionInfoPanel.lua"
        self.asset.parent.mkdir(parents=True)
        self.asset.write_bytes(b"original source fixture\n")
        self.sha = hashlib.sha256(self.asset.read_bytes()).hexdigest()
        self.artifact_patch = patch.object(verifier, "artifact_ref", side_effect=lambda ref, **kwargs: self.asset)
        self.artifact_patch.start()
        self.addCleanup(self.artifact_patch.stop)

    def test_prepared_path_sha_schema_without_bytes_is_accepted(self) -> None:
        ref = {"path": str(self.asset), "sha256": self.sha}
        self.assertNotIn("bytes", ref)
        self.assertEqual(verifier.verify_original_asset_ref(
            ref, "Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.lua", "originalLua"),
            self.asset)

    def test_tampered_sha_is_rejected(self) -> None:
        ref = {"path": str(self.asset), "sha256": "0" * 64}
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_original_asset_ref(
                ref, "Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.lua", "originalLua")

    def test_wrong_optional_byte_count_is_rejected(self) -> None:
        ref = {"path": str(self.asset), "sha256": self.sha, "bytes": self.asset.stat().st_size + 1}
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_original_asset_ref(
                ref, "Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.lua", "originalLua")

    def test_malformed_optional_byte_count_is_rejected(self) -> None:
        for malformed in (0, True, "24"):
            with self.subTest(bytes=malformed):
                ref = {"path": str(self.asset), "sha256": self.sha, "bytes": malformed}
                with self.assertRaises(verifier.VerificationError):
                    verifier.verify_original_asset_ref(
                        ref, "Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.lua", "originalLua")

    def test_correct_optional_byte_count_is_accepted(self) -> None:
        ref = {"path": str(self.asset), "sha256": self.sha, "bytes": self.asset.stat().st_size}
        self.assertEqual(verifier.verify_original_asset_ref(
            ref, "Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.lua", "originalLua"),
            self.asset)

    def test_xml_controls_without_id_match_empty_snapshot_id(self) -> None:
        source = ET.fromstring('<Context ColorSet="Beige"><Grid ID="Action" /></Context>')
        captured = {
            "kind": "Context", "id": "", "sourceAttributes": {"ColorSet": "Beige"},
            "children": [{"kind": "Grid", "id": "Action", "sourceAttributes": {"ID": "Action"}, "children": []}],
        }
        self.assertTrue(verifier.xml_tree_matches(source, captured))

    def test_xml_tree_rejects_unexpected_nonempty_root_id(self) -> None:
        source = ET.fromstring('<Context ColorSet="Beige" />')
        captured = {"kind": "Context", "id": "Unexpected", "sourceAttributes": {"ColorSet": "Beige"}, "children": []}
        self.assertFalse(verifier.xml_tree_matches(source, captured))

    def test_original_button_requires_both_distinct_click_callbacks(self) -> None:
        inputs = [end_turn_target("LeftClick"), end_turn_target("RightClick")]
        self.assertEqual(verifier.require_end_turn_targets(inputs, 2), inputs)

    def test_original_button_rejects_missing_duplicate_or_disabled_callback(self) -> None:
        left, right = end_turn_target("LeftClick"), end_turn_target("RightClick")
        for inputs in ([left], [left, left], [left, {**right, "disabled": True}]):
            with self.subTest(inputs=inputs):
                with self.assertRaises(verifier.VerificationError):
                    verifier.require_end_turn_targets(inputs, 2)

    def test_extra_hidden_callback_cannot_hide_behind_two_valid_rows(self) -> None:
        inputs = [end_turn_target("LeftClick"), end_turn_target("RightClick"),
                  {**end_turn_target("LeftClick"), "visible": False}]
        with self.assertRaises(verifier.VerificationError):
            verifier.require_end_turn_targets(inputs, 2)

    def test_both_callback_rows_require_exact_geometry_and_identity(self) -> None:
        for index in (0, 1):
            for field, wrong in (
                ("bounds", {"x": 0, "y": 844, "width": 320, "height": 36}),
                ("clippedBounds", {"x": 0, "y": 844, "width": 320, "height": 36}),
                ("id", "DifferentButton"), ("key", 3), ("visible", False),
                ("disabled", True), ("event", "MouseEnter"),
            ):
                with self.subTest(row=index, field=field):
                    inputs = [end_turn_target("LeftClick"), end_turn_target("RightClick")]
                    inputs[index][field] = wrong
                    with self.assertRaises(verifier.VerificationError):
                        verifier.require_end_turn_targets(inputs, 2)

    def test_local_packet_key_maps_to_exact_global_target_key(self) -> None:
        verifier.require_global_key(verifier.KEY_BASE + 2, 2)
        verifier.require_packet_end_turn_hit([(2, (1584.0, 844.0, 1904.0, 880.0))], 2)
        with self.assertRaises(verifier.VerificationError):
            verifier.require_global_key(verifier.KEY_BASE + 3, 2)
        with self.assertRaises(verifier.VerificationError):
            verifier.require_packet_end_turn_hit([(verifier.KEY_BASE + 2, (1584.0, 844.0, 1904.0, 880.0))], 2)

    def test_native_input_marker_matches_global_target_and_button_kind(self) -> None:
        output = "INTERACTIVE_SMOKE_BUTTON=9|4503599627370498|1|0\n"
        verifier.require_native_button_marker(output, 9, verifier.KEY_BASE + 2, "unit-left")
        for malformed in (
            "INTERACTIVE_SMOKE_BUTTON=9|2|1|0\n",
            "INTERACTIVE_SMOKE_BUTTON=9|4503599627370498|5|0\n",
            "INTERACTIVE_SMOKE_BUTTON=9|4503599627370498|1|1\n",
        ):
            with self.subTest(output=malformed):
                with self.assertRaises(verifier.VerificationError):
                    verifier.require_native_button_marker(malformed, 9, verifier.KEY_BASE + 2, "unit-left")


class PublishedWorldAndStateTests(unittest.TestCase):
    COMMIT = "INTERACTIVE_GPU_SCENE_COMMITTED=9|42\n"
    WORLD = "INTERACTIVE_WORLD_FRAME=6|9|1|2|1|42|9|0|1\n"
    ACTION = "INTERACTIVE_ACTION_INFO_PANEL_FRAME=12|9|1|0|99|42|snapshot.json|snapshot\n"

    def check_world(self, output: str) -> None:
        frame = verifier.FRAME.search(output)
        self.assertIsNotNone(frame)
        row = verifier.require_published_world_frame(output, frame)
        self.assertEqual((int(row[1]), int(row[2]), int(row[3]), int(row[6])), (6, 9, 1, 42))

    def test_committed_world_and_action_frame_share_exact_generation_turn_device(self) -> None:
        self.check_world(self.COMMIT + self.WORLD + self.ACTION)

    def test_missing_duplicate_stale_or_reordered_world_commit_is_rejected(self) -> None:
        malformed = (
            self.WORLD + self.ACTION,
            self.COMMIT + self.ACTION,
            self.COMMIT + self.COMMIT + self.WORLD + self.ACTION,
            self.COMMIT + self.WORLD + self.WORLD + self.ACTION,
            self.COMMIT.replace("9|42", "8|42") + self.WORLD + self.ACTION,
            self.COMMIT.replace("9|42", "9|43") + self.WORLD + self.ACTION,
            self.COMMIT + self.WORLD.replace("6|9|1", "6|8|1") + self.ACTION,
            self.COMMIT + self.WORLD.replace("6|9|1", "6|9|2") + self.ACTION,
            self.COMMIT + self.WORLD.replace("|42|9|", "|43|9|") + self.ACTION,
            self.COMMIT + self.ACTION + self.WORLD,
            self.WORLD + self.COMMIT + self.ACTION,
        )
        for output in malformed:
            with self.subTest(output=output):
                with self.assertRaises(verifier.VerificationError):
                    verifier.require_published_world_frame(output, verifier.FRAME.search(output))

    def test_published_world_contains_exact_namespaced_original_hit(self) -> None:
        world = {"hits": [[123, 0, 0, 20, 20], [verifier.KEY_BASE + 2, 1584, 844, 1904, 880]]}
        verifier.require_world_end_turn_hit(world, verifier.KEY_BASE + 2, 2)

    def test_valid_packet_does_not_substitute_for_missing_or_tampered_world_hit(self) -> None:
        verifier.require_packet_end_turn_hit([(2, (1584.0, 844.0, 1904.0, 880.0))], 2)
        good = [verifier.KEY_BASE + 2, 1584, 844, 1904, 880]
        for hits in (
            [], [[2, *good[1:]]], [[verifier.KEY_BASE + 3, *good[1:]]],
            [[good[0], 0, *good[2:]]], [good, good],
            [good, [verifier.KEY_BASE, 0, 0, 1, 1]],
        ):
            with self.subTest(hits=hits):
                with self.assertRaises(verifier.VerificationError):
                    verifier.require_world_end_turn_hit({"hits": hits}, verifier.KEY_BASE + 2, 2)

    @staticmethod
    def state() -> tuple[dict, dict, dict]:
        info = {"owner": 0, "turn": 1, "blockingType": 3,
                "blockingNotification": -1, "canEndTurn": False}
        world = {"turn": 1, "elapsed": 1, "activePlayer": 0, "gridWidth": 40, "gridHeight": 24}
        expected = {"owner": 0, "turn": 1, "blocker": 3, "notification": -1,
                    "phase": "unit-right", "sdk_identity": (1, 1, 0, 960)}
        return info, world, expected

    def test_snapshot_state_matches_actual_target_frame_and_sdk_identity(self) -> None:
        info, world, expected = self.state()
        verifier.require_action_info_state(info, world, **expected)
        info.update(blockingType=-1, canEndTurn=True)
        expected.update(blocker=-1, phase="end-turn")
        verifier.require_action_info_state(info, world, **expected)

    def test_snapshot_state_cannot_disagree_with_actual_target_or_frame(self) -> None:
        for field, wrong in (("owner", 1), ("turn", 2), ("blockingType", -1),
                             ("blockingNotification", 0), ("canEndTurn", True), ("owner", False)):
            with self.subTest(field=field, wrong=wrong):
                info, world, expected = self.state()
                info[field] = wrong
                with self.assertRaises(verifier.VerificationError):
                    verifier.require_action_info_state(info, world, **expected)

    def test_consistent_ui_frame_cannot_substitute_for_actual_sdk_identity(self) -> None:
        info, world, expected = self.state()
        info["turn"] = world["turn"] = expected["turn"] = 2
        with self.assertRaises(verifier.VerificationError):
            verifier.require_action_info_state(info, world, **expected)
        for field, wrong in (("elapsed", 2), ("activePlayer", 1), ("gridWidth", 41)):
            with self.subTest(field=field):
                info, world, expected = self.state()
                world[field] = wrong
                with self.assertRaises(verifier.VerificationError):
                    verifier.require_action_info_state(info, world, **expected)

    def test_end_turn_readiness_is_required_after_all_actual_blockers_clear(self) -> None:
        info, world, expected = self.state()
        info["blockingType"] = expected["blocker"] = -1
        expected["phase"] = "end-turn"
        with self.assertRaises(verifier.VerificationError):
            verifier.require_action_info_state(info, world, **expected)


if __name__ == "__main__":
    unittest.main()
