"""Build and run focused cross-standard C ABI boundary regression checks."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone


PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "Tests/explore_score_bridge.cpp"
BRIDGE_CPP = PROJECT / "Source/Concurrency/ExploreScoreBridge.cpp"
BRIDGE_H = PROJECT / "Source/Concurrency/ExploreScoreBridge.h"
SCORER_H = PROJECT / "Source/Concurrency/ExplorePlotScores.h"
BATCH_H = PROJECT / "Source/Concurrency/OrderedBatch.h"
BUILD_ROOT = PROJECT / "Build/ExploreScoreBridgeBoundary"
EVIDENCE_ROOT = PROJECT / "evidence/explore_score_bridge"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
SOURCE_INPUTS = {
    "Tests/explore_score_bridge.cpp": SOURCE,
    "Source/Concurrency/ExploreScoreBridge.cpp": BRIDGE_CPP,
    "Source/Concurrency/ExploreScoreBridge.h": BRIDGE_H,
    "Source/Concurrency/ExplorePlotScores.h": SCORER_H,
    "Source/Concurrency/OrderedBatch.h": BATCH_H,
    "tools/verify_explore_score_bridge.py": Path(__file__).resolve(),
}


def artifact(path: Path) -> dict[str, object]:
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def unique_directory(parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    while True:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        directory = parent / f"{stamp}_{uuid.uuid4().hex[:10]}"
        try:
            directory.mkdir()
            return directory
        except FileExistsError:
            continue


def initialize_msvc(directory: Path) -> tuple[Path, dict[str, str]]:
    setup = directory / "initialize_msvc.cmd"
    setup.write_text(
        "@echo off\n"
        f'call "{VS / "VC/Auxiliary/Build/vcvars64.bat"}" >nul\n'
        "if errorlevel 1 exit /b 1\n"
        "set\n",
        encoding="utf-8",
    )
    initialized = subprocess.run(
        ["cmd.exe", "/d", "/c", str(setup)], cwd=directory,
        capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60,
    )
    if initialized.returncode:
        raise RuntimeError(f"MSVC x64 setup failed: {setup}")
    environment = {key.upper(): value for key, value in os.environ.items()}
    paths: list[str] = []
    for line in initialized.stdout.decode("mbcs", errors="replace").splitlines():
        if "=" not in line or line.startswith("="):
            continue
        key, value = line.split("=", 1)
        environment[key.upper()] = value
        if key.upper() == "PATH":
            paths.append(value)
    environment["PATH"] = ";".join(dict.fromkeys(part for value in paths for part in value.split(";")))
    compiler = next((Path(part) / "cl.exe" for part in environment["PATH"].split(";")
                     if (Path(part) / "cl.exe").is_file()), None)
    if compiler is None:
        raise RuntimeError("MSVC compiler was not found after x64 setup")
    return compiler, environment


def compile_object(compiler: Path, environment: dict[str, str], directory: Path,
                   name: str, standard: str, source: Path,
                   include_directory: Path) -> tuple[Path, Path, Path]:
    obj = directory / f"{name}.obj"
    response = directory / f"{name}.rsp"
    response.write_text("\n".join([
        "/nologo", f"/std:{standard}", "/EHsc", "/W4", "/WX", "/O2", "/MD",
        "/fp:strict", "/utf-8", f'/I"{include_directory}"', "/c", f'"{source}"',
        f'/Fo"{obj}"',
    ]) + "\n", encoding="utf-8")
    result = subprocess.run([str(compiler), f"@{response}"], cwd=directory, env=environment,
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
    log = directory / f"{name}.build.log"
    log.write_bytes(result.stdout + result.stderr)
    log_text = log.read_bytes().decode("mbcs", errors="replace")
    if result.returncode or re.search(r"\bwarning\s+C\d+", log_text, re.I):
        raise RuntimeError(f"{name} C++ {standard} compilation failed; see {log}\n{log_text[-4000:]}")
    return obj, response, log


def build_and_run(source_hashes_before: dict[str, dict[str, object]]) -> dict[str, object]:
    directory = unique_directory(BUILD_ROOT)
    evidence = unique_directory(EVIDENCE_ROOT / "runs")
    frozen_root = directory / "frozen_inputs"
    frozen_files: dict[str, Path] = {}
    for relative, original in SOURCE_INPUTS.items():
        frozen = frozen_root / relative
        frozen.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(original, frozen)
        if artifact(frozen)["sha256"] != source_hashes_before[relative]["sha256"]:
            raise RuntimeError(f"Frozen source copy differs from pre-build hash: {relative}")
        frozen_files[relative] = frozen

    compiler, environment = initialize_msvc(directory)
    bridge_obj, bridge_rsp, bridge_log = compile_object(
        compiler, environment, directory, "bridge_cpp17", "c++17",
        frozen_files["Source/Concurrency/ExploreScoreBridge.cpp"],
        frozen_root / "Source/Concurrency",
    )
    test_obj, test_rsp, test_log = compile_object(
        compiler, environment, directory, "caller_cpp14", "c++14",
        frozen_files["Tests/explore_score_bridge.cpp"],
        frozen_root / "Source/Concurrency",
    )

    executable = directory / "ExploreScoreBridgeBoundary.exe"
    link_rsp = directory / "link.rsp"
    link_rsp.write_text("\n".join([
        "/nologo", f'"{bridge_obj}"', f'"{test_obj}"', f'/Fe"{executable}"',
        "/link", "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX",
    ]) + "\n", encoding="utf-8")
    linked = subprocess.run([str(compiler), f"@{link_rsp}"], cwd=directory, env=environment,
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
    link_log = directory / "link.build.log"
    link_log.write_bytes(linked.stdout + linked.stderr)
    link_text = link_log.read_bytes().decode("mbcs", errors="replace")
    if linked.returncode or re.search(r"\bwarning\s+C\d+", link_text, re.I):
        raise RuntimeError(f"C ABI boundary link failed; see {link_log}\n{link_text[-4000:]}")

    execution = subprocess.run([str(executable)], cwd=directory, env=environment,
                               capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
    transcript = (execution.stdout + execution.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
    execution_log = evidence / "execution.log"
    execution_log.write_text(transcript, encoding="utf-8")
    match = re.search(r"^EXPLORE_SCORE_BRIDGE_BOUNDARY_PASS checks=(\d+) GAMECORE_LOADED=false$",
                      transcript, re.M)
    if execution.returncode or not match:
        raise RuntimeError(f"Boundary regression failed; see {execution_log}\n{transcript[-3000:]}")

    return {
        "standard_bridge": "C++17", "standard_caller": "C++14",
        "run_directory": str(directory), "evidence_directory": str(evidence),
        "executable": artifact(executable), "compiler": artifact(compiler),
        "sources": [artifact(BRIDGE_CPP), artifact(SOURCE)],
        "headers": [artifact(BRIDGE_H), artifact(SCORER_H), artifact(BATCH_H)],
        "frozen_inputs": [artifact(frozen_files[key]) for key in sorted(frozen_files)],
        "responses": [artifact(bridge_rsp), artifact(test_rsp), artifact(link_rsp)],
        "build_logs": [artifact(bridge_log), artifact(test_log), artifact(link_log)],
        "execution_log": artifact(execution_log), "checks": int(match.group(1)),
        "gamecore_loaded": False,
    }


def main() -> None:
    if len(sys.argv) > 1 and Path(sys.argv[1]).resolve() != Path(sys.executable).resolve():
        raise RuntimeError("Invoke this verifier with the requested Python interpreter")
    for path in (SOURCE, BRIDGE_CPP, BRIDGE_H, SCORER_H, BATCH_H, Path(__file__).resolve()):
        path.read_bytes().decode("ascii")
    source_hashes_before = {relative: artifact(path) for relative, path in SOURCE_INPUTS.items()}
    run = build_and_run(source_hashes_before)
    source_hashes_after = {relative: artifact(path) for relative, path in SOURCE_INPUTS.items()}
    if source_hashes_before != source_hashes_after:
        raise RuntimeError("A source/header/verifier input changed during the frozen component build")
    report = {
        "status": "EXPLORE_SCORE_BRIDGE_C_ABI_BOUNDARY_PASS",
        "test_source": artifact(SOURCE), "verifier": artifact(Path(__file__).resolve()),
        "source_hashes_before": source_hashes_before,
        "source_hashes_after": source_hashes_after,
        "run": run, "checks": run["checks"], "gamecore_loaded": False,
        "sdk_dll_built": False, "sdk_runtime_launched": False,
        "scope": "ISOLATED_CPP14_CALLER_CPP17_BRIDGE_C_ABI_VALIDATION_FAILURE_ATOMICITY_AND_ORDERED_SCORES_ONLY",
        "metrics_scope": "IN_FLIGHT_SCORE_INVOCATIONS_AND_THREAD_CREATION_NOT_PHYSICAL_CPU_PROOF_OR_SPEEDUP",
    }
    destination = unique_directory(EVIDENCE_ROOT / "reports") / "conformance.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report["checks"],
                      "evidence": artifact(destination), "gamecore_loaded": False}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
