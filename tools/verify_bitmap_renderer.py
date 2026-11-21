"""Build and retain offline Direct2D/WIC bitmap renderer checks."""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import struct
import sys

from collect_baseline import PROJECT
from native_build import environment_for, run

VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
OWNED = {
    "header": PROJECT / "Source/Presentation/BitmapRenderer.h",
    "renderer": PROJECT / "Source/Presentation/BitmapRenderer.cpp",
    "test": PROJECT / "Tests/bitmap_renderer.cpp",
    "verifier": Path(__file__).resolve(),
}
LIBRARIES = ("d2d1.lib", "windowscodecs.lib", "ole32.lib")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def allocate() -> tuple[str, Path, Path]:
    build_root = PROJECT / "Build/BitmapRenderer"
    evidence_root = PROJECT / "evidence/bitmap_renderer"
    build_root.mkdir(parents=True, exist_ok=True)
    evidence_root.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(6)
        build, evidence = build_root / run_id, evidence_root / run_id
        try:
            build.mkdir(exist_ok=False)
            evidence.mkdir(exist_ok=False)
            return run_id, build, evidence
        except FileExistsError:
            continue
    raise RuntimeError("Could not allocate a unique renderer evidence ID")


def parse_dependencies(document: Path, source: Path) -> list[Path]:
    data = json.loads(document.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Malformed sourceDependencies document: {document}")
    data = data.get("Data", data)
    if not isinstance(data, dict) or not isinstance(data.get("Includes"), list):
        raise RuntimeError(f"sourceDependencies has no Includes array: {document}")
    result, seen = [], set()
    for raw in [data.get("Source", str(source)), *data["Includes"]]:
        if not isinstance(raw, str) or not raw:
            raise RuntimeError("Compiler returned an invalid include path")
        path = Path(raw)
        if not path.is_absolute():
            path = source.parent / path
        path = path.resolve(strict=True)
        key = str(path).casefold()
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def compile_binary(compiler: str, env: dict, directory: Path, name: str,
                   sources: list[Path], optimization: str, defines=()) -> tuple[dict, str]:
    linker = shutil.which("link.exe", path=env.get("PATH"))
    if not linker:
        raise RuntimeError("MSVC linker is unavailable")
    common = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", optimization,
              "/MD", "/fp:strict", "/DWIN32", "/D_WIN32_WINNT=0x0A00", "/DNOMINMAX",
              "/DWIN32_LEAN_AND_MEAN"] + [f"/D{value}" for value in defines]
    objects, tus, logs = [], [], []
    for index, source in enumerate(sources):
        obj = directory / f"{name}_{index}.obj"
        rsp = directory / f"{name}_{index}.rsp"
        dep = directory / f"{name}_{index}.sourceDependencies.json"
        flags = [*common, "/c", f'"{source}"', f'/Fo"{obj}"', f'/sourceDependencies "{dep}"']
        rsp.write_text("\n".join(flags) + "\n", encoding="utf-8", newline="\n")
        result = run([compiler, f"@{rsp}"], cwd=directory, env=env, timeout=180)
        output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
        log = directory / f"{name}_{index}.compile.log"
        log.write_text(output, encoding="utf-8", newline="\n")
        logs.append(output)
        if result.returncode or re.search(r"\bwarning\s+C\d+", output, re.I):
            raise RuntimeError(f"{name} compilation failed or warned ({result.returncode}):\n{output[-6000:]}")
        if not obj.is_file() or not dep.is_file():
            raise RuntimeError(f"MSVC omitted object or sourceDependencies output for {source}")
        deps = parse_dependencies(dep, source)
        objects.append(obj)
        tus.append({"source": str(source), "source_sha256": sha(source),
                    "response_file": str(rsp), "response_file_sha256": sha(rsp),
                    "arguments": flags, "object": str(obj), "object_sha256": sha(obj),
                    "dependency_document": str(dep), "dependency_document_sha256": sha(dep),
                    "dependencies": [str(p) for p in deps], "compile_log": str(log),
                    "compile_log_sha256": sha(log)})
    exe = directory / f"{name}.exe"
    link_rsp = directory / f"{name}.link.rsp"
    link_flags = [*(f'"{obj}"' for obj in objects), f'/OUT:"{exe}"', "/INCREMENTAL:NO",
                  "/MACHINE:X64", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF", "/SUBSYSTEM:CONSOLE",
                  "/VERBOSE:LIB", *LIBRARIES]
    link_rsp.write_text("\n".join(link_flags) + "\n", encoding="utf-8", newline="\n")
    linked = run([linker, f"@{link_rsp}"], cwd=directory, env=env, timeout=180)
    link_output = (linked.stdout + linked.stderr).decode("mbcs", errors="replace")
    link_log = directory / f"{name}.link.log"
    link_log.write_text(link_output, encoding="utf-8", newline="\n")
    logs.append(link_output)
    if linked.returncode or re.search(r"\bwarning\s+(?:C|LNK)\d+", link_output, re.I):
        raise RuntimeError(f"{name} link failed or warned ({linked.returncode}):\n{link_output[-6000:]}")
    if not exe.is_file():
        raise RuntimeError(f"Linker omitted executable {exe}")
    loaded = {}
    for line in link_output.splitlines():
        for library in LIBRARIES:
            match = re.search(r"([A-Za-z]:\\.*?" + re.escape(library) + r")", line, re.I)
            if match:
                path = Path(match.group(1).strip('" ').replace('\\\\', '\\'))
                if path.is_file():
                    loaded.setdefault(path.name.casefold(), path.resolve())
    if set(loaded) != {x.casefold() for x in LIBRARIES}:
        raise RuntimeError(f"Could not freeze all resolved renderer SDK libraries: {loaded}")
    record = {"optimization": optimization, "compiler": str(Path(compiler).resolve()),
              "compiler_sha256": sha(Path(compiler).resolve()), "linker": str(Path(linker).resolve()),
              "linker_sha256": sha(Path(linker).resolve()), "link_response": str(link_rsp),
              "link_response_sha256": sha(link_rsp), "link_arguments": link_flags,
              "link_log": str(link_log), "link_log_sha256": sha(link_log),
              "resolved_libraries": {name: {"path": str(path), "sha256": sha(path)} for name, path in loaded.items()},
              "translation_units": tus, "executable": str(exe), "executable_sha256": sha(exe)}
    return record, "\n".join(logs)


def freeze_dependencies(records: list[dict], frozen_root: Path) -> tuple[list[dict], dict[str, str]]:
    paths = {}
    for record in records:
        for tu in record["translation_units"]:
            for raw in tu["dependencies"]:
                path = Path(raw).resolve(strict=True)
                paths.setdefault(str(path).casefold(), path)
    copied, live_hashes = [], {}
    for path in sorted(paths.values(), key=lambda p: str(p).casefold()):
        digest = sha(path)
        live_hashes[str(path)] = digest
        try:
            path.relative_to(frozen_root.resolve())
            target = path
        except ValueError:
            key = hashlib.sha256(str(path).casefold().encode("utf-8")).hexdigest()[:20]
            target = frozen_root / "dependencies" / f"{key}_{path.name}"
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        if sha(target) != digest:
            raise RuntimeError(f"Frozen compiler dependency differs: {path}")
        copied.append({"original_path": str(path), "sha256": digest,
                       "frozen_path": str(target), "frozen_sha256": sha(target)})
    return copied, live_hashes


def write_cli_packet(path: Path) -> None:
    data = bytearray(b"ZSUPIX01")
    data += struct.pack("<5I", 8, 8, 0, 1, 1)
    data += struct.pack("<IQ16f", 0xFFFFFFFF, 0x4142,
                        0, 0, 1, 1, 0, 0, 8, 8, 0, 0, 8, 8, 0.25, 0.5, 1, 1)
    data += struct.pack("<Q4f", 0x4142, 0, 0, 8, 8)
    path.write_bytes(data)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    args = parser.parse_args()
    missing = [str(path) for path in OWNED.values() if not path.is_file()]
    if missing:
        raise RuntimeError("Renderer source input is missing: " + ", ".join(missing))
    before = {key: sha(path) for key, path in OWNED.items()}
    run_id, build_root, evidence = allocate()
    frozen = build_root / "frozen"
    for key, path in OWNED.items():
        target = frozen / path.relative_to(PROJECT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        if sha(target) != before[key]:
            raise RuntimeError(f"Frozen source differs: {key}")
    frozen_owned = {key: frozen / path.relative_to(PROJECT) for key, path in OWNED.items()}
    result = {"schema": "zerosis.bitmap_renderer_conformance.v1", "run_id": run_id,
              "status": "RUNNING", "scope": "offline_Direct2D_WIC_pixel_rendering_only",
              "gamecore_loaded": False, "sdk_linked": False, "wpr_capture_started": False,
              "stage_promoted": False, "mods_written": False, "performance_improvement_verified": False,
              "source_hashes_before": before, "source_hashes_after": None,
              "frozen_inputs": {}, "compiler_dependencies": [], "compiler_dependency_hashes_before": None,
              "compiler_dependency_hashes_after": None, "builds": {}, "test_runs": [],
              "renderer_artifact": None, "cli_packet": None, "cli_png": None,
              "environment_setup": None, "error": None}
    try:
        for key, path in frozen_owned.items():
            result["frozen_inputs"][key] = {"path": str(path), "sha256": sha(path)}
        build_records = []
        for opt in ("/O2", "/Od"):
            label = opt[1:]
            directory = build_root / label
            directory.mkdir()
            env, compiler = environment_for(VS, "x64", directory)
            env.pop("ZEROSIS_FOUND_VALUE_CPU_TRACE", None)
            setup = directory / "read_build_environment.cmd"
            result["environment_setup"] = {"path": str(setup), "sha256": sha(setup),
                                           "compiler": str(Path(compiler).resolve()),
                                           "compiler_sha256": sha(Path(compiler).resolve())}
            test_dir = evidence / "test_inputs" / label
            test_dir.mkdir(parents=True)
            record, _ = compile_binary(compiler, env, directory, f"bitmap_renderer_{label}",
                                       [frozen_owned["test"], frozen_owned["renderer"]], opt)
            build_records.append(record)
            test_result = run([record["executable"], "--artifact-dir", str(test_dir)],
                              cwd=directory, env=env, timeout=60)
            output = (test_result.stdout + test_result.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
            log = evidence / f"test_{label}.log"
            log.write_text(output, encoding="utf-8", newline="\n")
            if test_result.returncode or output.strip() != "PASS|39|D2D/WIC alpha8, RGBA32, BC1/2/3, tint, clip, PNG, and strict ZSUPIX01/02 packet checks":
                raise RuntimeError(f"{label} native pixel tests failed ({test_result.returncode}):\n{output[-4000:]}")
            result["test_runs"].append({"optimization": opt, "status": output.strip(),
                                        "checks": 33, "capture_started": False,
                                        "gamecore_loaded": False, "log": str(log), "log_sha256": sha(log),
                                        "retained_inputs": [str(p) for p in sorted(test_dir.iterdir()) if p.is_file()]})
            result["builds"][label] = record

        cli_dir = build_root / "cli_o2"
        cli_dir.mkdir()
        env, compiler = environment_for(VS, "x64", cli_dir)
        cli_record, _ = compile_binary(compiler, env, cli_dir, "BitmapRenderer",
                                       [frozen_owned["renderer"]], "/O2", ("ZEROSIS_BITMAP_RENDERER_CLI",))
        build_records.append(cli_record)
        packet = evidence / "cli_scene.packet"
        png = evidence / "cli_scene.png"
        write_cli_packet(packet)
        executed = run([cli_record["executable"], str(packet), str(png)], cwd=cli_dir, env=env, timeout=30)
        cli_output = (executed.stdout + executed.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
        cli_log = evidence / "cli_run.log"
        cli_log.write_text(cli_output, encoding="utf-8", newline="\n")
        if executed.returncode or cli_output.strip() != "BITMAP_RENDER_PASS width=8 height=8 sprites=1 textures=0 hits=1 scope=OFFSCREEN_D2D_WIC":
            raise RuntimeError(f"Renderer CLI packet smoke failed ({executed.returncode}): {cli_output[-3000:]}")
        png_data = png.read_bytes()
        if len(png_data) < 24 or png_data[:8] != b"\x89PNG\r\n\x1a\n" or struct.unpack(">II", png_data[16:24]) != (8, 8):
            raise RuntimeError("Renderer CLI did not produce a valid 8x8 PNG")
        result["renderer_artifact"] = cli_record
        result["cli_packet"] = {"path": str(packet), "sha256": sha(packet), "size": packet.stat().st_size}
        result["cli_png"] = {"path": str(png), "sha256": sha(png), "size": png.stat().st_size,
                             "width": 8, "height": 8}
        result["cli_log"] = {"path": str(cli_log), "sha256": sha(cli_log)}
        deps, dep_before = freeze_dependencies(build_records, frozen)
        dep_after = {path: sha(Path(path)) for path in dep_before}
        if dep_before != dep_after:
            raise RuntimeError("Compiler dependency changed during the retained build")
        library_records = {}
        for record in build_records:
            for name, library in record["resolved_libraries"].items():
                prior = library_records.get(name)
                if prior and prior["sha256"] != library["sha256"]:
                    raise RuntimeError(f"Resolved library changed across isolated builds: {name}")
                target = frozen / "libraries" / Path(library["path"]).name
                target.parent.mkdir(parents=True, exist_ok=True)
                if not target.exists():
                    shutil.copy2(library["path"], target)
                if sha(target) != library["sha256"]:
                    raise RuntimeError(f"Frozen linker library differs: {name}")
                library_records[name] = {"original_path": library["path"], "sha256": library["sha256"],
                                         "frozen_path": str(target), "frozen_sha256": sha(target)}
        after = {key: sha(path) for key, path in OWNED.items()}
        if before != after:
            raise RuntimeError("Renderer sources changed during the retained build")
        result.update({"status": "BITMAP_RENDERER_COMPONENT_PASS", "source_hashes_after": after,
                       "source_inputs_unchanged": True, "compiler_dependencies": deps,
                       "compiler_dependency_hashes_before": dep_before,
                       "compiler_dependency_hashes_after": dep_after,
                       "resolved_libraries": library_records,
                       "source_dependency_count": len(deps),
                       "scope_claim": "software offscreen Direct2D composition with WIC decode/PNG; component fixtures only; no retail UI capture"})
    except Exception as error:
        result["error"] = str(error)
        result["status"] = "BITMAP_RENDERER_COMPONENT_FAILED"
        result["source_hashes_after"] = {key: sha(path) for key, path in OWNED.items() if path.is_file()}
    report = evidence / "conformance.json"
    with report.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    print(json.dumps({"status": result["status"], "run_id": run_id,
                      "report": str(report), "report_sha256": sha(report), "error": result["error"]},
                     ensure_ascii=False))
    return 0 if result["status"] == "BITMAP_RENDERER_COMPONENT_PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
