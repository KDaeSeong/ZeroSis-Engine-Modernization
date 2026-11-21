"""Compile and run production exit methods against explicit headless fixtures.

This runs only a small console component. Host/GameCore/SDK/Lua modules, HWND,
GPU, installed game files, MODS and user saves are not accessed or executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
from collect_baseline import pe_header
from native_build import environment_for, run
from verify_bitmap_window import run_owned_test
from load_menu_native_handoff import block

TEMPLATE = Path(__file__).with_suffix(".cpp.in")
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
SOURCE_NAMES = ("UiPopupContext.h", "InteractiveUiSession.h", "InteractiveGameSession.h", "InteractiveGameLoop.h", "UiInputDispatch.h")


def seal(path: Path) -> dict:
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def generate(texts: dict[str, str]) -> tuple[str, dict, dict]:
    popup = texts["UiPopupContext.h"]
    ui = texts["InteractiveUiSession.h"]
    session = texts["InteractiveGameSession.h"]
    loop = texts["InteractiveGameLoop.h"]
    inputs = texts["UiInputDispatch.h"]
    dispatch = block(popup, "bool DispatchInput(UiInputKind kind,std::uint64_t key,double delta=0.0){")
    update = block(ui, "bool Update(){")
    fragments = {
        "POPUP_KIND": block(popup, "enum class UiPopupKind ") + ";",
        "MENU_REQUEST": block(popup, "struct GameMenuRequest final ") + ";",
        "INPUT_KIND": block(inputs, "enum class UiInputKind ") + ";",
        "INPUT_REQUEST": block(inputs, "struct UiInputRequest final ") + ";",
        "INPUT_TARGET": block(inputs, "struct UiInputTarget final ") + ";",
        "POPUP_REQUIRE": block(popup, "void Require() const "),
        "LOCAL_PLAYER": block(popup, "void RequireLocalMenuPlayer(int owner,int turn)"),
        "OWNED_PLAYER": block(popup, "void RequireOwnedMenuPlayer()"),
        "EXIT_OWNER": block(popup, "void RequireExitConfirmOwner()"),
        "GAME_OWNER": block(popup, "void RequireGameMenuOwner()"),
        "MARK_CLOSED": block(popup, "void MarkExitConfirmClosed()"),
        "QUEUE_EXIT": block(popup, "void QueueConfirmedExit()"),
        "QUEUE_MENU": block(popup, "void QueueGameMenuRequest(GameMenuRequest::Kind kind,const char* action)"),
        "TAKE_MENU": block(popup, "std::vector<GameMenuRequest> TakeGameMenuRequests()"),
        "HAS_MENU": block(popup, "bool HasPendingGameMenuRequests() const "),
        "OPEN_POPUP": block(popup, "void OpenExitConfirm()"),
        "POPUP_DISPATCH": block(dispatch, "if(kind_==UiPopupKind::ExitConfirm){"),
        "OPEN_ROUTER": block(ui, "void OpenExitConfirm()"),
        "FINISH_ROUTER": block(ui, "void FinishExitConfirmForExit()"),
        "CHILD_RETURN": block(update, "if(popup_ && kind_==UiPopupKind::ExitConfirm && !popup_->IsActive()){ ".rstrip()),
        "SESSION_OWNER": block(session, "void Owner() const"),
        "SESSION_CHECK": block(session, "void Check()"),
        "SESSION_PENDING": block(session, "bool HasPendingExit()"),
        "SESSION_APPLY": block(session, "void ApplyGameMenuRequests(const std::vector<GameMenuRequest>& requests)"),
        "SESSION_DISPATCH": block(session, "bool DispatchUi(const ZeroSisPresentation::BitmapInputEvent& input)"),
    }
    rendered = TEMPLATE.read_text(encoding="utf-8")
    for name, value in fragments.items():
        token = "@@" + name + "@@"
        if rendered.count(token) != 1:
            raise RuntimeError(f"Production template slot mismatch: {token}")
        rendered = rendered.replace(token, value)
    if "@@" in rendered:
        raise RuntimeError("Unresolved production fragment remains")
    if re.search(r"\b(?:LoadLibrary[A-Za-z]*|GetProcAddress)\s*\(", rendered):
        raise RuntimeError("Console component contains an explicit module-loader call")
    input_barrier = block(loop, "if(live.HasPendingExit()){")
    exit_branch = block(loop, "if(menuExitRequested){")
    gate = "if(loadHandoff.archive || menuExitRequested)return;"
    position = loop.index("const bool consumed=live.DispatchUi(input);")
    static_checks = {
        "dispatch_before_exit_barrier": position < loop.index(input_barrier, position),
        "exit_barrier_ends_input_batch": "menuExitRequested=true;acted=true;break;" in input_barrier,
        "exit_cannot_also_load": "if(live.HasPendingLoad())throw" in input_barrier,
        "pre_tick_gate_present_once": loop.count(gate) == 1,
        "gate_before_tick_and_update": loop.index(gate) < loop.index("if(live.Tick())redraw=true;") < loop.index("live.UpdateUi()", loop.index(gate)),
        "exit_before_load_and_save_close": loop.index(exit_branch) < loop.index("if(loadHandoff.archive){", loop.index(exit_branch)) < loop.index("live.Save();SdkStateSnapshot::Write", loop.index(exit_branch)),
        "exit_has_no_save_or_tick": not re.search(r"live\.(?:Save|Tick|UpdateUi)\s*\(", exit_branch),
        "existing_smoke_may_not_skip_sequence": "if(smoke)throw" in exit_branch,
        "exit_returns_empty_load_handoff": "return {};" in exit_branch,
        "stop_clears_pending_exit": "pendingExit_=false;" in block(session, "void Stop()"),
    }
    if not all(static_checks.values()):
        raise RuntimeError("Source-only loop/Stop gate failed: " + repr(static_checks))
    metadata = {name: {"bytes": len(value.encode("utf-8")), "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()}
                for name, value in fragments.items()}
    return rendered, metadata, {"classification": "SOURCE_ONLY_NOT_EXECUTED_LOOP_OR_NATIVE_SHUTDOWN", "checks": static_checks}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attempt", default="current")
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z0-9_]{1,24}", args.attempt):
        raise SystemExit("Invalid owned component attempt name")
    sources = {name: PROJECT / "Source/Host" / name for name in SOURCE_NAMES}
    before = [seal(path) for path in sources.values()]
    texts = {name: path.read_text(encoding="utf-8-sig").replace("\r\n", "\n") for name, path in sources.items()}
    generated, fragments, source_checks = generate(texts)
    build = PROJECT / "Build/GameMenuExitComponent" / args.attempt
    evidence = PROJECT / "evidence/game_menu/offline_exit"
    if build.exists():
        raise RuntimeError("Owned attempt already exists; choose a distinct small retry name")
    build.mkdir(parents=True)
    evidence.mkdir(parents=True, exist_ok=True)
    result_path = evidence / ("cpp_tests.json" if args.attempt == "current" else f"cpp_tests_{args.attempt}.json")
    if result_path.exists():
        raise RuntimeError("Component report already exists; refusing replacement")
    report = {
        "schema": "zerosis.game_menu_exit.extracted_cpp.v1", "status": "IN_PROGRESS",
        "attempt": args.attempt, "build": str(build), "sources_before": before,
        "runner": seal(Path(__file__)), "template": seal(TEMPLATE), "fragments": fragments,
        "source_only_checks": source_checks, "runs": [],
        "scope": "Exact production popup owner/input/close/request/handoff, UI router child open/return/finish and session menu/dispatch methods. Protected Lua callbacks, SDK interfaces, filesystem directory creation, ordinary parent close/release and window/core ownership are explicit fixtures. Loop barriers and Stop pending reset are source-only checks.",
        "host_or_gamecore_executed": False, "gamecore_or_lua_module_loaded": False,
        "hwnd_created": False, "gpu_or_clr_used": False, "retail_mods_or_user_saves_accessed": False,
        "live_gameplay_or_shutdown_verified": False,
    }

    def checkpoint() -> None:
        result_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    checkpoint()
    try:
        source = build / "exit_component.cpp"
        source.write_text(generated, encoding="utf-8")
        report["generated_source"] = seal(source)
        environment, compiler = environment_for(VS, "x64", build)
        environment["VSLANG"] = "1033"
        report["compiler"] = seal(Path(compiler))
        for name, optimization in (("optimized", "/O2"), ("unoptimized", "/Od")):
            directory = build / name
            directory.mkdir()
            executable = directory / "exit_component.exe"
            arguments = [compiler, "/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/MT", optimization,
                         "/source-charset:utf-8", "/D_CRT_SECURE_NO_WARNINGS", str(source),
                         "/Fo" + str(directory) + "\\", "/Fe" + str(executable),
                         "/sourceDependencies", str(directory / "dependencies.json")]
            if optimization == "/Od":
                arguments.append("/RTC1")
            arguments += ["/link", "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX", "wer.lib"]
            row = {"flavor": name, "status": "COMPILING"}
            report["runs"].append(row)
            checkpoint()
            completed = run(arguments, cwd=directory, env=environment, timeout=180)
            transcript = (completed.stdout + completed.stderr).decode("mbcs", errors="replace")
            log = directory / "compile.log"
            log.write_text(transcript, encoding="utf-8")
            row.update(compiler_exit_code=completed.returncode, compile_log=seal(log))
            checkpoint()
            if completed.returncode or re.search(r"\bwarning\s+[A-Z]+\d+", transcript, re.I):
                raise RuntimeError(f"{name} compile failed or warned: {transcript[-2600:]}")
            if [seal(path) for path in sources.values()] != before:
                raise RuntimeError("Production input changed during component compilation")
            pe = pe_header(executable)
            if pe["architecture"] != "x64":
                raise RuntimeError("Console component architecture mismatch")
            imported = run([str(Path(compiler).with_name("dumpbin.exe")), "/nologo", "/imports", str(executable)], cwd=directory, env=environment, timeout=30)
            import_text = (imported.stdout + imported.stderr).decode("mbcs", errors="replace")
            dlls = sorted(set(re.findall(r"^\s*([A-Za-z0-9_.-]+\.dll)\s*$", import_text, re.M | re.I)), key=str.lower)
            if imported.returncode or not dlls or any(re.search(r"gamecore|zerosis|lua|user32|d3d|granny|clr", value, re.I) for value in dlls):
                raise RuntimeError("Console component imports an unexpected application/UI/render dependency")
            row.update(status="RUNNING", executable=seal(executable), pe=pe, imports=dlls)
            checkpoint()
            execution = run_owned_test([str(executable)], cwd=directory, env=environment, timeout=30)
            output = execution.pop("stdout") + execution.pop("stderr")
            output_log = directory / "execution.log"
            output_log.write_text(output, encoding="utf-8")
            row.update(execution=execution, execution_log=seal(output_log))
            marker = re.search(r"EXTRACTED_GAME_MENU_EXIT_PASS cases=(\d+) checks=(\d+) GAMECORE_ACTUAL_LOADED=false HWND_CREATED=false", output)
            if execution["returncode"] or execution["timed_out"] or not marker or "FAULT_UI_SUPPRESSED ERROR_MODE=32771 WER_FLAGS=32" not in output:
                raise RuntimeError(f"{name} component failed: {output[-2600:]}")
            row.update(status="PASS", cases=int(marker[1]), checks=int(marker[2]), warnings=0)
            checkpoint()
        report["sources_after"] = [seal(path) for path in sources.values()]
        if report["sources_after"] != before:
            raise RuntimeError("Production input changed during component execution")
        if len({(row["cases"], row["checks"]) for row in report["runs"]}) != 1:
            raise RuntimeError("Optimization variants executed different test counts")
        report.update(status="PASS", total_checks=sum(row["checks"] for row in report["runs"]))
    except Exception as error:
        report.update(status="FAIL", error=str(error))
        checkpoint()
        print(json.dumps({"status": "FAIL", "report": str(result_path), "error": str(error)}, ensure_ascii=False))
        raise SystemExit(1)
    checkpoint()
    print(json.dumps({"status": "PASS", "report": str(result_path), "build": str(build), "cases_per_variant": report["runs"][0]["cases"], "total_checks": report["total_checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
