"""Syntax-check the actual presentation HostMain.cpp; never link or execute it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
from native_build import environment_for, run

BASELINE_ID = "20261015T134352Z_8bd70cf290e9"
BASELINE = PROJECT / "Build/UiWindowHost" / BASELINE_ID / "dependency_discovery/tu_00_host_main"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")


def seal(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-build', default=BASELINE_ID)
    parser.add_argument('--stage', choices=('save-delete', 'save-overwrite'), default='save-delete')
    args = parser.parse_args()
    if not re.fullmatch(r'\d{8}T\d{6}Z_[0-9a-f]{12}', args.baseline_build):
        parser.error('Expected an exact preserved host build ID')
    baseline_directory = PROJECT / 'Build/UiWindowHost' / args.baseline_build / 'dependency_discovery/tu_00_host_main'
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(6)
    build = PROJECT / "Build/LoadMenuHostSyntax" / run_id
    stage = 'save_delete' if args.stage == 'save-delete' else 'save_overwrite'
    evidence = PROJECT / 'evidence' / stage / 'source_contract/host_syntax' / run_id
    build.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    original_rsp = baseline_directory / "host_main.discover.rsp"
    original_deps = baseline_directory / "host_main.sourceDependencies.json"
    baseline = json.loads(original_deps.read_text(encoding="utf-8-sig"))["Data"]
    candidates = {Path(raw) for raw in (baseline["Source"], *baseline["Includes"]) if Path(raw).is_relative_to(PROJECT / "Source")}
    candidates.add(PROJECT / "Source/Host/UiLoadMenuContract.h")
    # MSVC may spell newly consumed paths in lowercase. Windows identifies
    # these paths case-insensitively; preserve the original spelling in seals.
    before = {str(path).casefold(): seal(path) for path in sorted(candidates)}
    report = {"schema": "ZEROSIS_LOAD_MENU_ACTUAL_HOST_SYNTAX_V1", "status": "IN_PROGRESS", "run_id": run_id,
              "baseline_host_id": args.baseline_build, "feature_stage": args.stage,
              "baseline_response": seal(original_rsp), "baseline_dependencies": seal(original_deps),
              "project_inputs_before": before, "gamecore_or_host_executed": False, "hwnd_created": False,
              "linked": False, "object_or_executable_created": False,
              "generated_ui_header": seal(PROJECT / "Source/Host/UiPopupAssets.generated.h"),
              "generated_ui_limit": "The preserved generated UI header is consumed in place. This proof covers current C++ syntax only, not current Lua embedding, linking or native execution."}
    destination = evidence / "result.json"
    def checkpoint():
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    checkpoint()
    try:
        env, compiler = environment_for(VS, "x64", build)
        env["VSLANG"] = "1033"
        report["compiler"] = seal(Path(compiler))
        dependencies = build / "syntax.sourceDependencies.json"
        flags = []
        for line in original_rsp.read_text(encoding="utf-8-sig").splitlines():
            if line == "/c" or line.startswith(("/Fo", "/sourceDependencies")):
                continue
            flags.append(line)
        if any("frozen" in flag.lower() for flag in flags) or any(flag.startswith(("/Fe", "/Fd", "/link")) for flag in flags):
            raise RuntimeError("Unexpected frozen/output/link argument in baseline discovery response")
        flags.extend(("/Zs", f'/sourceDependencies "{dependencies}"'))
        response = build / "syntax.rsp"
        response.write_text("\n".join(flags) + "\n", encoding="utf-8")
        report["response"] = seal(response)
        checkpoint()
        result = run([compiler, "@" + str(response)], cwd=build, env=env, timeout=300)
        output = (result.stdout + result.stderr).decode("mbcs", errors="replace")
        log = evidence / "compile.log"
        log.write_text(output, encoding="utf-8")
        report.update(compiler_exit_code=result.returncode, compile_log=seal(log),
                      warnings=re.findall(r"\b(?:warning [A-Z]+\d+|warning D\d+)\b", output, flags=re.I))
        checkpoint()
        after = {str(path).casefold(): seal(path) for path in sorted(candidates)}
        report["project_inputs_after"] = after
        if before != after:
            raise RuntimeError("A consumed project source changed during syntax compilation")
        if any(build.rglob("*.obj")) or any(build.rglob("*.exe")) or any(build.rglob("*.dll")):
            raise RuntimeError("Syntax-only compiler unexpectedly produced code artifacts")
        if dependencies.is_file():
            consumed = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
            project_consumed = {str(Path(raw)).casefold() for raw in (consumed["Source"], *consumed["Includes"])
                                if Path(raw).is_relative_to(PROJECT / "Source")}
            missing = project_consumed - set(before)
            report.update(dependencies=seal(dependencies), consumed_project_input_count=len(project_consumed),
                          consumed_project_inputs={key: after[key] for key in sorted(project_consumed) if key in after},
                          unsealed_project_dependencies=sorted(missing))
            if missing:
                raise RuntimeError("Syntax compiler consumed a new project dependency without a before hash")
        else:
            report["dependencies_available"] = False
        if result.returncode or report["warnings"]:
            raise RuntimeError("Actual HostMain.cpp syntax compilation failed or warned")
        report["status"] = "PASS"
    except Exception as exc:
        report.update(status="FAIL", error=str(exc))
        checkpoint()
        print(json.dumps({"status": "FAIL", "report": str(destination), "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    checkpoint()
    print(json.dumps({"status": "PASS", "report": str(destination), "build": str(build),
                      "consumed_project_inputs": report.get("consumed_project_input_count"), "warnings": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
