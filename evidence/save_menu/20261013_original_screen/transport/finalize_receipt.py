"""Record focused transport results and the independent root integration review."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def ref(path):
    data = path.read_bytes()
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


bitmap_path = HERE / "bitmap/20261013T112135Z_d547173d8dc5/conformance.json"
dispatch_path = HERE / "dispatch/20261013T112531Z_d1019749ec3c/conformance.json"
cleanup_path = HERE / "cleanup/20261013T115853Z_c0226042/cleanup.json"
bitmap = json.loads(bitmap_path.read_text(encoding="utf-8"))
dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
cleanup = json.loads(cleanup_path.read_text(encoding="utf-8"))
assert bitmap["status"] == "BITMAP_WINDOW_COMPONENT_PASS" and bitmap["source_inputs_unchanged"]
assert [(run["checks"], run["com_init_markers"], run["com_uninit_markers"], run["returncode"])
        for run in bitmap["test_runs"]] == [(202, 9, 9, 0), (202, 9, 9, 0)]
assert dispatch["status"] == "PASS_UI_INPUT_DISPATCH_NATIVE" and dispatch["inputs_unchanged_after_run"]
assert [run["checks"] for run in dispatch["native_test"]["runs"]] == [122, 122]
assert dispatch["legacy_regression"]["status"] == "PASS_UI_PRESENTATION_INPUT_COMPONENT_ONLY"
assert cleanup["status"] == "PASS" and cleanup["deleted_files"] == 22
assert cleanup["deleted_logical_bytes"] == 14029046 and cleanup["protected_files_unchanged"]
sources = ("Source/Presentation/BitmapWindow.h", "Source/Presentation/BitmapWindow.cpp",
           "Source/Host/UiInputDispatch.h", "Tests/bitmap_window.cpp", "Tests/ui_input_dispatch.cpp",
           "tools/verify_bitmap_window.py", "tools/build_ui_window_host.py")
result = {
    "schema": "ZEROSIS_SAVE_MENU_TEXT_TRANSPORT_HANDOFF_V1",
    "created_utc": datetime.now(timezone.utc).isoformat(),
    "status": "TRANSPORT_COMPONENT_PASS_INTEGRATION_REVIEW_HAS_FINDINGS",
    "changed_sources": [ref(ROOT / source) for source in sources],
    "bitmap": {"conformance": ref(bitmap_path), "O2_checks": 202, "Od_checks": 202,
               "COM_init_per_run": 9, "COM_release_per_run": 9,
               "unicode_marker_required": True, "unchanged_source_gate": True},
    "dispatcher": {"conformance": ref(dispatch_path), "O2_checks": 122, "Od_checks": 122,
                   "legacy_status": dispatch["legacy_regression"]["status"],
                   "legacy_conformance": dispatch["legacy_regression"]["conformance"],
                   "unchanged_source_gate": True},
    "cleanup": {"receipt": ref(cleanup_path), "deleted_files": 22,
                "deleted_logical_bytes": 14029046, "protected_files_verified": 704,
                "before_build_bytes": 40503195, "after_build_bytes": 26474149,
                "source_or_save_deleted": False, "volume_free_space_measured": False},
    "integration_review": {
        "type": "independent read-only source review",
        "reviewed_root_hashes": {
            "Source/Host/InteractiveGameSession.h": "3e24acfd3478b0c8b3ac535fbb4100a91a22644adc30e3337a58ada48c5c4b93",
            "Source/Host/InteractiveUiSession.h": "f0fe9def63941cc2014e67178d2c3ca5e0d971e52a9023310251c3d5498671b0",
            "Source/Host/InteractiveGameLoop.h": "3904d13f55ff171e33e9d95b71d2eb86881d2a38c891a1ea2f915fd3868e5045",
            "Source/Host/UiPopupContext.h": "bdf5ea4c98e9dde0a3cb58f125dc96a18af75bcd4f1efb1b52512f445800152f"},
        "findings": [
            {"priority": "P1", "file": "Source/Host/InteractiveGameLoop.h", "lines": [188, 209, 542, 837],
             "description": "Every consumed NameBox character redraws. During WaitForUiPacket, PumpMessages admits later committed characters and unconditional RejectPending discards them. Fast real typing can lose characters during scene preparation.",
             "required_boundary": "Preserve textual input only for an explicitly stable same-child focused NameBox owner; reject it on focus, child, player or turn change. Keep scene-based click rejection."},
            {"priority": "P1", "file": "Source/Host/InteractiveGameLoop.h", "lines": [800, 836],
             "description": "Any KeyDown sets acted. Same-batch repeated Backspace/Delete/caret keys are discarded after the first although the text-owning child and focused NameBox remain unchanged.",
             "required_boundary": "Distinguish in-place edit keys from Return/Escape and callbacks that replace or close UI."}],
        "no_additional_concrete_issue_found": [
            "Save/Close requests are taken before Update releases the child VM.",
            "Child timer stays Released while the suspended GameMenu retains its timer.",
            "Named save closes the restored parent before archive capture.",
            "Text mode is default off and enabled from the focused child Frame only after scene commit.",
            "Corrected opt-in GPU capture uses cached frame context outside WithCore; SDK-dependent SaveMenu queries remain inside Owner/WithCore."],
        "root_source_edited_by_this_agent": False,
        "integration_findings_fixed_by_this_agent": False},
    "proof_limits": {"full_host_built_by_this_agent": False, "retail_launched_by_this_agent": False,
                     "physical_korean_ime_verified": False, "human_input_verified": False,
                     "integrated_namebox_input_loss_verified_at_runtime": False},
    "original_failed_receipts_preserved": [ref(HERE / path) for path in (
        "bitmap/20261013T111458Z_c0476a5e3df2/conformance.json",
        "bitmap/20261013T111731Z_b1c816d17e2a/conformance.json",
        "bitmap/20261013T111853Z_ac744b7aec3b/conformance.json",
        "bitmap/20261013T112005Z_e6571f4ea008/conformance.json",
        "dispatch/20261013T112303Z_ca89ab67334b/conformance.json")],
}
target = HERE / "final_receipt.json"
with target.open("x", encoding="utf-8", newline="\n") as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
    stream.write("\n")
print(json.dumps(ref(target)))
