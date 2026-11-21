"""Exercise actual HostServices with SDK adapters mocked; reuse a retained Host input tree."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

from collect_baseline import PROJECT, pe_header
from native_build import environment_for, run


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def artifact(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-id", required=True)
    parser.add_argument("--evidence-name", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}", args.host_id):
        raise ValueError("Invalid retained Host identity")
    if not re.fullmatch(r"[A-Za-z0-9_]+", args.evidence_name):
        raise ValueError("Invalid evidence folder name")
    evidence = PROJECT / "evidence/unit_panel_integration" / args.evidence_name
    output = evidence / "component"
    output.mkdir(parents=True, exist_ok=False)
    report_path = PROJECT / "evidence/ui_window_host" / args.host_id / "build_result.json"
    base = json.loads(report_path.read_text(encoding="utf-8"))
    if base["status"] != "UI_WINDOW_HOST_CANDIDATE_BUILT" or not base["source_inputs_unchanged"]:
        raise RuntimeError("Retained Host is not a completed immutable input baseline")
    base_records = {str(Path(row["path"])).casefold(): row for row in base["compiler_inputs"]}
    for row in base_records.values():
        if digest(Path(row["path"])) != row["sha256"]:
            raise RuntimeError("Retained compiler input changed: " + row["path"])
    response_path = Path(base["response"]["path"])
    if digest(response_path) != base["response"]["sha256"]:
        raise RuntimeError("Retained compiler response changed")
    source = PROJECT / "Tests/selection_camera.cpp"
    header = PROJECT / "Source/Host/HostServices.h"
    snapshots = output / "changed_inputs"
    snapshots.mkdir()
    frozen_test = snapshots / source.name
    frozen_header = snapshots / header.name
    frozen_tool = snapshots / Path(__file__).name
    copied = []
    for live, frozen in ((source, frozen_test), (header, frozen_header), (Path(__file__), frozen_tool)):
        before = artifact(live)
        shutil.copy2(live, frozen)
        if digest(frozen) != before["sha256"]:
            raise RuntimeError("Changed input snapshot differs from source")
        copied.append({"original": before, "frozen": artifact(frozen)})

    lua_report_path = PROJECT / "evidence/lua_provider/build_result.json"
    lua_report = json.loads(lua_report_path.read_text(encoding="utf-8"))
    library = lua_report["library"]
    library_path = Path(library["path"])
    if digest(library_path) != library["sha256"]:
        raise RuntimeError("Static Lua component link input changed")
    environment, compiler_text = environment_for(
        Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"), "x64", output / "environment")
    compiler = Path(compiler_text)
    if digest(compiler) != base["compiler"]["sha256"]:
        raise RuntimeError("Component compiler differs from retained Host compiler")
    environment["INCLUDE"] = ""
    environment["VSLANG"] = "1033"
    inherited = response_path.read_text(encoding="utf-8").splitlines()
    flags = inherited[:inherited.index("/c")]
    flags = [value for value in flags if value not in ("/DZEROSIS_SHARED_LUA_RUNTIME=1", "/DLUA_BUILD_AS_DLL")]
    flags.insert(0, f'/I"{snapshots}"')
    executable = output / "selection_camera.exe"
    object_path = output / "selection_camera.obj"
    dependencies = output / "dependencies.json"
    flags += [f'"{frozen_test}"', f'"{library_path}"', f'/Fo"{object_path}"',
              f'/Fe"{executable}"', f'/sourceDependencies "{dependencies}"']
    response = output / "compile.rsp"
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    built = run([compiler, "@" + str(response), "/link", "/INCREMENTAL:NO", "/MACHINE:X64",
                 "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF"], cwd=output, env=environment, timeout=180)
    build_log = output / "compile.log"
    build_log.write_bytes(built.stdout + built.stderr)
    decoded_build = (built.stdout + built.stderr).decode("mbcs", errors="replace")
    if built.returncode or re.search(r"\bwarning\s+[A-Z]+[0-9]+", decoded_build):
        raise RuntimeError("Selection camera component compile failed: " + decoded_build[-4000:])
    consumed = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
    inputs = [Path(consumed["Source"]), *(Path(path) for path in consumed["Includes"])]
    owned = {str(Path(row["frozen"]["path"])).casefold(): row["frozen"] for row in copied}
    records = []
    for path in inputs:
        key = str(path).casefold()
        expected = owned.get(key, base_records.get(key))
        if expected is None or digest(path) != expected["sha256"]:
            raise RuntimeError("Component consumed an unexpected or changed compiler input: " + str(path))
        records.append(artifact(path))
    actual_inputs = {str(path).casefold() for path in inputs}
    if str(frozen_header).casefold() not in actual_inputs or str(frozen_test).casefold() not in actual_inputs:
        raise RuntimeError("Actual changed header and test were not consumed")
    old_header = next(row["path"] for row in base["compiler_inputs"]
                      if row.get("relative_path", "").replace("\\", "/") == "Source/Host/HostServices.h")
    if old_header.casefold() in actual_inputs:
        raise RuntimeError("Component consumed the superseded HostServices header")

    imports_result = run([compiler.with_name("dumpbin.exe"), "/dependents", executable],
                         cwd=output, env=environment, timeout=30)
    imports_log = output / "imports.log"
    imports_log.write_bytes(imports_result.stdout + imports_result.stderr)
    imports = re.findall(r"^\s+([\w.-]+\.dll)\s*$", imports_result.stdout.decode("ascii", errors="replace"), re.M | re.I)
    allowed = {"kernel32.dll", "msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll", "bcrypt.dll"}
    if imports_result.returncode or not imports or any(
            value.lower() not in allowed and not value.lower().startswith("api-ms-win-crt-") for value in imports):
        raise RuntimeError("Unexpected component import: " + str(imports))
    executed = run([executable], cwd=output, env=environment, timeout=30)
    execution_log = output / "execution.log"
    execution_log.write_bytes(executed.stdout + executed.stderr)
    transcript = (executed.stdout + executed.stderr).decode("utf-8", errors="replace")
    match = re.search(r"SELECTION_CAMERA_COMPONENT_PASS checks=(\d+) SDK_ADAPTERS_MOCKED=true GAMECORE_LOADED=false", transcript)
    if executed.returncode or not match or int(match[1]) < 35:
        raise RuntimeError("Selection camera component failed: " + transcript[-3000:])
    for row in [*records, library, base["compiler"]]:
        if digest(Path(row["path"])) != row["sha256"]:
            raise RuntimeError("Consumed component input changed during execution")
    for row in copied:
        if digest(Path(row["original"]["path"])) != row["original"]["sha256"]:
            raise RuntimeError("Live changed source or runner changed during execution")
    pe = pe_header(executable)
    if pe["architecture"] != "x64":
        raise RuntimeError("Component is not x64")
    report = {"status": "PASS_SELECTION_CAMERA_COMPONENT", "scope": "ACTUAL_HOST_WITH_MOCKED_SDK_ADAPTERS",
              "prepared_host": args.host_id, "shared_baseline": artifact(report_path),
              "changed_inputs": copied, "compiler_inputs": records, "compiler_inputs_unchanged": True,
              "compiler": artifact(compiler), "link_library": library, "compile_response": artifact(response),
              "compile_log": artifact(build_log), "dependencies": artifact(dependencies),
              "executable": {**artifact(executable), "pe": pe}, "intermediate_object": artifact(object_path),
              "execution_log": artifact(execution_log), "checks": int(match[1]), "exit_code": executed.returncode,
              "imports": imports, "imports_log": artifact(imports_log), "gamecore_loaded": False,
              "original_lua_executed": False, "native_clicks_verified": False, "camera_pixels_verified": False,
              "save_compatibility_verified": False, "full_host_rebuilt": False,
              "bRelease_true": "EXPLICIT_UNSUPPORTED_BEFORE_SELECTION_RESOLUTION",
              "coverage": ["ABI virtual dispatch", "unit plot and queue", "city precedence and retained unit",
                           "empty/unbound selection", "missing/stale/delayed-death identities",
                           "null/invalid/throwing plot", "wrong thread and missing owner lock",
                           "unsupported release has no side effects", "adapter destruction",
                           "existing notification deferral preserved"],
              "remaining_gate": "Original CycleRight/CycleLeft HWND input, SDK selection, camera rendering, gameplay preservation and save/restore."}
    destination = evidence / "component.json"
    if destination.exists():
        raise RuntimeError("Component report already exists")
    destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report["checks"],
                      "report": artifact(destination), "gamecore_loaded": False, "full_host_rebuilt": False}))


if __name__ == "__main__":
    main()
