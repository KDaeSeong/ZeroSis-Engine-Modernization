#!/usr/bin/env python3
"""Prepare bounded, provenance-tracked Civ V Warrior GR2 inspection evidence.

This is intentionally a preparation tool: it extracts only the model, FXSXML,
and idle animation records referenced by ART_DEF_UNIT__WARRIOR, then runs the
existing x86 GrannyBridge inspection modes. It never writes to the game tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
sys.path.insert(0, str(HERE))
from civ5_ui_assets import Fpk  # noqa: E402

DEFAULT_GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")
DEFAULT_BRIDGE = Path(r"C:\Users\home\OneDrive\Documents\Firaxis ModBuddy\ZeroSis' Daelaam Protoss\Tools\ArchonPipeline\GrannyBridge.exe")
DEFAULT_SDK = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V SDK\Nexus\x86")
EXPECTED = {
    "ART_DEF_UNIT_MEMBER_WARRIOR_V2": 3,
    "ART_DEF_UNIT_MEMBER_WARRIOR": 6,
    "ART_DEF_UNIT_MEMBER_WARRIOR_V4": 3,
}
MAX_XML_BYTES = 8 * 1024 * 1024
MAX_SELECTED_BYTES = 64 * 1024 * 1024
_helper_failure = None


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def text(element: ET.Element, name: str) -> str:
    child = element.find(name)
    require(child is not None and child.text is not None, f"Missing XML field {name}")
    return child.text.strip()


def read_xml(path: Path) -> tuple[ET.Element, dict]:
    raw = path.read_bytes()
    require(len(raw) <= MAX_XML_BYTES, f"XML exceeds bound: {path}")
    return ET.fromstring(raw), {"path": str(path), "bytes": len(raw), "sha256": sha256_bytes(raw)}


def resolve_pack_name(pack: Fpk, reference: str) -> str:
    """Resolve a Civ XML virtual path against the FPK's basename catalog."""
    normalized = reference.replace("\\", "/").strip("/").casefold()
    direct = [entry.name for entry in pack.entries.values()
              if entry.name.replace("\\", "/").casefold() == normalized]
    if direct:
        require(len(direct) == 1, f"Ambiguous exact FPK record: {reference}")
        return direct[0]
    basename = normalized.rsplit("/", 1)[-1]
    matches = [entry.name for entry in pack.entries.values()
               if entry.name.replace("\\", "/").casefold().rsplit("/", 1)[-1] == basename]
    require(len(matches) == 1, f"Expected one FPK basename for {reference}, found {matches}")
    return matches[0]


def run_helper(bridge: Path, sdk: Path, args: list[str], stdout_path: Path,
               stderr_path: Path, cwd: Path) -> dict:
    global _helper_failure
    if _helper_failure is not None:
        return {"argv": [str(bridge), *map(str, args)], "exit_code": None,
                "not_run": True, "reason": "Earlier helper failure: " + _helper_failure,
                "stdout": None, "stderr": None}
    if os.name == "nt":
        import ctypes
        # Inherited by child processes: avoid critical-error and crash dialogs.
        ctypes.windll.kernel32.SetErrorMode(0x8003)
    env = os.environ.copy()
    prior = env.get("PATH", "")
    env["PATH"] = str(sdk) + os.pathsep + prior
    command = [str(bridge), *map(str, args)]
    started = time.time()
    try:
        result = subprocess.run(command, cwd=str(cwd), env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=45, check=False,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired as error:
        _helper_failure = args[0] + " timed out"
        stdout_path.write_bytes(error.stdout or b"")
        stderr_path.write_bytes(error.stderr or b"")
        return {"argv": command, "exit_code": None, "timed_out": True,
                "elapsed_seconds": 45, "stdout": str(stdout_path), "stderr": str(stderr_path)}
    stdout_path.write_bytes(result.stdout)
    stderr_path.write_bytes(result.stderr)
    if result.returncode != 0:
        _helper_failure = args[0] + " exited with " + str(result.returncode)
    return {"argv": command, "exit_code": result.returncode,
            "timed_out": False,
            "elapsed_seconds": round(time.time() - started, 3),
            "stdout": str(stdout_path), "stderr": str(stderr_path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--game-root", type=Path, default=DEFAULT_GAME)
    parser.add_argument("--bridge", type=Path, default=DEFAULT_BRIDGE)
    parser.add_argument("--sdk-root", type=Path, default=DEFAULT_SDK)
    parser.add_argument("--run-id", help="UTC run ID; defaults to current UTC timestamp")
    args = parser.parse_args()

    game = args.game_root.resolve(strict=True)
    bridge = args.bridge.resolve(strict=True)
    sdk = args.sdk_root.resolve(strict=True)
    run_id = args.run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    require(re.fullmatch(r"\d{8}T\d{6}Z(?:_[A-Za-z0-9-]{1,32})?", run_id) is not None,
            "run-id must be a UTC timestamp with optional safe suffix")
    out_root = (PROJECT / "Build" / "UnitModels" / run_id).resolve()
    evidence_dir = (PROJECT / "evidence" / "unit_models").resolve()
    require(out_root.is_relative_to((PROJECT / "Build" / "UnitModels").resolve()), "Unsafe output path")
    require(evidence_dir.is_relative_to(PROJECT.resolve()), "Unsafe evidence path")
    require(not out_root.exists(), f"Run output already exists: {out_root}")
    out_root.mkdir(parents=True)
    evidence_dir.mkdir(parents=True, exist_ok=True)

    fpk_path = game / "Resource" / "Common" / "UnitModels.fpk"
    unit_art_path = game / "Assets" / "Units" / "Civ5ArtDefines_Units.xml"
    member_art_path = game / "Assets" / "Units" / "Civ5ArtDefines_UnitMembers.xml"
    dll_names = ("Firaxis.Framework.dll", "Firaxis.Framework.Granny.dll",
                 "Firaxis.Framework.FirePlace.dll", "Firaxis.Framework.Granny.ImplWin32.dll",
                 "GrannyExporterFBXWin32.dll")
    provenance_paths = [fpk_path, unit_art_path, member_art_path, bridge,
                        bridge.with_suffix(".cs"), Path(str(bridge) + ".config")]
    provenance_paths += [sdk / name for name in dll_names if (sdk / name).is_file()]
    before = {str(path): sha256_file(path) for path in provenance_paths if path.is_file()}
    require(len(before) == len([path for path in provenance_paths if path.is_file()]), "Cannot hash source inputs")
    require(bridge.is_file() and fpk_path.is_file(), "Missing bridge or UnitModels.fpk")

    unit_root, unit_xml = read_xml(unit_art_path)
    unit_matches = [node for node in unit_root.findall(".//UnitArtInfo")
                    if text(node, "Type") == "ART_DEF_UNIT__WARRIOR"]
    require(len(unit_matches) == 1, "Expected exactly one ART_DEF_UNIT__WARRIOR")
    members = {}
    for node in unit_matches[0].findall("UnitMemberArt"):
        member = text(node, "MemberType")
        require(member not in members, f"Duplicate Warrior member {member}")
        members[member] = int(text(node, "MemberCount"))
    require(members == EXPECTED, f"Unexpected Warrior member/count set: {members}")

    member_root, member_xml = read_xml(member_art_path)
    member_defs = {}
    for node in member_root.findall(".//UnitMemberArtInfo"):
        key_node = node.find("Type")
        if key_node is not None and key_node.text and key_node.text.strip() in EXPECTED:
            key = key_node.text.strip()
            require(key not in member_defs, f"Duplicate unit member definition {key}")
            granny = text(node, "Granny").replace("\\", "/")
            require(not granny.startswith("/") and ".." not in granny.split("/"), "Unsafe Granny path")
            member_defs[key] = granny
    require(set(member_defs) == set(EXPECTED), "Missing Warrior unit member definitions")

    pack = Fpk(fpk_path)
    outputs = []
    helper_calls = []
    failures = []
    for member in EXPECTED:
        fxs_name = member_defs[member]
        fxs_record_name = resolve_pack_name(pack, fxs_name)
        fxs_data, fxs_origin = pack.read(fxs_record_name)
        require(len(fxs_data) <= MAX_XML_BYTES, "Selected FXSXML exceeds XML bound")
        fxs = ET.fromstring(fxs_data)
        models = [n.attrib["file"].strip().replace("\\", "/")
                  for n in fxs.findall(".//Mesh") if n.attrib.get("file", "").strip()]
        anim_nodes = [n for n in fxs.findall(".//Animation") if n.attrib.get("file", "").strip()]
        require(models, f"No model reference in {fxs_name}")
        # Use exact referenced model(s); select the actual idle animation by its source tag.
        idle_refs = []
        for node in anim_nodes:
            ref = node.attrib["file"].strip().replace("\\", "/")
            if Path(ref).name.casefold() == "warrior_idlea.gr2":
                idle_refs.append(ref)
        require(len(idle_refs) == 1, f"Expected exactly one base Warrior_IdleA animation in {fxs_name}: {idle_refs}")
        require(len(set(models)) == len(models), f"Duplicate model references in {fxs_name}")
        require(len(set(idle_refs)) == len(idle_refs), f"Duplicate idle references in {fxs_name}")

        member_dir = out_root / member
        member_dir.mkdir()
        fxs_out = member_dir / Path(fxs_name).name
        fxs_out.write_bytes(fxs_data)
        item = {"member_type": member, "member_count": EXPECTED[member],
                "fxsxml": {**fxs_origin, "extracted_path": str(fxs_out),
                            "extracted_sha256": sha256_bytes(fxs_data)}, "models": [], "idle": []}
        for kind, refs in (("model", models), ("idle", idle_refs)):
            for index, entry_name in enumerate(refs):
                record_name = resolve_pack_name(pack, entry_name)
                data, origin = pack.read(record_name)
                require(len(data) <= MAX_SELECTED_BYTES, f"Selected GR2 exceeds bound: {entry_name}")
                payload = member_dir / f"{kind}-{index}-{Path(entry_name).name}"
                payload.write_bytes(data)
                record = {**origin, "extracted_path": str(payload),
                          "extracted_sha256": sha256_bytes(data), "bytes": len(data)}
                if kind == "model":
                    inspect = member_dir / f"model-{index}.json"
                    call = run_helper(bridge, sdk, ["inspect", str(payload), str(inspect)],
                                      member_dir / f"model-{index}-inspect.stdout.txt",
                                      member_dir / f"model-{index}-inspect.stderr.txt", member_dir)
                    materials = run_helper(bridge, sdk, ["materials", str(payload)],
                                           member_dir / f"model-{index}-materials.stdout.txt",
                                           member_dir / f"model-{index}-materials.stderr.txt", member_dir)
                    record.update({"helper": {"inspect": call, "materials": materials},
                                   "materials_log": materials["stdout"]})
                    if call["exit_code"] == 0 and not call.get("timed_out"):
                        require(inspect.is_file() and inspect.stat().st_size <= 64 * 1024 * 1024,
                                "Missing or oversized inspect JSON")
                        report = json.loads(inspect.read_text(encoding="utf-8"))
                        require(report.get("source_sha256") == record["extracted_sha256"],
                                "Inspect report source hash mismatch")
                        record.update({"inspect_json": str(inspect), "inspect_sha256": sha256_file(inspect),
                                       "models": len(report.get("models", [])),
                                       "meshes": len(report.get("meshes", [])),
                                       "material_texture_paths": report.get("material_texture_paths", [])})
                    else:
                        failures.append({"member": member, "operation": "inspect",
                                         "exit_code": call["exit_code"], "stderr": call["stderr"]})
                    if materials["exit_code"] != 0 or materials.get("timed_out"):
                        failures.append({"member": member, "operation": "materials",
                                         "exit_code": materials["exit_code"], "stderr": materials["stderr"]})
                    helper_calls.extend([call, materials])
                    item["models"].append(record)
                else:
                    require(Path(entry_name).suffix.casefold() == ".gr2", "Idle reference is not a GR2")
                    idle_json = member_dir / f"idle-{index}-t0.json"
                    call = run_helper(bridge, sdk, ["densechunk_2_0_1", str(item["models"][0]["extracted_path"]),
                                                    str(payload), str(idle_json)],
                                      member_dir / f"idle-{index}-sample.stdout.txt",
                                      member_dir / f"idle-{index}-sample.stderr.txt", member_dir)
                    if call["exit_code"] == 0 and not call.get("timed_out"):
                        require(idle_json.is_file() and idle_json.stat().st_size <= 64 * 1024 * 1024,
                                "Missing or oversized t=0 pose JSON")
                        sample = json.loads(idle_json.read_text(encoding="utf-8"))
                        require(sample.get("model_sha256") == item["models"][0]["extracted_sha256"] and
                                sample.get("animation_sha256") == record["extracted_sha256"],
                                "Pose sample does not match selected model/idle bytes")
                        require(len(sample.get("frames", [])) == 1 and sample["frames"][0].get("time") == 0,
                                "Expected one t=0 pose frame")
                        record.update({"sample_json": str(idle_json), "sample_sha256": sha256_file(idle_json),
                                       "sampled_bones": len(sample.get("bones", [])), "helper": call})
                    else:
                        failures.append({"member": member, "operation": "sample_t0",
                                         "exit_code": call["exit_code"], "stderr": call["stderr"]})
                    helper_calls.append(call)
                    item["idle"].append(record)
        outputs.append(item)

    after = {str(path): sha256_file(path) for path in provenance_paths if path.is_file()}
    require(before == after, "Source input/helper/SDK DLL hashes changed during preparation")
    report = {"schema": 1, "run_id": run_id,
              "status": "PASS_PREPARATION_ONLY" if not failures else "FAILED_PARTIAL",
              "scope": "ART_DEF_UNIT__WARRIOR referenced models and idle t=0 inspection only; no binary packaging",
              "game_root": str(game), "source_xml": {"unit_art": unit_xml, "unit_members": member_xml},
              "selected_members": members, "member_sources": member_defs,
              "fpk_sha256": before[str(fpk_path)], "bridge": str(bridge), "sdk_root": str(sdk),
              "input_hashes_before": before, "input_hashes_after": after,
              "outputs": outputs, "helper_calls": helper_calls, "failures": failures,
              "limitations": ["No final binary packaging", "No runtime or visual equivalence claim",
                              "Idle samples exist only for outputs with a verified sample_json"]}
    report_path = evidence_dir / f"{run_id}.json"
    temp = report_path.with_suffix(".json.tmp")
    temp.write_text(json.dumps(report, indent=2), encoding="utf-8")
    temp.replace(report_path)
    print(json.dumps({"status": report["status"], "run_id": run_id,
                      "report": str(report_path), "output": str(out_root),
                      "members": len(outputs), "helper_calls": len(helper_calls)}, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"PREPARATION_FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        raise
