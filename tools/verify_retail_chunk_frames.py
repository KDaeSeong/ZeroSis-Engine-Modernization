"""Compile and run focused portable length-prefix framing regressions only."""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import subprocess

PROJECT = Path(__file__).absolute().parents[1]
PINS = {
    "probe_public_retail_save": "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "verify_retail_save_header": "9bc62f6e200fbb470d516606aa845724426be42e5ee8bdd56f69f1126afcaa5f",
    "native_build": "c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21",
    "collect_baseline": "7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187",
}


def main():
    assert len(sys.argv) == 1 and os.name == "nt" and not sys.flags.optimize
    for name, expected in PINS.items():
        path = PROJECT / "tools" / (name + ".py")
        for part in (path, *path.parents):
            assert not part.lstat().st_file_attributes & 0x400
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected
    modules = {name: importlib.import_module(name) for name in PINS}
    for name, module in modules.items():
        assert Path(module.__file__).absolute() == PROJECT / "tools" / (name + ".py")
    g, h, n = [modules[name] for name in ("probe_public_retail_save", "verify_retail_save_header", "native_build")]
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"warm".decode(encoding)
    source = PROJECT / "Tests/retail_save_chunk_frames.cpp"
    headers = g.host_headers(source, PROJECT)
    assert PROJECT / "Source/Host/RetailSaveChunkFrames.h" in headers
    inputs = [g.artifact(path) for path in (source, *headers, Path(__file__).absolute(),
        *(PROJECT / "tools" / (name + ".py") for name in PINS))]
    compiler = g.artifact(h.COMPILER)
    assert compiler["sha256"] == h.COMPILER_SHA
    fingerprint = g.identity({"schema": "zerosis.chunk_frames.unit.identity.v1", "inputs": inputs, "compiler": compiler})
    parent = g.ordinary(PROJECT / "Build/RetailChunkFrames")
    stage = g.ordinary(PROJECT / "evidence/retail_save_container/map_trace/chunk_frames_component")
    parent.mkdir(parents=True, exist_ok=True); stage.mkdir(parents=True, exist_ok=True)
    root = g.ordinary(parent / fingerprint)
    evidence = g.ordinary(stage / ("compile_unit_" + fingerprint))
    results = g.ordinary(stage / ("test_" + fingerprint))
    assert not root.exists() and not evidence.exists() and not results.exists(), "Inspect the previous exact attempt"
    compile_command = (str(h.COMPILER), "@" + str(root / "compile.rsp"), "/link", "/MACHINE:X64",
        "/INCREMENTAL:NO", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF")
    env_command = ("cmd.exe", "/d", "/c", str(root / "read_build_environment.cmd"))
    test_command = (str(root / "RetailPublicProbe.exe"),)
    output = [root / name for name in ("RetailPublicProbe.exe", "retail_public_probe.obj", "compile.rsp",
        "dependencies.json", "read_build_environment.cmd")]
    output += [evidence / name for name in ("build_started.json", "compile.log", "build_result.json", "failed_attempt.json")]
    output += [results / name for name in ("stdout.log", "stderr.log", "process.json", "result.json", "failed_attempt.json")]
    guard = g.OfflineGuard(commands=[env_command, compile_command, test_command], directory=root,
        readable=[Path(row["path"]) for row in inputs + [compiler]], writable=output,
        directories=[root, evidence, results])
    sys.addaudithook(guard.audit)
    try:
        results.mkdir()
        build, environment = g.ensure_build(project=PROJECT, root=root, evidence=evidence, source=source,
            headers=headers, inputs=inputs, compiler=compiler, compiler_path=h.COMPILER, vs=h.VS,
            command=compile_command, environment_for=n.environment_for, pe_imports=h.pe_imports,
            guard=guard, fingerprint=fingerprint)
        run = subprocess.run(test_command, cwd=root, env=environment, capture_output=True, timeout=30,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        assert len(run.stdout) <= 64 * 1024 and len(run.stderr) <= 16 * 1024
        g.write_text(results / "stdout.log", run.stdout.decode("utf-8-sig", errors="replace"), 64 * 1024)
        g.write_text(results / "stderr.log", run.stderr.decode("utf-8", errors="replace"), 32 * 1024)
        g.write_json(results / "process.json", {"returncode": run.returncode,
            "stdout_bytes": len(run.stdout), "stderr_bytes": len(run.stderr)})
        assert run.returncode == 0, "Inspect the preserved native test output"
        test = json.loads(run.stdout.decode("utf-8-sig"))
        assert test["status"] == "PASS_RETAIL_CHUNK_FRAMES_COMPONENT" and test["checks"] > 0
        assert test["full_engine_goal_complete"] is False
        g.unchanged(inputs + [compiler] + list(build["artifacts"].values()))
        assert not guard.denied and len(guard.calls) == 3
        report = {"schema": "zerosis.retail.chunk_frames.component.v1", "status": "PASS_X64_LENGTH_PREFIX_FRAMING_COMPONENT",
            "utc": datetime.now(timezone.utc).isoformat(), "inputs": inputs,
            "build_report": g.artifact(evidence / "build_result.json"), "test": test,
            "stdout": g.artifact(results / "stdout.log"), "stderr": g.artifact(results / "stderr.log"),
            "child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
            "retired_intermediates": build["retired_intermediates"], "retired_logical_bytes": build["retired_logical_bytes"],
            "sdk_or_host_or_hwnd_or_game_executed": False, "user_game_files_accessed": False,
            "producer_contract_or_complete_save_verified": False, "full_engine_goal_complete": False}
        target = results / "result.json"
        g.write_json(target, report)
        print(json.dumps({"report": g.artifact(target), "status": report["status"], "checks": test["checks"],
            "retired_logical_bytes": build["retired_logical_bytes"]}))
        return 0
    except BaseException as error:
        if results.is_dir() and not (results / "failed_attempt.json").exists():
            g.write_json(results / "failed_attempt.json", {"status": "FAILED_CHUNK_FRAME_COMPONENT",
                "error": type(error).__name__ + ": " + str(error), "child_commands": guard.calls,
                "forbidden_access_attempts": guard.denied, "sdk_or_game_executed": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
