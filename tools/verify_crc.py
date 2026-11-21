"""Compare actual SDK x86 CRC object code with a standalone x64 implementation."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib

from collect_baseline import PROJECT, digest, dump, read_text
from native_build import build_program, checked_run
from build_crc_reference import build_reference


def fixtures():
    seeds = (0, 1, 0x80000000, 0xffffffff)
    buffer = bytes((index * 73 + (index >> 3) * 19) & 255 for index in range(16384))
    yield 0xffffffff, b"123456789", 4
    for seed in seeds:
        for length in range(1025):
            yield seed, buffer[:length], length // 2
    for byte in range(256):
        yield seeds[byte % len(seeds)], bytes([byte]), byte % 2
    state = 0x12345678
    for _ in range(1024):
        state = (state * 1664525 + 1013904223) & 0xffffffff
        length = (state >> 8) % len(buffer)
        data = buffer[:length]
        yield state, data, state % (length + 1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--vs", type=Path, required=True)
    parser.add_argument("--dumpbin", type=Path, required=True)
    args = parser.parse_args()
    evidence = PROJECT / "evidence/crc"
    build = PROJECT / "Build/CRC"
    for directory in (evidence, build / "reference"):
        directory.mkdir(parents=True, exist_ok=True)
    header = args.sdk / "FirePlace/include/FireWorks/FCrc32.h"
    types = args.sdk / "FirePlace/include/FireWorks/FFireTypes.h"
    library = args.sdk / "FirePlace/lib/FireWorksWin32.lib"
    with (PROJECT / "evidence/2026-09-22/input_sha256.csv").open(encoding="utf-8-sig", newline="") as stream:
        m0 = {row["path"]: row["sha256"] for row in csv.DictReader(stream)}
    for path in (header, types, library):
        if m0.get(str(path)) != digest(path):
            raise RuntimeError(f"SDK reference input differs from M0: {path}")
    sources = [PROJECT / "Source/Numerics/CvCompatibleCrc32.h", PROJECT / "Tests/crc_trace.cpp",
               PROJECT / "Tests/sdk_crc_reference.cpp",
               header, types, library]
    input_hashes = {str(path): digest(path) for path in sources}
    libtool = args.dumpbin.with_name("lib.exe")
    reference_object = build / "reference/SDK_FCrc32.obj"
    # Preserve the exact SDK archive member as provenance. Linking uses the v90
    # archive because the member contains legacy LTCG/PCH dependencies.
    member = ".\\Final Release\\FCrc32.obj"
    checked_run([libtool, "/nologo", f"/EXTRACT:{member}", f"/OUT:{reference_object}", library], cwd=build)
    (evidence / "sdk_object_symbols.txt").write_text(dump(args.dumpbin, "/SYMBOLS", reference_object), encoding="utf-8")
    builds = [build_reference(args.sdk, evidence)]
    builds.append(build_program(name="crc_trace", architecture="x64", vs=args.vs,
                  directory=build / "x64", evidence=evidence, source=PROJECT / "Tests/crc_trace.cpp",
                  includes=[PROJECT / "Source"]))
    map_path = Path(builds[0]["map"])
    map_lines = read_text(map_path).splitlines()
    map_proof = [line.strip() for line in map_lines if "?Calc@FCRC@@" in line or "?g_CRC32@@" in line]
    if len(map_proof) != 2 or not all("FireWorksWin32:FCrc32.obj" in line for line in map_proof):
        raise RuntimeError("Actual SDK CRC provider was not confirmed in the reference link map")
    # Audit imports before execution. Neither standalone test may load a game module.
    for entry in builds:
        imports = dump(args.dumpbin, "/DEPENDENTS", Path(entry["path"]))
        import_path = evidence / f"imports_{entry['pe']['architecture']}.txt"
        import_path.write_text(imports, encoding="utf-8")
        if any(name in imports.lower() for name in ("fireworks", "cvgame", "lua51", "steam_api")):
            raise RuntimeError("Unexpected game dependency in standalone CRC test")
    cases = list(fixtures())
    fixture = build / "crc_inputs.bin"
    with fixture.open("wb") as stream:
        stream.write(b"ZCRC0001" + struct.pack("<I", len(cases)))
        for index, (seed, data, split) in enumerate(cases):
            stream.write(struct.pack("<4I", index, seed, len(data), split) + data)
    expected = b"".join(struct.pack("<5I", index, seed, len(data), checksum, checksum)
                        for index, (seed, data, _) in enumerate(cases)
                        for checksum in [zlib.crc32(data, seed ^ 0xffffffff) ^ 0xffffffff])
    outputs = [checked_run([entry["path"], fixture], cwd=build, timeout=60).stdout for entry in builds]
    if any(output != expected for output in outputs):
        for name, output in zip(("x86 SDK", "x64"), outputs):
            if output != expected:
                first = next((i for i, pair in enumerate(zip(output, expected)) if pair[0] != pair[1]), min(len(output), len(expected)))
                raise RuntimeError(f"{name} differs from zlib oracle at byte {first}")
    if any(digest(Path(path)) != value for path, value in input_hashes.items()):
        raise RuntimeError("CRC source/reference changed during verification")
    stage = PROJECT / "Stage/Numerics"
    stage.mkdir(parents=True, exist_ok=True)
    stage_header = stage / "CvCompatibleCrc32.h"
    shutil.copyfile(sources[0], stage_header)
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "SDK_BINARY_CRC_X86_X64_CONFORMANCE_PASS", "cases": len(cases),
              "whole_and_chunked_results_compared": len(cases) * 2,
              "trace_sha256": hashlib.sha256(expected).hexdigest(), "trace_bytes": len(expected),
              "oracle": "Python zlib.crc32(data, raw_seed XOR ffffffff) XOR ffffffff",
              "known_123456789_raw_crc": hex(struct.unpack_from("<5I", expected)[3]),
              "builds": builds, "input_sha256": input_hashes,
              "fixture": {"path": str(fixture), "sha256": digest(fixture)},
              "reference": {"kind": "ACTUAL_SDK_STATIC_OBJECT_CODE", "library": str(library),
                            "member": member, "object": str(reference_object), "object_sha256": digest(reference_object),
                            "map_proof": map_proof, "map_sha256": digest(map_path),
                            "note": "Original FireWorks library linked with v90 and VC90 runtime; harness calls only FCRC::Calc; no GameCore loaded"},
              "stage_header": {"path": str(stage_header), "sha256": digest(stage_header)},
              "excluded": ["CalcFile", "custom polynomial", "full FCRC ABI", "GameCore runtime", "4GB-sized buffer execution"],
              "game_launched": False, "x64_gamecore_built": False}
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    (evidence / "conformance.json").write_text(serialized, encoding="utf-8")
    (stage / "crc_verification.json").write_text(serialized, encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "cases", "whole_and_chunked_results_compared",
          "trace_sha256", "known_123456789_raw_crc", "game_launched")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
