import argparse
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from unit_animation_assets import embedded_assets
BRIDGE_RUN = ROOT / "Build" / "GrannyAnimationBridge" / "20261005T113900Z"
SDK = {
    "Firaxis.Framework.dll": "a1b9d304ba52fbf27d8c71c9fef3ff18b37581613b11d6da3f6f3e4d7daf7c86",
    "Firaxis.Framework.Granny.dll": "426c993ca193894cd6446f8ca1d04b98075febe4582fa14f37456e1ab6c62d68",
    "Firaxis.Framework.FirePlace.dll": "88b00a98551134b283e4a5e9c1343dfc339aa6eef6c6da55fe2c57878adde498",
    "Firaxis.Framework.Granny.Implx64.dll": "b73252c3783216b41b6926d188be77f6cc27e069fa29e978dad17fdb9ccb24d6",
}

def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--v1", required=True, type=Path)
    ap.add_argument("--v2", required=True, type=Path)
    ap.add_argument("--run-id", default=time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()))
    ap.add_argument("--resume-failed-run", action="store_true")
    args = ap.parse_args()
    if not re.fullmatch(r"2026[0-9]{4}T[0-9]{6}Z", args.run_id):
        raise SystemExit("run-id must be a UTC timestamp: YYYYMMDDTHHMMSSZ")
    args.v1, args.v2 = args.v1.absolute(), args.v2.absolute()
    if not args.v1.is_file() or not args.v2.is_file():
        raise SystemExit("Both unit package input files must exist")
    out = ROOT / "Build" / "UnitAnimation" / args.run_id
    evidence = ROOT / "evidence" / "unit_animation" / args.run_id
    if out.exists() or evidence.exists():
        report_path = evidence / "report.json"
        if not args.resume_failed_run or not out.is_dir() or not report_path.is_file():
            raise SystemExit("Refusing to overwrite an existing run")
        old = json.loads(report_path.read_text(encoding="utf-8"))
        if old.get("status", "").startswith("PASS") or old.get("v1_package", {}).get("sha256") != sha(args.v1) or old.get("v2_package", {}).get("sha256") != sha(args.v2):
            raise SystemExit("Only the exact inputs of a failed run may be resumed")
    compiler = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Tools\MSVC\14.44.35207\bin\HostX64\x64\cl.exe")
    vcvars = compiler.parents[6] / "Auxiliary" / "Build" / "vcvars64.bat"
    if not compiler.is_file() or not vcvars.is_file():
        raise SystemExit("The recorded VS 2022 x64 compiler/runtime is unavailable")
    out.mkdir(parents=True, exist_ok=True); evidence.mkdir(parents=True, exist_ok=True)
    runtime_input = out / "runtime_input"; runtime_input.mkdir(exist_ok=True)
    runtime_package = runtime_input / "unit-assets.bin"
    shutil.copy2(args.v2, runtime_package)
    embedded = embedded_assets(runtime_package)
    if not embedded: raise SystemExit("v2 package has no embedded animation inputs")
    for name, payload in embedded.items():
        (runtime_input / name).write_bytes(payload)
    embedded_hashes = {name: hashlib.sha256(payload).hexdigest() for name, payload in embedded.items()}
    frozen = out / "frozen"; frozen.mkdir(exist_ok=True)
    inputs = [ROOT / "Source" / "Presentation" / "WorldUnitAssets.h",
              ROOT / "Source" / "Animation" / "UnitAnimation.h",
              ROOT / "Source" / "Animation" / "GrannyAnimationBridge.h",
              ROOT / "tools" / "unit_animation_assets.py",
              ROOT / "Tests" / "unit_animation.cpp",
              ROOT / "tools" / "verify_unit_animation.py"]
    input_hashes = {}
    for p in inputs:
        target = frozen / p.name
        shutil.copy2(p, target)
        input_hashes[str(p)] = sha(p)
        if sha(target) != input_hashes[str(p)]:
            raise SystemExit("Frozen source copy hash mismatch")
    for name, expected in SDK.items():
        src = BRIDGE_RUN / name
        if sha(src) != expected:
            raise SystemExit(f"Retained SDK dependency hash mismatch: {name}")
        shutil.copy2(src, out / name)
    bridge = BRIDGE_RUN / "ZeroSisGrannyAnimationBridge.dll"
    bridge_hash = sha(bridge)
    shutil.copy2(bridge, out / bridge.name)
    config = BRIDGE_RUN / "GrannyAnimationBridgeTest.exe.config"
    shutil.copy2(config, out / "unit_animation.exe.config")
    (out / "compile.log").write_text("", encoding="utf-8")
    compile_script = out / "compile.cmd"
    compile_script.write_text(
        "@echo off\r\n"
        f'call "{vcvars}" >nul\r\n'
        "if errorlevel 1 exit /b %errorlevel%\r\n"
        f'"{compiler}" /nologo /std:c++17 /EHsc /W4 /WX /DWIN32_LEAN_AND_MEAN /D NOMINMAX /I"{ROOT}" "{ROOT / "Tests" / "unit_animation.cpp"}" /Fe:"{out / "unit_animation.exe"}" /Fo:"{out / "unit_animation.obj"}" /link d3d11.lib dxgi.lib\r\n'
        "exit /b %errorlevel%\r\n", encoding="utf-8")
    built = subprocess.run(["cmd.exe", "/d", "/c", str(compile_script)], cwd=ROOT, text=True, capture_output=True, timeout=120, creationflags=subprocess.CREATE_NO_WINDOW)
    (out / "compile.log").write_text(built.stdout + built.stderr, encoding="utf-8")
    run = None
    if built.returncode == 0:
        SEM_FAILCRITICALERRORS = 0x0001; SEM_NOGPFAULTERRORBOX = 0x0002; SEM_NOOPENFILEERRORBOX = 0x8000
        ctypes.windll.kernel32.SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX | SEM_NOOPENFILEERRORBOX)
        try:
            run = subprocess.run([str(out / "unit_animation.exe"), str(args.v1), str(runtime_package)], cwd=out,
                                 text=True, capture_output=True, timeout=180,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        except subprocess.TimeoutExpired as exc:
            run = exc
    report = {
        "schema": 1, "run_id": args.run_id,
        "status": "PASS_UNIT_ANIMATION" if built.returncode == 0 and run is not None and not isinstance(run, subprocess.TimeoutExpired) and run.returncode == 0 and all(sha(Path(p)) == h for p, h in input_hashes.items()) else "FAIL_UNIT_ANIMATION",
        "source_hashes": input_hashes,
        "source_hashes_after": {p: sha(Path(p)) for p in input_hashes},
        "compiler": str(compiler), "compiler_sha256": sha(compiler),
        "config_sha256": sha(out / "unit_animation.exe.config"),
        "bridge_sha256": bridge_hash,
        "sdk_dependencies": {n: sha(out / n) for n in SDK},
        "v1_package": {"path": str(args.v1), "sha256": sha(args.v1)},
        "v2_package": {"path": str(args.v2), "sha256": sha(args.v2)},
        "runtime_package": {"path": str(runtime_package), "sha256": sha(runtime_package), "embedded_sibling_sha256": embedded_hashes},
        "build_exit": built.returncode,
        "run_exit": None if run is None or isinstance(run, subprocess.TimeoutExpired) else run.returncode,
        "stdout": "" if run is None or isinstance(run, subprocess.TimeoutExpired) else run.stdout,
        "stderr": built.stderr if run is None or isinstance(run, subprocess.TimeoutExpired) else run.stderr,
        "timeout": isinstance(run, subprocess.TimeoutExpired),
        "scope": "native CPU unit package animation integration test; not full engine or in-game animation proof",
    }
    (evidence / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({"status": report["status"], "run_id": args.run_id, "report": str(evidence / "report.json")}, indent=2))
    return 0 if report["status"].startswith("PASS") else 1

if __name__ == "__main__":
    sys.exit(main())
