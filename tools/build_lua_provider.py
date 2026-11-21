"""Build a tracked x64 /MD Lua 5.1 provider with measured SDK rounding compatibility."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from build_lua_component import prepare_source
from build_sdk_x64 import object_machine
from collect_baseline import PROJECT, digest, read_text
from native_build import environment_for, run, checked_run


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


def initial_specification(upstream):
    patches = []
    def patch(file, old, new, count, reason):
        source = upstream / file
        if source.read_text(encoding="ascii").count(old) != count:
            raise RuntimeError(f"Upstream patch context drift: {file}")
        patches.append({"id": f"lua51_{len(patches)+1:02d}", "file": file, "source_sha256": digest(source),
                        "old": old, "new": new, "count": count, "reason": reason})
    configuration = PROJECT / "Source/SDK_BNW_Original/ThirdPartyLibs/Lua51/include/luaconf.h"
    sdk_text = configuration.read_text(encoding="ascii")
    official_text = (upstream / "src/luaconf.h").read_text(encoding="ascii")
    for pattern in (r'#define LUA_CPATH_DEFAULT \\\n([^\n]+)',):
        old_lines = re.findall(pattern, official_text)
        new_lines = re.findall(pattern, sdk_text)
        if len(old_lines) != 2 or len(new_lines) != 2:
            raise RuntimeError("Expected Windows/POSIX Lua module search paths")
        for old, new in zip(old_lines, new_lines):
            patch("src/luaconf.h", old, new, 1, "Retain the SDK module search paths without changing Lua public types")
    old = "#if defined(LUA_NUMBER_DOUBLE) && !defined(LUA_ANSI) && !defined(__SSE2__) && \\\n"
    new = """/* SDK x86 uses x87 FISTP. Match its current rounding mode on x64 SSE2. */
#if defined(LUA_NUMBER_DOUBLE) && !defined(LUA_ANSI) && defined(_MSC_VER) && defined(_M_X64)
#include <emmintrin.h>
#define lua_number2int(i,d) ((i) = _mm_cvtsd_si32(_mm_set_sd(d)))
#define lua_number2integer(i,n) ((i) = (lua_Integer)_mm_cvtsd_si64(_mm_set_sd(n)))
#elif defined(LUA_NUMBER_DOUBLE) && !defined(LUA_ANSI) && !defined(__SSE2__) && \\
"""
    patch("src/luaconf.h", old, new, 1, "Preserve measured x86 SDK rounding in all four modes; retain native-width Lua integers")
    patch("src/lgc.c", "sizeof(Node) * sizenode(h)", "sizeof(Node) * cast(size_t, sizenode(h))", 1,
          "Explicitly promote bounded node count to native allocation width after the original shift")
    patch("src/ltable.c", "luaM_freearray(L, nold, twoto(oldhsize), Node)",
          "luaM_freearray(L, nold, cast(size_t, twoto(oldhsize)), Node)", 1,
          "Explicit native byte-count operand, retaining the original table-size bound")
    patch("src/ltable.c", "luaM_freearray(L, t->node, sizenode(t), Node)",
          "luaM_freearray(L, t->node, cast(size_t, sizenode(t)), Node)", 1,
          "Explicit native byte-count operand, retaining the original table-size bound")
    return {"format": 1, "scope": "LUA51_X64_MD_PROVIDER_CANDIDATE", "patches": patches,
            "sdk_configuration": {"path": str(configuration), "sha256": digest(configuration)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vs", type=Path, required=True)
    args = parser.parse_args()
    archive, originals = prepare_source()
    upstream = archive.parent / "lua-5.1.4"
    evidence = PROJECT / "evidence/lua_provider"
    evidence.mkdir(parents=True, exist_ok=True)
    specification = PROJECT / "Source/Providers/Lua51/patches.json"
    if not specification.exists():
        save(specification, initial_specification(upstream))
    plan = json.loads(specification.read_text(encoding="utf-8"))
    if digest(Path(plan["sdk_configuration"]["path"])) != plan["sdk_configuration"]["sha256"]:
        raise RuntimeError("SDK configuration input changed")
    manifest_path = evidence / "port_manifest.json"
    prior = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else []
    prior_hashes = {r["path"]: r["sha256"] for r in prior}
    root = PROJECT / "Source/Lua51_x64"
    generated = []
    for row in originals:
        source = Path(row["path"])
        relative = source.relative_to(upstream).as_posix()
        if not relative.startswith("src/") and relative != "COPYRIGHT":
            continue
        content = source.read_bytes().decode("ascii")
        applied = []
        for patch in (p for p in plan["patches"] if p["file"] == relative):
            if digest(source) != patch["source_sha256"] or content.count(patch["old"]) != patch["count"]:
                raise RuntimeError(f"Provider patch input differs: {patch['id']}")
            content = content.replace(patch["old"], patch["new"])
            applied.append(patch["id"])
        target = root / relative
        data = content.encode("ascii")
        if target.exists() and target.read_bytes() != data and digest(target) != prior_hashes.get(str(target)):
            raise RuntimeError(f"Untracked provider edit: {target}")
        generated.append((source, target, data, applied))
    manifest = []
    for source, target, data, applied in generated:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        manifest.append({"path": str(target), "sha256": digest(target), "upstream": str(source),
                         "upstream_sha256": digest(source), "patch_ids": applied})
    save(manifest_path, manifest)
    directory = PROJECT / "Build/Lua_provider/x64"
    env, compiler = environment_for(args.vs, "x64", directory)
    sources = sorted(p for p in (root / "src").glob("*.c") if p.name not in {"lua.c", "luac.c", "print.c"})
    response = directory / "compile.rsp"
    flags = ["/nologo", "/c", "/TC", "/O2", "/MD", "/fp:strict", "/W3", "/WX", "/D_CRT_SECURE_NO_WARNINGS",
             f'/Fo"{directory.as_posix()}/"']
    response.write_text("\n".join(flags + [f'"{p}"' for p in sources]), encoding="utf-8")
    result = run([compiler, f"@{response}"], cwd=directory, env=env, timeout=180)
    log = evidence / "compile_x64.log"
    log.write_bytes(result.stdout + result.stderr)
    if result.returncode or re.search(r"\bwarning\s+[A-Z]+\d+", read_text(log)):
        raise RuntimeError(f"Lua provider compilation failed: {log}\n{read_text(log)[:4000]}")
    library = directory / "ZeroSis_Lua51_x64.lib"
    objects = [directory / source.with_suffix(".obj").name for source in sources]
    checked_run([Path(compiler).with_name("lib.exe"), "/nologo", f"/OUT:{library}", *objects], cwd=directory, env=env)
    machines = [object_machine(path) for path in objects]
    if len(machines) != 29 or any(r["architecture"] != "x64" for r in machines):
        raise RuntimeError("Provider object architecture mismatch")
    if any(digest(Path(r["path"])) != r["sha256"] for r in manifest):
        raise RuntimeError("Provider source changed while compiling")
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "status": "LUA51_X64_MD_PROVIDER_BUILT",
        "runtime": "/MD", "translation_units": 29, "compiler_and_linker_warnings": 0,
        "library": {"path": str(library), "sha256": digest(library)}, "objects": machines,
        "source_manifest": {"path": str(manifest_path), "sha256": digest(manifest_path)},
        "patches": {"path": str(specification), "sha256": digest(specification)},
        "builder": {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__))},
        "compiler": {"path": compiler, "sha256": digest(Path(compiler))},
        "log": {"path": str(log), "sha256": digest(log)}, "response": {"path": str(response), "sha256": digest(response)},
        "sdk_configuration": plan["sdk_configuration"], "scope": "PROVIDER_BUILD_NOT_GAMECORE_LINK_OR_GAME_ACCEPTANCE",
        "game_launched": False, "gamecore_runtime_verified": False}
    save(evidence / "build_result.json", result)
    print(json.dumps({k: result[k] for k in ("status", "translation_units", "compiler_and_linker_warnings", "runtime")}))


if __name__ == "__main__":
    main()
