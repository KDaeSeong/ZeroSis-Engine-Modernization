"""Compile and run the portable Unit GreatWork save preflight policy only.

The production SDK source is pinned as provenance, never linked into this test.
Database behavior and actual GameCore saving require separate runtime proof.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess

PROJECT = Path(__file__).absolute().parents[1]


def main() -> int:
    if len(sys.argv) != 1 or os.name != "nt" or sys.flags.optimize:
        raise RuntimeError("Require the Windows interpreter without extra arguments")
    helper = PROJECT / "tools/trace_public_retail_map.py"
    for part in (helper, *helper.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Pinned helper has a reparse parent")
    if helper.stat().st_size > 128 * 1024 or hashlib.sha256(helper.read_bytes()).hexdigest() != \
            "7f6a52d43f5af38057d3b0cb1bdb08ecd1a28f6da78d510640195d55a087462a":
        raise RuntimeError("Reviewed helper changed before import")
    import trace_public_retail_map as trace
    if Path(trace.__file__).absolute() != helper:
        raise RuntimeError("Pinned helper came from a different path")
    generic_path = PROJECT / "tools/probe_public_retail_save.py"
    trace.pinned_read(generic_path,
        "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962", 128 * 1024)
    case = trace.CASES["jpl_before"]
    original = PROJECT / "evidence/retail_save_container/players/probes" / case["report"]
    prior = json.loads(trace.pinned_read(original, case["report_sha256"], 256 * 1024).decode("utf-8-sig"))
    for name in ("verify_retail_save_header.py", "native_build.py", "collect_baseline.py"):
        rows = [row for row in prior["inputs"] if Path(row["path"]).absolute() == PROJECT / "tools" / name]
        if len(rows) != 1:
            raise RuntimeError("Missing original compiler-helper pin")
        trace.pinned_read(PROJECT / "tools" / name, rows[0]["sha256"], 2 * 1024 * 1024)
    import probe_public_retail_save as g
    import verify_retail_save_header as h
    import native_build as n
    import collect_baseline as baseline
    for module in (g, h, n, baseline):
        g.require(Path(module.__file__).absolute() == PROJECT / "tools" / (module.__name__ + ".py"),
                  "Compiler helper was imported from a different path")
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"".decode(encoding)
    source = g.ordinary(PROJECT / "Tests/unit_great_work_save.cpp", file=True)
    header = g.ordinary(PROJECT / "Source/Serialization/UnitGreatWorkSave.h", file=True)
    sdk_source = g.ordinary(PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvUnit.cpp", file=True)
    helpers = ("verify_unit_great_work_save.py", "trace_public_retail_map.py", "probe_public_retail_save.py",
               "verify_retail_save_header.py", "native_build.py", "collect_baseline.py")
    inputs = [g.artifact(path) for path in
              (source, header, sdk_source, *(PROJECT / "tools" / name for name in helpers))]
    compiler_path = g.ordinary(h.COMPILER, file=True)
    compiler = g.artifact(compiler_path)
    g.require(compiler["sha256"] == h.COMPILER_SHA, "Reviewed compiler changed")
    fingerprint = g.identity({"schema": "zerosis.unit_great_work_policy.build.v1",
                              "inputs": inputs, "compiler": compiler})
    parent = g.ordinary(PROJECT / "Build/UnitGreatWorkSave")
    stage = g.ordinary(PROJECT / "evidence/serialization/unit_great_work_save")
    parent.mkdir(parents=True, exist_ok=True)
    g.require(stage.is_dir(), "Production source-change provenance is missing")
    root = g.ordinary(parent / fingerprint)
    evidence = g.ordinary(stage / ("compile_" + fingerprint))
    results = g.ordinary(stage / ("test_" + fingerprint))
    g.require(not root.exists() and not evidence.exists() and not results.exists(),
              "Inspect the existing exact attempt instead of overwriting it")
    compile_command = (str(compiler_path), "@" + str(root / "compile.rsp"), "/link", "/MACHINE:X64",
                       "/INCREMENTAL:NO", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF")
    environment_command = ("cmd.exe", "/d", "/c", str(root / "read_build_environment.cmd"))
    test_command = (str(root / "RetailPublicProbe.exe"),)
    outputs = [root / name for name in ("RetailPublicProbe.exe", "retail_public_probe.obj", "compile.rsp",
                                        "dependencies.json", "read_build_environment.cmd")]
    outputs += [evidence / name for name in ("build_started.json", "compile.log", "build_result.json", "failed_attempt.json")]
    outputs += [results / name for name in ("test.json", "stdout.log", "stderr.log", "process_result.json",
                                           "result.json", "failed_attempt.json")]
    guard = g.OfflineGuard(commands=[environment_command, compile_command, test_command], directory=root,
        readable=[Path(row["path"]) for row in inputs + [compiler]], writable=outputs,
        directories=[root, evidence, results])
    sys.addaudithook(guard.audit)
    try:
        results.mkdir()
        build, environment = g.ensure_build(project=PROJECT, root=root, evidence=evidence, source=source,
            headers=[header], inputs=inputs, compiler=compiler, compiler_path=compiler_path, vs=h.VS,
            command=compile_command, environment_for=n.environment_for, pe_imports=h.pe_imports,
            guard=guard, fingerprint=fingerprint)
        outcome = subprocess.run(list(test_command), cwd=root, env=environment, capture_output=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        g.require(len(outcome.stdout) <= 64 * 1024 and len(outcome.stderr) <= 16 * 1024,
                  "Policy test exceeded its output budget")
        g.write_text(results / "stdout.log", outcome.stdout.decode("utf-8-sig", errors="replace"), 64 * 1024)
        g.write_text(results / "stderr.log", outcome.stderr.decode("utf-8", errors="replace"), 32 * 1024)
        g.write_json(results / "process_result.json", {"returncode": outcome.returncode,
            "stdout_bytes": len(outcome.stdout), "stderr_bytes": len(outcome.stderr),
            "stdout": g.artifact(results / "stdout.log"), "stderr": g.artifact(results / "stderr.log"),
            "production_unit_write_executed": False, "database_or_sdk_code_executed": False})
        g.require(outcome.returncode == 0, "Policy test failed; inspect the retained process result and bounded logs")
        test = json.loads(outcome.stdout.decode("utf-8-sig"))
        g.require(test.get("status") == "PASS_UNIT_GREAT_WORK_SAVE_POLICY" and test.get("checks", 0) > 0,
                  "Missing policy test result")
        for name, minimum in (("no_work_cases", 1), ("valid_cases", 2), ("failure_cases", 7), ("literal_wire_suffixes", 2)):
            g.require(type(test.get(name)) is int and test[name] >= minimum, "Missing policy branch: " + name)
        for name in ("all_failure_body_calls_zero", "all_failure_persist_calls_zero", "unchanged_failure_destinations"):
            g.require(test.get(name) is True, "Failure isolation differs: " + name)
        g.require(test.get("database_sdk_or_gamecore_executed") is False and
                  test.get("full_engine_goal_complete") is False and all(test.get(name) is False for name in g.FLAGS_FALSE),
                  "Portable policy test exceeded its proof scope")
        g.write_json(results / "test.json", test)
        g.unchanged(inputs + [compiler] + list(build["artifacts"].values()))
        g.require(not guard.denied, "Offline guard rejected an operation")
        report = {"schema": "zerosis.unit_great_work_policy.component.v1", "status": "PASS_X64_UNIT_GREAT_WORK_SAVE_POLICY",
            "utc": datetime.now(timezone.utc).isoformat(), "mode": "O2", "build_fingerprint": fingerprint,
            "build_report": g.artifact(evidence / "build_result.json"), "inputs": inputs,
            "test": test, "test_log": g.artifact(results / "test.json"), "stderr_log": g.artifact(results / "stderr.log"),
            "process_result": g.artifact(results / "process_result.json"),
            "retired_intermediates": build["retired_intermediates"], "retired_logical_bytes": build["retired_logical_bytes"],
            "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
            "production_source_compiled_in_this_component": False, "database_or_sdk_code_executed": False,
            "real_save_file_preservation_verified": False, "game_user_saves_or_runtime_accessed": False,
            "runtime_updated": False, "retail_save_accepted": False, "full_engine_goal_complete": False}
        target = results / "result.json"
        g.write_json(target, report)
        print(json.dumps({"status": report["status"], "report": g.artifact(target), "test": test,
                          "retired_logical_bytes": report["retired_logical_bytes"]}))
        return 0
    except BaseException as error:
        if results.is_dir() and not (results / "failed_attempt.json").exists():
            g.write_json(results / "failed_attempt.json", {"status": "FAILED_UNIT_GREAT_WORK_SAVE_POLICY",
                "error": type(error).__name__ + ": " + str(error), "child_commands": guard.calls,
                "forbidden_access_attempts": guard.denied, "full_engine_goal_complete": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
