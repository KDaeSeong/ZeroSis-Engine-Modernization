"""Plan one explicitly named failed UI Host directory; this tool never deletes.

The existing pruner supplies only its path/file/hash helpers. Its historical
retention policy and apply entry point are deliberately not invoked.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import uuid

import prune_superseded_runtime_artifacts as safety

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "ZEROSIS_EXPLICIT_FAILED_UI_HOST_PLAN_V1"


def require(value, message):
    if not value:
        raise RuntimeError(message)


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def identity(info):
    return dict(device=str(info.st_dev), file_id=str(info.st_ino),
                bytes=info.st_size, mtime_ns=str(info.st_mtime_ns),
                links=info.st_nlink, attributes=info.st_file_attributes)


def checked_file(path):
    path = Path(os.path.abspath(path))
    require(path.resolve(strict=True) == path, "Resolved file path differs: " + str(path))
    for ancestor in [path, *path.parents]:
        require(not ancestor.lstat().st_file_attributes & 0x400,
                "Reparse file/ancestor: " + str(ancestor))
    info = safety.regular(path)
    require(info.st_ino != 0, "Missing stable file ID: " + str(path))
    return path, info


def build_path(build_id):
    require(bool(safety.RUN.fullmatch(build_id)), "Invalid explicit build ID")
    path = safety.boundary(ROOT / "Build/UiWindowHost" / build_id)
    require(path.parent == ROOT / "Build/UiWindowHost" and path.is_dir(),
            "Target is not an immediate UI Host build directory")
    return path


def failed_contract(build_id):
    target = build_path(build_id)
    path = safety.boundary(ROOT / "evidence/ui_window_host" / build_id / "build_result.json")
    value = read(path)
    require(value.get("build_id") == build_id and value.get("status") == "UI_WINDOW_HOST_BUILD_FAILED",
            "Target is not a recorded failed UI Host build")
    require(value.get("executable") is None and value.get("error"),
            "Failed report contains an executable or no diagnostic")
    return target, path, value


def target_inventory(target):
    files, directories = [], []
    for current, dirs, names in os.walk(target, followlinks=False):
        directory = safety.boundary(Path(current))
        info = directory.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_ino != 0, "Invalid target directory")
        directories.append(dict(path=str(directory), identity=identity(info)))
        for name in dirs:
            safety.boundary(directory / name)
        for name in names:
            path, info = checked_file(directory / name)
            require(path.is_relative_to(target), "Target file escaped explicit directory")
            require(info.st_nlink == 1, "Target file has another hardlink: " + str(path))
            require(not info.st_file_attributes & 1, "Read-only target requires separate review: " + str(path))
            require(path.suffix.lower() not in (".exe", ".dll", ".zssave"),
                    "Unexpected executable/library/save inside failed build: " + str(path))
            before = identity(info)
            digest = safety.digest(path)
            require(identity(checked_file(path)[1]) == before, "Target changed during hashing")
            files.append(dict(path=str(path), identity=before, sha256=digest))
    return dict(files=sorted(files, key=lambda r: r["path"]),
                directories=sorted(directories, key=lambda r: r["path"]))


def request_scan(build_id):
    """Only the small sealed request documents; never runtime/session files."""
    records = []
    for path in sorted((ROOT / "evidence/interactive_game").glob("*/request.json")):
        path, info = checked_file(path)
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8-sig"))
        require(build_id.casefold() not in json.dumps(value).casefold(),
                "A retained request mentions the failed build: " + str(path))
        require(identity(checked_file(path)[1]) == identity(info), "Request changed during scan")
        records.append(dict(path=str(path), identity=identity(info), sha256=hashlib.sha256(raw).hexdigest()))
    require(records, "No current runtime requests were available for reference checking")
    return records


def write_new(path, value, compressed=False):
    raw = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    with path.open("xb") as stream:
        stream.write(gzip.compress(raw, mtime=0) if compressed else raw)
    return dict(path=str(path), sha256=safety.digest(path), bytes=path.stat().st_size)


def make_plan(args):
    target, failure_path, failure = failed_contract(args.build_id)
    require(args.success_host != args.build_id, "Successful and failed Host IDs overlap")
    candidates = target_inventory(target)
    require(candidates["files"], "Empty failed build is not a file deletion plan")
    protected, hashes = {}, {}

    def protect(path, role, expected=None):
        path, info = checked_file(path)
        require(not path.is_relative_to(target), "Protected file intersects target: " + str(path))
        before = identity(info)
        key = tuple(before.values())
        digest = hashes.get(key)
        if digest is None:
            digest = hashes[key] = safety.digest(path)
        require(identity(checked_file(path)[1]) == before, "Protected file changed while hashing")
        require(expected is None or digest == expected.lower(), "Sealed input hash differs: " + str(path))
        record = protected.setdefault(str(path), dict(path=str(path), identity=before, sha256=digest, roles=[]))
        require(record["identity"] == before and record["sha256"] == digest, "Protected identity changed")
        if role not in record["roles"]:
            record["roles"].append(role)

    helper = Path(safety.__file__).resolve()
    protect(Path(__file__).resolve(), "planner")
    protect(helper, "safety_helpers")
    for path, _ in safety.inventory(failure_path.parent):
        protect(path, "retained_failed_build_diagnostic")
    success_root = build_path(args.success_host)
    success_report = ROOT / "evidence/ui_window_host" / args.success_host / "build_result.json"
    success = read(success_report)
    require(success.get("build_id") == args.success_host and
            success.get("status") == "UI_WINDOW_HOST_CANDIDATE_BUILT" and
            success.get("source_inputs_unchanged") is True, "Successful Host is not sealed")
    protect(success_report, "success_build_report")
    exe = success["executable"]
    require(Path(exe["path"]).is_relative_to(success_root), "Success EXE escaped its build")
    protect(exe["path"], "success_host_executable", exe["sha256"])
    for path, _ in safety.inventory(success_root / "frozen"):
        protect(path, "success_host_frozen_input")
    saves_path = safety.boundary(Path(args.save_baseline).absolute())
    saves = read(saves_path)["saves"]
    require(len(saves) == 8 and len({r["path"] for r in saves}) == 8, "Expected eight distinct retained user saves")
    protect(saves_path, "save_baseline")
    for row in saves:
        require(Path(row["path"]).stat().st_size == row["bytes"], "Retained save size differs")
        protect(row["path"], "existing_user_save", row["sha256"])
    roles = [(args.ea_run, "ea"), *[(run, "runtime") for run in args.protect_run]]
    require(len({run for run, _ in roles}) == len(roles), "Duplicate protected runtime ID")
    protected_roots = [str(failure_path.parent), str(success_root)]
    run_counts = {}
    for run, role in roles:
        require(bool(safety.RUN.fullmatch(run)), "Invalid protected runtime ID")
        evidence = safety.boundary(ROOT / "evidence/interactive_game" / run)
        runtime = safety.boundary(ROOT / "Build/InteractiveGameRuntime" / run)
        request_path = evidence / "request.json"
        request = read(request_path)
        require(request.get("run_id") == run, "Protected request identity mismatch")
        protect(request_path, role + "_request")
        inputs = request["runtime_inputs"]
        require(inputs and len({row["path"] for row in inputs}) == len(inputs), "Runtime input inventory is empty/duplicate")
        for row in inputs:
            require(Path(row["path"]).is_relative_to(runtime), "Runtime input escaped sealed runtime")
            protect(row["path"], role + "_sealed_input", row["sha256"])
        for field in ("interactive_ui_support", "interactive_ui_support_inventory", "provenance", "launcher_control_metadata"):
            for path, digest in safety.refs(request.get(field)):
                # refs ignores original_path annotations: only sealed path+hash artifacts.
                protect(path, role + "_sealed_support_or_launcher", digest)
        protected_roots.extend((str(evidence), str(runtime)))
        run_counts[run] = len(inputs)
    for run in args.protect_terminal_run:
        require(run in {r for r, _ in roles}, "Terminal evidence must belong to an explicitly protected run")
        evidence = ROOT / "evidence/interactive_game" / run
        result = read(evidence / "result.json")
        require(result.get("status") and "RUNNING" not in result["status"], "Terminal evidence is not complete")
        for path, _ in safety.inventory(evidence):
            protect(path, "terminal_run_evidence")
    for name in ("tools/Start-Engine.ps1", "Play/EarlyAccess/새 게임.cmd", "Play/EarlyAccess/이어하기.cmd", "Play/EarlyAccess/불러오기.cmd"):
        protect(ROOT / name, "public_ea_launcher")
    requests = request_scan(args.build_id)
    for row in requests:
        protect(row["path"], "current_runtime_request", row["sha256"])
    # No candidate can alias a protected file even if a hardlink appeared during collection.
    candidate_ids = {(r["identity"]["device"], r["identity"]["file_id"]) for r in candidates["files"]}
    require(not candidate_ids.intersection((r["identity"]["device"], r["identity"]["file_id"]) for r in protected.values()),
            "Candidate file identity overlaps a protected file")
    require(target_inventory(target) == candidates, "Target changed during protection collection")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    output = ROOT / "evidence/storage_cleanup/failed_ui_host_plans" / stamp
    output.mkdir(parents=True, exist_ok=False)
    target_ledger = write_new(output / "target-files.json.gz", candidates, True)
    protected_ledger = write_new(output / "protected-files.json.gz", sorted(protected.values(), key=lambda r: r["path"]), True)
    plan = dict(schema=SCHEMA, status="PREVIEW_ONLY_NO_DELETION", created_utc=datetime.now(timezone.utc).isoformat(),
                root=str(ROOT), build_id=args.build_id, target=str(target), success_host=args.success_host,
                scope="one_explicit_failed_UiWindowHost_directory_only", target_ledger=target_ledger,
                protected_ledger=protected_ledger, target_file_count=len(candidates["files"]),
                target_directory_count=len(candidates["directories"]),
                target_logical_bytes=sum(r["identity"]["bytes"] for r in candidates["files"]),
                target_all_single_link=True, target_no_reparse=True, target_no_executable_or_save=True,
                failed_report=dict(path=str(failure_path), sha256=safety.digest(failure_path),
                                   source_hash_count=len(failure["source_hashes_before"])),
                protected_file_count=len(protected), protected_roles=dict(Counter(role for r in protected.values() for role in r["roles"])),
                protected_roots=protected_roots, protected_runtime_inputs=run_counts,
                request_documents=requests, current_request_scan_count=len(requests),
                current_requests_reference_target=False, changing_session_files_hashed=False,
                apply_requirements=["Revalidate plan, helper and ledger SHA and every protected identity/content hash before and after deletion",
                                    "Refresh request reference check; if request set changed, prepare a fresh plan with new immutable runtime inputs",
                                    "Revalidate failed status/no executable and exact target directory/file inventory",
                                    "Immediately before each removal verify resolved target boundary, no reparse, single link, ID/size/mtime/SHA",
                                    "Remove only listed files and then empty listed directories; never recursively remove an unchecked computed path"],
                deletion_implemented=False, files_removed=0)
    record = write_new(output / "plan.json", plan)
    print(json.dumps(dict(status=plan["status"], plan=record, target_file_count=plan["target_file_count"],
                          target_logical_bytes=plan["target_logical_bytes"], protected_file_count=len(protected),
                          current_request_scan_count=len(requests)), ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--success-host", required=True)
    parser.add_argument("--ea-run", required=True)
    parser.add_argument("--protect-run", action="append", default=[])
    parser.add_argument("--protect-terminal-run", action="append", default=[])
    parser.add_argument("--save-baseline", required=True)
    make_plan(parser.parse_args())


if __name__ == "__main__":
    main()
