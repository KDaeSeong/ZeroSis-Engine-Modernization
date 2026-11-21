"""Verify a city-capture checkpoint survives a fresh SDK restore and next turn.

This proof is specific to the sealed ZeroSis native-save archive and the
capture fixture. It does not claim retail-save compatibility or full gameplay.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import struct
from pathlib import Path
from typing import Any

from collect_baseline import PROJECT, digest
from verify_first_turn_candidate import inspect_save
from verify_world_builder_map_object import check_artifacts
import verify_interactive_game as base
import verify_restore_game_metadata as metadata

EVIDENCE = PROJECT / "evidence/interactive_game"
RUNTIME = PROJECT / "Build/InteractiveGameRuntime"
RUN_ID = re.compile(r"\d{8}T\d{6}Z_[0-9a-f]{12}\Z")
ARCHIVE_MAGIC = b"ZEROSIS_SAVE_V1\0"
SECTION_IDENTITIES = ([(kind, 0) for kind in range(1, 6)] +
                      [(6, index) for index in range(64)] +
                      [(7, index) for index in range(64)])
RESTORE_STATUSES = {
    "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS",
}
RESTORE_INPUT_PROFILE = "POSTED_HWND_CONTINUOUS_TREE_DECISION_UI_LOOP"


def fail(message: str) -> None:
    raise RuntimeError(message)


def checked_ref(ref: Any, expected: Path | None = None) -> Path:
    if not isinstance(ref, dict):
        fail("Missing immutable artifact reference")
    check_artifacts(ref)
    path = Path(ref["path"]).resolve(strict=True)
    if expected is not None and path != expected.resolve(strict=True):
        fail("Artifact reference differs from its exact expected path")
    return path


def read_json_ref(ref: Any, expected: Path | None = None) -> dict:
    path = checked_ref(ref, expected)
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail("Immutable JSON artifact is not an object")
    return value


def exact_ref(result: dict, key: str, path: Path) -> Path:
    return checked_ref(result.get(key), path)


def run_pair(run_id: str) -> tuple[Path, dict, dict, dict, str, str]:
    if not RUN_ID.fullmatch(run_id):
        fail(f"Invalid run identity: {run_id}")
    evidence = EVIDENCE / run_id
    request_path, result_path = evidence / "request.json", evidence / "result.json"
    request = json.loads(request_path.read_text(encoding="utf-8"))
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if request.get("run_id") != run_id or result.get("run_id") != run_id:
        fail("Request/result run ID differs from evidence directory")
    check_artifacts(request)
    check_artifacts(result)
    exact_ref(result, "request", request_path)
    stdout_path = exact_ref(result, "stdout", evidence / "stdout.log")
    stderr_path = exact_ref(result, "stderr", evidence / "stderr.log")
    return evidence, request, result, read_json_ref(result.get("attempt"), evidence / "attempt.json"), \
        stdout_path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n"), \
        stderr_path.read_text(encoding="utf-8", errors="replace")


def marker_rows(text: str, name: str, pattern: str, marker_prefix: str | None = None) -> list[tuple[str, ...]]:
    marker_match = re.match(r"\^([A-Z][A-Z0-9_]*)=", pattern)
    if marker_match is None:
        fail(f"Verifier has no exact marker prefix for {name}")
    marker = marker_prefix or (marker_match.group(1) + "=")
    candidates = [line for line in text.splitlines() if line.startswith(marker)]
    if not candidates:
        fail(f"Missing or malformed {name} marker")
    rows: list[tuple[str, ...]] = []
    for line in candidates:
        match = re.fullmatch(pattern, line)
        if match is None:
            fail(f"Malformed {name} marker")
        rows.append(tuple(match.groups()))
    return rows


def generated_inventory(result: dict, runtime: Path) -> dict[str, list[Path]]:
    rows = result.get("generated_files")
    if not isinstance(rows, list):
        fail("Runner result omits generated-file inventory")
    paths: list[Path] = []
    for row in rows:
        paths.append(checked_ref(row))
    session_root = (runtime / "sessions").resolve(strict=True)
    if any(not path.is_relative_to(session_root) for path in paths):
        fail("Generated artifact escaped its private session tree")
    actual = sorted(path.resolve() for path in session_root.rglob("*") if path.is_file())
    if sorted(paths) != actual or len(paths) != len(set(paths)):
        fail("Generated artifact inventory is incomplete or contains duplicates")
    named: dict[str, list[Path]] = {}
    for path in paths:
        named.setdefault(path.name, []).append(path)
    return named


def runtime_inputs(request: dict, runtime: Path) -> dict[str, dict]:
    rows = request.get("runtime_inputs")
    if not isinstance(rows, list) or not rows:
        fail("Request lacks its frozen runtime-input manifest")
    by_name: dict[str, dict] = {}
    for row in rows:
        path = checked_ref(row)
        if path.parent != runtime.resolve(strict=True) or path.name in by_name:
            fail("Runtime input is duplicate or outside its isolated runtime")
        if digest(path) != row.get("sha256"):
            fail(f"Runtime input hash differs: {path.name}")
        by_name[path.name] = row
    required = {"ZeroSisHost_x64.exe", "CvGameCoreDLL_Expansion2_x64.dll", "bundle.manifest"}
    if not required <= by_name.keys():
        fail("Runtime input manifest omits Host, SDK, or bundle")
    return by_name


def immutable_result(result: dict, attempt: dict, request: dict, stdout: str, stderr: str,
                     *, capture: bool) -> None:
    if result.get("returncode") != 0 or result.get("timed_out") is not False or \
       result.get("runtime_inputs_unchanged") is not True or attempt.get("status") != "FINISHED" or \
       attempt.get("returncode") != 0 or attempt.get("timed_out") is not False or \
       attempt.get("host_pid") != result.get("pid") or attempt.get("pid") != result.get("driver_pid"):
        fail("Runner or immutable attempt record does not prove a clean completed process")
    if re.search(r"HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|SCRIPT_FAILURE", stdout + "\n" + stderr):
        fail("Process output contains a Host, native, cleanup, or script failure")
    if request.get("smoke") is not True or request.get("stage_or_mods_changed") is not False:
        fail("Run was not a smoke in its isolated no-stage/no-MODS scope")
    if capture:
        if result.get("status") != "CONTINUOUS_INTERACTIVE_SDK_CITY_CAPTURE_SMOKE_PASS" or \
           request.get("city_capture_smoke") is not True or request.get("input_profile") != "POSTED_HWND_CITY_CAPTURE_SMOKE" or \
           result.get("city_capture_smoke_requested") is not True or result.get("city_capture_sequence_verified") is not True or \
           result.get("native_window_posted_input_verified") is not True:
            fail("Source run is not an actual passing city-capture runner result")
        city = result.get("city_capture_evidence")
        leader = city.get("leader_diplomacy") if isinstance(city, dict) else None
        if not isinstance(city, dict) or city.get("verified") is not True or not isinstance(leader, dict) or \
           leader.get("leader_3d_equivalence_verified") is not False:
            fail("Source result lacks its explicit verified capture evidence and retail-3D boundary")
    else:
        if result.get("status") not in RESTORE_STATUSES or request.get("input_profile") != RESTORE_INPUT_PROFILE or \
           request.get("decisions") is not True or request.get("research_tree") is not True or \
           request.get("city_capture_smoke") is not False or \
           result.get("fresh_process_restore_verified") is not True or result.get("semantic_restore_equal") is not True or \
           result.get("checkpoint_input_unchanged") is not True or result.get("native_window_posted_input_verified") is not True:
            fail("Restore runner status or result flags do not prove a fresh-process checkpoint continuation")


def runtime_for(request: dict, run_id: str) -> Path:
    runtime = Path(request.get("cwd", "")).resolve(strict=True)
    if runtime != (RUNTIME / run_id).resolve(strict=True):
        fail("Run cwd is not its exact isolated runtime")
    return runtime


def driver_command(request: dict, result: dict, evidence: Path, runtime: Path,
                   checkpoint: Path | None = None) -> list[str]:
    driver = read_json_ref(result.get("interactive_ui_driver"), evidence / "driver_result.json")
    support = read_json_ref(request.get("interactive_ui_support"), evidence / "interactive_ui_support.json")
    support_root = runtime / "interactive_ui_support"
    driver_path = checked_ref(support["tools"]["interactive_ui_driver.py"]["frozen"],
                              support_root / "tools/interactive_ui_driver.py")
    python = checked_ref(support["python"])
    manifest = checked_ref(support["frozen_support_manifest"], support_root / "support_manifest.json")
    mode = "play-load-smoke" if checkpoint else "play-smoke"
    expected = [str(python), "-B", "-X", "utf8", str(driver_path),
                "--host", str(runtime / "ZeroSisHost_x64.exe"), "--cwd", str(runtime),
                "--runtime", str(runtime), "--tools", str(support_root / "tools"),
                "--icons", str(support_root / "assets/inline_icons.json"),
                "--support-manifest", str(manifest), "--support-manifest-sha256", digest(manifest),
                "--report", str(evidence / "driver_result.json"), "--language", request["language"],
                "--mode", mode, "--timeout", str(request["timeout"]), "--scene-timeout", "60"]
    host_command = [str(runtime / "ZeroSisHost_x64.exe"), "--" + mode, request["language"]]
    if checkpoint:
        expected.extend(["--checkpoint", str(checkpoint)])
        host_command.append(str(checkpoint))
    if request.get("command") != expected or driver.get("command") != host_command or \
       driver.get("cwd") != str(runtime) or driver.get("runtime") != str(runtime) or \
       driver.get("status") != "INTERACTIVE_UI_DRIVER_PASS" or driver.get("returncode") != 0 or \
       driver.get("pid") != result.get("pid") or driver.get("error") is not None or \
       result.get("interactive_ui_support_unchanged") is not True:
        fail("Frozen UI driver/Host invocation or result differs from the exact private runtime command")
    return host_command


def same_provenance(source_request: dict, restore_request: dict,
                    source_runtime: Path, restore_runtime: Path) -> dict[str, str]:
    left, right = runtime_inputs(source_request, source_runtime), runtime_inputs(restore_request, restore_runtime)
    for name in ("ZeroSisHost_x64.exe", "CvGameCoreDLL_Expansion2_x64.dll", "bundle.manifest",
                 "ZeroSisLua51_x64.dll", "ZeroSisDatabase_x64.dll", "ZeroSisLocalization_x64.dll"):
        if name not in left or name not in right or left[name]["sha256"] != right[name]["sha256"]:
            fail(f"Capture and restore do not share identical sealed runtime input: {name}")
    return {"host_executable_sha256": left["ZeroSisHost_x64.exe"]["sha256"],
            "gamecore_sha256": left["CvGameCoreDLL_Expansion2_x64.dll"]["sha256"],
            "bundle_manifest_sha256": left["bundle.manifest"]["sha256"]}


def exact_generated(result: dict, named: dict[str, list[Path]], runtime: Path, filename: str) -> Path:
    matches = named.get(filename, [])
    if len(matches) != 1:
        fail(f"Expected exactly one generated artifact named {filename}")
    path = matches[0]
    if not path.is_relative_to((runtime / "sessions").resolve(strict=True)):
        fail(f"Expected generated artifact is absent from private session: {filename}")
    return path


def state_identity(data: bytes) -> tuple[int, int, int, int]:
    try:
        fields = data.decode("utf-8", errors="strict").splitlines()[0].split("|")
        if len(fields) != 5 or fields[0] != "G":
            raise ValueError
        turn, elapsed, active, plots = map(int, fields[1:])
    except (UnicodeDecodeError, IndexError, ValueError) as exc:
        raise RuntimeError("Semantic SDK state lacks a valid Game identity row") from exc
    if min(turn, elapsed, plots) < 0 or not 0 <= active < 64:
        fail("Semantic Game identity is outside native limits")
    return turn, elapsed, active, plots


def governance(text: str, phase: str) -> list[tuple[int, ...]]:
    rows = marker_rows(text, f"city governance {phase}",
                       r"^INTERACTIVE_CITY_GOVERNANCE=" + re.escape(phase) + r"\|([^\r\n]+)$",
                       marker_prefix=f"INTERACTIVE_CITY_GOVERNANCE={phase}|")
    parsed: list[tuple[int, ...]] = []
    for (tail,) in rows:
        fields = tail.split("|")
        if len(fields) != 11:
            fail(f"{phase} city governance row does not have all 12 fields")
        try:
            row = tuple(map(int, fields))
        except ValueError as exc:
            raise RuntimeError(f"Malformed {phase} city governance integer") from exc
        player, city_id, owner, x, y, puppet, razing, original_owner, capital_id, city_count, alive = row
        if not (0 <= player < 64 and city_id >= 0 and 0 <= owner < 64 and
                -1 <= original_owner < 64 and capital_id >= -1 and city_count >= 0 and
                puppet in (0, 1) and razing in (0, 1) and alive in (0, 1)):
            fail(f"{phase} city governance row has invalid native values")
        if owner != player:
            fail(f"{phase} iterator player does not own enumerated city {city_id}")
        parsed.append(row)
    count_rows = marker_rows(text, f"city governance count {phase}",
                             r"^INTERACTIVE_CITY_GOVERNANCE_COUNT=" + re.escape(phase) + r"\|(\d+)$",
                             marker_prefix=f"INTERACTIVE_CITY_GOVERNANCE_COUNT={phase}|")
    if len(count_rows) != 1 or int(count_rows[0][0]) != len(parsed) or not parsed:
        fail(f"{phase} city governance count does not match enumerated rows")
    identities = [(row[0], row[1]) for row in parsed]
    if len(set(identities)) != len(identities):
        fail(f"{phase} city governance contains duplicate player/city identities")
    return parsed


def governance_match(source_final: list[tuple[int, ...]], restore_initial: list[tuple[int, ...]]) -> None:
    if sorted(source_final) != sorted(restore_initial):
        fail("Source final city governance differs from fresh restore initial governance")


def fixture_capture(stdout: str) -> tuple[int, int, int, int, int, int]:
    rows = marker_rows(stdout, "city capture fixture",
                       r"^INTERACTIVE_CITY_CAPTURE_FIXTURE=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$")
    if len(rows) != 1:
        fail("Capture source does not contain exactly one city fixture marker")
    return tuple(map(int, rows[0]))


def capture_proof(stdout: str, source_final: list[tuple[int, ...]], restore_initial: list[tuple[int, ...]],
                  restore_final: list[tuple[int, ...]]) -> dict[str, Any]:
    fixtures = fixture_capture(stdout)
    attacker, _unit, defender, _old_city, _x, _y = fixtures
    capitals = marker_rows(stdout, "city capture capital",
                           r"^INTERACTIVE_CITY_CAPTURE_CAPITAL=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$")
    verified = marker_rows(stdout, "city capture verified",
                           r"^INTERACTIVE_CITY_CAPTURE_VERIFIED=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$")
    if len(capitals) != 1 or len(verified) != 1:
        fail("Capture source lacks unique capital and ownership verification markers")
    cap_owner, capital_id, before_count, declared_war, created, met = map(int, capitals[0])
    own, new_city_id, puppet, razing, original_owner = map(int, verified[0])
    if cap_owner != defender or own != attacker or puppet != 1 or razing != 0 or original_owner != defender or \
       declared_war != 1 or created not in (0, 1) or met != 1 or before_count < 1:
        fail("Fixture did not capture the target city as puppet while retaining the defender capital")
    if attacker == defender or capital_id == _old_city or capital_id < 0:
        fail("Captured city fixture identities are inconsistent")
    all_phases = {"source-final": source_final, "restore-initial": restore_initial, "restore-final": restore_final}
    for phase, rows in all_phases.items():
        by_identity = {(row[0], row[1]): row for row in rows}
        captured = by_identity.get((attacker, new_city_id))
        capital = by_identity.get((defender, capital_id))
        if captured is None or captured[3:5] != (_x, _y) or captured[5] != 1 or captured[6] != 0 or captured[7] != defender or captured[10] != 1:
            fail(f"{phase} governance does not preserve captured city as defender-origin puppet")
        if capital is None or capital[2] != defender or capital[8] != capital_id or capital[10] != 1:
            fail(f"{phase} governance does not preserve defender's original live capital")
        defender_rows = [row for row in rows if row[0] == defender]
        if len(defender_rows) != before_count or \
           not all(row[9] == before_count and row[10] == 1 for row in defender_rows) or \
           not any(row[1] == capital_id for row in defender_rows):
            fail(f"{phase} governance does not retain defender ownership and alive status")
    if not any(row[0] == attacker and row[1] == new_city_id for row in restore_initial):
        fail("Restored initial state omits the captured city")
    return {"attacker": attacker, "defender": defender, "captured_city": new_city_id,
            "defender_capital": capital_id, "defender_cities_before": before_count,
            "capital_founded_for_fixture": bool(created),
            "captured_city_puppet_preserved": True, "original_capital_preserved": True}


def database_integrity(path: Path) -> None:
    with sqlite3.connect(":memory:") as db:
        db.deserialize(path.read_bytes())
        if db.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            fail(f"Saved-game database integrity check failed: {path.name}")


def archive(path: Path, manifest: Path, database: Path, identity: tuple[int, int, int, int]) -> dict:
    turn, elapsed, active, _plots = identity
    value = inspect_save(path, manifest, database,
                         expected=(1, 0, turn, elapsed, active, 64, 64, 133))
    if value.get("section_count") != 133 or len(value.get("sections", [])) != 133:
        fail("Native save does not contain the complete 133-section archive")
    database_integrity(database)
    return value


def enum_value(name: str, request: dict) -> tuple[int, dict[str, str]]:
    provenance = request.get("provenance")
    if not isinstance(provenance, dict) or not isinstance(provenance.get("city_site_sdk_build"), dict):
        fail("Capture request lacks frozen SDK build provenance for ReplayMessageTypes")
    build_ref = provenance["city_site_sdk_build"]
    build = read_json_ref(build_ref)
    dependencies = build.get("source_dependency_inputs")
    if not isinstance(dependencies, list):
        fail("Frozen SDK build report omits compiler dependency hashes")
    candidates = [row for row in dependencies if str(row.get("path", "")).replace("\\", "/").lower().endswith("/cvgamecoredllutil/include/cvenums.h")]
    hashes = {(row.get("sha256_after_compile"), row.get("sha256_after_link")) for row in candidates}
    if not candidates or len(hashes) != 1 or None in next(iter(hashes)) or \
       next(iter(hashes))[0] != next(iter(hashes))[1]:
        fail("Frozen SDK build provenance does not uniquely identify CvEnums.h")
    header_hash = next(iter(hashes))[0]
    header_paths = {os.path.normcase(os.path.abspath(row["path"])) for row in candidates}
    if len(header_paths) != 1:
        fail("SDK dependency manifest maps CvEnums.h to multiple source paths")
    header_path = next(iter(header_paths))
    expected_path = PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h"
    expected_header = os.path.normcase(os.path.abspath(str(expected_path)))
    path = Path(header_path)
    if header_path != expected_header or digest(path) != header_hash:
        fail("Current CvEnums.h is not byte-identical to the header recorded during the sealed SDK build")
    text = path.read_text(encoding="utf-8", errors="strict")
    match = re.search(r"\benum\s+ReplayMessageTypes\s*\{([^}]+)\}", text, re.S)
    if not match:
        fail("SDK ReplayMessageTypes enum is unavailable for exact reload proof")
    items = [part.strip() for part in match.group(1).split(",") if part.strip()]
    value = -1
    for item in items:
        item_match = re.fullmatch(r"(\w+)(?:\s*=\s*(-?\d+))?", item)
        if not item_match:
            fail("SDK ReplayMessageTypes enum has an unsupported expression")
        value = int(item_match.group(2)) if item_match.group(2) else value + 1
        if item_match.group(1) == name:
            return value, {"path": header_path, "sha256": header_hash,
                           "sdk_build_report": str(build_ref["path"]),
                           "sdk_build_report_sha256": str(build_ref["sha256"])}
    fail(f"SDK enum lacks {name}")


def expected_reload_text(language: str, localization_db: Path, session: int) -> tuple[str, str]:
    templates = {"en_US": "Session {1_number} starts",
                 "ko_KR": "세션 {1_number}{1: plural 1?이; 2?가;} 시작됐습니다."}
    template = templates.get(language)
    if template is None:
        fail("Reload verifier supports only the sealed en_US/ko_KR localization templates")
    uri = localization_db.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        rows = db.execute('SELECT "Text" FROM LocalizedText WHERE "Language"=? AND "Tag"=?',
                          (language, "TXT_KEY_MISC_RELOAD")).fetchall()
    if rows != [(template,)]:
        fail("Canonical TXT_KEY_MISC_RELOAD template differs from the supported source localization")
    if language == "en_US":
        formatted = f"Session {session} starts"
    else:
        suffix = "이" if session == 1 else "가"
        formatted = f"세션 {session}{suffix} 시작됐습니다."
    return template, formatted


def verify_reload(checkpoint: Path, restored: Path, language: str, localization_db: Path,
                  sdk_request: dict, turn: int, elapsed: int, active: int, plots: int) -> dict:
    before_header, before_sections = metadata._archive(checkpoint)
    after_header, after_sections = metadata._archive(restored)
    expected_header = {"flags": 0, "turn": turn, "elapsed": elapsed, "active_player": active}
    if before_header != expected_header or after_header != expected_header or \
       before_sections.keys() != after_sections.keys() or len(before_sections) != 133:
        fail("Checkpoint/restore archive header or section identities differ")
    changed = [identity for identity in SECTION_IDENTITIES if before_sections[identity] != after_sections[identity]]
    if changed != [(3, 0)]:
        fail(f"Only SDK Game section (3,0) may change during reload; observed {changed}")
    before, after = before_sections[(3, 0)], after_sections[(3, 0)]
    common = min(len(before), len(after))
    first = next((index for index in range(common) if before[index] != after[index]), None)
    if first is None or first < 4 or metadata._i32(before, first - 4) != metadata.REPLAY_MESSAGE_VERSION or \
       before[:first] != after[:first]:
        fail("Game section first difference is not the versioned replay count after identical prefix")
    count_before, count_after = metadata._i32(before, first), metadata._i32(after, first)
    if count_before < 0 or count_after != count_before + 1:
        fail("Restore did not append exactly one replay message")
    old_cursor = new_cursor = first + 4
    for _ in range(count_before):
        old_next, _ = metadata._replay_message(before, old_cursor)
        new_next, _ = metadata._replay_message(after, new_cursor)
        if before[old_cursor:old_next] != after[new_cursor:new_next]:
            fail("A pre-existing replay message changed during restore")
        old_cursor, new_cursor = old_next, new_next
    new_cursor, appended = metadata._replay_message(after, new_cursor)
    session_before = metadata._i32(before, old_cursor)
    session_after = metadata._i32(after, new_cursor)
    template, formatted = expected_reload_text(language, localization_db, session_after)
    if session_after != session_before + 1:
        fail("CvGame session counter did not increment exactly once")
    replay_type, sdk_enum = enum_value("REPLAY_MESSAGE_MAJOR_EVENT", sdk_request)
    if (appended["turn"], appended["type"], appended["plots"], appended["player"], appended["text"]) != \
       (turn, replay_type, [(-1, -1)], active, formatted):
        fail("Appended replay message is not the exact localized SDK reload event")
    if before[old_cursor + 4:] != after[new_cursor + 4:]:
        fail("Unexpected Game-section suffix changed after reload session counter")
    return {"changed_sections": [list(item) for item in changed], "section_count": 133,
            "replay_count_before": count_before, "replay_count_after": count_after,
            "sessions_before": session_before, "sessions_after": session_after,
            "reload_text": appended["text"], "reload_template": template,
            "replay_enum_source": sdk_enum,
            "existing_replay_messages_byte_identical": True}


def verify(capture_id: str, restore_id: str) -> dict:
    if capture_id == restore_id:
        fail("Capture and restore must be distinct fresh processes")
    ce, crq, cres, catt, cout, cerr = run_pair(capture_id)
    restore_evidence, rrq, rres, ratt, rout, rerr = run_pair(restore_id)
    immutable_result(cres, catt, crq, cout, cerr, capture=True)
    immutable_result(rres, ratt, rrq, rout, rerr, capture=False)
    if cres.get("pid") == rres.get("pid") or cres.get("driver_pid") == rres.get("driver_pid") or \
       crq.get("language") != rrq.get("language"):
        fail("Capture and restore must use distinct Host/driver processes and the same language")
    source_runtime, restore_runtime = runtime_for(crq, capture_id), runtime_for(rrq, restore_id)
    driver_command(crq, cres, ce, source_runtime)
    provenance = same_provenance(crq, rrq, source_runtime, restore_runtime)
    # This shared helper's input profile applies to the restore run. Its
    # sealed Host/Core/provider chain also binds the capture's identical bytes.
    provenance["restore_compiled_inputs"] = base.verify_provenance(
        rrq, rres, restore_runtime, expected_input_profile=RESTORE_INPUT_PROFILE)
    source_inputs = runtime_inputs(crq, source_runtime)
    restore_inputs = runtime_inputs(rrq, restore_runtime)
    manifest_source = Path(source_inputs["bundle.manifest"]["path"]).resolve(strict=True)
    manifest_restore = Path(restore_inputs["bundle.manifest"]["path"]).resolve(strict=True)

    source_named = generated_inventory(cres, source_runtime)
    restore_named = generated_inventory(rres, restore_runtime)
    source_saves = marker_rows(cout, "source native saves", r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$")
    if len(source_saves) < 2:
        fail("Capture source did not write the expected initial and final native checkpoints")
    source_turn, source_save_text = int(source_saves[-1][0]), source_saves[-1][1]
    source_save = Path(source_save_text).resolve(strict=True)
    if source_save.name != "play-save-2-turn-" + str(source_turn) + ".zssave":
        fail("Final capture checkpoint is not the final ordered native save")
    source_runtime_root = (source_runtime / "sessions").resolve(strict=True)
    if not source_save.is_relative_to(source_runtime_root):
        fail("Source final native save escaped its private session")
    if source_save not in source_named.get(source_save.name, []):
        fail("Source final native save is absent from immutable generated-file inventory")
    source_final_state = exact_generated(cres, source_named, source_runtime, "play-final-state.txt")
    source_db = source_save.parent / "Civ5SavedGameDatabase.db"
    if source_db.resolve(strict=True) not in source_named.get(source_db.name, []):
        fail("Source native save embedded database is absent from generated inventory")
    if source_final_state.parent != source_save.parent:
        fail("Source final semantic state and native save are not from one SDK session")
    final_state = source_final_state.read_bytes()
    identity = state_identity(final_state)
    if identity[0] != source_turn:
        fail("Source final SDK state turn differs from native save marker")
    source_archive = archive(source_save, manifest_source, source_db, identity)

    resume = rrq.get("resume_from")
    if not isinstance(resume, dict):
        fail("Restore request lacks its frozen checkpoint binding")
    command = driver_command(rrq, rres, restore_evidence, restore_runtime,
                             checked_ref(resume.get("checkpoint_input")))
    if not isinstance(resume, dict) or resume.get("run_id") != capture_id or not isinstance(command, list) or \
       len(command) != 4 or Path(command[0]).resolve() != (restore_runtime / "ZeroSisHost_x64.exe").resolve() or \
       command[1] != "--play-load-smoke" or command[2] != rrq.get("language") or \
       Path(command[3]).resolve() != Path(resume.get("checkpoint_input", {}).get("path", "")).resolve():
        fail("Restore request does not launch the exact source checkpoint in a fresh Host process")
    frozen_source_result = checked_ref(resume.get("run_result"), restore_evidence / "resume-source-result.json")
    source_result_path = (ce / "result.json").resolve(strict=True)
    if frozen_source_result.read_bytes() != source_result_path.read_bytes():
        fail("Restore request's frozen source result differs from original capture result bytes")
    checkpoint_source = checked_ref(resume.get("checkpoint_source"), source_save)
    checkpoint_input = checked_ref(resume.get("checkpoint_input"))
    if not checkpoint_input.is_relative_to(restore_runtime) or checkpoint_input == checkpoint_source or \
       checkpoint_input.read_bytes() != source_save.read_bytes() or digest(checkpoint_input) != resume["checkpoint_input"].get("sha256"):
        fail("Restore checkpoint input is not an exact private copy of the source final save")
    if digest(checkpoint_source) != resume["checkpoint_source"].get("sha256"):
        fail("Immutable source checkpoint hash changed")
    restore_marker = marker_rows(rout, "restore checkpoint path", r"^INTERACTIVE_RESTORE_CHECKPOINT=(.+)$")
    if len(restore_marker) != 1 or Path(restore_marker[0][0]).resolve(strict=True) != checkpoint_input:
        fail("Host restored a different checkpoint than the immutable posted input")
    base.generated(cres, source_save, source_runtime)

    source_governance = governance(cout, "final")
    restore_governance_initial = governance(rout, "initial")
    restore_governance_final = governance(rout, "final")
    governance_match(source_governance, restore_governance_initial)
    initial_state = exact_generated(rres, restore_named, restore_runtime, "play-initial-state.txt").read_bytes()
    if initial_state != final_state:
        fail("Fresh restore initial semantic SDK snapshot differs byte-for-byte from source final state")
    restored_state_path = exact_generated(rres, restore_named, restore_runtime, "play-final-state.txt")
    restored_state = restored_state_path.read_bytes()
    restored_identity = state_identity(restored_state)
    if restored_identity != (identity[0] + 1, identity[1] + 1, identity[2], identity[3]):
        fail("Restored process did not preserve the capture world and advance one normal human turn")
    next_turn_rows = marker_rows(rout, "next human turn", r"^INTERACTIVE_NEXT_HUMAN_TURN=(\d+)\|(\d+)$")
    if not any(int(turn) == identity[0] + 1 and int(updates) > 0 for turn, updates in next_turn_rows):
        fail("Fresh restore did not log an actual next human turn with SDK updates")
    capture = capture_proof(cout, source_governance, restore_governance_initial, restore_governance_final)

    source_copy = checked_ref(resume.get("checkpoint_source"), source_save)
    source_db_copy = source_copy.parent / "Civ5SavedGameDatabase.db"
    input_db = checkpoint_input.parent / "Civ5SavedGameDatabase.db"
    if not source_db_copy.is_file():
        fail("Source final save's immutable sidecar database is missing")
    # The native format embeds the SDK saved-game DB in section (3,0). The
    # isolated checkpoint input is a single copied save; its authoritative DB
    # sidecar remains the source session's generated immutable artifact.
    if input_db.exists():
        fail("Checkpoint materialization unexpectedly added a saved-game DB sidecar")
    input_database = source_db
    source_copy_archive = archive(source_copy, manifest_source, source_db_copy, identity)
    input_archive = archive(checkpoint_input, manifest_restore, input_database, identity)
    if source_archive["sections"] != source_copy_archive["sections"] or source_archive["sections"] != input_archive["sections"]:
        fail("Final source, immutable copy, and checkpoint input do not contain identical 133 native sections")
    restored_save = exact_generated(rres, restore_named, restore_runtime, "play-restored-checkpoint.zssave")
    restored_db = restored_save.parent / "Civ5SavedGameDatabase.db"
    if restored_db.resolve(strict=True) not in restore_named.get(restored_db.name, []):
        fail("Restored native save sidecar DB is not included in generated inventory")
    restored_archive = archive(restored_save, manifest_restore, restored_db, identity)
    reload = verify_reload(checkpoint_input, restored_save, rrq.get("language", ""),
                           Path(restore_inputs["localization.db"]["path"]).resolve(strict=True),
                           crq, *identity)
    sections_before = {(row["kind"], row["index"]): row["sha256"] for row in input_archive["sections"]}
    sections_after = {(row["kind"], row["index"]): row["sha256"] for row in restored_archive["sections"]}
    if sections_before.keys() != sections_after.keys():
        fail("Restored archive lost native sections")
    changed = [key for key in SECTION_IDENTITIES if sections_before[key] != sections_after[key]]
    if changed != [(3, 0)] or int(rout.count("INTERACTIVE_RESTORE_SECTION_CHANGED=3|0")) != 1 or \
       "INTERACTIVE_RESTORE_SECTIONS_EQUAL=132|133" not in rout:
        fail("Runtime/native archive does not prove exactly one Game-section difference and 132 identical sections")
    if f"INTERACTIVE_RESTORE_IDENTITY={identity[0]}|{identity[1]}|{identity[2]}|133" not in rout or \
       "INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=true" not in rout:
        fail("Restore runtime identity or idle-state preservation marker differs from source checkpoint")

    close = marker_rows(rout, "play close", r"^INTERACTIVE_PLAY_CLOSED=(\d+)\|NATIVE_CHECKPOINT_WRITTEN$")
    saves = marker_rows(rout, "restore native saves", r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$")
    if not any(int(turn) == restored_identity[0] for turn, in close) or not any(int(turn) == restored_identity[0] for turn, _ in saves):
        fail("Restored process did not close and save its next-turn checkpoint")
    final_turn, final_save_text = int(saves[-1][0]), saves[-1][1]
    final_save = Path(final_save_text).resolve(strict=True)
    if final_turn != restored_identity[0] or final_save.name != f"play-save-2-turn-{final_turn}.zssave" or \
       final_save not in restore_named.get(final_save.name, []) or final_save.parent != restored_state_path.parent:
        fail("Restored final native save is absent, out of order, or from a different SDK session")
    final_save_archive = archive(final_save, manifest_restore,
                                 final_save.parent / "Civ5SavedGameDatabase.db", restored_identity)
    for line in ("INTERACTIVE_UI_ROUTER_STOPPED=true", "INTERACTIVE_GAME_SESSION_STOPPED=true",
                 "INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true"):
        if rout.splitlines().count(line) != 1:
            fail(f"Restored process cleanup/unload marker is missing or duplicated: {line}")
    if re.search(r"HOST_CLEANUP_PENDING|GAMECORE_UNLOAD_FAILED", rout + "\n" + rerr):
        fail("Restored process reports incomplete SDK cleanup or GameCore unload")

    return {"status": "CITY_CAPTURE_FRESH_RESTORE_ROUNDTRIP_PASS", "capture_run": capture_id,
            "restore_run": restore_id, "capture_pid": cres["pid"], "restore_pid": rres["pid"],
            "distinct_fresh_processes": True, "provenance": provenance,
            "source_turn": identity[0], "restored_turn": restored_identity[0],
            "checkpoint_sha256": digest(source_save), "checkpoint_input_sha256": digest(checkpoint_input),
            "checkpoint_bytes_identical": True, "section_count": 133,
            "restore_section_changes": [list(item) for item in changed],
            "identical_section_count": 132, "reload": reload, "city_governance_equal": True,
            "capture": capture, "next_turn_and_save_verified": True,
            "gamecore_unloaded": True, "retail_save_compatibility_verified": False,
            "retail_renderer_equivalence_verified": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_id")
    parser.add_argument("restore_id")
    args = parser.parse_args()
    report = verify(args.capture_id, args.restore_id)
    report["validator_sha256"] = digest(Path(__file__).resolve())
    print(json.dumps(report, ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, sqlite3.Error) as exc:
        raise SystemExit(f"CITY_CAPTURE_RESTORE_VERIFY_FAILED: {exc}") from exc
