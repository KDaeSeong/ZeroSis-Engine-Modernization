#!/usr/bin/env python3
"""Build and run focused offscreen WorldView visibility and UnitPanel fallback checks."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

PROJECT = Path(__file__).resolve().parents[1]
SOURCES = (
    PROJECT / "Tests/world_view_visibility.cpp",
    PROJECT / "Source/Presentation/BitmapRenderer.cpp",
    PROJECT / "Source/Presentation/WorldTerrainRenderer.cpp",
    PROJECT / "Source/Presentation/WorldViewRenderer.cpp",
)
HEADERS = (
    PROJECT / "Source/Presentation/BitmapRenderer.h",
    PROJECT / "Source/Presentation/WorldTerrainRenderer.h",
    PROJECT / "Source/Presentation/WorldUnitAssets.h",
    PROJECT / "Source/Presentation/WorldViewRenderer.h",
    PROJECT / "Source/Animation/UnitAnimation.h",
    PROJECT / "Source/Animation/GrannyAnimationBridge.h",
)
VS_DEFAULT = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
WINDOWS_SDK_DEFAULT = Path(r"C:\Program Files (x86)\Windows Kits\10")
PASS_MARKER = (
    "PASS_WORLD_VIEW_VISIBILITY hidden_owned_roster_selected_hud_map_pixels_and_hits_filtered "
    "hidden_foreign_missing_plot_invalid_id_rejected"
)
UNIT_PANEL_PASS_MARKER = (
    "PASS_WORLD_VIEW_UNIT_PANEL_SUPPRESSION false_true_false_ordered_hits_map_pixels_preserved "
    "selected_captions_found_skip_actions_pages_and_empty_notice_removed"
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(command: list[str], *, cwd: Path, env: dict[str, str], stdout_path: Path,
        stderr_path: Path) -> int:
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, encoding="utf-8",
                               errors="replace", capture_output=True, check=False)
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    return completed.returncode


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT / "Build/world_view_visibility")
    parser.add_argument("--vs", type=Path, default=VS_DEFAULT)
    parser.add_argument("--windows-sdk", type=Path, default=WINDOWS_SDK_DEFAULT)
    parser.add_argument("--sdk-version", default="10.0.26100.0")
    args = parser.parse_args(argv)

    for path in (*SOURCES, *HEADERS):
        if not path.is_file():
            parser.error(f"required source file not found: {path}")
    compiler_root = args.vs / "VC/Tools/MSVC/14.44.35207"
    compiler = compiler_root / "bin/Hostx64/x64/cl.exe"
    sdk_include = args.windows_sdk / "Include" / args.sdk_version
    sdk_lib = args.windows_sdk / "Lib" / args.sdk_version
    if not compiler.is_file() or not (sdk_include / "um/d3d11.h").is_file():
        parser.error("the configured MSVC or Windows SDK installation is unavailable")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_root = args.output.resolve()
    session = output_root / stamp
    suffix = 1
    while session.exists():
        session = output_root / f"{stamp}_{suffix}"
        suffix += 1
    build = session / "build"
    captures = session / "captures"
    build.mkdir(parents=True)
    captures.mkdir()
    exe = build / "world_view_visibility.exe"
    env = os.environ.copy()
    env["INCLUDE"] = ";".join(str(path) for path in (
        compiler_root / "include", sdk_include / "um", sdk_include / "shared", sdk_include / "ucrt",
        sdk_include / "winrt", sdk_include / "cppwinrt"))
    env["LIB"] = ";".join(str(path) for path in (
        compiler_root / "lib/x64", sdk_lib / "um/x64", sdk_lib / "ucrt/x64"))
    env["PATH"] = str(compiler.parent) + os.pathsep + env.get("PATH", "")
    command = [str(compiler), "/nologo", "/std:c++17", "/O2", "/W4", "/WX", "/utf-8", "/fp:strict",
               "/EHsc", "/MD", "/DUNICODE", "/D_UNICODE", "/DNOMINMAX", "/DWIN32_LEAN_AND_MEAN",
               "/D_CRT_SECURE_NO_WARNINGS", f"/I{PROJECT / 'Source/Presentation'}",
               f"/Fo{str(build) + os.sep}", f"/Fe{exe}", *(str(path) for path in SOURCES),
               "d3d11.lib", "d3dcompiler.lib", "dxgi.lib", "d2d1.lib", "dwrite.lib",
               "windowscodecs.lib", "ole32.lib", "uuid.lib"]
    compile_stdout, compile_stderr = session / "compile.stdout.log", session / "compile.stderr.log"
    compile_rc = run(command, cwd=PROJECT, env=env, stdout_path=compile_stdout, stderr_path=compile_stderr)
    run_stdout, run_stderr = session / "run.stdout.log", session / "run.stderr.log"
    run_command = [str(exe), str(captures)]
    run_rc = None
    if compile_rc == 0:
        run_rc = run(run_command, cwd=PROJECT, env=env, stdout_path=run_stdout, stderr_path=run_stderr)
    stdout_text = run_stdout.read_text(encoding="utf-8") if run_stdout.exists() else ""
    passed = (compile_rc == 0 and run_rc == 0 and PASS_MARKER in stdout_text and
              UNIT_PANEL_PASS_MARKER in stdout_text and not captures.exists())
    status = "PASS_COMPONENT_CONTRACT" if passed else "FAILED"
    if status == "PASS_COMPONENT_CONTRACT":
        for object_file in build.glob("*.obj"):
            object_file.unlink()
    files = [path for path in session.rglob("*") if path.is_file()]
    manifest = {
        "status": status,
        "scope": "Actual offscreen WorldView PNG pixels and ordered hits: visible/hidden units plus original UnitPanel suppression/fallback; no game, Host runtime, stock UnitPanel rendering, or desktop interaction",
        "session_dir": str(session),
        "compiler": str(compiler),
        "compile_command": command,
        "compile_exit_code": compile_rc,
        "compile_stdout": str(compile_stdout),
        "compile_stderr": str(compile_stderr),
        "run_command": run_command,
        "run_exit_code": run_rc,
        "run_stdout": str(run_stdout),
        "run_stderr": str(run_stderr),
        "pass_marker": PASS_MARKER if status == "PASS_COMPONENT_CONTRACT" else None,
        "unit_panel_pass_marker": UNIT_PANEL_PASS_MARKER if status == "PASS_COMPONENT_CONTRACT" else None,
        "unit_panel_contract": {
            "default_fallback_false_true_false": True,
            "suppressed": ["selected_unit_caption", "moves_health_caption", "Found", "Skip",
                           "unit_action_title", "six_visible_actions", "both_page_buttons", "empty_action_notice"],
            "preserved": ["all_other_pixels", "map_viewport", "ordered_hit_bounds", "plot_selection",
                          "owned_unit", "owned_city", "NextUnit", "EndTurn", "Save", "Close",
                          "Research", "Production", "four_camera_arrows", "city_and_status_text"],
            "oracle": "Decoded 1920x1080 real renderer output; removed regions become rendered HUD background, all pixels outside those regions and ordered retained hits remain identical; returning to fallback restores identical pixels and hits",
            "executed_pass": status == "PASS_COMPONENT_CONTRACT",
        },
        "temporary_captures_removed": not captures.exists(),
        "sources": [{"path": str(path), "sha256": digest(path)} for path in (*SOURCES, *HEADERS)],
        "executable": ({"path": str(exe), "sha256": digest(exe)} if exe.is_file() else None),
        "retained_files": [{"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}
                           for path in files],
    }
    report_path = session / "result.json"
    report_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": status, "report": str(report_path)}, ensure_ascii=False))
    return 0 if status == "PASS_COMPONENT_CONTRACT" else 1


if __name__ == "__main__":
    raise SystemExit(main())
