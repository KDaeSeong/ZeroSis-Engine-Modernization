"""Freeze and run the isolated C++14/C++17 shared-facts bridge component."""
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
SOURCE = PROJECT / "Tests/found_value_shared_bridge.cpp"
BRIDGE_CPP = PROJECT / "Source/Concurrency/FoundValueSharedBridge.cpp"
BRIDGE_H = PROJECT / "Source/Concurrency/FoundValueSharedBridge.h"
REFERENCE_BRIDGE_CPP = PROJECT / "Source/Concurrency/FoundValueScoreBridge.cpp"
KERNEL_H = PROJECT / "Source/Concurrency/FoundValueSharedScores.h"
BATCH_H = PROJECT / "Source/Concurrency/OrderedBatch.h"
VERIFIER = Path(__file__).resolve()
BUILD_ROOT = PROJECT / "Build/FoundValueSharedBridge"
EVIDENCE_ROOT = PROJECT / "evidence/found_value_shared_bridge"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
MANDATORY = [SOURCE, BRIDGE_CPP, BRIDGE_H, REFERENCE_BRIDGE_CPP, KERNEL_H, BATCH_H, VERIFIER]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def artifact(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), "sha256": digest(path), "size": path.stat().st_size}


def run_logged(command: list[str], cwd: Path, env: dict[str, str], log: Path,
               timeout: int = 180) -> str:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout)
    output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    log.write_text(output, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", output, re.I):
        raise RuntimeError(f"Command failed or emitted warnings; see {log}\n{output[-5000:]}")
    return output


def initialize_msvc(directory: Path) -> tuple[Path, Path, dict[str, str]]:
    directory.mkdir(parents=True, exist_ok=False)
    setup = directory / "initialize_msvc.cmd"
    setup.write_text('@echo off\n' + f'call "{VS / "VC/Auxiliary/Build/vcvars64.bat"}" >nul\n'
                     'if errorlevel 1 exit /b 1\nset\n', encoding="utf-8")
    result = subprocess.run(["cmd.exe", "/d", "/c", str(setup)], cwd=directory,
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
    if result.returncode:
        raise RuntimeError("MSVC x64 environment setup failed")
    env = {key.upper(): value for key, value in os.environ.items()}
    paths = []
    for line in result.stdout.decode("mbcs", errors="replace").splitlines():
        if "=" not in line or line.startswith("="):
            continue
        key, value = line.split("=", 1)
        env[key.upper()] = value
        if key.upper() == "PATH":
            paths.append(value)
    env["PATH"] = ";".join(dict.fromkeys(part for value in paths for part in value.split(";")))
    compiler = next((Path(part) / "cl.exe" for part in env["PATH"].split(";")
                     if (Path(part) / "cl.exe").is_file()), None)
    linker = next((Path(part) / "link.exe" for part in env["PATH"].split(";")
                   if (Path(part) / "link.exe").is_file()), None)
    if compiler is None or linker is None:
        raise RuntimeError("MSVC x64 compiler/linker not found")
    return compiler.resolve(), linker.resolve(), env


def compile_flags(standard: str, optimization: str, source: Path, obj: Path,
                  deps: Path, include: Path) -> list[str]:
    return ["/nologo", f"/std:{standard}", "/EHsc", "/W4", "/WX", "/permissive-",
            "/MD", "/fp:strict", "/utf-8", optimization, f'/I"{include}"', "/c",
            f'"{source}"', f'/Fo"{obj}"', f'/sourceDependencies "{deps}"']


def discover(compiler: Path, env: dict[str, str], source: Path, standard: str,
             label: str, directory: Path, include: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=False)
    obj, deps = directory / f"{label}.obj", directory / "dependencies.json"
    rsp = directory / "discover.rsp"
    rsp.write_text("\n".join(compile_flags(standard, "/O2", source, obj, deps, include)) + "\n",
                   encoding="utf-8")
    run_logged([str(compiler), f"@{rsp}"], directory, env, directory / "discover.log")
    data = json.loads(deps.read_text(encoding="utf-8-sig"))["Data"]
    if Path(data["Source"]).resolve() != source.resolve():
        raise RuntimeError(f"{label} dependency discovery compiled the wrong source")
    paths = {source.resolve(), *(Path(item).resolve() for item in data["Includes"])}
    if any(not path.is_file() for path in paths):
        raise RuntimeError(f"{label} dependency report listed a missing compiler input")
    return sorted(paths, key=lambda path: str(path).casefold())


def freeze_inputs(discovered: dict[str, list[Path]], snapshot: Path,
                  include_roots: list[Path]) -> tuple[dict[Path, Path], list[Path], list[dict[str, object]]]:
    roots = []
    for root in include_roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)
    all_inputs = {path.resolve() for paths in discovered.values() for path in paths}
    mapping: dict[Path, Path] = {}
    records = []
    root_targets = {root: snapshot / "include_roots" / f"root_{index:03d}"
                    for index, root in enumerate(roots)}
    for path in sorted(all_inputs, key=lambda item: str(item).casefold()):
        if path.is_relative_to(PROJECT.resolve()):
            target = snapshot / "project" / path.relative_to(PROJECT.resolve())
        else:
            candidates = [root for root in roots if path.is_relative_to(root)]
            if not candidates:
                raise RuntimeError("Compiler dependency is outside the frozen project/INCLUDE closure: " + str(path))
            root = max(candidates, key=lambda item: len(item.parts))
            target = root_targets[root] / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(path, target)
        if digest(path) != digest(target):
            raise RuntimeError("Frozen compiler input differs from its original: " + str(path))
        mapping[path] = target.resolve()
        records.append({"original_path": str(path), **artifact(target)})
    frozen_roots = [root_targets[root] for root in roots]
    return mapping, frozen_roots, records


def copy_toolchain(compiler: Path, linker: Path, snapshot: Path) -> tuple[Path, Path, list[dict[str, object]]]:
    version_root = compiler.parents[3]
    directory = snapshot / "toolchain" / "VC/Tools/MSVC" / version_root.name / compiler.parent.relative_to(version_root)
    directory.mkdir(parents=True, exist_ok=False)
    records = []
    live_cl_dir = compiler.parent
    names = {compiler.name, linker.name, "c1.dll", "c1xx.dll", "mspdb140.dll",
             "mspdbcore.dll", "mspdbst.dll", "mspft140.dll"}
    for name in sorted(names):
        source = compiler.with_name(name)
        if not source.is_file():
            if name in (compiler.name, linker.name):
                source = linker.with_name(name)
            else:
                continue
        if not source.is_file():
            raise RuntimeError("Missing compiler/linker module: " + name)
        target = directory / name
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise RuntimeError("Compiler/linker module freeze mismatch: " + name)
        records.append({"original_path": str(source.resolve()), **artifact(target)})
    frozen_cl, frozen_link = directory / compiler.name, directory / linker.name
    return frozen_cl, frozen_link, records


def library_paths(text: str) -> list[Path]:
    found = []
    for raw in re.findall(r"(?i)([A-Z]:\\[^\r\n\"]+?\.lib)", text):
        path = Path(raw.strip())
        if path.is_file() and path.resolve() not in found:
            found.append(path.resolve())
    return found


def freeze_libraries(paths: list[Path], snapshot: Path) -> tuple[list[Path], list[dict[str, object]]]:
    if not paths:
        raise RuntimeError("Linker did not report concrete selected .lib inputs")
    records, directories = [], []
    for index, source in enumerate(paths):
        directory = snapshot / "libraries" / f"lib_{index:03d}"
        directory.mkdir(parents=True, exist_ok=False)
        target = directory / source.name
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise RuntimeError("Frozen linker library differs from source: " + str(source))
        directories.append(directory.resolve())
        records.append({"original_path": str(source), **artifact(target)})
    return directories, records


def build_one(name: str, optimization: str, compiler: Path, linker: Path,
              base_env: dict[str, str], run_dir: Path, snapshot: Path,
              mapping: dict[Path, Path], frozen_roots: list[Path],
              discovered: dict[str, list[Path]], frozen_records: list[dict[str, object]],
              frozen_libraries: tuple[list[Path], list[dict[str, object]]] | None = None
              ) -> tuple[dict[str, object], tuple[list[Path], list[dict[str, object]]]]:
    directory = run_dir / name
    directory.mkdir(parents=True, exist_ok=False)
    env = base_env.copy()
    env["INCLUDE"] = ";".join(str(root) for root in frozen_roots)
    env["PATH"] = str(compiler.parent) + ";" + env.get("PATH", "")
    frozen_project = snapshot / "project"
    objects, deps_data, responses, logs = [], [], [], []
    for label, standard, original_source, include_rel in (
        ("caller_cpp14", "c++14", SOURCE.resolve(), "Source/Concurrency"),
        ("bridge_cpp17", "c++17", BRIDGE_CPP.resolve(), "Source/Concurrency"),
        ("dense_reference_cpp17", "c++17", REFERENCE_BRIDGE_CPP.resolve(), "Source/Concurrency"),
    ):
        source = mapping[original_source]
        include = frozen_project / include_rel
        obj, deps = directory / f"{label}.obj", directory / f"{label}.dependencies.json"
        rsp = directory / f"{label}.rsp"
        rsp.write_text("\n".join(compile_flags(standard, optimization, source, obj, deps, include)) + "\n",
                       encoding="utf-8")
        responses.append(rsp)
        log = directory / f"{label}.build.log"
        run_logged([str(compiler), f"@{rsp}"], directory, env, log)
        logs.append(log)
        data = json.loads(deps.read_text(encoding="utf-8-sig"))["Data"]
        consumed = {Path(data["Source"]).resolve(), *(Path(item).resolve() for item in data["Includes"])}
        expected = {mapping[path.resolve()].resolve() for path in discovered[label]}
        if Path(data["Source"]).resolve() != source.resolve() or consumed != expected or \
                any(not path.is_relative_to(snapshot.resolve()) for path in consumed):
            raise RuntimeError(f"{name}/{label} consumed inputs outside its frozen dependency closure")
        objects.append(obj)
        deps_data.append(deps)

    if frozen_libraries is None:
        probe_executable = directory / "FoundValueSharedBridge.link_probe.exe"
        probe_rsp = directory / "link_probe.rsp"
        probe_rsp.write_text("\n".join(["/nologo", *(f'"{item}"' for item in objects),
                                         f'/OUT:"{probe_executable}"', "/INCREMENTAL:NO", "/MACHINE:X64",
                                         "/Brepro", "/WX", "/VERBOSE:LIB",
                                         "/DEFAULTLIB:advapi32.lib"]) + "\n", encoding="utf-8")
        probe_log = directory / "link_probe.build.log"
        probe_text = run_logged([str(linker), f"@{probe_rsp}"], directory, env, probe_log)
        frozen_libraries = freeze_libraries(library_paths(probe_text), snapshot)
    library_dirs, library_records = frozen_libraries
    env["LIB"] = ";".join(str(path) for path in library_dirs)

    executable = directory / "FoundValueSharedBridge.exe"
    rsp = directory / "link.rsp"
    rsp.write_text("\n".join(["/nologo", *(f'"{item}"' for item in objects),
                               f'/OUT:"{executable}"', "/INCREMENTAL:NO", "/MACHINE:X64",
                               "/Brepro", "/WX", "/VERBOSE:LIB",
                               "/DEFAULTLIB:advapi32.lib"]) + "\n", encoding="utf-8")
    link_log = directory / "link.build.log"
    link_output = run_logged([str(linker), f"@{rsp}"], directory, env, link_log)
    final_libraries = library_paths(link_output)
    allowed_library_paths = {Path(item["path"]).resolve() for item in library_records}
    if not final_libraries or any(path not in allowed_library_paths for path in final_libraries):
        raise RuntimeError("Final linker pass resolved a non-frozen .lib")
    execution = subprocess.run([str(executable)], cwd=directory, env=env, capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=45)
    transcript = (execution.stdout + execution.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
    run_log = directory / "execution.log"
    run_log.write_text(transcript, encoding="utf-8")
    match = re.search(r"^FOUND_VALUE_SHARED_BRIDGE_PASS checks=(\d+) GAMECORE_LOADED=false TRACE_CAPTURED=false$", transcript, re.M)
    if execution.returncode or not match:
        raise RuntimeError(f"{name} component run failed; see {run_log}\n{transcript[-4000:]}")
    for record in frozen_records:
        if digest(Path(record["path"])) != record["sha256"] or \
                digest(Path(record["original_path"])) != record["sha256"]:
            raise RuntimeError("A frozen or live source/header/toolchain file changed during build/run")
    for record in library_records:
        if digest(Path(record["path"])) != record["sha256"] or \
                digest(Path(record["original_path"])) != record["sha256"]:
            raise RuntimeError("A frozen or source linker library changed during build/run")
    return {"configuration": name, "optimization": optimization,
            "caller_standard": "C++14", "bridge_standard": "C++17", "checks": int(match.group(1)),
            "executable": artifact(executable), "objects": [artifact(path) for path in objects],
            "responses": [artifact(path) for path in [*responses, rsp]],
            "dependency_reports": [artifact(path) for path in deps_data],
            "build_logs": [artifact(path) for path in [*logs, link_log]],
            "execution_log": artifact(run_log), "selected_link_libraries": library_records,
            "final_link_resolved_only_frozen_libraries": True,
            "compiler_inputs_frozen": True, "gamecore_loaded": False}, frozen_libraries


def main() -> None:
    if len(sys.argv) > 1 and Path(sys.argv[1]).resolve() != Path(sys.executable).resolve():
        raise RuntimeError("Invoke this verifier with the requested Python interpreter")
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:10]}"
    run_dir, evidence_dir = BUILD_ROOT / run_id, EVIDENCE_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir.mkdir(parents=True, exist_ok=False)
    snapshot = evidence_dir / "frozen_inputs"
    snapshot.mkdir(parents=True, exist_ok=False)
    before = {str(path.resolve()): artifact(path) for path in MANDATORY}
    mandatory_records = []
    for path in MANDATORY:
        rel = path.relative_to(PROJECT)
        target = snapshot / "project" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if digest(path) != digest(target):
            raise RuntimeError("Mandatory frozen file mismatch: " + str(path))
        mandatory_records.append({"original_path": str(path.resolve()), **artifact(target)})

    compiler, linker, base_env = initialize_msvc(run_dir / "environment")
    compiler_modules = {"compiler": artifact(compiler), "linker": artifact(linker)}
    roots = [PROJECT.resolve(), *(Path(item).resolve() for item in base_env.get("INCLUDE", "").split(";")
                                   if item and Path(item).is_dir())]
    discovered = {
        "caller_cpp14": discover(compiler, base_env, SOURCE, "c++14", "caller_cpp14",
                                  run_dir / "discovery_caller", PROJECT / "Source/Concurrency"),
        "bridge_cpp17": discover(compiler, base_env, BRIDGE_CPP, "c++17", "bridge_cpp17",
                                  run_dir / "discovery_bridge", PROJECT / "Source/Concurrency"),
        "dense_reference_cpp17": discover(compiler, base_env, REFERENCE_BRIDGE_CPP, "c++17",
                                            "dense_reference_cpp17", run_dir / "discovery_dense_reference",
                                            PROJECT / "Source/Concurrency"),
    }
    mapping, frozen_roots, dependency_records = freeze_inputs(discovered, snapshot, roots)
    frozen_compiler, frozen_linker, module_records = copy_toolchain(compiler, linker, snapshot)
    env = base_env.copy()
    env.pop("ZEROSIS_FOUND_VALUE_CPU_TRACE", None)
    env["PATH"] = str(frozen_compiler.parent) + ";" + env.get("PATH", "")
    records = mandatory_records + dependency_records + module_records
    if any(digest(Path(row["path"])) != row["sha256"] or
           digest(Path(row["original_path"])) != row["sha256"] for row in records):
        raise RuntimeError("A pre-build frozen input failed its hash check")

    optimized, frozen_libraries = build_one("optimized_O2", "/O2", compiler, linker, env,
                                             run_dir, snapshot, mapping, frozen_roots, discovered, records)
    unoptimized, _ = build_one("unoptimized_Od", "/Od", compiler, linker, env,
                               run_dir, snapshot, mapping, frozen_roots, discovered, records, frozen_libraries)
    configurations = [optimized, unoptimized]
    if configurations[0]["checks"] != configurations[1]["checks"]:
        raise RuntimeError("O2 and Od component check counts differ")
    after = {str(path.resolve()): artifact(path) for path in MANDATORY}
    if before != after:
        raise RuntimeError("A live source or verifier changed during the component verification")
    if compiler_modules != {"compiler": artifact(compiler), "linker": artifact(linker)}:
        raise RuntimeError("Live compiler or linker changed during verification")
    for row in records:
        if digest(Path(row["path"])) != row["sha256"] or \
                digest(Path(row["original_path"])) != row["sha256"]:
            raise RuntimeError("A frozen source, header, or compiler module changed")
    report = {
        "status": "FOUND_VALUE_SHARED_BRIDGE_CPP14_CPP17_PASS",
        "run_id": run_id,
        "source_hashes_before": before,
        "source_hashes_after": after,
        "dependency_discovery_inputs": {label: [artifact(path) for path in paths]
                                         for label, paths in discovered.items()},
        "frozen_inputs": records,
        "compiler": compiler_modules["compiler"], "linker": compiler_modules["linker"],
        "frozen_compiler_modules": module_records,
        "configurations": configurations,
        "checks": {row["configuration"]: row["checks"] for row in configurations},
        "toolchain_scope": {"x64": True, "warning_level": "/W4", "warnings_as_errors": True,
                            "runtime": "/MD", "floating_point": "/fp:strict",
                            "caller_standard": "C++14", "bridge_standard": "C++17",
                            "compiler_and_helper_modules_frozen_for_provenance": True,
                            "compiler_copy_executed": False,
                            "project_and_active_msvc_sdk_header_closure_frozen": True,
                            "selected_link_libraries_copied_to_frozen_overlay_and_hash_checked_pre_post": True},
        "gamecore_loaded": False, "sdk_dll_built": False, "sdk_runtime_launched": False,
        "wpr_started": False, "capture_performed": False,
        "found_value_cpu_trace_environment_cleared_for_component_run": True,
        "scope": "ISOLATED_SHARED_FACTS_C_ABI_PREVALIDATION_OWNER_THREAD_INDEX_ONLY_ORDERED_BATCH_ALL_OR_NOTHING_OUTPUTS_AND_DENSE_ABI_DIFFERENTIAL",
    }
    destination = evidence_dir / "conformance.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "run_id": run_id,
                      "checks": report["checks"], "evidence": artifact(destination),
                      "gamecore_loaded": False, "capture_performed": False}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
