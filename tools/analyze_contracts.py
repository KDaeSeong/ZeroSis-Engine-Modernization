"""Extract SDK interface declarations, typed call candidates and library symbols.

This is a source census, not C++ type checking, runtime coverage or a complete ABI.
No game module is loaded. Original SDK files are read only.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from collect_baseline import PROJECT, digest, dump, read_text, write_csv


def mask_cpp(text: str) -> str:
    pattern = r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\''
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m[0]), text)


def closing_brace(text: str, start: int) -> int:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return index
    raise ValueError("Unbalanced class definition")


def family(name: str) -> str:
    if name.startswith("ICvEngineScriptSystem"):
        return "host_script"
    if name.startswith("ICvUserInterface") or name == "CvDLLInterfaceIFaceBase":
        return "host_ui"
    if name.startswith("ICvEngineUtility"):
        return "host_engine_utility"
    if name == "ICvUnknown":
        return "shared_lifetime"
    return "gamecore_exposed_interface"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--dumpbin", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=PROJECT / "evidence" / "m1")
    args = parser.parse_args()
    output = args.out.resolve()
    if not output.is_relative_to(PROJECT) or output == PROJECT:
        parser.error("Output must be inside the independent project")
    if output.is_relative_to(args.sdk.resolve()) or args.sdk.resolve().is_relative_to(output):
        parser.error("SDK and output cannot overlap")
    output.mkdir(parents=True, exist_ok=True)
    inputs = {}

    def source(path: Path) -> str:
        inputs[str(path)] = digest(path)
        return read_text(path)

    declarations = []
    class_bases = {}
    headers = [args.sdk / "CvGameCoreDLLUtil" / "include" / name for name in (
        "CvDllInterfaces.h", "CvDllInterfaces2.h", "ICvDLLUtility.h",
        "ICvDLLScriptSystem.h", "ICvDLLUserInterface.h", "ICvDLLDatabaseUtility.h",
    )]
    for path in headers:
        original = source(path)
        masked = mask_cpp(original)
        for match in re.finditer(r"\bclass\s+(\w+)\s*(?::\s*([^;{]+))?\s*\{", masked):
            class_name = match[1]
            bases = re.findall(r"(?:public|protected|private)\s+(\w+)", match[2] or "")
            class_bases[class_name] = bases
            start = match.end()
            end = closing_brace(masked, start - 1)
            for declaration in re.finditer(r"\bvirtual\s+([^;{}]+?)\s*=\s*0\s*;", masked[start:end]):
                names = re.findall(r"\b([A-Za-z_]\w*)\s*\(", declaration[1])
                names = [name for name in names if not name.startswith("_") and name not in {"DECLSPEC_DEPRECATED"}]
                if not names:
                    raise ValueError(f"Cannot identify virtual method in {path}: {declaration[0]}")
                method = names[0]
                absolute_start = start + declaration.start()
                signature = " ".join(original[absolute_start:start + declaration.end()].split())
                key = f"{class_name}::{signature}"
                declarations.append({
                    "declaration_id": hashlib.sha256(key.encode()).hexdigest()[:16],
                    "interface": class_name, "bases": ",".join(bases), "method": method,
                    "signature": signature, "file": str(path.relative_to(args.sdk)),
                    "line": original.count("\n", 0, absolute_start) + 1,
                    "family": family(class_name), "implementation_status": "NOT_IMPLEMENTED",
                    "worker_call_policy": "FORBIDDEN_UNTIL_INDIVIDUAL_CONTRACT_REVIEW",
                })

    def ancestors(name: str, seen=None) -> set[str]:
        seen = set() if seen is None else seen
        if name in seen:
            return seen
        seen.add(name)
        for base in class_bases.get(name, []):
            ancestors(base, seen)
        return seen

    call_rows = []
    ambiguous_aliases = []
    bnw = args.sdk / "CvGameCoreDLL_Expansion2"
    for path in sorted(bnw.rglob("*")):
        if path.suffix.lower() not in {".cpp", ".h"}:
            continue
        text = mask_cpp(source(path))
        patterns = [
            (r"\bgDLL\s*->\s*(\w+)\s*\(", "ICvEngineUtility4", "gDLL_macro"),
            (r"\bDLLUI\s*->\s*(\w+)\s*\(", "ICvUserInterface2", "DLLUI_macro"),
            (r"\bGC\s*\.\s*GetEngineUserInterface\s*\(\s*\)\s*->\s*(\w+)\s*\(", "ICvUserInterface2", "direct_ui_getter"),
            (r"\bgDLL\s*->\s*getInterfaceIFace\s*\(\s*\)\s*->\s*(\w+)\s*\(", "CvDLLInterfaceIFaceBase", "deprecated_ui_getter"),
        ]
        aliases = defaultdict(set)
        for match in re.finditer(r"\b(ICvEngineScriptSystem(?:Args)?1|ICvUserInterface[12]|ICvEngineUtility[1-4])\s*\*\s*(\w+)", text):
            aliases[match[2]].add(match[1])
        for alias, types in aliases.items():
            if len(types) == 1:
                patterns.append((rf"\b{re.escape(alias)}\s*->\s*(\w+)\s*\(", next(iter(types)), "file_scoped_typed_alias_candidate"))
            else:
                ambiguous_aliases.append({"file": str(path.relative_to(args.sdk)), "alias": alias, "types": sorted(types)})
        for pattern, interface, evidence in patterns:
            for match in re.finditer(pattern, text):
                method = match[1]
                candidates = [row for row in declarations if row["interface"] in ancestors(interface) and row["method"] == method]
                call_rows.append({
                    "interface": interface, "method": method, "file": str(path.relative_to(args.sdk)),
                    "line": text.count("\n", 0, match.start()) + 1,
                    "declaration_ids": ",".join(row["declaration_id"] for row in candidates),
                    "candidate_count": len(candidates),
                    "resolution": "NAME_MATCH" if len(candidates) == 1 else "OVERLOAD_REVIEW" if candidates else "UNMAPPED",
                    "evidence": evidence,
                })

    libraries = []
    symbols = []
    raw_dir = output / "linker_members"
    raw_dir.mkdir(exist_ok=True)
    for path in sorted(args.sdk.rglob("*.lib")):
        inputs[str(path)] = digest(path)
        contents = dump(args.dumpbin, "/LINKERMEMBER:2", path)
        (raw_dir / f"{path.stem}.txt").write_text(contents, encoding="utf-8")
        marker = re.search(r"(\d+) public symbols", contents)
        if marker is None:
            raise ValueError(f"No public symbol table: {path}")
        expected = int(marker[1])
        symbol_block = re.split(r"(?m)^\s*(?:Archive member name at|Summary)\b", contents[marker.end():], maxsplit=1)[0]
        extracted = [(member, symbol.rstrip()) for member, symbol in re.findall(
            r"(?m)^[ \t]+([0-9A-Fa-f]+)[ \t]+(\S[^\r\n]*)$", symbol_block
        )]
        if len(extracted) != expected:
            raise ValueError(f"Symbol extraction mismatch: {path}: {len(extracted)} != {expected}")
        for member, symbol in extracted:
            symbols.append({"library": path.name, "member_index_hex": member, "symbol": symbol})
        libraries.append({
            "library": path.name, "path": str(path), "sha256": inputs[str(path)],
            "public_symbol_entries": expected, "unique_symbol_names": len({symbol for _, symbol in extracted}),
            "import_pointer_entries": sum(symbol.startswith("__imp_") for _, symbol in extracted),
            "status": "X64_REPLACEMENT_PENDING",
        })

    unmatched = [row for row in call_rows if row["resolution"] == "UNMAPPED"]
    report = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "STATIC_INTERFACE_AND_SYMBOL_CENSUS_NOT_FULL_ABI_OR_SEMANTIC_REVIEW",
        "interface_classes": len(class_bases), "pure_virtual_declarations": len(declarations),
        "declarations_by_family": dict(Counter(row["family"] for row in declarations)),
        "typed_call_candidates": len(call_rows), "resolution_counts": dict(Counter(row["resolution"] for row in call_rows)),
        "unique_call_names_by_receiver": len({(row["interface"], row["method"]) for row in call_rows}),
        "ambiguous_aliases": ambiguous_aliases, "unmapped_candidates": unmatched,
        "libraries": libraries, "library_symbol_entries": len(symbols),
        "input_files": len(inputs), "inputs_unchanged": all(digest(Path(path)) == value for path, value in inputs.items()),
        "full_contract_gate_complete": False, "game_launched": False,
        "limitations": [
            "Comment and string masking is not a compiler preprocessor or C++ parser.",
            "Conditional compilation branches and file-scoped alias shadowing require compiler/callsite review.",
            "Matching names do not resolve overloads, ownership, execution paths or thread safety.",
            "Inherited methods may yield multiple candidates; vtable layout is not inferred.",
            "Symbol counts include templates and support symbols, not only functions required by BNW.",
            "Whole-program call closure and all seven x64 dependency replacements remain incomplete.",
        ],
    }
    write_csv(output / "interface_declarations.csv", declarations, list(declarations[0]))
    write_csv(output / "typed_call_candidates.csv", call_rows, list(call_rows[0]))
    write_csv(output / "library_symbols.csv", symbols, list(symbols[0]))
    write_csv(output / "library_summary.csv", libraries, list(libraries[0]))
    write_csv(output / "input_sha256.csv", [{"path": path, "sha256": value} for path, value in sorted(inputs.items())], ["path", "sha256"])
    (output / "contract_inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in report.items() if key not in {"libraries", "limitations", "unmapped_candidates", "ambiguous_aliases"}}, ensure_ascii=False))
    if not report["inputs_unchanged"]:
        raise SystemExit("Source changed during analysis")


if __name__ == "__main__":
    main()
