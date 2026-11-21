"""Independently verify an actual-SDK official TechPopup selection/turn/restore pair."""
from __future__ import annotations
import argparse
import configparser
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_city_decision_probe import (
    _decision_snapshot_semantics, fail, inspect_state_snapshot, int_row, lines, one,
    recorded, verify_game_restore,
)
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts
from ui_window_frame import verify_frame, verify_closed_frame

ROOT = PROJECT / "evidence/city_research_ui"
LANGUAGES = {"en_US", "ko_KR"}
REQUIRED_HOST = {
    "HostMain.cpp", "HostRun.h", "HostServices.h", "LocalGameCommands.h",
    "LocalSdkSession.h", "FoundCityProbe.h", "CityDecisionProbe.h",
    "UiPopupContext.h", "UiInputDispatch.h", "UiPopupAssets.generated.h",
}
VALIDATOR_INPUTS = (
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


def fail_if(value: bool, message: str) -> None:
    if value:
        fail(message)


def cpp_bytes(data: bytes) -> str:
    return "\n".join('"' + "".join(f"\\x{b:02x}" for b in data[i:i+64]) + '"'
                     for i in range(0, len(data), 64))


def freeze_validator():
    folder = ROOT / "validators" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12])
    folder.mkdir(parents=True, exist_ok=False)
    files, hashes = [], {}
    for source in VALIDATOR_INPUTS:
        if not source.is_file():
            fail(f"Missing Research UI provenance input: {source}")
        before = digest(source)
        target = folder / source.name
        shutil.copy2(source, target)
        row = artifact(target)
        if row["sha256"] != before:
            fail(f"Frozen verifier/source differs: {source}")
        files.append({"original_path": str(source), **row})
        hashes[str(source)] = before
    return folder, files, hashes


def source_provenance(request: dict) -> dict:
    reports = {}
    for key in ("candidate_build", "shared_lua_build", "found_value_shared_sdk_build"):
        row = request.get(key)
        if not isinstance(row, dict):
            fail(f"Research request lacks {key} source provenance")
        check_artifacts(row)
        reports[key] = json.loads(Path(row["path"]).read_text(encoding="utf-8"))
    build, shared, found = (reports[k] for k in
                            ("candidate_build", "shared_lua_build", "found_value_shared_sdk_build"))
    if found.get("status") != "FOUND_VALUE_SHARED_SDK_CANDIDATE_LINKED" or \
       found.get("gamecore", {}).get("sha256") != "a58a0d20cbaecad13ea248fe362d0c15bb97096802b9f60c5ef5f0dd8bb90c07":
        fail("Run did not use the designated a58 shared-found-values GameCore")
    if shared.get("status") != "SHARED_LUA_RUNTIME_CANDIDATE_BUILT":
        fail("Run did not pin the shared Lua runtime")
    src = {Path(row.get("path", "")).name: row for row in build.get("sources", [])}
    if not REQUIRED_HOST <= src.keys():
        fail("Frozen Host source closure omits a required Research UI file")
    for name in REQUIRED_HOST:
        check_artifacts(src[name])
    text = {name: Path(src[name]["path"]).read_text(encoding="utf-8") for name in REQUIRED_HOST}
    joined = "\n".join(text.values())
    required = (
        "--check-city-research-ui-window", "checkResearchWindow", "checkResearchUi",
        "ChooseResearchTechnology()", "BUTTONPOPUP_CHOOSETECH", "UiPopupKind::Research",
        'std::strcmp(operation,"sendResearch")==0', "Only normal local research selection is supported",
        "Research requires the active owned TechPopup", "ResearchCommandGuard", '"TechPopup"',
        "RESEARCH_UI_INPUT_ROUTE=OFFICIAL_BNW_TECH_POPUP_RETAINED_BUTTON_SDK_RECEIVER",
        "Research frame clock changed gameplay state", "researchAlreadyChosen?0:1",
        "std::count(events.begin(),events.end(),research)-std::count(previous.begin(),previous.end(),research)!=1",
        "RESEARCH_UI_LOCAL_EVENT=%s",
    )
    for token in required:
        if token not in joined:
            fail(f"Frozen Host route omits required Research contract: {token}")
    header = text["UiPopupAssets.generated.h"]
    guard = (PROJECT / "Source/Host/ResearchCommandGuard.lua").read_bytes()
    scene = (PROJECT / "Source/Host/UiScene.lua").read_bytes()
    input_lua = (PROJECT / "Source/Presentation/UiPresentationInput.lua").read_bytes()
    if cpp_bytes(guard) not in header or cpp_bytes(scene + b"\n" + input_lua) not in header or \
       "ResearchCommandGuard" not in header or "TechPopup" not in header:
        fail("Frozen generated UI header does not byte-embed the current guard/scene/official TechPopup sources")
    inputs = {Path(row.get("path", "")).name: row for row in request.get("inputs", [])}
    for name in ("ZeroSisHost_x64.exe", "CvGameCoreDLL_Expansion2_x64.dll",
                 "ZeroSisLua51_x64.dll", "rules.db", "localization.db", "bundle.manifest"):
        if name not in inputs:
            fail(f"Private Research runtime omits {name}")
        check_artifacts(inputs[name])
    if inputs["ZeroSisHost_x64.exe"]["sha256"] != build.get("executable", {}).get("sha256") or \
       inputs["ZeroSisLua51_x64.dll"]["sha256"] != shared.get("lua_dll", {}).get("sha256") or \
       inputs["CvGameCoreDLL_Expansion2_x64.dll"]["sha256"] != found["gamecore"]["sha256"]:
        fail("Private Host/GameCore/Lua hashes differ from the frozen build reports")
    if request.get("shared_found_value_sdk_enabled") is not True or \
       request.get("research_ui_enabled") is not True or request.get("research_window_requested") is not True:
        fail("Request did not enable the selected Research UI/window modes")
    settings = request.get("ui_settings_source")
    if not isinstance(settings, dict) or not all(isinstance(settings.get(k), str)
                                                  for k in ("original_source", "path", "sha256")):
        fail("Request lacks frozen UserSettings source/hash provenance")
    setting_path = Path(settings["path"]).resolve(strict=True)
    runtime_path = Path(request.get("cwd", "")).resolve(strict=True)
    expected_original = Path(r"C:\Users\home\OneDrive\Documents\My Games\Sid Meier's Civilization 5\UserSettings.ini")
    if Path(settings["original_source"]).resolve(strict=True) != expected_original.resolve(strict=True) or \
       setting_path != (runtime_path / "UserSettings.frozen.ini").resolve(strict=True):
        fail("Research UI settings do not originate from the requested user INI and exact private frozen copy")
    frozen_bytes = setting_path.stat().st_size
    if digest(setting_path) != settings["sha256"] or \
       ("bytes" in settings and settings["bytes"] != frozen_bytes):
        fail("Frozen UserSettings source hash or byte count differs")
    frozen_ini = configparser.ConfigParser(interpolation=None, strict=True)
    frozen_ini.read_string(setting_path.read_text(encoding="utf-8-sig"))
    try:
        small_setting_text = frozen_ini["InterfaceSettings"]["SmallUIAssets"].strip()
    except KeyError:
        fail("Frozen user INI lacks InterfaceSettings.SmallUIAssets")
    if small_setting_text not in ("0", "1"):
        fail("Frozen user INI SmallUIAssets is not an explicit 0/1 setting")
    small = request.get("small_ui_assets_setting")
    if type(small) is not bool or (small_setting_text == "1") is not small or \
       type(request.get("small_ui_assets_environment_removed")) is not bool or \
       request.get("auto_ui_assets_effective_retail_setting_verified") is not False:
        fail("SmallUIAssets frozen INI/value or effective-retail boundary differs")
    popup = text["UiPopupContext.h"]
    if 'std::getenv("ZEROSIS_UI_SMALL_ASSETS")' not in popup or \
       "smallUiAssets_=small[0]=='1'" not in popup or "lua_pushboolean(state,self.smallUiAssets_)" not in popup:
        fail("Native Research context does not bind the explicit SmallUIAssets value")
    return {
        **reports, "host_sources": {n: src[n] for n in sorted(REQUIRED_HOST)},
        "gamecore_sha256": found["gamecore"]["sha256"],
        "host_executable_sha256": inputs["ZeroSisHost_x64.exe"]["sha256"],
        "shared_lua_sha256": inputs["ZeroSisLua51_x64.dll"]["sha256"],
        "small_ui_assets_setting": small, "ui_settings_source": settings,
        "ui_settings_sha256": digest(setting_path), "ui_settings_bytes": frozen_bytes,
    }


def recorded_exact(result: dict, path: Path, runtime: Path) -> Path:
    path = path.resolve(strict=True)
    if not path.is_relative_to(runtime.resolve() / "sessions"):
        fail("SDK session artifact escaped the private runtime sessions directory")
    rows = [row for row in result.get("generated_files", [])
            if Path(row.get("path", "")).resolve() == path]
    if len(rows) != 1:
        fail(f"Expected one immutable generated artifact record for {path.name}")
    check_artifacts(rows[0])
    return path


def read_doc(row: dict) -> dict:
    check_artifacts(row)
    return json.loads(Path(row["path"]).read_text(encoding="utf-8"))


def find_key(node, key):
    if isinstance(node, dict):
        if node.get("key") == key:
            return node
        for value in node.values():
            found = find_key(value, key)
            if found is not None:
                return found
    elif isinstance(node, list):
        for value in node:
            found = find_key(value, key)
            if found is not None:
                return found
    return None


def verify_window(result: dict, request: dict, output: str, session: Path, selection: list[int]) -> dict:
    if request.get("research_window_requested") is not True or result.get("research_window_enabled") is not True or \
       result.get("native_tech_hit_dispatch_verified") is not True:
        fail("Native Research-window mode/TechButton hit dispatch flag is missing")
    report_row = result.get("ui_window_report")
    if not isinstance(report_row, dict):
        fail("Research run lacks its owned UI window report")
    report = read_doc(report_row)
    if report.get("status") != "LIVE_SDK_RESEARCH_WINDOW_POSTED_INPUT_PASS" or \
       report.get("scope") != "actual_live_SDK_research_VM_and_owned_GPU_HWND_selected_tech_hit_and_closed_refresh" or \
       report.get("research_fixture_enabled") is not True or report.get("production_fixture_enabled") is not False or \
       report.get("display_resize_enabled") is not True or report.get("refresh_closed_enabled") is not True or \
       report.get("pid") != result["pid"] or report.get("returncode") != 0 or report.get("timed_out") is not False or \
       report.get("error") is not None or report.get("real_user_click_verified") is not False or \
       report.get("installed_game_launched") is not False:
        fail("Research driver report does not match the exact owned-child posted-input scope")
    scenes, closed_rows, windows, frames = (report.get(k, []) for k in
                                             ("scenes", "refresh_scenes", "windows", "frames"))
    if (len(scenes), len(closed_rows), len(windows), len(frames)) != (1, 1, 1, 3):
        fail("Research window needs one TechPopup, one closed scene, one HWND and three GPU frames")
    scene, closed, window = scenes[0], closed_rows[0], windows[0]
    if scene.get("sequence") != 1 or scene.get("turn") != 0 or \
       Path(scene["snapshot"]["path"]).resolve() != session / "ui-popup-1-window.json" or \
       Path(closed["snapshot"]["path"]).resolve() != session / "ui-popup-1-closed.json":
        fail("Research window snapshots escaped the actual turn-zero restore session")
    shown = read_doc(scene["snapshot"])
    closed_doc = read_doc(closed["snapshot"])
    for snapshot, active in ((shown, True), (closed_doc, False)):
        if snapshot.get("contextName") != "TechPopup" or snapshot.get("popupKind") != "Research" or \
           snapshot.get("timerSemaphore") != 0 or snapshot.get("active") is not active:
            fail("Research shown/closed native snapshot has the wrong context lifecycle")
    manifest, closed_manifest = read_doc(scene["manifest"]), read_doc(closed["manifest"])
    if manifest.get("context") != "research" or manifest.get("context_name") != "TechPopup" or \
       manifest.get("snapshot_state_unchanged") is not True or \
       manifest.get("snapshot", {}).get("sha256") != scene["snapshot"]["sha256"] or \
       closed_manifest.get("context") != "research" or closed_manifest.get("closed_context_not_drawn") is not True or \
       closed_manifest.get("hit_regions") != [] or closed_manifest.get("sprite_count") != 0 or \
       closed_manifest.get("texture_count") != 0:
        fail("Research scene manifests do not bind the shown and empty closed context")
    key, x0, y0, x1, y1 = window.get("selected_hit", [None] * 5)
    expected_control = {"key": key, "player_id": 0, "tech_id": selection[1]}
    hit_rows = [hit for hit in manifest.get("hit_regions", []) if hit and hit[0] == key]
    targets = shown.get("inputTargets")
    callback_rows = [row for row in targets if isinstance(row, dict) and row.get("key") == key and \
                     row.get("event") == "LeftClick"] \
        if isinstance(targets, list) else []
    button = find_key(shown.get("tree"), key)
    if selection[0] != 0 or window.get("selected_control") != expected_control or \
       hit_rows != [[key, x0, y0, x1, y1]] or not (0 <= x0 < x1 <= 1920 and 0 <= y0 < y1 <= 1080) or \
       not isinstance(button, dict) or button.get("kind") != "Button" or len(callback_rows) != 1 or \
       callback_rows[0].get("id") != "TechButton" or callback_rows[0].get("event") != "LeftClick" or \
       callback_rows[0].get("visible") is not True or callback_rows[0].get("disabled") is not False or \
       (callback_rows[0].get("void1"), callback_rows[0].get("void2")) != (selection[1], 0):
        fail("Posted hit does not match one visible legal TechButton with exact (tech,0) callback payload")
    if window.get("input_policy") != "Actual selected technology hit then late Escape" or \
       window.get("synthetic_messages_posted") is not True:
        fail("Research driver did not post its bounded selected-technology HWND input")
    logical = window.get("posted_click_logical", [])
    if len(logical) != 2 or not (x0 <= logical[0] < x1 and y0 <= logical[1] < y1):
        fail("Posted logical point escaped the selected TechButton hit region")
    client = window.get("client", [])
    posted_client = window.get("posted_click_client", [])
    if len(client) != 2 or len(posted_client) != 2 or min(client) <= 0:
        fail("Research posted client point or owned client dimensions are missing")
    width, height = client
    scale = min(width / 1920.0, height / 1080.0)
    mapped_x = (posted_client[0] - (width - 1920.0 * scale) / 2.0) / scale
    mapped_y = (posted_client[1] - (height - 1080.0 * scale) / 2.0) / scale
    if abs(logical[0] - mapped_x) > 1e-8 or abs(logical[1] - mapped_y) > 1e-8 or \
       not (0 <= posted_client[0] < width and 0 <= posted_client[1] < height) or \
       not (x0 <= mapped_x < x1 and y0 <= mapped_y < y1):
        fail("Posted research client point does not map into its exact selected TechButton hit")
    top_hit = next((hit for hit in reversed(manifest.get("hit_regions", []))
                    if len(hit) == 5 and hit[1] <= mapped_x < hit[3] and hit[2] <= mapped_y < hit[4]), None)
    if top_hit != [key, x0, y0, x1, y1]:
        fail("Posted research coordinate is covered by a different topmost active control")
    hwnd, tid = window.get("hwnd"), window.get("owner_thread")
    if window.get("sequence") != 1 or window.get("pid") != result["pid"] or \
       window.get("accepted") != 1 or window.get("refresh_accepted") != 0 or \
       window.get("delivered") != 2 or window.get("completed") is not True or \
       window.get("refresh_delivered") != 1 or window.get("scene_generation_before") != 1 or \
       window.get("scene_generation_after") != 2 or \
       window.get("refresh_completed") is not True or \
       window.get("refresh_device_identity_before", 0) <= 0 or \
       window.get("refresh_device_identity_before") != window.get("refresh_device_identity_after"):
        fail("Research callback/closed refresh changed HWND, GPU device identity, or scene generation")
    phases = {}
    for frame in frames:
        phase = frame.get("phase")
        if phase not in ("initial", "resized", "closed") or phase in phases or \
           frame.get("sequence") != 1 or frame.get("pid") != result["pid"] or \
           (frame.get("hwnd"), frame.get("owner_thread")) != (hwnd, tid) or \
           frame.get("native_visible") is not True or frame.get("desktop_pixels_verified") is not False or \
           frame.get("client") != ([1000, 700] if phase == "initial" else [900, 600]):
            fail("Research GPU frame escaped the same visible owned HWND/thread/client")
        source = closed if phase == "closed" else scene
        checker = verify_closed_frame if phase == "closed" else verify_frame
        parity = checker(Path(source["png"]["path"]), Path(frame["png"]["path"]), *frame["client"])
        if parity != frame.get("pixel_check"):
            fail("Research GPU frame parity differs from an independent bitmap recomputation")
        phases[phase] = frame
    for earlier, later in (("initial", "resized"), ("resized", "closed")):
        if phases[later]["device_kind"] != phases[earlier]["device_kind"] or \
           phases[later]["render_count"] <= phases[earlier]["render_count"] or \
           phases[later]["present_count"] <= phases[earlier]["present_count"]:
            fail("Research resize/closed scene refresh lost device-kind or frame counter continuity")
    if result.get("gpu_frame_bitmap_parity_verified") is not True:
        fail("Runner did not retain its narrow GPU frame bitmap-parity result")
    if set(phases) != {"initial", "resized", "closed"} or \
       lines(output, "UI_WINDOW_EXPECTED_CONTROL") != [f"1|{key}|0|{selection[1]}"] or \
       lines(output, "UI_WINDOW_STATE_UNCHANGED") != ["1|before-input"] or \
       lines(output, "UI_WINDOW_COMPLETE") != ["1|2|1|owner-thread"] or \
       lines(output, "UI_WINDOW_REFRESH_COMPLETE") != ["1|1|0|2|owner-thread"]:
        fail("Research HWND/GPU/scene-generation lifecycle markers differ")
    input_rows = [list(map(int, row.split("|"))) for row in lines(output, "UI_WINDOW_INPUT")]
    if len(input_rows) != 3 or any(len(row) != 10 or row[0] != 1 or row[4] != row[5] or \
                             row[6:9] != [0, 0, 0] or row[9] != tid for row in input_rows) or \
       input_rows[0][1:4] != [2, key, 1] or input_rows[1][1:4] != [1, 27, 0] or \
       input_rows[2][1:4] != [1, 27, 0]:
        fail("Research window input did not record one TechButton hit and reject both late Escape inputs")
    return {"driver_report": artifact(Path(report_row["path"])),
            "selected_control": expected_control, "selected_hit": window["selected_hit"],
            "hwnd": hwnd, "owner_thread": tid, "same_hwnd_device_closed_refresh_verified": True,
            "three_gpu_frames_and_bitmap_parity_verified": True,
            "native_tech_hit_verified": True, "late_and_closed_input_rejected": True,
            "human_input_verified": False, "retail_pixel_equivalence_verified": False}


def verify_run(run_id: str) -> dict:
    if not re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", run_id):
        fail("Research run ID has an invalid immutable identity format")
    folder = ROOT / run_id
    result_path, request_path = folder / "result.json", folder / "request.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    request = json.loads(request_path.read_text(encoding="utf-8"))
    check_artifacts(result); check_artifacts(request)
    for key, expected in (("request", request_path), ("stdout", folder / "stdout.log"),
                          ("stderr", folder / "stderr.log"), ("ui_window_report", folder / "ui_window.json")):
        row = result.get(key)
        if not isinstance(row, dict):
            fail(f"Research result omits {key} artifact")
        check_artifacts(row)
        if Path(row["path"]).resolve() != expected.resolve() or not expected.is_file():
            fail(f"Research {key} escaped its exact run directory")
    lang = request.get("language")
    if request.get("run_id") != run_id or lang not in LANGUAGES or \
       result.get("status") != "ISOLATED_SDK_OFFICIAL_RESEARCH_UI_TURN_AND_NATIVE_RESTORE_PASS":
        fail("Run is not a successful exact-language official TechPopup SDK execution")
    flags = ("exit_code", "pid", "timed_out", "host_failures", "official_research_ui_enabled",
             "research_window_enabled", "research_ui_verified", "official_research_callback_verified",
             "native_tech_hit_dispatch_verified", "turn_advance_verified")
    if any(key not in result for key in flags):
        fail("Research result lacks required process/callback/turn/restore flags")
    if result["exit_code"] != 0 or type(result["pid"]) is not int or result["pid"] <= 0 or \
       result["timed_out"] is not False or result["host_failures"] != [] or \
       any(result[key] is not True for key in flags[4:]):
        fail("Research process, callback, turn or native restore did not pass cleanly")
    for key in ("free_tech_or_steal_verified", "right_click_or_pedia_verified",
                "retail_save_compatibility_verified", "accepted_stage_promoted"):
        if key not in result or result[key] is not False:
            fail(f"Research result overstates unsupported scope: {key}")
    if result.get("renderer_verified") is not False or result.get("interactive_input_verified") is not False:
        fail("Runner overstates full renderer or human-interactive verification")
    runtime = (PROJECT / "Build/CityResearchUiRuntime" / run_id).resolve()
    if Path(request.get("cwd", "")).resolve() != runtime or \
       request.get("command", [None])[1:] != ["--check-city-research-ui-window", lang] or \
       request.get("research_ui_enabled") is not True or request.get("research_window_requested") is not True:
        fail("Research command, window-implies-UI flags, or private runtime path differs")
    output = (folder / "stdout.log").read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    stderr = (folder / "stderr.log").read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    expected_stderr = [f"UI_WINDOW_PROCESS_START={result['pid']}"]
    if any("HOST_FAILURE:" in line or "HOST_NATIVE_EXCEPTION" in line for line in stderr.splitlines()) or \
       stderr.splitlines() != expected_stderr:
        fail("Research stderr must contain only the HostMain PID marker for this exact child")
    provenance = source_provenance(request)
    if one(output, "RESEARCH_UI_SMALL_ASSETS") != ("1" if provenance["small_ui_assets_setting"] else "0"):
        fail("Native UI did not emit the request's exact frozen SmallUIAssets setting")
    for marker in (
        "RESEARCH_UI_INPUT_ROUTE=OFFICIAL_BNW_TECH_POPUP_RETAINED_BUTTON_SDK_RECEIVER",
        "RESEARCH_UI_TIMER_SEMAPHORE=0", "RESEARCH_UI_OWNER_CLOCK=0,0.25",
        "RESEARCH_UI_FRAME_GAMEPLAY_STATE_EQUAL=true",
        "CITY_DECISION_INPUT_ROUTE=SDK_CITY_PUSH_ORDER_AND_OFFICIAL_RESEARCH_UI",
        "FOUND_CITY_CONTINUED_TURN_VERIFIED=true", "FOUND_CITY_RESTORE_FRESH_SESSION=true",
        "FOUND_CITY_RESTORE_STATE_EQUAL=true", "FOUND_CITY_RESTORE_IDLE_STATE_EQUAL=true",
        "FOUND_CITY_RESTORE_IDLE_UPDATES=3", "CITY_DECISION_RESTORE_FRESH_SESSION=true",
        "CITY_DECISION_RESTORE_STATE_EQUAL=true", "CITY_DECISION_RESTORE_IDLE_STATE_EQUAL=true",
        "CITY_DECISION_RESTORE_IDLE_UPDATES=3", "CITY_DECISION_RESTORED_CORE_MODULE_UNLOADED=true",
        "RESEARCH_UI_SHUTDOWN_PASS ORIGINAL_POPUP_CALLBACK=true SDK_RECEIVER=true TURN_AND_NATIVE_RESTORE=true RETAIL_UI_EQUIVALENCE=false",
    ):
        if output.splitlines().count(marker) != 1:
            fail(f"Research runtime lacks a unique expected lifecycle marker: {marker}")
    rng = one(output, "RESEARCH_UI_FRAME_SYNC_RNG")
    if not re.fullmatch(r"\d+\|\d+", rng) or rng.split("|")[0] != rng.split("|")[1]:
        fail("Synchronous RNG seed changed across the Research frame capture")
    if one(output, "UI_POPUP_CONTEXT") != "OFFICIAL_BNW_RESEARCH_PERSISTENT_VM_RETAINED_CONTROLS" or \
       one(output, "UI_POPUP_CONTEXT_CLOSED") != "1" or \
       one(output, "RESEARCH_UI_WINDOW_ROUTE") != "OWNED_HWND_HIT_OFFICIAL_TECH_SELECTED_SDK_RECEIVER":
        fail("Research popup lifecycle or owned-window route differs")
    legal = int_row(one(output, "RESEARCH_UI_LEGAL_CHOICE"), 3, "legal Research choice")
    selected = int_row(one(output, "RESEARCH_UI_SELECTION"), 3, "selected Research choice")
    if legal != selected or selected[0] != 0 or selected[1] < 0 or selected[2] <= 0:
        fail("Official TechSelected did not select its live legal active-player TechButton")
    event = f"local-research:{selected[1]}:0:-1:0"
    if lines(output, "RESEARCH_UI_LOCAL_EVENT") != [event] or \
       result.get("research_ui_selection_logs") != [",".join(map(str, selected))]:
        fail("Actual Host did not retain exactly one original normal research event/selection")
    phases = {}
    for phase in ("shown", "frame-1", "window", "closed"):
        fields = one(output, "UI_POPUP_" + phase).split(",")
        if len(fields) != 3 or fields[:2] != ["1", "0"] or not fields[2].isdigit():
            fail(f"Research {phase} snapshot marker has an invalid sequence/turn/size")
        phases[phase] = int(fields[2])
    sessions = [Path(one(output, marker)).resolve() for marker in
                ("SESSION_DIRECTORY", "FOUND_CITY_RESTORE_SESSION_DIRECTORY",
                 "CITY_DECISION_RESTORE_SESSION_DIRECTORY")]
    if len(set(sessions)) != 3 or any(not p.is_relative_to(runtime / "sessions") for p in sessions):
        fail("Initial, turn-zero restore, and turn-one restore sessions are not distinct/private")
    ui_session = sessions[1]
    snap_paths = {phase: ui_session / f"ui-popup-1-{phase}.json" for phase in phases}
    snap_docs = {}
    for phase, path in snap_paths.items():
        recorded_exact(result, path, runtime)
        if path.stat().st_size != phases[phase]:
            fail(f"Research {phase} native snapshot byte count differs")
        snapshot = json.loads(path.read_text(encoding="utf-8"))
        if snapshot.get("contextName") != "TechPopup" or snapshot.get("popupKind") != "Research" or \
           snapshot.get("timerSemaphore") != 0 or snapshot.get("active") is not (phase != "closed"):
            fail(f"Research {phase} snapshot context/timer/lifecycle differs")
        if snapshot.get("presentationClock") != (0 if phase == "shown" else 0.25):
            fail(f"Research {phase} owner presentation clock differs")
        expected_lifecycle = ["queued", "shown:11"]
        if phase == "closed":
            expected_lifecycle += ["context-hidden:TechPopup", "processed:11"]
        if snapshot.get("lifecycle") != expected_lifecycle:
            fail(f"Research {phase} lifecycle does not preserve the stock CHOOSETECH enum and close sequence")
        snap_docs[phase] = snapshot
    if snap_docs["shown"] == snap_docs["frame-1"] or snap_docs["frame-1"] != snap_docs["window"] or \
       snap_docs["closed"] == snap_docs["shown"]:
        fail("Research shown/frame/window/closed snapshots do not preserve the expected sequence")
    for phase in ("shown", "frame-1", "window"):
        targets = snap_docs[phase].get("inputTargets")
        matches = [row for row in targets if isinstance(row, dict) and row.get("id") == "TechButton" and
                   row.get("event") == "LeftClick" and
                   (row.get("void1"), row.get("void2")) == (selected[1], 0)] if isinstance(targets, list) else []
        if len(matches) != 1:
            fail(f"Research {phase} snapshot lacks its exact legal TechButton payload")
    before = int_row(one(output, "CITY_DECISION_BEFORE_TURN"), 12, "pre-turn city/research row")
    after = int_row(one(output, "CITY_DECISION_AFTER_TURN"), 12, "post-turn city/research row")
    restored = [int_row(value, 12, "restored city/research row") for value in lines(output, "CITY_DECISION_RESTORED")]
    if len(restored) != 4 or restored != [after] * 4 or before[:3] != [0, 0, 0] or \
       before[4] != 1 or before[5] != selected[1] or before[6] != 1 or before[7] != 0 or \
       after[:3] != [1, 1, 0] or after[4:7] != before[4:7] or after[7] <= before[7] or \
       after[8] != before[8] or after[9] <= before[9] or after[10] >= before[10]:
        fail("Research UI choice, one-item city order or normal turn progress differs")
    for key, value in (("city_decision_before_turn_logs", lines(output, "CITY_DECISION_BEFORE_TURN")),
                       ("city_decision_after_turn_logs", lines(output, "CITY_DECISION_AFTER_TURN")),
                       ("city_decision_restored_logs", lines(output, "CITY_DECISION_RESTORED"))):
        if result.get(key) != value:
            fail(f"Runner JSON does not retain exact {key}")
    index = PROJECT / "evidence/city_decisions/conformance.json"
    index_doc = json.loads(index.read_text(encoding="utf-8")); check_artifacts(index_doc)
    api = json.loads(Path(index_doc["path"]).read_text(encoding="utf-8")); check_artifacts(api)
    if api.get("status") != "ISOLATED_SDK_CITY_DECISIONS_TURN_AND_NATIVE_RESTORE_PAIR_PASS":
        fail("Actual SDK city-decision API baseline is not a validated pair")
    baseline = {row.get("language"): row for row in api.get("runs", [])}.get(lang)
    if not baseline or baseline.get("decision_before") != before or baseline.get("decision_after_turn") != after:
        fail("Research UI city-order/turn rows differ from the same-language API route baseline")
    ui_proof = verify_window(result, request, output, ui_session, selected)
    checks = [(sessions[0] / "state-after-founded-city.txt", ui_session / "state-after-found-city-restore.txt"),
              (sessions[0] / "state-after-founded-city.txt", ui_session / "state-after-found-city-idle.txt")]
    for left, right in checks:
        if recorded_exact(result, left, runtime).read_bytes() != recorded_exact(result, right, runtime).read_bytes():
            fail("Turn-zero fresh restore or three idle updates changed the founding state")
    checkpoints = [Path(value).resolve() for value in lines(output, "NATIVE_CHECKPOINT_WRITTEN")]
    expected_cp = [(sessions[0] / "checkpoint-turn-0.zssave").resolve(),
                   (ui_session / "checkpoint-turn-1.zssave").resolve()]
    if checkpoints != expected_cp:
        fail("Native checkpoint paths differ from the initial and post-turn Research sessions")
    rules = [row for row in request["inputs"] if Path(row["path"]).name == "rules.db"]
    locs = [row for row in request["inputs"] if Path(row["path"]).name == "localization.db"]
    bundles = [row for row in request["inputs"] if Path(row["path"]).name == "bundle.manifest"]
    if (len(rules), len(locs), len(bundles)) != (1, 1, 1):
        fail("Research request lacks unique rules/localization/bundle inputs")
    cp0 = recorded_exact(result, expected_cp[0], runtime)
    restore0 = recorded_exact(result, ui_session / "state-after-found-city-restore.zssave", runtime)
    cp1 = recorded_exact(result, expected_cp[1], runtime)
    restore1 = recorded_exact(result, sessions[2] / "state-after-city-decision-restore.zssave", runtime)
    localization = Path(locs[0]["path"]); bundle = Path(bundles[0]["path"])
    archive_proof = [
        verify_game_restore(cp0, restore0, rules=sessions[0] / "rules.db", localization=localization,
                            language=lang, turn=0),
        verify_game_restore(cp1, restore1, rules=ui_session / "rules.db", localization=localization,
                            language=lang, turn=1),
    ]
    inspect_save(cp0, bundle, sessions[0] / "Civ5SavedGameDatabase.db", expected=(1,0,0,0,0,64,64,133))
    inspect_save(restore0, bundle, ui_session / "Civ5SavedGameDatabase.db", expected=(1,0,0,0,0,64,64,133))
    inspect_save(cp1, bundle, ui_session / "Civ5SavedGameDatabase.db", expected=(1,0,1,1,0,64,64,133))
    inspect_save(restore1, bundle, sessions[2] / "Civ5SavedGameDatabase.db", expected=(1,0,1,1,0,64,64,133))
    turn_state = recorded_exact(result, ui_session / "state-after-city-decision-turn.txt", runtime).read_bytes()
    before_save = recorded_exact(result, ui_session / "state-before-save.txt", runtime).read_bytes()
    restored1 = recorded_exact(result, sessions[2] / "state-after-city-decision-restore.txt", runtime).read_bytes()
    idle1 = recorded_exact(result, sessions[2] / "state-after-city-decision-idle.txt", runtime).read_bytes()
    if turn_state != before_save or turn_state != restored1 or turn_state != idle1:
        fail("Turn-one state changed before save, after fresh restore or during three idle updates")
    state, _ = inspect_state_snapshot(sessions[2] / "state-after-city-decision-restore.txt", 1)
    return {
        "run_id": run_id, "language": lang, "status": result["status"], "pid": result["pid"],
        "selection": selected, "research_event": event, "decision_before": before, "decision_after_turn": after,
        "restored_observations": restored, "decision_semantics": _decision_snapshot_semantics(turn_state, before, after),
        "restore_state": state, "archive_restore_proof": archive_proof, "window_proof": ui_proof,
        "host_provenance": provenance, "small_ui_assets_setting": provenance["small_ui_assets_setting"],
        "frame_sync_rng_seed_unchanged": rng, "official_callback_exactly_once_verified": True,
        "narrow_gpu_frame_bitmap_parity_verified": True,
        "api_route_city_decision_equal": True, "turn_advance_and_native_restore_verified": True,
        "free_tech_or_steal_verified": False, "right_click_or_pedia_verified": False,
        "human_input_verified": False, "retail_ui_equivalence_verified": False,
        "retail_save_compatibility_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", required=True)
    args = parser.parse_args()
    if len(args.run) != 2 or len(set(args.run)) != 2:
        parser.error("Provide exactly one distinct en_US and one ko_KR run")
    proof, frozen, hashes = freeze_validator()
    try:
        rows = [verify_run(run_id) for run_id in args.run]
        if {row["language"] for row in rows} != LANGUAGES:
            fail("Provide one successful actual SDK Research UI run per language")
        en, ko = (next(row for row in rows if row["language"] == lang) for lang in ("en_US", "ko_KR"))
        for key in ("selection", "research_event", "decision_before", "decision_after_turn",
                    "restored_observations", "decision_semantics", "small_ui_assets_setting"):
            if en[key] != ko[key]:
                fail(f"EN/KO Research UI semantic observation differs: {key}")
        for key in ("host_executable_sha256", "gamecore_sha256", "shared_lua_sha256"):
            if en["host_provenance"][key] != ko["host_provenance"][key]:
                fail(f"EN/KO run did not use identical {key}")
        if en["host_provenance"]["ui_settings_sha256"] != ko["host_provenance"]["ui_settings_sha256"]:
            fail("EN/KO run did not use identical frozen UI settings")
        after = {path: digest(Path(path)) for path in hashes}
        if after != hashes or any(digest(Path(row["path"])) != row["sha256"] for row in frozen):
            fail("Verifier/provenance inputs changed during inspection")
        report = {
            "status": "ISOLATED_SDK_OFFICIAL_RESEARCH_UI_TURN_AND_NATIVE_RESTORE_PAIR_PASS",
            "scope": "ACTUAL_SDK_BNW_TECHPOPUP_NORMAL_RESEARCH_HIT_TURN_NATIVE_RESTORE_EN_KO",
            "runs": rows, "language_pair": ["en_US", "ko_KR"],
            "same_host_gamecore_and_shared_lua": True, "source_freeze_verified": True,
            "frozen_sources": frozen, "source_hashes_before": hashes, "source_hashes_after": after,
            "proof_directory": str(proof), "research_ui_verified": True,
            "official_normal_research_callback_exactly_once_verified": True,
            "research_window_selected_tech_hit_verified": True,
            "same_hwnd_device_and_three_gpu_frames_verified": True,
            "narrow_gpu_frame_bitmap_parity_verified": True,
            "api_route_city_decision_equal": True, "turn_advance_verified": True,
            "fresh_native_restore_and_three_idle_updates_verified": True,
            "ui_frame_gameplay_state_unchanged": True,
            "ui_frame_sync_rng_seed_unchanged": True,
            "small_ui_assets_requested_setting_match_verified": True,
            "small_ui_assets_effective_retail_setting_verified": False,
            "free_tech_or_steal_verified": False, "right_click_or_pedia_verified": False,
            "ui_pixels_verified": False, "human_input_verified": False,
            "retail_ui_equivalence_verified": False, "retail_save_compatibility_verified": False,
            "accepted_stage_promoted": False,
            "limitations": [
                "Only the stock normal TechSelected callback is verified.",
                "Free research, technology theft, right-click and Pedia behavior are not verified.",
                "GPU bitmap parity covers these retained popup frames only; it does not prove retail UI pixels or human input.",
                "SmallUIAssets proves the requested frozen setting, not the effective retail setting.",
                "The RNG check covers synchronous seed equality across the frame only.",
            ],
        }
    except Exception as exc:
        report = {"status": "FAIL_CITY_RESEARCH_UI_CONFORMANCE", "run_ids": args.run,
                  "proof_directory": str(proof), "frozen_sources": frozen,
                  "failure": f"{type(exc).__name__}: {exc}", "research_ui_verified": False,
                  "ui_pixels_verified": False, "human_input_verified": False,
                  "retail_ui_equivalence_verified": False, "retail_save_compatibility_verified": False}
        out = proof / "conformance.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "proof": artifact(out),
                          "failure": report["failure"]}, ensure_ascii=False), file=sys.stderr)
        raise
    out = proof / "conformance.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "proof": artifact(out),
                      "runs": [{"run_id": row["run_id"], "language": row["language"],
                                "selection": row["selection"]} for row in rows]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"CITY_RESEARCH_UI_CONFORMANCE_FAILED: {exc}", file=sys.stderr)
        raise
