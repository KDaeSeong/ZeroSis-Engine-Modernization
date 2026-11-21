"""One-use apply for the exact reviewed failed Host plan in this directory."""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import gzip
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import stat
import sys
import uuid

SELF = Path(__file__).resolve()
OUT = SELF.parent
ROOT = OUT.parents[3]
BUILD_ID = "20261009T122845Z_f9ae33a6484d"
PLAN_SHA = "3c337e839e7944cd36b8ef72652d680a64d5afdf469c4d4a537bbf7bad6e81ef"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_new(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, separators=(",", ":"))
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    parser.add_argument("--code-sha256", required=True)
    args = parser.parse_args()
    require(digest(SELF) == args.code_sha256, "Apply code SHA differs")
    plan_path = OUT / "plan.json"
    require(digest(plan_path) == PLAN_SHA, "Reviewed plan SHA differs")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    require(plan["root"] == str(ROOT) and plan["build_id"] == BUILD_ID and
            plan["status"] == "PREVIEW_ONLY_NO_DELETION" and plan["files_removed"] == 0,
            "Plan root/build/status differs")
    target = ROOT / "Build/UiWindowHost" / BUILD_ID
    require(plan["target"] == str(target) and target.parent == ROOT / "Build/UiWindowHost",
            "Plan target is not the exact approved failed Host")
    ledgers = {}
    for key, name in (("target_ledger", "target-files.json.gz"), ("protected_ledger", "protected-files.json.gz")):
        row = plan[key]
        path = Path(row["path"])
        require(path == OUT / name and digest(path) == row["sha256"], "Pinned ledger differs")
        ledgers[key] = json.loads(gzip.decompress(path.read_bytes()))
    targets = ledgers["target_ledger"]
    protected = ledgers["protected_ledger"]
    require(len(targets["files"]) == plan["target_file_count"] == 67 and
            len(targets["directories"]) == plan["target_directory_count"] == 14 and
            sum(row["identity"]["bytes"] for row in targets["files"]) == plan["target_logical_bytes"] == 88036972 and
            len(protected) == plan["protected_file_count"] == 752, "Reviewed counts differ")
    for rows in (targets["files"], targets["directories"], protected):
        require(len({row["path"].casefold() for row in rows}) == len(rows), "Duplicate ledger path")
    pinned = {row["path"]: row for row in protected}
    for name in ("plan_failed_ui_host_cleanup.py", "prune_superseded_runtime_artifacts.py"):
        path = ROOT / "tools" / name
        require(str(path) in pinned and digest(path) == pinned[str(path)]["sha256"], "Pinned helper differs")
    sys.path.insert(0, str(ROOT / "tools"))
    import plan_failed_ui_host_cleanup as p
    require(p.ROOT == ROOT, "Imported planner root differs")
    p.safety.boundary(OUT)
    for row in targets["files"] + targets["directories"]:
        path = Path(row["path"])
        require(path == target or path.is_relative_to(target), "Ledger escaped exact target")
    require(not any(Path(row["path"]).is_relative_to(target) for row in protected), "Protected path overlaps target")
    for name in ("apply-attempt.json", "cleanup.json", "cleanup.json.new", "removed-files.jsonl"):
        require(not (OUT / name).exists(), "Apply already attempted; do not replay")
    attempt = dict(status="ONE_USE_APPLY_STARTED_DO_NOT_REPLAY", token=uuid.uuid4().hex,
                   started_utc=datetime.now(timezone.utc).isoformat(), plan_sha256=PLAN_SHA,
                   apply_code_sha256=args.code_sha256)
    write_new(OUT / "apply-attempt.json", attempt)
    receipt = dict(status="PREFLIGHT_RUNNING_DO_NOT_REPLAY", token=attempt["token"],
                   plan_sha256=PLAN_SHA, apply_code_sha256=args.code_sha256,
                   target=str(target), planned_files=67, protected_files=752,
                   removed_files=0, removed_logical_bytes=0, removed_allocation_bytes=0,
                   removed_directories=0, errors=[], protected_before_verified=False,
                   protected_after_verified=False, changing_session_files_touched=False)
    write_new(OUT / "cleanup.json", receipt)

    def checkpoint():
        temporary = OUT / "cleanup.json.new"
        write_new(temporary, receipt)
        os.replace(temporary, OUT / "cleanup.json")

    def guards():
        errors, hashes = [], {}
        for row in protected:
            try:
                path, info = p.checked_file(Path(row["path"]))
                before = p.identity(info)
                require(before == row["identity"], "Protected identity differs: " + str(path))
                key = tuple(before.values())
                sha = hashes.get(key)
                if sha is None:
                    sha = hashes[key] = digest(path)
                require(sha == row["sha256"] and p.identity(p.checked_file(path)[1]) == before,
                        "Protected content/identity differs: " + str(path))
            except Exception as error:
                errors.append(str(error))
        return errors

    class FileStandardInfo(ctypes.Structure):
        _fields_ = [("allocation", ctypes.c_longlong), ("length", ctypes.c_longlong),
                    ("links", wintypes.DWORD), ("delete_pending", ctypes.c_ubyte),
                    ("directory", ctypes.c_ubyte)]

    kernel = p.safety.K
    kernel.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel.GetFileInformationByHandleEx.restype = wintypes.BOOL
    marked, journal = {}, None

    def unlink_pinned(row):
        path = p.safety.boundary(Path(row["path"]))
        require(path.is_relative_to(target), "Immediate path escaped target")
        _, info = p.checked_file(path)
        require(p.identity(info) == row["identity"] and info.st_nlink == 1 and
                not info.st_file_attributes & (0x400 | 1), "Immediate file identity/links/attributes differ")
        # Exclusive READ+DELETE handle; hash and disposition refer to this same
        # pinned file object. No wildcard, recursive delete, or attribute change.
        handle = kernel.CreateFileW(str(path), 0x80010000, 0, None, 3, 0x00200000, None)
        if handle == ctypes.c_void_p(-1).value:
            raise ctypes.WinError(ctypes.get_last_error())
        fd, native_owned = None, True
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
            native_owned = False
            with os.fdopen(fd, "rb") as stream:
                fd = None  # stream now owns and closes the Windows handle.
                require(p.identity(os.fstat(stream.fileno())) == row["identity"], "Exclusive handle identity differs")
                require(hashlib.file_digest(stream, "sha256").hexdigest() == row["sha256"], "Immediate file SHA differs")
                require(p.identity(os.fstat(stream.fileno())) == row["identity"], "File changed while hashing exclusive handle")
                storage = FileStandardInfo()
                if not kernel.GetFileInformationByHandleEx(handle, 1, ctypes.byref(storage), ctypes.sizeof(storage)):
                    raise ctypes.WinError(ctypes.get_last_error())
                require(storage.links == 1 and storage.length == row["identity"]["bytes"] and
                        not storage.delete_pending and not storage.directory, "Exclusive storage identity differs")
                disposition = wintypes.BOOL(True)
                if not kernel.SetFileInformationByHandle(handle, 4, ctypes.byref(disposition), ctypes.sizeof(disposition)):
                    raise ctypes.WinError(ctypes.get_last_error())
                marked[row["path"]] = dict(logical_bytes=row["identity"]["bytes"], allocation_bytes=storage.allocation)
        finally:
            if fd is not None:
                os.close(fd)
            elif native_owned:
                # Only a failed ownership transfer leaves the raw handle here.
                kernel.CloseHandle(handle)
        require(not path.exists(), "Marked file still exists after exclusive close")

    try:
        require(p.failed_contract(BUILD_ID)[0] == target and digest(Path(plan["failed_report"]["path"])) == plan["failed_report"]["sha256"],
                "Failed build contract/report changed")
        require(p.request_scan(BUILD_ID) == plan["request_documents"], "Current request set/identity/SHA changed; a fresh plan is required")
        require(p.target_inventory(target) == targets, "Full target file/directory inventory changed")
        before_errors = guards()
        receipt["protected_before_errors"] = before_errors
        require(not before_errors, "Protected files changed before deletion")
        receipt["protected_before_verified"] = True
        require(digest(plan_path) == PLAN_SHA and digest(SELF) == args.code_sha256, "Plan/apply code changed before deletion")
        for key in ("target_ledger", "protected_ledger"):
            require(digest(Path(plan[key]["path"])) == plan[key]["sha256"], "Ledger changed before deletion")
        receipt["status"] = "REMOVING_LISTED_FILES_DO_NOT_REPLAY"
        checkpoint()
        journal = (OUT / "removed-files.jsonl").open("xb", buffering=0)
        for row in targets["files"]:
            receipt["pending_file"] = row["path"]
            checkpoint()
            unlink_pinned(row)
            details = marked[row["path"]]
            receipt["removed_files"] += 1
            receipt["removed_logical_bytes"] += details["logical_bytes"]
            receipt["removed_allocation_bytes"] += details["allocation_bytes"]
            line = (json.dumps(dict(path=str(Path(row["path"]).relative_to(target)), sha256=row["sha256"], **details), separators=(",", ":")) + "\n").encode()
            require(journal.write(line) == len(line), "Removed-file journal write failed")
            os.fsync(journal.fileno())
            receipt["pending_file"] = None
            checkpoint()
        for row in sorted(targets["directories"], key=lambda r: len(Path(r["path"]).parts), reverse=True):
            path = p.safety.boundary(Path(row["path"]))
            info = path.lstat()
            require((path == target or path.is_relative_to(target)) and stat.S_ISDIR(info.st_mode) and
                    str(info.st_dev) == row["identity"]["device"] and str(info.st_ino) == row["identity"]["file_id"] and
                    info.st_file_attributes == row["identity"]["attributes"] and not any(path.iterdir()),
                    "Directory identity changed or directory is not empty")
            path.rmdir()
            receipt["removed_directories"] += 1
        require(not target.exists(), "Failed target still exists")
        require(p.request_scan(BUILD_ID) == plan["request_documents"], "Request set/identity/SHA changed during cleanup")
        receipt["status"] = "TARGET_REMOVED_PENDING_PROTECTION_RECHECK"
    except Exception as error:
        receipt["status"] = "FAILED_DO_NOT_REPLAY"
        receipt["errors"].append(type(error).__name__ + ": " + str(error))
    finally:
        if journal is not None:
            journal.close()
        # Reconcile successful handle dispositions, even if a later journal or
        # close operation failed. No absent unattempted path is counted as ours.
        absent = [details for name, details in marked.items() if not Path(name).exists()]
        receipt["removed_files"] = len(absent)
        receipt["removed_logical_bytes"] = sum(row["logical_bytes"] for row in absent)
        receipt["removed_allocation_bytes"] = sum(row["allocation_bytes"] for row in absent)
        after_errors = guards()
        receipt["protected_after_errors"] = after_errors
        receipt["protected_after_verified"] = not after_errors
        if after_errors:
            receipt["status"] = "FAILED_DO_NOT_REPLAY"
            receipt["errors"].append("Protected file verification failed after cleanup")
        if not receipt["errors"] and receipt["removed_files"] == 67 and receipt["removed_directories"] == 14:
            receipt["status"] = "PASS_EXACT_FAILED_UI_HOST_REMOVED_PROTECTED_FILES_UNCHANGED"
        receipt["completed_utc"] = datetime.now(timezone.utc).isoformat()
        receipt["allocation_note"] = "Actual per-file NTFS allocation measured on exclusive handles; not a whole-volume free-space delta."
        receipt["plan_and_code_unchanged"] = digest(plan_path) == PLAN_SHA and digest(SELF) == args.code_sha256
        if not receipt["plan_and_code_unchanged"]:
            receipt["status"] = "FAILED_DO_NOT_REPLAY"
            receipt["errors"].append("Plan or apply code changed")
        receipt["ledgers_unchanged"] = all(digest(Path(plan[key]["path"])) == plan[key]["sha256"]
                                             for key in ("target_ledger", "protected_ledger"))
        if not receipt["ledgers_unchanged"]:
            receipt["status"] = "FAILED_DO_NOT_REPLAY"
            receipt["errors"].append("A pinned ledger changed")
        if (OUT / "removed-files.jsonl").exists():
            receipt["removed_journal"] = dict(path=str(OUT / "removed-files.jsonl"), sha256=digest(OUT / "removed-files.jsonl"))
        checkpoint()
    print(json.dumps(dict(status=receipt["status"], removed_files=receipt["removed_files"],
                          removed_logical_bytes=receipt["removed_logical_bytes"], removed_allocation_bytes=receipt["removed_allocation_bytes"],
                          protected_files=752, protected_before_verified=receipt["protected_before_verified"],
                          protected_after_verified=receipt["protected_after_verified"], errors=receipt["errors"],
                          report=str(OUT / "cleanup.json"), report_sha256=digest(OUT / "cleanup.json")), ensure_ascii=False))
    return 0 if receipt["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
