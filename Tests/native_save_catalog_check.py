"""Run isolated native Win32 catalog boundaries without loading SDK/game DLLs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets
import shutil
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
from collect_baseline import pe_header
from native_build import environment_for, run
from verify_bitmap_window import run_owned_test

SOURCE = PROJECT / "Tests/native_save_catalog.cpp"
HEADERS = [PROJECT / "Source/Host" / name for name in
           ("NativeSaveCatalog.h", "UiSaveMenuContract.h", "NativeSaveArchive.h", "HostFiles.h", "SdkHostIncludes.h")]
HEADERS.append(PROJECT / "Tests/owned_save_replace_transaction_fixture.h")
OUTPUT_ROOT = PROJECT / "Build/NativeSaveCatalog"
EVIDENCE_ROOT = PROJECT / "evidence/native_save_catalog"
SDK = PROJECT / "Source/SDK_BNW_x64"
SDK_INCLUDES = [SDK / name for name in (
    "CvGameCoreDLL_Expansion2", "CvGameCoreDLLUtil/include", "CvGameDatabase/include",
    "CvLocalization/include", "CvWorldBuilderMap/include", "FirePlace/include",
    "FirePlace/include/FireWorks", "ThirdPartyLibs/Lua51/include")]
FAULT_UI_MARKER = "NATIVE_SAVE_CATALOG_FAULT_UI_SUPPRESSED WER_NO_UI=true"


def artifact(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest}


def positive_exact(value):
    if not re.fullmatch(r"[1-9][0-9]*", value):
        raise argparse.ArgumentTypeError("Expected an exact positive decimal check count")
    return int(value)


def allocate():
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    for _ in range(10):
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(6)
        output, evidence = OUTPUT_ROOT / run_id, EVIDENCE_ROOT / run_id
        try:
            output.mkdir(exist_ok=False)
        except FileExistsError:
            continue
        try:
            evidence.mkdir(exist_ok=False)
        except FileExistsError:
            output.rmdir()
            continue
        return run_id, output, evidence
    raise RuntimeError("Could not allocate a unique native catalog run ID")


def freeze(path, frozen, records):
    """Preserve only consumed source/header/library bytes, never a project copy."""
    path = path.resolve(strict=True)
    key = str(path).casefold()
    seal = artifact(path)
    if key in records:
        row = records[key]
        if seal != row["original"] or artifact(Path(row["frozen"]["path"])) != row["frozen"]:
            raise RuntimeError(f"Compiler input changed: {path}")
        return Path(row["frozen"]["path"])
    try:
        relative = path.relative_to(PROJECT)
    except ValueError:
        prefix = hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        relative = Path("external") / (prefix + "_" + path.name)
    target = frozen / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        raise RuntimeError(f"Frozen compiler input already exists: {target}")
    shutil.copy2(path, target)
    frozen_seal = artifact(target)
    if (seal["bytes"], seal["sha256"]) != (frozen_seal["bytes"], frozen_seal["sha256"]):
        raise RuntimeError(f"Frozen compiler input differs: {path}")
    records[key] = {"original": seal, "frozen": frozen_seal}
    return target


def parse_transcript(transcript, expected_checks):
    markers = re.findall(r"^NATIVE_SAVE_CATALOG_PASS checks=([0-9]+) "
                         r"GAMECORE_LOADED=false RETAIL_SAVES_TOUCHED=false$", transcript, re.M)
    if markers != [str(expected_checks)]:
        raise RuntimeError(f"Expected exactly {expected_checks} native checks and one pass marker")
    if transcript.splitlines().count(FAULT_UI_MARKER) != 1:
        raise RuntimeError("Native WER fault UI suppression marker is missing or duplicated")
    return expected_checks


def execute(row, optimization, before, output, frozen, frozen_records, expected_checks, checkpoint):
    flavor = row["flavor"]
    directory = output / flavor
    directory.mkdir(exist_ok=False)
    environment, compiler = environment_for(
        Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"), "x64", directory)
    environment["VSLANG"] = "1033"
    wer = next((Path(part) / "wer.lib" for part in environment.get("LIB", "").split(";")
                if part and (Path(part) / "wer.lib").is_file()), None)
    if wer is None:
        raise RuntimeError("WER import library is missing")
    wer_frozen = freeze(wer, frozen, frozen_records)
    executable = directory / "NativeSaveCatalog.exe"
    dependencies = directory / "dependencies.json"
    response = directory / "compile.rsp"
    frozen_source = frozen / SOURCE.relative_to(PROJECT)
    flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", optimization, "/MD", "/fp:strict",
             "/source-charset:windows-1252", "/external:W0", "/DWIN32", "/DNDEBUG", "/DFINAL_RELEASE",
             "/D_CRT_SECURE_NO_WARNINGS", "/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS",
             "/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING"]
    flags.extend(f'/external:I"{path}"' for path in SDK_INCLUDES)
    flags.extend([f'/I"{frozen / "Source/Host"}"', f'/I"{PROJECT / "Source/Porting"}"',
                  f'"{frozen_source}"', f'/Fo"{directory.as_posix()}/"', f'/Fe"{executable}"',
                  f'/sourceDependencies "{dependencies}"'])
    link_flags = ["/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF", str(wer_frozen)]
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    row.update({"optimization": optimization, "compiler": artifact(Path(compiler)),
                "response": artifact(response), "arguments": flags, "link_arguments": link_flags,
                "wer_library": artifact(wer_frozen), "status": "COMPILING"})
    checkpoint()
    compiled = run([compiler, f"@{response}", "/link", *link_flags],
                   cwd=directory, env=environment, timeout=180)
    text = (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace")
    log = directory / "compile.log"
    log.write_text(text, encoding="utf-8")
    row.update({"compile_log": artifact(log), "compiler_exit_code": compiled.returncode})
    checkpoint()
    if compiled.returncode or re.search(r"\bwarning\s+[A-Z]+\d+", text, re.I):
        raise RuntimeError(f"{flavor} compile failed or warned: {log}\n{text[-2500:]}")
    consumed = json.loads(dependencies.read_text(encoding="utf-8-sig"))["Data"]
    inputs = []
    for raw in [consumed["Source"], *consumed["Includes"]]:
        path = Path(raw).resolve(strict=True)
        if path not in inputs:
            inputs.append(path)
    if Path(consumed["Source"]).resolve(strict=True) != frozen_source:
        raise RuntimeError("Compiler consumed an unexpected test source")
    for header in HEADERS:
        if frozen / header.relative_to(PROJECT) not in inputs:
            raise RuntimeError(f"Compiler did not consume {header.name}")
    dependency_seals = []
    for path in inputs:
        if path.is_relative_to(frozen):
            dependency_seals.append({"consumed": artifact(path), "frozen": artifact(path)})
        else:
            saved = freeze(path, frozen, frozen_records)
            dependency_seals.append({"consumed": artifact(path), "frozen": artifact(saved)})
    if [artifact(path) for path in [SOURCE, *HEADERS]] != before:
        raise RuntimeError("Catalog source changed during compilation")
    pe = pe_header(executable)
    if pe["architecture"] != "x64":
        raise RuntimeError("Catalog test has an unexpected PE architecture")
    fixtures = directory / "data"
    fixtures.mkdir(exist_ok=False)
    row.update({"status": "RUNNING", "executable": artifact(executable), "pe": pe,
                "dependencies": artifact(dependencies), "compiler_inputs": dependency_seals,
                "compiler_input_count": len(inputs), "fixture_root": str(fixtures),
                "compiler_and_linker_warnings": 0, "pid": None})
    checkpoint()
    def started(pid):
        row["pid"] = pid
        checkpoint()
    execution = run_owned_test([str(executable), str(fixtures)], cwd=directory,
                               env=environment, timeout=45, on_start=started)
    transcript = (execution.pop("stdout") + execution.pop("stderr")).replace("\r\n", "\n").replace("\r", "\n")
    execution_log = directory / "execution.log"
    execution_log.write_text(transcript, encoding="utf-8")
    row.update({"native_execution": execution, "execution_log": artifact(execution_log)})
    checkpoint()
    if execution["returncode"] or execution["timed_out"]:
        raise RuntimeError(f"{flavor} catalog boundaries failed: {execution_log}\n{transcript[-2500:]}")
    row.update({"checks": parse_transcript(transcript, expected_checks), "status": "PASS",
                "native_exit_code": execution["returncode"], "fault_ui_suppressed": True,
                "gamecore_loaded": False, "retail_saves_touched": False})
    replacement = re.findall(r"^NATIVE_SAVE_REPLACEMENT_PASS checks=([0-9]+) ATOMIC=false "
                             r"GAMECORE_LOADED=false RETAIL_SAVES_TOUCHED=false$", transcript, re.M)
    if len(replacement) != 1 or not 100 <= int(replacement[0]) <= 10000:
        raise RuntimeError("Replacement failure/collision boundaries are missing or incomplete")
    row["replacement_checks"] = int(replacement[0])
    row["crash_runs"] = []
    for phase in ("stage", "journal", "old", "new", "old-cleanup", "journal-cleanup"):
        root = directory / ("crash-" + phase)
        root.mkdir(exist_ok=False)
        crash = {"phase": phase, "fixture_root": str(root)}
        row["crash_runs"].append(crash)
        checkpoint()
        for mode, expected_exit in (("crash", 91), ("recover", 0)):
            child = run_owned_test([str(executable), str(root), "--replace-" + mode, phase],
                                   cwd=directory, env=environment, timeout=30)
            output = (child.pop("stdout") + child.pop("stderr")).replace("\r\n", "\n").replace("\r", "\n")
            log = directory / ("replacement-" + phase + "-" + mode + ".log")
            log.write_text(output, encoding="utf-8")
            crash[mode] = {"execution": child, "log": artifact(log)}
            checkpoint()
            if child["returncode"] != expected_exit or child["timed_out"] or output.splitlines().count(FAULT_UI_MARKER) != 1:
                raise RuntimeError(f"Own process {mode}/{phase} failed: {output[-1500:]}")
            if mode == "recover":
                marker = (f"NATIVE_SAVE_REPLACEMENT_RECOVERY_PASS phase={phase} "
                          f"orphan_preserved={'true' if phase == 'stage' else 'false'} ATOMIC=false")
                if output.splitlines().count(marker) != 1:
                    raise RuntimeError(f"Recovery marker missing for own interruption {phase}")
        crash["status"] = "PASS_PROCESS_INTERRUPTION_AND_RESTART"


def main():
    global OUTPUT_ROOT, EVIDENCE_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-checks", type=positive_exact, required=True)
    parser.add_argument("--replacement", action="store_true",
                        help="Use the owned replacement transaction build/evidence roots")
    args = parser.parse_args()
    if args.replacement:
        OUTPUT_ROOT = PROJECT / "Build/NativeSaveReplacement"
        EVIDENCE_ROOT = PROJECT / "evidence/save_overwrite/source_contract/native_transaction"
    for path in [SOURCE, *HEADERS]:
        path.read_bytes().decode("ascii")
    before = [artifact(path) for path in [SOURCE, *HEADERS]]
    run_id, output, evidence = allocate()
    frozen = output / "frozen"
    frozen_records = {}
    report = {"schema": "ZEROSIS_NATIVE_SAVE_CATALOG_BOUNDARIES_V2", "status": "IN_PROGRESS",
              "run_id": run_id, "started_utc": datetime.now(timezone.utc).isoformat(),
              "runner": artifact(Path(__file__)), "expected_checks_per_flavor": args.expected_checks,
              "sources": before, "runs": [], "original_save_schema_changed": False,
              "live_gameplay_verified": False, "retail_ui_restored": False,
              "console_suppression": "CREATE_NO_WINDOW", "fault_ui_suppression":
              "inherited SetErrorMode and required child WerSetFlags(WER_FAULT_REPORTING_NO_UI)"}
    destination = evidence / "result.json"
    def checkpoint():
        report["frozen_inputs"] = list(frozen_records.values())
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    checkpoint()
    try:
        for path in [SOURCE, *HEADERS, Path(__file__).resolve()]:
            freeze(path, frozen, frozen_records)
        for flavor, optimization in [("optimized", "/O2"), ("debug", "/Od")]:
            row = {"flavor": flavor, "status": "PENDING"}
            report["runs"].append(row)
            execute(row, optimization, before, output, frozen, frozen_records,
                    args.expected_checks, checkpoint)
            checkpoint()
            print(json.dumps({"flavor": flavor, "checks": row["checks"], "status": "PASS"}), flush=True)
        if [artifact(path) for path in [SOURCE, *HEADERS]] != before:
            raise RuntimeError("Catalog source changed during boundary tests")
        for row in frozen_records.values():
            if artifact(Path(row["original"]["path"])) != row["original"] or artifact(Path(row["frozen"]["path"])) != row["frozen"]:
                raise RuntimeError("Frozen compiler input seal differs after boundary tests")
        report["status"] = "NATIVE_SAVE_CATALOG_BOUNDARIES_PASS"
        report["native_checks"] = args.expected_checks * 2
        report["replacement_checks"] = sum(row["replacement_checks"] for row in report["runs"])
        report["process_interruption_recovery_cases"] = sum(len(row["crash_runs"]) for row in report["runs"])
        report["replacement_atomic_or_power_loss_durability_claimed"] = False
        report["source_inputs_unchanged"] = True
    except Exception as error:
        report["status"] = "NATIVE_SAVE_CATALOG_BOUNDARIES_FAILED"
        report["error"] = str(error)
        raise
    finally:
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        checkpoint()
    print(json.dumps({"status": report["status"], "native_checks": report["native_checks"],
                      "result": artifact(destination), "gamecore_loaded": False}), flush=True)


if __name__ == "__main__":
    main()
