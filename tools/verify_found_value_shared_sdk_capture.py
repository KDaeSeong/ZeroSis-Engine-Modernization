"""Freeze source-grounded tests for the shared-facts SDK capture; never build GameCore."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import traceback

from native_build import environment_for

PROJECT = Path(__file__).resolve().parents[1]
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
BUILD_ROOT = PROJECT / "Build/FoundValueSharedSdkCapture"
EVIDENCE_ROOT = PROJECT / "evidence/found_value_shared_sdk_capture"
INPUTS = {
    "capture": PROJECT / "Source/Concurrency/FoundValueSharedSdkCapture.inc",
    "shared_bridge_header": PROJECT / "Source/Concurrency/FoundValueSharedBridge.h",
    "score_bridge_header": PROJECT / "Source/Concurrency/FoundValueScoreBridge.h",
    "original_player_ai": PROJECT / "Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvPlayerAI.cpp",
    "active_player_ai": PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvPlayerAI.cpp",
    "original_site_evaluator": PROJECT / "Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvSiteEvaluationClasses.cpp",
    "active_site_evaluator": PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvSiteEvaluationClasses.cpp",
    "test": PROJECT / "Tests/found_value_shared_sdk_capture.cpp",
    "verifier": Path(__file__).resolve(),
    "native_build": PROJECT / "tools/native_build.py",
    "collect_baseline": PROJECT / "tools/collect_baseline.py",
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def artifact(path: Path) -> dict:
    return {"path": str(path.resolve()), "sha256": digest(path), "size": path.stat().st_size}


def source_watch(path: Path) -> dict:
    return {"original_source_path": str(path.resolve()),
            "original_source_sha256": digest(path),
            "original_source_size": path.stat().st_size}


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(6)


def run(command: list[str], cwd: Path, env: dict, log: Path, timeout: int = 120) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    log.write_bytes(result.stdout + result.stderr)
    return result


def freeze(source: Path, destination: Path, original_path: Path) -> dict:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    if digest(destination) != digest(source):
        raise RuntimeError("Frozen input differs from source: " + str(source))
    return {"original_source_path": str(original_path.resolve()),
            "original_source_sha256": digest(source), "original_source_size": source.stat().st_size,
            **artifact(destination)}


def freeze_system_headers(inputs: list[Path], roots: list[Path], frozen_root: Path) -> tuple[list[dict], list[Path]]:
    include_roots = [root.resolve() for root in roots if root.is_dir()]
    overlays = [frozen_root / ("include_%03d" % index) for index in range(len(include_roots))]
    for overlay in overlays:
        overlay.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict] = {}
    for source in inputs:
        owners = [index for index, root in enumerate(include_roots) if source.is_relative_to(root)]
        if not owners:
            raise RuntimeError("System compiler input is outside MSVC INCLUDE roots: " + str(source))
        for index in owners:
            target = overlays[index] / source.relative_to(include_roots[index])
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if digest(target) != digest(source):
                    raise RuntimeError("Conflicting system headers map to one frozen include path")
            else:
                shutil.copy2(source, target)
            records[str(target.resolve())] = {"source_path": str(source.resolve()), **artifact(target)}
    return list(records.values()), overlays


def dependency_paths(path: Path) -> tuple[Path, list[Path]]:
    document = json.loads(path.read_text(encoding="utf-8-sig"))
    data = document.get("Data", document)
    source = Path(data["Source"]).resolve()
    includes = sorted({Path(item).resolve() for item in data.get("Includes", [])},
                      key=lambda item: str(item).casefold())
    if not source.is_file() or any(not item.is_file() for item in includes):
        raise RuntimeError("MSVC sourceDependencies contains a missing compiler input")
    return source, includes


def compact_build(directory: Path, source: Path, include_root: Path, env: dict,
                  compiler: str, optimization: str, test_args: list[Path]) -> dict:
    executable = directory / "found_value_shared_sdk_capture.exe"
    object_file = directory / "found_value_shared_sdk_capture.obj"
    dependencies = directory / "source_dependencies.json"
    response = directory / "compile.rsp"
    log = directory / "compile.log"
    flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/permissive-",
             "/MD", "/fp:strict", "/utf-8", optimization,
             f'/I"{include_root}"', f'/Fo"{object_file}"', f'/Fe"{executable}"',
             f'/sourceDependencies "{dependencies}"', f'"{source}"']
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    compiled = run([compiler, "@" + str(response), "/link", "/INCREMENTAL:NO",
                    "/MACHINE:X64", "/Brepro", "/WX"], directory, env, log)
    compiler_text = (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace")
    if compiled.returncode or "warning C" in compiler_text:
        raise RuntimeError(f"{optimization} compile failed or warned ({compiled.returncode}):\n{compiler_text[-5000:]}")
    if not executable.is_file() or not object_file.is_file() or not dependencies.is_file():
        raise RuntimeError(optimization + " compile omitted its executable, object, or dependency record")
    consumed_source, consumed_headers = dependency_paths(dependencies)
    frozen_root = include_root.resolve()
    if consumed_source != source.resolve() or not consumed_source.is_relative_to(frozen_root):
        raise RuntimeError("Compiler used a translation unit outside the frozen proof")
    if any(not header.is_relative_to(frozen_root) for header in consumed_headers):
        raise RuntimeError("Compiler consumed a header outside the frozen proof")
    executed = subprocess.run([str(executable), *(str(path) for path in test_args)], cwd=directory,
                              env=env, capture_output=True, timeout=30,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    transcript = (executed.stdout + executed.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
    execution = directory / "execution.log"
    execution.write_text(transcript, encoding="utf-8")
    import re
    match = re.fullmatch(r"FOUND_VALUE_SHARED_SDK_CAPTURE_EXACT_BODY_MOCK_PASS checks=(\d+) capture=false GAMECORE_LOADED=false SDK_BUILD=false WPR=false\n?", transcript)
    if executed.returncode or match is None:
        raise RuntimeError(f"{optimization} mock failed ({executed.returncode}):\n{transcript[-5000:]}")
    return {"optimization": optimization, "status": "PASS", "checks": int(match.group(1)),
            "executable": artifact(executable), "object": artifact(object_file),
            "response_file": artifact(response), "compile_log": artifact(log),
            "execution_log": artifact(execution), "source_dependencies": artifact(dependencies),
            "consumed_files": [artifact(consumed_source), *(artifact(path) for path in consumed_headers)],
            "warnings": 0, "gamecore_loaded": False, "sdk_build_performed": False}


def main() -> int:
    missing = [name for name, path in INPUTS.items() if not path.is_file()]
    if missing:
        raise RuntimeError("Required frozen source missing: " + ", ".join(missing))
    original_site = INPUTS["original_site_evaluator"].read_bytes()
    if original_site != INPUTS["active_site_evaluator"].read_bytes():
        raise RuntimeError("Active x64 and original site evaluator source differ")
    before = {name: source_watch(path) for name, path in INPUTS.items()}
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        identifier = run_id()
        build = BUILD_ROOT / identifier
        evidence = EVIDENCE_ROOT / identifier
        try:
            build.mkdir()
            evidence.mkdir()
            break
        except FileExistsError:
            continue
    else:
        raise RuntimeError("Could not allocate unique shared-capture evidence directories")

    report: dict = {
        "schema": "zerosiscitysite.found_value_shared_sdk_capture_component.v1",
        "run_id": identifier,
        "status": "RUNNING",
        "scope": "exact_original_sdk_body_source_checks_and_owner_cache_transaction_mock",
        "capture_started": False,
        "wpr_capture_started": False,
        "gamecore_loaded": False,
        "sdk_build_performed": False,
        "sdk_or_stage_modified": False,
        "physical_multicore_proven": False,
        "performance_claim": False,
        "source_watches_before": before,
        "source_watches_after": None,
        "compiler": None,
        "builds": {},
        "evidence_path": str((evidence / "conformance.json").resolve()),
    }

    try:
        frozen_root = build / "frozen"
        include_root = frozen_root / "include"
        source_root = frozen_root / "tests"
        sdk_root = frozen_root / "sdk"
        tool_root = frozen_root / "tools"
        for folder in (include_root, source_root, sdk_root, tool_root): folder.mkdir(parents=True, exist_ok=True)
        frozen: dict[str, Path] = {}
        frozen_records = {}
        destinations = {
            "capture": frozen_root / "Source/Concurrency/FoundValueSharedSdkCapture.inc",
            "shared_bridge_header": include_root / "FoundValueSharedBridge.h",
            "score_bridge_header": include_root / "FoundValueScoreBridge.h",
            "original_player_ai": sdk_root / "original/CvPlayerAI.cpp",
            "active_player_ai": sdk_root / "active/CvPlayerAI.cpp",
            "original_site_evaluator": sdk_root / "original/CvSiteEvaluationClasses.cpp",
            "active_site_evaluator": sdk_root / "active/CvSiteEvaluationClasses.cpp",
            "test": source_root / "found_value_shared_sdk_capture.cpp",
            "verifier": tool_root / "verify_found_value_shared_sdk_capture.py",
            "native_build": tool_root / "native_build.py",
            "collect_baseline": tool_root / "collect_baseline.py",
        }
        for name, source in INPUTS.items():
            frozen_records[name] = freeze(source, destinations[name], source)
            frozen[name] = destinations[name].resolve()

        environment_dir = build / "environment"
        env, compiler = environment_for(VS, "x64", environment_dir)
        from shutil import which
        linker = which("link.exe", path=env.get("PATH", ""))
        if linker is None: raise RuntimeError("MSVC linker is missing from initialized x64 environment")
        compiler_path = Path(compiler).resolve()
        linker_path = Path(linker).resolve()
        vcvars = VS / "VC/Auxiliary/Build/vcvars64.bat"
        report["compiler"] = {"path": str(compiler_path), "sha256": digest(compiler_path),
                              "linker_path": str(linker_path), "linker_sha256": digest(linker_path),
                              "vcvars_path": str(vcvars.resolve()), "vcvars_sha256": digest(vcvars),
                              "standard": "C++14", "architecture": "x64"}

        # Discovery selects the exact standard-library and Windows SDK headers used below.
        discovery = build / "dependency_discovery"
        discovery.mkdir()
        probe_exe = discovery / "probe.exe"
        probe_obj = discovery / "probe.obj"
        probe_deps = discovery / "dependencies.json"
        probe_rsp = discovery / "compile.rsp"
        probe_log = discovery / "compile.log"
        probe_flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/permissive-",
                       "/MD", "/fp:strict", "/utf-8", "/O2", f'/I"{include_root}"',
                       f'/Fo"{probe_obj}"', f'/Fe"{probe_exe}"',
                       f'/sourceDependencies "{probe_deps}"', f'"{frozen["test"]}"']
        probe_rsp.write_text("\n".join(probe_flags) + "\n", encoding="utf-8")
        probe = run([compiler, "@" + str(probe_rsp), "/link", "/INCREMENTAL:NO",
                     "/MACHINE:X64", "/Brepro", "/WX"], discovery, env, probe_log)
        probe_output = (probe.stdout + probe.stderr).decode("mbcs", errors="replace")
        if probe.returncode or "warning C" in probe_output:
            raise RuntimeError("Compiler dependency discovery failed or warned:\n" + probe_output[-5000:])
        probe_source, probe_headers = dependency_paths(probe_deps)
        if probe_source != frozen["test"]:
            raise RuntimeError("Dependency probe compiled an unexpected test source")
        include_roots = [Path(item).resolve() for item in env.get("INCLUDE", "").split(";") if item]
        system_records, overlays = freeze_system_headers(
            [path for path in probe_headers if not path.is_relative_to(include_root.resolve())],
            include_roots, frozen_root / "system")
        frozen_includes = [include_root, *overlays]
        run_env = env.copy()
        run_env["INCLUDE"] = ";".join(str(path) for path in frozen_includes)
        for label, optimization in (("O2", "/O2"), ("Od", "/Od")):
            directory = build / label
            directory.mkdir()
            report["builds"][label] = compact_build(directory, frozen["test"], frozen_root,
                run_env, compiler, optimization, [frozen["capture"], frozen["original_player_ai"],
                    frozen["original_site_evaluator"], frozen["active_player_ai"], frozen["active_site_evaluator"]])

        after = {name: source_watch(path) for name, path in INPUTS.items()}
        report["source_watches_after"] = after
        if {name: value["original_source_sha256"] for name, value in before.items()} != {
                name: value["original_source_sha256"] for name, value in after.items()}:
            raise RuntimeError("A guarded capture, ABI, source, test, or tool changed during proof")
        for name, path in frozen.items():
            if digest(path) != before[name]["original_source_sha256"]:
                raise RuntimeError("Frozen input changed during proof: " + name)
        if digest(compiler_path) != report["compiler"]["sha256"] or digest(linker_path) != report["compiler"]["linker_sha256"]:
            raise RuntimeError("Compiler or linker changed during proof")
        report["frozen_inputs"] = frozen_records
        report["frozen_system_headers"] = system_records
        frozen_header_artifacts = []
        frozen_by_original = {}
        for record in system_records:
            frozen_by_original.setdefault(record["source_path"], []).append(
                {"path": record["path"], "sha256": record["sha256"], "size": record["size"]})
        for path in probe_headers:
            if path.is_relative_to(include_root.resolve()):
                frozen_header_artifacts.append(artifact(path))
            else:
                copies = frozen_by_original.get(str(path.resolve()))
                if not copies:
                    raise RuntimeError("Dependency discovery header lacks a frozen copy: " + str(path))
                frozen_header_artifacts.extend(copies)
        report["dependency_discovery"] = {"source": artifact(probe_source),
            "headers": frozen_header_artifacts,
            "response": artifact(probe_rsp), "compile_log": artifact(probe_log),
            "count": 1 + len(probe_headers)}
        report["status"] = "FOUND_VALUE_SHARED_SDK_CAPTURE_EXACT_BODY_MOCK_PASS"
        report["artifacts"] = {"build_files": {str(path.relative_to(build)): digest(path)
            for path in build.rglob("*") if path.is_file()}, "conformance_written_last": True}
        destination = evidence / "conformance.json"
        destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "run_id": identifier,
            "build": str(build.resolve()), "conformance": str(destination.resolve()),
            "capture_started": False, "gamecore_loaded": False,
            "sdk_build_performed": False, "wpr_capture_started": False}, sort_keys=True))
        return 0
    except Exception as error:
        report["source_watches_after"] = {name: source_watch(path) for name, path in INPUTS.items()}
        report["status"] = "FOUND_VALUE_SHARED_SDK_CAPTURE_COMPONENT_FAIL"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
        (evidence / "conformance.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"verify_found_value_shared_sdk_capture: {error}", file=sys.stderr)
        raise SystemExit(1)
