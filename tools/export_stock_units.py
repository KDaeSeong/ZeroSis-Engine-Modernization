#!/usr/bin/env python3
"""Extract selected original Warrior inputs and export them after loading their GSD.

The bounded x86 preparation helper never saves GR2 or runs inside the x64 game.
Compiler output and source-input hashes are retained; stop on the first failure.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

from prepare_unit_models import (DEFAULT_GAME, DEFAULT_BRIDGE, DEFAULT_SDK, EXPECTED,
                                 Fpk, require, resolve_pack_name, sha256_file, text)

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
CSC = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe")
CONFIG = b'<?xml version="1.0"?><configuration><startup useLegacyV2RuntimeActivationPolicy="true"><supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.0"/></startup></configuration>'


def artifact(path: Path) -> dict:
    return {"path": str(path.resolve(strict=True)), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def bounded(command: list[str], log_dir: Path, name: str, timeout: int, cwd: Path) -> dict:
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, timeout=timeout,
                                creationflags=subprocess.CREATE_NO_WINDOW, check=False)
        stdout, stderr, rc, timed_out = result.stdout, result.stderr, result.returncode, False
    except subprocess.TimeoutExpired as error:
        stdout, stderr, rc, timed_out = error.stdout or b"", error.stderr or b"", None, True
    out_path, err_path = log_dir / (name + ".stdout.txt"), log_dir / (name + ".stderr.txt")
    out_path.write_bytes(stdout)
    err_path.write_bytes(stderr)
    return {"argv": command, "exit_code": rc, "timed_out": timed_out,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout": artifact(out_path), "stderr": artifact(err_path)}


def prepare_helper(sdk: Path, bridge: Path, run: Path, report: dict) -> Path:
    source = HERE / "StockUnitExporter.cs"
    names = ["Firaxis.Framework.dll", "Firaxis.Framework.Granny.dll",
             "Firaxis.Framework.FirePlace.dll", "Firaxis.Framework.Granny.ImplWin32.dll",
             "CSScriptLibrary.dll"]
    deps = [sdk / name for name in names] + [bridge]
    before = [artifact(p) for p in [source, Path(__file__), CSC, *deps]]
    signature = hashlib.sha256(json.dumps(before, sort_keys=True).encode() + CONFIG).hexdigest()
    tool_dir = PROJECT / "Build" / "UnitModelTools" / ("stock_" + signature[:20])
    seal = tool_dir / "tool-manifest.json"
    exe = tool_dir / "StockUnitExporter.exe"
    if seal.is_file():
        saved = json.loads(seal.read_text(encoding="utf-8"))
        require(saved["signature"] == signature and saved["status"] == "PASS_HELPER_BUILD", "Helper cache seal mismatch")
        for row in saved["outputs"]:
            require(artifact(Path(row["path"])) == row, "Helper cache file changed")
    else:
        require(not tool_dir.exists(), "Unsealed helper directory exists; preserve it and repair source first")
        tool_dir.mkdir(parents=True)
        shutil.copyfile(source, tool_dir / source.name)
        (tool_dir / (exe.name + ".config")).write_bytes(CONFIG)
        # A per-file immutable cache avoids repeatedly allocating SDK dependencies.
        dep_cache = PROJECT / "Build" / "UnitModelTools" / "dependencies"
        for dep in deps:
            sha = sha256_file(dep)
            cache = dep_cache / sha / dep.name
            if not cache.exists():
                cache.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(dep, cache)
            require(sha256_file(cache) == sha, "Preparation dependency cache changed")
            target = tool_dir / dep.name
            os.link(cache, target)
        command = [str(CSC), "/nologo", "/target:exe", "/platform:x86", "/unsafe", "/optimize+", "/warnaserror+",
                   "/out:" + str(exe), "/r:System.Core.dll", "/r:System.Web.Extensions.dll"]
        command += ["/r:" + str(tool_dir / name) for name in names[:3]]
        command += ["/r:" + str(tool_dir / bridge.name), str(tool_dir / source.name)]
        compilation = bounded(command, tool_dir, "compile", 45, tool_dir)
        report["compiler"] = compilation
        require(compilation["exit_code"] == 0 and exe.is_file(), "Stock helper compilation failed: " + compilation["stdout"]["path"])
        output_paths = [tool_dir / source.name, exe, tool_dir / (exe.name + ".config")]
        output_paths += [tool_dir / dep.name for dep in deps]
        write_json(seal, {"status": "PASS_HELPER_BUILD", "signature": signature, "inputs": before,
                          "outputs": [artifact(p) for p in output_paths], "compiler": compilation})
    report["helper"] = {"manifest": artifact(seal), "exe": artifact(exe)}
    require(before == [artifact(p) for p in [source, Path(__file__), CSC, *deps]], "Preparation tool inputs changed")
    return exe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--sdk", type=Path, default=DEFAULT_SDK)
    parser.add_argument("--bridge", type=Path, default=DEFAULT_BRIDGE)
    args = parser.parse_args()
    game, sdk, bridge = (p.resolve(strict=True) for p in (args.game, args.sdk, args.bridge))
    ctypes.windll.kernel32.SetErrorMode(0x8003)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run = PROJECT / "Build" / "StockUnitExports" / run_id
    run.mkdir(parents=True, exist_ok=False)
    report = {"schema": 1, "status": "RUNNING", "run_id": run_id, "inputs": [], "outputs": [], "helper_calls": []}
    manifest_path = run / "export-manifest.json"
    try:
        pack_path = game / "Resource" / "Common" / "UnitModels.fpk"
        unit_path = game / "Assets" / "Units" / "Civ5ArtDefines_Units.xml"
        member_path = game / "Assets" / "Units" / "Civ5ArtDefines_UnitMembers.xml"
        original_paths = [pack_path, unit_path, member_path]
        report["inputs"] = [artifact(p) for p in original_paths]
        pack = Fpk(pack_path)
        unit = [n for n in ET.fromstring(unit_path.read_bytes()).findall(".//UnitArtInfo")
                if text(n, "Type") == "ART_DEF_UNIT__WARRIOR"]
        require(len(unit) == 1, "Original Warrior ArtDef not unique")
        require({text(n, "MemberType"): int(text(n, "MemberCount")) for n in unit[0].findall("UnitMemberArt")} == EXPECTED,
                "Unexpected stock Warrior member counts")
        member_rows = {text(n, "Type"): text(n, "Granny") for n in ET.fromstring(member_path.read_bytes()).findall(".//UnitMemberArtInfo")
                       if text(n, "Type") in EXPECTED}
        require(set(member_rows) == set(EXPECTED), "Missing original Warrior member definitions")

        def extract(reference: str) -> tuple[Path, dict]:
            raw, origin = pack.read(resolve_pack_name(pack, reference))
            target = run / Path(reference.replace("\\", "/")).name
            require(target.parent == run and len(raw) <= 64 * 1024 * 1024, "Invalid extracted candidate path/size")
            if target.exists():
                require(target.read_bytes() == raw, "Conflicting selected FPK basename")
            else:
                target.write_bytes(raw)
            return target, {**origin, "extracted": artifact(target)}

        gsd, gsd_origin = extract("unitmodels_stringdatabase.gsd")
        report["gsd"] = gsd_origin
        exe = prepare_helper(sdk, bridge, run, report)
        # Each child retains both model/animation objects, loads GSD first, and has a 45s bound.
        for member in EXPECTED:
            fxs, fxs_origin = extract(member_rows[member])
            xml = ET.fromstring(fxs.read_bytes())
            model_refs = [n.attrib["file"] for n in xml.findall(".//Mesh")]
            idle_refs = [n.attrib["file"] for n in xml.findall(".//Animation")
                         if n.attrib.get("file", "").replace("\\", "/").rsplit("/", 1)[-1].casefold() == "warrior_idlea.gr2"]
            require(len(model_refs) == 1 and len(idle_refs) == 1, "Unexpected Warrior mesh/idle references")
            model, model_origin = extract(model_refs[0])
            idle, idle_origin = extract(idle_refs[0])
            output = run / (member + ".json")
            call = bounded([str(exe), str(sdk), str(gsd), str(model), str(idle), str(output)], run, member, 45, exe.parent)
            report["helper_calls"].append(call)
            require(call["exit_code"] == 0 and not call["timed_out"], "Stock helper failed; remaining members were not launched: " + call["stderr"]["path"])
            require(output.is_file() and output.stat().st_size <= 32 * 1024 * 1024, "Missing/oversized stock export")
            data = json.loads(output.read_text(encoding="utf-8"))
            require(data["source_sha256"] == sha256_file(model) and data["gsd_sha256"] == sha256_file(gsd)
                    and data["animation_sha256"] == sha256_file(idle), "Export provenance mismatch")
            report["outputs"].append({"member_type": member, "json": artifact(output),
                                      "model": model_origin, "idle": idle_origin, "fxsxml": fxs_origin})
        report["inputs_after"] = [artifact(p) for p in original_paths]
        require(report["inputs"] == report["inputs_after"], "Original inputs changed")
        report["status"] = "PASS_STOCK_UNIT_EXPORT"
    except Exception as error:
        report["status"] = "FAILED_STOCK_UNIT_EXPORT"
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        write_json(manifest_path, report)
    print(json.dumps({"status": report["status"], "exports": str(run), "manifest": str(manifest_path),
                      "outputs": len(report["outputs"]), "error": report.get("error")}, indent=2))
    return 0 if report["status"] == "PASS_STOCK_UNIT_EXPORT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
