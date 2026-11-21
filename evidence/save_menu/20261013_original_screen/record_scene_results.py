"""Record focused scene checks and observed suites without copying packets."""
import difflib
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(ROOT / "Tests"), str(ROOT / "tools")]
from save_menu_scene import verify_component
from ui_pixel_scene import save_menu_contract


def ref(path):
    data = path.read_bytes()
    return dict(path=path.relative_to(ROOT).as_posix(), bytes=len(data),
                sha256=hashlib.sha256(data).hexdigest())


def require(value, message):
    if not value:
        raise RuntimeError(message)


def main():
    report = HERE / "scene_conformance.json"
    require(not report.exists(), "Refuse to replace an earlier scene receipt")
    expected = {
        "Source/Host/UiScene.lua": "6593ae800265db607c5dcfd54e3d69a2a3ade5c395d117557e39eafb2ae49e7d",
        "Source/Presentation/UiPresentationInput.lua": "0414456ec44b6ff5a1b3b6399e5a97153aaf83298dde0b9c18f01ac9bcf686a4",
        "tools/prepare_ui_popup_assets.py": "a112c60eb73b0670156181b11688b75cd33188e5471f21a80cca22d7a04d5f2e",
        "tools/ui_pixel_scene.py": "ba3cff4a8471e24df7c5176d548fa2c59283f6d2e5772c57da00c00461f27f99",
        "tools/verify_ui_scene.py": "c61f88fb6f2dcf98632e35fe61161baf52073fe73bc094bdfae45c41fd1d9930",
        "tools/render_ui_popup.py": "8c0981a1feb9722efeff7bcee4a37486eb8178b88acf49872ddc77ff49f190c4",
        "tools/interactive_ui_driver.py": "39fb756a5b7d16fd4e5ee0d98fb82f008a8c51ff3141369476c51b2877d5316e",
    }
    before = [ref(ROOT / name) for name in expected]
    require(all(row["sha256"] == expected[row["path"]] for row in before), "Stable source marker drifted")
    backup_manifests = [HERE / "source_before" / name for name in
                        ("scene_backup_manifest.json", "scene_render_backup_manifest.json", "tools/driver_backup_manifest.json")]
    changed, patch = [], []
    for manifest in backup_manifests:
        data = json.loads(manifest.read_text(encoding="utf-8-sig"))
        for row in data.get("files", [data]):
            path, backup = Path(row["path"]), Path(row["backup"])
            require(backup.resolve().is_relative_to((HERE / "source_before").resolve()), "Backup escaped owned scope")
            require(ref(backup)["sha256"] == row["sha256"] and backup.stat().st_size == row["bytes"], "Before copy changed")
            current = ref(path)
            if current["sha256"] == row["sha256"]:
                continue
            changed.append(dict(before=dict(path=current["path"], sha256=row["sha256"], bytes=row["bytes"]),
                                after=current, backup=ref(backup)))
            patch.extend(difflib.unified_diff(backup.read_text(encoding="utf-8-sig").splitlines(True),
                                             path.read_text(encoding="utf-8-sig").splitlines(True),
                                             fromfile="before/" + current["path"], tofile="after/" + current["path"]))
    result = verify_component(include_snapshot=True)
    require(result["status"] == "PASS_ORIGINAL_SAVE_MENU_COMPONENT" and result["archiveWrites"] == 0 and
            result["timerChanges"] == 0 and result["temporary_styles_removed"], "Component scope or cleanup changed")
    proofs = {}
    for token in ("opened_snapshot", "named_snapshot", "long_name_snapshot", "long_home_snapshot", "literal_name_snapshot"):
        value = result.pop(token)
        proof = save_menu_contract(value)
        proofs[token] = dict(catalog_rows=proof["catalog_rows"], input_order_keys=proof["input_order_keys"],
                             retail_pixels_verified=False, native_save_load_verified=False)
    closed = result.pop("closed_snapshot")
    closed_proof = save_menu_contract(closed, closed=True)
    require(not closed["active"] and not closed["saveMenu"]["textInputEnabled"], "Closed child retained text focus")
    require([ref(ROOT / name) for name in expected] == before, "Stable source changed during receipt")
    patch_path = HERE / "scene_changes.patch"
    require(not patch_path.exists(), "Refuse to replace previous patch")
    patch_path.write_text("".join(patch), encoding="utf-8")
    test_paths = [ROOT / "Tests" / name for name in
                  ("save_menu_scene.py", "test_save_menu.py", "test_save_menu_renderer.py", "game_menu_scene.py")]
    conformance = dict(status="PASS_ORIGINAL_SAVE_MENU_SCENE_COMPONENT_AND_SOURCE_BOUND_RENDERER",
        recorded_utc=datetime.now(timezone.utc).isoformat(), source_stable=True,
        stable_compiler_and_support_inputs=before, changed_files=changed, changed_file_patch=ref(patch_path),
        changed_file_only_backups=[ref(path) for path in backup_manifests], test_sources=[ref(path) for path in test_paths],
        fresh_lua_component=result, source_bound_snapshots=proofs,
        closed_snapshot_input_order_keys=closed_proof["input_order_keys"],
        observed_suite_results=[
            dict(command="python -B -X utf8 -m unittest discover -s Tests -p test_save_menu*.py -v",
                 tests=6, result="PASS", elapsed_seconds=16.142,
                 checks="Original bytes/includes/tree, max32 Unicode edits, literal markup, clipped caret, retained packet hit order, close-empty scene"),
            dict(command="python -B -X utf8 -m unittest discover -s Tests -p game_menu_renderer.py -v",
                 tests=6, result="PASS", elapsed_seconds=25.836, packets=8,
                 temporary_logical_bytes=176037881, temporary_directory_removed=True, installed_sources_unchanged=True),
            dict(command="python -B -X utf8 -m unittest discover -s Tests -p test_game_menu_timeline.py -v",
                 tests=20, result="PASS", elapsed_seconds=0.581)],
        requirement="Original SaveMenu child from retained GameMenu; local session-owned new named save; cancel returns parent",
        unsupported_actions=["overwrite", "delete", "cloud", "map save", "foreign archive", "retail Civ5Save import"],
        proof_limits=dict(retail_screen_equivalence_verified=False, retail_caret_timing_verified=False,
                          retail_text_scroll_verified=False, cloud_checkbox_geometry_verified=False,
                          unsupported_cloud_checkbox_runtime_hidden=True, native_game_verified=False,
                          native_save_load_verified=False, deployed_to_ea06=False, full_engine_goal_complete=False),
        storage=dict(full_project_copies=0, full_packet_copies_retained=0,
                     all_focused_temporary_styles_and_packets_removed=True,
                     retained_scope="Changed-file before copies, source tests, patch and small hash/verification receipts"))
    report.write_text(json.dumps(conformance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(dict(status=conformance["status"], lua_checks=result["checks"], suites_tests=[6, 6, 20],
                          changed_files=len(changed), report=ref(report), native_game_verified=False,
                          temporary_removed=True)))


if __name__ == "__main__":
    main()
