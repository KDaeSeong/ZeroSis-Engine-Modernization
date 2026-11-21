"""Trace a pinned public inflated Game/Map prefix without launching the game.

Reuse the existing checked headless build helpers and one bounded RAM decoder.
An observation, including a parser rejection, is never a save-load approval.
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
import stat
import subprocess

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/retail_save_container/map_trace"
FROZEN_HELPERS = {
    "probe_public_retail_save.py": "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "probe_public_retail_partial_inflate.py": "b132c5ada100172381be6f7e487f415c090d9771e75e16ea99dc7b264778ca98",
}
CASES = {
    "jpl_before": {
        "report": "jpl_before_8fe49418cee5e69aefac/probe_result.json",
        "report_sha256": "d90dce03c773034cc44afd311b0ae6a1b84b3afd6d3be48dc0dc2677e86966d7",
        "prefix_bytes": 19499847,
        "prefix_sha256": "d97a9b826e16f2e8c0056d8678b57e1f4ec3da87908237a0f70cf0eee981baaf",
    },
    "rivar_settler12": {
        "report": "rivar_settler12_c843200a41dec2c37123/probe_result.json",
        "report_sha256": "9348e988617a64d0bb72447b926550a88c8b242b0073fa92156416bcbee584f2",
        "prefix_bytes": 16696115,
        "prefix_sha256": "d5c651814103496a98c6bed08e86fd1b68bcb6ada053bc4873ce98d0b8d6f106",
    },
}
_MAIN_USED = False


def require(value, message: str) -> None:
    if not value:
        raise RuntimeError(message)


def pinned_read(path: Path, sha256: str, maximum: int) -> bytes:
    for parent in (path, *path.parents):
        info = parent.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "Pinned input has a reparse parent")
    before = path.lstat()
    require(stat.S_ISREG(before.st_mode) and before.st_size <= maximum, "Pinned input exceeds its file budget")
    data = path.read_bytes()
    after = path.lstat()
    require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and
            len(data) == before.st_size and hashlib.sha256(data).hexdigest() == sha256,
            "Pinned input changed before import")
    return data


def trace(argv: list[str] | None = None) -> dict:
    global _MAIN_USED
    require(not _MAIN_USED, "This trace entry point is one-use per interpreter")
    _MAIN_USED = True
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", required=True, choices=sorted(CASES))
    parser.add_argument("--awards", required=True, type=int)
    parser.add_argument("--boolean-encoding", required=True, choices=("canonical", "sdk-byte"))
    args = parser.parse_args(argv)
    require(os.name == "nt" and not sys.flags.optimize and args.awards == 5,
            "Require the reviewed Windows interpreter and unchanged explicit award width five")
    for name, sha in FROZEN_HELPERS.items():
        pinned_read(PROJECT / "tools" / name, sha, 128 * 1024)
    case = CASES[args.fixture]
    old_path = PROJECT / "evidence/retail_save_container/players/probes" / case["report"]
    prior = json.loads(pinned_read(old_path, case["report_sha256"], 256 * 1024).decode("utf-8-sig"))
    for name in ("verify_retail_save_header.py", "native_build.py", "collect_baseline.py"):
        pins = [row for row in prior["inputs"] if Path(row["path"]).absolute() == PROJECT / "tools" / name]
        require(len(pins) == 1, "A build helper lacks its original input identity")
        pinned_read(PROJECT / "tools" / name, pins[0]["sha256"], 2 * 1024 * 1024)
    import probe_public_retail_save as generic
    import probe_public_retail_partial_inflate as partial
    import verify_retail_save_header as header_tools
    import native_build
    import collect_baseline
    for module in (generic, partial, header_tools, native_build, collect_baseline):
        require(Path(module.__file__).absolute() == PROJECT / "tools" / (module.__name__ + ".py"),
                "Imported helper module is outside its pinned path")
    COMPILER, COMPILER_SHA, VS, pe_imports = (header_tools.COMPILER, header_tools.COMPILER_SHA,
                                            header_tools.VS, header_tools.pe_imports)
    environment_for = native_build.environment_for
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"".decode(encoding)
    source = generic.ordinary(PROJECT / "Tests/retail_map_trace.cpp", file=True)
    headers = generic.host_headers(source, PROJECT)
    helper_names = ("trace_public_retail_map.py", *FROZEN_HELPERS, "verify_retail_save_header.py",
                    "native_build.py", "collect_baseline.py")
    inputs = [generic.artifact(path) for path in
              (source, *headers, *(PROJECT / "tools" / name for name in helper_names))]
    compiler_path = generic.ordinary(COMPILER, file=True)
    compiler = generic.artifact(compiler_path)
    generic.require(compiler["sha256"] == COMPILER_SHA, "Reviewed compiler changed")
    fingerprint = generic.identity({"schema": "zerosis.map_trace.build_identity.v1",
                                    "inputs": inputs, "compiler": compiler})
    old_pin = generic.artifact(old_path)
    generic.require(old_pin["sha256"] == case["report_sha256"], "Original observation changed")
    old = generic.read_json(old_path)
    manifest = PROJECT / "evidence/retail_save_container/players/public_fixture_candidates.json"
    manifest_pin = generic.artifact(manifest)
    candidate = generic.select_fixture(generic.read_json(manifest), args.fixture)
    generic.require(old["fixture"] == candidate and old["candidate_manifest"] == manifest_pin and
                    old["status"] == "OBSERVED_PUBLIC_RETAIL_SAVE_PROBE" and old["guard_passed"] is True and
                    not old["forbidden_access_attempts"], "Original fixture identity or scope differs")
    header = old["native_results"][0]
    generic.require(header["mode"] == "header" and header["returncode"] == 0 and
                    header["observation"]["pregame_observed"] is True, "No successful original prefix observation")
    # Later Map-reader fixes must not invalidate the independent Header/Pregame
    # source of the body offset. Only these relevant source inputs are reused.
    header_inputs = [row for row in old["inputs"] if Path(row["path"]).name in
                     ("RetailSaveHeader.h", "RetailSavePregame.h")]
    generic.require(len(header_inputs) == 2, "Original Header/Pregame input pins are missing")
    generic.unchanged(header_inputs + [header["json_log"], header["stderr_log"]])
    generic.require(generic.read_json(header["json_log"]["path"]) == header["observation"],
                    "Original header log differs")
    offset = header["observation"]["compressed_offset"]
    raw, raw_pin = generic.fetch_fixture(candidate)
    generic.require(raw_pin == old["raw"], "Downloaded bytes differ from the original pinned fixture")
    protected = inputs + [compiler, manifest_pin, old_pin, *header_inputs, header["json_log"], header["stderr_log"]]
    generic.unchanged(protected)
    build_parent = generic.ordinary(PROJECT / "Build/RetailMapTrace")
    generic.ordinary(STAGE)
    build_parent.mkdir(parents=True, exist_ok=True)
    STAGE.mkdir(parents=True, exist_ok=True)
    root = generic.ordinary(build_parent / fingerprint)
    build_evidence = generic.ordinary(STAGE / ("compile_" + fingerprint))
    identity = generic.identity({"build": fingerprint, "fixture": candidate, "awards": args.awards,
                                 "boolean_encoding": args.boolean_encoding,
                                 "original_header": old_pin, "prefix_sha256": case["prefix_sha256"]})
    evidence = generic.ordinary(STAGE / (args.fixture + "_" + identity))
    generic.require(not root.exists() and not build_evidence.exists() or
                    root.is_dir() and (build_evidence / "build_result.json").is_file(),
                    "Inspect a partial trace build before retrying")
    generic.require(not evidence.exists(), "This exact public trace is one-use; inspect its retained result")
    reused = root.exists()
    exe = root / "RetailPublicProbe.exe"
    build_command = (str(compiler_path), "@" + str(root / "compile.rsp"), "/link", "/MACHINE:X64",
                     "/INCREMENTAL:NO", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF")
    env_command = ("cmd.exe", "/d", "/c", str(root / "read_build_environment.cmd"))
    command = (str(exe), "--awards", str(args.awards), "--boolean-encoding", args.boolean_encoding)
    build_files = [root / name for name in ("RetailPublicProbe.exe", "retail_public_probe.obj", "compile.rsp",
                                           "dependencies.json", "read_build_environment.cmd")]
    build_logs = [build_evidence / name for name in ("build_started.json", "compile.log", "build_result.json", "failed_attempt.json")]
    case_logs = [evidence / name for name in ("started.json", "chunks.json", "trace.json", "trace.stderr.log", "result.json", "failed_attempt.json")]
    guard = generic.OfflineGuard(commands=[env_command, build_command, command], directory=root,
        readable=[Path(row["path"]) for row in protected], writable=[*build_files, *build_logs, *case_logs],
        directories=[root, build_evidence, evidence])
    sys.addaudithook(guard.audit)
    try:
        evidence.mkdir()
        generic.write_json(evidence / "started.json", {"schema": "zerosis.map_trace.started.v1",
            "fixture": candidate, "raw": raw_pin, "original_header_report": old_pin,
            "inputs": inputs, "body_offset": offset, "awards": args.awards,
            "boolean_encoding": args.boolean_encoding, "build_fingerprint": fingerprint})
        build, environment = generic.ensure_build(project=PROJECT, root=root, evidence=build_evidence,
            source=source, headers=headers, inputs=inputs, compiler=compiler, compiler_path=compiler_path, vs=VS,
            command=build_command, environment_for=environment_for, pe_imports=pe_imports, guard=guard,
            fingerprint=fingerprint)
        prefix, decode = partial.emitted_prefix(raw, offset)
        generic.require(len(prefix) == case["prefix_bytes"] and
                        hashlib.sha256(prefix).hexdigest() == case["prefix_sha256"],
                        "One-pass emitted prefix differs from the earlier independent observation")
        generic.write_json(evidence / "chunks.json", decode)
        result = subprocess.run(list(command), cwd=root, env=environment, input=prefix, capture_output=True,
            timeout=180, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        generic.require(result.returncode in (0, 1) and len(result.stdout) <= 64 * 1024 and len(result.stderr) <= 16 * 1024,
                        "Native trace exceeded its bounded diagnostic protocol")
        observation = json.loads(result.stdout.decode("utf-8-sig"))
        generic.require(isinstance(observation, dict) and observation.get("schema") == "zerosis.retail.map_trace.v1" and
                        observation.get("mode") == "map_trace" and observation.get("stdin_read_complete") is True and
                        observation.get("input_bytes") == len(prefix) and
                        observation.get("profiles", {}).get("awards") == args.awards and
                        observation.get("profiles", {}).get("boolean_encoding") == args.boolean_encoding,
                        "Native trace input/schema/profile echo differs")
        for name in ("restore_approved", "complete_save_verified", "full_engine_goal_complete"):
            generic.require(observation.get(name) is False, "Native diagnostic exceeded its acceptance scope")
        generic.write_json(evidence / "trace.json", observation)
        generic.write_text(evidence / "trace.stderr.log", result.stderr.decode("utf-8", errors="replace"), 32 * 1024)
        generic.unchanged(protected + list(build["artifacts"].values()))
        generic.require(not guard.denied, "Trace offline guard rejected an operation")
        report = {"schema": "zerosis.public_map_trace.observation.v1", "status": "OBSERVED_PUBLIC_GAME_MAP_TRACE",
            "utc": datetime.now(timezone.utc).isoformat(), "fixture": candidate, "raw": raw_pin,
            "original_header_report": old_pin, "body_offset": offset, "prefix_bytes": len(prefix),
            "boolean_encoding": args.boolean_encoding,
            "prefix_sha256": case["prefix_sha256"], "prefix_explicitly_incomplete": True,
            "decode": {name: value for name, value in decode.items() if name != "chunks"},
            "chunks_log": generic.artifact(evidence / "chunks.json"), "native_observation": observation,
            "native_returncode": result.returncode, "native_log": generic.artifact(evidence / "trace.json"),
            "native_stderr": generic.artifact(evidence / "trace.stderr.log"), "inputs": inputs,
            "compile_report": generic.artifact(build_evidence / "build_result.json"), "build_reused": reused,
            "guard_passed": True, "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
            "raw_or_inflated_or_database_saved": False, "game_or_user_save_accessed": False,
            "sdk_restore_verified": False, "full_engine_goal_complete": False}
        target = evidence / "result.json"
        generic.write_json(target, report)
        return {"status": report["status"], "report": generic.artifact(target), "build_fingerprint": fingerprint,
                "build_reused": reused, "native_observation": observation,
                "retired_logical_bytes": 0 if reused else build["retired_logical_bytes"], "guard_passed": True}
    except BaseException as error:
        if evidence.is_dir() and not (evidence / "failed_attempt.json").exists():
            generic.write_json(evidence / "failed_attempt.json", {"status": "FAILED_PUBLIC_MAP_TRACE",
                "error": type(error).__name__ + ": " + str(error), "fixture": candidate,
                "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
                "raw_or_inflated_or_database_saved": False, "full_engine_goal_complete": False})
        raise


def main() -> int:
    try:
        print(json.dumps(trace(), ensure_ascii=True))
        return 0
    except Exception as error:
        print(json.dumps({"status": "FAILED_PUBLIC_MAP_TRACE", "error": type(error).__name__ + ": " + str(error)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
