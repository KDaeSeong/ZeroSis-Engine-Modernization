"""One explicit 6-root apply. Default is read-only preflight; no plan replay."""
from __future__ import annotations
import argparse
import base64
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import prepare as m

def unpack(reference):
    path = m.checked(Path(reference["path"]))
    m.need(path.parent == m.OUT and m.low.digest(path) == reference["sha256"], "Ledger hash/path changed")
    raw = gzip.decompress(path.read_bytes())
    m.need(len(raw) == reference["uncompressed_bytes"] and
           hashlib.sha256(raw).hexdigest() == reference["uncompressed_sha256"], "Ledger roundtrip hash/length changed")
    return json.loads(raw)

def pair(row):
    return row["identity"]["device"], row["identity"]["file_id"]

def validate_file(row, removed=None, hashes=None):
    path = m.checked(Path(row["path"]))
    expected = dict(row["identity"])
    expected["links"] -= (removed or {}).get(pair(row), 0)
    m.need(m.ident(m.low.regular(path)) == expected, "File identity/mtime/attributes/links changed: " + str(path))
    if hashes is not None:
        key = pair(row)
        if key not in hashes: hashes[key] = m.low.digest(path)
        m.need(hashes[key] == row["sha256"] and m.ident(m.low.regular(path)) == expected,
               "File SHA/stable metadata changed: " + str(path))
    return path

def verify_aliases(groups, removed=None, hashes=None):
    parents = set()
    for group in groups:
        names = group["surviving_aliases"]
        if not names: continue
        expected = dict(group["identity"])
        key = expected["device"], expected["file_id"]
        expected["links"] -= (removed or {}).get(key, 0)
        for name in names:
            path = Path(name)
            m.need(not m.inside(path), "Surviving alias entered targets")
            for parent in path.parents:
                if parent in parents: break
                info = parent.lstat()
                m.need(parent.is_dir() and not info.st_file_attributes & 0x400, "Alias ancestor changed")
                parents.add(parent)
            m.need(m.ident(m.low.regular(path)) == expected, "Surviving alias metadata changed: " + str(path))
        validate_file(dict(path=names[0], identity=group["identity"], sha256=group["sha256"]), removed, hashes)
        observed = {str(x).casefold() for x in m.hardlink_names(Path(names[0]))}
        wanted = names if removed is not None else names + group["target_paths"]
        m.need(observed == {x.casefold() for x in wanted}, "Surviving hardlink names changed")

def current_tree(inventory):
    files, directories = set(), set()
    for target in m.TARGETS:
        for path, info, directory in m.walk(target):
            (directories if directory else files).add(str(path))
    m.need(files == {row["path"] for row in inventory["files"]} and
           directories == {row["path"] for row in inventory["directories"]}, "Target membership changed")
    for row in inventory["directories"]:
        path = m.checked(Path(row["path"]))
        m.need(m.ident(path.lstat()) == row["identity"], "Directory identity/mtime changed")

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--apply", action="store_true", help="Root must review the code and exact plan SHA first")
    args = parser.parse_args()
    plan_path = m.checked(m.OUT / "plan.json")
    m.need(m.low.digest(plan_path) == args.expected_plan_sha256.lower(), "Reviewed plan SHA mismatch")
    plan = m.read(plan_path)
    m.need(plan["schema"] == m.SCHEMA and plan["status"] == "READY_FOR_ROOT_REVIEW_NO_DELETION" and
           plan["project"] == str(m.ROOT) and plan["targets"] == [str(x) for x in m.TARGETS] and len(m.TARGETS) == 6,
           "Plan is not the exact 6-root contract")
    m.need(not any((m.OUT / name).exists() for name in ("application-started.json", "retired.json", "application-failed.json", "unlink-journal.jsonl")), "Apply was already started; no replay/resume")
    for item in [*plan["scripts"].values(), *plan["helper_inputs"]]:
        m.need(m.low.digest(m.checked(Path(item["path"]))) == item["sha256"], "Reviewed code changed")
    m.need(m.replacement_audit() == plan["replacements"], "Protected replacement menu pair changed")
    m.process_audit()
    inventory = unpack(plan["inventory"]); protection = unpack(plan["protection"]); diagnostics = unpack(plan["diagnostics"])
    m.need(len(inventory["files"]) == plan["target_file_count"] and
           len(inventory["directories"]) == plan["target_directory_count"], "Inventory counts changed")
    m.need(all(m.inside(Path(row["path"])) for row in inventory["files"] + inventory["directories"]), "Inventory escaped")
    m.need(all(not m.inside(Path(row["path"])) for row in protection["files"]), "Protection intersects targets")
    current_tree(inventory)
    hashes = {}
    for row in inventory["files"] + protection["files"]: validate_file(row, hashes=hashes)
    verify_aliases(inventory["groups"], hashes=hashes)
    m.need(m.sessions_audit() == protection["sessions"], "Candidate sessions/saves changed or acquired manual data")
    users = m.user_save_audit()
    m.need(users == protection["user_saves"], "Protected user save set or its identities/content changed")
    # Existing protected request files are SHA-checked above. A newly completed
    # noncandidate request is allowed only after its references pass this audit.
    requests = m.request_audit()
    processes_before = m.process_audit()
    for item in diagnostics["originals"]:
        raw = base64.b64decode(item["content_base64"], validate=True)
        m.need(len(raw) == item["bytes"] and hashlib.sha256(raw).hexdigest() == item["sha256"],
               "Original diagnostic roundtrip failed")
        path = Path(item["path"])
        m.need(m.inside(path) and path.stat().st_size == item["bytes"] and m.low.digest(path) == item["sha256"],
               "Original diagnostic drifted")
    if not args.apply:
        print(json.dumps(dict(status="READ_ONLY_PREFLIGHT_PASS_NO_DELETION", files=len(inventory["files"]),
                              protected=len(protection["files"]), user_saves=users["count"],
                              plan_sha256=args.expected_plan_sha256)), flush=True)
        return
    free_before = shutil.disk_usage(m.ROOT).free
    m.write_new("application-started.json", dict(status="STARTED_EXACT_REVIEWED_SIX_ROOT_APPLY",
        utc=datetime.now(timezone.utc).isoformat(), plan_sha256=args.expected_plan_sha256,
        processes=processes_before, free_bytes=free_before))
    removed, removed_files = Counter(), 0
    try:
        with (m.OUT / "unlink-journal.jsonl").open("x", encoding="utf-8") as journal:
            for row in inventory["files"]:
                path = validate_file(row, removed)
                m.need(m.inside(path), "Unlink escaped explicit roots")
                # Unlink this exact name only. Never change attributes on an
                # inode also used by a protected runtime or RuntimeInputCache.
                m.low.unlink_without_attribute_changes(path)
                m.need(not path.exists(), "Exact target name was not removed")
                removed[pair(row)] += 1; removed_files += 1
                journal.write(json.dumps(dict(path=str(path), identity=row["identity"],
                                              sha256=row["sha256"], action="UNLINKED_EXACT_NAME")) + "\n")
                journal.flush()
            os.fsync(journal.fileno())
        for row in sorted(inventory["directories"], key=lambda value: len(Path(value["path"]).parts), reverse=True):
            path = m.checked(Path(row["path"])); now = m.ident(path.lstat())
            m.need(m.inside(path) and now["device"] == row["identity"]["device"] and
                   now["file_id"] == row["identity"]["file_id"], "Directory identity changed during apply")
            path.rmdir()  # Explicitly inventoried, empty directory; never recursive.
        after_hashes = {}
        for row in protection["files"]: validate_file(row, removed, after_hashes)
        verify_aliases(inventory["groups"], removed, after_hashes)
        processes_after = m.process_audit()
        m.need(all(not path.exists() for path in m.TARGETS), "Retired root remains")
        report = dict(status="PASS_EXPLICIT_SIX_ROOT_SUPERSEDED_MENU_PAIR_RETIREMENT", original_targets_status="RETIRED",
            evidence_claim="Compressed original diagnostics and full path/identity/mtime/SHA ledgers remain; six selected historical PNGs remain in diagnostics; other runtime, pixel and smoke-save files were retired.",
            removed_files=removed_files, retired_roots=[str(x) for x in m.TARGETS], plan_sha256=args.expected_plan_sha256,
            logical_bytes_removed=plan["logical_bytes"], estimated_file_storage_reclaimed=plan["estimated_reclaimable_file_storage_bytes"],
            free_bytes_before=free_before, free_bytes_after=shutil.disk_usage(m.ROOT).free,
            protected_files_verified=len(protection["files"]), protected_native_user_saves_verified=users["count"],
            surviving_aliases_verified=plan["surviving_alias_path_count"],
            protected_processes_after=processes_after, compressed_live_files=False, processes_stopped=False)
        m.write_new("retired.json", report)
        print(json.dumps(report, ensure_ascii=False), flush=True)
    except BaseException as error:
        m.write_new("application-failed.json", dict(status="PARTIAL_OR_FAILED_NO_REPLAY",
            removed_files=removed_files, error=repr(error), review_required=True))
        raise

if __name__ == "__main__":
    main()
