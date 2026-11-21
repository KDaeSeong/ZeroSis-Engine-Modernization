"""Prepare one explicit 10-root menu-candidate retirement plan. Never delete target files."""
from __future__ import annotations
import base64
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
EXPECTED = Path(r"C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization")
if ROOT != EXPECTED or OUT != ROOT / "evidence/storage_cleanup/20261010_superseded_menu_candidates":
    raise RuntimeError("Unexpected exact project/output boundary")
sys.path.insert(0, str(ROOT / "tools"))
import prune_superseded_runtime_artifacts as low
# Only require/digest/regular/stored/refs and attribute-preserving unlink are reused.
# No historical plan, retention policy, default candidate list or apply entry is called.
need = low.require
RUNS = ("20261010T012414Z_6abf227bfb5d", "20261010T014720Z_fb875e0dba10", "20261010T021923Z_7dc72b3208dc")
HOSTS = ("20261010T010743Z_6160fe65056b", "20261010T014514Z_0a483def3217")
TARGET_IDS = RUNS + HOSTS
TARGETS = tuple(ROOT / group / run for run in RUNS for group in
                ("Build/InteractiveGameRuntime", "evidence/interactive_game")) + tuple(
                ROOT / group / host for host in HOSTS for group in ("Build/UiWindowHost", "evidence/ui_window_host"))
MANUAL_RUNS = (
    "20261003T154510Z_b1af9e8eb764", "20261003T230735Z_2003f24507ce", "20261004T000710Z_796f1ea91c5e",
    "20261007T202612Z_d895c0fe84ab", "20261009T123717Z_504abb2ccaf9", "20261009T132430Z_a0a5dd8fd007",
    "20261009T163702Z_0461db127034",
)
EA_RUN = MANUAL_RUNS[-1]
NEW_HOST = "20261010T023559Z_49c6a1742499"
NEW_FRESH = "20261010T023901Z_b061052028cb"
NEW_RESTORE = "20261010T024641Z_f3b22ca6ce28"
KEEP_RUNS = MANUAL_RUNS + ("20261009T155510Z_59a23754e9cf", "20261009T160013Z_804760e7018f", NEW_FRESH, NEW_RESTORE)
KEEP_HOSTS = ("20261009T155317Z_8f390480966b", NEW_HOST)
DYNAMIC_RUNS = ()  # Live runtime IDs are additionally discovered from actual processes.
UNIT_PACKAGE_ID = "480678966a78bedbee642040285010aa86f8a2cc34b0929c2774dcee8ab54266"
UNIT_MANIFEST = ROOT / "Build/UnitAssets" / UNIT_PACKAGE_ID / "unit-assets.manifest.json"
PINNED_PROTECTED = {
    ROOT / "Source/Host/UiScene.lua": "5891bb0902de798478a358d22d190ae62d85b205b99862391e2b3e4245e0ab6c",
    UNIT_MANIFEST: "d6df7f9123075e7cd328712c968b1ef8023f1e32da16ced2d95651f4ffa0c3f1",
    UNIT_MANIFEST.parent / "unit-assets.bin": UNIT_PACKAGE_ID,
}
KEEP_FROZEN_ROOTS = (
    UNIT_MANIFEST.parent,
    ROOT / "Build/UnitAssets/b36aa9c2b78af7e597357275abaf9763abd7c252f6eb721d49921cf2a06f4b94",
    ROOT / "Build/StockUnitExports/20261005T072135Z",
    ROOT / "Build/GrannyAnimationBridge/20261005T113900Z",
    ROOT / "evidence/granny_animation_bridge/20261005T113900Z",
    ROOT / "evidence/top_panel_scene/20261010_user_clip",
) + tuple(ROOT / "evidence/game_menu_scene" / name for name in (
    "20261010_native_012414", "20261010_native_014720", "20261010_restore_021923",
    "20261010_fresh_023901", "20261010_native_023901", "20261010_restore_024641"))
REPLACEMENTS = (
    (ROOT / "evidence/ui_window_host" / NEW_HOST / "build_result.json",
     "8cbfdcb06fa33a9809713ffbc48a462d5715df853dd642288eadcf1973033c68", "UI_WINDOW_HOST_CANDIDATE_BUILT"),
    (ROOT / "evidence/interactive_game" / NEW_FRESH / "result.json",
     "ce2110db6c7f658b6743fe73c74bd29cbe6fec9fbdf789ef509465328a43217c", "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS"),
    (ROOT / "evidence/interactive_game" / NEW_RESTORE / "result.json",
     "e156d5bc53293f8172fbe1f1bff6a60abf76721a3c6bf579dfdd6334cf0ec92b", "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS"),
)
USER_GAME = Path.home() / "OneDrive/Documents/My Games/Sid Meier's Civilization 5"
SCHEMA = "ZEROSIS_EXPLICIT_MENU_TEN_ROOT_RETIREMENT_V1"
RUN_SPECS = {
    RUNS[0]: dict(host=HOSTS[0], session="28cdbe1bee6b48668afbdef508fa9817", restore=None, saves=2,
        status="CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_FAILED", returncode=1,
        result_sha256="17eb187fc14215c1616ac74139bc78ca19baa914d237938592669361ce312e13",
        driver_status="INTERACTIVE_UI_DRIVER_FAILED", driver_error="Host process deadline expired",
        menu_frames=((15,50),(18,55),(20,57))),
    RUNS[1]: dict(host=HOSTS[1], session="f58bfcfe7aa008a8888d4364c822ed26", restore=None, saves=4,
        status="CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_PASS", returncode=0,
        result_sha256="bd19ce7bb4e93b48c320c550a906b021a324bcaddf15bb00e5754d999528e3dd",
        driver_status="INTERACTIVE_UI_DRIVER_PASS", driver_error=None,
        menu_frames=((15,50),(18,55),(20,57))),
    RUNS[2]: dict(host=HOSTS[1], session="2be86e9bc74ad7dfe4751ce53ecc382f", restore=RUNS[1], saves=3,
        status="CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_FAILED", returncode=1,
        result_sha256="cb5728244d4569834dbcd785a83aa05bd9a333f3c47cac60db3b24b247989f30",
        driver_status="INTERACTIVE_UI_DRIVER_FAILED", driver_error=None,
        menu_frames=((6,17),(9,23),(11,25))),
}

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def ident(info):
    return dict(device=str(info.st_dev), file_id=str(info.st_ino), bytes=info.st_size,
                mtime_ns=str(info.st_mtime_ns), links=info.st_nlink, attributes=info.st_file_attributes)

def inside(path):
    return any(Path(path).is_relative_to(target) for target in TARGETS)

def checked(path):
    path = Path(os.path.abspath(path))
    need(path.resolve(strict=True) == path, "Resolved path changed: " + str(path))
    for item in (path, *path.parents):
        need(not item.lstat().st_file_attributes & 0x400, "Reparse ancestor: " + str(item))
    return path

def walk(root):
    checked(root)
    for current, dirs, files in os.walk(root, followlinks=False):
        current = Path(current); info = current.lstat()
        need(stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400, "Invalid directory")
        yield current, info, True
        for name in dirs:
            value = (current / name).lstat()
            need(stat.S_ISDIR(value.st_mode) and not value.st_file_attributes & 0x400, "Reparse directory")
        for name in files:
            path = current / name
            yield path, low.regular(path), False

def record(path, info=None, cache=None):
    info = low.regular(path) if info is None else info
    identity = ident(info)
    key = tuple(identity.values())
    if cache is None: cache = {}
    if key not in cache: cache[key] = low.digest(path)
    need(ident(low.regular(path)) == identity, "Changed while hashing: " + str(path))
    return dict(path=str(path), identity=identity, sha256=cache[key])

def write_new(name, data, packed=False):
    path = OUT / name
    need(path.parent == OUT, "Output path escaped")
    raw = (json.dumps(data, ensure_ascii=False, separators=(",", ":") if packed else None,
                      indent=None if packed else 2) + "\n").encode("utf-8")
    content = gzip.compress(raw, compresslevel=9, mtime=0) if packed else raw
    if packed: need(gzip.decompress(content) == raw, "Gzip roundtrip failed")
    with path.open("xb") as stream: stream.write(content)
    need(path.read_bytes() == content, "Written plan artifact differs")
    return dict(path=str(path), bytes=len(content), sha256=low.digest(path),
                uncompressed_bytes=len(raw), uncompressed_sha256=hashlib.sha256(raw).hexdigest())

def hardlink_names(path):
    kernel = low.K
    kernel.FindFirstFileNameW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR]
    kernel.FindFirstFileNameW.restype = wintypes.HANDLE
    kernel.FindNextFileNameW.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR]
    kernel.FindNextFileNameW.restype = wintypes.BOOL
    kernel.FindClose.argtypes = [wintypes.HANDLE]; kernel.FindClose.restype = wintypes.BOOL
    size = wintypes.DWORD(32768); buffer = ctypes.create_unicode_buffer(size.value)
    handle = kernel.FindFirstFileNameW(str(path), 0, ctypes.byref(size), buffer)
    if handle == ctypes.c_void_p(-1).value: raise ctypes.WinError(ctypes.get_last_error())
    result = []
    try:
        while True:
            result.append(Path(path.anchor) / buffer.value.lstrip("\\"))
            size.value = 32768
            if not kernel.FindNextFileNameW(handle, ctypes.byref(size), buffer):
                need(ctypes.get_last_error() == 38, "Unexpected hardlink enumeration failure")
                break
    finally: kernel.FindClose(handle)
    return sorted(set(result), key=lambda item: str(item).casefold())

def process_audit():
    command = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); @(Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath,CommandLine) | ConvertTo-Json -Compress"
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True,
                          encoding="utf-8", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    need(proc.returncode == 0, "Cannot inspect processes")
    values = json.loads(proc.stdout); values = values if isinstance(values, list) else [values]
    relevant, active_runs = [], set(DYNAMIC_RUNS)
    for value in values:
        text = str(value.get("ExecutablePath") or "") + " " + str(value.get("CommandLine") or "")
        need(not any(identifier.casefold() in text.casefold() for identifier in TARGET_IDS),
             "Candidate is used by a current process")
        if str(ROOT).casefold() in text.casefold() or value["Name"].casefold() in ("zerosishost_x64.exe", "cl.exe", "link.exe", "c1xx.exe"):
            need(value.get("ExecutablePath") and value.get("CommandLine"), "Relevant process visibility incomplete")
            relevant.append(value)
        executable = value.get("ExecutablePath") or ""
        match = re.search(r"InteractiveGameRuntime\\([^\\]+)\\ZeroSisHost_x64\.exe$", executable, re.I)
        if match: active_runs.add(match.group(1))
    ea = [row for row in relevant if row["ProcessId"] == 11532]
    if ea:
        need(Path(ea[0]["ExecutablePath"]) == ROOT / "Build/InteractiveGameRuntime" / EA_RUN / "ZeroSisHost_x64.exe",
             "PID 11532 identity changed")
    need(not set(active_runs).intersection(TARGET_IDS), "Active session entered target roots")
    return dict(relevant_processes=relevant, target_process_hits=[], active_runtime_ids=sorted(active_runs),
                protected_ea_pid11532_present=bool(ea), processes_stopped=False)

def request_audit():
    rows, own = [], []
    paths = sorted((ROOT / "evidence").glob("*/*/request.json"))
    need(paths, "No retained request documents")
    for path in paths:
        checked(path); raw = path.read_bytes(); text = raw.decode("utf-8-sig")
        value = json.loads(text); hits = [identifier for identifier in TARGET_IDS if identifier in text]
        item = record(path); item["target_identifiers"] = hits
        if inside(path):
            need(path.parent.name in RUNS and path == ROOT / "evidence/interactive_game" / path.parent.name / "request.json",
                 "Unexpected request inside targets")
            own.append(item)
        else:
            need(not hits, "Retained request references a candidate: " + str(path))
            rows.append(item)
    need({Path(row["path"]).parent.name for row in own} == set(RUNS), "Missing retiring request")
    for path in sorted((ROOT / "Play").rglob("*")) + [ROOT / "tools/Start-Engine.ps1"]:
        if path.is_file() and path.suffix.lower() in (".json", ".ps1", ".cmd"):
            text = path.read_text(encoding="utf-8-sig")
            need(not any(identifier in text for identifier in TARGET_IDS), "Launcher references a candidate")
    return dict(retained_requests=rows, retiring_requests=own, retained_reference_hits=[],
                scan_scope="all evidence/*/*/request.json and Play launch controls; new nonreferencing requests are allowed")

def replacement_audit():
    rows = []
    for path, sha, status in REPLACEMENTS:
        checked(path); document = read(path)
        need(low.digest(path) == sha and document["status"] == status, "Protected replacement report changed")
        if path.name == "result.json":
            need(document["returncode"] == 0 and document["timed_out"] is False and not document["failures"] and
                 document["game_menu_sequence_verified"] is True and document["game_menu_state_equal"] is True and
                 document["human_input_verified"] is False, "Replacement lost its automated GameMenu PASS boundary")
            request = read(path.parent / "request.json")
            need(request["smoke"] is True and request["game_menu_smoke"] is True, "Replacement is not the menu smoke")
            copied_host = path.parent / "host_build.json"
            need(low.digest(copied_host) == REPLACEMENTS[0][1], "Replacement does not use the accepted Host")
            if path.parent.name == NEW_RESTORE:
                need(request["resume_from"]["run_id"] == NEW_FRESH, "Replacement restore is not paired with its fresh run")
        else:
            need(document["source_inputs_unchanged"] is True, "Replacement Host inputs are not sealed")
        rows.append(dict(path=str(path), sha256=sha, status=status))
    return rows


def sessions_audit():
    audited = []
    for run, spec in RUN_SPECS.items():
        evidence = ROOT / "evidence/interactive_game" / run
        runtime = ROOT / "Build/InteractiveGameRuntime" / run
        need(low.digest(evidence / "result.json") == spec["result_sha256"], "Original terminal result changed")
        request, result, attempt, driver = (read(evidence / name) for name in
                                            ("request.json", "result.json", "attempt.json", "driver_result.json"))
        mode = "play-load-smoke" if spec["restore"] else "play-smoke"
        need(request["smoke"] is True and request["game_menu_smoke"] is True and request["top_panel"] is True and
             request["run_id"] == run and request["command"][request["command"].index("--mode") + 1] == mode,
             "Candidate is not the explicit automated menu smoke")
        command = [str(runtime / "ZeroSisHost_x64.exe"), "--" + mode, "ko_KR"]
        if spec["restore"]: command.append(str(runtime / "checkpoint-input.zssave"))
        need(driver["command"] == command and driver["status"] == spec["driver_status"] and
             driver["error"] == spec["driver_error"] and driver["returncode"] == spec["returncode"],
             "Candidate driver terminal boundary changed")
        need(attempt["status"] == "FINISHED" and attempt["timed_out"] is False and
             attempt["returncode"] == spec["returncode"] and result["returncode"] == spec["returncode"] and
             result["timed_out"] is False and result["status"] == spec["status"] and
             result["human_input_verified"] is False and bool(result["failures"]) == bool(spec["returncode"]),
             "Candidate terminal automated state changed")
        host_report = ROOT / "evidence/ui_window_host" / spec["host"] / "build_result.json"
        need(low.digest(evidence / "host_build.json") == low.digest(host_report), "Candidate Host identity changed")
        need(low.digest(runtime / "ZeroSisHost_x64.exe") == read(host_report)["executable"]["sha256"],
             "Candidate runtime does not use its recorded Host")
        sessions = sorted((runtime / "sessions").iterdir())
        session = runtime / "sessions" / spec["session"]
        need(sessions == [session], "Unaccounted session; possible manual data")
        stdout = (evidence / "stdout.log").read_text(encoding="utf-8-sig")
        need("SESSION_DIRECTORY=" + str(session) in stdout, "Smoke session lacks its native owner marker")
        if spec["returncode"] == 0:
            need("INTERACTIVE_SMOKE_SEQUENCE=SELECT_MOVE_EXPLICIT_SKIP_END_TURN_SAVE_WM_CLOSE" in stdout and
                 re.search(r"INTERACTIVE_PLAY_CLOSED=\d+\|NATIVE_CHECKPOINT_WRITTEN", stdout) and
                 "INTERACTIVE_GAME_SESSION_STOPPED=true" in stdout, "Passing smoke was not closed normally")
        expected = {row["path"]: row["sha256"] for row in result["generated_files"] if row["path"].endswith(".zssave")}
        if spec["restore"]:
            need(request["resume_from"]["run_id"] == spec["restore"], "Restore depends on an unexpected run")
            item = request["resume_from"]["checkpoint_input"]
            need(item["path"] == str(runtime / "checkpoint-input.zssave"), "Checkpoint input escaped runtime")
            expected[item["path"]] = item["sha256"]
        saves = sorted(runtime.rglob("*.zssave"))
        need(len(saves) == len(expected) == spec["saves"] and {str(x) for x in saves} == set(expected),
             "Unaccounted save file")
        saved = [record(checked(path)) for path in saves]
        need(all(row["sha256"] == expected[row["path"]] for row in saved), "Automated save changed")
        diagnostic_names = ("request.json", "result.json", "attempt.json", "driver_result.json", "stdout.log", "stderr.log",
                            "host_build.json", "interactive_ui_support.json", "runner.py", "game_menu_timeline.py",
                            "notification_panel_timeline.py", "action_info_panel_timeline.py")
        audited.append(dict(run_id=run, host_id=spec["host"], session=str(session), terminal_status=spec["status"],
                            terminal_returncode=spec["returncode"], original_failures=result["failures"],
                            observed_session_count=1, observed_save_count=len(saved), saves=saved,
                            classification="EXACT_HASH_MATCHED_TERMINAL_AUTOMATED_SMOKE_OUTPUTS_NOT_ALL_PASS",
                            separate_manual_sessions_observed=0,
                            original_diagnostic_paths=[str(evidence / name) for name in diagnostic_names]))
    return audited


def diagnostic_paths(sessions):
    paths = {Path(name) for session in sessions for name in session["original_diagnostic_paths"]}
    pixels = []
    for run, spec in RUN_SPECS.items():
        session = ROOT / "Build/InteractiveGameRuntime" / run / "sessions" / spec["session"]
        driver = read(ROOT / "evidence/interactive_game" / run / "driver_result.json")
        scenes = {row["sequence"]: row for row in driver["scene_requests"]}
        for frame, sequence in spec["menu_frames"]:
            folder = session / ("play-ui-" + str(sequence))
            scene = scenes[sequence]
            need(scene["context"] == "game-menu" and Path(scene["folder"]) == folder and not scene["closed"],
                 "Selected historical menu pixel no longer matches its driver record")
            frame_name = "play-scene-" + str(frame)
            pixel = session / (frame_name + "-gpu.png")
            frame_json = session / (frame_name + ".json")
            need(read(frame_json)["generation"] == frame, "Selected native GPU frame generation changed")
            paths.update((pixel, frame_json))
            paths.add(session / ("play-ui-" + str(sequence) + ".json"))
            for name in ("scene_manifest.json", "driver_record.json", "preparation_inputs.json", "scene.packet"):
                paths.add(folder / name)
            pixels.append(pixel)
        paths.update((session / "game-menu-before.txt", session / "game-menu-after.txt"))
    for host in HOSTS:
        evidence = ROOT / "evidence/ui_window_host" / host
        paths.update(path for path in evidence.iterdir() if path.is_file())
        for row in read(evidence / "build_result.json")["sources"]:
            if Path(row["path"]).name in ("BitmapWindow.cpp", "InteractiveGameLoop.h"):
                paths.add(Path(row["path"]))
    need(len(pixels) == 9 and sum(path.stat().st_size for path in pixels) <= 8 * 1024 * 1024,
         "Selected historical pixel budget expanded")
    need(all(inside(path) for path in paths), "Diagnostic source escaped exact retirement roots")
    need(sum(path.stat().st_size for path in paths) <= 48 * 1024 * 1024, "Original diagnostic budget expanded")
    return sorted(paths), [str(path) for path in pixels]

def user_save_audit():
    paths = set()
    for run in MANUAL_RUNS:
        runtime = checked(ROOT / "Build/InteractiveGameRuntime" / run)
        paths.update(runtime.rglob("*.zssave"))
    for name in ("Saves", "ModdedSaves"):
        paths.update((USER_GAME / name).rglob("*.zssave"))
    need(len(paths) >= 10 and all(not inside(path) for path in paths), "Protected native-user-save set shrank or overlaps")
    candidate_bundles = {low.digest(ROOT / "Build/InteractiveGameRuntime" / run / "bundle.manifest") for run in RUNS}
    rows = []
    for path in sorted(paths):
        checked(path); saved = record(path)
        with path.open("rb") as stream:
            header = stream.read(60)
            need(len(header) == 60 and header[:16] == b"ZEROSIS_SAVE_V1\0" and
                 struct.unpack_from("<I", header, 16)[0] == 1, "Invalid protected native save")
            kind, index, size = struct.unpack_from("<III", header, 48)
            need(kind == 1 and index == 0 and 1 <= size <= 16384, "Invalid native bundle section")
            bundle = stream.read(size); need(len(bundle) == size, "Truncated protected save")
        identity = hashlib.sha256(bundle).hexdigest()
        need(identity not in candidate_bundles, "A real user save depends on a candidate engine bundle")
        saved["bundle_sha256"] = identity; rows.append(saved)
    return dict(count=len(rows), distinct_bundle_count=len({row["bundle_sha256"] for row in rows}),
                candidate_bundle_matches=0, files=rows)

def alias_audit(rows):
    groups = {}
    for row in rows:
        identity = row["identity"]; key = identity["device"], identity["file_id"]
        if key not in groups:
            groups[key] = dict(identity=identity, sha256=row["sha256"], target_paths=[], surviving_aliases=[],
                               stored_bytes=low.stored(Path(row["path"])))
        group = groups[key]
        if group["identity"] != identity or group["sha256"] != row["sha256"]:
            raise RuntimeError("Hardlink identity drift: " + json.dumps(dict(first_path=group["target_paths"][0],
                first_identity=group["identity"], first_sha256=group["sha256"], second=row), ensure_ascii=False))
        group["target_paths"].append(row["path"])
    checked_parents = set()
    for group in groups.values():
        if group["identity"]["links"] == 1: continue
        sample = Path(group["target_paths"][0]); names = hardlink_names(sample)
        need(len(names) == group["identity"]["links"], "Hardlink count drift")
        need({str(path).casefold() for path in names if inside(path)} ==
             {path.casefold() for path in group["target_paths"]}, "Unexpected target alias")
        for path in names:
            if inside(path): continue
            for parent in path.parents:
                if parent in checked_parents: break
                value = parent.lstat()
                need(stat.S_ISDIR(value.st_mode) and not value.st_file_attributes & 0x400, "Reparse alias ancestor")
                checked_parents.add(parent)
            need(ident(low.regular(path)) == group["identity"], "Surviving alias differs")
            group["surviving_aliases"].append(str(path))
        need(ident(low.regular(sample)) == group["identity"], "Alias group changed during enumeration")
    return list(groups.values())

def protection(cache, processes, users, requests):
    paths, sealed = set(PINNED_PROTECTED), dict(PINNED_PROTECTED)
    for base in (ROOT / "Source", USER_GAME / "Saves", USER_GAME / "ModdedSaves", *KEEP_FROZEN_ROOTS):
        for path, info, directory in walk(base):
            if not directory: paths.add(path)
    for host in KEEP_HOSTS:
        base = ROOT / "Build/UiWindowHost" / host
        for path, info, directory in walk(base / "frozen"):
            if not directory: paths.add(path)
        paths.update((base / "final/ZeroSisHost_x64.exe", ROOT / "evidence/ui_window_host" / host / "build_result.json"))
    active = set(processes["active_runtime_ids"]) | set(DYNAMIC_RUNS)
    for run in KEEP_RUNS:
        evidence = ROOT / "evidence/interactive_game" / run
        request_path = evidence / "request.json"; paths.add(request_path)
        for name, sha in low.refs(read(request_path)):
            path = Path(name)
            # Request references are sealed inputs. Mutable session/output files
            # are outside the target boundary and must never enter fixed hashes.
            need(not any(path.is_relative_to(ROOT / "Build/InteractiveGameRuntime" / dynamic / "sessions")
                         for dynamic in active), "Mutable session unexpectedly referenced as a frozen input")
            if path.is_file():
                need(path not in sealed or sealed[path] == sha, "Conflicting frozen dependency hashes")
                sealed[path] = sha; paths.add(path)
        if run not in active and (evidence / "result.json").is_file(): paths.add(evidence / "result.json")
    for row in requests["retained_requests"]: paths.add(Path(row["path"]))
    # Preserve other existing saves; current automated sessions are protected as
    # whole excluded roots, not frozen output bytes. Real-user saves are explicit.
    for directory in (ROOT / "Build/InteractiveGameRuntime").iterdir():
        if directory.is_dir() and directory.name not in active:
            paths.update(path for path in directory.rglob("*.zssave") if not inside(path))
    paths.update(Path(row["path"]) for row in users["files"])
    paths.update(path for path in (ROOT / "Play").rglob("*") if path.is_file())
    paths.update((ROOT / "tools/Start-Engine.ps1", Path(low.__file__)))
    records = []
    for path in sorted(paths):
        checked(path); need(not inside(path), "Protected file intersects a candidate")
        row = record(path, cache=cache)
        need(path not in sealed or row["sha256"] == sealed[path], "Frozen protected dependency changed: " + str(path))
        records.append(row)
    return records

def main():
    need(not any((OUT / name).exists() for name in
                 ("plan.json", "inventory.json.gz", "protection.json.gz", "diagnostics.json.gz", "application-started.json",
                  "retired.json", "application-failed.json", "unlink-journal.jsonl")),
         "Plan outputs already exist; no historical-plan replay")
    need(len(TARGETS) == len(set(TARGETS)) == 10, "Explicit root count changed")
    checked(OUT)
    for path in TARGETS:
        need(path.parent in (ROOT / "Build/UiWindowHost", ROOT / "evidence/ui_window_host",
                             ROOT / "Build/InteractiveGameRuntime", ROOT / "evidence/interactive_game"), "Scope expanded")
        checked(path)
    replacements = replacement_audit()
    sessions = sessions_audit(); requests = request_audit(); processes = process_audit(); users = user_save_audit()
    print("READ_ONLY_AUDIT=sessions-requests-processes-user-saves-pass", flush=True)
    rows, directories, cache = [], [], {}
    for target in TARGETS:
        for path, info, directory in walk(target):
            if directory: directories.append(dict(path=str(path), identity=ident(info)))
            else: rows.append(record(path, info, cache))
    print("READ_ONLY_AUDIT=target-hashes-complete|" + str(len(rows)), flush=True)
    groups = alias_audit(rows)
    print("READ_ONLY_AUDIT=hardlinks-complete|" + str(sum(len(g["surviving_aliases"]) for g in groups)), flush=True)
    protected = protection(cache, processes, users, requests)
    candidate_ids = {(r["identity"]["device"], r["identity"]["file_id"]) for r in rows}
    aliases = {name.casefold() for g in groups for name in g["surviving_aliases"]}
    for row in protected:
        if (row["identity"]["device"], row["identity"]["file_id"]) in candidate_ids:
            need(row["path"].casefold() in aliases, "Protected file is not a surviving alias")
    for row in rows:
        need(ident(low.regular(Path(row["path"]))) == row["identity"], "Candidate changed before sealing")
    # New outside requests may appear while the protected fresh run completes.
    # They must not refer to any candidate; old protected request hashes persist.
    request_audit(); processes = process_audit()
    inventory = write_new("inventory.json.gz", dict(files=rows, directories=directories, groups=groups), True)
    preservation = write_new("protection.json.gz", dict(files=protected, requests=requests, sessions=sessions,
                                                      user_saves=users, processes=processes), True)
    originals_paths, selected_pixels = diagnostic_paths(sessions)
    originals = []
    for path in originals_paths:
        raw = path.read_bytes()
        item = dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                    content_base64=base64.b64encode(raw).decode("ascii"))
        restored = base64.b64decode(item["content_base64"], validate=True)
        need(restored == raw and hashlib.sha256(restored).hexdigest() == item["sha256"], "Raw diagnostic roundtrip failed")
        originals.append(item)
    diagnostic = write_new("diagnostics.json.gz", dict(status="ORIGINALS_PRESENT_PENDING_ROOT_REVIEW",
        note="After approved deletion these are historical diagnostics and hashes, not live runtime/save files; only the selected historical PNG bytes are retained.",
        selected_historical_pixels=selected_pixels,
        pixel_claim="Nine exact historical native GPU PNGs retained at reviewed menu/confirmation/unavailable frames; no claim of current UI equivalence or new desktop capture.",
        originals=originals), True)
    need(diagnostic["bytes"] <= 12 * 1024 * 1024, "Compressed diagnostic budget expanded")
    scripts = {name: dict(path=str(OUT / name), sha256=low.digest(OUT / name)) for name in ("prepare.py", "apply.py")}
    plan = dict(schema=SCHEMA, status="READY_FOR_ROOT_REVIEW_NO_DELETION",
        created_utc=datetime.now(timezone.utc).isoformat(), project=str(ROOT), targets=[str(x) for x in TARGETS],
        inventory=inventory, protection=preservation, diagnostics=diagnostic, scripts=scripts,
        helper_inputs=[dict(path=str(Path(low.__file__)), sha256=low.digest(Path(low.__file__)))],
        target_file_count=len(rows), target_directory_count=len(directories),
        logical_bytes=sum(row["identity"]["bytes"] for row in rows),
        unique_file_storage_bytes=sum(group["stored_bytes"] for group in groups),
        estimated_reclaimable_file_storage_bytes=sum(group["stored_bytes"] for group in groups if not group["surviving_aliases"]),
        surviving_alias_group_count=sum(bool(group["surviving_aliases"]) for group in groups),
        surviving_alias_path_count=sum(len(group["surviving_aliases"]) for group in groups),
        protected_file_count=len(protected), request_document_count=len(requests["retained_requests"]) + len(RUNS),
        retained_request_target_reference_count=0,
        automated_save_disposition=dict(count=sum(x["observed_save_count"] for x in sessions),
                                        reason="EXACT_HASH_MATCHED_TERMINAL_AUTOMATED_SMOKE_OUTPUTS_NOT_ALL_PASS", user_saves_deleted=False),
        protected_native_user_saves=dict(count=users["count"], bundles=users["distinct_bundle_count"], candidate_bundle_matches=0),
        protected=dict(ea_runtime=EA_RUN, runtime_ids=list(KEEP_RUNS), host_ids=list(KEEP_HOSTS),
                       frozen_roots=[str(path) for path in KEEP_FROZEN_ROOTS],
                       pinned_inputs={str(path): sha for path, sha in PINNED_PROTECTED.items()},
                       source_root=str(ROOT / "Source"), user_save_roots=[str(USER_GAME / name) for name in ("Saves", "ModdedSaves")],
                       mods_boundary=str(USER_GAME / "MODS"), dynamic_runtime_ids=list(DYNAMIC_RUNS),
                       dynamic_policy="Entire sessions and changing evidence are outside all 10 targets; only request/frozen inputs are hashed.",
                       additional_live_runtime_ids=processes["active_runtime_ids"]),
        replacements=replacements,
        volume_free_bytes_at_plan=shutil.disk_usage(ROOT).free,
        apply_contract=["Root reviews code and this exact plan SHA; preparation made no deletion.",
                        "Only the explicit 10 roots; verify path, reparse, identity, mtime, SHA, aliases and tree membership.",
                        "Reject candidate processes, unexpected candidate sessions/saves and any retained request/launcher reference.",
                        "Allow new outside requests only after scanning them for candidate references; changing live outputs remain outside deletion.",
                        "Preserve current EA, Host023559/fresh023901/restore024641, all manual bundles including regular20261007T202612, Source, user saves and external hardlinks.",
                        "Preserve original Warrior UnitAssets/provider/animation bridge, frozen TopPanel fix evidence and current GameMenu pixel/independent records.",
                        "Exclusive one-shot marker and per-file journal; no recursive deletion, no attribute changes, no replay after partial failure.",
                        "Report logical removal and allocation estimate separately from observed volume free-space change."])
    result = write_new("plan.json", plan)
    print(json.dumps(dict(status=plan["status"], plan=result, files=len(rows), protected=len(protected),
                          user_saves=users["count"], automated_saves=plan["automated_save_disposition"]["count"],
                          logical_bytes=plan["logical_bytes"], reclaimable_bytes=plan["estimated_reclaimable_file_storage_bytes"],
                          surviving_aliases=plan["surviving_alias_path_count"]), ensure_ascii=False), flush=True)

if __name__ == "__main__":
    main()
