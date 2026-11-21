"""Freeze and execute the LocalGameCommands city/research component in O2 and Od."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone

from collect_baseline import PROJECT
from native_build import environment_for

SOURCE = PROJECT / "Source/Host/LocalGameCommands.h"
TEST = PROJECT / "Tests/local_city_decision_commands.cpp"
TOOL = Path(__file__).resolve()
EVIDENCE_ROOT = PROJECT / "evidence/local_city_decision_commands"
BUILD_ROOT = PROJECT / "Build/LocalCityDecisionCommands"
VS = Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")

MOCK_SDK = r'''#pragma once
enum PlayerOptionTypes : unsigned { MOCK_PLAYER_OPTION=0 };
enum CommandTypes { NO_COMMAND=-1, MOCK_COMMAND=0 };
enum MissionTypes { NO_MISSION=-1, MOCK_MISSION=0 };
enum TaskTypes { TASK_RAZE=0, TASK_CREATE_PUPPET=19, TASK_ANNEX_PUPPET=20 };
enum OrderTypes { NO_ORDER=-1, ORDER_TRAIN=0, ORDER_CONSTRUCT, ORDER_CREATE, ORDER_MAINTAIN, NUM_ORDER_TYPES };
enum TechTypes { NO_TECH=-1 };
enum PlayerTypes { NO_PLAYER=-1, MOCK_PLAYER=0 };
enum TeamTypes { NO_TEAM=-1 };
enum FromUIDiploEventTypes { NO_FROM_UI_DIPLO_EVENT=-1 };
enum BeliefTypes { NO_BELIEF=-1 };
// CvDLLUtilDefines.h: MAX_CIV_PLAYERS=63, MAX_PLAYERS=MAX_CIV_PLAYERS+1.
static constexpr int MAX_PLAYERS=64;
enum UnitTypes { NO_UNIT=-1 };
enum BuildingTypes { NO_BUILDING=-1 };
enum ProjectTypes { NO_PROJECT=-1 };
enum YieldTypes { NO_YIELD=-1, YIELD_FOOD=0, YIELD_PRODUCTION, YIELD_GOLD, YIELD_SCIENCE, YIELD_CULTURE, YIELD_FAITH };
'''


def sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def artifact(path: Path) -> dict:
    return {"path": str(path), "sha256": sha(path), "bytes": path.stat().st_size}


def check_source_contracts() -> dict:
    commands = SOURCE.read_text(encoding="utf-8")
    session = (PROJECT / "Source/Host/LocalSdkSession.h").read_text(encoding="utf-8")
    services = (PROJECT / "Source/Host/HostServices.h").read_text(encoding="utf-8")
    popup = (PROJECT / "Source/Host/UiPopupContext.h").read_text(encoding="utf-8")
    interactive = (PROJECT / "Source/Host/InteractiveGameSession.h").read_text(encoding="utf-8")
    checks = {
        "optional trailing bind callbacks": "PushOrderHandler orderHandler={},ResearchHandler researchHandler={},CityPurchaseHandler purchaseHandler={}" in commands,
        "city order tuple retained": "orderHandler(command.unitID,command.order,command.data1,command.alt,command.shift,command.control)" in commands,
        "research tuple retained": "researchHandler(command.tech,command.data1,command.stealFrom,command.shift)" in commands,
        "owner and game lock guard": "void RequireCommandOwner() const" in session and "RequireOwnerLock(host_.gameThread==GetCurrentThreadId(),host_.gameLock.HeldByCurrentThread())" in session,
        "four official order categories and append/replace tuples": "ValidateCityOrderEnvelope(cityID,order,data,alt,shift,control)" in session and "order!=ORDER_TRAIN && order!=ORDER_CONSTRUCT && order!=ORDER_CREATE && order!=ORDER_MAINTAIN" in commands and "Both official ProductionPopup append and replace tuples are valid" in commands,
        "city identity validated before receiver": "city->GetOwner()!=active" in session and "ResponseCityPushOrder(active,cityID,order,data,alt,shift,control)" in session,
        "research restricted to normal choice": "discover!=0 || stealFrom!=NO_PLAYER || shift" in session,
        "research bounds and non-null info": "techID>=context.GetNumTechInfos()" in session and "if(!info)throw std::invalid_argument(\"Local research technology has no rules entry\")" in session,
        "purchase yield preserved through engine utility and v2 receiver": "void sendPurchase(int cityID,UnitTypes unit,BuildingTypes building,ProjectTypes project,int purchaseYield) override" in services and "ResponseCityPurchase(active,cityID,unit,building,project,purchaseYield)" in session,
        "local session bind order matches API handler order": session.find("int cityID,OrderTypes order") < session.find("TechTypes tech,int discover") < session.find("int cityID,UnitTypes unit,BuildingTypes building"),
        "purchase owner, item, yield and live-turn validation": "ValidateCityPurchaseEnvelope(cityID,unit,building,project,purchaseYield)" in session and "must name exactly one unit, building, or project" in commands and "Local ProductionPopup purchase supports gold or faith only" in commands and "Local city purchase requires the active human's live turn" in session,
        "project and process IDs require prepared rules index": "validCityProjectTypes.count(data)" in session and "validCityProcessTypes.count(data)" in session and "validCityProjectTypes.count(static_cast<int>(project))" in session and "bool cityItemRulesReady=false" in services,
        "Handler2 query is per-call and synchronously dispatched": "receiver.QueryInterface<ICvNetMessageHandler2>()" in session and "ResponseCityPurchase(active,cityID,unit,building,project,purchaseYield)" in session and "ICvNetMessageHandler2* purchaseReceiver" in session,
        "only requested EngineServices transports added": "void sendPushOrder(" in services and "void sendResearch(" in services,
        "component lifecycle and order tests": TEST.exists(),
        "city task and liberation callbacks remain optional trailing Bind handlers": "CityPurchaseHandler purchaseHandler={},CityTaskHandler cityTaskHandler={},LiberatePlayerHandler liberatePlayerHandler={}" in commands,
        "city decision payload fields delivered exactly": "cityTaskHandler(command.unitID,command.cityTask,command.data1,command.data2,command.taskOption,command.alt,command.shift,command.control)" in commands and "liberatePlayerHandler(command.liberatedPlayer,command.unitID)" in commands,
        "city task and liberation sends reject unbound callbacks": "Local city tasks require a bound SDK receiver" in commands and "Local city liberation requires a bound SDK receiver" in commands,
        "live validators are part of the profile": "CityTaskLegalityValidator canPerformCityTask;" in session and "LiberationLegalityValidator canLiberatePlayer;" in session,
        "city tasks restrict stock choices and exact unmodified tuple": "task!=TASK_RAZE && task!=TASK_CREATE_PUPPET && task!=TASK_ANNEX_PUPPET" in session and "data1!=-1 || data2!=-1 || option || alt || shift || control" in session,
        "city tasks require capture validator and clear adapters before response": "!validator || !validator(cityID,task,data1,data2,option,alt,shift,control)" in session and "city.reset();player.reset();\n                receiver.ResponseCityDoTask(active,cityID,task,data1,data2,option,alt,shift,control);" in session,
        "liberation requires bounded nonactive recipient and exact validator": "liberatedID<0 || liberatedID>=MAX_PLAYERS" in session and "if(liberated==active)" in session and "!validator || !validator(liberated,cityID)" in session,
        "liberation clears SDK adapters before exact response": "city.reset();player.reset();\n                receiver.ResponseLiberatePlayer(active,liberated,cityID);" in session,
        "UI capture routing validates full payload and retains city/recipient identity": "input.data.size()!=5 || input.options.size()!=2" in popup and "captureCity_=input.Data(0);captureOwner_=game_->GetActivePlayer();captureLiberated_=input.Data(4);" in popup,
        "city commands are deferred until the stock callback exits": "pendingCaptureAction_!=0" in popup and "!scripts_.IsQuiescent()" in popup and "engine.sendDoTask(captureCity_,pendingCaptureTask_,-1,-1,false,false,false,false)" in popup,
        "city task legality binds the exact owned capture city and original Lua policy": "!ui_->CaptureDecisionMatches(cityID,-2) || !OwnsCity(cityID)" in interactive and "c:GetOwner()==id" in interactive and "CanRaze" in interactive and "MayNotAnnex" in interactive,
        "liberation eligibility is exact popup Data5 and owned city": "!ui_->CaptureDecisionMatches(cityID,liberatedID)" in interactive and "!OwnsCity(cityID)" in interactive and "captureLiberated_" in popup,
        "host forwards both exact city command shapes": "SendCityTask(cityID,task,data1,data2,option,alt,shift,control)" in services and "SendLiberatePlayer(liberated,cityID)" in services,
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise RuntimeError("Source contract check failed: " + ", ".join(failed))
    return {"scope": "STATIC_SOURCE_CONTRACT_ONLY_NOT_COMPILE_OR_EXECUTION_PROOF", "checks": checks, "count": len(checks)}


def run(command, *, cwd: Path, env: dict, timeout: int) -> subprocess.CompletedProcess:
    args=[str(item) for item in command]
    started=time.monotonic()
    child=subprocess.Popen(args,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    timed_out=False
    try:
        stdout,stderr=child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True
        child.kill()
        stdout,stderr=child.communicate()
    result=subprocess.CompletedProcess(args,child.returncode,stdout,stderr)
    result.child_pid=child.pid
    result.elapsed_seconds=round(time.monotonic()-started,6)
    result.timed_out=timed_out
    return result


def process_record(result: subprocess.CompletedProcess, timeout: int) -> dict:
    return {"child_pid":result.child_pid,"returncode":result.returncode,"timed_out":result.timed_out,
            "timeout_seconds":timeout,"elapsed_seconds":result.elapsed_seconds,
            "creationflags":"CREATE_NO_WINDOW"}


def compile_fixture(compiler: Path, linker: Path, env: dict, frozen_test: Path,
                    frozen_host: Path, frozen_system_roots: list[Path], out: Path,
                    optimization: str) -> dict:
    out.mkdir(parents=True, exist_ok=False)
    obj, exe = out / "fixture.obj", out / "LocalCityDecisionCommands.exe"
    deps, rsp = out / "dependencies.json", out / "compile.rsp"
    flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", optimization,
             "/MD", "/fp:strict", "/utf-8", "/D_CRT_SECURE_NO_WARNINGS", "/c",
             f'/I"{frozen_host}"']
    flags.extend(f'/I"{root}"' for root in frozen_system_roots)
    flags.extend([f'"{frozen_test}"', f'/Fo"{obj}"', f'/sourceDependencies "{deps}"'])
    rsp.write_text("\n".join(flags) + "\n", encoding="utf-8")
    build_env = env.copy()
    build_env["INCLUDE"] = ";".join([str(frozen_host), *(str(root) for root in frozen_system_roots)])
    result = run([compiler, "@" + str(rsp)], cwd=out, env=build_env, timeout=180)
    compile_log = out / "compile.log"; compile_log.write_bytes(result.stdout + result.stderr)
    compile_record=process_record(result,180);(out/"compile_process.json").write_text(json.dumps(compile_record,indent=2)+"\n",encoding="utf-8")
    transcript = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    if result.returncode or re.search(r"\bwarning\s+[A-Z]?\d+", transcript, re.I):
        raise RuntimeError(f"{optimization} compile failed or emitted a warning: {transcript[-5000:]}")
    link_rsp = out / "link.rsp"
    link_rsp.write_text("\n".join(["/nologo", f'"{obj}"', f'/OUT:"{exe}"', "/INCREMENTAL:NO",
                                  "/MACHINE:X64", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF"]) + "\n", encoding="utf-8")
    linked = run([linker, "@" + str(link_rsp)], cwd=out, env=build_env, timeout=120)
    link_log = out / "link.log"; link_log.write_bytes(linked.stdout + linked.stderr)
    link_record=process_record(linked,120);(out/"link_process.json").write_text(json.dumps(link_record,indent=2)+"\n",encoding="utf-8")
    link_text = (linked.stdout + linked.stderr).decode("mbcs", errors="replace")
    if linked.returncode or re.search(r"\bwarning\s+[A-Z]?\d+", link_text, re.I):
        raise RuntimeError(f"{optimization} link failed or emitted a warning: {link_text[-5000:]}")
    executed = run([exe], cwd=out, env=build_env, timeout=30)
    output = (executed.stdout + executed.stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
    execution_log = out / "execution.log"; execution_log.write_text(output, encoding="utf-8")
    execution_record=process_record(executed,30);(out/"execution_process.json").write_text(json.dumps(execution_record,indent=2)+"\n",encoding="utf-8")
    match = re.search(r"^LOCAL_CITY_DECISION_COMMANDS_PASS checks=(\d+) GAMECORE_LOADED=false MOCK_SDK=true$", output, re.M)
    if executed.returncode or not match or int(match.group(1)) < 28:
        raise RuntimeError(f"{optimization} execution failed (exit={executed.returncode}) or had too few checks: {output[-4000:]}")
    dep_data = json.loads(deps.read_text(encoding="utf-8-sig"))["Data"]
    if Path(dep_data["Source"]).resolve() != frozen_test.resolve():
        raise RuntimeError(f"{optimization} did not compile the frozen test input")
    return {"optimization": optimization, "checks": int(match.group(1)),
            "executable": artifact(exe), "object": artifact(obj), "compile_response": artifact(rsp),
            "link_response": artifact(link_rsp), "dependencies": artifact(deps),
            "processes":{"compile":compile_record,"link":link_record,"execute":execution_record},
            "compile_log": artifact(compile_log), "link_log": artifact(link_log),
            "execution_log": artifact(execution_log), "compiler_inputs": [Path(dep_data["Source"]),
                *(Path(item) for item in dep_data["Includes"])]}


def main() -> None:
    if len(sys.argv) != 1:
        raise RuntimeError("No switches supported; verifier performs only the isolated O2/Od component builds")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    evidence = EVIDENCE_ROOT / run_id
    build = BUILD_ROOT / run_id
    evidence.mkdir(parents=True, exist_ok=False); build.mkdir(parents=True, exist_ok=False)
    source_contracts = check_source_contracts()
    live_paths = {"command_header": SOURCE, "test": TEST, "verifier": TOOL}
    before = {key: artifact(path) for key, path in live_paths.items()}
    frozen = evidence / "frozen_inputs"; frozen_host = frozen / "Source/Host"
    frozen_host.mkdir(parents=True)
    frozen_source = frozen_host / "LocalGameCommands.h"
    frozen_test = frozen / "Tests/local_city_decision_commands.cpp"
    frozen_test.parent.mkdir(parents=True)
    shutil.copy2(SOURCE, frozen_source); shutil.copy2(TEST, frozen_test)
    mock_header = frozen_host / "SdkHostIncludes.h"; mock_header.write_text(MOCK_SDK, encoding="utf-8", newline="\n")
    frozen_tool = frozen / "tools/verify_local_city_decision_commands.py"
    frozen_tool.parent.mkdir(parents=True); shutil.copy2(TOOL, frozen_tool)
    mock_note = frozen / "mock_sdk_scope.txt"
    mock_note.write_text("Source-shaped enum/constant fixture only. LocalGameCommands.h is the exact frozen production header. No SDK binaries, Host executable, provider, GameCore module, or Civ V process is loaded.\n", encoding="utf-8")
    frozen_paths = [frozen_source, frozen_test, mock_header, frozen_tool, mock_note]
    frozen_hashes = {str(path.relative_to(evidence)): sha(path) for path in frozen_paths}
    if sha(SOURCE) != sha(frozen_source) or sha(TEST) != sha(frozen_test) or sha(TOOL) != sha(frozen_tool):
        raise RuntimeError("Frozen project input hash mismatch")

    env_dir = build / "environment"
    env, compiler_name = environment_for(VS, "x64", env_dir)
    compiler = Path(compiler_name).resolve(); linker = compiler.with_name("link.exe")
    compiler_before, linker_before = artifact(compiler), artifact(linker)
    include_roots = [Path(item).resolve() for item in env.get("INCLUDE", "").split(";") if item and Path(item).is_dir()]
    if not include_roots: raise RuntimeError("MSVC compiler include roots were unavailable")

    # Discover the actual CRT/Windows header closure used by this frozen mock fixture.
    discovery = build / "dependency_discovery"; discovery.mkdir()
    discovery_obj, discovery_deps, discovery_rsp = discovery / "fixture.obj", discovery / "dependencies.json", discovery / "compile.rsp"
    discovery_flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/O2", "/MD", "/fp:strict", "/utf-8", "/c",
                       f'/I"{frozen_host}"', f'"{frozen_test}"', f'/Fo"{discovery_obj}"', f'/sourceDependencies "{discovery_deps}"']
    discovery_rsp.write_text("\n".join(discovery_flags) + "\n", encoding="utf-8")
    discovered = run([compiler, "@" + str(discovery_rsp)], cwd=discovery, env=env, timeout=180)
    discovery_log = discovery / "discovery.log"; discovery_log.write_bytes(discovered.stdout + discovered.stderr)
    discovery_record=process_record(discovered,180);(discovery/"discovery_process.json").write_text(json.dumps(discovery_record,indent=2)+"\n",encoding="utf-8")
    discovery_text = (discovered.stdout + discovered.stderr).decode("mbcs", errors="replace")
    if discovered.returncode or re.search(r"\bwarning\s+[A-Z]?\d+", discovery_text, re.I):
        raise RuntimeError("Compiler dependency discovery failed: " + discovery_text[-4000:])
    dep_data = json.loads(discovery_deps.read_text(encoding="utf-8-sig"))["Data"]
    if Path(dep_data["Source"]).resolve() != frozen_test.resolve(): raise RuntimeError("Discovery compiled an unexpected source")
    consumed = {Path(dep).resolve() for dep in dep_data["Includes"]}
    consumed_system = {header for header in consumed if not header.is_relative_to(frozen.resolve())}
    root_map = {root: frozen / "compiler_headers" / f"root_{index:03d}" for index, root in enumerate(include_roots)}
    for target_root in root_map.values(): target_root.mkdir(parents=True, exist_ok=True)
    frozen_header_map = {}
    for header in sorted(consumed_system, key=lambda path: str(path).casefold()):
        root = next((candidate for candidate in include_roots if header.is_relative_to(candidate)), None)
        if root is None: raise RuntimeError(f"Compiler consumed header outside the MSVC include roots: {header}")
        target = root_map[root] / header.relative_to(root); target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(header, target)
        if sha(header) != sha(target): raise RuntimeError(f"Compiler header freeze mismatch: {header}")
        frozen_header_map[header] = target
    frozen_system_roots = list(root_map.values())
    configs = []
    for label, opt in (("optimized_O2", "/O2"), ("unoptimized_Od", "/Od")):
        report = compile_fixture(compiler, linker, env, frozen_test, frozen_host, frozen_system_roots, build / label, opt)
        actual = {Path(item).resolve() for item in report.pop("compiler_inputs")}
        expected = {frozen_test.resolve(), frozen_source.resolve(), mock_header.resolve(), *(path.resolve() for path in frozen_header_map.values())}
        if actual != expected:
            raise RuntimeError(f"{label} compiler closure mismatch: missing={actual-expected}; extra={expected-actual}")
        if any(not path.is_relative_to(frozen.resolve()) for path in actual):
            raise RuntimeError(f"{label} consumed mutable non-frozen compiler inputs")
        report["compiler_inputs"] = [artifact(path) for path in sorted(actual, key=lambda path: str(path).casefold())]
        configs.append(report)

    after = {key: artifact(path) for key, path in live_paths.items()}
    if before != after: raise RuntimeError("Live source/test/verifier changed during component verification")
    if artifact(compiler) != compiler_before or artifact(linker) != linker_before:
        raise RuntimeError("Compiler or linker changed during component verification")
    if any(sha(source) != sha(frozen_header_map[source]) for source in frozen_header_map):
        raise RuntimeError("A consumed MSVC input changed during the component build")
    if any(sha(path) != frozen_hashes[str(path.relative_to(evidence))] for path in frozen_paths):
        raise RuntimeError("A frozen component input changed during build")
    report = {"status": "LOCAL_CITY_DECISION_COMMANDS_COMPONENT_PASS", "run_id": run_id,
              "source_contract_checks": source_contracts,
              "dependency_discovery_process": discovery_record,
              "test": before["test"], "production_header": before["command_header"], "verifier": before["verifier"],
              "frozen_inputs": [{"path": str(path.relative_to(evidence)), "sha256": frozen_hashes[str(path.relative_to(evidence))]} for path in frozen_paths],
              "compiler": compiler_before, "linker": linker_before, "compiler_header_copies": [
                  {"original_source": str(source), **artifact(target)} for source, target in frozen_header_map.items()],
              "configs": configs, "checks": {row["optimization"]: row["checks"] for row in configs},
              "mock_sdk_used": True, "sdk_dll_loaded": False, "gamecore_loaded": False, "host_executable_built": False,
              "scope": "FROZEN_PRODUCTION_LOCALGAMECOMMANDS_HEADER_WITH_SOURCE_SHAPED_MOCK_SDK_TYPES_TESTED_INDEPENDENTLY_OF_HOST_AND_GAMECORE",
              "limitations": "The mock SDK fixture executes LocalGameCommands transport only: it covers task/liberation and pantheon FIFO and exact tuple/payload retention, optional/unbound handlers, callback failure propagation, reentrancy rejection, cancellation and callback lifetime. Source-contract checks inspect LocalSdkSession validators, popup payload gating and HostServices forwarding, but do not compile those files or execute stock Lua CanRaze/MayNotAnnex/pantheon legality. It does not prove Civ V receiver acceptance, faith changes, notification expiry or in-game effects.",
              "evidence_directory": str(evidence)}
    out = evidence / "conformance.json"; out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "run_id": run_id, "source_contract_checks": source_contracts["count"],
                      "checks": report["checks"], "evidence": artifact(out), "mock_sdk_used": True, "gamecore_loaded": False}))


if __name__ == "__main__":
    main()
