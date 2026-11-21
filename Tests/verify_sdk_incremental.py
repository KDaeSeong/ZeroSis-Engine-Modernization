"""Exercise real MSVC/PCH dependency invalidation in a private fixture."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_sdk_incremental import (BUILD_ROOT, EVIDENCE_ROOT, VS, build_lock,
                                   clear_outputs, escape, save, tracked_compile, x64_project)
from native_build import environment_for


def main():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    root = BUILD_ROOT / "validation" / run_id
    source = root / "Source"
    directory = root / "Build"
    evidence = EVIDENCE_ROOT / "validation" / run_id
    source.mkdir(parents=True)
    directory.mkdir()
    evidence.mkdir(parents=True)
    fixture = {
        "_precompile.cpp": '#include "pch.h"\n',
        "pch.h": '#pragma once\n#include "shared.h"\n#ifndef RECIPE_BONUS\n#define RECIPE_BONUS 0\n#endif\n',
        "shared.h": "#pragma once\n#define SHARED_VALUE 11\n",
        "local.h": "#pragma once\n#define LOCAL_VALUE 5\n",
        "a.cpp": '#include "pch.h"\n#include "local.h"\nint value_a() { return SHARED_VALUE + LOCAL_VALUE; }\n',
        "b.cpp": '#include "pch.h"\nint value_b() { return SHARED_VALUE + RECIPE_BONUS; }\n',
    }
    for name, text in fixture.items():
        (source / name).write_text(text, encoding="utf-8")
    sources = [source / name for name in ("_precompile.cpp", "a.cpp", "b.cpp")]
    project = directory / "fixture.vcxproj"
    flags = ["/nologo", "/c", "/std:c++14", "/EHsc", "/MD", "/Od", "/fp:strict", f'/I"{source}"']
    x64_project(project, sources, flags, "pch.h", "14.44.35207")
    sdk = Path(r"C:\Program Files (x86)\Windows Kits\10")
    command = [str(VS / "MSBuild/Current/Bin/amd64/MSBuild.exe"), str(project),
               "/nologo", "/t:ClCompile", "/m:1", "/nr:false", "/v:minimal",
               "/p:Configuration=Dev", "/p:Platform=x64", "/p:PreferredToolArchitecture=x64",
               "/p:TrackFileAccess=true", "/p:UseMultiToolTask=false",
               "/p:WindowsTargetPlatformVersion=10.0.26100.0",
               "/p:_LatestWindowsTargetPlatformVersion=10.0.26100.0",
               "/p:TargetPlatformDisplayName=Windows", "/p:TargetPlatformSdkPath=" + escape(sdk) + "/",
               "/p:WindowsSdkDir=" + escape(sdk) + "/"]
    checks = []

    def build(name, expected=None, passed=True):
        run_dir = evidence / name
        run_dir.mkdir()
        with build_lock(directory):
            result = tracked_compile(directory, project, command, sources, [source], run_dir, 2)
        assert (result["status"] == "SDK_INCREMENTAL_COMPILE_PASS") == passed, (name, result["status"], result["unique_error_lines"])
        if expected is not None:
            assert set(result["rebuilt_units"]) == set(expected), (name, result["rebuilt_units"], expected)
        checks.append({"case": name, "passed": True, "rebuilt_units": result["rebuilt_units"],
                       "report": str(run_dir / "build_result.json")})
        print(json.dumps({"case": name, "rebuilt": result["rebuilt_units"], "expected_success": passed}), flush=True)
        return result

    all_units = [path.stem for path in sources]
    build("cold", all_units)
    build("unchanged", [])
    (source / "a.cpp").write_text(fixture["a.cpp"].replace("LOCAL_VALUE;", "LOCAL_VALUE + 1;"), encoding="utf-8")
    build("one_cpp", ["a"])
    (source / "local.h").write_text(fixture["local.h"].replace("5", "6"), encoding="utf-8")
    build("local_header", ["a"])
    (source / "shared.h").write_text(fixture["shared.h"].replace("11", "12"), encoding="utf-8")
    build("transitive_pch_header", all_units)
    timestamp = (source / "a.cpp").stat()
    valid_a = fixture["a.cpp"].replace("LOCAL_VALUE;", "LOCAL_VALUE + 2 + RECIPE_BONUS;")
    (source / "a.cpp").write_text(valid_a, encoding="utf-8")
    os.utime(source / "a.cpp", ns=(timestamp.st_atime_ns, timestamp.st_mtime_ns))
    build("changed_content_restored_timestamp", all_units)
    (directory / "obj/a.obj").unlink()
    build("missing_object", ["a"])
    (directory / "obj/b.obj").write_bytes(b"damaged compiler output")
    build("damaged_object", ["b"])
    (directory / "obj/GameCore_x64.pch").write_bytes(b"damaged precompiled header")
    build("damaged_pch", all_units)
    (source / "a.cpp").write_text(valid_a + "\nthis is a compilation error!\n", encoding="utf-8")
    build("compile_failure", passed=False)
    (source / "a.cpp").write_text(valid_a, encoding="utf-8")
    recovered = build("failure_recovery")
    assert "a" in recovered["rebuilt_units"], "Failed source must be recompiled after correction"
    (source / "local.h").unlink()
    build("missing_header", passed=False)
    (source / "local.h").write_text(fixture["local.h"].replace("5", "6"), encoding="utf-8")
    build("header_recovery", all_units)
    x64_project(project, sources, flags + ["/DRECIPE_BONUS=3"], "pch.h", "14.44.35207")
    build("compiler_options_changed", all_units)
    build("final_unchanged", [])
    with build_lock(directory):
        try:
            with build_lock(directory):
                raise AssertionError("Concurrent output ownership was accepted")
        except RuntimeError:
            checks.append({"case": "concurrent_build_rejected", "passed": True})
    outside = root / "keep.obj"
    outside.write_bytes(b"must survive")
    try:
        clear_outputs(directory, [outside])
        raise AssertionError("Outside output invalidation was accepted")
    except RuntimeError:
        assert outside.read_bytes() == b"must survive"
        checks.append({"case": "outside_output_preserved", "passed": True})
    expected_main = root / "expected_main.cpp"
    expected_main.write_text("int value_a(); int value_b();\nint main() { return value_a() == 23 && value_b() == 15 ? 0 : 1; }\n", encoding="utf-8")
    env, compiler = environment_for(VS, "x64", root)
    executable = root / "fixture_result.exe"
    linked = subprocess.run([compiler, "/nologo", "/EHsc", "/MD", str(expected_main),
                             "/Fo" + str(root / "expected_main.obj"), "/Fe" + str(executable),
                             str(directory / "obj/_precompile.obj"),
                             str(directory / "obj/a.obj"), str(directory / "obj/b.obj")],
                            cwd=root, env=env, capture_output=True, timeout=60,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    assert linked.returncode == 0, (linked.stdout + linked.stderr).decode("mbcs", errors="replace")
    executed = subprocess.run([str(executable)], cwd=root, capture_output=True, timeout=10,
                              creationflags=subprocess.CREATE_NO_WINDOW)
    assert executed.returncode == 0, "Objects contain outdated values after dependency changes"
    checks.append({"case": "linked_fixture_values", "passed": True, "expected_a": 23, "expected_b": 15})
    report = {"status": "SDK_INCREMENTAL_DEPENDENCY_VALIDATION_PASS", "checks": checks,
              "scope": "REAL_MSVC_PRIVATE_FIXTURE_NOT_GAME_RUNTIME"}
    save(evidence / "conformance.json", report)
    save(EVIDENCE_ROOT / "validation/latest.json", report)
    print(json.dumps({"status": report["status"], "checks": len(checks), "report": str(evidence / "conformance.json")}), flush=True)


if __name__ == "__main__":
    main()
