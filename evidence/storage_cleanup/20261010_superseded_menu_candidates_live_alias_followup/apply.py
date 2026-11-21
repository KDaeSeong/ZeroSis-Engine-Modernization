"""Apply one reviewed follow-up, allowing only audited positive live-EA DDS aliases."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import prepare as f

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    path = f.m.checked(f.OUT / "plan.json")
    f.need(f.digest(path) == args.expected_plan_sha256.lower(), "Reviewed follow-up plan SHA mismatch")
    plan = f.m.read(path)
    f.need(plan["schema"] == f.SCHEMA and plan["status"] == "READY_FOR_ROOT_REVIEW_NO_DELETION" and
        plan["project"] == str(f.ROOT) and plan["targets"] == [str(x) for x in f.m.TARGETS] and plan["policy"] == f.POLICY and
        plan["full_preflight_required_before_delete"] is True,
        "Follow-up exact target/policy contract changed")
    f.need(plan["original_plan"] == dict(path=str(f.ORIGINAL / "plan.json"), sha256=f.ORIGINAL_PLAN_SHA), "Original plan reference changed")
    f.need(not any((f.OUT / name).exists() for name in
        ("application-started.json", "retired.json", "application-failed.json", "unlink-journal.jsonl")), "Apply already started; no replay/resume")
    for name, item in plan["scripts"].items():
        f.need(name in ("prepare.py", "apply.py") and Path(item["path"]) == f.OUT / name and
            f.digest(f.m.checked(Path(item["path"]))) == item["sha256"], "Reviewed follow-up code changed")
    f.need(set(plan["scripts"]) == {"prepare.py", "apply.py"}, "Incomplete reviewed code list")
    original, inventory, protection, diagnostics = f.load_original()
    f.need(plan["original_ledgers"] == {key: original[key] for key in ("inventory", "protection", "diagnostics")}, "Original ledger references changed")
    state, users, processes = f.preflight(original, inventory, protection, diagnostics, plan["accepted_live_alias_additions"])
    if not args.apply:
        print(json.dumps(dict(status="READ_ONLY_FOLLOWUP_PREFLIGHT_PASS_NO_DELETION", plan_sha256=args.expected_plan_sha256,
            files=len(inventory["files"]), user_saves=users["count"], accepted_live_alias_additions=state.addition_records())), flush=True)
        return
    free_before = shutil.disk_usage(f.ROOT).free
    f.write_new("application-started.json", dict(status="STARTED_EXACT_REVIEWED_LIVE_ALIAS_FOLLOWUP_APPLY",
        utc=datetime.now(timezone.utc).isoformat(), plan_sha256=args.expected_plan_sha256, original_plan_sha256=f.ORIGINAL_PLAN_SHA,
        processes=processes, accepted_live_alias_additions=state.addition_records(), free_bytes=free_before))
    removed_files = 0
    try:
        with (f.OUT / "unlink-journal.jsonl").open("x", encoding="utf-8") as journal:
            for row in inventory["files"]:
                path = state.validate_file(row)  # A new link count requires fresh FindNames + per-path checks before unlink.
                f.need(f.m.inside(path), "Unlink escaped exact target roots")
                f.m.low.unlink_without_attribute_changes(path)
                f.need(not path.exists(), "Exact target name remains")
                state.removed_name(path, row); removed_files += 1
                journal.write(json.dumps(dict(path=str(path), identity=row["identity"], sha256=row["sha256"],
                    accepted_added_aliases=len(state.additions[f.pair(row["identity"])]), action="UNLINKED_EXACT_NAME")) + "\n")
                journal.flush()
            os.fsync(journal.fileno())
        for row in sorted(inventory["directories"], key=lambda value: len(Path(value["path"]).parts), reverse=True):
            path = f.m.checked(Path(row["path"])); now = f.m.ident(path.lstat())
            f.need(f.m.inside(path) and now["device"] == row["identity"]["device"] and
                now["file_id"] == row["identity"]["file_id"], "Target directory identity changed during apply")
            path.rmdir()  # Exact inventoried empty directory only; never recursive.
        after_hashes = {}
        for row in protection["files"]: state.validate_file(row, after_hashes)
        state.verify_all(after_hashes)
        processes_after = f.m.process_audit()
        f.need(all(not path.exists() for path in f.m.TARGETS), "A retired target root remains")
        report = dict(status="PASS_EXPLICIT_TEN_ROOT_LIVE_ALIAS_FOLLOWUP_RETIREMENT", removed_files=removed_files,
            retired_roots=[str(path) for path in f.m.TARGETS], plan_sha256=args.expected_plan_sha256,
            original_plan_sha256=f.ORIGINAL_PLAN_SHA, original_plan_and_ledgers_rewritten=False,
            logical_bytes_removed=original["logical_bytes"], estimated_file_storage_reclaimed=state.reclaimable_bytes(),
            free_bytes_before=free_before, free_bytes_after=shutil.disk_usage(f.ROOT).free,
            protected_files_verified=len(protection["files"]), protected_native_user_saves_verified=users["count"],
            original_surviving_aliases_verified=original["surviving_alias_path_count"],
            accepted_live_alias_additions=state.addition_records(), protected_processes_after=processes_after,
            processes_stopped=False, file_attributes_changed=False,
            evidence_claim="Original immutable ledgers and compressed diagnostics remain; same-file-ID additions are explicitly recorded and verified.")
        f.write_new("retired.json", report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    except BaseException as error:
        f.write_new("application-failed.json", dict(status="PARTIAL_OR_FAILED_NO_REPLAY", removed_files=removed_files,
            error=repr(error), accepted_live_alias_additions=state.addition_records(), review_required=True))
        raise

if __name__ == "__main__":
    main()
