"""Freeze and exercise source-grounded mock checks for found-value SDK capture.

This verifier never builds or loads GameCore. The C++14 test reads frozen source
for structural contracts and exercises a mock commit transaction only.
"""
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
BUILD_ROOT = PROJECT / "Build/FoundValueSdkCapture"
EVIDENCE_ROOT = PROJECT / "evidence/found_value_sdk_capture"
INPUTS = {
    "capture_include": PROJECT / "Source/Concurrency/FoundValueSdkCapture.inc",
    "bridge_header": PROJECT / "Source/Concurrency/FoundValueScoreBridge.h",
    "original_player_ai": PROJECT / "Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvPlayerAI.cpp",
    "original_site_evaluator": PROJECT / "Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvSiteEvaluationClasses.cpp",
    "test": PROJECT / "Tests/found_value_sdk_capture.cpp",
    "verifier": Path(__file__).resolve(),
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(6)


def command(command_line: list[str], cwd: Path, env: dict, log: Path) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(command_line, cwd=cwd, env=env, capture_output=True, timeout=120,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    output = result.stdout + result.stderr
    log.write_bytes(output)
    return result


def main() -> int:
    missing = [name for name, path in INPUTS.items() if not path.is_file()]
    if missing:
        raise RuntimeError("Required source input is missing: " + ", ".join(missing))
    before = {name: digest(path) for name, path in INPUTS.items()}
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
        raise RuntimeError("Could not allocate unique retained run directories")

    frozen_root = build / "frozen"
    frozen_root.mkdir()
    frozen: dict[str, Path] = {}
    records: dict[str, dict[str, object]] = {}
    for name, source in INPUTS.items():
        target = (frozen_root / "include/FoundValueScoreBridge.h" if name == "bridge_header"
                  else frozen_root / (name + source.suffix))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied_hash = digest(target)
        if copied_hash != before[name]:
            raise RuntimeError("Frozen source hash mismatch: " + name)
        frozen[name] = target.resolve()
        records[name] = {"source_path": str(source.resolve()), "frozen_path": str(target.resolve()),
                         "sha256": copied_hash, "size": target.stat().st_size}

    report: dict[str, object] = {
        "schema": "zerosiscitysite.found_value_sdk_capture_component.v1",
        "run_id": identifier,
        "status": "RUNNING",
        "scope": "source_extracted_cpp14_structural_checks_and_mock_commit_only",
        "capture_started": False,
        "wpr_capture_started": False,
        "gamecore_loaded": False,
        "sdk_build_performed": False,
        "sdk_or_stage_modified": False,
        "physical_multicore_proven": False,
        "frozen_inputs": records,
        "source_hashes_before": before,
        "source_hashes_after": None,
        "compiler": None,
        "builds": {},
        "evidence_path": str((evidence / "conformance.json").resolve()),
    }

    try:
        env_dir = build / "environment"
        env, compiler = environment_for(VS, "x64", env_dir)
        linker = shutil.which("link.exe", path=env.get("PATH", ""))
        if linker is None:
            raise RuntimeError("MSVC linker is missing from initialized environment")
        vcvars = VS / "VC/Auxiliary/Build/vcvars64.bat"
        report["compiler"] = {
            "path": str(Path(compiler).resolve()), "sha256": digest(Path(compiler)),
            "linker_path": str(Path(linker).resolve()), "linker_sha256": digest(Path(linker)),
            "vcvars_path": str(vcvars.resolve()), "vcvars_sha256": digest(vcvars),
            "environment_script": str((env_dir / "read_build_environment.cmd").resolve()),
            "environment_script_sha256": digest(env_dir / "read_build_environment.cmd"),
            "standard": "C++14", "architecture": "x64",
        }

        for optimization in ("/O2", "/Od"):
            label = optimization[1:]
            directory = build / label
            directory.mkdir()
            executable = directory / "found_value_sdk_capture.exe"
            object_file = directory / "found_value_sdk_capture.obj"
            dependencies = directory / "source_dependencies.json"
            response = directory / "compile.rsp"
            log = directory / "compile.log"
            flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/permissive-",
                     "/MD", "/fp:strict", "/utf-8", optimization,
                     f'/I"{frozen_root / "include"}"',
                     f'/Fo"{object_file}"', f'/Fe"{executable}"',
                     f'/sourceDependencies "{dependencies}"', f'"{frozen["test"]}"',
                     "/link", "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX"]
            response.write_text("\n".join(flags) + "\n", encoding="utf-8")
            compiled = command([compiler, "@" + str(response)], directory, env, log)
            output = (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace")
            if compiled.returncode or "warning C" in output:
                raise RuntimeError(f"{label} compile failed or warned ({compiled.returncode}):\n{output[-5000:]}")
            if not executable.is_file() or not dependencies.is_file():
                raise RuntimeError(label + " compile omitted executable or /sourceDependencies output")

            dependency_doc = json.loads(dependencies.read_text(encoding="utf-8-sig"))
            dependency_data = dependency_doc.get("Data", dependency_doc)
            if Path(dependency_data.get("Source", "")).resolve() != frozen["test"]:
                raise RuntimeError(label + " compiler dependency document names a different translation unit")
            dependency_hashes = {}
            for item in dependency_data.get("Includes", []):
                path = Path(item).resolve(strict=True)
                dependency_hashes[str(path)] = digest(path)

            executed = subprocess.run(
                [str(executable), str(frozen["capture_include"]), str(frozen["original_player_ai"]),
                 str(frozen["original_site_evaluator"])], cwd=directory, env=env,
                capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            test_output = (executed.stdout + executed.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
            expected = "FOUND_VALUE_SDK_CAPTURE_MOCK_PASS checks=25 capture=false GAMECORE_LOADED=false SDK_BUILD=false WPR=false"
            if executed.returncode or test_output.strip() != expected:
                raise RuntimeError(f"{label} component mock failed ({executed.returncode}):\n{test_output}")
            report["builds"][label] = {
                "status": test_output.strip(), "checks": 25,
                "executable": str(executable.resolve()), "executable_sha256": digest(executable),
                "object": str(object_file.resolve()), "object_sha256": digest(object_file),
                "response_file": str(response.resolve()), "response_sha256": digest(response),
                "compile_log": str(log.resolve()), "compile_log_sha256": digest(log),
                "source_dependencies": str(dependencies.resolve()),
                "source_dependencies_sha256": digest(dependencies),
                "system_dependency_hashes": dependency_hashes,
            }

        after = {name: digest(path) for name, path in INPUTS.items()}
        report["source_hashes_after"] = after
        if before != after:
            raise RuntimeError("A guarded source changed during the component proof")
        for name, path in frozen.items():
            if digest(path) != before[name]:
                raise RuntimeError("Frozen component input changed during the proof: " + name)
        if digest(Path(compiler)) != report["compiler"]["sha256"] or digest(Path(linker)) != report["compiler"]["linker_sha256"]:
            raise RuntimeError("Compiler or linker changed during the component proof")
        report["status"] = "FOUND_VALUE_SDK_CAPTURE_COMPONENT_PASS"
        report["artifacts"] = {
            "build_files": {str(path.relative_to(build)): digest(path)
                            for path in build.rglob("*") if path.is_file()},
            "conformance_written_last": True,
        }
        destination = evidence / "conformance.json"
        destination.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "run_id": identifier,
                          "build": str(build.resolve()), "conformance": str(destination.resolve()),
                          "capture_started": False, "gamecore_loaded": False,
                          "sdk_build_performed": False, "wpr_capture_started": False}, sort_keys=True))
        return 0
    except Exception as error:
        report["source_hashes_after"] = {name: digest(path) for name, path in INPUTS.items()}
        report["status"] = "FOUND_VALUE_SDK_CAPTURE_COMPONENT_FAIL"
        report["error"] = f"{type(error).__name__}: {error}"
        report["traceback"] = traceback.format_exc()
        (evidence / "conformance.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                                                   encoding="utf-8")
        raise


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"verify_found_value_sdk_capture: {error}", file=sys.stderr)
        raise SystemExit(1)
