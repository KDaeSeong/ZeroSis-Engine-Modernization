"""Seal source/no-window evidence without claiming the deferred native/Host gate."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import secrets

from cleanup_intermediates import usage

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
NAMES = ("Source/Presentation/BitmapWindow.h", "Source/Presentation/BitmapWindow.cpp",
         "Source/Presentation/BitmapEditorInput.h", "Source/Host/UiInputDispatch.h",
         "Source/Host/InteractiveGameLoop.h", "Tests/bitmap_window.cpp",
         "Tests/bitmap_editor_input.cpp", "Tests/ui_input_dispatch.cpp",
         "tools/verify_bitmap_window.py", "tools/build_ui_window_host.py")


def ref(path):
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest}


before = {name: ref(ROOT / name) for name in NAMES}
queue_path = HERE / "editor_no_window/20261013T123224Z_9ade395cc76c/conformance.json"
syntax_path = HERE / "editor_syntax_no_window/20261013T123851Z_cce655d5669b/conformance.json"
cleanup_path = HERE / "editor_cleanup/20261013T124212Z_d4ed826f/cleanup.json"
old_cleanup_path = HERE / "cleanup/20261013T115853Z_c0226042/cleanup.json"
queue = json.loads(queue_path.read_text(encoding="utf-8"))
syntax = json.loads(syntax_path.read_text(encoding="utf-8"))
cleanup = json.loads(cleanup_path.read_text(encoding="utf-8"))
old_cleanup = json.loads(old_cleanup_path.read_text(encoding="utf-8"))
assert queue["status"] == "PASS_EDITOR_BUFFER_NO_WINDOW" and queue["source_unchanged"]
assert all(run["status"] == "PASS" and run["checks"] == 17 and run["returncode"] == 0 for run in queue["runs"])
assert {run["optimization"] for run in queue["runs"]} == {"O2", "Od"}
assert syntax["status"] == "PASS_EDITOR_PRESENTATION_SYNTAX_NO_WINDOW" and syntax["source_unchanged"]
assert syntax["objects_or_executables_created"] == []
assert all(run["status"] == "PASS" and run["returncode"] == 0 and not run["warnings"] and
           len(run["dependencies"]) > 1 for run in syntax["runs"])
for name, recorded in queue["source_after"].items():
    assert ref(ROOT / name) == recorded
for name, recorded in syntax["source_after"].items():
    assert ref(ROOT / name) == recorded
assert cleanup["status"] == old_cleanup["status"] == "PASS"
assert cleanup["deleted_files"] == 4 and cleanup["protected_files_unchanged"]

test = (ROOT / "Tests/bitmap_window.cpp").read_text(encoding="utf-8")
start = test.index("bool RunEditorRefreshInputTests() {")
end = test.index("bool RunRetainingInputTests(", start)
new_checks = len(re.findall(r"\bExpect\(", test[start:end]))
assert new_checks == 32
remainder = test[:start] + test[end:]
remainder = remainder.replace('#include "../Source/Presentation/BitmapEditorInput.h"\n', "", 1)
remainder = remainder.replace("    if(!RunEditorRefreshInputTests())return 1;\n", "", 1)
original = (HERE.parent / "source_before/rapid_editor/Tests/bitmap_window.cpp").read_text(encoding="utf-8")
nonblank = lambda value: [line for line in value.splitlines() if line.strip()]
legacy_unchanged = nonblank(remainder) == nonblank(original)
assert legacy_unchanged, "Existing presenter/Unicode assertions changed outside the new test"
constants = {}
for statement in ast.parse((ROOT / "tools/verify_bitmap_window.py").read_text(encoding="utf-8")).body:
    if isinstance(statement, ast.Assign) and len(statement.targets) == 1 and isinstance(statement.targets[0], ast.Name):
        key = statement.targets[0].id
        if key in ("EXPECTED_COMPONENT_CHECKS", "EXPECTED_WINDOW_COM_APARTMENTS"):
            constants[key] = ast.literal_eval(statement.value)
assert constants == {"EXPECTED_COMPONENT_CHECKS": 234, "EXPECTED_WINDOW_COM_APARTMENTS": 10}
for name in ("tools/verify_bitmap_window.py", "tools/build_ui_window_host.py"):
    ast.parse((ROOT / name).read_text(encoding="utf-8"), filename=name)
after = {name: ref(ROOT / name) for name in NAMES}
assert before == after
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + secrets.token_hex(4)
folder = HERE / "editor_final" / stamp
folder.mkdir(parents=True, exist_ok=False)
report = {
    "schema": "ZEROSIS_SAVE_MENU_EDITOR_FIX_HANDOFF_V1",
    "status": "SOURCE_AND_NO_WINDOW_CHECKS_COMPLETE_NATIVE_HOST_GATE_PENDING",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "window_created_in_fix_checks": False, "game_process_accessed": False,
    "installed_mods_or_user_saves_touched": False, "published_ea_modified": False,
    "own_processes_live": cleanup["own_processes_live"],
    "source_before": before, "source_after": after, "source_unchanged_during_seal": True,
    "changed_file_backups": [ref(HERE.parent / "source_before/rapid_editor/before.json"),
                             ref(HERE.parent / "source_before/rapid_editor/ui_popup_context_before.json")],
    "contracts": {
        "stable_editor_owner": "Host serial binds SaveMenu contextSequence, Lua focus epoch, actual SDK player and turn; SDK/Lua calls require held WithCore",
        "native_focus": "bound editor requires nativeTextFocused_; WM_KILLFOCUS suspends; WM_SETFOCUS advances native epoch; WM_CANCELMODE invalidates prefix/raw messages and resumes only while GetFocus equals owned HWND",
        "retention": "production buffer limit 1024; exact nonzero owner and native epoch; TextInput and six edit keys only; original scene generations retained; no SDK/Lua callbacks from WndProc",
        "ordinary_edit_batch": "TextInput/Backspace/Delete/Home/End/Left/Right do not set the terminal action barrier",
        "geometry_terminal_barrier": "pointer callbacks, Enter/Escape and Save clicks keep existing scene-generation rejection; no old/unrelated child is retagged",
        "native_apis": ["EnableTextInput(enabled,error,editorOwner=0)", "GetTextInputState(state,error)",
                        "UpdatePreparedGpuSceneRetainingInput(scene,error,editorOwner=0,textFocusEpoch=0)"],
        "save_menu_game_types": "private saveMenuGameTypes table pushes all five actual CvEnums constants under RequireSaveMenuOwner; no frontend/shared SDK global fabricated",
        "legacy_unbound_transport": "owner 0 deliberately retains the prior synthetic component transport behavior; it cannot enter the production cross-refresh editor buffer"
    },
    "no_window_queue": {"receipt": ref(queue_path), "optimizations": ["O2", "Od"], "checks_each": 17,
                        "scope": "actual production editor buffer, FIFO/generations, repeated edits, owner/epoch rejection, terminal barrier and bounded overflow"},
    "syntax_only": {"receipt": ref(syntax_path), "actual_translation_units": [run["source"] for run in syntax["runs"]],
                    "flags": "actual presenter C++14/W4/WX/O2/MD/fp:strict/diagnostic defines with /Zs",
                    "warnings": 0, "linked": False, "objects_or_executables_created": False},
    "pending_native_window_test": {"executed": False, "expected_checks": 234, "unchanged_legacy_checks": 202,
                                   "new_checks": new_checks, "legacy_source_unchanged_except_blank_lines": legacy_unchanged,
                                   "expected_balanced_com_apartments": 10,
                                   "scope": "rapid posted Korean/Latin text during real preparation drains, same-editor GPU refresh/surrogate continuity, repeated edit keys, actual owned-focus loss/regain, mode cancellation, stale owner/focus/raw queue rejection and close"},
    "uncompiled_host_integration": ["Source/Host/UiPopupContext.h", "Source/Host/InteractiveUiSession.h",
                                    "Source/Host/InteractiveGameLoop.h", "Source/Host/InteractiveGameSession.h"],
    "host_header_handoff_before_scene_S05_lifecycle_delta": {
        "UiPopupContext.h": "55800ba1243f295298b937e3e008cd32897055aa51751bfa4bbf2038fac0d954",
        "InteractiveUiSession.h": "e92cb062143822c80f131932337c54d8961f494fcfe7d4c7a139284403307a85",
        "warning": "These two hashes are pre-S05 observations, not current-file claims; scene agent now owns lifecycle-only changes. Presentation proof does not compile either header."
    },
    "remaining_gates": ["fresh integrated Host compilation against final coordinated Source",
                         "234-check HWND component execution after retail mod-test hold lifts",
                         "rapid continuous actual SaveMenu editor refresh in candidate Host, child/focus/turn/player change rejection",
                         "physical Korean IME composition/commit/candidate placement and original SaveMenu save/load/close runtime"],
    "cleanup": {"latest_receipt": ref(cleanup_path), "latest_deleted_objects": 4, "latest_deleted_bytes": cleanup["deleted_logical_bytes"],
                "prior_receipt": ref(old_cleanup_path), "total_own_deleted_objects": cleanup["deleted_files"] + old_cleanup["deleted_files"],
                "total_own_deleted_bytes": cleanup["deleted_logical_bytes"] + old_cleanup["deleted_logical_bytes"],
                "kept": "changed-file backups, frozen inputs, latest O2/Od test executables/dependencies/logs, original failed receipts and current evidence",
                "owned_build_after": usage(ROOT / "Build/SaveMenuTransport"),
                "evidence_before_final_receipt": usage(HERE), "volume_free_space_measured": False},
    "old_unexecuted_finalize_receipt_py": "obsolete earlier P1-open draft; not this final handoff; original failed/previous PASS receipts remain immutable"
}
target = folder / "handoff.json"
target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
print(json.dumps({"status": report["status"], "receipt": ref(target), "source_files_sealed": len(after),
                  "native_checks_pending": 234, "new_checks": new_checks,
                  "legacy_source_unchanged": legacy_unchanged, "objects_deleted_total": report["cleanup"]["total_own_deleted_objects"],
                  "bytes_deleted_total": report["cleanup"]["total_own_deleted_bytes"]}))
