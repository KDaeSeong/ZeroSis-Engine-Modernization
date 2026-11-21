"""Build one sealed current SDK runtime candidate; never load or promote it."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
PROJECT = Path(__file__).absolute().parents[1]
STAGE = PROJECT / "evidence/sdk_runtime_current"
OUT = PROJECT / "Build/SDKIncremental/x64/runtime_candidate"
SOURCES = OUT / "source/CvGameCoreDLL_Expansion2"
PLAN = STAGE / "overlay_plan.json"
BASE = PROJECT / "evidence/sdk_current/base_link_result.json"
PUBLICATION = PROJECT / "evidence/sdk_current/progress_update.json"
PREFLIGHT = PROJECT / "evidence/sdk_incremental/runtime_candidate_preflight.json"
HELPER = PROJECT / "tools/link_current_sdk_base.py"
BASE_SHA = "5f36ecab69c7b19da42f66d8327c5ddba68b539966ff2c8d5115521a102ef255"
HELPER_SHA = "9e46d084c07e525a97e138c30c4a58a657e1d1949e0bedb7d6284f8b20454c78"
PUBLICATION_SHA = "cbcc9666d1c867faa02c46807f73a45298ecf315bac36a2a9cc8c9a4739bf88a"
PREFLIGHT_SHA = "b6245ded36cef8cdf04b5e9784cc429afa9a4e3629beb6040eb896d5099fb352"
OLD_RUNTIME = PROJECT / "Build/FoundValueSharedSDK/20261002T154635Z_480d61cc2900/CvGameCoreDLL_Expansion2_x64.dll"
OLD_RUNTIME_SHA = "a58a0d20cbaecad13ea248fe362d0c15bb97096802b9f60c5ef5f0dd8bb90c07"
RESUME_FAILURE_SHA = "c1b7bbb7b7479be6afbf303f7ccdfc2bb53c1c87773927f9bdc9e464cc8c5df6"
FAILED_PLAN_SHA = "78047039e67014aa4556b2d9d3d55bb7b60c81d0589fa6b3792c78c873588223"
PREVIOUS_BUILDER_SHA = "b3114a85f5bc353ec2525df546adc8b4b51867e764044f11cbf35d432da168fd"
PREVIOUS_STARTED_SHA = "03443d343615842264f370ee9290e5b37a17f840a08775a4410eb9e00c77d7e1"
BUILDER_BACKUP = STAGE / "builder_before_cpp17_resume.py.gz"
BUILDER_BACKUP_SHA = "041478be3f980a9b39ece296471c988ceafde58c634ad3a84b4f91b4f3362385"
SDK_NAMES = {
    "CvAIOperation", "CvCultureClasses", "CvEspionageClasses", "CvMilitaryAI",
    "CvTraitClasses", "CvGame", "CvMapGenerator", "CvEconomicAI",
    "CvCitySpecializationAI", "CvPlayerAI", "CvSiteEvaluationClasses",
}
BRIDGE_NAMES = {"ExploreScoreBridge", "CitySiteScoreBridge", "CitySiteCpuTrace", "FoundValueSharedBridge"}
DEFINES = (
    "FXS_IS_DLL", "WIN32", "NDEBUG", "_WINDOWS", "_USRDLL",
    "CVGAMECOREDLL_EXPORTS", "FINAL_RELEASE", "_CRT_SECURE_NO_WARNINGS",
    "_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS",
)
FLAGS = (
    "/nologo", "/c", "/std:c++14", "/MD", "/Od", "/bigobj", "/EHsc",
    "/fp:strict", "/W3", "/FC", "/Y-", "/we4302", "/we4311", "/we4312",
)
BRIDGE_FLAGS = tuple("/std:c++17" if x == "/std:c++14" else x for x in FLAGS)
CRITICAL = re.compile(r"\b(?:warning|경고)\s+C(?:4244|4267|4302|4311|4312|4838)\b", re.I)


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def helpers():
    require(sha(HELPER) == HELPER_SHA, "Reviewed base-link helper changed")
    spec = importlib.util.spec_from_file_location("sealed_current_base_link", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def encoded(value):
    return (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")


def write_new(path, payload):
    path = Path(path)
    require(not path.exists(), "Inspect existing output before retrying: " + str(path))
    with path.open("xb") as stream:
        stream.write(payload)


def response_bytes(row, output, include_dirs):
    require(row["role"] in ("sdk_overlay", "bridge"), "Unknown compilation role")
    flags = FLAGS if row["role"] == "sdk_overlay" else BRIDGE_FLAGS
    command = [*flags, *("/D" + x for x in DEFINES),
               *(f'/I"{p}"' for p in include_dirs),
               f'/Fo"{output["object"]}"', f'/sourceDependencies "{output["dependencies"]}"',
               f'"{Path(row["source"]["path"])}"']
    return ("\n".join(command) + "\n").encode("utf-8")


def lua_exports(path):
    """Inspect the retained Lua DLL as bytes, without using a loader."""
    data = Path(path).read_bytes()
    require(len(data) >= 64 and data[:2] == b"MZ", "Invalid shared Lua DOS header")
    nt = struct.unpack_from("<I", data, 60)[0]
    require(nt + 24 <= len(data) and data[nt:nt + 4] == b"PE\0\0", "Invalid shared Lua PE")
    machine, sections, _, _, _, optional_bytes, flags = struct.unpack_from("<HHIIIHH", data, nt + 4)
    optional = nt + 24
    require(machine == 0x8664 and flags & 0x2000 and optional_bytes >= 240 and
            optional + optional_bytes + 40 * sections <= len(data) and
            struct.unpack_from("<H", data, optional)[0] == 0x20b and 0 < sections <= 96,
            "Shared Lua must be a complete AMD64 DLL")
    tables = []
    for offset in range(optional + optional_bytes, optional + optional_bytes + 40 * sections, 40):
        size, rva, raw_size, raw = struct.unpack_from("<IIII", data, offset + 8)
        require(raw + raw_size <= len(data), "Truncated shared Lua section")
        tables.append((rva, size, raw, raw_size))

    def at(rva, size):
        for first, _, raw, raw_size in tables:
            if first <= rva and rva + size <= first + raw_size:
                return raw + rva - first
        raise RuntimeError("Shared Lua export RVA is not file-backed")

    def text(rva):
        output = bytearray()
        for i in range(4096):
            value = data[at(rva + i, 1)]
            if not value:
                return output.decode("ascii")
            output.append(value)
        raise RuntimeError("Unterminated shared Lua export")

    export_rva = struct.unpack_from("<I", data, optional + 112)[0]
    export = at(export_rva, 40)
    functions, names, _, table, _ = struct.unpack_from("<IIIII", data, export + 20)
    require(functions == names == 124, "Retained shared Lua export count changed")
    result = [text(struct.unpack_from("<I", data, at(table + i * 4, 4))[0]) for i in range(names)]
    require(len(set(result)) == names and {
        "ZeroSisLuaInvoke", "lua_newstate", "lua_newthread", "lua_close", "lua_gc",
        "lua_cpcall", "lua_pcall", "luaL_newstate", "luaL_openlibs",
    } <= set(result), "Required shared Lua/callback exports are missing")
    return result


def publication_inputs(sealed, base, publication):
    """Replace exactly two old publication identities with their attested after rows."""
    require(publication["status"] == "PUBLISHED_CURRENT_BASE_SDK_COMPILE_LINK_NOT_LOADED",
            "Current base publication is not final")
    replacements = {}
    for name, relative in (
        ("index", "evidence/save_menu/20261013_original_screen/current_progress.json"),
        ("document", "docs/M7_RETAIL_SAVE_BOUNDARY.md"),
    ):
        before, after = publication["before"][name], publication["after"][name]
        expected = sealed.key(PROJECT / relative)
        require(sealed.key(before["path"]) == sealed.key(after["path"]) == expected,
                "Publication replacement escaped its exact metadata path")
        replacements[expected] = (before, after)
    superseded = []
    require(len(base["inputs"]) == 1655, "Reviewed base input set changed")
    for row in base["inputs"]:
        pair = replacements.get(sealed.key(row["path"]))
        if pair:
            before, after = pair
            require(row["bytes"] == before["bytes"] and row["sha256"] == before["sha256"],
                    "Old metadata input does not match the publication before identity")
            sealed.pin(after)
            superseded.append({"before": row, "after": after})
        else:
            sealed.pin(row)
    require(len(superseded) == 2, "Expected exactly two attested superseded base inputs")
    return superseded


def initial_output_tree(sealed, generated, cached=()):
    """Permit preparation files and only the explicitly authenticated SDK cache."""
    expected = {sealed.key(row["path"]) for row in generated if sealed.within(row["path"], OUT)}
    require(len(expected) == 13 and OUT.is_dir(), "Exactly thirteen prepared files must already exist")
    for row in cached:
        expected.update(sealed.key(row[name]["path"]) for name in ("object", "response", "dependencies"))
    allowed_dirs = {sealed.key(OUT)}
    for name in expected:
        parent = Path(name).parent
        while sealed.within(parent, OUT):
            allowed_dirs.add(sealed.key(parent))
            if sealed.key(parent) == sealed.key(OUT):
                break
            parent = parent.parent
    if cached:
        allowed_dirs.update(sealed.key(OUT / name) for name in ("obj", "rsp", "deps", "tmp"))
    files = set()
    for path in OUT.rglob("*"):
        sealed.no_reparse(path)
        if path.is_file():
            files.add(sealed.key(path))
        else:
            require(path.is_dir() and sealed.key(path) in allowed_dirs, "Unexpected preparation/cache directory")
    require(files == expected, "Candidate root contains unreviewed or previous build output")


def resume_sdk_cache(sealed, requested_sha, sdk_units, generated, paths, include_dirs):
    """Reuse the eleven successful C++14 cells from one exact preserved failure."""
    require(requested_sha == RESUME_FAILURE_SHA, "Only the reviewed first failure can be resumed")
    failed_path, started_path = STAGE / "failed_attempt.json", STAGE / "build_started.json"
    failure = sealed.read_json(failed_path, RESUME_FAILURE_SHA)
    started = sealed.read_json(started_path, PREVIOUS_STARTED_SHA)
    backup = sealed.pin({"path": str(BUILDER_BACKUP), "sha256": BUILDER_BACKUP_SHA})
    require(hashlib.sha256(gzip.decompress(BUILDER_BACKUP.read_bytes())).hexdigest() == PREVIOUS_BUILDER_SHA,
            "Original builder source-only backup failed roundtrip")
    require(failure["status"] == "FAILED_CURRENT_RUNTIME_SDK_CANDIDATE_PRESERVED" and
            failure["error"] == "RuntimeError: Compile failed or emitted a width diagnostic: ExploreScoreBridge" and
            failure["plan_sha256"] == FAILED_PLAN_SHA and sealed.key(failure["output_root"]) == sealed.key(OUT),
            "Preserved failure is not the reviewed bridge-language failure")
    require(started["status"] == "CURRENT_RUNTIME_SDK_BUILD_STARTED_NOT_LOADED" and
            started["plan_sha256"] == FAILED_PLAN_SHA and started["builder"]["sha256"] == PREVIOUS_BUILDER_SHA and
            sealed.key(started["output_root"]) == sealed.key(OUT), "Original compile startup identity differs")
    require(all(failure[name] is False for name in ("gamecore_loaded", "runtime_updated", "default_promoted")) and
            started["gamecore_loaded"] is False and started["runtime_updated"] is False,
            "Previous attempt exceeded the build-only scope")
    cached = failure["compiled_units"]
    require(len(cached) == 11 and {r["name"] for r in cached} == SDK_NAMES, "Exactly eleven SDK cache cells required")
    previous_commands = [(str(sealed.CMD), "/d", "/c", str(OUT / "read_build_environment.cmd"))]
    previous_commands += [(str(sealed.COMPILER), "@" + str(paths[r["name"]]["response"])) for r in cached]
    previous_commands += [(str(sealed.COMPILER), "@" + str(paths["ExploreScoreBridge"]["response"]))]
    actual = failure["child_commands"]
    require(len(actual) == 13 and len(actual) == len(previous_commands), "Previous child-command count differs")
    for before, expected in zip(actual, previous_commands):
        require(len(before) == len(expected) and sealed.key(before[0]) == sealed.key(expected[0]) and
                tuple(before[1:]) == tuple(expected[1:]), "Previous command order or exact arguments differ")
    current_sources = {r["name"]: r for r in sdk_units}
    observed_generated = {}
    validated = []
    for row in cached:
        name = row["name"]
        require(row["role"] == "sdk_overlay" and row["returncode"] == 0 and
                row["binary_pch_consumed"] is False and row["all_dependencies_prehashed"] is True and
                row["critical_numeric_warning_lines"] == [], "SDK cache is not an attested successful C++14 compile")
        new_source = current_sources[name]["source"]
        require(sealed.key(row["source"]["path"]) == sealed.key(new_source["path"]) and
                row["source"]["sha256"] == new_source["sha256"] and row["source"]["bytes"] == new_source["bytes"],
                "Prepared source bytes changed since the cached SDK compilation")
        for field in ("object", "response", "dependencies", "log"):
            require(sealed.key(row[field]["path"]) == sealed.key(paths[name][field]),
                    "SDK cache artifact escaped its exact cell")
            sealed.pin(row[field])
        require(Path(row["response"]["path"]).read_bytes() == response_bytes(current_sources[name], paths[name], include_dirs),
                "Cached SDK response differs from the unchanged C++14 recipe")
        data = json.loads(Path(row["dependencies"]["path"]).read_text(encoding="utf-8-sig"))["Data"]
        require(sealed.key(data["Source"]) == sealed.key(row["source"]["path"]), "Cached dependency source differs")
        dependency_keys = [sealed.key(data["Source"])] + [sealed.key(x) for x in data["Includes"]]
        require(dependency_keys == [sealed.key(x["path"]) for x in row["consumed_inputs"]],
                "Cached complete compiler dependency list differs")
        for consumed in row["consumed_inputs"]:
            k = sealed.key(consumed["path"])
            require(k in sealed.INPUTS, "Cached consumed input is absent from the current prehashed plan")
            current = sealed.INPUTS[k]
            require(current["bytes"] == consumed["bytes"] and current["sha256"] == consumed["sha256"],
                    "Cached consumed input changed in the current plan")
            sealed.pin(consumed)
            if Path(consumed["path"]).parent == SOURCES:
                observed_generated[k] = consumed
        require(sealed.inspect_coff(row["object"]["path"]) == row["object_coff"], "Cached SDK COFF evidence differs")
        log = Path(row["log"]["path"]).read_text(encoding="utf-8")
        require(not CRITICAL.search(log) and not re.search(r"\b(?:error|오류)\s+C\d+", log, re.I),
                "Cached successful SDK log contains an error/width diagnostic")
        copied = dict(row, language_standard="c++14", compiler_evidence_reused=True)
        validated.append(copied)
    require(len(observed_generated) == 13 and set(observed_generated) ==
            {sealed.key(x["path"]) for x in generated}, "Cached SDK dependencies must bind all thirteen generated source/header bytes")
    for row in generated:
        old = observed_generated[sealed.key(row["path"])]
        require(old["sha256"] == row["sha256"] and old["bytes"] == row["bytes"],
                "Generated source/header bytes changed across the plan metadata repair")
    return validated, {"failure": sealed.artifact(failed_path), "started": sealed.artifact(started_path),
        "previous_builder_backup": backup, "previous_builder_sha256": PREVIOUS_BUILDER_SHA,
        "previous_plan_sha256": FAILED_PLAN_SHA, "previous_child_command_count": 13,
        "previous_child_commands": actual, "successful_sdk_cells_revalidated": 11,
        "generated_source_and_header_bytes_unchanged": 13, "sdk_response_language_standard": "c++14",
        "historical_failed_status_preserved": True}


def install_guard(sealed, writable, directories, commands, calls):
    def audit(event, args):
        if event == "subprocess.Popen":
            command = next((row for row in commands if subprocess.list2cmdline(row) == args[1]), None) \
                if isinstance(args[1], str) else tuple(map(str, args[1]))
            require(command in commands and (args[0] is None or sealed.key(args[0]) == sealed.key(command[0])),
                    "Unapproved runtime-candidate child command")
            calls.append(command)
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            writing = isinstance(args[1], str) and any(c in args[1] for c in "wax+") or \
                isinstance(args[2], int) and args[2] & (
                    os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
            if writing:
                require(sealed.key(os.fsdecode(args[0])) in writable, "Write escaped exact owned output list")
        if event in ("os.remove", "os.rmdir", "os.mkdir", "os.rename", "os.chmod", "os.link", "os.symlink"):
            for target in args[:2] if event in ("os.rename", "os.link", "os.symlink") else args[:1]:
                if isinstance(target, (str, bytes, os.PathLike)):
                    require(event == "os.mkdir" and sealed.key(os.fsdecode(target)) in directories,
                            "Unapproved runtime-candidate filesystem mutation")
        if event.startswith(("ctypes.dlopen", "socket.", "urllib.", "http.client.", "winreg.")) or \
                event in ("os.system", "os.startfile", "os.startfile/2"):
            raise RuntimeError("Network, dynamic loading, registry and interactive launches are forbidden")
    sys.addaudithook(audit)


def run_low(command, commands, cwd, env, timeout):
    command = tuple(map(str, command))
    require(command in commands, "Command was not sealed before launch")
    return subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=timeout,
                          creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)


def environment(sealed, setup, commands):
    vcvars = sealed.VS / "VC/Auxiliary/Build/vcvars64.bat"
    sealed.capture(vcvars)
    sealed.capture(vcvars.with_name("vcvarsall.bat"))
    sealed.capture(sealed.CMD)
    content = '@echo off\ncall "' + str(vcvars) + '" >nul\nif errorlevel 1 exit /b 1\nset\n'
    write_new(setup, content.encode("utf-8"))
    env = {k.upper(): v for k, v in os.environ.items()}
    for name in ("CL", "_CL_", "LINK", "_LINK_"):
        env.pop(name, None)
    result = run_low((sealed.CMD, "/d", "/c", setup), commands, OUT, env, 60)
    require(result.returncode == 0, "Compiler environment setup failed")
    # Never persist or print this environment: inherited values may be secrets.
    for line in result.stdout.decode("mbcs", errors="replace").splitlines():
        if "=" in line and not line.startswith("="):
            name, value = line.split("=", 1)
            env[name.upper()] = value
    for name in ("CL", "_CL_", "LINK", "_LINK_"):
        env.pop(name, None)
    require(sealed.key(shutil.which("cl.exe", path=env.get("PATH")) or "") == sealed.key(sealed.COMPILER),
            "Environment selected another compiler")
    env["VSLANG"] = "1033"
    env["TMP"] = env["TEMP"] = str(OUT / "tmp")
    return env


def map_contract(sealed, text, pe, expected_names):
    exports = {}
    for name, rva in pe["exports"].items():
        matches = re.findall(
            r"(?m)^\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}\s+" + re.escape(name) +
            r"\s+([0-9A-Fa-f]{16})\s+(?:[fi]\s+){0,2}([^\r\n]+)$", text)
        require(len(matches) == 1 and int(matches[0][0], 16) == pe["image_base"] + rva,
                "Export address disagrees with the link map: " + name)
        exports[name] = {"rva": rva, "map_address": matches[0][0]}
    registry = re.findall(
        r"(?m)^\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}\s+"
        r"(\?state@\?1\?\?State@ZeroSisLuaBorrowed@@\S+)\s+"
        r"([0-9A-Fa-f]{16})\s+(?:[fi]\s+){0,2}([^\r\n]+)$", text)
    require(len(registry) == 1, "Borrowed Lua registry must have exactly one map symbol/address")
    required = {
        "ZeroSisFoundValueEvaluateSharedBatch": "FoundValueSharedBridge.obj",
        "ZeroSisFoundValueSharedLastBatchId": "FoundValueSharedBridge.obj",
        "ZeroSisEvaluateExploreScores": "ExploreScoreBridge.obj",
        "ZeroSisEvaluateCitySites": "CitySiteScoreBridge.obj",
    }
    bridges = {}
    for name, owner in required.items():
        matches = re.findall(
            r"(?m)^\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}\s+" + re.escape(name) +
            r"\s+([0-9A-Fa-f]{16})\s+(?:[fi]\s+){0,2}" + re.escape(owner) + r"\s*$", text)
        require(len(matches) == 1, "Missing exact bridge symbol/owner: " + name)
        bridges[name] = {"address": matches[0], "object": owner}
    plain = re.findall(
        r"(?m)^\s*[0-9A-Fa-f]{4}:[0-9A-Fa-f]{8}\s+\S+\s+[0-9A-Fa-f]{16}"
        r"\s+(?:[fi]\s+){0,2}([^:\s]+\.obj)\s*$", text)
    require(plain and set(x.casefold() for x in plain) <= {x.casefold() for x in expected_names},
            "Link map contains an unsealed direct object origin")
    require({name + ".obj" for name in BRIDGE_NAMES} <= set(plain),
            "One of the four bridge objects is absent from the final map")
    return {"exports": exports, "borrowed_registry": {
        "symbol": registry[0][0], "address": registry[0][1], "owner": registry[0][2]},
        "bridge_symbols": bridges, "direct_object_origins": sorted(set(plain), key=str.casefold)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--resume-failed-sha256")
    args = parser.parse_args()
    require(not sys.flags.optimize and re.fullmatch("[0-9a-f]{64}", args.plan_sha256),
            "An exact reviewed preparation-plan SHA-256 is required")
    require(args.resume_failed_sha256 is None or args.resume_failed_sha256 == RESUME_FAILURE_SHA,
            "Resume requires the exact reviewed first-failure SHA-256")
    sealed = helpers()
    sealed.capture(HELPER)
    sealed.capture(Path(__file__).absolute())
    plan = sealed.read_json(PLAN, args.plan_sha256)
    require(plan["status"] == "CURRENT_RUNTIME_SDK_OVERLAY_PREPARED_NOT_COMPILED",
            "Preparation is not final or already claims execution")
    base = sealed.read_json(BASE, BASE_SHA)
    publication = sealed.read_json(PUBLICATION, PUBLICATION_SHA)
    preflight = sealed.read_json(PREFLIGHT, PREFLIGHT_SHA)
    require(base["status"] == "PASS_CURRENT_BASE_SDK_LINK_NOT_LOADED" and base["object_count"] == 161 and
            base["provider_count"] == 16 and base["platform_library_count"] == 14,
            "Current base SDK is not the reviewed complete link")
    superseded = publication_inputs(sealed, base, publication)
    require(len(preflight["protected"]) == 36, "Runtime preflight protection set changed")
    for row in preflight["protected"]:
        sealed.pin(row)
    for name in ("base_link", "current_recipe", "current_manifest", "shared_lua_library", "shared_lua_dll"):
        sealed.pin(plan[name])
    require(sealed.key(plan["base_link"]["path"]) == sealed.key(BASE) and plan["base_link"]["sha256"] == BASE_SHA,
            "Plan is not based on the current base SDK")
    for name in ("generated_dll", "link_response", "link_log", "link_map", "import_library", "export_object",
                 "validation", "compile_report", "compile_state", "compiler", "linker", "definition"):
        sealed.pin(base[name])
    require(base["compiler"]["sha256"] == sealed.PINS[sealed.COMPILER] and
            base["linker"]["sha256"] == sealed.PINS[sealed.LINKER], "Compiler/linker pin changed")
    require(set(Path(base["definition"]["path"]).read_text(encoding="ascii").split()) ==
            {"EXPORTS", *sealed.EXPORTS}, "GameCore public export definition changed")
    require(sealed.inspect_pe(base["generated_dll"]["path"]) == base["pe"], "Current base PE changed")
    old_runtime = sealed.pin({"path": str(OLD_RUNTIME), "sha256": OLD_RUNTIME_SHA})
    old_pe = sealed.inspect_pe(OLD_RUNTIME)
    shared_library = sealed.pin(plan["shared_lua_library"])
    shared_dll = sealed.pin(plan["shared_lua_dll"])
    require(Path(shared_library["path"]).name == "ZeroSisLua51_x64.lib" and
            Path(shared_dll["path"]).name == "ZeroSisLua51_x64.dll", "Wrong shared Lua module names")
    shared_exports = lua_exports(shared_dll["path"])
    sdk_units, bridges = plan["sdk_units"], plan["bridge_units"]
    require(len(sdk_units) == 11 and {r["name"] for r in sdk_units} == SDK_NAMES and
            len(bridges) == 4 and {r["name"] for r in bridges} == BRIDGE_NAMES,
            "Expected exactly eleven SDK and four bridge units")
    require(set(plan["base_object_replacements"]) == SDK_NAMES, "Base replacement set differs")
    require(len(plan["generated_files"]) == 13, "Prepared source/header count differs")
    for row in plan["generated_files"]:
        sealed.pin(row)
        require(Path(row["path"]).parent == SOURCES, "Prepared file escaped the exact source directory")
    generated_keys = {sealed.key(row["path"]) for row in plan["generated_files"]}
    for row in sdk_units:
        require(row["role"] == "sdk_overlay" and Path(row["source"]["path"]) == SOURCES / (row["name"] + ".cpp") and
                sealed.key(row["source"]["path"]) in generated_keys, "Invalid prepared SDK unit")
        require(Path(row["base_source"]["path"]) ==
                PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2" / (row["name"] + ".cpp"),
                "SDK unit baseline is not the working copied source")
        sealed.pin(row["source"])
        sealed.pin(row["base_source"])
    for row in bridges:
        require(row["role"] == "bridge" and Path(row["source"]["path"]).name == row["name"] + ".cpp" and
                sealed.within(row["source"]["path"], PROJECT / "Source") and
                row["historical_hash_match"] is True and
                row["source"]["sha256"] == row["historical_source"]["sha256"], "Bridge historical source differs")
        sealed.pin(row["source"])
        sealed.pin(row["historical_source"])
    for row in plan["compile_inputs"]:
        sealed.pin(row)
    include_dirs = [Path(x) for x in plan["include_dirs"]]
    require(1 <= len(include_dirs) <= 32 and len({sealed.key(p) for p in include_dirs}) == len(include_dirs) and
            include_dirs[0] == SOURCES, "Invalid include ordering")
    for path in include_dirs:
        sealed.input_path(path)
        require(path.is_dir(), "Include directory does not exist")
    project = PROJECT / "Build/SDKIncremental/x64/sdk_incremental.vcxproj"
    sealed.capture(project)
    xml = ET.fromstring(project.read_bytes())
    options = "\n".join(x.text or "" for x in xml.iter() if x.tag.endswith("AdditionalOptions"))
    require({x for x in re.findall(r"/D([A-Za-z0-9_]+)", options)} == set(DEFINES),
            "Current SDK compile definitions differ from the fixed runtime recipe")
    base_objects = base["objects"]
    require(len(base_objects) == 161 and len({Path(x["path"]).stem.casefold() for x in base_objects}) == 161,
            "Base object inventory is ambiguous")
    object_by_name = {Path(x["path"]).stem: x for x in base_objects}
    require(SDK_NAMES <= set(object_by_name), "Base SDK replacement object is missing")
    for row in base_objects:
        require(Path(row["path"]).parent == PROJECT / "Build/SDKIncremental/x64/obj",
                "Base inventory contains an old overlay object")
        sealed.pin(row)
        sealed.inspect_coff(row["path"])
    base_response = Path(base["link_response"]["path"]).read_text(encoding="utf-8")
    response_inputs = re.findall(r'^"([^"\r\n]+\.(?:obj|lib))"$', base_response, re.M | re.I)
    require([sealed.key(x) for x in response_inputs] == [
        sealed.key(r["path"]) for r in base_objects] + [
        sealed.key(r["library"]["path"]) for r in base["providers"] + base["platform_libraries"]],
        "Reviewed base response input order differs")
    providers = []
    require(tuple(x["name"] for x in base["providers"]) == sealed.PROVIDER_NAMES, "Base providers differ")
    for row in base["providers"]:
        library = shared_library if row["name"] == "Lua51" else sealed.pin(row["library"])
        providers.append({"name": row["name"], "library": library,
                          "coff": sealed.inspect_coff(library["path"])})
    require(sum(sealed.key(r["library"]["path"]) == sealed.key(shared_library["path"]) for r in providers) == 1,
            "Shared Lua import library was not substituted exactly once")
    platform = base["platform_libraries"]
    require(tuple(r["name"] for r in platform) == sealed.PLATFORM, "Platform-library set differs")
    for row in platform + base["implicit_library_candidates"]:
        sealed.pin(row["library"])
        sealed.inspect_coff(row["library"]["path"])
    units = sdk_units + bridges
    paths = {}
    for row in units:
        name = row["name"]
        paths[name] = {"object": OUT / "obj" / (name + ".obj"), "response": OUT / "rsp" / (name + ".rsp"),
                       "dependencies": OUT / "deps" / (name + ".json"), "log": STAGE / ("compile_" + name + ".log")}
    cached_units, resume_proof = [], None
    if args.resume_failed_sha256:
        cached_units, resume_proof = resume_sdk_cache(sealed, args.resume_failed_sha256,
            sdk_units, plan["generated_files"], paths, include_dirs)
    initial_output_tree(sealed, plan["generated_files"], cached_units)
    active_units = bridges if resume_proof else units
    dll = OUT / "CvGameCoreDLL_Expansion2_x64_runtime_candidate.dll"
    link_paths = {"dll": dll, "map": dll.with_suffix(".map"), "library": OUT / "RuntimeCandidate.lib",
                  "exp": OUT / "RuntimeCandidate.exp", "response": OUT / "link.rsp",
                  "log": STAGE / "link.log", "validation": STAGE / "link_validation.json",
                  "result": STAGE / "build_result.json", "started": STAGE / "build_started.json",
                  "failed": STAGE / "failed_attempt.json", "setup": OUT / "read_build_environment.cmd"}
    if resume_proof:
        link_paths.update(started=STAGE / "resume_started.json", failed=STAGE / "resume_failed_attempt.json",
                          setup=OUT / "read_resume_build_environment.cmd")
    writable_paths = [p for row in active_units for p in paths[row["name"]].values()] + list(link_paths.values())
    for path in writable_paths:
        sealed.no_reparse(path)
        require(not path.exists(), "Inspect previous runtime-candidate output before retrying: " + str(path))
    directories = [OUT / x for x in ("obj", "rsp", "deps", "tmp")]
    if resume_proof:
        require(all(p.is_dir() for p in directories), "Resume requires the exact existing four output directories")
    else:
        require(all(not p.exists() for p in directories), "Inspect previous candidate output directories")
    commands = {(str(sealed.CMD), "/d", "/c", str(link_paths["setup"]))}
    commands.update((str(sealed.COMPILER), "@" + str(paths[row["name"]]["response"])) for row in active_units)
    commands.add((str(sealed.LINKER), "@" + str(link_paths["response"])))
    calls, compiled = [], list(cached_units)
    install_guard(sealed, {sealed.key(p) for p in writable_paths},
                  {sealed.key(p) for p in directories}, commands, calls)
    for path in directories:
        if not path.exists():
            path.mkdir()
    frozen_before = list(sealed.INPUTS.values())
    try:
        write_new(link_paths["started"], encoded({
            "status": "CURRENT_RUNTIME_SDK_BUILD_STARTED_NOT_LOADED", "plan_sha256": args.plan_sha256,
            "builder": sealed.artifact(__file__), "input_count": len(frozen_before), "output_root": str(OUT),
            "resume_proof": resume_proof, "new_compile_units": len(active_units),
            "previously_compiled_sdk_units_reused": len(cached_units),
            "gamecore_loaded": False, "runtime_updated": False}))
        env = environment(sealed, link_paths["setup"], commands)
        prehashed = set(sealed.INPUTS)
        dependencies_seen = {sealed.key(item["path"]): sealed.INPUTS[sealed.key(item["path"])]
                             for row in cached_units for item in row["consumed_inputs"]}
        for row in active_units:
            name, source = row["name"], Path(row["source"]["path"])
            output = paths[name]
            write_new(output["response"], response_bytes(row, output, include_dirs))
            response_before = sealed.artifact(output["response"])
            sealed.verify_inputs()
            result = run_low((sealed.COMPILER, "@" + str(output["response"])), commands, OUT, env, 240)
            text = (result.stdout + result.stderr).decode("mbcs", errors="replace")
            write_new(output["log"], text.encode("utf-8"))
            critical = [x for x in text.splitlines() if CRITICAL.search(x)]
            require(result.returncode == 0 and not critical, "Compile failed or emitted a width diagnostic: " + name)
            require(sealed.artifact(output["response"]) == response_before, "Compile response changed")
            require(output["dependencies"].is_file(), "Compiler dependency output is missing")
            data = json.loads(output["dependencies"].read_text(encoding="utf-8-sig"))["Data"]
            require(sealed.key(data["Source"]) == sealed.key(source), "Compiler dependency source differs")
            dependencies = [source] + [Path(x) for x in data["Includes"]]
            for path in dependencies:
                require(sealed.key(path) in prehashed, "Compiler consumed an input absent from the prehashed closure: " + str(path))
                actual = sealed.artifact(path)
                expected = sealed.INPUTS[sealed.key(path)]
                require(actual["sha256"] == expected["sha256"] and actual["bytes"] == expected["bytes"],
                        "Compiler dependency changed: " + str(path))
                dependencies_seen[sealed.key(path)] = expected
            require(not any(path.suffix.lower() == ".pch" for path in dependencies), "Binary PCH was consumed")
            if row["role"] == "sdk_overlay":
                required_headers = {sealed.key(SOURCES / "CvGameCoreDLLPCH.h")}
                if name == "CvSiteEvaluationClasses":
                    required_headers.add(sealed.key(SOURCES / "CvSiteEvaluationClasses.h"))
                require(required_headers <= {sealed.key(x) for x in dependencies},
                        "Prepared text PCH/site header was not consumed")
            detail = sealed.inspect_output_coff(output["object"])
            compiled.append({"name": name, "role": row["role"], "source": row["source"],
                "object": sealed.artifact(output["object"]), "object_coff": detail,
                "response": response_before, "dependencies": sealed.artifact(output["dependencies"]),
                "consumed_inputs": [sealed.INPUTS[sealed.key(x)] for x in dependencies],
                "log": sealed.artifact(output["log"]), "returncode": result.returncode,
                "critical_numeric_warning_lines": critical,
                "other_warning_lines": [x for x in text.splitlines() if re.search(r"\b(?:warning|경고)\s+C\d+", x, re.I)],
                "binary_pch_consumed": False, "all_dependencies_prehashed": True,
                "language_standard": "c++14" if row["role"] == "sdk_overlay" else "c++17",
                "compiler_evidence_reused": False})
            sealed.verify_inputs()
        new_objects = {row["name"]: row["object"] for row in compiled}
        current_objects = [new_objects.get(Path(row["path"]).stem, row) for row in base_objects]
        current_objects += [new_objects[name] for name in sorted(BRIDGE_NAMES)]
        require(len(current_objects) == 165 and len({sealed.key(r["path"]) for r in current_objects}) == 165,
                "Runtime candidate must link exactly 165 unique current objects")
        reused = [row for row in current_objects if Path(row["path"]).parent == PROJECT / "Build/SDKIncremental/x64/obj"]
        require(len(reused) == 150 and sum(Path(r["path"]).parent == OUT / "obj" for r in current_objects) == 15,
                "Expected 150 reused base and 15 newly compiled objects")
        lib_dirs = [Path(x.strip().strip('"')) for x in env.get("LIB", "").split(";") if x.strip()]
        require(lib_dirs and all(p.is_absolute() for p in lib_dirs), "Invalid compiler LIB search path")
        explicit = {Path(r["library"]["path"]).name.casefold(): Path(r["library"]["path"]) for r in providers + platform}
        allowed_libraries = {sealed.key(r["library"]["path"]) for r in providers + platform + base["implicit_library_candidates"]}

        def resolve(name):
            require(re.fullmatch(r"[A-Za-z0-9_.-]+", name), "Unexpected DEFAULTLIB name")
            canonical = name if name.lower().endswith(".lib") else name + ".lib"
            path = explicit.get(canonical.casefold()) or next((p / canonical for p in lib_dirs if (p / canonical).is_file()), None)
            require(path is not None and sealed.key(path) in allowed_libraries, "DEFAULTLIB is not in the sealed base/provider graph: " + canonical)
            return path

        pending = [x for row in current_objects for x in sealed.COFF[sealed.key(row["path"])]["default_libraries"]]
        pending += [x for row in providers + platform for x in sealed.COFF[sealed.key(row["library"]["path"])]["default_libraries"]]
        resolutions = {}
        while pending:
            name = pending.pop()
            canonical = (name if name.lower().endswith(".lib") else name + ".lib").casefold()
            if canonical in resolutions:
                continue
            path = resolve(name)
            resolutions[canonical] = str(path)
            pending.extend(sealed.COFF[sealed.key(path)]["default_libraries"])
            require(len(resolutions) <= 128, "Unbounded default-library graph")
        flags = ["/NOLOGO", "/DLL", "/MACHINE:X64", "/INCREMENTAL:NO", "/OPT:REF", "/OPT:ICF",
                 "/Brepro", "/DYNAMICBASE", "/NXCOMPAT", "/VERBOSE:LIB", f'/DEF:"{base["definition"]["path"]}"',
                 f'/OUT:"{dll}"', f'/IMPLIB:"{link_paths["library"]}"', f'/MAP:"{link_paths["map"]}"']
        flags += ['"' + x["path"] + '"' for x in current_objects]
        flags += ['"' + x["library"]["path"] + '"' for x in providers + platform]
        link_text = "\n".join(flags) + "\n"
        require(all(not re.search(r"(?:SaveRestoreSDK|NewGameSDK|ExploreSDK|CitySiteSDK|FoundValueSharedSDK|attempt_037)[\\/]", r["path"], re.I)
                    for r in current_objects), "Historical overlay object leaked into the current link")
        write_new(link_paths["response"], link_text.encode("utf-8"))
        link_response = sealed.artifact(link_paths["response"])
        for row in compiled:
            require(sealed.artifact(row["object"]["path"]) == row["object"], "New object changed before link")
        sealed.verify_inputs()
        linked = run_low((sealed.LINKER, "@" + str(link_paths["response"])), commands, OUT, env, 240)
        output = (linked.stdout + linked.stderr).decode("mbcs", errors="replace")
        write_new(link_paths["log"], output.encode("utf-8"))
        require(linked.returncode == 0 and not re.search(r"\b(?:fatal\s+)?error\s+LNK\d+|\bwarning\s+LNK\d+|\bLNK(?:2001|2019|1120)\b", output, re.I),
                "Runtime SDK link failed or emitted a linker diagnostic")
        require(sealed.artifact(link_paths["response"]) == link_response, "Link response changed")
        for name, expected in resolutions.items():
            require(sealed.key(resolve(name)) == sealed.key(expected), "DEFAULTLIB resolution changed during link")
        search_events = sealed.verbose_library_searches(output)
        require(search_events, "No authenticated linker library-search evidence")
        searched = {}
        for event in search_events:
            k = sealed.key(event["path"])
            require(k in allowed_libraries and k in sealed.COFF and k in sealed.INPUTS,
                    "Linker searched an unsealed library")
            searched[k] = sealed.INPUTS[k]
        pe = sealed.inspect_pe(dll)
        require(pe["dynamic_base"] and pe["nx_compatible"] and set(pe["imports"]) == set(old_pe["imports"]),
                "Runtime candidate PE/import modules do not match the R11 SDK contract")
        require("zerosislua51_x64.dll" in pe["imports"], "Runtime candidate lacks shared Lua")
        map_text = link_paths["map"].read_text(encoding="mbcs", errors="strict")
        map_checks = map_contract(sealed, map_text, pe, [Path(r["path"]).name for r in current_objects])
        selected, groups = sealed.map_archive_selection(map_text, sealed.COFF, sealed.INPUTS,
            {sealed.key(r["library"]["path"]) for r in providers},
            {sealed.key(r["library"]["path"]) for r in platform}, set(searched))
        require("dummynode_" not in map_text, "A private Lua implementation was linked")
        output_coff = {name: sealed.inspect_output_coff(link_paths[name]) for name in ("library", "exp")}
        for row in compiled:
            for name in ("object", "response", "dependencies", "log"):
                require(sealed.artifact(row[name]["path"]) == row[name], "Compiled artifact changed after link")
        sealed.verify_inputs()
        require(len(calls) == len(active_units) + 2 and Counter(Path(x[0]).name.casefold() for x in calls) ==
                Counter({"cmd.exe": 1, "cl.exe": len(active_units), "link.exe": 1}), "Unexpected build child-command set")
        validation = {"pe": pe, "map": map_checks, "output_coff": output_coff,
            "actual_searched_libraries": list(searched.values()), "library_search_events": search_events,
            "final_selected_libraries": selected, "final_map_library_groups": groups,
            "selection_evidence_source": "link_map_section_owner_member",
            "map_owner_member_pair_count": sum(len(r["members"]) for r in selected),
            "verbose_loaded_member_lines": re.findall(r"(?im)^\s*Loaded\s+([^\r\n]+)", output),
            "selection_scope": "Final unique owner/member labels; not every transient archive extraction.",
            "unresolved_symbols": 0, "linker_warnings": 0}
        write_new(link_paths["validation"], encoded(validation))
        report = {"schema": "zerosis.sdk.current_runtime_candidate.v1",
            "status": "PASS_CURRENT_RUNTIME_SDK_CANDIDATE_COMPILED_LINKED_NOT_LOADED",
            "utc": datetime.now(timezone.utc).isoformat(), "builder": sealed.artifact(__file__),
            "plan": sealed.artifact(PLAN), "base_link": sealed.artifact(BASE),
            "publication": sealed.artifact(PUBLICATION), "preflight": sealed.artifact(PREFLIGHT),
            "superseded_base_metadata_inputs": superseded, "inputs": list(sealed.INPUTS.values()),
            "protected": preflight["protected"], "protected_unchanged": True,
            "compiled_units": compiled, "compiled_sdk_units": 11, "compiled_bridge_units": 4,
            "build_mode": "resume_cached_sdk_cpp14_bridge_cpp17" if resume_proof else "fresh_role_specific_compile",
            "resume_proof": resume_proof, "newly_compiled_units": len(active_units),
            "reused_previously_compiled_sdk_units": len(cached_units),
            "this_attempt_child_command_count": len(calls),
            "object_count": 165, "objects": current_objects, "reused_current_base_objects": 150,
            "providers": providers, "platform_libraries": platform, "shared_lua_library": shared_library,
            "shared_lua_dll": shared_dll, "shared_lua_exports": shared_exports,
            "r11_sdk_contract": old_runtime, "r11_import_modules": sorted(old_pe["imports"]),
            "generated_dll": sealed.artifact(dll), "pe": pe, "link_response": link_response,
            "link_log": sealed.artifact(link_paths["log"]), "link_map": sealed.artifact(link_paths["map"]),
            "import_library": sealed.artifact(link_paths["library"]), "export_object": sealed.artifact(link_paths["exp"]),
            "validation": sealed.artifact(link_paths["validation"]), "linker_exit_code": linked.returncode,
            "compiler_jobs": 1,
            "compiler_flags_by_role": {"sdk_overlay": list(FLAGS), "bridge": list(BRIDGE_FLAGS)},
            "compiler_defines": list(DEFINES),
            "all_compiler_dependencies_prehashed": True, "consumed_inputs": list(dependencies_seen.values()),
            "inputs_unchanged": True, "child_commands": [list(x) for x in calls],
            "hidden_below_normal_children": True, "binary_pch_consumed": False,
            "whole_project_or_sdk_copied": False, "additional_source_copies_by_builder": False,
            "prepared_overlay_source_file_count": 13, "binary_pch_copied": False, "working_sdk_modified": False,
            "runtime_overlay_sources_rebased": True, "shared_lua_import_library_substituted": True,
            "base_export_contract_unchanged": True, "borrowed_registry_unique": True,
            "gamecore_loaded": False, "host_executed": False, "windows_created": False,
            "retail_accessed": False, "user_state_or_processes_accessed": False,
            "full_host_integration": False, "runtime_updated": False, "default_promoted": False,
            "retail_save_accepted": False, "full_player_restore_verified": False,
            "ruleset_compatibility_verified": False, "full_ui_accepted": False,
            "multicore_accepted": False, "performance_improvement_verified": False,
            "full_engine_goal_complete": False,
            "scope": "Current SDK runtime-overlay compilation and static DLL link only; never loaded or promoted."}
        write_new(link_paths["result"], encoded(report))
        print(json.dumps({"status": report["status"], "objects": 165, "newly_compiled": len(active_units),
                          "reused_sdk_compile_cells": len(cached_units), "reused_base": 150,
                          "report": sealed.artifact(link_paths["result"])}))
    except BaseException as error:
        failure = {"status": "FAILED_CURRENT_RUNTIME_SDK_CANDIDATE_PRESERVED",
            "utc": datetime.now(timezone.utc).isoformat(), "error": type(error).__name__ + ": " + str(error),
            "plan_sha256": args.plan_sha256, "output_root": str(OUT), "compiled_units": compiled,
            "resume_proof": resume_proof, "newly_compiled_units": len(compiled) - len(cached_units),
            "reused_previously_compiled_sdk_units": len(cached_units),
            "child_commands": [list(x) for x in calls], "gamecore_loaded": False,
            "runtime_updated": False, "default_promoted": False}
        if not link_paths["failed"].exists():
            write_new(link_paths["failed"], encoded(failure))
        raise


if __name__ == "__main__":
    main()
