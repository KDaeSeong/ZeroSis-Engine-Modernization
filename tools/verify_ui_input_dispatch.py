"""Compile and exercise the native Lua target collector plus the ranking-input regression."""
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

from native_build import environment_for

PROJECT=Path(__file__).resolve().parents[1]
VS=Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community")
HEADER=PROJECT/"Source/Host/UiInputDispatch.h"
TEST=PROJECT/"Tests/ui_input_dispatch.cpp"
TOOL=Path(__file__).resolve()
LUA_SOURCE=PROJECT/"Source/Lua51_x64/src"
SHARED_REPORT=PROJECT/"evidence/shared_lua_runtime/build_result.json"
LEGACY_TOOL=PROJECT/"tools/verify_ui_presentation_input.py"
ADDENDUM=PROJECT/"Source/Presentation/UiPresentationInput.lua"
EVIDENCE_ROOT=PROJECT/"evidence/ui_input_dispatch"
BUILD_ROOT=PROJECT/"Build/UiInputDispatch"


def sha(path:Path)->str:
    with path.open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def artifact(path:Path)->dict:
    return {"path":str(path),"sha256":sha(path),"bytes":path.stat().st_size}


def run(command:list[object],*,cwd:Path,env:dict,timeout:int)->subprocess.CompletedProcess:
    args=[str(item) for item in command]
    started=time.monotonic()
    child=subprocess.Popen(args,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                           creationflags=subprocess.CREATE_NO_WINDOW)
    timed_out=False
    try:stdout,stderr=child.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out=True;child.kill();stdout,stderr=child.communicate()
    result=subprocess.CompletedProcess(args,child.returncode,stdout,stderr)
    result.child_pid=child.pid
    result.elapsed_seconds=round(time.monotonic()-started,6)
    result.timed_out=timed_out
    return result


def process_record(result:subprocess.CompletedProcess,timeout:int)->dict:
    return {"child_pid":result.child_pid,"returncode":result.returncode,"timed_out":result.timed_out,
            "timeout_seconds":timeout,"elapsed_seconds":result.elapsed_seconds,
            "creationflags":"CREATE_NO_WINDOW"}


def require_process(result:subprocess.CompletedProcess,label:str)->None:
    if result.returncode or result.timed_out:
        output=(result.stdout+result.stderr).decode("utf-8",errors="replace")[-4000:]
        raise RuntimeError(f"{label} failed (pid={result.child_pid}, exit={result.returncode}, timeout={result.timed_out}): {output}")


def main()->int:
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_")+uuid.uuid4().hex[:12]
    evidence=EVIDENCE_ROOT/run_id;build=BUILD_ROOT/run_id
    evidence.mkdir(parents=True,exist_ok=False);build.mkdir(parents=True,exist_ok=False)
    failure=None;native_result=None;legacy_result=None;processes={};compiler_info={};linker_info={}
    shared=json.loads(SHARED_REPORT.read_text(encoding="utf-8"))
    if shared.get("status")!="SHARED_LUA_RUNTIME_CANDIDATE_BUILT":
        raise RuntimeError("The existing shared Lua provider report is not a successful candidate")
    lua_dll=Path(shared["lua_dll"]["path"]).resolve(strict=True)
    lua_lib=Path(shared["lua_library"]["path"]).resolve(strict=True)
    lua_header=LUA_SOURCE/"lua.h";aux_header=LUA_SOURCE/"lauxlib.h"
    inputs={"dispatch_header":HEADER,"native_test":TEST,"verifier":TOOL,"lua_header":lua_header,
            "lua_aux_header":aux_header,"lua_lib_header":LUA_SOURCE/"lualib.h","lua_runtime":lua_dll,"lua_import_library":lua_lib,
            "lua_addendum":ADDENDUM,"presentation_input_test":PROJECT/"Tests/ui_presentation_input.lua",
            "legacy_regression_verifier":LEGACY_TOOL}
    before={key:artifact(path.resolve(strict=True)) for key,path in inputs.items()}
    frozen=evidence/"frozen_inputs";frozen.mkdir()
    frozen_paths={}
    for key,path in inputs.items():
        if key=="dispatch_header":target=frozen/"Source/Host/UiInputDispatch.h"
        elif key=="native_test":target=frozen/"Tests/ui_input_dispatch.cpp"
        else:target=frozen/(key+path.suffix)
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,target)
        if sha(path)!=sha(target):raise RuntimeError("Frozen input copy mismatch: "+key)
        frozen_paths[key]=target
    try:
        env,compiler_path=environment_for(VS,"x64",build/"environment")
        compiler=Path(compiler_path).resolve(strict=True);linker=compiler.with_name("link.exe")
        compiler_info=artifact(compiler);linker_info=artifact(linker)
        runtime_copy=build/lua_dll.name;shutil.copy2(lua_dll,runtime_copy)
        if sha(runtime_copy)!=sha(lua_dll):raise RuntimeError("Shared Lua runtime copy changed")
        native_result={"runs":[]}
        for configuration,optimization in (("O2","/O2"),("Od","/Od")):
            config_dir=build/configuration;config_dir.mkdir()
            obj=config_dir/"ui_input_dispatch.obj";exe=config_dir/"UiInputDispatch.exe";deps=config_dir/"dependencies.json"
            compile_rsp=config_dir/"compile.rsp"
            compile_flags=["/nologo","/c","/std:c++14","/EHsc",optimization,"/MD","/W4","/WX","/utf-8",
                "/D_CRT_SECURE_NO_WARNINGS","/DLUA_BUILD_AS_DLL",f'/I"{frozen_paths["dispatch_header"].parent}"',
                f'/I"{LUA_SOURCE}"',f'/I"{PROJECT/"Source/Host"}"',f'"{frozen_paths["native_test"]}"',
                f'/Fo"{obj}"',f'/sourceDependencies "{deps}"']
            compile_rsp.write_text("\n".join(compile_flags)+"\n",encoding="utf-8")
            compile_result=run([compiler,"@"+str(compile_rsp)],cwd=config_dir,env=env,timeout=180)
            processes[configuration+"_compile"]=process_record(compile_result,180)
            (config_dir/"compile.log").write_bytes(compile_result.stdout+compile_result.stderr)
            require_process(compile_result,"native collector "+configuration+" compile")
            if re.search(rb"\bwarning\s+[A-Z]?\d+",compile_result.stdout+compile_result.stderr,re.I):
                raise RuntimeError("Native collector "+configuration+" compile emitted a warning")
            link_rsp=config_dir/"link.rsp"
            link_rsp.write_text("\n".join(["/nologo",f'"{obj}"',f'"{lua_lib}"',f'/OUT:"{exe}"',
                "/INCREMENTAL:NO","/MACHINE:X64","/Brepro","/WX","/OPT:REF","/OPT:ICF"]) + "\n",encoding="utf-8")
            link_result=run([linker,"@"+str(link_rsp)],cwd=config_dir,env=env,timeout=120)
            processes[configuration+"_link"]=process_record(link_result,120)
            (config_dir/"link.log").write_bytes(link_result.stdout+link_result.stderr)
            require_process(link_result,"native collector "+configuration+" link")
            if re.search(rb"\bwarning\s+[A-Z]?\d+",link_result.stdout+link_result.stderr,re.I):
                raise RuntimeError("Native collector "+configuration+" link emitted a warning")
            shutil.copy2(lua_dll,config_dir/lua_dll.name)
            native_run=run([exe],cwd=config_dir,env=env,timeout=60)
            processes[configuration+"_test"]=process_record(native_run,60)
            (config_dir/"native_test.log").write_bytes(native_run.stdout+native_run.stderr)
            require_process(native_run,"native collector "+configuration+" test")
            native_text=(native_run.stdout+native_run.stderr).decode("utf-8",errors="replace").replace("\r\n","\n")
            match=re.search(r"^UI_INPUT_DISPATCH_PASS checks=(\d+) LUA51_SHARED=true GAMECORE_LOADED=false$",native_text,re.M)
            if not match or int(match.group(1))<45:raise RuntimeError(configuration+" native test missing expected checks: "+native_text[-2000:])
            native_result["runs"].append({"configuration":configuration,"checks":int(match.group(1)),"output":native_text})
        native_result["checks"]=min(run["checks"] for run in native_result["runs"])

        # The legacy runner adds its own run directory and compiler snapshot.
        # Keep its roots short enough for Windows subprocess executable paths.
        legacy_evidence=PROJECT/"evidence"/"ui_input_lua"/run_id[-12:]
        legacy_build=PROJECT/"Build"/"UiInputLua"/run_id[-12:]
        legacy_result_run=run([sys.executable,LEGACY_TOOL,"--evidence-root",legacy_evidence,
            "--build-root",legacy_build,"--lua-dll",lua_dll],cwd=PROJECT,env=env,timeout=180)
        processes["legacy_ui_regression"]=process_record(legacy_result_run,180)
        (evidence/"legacy_regression_process.log").write_bytes(legacy_result_run.stdout+legacy_result_run.stderr)
        require_process(legacy_result_run,"existing Lua UI regression")
        legacy_output=legacy_result_run.stdout.decode("utf-8",errors="replace").strip()
        legacy_record=next((line for line in legacy_output.splitlines() if line.lstrip().startswith("{")),None)
        if legacy_record is None:raise RuntimeError("Existing Lua UI regression returned no JSON status record")
        legacy_result=json.loads(legacy_record)
        if legacy_result.get("status")!="PASS_UI_PRESENTATION_INPUT_COMPONENT_ONLY":
            raise RuntimeError("Existing Lua UI input regression failed: "+legacy_record[-2000:])
        legacy_conformance=Path(legacy_result["evidence"])/"conformance.json"
        legacy_report=json.loads(legacy_conformance.read_text(encoding="utf-8"))
        if legacy_report.get("status")!="PASS_UI_PRESENTATION_INPUT_COMPONENT_ONLY":
            raise RuntimeError("Existing Lua UI regression evidence does not confirm its printed PASS status")
        legacy_result["conformance"]=artifact(legacy_conformance)
    except Exception as exc:
        failure=f"{type(exc).__name__}: {exc}"

    after={key:artifact(path.resolve()) for key,path in inputs.items()}
    invariant=before==after
    addendum=frozen_paths["lua_addendum"].read_text(encoding="utf-8-sig")
    header=frozen_paths["dispatch_header"].read_text(encoding="utf-8-sig")
    input_test=frozen_paths["presentation_input_test"].read_text(encoding="utf-8-sig")
    native_test=frozen_paths["native_test"].read_text(encoding="utf-8-sig")
    checks={"target_limit_4096":"MaxTargets=4096" in header,
            "target_optional_pair_preserved":"target.void1=value.void1" in addendum and "target.void2=value.void2" in addendum and "hasVoidPayload" in header,
            "exact_signed_int_payload_range":"ExactInt32" in header and "numeric_limits<int>::min" in header and "numeric_limits<int>::max" in header,
            "legacy_identity_fields_preserved":"std::string id" in header and "std::uint64_t key" in header,
            "requested_left_click_and_scroll_events_are_validated":"event differs from the requested target collector" in header and
                "request->scroll?\"GetScrollTargets\":\"GetInputTargets\"" in header and
                "UI scroll target has no explicit Scroll event" in header,
            "lua_left_right_filters_and_invalid_filter_passed":bool(legacy_result and
                "GetInputTargets(Mouse.eLClick)" in input_test and "GetInputTargets(Mouse.eRClick)" in input_test and
                "unsupported target event filter was accepted" in input_test),
            "protected_callback_rejection_preserves_prior_output":
                "ProtectedCollectTargets" in native_test and
                "protected Lua validation rejection replaced the prior output" in native_test and
                bool(native_result),
            "pointer_and_scroll_request_kinds_are_tail_additions":"PointerMove=3, Scroll=4" in header,
            "native_scroll_request_requires_finite_bounded_owned_key":
                "std::isfinite(request->delta)" in header and "std::fabs(request->delta)>32768.0" in header and
                "request->key==0" in header and "badDeltas" in native_test,
            "pointer_clear_and_scroll_arguments_pass_through_protected_lua":
                "DispatchPointerMove=function(key)" in native_test and "LastScrollDelta==-48" in native_test and
                "pointer key zero did not clear hover" in native_test and bool(native_result),
            "lua_scroll_requires_visible_row_and_clamps_owned_pixel_offset":
                "isLeftInputTarget(handle,value)" in addendum and "if right>left and bottom>top then" in addendum and
                "local current=panel:GetScrollValue()" in addendum and
                "panel:SetScrollValue(math.max(0,math.min(maximum,current+delta)))" in addendum and
                "function ZeroSisUi.GetScrollTargets()" in addendum and "value.attributes.Vertical=='1'" in addendum and
                "event='Scroll'" in addendum and "math.min(value.x+value.w,1920)" in addendum,
            "lua_component_tests_cover_clipped_rows_and_panel_owned_pixel_policy":
                all(token in input_test for token in ("InputScrollRow2", "DispatchScroll",
                    "GetScrollTargets", "InputScrollPanel", "empty-panel-owned scroll", "48-pixel scroll did not move", "positive scroll did not clamp at the content bottom",
                    "negative scroll did not clamp at zero")) and
                bool(legacy_result),
            "legacy_ranking_ui_regression_passed":bool(legacy_result and legacy_result.get("status")=="PASS_UI_PRESENTATION_INPUT_COMPONENT_ONLY"),
            "native_invalid_and_large_target_cases_passed":bool(native_result)}
    status="PASS_UI_INPUT_DISPATCH_NATIVE" if failure is None and invariant and all(checks.values()) else "FAIL_UI_INPUT_DISPATCH_NATIVE"
    report={"status":status,"run_id":run_id,
        "scope":"Native Lua target collector and retained-scene pointer/scroll dispatch with source-frozen input validation plus ranking-popup UI regression; no Host window or GameCore",
        "checks":checks,
        "native_test":native_result,"legacy_regression":legacy_result,"processes":processes,
        "inputs_unchanged_after_run":invariant,"inputs_before":before,"inputs_after":after,
        "frozen_inputs":{key:artifact(path) for key,path in frozen_paths.items()},
        "compiler":compiler_info,"linker":linker_info,
        "build_artifacts":{path.name:artifact(path) for path in build.iterdir() if path.is_file()},
        "gamecore_loaded":False,"sdk_execution":False,"host_window_connected":False,
        "failure":failure,"limitations":[
            "The native fixture exercises the real collector against shared Lua 5.1 and hand-built target tables, including ProductionPopup-shaped optional payloads.",
            "The existing ranking-popup regression runs official popup Lua against mocked Civ/UI bindings; it does not exercise a live ProductionPopup click or the Host window.",
            "No Civ V SDK/GameCore or retail process is loaded."]}
    (evidence/"conformance.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":status,"run_id":run_id,"evidence":str(evidence/"conformance.json"),
        "native_checks":native_result.get("checks") if native_result else None,
        "legacy_status":legacy_result.get("status") if legacy_result else None,"failure":failure},ensure_ascii=True))
    return 0 if status.startswith("PASS_") else 1


if __name__=="__main__":raise SystemExit(main())
