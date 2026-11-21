"""Draft an eight-run retirement preview; never delete or apply anything."""
from __future__ import annotations

from collections import defaultdict, deque
import argparse
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[3]
CONTRACT_FILE = ROOT / "tools/prune_superseded_runtime_artifacts.py"
BASELINE = ROOT / "evidence/storage_cleanup/20261007T193212Z_c1a07d6e4b39"
PROMOTION_DIR = ROOT / "evidence/runtime_promotion/20261007T203124Z"
TOP_PANEL_COMPONENT_VALIDATION = ROOT / "evidence/top_panel_scene_component/native_render_validation.json"
CANDIDATE_MANUAL_RUNS = ("20261006T133923Z_6730b22058d0", "20261007T200250Z_d0543d99dfc1")
OBSOLETE_HOST_RUNS = ("20261007T202902Z_b6199cc5c0d9", "20261007T203401Z_36875d10233c",
                      "20261007T204501Z_1f6258cecbf2")
FAILED_SMOKE_RUNS = ("20261007T203129Z_a4260011e240", "20261007T204232Z_1a982fc3a2b8",
                     "20261007T204636Z_c4b05b8132cf")
CANDIDATE_IDS = (*CANDIDATE_MANUAL_RUNS, *OBSOLETE_HOST_RUNS, *FAILED_SMOKE_RUNS)
APPROVED_TEST_SAVES = {
    "20261007T203129Z_a4260011e240": ("Build/InteractiveGameRuntime/20261007T203129Z_a4260011e240/sessions/dff081cb7f5bba520a857b758ea87f0c/autosave-0-turn-0.zssave", 9612910, "cfb918db35d29ca4416f683f552aa9479543cf28da2f48c443b0026e244d798e"),
    "20261007T204232Z_1a982fc3a2b8": ("Build/InteractiveGameRuntime/20261007T204232Z_1a982fc3a2b8/sessions/dfa1c642c540e4526eddd1c5629b995e/autosave-0-turn-0.zssave", 9612910, "25c6ca50555554209c9d1f512495824d9802a98bcef31e1f261f963aba0720f8"),
    "20261007T204636Z_c4b05b8132cf": ("Build/InteractiveGameRuntime/20261007T204636Z_c4b05b8132cf/sessions/8fdefadd230e05e1e5304814310ee7f0/autosave-0-turn-0.zssave", 9612910, "b9c105f3874209bdbb710c5a64f518c44db78d10d25902f34891e3e2db2d5e02"),
}
CURRENT_MANUAL = "20261007T202612Z_d895c0fe84ab"
KNOWN_HOST = "20261007T192802Z_20ff3a2b797c"
KNOWN_HOST_SHA = "7d75dbd22b7bc08ff57df6d2ff96b87e5f37698bbe68ca8aa563ace1ed8a4fca"
MOVE = "20261007T192923Z_503f1dbbd104"
RESTORE = "20261007T193254Z_1453ea25dd27"
SAVED_MANUALS = ("20261004T000710Z_796f1ea91c5e",
                 "20261003T230735Z_2003f24507ce",
                 "20261003T154510Z_b1af9e8eb764")
RUN_RE = re.compile(r"[0-9]{8}T[0-9]{6}Z_[0-9a-f]{12}")
TEXT = {".json", ".md", ".py", ".ps1", ".txt", ".h", ".cpp", ".xml", ".lua", ".cmd"}


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def load_contract():
    spec = importlib.util.spec_from_file_location("runtime_retirement_contract", CONTRACT_FILE)
    require(spec and spec.loader, "Cannot load the reviewed runtime cleanup contract")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    require(mod.ROOT == ROOT, "Cleanup contract resolved another project")
    return mod


def under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def candidate_root(path: Path, roots: list[Path]):
    return next((root for root in roots if under(path, root)), None)


def add_tree(mod, protected: set[Path], root: Path, targets: list[Path]):
    root = mod.boundary(root)
    require(root.is_dir(), "Missing protected tree: " + str(root))
    require(candidate_root(root, targets) is None, "Protected tree overlaps retirement: " + str(root))
    count = 0
    for path, _ in mod.inventory(root):
        require(candidate_root(path, targets) is None, "Protected file overlaps retirement: " + str(path))
        protected.add(path)
        count += 1
        if count % 5000 == 0:
            print(json.dumps({"phase": "protected_tree", "path": str(root.relative_to(ROOT)),
                              "files": count}), flush=True)
    print(json.dumps({"phase": "protected_tree_complete", "path": str(root.relative_to(ROOT)),
                      "files": count}), flush=True)


def add_closure(mod, seeds: list[Path], protected: set[Path], targets: list[Path]):
    pending, visited, documents = deque(seeds), set(), 0
    while pending:
        path = mod.boundary(Path(pending.popleft()))
        if path in visited:
            continue
        mod.regular(path)
        visited.add(path)
        protected.add(path)
        if path.suffix.lower() != ".json":
            continue
        doc = json.loads(path.read_text(encoding="utf-8-sig"))
        documents += 1
        for name, _ in mod.refs(doc):
            ref = Path(name)
            if not ref.is_absolute() or not under(ref, ROOT) or not ref.is_file():
                continue
            ref = mod.boundary(ref)
            require(candidate_root(ref, targets) is None,
                    "Current runtime dependency points into a retirement candidate: " + str(ref))
            protected.add(ref)
            if ref.suffix.lower() == ".json" and ref not in visited:
                pending.append(ref)
        if documents % 100 == 0:
            print(json.dumps({"phase": "dependency_closure", "documents": documents,
                              "queued": len(pending)}), flush=True)
    return documents


def reject_live_references(mod, roots: list[Path]):
    """Reject candidate run IDs in executable/source/test/tool trees."""
    ids = [*CANDIDATE_IDS]
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
            hits = [run for run in ids if run.encode("ascii") in data]
            require(not hits, "Current source/test/tool/doc names a retirement candidate: " + str(path))
            checked += 1
            if checked % 2000 == 0:
                print(json.dumps({"phase": "live_reference_check", "files": checked}), flush=True)
    return checked


def historical_doc_references(mod, docs_root: Path):
    """Record explicitly historical references; reject docs that state a current dependency."""
    ids = [*CANDIDATE_IDS]
    history_markers = ("당시", "과거", "이력", "역사", "퇴역", "무효", "대체된", "실패했던",
                       "historical", "retired", "superseded", "former", "previously", "at the time")
    current_markers = ("현재", "지금", "current", "currently", "latest", "now selected")
    rows, checked = [], 0
    for path, _ in mod.inventory(mod.boundary(docs_root)):
        if path.suffix.lower() not in TEXT or path.stat().st_size > 16 * 1024 * 1024:
            continue
        raw = path.read_bytes()
        try:
            text = raw.decode("utf-16" if b"\x00" in raw else "utf-8-sig")
        except UnicodeError:
            require(False, "Cannot classify a docs reference due to unknown encoding: " + str(path))
        hits = []
        for line_number, line in enumerate(text.splitlines(), 1):
            referenced = [run for run in ids if run in line]
            if not referenced:
                continue
            # Require the historical qualifier on the same documentation line;
            # a neighboring current-state sentence cannot launder a live reference.
            context = line.casefold()
            historical = any(marker.casefold() in context for marker in history_markers)
            current = any(marker.casefold() in context for marker in current_markers)
            require(historical and not current,
                    "Docs reference is not explicitly historical; update the live documentation before planning: " +
                    f"{path}:{line_number}")
            hits.append({"line": line_number, "run_ids": referenced})
        if hits:
            # add_tree() already retains and later hashes this entire documentation tree.
            rows.append({"path": str(path.relative_to(ROOT)), "sha256": mod.digest(path),
                         "bytes": path.stat().st_size, "references": hits,
                         "classification": "HISTORICAL_REFERENCE_ONLY_RAW_ARTIFACTS_RETIRED"})
        checked += 1
        if checked % 2000 == 0:
            print(json.dumps({"phase": "historical_doc_references", "files": checked,
                              "historical_files": len(rows)}), flush=True)
    return checked, rows


def artifact_summary(mod, directory: Path):
    directory = mod.legal_target(directory)
    count = total = 0
    for path, info in mod.inventory(directory):
        count += 1
        total += info.st_size
    return {"path": str(directory.relative_to(ROOT)), "files": count, "logical_bytes": total}


def create_plan(active_host_result: Path, active_smoke_run: str, active_restore_run: str):
    mod = load_contract()
    mod.no_active_host()
    output = mod.boundary(Path(__file__).resolve().parent)
    require(under(output, ROOT / "evidence/storage_cleanup"), "Output outside cleanup evidence")
    require(not (output / "plan.json").exists() and not (output / "cleanup.json").exists(),
            "This planner folder already has an output; do not replay it")
    require(RUN_RE.fullmatch(active_smoke_run) and RUN_RE.fullmatch(active_restore_run),
            "Active smoke/restore run ID is malformed")

    targets = []
    for run in CANDIDATE_MANUAL_RUNS:
        targets.extend((mod.legal_target(ROOT / "Build/InteractiveGameRuntime" / run),
                        mod.legal_target(ROOT / "evidence/interactive_game" / run)))
    for run in OBSOLETE_HOST_RUNS:
        targets.extend((mod.legal_target(ROOT / "Build/UiWindowHost" / run),
                        mod.legal_target(ROOT / "evidence/ui_window_host" / run)))
    for run in FAILED_SMOKE_RUNS:
        targets.extend((mod.legal_target(ROOT / "Build/InteractiveGameRuntime" / run),
                        mod.legal_target(ROOT / "evidence/interactive_game" / run)))
    require(len(targets) == 16 and len(set(targets)) == 16 and all(x.is_dir() for x in targets),
            "Retirement scope must be exactly the sixteen reviewed Build/evidence directories")
    candidate_saves = []
    for root in targets:
        for path, info in mod.inventory(root):
            if path.suffix.lower() == ".zssave":
                candidate_saves.append({"path": str(path.relative_to(ROOT)), "sha256": mod.digest(path),
                                        "bytes": info.st_size, "device": info.st_dev,
                                        "file_id": info.st_ino, "candidate_directory": str(root.relative_to(ROOT)),
                                        "run_id": root.name})
    expected_saves = {str(Path(row[0])): (run, row[1], row[2])
                      for run, row in APPROVED_TEST_SAVES.items()}
    observed_saves = {row["path"]: row for row in candidate_saves}
    require(set(observed_saves) == set(expected_saves),
            "Candidate .zssave set differs from the exact reviewed test-save allowlist: " +
            json.dumps(candidate_saves, ensure_ascii=False))
    for path, (run, expected_bytes, expected_sha) in expected_saves.items():
        row = observed_saves[path]
        require(row["run_id"] == run and row["bytes"] == expected_bytes and row["sha256"] == expected_sha,
                "Reviewed test-save identity/hash changed: " + path)
        req_path = ROOT / "evidence/interactive_game" / run / "request.json"
        result_path = ROOT / "evidence/interactive_game" / run / "result.json"
        request_doc = json.loads(req_path.read_text(encoding="utf-8-sig"))
        result_doc = json.loads(result_path.read_text(encoding="utf-8-sig"))
        require(request_doc.get("run_id") == run and request_doc.get("smoke") is True and
                result_doc.get("run_id") == run and result_doc.get("status") ==
                "CONTINUOUS_INTERACTIVE_SDK_TREE_DECISION_UI_SMOKE_FAILED" and
                result_doc.get("returncode") == 1,
                "Reviewed autosave is not attached to the expected failed test run: " + run)
        row["retirement_authorization"] = "EXACT_TEST_AUTOSAVE_REVIEWED_BY_ROOT"

    active_host_result = mod.boundary(active_host_result.resolve(strict=True))
    require(active_host_result.name == "build_result.json" and
            active_host_result.parent.parent.name == "ui_window_host",
            "Active Host build result must be under evidence/ui_window_host/<run>/build_result.json")
    active_host_id = active_host_result.parent.name
    require(RUN_RE.fullmatch(active_host_id) and active_host_id > KNOWN_HOST,
            "Active Host must be newer than the last retained Host")
    host_doc = json.loads(active_host_result.read_text(encoding="utf-8-sig"))
    host_exe = mod.boundary(Path(host_doc["executable"]["path"]))
    host_sha = host_doc["executable"]["sha256"]
    require(host_doc.get("status") == "UI_WINDOW_HOST_CANDIDATE_BUILT" and
            host_doc.get("source_inputs_unchanged") is True and mod.digest(host_exe) == host_sha,
            "Active Host build is incomplete or its executable changed")
    host_ids = [p.name for p in (ROOT / "Build/UiWindowHost").iterdir()
                if p.is_dir() and RUN_RE.fullmatch(p.name)]
    active_runtime_ids = [active_smoke_run, active_restore_run]
    active_records = {}
    for run_id in active_runtime_ids:
        active_runtime = ROOT / "Build/InteractiveGameRuntime" / run_id
        result_path = mod.boundary(ROOT / "evidence/interactive_game" / run_id / "result.json")
        request_path = mod.boundary(ROOT / "evidence/interactive_game" / run_id / "request.json")
        result = json.loads(result_path.read_text(encoding="utf-8-sig"))
        request = json.loads(request_path.read_text(encoding="utf-8-sig"))
        require(result.get("run_id") == run_id and str(result.get("status", "")).endswith("_PASS")
                and result.get("returncode") == 0 and result.get("timed_out") is False
                and result.get("failures") == [] and result.get("runtime_inputs_unchanged") is True,
                "Active smoke/restore is not a fully passing, unchanged-input result: " + run_id)
        require(request.get("run_id") == run_id and request.get("smoke") is True
                and Path(request["cwd"]).resolve(strict=True) == active_runtime.resolve(strict=True),
                "Active smoke/restore request does not match its sealed runtime: " + run_id)
        runtime_hosts = [row for row in request.get("runtime_inputs", [])
                         if Path(row.get("path", "")).name == "ZeroSisHost_x64.exe"]
        require(len(runtime_hosts) == 1 and runtime_hosts[0].get("sha256") == host_sha,
                "Active smoke/restore did not use the active Host build: " + run_id)
        active_records[run_id] = {"request_path": request_path, "result_path": result_path,
                                  "request": request, "result": result}
    runtime_ids = [p.name for p in (ROOT / "Build/InteractiveGameRuntime").iterdir()
                   if p.is_dir() and RUN_RE.fullmatch(p.name)]
    require(host_ids and max(host_ids) == active_host_id and runtime_ids and
            max(runtime_ids) == max(active_runtime_ids) and min(active_runtime_ids) > CURRENT_MANUAL,
            "A newer Host/runtime exists than the supplied active test; refresh protection inputs")

    start_engine = mod.boundary(ROOT / "tools/Start-Engine.ps1")
    launcher_text = start_engine.read_text(encoding="utf-8-sig")
    require(not any(run in launcher_text for run in CANDIDATE_IDS)
            and CURRENT_MANUAL in launcher_text,
            "Launcher still refers to a retirement candidate or no longer selects the current manual run")
    launcher_validation_path = mod.boundary(PROMOTION_DIR / "launcher_validation.json")
    promotion_path = mod.boundary(PROMOTION_DIR / "promotion.json")
    validation = json.loads(launcher_validation_path.read_text(encoding="utf-8-sig"))
    promotion = json.loads(promotion_path.read_text(encoding="utf-8-sig"))
    require(validation.get("status") == "PASS_MANUAL_NEW_CONTINUE_AND_ALL_SAVED_BUNDLES"
            and validation.get("count") == 10 and validation.get("user_saves") == 8
            and validation.get("plan_only") is True and validation.get("gameplay_launched") is False
            and all(row.get("smoke_inputs") is False and row.get("total_play_timeout_seconds") == 0
                    for row in validation.get("plans", []))
            and validation.get("saves_unchanged") is True and
            promotion.get("status") == "PASS_MANUAL_NEW_CONTINUE_AND_ALL_SAVED_BUNDLES"
            and promotion.get("run_id") == CURRENT_MANUAL and promotion.get("actual_game_launched") is False,
            "Current promotion or independent PS7 PlanOnly validation is incomplete")
    before, after = validation.get("saves_before", []), validation.get("saves_after", [])
    require(len(before) == len(after) == 8 and before == after,
            "The exact eight user-save hashes did not remain unchanged")
    manual_request_path = mod.boundary(ROOT / "evidence/interactive_game" / CURRENT_MANUAL / "request.json")
    manual_request = json.loads(manual_request_path.read_text(encoding="utf-8-sig"))
    manual_host = [row for row in manual_request.get("runtime_inputs", [])
                   if Path(row.get("path", "")).name == "ZeroSisHost_x64.exe"]
    require(manual_request.get("run_id") == CURRENT_MANUAL and manual_request.get("smoke") is False
            and manual_request.get("unit_assets", {}).get("status") == "PASS_ORIGINAL_UNIT_PACKAGE"
            and len(manual_host) == 1 and manual_host[0].get("sha256") == KNOWN_HOST_SHA,
            "Current manual runtime is missing its sealed Host or original unit assets")
    top_panel_component_validation_path = mod.boundary(TOP_PANEL_COMPONENT_VALIDATION)
    top_panel_component_validation = json.loads(
        top_panel_component_validation_path.read_text(encoding="utf-8-sig"))
    top_panel_snapshot = mod.boundary(Path(
        top_panel_component_validation["actual_hidden_sdk_snapshot"]["snapshot"]["path"]))
    require(top_panel_component_validation.get("status") ==
            "STOCK_TOP_PANEL_COMPONENT_SNAPSHOT_COMPILER_AND_NATIVE_RENDER_PASS" and
            top_panel_snapshot.parts[-5] == active_smoke_run and
            mod.digest(top_panel_snapshot) ==
            top_panel_component_validation["actual_hidden_sdk_snapshot"]["snapshot"]["sha256"],
            "TopPanel component validation is not the reviewed passing evidence from the active smoke run")
    top_panel_run_validations = []
    for run_id in active_runtime_ids:
        tp_path = mod.boundary(ROOT / "evidence/interactive_game" / run_id / "top_panel_validation.json")
        tp_doc = json.loads(tp_path.read_text(encoding="utf-8-sig"))
        revalidation_path = mod.boundary(
            ROOT / "evidence/interactive_game" / run_id / "top_panel_revalidation.json")
        revalidation_doc = json.loads(revalidation_path.read_text(encoding="utf-8-sig"))
        tp_sha = mod.digest(tp_path)
        result_path = active_records[run_id]["result_path"]
        result_sha = mod.digest(result_path)
        superseded = revalidation_doc.get("supersedes_report") or {}
        capture = revalidation_doc.get("capture_pipeline") or {}
        integrity = revalidation_doc.get("result_integrity") or {}
        pixel_comparison = revalidation_doc.get("pixel_comparison")
        superseded_path = mod.boundary(Path(superseded.get("path", "")))
        run_request = active_records[run_id]["request"]
        require(tp_doc.get("status") == "PASS_INTERACTIVE_TOP_PANEL_NATIVE_SDK_SMOKE" and
                (tp_doc.get("evidence") or {}).get("run_id") == run_id and
                ((tp_doc.get("evidence") or {}).get("host") or {}).get("host_executable_sha256") == host_sha and
                run_request.get("top_panel") is True,
                "TopPanel native SDK validation does not identify this run and active Host: " + run_id)
        require(revalidation_doc.get("status") == "CORRECTED_TOP_PANEL_CAPTURE_AND_PIXEL_ASSESSMENT" and
                revalidation_doc.get("run_id") == run_id and
                capture.get("host_build_id") == active_host_id and
                capture.get("host_executable_sha256") == host_sha and
                superseded_path == tp_path and
                superseded.get("sha256") == tp_sha and integrity.get("unchanged") is True and
                integrity.get("sha256_before") == result_sha and
                integrity.get("sha256_after") == result_sha and
                isinstance(pixel_comparison, dict),
                "TopPanel correction report does not supersede the raw report or bind to unchanged current evidence: " +
                run_id)
        top_panel_run_validations.append({"run_id": run_id, "path": tp_path,
            "document": tp_doc, "sha256": tp_sha, "revalidation_path": revalidation_path,
            "revalidation_document": revalidation_doc,
            "revalidation_sha256": mod.digest(revalidation_path),
            "result_path": result_path, "result_sha256": result_sha})
    restore_request = active_records[active_restore_run]["request"]
    restore_result = active_records[active_restore_run]["result"]
    resume_from = restore_request.get("resume_from") or {}
    require(resume_from.get("run_id") == active_smoke_run and
            restore_result.get("semantic_restore_equal") is True and
            restore_result.get("fresh_process_restore_verified") is True,
            "Active restore must resume the exact smoke source and pass semantic fresh-process equivalence")
    current_saves = []
    user_save_paths: set[Path] = set()
    for row in before:
        path = mod.boundary(Path(row["path"]))
        info = mod.regular(path)
        sha = mod.digest(path)
        require(sha == row["sha256"], "A retained user-save hash changed: " + str(path))
        user_save_paths.add(path)
        current_saves.append({"path": str(path), "sha256": sha, "bytes": info.st_size})

    # The prior list contributes paths only. Every retained byte is rehashed later.
    with gzip.open(mod.boundary(BASELINE / "protected.json.gz"), "rt", encoding="utf-8") as stream:
        prior = json.load(stream)
    protected: set[Path] = set()
    retained_manual_validator = mod.boundary(output / "validate_retained_manual.py")
    mod.regular(retained_manual_validator)
    require(candidate_root(retained_manual_validator, targets) is None,
            "Retained-manual validation script overlaps a retirement candidate")
    protected.add(retained_manual_validator)
    retired_prior = 0
    for index, name in enumerate(prior, 1):
        path = Path(name)
        require(path.is_absolute(), "Prior protected entry is not absolute: " + name)
        if candidate_root(path, targets):
            retired_prior += 1
        else:
            path = mod.boundary(path)
            mod.regular(path)
            protected.add(path)
        if index % 5000 == 0:
            print(json.dumps({"phase": "prior_paths", "processed": index, "total": len(prior)}), flush=True)

    protected_runs = [CURRENT_MANUAL, *SAVED_MANUALS, MOVE, RESTORE, *active_runtime_ids]
    protected_trees = [ROOT / name for name in ("Source", "Tests", "tools", "docs")]
    for run in protected_runs:
        protected_trees.extend((ROOT / "Build/InteractiveGameRuntime" / run,
                                ROOT / "evidence/interactive_game" / run))
    for run in (KNOWN_HOST, active_host_id):
        protected_trees.extend((ROOT / "Build/UiWindowHost" / run,
                                ROOT / "evidence/ui_window_host" / run))
    protected_trees.extend((PROMOTION_DIR, ROOT / "evidence/runtime_promotion/20261007T202716Z"))
    protected_trees.append(ROOT / "evidence/top_panel_scene_component")
    for index, tree in enumerate(protected_trees, 1):
        add_tree(mod, protected, tree, targets)
        if index % 4 == 0:
            print(json.dumps({"phase": "protected_trees", "tree": index,
                              "total": len(protected_trees), "paths": len(protected)}), flush=True)

    seeds = [active_host_result, launcher_validation_path, promotion_path,
             manual_request_path, top_panel_component_validation_path,
             ROOT / "evidence/interactive_game" / MOVE / "request.json",
             ROOT / "evidence/interactive_game" / MOVE / "result.json",
             ROOT / "evidence/interactive_game" / RESTORE / "request.json",
             ROOT / "evidence/interactive_game" / RESTORE / "result.json"]
    for record in active_records.values():
        seeds.extend((record["request_path"], record["result_path"]))
    for row in top_panel_run_validations:
        seeds.extend((row["path"], row["revalidation_path"]))
    seed_current = [mod.boundary(Path(seed)) for seed in seeds]
    documents = add_closure(mod, seed_current, protected, targets)
    for path in protected:
        require(candidate_root(path, targets) is None,
                "Protected path or current dependency overlaps retirement: " + str(path))
    checked = reject_live_references(mod, [ROOT / name for name in ("Source", "Tests", "tools")])
    docs_checked, historical_docs = historical_doc_references(mod, ROOT / "docs")

    cache, protected_hashes = {}, {}
    for index, path in enumerate(sorted(protected, key=lambda p: str(p).casefold()), 1):
        path = mod.boundary(path)
        info = mod.regular(path)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in cache:
            cache[identity] = mod.digest(path)
        require((path.stat().st_dev, path.stat().st_ino, path.stat().st_size,
                 path.stat().st_mtime_ns) == identity, "Protected file changed while hashing: " + str(path))
        protected_hashes[str(path)] = cache[identity]
        if index % 5000 == 0:
            print(json.dumps({"phase": "protected_hashes", "files": index,
                              "total": len(protected)}), flush=True)
    for row in historical_docs:
        protected_path = str(ROOT / row["path"])
        require(protected_hashes.get(protected_path) == row["sha256"],
                "Historical documentation changed between classification and protected hashing: " + protected_path)

    protected_file = output / "protected.json.gz"
    with gzip.open(protected_file, "wt", encoding="utf-8") as stream:
        json.dump(protected_hashes, stream, separators=(",", ":"))
    ledger_file = output / "retired-files.jsonl.gz"
    test_saves_file = output / "candidate-test-saves.jsonl.gz"
    with gzip.open(test_saves_file, "wt", encoding="utf-8") as test_save_ledger:
        for row in sorted(candidate_saves, key=lambda item: item["path"].casefold()):
            test_save_ledger.write(json.dumps(row, separators=(",", ":")) + "\n")
    summaries, total_files, logical = [], 0, 0
    inode_rows = defaultdict(lambda: {"links": 0, "paths": 0, "stored": 0})
    with gzip.open(ledger_file, "wt", encoding="utf-8") as ledger:
        for number, root in enumerate(targets, 1):
            count = size = 0
            for path, info in mod.inventory(root):
                identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                if identity not in cache:
                    cache[identity] = mod.digest(path)
                ledger.write(json.dumps({"path": str(path.relative_to(ROOT)), "sha256": cache[identity],
                    "bytes": info.st_size, "mtime_ns": info.st_mtime_ns,
                    "device": info.st_dev, "file_id": info.st_ino}, separators=(",", ":")) + "\n")
                inode = inode_rows[(info.st_dev, info.st_ino)]
                inode["links"], inode["paths"] = info.st_nlink, inode["paths"] + 1
                inode["stored"] = inode["stored"] or mod.stored(path)
                count, size = count + 1, size + info.st_size
                require((path.stat().st_dev, path.stat().st_ino, path.stat().st_size,
                         path.stat().st_mtime_ns) == identity, "Candidate changed during inventory: " + str(path))
                if count % 1000 == 0:
                    print(json.dumps({"phase": "candidate_files", "directory": number,
                                      "files": count, "logical_bytes": size}), flush=True)
            summaries.append({"path": str(root.relative_to(ROOT)), "files": count, "logical_bytes": size})
            total_files, logical = total_files + count, logical + size
            print(json.dumps({"phase": "candidate_directory", "directory": number, "total": len(targets),
                              "files": total_files, "logical_bytes": logical}), flush=True)
    mod.no_active_host()
    retired_runs = []
    for run in CANDIDATE_MANUAL_RUNS:
        req_path = ROOT / "evidence/interactive_game" / run / "request.json"
        req_doc = json.loads(req_path.read_text(encoding="utf-8-sig")) if req_path.is_file() else {}
        retired_runs.append({"run_id": run, "kind": "superseded_manual_runtime",
            "request_status": "PREPARED_NON_SMOKE" if req_doc.get("smoke") is False else "REQUEST_REVIEW_REQUIRED",
            "request_sha256": mod.digest(req_path) if req_path.is_file() else None,
            "unit_assets_status": (req_doc.get("unit_assets") or {}).get("status"),
            "retained_raw_artifacts": False})
    for run in OBSOLETE_HOST_RUNS:
        result_path = ROOT / "evidence/ui_window_host" / run / "build_result.json"
        result_doc = json.loads(result_path.read_text(encoding="utf-8-sig"))
        retired_runs.append({"run_id": run, "kind": "superseded_host_build",
            "result_status": result_doc.get("status"), "result_sha256": mod.digest(result_path),
            "executable_sha256": (result_doc.get("executable") or {}).get("sha256"),
            "source_inputs_unchanged": result_doc.get("source_inputs_unchanged"),
            "retained_raw_artifacts": False})
    for run in FAILED_SMOKE_RUNS:
        req_path = ROOT / "evidence/interactive_game" / run / "request.json"
        result_path = ROOT / "evidence/interactive_game" / run / "result.json"
        req_doc = json.loads(req_path.read_text(encoding="utf-8-sig"))
        result_doc = json.loads(result_path.read_text(encoding="utf-8-sig"))
        failures = result_doc.get("failures") or []
        first_failure = failures[0] if failures else None
        if isinstance(first_failure, dict):
            first_failure = first_failure.get("message") or first_failure.get("reason") or json.dumps(first_failure)
        retired_runs.append({"run_id": run, "kind": "failed_smoke_runtime",
            "request_sha256": mod.digest(req_path), "request_smoke": req_doc.get("smoke"),
            "result_status": result_doc.get("status"), "result_returncode": result_doc.get("returncode"),
            "result_sha256": mod.digest(result_path),
            "failure_reason_excerpt": str(first_failure)[:400] if first_failure is not None else None,
            "retained_raw_artifacts": False})
    plan = {"status": "PREVIEW_ONLY", "scope": "EXACT_EIGHT_RETIRED_RUNS_SIXTEEN_BUILD_AND_EVIDENCE_DIRECTORIES",
        "root": str(ROOT), "retirement_run_ids": list(CANDIDATE_IDS), "current_manual_runtime": CURRENT_MANUAL,
        "known_host": {"run_id": KNOWN_HOST, "sha256": KNOWN_HOST_SHA},
        "new_active_host": {"run_id": active_host_id, "sha256": host_sha, "result": str(active_host_result.relative_to(ROOT))},
        "active_smoke_run": active_smoke_run, "active_restore_run": active_restore_run,
        "top_panel_component_validation": {"path": str(top_panel_component_validation_path.relative_to(ROOT)),
            "sha256": mod.digest(top_panel_component_validation_path),
            "status": top_panel_component_validation["status"],
            "snapshot": str(top_panel_snapshot.relative_to(ROOT)),
            "snapshot_sha256": top_panel_component_validation["actual_hidden_sdk_snapshot"]["snapshot"]["sha256"],
            "live_game_or_host_compositing_verified": top_panel_component_validation.get("live_host_compositing_verified")},
        "top_panel_run_validations": [{"run_id": row["run_id"],
            "path": str(row["path"].relative_to(ROOT)), "sha256": row["sha256"],
            "status": row["document"]["status"],
            "host_executable_sha256": row["document"]["evidence"]["host"]["host_executable_sha256"],
            "revalidation_path": str(row["revalidation_path"].relative_to(ROOT)),
            "revalidation_sha256": row["revalidation_sha256"],
            "revalidation_status": row["revalidation_document"]["status"],
            "superseded_report_sha256": row["revalidation_document"]["supersedes_report"]["sha256"],
            "capture_host_build_id": row["revalidation_document"]["capture_pipeline"]["host_build_id"],
            "capture_host_executable_sha256": row["revalidation_document"]["capture_pipeline"]["host_executable_sha256"],
            "result_sha256": row["result_sha256"],
            "result_integrity_unchanged": row["revalidation_document"]["result_integrity"]["unchanged"]}
            for row in top_panel_run_validations],
        "restore_semantics": {"source_smoke_run": active_smoke_run,
            "semantic_restore_equal": restore_result.get("semantic_restore_equal"),
            "fresh_process_restore_verified": restore_result.get("fresh_process_restore_verified")},
        "protected_runtime_runs": protected_runs,
        "protected_host_runs": [KNOWN_HOST, active_host_id], "retired_run_summaries": retired_runs,
        "user_save_count": 8, "user_saves_current_hashes": current_saves,
        "candidate_test_saves": candidate_saves,
        "candidate_test_saves_ledger": {"path": str(test_saves_file.relative_to(ROOT)),
            "sha256": mod.digest(test_saves_file), "entries": len(candidate_saves)},
        "candidate_test_saves_user_save_overlap": sorted(
            str(path) for path in user_save_paths.intersection({ROOT / Path(name) for name in observed_saves})),
        "candidate_test_save_policy": "ONLY_THE_THREE_EXACT_ROOT_REVIEWED_FAILED_SMOKE_AUTOSAVES_ARE_INCLUDED; ALL_OTHER_ZSSAVE_FILES_BLOCK_PLAN",
        "previous_protected_path_count": len(prior), "prior_candidate_paths_retired": retired_prior,
        "current_dependency_files": len(protected_hashes), "current_json_documents": documents,
        "live_source_test_tool_files_checked": checked,
        "historical_document_files_checked": docs_checked,
        "historical_reference_retirement_list": historical_docs,
        "retained_manual_validation_script": {
            "path": str(retained_manual_validator.relative_to(ROOT)),
            "sha256": protected_hashes[str(retained_manual_validator)],
            "protected": True},
        "directories": summaries,
        "files": total_files, "logical_bytes": logical,
        "estimated_reclaimable_file_storage": sum(v["stored"] for v in inode_rows.values()
            if v["links"] == v["paths"]),
        "protected": {"path": str(protected_file), "sha256": mod.digest(protected_file)},
        "ledger": {"path": str(ledger_file), "sha256": mod.digest(ledger_file)},
        "prior_hashes_reused": False, "deletion_performed": False,
        "source_tests_tools_docs_game_mods_and_user_saves_deleted": False,
        "script_sha256": mod.digest(CONTRACT_FILE), "planner_sha256": mod.digest(Path(__file__))}
    plan_path = output / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"phase": "complete", "status": plan["status"], "plan": str(plan_path),
        "candidate_directories": len(targets), "candidate_runs": len(CANDIDATE_IDS),
        "files": total_files, "logical_bytes": logical}), flush=True)
    return plan_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-preview-plan", action="store_true",
                        help="Write a PREVIEW_ONLY plan; this never applies/deletes it")
    parser.add_argument("--active-host-result", type=Path,
                        help="Finished newer evidence/ui_window_host/<run>/build_result.json")
    parser.add_argument("--active-smoke-run",
                        help="Finished PASS runtime and evidence interactive smoke run ID using that Host")
    parser.add_argument("--active-restore-run",
                        help="Finished PASS restore runtime using that same Host")
    args = parser.parse_args()
    if not args.write_preview_plan:
        print(json.dumps({"status": "DRAFT_ONLY", "message": "No plan generated; use --write-preview-plan only after review and source/build freeze."}))
    else:
        require(args.active_host_result is not None and args.active_smoke_run and args.active_restore_run,
                "Plan creation requires the finished active Host result and matching smoke/restore run IDs")
        print(create_plan(args.active_host_result, args.active_smoke_run, args.active_restore_run))
