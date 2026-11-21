"""Build the actual pure camera controls at /O2 and /Od; no Host, GameCore or window."""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
from native_build import environment_for, run
from collect_baseline import pe_header

PROJECT = Path(__file__).resolve().parents[1]
SCOPE = PROJECT / "evidence/world_camera/controls/scope.json"
SCOPE_SHA = "781f1f34837d12d54b6b6cc2dcdb2e88c9f4c341aa3130f26285c7b9e70db4c2"
RELATIVE_INPUTS = (
    "Tests/world_camera_controls.cpp", "Source/Presentation/WorldCameraControls.h",
    "Source/Host/InteractiveGameLoop.h", "Source/Presentation/WorldViewRenderer.h",
    "Source/Presentation/WorldViewRenderer.cpp", "Source/Presentation/WorldTerrainRenderer.cpp",
    "tools/verify_world_camera_controls.py", "tools/native_build.py", "tools/collect_baseline.py",
)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def artifact(path):
    path = Path(path)
    with path.open("rb") as stream:
        sha = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha}


def mask_cpp(text):
    # Preserve offsets/newlines while removing comments and quoted strings.
    pattern = r'R"([^ ()\\\t\r\n]{0,16})\(.*?\)\1"|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/'
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group()), text, flags=re.S)


def closing(text, start, opening, ending):
    require(text[start] == opening, "Source contract delimiter differs")
    depth = 0
    for position in range(start, len(text)):
        if text[position] == opening:
            depth += 1
        elif text[position] == ending:
            depth -= 1
            if depth == 0:
                return position
    raise RuntimeError("Source contract delimiter is unterminated")


def if_blocks(mask):
    found = []
    for match in re.finditer(r"\bif\s*\(", mask):
        start = mask.index("(", match.start())
        stop = closing(mask, start, "(", ")")
        body_start = stop + 1
        while body_start < len(mask) and mask[body_start].isspace():
            body_start += 1
        if body_start < len(mask) and mask[body_start] == "{":
            body_end = closing(mask, body_start, "{", "}")
            found.append((match.start(), body_start, body_end, mask[start + 1:stop]))
    return found


def source_connections():
    loop_path = PROJECT / "Source/Host/InteractiveGameLoop.h"
    source = loop_path.read_text(encoding="utf-8")
    mask = mask_cpp(source)
    function = mask.index("RunInteractiveGameLoop(")
    parameters = mask.index("(", function)
    body = mask.index("{", closing(mask, parameters, "(", ")") + 1)
    finish = closing(mask, body, "{", "}")
    matches = list(re.finditer(r"\bWorldCameraZoom\s+(\w+)\s*(?:\{\s*\})?\s*;", mask[body:finish]))
    require(len(matches) == 1, "Loop must own one persistent production zoom value")
    variable = matches[0].group(1)
    declaration = body + matches[0].start()
    publish = mask.index("const auto publish=", body)
    pumping = mask.index("while(windowCreated)", publish)
    require(declaration < publish < pumping, "Zoom value was recreated inside publish/window pumping")
    require(mask[body:declaration].count("{") == mask[body:declaration].count("}") + 1,
            "Zoom value is not owned by the outer interactive function")
    require(not re.search(r"\b" + variable + r"\s*=", mask[declaration:finish]),
            "Zoom state is reset rather than retained across redraw/selection/menu")
    require(re.search(r"\bview\.tileWidth\s*=\s*" + variable + r"\.TileWidth\(\s*\)\s*;", mask),
            "Published world view does not carry the persistent zoom value")

    blocks = if_blocks(mask)
    modal = next(row for row in blocks if row[0] > pumping and row[3].strip() == "uiActive")
    stale = next(row for row in blocks if row[0] > pumping and "input.sceneGeneration" in row[3]
                 and "window.SceneGeneration()" in row[3])
    require(all(token in stale[3] for token in ("acted", "closeRequested", "HasMandatoryUiDecision"))
            and re.search(r"\bcontinue\s*;", mask[stale[1]:stale[2]]),
            "Existing stale/acted/close guard was weakened")
    require(re.search(r"\bcontinue\s*;\s*$", mask[modal[1] + 1:modal[2]]),
            "Modal input no longer exits before world input")
    records = []
    bindings = {}
    for operation, keys in (("ZoomIn", ("VK_PRIOR", "VK_OEM_PLUS")),
                            ("ZoomOut", ("VK_NEXT", "VK_OEM_MINUS"))):
        bound = re.search(r"\bconst\s+bool\s+(\w+)\s*=\s*input\.virtualKey\s*==\s*" + keys[0]
                          + r"\s*\|\|\s*input\.virtualKey\s*==\s*" + keys[1] + r"\s*;", mask)
        if bound:
            bindings[operation] = bound.group(1)
    for method, keys in (("ZoomIn", ("VK_PRIOR", "VK_OEM_PLUS")),
                         ("ZoomOut", ("VK_NEXT", "VK_OEM_MINUS"))):
        calls = list(re.finditer(r"\b" + variable + r"\." + method + r"\(\s*\)", mask[body:finish]))
        require(len(calls) == 1, method + " must have exactly one world-input call site")
        position = body + calls[0].start()
        require(position > modal[2] and position > stale[2], method + " bypasses modal/stale/close guards")
        require(any(row[1] < position < row[2] and "input.kind" in row[3]
                    and "BitmapInputKind::KeyDown" in row[3] for row in blocks),
                method + " is not guarded by native KeyDown input")
        candidates = [row for row in blocks if row[1] < position < row[2]
                      and all(key in row[3] for key in keys)]
        if candidates:
            branch = min(candidates, key=lambda row: row[2] - row[1])
            segment = mask[branch[1]:branch[2]]
        elif len(bindings) == 2:
            branch = next(row for row in blocks if row[1] < position < row[2]
                          and re.fullmatch(r"\s*" + bindings["ZoomIn"] + r"\s*\|\|\s*" + bindings["ZoomOut"] + r"\s*", row[3]))
            segment = mask[branch[1]:branch[2]]
            require(re.search(r"\b" + bindings["ZoomIn"] + r"\s*\?\s*" + variable
                              + r"\.ZoomIn\(\s*\)\s*:\s*" + variable + r"\.ZoomOut\(\s*\)", segment),
                    "Shared zoom branch reverses its original key mapping")
            settled = next(row for row in blocks if branch[1] < row[0] < row[2] < position
                           and "closeRequested" in row[3] and "live.IsAdvancing()" in row[3])
            require("continue;" in mask[settled[1]:settled[2]], "Unsettled world input can reach zoom mutation")
        else:
            # Also accept adjacent switch labels followed by the matching call.
            switch = mask.rfind("switch(input.virtualKey)", modal[2], position)
            require(switch >= 0, method + " lacks its original key pair")
            labels = mask[switch:position]
            boundary = max(labels.rfind("break;"), labels.rfind("continue;"))
            require(all(re.search(r"\bcase\s+" + key + r"\s*:", labels[boundary + 1:]) for key in keys),
                    method + " switch labels differ from the original pair")
            end = mask.find("continue;", position)
            require(end >= 0, method + " switch case does not consume the camera key")
            segment = mask[position:end + len("continue;")]
        require(not re.search(r"\blive\s*\.(?!IsAdvancing\s*\()|\blocalCommands\b|\bResponse\w*\s*\(|\bSend\w*\s*\(", segment),
                method + " source branch contains an SDK command")
        require("redraw" in segment and "acted" in segment and "continue;" in segment,
                method + " does not consume one key and request its redraw")
        records.append({"operation": method, "keys": list(keys), "line": source.count("\n", 0, position) + 1})

    compact = re.sub(r"\s+", "", mask)
    for action, axis, delta, span, wraps in (
            ("PanLeft", "cameraX", -3, "gridWidth", "wrapX"),
            ("PanRight", "cameraX", 3, "gridWidth", "wrapX"),
            ("PanUp", "cameraY", 3, "gridHeight", "wrapY"),
            ("PanDown", "cameraY", -3, "gridHeight", "wrapY")):
        expected = axis + "=PanCameraCoordinate(" + axis + "," + str(delta) + ",world." + span + ",world." + wraps + ");"
        require(expected in compact, action + " does not use the captured per-axis wrap/span")
    renderer = (PROJECT / "Source/Presentation/WorldViewRenderer.cpp").read_text(encoding="utf-8")
    terrain = (PROJECT / "Source/Presentation/WorldTerrainRenderer.cpp").read_text(encoding="utf-8")
    header = (PROJECT / "Source/Presentation/WorldViewRenderer.h").read_text(encoding="utf-8")
    require(re.search(r'#include\s+"WorldCameraControls.h"', header), "Renderer does not include the production controls")
    require("WorldCameraZoom::Default" in mask_cpp(header), "WorldView default diverges from production zoom")
    for name, text in (("world", renderer), ("terrain", terrain)):
        checked = mask_cpp(text)
        require("WorldCameraZoom::Minimum" in checked and "WorldCameraZoom::Maximum" in checked,
                name + " renderer does not share camera bounds")
    rendered = mask_cpp(renderer)
    require(re.search(r"RenderWorldTerrain(?:ToTexture)?\s*\(\s*view\s*,", rendered)
            and "projection->plots=std::move(terrain.projectedPlots)" in re.sub(r"\s+", "", rendered),
            "World view/terrain depth-ID projection source handoff differs")
    return {"scope": "STATIC_SOURCE_CONNECTIONS_ONLY", "key_routes": records,
            "zoom_variable": variable, "persistent_publish_value": True,
            "modal_stale_close_order_preserved": True, "axis_specific_pan_calls": 4,
            "shared_renderer_bounds_and_projection_handoff": True,
            "physical_keys_or_native_routing_verified": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, help="New YYYYMMDDTHHMMSSZ_12hex identity; existing output is never reused")
    parser.add_argument("--vs", type=Path, default=Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"))
    args = parser.parse_args()
    require(re.fullmatch(r"[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}", args.run_id), "Invalid camera component identity")
    require(artifact(SCOPE)["sha256"] == SCOPE_SHA, "Reviewed camera scope changed")
    scope = json.loads(SCOPE.read_text(encoding="utf-8"))
    require(scope["retail_mod_test_hold_active"] and not scope["host_gamecore_hwnd_execution_allowed"]
            and not scope["retail_user_state_or_process_access_allowed"], "Camera hold contract differs")
    before = [artifact(PROJECT / name) for name in RELATIVE_INPUTS]
    connection = source_connections()
    build = PROJECT / "Build/WorldCameraControls" / args.run_id
    evidence = PROJECT / "evidence/world_camera/controls" / args.run_id
    require(not build.exists() and not evidence.exists(), "Existing camera output must not be overwritten or replayed")
    for root in (build, evidence):
        require(root.resolve().is_relative_to(PROJECT) and root.resolve() == root.absolute(), "Camera output crosses a project/reparse boundary")
    build.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    report = {"schema": "zerosis.world_camera.controls_component.v1", "status": "STARTED",
              "utc": datetime.now(timezone.utc).isoformat(), "scope": artifact(SCOPE),
              "inputs": before, "source_connections": connection, "variants": [],
              "gamecore_loaded": False, "host_executed": False, "hwnd_created": False, "gpu_used": False,
              "retail_user_state_accessed": False, "game_process_queried": False,
              "full_host_compiled": False, "native_acceptance_verified": False,
              "remaining_gates": ["physical original keys and modal/stale routing", "GPU redraw and depth/ID picking",
                                  "original camera equivalence and useful playable campaign"]}
    failure = None
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.SetErrorMode.argtypes = [ctypes.c_uint]
        kernel32.SetErrorMode.restype = ctypes.c_uint
        kernel32.WerSetFlags.argtypes = [ctypes.c_ulong]
        kernel32.WerSetFlags.restype = ctypes.c_long
        previous_error_mode = kernel32.SetErrorMode(32771)
        wer_hresult = kernel32.WerSetFlags(32)
        report["runner_error_ui"] = {"dll": "kernel32", "error_mode": 32771,
                                     "previous_error_mode": previous_error_mode,
                                     "wer_flags": 32, "wer_hresult": wer_hresult}
        require(wer_hresult >= 0, "Runner WerSetFlags failed before any child launch")
        environment, compiler_text = environment_for(args.vs, "x64", build / "environment")
        compiler = Path(compiler_text)
        environment["VSLANG"] = "1033"
        report["compiler"] = artifact(compiler)
        source = PROJECT / RELATIVE_INPUTS[0]
        controls = PROJECT / RELATIVE_INPUTS[1]
        for variant, optimization in (("optimized", "/O2"), ("unoptimized", "/Od")):
            directory = build / variant
            directory.mkdir()
            exe, obj, dependencies = (directory / name for name in ("world_camera_controls.exe", "world_camera_controls.obj", "dependencies.json"))
            response = directory / "compile.rsp"
            flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/utf-8", "/fp:strict", "/MT", optimization,
                     f'"{source}"', f'/Fo"{obj}"', f'/Fe"{exe}"', f'/sourceDependencies "{dependencies}"']
            response.write_text("\n".join(flags) + "\n", encoding="utf-8")
            compiled = run([compiler, "@" + str(response), "/link", "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF"],
                           cwd=directory, env=environment, timeout=180)
            log = directory / "compile.log"
            log.write_bytes(compiled.stdout + compiled.stderr)
            transcript = (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace")
            require(compiled.returncode == 0 and not re.search(r"\bwarning\s+[A-Z]+\d+|경고\s+[A-Z]+\d+", transcript, re.I),
                    "Camera component compile failed or warned; see " + str(log))
            consumed = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
            inputs = [Path(consumed["Source"]), *(Path(name) for name in consumed["Includes"])]
            project_inputs = {path.resolve() for path in inputs if path.resolve().is_relative_to(PROJECT)}
            require(project_inputs == {source.resolve(), controls.resolve()}, "Component did not consume only the actual fixture and production controls")
            require(not any("SDK_BNW" in str(path) or "GameCore" in str(path) for path in inputs), "Headless component consumed SDK/GameCore input")
            pe = pe_header(exe)
            require(pe["architecture"] == "x64", "Camera component is not x64")
            inspected = run([compiler.with_name("dumpbin.exe"), "/dependents", exe], cwd=directory, env=environment, timeout=30)
            imports_log = directory / "imports.log"
            imports_log.write_bytes(inspected.stdout + inspected.stderr)
            imports = re.findall(r"^\s+([\w.-]+\.dll)\s*$", inspected.stdout.decode("ascii", errors="replace"), re.M | re.I)
            require(inspected.returncode == 0 and imports and all(name.lower() == "kernel32.dll" for name in imports),
                    "Pure /MT camera component has unexpected DLL imports: " + str(imports))
            executed = run([exe], cwd=directory, env=environment, timeout=30)
            execution_log = directory / "execution.log"
            execution_log.write_bytes(executed.stdout + executed.stderr)
            match = re.fullmatch(r"WORLD_CAMERA_CONTROLS_PASS checks=(\d+) cases=(\d+) GAMECORE_LOADED=false HWND_CREATED=false GPU_USED=false\s*",
                                 (executed.stdout + executed.stderr).decode("utf-8", errors="replace"))
            require(executed.returncode == 0 and match and int(match[1]) > 3000 and int(match[2]) >= 45,
                    "Camera component failed; see " + str(execution_log))
            report["variants"].append({"variant": variant, "optimization": optimization, "checks": int(match[1]), "cases": int(match[2]),
                                       "response": artifact(response), "compile_log": artifact(log), "dependencies": artifact(dependencies),
                                       "project_inputs": [artifact(path) for path in sorted(project_inputs)],
                                       "executable": {**artifact(exe), "pe": pe}, "object": artifact(obj),
                                       "imports": imports, "imports_log": artifact(imports_log), "execution_log": artifact(execution_log),
                                       "compiler_and_linker_warnings": 0, "exit_code": executed.returncode})
        require(len({(row["checks"], row["cases"]) for row in report["variants"]}) == 1, "O2/Od fixture coverage differs")
        require([artifact(PROJECT / name) for name in RELATIVE_INPUTS] == before, "Camera source changed during component validation")
        require(artifact(SCOPE) == report["scope"] and artifact(compiler) == report["compiler"], "Scope/compiler changed during validation")
        report["inputs_unchanged"] = True
        report["status"] = "PASS_HEADLESS_PRODUCTION_WORLD_CAMERA_CONTROLS"
    except Exception as error:
        report["status"] = "FAILED"
        report["error"] = {"type": type(error).__name__, "message": str(error)}
        failure = error
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    destination = evidence / "result.json"
    with destination.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "report": artifact(destination),
                      "variants": [{"optimization": row["optimization"], "checks": row["checks"], "cases": row["cases"]}
                                   for row in report["variants"]], "native_acceptance_verified": False}))
    if failure is not None:
        raise failure


if __name__ == "__main__":
    main()
