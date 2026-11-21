"""Read-only Civ V engine inventory. Writes reports only inside this project.

Does not load game DLLs, launch Civ V, compile SDK sources, or alter game files.
PE observations and dumpbin output describe files on disk, not loaded modules.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import struct
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
import xml.etree.ElementTree as ET


PROJECT = Path(__file__).resolve().parents[1]
MACHINES = {0x014C: "x86", 0x8664: "x64", 0xAA64: "arm64"}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp949", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            pass
    raise ValueError(f"Unsupported text encoding: {path}")


def pe_header(path: Path) -> dict:
    with path.open("rb") as stream:
        dos = stream.read(64)
        if len(dos) != 64 or dos[:2] != b"MZ":
            raise ValueError(f"Missing DOS header: {path}")
        pe_offset = struct.unpack_from("<I", dos, 0x3C)[0]
        stream.seek(pe_offset)
        header = stream.read(26)
    if len(header) != 26 or header[:4] != b"PE\0\0":
        raise ValueError(f"Missing PE header: {path}")
    machine, sections, _, _, _, optional_size, flags = struct.unpack_from(
        "<HHIIIHH", header, 4
    )
    magic = struct.unpack_from("<H", header, 24)[0]
    if optional_size < 2 or magic not in (0x10B, 0x20B):
        raise ValueError(f"Unsupported optional header: {path}")
    return {
        "architecture": MACHINES.get(machine, f"unknown_0x{machine:04x}"),
        "machine_hex": f"0x{machine:04x}",
        "pe_format": {0x10B: "PE32", 0x20B: "PE32+"}[magic],
        "large_address_aware": bool(flags & 0x20),
        "is_dll": bool(flags & 0x2000),
        "section_count": sections,
    }


def dump(tool: Path, option: str, target: Path) -> str:
    result = subprocess.run(
        [str(tool), "/NOLOGO", option, str(target)],
        capture_output=True,
        timeout=60,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    if result.returncode:
        raise RuntimeError(f"dumpbin failed ({result.returncode}): {target}")
    return result.stdout.decode("utf-8", errors="replace").replace("\r\n", "\n")


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", type=Path, required=True)
    parser.add_argument("--sdk", type=Path, required=True, help="CvGameCoreSource directory")
    parser.add_argument("--mods", type=Path, required=True)
    parser.add_argument("--dumpbin", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=PROJECT / "evidence" / "2026-09-22")
    args = parser.parse_args()
    output = args.out.resolve()
    if not output.is_relative_to(PROJECT) or output == PROJECT:
        parser.error("Output must be a child directory of this independent project")
    for source in (args.game, args.sdk, args.mods):
        if not source.is_dir():
            parser.error(f"Input directory missing: {source}")
        if output.is_relative_to(source.resolve()) or source.resolve().is_relative_to(output):
            parser.error("Input and output directories must not overlap")
    if not args.dumpbin.is_file():
        parser.error("dumpbin executable missing")
    output.mkdir(parents=True, exist_ok=True)

    observed: dict[Path, str] = {}

    def remember(path: Path) -> str:
        path = path.resolve()
        if path not in observed:
            observed[path] = digest(path)
        return observed[path]

    binaries: dict[Path, str] = {
        path: "game_root"
        for path in args.game.iterdir()
        if path.is_file() and path.suffix.lower() in (".exe", ".dll")
    }
    for path in (args.game / "Assets" / "DLC").rglob("CvGameCore*.dll"):
        binaries[path] = "game_dlc"
    providers = []
    for mod_dir in sorted(args.mods.iterdir()):
        if not mod_dir.is_dir():
            continue
        dlls = list(mod_dir.rglob("CvGameCore*.dll"))
        if not dlls:
            continue
        manifests = []
        for path in sorted(mod_dir.glob("*.modinfo")):
            remember(path)
            root = ET.parse(path).getroot()
            manifests.append({
                "path": str(path), "id": root.get("id"), "version": root.get("version"),
                "name": root.findtext("./Properties/Name"),
                "set_dll_paths": [node.text for node in root.findall(".//SetDllPath")],
                "dll_file_entries": [
                    {"path": node.text, **node.attrib}
                    for node in root.findall("./Files/File")
                    if "cvgamecore" in (node.text or "").lower()
                    and (node.text or "").lower().endswith(".dll")
                ],
            })
        providers.append({
            "directory": str(mod_dir), "manifests": manifests,
            "dlls": [str(path) for path in sorted(dlls)],
            "enabled_or_loaded": "not_observed",
        })
        for path in dlls:
            binaries[path] = "installed_mod_file"

    binary_rows = []
    for path, origin in sorted(binaries.items()):
        binary_rows.append({
            "path": str(path), "origin": origin, "bytes": path.stat().st_size,
            "sha256": remember(path), **pe_header(path),
        })

    sdk_modules = []
    engine_calls = []
    for module in sorted(args.sdk.iterdir()):
        if not module.is_dir():
            continue
        counts = Counter()
        for path in sorted(module.rglob("*")):
            if not path.is_file():
                continue
            counts[path.suffix.lower()] += 1
            # Inventory every SDK file, including binary-only prerequisites.
            remember(path)
            if module.name == "CvGameCoreDLL_Expansion2" and path.suffix.lower() in (".cpp", ".h"):
                for line_number, line in enumerate(read_text(path).splitlines(), 1):
                    for match in re.finditer(r"\bgDLL\s*->\s*(\w+)\s*\(", line):
                        engine_calls.append({
                            "method": match.group(1), "file": str(path.relative_to(args.sdk)),
                            "line": line_number, "evidence_kind": "lexical_match_including_comments",
                        })
        sdk_modules.append({"module": module.name, "extensions": dict(sorted(counts.items()))})
    for path in sorted(args.sdk.iterdir()):
        if path.is_file():
            remember(path)

    projects = []
    for path in sorted(args.sdk.rglob("*.vcxproj")):
        root = ET.parse(path).getroot()
        settings = defaultdict(set)
        for node in root.iter():
            tag = node.tag.rsplit("}", 1)[-1]
            if tag in {"Platform", "PlatformToolset", "AdditionalDependencies", "TargetMachine", "ConfigurationType"}:
                if node.text and node.text.strip():
                    settings[tag].add(node.text.strip())
        projects.append({"path": str(path.relative_to(args.sdk)), "settings": {k: sorted(v) for k, v in settings.items()}})

    library_rows = []
    for path in sorted(args.sdk.rglob("*.lib")):
        headers = dump(args.dumpbin, "/HEADERS", path)
        machine_lines = Counter(line.strip() for line in headers.splitlines() if re.search(r"\bmachine\b", line, re.I))
        machine_matches = re.findall(
            r"(?im)^\s*([0-9a-f]+)\s+machine\b|^\s*Machine\s*:\s*([0-9a-f]+)\b", headers
        )
        machine_values = [int(first or second, 16) for first, second in machine_matches]
        machines = sorted({MACHINES.get(value, f"unknown_0x{value:04x}") for value in machine_values})
        if not machines:
            raise ValueError(f"No library machine evidence: {path}")
        library_rows.append({
            "path": str(path), "sha256": remember(path), "architectures_observed": ",".join(machines),
            "machine_header_observations": sum(machine_lines.values()), "machine_lines": dict(machine_lines),
        })

    dependency_reports = []
    for name, path in (
        ("dx11", args.game / "CivilizationV_DX11.exe"),
        ("bnw_core", args.game / "Assets" / "DLC" / "Expansion2" / "CvGameCore_Expansion2.dll"),
    ):
        contents = dump(args.dumpbin, "/DEPENDENTS", path)
        (output / f"{name}_dependents.txt").write_text(contents, encoding="utf-8")
        dependency_reports.append({
            "path": str(path), "declared_dependencies": sorted(set(
                line.strip() for line in contents.splitlines() if re.fullmatch(r"\s+[^\\/:]+\.dll\s*", line, re.I)
            )), "scope": "static_normal_and_delay_imports_reported_by_dumpbin_not_complete_runtime_graph",
        })
    dx11_headers = dump(args.dumpbin, "/HEADERS", args.game / "CivilizationV_DX11.exe")
    (output / "dx11_headers.txt").write_text(dx11_headers, encoding="utf-8")
    unchanged = all(digest(path) == before for path, before in observed.items())
    baseline = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "static_local_file_inventory_only",
        "game_root": str(args.game), "sdk_source_root": str(args.sdk), "mods_root": str(args.mods),
        "binaries": binary_rows, "sdk_modules": sdk_modules, "sdk_projects": projects,
        "sdk_libraries": library_rows, "gamecore_file_providers": providers,
        "dependency_reports": dependency_reports,
        "engine_call_lexical_matches": len(engine_calls),
        "engine_call_distinct_names": len({row["method"] for row in engine_calls}),
        "input_files_hashed": len(observed), "input_hashes_unchanged_after_collection": unchanged,
        "game_launched": False, "game_files_modified_by_collector": False,
        "runtime_verified": False, "performance_measured": False, "x64_engine_built": False,
        "limitations": [
            "Installed files do not establish which mods or DLLs are enabled or loaded.",
            "gDLL census is lexical, includes possible comments, and misses aliases and indirect calls.",
            "Source inventory is limited to the specified installed SDK; it is not a whole-PC search.",
            "Library machine observations do not prove source availability or x64 replacement feasibility.",
            "Matching hashes verify only the observed input files over this collection interval.",
        ],
    }
    (output / "baseline.json").write_text(json.dumps(baseline, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_csv(output / "binary_inventory.csv", binary_rows, ["path", "origin", "architecture", "machine_hex", "pe_format", "large_address_aware", "bytes", "sha256"])
    write_csv(output / "sdk_libraries.csv", library_rows, ["path", "architectures_observed", "machine_header_observations", "sha256"])
    write_csv(output / "engine_host_calls.csv", engine_calls, ["method", "file", "line", "evidence_kind"])
    grouped_calls = defaultdict(list)
    for row in engine_calls:
        grouped_calls[row["method"]].append(row)
    service_rows = [{
        "method": name, "lexical_occurrences": len(rows),
        "first_file": rows[0]["file"], "first_line": rows[0]["line"],
        "implementation_status": "NOT_IMPLEMENTED",
        "contract_status": "REQUIRES_SIGNATURE_CALLSITE_OWNERSHIP_AND_THREAD_REVIEW",
    } for name, rows in sorted(grouped_calls.items())]
    write_csv(output / "engine_services.csv", service_rows, [
        "method", "lexical_occurrences", "first_file", "first_line", "implementation_status", "contract_status",
    ])
    write_csv(output / "input_sha256.csv", [{"path": str(p), "sha256": h} for p, h in sorted(observed.items())], ["path", "sha256"])
    print(json.dumps({
        "report": str(output / "baseline.json"), "binaries": len(binary_rows),
        "sdk_libraries": len(library_rows), "gamecore_provider_directories": len(providers),
        "engine_call_lexical_matches": len(engine_calls), "engine_call_distinct_names": baseline["engine_call_distinct_names"],
        "input_files_hashed": len(observed), "input_hashes_unchanged": unchanged,
        "runtime_verified": False,
    }, ensure_ascii=False))
    if not unchanged:
        raise SystemExit("Observed input changed during collection; baseline requires review")


if __name__ == "__main__":
    main()
