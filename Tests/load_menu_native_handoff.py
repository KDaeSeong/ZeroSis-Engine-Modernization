"""Run extracted production handoff methods with explicit SDK/UI/window fixtures.

No Host, GameCore, HWND, retail installation, MODS or user-save access occurs.
This is a native component proof of the extracted methods, not live gameplay.
"""
from __future__ import annotations

from datetime import datetime, timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import secrets
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "tools"))
from collect_baseline import pe_header
from native_build import environment_for, run
from verify_bitmap_window import run_owned_test

SOURCE_NAMES = ("InteractiveUiSession.h", "InteractiveGameSession.h", "InteractiveGameLoop.h", "HostRun.h", "HostMain.cpp", "UiPopupContext.h")
SOURCES = {name: PROJECT / "Source/Host" / name for name in SOURCE_NAMES}
TEMPLATE = Path(__file__).with_suffix(".cpp.in")
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")


def seal(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def block(text, marker):
    """Extract one unchanged C++ brace block, ignoring comments/string braces."""
    if text.count(marker) != 1:
        raise RuntimeError(f"Expected one production marker: {marker}")
    start = text.index(marker)
    opening = text.index("{", start)
    parameters = text.find("(", start, opening)
    if parameters != -1:
        nesting, cursor = 1, parameters + 1
        while nesting and cursor < len(text):
            if text[cursor] == "(":
                nesting += 1
            elif text[cursor] == ")":
                nesting -= 1
            cursor += 1
        if nesting:
            raise RuntimeError(f"Unclosed C++ signature: {marker}")
        opening = text.index("{", cursor)
    depth, index, mode = 1, opening + 1, None
    while index < len(text):
        ch, following = text[index], text[index:index + 2]
        if mode in {"string", "char"}:
            if ch == "\\":
                index += 2
                continue
            if ch == ('"' if mode == "string" else "'"):
                mode = None
        elif mode == "line":
            if ch == "\n":
                mode = None
        elif mode == "comment":
            if following == "*/":
                mode = None
                index += 2
                continue
        elif following in {"//", "/*"}:
            mode = "line" if following == "//" else "comment"
            index += 2
            continue
        elif ch in {'"', "'"}:
            mode = "string" if ch == '"' else "char"
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if not depth:
                return text[start:index + 1]
        index += 1
    raise RuntimeError(f"Unclosed C++ production block: {marker}")


def generated_source(texts, close_before=None):
    game, ui = texts["InteractiveGameSession.h"], texts["InteractiveUiSession.h"]
    loop, host, main = texts["InteractiveGameLoop.h"], texts["HostRun.h"], texts["HostMain.cpp"]
    popup = texts["UiPopupContext.h"]
    close = block(popup, "void CloseInformationalPopup(){")
    load_close = block(close, "if(kind_==UiPopupKind::LoadMenu){")
    # Retain the exact production prologue and LoadMenu branch. Other popup
    # kinds are deliberately outside this focused boundary fixture.
    close = close[:close.index("        if(kind_==UiPopupKind::SaveMenu){")] + "    }"
    if close_before is not None:
        close = close.replace(load_close, close_before["fragment"])
    dispatch = block(popup, "bool DispatchInput(UiInputKind kind,std::uint64_t key,double delta=0.0){")
    update = block(ui, "bool Update(){")
    methods = {"DTO": block(game, "struct LoadHandoff final") + ";",
               "OWNER": block(game, "void Owner() const"),
               "CAPTURE": block(game, "std::shared_ptr<const UiLoadMenuCatalog> CaptureLoadMenuCatalog()"),
               "HAS_PENDING": block(game, "bool HasPendingLoad()"),
               "TAKE": block(game, "LoadHandoff TakePendingLoad()"),
               "DISPATCH": block(game, "bool DispatchUi(const ZeroSisPresentation::BitmapInputEvent& input)"),
               "APPLY": block(game, "void ApplyLoadMenuRequests(const std::vector<LoadMenuRequest>& requests)"),
               "PATH": block(game, "static std::wstring LoadFileName(const std::string& path)"),
               "CHECK": block(game, "void Check()"),
               "FINISH": block(ui, "void FinishLoadMenuForLoad()"),
               "UI_REQUIRE": block(ui, "void Require() const"),
               "HOST_PLAY": block(host, "InteractiveGameSession::LoadHandoff InteractivePlay("),
               "HOST_SHUTDOWN": block(host, "void Shutdown()"),
               "MAIN_PLAY": block(main, "if(play){"),
               "LOOP_EXIT": block(loop, "if(loadHandoff.archive){"),
               "POPUP_OPEN_LOAD": block(popup, "void OpenLoadMenu(){"),
               "POPUP_TAKE_LOAD": block(popup, "std::vector<LoadMenuRequest> TakeLoadMenuRequests(){"),
               "POPUP_HAS_LOAD": block(popup, "bool HasPendingLoadMenuRequests() const"),
               "POPUP_CLOSE_LOAD_PREFIX": close,
               "POPUP_DISPATCH_LOAD": block(dispatch, "if(kind_==UiPopupKind::LoadMenu){"),
               "POPUP_REQUIRE": block(popup, "void Require() const"),
               "POPUP_OWNED_PLAYER": block(popup, "void RequireOwnedMenuPlayer(){"),
               "POPUP_LOAD_OWNER": block(popup, "void RequireLoadMenuOwner(){"),
               "POPUP_FIND_LOAD": block(popup, "const UiSaveMenuFile& FindLoadMenuFile(const char* path){"),
               "POPUP_CAN_LOAD": block(popup, "bool CanLoadMenuFile(const UiSaveMenuFile& file){"),
               "POPUP_QUEUE_LOAD": block(popup, "void QueueLoadMenuRequest(LoadMenuRequest::Kind kind,const char* path){"),
               "POPUP_STOP": block(popup, "void Stop(){"),
               "POPUP_FAULT": block(popup, "void Fault() noexcept"),
               "WINDOW_CLOSE_REQUIRE": block(ui, "void Require() const"),
               "WINDOW_CLOSE_CURRENT": block(ui, "void CloseCurrent(){"),
               "WINDOW_CLOSE_ALL": block(ui, "void CloseAll(){"),
               "WINDOW_CLOSE_RETURN": block(update, "if(popup_ && kind_==UiPopupKind::LoadMenu && !popup_->IsActive()){")}
    begin = block(game, "void Begin(ICvGameContext3& context,")
    boundary = begin.index("game_.reset(context.GetGame())")
    methods["BEGIN_PREFIX"] = begin[:boundary] + "usedRestored_=restored;\n    }"
    dispatch_start = loop.index("const bool consumed=live.DispatchUi(input);")
    pending = block(loop, "if(live.HasPendingLoad()){")
    dispatch_end = loop.index(pending, dispatch_start) + len(pending)
    methods["LOOP_DISPATCH"] = loop[dispatch_start:dispatch_end]
    gate = "if(loadHandoff.archive)return;"
    if loop.count(gate) != 1 or loop.index(gate) > loop.index("if(live.Tick())redraw=true;"):
        raise RuntimeError("Production loop lacks the pre-tick handoff barrier")
    methods["LOOP_GATE"] = gate
    rendered = TEMPLATE.read_text(encoding="utf-8")
    for name, value in methods.items():
        token = "@@" + name + "@@"
        if rendered.count(token) != 1:
            raise RuntimeError(f"Template production slot mismatch: {token}")
        rendered = rendered.replace(token, value)
    if "@@" in rendered:
        raise RuntimeError("An unresolved production extraction slot remains")
    return rendered, {name: {"bytes": len(value.encode("utf-8")), "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest()}
                      for name, value in methods.items()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-close-before", action="store_true",
                        help="Replay the previously observed defective LoadMenu close branch; a failing regression is expected.")
    args = parser.parse_args()
    close_before_path = PROJECT / "evidence/load_menu/native_handoff/close_regression_before.json"
    close_before = json.loads(close_before_path.read_text(encoding="utf-8")) if args.replay_close_before else None
    if close_before is not None:
        fragment = close_before["fragment"].encode("utf-8")
        if hashlib.sha256(fragment).hexdigest() != close_before["fragment_sha256"]:
            raise RuntimeError("Historical observed close fragment changed")
    before = [seal(path) for path in SOURCES.values()]
    texts = {name: path.read_text(encoding="utf-8") for name, path in SOURCES.items()}
    source, fragments = generated_source(texts, close_before)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + secrets.token_hex(6)
    build = PROJECT / "Build/LoadMenuHandoff" / run_id
    evidence = PROJECT / "evidence/load_menu/native_handoff/attempts" / run_id
    build.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    report = {"schema": "ZEROSIS_EXTRACTED_LOAD_HANDOFF_COMPONENT_V2", "status": "IN_PROGRESS",
              "run_id": run_id, "sources": before, "extracted_fragments": fragments,
              "runner": seal(Path(__file__)), "template": seal(TEMPLATE), "runs": [],
              "sdk_ui_and_window_dependencies_mocked": True, "actual_gamecore_or_host_executed": False,
              "actual_hwnd_created": False, "retail_files_accessed": False, "live_gameplay_verified": False,
              "historical_close_replay": args.replay_close_before,
              "historical_close_fragment": seal(close_before_path) if close_before is not None else None,
              "historical_component_report": "20261015T123914Z_1e0e1c528212/result.json",
              "historical_host_syntax_report": "20261015T124615Z_0466b0ca28b2/result.json",
              "scope": "Exact production methods/fragments including UiPopupContext LoadMenu close/input/request/Stop/Fault and router CloseCurrent/CloseAll/LoadMenu return. SDK/Lua callback execution, catalog filesystem, cursor OS calls, parent GameMenu close, fresh-core initialization and window dependencies are explicit fixtures. Historical replay replaces only the observed prior LoadMenu close branch and is not a claim to replay the complete older source."}
    destination = evidence / "result.json"
    def checkpoint():
        destination.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    checkpoint()
    try:
        generated = build / "handoff.cpp"
        generated.write_text(source, encoding="utf-8")
        report["generated_source"] = seal(generated)
        contracts = build / "contracts"
        contracts.mkdir()
        report["contract_inputs"] = []
        for name in ("UiLoadMenuContract.h", "UiSaveMenuContract.h"):
            original = PROJECT / "Source/Host" / name
            frozen = contracts / name
            frozen.write_bytes(original.read_bytes())
            report["contract_inputs"].append({"observed": seal(original), "frozen": seal(frozen)})
        env, compiler = environment_for(VS, "x64", build)
        env["VSLANG"] = "1033"
        report["compiler"] = seal(Path(compiler))
        variants = (("optimized", "/O2"),) if args.replay_close_before else (("optimized", "/O2"), ("unoptimized", "/Od"))
        for flavor, optimization in variants:
            directory = build / flavor
            directory.mkdir()
            executable = directory / "handoff.exe"
            dependencies = directory / "dependencies.json"
            arguments = [compiler, "/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/MT", optimization,
                         "/source-charset:utf-8", "/DZEROSIS_UI_WINDOW_PRESENTATION", "/D_CRT_SECURE_NO_WARNINGS",
                         "/I" + str(contracts), str(generated), "/Fo" + str(directory) + "\\",
                         "/Fe" + str(executable), "/sourceDependencies", str(dependencies),
                         "/link", "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX", "wer.lib"]
            row = {"flavor": flavor, "status": "COMPILING", "optimization": optimization}
            report["runs"].append(row)
            checkpoint()
            compiled = run(arguments, cwd=directory, env=env, timeout=180)
            transcript = (compiled.stdout + compiled.stderr).decode("mbcs", errors="replace")
            log = directory / "compile.log"
            log.write_text(transcript, encoding="utf-8")
            row.update(compiler_exit_code=compiled.returncode, compile_log=seal(log))
            checkpoint()
            if compiled.returncode or re.search(r"\bwarning\s+[A-Z]+\d+", transcript, re.I):
                raise RuntimeError(f"{flavor} compilation failed or warned: {log}\n{transcript[-3500:]}")
            if [seal(path) for path in SOURCES.values()] != before:
                raise RuntimeError("A production handoff source changed during compilation")
            imports = run([str(Path(compiler).with_name("dumpbin.exe")), "/nologo", "/imports", str(executable)],
                          cwd=directory, env=env, timeout=30)
            import_text = (imports.stdout + imports.stderr).decode("mbcs", errors="replace")
            import_log = directory / "imports.log"
            import_log.write_text(import_text, encoding="utf-8")
            dlls = sorted(set(re.findall(r"^\s*([A-Za-z0-9_.-]+\.dll)\s*$", import_text, re.M | re.I)), key=str.lower)
            if imports.returncode or not dlls or any(re.search(r"gamecore|zerosis|lua", value, re.I) for value in dlls):
                raise RuntimeError("Headless test PE has unexpected or unverified imports")
            if re.search(r"\b(?:LoadLibrary[A-Za-z]*|GetProcAddress)\s*\(", source):
                raise RuntimeError("Extracted headless source contains an explicit dynamic module-loader call")
            pe = pe_header(executable)
            if pe["architecture"] != "x64":
                raise RuntimeError("Headless test is not x64")
            row.update(status="RUNNING", executable=seal(executable), pe=pe, imports=dlls, imports_log=seal(import_log),
                       explicit_source_module_loading_calls=False)
            checkpoint()
            execution = run_owned_test([str(executable)], cwd=directory, env=env, timeout=30)
            runtime_text = execution.pop("stdout") + execution.pop("stderr")
            runtime_log = directory / "execution.log"
            runtime_log.write_text(runtime_text, encoding="utf-8")
            row.update(execution=execution, execution_log=seal(runtime_log))
            checkpoint()
            marker = re.search(r"EXTRACTED_LOAD_HANDOFF_PASS cases=(\d+) checks=(\d+) GAMECORE_ACTUAL_LOADED=false HWND_CREATED=false", runtime_text)
            if execution["returncode"] or execution["timed_out"] or not marker or "FAULT_UI_SUPPRESSED ERROR_MODE=32771 WER_FLAGS=32" not in runtime_text:
                raise RuntimeError(f"{flavor} extracted-method test failed: {runtime_log}\n{runtime_text[-3500:]}")
            row.update(status="PASS", cases=int(marker[1]), checks=int(marker[2]), compiler_and_linker_warnings=0)
            checkpoint()
        if [seal(path) for path in SOURCES.values()] != before:
            raise RuntimeError("A production handoff source changed during the tests")
        if len({(row["cases"], row["checks"]) for row in report["runs"]}) != 1:
            raise RuntimeError("Optimization variants executed different case/check counts")
        report.update(status="PASS", sources_after=[seal(path) for path in SOURCES.values()],
                      total_checks=sum(row["checks"] for row in report["runs"]))
    except Exception as exc:
        report.update(status="FAIL", error=str(exc), sources_after=[seal(path) for path in SOURCES.values()])
        checkpoint()
        print(json.dumps({"status": "FAIL", "report": str(destination), "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
    checkpoint()
    print(json.dumps({"status": "PASS", "report": str(destination), "build": str(build),
                      "cases_per_flavor": report["runs"][0]["cases"], "total_checks": report["total_checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
