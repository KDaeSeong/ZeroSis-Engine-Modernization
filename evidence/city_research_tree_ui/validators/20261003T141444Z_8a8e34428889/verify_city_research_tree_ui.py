"""Strictly verify one EN/KO pair of actual SDK TechTree input/turn/restore runs."""
from __future__ import annotations

import argparse
import configparser
import hashlib
import importlib.util
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
ROOT = PROJECT / "evidence/city_research_tree_ui"
LANGUAGES = {"en_US", "ko_KR"}
sys.path.insert(0, str(PROJECT / "tools"))
from collect_baseline import digest
from probe_world_builder import artifact
from verify_city_decision_probe import (
    _decision_snapshot_semantics, fail, inspect_state_snapshot, int_row, lines, one,
    recorded, verify_game_restore,
)
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts
from verify_city_research_ui import recorded_exact, REQUIRED_HOST

FROZEN_PATHS = (
    PROJECT / "tools/verify_city_research_tree_ui.py",
    PROJECT / "tools/verify_city_research_ui.py",
    PROJECT / "tools/verify_city_decision_probe.py",
    PROJECT / "tools/verify_native_save_restore.py",
    PROJECT / "tools/verify_restore_game_metadata.py",
    PROJECT / "tools/verify_first_turn_candidate.py",
    PROJECT / "tools/verify_world_builder_map_object.py",
    PROJECT / "tools/prepare_ui_popup_assets.py",
    PROJECT / "tools/civ5_ui_assets.py",
    PROJECT / "tools/ui_window_frame.py",
    PROJECT / "tools/live_ui_window_driver.py",
    PROJECT / "tools/render_ui_popup.py",
    PROJECT / "Source/Host/UiScene.lua",
    PROJECT / "Source/Presentation/UiPresentationInput.lua",
    PROJECT / "Source/Host/ResearchCommandGuard.lua",
    PROJECT / "Source/Host/UiPopupContext.h",
    PROJECT / "Source/Host/HostRun.h",
    PROJECT / "Source/Host/HostMain.cpp",
    PROJECT / "Source/Host/CityDecisionProbe.h",
)


def freeze_inputs() -> tuple[Path, list[dict], dict[str, str]]:
    folder = ROOT / "validators" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    rows, hashes = [], {}
    for source in FROZEN_PATHS:
        if not source.is_file():
            fail(f"Missing ResearchTree verifier/source input: {source}")
        before = digest(source)
        target = folder / source.name
        shutil.copy2(source, target)
        row = artifact(target)
        if row["sha256"] != before:
            fail(f"Frozen input differs from live source: {source}")
        rows.append({"original_path": str(source), **row})
        hashes[str(source)] = before
    return folder, rows, hashes


def exact_artifact(result: dict, key: str, path: Path) -> Path:
    row = result.get(key)
    if not isinstance(row, dict):
        fail(f"ResearchTree result omits {key}")
    check_artifacts(row)
    if Path(row["path"]).resolve() != path.resolve() or not path.is_file():
        fail(f"ResearchTree {key} escaped its exact run directory")
    return path.resolve()


def generated_file(result: dict, path: Path, runtime: Path) -> Path:
    path = path.resolve(strict=True)
    if not path.is_relative_to(runtime.resolve() / "sessions"):
        fail("ResearchTree session artifact escaped the private runtime")
    matches = [row for row in result.get("generated_files", [])
               if Path(row.get("path", "")).resolve() == path]
    if len(matches) != 1:
        fail(f"Expected one immutable generated-file row for {path.name}")
    check_artifacts(matches[0])
    return path


def verify_source(request: dict) -> dict:
    reports = {}
    for key in ("candidate_build", "shared_lua_build", "found_value_shared_sdk_build"):
        row = request.get(key)
        if not isinstance(row, dict):
            fail(f"ResearchTree request lacks {key} source provenance")
        check_artifacts(row)
        reports[key] = json.loads(Path(row["path"]).read_text(encoding="utf-8"))
    build, shared, found = (reports[key] for key in
                            ("candidate_build", "shared_lua_build", "found_value_shared_sdk_build"))
    if found.get("status") != "FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED" or \
       found.get("gamecore", {}).get("sha256") != "a58a0d20cbaecad13ea248fe362d0c15bb97096802b9f60c5ef5f0dd8bb90c07" or \
       shared.get("status") != "SHARED_LUA_RUNTIME_CANDIDATE_BUILT":
        fail("ResearchTree run did not use the pinned shared-found-values GameCore and shared Lua runtime")
    source_rows = {Path(row.get("path", "")).name: row for row in build.get("sources", [])}
    if not REQUIRED_HOST <= source_rows.keys():
        fail("Frozen Host source closure omits a ResearchTree dependency")
    for name in REQUIRED_HOST:
        check_artifacts(source_rows[name])
    live_paths = {
        "UiScene.lua": PROJECT / "Source/Host/UiScene.lua",
        "UiPresentationInput.lua": PROJECT / "Source/Presentation/UiPresentationInput.lua",
        "ResearchCommandGuard.lua": PROJECT / "Source/Host/ResearchCommandGuard.lua",
        "UiPopupContext.h": PROJECT / "Source/Host/UiPopupContext.h",
        "HostRun.h": PROJECT / "Source/Host/HostRun.h",
        "HostMain.cpp": PROJECT / "Source/Host/HostMain.cpp",
        "CityDecisionProbe.h": PROJECT / "Source/Host/CityDecisionProbe.h",
    }
    for name, live in live_paths.items():
        if digest(Path(source_rows[name]["path"])) != digest(live):
            fail(f"Frozen ResearchTree Host source differs from current owned source: {name}")
    host = {name: Path(source_rows[name]["path"]).read_text(encoding="utf-8") for name in REQUIRED_HOST}
    joined = "\n".join(host.values())
    required = (
        "--check-city-research-tree-ui", "ResearchTree", "TechTree", "OpenResearchTree()",
        "ChooseResearchTreeTechnology()", "RESEARCH_TREE_UI_HANDOFF_ROUTE=OFFICIAL_OPEN_TT_BUTTON_DEFERRED_OWNER_NEW_VM",
        "RESEARCH_TREE_UI_INPUT_ROUTE=OFFICIAL_BNW_TECH_TREE_RETAINED_BUTTON_SDK_RECEIVER",
        "RESEARCH_TREE_UI_RESEARCH_DIRTY", "Only normal local research selection is supported",
        "Only the original normal research-tree popup request is supported",
        "RESEARCH_TREE_UI_INPUT=", "RESEARCH_TREE_UI_HORIZONTAL_SCROLL=",
        "Research frame clock changed gameplay state", "Research-tree horizontal scroll did not move its original viewport",
        "Research-tree scroll/reset changed gameplay, RNG or its measured range",
    )
    for token in required:
        if token not in joined:
            fail(f"Frozen Host source omits the ResearchTree contract: {token}")
    header = Path(source_rows["UiPopupAssets.generated.h"]["path"]).read_bytes()
    guard = (PROJECT / "Source/Host/ResearchCommandGuard.lua").read_bytes()
    scene = (PROJECT / "Source/Host/UiScene.lua").read_bytes()
    input_lua = (PROJECT / "Source/Presentation/UiPresentationInput.lua").read_bytes()
    def cpp_literal(data: bytes) -> bytes:
        return b"\n".join(b'"' + b"".join(f"\\x{byte:02x}".encode("ascii") for byte in data[i:i+64]) + b'"'
                            for i in range(0, len(data), 64))
    if cpp_literal(guard) not in header or cpp_literal(scene + b"\n" + input_lua) not in header:
        fail("Frozen generated UI header does not byte-embed the ResearchTree guard and scene/input sources")
    runtime_inputs = {Path(row.get("path", "")).name: row for row in request.get("inputs", [])}
    for name in ("ZeroSisHost_x64.exe", "CvGameCoreDLL_Expansion2_x64.dll", "ZeroSisLua51_x64.dll",
                 "rules.db", "localization.db", "bundle.manifest"):
        if name not in runtime_inputs:
            fail(f"Private ResearchTree runtime omits {name}")
        check_artifacts(runtime_inputs[name])
    if runtime_inputs["ZeroSisHost_x64.exe"]["sha256"] != build.get("executable", {}).get("sha256") or \
       runtime_inputs["ZeroSisLua51_x64.dll"]["sha256"] != shared.get("lua_dll", {}).get("sha256") or \
       runtime_inputs["CvGameCoreDLL_Expansion2_x64.dll"]["sha256"] != found["gamecore"]["sha256"]:
        fail("Private ResearchTree Host/GameCore/Lua hashes differ from their frozen build reports")
    if request.get("shared_found_value_sdk_enabled") is not True or \
       request.get("research_ui_enabled") is not True or request.get("research_tree_requested") is not True or \
       request.get("research_window_requested") is not False or \
       request.get("research_tree_input_profile") != "OWNER_RETAINED_CALLBACK_NORMAL_RESEARCH_HORIZONTAL_SCROLL_ESCAPE_V1" or \
       request.get("ui_shift_policy") != "NORMAL_FIXTURE_FALSE_V1":
        fail("ResearchTree request did not select its exact direct owner-input profile")
    settings = request.get("ui_settings_source")
    if not isinstance(settings, dict) or not all(isinstance(settings.get(key), str)
                                                  for key in ("original_source", "path", "sha256")):
        fail("ResearchTree request lacks frozen UserSettings provenance")
    source_ini = Path(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5\UserSettings.ini")
    runtime = Path(request.get("cwd", "")).resolve(strict=True)
    frozen_path = Path(settings["path"]).resolve(strict=True)
    if Path(settings["original_source"]).resolve(strict=True) != source_ini.resolve(strict=True) or \
       frozen_path != (runtime / "UserSettings.frozen.ini").resolve(strict=True) or \
       digest(frozen_path) != settings["sha256"] or \
       ("bytes" in settings and settings["bytes"] != frozen_path.stat().st_size):
        fail("ResearchTree UI settings do not match the exact private frozen user INI copy")
    ini = configparser.ConfigParser(interpolation=None, strict=True)
    ini.read_string(frozen_path.read_text(encoding="utf-8-sig"))
    try:
        small_text = ini["InterfaceSettings"]["SmallUIAssets"].strip()
    except KeyError:
        fail("Frozen ResearchTree user INI lacks InterfaceSettings.SmallUIAssets")
    small = request.get("small_ui_assets_setting")
    if small_text not in ("0", "1") or type(small) is not bool or (small_text == "1") is not small or \
       type(request.get("small_ui_assets_environment_removed")) is not bool or \
       request.get("auto_ui_assets_effective_retail_setting_verified") is not False:
        fail("ResearchTree frozen SmallUIAssets value or effective-retail limitation differs")
    popup = host["UiPopupContext.h"]
    if 'std::getenv("ZEROSIS_UI_SMALL_ASSETS")' not in popup or \
       "smallUiAssets_=small[0]=='1'" not in popup or "lua_pushboolean(state,self.smallUiAssets_)" not in popup:
        fail("ResearchTree context does not bind the explicit SmallUIAssets setting")
    return {**reports, "host_sources": {name: source_rows[name] for name in sorted(REQUIRED_HOST)},
            "gamecore_sha256": found["gamecore"]["sha256"],
            "host_executable_sha256": runtime_inputs["ZeroSisHost_x64.exe"]["sha256"],
            "shared_lua_sha256": runtime_inputs["ZeroSisLua51_x64.dll"]["sha256"],
            "small_ui_assets_setting": small, "ui_settings_source": settings,
            "ui_settings_sha256": digest(frozen_path), "ui_settings_bytes": frozen_path.stat().st_size}


def verify_run(run_id: str) -> dict:
    if not re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", run_id):
        fail("ResearchTree run ID has an invalid immutable identity")
    folder = ROOT / run_id
    result_path, request_path = folder / "result.json", folder / "request.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    check_artifacts(result); check_artifacts(request)
    exact_artifact(result, "request", request_path)
    exact_artifact(result, "stdout", folder / "stdout.log")
    exact_artifact(result, "stderr", folder / "stderr.log")
    lang = request.get("language")
    if request.get("run_id") != run_id or lang not in LANGUAGES or \
       result.get("status") != "ISOLATED_SDK_OFFICIAL_RESEARCH_TREE_UI_TURN_AND_NATIVE_RESTORE_PASS":
        fail("Run is not a successful exact-language actual SDK ResearchTree execution")
    if result.get("exit_code") != 0 or type(result.get("pid")) is not int or result["pid"] <= 0 or \
       result.get("timed_out") is not False or result.get("host_failures") != [] or \
       result.get("research_tree_enabled") is not True or result.get("research_tree_ui_verified") is not True or \
       result.get("positive_scroll_motion_verified") is not True or result.get("turn_advance_verified") is not True or \
       result.get("research_tree_window_verified") is not False:
        fail("ResearchTree process, direct input, positive scroll, or turn/restore flags differ")
    for key in ("future_tech_queue_verified", "shift_queue_verified", "free_tech_or_steal_verified",
                "renderer_verified", "interactive_input_verified", "retail_save_compatibility_verified",
                "accepted_stage_promoted"):
        if result.get(key) is not False:
            fail(f"ResearchTree run overstates unsupported scope: {key}")
    if result.get("research_window_enabled") is not False or result.get("native_tech_hit_dispatch_verified") is not False or \
       result.get("gpu_frame_bitmap_parity_verified") is not False:
        fail("Direct ResearchTree run claims native window/GPU presentation proof")
    runtime = (PROJECT / "Build/CityResearchTreeUiRuntime" / run_id).resolve()
    if Path(request.get("cwd", "")).resolve() != runtime or \
       request.get("command", [None])[1:] != ["--check-city-research-tree-ui", lang]:
        fail("ResearchTree command or private runtime path differs")
    stdout = (folder / "stdout.log").read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    stderr = (folder / "stderr.log").read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    if any("HOST_FAILURE:" in line or "HOST_NATIVE_EXCEPTION" in line for line in stderr.splitlines()):
        fail("ResearchTree stderr contains a native or host failure")
    if stderr.splitlines() != [f"UI_WINDOW_PROCESS_START={result['pid']}"]:
        fail("ResearchTree stderr must contain only the exact owned-child process-start marker")
    provenance = verify_source(request)
    small = "1" if provenance["small_ui_assets_setting"] else "0"
    required_lines = (
        "RESEARCH_TREE_UI_HANDOFF_ROUTE=OFFICIAL_OPEN_TT_BUTTON_DEFERRED_OWNER_NEW_VM",
        "RESEARCH_TREE_UI_TIMER_SHOWN=1", "RESEARCH_TREE_UI_RESEARCH_DIRTY=1",
        "RESEARCH_TREE_UI_SELECTION_REMAINS_OPEN=true", "RESEARCH_TREE_UI_TIMER_AFTER_SELECTION=1",
        "RESEARCH_TREE_UI_STALE_INPUT_REJECTED=true", "RESEARCH_TREE_UI_TIMER_SEMAPHORE=0",
        "RESEARCH_TREE_UI_INPUT_ROUTE=OFFICIAL_BNW_TECH_TREE_RETAINED_BUTTON_SDK_RECEIVER",
        "RESEARCH_TREE_UI_SHUTDOWN_PASS ORIGINAL_POPUP_CALLBACK=true SDK_RECEIVER=true TURN_AND_NATIVE_RESTORE=true RETAIL_UI_EQUIVALENCE=false",
        "RESEARCH_UI_OWNER_CLOCK=0,0.25", "RESEARCH_UI_FRAME_GAMEPLAY_STATE_EQUAL=true",
        "RESEARCH_UI_SMALL_ASSETS=" + small, "RESEARCH_TREE_UI_SMALL_ASSETS=" + small,
        "CITY_DECISION_INPUT_ROUTE=SDK_CITY_PUSH_ORDER_AND_OFFICIAL_RESEARCH_UI",
        "FOUND_CITY_RESTORE_FRESH_SESSION=true", "FOUND_CITY_RESTORE_STATE_EQUAL=true",
        "FOUND_CITY_RESTORE_IDLE_STATE_EQUAL=true", "FOUND_CITY_RESTORE_IDLE_UPDATES=3",
        "FOUND_CITY_RESTORED_CORE_MODULE_UNLOADED=true", "CITY_DECISION_RESTORE_FRESH_SESSION=true",
        "CITY_DECISION_RESTORED_CORE_MODULE_UNLOADED=true", "CITY_DECISION_RESTORE_STATE_EQUAL=true",
        "CITY_DECISION_RESTORE_IDLE_STATE_EQUAL=true", "CITY_DECISION_RESTORE_IDLE_UPDATES=3",
        "CITY_DECISION_BEFORE_TURN", "CITY_DECISION_AFTER_TURN",
        "CITY_DECISION_RESTORE_SECTIONS_EQUAL",
        "CITY_DECISION_SHUTDOWN_PASS GAMECORE_LOADED=true CITY_DECISIONS_ACCEPTED=true TURN_ADVANCE_VERIFIED=true CITY_DECISION_RESTORE_VERIFIED=true",
        "RESEARCH_TREE_UI_SHUTDOWN_PASS ORIGINAL_POPUP_CALLBACK=true SDK_RECEIVER=true TURN_AND_NATIVE_RESTORE=true RETAIL_UI_EQUIVALENCE=false",
    )
    for marker in required_lines:
        if "=" in marker and lines(stdout, marker.split("=", 1)[0]) != [marker.split("=", 1)[1]]:
            fail(f"ResearchTree output marker is missing, duplicated, or changed: {marker}")
        if "=" not in marker and len(lines(stdout, marker)) != (4 if marker == "CITY_DECISION_RESTORED" else 1):
            fail(f"ResearchTree output marker is missing, duplicated, or changed: {marker}")
    rng = one(stdout, "RESEARCH_UI_FRAME_SYNC_RNG").split("|")
    if len(rng) != 2 or not all(value.isdigit() for value in rng) or rng[0] != rng[1]:
        fail("ResearchTree frame did not preserve its synchronous SDK RNG seed")
    event = one(stdout, "RESEARCH_UI_LOCAL_EVENT")
    match = re.fullmatch(r"local-research:(\d+):0:-1:0", event)
    if not match:
        fail("ResearchTree did not dispatch the exact normal local research receiver tuple")
    tech = int(match.group(1))
    selection = [int(value) for value in one(stdout, "RESEARCH_TREE_UI_SELECTION").split(",")]
    if len(selection) != 3 or selection[0] != 0 or selection[1] != tech or selection[2] <= 0 or \
       result.get("research_tree_selection_logs") != [",".join(map(str, selection))]:
        fail("ResearchTree selection does not match the active human and exact SDK research event")
    if lines(stdout, "RESEARCH_TREE_UI_HANDOFF_ROUTE") != ["OFFICIAL_OPEN_TT_BUTTON_DEFERRED_OWNER_NEW_VM"]:
        fail("Original TechPopup OpenTT handoff route is missing")
    handoff = [int(value) for value in one(stdout, "RESEARCH_TREE_UI_HANDOFF").split("|")]
    if len(handoff) != 3 or handoff[0] <= 0 or handoff[1:] != [67, -1] or \
       result.get("research_tree_handoff_logs") != ["|".join(map(str, handoff))]:
        fail("Official OpenTTButton handoff did not preserve [key,67,-1]")
    scroll = one(stdout, "RESEARCH_TREE_UI_HORIZONTAL_SCROLL").split("|")
    if len(scroll) != 5:
        fail("ResearchTree horizontal scroll marker has the wrong shape")
    scroll_key = int(scroll[0]); offsets = [float(v) for v in scroll[1:]]
    if scroll_key <= 0 or offsets[0] != 0 or offsets[1] != 240 or offsets[2] != 0 or offsets[3] < 240 or \
       not all(map(lambda value: value == value and abs(value) != float("inf"), offsets)) or \
       result.get("research_tree_scroll_logs") != ["|".join(scroll)]:
        fail("ResearchTree horizontal wheel did not move and restore the measured offset")
    input_rows = [[int(part) for part in row.split("|")] for row in lines(stdout, "RESEARCH_TREE_UI_INPUT")]
    expected_inputs = [
        [2, selection[2], 0, 1, 1, 1], [4, scroll_key, 240, 1, 1, 1],
        [4, scroll_key, -240, 1, 1, 1], [1, 27, 0, 1, 0, 0],
        [2, selection[2], 0, 0, 0, 0], [1, 27, 0, 0, 0, 0],
    ]
    if input_rows != expected_inputs:
        fail("ResearchTree input trace differs from selection, horizontal wheel, Escape and stale rejection contract")
    if result.get("research_tree_selection_logs") != [",".join(map(str, selection))] or \
       result.get("research_tree_handoff_logs") != ["|".join(map(str, handoff))] or \
       result.get("research_tree_scroll_logs") != ["|".join(scroll)]:
        fail("Runner result JSON does not preserve the exact research-tree callback evidence")

    sessions = [Path(one(stdout, marker)).resolve() for marker in
                ("SESSION_DIRECTORY", "FOUND_CITY_RESTORE_SESSION_DIRECTORY", "CITY_DECISION_RESTORE_SESSION_DIRECTORY")]
    if len(set(sessions)) != 3 or any(not path.is_relative_to(runtime / "sessions") for path in sessions):
        fail("Initial, restored UI and turn-one sessions are not distinct private sessions")
    ui_session = sessions[1]
    # The chooser closes in the restored session root; the TechTree is a new
    # retained VM in its own child directory and starts its own sequence at 1.
    chooser_shown = generated_file(result, ui_session / "ui-popup-1-shown.json", runtime)
    chooser_closed = generated_file(result, ui_session / "ui-popup-1-closed.json", runtime)
    tree_dir = ui_session / "research-tree"
    tree_phases = ("shown", "frame-1", "updated-2", "updated-3", "updated-4", "closed")
    docs = {}
    for phase in tree_phases:
        path = generated_file(result, tree_dir / f"ui-popup-1-{phase}.json", runtime)
        docs[phase] = json.loads(path.read_text(encoding="utf-8"))
    chooser = json.loads(chooser_shown.read_text(encoding="utf-8"))
    chooser_end = json.loads(chooser_closed.read_text(encoding="utf-8"))
    chooser_targets = chooser.get("inputTargets", [])
    open_rows = [row for row in chooser_targets if isinstance(row, dict) and row.get("id") == "OpenTTButton" and row.get("event") == "LeftClick"]
    if len(open_rows) != 1 or open_rows[0].get("key") != handoff[0] or \
       chooser.get("contextName") != "TechPopup" or chooser.get("popupKind") != "Research" or \
       chooser.get("active") is not True or chooser.get("timerSemaphore") != 0 or \
       chooser_end.get("active") is not False or chooser_end.get("timerSemaphore") != 0 or \
       chooser_end.get("contextName") != "TechPopup":
        fail("Original TechPopup chooser snapshots do not show the exact retained OpenTTButton handoff")
    for phase, doc in docs.items():
        active = phase != "closed"
        if doc.get("contextName") != "TechTree" or doc.get("popupKind") != "ResearchTree" or \
           doc.get("timerSemaphore") != (1 if active else 0) or doc.get("active") is not active:
            fail(f"ResearchTree {phase} snapshot has incorrect popup context, active state or timer")
        if doc.get("presentationClock") != (0 if phase == "shown" else 0.25):
            fail(f"ResearchTree {phase} owner presentation clock differs")
        lifecycle = ["queued", "shown:67"]
        if phase == "closed":
            lifecycle += ["closed", "processed:67"]
        if doc.get("lifecycle") != lifecycle:
            fail(f"ResearchTree {phase} lifecycle differs from stock TechTree enum 67")
    if docs["shown"] == docs["frame-1"] or docs["updated-2"] == docs["frame-1"] or \
       docs["updated-3"] == docs["updated-2"] or docs["updated-4"] == docs["updated-3"] or \
       docs["closed"] == docs["updated-4"]:
        fail("ResearchTree shown/frame/callback/scroll/reset/closed snapshots do not represent distinct states")
    tree_targets = docs["shown"].get("inputTargets", [])
    tech_rows = [row for row in tree_targets if isinstance(row, dict) and row.get("id") == "TechButton" and
                 row.get("key") == selection[2] and row.get("event") == "LeftClick" and
                 (row.get("void1"), row.get("void2")) == (tech, 0) and row.get("visible") is True and row.get("disabled") is False]
    if len(tech_rows) != 1:
        fail("Shown ResearchTree snapshot lacks exactly one visible matching normal TechButton row")
    for phase in ("updated-2", "updated-3", "updated-4"):
        matches = [row for row in docs[phase].get("inputTargets", []) if isinstance(row, dict) and
                   row.get("id") == "TechButton" and row.get("key") == selection[2] and
                   row.get("event") == "LeftClick" and (row.get("void1"), row.get("void2")) == (tech, 0)]
        if len(matches) != 1:
            fail(f"ResearchTree {phase} snapshot lost the selected technology callback row")
    measured_ranges = {}
    for phase, expected_offset in (("shown", 0), ("updated-3", 240), ("updated-4", 0)):
        rows = [row for row in docs[phase].get("scrollTargets", []) if isinstance(row, dict) and
                row.get("key") == scroll_key and row.get("event") == "Scroll"]
        if len(rows) != 1:
            fail(f"ResearchTree {phase} snapshot lacks the exact retained horizontal ScrollPanel")
        row = rows[0]
        if row.get("orientation") != "horizontal" or row.get("scrollX") != expected_offset or \
           not isinstance(row.get("maximumScroll"), (int, float)) or row["maximumScroll"] < 240 or \
           row.get("contentWidth", 0) - row.get("viewportWidth", 0) != row.get("maximumScroll"):
            fail(f"ResearchTree {phase} snapshot range/offset differs from its measured horizontal panel")
        measured_ranges[phase] = row["maximumScroll"]
    if len(set(measured_ranges.values())) != 1:
        fail("ResearchTree measured horizontal maximum changed while scrolling")
    if docs["closed"].get("inputTargets") != []:
        fail("Closed ResearchTree snapshot retains stale left-click targets")
    before = int_row(one(stdout, "CITY_DECISION_BEFORE_TURN"), 12, "pre-turn city/research observation")
    after = int_row(one(stdout, "CITY_DECISION_AFTER_TURN"), 12, "post-turn city/research observation")
    restored = [int_row(value, 12, "restored city/research row") for value in lines(stdout, "CITY_DECISION_RESTORED")]
    if len(restored) != 4 or restored != [after] * 4 or before[:3] != [0, 0, 0] or \
       before[4] != 1 or before[5] != tech or before[6] != 1 or before[7] != 0 or \
       after[:3] != [1, 1, 0] or after[4:7] != before[4:7] or after[7] <= before[7] or \
       after[8] != before[8] or after[9] <= before[9] or after[10] >= before[10]:
        fail("ResearchTree selection, normal turn progress or fresh restore observations differ")
    for name, prefix in (("city_decision_before_turn_logs", "CITY_DECISION_BEFORE_TURN"),
                         ("city_decision_after_turn_logs", "CITY_DECISION_AFTER_TURN"),
                         ("city_decision_restored_logs", "CITY_DECISION_RESTORED")):
        if result.get(name) != lines(stdout, prefix):
            fail(f"Runner JSON does not preserve {name}")
    baseline_index = json.loads((PROJECT / "evidence/city_decisions/conformance.json").read_text(encoding="utf-8"))
    check_artifacts(baseline_index)
    baseline = json.loads(Path(baseline_index["path"]).read_text(encoding="utf-8")); check_artifacts(baseline)
    if baseline.get("status") != "ISOLATED_SDK_CITY_DECISIONS_TURN_AND_NATIVE_RESTORE_PAIR_PASS":
        fail("Validated same-language native city-decision API baseline is missing")
    base_run = next((row for row in baseline.get("runs", []) if row.get("language") == lang), None)
    if not base_run or base_run.get("decision_before") != before or base_run.get("decision_after_turn") != after:
        fail("ResearchTree turn/city observations differ from same-language API route baseline")

    # Retain strict native archive + serialized SDK state/idle evidence.
    checkpoints = [Path(value).resolve() for value in lines(stdout, "NATIVE_CHECKPOINT_WRITTEN")]
    expected_cp = [(sessions[0] / "checkpoint-turn-0.zssave").resolve(),
                   (ui_session / "checkpoint-turn-1.zssave").resolve()]
    if checkpoints != expected_cp:
        fail("Native checkpoint paths differ from initial and turn-one ResearchTree sessions")
    rules = [row for row in request.get("inputs", []) if Path(row.get("path", "")).name == "rules.db"]
    locs = [row for row in request.get("inputs", []) if Path(row.get("path", "")).name == "localization.db"]
    bundles = [row for row in request.get("inputs", []) if Path(row.get("path", "")).name == "bundle.manifest"]
    if (len(rules), len(locs), len(bundles)) != (1, 1, 1):
        fail("ResearchTree request lacks unique rules/localization/bundle inputs")
    cp0 = generated_file(result, expected_cp[0], runtime)
    restore0 = generated_file(result, ui_session / "state-after-found-city-restore.zssave", runtime)
    cp1 = generated_file(result, expected_cp[1], runtime)
    restore1 = generated_file(result, sessions[2] / "state-after-city-decision-restore.zssave", runtime)
    localization = Path(locs[0]["path"]); bundle = Path(bundles[0]["path"])
    restore_proof = [
        verify_game_restore(cp0, restore0, rules=sessions[0] / "rules.db", localization=localization, language=lang, turn=0),
        verify_game_restore(cp1, restore1, rules=ui_session / "rules.db", localization=localization, language=lang, turn=1),
    ]
    inspect_save(cp0, bundle, sessions[0] / "Civ5SavedGameDatabase.db", expected=(1,0,0,0,0,64,64,133))
    inspect_save(restore0, bundle, ui_session / "Civ5SavedGameDatabase.db", expected=(1,0,0,0,0,64,64,133))
    inspect_save(cp1, bundle, ui_session / "Civ5SavedGameDatabase.db", expected=(1,0,1,1,0,64,64,133))
    inspect_save(restore1, bundle, sessions[2] / "Civ5SavedGameDatabase.db", expected=(1,0,1,1,0,64,64,133))
    founding_state = generated_file(result, sessions[0] / "state-after-founded-city.txt", runtime).read_bytes()
    founding_restore = generated_file(result, ui_session / "state-after-found-city-restore.txt", runtime).read_bytes()
    founding_idle = generated_file(result, ui_session / "state-after-found-city-idle.txt", runtime).read_bytes()
    if founding_state != founding_restore or founding_state != founding_idle:
        fail("Turn-zero fresh restore or three idle updates changed the founding state")
    before_save = generated_file(result, ui_session / "state-before-save.txt", runtime).read_bytes()
    turn_state = generated_file(result, ui_session / "state-after-city-decision-turn.txt", runtime).read_bytes()
    restored_state = generated_file(result, sessions[2] / "state-after-city-decision-restore.txt", runtime).read_bytes()
    idle_state = generated_file(result, sessions[2] / "state-after-city-decision-idle.txt", runtime).read_bytes()
    if turn_state != before_save or turn_state != restored_state or turn_state != idle_state:
        fail("Turn-one serialized SDK state changed before save, after fresh restore, or across idle updates")
    archive_count = lines(stdout, "CITY_DECISION_RESTORE_SECTIONS_EQUAL")
    if len(archive_count) != 1 or archive_count[0].split(",")[-1] != "133":
        fail("Native archive restore did not preserve all 133 sections in both sessions")
    state_semantics, _ = inspect_state_snapshot(sessions[2] / "state-after-city-decision-restore.txt", 1)
    return {
        "run_id": run_id, "language": lang, "status": result["status"], "pid": result["pid"],
        "selection": selection, "handoff": handoff, "horizontal_scroll": [scroll_key, *offsets],
        "decision_before": before, "decision_after_turn": after, "restored_observations": restored,
        "decision_semantics": _decision_snapshot_semantics(turn_state, before, after),
        "restore_state": state_semantics, "archive_restore_proof": restore_proof,
        "host_provenance": provenance, "tree_snapshots": {p: str(tree_dir / f"ui-popup-1-{p}.json") for p in tree_phases},
        "small_ui_assets_setting": provenance["small_ui_assets_setting"],
        "normal_callback_exactly_once_verified": True, "horizontal_scroll_and_escape_verified": True,
        "turn_and_native_restore_verified": True, "window_or_human_input_verified": False,
        "free_steal_shift_future_queue_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True)
    args = parser.parse_args()
    if len(args.run) != 2 or len(set(args.run)) != 2:
        parser.error("Provide exactly one distinct en_US and one ko_KR ResearchTree run")
    proof, frozen, hashes = freeze_inputs()
    try:
        rows = [verify_run(run_id) for run_id in args.run]
        if {row["language"] for row in rows} != LANGUAGES:
            fail("Provide one successful actual SDK ResearchTree run per language")
        en, ko = (next(row for row in rows if row["language"] == language) for language in ("en_US", "ko_KR"))
        for key in ("selection", "handoff", "horizontal_scroll", "decision_before", "decision_after_turn",
                    "restored_observations", "decision_semantics", "small_ui_assets_setting"):
            if en.get(key) != ko.get(key):
                fail(f"EN/KO ResearchTree semantic observation differs: {key}")
        for key in ("host_executable_sha256", "gamecore_sha256", "shared_lua_sha256"):
            if en["host_provenance"][key] != ko["host_provenance"][key]:
                fail(f"EN/KO runs did not use identical {key}")
        if en["host_provenance"]["ui_settings_sha256"] != ko["host_provenance"]["ui_settings_sha256"]:
            fail("EN/KO runs did not use identical frozen UI settings")
        after = {path: digest(Path(path)) for path in hashes}
        if after != hashes or any(digest(Path(row["path"])) != row["sha256"] for row in frozen):
            fail("Verifier/source inputs changed while validating the pair")
        report = {
            "status": "ISOLATED_SDK_OFFICIAL_RESEARCH_TREE_UI_TURN_AND_NATIVE_RESTORE_PAIR_PASS",
            "scope": "ACTUAL_SDK_BNW_TECHTREE_OPEN_TT_HANDOFF_NORMAL_RESEARCH_HORIZONTAL_SCROLL_ESCAPE_TURN_RESTORE_EN_KO",
            "runs": rows, "language_pair": ["en_US", "ko_KR"], "source_freeze_verified": True,
            "frozen_inputs": frozen, "source_hashes_before": hashes, "source_hashes_after": after,
            "proof_directory": str(proof), "research_tree_ui_verified": True,
            "original_open_tt_handoff_verified": True, "official_normal_research_callback_exactly_once_verified": True,
            "horizontal_scroll_positive_motion_verified": True, "escape_close_and_stale_input_rejection_verified": True,
            "turn_advance_verified": True, "fresh_native_restore_and_three_idle_updates_verified": True,
            "window_verified": False, "human_input_verified": False, "future_queue_verified": False,
            "free_tech_or_steal_verified": False, "shift_queue_verified": False,
            "retail_ui_equivalence_verified": False, "renderer_verified": False,
            "retail_save_compatibility_verified": False, "accepted_stage_promoted": False,
            "limitations": [
                "This is direct owner-thread Lua input through the official retained TechTree controls; no HWND or human input was tested.",
                "Only the normal local research tuple is supported; free research, theft, Shift queue, and future-tech queue behavior are outside this proof.",
                "The proof covers horizontal retained scroll and popup lifecycle for this fixture, not full renderer or retail visual equivalence.",
                "Save evidence verifies the private native archive and semantic SDK restore path; retail save compatibility is not claimed.",
            ],
        }
    except Exception as exc:
        report = {"status": "FAIL_CITY_RESEARCH_TREE_UI_CONFORMANCE", "run_ids": args.run,
                  "proof_directory": str(proof), "frozen_inputs": frozen,
                  "failure": f"{type(exc).__name__}: {exc}", "research_tree_ui_verified": False,
                  "window_verified": False, "human_input_verified": False,
                  "retail_ui_equivalence_verified": False, "renderer_verified": False}
        out = proof / "conformance.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "proof": artifact(out), "failure": report["failure"]}, ensure_ascii=False), file=sys.stderr)
        raise
    out = proof / "conformance.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "proof": artifact(out),
                      "runs": [{"run_id": row["run_id"], "language": row["language"],
                                "selection": row["selection"], "horizontal_scroll": row["horizontal_scroll"]}
                               for row in rows]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
