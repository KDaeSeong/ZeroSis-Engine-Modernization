"""Build/run isolated numerical conformance programs, never Civilization V.

The x86 reference uses arithmetic statements extracted from the installed SDK.
It excludes engine logging, serialization and debug stack capture. A Python
integer oracle checks every record independently of the two C++ executables.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

from collect_baseline import PROJECT, digest, pe_header, read_text
from analyze_contracts import mask_cpp, closing_brace


def run(command, *, cwd, env=None, timeout=60):
    completed = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=timeout,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    if completed.returncode:
        message = (completed.stdout + completed.stderr).decode("mbcs", errors="replace")
        raise RuntimeError(f"Command failed ({completed.returncode}): {command[0]}\n{message[:7000]}")
    return completed


def extract_reference(sdk: Path, destination: Path) -> dict:
    import re
    cpp = sdk / "CvGameCoreDLL_Expansion2" / "CvRandom.cpp"
    source = read_text(cpp)
    masked = mask_cpp(source)
    import csv
    with (PROJECT / "evidence/2026-09-22/input_sha256.csv").open(encoding="utf-8-sig", newline="") as stream:
        original = {row["path"]: row["sha256"] for row in csv.DictReader(stream)}
    if original.get(str(cpp)) != digest(cpp):
        raise RuntimeError("CvRandom.cpp differs from M0. Review source changes before rebuilding the reference.")

    body_start = masked.index("{", masked.index("unsigned short CvRandom::get("))
    body_end = closing_brace(masked, body_start)
    body = source[body_start + 1:body_end]
    statements = []
    for pattern in (
        r"m_ulCallCount\+\+;", r"unsigned long ulNewSeed\s*=[^;]+;",
        r"unsigned short us\s*=[^;]+;", r"m_ulRandomSeed\s*=\s*ulNewSeed;", r"return us;",
    ):
        matches = re.findall(pattern, body)
        if len(matches) != 1:
            raise RuntimeError(f"SDK arithmetic extraction is ambiguous: {pattern}")
        statements.append(matches[0])
    constants = []
    for name in ("RANDOM_A", "RANDOM_C", "RANDOM_SHIFT"):
        match = re.search(rf"(?m)^#define\s+{name}\s+\((\d+)\)", source)
        if not match:
            raise RuntimeError(f"Missing SDK constant: {name}")
        constants.append(f"#define {name} ({match[1]})")
    float_start = masked.index("{", masked.index("float CvRandom::getFloat()"))
    float_end = closing_brace(masked, float_start)
    float_body = source[float_start + 1:float_end].strip()
    generated = """// Generated numerical reference. Not the full SDK CvRandom implementation.
// Original arithmetic: Firaxis/Take-Two SDK CvRandom.cpp; provenance beside this file.
#pragma once
#include <cstdint>
static_assert(sizeof(unsigned long) == 4);
static_assert(sizeof(unsigned short) == 2);
struct ReferenceSnapshot { unsigned long seed, calls, resets; bool synchronous; };
""" + "\n".join(constants) + """
#define MAX_UNSIGNED_SHORT (65535)
class SdkNumericReference {
    unsigned long m_ulRandomSeed = 0;
    unsigned long m_ulCallCount = 0;
    unsigned long m_ulResetCount = 0;
    bool m_bSynchronous = false;
public:
    SdkNumericReference() { reset(); }
    explicit SdkNumericReference(bool) : m_bSynchronous(true) {}
    void init(unsigned long seed) { reset(seed); }
    void reset(unsigned long ulSeed = 0) { m_ulRandomSeed = ulSeed; m_ulResetCount++; }
    void reseed(unsigned long ulNewValue) { m_ulResetCount++; m_ulRandomSeed = ulNewValue; }
    unsigned short get(unsigned short usNum) {
""" + "\n".join(statements) + """
    }
    float getFloat() { """ + float_body + """ }
    unsigned long getSeed() const { return m_ulRandomSeed; }
    unsigned long getCallCount() const { return m_ulCallCount; }
    unsigned long getResetCount() const { return m_ulResetCount; }
    bool isSynchronous() const { return m_bSynchronous; }
    void restore_numeric(ReferenceSnapshot state) {
        m_ulRandomSeed = state.seed; m_ulCallCount = state.calls;
        m_ulResetCount = state.resets; m_bSynchronous = state.synchronous;
    }
    bool operator==(const SdkNumericReference& other) const { return m_ulRandomSeed == other.m_ulRandomSeed; }
    bool operator!=(const SdkNumericReference& other) const { return !(*this == other); }
};
"""
    destination.write_text(generated, encoding="utf-8")
    return {
        "source": str(cpp), "source_sha256": digest(cpp),
        "extracted_get_statements": statements, "extracted_constants": constants,
        "extracted_getFloat_body": float_body,
        "wrapper": "Handwritten numeric fields/constructors/counters, reviewed against SDK; not full SDK class",
        "excluded": ["GC/gDLL logging", "engine thread assertions", "FDataStream", "debug stack history"],
    }


def build_architecture(architecture: str, vs: Path, generated_dir: Path, evidence: Path) -> dict:
    build_dir = PROJECT / "Build" / "Numerics" / architecture
    build_dir.mkdir(parents=True, exist_ok=True)
    vcvars = vs / "VC/Auxiliary/Build" / ("vcvars32.bat" if architecture == "x86" else "vcvars64.bat")
    if not vcvars.is_file():
        raise RuntimeError(f"Build environment missing: {vcvars}")
    setup = build_dir / "read_build_environment.cmd"
    setup.write_text(f'@echo off\ncall "{vcvars}" >nul\nif errorlevel 1 exit /b 1\nset\n', encoding="utf-8")
    environment = {key.upper(): value for key, value in os.environ.items()}
    environment_output = run(["cmd.exe", "/d", "/c", str(setup)], cwd=build_dir, env=environment)
    path_values = []
    for line in environment_output.stdout.decode("mbcs", errors="replace").splitlines():
        if "=" in line and not line.startswith("="):
            key, value = line.split("=", 1)
            environment[key.upper()] = value
            if key.upper() == "PATH":
                path_values.append(value)
    # Some host environments expose both Path and PATH; retain the initialized
    # tool directories rather than letting a stale duplicate hide the compiler.
    environment["PATH"] = ";".join(dict.fromkeys(part for value in path_values for part in value.split(";")))
    # Never save or print the process environment; it can contain unrelated secrets.
    compiler = shutil.which("cl.exe", path=environment.get("PATH"))
    if compiler is None:
        raise RuntimeError("C++ compiler missing from initialized environment")
    executable = build_dir / "random_conformance.exe"
    response = build_dir / "compile.rsp"
    flags = ["/nologo", "/std:c++17", "/EHsc", "/W4", "/WX", "/O2", "/fp:strict", "/MT"]
    if architecture == "x86":
        flags.append("/DZEROSIS_REFERENCE_BUILD")
    flags += [f'/I"{PROJECT / "Source"}"', f'/I"{generated_dir}"',
              f'"{PROJECT / "Tests/random_trace.cpp"}"', f'/Fo"{build_dir / "random_trace.obj"}"',
              f'/Fe"{executable}"']
    link_flags = ["/INCREMENTAL:NO", "/Brepro", "/WX",
                  "/MACHINE:X86" if architecture == "x86" else "/MACHINE:X64"]
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    # Keep /link on the command line with its arguments. In a multiline response
    # file, CL may resume compiler-option parsing on the following line.
    compilation = run([compiler, f"@{response}", "/link", *link_flags], cwd=build_dir, env=environment)
    build_log = (compilation.stdout + compilation.stderr).decode("mbcs", errors="replace")
    (evidence / f"compile_{architecture}.txt").write_text(build_log, encoding="utf-8")
    if re.search(r"\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+", build_log, re.I):
        raise RuntimeError(f"Compiler/linker warning detected in {architecture} build")
    pe = pe_header(executable)
    if pe["architecture"] != architecture:
        raise RuntimeError(f"Unexpected executable architecture: {pe}")
    return {"path": str(executable), "sha256": digest(executable), "compiler": compiler,
            "flags": flags + ["/link"] + link_flags, "pe": pe,
            "compiler_and_linker_warnings": 0,
            "compile_time_abi_assertions": {"pointer_bytes": 4 if architecture == "x86" else 8,
                "size_t_bytes": 4 if architecture == "x86" else 8, "unsigned_long_bytes": 4,
                "unsigned_int_bytes": 4, "unsigned_short_bytes": 2, "bool_bytes": 1}}


def oracle_trace():
    mask = 0xFFFFFFFF
    state = [0, 0, 1, 0]

    def record(phase, bound=0, result=0, index=0):
        return (phase, bound, result, *state, index)

    def draw(bound):
        state[1] = (state[1] + 1) & mask
        state[0] = (state[0] * 1103515245 + 12345) & mask
        return ((state[0] >> 16) * bound) // 65536

    yield record(1)
    state[:] = [0, 0, 0, 1]
    yield record(2)
    yield record(3)
    state[:] = [mask, 0, 2, 0]
    yield record(4, 0, draw(0))
    yield record(5, 1, draw(1))
    state[0] = 17
    state[2] += 1
    yield record(6)
    state[0] = 8
    state[2] += 1
    yield record(7)
    state[:] = [mask, mask, mask, 0]
    yield record(8, 0, draw(0))
    state[0] = 0
    state[2] = 0
    yield record(9)
    draw(37)
    yield record(10, 37, 1)
    state[:] = [0, 123, 456, 1]
    yield record(11, 0, 1)
    state[:] = [0x12345678, 0, 2, 0]
    for bound in range(65536):
        yield record(20, bound, draw(bound), bound)
    for seed_index in range(1024):
        seed = ((seed_index * 2654435761) & mask) ^ 0xA5A5A5A5
        state[:] = [seed, 0, 2, 0]
        for draw_index in range(128):
            bound = (seed_index * 131 + draw_index * 997) & 65535
            yield record(30, bound, draw(bound), seed_index * 128 + draw_index)
    state[:] = [0x87654321, 0, 2, 0]
    for index in range(1024):
        value = draw(65535) / 65535
        bits = struct.unpack("<I", struct.pack("<f", value))[0]
        yield record(40, 65535, bits, index)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--vs", type=Path, required=True)
    args = parser.parse_args()
    evidence = PROJECT / "evidence" / "numerics"
    evidence.mkdir(parents=True, exist_ok=True)
    generated = PROJECT / "Build" / "Numerics" / "reference"
    generated.mkdir(parents=True, exist_ok=True)
    provenance = extract_reference(args.sdk, generated / "sdk_numeric_reference.h")
    (evidence / "reference_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    inputs = [PROJECT / "Source/Numerics/CvCompatibleRandom.h", PROJECT / "Tests/random_trace.cpp", Path(provenance["source"])]
    hashes_before = {str(path): digest(path) for path in inputs}
    builds = [build_architecture(arch, args.vs, generated, evidence) for arch in ("x86", "x64")]
    traces = []
    for build in builds:
        traces.append(run([build["path"]], cwd=PROJECT / "Build/Numerics").stdout)
    if traces[0] != traces[1]:
        first = next((i for i, (a, b) in enumerate(zip(*traces)) if a != b), min(map(len, traces)))
        raise RuntimeError(f"x86/x64 trace mismatch at byte {first}")
    actual = traces[1]
    if len(actual) % 32:
        raise RuntimeError("Trace has incomplete records")
    records = list(struct.iter_unpack("<8I", actual))
    expected = list(oracle_trace())
    if len(records) != len(expected):
        raise RuntimeError(f"Oracle record count mismatch: {len(records)} != {len(expected)}")
    for index, (observed, wanted) in enumerate(zip(records, expected)):
        if observed != wanted:
            raise RuntimeError(f"Numerical oracle mismatch at record {index}: {observed} != {wanted}")
    if any(digest(Path(path)) != value for path, value in hashes_before.items()):
        raise RuntimeError("Observed implementation or reference changed during verification")
    stage = PROJECT / "Stage/Numerics"
    stage.mkdir(parents=True, exist_ok=True)
    staged_header = stage / "CvCompatibleRandom.h"
    shutil.copyfile(inputs[0], staged_header)
    if digest(staged_header) != hashes_before[str(inputs[0])]:
        raise RuntimeError("Staged numerical header differs from tested source")
    report = {
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "ISOLATED_NATIVE_NUMERIC_CONFORMANCE_PASS",
        "scope": "SDK_RELEASE_ARITHMETIC_COUNTERS_ONLY_NOT_GAMECORE_RUNTIME",
        "records_compared_exactly": len(records), "oracle_records_passed": len(expected),
        "phase_counts": dict(Counter(row[0] for row in records)),
        "trace_bytes": len(actual), "trace_sha256": hashlib.sha256(actual).hexdigest(),
        "builds": builds, "input_sha256": hashes_before,
        "stage_header": {"path": str(staged_header), "sha256": digest(staged_header)},
        "warning_policy": "MSVC W4 WX; linker WX; explicit compiler/linker warning log scan",
        "full_gamecore_built": False, "game_launched": False, "save_compatibility_verified": False,
        "multicore_game_execution_verified": False, "performance_improvement_measured": False,
        "excluded": provenance["excluded"],
    }
    (evidence / "conformance.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (stage / "verification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "status", "records_compared_exactly", "oracle_records_passed", "trace_sha256",
        "full_gamecore_built", "game_launched", "multicore_game_execution_verified",
    )}))


if __name__ == "__main__":
    main()
