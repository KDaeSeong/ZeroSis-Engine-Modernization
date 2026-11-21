"""Build and run focused LocalTurnSignals lifecycle component tests."""
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

from collect_baseline import PROJECT
from native_build import environment_for, run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


SOURCE = PROJECT / "Tests/local_turn_signals.cpp"
IMPLEMENTATION = PROJECT / "Source/Host/LocalTurnSignals.h"
OUTPUT = PROJECT / "Build/LocalTurnSignals"
EVIDENCE = PROJECT / "evidence/local_turn_signals"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")


def unique_directory(parent):
    parent.mkdir(parents=True, exist_ok=True)
    while True:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = parent / f"{stamp}_{uuid.uuid4().hex[:10]}"
        try:
            target.mkdir()
            return target
        except FileExistsError:
            continue


def compile_and_run(flavor, optimization):
    directory = unique_directory(OUTPUT / flavor)
    environment, compiler = environment_for(VS, "x64", directory)
    environment["VSLANG"] = "1033"
    executable = directory / "LocalTurnSignals.exe"
    dependencies = directory / "dependencies.json"
    response = directory / "compile.rsp"
    link_map = directory / "LocalTurnSignals.map"
    flags = [
        "/nologo",
        "/std:c++14",
        "/EHsc",
        "/W4",
        "/WX",
        optimization,
        "/MD",
        "/fp:strict",
        "/source-charset:windows-1252",
        "/DWIN32",
        "/D_CRT_SECURE_NO_WARNINGS",
    ]
    flags.extend(
        [
            f'/I"{IMPLEMENTATION.parent}"',
            f'"{SOURCE}"',
            f'/Fo"{directory.as_posix()}/"',
            f'/Fe"{executable}"',
            f'/sourceDependencies "{dependencies}"',
        ]
    )
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    result = run(
        [
            compiler,
            f"@{response}",
            "/link",
            "/INCREMENTAL:NO",
            "/MACHINE:X64",
            "/Brepro",
            "/WX",
            "/OPT:REF",
            "/OPT:ICF",
            f"/MAP:{link_map}",
        ],
        cwd=directory,
        env=environment,
        timeout=120,
    )
    build_text = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    build_log = directory / "build.log"
    build_log.write_text(build_text, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", build_text, re.I):
        raise RuntimeError(f"{flavor} compile failed; see {build_log}\n{build_text[-5000:]}")

    dependency_data = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
    if Path(dependency_data["Source"]).resolve() != SOURCE.resolve():
        raise RuntimeError(f"{flavor} compiled an unexpected test source")
    inputs = [Path(item) for item in [dependency_data["Source"], *dependency_data["Includes"]]]
    if not any(path.resolve() == IMPLEMENTATION.resolve() for path in inputs):
        raise RuntimeError(f"{flavor} did not consume LocalTurnSignals.h")

    execution = run([executable], cwd=directory, env=environment, timeout=30)
    transcript = (execution.stdout + execution.stderr).decode("utf-8", errors="replace")
    transcript = transcript.replace("\r\n", "\n").replace("\r", "\n")
    execution_log = directory / "execution.log"
    execution_log.write_text(transcript, encoding="utf-8")
    match = re.search(r"^LOCAL_TURN_SIGNALS_PASS checks=(\d+) GAMECORE_LOADED=false$", transcript, re.M)
    if execution.returncode or not match or int(match.group(1)) < 20:
        raise RuntimeError(f"{flavor} component test failed; see {execution_log}\n{transcript[-3000:]}")

    return {
        "flavor": flavor,
        "optimization": optimization,
        "run_directory": str(directory),
        "executable": artifact(executable),
        "compiler": artifact(Path(compiler)),
        "response": artifact(response),
        "dependency_report": artifact(dependencies),
        "map": artifact(link_map),
        "build_log": artifact(build_log),
        "execution_log": artifact(execution_log),
        "compiler_input_count": len(inputs),
        "compiler_inputs": [artifact(path) for path in inputs],
        "checks": int(match.group(1)),
        "gamecore_loaded": False,
    }


def main():
    for path in (SOURCE, IMPLEMENTATION, Path(__file__).resolve()):
        path.read_bytes().decode("ascii")
    runs = [compile_and_run("optimized", "/O2"), compile_and_run("debug", "/Od")]
    if runs[0]["checks"] != runs[1]["checks"]:
        raise RuntimeError("Optimized and debug test counts differ")
    report = {
        "status": "LOCAL_TURN_SIGNALS_NATIVE_PASS",
        "builder": artifact(Path(__file__).resolve()),
        "test_source": artifact(SOURCE),
        "implementation_header": artifact(IMPLEMENTATION),
        "runs": runs,
        "native_checks": sum(row["checks"] for row in runs),
        "gamecore_loaded": False,
        "scope": "TURN_TAGS_LOCAL_PARTICIPANT_SESSION_IDENTITY_AND_CALLBACK_LIFETIME",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    destination = EVIDENCE / "conformance.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check_artifacts(report)
    check_artifacts(json.loads(destination.read_text(encoding="utf-8")))
    print(
        json.dumps(
            {
                "status": report["status"],
                "native_checks": report["native_checks"],
                "evidence": artifact(destination),
                "gamecore_loaded": False,
            }
        )
    )


if __name__ == "__main__":
    main()
