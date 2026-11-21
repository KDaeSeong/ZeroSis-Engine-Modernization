"""Preview only: retire the six specifically reviewed runtime folders."""
from __future__ import annotations

from collections import defaultdict
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_FILE = ROOT / "tools/prune_superseded_runtime_artifacts.py"
PREVIOUS = ROOT / "evidence/storage_cleanup/20261007T185251Z_9a72c5df1e41"
RUNS = {
    "20261007T135521Z_f2dab4d1d447": ("UiWindowHost", "ui_window_host"),
    "20261007T190226Z_a6a8966d1678": ("InteractiveGameRuntime", "interactive_game"),
    "20261007T192327Z_d21ce77f65bf": ("InteractiveGameRuntime", "interactive_game"),
}
HOST = "20261007T192802Z_20ff3a2b797c"
HOST_SHA = "7d75dbd22b7bc08ff57df6d2ff96b87e5f37698bbe68ca8aa563ace1ed8a4fca"
PROTECTED_HOSTS = ("20261007T190026Z_e8927b74abf4", HOST)
BASE_HOST = "20261006T132536Z_f8bcf55e3ffa"
BASE_RUNS = ("20261006T132933Z_c6976cdbae5b", "20261006T133311Z_b83e6f290c55")
COMBAT = "20261006T134330Z_9d66f439b55e"
MANUAL = ("20261006T133923Z_6730b22058d0", "20261004T000710Z_796f1ea91c5e",
          "20261003T230735Z_2003f24507ce", "20261003T154510Z_b1af9e8eb764")
REVALIDATED = "20261007T191737Z_cb79c4f6eb96"
ACTIVE_MOVE = "20261007T192923Z_503f1dbbd104"
RESTORE_RUN = "20261007T193254Z_1453ea25dd27"
HISTORY_REPORT = ROOT / "evidence/declare_war_scene_component/leader_response_renderer_validation.json"
RUN_RE = re.compile(r"\d{8}T\d{6}Z_[0-9a-f]{12}")
TEXT = {".json", ".md", ".py", ".ps1", ".txt", ".log", ".xml", ".lua", ".cmd"}
CANDIDATE_IDS = tuple(RUNS)


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def load_contract():
    spec = importlib.util.spec_from_file_location("runtime_retirement_contract", CONTRACT_FILE)
    require(spec and spec.loader, "Cannot load cleanup contract")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    require(mod.ROOT == ROOT, "Cleanup contract resolved another project")
    return mod


def under(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def candidate(path, targets):
    return next((root for root in targets if under(path, root)), None)


def add_tree(mod, protected, root):
    root = mod.boundary(root)
    require(root.is_dir(), "Missing protected tree: " + str(root))
    for n, (path, _) in enumerate(mod.inventory(root), 1):
        protected.add(path)
        if n % 5000 == 0:
            print(json.dumps({"phase": "protected_tree", "path": str(root), "files": n}), flush=True)


def close_dependencies(mod, seeds, protected, docs, targets):
    pending, visited, files = list(seeds), set(), set()
    while pending:
        path = mod.boundary(Path(pending.pop()))
        files.add(path)
        if path == HISTORY_REPORT or path in visited:
            continue
        mod.regular(path)
        visited.add(path)
        if path.suffix.lower() != ".json":
            continue
        docs.add(path)
        node = json.loads(path.read_text(encoding="utf-8-sig"))
        for name, _ in mod.refs(node):
            target = Path(name)
            if not target.is_absolute() or not under(target, ROOT) or not target.is_file():
                continue
            target = mod.boundary(target)
            if candidate(target, targets):
                raise RuntimeError("Current dependency closure intersects candidate: " + str(target))
            files.add(target)
            if target.suffix.lower() == ".json" and target not in visited and target != HISTORY_REPORT:
                pending.append(target)
        if len(docs) % 100 == 0:
            print(json.dumps({"phase": "dependency_closure", "json_documents": len(docs),
                              "queued": len(pending)}), flush=True)
    for path in files:
        path = mod.boundary(path)
        mod.regular(path)
        protected.add(path)
        require(candidate(path, targets) is None,
                "Current dependency closure intersects candidate: " + str(path))
    return files, visited


def reject_live_references(mod, paths, historical_report):
    for n, path in enumerate(paths, 1):
        if path == historical_report or path.suffix.lower() not in TEXT or path.stat().st_size > 16 * 1024 * 1024:
            continue
        mod.regular(path)
        data = path.read_bytes()
        if b"\x00" in data:
            try:
                data = data.decode("utf-16").encode("utf-8")
            except UnicodeError:
                data = b""
        hits = [run for run in CANDIDATE_IDS if run.encode("ascii") in data]
        require(not hits, "Current source/document/seed refers to candidate: "
                + str(path) + " -> " + ", ".join(hits))
        if n % 5000 == 0:
            print(json.dumps({"phase": "reference_check", "paths": n}), flush=True)


def report_status(mod, run, category):
    folder = mod.boundary(ROOT / "evidence" / category / run)
    names = ("build_result.json", "result.json", "failure_summary.json", "host_failure.json")
    reports = []
    for name in names:
        path = folder / name
        if not path.is_file():
            continue
        mod.regular(path)
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        failure = next((data.get(k) for k in
                        ("host_failure", "failure", "primary_failure", "error", "failures")
                        if data.get(k)), None)
        if isinstance(failure, list):
            failure = "; ".join(map(str, failure[:5]))
        reports.append({"path": str(path.relative_to(ROOT)), "status": data.get("status"),
                        "failure_summary": str(failure)[:800] if failure else None,
                        "sha256": mod.digest(path)})
    return {"run_id": run, "reports": reports}


def validate_protected_pass(mod, run, expected_status):
    path = mod.boundary(ROOT / "evidence/interactive_game" / run / "result.json")
    mod.regular(path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    require(data.get("run_id") == run and data.get("status") == expected_status
            and data.get("failures") == [], "Protected run did not retain its expected PASS result: " + run)
    return {"run_id": run, "path": str(path.relative_to(ROOT)), "status": data["status"],
            "sha256": mod.digest(path)}


def historical_snapshot(mod):
    path = mod.boundary(HISTORY_REPORT)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    raw = mod.boundary(Path(data["source_snapshot"]))
    retired = ROOT / "Build/InteractiveGameRuntime/20261007T190226Z_a6a8966d1678"
    before, after = data.get("source_snapshot_sha256_before"), data.get("source_snapshot_sha256_after")
    require(under(raw, retired) and before and before == after and mod.digest(raw) == before,
            "Historical 190226 snapshot does not match the retained renderer report")
    return {"status": "PLANNED_RETIREMENT_OF_HISTORICAL_DIAGNOSTIC_RAW",
            "report_path": str(path.relative_to(ROOT)), "report_sha256": mod.digest(path),
            "retired_raw_path": str(raw.relative_to(ROOT)), "retired_raw_sha256": before,
            "reason": "Post-run renderer diagnostic input only; no launcher or current runtime depends on it."}


def create_plan():
    mod = load_contract()
    mod.no_active_host()
    output = mod.boundary(Path(__file__).resolve().parent)
    require(under(output, ROOT / "evidence/storage_cleanup"), "Output outside cleanup evidence")
    require(not (output / "plan.json").exists() and not (output / "cleanup.json").exists(),
            "Output folder already contains a plan")

    targets = []
    for run, (group, category) in RUNS.items():
        require(RUN_RE.fullmatch(run), "Invalid fixed run ID")
        for path in (ROOT / "Build" / group / run, ROOT / "evidence" / category / run):
            path = mod.legal_target(path)
            require(path.is_dir(), "Missing fixed candidate: " + str(path))
            targets.append(path)
    require(len(targets) == 6 and len(set(targets)) == 6, "Candidate scope must stay six folders")

    hosts = [p.name for p in (ROOT / "Build/UiWindowHost").iterdir()
             if p.is_dir() and RUN_RE.fullmatch(p.name)]
    require(HOST in hosts and max(hosts) == HOST, "Latest Host changed; refresh constants")
    host_result = json.loads((ROOT / "evidence/ui_window_host" / HOST / "build_result.json")
                             .read_text(encoding="utf-8-sig"))
    host_exe = mod.boundary(Path(host_result["executable"]["path"]))
    require(host_result.get("status") == "UI_WINDOW_HOST_CANDIDATE_BUILT"
            and host_result["executable"]["sha256"] == HOST_SHA and mod.digest(host_exe) == HOST_SHA,
            "Latest Host executable differs from reviewed SHA")
    runtime_ids = [p.name for p in (ROOT / "Build/InteractiveGameRuntime").iterdir()
                   if p.is_dir() and RUN_RE.fullmatch(p.name)]
    require(max(runtime_ids) == RESTORE_RUN and (ROOT / "Build/InteractiveGameRuntime" / ACTIVE_MOVE).is_dir()
            and (ROOT / "Build/InteractiveGameRuntime" / RESTORE_RUN).is_dir(),
            "Latest restore or protected move run changed; refresh constants")

    # Carry forward only prior protected paths outside these six reviewed folders.
    with gzip.open(mod.boundary(PREVIOUS / "protected.json.gz"), "rt", encoding="utf-8") as stream:
        old_paths = json.load(stream)
    protected, retired_old = set(), defaultdict(int)
    for n, name in enumerate(old_paths, 1):
        path = Path(name)
        require(path.is_absolute(), "Prior protected path is not absolute: " + name)
        old_target = candidate(path, targets)
        if old_target:
            retired_old[str(old_target.relative_to(ROOT))] += 1
        else:
            path = mod.boundary(path)
            mod.regular(path)
            protected.add(path)
        if n % 5000 == 0:
            print(json.dumps({"phase": "prior_paths", "processed": n, "total": len(old_paths)}), flush=True)

    keep_runs = [(("UiWindowHost", "ui_window_host"), run)
                 for run in (*PROTECTED_HOSTS, BASE_HOST)]
    keep_runs += [(("InteractiveGameRuntime", "interactive_game"), run)
                  for run in (*BASE_RUNS, COMBAT, *MANUAL, REVALIDATED, ACTIVE_MOVE, RESTORE_RUN)]
    trees = [ROOT / name for name in ("Source", "Tests", "tools", "docs")]
    for ((build_group, evidence_group), run) in keep_runs:
        trees.extend((ROOT / "Build" / build_group / run, ROOT / "evidence" / evidence_group / run))
    for n, tree in enumerate(trees, 1):
        require(candidate(tree, targets) is None, "Protected tree overlaps candidate: " + str(tree))
        add_tree(mod, protected, tree)
        print(json.dumps({"phase": "protected_trees", "tree": n, "total": len(trees),
                          "protected_paths": len(protected)}), flush=True)
    launcher = mod.boundary(ROOT / "tools/Start-Engine.ps1")
    protected.add(launcher)

    prior = json.loads((PREVIOUS / "plan.json").read_text(encoding="utf-8"))
    old_seeds = [Path(p) for p in prior.get("baseline_dependency_seeds", prior.get("seed_documents", []))]
    seeds = [p for p in old_seeds if candidate(p, targets) is None and p != HISTORY_REPORT]
    skipped_seeds = [str(p) for p in old_seeds if candidate(p, targets) is not None or p == HISTORY_REPORT]
    seeds += [ROOT / "evidence/ui_window_host" / run / "build_result.json"
              for run in (*PROTECTED_HOSTS, BASE_HOST)]
    seeds += [ROOT / "evidence/interactive_game" / REVALIDATED / n
              for n in ("request.json", "result.json", "declare_war_revalidation.json")]
    for run in (ACTIVE_MOVE, RESTORE_RUN):
        seeds += [ROOT / "evidence/interactive_game" / run / n
                  for n in ("request.json", "result.json")]
    for run in (*BASE_RUNS, COMBAT, *MANUAL):
        folder = ROOT / "evidence/interactive_game" / run
        seeds += [folder / n for n in ("request.json", "result.json") if (folder / n).is_file()]
    seeds = [mod.boundary(p) for p in seeds]
    docs = set()
    closure_files, closure_docs = close_dependencies(mod, seeds, protected, docs, targets)
    for path in protected:
        require(candidate(path, targets) is None, "Protected/dependency path intersects candidate: " + str(path))
    print(json.dumps({"phase": "dependency_closure", "seeds": len(seeds),
                      "documents": len(docs), "protected_paths": len(protected)}), flush=True)

    validation = json.loads((PREVIOUS / "post_cleanup_validation.json").read_text(encoding="utf-8"))
    save_records = [row for row in validation.get("saves", [])
                    if any("\\" + run + "\\" in row["path"] for run in MANUAL)]
    require(validation.get("user_saves") == 8 and len(save_records) == 8,
            "Prior validation no longer lists the exact eight manual saves")
    for row in save_records:
        path = mod.boundary(Path(row["path"]))
        require(any(under(path, ROOT / "Build/InteractiveGameRuntime" / run) for run in MANUAL),
                "User save is outside the preserved manual runs")
        mod.regular(path)
        require(mod.digest(path) == row["sha256"], "Manual save changed since completed validation: " + str(path))
        protected.add(path)

    revalidation_path = mod.boundary(ROOT / "evidence/interactive_game" / REVALIDATED / "declare_war_revalidation.json")
    original_result = mod.boundary(ROOT / "evidence/interactive_game" / REVALIDATED / "result.json")
    revalidation = json.loads(revalidation_path.read_text(encoding="utf-8-sig"))
    original_sha = mod.digest(original_result)
    original_data = json.loads(original_result.read_text(encoding="utf-8-sig"))
    require(revalidation.get("status") == "DECLARE_WAR_RANGE_INDEPENDENT_REVALIDATION_PASS"
            and revalidation.get("original_failure_preserved") is True
            and original_data.get("status") == "CONTINUOUS_INTERACTIVE_SDK_DECLARE_WAR_RANGE_SMOKE_FAILED"
            and revalidation.get("original_result_sha256_before") == original_sha
            and revalidation.get("original_result_sha256_after") == original_sha,
            "191737 independent proof or original failed result changed")
    history = historical_snapshot(mod)
    history_report = mod.boundary(HISTORY_REPORT)
    protected.add(history_report)
    current_passes = [validate_protected_pass(
        mod, ACTIVE_MOVE, "CONTINUOUS_INTERACTIVE_SDK_DECLARE_WAR_MOVE_SMOKE_PASS"),
        validate_protected_pass(
            mod, RESTORE_RUN, "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS")]

    scan = set(seeds) | closure_docs | {launcher}
    for tree in trees[:4]:
        scan.update(path for path, _ in mod.inventory(tree))
    reject_live_references(mod, scan, history_report)
    print(json.dumps({"phase": "references", "scanned": len(scan),
                      "historical_snapshot_exception": history["retired_raw_path"]}), flush=True)

    statuses = [report_status(mod, run, category) for run, (_, category) in RUNS.items()]
    status_file = output / "status-summary.json"
    status_file.write_text(json.dumps({"status": "READ_ONLY_CANDIDATE_STATUS", "runs": statuses},
                                      ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    history_file = output / "retired-historical-reference.json"
    history_file.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    cache, protected_hashes = {}, {}
    for n, path in enumerate(sorted(protected, key=lambda p: str(p).casefold()), 1):
        path = mod.boundary(path)
        info = mod.regular(path)
        ident = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if ident not in cache:
            cache[ident] = mod.digest(path)
        require((path.stat().st_dev, path.stat().st_ino, path.stat().st_size,
                 path.stat().st_mtime_ns) == ident, "Protected file changed during hashing: " + str(path))
        protected_hashes[str(path)] = cache[ident]
        if n % 5000 == 0:
            print(json.dumps({"phase": "protected_hashes", "files": n, "total": len(protected)}), flush=True)
    protected_file = output / "protected.json.gz"
    with gzip.open(protected_file, "wt", encoding="utf-8") as stream:
        json.dump(protected_hashes, stream, separators=(",", ":"))

    ledger_file = output / "retired-files.jsonl.gz"
    directories, total_files, logical = [], 0, 0
    inodes = defaultdict(lambda: {"links": 0, "paths": 0, "stored": 0})
    with gzip.open(ledger_file, "wt", encoding="utf-8") as ledger:
        for n, root in enumerate(targets, 1):
            count = size = 0
            for path, info in mod.inventory(root):
                ident = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                if ident not in cache:
                    cache[ident] = mod.digest(path)
                ledger.write(json.dumps({"path": str(path.relative_to(ROOT)), "sha256": cache[ident],
                                         "bytes": info.st_size, "mtime_ns": info.st_mtime_ns,
                                         "device": info.st_dev, "file_id": info.st_ino},
                                        separators=(",", ":")) + "\n")
                inode = inodes[(info.st_dev, info.st_ino)]
                inode["links"], inode["paths"] = info.st_nlink, inode["paths"] + 1
                inode["stored"] = inode["stored"] or mod.stored(path)
                count, size = count + 1, size + info.st_size
                require((path.stat().st_dev, path.stat().st_ino, path.stat().st_size,
                         path.stat().st_mtime_ns) == ident, "Candidate changed during inventory: " + str(path))
                if count % 1000 == 0:
                    print(json.dumps({"phase": "candidate_files", "directory": n, "files": count,
                                      "logical_bytes": size}), flush=True)
            directories.append({"path": str(root.relative_to(ROOT)), "files": count, "logical_bytes": size})
            total_files, logical = total_files + count, logical + size
            print(json.dumps({"phase": "candidate_directory", "directory": n, "total": 6,
                              "files": total_files, "logical_bytes": logical}), flush=True)
    mod.no_active_host()

    plan = {
        "status": "PREVIEW_ONLY", "scope": "EXACT_SIX_REVIEWED_SUPERSEDED_OR_FAILED_RUN_DIRECTORIES",
        "root": str(ROOT), "latest_host": HOST, "latest_host_executable_sha256": HOST_SHA,
        "protected_hosts": list(PROTECTED_HOSTS), "protected_runtime_runs":
            [*BASE_RUNS, COMBAT, *MANUAL, REVALIDATED, ACTIVE_MOVE, RESTORE_RUN],
        "protected_current_passes": current_passes,
        "directories": directories, "retired_runs": statuses, "files": total_files,
        "logical_bytes": logical,
        "estimated_reclaimable_file_storage": sum(x["stored"] for x in inodes.values()
                                                   if x["links"] == x["paths"]),
        "previous_protected_path_count": len(old_paths),
        "previous_candidate_paths_retired": dict(retired_old),
        "prior_candidate_seeds_retired": skipped_seeds,
        "current_dependency_files": len(protected_hashes), "current_json_documents": len(docs),
        "manual_user_save_count": len(save_records),
        "protected_revalidation": {"path": str(revalidation_path), "status": revalidation["status"],
                                   "sha256": mod.digest(revalidation_path),
                                   "original_result_status": original_data["status"],
                                   "original_result_sha256": original_sha},
        "historical_snapshot_retired": {"path": str(history_file), "sha256": mod.digest(history_file)},
        "status_summary": {"path": str(status_file), "sha256": mod.digest(status_file)},
        "protected": {"path": str(protected_file), "sha256": mod.digest(protected_file)},
        "ledger": {"path": str(ledger_file), "sha256": mod.digest(ledger_file)},
        "previous_protected_hashes_reused": False, "deletion_performed": False,
        "script_sha256": mod.digest(CONTRACT_FILE), "planner_sha256": mod.digest(Path(__file__)),
    }
    plan_file = output / "plan.json"
    plan_file.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"phase": "complete", "status": plan["status"], "plan": str(plan_file),
                      "candidate_directories": 6, "files": total_files, "logical_bytes": logical,
                      "estimated_reclaimable_file_storage": plan["estimated_reclaimable_file_storage"]}),
          flush=True)
    return plan_file


if __name__ == "__main__":
    print(create_plan())

