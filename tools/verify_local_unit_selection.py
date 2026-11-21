"""Run frozen-input local unit-selection model component tests only."""
from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT, digest
from native_build import environment_for, run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


SOURCE = PROJECT / "Tests/local_unit_selection.cpp"
HOST_INCLUDE = PROJECT / "Source/Host"
PORTING_INCLUDE = PROJECT / "Source/Porting"
SDK = PROJECT / "Source/SDK_BNW_x64"
OUTPUT_ROOT = PROJECT / "Build/LocalUnitSelection"
EVIDENCE_ROOT = PROJECT / "evidence/local_unit_selection"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
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
REQUIRED_HOST_HEADERS = [HOST_INCLUDE / "HostServices.h", HOST_INCLUDE / "LocalUnitSelection.h",
                         HOST_INCLUDE / "LocalSdkSession.h"]


def safe_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]


def freeze_copy(source: Path, target: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
    if digest(source) != digest(target):
        raise RuntimeError("Frozen input differs from source: " + str(source))
    return {"original_path": str(source.resolve()), **artifact(target)}


def unique_parent(path: Path, roots: list[Path]) -> Path | None:
    candidates = [root for root in roots if path.is_relative_to(root)]
    return max(candidates, key=lambda root: len(root.parts)) if candidates else None


def make_flags(source: Path, directory: Path, optimization: str, explicit_roots: list[Path],
               porting_root: Path, dependencies: Path, executable: Path) -> list[str]:
    flags = [
        "/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", optimization,
        "/MD", "/fp:strict", "/source-charset:windows-1252", "/external:W0",
        "/DWIN32", "/DNDEBUG", "/DFINAL_RELEASE", "/D_CRT_SECURE_NO_WARNINGS",
        "/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS",
        "/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING",
    ]
    flags.extend(f'/external:I"{path}"' for path in explicit_roots)
    flags.extend([f'/I"{porting_root}"', f'"{source}"', f'/Fo"{directory.as_posix()}/"',
                  f'/Fe"{executable}"', f'/sourceDependencies "{dependencies}"'])
    return flags


def compile_discovery(source: Path, explicit_roots: list[Path], porting_root: Path,
                      environment: dict, compiler: str, directory: Path) -> list[Path]:
    """Compile only to discover MSVC's exact active include closure before final builds."""
    directory.mkdir(parents=True, exist_ok=False)
    dependencies = directory / "dependencies.json"
    response = directory / "discovery.rsp"
    flags = make_flags(source, directory, "/O2", explicit_roots, porting_root,
                       dependencies, directory / "discovery.exe")
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    result = run([compiler, f"@{response}", "/link", "/INCREMENTAL:NO", "/MACHINE:X64",
                  "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF"],
                 cwd=directory, env=environment, timeout=180)
    output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    (directory / "discovery.log").write_text(output, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", output, re.I):
        raise RuntimeError("Dependency discovery compile failed:\n" + output[-6000:])
    value = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
    if Path(value["Source"]).resolve() != source.resolve():
        raise RuntimeError("Dependency discovery compiled an unexpected source")
    paths = [Path(value["Source"]), *(Path(item) for item in value["Includes"])]
    unique = {path.resolve() for path in paths}
    if any(not path.is_file() for path in unique):
        raise RuntimeError("Dependency discovery listed a missing compiler input")
    return sorted(unique, key=lambda path: str(path).casefold())


def freeze_compiler_inputs(inputs: list[Path], snapshot: Path, include_roots: list[Path],
                           environment_include_roots: list[Path], source_snapshot: Path) -> tuple[list[dict], list[Path], list[Path], list[Path]]:
    """Copy every discovered TU input and recreate include roots as frozen overlays."""
    all_roots = [root.resolve() for root in include_roots + environment_include_roots if root.is_dir()]
    root_targets: dict[Path, Path] = {}
    for index, root in enumerate(sorted(all_roots, key=lambda item: (len(item.parts), str(item).casefold()))):
        parents = [candidate for candidate in root_targets if root.is_relative_to(candidate)]
        if parents:
            parent = max(parents, key=lambda item: len(item.parts))
            root_targets[root] = root_targets[parent] / root.relative_to(parent)
        else:
            root_targets[root] = snapshot / "compiler_tree" / f"root_{index:03d}"
    frozen_paths = []
    records = []
    for path in inputs:
        resolved = path.resolve()
        if resolved.is_relative_to(snapshot.resolve()):
            relative = resolved.relative_to(snapshot.resolve())
            if relative == Path("Tests/local_unit_selection.cpp"):
                target = source_snapshot
            else:
                original = PROJECT / relative
                target = snapshot / relative
                if original.is_file():
                    if target.exists():
                        if digest(original) != digest(target):
                            raise RuntimeError("A frozen host input changed during dependency discovery: " + str(original))
                        records.append({"original_path": str(original.resolve()), **artifact(target)})
                    else:
                        records.append(freeze_copy(original, target))
                else:
                    # The discovery input is already one of the frozen entry headers.
                    records.append(artifact(target))
        else:
            matching_roots = [root for root in all_roots if resolved.is_relative_to(root)]
            owner = max(matching_roots, key=lambda root: len(root.parts)) if matching_roots else None
            if owner is None:
                # An unusual compiler input outside declared include roots is still
                # frozen under its own parent and exposed through that frozen parent.
                owner = resolved.parent
                root_targets.setdefault(owner, snapshot / "compiler_tree" / f"extra_{len(root_targets):03d}")
            target = root_targets[owner] / resolved.relative_to(owner)
            records.append(freeze_copy(resolved, target))
            for parent_root in matching_roots:
                if parent_root == owner:
                    continue
                alias = root_targets[parent_root] / resolved.relative_to(parent_root)
                records.append(freeze_copy(resolved, alias))
        frozen_paths.append(target.resolve())
    explicit_targets = [root_targets[root.resolve()] for root in include_roots]
    env_targets = [root_targets[root.resolve()] for root in environment_include_roots if root.resolve() in root_targets]
    known_roots = set(all_roots)
    extra_targets = [target for root, target in root_targets.items() if root not in known_roots]
    return records, explicit_targets, env_targets, extra_targets


def compile_and_run(name: str, optimization: str, *, run_directory: Path,
                    source: Path, frozen_explicit: list[Path], frozen_porting: Path,
                    frozen_environment_include: list[Path], environment: dict, compiler: str,
                    source_snapshot_root: Path, compiler_input_records: list[dict]) -> dict:
    directory = run_directory / name
    directory.mkdir(parents=True, exist_ok=False)
    environment = environment.copy()
    environment["VSLANG"] = "1033"
    if frozen_environment_include:
        environment["INCLUDE"] = ";".join(str(path) for path in frozen_environment_include)
    executable = directory / "LocalUnitSelection.exe"
    dependencies = directory / "dependencies.json"
    response = directory / "compile.rsp"
    flags = make_flags(source, directory, optimization, frozen_explicit, frozen_porting,
                       dependencies, executable)
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    response_before = digest(response)
    result = run([compiler, f"@{response}", "/link", "/INCREMENTAL:NO", "/MACHINE:X64",
                  "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF"],
                 cwd=directory, env=environment, timeout=180)
    output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    log = directory / "build.log"
    log.write_text(output, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", output, re.I):
        raise RuntimeError(f"{name} compile failed; see {log}\n{output[-6000:]}")
    if digest(response) != response_before:
        raise RuntimeError("Compiler response file changed during compilation")

    consumed = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
    inputs = [Path(item).resolve() for item in [consumed["Source"], *consumed["Includes"]]]
    if Path(consumed["Source"]).resolve() != source.resolve():
        raise RuntimeError(f"{name} compiled an unexpected frozen source")
    if any(not path.is_relative_to(source_snapshot_root.resolve()) for path in inputs):
        raise RuntimeError(f"{name} consumed a live compiler input outside the frozen tree")
    for record in compiler_input_records:
        if digest(Path(record["path"])) != record["sha256"]:
            raise RuntimeError("Frozen compiler input changed before execution")

    executed = run([executable], cwd=directory, env=environment, timeout=30)
    transcript = (executed.stdout + executed.stderr).decode("utf-8", errors="replace")
    transcript = transcript.replace("\r\n", "\n").replace("\r", "\n")
    run_log = directory / "execution.log"
    run_log.write_text(transcript, encoding="utf-8")
    match = re.search(r"^LOCAL_UNIT_SELECTION_PASS checks=(\d+) SDK_WRAPPER_MOCKED=true GAMECORE_LOADED=false$", transcript, re.M)
    if executed.returncode or not match or int(match.group(1)) < 15:
        raise RuntimeError(f"{name} component test failed; see {run_log}\n{transcript[-4000:]}")
    for record in compiler_input_records:
        if digest(Path(record["path"])) != record["sha256"]:
            raise RuntimeError("Frozen compiler input changed during execution")
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
        "compiler_inputs_are_frozen": True,
        "gamecore_loaded": False,
    }


def main():
    run_id = safe_id()
    run_directory = OUTPUT_ROOT / run_id
    evidence_directory = EVIDENCE_ROOT / run_id
    run_directory.mkdir(parents=True, exist_ok=False)
    evidence_directory.mkdir(parents=True, exist_ok=False)
    snapshot = evidence_directory / "frozen_inputs"

    host_headers = sorted(HOST_INCLUDE.glob("*.h"), key=lambda path: path.name.casefold())
    mandatory_live = [SOURCE, Path(__file__).resolve(), *REQUIRED_HOST_HEADERS]
    mandatory_live.extend(path for path in host_headers if path not in mandatory_live)
    live_before = {str(path.resolve()): digest(path) for path in mandatory_live}
    mandatory_records = [
        freeze_copy(SOURCE, snapshot / "Tests/local_unit_selection.cpp"),
        freeze_copy(Path(__file__).resolve(), snapshot / "tools/verify_local_unit_selection.py"),
    ]
    frozen_source = snapshot / "Tests/local_unit_selection.cpp"
    frozen_host = snapshot / "Source/Host"
    frozen_porting = snapshot / "Source/Porting"
    # Freeze the host header directory so quoted transitive includes cannot fall
    # back to live source while the dependency-discovery compile runs.
    for header in host_headers:
        mandatory_records.append(freeze_copy(header, frozen_host / header.name))

    environment, compiler = environment_for(VS, "x64", run_directory / "environment")
    include_environment = [Path(value).resolve() for value in environment.get("INCLUDE", "").split(";") if value]
    initial_explicit = [frozen_host, *SDK_INCLUDES]
    # The discovery pass compiles from the already frozen test/host entry points;
    # it does not execute its output. Its dependency manifest determines the
    # complete active compiler-input set to freeze before either test execution.
    discovery_inputs = compile_discovery(
        frozen_source, initial_explicit, PORTING_INCLUDE,
        environment, compiler, run_directory / "dependency_discovery")
    source_input_live = []
    for item in discovery_inputs:
        if item == frozen_source.resolve():
            source_input_live.append(SOURCE.resolve())
        elif item.is_relative_to(snapshot.resolve()):
            rel = item.relative_to(snapshot.resolve())
            source_input_live.append(PROJECT / rel)
        else:
            source_input_live.append(item)
    live_compiler_hashes = {str(path): digest(path) for path in source_input_live if path.is_file()}
    compiler_roots = [HOST_INCLUDE, *SDK_INCLUDES, PORTING_INCLUDE]
    compiler_records, frozen_include_roots, frozen_env_roots, frozen_extra_roots = freeze_compiler_inputs(
        discovery_inputs, snapshot, compiler_roots, include_environment, frozen_source)
    # Ensure core host files consumed by discovery are separately discoverable
    # in the preserved source list and all copied paths are present and stable.
    all_frozen_records = mandatory_records + compiler_records
    for record in all_frozen_records:
        if digest(Path(record["path"])) != record["sha256"]:
            raise RuntimeError("Frozen input failed its pre-run hash check")
    frozen_source_roots = snapshot / "compiler_tree"
    source_snapshot_root = snapshot.resolve()
    frozen_explicit = [frozen_host, *frozen_include_roots[1:-1], *frozen_extra_roots]
    frozen_porting = frozen_include_roots[-1]
    frozen_env_roots = [path for path in frozen_env_roots if path.exists()]
    rows = [
        compile_and_run("optimized", "/O2", run_directory=run_directory,
                        source=frozen_source, frozen_explicit=frozen_explicit,
                        frozen_porting=frozen_porting, frozen_environment_include=frozen_env_roots,
                        environment=environment, compiler=compiler,
                        source_snapshot_root=source_snapshot_root,
                        compiler_input_records=all_frozen_records),
        compile_and_run("debug", "/Od", run_directory=run_directory,
                        source=frozen_source, frozen_explicit=frozen_explicit,
                        frozen_porting=frozen_porting, frozen_environment_include=frozen_env_roots,
                        environment=environment, compiler=compiler,
                        source_snapshot_root=source_snapshot_root,
                        compiler_input_records=all_frozen_records),
    ]
    if rows[0]["checks"] != rows[1]["checks"]:
        raise RuntimeError("Optimized and debug component check counts differ")
    live_after = {path: digest(Path(path)) for path in live_before}
    if live_after != live_before:
        raise RuntimeError("A source/runner/required Host header changed during the check")
    live_compiler_hashes_after = {path: digest(Path(path)) for path in live_compiler_hashes
                                  if Path(path).is_file()}
    if live_compiler_hashes_after != live_compiler_hashes:
        raise RuntimeError("A live compiler input changed during the check")
    frozen_runner = next(item for item in mandatory_records if Path(item["path"]).name == "verify_local_unit_selection.py")
    report = {
        "status": "LOCAL_UNIT_SELECTION_FROZEN_INPUT_COMPONENT_PASS",
        "run_id": run_id,
        "builder": frozen_runner,
        "test_source": next(item for item in mandatory_records if Path(item["path"]).name == "local_unit_selection.cpp"),
        "required_host_headers": [item for item in mandatory_records if Path(item["path"]).suffix == ".h"],
        "frozen_compiler_inputs": compiler_records,
        "compiler_inputs_frozen_before_test_execution": True,
        "live_source_hashes_before": live_before,
        "live_source_hashes_after": live_after,
        "live_compiler_input_hashes_before": live_compiler_hashes,
        "live_compiler_input_hashes_after": live_compiler_hashes_after,
        "live_compiler_inputs_unchanged": True,
        "runs": rows,
        "native_checks": sum(row["checks"] for row in rows),
        "gamecore_loaded": False,
        "sdk_unit_wrapper_mocked": True,
        "local_sdk_session_guards_dynamically_verified": False,
        "scope": "FROZEN_LOCAL_UNIT_SELECTION_MODEL_AND_LOCAL_SDK_SESSION_HEADER_COMPILE_ONLY",
    }
    destination = evidence_directory / "conformance.json"
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    check_artifacts(report)
    check_artifacts(json.loads(destination.read_text(encoding="utf-8")))
    latest = EVIDENCE_ROOT / "conformance.json"
    latest.write_bytes(destination.read_bytes())
    print(json.dumps({"status": report["status"], "run_id": run_id,
                      "native_checks": report["native_checks"],
                      "evidence": artifact(destination), "gamecore_loaded": False,
                      "session_guards_dynamically_verified": False}))


if __name__ == "__main__":
    main()


