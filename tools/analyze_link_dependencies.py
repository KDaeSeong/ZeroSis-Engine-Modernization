"""Inventory reference COFF requirements and final link-map providers; no DLL loading."""
from __future__ import annotations

import argparse
from collections import defaultdict, Counter
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess

from collect_baseline import PROJECT, digest, dump, read_text, write_csv


SYMBOL = re.compile(r"^\s*[0-9A-F]+\s+([0-9A-F]+)\s+(UNDEF|ABS|SECT[0-9A-F]+)\s+.*?\b(External|WeakExternal)\s+\|\s+(.+)$")
MAP = re.compile(r"^\s*[0-9A-F]+:[0-9A-F]+\s+(.+?)\s+([0-9A-F]{8,16})\s+(.*?)\s*$", re.I)


def object_symbols(tool: Path, path: Path) -> dict:
    process = subprocess.run([str(tool), "/nologo", "/SYMBOLS", str(path)], capture_output=True,
                             timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
    if process.returncode:
        raise RuntimeError(f"dumpbin failed: {path}")
    defined, undefined, weak = set(), set(), set()
    entries = 0
    for line in process.stdout.decode("mbcs", errors="replace").splitlines():
        match = SYMBOL.match(line)
        if not match:
            continue
        entries += 1
        value, section, storage, displayed = match.groups()
        name = displayed.partition(" (")[0].rstrip()
        if storage == "WeakExternal":
            weak.add(name)
        elif section == "UNDEF" and int(value, 16) == 0:
            undefined.add(name)
        else:
            # Nonzero UNDEF is a COFF common definition, not an unresolved reference.
            defined.add(name)
    if entries == 0:
        raise RuntimeError(f"No external symbols parsed: {path}")
    return {"path": str(path), "sha256": digest(path), "defined": defined,
            "undefined": undefined, "weak": weak, "entries": entries,
            "dump_sha256": hashlib.sha256(process.stdout).hexdigest()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dumpbin", type=Path, required=True)
    args = parser.parse_args()
    evidence = PROJECT / "evidence/link_dependencies"
    evidence.mkdir(parents=True, exist_ok=True)
    build = PROJECT / "Build/SDK_Reference"
    build_report = json.loads((PROJECT / "evidence/sdk_reference/build_result.json").read_text(encoding="utf-8"))
    if build_report["status"] != "SDK_REFERENCE_BUILD_PASS":
        raise RuntimeError("Successful SDK reference build required")
    dll = Path(build_report["outputs"][0]["path"])
    if digest(dll) != build_report["outputs"][0]["sha256"]:
        raise RuntimeError("Reference DLL changed since build")
    objects = sorted((build / "obj").glob("*.obj"))
    if len(objects) != build_report["object_files"]:
        raise RuntimeError("Reference object set differs from build report")
    with ThreadPoolExecutor(max_workers=3) as executor:
        parsed = list(executor.map(lambda path: object_symbols(args.dumpbin, path), objects))
    all_defined = set().union(*(row["defined"] for row in parsed))
    consumers = defaultdict(set)
    for row in parsed:
        for name in row["undefined"] - all_defined:
            consumers[name].add(Path(row["path"]).name)
    providers = defaultdict(set)
    with (PROJECT / "evidence/m1/library_symbols.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            providers[row["symbol"]].add(row["library"])
    sdk_libraries = sorted({name for names in providers.values() for name in names})
    requirements = [{"symbol": symbol, "candidate_sdk_libraries": ";".join(sorted(providers[symbol])),
                     "consumer_count": len(users), "consumer_objects": ";".join(sorted(users)),
                     "classification": "SDK_LIBRARY_CANDIDATE" if providers[symbol] else "SYSTEM_CRT_OR_OTHER_REVIEW"}
                    for symbol, users in sorted(consumers.items())]
    link_map = build / "out/reference.map"
    map_rows, in_publics, unparsed_publics = [], False, []
    for line in read_text(link_map).splitlines():
        if "Publics by Value" in line:
            in_publics = True
            continue
        if "entry point at" in line or "Static symbols" in line:
            in_publics = False
        match = MAP.match(line) if in_publics else None
        if not match:
            if in_publics and re.match(r"\s*[0-9A-F]+:[0-9A-F]+\s", line, re.I):
                unparsed_publics.append(line)
            continue
        symbol, address, remaining = match.groups()
        owner = re.sub(r"^(?:[fi]\s+)+", "", remaining)
        library = owner.split(":", 1)[0] + ".lib" if ":" in owner else ""
        map_rows.append({"symbol": symbol, "address": address, "owner": owner, "library": library,
                         "sdk_library": library in sdk_libraries})
    if not map_rows or unparsed_publics:
        raise RuntimeError(f"Link-map parsing incomplete: {len(map_rows)} parsed, {len(unparsed_publics)} unparsed")
    library_rows = []
    for library in sdk_libraries:
        selected = [row for row in map_rows if row["library"] == library]
        library_rows.append({"library": library,
                             "direct_object_requirement_candidates": sum(library in providers[name] for name in consumers),
                             "final_map_public_entries": len(selected),
                             "final_map_owner_members": len({row["owner"] for row in selected})})
    for option, name in (("/IMPORTS", "reference_imports.txt"), ("/EXPORTS", "reference_exports.txt")):
        (evidence / name).write_text(dump(args.dumpbin, option, dll), encoding="utf-8")
    inputs = [{"path": row["path"], "sha256": row["sha256"]} for row in parsed]
    inputs += [{"path": str(path), "sha256": digest(path)}
               for path in (dll, link_map, PROJECT / "evidence/m1/library_symbols.csv")]
    warning_counts = Counter()
    for report_path in sorted((PROJECT / "evidence/sdk_reference/attempts").glob("*/build_result.json")):
        attempt = json.loads(report_path.read_text(encoding="utf-8"))
        # Count distinct diagnostic lines per attempt, not unique defects or source sites.
        for line in attempt["unique_warning_lines"]:
            match = re.search(r"\bwarning\s+(\w+)", line)
            if match:
                warning_counts[match[1]] += 1
    report = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "X86_REFERENCE_STATIC_LINK_REQUIREMENTS_NOT_X64_IMPLEMENTATION_OR_RUNTIME_CLOSURE",
        "object_files": len(parsed), "defined_external_names": len(all_defined),
        "unresolved_by_game_objects_unique_names": len(requirements),
        "direct_sdk_candidate_names": sum(bool(providers[name]) for name in consumers),
        "remaining_system_crt_or_other_names": sum(not providers[name] for name in consumers),
        "weak_external_names_pending": len(set().union(*(row["weak"] for row in parsed))),
        "map_public_entries": len(map_rows),
        "unparsed_map_public_lines": len(unparsed_publics),
        "map_sdk_public_entries": sum(row["sdk_library"] for row in map_rows),
        "libraries": library_rows, "recorded_build_warning_lines_by_code": dict(warning_counts),
        "inputs_unchanged": all(digest(Path(row["path"])) == row["sha256"] for row in inputs),
        "game_launched": False, "dll_loaded": False, "full_dependency_closure_verified": False,
        "limitations": ["All object undefined names overapproximate live requirements because linker can discard functions.",
                        "Candidate SDK providers are exact decorated-name matches, not semantic implementations.",
                        "Final map shows selected public symbols and providers for this one x86 configuration.",
                        "Weak externals, linker aliases, transitive references, dynamic loading and host callbacks need separate review.",
                        "Compiler C4819 warnings and absent library PDB warnings remain in the reference build history."]}
    write_csv(evidence / "object_requirements.csv", requirements, list(requirements[0]))
    write_csv(evidence / "final_map_publics.csv", map_rows, list(map_rows[0]))
    write_csv(evidence / "library_requirements.csv", library_rows, list(library_rows[0]))
    write_csv(evidence / "input_sha256.csv", inputs, ["path", "sha256"])
    object_rows = [{"path": row["path"], "sha256": row["sha256"], "dump_sha256": row["dump_sha256"],
                    "defined_names": len(row["defined"]), "undefined_names": len(row["undefined"]),
                    "weak_names": len(row["weak"]), "parsed_external_entries": row["entries"]} for row in parsed]
    write_csv(evidence / "object_summary.csv", object_rows, list(object_rows[0]))
    (evidence / "link_inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    if not report["inputs_unchanged"]:
        raise SystemExit("Inputs changed during link analysis")


if __name__ == "__main__":
    main()
