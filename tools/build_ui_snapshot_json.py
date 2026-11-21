"""Build the small shared-Lua-provider harness for native UI snapshot JSON."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from collect_baseline import PROJECT
from probe_world_builder import artifact
from verify_world_builder_map_object import check_artifacts
from build_native_host import compile_program


def main() -> int:
    provider_path = PROJECT / "evidence/shared_lua_runtime/build_result.json"
    provider = json.loads(provider_path.read_text(encoding="utf-8"))
    check_artifacts(provider)
    if provider.get("status") != "SHARED_LUA_RUNTIME_CANDIDATE_BUILT":
        raise RuntimeError("The established shared Lua provider is not available")
    lua_library = provider.get("lua_library")
    lua_dll = provider.get("lua_dll")
    if not isinstance(lua_library, dict) or not isinstance(lua_dll, dict):
        raise RuntimeError("Shared Lua provider report omits its x64 library/DLL")
    check_artifacts([lua_library, lua_dll])
    build_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    name = "sdk_ui_snapshot_json_" + build_id
    build = compile_program(name, PROJECT / "Tests/ui_snapshot_json.cpp",
                            libraries=[Path(lua_library["path"])], optimization="/O2",
                            definitions=("ZEROSIS_SHARED_LUA_RUNTIME=1", "LUA_BUILD_AS_DLL"),
                            additional_imports=("ZeroSisLua51_x64.dll",))
    exe = Path(build["executable"]["path"]).resolve(strict=True)
    dll = Path(lua_dll["path"]).resolve(strict=True)
    dll_copy = exe.parent / "ZeroSisLua51_x64.dll"
    dll_copy.write_bytes(dll.read_bytes())
    if artifact(dll_copy)["sha256"] != lua_dll["sha256"]:
        raise RuntimeError("Harness-local Lua provider DLL copy differs from the established provider")
    header_path = PROJECT / "Source/Host/UiSnapshotJson.h"
    test_path = PROJECT / "Tests/ui_snapshot_json.cpp"
    builder_path = Path(__file__).resolve()
    evidence = PROJECT / "evidence/ui_snapshot_json_component" / build_id
    evidence.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "UI_SNAPSHOT_JSON_COMPONENT_BUILT",
        "build_id": build_id,
        "profile": "ONE_TU_SHARED_LUA_5_1_X64_PROVIDER_NO_GAMECORE",
        "executable": build["executable"],
        "lua_dll": artifact(dll_copy),
        "lua_provider_dll": lua_dll,
        "lua_provider_library": lua_library,
        "lua_provider_build": artifact(provider_path),
        "header": {**artifact(header_path), "original_source": artifact(header_path)},
        "test_source": artifact(test_path),
        "builder": artifact(builder_path),
        "compiler": build["compiler"],
        "compiler_inputs": build["compiler_inputs"],
        "dependency_report": build["dependency_report"],
        "compile_response": build["response"],
        "compile_log": build["log"],
        "import_report": build["imports"],
        "gamecore_loaded": False,
        "gamecore_execution_verified": False,
    }
    out = evidence / "build_result.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "build_id": build_id, "build_result": artifact(out),
                      "executable": report["executable"], "lua_dll": report["lua_dll"],
                      "header": report["header"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
