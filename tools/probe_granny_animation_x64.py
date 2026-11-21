#!/usr/bin/env python3
"""One bounded, read-only x64 public Granny curve-sampling probe."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
CSC = Path(r"C:\Windows\Microsoft.NET\Framework\v4.0.30319\csc.exe")
DEFAULT_SDK = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V SDK\Nexus\x86")
EXPORTS = PROJECT / "Build" / "StockUnitExports" / "20261005T072135Z"
MAX_JSON = 4 * 1024 * 1024
CONFIG = (b'<?xml version="1.0"?><configuration><startup useLegacyV2RuntimeActivationPolicy="true">'
          b'<supportedRuntime version="v4.0" sku=".NETFramework,Version=v4.0"/></startup></configuration>')


def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def artifact(path: Path) -> dict:
    path = path.absolute()
    require(path.is_file(), f"Artifact is not a file: {path}")
    return {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run_bounded(argv: list[str], timeout: int, cwd: Path, env: dict[str, str]) -> dict:
    started = time.monotonic()
    try:
        result = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW,
                                check=False)
        return {"argv": argv, "exit_code": result.returncode, "timed_out": False,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "stdout": result.stdout, "stderr": result.stderr}
    except subprocess.TimeoutExpired as error:
        return {"argv": argv, "exit_code": None, "timed_out": True,
                "elapsed_seconds": round(time.monotonic() - started, 3),
                "stdout": error.stdout or b"", "stderr": error.stderr or b""}


def main() -> int:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    build_root = PROJECT / "Build" / "GrannyAnimationProbe" / run_id
    evidence_root = PROJECT / "evidence" / "granny_animation" / run_id
    require(not build_root.exists() and not evidence_root.exists(), "Run output already exists")

    # Keep the known install path lexical: resolving the Steam directory through
    # Windows final-path APIs can be denied even when individual files are readable.
    sdk = DEFAULT_SDK
    manifest_path = EXPORTS / "export-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    require(manifest.get("status") == "PASS_STOCK_UNIT_EXPORT", "Existing stock export is not sealed PASS")
    row = next((x for x in manifest["outputs"] if x.get("member_type") == "ART_DEF_UNIT_MEMBER_WARRIOR_V2"), None)
    require(row is not None, "Existing V2 export row is missing")
    expected_json = Path(row["json"]["path"]).absolute()
    model_path = Path(row["model"]["extracted"]["path"]).absolute()
    idle_path = Path(row["idle"]["extracted"]["path"]).absolute()
    gsd_path = Path(manifest["gsd"]["extracted"]["path"]).absolute()
    for path, record in ((expected_json, row["json"]), (model_path, row["model"]["extracted"]),
                         (idle_path, row["idle"]["extracted"]), (gsd_path, manifest["gsd"]["extracted"])):
        require(sha256_file(path) == record["sha256"], f"Existing export artifact hash mismatch: {path.name}")
    require(model_path.name.casefold() == "warrior_v2.gr2" and idle_path.name.casefold() == "warrior_idlea.gr2",
            "Existing export artifacts are not the selected stock V2 Warrior/IdleA pair")

    sdk_names = ("Firaxis.Framework.dll", "Firaxis.Framework.Granny.dll",
                 "Firaxis.Framework.FirePlace.dll", "Firaxis.Framework.Granny.Implx64.dll")
    sdk_paths = [sdk / name for name in sdk_names]
    require(all(path.is_file() for path in sdk_paths), "A required installed x64 Granny SDK assembly is missing")
    require(CSC.is_file(), "Installed .NET Framework 4 C# compiler is missing")

    build_root.mkdir(parents=True)
    evidence_root.mkdir(parents=True)
    exe = build_root / "GrannyAnimationProbe.exe"
    source = HERE / "GrannyAnimationProbe.cs"
    source_script = Path(__file__).resolve()
    tracked_inputs = [source, source_script, CSC, *sdk_paths, gsd_path, model_path, idle_path, expected_json]
    before = [artifact(path) for path in tracked_inputs]
    # ReflectionHelper.ProxyAssembly resolves Implx64 beside the executable.
    # Stage only these four SDK-managed assemblies in this private run folder;
    # the installed SDK files remain the read-only source of truth.
    staged_assemblies = []
    for source_dll in sdk_paths:
        destination = build_root / source_dll.name
        destination.write_bytes(source_dll.read_bytes())
        require(sha256_file(destination) == sha256_file(source_dll),
                f"Staged SDK assembly hash mismatch: {source_dll.name}")
        staged_assemblies.append(artifact(destination))
    (build_root / (exe.name + ".config")).write_bytes(CONFIG)

    refs = ["/reference:" + str(sdk / "Firaxis.Framework.dll"),
            "/reference:" + str(sdk / "Firaxis.Framework.Granny.dll"),
            "/reference:" + str(sdk / "Firaxis.Framework.FirePlace.dll"),
            "/reference:System.Web.Extensions.dll"]
    compile_argv = [str(CSC), "/nologo", "/target:exe", "/platform:x64", "/optimize+",
                    "/warn:4", "/warnaserror+", "/out:" + str(exe), *refs, str(source)]
    compiler = run_bounded(compile_argv, 45, build_root, os.environ.copy())
    (build_root / "compile.stdout.txt").write_bytes(compiler["stdout"])
    (build_root / "compile.stderr.txt").write_bytes(compiler["stderr"])
    compiler_summary = {k: v for k, v in compiler.items() if k not in ("stdout", "stderr")}
    if compiler["exit_code"] != 0 or compiler["timed_out"]:
        after = [artifact(path) for path in tracked_inputs]
        report = {"schema": 1, "run_id": run_id, "status": "FAILED_COMPILE",
                  "compiler": compiler_summary, "inputs_before": before, "inputs_after": after,
                  "source_inputs_unchanged": before == after}
        write_json(evidence_root / "report.json", report)
        print(json.dumps({"status": report["status"], "report": str(evidence_root / "report.json")}, indent=2))
        return 1

    output_json = build_root / "curve-samples.json"
    child_env = os.environ.copy()
    child_env["ZS_GRANNY_EXPECTED_JSON"] = str(expected_json)
    child_env["ZS_GRANNY_OUTPUT_JSON"] = str(output_json)
    runtime = run_bounded([str(exe), str(sdk), str(gsd_path), str(model_path), str(idle_path)],
                          30, build_root, child_env)
    stdout_path, stderr_path = build_root / "probe.stdout.txt", build_root / "probe.stderr.txt"
    stdout_path.write_bytes(runtime["stdout"])
    stderr_path.write_bytes(runtime["stderr"])
    runtime_summary = {k: v for k, v in runtime.items() if k not in ("stdout", "stderr")}
    probe_result = None
    if runtime["exit_code"] == 0 and not runtime["timed_out"]:
        require(output_json.is_file() and output_json.stat().st_size <= MAX_JSON, "Probe output missing/oversized")
        probe_result = json.loads(output_json.read_text(encoding="utf-8"))

    after = [artifact(path) for path in tracked_inputs]
    report = {"schema": 1, "run_id": run_id,
              "status": "PASS_PUBLIC_CURVE_SAMPLE_X64" if probe_result and
              probe_result.get("status") == "PASS_PUBLIC_CURVE_SAMPLE_X64" else "FAILED_RUNTIME_PROBE",
              "inputs_before": before, "inputs_after": after,
              "source_inputs_unchanged": before == after,
              "staged_sdk_assemblies": staged_assemblies,
              "staged_sdk_hashes_match_installed": all(
                  staged["sha256"] == original["sha256"]
                  for staged, original in zip(staged_assemblies, before[3:7])),
              "compiler": compiler_summary,
              "executable": artifact(exe), "runtime": runtime_summary,
              "stdout": artifact(stdout_path), "stderr": artifact(stderr_path),
              "probe_result": probe_result}
    require(before == after, "A source export or installed SDK input changed during the probe")
    report_path = evidence_root / "report.json"
    write_json(report_path, report)
    print(json.dumps({"status": report["status"], "run_id": run_id,
                      "report": str(report_path), "runtime_exit_code": runtime["exit_code"],
                      "backend": (probe_result or {}).get("sdk", {}).get("animation_runtime_path"),
                      "t0_max_error": (probe_result or {}).get("t0_comparison", {}).get("max_absolute_error"),
                      "time_samples": len((probe_result or {}).get("samples", []))}, indent=2))
    return 0 if report["status"] == "PASS_PUBLIC_CURVE_SAMPLE_X64" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"PROBE_FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        raise
