"""Compare the actual SDK x86 Lua archive with an x64 library in standalone processes."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import random
import re
import shutil
import struct

from collect_baseline import PROJECT, digest, pe_header, read_text
from native_build import build_program, checked_run, run, environment_for


def legacy_build(evidence, label):
    vc = Path(r"C:\Program Files (x86)\Microsoft Visual Studio 9.0\VC")
    winsdk = Path(r"C:\Program Files (x86)\Microsoft SDKs\Windows\v7.0A")
    snapshot = PROJECT / "Source/SDK_BNW_Original/ThirdPartyLibs/Lua51"
    manifest = json.loads((PROJECT / "evidence/sdk_reference/snapshot_manifest.json").read_text(encoding="utf-8"))
    for row in manifest:
        if Path(row["snapshot"]).is_relative_to(snapshot):
            if digest(Path(row["snapshot"])) != row["sha256"] or digest(Path(row["source"])) != row["sha256"]:
                raise RuntimeError("SDK Lua reference differs from preserved original")
    directory = PROJECT / "Build/Lua_reference" / label / "x86"
    directory.mkdir(parents=True, exist_ok=True)
    # The SDK .lib is an import library, not a static implementation archive.
    with (PROJECT / "evidence/2026-09-22/binary_inventory.csv").open(encoding="utf-8-sig") as stream:
        dll_row = next(r for r in csv.DictReader(stream) if Path(r["path"]).name.lower() == "lua51_win32.dll")
    original_dll = Path(dll_row["path"])
    reference_dll = directory / original_dll.name
    if digest(original_dll) != dll_row["sha256"]:
        raise RuntimeError("Installed Lua reference changed since M0")
    if reference_dll.exists() and digest(reference_dll) != dll_row["sha256"]:
        raise RuntimeError("Untracked reference DLL; refusing overwrite")
    shutil.copyfile(original_dll, reference_dll)
    source = PROJECT / "Tests/lua_compatibility_trace.cpp"
    compiler, library = vc / "bin/cl.exe", snapshot / "lib/lua51_Win32.lib"
    executable = directory / "lua_reference.exe"
    env = {key.upper(): value for key, value in os.environ.items()}
    env["INCLUDE"] = f"{vc / 'include'};{winsdk / 'Include'}"
    env["LIB"] = f"{vc / 'lib'};{winsdk / 'Lib'}"
    env["PATH"] = f"{vc / 'bin'};{vc.parent / 'Common7/IDE'};{winsdk / 'bin'};{env.get('PATH', '')}"
    flags = ["/nologo", "/EHsc", "/W4", "/WX", "/O2", "/fp:strict", "/MD", "/D_CRT_SECURE_NO_WARNINGS",
             f'/I"{snapshot / "include"}"', f'"{source}"', f'/Fo"{directory / "lua_reference.obj"}"',
             f'/Fe"{executable}"', f'"{library}"', "/link", "/LTCG", "/OPT:REF", "/OPT:ICF", "/INCREMENTAL:NO",
             "/MACHINE:X86", "/WX", f'/MAP:"{directory / "lua_reference.map"}"']
    response = directory / "compile.rsp"
    split = flags.index("/link")
    response.write_text("\n".join(flags[:split]), encoding="ascii")
    result = run([compiler, f"@{response}", "/link", *[v.replace('"', '') for v in flags[split+1:]]],
                 cwd=directory, env=env, timeout=120)
    log = evidence / "build_sdk_x86.log"
    log.write_bytes(result.stdout + result.stderr)
    if result.returncode or re.search(r"\bwarning\s+[A-Z]+\d+", read_text(log)):
        raise RuntimeError(f"SDK Lua reference build failed: {log}\n{read_text(log)[:3000]}")
    manifest_file = executable.with_suffix(".exe.manifest")
    if manifest_file.exists():
        checked_run([winsdk / "bin/mt.exe", "-nologo", "-manifest", manifest_file,
                     f"-outputresource:{executable};1"], cwd=directory, env=env)
    link_map = directory / "lua_reference.map"
    proof = [line.strip() for line in read_text(link_map).splitlines()
             if re.search(r"\s_lua(?:_tointeger|L_checkinteger|L_optinteger)\s", line)]
    if len(proof) != 3 or any("lua51_Win32:" not in line for line in proof):
        raise RuntimeError(f"SDK Lua archive provider not proven in map: {proof}")
    return {"path": str(executable), "sha256": digest(executable), "pe": pe_header(executable),
            "library": {"path": str(library), "sha256": digest(library)},
            "dll": {"path": str(reference_dll), "sha256": digest(reference_dll)},
            "dll_source": {"path": str(original_dll), "sha256": digest(original_dll)},
            "map": {"path": str(link_map), "sha256": digest(link_map)}, "map_proof": proof,
            "log": {"path": str(log), "sha256": digest(log)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vs", type=Path, required=True)
    parser.add_argument("--library", type=Path)
    parser.add_argument("--runtime", choices=("MT", "MD"), default="MT")
    parser.add_argument("--label", default="upstream")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_]+", args.label):
        raise RuntimeError("Invalid evidence label")
    evidence = PROJECT / "evidence/lua_reference" / args.label
    evidence.mkdir(parents=True, exist_ok=True)
    directory = PROJECT / "Build/Lua_reference" / args.label
    directory.mkdir(parents=True, exist_ok=True)
    reference = legacy_build(evidence, args.label)
    library = (args.library or PROJECT / "Build/Lua_component/x64/lua514_component.lib").resolve()
    source = PROJECT / "Tests/lua_compatibility_trace.cpp"
    before = {str(p): digest(p) for p in (source, library, Path(reference["library"]["path"]),
              Path(reference["dll"]["path"]), Path(reference["dll_source"]["path"]), Path(__file__).resolve())}
    if args.runtime == "MT":
        candidate = build_program(name="lua_candidate", architecture="x64", vs=args.vs, directory=directory,
            evidence=evidence, source=source, includes=[PROJECT / "Source/SDK_BNW_x64/ThirdPartyLibs/Lua51/include"],
            defines=["_CRT_SECURE_NO_WARNINGS"], objects=[library])
    else:
        env, compiler = environment_for(args.vs, "x64", directory)
        executable = directory / "lua_candidate.exe"
        response = directory / "compile.rsp"
        flags = ["/nologo", "/EHsc", "/W4", "/WX", "/O2", "/fp:strict", "/MD", "/D_CRT_SECURE_NO_WARNINGS",
            f'/I"{PROJECT / "Source/SDK_BNW_x64/ThirdPartyLibs/Lua51/include"}"', f'"{source}"',
            f'/Fo"{directory / "lua_candidate.obj"}"', f'/Fe"{executable}"', f'"{library}"',
            "/link", "/INCREMENTAL:NO", "/WX", "/MACHINE:X64"]
        split = flags.index("/link")
        response.write_text("\n".join(flags[:split]), encoding="utf-8")
        result = run([compiler, f"@{response}", "/link", *flags[split+1:]], cwd=directory, env=env, timeout=120)
        log = evidence / "build_candidate.log"
        log.write_bytes(result.stdout + result.stderr)
        if result.returncode or re.search(r"\bwarning\s+[A-Z]+\d+", read_text(log)):
            raise RuntimeError(f"Candidate build failed: {log}\n{read_text(log)[:4000]}")
        candidate = {"path": str(executable), "sha256": digest(executable), "pe": pe_header(executable),
                     "log": {"path": str(log), "sha256": digest(log)}}
    rng = random.Random(51464)
    values = {float(n) for n in range(-1024, 1025)}
    for n in (-2147483647, -65536, -32768, -256, -3, -1, 0, 1, 3, 255, 32767, 65535, 2147483646):
        for fraction in (0, 0.125, 0.25, 0.5, 0.75, 0.875):
            values.add(n + fraction)
    values.update(float(rng.randint(-2147483648, 2147483647)) for _ in range(4096))
    values.update({-2147483648.0, 2147483647.0})
    values = sorted(values)
    fixture = directory / "inputs.bin"
    fixture.write_bytes(b"ZLUA0001" + struct.pack("<I", len(values)) + struct.pack(f"<{len(values)}d", *values))
    runs = []
    for name, build in (("sdk_x86", reference), ("candidate_x64", candidate)):
        trace, scripts = evidence / f"{name}_conversions.bin", evidence / f"{name}_scripts.bin"
        result = checked_run([build["path"], fixture, trace, scripts], cwd=directory, timeout=90)
        native = json.loads(result.stdout.decode("utf-8"))
        if native["inputs"] != len(values) or native["conversion_results"] != len(values) * 12:
            raise RuntimeError("Unexpected native coverage")
        runs.append({"native": native, "build": build, "trace": {"path": str(trace), "sha256": digest(trace)},
                     "scripts": {"path": str(scripts), "sha256": digest(scripts)}})
    a, b = [Path(r["trace"]["path"]).read_bytes() for r in runs]
    reference_values, candidate_values = [struct.unpack(f"<{len(values)*12}q", v) for v in (a, b)]
    differences = []
    api = ("lua_tointeger", "luaL_checkinteger", "luaL_optinteger")
    mode_names = ("nearest", "downward", "upward", "toward_zero")
    for i, (left, right) in enumerate(zip(reference_values, candidate_values)):
        if left != right:
            mode, rest = divmod(i, len(values) * 3)
            case, function = divmod(rest, 3)
            differences.append({"mode": mode_names[mode], "input": values[case], "api": api[function], "sdk": left, "x64": right})
    oracle = []
    for rounding in (round, math.floor, math.ceil, math.trunc):
        for value in values:
            oracle.extend([rounding(value)] * 3)
    oracle_bytes = struct.pack(f"<{len(oracle)}q", *oracle)
    if a != oracle_bytes:
        raise RuntimeError("Actual SDK result did not match the four-mode integer oracle")
    expected_scripts = [sum((i*17)%991 for i in range(1,10001)), sum((i*i)%997 for i in range(1,3001)),
        sum(10+i*(i+1)//2 for i in range(1,513)), 93*7, sum(i*i for i in range(1,65)),
        sum(i*i for i in range(1,1025)), 128*256+255*65536, 100, 1, math.isqrt(123456789)+1234+7, 3, 317*317+3]
    expected_bytes = struct.pack("<12q", *expected_scripts)
    if any(Path(r["scripts"]["path"]).read_bytes() != expected_bytes for r in runs):
        raise RuntimeError("Lua script output differs from independent expected values")
    if any(digest(Path(path)) != value for path, value in before.items()):
        raise RuntimeError("Lua comparison inputs changed")
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SDK_LUA_X86_X64_CONFORMANCE_PASS" if not differences else "LUA_COMPATIBILITY_DIFFERENCES_CAPTURED",
        "input_sha256": before, "fixture": {"path": str(fixture), "sha256": digest(fixture)}, "runs": runs,
        "numeric_inputs": len(values), "rounding_modes": 4, "conversion_results": len(values)*12,
        "different_results": len(differences), "differences": differences,
        "sdk_matches_python_rounding_oracle": True, "scripts_match_python_oracle": True,
        "script_cases": 12, "oracle_trace_sha256": hashlib.sha256(oracle_bytes).hexdigest(),
        "library": {"path": str(library), "sha256": digest(library)}, "runtime": args.runtime,
        "scope": "ACTUAL_LUA_LIBRARIES_IN_STANDALONE_PROCESSES_NOT_GAMECORE", "game_launched": False,
        "excluded": ["full Lua API conformance", "all allocator failure paths", "cross-architecture bytecode loading",
                     "engine Lua locks/callback ownership", "game save/load and mod compatibility"]}
    (evidence / "conformance.json").write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k:result[k] for k in ("status", "numeric_inputs", "conversion_results", "different_results", "script_cases")}))


if __name__ == "__main__":
    main()
