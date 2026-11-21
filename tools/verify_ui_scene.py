"""Run official ranking-popup Lua against the retained scene in the shared Lua 5.1 runtime.

This is a component regression only: mocked Game/player/native bindings cannot
verify Civ V event ordering, the retail layout engine, style expansion or pixels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET
from prepare_ui_popup_assets import (control_tree as prepared_control_tree,
                                     production_font_metrics, production_style_defaults)


PROJECT = Path(__file__).resolve().parents[1]
INPUTS = {
    "test": PROJECT / "Tests/ui_scene_cases.lua",
    "scene": PROJECT / "Source/Host/UiScene.lua",
    "snapshot_json_header": PROJECT / "Source/Host/UiSnapshotJson.h",
    "ui_context": PROJECT / "Source/Host/UiPopupContext.h",
    "instance_manager": PROJECT / "Source/Assets/UI/Assets/UI/InstanceManager.lua",
    "icon_support": PROJECT / "Source/Assets/UI/Assets/UI/IconSupport.lua",
    "flua_vector": PROJECT / "Source/Assets/UI/Assets/Gameplay/Lua/FLuaVector.lua",
    "popup": PROJECT / "Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/WhosWinningPopup.lua",
    "xml": PROJECT / "Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/WhosWinningPopup.xml",
    "production_xml": PROJECT / "Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/ProductionPopup.xml",
    "inline_icons": PROJECT / "evidence/ui_popup/assets/inline_icons.json",
    "asset_preparer": PROJECT / "tools/prepare_ui_popup_assets.py",
    "font_loader": PROJECT / "tools/ui_bitmap_fonts.py",
    "styles": PROJECT / "Source/Assets/UI/Assets/UI/Styles.xml",
    "ui_input": PROJECT / "Source/Presentation/UiPresentationInput.lua",
    "tech_fixture": PROJECT / "Tests/tech_ui_cases.lua",
    "tech_tree_fixture": PROJECT / "Tests/tech_tree_ui_cases.lua",
}
TECH_ASSET_RELATIVE = {
    "tech_popup": "Assets/DLC/Expansion2/UI/InGame/TechPopup.lua",
    "tech_xml": "Assets/DLC/Expansion2/UI/InGame/TechPopup.xml",
    "tech_button": "Assets/DLC/Expansion2/UI/InGame/TechTree/TechButtonInclude.lua",
    "tech_help": "Assets/DLC/Expansion2/UI/InGame/TechTree/TechHelpInclude.lua",
    "info_tooltip": "Assets/DLC/Expansion2/UI/InGame/InfoTooltipInclude.lua",
}
GAME_ASSETS = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
TECH_INPUTS = {
    name: (PROJECT / "Source/Assets/UI" / relative
           if (PROJECT / "Source/Assets/UI" / relative).is_file() else GAME_ASSETS / relative)
    for name, relative in TECH_ASSET_RELATIVE.items()
}
TECH_EXPECTED_SHA256 = {
    "tech_popup": "4d86bcecab5738f2c8011d139dbf2f46d65e7ee5de17c26d8cf8788a21a7cefa",
    "tech_xml": "6aeacefea8da768818bbc0ea4cb9ebe0069d1285d4b0f152a3f12167f4570b86",
    "tech_button": "03e5be256a72fa4c80b14a4f6b046452370651cf3002093ee1d7f76f798fd86a",
    "tech_help": "ab0d09d272bb258e8fcefa86df3fa5f6de8a9ea16b0fc3007aa62a6f80f04fa5",
    "info_tooltip": "405a3d677fff50acdc1155a97e713185219ca9fc2ceb61db6d298b1fc5382fa4",
}
TECH_TREE_ASSET_RELATIVE = {
    "tech_tree": "Assets/DLC/Expansion2/UI/TechTree/TechTree.lua",
    "tech_tree_xml": "Assets/DLC/Expansion2/UI/InGame/TechTree/TechTree.xml",
}
TECH_TREE_EXPECTED_SHA256 = {
    "tech_tree": "2caafe619194a7f599d52d92cc3f4114c3a054ced78b1f8720b651cf78283488",
    "tech_tree_xml": "cdbdfd89ca6d77ef850f94b03a167b49abd0952cd7b8944877c4f9a29dbd1e2b",
}
DEFAULT_LUA = PROJECT / "Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def lua_quote(value: str) -> str:
    return '"' + "".join(
        chr(byte) if 32 <= byte < 127 and byte not in (34, 92) else "\\%03d" % byte
        for byte in value.encode("utf-8")
    ) + '"'


def lua_value(value: object) -> str:
    if isinstance(value, str):
        return lua_quote(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("nonfinite number in test UI layout")
        return repr(value)
    if isinstance(value, list):
        return "{" + ",".join(lua_value(item) for item in value) + "}"
    if isinstance(value, dict):
        def key_literal(key: object) -> str:
            if isinstance(key, str):
                return "[" + lua_quote(key) + "]"
            if isinstance(key, int) and not isinstance(key, bool) and key >= 0:
                return "[" + str(key) + "]"
            raise TypeError("unsupported Lua table key: " + repr(key))
        return "{" + ",".join(
            key_literal(key) + "=" + lua_value(item)
            for key, item in sorted(value.items(), key=lambda row: (type(row[0]).__name__, row[0]))
        ) + "}"
    raise TypeError("unsupported XML layout value: " + type(value).__name__)


def control_tree(element: ET.Element) -> dict[str, object]:
    kinds = {"Context", "Instance", "Box", "Image", "Label", "Grid",
             "ScrollPanel", "Stack", "ScrollBar", "GridButton", "Button", "Container",
             "AlphaAnim", "DownButton", "UpButton", "Meter", "ScrollAnim", "ShowOnMouseOver", "TextureBar", "GridData", "EditBox"}
    if element.tag not in kinds:
        raise ValueError("unsupported XML control in frozen fixture: " + element.tag)
    if element.text and element.text.strip():
        raise ValueError("unexpected mixed XML content in frozen fixture")
    return {
        "kind": element.tag,
        "attributes": dict(element.attrib),
        "children": [control_tree(child) for child in element],
    }


def long_string(value: str) -> str:
    level = 0
    while "]" + "=" * level + "]" in value:
        level += 1
    fence = "=" * level
    return "[" + fence + "[" + value + "]" + fence + "]"


def assemble(template: str, source: dict[str, bytes], layout: dict[str, object],
             font_metrics: dict[str, object], failure_mode: str = "") -> bytes:
    values = {
        "@@SOURCE_INSTANCE_MANAGER@@": long_string(source["instance_manager"].decode("utf-8-sig")),
        "@@SOURCE_ICON_SUPPORT@@": long_string(source["icon_support"].decode("utf-8-sig")),
        "@@SOURCE_FLUA_VECTOR@@": long_string(source["flua_vector"].decode("utf-8-sig")),
        "@@SOURCE_POPUP@@": long_string(source["popup"].decode("utf-8-sig")),
        "@@SCENE_SOURCE@@": long_string(source["scene"].decode("utf-8-sig")),
        "@@LAYOUT@@": lua_value(layout),
        "@@PRODUCTION_FONT_METRICS@@": lua_value(font_metrics),
        "@@FAILURE_MODE@@": lua_quote(failure_mode),
    }
    for token, value in values.items():
        template = template.replace(token, value)
    if "@@" in template:
        raise ValueError("unsubstituted Lua harness placeholder")
    return template.encode("utf-8")


def assemble_tech(template: str, source: dict[str, bytes], layout: dict[str, object]) -> bytes:
    values = {
        "@@SOURCE_INSTANCE_MANAGER@@": long_string(source["instance_manager"].decode("utf-8-sig")),
        "@@SOURCE_ICON_SUPPORT@@": long_string(source["icon_support"].decode("utf-8-sig")),
        "@@SOURCE_FLUA_VECTOR@@": long_string(source["flua_vector"].decode("utf-8-sig")),
        "@@SOURCE_INFO_TOOLTIP@@": long_string(source["info_tooltip"].decode("utf-8-sig")),
        "@@SOURCE_TECH_BUTTON@@": long_string(source["tech_button"].decode("utf-8-sig")),
        "@@SOURCE_TECH_HELP@@": long_string(source["tech_help"].decode("utf-8-sig")),
        "@@SOURCE_TECH_POPUP@@": long_string(source["tech_popup"].decode("utf-8-sig")),
        "@@SCENE_SOURCE@@": long_string(source["scene"].decode("utf-8-sig") + "\n" +
                                           source["ui_input"].decode("utf-8-sig")),
        "@@LAYOUT@@": lua_value(layout),
    }
    for token, value in values.items():
        template = template.replace(token, value)
    if "@@" in template:
        raise ValueError("unsubstituted Tech UI harness placeholder")
    return template.encode("utf-8")


def assemble_tech_tree(template: str, source: dict[str, bytes], layout: dict[str, object]) -> bytes:
    values = {
        "@@SOURCE_INSTANCE_MANAGER@@": long_string(source["instance_manager"].decode("utf-8-sig")),
        "@@SOURCE_ICON_SUPPORT@@": long_string(source["icon_support"].decode("utf-8-sig")),
        "@@SOURCE_FLUA_VECTOR@@": long_string(source["flua_vector"].decode("utf-8-sig")),
        "@@SOURCE_INFO_TOOLTIP@@": long_string(source["info_tooltip"].decode("utf-8-sig")),
        "@@SOURCE_TECH_BUTTON@@": long_string(source["tech_button"].decode("utf-8-sig")),
        "@@SOURCE_TECH_HELP@@": long_string(source["tech_help"].decode("utf-8-sig")),
        "@@SOURCE_TECH_TREE@@": long_string(source["tech_tree"].decode("utf-8-sig")),
        "@@SCENE_SOURCE@@": long_string(source["scene"].decode("utf-8-sig") + "\n" +
                                           source["ui_input"].decode("utf-8-sig")),
        "@@LAYOUT@@": lua_value(layout),
    }
    for token, value in values.items():
        template = template.replace(token, value)
    if "@@" in template:
        raise ValueError("unsubstituted TechTree UI harness placeholder")
    return template.encode("utf-8")


def validate_tech_report(report: dict[str, object]) -> dict[str, object]:
    assert report["status"] == "PASS_RESEARCH_POPUP_LUA_COMPONENT_ONLY"
    assert report["contextName"] == "TechPopup" and report["popupKind"] == "Research"
    assert report["timerSemaphore"] == 0
    assert report["officialTechSelectedArguments"] == [7, 0, -1, False]
    assert report["officialTechButtonVoidPair"] == [7, 0]
    assert report["officialShownAndProcessedLifecycle"] is True
    assert report["shortListMaximumScroll"] == 0
    assert report["positiveOverflowCaptured"] is True
    assert isinstance(report["positiveOverflowMaximum"], (int, float)) and report["positiveOverflowMaximum"] > 0
    assert report["nestedScrollClippingChecked"] is True
    assert report["malformedShuttleRejected"] is True
    assert report["rightClickPediaRuntimeVerified"] is False
    assert report["retailLayoutAndPixelsVerified"] is False
    return {
        "case": "official_tech_popup_research_scene_component",
        "context": "TechPopup/Research",
        "official_research_selection_arguments": report["officialTechSelectedArguments"],
        "dynamic_tech_row_and_voids_checked": True,
        "shown_close_timer_zero_lifecycle_checked": True,
        "measured_short_list_range_checked": True,
        "positive_overflow_and_malformed_shuttle_checked": True,
        "nested_scrollpanel_clipping_checked": True,
        "right_click_pedia_runtime_verified": False,
        "scope": "component-only; SDK research, retail layout and pixels remain outside this fixture",
    }


def validate_tech_tree_report(report: dict[str, object]) -> dict[str, object]:
    assert report["status"] == "PASS_RESEARCH_TREE_LUA_COMPONENT_ONLY"
    assert report["contextName"] == "TechTree" and report["popupKind"] == "ResearchTree"
    assert report["shownTimer"] == 1 and report["closedTimer"] == 0
    assert report["officialPopupEnum"] == 67
    assert report["openLifecycle"] == ["queued", "shown:67"]
    assert report["closeLifecycle"] == ["queued", "shown:67", "closed", "processed:67"]
    assert report["shiftResearchTuple"] == [7, 0, -1, False]
    assert report["researchDirtyUpdatedCapture"] is True
    assert report["horizontalShortRange"] == 0
    assert report["horizontalOverflowCaptured"] is True and report["horizontalMaximum"] > 0
    assert report["scrollResetChecked"] is True
    assert report["retailLayoutAndPixelsVerified"] is False
    return {
        "case": "official_bnw_techtree_research_tree_scene_component",
        "context": "TechTree/ResearchTree",
        "official_popup_enum": report["officialPopupEnum"],
        "shown_timer_one_close_timer_zero_checked": True,
        "normal_research_and_research_dirty_mock_checked": True,
        "horizontal_short_and_overflow_ranges_checked": True,
        "scroll_reset_checked": True,
        "retail_sdk_and_pixels_verified": False,
    }


def run_lua(encoder_path: Path, harness_path: Path,
            report_field: str = "__uiSceneComponentReport") -> str:
    # Execute the same C++ encoder used by the Host, with the retained Lua 5.1
    # provider beside the frozen exe; no Python or Lua replacement JSON encoder.
    process = subprocess.run([str(encoder_path), "--run", str(harness_path), report_field],
                             cwd=encoder_path.parent, capture_output=True, timeout=60,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    stdout = process.stdout.decode("utf-8", errors="strict")
    stderr = process.stderr.decode("utf-8", errors="replace")
    harness_path.with_suffix(".stdout.txt").write_text(stdout, encoding="utf-8")
    harness_path.with_suffix(".stderr.txt").write_text(stderr, encoding="utf-8")
    prefix = "UI_SNAPSHOT_JSON_REPORT="
    lines = [line[len(prefix):] for line in stdout.splitlines() if line.startswith(prefix)]
    if process.returncode != 0 or len(lines) != 1:
        raise RuntimeError(f"Native Lua component failed (exit {process.returncode}): {stderr or stdout}")
    return lines[0]


def find_control(node: dict, control_id: str) -> dict:
    if node.get("id") == control_id:
        return node
    for child in node.get("children", []):
        found = find_control(child, control_id)
        if found:
            return found
    return {}


def validate_report(report: dict) -> dict[str, object]:
    expected_modes = {"first": [0, 2], "second": [0, 2, 3], "third": [0, 6, 2]}
    stack_keys = {}
    row_labels = {}
    for name, values in expected_modes.items():
        snapshot = report[name]
        assert snapshot["active"] is True and snapshot["timerSemaphore"] == 1, name + " lifecycle state"
        assert snapshot["rendererVerified"] is False
        assert snapshot["styleExpansionVerified"] is False
        assert snapshot["fontMeasurementVerified"] is False
        draws = snapshot["draws"]
        assert [draw["value"] for draw in draws] == values, name + " RNG mode sequence"
        assert len(draws) == len(values), name + " unexpected RNG call count"
        for previous, current in zip(draws, draws[1:]):
            assert previous["seedAfter"] == current["seedBefore"], name + " non-contiguous seed trace"
        assert all(draw["seedAfter"] == draw["seedBefore"] + 1 for draw in draws), name + " fixture RNG accounting"
        lifecycle = snapshot["lifecycle"]
        assert lifecycle == ["queued", "shown:101"], name + " popup lifecycle events"
        stack = find_control(snapshot["tree"], "PlayerListStack")
        rows = stack.get("children")
        assert isinstance(rows, list) and len(rows) == 2, name + " active ranking rows"
        assert all(row["hidden"] is False for row in rows), name + " row visibility"
        stack_keys[name] = [row["key"] for row in rows]
        row_labels[name] = [find_control(row, "ScoreText")["text"] for row in rows]

    assert stack_keys["first"] == stack_keys["second"] == stack_keys["third"], "official row pool was not reused"
    # The second attempt rejects Gold and accepts Science; the third rejects
    # unavailable Wonders and accepts Gold. Confirm the displayed labels too.
    assert find_control(report["first"]["tree"], "ListNameLabel")["text"].startswith("TXT_KEY_PROGRESS_SCREEN_GOLD")
    assert find_control(report["second"]["tree"], "ListNameLabel")["text"].startswith("TXT_KEY_PROGRESS_SCREEN_SCIENCE")
    assert find_control(report["third"]["tree"], "ListNameLabel")["text"].startswith("TXT_KEY_PROGRESS_SCREEN_GOLD")

    first_rows = find_control(report["first"]["tree"], "PlayerListStack")["children"]
    active_portrait = find_control(first_rows[0], "Portrait")
    composite_portrait = find_control(first_rows[1], "Portrait")
    composite_icon = find_control(first_rows[1], "Icon")
    composite_bg = find_control(first_rows[1], "CivIconBG")
    composite_shadow = find_control(first_rows[1], "CivIconShadow")
    assert (active_portrait["texture"], active_portrait["textureX"], active_portrait["textureY"]) == (
        "LEADERS64.dds", 0, 0), "leader atlas hookup for active player"
    assert (composite_portrait["texture"], composite_portrait["textureX"], composite_portrait["textureY"]) == (
        "LEADERS64.dds", 64, 0), "leader atlas offset for met player"
    assert (composite_icon["texture"], composite_icon["textureX"], composite_icon["textureY"]) == (
        "CIV_ALPHA24.dds", 24, 0), "composite civilization icon atlas hookup"
    assert composite_icon["color"] == {"x": 0, "y": 0, "z": 1, "w": 1}, "composite primary color"
    assert composite_bg["texture"] == "CivIconBGSizes.dds" and composite_bg["color"] == {
        "x": 1, "y": 1, "z": 0, "w": 1
    }, "composite secondary color and background"
    assert composite_shadow["texture"] == "CIV_ALPHA24.dds" and not composite_shadow["hidden"], \
        "composite shadow icon hookup"

    third_rows = find_control(report["third"]["tree"], "PlayerListStack")["children"]
    unmet_portrait = find_control(third_rows[1], "Portrait")
    unmet_icon = find_control(third_rows[1], "Icon")
    unmet_bg = find_control(third_rows[1], "CivIconBG")
    unmet_shadow = find_control(third_rows[1], "CivIconShadow")
    assert (unmet_portrait["texture"], unmet_portrait["textureX"], unmet_portrait["textureY"]) == (
        "LEADER_UNMET64.dds", 128, 320), "unmet leader fallback atlas hookup"
    assert (unmet_bg["texture"], unmet_bg["textureX"], unmet_bg["textureY"]) == (
        "CIV_COLOR32.dds", 96, 160), "unmet civilization color icon fallback"
    assert unmet_icon["hidden"] and unmet_shadow["hidden"], "unmet icon visibility flags"
    assert report["nativeTimer"] == 0 and report["nativeTimerCalls"] == [1, -1, 1, -1, 1, -1], \
        "independent native timer call sequence"
    production = report["production"]
    assert production["active"] is True and production["timerSemaphore"] == 0, \
        "Production scene must retain its no-timer popup lifecycle"
    assert production["fontMetrics"]["policy"] == "CIV5_GLYPHGEN_GGXML_LAYOUT_V1"
    assert production["fontMetrics"]["retailMetricSemanticsVerified"] is False
    measured = find_control(production["tree"], "MeasuredLabel")
    frame = measured["textFrame"]
    assert frame["width"] == frame["wrapWidth"] and frame["height"] == 2 * frame["lineAdvance"]
    assert [line["text"] for line in frame["lines"]] == ["WI", "WI"]
    pair_advance = report["productionTestExpected"]["pairAdvance"]
    assert all(line["advanceWidth"] == pair_advance for line in frame["lines"]), \
        "prepared glyphgen advances were not used for wrapped lines"
    assert measured["fontMetricSource"]["ggxmlPath"].endswith("TwCenMT20.ggxml")
    assert measured["fontMetricSource"]["sha256"] == production["fontMetrics"]["fonts"]["TwCenMT20"]["sha256"]
    icon_label = find_control(production["tree"], "InlineIconLabel")
    assert icon_label["textFrame"]["lines"] == [{
        "text": "\U000f0000", "advanceWidth": report["productionTestExpected"]["iconAdvance"]
    }], "official inline icon mapping did not supply the captured glyphgen advance"
    bottom = find_control(production["tree"], "BottomRows")
    hidden = find_control(bottom, "HiddenStaleRow")
    row_a = find_control(bottom, "BottomRowA")
    row_b = find_control(bottom, "BottomRowB")
    assert hidden["hidden"] is True and row_a["y"] == 302 and row_b["y"] == 300 + frame["lineAdvance"] + 4
    right = find_control(production["tree"], "RightRows")
    right_a = find_control(right, "RightRowA")
    right_b = find_control(right, "RightRowB")
    font_metrics = production["fontMetrics"]["fonts"]["TwCenMT20"]
    assert right_a["x"] == 702 and right_b["x"] == 700 + report["productionTestExpected"]["wAdvance"] + 7
    targets = production["inputTargets"]
    target_by_id = {target["id"]: target for target in targets}
    assert set(target_by_id) == {"OwnerButton", "PanelHit", "PartialButton"}, \
        "production input targets did not filter the unhovered ShowOnMouseOver callback"
    owner_target = target_by_id["OwnerButton"]
    assert owner_target["event"] == "LeftClick" and owner_target["visible"] is True and owner_target["disabled"] is False
    assert owner_target["void1"] == "row-owner" and owner_target["void2"] == 87
    assert owner_target["bounds"] == owner_target["clippedBounds"]
    panel_target = target_by_id["PanelHit"]
    # This isolated scene harness does not load UiPresentationInput or issue a
    # scroll event, so the owned panel offset remains its real initial zero.
    assert panel_target["bounds"] == {"x": 330, "y": 390, "width": 40, "height": 40}
    assert panel_target["clippedBounds"] == {"x": 330, "y": 390, "width": 10, "height": 10}
    partial_target = target_by_id["PartialButton"]
    assert partial_target["bounds"] == {"x": -10, "y": 500, "width": 20, "height": 20}
    assert partial_target["clippedBounds"] == {"x": 0, "y": 500, "width": 10, "height": 20}
    scroll_targets = production["scrollTargets"]
    scroll_by_id = {target["id"]: target for target in scroll_targets}
    assert set(scroll_by_id) == {"StylePanel", "OuterScroll", "NestedScroll", "StaticScroll"}, \
        "scroll manifest must include visible vertical panels, including zero-range panels, and exclude hidden panels"
    for target in scroll_targets:
        assert target["event"] == "Scroll" and target["visible"] is True and target["disabled"] is False
        assert 0 <= target["scrollY"] <= target["maximumScroll"]
        assert target["maximumScroll"] == max(0, target["contentHeight"] - target["viewportHeight"])
    assert scroll_by_id["StylePanel"]["contentHeight"] == 430 and \
        scroll_by_id["StylePanel"]["viewportHeight"] == 400 and scroll_by_id["StylePanel"]["maximumScroll"] == 30
    assert scroll_by_id["OuterScroll"]["bounds"] == {"x": 500, "y": 700, "width": 100, "height": 100}
    assert scroll_by_id["NestedScroll"]["bounds"] == {"x": 550, "y": 750, "width": 150, "height": 150}
    assert scroll_by_id["NestedScroll"]["clippedBounds"] == {"x": 550, "y": 750, "width": 50, "height": 50}
    assert scroll_by_id["NestedScroll"]["maximumScroll"] == 100
    assert scroll_by_id["StaticScroll"]["maximumScroll"] == 0
    return {
        "case": "official_whos_winning_lua_on_retained_scene_component",
        "fixed_fixture_draw_values": expected_modes,
        "pooled_row_keys": stack_keys,
        "score_labels": row_labels,
        "icon_atlas_paths": ["active/default", "met/composite-color", "unmet/fallback"],
        "native_timer_calls": report["nativeTimerCalls"],
        "close_routes": ["Escape", "official close-button callback", "Return"],
        "nonmatching_popup_rng_calls": 0,
        "invalid_wonder_draw_rejected": True,
        "repeated_gold_draw_rejected": True,
        "balanced_close_checked_in_lua": True,
        "owned_snapshot_stability_checked_in_lua": True,
        "production_stack_flow_and_offsets_checked": True,
        "hidden_recycled_stack_row_excluded_from_flow": True,
        "exact_installed_glyphgen_metric_wrap_checked": True,
        "production_callback_input_target_bounds_checked": True,
        "production_scroll_target_clipping_and_ranges_checked": True,
        "scope": "component-only; does not verify retail event order, retail layout semantics, rendering or pixel equivalence",
    }


def validate_injection_report(report: dict, mode: str) -> dict[str, object]:
    expected_error = f"INJECTED_{mode.upper()}_HANDLER_FAILURE"
    assert report["injection"] == mode
    assert report["original_error"] == expected_error, mode + " original injected Lua error was lost"
    assert report["timer_after_fault_compensation" if mode == "shown" else "timer_after_fault"] == 0
    assert report["timer_calls"] == [1, -1], mode + " timer was not balanced exactly once"
    assert report["lua_vm_discard_required"] is True
    assert report["faulted_lua_retry_rejected"] is True
    return {
        "injected_event": mode,
        "original_error_preserved": True,
        "timer_calls": report["timer_calls"],
        "faulted_vm_reuse_rejected": True,
        "scope": "Lua injection plus mock timer; native C++ cleanup path checked structurally below",
    }


def validate_cpp_fault_contract(source: str) -> dict[str, bool]:
    def block(start: str, end: str) -> str:
        begin = source.find(start)
        finish = source.find(end, begin + len(start))
        assert begin >= 0 and finish > begin, "missing native fault handler block: " + start
        return source[begin:finish]

    native_timer = block('if(std::strcmp(operation,"timer")==0){', 'if(std::strcmp(operation,"randomSeed")==0){')
    fault = block('void Fault() noexcept {', 'std::string SnapshotText(')
    stop = block('void Stop(){', 'void Submit(')
    close = block('void CloseInformationalPopup(){', 'private:')
    call = block('void Call(lua_CFunction function,void* argument){', 'void Fault() noexcept {')
    assert "enum class TimerState {Released,Held,TransitionUnknown};" in source
    assert "self.timerState_=TimerState::TransitionUnknown;" in native_timer
    assert native_timer.index("self.timerState_=TimerState::TransitionUnknown;") < native_timer.index("self.game_->EndTurnTimerSemaphoreDecrement();")
    assert "if(!faulted_)Fault();" in call and "if(!success)" in call
    assert "faulted_=true;active_=false;host_.popupVisible=false;" in fault
    assert "if(timerState_==TimerState::Held)" in fault and "timerState_=TimerState::TransitionUnknown;" in fault
    assert fault.count("game_->EndTurnTimerSemaphoreDecrement();") == 1
    assert "else if(timerState_==TimerState::TransitionUnknown)" in fault and "timerRecoveryFailed_=true;" in fault
    assert "if(faulted_)" in close and "Call(&Close,nullptr);" in close
    assert close.index("if(faulted_)") < close.index("Call(&Close,nullptr);")
    assert "timerRecoveryFailed_ || timerState_==TimerState::TransitionUnknown" in stop
    assert "scripts_.FreeLuaThread(vm_);vm_=nullptr;" in stop
    assert "if(!scripts_.IsQuiescent())" in stop
    assert stop.index("CloseInformationalPopup();") < stop.index("scripts_.FreeLuaThread(vm_);vm_=nullptr;")
    assert stop.index("timerState_!=TimerState::Released") < stop.index("scripts_.FreeLuaThread(vm_);vm_=nullptr;")
    assert "void Stop(){" in source and "if(vm_)std::terminate();" in source
    return {
        "call_failure_latches_fault": True,
        "held_timer_has_one_compensation_attempt": True,
        "uncertain_transition_is_never_retried": True,
        "faulted_close_skips_lua_reentry": True,
        "stop_requires_balanced_quiescent_vm_before_release": True,
        "destructor_rejects_unstopped_live_vm": True,
    }


def prepared_production_font_metrics(source: dict[str, bytes]) -> dict[str, object]:
    production_tree = prepared_control_tree(ET.fromstring(source["production_xml"]))
    icons = json.loads(source["inline_icons"].decode("utf-8-sig"))["icons"]
    metrics = production_font_metrics(production_tree, icons)
    if metrics.get("policy") != "CIV5_GLYPHGEN_GGXML_LAYOUT_V1":
        raise ValueError("production asset preparation returned an unsupported font metric policy")
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lua-dll", type=Path, default=DEFAULT_LUA)
    parser.add_argument("--snapshot-json-build", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, default=PROJECT / "evidence/ui_scene_component")
    args = parser.parse_args()
    encoder_report_path = args.snapshot_json_build.resolve(strict=True)
    encoder_build = json.loads(encoder_report_path.read_text(encoding="utf-8-sig"))
    if encoder_build.get("status") != "UI_SNAPSHOT_JSON_COMPONENT_BUILT":
        raise RuntimeError("Snapshot encoder requires its successful native component build")
    encoder_artifact = encoder_build["executable"]
    encoder_path = Path(encoder_artifact["path"]).resolve(strict=True)
    if sha256(encoder_path.read_bytes()) != encoder_artifact["sha256"]:
        raise RuntimeError("Native snapshot encoder differs from its build proof")
    paths = {**INPUTS, "lua_runtime": args.lua_dll.resolve(), "runner": Path(__file__).resolve(),
             "native_encoder": encoder_path, "native_encoder_build_report": encoder_report_path}
    tech_ready = all(path.is_file() for path in TECH_INPUTS.values())
    if tech_ready:
        paths.update(TECH_INPUTS)
    tech_tree_inputs = {
        name: (PROJECT / "Source/Assets/UI" / relative
               if (PROJECT / "Source/Assets/UI" / relative).is_file() else GAME_ASSETS / relative)
        for name, relative in TECH_TREE_ASSET_RELATIVE.items()
    }
    tech_tree_ready = tech_ready and all(path.is_file() for path in tech_tree_inputs.values())
    if tech_tree_ready:
        paths.update(tech_tree_inputs)
    frozen = {name: path.read_bytes() for name, path in paths.items()}
    before = {name: sha256(data) for name, data in frozen.items()}
    if before["snapshot_json_header"] != encoder_build["header"]["sha256"] or \
            before["lua_runtime"] != encoder_build["lua_dll"]["sha256"]:
        raise RuntimeError("Component header or shared Lua differs from the actual native encoder inputs")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]
    output = args.evidence_root / run_id
    frozen_dir = output / "frozen_inputs"
    frozen_dir.mkdir(parents=True, exist_ok=False)
    frozen_paths = {}
    for name, original in paths.items():
        copy = frozen_dir / (name + original.suffix)
        copy.write_bytes(frozen[name])
        if sha256(copy.read_bytes()) != before[name]:
            raise RuntimeError("failed to retain exact frozen input: " + name)
        frozen_paths[name] = copy
    runtime_alias = frozen_dir / "ZeroSisLua51_x64.dll"
    runtime_alias.write_bytes(frozen["lua_runtime"])
    if sha256(runtime_alias.read_bytes()) != before["lua_runtime"]:
        raise RuntimeError("Frozen native encoder runtime alias changed")
    harness_path = output / "harness.lua"
    harness = b""
    report = None
    checks = None
    injected_checks = {}
    native_fault_contract = None
    harness_hashes = {}
    tech_checks = {"status": "NOT_RUN_TECH_ASSETS_NOT_PREPARED"}
    tech_report = None
    tech_harness_path = None
    tech_tree_report = None
    tech_tree_harness_path = None
    tech_tree_checks = {"status": "NOT_RUN_TECH_TREE_ASSETS_NOT_PREPARED"}
    failure = None
    try:
        if tech_ready:
            for name, expected_hash in TECH_EXPECTED_SHA256.items():
                if sha256(frozen[name]) != expected_hash:
                    raise RuntimeError("official TechPopup source hash changed: " + name)
        xml = ET.fromstring(frozen["xml"])
        layout = control_tree(xml)
        font_metrics = prepared_production_font_metrics(frozen)
        template = frozen["test"].decode("utf-8-sig")
        harness = assemble(template, frozen, layout, font_metrics)
        harness_path.write_bytes(harness)
        result_text = run_lua(frozen_paths["native_encoder"], harness_path)
        report = json.loads(result_text)
        checks = validate_report(report)

        harness_hashes["normal"] = sha256(harness_path.read_bytes())
        for mode in ("shown", "processed"):
            injected_harness = assemble(template, frozen, layout, font_metrics, failure_mode=mode)
            injected_path = output / ("harness-" + mode + ".lua")
            injected_path.write_bytes(injected_harness)
            injected_result = json.loads(run_lua(frozen_paths["native_encoder"], injected_path))
            injected_checks[mode] = validate_injection_report(injected_result, mode)
            harness_hashes[mode] = sha256(injected_path.read_bytes())
            if harness_hashes[mode] != sha256(injected_harness):
                raise RuntimeError(mode + " injected harness changed during execution")

        native_fault_contract = validate_cpp_fault_contract(frozen["ui_context"].decode("utf-8-sig"))
        if tech_ready:
            tech_tree = control_tree(ET.fromstring(frozen["tech_xml"]))
            tech_tree["contextName"] = "TechPopup"
            tech_tree["popupKind"] = "Research"
            style_defaults = production_style_defaults(PROJECT / "Source/Assets/UI", tech_tree)
            tech_tree["styleDefaults"] = style_defaults["controls"]
            tech_tree["styleDefaultsSource"] = style_defaults["source"]
            tech_tree["styleDefaultsPolicy"] = style_defaults["policy"]
            icons = json.loads(frozen["inline_icons"].decode("utf-8-sig"))["icons"]
            tech_tree["fontMetrics"] = production_font_metrics(tech_tree, icons)
            tech_template = frozen["tech_fixture"].decode("utf-8-sig")
            tech_harness = assemble_tech(tech_template, frozen, tech_tree)
            tech_harness_path = output / "tech-harness.lua"
            tech_harness_path.write_bytes(tech_harness)
            tech_report = json.loads(run_lua(frozen_paths["native_encoder"], tech_harness_path,
                                             "__techUiComponentReport"))
            tech_checks = validate_tech_report(tech_report)
            harness_hashes["tech"] = sha256(tech_harness_path.read_bytes())
            if harness_hashes["tech"] != sha256(tech_harness):
                raise RuntimeError("Tech UI retained harness changed during execution")
        if tech_tree_ready:
            for name, expected_hash in TECH_TREE_EXPECTED_SHA256.items():
                if sha256(frozen[name]) != expected_hash:
                    raise RuntimeError("official BNW TechTree source hash changed: " + name)
            tree_layout = control_tree(ET.fromstring(frozen["tech_tree_xml"]))
            tree_layout["contextName"] = "TechTree"
            tree_layout["popupKind"] = "ResearchTree"
            tree_styles = production_style_defaults(PROJECT / "Source/Assets/UI", tree_layout)
            tree_layout["styleDefaults"] = tree_styles["controls"]
            tree_layout["styleDefaultsSource"] = tree_styles["source"]
            tree_layout["styleDefaultsPolicy"] = tree_styles["policy"]
            tree_icons = json.loads(frozen["inline_icons"].decode("utf-8-sig"))["icons"]
            tree_layout["fontMetrics"] = production_font_metrics(tree_layout, tree_icons)
            tree_template = frozen["tech_tree_fixture"].decode("utf-8-sig")
            tree_harness = assemble_tech_tree(tree_template, frozen, tree_layout)
            tech_tree_harness_path = output / "tech-tree-harness.lua"
            tech_tree_harness_path.write_bytes(tree_harness)
            tech_tree_report = json.loads(run_lua(frozen_paths["native_encoder"], tech_tree_harness_path,
                                                   "__techTreeUiComponentReport"))
            tech_tree_checks = validate_tech_tree_report(tech_tree_report)
            harness_hashes["tech_tree"] = sha256(tree_harness)
            if sha256(tech_tree_harness_path.read_bytes()) != harness_hashes["tech_tree"]:
                raise RuntimeError("TechTree retained harness changed during execution")
        after = {name: sha256(path.read_bytes()) for name, path in paths.items()}
        frozen_after = {name: sha256(path.read_bytes()) for name, path in frozen_paths.items()}
        if before != after:
            raise RuntimeError("a live source input changed during the component run")
        if before != frozen_after:
            raise RuntimeError("a retained frozen input changed during the component run")
        if sha256(runtime_alias.read_bytes()) != before["lua_runtime"]:
            raise RuntimeError("the native shared Lua alias changed during the component run")
        if sha256(harness_path.read_bytes()) != sha256(harness):
            raise RuntimeError("the executed frozen Lua harness changed during the component run")
        if tech_harness_path and sha256(tech_harness_path.read_bytes()) != harness_hashes["tech"]:
            raise RuntimeError("the executed frozen Tech UI harness changed during the component run")
        if tech_tree_harness_path and sha256(tech_tree_harness_path.read_bytes()) != harness_hashes["tech_tree"]:
            raise RuntimeError("the executed frozen TechTree UI harness changed during the component run")
        for mode in ("shown", "processed"):
            if sha256((output / ("harness-" + mode + ".lua")).read_bytes()) != harness_hashes[mode]:
                raise RuntimeError(mode + " retained injected harness changed during the component run")
        status = "PASS_UI_SCENE_COMPONENT_ONLY"
    except Exception as exc:
        after = {name: sha256(path.read_bytes()) for name, path in paths.items()}
        frozen_after = {name: sha256(path.read_bytes()) for name, path in frozen_paths.items()}
        failure = f"{type(exc).__name__}: {exc}"
        status = "FAIL_UI_SCENE_COMPONENT_ONLY"
    evidence = {
        "status": status,
        "snapshot_encoding_backend": "BOUNDED_NATIVE_CPP_WITH_ACTUAL_SHARED_LUA51",
        "native_runtime_alias": {"path": str(runtime_alias), "sha256": sha256(runtime_alias.read_bytes())},
        "run_id": run_id,
        "inputs_unchanged_after_run": before == after and before == frozen_after,
        "inputs": {name: {"original_source": str(paths[name]),
                          "frozen_copy": str(frozen_paths[name]),
                          "sha256": before[name], "bytes": len(frozen[name]),
                          "live_unchanged_after_run": before[name] == after[name],
                          "frozen_copy_unchanged_after_run": before[name] == frozen_after[name]}
                   for name in paths},
        "harness_copy": str(harness_path),
        "test_harness_sha256": sha256(harness) if harness else None,
        "harness_copy_sha256": sha256(harness_path.read_bytes()) if harness_path.exists() else None,
        "failure_injections": injected_checks,
        "native_timer_fault_contract_static": native_fault_contract,
        "executed_harness_sha256": harness_hashes,
        "checks": checks,
        "snapshots": report,
        "tech_component": {"checks": tech_checks, "snapshot": tech_report,
                           "original_source_hashes_locked": tech_ready,
                           "harness_copy": str(tech_harness_path) if tech_harness_path else None},
        "tech_tree_component": {"checks": tech_tree_checks, "snapshot": tech_tree_report,
                                "original_source_hashes_locked": tech_tree_ready,
                                "harness_copy": str(tech_tree_harness_path) if tech_tree_harness_path else None},
        "failure": failure,
        "limitations": [
            "Lua failure injections use mock players, native adapters, timer and deterministic RNG; the native C++ timer recovery/Stop path is source-checked, not dynamically executed.",
            "Does not verify Civ V callback ordering, renderer, XML style expansion, font measurement or pixels.",
            "Fixtures use mock Game/player/native bindings and do not prove SDK callbacks, retail layout or pixels.",
        ],
    }
    (output / "report.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "evidence": str(output), "checks": checks,
                      "tech_tree_component": tech_tree_checks, "failure": failure}, ensure_ascii=False))
    return 0 if failure is None else 1


if __name__ == "__main__":
    raise SystemExit(main())
