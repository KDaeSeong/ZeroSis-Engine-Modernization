"""Remove only the four sealed no-HWND editor-check OBJ intermediates."""
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import subprocess

from cleanup_intermediates import boundary, digest, record, require, usage, write, SHELL

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
BUILD = ROOT / "Build/SaveMenuTransport"
RUNS = ("20261013T122252Z_fc65fe54af84", "20261013T123224Z_9ade395cc76c")
PROTECTED_SOURCE = ("Source/Presentation/BitmapWindow.h", "Source/Presentation/BitmapWindow.cpp",
                    "Source/Presentation/BitmapEditorInput.h", "Tests/bitmap_window.cpp",
                    "Tests/bitmap_editor_input.cpp", "Source/Host/InteractiveGameLoop.h",
                    "Source/Host/UiInputDispatch.h", "tools/verify_bitmap_window.py",
                    "tools/build_ui_window_host.py")


def require_own_tests_terminal():
    # Query only this console test name; never enumerate retail game processes.
    result = subprocess.run([str(SHELL), "-NoLogo", "-NoProfile", "-Command",
                             "@(Get-Process -Name editor_queue -ErrorAction SilentlyContinue).Count"],
                            capture_output=True, text=True, timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    require(result.returncode == 0 and result.stdout.strip() == "0",
            "A no-HWND editor console test is still active or its status is unknown")


require_own_tests_terminal()
rows = []
receipts = []
for run_id in RUNS:
    receipt_path = HERE / "editor_no_window" / run_id / "conformance.json"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    require(receipt["status"] == "PASS_EDITOR_BUFFER_NO_WINDOW" and receipt["source_unchanged"],
            "Expected terminal source-bound no-window proof is not valid")
    receipts.append(record(receipt_path))
    for completed in receipt["runs"]:
        require(completed["status"] == "PASS" and completed["returncode"] == 0, "Own test was not terminal")
        obj = completed["object"]
        path = boundary(Path(obj["path"]), BUILD / "E")
        expected = BUILD / "E" / run_id[-12:] / completed["optimization"] / "editor_queue.obj"
        require(path == expected and path.name == "editor_queue.obj", "Object is outside its exact owned run")
        row = record(path)
        require(row["sha256"] == obj["sha256"] and row["bytes"] == obj["bytes"] and row["links"] == 1,
                "Sealed object changed or acquired another hardlink")
        rows.append(row)
require(len(rows) == 4 and len({row["path"] for row in rows}) == 4, "Expected exactly four owned objects")
candidate_paths = {row["path"] for row in rows}
protected_paths = [ROOT / name for name in PROTECTED_SOURCE]
protected_paths += [path for path in BUILD.rglob("*") if path.is_file() and str(path) not in candidate_paths]
protected_paths += [path for path in HERE.rglob("*") if path.is_file()]
protected = [record(path) for path in dict.fromkeys(protected_paths)]
protected_ids = {(row["device"], row["file_id"]) for row in protected}
require(not any((row["device"], row["file_id"]) in protected_ids for row in rows),
        "An object aliases protected source, result or evidence")
before = usage(BUILD)
stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + secrets.token_hex(4)
folder = HERE / "editor_cleanup" / stamp
folder.mkdir(parents=True, exist_ok=False)
plan = folder / "plan.json"
write(plan, {"schema": "ZEROSIS_EDITOR_NO_WINDOW_OBJ_CLEANUP_PLAN_V1", "candidates": rows,
             "completed_receipts": receipts, "protected": protected, "before_build": before,
             "only_exact_owned_objects": True, "host_headers_owned_by_parallel_scene_agent_excluded_from_hash_gate": True})
deleted = []
for row in rows:
    path = boundary(Path(row["path"]), BUILD / "E")
    require(record(path) == row, "Object changed after cleanup plan")
    path.unlink()
    require(not path.exists(), "Deleted object remains")
    deleted.append({**row, "result": "deleted"})
for row in protected:
    require(record(Path(row["path"])) == row, "Protected file changed during cleanup")
require_own_tests_terminal()
after = usage(BUILD)
removed = sum(row["bytes"] for row in rows)
require(after["unique_logical_bytes"] == before["unique_logical_bytes"] - removed,
        "Unexpected owned build size change")
target = folder / "cleanup.json"
write(target, {"schema": "ZEROSIS_EDITOR_NO_WINDOW_OBJ_CLEANUP_RESULT_V1", "status": "PASS",
               "plan": record(plan), "deleted": deleted, "deleted_files": len(rows), "deleted_logical_bytes": removed,
               "before_build": before, "after_build": after, "protected_files_verified": len(protected),
               "protected_files_unchanged": True, "remaining_obj_files": len(list(BUILD.rglob("*.obj"))),
               "source_or_saves_deleted": False, "game_process_accessed": False, "own_processes_live": 0,
               "volume_free_space_measured": False})
print(json.dumps({"status": "PASS", "receipt": {"path": str(target), "sha256": digest(target)},
                  "deleted_files": len(rows), "deleted_logical_bytes": removed,
                  "before_build": before, "after_build": after, "protected_files_verified": len(protected)}))
