"""Build byte-identical SDK sources with a resource adapter; never load/deploy it."""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from collect_baseline import PROJECT, digest, pe_header, read_text


def msbuild_directory(path: Path) -> str:
    # Preserve literal apostrophes in legacy MSBuild item transforms (ZeroSis').
    value = path.as_posix() + "/"
    return "".join(f"%{ord(character):02X}" if character in "%$@();'?*" else character
                   for character in value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, required=True)
    parser.add_argument("--msbuild", type=Path, required=True)
    parser.add_argument("--windows-sdk", type=Path, required=True,
                        help="Installed legacy Windows SDK; bypasses optional per-user SDK discovery")
    args = parser.parse_args()
    if not (args.windows_sdk / "Include/Windows.h").is_file():
        raise RuntimeError("Requested Windows SDK does not contain Include/Windows.h")
    snapshot = PROJECT / "Source/SDK_BNW_Original"
    build = PROJECT / "Build/SDK_Reference"
    evidence = PROJECT / "evidence/sdk_reference"
    support = PROJECT / "Source/BuildSupport"
    for directory in (snapshot, build / "out", build / "obj", build / "NoUserProps", evidence):
        directory.mkdir(parents=True, exist_ok=True)
    with (PROJECT / "evidence/2026-09-22/input_sha256.csv").open(encoding="utf-8-sig", newline="") as stream:
        m0 = {row["path"]: row["sha256"] for row in csv.DictReader(stream)}
    manifest = []
    for original in sorted(args.sdk.rglob("*")):
        if not original.is_file():
            continue
        original_hash = digest(original)
        if m0.get(str(original)) != original_hash:
            raise RuntimeError(f"SDK input differs from M0: {original}")
        copy = snapshot / original.relative_to(args.sdk)
        copy.parent.mkdir(parents=True, exist_ok=True)
        if copy.exists():
            if digest(copy) != original_hash:
                raise RuntimeError(f"Existing snapshot differs; refusing overwrite: {copy}")
        else:
            shutil.copyfile(original, copy)
        if digest(copy) != original_hash:
            raise RuntimeError(f"Snapshot copy mismatch: {copy}")
        manifest.append({"source": str(original), "snapshot": str(copy), "sha256": original_hash})
    (evidence / "snapshot_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    project = snapshot / "CvGameCoreDLL_Expansion2/CvGameCoreDLL_Expansion2.vs2010.vcxproj"
    command = [str(args.msbuild), str(project), "/nologo", "/t:Build", "/m:2", "/v:minimal",
               "/p:Configuration=Mod", "/p:Platform=Win32", "/p:CL_MPCount=2",
               f"/p:SolutionDir={msbuild_directory(snapshot)}", f"/p:OutDir={msbuild_directory(build / 'out')}",
               f"/p:TargetPlatformSdkPath={msbuild_directory(args.windows_sdk)}",
               f"/p:WindowsSdkDir={msbuild_directory(args.windows_sdk)}",
               f"/p:IntDir={msbuild_directory(build / 'obj')}", f"/p:UserRootDir={msbuild_directory(build / 'NoUserProps')}",
               "/p:ForceImportAfterCppTargets=" + msbuild_directory(support) + "sdk_reference.targets"]
    if not args.msbuild.is_file():
        raise RuntimeError("Requested MSBuild does not exist")
    print(json.dumps({"phase": "BUILDING_UNCHANGED_SDK_SNAPSHOT", "files_verified": len(manifest)}, ensure_ascii=False), flush=True)
    attempts = evidence / "attempts"
    attempts.mkdir(exist_ok=True)
    if not list(attempts.iterdir()) and (evidence / "build_result.json").is_file():
        previous = attempts / "attempt_001"
        previous.mkdir()
        for name in ("msbuild.log", "build_result.json"):
            if (evidence / name).is_file():
                shutil.copyfile(evidence / name, previous / name)
    attempt = attempts / f"attempt_{len(list(attempts.iterdir())) + 1:03d}"
    attempt.mkdir()
    log_path = attempt / "msbuild.log"
    environment = {key.upper(): value for key, value in os.environ.items()}
    started = datetime.now(timezone.utc).isoformat()
    with log_path.open("wb") as log:
        result = subprocess.run(command, cwd=build, env=environment, stdout=log, stderr=subprocess.STDOUT,
                                timeout=900, creationflags=subprocess.CREATE_NO_WINDOW)
    log_text = read_text(log_path)
    failures = sorted(set(re.findall(r"(?m)^.*\berror\s+[A-Z]+\d+[^\r\n]*", log_text, re.I)))
    warnings = sorted(set(re.findall(r"(?m)^.*\bwarning\s+[A-Z]+\d+[^\r\n]*", log_text, re.I)))
    original_matches = all(digest(Path(row["source"])) == row["sha256"] for row in manifest)
    snapshot_matches = all(digest(Path(row["snapshot"])) == row["sha256"] for row in manifest)
    outputs = []
    for path in sorted((build / "out").glob("*.dll")):
        outputs.append({"path": str(path), "sha256": digest(path), "pe": pe_header(path)})
    status = "SDK_REFERENCE_BUILD_PASS" if result.returncode == 0 and outputs and original_matches and snapshot_matches else "SDK_REFERENCE_BUILD_FAILED"
    report = {
        "started_at_utc": started, "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": status, "exit_code": result.returncode, "command": command,
        "sdk_snapshot_files": len(manifest), "original_hashes_unchanged": original_matches,
        "snapshot_matches_original": snapshot_matches, "unique_warning_lines": warnings,
        "unique_error_lines": failures, "outputs": outputs, "log": str(log_path),
        "object_files": len(list((build / "obj").rglob("*.obj"))),
        "build_support": [{"path": str(path), "sha256": digest(path)}
                          for path in sorted(support.iterdir()) if path.is_file()],
        "build_adjustments": ["Explicit installed Windows SDK path", "MSBuild literal path escaping",
                              "Resource-only afxres.h adapter includes Windows SDK WinResrc.h",
                              "Link map and verbose library search enabled"],
        "runtime_verified": False, "game_launched": False, "deployed": False,
        "x64_gamecore_built": False,
    }
    (evidence / "build_result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    shutil.copyfile(evidence / "build_result.json", attempt / "build_result.json")
    shutil.copyfile(log_path, evidence / "msbuild.log")
    print(json.dumps({"status": status, "exit_code": result.returncode, "snapshot_files": len(manifest),
                      "objects": report["object_files"], "dlls": len(outputs),
                      "error_lines": failures[:8], "original_hashes_unchanged": original_matches}, ensure_ascii=False))
    if status != "SDK_REFERENCE_BUILD_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
