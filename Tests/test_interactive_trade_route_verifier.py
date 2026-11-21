"""Focused tests for stock FromGPT display-to-SDK scalar verification."""
from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))

import verify_interactive_trade_route as verifier


def label(control_id: str, text: str) -> dict:
    return {"id": control_id, "text": text, "children": []}


def snapshot(path: Path, order: tuple[str, ...]) -> dict:
    rows = {
        "North": {"from": "Capital", "to": "North", "raw": 124, "display": "1.2"},
        "South": {"from": "Capital", "to": "South", "raw": 123, "display": "1,2"},
    }
    tree_rows = []
    for destination in order:
        row = rows[destination]
        tree_rows.append({"id": "TRInstance", "children": [
            label("FromCity", row["from"]), label("ToCity", row["to"]),
            label("FromGPT", row["display"]), label("ToGPT", "0.0"),
        ]})
    path.write_text(json.dumps({"tree": {"id": "Root", "children": [
        {"id": "MainStack", "children": tree_rows}
    ]}}), encoding="utf-8")
    return {"path": str(path)}


class FromGptVerifierTests(unittest.TestCase):
    def test_raw_sdk_values_bind_to_one_decimal_display_and_allow_display_ties(self) -> None:
        routes = [
            {"from": "Capital", "to": "North", "from_owner": 0, "to_owner": 1,
             "from_city_id": 10, "to_city_id": 20, "from_gpt": 124},
            {"from": "Capital", "to": "South", "from_owner": 0, "to_owner": 1,
             "from_city_id": 10, "to_city_id": 21, "from_gpt": 123},
        ]
        with tempfile.TemporaryDirectory(prefix="trade-route-sort-", dir=PROJECT) as temporary:
            proof = snapshot(Path(temporary) / "snapshot.json", ("North", "South"))
            result = verifier.verify_from_gpt_rows(proof, routes, ascending=False)
        self.assertEqual(result["sdk_raw_hundredths"], [124, 123])
        self.assertEqual(result["displayed_values"], [1.2, 1.2])
        self.assertEqual([row["displayed_from_gpt_text"] for row in result["rows"]],
                         ["1.2", "1,2"])
        self.assertTrue(result["sdk_raw_hundredths_monotonic"])
        self.assertFalse(result["strict_reordering_claimed"])

    def test_display_must_match_the_mapped_sdk_scalar(self) -> None:
        with self.assertRaises(verifier.VerificationError):
            verifier.parse_from_gpt_display("1.3", 124)

    def test_display_rejects_more_precision_than_stock_format(self) -> None:
        with self.assertRaises(verifier.VerificationError):
            verifier.parse_from_gpt_display("1.24", 124)


class WheelConsumptionTests(unittest.TestCase):
    def test_non_overflow_scroll_panel_consumes_without_changing_offset(self) -> None:
        before = {"maximumScroll": 0, "scrollY": 0}
        after = {"maximumScroll": 0, "scrollY": 0}
        self.assertEqual(verifier.verify_wheel_result(0, before, after, True),
                         "consumed_without_overflow")

    def test_non_overflow_unconsumed_is_rejected(self) -> None:
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_wheel_result(0, {"maximumScroll": 0, "scrollY": 0}, None, False)

    def test_overflow_requires_consumption_and_post_wheel_geometry(self) -> None:
        before = {"maximumScroll": 100, "scrollY": 0}
        with self.assertRaises(verifier.VerificationError):
            verifier.verify_wheel_result(100, before, {"maximumScroll": 100, "scrollY": 20}, False)
        self.assertEqual(verifier.verify_wheel_result(
            100, before, {"maximumScroll": 100, "scrollY": 20}, True), "moved")

    def test_consumed_overflow_at_boundary_is_accepted(self) -> None:
        before = {"maximumScroll": 100, "scrollY": 100}
        after = {"maximumScroll": 100, "scrollY": 100}
        self.assertEqual(verifier.verify_wheel_result(100, before, after, True),
                         "already_at_bottom_boundary")


class TradeRouteDispatchContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.actions = {
            2: {"value": 81}, 3: {"value": 81}, 4: {"value": 18},
            6: {"value": 23}, 7: {"value": 13}, 9: {"value": 133},
        }
        self.events = [
            (2, 81, 0.0), (2, 81, 0.0), (2, 18, 0.0), (4, 126, 48.0),
            (2, 23, 0.0), (2, 13, 0.0), (1, 13, 0.0), (2, 133, 0.0), (1, 27, 0.0),
        ]
        self.decoded = [{"kind": kind, "key": key, "delta": delta, "consumed": True,
                         "active": index < 7, "timer_held": index < 7}
                        for index, (kind, key, delta) in enumerate(self.events)]

    def test_native_kinds_and_converted_wheel_match_requested_controls(self) -> None:
        verifier.verify_trade_route_dispatches(self.decoded, self.actions, 126)

    def test_wrong_native_enum_value_is_rejected(self) -> None:
        wrong_enum = [dict(event) for event in self.decoded]
        wrong_enum[0]["kind"] = 1
        with self.assertRaisesRegex(verifier.VerificationError, "kind/key/delta"):
            verifier.verify_trade_route_dispatches(wrong_enum, self.actions, 126)

    def test_raw_win32_wheel_delta_is_rejected(self) -> None:
        raw_wheel = [dict(event) for event in self.decoded]
        raw_wheel[3]["delta"] = -120.0
        with self.assertRaisesRegex(verifier.VerificationError, "kind/key/delta"):
            verifier.verify_trade_route_dispatches(raw_wheel, self.actions, 126)

    def test_tab_input_must_hit_the_requested_tab_key(self) -> None:
        misrouted = [dict(event) for event in self.decoded]
        misrouted[2]["key"] = 81
        with self.assertRaisesRegex(verifier.VerificationError, "kind/key/delta"):
            verifier.verify_trade_route_dispatches(misrouted, self.actions, 126)


class TradeRouteUiFrameLogParserTests(unittest.TestCase):
    def test_parses_actual_eight_field_trade_route_frame_record(self) -> None:
        line = (r"INTERACTIVE_UI_FRAME=51|41|1|trade-route|7409734|2224004560576|"
                r"C:\Build\sessions\session-id\play-ui-51.json|"
                r"C:\Build\sessions\session-id\play-ui-51")
        parsed = verifier.parse_trade_route_ui_frames(line)
        self.assertEqual(len(parsed), 1)
        self.assertEqual(len(parsed[0]), 8)
        self.assertEqual(parsed[0][:6],
                         ("51", "41", "1", "trade-route", "7409734", "2224004560576"))
        self.assertTrue(parsed[0][6].endswith("play-ui-51.json"))
        self.assertTrue(parsed[0][7].endswith("play-ui-51"))

    def test_rejects_non_trade_route_context_in_frame_records(self) -> None:
        line = "INTERACTIVE_UI_FRAME=51|41|1|city-view|7409734|2|snapshot.json|folder"
        with self.assertRaisesRegex(verifier.VerificationError, "omits TradeRoute retained UI frames"):
            verifier.parse_trade_route_ui_frames(line)

    def test_real_post_action_frame_can_share_next_action_generation(self) -> None:
        return_lines = [
            "INTERACTIVE_TRADE_ROUTE_ACTION=8|KEY_RETURN|13|47|57",
            "INTERACTIVE_TRADE_ROUTE_INPUT=1|13|0|1|1|1|STATE_UNCHANGED",
            (r"INTERACTIVE_UI_FRAME=58|48|1|trade-route|7409734|2224004560576|"
             r"C:\Build\sessions\session-id\play-ui-58.json|C:\Build\sessions\session-id\play-ui-58"),
            "INTERACTIVE_TRADE_ROUTE_ACTION=9|CloseButton|133|48|58",
        ]
        reopen_lines = [
            "INTERACTIVE_TRADE_ROUTE_ACTION=10|InternationalTradeRoutes|2251799813685254|49|59",
            (r"INTERACTIVE_UI_FRAME=60|50|1|trade-route|7409734|2224004560576|"
             r"C:\Build\sessions\session-id\play-ui-60.json|C:\Build\sessions\session-id\play-ui-60"),
            "INTERACTIVE_TRADE_ROUTE_ACTION=11|KEY_ESCAPE|27|50|60",
        ]
        wheel_lines = [
            "INTERACTIVE_TRADE_ROUTE_ACTION=4|TabButtonAvailableTR|18|43|53",
            "INTERACTIVE_TRADE_ROUTE_WHEEL=44|126|-120",
            "INTERACTIVE_TRADE_ROUTE_INPUT=4|126|48|1|1|1|STATE_UNCHANGED",
            (r"INTERACTIVE_UI_FRAME=55|45|1|trade-route|7409734|2224004560576|"
             r"C:\Build\sessions\session-id\play-ui-55.json|C:\Build\sessions\session-id\play-ui-55"),
            "INTERACTIVE_TRADE_ROUTE_ACTION=6|TabButtonTRWithYou|23|45|55",
        ]
        for lines, lower, upper, tab in ((return_lines, 47, 48, "YourTR"),
                                         (reopen_lines, 49, 50, "YourTR"),
                                         (wheel_lines, 44, 45, "AvailableTR")):
            with self.subTest(lower=lower):
                log = "\n".join(lines)
                frame = verifier.parse_trade_route_ui_frames(log)[0]
                action_pattern = re.compile(
                    r"^INTERACTIVE_TRADE_ROUTE_ACTION=(\d+)\|[^|]+\|(-?\d+)\|(\d+)\|(\d+)$", re.M)
                actions = action_pattern.findall(log)
                self.assertEqual(len(actions), 2)
                frame_position = log.index("INTERACTIVE_UI_FRAME=")
                self.assertLess(log.index(lines[0]), frame_position)
                self.assertLess(frame_position, log.index(lines[-1]))
                self.assertEqual(int(actions[1][2]), upper)
                if lower == 44:
                    wheel = re.search(r"^INTERACTIVE_TRADE_ROUTE_WHEEL=(\d+)\|", log, re.M)
                    self.assertEqual(int(wheel.group(1)), lower)
                    self.assertLess(wheel.start(), frame_position)
                else:
                    self.assertEqual(int(actions[0][2]), lower)
                proof = {"generation": int(frame[1]), "selected_tab": tab}
                self.assertEqual(verifier.snapshots_between_action_generations(
                    [proof], lower, upper), [proof])


class TradeRouteScrollTargetTests(unittest.TestCase):
    @staticmethod
    def record() -> dict:
        return {"key": 126, "id": "MainScroll", "event": "Scroll", "orientation": "vertical",
                "bounds": {"x": 482, "y": 341.5, "width": 956, "height": 400},
                "clippedBounds": {"x": 482, "y": 341.5, "width": 956, "height": 400},
                "scrollY": 0, "contentHeight": 68, "viewportHeight": 400, "maximumScroll": 0}

    def test_accepts_full_scroll_target_copied_from_main_scroll_metadata(self) -> None:
        main = self.record()
        target = dict(main, visible=True, disabled=False)
        verifier.validate_trade_route_scroll_target([target], main)

    def test_rejects_missing_or_changed_scroll_metadata(self) -> None:
        main = self.record()
        target = dict(main, visible=True, disabled=False)
        for altered in (dict(target, contentHeight=69),
                        {key: value for key, value in target.items() if key != "clippedBounds"},
                        dict(target, disabled=True), dict(target, visible=False),
                        dict(target, unexpected=True)):
            with self.subTest(altered=altered), self.assertRaises(verifier.VerificationError):
                verifier.validate_trade_route_scroll_target([altered], main)

    def test_accepts_actual_225105_trade_route_snapshot_schema(self) -> None:
        path = (PROJECT / "Build/InteractiveGameRuntime/20261008T225105Z_a09bb643b908/"
                "sessions/099511affc61c53a2f1816dd0c334110/play-ui-51.json")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        main = snapshot["tradeRoute"]["mainScroll"]
        target = snapshot["scrollTargets"][0]
        verifier.validate_trade_route_scroll_target(snapshot["scrollTargets"], main)
        self.assertEqual({key: target[key] for key in main}, main)
        self.assertIs(target["visible"], True)
        self.assertIs(target["disabled"], False)


class TradeRouteComponentLayoutContractTests(unittest.TestCase):
    def test_requires_fixture_proof_that_headers_start_below_tabs(self) -> None:
        verifier.validate_trade_route_tab_geometry_fixture(
            {"columnHeadersDoNotOverlapTabs": True})
        for fixture in ({"columnHeadersDoNotOverlapTabs": False}, {}, None):
            with self.subTest(fixture=fixture), self.assertRaises(verifier.VerificationError):
                verifier.validate_trade_route_tab_geometry_fixture(fixture)


class TradeRouteTabCaptionProofTests(unittest.TestCase):
    def setUp(self) -> None:
        self.snapshot, self.manifest = self.fixture()

    @staticmethod
    def fixture() -> tuple[dict, dict]:
        ids = ("TabButtonYourTR", "TabButtonAvailableTR", "TabButtonTRWithYou")
        tabs, targets, labels, geometry = [], [], [], []
        for index, control_id in enumerate(ids):
            key = 207 + index * 13
            text_key = f"TXT_KEY_{control_id.upper()}"
            bounds = {"x": 20 + index * 130, "y": 10, "width": 120, "height": 30}
            tabs.append({"id": control_id, "key": key, "kind": "Button", "hidden": False,
                         "x": bounds["x"], "y": bounds["y"], "width": bounds["width"],
                         "height": bounds["height"], "text": f"Tab {index + 1}",
                         "attributes": {"ID": control_id, "String": text_key},
                         "sourceAttributes": {"ID": control_id, "String": text_key}})
            targets.append({"key": key, "id": control_id, "event": "LeftClick",
                            "visible": True, "disabled": False, "bounds": bounds})
            labels.append({"key": key, "text": f"Tab {index + 1}", "glyph_count": 6,
                           "text_control": "Button", "text_control_id": control_id,
                           "retail_text_alignment_verified": False,
                           "bounds": [bounds["x"] + 10, bounds["y"] + 8, 90, 14]})
            geometry.append({"key": key, "kind": "Button", "id": control_id,
                             "style_decoration": False,
                             "bounds": [bounds["x"], bounds["y"],
                                                        bounds["width"], bounds["height"]],
                             "input_target": True})
        headers = [{"id": control_id, "kind": "Button", "key": 500 + index, "x": 10, "y": 50,
                    "width": 110, "height": 24}
                   for index, control_id in enumerate(sorted(verifier.SORT_TARGETS))]
        row_labels = [{"id": "FromGPT", "kind": "Label", "key": 900 + index,
                       "x": 10, "y": 5, "width": 40, "height": 12}
                      for index in range(2)]
        return ({"tree": {"id": "Root", "hidden": False,
                           "children": tabs + headers + row_labels},
                 "inputTargets": targets},
                {"labels": labels, "geometry": geometry,
                 "trade_route_scene": {"retail_pixels_verified": False}})

    def test_accepts_caption_glyphs_and_separated_headers(self) -> None:
        proof = verifier.verify_trade_route_tab_caption_proof(self.snapshot, self.manifest)
        self.assertEqual({row["id"] for row in proof["captions"]}, set(verifier.TAB_TARGETS))
        self.assertTrue(proof["headers_below_tabs"])
        self.assertEqual(proof["tab_bottom_y"], 40)
        self.assertFalse(proof["retail_pixel_equivalence_verified"])

    def test_rejects_missing_or_unrendered_caption(self) -> None:
        self.manifest["labels"].pop()
        with self.assertRaisesRegex(verifier.VerificationError, "glyph proof"):
            verifier.verify_trade_route_tab_caption_proof(self.snapshot, self.manifest)
        self.setUp()
        self.manifest["labels"][0]["glyph_count"] = 0
        with self.assertRaisesRegex(verifier.VerificationError, "glyph proof"):
            verifier.verify_trade_route_tab_caption_proof(self.snapshot, self.manifest)

    def test_rejects_caption_clipped_outside_button(self) -> None:
        self.manifest["labels"][0]["bounds"] = [130, 15, 20, 10]
        with self.assertRaisesRegex(verifier.VerificationError, "clipped outside"):
            verifier.verify_trade_route_tab_caption_proof(self.snapshot, self.manifest)

    def test_rejects_wrong_caption_or_original_source_string(self) -> None:
        self.manifest["labels"][0]["text"] = "Wrong"
        with self.assertRaisesRegex(verifier.VerificationError, "glyph proof"):
            verifier.verify_trade_route_tab_caption_proof(self.snapshot, self.manifest)
        self.setUp()
        self.snapshot["tree"]["children"][0]["sourceAttributes"]["String"] = "TXT_KEY_WRONG"
        with self.assertRaisesRegex(verifier.VerificationError, "source caption"):
            verifier.verify_trade_route_tab_caption_proof(self.snapshot, self.manifest)

    def test_rejects_header_overlapping_tab_row(self) -> None:
        header = next(node for node in self.snapshot["tree"]["children"]
                      if node["id"] in verifier.SORT_TARGETS)
        header["y"] = 39
        with self.assertRaisesRegex(verifier.VerificationError, "overlaps"):
            verifier.verify_trade_route_tab_caption_proof(self.snapshot, self.manifest)

    def test_rejects_changed_hit_geometry(self) -> None:
        self.manifest["geometry"][0]["bounds"][2] -= 1
        with self.assertRaisesRegex(verifier.VerificationError, "hit geometry changed"):
            verifier.verify_trade_route_tab_caption_proof(self.snapshot, self.manifest)

    def test_ignores_same_key_style_decoration_but_requires_one_hit_button_row(self) -> None:
        primary = self.manifest["geometry"][0]
        decoration = dict(primary, kind="Image", id="TabTexture", style_decoration=True,
                          input_target=False)
        self.manifest["geometry"].append(decoration)
        verifier.verify_trade_route_tab_caption_proof(self.snapshot, self.manifest)
        self.manifest["geometry"].append(dict(primary))
        with self.assertRaisesRegex(verifier.VerificationError, "unique non-decoration"):
            verifier.verify_trade_route_tab_caption_proof(self.snapshot, self.manifest)

    def test_manifest_must_be_hash_verified_in_exact_frame_folder(self) -> None:
        with tempfile.TemporaryDirectory(prefix="trade-route-caption-frame-", dir=PROJECT) as temporary:
            session = Path(temporary).resolve()
            folder = session / "play-ui-51"
            folder.mkdir()
            snapshot = session / "play-ui-51.json"
            snapshot.write_text("{}", encoding="utf-8")
            manifest = folder / "scene_manifest.json"
            manifest.write_text("{}", encoding="utf-8")
            generated = {snapshot.resolve(), manifest.resolve()}
            self.assertEqual(verifier.trade_route_frame_manifest(
                snapshot.resolve(), str(folder), generated, session), manifest.resolve())
            with self.assertRaisesRegex(verifier.VerificationError, "SHA-verified"):
                verifier.trade_route_frame_manifest(
                    snapshot.resolve(), str(folder), {snapshot.resolve()}, session)
            other = session / "play-ui-52"
            other.mkdir()
            with self.assertRaisesRegex(verifier.VerificationError, "exact generated snapshot"):
                verifier.trade_route_frame_manifest(
                    snapshot.resolve(), str(other), generated, session)


class NativeInputSourceContractTests(unittest.TestCase):
    @staticmethod
    def source_texts() -> dict[str, str]:
        return {
            "BitmapWindow.h": "enum class BitmapInputKind { KeyDown=0, ControlClick=1, Scroll=4 };",
            "BitmapWindow.cpp": (
                "kPrototypeScrollPixelsPerNotch = 48.0f; "
                "delta=-static_cast<float>(wheelDelta)*(kPrototypeScrollPixelsPerNotch/static_cast<float>(WHEEL_DELTA)); "
                "BitmapInputKind::Scroll,key,0,logicalX,logicalY,sceneGeneration_,delta"),
            "UiInputDispatch.h": (
                "KeyDown=1, LeftClick=2, PointerMove=3, Scroll=4; "
                'exportName="DispatchLeftClick"; exportName="DispatchScroll"'),
            "UiPopupContext.h": (
                "BitmapInputKind::ControlClick:request.kind=UiInputKind::LeftClick;request.key=event.controlKey; "
                "BitmapInputKind::KeyDown:request.kind=UiInputKind::KeyDown;request.key=event.virtualKey; "
                "BitmapInputKind::Scroll: request.kind=UiInputKind::Scroll;request.key=event.controlKey;request.delta=event.scrollDelta"),
            "UiPresentationInput.lua": (
                "function ZeroSisUi.DispatchScroll(controlKey,delta)\n"
                "panel:SetScrollValue(math.max(0,math.min(maximum,current+delta)))\n"
                "return true\nend"),
        }

    def test_accepts_source_backed_enum_wheel_conversion_and_scroll_consumption(self) -> None:
        verifier.validate_native_input_source_contract(self.source_texts())

    def test_rejects_wrong_ui_input_enum(self) -> None:
        texts = self.source_texts()
        texts["UiInputDispatch.h"] = texts["UiInputDispatch.h"].replace("LeftClick=2", "LeftClick=1")
        with self.assertRaisesRegex(verifier.VerificationError, "UiInputDispatch.h"):
            verifier.validate_native_input_source_contract(texts)

    def test_rejects_unconverted_raw_wheel_delta_formula(self) -> None:
        texts = self.source_texts()
        texts["BitmapWindow.cpp"] = texts["BitmapWindow.cpp"].replace(
            "-static_cast<float>(wheelDelta)", "static_cast<float>(wheelDelta)")
        with self.assertRaisesRegex(verifier.VerificationError, "BitmapWindow.cpp"):
            verifier.validate_native_input_source_contract(texts)

    def test_requires_scroll_consumption_after_the_clamped_setter(self) -> None:
        texts = self.source_texts()
        texts["UiPresentationInput.lua"] = texts["UiPresentationInput.lua"].replace(
            "return true\nend", "end\nreturn true")
        with self.assertRaisesRegex(verifier.VerificationError, "UiPresentationInput.lua"):
            verifier.validate_native_input_source_contract(texts)


class FrozenHostSourceProvenanceTests(unittest.TestCase):
    BUILD_ID = "20261008T135705Z_418f41986ec2"
    SOURCE_NAME = "InteractiveGameLoop.h"

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="trade-route-source-proof-", dir=PROJECT)
        self.addCleanup(self.temporary.cleanup)
        self.project = Path(self.temporary.name)
        self.project_root = self.project / "Build/UiWindowHost" / self.BUILD_ID

    def make_row(self, name: str, frozen_root: str) -> tuple[dict, Path, Path]:
        original = self.project / "Source/Host" / name
        frozen = self.project_root / "frozen" / frozen_root / "Source/Host" / name
        original.parent.mkdir(parents=True, exist_ok=True)
        frozen.parent.mkdir(parents=True, exist_ok=True)
        original.write_text("mutable working source", encoding="utf-8")
        frozen.write_text("compiled frozen source with INTERACTIVE_TRADE_ROUTE_ACTION",
                          encoding="utf-8")
        row = {
            "path": str(frozen),
            "original_source": str(original),
            "relative_path": f"Source\\Host\\{name}",
            "sha256": hashlib.sha256(frozen.read_bytes()).hexdigest(),
            "bytes": frozen.stat().st_size,
        }
        return row, original, frozen

    def check(self, row: dict, name: str = SOURCE_NAME, build_id: str | None = None) -> Path:
        with patch.object(verifier, "PROJECT", self.project):
            return verifier.compiled_host_source(build_id or self.BUILD_ID, name, row)

    def test_accepts_hash_bound_frozen_source_after_working_copy_changes(self) -> None:
        row, original, frozen = self.make_row(self.SOURCE_NAME, "include_roots/project")
        original.write_text("later working source contents", encoding="utf-8")
        compiled = self.check(row)
        self.assertEqual(compiled, frozen.resolve())
        self.assertIn("INTERACTIVE_TRADE_ROUTE_ACTION", compiled.read_text(encoding="utf-8"))

    def test_rejects_path_outside_exact_build_frozen_root(self) -> None:
        row, _, frozen = self.make_row(self.SOURCE_NAME, "include_roots/project")
        forged = dict(row)
        forged_path = self.project / "elsewhere" / self.SOURCE_NAME
        forged_path.parent.mkdir()
        forged_path.write_bytes(frozen.read_bytes())
        forged["path"] = str(forged_path)
        with self.assertRaises(verifier.VerificationError):
            self.check(forged)

    def test_rejects_wrong_project_relative_source_path(self) -> None:
        row, _, _ = self.make_row(self.SOURCE_NAME, "include_roots/project")
        forged = dict(row, relative_path="Source\\Other\\InteractiveGameLoop.h")
        with self.assertRaises(verifier.VerificationError):
            self.check(forged)

    def test_rejects_forged_original_source_lineage(self) -> None:
        row, _, _ = self.make_row(self.SOURCE_NAME, "include_roots/project")
        forged = dict(row, original_source=str(self.project / "Other" / self.SOURCE_NAME))
        with self.assertRaises(verifier.VerificationError):
            self.check(forged)

    def test_rejects_forged_frozen_source_hash(self) -> None:
        row, _, _ = self.make_row(self.SOURCE_NAME, "include_roots/project")
        forged = dict(row, sha256="0" * 64)
        with self.assertRaises(verifier.VerificationError):
            self.check(forged)

    def test_rejects_frozen_path_from_another_build_identity(self) -> None:
        row, _, frozen = self.make_row(self.SOURCE_NAME, "include_roots/project")
        other_build = "20261008T161612Z_f12596e7c414"
        other_frozen = (self.project / "Build/UiWindowHost" / other_build /
                        "frozen/include_roots/project/Source/Host" / self.SOURCE_NAME)
        other_frozen.parent.mkdir(parents=True)
        other_frozen.write_bytes(frozen.read_bytes())
        forged = dict(row, path=str(other_frozen))
        with self.assertRaises(verifier.VerificationError):
            self.check(forged)

    def test_accepts_lua_source_in_explicit_frozen_project_root(self) -> None:
        row, _, frozen = self.make_row("UiScene.lua", "project")
        compiled = self.check(row, name="UiScene.lua")
        self.assertEqual(compiled, frozen.resolve())

    def test_rejects_cpp_header_in_owned_project_frozen_root(self) -> None:
        row, _, _ = self.make_row(self.SOURCE_NAME, "project")
        with self.assertRaises(verifier.VerificationError):
            self.check(row)

    def test_rejects_lua_source_in_compiler_include_frozen_root(self) -> None:
        row, _, _ = self.make_row("UiScene.lua", "include_roots/project")
        with self.assertRaises(verifier.VerificationError):
            self.check(row, name="UiScene.lua")


class FrozenHostSourceContractTests(unittest.TestCase):
    def test_ui_scene_checks_retained_provenance_exports_not_layout_literals(self) -> None:
        text = "\n".join((
            "local hasRetainedTradeRouteUi = popupKind=='TradeRoute'",
            "rowTemplate=assert(provenance.rowTemplate)",
            "originalLayoutXml=assert(provenance.originalLayoutXml)",
            "originalLayoutLua=assert(provenance.originalLayoutLua)",
            "originalHelpersLua=assert(provenance.originalHelpersLua)",
        ))
        verifier.validate_compiled_host_source_contract("UiScene.lua", text)
        with self.assertRaisesRegex(verifier.VerificationError, "provenance exports"):
            verifier.validate_compiled_host_source_contract(
                "UiScene.lua", "TradeRouteOverview TRInstance")

    def test_fixture_contract_uses_actual_lua_userdata_names(self) -> None:
        text = "\n".join((
            "from:GetID() to:GetID() from:GetOwner() to:GetOwner()",
            "GetTradeRoutesToYou() GetTradeRoutesAvailable() UNITAI_UNKNOWN",
            "SetUnitAIType(fixtureAI) for _,unit in ipairs({inA,inB}) do",
            "MISSION_ESTABLISH_TRADE_ROUTE ResponsePushMission",
        ))
        verifier.validate_compiled_host_source_contract("TradeRouteSmokeFixture.h", text)
        with self.assertRaisesRegex(verifier.VerificationError, "real SDK getters"):
            verifier.validate_compiled_host_source_contract(
                "TradeRouteSmokeFixture.h", text.replace("from:GetID()", "FromCity:GetID()"))


class TradeRouteResumeLineageTests(unittest.TestCase):
    SOURCE_ID = "20261008T225105Z_a09bb643b908"
    RUN_ID = "20261008T233650Z_5cfa5136b39e"

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(prefix="trade-route-resume-", dir=PROJECT)
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name).absolute()
        self.root = root
        self.evidence = root / "evidence" / "interactive_game"
        self.source_evidence, self.run_evidence = self.evidence / self.SOURCE_ID, self.evidence / self.RUN_ID
        self.runtimes = root / "Build" / "InteractiveGameRuntime"
        self.source_runtime, self.runtime = self.runtimes / self.SOURCE_ID, self.runtimes / self.RUN_ID
        self.source_session = self.source_runtime / "sessions" / "source-session"
        self.session = self.runtime / "sessions" / "resume-session"
        for path in (self.source_evidence, self.run_evidence, self.source_session, self.session):
            path.mkdir(parents=True, exist_ok=True)
        self.build_id = "20261008T224629Z_ee41544939ef"
        self.build_path = root / "Build" / "UiWindowHost" / self.build_id / "build_result.json"
        self.build_path.parent.mkdir(parents=True)
        self.write(self.build_path, "same build")
        self.host = self.runtime / "ZeroSisHost_x64.exe"
        self.source_host = self.source_runtime / "ZeroSisHost_x64.exe"
        self.write(self.host, "same sealed host")
        self.write(self.source_host, "same sealed host")
        self.manifest = self.runtime / "bundle.manifest"
        self.source_manifest = self.source_runtime / "bundle.manifest"
        manifest_text = f"ZEROSIS_HOST_BUNDLE_V4\nZeroSisHost_x64.exe|{self.sha(self.host)}\n"
        self.write(self.manifest, manifest_text)
        self.write(self.source_manifest, manifest_text)
        self.current_inputs = self.inputs(self.host, self.manifest)
        self.source_inputs = self.inputs(self.source_host, self.source_manifest)
        self.host_build = self.ref(self.build_path)
        self.build = {"executable": {"sha256": self.sha(self.host)}}

        self.source_save = self.source_session / "play-save-2-turn-1.zssave"
        self.write(self.source_save, "source save")
        self.source_state = self.source_session / "play-final-state.txt"
        self.write(self.source_state, "G|1|1|0|960\n")
        self.source_db = self.source_session / "Civ5SavedGameDatabase.db"
        self.write(self.source_db, "source db")
        first_source_save = self.source_session / "play-save-1-turn-1.zssave"
        self.write(first_source_save, "first source save")
        self.source_request_path = self.source_evidence / "request.json"
        self.source_attempt_path = self.source_evidence / "attempt.json"
        self.source_stdout = self.source_evidence / "stdout.log"
        self.source_result_path = self.source_evidence / "result.json"
        self.source_request = {"run_id": self.SOURCE_ID, "cwd": str(self.source_runtime),
                               "trade_route_smoke": True, "runtime_inputs": list(self.source_inputs),
                               "provenance": {"host_build": self.host_build}}
        self.write_json(self.source_request_path, self.source_request)
        self.write_json(self.source_attempt_path, {"status": "FINISHED", "returncode": 0,
                                                    "timed_out": False, "pid": 101})
        self.source_output = ("INTERACTIVE_GAME_STARTED=0|0|40|24\n" +
                              "INTERACTIVE_NEXT_HUMAN_TURN=1|7\n" +
                              f"INTERACTIVE_NATIVE_SAVE=1|{first_source_save}\n" +
                              f"INTERACTIVE_NATIVE_SAVE=1|{self.source_save}\n")
        self.write(self.source_stdout, self.source_output)
        self.source_result = {
            "run_id": self.SOURCE_ID, "status": "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS",
            "returncode": 0, "timed_out": False, "runtime_inputs_unchanged": True,
            "trade_route_requested": True, "trade_route_sequence_verified": True,
            "pid": 100, "driver_pid": 101, "request": self.ref(self.source_request_path),
            "attempt": self.ref(self.source_attempt_path), "stdout": self.ref(self.source_stdout),
            "native_saves": [["1", str(first_source_save)], ["1", str(self.source_save)]],
            "next_human_turn": [["1", "7"]],
            "generated_files": [self.ref(path) for path in
                                 (first_source_save, self.source_save, self.source_state, self.source_db)],
        }
        self.write_json(self.source_result_path, self.source_result)

        self.checkpoint = self.runtime / "checkpoint-input.zssave"
        self.write(self.checkpoint, self.source_save.read_bytes())
        self.expected_state = self.run_evidence / "checkpoint-state.txt"
        self.write(self.expected_state, self.source_state.read_bytes())
        self.frozen_result = self.run_evidence / "resume-source-result.json"
        self.write(self.frozen_result, self.source_result_path.read_bytes())
        self.initial = self.session / "play-initial-state.txt"
        self.write(self.initial, self.source_state.read_bytes())
        self.roundtrip = self.session / "play-restored-checkpoint.zssave"
        self.write(self.roundtrip, "roundtrip save")
        self.current_db = self.session / "Civ5SavedGameDatabase.db"
        self.write(self.current_db, "current db")
        self.final_state = self.session / "play-final-state.txt"
        self.write(self.final_state, "G|2|2|0|960\n")
        self.resaves = [self.session / "play-save-1-turn-2.zssave",
                        self.session / "play-save-2-turn-2.zssave"]
        for index, path in enumerate(self.resaves):
            self.write(path, f"resave {index}")
        self.current_generated = {}
        for path in (self.initial, self.roundtrip, self.current_db, self.final_state, *self.resaves):
            self.current_generated.setdefault(path.name, []).append(path)
        self.resume = {"run_id": self.SOURCE_ID, "run_result": self.ref(self.frozen_result),
                       "checkpoint_source": self.ref(self.source_save),
                       "checkpoint_input": self.ref(self.checkpoint),
                       "expected_state": self.ref(self.expected_state),
                       "checkpoint_source_state": self.ref(self.source_state), "turn": 1}
        self.request = {"run_id": self.RUN_ID, "cwd": str(self.runtime),
                        "runtime_inputs": list(self.current_inputs),
                        "provenance": {"host_build": self.host_build}, "resume_from": self.resume}
        self.result = {"run_id": self.RUN_ID, "resume_from_run": self.SOURCE_ID,
                       "checkpoint_input_unchanged": True, "semantic_restore_equal": True,
                       "fresh_process_restore_verified": True, "pid": 200, "driver_pid": 201,
                       "next_human_turn": [["2", "8"]],
                       "native_saves": [["2", str(path)] for path in self.resaves]}
        self.attempt = {"pid": 201}
        self.output = (f"INTERACTIVE_RESTORE_CHECKPOINT={self.checkpoint}\n"
                       "INTERACTIVE_RESTORE_IDENTITY=1|1|0|133\n"
                       "INTERACTIVE_RESTORE_SECTIONS_EQUAL=132|133\n"
                       "INTERACTIVE_RESTORE_SECTION_CHANGED=3|0\n"
                       "INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=true\n"
                       "INTERACTIVE_GAME_STARTED=1|0|40|24\n"
                       "INTERACTIVE_NEXT_HUMAN_TURN=2|8\n" +
                       "".join(f"INTERACTIVE_NATIVE_SAVE=2|{path}\n" for path in self.resaves))

    @staticmethod
    def sha(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @classmethod
    def ref(cls, path: Path) -> dict:
        return {"path": str(path), "sha256": cls.sha(path)}

    @staticmethod
    def write(path: Path, data: str | bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)

    @classmethod
    def write_json(cls, path: Path, value: dict) -> None:
        cls.write(path, json.dumps(value))

    @classmethod
    def inputs(cls, host: Path, manifest: Path) -> list[dict]:
        return [cls.ref(host), cls.ref(manifest)]

    @staticmethod
    def section_rows(game_delta: bool = False, illegal_delta: bool = False) -> list[dict]:
        keys = [(kind, 0) for kind in range(1, 6)] + [
            (kind, index) for kind in (6, 7) for index in range(64)]
        rows = [{"kind": kind, "index": index, "sha256": f"{kind}:{index}"}
                for kind, index in keys]
        if game_delta:
            rows[2]["sha256"] = "game-reload-delta"
        if illegal_delta:
            rows[-1]["sha256"] = "illegal-player-delta"
        return rows

    def invoke(self, *, illegal_delta: bool = False, inspect_callback=None) -> dict:
        def fake_inspect(path: Path, bundle: Path, database: Path, *, expected: tuple) -> dict:
            sections = self.section_rows(game_delta=path == self.roundtrip,
                                         illegal_delta=path == self.roundtrip and illegal_delta)
            return {"archive": self.ref(path), "sections": sections,
                    "section_count": 133, "embedded_database": self.ref(database),
                    "sdk_map_dimensions": [40, 24]}

        original_resolve = Path.resolve

        def resolve_fixture_path(path: Path, strict: bool = False) -> Path:
            absolute = path.absolute()
            if absolute.is_relative_to(self.root.absolute()):
                if strict and not path.exists():
                    raise FileNotFoundError(path)
                return absolute
            return original_resolve(path, strict=strict)

        with patch.object(Path, "resolve", resolve_fixture_path), \
             patch.object(verifier, "PROJECT", self.root), \
             patch.object(verifier, "EVIDENCE", self.evidence), \
             patch.object(verifier, "RUNTIME_ROOT", self.runtimes), \
             patch.object(verifier, "verify_run", return_value={
                 "status": "PASS_INTERACTIVE_TRADE_ROUTE_NATIVE_SDK_SMOKE"}) as source_verify, \
             patch.object(verifier, "inspect_save", side_effect=inspect_callback or fake_inspect):
            result = verifier.verify_resume_lineage(
                self.RUN_ID, self.request, self.result, self.output, self.run_evidence,
                self.runtime, self.build, self.build_path, self.host, self.attempt,
                self.current_generated)
        source_verify.assert_called_once()
        return result

    def test_accepts_hash_bound_source_checkpoint_and_reports_restore_delta(self) -> None:
        proof = self.invoke()
        self.assertEqual(proof["source_run_id"], self.SOURCE_ID)
        self.assertEqual(proof["restore_identity"], [1, 1, 0, 960])
        self.assertEqual(proof["restore_section_changes"], [[3, 0]])
        self.assertEqual(proof["post_restore_turn"], 2)
        self.assertIs(proof["sdk_game_reload_metadata_semantics_verified"], False)
        self.assertTrue(any("RNG equivalence" in item for item in proof["limitations"]))

    def test_rejects_archive_counts_misrepresented_as_sdk_dimensions(self) -> None:
        self.output = self.output.replace("INTERACTIVE_GAME_STARTED=1|0|40|24",
                                          "INTERACTIVE_GAME_STARTED=1|0|64|64")
        with self.assertRaisesRegex(verifier.VerificationError, "checkpoint state or inspected SDK map dimensions"):
            self.invoke()

    def test_rejects_fresh_startup_turn_reused_instead_of_checkpoint_turn(self) -> None:
        # The actual source starts at turn 0 and saves at turn 1. A restored
        # process must begin at that saved turn, even though its map is unchanged.
        self.output = self.output.replace("INTERACTIVE_GAME_STARTED=1|0|40|24",
                                          "INTERACTIVE_GAME_STARTED=0|0|40|24")
        with self.assertRaisesRegex(verifier.VerificationError, "checkpoint state"):
            self.invoke()

    def test_copied_checkpoint_archive_is_bound_to_source_embedded_database(self) -> None:
        inspected: list[tuple[Path, Path]] = []

        def capture_inspect(path: Path, bundle: Path, database: Path, *, expected: tuple) -> dict:
            inspected.append((path, database))
            sections = self.section_rows(game_delta=path == self.roundtrip)
            return {"archive": self.ref(path), "sections": sections,
                    "section_count": 133, "embedded_database": self.ref(database),
                    "sdk_map_dimensions": [40, 24]}

        self.invoke(inspect_callback=capture_inspect)
        self.assertIn((self.checkpoint, self.source_db), inspected)

    def test_accepts_separate_frozen_build_report_copy_with_identical_bytes(self) -> None:
        source_build_copy = self.source_evidence / "host-build.json"
        self.write(source_build_copy, self.build_path.read_bytes())
        self.source_request["provenance"]["host_build"] = self.ref(source_build_copy)
        self.write_json(self.source_request_path, self.source_request)
        # The source result is frozen after its request, so update that exact
        # source result copy too; only the build report location is different.
        self.source_result["request"] = self.ref(self.source_request_path)
        self.write_json(self.source_result_path, self.source_result)
        self.write(self.frozen_result, self.source_result_path.read_bytes())
        self.resume["run_result"] = self.ref(self.frozen_result)

        proof = self.invoke()
        self.assertEqual(proof["source_run_id"], self.SOURCE_ID)

    def test_rejects_separate_build_report_copy_with_different_bytes(self) -> None:
        source_build_copy = self.source_evidence / "host-build.json"
        self.write(source_build_copy, "different build")
        self.source_request["provenance"]["host_build"] = self.ref(source_build_copy)
        self.write_json(self.source_request_path, self.source_request)
        self.source_result["request"] = self.ref(self.source_request_path)
        self.write_json(self.source_result_path, self.source_result)
        self.write(self.frozen_result, self.source_result_path.read_bytes())
        self.resume["run_result"] = self.ref(self.frozen_result)

        with self.assertRaisesRegex(verifier.VerificationError, "same successful sealed Host build"):
            self.invoke()

    def test_rejects_forged_source_run_identity(self) -> None:
        self.resume["run_id"] = self.RUN_ID
        with self.assertRaisesRegex(verifier.VerificationError, "source ID"):
            self.invoke()

    def test_rejects_forged_final_save_path(self) -> None:
        forged = self.source_runtime / "forged-save.zssave"
        self.write(forged, self.source_save.read_bytes())
        self.resume["checkpoint_source"] = self.ref(forged)
        with self.assertRaisesRegex(verifier.VerificationError, "escaped its exact"):
            self.invoke()

    def test_rejects_validly_hashed_but_wrong_expected_state(self) -> None:
        self.write(self.expected_state, "G|1|9|0|960\n")
        self.resume["expected_state"] = self.ref(self.expected_state)
        with self.assertRaisesRegex(verifier.VerificationError, "expected state"):
            self.invoke()

    def test_rejects_restored_initial_state_that_differs_from_checkpoint(self) -> None:
        self.write(self.initial, "G|1|2|1|960\n")
        with self.assertRaisesRegex(verifier.VerificationError, "initial SDK state"):
            self.invoke()

    def test_rejects_restore_marker_pointing_to_another_save(self) -> None:
        self.output = self.output.replace(str(self.checkpoint), str(self.source_save), 1)
        with self.assertRaisesRegex(verifier.VerificationError, "Raw native restore markers"):
            self.invoke()

    def test_rejects_roundtrip_delta_outside_sdk_game_section(self) -> None:
        with self.assertRaisesRegex(verifier.VerificationError, "outside the SDK Game"):
            self.invoke(illegal_delta=True)


if __name__ == "__main__":
    unittest.main()
