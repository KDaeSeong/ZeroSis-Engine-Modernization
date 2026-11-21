"""Compile and run the production art selector without SDK, GPU or a window."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from native_build import environment_for, run
from collect_baseline import pe_header

PROJECT = Path(__file__).resolve().parents[1]
STAGE = PROJECT / "evidence/unit_models/civilian_start"
SCOPE_SHA = "943746d6cc04cd175bc5f63d95bbf94d7bc0efd6a186bfabd2578a1444853785"
INPUTS = (
    "Tests/world_unit_art_selection.cpp",
    "Source/Presentation/WorldUnitArtSelection.h",
    "Source/Presentation/WorldTerrainRenderer.cpp",
    "tools/verify_world_unit_art_selection.py",
    "tools/native_build.py", "tools/collect_baseline.py",
)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def artifact(path):
    path = Path(path)
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--vs", type=Path, default=Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"))
    args = parser.parse_args()
    require(re.fullmatch(r"[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}", args.run_id), "Invalid run identity")
    scope_path = STAGE / "scope.json"
    require(artifact(scope_path)["sha256"] == SCOPE_SHA, "Reviewed civilian scope changed")
    scope = json.loads(scope_path.read_text(encoding="utf-8"))
    require(scope["original_game_new_mod_test_hold"], "Original mod test hold must remain active")
    for key in ("host_execution_allowed", "gamecore_execution_allowed", "native_window_execution_allowed", "retail_mods_access_allowed"):
        require(scope["deployment"][key] is False, "Scope execution boundary differs: " + key)
    before = [artifact(PROJECT / name) for name in INPUTS]
    build = PROJECT / "Build/WorldUnitArtSelection" / args.run_id
    evidence = STAGE / args.run_id
    for root in (build, evidence):
        require(not root.exists(), "Do not overwrite or replay an existing run")
        require(root.resolve() == root.absolute() and root.resolve().is_relative_to(PROJECT), "Output crosses project/reparse boundary")
        root.mkdir(parents=True)
    report = {"schema": "zerosis.world_unit.art_selection_component.v1", "status": "STARTED",
              "created_utc": datetime.now(timezone.utc).isoformat(), "scope": artifact(scope_path),
              "inputs": before, "variants": [], "host_executed": False, "gamecore_loaded": False,
              "hwnd_created": False, "gpu_used": False, "retail_user_state_accessed": False,
              "game_process_queried": False, "native_acceptance_verified": False}
    failure = None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetErrorMode.argtypes, kernel32.SetErrorMode.restype = [ctypes.c_uint], ctypes.c_uint
        kernel32.WerSetFlags.argtypes, kernel32.WerSetFlags.restype = [ctypes.c_ulong], ctypes.c_long
        old = kernel32.SetErrorMode(32771)
        hr = kernel32.WerSetFlags(32)
        report["runner_error_ui"] = {"dll": "kernel32", "error_mode": 32771, "previous_error_mode": old, "wer_flags": 32, "wer_hresult": hr}
        require(hr >= 0, "WerSetFlags failed before any child launch")
        environment, compiler_text = environment_for(args.vs, "x64", build / "environment")
        compiler = Path(compiler_text)
        environment["VSLANG"] = "1033"
        environment.pop("CL", None)
        environment.pop("_CL_", None)
        report["compiler"] = artifact(compiler)
        source, header = (PROJECT / INPUTS[i] for i in (0, 1))
        for name, optimization in (("optimized", "/O2"), ("unoptimized", "/Od")):
            directory = build / name
            directory.mkdir()
            exe, obj, dependencies = (directory / value for value in ("world_unit_art_selection.exe", "world_unit_art_selection.obj", "dependencies.json"))
            response = directory / "compile.rsp"
            flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/utf-8", "/fp:strict", "/MT", optimization,
                     f'"{source}"', f'/Fo"{obj}"', f'/Fe"{exe}"', f'/sourceDependencies "{dependencies}"']
            response.write_text("\n".join(flags) + "\n", encoding="utf-8")
            compiled = run([compiler, "@" + str(response), "/link", "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF"], cwd=directory, env=environment, timeout=180)
            log = directory / "compile.log"
            log.write_bytes(compiled.stdout + compiled.stderr)
            require(compiled.returncode == 0 and not re.search(r"\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+", (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace"), re.I), "Component compile failed or warned: " + str(log))
            consumed = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
            consumed_paths = [Path(consumed["Source"]), *(Path(value) for value in consumed["Includes"])]
            project_inputs = {value.resolve() for value in consumed_paths if value.resolve().is_relative_to(PROJECT)}
            require(project_inputs == {source.resolve(), header.resolve()}, "Fixture must compile the actual production helper only")
            require(not any("SDK_BNW" in str(value) or "GameCore" in str(value) for value in consumed_paths), "Fixture consumed SDK/GameCore source")
            pe = pe_header(exe)
            require(pe["architecture"] == "x64" and pe["pe_format"] == "PE32+" and not pe["is_dll"], "Unexpected fixture PE")
            inspected = run([compiler.with_name("dumpbin.exe"), "/dependents", exe], cwd=directory, env=environment, timeout=30)
            imports_log = directory / "imports.log"
            imports_log.write_bytes(inspected.stdout + inspected.stderr)
            imports = re.findall(r"^\s+([\w.-]+\.dll)\s*$", inspected.stdout.decode("ascii", errors="replace"), re.M | re.I)
            require(inspected.returncode == 0 and imports and all(value.lower() == "kernel32.dll" for value in imports), "Unexpected fixture DLL imports")
            executed = run([exe], cwd=directory, env=environment, timeout=30)
            execution_log = directory / "execution.log"
            execution_log.write_bytes(executed.stdout + executed.stderr)
            require(executed.returncode == 0 and not executed.stderr, "Fixture failed: " + str(execution_log))
            result = json.loads(executed.stdout.decode("utf-8"))
            require(result.get("status") == "PASS_WORLD_UNIT_ART_SELECTION" and isinstance(result.get("checks"), int) and isinstance(result.get("cases"), int) and result["checks"] >= result["cases"] >= 10, "Incomplete production art selection coverage")
            report["variants"].append({"optimization": optimization, "checks": result["checks"], "cases": result["cases"], "response": artifact(response), "compile_log": artifact(log), "dependencies": artifact(dependencies), "executable": {**artifact(exe), "pe": pe}, "object": artifact(obj), "imports": imports, "imports_log": artifact(imports_log), "execution_log": artifact(execution_log), "exit_code": executed.returncode, "compiler_and_linker_warnings": 0})
        require(len({(value["checks"], value["cases"]) for value in report["variants"]}) == 1, "Optimizations covered different cases")
        require(before == [artifact(PROJECT / name) for name in INPUTS], "Production or fixture inputs changed during validation")
        require(report["compiler"] == artifact(compiler) and report["scope"] == artifact(scope_path), "Compiler or scope changed")
        report["inputs_unchanged"] = True
        report["status"] = "PASS_HEADLESS_PRODUCTION_WORLD_UNIT_ART_SELECTION"
    except Exception as error:
        report["status"] = "FAILED"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        failure = error
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    result_path = evidence / "result.json"
    with result_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "report": artifact(result_path), "variants": [{key: row[key] for key in ("optimization", "checks", "cases")} for row in report["variants"]], "native_acceptance_verified": False}))
    if failure is not None:
        raise failure


if __name__ == "__main__":
    main()
