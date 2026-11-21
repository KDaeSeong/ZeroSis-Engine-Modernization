"""Verify a checkpoint carried into a distinct continuous-game Host process.

This joins one normal posted-input smoke run to a second process that loads
its final native checkpoint, confirms sampled SDK state, accepts more HWND
input, advances one turn, saves again, and shuts GameCore down cleanly.
"""
from __future__ import annotations

import argparse
import json
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
import verify_restore_game_metadata as restore_metadata
import verify_interactive_game as base

ROOT = PROJECT / "evidence/interactive_game"
RUNTIME_ROOT = PROJECT / "Build/InteractiveGameRuntime"
EXPECTED_SEQUENCE = "INTERACTIVE_SMOKE_SEQUENCE=SELECT_MOVE_EXPLICIT_SKIP_END_TURN_SAVE_WM_CLOSE"
END_TURN_POLICY = "INTERACTIVE_MANUAL_END_TURN_POLICY=PLAYEROPTION_WAIT_END_TURN:1"


def fail(message: str) -> None:
    raise RuntimeError(message)


def ref_json(row: dict, expected: Path | None = None) -> dict:
    if not isinstance(row, dict):
        fail("Missing immutable artifact reference")
    check_artifacts(row)
    path = Path(row["path"]).resolve(strict=True)
    if expected is not None and path != expected.resolve(strict=True):
        fail("Artifact reference escaped its expected checkpoint/runtime path")
    return json.loads(path.read_text(encoding="utf-8"))


def exact_file(row: dict, expected: Path | None = None) -> Path:
    if not isinstance(row, dict):
        fail("Missing immutable file artifact reference")
    check_artifacts(row)
    path = Path(row["path"]).resolve(strict=True)
    if expected is not None and path != expected.resolve(strict=True):
        fail("File artifact escaped its expected checkpoint/runtime path")
    return path


def runtime_input(request: dict, runtime: Path, basename: str) -> Path:
    rows = [row for row in request.get("runtime_inputs", []) if Path(row.get("path", "")).name == basename]
    if len(rows) != 1:
        fail(f"Runtime request does not contain exactly one frozen {basename}")
    check_artifacts(rows[0])
    path = Path(rows[0]["path"]).resolve(strict=True)
    if path != (runtime / basename).resolve(strict=True):
        fail(f"Frozen {basename} is outside its exact source runtime")
    return path


def output_text(evidence: Path, result: dict) -> tuple[str, str]:
    stdout = base.exact_ref(result.get("stdout"), evidence / "stdout.log", "stdout").read_text(encoding="utf-8")
    stderr = base.exact_ref(result.get("stderr"), evidence / "stderr.log", "stderr").read_text(encoding="utf-8", errors="replace")
    return stdout.replace("\r\n", "\n").replace("\r", "\n"), stderr


def state_identity(data: bytes) -> tuple[int, int, int, int]:
    try:
        first = data.decode("utf-8", errors="strict").splitlines()[0]
        fields = first.split("|")
        if len(fields) != 5 or fields[0] != "G":
            raise ValueError
        turn, elapsed, player, plots = map(int, fields[1:])
    except (UnicodeDecodeError, IndexError, ValueError) as exc:
        raise RuntimeError("Semantic SDK snapshot has no valid Game identity row") from exc
    if min(turn, elapsed, plots) < 0 or not 0 <= player < 64:
        fail("Semantic SDK snapshot identity is outside its native limits")
    return turn, elapsed, player, plots


def scene_projection(scene: dict) -> dict:
    # Generation, hit map, and selection annotation are presentation/input
    # state; compare the SDK-backed world values represented by the scene.
    units = []
    for unit in scene.get("units", []):
        if not isinstance(unit, dict):
            fail("Interactive scene contains a malformed unit row")
        units.append({key: unit.get(key) for key in ("id", "owner", "x", "y", "moves", "damage")})
    units.sort(key=lambda row: (row["owner"], row["id"]))
    plots = scene.get("plots")
    if not isinstance(plots, list) or any(not isinstance(row, list) or len(row) != 5 for row in plots):
        fail("Interactive scene plot map is malformed")
    return {
        "turn": scene.get("turn"), "elapsed": scene.get("elapsed"), "activePlayer": scene.get("activePlayer"),
        "gridWidth": scene.get("gridWidth"), "gridHeight": scene.get("gridHeight"),
        "units": units, "plots": plots,
    }


def generated_inventory(result: dict, runtime: Path) -> dict[str, Path]:
    rows = result.get("generated_files")
    if not isinstance(rows, list):
        fail("Interactive restore result lacks generated-file inventory")
    paths: list[Path] = []
    for row in rows:
        check_artifacts(row)
        path = Path(row["path"]).resolve(strict=True)
        if not path.is_relative_to((runtime / "sessions").resolve(strict=True)):
            fail("Generated resume artifact escaped its exact session tree")
        paths.append(path)
    actual = sorted(path.resolve() for path in (runtime / "sessions").rglob("*") if path.is_file())
    if sorted(paths) != actual or len(paths) != len(set(paths)):
        fail("Generated-file inventory does not exactly cover the resumed private session")
    named = {path.name: path for path in paths}
    if len(named) != len(paths):
        fail("Resumed session contains duplicate generated-file basenames")
    return named


def verify_manual_end_turn_policy(output: str, provenance: dict) -> None:
    if base.one_line(output, "INTERACTIVE_MANUAL_END_TURN_POLICY",
                     r"^INTERACTIVE_MANUAL_END_TURN_POLICY=(PLAYEROPTION_WAIT_END_TURN:1)$") != ["PLAYEROPTION_WAIT_END_TURN:1"]:
        fail("Interactive process did not apply the exact manual end-turn player option once")
    sealed_build = base.read_artifact(provenance.get("build"))
    sources = {Path(row.get("path", "")).name: row for row in sealed_build.get("sources", [])}
    session = sources.get("InteractiveGameSession.h")
    commands = sources.get("LocalGameCommands.h")
    if not isinstance(session, dict) or not isinstance(commands, dict):
        fail("Sealed Host provenance omits end-turn policy command sources")
    for row in (session, commands):
        check_artifacts(row)
    session_text = Path(session["path"]).read_text(encoding="utf-8")
    commands_text = Path(commands["path"]).read_text(encoding="utf-8")
    if "host_.localCommands.SendPlayerOption(PLAYEROPTION_WAIT_END_TURN,true);" not in session_text or \
       "void SendPlayerOption(PlayerOptionTypes option,bool value)" not in commands_text or \
       "const Command command={Command::Kind::PlayerOption,option,value" not in commands_text:
        fail("Frozen Host source does not connect the policy marker to ordinary SendPlayerOption")


def frozen_reload_metadata_helper(proof_dir: Path):
    source = PROJECT / "tools/verify_restore_game_metadata.py"
    frozen = proof_dir / "verify_restore_game_metadata.py"
    shutil.copy2(source, frozen)
    if digest(source) != digest(frozen):
        fail("Frozen SDK reload-metadata helper copy differs from its source")
    if Path(restore_metadata.__file__).resolve(strict=True) != source.resolve(strict=True):
        fail("Imported SDK reload-metadata helper is not the source file copied into proof")
    return restore_metadata, artifact(frozen)


def verify_restore_run(run_id: str, prior_id: str, prior_result: dict,
                       prior_request: dict, prior_provenance: dict,
                       proof_dir: Path) -> dict:
    if not re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", run_id):
        fail("Resume run ID has an invalid immutable identity")
    evidence = ROOT / run_id
    request_path, result_path = evidence / "request.json", evidence / "result.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if request.get("run_id") != run_id or result.get("run_id") != run_id:
        fail("Resume request/result identity differs from its evidence directory")
    check_artifacts(request); check_artifacts(result)
    base.exact_ref(result.get("request"), request_path, "resume request")
    output, stderr = output_text(evidence, result)
    attempt = ref_json(result.get("attempt"), evidence / "attempt.json")
    if result.get("status") != "CONTINUOUS_INTERACTIVE_SDK_WINDOW_RESTORE_SMOKE_PASS" or \
       result.get("returncode") != 0 or result.get("timed_out") is not False or \
       result.get("runtime_inputs_unchanged") is not True or result.get("native_window_posted_input_verified") is not True or \
       result.get("fresh_process_restore_verified") is not True or result.get("semantic_restore_equal") is not True or \
       result.get("checkpoint_input_unchanged") is not True or attempt.get("status") != "FINISHED" or \
       attempt.get("returncode") != 0 or attempt.get("timed_out") is not False or attempt.get("pid") != result.get("pid"):
        fail("Resume Host result did not complete its explicit restore, input, turn and save contract")
    if re.search(r"HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|SCRIPT_FAILURE", output + "\n" + stderr):
        fail("Resume process contains a Host, native, cleanup or script failure marker")
    runtime = Path(request.get("cwd", "")).resolve(strict=True)
    if runtime != (RUNTIME_ROOT / run_id).resolve(strict=True) or request.get("smoke") is not True or \
       request.get("input_profile") != "POSTED_HWND_CONTINUOUS_GAME_LOOP" or request.get("stage_or_mods_changed") is not False:
        fail("Resume process did not use its exact isolated posted-input runtime profile")
    resume_spec = request.get("resume_from")
    command = request.get("command")
    if not isinstance(resume_spec, dict) or not isinstance(command, list) or len(command) != 4 or \
       Path(command[0]).resolve() != (runtime / "ZeroSisHost_x64.exe").resolve() or command[1] != "--play-load-smoke" or \
       command[2] != request.get("language") or Path(command[3]).resolve() != Path(resume_spec.get("checkpoint_input", {}).get("path", "")).resolve():
        fail("Resume runner did not invoke the exact fresh-process checkpoint command")
    if result.get("pid") == prior_result.get("pid"):
        fail("Resume run reused the source smoke process instead of starting a new Host process")
    provenance = base.verify_provenance(request, result, runtime)
    verify_manual_end_turn_policy(output, provenance)
    for key in ("host_executable_sha256", "gamecore_sha256", "shared_lua_sha256"):
        if provenance[key] != prior_provenance[key]:
            fail(f"Checkpoint and resume process do not share identical sealed {key}")
    prior_manifest = next(Path(row["path"]) for row in prior_request["runtime_inputs"] if Path(row["path"]).name == "bundle.manifest")
    current_manifest = next(Path(row["path"]) for row in request["runtime_inputs"] if Path(row["path"]).name == "bundle.manifest")
    if digest(prior_manifest) != digest(current_manifest):
        fail("Checkpoint and resume private bundle manifests differ")
    named = generated_inventory(result, runtime)

    resume = request.get("resume_from")
    if not isinstance(resume, dict) or resume.get("run_id") != prior_id:
        fail("Resume request does not identify the exact source interactive run")
    prior_evidence = ROOT / prior_id
    frozen_prior_result = exact_file(resume.get("run_result"), evidence / "resume-source-result.json")
    original_prior_result = (prior_evidence / "result.json").resolve(strict=True)
    if not frozen_prior_result.is_relative_to(evidence.resolve(strict=True)) or \
       frozen_prior_result.read_bytes() != original_prior_result.read_bytes() or \
       digest(frozen_prior_result) != digest(original_prior_result):
        fail("Resume request frozen source result does not match the original source run bytes")
    prior_saves = base.one_line(prior_evidence.joinpath("stdout.log").read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n"),
                                "INTERACTIVE_NATIVE_SAVE", r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$")
    if len(prior_saves) < 2:
        fail("Source smoke did not produce the expected final native checkpoint")
    source_save = Path(prior_saves[-1][1]).resolve(strict=True)
    resume_source_ref = exact_file(resume.get("checkpoint_source"), source_save)
    base.generated(prior_result, resume_source_ref, Path(prior_request["cwd"]).resolve(strict=True))
    checkpoint_input = exact_file(resume.get("checkpoint_input"))
    if not checkpoint_input.is_relative_to(runtime) or checkpoint_input == resume_source_ref or \
       digest(checkpoint_input) != digest(resume_source_ref) or digest(checkpoint_input) != resume["checkpoint_input"].get("sha256"):
        fail("Resume checkpoint copy is not a byte-identical private-runtime input")
    if digest(resume_source_ref) != resume["checkpoint_source"].get("sha256"):
        fail("Original native checkpoint changed after it was frozen into the resume request")
    checkpoint_state_path = Path(resume.get("checkpoint_source_state", {}).get("path", "")).resolve(strict=True)
    if checkpoint_state_path != (RUNTIME_ROOT / prior_id / "sessions" / Path(prior_saves[-1][1]).parent.name / "play-final-state.txt").resolve(strict=True):
        fail("Source semantic checkpoint state does not belong to the original private session")
    base.generated(prior_result, checkpoint_state_path, Path(prior_request["cwd"]).resolve(strict=True))
    source_state = checkpoint_state_path.read_bytes()
    expected_state_path = exact_file(resume.get("expected_state"))
    expected_state = expected_state_path.read_bytes()
    if expected_state != source_state:
        fail("Frozen expected state differs from the source process close-time SDK snapshot")
    turn, elapsed, active, plot_count = state_identity(source_state)
    if resume.get("turn") != turn:
        fail("Resume request checkpoint turn differs from its frozen state snapshot")

    # The source and resumed processes each keep their own embedded database.
    prior_runtime = Path(prior_request["cwd"]).resolve(strict=True)
    prior_db = source_save.parent / "Civ5SavedGameDatabase.db"
    base.generated(prior_result, prior_db, prior_runtime)
    prior_rules_db = runtime_input(prior_request, prior_runtime, "rules.db")
    prior_localization_db = runtime_input(prior_request, prior_runtime, "localization.db")
    prior_output, _ = output_text(prior_evidence, prior_result)
    configuration_rows = base.one_line(prior_output, "NEW_GAME_CONFIGURATION_VERIFIED",
                                        r"^(NEW_GAME_CONFIGURATION_VERIFIED)$")
    if len(configuration_rows) != 1:
        fail("Checkpoint source did not report exactly one verified new-game configuration")
    manifest = Path(next(row["path"] for row in request["runtime_inputs"] if Path(row["path"]).name == "bundle.manifest")).resolve(strict=True)
    prior_manifest = Path(next(row["path"] for row in prior_request["runtime_inputs"] if Path(row["path"]).name == "bundle.manifest")).resolve(strict=True)
    source_archive = inspect_save(source_save, prior_manifest, prior_db,
                                  expected=(1, 0, turn, elapsed, active, 64, 64, 133))
    input_archive = inspect_save(checkpoint_input, manifest, prior_db,
                                 expected=(1, 0, turn, elapsed, active, 64, 64, 133))
    if source_archive["sections"] != input_archive["sections"]:
        fail("Copied resume checkpoint archive differs from the original native archive")

    restore_path = named.get("play-restored-checkpoint.zssave")
    initial_state_path = named.get("play-initial-state.txt")
    if restore_path is None or initial_state_path is None:
        fail("Resume session lacks its roundtrip checkpoint or initial semantic state")
    initial_state = initial_state_path.read_bytes()
    if initial_state != expected_state or initial_state != source_state:
        fail("Restored process initial semantic SDK snapshot differs byte-for-byte from checkpoint state")
    initial_identity = state_identity(initial_state)
    if initial_identity != (turn, elapsed, active, plot_count):
        fail("Restored initial game/map identity differs from its source checkpoint")
    roundtrip_archive = inspect_save(restore_path, manifest, initial_state_path.parent / "Civ5SavedGameDatabase.db",
                                     expected=(1, 0, turn, elapsed, active, 64, 64, 133))
    reload_helper, reload_helper_ref = frozen_reload_metadata_helper(proof_dir)
    reload_metadata_result = reload_helper.verify_game_restore(
        source_save, restore_path, rules_db_path=prior_rules_db,
        localization_db_path=prior_localization_db, language=prior_request.get("language"),
        configuration_verified=True,
    )
    source_sections = {(row["kind"], row["index"]): row["sha256"] for row in source_archive["sections"]}
    restored_sections = {(row["kind"], row["index"]): row["sha256"] for row in roundtrip_archive["sections"]}
    if source_sections.keys() != restored_sections.keys():
        fail("Roundtrip native save does not preserve the complete 133-section identity set")
    changed = sorted(identity for identity in source_sections if source_sections[identity] != restored_sections[identity])
    equal_count = len(source_sections) - len(changed)
    identity_rows = base.one_line(output, "INTERACTIVE_RESTORE_IDENTITY", r"^INTERACTIVE_RESTORE_IDENTITY=(\d+)\|(\d+)\|(\d+)\|(\d+)$")
    equal_rows = base.one_line(output, "INTERACTIVE_RESTORE_SECTIONS_EQUAL", r"^INTERACTIVE_RESTORE_SECTIONS_EQUAL=(\d+)\|(\d+)$")
    changed_rows = base.one_line(output, "INTERACTIVE_RESTORE_SECTION_CHANGED", r"^INTERACTIVE_RESTORE_SECTION_CHANGED=(\d+)\|(\d+)$")
    restore_checkpoint_rows = base.one_line(output, "INTERACTIVE_RESTORE_CHECKPOINT", r"^INTERACTIVE_RESTORE_CHECKPOINT=(.+)$")
    if identity_rows != [(str(turn), str(elapsed), str(active), "133")] or \
       equal_rows != [(str(equal_count), "133")] or \
       [tuple(map(int, row)) for row in changed_rows] != changed or changed != [(3, 0)] or \
       restore_checkpoint_rows != [str(checkpoint_input)] or \
       base.one_line(output, "INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED", r"^INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=(true)$") != ["true"]:
        fail("Restore identity or 133-section delta markers differ from independent archive comparison")

    scenes, gpu_frames = base.scene_maps(result, runtime)
    prior_scenes, _ = base.scene_maps(prior_result, prior_runtime)
    source_scene = prior_scenes[max(prior_scenes)][0]
    first_scene = scenes[1][0]
    if scene_projection(source_scene) != scene_projection(first_scene):
        fail("Resumed process initial world scene differs from source final non-input scene state")
    if first_scene["turn"] != turn or first_scene["elapsed"] != elapsed or first_scene["activePlayer"] != active or \
       first_scene["gridWidth"] * first_scene["gridHeight"] != plot_count or len(first_scene["plots"]) != plot_count:
        fail("First resumed world scene is not the exact checkpoint turn/player")

    starts = base.one_line(output, "INTERACTIVE_GAME_STARTED", r"^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$")
    selected_rows = base.one_line(output, "INTERACTIVE_UNIT_SELECTED", r"^INTERACTIVE_UNIT_SELECTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$")
    moved_rows = base.one_line(output, "INTERACTIVE_SMOKE_MOVEMENT_VERIFIED", r"^INTERACTIVE_SMOKE_MOVEMENT_VERIFIED=(\d+)\|(\d+)\|(\d+)$")
    mission_rows = base.one_line(output, "INTERACTIVE_MISSION_ACCEPTED", r"^INTERACTIVE_MISSION_ACCEPTED=(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$")
    next_rows = base.one_line(output, "INTERACTIVE_NEXT_HUMAN_TURN", r"^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$")
    close_rows = base.one_line(output, "INTERACTIVE_PLAY_CLOSED", r"^INTERACTIVE_PLAY_CLOSED=(\d+)\|NATIVE_CHECKPOINT_WRITTEN$")
    if len(starts) != 1 or not selected_rows or len(moved_rows) != 1 or len(next_rows) != 1 or len(close_rows) != 1 or \
       EXPECTED_SEQUENCE not in output or "INTERACTIVE_GAME_SESSION_STOPPED=true" not in output or \
       "INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true" not in output:
        fail("Resume process did not complete the original input/turn/save/close sequence")
    start_turn, player, width, height = map(int, starts[0])
    unit_id, target_x, target_y = map(int, moved_rows[0])
    selected = [tuple(map(int, row)) for row in selected_rows if int(row[1]) == unit_id]
    if len(selected) != 2:
        fail("Resumed moved unit lacks the initial and post-move native selection records")
    selected_turn, selected_id, start_x, start_y = selected[0]
    reselection_turn, reselection_id, reselection_x, reselection_y = selected[1]
    next_turn, updates = map(int, next_rows[0])
    if (start_turn, player, width, height) != (turn, active, first_scene["gridWidth"], first_scene["gridHeight"]) or \
       selected_turn != turn or selected_id != unit_id or not 0 <= start_x < width or not 0 <= start_y < height or \
       (reselection_turn, reselection_id, reselection_x, reselection_y) != (turn, unit_id, target_x, target_y) or \
       not 0 <= target_x < width or not 0 <= target_y < height or (start_x, start_y) == (target_x, target_y) or \
       next_turn != turn + 1 or int(close_rows[0][0]) != next_turn or updates <= 0:
        fail("Resumed process did not start from the checkpoint and reach exactly its next turn")
    prior_units = {row.get("id"): row for row in first_scene["units"] if isinstance(row, dict)}
    if unit_id not in prior_units or prior_units[unit_id].get("owner") != active or \
       (prior_units[unit_id].get("x"), prior_units[unit_id].get("y")) != (start_x, start_y):
        fail("Selected resumed unit does not match the checkpoint scene roster/coordinate")
    accepted_move = [tuple(map(int, row)) for row in mission_rows if int(row[1]) == unit_id and
                     int(row[3]) == target_x and int(row[4]) == target_y]
    if len(accepted_move) != 1 or accepted_move[0][0] != turn or accepted_move[0][2] < 0:
        fail("Resumed run lacks its exact SDK MOVE_TO mission record")
    move_scene = next((doc for _, (doc, _) in sorted(scenes.items()) if any(
        row.get("id") == unit_id and (row.get("x"), row.get("y")) == (target_x, target_y)
        for row in doc["units"] if isinstance(row, dict))), None)
    if move_scene is None:
        fail("Resumed SDK world scene never shows the moved unit at its actual destination")
    move_unit = next(row for row in move_scene["units"] if row.get("id") == unit_id)
    if move_unit.get("moves", 0) >= prior_units[unit_id].get("moves", 0):
        fail("Resumed unit movement did not reduce remaining SDK movement")
    final_scene = scenes[max(scenes)][0]
    final_units = {row.get("id"): row for row in final_scene["units"] if isinstance(row, dict)}
    if final_scene["turn"] != next_turn or final_scene["activePlayer"] != active or \
       final_units.keys() != prior_units.keys() or unit_id not in final_units or \
       (final_units[unit_id].get("x"), final_units[unit_id].get("y")) != (target_x, target_y):
        fail("Resume final scene does not preserve unit identities at the exact next turn")
    frames = result.get("frames", [])
    if len(frames) != len(scenes) or len(frames) < 5:
        fail("Resume HWND did not capture each scene to its GPU frame")
    device_ids = set()
    for revision, frame in enumerate(frames, 1):
        if len(frame) != 9:
            fail("Malformed resumed GPU frame row")
        rev, generation, frame_turn, unit_count, hit_count, device, present_count, _, device_kind = frame
        doc = scenes[revision][0]
        if (rev, generation, frame_turn, unit_count, hit_count) != \
           (revision, doc["generation"], doc["turn"], len(doc["units"]), len(doc["hits"])) or \
           device <= 0 or present_count <= 0 or device_kind not in (1, 2) or \
           base.verify_png(gpu_frames[revision]) != (1280, 720):
            fail("Resume frame metadata differs from its scene or private GPU capture")
        device_ids.add(device)
    if len(device_ids) != 1:
        fail("Resume scene refresh replaced the process-owned GPU device")
    posted = [tuple(map(int, row.split("|"))) for row in base.one_line(output, "INTERACTIVE_SMOKE_POSTED",
              r"^INTERACTIVE_SMOKE_POSTED=(\d+\|\d+\|-?\d+\|-?\d+)$")]
    native = [tuple(map(int, row.split("|"))) for row in base.one_line(output, "INTERACTIVE_WINDOW_INPUT",
             r"^INTERACTIVE_WINDOW_INPUT=(\d+\|\d+\|\d+\|[01])$")]
    if len(posted) < 5 or len(posted) != len(native):
        fail("Resume posted clicks do not match native input delivery count")
    selected_key = 0x5A57000000000000 | (2 << 48) | (unit_id & 0xFFFFFFFF)
    target_plot = next((plot for plot in first_scene["plots"] if plot[1] == target_x and plot[2] == target_y), None)
    if target_plot is None:
        fail("Resumed destination does not resolve to a unique checkpoint map plot")
    plot_key = 0x5A57000000000000 | (1 << 48) | (target_plot[0] & 0xFFFFFFFF)
    seen_selection = seen_move = False
    selected_click_positions: list[tuple[int, int]] = []
    for (gen, key, cx, cy), (delivered_gen, kind, delivered_key, consumed) in zip(posted, native):
        if (gen, key, kind, delivered_gen, delivered_key, consumed) != (gen, key, 1, gen, key, 1):
            fail("Resume HWND event was not consumed with its exact generation/key")
        docs = [doc for doc, _ in scenes.values() if doc["generation"] == gen]
        if len(docs) != 1:
            fail("Resume click generation does not identify one scene snapshot")
        doc = docs[0]
        hits = [hit for hit in doc["hits"] if isinstance(hit, list) and len(hit) == 5 and hit[0] == key]
        if len(hits) != 1 or not hits[0][1] <= cx * 1.5 < hits[0][3] or not hits[0][2] <= cy * 1.5 < hits[0][4]:
            fail("Resume posted coordinate/key is not inside its exact scene hit record")
        seen_selection |= key == selected_key
        seen_move |= key == plot_key
        if key == selected_key:
            unit_rows = [row for row in doc["units"] if isinstance(row, dict) and row.get("id") == unit_id]
            if len(unit_rows) != 1:
                fail("Repeated native unit selection does not resolve to one SDK scene unit")
            selected_click_positions.append((unit_rows[0].get("x"), unit_rows[0].get("y")))
    if not seen_selection or not seen_move:
        fail("Resume HWND did not deliver the exact unit and destination plot hits")
    if selected_click_positions != [(start_x, start_y), (target_x, target_y)]:
        fail("Initial selection and post-move reselection are not bound to their exact scene generations")
    if not any(int(row[2]) != accepted_move[0][2] and int(row[3]) == -1 and int(row[4]) == -1 for row in mission_rows):
        fail("Resume sequence lacks its explicit original MISSION_SKIP tuple")

    save_rows = base.one_line(output, "INTERACTIVE_NATIVE_SAVE", r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$")
    if len(save_rows) < 2 or any(int(row[0]) != next_turn for row in save_rows):
        fail("Resume close did not write repeated native saves at the resulting turn")
    manifest = Path(next(row["path"] for row in request["runtime_inputs"] if Path(row["path"]).name == "bundle.manifest")).resolve(strict=True)
    saves = []
    for turn_text, path_text in save_rows:
        path = Path(path_text).resolve(strict=True)
        base.generated(result, path, runtime)
        db = path.parent / "Civ5SavedGameDatabase.db"
        base.generated(result, db, runtime)
        saves.append(inspect_save(path, manifest, db,
                                  expected=(1, 0, next_turn, final_scene["elapsed"], active, 64, 64, 133)))
    return {
        "run_id": run_id, "source_run_id": prior_id, "language": request.get("language"), "pid": result.get("pid"),
        "restored_turn": turn, "resumed_turn": next_turn, "active_player": active, "unit_id": unit_id,
        "starting_coordinate": [start_x, start_y], "destination": [target_x, target_y],
        "move_mission": list(accepted_move[0]), "restore_identity": list(map(int, identity_rows[0])),
        "equal_native_sections": equal_count, "changed_sections": [list(row) for row in changed],
        "sdk_reload_metadata_verification": reload_metadata_result,
        "frozen_sdk_reload_metadata_helper": reload_helper_ref,
        "roundtrip_archive": roundtrip_archive, "resaved_archives": saves,
        "scene_count": len(scenes), "gpu_frames": len(frames), "gpu_device_identity": next(iter(device_ids)),
        "host_provenance": provenance, "checkpoint_source": resume["checkpoint_source"],
        "checkpoint_input": resume["checkpoint_input"], "expected_state": resume["expected_state"],
        "semantic_state_byte_equal": True, "scene_non_input_state_equal": True,
        "fresh_process_restore_verified": True, "post_restore_native_input_and_turn_verified": True,
        "human_input_verified": False, "retail_renderer_equivalence_verified": False, "full_gameplay_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-run", required=True)
    parser.add_argument("--resume-run", required=True)
    args = parser.parse_args()
    if args.checkpoint_run == args.resume_run:
        parser.error("--checkpoint-run and --resume-run must identify distinct Host processes")
    proof = ROOT / "validators" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12])
    proof.mkdir(parents=True, exist_ok=False)
    try:
        prior_id = args.checkpoint_run
        prior_evidence = ROOT / prior_id
        prior_request = json.loads((prior_evidence / "request.json").read_text(encoding="utf-8"))
        prior_result = json.loads((prior_evidence / "result.json").read_text(encoding="utf-8"))
        # The established smoke verifier proves the source run independently.
        prior_proof = base.verify_run(prior_id, proof / "source_run")
        prior_provenance = base.verify_provenance(prior_request, prior_result,
                                                   Path(prior_request["cwd"]).resolve(strict=True))
        if prior_proof.get("status") != "CONTINUOUS_INTERACTIVE_SDK_WINDOW_SMOKE_PASS":
            fail("Checkpoint source is not a verified successful posted-input smoke run")
        prior_output, _ = output_text(prior_evidence, prior_result)
        verify_manual_end_turn_policy(prior_output, prior_provenance)
        current_evidence = ROOT / args.resume_run
        current_result = json.loads((current_evidence / "result.json").read_text(encoding="utf-8"))
        current_request = json.loads((current_evidence / "request.json").read_text(encoding="utf-8"))
        if current_request.get("language") != prior_request.get("language"):
            fail("Checkpoint and resumed Host runs use different language settings")
        frozen_prior = current_request.get("resume_from", {}).get("run_result", {})
        frozen_prior_path = exact_file(frozen_prior, current_evidence / "resume-source-result.json")
        source_result_path = (prior_evidence / "result.json").resolve(strict=True)
        if not frozen_prior_path.is_relative_to(current_evidence.resolve(strict=True)) or \
           frozen_prior_path.read_bytes() != source_result_path.read_bytes() or \
           digest(frozen_prior_path) != digest(source_result_path):
            fail("Frozen resume-source-result.json does not byte-match the selected source run result")
        if current_request.get("resume_from", {}).get("run_id") != prior_id:
            fail("Resume request points to a different checkpoint source run")
        row = verify_restore_run(args.resume_run, prior_id, prior_result, prior_request,
                                 prior_provenance, proof)
        script_copy = proof / "verify_interactive_game_restore.py"
        shutil.copy2(Path(__file__).resolve(), script_copy)
        report = {
            "status": "FRESH_PROCESS_CHECKPOINT_RESTORE_CONTINUED_TURN_PASS",
            "scope": "PRIVATE_NATIVE_TURN1_CHECKPOINT_FRESH_HOST_RESTORE_POSTED_INPUT_MOVE_TURN2_RESAVE",
            "checkpoint_run_id": prior_id, "resume_run_id": args.resume_run,
            "source_smoke_proof": prior_proof, "resume_run": row,
            "independent_verifier": artifact(script_copy), "source_provenance_equal": True,
            "checkpoint_bytes_unchanged": True, "semantic_restore_equal": True,
            "native_section_restore_delta_verified": True, "fresh_process_restore_verified": True,
            "sdk_reload_metadata_delta_verified": True,
            "post_restore_native_input_and_turn_verified": True, "native_resave_verified": True,
            "human_input_verified": False, "retail_renderer_equivalence_verified": False,
            "full_gameplay_verified": False,
            "limitations": [
                "Restore equality covers the sampled SDK semantic snapshot, non-input scene state, and the SDK-defined replay/session reload delta; it does not establish general RNG or retail-save equivalence.",
                "Inputs are synthetic posted HWND clicks; this is not human-input proof.",
                "GPU output is the private strategic view and does not establish retail renderer equivalence.",
                "Two private turns do not establish complete gameplay coverage or external retail-save compatibility.",
            ],
        }
    except Exception as exc:
        report = {"status": "FAIL_INTERACTIVE_GAME_RESTORE_CONFORMANCE",
                  "checkpoint_run_id": args.checkpoint_run, "resume_run_id": args.resume_run,
                  "failure": f"{type(exc).__name__}: {exc}", "fresh_process_restore_verified": False,
                  "semantic_restore_equal": False, "human_input_verified": False,
                  "retail_renderer_equivalence_verified": False, "full_gameplay_verified": False}
        out = proof / "conformance.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "proof": artifact(out), "failure": report["failure"]}, ensure_ascii=False), file=sys.stderr)
        raise
    out = proof / "conformance.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "proof": artifact(out),
                      "checkpoint_run_id": args.checkpoint_run, "resume_run_id": args.resume_run,
                      "restored_turn": row["restored_turn"], "resumed_turn": row["resumed_turn"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
