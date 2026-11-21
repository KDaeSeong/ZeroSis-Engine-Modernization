"""Independently verify continuous original production/research UI decisions."""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import hashlib
import struct
import sqlite3
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
SAVE_MAGIC = b"ZEROSIS_SAVE_V1\0"


def parse_native_archive(path: Path) -> tuple[dict, dict[tuple[int, int], bytes]]:
    raw = path.read_bytes()
    require(len(raw) >= 80 and raw[:16] == SAVE_MAGIC, f"Invalid native archive envelope: {path}")
    end = len(raw) - 32
    require(hashlib.sha256(raw[:end]).digest() == raw[end:], f"Native archive checksum mismatch: {path}")
    version, flags, turn, elapsed, active, teams, players, count = struct.unpack_from("<8I", raw, 16)
    require((version, teams, players, count) == (1, 64, 64, 133), f"Native archive header differs: {path}")
    expected = [(kind, 0) for kind in range(1, 6)] + [(6, slot) for slot in range(64)] + [(7, slot) for slot in range(64)]
    sections: dict[tuple[int, int], bytes] = {}
    offset = 48
    for ident in expected:
        require(offset + 12 <= end, f"Truncated native section header: {path}")
        kind, slot, size = struct.unpack_from("<3I", raw, offset); offset += 12
        require((kind, slot) == ident and 0 < size <= end - offset, f"Native section identity/size differs: {path}")
        sections[ident] = raw[offset:offset + size]; offset += size
    require(offset == end, f"Native archive has unparsed trailing bytes: {path}")
    return {"version": version, "flags": flags, "turn": turn, "elapsed": elapsed,
            "active_player": active, "teams": teams, "players": players, "section_count": count,
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}, sections


def read_i32(data: bytes, offset: int) -> int:
    require(0 <= offset and offset + 4 <= len(data), "Truncated serialized CvGame integer")
    return struct.unpack_from("<i", data, offset)[0]


def parse_replay(data: bytes, offset: int) -> tuple[int, dict]:
    start = offset
    turn, kind, plot_count = (read_i32(data, offset + n) for n in (0, 4, 8)); offset += 12
    require(0 <= plot_count <= 4096, "Serialized replay plot count exceeds parser bound")
    require(offset + plot_count * 4 + 8 <= len(data), "Serialized replay plots are truncated")
    plots = [struct.unpack_from("<hh", data, offset + i * 4) for i in range(plot_count)]
    offset += plot_count * 4
    player, text_size = read_i32(data, offset), read_i32(data, offset + 4); offset += 8
    require(0 <= text_size <= len(data) - offset, "Serialized replay text length is invalid")
    text_bytes = data[offset:offset + text_size]
    text = text_bytes.decode("utf-8", errors="strict"); offset += text_size
    return offset, {"start": start, "turn": turn, "type": kind, "plots": plots,
                    "player": player, "text": text, "text_bytes": text_bytes}


def verify_reload_archive_delta(source_path: Path, restored_path: Path, language: str, marker_output: str) -> dict:
    source_header, source_sections = parse_native_archive(source_path)
    restored_header, restored_sections = parse_native_archive(restored_path)
    require(source_sections.keys() == restored_sections.keys() and len(source_sections) == 133,
            "Source/restored native section identities differ")
    require({k: v for k, v in source_header.items() if k not in ("sha256", "bytes")} ==
            {k: v for k, v in restored_header.items() if k not in ("sha256", "bytes")},
            "Reload changed native archive header identity")
    changed = [key for key in source_sections if source_sections[key] != restored_sections[key]]
    require(changed == [(3, 0)], f"Reload changed unexpected native sections: {changed}")
    before, after = source_sections[(3, 0)], restored_sections[(3, 0)]
    common = min(len(before), len(after))
    first = next((i for i in range(common) if before[i] != after[i]), None)
    require(first is not None and first >= 4 and read_i32(before, first - 4) == read_i32(after, first - 4) and
            read_i32(before, first - 4) >= 1 and before[:first] == after[:first],
            "Game section differs before a shared replay-version/count boundary")
    replay_version = read_i32(before, first - 4)
    old_count, new_count = read_i32(before, first), read_i32(after, first)
    require(new_count == old_count + 1 and 0 <= old_count <= 100000,
            "CvGame.Read did not append exactly one replay record to the observed count")
    old_cursor = new_cursor = first + 4
    for _ in range(old_count):
        old_next, _ = parse_replay(before, old_cursor)
        new_next, _ = parse_replay(after, new_cursor)
        require(before[old_cursor:old_next] == after[new_cursor:new_next], "Existing replay record changed during reload")
        old_cursor, new_cursor = old_next, new_next
    new_cursor, appended = parse_replay(after, new_cursor)
    before_sessions, after_sessions = read_i32(before, old_cursor), read_i32(after, new_cursor)
    require(after_sessions == before_sessions + 1 and before[old_cursor + 4:] == after[new_cursor + 4:],
            "CvGame.Read session increment or post-session Game bytes differ")
    require((appended["turn"], appended["type"], appended["plots"], appended["player"]) ==
            (source_header["turn"], 0, [(-1, -1)], source_header["active_player"]),
            "Appended replay record is not the source game's reload marker")
    if language == "en_US":
        expected_text = f"Session {after_sessions} starts"
    elif language == "ko_KR":
        expected_text = f"세션 {after_sessions}가 시작됐습니다."
    else:
        raise RuntimeError("Reload text verification supports only frozen EN/KO localization")
    require(appended["text"] == expected_text, "Appended replay record text is not the localized reload session")
    require(re.search(rf"^INTERACTIVE_RESTORE_IDENTITY={source_header['turn']}\|{source_header['elapsed']}\|{source_header['active_player']}\|133$", marker_output, re.M),
            "Host restore identity marker differs from independently parsed source archive")
    equal = 133 - len(changed)
    require(re.search(rf"^INTERACTIVE_RESTORE_SECTIONS_EQUAL={equal}\|133$", marker_output, re.M) and
            re.findall(r"^INTERACTIVE_RESTORE_SECTION_CHANGED=(\d+)\|(\d+)$", marker_output, re.M) == [tuple(map(str, x)) for x in changed],
            "Host restore section markers differ from the full archive comparison")
    return {"source_header": source_header, "restored_header": restored_header,
            "source_archive_sha256": source_header["sha256"], "restored_archive_sha256": restored_header["sha256"],
            "changed_sections": [list(x) for x in changed], "equal_sections": equal,
            "game_section_bytes": [len(before), len(after)], "replay_version": replay_version,
            "replay_count": [old_count, new_count], "existing_replay_records_byte_identical": True,
            "appended_reload_record": {"turn": appended["turn"], "type": appended["type"],
                                       "plots": [list(x) for x in appended["plots"]], "player": appended["player"],
                                       "text": appended["text"]},
            "session_counter": [before_sessions, after_sessions],
            "game_prefix_before_replay_count_identical": True, "game_suffix_after_session_identical": True,
            "all_other_sections_byte_identical": True, "source_checkpoint_archive": source_header,
            "restored_roundtrip_archive": restored_header}


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


def read_run(run_id: str, *, research_tree: bool = False) -> tuple[dict, dict, str, str, dict, Path, Path]:
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
    accepted = ({"CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS",
                 "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS"} if research_tree else
                {"CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_SMOKE_PASS",
                 "CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_RESTORE_SMOKE_PASS"})
    require(status in accepted and result.get("returncode") == 0 and result.get("timed_out") is False and
            result.get("runtime_inputs_unchanged") is True and result.get("decision_ui_smoke_requested") is True and
            result.get("stage_or_mods_changed") is False and attempt.get("status") == "FINISHED" and
            attempt.get("returncode") == 0 and attempt.get("timed_out") is False and attempt.get("pid") == result.get("driver_pid"),
            "Host/driver did not finish a clean decision-UI smoke with unchanged runtime inputs")
    require(not re.search(r"HOST_FAILURE|HOST_NATIVE_EXCEPTION|HOST_CLEANUP_PENDING|SCRIPT_FAILURE|INTERACTIVE_INPUT_REJECTED", stdout + "\n" + stderr),
            "Host or native-input failure marker is present")
    expected_profile = "POSTED_HWND_CONTINUOUS_TREE_DECISION_UI_LOOP" if research_tree else \
                       "POSTED_HWND_CONTINUOUS_DECISION_UI_LOOP"
    require(request.get("input_profile") == expected_profile and request.get("smoke") is True and
            request.get("decisions") is True and request.get("research_tree", False) is research_tree and
            result.get("research_tree_requested", False) is research_tree and
            (not research_tree or result.get("research_tree_sequence_verified") is True) and
            request.get("stage_or_mods_changed") is False,
            "Request does not describe the isolated decision-UI profile")
    return request, result, stdout, stderr, attempt, runtime, ev


def provenance(request: dict, result: dict, runtime: Path, *, research_tree: bool = False) -> dict:
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
                                   "INTERACTIVE_DECISION_PRODUCTION_TARGET", "INTERACTIVE_DECISION_RESEARCH_TARGET",
                                   "if(!uiFrame.cityBackdrop.empty())", "backdrop.textures.push_back({png})",
                                   "png=backdropFolder+L\"\\\\city-backdrop.png\"", "popup.textures.push_back({png})"),
        "InteractiveUiSession.h": ("BUTTONPOPUP_CHOOSEPRODUCTION", "BUTTONPOPUP_CHOOSETECH", "CaptureFrame", "VerifySnapshot"),
        "UiPopupContext.h": ("DispatchExternalWindowInput", "SnapshotForExternalScene", "TakeDeferredPopup"),
        "LocalSdkSession.h": ("ResponseCityPushOrder", "ResponseResearch"),
        "InteractiveGameSession.h": ("DecisionState", "CurrentResearch", "ProductionUnit"),
        "WorldViewRenderer.cpp": ("0x5a57000000000000ull", "2ull<<32", "4ull<<32"),
        "BitmapWindow.cpp": ("HitTestLogicalPoint", "hits_.rbegin()", "hits_.rend()", "return it->controlKey"),
    }
    for name, tokens in required_tokens.items():
        require(name in source, f"Frozen Host closure omits {name}")
        body = Path(source[name]["path"]).read_text(encoding="utf-8")
        require(all(token in body for token in tokens), f"Frozen Host source lacks decision/UI dispatch contract in {name}")
    popup = Path(source["UiPopupContext.h"]["path"]).read_text(encoding="utf-8")
    require("ChooseProductionUnit" in popup and "ChooseResearchTechnology" in popup,
            "Sealed popup source omits fixture methods required to distinguish them from the live UI path")
    if research_tree:
        loop = Path(source["InteractiveGameLoop.h"]["path"]).read_text(encoding="utf-8")
        require(all(token in loop for token in ("INTERACTIVE_DECISION_TREE_HANDOFF_TARGET",
                                                "INTERACTIVE_DECISION_TREE_SELECTION_REMAINS_OPEN",
                                                "PostMessageW(window.NativeHandle(),WM_KEYDOWN,VK_ESCAPE")),
                "Frozen Host loop omits the actual-window ResearchTree handoff, retained-open check, or Escape path")
        router = Path(source["InteractiveUiSession.h"]["path"]).read_text(encoding="utf-8")
        deferred_front_enqueue = ("pending_.push_front(deferred)" in router or
                                  "pending_.emplace_front(OwnedPopupInfo(deferred))" in router)
        require("TakeDeferredPopup" in router and deferred_front_enqueue and
                "BUTTONPOPUP_TECH_TREE" in popup and "deferredPopupReady_" in popup,
                "Frozen popup/router source omits the original deferred TechTree handoff path")
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


def runtime_input(request: dict, runtime: Path, name: str) -> tuple[dict, Path]:
    matches = [row for row in request.get("runtime_inputs", [])
               if type(row) is dict and Path(row.get("path", "")).name == name]
    require(len(matches) == 1, f"Run request does not identify exactly one private {name}")
    row = matches[0]
    check_artifacts(row)
    path = Path(row["path"]).resolve(strict=True)
    require(path.is_relative_to(runtime.resolve(strict=True)) and digest(path) == row.get("sha256"),
            f"Private {name} escaped its runtime or changed after the run")
    return row, path


def city_localization_contract(request: dict, runtime: Path, scenes: dict[int, tuple[dict, Path]]) -> dict:
    """Cross-check captured visible city names against the exact private DB inputs."""
    rules_row, rules_path = runtime_input(request, runtime, "rules.db")
    loc_row, loc_path = runtime_input(request, runtime, "localization.db")
    language = request.get("language")
    require(type(language) is str and language in ("en_US", "ko_KR"),
            "City-name localization check requires the run's exact EN/KO locale")
    uri = loc_path.as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as localization, \
         sqlite3.connect(rules_path.as_uri() + "?mode=ro", uri=True) as rules:
        table_names = {row[0] for row in localization.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        require({"Languages", "LocalizedText", "LanguagePriorities"} <= table_names,
                "Private localization DB omits the provider's LocalizedText/LanguagePriorities tables")
        loc_columns = {row[1] for row in localization.execute('PRAGMA table_info("LocalizedText")')}
        priority_columns = {row[1] for row in localization.execute('PRAGMA table_info("LanguagePriorities")')}
        require({"Tag", "Text", "Language"} <= loc_columns and
                {"LanguageSet", "Language", "Priority"} <= priority_columns,
                "Private localization DB schema differs from the loaded provider contract")
        require(localization.execute('SELECT 1 FROM "Languages" WHERE "Type"=? LIMIT 1',
                                     (language,)).fetchone() is not None,
                "Private localization DB does not expose the exact run locale selected by HostRun")
        built_in = {row[0] for row in rules.execute(
            "SELECT CityName FROM Civilization_CityNames UNION "
            "SELECT CityName FROM MinorCivilization_CityNames") if type(row[0]) is str}
        localized_count = literal_count = scene_city_count = 0
        checked_names = {}
        for doc, _ in scenes.values():
            plots = doc.get("plots")
            cities = doc.get("cities")
            require(type(plots) is list and type(cities) is list,
                    "World scene omits its visible plot/city records")
            visible_xy = {(p[1], p[2]) for p in plots if type(p) is list and len(p) == 5 and
                          p[3] == 1 and p[4] == 1}
            scene_ids = set()
            for city in cities:
                require(type(city) is dict and all(type(city.get(k)) is int for k in ("id", "owner", "x", "y")) and
                        type(city.get("rawName")) is str and type(city.get("displayName")) is str,
                        "World scene city record lacks exact identity/rawName/displayName fields")
                identity = city["owner"], city["id"]
                require(city["id"] >= 0 and city["owner"] >= 0 and identity not in scene_ids and
                        (city["x"], city["y"]) in visible_xy,
                        "World city record is duplicated or escapes a currently visible plot")
                scene_ids.add(identity)
                raw, display = city["rawName"], city["displayName"]
                scene_city_count += 1
                if raw in built_in:
                    candidates = localization.execute(
                        "SELECT T.Text FROM LocalizedText AS T LEFT JOIN "
                        "(SELECT Language,Priority FROM LanguagePriorities WHERE LanguageSet=?1) AS P "
                        "ON T.Language=P.Language WHERE T.Tag=?2 ORDER BY P.Priority DESC,T.rowid",
                        (language, raw)).fetchall()
                    # The provider preserves the original key when a catalog row
                    # is absent, NULL, or empty; WorldViewState only replaces the
                    # raw name when UTF-8 text is nonempty.
                    expected = raw if not candidates or candidates[0][0] in (None, "") else candidates[0][0]
                    require(display == expected,
                            f"Built-in city localization differs from private {language} provider lookup for {raw!r}")
                    localized_count += 1
                else:
                    require(raw == display,
                            "Non-catalog/custom city name was changed by the localization path")
                    literal_count += 1
                prior = checked_names.setdefault(identity, (raw, display))
                require(prior == (raw, display),
                        "The same visible city changed raw/display name within one SDK run")
        return {"rules_db": {"path": str(rules_path), "sha256": rules_row["sha256"]},
                "localization_db": {"path": str(loc_path), "sha256": loc_row["sha256"]},
                "language": language, "provider_language_set": language,
                "visible_city_rows_checked": scene_city_count,
                "built_in_localized_rows_checked": localized_count,
                "noncatalog_literal_rows_checked": literal_count,
                "custom_name_executed_by_fixture": False,
                "visible_plot_membership_checked": True}


def verify_decision_snapshot(snapshot: dict, *, turn: int, active: int, city: int, unit: int, tech: int) -> None:
    rows_by_type = snapshot["rows"]
    game = rows_by_type["G"][0]
    require(int(game[1]) == turn and int(game[3]) == active, "SDK semantic snapshot has a different turn/active player")
    players = [row for row in rows_by_type["P"] if int(row[1]) == active]
    cities = [row for row in rows_by_type["C"] if int(row[1]) == active and int(row[2]) == city]
    require(len(players) == len(cities) == 1 and int(players[0][10]) == tech and
            int(cities[0][8]) == unit, "SDK semantic snapshot lacks the selected city production/research state")


def ui_snapshots(driver: dict, result: dict, runtime: Path, by_name: dict[str, Path],
                 request_rows: list[tuple[str, ...]], frame_rows: list[tuple[str, ...]],
                 output: str, *, research_tree: bool = False) -> list[dict]:
    scene_requests = driver.get("scene_requests")
    require(type(scene_requests) is list and len(scene_requests) >= (3 if research_tree else 2),
            "UI driver did not service all required original popup scenes")
    contexts = [row.get("context") for row in scene_requests if type(row) is dict]
    required_contexts = ("production", "research", "research-tree") if research_tree else ("production", "research")
    require(all(ctx in contexts for ctx in required_contexts), "Driver omitted an original popup context")
    first_seen = []
    for ctx in contexts:
        if ctx in required_contexts and ctx not in first_seen:
            first_seen.append(ctx)
    require(first_seen[:len(required_contexts)] == list(required_contexts),
            "Original popup contexts did not follow the production→chooser→tree handoff order")
    require(len(request_rows) == len(scene_requests), "Native scene requests and driver-prepared requests differ")
    frame_by_sequence = {}
    for frame_row in frame_rows:
        require(len(frame_row) == 8, "Native popup frame row has an unexpected schema")
        frame_sequence = int(frame_row[0])
        require(frame_sequence not in frame_by_sequence,
                "Native popup frame sequence is duplicated")
        frame_by_sequence[frame_sequence] = frame_row
    request_sequences = set(range(1, len(scene_requests) + 1))
    require(set(frame_by_sequence) <= request_sequences,
            "Native popup frame refers to a missing preparation request")
    backdrop_rows = rows(output, "INTERACTIVE_CITY_BACKDROP",
                         r"^INTERACTIVE_CITY_BACKDROP=(\d+)\|([^\r\n|]+)$")
    backdrop_by_sequence = {}
    for sequence_s, path_s in backdrop_rows:
        sequence = int(sequence_s)
        require(sequence not in backdrop_by_sequence,
                "CityView backdrop marker sequence is duplicated")
        backdrop_by_sequence[sequence] = Path(path_s).resolve(strict=True)
    snapshots = []
    for seq, (driver_row, request_row) in enumerate(zip(scene_requests, request_rows), 1):
        ctx, snap, folder = request_row[1], Path(request_row[2]).resolve(strict=True), Path(request_row[3]).resolve(strict=True)
        require(int(request_row[0]) == seq and driver_row.get("sequence") == seq and driver_row.get("context") == ctx,
                "Native and driver popup sequence/context differ")
        require(ctx in ("city-view", "production", "research", "research-tree"),
                "Unexpected popup context in decision smoke")
        require(snap.name == f"play-ui-{seq}.json" and snap.parent.parent.name == "sessions" and
                folder.parent == snap.parent and folder.is_dir(), "Popup snapshot/prepared scene escaped its run session")
        snap_doc = json.loads(snap.read_text(encoding="utf-8"))
        context_name, kind = (("CityView", "CityView") if ctx == "city-view" else
                              ("ProductionPopup", "Production") if ctx == "production" else
                              ("TechPopup", "Research") if ctx == "research" else
                              ("TechTree", "ResearchTree"))
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
            original_sources.append(dict(artifact(copies[0]), original_name=source_path.name))
        frame_row = frame_by_sequence.get(seq)
        if frame_row is None:
            backdrop_path = backdrop_by_sequence.get(seq)
            require(ctx == "city-view" and backdrop_path == folder / "city-backdrop.png",
                    "Unframed CityView request is not backed by its exact generated city-backdrop marker")
            base.generated(result, backdrop_path, runtime)
            next_rows = [row for row in scene_requests if row.get("sequence") == seq + 1]
            require(len(next_rows) == 1 and next_rows[0].get("context") == "production",
                    "CityView backdrop is not immediately connected to its parent Production scene request")
            parent_folder = Path(next_rows[0].get("folder", "")).resolve(strict=True)
            composed_parent = parent_folder / "composed.png"
            require(composed_parent.is_file(),
                    "CityView backdrop parent Production composition is absent from generated evidence")
            base.generated(result, composed_parent, runtime)
            generation = turn = hwnd = device = 0
        else:
            frame_seq, generation, turn, frame_ctx, hwnd, device, frame_snapshot, frame_folder = frame_row
            require(int(frame_seq) == seq and int(generation) > 0 and int(turn) >= 0 and frame_ctx == ctx and
                    int(hwnd) > 0 and int(device) > 0 and Path(frame_snapshot).resolve() == snap and Path(frame_folder).resolve() == folder,
                    "Native popup frame does not identify its exact request/HWND/device")
        hit_key = None
        # The selected target is checked against the later target marker; preserve
        # the full retained payload rows in the proof for independent inspection.
        timer = snap_doc.get("timerSemaphore")
        snapshots.append({"sequence": seq, "context": ctx, "snapshot": artifact(snap), "scene_folder": str(folder),
                          "packet": artifact(packet), "manifest": artifact(manifest_path), "targets": targets,
                          "hit_regions": manifest["hit_regions"],
                          "original_context_sources": original_sources,
                          "snapshot_active": snap_doc.get("active"), "timer_semaphore": timer,
                          "target_keys": sorted(target_map), "hwnd": int(hwnd), "device": int(device),
                          "generation": int(generation), "turn": int(turn)})
    frame_bound = [row for row in snapshots if row["generation"] > 0]
    require(len({row["hwnd"] for row in frame_bound}) == 1 and len({row["device"] for row in frame_bound}) == 1,
            "Decision popups replaced the same owned HWND or GPU device")
    return snapshots


def popup_click_snapshot(ui: list[dict], inputs: list[tuple[str, ...]], posted: list[tuple[str, ...]],
                         context: str, key: int, *, expected_payload: tuple[int, int] | None = None
                         ) -> tuple[dict, dict, dict]:
    """Bind a posted point to its requested control and actual topmost native callback."""
    posts = []
    for row in posted:
        if int(row[1]) != key:
            continue
        candidates = [scene for scene in ui if scene["context"] == context and
                      scene["generation"] == int(row[0])]
        if len(candidates) != 1:
            continue
        if expected_payload is not None and not any(
                target.get("key") == key and target.get("event") == "LeftClick" and
                (target.get("void1"), target.get("void2")) == expected_payload
                for target in candidates[0]["targets"]):
            continue
        posts.append(row)
    require(len(posts) == 1, f"{context} requested key {key} does not identify one posted HWND click")
    generation, _, client_x, client_y = map(int, posts[0])
    events = [row for row in inputs if int(row[0]) == generation and int(row[1]) == 1]
    require(len(events) == 1 and int(events[0][3]) == 1,
            f"{context} posted generation was not consumed exactly once")
    delivered_key = int(events[0][2])
    scenes = [scene for scene in ui if scene["context"] == context and scene["generation"] == generation]
    require(len(scenes) == 1, f"{context} callback input does not bind to one exact native scene generation")
    scene = scenes[0]
    logical_x, logical_y = client_x * 1.5, client_y * 1.5
    bound_targets = []
    for target_key in (key, delivered_key):
        targets = [t for t in scene["targets"] if t["key"] == target_key and t.get("event") == "LeftClick"]
        require(len(targets) == 1 and targets[0].get("visible") is True and targets[0].get("disabled") is False,
                f"{context} key does not identify one enabled original left-click callback")
        target = targets[0]
        hits = [h for h in scene["hit_regions"] if isinstance(h, list) and len(h) == 5 and h[0] == target_key]
        require(len(hits) == 1, f"{context} callback is absent or duplicated in its compiled native hit map")
        clipped = target.get("clippedBounds")
        require(type(clipped) is dict and all(type(clipped.get(k)) in (int, float)
                                              for k in ("x", "y", "width", "height")),
                f"{context} callback lacks exact retained clipped bounds")
        expected = (clipped["x"], clipped["y"], clipped["x"] + clipped["width"], clipped["y"] + clipped["height"])
        require(all(math.isclose(float(actual), float(want), rel_tol=0.0, abs_tol=1e-4)
                    for actual, want in zip(hits[0][1:], expected)),
                f"{context} native hit rectangle differs from its retained callback clip")
        require(hits[0][1] <= logical_x < hits[0][3] and hits[0][2] <= logical_y < hits[0][4],
                f"{context} posted coordinate is outside its requested or delivered callback")
        bound_targets.append(target)
    top_hit = next((h for h in reversed(scene["hit_regions"])
                    if h[1] <= logical_x < h[3] and h[2] <= logical_y < h[4]), None)
    require(top_hit is not None and top_hit[0] == delivered_key,
            f"{context} delivered callback is not the topmost retained native hit")
    return scene, bound_targets[0], bound_targets[1]


def research_callback_targets(requested: dict, delivered: dict, tech: int, lua_text: str,
                              *, research_tree: bool) -> None:
    """Only stock small-button research aliases may replace the requested TechButton."""
    require(requested.get("id") == "TechButton" and
            all(t.get("void1") == tech and t.get("void2") == 0 for t in (requested, delivered)),
            "Requested and delivered research callbacks do not identify the same normal technology")
    if requested["key"] == delivered["key"]:
        return
    small = re.fullmatch(r"B([1-9][0-9]*)", str(delivered.get("id", "")))
    limits = re.findall(r"local\s+maxSmallButtons\s*=\s*(\d+)", lua_text)
    require(small is not None and len(set(limits)) == 1 and int(small[1]) <= int(limits[0]),
            "Native research hit is not a declared original small-button alias")
    registration = ("AddCallbackToSmallButtons( thisTechButton, maxSmallButtons, techID, numFreeTechs, Mouse.eLClick, TechSelected );"
                    if research_tree else
                    "AddCallbackToSmallButtons( thisTechButtonInstance, maxSmallButtons, tech.ID, buttonVoid2Value, Mouse.eLClick, TechSelected );")
    require(registration in lua_text and
            'local buttonName = "B"..tostring(buttonNum);' in lua_text and
            'thisTechButtonInstance[buttonName]:SetVoids(void1, void2);' in lua_text and
            'thisTechButtonInstance[buttonName]:RegisterCallback(thisEvent, thisCallback);' in lua_text,
            "Frozen original Lua does not bind the delivered small button to the same research callback")


def native_tree_escape_timer(output: str, generation: int, turn: int) -> dict:
    """Bind the timer release to the same native Escape dispatch, not an older close."""
    key_pattern = r"^INTERACTIVE_UI_NATIVE_KEY=(\d+)\|research-tree\|27\|1\|0$"
    keys = list(re.finditer(key_pattern, output, re.M))
    require(len(keys) == 1 and int(keys[0][1]) == generation,
            "ResearchTree Escape timer proof lacks its exact native key event")
    native = list(re.finditer(r"^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$", output, re.M))
    preceding = [event for event in native if event.end() < keys[0].start()]
    require(preceding and tuple(map(int, preceding[-1].groups())) == (generation, 0, 0, 1),
            "ResearchTree Escape key does not follow its consumed native KeyDown input")
    dispatch_end = preceding[-1].start()
    dispatch_start = preceding[-2].end() if len(preceding) > 1 else 0
    timer_pattern = r"^UI_WINDOW_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])\|(\d+)\|(\d+)\|([01])\|([01])\|(-?\d+)\|(\d+)$"
    timer_rows = list(re.finditer(timer_pattern, output[dispatch_start:dispatch_end], re.M))
    require(len(timer_rows) == 1,
            "ResearchTree Escape dispatch has missing or ambiguous popup timer records")
    sequence, kind, key, consumed, rng_before, rng_after, held_before, held_after, actual_turn, thread = map(int, timer_rows[0].groups())
    require(sequence > 0 and (kind, key, consumed) == (1, 27, 1) and
            rng_before == rng_after and (held_before, held_after) == (1, 0) and
            actual_turn == turn and thread > 0,
            "Actual ResearchTree Escape did not release timer 1 to 0 while preserving turn and RNG")
    return {"scene_generation": generation, "popup_sequence": sequence, "virtual_key": key,
            "consumed": True, "timer_held_before": held_before, "timer_held_after": held_after,
            "rng_before": rng_before, "rng_after": rng_after, "turn": actual_turn,
            "owner_thread": thread, "same_native_dispatch_verified": True}


def verify_run(run_id: str, proof_dir: Path, *, research_tree: bool = False) -> dict:
    request, result, output, stderr, attempt, runtime, evidence = read_run(run_id, research_tree=research_tree)
    prov = provenance(request, result, runtime, research_tree=research_tree)
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
    req_rows = rows(output, "INTERACTIVE_UI_SCENE_REQUEST", r"^INTERACTIVE_UI_SCENE_REQUEST=(\d+)\|([^\r\n|]+)\|([^\r\n|]+)\|([^\r\n|]+)$")
    frame_rows = rows(output, "INTERACTIVE_UI_FRAME", r"^INTERACTIVE_UI_FRAME=(\d+)\|(\d+)\|(\d+)\|([^\r\n|]+)\|(\d+)\|(\d+)\|([^\r\n|]+)\|([^\r\n|]+)$")
    inputs = rows(output, "INTERACTIVE_UI_NATIVE_INPUT", r"^INTERACTIVE_UI_NATIVE_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$")
    posted = rows(output, "INTERACTIVE_SMOKE_POSTED", r"^INTERACTIVE_SMOKE_POSTED=(\d+)\|(\d+)\|(-?\d+)\|(-?\d+)$")
    tree_handoffs = rows(output, "INTERACTIVE_DECISION_TREE_HANDOFF_TARGET", r"^INTERACTIVE_DECISION_TREE_HANDOFF_TARGET=(\d+)$")
    tree_open = re.findall(r"^INTERACTIVE_DECISION_TREE_SELECTION_REMAINS_OPEN=true$", output, re.M)
    native_tree_handoffs = rows(output, "RESEARCH_TREE_UI_HANDOFF", r"^RESEARCH_TREE_UI_HANDOFF=(\d+)\|(\d+)\|(-?\d+)$")
    key_events = rows(output, "INTERACTIVE_UI_NATIVE_KEY",
                      r"^INTERACTIVE_UI_NATIVE_KEY=(\d+)\|([^|]+)\|(\d+)\|([01])\|([01])$")
    require(len(starts) == len(targets_p) == len(targets_r) == len(before) == len(after) == len(completed) == len(next_turns) == 1,
            "Decision callback, before/after observation, or next-turn markers are missing/duplicated")
    tree_timer_proof = None
    if research_tree:
        require(len(tree_handoffs) == len(tree_open) == 1,
                "World-loop ResearchTree handoff key or post-selection open-state marker is missing/duplicated")
        # These optional records belong to the separate owner-only helper path.
        # If present, validate their identity, but never require them as evidence
        # for the posted-HWND route.
        if native_tree_handoffs:
            require(len(native_tree_handoffs) == 1 and int(native_tree_handoffs[0][0]) == int(tree_handoffs[0][0]) and
                    int(native_tree_handoffs[0][1]) == 67 and int(native_tree_handoffs[0][2]) == -1,
                    "Optional owner helper handoff record conflicts with the observed world-loop handoff")
    else:
        require(not tree_handoffs and not native_tree_handoffs and not tree_open,
                "Standard decision run unexpectedly contains ResearchTree sequence markers")
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
    city_name_proof = city_localization_contract(request, runtime, scenes) if research_tree else None
    ui = ui_snapshots(driver, result, runtime, by_name, req_rows, frame_rows, output,
                      research_tree=research_tree)
    require(len([r for r in inputs if int(r[1]) == 1]) >= (3 if research_tree else 2),
            "Original popup callback click inputs are missing")
    production_scene, production_target, production_delivered = popup_click_snapshot(
        ui, inputs, posted, "production", pkey, expected_payload=(6, unit))
    require(production_delivered["key"] == pkey, "Native production callback differs from its requested control")
    selected_context = "research-tree" if research_tree else "research"
    research_scene, research_target, research_delivered = popup_click_snapshot(ui, inputs, posted, selected_context, rkey)
    require(production_target.get("void1") == 6 and production_target.get("void2") == unit and
            city == int(targets_p[0][0]),
            "Production target is not the selected original ORDER_TRAIN callback for the exact city/unit")
    require("local g_append = false" in "\n".join(p.read_text(encoding="utf-8", errors="replace")
                                                       for p in Path(production_scene["scene_folder"]).rglob("*.lua")) and
            "Game.CityPushOrder(city, eOrder, iData, false, not g_append, true)" in
            "\n".join(p.read_text(encoding="utf-8", errors="replace")
                     for p in Path(production_scene["scene_folder"]).rglob("*.lua")),
            "Frozen original ProductionPopup callback does not preserve its replace-order tuple")
    production_tuple = {"api": "Game.CityPushOrder", "city": city, "order": "ORDER_TRAIN", "data": unit,
                        "order_id": 0, "alt": False, "shift": True, "control": True}
    opener_scene = None
    tree_scene = None
    if research_tree:
        open_key = int(tree_handoffs[0][0])
        require(open_key != rkey,
                "Original chooser handoff key and ResearchTree callback key unexpectedly alias")
        opener_scene, open_target, open_delivered = popup_click_snapshot(ui, inputs, posted, "research", open_key)
        require(open_delivered["key"] == open_key, "Native tree opener callback differs from its requested control")
        require(opener_scene["sequence"] < research_scene["sequence"],
                "Original TechPopup OpenTTButton click did not precede the ResearchTree selection scene")
        require(open_target.get("id") == "OpenTTButton" and open_target.get("event") == "LeftClick" and
                open_target.get("visible") is True and open_target.get("disabled") is False,
                "TechPopup handoff key is not its original visible OpenTTButton callback")
        opener_sources = {row["original_name"] for row in opener_scene["original_context_sources"]}
        opener_lua = "\n".join(p.read_text(encoding="utf-8", errors="replace")
                                 for p in Path(opener_scene["scene_folder"]).rglob("*.lua") if p.is_file())
        require("TechPopup.lua" in opener_sources and "function OpenTechTree()" in opener_lua and
                "ButtonPopupTypes.BUTTONPOPUP_TECH_TREE" in opener_lua and
                "Controls.OpenTTButton:RegisterCallback( Mouse.eLClick, OpenTechTree)" in opener_lua,
                "TechPopup opener provenance is not the original OpenTTButton-to-TechTree callback")
        tree_target = research_target
        require(tree_target.get("id") == "TechButton" and tree_target.get("void1") == tech and
                tree_target.get("void2") == 0 and research_scene["snapshot_active"] is True and
                research_scene["timer_semaphore"] == 1,
                "ResearchTree selection is not the exact original normal TechButton callback")
        tree_scene = research_scene
        scene_folder = Path(tree_scene["scene_folder"])
        lua_sources = [p for p in scene_folder.rglob("*.lua") if p.is_file()]
        lua_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in lua_sources)
        source_names = {row["original_name"] for row in tree_scene["original_context_sources"]}
        require({"TechTree.lua", "TechButtonInclude.lua"} <= source_names and
                "Network.SendResearch(eTech, player:GetNumFreeTechs(), -1, UIManager:GetShift())" in lua_text and
                "SetVoid1( tech.ID )" in lua_text and "SetVoid2( 0 )" in lua_text,
                "Frozen stock TechTree callback provenance/payload does not match the original normal research path")
        research_callback_targets(research_target, research_delivered, tech, lua_text, research_tree=True)
        research_tuple = {"api": "Network.SendResearch", "tech": tech, "discover": 0,
                          "steal_from": -1, "shift": False}
        tree_generation = tree_scene["generation"]
        post_selection_tree = [s for s in ui if s["context"] == "research-tree" and
                               s["sequence"] > tree_scene["sequence"] and
                               s["generation"] > tree_generation and s["snapshot_active"] is True and
                               s["timer_semaphore"] == 1]
        require(post_selection_tree,
                "Tree selection was not followed by an active held-timer ResearchTree snapshot refresh")
        matching_escape = [row for row in key_events if row[1] == "research-tree" and int(row[2]) == 27 and
                           int(row[3]) == 1 and int(row[4]) == 0]
        require(len(matching_escape) == 1 and int(matching_escape[0][0]) > tree_generation,
                "A consumed native VK_ESCAPE did not close the active ResearchTree scene")
        escape_generation = int(matching_escape[0][0])
        active_tree_generations = {s["generation"] for s in post_selection_tree}
        require(escape_generation == max(active_tree_generations),
                "Native Escape was not delivered against the latest captured active ResearchTree HWND scene")
        tree_timer_proof = native_tree_escape_timer(output, escape_generation, start_turn)
        require(any(doc["generation"] > escape_generation for doc, _ in scenes.values()),
                "World scene did not return after native ResearchTree Escape")
        require("INTERACTIVE_UI_NATIVE_KEY" in output,
                "Host output does not preserve the actual HWND virtual-key event trace")
    else:
        require(research_target.get("id") == "TechButton" and research_target.get("void1") == tech and
                research_target.get("void2") == 0,
                "Research target is not the normal exact-tech callback from the original TechPopup")
        lua_sources = [p for p in Path(research_scene["scene_folder"]).rglob("*.lua") if p.is_file()]
        lua_text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in lua_sources)
        require("Network.SendResearch(eTech, 0, iValue, false)" in lua_text,
                "Frozen original TechPopup callback does not preserve normal research selection")
        research_callback_targets(research_target, research_delivered, tech, lua_text, research_tree=False)
        research_tuple = {"api": "Network.SendResearch", "tech": tech, "discover": 0,
                          "steal_from": -1, "shift": False}
    pseq = production_scene["sequence"]
    rseq = research_scene["sequence"]
    # Native popup clicks are matched to their popup-frame generations and target keys.
    click_scenes = [(production_scene, pkey, "production")]
    if opener_scene is not None:
        click_scenes.append((opener_scene, int(tree_handoffs[0][0]), "research"))
    click_scenes.append((research_scene, research_delivered["key"], "research-tree" if research_tree else "research"))
    for click_scene, chosen_key, click_context in click_scenes:
        seq = click_scene["sequence"]
        frame = click_scene
        delivered = [row for row in inputs if int(row[0]) == frame["generation"] and int(row[1]) == 1 and int(row[3]) == 1]
        require(len(delivered) == 1 and int(delivered[0][2]) == chosen_key,
                f"{click_context} generation did not deliver exactly its expected consumed native callback")
        popup_targets = [t for t in click_scene["targets"] if t["key"] == chosen_key and t.get("event") == "LeftClick"]
        require(len(popup_targets) == 1, "Native hit-test key does not identify an original left-click callback row")
        if click_context == "production":
            require(popup_targets[0].get("void1") == 6 and popup_targets[0].get("void2") == unit,
                    "Native production hit-test callback payload differs from the selected ORDER_TRAIN unit")
        elif click_context == "research-tree":
            require(popup_targets[0].get("void1") == tech and popup_targets[0].get("void2") == 0,
                    "Native TechTree hit-test callback payload differs from the selected normal technology")
        elif research_tree:
            require(popup_targets[0].get("id") == "OpenTTButton",
                    "Original TechPopup dispatch was not the OpenTTButton handoff callback")
        else:
            require(popup_targets[0].get("void1") == tech and popup_targets[0].get("void2") == 0,
                    "Native research hit-test callback payload differs from normal selected technology")
        same_generation = [(revision, doc) for revision, (doc, _) in scenes.items() if doc["generation"] == frame["generation"]]
        require(len(same_generation) == 1, "Popup generation does not identify one composed world scene")
        _, composed_scene = same_generation[0]
        require(composed_scene["hits"] == click_scene["hit_regions"],
                "Native composed scene hit order/bounds differ from the prepared popup packet manifest")
        require(composed_scene.get("pixelHitCount", 0) == 0 and
                composed_scene.get("pixelHitKeys", []) == [] and
                composed_scene.get("pixelHitFile", "") == "",
                "Active original popup scene unexpectedly carries a world terrain pixel-hit raster")
        require(sum(1 for h in composed_scene["hits"] if isinstance(h, list) and len(h) == 5 and h[0] == chosen_key) == 1,
                "Selected original popup callback is absent/duplicated in the composed scene hit map")
        world_frames = result.get("frames", [])
        matched_frame = [f for f in world_frames if len(f) == 9 and f[1] == frame["generation"]]
        require(len(matched_frame) == 1 and matched_frame[0][5] == frame["device"] and
                matched_frame[0][2] == frame["turn"] and composed_scene["generation"] == frame["generation"],
                "Popup and composed world capture do not share the same scene generation/device/turn")
        composed_png = Path(click_scene["scene_folder"]) / "composed.png"
        require(composed_png.is_file(), "Original popup was not composed over the live world bitmap")
        composed_data = composed_png.read_bytes()
        require(composed_data[:8] == b"\x89PNG\r\n\x1a\n" and composed_data[12:16] == b"IHDR" and
                int.from_bytes(composed_data[16:20], "big") == 1920 and int.from_bytes(composed_data[20:24], "big") == 1080,
                "Composed original popup frame does not retain its 1920x1080 logical canvas")
    world_inputs = rows(output, "INTERACTIVE_WINDOW_INPUT", r"^INTERACTIVE_WINDOW_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$")
    all_inputs = [(int(g), int(k), int(key), int(c), "world") for g, k, key, c in world_inputs if int(k) == 1]
    all_inputs += [(int(g), int(k), int(key), int(c), "popup") for g, k, key, c in inputs if int(k) == 1]
    require(len(posted) == len(all_inputs) and len(posted) >= (6 if research_tree else 5),
            "Posted HWND coordinates and delivered world/popup input rows do not pair")
    posted_hits = []
    for (generation_s, key_s, x_s, y_s) in posted:
        generation, key, x, y = int(generation_s), int(key_s), int(x_s), int(y_s)
        matches_input = [row for row in all_inputs if row[0] == generation and row[1] == 1 and row[3] == 1]
        require(len(matches_input) == 1, "Posted coordinate was not consumed exactly once as its generation-bound control click")
        delivered_key = matches_input[0][2]
        if matches_input[0][4] == "world":
            require(delivered_key == key, "World hit-test changed the explicitly posted world control key")
        matches = [doc for doc, _ in scenes.values() if doc["generation"] == generation]
        require(len(matches) == 1, "Posted generation does not map to one actual composed world scene")
        doc = matches[0]
        hits = [h for h in doc["hits"] if isinstance(h, list) and len(h) == 5 and h[0] == key]
        delivered_hits = [h for h in doc["hits"] if isinstance(h, list) and len(h) == 5 and h[0] == delivered_key]
        hx, hy = x * 1.5, y * 1.5
        if hits or delivered_hits:
            require(len(hits) == len(delivered_hits) == 1,
                    "Requested or delivered key is absent/duplicated in its frozen scene hit list")
            require(hits[0][1] <= hx < hits[0][3] and hits[0][2] <= hy < hits[0][4] and
                    delivered_hits[0][1] <= hx < delivered_hits[0][3] and delivered_hits[0][2] <= hy < delivered_hits[0][4],
                    "Posted client coordinate falls outside its requested or actual top-hit retained region")
            top_hit = next((h for h in reversed(doc["hits"]) if h[1] <= hx < h[3] and h[2] <= hy < h[4]), None)
            require(top_hit is not None and top_hit[0] == delivered_key,
                    "Native callback differs from the composed scene's topmost hit at its posted coordinate")
        else:
            plot_domain = 1 << 32
            plot_prefix = 0x5A57000000000000
            require(matches_input[0][4] == "world" and key == delivered_key and
                    (key & 0xFFFF000000000000) == plot_prefix and
                    (key & 0x0000FFFF00000000) == plot_domain,
                    "Rectangle-free scene input is not the requested and delivered world plot key")
            plot_index = key & 0xFFFFFFFF
            require(sum(1 for p in doc.get("plots", []) if isinstance(p, list) and len(p) == 5 and
                        p[0] == plot_index and p[3:] == [1, 1]) == 1,
                    "Terrain pixel key does not identify exactly one currently visible plot in its scene")
            scene_path = next(path for scene_doc, path in scenes.values()
                              if scene_doc["generation"] == generation)
            pick_name = doc.get("pixelHitFile")
            require(isinstance(pick_name, str) and pick_name == scene_path.with_suffix(".pick").name,
                    "Rectangle-free plot click lacks the exact generation-bound terrain raster filename")
            pick_path = base.generated(result, scene_path.with_suffix(".pick"), runtime)
            require(base.pixel_key(pick_path, doc, hx, hy) == key,
                    "Native plot callback differs from the independently decoded terrain pixel ID")
            require(not any(h[1] - 3 <= hx < h[3] + 3 and h[2] - 3 <= hy < h[4] + 3
                            for h in doc["hits"] if isinstance(h, list) and len(h) == 5),
                    "Terrain pixel click overlaps a higher-priority native UI hit rectangle")
        posted_hits.append({"generation": generation, "key": key, "client": [x, y], "logical": [hx, hy],
                            "delivered_key": delivered_key, "input_surface": matches_input[0][4]})
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
            "research_tree_requested": research_tree,
            "research_tree_handoff_and_open_selection_verified": research_tree,
            "research_tree_escape_and_world_return_verified": research_tree,
            "research_tree_native_escape_timer": tree_timer_proof,
            "research_callback_dispatch": {"generation": research_scene["generation"],
                                           "requested": research_target, "delivered": research_delivered,
                                           "native_topmost_hit_verified": True},
            "city_name_localization_db_crosscheck": city_name_proof,
            "human_input_verified": False, "retail_renderer_equivalence_verified": False, "full_gameplay_verified": False}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", required=True)
    parser.add_argument("--source-run")
    parser.add_argument("--research-tree", action="store_true",
                        help="Verify the original TechPopup→TechTree selection path in the continuous HWND run")
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
        row = verify_run(args.run, proof, research_tree=args.research_tree)
        source_row = None
        if args.source_run:
            source_request, source_result, source_out, _, _, source_runtime, _ = read_run(
                args.source_run, research_tree=args.research_tree)
            source_row = verify_run(args.source_run, proof, research_tree=args.research_tree)
            current_request, current_result, current_out, _, _, current_runtime, _ = read_run(
                args.run, research_tree=args.research_tree)
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
            require(source_result.get("pid") != current_result.get("pid") and
                    source_result.get("pid") != current_result.get("driver_pid") and
                    current_result.get("pid") != source_result.get("driver_pid"),
                    "Source and restored Host/driver did not use distinct process identities")
            require(current_result.get("fresh_process_restore_verified") is True and current_result.get("semantic_restore_equal") is True and
                    current_result.get("checkpoint_input_unchanged") is True, "Fresh-process decision restore equality is not proven")
            require("INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=true" in current_out, "Restored state changed during idle startup")
            require("INTERACTIVE_RESTORE_CHECKPOINT" in current_out and "INTERACTIVE_RESTORE_SECTIONS_EQUAL" in current_out,
                    "Restore stdout omits independently checked checkpoint/section markers")
            source_result_files = [Path(r["path"]).resolve(strict=True) for r in source_result.get("generated_files", [])
                                   if Path(r.get("path", "")).name == "play-final-state.txt"]
            current_result_files = [Path(r["path"]).resolve(strict=True) for r in current_result.get("generated_files", [])
                                    if Path(r.get("path", "")).name == "play-initial-state.txt"]
            require(len(source_result_files) == len(current_result_files) == 1 and
                    source_result_files[0].read_bytes() == current_result_files[0].read_bytes(),
                    "Fresh process initial semantic state does not byte-match the source run final state")
            resume = current_request.get("resume_from")
            require(isinstance(resume, dict) and resume.get("run_id") == args.source_run,
                    "Restore request lacks its immutable source checkpoint contract")
            source_evidence = EVIDENCE / args.source_run
            copied_result = exact_artifact(resume.get("run_result"), source_evidence.parent / args.run / "resume-source-result.json",
                                           "frozen source result")
            original_result = source_evidence / "result.json"
            require(copied_result.read_bytes() == original_result.read_bytes() and digest(copied_result) == digest(original_result),
                    "Frozen source result copy differs from the source run result bytes")
            source_final_paths = [Path(path) for turn, path in rows(source_out, "INTERACTIVE_NATIVE_SAVE",
                                  r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$")]
            require(len(source_final_paths) >= 2, "Source run has no repeated final native save records")
            source_checkpoint = source_final_paths[-1].resolve(strict=True)
            source_final_result = read_run(args.source_run, research_tree=args.research_tree)[1]
            base.generated(source_final_result, source_checkpoint, source_runtime)
            source_checkpoint_ref = exact_artifact(resume.get("checkpoint_source"), source_checkpoint, "source native checkpoint")
            current_runtime_checkpoint = current_runtime / "checkpoint-input.zssave"
            checkpoint_input = exact_artifact(resume.get("checkpoint_input"), current_runtime_checkpoint, "private checkpoint input")
            require(source_checkpoint_ref.read_bytes() == checkpoint_input.read_bytes() and
                    digest(source_checkpoint_ref) == resume["checkpoint_source"].get("sha256") ==
                    digest(checkpoint_input) == resume["checkpoint_input"].get("sha256"),
                    "Source native save, declared checkpoint, and private runtime input are not byte-identical")
            checkpoint_state = exact_artifact(resume.get("checkpoint_source_state"), source_result_files[0], "source final semantic state")
            expected_state = exact_artifact(resume.get("expected_state"), EVIDENCE / args.run / "checkpoint-state.txt", "frozen expected state")
            require(checkpoint_state.read_bytes() == expected_state.read_bytes() == source_result_files[0].read_bytes(),
                    "Source final semantic state and frozen expected state differ")
            require(resume.get("turn") == int(source_row["final_turn"]), "Resume checkpoint turn differs from source final turn")
            src_state = sdk_snapshot(checkpoint_state)
            dst_state = sdk_snapshot(current_result_files[0])
            src_values = (int(src_state["rows"]["G"][0][1]), int(src_state["rows"]["G"][0][3]))
            dst_values = (int(dst_state["rows"]["G"][0][1]), int(dst_state["rows"]["G"][0][3]))
            require(src_values == dst_values == (int(source_row["final_turn"]), int(source_row["active_player"])) and
                    (source_row["city"], source_row["unit"], source_row["technology"]) ==
                    (row["city"], row["unit"], row["technology"]),
                    "Source and resumed city/unit/technology identities differ")
            verify_decision_snapshot(src_state, turn=int(source_row["final_turn"]), active=int(source_row["active_player"]),
                                     city=int(source_row["city"]), unit=int(source_row["unit"]), tech=int(source_row["technology"]))
            verify_decision_snapshot(dst_state, turn=int(row["startup_turn"]), active=int(row["active_player"]),
                                     city=int(row["city"]), unit=int(row["unit"]), tech=int(row["technology"]))
            source_save_header, _ = parse_native_archive(source_checkpoint)
            restored_paths = [Path(r["path"]).resolve(strict=True) for r in current_result.get("generated_files", [])
                              if Path(r.get("path", "")).name == "play-restored-checkpoint.zssave"]
            require(len(restored_paths) == 1 and restored_paths[0].is_relative_to(current_runtime / "sessions"),
                    "Restored roundtrip native archive is absent from the private session")
            restored_checkpoint = restored_paths[0]
            restore_marker = rows(current_out, "INTERACTIVE_RESTORE_CHECKPOINT", r"^INTERACTIVE_RESTORE_CHECKPOINT=(.+)$")
            require(len(restore_marker) == 1 and Path(restore_marker[0]).resolve(strict=True) == checkpoint_input,
                    "Native restore marker does not name the exact private checkpoint")
            reload_proof = verify_reload_archive_delta(source_checkpoint, restored_checkpoint,
                                                       current_request.get("language"), current_out)
            source_end = tuple(map(int, source_row["production_before_after"][1]))
            resumed_start = tuple(map(int, row["production_before_after"][0]))
            require(source_end == resumed_start, "Source final and resumed initial city production/research progress differ")
            row["source_run_id"] = args.source_run
            row["fresh_process_restore_verified"] = True
            row["source_and_restore_same_language"] = True
            row["source_host_pid"] = source_result.get("pid")
            row["source_final_checkpoint"] = artifact(source_checkpoint)
            row["private_checkpoint_input"] = artifact(checkpoint_input)
            row["roundtrip_restored_checkpoint"] = artifact(restored_checkpoint)
            row["source_city_unit_technology_identity"] = [source_row["city"], source_row["unit"], source_row["technology"]]
            row["source_restore_semantic_progress_equal"] = True
            row["independent_reload_archive_comparison"] = reload_proof
        else:
            row["fresh_process_restore_verified"] = False
        report = {"status": (("CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS" if args.source_run else
                               "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS") if args.research_tree else
                              ("CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_RESTORE_SMOKE_PASS" if args.source_run else
                               "CONTINUOUS_INTERACTIVE_SDK_DECISION_UI_SMOKE_PASS")),
                  "scope": "POSTED_HWND_ORIGINAL_CITY_PRODUCTION_TECHPOPUP_TECHTREE_RESEARCH_SELECTION_ESCAPE_ONE_TURN_NATIVE_SAVE_AND_CORE_UNLOAD" if args.research_tree else
                           "POSTED_HWND_ORIGINAL_CITY_PRODUCTION_AND_TECH_POPUP_CALLBACKS_ONE_TURN_NATIVE_SAVE_AND_CORE_UNLOAD",
                  "runs": [row], "independent_verifier": artifact(script_copy),
                  "frozen_helper_sources": helper_copies, "source_run_verified": source_row,
                  "source_provenance_verified": True, "original_ui_callback_payloads_verified": True,
                  "research_tree_sequence_verified": args.research_tree,
                  "research_tree_timer_release_verified": args.research_tree,
                  "city_name_localization_db_verified": bool(args.research_tree),
                  "native_packet_manifest_scene_and_same_device_verified": True, "production_research_and_next_turn_verified": True,
                  "native_133_section_saves_verified": True, "fresh_process_restore_verified": bool(args.source_run),
                  "human_input_verified": False, "retail_renderer_equivalence_verified": False, "full_gameplay_verified": False,
                  "limitations": ["Popup and world inputs are synthetic messages posted to the owned HWND.",
                                  "The private strategic renderer does not establish Civ V retail renderer or full gameplay equivalence.",
                                  "The proof covers only original production/research callbacks and one normal turn." if not args.research_tree else
                                  "This run checks one original TechTree selection and popup lifecycle; it does not prove general tree coverage or full gameplay."]}
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
