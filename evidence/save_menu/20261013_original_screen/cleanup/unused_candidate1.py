"""Plan only: retire four exact, unused first SaveMenu candidate directories.

No process inspection, native game launch, user-save scan, or deletion occurs.
The existing pruner is imported only for NTFS/file/size/boundary helpers. Its
historical candidate selection, global process guard, plan and apply are unused.
"""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import importlib.util
import json
import os
from pathlib import Path
import stat
import uuid


ROOT = Path(__file__).absolute().parents[4]
OUT = Path(__file__).absolute().parent
B1 = "20261013T114342Z_78ac35ee839b"
R1 = "20261013T114734Z_5ff2d836894d"
B2 = "20261013T115435Z_2f60a56301d0"
R2 = "20261013T120349Z_b60179226a6e"
EA06 = "20261012T121847Z_732a6d5f07ea"
TARGETS = tuple(ROOT / area / group / run for area, group, run in (
    ("Build", "UiWindowHost", B1), ("evidence", "ui_window_host", B1),
    ("Build", "InteractiveGameRuntime", R1), ("evidence", "interactive_game", R1)))
CURRENT = tuple(ROOT / area / group / run for area, group, run in (
    ("Build", "UiWindowHost", B2), ("evidence", "ui_window_host", B2),
    ("Build", "InteractiveGameRuntime", R2), ("evidence", "interactive_game", R2)))
ARCHIVES = {".zssave", ".civ5save", ".civ5mpsave"}
PROTECTED_MUTABLE_WORKSPACE = (ROOT / "Source", ROOT / "tools", ROOT / "Tests", ROOT / "Stage")
EXPLICIT_PROTECTED_SEALS = {
    ROOT / "tools" / "Start-Engine.ps1": "c487ce6c89e374bb625961ce81cf6cbae210608c578542658038e6cb06173d7c",
    ROOT / "Play" / "EarlyAccess" / "release.json": "5587028d64ff6206780837ee7112f0c34d62676fb0627ee099d4eb03aef9c2c5",
}
HISTORICAL_REPORT = ROOT / "evidence" / "sdk_x64" / "attempts" / "attempt_036" / "build_result.json"
HISTORICAL_MANIFEST = HISTORICAL_REPORT.parent / "port_manifest.json"
COMMON_MANIFEST = ROOT / "evidence" / "sdk_x64" / "port_manifest.json"
HISTORICAL_MANIFEST_SHA = "3489e5d6d584f7a560420d942e791ca8c7a97ba2d69a3fc19722617e1750e1f1"
HISTORICAL_HOST_REPORT = ROOT / "evidence" / "host" / "build_result.json"
HISTORICAL_HOST_REPORT_SHA = "078e1276a52a59e4401c69113dab31713b669eb68d80406f00e507c38d12acec"
CURRENT_GAME_INFO_REPORT = ROOT / "evidence" / "host_game_info" / "build_result.json"
OLD_GAME_INFO_REPORT_SHA = "35eea8e9cbbb52d8c8c83abc775320d6285d6187caa41d35e6d6b9a94654721a"
CURRENT_GAME_INFO_REPORT_SHA = "1517d0a63c443fd094f720cafd116e3e2b3f3f4cb496c10a388be66cc8488282"
B2_EXE_SHA = "78cf0240b83ed9bd1d58252562559ca2d965fa59df2a633cb8bcca6bb0114859"
HASH_CACHE = {}


def require(ok, message):
    if not ok:raise RuntimeError(message)


def helpers():
    path = ROOT / "tools" / "prune_superseded_runtime_artifacts.py"
    spec = importlib.util.spec_from_file_location("unused_candidate1_ntfs_helpers", path)
    require(spec and spec.loader, "Cannot load existing guarded NTFS helpers")
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    require(module.ROOT == ROOT, "Safety helper project root differs")
    return module, path


P, HELPER_PATH = helpers()


def directory(path):
    path = P.boundary(path);info = path.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_ino != 0 and not info.st_file_attributes & 0x400,
            "Directory is not an ordinary stable NTFS path: " + str(path))
    return path, info


def metadata(info):
    return {"device": info.st_dev, "file_id": info.st_ino, "bytes": info.st_size,
            "mtime_ns": info.st_mtime_ns, "links": info.st_nlink,
            "attributes": info.st_file_attributes, "mode": info.st_mode}


def identity(info):return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def write_json(path, row):
    require(path.parent.is_relative_to(OUT), "Receipt escaped its own cleanup directory")
    require(not os.path.lexists(path), "Receipt already exists: " + str(path))
    path.write_text(json.dumps(row, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sealed_digest(path):
    info = P.regular(P.boundary(path));key = identity(info)
    if key not in HASH_CACHE:HASH_CACHE[key] = P.digest(path)
    require(metadata(path.lstat()) == metadata(info), "File changed during sealed hashing: " + str(path))
    return HASH_CACHE[key]


def reference(path):return {"path": str(path), "sha256": sealed_digest(path), "bytes": path.stat().st_size}


def operational_endpoints():
    paths = set();findings = []
    def verify(row, base):
        require(isinstance(row, dict) and isinstance(row.get("path"), str) and
                P.SHA.fullmatch(str(row.get("sha256", ""))), "Invalid operational artifact row")
        path = Path(os.path.abspath(row["path"]))
        require(path.is_relative_to(base) and path.is_file(), "Missing/escaped sealed operational input: " + str(path))
        require(sealed_digest(path) == row["sha256"], "Sealed operational input differs: " + str(path))
        paths.add(path);return path
    for run in (EA06, R2):
        runtime = ROOT / "Build" / "InteractiveGameRuntime" / run
        evidence = ROOT / "evidence" / "interactive_game" / run
        request_path = evidence / "request.json";P.regular(P.boundary(request_path));paths.add(request_path)
        request = json.loads(request_path.read_text(encoding="utf-8-sig"))
        require(request.get("run_id") == run and Path(request.get("cwd", "")) == runtime and
                request.get("smoke") is False, "Operational request identity differs")
        inputs = request.get("runtime_inputs")
        require(isinstance(inputs, list) and inputs, "Missing immutable runtime_inputs inventory")
        for row in inputs:verify(row, runtime)
        support_path = verify(request["interactive_ui_support"], evidence)
        require(support_path == evidence / "interactive_ui_support.json", "Support record path differs")
        support = json.loads(support_path.read_text(encoding="utf-8-sig"))
        inventory = request["interactive_ui_support_inventory"]
        support_root = runtime / "interactive_ui_support"
        manifest_path = verify(support["frozen_support_manifest"], support_root)
        require(inventory["frozen_support_manifest"] == support["frozen_support_manifest"], "Frozen manifest inventory differs")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        require(set(inventory["tools"]) == set(support["tools"]) == set(manifest["tools"]) and manifest["tools"],
                "Frozen tool inventories disagree")
        for name, row in manifest["tools"].items():
            require(inventory["tools"][name]["frozen"] == support["tools"][name]["frozen"] == row,
                    "Frozen tool record differs: " + name)
            verify(row, support_root)
        for name in ("inline_icons", "asset_preparation_provenance"):
            row = manifest[name]
            require(inventory[name]["frozen"] == support[name]["frozen"] == row, "Frozen asset inventory differs")
            verify(row, support_root)
        for name in ("driver", "play", "resume", "selected"):
            verify(request["launcher_control_metadata"][name], runtime)
        findings.append({"run_id": run, "runtime_input_rows": len(inputs), "frozen_tool_rows": len(manifest["tools"]),
            "frozen_asset_rows": 2, "missing_sealed_operational_inputs": 0, "all_sha256_matched": True})
    result_path = ROOT / "evidence" / "ui_window_host" / B2 / "build_result.json"
    result = json.loads(result_path.read_text(encoding="utf-8-sig"));paths.add(result_path)
    row = result["executable"]
    require(row["sha256"] == B2_EXE_SHA, "Parent-authorized B2 executable identity differs")
    path = verify(row, ROOT / "Build" / "UiWindowHost" / B2)
    require(path == ROOT / "Build" / "UiWindowHost" / B2 / "final" / "ZeroSisHost_x64.exe", "B2 executable path differs")
    findings.append({"run_id": B2, "executable_sha256": B2_EXE_SHA, "missing_sealed_operational_inputs": 0,
                     "all_sha256_matched": True})
    return paths, findings


def unused_guard(targets):
    findings = []
    for target in targets:
        root, root_info = directory(target)
        require(all(not root.is_relative_to(item) and not item.is_relative_to(root) for item in CURRENT),
                "Unused target intersects current failure reproduction")
        for current, subdirs, files in os.walk(root, followlinks=False):
            current = P.boundary(Path(current))
            for name in subdirs:
                path, _ = directory(current / name)
                require(name.casefold() not in ("sessions", "session", "launches", "manual_play"),
                        "Unused candidate has execution/session directory: " + str(path))
            for name in files:
                path = current / name;P.regular(path);lower = name.casefold()
                require(path.suffix.casefold() not in ARCHIVES and lower not in
                        ("launch.json", "driver_result.json", "play-current.json", "play-final-state.txt") and
                        not lower.startswith(("play-", "autosave-", "ui-popup-")),
                        "Unused candidate contains launch/save/SDK execution artifact: " + str(path))
                if path.suffix.casefold() in (".log", ".txt"):
                    text = path.read_text(encoding="utf-8-sig", errors="replace")
                    require(not any(marker in text for marker in (
                        "SESSION_DIRECTORY=", "INTERACTIVE_GAME_STARTED=", "INTERACTIVE_PLAY_CLOSED=",
                        "INTERACTIVE_SAVE_MENU_SHOWN=", "NATIVE_SAVE_WRITTEN=")),
                        "Unused candidate log proves native execution: " + str(path))
        findings.append({"path": str(root), "directory_identity": metadata(root_info),
                         "session_launch_save_artifacts": 0, "native_execution_log_markers": 0})
    return findings


def diagnostic_summary(provenance):
    docs = []
    for name in (ROOT / "evidence" / "ui_window_host" / B1 / "build_result.json",
                 ROOT / "evidence" / "interactive_game" / R1 / "request.json"):
        document = json.loads(name.read_text(encoding="utf-8-sig"))
        docs.append({"record": reference(name), "status": document.get("status"),
            "run_id": document.get("run_id", document.get("build_id")), "source_inputs_unchanged": document.get("source_inputs_unchanged"),
            "smoke": document.get("smoke"), "input_profile": document.get("input_profile"),
            "timeout": document.get("timeout"), "executable": document.get("executable"),
            "initial_reason": "Superseded without native execution: capture UiKind call required the SDK game lock",
            "replacement_host": B2, "replacement_runtime": R2})
    return {"status": "UNUSED_CAPTURE_OWNER_BUG_CANDIDATE_SUPERSEDED", "records": docs,
            "whole_raw_backup_created": False, "current_failure_reproduction_retained": True,
            "historical_manifest_resolution": provenance,
            "plan_preflights": {"failed_attempts": 2, "plan_written": False, "deletion_performed": False,
                "guard_failures": ["Historical SDK attempt_036 manifest annotation differs from latest shared path",
                    "Historical Host game_info_build annotation differs from regenerated shared report"],
                "resolution": "Only the two exact reviewed provenance fields/hashes are treated separately; immutable operational endpoints remain strict"}}


def protected_files():
    paths, endpoints = operational_endpoints()
    for root in CURRENT:
        directory(root)
        for path, _ in P.inventory(root):paths.add(path)
    ea_runtime = ROOT / "Build" / "InteractiveGameRuntime" / EA06
    directory(ea_runtime)
    # User sessions are lexically protected, never scanned/hashed in this plan.
    for current, subdirs, files in os.walk(ea_runtime, followlinks=False):
        current = P.boundary(Path(current))
        subdirs[:] = [name for name in subdirs if name.casefold() != "sessions"]
        for name in subdirs:directory(current / name)
        for name in files:
            path = current / name
            require(path.suffix.casefold() not in ARCHIVES, "Unexpected user archive outside protected session scope")
            paths.add(path)
    seeds = [ROOT / "evidence" / "interactive_game" / EA06 / "request.json",
             ROOT / "evidence" / "interactive_game" / EA06 / "interactive_ui_support.json",
             ROOT / "evidence" / "ui_window_host" / B2 / "build_result.json",
             ROOT / "evidence" / "interactive_game" / R2 / "request.json",
             ROOT / "evidence" / "interactive_game" / R2 / "interactive_ui_support.json"]
    paths.update(seeds)
    for path, expected in EXPLICIT_PROTECTED_SEALS.items():
        require(sealed_digest(P.boundary(path)) == expected, "Explicit protected release/launcher seal differs: " + str(path))
        paths.add(path)
    launcher = ROOT / "tools" / "Start-Engine.ps1"
    paths.add(launcher)
    launcher_text = launcher.read_text(encoding="utf-8-sig")
    require(EA06 in launcher_text and B1 not in launcher_text and R1 not in launcher_text,
            "Default launcher selection no longer matches the protected EA06 / excluded candidates")
    visited = set();pending = [path for path in paths if path.suffix.casefold() == ".json"]
    external = 0;source_annotations = 0;archive_annotations = 0;target_refs = [];provenance = [];missing = []
    while pending:
        path = pending.pop()
        if path in visited:continue
        visited.add(path)
        try:document = json.loads(path.read_text(encoding="utf-8-sig"))
        except (UnicodeError, json.JSONDecodeError):continue
        if path == HISTORICAL_REPORT:
            recorded = document.get("manifest")
            require(document.get("attempt") == 36 and recorded == {
                    "path": str(COMMON_MANIFEST), "sha256": HISTORICAL_MANIFEST_SHA},
                    "Historical manifest exception does not match its exact reviewed field/SHA")
            P.regular(P.boundary(HISTORICAL_MANIFEST));P.regular(P.boundary(COMMON_MANIFEST))
            frozen = reference(HISTORICAL_MANIFEST)
            require(frozen["sha256"] == HISTORICAL_MANIFEST_SHA, "Existing historical manifest copy changed")
            provenance.append({"record": str(path), "field": "manifest", "recorded_sha256": recorded["sha256"],
                "current_shared_reference": reference(COMMON_MANIFEST), "verified_existing_attempt_copy": frozen,
                "consumer": "build_sdk_x64.py generate_port writes the shared source manifest; each attempt retains its own snapshot",
                "other_records_or_hashes_relaxed": False, "original_files_modified_or_copied": False})
            paths.add(COMMON_MANIFEST)
            # Rewrite only this in-memory provenance field, never either file.
            document = dict(document)
            document["manifest"] = {"path": str(HISTORICAL_MANIFEST), "sha256": HISTORICAL_MANIFEST_SHA}
        if path == HISTORICAL_HOST_REPORT:
            require(sealed_digest(path) == HISTORICAL_HOST_REPORT_SHA and document.get("game_info_build") == {
                    "path": str(CURRENT_GAME_INFO_REPORT), "sha256": OLD_GAME_INFO_REPORT_SHA},
                    "Historical Host exception does not match its exact reviewed parent SHA/field")
            current = reference(CURRENT_GAME_INFO_REPORT)
            require(current["sha256"] == CURRENT_GAME_INFO_REPORT_SHA, "Current retained game-info report changed")
            provenance.append({"record": str(path), "record_sha256": HISTORICAL_HOST_REPORT_SHA, "field": "game_info_build",
                "recorded_sha256": OLD_GAME_INFO_REPORT_SHA, "current_shared_reference": current,
                "consumer": "host_game_info_evidence.py build regenerates the shared verification report; build_native_host.py records its build-validation history",
                "historical_bytes_not_asserted_preserved": True, "other_records_or_hashes_relaxed": False,
                "original_files_modified_or_copied": False})
            document = dict(document)
            document["game_info_build"] = {"path": str(CURRENT_GAME_INFO_REPORT), "sha256": CURRENT_GAME_INFO_REPORT_SHA}
        for name, expected in P.refs(document):
            item = Path(os.path.abspath(name))
            if not item.is_relative_to(ROOT):external += 1;continue
            if any(item.is_relative_to(target) for target in TARGETS):
                target_refs.append({"record": str(path), "path": str(item), "sha256": expected});continue
            if any(item.is_relative_to(parent) for parent in PROTECTED_MUTABLE_WORKSPACE):
                source_annotations += 1;continue
            if item.suffix.casefold() in ARCHIVES or ea_runtime / "sessions" in (item, *item.parents):
                archive_annotations += 1;continue
            if item.is_file():
                P.boundary(item);P.regular(item)
                actual = sealed_digest(item)
                require(actual == expected, "Retained sealed operational reference changed: " + str(item) +
                        " referenced by " + str(path) + " expected=" + expected + " actual=" + actual)
                if item not in paths:
                    paths.add(item)
                    if item.suffix.casefold() == ".json":pending.append(item)
            else:
                require(not any(item.is_relative_to(ROOT / "Build" / "InteractiveGameRuntime" / run) for run in (EA06, R2)),
                        "Missing operational runtime/support reference: " + str(item))
                missing.append({"record": str(path), "path": str(item), "recorded_sha256": expected,
                    "classification": "Missing historical build provenance outside verified operational endpoints; preservation not asserted"})
    require(not target_refs, "Retained operational dependency references unused candidates: " + str(target_refs[:5]))
    require(len(provenance) == 2 and HISTORICAL_MANIFEST in paths and CURRENT_GAME_INFO_REPORT in paths,
            "Reviewed provenance boundaries are not protected")
    text_documents = 0
    for path in paths:
        if path.suffix.casefold() not in (".json", ".manifest", ".ps1", ".py", ".lua", ".log", ".txt", ".ini", ".cfg"):
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        require(B1 not in text and R1 not in text,
                "Retained operational text references unused candidate ID: " + str(path))
        text_documents += 1
    return sorted(paths), {"retained_documents_checked": len(visited), "retained_target_references": target_refs,
        "retained_operational_text_documents_checked": text_documents,
        "default_launcher_excludes_unused_candidates": True,
        "exact_reviewed_historical_provenance_resolutions": len(provenance),
        "sealed_operational_endpoints": endpoints,
        "missing_historical_provenance_ref_count": len(missing),
        "missing_historical_provenance_unique_paths": len({row["path"] for row in missing}),
        "missing_historical_refs_claimed_preserved": False,
        "live_source_annotations_not_hashed": source_annotations, "external_immutable_source_annotations_not_touched": external,
        "archive_annotations_lexically_protected_not_scanned": archive_annotations,
        "current_ea06_session_data_scan": False, "retail_game_or_mods_or_user_saves_scanned": False,
        "scope": "Current B2/R2 full frozen records and closed owned failure fixtures; EA06 immutable runtime/dependency closure"}, provenance, missing


def plan():
    directory(OUT)
    require(len(TARGETS) == 4 and len(set(TARGETS)) == 4, "Exact four targets required")
    findings = unused_guard(TARGETS)
    protection, closure, provenance, missing = protected_files()
    for path in protection:require(not any(path.is_relative_to(target) for target in TARGETS), "Protected path intersects target")
    name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8]
    output = OUT / name;output.mkdir(exist_ok=False)
    cache = {};groups = {};ledger_rows = [];directories = []
    for target in TARGETS:
        count = logical = 0
        for path, info in P.inventory(target):
            require(info.st_ino != 0, "Unstable target NTFS file ID")
            key = identity(info)
            if key not in cache:cache[key] = sealed_digest(path)
            require(metadata(path.lstat()) == metadata(info), "Target changed during hashing: " + str(path))
            with path.open("rb") as stream:head = stream.read(16)
            require(not head.startswith(b"ZEROSIS_SAVE_V1\0"), "Native archive hidden behind a non-save filename")
            file_id = (info.st_dev, info.st_ino)
            if file_id not in groups:
                groups[file_id] = {"links": info.st_nlink, "planned_links": 0,
                    "allocated_bytes": P.stored(path), "logical_bytes": info.st_size}
            entry = groups[file_id];allocated = entry["allocated_bytes"]
            require(entry["links"] == info.st_nlink and entry["logical_bytes"] == info.st_size, "Hardlink metadata differs")
            entry["planned_links"] += 1
            ledger_rows.append({"path": str(path), "sha256": cache[key], **metadata(info), "allocated_bytes": allocated})
            count += 1;logical += info.st_size
        directories.append({"path": str(target), "files": count, "logical_bytes": logical})
    preserved = []
    target_ids = set(groups)
    shared = set()
    for path in protection:
        info = P.regular(P.boundary(path));require(info.st_ino != 0, "Unstable protected NTFS file ID")
        key = identity(info)
        if key not in cache:cache[key] = sealed_digest(path)
        require(metadata(path.lstat()) == metadata(info), "Retained immutable file changed during hashing")
        if (info.st_dev, info.st_ino) in target_ids:shared.add((info.st_dev, info.st_ino))
        preserved.append({"path": str(path), "sha256": cache[key], **metadata(info)})
    ledger = output / "retired_files.jsonl.gz"
    with gzip.open(ledger, "wt", encoding="utf-8") as stream:
        for row in ledger_rows:stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    protected = output / "protected_files.json.gz"
    with gzip.open(protected, "wt", encoding="utf-8") as stream:
        json.dump(preserved, stream, ensure_ascii=False, separators=(",", ":"))
    missing_receipt = output / "missing_historical_provenance.json.gz"
    with gzip.open(missing_receipt, "wt", encoding="utf-8") as stream:
        json.dump(missing, stream, ensure_ascii=False, separators=(",", ":"))
    diagnostic = output / "retired_diagnostic.json";write_json(diagnostic, diagnostic_summary(provenance))
    for value in groups.values():require(value["planned_links"] <= value["links"], "Target hardlink accounting exceeds NTFS link count")
    report = {"schema": "ZEROSIS_UNUSED_SAVEMENU_CANDIDATE1_RETIREMENT_PLAN_V1", "status": "PREVIEW_ONLY",
        "exact_targets": directories, "unused_guards": findings, "retained_dependency_guards": closure,
        "protected_file_count": len(preserved), "shared_target_and_retained_identities": len(shared),
        "protected_roots": [str(root) for root in CURRENT] + [str(ROOT / "Build" / "InteractiveGameRuntime" / EA06)],
        "protected_live_source_scope": "All Source/tools/Tests/Stage paths excluded from deletion; current source hashes not asserted",
        "archive_protection": "Zero archive/session/launch artifacts in targets; all archives elsewhere unreachable by exact target scope",
        "deletion_performed": False, "game_processes_inspected": False, "retail_mods_or_user_saves_scanned": False,
        "native_windows_launched": False, "full_duplicate_backup_created": False,
        "file_count": len(ledger_rows), "logical_bytes": sum(row["logical_bytes"] for row in directories),
        "unique_ntfs_identities": len(groups), "unique_allocated_bytes": sum(row["allocated_bytes"] for row in groups.values()),
        "estimated_reclaimable_unique_allocated_bytes": sum(row["allocated_bytes"] for row in groups.values() if row["planned_links"] == row["links"]),
        "allocation_estimate_method": "GetCompressedFileSizeW once per NTFS file ID; reclaim only when every hardlink is in the four targets",
        "allocation_estimate_limit": "For uncompressed ordinary files GetCompressedFileSizeW reports logical size; physical NTFS cluster allocation can differ",
        "readonly_hardlink_delete_rule": "Revalidate device/file-ID/size/mtime/SHA/attributes; use reviewed helper FileDispositionInfoEx DELETE|POSIX|IGNORE_READONLY without changing shared attributes",
        "remaining_link_rule": "Surviving readonly hardlink bytes/mtime/attributes remain sealed; nlink may decrease by exact removed target links only",
        "review_required_before_apply": True, "apply_supported_by_this_plan_only_wrapper": False,
        "ledger": reference(ledger), "protected": reference(protected), "diagnostic": reference(diagnostic),
        "missing_historical_provenance": reference(missing_receipt),
        "wrapper": reference(Path(__file__)), "ntfs_helper": reference(HELPER_PATH)}
    destination = output / "plan.json";write_json(destination, report)
    print(json.dumps({"status": report["status"], "plan": reference(destination), "files": report["file_count"],
        "logical_bytes": report["logical_bytes"], "unique_allocated_bytes": report["unique_allocated_bytes"],
        "estimated_reclaimable_unique_allocated_bytes": report["estimated_reclaimable_unique_allocated_bytes"],
        "guard_findings": {"session_launch_save_artifacts": 0, "retained_target_references": 0,
            "shared_target_and_retained_identities": len(shared), "deletion_performed": False}}, ensure_ascii=False))


if __name__ == "__main__":plan()
