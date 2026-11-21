"""Independently verify one private continuous-game HWND smoke run.

The proof is limited to the posted input sequence, actual SDK unit movement,
one normal turn, and private native save archives. It does not prove a fresh
session restore, human input, retail rendering, or complete gameplay.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import struct
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from run_new_game_probe import verify_city_site_base, verify_found_value_base
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts

ROOT = PROJECT / "evidence/interactive_game"
RUNTIME_ROOT = PROJECT / "Build/InteractiveGameRuntime"
REQUIRED_SOURCES = {
    "HostMain.cpp", "HostRun.h", "InteractiveGameSession.h", "InteractiveGameLoop.h",
    "WorldViewState.h", "WorldViewRenderer.cpp", "WorldViewRenderer.h", "BitmapWindow.cpp",
    "BitmapWindow.h", "LocalSdkSession.h", "LocalTurnController.h", "LocalTurnSignals.h",
    "SdkGameSave.h",
}


def fail(message: str) -> None:
    raise RuntimeError(message)


def read_artifact(ref: dict) -> dict:
    if not isinstance(ref, dict):
        fail("Expected a path/hash/size artifact reference")
    check_artifacts(ref)
    return json.loads(Path(ref["path"]).read_text(encoding="utf-8"))


def exact_ref(ref: dict, path: Path, label: str) -> Path:
    if not isinstance(ref, dict):
        fail(f"Run result omits its {label} artifact")
    check_artifacts(ref)
    target = path.resolve(strict=True)
    if Path(ref.get("path", "")).resolve(strict=True) != target:
        fail(f"{label} escaped its exact run directory")
    return target


def generated(result: dict, path: Path, runtime: Path) -> Path:
    target = path.resolve(strict=True)
    if not target.is_relative_to((runtime / "sessions").resolve(strict=True)):
        fail(f"Generated file escaped the private session tree: {target.name}")
    rows = [row for row in result.get("generated_files", [])
            if Path(row.get("path", "")).resolve() == target]
    if len(rows) != 1:
        fail(f"Expected exactly one generated-file record for {target.name}")
    check_artifacts(rows[0])
    return target


def one_line(text: str, marker: str, pattern: str) -> list[tuple[str, ...]]:
    matches = re.findall(pattern, text, re.M)
    if any(not row for row in matches):
        fail(f"Malformed {marker} marker")
    return matches


def json_scene(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    required = ("turn", "elapsed", "activePlayer", "gridWidth", "gridHeight", "generation", "units", "plots", "hits")
    if not isinstance(value, dict) or any(key not in value for key in required):
        fail(f"Interactive world scene has an incomplete schema: {path.name}")
    if any(type(value[key]) is not int for key in ("turn", "elapsed", "activePlayer", "gridWidth", "gridHeight", "generation")):
        fail(f"Interactive world scene has invalid scalar state: {path.name}")
    if not isinstance(value["units"], list) or not isinstance(value["plots"], list) or not isinstance(value["hits"], list):
        fail(f"Interactive world scene arrays are malformed: {path.name}")
    return value


def pixel_key(path: Path, scene: dict, x: float, y: float) -> int:
    """Independently decode the retained RLE GPU-ID raster at the actual click."""
    data = path.read_bytes()
    if len(data) < 20 or len(data) > 32 * 1024 * 1024 or data[:8] != b'ZSTPICK1':
        fail('Invalid terrain picking packet header/bound')
    width, height, count = struct.unpack_from('<III', data, 8)
    if (width, height) != (1920, 1080) or count > 500000 or len(data) < 20 + count * 8:
        fail('Invalid terrain picking dimensions/key count')
    keys = list(struct.unpack_from('<' + 'Q' * count, data, 20))
    visible = {0x5A57000000000000 | (1 << 32) | p[0] for p in scene['plots'] if p[3:] == [1, 1]}
    if 0 in keys or len(set(keys)) != count or not set(keys) <= visible or keys != scene.get('pixelHitKeys'):
        fail('Terrain picking keys contain duplicates, hidden plots or differ from scene metadata')
    if scene.get('pixelHitCount') != width * height or not (0 <= x < width and 0 <= y < height):
        fail('Terrain picking raster or click is outside its scene')
    offset = 20 + count * 8
    if (len(data) - offset) % 8:
        fail('Truncated terrain picking run')
    wanted, cursor, selected = int(y) * width + int(x), 0, 0
    for length, index in struct.iter_unpack('<II', data[offset:]):
        if length == 0 or index > count or cursor + length > width * height:
            fail('Terrain picking RLE range/index is invalid')
        if cursor <= wanted < cursor + length:
            selected = keys[index - 1] if index else 0
        cursor += length
    if cursor != width * height:
        fail('Terrain picking raster is incomplete')
    return selected


def scene_maps(result: dict, runtime: Path) -> tuple[dict[int, tuple[dict, Path]], dict[int, Path]]:
    rows = result.get("generated_files", [])
    scenes: dict[int, tuple[dict, Path]] = {}
    gpu: dict[int, Path] = {}
    for row in rows:
        path = Path(row.get("path", ""))
        match = re.fullmatch(r"play-scene-(\d+)(-gpu)?\.(json|png)", path.name)
        if not match:
            continue
        check_artifacts(row)
        number, is_gpu, suffix = int(match.group(1)), match.group(2) is not None, match.group(3)
        target = path.resolve(strict=True)
        if not target.is_relative_to((runtime / "sessions").resolve(strict=True)):
            fail("Interactive scene artifact escaped the private session")
        if suffix == "json":
            if number in scenes:
                fail("Duplicate interactive world scene revision")
            scenes[number] = (json_scene(target), target)
        elif is_gpu:
            if number in gpu:
                fail("Duplicate interactive GPU frame revision")
            gpu[number] = target
    if len(scenes) < 5 or set(scenes) != set(gpu) or sorted(scenes) != list(range(1, len(scenes) + 1)):
        fail("Interactive smoke did not preserve a contiguous scene and GPU frame sequence")
    return scenes, gpu


def verify_png(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        fail(f"GPU capture is not a PNG: {path.name}")
    width, height = struct.unpack_from(">II", data, 16)
    if width != 1280 or height != 720:
        fail(f"GPU capture dimensions are not the owned 1280x720 window: {path.name}")
    return width, height


def verify_provenance(request: dict, result: dict, runtime: Path, *,
                      expected_input_profile: str = "POSTED_HWND_CONTINUOUS_GAME_LOOP") -> dict:
    references = request.get("provenance")
    required_refs = {"host_build", "shared_lua_build", "explore_sdk_build", "city_site_sdk_build",
                     "found_value_shared_sdk_build", "bundle"}
    if not isinstance(references, dict) or not required_refs <= references.keys():
        fail("Interactive request lacks frozen Host/provider/Core/bundle provenance")
    build = read_artifact(references["host_build"])
    lua = read_artifact(references["shared_lua_build"])
    explore = read_artifact(references["explore_sdk_build"])
    city = read_artifact(references["city_site_sdk_build"])
    found = read_artifact(references["found_value_shared_sdk_build"])
    bundle = read_artifact(references["bundle"])
    if build.get("status") != "UI_WINDOW_HOST_CANDIDATE_BUILT" or build.get("source_inputs_unchanged") is not True:
        fail("Interactive runtime was not built from a sealed window Host")
    source_rows = {Path(row.get("path", "")).name: row for row in build.get("sources", [])}
    if not REQUIRED_SOURCES <= source_rows.keys():
        fail("Sealed Host source closure omits continuous gameplay code")
    for name in REQUIRED_SOURCES:
        check_artifacts(source_rows[name])
    host_text = {name: Path(source_rows[name]["path"]).read_text(encoding="utf-8") for name in REQUIRED_SOURCES}
    for token, source in (
        ("LiveMissionProfile", "LocalSdkSession.h"), ("CanStartMission", "InteractiveGameSession.h"),
        ("ResponsePushMission", "LocalSdkSession.h"), ("Game.CanDoControl(ControlTypes.CONTROL_ENDTURN)", "InteractiveGameSession.h"),
        ("CommitCompletion", "InteractiveGameSession.h"), ("game_->Update();Check();++updates_", "InteractiveGameSession.h"),
        ("INTERACTIVE_WINDOW_INPUT", "InteractiveGameLoop.h"), ("WorldViewHitKey::OwnedUnit", "InteractiveGameLoop.h"),
        ("WorldViewHitKey::Plot", "InteractiveGameLoop.h"), ("INTERACTIVE_SMOKE_MOVEMENT_VERIFIED", "InteractiveGameLoop.h"),
        ("play-scene-", "InteractiveGameLoop.h"),
    ):
        if token not in host_text[source]:
            fail(f"Sealed compiled source lacks required gameplay contract: {source}:{token}")
    inputs = request.get("runtime_inputs")
    if not isinstance(inputs, list) or not inputs:
        fail("Interactive request lacks its private runtime input manifest")
    by_name: dict[str, dict] = {}
    for row in inputs:
        check_artifacts(row)
        path = Path(row["path"]).resolve(strict=True)
        if not path.is_relative_to(runtime.resolve(strict=True)):
            fail("Interactive runtime input escaped its exact private runtime")
        name = path.name
        if name in by_name:
            fail(f"Private runtime contains duplicate input basename: {name}")
        by_name[name] = row
    for name in ("ZeroSisHost_x64.exe", "CvGameCoreDLL_Expansion2_x64.dll", "ZeroSisLua51_x64.dll", "bundle.manifest"):
        if name not in by_name:
            fail(f"Interactive runtime omits frozen input {name}")
    executable = build.get("executable", {})
    if by_name["ZeroSisHost_x64.exe"]["sha256"] != executable.get("sha256"):
        fail("Private Host executable hash differs from its sealed build")
    if lua.get("status") != "SHARED_LUA_RUNTIME_CANDIDATE_BUILT":
        fail("Interactive runtime did not use the accepted shared Lua provider")
    verify_city_site_base(city, explore)
    verify_found_value_base(found, city, "SHARED_FACTS")
    expected_core = found.get("gamecore", {}).get("sha256")
    if not expected_core or by_name["CvGameCoreDLL_Expansion2_x64.dll"]["sha256"] != expected_core or \
       by_name["ZeroSisLua51_x64.dll"]["sha256"] != lua.get("lua_dll", {}).get("sha256"):
        fail("Private GameCore/shared-Lua hashes differ from their frozen provider chain")
    if not isinstance(bundle.get("files"), list) or not isinstance(bundle.get("manifest"), dict):
        fail("Accepted Host bundle manifest has no file table")
    check_artifacts(bundle["files"]); check_artifacts(bundle["manifest"])
    private_manifest = Path(by_name["bundle.manifest"]["path"]).read_text(encoding="ascii")
    # The runtime manifest is generated from the accepted bundle payload with the
    # selected Host and Core replacements, then has the separately selected Lua
    # provider appended after those rows by the runner.
    expected_rows = []
    for row in bundle["files"]:
        name = Path(row["path"]).name
        selected = by_name.get(name)
        if selected is None:
            fail(f"Private runtime does not materialize accepted bundle payload {name}")
        expected_rows.append(f"{name}|{selected['sha256']}\n")
    expected_rows.append(f"ZeroSisLua51_x64.dll|{by_name['ZeroSisLua51_x64.dll']['sha256']}\n")
    if 'WorldTerrainRenderer.cpp' in source_rows:
        terrain = request.get('terrain_assets')
        if not isinstance(terrain, dict) or terrain.get('originals_unchanged') is not True or 'terrain-assets.bin' not in by_name:
            fail('3D Host is missing its original terrain package provenance')
        terrain_manifest = read_artifact(terrain.get('source_manifest'))
        check_artifacts(terrain.get('package'))
        package_hash = by_name['terrain-assets.bin']['sha256']
        if terrain_manifest.get('package', {}).get('sha256') != package_hash or terrain['package'].get('sha256') != package_hash:
            fail('3D Host terrain package differs from its original asset manifest')
        expected_rows.append(f"terrain-assets.bin|{package_hash}\n")
    unit_assets = request.get('unit_assets')
    if unit_assets is not None:
        if (not isinstance(unit_assets, dict) or unit_assets.get('status') != 'PASS_ORIGINAL_UNIT_PACKAGE'
                or 'unit-assets.bin' not in by_name or 'WorldUnitAssets.h' not in source_rows):
            fail('3D Host unit package lacks its accepted asset or compiled loader provenance')
        package_ref = unit_assets.get('package')
        package = exact_ref(package_ref, runtime / 'unit-assets.bin', 'unit assets package')
        size = package.stat().st_size
        unit_manifest = read_artifact(unit_assets.get('manifest'))
        declared = unit_manifest.get('package', {})
        source_package = unit_assets.get('source_package', {})
        package_hash = by_name['unit-assets.bin']['sha256']
        if (unit_manifest.get('status') != 'PASS_ORIGINAL_UNIT_PACKAGE' or not 20 <= size <= 64 * 1024 * 1024
                or any(ref.get('sha256') != package_hash or type(ref.get('bytes')) is not int or ref['bytes'] != size
                       for ref in (package_ref, declared, source_package, by_name['unit-assets.bin']))):
            fail('3D Host unit package hash/size differs from the frozen original manifest or runtime inventory')
        with package.open('rb') as stream:
            header = stream.read(12)
            if header not in (b'ZSUNIT01' + struct.pack('<I', 1), b'ZSUNIT02' + struct.pack('<I', 2)):
                fail('3D Host unit package header/version is invalid')
        expected_rows.append(f"unit-assets.bin|{package_hash}\n")
        animation = unit_assets.get('animation_runtime')
        if header == b'ZSUNIT02' + struct.pack('<I', 2):
            if not isinstance(animation, dict) or animation.get('format_version') != 2:
                fail('Animated unit package lacks its pinned runtime closure')
            check_artifacts(animation)
            bridge = read_artifact(animation['bridge_report'])
            if bridge.get('status') != 'PASS_NATIVE_GRANNY_C_ABI_X64':
                fail('Animation bridge does not have a passing x64 C ABI proof')
            dependencies = {Path(r['path']).name: r['sha256'] for r in [bridge['bridge'], *bridge['private_sdk_assemblies']]}
            sealed = {Path(r['path']).name: r['sha256'] for r in animation['dependencies']}
            if dependencies != sealed or len(sealed) != 5:
                fail('Animation runtime DLL hashes differ from the verified bridge closure')
            embedded = animation['embedded_inputs']
            expected_embedded = {r['name']: (r['bytes'], r['sha256']) for r in unit_manifest['animation']['embedded_files']}
            if {Path(r['path']).name: (r['bytes'], r['sha256']) for r in embedded} != expected_embedded or len(embedded) != 5:
                fail('Animation embedded file manifest differs from the sealed runtime')
            for ref in [*embedded, *animation['dependencies'], animation['config']]:
                name = Path(ref['path']).name
                exact_ref(ref, runtime / name, 'animation input')
                if name not in by_name or by_name[name]['sha256'] != ref['sha256']:
                    fail('Animation input is absent from runtime inventory')
                expected_rows.append(f"{name}|{ref['sha256']}\n")
        elif animation:
            fail('Static unit package unexpectedly declares animation runtime dependencies')
    elif 'unit-assets.bin' in by_name:
        fail('3D Host has an undeclared unit package input')
    if private_manifest != "ZEROSIS_HOST_BUNDLE_V4\n" + "".join(expected_rows):
        fail("Private runtime bundle manifest does not match accepted payload and selected sealed Host/Core/Lua")
    if request.get("input_profile") != expected_input_profile or request.get("smoke") is not True:
        fail("Interactive run did not use the posted HWND smoke profile")
    if request.get("stage_or_mods_changed") is not False:
        fail("Interactive run request claims stage/MODS mutation")
    return {"build": references["host_build"], "bundle": references["bundle"],
            "host_executable_sha256": by_name["ZeroSisHost_x64.exe"]["sha256"],
            "gamecore_sha256": by_name["CvGameCoreDLL_Expansion2_x64.dll"]["sha256"],
            "shared_lua_sha256": by_name["ZeroSisLua51_x64.dll"]["sha256"],
            "compiled_source_rows": {name: source_rows[name] for name in sorted(REQUIRED_SOURCES)}}


def verify_run(run_id: str, proof_dir: Path) -> dict:
    if not re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", run_id):
        fail("Interactive run ID has an invalid immutable identity")
    evidence = ROOT / run_id
    request_path, result_path = evidence / "request.json", evidence / "result.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if request.get("run_id") != run_id or result.get("run_id") != run_id:
        fail("Interactive request/result identity differs from its evidence directory")
    check_artifacts(request); check_artifacts(result)
    exact_ref(result.get("request"), request_path, "request")
    output = exact_ref(result.get("stdout"), evidence / "stdout.log", "stdout").read_text(encoding="utf-8", errors="strict")
    output = output.replace("\r\n", "\n").replace("\r", "\n")
    stderr = exact_ref(result.get("stderr"), evidence / "stderr.log", "stderr").read_text(encoding="utf-8", errors="replace")
    attempt_ref = result.get("attempt")
    if not isinstance(attempt_ref, dict):
        fail("Interactive result omits child process attempt metadata")
    attempt = json.loads(exact_ref(attempt_ref, evidence / "attempt.json", "attempt").read_text(encoding="utf-8"))
    if result.get("status") != "CONTINUOUS_INTERACTIVE_SDK_WINDOW_SMOKE_PASS" or \
       result.get("returncode") != 0 or result.get("timed_out") is not False or \
       result.get("runtime_inputs_unchanged") is not True or result.get("native_window_posted_input_verified") is not True or \
       result.get("stage_or_mods_changed") is not False or attempt.get("status") != "FINISHED" or \
       attempt.get("returncode") != 0 or attempt.get("timed_out") is not False or \
       attempt.get("pid") != result.get("driver_pid", result.get("pid")):
        fail("Interactive smoke process/result did not finish cleanly with unchanged runtime inputs")
    if 'driver_pid' in result:
        driver = read_artifact(result.get('interactive_ui_driver'))
        if driver.get('status') != 'INTERACTIVE_UI_DRIVER_PASS' or driver.get('returncode') != 0 or \
           driver.get('pid') != result.get('pid') or attempt.get('host_pid') != result.get('pid'):
            fail('Interactive driver and actual Host process identities/completion differ')
    if re.search(r"HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|SCRIPT_FAILURE", output + "\n" + stderr):
        fail("Interactive smoke contains a Host, native, cleanup or script failure marker")
    runtime = Path(request.get("cwd", "")).resolve(strict=True)
    if runtime != (RUNTIME_ROOT / run_id).resolve(strict=True):
        fail("Interactive request cwd differs from its exact run-specific private runtime")
    provenance = verify_provenance(request, result, runtime)

    generated_rows = result.get("generated_files")
    if not isinstance(generated_rows, list):
        fail("Interactive result has no generated-file inventory")
    generated_paths = []
    for row in generated_rows:
        check_artifacts(row)
        path = Path(row["path"]).resolve(strict=True)
        if not path.is_relative_to((runtime / "sessions").resolve(strict=True)):
            fail("Generated runtime artifact escaped the exact session tree")
        generated_paths.append(path)
    actual_paths = sorted(path.resolve() for path in (runtime / "sessions").rglob("*") if path.is_file())
    if sorted(generated_paths) != actual_paths or len(set(generated_paths)) != len(generated_paths):
        fail("Recorded generated files do not exactly cover the private interactive session tree")
    generated_map = {path.name: path for path in generated_paths}
    if len(generated_map) != len(generated_paths):
        fail("Interactive session generated duplicate basenames")

    start_rows = one_line(output, "INTERACTIVE_GAME_STARTED", r"^INTERACTIVE_GAME_STARTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$")
    selection_rows = one_line(output, "INTERACTIVE_UNIT_SELECTED", r"^INTERACTIVE_UNIT_SELECTED=(\d+)\|(\d+)\|(\d+)\|(\d+)$")
    movement_rows = one_line(output, "INTERACTIVE_SMOKE_MOVEMENT_VERIFIED", r"^INTERACTIVE_SMOKE_MOVEMENT_VERIFIED=(\d+)\|(\d+)\|(\d+)$")
    accepted_rows = one_line(output, "INTERACTIVE_MISSION_ACCEPTED", r"^INTERACTIVE_MISSION_ACCEPTED=(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$")
    next_rows = one_line(output, "INTERACTIVE_NEXT_HUMAN_TURN", r"^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$")
    closed_rows = one_line(output, "INTERACTIVE_PLAY_CLOSED", r"^INTERACTIVE_PLAY_CLOSED=(\d+)\|NATIVE_CHECKPOINT_WRITTEN$")
    if len(start_rows) != 1 or not selection_rows or len(movement_rows) != 1 or len(next_rows) != 1 or len(closed_rows) != 1:
        fail("Interactive smoke is missing unique startup, selection, movement, next-turn or close records")
    if "INTERACTIVE_SMOKE_SEQUENCE=SELECT_MOVE_EXPLICIT_SKIP_END_TURN_SAVE_WM_CLOSE" not in output or \
       "INTERACTIVE_GAME_SESSION_STOPPED=true" not in output or \
       "INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true" not in output:
        fail("Interactive smoke sequence or owned GameCore shutdown markers are incomplete")
    start_turn, active, width, height = map(int, start_rows[0])
    moved_id, target_x, target_y = map(int, movement_rows[0])
    unit_selections = [tuple(map(int, row)) for row in selection_rows if int(row[1]) == moved_id]
    if len(unit_selections) != 1:
        fail("Actual moved unit does not have exactly one original HWND selection record")
    selected_turn, unit_id, start_x, start_y = unit_selections[0]
    next_turn, update_count = map(int, next_rows[0])
    close_turn = int(closed_rows[0][0])
    if not (0 <= active < 64 and width > 0 and height > 0 and 0 <= start_x < width and 0 <= start_y < height and
            unit_id >= 0 and selected_turn == start_turn and moved_id == unit_id and
            0 <= target_x < width and 0 <= target_y < height and (target_x, target_y) != (start_x, start_y) and
            next_turn == start_turn + 1 and close_turn == next_turn and update_count > 0):
        fail("Interactive startup, exact unit move, or next-turn boundary is inconsistent")
    matching_moves = [tuple(map(int, row)) for row in accepted_rows
                      if int(row[1]) == unit_id and int(row[3]) == target_x and int(row[4]) == target_y]
    if len(matching_moves) != 1 or matching_moves[0][0] != start_turn or matching_moves[0][2] < 0:
        fail("Original SDK move mission record does not match the selected unit and actual destination")

    scenes, gpu_frames = scene_maps(result, runtime)
    first = scenes[1][0]
    if first["turn"] != start_turn or first["activePlayer"] != active or \
       (first["gridWidth"], first["gridHeight"]) != (width, height):
        fail("First captured SDK world scene differs from the actual startup marker")
    initial_units = {row.get("id"): row for row in first["units"] if isinstance(row, dict)}
    initial_unit = initial_units.get(unit_id)
    if not initial_unit or initial_unit.get("owner") != active or (initial_unit.get("x"), initial_unit.get("y")) != (start_x, start_y):
        fail("First world JSON does not contain the selected SDK unit at its logged starting coordinate")
    selected_scenes = [(number, doc, path) for number, (doc, path) in scenes.items()
                       if any(isinstance(row, dict) and row.get("id") == unit_id and row.get("selected") is True for row in doc["units"])]
    if not selected_scenes:
        fail("No captured world scene shows the exact posted unit selected")
    moved_scenes = [(number, doc, path) for number, (doc, path) in scenes.items()
                    if any(isinstance(row, dict) and row.get("id") == unit_id and
                           (row.get("x"), row.get("y")) == (target_x, target_y) for row in doc["units"])]
    if not moved_scenes:
        fail("No captured world scene shows the exact SDK unit at the mission destination")
    moved_number, moved_doc, _ = moved_scenes[0]
    moved_unit = next(row for row in moved_doc["units"] if row.get("id") == unit_id)
    if moved_unit.get("moves", 0) >= initial_unit.get("moves", 0):
        fail("SDK movement did not reduce the selected unit's remaining movement")
    final = scenes[max(scenes)][0]
    final_ids = {row.get("id") for row in final["units"] if isinstance(row, dict)}
    if final["turn"] != next_turn or final["activePlayer"] != active or final_ids != set(initial_units):
        fail("Final SDK world scene does not preserve the owner roster at exactly the next human turn")
    final_unit = next((row for row in final["units"] if row.get("id") == unit_id), None)
    if not final_unit or (final_unit.get("x"), final_unit.get("y")) != (target_x, target_y):
        fail("Exact moved unit did not remain at the destination through the next turn")
    if not any(row.get("owner") == active for row in final["units"]):
        fail("Final SDK state lacks the active human's owned unit roster")

    frames = result.get("frames", [])
    if len(frames) != len(scenes) or len(frames) < 5:
        fail("Interactive smoke did not capture every scene revision to GPU")
    device_ids = set()
    for revision, frame in enumerate(frames, start=1):
        if len(frame) != 9:
            fail("Malformed INTERACTIVE_WORLD_FRAME result row")
        marker_revision, generation, turn, unit_count, hit_count, device, presents, occluded, device_kind = frame
        doc = scenes[revision][0]
        if marker_revision != revision or generation != doc["generation"] or turn != doc["turn"] or \
           unit_count != len(doc["units"]) or hit_count != len(doc["hits"]) or device <= 0 or presents <= 0 or device_kind not in (1, 2):
            fail("GPU frame marker differs from its actual scene JSON and owned device")
        device_ids.add(device)
        if verify_png(gpu_frames[revision]) != (1280, 720):
            fail("GPU frame dimensions differ from the private window profile")
    if len(device_ids) != 1:
        fail("Interactive scene refresh replaced the owned GPU device")

    posted = [tuple(map(int, row.split("|"))) for row in one_line(output, "INTERACTIVE_SMOKE_POSTED", r"^INTERACTIVE_SMOKE_POSTED=(\d+\|\d+\|-?\d+\|-?\d+)$")]
    native_inputs = [tuple(map(int, row.split("|"))) for row in one_line(output, "INTERACTIVE_WINDOW_INPUT", r"^INTERACTIVE_WINDOW_INPUT=(\d+\|\d+\|\d+\|[01])$")]
    if len(posted) < 5 or len(posted) != len(native_inputs) or any(row[1] <= 0 for row in posted):
        fail("Posted HWND click records and native delivered input records do not pair")
    selected_post = None
    move_post = None
    for (generation, key, cx, cy), (delivered_generation, kind, delivered_key, consumed) in zip(posted, native_inputs):
        if (generation, key) != (delivered_generation, delivered_key) or kind != 1 or consumed != 1:
            fail("A posted world hit was not consumed as the exact generation-bound native click")
        matching_scenes = [doc for doc, _ in scenes.values() if doc["generation"] == generation]
        if len(matching_scenes) != 1:
            fail("Native click generation does not identify exactly one captured scene")
        doc = matching_scenes[0]
        hits = [hit for hit in doc["hits"] if isinstance(hit, list) and len(hit) == 5 and hit[0] == key]
        # PostClick uses the 16:9 full-client transform of the fixed 1280x720 window.
        logical_x, logical_y = cx * 1.5, cy * 1.5
        if len(hits) == 1:
            _, left, top, right, bottom = hits[0]
            if not (left <= logical_x < right and top <= logical_y < bottom):
                fail("Posted client coordinate is outside the retained hit region")
        elif not hits:
            scene_path = next(path for scene, path in scenes.values() if scene['generation'] == generation)
            filename = doc.get('pixelHitFile')
            if not isinstance(filename, str) or filename != scene_path.with_suffix('.pick').name:
                fail('Native 3D click has no generation-bound raster ID evidence')
            pick_path = generated(result, scene_path.with_suffix('.pick'), runtime)
            if pixel_key(pick_path, doc, logical_x, logical_y) != key:
                fail('Native 3D click differs from the captured frontmost terrain pixel ID')
            if any(h[1] <= logical_x < h[3] and h[2] <= logical_y < h[4] for h in doc['hits']):
                fail('Native 3D click bypassed an overlaid UI hit')
        else:
            fail('Posted native key is duplicated in its exact scene hit map')
        if key == (0x5A57000000000000 | (2 << 32) | (unit_id & 0xFFFFFFFF)):
            selected_post = (generation, key)
        target_plots = [plot for plot in doc["plots"] if isinstance(plot, list) and len(plot) == 5 and
                        plot[1] == target_x and plot[2] == target_y]
        if len(target_plots) != 1:
            fail("Mission destination is not a unique plot in its posted scene")
        if key == (0x5A57000000000000 | (1 << 32) | (target_plots[0][0] & 0xFFFFFFFF)):
            move_post = (generation, key)
    if selected_post is None or move_post is None:
        fail("Exact unit-selection and destination-plot hit keys were not delivered by the owned HWND")
    if not any(number > selected_post[0] for number, _, _ in selected_scenes) or \
       not any(number > move_post[0] for number, _, _ in moved_scenes):
        fail("Native unit and plot hits were not followed by the corresponding SDK scene state transitions")
    if not any(int(row[2]) != matching_moves[0][2] and int(row[3]) == -1 and int(row[4]) == -1 for row in accepted_rows):
        fail("Explicit skip sequence lacks a distinct accepted original MISSION_SKIP tuple")

    save_rows = one_line(output, "INTERACTIVE_NATIVE_SAVE", r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$")
    if len(save_rows) < 2:
        fail("Interactive close did not preserve at least two native save archives")
    manifest_rows = [row for row in request["runtime_inputs"] if Path(row["path"]).name == "bundle.manifest"]
    if len(manifest_rows) != 1:
        fail("Private runtime request does not identify one bundle manifest")
    manifest = Path(manifest_rows[0]["path"]).resolve(strict=True)
    archives = []
    for index, (turn_text, path_text) in enumerate(save_rows, start=1):
        save_path = Path(path_text).resolve(strict=True)
        if not save_path.is_relative_to((runtime / "sessions").resolve(strict=True)) or \
           generated(result, save_path, runtime) != save_path:
            fail("Interactive native save escaped its exact generated session")
        db = save_path.parent / "Civ5SavedGameDatabase.db"
        generated(result, db, runtime)
        scene = final if int(turn_text) == next_turn else first
        archive = inspect_save(save_path, manifest, db,
                               expected=(1, 0, int(turn_text), scene["elapsed"], scene["activePlayer"], 64, 64, 133))
        if archive.get("section_count") != 133 or archive.get("sdk_restore_verified") is not False:
            fail("Interactive private archive did not preserve the 133-section native envelope")
        archives.append(archive)
    if len({row["sha256"] for row in (archive["archive"] for archive in archives)}) < 1:
        fail("Interactive archive inventory is empty")

    folder = proof_dir / run_id
    folder.mkdir(parents=True, exist_ok=False)
    proof_script = folder / "verify_interactive_game.py"
    shutil.copy2(Path(__file__).resolve(), proof_script)
    frozen_rows = [artifact(proof_script)]
    for name, row in provenance["compiled_source_rows"].items():
        frozen_rows.append({"name": name, **row})
    return {
        "run_id": run_id, "status": result["status"], "language": request.get("language"), "pid": result.get("pid"),
        "startup_turn": start_turn, "active_player": active, "selected_unit": unit_id,
        "starting_coordinate": [start_x, start_y], "destination": [target_x, target_y],
        "mission_record": list(matching_moves[0]), "selected_scene_revisions": [row[0] for row in selected_scenes],
        "moved_scene_revision": moved_number, "final_turn": next_turn, "update_count": update_count,
        "native_clicks": len(native_inputs), "scene_count": len(scenes), "gpu_frames": len(frames),
        "gpu_device_identity": next(iter(device_ids)), "save_archives": archives,
        "source_provenance": provenance, "frozen_evidence": frozen_rows,
        "posted_hit_sequence_and_consumption_verified": True, "sdk_selected_movement_and_turn_verified": True,
        "native_bundle_and_133_section_archives_verified": True, "fresh_session_restore_verified": False,
        "human_input_verified": False, "retail_renderer_equivalence_verified": False,
        "full_gameplay_verified": False, "no_human_or_retail_claim": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    proof = ROOT / "validators" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12])
    proof.mkdir(parents=True, exist_ok=False)
    try:
        row = verify_run(args.run, proof)
        report = {
            "status": "INPUT_SEQUENCE_NATIVE_SDK_WORLD_AND_SAVE_PASS",
            "scope": "POSTED_HWND_INPUT_TO_ACTUAL_SDK_UNIT_SELECTION_MOVE_ONE_TURN_AND_PRIVATE_NATIVE_SAVE_ARCHIVES",
            "runs": [row], "source_provenance_verified": True,
            "native_input_scene_hit_binding_verified": True, "sdk_world_state_transition_verified": True,
            "one_normal_turn_verified": True, "native_save_bundle_and_maps_verified": True,
            "fresh_session_restore_verified": False, "human_input_verified": False,
            "retail_renderer_equivalence_verified": False, "full_gameplay_verified": False,
            "limitations": [
                "The test used synthetic posted HWND clicks, not human input.",
                "GPU frames are private strategic-view captures and do not establish Civ V retail renderer equivalence.",
                "The proof validates native save archives and embedded private database/map records; it does not claim a fresh-session restore.",
                "One private fixture turn is not evidence of complete playable-game coverage.",
            ],
        }
    except Exception as exc:
        report = {"status": "FAIL_INTERACTIVE_GAME_CONFORMANCE", "run_ids": [args.run],
                  "failure": f"{type(exc).__name__}: {exc}", "fresh_session_restore_verified": False,
                  "human_input_verified": False, "retail_renderer_equivalence_verified": False,
                  "full_gameplay_verified": False}
        out = proof / "conformance.json"
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "proof": artifact(out), "failure": report["failure"]}, ensure_ascii=False), file=sys.stderr)
        raise
    out = proof / "conformance.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "proof": artifact(out), "run_id": args.run,
                      "selected_unit": row["selected_unit"], "destination": row["destination"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
