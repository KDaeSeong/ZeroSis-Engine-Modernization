"""Compile and run the SDK-backed local game command component tests."""
import json
import re
from pathlib import Path

from collect_baseline import PROJECT
from native_build import environment_for, run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


SOURCE = PROJECT / "Tests/local_game_commands.cpp"
HOST_INCLUDE = PROJECT / "Source/Host"
PORTING_INCLUDE = PROJECT / "Source/Porting"
SDK = PROJECT / "Source/SDK_BNW_x64"
OUTPUT = PROJECT / "Build/LocalGameCommands"
EVIDENCE = PROJECT / "evidence/local_game_commands"
SDK_INCLUDES = [
    SDK / "CvGameCoreDLL_Expansion2",
    SDK / "CvGameCoreDLLUtil/include",
    SDK / "CvGameDatabase/include",
    SDK / "CvLocalization/include",
    SDK / "CvWorldBuilderMap/include",
    SDK / "FirePlace/include",
    SDK / "FirePlace/include/FireWorks",
    SDK / "ThirdPartyLibs/Lua51/include",
]


def compile_and_run(name, optimization):
    directory = OUTPUT / name
    environment, compiler = environment_for(
        Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"),
        "x64",
        directory,
    )
    environment["VSLANG"] = "1033"
    executable = directory / "LocalGameCommands.exe"
    dependencies = directory / "dependencies.json"
    response = directory / "compile.rsp"
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
        "/external:W0",
        "/DWIN32",
        "/DNDEBUG",
        "/DFINAL_RELEASE",
        "/D_CRT_SECURE_NO_WARNINGS",
        "/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS",
        "/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING",
    ]
    flags.extend(f'/external:I"{path}"' for path in SDK_INCLUDES)
    flags.extend(
        [
            f'/I"{HOST_INCLUDE}"',
            f'/I"{PORTING_INCLUDE}"',
        ]
    )
    flags.extend(
        [
            f'"{SOURCE}"',
            f'/Fo"{directory.as_posix()}/"',
            f'/Fe"{executable}"',
            f'/sourceDependencies "{dependencies}"',
        ]
    )
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    result = run(
        [compiler, f"@{response}", "/link", "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF"],
        cwd=directory,
        env=environment,
        timeout=180,
    )
    output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    log = directory / "build.log"
    log.write_text(output, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", output, re.I):
        raise RuntimeError(f"{name} compile failed; see {log}\n{output[-6000:]}")

    consumed = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
    if Path(consumed["Source"]).resolve() != SOURCE.resolve():
        raise RuntimeError(f"{name} compiled an unexpected source")
    inputs = [Path(item) for item in [consumed["Source"], *consumed["Includes"]]]
    if not any(path.resolve() == (HOST_INCLUDE / "LocalGameCommands.h").resolve() for path in inputs):
        raise RuntimeError(f"{name} did not consume LocalGameCommands.h")
    enum_headers = [path for path in inputs if path.name.lower() == "cvenums.h"]
    if not enum_headers or not any(path.resolve().is_relative_to(SDK.resolve()) for path in enum_headers):
        raise RuntimeError(f"{name} did not consume the SDK enum declarations")

    executed = run([executable], cwd=directory, env=environment, timeout=30)
    transcript = (executed.stdout + executed.stderr).decode("utf-8", errors="replace")
    transcript = transcript.replace("\r\n", "\n").replace("\r", "\n")
    run_log = directory / "execution.log"
    run_log.write_text(transcript, encoding="utf-8")
    match = re.search(r"^LOCAL_GAME_COMMANDS_PASS checks=(\d+) GAMECORE_LOADED=false$", transcript, re.M)
    if executed.returncode or not match or int(match.group(1)) < 20:
        raise RuntimeError(f"{name} component test failed; see {run_log}\n{transcript[-4000:]}")
    return {
        "name": name,
        "optimization": optimization,
        "executable": artifact(executable),
        "compiler": artifact(Path(compiler)),
        "response": artifact(response),
        "dependency_report": artifact(dependencies),
        "checks": int(match.group(1)),
        "build_log": artifact(log),
        "execution_log": artifact(run_log),
        "compiler_input_count": len(inputs),
        "compiler_inputs": [artifact(path) for path in inputs],
        "gamecore_loaded": False,
    }


def main():
    for path in (SOURCE, HOST_INCLUDE / "LocalGameCommands.h", Path(__file__)):
        path.read_bytes().decode("ascii")
    rows = [compile_and_run("optimized", "/O2"), compile_and_run("debug", "/Od")]
    if rows[0]["checks"] != rows[1]["checks"]:
        raise RuntimeError("Optimized and debug component check counts differ")
    report = {
        "status": "LOCAL_GAME_COMMANDS_NATIVE_PASS",
        "builder": artifact(Path(__file__).resolve()),
        "test_source": artifact(SOURCE),
        "implementation": artifact(HOST_INCLUDE / "LocalGameCommands.h"),
        "runs": rows,
        "native_checks": sum(row["checks"] for row in rows),
        "gamecore_loaded": False,
        "scope": "SDK_ENUM_TYPES_AND_LOCAL_TRANSPORT_COMPONENT_ONLY",
    }
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    destination = EVIDENCE / "conformance.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check_artifacts(report)
    check_artifacts(json.loads(destination.read_text(encoding="utf-8")))
    print(json.dumps({"status": report["status"], "native_checks": report["native_checks"],
                      "evidence": artifact(destination), "gamecore_loaded": False}))


if __name__ == "__main__":
    main()
