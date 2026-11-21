"""Check current integrated Host syntax without linking or opening a window."""
from __future__ import annotations

import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

HERE = Path(__file__).absolute().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import build_ui_window_host as builder
from native_build import environment_for, run


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def ref(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def sources():
    paths = set(builder.OWNED.values())
    for folder in (ROOT / "Source/Host", ROOT / "Source/Presentation"):
        paths.update(folder.glob("*.h"))
    paths.add(ROOT / "Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h")
    paths.add(Path(__file__))
    return {str(path): ref(path) for path in sorted(paths)}


def main():
    require(builder.PROJECT == ROOT, "Compiler setup belongs to another workspace")
    tree = ast.parse((ROOT / "tools/build_ui_window_host.py").read_text(encoding="utf-8-sig"))
    common = [ast.literal_eval(node.value) for node in ast.walk(tree)
              if isinstance(node, ast.Assign) and any(
                  isinstance(target, ast.Name) and target.id == "common" for target in node.targets)]
    require(len(common) == 1 and all(isinstance(flag, str) for flag in common[0]),
            "Expected one explicit current Host compiler flag list")
    flags = common[0]
    require("/W4" in flags and "/WX" in flags and "/std:c++14" in flags,
            "Integrated Host warning/language contract changed")
    protected = [ROOT / "Play/EarlyAccess/release.json", ROOT / "tools/Start-Engine.ps1"]
    protected_before = [ref(path) for path in protected]
    before = sources()
    output = HERE / "host_syntax" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + secrets.token_hex(4))
    output.mkdir(parents=True, exist_ok=False)
    require(output.resolve(strict=True).is_relative_to(HERE.resolve(strict=True)), "Syntax workspace escaped")
    report = {"schema": "ZEROSIS_HOST_SYNTAX_NO_WINDOW_V1", "status": "IN_PROGRESS",
              "window_created": False, "game_or_host_executed": False, "linked": False,
              "sdk_loaded": False, "game_process_accessed": False,
              "default_publication_changed": False, "full_engine_goal_complete": False,
              "source_before": before, "protected_before": protected_before}
    try:
        env, compiler = environment_for(builder.VS, "x64", output)
        env["VSLANG"] = "1033"
        sdk_include, _ = builder.include_directories(env)
        include_flags = [f'/external:I"{path}"' for path in sdk_include]
        include_flags += [f'/I"{path}"' for path in builder.PROJECT_INCLUDE_DIRS]
        source = builder.OWNED["host_main"]
        dependencies = output / "dependencies.json"
        response = output / "syntax.rsp"
        compile_flags = flags + include_flags + ["/Zs", f'"{source}"',
                                                f'/sourceDependencies "{dependencies}"']
        response.write_text("\n".join(compile_flags) + "\n", encoding="utf-8")
        result = run([compiler, "@" + str(response)], cwd=output, env=env, timeout=180)
        log = output / "compile.log"
        log.write_bytes(result.stdout + result.stderr)
        decoded = (result.stdout + result.stderr).decode("mbcs", errors="replace")
        report.update(compiler=ref(Path(compiler)), compiled_source=ref(source),
                      compile_response=ref(response), compile_log=ref(log),
                      returncode=result.returncode, warnings=bool(re.search(r"\bwarning\s+[A-Z]+\d+", decoded, re.I)),
                      dependency_report=ref(dependencies) if dependencies.is_file() else None)
        require(result.returncode == 0 and not report["warnings"], "Current integrated Host syntax failed")
        report["source_after"] = sources()
        report["source_unchanged"] = before == report["source_after"]
        report["protected_after"] = [ref(path) for path in protected]
        report["default_publication_changed"] = protected_before != report["protected_after"]
        report["objects_or_executables_created"] = bool(list(output.glob("*.obj")) + list(output.glob("*.exe")))
        require(report["source_unchanged"], "Source changed while compiling; do not reuse this proof")
        require(not report["default_publication_changed"], "Published launcher changed during syntax check")
        require(not report["objects_or_executables_created"], "Syntax mode unexpectedly generated binary output")
        report["status"] = "PASS_INTEGRATED_HOST_SYNTAX_PENDING_LINK_AND_RUNTIME"
    except Exception as error:
        report["status"] = "FAILED_INTEGRATED_HOST_SYNTAX_NO_WINDOW"
        report["error"] = str(error)
    finally:
        setup = output / "read_build_environment.cmd"
        removed = []
        if setup.is_file():
            require(setup.resolve(strict=True).parent == output.resolve(strict=True), "Temporary setup path escaped")
            removed.append(ref(setup))
            setup.unlink()
        report["own_temporary_setup_removed"] = removed
        report["limits"] = ["Syntax only: no link, PE import test or native Host launch",
                            "No SaveMenu, physical IME, named save or restoration runtime proof",
                            "Original UI, full campaign, original saves/mods and multicore performance remain incomplete"]
        destination = output / "conformance.json"
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": report["status"], "receipt": ref(destination),
                          "source_unchanged": report.get("source_unchanged", False),
                          "windows_created": False, "linked": False}, ensure_ascii=False))
    return 0 if report["status"].startswith("PASS_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
