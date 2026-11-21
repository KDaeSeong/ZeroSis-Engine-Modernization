"""Generate a tracked BNW x64 source port and compile only; never link/load/deploy a DLL."""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import struct
import subprocess
import xml.etree.ElementTree as ET

from collect_baseline import PROJECT, digest, read_text
from native_build import environment_for


def save(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def generate_port(evidence, patches_path):
    snapshot_root = PROJECT / "Source/SDK_BNW_Original"
    destination_root = PROJECT / "Source/SDK_BNW_x64"
    manifest_path = evidence / "port_manifest.json"
    prior = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else []
    previous = {row["relative_path"]: row["port_sha256"] for row in prior}
    original = json.loads((PROJECT / "evidence/sdk_reference/snapshot_manifest.json").read_text(encoding="utf-8"))
    specification = json.loads(patches_path.read_text(encoding="utf-8"))
    patches = specification["patches"]
    known = {Path(row["snapshot"]).relative_to(snapshot_root).as_posix() for row in original}
    if any(patch["file"] not in known for patch in patches):
        raise RuntimeError("Patch target is not in the verified SDK snapshot")
    # Preflight every original and destination before making any source change.
    generated = []
    for entry in original:
        snapshot = Path(entry["snapshot"])
        if digest(snapshot) != entry["sha256"] or digest(Path(entry["source"])) != entry["sha256"]:
            raise RuntimeError(f"Original SDK/snapshot differs: {snapshot}")
        relative = snapshot.relative_to(snapshot_root).as_posix()
        content = snapshot.read_bytes()
        applied = []
        for patch in (item for item in patches if item["file"] == relative):
            if patch["source_sha256"] != entry["sha256"]:
                raise RuntimeError(f"Patch base hash differs: {patch['id']}")
            old, new = patch["old"].encode("latin-1"), patch["new"].encode("latin-1")
            if not old or content.count(old) != patch["count"]:
                raise RuntimeError(f"Patch match count differs: {patch['id']}")
            content = content.replace(old, new)
            applied.append(patch["id"])
        target = destination_root / relative
        if target.exists() and target.read_bytes() != content and digest(target) != previous.get(relative):
            raise RuntimeError(f"Untracked port edit; refusing overwrite: {target}")
        generated.append((entry, relative, target, content, applied))
    manifest = []
    for entry, relative, target, content, applied in generated:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != content:
            target.write_bytes(content)
        manifest.append({"relative_path": relative, "source": entry["source"], "snapshot": entry["snapshot"],
                         "original_sha256": entry["sha256"], "port": str(target),
                         "port_sha256": digest(target), "patch_ids": applied})
    save(manifest_path, manifest)
    return destination_root, manifest


def object_machine(path):
    with path.open("rb") as stream:
        header = stream.read(8)
    first = struct.unpack_from("<H", header)[0]
    machine = struct.unpack_from("<H", header, 6)[0] if header[:4] == b"\0\0\xff\xff" else first
    return {"path": str(path), "sha256": digest(path), "machine": f"0x{machine:04x}",
            "architecture": "x64" if machine == 0x8664 else "unexpected"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vs", type=Path, required=True)
    parser.add_argument("--phase", choices=("pch", "all"), default="all")
    args = parser.parse_args()
    evidence = PROJECT / "evidence/sdk_x64"
    evidence.mkdir(parents=True, exist_ok=True)
    patches_path = PROJECT / "Source/Porting/sdk_x64_patches.json"
    root, manifest = generate_port(evidence, patches_path)
    attempts = evidence / "attempts"
    attempts.mkdir(exist_ok=True)
    number = max((int(path.name.split("_")[-1]) for path in attempts.glob("attempt_*") if path.is_dir()), default=0) + 1
    attempt = attempts / f"attempt_{number:03d}"
    attempt.mkdir()
    build = PROJECT / "Build/SDK_x64" / attempt.name
    obj = build / "obj"
    obj.mkdir(parents=True, exist_ok=True)
    env, compiler = environment_for(args.vs, "x64", build)
    env["VSLANG"] = "1033"
    gamecore = root / "CvGameCoreDLL_Expansion2"
    project = gamecore / "CvGameCoreDLL_Expansion2.vs2013.vcxproj"
    ns = {"m": "http://schemas.microsoft.com/developer/msbuild/2003"}
    units = [node.attrib["Include"] for node in ET.parse(project).findall(".//m:ClCompile[@Include]", ns)]
    if len({Path(name).stem for name in units}) != len(units):
        raise RuntimeError("Output object names collide")
    pch_name = "CvGameCoreDLLPCH.h"
    support_inputs = [{"path": str(path), "sha256": digest(path)}
                      for path in [*sorted((PROJECT / "Source/Porting").glob("*.h")),
                                   PROJECT / "Source/LuaBorrowed/ZeroSisLuaBorrowed.h"]]
    includes = [gamecore, PROJECT / "Source/Porting", PROJECT / "Source/LuaBorrowed"] + [root / path for path in (
        "CvWorldBuilderMap/include", "CvGameCoreDLLUtil/include", "CvLocalization/include", "CvGameDatabase/include",
        "FirePlace/include", "FirePlace/include/FireWorks", "ThirdPartyLibs/Lua51/include")]
    flags = ["/nologo", "/c", "/std:c++14", "/EHsc", "/MD", "/Od", "/fp:strict", "/W3", "/bigobj", "/FC",
             "/we4302", "/we4311", "/we4312",
             "/DFXS_IS_DLL", "/DWIN32", "/DNDEBUG", "/D_WINDOWS", "/D_USRDLL", "/DCVGAMECOREDLL_EXPORTS",
             "/DFINAL_RELEASE", "/D_CRT_SECURE_NO_WARNINGS",
             "/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS"]
    flags += [f'/I"{path}"' for path in includes]
    flags += [f'/Fp"{build / "GameCore_x64.pch"}"', f'/Fo"{obj.as_posix()}/"']
    executions = []

    def compile_units(label, names, extra):
        response = attempt / f"{label}.rsp"
        response.write_text("\n".join(flags + extra + [f'"{gamecore / name}"' for name in names]) + "\n", encoding="utf-8")
        log = attempt / f"{label}.log"
        print(json.dumps({"phase": label, "attempt": number, "translation_units": len(names)}), flush=True)
        started = datetime.now(timezone.utc).isoformat()
        with log.open("wb") as stream:
            result = subprocess.run([compiler, f"@{response}"], cwd=gamecore, env=env,
                                    stdout=stream, stderr=subprocess.STDOUT, timeout=900,
                                    creationflags=subprocess.CREATE_NO_WINDOW)
        output = read_text(log)
        warnings = sorted(set(re.findall(r"(?m)^.*\bwarning\s+[A-Z]+\d+[^\r\n]*", output)))
        errors = sorted(set(re.findall(r"(?m)^.*\b(?:fatal )?error\s+[A-Z]+\d+[^\r\n]*", output)))
        executions.append({"phase": label, "started_at_utc": started,
                           "finished_at_utc": datetime.now(timezone.utc).isoformat(), "exit_code": result.returncode,
                           "log": str(log), "log_sha256": digest(log), "response": str(response), "response_sha256": digest(response),
                           "translation_units": names, "unique_warning_lines": warnings, "unique_error_lines": errors})
        return result.returncode == 0

    pch_ok = compile_units("pch", ["_precompile.cpp"], [f"/Yc{pch_name}"])
    all_ok = False
    if pch_ok and args.phase == "all":
        all_ok = compile_units("gamecore", [name for name in units if name != "_precompile.cpp"], [f"/Yu{pch_name}", "/MP4"])
    objects = [object_machine(path) for path in sorted(obj.glob("*.obj"))]
    original_match = all(digest(Path(row["source"])) == row["original_sha256"]
                         and digest(Path(row["snapshot"])) == row["original_sha256"] for row in manifest)
    port_match = all(digest(Path(row["port"])) == row["port_sha256"] for row in manifest)
    port_match = port_match and all(digest(Path(row["path"])) == row["sha256"] for row in support_inputs)
    status = ("SDK_X64_ALL_OBJECTS_COMPILED" if all_ok and len(objects) == len(units) else
              "SDK_X64_PCH_COMPILED" if pch_ok and args.phase == "pch" else "SDK_X64_COMPILE_BLOCKED")
    if not original_match or not port_match or any(row["architecture"] != "x64" for row in objects):
        status = "SDK_X64_INPUT_OR_ARCHITECTURE_MISMATCH"
    warnings = sorted({line for row in executions for line in row["unique_warning_lines"]})
    errors = sorted({line for row in executions for line in row["unique_error_lines"]})
    numeric_warnings = [line for line in warnings if re.search(r"warning\s+C(?:4244|4267|4838)\b", line)]
    if numeric_warnings:
        status = "SDK_X64_NUMERIC_WARNING_GATE_FAILED"
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "status": status, "attempt": number,
              "phase_requested": args.phase, "compiler": compiler, "compiler_sha256": digest(Path(compiler)),
              "patch_specification": {"path": str(patches_path), "sha256": digest(patches_path)},
              "support_inputs": support_inputs,
              "numeric_warning_gate": {"level": "/W3", "codes": ["C4244", "C4267", "C4838"],
                                       "passed": not numeric_warnings, "remaining_lines": numeric_warnings},
              "builder": {"path": str(Path(__file__).resolve()), "sha256": digest(Path(__file__))},
              "manifest": {"path": str(evidence / "port_manifest.json"), "sha256": digest(evidence / "port_manifest.json")},
              "original_files_unchanged": original_match, "generated_port_inputs_unchanged": port_match,
              "port_files": len(manifest), "modified_files": sum(bool(row["patch_ids"]) for row in manifest),
              "translation_units_expected": len(units), "objects": objects, "executions": executions,
              "unique_warning_lines": warnings, "unique_error_lines": errors,
              "warning_code_counts": dict(Counter(re.search(r"warning\s+([A-Z]+\d+)", line).group(1) for line in warnings)),
              "x64_gamecore_linked": False, "game_launched": False, "runtime_verified": False, "deployed": False,
              "scope": "COMPILE_ONLY_NOT_LINKED_OR_EXECUTED"}
    save(attempt / "build_result.json", result)
    save(evidence / "build_result.json", result)
    # Preserve the exact patch plan and file mapping for each diagnostic attempt.
    (attempt / patches_path.name).write_bytes(patches_path.read_bytes())
    save(attempt / "port_manifest.json", manifest)
    print(json.dumps({"status": status, "attempt": number, "object_files": len(objects),
                      "expected": len(units), "warning_codes": result["warning_code_counts"], "error_lines": errors[:14]}, ensure_ascii=False))
    if status not in {"SDK_X64_ALL_OBJECTS_COMPILED", "SDK_X64_PCH_COMPILED"}:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
