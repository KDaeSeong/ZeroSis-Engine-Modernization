"""Delete only this focused run's sealed, regenerable OBJ files."""
from __future__ import annotations

import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[4]
EVIDENCE = Path(__file__).resolve().parent
BUILD = ROOT / "Build" / "SaveMenuTransport"
SOURCES = (
    "Source/Presentation/BitmapWindow.h",
    "Source/Presentation/BitmapWindow.cpp",
    "Source/Host/UiInputDispatch.h",
    "Tests/bitmap_window.cpp",
    "Tests/ui_input_dispatch.cpp",
    "tools/verify_bitmap_window.py",
    "tools/build_ui_window_host.py",
)
SHELL = Path(r"C:\Users\home\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe")
KERNEL = ctypes.WinDLL("kernel32", use_last_error=True)
KERNEL.GetCompressedFileSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
KERNEL.GetCompressedFileSizeW.restype = wintypes.DWORD


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def boundary(path, root=ROOT):
    absolute = Path(os.path.abspath(path))
    require(absolute != root and absolute.is_relative_to(root), "Path is outside the exact owned root")
    require(absolute.resolve(strict=True) == absolute, "Resolved path differs")
    for ancestor in [absolute, *absolute.parents]:
        require(not getattr(ancestor.lstat(), "st_file_attributes", 0) & 0x400,
                "Reparse point or ancestor: " + str(ancestor))
        if ancestor == root:
            break
    return absolute


def record(path):
    path = boundary(path)
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode), "Not a regular file")
    return {"path": str(path), "bytes": info.st_size, "sha256": digest(path),
            "device": info.st_dev, "file_id": info.st_ino, "links": info.st_nlink,
            "mtime_ns": info.st_mtime_ns, "mode": info.st_mode,
            "attributes": getattr(info, "st_file_attributes", 0)}


def stored_bytes(path):
    high = wintypes.DWORD()
    ctypes.set_last_error(0)
    low = KERNEL.GetCompressedFileSizeW(str(path), ctypes.byref(high))
    if low == 0xFFFFFFFF and ctypes.get_last_error():
        raise ctypes.WinError(ctypes.get_last_error())
    return (high.value << 32) | low


def usage(root):
    count = logical = unique_logical = stored = 0
    seen = set()
    for path in sorted(root.rglob("*")):
        boundary(path)
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            continue
        count += 1
        logical += info.st_size
        identity = (info.st_dev, info.st_ino)
        if identity not in seen:
            seen.add(identity)
            unique_logical += info.st_size
            stored += stored_bytes(path)
    return {"files": count, "logical_bytes": logical,
            "unique_logical_bytes": unique_logical,
            "win32_reported_stored_bytes": stored,
            "volume_free_space_measured": False}


def own_process_guard():
    owned_path = str(BUILD.resolve(strict=True)).replace("'", "''") + "\\"
    command = ("$taskOwnedPath='" + owned_path + "'; "
               "@((Get-Process -ErrorAction Stop) | Where-Object { "
               "$_.Path -and $_.Path.StartsWith($taskOwnedPath,[System.StringComparison]::OrdinalIgnoreCase) }).Count")
    result = subprocess.run([str(SHELL), "-NoLogo", "-NoProfile", "-Command", command],
                            capture_output=True, text=True, timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0 and result.stdout.strip() == "0",
            "An owned focused-test process is active or its status is unknown")


def write(path, value):
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def main():
    own_process_guard()
    require(BUILD.resolve(strict=True) == BUILD, "Owned build root changed")
    candidates = [path for path in sorted(BUILD.rglob("*")) if path.suffix.lower() == ".obj"]
    require(len(candidates) == 22, "Unexpected OBJ inventory; require a fresh reviewed scope")
    rows = []
    for path in candidates:
        boundary(path, BUILD)
        row = record(path)
        require(row["links"] == 1, "OBJ has another hardlink")
        rows.append(row)
    require(sum(row["bytes"] for row in rows) == 14029046, "Reviewed byte count changed")
    protected_paths = [ROOT / source for source in SOURCES]
    protected_paths += [path for path in sorted(BUILD.rglob("*"))
                        if path.is_file() and path.suffix.lower() != ".obj"]
    protected_paths += [path for path in sorted(EVIDENCE.rglob("*")) if path.is_file()]
    protected_paths += [path for path in sorted((EVIDENCE.parent / "source_before").rglob("*"))
                        if path.is_file()]
    protected = [record(path) for path in dict.fromkeys(protected_paths)]
    protected_ids = {(row["device"], row["file_id"]) for row in protected}
    require(not any((row["device"], row["file_id"]) in protected_ids for row in rows),
            "Candidate aliases a protected source, result or evidence file")
    before_build, before_evidence = usage(BUILD), usage(EVIDENCE)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + secrets.token_hex(4)
    output = EVIDENCE / "cleanup" / stamp
    output.mkdir(parents=True, exist_ok=False)
    plan = {"schema": "ZEROSIS_SAVE_MENU_TRANSPORT_OBJ_CLEANUP_PLAN_V1",
            "created_utc": datetime.now(timezone.utc).isoformat(), "owned_root": str(BUILD),
            "regenerable_objects_only": True, "source_or_saves_deleted": False,
            "active_other_agent_host_build_ignored_by_scope": True,
            "candidates": rows, "protected": protected,
            "before_build": before_build, "before_evidence": before_evidence}
    plan_path = output / "plan.json"
    write(plan_path, plan)
    deleted = []
    for row in rows:
        path = Path(row["path"])
        boundary(path, BUILD)
        require(record(path) == row, "Candidate changed after the sealed plan")
        path.unlink()
        require(not path.exists(), "Deleted object remains present")
        deleted.append({**row, "result": "deleted"})
    for row in protected:
        require(record(Path(row["path"])) == row, "Protected file changed during cleanup")
    own_process_guard()
    after_build = usage(BUILD)
    require(after_build["unique_logical_bytes"] == before_build["unique_logical_bytes"] - 14029046,
            "Unexpected owned build storage change")
    report = {"schema": "ZEROSIS_SAVE_MENU_TRANSPORT_OBJ_CLEANUP_RESULT_V1",
              "status": "PASS", "plan": record(plan_path), "deleted": deleted,
              "deleted_files": len(deleted), "deleted_logical_bytes": 14029046,
              "protected_files_verified": len(protected), "protected_files_unchanged": True,
              "before_build": before_build, "after_build": after_build,
              "before_evidence": before_evidence,
              "remaining_obj_files": len(list(BUILD.rglob("*.obj"))),
              "volume_free_space_measured": False}
    report_path = output / "cleanup.json"
    write(report_path, report)
    evidence_after = usage(EVIDENCE)
    write(output / "usage_after.json", {"evidence_after_result_receipt": evidence_after,
                                        "usage_receipt_itself_excluded": True})
    print(json.dumps({"status": "PASS", "report": str(report_path),
                      "report_sha256": digest(report_path), "deleted_files": 22,
                      "deleted_logical_bytes": 14029046,
                      "protected_files_verified": len(protected),
                      "before_build": before_build, "after_build": after_build,
                      "evidence_after_result_receipt": evidence_after}))


if __name__ == "__main__":
    main()
