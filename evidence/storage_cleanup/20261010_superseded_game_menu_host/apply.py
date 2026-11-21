"""Apply only the reviewed six-folder plan. Default mode is read-only preflight."""
from __future__ import annotations
import argparse
import base64
import hashlib
from collections import Counter
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import shutil
import os
import prepare as m

def unpack(reference):
    path = m.checked(Path(reference["path"]))
    m.need(path.parent == m.OUT and m.low.digest(path) == reference["sha256"], "Ledger hash/path changed")
    return json.loads(gzip.decompress(path.read_bytes()))

def pair(row):
    value = row["identity"]
    return value["device"], value["file_id"]

def validate_file(row, removed=None, hashes=None):
    path = m.checked(Path(row["path"]))
    current = m.ident(m.low.regular(path))
    expected = dict(row["identity"])
    if removed: expected["links"] -= removed.get(pair(row), 0)
    m.need(current == expected, "File identity/mtime/attributes/link count changed: " + str(path))
    if hashes is not None:
        key = pair(row)
        if key not in hashes: hashes[key] = m.low.digest(path)
        m.need(hashes[key] == row["sha256"] and m.ident(m.low.regular(path)) == expected,
               "File SHA or stable metadata changed: " + str(path))
    return path

def verify_aliases(groups, removed=None, hashes=None):
    parents = set()
    for group in groups:
        names = group["surviving_aliases"]
        if not names: continue
        row = dict(identity=group["identity"], sha256=group["sha256"])
        expected = dict(group["identity"])
        expected["links"] -= (removed or {}).get((expected["device"], expected["file_id"]), 0)
        for name in names:
            path = Path(name)
            m.need(not m.inside(path), "Surviving alias entered target")
            for parent in path.parents:
                if parent in parents: break
                value = parent.lstat()
                m.need(not value.st_file_attributes & 0x400 and parent.is_dir(), "Alias ancestor changed")
                parents.add(parent)
            m.need(m.ident(m.low.regular(path)) == expected, "Surviving alias metadata changed")
        row["path"] = names[0]
        validate_file(row, removed, hashes)
        observed = {str(x).casefold() for x in m.links.hardlink_names(Path(names[0]))}
        wanted = set(names if removed else names + group["target_paths"])
        m.need(observed == {x.casefold() for x in wanted}, "Surviving hardlink names changed")

def current_tree(inventory):
    seen_files, seen_dirs = set(), set()
    for target in m.TARGETS:
        for path, info, directory in m.walk(target):
            (seen_dirs if directory else seen_files).add(str(path))
    m.need(seen_files == {row["path"] for row in inventory["files"]} and
           seen_dirs == {row["path"] for row in inventory["directories"]}, "Target contents changed")
    for row in inventory["directories"]:
        path = m.checked(Path(row["path"]))
        m.need(m.ident(path.lstat()) == row["identity"], "Directory identity or contents timestamp changed")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--apply", action="store_true", help="Use only after root has reviewed and approved the exact plan")
    args = parser.parse_args()
    plan_path = m.checked(m.OUT / "plan.json")
    m.need(m.low.digest(plan_path) == args.expected_plan_sha256.lower(), "Reviewed plan hash mismatch")
    plan = m.read(plan_path)
    m.need(plan["schema"] == "ZEROSIS_EXPLICIT_SIX_FOLDER_RETIREMENT_V1" and
           plan["status"] == "READY_FOR_ROOT_REVIEW_NO_DELETION" and
           plan["project"] == str(m.ROOT) and plan["targets"] == [str(x) for x in m.TARGETS],
           "Plan is not the explicit six-folder scope")
    m.need(not (m.OUT / "application-started.json").exists(), "This plan was already started; no replay/resume is allowed")
    for item in [*plan["scripts"].values(), *plan["helper_inputs"]]:
        m.need(m.low.digest(m.checked(Path(item["path"]))) == item["sha256"], "Reviewed code changed")
    replacement = m.ROOT / "evidence/ui_window_host" / m.NEW_HOST / "build_result.json"
    m.need(m.low.digest(replacement) == m.NEW_REPORT_SHA and
           m.read(replacement)["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT", "Replacement changed")
    inventory = unpack(plan["inventory"]); protection = unpack(plan["protection"]); diagnostics = unpack(plan["diagnostics"])
    m.need(len(inventory["files"]) == plan["target_file_count"] and
           len(inventory["directories"]) == plan["target_directory_count"], "Inventory count changed")
    m.need(all(m.inside(Path(row["path"])) for row in inventory["files"] + inventory["directories"]), "Inventory escaped target roots")
    m.need(all(not m.inside(Path(row["path"])) for row in protection["files"]), "Protected path overlaps target")
    current_tree(inventory)
    hashes = {}
    for row in inventory["files"] + protection["files"]: validate_file(row, hashes=hashes)
    verify_aliases(inventory["groups"], hashes=hashes)
    m.need(m.session_audit() == protection["session"], "Retiring session/saves changed or acquired manual data")
    m.need(m.request_audit() == protection["requests"], "Runtime request set or dependencies changed")
    processes_before = m.process_audit()
    for original in diagnostics["originals"]:
        raw = base64.b64decode(original["content_base64"], validate=True)
        m.need(len(raw) == original["bytes"] and hashlib.sha256(raw).hexdigest() == original["sha256"],
               "Compressed diagnosis cannot restore the original bytes")
        path = Path(original["path"])
        m.need(m.inside(path) and path.stat().st_size == original["bytes"] and
               m.low.digest(path) == original["sha256"], "Original diagnosis drifted")
    if not args.apply:
        print(json.dumps(dict(status="READ_ONLY_PREFLIGHT_PASS_NO_DELETION", files=len(inventory["files"]),
                              plan_sha256=args.expected_plan_sha256)))
        return
    free_before = shutil.disk_usage(m.ROOT).free
    # An exclusive marker makes a partial run non-replayable.
    m.write_new("application-started.json", dict(status="STARTED_EXACT_REVIEWED_SIX_FOLDER_APPLY",
        utc=datetime.now(timezone.utc).isoformat(), plan_sha256=args.expected_plan_sha256,
        processes=processes_before, free_bytes=free_before))
    removed, removed_files = Counter(), 0
    try:
        with (m.OUT / "unlink-journal.jsonl").open("x", encoding="utf-8") as journal:
            for row in inventory["files"]:
                path = validate_file(row, removed)
                m.need(m.inside(path), "Unlink escaped one of the six resolved roots")
                # Deletes only this name; never flips read-only/compression flags
                # on an inode whose other hardlinks remain in active runtimes.
                m.low.unlink_without_attribute_changes(path)
                m.need(not path.exists(), "Exact target name was not removed")
                removed[pair(row)] += 1; removed_files += 1
                journal.write(json.dumps(dict(path=str(path), device=pair(row)[0], file_id=pair(row)[1],
                                              sha256=row["sha256"])) + "\n")
                journal.flush()
            os.fsync(journal.fileno())
        for row in sorted(inventory["directories"], key=lambda value: len(Path(value["path"]).parts), reverse=True):
            path = m.checked(Path(row["path"])); now = m.ident(path.lstat())
            m.need(m.inside(path) and now["device"] == row["identity"]["device"] and
                   now["file_id"] == row["identity"]["file_id"], "Directory identity changed during apply")
            path.rmdir()  # Empty, explicitly inventoried directory only; no recursive delete.
        after_hashes = {}
        for row in protection["files"]: validate_file(row, removed, after_hashes)
        verify_aliases(inventory["groups"], removed, after_hashes)
        processes_after = m.process_audit()
        m.need(all(not path.exists() for path in m.TARGETS), "A retired target remains")
        report = dict(status="PASS_EXPLICIT_SIX_FOLDER_RETIREMENT", original_targets_status="RETIRED",
            evidence_claim="Only compressed original diagnostics and full hash/identity ledgers remain; deleted runtime, images and saves are not current retained evidence.",
            removed_files=removed_files, retired_roots=[str(x) for x in m.TARGETS],
            plan_sha256=args.expected_plan_sha256, logical_bytes_removed=plan["logical_bytes"],
            estimated_file_storage_reclaimed=plan["estimated_reclaimable_file_storage_bytes"],
            free_bytes_before=free_before, free_bytes_after=shutil.disk_usage(m.ROOT).free,
            protected_files_verified=len(protection["files"]), surviving_aliases_verified=plan["surviving_alias_path_count"],
            protected_processes_after=processes_after, compressed_live_files=False, processes_stopped=False)
        m.write_new("retired.json", report)
        print(json.dumps(report, ensure_ascii=False))
    except BaseException as error:
        m.write_new("application-failed.json", dict(status="PARTIAL_OR_FAILED_NO_REPLAY",
            removed_files=removed_files, error=repr(error), review_required=True))
        raise

if __name__ == "__main__":
    main()
