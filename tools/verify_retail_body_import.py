"""Build one portable body-import component and inspect two pinned RAM inputs.

Importing this module performs no I/O, downloads, builds or child execution.
Only main() may create the named build and bounded evidence outputs.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import ssl
import stat
import subprocess
import sys
import urllib.request
import zlib

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/retail_save_container/body_import"
SOURCE = PROJECT / "Tests/retail_body_import.cpp"
SOURCE_SHA = "48b6d4afa52cc7f18d78422ec8fcedef018e3f278a6d56985dad8358fd4f1c69"
IMPORT_HEADER = PROJECT / "Source/Host/RetailSaveBodyImport.h"
IMPORT_HEADER_SHA = "b64bbfecde88ac7970436eecf058689791fbb9c1c1fdeacfa78362cce8ca406b"
POST = PROJECT / "evidence/retail_save_container/map_trace/restore_booleans/player1_trace/publication/post_checks.json"
POST_SHA = "e581c8508ecaa68f54d3b26180e44b8aaa05f1d7e0e26be687804dcc35b26e39"
PUBLIC = PROJECT / "evidence/retail_save_container/map_trace/chunk_frames_component/public_result.json"
PUBLIC_SHA = "9219e7b264e4190127a29f7d81f6bdfb403637221e1fd0d7ef275559dc7b614d"
BUDGET = PROJECT / "evidence/retail_save_container/map_trace/record_budget/result.json"
BUDGET_SHA = "c00a7e6c07179e2df7d049e36df42e6484eda51a4a47111086ab63b327a242e1"
PINS = {
    "probe_public_retail_save": "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "verify_retail_save_header": "9bc62f6e200fbb470d516606aa845724426be42e5ee8bdd56f69f1126afcaa5f",
    "native_build": "c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21",
    "collect_baseline": "7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187",
}
PIN_KEYS = ("path", "bytes", "sha256", "file_identity", "mtime_ns")
FALSE_FLAGS = (
    "gamecore_loaded", "window_created", "game_accessed", "user_saves_accessed",
    "complete_player_validated", "complete_save_validated", "ruleset_compatibility_verified",
    "restore_approved", "sdk_executed", "full_engine_goal_complete",
)
WIRE_GROUPS = ("game_map", "teams", "players", "supporting", "object_counts_completed",
               "array_records_completed", "last_completed_offset", "declared_sequence_has_zero_remainder")
EXPECTED = {
    "jpl_before": {
        "raw_bytes": 719344,
        "raw_sha256": "dd879d6b0d84bdf7b80abcb98aed925738031a5530dc85a8849cce0ec7598995",
        "inflated_bytes": 21151963,
        "inflated_sha256": "112a36e4158b8da82d12cac5c2a724c907a563cfc56fe0747dbaf7197a8a1e4b",
        "records": 1805777, "budget": 2097152, "edits": [],
    },
    "rivar_settler12": {
        "raw_bytes": 691024,
        "raw_sha256": "81001bbe3c7ec96329ade9d506acc097b68fcf743c081b44cd0dbccdefc18ab2",
        "inflated_bytes": 16727961,
        "inflated_sha256": "34a2483f6d2c135cb8edb9c0b237c2fbac624d2fd3dca2adc0dba22d98087240",
        "records": 713024, "budget": 1048576,
        "edits": [{"offset": 7795644, "before": 68, "after": 1,
                   "player_slot": 1, "operation_index": 0}],
    },
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def module_bytes(path, expected):
    """Authenticate local helpers before any helper module executes."""
    for part in (path, *path.parents):
        info = part.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Reparse helper path is forbidden")
    before = path.stat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= 2 * 1024 * 1024,
            "Helper size or file kind differs")
    data = path.read_bytes()
    after = path.stat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "Helper changed while reading")
    require(len(data) == before.st_size and hashlib.sha256(data).hexdigest() == expected,
            "Frozen helper SHA-256 differs: " + path.name)


def pinned_rows(g, rows, count):
    require(isinstance(rows, list) and len(rows) == count, "Previous publication pin count differs")
    normalized = []
    for row in rows:
        require(isinstance(row, dict) and all(name in row for name in PIN_KEYS), "Incomplete publication pin")
        expected = {name: row[name] for name in PIN_KEYS}
        require(g.artifact(expected["path"]) == expected, "Published input changed: " + expected["path"])
        normalized.append(expected)
    return normalized


def unique_rows(g, rows):
    unique = {}
    for row in rows:
        key = g.key(row["path"])
        require(key not in unique or unique[key] == row, "Conflicting input pins")
        unique[key] = row
    return [unique[name] for name in sorted(unique)]


def framed_input(g, case, expected, opener):
    fixture = g.select_fixture({"candidates": [case["fixture"]]}, case["fixture"]["id"])
    require(fixture["bytes"] == expected["raw_bytes"] and case["raw_sha256"] == expected["raw_sha256"] and
            case["inflated_bytes"] == expected["inflated_bytes"] and
            case["inflated_sha256"] == expected["inflated_sha256"], "Pinned public input identity differs")
    request = urllib.request.Request(fixture["raw_url"], headers={
        "User-Agent": "ZeroSis-Portable-Body-Import", "Accept-Encoding": "identity"})
    with opener.open(request, timeout=30) as response:
        require(response.status == 200 and response.geturl() == fixture["raw_url"], "Public response identity differs")
        length = response.headers.get("Content-Length")
        require(length is None or int(length) == fixture["bytes"], "Public content length differs")
        raw = response.read(fixture["bytes"] + 1)
    require(len(raw) == fixture["bytes"] and hashlib.sha256(raw).hexdigest() == expected["raw_sha256"],
            "Public raw size or SHA-256 differs")
    git_sha = hashlib.sha1(b"blob " + str(len(raw)).encode("ascii") + b"\0" + raw).hexdigest()
    require(git_sha == fixture["git_blob_sha1"], "Public Git blob SHA-1 differs")
    header = case["header"]["observation"]
    require(case["header"]["returncode"] == 0 and header["status"] == "DIAGNOSTIC_HEADER_PREFIX_OBSERVED",
            "Pinned C++ header observation did not succeed")
    framing = header["chunk_frames"]
    frames, container = framing["frames"], framing["container_span"]
    require(len(frames) == 11 and container["offset"] == header["compressed_offset"] - 4 and
            container["bytes"] == len(raw) - container["offset"], "Pinned C++ container span differs")
    cursor, total = container["offset"], 0
    decoder, output = zlib.decompressobj(), bytearray()
    for frame in frames:
        require(frame["header"] == {"offset": cursor, "bytes": 4}, "Frame header is not consecutive")
        begin, size = frame["payload"]["offset"], frame["payload"]["bytes"]
        require(begin == cursor + 4 and 0 < size <= 65536 and size <= len(raw) - begin and
                int.from_bytes(raw[cursor:begin], "little") == size, "C++ frame payload differs from raw length word")
        remaining = expected["inflated_bytes"] + 1 - len(output)
        require(remaining > 0, "Inflated byte budget exhausted")
        output.extend(decoder.decompress(raw[begin:begin + size], remaining))
        require(len(output) <= expected["inflated_bytes"] and not decoder.unconsumed_tail and not decoder.unused_data,
                "Declared frame decompression exceeded its strict bound")
        cursor, total = begin + size, total + size
    require(cursor == len(raw) and total == framing["total_payload_bytes"] and decoder.eof is False,
            "Declared frame coverage or retained nonfinal codec observation differs")
    require(len(output) == expected["inflated_bytes"] and hashlib.sha256(output).hexdigest() == expected["inflated_sha256"],
            "Inflated size or SHA-256 differs")
    return bytes(output), {"fixture": fixture, "raw_bytes": len(raw), "raw_sha256": expected["raw_sha256"],
        "git_blob_sha1": git_sha, "inflated_bytes": len(output), "inflated_sha256": expected["inflated_sha256"],
        "authenticated_cpp_frame_count": 11, "compressed_payload_bytes": total, "zlib_eof": False,
        "decoder_reset_flush_or_retry_used": False, "raw_inflated_or_database_saved": False}


def native_json(payload):
    value = json.loads(payload.decode("utf-8-sig"))
    require(isinstance(value, dict) and value.get("schema") == "zerosis.retail.body_import_test.v1" and
            value.get("status") == "PASS_RETAIL_BODY_IMPORT_COMPONENT", "Native component schema or status differs")

    def visit(item, depth=0):
        require(depth <= 16, "Native JSON is too deeply nested")
        if isinstance(item, str):
            require(len(item) <= 4096, "Native JSON contains a payload-sized string")
        elif isinstance(item, list):
            require(len(item) <= 256, "Native JSON contains a payload-sized array")
            for child in item:
                visit(child, depth + 1)
        elif isinstance(item, dict):
            require(len(item) <= 128, "Native JSON object exceeds its bound")
            for child in item.values():
                visit(child, depth + 1)
    visit(value)
    require(all(value.get(name) is False for name in FALSE_FLAGS), "Native component exceeded its execution or approval scope")
    require(value.get("input_bytes_unchanged") is True and value.get("input_files_unchanged") is True and
            type(value.get("checks")) is int and value["checks"] > 0, "Native preservation checks differ")
    return value


def same_structure(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(same_structure(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(same_structure(a, b) for a, b in zip(left, right))
    return left == right


def run_once(g, command, data, root, environment, prefix):
    timed_out = False
    try:
        run = subprocess.run(command, cwd=root, env=environment, input=data, capture_output=True, timeout=60,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        stdout, stderr, code = run.stdout, run.stderr, run.returncode
    except subprocess.TimeoutExpired as error:
        stdout, stderr, code = error.stdout or b"", error.stderr or b"", None
        timed_out = True
    stdout_path, stderr_path, process_path = [STAGE / (prefix + suffix)
        for suffix in (".stdout.log", ".stderr.log", ".process.json")]
    g.write_text(stdout_path, stdout[:128 * 1024].decode("utf-8-sig", errors="replace"), 384 * 1024)
    g.write_text(stderr_path, stderr[:16 * 1024].decode("utf-8", errors="replace"), 48 * 1024)
    g.write_json(process_path, {"command": list(command), "returncode": code, "timed_out": timed_out,
        "stdout_bytes": len(stdout), "stderr_bytes": len(stderr),
        "stdout_truncated": len(stdout) > 128 * 1024, "stderr_truncated": len(stderr) > 16 * 1024})
    require(not timed_out and code == 0 and len(stdout) <= 128 * 1024 and len(stderr) <= 16 * 1024,
            "Inspect the preserved native child logs")
    return native_json(stdout), {name: g.artifact(path) for name, path in
        (("stdout", stdout_path), ("stderr", stderr_path), ("process", process_path))}


def main():
    require(os.name == "nt" and len(sys.argv) == 1 and not sys.flags.optimize, "Require Windows and no runner arguments")
    require(len(SOURCE_SHA) == 64, "Test source has not been frozen")
    sys.dont_write_bytecode = True
    for name, digest in PINS.items():
        module_bytes(PROJECT / "tools" / (name + ".py"), digest)
    modules = {name: importlib.import_module(name) for name in PINS}
    require(all(Path(module.__file__).absolute() == PROJECT / "tools" / (name + ".py")
                for name, module in modules.items()), "Imported helper path differs")
    g, h, n = [modules[name] for name in ("probe_public_retail_save", "verify_retail_save_header", "native_build")]
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"warm".decode(encoding)
    post_pin, public_pin, budget_pin = g.artifact(POST), g.artifact(PUBLIC), g.artifact(BUDGET)
    require(post_pin["sha256"] == POST_SHA and public_pin["sha256"] == PUBLIC_SHA and
            budget_pin["sha256"] == BUDGET_SHA, "Frozen publication or full-wire reference SHA differs")
    post, public, budget = g.read_json(POST), g.read_json(PUBLIC), g.read_json(BUDGET)
    require(post["runtime_hold_unchanged"] is True and post["default_provider_unchanged"] is True and
            post["general_import_adapter_implemented"] is False, "Previous publication scope differs")
    frozen = pinned_rows(g, post["protected_files"], 45) + pinned_rows(g, post["source_contract_inputs"], 14)
    frozen += pinned_rows(g, post["source_and_proof_files"], 24)
    source_pin, header_pin = g.artifact(SOURCE), g.artifact(IMPORT_HEADER)
    require(source_pin["sha256"] == SOURCE_SHA and header_pin["sha256"] == IMPORT_HEADER_SHA,
            "Frozen component source SHA differs")
    headers = g.host_headers(SOURCE, PROJECT)
    require(IMPORT_HEADER in headers, "Production import helper is absent from the portable include closure")
    inputs = unique_rows(g, frozen + [post_pin, public_pin, budget_pin, source_pin, g.artifact(Path(__file__).absolute())] +
        [g.artifact(path) for path in headers] + [g.artifact(PROJECT / "tools" / (name + ".py")) for name in PINS])
    compiler = g.artifact(h.COMPILER)
    require(compiler["sha256"] == h.COMPILER_SHA, "Reviewed compiler SHA differs")
    fingerprint = g.identity({"schema": "zerosis.retail.body_import.identity.v1", "inputs": inputs, "compiler": compiler})
    parent = g.ordinary(PROJECT / "Build/RetailBodyImport")
    stage = g.ordinary(STAGE)
    parent.mkdir(parents=True, exist_ok=True); stage.mkdir(parents=True, exist_ok=True)
    root, evidence = g.ordinary(parent / fingerprint), g.ordinary(stage / ("compile_" + fingerprint))
    result_path, started_path, failed_path = [stage / name for name in ("result.json", "started.json", "failed_attempt.json")]
    require(not any(path.exists() for path in (root, evidence, result_path, started_path, failed_path)),
            "Inspect the retained previous body-import attempt before retrying")
    require(isinstance(public["cases"], list) and len(public["cases"]) == 2 and
            [case["fixture"]["id"] for case in public["cases"]] == list(EXPECTED), "Pinned public fixture set differs")
    jpl_cases = [case for case in budget["cases"] if case["name"] == "jpl_explicit_budget"]
    require(len(jpl_cases) == 1 and budget["fixture"]["id"] == "jpl_before" and
            budget["inflated_sha256"] == EXPECTED["jpl_before"]["inflated_sha256"], "Full JPL reference differs")
    references = {"jpl_before": jpl_cases[0]["observation"],
                  "rivar_settler12": public["cases"][1]["wire"]["observation"]}
    for reference in references.values():
        require(reference["status"] == "DIAGNOSTIC_SEQUENCE_OBSERVED" and
                reference["teams_completed"] == reference["players_completed"] == 64 and
                reference["declared_sequence_has_zero_remainder"] is True,
                "Structural reference is not the complete declared wire sequence")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
        urllib.request.HTTPSHandler(context=ssl.create_default_context()), g.NoRedirect())
    prepared = [framed_input(g, case, EXPECTED[case["fixture"]["id"]], opener) for case in public["cases"]]
    g.unchanged(inputs + [compiler])
    compile_command = (str(h.COMPILER), "@" + str(root / "compile.rsp"), "/link", "/MACHINE:X64",
        "/INCREMENTAL:NO", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF")
    env_command = ("cmd.exe", "/d", "/c", str(root / "read_build_environment.cmd"))
    executable = str(root / "RetailPublicProbe.exe")
    commands = [(executable, "--self-test")]
    commands += [(executable, "--public", "5", "4", "6", str(len(data)), str(EXPECTED[meta["fixture"]["id"]]["budget"]))
        for data, meta in prepared]
    writable = [root / name for name in ("RetailPublicProbe.exe", "retail_public_probe.obj", "compile.rsp",
        "dependencies.json", "read_build_environment.cmd")]
    writable += [evidence / name for name in ("build_started.json", "compile.log", "build_result.json", "failed_attempt.json")]
    writable += [result_path, started_path, failed_path]
    for prefix in ("self", "public_0", "public_1"):
        writable += [stage / (prefix + suffix) for suffix in (".stdout.log", ".stderr.log", ".process.json")]
    require(not any(path.exists() for path in writable), "An output from an unreviewed previous attempt already exists")
    guard = g.OfflineGuard(commands=[env_command, compile_command, *commands], directory=root,
        readable=[Path(row["path"]) for row in inputs + [compiler]], writable=writable, directories=[root, evidence])
    sys.addaudithook(guard.audit)
    try:
        g.write_json(started_path, {"schema": "zerosis.retail.body_import.started.v1", "fingerprint": fingerprint,
            "inputs": inputs, "public_inputs": [meta for _, meta in prepared],
            "commands": [env_command, compile_command, *commands], "sdk_or_host_or_game_executed": False})
        build, environment = g.ensure_build(project=PROJECT, root=root, evidence=evidence, source=SOURCE,
            headers=headers, inputs=inputs, compiler=compiler, compiler_path=h.COMPILER, vs=h.VS,
            command=compile_command, environment_for=n.environment_for, pe_imports=h.pe_imports,
            guard=guard, fingerprint=fingerprint)
        self_test, self_logs = run_once(g, commands[0], b"", root, environment, "self")
        require(self_test["mode"] == "self-test" and self_test["synthetic_operation_cases"] >= 20 and
                self_test["raw_boolean_cases"] >= 256 and self_test["truncations"] > 0 and
                self_test["directed_corruptions"] > 0, "Focused component coverage differs")
        cases = []
        for index, (data, meta) in enumerate(prepared):
            native, logs = run_once(g, commands[index + 1], data, root, environment, "public_" + str(index))
            expected, observed = EXPECTED[meta["fixture"]["id"]], native["public"]
            require(native["mode"] == "public" and observed["input_bytes"] == len(data) and
                    [observed[name] for name in ("awards", "grand", "projects")] == [5, 4, 6] and
                    observed["maximum_input_bytes"] == len(data) and observed["maximum_total_records"] == expected["budget"],
                    "Public argument echo differs")
            require(observed["team_count"] == observed["player_count"] == 64 and
                    observed["array_records"] == expected["records"] and observed["next_inflated_offset"] == len(data) and
                    observed["following_bytes"] == 0 and observed["canonical_body_wire_framed"] is True and
                    observed["edit_count"] == len(expected["edits"]) and observed["edits"] == expected["edits"],
                    "Public canonical wire or identified edits differ")
            reference = references[meta["fixture"]["id"]]
            require(all(name in observed["wire"] and
                        same_structure(observed["wire"][name], reference[name]) for name in WIRE_GROUPS),
                    "Public intermediate structure differs from its pinned full-wire reference")
            require(hashlib.sha256(data).hexdigest() == meta["inflated_sha256"], "Original RAM input changed")
            cases.append({**meta, "observation": native, **logs,
                "structural_reference": budget_pin if meta["fixture"]["id"] == "jpl_before" else public_pin,
                "structural_comparison": {name: True for name in WIRE_GROUPS}})
        g.unchanged(inputs + [compiler] + list(build["artifacts"].values()))
        require(not guard.denied and guard.calls == [list(command) for command in (env_command, compile_command, *commands)],
                "Offline guard observed missing, repeated or forbidden operations")
        report = {"schema": "zerosis.retail.body_import.component.v1", "status": "PASS_PORTABLE_RETAIL_BODY_IMPORT_COMPONENT",
            "utc": datetime.now(timezone.utc).isoformat(), "inputs": inputs, "previous_publication": post_pin,
            "frozen_previous_counts": {"protected": 45, "source_contracts": 14, "source_and_proof": 24},
            "build_report": g.artifact(evidence / "build_result.json"), "self_test": self_test,
            "self_logs": self_logs, "cases": cases, "child_commands": guard.calls,
            "forbidden_access_attempts": guard.denied, "retired_intermediates": build["retired_intermediates"],
            "retired_logical_bytes": build["retired_logical_bytes"], "raw_inflated_or_database_saved": False,
            "actual_import_entrypoint_implemented": False, "sdk_restore_performed": False,
            "sdk_or_host_or_hwnd_or_original_game_executed": False, "user_game_files_accessed": False,
            "producer_contract_verified": False, "ruleset_compatibility_verified": False,
            "complete_save_verified": False, "restore_approved": False, "full_engine_goal_complete": False,
            "whole_project_storage_rescanned": False}
        g.write_json(result_path, report)
        print(json.dumps({"status": report["status"], "report": g.artifact(result_path),
            "retired_logical_bytes": build["retired_logical_bytes"]}))
        return 0
    except BaseException as error:
        if not failed_path.exists():
            g.write_json(failed_path, {"status": "FAILED_PORTABLE_BODY_IMPORT_COMPONENT", "error": type(error).__name__ + ": " + str(error),
                "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
                "raw_inflated_or_database_saved": False, "sdk_or_host_or_game_executed": False,
                "actual_import_entrypoint_implemented": False, "sdk_restore_performed": False,
                "restore_approved": False, "full_engine_goal_complete": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
