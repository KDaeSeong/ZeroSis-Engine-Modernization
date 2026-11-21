"""Run the narrow headless native trade-route fixture probe in a private runtime.

This probe uses an explicit synthetic fixture that includes a P1 unit-AI
exception. It is source/SDK diagnostics only, not UI or full-game proof.
"""
from __future__ import annotations

import argparse
import ctypes
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from collect_baseline import PROJECT, digest
from probe_world_builder import artifact
from run_new_game_probe import verify_city_site_base, verify_found_value_base
from runtime_input_cache import materialize_immutable
from verify_world_builder_map_object import check_artifacts


RUNTIME_ROOT = PROJECT / "Build/TradeRouteFixtureRuntime"
EVIDENCE_ROOT = PROJECT / "evidence/trade_route_fixture"
SDK_LANGUAGE = "ko_KR"
FINAL_INVENTORY = re.compile(
    r"^TRADE_ROUTE_FIXTURE_FINAL=(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|(\d+)$",
    re.MULTILINE,
)
REQUIRED_HOST_SOURCES = (
    "HostMain.cpp",
    "HostRun.h",
    "TradeRouteFixtureProbe.h",
    "TradeRouteSmokeFixture.h",
    "TradeRoutePresentation.h",
)


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def frozen_copy(source: Path, target: Path) -> dict:
    shutil.copy2(source, target)
    if digest(source) != digest(target):
        raise RuntimeError(f"Evidence copy differs from source: {source}")
    return artifact(target)


def validate_host(build_path: Path, build: dict, shared_lua_path: Path) -> tuple[Path, dict, dict]:
    check_artifacts(build)
    if build.get("status") != "UI_WINDOW_HOST_CANDIDATE_BUILT" or \
            build.get("source_inputs_unchanged") is not True:
        raise RuntimeError("--host-build must identify a sealed, successful window Host build")
    build_id = build.get("build_id")
    if not isinstance(build_id, str) or not re.fullmatch(r"\d{8}T\d{6}Z_[0-9a-f]{12}", build_id):
        raise RuntimeError("Host build report has no immutable build ID")
    expected_report = (PROJECT / "evidence/ui_window_host" / build_id / "build_result.json").resolve()
    if build_path.resolve(strict=True) != expected_report:
        raise RuntimeError("Host build report is not the sealed project evidence report for its build ID")

    executable = build.get("executable")
    if not isinstance(executable, dict):
        raise RuntimeError("Host build report omits its executable artifact")
    executable_path = Path(executable["path"]).resolve(strict=True)
    build_root = (PROJECT / "Build/UiWindowHost" / build_id).resolve(strict=True)
    if not executable_path.is_relative_to(build_root) or executable.get("pe", {}).get("architecture") != "x64":
        raise RuntimeError("Host executable is outside its frozen x64 build directory")

    source_rows = {
        Path(row.get("original_source", row.get("relative_path", row.get("path", "")))).name: row
        for row in build.get("sources", []) if isinstance(row, dict)
    }
    if not set(REQUIRED_HOST_SOURCES) <= source_rows.keys():
        raise RuntimeError("Sealed Host source closure lacks trade-route fixture integration")
    source_text: dict[str, str] = {}
    for name in REQUIRED_HOST_SOURCES:
        row = source_rows[name]
        frozen_source = Path(row["path"]).resolve(strict=True)
        if not frozen_source.is_relative_to(build_root) or digest(frozen_source) != row.get("sha256"):
            raise RuntimeError(f"Frozen Host source hash/path is invalid: {name}")
        source_text[name] = frozen_source.read_text(encoding="utf-8-sig")
    if "--check-trade-route-fixture" not in source_text["HostMain.cpp"] or \
            "TradeRouteFixtureObservation" not in source_text["HostRun.h"] or \
            "TradeRouteFixtureProbe::Run" not in source_text["HostRun.h"] or \
            "TRADE_ROUTE_FIXTURE_PROBE_PASS" not in source_text["HostMain.cpp"]:
        raise RuntimeError("Frozen Host sources do not contain the explicit trade-route probe mode")

    shared_ref = build.get("shared_lua_build")
    if not isinstance(shared_ref, dict):
        raise RuntimeError("Host build report lacks its frozen shared-Lua provider report")
    frozen_shared_path = Path(shared_ref["path"]).resolve(strict=True)
    if digest(frozen_shared_path) != shared_ref.get("sha256") or \
            Path(shared_ref.get("original_path", "")).resolve() != shared_lua_path.resolve(strict=True) or \
            digest(shared_lua_path) != shared_ref.get("sha256"):
        raise RuntimeError("Selected shared-Lua provider differs from the Host's frozen build input")
    frozen_shared = load_json(frozen_shared_path)
    if frozen_shared.get("status") != "SHARED_LUA_RUNTIME_CANDIDATE_BUILT":
        raise RuntimeError("Host frozen shared-Lua report is not a built provider")
    return executable_path, source_rows, frozen_shared


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host-build", required=True, type=Path,
                        help="Sealed UI Host build_result.json")
    parser.add_argument("--terrain-manifest", required=True, type=Path,
                        help="Existing terrain package required by the selected Host; never regenerated")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Native child timeout in seconds (30..180; default 120)")
    args = parser.parse_args()
    if not 30 <= args.timeout <= 180:
        parser.error("--timeout must be between 30 and 180 seconds")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    runtime = RUNTIME_ROOT / run_id
    evidence = EVIDENCE_ROOT / run_id
    runtime.mkdir(parents=True, exist_ok=False)
    evidence.mkdir(parents=True, exist_ok=False)
    request_path = evidence / "request.json"
    result_path = evidence / "result.json"
    stdout_path = evidence / "stdout.log"
    stderr_path = evidence / "stderr.log"
    stdout_path.write_bytes(b"")
    stderr_path.write_bytes(b"")

    request: dict = {
        "schema": "zerosis.trade_route_fixture_probe_request.v1",
        "run_id": run_id,
        "command": None,
        "cwd": str(runtime.resolve()),
        "timeout_seconds": args.timeout,
        "language": SDK_LANGUAGE,
        "fixture_scope": "SYNTHETIC_P1_UNIT_AI_EXCEPTION_NATIVE_SDK_DIAGNOSTIC_ONLY",
        "ui_requested": False,
        "texture_or_screenshot_requested": False,
        "full_game_pass_claimed": False,
    }
    write_json(request_path, request)
    process = None
    start = time.monotonic()
    stdout = b""
    stderr = b""
    return_code = None
    timed_out = False
    inputs: list[dict] = []
    inventory_rows: list[dict] = []
    presentation_rows: list[dict] = []
    source_evidence: dict = {}
    provider_refs: dict = {}
    errors: list[str] = []
    final_counts = None
    success = False

    try:
        build_path = args.host_build.resolve(strict=True)
        build = load_json(build_path)
        runtime_report_path = PROJECT / "evidence/shared_lua_runtime/build_result.json"
        explore_path = PROJECT / "evidence/explore_sdk/build_result.json"
        city_path = PROJECT / "evidence/city_site_sdk/build_result.json"
        found_path = PROJECT / "evidence/found_value_shared_sdk/build_result.json"
        bundle_path = PROJECT / "evidence/host/bundle.json"
        runtime_report = load_json(runtime_report_path)
        explore = load_json(explore_path)
        city = load_json(city_path)
        found = load_json(found_path)
        bundle = load_json(bundle_path)
        check_artifacts(runtime_report)
        check_artifacts(explore)
        check_artifacts(city)
        check_artifacts(found)
        # The accepted runtime bytes and manifest are the input contract. Its
        # historical preparer source may have changed since preparation, just
        # as in run_found_city_probe; it is not an executable runtime input.
        check_artifacts(bundle["files"])
        check_artifacts(bundle["manifest"])
        if explore.get("status") != "EXPLORE_SDK_CANDIDATE_LINKED":
            raise RuntimeError("Shared SDK fixture requires the recorded Explore SDK provider")
        verify_city_site_base(city, explore)
        verify_found_value_base(found, city, "SHARED_FACTS")
        if bundle.get("status") != "NATIVE_HOST_BUNDLE_PREPARED_NOT_GAME_EXECUTED":
            raise RuntimeError("Accepted native Host bundle is not in its prepared state")
        if not isinstance(bundle.get("files"), list) or not isinstance(bundle.get("manifest"), dict):
            raise RuntimeError("Accepted native Host bundle omits its file/manifest records")
        forbidden_extensions = {".dds", ".png", ".jpg", ".jpeg", ".tga", ".bmp", ".gif"}
        if any(Path(row.get("path", "")).suffix.lower() in forbidden_extensions
               for row in bundle["files"] if isinstance(row, dict)):
            raise RuntimeError("Accepted bundle unexpectedly contains UI/texture image assets")

        executable, source_rows, frozen_shared = validate_host(build_path, build, runtime_report_path)
        core = found.get("gamecore")
        lua_dll = runtime_report.get("lua_dll")
        if not isinstance(core, dict) or not isinstance(lua_dll, dict):
            raise RuntimeError("Selected shared Found SDK or Lua provider omits its runtime DLL")
        check_artifacts(core)
        check_artifacts(lua_dll)
        if core.get("sha256") != found.get("gamecore", {}).get("sha256"):
            raise RuntimeError("Selected shared Found SDK Core hash is inconsistent")
        if frozen_shared.get("lua_dll", {}).get("sha256") != lua_dll.get("sha256"):
            raise RuntimeError("Host's frozen shared-Lua DLL differs from the selected runtime provider")

        proof_sources = evidence / "frozen_sources"
        proof_sources.mkdir()
        for name in REQUIRED_HOST_SOURCES:
            source_evidence[name] = frozen_copy(Path(source_rows[name]["path"]), proof_sources / name)
        for label, source in (
            ("host_build", build_path), ("shared_lua_build", runtime_report_path),
            ("explore_sdk_build", explore_path), ("city_site_sdk_build", city_path),
            ("found_value_shared_sdk_build", found_path), ("accepted_bundle", bundle_path),
            ("runner", Path(__file__).resolve()),
        ):
            provider_refs[label] = frozen_copy(source, evidence / (label + source.suffix))
        request["provenance"] = provider_refs
        request["frozen_host_sources"] = source_evidence
        request["host_build_id"] = build["build_id"]
        request["host_executable"] = artifact(executable)
        request["sdk_gamecore"] = core
        request["shared_lua_dll"] = lua_dll
        request["accepted_bundle"] = artifact(bundle_path)

        cache_root = PROJECT / "Build/RuntimeInputCache"
        materializations = []
        for row in bundle["files"]:
            name = Path(row["path"]).name
            if name == "ZeroSisHost_x64.exe":
                source = executable
            elif name == "CvGameCoreDLL_Expansion2_x64.dll":
                source = Path(core["path"])
            else:
                source = Path(row["path"])
            target = runtime / name
            if source.suffix.lower() in (".dll", ".exe", ".bin", ".dat"):
                materialization = materialize_immutable(source, target, cache_root)
            else:
                shutil.copy2(source, target)
                materialization = {"target": str(target), "materialization_method": "private-copy",
                                   "size": target.stat().st_size}
            observed = artifact(target)
            if observed["sha256"] != digest(source):
                raise RuntimeError(f"Private bundle input differs from selected source: {name}")
            inputs.append({"source": str(source), **observed})
            materializations.append(materialization)
        lua_source = Path(lua_dll["path"])
        lua_target = runtime / "ZeroSisLua51_x64.dll"
        materializations.append(materialize_immutable(lua_source, lua_target, cache_root))
        inputs.append({"source": str(lua_source), **artifact(lua_target)})
        terrain_manifest_path = args.terrain_manifest.resolve(strict=True)
        terrain_manifest = load_json(terrain_manifest_path)
        if not terrain_manifest_path.is_relative_to((PROJECT / "Build/TerrainAssets").resolve(strict=True)) or \
                terrain_manifest.get("format") != "ZEROSIS_CIV5_TERRAIN_DIFFUSE_PACKAGE_V1":
            raise RuntimeError("Terrain input must be an existing project terrain-package manifest")
        terrain_package = terrain_manifest["package"]
        terrain_source = Path(terrain_package["path"]).resolve(strict=True)
        if terrain_source.parent != terrain_manifest_path.parent or \
                terrain_source.name != "terrain-assets.bin":
            raise RuntimeError("Terrain package escaped its declared content-addressed folder")
        check_artifacts(terrain_package)
        terrain_target = runtime / "terrain-assets.bin"
        materializations.append(materialize_immutable(terrain_source, terrain_target, cache_root))
        inputs.append({"source": str(terrain_source), **artifact(terrain_target)})
        provider_refs["terrain_manifest"] = frozen_copy(terrain_manifest_path, evidence / "terrain-manifest.json")
        request["terrain_package_reused_without_rendering"] = True
        manifest = runtime / "bundle.manifest"
        manifest.write_text(
            "ZEROSIS_HOST_BUNDLE_V4\n" +
            "".join(Path(row["path"]).name + "|" + row["sha256"] + "\n" for row in inputs),
            encoding="ascii",
        )
        inputs.append(artifact(manifest))
        request["runtime_inputs"] = inputs
        request["input_materializations"] = materializations
        request["command"] = [str(runtime / "ZeroSisHost_x64.exe"),
                               "--check-trade-route-fixture", SDK_LANGUAGE]
        request["environment_overrides"] = {
            "ZEROSIS_EXPLORE_WORKERS": "0", "ZEROSIS_CITY_SITE_WORKERS": "0",
            "ZEROSIS_FOUND_VALUE_WORKERS": "0", "ZEROSIS_UI_WINDOW_PROFILE": None,
            "ZEROSIS_CITY_SITE_CPU_TRACE": None, "ZEROSIS_FOUND_VALUE_CPU_TRACE": None,
            "ZEROSIS_FOUND_VALUE_TRACE": None,
        }
        write_json(request_path, request)

        environment = os.environ.copy()
        environment["ZEROSIS_EXPLORE_WORKERS"] = "0"
        environment["ZEROSIS_CITY_SITE_WORKERS"] = "0"
        environment["ZEROSIS_FOUND_VALUE_WORKERS"] = "0"
        for key in ("ZEROSIS_UI_WINDOW_PROFILE", "ZEROSIS_CITY_SITE_CPU_TRACE",
                    "ZEROSIS_FOUND_VALUE_CPU_TRACE", "ZEROSIS_FOUND_VALUE_TRACE"):
            environment.pop(key, None)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.SetErrorMode.argtypes = [ctypes.c_uint]
        kernel.SetErrorMode.restype = ctypes.c_uint
        old_error_mode = kernel.SetErrorMode(0x0001 | 0x0002 | 0x8000)
        try:
            process = subprocess.Popen(
                request["command"], cwd=runtime, env=environment,
                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        finally:
            kernel.SetErrorMode(old_error_mode)
        try:
            stdout, stderr = process.communicate(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            stdout, stderr = process.communicate(timeout=10)
        return_code = process.returncode
        stdout_path.write_bytes(stdout)
        stderr_path.write_bytes(stderr)
        output = (stdout + stderr).decode("utf-8", errors="replace").replace("\r\n", "\n")
        session_names = re.findall(r"^SESSION_DIRECTORY=(.+)$", output, re.MULTILINE)
        if len(session_names) != 1:
            raise RuntimeError("Native diagnostic did not identify exactly one private SDK session")
        session_directory = Path(session_names[0]).resolve(strict=True)
        if session_directory.parent != (runtime / "sessions").resolve(strict=True):
            raise RuntimeError("Native diagnostic session escaped its exact private runtime")
        request["session_directory"] = str(session_directory)

        for path in sorted(session_directory.glob("trade-probe-*-inventory.json")):
            row = artifact(path)
            data = load_json(path)
            if data.get("schema") != "ZEROSIS_TRADE_ROUTE_SDK_INVENTORY_V1" or \
                    data.get("source") != "SDK:GetTradeRoutes/GetTradeRoutesToYou/GetTradeRoutesAvailable":
                errors.append(f"Inventory schema/source differs: {path.name}")
            inventory_rows.append(row)
        for path in sorted(session_directory.glob("trade-probe-*-presentation.json")):
            row = artifact(path)
            data = load_json(path)
            if not isinstance(data, dict) or data.get("schema") != "ZEROSIS_TRADE_ROUTE_PRESENTATION_V1":
                errors.append(f"TradeVisuals JSON schema differs: {path.name}")
            presentation_rows.append(row)
        if not inventory_rows or not presentation_rows:
            errors.append("Native Host did not retain SDK inventory and TradeVisuals JSON samples")
        final_inventory_path = session_directory / "trade-probe-final-inventory.json"
        final_presentation_path = session_directory / "trade-probe-final-presentation.json"
        final_inventory = load_json(final_inventory_path) if final_inventory_path.is_file() else None
        if final_inventory is None:
            errors.append("Native Host did not retain the final actual-SDK inventory JSON")
        elif any(not isinstance(final_inventory.get(key), list) for key in ("outbound", "inbound", "available")):
            errors.append("Final SDK inventory JSON omits route collections")

        markers = FINAL_INVENTORY.findall(output)
        if len(markers) == 1:
            values = tuple(int(value) for value in markers[0])
            final_counts = {
                "active_player": values[0], "turn": values[1], "elapsed": values[2],
                "outbound": values[3], "inbound": values[4], "available": values[5],
            }
        else:
            errors.append("Native output must contain exactly one final SDK inventory marker")
        if final_counts and (final_counts["active_player"] != 0 or final_counts["turn"] != 1 or
                             final_counts["elapsed"] != 1 or final_counts["outbound"] < 2 or
                             final_counts["inbound"] < 2 or final_counts["available"] < 2):
            errors.append("Final actual-SDK inventory is below the required next-turn route minimum")
        if final_inventory and final_counts:
            json_counts = {key: len(final_inventory[key]) for key in ("outbound", "inbound", "available")}
            if final_inventory.get("activePlayer") != final_counts["active_player"] or \
                    final_inventory.get("turn") != final_counts["turn"] or \
                    final_inventory.get("elapsed") != final_counts["elapsed"] or any(
                        json_counts[key] != final_counts[key] for key in json_counts
                    ):
                errors.append("Final SDK inventory JSON differs from the native getter-count marker")
        if final_presentation_path.is_file():
            final_presentation = load_json(final_presentation_path)
            if final_presentation.get("schema") != "ZEROSIS_TRADE_ROUTE_PRESENTATION_V1":
                errors.append("Final TradeVisuals JSON schema differs")
        else:
            errors.append("Native Host did not retain the final TradeVisuals JSON")
        if output.splitlines().count("TRADE_ROUTE_FIXTURE_PROBE_PASS GAMECORE_UNLOADED=true UI_RENDERING=false") != 1:
            errors.append("Native completion PASS marker is absent or duplicated")
        if "HOST_FAILURE:" in output or "HOST_NATIVE_EXCEPTION" in output:
            errors.append("Native Host failure marker is present")
        for row in inputs:
            if digest(Path(row["path"])) != row["sha256"]:
                errors.append(f"Private runtime input changed during execution: {Path(row['path']).name}")
        check_artifacts(provider_refs)
        check_artifacts(source_evidence)
        success = return_code == 0 and not timed_out and not errors

    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        if process is not None and process.poll() is None:
            process.kill()
            try:
                stdout, stderr = process.communicate(timeout=10)
            except Exception as cleanup_error:
                errors.append(f"Child reap failed: {type(cleanup_error).__name__}: {cleanup_error}")
        if process is not None:
            return_code = process.returncode
            stdout_path.write_bytes(stdout)
            stderr_path.write_bytes(stderr)

    write_json(request_path, request)
    result = {
        "schema": "zerosis.trade_route_fixture_probe_result.v1",
        "status": "NATIVE_TRADE_ROUTE_FIXTURE_SDK_DIAGNOSTIC_PASS" if success else
                  "NATIVE_TRADE_ROUTE_FIXTURE_SDK_DIAGNOSTIC_FAILED",
        "scope": "SYNTHETIC_P1_UNIT_AI_EXCEPTION_SOURCE_AND_NATIVE_SDK_FIXTURE_ONLY",
        "run_id": run_id,
        "request": artifact(request_path) if request_path.is_file() else None,
        "stdout": artifact(stdout_path), "stderr": artifact(stderr_path),
        "exit_code": return_code, "timed_out": timed_out,
        "duration_seconds": time.monotonic() - start,
        "final_sdk_inventory": final_counts,
        "inventory_json_count": len(inventory_rows), "inventory_json": inventory_rows,
        "trade_visuals_json_count": len(presentation_rows), "trade_visuals_json": presentation_rows,
        "runtime_input_count": len(inputs), "runtime_inputs_unchanged": bool(inputs) and all(
            Path(row["path"]).is_file() and digest(Path(row["path"])) == row["sha256"] for row in inputs),
        "host_build_id": request.get("host_build_id"),
        "synthetic_p1_unit_ai_exception": True,
        "ui_or_full_game_pass_claimed": False,
        "errors": errors,
    }
    write_json(result_path, result)
    print(json.dumps({
        "status": result["status"], "result": str(result_path),
        "outbound": final_counts.get("outbound") if final_counts else None,
        "inbound": final_counts.get("inbound") if final_counts else None,
        "available": final_counts.get("available") if final_counts else None,
        "runtime_inputs": result["runtime_input_count"],
    }, separators=(",", ":")), flush=True)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
