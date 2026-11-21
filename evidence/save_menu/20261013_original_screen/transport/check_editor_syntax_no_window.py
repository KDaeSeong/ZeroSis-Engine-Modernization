"""Syntax-check the actual presenter/editor regression without linking or running HWND code."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import sys

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from native_build import environment_for, run


def ref(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest}


stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + secrets.token_hex(6)
build = ROOT / "Build/SaveMenuTransport/S" / stamp[-12:]
evidence = HERE / "editor_syntax_no_window" / stamp
build.mkdir(parents=True, exist_ok=False)
evidence.mkdir(parents=True, exist_ok=False)
names = ("Source/Presentation/BitmapWindow.cpp", "Tests/bitmap_window.cpp",
         "Source/Presentation/BitmapEditorInput.h", "Source/Presentation/BitmapWindow.h",
         "Source/Presentation/BitmapRenderer.h")
before = {name: ref(ROOT / name) for name in names}
report = {"schema": "ZEROSIS_EDITOR_PRESENTATION_SYNTAX_NO_WINDOW_V1", "status": "RUNNING",
          "scope": "MSVC /Zs actual BitmapWindow and authored HWND test translation units only",
          "linked": False, "native_test_executed": False, "window_created": False,
          "sdk_loaded": False, "game_process_accessed": False,
          "source_before": before, "runs": [], "build": str(build), "failure": None,
          "host_integration_headers_compiled": False}
target = evidence / "conformance.json"


def checkpoint():
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


checkpoint()
try:
    for name in names:
        destination = build / "frozen" / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, destination)
        assert ref(destination)["sha256"] == before[name]["sha256"]
    env, compiler = environment_for(Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"), "x64", build)
    env["VSLANG"] = "1033"
    report["compiler"] = ref(Path(compiler))
    common = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/O2", "/MD", "/fp:strict",
              "/DWIN32", "/D_WIN32_WINNT=0x0A00", "/DNOMINMAX", "/DWIN32_LEAN_AND_MEAN",
              "/DZEROSIS_BITMAP_WINDOW_DIAGNOSTICS", "/Zs", "/showIncludes"]
    for name in names[:2]:
        source = build / "frozen" / name
        label = "presentation" if name.startswith("Source/") else "regression"
        flags = [*common, '"' + str(source) + '"']
        response = build / (label + ".rsp")
        response.write_text("\n".join(flags) + "\n", encoding="utf-8")
        compiled = run([compiler, "@" + str(response)], cwd=build, env=env, timeout=120)
        output = (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace")
        log = evidence / (label + "_syntax.log")
        log.write_text(output, encoding="utf-8")
        dependencies = {source.resolve()}
        for line in output.splitlines():
            match = re.search(r"(?:Note: including file:|참고: 포함 파일:)\s*(.+?)\s*$", line)
            if match:
                dependencies.add(Path(match.group(1)).resolve())
        warnings = bool(re.search(r"(?:\bwarning|경고)\s+[A-Z]+\d+", output, re.I))
        record = {"source": name, "returncode": compiled.returncode,
                  "status": "PASS" if compiled.returncode == 0 and not warnings else "FAIL",
                  "warnings": warnings, "arguments": flags, "response": ref(response), "log": ref(log),
                  "dependencies": [ref(path) for path in sorted(dependencies, key=str)]}
        report["runs"].append(record)
        checkpoint()
        if record["status"] != "PASS":
            raise RuntimeError("Syntax check failed or warned: " + output[-3000:])
        if len(dependencies) < 2:
            raise RuntimeError("Compiler include trace was not captured")
    report["source_after"] = {name: ref(ROOT / name) for name in names}
    report["source_unchanged"] = before == report["source_after"]
    report["objects_or_executables_created"] = [str(path) for path in build.rglob("*")
                                                if path.is_file() and path.suffix.lower() in (".obj", ".exe", ".pdb")]
    if not report["source_unchanged"] or report["objects_or_executables_created"]:
        raise RuntimeError("Syntax check source drifted or unexpectedly generated native outputs")
    report["status"] = "PASS_EDITOR_PRESENTATION_SYNTAX_NO_WINDOW"
except Exception as error:
    report["status"] = "FAIL"
    report["failure"] = str(error)
finally:
    checkpoint()
print(json.dumps({"status": report["status"], "receipt": ref(target), "failure": report["failure"]}))
sys.exit(0 if report["status"] == "PASS_EDITOR_PRESENTATION_SYNTAX_NO_WINDOW" else 1)
