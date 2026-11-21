"""Reject stale, obscured, or semantically different original popup click evidence."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from verify_interactive_decisions import popup_click_snapshot, research_callback_targets


def target(key, control_id, rect):
    left, top, right, bottom = rect
    return {"key": key, "id": control_id, "event": "LeftClick", "visible": True,
            "disabled": False, "void1": 1, "void2": 0,
            "clippedBounds": {"x": left, "y": top, "width": right-left, "height": bottom-top}}


class PopupNativeHit(unittest.TestCase):
    def setUp(self):
        self.scene = {"context": "research-tree", "generation": 10,
                      "targets": [target(790, "TechButton", (430, 270, 700, 330)),
                                  target(870, "B2", (532, 286.5, 577, 331.5))],
                      "hit_regions": [[790, 430, 270, 700, 330], [870, 532, 286.5, 577, 331.5]]}
        self.inputs = [("10", "1", "870", "1")]
        self.posts = [("10", "790", "376", "200")]

    def verify(self, scene=None, inputs=None, posts=None):
        return popup_click_snapshot([self.scene if scene is None else scene],
                                    self.inputs if inputs is None else inputs,
                                    self.posts if posts is None else posts, "research-tree", 790)

    def test_topmost_child_and_unobscured_parent(self):
        _, requested, delivered = self.verify()
        self.assertEqual((requested["key"], delivered["key"]), (790, 870))
        _, requested, delivered = self.verify(inputs=[("10", "1", "790", "1")],
                                              posts=[("10", "790", "300", "190")])
        self.assertEqual(requested, delivered)

    def test_reject_unbound_dispatch(self):
        cases = [
            {"inputs": [("9", "1", "870", "1")]},
            {"inputs": self.inputs * 2},
            {"inputs": [("10", "1", "870", "0")]},
            {"inputs": [("10", "1", "790", "1")]},
            {"posts": self.posts * 2},
            {"posts": [("10", "790", "0", "0")]},
            {"posts": [("10", "790", "300", "190")]},
        ]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(RuntimeError):
                self.verify(**case)

    def test_reject_changed_retained_hit(self):
        for change in ("clip", "hidden", "duplicate", "missing", "order"):
            scene = copy.deepcopy(self.scene)
            if change == "clip": scene["targets"][1]["clippedBounds"]["x"] += 1
            if change == "hidden": scene["targets"][1]["visible"] = False
            if change == "duplicate": scene["targets"].append(copy.deepcopy(scene["targets"][1]))
            if change == "missing": scene["hit_regions"].pop()
            if change == "order": scene["hit_regions"].reverse()
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                self.verify(scene=scene)

    def test_reject_different_research_semantics(self):
        requested, delivered = self.scene["targets"]
        for field, value in (("void1", 2), ("void2", 1), ("id", "OpenTTButton"), ("id", "B99")):
            altered = dict(delivered, **{field: value})
            with self.subTest(field=field, value=value), self.assertRaises(RuntimeError):
                research_callback_targets(requested, altered, 1, "local maxSmallButtons = 5", research_tree=True)
        with self.assertRaises(RuntimeError):
            research_callback_targets(requested, delivered, 1, "local maxSmallButtons = 5", research_tree=True)


if __name__ == "__main__":
    unittest.main()
