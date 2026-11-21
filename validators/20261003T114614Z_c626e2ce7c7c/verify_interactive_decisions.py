"""Independently verify continuous original production/research UI decisions."""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts
import verify_interactive_game as base

EVIDENCE = PROJECT / "evidence/interactive_game"
RUNTIME = PROJECT / "Build/InteractiveGameRuntime"
RUN_ID = re.compile(r"\d{8}T\d{6}Z_[0-9a-f]{12}")


def require(ok: bool, why: str) -> None:
    if not ok:
        raise RuntimeError(why)


def exact_artifact(ref: dict, expected: Path, label: str) -> Path:
    check_artifacts(ref)
    actual = Path(ref["path"]).resolve(strict=True)
    require(actual == expected.resolve(strict=True), f"{label} escaped its expected evidence path")
    return actual


def text_artifact(ref: dict, expected: Path, label: str) -> str:
    return exact_artifact(ref, expected, label).read_text(encoding="utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")


def rows(text: str, marker: str, pattern: str) -> list[tuple[str, ...]]:
    found = re.findall(pattern, text, re.M)
    require(bool(found) or marker not in text, f"Malformed {marker} records")
    return found


def read_run(run_id: str) -> tuple[dict, dict, str, str, dict, Path, Path]:
    require(RUN_ID.fullmatch(run_id) is not None, "Invalid immutable run ID")
    ev = EVIDENCE / run_id
    reqp, resp = ev / "request.json", ev / "result.json"
    request, result = json.loads(reqp.read_text(encoding="utf-8")), json.loads(resp.read_text(encoding="utf-8"))
    require(request.get("run_id") == run_id and result.get("run_id") == run_id, "Run identity differs from evidence directory")
    check_artifacts(request); check_artifacts(result)
    exact_artifact(result.get("request"), reqp, "request")
    stdout = text_artifact(result.get("stdout"), ev / "stdout.log", "stdout")
    stderr = text_artifact(result.get("stderr"), ev / "stderr.log", "stderr")
    attempt = json.loads(exact_artifact(result.get("attempt"), ev / "attempt.json", "process attempt").read_text(encoding="utf-8"))
    runtime = Path(request.get("cwd", "")).resolve(strict=True)
    require(runtime == (RUNTIME / run_id).resolve(strict=True), "Run cwd is not its private runtime")
    status = result.get("status")
    accepted = {"CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_SMOKE_PASS",
                "CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_RESTORE_SMOKE_PASS"}
    require(status in accepted and result.get("returncode") == 0 and result.get("timed_out") is False and
            result.get("runtime_inputs_unchanged") is True and result.get("decision_ui_smoke_requested") is True and
            result.get("stage_or_mods_changed") is False and attempt.get("status") == "FINISHED" and
            attempt.get("returncode") == 0 and attempt.get("timed_out") is False and attempt.get("pid") == result.get("driver_pid"),
            "Host/driver did not finish a clean decision-UI smoke with unchanged runtime inputs")
    require(not re.search(r"HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|SCRIPT_FAILURE|INTERACTIVE_INPUT_REJECTED", stdout + "\n" + stderr),
            "Host or native-input failure marker is present")
    require(request.get("input_profile") == "POSTED_HWND_CONTINUOUS_DECISION_UI_LOOP" and request.get("smoke") is True and
            request.get("decisions") is True and request.get("stage_or_mods_changed") is False,
            "Request does not describe the isolated decision-UI profile")
    return request, result, stdout, stderr, attempt, runtime, ev


def provenance(request: dict, result: dict, runtime: Path) -> dict:
    # Reuse the independently established frozen provider-chain checker. Its last
    # profile assertion is for the predecessor world-only profile, so adapt only
    # that input field while retaining every hash/source/runtime check.
    adjusted = dict(request, input_profile="POSTED_HWND_CONTINUOUS_GAME_LOOP")
    proof = base.verify_provenance(adjusted, result, runtime)
    source = dict(proof["compiled_source_rows"])
    build_doc = json.loads(Path(request["provenance"]["host_build"]["path"]).read_text(encoding="utf-8"))
    for row in build_doc.get("sources", []):
        name = Path(row.get("path", "")).name
        if name in {"InteractiveUiSession.h", "UiPopupContext.h", "HostServices.h"}:
            check_artifacts(row)
            source[name] = row
    required_tokens = {
        "InteractiveGameLoop.h": ("INTERACTIVE_DECISION_SMOKE_COMPLETE=1", "DispatchUi(input)",
                                   "INTERACTIVE_DECISION_PRODUCTION_TARGET", "INTERACTIVE_DECISION_RESEARCH_TARGET"),
        "InteractiveUiSession.h": ("BUTTONPOPUP_CHOOSEPRODUCTION", "BUTTONPOPUP_CHOOSETECH", "CaptureFrame", "VerifySnapshot"),
        "UiPopupContext.h": ("DispatchExternalWindowInput", "SnapshotForExternalScene", "TakeDeferredPopup"),
        "LocalSdkSession.h": ("ResponseCityPushOrder", "ResponseResearch"),
        "InteractiveGameSession.h": ("DecisionState", "CurrentResearch", "ProductionUnit"),
        "WorldViewRenderer.cpp": ("0x5a57000000000000ull", "2ull<<32", "4ull<<32"),
    }
    for name, tokens in required_tokens.items():
        require(name in source, f"Frozen Host closure omits {name}")
        body = Path(source[name]["path"]).read_text(encoding="utf-8")
        require(all(token in body for token in tokens), f"Frozen Host source lacks decision/UI dispatch contract in {name}")
    popup = Path(source["UiPopupContext.h"]["path"]).read_text(encoding="utf-8")
    require("ChooseProductionUnit" in popup and "ChooseResearchTechnology" in popup,
            "Sealed popup source omits fixture methods required to distinguish them from the live UI path")
    return proof


def generated_files(result: dict, runtime: Path) -> tuple[dict[str, Path], list[dict]]:
    listed = result.get("generated_files")
    require(type(listed) is list, "Result lacks generated-file inventory")
    paths: list[Path] = []
    by_name: dict[str, Path] = {}
    for row in listed:
        check_artifacts(row)
        path = Path(row["path"]).resolve(strict=True)
        require(path.is_relative_to((runtime / "sessions").resolve(strict=True)), "Generated artifact escaped this private session")
        paths.append(path)
        key = path.name if path.name not in by_name else str(path.relative_to((runtime / "sessions").resolve(strict=True)))
        require(key not in by_name, "Generated session artifact identity is duplicated")
        by_name[key] = path
    actual = sorted(path.resolve() for path in (runtime / "sessions").rglob("*") if path.is_file())
    require(sorted(paths) == actual and len(paths) == len(set(paths)), "Generated inventory does not exactly cover the session files")
    return by_name, listed


def sdk_snapshot(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    parsed: dict[str, list[list[str]]] = {"G": [], "P": [], "C": [], "U": []}
    for line in raw.splitlines():
        fields = line.split("|")
        if fields[0] in parsed:
            parsed[fields[0]].append(fields)
    require(len(parsed["G"]) == 1 and len(parsed["G"][0]) == 5, f"Malformed SDK game-state snapshot: {path.name}")
    require(len(parsed["P"]) == 64 and all(len(row) == 11 for row in parsed["P"]), f"Malformed SDK player snapshot: {path.name}")
    require(all(len(row) == 12 for row in parsed["C"]) and all(len(row) == 13 for row in parsed["U"]),
            f"Malformed SDK city/unit snapshot: {path.name}")
    return {"path": path, "bytes": raw, "rows": parsed}


def verify_decision_snapshot(snapshot: dict, *, turn: int, active: int, city: int, unit: int, tech: int) -> None:
    rows_by_type = snapshot["rows"]
    game = rows_by_type["G"][0]
    require(int(game[1]) == turn and int(game[3]) == active, "SDK semantic snapshot has a different turn/active player")
    players = [row for row in rows_by_type["P"] if int(row[1]) == active]
    cities = [row for row in rows_by_type["C"] if int(row[1]) == active and int(row[2]) == city]
    units = [row for row in rows_by_type["U"] if int(row[1]) == active and int(row[2]) == unit]
    require(len(players) == len(cities) == len(units) == 1 and int(players[0][10]) == tech and
            int(cities[0][8]) == unit, "SDK semantic snapshot lacks the selected city production/research state")


def ui_snapshots(driver: dict, by_name: dict[str, Path], request_rows: list[tuple[str, ...]], frame_rows: list[tuple[str, ...]], output: str) -> list[dict]:
    scene_requests = driver.get("scene_requests")
    require(type(scene_requests) is list and len(scene_requests) >= 2, "UI driver did not service at least two original popup scenes")
    contexts = [row.get("context") for row in scene_requests if type(row) is dict]
    require("production" in contexts and "research" in contexts, "Driver omitted original Production or Tech popup")
    require(len(request_rows) == len(scene_requests), "Native scene requests and driver-prepared requests differ")
    require(len(frame_rows) == len(scene_requests), "Native popup frames do not pair one-to-one with requests")
    snapshots = []
    for seq, (driver_row, request_row, frame_row) in enumerate(zip(scene_requests, request_rows, frame_rows), 1):
        ctx, snap, folder = request_row[1], Path(request_row[2]).resolve(strict=True), Path(request_row[3]).resolve(strict=True)
        require(int(request_row[0]) == seq and driver_row.get("sequence") == seq and driver_row.get("context") == ctx,
                "Native and driver popup sequence/context differ")
        require(ctx in ("production", "research"), "Unexpected popup context in decision smoke")
        require(snap.name == f"play-ui-{seq}.json" and snap.parent.parent.name == "sessions" and
                folder.parent == snap.parent and folder.is_dir(), "Popup snapshot/prepared scene escaped its run session")
        snap_doc = json.loads(snap.read_text(encoding="utf-8"))
        context_name, kind = ("ProductionPopup", "Production") if ctx == "production" else ("TechPopup", "Research")
        require(snap_doc.get("contextName") == context_name and snap_doc.get("popupKind") == kind and snap_doc.get("active") is True,
                "Popup snapshot is not the active original SDK context")
        targets = snap_doc.get("inputTargets")
        require(type(targets) is list and targets, "Original popup snapshot has no retained callback targets")
        target_map = {}
        for target in targets:
            require(type(target) is dict and type(target.get("key")) is int and target["key"] > 0 and
                    target.get("event") in ("LeftClick", "RightClick") and
                    target.get("visible") is True and target.get("disabled") is False,
                    "Popup snapshot target is not a visible original callback")
            target_map.setdefault(target["key"], []).append(target)
        packet = folder / "scene.packet"
        manifest_path = folder / "scene_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_snapshot = manifest.get("snapshot", {})
        packet_ref = manifest.get("packet", {})
        require(manifest.get("context") == ctx and manifest_snapshot.get("sha256") == digest(snap) and
                manifest.get("snapshot_state_unchanged") is True and manifest.get("closed_context_not_drawn") is False,
                "Prepared packet manifest is not tied to the exact active snapshot")
        require(manifest.get("packet_version") == "ZSUPIX02" and manifest.get("retained_input_targets") == targets,
                "Prepared packet manifest does not preserve the exact callback payload rows")
        require(type(manifest.get("hit_regions")) is list,
                "Prepared UI manifest has no compiled retained hit map")
        require(Path(manifest_snapshot.get("path", "")).resolve(strict=True) == snap and
                packet.is_file() and Path(packet_ref.get("path", "")).resolve(strict=True) == packet and
                packet_ref.get("sha256") == digest(packet), "Prepared packet/source snapshot hash differs from its manifest")
        require(driver_row.get("snapshot_before_sha256") == digest(snap) and
                driver_row.get("snapshot_after_sha256") == digest(snap) and
                driver_row.get("snapshot_state_unchanged") is True and
                Path(driver_row.get("folder", "")).resolve(strict=True) == folder,
                "Driver snapshot/scene provenance differs from the immutable native capture")
        original_sources = []
        for source_row in manifest.get("original_context_sources", []):
            source_path = Path(source_row.get("path", ""))
            copies = [p for p in (folder / "source_ui").glob("*" + source_path.name) if p.is_file()]
            require(len(copies) == 1 and digest(copies[0]) == source_row.get("sha256"),
                    "Frozen original popup Lua/XML source copy differs from its context manifest")
            original_sources.append(artifact(copies[0]))
        generation, turn, frame_ctx, hwnd, device, frame_snapshot, frame_folder = frame_row
        require(int(frame_row[0]) == seq and int(generation) > 0 and int(turn) >= 0 and frame_ctx == ctx and
                int(hwnd) > 0 and int(device) > 0 and Path(frame_snapshot).resolve() == snap and Path(frame_folder).resolve() == folder,
                "Native popup frame does not identify its exact request/HWND/device")
        hit_key = None
        # The selected target is checked against the later target marker; preserve
        # the full retained payload rows in the proof for independent inspection.
        snapshots.append({"sequence": seq, "context": ctx, "snapshot": artifact(snap), "scene_folder": str(folder),
                          "packet": artifact(packet), "manifest": artifact(manifest_path), "targets": targets,
                          "hit_regions": manifest["hit_regions"],
                          "original_context_sources": original_sources,
                          "target_keys": sorted(target_map), "hwnd": int(hwnd), "device": int(device), "generation": int(generation), "turn": int(turn)})
    require(len({row["hwnd"] for row in snapshots}) == 1 and len({row["device"] for row in snapshots}) == 1,
            "Decision popups replaced the same owned HWND or GPU device")
    return snapshots


def verify_run(run_id: str, proof_dir: Path) -> dict:
    request, result, output, stderr, attempt, runtime, evidence = read_run(run_id)
    prov = provenance(request, result, runtime)
    driver_ref = result.get("interactive_ui_driver")
    require(type(driver_ref) is dict, "Result omits the actual scene-driver report")
    driver = json.loads(Path(driver_ref["path"]).read_text(encoding="utf-8"))
    check_artifacts(driver_ref)
    require(driver.get("status") == "INTERACTIVE_UI_DRIVER_PASS" and driver.get("returncode") == 0 and driver.get("error") is None,
            "UI scene driver did not complete all actual popup preparations")
    by_name, generated = generated_files(result, runtime)
    starts = rows(output, "INTERACTIVE_GAME_STARTED", r"^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$")
    targets_p = rows(output, "INTERACTIVE_DECISION_PRODUCTION_TARGET", r"^INTERACTIVE_DECISION_PRODUCTION_TARGET=(\d+)\|(\d+)\|(\d+)$")
    targets_r = rows(output, "INTERACTIVE_DECISION_RESEARCH_TARGET", r"^INTERACTIVE_DECISION_RESEARCH_TARGET=(\d+)\|(\d+)$")
    city_events = rows(output, "TURN_CYCLE_EVENT", r"^TURN_CYCLE_EVENT=(\d+)\|(local-city-order:\d+:\d+:\d+:[01]:[01]:[01])$")
    research_events = rows(output, "TURN_CYCLE_EVENT", r"^TURN_CYCLE_EVENT=(\d+)\|(local-research:\d+:0:-1:0)$")
    before = rows(output, "INTERACTIVE_DECISION_BEFORE_TURN", r"^INTERACTIVE_DECISION_BEFORE_TURN=((?:\d+,){11}\d+)$")
    after = rows(output, "INTERACTIVE_DECISION_AFTER_TURN", r"^INTERACTIVE_DECISION_AFTER_TURN=((?:\d+,){11}\d+)$")
    completed = re.findall(r"^INTERACTIVE_DECISION_SMOKE_COMPLETE=1$", output, re.M)
    next_turns = rows(output, "INTERACTIVE_NEXT_HUMAN_TURN", r"^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$")
    req_rows = rows(output, "INTERACTIVE_UI_SCENE_REQUEST", r"^INTERACTIVE_UI_SCENE_REQUEST=(\d+)\|([^|]+)\|([^|]+)\|([^|]+)$")
    frame_rows = rows(output, "INTERACTIVE_UI_FRAME", r"^INTERACTIVE_UI_FRAME=(\d+)\|(\d+)\|(\d+)\|([^|]+)\|(\d+)\|(\d+)\|([^|]+)\|([^|]+)$")
    inputs = rows(output, "INTERACTIVE_UI_NATIVE_INPUT", r"^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$")
    require(len(starts) == len(targets_p) == len(targets_r) == len(before) == len(after) == len(completed) == len(next_turns) == 1,
            "Decision callback, before/after observation, or next-turn markers are missing/duplicated")
    require("INTERACTIVE_GAME_SESSION_STOPPED=true" in output and "INTERACTIVE_UI_ROUTER_STOPPED=true" in output and
            "INTERACTIVE_PLAY_CLOSED=" in output and "INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true" in output,
            "UI router/session or GameCore did not shut down cleanly")
    start_turn, active, width, height = map(int, starts[0])
    city, unit, pkey = map(int, targets_p[0]); tech, rkey = map(int, targets_r[0])
    require(len(city_events) == len(research_events) == 1 and
            city_events[0][1] == f"local-city-order:{city}:0:{unit}:0:1:1" and
            research_events[0][1] == f"local-research:{tech}:0:-1:0",
            "Owner event log does not contain exactly the original production/research command tuples")
    b = tuple(map(int, before[0].split(","))); a = tuple(map(int, after[0].split(",")))
    next_turn, update_count = map(int, next_turns[0])
    require(len(b) == len(a) == 12 and b[0] == start_turn and a[0] == start_turn + 1 and
            b[2:6] == a[2:6] == (active, city, unit, tech),
            "Decision observations do not identify the exact same city/unit/technology")
    require(next_turn == start_turn + 1 and update_count > 0 and a[0] == next_turn and a[1] > b[1] and a[6] == 1 and
            a[7] > b[7] and a[8] == b[8] and a[9] > b[9] and a[10] < b[10],
            "Actual next turn did not advance production and research while preserving the selected orders")
    scenes, gpu = base.scene_maps(result, runtime)
    require(len(scenes) == len(result.get("frames", [])), "World scene and GPU frame inventories differ")
    device_set = set()
    for i, frame in enumerate(result["frames"], 1):
        doc = scenes[i][0]
        require(len(frame) == 9 and frame[0] == i and frame[1] == doc["generation"] and frame[2] == doc["turn"] and
                frame[4] == len(doc["hits"]) and frame[5] > 0 and frame[6] > 0,
                "World JSON and actual GPU frame metadata differ")
        device_set.add(frame[5]); base.verify_png(gpu[i])
    require(len(device_set) == 1, "World-scene refresh replaced the active GPU device")
    city_rows = [entry for doc, _ in scenes.values() for entry in doc.get("cities", [])
                 if isinstance(entry, dict) and entry.get("id") == city and entry.get("owner") == active]
    require(city_rows, "Chosen production city is absent from all actual world scene city records")
    ui = ui_snapshots(driver, by_name, req_rows, frame_rows, output)
    require(len([r for r in inputs if int(r[1]) == 1]) >= 2, "Original popup callback click inputs are missing")
    for marker, key, context in ((targets_p[0], pkey, "production"), (targets_r[0], rkey, "research")):
        snapshots = [s for s in ui if s["context"] == context]
        require(len(snapshots) == 1 and key in snapshots[0]["target_keys"], "Selected native key is absent from its original popup callback snapshot")
        selected_targets = [t for t in snapshots[0]["targets"] if t["key"] == key and t.get("event") == "LeftClick"]
        require(len(selected_targets) == 1, "Selected popup key does not resolve to exactly one original left-click callback")
        target = selected_targets[0]
        packet_hits = [h for h in snapshots[0]["hit_regions"] if isinstance(h, list) and len(h) == 5 and h[0] == key]
        require(len(packet_hits) == 1, "Selected callback key is absent or duplicated in the compiled popup packet hit manifest")
        clipped = target.get("clippedBounds")
        require(type(clipped) is dict and all(type(clipped.get(k)) in (int, float) for k in ("x", "y", "width", "height")),
                "Original popup callback snapshot lacks clipped logical bounds")
        expected_bounds = (clipped["x"], clipped["y"], clipped["x"] + clipped["width"], clipped["y"] + clipped["height"])
        require(all(math.isclose(float(actual), float(expected), rel_tol=0.0, abs_tol=1e-4)
                    for actual, expected in zip(packet_hits[0][1:], expected_bounds)),
                "Compiled packet hit rectangle differs from the exact retained callback clipping")
        scene_folder = Path(snapshots[0]["scene_folder"])
        lua_sources = [p for p in scene_folder.rglob("*.lua") if p.is_file()]
        lua_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in lua_sources)
        if context == "production":
            require(target.get("void1") == 6 and target.get("void2") == unit and city == int(marker[0]),
                    "Production target is not the selected original ORDER_TRAIN callback for the exact city/unit")
            require("local g_append = false" in lua_text and
                    "Game.CityPushOrder(city, eOrder, iData, false, not g_append, true)" in lua_text,
                    "Frozen original ProductionPopup callback does not preserve its replace-order tuple")
            original_tuple = {"api": "Game.CityPushOrder", "city": city, "order": "ORDER_TRAIN", "data": unit,
                              "order_id": 0, "alt": False, "shift": True, "control": True}
        else:
            require(target.get("id") == "TechButton" and target.get("void1") == tech and target.get("void2") == 0,
                    "Research target is not the normal exact-tech callback from the original TechPopup")
            require("Network.SendResearch(eTech, 0, iValue, false)" in lua_text,
                    "Frozen original TechPopup callback does not preserve normal research selection")
            original_tuple = {"api": "Network.SendResearch", "tech": tech, "discover": 0,
                              "steal_from": -1, "shift": False}
        if context == "production":
            pseq = snapshots[0]["sequence"]
            production_tuple = original_tuple
        else:
            rseq = snapshots[0]["sequence"]
            research_tuple = original_tuple
    # Native popup clicks are matched to their popup-frame generations and target keys.
    for seq in (pseq, rseq):
        frame = ui[seq - 1]
        chosen_key = pkey if seq == pseq else rkey
        require(any(int(row[0]) == frame["generation"] and int(row[2]) == chosen_key and int(row[3]) == 1 for row in inputs),
                "Consumed popup click is not bound to the callback key in that exact scene generation")
        same_generation = [(revision, doc) for revision, (doc, _) in scenes.items() if doc["generation"] == frame["generation"]]
        require(len(same_generation) == 1, "Popup generation does not identify one composed world scene")
        _, composed_scene = same_generation[0]
        require(sum(1 for h in composed_scene["hits"] if isinstance(h, list) and len(h) == 5 and h[0] == chosen_key) == 1,
                "Selected original popup callback is absent/duplicated in the composed scene hit map")
        world_frames = result.get("frames", [])
        matched_frame = [f for f in world_frames if len(f) == 9 and f[1] == frame["generation"]]
        require(len(matched_frame) == 1 and matched_frame[0][5] == frame["device"] and
                matched_frame[0][2] == frame["turn"] and composed_scene["generation"] == frame["generation"],
                "Popup and composed world capture do not share the same scene generation/device/turn")
        composed_png = Path(ui[seq - 1]["scene_folder"]) / "composed.png"
        require(composed_png.is_file(), "Original popup was not composed over the live world bitmap")
        composed_data = composed_png.read_bytes()
        require(composed_data[:8] == b"\x89PNG\r\n\x1a\n" and composed_data[12:16] == b"IHDR" and
                int.from_bytes(composed_data[16:20], "big") == 1920 and int.from_bytes(composed_data[20:24], "big") == 1080,
                "Composed original popup frame does not retain its 1920x1080 logical canvas")
    posted = rows(output, "INTERACTIVE_SMOKE_POSTED", r"^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$")
    world_inputs = rows(output, "INTERACTIVE_WINDOW_INPUT", r"^INTERACTIVE_WINDOW_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$")
    all_inputs = [(int(g), int(k), int(key), int(c), "world") for g, k, key, c in world_inputs if int(k) == 1]
    all_inputs += [(int(g), int(k), int(key), int(c), "popup") for g, k, key, c in inputs if int(k) == 1]
    require(len(posted) == len(all_inputs) and len(posted) >= 5, "Posted HWND coordinates and delivered world/popup input rows do not pair")
    posted_hits = []
    for (generation_s, key_s, x_s, y_s) in posted:
        generation, key, x, y = int(generation_s), int(key_s), int(x_s), int(y_s)
        matches_input = [row for row in all_inputs if row[0] == generation and row[2] == key and row[1] == 1 and row[3] == 1]
        require(len(matches_input) == 1, "Posted coordinate was not consumed exactly once as its generation-bound control click")
        matches = [doc for doc, _ in scenes.values() if doc["generation"] == generation]
        require(len(matches) == 1, "Posted generation does not map to one actual composed world scene")
        doc = matches[0]
        hits = [h for h in doc["hits"] if isinstance(h, list) and len(h) == 5 and h[0] == key]
        require(len(hits) == 1, "Posted world key is absent or duplicated in the frozen scene hit list")
        hx, hy = x * 1.5, y * 1.5
        require(hits[0][1] <= hx < hits[0][3] and hits[0][2] <= hy < hits[0][4],
                "Posted client coordinate falls outside its exact retained world hit region")
        posted_hits.append({"generation": generation, "key": key, "client": [x, y], "logical": [hx, hy],
                            "input_surface": matches_input[0][4]})
    require(len(re.findall(r"^INTERACTIVE_DECISION_PRODUCTION_TARGET=", output, re.M)) == 1 and
            len(re.findall(r"^INTERACTIVE_DECISION_RESEARCH_TARGET=", output, re.M)), "Original decision callbacks were not uniquely recorded")
    state_files = {}
    for name in ("play-decisions-selected-state.txt", "play-decisions-next-turn-state.txt"):
        matches = [p for p in by_name.values() if p.name == name]
        require(len(matches) == 1, f"Missing exact state snapshot {name}")
        state_files[name] = artifact(matches[0])
    final_matches = [p for p in by_name.values() if p.name == "play-final-state.txt"]
    require(len(final_matches) == 1, "Missing native final SDK semantic snapshot")
    state_files["play-final-state.txt"] = artifact(final_matches[0])
    selected_semantic = sdk_snapshot(Path(state_files["play-decisions-selected-state.txt"]["path"]))
    next_semantic = sdk_snapshot(Path(state_files["play-decisions-next-turn-state.txt"]["path"]))
    final_semantic = sdk_snapshot(Path(state_files["play-final-state.txt"]["path"]))
    verify_decision_snapshot(selected_semantic, turn=start_turn, active=active, city=city, unit=unit, tech=tech)
    verify_decision_snapshot(next_semantic, turn=next_turn, active=active, city=city, unit=unit, tech=tech)
    verify_decision_snapshot(final_semantic, turn=next_turn, active=active, city=city, unit=unit, tech=tech)
    require(next_semantic["bytes"] == final_semantic["bytes"], "Post-turn decision and final native state snapshots differ")
    saves = rows(output, "INTERACTIVE_NATIVE_SAVE", r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$")
    require(len(saves) >= 2 and int(saves[-1][0]) == next_turn, "Native saves do not include the final human-turn boundary")
    manifest_rows = [r for r in request.get("runtime_inputs", []) if Path(r.get("path", "")).name == "bundle.manifest"]
    require(len(manifest_rows) == 1, "Runtime does not identify exactly one sealed bundle manifest")
    manifest = Path(manifest_rows[0]["path"]).resolve(strict=True)
    archives = []
    for turn_s, save_s in saves:
        path = Path(save_s).resolve(strict=True)
        require(path.is_relative_to((runtime / "sessions").resolve(strict=True)) and by_name.get(path.name) == path,
                "Native save escaped generated session evidence")
        db = path.parent / "Civ5SavedGameDatabase.db"
        require(db.name in by_name and by_name[db.name] == db.resolve(strict=True), "Native save database is not recorded")
        archive = inspect_save(path, manifest, db,
                               expected=(1, 0, int(turn_s), (scenes[max(scenes)][0] if int(turn_s) == next_turn else scenes[1][0])["elapsed"], active, 64, 64, 133))
        require(archive.get("section_count") == 133 and archive.get("sdk_restore_verified") is False,
                "Private native save does not contain the expected 133-section SDK archive")
        archives.append(archive)
    require(re.search(r"^INTERACTIVE_UI_ROUTER_STOPPED=true$", output, re.M) and
            re.search(r"^INTERACTIVE_GAME_SESSION_STOPPED=true$", output, re.M), "Session-owned callbacks were not unbound")
    host_src = prov["compiled_source_rows"]
    local_src = Path(host_src["LocalSdkSession.h"]["path"]).read_text(encoding="utf-8")
    require("ResponseCityPushOrder(active,cityID,order,data,alt,shift,control)" in local_src and
            "ResponseResearch(active,tech,discover,shift)" in local_src and
            "Only normal local research selection is supported" in local_src,
            "Frozen Host receiver source does not preserve the guarded SDK city-order/research signatures")
    return {"run_id": run_id, "status": result["status"], "language": request.get("language"), "pid": result.get("pid"),
            "startup_turn": start_turn, "final_turn": next_turn, "active_player": active, "city": city, "unit": unit, "technology": tech,
            "production_before_after": [list(b), list(a)], "ui_scenes": ui, "world_scenes": len(scenes), "world_gpu_frames": len(gpu),
            "world_gpu_device": next(iter(device_set)), "native_popup_inputs": inputs, "native_archives": archives,
            "posted_world_hits": posted_hits,
            "decision_state_files": state_files, "source_provenance": prov,
            "original_command_tuples": {"production": production_tuple, "research": research_tuple},
            "original_production_and_research_callbacks_verified": True, "same_hwnd_and_device_verified": True,
            "actual_turn_progress_verified": True, "core_unload_verified": True,
            "human_input_verified": False, "retail_renderer_equivalence_verified": False, "full_gameplay_verified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--source-run")
    args = parser.parse_args()
    proof = PROJECT / "validators" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12])
    proof.mkdir(parents=True, exist_ok=False)
    script_copy = proof / "verify_interactive_decisions.py"
    shutil.copy2(Path(__file__).resolve(), script_copy)
    helper_copies = []
    for name in ("verify_interactive_game.py", "collect_baseline.py", "probe_world_builder.py",
                 "verify_first_turn_candidate.py", "verify_world_builder_map_object.py"):
        target = proof / "helpers" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(PROJECT / "tools" / name, target)
        helper_copies.append(artifact(target))
    try:
        row = verify_run(args.run, proof)
        source_row = None
        if args.source_run:
            source_request, source_result, source_out, _, _, source_runtime, _ = read_run(args.source_run)
            source_row = verify_run(args.source_run, proof)
            current_request, current_result, current_out, _, _, current_runtime, _ = read_run(args.run)
            require(args.source_run != args.run and source_request.get("language") == current_request.get("language"), "Restore pair identity/language mismatch")
            resume_from = current_request.get("resume_from")
            require((isinstance(resume_from, dict) and resume_from.get("run_id") == args.source_run) or
                    current_result.get("resume_from_run") == args.source_run,
                    "Restore request does not point to the selected source run")
            source_build = source_request.get("provenance", {}).get("host_build", {})
            current_build = current_request.get("provenance", {}).get("host_build", {})
            check_artifacts(source_build); check_artifacts(current_build)
            require(source_build.get("sha256") == current_build.get("sha256"),
                    "Checkpoint and restore use different sealed Host builds")
            source_inputs = {Path(r["path"]).name: r["sha256"] for r in source_request.get("runtime_inputs", [])}
            current_inputs = {Path(r["path"]).name: r["sha256"] for r in current_request.get("runtime_inputs", [])}
            require(source_inputs == current_inputs, "Checkpoint and restore do not use byte-identical Core/provider/runtime inputs")
            require(current_result.get("fresh_process_restore_verified") is True and current_result.get("semantic_restore_equal") is True and
                    current_result.get("checkpoint_input_unchanged") is True, "Fresh-process decision restore equality is not proven")
            require("INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=true" in current_out, "Restored state changed during idle startup")
            source_result_files = [Path(r["path"]).resolve(strict=True) for r in source_result.get("generated_files", [])
                                   if Path(r.get("path", "")).name == "play-final-state.txt"]
            current_result_files = [Path(r["path"]).resolve(strict=True) for r in current_result.get("generated_files", [])
                                    if Path(r.get("path", "")).name == "play-initial-state.txt"]
            require(len(source_result_files) == len(current_result_files) == 1 and
                    source_result_files[0].read_bytes() == current_result_files[0].read_bytes(),
                    "Fresh process initial semantic state does not byte-match the source run final state")
            row["source_run_id"] = args.source_run
            row["fresh_process_restore_verified"] = True
            row["source_and_restore_same_language"] = True
        else:
            row["fresh_process_restore_verified"] = False
        report = {"status": "CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_RESTORE_SMOKE_PASS" if args.source_run else
                  "CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_SMOKE_PASS",
                  "scope": "POSTED_HWND_ORIGINAL_CITY_PRODUCTION_AND_TECH_POPUP_CALLBACKS_ONE_TURN_NATIVE_SAVE_AND_CORE_UNLOAD",
                  "runs": [row], "independent_verifier": artifact(script_copy),
                  "frozen_helper_sources": helper_copies, "source_run_verified": source_row,
                  "source_provenance_verified": True, "original_ui_callback_payloads_verified": True,
                  "native_packet_manifest_scene_and_same_device_verified": True, "production_research_and_next_turn_verified": True,
                  "native_133_section_saves_verified": True, "fresh_process_restore_verified": bool(args.source_run),
                  "human_input_verified": False, "retail_renderer_equivalence_verified": False, "full_gameplay_verified": False,
                  "limitations": ["Popup and world inputs are synthetic messages posted to the owned HWND.",
                                  "The private strategic renderer does not establish Civ V retail renderer or full gameplay equivalence.",
                                  "The proof covers only original production/research callbacks and one normal turn."]}
        out = proof / "conformance.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except Exception as exc:
        report = {"status": "FAIL_INTERACTIVE_DECISION_UI_CONFORMANCE", "run_ids": [args.run] + ([args.source_run] if args.source_run else []),
                  "failure": f"{type(exc).__name__}: {exc}", "human_input_verified": False,
                  "retail_renderer_equivalence_verified": False, "full_gameplay_verified": False}
        out = proof / "conformance.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "proof": artifact(out), "failure": report["failure"]}, ensure_ascii=False), file=sys.stderr)
        raise
    print(json.dumps({"status": report["status"], "proof": artifact(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
