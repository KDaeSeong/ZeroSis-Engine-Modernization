"""Compile and exercise the native host's SDK TempHeap export and lifecycle."""
import json
from datetime import datetime, timezone
from pathlib import Path
import re
import uuid

from collect_baseline import PROJECT
from native_build import environment_for, run
from probe_world_builder import artifact
from temp_heap_evidence import validate as validate_temp_heap
from verify_world_builder_map_object import check_artifacts


SOURCE = PROJECT / "Tests/host_temp_heap.cpp"
IMPLEMENTATION = PROJECT / "Source/Host/HostTempHeap.h"
OUTPUT = PROJECT / "Build/HostTempHeap"
EVIDENCE = PROJECT / "evidence/host_temp_heap"
SDK = PROJECT / "Source/SDK_BNW_x64"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")


def unique_directory(parent):
    parent.mkdir(parents=True, exist_ok=True)
    while True:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        path = parent / f"{stamp}_{uuid.uuid4().hex[:10]}"
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue


def compile_and_run(build, providers, optimization, flavor):
    directory = unique_directory(OUTPUT / flavor)
    environment, compiler = environment_for(VS, "x64", directory)
    environment["VSLANG"] = "1033"
    executable = directory / "HostTempHeap.exe"
    dependencies = directory / "dependencies.json"
    response = directory / "compile.rsp"
    link_map = directory / "HostTempHeap.map"
    sdk_includes = [
        SDK / "CvGameCoreDLL_Expansion2",
        SDK / "CvGameCoreDLLUtil/include",
        SDK / "CvGameDatabase/include",
        SDK / "CvLocalization/include",
        SDK / "CvWorldBuilderMap/include",
        SDK / "FirePlace/include",
        SDK / "FirePlace/include/FireWorks",
        SDK / "ThirdPartyLibs/Lua51/include",
    ]
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
        "/DFXS_IS_DLL",
        "/DFINAL_RELEASE",
        "/D_CRT_SECURE_NO_WARNINGS",
        "/D_SECURE_SCL=0",
        "/D_HAS_ITERATOR_DEBUGGING=0",
        "/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS",
        "/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING",
    ]
    flags.extend(f'/external:I"{path}"' for path in sdk_includes)
    flags.extend(
        [
            f'/I"{PROJECT / "Source/Host"}"',
            f'/I"{PROJECT / "Source/Porting"}"',
            f'"{SOURCE}"',
            *[f'"{Path(item["path"])}"' for item in providers],
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
        timeout=180,
    )
    build_text = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    build_log = directory / "build.log"
    build_log.write_text(build_text, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", build_text, re.I):
        raise RuntimeError(f"{flavor} compile failed; see {build_log}\n{build_text[-6000:]}")

    dependency_data = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
    if Path(dependency_data["Source"]).resolve() != SOURCE.resolve():
        raise RuntimeError(f"{flavor} compiled an unexpected source")
    inputs = [Path(item) for item in [dependency_data["Source"], *dependency_data["Includes"]]]
    if not any(path.resolve() == IMPLEMENTATION.resolve() for path in inputs):
        raise RuntimeError(f"{flavor} did not consume HostTempHeap.h")

    dumpbin = Path(compiler).with_name("dumpbin.exe")
    export_result = run([dumpbin, "/exports", executable], cwd=directory, env=environment)
    export_text = (export_result.stdout + export_result.stderr).decode("mbcs", errors="replace")
    export_log = directory / "exports.log"
    export_log.write_text(export_text, encoding="utf-8")
    if export_result.returncode or not re.search(r"\bGetTempHeap\b", export_text):
        raise RuntimeError(f"{flavor} executable does not export GetTempHeap\n{export_text[-3000:]}")

    import_result = run([dumpbin, "/dependents", executable], cwd=directory, env=environment)
    import_text = (import_result.stdout + import_result.stderr).decode("mbcs", errors="replace")
    import_log = directory / "imports.log"
    import_log.write_text(import_text, encoding="utf-8")
    imports = re.findall(r"^\s+([^\s]+\.dll)\s*$", import_text, re.I | re.M)
    forbidden = ("cvgame", "lua51", "steam_api", "fireworks")
    if import_result.returncode or not imports or any(any(term in item.lower() for term in forbidden) for item in imports):
        raise RuntimeError(f"{flavor} executable has an invalid DLL dependency set\n{import_text[-3000:]}")

    executed = run([executable], cwd=directory, env=environment, timeout=45)
    transcript = (executed.stdout + executed.stderr).decode("utf-8", errors="replace")
    transcript = transcript.replace("\r\n", "\n").replace("\r", "\n")
    execution_log = directory / "execution.log"
    execution_log.write_text(transcript, encoding="utf-8")
    match = re.search(
        r"^HOST_TEMP_HEAP_PASS checks=(\d+) GETPROC_EXPORT=true PROVIDER_ROUNDTRIP=true GAMECORE_LOADED=false$",
        transcript,
        re.M,
    )
    if executed.returncode or not match or int(match.group(1)) < 20:
        raise RuntimeError(f"{flavor} lifecycle test failed; see {execution_log}\n{transcript[-4000:]}")

    return {
        "flavor": flavor,
        "optimization": optimization,
        "executable": artifact(executable),
        "compiler": artifact(Path(compiler)),
        "response": artifact(response),
        "dependency_report": artifact(dependencies),
        "map": artifact(link_map),
        "build_log": artifact(build_log),
        "execution_log": artifact(execution_log),
        "export_log": artifact(export_log),
        "import_log": artifact(import_log),
        "direct_dependencies": imports,
        "compiler_input_count": len(inputs),
        "compiler_inputs": [artifact(path) for path in inputs],
        "provider_libraries": providers,
        "checks": int(match.group(1)),
        "gamecore_loaded": False,
    }


def main():
    build_path = PROJECT / "evidence/temp_heap/build_result.json"
    build, conformance, provider = validate_temp_heap(build_path)
    if build["status"] != "TEMP_HEAP_PROVIDERS_BUILT" or conformance["status"] != "SDK_TEMP_HEAP_CONFORMANCE_PASS":
        raise RuntimeError("Validated TempHeap/Foundation provider artifacts are unavailable")
    providers = build["x64"]["libraries"]
    if len(providers) != 2 or providers[0] != build["x64"]["libraries"][0] or providers[1] != build["foundation"]["library"]:
        raise RuntimeError("Expected TempHeap and matching Foundation libraries")
    check_artifacts(providers)
    for path in (SOURCE, IMPLEMENTATION, Path(__file__).resolve()):
        path.read_bytes().decode("ascii")

    runs = [compile_and_run(build, providers, "/O2", "optimized"),
            compile_and_run(build, providers, "/Od", "debug")]
    if runs[0]["checks"] != runs[1]["checks"]:
        raise RuntimeError("Optimized and debug lifecycle check counts differ")
    report = {
        "status": "HOST_TEMP_HEAP_LIFECYCLE_PASS",
        "builder": artifact(Path(__file__).resolve()),
        "test_source": artifact(SOURCE),
        "implementation_header": artifact(IMPLEMENTATION),
        "provider_build": artifact(build_path),
        "provider_conformance": artifact(PROJECT / "evidence/temp_heap/conformance.json"),
        "validated_provider": provider,
        "runs": runs,
        "native_checks": sum(row["checks"] for row in runs),
        "sdk_or_game_dll_loaded": False,
        "scope": "EXE_TEMP_HEAP_EXPORT_PROVIDER_LINK_AND_HOST_SESSION_OWNER_LIFECYCLE",
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
