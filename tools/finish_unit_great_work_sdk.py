"""Validate retained one-unit SDK outputs without starting any child process.

The failed original attempt and all of its source, logs and binary outputs stay
unchanged. Only its 144-byte environment script may be retired, after all static
checks, and result.json is created exactly once in the original evidence stage.
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
import stat
from urllib.parse import unquote
import xml.etree.ElementTree as ET


PROJECT = Path(__file__).absolute().parents[1]
IDENTITY = "2bdcdf80a1695780f864"
ROOT = PROJECT / "Build/UnitGreatWorkSaveSDK" / IDENTITY
STAGE = PROJECT / "evidence/serialization/unit_great_work_save" / ("sdk_" + IDENTITY)
RESULT = STAGE / "result.json"
PARENT = PROJECT / "evidence/sdk_runtime_current/build_result.json"
PARENT_SHA = "dc7dd791816a870a1e6b55778b5f718ebf8f04418edf9e9a7eac5527f82bd303"
SOURCE = PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvUnit.cpp"
HEADER = PROJECT / "Source/Serialization/UnitGreatWorkSave.h"
SOURCE_SHA = "92670270dbf6c031f7c4d2424b73528b691a95a37aebff060a661607a881a5a6"
HEADER_SHA = "55255f004479bebc77b7f7a1d1c75521cefb60105eb7066323c41897b8a7f9fc"
SOURCE_BEFORE_SHA = "e2fbfa20b3f2c4ecc6e37cf7cce3ea894272098b4bce50da08c8874900a4823b"
OLD_OBJECT_SHA = "b1f89c56c0330d5040181a4e58df1a0141548d225f99256f9b1313503ed0e06f"
MODULES = {
    "probe_public_retail_save": "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962",
    "link_current_sdk_base": "9e46d084c07e525a97e138c30c4a58a657e1d1949e0bedb7d6284f8b20454c78",
    "build_current_sdk_runtime_candidate": "43a93dce2d8d108b91dc464230a1f4405e75728b14cd4314d969bc46f3d64144",
    "current_runtime_sdk_input": "42dd2648e7f906595cdc3dffb2ffe80f1a0716fd70da70e908c312e510da3b78",
    "native_build": "c3ac0e9c1438c83662a2dbe5032e6711713266d5dfb67086b3e7ae9e71e14c21",
    "collect_baseline": "7b94e1e90b5a9e4a1df74194da6eb8c2ea2e12f041bdb58aaa8a3aef2a2bb187",
}
ORIGINAL_BUILDER = PROJECT / "tools/build_unit_great_work_sdk.py"
BUILDER_SHA = "1d70131070e730db232effec203788dd48b8e0515ed96a439ed620cb1f26faf5"
# First-observed pins from the retained attempt. No outputs are regenerated.
BUILD_PINS = {
    "CvUnit.obj": (1996927, "fabc59b183de0298eef4dd6c92d5e39cd291a14d26e72d3ab5540c797078a880"),
    "CvUnit.dependencies.json": (57866, "1208634a01660b2a1d2970d565c3f76bf1a2a69a65f498874ed57beb493f6bd5"),
    "CvUnit.rsp": (1932, "c936e72de2b5bb3150a529144dbd9ea8f51bc59ebfa527d389591048e4d9ff54"),
    "link.rsp": (25753, "0a1b83ce70be7c784652aa5a71e987561883f766fb8ecc654e4c3a46c145133b"),
    "CvGameCoreDLL_Expansion2_x64.dll": (6945792, "430f3122d0b555d6daae14aa7c011ef43ce8f978270477c8af596ca4b0493ab9"),
    "UnitSaveGuard.lib": (2622, "fd913629973918f5fd8102b446abc62ee54be89e8fc534a693171b8d3e6f784f"),
    "UnitSaveGuard.exp": (1444, "ea907a7bfcce3d6e4b3a4e5a91ab30092282c7af9e8e6ee889d7d31350c32959"),
    "CvGameCoreDLL_Expansion2_x64.map": (19639425, "a350865ef92ce08c3c2b8abbd5649febe4cdfc2d3957da919073af2c48e88c6a"),
    "read_build_environment.cmd": (144, "070f0010b005a4ee792b70e7f052a470296f296ffd48556310229b4a2829e30e"),
}
EVIDENCE_PINS = {
    "preflight.json": (4429, "aac9610d80992b0e56946317d474f496cabdee8d6dd07106acea305de78fea85"),
    "failed_attempt.json": (1123, "0de690fed8961bf424cd2619e51f7129cfcbeca2e80e0d4cd6cb6931942d499c"),
    "compile.log": (31158, "f5864943c80dac62d882a17c69f2920867a25a192fd7dbd41bd8aef8df93e6d8"),
    "link.log": (32742, "5825d1d1a339517c6b80876bedd81d1c08f1ed59ec2a7b06988ea8542d69a64b"),
}
LIVE_METADATA = {
    "index": PROJECT / "evidence/save_menu/20261013_original_screen/current_progress.json",
    "document": PROJECT / "docs/M7_RETAIL_SAVE_BOUNDARY.md",
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def no_execution(event, _args):
    # This hook also covers bootstrap imports, before the exact file guard exists.
    if event == "subprocess.Popen" or event.startswith(("ctypes.dlopen", "socket.", "urllib.", "http.client.")) or \
            event in ("os.system", "os.startfile", "os.startfile/2"):
        raise RuntimeError("Static validation forbids child processes, network and dynamic loading")


def module_inputs():
    result = []
    for name, expected in MODULES.items():
        path = PROJECT / "tools" / (name + ".py")
        for part in (path, *path.parents):
            info = part.lstat()
            require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                    "Reparse helper path")
        before = path.stat()
        require(stat.S_ISREG(before.st_mode) and before.st_size < 256 * 1024, "Invalid helper file")
        with path.open("rb") as stream:
            sha = hashlib.file_digest(stream, "sha256").hexdigest()
        after = path.stat()
        require(sha == expected and (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns), "Helper changed before import")
        result.append(path)
    return result


def pin(g, path, size, sha):
    row = g.artifact(path)
    require(row["bytes"] == size and row["sha256"] == sha, "Retained artifact differs: " + str(path))
    return row


def compiler_recipe(sealed, parent, project_path):
    namespace = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
    tree = ET.fromstring(project_path.read_bytes())

    def setting(name):
        values = [node.text for node in tree.findall(".//m:ItemDefinitionGroup/m:ClCompile/m:" + name, namespace)]
        require(len(values) == 1, "Ambiguous original compiler setting")
        return values[0]

    require(setting("Optimization") == "Disabled" and setting("RuntimeLibrary") == "MultiThreadedDLL" and
            setting("ExceptionHandling") == "Sync" and setting("FloatingPointModel") == "Strict",
            "Original compiler ABI settings differ")
    options = unquote(setting("AdditionalOptions")).replace("%(AdditionalOptions)", "")
    includes = [Path(value) for value in re.findall(r'/I"([^"\r\n]+)"', options)]
    flags = re.sub(r'/I"[^"\r\n]+"', "", options).split()
    expected = {"/nologo", "/c", "/std:c++14", "/EHsc", "/MD", "/Od", "/W3", "/bigobj", "/FC",
                "/we4302", "/we4311", "/we4312", *("/D" + name for name in parent["compiler_defines"])}
    require(len(flags) == len(expected) and set(flags) == expected and len(includes) == 10,
            "Original CvUnit compiler recipe differs")
    for directory in includes:
        require(directory.is_dir() and sealed.within(directory, PROJECT / "Source"), "Invalid original include root")
        sealed.no_reparse(directory)
    return flags + ["/fp:strict", "/Y-"], includes


def main() -> int:
    require(len(sys.argv) == 1 and os.name == "nt" and not sys.flags.optimize,
            "Require the reviewed Windows interpreter without extra arguments")
    sys.addaudithook(no_execution)
    module_paths = module_inputs()
    names = ("probe_public_retail_save", "link_current_sdk_base",
             "build_current_sdk_runtime_candidate", "current_runtime_sdk_input")
    modules = [importlib.import_module(name) for name in names]
    for name, module in zip(names, modules):
        require(Path(module.__file__).absolute() == PROJECT / "tools" / (name + ".py"), "Unexpected helper module")
    g, sealed, runtime, retained = modules
    helper_pins = [g.artifact(path) for path in module_paths]
    require(all(row["sha256"] == MODULES[Path(row["path"]).stem] for row in helper_pins), "Helper changed during import")
    own = g.artifact(Path(__file__).absolute())
    g.ordinary(ROOT); g.ordinary(STAGE); g.ordinary(RESULT)
    require(ROOT.is_dir() and STAGE.is_dir() and not RESULT.exists(), "Require the retained, unfinished exact attempt")
    original_builder = pin(g, ORIGINAL_BUILDER, 17765, BUILDER_SHA)
    build = {name: pin(g, ROOT / name, *expected) for name, expected in BUILD_PINS.items()}
    evidence = {name: pin(g, STAGE / name, *expected) for name, expected in EVIDENCE_PINS.items()}
    preflight, failed = g.read_json(STAGE / "preflight.json"), g.read_json(STAGE / "failed_attempt.json")
    source_pin = pin(g, SOURCE, 573706, SOURCE_SHA)
    header_pin = pin(g, HEADER, 1378, HEADER_SHA)
    project_path = PROJECT / "Build/SDKIncremental/x64/sdk_incremental.vcxproj"
    project_pin = g.artifact(project_path)
    change_path = STAGE.parent / "source_change.json"
    change_pin = pin(g, change_path, 3826, "3473eaa97dc88331e6a8bb821948827c1fc9e58216e718965090b6a9fe2d13d0")
    require(preflight["schema"] == "zerosis.unit_great_work_sdk.preflight.v1" and
            preflight["builder"] == original_builder and preflight["source"] == source_pin and
            preflight["header"] == header_pin and preflight["project"] == project_pin and
            preflight["source_change"] == change_pin and preflight["source_delta_count"] == 1 and
            preflight["new_header_count"] == 1 and preflight["object_count"] == 165 and
            preflight["reused_objects"] == 164 and preflight["no_pch_consumed"] is True and
            preflight["whole_project_copied"] is False and preflight["gamecore_loaded"] is False,
            "Original preflight does not describe this retained attempt")
    change = g.read_json(change_path)
    require(change["source_before"]["sha256"] == SOURCE_BEFORE_SHA and
            change["source_after"]["sha256"] == SOURCE_SHA and
            change["new_helper_after"]["sha256"] == HEADER_SHA, "Source delta receipt differs")
    live_before = {name: g.artifact(path) for name, path in LIVE_METADATA.items()}

    files = retained._Artifacts()
    parent_pin = files.verify({"path": str(PARENT), "sha256": PARENT_SHA})
    parent = files.json(parent_pin)
    retained._report_shape(parent)
    retained._published_revisions(files, parent_pin)
    require(preflight["parent"] == parent_pin and preflight["inherited_input_count"] == len(parent["inputs"]),
            "Original parent graph differs")
    revisions = {key: [old, new] for key, (old, new) in files.revisions.items()}
    require(preflight["historical_metadata_revisions"] == revisions and len(revisions) == 2,
            "Historical publication exemptions differ")
    registry, source_deltas = {}, 0
    for row in parent["inputs"]:
        if sealed.key(row["path"]) == sealed.key(SOURCE):
            require(row["sha256"] == SOURCE_BEFORE_SHA and row["bytes"] == 572855,
                    "Unexpected parent CvUnit source")
            actual = files.verify(source_pin)
            source_deltas += 1
        else:
            actual = files.verify(row)
        key = sealed.key(actual["path"])
        require(key not in registry, "Duplicate inherited input")
        registry[key] = actual
    require(source_deltas == 1 and sealed.key(HEADER) not in registry, "Source delta is not exactly one plus a new helper")
    registry[sealed.key(HEADER)] = files.verify(header_pin)
    base = files.json(parent["base_link"])
    objects = parent["objects"]
    require(len(objects) == 165 and len({sealed.key(row["path"]) for row in objects}) == 165,
            "Retained graph is not 165 distinct direct objects")
    for row in objects:
        files.verify(row)
    old_units = [row for row in objects if Path(row["path"]).name == "CvUnit.obj"]
    require(len(old_units) == 1 and old_units[0]["sha256"] == OLD_OBJECT_SHA and
            old_units[0]["bytes"] == 1979871, "Unexpected replaced base object")
    libraries = {}
    for row in parent["providers"] + parent["platform_libraries"] + base["implicit_library_candidates"]:
        library = files.verify(row["library"])
        libraries[sealed.key(library["path"])] = library
    for path in (sealed.COMPILER, sealed.LINKER):
        files.verify({"path": str(path), "sha256": sealed.PINS[path]})
    old_dll = files.verify(parent["generated_dll"])
    old_response = files.verify(parent["link_response"])
    old_text = Path(old_response["path"]).read_bytes().decode("utf-8")
    expected_inputs = [row["path"] for row in objects] + [
        row["library"]["path"] for row in parent["providers"] + parent["platform_libraries"]]
    found = re.findall(r'^"([^"\r\n]+\.(?:obj|lib))"$', old_text, re.M | re.I)
    require([sealed.key(path) for path in found] == [sealed.key(path) for path in expected_inputs],
            "Original response graph/order differs")
    flags, includes = compiler_recipe(sealed, parent, project_path)
    require(preflight["flags"] == flags, "Original compile flags differ")
    fingerprint = g.identity({"schema": "zerosis.unit_great_work_sdk.identity.v1", "parent": parent_pin,
        "source": source_pin, "header": header_pin, "source_change": change_pin, "builder": original_builder,
        "project": project_pin, "flags": flags, "include_directories": [str(path) for path in includes]})
    require(fingerprint == IDENTITY, "Original attempt fingerprint differs")
    obj, dependencies = ROOT / "CvUnit.obj", ROOT / "CvUnit.dependencies.json"
    setup = ROOT / "read_build_environment.cmd"
    expected_commands = [["cmd.exe", "/d", "/c", str(setup)],
                         [str(sealed.COMPILER), "@" + str(ROOT / "CvUnit.rsp")],
                         [str(sealed.LINKER), "@" + str(ROOT / "link.rsp")]]
    require(failed["status"] == "FAILED_UNIT_GREAT_WORK_SDK_DELTA" and
            failed["child_commands"] == expected_commands and
            failed["error"] == "RuntimeError: Probe file access escaped the exact allowlist" and
            failed["forbidden_access_attempts"] == ["Probe file access escaped the exact allowlist"] and
            failed["dll_loaded"] is False and failed["full_engine_goal_complete"] is False,
            "Original failure or its three child commands differ")
    compile_text = "\n".join([*flags, *(f'/I"{path}"' for path in includes), f'/Fo"{obj}"',
                              f'/sourceDependencies "{dependencies}"', f'"{SOURCE}"']) + "\n"
    require((ROOT / "CvUnit.rsp").read_bytes() == compile_text.encode("utf-8"), "Retained compile response differs")
    replacements = {"/OUT:": f'/OUT:"{ROOT / "CvGameCoreDLL_Expansion2_x64.dll"}"',
                    "/IMPLIB:": f'/IMPLIB:"{ROOT / "UnitSaveGuard.lib"}"',
                    "/MAP:": f'/MAP:"{ROOT / "CvGameCoreDLL_Expansion2_x64.map"}"'}
    changed_flags, unit_replacements, lines = set(), 0, []
    for line in old_text.splitlines():
        match = next((prefix for prefix in replacements if line.startswith(prefix)), None)
        if match:
            require(match not in changed_flags, "Duplicate original output flag")
            changed_flags.add(match); lines.append(replacements[match])
        elif line == '"' + old_units[0]["path"] + '"':
            lines.append('"' + str(obj) + '"'); unit_replacements += 1
        else:
            lines.append(line)
    require(changed_flags == set(replacements) and unit_replacements == 1 and
            (ROOT / "link.rsp").read_bytes() == ("\n".join(lines) + "\n").encode("utf-8"),
            "Retained link delta is not exactly one object and three output flags")

    # Decode bytes directly; TextIO's separate codec lookup caused the old denial.
    for encoding in ("mbcs", "utf-8", "utf-8-sig"):
        b"warm".decode(encoding)
    first_pins = [original_builder, *build.values(), *evidence.values(), source_pin, header_pin, change_pin, project_pin, *helper_pins]
    readable = [Path(row["path"]) for row, _ in files.checked.values()]
    readable += [Path(row["path"]) for row in first_pins + [own, *live_before.values()]] + module_paths
    guard = g.OfflineGuard(commands=[], directory=ROOT, readable=readable, writable=[RESULT], directories=[ROOT, STAGE])
    files.finish()
    sys.addaudithook(guard.audit)
    data = g.read_json(dependencies).get("Data")
    require(isinstance(data, dict) and sealed.key(data["Source"]) == sealed.key(SOURCE) and
            isinstance(data["Includes"], list) and all(isinstance(path, str) for path in data["Includes"]),
            "Malformed actual dependency graph")
    require(not data.get("ImportedModules") and not data.get("ImportedHeaderUnits"), "Unexpected compiler module input")
    consumed = []
    for path in [str(SOURCE), *data["Includes"]]:
        key = sealed.key(path)
        require(key in registry and Path(path).suffix.lower() != ".pch", "Unpinned input or binary PCH in actual dependencies")
        actual = g.artifact(path)
        require(actual["sha256"] == registry[key]["sha256"] and actual["bytes"] == registry[key]["bytes"],
                "Actual dependency differs from the inherited registry")
        consumed.append({name: actual[name] for name in ("path", "bytes", "sha256")})
    require(sealed.key(HEADER) in {sealed.key(row["path"]) for row in consumed}, "The new production helper was not compiled")
    compile_log = (STAGE / "compile.log").read_bytes().decode("utf-8", errors="strict")
    link_log = (STAGE / "link.log").read_bytes().decode("utf-8", errors="strict")
    critical = [line for line in compile_log.splitlines() if runtime.CRITICAL.search(line)]
    require(not critical and not re.search(r"\b(?:fatal\s+)?error\s+C\d+", compile_log, re.I),
            "Retained compile log contains an error or critical width diagnostic")
    warning_codes = {}
    for code in re.findall(r"\bwarning\s+(C\d+)\b", compile_log, re.I):
        warning_codes[code.upper()] = warning_codes.get(code.upper(), 0) + 1
    require(not re.search(r"\b(?:fatal\s+)?error\s+LNK\d+|\bwarning\s+LNK\d+", link_log, re.I),
            "Retained link log contains a linker diagnostic")
    searches = sealed.verbose_library_searches(link_log)
    require(searches and all(sealed.key(row["path"]) in libraries for row in searches), "Linker searched an unpinned library")
    object_proof = sealed.inspect_coff(obj)
    require(object_proof["machine"] == "0x8664" and object_proof["coff_members"] == 1, "New object is not standalone AMD64 COFF")
    old_pe = sealed.inspect_pe(old_dll["path"])
    pe = sealed.inspect_pe(ROOT / "CvGameCoreDLL_Expansion2_x64.dll")
    require(old_pe == parent["pe"] and pe["dynamic_base"] and pe["nx_compatible"] and
            set(pe["imports"]) == set(old_pe["imports"]) and "zerosislua51_x64.dll" in pe["imports"] and
            set(pe["exports"]) == set(old_pe["exports"]) == sealed.EXPORTS, "Retained DLL import/export contract differs")
    current_objects = [build["CvUnit.obj"] if sealed.key(row["path"]) == sealed.key(old_units[0]["path"]) else row
                       for row in objects]
    require(sum(row in objects for row in current_objects) == 164 and len(current_objects) == 165,
            "Static graph does not reuse exactly 164 parent objects")
    map_text = (ROOT / "CvGameCoreDLL_Expansion2_x64.map").read_bytes().decode("mbcs", errors="strict")
    map_text = map_text.replace("\r\n", "\n").replace("\r", "\n")
    map_proof = runtime.map_contract(sealed, map_text, pe, [Path(row["path"]).name for row in current_objects])
    require("dummynode_" not in map_text, "Private Lua implementation entered the retained DLL")
    # Rehash the exact inherited closure; no directory scan or source copying.
    files.finish()
    post = retained._Artifacts()
    for actual, _snapshot in files.checked.values():
        post.verify(actual)
    files.finish(); post.finish()
    g.unchanged(first_pins + [own, *live_before.values()])
    live_after = {name: g.artifact(path) for name, path in LIVE_METADATA.items()}
    require(live_after == live_before and not guard.denied and not guard.calls, "Static validation changed inputs or attempted an operation")
    retired = build["read_build_environment.cmd"]
    result = {"schema": "zerosis.unit_great_work_sdk.retained_static.v1",
        "status": "PASS_RETAINED_UNIT_SAVE_SDK_STATIC_OUTPUTS", "utc": datetime.now(timezone.utc).isoformat(),
        "fingerprint": IDENTITY, "validator": own, "original_builder": original_builder, "helpers": helper_pins,
        "original_preflight": evidence["preflight.json"], "original_failure": evidence["failed_attempt.json"],
        "original_failure_status": failed["status"], "original_failure_error": failed["error"],
        "historical_child_commands": failed["child_commands"], "historical_forbidden_access_attempts": failed["forbidden_access_attempts"],
        "compile_process_exit_code": None, "link_process_exit_code": None, "process_exit_code_evidence": "not_retained",
        "new_child_commands": guard.calls, "forbidden_access_attempts": guard.denied,
        "parent": parent_pin, "source": source_pin, "header": header_pin, "source_change": change_pin,
        "base_compile_project": project_pin, "compile_flags": flags, "include_directories": [str(path) for path in includes],
        "historical_metadata_revisions": revisions, "live_metadata_before": live_before, "live_metadata_after": live_after,
        "inherited_input_count": len(parent["inputs"]), "inherited_source_deltas": 1, "new_header_count": 1,
        "non_metadata_input_rehash_count": len(post.checked), "all_compiler_dependencies_prehashed": True,
        "all_inherited_non_metadata_inputs_rehashed": True, "consumed_inputs": consumed, "no_pch_consumed": True,
        "object_count": 165, "reused_parent_objects": 164, "replaced_parent_object": old_units[0],
        "current_objects": current_objects, "new_object_coff": object_proof,
        "artifacts": {name: row for name, row in build.items() if name != "read_build_environment.cmd"},
        "logs": {name: evidence[name] for name in ("compile.log", "link.log")}, "pe": pe, "map_contract": map_proof,
        "warning_codes": warning_codes, "critical_numeric_warning_lines": critical,
        "retired_environment_script": retired, "retired_logical_bytes": 144, "static_output_validation_only": True,
        "old_runtime_and_non_metadata_inputs_unchanged_except_declared_source_delta": True,
        "live_progress_and_document_unchanged": True, "original_failed_attempt_preserved": True,
        "new_compile_or_link_executed": False, "sdk_or_dll_or_host_executed": False,
        "dll_or_sdk_reference_loaded": False, "old_prepared_bundles_updated": False, "runtime_updated": False,
        "real_database_or_saving_executed": False, "retail_save_accepted": False,
        "game_processes_or_user_saves_accessed": False, "restore_approved": False, "full_engine_goal_complete": False}
    require(len((json.dumps(result, ensure_ascii=True, indent=2) + "\n").encode("utf-8")) <= g.MAX_JSON,
            "Static result exceeds the fixed evidence budget before cleanup")
    require(g.retire(setup, ROOT, guard) == retired and retired["bytes"] == 144,
            "Retired script differs from its original first pin")
    g.write_json(RESULT, result)
    print(json.dumps({"status": result["status"], "report": g.artifact(RESULT),
        "new_child_commands": 0, "reused_parent_objects": 164, "actual_dependency_count": len(consumed),
        "compile_process_exit_code": None, "link_process_exit_code": None, "process_exit_code_evidence": "not_retained",
        "retired_logical_bytes": 144}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
