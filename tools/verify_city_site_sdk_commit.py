"""Verify CitySite FindBestSites result commits in frozen SDK-shaped mocks."""
from __future__ import annotations

import hashlib
import importlib.util
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
BASE_ID = "20261001T123732Z_b9cfa90a84ff"
BASE_EVIDENCE = PROJECT / "evidence/city_site_sdk" / BASE_ID
BASE_REPORT = BASE_EVIDENCE / "build_result.json"
BASE_CANDIDATE = PROJECT / "Build/CitySiteSDK" / BASE_ID / "Source/CvGameCoreDLL_Expansion2/CvCitySpecializationAI.cpp"
FROZEN_BUILDER = BASE_EVIDENCE / "frozen/builder/build_city_site_sdk_candidate.py"
FROZEN_SDK = BASE_EVIDENCE / "frozen/sdk_source/CvCitySpecializationAI.cpp"
BRIDGE_H = PROJECT / "Source/Concurrency/CitySiteScoreBridge.h"
SOURCE_TEMPLATE = PROJECT / "Tests/city_site_sdk_commit.cpp"
BUILDER_LIVE = PROJECT / "tools/build_city_site_sdk_candidate.py"
NATIVE_BUILD = PROJECT / "tools/native_build.py"
COLLECT_BASELINE = PROJECT / "tools/collect_baseline.py"
VERIFIER = Path(__file__).resolve()
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
BUILD_ROOT = PROJECT / "Build/CitySiteSdkCommit"
EVIDENCE_ROOT = PROJECT / "evidence/city_site_sdk_commit"
PLACEHOLDERS = {
    "/*__GENERATED_PATCH_HELPERS__*/": "patch helpers",
    "/*__ORIGINAL_SCALAR_HELPERS__*/": "original scalar helpers",
    "/*__GENERATED_FIND_BEST_SITES__*/": "generated FindBestSites",
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def artifact(path: Path) -> dict[str, object]:
    return {"path": str(path.resolve()), "sha256": digest(path), "size": path.stat().st_size}


def unique_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]


def copy_frozen(source: Path, target: Path) -> dict[str, object]:
    target.parent.mkdir(parents=True, exist_ok=True)
    before = digest(source)
    shutil.copy2(source, target)
    frozen = digest(target)
    after = digest(source)
    if before != frozen or before != after:
        raise RuntimeError(f"Input changed while freezing: {source}")
    return {"original_path": str(source.resolve()), "source_sha256_before": before,
            "source_sha256_after": after, **artifact(target)}


def initialize_msvc(directory: Path) -> tuple[Path, Path, dict[str, str]]:
    directory.mkdir(parents=True, exist_ok=False)
    setup = directory / "initialize_msvc.cmd"
    setup.write_text(
        "@echo off\n"
        f'call "{VS / "VC/Auxiliary/Build/vcvars64.bat"}" >nul\n'
        "if errorlevel 1 exit /b 1\nset\n", encoding="utf-8")
    result = subprocess.run(["cmd.exe", "/d", "/c", str(setup)], cwd=directory,
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
    if result.returncode:
        raise RuntimeError("MSVC x64 environment initialization failed")
    env = {key.upper(): value for key, value in os.environ.items()}
    path_values: list[str] = []
    for line in result.stdout.decode("mbcs", errors="replace").splitlines():
        if "=" not in line or line.startswith("="):
            continue
        key, value = line.split("=", 1)
        env[key.upper()] = value
        if key.upper() == "PATH":
            path_values.append(value)
    env["PATH"] = ";".join(dict.fromkeys(part for value in path_values for part in value.split(";")))
    compiler = next((Path(value) / "cl.exe" for value in env["PATH"].split(";")
                     if (Path(value) / "cl.exe").is_file()), None)
    linker = next((Path(value) / "link.exe" for value in env["PATH"].split(";")
                   if (Path(value) / "link.exe").is_file()), None)
    if compiler is None or linker is None:
        raise RuntimeError("MSVC compiler/linker missing after x64 setup")
    return compiler.resolve(), linker.resolve(), env


def call_tool(command: list[str], cwd: Path, env: dict[str, str], log: Path,
              timeout: int = 180) -> None:
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=timeout)
    output = result.stdout + result.stderr
    log.write_bytes(output)
    decoded = output.decode("mbcs", errors="replace")
    if result.returncode or re.search(r"\bwarning\s+[A-Z]+\d+|\bwarning\s+C\d+", decoded, re.I):
        raise RuntimeError(f"Compiler/linker failed or warned; see {log}\n{decoded[-6000:]}")


def sdk_span(text: str, start: str, end: str, label: str) -> str:
    if text.count(start) != 1 or text.count(end) != 1:
        raise RuntimeError(f"Expected unique SDK source anchors for {label}")
    left = text.index(start)
    right = text.index(end, left + len(start))
    if right <= left:
        raise RuntimeError(f"Invalid SDK source span for {label}")
    return text[left:right]


def generate_harness(builder_file: Path, sdk_file: Path, candidate_file: Path,
                     template_file: Path, generated_file: Path, frozen_tools: Path) -> dict[str, str | int]:
    sys.path.insert(0, str(frozen_tools))
    spec = importlib.util.spec_from_file_location("frozen_city_site_builder", builder_file)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load the physically frozen candidate builder")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    sdk_bytes = sdk_file.read_bytes()
    prepared = builder.prepare_source(sdk_bytes)
    if prepared != candidate_file.read_bytes():
        raise RuntimeError("Frozen builder output does not exactly match its recorded candidate source")
    prepared_text = prepared.decode("latin1")
    sdk_text = sdk_bytes.decode("latin1")
    if "\r\n" not in prepared_text or "\r\n" not in sdk_text:
        raise RuntimeError("Unexpected SDK source line-ending/encoding contract")

    find_start = "/// Find the best nearby city site for all yield types\r\nvoid CvCitySpecializationAI::FindBestSites()\r\n{"
    find_end = "\r\n/// Evaluate strength of an existing city"
    find_body = sdk_span(prepared_text, find_start, find_end, "prepared FindBestSites")
    specific_start = "/// Evaluate strength of an existing city for providing a specific type of yield (except Science!)\r\nint CvCitySpecializationAI::PlotValueForSpecificYield(CvPlot* pPlot, YieldTypes eYield)\r\n{"
    science_start = "/// Evaluate strength of a city plot for providing science\r\nint CvCitySpecializationAI::PlotValueForScience(CvPlot* pPlot)\r\n{"
    building_start = "/// Multiply city value for a yield based on buildings present"
    specific = sdk_span(sdk_text, specific_start, science_start, "original specific-yield oracle")
    science = sdk_span(sdk_text, science_start, building_start, "original science oracle")
    helper_text = builder.PATCH_HELPERS.replace("\n", "\r\n")
    if prepared_text.count(helper_text) != 1:
        raise RuntimeError("Candidate does not contain exactly one builder helper block")
    template = template_file.read_text(encoding="utf-8")
    replacements = {
        "/*__GENERATED_PATCH_HELPERS__*/": helper_text,
        "/*__ORIGINAL_SCALAR_HELPERS__*/": specific + science,
        "/*__GENERATED_FIND_BEST_SITES__*/": find_body,
    }
    for marker, replacement in replacements.items():
        if template.count(marker) != 1:
            raise RuntimeError(f"Template must contain exactly one {PLACEHOLDERS[marker]} marker")
        template = template.replace(marker, replacement, 1)
    if any(marker in template for marker in replacements):
        raise RuntimeError("Generated component source contains an unexpanded marker")
    generated_file.parent.mkdir(parents=True, exist_ok=True)
    normalized = template.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\r\n")
    generated_file.write_bytes(normalized.encode("utf-8"))
    return {
        "candidate_sha256": digest(candidate_file),
        "prepared_find_best_sites_sha256": hashlib.sha256(find_body.encode("latin1")).hexdigest(),
        "builder_patch_helpers_sha256": hashlib.sha256(helper_text.encode("latin1")).hexdigest(),
        "original_specific_yield_helper_sha256": hashlib.sha256(specific.encode("latin1")).hexdigest(),
        "original_science_helper_sha256": hashlib.sha256(science.encode("latin1")).hexdigest(),
        "generated_translation_unit_sha256": digest(generated_file),
        "find_best_sites_bytes": len(find_body.encode("latin1")),
        "helper_bytes": len(helper_text.encode("latin1")),
    }


def compile_discovery(compiler: Path, env: dict[str, str], source: Path, include_root: Path,
                      directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=False)
    obj = directory / "discovery.obj"
    dependencies = directory / "dependencies.json"
    response = directory / "discovery.rsp"
    response.write_text("\n".join([
        "/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/O2", "/MD", "/fp:strict", "/utf-8",
        "/D_CRT_SECURE_NO_WARNINGS",
        f'/I"{include_root}"', "/c", f'"{source}"', f'/Fo"{obj}"',
        f'/sourceDependencies "{dependencies}"',
    ]) + "\n", encoding="utf-8")
    call_tool([str(compiler), f"@{response}"], directory, env, directory / "discovery.log")
    data = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
    if Path(data["Source"]).resolve() != source.resolve():
        raise RuntimeError("Dependency discovery compiled an unexpected generated source")
    inputs = {Path(data["Source"]).resolve(), *(Path(item).resolve() for item in data["Includes"])}
    if any(not path.is_file() for path in inputs):
        raise RuntimeError("Compiler dependency report listed a missing file")
    if BRIDGE_H.name not in {path.name for path in inputs}:
        raise RuntimeError("Compiler dependency closure did not include CitySiteScoreBridge.h")
    return sorted(inputs, key=lambda item: str(item).casefold())


def freeze_compiler_closure(inputs: list[Path], snapshot: Path, source: Path,
                            include_roots: list[Path]) -> tuple[dict[Path, Path], list[Path], list[dict[str, object]]]:
    roots: list[Path] = []
    for root in include_roots:
        if root.is_dir() and root.resolve() not in roots:
            roots.append(root.resolve())
    root_targets = {root: snapshot / "include_roots" / f"root_{index:03d}"
                    for index, root in enumerate(roots)}
    mapping: dict[Path, Path] = {source.resolve(): source.resolve()}
    records: list[dict[str, object]] = []
    for original in inputs:
        if original.resolve() == source.resolve():
            continue
        path = original.resolve()
        matching = [root for root in roots if path.is_relative_to(root)]
        if not matching:
            root = path.parent
            root_targets.setdefault(root, snapshot / "include_roots" / f"extra_{len(root_targets):03d}")
            roots.append(root)
            matching = [root]
        selected = matching[0]
        target = root_targets[selected] / path.relative_to(selected)
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(path, target)
        for alias_root in matching:
            alias = root_targets[alias_root] / path.relative_to(alias_root)
            if not alias.exists():
                alias.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, alias)
        mapping[path] = target.resolve()
        if digest(path) != digest(target):
            raise RuntimeError(f"Compiler header changed during freeze: {path}")
        records.append({"original_path": str(path), **artifact(target)})
    return mapping, [root_targets[root] for root in roots], records


def compile_run(name: str, optimization: str, compiler: Path, linker: Path,
                environment: dict[str, str], run_dir: Path, source: Path, include_roots: list[Path],
                mapping: dict[Path, Path], expected_inputs: list[Path], frozen_records: list[dict[str, object]]) -> dict[str, object]:
    directory = run_dir / name
    directory.mkdir(parents=True, exist_ok=False)
    env = environment.copy()
    env["VSLANG"] = "1033"
    env["INCLUDE"] = ";".join(str(path) for path in include_roots[1:])
    object_path = directory / "city_site_sdk_commit.obj"
    dependencies = directory / "dependencies.json"
    response = directory / "compile.rsp"
    response.write_text("\n".join([
        "/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", optimization,
        "/MD", "/fp:strict", "/utf-8", "/D_CRT_SECURE_NO_WARNINGS",
        f'/I"{include_roots[0]}"', "/c",
        f'"{source}"', f'/Fo"{object_path}"', f'/sourceDependencies "{dependencies}"',
    ]) + "\n", encoding="utf-8")
    call_tool([str(compiler), f"@{response}"], directory, env, directory / "compile.log")
    data = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
    consumed = {Path(data["Source"]).resolve(), *(Path(item).resolve() for item in data["Includes"])}
    expected = {mapping[path.resolve()].resolve() for path in expected_inputs}
    if consumed != expected:
        raise RuntimeError(f"{name} consumed a different frozen include closure: new={consumed-expected}, missing={expected-consumed}")
    if any(not path.is_relative_to(source.parents[1].resolve()) for path in consumed):
        raise RuntimeError(f"{name} compiled a live input outside the frozen evidence tree")
    for item in frozen_records:
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"A frozen compiler header changed during {name}")

    executable = directory / "CitySiteSdkCommit.exe"
    link_response = directory / "link.rsp"
    link_response.write_text("\n".join([
        "/nologo", f'"{object_path}"', f'/OUT:"{executable}"',
        "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX",
    ]) + "\n", encoding="utf-8")
    call_tool([str(linker), f"@{link_response}"], directory, env, directory / "link.log")
    executed = subprocess.run([str(executable)], cwd=directory, env=env, capture_output=True,
                              creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
    output = (executed.stdout + executed.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
    log = directory / "execution.log"
    log.write_text(output, encoding="utf-8")
    match = re.search(r"^CITY_SITE_SDK_COMMIT_PASS checks=(\d+) SOURCE_SHAPED_MOCKS=true GAMECORE_LOADED=false$", output, re.M)
    if executed.returncode or not match or int(match.group(1)) < 35:
        raise RuntimeError(f"{name} component test failed; see {log}\n{output[-5000:]}")
    for item in frozen_records:
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError(f"A frozen compiler header changed during {name} execution")
    return {
        "configuration": name, "optimization": optimization, "standard": "C++14",
        "checks": int(match.group(1)), "executable": artifact(executable),
        "object": artifact(object_path), "compile_response": artifact(response),
        "link_response": artifact(link_response),
        "dependency_report": artifact(dependencies),
        "build_logs": [artifact(directory / "compile.log"), artifact(directory / "link.log")],
        "execution_log": artifact(log), "compiler_inputs_are_frozen": True,
        "source_shaped_mocks": True, "gamecore_loaded": False,
    }


def main() -> None:
    if len(sys.argv) > 1 and Path(sys.argv[1]).resolve() != Path(sys.executable).resolve():
        raise RuntimeError("Invoke this verifier with the requested Python interpreter")
    base_report_data = json.loads(BASE_REPORT.read_text(encoding="utf-8"))
    if base_report_data.get("build_id") != BASE_ID or base_report_data.get("status") != "CITY_SITE_SDK_CANDIDATE_PREPARED_NOT_BUILT":
        raise RuntimeError("Expected the frozen prepared, unbuilt candidate report")
    if digest(BASE_CANDIDATE) != base_report_data["candidate_source"]["sha256"]:
        raise RuntimeError("Prepared candidate source differs from its manifest hash")
    if digest(FROZEN_BUILDER) != base_report_data["builder"]["sha256"]:
        raise RuntimeError("Frozen builder differs from its manifest hash")
    frozen_rows = {row.get("original_path", "").lower(): row for row in base_report_data["frozen_inputs"]}
    sdk_original = str(PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvCitySpecializationAI.cpp").lower()
    sdk_row = frozen_rows.get(sdk_original)
    if sdk_row is None:
        raise RuntimeError("Candidate manifest does not identify frozen SDK source")
    sdk_input = Path(sdk_row["artifact"]["path"])
    if not sdk_input.is_file() or digest(sdk_input) != sdk_row["artifact"]["sha256"]:
        raise RuntimeError("Frozen source SDK helper input failed its manifest hash")
    bridge_original = str(BRIDGE_H).lower()
    bridge_row = frozen_rows.get(bridge_original)
    if bridge_row is None:
        raise RuntimeError("Candidate manifest does not identify the frozen bridge ABI header")
    bridge_input = Path(bridge_row["artifact"]["path"])
    if digest(bridge_input) != bridge_row["artifact"]["sha256"]:
        raise RuntimeError("Frozen bridge header failed its candidate manifest hash")

    run_id = unique_id()
    run_dir = BUILD_ROOT / run_id
    evidence = EVIDENCE_ROOT / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    snapshot = evidence / "frozen_inputs"
    snapshot.mkdir(parents=True, exist_ok=False)

    live_inputs = [BASE_REPORT, BASE_CANDIDATE, FROZEN_BUILDER, sdk_input, bridge_input,
                   SOURCE_TEMPLATE, BUILDER_LIVE, NATIVE_BUILD, COLLECT_BASELINE, VERIFIER]
    source_before = {str(path.resolve()): artifact(path) for path in live_inputs}
    frozen_records = []
    copy_map = [
        (BASE_REPORT, "provenance/build_result.json"),
        (BASE_CANDIDATE, "candidate/CvCitySpecializationAI.cpp"),
        (FROZEN_BUILDER, "tools/build_city_site_sdk_candidate.py"),
        (sdk_input, "sdk/CvCitySpecializationAI.cpp"),
        (bridge_input, "Source/Concurrency/CitySiteScoreBridge.h"),
        (SOURCE_TEMPLATE, "Tests/city_site_sdk_commit.cpp"),
        (BUILDER_LIVE, "tools/build_city_site_sdk_candidate_live.py"),
        (NATIVE_BUILD, "tools/native_build.py"),
        (COLLECT_BASELINE, "tools/collect_baseline.py"),
        (VERIFIER, "tools/verify_city_site_sdk_commit.py"),
    ]
    copied: dict[Path, Path] = {}
    for source, relative in copy_map:
        target = snapshot / relative
        frozen_records.append(copy_frozen(source, target))
        copied[source.resolve()] = target.resolve()

    generated_source = snapshot / "generated/city_site_sdk_commit.generated.cpp"
    generation = generate_harness(copied[FROZEN_BUILDER.resolve()], copied[sdk_input.resolve()],
                                  copied[BASE_CANDIDATE.resolve()], copied[SOURCE_TEMPLATE.resolve()],
                                  generated_source, snapshot / "tools")
    generated_record = {"original_path": "generated from exact frozen candidate and source spans",
                        **artifact(generated_source)}
    frozen_records.append(generated_record)

    compiler, linker, environment = initialize_msvc(run_dir / "environment")
    compiler_before, linker_before = artifact(compiler), artifact(linker)
    original_include_roots = [snapshot / "Source/Concurrency"]
    original_include_roots.extend(Path(value).resolve() for value in environment.get("INCLUDE", "").split(";")
                                  if value and Path(value).is_dir())
    discovery = compile_discovery(compiler, environment, generated_source,
                                  original_include_roots[0], run_dir / "dependency_discovery")
    discovery_hashes = {str(path): artifact(path) for path in discovery}
    mapping, frozen_include_roots, compiler_header_records = freeze_compiler_closure(
        discovery, snapshot, generated_source, original_include_roots)
    all_frozen_records = frozen_records + compiler_header_records
    for record in all_frozen_records:
        if digest(Path(record["path"])) != record["sha256"]:
            raise RuntimeError("Frozen component input failed pre-run hash check")
    configs = [
        compile_run("optimized_O2", "/O2", compiler, linker, environment, run_dir,
                    generated_source, frozen_include_roots, mapping, discovery, all_frozen_records),
        compile_run("unoptimized_Od", "/Od", compiler, linker, environment, run_dir,
                    generated_source, frozen_include_roots, mapping, discovery, all_frozen_records),
    ]
    source_after = {str(path.resolve()): artifact(path) for path in live_inputs}
    if source_before != source_after:
        raise RuntimeError("A live component source, builder, template, or provenance input changed during verification")
    if compiler_before != artifact(compiler) or linker_before != artifact(linker):
        raise RuntimeError("Compiler or linker executable changed during verification")
    for record in all_frozen_records:
        if digest(Path(record["path"])) != record["sha256"]:
            raise RuntimeError("Frozen component input failed post-run hash check")
    discovery_after = {str(path): artifact(Path(path)) for path in discovery_hashes}
    if discovery_hashes != discovery_after:
        raise RuntimeError("Live compiler dependency closure changed during verification")

    report = {
        "status": "CITY_SITE_SDK_COMMIT_ATOMICITY_CPP14_PASS",
        "run_id": run_id,
        "prepared_candidate": base_report_data["candidate_source"],
        "prepared_candidate_manifest": artifact(copied[BASE_REPORT.resolve()]),
        "source_extraction": generation,
        "source_hashes_before": source_before,
        "source_hashes_after": source_after,
        "dependency_discovery_inputs": discovery_hashes,
        "frozen_inputs": all_frozen_records,
        "compiler": compiler_before,
        "linker": linker_before,
        "compiler_settings": {
            "architecture": "x64", "standard": "C++14", "warning_level": "/W4",
            "warnings_as_errors": True, "optimization_runs": ["/O2", "/Od"],
            "runtime": "/MD", "floating_point": "/fp:strict",
            "compiler_and_linker_executable_hashes_checked_before_and_after": True,
            "compiler_helper_dlls_frozen": False, "link_libraries_frozen": False,
            "active_compiler_header_closure_frozen": True,
        },
        "configurations": configs,
        "scope": "PREPARED_FINDBESTSITES_AND_EXACT_ORIGINAL_SCALAR_HELPERS_IN_SOURCE_SHAPED_MOCKS; FAILURE_ATOMICITY_OWNER_LOCK_ORDER_SCALAR_EQUIVALENCE_AND_SINGLE_COMMIT_ONLY",
        "mock_scope": {
            "sdk_gc_map_player_plot_and_bridge_are_source_shaped_mocks": True,
            "bridge_implementation_is_mocked_and_fault_injected": True,
            "original_sdk_plot_value_helpers_are_exact_frozen_source": True,
            "candidate_helper_and_findbest_sites_are_exact_builder_output": True,
            "gamecore_loaded": False, "sdk_dll_built": False, "game_runtime_launched": False,
            "physical_multicore_or_performance_proof": False,
        },
    }
    destination = evidence / "conformance.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "run_id": run_id,
                      "checks": {row["configuration"]: row["checks"] for row in configs},
                      "evidence": artifact(destination), "gamecore_loaded": False}, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
