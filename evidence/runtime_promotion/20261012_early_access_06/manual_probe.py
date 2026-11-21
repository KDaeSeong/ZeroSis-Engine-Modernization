"""Machine-operated smoke=false Start-Engine save/restore probe for EA0.6.

This intentionally uses the ordinary launcher and posts only F5 and WM_CLOSE
to the visible game window owned by that launch's recorded driver PID. It is
not human play or a test of retail Civ V.
"""
from __future__ import annotations

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time


RUN_ID = "20261012T121847Z_732a6d5f07ea"
GAME_TITLE = "ZeroSis' Civilization - 전략 지도"
DEADLINE_SECONDS = 180
ROOT = Path(__file__).resolve().parents[3]
RUNTIME = ROOT / "Build" / "InteractiveGameRuntime" / RUN_ID
SESSION_ROOT = RUNTIME / "sessions"
EVIDENCE = Path(__file__).resolve().parent
MANUAL_ROOT = ROOT / "evidence" / "manual_play"
LAUNCHER = ROOT / "tools" / "Start-Engine.ps1"
REPORT_PATH = EVIDENCE / "manual_probe_result.json"
RELOCATION_PATH = EVIDENCE / "manual_probe_relocation.json"
POWERSHELL_FALLBACK = Path(r"C:\Users\home\.cache\codex-runtimes\codex-primary-runtime\dependencies\native\powershell\pwsh.exe")


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def inventory_saves() -> dict[str, str]:
    result = {}
    runtime_root = ROOT / "Build" / "InteractiveGameRuntime"
    for path in runtime_root.rglob("*.zssave"):
        if path.is_file():
            result[str(path.resolve())] = digest(path)
    return result


def inventory_digest(items: dict[str, str]) -> str:
    material = "\n".join(f"{path}|{items[path]}" for path in sorted(items))
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def pwsh() -> str:
    found = shutil.which("pwsh")
    if found:
        return found
    require(POWERSHELL_FALLBACK.is_file(), "pwsh was not found")
    return str(POWERSHELL_FALLBACK)


def run_plan(mode: str, checkpoint: Path | None = None) -> dict:
    args = [pwsh(), "-NoProfile", "-File", str(LAUNCHER), "-EarlyAccess", "-Mode", mode, "-PlanOnly"]
    if checkpoint is not None:
        args.extend(["-Checkpoint", str(checkpoint)])
    completed = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, timeout=20, check=False)
    require(completed.returncode == 0, f"Start-Engine {mode} preflight failed: {completed.stderr[-1000:]}")
    try:
        plan = json.loads(completed.stdout.strip())
    except json.JSONDecodeError as error:
        raise RuntimeError("Start-Engine preflight did not return JSON") from error
    require(Path(plan.get("runtime", "")).resolve() == RUNTIME.resolve(),
            f"EarlyAccess {mode} routes to a different runtime: {plan.get('runtime')}")
    require(plan.get("smoke_inputs") is False and plan.get("total_play_timeout_seconds") == 0,
            "Start-Engine plan is not an unbounded manual-play route")
    require(Path(plan.get("launcher", "")).is_file(), "Selected Play/Resume launcher is missing")
    return plan


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


def find_owned_host(driver_pid: int) -> tuple[int, str] | None:
    """Find the driver's direct child only when its full image path is EA06 Host."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32FirstW.restype = wintypes.BOOL
    kernel32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    kernel32.Process32NextW.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD)]
    kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    require(snapshot not in (None, 0, wintypes.HANDLE(-1).value), "CreateToolhelp32Snapshot failed")
    found = []
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(entry)
        more = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            if entry.th32ParentProcessID == driver_pid and entry.szExeFile.casefold() == "zerosishost_x64.exe":
                process = kernel32.OpenProcess(0x1000, False, entry.th32ProcessID)
                if process:
                    try:
                        buffer = ctypes.create_unicode_buffer(32768)
                        size = wintypes.DWORD(len(buffer))
                        if kernel32.QueryFullProcessImageNameW(process, 0, buffer, ctypes.byref(size)):
                            image = Path(buffer.value).resolve()
                            if image == (RUNTIME / "ZeroSisHost_x64.exe").resolve():
                                found.append((int(entry.th32ProcessID), str(image)))
                    finally:
                        kernel32.CloseHandle(process)
            more = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
    finally:
        kernel32.CloseHandle(snapshot)
    require(len(found) <= 1, "Multiple EA06 Host children belong to the same UI driver")
    return found[0] if found else None


def enumerate_owned_window(pid: int):
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.EnumWindows.argtypes = [ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM), wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetClientRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetClientRect.restype = wintypes.BOOL
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = []

    @callback_type
    def visit(hwnd, _):
        owner = wintypes.DWORD()
        tid = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid or not tid or not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, len(title))
        client = wintypes.RECT()
        if title.value == GAME_TITLE and user32.GetClientRect(hwnd, ctypes.byref(client)) and client.right > 0 and client.bottom > 0:
            found.append((int(hwnd), int(tid), [int(client.right), int(client.bottom)]))
        return True

    require(bool(user32.EnumWindows(visit, 0)), "EnumWindows failed")
    require(len(found) <= 1, "Multiple visible game windows belong to the selected driver PID")
    return user32, found[0] if found else None


def post_owned(user32, hwnd: int, message: int, wparam: int, lparam: int, driver_pid: int, tid: int) -> None:
    owner = wintypes.DWORD()
    actual_tid = user32.GetWindowThreadProcessId(wintypes.HWND(hwnd), ctypes.byref(owner))
    require(owner.value == driver_pid and actual_tid == tid, "Refusing input to a window outside the launch-owned PID/thread")
    user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.PostMessageW.restype = wintypes.BOOL
    require(bool(user32.PostMessageW(wintypes.HWND(hwnd), message, wparam, lparam)),
            f"PostMessageW failed for owned HWND {hwnd}")


def wait_for(predicate, description: str, seconds: int = DEADLINE_SECONDS):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise TimeoutError(f"Timed out waiting for {description}")


def wait_for_native_save_marker(log_path: Path, save_path: Path) -> tuple[int, str]:
    def find_marker():
        if not log_path.is_file():
            return None
        output = log_path.read_text(encoding="utf-8", errors="replace")
        for turn, raw_path in re.findall(r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$", output, re.M):
            if Path(raw_path).resolve() == save_path.resolve():
                return int(turn), raw_path
        return None
    return wait_for(find_marker, "Host INTERACTIVE_NATIVE_SAVE marker")


def readable_save_size(path: Path) -> int | None:
    """Return a positive size only after the atomic save is openable for reading."""
    try:
        with path.open("rb") as stream:
            size = os.fstat(stream.fileno()).st_size
            return size if size > 0 else None
    except (OSError, PermissionError):
        return None


def new_session_dirs(before: set[str]) -> list[Path]:
    if not SESSION_ROOT.is_dir():
        return []
    return [path for path in SESSION_ROOT.iterdir() if path.is_dir() and
            str(path.resolve()) not in before]


def new_launch_dirs(before: set[str]) -> list[Path]:
    if not MANUAL_ROOT.is_dir():
        return []
    return [path for path in MANUAL_ROOT.iterdir() if path.is_dir() and str(path.resolve()) not in before and
            (path / "launch.json").is_file()]


def launch(mode: str, checkpoint: Path | None, report: dict) -> tuple[dict, Path, dict]:
    before_dirs = {str(path.resolve()) for path in MANUAL_ROOT.iterdir() if path.is_dir()} if MANUAL_ROOT.is_dir() else set()
    before_sessions = {str(path.resolve()) for path in SESSION_ROOT.iterdir() if path.is_dir()}
    args = [pwsh(), "-NoProfile", "-File", str(LAUNCHER), "-EarlyAccess", "-Mode", mode]
    if checkpoint is not None:
        args.extend(["-Checkpoint", str(checkpoint)])
    env = os.environ.copy()
    for key in list(env):
        if key.upper().startswith("ZEROSIS_PLAY_"):
            env.pop(key)
    wrapper = subprocess.Popen(args, cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))
    report["launches"].append({"requested_mode": mode, "wrapper_pid": wrapper.pid, "native_inputs": []})
    launch_dir = None
    launch_path = None
    record = None
    driver_pid = None
    host_pid = None
    host_path = None
    hwnd = None
    tid = None
    user32 = None
    try:
        launch_dir = wait_for(lambda: (dirs[0] if len(dirs := new_launch_dirs(before_dirs)) == 1 else None),
                              f"{mode} launch record")
        launch_path = launch_dir / "launch.json"

        def read_record():
            try:
                doc = json.loads(launch_path.read_text(encoding="utf-8-sig"))
                return doc if doc.get("driver_pid") else None
            except (OSError, json.JSONDecodeError):
                return None

        record = wait_for(read_record, "Start-Engine driver PID")
        common = (record.get("mode") == mode and record.get("requested_mode") == mode and
                  Path(record.get("runtime", "")).resolve() == RUNTIME.resolve() and
                  record.get("smoke_inputs") is False and record.get("total_play_timeout_seconds") == 0)
        correct_checkpoint = not record.get("checkpoint") if mode == "New" else (
            checkpoint is not None and Path(record.get("checkpoint", "")).resolve() == checkpoint.resolve())
        require(common and correct_checkpoint, "launch.json does not prove the requested ordinary mode/runtime/checkpoint")
        driver_pid = int(record["driver_pid"])

        # Start-Engine owns stdout.log with FileShare.None while the launch is
        # active. Correlate the private session through the EA06 sessions tree.
        sessions = wait_for(lambda: (items[0] if len(items := new_session_dirs(before_sessions)) == 1 else None),
                            "new private EA06 session directory")
        session_dir = sessions.resolve(strict=True)
        require(session_dir.is_relative_to(SESSION_ROOT.resolve()), "Private session escaped EA06 sessions")
        report["launches"][-1].update({"runtime": str(RUNTIME), "session": str(session_dir),
                                      "driver_pid": driver_pid})
        host = wait_for(lambda: find_owned_host(driver_pid), "EA06 Host child process")
        host_pid, host_path = host
        report["launches"][-1].update({"host_pid": host_pid, "host_path": host_path})
        owned = wait_for(lambda: (state if (state := enumerate_owned_window(host_pid))[1] is not None else None),
                         "launch-owned visible game window")
        user32, window = owned
        # The exact PID/title/client identity is the readiness gate. Host creates
        # this window only after preparing and committing its initial scene.
        hwnd, tid, client = window
        report["launches"][-1].update({"hwnd": hwnd, "window_thread": tid, "client": client})
        write_report(report)
        if mode == "New":
            before_files = {path.resolve() for path in session_dir.rglob("*.zssave") if path.is_file()}
            post_owned(user32, hwnd, 0x0100, 0x74, 1, host_pid, tid)  # WM_KEYDOWN / VK_F5
            report["launches"][-1]["native_inputs"].append({"message": "WM_KEYDOWN", "key": "VK_F5", "hwnd": hwnd,
                                                              "pid": host_pid, "thread": tid})
            checkpoint_path = wait_for(lambda: next((path.resolve() for path in session_dir.rglob("play-save-*-turn-*.zssave")
                                                      if path.is_file() and path.resolve() not in before_files), None),
                                       "F5-created native save")
            require(checkpoint_path.is_relative_to(SESSION_ROOT.resolve()), "F5 save escaped the EA06 session tree")
            size_before = wait_for(lambda: readable_save_size(checkpoint_path),
                                   "positive closed-readable atomic F5 save bytes")
            report["launches"][-1]["f5_save"] = {"path": str(checkpoint_path), "bytes_before_close": size_before}
            write_report(report)
        else:
            checkpoint_path = checkpoint.resolve()
        post_owned(user32, hwnd, 0x0010, 0, 0, host_pid, tid)  # WM_CLOSE
        report["launches"][-1]["native_inputs"].append({"message": "WM_CLOSE", "hwnd": hwnd,
                                                          "pid": host_pid, "thread": tid})
        write_report(report)
        require(wrapper.wait(timeout=DEADLINE_SECONDS) == 0, f"Start-Engine {mode} wrapper returned nonzero")
    finally:
        try:
            # Setup failures also close only the Host child belonging to this
            # wrapper. Never leave a started native Host behind, even if the
            # launcher wrapper has already returned.
            if launch_path is None:
                candidates = new_launch_dirs(before_dirs)
                if len(candidates) == 1:
                    launch_dir = candidates[0]
                    launch_path = launch_dir / "launch.json"
            if driver_pid is None and launch_path is not None and launch_path.is_file():
                try:
                    cleanup_record = json.loads(launch_path.read_text(encoding="utf-8-sig"))
                    driver_pid = int(cleanup_record.get("driver_pid") or 0) or None
                    report["launches"][-1]["cleanup_launch_record"] = str(launch_path)
                except (OSError, ValueError, json.JSONDecodeError):
                    pass
            if host_pid is None and driver_pid is not None:
                owned_host = find_owned_host(driver_pid)
                if owned_host is None and wrapper.poll() is None:
                    owned_host = wait_for(lambda: find_owned_host(driver_pid), "owned Host for cleanup", 30)
                if owned_host:
                    host_pid, host_path = owned_host
            if host_pid is not None:
                owned = enumerate_owned_window(host_pid)
                if owned[1] is None and wrapper.poll() is None:
                    owned = wait_for(lambda: (state if (state := enumerate_owned_window(host_pid))[1] is not None else None),
                                     "owned game window for cleanup", 30)
                if owned[1] is not None:
                    user32, window = owned
                    hwnd, tid, _ = window
                    post_owned(user32, hwnd, 0x0010, 0, 0, host_pid, tid)
                    report["launches"][-1].setdefault("cleanup", []).append({"message": "WM_CLOSE", "hwnd": hwnd,
                                                                                "pid": host_pid, "thread": tid})
                    write_report(report)
            if wrapper.poll() is None:
                wrapper.wait(timeout=30)
        except Exception as cleanup_error:
            report["launches"][-1]["cleanup_error"] = str(cleanup_error)
            try:
                write_report(report)
            except Exception:
                pass
    require(launch_dir is not None and launch_path is not None and driver_pid is not None and
            host_pid is not None and session_dir.is_dir(), "Launch setup did not establish owned runtime/session identity")
    require(wrapper.poll() is not None, "Launcher wrapper is still active; refusing to read its locked stdout.log")
    completed = wait_for(lambda: (doc if (doc := json.loads(launch_path.read_text(encoding="utf-8-sig"))).get("status") in
                                  ("CLOSED", "FAILED") else None), "closed launcher record", 20)
    driver_result_path = launch_dir / "driver_result.json"
    require(completed.get("status") == "CLOSED" and driver_result_path.is_file(),
            f"Start-Engine {mode} did not close cleanly")
    driver_result = json.loads(driver_result_path.read_text(encoding="utf-8-sig"))
    require(int(driver_result.get("pid", -1)) == host_pid, "Driver result Host PID differs from the input-owned process")
    expected_mode = "--play" if mode == "New" else "--play-load"
    command = driver_result.get("command")
    require(driver_result.get("status") == "INTERACTIVE_UI_DRIVER_PASS" and driver_result.get("returncode") == 0 and
            driver_result.get("timeout_seconds") == 0 and isinstance(command, list) and len(command) >= 2 and
            command[1] == expected_mode and "smoke" not in command[1],
            f"Driver did not prove ordinary {expected_mode} with rc=0")
    profile = driver_result.get("sdk_session_profile", {})
    require(profile.get("ZEROSIS_PLAY_TOP_PANEL") == "1" and
            profile.get("ZEROSIS_PLAY_ACTION_INFO_PANEL") == "1" and
            profile.get("ZEROSIS_PLAY_NOTIFICATION_PANEL") == "1",
            "Ordinary EA06 HUD panel profile differs from its requested interactive bundle")
    if mode == "Load":
        require(checkpoint is not None and len(command) >= 4 and Path(command[3]).resolve() == checkpoint.resolve(),
                "Driver did not load the exact F5-created checkpoint")
    require((launch_dir / "stdout.log").is_file(), "Manual launch stdout log is missing")
    output = (launch_dir / "stdout.log").read_text(encoding="utf-8", errors="replace")
    require(re.search(r"^INTERACTIVE_PLAY_CLOSED=\d+\|NATIVE_CHECKPOINT_WRITTEN$", output, re.M),
            "Host did not report its owner-controlled save and close")
    save_rows = re.findall(r"^INTERACTIVE_NATIVE_SAVE=(\d+)\|(.+)$", output, re.M)
    if mode == "New":
        matching_save_rows = [(int(turn), path) for turn, path in save_rows
                              if Path(path).resolve() == checkpoint_path]
        require(matching_save_rows,
                "Host save marker does not identify the F5-created checkpoint")
        turn, marker_path = matching_save_rows[-1]
        report["launches"][-1]["f5_save"].update({"bytes": checkpoint_path.stat().st_size,
                                                   "sha256": digest(checkpoint_path), "turn": turn,
                                                   "native_save_marker_path": marker_path})
        event_rows = re.findall(r"^INTERACTIVE_WINDOW_INPUT=(\d+)\|(\d+)\|(\d+)\|([01])$", output, re.M)
        key_rows = [row for row in event_rows if row[1] == "0"]
        require(len(key_rows) == 1 and key_rows[0][3] == "1",
                "The single posted F5 did not reach and pass the Host key-input dispatch")
    require(checkpoint_path.is_file() and checkpoint_path.stat().st_size > 0,
            "Native checkpoint is missing or empty")
    report["launches"][-1].update({"launch_record": str(launch_path), "driver_result": {
        "status": driver_result["status"], "returncode": driver_result["returncode"],
        "timeout_seconds": driver_result["timeout_seconds"], "native_mode": command[1]},
        "checkpoint": {"path": str(checkpoint_path), "bytes": checkpoint_path.stat().st_size,
                       "sha256": digest(checkpoint_path)}, "status": completed["status"]})
    write_report(report)
    return completed, checkpoint_path, {"session": session_dir, "output": output}


def relocate_verification_saves(sessions: list[Path], launches: list[dict]) -> list[dict]:
    """Rename only this probe's saves after both Host processes have exited."""
    for launch_row in launches:
        require(find_owned_host(int(launch_row["driver_pid"])) is None,
                "A verification Host process remains active during save relocation")
        _, window = enumerate_owned_window(int(launch_row["host_pid"]))
        require(window is None, "A verification Host window remains active during save relocation")
    moved = []
    for session in sessions:
        session = session.resolve(strict=True)
        require(session.is_relative_to(SESSION_ROOT.resolve()), "Refusing to rename a save outside EA06 sessions")
        for source in sorted(session.glob("play-save-*-turn-*.zssave")):
            target = source.with_name("verification-" + source.name)
            require(not target.exists(), f"Verification save target already exists: {target}")
            before = source.stat()
            row = {"original_path": str(source.resolve()), "verification_path": str(target.resolve()),
                   "bytes": before.st_size, "sha256": digest(source), "file_id": int(before.st_ino)}
            source.rename(target)
            after = target.stat()
            require(after.st_size == row["bytes"] and digest(target) == row["sha256"] and
                    int(after.st_ino) == row["file_id"], "Save rename changed bytes or file identity")
            moved.append(row)
    receipt = {"status": "VERIFICATION_SAVES_RENAMED", "reason":
               "Keep harness saves out of Start-Engine's play-save-* Continue search; driver logs retain original paths.",
               "moves": moved}
    temporary = RELOCATION_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(RELOCATION_PATH)
    return moved


def write_report(report: dict) -> None:
    temporary = REPORT_PATH.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(REPORT_PATH)


def main() -> int:
    require(os.name == "nt", "This native HWND probe requires Windows")
    require(RUNTIME.is_dir() and LAUNCHER.is_file(), "EA06 runtime or Start-Engine launcher is missing")
    request_path = ROOT / "evidence" / "interactive_game" / RUN_ID / "request.json"
    request = json.loads(request_path.read_text(encoding="utf-8-sig"))
    command = request.get("command", [])
    require(request.get("run_id") == RUN_ID and request.get("cwd") == str(RUNTIME) and request.get("smoke") is False,
            "EA06 request identity or smoke=false contract differs")
    require(isinstance(command, list) and "--mode" in command and
            command[command.index("--mode") + 1] == "play" and
            all("smoke" not in str(value).lower() for value in command),
            "Prepared command is not the ordinary smoke=false play mode")
    require("--timeout" in command and command[command.index("--timeout") + 1] == "120",
            "Prepared request timeout differs from the expected 120-second preparation deadline")
    new_plan = run_plan("New")
    report = {"status": "MANUAL_NATIVE_PROBE_RUNNING", "run_id": RUN_ID,
              "scope": "machine-operated ordinary Start-Engine play/play-load save-restore-close; not human play",
              "request": {"smoke": False, "preparation_timeout_seconds": 120},
              "plan": {"runtime": new_plan["runtime"], "smoke_inputs": new_plan["smoke_inputs"],
                       "total_play_timeout_seconds": new_plan["total_play_timeout_seconds"]},
              "original_saves_before": {"count": 0, "inventory_sha256": ""}, "launches": []}
    original = inventory_saves()
    report["original_saves_before"] = {"count": len(original), "inventory_sha256": inventory_digest(original)}
    write_report(report)
    new_completed, checkpoint, new_meta = launch("New", None, report)
    load_plan = run_plan("Load", checkpoint)
    load_completed, loaded_checkpoint, load_meta = launch("Load", checkpoint, report)
    # Rename only this probe's session-local saves, after both ordinary
    # launcher processes and their owned Hosts have fully closed.
    moved = relocate_verification_saves([new_meta["session"], load_meta["session"]], report["launches"])
    before_state = new_meta["session"] / "play-final-state.txt"
    after_state = load_meta["session"] / "play-initial-state.txt"
    require(before_state.is_file() and after_state.is_file() and before_state.read_bytes() == after_state.read_bytes(),
            "Loaded SDK semantic snapshot differs from the state saved by the New session")
    checkpoint_sha = report["launches"][0]["checkpoint"]["sha256"]
    relocated_checkpoint = next((Path(row["verification_path"]) for row in moved
                                 if Path(row["original_path"]).resolve() == checkpoint.resolve()), None)
    require(relocated_checkpoint is not None and digest(relocated_checkpoint) == checkpoint_sha,
            "New checkpoint bytes or file identity changed during play-load/relocation")
    after_saves = inventory_saves()
    changed = [path for path, value in original.items() if after_saves.get(path) != value]
    require(not changed, "An original save changed or disappeared: " + ", ".join(changed[:5]))
    added = sorted(set(after_saves) - set(original))
    require(all(Path(path).is_relative_to(SESSION_ROOT.resolve()) for path in added),
            "A new save was written outside EA06's own session tree")
    report["restore"] = {"load_plan_runtime": load_plan["runtime"], "checkpoint_original_path": str(checkpoint),
                         "checkpoint_verification_path": str(relocated_checkpoint), "checkpoint_sha256": digest(relocated_checkpoint),
                         "semantic_snapshot_equal": True, "snapshot_bytes": before_state.stat().st_size,
                         "snapshot_sha256": digest(before_state), "restored_snapshot": str(after_state)}
    preserved = {path: after_saves[path] for path in original if path in after_saves}
    require(len(preserved) == len(original), "Original save inventory is incomplete after verification")
    report["original_saves_after"] = {"count": len(original), "inventory_sha256": inventory_digest(preserved),
                                      "unchanged": True, "new_ea06_session_saves": len(added)}
    report["relocation_receipt"] = str(RELOCATION_PATH)
    report["relocated_verification_saves"] = len(moved)
    report["status"] = "MANUAL_NATIVE_PROBE_PASS"
    write_report(report)
    print(json.dumps({"status": report["status"], "run_id": RUN_ID,
                      "new_mode": report["launches"][0]["driver_result"]["native_mode"],
                      "load_mode": report["launches"][1]["driver_result"]["native_mode"],
                      "checkpoint_bytes": report["launches"][0]["f5_save"]["bytes"],
                      "semantic_snapshot_equal": True, "original_saves_unchanged": True}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        if REPORT_PATH.is_file():
            try:
                failed = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
                failed["status"] = "MANUAL_NATIVE_PROBE_FAILED"
                failed["error"] = str(error)
                write_report(failed)
            except Exception:
                pass
        print(f"MANUAL_NATIVE_PROBE_FAILED: {error}", file=sys.stderr)
        sys.exit(1)
