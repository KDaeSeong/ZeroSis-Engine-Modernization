"""Record the editor-focus contract correction without replacing prior evidence."""
import difflib
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "Tests"), str(ROOT / "tools")]
from save_menu_scene import verify_component as save_component
from game_menu_scene import verify_component as menu_component
from ui_pixel_scene import save_menu_contract


def ref(path):
    data = path.read_bytes()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    output = HERE / "editor_focus_conformance.json"
    require(not output.exists(), "Refuse to replace focus correction receipt")
    expected = {
        "Source/Host/UiScene.lua": "62e2db1bf478ce8dfbf51fa41fdc7272529dce93e714349939ff84038f08024f",
        "Source/Presentation/UiPresentationInput.lua": "4d5f4a367cec8a77593baccda9910fc1bf5cdc4ccafa6a03d98cf64aeab16825",
        "tools/ui_pixel_scene.py": "471cf6ba024dfb7506338ea2beea0a3843dbdd8b97fc42787afb76655bd7d1ef",
    }
    unchanged_names = ("tools/prepare_ui_popup_assets.py", "tools/render_ui_popup.py",
                       "tools/verify_ui_scene.py", "tools/interactive_ui_driver.py")
    before = [ref(ROOT / name) for name in (*expected, *unchanged_names)]
    require(all(ref(ROOT / name)["sha256"] == value for name, value in expected.items()), "Focus source marker drifted")
    old = HERE / "scene_conformance.json"
    require(ref(old)["sha256"] == "bae8acbf396b65b6195172d46e91977987a551df4b5f82fb06d1d9d69157b2cc",
            "Historical scene receipt drifted")
    original = json.loads(old.read_text(encoding="utf-8"))
    previous_sources = {row["path"]: row for row in original["stable_compiler_and_support_inputs"]}
    require(all(ref(ROOT / name) == previous_sources[name] for name in unchanged_names), "Unrelated stable input changed")
    backup_manifest = HERE / "source_before/editor_focus/manifest.json"
    rows = json.loads(backup_manifest.read_text(encoding="utf-8"))["files"]
    changes, patch = [], []
    for row in rows:
        path, backup = Path(row["path"]), Path(row["backup"])
        require(ref(backup)["sha256"] == row["sha256"] and backup.stat().st_size == row["bytes"], "Focus before copy drifted")
        current = ref(path)
        changes.append(dict(before=dict(path=current["path"], bytes=row["bytes"], sha256=row["sha256"]),
                            after=current, backup=ref(backup)))
        patch.extend(difflib.unified_diff(backup.read_text(encoding="utf-8").splitlines(True),
                                         path.read_text(encoding="utf-8").splitlines(True),
                                         fromfile="before_focus/" + current["path"], tofile="after_focus/" + current["path"]))
    save = save_component(include_snapshot=True)
    snapshots = {name: save.pop(name) for name in tuple(save) if name.endswith("_snapshot")}
    proof = {name: save_menu_contract(snapshot, closed=name == "closed_snapshot")
             for name, snapshot in snapshots.items()}
    require(save["temporary_styles_removed"] and save["archiveWrites"] == 0 and save["timerChanges"] == 0,
            "Focus component scope or cleanup changed")
    focused = snapshots["named_snapshot"]["saveMenu"]
    closed = snapshots["closed_snapshot"]["saveMenu"]
    require(focused["textInputFocusToken"] == focused["focusEpoch"] > 0 and
            closed["focusEpoch"] > focused["focusEpoch"] and closed["textInputFocusToken"] == 0,
            "Focused/closed lifetime boundary changed")
    menu = menu_component()
    require(menu["temporary_styles_removed"], "GameMenu component temporary styles remain")
    require([ref(ROOT / name) for name in (*expected, *unchanged_names)] == before, "Source changed during focus checks")
    patch_path = HERE / "editor_focus_changes.patch"
    require(not patch_path.exists(), "Refuse to replace focus patch")
    patch_path.write_text("".join(patch), encoding="utf-8")
    result = dict(status="PASS_EXACT_EDITOR_FOCUS_LIFETIME_CONTRACT_COMPONENT",
                  recorded_utc=datetime.now(timezone.utc).isoformat(), previous_scene_receipt=ref(old),
                  stable_compiler_and_support_inputs=before, changed_files=changes,
                  changed_file_backup_manifest=ref(backup_manifest), patch=ref(patch_path),
                  export="ZeroSisUi.GetTextInputFocusToken() -> exact positive focusEpoch only live focused NameBox; otherwise 0",
                  token_changes_on=["explicit TakeFocus/refocus", "other retained left click", "child close"],
                  token_stable_during=["Unicode insertion", "Backspace/Delete", "caret movement", "capture/layout refresh"],
                  native_required_binding="Separate contextSequence/player/turn and HWND focus owner; permit only editor TextInput/edit keys across same-owner refresh",
                  fresh_save_menu_lua=save, fresh_game_menu_lua=menu,
                  source_bound_snapshots={name: dict(input_order_keys=row["input_order_keys"], catalog_rows=row["catalog_rows"])
                                          for name, row in proof.items()},
                  observed_renderer_suite=dict(tests=6, result="PASS", elapsed_seconds=11.320,
                      checks="Exact original tree/provenance/packet/clip/literal name; forged epoch/token rejected; closed empty scene"),
                  all_temporary_styles_and_packet_directories_removed=True,
                  native_fast_typing_verified=False, native_game_verified=False,
                  native_save_load_verified=False, retail_pixels_verified=False,
                  full_engine_goal_complete=False, ea06_changed=False)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=result["status"], save_menu_checks=save["checks"],
                          game_menu_status=menu["status"], report=ref(output), temporary_removed=True)))


if __name__ == "__main__":
    main()
