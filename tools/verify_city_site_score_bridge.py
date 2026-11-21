"""Freeze and verify the isolated C++14 caller / C++17 city-score bridge."""
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
SOURCE = PROJECT / "Tests/city_site_score_bridge.cpp"
CONCURRENCY = PROJECT / "Source/Concurrency"
SOURCE_ROOT = PROJECT / "Source"
DIAGNOSTICS = SOURCE_ROOT / "Diagnostics"
BRIDGE_CPP = CONCURRENCY / "CitySiteScoreBridge.cpp"
BRIDGE_H = CONCURRENCY / "CitySiteScoreBridge.h"
CITY_SCORES_H = CONCURRENCY / "CitySiteScores.h"
ORDERED_BATCH_H = CONCURRENCY / "OrderedBatch.h"
TRACE_PROVIDER_CPP = DIAGNOSTICS / "CitySiteCpuTrace.cpp"
TRACE_PROVIDER_H = DIAGNOSTICS / "CitySiteCpuTrace.h"
NATIVE_BUILD = PROJECT / "tools/native_build.py"
COLLECT_BASELINE = PROJECT / "tools/collect_baseline.py"
VERIFIER = Path(__file__).resolve()
BUILD_ROOT = PROJECT / "Build/CitySiteScoreBridgeBoundary"
EVIDENCE_ROOT = PROJECT / "evidence/city_site_score_bridge"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
MANDATORY = [SOURCE, BRIDGE_CPP, BRIDGE_H, CITY_SCORES_H, ORDERED_BATCH_H,
             TRACE_PROVIDER_CPP, TRACE_PROVIDER_H,
             NATIVE_BUILD, COLLECT_BASELINE, VERIFIER]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def artifact(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), "sha256": digest(path), "size": path.stat().st_size}


def unique_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]


def initialize_msvc(directory: Path) -> tuple[Path, Path, dict[str, str]]:
    directory.mkdir(parents=True, exist_ok=False)
    setup = directory / "initialize_msvc.cmd"
    setup.write_text(
        "@echo off\n"
        f'call "{VS / "VC/Auxiliary/Build/vcvars64.bat"}" >nul\n'
        "if errorlevel 1 exit /b 1\nset\n",
        encoding="utf-8",
    )
    setup_result = subprocess.run(
        ["cmd.exe", "/d", "/c", str(setup)], cwd=directory, capture_output=True,
        creationflags=subprocess.CREATE_NO_WINDOW, timeout=60,
    )
    if setup_result.returncode:
        raise RuntimeError("MSVC x64 environment initialization failed")
    env = {key.upper(): value for key, value in os.environ.items()}
    path_entries: list[str] = []
    for line in setup_result.stdout.decode("mbcs", errors="replace").splitlines():
        if "=" not in line or line.startswith("="):
            continue
        key, value = line.split("=", 1)
        env[key.upper()] = value
        if key.upper() == "PATH":
            path_entries.append(value)
    env["PATH"] = ";".join(dict.fromkeys(part for item in path_entries for part in item.split(";")))
    compiler = next((Path(item) / "cl.exe" for item in env["PATH"].split(";")
                     if (Path(item) / "cl.exe").is_file()), None)
    linker = next((Path(item) / "link.exe" for item in env["PATH"].split(";")
                   if (Path(item) / "link.exe").is_file()), None)
    if compiler is None or linker is None:
        raise RuntimeError("MSVC compiler or linker was not found after x64 setup")
    return compiler.resolve(), linker.resolve(), env


def run_logged(command: list[str], cwd: Path, env: dict[str, str], log: Path,
               timeout: int = 180) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout)
    output = result.stdout + result.stderr
    log.write_bytes(output)
    decoded = output.decode("mbcs", errors="replace")
    if result.returncode or re.search(r"\bwarning\s+[A-Z]+\d+|\bwarning\s+C\d+", decoded, re.I):
        raise RuntimeError(f"Compiler/linker failed or warned; see {log}\n{decoded[-6000:]}")


def verify_frozen_trace_contract(snapshot: Path) -> dict[str, str]:
    bridge = (snapshot / "Source/Concurrency/CitySiteScoreBridge.cpp").read_text(encoding="utf-8")
    header = (snapshot / "Source/Diagnostics/CitySiteCpuTrace.h").read_text(encoding="utf-8")
    provider = (snapshot / "Source/Diagnostics/CitySiteCpuTrace.cpp").read_text(encoding="utf-8")
    required = {
        "bridge": ("../Diagnostics/CitySiteCpuTrace.h", "struct OwnedSiteInput", "CitySiteCpuTraceBatch",
                   "CitySiteCpuTraceJob", "std::atomic<std::uint64_t>", "fetch_add", "evaluate_ordered"),
        "provider_header": ("class CitySiteCpuTraceBatch", "class CitySiteCpuTraceJob"),
        "provider": ("ZEROSIS_CITY_SITE_CPU_TRACE", "TraceLoggingRegister", "TraceLoggingUnregister",
                     'TraceLoggingWrite(g_citySiteCpuTraceProvider, "BatchBegin"',
                     'TraceLoggingWrite(g_citySiteCpuTraceProvider, "BatchEnd"'),
    }
    for label, tokens in required.items():
        text = {"bridge": bridge, "provider_header": header, "provider": provider}[label]
        if any(token not in text for token in tokens):
            raise RuntimeError(f"Frozen diagnostics integration is missing required {label} contract")
    batch_at = bridge.find("CitySiteCpuTraceBatch trace(")
    schedule_at = bridge.find("evaluate_ordered(")
    job_at = bridge.find("CitySiteCpuTraceJob trace(")
    score_at = bridge.find("evaluate_all(input.site)")
    if min(batch_at, schedule_at, job_at, score_at) < 0 or batch_at >= schedule_at or job_at >= score_at:
        raise RuntimeError("Trace batch/job lifetime does not enclose the scheduled and scored operation")
    return {"bridge_sha256": digest(snapshot / "Source/Concurrency/CitySiteScoreBridge.cpp"),
            "provider_header_sha256": digest(snapshot / "Source/Diagnostics/CitySiteCpuTrace.h"),
            "provider_cpp_sha256": digest(snapshot / "Source/Diagnostics/CitySiteCpuTrace.cpp")}


def flags(standard: str, optimization: str, source: Path, obj: Path,
          dependencies: Path, include_root: Path | None) -> list[str]:
    values = ["/nologo", f"/std:{standard}", "/EHsc", "/W4", "/WX", optimization,
              "/MD", "/fp:strict", "/utf-8"]
    if include_root is not None:
        values.append(f'/I"{include_root}"')
    values.extend(["/c", f'"{source}"', f'/Fo"{obj}"', f'/sourceDependencies "{dependencies}"'])
    return values


def compile_discovery(compiler: Path, env: dict[str, str], source: Path, standard: str,
                      tag: str, directory: Path, include_root: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=False)
    obj = directory / f"{tag}.obj"
    dep = directory / "dependencies.json"
    rsp = directory / "discovery.rsp"
    std = "C++14" if standard == "c++14" else "C++17"
    rsp.write_text("\n".join(flags(standard, "/O2", source, obj, dep, include_root)) + "\n",
                   encoding="utf-8")
    run_logged([str(compiler), f"@{rsp}"], directory, env, directory / "discovery.log")
    data = json.loads(dep.read_text(encoding="utf-8-sig"))["Data"]
    if Path(data["Source"]).resolve() != source.resolve():
        raise RuntimeError(f"{tag} dependency discovery compiled the wrong source")
    paths = {Path(data["Source"]).resolve(), *(Path(item).resolve() for item in data["Includes"])}
    if any(not item.is_file() for item in paths):
        raise RuntimeError(f"{tag} dependency report includes a missing input")
    # Each translation unit has its own language mode and dependency closure.
    (directory / "standard.txt").write_text(std + "\n", encoding="ascii")
    return sorted(paths, key=lambda item: str(item).casefold())


def freeze_inputs(discovered: dict[str, list[Path]], snapshot: Path,
                  include_roots: list[Path]) -> tuple[dict[Path, Path], list[Path], list[dict[str, object]]]:
    roots: list[Path] = []
    for root in include_roots:
        try:
            resolved = root.resolve()
        except OSError:
            continue
        if resolved.is_dir() and resolved not in roots:
            roots.append(resolved)

    all_inputs = {path.resolve() for paths in discovered.values() for path in paths}
    source_paths = {SOURCE.resolve(), BRIDGE_CPP.resolve(), TRACE_PROVIDER_CPP.resolve()}
    input_map: dict[Path, Path] = {}
    root_map = {
        root: (snapshot / "Source" if index == 0
               else snapshot / "include_roots" / f"root_{index:03d}")
        for index, root in enumerate(roots)
    }
    for path in sorted(all_inputs, key=lambda item: str(item).casefold()):
        if path in source_paths:
            rel = {
                SOURCE.resolve(): "Tests/city_site_score_bridge.cpp",
                BRIDGE_CPP.resolve(): "Source/Concurrency/CitySiteScoreBridge.cpp",
                TRACE_PROVIDER_CPP.resolve(): "Source/Diagnostics/CitySiteCpuTrace.cpp",
            }[path]
            target = snapshot / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            input_map[path] = target.resolve()
            continue
        matches = [root for root in roots if path.is_relative_to(root)]
        if not matches:
            root = path.parent
            if root not in root_map:
                root_map[root] = snapshot / "include_roots" / f"extra_{len(root_map):03d}"
                roots.append(root)
            matches = [root]
        primary = max(matches, key=lambda item: len(item.parts))
        target = root_map[primary] / path.relative_to(primary)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(path, target)
        for alias_root in matches:
            alias = root_map[alias_root] / path.relative_to(alias_root)
            if not alias.exists():
                alias.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, alias)
        input_map[path] = target.resolve()

    records: list[dict[str, object]] = []
    for original, frozen in sorted(input_map.items(), key=lambda item: str(item[0]).casefold()):
        if digest(original) != digest(frozen):
            raise RuntimeError(f"Frozen compiler input differs from discovery input: {original}")
        records.append({"original_path": str(original), **artifact(frozen)})
    frozen_roots = [root_map[root] for root in roots if root in root_map]
    return input_map, frozen_roots, records


def build_configuration(name: str, optimization: str, compiler: Path, linker: Path,
                        base_env: dict[str, str], run_dir: Path, snapshot: Path,
                        frozen_roots: list[Path], input_map: dict[Path, Path],
                        discovery_inputs: dict[str, list[Path]], records: list[dict[str, object]]) -> dict[str, object]:
    directory = run_dir / name
    directory.mkdir(parents=True, exist_ok=False)
    env = base_env.copy()
    env["VSLANG"] = "1033"
    # Preserve ../Diagnostics from the bridge source and the original MSVC include search order.
    project_root = snapshot / "Source"
    env["INCLUDE"] = ";".join(str(path) for path in frozen_roots[1:])
    objects: list[Path] = []
    deps_out: dict[str, Path] = {}
    logs: list[Path] = []
    response_files: list[Path] = []
    for tag, standard, original_source, include_relative in (
        ("caller_cpp14", "c++14", SOURCE.resolve(), "Source/Concurrency"),
        ("bridge_cpp17", "c++17", BRIDGE_CPP.resolve(), "Source/Concurrency"),
        ("trace_provider_cpp14", "c++14", TRACE_PROVIDER_CPP.resolve(), "Source/Diagnostics"),
    ):
        frozen_source = input_map[original_source]
        obj = directory / f"{tag}.obj"
        dep = directory / f"{tag}.dependencies.json"
        rsp = directory / f"{tag}.rsp"
        include = snapshot / include_relative
        rsp.write_text("\n".join(flags(standard, optimization, frozen_source, obj, dep, include)) + "\n",
                       encoding="utf-8")
        response_files.append(rsp)
        log = directory / f"{tag}.build.log"
        run_logged([str(compiler), f"@{rsp}"], directory, env, log)
        logs.append(log)
        data = json.loads(dep.read_text(encoding="utf-8-sig"))["Data"]
        if Path(data["Source"]).resolve() != frozen_source.resolve():
            raise RuntimeError(f"{name}/{tag} compiled a non-frozen source")
        consumed = {Path(data["Source"]).resolve(), *(Path(item).resolve() for item in data["Includes"])}
        discovered_frozen = {input_map[path.resolve()].resolve() for path in discovery_inputs[tag]}
        if consumed != discovered_frozen:
            missing = sorted(map(str, consumed - discovered_frozen))
            omitted = sorted(map(str, discovered_frozen - consumed))
            raise RuntimeError(f"{name}/{tag} frozen include closure changed; new={missing}; omitted={omitted}")
        if any(not path.is_relative_to(snapshot.resolve()) for path in consumed):
            raise RuntimeError(f"{name}/{tag} consumed a live compiler input")
        objects.append(obj)
        deps_out[tag] = dep

    executable = directory / "CitySiteScoreBridgeBoundary.exe"
    link_rsp = directory / "link.rsp"
    link_rsp.write_text("\n".join([
        "/nologo", *(f'"{obj}"' for obj in objects), "advapi32.lib", f'/OUT:"{executable}"',
        "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX",
    ]) + "\n", encoding="utf-8")
    link_log = directory / "link.build.log"
    run_logged([str(linker), f"@{link_rsp}"], directory, env, link_log)
    executions = []
    for mode, enabled in (("default_disabled", False), ("trace_enabled", True)):
        execution_env = env.copy()
        execution_env.pop("ZEROSIS_CITY_SITE_CPU_TRACE", None)
        if enabled:
            execution_env["ZEROSIS_CITY_SITE_CPU_TRACE"] = "1"
        execution = subprocess.run([str(executable)], cwd=directory, env=execution_env, capture_output=True,
                                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
        transcript = (execution.stdout + execution.stderr).decode("utf-8", errors="replace")
        transcript = transcript.replace("\r\n", "\n").replace("\r", "\n")
        execution_log = directory / f"execution_{mode}.log"
        execution_log.write_text(transcript, encoding="utf-8")
        match = re.search(r"^CITY_SITE_SCORE_BRIDGE_BOUNDARY_PASS checks=(\d+) GAMECORE_LOADED=false$",
                          transcript, re.M)
        if execution.returncode or not match or int(match.group(1)) < 518:
            raise RuntimeError(f"{name}/{mode} boundary run failed; see {execution_log}\n{transcript[-4000:]}")
        trace_rows = re.findall(
            r"^ZEROSIS_CITY_SITE_CPU_TRACE batch_id=(\d+) process_id=(\d+) requested_workers=(\d+) sites=(\d+) workers_started=(\d+)$",
            transcript, re.M)
        if enabled:
            if not trace_rows:
                raise RuntimeError(f"{name} enabled run did not exercise successful TraceLogging registration")
            batch_ids = [int(row[0]) for row in trace_rows]
            if len(batch_ids) != len(set(batch_ids)) or any(
                    int(workers) not in (1, 2, 4) or int(sites) == 0 or
                    not 1 <= int(started) <= min(int(workers), int(sites))
                    for _batch, _process, workers, sites, started in trace_rows):
                raise RuntimeError(f"{name} emitted invalid or reused diagnostics batch metadata")
        elif trace_rows:
            raise RuntimeError(f"{name} default run emitted tracing with the opt-in environment removed")
        executions.append({"mode": mode, "trace_env_present": enabled,
                           "trace_env_value": "1" if enabled else None,
                           "wpr_session_started": False, "trace_capture_performed": False,
                           "trace_batch_summaries": [list(row) for row in trace_rows],
                           "checks": int(match.group(1)), "execution_log": artifact(execution_log)})
    for item in records:
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"Frozen compiler input changed during {name}")
    return {
        "configuration": name, "optimization": optimization,
        "caller_standard": "C++14", "bridge_standard": "C++17", "trace_provider_standard": "C++14",
        "executable": artifact(executable), "checks": executions[0]["checks"],
        "objects": [artifact(path) for path in objects],
        "responses": [artifact(path) for path in [*response_files, link_rsp]],
        "dependency_reports": [artifact(path) for path in deps_out.values()],
        "build_logs": [artifact(path) for path in [*logs, link_log]],
        "executions": executions,
        "compiler_inputs": [{"caller_or_bridge": tag,
                             "inputs": [artifact(input_map[path.resolve()]) for path in discovery_inputs[tag]]}
                            for tag in ("caller_cpp14", "bridge_cpp17", "trace_provider_cpp14")],
        "compiler_inputs_are_frozen": True,
        "gamecore_loaded": False,
    }


def main() -> None:
    if len(sys.argv) > 1 and Path(sys.argv[1]).resolve() != Path(sys.executable).resolve():
        raise RuntimeError("Invoke this verifier with the requested Python interpreter")
    run_id = unique_id()
    run_dir = BUILD_ROOT / run_id
    evidence_dir = EVIDENCE_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    evidence_dir.mkdir(parents=True, exist_ok=False)
    snapshot = evidence_dir / "frozen_inputs"
    snapshot.mkdir(parents=True, exist_ok=False)

    source_before = {str(path.resolve()): artifact(path) for path in MANDATORY}
    mandatory_records = []
    for source, relative in (
        (SOURCE, "Tests/city_site_score_bridge.cpp"),
        (BRIDGE_CPP, "Source/Concurrency/CitySiteScoreBridge.cpp"),
        (BRIDGE_H, "Source/Concurrency/CitySiteScoreBridge.h"),
        (CITY_SCORES_H, "Source/Concurrency/CitySiteScores.h"),
        (ORDERED_BATCH_H, "Source/Concurrency/OrderedBatch.h"),
        (TRACE_PROVIDER_CPP, "Source/Diagnostics/CitySiteCpuTrace.cpp"),
        (TRACE_PROVIDER_H, "Source/Diagnostics/CitySiteCpuTrace.h"),
        (NATIVE_BUILD, "tools/native_build.py"),
        (COLLECT_BASELINE, "tools/collect_baseline.py"),
        (VERIFIER, "tools/verify_city_site_score_bridge.py"),
    ):
        target = snapshot / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if digest(source) != digest(target):
            raise RuntimeError(f"Mandatory source freeze failed: {source}")
        mandatory_records.append({"original_path": str(source.resolve()), **artifact(target)})

    trace_contract = verify_frozen_trace_contract(snapshot)

    compiler, linker, environment = initialize_msvc(run_dir / "environment")
    compiler_before, linker_before = artifact(compiler), artifact(linker)
    original_include_roots = [SOURCE_ROOT.resolve()]
    original_include_roots.extend(Path(value).resolve() for value in environment.get("INCLUDE", "").split(";")
                                  if value and Path(value).is_dir())
    live_discovery: dict[str, list[Path]] = {}
    live_discovery["caller_cpp14"] = compile_discovery(
        compiler, environment, SOURCE, "c++14", "caller_cpp14", run_dir / "discovery_caller", CONCURRENCY)
    live_discovery["bridge_cpp17"] = compile_discovery(
        compiler, environment, BRIDGE_CPP, "c++17", "bridge_cpp17", run_dir / "discovery_bridge", CONCURRENCY)
    live_discovery["trace_provider_cpp14"] = compile_discovery(
        compiler, environment, TRACE_PROVIDER_CPP, "c++14", "trace_provider_cpp14",
        run_dir / "discovery_trace_provider", DIAGNOSTICS)
    source_input_union = {path for paths in live_discovery.values() for path in paths}
    required_tus = {SOURCE.resolve(), BRIDGE_CPP.resolve(), TRACE_PROVIDER_CPP.resolve(),
                    BRIDGE_H.resolve(), CITY_SCORES_H.resolve(), ORDERED_BATCH_H.resolve(), TRACE_PROVIDER_H.resolve()}
    if not required_tus.issubset(source_input_union):
        raise RuntimeError("Dependency discovery missed a caller, bridge, or diagnostics source/header")
    live_discovery_hashes = {str(path): artifact(path) for path in sorted(source_input_union,
                             key=lambda item: str(item).casefold())}
    input_map, frozen_include_roots, compiler_records = freeze_inputs(
        live_discovery, snapshot, original_include_roots)
    frozen_records = mandatory_records + compiler_records
    for item in frozen_records:
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Frozen input pre-build hash check failed")

    # The frozen bridge source directory is first for quoted headers; remaining roots mirror INCLUDE order.
    configurations = [
        build_configuration("optimized_O2", "/O2", compiler, linker, environment,
                            run_dir, snapshot, frozen_include_roots, input_map,
                            live_discovery, frozen_records),
        build_configuration("unoptimized_Od", "/Od", compiler, linker, environment,
                            run_dir, snapshot, frozen_include_roots, input_map,
                            live_discovery, frozen_records),
    ]
    live_discovery_after = {str(path): artifact(Path(path)) for path in live_discovery_hashes}
    if live_discovery_hashes != live_discovery_after:
        raise RuntimeError("A discovered source/header input changed during frozen compilation")
    source_after = {str(path.resolve()): artifact(path) for path in MANDATORY}
    if source_before != source_after:
        raise RuntimeError("A live source, input script, or verifier changed during the component verification")
    compiler_after, linker_after = artifact(compiler), artifact(linker)
    if compiler_before != compiler_after or linker_before != linker_after:
        raise RuntimeError("MSVC compiler or linker executable changed during verification")
    for item in frozen_records:
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Frozen input post-build hash check failed")

    report = {
        "status": "CITY_SITE_SCORE_BRIDGE_CPP14_CPP17_BOUNDARY_PASS",
        "run_id": run_id,
        "source_hashes_before": source_before,
        "source_hashes_after": source_after,
        "dependency_discovery_inputs": live_discovery_hashes,
        "frozen_inputs": frozen_records,
        "compiler": compiler_before,
        "linker": linker_before,
        "trace_integration_source": trace_contract,
        "toolchain_scope": {
            "x64": True, "warning_level": "/W4", "warnings_as_errors": True,
            "runtime": "/MD", "floating_point": "/fp:strict",
            "compiler_and_linker_executable_hashes_checked_before_and_after": True,
            "compiler_helper_dlls_frozen": False, "link_libraries_frozen": False,
            "windows_sdk_and_msvc_headers": "actual active dependency closure physically copied and recompiled from frozen overlays",
            "trace_provider_link_library": "advapi32.lib",
        },
        "configurations": configurations,
        "checks": {item["configuration"]: item["checks"] for item in configurations},
        "gamecore_loaded": False,
        "sdk_dll_built": False,
        "sdk_runtime_launched": False,
        "trace_provider_scope": {
            "provider_translation_unit": "C++14",
            "default_runs_remove_environment_override": True,
            "enabled_runs_set_environment_to": "1",
            "trace_logging_registration_exercised_without_wpr_session": True,
            "trace_capture_performed": False,
            "enabled_run_batch_metadata_validated": True,
        },
        "metrics_scope": "WORKER_CREATION_AND_SCORE_INVOCATION_ACCOUNTING_ONLY_NOT_PHYSICAL_MULTICORE_OR_PERFORMANCE_PROOF",
        "scope": "ISOLATED_C14_CALLER_C17_BRIDGE_C14_TRACE_PROVIDER_ABI_CONFIG_VALIDATION_FAILURE_ATOMICITY_OVERFLOW_METRICS_AND_OPT_IN_REGISTRATION",
    }
    destination = evidence_dir / "conformance.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "run_id": run_id,
                      "checks": report["checks"], "evidence": artifact(destination),
                      "gamecore_loaded": False}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
