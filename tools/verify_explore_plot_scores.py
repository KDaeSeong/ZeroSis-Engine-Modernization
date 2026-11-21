"""Build and run the isolated ExplorePlotScores C++17 component tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "Tests/explore_plot_scores.cpp"
HEADER = PROJECT / "Source/Concurrency/ExplorePlotScores.h"
ORDERED_BATCH = PROJECT / "Source/Concurrency/OrderedBatch.h"
BUILD = PROJECT / "Build/ExplorePlotScores"
EVIDENCE = PROJECT / "evidence/explore_plot_scores"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")


def artifact(path: Path) -> dict:
    import hashlib

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return {"path": str(path), "sha256": digest, "size": path.stat().st_size}


def unique_directory(parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    while True:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = parent / f"{stamp}_{uuid.uuid4().hex[:10]}"
        try:
            target.mkdir()
            return target
        except FileExistsError:
            pass


def build_and_run(flavor: str, optimization: str) -> dict:
    directory = unique_directory(BUILD / flavor)
    evidence = unique_directory(EVIDENCE / flavor)
    setup = directory / "initialize_msvc.cmd"
    setup.write_text(
        '@echo off\n'
        f'call "{VS / "VC/Auxiliary/Build/vcvars64.bat"}" >nul\n'
        'if errorlevel 1 exit /b 1\n'
        'set\n', encoding="utf-8"
    )
    initialized = subprocess.run(
        ["cmd.exe", "/d", "/c", str(setup)], cwd=directory,
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60,
    )
    if initialized.returncode:
        raise RuntimeError(f"MSVC x64 setup failed: {setup}")
    env = {key.upper(): value for key, value in os.environ.items()}
    paths = []
    for line in initialized.stdout.decode("mbcs", errors="replace").splitlines():
        if "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            env[key.upper()] = value
            if key.upper() == "PATH":
                paths.append(value)
    env["PATH"] = ";".join(dict.fromkeys(part for value in paths for part in value.split(";")))
    compiler = next((Path(part) / "cl.exe" for part in env["PATH"].split(";")
                     if (Path(part) / "cl.exe").is_file()), None)
    if compiler is None:
        raise RuntimeError("MSVC compiler was not found after x64 setup")

    executable = directory / "ExplorePlotScores.exe"
    response = directory / "compile.rsp"
    flags = [
        "/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", optimization,
        "/MD", "/fp:strict", f'/I"{HEADER.parent}"', f'"{SOURCE}"',
        f'/Fo"{directory.as_posix()}/"', f'/Fe"{executable}"',
    ]
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    command = [str(compiler), f"@{response}", "/link", "/INCREMENTAL:NO", "/MACHINE:X64",
               "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF", f"/MAP:{directory / 'ExplorePlotScores.map'}"]
    result = subprocess.run(command, cwd=directory, env=env, capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
    build_text = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    build_log = evidence / "build.log"
    build_log.write_text(build_text, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", build_text, re.I):
        raise RuntimeError(f"{flavor} build failed; see {build_log}\n{build_text[-5000:]}")

    execution = subprocess.run([str(executable)], cwd=directory, env=env,
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
    transcript = (execution.stdout + execution.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
    execution_log = evidence / "execution.log"
    execution_log.write_text(transcript, encoding="utf-8")
    match = re.search(r"^EXPLORE_PLOT_SCORES_PASS checks=(\d+) GAMECORE_LOADED=false$", transcript, re.M)
    if execution.returncode or not match:
        raise RuntimeError(f"{flavor} tests failed; see {execution_log}\n{transcript[-3000:]}")
    return {
        "flavor": flavor, "optimization": optimization, "run_directory": str(directory),
        "evidence_directory": str(evidence), "executable": artifact(executable),
        "compiler": str(compiler), "response": artifact(response), "build_log": artifact(build_log),
        "execution_log": artifact(execution_log), "checks": int(match.group(1)),
        "gamecore_loaded": False,
    }


def main() -> None:
    if len(sys.argv) > 1 and Path(sys.argv[1]).resolve() != Path(sys.executable).resolve():
        raise RuntimeError("Invoke this verifier with the requested Python interpreter")
    for path in (SOURCE, HEADER, ORDERED_BATCH, Path(__file__).resolve()):
        path.read_bytes().decode("ascii")
    runs = [build_and_run("optimized", "/O2"), build_and_run("debug", "/Od")]
    if runs[0]["checks"] != runs[1]["checks"]:
        raise RuntimeError("Optimized and debug check counts differ")
    report = {
        "status": "EXPLORE_PLOT_SCORES_NATIVE_PASS",
        "test_source": artifact(SOURCE), "implementation_header": artifact(HEADER),
        "ordered_batch_header": artifact(ORDERED_BATCH), "runs": runs,
        "native_checks": sum(run["checks"] for run in runs), "gamecore_loaded": False,
        "scope": "PURE_RANGE_1_EXPLORE_PLOT_SCORING_AND_ORDERED_BATCH_COMPONENT_ONLY",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    destination = EVIDENCE / f"conformance_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{uuid.uuid4().hex[:8]}.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "native_checks": report["native_checks"],
                      "evidence": artifact(destination), "gamecore_loaded": False}))


if __name__ == "__main__":
    main()
