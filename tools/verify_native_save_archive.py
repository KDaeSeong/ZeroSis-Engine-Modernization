"""Build and run isolated native save archive and filesystem transaction tests."""
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

from collect_baseline import PROJECT
from native_build import environment_for, run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


SOURCE = PROJECT / "Tests/native_save_archive.cpp"
IMPLEMENTATION = PROJECT / "Source/Host/NativeSaveArchive.h"
HOST_INCLUDE = PROJECT / "Source/Host"
PORTING_INCLUDE = PROJECT / "Source/Porting"
SDK = PROJECT / "Source/SDK_BNW_x64"
OUTPUT = PROJECT / "Build/NativeSaveArchive"
EVIDENCE = PROJECT / "evidence/native_save_archive"
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


def compile_and_run(optimization, flavor):
    directory = unique_directory(OUTPUT / flavor)
    environment, compiler = environment_for(
        Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"),
        "x64",
        directory,
    )
    environment["VSLANG"] = "1033"
    executable = directory / "NativeSaveArchive.exe"
    dependencies = directory / "dependencies.json"
    response = directory / "compile.rsp"
    data_directory = directory / "transaction-data"
    data_directory.mkdir()
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
    flags.extend([f'/I"{HOST_INCLUDE}"', f'/I"{PORTING_INCLUDE}"'])
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
        ],
        cwd=directory,
        env=environment,
        timeout=180,
    )
    build_output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    build_log = directory / "build.log"
    build_log.write_text(build_output, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", build_output, re.I):
        raise RuntimeError(f"{flavor} compile failed; see {build_log}\n{build_output[-6000:]}")

    dependency_data = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
    if Path(dependency_data["Source"]).resolve() != SOURCE.resolve():
        raise RuntimeError(f"{flavor} compiled an unexpected source")
    inputs = [Path(item) for item in [dependency_data["Source"], *dependency_data["Includes"]]]
    for required in (IMPLEMENTATION, HOST_INCLUDE / "HostFiles.h"):
        if not any(path.resolve() == required.resolve() for path in inputs):
            raise RuntimeError(f"{flavor} did not consume {required.name}")
    enum_headers = [path for path in inputs if path.name.lower() == "cvenums.h"]
    if not enum_headers:
        raise RuntimeError(f"{flavor} did not consume the SDK enum declarations")

    execution = run(
        [executable, data_directory],
        cwd=directory,
        env=environment,
        timeout=45,
    )
    transcript = (execution.stdout + execution.stderr).decode("utf-8", errors="replace")
    transcript = transcript.replace("\r\n", "\n").replace("\r", "\n")
    execution_log = directory / "execution.log"
    execution_log.write_text(transcript, encoding="utf-8")
    match = re.search(r"^NATIVE_SAVE_ARCHIVE_PASS checks=(\d+) GAMECORE_LOADED=false$", transcript, re.M)
    if execution.returncode or not match or int(match.group(1)) < 20:
        raise RuntimeError(f"{flavor} archive test failed; see {execution_log}\n{transcript[-5000:]}")

    archive = data_directory / "save.bin"
    if not archive.is_file():
        raise RuntimeError(f"{flavor} did not leave the committed test archive")
    return {
        "flavor": flavor,
        "optimization": optimization,
        "run_directory": str(directory),
        "data_directory": str(data_directory),
        "executable": artifact(executable),
        "compiler": artifact(Path(compiler)),
        "response": artifact(response),
        "dependency_report": artifact(dependencies),
        "build_log": artifact(build_log),
        "execution_log": artifact(execution_log),
        "compiler_input_count": len(inputs),
        "compiler_inputs": [artifact(path) for path in inputs],
        "committed_archive": artifact(archive),
        "checks": int(match.group(1)),
        "gamecore_loaded": False,
    }


def main():
    for path in (SOURCE, IMPLEMENTATION, Path(__file__)):
        path.read_bytes().decode("ascii")
    runs = [compile_and_run("/O2", "optimized"), compile_and_run("/Od", "debug")]
    if runs[0]["checks"] != runs[1]["checks"]:
        raise RuntimeError("Optimized and debug archive check counts differ")
    report = {
        "status": "NATIVE_SAVE_ARCHIVE_NATIVE_PASS",
        "builder": artifact(Path(__file__).resolve()),
        "test_source": artifact(SOURCE),
        "implementation_header": artifact(IMPLEMENTATION),
        "runs": runs,
        "native_checks": sum(row["checks"] for row in runs),
        "sdk_or_game_dll_loaded": False,
        "scope": "SDK_BACKED_ARCHIVE_CODEC_AND_WINDOWS_ATOMIC_FILE_TRANSACTIONS",
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
                "sdk_or_game_dll_loaded": False,
            }
        )
    )


if __name__ == "__main__":
    main()
