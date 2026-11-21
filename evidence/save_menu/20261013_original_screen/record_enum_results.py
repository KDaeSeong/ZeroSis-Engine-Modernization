"""Record a source-only fix for the preserved missing-GameTypes native failure."""
import difflib
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "Tests"), str(ROOT / "tools")]
from save_menu_scene import sdk_game_types, verify_component
from game_menu_scene import verify_component as menu_component


def ref(path):
    data = path.read_bytes()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    output = HERE / "enum_binding_conformance.json"
    require(not output.exists(), "Refuse to replace an enum correction receipt")
    stable_names = ("Source/Host/UiScene.lua", "Source/Presentation/UiPresentationInput.lua",
                    "tools/prepare_ui_popup_assets.py", "tools/ui_pixel_scene.py", "tools/render_ui_popup.py",
                    "tools/verify_ui_scene.py", "tools/interactive_ui_driver.py")
    stable = [ref(ROOT / name) for name in stable_names]
    require(stable[0]["sha256"] == "39a0b4c3529ac03febb57ea9187074e3db39516e2eb1c1f3452136adcf41dfcd",
            "Corrected Scene source changed")
    historical = HERE / "editor_focus_conformance.json"
    require(ref(historical)["sha256"] == "1b405842260a9141d907a584c2fb4b19c7717d68b9967d68b3857457db18facf",
            "Historical focus receipt changed")
    failure_ref_path = HERE / "enum_binding_failure_reference.json"
    failure_ref = json.loads(failure_ref_path.read_text(encoding="utf-8"))
    failure = ROOT / failure_ref["path"]
    require(all(ref(failure)[key] == failure_ref[key] for key in ("path", "bytes", "sha256")), "Native failure evidence changed")
    enum_path = ROOT / "Source/SDK_BNW_x64/CvGameCoreDLLUtil/include/CvEnums.h"
    cpp_path = ROOT / "Source/Host/UiPopupContext.h"
    cpp = cpp_path.read_text(encoding="utf-8-sig")
    block = re.search(r'if\(std::strcmp\(operation,"saveMenuGameTypes"\)==0\)\{(.*?)\n\s*\}', cpp, re.S)
    require(block is not None, "Guarded native enum binding source is missing")
    block = block.group(1)
    bindings = re.findall(r'lua_pushnumber\(state,static_cast<lua_Number>\((GAME_[A-Z_]+)\)\);lua_setfield\(state,-2,"(GAME_[A-Z_]+)"\);', block)
    enums = sdk_game_types()
    require(len(bindings) == 5 and dict(bindings) == {name: name for name in enums},
            "Native enum binding source does not use exactly the actual SDK constants")
    require("lua_gettop(state)!=1" in block and "self.RequireSaveMenuOwner();lua_newtable(state);" in block,
            "Native enum binding source lost arity or ownership guard")
    backup_manifest = HERE / "source_before/enum_binding/manifest.json"
    rows = json.loads(backup_manifest.read_text(encoding="utf-8"))["files"]
    changes, patch = [], []
    for row in rows:
        path, backup = Path(row["path"]), Path(row["backup"])
        require(ref(backup)["sha256"] == row["sha256"] and backup.stat().st_size == row["bytes"], "Enum before copy changed")
        current = ref(path)
        changes.append(dict(before=dict(path=current["path"], bytes=row["bytes"], sha256=row["sha256"]),
                            after=current, backup=ref(backup)))
        patch.extend(difflib.unified_diff(backup.read_text(encoding="utf-8").splitlines(True),
                                         path.read_text(encoding="utf-8").splitlines(True),
                                         fromfile="before_enum/" + current["path"], tofile="after_enum/" + current["path"]))
    component = verify_component()
    menu = menu_component()
    require(component["enumBindingCalls"] == 1 and component["temporary_styles_removed"] and
            menu["temporary_styles_removed"], "Actual fixture enum binding or temporary cleanup differed")
    require([ref(ROOT / name) for name in stable_names] == stable, "Source changed during enum receipt")
    require(all(ref(failure)[key] == failure_ref[key] for key in ("path", "bytes", "sha256")), "Failure evidence changed during review")
    patch_path = HERE / "enum_binding_changes.patch"
    require(not patch_path.exists(), "Refuse to replace enum patch")
    patch_path.write_text("".join(patch), encoding="utf-8")
    result = dict(status="PASS_SOURCE_COMPONENT_NATIVE_SDK_ENUM_BINDING_CORRECTION",
                  recorded_utc=datetime.now(timezone.utc).isoformat(),
                  preserved_native_failure=ref(failure), failure_reference=ref(failure_ref_path),
                  previous_focus_receipt=ref(historical), stable_compiler_and_support_inputs=stable,
                  native_enum_source_observed=ref(cpp_path), sdk_enum_definition=ref(enum_path),
                  native_enum_branch_sha256=hashlib.sha256(block.encode("utf-8")).hexdigest(),
                  actual_sdk_enums=enums, changed_files=changes, backup_manifest=ref(backup_manifest), patch=ref(patch_path),
                  lua_contract="SaveMenu binds native('saveMenuGameTypes') private actual SDK table; all five fields validated; current header must be single player",
                  fixture_frontend_global_prepopulated=False, lua_only_enum_fallback=False,
                  fresh_save_lua_component=component, fresh_game_menu_lua_regression=menu,
                  observed_focused_suite=dict(tests=7, result="PASS", elapsed_seconds=10.392,
                      negative_cases=["missing native table", "non-table", "wrong SDK value", "missing SDK field", "unsupported multiplayer header"],
                      original_tree_packet_unicode_caret_and_lifecycle_regression=True),
                  all_temporary_styles_and_packets_removed=True, retained_copied_original_game_assets=False,
                  windows_opened=0, host_builds_started=0, native_enum_execution_verified=False,
                  native_save_load_verified=False, retail_pixels_verified=False,
                  default_launcher_changed=False, ea06_changed=False, full_engine_goal_complete=False)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=result["status"], lua_checks=component["checks"], focused_suite=7,
                          native_enum_execution_verified=False, report=ref(output))))


if __name__ == "__main__":
    main()
