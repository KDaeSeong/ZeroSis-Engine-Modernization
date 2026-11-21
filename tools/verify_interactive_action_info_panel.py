"""Independently verify one immutable original ActionInfoPanel native run.

This is evidence validation only. It does not launch Civ V, alter a save, or
claim retail-pixel equivalence for the retained renderer.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from collect_baseline import PROJECT, digest
from action_info_panel_timeline import KEY_BASE, verify_action_info_panel_timeline
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts
from verify_interactive_trade_route import (
    RUN_ID, VerificationError, artifact_ref, compiled_build_source,
    generated_map, load_json, require, sdk_state_identity,
    trade_route_frame_manifest, unique_generated, verified_runtime_bundle,
    verify_frozen_support,
)

EVIDENCE = PROJECT / "evidence/interactive_game"
RUNTIMES = PROJECT / "Build/InteractiveGameRuntime"
HOST_SOURCES = (
    "InteractiveGameLoop.h", "InteractiveGameSession.h",
    "InteractiveUiSession.h", "UiPopupContext.h", "UiScene.lua",
)
ACTION_LUA = "Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.lua"
ACTION_XML = "Assets/DLC/Expansion2/UI/InGame/WorldView/ActionInfoPanel.xml"
FRAME = re.compile(r"^INTERACTIVE_ACTION_INFO_PANEL_FRAME=(\d+)\|(\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(\d+)\|([^|]+)\|(.+)$", re.M)
WORLD_FRAME = re.compile(r"^INTERACTIVE_WORLD_FRAME=(\d+)\|(\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|([01])\|(\d+)$", re.M)
COMMITTED = re.compile(r"^INTERACTIVE_GPU_SCENE_COMMITTED=(\d+)\|(\d+)$", re.M)
TARGET = re.compile(r"^INTERACTIVE_ACTION_INFO_SMOKE_TARGET=([^|]+)\|(-?\d+)\|(-?\d+)\|(\d+)\|(\d+)\|(-?\d+)$", re.M)
POST = re.compile(r"^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$", re.M)
BUTTON = re.compile(r"^INTERACTIVE_SMOKE_BUTTON=(\d+)\|(\d+)\|(\d+)\|(\d+)$", re.M)
SAVE = re.compile(r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$", re.M)
NEXT_TURN = re.compile(r"^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$", re.M)


def xml_tree_matches(xml_node: ET.Element, snapshot_node: object) -> bool:
    """Compare retained original control identity/tree while ignoring runtime values."""
    if not isinstance(snapshot_node, dict):
        return False
    if snapshot_node.get("kind") != xml_node.tag or snapshot_node.get("id") != xml_node.attrib.get("ID", ""):
        return False
    source_attrs = snapshot_node.get("sourceAttributes")
    if not isinstance(source_attrs, dict) or source_attrs != dict(xml_node.attrib):
        return False
    children = [child for child in xml_node if isinstance(child.tag, str)]
    captured = snapshot_node.get("children")
    return (isinstance(captured, list) and len(captured) == len(children) and
            all(xml_tree_matches(source, actual) for source, actual in zip(children, captured)))


def packet_hits(packet_path: Path) -> tuple[int, int, list[tuple[int, tuple[float, float, float, float]]]]:
    data = packet_path.read_bytes()
    require(len(data) >= 32 and data[:8] == b"ZSUPIX02", "ActionInfo packet is not the retained scene packet format")
    width, height, texture_count, sprite_count, hit_count, scroll_count = struct.unpack_from("<6I", data, 8)
    require((width, height) == (1920, 1080) and texture_count <= 64 and sprite_count <= 10000 and
            hit_count <= 10000 and scroll_count == 0, "ActionInfo packet dimensions or record counts are invalid")
    offset = 32
    for _ in range(texture_count):
        require(offset + 4 <= len(data), "Truncated ActionInfo texture path length")
        size = struct.unpack_from("<I", data, offset)[0]
        offset += 4
        require(0 < size < 4096 and offset + size <= len(data), "Invalid ActionInfo texture path")
        data[offset:offset + size].decode("utf-8")
        offset += size
    offset += sprite_count * struct.calcsize("<IQ16f")
    require(offset + hit_count * struct.calcsize("<Q4f") == len(data),
            "ActionInfo packet has truncated or trailing sprite/hit records")
    hits = []
    for _ in range(hit_count):
        key, x0, y0, x1, y1 = struct.unpack_from("<Q4f", data, offset)
        offset += struct.calcsize("<Q4f")
        hits.append((key, (x0, y0, x1, y1)))
    return texture_count, sprite_count, hits


def verify_original_asset_ref(ref: object, expected: str, label: str) -> Path:
    """Validate the frozen BNW source reference; byte length is optional in prepared.json."""
    path = artifact_ref(ref, label=f"prepared original {label}")
    require(path.as_posix().endswith(expected), f"Prepared original {label} is not at the canonical BNW path")
    require(isinstance(ref, dict) and isinstance(ref.get("sha256"), str) and
            re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]) is not None and
            digest(path) == ref["sha256"],
            f"Prepared original {label} does not match its pinned SHA-256")
    if "bytes" in ref:
        size = ref["bytes"]
        require(type(size) is int and size > 0 and path.stat().st_size == size,
                f"Prepared original {label} has an invalid or mismatched byte length")
    return path


def require_end_turn_targets(inputs: object, local_key: int) -> list[dict]:
    bounds = {"x": 1584, "y": 844, "width": 320, "height": 36}
    require(isinstance(inputs, list) and len(inputs) == 2 and
            all(isinstance(item, dict) and type(item.get("key")) is int and item["key"] == local_key and
                item.get("id") == "EndTurnButton" and item.get("visible") is True and
                item.get("disabled") is False and item.get("bounds") == bounds and
                item.get("clippedBounds") == bounds for item in inputs) and
            {item.get("event") for item in inputs} == {"LeftClick", "RightClick"},
            "Native key does not resolve to exactly two enabled original EndTurnButton callbacks with exact bounds")
    return inputs


def require_packet_end_turn_hit(packet_hit_rows: list[tuple[int, tuple[float, float, float, float]]],
                                local_key: int) -> None:
    require(packet_hit_rows == [(local_key, (1584.0, 844.0, 1904.0, 880.0))],
            "ActionInfo scene packet does not contain exactly the original local-key button hit")


def require_global_key(global_key: int, local_key: int) -> None:
    require(global_key == KEY_BASE + local_key,
            "ActionInfo native target does not map the original local key through its exact context namespace")


def require_native_button_marker(output: str, generation: int, global_key: int, phase: str) -> None:
    rows = [row for row in BUTTON.finditer(output)
            if int(row[1]) == generation and int(row[2]) == global_key]
    expected_button = 5 if phase == "unit-right" else 1
    require(len(rows) == 1 and int(rows[0][3]) == expected_button and int(rows[0][4]) == 0,
            "Native input marker does not match the ActionInfo target generation/key/button")


def require_published_world_frame(output: str, frame: re.Match[str]) -> re.Match[str]:
    generation, turn, device = int(frame[2]), int(frame[3]), int(frame[6])
    worlds = [row for row in WORLD_FRAME.finditer(output) if int(row[2]) == generation]
    commits = [row for row in COMMITTED.finditer(output) if int(row[1]) == generation]
    require(len(worlds) == len(commits) == 1 and device > 0 and
            int(worlds[0][3]) == turn and int(worlds[0][6]) == device == int(commits[0][2]) and
            commits[0].end() < worlds[0].start() and worlds[0].end() < frame.start(),
            "ActionInfo frame lacks its unique preceding committed world generation, turn and device")
    return worlds[0]


def require_world_end_turn_hit(world: dict, global_key: int, local_key: int) -> None:
    require_global_key(global_key, local_key)
    hits = world.get("hits")
    require(isinstance(hits, list) and all(isinstance(row, list) and len(row) == 5 and
            type(row[0]) is int for row in hits), "Published world hit records are malformed")
    action_hits = [row for row in hits if KEY_BASE <= row[0] < KEY_BASE + (1 << 32)]
    require(action_hits == [[global_key, 1584, 844, 1904, 880]],
            "Published world does not contain exactly the namespaced original ActionInfo button hit")


def require_action_info_state(info: object, world: dict, *, owner: int, turn: int,
                              blocker: int, notification: int, phase: str,
                              sdk_identity: tuple[int, int, int, int]) -> None:
    require(isinstance(info, dict) and
            all(type(info.get(name)) is int for name in ("owner", "turn", "blockingType", "blockingNotification")) and
            (info["owner"], info["turn"], info["blockingType"], info["blockingNotification"]) ==
            (owner, turn, blocker, notification) and info.get("canEndTurn") is (phase == "end-turn"),
            "ActionInfo snapshot owner, turn, blocker, notification or readiness differs from its actual target/frame")
    require(all(type(world.get(name)) is int for name in ("turn", "elapsed", "activePlayer", "gridWidth", "gridHeight")) and
            (world["turn"], world["elapsed"], world["activePlayer"]) == sdk_identity[:3] and
            world["gridWidth"] > 0 and world["gridHeight"] > 0 and
            world["gridWidth"] * world["gridHeight"] == sdk_identity[3] and
            (turn, owner) == (sdk_identity[0], sdk_identity[2]),
            "Published ActionInfo world identity differs from its captured initial human-turn SDK state")


def verified_original(prepared: dict, snapshot: dict, manifest: dict) -> dict:
    proof = prepared.get("action_info_panel")
    require(isinstance(proof, dict), "Frozen prepared.json omits ActionInfoPanel source proof")
    for field, expected in (("originalLua", ACTION_LUA), ("originalXml", ACTION_XML)):
        ref = proof.get(field)
        verify_original_asset_ref(ref, expected, field)
        captured = snapshot.get("actionInfoPanel", {}).get(field)
        require(isinstance(captured, dict) and captured.get("path") == ref.get("path") and
                captured.get("sha256") == ref.get("sha256"), f"Snapshot {field} differs from frozen preparation")
        require(any(isinstance(row, dict) and row.get("path") == ref.get("path") and
                    row.get("sha256") == ref.get("sha256") for row in manifest.get("original_context_sources", [])),
                f"Scene manifest omits original {field} provenance")
    xml_ref = proof["originalXml"]
    original_xml = artifact_ref(xml_ref, label="original ActionInfoPanel XML")
    root = ET.parse(original_xml).getroot()
    lua_nodes = [node for node in root.iter() if node.tag == "LuaContext"]
    require(len(lua_nodes) == 1 and lua_nodes[0].attrib.get("ID") == "NotificationPanel",
            "Original ActionInfoPanel XML no longer has its one unconnected NotificationPanel declaration")
    parent = next(node for node in root.iter() if lua_nodes[0] in list(node))
    parent.remove(lua_nodes[0])
    require(xml_tree_matches(root, snapshot.get("tree")),
            "Captured ActionInfo controls differ from the original XML tree")
    return {"original_lua": proof["originalLua"], "original_xml": proof["originalXml"],
            "source_bytes_preserved": True, "notification_panel_connected": False}


def verify_frame(run_runtime: Path, prepared: dict,
                 generated: dict[str, list[Path]], generated_paths: set[Path],
                 frame_row: re.Match[str], target: re.Match[str], output: str,
                 initial_identity: tuple[int, int, int, int]) -> dict:
    revision, generation, frame_turn = int(frame_row[1]), int(frame_row[2]), int(frame_row[3])
    snapshot_ref, folder_ref = frame_row[7], frame_row[8]
    snapshot_path = Path(snapshot_ref).resolve(strict=True)
    session_root = (run_runtime / "sessions").resolve(strict=True)
    require(snapshot_path in generated_paths and snapshot_path.is_relative_to(session_root),
            "ActionInfo frame snapshot is not a generated artifact of this exact run")
    manifest_path = trade_route_frame_manifest(snapshot_path, folder_ref, generated_paths, session_root)
    snapshot = load_json(snapshot_path, "ActionInfo frame snapshot")
    manifest = load_json(manifest_path, "ActionInfo frame manifest")
    world_row = require_published_world_frame(output, frame_row)
    world_revision = int(world_row[1])
    world_path = unique_generated(generated, f"play-scene-{world_revision}.json")
    gpu_path = unique_generated(generated, f"play-scene-{world_revision}-gpu.png")
    require(world_path.parent == gpu_path.parent == snapshot_path.parent,
            "Published ActionInfo world JSON or GPU capture belongs to another session")
    world = load_json(world_path, "published ActionInfo world scene")
    require(type(world.get("generation")) is int and world["generation"] == generation and
            isinstance(world.get("hits"), list) and len(world["hits"]) == int(world_row[5]),
            "Published world JSON generation or hit count differs from its exact WORLD_FRAME marker")
    with gpu_path.open("rb") as stream:
        png_header = stream.read(24)
    require(len(png_header) == 24 and png_header[:16] == b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR",
            "Published ActionInfo GPU capture lacks a valid PNG dimension header")
    client_width, client_height = struct.unpack_from(">2I", png_header, 16)
    require((client_width, client_height) == (1280, 720),
            "Published ActionInfo GPU capture differs from the native 1280x720 client contract")
    packet_path = artifact_ref(manifest.get("packet"), exact=Path(folder_ref).resolve(strict=True) / "scene.packet",
                               label="ActionInfo scene packet")
    require(snapshot.get("contextName") == "ActionInfoPanel" and snapshot.get("popupKind") == "ActionInfoPanel" and
            snapshot.get("active") is True and snapshot.get("timerSemaphore") == 0 and
            snapshot.get("nonmodal") is True and snapshot.get("lifecycle") == ["queued"],
            "ActionInfo snapshot is not the active original nonmodal world overlay")
    require(snapshot.get("scrollTargets", []) == [], "Original ActionInfoPanel unexpectedly exposes scroll input")
    proof = verified_original(prepared, snapshot, manifest)
    info = snapshot.get("actionInfoPanel")
    require(isinstance(info, dict) and info.get("notificationPanelIntegrated") is False,
            "Original NotificationPanel boundary is missing or was connected")
    require_action_info_state(info, world, owner=int(frame_row[4]), turn=frame_turn,
                              blocker=int(target[2]), notification=int(target[3]), phase=target[1],
                              sdk_identity=initial_identity)
    tree = snapshot.get("tree")
    def find(node: object, wanted: str) -> list[dict]:
        if not isinstance(node, dict):
            return []
        found = [node] if node.get("id") == wanted else []
        for child in node.get("children", []):
            found.extend(find(child, wanted))
        return found
    buttons, captions = find(tree, "EndTurnButton"), find(tree, "EndTurnText")
    require(len(buttons) == len(captions) == 1 and buttons[0].get("kind") == "GridButton" and
            captions[0].get("kind") == "Label" and isinstance(captions[0].get("text"), str) and captions[0]["text"].strip(),
            "Original EndTurnButton or its caption is missing")
    button = buttons[0]
    bounds = [button.get("x"), button.get("y"), button.get("width"), button.get("height")]
    require(bounds == [1584, 844, 320, 36],
            "Original EndTurnButton bounds differ from the source-anchored 1920x1080 geometry")
    key = int(target[4])
    local_key = button.get("key")
    require(type(local_key) is int and 0 < local_key < (1 << 32),
            "Original EndTurnButton key is outside the exact local ActionInfo namespace")
    require_world_end_turn_hit(world, key, local_key)
    inputs = snapshot.get("inputTargets", [])
    require_end_turn_targets(inputs, local_key)
    require(button.get("hidden") is False and button.get("disabled") is False,
            "Captured original EndTurnButton identity or enabled state differs from its native key")
    manifest_scene = manifest.get("action_info_panel_scene", {})
    require(manifest_scene.get("end_turn_button_key") == local_key and
            manifest_scene.get("end_turn_bounds") == bounds and
            manifest_scene.get("end_turn_text") == captions[0]["text"] and
            manifest_scene.get("button_disabled") is False and
            manifest.get("scroll_regions") == [], "Published manifest differs from captured original button geometry")
    hits = manifest.get("hit_regions", [])
    require(hits == [[local_key, 1584, 844, 1904, 880]], "Published packet hit region differs from original button geometry")
    _, sprite_count, packet_hit_rows = packet_hits(packet_path)
    require_packet_end_turn_hit(packet_hit_rows, local_key)
    posts = [row for row in POST.finditer(output)
             if int(row[1]) == generation and int(row[2]) == key]
    require_native_button_marker(output, generation, key, target[1])
    logical_post = [int(posts[0][3]) * 1920 / client_width,
                    int(posts[0][4]) * 1080 / client_height] if len(posts) == 1 else []
    require(len(posts) == 1 and 1584 <= logical_post[0] < 1904 and 844 <= logical_post[1] < 880,
            "Physical HWND client-pixel post does not map inside the original 1920x1080 button hit region")
    require(int(target[5]) == generation and int(target[6]) == frame_turn,
            "Target turn/generation differs from its published ActionInfo frame")
    return {"revision": revision, "generation": generation, "turn": frame_turn,
            "snapshot": {"path": str(snapshot_path), "sha256": digest(snapshot_path)},
            "manifest": {"path": str(manifest_path), "sha256": digest(manifest_path)},
            "packet": {"path": str(packet_path), "sha256": digest(packet_path),
                       "sprite_count": sprite_count, "hit_count": 1},
            "world": {"path": str(world_path), "sha256": digest(world_path),
                      "revision": world_revision, "generation": generation,
                      "device_identity": int(world_row[6]), "global_key": key,
                      "hit_bounds": [1584, 844, 1904, 880]},
            "gpu_capture": {"path": str(gpu_path), "sha256": digest(gpu_path),
                            "client_size": [client_width, client_height]},
            "action_info_state": {name: info[name] for name in
                                  ("owner", "turn", "blockingType", "blockingNotification", "canEndTurn")},
            "source": proof, "control_id": "EndTurnButton", "local_key": local_key,
            "bounds": bounds, "posted_client_point": [int(posts[0][3]), int(posts[0][4])],
            "posted_scene_point": logical_post,
            "caption": captions[0]["text"]}


def verify_states(generated: dict[str, list[Path]], restored: bool,
                  initial_identity: tuple[int, int, int, int]) -> dict:
    phases = ("unit-right", "unit-left") + (() if restored else ("notification",))
    checks = {}
    for phase in phases:
        before = unique_generated(generated, f"action-info-{phase}-before.txt")
        after = unique_generated(generated, f"action-info-{phase}-after.txt")
        before_bytes, after_bytes = before.read_bytes(), after.read_bytes()
        require(before_bytes == after_bytes,
                f"ActionInfo {phase} callback changed the complete SDK snapshot unexpectedly")
        require(sdk_state_identity(before_bytes, f"ActionInfo {phase} SDK state") == initial_identity,
                f"ActionInfo {phase} callback SDK identity differs from the captured initial human turn")
        checks[phase] = {"before_sha256": digest(before), "after_sha256": digest(after), "byte_equal": True,
                         "sdk_identity": initial_identity}
    return checks


def native_save_metadata(path: Path) -> tuple[int, ...]:
    data = path.read_bytes()
    require(len(data) >= 48 and data[:16] == b"ZEROSIS_SAVE_V1\0" and
            hashlib.sha256(data[:-32]).digest() == data[-32:],
            "ActionInfo native save header or whole-file digest is invalid")
    meta = struct.unpack_from("<8I", data, 16)
    require(meta[0] == 1 and meta[1] == 0 and meta[5:] == (64, 64, 133),
            "ActionInfo native save format/map metadata differs from the sealed SDK contract")
    return meta


def verify_run(run_id: str, chain: frozenset[str] = frozenset()) -> dict:
    require(RUN_ID.fullmatch(run_id) is not None and run_id not in chain,
            "Invalid or cyclic ActionInfo run ID")
    evidence = EVIDENCE / run_id
    runtime = (RUNTIMES / run_id).resolve(strict=True)
    request_path, result_path = evidence / "request.json", evidence / "result.json"
    request, result = load_json(request_path, "ActionInfo request"), load_json(result_path, "ActionInfo result")
    check_artifacts(request)
    check_artifacts(result)
    resume = request.get("resume_from")
    require(resume is None or isinstance(resume, dict), "ActionInfo resume lineage is malformed")
    restored = isinstance(resume, dict)
    require(request.get("run_id") == result.get("run_id") == run_id and
            all(request.get(k) is True for k in ("smoke", "decisions", "top_panel", "action_info_panel")) and
            result.get("action_info_panel_requested") is True and
            result.get("action_info_panel_sequence_verified") is True and
            result.get("action_info_panel_dispatch_verified") is True and
            result.get("returncode") == 0 and result.get("timed_out") is False and
            result.get("runtime_inputs_unchanged") is True and result.get("failures") == [] and
            str(result.get("status", "")).endswith("PASS"),
            "Runner did not report a clean, complete ActionInfo profile; independent checks still apply")
    require(Path(request.get("cwd", "")).resolve(strict=True) == runtime,
            "ActionInfo request escaped its exact immutable private runtime")
    artifact_ref(result.get("request"), exact=request_path, label="ActionInfo request reference")
    stdout_path = artifact_ref(result.get("stdout"), exact=evidence / "stdout.log", label="ActionInfo stdout")
    stderr_path = artifact_ref(result.get("stderr"), exact=evidence / "stderr.log", label="ActionInfo stderr")
    output = stdout_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    stderr = stderr_path.read_text(encoding="utf-8")
    require(not re.search(r"HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|INTERACTIVE_INPUT_REJECTED", output + stderr),
            "Host output contains a native, cleanup, or input failure")
    timeline_ok, timeline_error = verify_action_info_panel_timeline(output, restored=restored)
    require(timeline_ok, timeline_error or "ActionInfo timeline did not pass")
    host_path, bundle_path, _ = verified_runtime_bundle(request, runtime, "ActionInfo")
    build_path = artifact_ref(request.get("provenance", {}).get("host_build"), label="ActionInfo Host build")
    build = load_json(build_path, "ActionInfo Host build report")
    require(build.get("status") == "UI_WINDOW_HOST_CANDIDATE_BUILT" and
            build.get("source_inputs_unchanged") is True and
            digest(host_path) == build.get("executable", {}).get("sha256"),
            "ActionInfo runtime Host differs from its successful frozen build")
    source_rows = {Path(row.get("path", "")).name: row for row in build.get("sources", []) if isinstance(row, dict)}
    host_source_proof = {}
    for name in HOST_SOURCES:
        require(name in source_rows, f"Host build omits ActionInfo source {name}")
        freeze_root = "project" if name == "UiScene.lua" else "include_roots/project"
        frozen = compiled_build_source(build.get("build_id"), source_rows[name], f"Source\\Host\\{name}", freeze_root)
        host_source_proof[name] = {"path": str(frozen), "sha256": digest(frozen)}
    generated, generated_paths = generated_map(result, runtime)
    initial_state = unique_generated(generated, "play-initial-state.txt")
    initial_identity = sdk_state_identity(initial_state.read_bytes(), "ActionInfo initial SDK state")
    verify_frozen_support(request, evidence, runtime)
    prepared_path = (runtime / "interactive_ui_support/assets/prepared.json").resolve(strict=True)
    prepared = load_json(prepared_path, "frozen UI preparation report")
    require(prepared.get("action_info_panel", {}).get("sourceBytesPreserved") is True,
            "Prepared ActionInfo source preservation proof is absent")
    attempt_path = artifact_ref(result.get("attempt"), exact=evidence / "attempt.json", label="ActionInfo attempt")
    attempt = load_json(attempt_path, "ActionInfo Host attempt")
    require(attempt.get("status") == "FINISHED" and attempt.get("returncode") == 0 and
            attempt.get("timed_out") is False and attempt.get("pid") == result.get("driver_pid"),
            "ActionInfo Host attempt did not finish under the recorded driver")
    frames = list(FRAME.finditer(output))
    targets = list(TARGET.finditer(output))
    require(len(targets) == (3 if restored else 5), "ActionInfo target count differs from fresh/restore contract")
    frame_by_generation = {int(row[2]): row for row in frames}
    require(len(frame_by_generation) == len(frames), "ActionInfo frame generation is duplicated")
    frame_proofs = []
    for target in targets:
        generation = int(target[5])
        require(generation in frame_by_generation, "ActionInfo target has no exact published frame")
        frame = frame_by_generation[generation]
        frame_proofs.append(verify_frame(runtime, prepared, generated, generated_paths, frame, target,
                                        output, initial_identity))
    states = verify_states(generated, restored, initial_identity)
    final_state = unique_generated(generated, "play-final-state.txt")
    final_identity = sdk_state_identity(final_state.read_bytes(), "ActionInfo final SDK state")
    saves = [tuple(row.groups()) for row in SAVE.finditer(output)]
    next_turn = [tuple(row.groups()) for row in NEXT_TURN.finditer(output)]
    require(len(saves) >= 2 and result.get("native_saves") == [list(row) for row in saves] and
            len(next_turn) == 1 and result.get("next_human_turn") == [list(next_turn[0])] and
            int(saves[-1][0]) == final_identity[0] == int(next_turn[0][0]),
            "ActionInfo run lacks repeated final-turn SDK saves or matching normal turn evidence")
    archives = []
    archive_metadata = []
    for turn, save_name in saves:
        save_path = Path(save_name).resolve(strict=True)
        require(save_path in generated_paths and int(turn) == final_identity[0],
                "ActionInfo native save is not a generated final-turn session artifact")
        metadata = native_save_metadata(save_path)
        require(metadata[2:5] == final_identity[:3],
                "ActionInfo native save turn/player differs from its final SDK state")
        archive_metadata.append(metadata)
        archives.append(inspect_save(save_path, bundle_path, save_path.parent / "Civ5SavedGameDatabase.db",
                                     expected=metadata))
    require(len(set(archive_metadata)) == 1,
            "Repeated ActionInfo native saves do not preserve one exact turn/player archive identity")
    restore_proof = None
    if restored:
        source_id = resume.get("run_id")
        require(isinstance(source_id, str) and RUN_ID.fullmatch(source_id) is not None and source_id != run_id,
                "ActionInfo restore source ID is invalid")
        fresh_proof = verify_run(source_id, chain | {run_id})
        source_evidence = EVIDENCE / source_id
        source_runtime = (RUNTIMES / source_id).resolve(strict=True)
        source_request = load_json(source_evidence / "request.json", "ActionInfo source request")
        source_result = load_json(source_evidence / "result.json", "ActionInfo source result")
        require(source_request.get("action_info_panel") is True and source_request.get("resume_from") is None and
                fresh_proof.get("status") == "PASS_INTERACTIVE_ACTION_INFO_PANEL_NATIVE_SDK_SMOKE" and
                source_result.get("pid") != result.get("pid") and
                source_result.get("driver_pid") != result.get("driver_pid"),
                "Restore does not descend from a separately completed fresh ActionInfo run")
        source_generated, source_paths = generated_map(source_result, source_runtime)
        frozen_source_result = artifact_ref(resume.get("run_result"), exact=evidence / "resume-source-result.json",
                                            label="frozen ActionInfo source result")
        source_result_path = source_evidence / "result.json"
        require(frozen_source_result.read_bytes() == source_result_path.read_bytes(),
                "Resumed request's frozen source result differs from the selected fresh run")
        source_host, source_bundle, _ = verified_runtime_bundle(source_request, source_runtime,
                                                                 "ActionInfo fresh source")
        require(digest(source_host) == digest(host_path) and digest(source_bundle) == digest(bundle_path),
                "Fresh and restored ActionInfo runs do not use the same sealed Host bundle")
        source_state = unique_generated(source_generated, "play-final-state.txt")
        restored_initial = unique_generated(generated, "play-initial-state.txt")
        require(source_state.read_bytes() == restored_initial.read_bytes(),
                "Restored SDK initial state differs byte-for-byte from fresh ActionInfo final state")
        checkpoint = artifact_ref(resume.get("checkpoint_input"), exact=runtime / "checkpoint-input.zssave",
                                  label="ActionInfo restored checkpoint copy")
        source_save = artifact_ref(resume.get("checkpoint_source"), label="ActionInfo source checkpoint")
        require(source_save in source_paths and checkpoint.read_bytes() == source_save.read_bytes(),
                "Restored checkpoint is not byte-identical to a generated fresh-run SDK save")
        source_metadata = native_save_metadata(source_save)
        source_archive = inspect_save(source_save, source_bundle,
                                      source_save.parent / "Civ5SavedGameDatabase.db", expected=source_metadata)
        roundtrip_path = unique_generated(generated, "play-restored-checkpoint.zssave")
        roundtrip_metadata = native_save_metadata(roundtrip_path)
        resumed_archive = inspect_save(roundtrip_path, bundle_path,
                                       restored_initial.parent / "Civ5SavedGameDatabase.db", expected=roundtrip_metadata)
        require(source_metadata == roundtrip_metadata,
                "Restore roundtrip changed native save turn/player/map metadata")
        source_sections = {(row["kind"], row["index"]): row["sha256"] for row in source_archive["sections"]}
        resumed_sections = {(row["kind"], row["index"]): row["sha256"] for row in resumed_archive["sections"]}
        require(source_sections.keys() == resumed_sections.keys() and len(source_sections) == 133,
                "ActionInfo native save/restore section inventories differ")
        changed = sorted(key for key in source_sections if source_sections[key] != resumed_sections[key])
        require(all(key == (3, 0) for key in changed),
                "Restored ActionInfo checkpoint changed native player/team sections")
        require(result.get("fresh_process_restore_verified") is True and
                result.get("checkpoint_input_unchanged") is True and result.get("semantic_restore_equal") is True,
                "Runner did not complete its fresh-process checkpoint checks")
        restore_proof = {"source_run_id": source_id, "source_result_sha256": digest(source_evidence / "result.json"),
                         "initial_state_equal": True, "checkpoint_copy_equal": True,
                         "native_section_count": len(source_sections), "changed_sections": changed,
                         "initial_identity": initial_identity,
                         "allowed_changed_section": {"kind": 3, "index": 0, "name": "Game"},
                         "game_internal_rng_reload_equality_verified": False}
    proof = {"status": "PASS_INTERACTIVE_ACTION_INFO_PANEL_NATIVE_SDK_SMOKE", "run_id": run_id,
             "result": {"path": str(result_path), "sha256": digest(result_path)},
             "host_build": {"path": str(build_path), "sha256": digest(build_path)},
             "host_sources": host_source_proof, "frames": frame_proofs, "sdk_state_checks": states,
             "initial_sdk_identity": initial_identity,
             "sdk_identity_fields": ["turn", "elapsedTurns", "activePlayer", "plotCount"],
             "native_save_count": len(archives), "final_sdk_identity": final_identity,
             "restore": restore_proof, "retail_pixels_verified": False,
             "notification_panel_integrated": False}
    return proof


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="Exact immutable run ID to verify")
    parser.add_argument("--output", type=Path, help="Optional new validation JSON path")
    parser.add_argument("--prior-validation", type=Path, action="append", default=[],
                        help="Earlier validation report(s) preserved as provenance for a follow-up")
    args = parser.parse_args()
    try:
        proof = verify_run(args.run_id)
        error = None
    except (OSError, ValueError, KeyError, RuntimeError, ET.ParseError) as exc:
        proof = {"status": "FAIL_INTERACTIVE_ACTION_INFO_PANEL_NATIVE_SDK_SMOKE",
                 "run_id": args.run_id, "error": str(exc)}
        error = str(exc)
    if args.prior_validation:
        proof["verification_followup"] = {
            "native_reexecuted": False,
            "verifier_sha256": digest(Path(__file__).resolve()),
            "prior_reports": [
                {"path": str(path.resolve(strict=True)), "sha256": digest(path.resolve(strict=True))}
                for path in args.prior_validation
            ],
            "corrections": [
                "Prepared original asset references may omit optional bytes while path and SHA-256 remain mandatory.",
                "Original XML controls without an ID are compared with the renderer's empty-string ID representation.",
                "The original EndTurnButton retains distinct left- and right-click input target rows for one key.",
                "Scene packet hit records retain local UI keys; HWND targets carry the native context namespace.",
                "Each native ActionInfo target is checked against the exact global HWND input marker and scene coordinates.",
                "Both callback rows require exact local key, ID, visibility, enabled state and complete/clipped bounds; extra rows are rejected.",
                "Each target binds a unique committed WORLD_FRAME generation, turn and device to its world JSON global hit and captured client dimensions.",
                "Snapshot owner, turn, blocker, notification and readiness match the target/frame and captured SDK identity.",
                "Restored Host source provenance remains separate from recursively verified fresh-run proof; Game section internal RNG/reload equality is unverified.",
            ],
        }
    target = args.output or (EVIDENCE / args.run_id / "action_info_panel_validation.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(proof, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(json.dumps({"status": proof["status"], "output": str(target), "error": error}, ensure_ascii=False))
    return 0 if proof["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    sys.exit(main())
