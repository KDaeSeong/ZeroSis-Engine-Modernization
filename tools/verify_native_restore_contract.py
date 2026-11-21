"""Build only the portable native-restore contract and inspect one owned save.

The existing SDK/Host pair and its private saves are read-only inputs. Two
headless configurations run the same component test; no SDK binary is loaded.
"""
from __future__ import annotations

import codecs
from contextlib import closing
from datetime import datetime, timezone
import gzip
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import struct
import subprocess
import sys


PROJECT = Path(__file__).absolute().parents[1]
BUILD = PROJECT / "Build/NativeRestoreContract/component"
STAGE = PROJECT / "evidence/native_restore_contract"
COMPONENT = STAGE / "component"
SOURCE = PROJECT / "Tests/native_restore_contract.cpp"
SOURCE_SHA = "3704596ab0696a273ac9c8ef35535ee8ec04d11276322ebe87a8be8e8d7bf4b7"
HEADER_PINS = {
    "NativeSaveEnvelope.h": "f8f343d891e4e9fe7aa9d756e1c467971586125803163edf1e478717c11aa7a8",
    "NativeRestoreContract.h": "74bafe17ed8548e59acaaa7facc2dba30ae9454e5613d81d218c3b2080524a36",
    "RetailSaveStateWire.h": "10bfd0244fe20289b2c72cb98a5402b88795a36395c217c768035fb24741fdda",
    "RetailSaveGameFront.h": "8e1316874fbf8f1c726f39a250128a475399b8916ce89a3b9822c0656bb0215c",
    "RetailSaveGameTail.h": "30ae2705dd5e358cf7bf8a56061d8ecb865f9cc7a3fc73290b07c8599c82d140",
}
HELPER_PINS = {
    "probe_public_retail_save": "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "verify_retail_save_header": "9bc62f6e200fbb470d516606aa845724426be42e5ee8bdd56f69f1126afcaa5f",
    "native_build": "c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21",
    "collect_baseline": "7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187",
}
AUDIT = PROJECT / "evidence/sdk_runtime_play/latest_pair_preparation/publication/final_audit.json"
AUDIT_SHA = "730c6a91e5e0e975502559c1952008200cf85181885e0385c62d3f7f1a2c4eaf"
CODEC = PROJECT / "evidence/native_save_archive/portable_envelope/result.json"
CODEC_SHA = "62acfd495ea42514be16d55cef421fcbb6965a955a362680fa2e650775769f7f"
FIXTURE_SHA = "d4f51ae15c11bce5dbec849d271a3c6cc80c8ae9d88b8a3b2e35069b0193c07b"
FIXTURE_BYTES = 9612910
HISTORIES = (
    ("Build/NativeSaveEnvelope/e7df5df8b738d5f4adc1/dependencies.json",
     "7542afd5a13322ebcbd4d0540340af3948ad8f492777e54c8d26368b53dd5206"),
    ("Build/RetailSaveState/865fbff5be2d9db2/O2/dependencies.json",
     "b6bb08b175bdb492cd8ac91913610ac25173a1543addacfdd340aec9c5fc1ab7"),
)
MODES = {"O2": ("/O2",), "OdRTC1": ("/Od", "/RTC1")}
FIRST_COMPONENT = STAGE / "component"
FIRST_STARTED_SHA = "d7484a203d6f56c1b1d208dea3b0005a0b9d00163c30740e39c5edbfffa856d6"
FIRST_FAILED_SHA = "3cb9161acbd985feffe4d94f7e99e2ee9db055e30b81629d1d01a628a08d1c92"
DRIVER_BEFORE_SHA = "75644aab86619c6f72baad235bca6a697c364457de8bd370a00664c3d2ab5888"
DRIVER_BACKUP = STAGE / "source_backups/verify_native_restore_contract.before_retry01.75644aab.py.gz"
DRIVER_BACKUP_SHA = "1f28bcaa9eb08756fecb83c17372666b2a0f1a1acfb0f9dcf915b004024ba425"
BACKUP_RECEIPT = STAGE / "source_backups/verify_native_restore_contract.retry01_backup.json"
BACKUP_RECEIPT_SHA = "b608d9bff1f27ca6f25ef97a7a20e93f520792ee04e4bcea8d6b9566f1502c3a"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load_helpers():
    for name, expected in HELPER_PINS.items():
        path = PROJECT / "tools" / (name + ".py")
        for part in (path, *path.parents):
            info = part.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                    "A compiler helper has a reparse parent")
        data = path.read_bytes()
        require(len(data) <= 2 * 1024 * 1024 and hashlib.sha256(data).hexdigest() == expected,
                "A reviewed compiler helper changed")
    modules = {name: importlib.import_module(name) for name in HELPER_PINS}
    for name, module in modules.items():
        require(Path(module.__file__).absolute() == PROJECT / "tools" / (name + ".py"),
                "A compiler helper was imported from another path")
    return modules["probe_public_retail_save"], modules["verify_retail_save_header"], modules["native_build"]


def pin(g, path, expected=None, maximum=64 * 1024 * 1024):
    row = g.artifact(path, maximum)
    if expected is not None:
        require(row["sha256"] == expected, "Pinned bytes changed: " + Path(path).name)
    return row


def recorded(g, row):
    actual = pin(g, row["path"])
    require(all(actual[key] == row[key] for key in actual if key in row),
            "Retained input identity differs: " + Path(row["path"]).name)
    return actual


def merge(g, rows):
    result = {}
    for row in rows:
        key = g.key(row["path"])
        require(key not in result or result[key] == row, "Conflicting input identities")
        result[key] = row
    return [result[key] for key in sorted(result)]


def retry_inputs(g, attempt, compiler):
    if attempt == 0:
        return None, []
    started = pin(g, FIRST_COMPONENT / "started.json", FIRST_STARTED_SHA)
    failed = pin(g, FIRST_COMPONENT / "failed_attempt.json", FIRST_FAILED_SHA)
    backup = pin(g, DRIVER_BACKUP, DRIVER_BACKUP_SHA)
    receipt = pin(g, BACKUP_RECEIPT, BACKUP_RECEIPT_SHA)
    logs = {name: pin(g, FIRST_COMPONENT / "O2" / ("compile." + suffix), expected) for name, suffix, expected in (
        ("stdout", "stdout.log", "45360cb400058cc17085e4ec5068dcbde5c2ebcf0e470d51b1f8b8196c28f905"),
        ("stderr", "stderr.log", "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"),
        ("process", "process.json", "bbe0bbb45571ccf42e51cfb2294a21c1839f208451cc0bb867610623de1a793d"))}
    original = g.read_json(Path(started["path"]))
    failure = g.read_json(Path(failed["path"]))
    process = g.read_json(Path(logs["process"]["path"]))
    old_driver = [row for row in original["inputs"] if g.key(row["path"]) == g.key(Path(__file__).absolute())]
    old_test = [row for row in original["inputs"] if g.key(row["path"]) == g.key(SOURCE)]
    require(len(old_driver) == len(old_test) == 1 and old_driver[0]["bytes"] == 26724 and
            old_driver[0]["sha256"] == DRIVER_BEFORE_SHA and old_test[0]["sha256"] ==
            "5e1d2d9618f845aa035481f5a624b9a11dec8614b4a4a3a6ec32ba6f5068a20a" and
            old_test[0]["sha256"] != SOURCE_SHA, "Retry does not replace the exact failed test source")
    restored = gzip.decompress(g.read_bytes(DRIVER_BACKUP, 16384))
    proof = g.read_json(BACKUP_RECEIPT)
    require(len(restored) == 26724 and hashlib.sha256(restored).hexdigest() == DRIVER_BEFORE_SHA and
            proof["roundtrip_verified"] is True and proof["first_started"] == started and
            proof["before"] == old_driver[0], "The original driver backup does not restore its first-started identity")
    require(failure["status"] == "FAILED_PORTABLE_NATIVE_RESTORE_CONTRACT" and
            failure["forbidden_access_attempts"] == [] and len(failure["child_commands"]) == 2 and
            failure["child_commands"][0][0] == "cmd.exe" and
            g.key(failure["child_commands"][1][0]) == g.key(compiler) and
            failure["child_commands"][1] == process["command"] and
            type(process["returncode"]) is int and process["returncode"] != 0 and
            b"C4244" in g.read_bytes(logs["stdout"]["path"], 4096), "The preserved first failure differs")
    provenance = dict(attempt=1, previous_started=started, previous_failed_attempt=failed,
        previous_compile_logs=logs, previous_driver_backup=backup, backup_receipt=receipt,
        source_before=dict(original_path=str(SOURCE), bytes=old_test[0]["bytes"], sha256=old_test[0]["sha256"]),
        source_after=dict(path=str(SOURCE), sha256=SOURCE_SHA),
        reason="Explicit retry after the first O2 /WX C4244 short-pair construction failure; only the reviewed test-source conversion fix is accepted.")
    return provenance, [started, failed, backup, receipt, *logs.values()]


def native_layout(raw, manifest):
    require(80 <= len(raw) <= 32 * 1024 * 1024 and raw[:16] == b"ZEROSIS_SAVE_V1\0",
            "The retained input is not bounded native V1")
    end = len(raw) - 32
    require(hashlib.sha256(raw[:end]).digest() == raw[end:], "The native checksum differs")
    version, flags, turn, elapsed, active, teams, players, count = struct.unpack_from("<8I", raw, 16)
    require(version == 1 and flags <= 3 and turn <= 2147483647 and elapsed <= 2147483647 and
            active < 64 and (teams, players, count) == (64, 64, 133), "The native V1 metadata differs")
    identities = [(kind, 0) for kind in range(1, 6)] + [(6, i) for i in range(64)] + [(7, i) for i in range(64)]
    sections, at = [], 48
    for identity in identities:
        require(at <= end and end - at >= 12, "Truncated native descriptor")
        kind, index, size = struct.unpack_from("<3I", raw, at)
        at += 12
        require((kind, index) == identity and 0 < size <= 2147483647 and size <= end - at,
                "The native section order or byte bound differs")
        sections.append(dict(kind=kind, index=index, offset=at, bytes=size))
        at += size
    require(at == end, "Native section data does not end at its checksum")
    bundle, game = sections[0], sections[2]
    require(raw[bundle["offset"]:bundle["offset"] + bundle["bytes"]] == manifest,
            "The retained native Bundle bytes differ")
    return dict(input_bytes=len(raw), wire_sha256=hashlib.sha256(raw).hexdigest(), section_count=133,
                flags=flags, turn=turn, elapsed=elapsed, active_player=active,
                game_offset=game["offset"], game_bytes=game["bytes"],
                game_sha256=hashlib.sha256(raw[game["offset"]:game["offset"] + game["bytes"]]).hexdigest())


def verify_game_observation(raw, expected, observed):
    require(isinstance(observed, dict) and all(type(observed.get(key)) is type(value) and observed[key] == value
            for key, value in expected.items()),
            "The native observation differs from independent Python framing")
    game = raw[expected["game_offset"]:expected["game_offset"] + expected["game_bytes"]]
    require(len(game) >= 4 and struct.unpack_from("<I", game)[0] == 1, "Unsupported native CvGame version")
    fields = ("replay_messages", "sessions", "replay_count_offset", "replay_records_offset",
              "replay_records_bytes", "session_offset")
    require(all(type(observed.get(key)) is int and observed[key] >= 0 for key in fields),
            "Invalid source-order Game observation")
    count_at, at, size, session_at = (observed[key] for key in fields[2:])
    require(4 <= count_at <= len(game) - 4 and at == count_at + 4 and size <= len(game) - at and
            session_at == at + size and session_at <= len(game) - 4 and
            struct.unpack_from("<I", game, count_at - 4)[0] == 2 and
            struct.unpack_from("<i", game, count_at)[0] == observed["replay_messages"] and
            struct.unpack_from("<i", game, session_at)[0] == observed["sessions"],
            "Observed Game offsets do not describe their actual count/session words")
    require(observed["replay_messages"] <= size // 20, "Replay count exceeds its observed bytes")
    for _ in range(observed["replay_messages"]):
        require(at <= session_at and session_at - at >= 20, "Truncated observed replay record")
        plots = struct.unpack_from("<i", game, at + 8)[0]
        at += 12
        require(0 <= plots <= (session_at - at - 8) // 4, "Observed replay plots exceed their span")
        at += plots * 4
        text = struct.unpack_from("<i", game, at + 4)[0]
        at += 8
        require(0 <= text <= session_at - at, "Observed replay text exceeds its span")
        game[at:at + text].decode("utf-8", errors="strict")
        at += text
    require(at == session_at and observed.get("structural_game_inspection_verified") is True and
            observed.get("sdk_restore_verified") is False, "Game inspection claims an unsupported scope")


def standard_inputs(g, compiler):
    vc = compiler.parents[3]
    kits = Path(r"C:\Program Files (x86)\Windows Kits\10")
    include_roots = [vc / "include", kits / "Include/10.0.26100.0/ucrt"]
    inputs, paths = [], {}
    for relative, expected in HISTORIES:
        row = pin(g, PROJECT / relative, expected)
        inputs.append(row)
        document = g.read_json(Path(row["path"]))
        require(document.get("Version") == "1.2" and isinstance(document.get("Data", {}).get("Includes"), list),
                "The historical portable dependency locator differs")
        for value in document["Data"]["Includes"]:
            path = g.ordinary(value, file=True)
            if g.within(path, PROJECT):
                continue
            require(any(g.within(path, root) for root in include_roots),
                    "Historical dependencies escaped the exact portable toolchain include roots")
            paths[g.key(path)] = path
    require(paths, "No historical portable standard-header graph")
    inputs.extend(pin(g, path) for path in paths.values())
    libraries = [vc / "lib/x64" / name for name in ("libcpmt.lib", "libcmt.lib", "libvcruntime.lib", "oldnames.lib")]
    libraries += [kits / "Lib/10.0.26100.0/ucrt/x64/libucrt.lib", kits / "Lib/10.0.26100.0/um/x64/kernel32.lib"]
    inputs.extend(pin(g, path) for path in libraries)
    for name in ("cl.exe", "c1xx.dll", "c2.dll", "link.exe"):
        inputs.append(pin(g, compiler.parent / name))
    inputs.append(pin(g, vc.parents[2] / "Auxiliary/Build/vcvars64.bat"))
    return inputs, include_roots, libraries


def response(mode, includes):
    root = BUILD / mode
    flags = ["/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", "/MT", "/utf-8", "/fp:strict", "/X", *MODES[mode]]
    flags += [f'/I"{PROJECT / "Source/Host"}"', *(f'/I"{path}"' for path in includes), f'"{SOURCE}"',
              f'/Fo"{root / "contract.obj"}"', f'/Fe"{root / "NativeRestoreContractTest.exe"}"',
              f'/sourceDependencies "{root / "dependencies.json"}"']
    return "\n".join(flags) + "\n"


def capture(g, command, environment, prefix, *, data=b"", compile_mode=False):
    stdout, stderr, timed_out, code, launch_error = b"", b"", False, None, None
    try:
        child = subprocess.run(command, cwd=BUILD, env=environment, input=data, capture_output=True, timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        stdout, stderr, code = child.stdout, child.stderr, child.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr, timed_out = error.stdout or b"", error.stderr or b"", True
    except OSError as error:
        launch_error = type(error).__name__ + ": " + str(error)
    maximum = 512 * 1024 if compile_mode else 128 * 1024
    encoding = "mbcs" if compile_mode else "utf-8-sig"
    paths = {name: prefix.with_suffix(suffix) for name, suffix in
             (("stdout", ".stdout.log"), ("stderr", ".stderr.log"), ("process", ".process.json"))}
    g.write_text(paths["stdout"], stdout[:maximum].decode(encoding, errors="replace"), maximum * 3)
    g.write_text(paths["stderr"], stderr[:maximum].decode(encoding, errors="replace"), maximum * 3)
    g.write_json(paths["process"], dict(command=list(command), returncode=code, timed_out=timed_out, launch_error=launch_error,
        stdin_bytes=len(data), stdout_bytes=len(stdout), stderr_bytes=len(stderr)))
    logs = {name: g.artifact(path) for name, path in paths.items()}
    require(not timed_out and code == 0 and len(stdout) <= maximum and len(stderr) <= maximum,
            "Child failed; inspect its preserved logs and process result")
    if compile_mode:
        require(not re.search(r"\bwarning\s+[A-Z]+\d+", (stdout + stderr).decode("mbcs", errors="replace"), re.I),
                "The portable build emitted a warning")
        return None, logs
    require(not stderr, "The portable test wrote stderr")
    value = json.loads(stdout.decode("utf-8-sig"))
    require(isinstance(value, dict), "The portable test did not return a JSON object")
    return value, logs


def check_test(g, value, mode):
    require(value.get("schema") == "zerosis.native_restore.contract_test.v1" and
            value.get("status") == "PASS_NATIVE_RESTORE_CONTRACT_COMPONENT" and value.get("mode") == mode and
            type(value.get("checks")) is int and value["checks"] > 0 and value.get("phase") == "complete" and
            value.get("error") is None and value.get("profiles") == {"awards": 5} and value.get("game_input") is None,
            "Missing portable contract result")
    for name in ("input_bytes_unchanged", "input_files_unchanged", "all_failure_outputs_unchanged", "test_only_sha256"):
        require(value.get(name) is True, "Missing component invariant: " + name)
    for name in (*g.FLAGS_FALSE, "sdk_executed", "production_cng_executed", "native_restore_approved", "full_engine_goal_complete"):
        require(value.get(name) is False, "The component exceeded its proof scope: " + name)
    if mode == "self-test":
        require(value.get("stdin_read_complete") is False and value.get("native_input") is None,
                "The self-test unexpectedly consumed an input")
        for name in ("truncations", "directed_corruptions", "atomic_failure_cases", "literal_cases", "valid_cases"):
            require(type(value.get(name)) is int and value[name] > 0, "Missing negative test class: " + name)
        require(type(value.get("sha256_vectors")) is int and value["sha256_vectors"] >= 3,
                "The test-only SHA256 implementation lacks its known answers")
    else:
        require(value.get("stdin_read_complete") is True, "The owned native input was not consumed completely")


def main():
    global BUILD, COMPONENT
    require(sys.argv[1:] in ([], ["--attempt", "1"]) and os.name == "nt" and not sys.flags.optimize,
            "Use the Windows interpreter with no arguments or explicit --attempt 1")
    attempt = 1 if sys.argv[1:] else 0
    suffix = "component_retry01" if attempt else "component"
    BUILD = PROJECT / "Build/NativeRestoreContract" / suffix
    COMPONENT = STAGE / suffix
    require(len(SOURCE_SHA) == 64 and all(len(value) == 64 for value in HEADER_PINS.values()),
            "The portable source and header inputs are not frozen")
    sys.dont_write_bytecode = True
    g, h, n = load_helpers()
    for encoding in ("mbcs", "utf-8", "utf-8-sig", "ascii"):
        codecs.lookup(encoding)
        b"".decode(encoding)
    compiler_path = g.ordinary(h.COMPILER, file=True)
    compiler = pin(g, compiler_path, h.COMPILER_SHA)
    inputs = [pin(g, Path(__file__).absolute()), pin(g, SOURCE, SOURCE_SHA), pin(g, AUDIT, AUDIT_SHA), pin(g, CODEC, CODEC_SHA)]
    previous_failure, retry_rows = retry_inputs(g, attempt, compiler_path)
    inputs.extend(retry_rows)
    inputs.extend(pin(g, PROJECT / "tools" / (name + ".py"), expected) for name, expected in HELPER_PINS.items())
    headers = g.host_headers(SOURCE, PROJECT)
    require({path.name for path in headers} == set(HEADER_PINS), "The consumer includes a nonportable or unexpected project header")
    inputs.extend(pin(g, path, HEADER_PINS[path.name]) for path in headers)
    audit, codec = g.read_json(AUDIT), g.read_json(CODEC)
    require(audit.get("status") == "PASS_LATEST_HOST_SDK_PRIVATE_PREPARATION_PUBLICATION" and
            audit.get("run_id") == "20261024T031412Z_e06aeb61ed6a", "Unexpected retained runtime publication")
    publication_row = next(row for row in audit["proofs"] if Path(row["path"]).name == "result.json" and Path(row["path"]).parent.name == "publication")
    inputs.append(recorded(g, publication_row))
    publication = g.read_json(Path(publication_row["path"]))
    request_row = publication["stage"]["proofs"]["request"]
    inputs.append(recorded(g, request_row))
    request = g.read_json(Path(request_row["path"]))
    runtime = PROJECT / "Build/InteractiveGameRuntime/20261024T031412Z_e06aeb61ed6a"
    require(g.key(request["cwd"]) == g.key(runtime) and len(request["runtime_inputs"]) == 24,
            "Unexpected current private runtime inventory")
    current = {Path(row["path"]).name: recorded(g, row) for row in request["runtime_inputs"]}
    require(len(current) == 24 and all(g.within(row["path"], runtime) for row in current.values()), "Current runtime paths escaped their run")
    inputs.extend(current.values())
    retained = codec["retained_native_input"]
    for name in ("input", "request", "bundle_manifest"):
        inputs.append(recorded(g, retained[name]))
    native = retained["input"]
    require(native["sha256"] == FIXTURE_SHA and native["bytes"] == FIXTURE_BYTES and
            g.key(native["path"]) == g.key(PROJECT / "Build/InteractiveGameRuntime/20261022T001546Z_7fba195072e4/sessions/5cf0696b4369a6f8a2f7a9d9419fc8d7/autosave-0-turn-0.zssave"),
            "Unexpected owned native input")
    raw = g.read_bytes(native["path"], 32 * 1024 * 1024)
    expected = native_layout(raw, g.read_bytes(retained["bundle_manifest"]["path"], 16384))
    prior_request = g.read_json(Path(retained["request"]["path"]))
    prior_rules = next(row for row in prior_request["runtime_inputs"] if Path(row["path"]).name == "rules.db")
    require((prior_rules["sha256"], prior_rules.get("bytes", current["rules.db"]["bytes"])) ==
            (current["rules.db"]["sha256"], current["rules.db"]["bytes"]), "The explicit width database differs from the fixture rules")
    tool_inputs, includes, libraries = standard_inputs(g, compiler_path)
    inputs = merge(g, inputs + tool_inputs + [compiler])
    fingerprint = g.identity(dict(schema="zerosis.native_restore.contract.inputs.v1", inputs=inputs, modes=MODES))
    require(not BUILD.exists() and not COMPONENT.exists(), "Inspect the retained exact attempt; this driver does not repeat builds")
    environment_command = ("cmd.exe", "/d", "/c", str(BUILD / "read_build_environment.cmd"))
    commands, writable = [environment_command], [BUILD / "read_build_environment.cmd"]
    mode_commands = {}
    for mode in MODES:
        root, evidence = BUILD / mode, COMPONENT / mode
        compile_command = (str(compiler_path), "@" + str(root / "compile.rsp"), "/link", "/MACHINE:X64", "/SUBSYSTEM:CONSOLE",
                           "/INCREMENTAL:NO", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF", "/NODEFAULTLIB", *(str(path) for path in libraries))
        self_command = (str(root / "NativeRestoreContractTest.exe"), "--self-test")
        native_command = (str(root / "NativeRestoreContractTest.exe"), "--stdin-native", str(len(raw)), "5")
        mode_commands[mode] = (compile_command, self_command, native_command)
        commands.extend((compile_command, self_command, native_command))
        writable.extend(root / name for name in ("compile.rsp", "dependencies.json", "contract.obj", "NativeRestoreContractTest.exe"))
        writable.extend(evidence / (phase + suffix) for phase in ("compile", "self", "native") for suffix in (".stdout.log", ".stderr.log", ".process.json"))
    writable.extend(COMPONENT / name for name in ("started.json", "failed_attempt.json", "result.json"))
    uri = Path(current["rules.db"]["path"]).as_uri() + "?mode=ro&immutable=1"

    class Guard(g.OfflineGuard):
        database_opens = 0

        def audit(self, event, args):
            if event == "sqlite3.connect":
                if args[0] != uri or self.database_opens:
                    self.fail("Only the exact immutable read-only width database may be opened once")
                self.database_opens += 1
            if event.startswith(("ctypes.dlsym", "os.exec", "os.spawn")) or event in ("os.kill", "os.killpg", "os.posix_spawn"):
                self.fail("Unapproved native execution or dynamic symbol access")
            super().audit(event, args)

    guard = Guard(commands=commands, directory=BUILD, readable=[Path(row["path"]) for row in inputs], writable=writable,
        directories=[BUILD, STAGE, COMPONENT, *(BUILD / mode for mode in MODES), *(COMPONENT / mode for mode in MODES)])
    sys.addaudithook(guard.audit)
    try:
        BUILD.mkdir(); STAGE.mkdir(exist_ok=True); COMPONENT.mkdir()
        for mode in MODES:
            (BUILD / mode).mkdir(); (COMPONENT / mode).mkdir()
        g.write_json(COMPONENT / "started.json", dict(schema="zerosis.native_restore.contract.started.v1", fingerprint=fingerprint,
            attempt=attempt, previous_failure=previous_failure, inputs=inputs, compiler=compiler,
            planned_commands=[list(command) for command in commands], sdk_host_or_ui_execution_allowed=False))
        require(not any(os.environ.get(name) for name in ("CL", "_CL_", "LINK")), "Inherited compiler options are forbidden")
        environment, selected = n.environment_for(h.VS, "x64", BUILD)
        require(g.key(selected) == g.key(compiler_path) and not any(environment.get(name) for name in ("CL", "_CL_", "LINK")),
                "Compiler selection or inherited options changed")
        environment["TMP"] = environment["TEMP"] = str(BUILD)
        environment["VSLANG"] = "1033"
        environment["PATH"] = str(compiler_path.parent) + os.pathsep + str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32")
        environment["INCLUDE"] = os.pathsep.join(str(path) for path in includes)
        environment["LIB"] = os.pathsep.join(dict.fromkeys(str(path.parent) for path in libraries))
        with closing(sqlite3.connect(uri, uri=True)) as database:
            database.execute("PRAGMA query_only=ON")
            widths = database.execute("SELECT Value FROM Defines WHERE Name=?", ("NUM_VICTORY_POINT_AWARDS",)).fetchall()
        require(len(widths) == 1 and str(widths[0][0]) == "5", "The pinned rules database does not declare width five")
        results, outputs, retired = {}, [], []
        input_by_key = {g.key(row["path"]): row for row in inputs}
        for mode, (compile_command, self_command, native_command) in mode_commands.items():
            root, evidence = BUILD / mode, COMPONENT / mode
            g.write_text(root / "compile.rsp", response(mode, includes), 16384)
            _, compile_logs = capture(g, compile_command, environment, evidence / "compile", compile_mode=True)
            dependency = g.read_json(root / "dependencies.json")
            require(dependency.get("Version") == "1.2", "Unexpected compiler dependency format")
            g.dependency_check(root / "dependencies.json", SOURCE, headers, PROJECT)
            actual = {g.key(value) for value in [dependency["Data"]["Source"], *dependency["Data"]["Includes"]]}
            require(actual <= input_by_key.keys(), "The compiler consumed an input outside the prehashed portable graph")
            actual_inputs = [input_by_key[key] for key in sorted(actual)]
            g.unchanged(actual_inputs)
            require(h.pe_imports(root / "NativeRestoreContractTest.exe") == ["kernel32.dll"], "The headless executable imports an unapproved DLL")
            self_result, self_logs = capture(g, self_command, environment, evidence / "self")
            check_test(g, self_result, "self-test")
            native_result, native_logs = capture(g, native_command, environment, evidence / "native", data=raw)
            check_test(g, native_result, "stdin-native")
            verify_game_observation(raw, expected, native_result.get("native_input"))
            artifacts = {name: g.artifact(root / name) for name in ("compile.rsp", "dependencies.json", "NativeRestoreContractTest.exe")}
            outputs.extend(artifacts.values())
            results[mode] = dict(flags=list(MODES[mode]), imports=["kernel32.dll"], actual_compiler_input_count=len(actual_inputs),
                actual_compiler_input_manifest_sha256=hashlib.sha256(json.dumps(actual_inputs, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
                all_actual_compiler_dependencies_prehashed=True, artifacts=artifacts, compile_logs=compile_logs,
                self_test=self_result, self_logs=self_logs, native_test=native_result, native_logs=native_logs)
        require(results["O2"]["native_test"]["native_input"] == results["OdRTC1"]["native_test"]["native_input"], "Native observations differ between configurations")
        for key in ("checks", "truncations", "directed_corruptions", "atomic_failure_cases"):
            require(results["O2"]["self_test"][key] == results["OdRTC1"]["self_test"][key], "Self-test counts differ between configurations")
        g.unchanged(inputs + outputs)
        require(not guard.denied and not any(guard.commands.values()) and guard.database_opens == 1, "The exact child/database command budget was not observed")
        for path in [BUILD / "read_build_environment.cmd", *(BUILD / mode / "contract.obj" for mode in MODES)]:
            retired.append(g.retire(path, BUILD, guard))
        report = dict(schema="zerosis.native_restore.contract.component.v1", status="PASS_PORTABLE_NATIVE_RESTORE_CONTRACT",
            utc=datetime.now(timezone.utc).isoformat(), attempt=attempt, previous_failure=previous_failure,
            fingerprint=fingerprint, inputs=inputs, compiler=compiler,
            results=results, retained_native_input=retained["input"], independent_python_native_v1=expected,
            explicit_awards_width=5, rules_database=current["rules.db"], rules_database_read_only=True,
            retained_runtime_inputs_unchanged=24, retained_host=current["ZeroSisHost_x64.exe"],
            retained_sdk=current["CvGameCoreDLL_Expansion2_x64.dll"],
            historical_graphs_used_only_as_dependency_locators=True, child_commands=guard.calls,
            forbidden_access_attempts=guard.denied, retired_intermediates=retired,
            retired_logical_bytes=sum(row["bytes"] for row in retired), input_bytes_saved_or_copied=False,
            production_callers_compiled=False, sdk_or_host_or_window_executed=False, original_game_or_user_state_accessed=False,
            sdk_restore_verified=False, native_restore_approved=False, retail_save_accepted=False,
            runtime_updated=False, default_promoted=False, full_engine_goal_complete=False)
        g.write_json(COMPONENT / "result.json", report)
        print(json.dumps(dict(status=report["status"], report=g.artifact(COMPONENT / "result.json"),
                             modes=list(results), native_input_sha256=FIXTURE_SHA)))
        return 0
    except BaseException as error:
        if COMPONENT.is_dir() and not (COMPONENT / "failed_attempt.json").exists():
            g.write_json(COMPONENT / "failed_attempt.json", dict(status="FAILED_PORTABLE_NATIVE_RESTORE_CONTRACT",
                attempt=attempt, previous_failure=previous_failure,
                error=type(error).__name__ + ": " + str(error), child_commands=guard.calls,
                forbidden_access_attempts=guard.denied, sdk_or_host_or_window_executed=False, full_engine_goal_complete=False))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
