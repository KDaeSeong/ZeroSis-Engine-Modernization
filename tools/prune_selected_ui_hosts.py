"""Create/apply one fresh, explicitly bounded UI Host retirement plan.

Only the four reviewed Host IDs are accepted. Planning snapshots their raw
builds plus matching UI Host evidence; application delegates deletion to the
existing guarded runtime pruner after rechecking this wrapper's scope.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import uuid

import prune_superseded_runtime_artifacts as safety

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ZEROSIS_SELECTED_UI_HOST_RETIREMENT_V1"
AUTHORIZED = (
    "20261011T095830Z_0e393114a58d",
    "20261011T104734Z_8c80ee26b062",
    "20261011T112831Z_f6767cca6e60",
    "20261011T123601Z_25d4e2bf0bdb",
)
KEEP_HOSTS = (
    "20261011T124501Z_5bf7bf678d40",
    "20261010T072241Z_8a97a1f4381e",
)
KEEP_RUNTIME_RUNS = (
    "20261011T124731Z_b821f4b6c26a",
    "20261011T125838Z_2f697438e208",
)
EXTERNAL_TOOL_SHA256 = {
    os.path.normcase(r"C:\Python314\python.exe"): "fda7026477256845afab371e354c4d512896665f1761939cb5887d0a9dec257a",
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)


def file_metadata(info):
    return dict(device=info.st_dev, file_id=info.st_ino, bytes=info.st_size, mtime_ns=info.st_mtime_ns,
                links=info.st_nlink, attributes=info.st_file_attributes, mode=info.st_mode)


def checked_file(path):
    path = safety.boundary(Path(path))
    info = safety.regular(path)
    require(info.st_ino != 0, "Unstable file ID: " + str(path))
    return path, info


def checked_directory(path):
    path = safety.boundary(Path(path))
    info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and not info.st_file_attributes & 0x400 and info.st_ino != 0,
            "Invalid/reparse directory: " + str(path))
    return path, info


def external_tool_snapshot(path, expected_sha256):
    path = Path(path)
    require(path.is_absolute(), "External dependency path is not absolute: " + str(path))
    path = Path(os.path.abspath(path))
    key = os.path.normcase(str(path))
    require(key in EXTERNAL_TOOL_SHA256, "Unexpected external dependency class: " + str(path))
    sealed_sha256 = EXTERNAL_TOOL_SHA256[key]
    require(isinstance(expected_sha256, str) and expected_sha256.lower() == sealed_sha256,
            "External tool reference SHA differs from reviewed seal: " + str(path))
    for ancestor in (path, *path.parents):
        ancestor_info = ancestor.lstat()
        require(not ancestor_info.st_file_attributes & 0x400,
                "External tool has a reparse point in its path: " + str(ancestor))
        if ancestor == Path(path.anchor):
            break
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not info.st_file_attributes & 0x400 and
            info.st_ino != 0 and info.st_nlink == 1,
            "External tool is not a stable single-link regular file: " + str(path))
    before = file_metadata(info)
    actual_sha256 = safety.digest(path)
    after = path.lstat()
    require(file_metadata(after) == before and actual_sha256 == sealed_sha256,
            "External tool identity/metadata/content differs from seal: " + str(path))
    return dict(path=str(path), sha256=actual_sha256, identity=list(identity(info)), metadata=before,
                role="readonly_external_runtime_tool")


def verify_external_tools(rows):
    for row in rows:
        current = external_tool_snapshot(row["path"], row["sha256"])
        require(current["identity"] == row["identity"] and current["metadata"] == row["metadata"],
                "External tool metadata changed: " + row["path"])


def external_refs_for_current_requests(manual):
    refs = {}
    for run in dict.fromkeys((*manual, *KEEP_RUNTIME_RUNS)):
        request = ROOT / "evidence/interactive_game" / run / "request.json"
        record = json.loads(safety.boundary(request).read_text(encoding="utf-8-sig"))
        require(record.get("run_id") == run, "Request ID differs from live runtime list: " + run)
        for field in ("runtime_inputs", "interactive_ui_support", "interactive_ui_support_inventory",
                      "provenance", "launcher_control_metadata"):
            for name, sha in safety.refs(record.get(field)):
                path = Path(name)
                if path.is_absolute() and not path.is_relative_to(ROOT):
                    refs.setdefault(os.path.normcase(str(path)), (path, sha))
    release = ROOT / "Play/EarlyAccess/release.json"
    if release.is_file():
        for name, sha in safety.refs(json.loads(release.read_text(encoding="utf-8-sig"))):
            path = Path(name)
            if path.is_absolute() and not path.is_relative_to(ROOT):
                refs.setdefault(os.path.normcase(str(path)), (path, sha))
    require(set(refs) == set(EXTERNAL_TOOL_SHA256),
            "Live requests/release external tool references differ from the reviewed class set")
    return [external_tool_snapshot(path, sha) for path, sha in refs.values()]


def snapshot_tree(root, require_single_link=False):
    root, _ = checked_directory(root)
    dirs, files = [], []
    for current, names, leaves in os.walk(root, followlinks=False):
        current, dinfo = checked_directory(current)
        dirs.append(dict(path=str(current), identity=list(identity(dinfo)), metadata=file_metadata(dinfo)))
        for name in names:
            checked_directory(current / name)
        for name in leaves:
            path, info = checked_file(current / name)
            if require_single_link:
                require(info.st_nlink == 1, "Target has another hardlink: " + str(path))
            digest = safety.digest(path)
            require(identity(checked_file(path)[1]) == identity(info), "File changed while hashing: " + str(path))
            files.append(dict(path=str(path), sha256=digest, identity=list(identity(info)),
                              metadata=file_metadata(info)))
    return dirs, files


def process_guard():
    safety.no_active_host()
    script = "@(Get-Process -Name Civ5,CivilizationV -ErrorAction SilentlyContinue).Count"
    bundled = Path(r"C:\Users\home\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe")
    shell = str(bundled) if bundled.is_file() else "powershell.exe"
    result = subprocess.run([shell, "-NoLogo", "-NoProfile", "-Command", script], capture_output=True,
                            text=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0 and result.stdout.strip() == "0",
            "Civ V native probe is active or process status is unknown")


def current_host_headers():
    report = ROOT / "evidence/ui_window_host" / KEEP_HOSTS[0] / "build_result.json"
    value = json.loads(safety.boundary(report).read_text(encoding="utf-8-sig"))
    rows = []
    for item in value.get("sources", []):
        name = item.get("original_source")
        if not isinstance(name, str) or Path(name).suffix.lower() not in (".h", ".hpp", ".hh"):
            continue
        path = safety.boundary(Path(name))
        require(path.is_relative_to(ROOT / "Source"), "Current Host header escaped Source")
        rows.append(dict(path=str(path), host_sha256=item["sha256"],
                         live_sha256=safety.digest(path), bytes=path.stat().st_size))
    require(rows, "Current Host report has no source headers to snapshot")
    return rows


def make_plan(host_ids):
    process_guard()
    require(tuple(sorted(host_ids)) == tuple(sorted(AUTHORIZED)) and len(host_ids) == len(AUTHORIZED),
            "Pass each of the four authorized --host-id values exactly once")
    start_engine = safety.boundary(ROOT / "tools/Start-Engine.ps1")
    manual = list(dict.fromkeys(safety.RUN.findall(start_engine.read_text(encoding="utf-8-sig"))))
    require(manual and "20261012T121847Z_732a6d5f07ea" in manual,
            "Live Start-Engine manual runtime list is missing the promoted EA 0.6 run")
    external_tools = external_refs_for_current_requests(manual)
    external_by_path = {os.path.normcase(row["path"]): row for row in external_tools}

    target_roots = []
    target_reports = {}
    for run in AUTHORIZED:
        build = safety.boundary(ROOT / "Build/UiWindowHost" / run)
        evidence = safety.boundary(ROOT / "evidence/ui_window_host" / run)
        report = safety.boundary(evidence / "build_result.json")
        value = json.loads(report.read_text(encoding="utf-8-sig"))
        require(value.get("build_id") == run and value.get("status") in
                ("UI_WINDOW_HOST_CANDIDATE_BUILT", "UI_WINDOW_HOST_BUILD_FAILED"),
                "Host report status/identity is not a reviewed terminal state: " + run)
        target_roots.extend((build, evidence))
        target_reports[run] = dict(status=value.get("status"), report=str(report), report_sha256=safety.digest(report))
    require(len(set(target_roots)) == 8, "Duplicate/overlapping Host targets")

    target_dirs, target_files = [], []
    for root in target_roots:
        dirs, files = snapshot_tree(root, require_single_link=True)
        target_dirs.extend(dirs)
        target_files.extend(files)
    require(target_files, "Selected Host targets contain no files")

    protected = {}
    protected_digest_cache = {}

    def protect(path, role, expected=None):
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        path, info = checked_file(candidate)
        require(not any(path == root or path.is_relative_to(root) for root in target_roots),
                "Protected file intersects selected Host target: " + str(path))
        cache_key = str(path)
        before = file_metadata(info)
        cached = protected_digest_cache.get(cache_key)
        if cached is None:
            sha = safety.digest(path)
            protected_digest_cache[cache_key] = dict(identity=list(identity(info)), metadata=before, sha256=sha)
        else:
            require(cached["identity"] == list(identity(info)) and cached["metadata"] == before,
                    "Protected file metadata changed within snapshot: " + str(path))
            sha = cached["sha256"]
        checked = checked_file(path)[1]
        require(identity(checked) == identity(info) and file_metadata(checked) == file_metadata(info),
                "Protected file metadata changed while hashing: " + str(path))
        require(expected is None or sha == expected.lower(), "Sealed hash mismatch: " + str(path))
        record = protected.setdefault(str(path), dict(path=str(path), sha256=sha,
                                                       identity=list(identity(info)), metadata=file_metadata(info), roles=[]))
        require(record["sha256"] == sha and record["identity"] == list(identity(info)),
                "Protected identity changed during snapshot")
        require(record["metadata"] == file_metadata(info), "Protected metadata changed during snapshot")
        if role not in record["roles"]:
            record["roles"].append(role)

    def protect_reference(path, role, expected=None):
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = ROOT / candidate
        if candidate.is_absolute() and not candidate.is_relative_to(ROOT):
            key = os.path.normcase(str(candidate.absolute()))
            row = external_by_path.get(key)
            require(row is not None, "Unexpected external dependency class: " + str(candidate))
            require(expected is None or row["sha256"] == expected.lower(),
                    "External dependency sealed hash mismatch: " + str(candidate))
            return
        protect(candidate, role, expected)

    closure_seeds = [ROOT / "evidence" / name for name in (
        "shared_lua_runtime/build_result.json", "explore_sdk/build_result.json",
        "city_site_sdk/build_result.json", "found_value_shared_sdk/build_result.json", "host/bundle.json",
        "database/candidate/build_result.json", "localization/provider/build_result.json",
        "streams/provider/build_result.json", "temp_heap/build_result.json")]
    closure_seeds += [ROOT / "evidence/ui_window_host" / run / "build_result.json" for run in KEEP_HOSTS]
    closure_seeds += [ROOT / "evidence/interactive_game" / run / "request.json" for run in (*manual, *KEEP_RUNTIME_RUNS)]
    closure_seeds = list(dict.fromkeys(safety.boundary(path) for path in closure_seeds if path.is_file()))
    expected_seed_count = 9 + len(set(manual) | set(KEEP_RUNTIME_RUNS) | set(KEEP_HOSTS))
    require(len(closure_seeds) >= expected_seed_count, "Current operational JSON seed set is incomplete")
    closure, visited = safety.closure(closure_seeds)
    history_root = ROOT / "Play/EarlyAccess/history"
    require(not any(Path(name).is_relative_to(history_root) for name in visited),
            "Operational dependency closure reached a historical release JSON; review its provenance explicitly")
    for path, expected in closure.items():
        protect(path, "current_host_manual_request_or_provider_execution_closure", expected)

    direct_paths = [ROOT / "Play/EarlyAccess/release.json"]
    direct_paths += sorted((ROOT / "Play/EarlyAccess/history").glob("*/release.json"))
    direct_paths += [ROOT / name for name in (
        "tools/Start-Engine.ps1", "Play/EarlyAccess/새 게임.cmd", "Play/EarlyAccess/이어하기.cmd",
        "Play/EarlyAccess/불러오기.cmd", "docs/EARLY_ACCESS_KR.md", "docs/ENGINE_COMPLETION_STATUS.md")]
    direct_paths += [ROOT / "evidence/runtime_promotion/20261012_early_access_06/runtime_validation.json",
                     ROOT / "evidence/runtime_promotion/20261012_early_access_06/launcher_before.json",
                     ROOT / "evidence/runtime_promotion/20261012_early_access_06/publication.json"]
    direct_paths = list(dict.fromkeys(safety.boundary(path) for path in direct_paths if path.is_file()))
    for path in direct_paths:
        protect(path, "direct_play_release_docs_launcher_or_provenance")
    current_release = ROOT / "Play/EarlyAccess/release.json"
    if current_release.is_file():
        for referenced, expected in safety.refs(json.loads(current_release.read_text(encoding="utf-8-sig"))):
            protect_reference(referenced, "current_release_direct_dependency", expected)

    # Retain complete latest Host build/evidence trees and their directory identities.
    protected_roots = []
    protected_dirs = []
    for run in KEEP_HOSTS:
        for root in (ROOT / "Build/UiWindowHost" / run, ROOT / "evidence/ui_window_host" / run):
            if root.is_dir():
                dirs, files = snapshot_tree(root)
                protected_roots.append(str(root))
                protected_dirs.extend(dirs)
                for row in files:
                    protect(row["path"], "current_host_baseline_fresh_or_restore_tree", row["sha256"])

    for run in KEEP_RUNTIME_RUNS:
        for root in (ROOT / "Build/InteractiveGameRuntime" / run, ROOT / "evidence/interactive_game" / run):
            require(root.is_dir(), "Protected fresh/restore runtime root is missing: " + str(root))
            dirs, files = snapshot_tree(root)
            protected_roots.append(str(root))
            protected_dirs.extend(dirs)
            for row in files:
                protect(row["path"], "fresh_or_restore_runtime_tree", row["sha256"])

    # All live manual bundle saves are protected, including older saved-version dependencies.
    manual_saves = []
    for run in manual:
        runtime = ROOT / "Build/InteractiveGameRuntime" / run
        evidence = ROOT / "evidence/interactive_game" / run
        require(runtime.is_dir() and evidence.is_dir(), "Live manual runtime/evidence is missing: " + run)
        for save in sorted(runtime.rglob("*.zssave")):
            protect(save, "actual_user_save")
            manual_saves.append(str(save))
    require(manual_saves, "No actual manual runtime saves were found")

    changed_headers = current_host_headers()
    changed_header_rows = []
    for row in changed_headers:
        path, info = checked_file(row["path"])
        protect(path, "current_host_source_header")
        changed_header_rows.append(dict(path=str(path), sha256=row["live_sha256"],
                                        host_frozen_sha256=row["host_sha256"],
                                        changed_since_current_host=row["live_sha256"] != row["host_sha256"],
                                        identity=list(identity(info))))

    # Protect every sealed runtime dependency in the live manual requests.
    for path in (start_engine, *direct_paths):
        protect(path, "live_manual_runtime_or_release_seed")
    for run in (*manual, *KEEP_RUNTIME_RUNS):
        request = ROOT / "evidence/interactive_game" / run / "request.json"
        record = json.loads(request.read_text(encoding="utf-8-sig"))
        require(record.get("run_id") == run, "Request ID differs from live runtime list: " + run)
        for field in ("runtime_inputs", "interactive_ui_support", "interactive_ui_support_inventory",
                      "provenance", "launcher_control_metadata"):
            for path, sha in safety.refs(record.get(field)):
                protect_reference(path, "sealed_manual_runtime_dependency", sha)

    candidate_ids = {(row["identity"][0], row["identity"][1]) for row in target_files}
    preserved_ids = {(row["identity"][0], row["identity"][1]) for row in protected.values()}
    external_ids = {(row["identity"][0], row["identity"][1]) for row in external_tools}
    preserved_ids |= external_ids
    require(not candidate_ids.intersection(preserved_ids), "Target identity aliases protected content")
    for root in target_roots:
        require(root not in [Path(p) for p in protected], "Target root appears in file protection set")
    require(len(protected) > 100, "Fresh protected closure unexpectedly small")

    # Recheck candidate metadata and content immediately before sealing the plan.
    for row in target_files:
        path, info = checked_file(row["path"])
        require(list(identity(info)) == row["identity"] and file_metadata(info) == row["metadata"] and
                safety.digest(path) == row["sha256"],
                "Selected Host changed during plan construction")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    output = ROOT / "evidence/storage_cleanup/selected_ui_host_plans" / stamp
    output.mkdir(parents=True, exist_ok=False)
    ledger_path = output / "retired-files.jsonl.gz"
    with gzip.open(ledger_path, "wt", encoding="utf-8") as stream:
        for row in sorted(target_files, key=lambda item: item["path"]):
            path = Path(row["path"])
            info = path.lstat()
            stream.write(json.dumps(dict(path=str(path.relative_to(ROOT)), sha256=row["sha256"], bytes=info.st_size,
                                         mtime_ns=info.st_mtime_ns, device=info.st_dev, file_id=info.st_ino,
                                         links=info.st_nlink, attributes=info.st_file_attributes, mode=info.st_mode,
                                         metadata=file_metadata(info)),
                                    separators=(",", ":")) + "\n")
    diagnostic_paths = [ROOT / "evidence/worker_production/20261011_receiver_native/retry/retirement_diagnostics.json",
                        ROOT / "evidence/worker_production/20261011_production_retention/retirement_diagnostics.json",
                        ROOT / "evidence/worker_production/20261011_receiver_native/retry/fresh_launch.json"]
    retained_diagnostics = []
    for path in diagnostic_paths:
        protect(path, "preserved_compact_retirement_diagnostic")
        retained_diagnostics.append(dict(path=str(path), bytes=path.stat().st_size, sha256=safety.digest(path)))
    candidate_ids = {(row["identity"][0], row["identity"][1]) for row in target_files}
    preserved_ids = {(row["identity"][0], row["identity"][1]) for row in protected.values()}
    preserved_ids |= {(row["identity"][0], row["identity"][1]) for row in external_tools}
    require(not candidate_ids.intersection(preserved_ids), "Target identity aliases protected content")
    protected_path = output / "protected-files.json.gz"
    with gzip.open(protected_path, "wt", encoding="utf-8") as stream:
        json.dump({name: row["sha256"] for name, row in protected.items()}, stream, separators=(",", ":"))
    protected_meta = output / "protected-metadata.json.gz"
    with gzip.open(protected_meta, "wt", encoding="utf-8") as stream:
        json.dump(protected, stream, ensure_ascii=False, separators=(",", ":"))
    diagnostics = dict(schema=SCHEMA, selected_hosts=target_reports,
                       retained_diagnostics=retained_diagnostics,
                       changed_source_headers=changed_header_rows,
                       manual_runtime_ids=manual, actual_user_saves=manual_saves,
                       keep_host_ids=list(KEEP_HOSTS), preserved_roots=protected_roots,
                       protected_file_count=len(protected), candidate_file_count=len(target_files),
                       candidate_directory_count=len(target_dirs), candidate_logical_bytes=sum(x["identity"][2] for x in target_files),
                       candidate_allocated_bytes=sum(safety.stored(x["path"]) for x in target_files),
                       readonly_external_tools=external_tools, outside_deletion_or_compression=False,
                       active_processes="none at plan creation", target_reparse_points=0,
                       target_hardlinks="all single-link", target_identity_collisions=0,
                       report_dirs_are_paired_targets=True, deletion_performed=False)
    diag_path = output / "diagnostics.json"
    diag_path.write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    target_paths = [str(path.relative_to(ROOT)) for path in target_roots]
    report = dict(schema=SCHEMA, status="PREVIEW_ONLY", created_utc=datetime.now(timezone.utc).isoformat(),
                  root=str(ROOT), selected_host_ids=list(AUTHORIZED), directories=[dict(path=p) for p in target_paths],
                  files=len(target_files), logical_bytes=sum(x["identity"][2] for x in target_files),
                  target_directory_snapshot=target_dirs,
                  estimated_reclaimable_file_storage=diagnostics["candidate_allocated_bytes"],
                  ledger=dict(path=str(ledger_path), sha256=safety.digest(ledger_path)),
                  protected=dict(path=str(protected_path), sha256=safety.digest(protected_path)),
                  protected_metadata=dict(path=str(protected_meta), sha256=safety.digest(protected_meta)),
                  diagnostics=dict(path=str(diag_path), sha256=safety.digest(diag_path)),
                  protected_directories=protected_dirs, protected_roots=protected_roots,
                  manual_runtime_ids=manual, current_host_ids=list(KEEP_HOSTS),
                  current_fresh_restore_runtime_ids=list(KEEP_RUNTIME_RUNS),
                  readonly_external_tools=external_tools, outside_deletion_or_compression=False,
                  changed_source_headers=changed_header_rows, actual_user_saves=manual_saves,
                  paired_evidence_targets=True, raw_builds_and_reports_retired_together=True,
                  retained_compact_diagnostics=diagnostics["retained_diagnostics"],
                  deletion_implemented=False, compression_implemented=False, files_removed=0,
                  wrapper_sha256=safety.digest(Path(__file__)), script_sha256=safety.digest(Path(safety.__file__)))
    plan_path = output / "plan.json"
    plan_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=report["status"], plan=str(plan_path), plan_sha256=safety.digest(plan_path),
                          target_files=len(target_files), target_dirs=len(target_dirs),
                          logical_bytes=report["logical_bytes"], protected_files=len(protected)), ensure_ascii=False))


def apply_plan(path, expected_sha256):
    process_guard()
    path = safety.boundary(Path(path))
    require(path.is_relative_to(ROOT / "evidence/storage_cleanup/selected_ui_host_plans"),
            "Selected-Host plan is outside its dedicated evidence boundary")
    require(isinstance(expected_sha256, str) and safety.SHA.fullmatch(expected_sha256),
            "A valid --plan-sha256 pin is required")
    plan_bytes = path.read_bytes()
    require(hashlib.sha256(plan_bytes).hexdigest() == expected_sha256.lower(),
            "Plan SHA-256 does not match the explicit apply pin")
    report = json.loads(plan_bytes.decode("utf-8"))
    require(report.get("schema") == SCHEMA and report.get("status") == "PREVIEW_ONLY" and
            report.get("root") == str(ROOT), "Wrong selected-Host plan schema/root/status")
    require(report.get("selected_host_ids") == list(AUTHORIZED), "Plan has a different Host allowlist")
    require(report.get("wrapper_sha256") == safety.digest(Path(__file__)) and
            report.get("script_sha256") == safety.digest(Path(safety.__file__)), "Reviewed cleanup scripts changed")
    external_tools = report.get("readonly_external_tools")
    require(isinstance(external_tools, list) and
            {os.path.normcase(row.get("path", "")) for row in external_tools} == set(EXTERNAL_TOOL_SHA256) and
            report.get("outside_deletion_or_compression") is False,
            "Plan external-tool guard or no-outside-mutation declaration is invalid")
    verify_external_tools(external_tools)
    expected = {str((ROOT / "Build/UiWindowHost" / run).relative_to(ROOT)) for run in AUTHORIZED}
    expected |= {str((ROOT / "evidence/ui_window_host" / run).relative_to(ROOT)) for run in AUTHORIZED}
    actual = {row["path"] for row in report.get("directories", [])}
    require(actual == expected and len(report["directories"]) == 8, "Plan target boundary is not the exact eight selected directories")
    for key in ("ledger", "protected", "protected_metadata", "diagnostics"):
        ref = report[key]
        ref_path = safety.boundary(Path(ref["path"]))
        require(ref_path.parent == path.parent, "Plan evidence escaped its directory: " + key)
        require(safety.digest(ref_path) == ref["sha256"], "Plan evidence hash changed: " + key)
    require(safety.digest(report["ledger"]["path"]) == report["ledger"]["sha256"], "Target ledger changed")
    with gzip.open(report["ledger"]["path"], "rt", encoding="utf-8") as stream:
        ledger = [json.loads(line) for line in stream]
    require(len(ledger) == report.get("files") and len({row["path"] for row in ledger}) == len(ledger),
            "Target ledger count/path set is invalid")
    planned_files = {str((ROOT / row["path"]).absolute()): row for row in ledger}
    planned_dirs = {row["path"]: row["metadata"] for row in report.get("target_directory_snapshot", [])}
    require(planned_dirs, "Target directory snapshot is missing")
    found_files = {}
    found_dirs = {}
    for target in report["directories"]:
        root = safety.boundary(ROOT / target["path"])
        dirs, files = snapshot_tree(root, require_single_link=True)
        found_dirs.update({row["path"]: row["metadata"] for row in dirs})
        found_files.update({row["path"]: row for row in files})
    require(found_dirs == planned_dirs, "Target directory path/identity inventory changed")
    require(set(found_files) == set(planned_files), "Target file path inventory changed")
    for name, current in found_files.items():
        row = planned_files[name]
        require(current["sha256"] == row["sha256"] and current["identity"] ==
                [row["device"], row["file_id"], row["bytes"], row["mtime_ns"]] and
                current["metadata"] == row["metadata"], "Target file identity/hash/metadata changed: " + name)
    require(safety.digest(report["protected_metadata"]["path"]) == report["protected_metadata"]["sha256"],
            "Protected metadata ledger changed")
    require(safety.digest(report["protected"]["path"]) == report["protected"]["sha256"],
            "Protected hash ledger changed")
    with gzip.open(report["protected_metadata"]["path"], "rt", encoding="utf-8") as stream:
        metadata = json.load(stream)
    with gzip.open(report["protected"]["path"], "rt", encoding="utf-8") as stream:
        protected_hashes = json.load(stream)
    require(set(metadata) == set(protected_hashes) and all(
        metadata[name]["sha256"] == protected_hashes[name] for name in metadata),
        "Protected metadata and hash ledgers differ")

    def verify_protected_metadata():
        for name, row in metadata.items():
            path, info = checked_file(name)
            require(list(identity(info)) == row["identity"] and file_metadata(info) == row["metadata"],
                    "Protected file metadata changed: " + str(path))

    verify_protected_metadata()
    expected_dirs = {row["path"]: row["metadata"] for row in report.get("protected_directories", [])}
    for name, expected_metadata in expected_dirs.items():
        _, info = checked_directory(name)
        require(file_metadata(info) == expected_metadata, "Protected directory metadata changed: " + name)
    require(not set(found_files).intersection(metadata), "Protected file overlaps target")
    # The base apply routine revalidates the exact target ledger and all protected SHA values
    # immediately before and after removal, and removes only listed files/empty directories.
    verify_external_tools(external_tools)
    safety.apply(path)
    verify_external_tools(external_tools)
    cleanup = json.loads((path.parent / "cleanup.json").read_text(encoding="utf-8"))
    require(cleanup.get("status") == "PASS_OBSOLETE_ARTIFACT_RETIREMENT", "Base guarded cleanup did not pass")
    verify_protected_metadata()
    for name, expected_metadata in expected_dirs.items():
        _, info = checked_directory(name)
        require(file_metadata(info) == expected_metadata, "Protected directory changed after cleanup: " + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-id", action="append", choices=AUTHORIZED,
                        help="Authorized UI Host ID; provide each of the four once when planning")
    parser.add_argument("--apply", type=Path, help="Apply one freshly reviewed plan through the base guarded pruner")
    parser.add_argument("--plan-sha256", help="Required SHA-256 pin when applying a reviewed plan")
    args = parser.parse_args()
    if args.apply:
        require(not args.host_id, "Do not mix --apply and --host-id")
        if not args.plan_sha256:
            parser.error("--plan-sha256 is required with --apply")
        apply_plan(args.apply, args.plan_sha256)
    else:
        if args.plan_sha256:
            parser.error("--plan-sha256 is only valid with --apply")
        make_plan(args.host_id or [])


if __name__ == "__main__":
    main()
