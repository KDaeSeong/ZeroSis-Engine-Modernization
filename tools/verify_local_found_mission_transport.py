"""Run the isolated ordered LocalGameCommands mission transport test."""
import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT
from native_build import environment_for, run
from probe_world_builder import artifact


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def check_session_contract(path):
    source = path.read_text(encoding="utf-8")
    start = source.index("},[this,&receiver,&game,&context](int unitID,MissionTypes mission")
    end = source.index("});", start)
    block = source[start:end]
    required = [
        "RequireCommandOwner();", "game.IsGameMultiPlayer()", "GetInfoTypeForString(\"MISSION_FOUND\",true)",
        "GetMissionInfo(foundMission)", "GetType())!=\"MISSION_FOUND\"", "mission!=foundMission",
        "data1!=-1 || data2!=-1 || flags!=0 || shift", "selected.size()!=1",
        "selected.front().first!=active || selected.front().second!=unitID", "unit->IsDelayedDeathExported()",
        "unit->IsBusy()", "receiver.ResponsePushMission(active,unitID,mission,data1,data2,flags,shift);",
    ]
    offsets = [block.find(item) for item in required]
    if any(index < 0 for index in offsets) or offsets != sorted(offsets):
        raise RuntimeError("LocalSdkSession found-mission guard/dispatch contract is missing or reordered")
    host = (PROJECT / "Source/Host/HostServices.h").read_text(encoding="utf-8")
    if "void sendPushMission(int unitID,MissionTypes mission,int data1,int data2,int flags,bool shift) override" not in host:
        raise RuntimeError("EngineServices sendPushMission override is missing")
    if "uint AddCityMessage(uint parentEvent,const IDInfo& cityID" not in host:
        raise RuntimeError("Owned AddCityMessage capture is missing")
    if "void GameplayUnitActivate(ICvUnit1* unit) override" not in host:
        raise RuntimeError("GameplayUnitActivate identity capture is missing")


def main():
    project = PROJECT
    source = project / "Tests/local_found_mission_commands.cpp"
    live = {
        "test": source,
        "transport": project / "Source/Host/LocalGameCommands.h",
        "sdk_includes": project / "Source/Host/SdkHostIncludes.h",
        "session": project / "Source/Host/LocalSdkSession.h",
        "host": project / "Source/Host/HostServices.h",
        "runner": Path(__file__).resolve(),
    }
    before = {key: sha(path) for key, path in live.items()}
    check_session_contract(live["session"])
    build_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    evidence = project / "evidence/local_found_mission" / build_id
    frozen = evidence / "frozen_inputs"
    frozen_host = frozen / "Source/Host"
    frozen_test = frozen / "Tests/local_found_mission_commands.cpp"
    frozen_host.mkdir(parents=True)
    frozen_test.parent.mkdir(parents=True)
    for key, path in live.items():
        if key == "test":
            shutil.copy2(path, frozen_test)
        elif key == "transport":
            shutil.copy2(path, frozen_host / "LocalGameCommands.h")
        elif key == "sdk_includes":
            shutil.copy2(path, frozen_host / "SdkHostIncludes.h")
        else:
            destination = frozen / path.relative_to(project)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
    frozen_paths = [frozen_test, frozen_host / "LocalGameCommands.h", frozen_host / "SdkHostIncludes.h",
                    frozen / "Source/Host/LocalSdkSession.h", frozen / "Source/Host/HostServices.h",
                    frozen / "tools/verify_local_found_mission_transport.py"]
    frozen_hashes = {str(path.relative_to(evidence)): sha(path) for path in frozen_paths}
    sdk = project / "Source/SDK_BNW_x64"
    sdk_includes = [sdk / value for value in (
        "CvGameCoreDLL_Expansion2", "CvGameCoreDLLUtil/include", "CvGameDatabase/include",
        "CvLocalization/include", "CvWorldBuilderMap/include", "FirePlace/include",
        "FirePlace/include/FireWorks", "ThirdPartyLibs/Lua51/include")]
    output = project / "Build/LocalFoundMission" / build_id
    output.mkdir(parents=True)
    environment, compiler = environment_for(Path(r"C:\Program Files\Microsoft Visual Studio\2022\Community"), "x64", output)
    environment["VSLANG"] = "1033"
    executable = output / "LocalFoundMission.exe"
    deps = output / "dependencies.json"
    response = output / "compile.rsp"
    flags = ["/nologo", "/std:c++14", "/EHsc", "/W4", "/WX", "/O2", "/MD", "/fp:strict",
             "/source-charset:windows-1252", "/external:W0", "/DWIN32", "/DNDEBUG", "/DFINAL_RELEASE",
             "/D_CRT_SECURE_NO_WARNINGS", "/D_SILENCE_STDEXT_HASH_DEPRECATION_WARNINGS",
             "/D_SILENCE_TR1_NAMESPACE_DEPRECATION_WARNING"]
    flags.extend(f'/external:I"{path}"' for path in sdk_includes)
    flags.extend([f'/I"{frozen_host}"', f'/I"{project / "Source/Porting"}"', f'"{frozen_test}"',
                  f'/Fo"{output.as_posix()}/"', f'/Fe"{executable}"', f'/sourceDependencies "{deps}"'])
    response.write_text("\n".join(flags) + "\n", encoding="utf-8")
    result = run([compiler, f"@{response}", "/link", "/INCREMENTAL:NO", "/MACHINE:X64", "/Brepro", "/WX", "/OPT:REF", "/OPT:ICF"],
                 cwd=output, env=environment, timeout=180)
    log_text = (result.stdout + result.stderr).decode("mbcs", errors="replace")
    (output / "build.log").write_text(log_text, encoding="utf-8")
    if result.returncode or re.search(r"\bwarning\s+C\d+", log_text, re.I):
        raise RuntimeError(f"Component compile failed: {log_text[-5000:]}")
    executed = run([executable], cwd=output, env=environment, timeout=30)
    transcript = (executed.stdout + executed.stderr).decode("utf-8", errors="replace")
    transcript = transcript.replace("\r\n", "\n").replace("\r", "\n")
    (output / "execution.log").write_text(transcript, encoding="utf-8")
    match = re.search(r"^LOCAL_FOUND_MISSION_TRANSPORT_PASS checks=(\d+) GAMECORE_LOADED=false$", transcript, re.M)
    if executed.returncode or not match or int(match.group(1)) < 10:
        raise RuntimeError(f"Component test failed: {transcript[-4000:]}")
    after = {key: sha(path) for key, path in live.items()}
    if before != after or any(sha(path) != frozen_hashes[str(path.relative_to(evidence))] for path in frozen_paths):
        raise RuntimeError("A guarded source or frozen input changed during the component check")
    report = {
        "status": "LOCAL_FOUND_MISSION_TRANSPORT_COMPONENT_PASS",
        "scope": "LOCAL_COMMAND_TRANSPORT_AND_STATIC_SESSION_GUARD_CONTRACT_ONLY",
        "gamecore_loaded": False,
        "checks": int(match.group(1)),
        "frozen_inputs": [{"path": str(path.relative_to(evidence)), "sha256": frozen_hashes[str(path.relative_to(evidence))]} for path in frozen_paths],
        "live_source_hashes_before": before,
        "live_source_hashes_after": after,
        "compiler": artifact(Path(compiler)),
        "executable": artifact(executable),
        "build_log": artifact(output / "build.log"),
        "execution_log": artifact(output / "execution.log"),
        "evidence_directory": str(evidence),
    }
    (evidence / "conformance.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": report["checks"], "evidence": artifact(evidence / "conformance.json")}))


if __name__ == "__main__":
    main()
