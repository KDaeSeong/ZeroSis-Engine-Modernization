"""Build and run only the portable exhaustive boolean-wire component tests."""
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
        raise RuntimeError("Require the reviewed Windows interpreter with no extra arguments")
    helper = PROJECT / "tools/trace_public_retail_map.py"
    for part in (helper, *helper.parents):
        info = part.lstat()
        if stat.S_ISLNK(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError("Trace-helper path contains a reparse point")
    if helper.stat().st_size > 128 * 1024 or hashlib.sha256(helper.read_bytes()).hexdigest() != \
            "7f6a52d43f5af38057d3b0cb1bdb08ecd1a28f6da78d510640195d55a087462a":
        raise RuntimeError("Reviewed trace helper changed before import")
    import trace_public_retail_map as trace_helper
    if Path(trace_helper.__file__).absolute() != helper:
        raise RuntimeError("Trace helper was imported from an unexpected path")
    CASES, FROZEN_HELPERS, pinned_read = trace_helper.CASES, trace_helper.FROZEN_HELPERS, trace_helper.pinned_read
    for name, sha in FROZEN_HELPERS.items():
        pinned_read(PROJECT / "tools" / name, sha, 128 * 1024)
    case = CASES["jpl_before"]
    original = PROJECT / "evidence/retail_save_container/players/probes" / case["report"]
    prior = json.loads(pinned_read(original, case["report_sha256"], 256 * 1024).decode("utf-8-sig"))
    for name in ("verify_retail_save_header.py", "native_build.py", "collect_baseline.py"):
        rows = [r for r in prior["inputs"] if Path(r["path"]).absolute() == PROJECT / "tools" / name]
        if len(rows) != 1:
            raise RuntimeError("Missing original build-helper pin")
        pinned_read(PROJECT / "tools" / name, rows[0]["sha256"], 2 * 1024 * 1024)
    import probe_public_retail_save as g
    import verify_retail_save_header as h
    import native_build as n
    import collect_baseline as baseline
    for module in (g, h, n, baseline):
        g.require(Path(module.__file__).absolute() == PROJECT / "tools" / (module.__name__ + ".py"),
                  "Build helper was imported from an unexpected path")
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"".decode(encoding)
    source = g.ordinary(PROJECT / "Tests/retail_bool_wire.cpp", file=True)
    headers = g.host_headers(source, PROJECT)
    helpers = ("verify_retail_bool_wire.py", "trace_public_retail_map.py", "probe_public_retail_save.py",
               "verify_retail_save_header.py", "native_build.py", "collect_baseline.py")
    inputs = [g.artifact(q) for q in (source, *headers, *(PROJECT / "tools" / name for name in helpers))]
    compiler_path = g.ordinary(h.COMPILER, file=True)
    compiler = g.artifact(compiler_path)
    g.require(compiler["sha256"] == h.COMPILER_SHA, "Reviewed compiler changed")
    fp = g.identity({"schema": "zerosis.boolean_wire.build_identity.v1", "inputs": inputs, "compiler": compiler})
    parent = g.ordinary(PROJECT / "Build/RetailBoolWire")
    stage = g.ordinary(PROJECT / "evidence/retail_save_container/map_trace")
    parent.mkdir(parents=True, exist_ok=True)
    g.require(stage.is_dir(), "Map-trace source provenance is missing")
    root = g.ordinary(parent / fp)
    evidence = g.ordinary(stage / ("bool_compile_" + fp))
    result_dir = g.ordinary(stage / ("bool_test_" + fp))
    g.require(not root.exists() and not evidence.exists() and not result_dir.exists(),
              "Inspect a previous boolean test attempt instead of overwriting it")
    compile_command = (str(compiler_path), "@" + str(root / "compile.rsp"), "/link", "/MACHINE:X64",
                       "/INCREMENTAL:NO", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF")
    environment_command = ("cmd.exe", "/d", "/c", str(root / "read_build_environment.cmd"))
    command = (str(root / "RetailPublicProbe.exe"),)
    outputs = [root / name for name in ("RetailPublicProbe.exe", "retail_public_probe.obj", "compile.rsp",
                                        "dependencies.json", "read_build_environment.cmd")]
    outputs += [evidence / name for name in ("build_started.json", "compile.log", "build_result.json", "failed_attempt.json")]
    outputs += [result_dir / name for name in ("test.json", "stderr.log", "result.json", "failed_attempt.json")]
    guard = g.OfflineGuard(commands=[environment_command, compile_command, command], directory=root,
        readable=[Path(r["path"]) for r in inputs + [compiler]], writable=outputs,
        directories=[root, evidence, result_dir])
    sys.addaudithook(guard.audit)
    try:
        result_dir.mkdir()
        build, environment = g.ensure_build(project=PROJECT, root=root, evidence=evidence, source=source,
            headers=headers, inputs=inputs, compiler=compiler, compiler_path=compiler_path, vs=h.VS,
            command=compile_command, environment_for=n.environment_for, pe_imports=h.pe_imports,
            guard=guard, fingerprint=fp)
        result = subprocess.run(list(command), cwd=root, env=environment, capture_output=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        g.require(result.returncode == 0 and len(result.stdout) <= 64 * 1024 and len(result.stderr) <= 16 * 1024,
                  "Boolean component tests failed or exceeded their output budget")
        test = json.loads(result.stdout.decode("utf-8-sig"))
        g.require(test.get("status") == "PASS_RETAIL_BOOL_WIRE_COMPONENT" and test.get("checks", 0) >= 1024,
                  "Missing exhaustive boolean-component proof")
        g.require(test.get("literal_byte_values") == 256 and test.get("canonical_accepted") == 2 and
                  test.get("canonical_rejected") == 254 and test.get("sdk_byte_accepted") == 256 and
                  test.get("unknown_profile_cases") == 3 and test.get("truncations", 0) >= 24 and
                  test.get("input_bytes_unchanged") is True and all(test.get(name) is False for name in g.FLAGS_FALSE),
                  "Boolean test coverage, byte preservation or scope differs")
        g.write_json(result_dir / "test.json", test)
        g.write_text(result_dir / "stderr.log", result.stderr.decode("utf-8", errors="replace"), 32 * 1024)
        g.unchanged(inputs + [compiler] + list(build["artifacts"].values()))
        g.require(not guard.denied, "Boolean test offline guard rejected an operation")
        report = {"schema": "zerosis.boolean_wire.component.v1", "status": "PASS_X64_BOOLEAN_WIRE_COMPONENT",
            "utc": datetime.now(timezone.utc).isoformat(), "mode": "O2", "build_fingerprint": fp,
            "build_report": g.artifact(evidence / "build_result.json"), "inputs": inputs,
            "test": test, "test_log": g.artifact(result_dir / "test.json"),
            "stderr_log": g.artifact(result_dir / "stderr.log"), "retired_intermediates": build["retired_intermediates"],
            "retired_logical_bytes": build["retired_logical_bytes"], "child_commands": guard.calls,
            "forbidden_access_attempts": guard.denied, "gamecore_or_sdk_code_executed": False,
            "user_game_or_saves_accessed": False, "runtime_updated": False,
            "retail_save_accepted": False, "full_engine_goal_complete": False}
        target = result_dir / "result.json"
        g.write_json(target, report)
        print(json.dumps({"status": report["status"], "report": g.artifact(target), "test": test,
                          "retired_logical_bytes": report["retired_logical_bytes"]}))
        return 0
    except BaseException as error:
        if result_dir.is_dir() and not (result_dir / "failed_attempt.json").exists():
            g.write_json(result_dir / "failed_attempt.json", {"status": "FAILED_BOOL_WIRE_COMPONENT",
                "error": type(error).__name__ + ": " + str(error), "child_commands": guard.calls,
                "forbidden_access_attempts": guard.denied, "full_engine_goal_complete": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
