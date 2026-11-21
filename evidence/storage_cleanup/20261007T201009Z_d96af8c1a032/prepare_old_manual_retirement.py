"""Prepare, but never apply, retirement of the one superseded zero-save runtime."""
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
BASELINE = ROOT / "evidence/storage_cleanup/20261007T193212Z_c1a07d6e4b39"
PROMOTION = ROOT / "evidence/runtime_promotion/20261007T200917Z"
OLD_MANUAL = "20261006T133923Z_6730b22058d0"
NEW_MANUAL = "20261007T200250Z_d0543d99dfc1"
HOST = "20261007T192802Z_20ff3a2b797c"
HOST_SHA = "7d75dbd22b7bc08ff57df6d2ff96b87e5f37698bbe68ca8aa563ace1ed8a4fca"
MOVE = "20261007T192923Z_503f1dbbd104"
RESTORE = "20261007T193254Z_1453ea25dd27"
SAVED_MANUALS = ("20261004T000710Z_796f1ea91c5e",
                 "20261003T230735Z_2003f24507ce",
                 "20261003T154510Z_b1af9e8eb764")
RUN_RE = re.compile(r"\d{8}T\d{6}Z_[0-9a-f]{12}")
TEXT = {".json", ".md", ".py", ".ps1", ".txt", ".h", ".cpp", ".xml", ".lua", ".cmd"}


def require(value, message):
    if not value:
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


def add_tree(mod, protected, root, targets):
    root = mod.boundary(root)
    require(root.is_dir(), "Missing protected tree: " + str(root))
    require(candidate(root, targets) is None, "Protected tree overlaps candidate: " + str(root))
    count = 0
    for path, _ in mod.inventory(root):
        protected.add(path)
        count += 1
        if count % 5000 == 0:
            print(json.dumps({"phase": "protected_tree", "path": str(root.relative_to(ROOT)),
                              "files": count}), flush=True)
    print(json.dumps({"phase": "protected_tree_complete", "path": str(root.relative_to(ROOT)),
                      "files": count}), flush=True)


def add_dependency_closure(mod, seeds, protected, targets):
    pending, visited, documents = list(seeds), set(), 0
    while pending:
        path = mod.boundary(Path(pending.pop()))
        if path in visited:
            continue
        mod.regular(path)
        visited.add(path)
        protected.add(path)
        if path.suffix.lower() != ".json":
            continue
        node = json.loads(path.read_text(encoding="utf-8-sig"))
        documents += 1
        for name, _ in mod.refs(node):
            target = Path(name)
            if not target.is_absolute() or not under(target, ROOT) or not target.is_file():
                continue
            target = mod.boundary(target)
            require(candidate(target, targets) is None,
                    "Current dependency closure intersects retirement: " + str(target))
            protected.add(target)
            if target.suffix.lower() == ".json" and target not in visited:
                pending.append(target)
        if documents % 100 == 0:
            print(json.dumps({"phase": "dependency_closure", "json_documents": documents,
                              "queued": len(pending)}), flush=True)
    return documents


def reject_live_references(mod, roots, targets):
    candidate_ids = [OLD_MANUAL]
    checked = 0
    for root in roots:
        for path, _ in mod.inventory(mod.boundary(root)):
            if path.suffix.lower() not in TEXT or path.stat().st_size > 16 * 1024 * 1024:
                continue
            data = path.read_bytes()
            if b"\x00" in data:
                try:
                    data = data.decode("utf-16").encode("utf-8")
                except UnicodeError:
                    data = b""
            hits = [item for item in candidate_ids if item.encode("ascii") in data]
            require(not hits, "Live code/test/tool references retiring runtime: " + str(path))
            checked += 1
            if checked % 2000 == 0:
                print(json.dumps({"phase": "live_reference_check", "files": checked}), flush=True)
    return checked


def result_record(mod, run, expected_status):
    path = mod.boundary(ROOT / "evidence/interactive_game" / run / "result.json")
    mod.regular(path)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    require(data.get("run_id") == run and data.get("status") == expected_status
            and data.get("returncode") == 0 and data.get("timed_out") is False
            and data.get("failures") == [], "Protected PASS result changed: " + run)
    return {"run_id": run, "status": expected_status,
            "path": str(path.relative_to(ROOT)), "sha256": mod.digest(path)}


def create_plan():
    mod = load_contract()
    mod.no_active_host()
    output = mod.boundary(Path(__file__).resolve().parent)
    require(under(output, ROOT / "evidence/storage_cleanup"), "Output outside cleanup evidence")
    require(not (output / "plan.json").exists() and not (output / "cleanup.json").exists(),
            "Output folder already has a plan")

    targets = [mod.legal_target(ROOT / "Build/InteractiveGameRuntime" / OLD_MANUAL),
               mod.legal_target(ROOT / "evidence/interactive_game" / OLD_MANUAL)]
    require(len(targets) == 2 and len(set(targets)) == 2, "Retirement scope must be exactly two folders")
    require(all(path.is_dir() for path in targets), "A fixed retirement directory is missing")
    require(not any(path.suffix.lower() == ".zssave" for root in targets
                    for path, _ in mod.inventory(root)), "Old manual runtime now contains a save; refresh scope")

    host_ids = [p.name for p in (ROOT / "Build/UiWindowHost").iterdir()
                if p.is_dir() and RUN_RE.fullmatch(p.name)]
    runtime_ids = [p.name for p in (ROOT / "Build/InteractiveGameRuntime").iterdir()
                   if p.is_dir() and RUN_RE.fullmatch(p.name)]
    require(max(host_ids) == HOST and max(runtime_ids) == NEW_MANUAL,
            "A newer Host or runtime exists; refresh retention constants")
    start_engine = mod.boundary(ROOT / "tools/Start-Engine.ps1")
    launcher_text = start_engine.read_text(encoding="utf-8-sig")
    require(OLD_MANUAL not in launcher_text and NEW_MANUAL in launcher_text,
            "Start-Engine still references the retiring manual runtime")

    host_result_path = mod.boundary(ROOT / "evidence/ui_window_host" / HOST / "build_result.json")
    host_result = json.loads(host_result_path.read_text(encoding="utf-8-sig"))
    host_exe = mod.boundary(Path(host_result["executable"]["path"]))
    require(host_result.get("status") == "UI_WINDOW_HOST_CANDIDATE_BUILT"
            and host_result.get("source_inputs_unchanged") is True
            and host_result["executable"].get("sha256") == HOST_SHA
            and mod.digest(host_exe) == HOST_SHA, "Current Host differs from the reviewed SHA")

    promotion_path = mod.boundary(PROMOTION / "promotion.json")
    validation_path = mod.boundary(PROMOTION / "launcher_validation.json")
    promotion = json.loads(promotion_path.read_text(encoding="utf-8-sig"))
    validation = json.loads(validation_path.read_text(encoding="utf-8-sig"))
    require(promotion.get("status") == "VALIDATED_MANUAL_CANDIDATE_SELECTED"
            and promotion.get("manual_runtime") == NEW_MANUAL
            and validation.get("status") == "PASS_MANUAL_NEW_CONTINUE_AND_ALL_SAVED_BUNDLES"
            and validation.get("count") == 10 and validation.get("user_saves") == 8
            and validation.get("gameplay_launched") is False,
            "Current promotion or PlanOnly evidence is incomplete")
    require(validation.get("saves_unchanged") is True and len(validation.get("saves_before", [])) == 8
            and validation.get("saves_before") == validation.get("saves_after"),
            "The eight retained user save hashes changed")
    for proof in promotion.get("proofs", []):
        proof_path = mod.boundary(Path(proof["path"]))
        require(mod.digest(proof_path) == proof.get("sha256"), "Promotion proof hash changed")
    passes = [result_record(mod, MOVE, "CONTINUOUS_INTERACTIVE_SDK_DECLARE_WAR_MOVE_SMOKE_PASS"),
              result_record(mod, RESTORE, "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_RESTORE_SMOKE_PASS")]

    # Carry forward prior protected paths, but retire exactly these two paths.
    with gzip.open(mod.boundary(BASELINE / "protected.json.gz"), "rt", encoding="utf-8") as stream:
        prior = json.load(stream)
    protected, retired_prior = set(), 0
    for index, name in enumerate(prior, 1):
        path = Path(name)
        require(path.is_absolute(), "Prior protected path is not absolute: " + name)
        if candidate(path, targets):
            retired_prior += 1
        else:
            path = mod.boundary(path)
            mod.regular(path)
            protected.add(path)
        if index % 5000 == 0:
            print(json.dumps({"phase": "prior_protected_paths", "processed": index,
                              "total": len(prior)}), flush=True)

    trees = [ROOT / name for name in ("Source", "Tests", "tools", "docs")]
    protected_runs = [NEW_MANUAL, *SAVED_MANUALS, MOVE, RESTORE]
    for run in protected_runs:
        trees.extend((ROOT / "Build/InteractiveGameRuntime" / run,
                      ROOT / "evidence/interactive_game" / run))
    trees.extend((ROOT / "Build/UiWindowHost" / HOST,
                  ROOT / "evidence/ui_window_host" / HOST,
                  PROMOTION))
    for index, tree in enumerate(trees, 1):
        add_tree(mod, protected, tree, targets)
        print(json.dumps({"phase": "protected_trees", "tree": index, "total": len(trees),
                          "protected_paths": len(protected)}), flush=True)

    saves = [Path(row["path"]) for row in validation["saves_before"]]
    require(len(saves) == 8 and len(set(saves)) == 8, "Expected the exact eight validated saves")
    current_saves = []
    for path in saves:
        path = mod.boundary(path)
        mod.regular(path)
        current_saves.append({"path": str(path), "sha256": mod.digest(path)})
        protected.add(path)

    manual_request = mod.boundary(ROOT / "evidence/interactive_game" / NEW_MANUAL / "request.json")
    request = json.loads(manual_request.read_text(encoding="utf-8-sig"))
    require(request.get("run_id") == NEW_MANUAL and request.get("smoke") is False,
            "Prepared runtime request is not manual mode")
    play = mod.boundary(ROOT / "Build/InteractiveGameRuntime" / NEW_MANUAL / "Play.ps1")
    require("--mode play" in play.read_text(encoding="utf-8-sig")
            and "--timeout 0" in play.read_text(encoding="utf-8-sig"),
            "Prepared Play launcher is not unbounded manual play")

    seeds = [host_result_path, promotion_path, validation_path, manual_request,
             ROOT / "evidence/interactive_game" / MOVE / "request.json",
             ROOT / "evidence/interactive_game" / MOVE / "result.json",
             ROOT / "evidence/interactive_game" / RESTORE / "request.json",
             ROOT / "evidence/interactive_game" / RESTORE / "result.json"]
    seeds = [mod.boundary(path) for path in seeds]
    documents = add_dependency_closure(mod, seeds, protected, targets)
    for path in protected:
        require(candidate(path, targets) is None,
                "Protected path or current dependency overlaps retirement: " + str(path))

    scan_roots = [ROOT / name for name in ("Source", "Tests", "tools")]
    checked = reject_live_references(mod, scan_roots, targets)

    cache, protected_hashes = {}, {}
    for index, path in enumerate(sorted(protected, key=lambda p: str(p).casefold()), 1):
        path = mod.boundary(path)
        info = mod.regular(path)
        ident = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if ident not in cache:
            cache[ident] = mod.digest(path)
        require((path.stat().st_dev, path.stat().st_ino, path.stat().st_size,
                 path.stat().st_mtime_ns) == ident, "Protected file changed while hashing: " + str(path))
        protected_hashes[str(path)] = cache[ident]
        if index % 5000 == 0:
            print(json.dumps({"phase": "protected_hashes", "files": index,
                              "total": len(protected)}), flush=True)

    protected_file = output / "protected.json.gz"
    with gzip.open(protected_file, "wt", encoding="utf-8") as stream:
        json.dump(protected_hashes, stream, separators=(",", ":"))

    ledger_file = output / "retired-files.jsonl.gz"
    summaries, total_files, logical = [], 0, 0
    inodes = defaultdict(lambda: {"links": 0, "paths": 0, "stored": 0})
    with gzip.open(ledger_file, "wt", encoding="utf-8") as ledger:
        for number, root in enumerate(targets, 1):
            count, size = 0, 0
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
                    print(json.dumps({"phase": "candidate_files", "directory": number,
                                      "files": count, "logical_bytes": size}), flush=True)
            summaries.append({"path": str(root.relative_to(ROOT)), "files": count,
                              "logical_bytes": size})
            total_files, logical = total_files + count, logical + size
            print(json.dumps({"phase": "candidate_directory", "directory": number, "total": 2,
                              "files": total_files, "logical_bytes": logical}), flush=True)
    mod.no_active_host()

    plan = {
        "status": "PREVIEW_ONLY",
        "scope": "EXACT_OLD_ZERO_SAVE_MANUAL_RUNTIME_BUILD_AND_EVIDENCE_DIRECTORIES",
        "root": str(ROOT), "retired_manual_runtime": OLD_MANUAL,
        "current_manual_runtime": NEW_MANUAL, "latest_host": HOST,
        "latest_host_executable_sha256": HOST_SHA, "protected_runtime_runs": protected_runs,
        "protected_passes": passes, "manual_user_save_count": len(current_saves),
        "manual_user_saves_current_hashes": current_saves,
        "previous_protected_path_count": len(prior), "prior_candidate_paths_retired": retired_prior,
        "current_dependency_files": len(protected_hashes), "current_json_documents": documents,
        "live_source_tool_test_files_checked": checked,
        "promotion_record": {"path": str(promotion_path.relative_to(ROOT)),
                             "sha256": mod.digest(promotion_path)},
        "launcher_validation": {"path": str(validation_path.relative_to(ROOT)),
                                "sha256": mod.digest(validation_path)},
        "directories": summaries, "files": total_files, "logical_bytes": logical,
        "estimated_reclaimable_file_storage": sum(v["stored"] for v in inodes.values()
                                                   if v["links"] == v["paths"]),
        "protected": {"path": str(protected_file), "sha256": mod.digest(protected_file)},
        "ledger": {"path": str(ledger_file), "sha256": mod.digest(ledger_file)},
        "previous_protected_hashes_reused": False, "deletion_performed": False,
        "source_tools_tests_game_mods_user_saves_deleted": False,
        "script_sha256": mod.digest(CONTRACT_FILE), "planner_sha256": mod.digest(Path(__file__)),
    }
    destination = output / "plan.json"
    destination.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"phase": "complete", "status": plan["status"],
                      "plan": str(destination), "candidate_directories": 2,
                      "files": total_files, "logical_bytes": logical}, ensure_ascii=False), flush=True)
    return destination


if __name__ == "__main__":
    print(create_plan())
