#!/usr/bin/env python3
"""Compile and run isolated Civ V terrain and full WorldView D3D11 parity fixtures."""
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
    PROJECT / "Tests/world_terrain_renderer.cpp",
    PROJECT / "Source/Presentation/BitmapRenderer.cpp",
    PROJECT / "Source/Presentation/WorldTerrainRenderer.cpp",
    PROJECT / "Source/Presentation/WorldViewRenderer.cpp",
)
HEADERS = (PROJECT / "Source/Presentation/WorldTerrainRenderer.h",
           PROJECT / "Source/Presentation/WorldUnitAssets.h",
           PROJECT / "Source/Presentation/WorldViewRenderer.h",
           PROJECT / "Source/Presentation/BitmapRenderer.h",
           PROJECT / "Source/Animation/UnitAnimation.h",
           PROJECT / "Source/Animation/GrannyAnimationBridge.h",
           PROJECT / "tools/unit_animation_assets.py")
WINDOWS_SDK_DEFAULT = Path(r"C:\Program Files (x86)\Windows Kits\10")
VS_DEFAULT = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")


def digest(path: Path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def run(command, *, cwd, env, stdout_path, stderr_path):
    completed = subprocess.run(command, cwd=cwd, env=env, text=True, encoding="utf-8",
                               errors="replace", capture_output=True, check=False)
    stdout_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    return completed.returncode


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path, help="Content-addressed terrain-assets.bin")
    parser.add_argument("--unit-package", type=Path, help="Optional prepared original unit-assets.bin")
    parser.add_argument("--reuse-build", type=Path, help="Reuse a passing component binary after exact source and EXE hash checks")
    parser.add_argument("--output", type=Path, default=PROJECT / "Build/terrain_renderer_validation")
    parser.add_argument("--vs", type=Path, default=VS_DEFAULT)
    parser.add_argument("--windows-sdk", type=Path, default=WINDOWS_SDK_DEFAULT)
    parser.add_argument("--sdk-version", default="10.0.26100.0")
    args = parser.parse_args(argv)
    package = args.package.resolve(strict=True)
    require_inputs = (*SOURCES, *HEADERS, package)
    for path in require_inputs:
        if not path.is_file():
            parser.error(f"required file not found: {path}")
    compiler_root = args.vs / "VC/Tools/MSVC/14.44.35207"
    compiler = compiler_root / "bin/Hostx64/x64/cl.exe"
    sdk = args.windows_sdk
    um_include = sdk / "Include" / args.sdk_version
    um_lib = sdk / "Lib" / args.sdk_version
    if not compiler.is_file() or not (um_include / "um/d3d11.h").is_file():
        parser.error("the configured MSVC or Windows SDK installation is unavailable")
    output_root = args.output.resolve()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    session = output_root / stamp
    if session.exists():
        suffix = 1
        while (output_root / f"{stamp}_{suffix}").exists():
            suffix += 1
        session = output_root / f"{stamp}_{suffix}"
    session.mkdir(parents=True)
    source_copy = session / "sources"
    source_copy.mkdir()
    source_artifacts = []
    for path in require_inputs[:-1]:
        target = source_copy / path.name
        target.write_bytes(path.read_bytes())
        source_artifacts.append({"source": str(path), "copy": str(target), "sha256": digest(path),
                                 "copied_sha256": digest(target)})
    build = session / "build"
    build.mkdir()
    obj = build / "obj"
    obj.mkdir()
    exe = build / "world_terrain_renderer.exe"
    package_hash = digest(package)
    env = os.environ.copy()
    env["INCLUDE"] = ";".join(str(item) for item in (
        compiler_root / "include", um_include / "um", um_include / "shared", um_include / "ucrt",
        um_include / "winrt", um_include / "cppwinrt"))
    env["LIB"] = ";".join(str(item) for item in (
        compiler_root / "lib/x64", um_lib / "um/x64", um_lib / "ucrt/x64"))
    env["PATH"] = str(compiler.parent) + os.pathsep + env.get("PATH", "")
    command = [str(compiler), "/nologo", "/std:c++17", "/O2", "/W4", "/WX", "/utf-8", "/fp:strict", "/EHsc", "/MD",
               "/DUNICODE", "/D_UNICODE", "/DNOMINMAX", "/DWIN32_LEAN_AND_MEAN", "/D_CRT_SECURE_NO_WARNINGS",
               f"/I{PROJECT / 'Source/Presentation'}", f"/Fo{str(obj) + os.sep}", f"/Fe{exe}",
               *(str(path) for path in SOURCES), "d3d11.lib", "d3dcompiler.lib", "dxgi.lib", "d2d1.lib",
               "dwrite.lib", "windowscodecs.lib", "ole32.lib", "uuid.lib"]
    compile_stdout, compile_stderr = session / "compile.stdout.log", session / "compile.stderr.log"
    reused = None
    if args.reuse_build:
        prior_path = args.reuse_build.resolve(strict=True)
        prior = json.loads(prior_path.read_text(encoding='utf8'))
        if prior.get('status') != 'PASS_COMPONENT_CONTRACT' or prior.get('compile_exit_code') != 0:
            raise ValueError('Reuse requires a passing compiled component')
        expected = {str(path.resolve()): digest(path) for path in (*SOURCES, *HEADERS)}
        recorded = {str(Path(row['source']).resolve()): row['sha256'] for row in prior['sources']}
        if expected != recorded or any(digest(Path(row['copy'])) != row['sha256'] for row in prior['sources']):
            raise ValueError('Retained component source differs from current or frozen inputs')
        exe = Path(prior['executable']).resolve(strict=True)
        if digest(exe) != prior['executable_sha256']:
            raise ValueError('Retained component binary changed')
        command = prior['command']
        compile_rc = 0
        compile_stdout.write_text('Reused exact retained component binary; no compiler invoked.\n', encoding='utf8')
        compile_stderr.write_text('', encoding='utf8')
        reused = {'path': str(prior_path), 'sha256': digest(prior_path),
                  'executable': {'path': str(exe), 'sha256': digest(exe)}}
    else:
        compile_rc = run(command, cwd=PROJECT, env=env, stdout_path=compile_stdout, stderr_path=compile_stderr)
    manifest = {"status": "BUILD_FAILED" if compile_rc else "BUILT", "session_dir": str(session),
                "scope": "terrain and full WorldView/HUD rendering through legacy PNG and caller-owned same-device D3D11 target; no game or Host runtime",
                "compiler": str(compiler), "compiler_flags": ["/std:c++17", "/O2", "/W4", "/WX", "/utf-8", "/fp:strict"],
                "command": command, "compile_exit_code": compile_rc,
                "compile_stdout": str(compile_stdout), "compile_stderr": str(compile_stderr),
                "package": {"path": str(package), "sha256": package_hash}, "sources": source_artifacts,
                "executable": str(exe) if exe.exists() else None}
    if reused:
        manifest['reused_build'] = reused
    if compile_rc == 0:
        capture_dir = session / "captures"
        capture_dir.mkdir()
        run_command = [str(exe), str(package), str(capture_dir)]
        private_unit_runtime = None
        unit_package_is_v2 = False
        if args.unit_package:
            unit_package = args.unit_package.resolve(strict=True)
            unit_package_sha = digest(unit_package)
            with unit_package.open('rb') as stream:
                package_header = stream.read(12)
            unit_package_is_v2 = package_header == b'ZSUNIT02\x02\0\0\0'
            manifest['unit_package'] = {'path': str(unit_package), 'sha256': unit_package_sha,
                                        'format': 'ZSUNIT02 v2' if unit_package_is_v2 else 'ZSUNIT01 v1'}
            run_unit_package = unit_package
            if unit_package_is_v2:
                from runtime_input_cache import materialize_immutable
                from unit_animation_assets import materialize as materialize_unit_animation
                runtime_dir = exe.parent.resolve(strict=True)
                animation, materialized_rows, cache_methods = materialize_unit_animation(
                    unit_package, runtime_dir, materialize_immutable)
                private_package = runtime_dir / 'unit-assets.bin'
                with private_package.open('xb') as stream:
                    with unit_package.open('rb') as source_stream:
                        while True:
                            block = source_stream.read(1024 * 1024)
                            if not block:
                                break
                            stream.write(block)
                if digest(private_package) != unit_package_sha:
                    raise ValueError('Private v2 unit package copy hash mismatch')
                test_config = Path(str(exe) + '.config')
                config_source = Path(animation['config']['path'])
                test_config.write_bytes(config_source.read_bytes())
                if digest(test_config) != animation['config']['sha256']:
                    raise ValueError('Component executable CLR config hash mismatch')
                private_unit_runtime = {'package': {'path': str(private_package), 'sha256': unit_package_sha,
                                                     'bytes': private_package.stat().st_size},
                    'animation': animation, 'materialized_files': materialized_rows,
                    'cache_methods': cache_methods,
                    'test_executable_config': {'path': str(test_config), 'sha256': digest(test_config),
                                               'bytes': test_config.stat().st_size}}
                run_unit_package = private_package
            run_command.append(str(run_unit_package))
        stdout_path, stderr_path = session / "run.stdout.log", session / "run.stderr.log"
        run_rc = run(run_command, cwd=PROJECT, env=env, stdout_path=stdout_path, stderr_path=stderr_path)
        gpu_marker = "PASS_TERRAIN_GPU_TARGET_CONTRACT color_bytes_preserved id_projection_parity resized_and_foreign_targets_rejected"
        world_marker = "PASS_WORLD_VIEW_GPU_CONTRACT exact_hits_pixel_ids_city_spans_bounded_edge_png_difference"
        run_output = stdout_path.read_text(encoding="utf-8")
        world_pixel_stats = []
        for line in run_output.splitlines():
            if not line.startswith("WORLD_VIEW_PIXEL_PARITY "):
                continue
            fields = dict(token.split("=", 1) for token in line.split()[1:] if "=" in token)
            if not fields:
                continue
            for key in ("differing_pixels", "differing_channel_bytes", "max_channel_delta",
                        "total_rgb_delta", "rgb_channel_count", "differing_pixel_limit",
                        "matched_unit_marker_ellipses", "ellipse_annulus_diff_pixels",
                        "ellipse_annulus_delta_gt16_pixels", "max_outside_ellipse_delta",
                        "max_ellipse_annulus_delta"):
                if key in fields:
                    fields[key] = int(fields[key])
            for key in ("alpha_exact", "reference_3x3_edge_only", "within_limits"):
                if key in fields:
                    fields[key] = fields[key] == "true"
            world_pixel_stats.append(fields)
        world_pixel_self_checks = []
        for line in run_output.splitlines():
            if not line.startswith("WORLD_VIEW_PIXEL_SELF_CHECK "):
                continue
            fields = dict(token.split("=", 1) for token in line.split()[1:] if "=" in token)
            for key in ("accepted", "edge_only", "alpha_exact"):
                if key in fields:
                    fields[key] = fields[key] == "true"
            for key in ("differing_pixels", "pixel_limit", "outside_max_delta", "annulus_max_delta"):
                if key in fields:
                    fields[key] = int(fields[key])
            world_pixel_self_checks.append(fields)
        self_check_names = {row.get("name") for row in world_pixel_self_checks}
        pixel_self_checks_valid = (len(world_pixel_self_checks) == 7 and
                                   len(self_check_names) == 7 and
                                   all(row.get("accepted") == (row.get("expected") == "accept")
                                       for row in world_pixel_self_checks) and
                                   "PASS_WORLD_VIEW_PIXEL_COMPARATOR_SELF_CHECK cases=7" in run_output)
        expected_world_pixel_runs = (6 if unit_package_is_v2 else 3) if args.unit_package else 1
        pixel_stats_valid = (len(world_pixel_stats) == expected_world_pixel_runs and
                             all(row.get("name") and row.get("within_limits") is True and
                                 row.get("alpha_exact") is True and row.get("reference_3x3_edge_only") is True and
                                 isinstance(row.get("max_outside_ellipse_delta"), int) and
                                 row.get("max_outside_ellipse_delta") <= 16 and
                                 isinstance(row.get("max_ellipse_annulus_delta"), int) and
                                 row.get("max_ellipse_annulus_delta") <= 64
                                 for row in world_pixel_stats))
        animation_contract = (not unit_package_is_v2 or
                              'PASS_ORIGINAL_WARRIOR_ANIMATION_CONTRACT t05_changed t1_changed loop_exact' in run_output)
        gpu_contract = (run_rc == 0 and gpu_marker in run_output and world_marker in run_output and
                        animation_contract and
                        pixel_stats_valid and pixel_self_checks_valid)
        captures = []
        for path in sorted(capture_dir.iterdir()):
            if path.is_file():
                captures.append({"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)})
        manifest.update({"status": "PASS_COMPONENT_CONTRACT" if gpu_contract else "RUNTIME_FAILED",
                         "run_command": run_command, "run_exit_code": run_rc,
                         "run_stdout": str(stdout_path), "run_stderr": str(stderr_path),
                         "gpu_target_contract_marker": gpu_marker if gpu_contract else None,
                         "full_world_view_gpu_contract_marker": world_marker if gpu_contract else None,
                         "original_unit_and_depth_parity_tested": bool(args.unit_package),
                         "original_unit_animation_tested": unit_package_is_v2 and animation_contract,
                         "private_unit_runtime": private_unit_runtime,
                         "gpu_contract_note": "Caller target color bytes, exact ID raster and projected contour/anchor parity, dimension/device mismatch rejection, plus full WorldView/HUD legacy-vs-GPU hit records, pixel IDs, city projection spans and bounded reference-edge PNG differences; optional unit package adds original-model/depth WorldView parity.",
                         "full_world_png_parity_policy": {
                             "scope": "Full WorldView/HUD CPU WIC PNG versus caller-owned GPU target capture only",
                             "alpha": "exact",
                             "edge_rule": "Every differing pixel must have at least one RGB channel with a value range of 16 or greater inside its legacy reference 3x3 neighborhood",
                             "unit_marker_mask": {
                                 "center": "center of an exactly matched legacy OwnedUnit hit rectangle",
                                 "physical_radii": [6.3, 7.95],
                                 "stroke_half_width_physical": "selected 1.5; unselected 0.75",
                                 "annulus_formula": "abs(normalizedRadius - 1) * min(rx, ry) <= strokeHalfWidth + 1 physical pixel",
                                 "maximum_per_channel_delta_inside_annulus": 64,
                                 "maximum_per_channel_delta_outside_annulus": 16
                             },
                             "maximum_differing_pixel_ratio": 0.001,
                             "maximum_total_absolute_rgb_delta_ratio": 0.01,
                             "threshold_status": "Selected fixture limits; these values are not guaranteed by Direct2D",
                             "exact_contracts_preserved": ["terrain target color bytes", "original unit geometry parity",
                                                            "ID raster", "UI hits and scrolls", "camera projection and city spans"],
                             "statistics": world_pixel_stats,
                             "negative_comparator_self_checks": world_pixel_self_checks
                         },
                         "captures": captures, "executable_sha256": digest(exe)})
    source_unchanged = True
    for artifact in source_artifacts:
        artifact["sha256_after"] = digest(Path(artifact["source"]))
        artifact["copied_sha256_after"] = digest(Path(artifact["copy"]))
        artifact["unchanged"] = artifact["sha256"] == artifact["sha256_after"] == artifact["copied_sha256"] == artifact["copied_sha256_after"]
        source_unchanged = source_unchanged and artifact["unchanged"]
    manifest["source_inputs_unchanged"] = source_unchanged
    if not source_unchanged:
        manifest["status"] = "SOURCE_INPUT_CHANGED"
    manifest_path = session / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": manifest["status"], "session_dir": str(session),
                      "manifest_path": str(manifest_path), "package_path": str(package),
                      "package_sha256": package_hash, "executable": manifest["executable"]},
                     ensure_ascii=False, separators=(",", ":")))
    return 0 if manifest["status"] == "PASS_COMPONENT_CONTRACT" else 1


if __name__ == "__main__":
    sys.exit(main())
