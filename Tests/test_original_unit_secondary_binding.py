"""Bind a repeated retained SecondaryButton to its unique actual posted generation."""
import copy
from pathlib import Path
import re
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_interactive_decisions import verify_original_unit_action


def fixture():
    text = "\n".join([
        "INTERACTIVE_GAME_STARTED=0|0|64|64", "INTERACTIVE_UNIT_SELECTED=0|7|2|4",
        *[f"INTERACTIVE_GPU_SCENE_COMMITTED={n}|99" for n in range(1, 5)],
        "INTERACTIVE_UI_FRAME=13|4|0|unit-panel|11|99|snapshot|folder",
        "INTERACTIVE_ORIGINAL_UNIT_SECONDARY_TARGET=25", "INTERACTIVE_SMOKE_BUTTON=4|25|1|0",
        "INTERACTIVE_SMOKE_POSTED=4|25|18|596", "INTERACTIVE_UNIT_PANEL_INPUT=4|1|25|1",
        "INTERACTIVE_GPU_SCENE_COMMITTED=5|99", "INTERACTIVE_ORIGINAL_UNIT_ACTION_TARGET=7|17|86",
        "INTERACTIVE_UNIT_ACTION_TARGET=7|7|86|0|5", "INTERACTIVE_SMOKE_BUTTON=5|86|1|0",
        "INTERACTIVE_SMOKE_POSTED=5|86|58|542", "INTERACTIVE_ORIGINAL_UNIT_ACTION=0|7|0|17",
        "INTERACTIVE_UNIT_PANEL_INPUT=5|1|86|1", "INTERACTIVE_UNIT_ACTION_OBSERVED=7|7|0|2|0",
        "INTERACTIVE_UNIT_ACTION_SMOKE_VERIFIED=7|7|0|2", ""])
    ui = [{"context": "unit-panel", "generation": generation, "sequence": generation * 4 - 3,
           "turn": 0, "snapshot_active": True, "timer_semaphore": 0,
           "targets": [{"key": 25, "id": "SecondaryButton", "event": "LeftClick",
                        "visible": True, "disabled": False,
                        "clippedBounds": {"x": 10, "y": 878, "width": 36, "height": 32}}],
           "hit_regions": [[25, 10, 878, 46, 910]]} for generation in range(1, 5)]
    ui.append({"context": "unit-panel", "generation": 5, "sequence": 17, "turn": 0,
               "snapshot_active": True, "timer_semaphore": 0,
               "targets": [{"key": 86, "id": "UnitActionButton", "event": "LeftClick", "void1": 17,
                            "visible": True, "disabled": False}], "hit_regions": [[86, 50, 800, 110, 850]]})
    return text, ui


def verify(text, ui):
    starts = re.findall(r"^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$", text, re.M)
    selected = re.findall(r"^INTERACTIVE_UNIT_SELECTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$", text, re.M)
    posted = re.findall(r"^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$", text, re.M)
    return verify_original_unit_action(text, ui, starts, selected, posted, [])


class OriginalSecondaryBinding(unittest.TestCase):
    def test_repeated_visible_frames_bind_only_actual_generation(self):
        proof = verify(*fixture())
        self.assertEqual(proof["secondary_button"], {"key": 25, "generation": 4, "scene_sequence": 13})

    def test_missing_duplicate_post_input_or_target_rejected(self):
        text, ui = fixture()
        for marker in ("INTERACTIVE_ORIGINAL_UNIT_SECONDARY_TARGET=25\n",
                       "INTERACTIVE_SMOKE_POSTED=4|25|18|596\n", "INTERACTIVE_UNIT_PANEL_INPUT=4|1|25|1\n"):
            for replacement in ("", marker * 2):
                with self.subTest(marker=marker, replacement=replacement), self.assertRaises(RuntimeError):
                    verify(text.replace(marker, replacement), ui)

    def test_wrong_stale_or_future_generation_rejected(self):
        text, ui = fixture()
        cases = [text.replace("POSTED=4|25", "POSTED=3|25"),
                 text.replace("INPUT=4|1|25", "INPUT=3|1|25"),
                 text.replace("BUTTON=4|25", "BUTTON=3|25").replace("POSTED=4|25", "POSTED=3|25").replace("INPUT=4|1|25", "INPUT=3|1|25"),
                 text.replace("BUTTON=4|25", "BUTTON=5|25").replace("POSTED=4|25", "POSTED=5|25").replace("INPUT=4|1|25", "INPUT=5|1|25")]
        for changed in cases:
            with self.subTest(changed=changed), self.assertRaises(RuntimeError): verify(changed, ui)

    def test_callback_payload_hit_and_scene_identity_rejected(self):
        for change in ("callback", "duplicate", "disabled", "clip", "obscured", "turn", "timer", "scene", "action_payload"):
            text, ui = fixture(); selected = ui[3]
            if change == "callback": selected["targets"][0]["id"] = "InventedButton"
            if change == "duplicate": selected["targets"].append(copy.deepcopy(selected["targets"][0]))
            if change == "disabled": selected["targets"][0]["disabled"] = True
            if change == "clip": selected["targets"][0]["clippedBounds"]["x"] += 1
            if change == "obscured": selected["hit_regions"].append([55, 10, 878, 46, 910])
            if change == "turn": selected["turn"] = 1
            if change == "timer": selected["timer_semaphore"] = 1
            if change == "scene": ui.append(copy.deepcopy(selected))
            if change == "action_payload": ui[4]["targets"][0]["void1"] = 99
            with self.subTest(change=change), self.assertRaises(RuntimeError): verify(text, ui)

    def test_outside_or_wrong_kind_unconsumed_input_rejected(self):
        text, ui = fixture()
        for old, new in (("POSTED=4|25|18|596", "POSTED=4|25|999|999"),
                         ("INPUT=4|1|25|1", "INPUT=4|5|25|1"),
                         ("INPUT=4|1|25|1", "INPUT=4|1|25|0"),
                         ("INPUT=4|1|25|1", "INPUT=4|1|26|1")):
            with self.subTest(new=new), self.assertRaises(RuntimeError): verify(text.replace(old, new), ui)

    def test_post_and_callback_order_rejected(self):
        text, ui = fixture()
        for first, second in (("INTERACTIVE_SMOKE_BUTTON=4|25|1|0", "INTERACTIVE_SMOKE_POSTED=4|25|18|596"),
                              ("INTERACTIVE_SMOKE_POSTED=4|25|18|596", "INTERACTIVE_UNIT_PANEL_INPUT=4|1|25|1")):
            changed = text.replace(first, "SWAP").replace(second, first).replace("SWAP", second)
            with self.subTest(first=first), self.assertRaises(RuntimeError): verify(changed, ui)


if __name__ == "__main__":
    unittest.main()
