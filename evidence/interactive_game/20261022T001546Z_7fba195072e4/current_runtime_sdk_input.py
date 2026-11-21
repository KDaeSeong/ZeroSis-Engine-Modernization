"""Validate the retained current SDK candidate without loading or executing it.

Importing this module performs no file reads or process calls.  Validation is a
read-only input gate, not evidence of Host integration, save compatibility, or
successful execution.  Only the two explicitly published metadata revisions are
accepted in place of their build-time identities.
"""
from __future__ import annotations

import hashlib
import gzip
import json
import os
from pathlib import Path
import re
import stat
import struct


PROJECT = Path(__file__).absolute().parents[1]
STATUS = "PASS_CURRENT_RUNTIME_SDK_CANDIDATE_COMPILED_LINKED_NOT_LOADED"
POST_SHA = "890cc4278df239dde1ea73760ad74e866aa4bfeebfb7e0e536a05012245b3635"
EXPORTS = {"DllGetGameContext", "ZeroSisShutdownGameCore", "ZeroSisGetBootstrapError"}
SDK_NAMES = {"CvGame", "CvMapGenerator", "CvEspionageClasses", "CvMilitaryAI",
             "CvCultureClasses", "CvTraitClasses", "CvAIOperation", "CvEconomicAI",
             "CvCitySpecializationAI", "CvPlayerAI", "CvSiteEvaluationClasses"}
BRIDGE_SOURCES = {
    "ExploreScoreBridge": "Source/Concurrency/ExploreScoreBridge.cpp",
    "CitySiteScoreBridge": "Source/Concurrency/CitySiteScoreBridge.cpp",
    "CitySiteCpuTrace": "Source/Diagnostics/CitySiteCpuTrace.cpp",
    "FoundValueSharedBridge": "Source/Concurrency/FoundValueSharedBridge.cpp",
}
FALSE_FLAGS = (
    "gamecore_loaded", "host_executed", "windows_created", "retail_accessed",
    "user_state_or_processes_accessed", "full_host_integration", "runtime_updated",
    "default_promoted", "retail_save_accepted", "full_player_restore_verified",
    "ruleset_compatibility_verified", "full_ui_accepted", "multicore_accepted",
    "performance_improvement_verified", "full_engine_goal_complete",
    "binary_pch_consumed", "binary_pch_copied", "whole_project_or_sdk_copied",
    "additional_source_copies_by_builder", "working_sdk_modified",
)


class CurrentRuntimeSdkInputError(RuntimeError):
    """A retained build, its evidence, or one of its inputs is unsuitable."""


def _require(condition, message):
    if not condition:
        raise CurrentRuntimeSdkInputError(message)


def _key(path):
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _identity(row):
    _require(isinstance(row, dict) and isinstance(row.get("path"), str) and
             isinstance(row.get("sha256"), str) and
             re.fullmatch("[0-9a-f]{64}", row["sha256"]), "Malformed artifact identity")
    _require("bytes" not in row or (type(row["bytes"]) is int and row["bytes"] >= 0),
             "Malformed artifact byte count")
    return _key(row["path"]), row["sha256"]


def _same(left, right):
    return _identity(left) == _identity(right) and (
        "bytes" not in left or "bytes" not in right or left["bytes"] == right["bytes"])


def _snapshot(info):
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


class _Artifacts:
    def __init__(self):
        self.checked = {}
        self.revisions = {}

    def effective(self, row):
        identity = _identity(row)
        revision = self.revisions.get(identity[0])
        if revision and _same(row, revision[0]):
            return revision[1]
        return row

    def path(self, value):
        path = Path(value)
        roots = (PROJECT, Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"),
                 Path(r"C:\Program Files (x86)\Windows Kits"),
                 Path(r"C:\Windows\System32"), Path(r"C:\Windows\Microsoft.NET"))
        allowed = any(_key(path) == _key(root) or _key(path).startswith(_key(root) + os.sep)
                      for root in roots)
        _require(path.is_absolute() and ".." not in path.parts and (allowed or
                 _key(path) == _key(r"C:\Windows\Globalization\Sorting\SortDefault.nls")),
                 "Artifact outside retained source, build, or toolchain roots: " + str(path))
        for parent in (path, *path.parents):
            info = parent.lstat()
            _require(not stat.S_ISLNK(info.st_mode) and
                     not getattr(info, "st_file_attributes", 0) & 0x400,
                     "Reparse or symbolic artifact path: " + str(parent))
        return path

    def verify(self, row):
        row = self.effective(row)
        revision = self.revisions.get(_key(row["path"]))
        if revision:
            _require(_same(row, revision[1]), "Unattested publication metadata identity")
            # These are historical documentation identities, not executable
            # inputs. Later publications may legitimately change the live files.
            return dict(revision[1])
        path = self.path(row["path"])
        key = _key(path)
        before = path.stat()
        _require(stat.S_ISREG(before.st_mode), "Artifact is not a regular file: " + str(path))
        cached = self.checked.get(key)
        if cached:
            _require(_same(row, cached[0]) and _snapshot(before) == cached[1],
                     "Artifact identity changed: " + str(path))
            return cached[0]
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        actual = dict(path=str(path), bytes=before.st_size, sha256=digest.hexdigest())
        _require(_snapshot(before) == _snapshot(path.stat()) and _same(row, actual),
                 "Artifact hash or size changed: " + str(path))
        self.checked[key] = actual, _snapshot(before)
        return actual

    def json(self, row):
        actual = self.verify(row)
        _require(actual["bytes"] <= 8 * 1024 * 1024, "JSON evidence exceeds the input bound")
        raw = Path(actual["path"]).read_bytes()
        _require(hashlib.sha256(raw).hexdigest() == actual["sha256"], "JSON changed while reading")
        return json.loads(raw.decode("utf-8-sig"))

    def finish(self):
        for actual, snapshot in self.checked.values():
            path = self.path(actual["path"])
            _require(_snapshot(path.stat()) == snapshot, "Input changed during validation: " + str(path))


def _report_shape(build):
    _require(build.get("schema") == "zerosis.sdk.current_runtime_candidate.v1" and
             build.get("status") == STATUS and build.get("build_mode") ==
             "resume_cached_sdk_cpp14_bridge_cpp17", "Not the retained current runtime SDK build")
    _require(all(build.get(name) is False for name in FALSE_FLAGS),
             "Build claims execution, promotion, or an unsupported scope")
    for name in ("inputs_unchanged", "protected_unchanged", "all_compiler_dependencies_prehashed",
                 "base_export_contract_unchanged", "borrowed_registry_unique",
                 "runtime_overlay_sources_rebased", "shared_lua_import_library_substituted",
                 "hidden_below_normal_children"):
        _require(build.get(name) is True, "Missing build input contract: " + name)
    counts = dict(compiled_sdk_units=11, compiled_bridge_units=4, object_count=165,
                  reused_current_base_objects=150, newly_compiled_units=4,
                  reused_previously_compiled_sdk_units=11, compiler_jobs=1,
                  linker_exit_code=0, this_attempt_child_command_count=6)
    _require(all(type(build.get(name)) is int and build[name] == value for name, value in counts.items()),
             "Current SDK object, compiler, or command counts changed")
    proof = build["resume_proof"]
    _require(proof["previous_child_command_count"] == 13 and
             proof["successful_sdk_cells_revalidated"] == 11 and
             proof["generated_source_and_header_bytes_unchanged"] == 13 and
             proof["historical_failed_status_preserved"] is True and
             len(build["child_commands"]) == 6, "Cached SDK resume evidence changed")
    units = build["compiled_units"]
    _require(len(units) == 15 and len({unit["name"] for unit in units}) == 15 and
             {u["name"] for u in units if u["role"] == "sdk_overlay"} == SDK_NAMES and
             {u["name"] for u in units if u["role"] == "bridge"} == set(BRIDGE_SOURCES),
             "Unexpected compiled source units")
    for unit in units:
        sdk = unit["role"] == "sdk_overlay"
        _require(unit["returncode"] == 0 and not unit["critical_numeric_warning_lines"] and
                 unit["all_dependencies_prehashed"] is True and unit["binary_pch_consumed"] is False and
                 unit["language_standard"] == ("c++14" if sdk else "c++17") and
                 unit["compiler_evidence_reused"] is sdk, "Unverified compiler unit: " + unit["name"])
        flags = build["compiler_flags_by_role"][unit["role"]]
        _require({"/MD", "/fp:strict", "/Y-", "/std:" + unit["language_standard"]} <= set(flags),
                 "Compiler ABI or language flags changed")


def _published_revisions(files, report):
    stage = PROJECT / "evidence/sdk_runtime_current"
    post = files.json(dict(path=str(stage / "post_publication_checks.json"), sha256=POST_SHA))
    _require(post["status"] == "PASS_CURRENT_RUNTIME_SDK_POST_PUBLICATION_CHECKS" and
             _same(post["build"], report) and post["remaining_owned_temporary_files"] == 0 and
             all(post[name] is False for name in ("gamecore_or_host_or_hwnd_executed", "retail_accessed",
                 "runtime_updated", "default_promoted", "retail_save_accepted", "full_ui_accepted",
                 "multicore_accepted", "full_engine_goal_complete")), "Post-publication scope differs")
    publication = files.json(post["publication"])
    _require(publication["status"] == "PUBLISHED_CURRENT_RUNTIME_SDK_CANDIDATE_BUILD_ONLY" and
             _same(publication["stage"]["proofs"]["build"], report), "Publication belongs to another build")
    backups = publication["backups"]
    _require(len(backups) == 2, "Publication metadata backups differ")
    for name, relative in (("index", "evidence/save_menu/20261013_original_screen/current_progress.json"),
                           ("document", "docs/M7_RETAIL_SAVE_BOUNDARY.md")):
        before, after = publication["before"][name], publication["after"][name]
        _require(_key(before["path"]) == _key(after["path"]) == _key(PROJECT / relative) and
                 _same(post[name], after), "Unrelated publication metadata replacement")
        backup = [entry for entry in backups if _same(entry["original"], before)]
        _require(len(backup) == 1 and backup[0]["roundtrip"] is True and
                 _key(backup[0]["compressed"]["path"]) ==
                 _key(stage / ("publication_" + name + ".before.gz")), "Missing exact publication backup")
        compressed = files.verify(backup[0]["compressed"])
        with gzip.open(compressed["path"], "rb") as stream:
            raw = stream.read(8 * 1024 * 1024 + 1)
        _require(len(raw) <= 8 * 1024 * 1024 and len(raw) == before["bytes"] and
                 hashlib.sha256(raw).hexdigest() == before["sha256"], "Publication backup roundtrip differs")
        files.revisions[_key(before["path"])] = before, after
    return post


def _pe(data):
    """Read the PE contract used by the retained base-link parser, without a loader."""
    _require(len(data) >= 64 and data[:2] == b"MZ", "Missing DOS header")
    nt = struct.unpack_from("<I", data, 60)[0]
    _require(nt + 24 <= len(data) and data[nt:nt + 4] == b"PE\0\0", "Missing PE signature")
    machine, count, _, _, _, optional_size, characteristics = struct.unpack_from("<HHIIIHH", data, nt + 4)
    optional = nt + 24
    _require(machine == 0x8664 and characteristics & 0x2000 and characteristics & 0x20 and
             0 < count <= 96 and optional_size >= 240 and
             optional + optional_size + count * 40 <= len(data) and
             struct.unpack_from("<H", data, optional)[0] == 0x20b, "Expected complete AMD64 PE32+ DLL")
    header_bytes = struct.unpack_from("<I", data, optional + 60)[0]
    directories = struct.unpack_from("<I", data, optional + 108)[0]
    _require(14 <= directories <= (optional_size - 112) // 8, "Invalid PE directory count")
    sections = []
    for offset in range(optional + optional_size, optional + optional_size + count * 40, 40):
        size, rva, raw_size, raw = struct.unpack_from("<IIII", data, offset + 8)
        flags = struct.unpack_from("<I", data, offset + 36)[0]
        _require(raw + raw_size <= len(data) and not (flags & 0x20000000 and flags & 0x80000000),
                 "Invalid or writable executable PE section")
        sections.append((rva, size, raw, raw_size, flags))

    def at(rva, size):
        if rva < header_bytes and rva + size <= min(header_bytes, len(data)):
            return rva
        for first, _, raw, raw_size, _ in sections:
            if first <= rva and rva + size <= first + raw_size:
                return raw + rva - first
        raise CurrentRuntimeSdkInputError("Unmapped PE RVA")

    def string(rva):
        output = bytearray()
        for index in range(4096):
            value = data[at(rva + index, 1)]
            if value == 0:
                return output.decode("ascii")
            output.append(value)
        raise CurrentRuntimeSdkInputError("Unterminated PE name")

    export_rva, export_size = struct.unpack_from("<II", data, optional + 112)
    export = at(export_rva, 40)
    functions, names, address_table, name_table, ordinal_table = struct.unpack_from("<IIIII", data, export + 20)
    _require(functions == names == 3, "Expected exactly three named exports")
    exports, ordinals = {}, set()
    for index in range(names):
        name = string(struct.unpack_from("<I", data, at(name_table + 4 * index, 4))[0])
        ordinal = struct.unpack_from("<H", data, at(ordinal_table + 2 * index, 2))[0]
        _require(ordinal < functions and ordinal not in ordinals and name not in exports, "Duplicate PE export")
        ordinals.add(ordinal)
        target = struct.unpack_from("<I", data, at(address_table + 4 * ordinal, 4))[0]
        _require(target and not export_rva <= target < export_rva + export_size and
                 any(first <= target < first + max(size, raw_size) and flags & 0x20000000
                     for first, size, _, raw_size, flags in sections), "Forwarded or nonexecutable export")
        exports[name] = target
    _require(set(exports) == EXPORTS, "Required lifecycle exports differ")
    return exports


def _validate(report_path, expected_sha256):
    stage = PROJECT / "evidence/sdk_runtime_current"
    output = PROJECT / "Build/SDKIncremental/x64/runtime_candidate"
    source = output / "source/CvGameCoreDLL_Expansion2"
    _require(isinstance(expected_sha256, str) and re.fullmatch("[0-9a-f]{64}", expected_sha256),
             "An exact lowercase report SHA-256 is required")
    _require(_key(report_path) == _key(stage / "build_result.json"), "Unexpected candidate report path")
    files = _Artifacts()
    report = files.verify(dict(path=str(report_path), sha256=expected_sha256))
    build = files.json(report)
    _report_shape(build)
    post = _published_revisions(files, report)
    for name in ("plan", "validation"):
        _require(_same(build[name], post[name]), "Build and post-publication proof disagree: " + name)
    _require(_key(build["plan"]["path"]) == _key(stage / "overlay_plan.json") and
             _key(build["validation"]["path"]) == _key(stage / "link_validation.json"), "Unexpected proof paths")
    plan, validation = files.json(build["plan"]), files.json(build["validation"])
    _require(plan["status"] == "CURRENT_RUNTIME_SDK_OVERLAY_PREPARED_NOT_COMPILED" and
             plan["current_recipe_patch_count"] == 714 and plan["generated_file_count"] == 13 and
             plan["planned_link_object_count"] == 165 and plan["base_objects_to_reuse"] == 150 and
             plan["inputs_unchanged"] is True and plan["working_sdk_modified"] is False and
             plan["native_tools_called"] is False and plan["compiled"] is False and plan["linked"] is False,
             "Unsupported source preparation profile")
    expected_files = {str(source / (name + ".cpp")) for name in SDK_NAMES} | {
        str(source / "CvSiteEvaluationClasses.h"), str(source / "CvGameCoreDLLPCH.h")}
    _require(len(plan["generated_files"]) == 13 and
             {_key(row["path"]) for row in plan["generated_files"]} == {_key(p) for p in expected_files},
             "Generated source/header set differs")
    semantic = plan["semantic_proof"]
    _require(semantic["all_historical_generation_replays_match"] is True and
             semantic["old_save_count_patches_reapplied"] is False and
             semantic["routing_pch_header_byte_identical"] is True and
             len(semantic["save_runtime_initializer_ids"]) == 5 and len(semantic["new_game_patch_ids"]) == 18 and
             len(semantic["checked_count_writer_bodies"]) == 4 and
             all(row["identical"] is True and row["before_sha256"] == row["after_sha256"]
                 for row in semantic["checked_count_writer_bodies"]), "Source rebase evidence differs")
    inputs = {_key(row["path"]): files.verify(row) for row in build["inputs"]}
    _require(len(inputs) == len(build["inputs"]), "Duplicate input inventory paths")
    _require(len(build["protected"]) == len(plan["protected"]) == 36, "Protected input inventory changed")
    for row in (*build["protected"], *plan["protected"], *plan["compile_inputs"], *plan["generated_files"]):
        actual = files.verify(row)
        _require(_key(actual["path"]) in inputs and _same(actual, inputs[_key(actual["path"])]),
                 "Unsealed preparation or protected input")
    _require(_key(plan["current_recipe"]["path"]) == _key(PROJECT / "Source/Porting/sdk_x64_patches.json") and
             _key(plan["current_manifest"]["path"]) == _key(PROJECT / "evidence/sdk_x64/port_manifest.json"),
             "Unexpected SDK recipe/manifest")
    recipe = files.json(plan["current_recipe"])
    _require(len(recipe["patches"]) == 714, "SDK recipe patch count changed")
    files.verify(plan["current_manifest"])
    base = files.json(build["base_link"])
    _require(base["status"] == "PASS_CURRENT_BASE_SDK_LINK_NOT_LOADED" and len(base["objects"]) == 161 and
             _same(build["base_link"], plan["base_link"]), "Base object provenance differs")
    base_objects = {Path(row["path"]).stem: files.verify(row) for row in base["objects"]}
    _require(len(base_objects) == 161 and set(plan["base_object_replacements"]) == SDK_NAMES,
             "Base object replacement set differs")
    expected_objects = {_key(row["path"]) for name, row in base_objects.items() if name not in SDK_NAMES}
    plan_units = {row["name"]: row for row in (*plan["sdk_units"], *plan["bridge_units"])}
    _require(len(plan_units) == 15 and set(plan_units) == SDK_NAMES | set(BRIDGE_SOURCES), "Plan unit set differs")
    consumed = set()
    for unit in build["compiled_units"]:
        name = unit["name"]
        expected_source = source / (name + ".cpp") if name in SDK_NAMES else PROJECT / BRIDGE_SOURCES[name]
        _require(_key(unit["source"]["path"]) == _key(expected_source) and
                 _same(unit["source"], plan_units[name]["source"]) and
                 _key(unit["object"]["path"]) == _key(output / "obj" / (name + ".obj")),
                 "Compiled unit source or output escaped its role")
        for field in ("source", "object", "response", "dependencies", "log"):
            files.verify(unit[field])
        if name in SDK_NAMES:
            base_source = plan_units[name]["base_source"]
            _require(_key(base_source["path"]) == _key(PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2" /
                                                      (name + ".cpp")), "Unexpected base SDK source")
            files.verify(base_source)
        expected_objects.add(_key(unit["object"]["path"]))
        dependencies = files.json(unit["dependencies"])
        _require(dependencies["Version"] == "1.2" and
                 _key(dependencies["Data"]["Source"]) == _key(expected_source), "Dependency source differs")
        dependency_paths = {_key(expected_source), *(_key(p) for p in dependencies["Data"]["Includes"])}
        unit_paths = {_key(row["path"]) for row in unit["consumed_inputs"]}
        _require(dependency_paths == unit_paths, "Compiler dependency closure differs")
        for row in unit["consumed_inputs"]:
            _require(_key(row["path"]) in inputs and _same(files.effective(row), inputs[_key(row["path"])]),
                     "Compiler consumed an unsealed dependency")
        consumed.update(unit_paths)
    _require(consumed == {_key(row["path"]) for row in build["consumed_inputs"]}, "Consumed input union differs")
    _require(len(build["objects"]) == len(expected_objects) == 165 and
             {_key(row["path"]) for row in build["objects"]} == expected_objects,
             "Linked objects differ from 150 base plus 15 current units")
    for row in build["objects"]:
        actual = files.verify(row)
        with Path(actual["path"]).open("rb") as stream:
            header = stream.read(8)
        _require(len(header) == 8 and (struct.unpack_from("<H", header)[0] == 0x8664 or
                 (header[:4] == b"\0\0\xff\xff" and struct.unpack_from("<H", header, 6)[0] == 0x8664)),
                 "Linked object is not AMD64 COFF")
    outputs = dict(generated_dll=output / "CvGameCoreDLL_Expansion2_x64_runtime_candidate.dll",
                   link_response=output / "link.rsp", link_log=stage / "link.log",
                   link_map=output / "CvGameCoreDLL_Expansion2_x64_runtime_candidate.map",
                   import_library=output / "RuntimeCandidate.lib", export_object=output / "RuntimeCandidate.exp")
    for name, path in outputs.items():
        _require(_key(build[name]["path"]) == _key(path), "Unexpected candidate output path: " + name)
        files.verify(build[name])
    _require(len(build["providers"]) == 16 and len(build["platform_libraries"]) == 14,
             "Provider or platform library inventory differs")
    for group in (build["providers"], build["platform_libraries"]):
        for row in group:
            files.verify(row["library"])
    for name in ("shared_lua_library", "shared_lua_dll"):
        _require(_same(build[name], plan[name]), "Shared Lua contract differs")
        files.verify(build[name])
    pe = validation["pe"]
    _require(validation["unresolved_symbols"] == 0 and validation["linker_warnings"] == 0 and
             pe == build["pe"] and pe["machine"] == "0x8664" and pe["pe_format"] == "PE32+" and
             pe["is_dll"] is True and pe["dynamic_base"] is True and pe["nx_compatible"] is True and
             set(pe["exports"]) == EXPORTS and "zerosislua51_x64.dll" in pe["imports"],
             "Retained PE or link validation differs")
    gamecore = files.verify(build["generated_dll"])
    data = Path(gamecore["path"]).read_bytes()
    _require(hashlib.sha256(data).hexdigest() == gamecore["sha256"] and _pe(data) == pe["exports"],
             "Actual DLL PE exports differ from retained evidence")
    files.finish()
    return dict(gamecore=gamecore, report=report, validation=files.verify(build["validation"]),
                shared_lua_dll=files.verify(build["shared_lua_dll"]))


def validate_current_runtime_sdk(report_path, expected_sha256):
    """Return pinned GameCore, report, validation, and shared Lua artifacts.

    The caller must supply the reviewed build-result SHA-256.  Every recorded
    build input remains required, except the two explicitly attested publication
    revisions. The historical metadata identities are verified through immutable
    receipts and backups; the live documents may contain later publications.
    No output files, processes, Windows handles, or DLL loads occur.
    """
    try:
        return _validate(report_path, expected_sha256)
    except CurrentRuntimeSdkInputError:
        raise
    except (OSError, ValueError, KeyError, TypeError, AttributeError, struct.error) as error:
        raise CurrentRuntimeSdkInputError("Invalid current SDK input: " + str(error)) from error
