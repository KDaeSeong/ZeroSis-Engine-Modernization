"""Read-only reassessment; never promotes or rewrites the original native failure."""
from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / "tools"))
import verify_interactive_decisions as v
from run_interactive_game import frozen_ui_support_source

RUN = "20261010T080723Z_86472427ac3f"
EV = ROOT / "evidence/interactive_game" / RUN
OUT = Path(__file__).with_name("independent_fresh_080723_reassessment_final.json")
FIRST = Path(__file__).with_name("independent_fresh_080723_reassessment.json")
SECOND = Path(__file__).with_name("independent_fresh_080723_reassessment_fixed_call.json")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    if OUT.exists():
        raise RuntimeError("Refusing to overwrite an existing independent report")
    rq, rs, driver = [load(EV / n) for n in ("request.json", "result.json", "driver_result.json")]
    text = (EV / "stdout.log").read_text(encoding="utf-8")
    runtime = Path(rq["cwd"]).resolve(strict=True)
    paths = [EV / n for n in ("request.json", "result.json", "stdout.log", "driver_result.json")]
    paths += [Path(r["path"]) for r in rq["provenance"]["worker_research_verifiers"].values()]
    before = {str(p): sha(p) for p in paths}
    diagnostics_before = {str(p): sha(p) for p in (FIRST, SECOND)}
    report = {
        "status": "FAILED_INDEPENDENT_REASSESSMENT",
        "run_id": RUN,
        "utc": datetime.now(timezone.utc).isoformat(),
        "scope": "Corrected current validator reads immutable native evidence. Original FAILED result and old frozen validator remain authoritative for run acceptance. No native execution, restore, release promotion or raw FAIL-to-PASS conversion.",
        "earlier_diagnostic_failures": [row(p) for p in (FIRST, SECOND)],
        "earlier_diagnostic_failure_explanation": "The first one-off report script passed the keyword-only restored parameter positionally. The next reporting attempt assumed the successful worker proof dictionary had a passed field, whereas success is expressed by return without exception and contract_version=1. Both are reporting-call mistakes, not production verifier or native errors. This follow-up corrects the report script only and preserves both failed reports.",
        "original_result": row(EV / "result.json"),
        "current_verifier": row(ROOT / "tools/verify_interactive_decisions.py"),
        "old_frozen_verifier": row(Path(rq["provenance"]["worker_research_verifiers"]["verify_interactive_decisions.py"]["path"])),
        "raw_status": rs["status"],
        "raw_failures": rs["failures"],
        "raw_host_returncode": rs["returncode"],
        "timed_out": rs["timed_out"],
        "new_native_execution_performed": False,
        "restore_started": False,
        "full_fresh_restore_pair_passed": False,
        "full_gameplay_verified": False,
    }
    try:
        assert rs["status"] == "CONTINUOUS_INTERACTIVE_SDK_WORKER_BUILD_SMOKE_FAILED"
        assert rs["returncode"] == 0 and rs["timed_out"] is False
        assert rs["failures"] == ["Natural worker research validation failed: Frozen original Lua does not bind the delivered small button to the same research callback"]
        assert driver["status"] == "INTERACTIVE_UI_DRIVER_PASS" and driver["returncode"] == 0
        assert v.worker_research_contract_required(rq) is True
        research = v.verify_worker_research_integration(text, runtime, driver, rs["frames"], required=True)
        assert research["contract_version"] == 1 and len(research["turns"]) == 6
        assert len(research["awards"]) == len(research["continuations"]) == 0
        assert len(research["original_callbacks"]) == 1
        report["corrected_worker_research_integration"] = {"passed": True, **research}
        report["natural_award_and_subsequent_research_selection_exercised"] = False
        report["include_callback_root_cause"] = "TechTree.lua includes TechButtonInclude; the original callback and SetVoids/RegisterCallback helper are split between those two manifest/hash-verified files. The old new-integration call passed only TechTree.lua into a helper that needed both bodies. The corrected call proves that exact include relation, callback and payload without accepting arbitrary concatenated Lua."
        print("CORRECTED_ACTUAL_FROZEN_CALLBACK_AND_SIX_TURN_PROOF_PASS", flush=True)
        unit = v.verify_unit_panel_integration(text, runtime, driver, rs["frames"], required=True,
            restored=False, unit_actions=True, worker_build=True, decisions=True)
        assert unit == rs["original_unit_panel_integration"]
        report["original_unit_panel_recomputed_equal"] = True
        report["unit_panel_initial"] = unit["initial"]
        report["unit_panel_mission_count"] = len(unit["missions"])
        action = v.verify_action_info_panel_timeline(text, False, True, True)
        notification = v.verify_notification_panel_timeline(text, restored=False)
        assert action == (True, None) and notification == (True, None)
        report["original_hud_and_notification_timelines"] = {"action_info_panel": action, "notification_panel": notification}
        completed = re.findall(r"^INTERACTIVE_WORKER_BUILD_COMPLETED=([^\r\n]+)$", text, re.M)
        assert completed == ["32770|571|2|3|6"]
        report["worker_build_completed"] = {"unit": 32770, "plot": 571, "build": 2, "improvement": 3, "turn": 6}
        assert len(rs["native_saves"]) == 2
        save_rows, save_sections, indices = [], [], []
        for number, (turn, name) in enumerate(rs["native_saves"], 1):
            path = Path(name).resolve(strict=True)
            assert path.is_relative_to((runtime / "sessions").resolve(strict=True))
            assert path.name == f"play-save-{number}-turn-6.zssave" and int(turn) == 6
            header, sections = v.parse_native_archive(path)
            assert header["turn"] == 6 and len(sections) == 133
            save_rows.append({"artifact": row(path), "header": header})
            save_sections.append(sections)
            marker = f"INTERACTIVE_NATIVE_SAVE=6|{name}"
            assert text.count(marker) == 1
            indices.append(text.index(marker))
        for marker in ("INTERACTIVE_PLAY_CLOSED=6|NATIVE_CHECKPOINT_WRITTEN", "INTERACTIVE_GAME_SESSION_STOPPED=true", "INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true"):
            assert text.count(marker) == 1
            indices.append(text.index(marker))
        assert indices == sorted(indices) and len(set(indices)) == len(indices)
        report["native_save_archives"] = save_rows
        report["native_save_section_equality"] = {"total": 133, "equal": sum(save_sections[0][k] == save_sections[1][k] for k in save_sections[0]), "scope": "Two explicit saves in this fresh run; not restore equivalence."}
        report["two_saves_then_normal_close_verified"] = True
        proof = v.provenance(rq, rs, runtime, research_tree=True)
        report["frozen_host_and_runtime_provenance_verified"] = True
        report["provenance_output_keys"] = sorted(proof)
        print("UNIT_PANEL_HUD_NATIVE_SAVES_NORMAL_CLOSE_FROZEN_PROVENANCE_PASS", flush=True)
        rejected = {}
        for name, fn in (("read_run", lambda: v.read_run(RUN, research_tree=True)),
                         ("frozen_ui_support_source", lambda: frozen_ui_support_source(RUN))):
            try:
                fn()
            except RuntimeError as exc:
                rejected[name] = str(exc)
            else:
                raise AssertionError(f"{name} incorrectly accepted the original FAILED run")
        report["original_failed_run_remains_ineligible"] = rejected
        after = {str(p): sha(p) for p in paths}
        assert before == after and diagnostics_before == {str(p): sha(p) for p in (FIRST, SECOND)}
        report["raw_and_frozen_files_unchanged"] = before
        report["original_failed_result_preserved"] = True
        report["both_diagnostic_failures_preserved"] = True
        report["changed_sources"] = [row(ROOT / n) for n in ("tools/verify_interactive_decisions.py", "Tests/test_worker_research_timeline.py")]
        fixture_dir = ROOT / "Tests/fixtures/worker_research_callbacks"
        report["portable_actual_lua_regression_fixtures"] = [row(p) for p in sorted(fixture_dir.iterdir()) if p.is_file()]
        report["related_tests_completed_before_reassessment"] = {
            "total_passed": 63, "production_sources_unchanged_since_tests": True,
            "commands": [{"command": "python -B -X utf8 " + name, "passed": count} for name, count in (
                ("Tests/test_worker_research_timeline.py", 22),
                ("Tests/interactive_decision_hit_contract.py", 4),
                ("Tests/interactive_decision_timer_contract.py", 2),
                ("Tests/test_worker_unit_panel_profile.py", 10),
                ("Tests/action_info_panel_timeline.py", 25))]}
        report["status"] = "PASS_CORRECTED_INDEPENDENT_SCOPED_PROOFS_ORIGINAL_NATIVE_RESULT_REMAINS_FAILED"
    except Exception as exc:
        report["error"] = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(json.dumps({"report": str(OUT), "status": report["status"], "bytes": OUT.stat().st_size, "sha256": sha(OUT)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
