"""Owned ordinary-process original SaveMenu save/restore integration probe.

This is posted native HWND input to one explicitly supplied frozen candidate.
It is not physical IME typing, human play, retail pixels, or full campaign proof.
No launcher, existing save, or unrelated process is modified or terminated.
"""
from __future__ import annotations

import argparse
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import threading
import time
import uuid


ROOT = Path(__file__).absolute().parents[4]
EVIDENCE = Path(__file__).absolute().parent
sys.path.insert(0, str(ROOT / "tools"))
import verify_restore_game_metadata as game_metadata
TITLE = "ZeroSis' Civilization - 전략 지도"
ARCHIVE_EXTENSIONS = {".zssave", ".civ5save", ".civ5mpsave"}
WM_CLOSE, WM_KEYDOWN, WM_CHAR = 0x10, 0x100, 0x102
WM_LBUTTONDOWN, WM_LBUTTONUP = 0x201, 0x202
VK_ESCAPE, VK_HOME, VK_END, VK_DELETE, VK_BACK = 27, 36, 35, 46, 8
TIMEOUT = 180


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def ordinary(path: Path, *, directory=False) -> Path:
    """Reject lexical reparse/alias paths before using an owned filesystem path."""
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists():
            state = part.lstat()
            require(not (getattr(state, "st_file_attributes", 0) & 0x400),
                    f"Refusing a reparse path: {part}")
    if path.exists():
        require(path.resolve(strict=True) == path, f"Refusing an alias path: {path}")
        require(path.is_dir() if directory else path.is_file(), f"Wrong path type: {path}")
    return path


def digest(path):
    path = ordinary(Path(path))
    before = path.stat()
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    after = path.stat()
    require((before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_ino, after.st_size, after.st_mtime_ns), f"File changed while hashing: {path}")
    return value.hexdigest()


def artifact(path):
    path = ordinary(Path(path))
    return {"path": str(path), "sha256": digest(path), "bytes": path.stat().st_size}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def transient_json(path):
    try:
        return read_json(path)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def write_json(path, document):
    path = ordinary(Path(path))
    # Only the current attempt's explicitly owned small report is replaced.
    temporary = path.with_name(path.name + ".tmp")
    ordinary(temporary)
    temporary.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def inventory_archives():
    result = {}
    for base in (ROOT,):
        if not base.exists():
            continue
        ordinary(base, directory=True)
        for directory, subdirs, files in os.walk(base, followlinks=False):
            # No reparse directory is traversed or silently excluded from the claim.
            for name in subdirs:
                ordinary(Path(directory) / name, directory=True)
            for name in files:
                path = Path(directory) / name
                if path.suffix.casefold() in ARCHIVE_EXTENSIONS:
                    result[str(path)] = artifact(path)
    return result


def inventory_difference(before, after):
    changed = [path for path, row in before.items() if after.get(path) != row]
    added = [after[path] for path in sorted(after.keys() - before.keys())]
    return {"before_count": len(before), "after_count": len(after),
            "preexisting_changed_or_missing": changed, "new_archives": added,
            "all_preexisting_archives_unchanged": not changed}


def verify_reference(row):
    require(type(row) is dict and type(row.get("path")) is str and
            re.fullmatch(r"[0-9a-f]{64}", row.get("sha256", "")), "Missing sealed artifact reference")
    observed = artifact(Path(row["path"]))
    require(observed["sha256"] == row["sha256"] and
            ("bytes" not in row or observed["bytes"] == row["bytes"]),
            f"Sealed artifact changed: {row['path']}")
    return observed


def option(command, flag):
    require(command.count(flag) == 1 and command.index(flag) + 1 < len(command), f"Missing/duplicate {flag}")
    return command[command.index(flag) + 1]


def replace_option(command, flag, value):
    option(command, flag)
    command[command.index(flag) + 1] = str(value)


def seal_request(request_path, expected_host_sha):
    request_path = ordinary(request_path)
    request = read_json(request_path)
    run_id = request.get("run_id", "")
    require(re.fullmatch(r"[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}", run_id), "Invalid prepared runtime ID")
    runtime = ordinary(ROOT / "Build" / "InteractiveGameRuntime" / run_id, directory=True)
    require(request_path == ROOT / "evidence" / "interactive_game" / run_id / "request.json" and
            Path(request.get("cwd", "")) == runtime and request.get("smoke") is False and
            request.get("input_profile") == "MANUAL_CONTINUOUS_GAME_LOOP" and not request.get("resume_from"),
            "Request is not an exact fresh ordinary candidate request")
    launcher_source = artifact(ROOT / "tools" / "Start-Engine.ps1")
    published = re.findall(r"'[0-9]{8}T[0-9]{6}Z_[0-9a-f]+'",
                           (ROOT / "tools" / "Start-Engine.ps1").read_text(encoding="utf-8-sig"))
    require("'" + run_id + "'" not in published, "Refusing a published/default runtime")
    command = request.get("command")
    require(type(command) is list and all(type(item) is str for item in command) and command[1:4] == ["-B", "-X", "utf8"] and
            option(command, "--mode") == "play" and "--checkpoint" not in command and
            Path(option(command, "--runtime")) == runtime and Path(option(command, "--cwd")) == runtime,
            "Prepared command is not the frozen ordinary play driver")
    controls = request["launcher_control_metadata"]
    python = verify_reference(controls["python"])
    driver = verify_reference(controls["driver"])
    require(Path(command[0]) == Path(python["path"]) and Path(command[4]) == Path(driver["path"]) and
            Path(driver["path"]).parent == Path(option(command, "--tools")) and
            Path(driver["path"]).is_relative_to(runtime / "interactive_ui_support"), "Frozen driver identity mismatch")
    sealed = [artifact(request_path), python, driver, launcher_source]
    for row in request["runtime_inputs"]:
        require(Path(row["path"]).is_relative_to(runtime), "Runtime input escaped exact candidate")
        sealed.append(verify_reference(row))
    host_rows = [row for row in sealed if Path(row["path"]) == runtime / "ZeroSisHost_x64.exe"]
    require(len(host_rows) == 1 and Path(option(command, "--host")) == Path(host_rows[0]["path"]), "Missing exact Host input")
    if expected_host_sha:
        require(host_rows[0]["sha256"] == expected_host_sha, "Parent-authorized Host SHA mismatch")
    for row in request["interactive_ui_support_inventory"]["tools"].values():
        sealed.append(verify_reference(row["frozen"]))
    support = verify_reference(request["interactive_ui_support"])
    sealed.append(support)
    manifest = artifact(Path(option(command, "--support-manifest")))
    require(manifest["sha256"] == option(command, "--support-manifest-sha256"), "Frozen support manifest changed")
    sealed.append(manifest)
    for key in ("play", "resume", "selected"):
        sealed.append(verify_reference(controls[key]))
    return request, runtime, command, host_rows[0], {row["path"]: row for row in sealed}


class PROCESSENTRY32W(ctypes.Structure):
    _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                ("th32DefaultHeapID", ctypes.c_size_t), ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]


class NativeOwnership:
    def __init__(self, driver_pid, host_reference):
        self.driver_pid, self.expected = driver_pid, host_reference
        self.host_pid = self.handle = self.hwnd = self.tid = None
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        signatures = [
            (self.kernel, "CreateToolhelp32Snapshot", [wintypes.DWORD, wintypes.DWORD], wintypes.HANDLE),
            (self.kernel, "Process32FirstW", [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)], wintypes.BOOL),
            (self.kernel, "Process32NextW", [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)], wintypes.BOOL),
            (self.kernel, "OpenProcess", [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            (self.kernel, "CloseHandle", [wintypes.HANDLE], wintypes.BOOL),
            (self.kernel, "GetExitCodeProcess", [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            (self.kernel, "QueryFullProcessImageNameW", [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                       ctypes.POINTER(wintypes.DWORD)], wintypes.BOOL),
            (self.user, "EnumWindows", [self.callback_type, wintypes.LPARAM], wintypes.BOOL),
            (self.user, "GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
            (self.user, "IsWindowVisible", [wintypes.HWND], wintypes.BOOL),
            (self.user, "GetWindowTextLengthW", [wintypes.HWND], ctypes.c_int),
            (self.user, "GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
            (self.user, "GetClientRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
            (self.user, "PostMessageW", [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM], wintypes.BOOL)]
        for library, name, args, result in signatures:
            function = getattr(library, name);function.argtypes = args;function.restype = result

    def image(self, handle):
        value = ctypes.create_unicode_buffer(32768);size = wintypes.DWORD(len(value))
        require(self.kernel.QueryFullProcessImageNameW(handle, 0, value, ctypes.byref(size)), "Cannot query own Host image")
        return ordinary(Path(value.value))

    def find_host(self):
        if self.handle:
            return self.host_pid
        snapshot = self.kernel.CreateToolhelp32Snapshot(2, 0)
        require(snapshot not in (None, 0, wintypes.HANDLE(-1).value), "Process inventory failed")
        found = []
        try:
            entry = PROCESSENTRY32W();entry.dwSize = ctypes.sizeof(entry)
            more = self.kernel.Process32FirstW(snapshot, ctypes.byref(entry))
            while more:
                if entry.th32ParentProcessID == self.driver_pid and entry.szExeFile.casefold() == "zerosishost_x64.exe":
                    handle = self.kernel.OpenProcess(0x1000 | 0x100000, False, entry.th32ProcessID)
                    require(handle, "Cannot pin the driver's direct Host child")
                    try:
                        image = self.image(handle)
                        require(image == Path(self.expected["path"]) and digest(image) == self.expected["sha256"],
                                "Direct Host child differs from exact candidate path/SHA")
                        found.append((int(entry.th32ProcessID), handle));handle = None
                    finally:
                        if handle:self.kernel.CloseHandle(handle)
                more = self.kernel.Process32NextW(snapshot, ctypes.byref(entry))
        finally:
            self.kernel.CloseHandle(snapshot)
        if len(found) > 1:
            for _, handle in found:self.kernel.CloseHandle(handle)
            raise RuntimeError("Multiple candidate Host children belong to one driver")
        if found:
            self.host_pid, self.handle = found[0]
        return self.host_pid

    def alive(self):
        code = wintypes.DWORD()
        return bool(self.handle and self.kernel.GetExitCodeProcess(self.handle, ctypes.byref(code)) and code.value == 259)

    def find_window(self):
        if not self.find_host() or not self.alive():return None
        found = []
        @self.callback_type
        def visit(hwnd, _):
            owner = wintypes.DWORD();tid = self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
            if owner.value != self.host_pid or not tid or not self.user.IsWindowVisible(hwnd):return True
            title = ctypes.create_unicode_buffer(self.user.GetWindowTextLengthW(hwnd) + 1)
            self.user.GetWindowTextW(hwnd, title, len(title));client = wintypes.RECT()
            if title.value == TITLE and self.user.GetClientRect(hwnd, ctypes.byref(client)) and client.right > 0 and client.bottom > 0:
                found.append((int(hwnd), int(tid), int(client.right), int(client.bottom)))
            return True
        require(self.user.EnumWindows(visit, 0), "Window inventory failed")
        require(len(found) <= 1, "Multiple visible windows belong to own Host")
        if not found:return None
        hwnd, tid, width, height = found[0]
        if self.hwnd is not None:
            require((hwnd, tid) == (self.hwnd, self.tid), "Own Host window/thread identity changed")
        self.hwnd, self.tid = hwnd, tid
        return {"driver_pid": self.driver_pid, "host_pid": self.host_pid, "host_path": self.expected["path"],
                "host_sha256": self.expected["sha256"], "hwnd": hwnd, "thread": tid, "client": [width, height]}

    def post(self, message, wparam=0, lparam=0):
        require(self.alive() and self.image(self.handle) == Path(self.expected["path"]), "Own Host lifetime/image changed")
        require(self.hwnd is not None and self.find_window(), "No owned visible input window")
        owner = wintypes.DWORD();tid = self.user.GetWindowThreadProcessId(self.hwnd, ctypes.byref(owner))
        require(owner.value == self.host_pid and tid == self.tid, "Refusing input outside exact Host PID/thread/HWND")
        require(self.user.PostMessageW(self.hwnd, message, wparam, lparam), "Owned PostMessageW failed")

    def release(self):
        if self.handle:self.kernel.CloseHandle(self.handle);self.handle = None


class Launch:
    def __init__(self, mode, runtime, command, host, attempt, report):
        self.mode, self.runtime, self.attempt, self.report = mode, runtime, attempt, report
        self.row = {"mode": mode, "command": command, "native_inputs": [], "timeout_seconds": 0}
        report["launches"].append(self.row)
        self.lines, self.lock, self.session = [], threading.Lock(), None
        env = dict(os.environ)
        for name in list(env):
            if name.startswith("ZEROSIS_PLAY_") or name in ("ZEROSIS_UI_WINDOW_PROFILE", "ZEROSIS_SAVE_MENU_CAPTURE"):
                env.pop(name)
        if mode == "play":env["ZEROSIS_SAVE_MENU_CAPTURE"] = "1"
        self.row["save_menu_capture_environment"] = env.get("ZEROSIS_SAVE_MENU_CAPTURE")
        self.process = subprocess.Popen(command, cwd=runtime, env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                        encoding="utf-8", errors="replace", bufsize=1,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.owner = NativeOwnership(self.process.pid, host)
        self.row["driver_pid"] = self.process.pid
        self.threads = []
        for stream, label in ((self.process.stdout, "stdout"), (self.process.stderr, "stderr")):
            def drain(stream=stream, label=label):
                with (attempt / f"{mode}.{label}.log").open("w", encoding="utf-8", newline="\n") as output:
                    for line in iter(stream.readline, ""):
                        output.write(line);output.flush()
                        if label == "stdout":
                            with self.lock:self.lines.append(line.rstrip("\r\n"))
            thread = threading.Thread(target=drain, daemon=True);thread.start();self.threads.append(thread)

    def entries(self, prefix):
        with self.lock:return [line[len(prefix):] for line in self.lines if line.startswith(prefix)]

    def wait(self, predicate, description, seconds=TIMEOUT):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            value = predicate()
            if value:return value
            require(self.process.poll() is None, f"Own driver exited before {description}")
            time.sleep(0.1)
        raise RuntimeError(f"Timed out waiting for {description}; no restart or unrelated termination was performed")

    def ready(self):
        self.row.update(self.wait(self.owner.find_window, "own candidate HWND"))
        def session_path():
            rows = self.entries("SESSION_DIRECTORY=")
            if not rows:return None
            require(len(rows) == 1, "Own Host declared multiple sessions")
            path = ordinary(Path(rows[0]), directory=True)
            require(path.parent == self.runtime / "sessions", "Own session escaped exact candidate runtime")
            return path
        self.session = self.wait(session_path, "own exact native session")
        self.row["session"] = str(self.session)
        self.wait(lambda: (transient_json(self.session / "play-current.json") or {}).get("generation"), "first committed world scene")
        self.save_report()

    def save_report(self):write_json(self.attempt / "probe_result.json", self.report)

    def post(self, message, wparam=0, lparam=0, **detail):
        self.owner.post(message, wparam, lparam)
        self.row["native_inputs"].append({"message": message, "wparam": wparam, "lparam": lparam,
            "pid": self.owner.host_pid, "thread": self.owner.tid, "hwnd": self.owner.hwnd, **detail})
        self.save_report()

    def frame(self, context, *, after=0):
        native_context = {"SaveMenu": "save-menu", "GameMenu": "game-menu"}[context]
        def latest():
            for raw in reversed(self.entries("INTERACTIVE_UI_FRAME=")):
                fields = raw.split("|")
                require(len(fields) == 8, "Unexpected native UI-frame field contract")
                sequence, generation, turn, name, hwnd, device, snapshot_text, folder_text = fields
                if name != native_context or int(generation) <= after:continue
                require(int(hwnd) == self.owner.hwnd and int(device) > 0, "Frame is not from own native GPU/window")
                snapshot_path = ordinary(Path(snapshot_text));folder = ordinary(Path(folder_text), directory=True)
                require(snapshot_path.parent == self.session and folder.parent == self.session and
                        folder.name == "play-ui-" + sequence, "Native UI artifact escaped own session")
                snapshot = transient_json(snapshot_path);record = transient_json(folder / "driver_record.json")
                world = transient_json(self.session / "play-current.json")
                if not snapshot or not record or not world or world.get("generation") != int(generation):return None
                if snapshot.get("active") is not True or snapshot.get("contextHidden") is True:continue
                require(record["snapshot_before_sha256"] == record["snapshot_after_sha256"] == digest(snapshot_path) and
                        record.get("snapshot_state_unchanged") is True and record.get("database_unchanged") is True and
                        record.get("context") == ("save-menu" if context == "SaveMenu" else "game-menu") and
                        record.get("closed") is False, "Driver's real read-only scene proof differs")
                manifest_ref = verify_reference(record["manifest"]);manifest = read_json(manifest_ref["path"])
                require(manifest.get("packet_version") == "ZSUPIX02" and
                        manifest.get("retained_input_targets") == snapshot.get("inputTargets") and
                        manifest.get("closed_context_not_drawn") is False and
                        manifest.get("retail_pixels_verified", False) is False,
                        "Native packet lost its retained original input/layout boundary")
                self.report["sealed_original_ui_sources"].update({row["path"]: verify_reference(row)
                    for row in manifest.get("original_context_sources", [])})
                info = {"sequence": int(sequence), "generation": int(generation), "turn": int(turn),
                        "context": context, "device": int(device), "snapshot": artifact(snapshot_path),
                        "manifest": manifest_ref, "driver_record": artifact(folder / "driver_record.json")}
                committed = generation + "|" + device
                require(committed in self.entries("INTERACTIVE_GPU_WORLD_COMMITTED=") and
                        committed in self.entries("INTERACTIVE_GPU_SCENE_COMMITTED="),
                        "Original UI frame lacks its matching native world/scene GPU commit")
                renderer = [row.split("|") for row in self.entries("INTERACTIVE_WORLD_FRAME=")
                            if len(row.split("|")) == 9 and row.split("|")[1] == generation]
                require(renderer and renderer[-1][5] == device and int(renderer[-1][6]) > 0,
                        "Original UI lacks a presented frame on the exact native device")
                info["native_renderer_frame"] = {"revision": int(renderer[-1][0]), "generation": int(generation),
                    "device": int(device), "present_count": int(renderer[-1][6]),
                    "occluded": renderer[-1][7] == "1", "device_kind": int(renderer[-1][8])}
                key = "saveMenu" if context == "SaveMenu" else "gameMenu"
                menu = snapshot.get(key, {})
                require(snapshot.get("timerSemaphore") == (0 if context == "SaveMenu" else 1) and
                        menu.get("timerSemaphore") == (0 if context == "SaveMenu" else 1) and
                        menu.get("owner") == world.get("activePlayer") and menu.get("turn") == world.get("turn"),
                        "Original menu lost owner/turn/parent timer boundary")
                if context == "SaveMenu":
                    require(menu.get("parentContext") == "GameMenu" and menu.get("catalogScope") ==
                            "CURRENT_ENGINE_SESSION_NATIVE_ZSSAVE_ONLY", "Wrong native catalog/parent scope")
                return {"info": info, "snapshot": snapshot, "world": world}
            return None
        return self.wait(latest, f"committed original {context} after generation {after}")

    def click(self, frame, control_id, *, key=None):
        targets = [row for row in frame["snapshot"]["inputTargets"] if row.get("id") == control_id and
                   row.get("event") == "LeftClick" and row.get("visible") is True and row.get("disabled") is False and
                   (key is None or row.get("key") == key)]
        require(len(targets) == 1, f"Original live {control_id} is not a unique enabled callback target")
        target = targets[0];bounds = target["clippedBounds"]
        current = self.owner.find_window();require(current, "Own click window disappeared")
        world = transient_json(self.session / "play-current.json")
        require(world and world.get("generation") == frame["info"]["generation"], "Refusing a stale original control target")
        width, height = current["client"];scale = min(width / 1920, height / 1080)
        x = int((width - 1920 * scale) / 2 + (bounds["x"] + bounds["width"] / 2) * scale)
        y = int((height - 1080 * scale) / 2 + (bounds["y"] + bounds["height"] / 2) * scale)
        require(0 <= x < width and 0 <= y < height and bounds["width"] > 0 and bounds["height"] > 0, "Original target is outside own client")
        point = (y & 0xffff) << 16 | (x & 0xffff)
        detail = {"control_id": control_id, "control_key": target["key"], "scene_generation": frame["info"]["generation"]}
        self.post(WM_LBUTTONDOWN, 1, point, **detail);self.post(WM_LBUTTONUP, 0, point, **detail)

    def normal_close(self):
        if self.process.poll() is not None:return
        if not self.owner.find_window():
            self.wait(self.owner.find_window, "own window for normal error cleanup", 30)
        self.post(WM_CLOSE, normal_owner_close=True)
        try:self.process.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            raise RuntimeError("Own normal WM_CLOSE did not finish; no forced/unrelated termination was performed")

    def result(self, checkpoint=None):
        for thread in self.threads:thread.join(timeout=5)
        path = self.attempt / f"{self.mode}.driver_result.json"
        document = read_json(path);command = document.get("command", [])
        require(self.process.returncode == 0 and document.get("status") == "INTERACTIVE_UI_DRIVER_PASS" and
                document.get("pid") == self.owner.host_pid and document.get("returncode") == 0 and
                document.get("timeout_seconds") == 0 and len(command) >= 3 and
                command[0] == self.owner.expected["path"] and command[1] == "--" + self.mode and
                Path(document.get("runtime", "")) == self.runtime,
                "Own ordinary Host/driver did not close at rc0 with timeout0")
        if checkpoint is not None:require(len(command) == 4 and Path(command[3]) == checkpoint, "Load process used a different native save")
        require(len(self.entries("INTERACTIVE_PLAY_CLOSED=")) == 1 and
                self.entries("INTERACTIVE_PLAY_CLOSED=")[0].endswith("|NATIVE_CHECKPOINT_WRITTEN") and
                any(line.startswith("INTERACTIVE_PLAY_SHUTDOWN_PASS ") for line in self.lines), "Missing native normal-close/GameCore-unload proof")
        self.row.update({"driver_result": artifact(path), "returncode": self.process.returncode,
                         "stdout": artifact(self.attempt / f"{self.mode}.stdout.log"),
                         "stderr": artifact(self.attempt / f"{self.mode}.stderr.log"),
                         "initial_sdk_state": artifact(self.session / "play-initial-state.txt"),
                         "final_sdk_state": artifact(self.session / "play-final-state.txt")})
        return document


def nodes(snapshot):
    result = []
    def visit(node, ancestors=()):
        result.append((node, ancestors))
        for child in node.get("children", []):visit(child, (*ancestors, node.get("id", "")))
    visit(snapshot["tree"])
    return result


def namebox(frame):
    found = [node for node, _ in nodes(frame["snapshot"]) if node.get("id") == "NameBox"]
    require(len(found) == 1 and found[0].get("kind") == "EditBox" and found[0].get("maxLength") == 32,
            "Original MaxLength32 NameBox missing")
    return found[0]


def record_frame(launch, label, frame):
    launch.row.setdefault("original_menu_frames", []).append({"phase": label, **frame["info"],
        "timer": frame["snapshot"]["timerSemaphore"], "menu": frame["snapshot"].get("saveMenu", frame["snapshot"].get("gameMenu"))})
    launch.save_report()


def edit_key(launch, frame, key, expected_text, expected_caret):
    launch.post(WM_KEYDOWN, key, 1, editing_key=key, scene_generation=frame["info"]["generation"])
    updated = launch.frame("SaveMenu", after=frame["info"]["generation"])
    edit = namebox(updated)
    require(edit.get("focused") is True and edit.get("text") == expected_text and edit.get("caretCodepoint") == expected_caret,
            "Native editing key did not preserve exact original NameBox text/caret")
    record_frame(launch, f"edit-key-{key}", updated)
    return updated


def preview(launch, frame):
    snapshot = frame["snapshot"]
    count = snapshot["saveMenu"].get("catalogCount")
    rows = [(node, ancestor) for node, ancestor in nodes(snapshot) if node.get("id") == "Button" and
            "LoadFileButtonStack" in ancestor]
    require(type(count) is int and count == len(rows) and count > 0, "Actual initial-autosave catalog row is missing")
    archives = {path.stem: artifact(path) for path in launch.session.glob("*.zssave")}
    require(len(archives) == count, "Original native catalog count differs from current session archives")
    selected, _ = rows[0]
    def texts(node):
        values = [node.get("text", "")]
        for child in node.get("children", []):values.extend(texts(child))
        return [item for item in values if type(item) is str and item]
    labels = texts(selected)
    matching = [stem for stem in archives if stem in labels]
    require(len(matching) == 1, "Original list row does not identify exactly one actual archive")
    launch.click(frame, "Button", key=selected["key"])
    updated = launch.frame("SaveMenu", after=frame["info"]["generation"])
    require(namebox(updated).get("text") == matching[0] and updated["snapshot"]["saveMenu"].get("nameAvailable") is False,
            "Selecting an existing save did not gate overwrite by original name")
    original_lua = Path(snapshot["saveMenu"]["originalLua"]["path"])
    lua = original_lua.read_text(encoding="utf-8-sig")
    # Derive actual header-preview controls from unchanged installed Lua.
    marker = re.search(r"function\s+SetSaveInfoToCiv\s*\(", lua)
    require(marker, "Original SaveMenu lacks its actual SetSaveInfoToCiv callback")
    remainder = lua[marker.end():]
    next_function = re.search(r"\nfunction\s+", remainder)
    body = remainder[:next_function.start()] if next_function else remainder
    detail_ids = sorted(set(re.findall(r"Controls\.([A-Za-z_][A-Za-z0-9_]*):(?:SetText|LocalizeAndSetText)\(", body)))
    details = {node["id"]: node.get("text", "") for node, _ in nodes(updated["snapshot"]) if node.get("id") in detail_ids}
    require(len(detail_ids) >= 4 and len(details) == len(detail_ids) and all(type(value) is str and value for value in details.values()),
            "Actual saved-header preview did not populate original detail labels")
    actual_archive = Path(archives[matching[0]]["path"])
    actual_modification = datetime.fromtimestamp(actual_archive.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    require(details.get("TimeSaved") == actual_modification,
            "Original saved-header modification text differs from its actual archive timestamp")
    launch.row["header_preview"] = {"catalog_count": count, "selected_archive": archives[matching[0]],
        "original_list_text": labels, "original_header_detail_text": details,
        "actual_archive_local_modification_time": actual_modification,
        "proof": "Actual stock selected-row preview plus compiled SDK header capture; no synthetic header metadata",
        "all_serialized_fields_claimed": False}
    record_frame(launch, "existing-real-header-preview", updated)
    return updated


def probe_save(launch, save_name):
    world = read_json(launch.session / "play-current.json")
    launch.post(WM_KEYDOWN, VK_ESCAPE, 1, original_game_menu=True, scene_generation=world["generation"])
    parent = launch.frame("GameMenu", after=world["generation"]);record_frame(launch, "parent-opened", parent)
    launch.click(parent, "SaveGameButton")
    child = launch.frame("SaveMenu", after=parent["info"]["generation"]);record_frame(launch, "child-opened", child)
    child = preview(launch, child)
    launch.click(child, "BackButton")
    parent = launch.frame("GameMenu", after=child["info"]["generation"]);record_frame(launch, "cancel-returned-parent", parent)
    require(len(launch.entries("INTERACTIVE_SAVE_MENU_PARENT_RETURNED=")) == 1, "Cancel did not return the retained parent")
    launch.click(parent, "SaveGameButton")
    child = launch.frame("SaveMenu", after=parent["info"]["generation"]);record_frame(launch, "child-reopened", child)
    launch.click(child, "NameBox")
    child = launch.frame("SaveMenu", after=child["info"]["generation"])
    require(namebox(child).get("focused") is True and child["snapshot"]["saveMenu"].get("textInputEnabled") is True,
            "Original NameBox did not receive live native focus")
    text = namebox(child)["text"]
    child = edit_key(launch, child, VK_HOME, text, 0)
    child = edit_key(launch, child, VK_DELETE, text[1:], 0)
    text = text[1:]
    child = edit_key(launch, child, VK_END, text, len(text))
    while text:
        text = text[:-1];child = edit_key(launch, child, VK_BACK, text, len(text))
    require(namebox(child)["text"] == "" and len(save_name) <= 32 and all(ord(char) <= 0xffff for char in save_name),
            "Unicode test name/empty original edit boundary changed")
    for char in save_name:
        launch.post(WM_CHAR, ord(char), 1, unicode_scalar=ord(char), input_claim="POSTED_WM_CHAR_NOT_PHYSICAL_IME",
                    scene_generation=child["info"]["generation"])
        child = launch.frame("SaveMenu", after=child["info"]["generation"]);text += char
        require(namebox(child)["text"] == text and namebox(child)["caretCodepoint"] == len(text),
                "Native Unicode scalar did not append exactly once to original NameBox")
        record_frame(launch, "append-unicode-scalar", child)
    require(child["snapshot"]["saveMenu"]["nameAvailable"] is True, "Unique Korean name is unavailable")
    before = {str(path): artifact(path) for path in launch.session.glob("*.zssave")}
    expected = launch.session / (save_name + ".zssave")
    require(not os.path.lexists(expected), "Unique named archive unexpectedly exists; refusing overwrite")
    record_frame(launch, "ready-to-save", child);launch.click(child, "SaveButton")
    def written():
        rows = launch.entries("INTERACTIVE_SAVE_MENU_NAMED_SAVE=")
        if not rows:return None
        require(len(rows) == 1, "Original save callback created more than one named archive")
        fields = rows[0].split("|")
        require(len(fields) == 3 and Path(fields[2]) == expected and int(fields[0]) == child["world"]["activePlayer"] and
                int(fields[1]) == child["world"]["turn"], "Named native archive lost exact path/owner/turn")
        return artifact(expected) if expected.is_file() else None
    created = launch.wait(written, "one closed-readable create-only named native save")
    after = {str(path): artifact(path) for path in launch.session.glob("*.zssave")}
    require(set(after) - set(before) == {str(expected)} and all(after.get(path) == row for path, row in before.items()),
            "Named save created extra archive or overwrote an existing current-session save")
    launch.row["named_save"] = created;launch.save_report()
    return expected


def verify_timeline(launch):
    queued = [list(map(int, row.split("|"))) for row in launch.entries("INTERACTIVE_SAVE_MENU_REQUEST_QUEUED=")]
    require(len(queued) == 3 and [row[0] for row in queued] == [1, 0, 1] and all(row[1:] == queued[0][1:] for row in queued),
            "Original Cancel / Save+Close command order or owner/turn differs")
    shown = [row.split("|") for row in launch.entries("INTERACTIVE_SAVE_MENU_SHOWN=")]
    parent = [row.split("|") for row in launch.entries("INTERACTIVE_GAME_MENU_SHOWN=")]
    require(len(shown) == 2 and all(row[-2:] == ["0", "STATE_UNCHANGED"] for row in shown) and
            parent and all(row[-2:] == ["1", "STATE_UNCHANGED"] for row in parent), "Parent timer1/child timer0 native proof differs")
    inputs = [row.split("|") for row in launch.entries("INTERACTIVE_SAVE_MENU_INPUT=")]
    require(inputs and all(len(row) == 9 and row[2] == "1" and row[6] == "0" and row[8] == "STATE_UNCHANGED" for row in inputs),
            "Original save input crossed SDK readonly/timer boundary or was not consumed")
    require(launch.entries("INTERACTIVE_SAVE_MENU_PARENT_RETURNED=") == ["STATE_UNCHANGED", "STATE_UNCHANGED"],
            "Retained GameMenu return count or SDK state differs")
    captures = launch.entries("INTERACTIVE_SAVE_MENU_GPU_CAPTURE=")
    require(len(captures) == 1, "One actual candidate SaveMenu GPU capture was not produced")
    generation, path = captures[0].split("|");image = ordinary(Path(path))
    require(image == launch.session / "save-menu-native-gpu.png", "GPU capture escaped own session")
    with image.open("rb") as stream:header = stream.read(24)
    require(header[:8] == b"\x89PNG\r\n\x1a\n" and header[12:16] == b"IHDR", "Native GPU capture is not a PNG")
    width, height = struct.unpack(">II", header[16:24]);require(width > 0 and height > 0, "Empty GPU capture")
    first_child = next(row for row in launch.row["original_menu_frames"] if row["phase"] == "child-opened")
    require(int(generation) == first_child["generation"], "GPU capture is not the actual first SaveMenu native frame")
    launch.row["native_save_menu_timeline"] = {"queued_kinds": [row[0] for row in queued],
        "parent_timer": 1, "child_timer": 0, "read_only_input_count": len(inputs),
        "sdk_state_unchanged_for_each_input": True, "command_order": ["Cancel:Close", "Save:Save", "Save:Close"],
        "actual_gpu_frame": {**artifact(image), "generation": int(generation), "width": width, "height": height}}


def compare_sdk_state(first, second, *, runtime: Path, language: str):
    left = first.session / "play-final-state.txt";right = second.session / "play-initial-state.txt"
    a, b = left.read_bytes(), right.read_bytes()
    require(a and a == b, "Separate-process restored native SDK snapshot differs from first normal-close state")
    counts = {key: 0 for key in ("G", "M", "P", "U", "C", "T")}
    for line in a.decode("utf-8").splitlines():
        key = line.split("|", 1)[0];require(key in counts, "Unknown native SdkStateSnapshot section tag")
        counts[key] += 1
    require(counts["G"] == 1 and counts["M"] > 0 and counts["P"] == 64 and counts["U"] > 0 and counts["T"] > 0,
            "Native semantic sample is missing actual SDK sections")
    require(second.entries("INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=") == ["true"], "Restored SDK changed during its idle boundary")
    equality = second.entries("INTERACTIVE_RESTORE_SECTIONS_EQUAL=")
    require(len(equality) == 1, "Native restore section identity check missing")
    equal, total = map(int, equality[0].split("|"))
    require((equal, total) == (game_metadata.SECTION_COUNT - 1, game_metadata.SECTION_COUNT) and
            second.entries("INTERACTIVE_RESTORE_SECTION_CHANGED=") == ["3|0"],
            "Native restore must preserve all 132 non-Game sections and change only Game (3,0)")
    require(first.entries("NEW_GAME_CONFIGURATION_VERIFIED") == [""],
            "Named-save source lacks exactly one verified new-game configuration marker")
    require(first.entries("LANGUAGE=") == [language] and second.entries("LANGUAGE=") == [language],
            "Source/restored Host localization language differs from its prepared request")
    checkpoint = verify_reference(first.row["named_save"])
    require(Path(checkpoint["path"]).parent == first.session, "Named save escaped its exact source session")
    restored = artifact(second.session / "play-restored-checkpoint.zssave")
    rules = artifact(first.session / "rules.db")
    localization = artifact(runtime / "localization.db")
    byte_result = game_metadata.verify_game_restore(
        checkpoint["path"], restored["path"], rules_db_path=rules["path"],
        localization_db_path=localization["path"], language=language,
        configuration_verified=True, fixed_fixture=False,
    )
    require(byte_result.get("status") == "CURRENT_ARCHIVE_GAME_RESTORE_METADATA_PASS" and
            byte_result.get("changed_sections") == [[3, 0]] and
            byte_result.get("input_pair_game_byte_preservation_verified") is True,
            "Independent native Game-byte reload metadata check did not pass")
    for reference in (checkpoint, restored, rules, localization): verify_reference(reference)
    return {"first_final": artifact(left), "second_initial": artifact(right), "exact_bytes_equal": True,
            "sdk_snapshot_section_counts": counts, "native_restore_sections_equal": equal, "native_restore_sections_total": total,
            "native_restore_changed_sections": second.entries("INTERACTIVE_RESTORE_SECTION_CHANGED="),
            "independent_reload_byte_check": byte_result, "named_checkpoint": checkpoint,
            "restored_checkpoint": restored, "source_rules_db": rules, "localization_db": localization,
            "scope": "Actual SDK samples and bounded input-pair serialized reload check; not retail-save compatibility or full campaign"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--expected-host-sha256", required=True)
    args = parser.parse_args()
    require(os.name == "nt", "This bounded native probe requires Windows")
    ordinary(ROOT, directory=True);ordinary(EVIDENCE, directory=True)
    attempt = EVIDENCE / "attempts" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:8])
    ordinary(attempt.parent, directory=True);attempt.mkdir(parents=True, exist_ok=False)
    report = {"schema": "zerosis.original_save_menu.native_probe.v1", "status": "RUNNING", "request": str(args.request),
              "probe_source": artifact(Path(__file__)), "launches": [], "sealed_original_ui_sources": {},
              "published_launcher_changed": False, "retail_full_ui_verified": False, "full_campaign_verified": False,
              "physical_ime_verified": False, "user_originals_modified": False, "unrelated_processes_terminated": False,
              "serialized_text_input_only": True, "rapid_typing_verified": False, "default_publication_authorized": False,
              "archive_preservation_scope": "ENGINE_PROJECT_ONLY; retail MODS and user save directories are not inspected",
              "proof_scope": "Focused ordinary native SaveMenu plus bounded input-pair reload bytes; no full S03 rapid-input claim"}
    baseline = None;launches = [];error = None;sealed = {}
    try:
        request, runtime, frozen_command, host, sealed = seal_request(args.request, args.expected_host_sha256)
        metadata_source = artifact(Path(game_metadata.__file__))
        require(Path(metadata_source['path']) == ROOT / 'tools' / 'verify_restore_game_metadata.py',
                "Independent Game metadata verifier was imported from a different location")
        report['reload_metadata_verifier'] = metadata_source
        sealed[metadata_source['path']] = metadata_source
        require(request.get('language') == option(frozen_command, '--language'),
                "Prepared request and driver localization languages differ")
        report.update({"run_id": request["run_id"], "runtime": str(runtime), "expected_host": host,
                       "prepared_timeout_seconds": request["timeout"], "probe_override_timeout_seconds": 0,
                       "default_continue_candidate_scope": "Excluded from explicit current published runtime ID lists"})
        baseline = inventory_archives();write_json(attempt / "archives_before.json", baseline)
        report["archives_before"] = artifact(attempt / "archives_before.json")
        for mode in ("play", "play-load"):
            command = list(frozen_command)
            replace_option(command, "--mode", mode);replace_option(command, "--timeout", 0)
            replace_option(command, "--report", attempt / f"{mode}.driver_result.json")
            if mode == "play-load":command.extend(["--checkpoint", str(checkpoint)])
            launch = Launch(mode, runtime, command, host, attempt, report);launches.append(launch)
            try:
                launch.ready()
                if mode == "play":
                    name = "저장검증" + datetime.now(timezone.utc).strftime("%H%M%S") + "_" + uuid.uuid4().hex[:6]
                    report["unique_korean_name"] = name
                    checkpoint = probe_save(launch, name)
                else:
                    require(launch.entries("INTERACTIVE_RESTORE_CHECKPOINT=") == [str(checkpoint)], "Second process did not load exact named native archive")
                launch.normal_close();launch.result(checkpoint if mode == "play-load" else None)
                if mode == "play":verify_timeline(launch)
                else:require(not launch.entries("INTERACTIVE_SAVE_MENU_GPU_CAPTURE="), "Second launch unexpectedly captured SaveMenu")
            finally:
                if launch.process.poll() is None:
                    try:launch.normal_close()
                    except Exception as cleanup_error:launch.row["normal_close_cleanup_error"] = str(cleanup_error)
                launch.row["own_driver_still_running"] = launch.process.poll() is None
                launch.save_report()
        require(launches[0].owner.host_pid != launches[1].owner.host_pid and launches[0].process.pid != launches[1].process.pid,
                "Restore did not use a distinct own driver/Host process")
        report["restore_sdk_state"] = compare_sdk_state(launches[0], launches[1], runtime=runtime, language=request['language'])
        report["status"] = "ORIGINAL_SAVE_MENU_NATIVE_PROBE_PASS"
    except Exception as exc:
        error = str(exc);report["status"] = "ORIGINAL_SAVE_MENU_NATIVE_PROBE_FAILED";report["error"] = error
    finally:
        if baseline is not None:
            try:
                after = inventory_archives();write_json(attempt / "archives_after.json", after)
                report["archives_after"] = artifact(attempt / "archives_after.json")
                report["archive_preservation"] = inventory_difference(baseline, after)
                require(not report["archive_preservation"]["preexisting_changed_or_missing"], "A pre-existing archive changed or disappeared")
                owned_sessions = [Path(row["session"]) for row in report["launches"] if row.get("session")]
                require(all(any(Path(row["path"]).is_relative_to(session) for session in owned_sessions)
                            for row in report["archive_preservation"]["new_archives"]), "New archive appeared outside this probe's own sessions")
                report["new_owned_verification_archives_preserved"] = True
            except Exception as preservation_error:
                report["status"] = "ORIGINAL_SAVE_MENU_NATIVE_PROBE_FAILED";report["preservation_error"] = str(preservation_error)
        try:
            for row in [*sealed.values(), *report["sealed_original_ui_sources"].values()]:verify_reference(row)
            report["sealed_inputs_and_published_launcher_unchanged"] = True
        except Exception as integrity_error:
            report["status"] = "ORIGINAL_SAVE_MENU_NATIVE_PROBE_FAILED";report["integrity_error"] = str(integrity_error)
        for launch in launches:launch.owner.release()
        write_json(attempt / "probe_result.json", report)
    print(json.dumps({"status": report["status"], "result": str(attempt / "probe_result.json"), "error": error}, ensure_ascii=False))
    return 0 if report["status"] == "ORIGINAL_SAVE_MENU_NATIVE_PROBE_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
