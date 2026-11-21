"""Apply only the four sealed, unused candidate paths. No process/game access."""
from __future__ import annotations
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat

HERE = Path(__file__).absolute().parent
PLAN_PATH = HERE / "20261013T125211Z_df4ecd59/plan.json"
PLAN_SHA = "6b14d8d4c9d989bdb391d1640a1cfb5a1587fc7eab96c1242e7deee127b7c09e"
WRAPPER_SHA = "b872fd525f6dd9ff6d499d549f35ec4184907209c4968b4d526b6b7e63090d4d"
HELPER_SHA = "e7dc5a356deba20add2482c4109f5e78775b48480c5ea81e483289e97f3b3678"


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_helpers():
    wrapper = HERE / "unused_candidate1.py"
    helper = HERE.parents[3] / "tools/prune_superseded_runtime_artifacts.py"
    require(digest(wrapper) == WRAPPER_SHA and digest(helper) == HELPER_SHA,
            "Reviewed plan/helper code changed")
    spec = importlib.util.spec_from_file_location("sealed_unused_candidate1", wrapper)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    require(module.HELPER_PATH == helper, "Helper path differs")
    return module


def utc():
    return datetime.now(timezone.utc).isoformat()


def write_new(path, row):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(row, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    require(digest(PLAN_PATH) == PLAN_SHA, "Approved plan changed")
    started = PLAN_PATH.parent / "apply_started.json"
    result_path = PLAN_PATH.parent / "apply_result.json"
    require(not os.path.lexists(started) and not os.path.lexists(result_path),
            "This plan is single-use; do not replay an attempted application")
    a = load_helpers()
    p = a.P
    p.regular(p.boundary(PLAN_PATH))
    p.regular(p.boundary(Path(__file__)))
    plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
    require(plan["status"] == "PREVIEW_ONLY" and plan["file_count"] == 714,
            "Unexpected plan status/count")
    require([row["path"] for row in plan["exact_targets"]] == [str(x) for x in a.TARGETS],
            "Exact four target paths differ")
    sealed = {PLAN_PATH: PLAN_SHA, Path(__file__): digest(Path(__file__))}
    for name in ("wrapper", "ntfs_helper", "ledger", "protected", "diagnostic", "missing_historical_provenance"):
        row = plan[name]
        path = Path(row["path"])
        p.regular(p.boundary(path))
        require(path.is_relative_to(a.ROOT) and digest(path) == row["sha256"],
                "Plan artifact seal differs: " + name)
        sealed[path] = row["sha256"]
    with gzip.open(plan["ledger"]["path"], "rt", encoding="utf-8") as stream:
        retired = [json.loads(line) for line in stream]
    with gzip.open(plan["protected"]["path"], "rt", encoding="utf-8") as stream:
        protected = json.load(stream)
    require(len(retired) == 714 and len(protected) == plan["protected_file_count"],
            "Ledger counts differ")
    original_protected_count = len(protected)
    supplemental = []
    for name, sha in (
        ("Play/EarlyAccess/history/0.5/release.json", "c82209bdeec169ffdc363805782548934398faf3dec369c12c681a8cc6a31934"),
        ("docs/EARLY_ACCESS_KR.md", "d6f3820ca1538099fa8bf6c6d1172be026902fa0951822c78e1d15351231e671")):
        path = p.boundary(a.ROOT / name)
        info = p.regular(path)
        require(digest(path) == sha, "Exactly reviewed historical documentation changed")
        supplemental.append({"path": str(path), "sha256": sha, **a.metadata(info)})
    require(not ({row["path"] for row in supplemental} & {row["path"] for row in protected}),
            "Supplemental historical documentation was already in the ledger")
    protected.extend(supplemental)
    require(len({row["path"] for row in retired}) == len(retired), "Duplicate retired paths")
    expected_paths = {Path(row["path"]) for row in retired}
    actual_paths = {path for target in a.TARGETS for path, _ in p.inventory(target)}
    require(actual_paths == expected_paths, "Target inventory changed since preview")
    for path in expected_paths:
        require(sum(path.is_relative_to(target) for target in a.TARGETS) == 1,
                "Retired file escapes exact scope")
    for row in protected:
        require(not any(Path(row["path"]).is_relative_to(target) for target in a.TARGETS),
                "Protected path intersects retirement")
    a.HASH_CACHE.clear()
    unused = a.unused_guard(a.TARGETS)
    # Revalidate the actual current runtime endpoints. The original sealed raw
    # protection ledger, not obsolete documentation pointers, defines what
    # must retain identical bytes. Rewalking the historical graph stopped a
    # previous preflight on the EA0.5 guide's obsolete content hash; it deleted
    # nothing. That failure is retained separately and is not called preserved.
    protected_paths = {Path(row["path"]) for row in protected}
    endpoint_paths, endpoints = a.operational_endpoints()
    require(set(endpoint_paths).issubset(protected_paths), "Current runtime endpoint escaped protected ledger")
    for root in a.CURRENT:
        require({path for path, _ in p.inventory(root)}.issubset(protected_paths),
                "Current B2/R2 immutable inventory changed since preview")
    text_count = 0
    for row in protected:
        path = Path(row["path"])
        if path.suffix.casefold() in (".json", ".manifest", ".ps1", ".py", ".lua", ".log", ".txt", ".ini", ".cfg"):
            text = path.read_text(encoding="utf-8-sig", errors="replace")
            require(a.B1 not in text and a.R1 not in text, "Protected operational text references retired candidate")
            text_count += 1
    closure = {"sealed_operational_endpoints": endpoints,
               "current_B2_R2_inventory_matches_protected_ledger": True,
               "retained_text_documents_checked": text_count, "retained_target_references": 0,
               "all_original_protected_raw_files_sealed_before_and_after": True,
               "historical_reference_graph_rewalked": False,
               "historical_hash_failure_claimed_preserved": False,
               "historical_preflight_failure": str(PLAN_PATH.parent / "apply_preflight_failure.json")}
    counts = Counter((row["device"], row["file_id"]) for row in retired)
    require(len(counts) == plan["unique_ntfs_identities"], "NTFS identity count differs")
    hash_cache = {}

    def verify(row, removed_links=0, cached=True):
        path = p.boundary(Path(row["path"]))
        info = p.regular(path)
        metadata = a.metadata(info)
        expected = {key: row[key] for key in metadata}
        expected["links"] -= removed_links
        require(metadata == expected, "Sealed file metadata differs: " + str(path))
        key = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if cached and key in hash_cache:
            actual = hash_cache[key]
        else:
            with path.open("rb") as stream:
                handle_info = os.fstat(stream.fileno())
                # Windows fstat omits the extension-derived execute bits in lstat.
                # Compare handle identity/content fields, and keep path mode sealed.
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink", "st_file_attributes"):
                    require(getattr(handle_info, field) == getattr(info, field),
                            "Opened file identity differs: " + str(path))
                require(stat.S_ISREG(handle_info.st_mode), "Opened file is not regular")
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
                after = os.fstat(stream.fileno())
                for field in ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_nlink", "st_file_attributes"):
                    require(getattr(after, field) == getattr(handle_info, field), "File changed during hashing")
            hash_cache[key] = actual
        require(actual == row["sha256"] and a.metadata(path.lstat()) == expected,
                "Sealed file content changed: " + str(path))
        if "allocated_bytes" in row:
            require(p.stored(path) == row["allocated_bytes"], "Stored file size changed")

    for row in retired + protected:
        verify(row)
    for path, sha in sealed.items():
        require(digest(path) == sha, "Plan evidence changed during preflight")
    folders = {}
    for target in a.TARGETS:
        for current, subdirs, _ in os.walk(target, followlinks=False):
            path, info = a.directory(Path(current))
            folders[path] = (info.st_dev, info.st_ino, info.st_file_attributes, info.st_mode)
            for name in subdirs:
                a.directory(path / name)
    write_new(started, {"status": "APPLY_STARTED_SINGLE_USE", "utc": utc(), "plan_sha256": PLAN_SHA,
        "apply_script_sha256": sealed[Path(__file__)], "target_count": 4,
        "all_file_preflight_checks_passed": True, "protected_files": len(protected),
        "game_mods_saves_or_processes_accessed": False})
    removed = []
    removed_ids = Counter()
    errors = []
    report = {"schema": "ZEROSIS_UNUSED_CANDIDATE1_APPLY_V1", "started_utc": utc(),
        "plan": {"path": str(PLAN_PATH), "sha256": PLAN_SHA},
        "apply_script": {"path": str(Path(__file__)), "sha256": sealed[Path(__file__)]},
        "unused_guards": unused, "operational_guards": closure,
        "game_mods_saves_or_processes_accessed": False, "source_hash_preservation_claimed": False,
        "shared_file_attributes_changed": False, "full_backup_created": False}
    try:
        for row in retired:
            identity = (row["device"], row["file_id"])
            verify(row, removed_ids[identity], cached=False)
            p.unlink_without_attribute_changes(Path(row["path"]))
            require(not os.path.lexists(row["path"]), "Deleted target path remains")
            removed.append(row)
            removed_ids[identity] += 1
        for path in sorted(folders, key=lambda item: len(item.parts), reverse=True):
            canonical, info = a.directory(path)
            require((info.st_dev, info.st_ino, info.st_file_attributes, info.st_mode) == folders[path],
                    "Directory identity/attributes changed before removal")
            canonical.rmdir()
        require(all(not os.path.lexists(target) for target in a.TARGETS), "Target root remains")
    except Exception as error:
        errors.append(str(error))
    hash_cache.clear()
    preserved_count = 0
    for row in protected:
        try:
            verify(row, removed_ids[(row["device"], row["file_id"])])
            preserved_count += 1
        except Exception as error:
            errors.append(str(error))
    for path, sha in sealed.items():
        try:
            require(digest(path) == sha, "Plan evidence changed after application")
        except Exception as error:
            errors.append(str(error))
    complete = len(removed) == len(retired) and not errors and all(not os.path.lexists(target) for target in a.TARGETS)
    unique_rows = {(row["device"], row["file_id"]): row for row in retired}
    retired_storage = sum(row["allocated_bytes"] for key, row in unique_rows.items()
                          if removed_ids[key] == row["links"])
    report.update(status="COMPLETE_FOUR_UNUSED_CANDIDATE_PATHS_RETIRED" if complete else "INCOMPLETE_SINGLE_USE_DO_NOT_REPLAY",
        completed_utc=utc(), removed_file_count=len(removed), removed_logical_bytes=sum(row["bytes"] for row in removed),
        unique_GetCompressedFileSizeW_bytes_with_all_links_removed=retired_storage,
        storage_method="Measured before deletion once per NTFS ID and counted only when all original links were removed; not a volume free-space/cluster allocation measurement",
        original_plan_protected_file_count=original_protected_count, supplemental_protected_files=supplemental,
        protected_file_count=len(protected), protected_files_verified_after=preserved_count,
        protected_bytes_mtime_attributes_unchanged=preserved_count == len(protected),
        hardlink_decrements_exact=preserved_count == len(protected), errors=errors,
        retired_path_size_sha_receipt=plan["ledger"],
        target_results=[{"path": str(target), "removed": not os.path.lexists(target)} for target in a.TARGETS])
    write_new(result_path, report)
    print(json.dumps({"status": report["status"], "result": str(result_path), "sha256": digest(result_path),
        "removed_files": len(removed), "logical_bytes": report["removed_logical_bytes"],
        "unique_retired_storage_bytes": retired_storage, "protected_verified": preserved_count,
        "errors": errors[:3]}, ensure_ascii=False))
    return 0 if complete else 1


if __name__ == "__main__":
    raise SystemExit(main())
