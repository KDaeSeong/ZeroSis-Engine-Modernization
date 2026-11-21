"""Build official Lua 5.1.4 for isolated x64 boundary tests, not GameCore deployment."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path, PurePosixPath
import re
import tarfile
import urllib.request

from collect_baseline import PROJECT, digest, read_text
from native_build import environment_for, run, checked_run

URL = "https://www.lua.org/ftp/lua-5.1.4.tar.gz"
SHA256 = "b038e225eaf2a5b57c9bcc35cd13aa8c6c8288ef493d52970c9545074098af3a"


def prepare_source():
    archive = PROJECT / "Source/ThirdParty/lua-5.1.4.tar.gz"
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.is_file():
        with urllib.request.urlopen(URL, timeout=30) as response:
            data = response.read(1000000)
        import hashlib
        if hashlib.sha256(data).hexdigest() != SHA256:
            raise RuntimeError("Official Lua archive checksum mismatch")
        archive.write_bytes(data)
    if digest(archive) != SHA256:
        raise RuntimeError("Pinned Lua archive changed")
    sources = []
    with tarfile.open(archive, "r:gz") as package:
        for member in package.getmembers():
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts or relative.parts[0] != "lua-5.1.4":
                raise RuntimeError("Unexpected archive path")
            if member.isdir():
                continue
            if not member.isfile():
                raise RuntimeError("Links/special files are not accepted")
            target = archive.parent.joinpath(*relative.parts)
            content = package.extractfile(member).read()
            if target.exists() and target.read_bytes() != content:
                raise RuntimeError(f"Existing upstream source was modified: {target}")
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                target.write_bytes(content)
            sources.append({"path": str(target), "sha256": digest(target)})
    return archive, sources


def build(vs):
    archive, sources = prepare_source()
    root = archive.parent / "lua-5.1.4/src"
    evidence = PROJECT / "evidence/lua_component"
    directory = PROJECT / "Build/Lua_component/x64"
    evidence.mkdir(parents=True, exist_ok=True)
    env, compiler = environment_for(vs, "x64", directory)
    units = sorted(p for p in root.glob("*.c") if p.name not in {"lua.c", "luac.c", "print.c"})
    response = directory / "compile.rsp"
    flags = ["/nologo", "/c", "/TC", "/O2", "/MT", "/fp:strict", "/W3", "/D_CRT_SECURE_NO_WARNINGS",
             f'/Fo"{directory.as_posix()}/"']
    response.write_text("\n".join(flags + [f'"{p}"' for p in units]), encoding="utf-8")
    result = run([compiler, f"@{response}"], cwd=directory, env=env, timeout=180)
    log = evidence / "compile_x64.log"
    log.write_bytes(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"Lua component compilation failed: {log}")
    library = directory / "lua514_component.lib"
    objects = [directory / p.with_suffix(".obj").name for p in units]
    checked_run([Path(compiler).with_name("lib.exe"), "/nologo", f"/OUT:{library}", *objects], cwd=directory, env=env)
    sdk_headers = PROJECT / "Source/SDK_BNW_Original/ThirdPartyLibs/Lua51/include"
    comparison = []
    for name in ("lua.h", "luaconf.h", "lauxlib.h", "lualib.h"):
        left, right = sdk_headers / name, root / name
        comparison.append({"file": name, "sdk_path": str(left), "sdk_sha256": digest(left),
            "upstream_path": str(right), "upstream_sha256": digest(right),
            "same_after_newline_normalization": left.read_bytes().replace(b"\r\n", b"\n") == right.read_bytes().replace(b"\r\n", b"\n")})
    output = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "status": "LUA514_X64_COMPONENT_BUILT",
        "source_url": URL, "checksum_source": "https://www.lua.org/ftp/", "archive": {"path": str(archive), "sha256": SHA256},
        "sources": sources, "translation_units": len(units), "runtime": "/MT",
        "builder": {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__))},
        "library": {"path": str(library), "sha256": digest(library)},
        "log": {"path": str(log), "sha256": digest(log)}, "sdk_header_comparison": comparison,
        "warnings": sorted(set(re.findall(r"(?m)^.*\bwarning\s+[A-Z]+\d+[^\r\n]*", read_text(log)))),
        "scope": "OFFICIAL_LUA_STANDALONE_TEST_PROVIDER_NOT_GAMECORE_PROVIDER_ACCEPTANCE",
        "game_launched": False, "gamecore_linked": False}
    (evidence / "build_result.json").write_text(json.dumps(output, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], "translation_units": len(units),
                      "headers_equal": all(r["same_after_newline_normalization"] for r in comparison),
                      "warning_lines": len(output["warnings"])}))
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vs", type=Path, required=True)
    build(parser.parse_args().vs)
