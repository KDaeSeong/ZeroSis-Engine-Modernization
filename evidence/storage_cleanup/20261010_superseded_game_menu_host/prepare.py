"""Plan only the six explicitly delegated superseded directories. No deletion."""
from __future__ import annotations
import base64
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
EXPECTED = Path(r"C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Engine Modernization")
assert ROOT == EXPECTED and OUT == ROOT / "evidence/storage_cleanup/20261010_superseded_game_menu_host"
sys.path.insert(0, str(ROOT / "tools"))
import prune_superseded_runtime_artifacts as low
# Helpers only: never call the historical plan/apply or retention-policy code.
OLD_HELPERS = ROOT / "evidence/storage_cleanup/20261010_failed_notification_runs/prepare.py"
spec = importlib.util.spec_from_file_location("reviewed_link_helpers", OLD_HELPERS)
links = importlib.util.module_from_spec(spec)
spec.loader.exec_module(links)
need = low.require
HOSTS = ("20261010T005010Z_6fb779d5bda3", "20261009T152915Z_262e1edd772f")
RUN = "20261009T153212Z_24547e20f8c7"
SESSION = "726832461d50343c06420b4247bc9161"
NEW_HOST = "20261010T010743Z_6160fe65056b"
NEW_REPORT_SHA = "db85655f7a6346d4010fdcd9abe1d9f5fe0ea6d93e880e7fd0cff80f42761836"
KEEP_HOST = "20261009T155317Z_8f390480966b"
KEEP_RUNS = ("20261009T163702Z_0461db127034", "20261009T155510Z_59a23754e9cf", "20261009T160013Z_804760e7018f")
TARGETS = tuple(ROOT / group / host for host in HOSTS for group in ("Build/UiWindowHost", "evidence/ui_window_host")) + (
    ROOT / "Build/InteractiveGameRuntime" / RUN, ROOT / "evidence/interactive_game" / RUN)
USER_GAME = Path.home() / "OneDrive/Documents/My Games/Sid Meier's Civilization 5"

def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))

def ident(info):
    return dict(device=str(info.st_dev), file_id=str(info.st_ino), bytes=info.st_size,
                mtime_ns=str(info.st_mtime_ns), links=info.st_nlink,
                attributes=info.st_file_attributes)

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
        current = Path(current); info = current.stat(follow_symlinks=False)
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
    with path.open("xb") as stream:
        stream.write(gzip.compress(raw, compresslevel=9, mtime=0) if packed else raw)
    return dict(path=str(path), bytes=path.stat().st_size, sha256=low.digest(path))

def process_audit():
    command = "[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); @(Get-CimInstance Win32_Process | Select-Object ProcessId,Name,ExecutablePath,CommandLine) | ConvertTo-Json -Compress"
    proc = subprocess.run(["powershell.exe", "-NoProfile", "-Command", command], capture_output=True,
                          encoding="utf-8", timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
    need(proc.returncode == 0, "Cannot inspect processes")
    values = json.loads(proc.stdout); values = values if isinstance(values, list) else [values]
    relevant = []
    for value in values:
        text = str(value.get("ExecutablePath") or "") + " " + str(value.get("CommandLine") or "")
        need(not any(identifier in text for identifier in (*HOSTS, RUN)), "Target is used by a current process")
        if str(ROOT).casefold() in text.casefold() or value["Name"].casefold() in ("zerosishost_x64.exe", "cl.exe", "link.exe", "c1xx.exe"):
            need(value.get("ExecutablePath") and value.get("CommandLine"), "Relevant process visibility incomplete")
            relevant.append(value)
    ea = [row for row in relevant if row["ProcessId"] == 11532]
    if ea:
        need(ea[0]["ExecutablePath"] == str(ROOT / "Build/InteractiveGameRuntime" / KEEP_RUNS[0] / "ZeroSisHost_x64.exe"),
             "PID 11532 identity changed")
    return dict(observed_process_count=len(values), relevant_processes=relevant, target_process_hits=[],
                protected_ea_pid11532_present=bool(ea), processes_stopped=False)

def request_audit():
    rows, own = [], []
    paths = sorted((ROOT / "evidence").glob("*/*/request.json"))
    need(paths, "No retained request documents")
    for path in paths:
        checked(path); raw = path.read_bytes(); value = json.loads(raw.decode("utf-8-sig"))
        hits = [identifier for identifier in (*HOSTS, RUN) if identifier in raw.decode("utf-8-sig")]
        item = record(path)
        item["target_identifiers"] = hits
        if inside(path):
            need(path == ROOT / "evidence/interactive_game" / RUN / "request.json", "Unexpected request inside targets")
            own.append(item)
        else:
            need(not hits, "Retained runtime request uses target: " + str(path))
            rows.append(item)
    need(len(own) == 1, "Missing retired-run request")
    # Current launch routing is a dependency too, not a historical report.
    for path in sorted((ROOT / "Play").rglob("*")) + [ROOT / "tools/Start-Engine.ps1"]:
        if path.is_file() and path.suffix.lower() in (".json", ".ps1", ".cmd"):
            raw = path.read_text(encoding="utf-8-sig")
            need(not any(identifier in raw for identifier in (*HOSTS, RUN)), "Current launcher references a target")
    return dict(retained_requests=rows, retiring_request=own[0], retained_reference_hits=[],
                scan_scope="all evidence/*/*/request.json plus current Play launch controls")

def session_audit():
    evidence = ROOT / "evidence/interactive_game" / RUN
    runtime = ROOT / "Build/InteractiveGameRuntime" / RUN
    request, result, attempt, driver = (read(evidence / name) for name in ("request.json", "result.json", "attempt.json", "driver_result.json"))
    need(request["smoke"] is True and request["run_id"] == RUN and "--mode" in request["command"] and
         request["command"][request["command"].index("--mode") + 1] == "play-smoke", "Not an explicit automated smoke request")
    need(driver["command"] == [str(runtime / "ZeroSisHost_x64.exe"), "--play-smoke", "ko_KR"], "Driver command is not the recorded smoke")
    need(attempt["status"] == "FINISHED" and not attempt["timed_out"] and attempt["returncode"] == 0 and
         result["status"] == "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_FAILED" and
         result["human_input_verified"] is False, "Run did not reach its documented terminal failed state")
    sessions = sorted((runtime / "sessions").iterdir())
    need(sessions == [runtime / "sessions" / SESSION], "Unaccounted session; possible manual data")
    stdout = (evidence / "stdout.log").read_text(encoding="utf-8-sig")
    need("SESSION_DIRECTORY=" + str(sessions[0]) in stdout and
         "INTERACTIVE_SMOKE_SEQUENCE=SELECT_MOVE_EXPLICIT_SKIP_END_TURN_SAVE_WM_CLOSE" in stdout and
         "INTERACTIVE_PLAY_CLOSED=1|NATIVE_CHECKPOINT_WRITTEN" in stdout and
         "INTERACTIVE_GAME_SESSION_STOPPED=true" in stdout, "Missing complete smoke session provenance")
    expected = {row["path"]: row["sha256"] for row in result["generated_files"] if row["path"].endswith(".zssave")}
    saves = sorted(runtime.rglob("*.zssave"))
    need(len(saves) == len(expected) == 3 and {str(x) for x in saves} == set(expected), "Unaccounted save file")
    saved = [record(path) for path in saves]
    need(all(row["sha256"] == expected[row["path"]] for row in saved), "Save changed after automated result")
    return dict(session=str(sessions[0]), observed_session_count=1, observed_save_count=3,
                classification="EXACT_HASH_MATCHED_TERMINAL_AUTOMATED_SMOKE_OUTPUTS",
                separate_manual_sessions_observed=0, saves=saved, terminal_status=result["status"],
                failures=result["failures"], original_diagnostic_paths=[str(evidence / name) for name in
                ("request.json", "result.json", "attempt.json", "driver_result.json", "stdout.log", "stderr.log")])

def alias_audit(rows):
    groups = {}
    for row in rows:
        identity = row["identity"]; key = identity["device"], identity["file_id"]
        if key not in groups:
            groups[key] = dict(identity=identity, sha256=row["sha256"], target_paths=[], surviving_aliases=[],
                               stored_bytes=low.stored(Path(row["path"])))
        group = groups[key]
        need(group["identity"] == identity and group["sha256"] == row["sha256"], "Hardlink identity drift")
        group["target_paths"].append(row["path"])
    checked_parents = set()
    for group in groups.values():
        if group["identity"]["links"] == 1: continue
        sample = Path(group["target_paths"][0])
        names = links.hardlink_names(sample)
        need(len(names) == group["identity"]["links"], "Hardlink count drift")
        need({str(path).casefold() for path in names if inside(path)} == {path.casefold() for path in group["target_paths"]}, "Unexpected target alias")
        for path in names:
            if inside(path): continue
            for parent in path.parents:
                if parent in checked_parents: break
                value = parent.lstat()
                need(stat.S_ISDIR(value.st_mode) and not value.st_file_attributes & 0x400, "Reparse alias ancestor")
                checked_parents.add(parent)
            need(ident(low.regular(path)) == group["identity"], "Surviving alias identity differs")
            group["surviving_aliases"].append(str(path))
        need(ident(low.regular(sample)) == group["identity"], "Alias group changed during enumeration")
        group["links_after"] = group["identity"]["links"] - len(group["target_paths"])
    return list(groups.values())

def protection(cache):
    paths, sealed = set(), {}
    roots = [ROOT / "Source", USER_GAME / "Saves", USER_GAME / "ModdedSaves"]
    for host in (KEEP_HOST, NEW_HOST):
        roots += [ROOT / "Build/UiWindowHost" / host / "frozen"]
        paths.add(ROOT / "Build/UiWindowHost" / host / "final/ZeroSisHost_x64.exe")
        paths.add(ROOT / "evidence/ui_window_host" / host / "build_result.json")
    for root in roots:
        for path, info, directory in walk(root):
            if not directory: paths.add(path)
    for run in KEEP_RUNS:
        evidence = ROOT / "evidence/interactive_game" / run
        request_path = evidence / "request.json"; paths.add(request_path)
        request = read(request_path)
        for path, sha in low.refs(request):
            path = Path(path)
            if path.is_file():
                need(path not in sealed or sealed[path] == sha, "Conflicting protected dependency hashes")
                sealed[path] = sha
                paths.add(path)
        if (evidence / "result.json").exists(): paths.add(evidence / "result.json")
    # Preserve every other engine save, including old manual runtime sessions.
    paths.update(path for path in (ROOT / "Build/InteractiveGameRuntime").rglob("*.zssave") if not inside(path))
    paths.update(path for path in (ROOT / "Play").rglob("*") if path.is_file())
    paths.update((ROOT / "tools/Start-Engine.ps1", ROOT / "tools/prune_superseded_runtime_artifacts.py", OLD_HELPERS))
    records = []
    for path in sorted(paths):
        checked(path); need(not inside(path), "Protected path intersects deletion target")
        row = record(path, cache=cache)
        need(path not in sealed or row["sha256"] == sealed[path], "Protected sealed dependency changed: " + str(path))
        records.append(row)
    return records

def main():
    need(not (OUT / "plan.json").exists() and not (OUT / "application-started.json").exists(), "Plan already exists; do not replay")
    for path in TARGETS:
        need(path.parent in (ROOT / "Build/UiWindowHost", ROOT / "evidence/ui_window_host",
                            ROOT / "Build/InteractiveGameRuntime", ROOT / "evidence/interactive_game"), "Target scope expanded")
        checked(path)
    replacement = ROOT / "evidence/ui_window_host" / NEW_HOST / "build_result.json"
    need(low.digest(replacement) == NEW_REPORT_SHA and read(replacement)["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT",
         "Reviewed replacement build is not complete")
    session = session_audit(); requests = request_audit(); processes = process_audit()
    print("READ_ONLY_AUDIT=references-and-session-pass", flush=True)
    rows, directories, cache = [], [], {}
    for target in TARGETS:
        for path, info, directory in walk(target):
            if directory:
                directories.append(dict(path=str(path), identity=ident(info)))
            else:
                rows.append(record(path, info, cache))
    print("READ_ONLY_AUDIT=target-hashes-complete|" + str(len(rows)), flush=True)
    groups = alias_audit(rows)
    print("READ_ONLY_AUDIT=hardlinks-complete|" + str(sum(len(g["surviving_aliases"]) for g in groups)), flush=True)
    protected = protection(cache)
    # Shared immutable aliases may intersect protected identities; unlinking
    # only the exact retired names preserves those bytes and attributes.
    candidate_ids = {(r["identity"]["device"], r["identity"]["file_id"]) for r in rows}
    aliases = {name for g in groups for name in g["surviving_aliases"]}
    for row in protected:
        if (row["identity"]["device"], row["identity"]["file_id"]) in candidate_ids:
            need(row["path"] in aliases, "Protected file is not a verified surviving alias")
    for row in rows:
        need(ident(low.regular(Path(row["path"]))) == row["identity"], "Target changed before sealing plan")
    requests2 = request_audit(); need(requests2 == requests, "Requests changed while planning")
    processes = process_audit()
    inventory = write_new("inventory.json.gz", dict(files=rows, directories=directories, groups=groups), True)
    preservation = write_new("protection.json.gz", dict(files=protected, requests=requests, session=session, processes=processes), True)
    diagnostic_paths = {Path(x) for x in session["original_diagnostic_paths"]}
    for host in HOSTS:
        diagnostic_paths.update(path for path in (ROOT / "evidence/ui_window_host" / host).iterdir() if path.is_file())
    diagnostics = []
    for path in sorted(diagnostic_paths):
        raw = path.read_bytes()
        diagnostics.append(dict(path=str(path), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                                content_base64=base64.b64encode(raw).decode("ascii")))
    diagnostic = write_new("diagnostics.json.gz", dict(status="ORIGINALS_CURRENTLY_PRESENT_PLANNED_RETIREMENT",
        note="After approved deletion these compressed diagnostics and hashes are historical records, not retained runtime/pixel/save files.",
        originals=diagnostics), True)
    artifacts = {name: dict(path=str(OUT / name), sha256=low.digest(OUT / name)) for name in ("prepare.py", "apply.py")}
    plan = dict(schema="ZEROSIS_EXPLICIT_SIX_FOLDER_RETIREMENT_V1", status="READY_FOR_ROOT_REVIEW_NO_DELETION",
        created_utc=datetime.now(timezone.utc).isoformat(), project=str(ROOT), targets=[str(x) for x in TARGETS],
        inventory=inventory, protection=preservation, diagnostics=diagnostic, scripts=artifacts,
        helper_inputs=[dict(path=str(path), sha256=low.digest(path)) for path in (Path(low.__file__), OLD_HELPERS)],
        target_file_count=len(rows), target_directory_count=len(directories), logical_bytes=sum(r["identity"]["bytes"] for r in rows),
        unique_file_storage_bytes=sum(g["stored_bytes"] for g in groups),
        estimated_reclaimable_file_storage_bytes=sum(g["stored_bytes"] for g in groups if not g["surviving_aliases"]),
        surviving_alias_group_count=sum(bool(g["surviving_aliases"]) for g in groups),
        surviving_alias_path_count=sum(len(g["surviving_aliases"]) for g in groups),
        protected_file_count=len(protected), request_document_count=len(requests["retained_requests"])+1,
        retained_request_target_reference_count=0, excluded_candidates=[],
        automated_save_disposition=dict(count=3, reason=session["classification"], user_saves_deleted=False),
        replacement=dict(host=NEW_HOST, report_sha256=NEW_REPORT_SHA),
        protected=dict(ea_pid=11532, ea_runtime=KEEP_RUNS[0], latest_host=KEEP_HOST, latest_fresh=KEEP_RUNS[1],
                       latest_restore=KEEP_RUNS[2], source_root=str(ROOT/"Source"), user_save_roots=[str(x) for x in roots_for_users()]),
        volume_free_bytes_at_plan=shutil.disk_usage(ROOT).free,
        apply_contract=["Root approval is still required; preparation did not unlink, compress targets, launch a game or stop processes.",
                        "Explicit six roots only; fresh exact path/reparse/file ID/size/mtime/SHA/link/survivor checks before mutation.",
                        "Reject any new runtime request, unaccounted session/save, target process or candidate/protected drift.",
                        "Verify current replacement, EA, latest proof pair, Source and all other user saves.",
                        "Exclusive one-shot start marker; journal each file; no recursive delete and no resume/replay after partial failure.",
                        "Preserve all external hardlinks without attribute changes; report logical removal separately from free volume change.",
                        "After success mark original targets RETIRED; retain only this small diagnosis and full hash inventory."])
    result = write_new("plan.json", plan)
    print(json.dumps(dict(status=plan["status"], plan=result, files=len(rows),
        logical_bytes=plan["logical_bytes"], estimated_reclaimable_file_storage_bytes=plan["estimated_reclaimable_file_storage_bytes"],
        survivor_aliases=plan["surviving_alias_path_count"], protected=len(protected)), ensure_ascii=False), flush=True)

def roots_for_users():
    return (USER_GAME / "Saves", USER_GAME / "ModdedSaves")

if __name__ == "__main__":
    main()
