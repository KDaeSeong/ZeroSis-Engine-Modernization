"""Run actual x64 numeric helpers and extracted SDK functions against independent oracles."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import struct

from collect_baseline import PROJECT, digest
from native_build import build_program, checked_run


def block(text, marker, semicolon=False):
    start = text.index(marker)
    opening = text.index("{", start)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[start:index + 1] + (";" if semicolon else "")
    raise RuntimeError(f"Incomplete source definition: {marker}")


def extracts(directory):
    port = PROJECT / "Source/SDK_BNW_x64"
    files = {name: port / relative for name, relative in {
        "auto": "FirePlace/include/FireWorks/FAutoVector.h",
        "database": "CvGameCoreDLL_Expansion2/CvDatabaseUtility.cpp",
        "flua": "FirePlace/include/FireWorks/FLua/Include/FLuaCommon.h",
        "enums": "CvGameCoreDLLUtil/include/CvEnums.h",
        "notifications": "CvGameCoreDLL_Expansion2/CvNotifications.cpp"}.items()}
    content = {name: path.read_bytes().decode("latin1").replace("\r\n", "\n") for name, path in files.items()}
    output = ["// Extracted from Firaxis SDK port for isolated execution. Original copyright remains applicable.\n"]
    output.append(block(content["auto"], "template<typename ElementType>\nstruct AutoVectorCommand", True))
    for name, signature in (("setAt", "size_t index, const ElementType & v"),
                            ("insert", "size_t index, const ElementType & v"), ("erase", "size_t index"),
                            ("resize", "size_t count"), ("resize", "size_t count, const ElementType & v")):
        output.append("template<typename ElementType, typename ClassContainer>\n" + block(content["auto"],
            f"void FAutoVariable<std::vector<ElementType>, ClassContainer>::{name}({signature})"))
    output.append(block(content["database"], "void CvDatabaseUtility::Initialize2DArray(int**& ppArray, const size_t"))
    output.append(block(content["database"], "void CvDatabaseUtility::SafeDelete2DArray"))
    output.append("namespace FLua { namespace Details {")
    for name in ("ArgValidator<int>", "FromLuaAnalog<int>"):
        output.append(block(content["flua"], "template<> struct " + name, True))
    output.append("template<> struct ArgValidator<const int> : ArgValidator<int> {};\n"
                  "template<> struct FromLuaAnalog<const int> : FromLuaAnalog<int> {};\n}}")
    output.append(block(content["enums"], "enum NotificationTypes", True))
    table = block(content["notifications"], "static uint V1_IndexToHash[]", True)
    output.append(table)
    path = directory / "sdk_numeric_extracts.h"
    path.write_text("\n\n".join(output) + "\n", encoding="utf-8")
    original_table_path = PROJECT / "Source/SDK_BNW_Original/CvGameCoreDLL_Expansion2/CvNotifications.cpp"
    original_table = block(original_table_path.read_bytes().decode("latin1"), "static uint V1_IndexToHash[]", True)
    names = re.findall(r"\bNOTIFICATION_\w+\b", original_table)
    if re.findall(r"\bNOTIFICATION_\w+\b", table) != names:
        raise RuntimeError("Notification index order changed")
    definitions = dict(re.findall(r"\b(NOTIFICATION_\w+)\s*=\s*(0x[0-9A-Fa-f]+)\b", content["enums"]))
    hashes = b"".join(struct.pack("<I", int(definitions[name], 16)) for name in names)
    return path, [*files.values(), original_table_path], hashes, len(names)


def fixtures():
    candidates = {0, 1, -1, 42}
    for width in (8, 16, 32, 64):
        for value in (-(1 << (width - 1)), 1 << (width - 1), 1 << width):
            candidates.update(range(value - 3, value + 4))
    rng = random.Random(0x641432)
    signed = sorted({v for v in candidates if -(1 << 63) <= v < 1 << 63})
    signed += [rng.getrandbits(64) - (1 << 63) for _ in range(2048)]
    unsigned = sorted({v for v in candidates if 0 <= v < 1 << 64})
    unsigned += [rng.getrandbits(64) for _ in range(2048)]
    targets = [(True, 8), (False, 8), (True, 16), (False, 16), (True, 32), (False, 32),
               (True, 64), (False, 64), (False, 64), (True, 64)]
    inputs, outputs = [], []
    for kind, values in ((0, signed), (1, unsigned)):
        for number in values:
            for index, (is_signed, width) in enumerate(targets):
                minimum = -(1 << (width - 1)) if is_signed else 0
                maximum = (1 << (width - int(is_signed))) - 1
                valid = minimum <= number <= maximum
                inputs.append(struct.pack("<BBQ", kind, index, number & ((1 << 64) - 1)))
                outputs.append(struct.pack("<BQ", valid, (number & ((1 << 64) - 1)) if valid else 0))
    return b"ZNRW0001" + struct.pack("<I", len(inputs)) + b"".join(inputs), b"".join(outputs), len(inputs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vs", type=Path, required=True)
    parser.add_argument("--lua-provider", type=Path, help="Test the GameCore /MD provider instead of unmodified upstream Lua")
    args = parser.parse_args()
    evidence = PROJECT / "evidence/numeric_boundaries"
    directory = PROJECT / "Build/Numeric_boundaries"
    directory.mkdir(parents=True, exist_ok=True)
    lua_report = args.lua_provider.resolve() if args.lua_provider else PROJECT / "evidence/lua_component/build_result.json"
    lua = json.loads(lua_report.read_text(encoding="utf-8"))
    if args.lua_provider:
        if lua["status"] != "LUA51_X64_MD_PROVIDER_BUILT" or lua["runtime"] != "/MD":
            raise RuntimeError("Expected GameCore-compatible provider runtime")
        lua_inputs = json.loads(Path(lua["source_manifest"]["path"]).read_text(encoding="utf-8"))
        lua_inputs += [lua[key] for key in ("library", "builder", "source_manifest", "patches", "log")]
    else:
        lua_inputs = lua["sources"] + [lua["library"], lua["archive"], lua["builder"]]
    if any(digest(Path(r["path"])) != r["sha256"] for r in lua_inputs):
        raise RuntimeError("Lua component inputs changed")
    manifest = json.loads((PROJECT / "evidence/sdk_x64/port_manifest.json").read_text(encoding="utf-8"))
    if any(digest(Path(r["port"])) != r["port_sha256"] for r in manifest):
        raise RuntimeError("Generated SDK port changed")
    extract, sdk_inputs, hash_expected, notification_count = extracts(directory)
    source = PROJECT / "Tests/numeric_boundaries_test.cpp"
    inputs = [source, extract, *sdk_inputs, *list((PROJECT / "Source/Porting").glob("*.h")),
              PROJECT / "Source/Porting/sdk_x64_patches.json", Path(__file__).resolve(), PROJECT / "tools/native_build.py",
              lua_report, Path(lua["library"]["path"])]
    before = {str(p): digest(p) for p in inputs}
    executable = build_program(name="numeric_boundaries_test", architecture="x64", vs=args.vs,
        directory=directory, evidence=evidence, source=source,
        includes=[PROJECT / "Source/Porting", directory, PROJECT / "Source/SDK_BNW_x64/ThirdPartyLibs/Lua51/include"],
        defines=["_CRT_SECURE_NO_WARNINGS"], objects=[Path(lua["library"]["path"])], runtime=lua["runtime"])
    fixture_bytes, expected, count = fixtures()
    fixture = directory / "inputs.bin"
    fixture.write_bytes(fixture_bytes)
    trace, hashes = directory / "conversion_trace.bin", directory / "notification_hashes.bin"
    execution = checked_run([executable["path"], fixture, trace, hashes], cwd=directory, timeout=90)
    native = json.loads(execution.stdout.decode("utf-8"))
    if native["status"] != "PASS" or native["records"] != count or native["notification_entries"] != notification_count:
        raise RuntimeError("Native coverage accounting mismatch")
    if trace.read_bytes() != expected or hashes.read_bytes() != hash_expected:
        raise RuntimeError("Native output differs from the independent Python integer/hash oracle")
    if native["lua_rejections"] != native["lua_recoveries"] or native["lua_cases"] < 70:
        raise RuntimeError("Lua error/recovery coverage incomplete")
    if any(digest(Path(p)) != h for p, h in before.items()):
        raise RuntimeError("Numeric inputs changed during execution")
    native_path = evidence / "native_execution.json"
    native_path.write_text(json.dumps(native, indent=2) + "\n", encoding="utf-8")
    output = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "status": "SDK_X64_NUMERIC_BOUNDARIES_PASS",
        "input_sha256": before, "build": executable, "native": native,
        "native_execution": {"path": str(native_path), "sha256": digest(native_path)},
        "fixtures": {"path": str(fixture), "sha256": digest(fixture)},
        "trace": {"path": str(trace), "sha256": digest(trace)},
        "notification_trace": {"path": str(hashes), "sha256": digest(hashes)},
        "expected_trace_sha256": hashlib.sha256(expected).hexdigest(),
        "expected_notification_sha256": hashlib.sha256(hash_expected).hexdigest(),
        "oracle": "Python arbitrary-precision integer bounds; unchanged SDK notification enum literals and table order",
        "lua_provider": "Tracked Lua 5.1.4 x64 code with SDK public headers; native ABI unchanged",
        "lua_library": lua["library"], "runtime": lua["runtime"],
        "lua_provider_report": {"path": str(lua_report), "sha256": digest(lua_report)},
        "verified": ["signed and unsigned 64-bit inputs into ten target integer types",
            "rejected conversion leaves destination unchanged; throwing adapter agrees",
            "native byte-count sum/product overflow; signed effect product and empty-history sentinel",
            "actual extracted FAutoVector methods reject oversized command indices before touch/mutation",
            "actual extracted SDK database array initialization/deallocation and overflow recovery",
            "actual FLua int validator/converter specializations",
            "actual Lua protected calls: types, strings, defaults, game/native bounds, NaN, infinities and recovery",
            "all legacy notification table entries preserve index order and uint32 bits"],
        "not_verified": ["full GameCore/engine integration or exception propagation", "cross-architecture fractional Lua rounding",
            "all Lua APIs or library behavioral compatibility", "whole-game save/load compatibility",
            "multicore game performance or host execution"], "game_launched": False, "gamecore_runtime_verified": False}
    (evidence / "conformance.json").write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": output["status"], **native}))


if __name__ == "__main__":
    main()
