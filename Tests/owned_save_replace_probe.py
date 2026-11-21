"""Bounded Windows rename/replacement experiment using only newly created files.

This is an API behavior probe, not a production save-overwrite implementation.
No Host, GameCore, GUI, user save, or game process is opened or executed.
"""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

PROJECT = Path(__file__).absolute().parents[1]
BUILD_PARENT = PROJECT / "Build" / "OwnedSaveReplaceProbe"
EVIDENCE_PARENT = PROJECT / "evidence/save_overwrite/source_contract/native_probe"
SDK = Path(r"C:\Program Files (x86)\Windows Kits\10\Include\10.0.26100.0\um")
READ, WRITE, DELETE = 0x80000000, 0x40000000, 0x00010000
SHARE_READ, SHARE_WRITE, SHARE_DELETE = 1, 2, 4
REPARSE, BACKUP = 0x00200000, 0x02000000
INVALID = W.HANDLE(-1).value
DOCS = [
    "https://learn.microsoft.com/en-us/windows/win32/api/winbase/ns-winbase-file_rename_info",
    "https://learn.microsoft.com/en-us/windows/win32/api/fileapi/nf-fileapi-setfileinformationbyhandle",
    "https://learn.microsoft.com/en-us/windows/win32/api/minwinbase/ne-minwinbase-file_info_by_handle_class",
    "https://learn.microsoft.com/en-us/windows-hardware/drivers/ddi/ntifs/ns-ntifs-_file_rename_information",
]


class RenameUnion(C.Union):
    _fields_ = [("ReplaceIfExists", C.c_ubyte), ("Flags", W.DWORD)]


class RenameInfo(C.Structure):
    _anonymous_ = ("choice",)
    _fields_ = [("choice", RenameUnion), ("RootDirectory", W.HANDLE),
                ("FileNameLength", W.DWORD), ("FileName", W.WCHAR * 1)]


class HandleInfo(C.Structure):
    _fields_ = [("attributes", W.DWORD), ("creation", W.FILETIME),
                ("access", W.FILETIME), ("write", W.FILETIME),
                ("volume", W.DWORD), ("size_high", W.DWORD),
                ("size_low", W.DWORD), ("links", W.DWORD),
                ("index_high", W.DWORD), ("index_low", W.DWORD)]


class StandardInfo(C.Structure):
    _fields_ = [("allocation", C.c_longlong), ("size", C.c_longlong),
                ("links", W.DWORD), ("delete_pending", C.c_ubyte),
                ("directory", C.c_ubyte)]


class DispositionInfo(C.Structure):
    _fields_ = [("DeleteFile", C.c_ubyte)]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_record(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": sha(data)}


def check_sdk() -> dict:
    headers = {name: (SDK / name).read_text(encoding="utf-8-sig")
               for name in ("winbase.h", "minwinbase.h")}
    body = headers["minwinbase.h"].split("typedef enum _FILE_INFO_BY_HANDLE_CLASS", 1)[1].split("}", 1)[0]
    names = re.findall(r"^\s*(File\w+|MaximumFileInfoByHandleClass)\b", body, re.M)
    assert names.index("FileRenameInfoEx") == 22
    assert names.index("FileStandardInfo") == 1
    for name, value in (("FILE_RENAME_FLAG_REPLACE_IF_EXISTS", 1),
                        ("FILE_RENAME_FLAG_POSIX_SEMANTICS", 2)):
        match = re.search(r"#define\s+" + name + r"\s+(0x[0-9A-Fa-f]+)", headers["winbase.h"])
        assert match is not None and int(match[1], 16) == value
    structure = headers["winbase.h"].split("typedef struct _FILE_RENAME_INFO", 1)[1].split("FILE_RENAME_INFO,", 1)[0]
    assert re.search(r"BOOLEAN\s+ReplaceIfExists", structure)
    assert re.search(r"DWORD\s+Flags", structure)
    assert re.search(r"HANDLE\s+RootDirectory", structure)
    assert re.search(r"DWORD\s+FileNameLength", structure)
    assert re.search(r"WCHAR\s+FileName\[1\]", structure)
    assert C.sizeof(C.c_void_p) == 8 and C.sizeof(W.WCHAR) == 2
    assert [RenameInfo.choice.offset, RenameInfo.RootDirectory.offset,
            RenameInfo.FileNameLength.offset, RenameInfo.FileName.offset] == [0, 8, 16, 20]
    assert C.sizeof(RenameInfo) == 24
    return {"headers": [file_record(SDK / name) for name in headers],
            "FileRenameInfoEx": 22, "REPLACE_IF_EXISTS": 1, "POSIX_SEMANTICS": 2,
            "rename_info_size": C.sizeof(RenameInfo),
            "rename_info_offsets": {name: getattr(RenameInfo, name).offset
                                    for name in ("choice", "RootDirectory", "FileNameLength", "FileName")},
            "documentation": DOCS,
            "layout_authority": "Installed SDK winbase.h; the Learn FILE_RENAME_INFO page currently renders an extra ReplaceIfExists row, so its displayed syntax was not copied literally."}


class Kernel:
    def __init__(self):
        self.k = C.WinDLL("kernel32", use_last_error=True)
        signatures = {
            "CreateFileW": ([W.LPCWSTR, W.DWORD, W.DWORD, C.c_void_p, W.DWORD, W.DWORD, W.HANDLE], W.HANDLE),
            "CloseHandle": ([W.HANDLE], W.BOOL),
            "ReadFile": ([W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p], W.BOOL),
            "WriteFile": ([W.HANDLE, C.c_void_p, W.DWORD, C.POINTER(W.DWORD), C.c_void_p], W.BOOL),
            "FlushFileBuffers": ([W.HANDLE], W.BOOL),
            "SetFilePointerEx": ([W.HANDLE, C.c_longlong, C.POINTER(C.c_longlong), W.DWORD], W.BOOL),
            "SetFileInformationByHandle": ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            "GetFileInformationByHandle": ([W.HANDLE, C.POINTER(HandleInfo)], W.BOOL),
            "GetFileInformationByHandleEx": ([W.HANDLE, C.c_int, C.c_void_p, W.DWORD], W.BOOL),
            "GetFinalPathNameByHandleW": ([W.HANDLE, W.LPWSTR, W.DWORD, W.DWORD], W.DWORD),
            "GetFileAttributesW": ([W.LPCWSTR], W.DWORD),
            "CreateDirectoryW": ([W.LPCWSTR, C.c_void_p], W.BOOL),
            "RemoveDirectoryW": ([W.LPCWSTR], W.BOOL),
        }
        for name, (args, result) in signatures.items():
            method = getattr(self.k, name)
            method.argtypes, method.restype = args, result

    @staticmethod
    def require(value):
        if not value:
            raise C.WinError(C.get_last_error())
        return value

    def open(self, path, access=READ | DELETE, share=0, creation=3, directory=False):
        flags = REPARSE | (BACKUP if directory else 0)
        handle = self.k.CreateFileW(str(path), access, share, None, creation, flags, None)
        if handle == INVALID:
            raise C.WinError(C.get_last_error())
        return handle

    def close(self, handle):
        if handle is not None:
            self.require(self.k.CloseHandle(handle))

    def read(self, handle):
        self.require(self.k.SetFilePointerEx(handle, 0, None, 0))
        buffer = C.create_string_buffer(4096)
        count = W.DWORD()
        self.require(self.k.ReadFile(handle, buffer, len(buffer), C.byref(count), None))
        if count.value >= len(buffer):
            raise ValueError("unexpected oversized own fixture")
        return buffer.raw[:count.value]

    def describe(self, handle, read=True):
        basic, standard = HandleInfo(), StandardInfo()
        self.require(self.k.GetFileInformationByHandle(handle, C.byref(basic)))
        self.require(self.k.GetFileInformationByHandleEx(handle, 1, C.byref(standard), C.sizeof(standard)))
        out = {"file_id": [basic.volume, basic.index_high, basic.index_low],
               "hardlink_count": basic.links, "attributes": basic.attributes,
               "bytes": standard.size, "allocation_bytes": standard.allocation,
               "delete_pending": bool(standard.delete_pending),
               "directory": bool(standard.directory),
               "filetime_last_write": (basic.write.dwHighDateTime << 32) | basic.write.dwLowDateTime}
        final = C.create_unicode_buffer(32768)
        C.set_last_error(0)
        size = self.k.GetFinalPathNameByHandleW(handle, final, len(final), 0)
        if size:
            assert size < len(final)
            out["final_path"] = final.value.removeprefix("\\\\?\\")
        else:
            out["final_path_error"] = C.get_last_error()
        if read:
            content = self.read(handle)
            assert len(content) == out["bytes"]
            out["sha256"] = sha(content)
            out["content_ascii"] = content.decode("ascii")
        return out

    def absent(self, path):
        C.set_last_error(0)
        value = self.k.GetFileAttributesW(str(path))
        return value == 0xFFFFFFFF and C.get_last_error() in (2, 3)

    def rename(self, handle, target, flags):
        encoded = str(target).encode("utf-16-le")
        buffer = C.create_string_buffer(C.sizeof(RenameInfo) + len(encoded))
        value = RenameInfo.from_buffer(buffer)
        value.Flags, value.RootDirectory, value.FileNameLength = flags, None, len(encoded)
        C.memmove(C.addressof(buffer) + RenameInfo.FileName.offset, encoded, len(encoded))
        C.set_last_error(0)
        result = self.k.SetFileInformationByHandle(handle, 22, buffer, len(buffer))
        error = 0 if result else C.get_last_error()
        return {"success": bool(result), "winerror": error,
                "error_message": C.FormatError(error).strip() if error else "",
                "information_class": 22, "flags": flags,
                "buffer_bytes": len(buffer), "name_bytes": len(encoded)}


def non_reparse_path(path):
    resolved = path.resolve(strict=True)
    if os.path.normcase(str(resolved)) != os.path.normcase(str(path.absolute())):
        raise ValueError("resolved path differs from intended path")
    for ancestor in (path, *path.parents):
        if getattr(os.lstat(ancestor), "st_file_attributes", 0) & 0x400:
            raise ValueError("reparse ancestor: " + str(ancestor))


def run():
    sdk = check_sdk()
    api = Kernel()
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    evidence = EVIDENCE_PARENT / run_id
    evidence.mkdir(parents=True, exist_ok=False)
    root = BUILD_PARENT / run_id
    report = {"schema": "zerosis.owned_save_replace_probe.v1", "run_id": run_id,
              "status": "RUNNING", "utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "source": file_record(Path(__file__).absolute()), "sdk": sdk,
              "fixture_root": str(root), "windows_version": str(sys.getwindowsversion()),
              "cases": [], "retail_files_accessed": False,
              "host_gamecore_hwnd_or_game_process_accessed": False,
              "production_sources_changed": False,
              "rename_old_then_delete_or_recreate_used": False,
              "limits": ["Only same-directory own text files on the current Windows/filesystem were tested.",
                         "This is not a crash/power-failure durability test, filesystem/filter compatibility guarantee, or production archive overwrite test.",
                         "FileRenameInfoEx does not accept an expected target file ID. A successful operation alone does not prove compare-and-swap protection against a competing name replacement.",
                         "No production save eligibility, archive checksum, bundle manifest, parent-pin policy, or catalog integration was exercised."]}
    cleanup = {"schema": "zerosis.owned_save_replace_probe.cleanup.v1", "run_id": run_id,
               "root": str(root), "status": "NOT_STARTED", "files": [], "directories": [],
               "unexpected_entries": [], "root_removed": False}
    pins, originals, known_names = [], {}, set()
    root_identity = None
    error = None
    try:
        non_reparse_path(PROJECT / "Build")
        if not BUILD_PARENT.exists():
            api.require(api.k.CreateDirectoryW(str(BUILD_PARENT), None))
        non_reparse_path(BUILD_PARENT)
        for directory in (PROJECT, PROJECT / "Build", BUILD_PARENT):
            pins.append(api.open(directory, 0x80, SHARE_READ | SHARE_WRITE, directory=True))
        api.require(api.k.CreateDirectoryW(str(root), None))
        non_reparse_path(root)
        pins.append(api.open(root, 0x80, SHARE_READ | SHARE_WRITE, directory=True))
        root_identity = api.describe(pins[-1], read=False)
        assert os.path.normcase(root_identity["final_path"]) == os.path.normcase(str(root))
        report["root_identity"] = root_identity

        def create(name, content):
            path = root / name
            assert path.parent == root and path.suffix == ".txt"
            known_names.add(name)
            handle = api.open(path, READ | WRITE | DELETE, 0, creation=1)
            try:
                count = W.DWORD()
                api.require(api.k.WriteFile(handle, content, len(content), C.byref(count), None))
                assert count.value == len(content)
                api.require(api.k.FlushFileBuffers(handle))
                observed = api.describe(handle)
                assert observed["content_ascii"] == content.decode("ascii")
                assert observed["hardlink_count"] == 1 and not (observed["attributes"] & 0x400)
                originals[tuple(observed["file_id"])] = observed
                return path, observed
            finally:
                api.close(handle)

        shares = [("exclusive", 0), ("read", SHARE_READ),
                  ("read_delete", SHARE_READ | SHARE_DELETE),
                  ("read_write_delete", SHARE_READ | SHARE_WRITE | SHARE_DELETE)]
        for share_name, share in shares:
            for flags in (1, 3):
                label = f"{share_name}_flags{flags}"
                old_bytes = f"OLD:{run_id}:{label}\n".encode("ascii")
                new_bytes = f"NEW:{run_id}:{label}\n".encode("ascii")
                target, old_info = create(label + "_target.txt", old_bytes)
                stage, new_info = create(label + "_stage.txt", new_bytes)
                row = {"case": label, "target_access": READ | DELETE,
                       "target_share": share, "stage_access": READ | DELETE,
                       "stage_share": SHARE_READ | SHARE_DELETE,
                       "target_before": old_info, "stage_before": new_info}
                report["cases"].append(row)
                target_handle = stage_handle = reader = None
                try:
                    target_handle = api.open(target, READ | DELETE, share)
                    stage_handle = api.open(stage, READ | DELETE, SHARE_READ | SHARE_DELETE)
                    assert api.describe(target_handle)["file_id"] == old_info["file_id"]
                    assert api.describe(stage_handle)["file_id"] == new_info["file_id"]
                    row["rename"] = api.rename(stage_handle, target, flags)
                    row["old_handle_after"] = api.describe(target_handle)
                    row["stage_handle_after"] = api.describe(stage_handle)
                    assert row["old_handle_after"]["file_id"] == old_info["file_id"]
                    assert row["old_handle_after"]["sha256"] == sha(old_bytes)
                    assert row["stage_handle_after"]["file_id"] == new_info["file_id"]
                    assert row["stage_handle_after"]["sha256"] == sha(new_bytes)
                    try:
                        reader = api.open(target, READ, SHARE_READ | SHARE_WRITE | SHARE_DELETE)
                        row["name_while_old_handle_open"] = api.describe(reader)
                        expected = new_info if row["rename"]["success"] else old_info
                        assert row["name_while_old_handle_open"]["file_id"] == expected["file_id"]
                        assert row["name_while_old_handle_open"]["sha256"] == expected["sha256"]
                    except OSError as exc:
                        row["name_while_old_handle_open_error"] = exc.winerror
                        if row["rename"]["success"]:
                            raise
                    row["stage_name_absent_while_handles_open"] = api.absent(stage)
                    assert row["stage_name_absent_while_handles_open"] == row["rename"]["success"]
                    row["old_read_and_name_new_verified_while_old_open"] = (
                        row["rename"]["success"] and row["name_while_old_handle_open"]["file_id"] == new_info["file_id"])
                finally:
                    for handle in (reader, stage_handle, target_handle):
                        api.close(handle)
                handle = api.open(target, READ, SHARE_READ | SHARE_WRITE | SHARE_DELETE)
                try:
                    row["target_after_all_case_handles_closed"] = api.describe(handle)
                    expected = new_info if row["rename"]["success"] else old_info
                    assert row["target_after_all_case_handles_closed"]["file_id"] == expected["file_id"]
                    assert row["target_after_all_case_handles_closed"]["sha256"] == expected["sha256"]
                finally:
                    api.close(handle)
                if not row["rename"]["success"]:
                    handle = api.open(stage, READ, SHARE_READ | SHARE_WRITE | SHARE_DELETE)
                    try:
                        row["stage_after_failed_replace"] = api.describe(handle)
                        assert row["stage_after_failed_replace"]["file_id"] == new_info["file_id"]
                        assert row["stage_after_failed_replace"]["sha256"] == new_info["sha256"]
                    finally:
                        api.close(handle)
                row["observations_verified"] = True
        report["status"] = "PROBE_COMPLETED"
        report["exclusive_posix_replace_observed"] = next(
            r["rename"]["success"] for r in report["cases"] if r["case"] == "exclusive_flags3")
        report["any_posix_replace_observed"] = any(
            r["rename"]["success"] for r in report["cases"] if r["rename"]["flags"] == 3)
    except BaseException as exc:
        error = exc
        report["status"] = "PROBE_FAILED"
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        try:
            if root_identity is not None:
                current_identity = api.describe(pins[-1], read=False)
                assert current_identity["file_id"] == root_identity["file_id"]
                assert os.path.normcase(current_identity["final_path"]) == os.path.normcase(str(root))
                assert root.resolve(strict=True).parent == BUILD_PARENT.resolve(strict=True)
                non_reparse_path(root)
                entries = list(root.iterdir())
                if any(f.name not in known_names or not f.is_file() for f in entries):
                    cleanup["unexpected_entries"] = [str(f) for f in entries if f.name not in known_names or not f.is_file()]
                    raise ValueError("unexpected cleanup entry")
                for path in sorted(entries):
                    handle = api.open(path, READ | DELETE, 0)
                    try:
                        observed = api.describe(handle)
                        original = originals[tuple(observed["file_id"])]
                        assert observed["sha256"] == original["sha256"]
                        assert observed["bytes"] == original["bytes"]
                        assert observed["hardlink_count"] == 1 and not (observed["attributes"] & 0x400)
                        assert os.path.normcase(observed["final_path"]) == os.path.normcase(str(path))
                        receipt = {"path": str(path), "before": observed, "status": "VALIDATED"}
                        cleanup["files"].append(receipt)
                        disposition = DispositionInfo(1)
                        api.require(api.k.SetFileInformationByHandle(handle, 4, C.byref(disposition), C.sizeof(disposition)))
                    finally:
                        api.close(handle)
                    assert api.absent(path)
                    receipt["status"] = "REMOVED_BY_VALIDATED_EXCLUSIVE_HANDLE"
                assert not list(root.iterdir())
                api.close(pins.pop())
                api.require(api.k.RemoveDirectoryW(str(root)))
                assert api.absent(root)
                cleanup["directories"].append(str(root))
                cleanup["root_removed"] = True
                cleanup["status"] = "COMPLETE"
            else:
                cleanup["status"] = "NO_PROBE_ROOT_WAS_PINNED"
        except BaseException as exc:
            cleanup["status"] = "CLEANUP_FAILED"
            cleanup["error"] = {"type": type(exc).__name__, "message": str(exc)}
            if error is None:
                error = exc
                report["status"] = "PROBE_FAILED_CLEANUP"
        finally:
            for handle in reversed(pins):
                api.close(handle)
        cleanup["known_original_files"] = [{"file_id": r["file_id"], "bytes": r["bytes"], "sha256": r["sha256"]}
                                             for r in originals.values()]
        cleanup["removed_file_count"] = sum(r["status"].startswith("REMOVED") for r in cleanup["files"])
        cleanup["removed_named_logical_bytes"] = sum(r["before"]["bytes"] for r in cleanup["files"] if r["status"].startswith("REMOVED"))
        cleanup["removed_named_allocation_bytes"] = sum(r["before"]["allocation_bytes"] for r in cleanup["files"] if r["status"].startswith("REMOVED"))
        cleanup["superseded_old_file_unlinks"] = [r["target_before"] for r in report["cases"]
                                                if r.get("rename", {}).get("success")]
        cleanup["superseded_old_file_unlink_note"] = "Successful replacements remove the original target name atomically; its old handle was read before close. These original IDs are recorded separately, not counted again as named cleanup files."
        (evidence / "cleanup.json").write_text(json.dumps(cleanup, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["cleanup"] = file_record(evidence / "cleanup.json")
        report["source_after"] = file_record(Path(__file__).absolute())
        assert report["source"] == report["source_after"]
        (evidence / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "result": file_record(evidence / "result.json"),
                      "cleanup": report["cleanup"], "case_count": len(report["cases"]),
                      "exclusive_posix_replace_observed": report.get("exclusive_posix_replace_observed"),
                      "case_outcomes": [{"case": r["case"], "rename": r.get("rename"),
                                         "old_read_name_new_verified": r.get("old_read_and_name_new_verified_while_old_open")}
                                        for r in report["cases"]],
                      "cleanup_status": cleanup["status"], "fixture_root_removed": cleanup["root_removed"]}, ensure_ascii=False))
    if error is not None:
        raise error


if __name__ == "__main__":
    run()
