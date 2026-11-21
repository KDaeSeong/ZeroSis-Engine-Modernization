"""Compile an extracted-original differential fixture for the city-site value kernel."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
from datetime import datetime, timezone

PROJECT = Path(__file__).resolve().parents[1]
SDK = PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvCitySpecializationAI.cpp"
HEADER = PROJECT / "Source/Concurrency/CitySiteScores.h"
TEST = PROJECT / "Tests/city_site_scores.cpp"
SCHEDULER = PROJECT / "Source/Concurrency/OrderedBatch.h"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
EVIDENCE = PROJECT / "evidence/city_site_scores"


def artifact(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def mkdir_unique(parent: Path) -> Path:
    parent.mkdir(parents=True, exist_ok=True)
    while True:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        target = parent / f"{stamp}_{uuid.uuid4().hex[:10]}"
        try:
            target.mkdir()
            return target
        except FileExistsError:
            pass


def extract_function(source: str, signature: str) -> str:
    start = source.find(signature)
    if start < 0:
        raise RuntimeError(f"Original SDK helper not found: {signature}")
    brace = source.find("{", start)
    if brace < 0:
        raise RuntimeError("Original helper has no body")
    depth = 0
    state = "code"
    escaped = False
    index = brace
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if state == "line_comment":
            if char == "\n": state = "code"
        elif state == "block_comment":
            if char == "*" and nxt == "/": state = "code"; index += 1
        elif state in ("string", "char"):
            if escaped: escaped = False
            elif char == "\\": escaped = True
            elif (state == "string" and char == '"') or (state == "char" and char == "'"):
                state = "code"
        else:
            if char == "/" and nxt == "/": state = "line_comment"; index += 1
            elif char == "/" and nxt == "*": state = "block_comment"; index += 1
            elif char == '"': state = "string"
            elif char == "'": state = "char"
            elif char == "{": depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return source[start:index + 1]
        index += 1
    raise RuntimeError("Original helper body is unterminated")


def init_msvc(directory: Path) -> dict[str, str]:
    setup = directory / "initialize_msvc.cmd"
    setup.write_text('@echo off\n' + f'call "{VS / "VC/Auxiliary/Build/vcvars64.bat"}" >nul\n'
                     'if errorlevel 1 exit /b 1\nset\n', encoding="utf-8")
    result = subprocess.run(["cmd.exe", "/d", "/c", str(setup)], cwd=directory,
                            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
    if result.returncode:
        raise RuntimeError("MSVC x64 environment setup failed")
    env = {key.upper(): value for key, value in os.environ.items()}
    path_entries = []
    for line in result.stdout.decode("mbcs", errors="replace").splitlines():
        if "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            env[key.upper()] = value
            if key.upper() == "PATH": path_entries.append(value)
    env["PATH"] = ";".join(dict.fromkeys(part for value in path_entries for part in value.split(";")))
    compiler = next((Path(part) / "cl.exe" for part in env["PATH"].split(";")
                     if (Path(part) / "cl.exe").is_file()), None)
    if compiler is None: raise RuntimeError("MSVC compiler not found")
    env["CITY_SITE_COMPILER"] = str(compiler)
    return env


def build_run(flavor: str, optimization: str, root: Path, env: dict[str, str]) -> dict:
    run_dir = root / flavor
    run_dir.mkdir()
    exe = run_dir / "city_site_scores.exe"
    rsp = run_dir / "compile.rsp"
    generated = root / "frozen_inputs/city_site_scores_oracle.cpp"
    frozen_header = root / "frozen_inputs/CitySiteScores.h"
    frozen_scheduler = root / "frozen_inputs/OrderedBatch.h"
    flags = ["/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", optimization,
             "/MD", "/fp:strict", f'/I"{frozen_header.parent.as_posix()}"',
             f'"{generated.as_posix()}"', '/Fe"city_site_scores.exe"']
    rsp.write_text("\n".join(flags) + "\n", encoding="utf-8")
    command = [env["CITY_SITE_COMPILER"], f"@{rsp}", "/link", "/INCREMENTAL:NO", "/MACHINE:X64",
               "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF", "/MAP:city_site_scores.map"]
    result = subprocess.run(command, cwd=run_dir, env=env, capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
    build_log = run_dir / "build.log"
    build_text = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    build_log.write_text(build_text, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", build_text, re.I):
        raise RuntimeError(f"{flavor} compiler failed; inspect {build_log}\n{build_text[-5000:]}")
    execution = subprocess.run([str(exe)], cwd=run_dir, env=env, capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
    transcript = (execution.stdout + execution.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
    execution_log = run_dir / "execution.log"
    execution_log.write_text(transcript, encoding="utf-8")
    match = re.search(r"^CITY_SITE_SCORES_PASS checks=(\d+) jobs=(\d+) serial_workers_started=(\d+) workers_started=(\d+) GAMECORE_LOADED=false$",
                      transcript, re.M)
    if execution.returncode or not match:
        raise RuntimeError(f"{flavor} fixture failed; inspect {execution_log}\n{transcript[-3000:]}")
    return {"flavor": flavor, "optimization": optimization, "run_directory": str(run_dir),
            "executable": artifact(exe), "compile_response": artifact(rsp),
            "build_log": artifact(build_log), "execution_log": artifact(execution_log),
            "checks": int(match.group(1)), "jobs": int(match.group(2)),
            "scheduler_worker_counts": [int(match.group(3)), int(match.group(4))],
            "workers_started": int(match.group(4)), "gamecore_loaded": False,
            "compiler_inputs": [artifact(generated), artifact(frozen_header), artifact(frozen_scheduler)]}


def run_compile(compiler: Path, source: Path, include_root: Path, directory: Path,
                optimization: str, dependencies: Path, env: dict[str, str]) -> tuple[subprocess.CompletedProcess, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    response = directory / "compile.rsp"
    flags = ["/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", optimization,
             "/MD", "/fp:strict", f'/I"{include_root.as_posix()}"',
             f'"{source.as_posix()}"', '/Fe"city_site_scores.exe"',
             f'/sourceDependencies "{dependencies.as_posix()}"']
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    command = [str(compiler), f"@{response}", "/link", "/INCREMENTAL:NO", "/MACHINE:X64",
               "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF", "/MAP:city_site_scores.map"]
    return subprocess.run(command, cwd=directory, env=env, capture_output=True,
                          creationflags=subprocess.CREATE_NO_WINDOW, timeout=180), response


def dependency_paths(path: Path) -> tuple[Path, list[Path]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))["Data"]
    source = Path(data["Source"]).resolve()
    includes = sorted({Path(item).resolve() for item in data["Includes"]}, key=lambda p: str(p).casefold())
    if not source.is_file() or any(not item.is_file() for item in includes):
        raise RuntimeError("MSVC sourceDependencies listed a missing compiler input")
    return source, includes


def freeze_discovered_headers(inputs: list[Path], frozen_root: Path,
                              source_root: Path, environment_roots: list[Path]) -> tuple[list[dict], list[Path]]:
    roots = [path.resolve() for path in environment_roots if path.is_dir()]
    overlays = [frozen_root / f"include_{index:03d}" for index in range(len(roots))]
    for overlay in overlays: overlay.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict] = {}
    for source in inputs:
        if source.is_relative_to(source_root.resolve()):
            records[str(source)] = {"original_path": str(source), **artifact(source)}
            continue
        owners = [index for index, root in enumerate(roots) if source.is_relative_to(root)]
        if not owners:
            raise RuntimeError("Discovered header is outside frozen source and INCLUDE roots: " + str(source))
        for index in owners:
            target = overlays[index] / source.relative_to(roots[index])
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                if artifact(target)["sha256"] != artifact(source)["sha256"]:
                    raise RuntimeError("Conflicting compiler headers map to one frozen path")
            else:
                shutil.copy2(source, target)
            records[str(target.resolve())] = {"original_path": str(source), **artifact(target)}
    return list(records.values()), overlays


def build_frozen_run(flavor: str, optimization: str, root: Path, compiler: Path,
                     source: Path, source_include: Path, frozen_environment: list[Path],
                     frozen_records: list[dict], compiler_record: dict,
                     compiler_module_records: list[dict], environment: dict[str, str]) -> dict:
    directory = root / flavor
    directory.mkdir()
    dependencies = directory / "dependencies.json"
    env = environment.copy()
    env["INCLUDE"] = ";".join(str(path) for path in frozen_environment)
    for record in frozen_records:
        if artifact(Path(record["path"]))["sha256"] != record["sha256"]:
            raise RuntimeError("Frozen compiler input failed its precompile hash check")
    if artifact(compiler)["sha256"] != compiler_record["sha256"]:
        raise RuntimeError("Frozen compiler binary failed its precompile hash check")
    for record in compiler_module_records:
        if artifact(Path(record["path"]))["sha256"] != record["sha256"]:
            raise RuntimeError("Frozen compiler/linker module failed its precompile hash check")
    result, response = run_compile(compiler, source, source_include, directory,
                                   optimization, dependencies, env)
    build_text = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    build_log = directory / "build.log"
    build_log.write_text(build_text, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", build_text, re.I):
        raise RuntimeError(f"{flavor} frozen compile failed; inspect {build_log}\n{build_text[-5000:]}")
    consumed_source, consumed_headers = dependency_paths(dependencies)
    frozen_roots = [source_include.resolve(), *(path.resolve() for path in frozen_environment)]
    consumed = [consumed_source, *consumed_headers]
    if any(not any(path.is_relative_to(frozen) for frozen in frozen_roots) for path in consumed):
        raise RuntimeError("Final compiler consumed a live source/header outside the frozen dependency tree")
    consumed_artifacts = [artifact(path) for path in consumed]
    if consumed_source != source.resolve():
        raise RuntimeError("Final compiler did not compile the frozen generated oracle")
    if artifact(compiler)["sha256"] != compiler_record["sha256"]:
        raise RuntimeError("Frozen compiler binary changed during compile")
    for record in compiler_module_records:
        if artifact(Path(record["path"]))["sha256"] != record["sha256"]:
            raise RuntimeError("Frozen compiler/linker module changed during compile")
    for record in frozen_records:
        if artifact(Path(record["path"]))["sha256"] != record["sha256"]:
            raise RuntimeError("A frozen compiler input changed during compilation")
    exe = directory / "city_site_scores.exe"
    execution = subprocess.run([str(exe)], cwd=directory, env=env, capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
    transcript = (execution.stdout + execution.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
    execution_log = directory / "execution.log"
    execution_log.write_text(transcript, encoding="utf-8")
    match = re.search(r"^CITY_SITE_SCORES_PASS checks=(\d+) jobs=(\d+) serial_workers_started=(\d+) workers_started=(\d+) GAMECORE_LOADED=false$",
                      transcript, re.M)
    if execution.returncode or not match:
        raise RuntimeError(f"{flavor} frozen fixture failed; inspect {execution_log}\n{transcript[-3000:]}")
    for record in frozen_records:
        if artifact(Path(record["path"]))["sha256"] != record["sha256"]:
            raise RuntimeError("A frozen compiler input changed during execution")
    if artifact(compiler)["sha256"] != compiler_record["sha256"]:
        raise RuntimeError("Frozen compiler binary changed during execution")
    for record in compiler_module_records:
        if artifact(Path(record["path"]))["sha256"] != record["sha256"]:
            raise RuntimeError("Frozen compiler/linker module changed during execution")
    return {"flavor": flavor, "optimization": optimization, "run_directory": str(directory),
            "executable": artifact(exe), "compiler": artifact(compiler),
            "compile_response": artifact(response), "dependency_report": artifact(dependencies),
            "build_log": artifact(build_log), "execution_log": artifact(execution_log),
            "checks": int(match.group(1)), "jobs": int(match.group(2)),
            "scheduler_worker_counts": [int(match.group(3)), int(match.group(4))],
            "workers_started": int(match.group(4)), "compiler_input_count": len(consumed),
            "compiler_inputs": consumed_artifacts, "compiler_inputs_are_frozen": True,
            "compiler_binary_archive_hash_verified": True,
            "executed_compiler_hash_matches_archive": artifact(compiler)["sha256"] == compiler_record["sha256"],
            "compiler_binary_record": compiler_record,
            "compiler_module_records": compiler_module_records,
            "gamecore_loaded": False}


def main() -> None:
    original = SDK.read_bytes().decode("cp1252")
    sdk_artifact = artifact(SDK)
    header_artifact, test_artifact, scheduler_artifact, verifier_artifact = map(
        artifact, (HEADER, TEST, SCHEDULER, Path(__file__).resolve()))
    root = mkdir_unique(EVIDENCE)
    frozen = root / "frozen_inputs"
    frozen.mkdir()
    (frozen / "CitySiteScores.h").write_bytes(HEADER.read_bytes())
    (frozen / "OrderedBatch.h").write_bytes(SCHEDULER.read_bytes())
    (frozen / "test_template.cpp").write_bytes(TEST.read_bytes())
    (frozen / "CvCitySpecializationAI.cpp").write_bytes(SDK.read_bytes())
    template = TEST.read_bytes().decode("utf-8-sig")
    marker = "// CITY_SITE_ORIGINAL_HELPERS"
    if template.count(marker) != 1: raise RuntimeError("Fixture must have exactly one oracle insertion marker")
    specific = extract_function(original, "int CvCitySpecializationAI::PlotValueForSpecificYield(")
    science = extract_function(original, "int CvCitySpecializationAI::PlotValueForScience(")
    if not specific or not science: raise RuntimeError("Original helper extraction failed")
    generated_text = template.replace(marker, specific + "\n\n" + science)
    generated = frozen / "city_site_scores_oracle.cpp"
    generated.write_text(generated_text, encoding="utf-8")
    oracle_record = {"source": sdk_artifact, "specific_helper_sha256": hashlib.sha256(specific.encode()).hexdigest(),
                     "science_helper_sha256": hashlib.sha256(science.encode()).hexdigest(),
                     "specific_helper_bytes": len(specific.encode()), "science_helper_bytes": len(science.encode()),
                     "compiler_input": artifact(generated), "extraction_exact_source_text": True}
    (root / "oracle_extraction.json").write_text(json.dumps(oracle_record, indent=2) + "\n", encoding="utf-8")
    env = init_msvc(root)
    live_compiler = Path(env["CITY_SITE_COMPILER"]).resolve()
    original_include_roots = [Path(item).resolve() for item in env.get("INCLUDE", "").split(";") if item]
    discovery_dir = root / "dependency_discovery"
    discovery_dependencies = discovery_dir / "dependencies.json"
    probe, probe_response = run_compile(live_compiler, generated, frozen, discovery_dir,
                                        "/O2", discovery_dependencies, env)
    probe_text = (probe.stdout + probe.stderr).decode("mbcs", errors="replace")
    (discovery_dir / "build.log").write_text(probe_text, encoding="utf-8")
    if probe.returncode or re.search(r"\bwarning\s+C\d+", probe_text, re.I):
        raise RuntimeError("MSVC /sourceDependencies discovery compile failed: " + probe_text[-4000:])
    discovered_source, discovered_headers = dependency_paths(discovery_dependencies)
    if discovered_source != generated.resolve():
        raise RuntimeError("Dependency probe compiled an unexpected generated oracle")
    frozen_deps = root / "frozen_dependencies"
    frozen_records, frozen_env_roots = freeze_discovered_headers(
        discovered_headers, frozen_deps, frozen.resolve(), original_include_roots)
    compiler_pre = artifact(live_compiler)
    frozen_toolchain = root / "frozen_toolchain"
    live_version_root = live_compiler.parents[3]
    frozen_version_root = frozen_toolchain / "VC/Tools/MSVC" / live_version_root.name
    frozen_compiler_directory = frozen_version_root / live_compiler.parent.relative_to(live_version_root)
    frozen_compiler_directory.mkdir(parents=True)
    frozen_compiler = frozen_compiler_directory / "cl.exe"
    shutil.copy2(live_compiler, frozen_compiler)
    compiler_record = {"original_path": str(live_compiler), **artifact(frozen_compiler)}
    if compiler_pre["sha256"] != compiler_record["sha256"]:
        raise RuntimeError("Frozen compiler binary differs from the discovered compiler")
    compiler_module_records = []
    for name in ("c1.dll", "c1xx.dll", "mspdb140.dll", "mspdbcore.dll", "mspdbst.dll", "mspft140.dll", "link.exe"):
        original = live_compiler.with_name(name)
        if not original.is_file():
            raise RuntimeError("Required adjacent MSVC compile/link module is missing: " + name)
        target = frozen_compiler_directory / name
        shutil.copy2(original, target)
        record = {"original_path": str(original), **artifact(target)}
        if artifact(original)["sha256"] != record["sha256"]:
            raise RuntimeError("Frozen MSVC module differs from its source: " + name)
        compiler_module_records.append(record)
    # The test TU and its two project headers are frozen in frozen_inputs; system
    # headers resolve only through these frozen INCLUDE overlays in final passes.
    frozen_records.append({"original_path": str(generated.resolve()), **artifact(generated)})
    frozen_records.append({"original_path": str(frozen / "CitySiteScores.h"),
                           **artifact(frozen / "CitySiteScores.h")})
    frozen_records.append({"original_path": str(frozen / "OrderedBatch.h"),
                           **artifact(frozen / "OrderedBatch.h")})
    frozen_records = list({record["path"]: record for record in frozen_records}.values())
    for record in frozen_records:
        if artifact(Path(record["path"]))["sha256"] != record["sha256"]:
            raise RuntimeError("A frozen source/header failed its pre-run hash check")
    # The standalone copy cannot resolve MSVC's private mspdbcore loader in this
    # environment. Execute the byte-identical installed compiler, while compiling
    # only against the frozen source/header closure and checking its hash before/after.
    frozen_env = env.copy()
    runs = [
        build_frozen_run("optimized", "/O2", root, live_compiler, generated, frozen,
                         frozen_env_roots, frozen_records, compiler_record, compiler_module_records, frozen_env),
        build_frozen_run("debug", "/Od", root, live_compiler, generated, frozen,
                         frozen_env_roots, frozen_records, compiler_record, compiler_module_records, frozen_env),
    ]
    if runs[0]["checks"] != runs[1]["checks"] or runs[0]["jobs"] != runs[1]["jobs"] or \
       runs[0]["scheduler_worker_counts"] != runs[1]["scheduler_worker_counts"]:
        raise RuntimeError("O2 and Od conformance totals differ")
    unchanged = all(artifact(path)["sha256"] == expected["sha256"] for path, expected in (
        (SDK, sdk_artifact), (HEADER, header_artifact), (TEST, test_artifact),
        (SCHEDULER, scheduler_artifact), (Path(__file__).resolve(), verifier_artifact)))
    if not unchanged: raise RuntimeError("An input changed while the isolated fixture was running")
    report = {"status": "CITY_SITE_SCORE_ORIGINAL_DIFFERENTIAL_PASS", "runs": runs,
              "source_inputs": [sdk_artifact, header_artifact, test_artifact, scheduler_artifact, verifier_artifact],
              "frozen_inputs": [artifact(path) for path in frozen.iterdir()],
              "oracle_extraction": artifact(root / "oracle_extraction.json"),
              "dependency_probe": {"report": artifact(discovery_dependencies),
                                   "compile_response": artifact(probe_response),
                                   "build_log": artifact(discovery_dir / "build.log"),
                                   "source_dependency_count": 1 + len(discovered_headers),
                                   "discovered_headers": [{"original_path": str(path), "sha256": artifact(path)["sha256"],
                                                           "size": path.stat().st_size}
                                                          for path in discovered_headers]},
              "frozen_translation_unit_inputs": frozen_records,
              "translation_unit_source_dependencies_frozen": True,
              "final_compiler_binary": compiler_record,
              "compiler_execution_path": str(live_compiler),
              "compiler_copy_executed": False,
              "compiler_execution_binary_matches_frozen_archive": compiler_pre["sha256"] == compiler_record["sha256"],
              "frozen_compiler_link_modules": compiler_module_records,
              "compiler_binary_source_pre_hash": compiler_pre,
              "compiler_binary_frozen_hash_verified": True,
              "full_compiler_linker_runtime_closure_frozen": False,
              "provenance_limit": "All final /sourceDependencies source/header inputs are frozen and hashed. A matching cl.exe copy is frozen and hashed; the installed byte-identical cl.exe was executed because the isolated copy could not load mspdbcore.dll. Linker, compiler helper DLLs, and link libraries remain toolchain environment inputs and are not claimed frozen.",
              "source_inputs_unchanged_before_after": True, "active_source_sdk_modified": False,
              "active_scheduler_modified": False, "component_ordered_batch_four_worker_determinism": True,
              "component_scheduler_worker_counts_compared": [1, 4],
              "production_alias_or_callsite_changed": False,
              "localization_inputs_in_kernel_or_fixture": False,
              "english_korean_localization_runtime_tested": False,
              "arithmetic_contract": {
                  "original_types": "int operands, accumulators, and return values; Win64 MSVC int is 32-bit signed",
                  "original_overflow_behavior": "signed overflow is undefined behavior; source has no saturation or overflow recovery",
                  "candidate_valid_domain": "every original intermediate (science FOOD+SCIENCE, each yield*multiplier, each accumulation, final science sum) fits int32",
                  "out_of_domain_behavior": "return Status::overflow before exposing a value; no clamp or wrap",
                  "numeric_input_bounds_proven_from_source": False,
                  "multiplier_transition": "starts at zero per helper; foreign ownership resets to zero; supported ring distance updates; unsupported distance retains prior multiplier"
              },
              "gamecore_loaded": False,
              "scope": "PURE_CITY_SITE_PLOT_VALUE_KERNEL_VS_EXACT_EXTRACTED_SDK_HELPERS; NOT_GAMECORE_OR_MULTICORE_ACCEPTANCE"}
    destination = root / "conformance.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": runs[0]["checks"],
                      "evidence": artifact(destination), "gamecore_loaded": False}))


if __name__ == "__main__":
    main()
