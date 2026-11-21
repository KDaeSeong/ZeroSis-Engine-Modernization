"""Build and run the production editor queue checks without creating a window."""
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
from verify_bitmap_window import dependencies


def ref(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest}


stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + secrets.token_hex(6)
build = ROOT / "Build/SaveMenuTransport/E" / stamp[-12:]
evidence = HERE / "editor_no_window" / stamp
build.mkdir(parents=True, exist_ok=False); evidence.mkdir(parents=True, exist_ok=False)
names = ("Tests/bitmap_editor_input.cpp", "Source/Presentation/BitmapEditorInput.h",
         "Source/Presentation/BitmapWindow.h", "Source/Presentation/BitmapRenderer.h")
before = {name: ref(ROOT / name) for name in names}
report = {"schema": "ZEROSIS_EDITOR_BUFFER_NO_WINDOW_CHECK_V1", "status": "RUNNING",
          "scope": "production bounded queue and terminal-action policy only",
          "window_created": False, "sdk_loaded": False, "game_process_accessed": False,
          "source_before": before, "runs": [], "build": str(build), "failure": None}
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
    linker = shutil.which("link.exe", path=env["PATH"])
    report["compiler"] = ref(Path(compiler)); report["linker"] = ref(Path(linker))
    for optimization in ("O2", "Od"):
        folder = build / optimization; folder.mkdir()
        source = build / "frozen/Tests/bitmap_editor_input.cpp"
        obj = folder / "editor_queue.obj"; exe = folder / "editor_queue.exe"
        dependency = folder / "dependencies.json"; response = folder / "compile.rsp"
        flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/" + optimization, "/MD",
                 "/DWIN32", "/D_WIN32_WINNT=0x0A00", "/DNOMINMAX", "/DWIN32_LEAN_AND_MEAN",
                 "/c", '"' + str(source) + '"', '/Fo"' + str(obj) + '"',
                 '/sourceDependencies "' + str(dependency) + '"']
        response.write_text("\n".join(flags) + "\n", encoding="utf-8")
        compiled = run([compiler, "@" + str(response)], cwd=folder, env=env, timeout=180)
        output = (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace")
        log = evidence / (optimization + "_compile.log"); log.write_text(output, encoding="utf-8")
        if compiled.returncode or re.search(r"\bwarning\s+C\d+", output, re.I):
            raise RuntimeError("Compile failed or warned: " + output[-3000:])
        link_response = folder / "link.rsp"
        link_response.write_text('"' + str(obj) + '"\n/OUT:"' + str(exe) +
                                 '"\n/INCREMENTAL:NO\n/MACHINE:X64\n/Brepro\n/WX\n/OPT:REF\n/OPT:ICF\n/SUBSYSTEM:CONSOLE\n', encoding="utf-8")
        linked = run([linker, "@" + str(link_response)], cwd=folder, env=env, timeout=180)
        output = (linked.stdout + linked.stderr).decode("mbcs", errors="replace")
        link_log = evidence / (optimization + "_link.log"); link_log.write_text(output, encoding="utf-8")
        if linked.returncode or re.search(r"\bwarning\s+LNK\d+", output, re.I):
            raise RuntimeError("Link failed or warned: " + output[-3000:])
        tested = run([exe], cwd=folder, env=env, timeout=30)
        output = (tested.stdout + tested.stderr).decode("utf-8", errors="replace")
        test_log = evidence / (optimization + "_test.log"); test_log.write_text(output, encoding="utf-8")
        match = re.fullmatch(r"BITMAP_EDITOR_INPUT_BUFFER_PASS checks=17 WINDOW_CREATED=false SDK_LOADED=false\s*", output)
        record = {"optimization": optimization, "returncode": tested.returncode,
                  "status": "PASS" if tested.returncode == 0 and match else "FAIL",
                  "checks": 17 if match else None, "executable": ref(exe), "object": ref(obj),
                  "compile_log": ref(log), "link_log": ref(link_log), "test_log": ref(test_log),
                  "dependencies": [ref(path) for path in dependencies(dependency, source)]}
        report["runs"].append(record); checkpoint()
        if record["status"] != "PASS":
            raise RuntimeError("No-window queue test failed: " + output[-3000:])
    after = {name: ref(ROOT / name) for name in names}
    report["source_after"] = after; report["source_unchanged"] = before == after
    if before != after:
        raise RuntimeError("Source changed during the no-window component run")
    report["status"] = "PASS_EDITOR_BUFFER_NO_WINDOW"
except Exception as error:
    report["status"] = "FAIL"; report["failure"] = str(error)
finally:
    checkpoint()
print(json.dumps({"status": report["status"], "receipt": ref(target), "failure": report["failure"]}))
sys.exit(0 if report["status"] == "PASS_EDITOR_BUFFER_NO_WINDOW" else 1)
