"""Run the official BNW WhosWinning popup through the retained-scene input addendum."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_LUA = PROJECT / "Build/SharedLuaRuntime/Lua/ZeroSisLua51_x64.dll"
DEFAULT_SNAPSHOT_JSON_BUILD = PROJECT / "evidence/ui_snapshot_json_component/20261003T134802Z_658a13d832dd/build_result.json"
POPUP_DIR = PROJECT / "Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups"
INPUTS = {
    "harness": PROJECT / "Tests/ui_presentation_input.lua",
    "scene": PROJECT / "Source/Host/UiScene.lua",
    "addendum": PROJECT / "Source/Presentation/UiPresentationInput.lua",
    "instance_manager": PROJECT / "Source/Assets/UI/Assets/UI/InstanceManager.lua",
    "icon_support": PROJECT / "Source/Assets/UI/Assets/UI/IconSupport.lua",
    "flua_vector": PROJECT / "Source/Assets/UI/Assets/Gameplay/Lua/FLuaVector.lua",
    "popup": POPUP_DIR / "WhosWinningPopup.lua",
    "xml": POPUP_DIR / "WhosWinningPopup.xml",
    "production_xml": PROJECT / "Source/Assets/UI/Assets/DLC/Expansion2/UI/InGame/Popups/ProductionPopup.xml",
    "inline_icons": PROJECT / "evidence/ui_popup/assets/inline_icons.json",
    "lua_runtime": DEFAULT_LUA,
    "unit_panel_scene_test": PROJECT / "Tests/unit_panel_scene.lua",
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence-root", type=Path, default=PROJECT / "evidence/ui_presentation_input")
    parser.add_argument("--build-root", type=Path, default=PROJECT / "Build/UiPresentationInput")
    parser.add_argument("--lua-dll", type=Path, default=DEFAULT_LUA)
    parser.add_argument("--snapshot-json-build", type=Path, default=DEFAULT_SNAPSHOT_JSON_BUILD)
    args = parser.parse_args()
    inputs = dict(INPUTS)
    inputs["lua_runtime"] = args.lua_dll.absolute()
    inputs["snapshot_json_build_report"] = args.snapshot_json_build.absolute()
    if not inputs["snapshot_json_build_report"].is_file():
        raise FileNotFoundError(inputs["snapshot_json_build_report"])
    build_report = json.loads(inputs["snapshot_json_build_report"].read_text(encoding="utf-8-sig"))
    if build_report.get("status") != "UI_SNAPSHOT_JSON_COMPONENT_BUILT":
        raise RuntimeError("Snapshot encoder report is not a successful shared-Lua component build")
    encoder_path = Path(build_report["executable"]["path"]).absolute()
    encoder_dll_path = Path(build_report["lua_dll"]["path"]).absolute()
    if not encoder_path.is_file() or not encoder_dll_path.is_file():
        raise FileNotFoundError("Reported snapshot encoder or Lua provider is missing")
    if sha(encoder_path.read_bytes()) != build_report["executable"]["sha256"]:
        raise RuntimeError("Snapshot encoder differs from its successful build report")
    if sha(encoder_dll_path.read_bytes()) != build_report["lua_dll"]["sha256"]:
        raise RuntimeError("Snapshot encoder provider DLL differs from its successful build report")
    if build_report["lua_dll"]["sha256"] != build_report["lua_provider_dll"]["sha256"]:
        raise RuntimeError("Snapshot encoder's local DLL differs from its provider build DLL")
    inputs["native_encoder"] = encoder_path
    inputs["native_encoder_provider"] = encoder_dll_path
    frozen = {key: path.read_bytes() for key, path in inputs.items()}
    hashes = {key: sha(data) for key, data in frozen.items()}

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]
    evidence = args.evidence_root.resolve() / run_id
    build = args.build_root.resolve() / run_id
    frozen_dir = evidence / "frozen_inputs"
    frozen_dir.mkdir(parents=True, exist_ok=False)
    build.mkdir(parents=True, exist_ok=False)
    copies = {}
    for key, path in inputs.items():
        # The native encoder loads its shared Lua provider by the provider's
        # original filename from the executable directory.
        target = frozen_dir / (path.name if key in ("native_encoder", "native_encoder_provider") else key + path.suffix)
        target.write_bytes(frozen[key])
        if sha(target.read_bytes()) != hashes[key]:
            raise RuntimeError("frozen input copy mismatch: " + key)
        copies[key] = target

    sys.path.insert(0, str(PROJECT / "tools"))
    spec = importlib.util.spec_from_file_location("ui_scene_verifier", PROJECT / "tools/verify_ui_scene.py")
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    failure = None
    result = None
    harness = b""
    research_result = None
    research_tree_result = None
    unit_panel_result = None
    research_style_proof = None
    try:
        layout = module.control_tree(ET.fromstring(frozen["xml"]))
        source = {key: data for key, data in frozen.items()}
        source["scene"] = frozen["scene"] + b"\n" + frozen["addendum"]
        template = frozen["harness"].decode("utf-8-sig")
        template = template.replace(
            "elseif operation == 'uiFrameTime' then",
            "elseif operation == 'snapshotJson' then\n    return __ZeroSisSnapshotJson(values[1], values[2])\n  elseif operation == 'uiFrameTime' then")
        font_metrics = module.prepared_production_font_metrics(source)
        layout["fontMetrics"] = font_metrics
        harness_template = template.replace("@@RESEARCH_INPUT_CASE@@", "false").replace(
            "@@RESEARCH_TREE_INPUT_CASE@@", "false")
        harness = module.assemble(harness_template, source, layout, font_metrics)
        harness_path = build / "ui_presentation_input.lua"
        harness_path.write_bytes(harness)
        result_text = module.run_lua(copies["native_encoder"], harness_path, "__uiSceneComponentReport")
        result = json.loads(result_text)
        assert result["nativeTimer"] == 0, "popup timer did not finish released"
        assert result["nativeTimerCalls"] == [1, -1, 1, -1, 1, -1], f"unexpected timer transitions: {result['nativeTimerCalls']}"
        expected_seed = 731 + sum(len(result[name]["draws"]) for name in ("first", "second", "third"))
        assert result["finalSeed"] == expected_seed, (
            f"input dispatch altered RNG accounting: expected {expected_seed}, got {result['finalSeed']}"
        )
        assert b"DispatchLeftClick" in harness, "input addendum missing from assembled Lua"
        research_layout = dict(layout)
        research_layout["popupKind"] = "Research"
        research_layout["contextName"] = "TechPopup"
        research_layout["fontMetrics"] = font_metrics
        # Keep the input-only ranking layout, but snapshot comparison must use
        # the official slider/shuttle geometry rather than invented defaults.
        from prepare_ui_popup_assets import production_style_defaults
        research_style_proof = production_style_defaults(frozen_dir / 'research_styles', research_layout)
        styles = research_style_proof['controls']
        research_layout["styleDefaults"] = styles
        research_layout["styleDefaultsSource"] = research_style_proof['source']
        research_layout["styleDefaultsPolicy"] = research_style_proof['policy']
        research_harness_template = template.replace("@@RESEARCH_INPUT_CASE@@", "true").replace(
            "@@RESEARCH_TREE_INPUT_CASE@@", "false")
        research_harness = module.assemble(research_harness_template, source,
                                           research_layout, font_metrics)
        research_path = build / "research_timer0_input.lua"
        research_path.write_bytes(research_harness)
        research_result = json.loads(module.run_lua(copies["native_encoder"], research_path, "__uiSceneComponentReport"))
        assert research_result["researchInput"] and research_result["timer"] == 0
        assert research_result["inactiveRejected"] and research_result["staleRejected"]
        assert research_result["clicks"] == 1 and research_result["clock"] > 0

        research_tree_layout = dict(layout)
        research_tree_layout["popupKind"] = "ResearchTree"
        research_tree_layout["contextName"] = "TechTree"
        research_tree_layout["fontMetrics"] = font_metrics
        research_tree_layout["styleDefaults"] = {name: {"attributes": {}} for name in styles}
        research_tree_layout["styleDefaultsSource"] = "component-fixture:input-only"
        research_tree_layout["styleDefaultsPolicy"] = "INERT_INPUT_ONLY_NO_VISUAL_CLAIM"
        # This input-only fixture needs just the detached button and horizontal
        # panel appended by the harness. Reusing ranking scrollbars would make
        # a tree snapshot claim measurements that this fixture never prepared.
        research_tree_layout["children"] = []
        research_tree_template = template.replace("@@RESEARCH_INPUT_CASE@@", "false").replace(
            "@@RESEARCH_TREE_INPUT_CASE@@", "true")
        research_tree_harness = module.assemble(research_tree_template, source,
                                                research_tree_layout, font_metrics)
        research_tree_path = build / "research_tree_timer1_horizontal_input.lua"
        research_tree_path.write_bytes(research_tree_harness)
        research_tree_result = json.loads(module.run_lua(copies["native_encoder"], research_tree_path, "__uiSceneComponentReport"))
        assert research_tree_result["researchTreeInput"] and research_tree_result["timerOpen"] == 1
        assert research_tree_result["timerClosed"] == 0 and research_tree_result["clicks"] == 1
        assert research_tree_result["clock"] > 0 and research_tree_result["scrollX"] == 0
        assert research_tree_result["maximumScroll"] == 180 and research_tree_result["rngUnchanged"]
        assert research_tree_result["lifecycle"] == "queued,shown:67,closed,processed:67"

        unit_panel_layout = dict(layout)
        unit_panel_layout["popupKind"] = "UnitPanel"
        unit_panel_layout["contextName"] = "UnitPanel"
        unit_panel_layout["layoutVariant"] = "default"
        unit_panel_layout["styleDefaults"] = styles
        unit_panel_layout["children"] = list(layout.get("children", [])) + [{
            "kind": "Instance", "attributes": {"Name": "UnitPanelInputCase"},
            "children": [
                {"kind": "Button", "attributes": {"ID": "UnitPanelConsumeOnly", "ConsumeMouse": "1", "Size": "10,20"}, "children": []},
                {"kind": "Button", "attributes": {"ID": "UnitPanelConsumeClick", "ConsumeMouse": "1", "Size": "10,20"}, "children": []},
                {"kind": "Button", "attributes": {"ID": "UnitPanelNormalClick", "Size": "10,20"}, "children": []},
            ],
        }]
        unit_panel_template = template.replace("@@RESEARCH_INPUT_CASE@@", "true").replace(
            "@@RESEARCH_TREE_INPUT_CASE@@", "false")
        branch_start = unit_panel_template.index("if RESEARCH_INPUT_CASE then")
        branch_end = unit_panel_template.index("if RESEARCH_TREE_INPUT_CASE then", branch_start)
        unit_panel_template = (unit_panel_template[:branch_start] + "if RESEARCH_INPUT_CASE then\n" +
                               frozen["unit_panel_scene_test"].decode("utf-8-sig") +
                               "\n  return\nend\n\n" + unit_panel_template[branch_end:])
        unit_panel_harness = module.assemble(unit_panel_template, source, unit_panel_layout, font_metrics)
        unit_panel_path = build / "unit_panel_consume_mouse_input.lua"
        unit_panel_path.write_bytes(unit_panel_harness)
        unit_panel_result = json.loads(module.run_lua(copies["native_encoder"], unit_panel_path,
                                                       "__uiSceneComponentReport"))
        assert unit_panel_result["unitPanelInput"] and unit_panel_result["consumeClickDeduplicated"]
        assert unit_panel_result["consumeOnly"] and unit_panel_result["clicks"] == 1
        assert unit_panel_result["hiddenRejected"]
    except Exception as exc:  # retain exact failure artifact for review
        failure = f"{type(exc).__name__}: {exc}"

    live_after = {key: sha(path.read_bytes()) for key, path in inputs.items()}
    copies_after = {key: sha(path.read_bytes()) for key, path in copies.items()}
    invariant = hashes == live_after == copies_after
    status = "PASS_UI_PRESENTATION_INPUT_COMPONENT_ONLY" if failure is None and invariant else "FAIL_UI_PRESENTATION_INPUT_COMPONENT_ONLY"
    report = {
        "status": status,
        "run_id": run_id,
        "scope": "Lua retained-scene input dispatch component with official popup Lua/layout; no host/window connection",
        "inputs_unchanged_after_run": invariant,
        "inputs": {key: {"original_path": str(inputs[key]), "frozen_path": str(copies[key]),
                         "sha256": hashes[key], "bytes": len(frozen[key]),
                         "original_unchanged": hashes[key] == live_after[key],
                         "frozen_unchanged": hashes[key] == copies_after[key]} for key in inputs},
        "build_artifact": str(build / "ui_presentation_input.lua"),
        "harness_sha256": sha(harness) if harness else None,
        "checks": {
            "official_escape_and_return_callbacks": True if result else None,
            "official_close_button_gridbutton_callback": True if result else None,
            "repeated_repaint_snapshot_is_identical_and_rng_free": True if result else None,
            "invalid_fractional_string_and_stale_keys_rejected": True if result else None,
            "hidden_button_excluded_and_rejected": True if result else None,
            "duplicate_closed_dispatch_has_no_timer_release": True if result else None,
            "rng_seed_unchanged_by_repaint_and_input_dispatch": result.get("finalSeed") == 739 if result else None,
            "research_timer0_active_row_click_and_clock": research_result.get("researchInput") if research_result else None,
            "research_inactive_and_stale_row_rejected": research_result.get("inactiveRejected") and research_result.get("staleRejected") if research_result else None,
            "research_tree_timer1_leftclick_only_and_clock": research_tree_result.get("researchTreeInput") if research_tree_result else None,
            "research_tree_snapshot_preserves_left_and_right_metadata": research_tree_result.get("researchTreeInput") if research_tree_result else None,
            "research_tree_horizontal_scroll_range_and_reflow": research_tree_result.get("maximumScroll") == 180 and research_tree_result.get("scrollX") == 0 if research_tree_result else None,
            "research_tree_queued_shown_processed_and_timer_balance": research_tree_result.get("lifecycle") == "queued,shown:67,closed,processed:67" and research_tree_result.get("timerClosed") == 0 if research_tree_result else None,
            "unit_panel_consumemouse_target_and_click_deduplication": unit_panel_result.get("consumeClickDeduplicated") and unit_panel_result.get("consumeOnly") if unit_panel_result else None,
            "unit_panel_click_dispatch_and_hidden_stale_rejection": unit_panel_result.get("clicks") == 1 and unit_panel_result.get("hiddenRejected") if unit_panel_result else None,
        },
        "component_result": result,
        "research_input_component_result": research_result,
        "research_snapshot_style_provenance": research_style_proof,
        "research_tree_input_component_result": research_tree_result,
        "unit_panel_input_component_result": unit_panel_result,
        "gamecore_loaded": False,
        "sdk_execution": False,
        "host_window_connected": False,
        "failure": failure,
        "limitations": [
            "The shared Lua 5.1 runtime executes official popup Lua against mock Civ/UI bindings and frozen layout XML.",
            "No Win32 message, pointer hit-test, renderer, retail UI manager, SDK, or GameCore execution is exercised.",
            "GetInputTargets supplies identities only; a future native host must perform real visible-control hit-testing.",
        ],
    }
    (evidence / "conformance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "evidence": str(evidence), "build": str(build), "failure": failure}, ensure_ascii=False))
    return 0 if status.startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
