"""Compile one changed SDK unit and link an isolated, never-loaded DLL.

Reuse the retained 165-object runtime graph with exactly one CvUnit replacement.
The old runtime, reports, object cache and prepared game bundles are read-only.
"""
from __future__ import annotations

import sys
sys.dont_write_bytecode = True

from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/serialization/unit_great_work_save"
PARENT = PROJECT / "evidence/sdk_runtime_current/build_result.json"
PARENT_SHA = "dc7dd791816a870a1e6b55778b5f718ebf8f04418edf9e9a7eac5527f82bd303"
MODULES = {
    "probe_public_retail_save": "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "link_current_sdk_base": "9e46d084c07e525a97e138c30c4a58a657e1d1949e0bedb7d6284f8b20454c78",
    "build_current_sdk_runtime_candidate": "43a93dce2d8d108b91dc464230a1f4405e75728b14cd4314d969bc46f3d64144",
    "current_runtime_sdk_input": "42dd2648e7f906595cdc3dffb2ffe80f1a0716fd70da70e908c312e510da3b78",
    "native_build": "c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21",
    "collect_baseline": "7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187",
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def digest(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> int:
    require(len(sys.argv) == 1 and os.name == "nt" and not sys.flags.optimize,
            "Require the reviewed Windows interpreter without extra arguments")
    for name, sha in MODULES.items():
        path = PROJECT / "tools" / (name + ".py")
        for part in (path, *path.parents):
            require(not part.lstat().st_file_attributes & 0x400, "Reparse module path")
        require(path.stat().st_size < 256 * 1024 and digest(path) == sha, "Helper changed before import")
    modules = {name: importlib.import_module(name) for name in MODULES}
    for name, module in modules.items():
        require(Path(module.__file__).absolute() == PROJECT / "tools" / (name + ".py"), "Unexpected helper path")
    g, sealed, runtime, retained, native = [modules[name] for name in
        ("probe_public_retail_save", "link_current_sdk_base", "build_current_sdk_runtime_candidate",
         "current_runtime_sdk_input", "native_build")]
    files = retained._Artifacts()
    parent_pin = files.verify({"path": str(PARENT), "sha256": PARENT_SHA})
    parent = files.json(parent_pin)
    retained._report_shape(parent)
    retained._published_revisions(files, parent_pin)
    change_path = STAGE / "source_change.json"
    change_pin = g.artifact(change_path)
    change = g.read_json(change_path)
    source = PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvUnit.cpp"
    header = PROJECT / "Source/Serialization/UnitGreatWorkSave.h"
    source_pin, header_pin = g.artifact(source), g.artifact(header)
    require(source_pin["sha256"] == "92670270dbf6c031f7c4d2424b73528b691a95a37aebff060a661607a881a5a6" and
            header_pin["sha256"] == "55255f004479bebc77b7f7a1d1c75521cefb60105eb7066323c41897b8a7f9fc",
            "Review a changed production fix before compilation")
    before_sha = "e2fbfa20b3f2c4ecc6e37cf7cce3ea894272098b4bce50da08c8874900a4823b"
    registry, replaced_source_rows = {}, 0
    for row in parent["inputs"]:
        if sealed.key(row["path"]) == sealed.key(source):
            require(row["sha256"] == before_sha, "Parent has a different CvUnit source")
            actual = files.verify(source_pin)
            replaced_source_rows += 1
        else:
            actual = files.verify(row)
        require(sealed.key(actual["path"]) not in registry, "Duplicate inherited input")
        registry[sealed.key(actual["path"])] = actual
    require(replaced_source_rows == 1, "Exactly one inherited source delta is required")
    registry[sealed.key(header)] = files.verify(header_pin)
    # These are historical metadata revisions, not compiler inputs. The current
    # progress/doc/runtime hashes are protected separately by this stage.
    revisions = {key: [old, new] for key, (old, new) in files.revisions.items()}
    base = files.json(parent["base_link"])
    for row in parent["objects"]:
        files.verify(row)
    require(len(parent["objects"]) == 165, "Retained runtime object count changed")
    original_units = [row for row in parent["objects"] if Path(row["path"]).name == "CvUnit.obj"]
    require(len(original_units) == 1 and original_units[0]["sha256"] ==
            "b1f89c56c0330d5040181a4e58df1a0141548d225f99256f9b1313503ed0e06f", "Unexpected original CvUnit object")
    libraries = {}
    for row in parent["providers"] + parent["platform_libraries"] + base["implicit_library_candidates"]:
        pin = files.verify(row["library"])
        libraries[sealed.key(pin["path"])] = pin
    for path in (sealed.COMPILER, sealed.LINKER):
        files.verify({"path": str(path), "sha256": sealed.PINS[path]})
    old_dll = files.verify(parent["generated_dll"])
    old_pe = sealed.inspect_pe(old_dll["path"])
    old_response_pin = files.verify(parent["link_response"])
    old_response = Path(old_response_pin["path"]).read_text(encoding="utf-8")
    old_lines = old_response.splitlines()
    expected_link_inputs = [row["path"] for row in parent["objects"]] + [
        row["library"]["path"] for row in parent["providers"] + parent["platform_libraries"]]
    found = re.findall(r'^"([^"\r\n]+\.(?:obj|lib))"$', old_response, re.M | re.I)
    require([sealed.key(path) for path in found] == [sealed.key(path) for path in expected_link_inputs],
            "Parent response input order differs")
    project_path = PROJECT / "Build/SDKIncremental/x64/sdk_incremental.vcxproj"
    project_pin = g.artifact(project_path)
    namespace = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
    tree = ET.parse(project_path).getroot()
    def setting(name):
        values = [node.text for node in tree.findall(".//m:ItemDefinitionGroup/m:ClCompile/m:" + name, namespace)]
        require(len(values) == 1, "Ambiguous original SDK compiler setting")
        return values[0]
    require(setting("Optimization") == "Disabled" and setting("RuntimeLibrary") == "MultiThreadedDLL" and
            setting("ExceptionHandling") == "Sync" and setting("FloatingPointModel") == "Strict",
            "Original CvUnit compiler ABI settings changed")
    options = unquote(setting("AdditionalOptions")).replace("%(AdditionalOptions)", "")
    includes = [Path(value) for value in re.findall(r'/I"([^"\r\n]+)"', options)]
    flags = re.sub(r'/I"[^"\r\n]+"', "", options).split()
    expected = {"/nologo", "/c", "/std:c++14", "/EHsc", "/MD", "/Od", "/W3", "/bigobj", "/FC",
                "/we4302", "/we4311", "/we4312", *("/D" + name for name in parent["compiler_defines"])}
    require(len(flags) == len(expected) and set(flags) == expected and len(includes) == 10,
            "Base CvUnit compiler recipe differs")
    for directory in includes:
        require(directory.is_dir() and sealed.within(directory, PROJECT / "Source"), "Invalid compiler include root")
        sealed.no_reparse(directory)
    flags += ["/fp:strict", "/Y-"]
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"".decode(encoding)
    own = g.artifact(Path(__file__).absolute())
    identity = g.identity({"schema": "zerosis.unit_great_work_sdk.identity.v1", "parent": parent_pin,
        "source": source_pin, "header": header_pin, "source_change": change_pin, "builder": own,
        "project": project_pin, "flags": flags, "include_directories": [str(path) for path in includes]})
    build_parent = g.ordinary(PROJECT / "Build/UnitGreatWorkSaveSDK")
    build_parent.mkdir(parents=True, exist_ok=True)
    root, evidence = g.ordinary(build_parent / identity), g.ordinary(STAGE / ("sdk_" + identity))
    require(not root.exists() and not evidence.exists(), "Inspect a previous exact SDK attempt before retrying")
    obj, dependencies = root / "CvUnit.obj", root / "CvUnit.dependencies.json"
    compile_response, link_response = root / "CvUnit.rsp", root / "link.rsp"
    dll, library, export, link_map = root / "CvGameCoreDLL_Expansion2_x64.dll", root / "UnitSaveGuard.lib", root / "UnitSaveGuard.exp", root / "CvGameCoreDLL_Expansion2_x64.map"
    setup = root / "read_build_environment.cmd"
    compile_command, link_command = (str(sealed.COMPILER), "@" + str(compile_response)), (str(sealed.LINKER), "@" + str(link_response))
    environment_command = ("cmd.exe", "/d", "/c", str(setup))
    compile_text = "\n".join([*flags, *(f'/I"{path}"' for path in includes), f'/Fo"{obj}"',
                              f'/sourceDependencies "{dependencies}"', f'"{source}"']) + "\n"
    replacements = {"/OUT:": f'/OUT:"{dll}"', "/IMPLIB:": f'/IMPLIB:"{library}"', "/MAP:": f'/MAP:"{link_map}"'}
    changed_flags, unit_replacements, link_lines = set(), 0, []
    for line in old_lines:
        matched = next((prefix for prefix in replacements if line.startswith(prefix)), None)
        if matched:
            require(matched not in changed_flags, "Duplicate parent output flag")
            changed_flags.add(matched)
            link_lines.append(replacements[matched])
        elif line == '"' + original_units[0]["path"] + '"':
            link_lines.append('"' + str(obj) + '"')
            unit_replacements += 1
        else:
            link_lines.append(line)
    require(changed_flags == set(replacements) and unit_replacements == 1, "Link delta is not exactly one object and output paths")
    link_text = "\n".join(link_lines) + "\n"
    outputs = [obj, dependencies, compile_response, link_response, dll, library, export, link_map, setup]
    outputs += [evidence / name for name in ("preflight.json", "compile.log", "link.log", "build_result.json", "failed_attempt.json")]
    readable = [Path(row["path"]) for row, _ in files.checked.values()] + [Path(row["path"]) for row in libraries.values()]
    readable += [change_path, Path(__file__).absolute(), project_path, *(PROJECT / "tools" / (name + ".py") for name in MODULES)]
    guard = g.OfflineGuard(commands=[environment_command, compile_command, link_command], directory=root,
        readable=readable, writable=outputs, directories=[root, evidence])
    files.finish()
    sys.addaudithook(guard.audit)
    try:
        root.mkdir(); evidence.mkdir()
        g.write_json(evidence / "preflight.json", {"schema": "zerosis.unit_great_work_sdk.preflight.v1",
            "parent": parent_pin, "source": source_pin, "header": header_pin, "source_change": change_pin,
            "builder": own, "project": project_pin, "inherited_input_count": len(parent["inputs"]),
            "source_delta_count": 1, "new_header_count": 1, "historical_metadata_revisions": revisions,
            "object_count": 165, "reused_objects": 164, "flags": flags,
            "no_pch_consumed": True, "whole_project_copied": False, "gamecore_loaded": False})
        environment, selected = native.environment_for(sealed.VS, "x64", root)
        require(sealed.key(selected) == sealed.key(sealed.COMPILER), "Environment selected another compiler")
        for name in ("CL", "_CL_", "LINK", "_LINK_"):
            environment.pop(name, None)
        environment["TMP"] = environment["TEMP"] = str(root)
        environment["VSLANG"] = "1033"
        g.write_text(compile_response, compile_text, 64 * 1024)
        compiled = subprocess.run(compile_command, cwd=root, env=environment, capture_output=True, timeout=180,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        compile_log = (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace")
        g.write_text(evidence / "compile.log", compile_log, 1024 * 1024)
        critical = [line for line in compile_log.splitlines() if runtime.CRITICAL.search(line)]
        require(compiled.returncode == 0 and not critical, "SDK unit compile failed or emitted a critical numeric diagnostic")
        dep = g.read_json(dependencies).get("Data")
        require(isinstance(dep, dict) and sealed.key(dep["Source"]) == sealed.key(source) and
                isinstance(dep["Includes"], list), "Malformed actual SDK dependency report")
        consumed = []
        for path in [str(source), *dep["Includes"]]:
            key = sealed.key(path)
            require(key in registry, "Compiler consumed an input absent from the prehashed registry: " + path)
            current = g.artifact(path)
            require(current["sha256"] == registry[key]["sha256"] and current["bytes"] == registry[key]["bytes"],
                    "Compiler input changed from prehash")
            consumed.append(current)
        require(sealed.key(header) in {sealed.key(row["path"]) for row in consumed}, "Production helper was not compiled")
        object_proof = sealed.inspect_coff(obj)
        require(object_proof, "Missing actual AMD64 object proof")
        files.finish()
        g.write_text(link_response, link_text, 128 * 1024)
        linked = subprocess.run(link_command, cwd=root, env=environment, capture_output=True, timeout=240,
            creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        link_log = (linked.stdout + linked.stderr).decode("mbcs", errors="replace")
        g.write_text(evidence / "link.log", link_log, 4 * 1024 * 1024)
        require(linked.returncode == 0 and not re.search(r"\b(?:fatal\s+)?error\s+LNK\d+|\bwarning\s+LNK\d+", link_log, re.I),
                "SDK delta link failed or emitted a linker diagnostic")
        events = sealed.verbose_library_searches(link_log)
        require(events and all(sealed.key(event["path"]) in libraries for event in events), "Linker searched an unpinned library")
        pe = sealed.inspect_pe(dll)
        require(pe["dynamic_base"] and pe["nx_compatible"] and set(pe["imports"]) == set(old_pe["imports"]),
                "Linked DLL changed the retained import-module contract")
        require("zerosislua51_x64.dll" in pe["imports"], "Shared Lua contract is missing")
        current_objects = [g.artifact(obj) if sealed.key(row["path"]) == sealed.key(original_units[0]["path"]) else row
                           for row in parent["objects"]]
        map_text = link_map.read_text(encoding="mbcs", errors="strict")
        map_proof = runtime.map_contract(sealed, map_text, pe, [Path(row["path"]).name for row in current_objects])
        require("dummynode_" not in map_text, "Private Lua implementation entered the DLL")
        files.finish()
        g.unchanged([own, source_pin, header_pin, change_pin, project_pin])
        require(not guard.denied and len(guard.calls) == 3, "Unexpected build operations")
        retired = g.retire(setup, root, guard)
        warnings = {}
        for code in re.findall(r"\bwarning\s+(C\d+)\b", compile_log, re.I):
            warnings[code.upper()] = warnings.get(code.upper(), 0) + 1
        artifacts = {path.name: g.artifact(path) for path in
            (obj, dependencies, compile_response, link_response, dll, library, export, link_map,
             evidence / "compile.log", evidence / "link.log")}
        result = {"schema": "zerosis.unit_great_work_sdk.delta.v1", "status": "PASS_ONE_UNIT_SDK_COMPILE_AND_STATIC_LINK",
            "utc": datetime.now(timezone.utc).isoformat(), "fingerprint": identity, "parent": parent_pin,
            "source": source_pin, "header": header_pin, "source_change": change_pin, "builder": own,
            "base_compile_project": project_pin, "compile_flags": flags, "no_pch_consumed": True,
            "inherited_input_count": len(parent["inputs"]), "inherited_source_deltas": 1,
            "all_compiler_dependencies_prehashed": True, "consumed_inputs": consumed,
            "object_count": 165, "reused_parent_objects": 164, "replaced_parent_object": original_units[0],
            "current_objects": current_objects, "artifacts": artifacts, "pe": pe, "map_contract": map_proof,
            "warning_codes": warnings, "critical_numeric_warning_lines": critical,
            "compile_returncode": compiled.returncode, "link_returncode": linked.returncode,
            "retired_environment_script": retired, "child_commands": guard.calls,
            "forbidden_access_attempts": guard.denied, "old_runtime_and_inputs_unchanged": True,
            "old_prepared_bundles_updated": False, "dll_or_sdk_reference_loaded": False,
            "real_database_or_saving_executed": False, "retail_save_accepted": False,
            "game_processes_or_user_files_accessed": False, "full_engine_goal_complete": False}
        target = evidence / "build_result.json"
        g.write_json(target, result)
        print(json.dumps({"report": g.artifact(target), "status": result["status"], "fingerprint": identity,
            "dll": artifacts[dll.name], "dependency_count": len(consumed), "warning_codes": warnings,
            "reused_objects": 164, "compiled_objects": 1, "retired_logical_bytes": retired["bytes"]}))
        return 0
    except BaseException as error:
        if evidence.is_dir() and not (evidence / "failed_attempt.json").exists():
            g.write_json(evidence / "failed_attempt.json", {"status": "FAILED_UNIT_GREAT_WORK_SDK_DELTA",
                "error": type(error).__name__ + ": " + str(error), "child_commands": guard.calls,
                "forbidden_access_attempts": guard.denied, "dll_loaded": False, "full_engine_goal_complete": False})
        raise


if __name__ == "__main__":
    raise SystemExit(main())
