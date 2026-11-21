"""Run bounded native Lua 5.1 snapshot JSON safety and fixture roundtrip checks."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT, digest
from native_build import run
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts


def require(ok: bool, message: str) -> None:
    if not ok:
        raise RuntimeError(message)


def verify(build_path: Path) -> dict:
    build_path = build_path.resolve(strict=True)
    build = json.loads(build_path.read_text(encoding="utf-8"))
    check_artifacts(build)
    require(build.get("status") == "UI_SNAPSHOT_JSON_COMPONENT_BUILT", "Build report is not the expected native Lua snapshot component")
    exe_ref, dll_ref, header = build.get("executable"), build.get("lua_dll"), build.get("header")
    require(isinstance(exe_ref, dict) and isinstance(dll_ref, dict) and isinstance(header, dict),
            "Build report omits the executable/provider/header artifacts")
    check_artifacts([exe_ref, dll_ref, header])
    exe, dll, header_path = (Path(row["path"]).resolve(strict=True) for row in (exe_ref, dll_ref, header))
    require(exe.parent == dll.parent and dll.name == "ZeroSisLua51_x64.dll" and header_path.name == "UiSnapshotJson.h",
            "Component executable, provider DLL alias, or helper header path differs")
    original_header = header.get("original_source")
    require(isinstance(original_header, dict), "Build header report lacks original_source provenance")
    check_artifacts(original_header)
    require(Path(original_header["path"]).resolve(strict=True) == (PROJECT / "Source/Host/UiSnapshotJson.h").resolve(strict=True) and
            original_header["sha256"] == header["sha256"] == digest(header_path),
            "Built helper header does not match its exact frozen source")
    test_source = PROJECT / "Tests/ui_snapshot_json.cpp"
    case_source = PROJECT / "Tests/ui_snapshot_json_cases.lua"
    input_map = {Path(row["path"]).resolve(strict=True): row["sha256"] for row in build.get("compiler_inputs", [])}
    require(input_map.get(test_source.resolve(strict=True)) == digest(test_source) and
            input_map.get(header_path) == digest(header_path),
            "Compiler dependency report does not prove consumption of the live C++ test and helper header")
    imports = build.get("import_report", {}).get("dependencies", [])
    require("ZeroSisLua51_x64.dll" in imports and build.get("lua_provider_library", {}).get("sha256"),
            "Harness is not linked to the shared Lua 5.1 provider")
    require(dll_ref["sha256"] == build["lua_provider_library"]["sha256"],
            "Harness-local provider DLL differs from the linked provider")

    output_dir = build_path.parent
    frozen_cases = output_dir / "ui_snapshot_json_cases.lua"
    shutil.copy2(case_source, frozen_cases)
    require(digest(frozen_cases) == digest(case_source), "Frozen Lua roundtrip fixture differs from its source")
    self_result = run([exe], cwd=exe.parent, timeout=180)
    self_log = output_dir / "safety-selftest.log"
    self_log.write_bytes(self_result.stdout + self_result.stderr)
    stdout = self_result.stdout.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
    stderr = self_result.stderr.decode("utf-8", errors="replace")
    match = re.fullmatch(r"UI_SNAPSHOT_JSON_TEST_PASS checks=(\d+) GAMECORE_LOADED=false\n", stdout)
    require(self_result.returncode == 0 and match is not None and int(match.group(1)) >= 10 and not stderr,
            "Native safety fixture failed; immutable safety log was preserved")

    fixture_result = run([exe, "--run", frozen_cases, "snapshot_json_report"], cwd=exe.parent, timeout=180)
    fixture_log = output_dir / "lua-roundtrip.log"
    fixture_log.write_bytes(fixture_result.stdout + fixture_result.stderr)
    fixture_stdout = fixture_result.stdout.decode("utf-8", errors="strict").replace("\r\n", "\n").replace("\r", "\n")
    fixture_stderr = fixture_result.stderr.decode("utf-8", errors="replace")
    rows = re.findall(r"^UI_SNAPSHOT_JSON_REPORT=(.+)$", fixture_stdout, re.M)
    require(fixture_result.returncode == 0 and len(rows) == 1 and fixture_stdout == f"UI_SNAPSHOT_JSON_REPORT={rows[0]}\n" and
            not fixture_stderr, "Lua fixture did not return exactly its JSON report on stdout")
    report = json.loads(rows[0])
    require(report.get("status") == "UI_SNAPSHOT_JSON_ROUNDTRIP_FIXTURE", "Lua fixture report status differs")
    parsed = {name: json.loads(report[name]) for name in ("empty_array", "empty_object", "sparse_array", "sorted_object", "payload")}
    require(parsed["empty_array"] == [] and parsed["empty_object"] == {} and parsed["sparse_array"] == [],
            "Empty or sparse Lua table JSON semantics differ")
    require(report["sorted_object"] == '{"a":"first","z":"last"}' and
            parsed["sorted_object"] == {"a": "first", "z": "last"},
            "String-key object ordering/roundtrip differs")
    payload = parsed["payload"]
    require(payload.get("label") == "기술 트리" and payload.get("number") == 1.2345678901234567 and
            payload.get("sparse") == [] and payload.get("ordered") == {"a": "first", "z": "last"} and
            payload.get("controls") == "\x00\x01\x1f\"\\" and
            payload.get("repeated", {}).get("shared", {}).get("answer") == 42,
            "UTF-8, escaped controls, finite-number or shared-table JSON roundtrip differs")

    return {
        "status": "UI_SNAPSHOT_JSON_COMPONENT_PASS",
        "build": artifact(build_path),
        "executable": exe_ref,
        "lua_provider_dll": dll_ref,
        "helper_header": header,
        "frozen_lua_fixture": artifact(frozen_cases),
        "self_test": {"checks": int(match.group(1)), "exit_code": self_result.returncode, "log": artifact(self_log),
                       "covered": ["empty array/object", "sparse ipairs stop", "sorted object keys", "UTF-8 and control escaping",
                                   "finite number precision", "shared non-cyclic tables", "raw lookup/no metamethod",
                                   "unsupported values", "cycle", "depth/visited/output/key bounds", "Lua stack restoration"]},
        "fixture_roundtrip": {"exit_code": fixture_result.returncode, "log": artifact(fixture_log),
                              "report": report, "parsed_values_verified": True},
        "gamecore_loaded": False,
        "actual_game_ui_runtime_verified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", required=True, type=Path)
    args = parser.parse_args()
    proof_dir = PROJECT / "validators" / (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12])
    proof_dir.mkdir(parents=True, exist_ok=False)
    frozen_verifier = proof_dir / "verify_ui_snapshot_json.py"
    shutil.copy2(Path(__file__).resolve(), frozen_verifier)
    try:
        result = verify(args.build)
        result["independent_verifier"] = artifact(frozen_verifier)
        result["scope"] = "ONE_TU_ACTUAL_SHARED_LUA_5_1_X64_PROVIDER_JSON_ENCODE_AND_PYTHON_ROUNDTRIP_NO_GAMECORE"
        result["limitations"] = ["This component test does not execute the full Host or the Civ V SDK.",
                                 "The actual Production/ResearchTree runtime snapshot remains a separate integration gate."]
    except Exception as exc:
        result = {"status": "FAIL_UI_SNAPSHOT_JSON_COMPONENT", "failure": f"{type(exc).__name__}: {exc}",
                  "build": artifact(args.build.resolve(strict=True)), "independent_verifier": artifact(frozen_verifier),
                  "gamecore_loaded": False, "actual_game_ui_runtime_verified": False}
        out = proof_dir / "conformance.json"
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"status": result["status"], "proof": artifact(out), "failure": result["failure"]}, ensure_ascii=False), file=sys.stderr)
        raise
    out = proof_dir / "conformance.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "proof": artifact(out)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
