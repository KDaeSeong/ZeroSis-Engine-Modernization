"""Compile and exercise terrain patch placement on an offscreen D3D11 software device."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

PROJECT = Path(__file__).resolve().parents[1]
PRESENTATION = PROJECT / "Source/Presentation"
EVIDENCE = PROJECT / "evidence/world_terrain_original/patch_placement"
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT / "tools"))
sys.path.insert(0, str(EVIDENCE))
from civ5_original_terrain_assets import prepare
from civ5_original_water_assets import prepare as prepare_water
from civ5_original_water_lean_assets import prepare as prepare_water_surface
from native_build import checked_run, environment_for
from verify_retail_patch_layout import verify

SOURCES = [PROJECT / "Tests/original_terrain_patch_world.cpp",
           PRESENTATION / "BitmapRenderer.cpp", PRESENTATION / "WorldViewRenderer.cpp",
           PRESENTATION / "WorldTerrainRenderer.cpp"]
PACKAGE_SHA = "02104c582759bf0cefb58f97379699e45300eb2a9c6da6fdd3c65d1440cb84e8"


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game", required=True, type=Path, help="Local Civilization V installation")
    parser.add_argument("--vs", type=Path, default=Path("C:/Program Files/Microsoft Visual Studio/2022/Community"))
    args = parser.parse_args()
    game = args.game.resolve(strict=True)
    retail = verify(game / "CivilizationV_DX11.exe")
    pack = prepare(game, PROJECT / "Build/OriginalTerrainAssets")
    package = Path(pack["package_path"])
    assert pack["package_sha256"] == PACKAGE_SHA
    water = prepare_water(game, PROJECT / "Build/OriginalWaterAssets")["package"]
    surface = prepare_water_surface(game, PROJECT / "Build/OriginalWaterLeanAssets")["package"]
    work_root = PROJECT / "Build/TerrainPatchPlacement"
    work_root.mkdir(parents=True, exist_ok=True)
    assert work_root.resolve() == work_root
    modes = []
    with tempfile.TemporaryDirectory(dir=work_root) as directory:
        work = Path(directory).resolve()
        assert work.parent == work_root
        env, compiler = environment_for(args.vs, "x64", work)
        for mode in ("/O2", "/Od"):
            exe = work / ("patch_" + mode[1:] + ".exe")
            command = [compiler, "/nologo", "/std:c++17", mode, "/W4", "/WX", "/utf-8", "/fp:strict", "/EHsc", "/MD",
                       "/DUNICODE", "/D_UNICODE", "/DNOMINMAX", "/DWIN32_LEAN_AND_MEAN", "/D_CRT_SECURE_NO_WARNINGS",
                       "/I" + str(PRESENTATION), "/Fe" + str(exe), *SOURCES, "/link", "/INCREMENTAL:NO", "/WX",
                       "d3d11.lib", "d3dcompiler.lib", "dxgi.lib", "d2d1.lib", "dwrite.lib", "windowscodecs.lib",
                       "ole32.lib", "uuid.lib"]
            checked_run(command, cwd=work, env=env, timeout=240)
            execution = checked_run([exe, package, water["path"], surface["path"]], cwd=work, env=env, timeout=180)
            output = execution.stdout.decode("ascii").strip()
            assert output.startswith("PASS_TERRAIN_PATCH_WORLD ") and not execution.stderr, output
            print(mode, output, flush=True)
            modes.append({"mode": mode, "result": output})
    tracked_inputs = [*SOURCES, Path(__file__).resolve(), EVIDENCE / "verify_retail_patch_layout.py"]
    tracked_inputs.extend(PRESENTATION / name for name in (
        "OriginalTerrainGeometry.h", "OriginalTerrainPatchPlacement.h", "OriginalTerrainLod.h", "WorldTerrainRenderer.h", "OriginalTerrainTessellationModel.h",
        "OriginalTerrainTessellationShader.h", "OriginalTerrainGpu.inc", "OriginalTerrainGpuTypes.inc",
        "OriginalDynamicShadowGpu.inc", "OriginalDynamicShadowGpuTypes.inc", "OriginalDynamicShadowShader.h"))
    stamp = datetime.now(timezone.utc)
    report = EVIDENCE / ("world_" + stamp.strftime("%Y%m%dT%H%M%S%fZ") + ".json")
    record = {"status": "PASS_TERRAIN_PATCH_WORLD_WARP", "finished_utc": stamp.isoformat(), "compiler": str(compiler),
              "git_base": subprocess.check_output(["git","rev-parse","HEAD"],cwd=PROJECT,text=True).strip(),
              "retail_layout": retail, "package_sha256": PACKAGE_SHA, "modes": modes, "physical_gpu": False,
              "water_sha256": water["sha256"], "water_surface_sha256": surface["sha256"],
              "window_or_gamecore": False, "source_sha256": {p.relative_to(PROJECT).as_posix(): digest(p) for p in tracked_inputs}}
    with report.open("x", encoding="utf8", newline="\n") as stream:
        json.dump(record, stream, indent=2)
        stream.write("\n")
    print(report)


if __name__ == "__main__":
    main()
