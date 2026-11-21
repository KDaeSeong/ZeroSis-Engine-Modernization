"""Plan-only inventory for two explicitly superseded UI Host build/evidence pairs."""
from __future__ import annotations
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(PROJECT / "tools"))
import prune_superseded_runtime_artifacts as base

ROOT = base.ROOT
OUT = Path(__file__).resolve().parent
SELECTED = ("20261010T071926Z_7754ee20c182", "20261010T044454Z_fce2fdf05278")
CURRENT_HOSTS = ("20261010T061111Z_b26391596d41", "20261010T072241Z_8a97a1f4381e")
BASE_DIRECTORY = ROOT / "evidence/storage_cleanup/20261010T073353Z_16f2c7150d1d"
BASE_SHA = "99eed1b129e24139b435feb34e2a88172ba7332ffaf9a3e4d3d20f9dfa177baa"

class FileStandardInfo(ctypes.Structure):
    _fields_ = [("AllocationSize", ctypes.c_longlong), ("EndOfFile", ctypes.c_longlong),
                ("NumberOfLinks", wintypes.DWORD), ("DeletePending", wintypes.BOOLEAN),
                ("Directory", wintypes.BOOLEAN)]

base.K.GetFileInformationByHandleEx.argtypes = [
    wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
base.K.GetFileInformationByHandleEx.restype = wintypes.BOOL

def allocation(path, info):
    handle = base.K.CreateFileW(str(path), 0x80, 7, None, 3, 0x00200000, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        value = FileStandardInfo()
        if not base.K.GetFileInformationByHandleEx(handle, 1, ctypes.byref(value), ctypes.sizeof(value)):
            raise ctypes.WinError(ctypes.get_last_error())
        base.require(not value.Directory and not value.DeletePending and
                     value.EndOfFile == info.st_size and value.NumberOfLinks == info.st_nlink and
                     value.AllocationSize >= 0, "Allocation identity differs: " + str(path))
        return value.AllocationSize
    finally:
        base.K.CloseHandle(handle)

def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))

def identity(info):
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns,
            info.st_nlink, getattr(info, "st_file_attributes", 0))

def reference(path):
    base.regular(base.boundary(path))
    return {"path": str(path), "sha256": base.digest(path)}

def strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for key, value in node.items():
            yield str(key)
            yield from strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from strings(value)

def main():
    base.require(ROOT == PROJECT and base.digest(Path(base.__file__)) == BASE_SHA,
                 "Unexpected base boundary/identity implementation")
    base.boundary(OUT)
    base.require(not (OUT / "plan.json").exists() and not (OUT / "retired-files.jsonl.gz").exists(),
                 "This plan folder has already been inventoried")
    base.no_active_host()
    base_plan_path = base.boundary(BASE_DIRECTORY / "plan.json")
    base_plan = read_json(base_plan_path)
    protected_path = base.boundary(Path(base_plan["protected"]["path"]))
    metadata_path = base.boundary(Path(base_plan["protected_metadata"]["path"]))
    base.require(base.digest(protected_path) == base_plan["protected"]["sha256"] and
                 base.digest(metadata_path) == base_plan["protected_metadata"]["sha256"],
                 "Shared protected ledgers changed")
    with gzip.open(protected_path, "rt", encoding="utf8") as stream:
        protected = json.load(stream)
    with gzip.open(metadata_path, "rt", encoding="utf8") as stream:
        metadata = json.load(stream)
    base.require(set(protected) == set(metadata), "Shared protected metadata paths differ")
    cleanup_path = base.boundary(BASE_DIRECTORY / "cleanup.json")
    identity_check_path = base.boundary(BASE_DIRECTORY / "protected-identity-check.json")
    cleanup = read_json(cleanup_path)
    identity_check = read_json(identity_check_path)
    base.require(cleanup["status"] == "PASS_OBSOLETE_ARTIFACT_RETIREMENT" and
                 identity_check["status"] == "PASS_PROTECTED_IDENTITIES_AND_ATTRIBUTES_UNCHANGED" and
                 identity_check["plan_sha256"] == base.digest(base_plan_path) and
                 identity_check["files"] == len(protected), "Prior shared protection verification is incomplete")
    targets = [base.legal_target(ROOT / parent / host) for host in SELECTED
               for parent in ("Build/UiWindowHost", "evidence/ui_window_host")]
    overlaps = [name for name in protected if any(Path(name).is_relative_to(t) for t in targets)]
    base.require(not overlaps, "Current protected paths intersect a selected Host")
    request_rows = []
    for path in sorted((ROOT / "evidence/interactive_game").glob("*/request.json")):
        raw = path.read_bytes()
        text = raw.decode("utf-8-sig")
        base.require(not any(host in text for host in SELECTED),
                     "Retained runtime request depends on selected Host: " + str(path))
        request_rows.append([str(path.relative_to(ROOT)), hashlib.sha256(raw).hexdigest()])
    request_index = hashlib.sha256(json.dumps(request_rows, separators=(",", ":")).encode()).hexdigest()
    retained_inputs = []
    for host in CURRENT_HOSTS:
        path = ROOT / "evidence/ui_window_host" / host / "build_result.json"
        report = read_json(path)
        base.require(not any(host_id in text for text in strings(report) for host_id in SELECTED),
                     "Current Host record depends on selected Host: " + host)
        base.require(report["source_inputs_unchanged"] and report["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT",
                     "Current Host is not a sealed candidate")
        retained_inputs.append({"build_id": host, "report": reference(path),
                                "compiler_input_count": len(report["compiler_inputs"]),
                                "selected_host_references": 0})
    selected_reports = []
    for host in SELECTED:
        path = ROOT / "evidence/ui_window_host" / host / "build_result.json"
        report = read_json(path)
        base.require(report["build_id"] == host and report["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT" and
                     report["source_inputs_unchanged"], "Selected Host is not the expected superseded build")
        exe = base.boundary(Path(report["executable"]["path"]))
        base.require(exe.is_relative_to(ROOT / "Build/UiWindowHost" / host) and
                     base.digest(exe) == report["executable"]["sha256"], "Selected Host executable changed")
        selected_reports.append({"build_id": host, "historical_status": report["status"],
                                 "report_sha256": base.digest(path),
                                 "executable_sha256": report["executable"]["sha256"],
                                 "loop_sha256": report["source_hashes_before"]["interactive_loop"],
                                 "raw_diagnostics_retired": False})
    protected_ids = {}
    for name, value in metadata.items():
        protected_ids.setdefault((value[0], value[1]), set()).add(protected[name])
    hashes = {}
    groups = {}
    snapshots = {}
    directories = []
    ledger = OUT / "retired-files.jsonl.gz"
    with gzip.open(ledger, "wt", encoding="utf8") as stream:
        for target in targets:
            count = logical = 0
            for path, info in base.inventory(target):
                before = identity(info)
                cache_key = before[:4]
                if cache_key not in hashes:
                    hashes[cache_key] = base.digest(path)
                actual_sha = hashes[cache_key]
                base.require(identity(base.regular(path)) == before,
                             "Target changed while hashing: " + str(path))
                file_key = before[:2]
                if file_key in protected_ids:
                    base.require(protected_ids[file_key] == {actual_sha},
                                 "Target alias differs from protected content: " + str(path))
                item = groups.get(file_key)
                if item is None:
                    item = groups[file_key] = {
                        "links": info.st_nlink, "count": 0, "stored": base.stored(path),
                        "allocation": allocation(path, info),
                        "protected_alias": file_key in protected_ids,
                        "sha256": actual_sha, "bytes": info.st_size}
                base.require(item["links"] == info.st_nlink and item["sha256"] == actual_sha and
                             item["bytes"] == info.st_size, "Target hardlink group changed")
                item["count"] += 1
                snapshots[str(path)] = before
                row = {"path": str(path.relative_to(ROOT)), "sha256": actual_sha,
                       "bytes": info.st_size, "mtime_ns": info.st_mtime_ns,
                       "device": info.st_dev, "file_id": info.st_ino,
                       "links": info.st_nlink, "attributes": before[5],
                       "allocation_size": item["allocation"]}
                stream.write(json.dumps(row, separators=(",", ":")) + "\n")
                count += 1
                logical += info.st_size
            directories.append({"path": str(target.relative_to(ROOT)), "files": count, "logical_bytes": logical})
            print(json.dumps({"phase": "target_inventoried", "path": str(target.relative_to(ROOT)),
                              "files": count, "logical_bytes": logical}), flush=True)
    observed = set()
    for target in targets:
        for path, info in base.inventory(target):
            name = str(path)
            base.require(name in snapshots and identity(info) == snapshots[name],
                         "Target tree changed after inventory: " + name)
            observed.add(name)
    base.require(observed == set(snapshots), "Target file set changed after inventory")
    for group in groups.values():
        base.require(group["count"] <= group["links"], "Target names exceed hardlink count")
        if group["protected_alias"]:
            base.require(group["count"] < group["links"], "Protected alias is not retained outside selection")
    base.require(base.digest(protected_path) == base_plan["protected"]["sha256"] and
                 base.digest(metadata_path) == base_plan["protected_metadata"]["sha256"],
                 "Shared protected ledgers changed during inventory")
    report = {
        "schema": 1, "status": "PREVIEW_ONLY", "root": str(ROOT),
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "EXACT_TWO_SUPERSEDED_UI_HOST_BUILD_EVIDENCE_PAIRS",
        "user_instruction": "불필요한 작업물 지워.",
        "selected_hosts": list(SELECTED), "directories": directories,
        "files": sum(d["files"] for d in directories),
        "logical_bytes": sum(d["logical_bytes"] for d in directories),
        "unique_file_ids": len(groups),
        "estimated_reclaimable_file_storage": sum(g["stored"] for g in groups.values() if g["count"] == g["links"]),
        "estimated_reclaimable_allocation_bytes": sum(g["allocation"] for g in groups.values() if g["count"] == g["links"]),
        "externally_shared_file_id_count": sum(g["count"] < g["links"] for g in groups.values()),
        "protected_shared_file_id_count": sum(g["protected_alias"] for g in groups.values()),
        "ledger": reference(ledger),
        "shared_protected": {**base_plan["protected"], "files": len(protected)},
        "shared_protected_metadata": base_plan["protected_metadata"],
        "shared_protection_source_plan": reference(base_plan_path),
        "shared_protection_completed_cleanup": reference(cleanup_path),
        "shared_protection_identity_check": reference(identity_check_path),
        "protected_path_intersection_count": 0,
        "retained_request_index": {"count": len(request_rows), "sha256": request_index,
                                  "selected_host_references": 0},
        "retained_current_host_inputs": retained_inputs,
        "retired_host_records": selected_reports,
        "script_sha256": BASE_SHA, "planner_sha256": base.digest(Path(__file__)),
        "protected_files_rehashed_by_this_plan": 0,
        "target_unique_content_hashes_computed": len(hashes),
        "reused_functions": ["base.inventory", "base.regular", "base.boundary", "base.legal_target",
                             "base.digest", "base.stored", "base.no_active_host"],
        "apply_performed": False,
        "apply_gate": "Parent review required. This is a plan-only producer with no apply implementation. Do not pass this shared-protection schema directly to base.apply, which requires a local protected file.",
        "preservation": ["Current Host072241 and EA0.5 Host061111",
                         "All 9 manual runtimes and 12 saved games",
                         "Current 061414 fresh and 064159 failure reproduction",
                         "Source, tools, installed game, release launchers and previous raw retirement ledgers"],
        "limitations": [
            "Reclaim estimates use actual NumberOfLinks and AllocationSize, count each file ID once, and exclude identities with names outside the four selected roots.",
            "No volume free-space change is claimed; allocation estimates can become stale if links or files change before apply.",
            "The shared 35447-file protected map and its completed prior checks are hash-pinned and referenced, not copied or rehashed. Target aliases sharing protected identities are freshly content-hashed and must match their protected SHA.",
            "Before any future apply, parent must validate this exact plan hash, exact root/file inventory and the shared protection state, retaining all existing unlink/boundary/identity safeguards."
        ]
    }
    destination = OUT / "plan.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf8")
    print(json.dumps({"status": report["status"], "plan": str(destination),
                      "plan_sha256": base.digest(destination), "directories": directories,
                      "files": report["files"], "logical_bytes": report["logical_bytes"],
                      "estimated_reclaimable_allocation_bytes": report["estimated_reclaimable_allocation_bytes"],
                      "externally_shared_file_id_count": report["externally_shared_file_id_count"],
                      "protected_shared_file_id_count": report["protected_shared_file_id_count"]}), flush=True)

if __name__ == "__main__":
    main()
