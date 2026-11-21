"""Build the pinned ICU 4.4.2 common/i18n/stub-data sources as AMD64 /MD libraries.

Original files remain read-only inputs. This does not execute the game or use
stub data as language data: the consumer must provide the original ICU44 data.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re
import struct

from collect_baseline import PROJECT, digest
from fetch_icu44_source import ARCHIVE_SHA256, COMMIT
from native_build import environment_for, run


def artifact(path):
    return {"path": str(path), "sha256": digest(path)}


def source_units(root, component):
    if component == "stubdata":
        return [root / "source/stubdata/stubdata.c"]
    makefile = (root / "source" / component / "Makefile.in").read_text(encoding="utf-8")
    match = re.search(r"^OBJECTS\s*=\s*((?:[^\n]*\\\n)*[^\n]*)", makefile, re.M)
    if not match:
        raise RuntimeError("ICU translation unit list is absent: " + component)
    names = match[1].replace("\\\n", " ").split()
    if not names or len(names) != len(set(names)) or any(not name.endswith(".o") for name in names):
        raise RuntimeError("Unexpected ICU translation unit list")
    units = []
    for name in names:
        candidates = [root / "source" / component / (name[:-2] + suffix) for suffix in (".c", ".cpp")]
        candidates = [path for path in candidates if path.is_file()]
        if len(candidates) != 1:
            raise RuntimeError("Ambiguous ICU translation unit: " + name)
        units += candidates
    return units


def verify_source():
    vendor = PROJECT / "Source/ThirdParty/ICU44"
    root = vendor / "original"
    receipt_path = vendor / "source_receipt.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt["commit"] != COMMIT or digest(Path(receipt["archive"]["path"])) != ARCHIVE_SHA256:
        raise RuntimeError("ICU source archive identity differs")
    manifest_path = vendor / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if len(manifest) != 642:
        raise RuntimeError("ICU source manifest is incomplete")
    for item in manifest:
        path = (root / item["relative"]).resolve()
        if not path.is_relative_to(root.resolve()) or str(path) != item["path"] or digest(path) != item["sha256"]:
            raise RuntimeError("ICU original differs: " + item["relative"])
    return root, [artifact(receipt_path), artifact(manifest_path)], manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vs", type=Path, default=Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"))
    args = parser.parse_args()
    root, seals, manifest = verify_source()
    out = PROJECT / "Build/ICU44/x64"
    evidence = PROJECT / "evidence/icu44"
    out.mkdir(parents=True, exist_ok=True)
    evidence.mkdir(parents=True, exist_ok=True)
    environment, compiler = environment_for(args.vs, "x64", out)
    report = {"status": "ICU44_BUILD_IN_PROGRESS", "archive_sha256": ARCHIVE_SHA256,
              "commit": COMMIT, "source_seals": seals, "original_file_count": len(manifest),
              "builder": artifact(Path(__file__).resolve()), "compiler": artifact(Path(compiler)),
              "components": [], "game_launched": False, "gamecore_loaded": False,
              "scope": "Static libraries only; real ICU44 data must be supplied by the consumer"}
    for component, define in (("common", "U_COMMON_IMPLEMENTATION"), ("i18n", "U_I18N_IMPLEMENTATION"), ("stubdata", "U_DATA_IMPLEMENTATION")):
        directory = out / component
        directory.mkdir(exist_ok=True)
        sources = source_units(root, component)
        flags = ["/nologo", "/c", "/MP4", "/O2", "/MD", "/EHsc", "/W3", "/utf-8", "/Gy", "/Gw", "/FIstdint.h",
                 "/DNDEBUG", "/DWIN32", "/D_WINDOWS", "/DU_STATIC_IMPLEMENTATION", "/DU_HAVE_INTTYPES_H=1",
                 "/D_CRT_SECURE_NO_WARNINGS", "/D" + define,
                 f'/I"{root / "source/common"}"', f'/I"{root / "source/i18n"}"',
                 f'/Fo"{directory}\\\\"']
        response = directory / "compile.rsp"
        response.write_text("\n".join(flags + [f'"{path}"' for path in sources]) + "\n", encoding="utf-8")
        print(f"Compiling ICU {component}: {len(sources)} units", flush=True)
        result = run([compiler, "@" + str(response)], cwd=directory, env=environment, timeout=300)
        output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
        log = evidence / (component + "_build.log")
        log.write_text(output, encoding="utf-8")
        warnings = Counter(re.findall(r"(?:warning|경고)\s+(C\d+)", output, re.I))
        entry = {"name": component, "sources": [artifact(path) for path in sources], "flags": flags,
                 "response": artifact(response), "log": artifact(log), "warning_code_occurrences": dict(warnings),
                 "returncode": result.returncode}
        report["components"].append(entry)
        if result.returncode:
            report["status"] = "ICU44_BUILD_FAILED"
            (evidence / "build_result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            errors = [line for line in output.splitlines() if re.search(r"(?:error|오류)\s+[A-Z]+\d+", line)]
            raise RuntimeError("ICU compilation failed: " + str(log) + "\n" + "\n".join(errors[:20]))
        objects = [directory / (source.stem + ".obj") for source in sources]
        for obj in objects:
            with obj.open("rb") as stream:
                if struct.unpack("<H", stream.read(2))[0] != 0x8664:
                    raise RuntimeError("ICU object is not AMD64: " + str(obj))
        library = out / ("icu44_" + component + ".lib")
        librarian = Path(compiler).with_name("lib.exe")
        lib_response = directory / "library.rsp"
        lib_response.write_text("\n".join(["/nologo", "/Brepro", "/MACHINE:X64", f'/OUT:"{library}"'] +
                                         [f'"{obj}"' for obj in objects]) + "\n", encoding="utf-8")
        result = run([librarian, "@" + str(lib_response)], cwd=directory, env=environment)
        lib_log = evidence / (component + "_library.log")
        lib_log.write_bytes(result.stdout + result.stderr)
        if result.returncode or re.search(rb"(?:warning|error)\s+LNK\d+", result.stdout + result.stderr, re.I):
            raise RuntimeError("ICU librarian failed: " + str(lib_log))
        entry.update({"objects": [artifact(obj) for obj in objects], "library": artifact(library),
                      "librarian": artifact(librarian), "library_response": artifact(lib_response), "library_log": artifact(lib_log)})
        print(f"Built ICU {component}: {len(objects)} AMD64 objects; warnings {dict(warnings)}", flush=True)
    verify_source()
    report["status"] = "ICU44_AMD64_STATIC_LIBRARIES_BUILT"
    report["original_files_unchanged"] = True
    (evidence / "build_result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(report["status"], flush=True)


if __name__ == "__main__":
    main()
