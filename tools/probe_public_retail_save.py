"""Probe one pinned public fixture in RAM with the portable retail parsers.

This module is import-safe. Downloads, compilation and child processes occur
only through main(); no raw, inflated or embedded-database payload is saved.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zlib


MAX_RAW = 8 * 1024 * 1024
MAX_INFLATED = 64 * 1024 * 1024
MAX_JSON = 256 * 1024
FLAGS_FALSE = ("gamecore_loaded", "window_created", "game_accessed", "user_saves_accessed",
               "complete_player_validated", "complete_save_validated",
               "ruleset_compatibility_verified", "restore_approved")
QUOTED_INCLUDE = re.compile(r'^\s*#\s*include\s*"([^"\r\n]+)"', re.MULTILINE)


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def key(path) -> str:
    return os.path.normcase(os.path.abspath(os.fsdecode(path)))


def within(path, root) -> bool:
    return key(path) == key(root) or key(path).startswith(key(root) + os.sep)


def forbidden(path) -> bool:
    parts = {part.casefold() for part in Path(os.fsdecode(path)).parts}
    return bool(parts & {"my games", "mods", "saves", ".codex", "gamecore"}) or \
        {"steamapps", "common"}.issubset(parts)


def ordinary(path, *, file: bool = False) -> Path:
    path = Path(os.path.abspath(os.fsdecode(path)))
    require(not forbidden(path), "Original-game or internal path is forbidden")
    for part in (path, *path.parents):
        try:
            info = part.lstat()
        except FileNotFoundError:
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Reparse path is forbidden: " + str(part))
    if file:
        require(stat.S_ISREG(path.lstat().st_mode), "Expected an ordinary file: " + str(path))
    return path


def read_bytes(path, maximum: int) -> bytes:
    path = ordinary(path, file=True)
    before = path.lstat()
    require(0 <= before.st_size <= maximum, "File exceeds its read budget: " + path.name)
    with path.open("rb") as stream:
        data = stream.read(maximum + 1)
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and len(data) == before.st_size,
            "Input changed while reading: " + path.name)
    return data


def artifact(path, maximum: int = 64 * 1024 * 1024) -> dict:
    path = ordinary(path, file=True)
    data = read_bytes(path, maximum)
    info = path.lstat()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "file_identity": [info.st_dev, info.st_ino], "mtime_ns": info.st_mtime_ns}


def unchanged(rows: list[dict]) -> None:
    for row in rows:
        require(artifact(row["path"]) == row, "Pinned input or output changed: " + row["path"])


def read_json(path) -> dict:
    value = json.loads(read_bytes(path, MAX_JSON).decode("utf-8-sig"))
    require(isinstance(value, dict), "Expected a JSON object: " + Path(path).name)
    return value


def write_json(path: Path, value: dict) -> None:
    ordinary(path)
    text = json.dumps(value, ensure_ascii=True, indent=2) + "\n"
    require(len(text.encode("utf-8")) <= MAX_JSON, "Refusing an oversized evidence report")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def write_text(path: Path, text: str, maximum: int) -> None:
    ordinary(path)
    require(len(text.encode("utf-8")) <= maximum, "Refusing an oversized text log")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(text)


def identity(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:20]


def host_headers(source: Path, project: Path) -> list[Path]:
    host = ordinary(project / "Source/Host")
    pending, seen, headers = [source], set(), {}
    while pending:
        current = pending.pop()
        if key(current) in seen:
            continue
        seen.add(key(current))
        require(len(seen) <= 128, "Portable include closure exceeded its file bound")
        text = read_bytes(current, 2 * 1024 * 1024).decode("utf-8-sig")
        for name in QUOTED_INCLUDE.findall(text):
            require("\\" not in name and not Path(name).is_absolute() and
                    all(part not in ("", ".", "..") for part in name.split("/")),
                    "Quoted include escapes the portable header closure")
            candidate = current.parent / name
            if not candidate.exists():
                candidate = host / name
            candidate = ordinary(candidate, file=True)
            require(within(candidate, host) and candidate.suffix.casefold() == ".h",
                    "Project includes must be portable Host headers")
            headers[key(candidate)] = candidate
            pending.append(candidate)
    require(headers, "Probe has no portable header dependencies")
    return [headers[name] for name in sorted(headers)]


def select_fixture(manifest: dict, fixture_id: str) -> dict:
    require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", fixture_id) is not None,
            "Invalid fixture identifier")
    candidates = manifest.get("candidates")
    require(isinstance(candidates, list) and 0 < len(candidates) <= 128, "Invalid public candidate manifest")
    matches = [row for row in candidates if isinstance(row, dict) and row.get("id") == fixture_id]
    require(len(matches) == 1, "Fixture identifier is missing or duplicated")
    row = matches[0]
    for name in ("id", "repo", "commit", "path", "git_blob_sha1", "raw_url"):
        require(isinstance(row.get(name), str), "Candidate field is missing: " + name)
    require(re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", row["repo"]) is not None and
            re.fullmatch(r"[0-9a-f]{40}", row["commit"]) is not None and
            re.fullmatch(r"[0-9a-f]{40}", row["git_blob_sha1"]) is not None, "Candidate Git identity is invalid")
    size = row.get("bytes")
    require(type(size) is int and 0 < size <= MAX_RAW, "Candidate raw byte count exceeds 8 MiB")
    parts = row["path"].split("/")
    require(all(part not in ("", ".", "..") for part in parts) and
            "\\" not in row["path"] and ":" not in row["path"], "Candidate Git path is invalid")
    expected = "https://raw.githubusercontent.com/" + row["repo"] + "/" + row["commit"] + "/" + quote(row["path"], safe="/")
    parsed = urlsplit(row["raw_url"])
    require(row["raw_url"] == expected and parsed.scheme == "https" and
            parsed.netloc == "raw.githubusercontent.com" and not parsed.query and not parsed.fragment,
            "Candidate raw URL does not match its exact pinned Git path")
    return {name: row[name] for name in ("id", "repo", "commit", "path", "bytes", "git_blob_sha1", "raw_url")}


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        raise RuntimeError("Public fixture redirects are forbidden")


def fetch_fixture(candidate: dict) -> tuple[bytes, dict]:
    request = Request(candidate["raw_url"], headers={"User-Agent": "ZeroSis-Public-Retail-RAM-Probe",
                                                    "Accept-Encoding": "identity"})
    with build_opener(NoRedirect()).open(request, timeout=30) as response:
        require(response.status == 200 and response.geturl() == candidate["raw_url"],
                "Public fixture response identity differs")
        length = response.headers.get("Content-Length")
        require(length is None or int(length) == candidate["bytes"], "Public fixture content length differs")
        data = response.read(candidate["bytes"] + 1)
    require(len(data) == candidate["bytes"] <= MAX_RAW, "Public fixture size differs")
    git_sha = hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()
    require(git_sha == candidate["git_blob_sha1"], "Public fixture Git blob SHA-1 differs")
    return data, {"bytes": len(data), "git_blob_sha1": git_sha, "sha256": hashlib.sha256(data).hexdigest(),
                  "downloaded_before_offline_guard": True, "retained_on_disk": False}


class OfflineGuard:
    def __init__(self, *, commands: list[tuple[str, ...]], directory: Path,
                 readable: list[Path], writable: list[Path], directories: list[Path]):
        self.commands = {command: 1 for command in commands}
        self.directory = key(directory)
        self.readable = {key(path) for path in (*readable, *writable)}
        self.writable = {key(path) for path in writable}
        self.directories = {key(path) for path in directories}
        self.calls: list[list[str]] = []
        self.denied: list[str] = []
        self.deletions: set[str] = set()
        self.command_processor = key(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32/cmd.exe")

    def fail(self, reason: str) -> None:
        self.denied.append(reason)
        raise RuntimeError(reason)

    def target(self, path) -> Path:
        try:
            return ordinary(path)
        except (OSError, RuntimeError):
            self.fail("Forbidden or nonordinary path attempted under the offline guard")
        raise RuntimeError("Unreachable guard path")

    def audit(self, event: str, args) -> None:
        if event == "subprocess.Popen":
            raw = args[1]
            command = next((row for row in self.commands if subprocess.list2cmdline(row) == raw), None) \
                if isinstance(raw, str) else tuple(str(part) for part in raw)
            if command not in self.commands or self.commands[command] != 1:
                self.fail("Unapproved or repeated probe child command")
            executable = args[0]
            if executable is not None and key(executable) != key(command[0]) and not \
                    (command[0].casefold() == "cmd.exe" and key(executable) == self.command_processor):
                self.fail("Probe child executable override differs")
            if args[2] is None or key(args[2]) != self.directory:
                self.fail("Probe child working directory differs")
            self.commands[command] = 0
            self.calls.append(list(command))
        if event in ("open", "os.listdir", "os.scandir", "os.chdir") and args and \
                isinstance(args[0], (str, bytes, os.PathLike)):
            target = self.target(args[0])
            if forbidden(target):
                self.fail("Original-game or internal-state access attempted")
            if event == "open":
                writing = isinstance(args[1], str) and any(letter in args[1] for letter in "wax+") or \
                    isinstance(args[2], int) and bool(args[2] & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
                if key(target) not in (self.writable if writing else self.readable):
                    self.fail("Probe file access escaped the exact allowlist")
                if writing and target.exists():
                    self.fail("Probe attempted to overwrite an existing output")
            elif key(target) not in self.directories:
                self.fail("Probe directory access escaped the exact allowlist")
        if event == "os.mkdir":
            if key(self.target(args[0])) not in self.directories:
                self.fail("Probe directory creation escaped its allowlist")
        if event == "os.remove":
            target = key(self.target(args[0]))
            if target not in self.deletions:
                self.fail("Probe deletion was not identity-authorized")
            self.deletions.remove(target)
        if event in ("os.rmdir", "os.rename", "os.chmod", "os.link", "os.symlink"):
            self.fail("Probe attempted an unapproved filesystem mutation")
        if event.startswith(("ctypes.dlopen", "socket.", "urllib.", "http.client.")) or \
                event in ("os.system", "os.startfile", "os.startfile/2"):
            self.fail("Network, dynamic loading and interactive launch are forbidden after the guard")


def dependency_check(path: Path, source: Path, headers: list[Path], project: Path) -> dict:
    data = read_json(path).get("Data")
    require(isinstance(data, dict) and key(data.get("Source", "")) == key(source) and
            isinstance(data.get("Includes"), list) and all(isinstance(item, str) for item in data["Includes"]),
            "Compiler source-dependency report is invalid")
    includes = data["Includes"]
    require({key(item) for item in includes if within(item, project)} == {key(path) for path in headers},
            "Actual project includes differ from the pinned portable header closure")
    require(not any(forbidden(item) or "sdk_bnw_" in key(item) for item in includes),
            "A game SDK or forbidden path appeared in compiler dependencies")
    return {"project_include_count": len(headers), "actual_project_include_pinset_matches": True,
            "game_sdk_included": False}


def retire(path: Path, root: Path, guard: OfflineGuard) -> dict:
    ordinary(path, file=True)
    require(within(path, root), "Intermediate escaped its owned build root")
    before = path.lstat()
    require(before.st_nlink == 1, "Intermediate is not a one-use file")
    row = artifact(path)
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and artifact(path) == row,
            "Intermediate changed before identity-checked deletion")
    guard.deletions.add(key(path))
    path.unlink()
    require(not path.exists(), "Intermediate deletion did not finish")
    return row


def native_environment(root: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment["TMP"] = environment["TEMP"] = str(root)
    environment["VSLANG"] = "1033"
    return environment


def response_text(source: Path, host: Path, root: Path) -> str:
    flags = ["/nologo", "/O2", "/std:c++17", "/EHsc", "/W4", "/WX", "/MT", "/utf-8",
             f'/I"{host}"', f'"{source}"', f'/Fo"{root / "retail_public_probe.obj"}"',
             f'/Fe"{root / "RetailPublicProbe.exe"}"', f'/sourceDependencies "{root / "dependencies.json"}"']
    return "\n".join(flags) + "\n"


def ensure_build(*, project: Path, root: Path, evidence: Path, source: Path, headers: list[Path],
                 inputs: list[dict], compiler: dict, compiler_path: Path, vs: Path,
                 command: tuple[str, ...], environment_for, pe_imports, guard: OfflineGuard,
                 fingerprint: str) -> tuple[dict, dict[str, str]]:
    report_path = evidence / "build_result.json"
    exe, response, dependencies = root / "RetailPublicProbe.exe", root / "compile.rsp", root / "dependencies.json"
    expected_response = response_text(source, project / "Source/Host", root)
    if report_path.exists():
        prior = read_json(report_path)
        require(prior.get("status") == "PASS_HEADLESS_PUBLIC_RETAIL_PROBE_BUILD" and
                prior.get("fingerprint") == fingerprint and prior.get("inputs") == inputs and prior.get("compiler") == compiler and
                prior.get("forbidden_access_attempts") == [] and all(prior.get(name) is False for name in FLAGS_FALSE),
                "Existing probe build report differs")
        artifacts = prior.get("artifacts")
        require(isinstance(artifacts, dict) and set(artifacts) == {"executable", "response", "dependencies", "compile_log"},
                "Existing build artifact manifest differs")
        expected_paths = {"executable": exe, "response": response, "dependencies": dependencies,
                          "compile_log": evidence / "compile.log"}
        require(all(key(artifacts[name]["path"]) == key(path) for name, path in expected_paths.items()),
                "Existing build artifact paths escaped the fingerprint")
        unchanged(list(artifacts.values()))
        require(read_bytes(response, MAX_JSON).decode("utf-8") == expected_response, "Cached compiler response differs")
        dependency_check(dependencies, source, headers, project)
        require(pe_imports(exe) == ["kernel32.dll"] == prior.get("imports"), "Cached executable imports differ")
        require({child.name for child in root.iterdir()} == {"RetailPublicProbe.exe", "compile.rsp", "dependencies.json"},
                "Cached build contains unreviewed or unretired files")
        require({child.name for child in evidence.iterdir()} == {"build_started.json", "compile.log", "build_result.json"},
                "Cached build evidence contains unreviewed files")
        return prior, native_environment(root)
    require(not root.exists() and not evidence.exists(), "Inspect partial probe build before retrying")
    root.mkdir(); evidence.mkdir()
    write_json(evidence / "build_started.json", {"schema": "zerosis.public_retail_probe.build_started.v1",
        "fingerprint": fingerprint, "inputs": inputs, "compiler": compiler, "build_root": str(root)})
    try:
        environment, selected = environment_for(vs, "x64", root)
        require(key(selected) == key(compiler_path) and artifact(compiler_path) == compiler, "Reviewed compiler selection changed")
        environment["TMP"] = environment["TEMP"] = str(root); environment["VSLANG"] = "1033"
        write_text(response, expected_response, MAX_JSON)
        compiled = subprocess.run(list(command), cwd=root, env=environment, capture_output=True, timeout=120,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        output = (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace")
        write_text(evidence / "compile.log", output, 512 * 1024)
        require(compiled.returncode == 0 and not re.search(r"\bwarning\s+[A-Z]+\d+", output, re.IGNORECASE),
                "Probe compilation failed; inspect the bounded compile log")
        deps = dependency_check(dependencies, source, headers, project)
        imports = pe_imports(exe)
        require(imports == ["kernel32.dll"], "Probe executable imports exceed the headless scope")
        artifacts = {"executable": artifact(exe), "response": artifact(response), "dependencies": artifact(dependencies),
                     "compile_log": artifact(evidence / "compile.log")}
        unchanged(inputs + [compiler]); require(not guard.denied, "Offline guard rejected a build operation")
        retired = [retire(root / name, root, guard) for name in ("retail_public_probe.obj", "read_build_environment.cmd")]
        report = {"schema": "zerosis.public_retail_probe.build.v1", "status": "PASS_HEADLESS_PUBLIC_RETAIL_PROBE_BUILD",
            "utc": datetime.now(timezone.utc).isoformat(), "fingerprint": fingerprint, "build_root": str(root),
            "inputs": inputs, "compiler": compiler, "artifacts": artifacts, "imports": imports,
            "dependencies_checked": deps, "retired_intermediates": retired,
            "retired_logical_bytes": sum(row["bytes"] for row in retired),
            "child_commands": guard.calls.copy(), "forbidden_access_attempts": guard.denied.copy(),
            **{name: False for name in FLAGS_FALSE}}
        write_json(report_path, report)
        return report, environment
    except BaseException as error:
        write_json(evidence / "failed_attempt.json", {"status": "FAILED_PUBLIC_RETAIL_PROBE_BUILD",
            "error": type(error).__name__ + ": " + str(error), "fingerprint": fingerprint,
            "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
            **{name: False for name in FLAGS_FALSE}})
        raise


def small_native_json(payload: bytes) -> dict:
    require(len(payload) <= MAX_JSON, "Native probe JSON exceeded its evidence bound")
    value = json.loads(payload.decode("utf-8-sig").strip())
    require(isinstance(value, dict) and isinstance(value.get("status"), str) and
            value.get("schema") == "zerosis.retail.public_probe.v1", "Native probe did not return the declared status schema")
    def visit(item, depth=0):
        require(depth <= 16, "Native probe JSON nesting exceeded its bound")
        if isinstance(item, str):
            require(len(item) <= 4096, "Refusing a payload-sized native JSON string")
        elif isinstance(item, list):
            require(len(item) <= 128, "Refusing a payload-sized native JSON array")
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, dict):
            require(len(item) <= 256, "Native probe JSON object exceeded its bound")
            for child in item.values():
                visit(child, depth + 1)
    visit(value)
    for name in (*FLAGS_FALSE, "complete_save_verified", "host_gamecore_or_hwnd_executed", "game_or_user_save_paths_accessed",
                 "automatic_profile_retry", "native_inflate_performed", "full_engine_goal_complete"):
        require(name not in value or value[name] is False, "Native probe exceeded its scope: " + name)
    return value


def run_native(command: tuple[str, ...], data: bytes, *, root: Path, environment: dict,
               evidence: Path, mode: str) -> dict:
    result = subprocess.run(list(command), cwd=root, env=environment, input=data, capture_output=True, timeout=180,
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
    require(result.returncode in (0, 1), "Native probe exited outside its diagnostic protocol")
    require(len(result.stderr) <= 16 * 1024, "Native probe stderr exceeded its log bound")
    observation = small_native_json(result.stdout)
    require(observation.get("mode") == mode and isinstance(observation.get("profiles"), dict),
            "Native probe mode or profile echo differs")
    declared = observation["profiles"]
    require(declared.get("widths_explicit") is True and
            all(declared.get(name) == int(command[index]) for name, index in (("awards", 3), ("grand", 5), ("projects", 7))),
            "Native probe did not use the exact caller-declared widths")
    if observation.get("stdin_read_complete") is True:
        require(observation["input_bytes"] == len(data), "Native probe stdin byte count differs")
    else:
        require(observation.get("input_bytes") is None and result.returncode == 1, "Native stdin failure metadata differs")
    write_json(evidence / (mode + ".json"), observation)
    write_text(evidence / (mode + ".stderr.log"), result.stderr.decode("utf-8", errors="replace"), 32 * 1024)
    return {"mode": mode, "returncode": result.returncode, "observation": observation,
            "json_log": artifact(evidence / (mode + ".json")),
            "stderr_log": artifact(evidence / (mode + ".stderr.log")), "stdin_bytes": len(data),
            "stdin_sha256": hashlib.sha256(data).hexdigest(), "stdin_was_ram_only": True}


_MAIN_USED = False


def probe(argv: list[str] | None = None) -> dict:
    global _MAIN_USED
    require(not _MAIN_USED, "Probe entry point is one-use per interpreter")
    _MAIN_USED = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--awards", type=int, required=True)
    parser.add_argument("--grand", type=int, required=True)
    parser.add_argument("--projects", type=int, required=True)
    args = parser.parse_args(argv)
    require(os.name == "nt" and not sys.flags.optimize, "Reviewed Windows interpreter invocation required")
    profiles = {"awards": args.awards, "grand": args.grand, "projects": args.projects}
    require(all(type(value) is int and 0 <= value <= 4096 for value in profiles.values()),
            "Explicit profile widths must be integers between zero and 4096")
    project = ordinary(Path(__file__).absolute().parents[1])
    source = ordinary(project / "Tests/retail_public_probe.cpp", file=True)
    manifest_path = ordinary(project / "evidence/retail_save_container/players/public_fixture_candidates.json", file=True)
    helper_paths = [ordinary(project / "tools" / name, file=True) for name in
                    ("probe_public_retail_save.py", "verify_retail_save_header.py", "native_build.py", "collect_baseline.py")]
    # Helpers and standard modules load before the offline guard. Importing this
    # module alone never imports build helpers, fetches data or installs a hook.
    from native_build import environment_for
    from verify_retail_save_header import COMPILER, COMPILER_SHA, VS, pe_imports
    # Avoid a first-use codec import after the exact read allowlist is active.
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"".decode(encoding)
    headers = host_headers(source, project)
    inputs = [artifact(path) for path in (source, *headers, *helper_paths)]
    compiler_path = ordinary(COMPILER, file=True); compiler = artifact(compiler_path)
    require(compiler["sha256"] == COMPILER_SHA, "Reviewed x64 compiler SHA-256 changed")
    manifest_pin = artifact(manifest_path, MAX_JSON)
    candidate = select_fixture(read_json(manifest_path), args.fixture)
    fingerprint = identity({"schema": "zerosis.public_retail_probe.fingerprint.v1", "inputs": inputs, "compiler": compiler})
    root_parent = ordinary(project / "Build/RetailPublicProbe")
    report_parent = ordinary(project / "evidence/retail_save_container/players/probes")
    root = ordinary(root_parent / fingerprint)
    compile_evidence = ordinary(report_parent / ("compile_" + fingerprint))
    probe_id = identity({"build": fingerprint, "fixture": candidate, "profiles": profiles, "manifest": manifest_pin})
    evidence = ordinary(report_parent / (candidate["id"] + "_" + probe_id))
    compile_report = compile_evidence / "build_result.json"
    probe_report = evidence / "probe_result.json"
    build_exists = root.exists() or compile_evidence.exists()
    require(not build_exists or root.is_dir() and compile_evidence.is_dir() and compile_report.is_file(),
            "Inspect prior partial probe build before retrying")
    require(not evidence.exists() or evidence.is_dir() and probe_report.is_file(),
            "Inspect prior partial fixture probe before retrying")
    # The sole raw download happens here, before installing the offline guard.
    # Its exact URL, byte count and Git object identity are checked in RAM.
    raw, raw_identity = fetch_fixture(candidate)
    unchanged(inputs + [compiler, manifest_pin])
    for parent in (root_parent, report_parent):
        ordinary(parent); parent.mkdir(parents=True, exist_ok=True); ordinary(parent)
    exe = root / "RetailPublicProbe.exe"
    compile_command = (str(compiler_path), "@" + str(root / "compile.rsp"), "/link", "/MACHINE:X64",
                       "/INCREMENTAL:NO", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF")
    widths = ("--awards", str(args.awards), "--grand", str(args.grand), "--projects", str(args.projects))
    header_command = (str(exe), "--header", *widths)
    inflated_command = (str(exe), "--inflated", *widths)
    environment_command = ("cmd.exe", "/d", "/c", str(root / "read_build_environment.cmd"))
    build_files = [root / name for name in ("RetailPublicProbe.exe", "retail_public_probe.obj", "compile.rsp",
                                           "dependencies.json", "read_build_environment.cmd")]
    compile_files = [compile_evidence / name for name in
                     ("build_started.json", "compile.log", "build_result.json", "failed_attempt.json")]
    probe_files = [evidence / name for name in ("probe_started.json", "header.json", "header.stderr.log",
                                              "inflated.json", "inflated.stderr.log", "probe_result.json", "failed_attempt.json")]
    guard = OfflineGuard(commands=[environment_command, compile_command, header_command, inflated_command],
        directory=root, readable=[Path(row["path"]) for row in inputs + [compiler, manifest_pin]],
        writable=[*build_files, *compile_files, *probe_files], directories=[root, compile_evidence, evidence])
    sys.addaudithook(guard.audit)
    try:
        if not evidence.exists():
            evidence.mkdir()
            write_json(evidence / "probe_started.json", {"schema": "zerosis.public_retail_probe.started.v1",
                "fixture": candidate, "profiles": profiles, "build_fingerprint": fingerprint,
                "candidate_manifest": manifest_pin, "raw": raw_identity})
        build, environment = ensure_build(project=project, root=root, evidence=compile_evidence, source=source,
            headers=headers, inputs=inputs, compiler=compiler, compiler_path=compiler_path, vs=VS,
            command=compile_command, environment_for=environment_for, pe_imports=pe_imports, guard=guard,
            fingerprint=fingerprint)
        if probe_report.exists():
            prior = read_json(probe_report)
            require(prior.get("status") == "OBSERVED_PUBLIC_RETAIL_SAVE_PROBE" and prior.get("fixture") == candidate and
                    prior.get("profiles") == profiles and prior.get("build_fingerprint") == fingerprint and
                    prior.get("candidate_manifest") == manifest_pin and prior.get("raw") == raw_identity and
                    prior.get("inputs") == inputs and prior.get("compiler") == compiler and
                    prior.get("guard_passed") is True and prior.get("forbidden_access_attempts") == [] and
                    prior.get("compile_report") == artifact(compile_report) and
                    all(prior.get(name) is False for name in FLAGS_FALSE), "Existing fixture probe identity differs")
            require(key(prior["probe_started"]["path"]) == key(evidence / "probe_started.json"),
                    "Existing probe-start identity escaped its evidence directory")
            unchanged([prior["probe_started"]])
            native_rows = prior.get("native_results")
            require(isinstance(native_rows, list) and [row.get("mode") for row in native_rows] in
                    (["header"], ["header", "inflated"]), "Existing native observation sequence differs")
            log_names = {"probe_started.json", "probe_result.json"}
            for row in native_rows:
                mode = row["mode"]
                require(key(row["json_log"]["path"]) == key(evidence / (mode + ".json")) and
                        key(row["stderr_log"]["path"]) == key(evidence / (mode + ".stderr.log")),
                        "Existing native log path differs")
                unchanged([row["json_log"], row["stderr_log"]])
                require(read_json(evidence / (mode + ".json")) == row["observation"], "Existing native JSON content differs")
                small_native_json(json.dumps(row["observation"]).encode("utf-8"))
                log_names.update((mode + ".json", mode + ".stderr.log"))
            require({child.name for child in evidence.iterdir()} == log_names, "Existing probe contains unreviewed files")
            unchanged(inputs + [compiler, manifest_pin]); require(not guard.denied, "Offline guard rejected reuse")
            return {"status": prior["status"], "reused": True, "fixture": candidate["id"],
                    "report": artifact(probe_report), "build_fingerprint": fingerprint,
                    **{name: False for name in FLAGS_FALSE}}
        results = [run_native(header_command, raw, root=root, environment=environment, evidence=evidence, mode="header")]
        inflation = {"attempted": False, "reason": "header_parser_rejected", "retained_on_disk": False}
        if results[0]["returncode"] == 0:
            offset = results[0]["observation"].get("compressed_offset")
            require(type(offset) is int and 0 <= offset <= len(raw), "Header did not return one bounded compressed offset")
            compressed = raw[offset:]
            inflation = {"attempted": True, "compressed_offset": offset, "compressed_bytes": len(compressed),
                "compressed_sha256": hashlib.sha256(compressed).hexdigest(), "retained_on_disk": False,
                "maximum_inflated_bytes": MAX_INFLATED, "signature_search_used": False}
            decoder = zlib.decompressobj()
            try:
                inflated = decoder.decompress(compressed, MAX_INFLATED + 1)
            except zlib.error as error:
                inflation.update({"status": "ZLIB_DIAGNOSTIC_REJECTED", "error": str(error),
                    "inflated_bytes": None, "sha256": None, "decoder_eof": decoder.eof,
                    "unconsumed_tail_bytes": len(decoder.unconsumed_tail), "unused_data_bytes": len(decoder.unused_data),
                    "unconsumed_tail_sha256": hashlib.sha256(decoder.unconsumed_tail).hexdigest(),
                    "unused_data_sha256": hashlib.sha256(decoder.unused_data).hexdigest(), "compressed_stream_complete": False})
            else:
                inflation.update({"inflated_bytes": len(inflated), "sha256": hashlib.sha256(inflated).hexdigest(),
                    "decoder_eof": decoder.eof, "unconsumed_tail_bytes": len(decoder.unconsumed_tail),
                    "unused_data_bytes": len(decoder.unused_data),
                    "unconsumed_tail_sha256": hashlib.sha256(decoder.unconsumed_tail).hexdigest(),
                    "unused_data_sha256": hashlib.sha256(decoder.unused_data).hexdigest(),
                    "compressed_stream_complete": decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data})
                if len(inflated) > MAX_INFLATED:
                    inflation["status"] = "INFLATED_BYTE_LIMIT_REJECTED"
                else:
                    inflation["status"] = "BOUNDED_INFLATION_OBSERVED"
                    results.append(run_native(inflated_command, inflated, root=root, environment=environment,
                                              evidence=evidence, mode="inflated"))
        unchanged(inputs + [compiler, manifest_pin] + list(build["artifacts"].values()))
        require(not guard.denied, "Offline guard rejected a probe operation")
        report = {"schema": "zerosis.public_retail_probe.observation.v1", "status": "OBSERVED_PUBLIC_RETAIL_SAVE_PROBE",
            "utc": datetime.now(timezone.utc).isoformat(), "fixture": candidate, "profiles": profiles,
            "build_fingerprint": fingerprint, "build_reused": build_exists, "compile_report": artifact(compile_report),
            "candidate_manifest": manifest_pin, "inputs": inputs, "compiler": compiler, "raw": raw_identity,
            "inflation": inflation, "native_results": results, "probe_started": artifact(evidence / "probe_started.json"),
            "guard_passed": True, "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
            "automatic_profile_retry": False, "raw_or_inflated_or_database_saved": False,
            "input_files_unchanged": True, "complete_container_validated": False, "sdk_restore_verified": False,
            "full_engine_goal_complete": False, **{name: False for name in FLAGS_FALSE}}
        write_json(probe_report, report)
        return {"status": report["status"], "reused": False, "fixture": candidate["id"],
            "report": artifact(probe_report), "build_fingerprint": fingerprint,
            "native_header_status": results[0]["observation"]["status"],
            "native_inflated_status": results[1]["observation"]["status"] if len(results) == 2 else None,
            "inflation": inflation, "guard_passed": True, **{name: False for name in FLAGS_FALSE}}
    except BaseException as error:
        if evidence.is_dir() and not (evidence / "failed_attempt.json").exists():
            write_json(evidence / "failed_attempt.json", {"status": "FAILED_PUBLIC_RETAIL_SAVE_PROBE",
                "error": type(error).__name__ + ": " + str(error), "fixture": candidate, "profiles": profiles,
                "build_fingerprint": fingerprint, "raw": raw_identity, "child_commands": guard.calls,
                "forbidden_access_attempts": guard.denied, "raw_or_inflated_or_database_saved": False,
                **{name: False for name in FLAGS_FALSE}})
        raise


def main(argv: list[str] | None = None) -> int:
    try:
        print(json.dumps(probe(argv), ensure_ascii=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "FAILED_PUBLIC_RETAIL_SAVE_PROBE", "error": type(error).__name__ + ": " + str(error),
                          **{name: False for name in FLAGS_FALSE}}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
