"""Build a frozen original-body oracle and exercise the owned found-value kernel."""
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
SDK_REL = Path("Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvSiteEvaluationClasses.cpp")
ACTIVE_SDK_REL = Path("Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvSiteEvaluationClasses.cpp")
HEADER_REL = Path("Source/Concurrency/FoundValueScores.h")
TEST_REL = Path("Tests/found_value_scores.cpp")
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")


def artifact(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}


def unique_id() -> str:
    return f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{uuid.uuid4().hex[:10]}"


def extract_function(source: str, signature: str) -> tuple[str, int]:
    start = source.find(signature)
    if start < 0:
        raise RuntimeError(f"Original SDK function not found: {signature}")
    brace = source.find("{", start)
    if brace < 0:
        raise RuntimeError("Original function has no body")
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
                    return source[start:index + 1], source.count("\n", 0, start) + 1
        index += 1
    raise RuntimeError("Original SDK function body is unterminated")


def init_msvc(directory: Path) -> tuple[dict[str, str], Path]:
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
        if "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            env[key.upper()] = value
            if key.upper() == "PATH": paths.append(value)
    env["PATH"] = ";".join(dict.fromkeys(part for value in paths for part in value.split(";")))
    compiler = next((Path(part) / "cl.exe" for part in env["PATH"].split(";")
                     if (Path(part) / "cl.exe").is_file()), None)
    if compiler is None: raise RuntimeError("MSVC compiler not found")
    return env, compiler.resolve()


def compile_source(compiler: Path, source: Path, include_root: Path, directory: Path,
                   optimization: str, dependencies: Path, env: dict[str, str]):
    directory.mkdir(parents=True, exist_ok=True)
    response = directory / "compile.rsp"
    flags = ["/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", "/permissive-",
             "/source-charset:.1252", optimization, "/MD", "/fp:strict",
             f'/I"{include_root.as_posix()}"', f'"{source.as_posix()}"',
             '/Fe"found_value_scores.exe"', f'/sourceDependencies "{dependencies.as_posix()}"']
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    command = [str(compiler), f"@{response}", "/link", "/INCREMENTAL:NO", "/MACHINE:X64",
               "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF", "/MAP:found_value_scores.map"]
    result = subprocess.run(command, cwd=directory, env=env, capture_output=True,
                            creationflags=subprocess.CREATE_NO_WINDOW, timeout=180)
    return result, response


def dependency_paths(path: Path) -> tuple[Path, list[Path]]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))["Data"]
    source = Path(data["Source"]).resolve()
    includes = sorted({Path(item).resolve() for item in data["Includes"]}, key=lambda p: str(p).casefold())
    if not source.is_file() or any(not item.is_file() for item in includes):
        raise RuntimeError("MSVC sourceDependencies listed a missing compiler input")
    return source, includes


def freeze_headers(inputs: list[Path], frozen_root: Path, project_root: Path,
                   include_roots: list[Path]) -> tuple[list[dict], list[Path]]:
    roots = [path.resolve() for path in include_roots if path.is_dir()]
    overlays = [frozen_root / f"include_{index:03d}" for index in range(len(roots))]
    for overlay in overlays: overlay.mkdir(parents=True, exist_ok=True)
    records: dict[str, dict] = {}
    for source in inputs:
        if source.is_relative_to(project_root.resolve()):
            records[str(source)] = {"original_path": str(source), **artifact(source)}
            continue
        owners = [index for index, root in enumerate(roots) if source.is_relative_to(root)]
        if not owners:
            raise RuntimeError("Compiler input is outside frozen project and INCLUDE roots: " + str(source))
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


def build_frozen_run(flavor: str, optimization: str, build_root: Path, compiler: Path,
                     source: Path, frozen_source_root: Path, frozen_includes: list[Path],
                     frozen_records: list[dict], compiler_record: dict,
                     module_records: list[dict], base_env: dict[str, str]) -> dict:
    directory = build_root / flavor
    dependencies = directory / "dependencies.json"
    env = base_env.copy()
    env["INCLUDE"] = ";".join(str(path) for path in frozen_includes)
    for record in frozen_records + [compiler_record] + module_records:
        if artifact(Path(record["path"]))["sha256"] != record["sha256"]:
            raise RuntimeError("A frozen source or toolchain input failed its precompile hash check")
    result, response = compile_source(compiler, source, frozen_source_root, directory,
                                     optimization, dependencies, env)
    text = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    log = directory / "build.log"
    log.write_text(text, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", text, re.I):
        raise RuntimeError(f"{flavor} build failed or emitted warnings; inspect {log}\n{text[-5000:]}")
    consumed_source, consumed_headers = dependency_paths(dependencies)
    frozen_roots = [frozen_source_root.resolve(), *(root.resolve() for root in frozen_includes)]
    consumed = [consumed_source, *consumed_headers]
    if consumed_source != source.resolve() or any(
            not any(path.is_relative_to(root) for root in frozen_roots) for path in consumed):
        raise RuntimeError("Final compile used a source/header outside the frozen compiler-input closure")
    exe = directory / "found_value_scores.exe"
    execution = subprocess.run([str(exe)], cwd=directory, env=env, capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW, timeout=45)
    transcript = (execution.stdout + execution.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
    run_log = directory / "execution.log"
    run_log.write_text(transcript, encoding="utf-8")
    match = re.search(r"^FOUND_VALUE_SCORES_PASS checks=(\d+) candidates=(\d+) workers=4 GAMECORE_LOADED=false SOURCE_ORACLE=EXTRACTED$",
                      transcript, re.M)
    if execution.returncode or not match:
        raise RuntimeError(f"{flavor} fixture failed; inspect {run_log}\n{transcript[-4000:]}")
    for record in frozen_records + [compiler_record] + module_records:
        if artifact(Path(record["path"]))["sha256"] != record["sha256"]:
            raise RuntimeError("A frozen source or toolchain input changed during build/run")
    return {"flavor": flavor, "optimization": optimization, "run_directory": str(directory),
            "executable": artifact(exe), "compile_response": artifact(response),
            "dependencies": artifact(dependencies), "build_log": artifact(log),
            "execution_log": artifact(run_log), "checks": int(match.group(1)),
            "candidates": int(match.group(2)), "source_dependencies": [artifact(path) for path in consumed],
            "source_dependencies_frozen": True, "gamecore_loaded": False}


def main() -> None:
    source = PROJECT / SDK_REL
    active_source = PROJECT / ACTIVE_SDK_REL
    header = PROJECT / HEADER_REL
    test = PROJECT / TEST_REL
    verifier = Path(__file__).resolve()
    original_bytes = source.read_bytes()
    active_bytes = active_source.read_bytes()
    if original_bytes != active_bytes:
        raise RuntimeError("Original and active x64 evaluator sources differ")
    original = original_bytes.decode("cp1252")
    source_record = artifact(source)
    active_source_record = artifact(active_source)
    header_record, test_record, verifier_record = map(artifact, (header, test, verifier))
    header.read_bytes().decode("ascii", errors="strict")
    identifier = unique_id()
    evidence = PROJECT / "evidence/found_value_scores" / identifier
    build = PROJECT / "Build/FoundValueScores" / identifier
    evidence.mkdir(parents=True)
    build.mkdir(parents=True)
    frozen = build / "frozen_inputs"
    frozen.mkdir()
    (frozen / "FoundValueScores.h").write_bytes(header.read_bytes())
    (frozen / "test_template.cpp").write_bytes(test.read_bytes())
    (frozen / "CvSiteEvaluationClasses.cpp").write_bytes(original_bytes)
    template = test.read_bytes().decode("ascii")
    marker = "// FOUND_VALUE_ORIGINAL_FUNCTION_BODIES"
    if template.count(marker) != 1:
        raise RuntimeError("Fixture must have exactly one original body insertion marker")
    base, base_line = extract_function(original, "int CvCitySiteEvaluator::PlotFoundValue(")
    settler, settler_line = extract_function(original, "int CvSiteEvaluatorForSettler::PlotFoundValue(")
    generated_text = template.replace(marker, base + "\n\n" + settler)
    generated = frozen / "found_value_scores_oracle.cpp"
    generated.write_bytes(generated_text.encode("cp1252"))
    oracle_record = {"original_source": source_record, "active_source": active_source_record,
                     "base_function_line": base_line, "base_function_bytes": len(base.encode("cp1252")),
                     "base_function_sha256": hashlib.sha256(base.encode("cp1252")).hexdigest(),
                     "settler_function_line": settler_line,
                     "settler_function_bytes": len(settler.encode("cp1252")),
                     "settler_function_sha256": hashlib.sha256(settler.encode("cp1252")).hexdigest(),
                     "compiler_input": artifact(generated), "function_text_extraction_exact": True,
                     "oracle_helpers": "TEST_FACADE_RETURNS_PRECOMPUTED_OWNED_OBSERVATIONS"}
    (evidence / "oracle_extraction.json").write_text(json.dumps(oracle_record, indent=2) + "\n", encoding="utf-8")
    env, compiler = init_msvc(build)
    include_roots = [Path(item).resolve() for item in env.get("INCLUDE", "").split(";") if item]
    discovery = build / "dependency_discovery"
    probe_deps = discovery / "dependencies.json"
    probe, probe_rsp = compile_source(compiler, generated, frozen, discovery, "/O2", probe_deps, env)
    probe_text = (probe.stdout + probe.stderr).decode("mbcs", errors="replace")
    (discovery / "build.log").write_text(probe_text, encoding="utf-8")
    if probe.returncode or re.search(r"\bwarning\s+C\d+", probe_text, re.I):
        raise RuntimeError("Compiler dependency discovery failed or emitted warnings: " + probe_text[-4000:])
    discovered_source, discovered_headers = dependency_paths(probe_deps)
    if discovered_source != generated.resolve():
        raise RuntimeError("Dependency probe compiled an unexpected generated oracle")
    frozen_deps = build / "frozen_dependencies"
    frozen_records, frozen_env_roots = freeze_headers(discovered_headers, frozen_deps, frozen.resolve(), include_roots)
    live_compiler = compiler.resolve()
    compiler_pre = artifact(live_compiler)
    toolchain = build / "frozen_toolchain"
    version_root = live_compiler.parents[3]
    frozen_version_root = toolchain / "VC/Tools/MSVC" / version_root.name
    compiler_directory = frozen_version_root / live_compiler.parent.relative_to(version_root)
    compiler_directory.mkdir(parents=True)
    frozen_compiler = compiler_directory / "cl.exe"
    shutil.copy2(live_compiler, frozen_compiler)
    compiler_record = {"original_path": str(live_compiler), **artifact(frozen_compiler)}
    if compiler_pre["sha256"] != compiler_record["sha256"]:
        raise RuntimeError("Frozen cl.exe copy does not match its source")
    module_records = []
    for name in ("c1.dll", "c1xx.dll", "mspdb140.dll", "mspdbcore.dll", "mspdbst.dll", "mspft140.dll", "link.exe"):
        original_module = live_compiler.with_name(name)
        if not original_module.is_file(): raise RuntimeError("MSVC compiler/link module missing: " + name)
        target = compiler_directory / name
        shutil.copy2(original_module, target)
        record = {"original_path": str(original_module), **artifact(target)}
        if artifact(original_module)["sha256"] != record["sha256"]:
            raise RuntimeError("Frozen compiler/link module differs from source: " + name)
        module_records.append(record)
    frozen_records += [{"original_path": str(generated), **artifact(generated)},
                       {"original_path": str(frozen / "FoundValueScores.h"), **artifact(frozen / "FoundValueScores.h")},
                       {"original_path": str(frozen / "test_template.cpp"), **artifact(frozen / "test_template.cpp")},
                       {"original_path": str(frozen / "CvSiteEvaluationClasses.cpp"), **artifact(frozen / "CvSiteEvaluationClasses.cpp")}]
    frozen_records = list({record["path"]: record for record in frozen_records}.values())
    runs = [build_frozen_run("optimized", "/O2", build, compiler, generated, frozen,
                             frozen_env_roots, frozen_records, compiler_record, module_records, env),
            build_frozen_run("debug", "/Od", build, compiler, generated, frozen,
                             frozen_env_roots, frozen_records, compiler_record, module_records, env)]
    if runs[0]["checks"] != runs[1]["checks"] or runs[0]["candidates"] != runs[1]["candidates"]:
        raise RuntimeError("O2 and Od differential totals differ")
    unchanged = all(artifact(path)["sha256"] == expected["sha256"] for path, expected in (
        (source, source_record), (active_source, active_source_record), (header, header_record),
        (test, test_record), (verifier, verifier_record)))
    if not unchanged: raise RuntimeError("A watched source input changed during verification")
    report = {"status": "FOUND_VALUE_SCORES_ORIGINAL_BODY_DIFFERENTIAL_PASS", "unique_id": identifier,
              "runs": runs, "source_inputs": [source_record, active_source_record, header_record, test_record, verifier_record],
              "oracle_extraction": artifact(evidence / "oracle_extraction.json"),
              "frozen_source_inputs": [artifact(path) for path in frozen.iterdir()],
              "dependency_probe": {"dependencies": artifact(probe_deps), "response": artifact(probe_rsp),
                                   "build_log": artifact(discovery / "build.log"),
                                   "discovered_count": 1 + len(discovered_headers)},
              "frozen_translation_unit_inputs": frozen_records,
              "final_compiler_copy": compiler_record, "executed_compiler": compiler_pre,
              "compiler_executed_copy": False, "compiler_modules": module_records,
              "compiler_and_module_hashes_checked_pre_post": True,
              "full_linker_runtime_and_system_library_closure_frozen": False,
              "source_inputs_unchanged_pre_post": True, "source_sdk_modified": False,
              "gamecore_loaded": False, "civ_v_runtime_tested": False,
              "scope": "OWNED_FOUND_VALUE_KERNEL_VS_EXACT_EXTRACTED_BASE_AND_SETTLER_FUNCTION_BODIES_WITH_HELPER_FACADE"}
    destination = evidence / "conformance.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "unique_id": identifier,
                      "checks_per_configuration": runs[0]["checks"], "candidates": runs[0]["candidates"],
                      "evidence": artifact(destination), "gamecore_loaded": False}))


if __name__ == "__main__":
    if len(sys.argv) > 1 and Path(sys.argv[1]).resolve() != Path(sys.executable).resolve():
        raise RuntimeError("Invoke this verifier with the requested Python interpreter")
    main()
