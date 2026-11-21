"""Execute the actual patched SDK batch-allocation header, without GameCore or engine libraries."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from collect_baseline import PROJECT, digest
from native_build import build_program, checked_run


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vs", type=Path, required=True)
    args = parser.parse_args()
    root = PROJECT / "Source/SDK_BNW_x64"
    evidence = PROJECT / "evidence/sdk_x64_allocator"
    build = PROJECT / "Build/SDK_x64_allocator"
    manifest = json.loads((PROJECT / "evidence/sdk_x64/port_manifest.json").read_text(encoding="utf-8"))
    expected = {row["port"]: row["port_sha256"] for row in manifest}
    headers = [root / "FirePlace/include/FireWorks" / name for name in ("FBatchAllocate.h", "FAssert.h", "FDefNew.h")]
    if any(digest(path) != expected[str(path)] for path in headers):
        raise RuntimeError("Allocator input differs from the generated port manifest")
    source = PROJECT / "Tests/sdk_x64_allocator_test.cpp"
    sources = headers + [source, PROJECT / "Source/Porting/sdk_x64_patches.json", Path(__file__).resolve(),
                         PROJECT / "tools/native_build.py"]
    before = {str(path): digest(path) for path in sources}
    executable = build_program(name="sdk_x64_allocator_test", architecture="x64", vs=args.vs,
                               directory=build, evidence=evidence, source=source,
                               includes=[root / "FirePlace/include"], defines=["FINAL_RELEASE", "NDEBUG", "FXS_IS_DLL"])
    execution = checked_run([executable["path"]], cwd=build)
    native = json.loads(execution.stdout.decode("utf-8"))
    if (native["status"] != "PASS" or native["scope"] != "SDK_HEADER_ALLOCATOR_ONLY"
            or native["pointer_bytes"] != 8 or native["layout_cases"] != 196
            or native["allocations_above_4g"] != 197 or native["rejected_overflows"] != 4
            or not 0xffffffff < int(native["lowest_address"], 16) <= int(native["highest_address"], 16)):
        raise RuntimeError("Native SDK allocation coverage mismatch")
    if any(digest(Path(path)) != value for path, value in before.items()):
        raise RuntimeError("Allocator inputs changed during execution")
    execution_path = evidence / "native_execution.json"
    execution_path.write_text(json.dumps(native, indent=2) + "\n", encoding="utf-8")
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "SDK_X64_ALLOCATOR_COMPONENT_PASS", "input_sha256": before, "build": executable,
              "native_execution": {"path": str(execution_path), "sha256": digest(execution_path)},
              "native": native,
              "verified": ["actual patched SDK header compiled and executed in x64",
                           "32-bit logical dimensions retained, native-width byte and address arithmetic",
                           "196 1D/2D/mixed layouts including zero dimensions and 12-byte records",
                           "197 actual allocations at addresses above 4 GiB with reads/writes/free",
                           "array bounds and alignment; row strides and independent payload preservation",
                           "four injected size-overflow inputs rejected before outputs change, then recovery"],
              "not_verified": ["GameCore initialization or gameplay", "whole engine address-space acceptance gate",
                               "allocating more than 4 GiB of physical memory", "arbitrary nontrivial or over-aligned element types",
                               "all FireWorks memory providers", "race sanitizer", "game save/load compatibility"],
              "game_launched": False, "gamecore_runtime_verified": False}
    (evidence / "conformance.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"component_status": result["status"], **native}))


if __name__ == "__main__":
    main()
