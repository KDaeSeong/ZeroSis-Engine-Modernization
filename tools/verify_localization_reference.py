"""Record the original localization DLL in isolated, owned fixture processes."""
import argparse
import json
from pathlib import Path
import re
from collect_baseline import PROJECT, digest
from native_build import checked_run, environment_for, run
from build_icu44 import artifact


def artifacts(value):
    if isinstance(value, dict):
        if "path" in value and "sha256" in value:
            yield value
        for child in value.values():
            yield from artifacts(child)
    elif isinstance(value, list):
        for child in value:
            yield from artifacts(child)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vs", type=Path, default=Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"))
    args = parser.parse_args()
    evidence = PROJECT / "evidence/localization/reference"
    build_path = evidence / "build_result.json"
    build = json.loads(build_path.read_text(encoding="utf-8"))
    if build["status"] != "SDK_LOCALIZATION_REFERENCE_BUILT":
        raise RuntimeError("Original reference build is not ready")
    for item in artifacts(build):
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Reference build input or artifact changed: " + item["path"])
    exe = Path(build["executable"]["path"])
    env, compiler = environment_for(args.vs, "x64", PROJECT / "Build/Localization/import-audit")
    paths = [exe] + [Path(item["copy"]["path"]) for item in build["original_inputs"] if item["copy"]["path"].lower().endswith(".dll")]
    allowed = {"kernel32.dll", "msvcr90.dll", "msvcp90.dll", "cvlocalizationwin32final release.dll",
               "cvgamedatabasewin32final release.dll", "lua51_win32.dll"}
    audited = []
    for i, path in enumerate(paths):
        result = checked_run([Path(compiler).with_name("dumpbin.exe"), "/imports", path], cwd=exe.parent, env=env)
        log = evidence / f"imports_{i}.log"
        log.write_bytes(result.stdout + result.stderr)
        dependencies = re.findall(r"^[ \t]+([^\\:\r\n]+\.dll)[ \t]*\r?$", result.stdout.decode("mbcs", errors="replace"), re.M | re.I)
        if not dependencies or any(name.lower() not in allowed for name in dependencies):
            raise RuntimeError("Unexpected localization reference dependency: " + repr(dependencies))
        audited.append({"binary": artifact(path), "log": artifact(log), "dependencies": dependencies})
    executions = []
    for mode in ("basic", "parameters", "numbers", "forms", "dictionary", "numeric_corpus"):
        result = run([exe, mode], cwd=exe.parent)
        log = evidence / (mode + ".log")
        log.write_bytes(result.stdout + result.stderr)
        output = result.stdout.decode("ascii").replace("\r\n", "\n")
        passed = re.search(r"^PASS\|(\d+)$", output, re.M)
        if result.returncode or result.stderr or not passed or "INITIALIZE|1\n" not in output or "SHUTDOWN|1\n" not in output:
            raise RuntimeError("Original localization probe failed: " + str(log))
        executions.append({"mode": mode, "log": artifact(log), "assertions": int(passed[1]), "exit_code": result.returncode})
    failure = run([exe, "spellout_nan"], cwd=exe.parent, timeout=10)
    failure_log = evidence / "spellout_nan_failure.log"
    failure_log.write_bytes(failure.stdout + failure.stderr)
    if (failure.returncode & 0xffffffff) != 0xc00000fd or b"BEGIN|SPELL_OUT_FLOAT_QUIET_NAN" not in failure.stdout:
        raise RuntimeError("Original NaN spellout failure changed; inspect " + str(failure_log))
    failure_record = {"status": "KNOWN_ORIGINAL_STACK_OVERFLOW_REPRODUCED", "input": "spellout(float quiet NaN 0x7fc00000)",
                      "exit_code": failure.returncode, "exit_hex": hex(failure.returncode & 0xffffffff),
                      "executable": artifact(exe), "log": artifact(failure_log), "game_launched": False, "gamecore_loaded": False}
    failure_path = evidence / "spellout_nan_failure.json"
    failure_path.write_text(json.dumps(failure_record, indent=2) + "\n", encoding="utf-8")
    for item in artifacts(build):
        if digest(Path(item["path"])) != item["sha256"]:
            raise RuntimeError("Reference input changed during execution")
    report = {"status": "SDK_LOCALIZATION_ORIGINAL_TRACE_RECORDED", "build": artifact(build_path), "imports": audited,
              "executions": executions, "original_defect": artifact(failure_path), "verifier": artifact(Path(__file__).resolve()), "game_launched": False,
              "gamecore_loaded": False, "scope": "Original component behavior observations; no x64 Localization equivalence claim"}
    (evidence / "observations.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "runs": len(executions), "assertions": sum(row["assertions"] for row in executions)}))


if __name__ == "__main__":
    main()
