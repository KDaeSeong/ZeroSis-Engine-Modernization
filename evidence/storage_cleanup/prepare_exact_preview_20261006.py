"""Create a fresh, fixed-path cleanup preview; this script never deletes files."""
from __future__ import annotations

from datetime import datetime, timezone
import gzip
import importlib.util
import json
import os
from pathlib import Path
import uuid

ROOT = Path(__file__).resolve().parents[2]
PRUNER_PATH = ROOT / "tools/prune_superseded_runtime_artifacts.py"
SPEC = importlib.util.spec_from_file_location("runtime_pruner", PRUNER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("Could not load the approved retirement ledger helpers")
PRUNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PRUNER)

HOST = "20261006T132536Z_f8bcf55e3ffa"
BITMAP_PASS = "20261006T132646Z_43520a264230"
FRESH = "20261006T132933Z_c6976cdbae5b"
RESTORE = "20261006T133311Z_b83e6f290c55"
COMBAT_FAILED = "20261006T133653Z_55bff44be6f4"
COMBAT_PASS = "20261006T134330Z_9d66f439b55e"
MANUAL_DEFAULT = "20261006T133923Z_6730b22058d0"
PREVIOUS_MANUAL_DEFAULT = "20261005T125723Z_ac109f515719"
DISPATCH = "20261006T115330Z_4198821b6237"
DISPATCH_LUA = "4198821b6237"
DISPATCH_LUA_RUN = "20261006T115335Z_f687450fa10d"
VALIDATOR = "20261006T133655Z_165cb9011b52"
PROMOTION = "20261006T134752Z"
BITMAP_FAILED = (
    "20261006T131602Z_dbfc487671f1",
    "20261006T131924Z_ebe2848742df",
    "20261006T132105Z_bf19a1cf2706",
    "20261006T132228Z_81d17096c8e8",
    "20261006T132521Z_03dafdfc1897",
)


def path(relative: str) -> Path:
    return PRUNER.boundary(ROOT / relative)


def add_tree(protected: dict[str, str | None], root: Path) -> int:
    root = PRUNER.boundary(root)
    count = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = PRUNER.boundary(Path(current))
        for name in dirs:
            PRUNER.boundary(current_path / name)
        for name in files:
            file_path = PRUNER.boundary(current_path / name)
            PRUNER.regular(file_path)
            protected.setdefault(str(file_path), None)
            count += 1
    return count


def main() -> int:
    PRUNER.no_active_host()
    launcher = path("tools/Start-Engine.ps1")
    launcher_text = launcher.read_text(encoding="utf-8-sig")
    manual_runs = sorted(set(PRUNER.RUN.findall(launcher_text)))
    require_manual = {"20261003T154510Z_b1af9e8eb764", "20261003T230735Z_2003f24507ce",
                      "20261004T000710Z_796f1ea91c5e", MANUAL_DEFAULT}
    if set(manual_runs) != require_manual or PREVIOUS_MANUAL_DEFAULT in manual_runs:
        raise RuntimeError("Frozen launcher manual-runtime list differs from reviewed promotion")

    prior_manual = path(f"Build/InteractiveGameRuntime/{PREVIOUS_MANUAL_DEFAULT}")
    prior_saves = list(prior_manual.rglob("*.zssave"))
    if prior_saves:
        raise RuntimeError("Previous manual default unexpectedly contains save files")
    previous_launcher_mentions = PREVIOUS_MANUAL_DEFAULT in launcher_text
    if previous_launcher_mentions:
        raise RuntimeError("Previous manual default is still referenced by the frozen launcher")

    combat_result = path(f"evidence/interactive_game/{COMBAT_PASS}/result.json")
    combat_status = json.loads(combat_result.read_text(encoding="utf-8-sig")).get("status")
    if combat_status != "CONTINUOUS_INTERACTIVE_SDK_COMBAT_SMOKE_PASS":
        raise RuntimeError("Newer combat run is not a passing replacement")
    failed_combat_result = path(f"evidence/interactive_game/{COMBAT_FAILED}/result.json")
    if json.loads(failed_combat_result.read_text(encoding="utf-8-sig")).get("status") != \
            "CONTINUOUS_INTERACTIVE_SDK_COMBAT_SMOKE_FAILED":
        raise RuntimeError("Failed combat candidate status changed")

    candidates = [
        f"Build/UiWindowHost/20261006T120008Z_32a336f5d95d",
        f"evidence/ui_window_host/20261006T120008Z_32a336f5d95d",
        f"Build/InteractiveGameRuntime/20261006T120232Z_10eeb7212e57",
        f"evidence/interactive_game/20261006T120232Z_10eeb7212e57",
        f"Build/InteractiveGameRuntime/20261006T121618Z_e382f0b538e7",
        f"evidence/interactive_game/20261006T121618Z_e382f0b538e7",
        f"Build/InteractiveGameRuntime/{COMBAT_FAILED}",
        f"evidence/interactive_game/{COMBAT_FAILED}",
        f"Build/InteractiveGameRuntime/{PREVIOUS_MANUAL_DEFAULT}",
        f"evidence/interactive_game/{PREVIOUS_MANUAL_DEFAULT}",
    ]
    for run in BITMAP_FAILED:
        candidates.extend((f"Build/BitmapWindow/{run}", f"evidence/bitmap_window/{run}"))
    if len(candidates) != 20 or len(set(candidates)) != 20:
        raise RuntimeError("Fixed retirement whitelist is malformed")
    candidate_paths = [path(relative) for relative in candidates]

    seeds = [
        "evidence/shared_lua_runtime/build_result.json",
        "evidence/explore_sdk/build_result.json",
        "evidence/city_site_sdk/build_result.json",
        "evidence/found_value_shared_sdk/build_result.json",
        "evidence/host/bundle.json",
        "evidence/database/candidate/build_result.json",
        "evidence/localization/provider/build_result.json",
        "evidence/streams/provider/build_result.json",
        "evidence/temp_heap/build_result.json",
        f"evidence/ui_window_host/{HOST}/build_result.json",
        f"evidence/bitmap_window/{BITMAP_PASS}/conformance.json",
        f"validators/{VALIDATOR}/conformance.json",
        f"evidence/ui_input_dispatch/{DISPATCH}/conformance.json",
        f"evidence/ui_input_lua/{DISPATCH_LUA}/{DISPATCH_LUA_RUN}/conformance.json",
        f"evidence/runtime_promotion/{PROMOTION}/promotion.json",
    ]
    seeds += [
        f"evidence/interactive_game/{run}/{name}"
        for run in sorted(set([FRESH, RESTORE, *manual_runs]))
        for name in ("request.json", "result.json")
        if (ROOT / "evidence/interactive_game" / run / name).is_file()
    ]
    seed_paths = [path(relative) for relative in seeds]
    protected, documents = PRUNER.closure(seed_paths)

    protected_trees = [
        ROOT / "Source", ROOT / "Tests", ROOT / "tools",
        ROOT / "Build/UiWindowHost" / HOST,
        ROOT / "Build/BitmapWindow" / BITMAP_PASS,
        ROOT / "evidence/ui_window_host" / HOST,
        ROOT / "evidence/bitmap_window" / BITMAP_PASS,
        ROOT / "Build/InteractiveGameRuntime" / FRESH,
        ROOT / "Build/InteractiveGameRuntime" / RESTORE,
        ROOT / "Build/InteractiveGameRuntime" / MANUAL_DEFAULT,
        ROOT / "evidence/interactive_game" / FRESH,
        ROOT / "evidence/interactive_game" / RESTORE,
        ROOT / "evidence/interactive_game" / MANUAL_DEFAULT,
        ROOT / "Build/UiInputDispatch" / DISPATCH,
        ROOT / "evidence/ui_input_dispatch" / DISPATCH,
        ROOT / "Build/UiInputLua" / DISPATCH_LUA / DISPATCH_LUA_RUN,
        ROOT / "evidence/ui_input_lua" / DISPATCH_LUA / DISPATCH_LUA_RUN,
    ] + [ROOT / "Build/InteractiveGameRuntime" / run for run in manual_runs] + [
        ROOT / "evidence/interactive_game" / run for run in manual_runs]
    for tree in protected_trees:
        add_tree(protected, tree)

    manual_save_paths = []
    for run in manual_runs:
        runtime = path(f"Build/InteractiveGameRuntime/{run}")
        manual_save_paths.extend(PRUNER.boundary(save) for save in runtime.rglob("*.zssave"))
    if len(manual_save_paths) != 8:
        raise RuntimeError(f"Expected exactly eight retained manual saves, found {len(manual_save_paths)}")
    checkpoint = path(f"Build/InteractiveGameRuntime/{RESTORE}/checkpoint-input.zssave")
    if not checkpoint.is_file():
        raise RuntimeError("Latest restore checkpoint input is missing")
    for save in [*manual_save_paths, checkpoint]:
        protected.setdefault(str(save), None)

    protected_roots = {Path(name).relative_to(ROOT).parts for name in protected}
    for candidate in candidate_paths:
        parts = candidate.relative_to(ROOT).parts
        if any(parts[:len(prefix)] == prefix or prefix[:len(parts)] == parts
               for prefix in protected_roots):
            raise RuntimeError("Candidate intersects protected dependency closure: " + str(candidate))

    planner_path = path(Path(__file__).relative_to(ROOT).as_posix())
    protected.setdefault(str(planner_path), None)

    # Existing report format: path -> SHA map plus a file-identity retirement ledger.
    hash_cache: dict[tuple[int, int, int, int], str] = {}
    for name in list(protected):
        protected_path = path(Path(name).relative_to(ROOT).as_posix())
        info = PRUNER.regular(protected_path)
        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
        if identity not in hash_cache:
            hash_cache[identity] = PRUNER.digest(protected_path)
        protected[name] = hash_cache[identity]

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + uuid.uuid4().hex[:12]
    output = ROOT / "evidence/storage_cleanup" / stamp
    output.mkdir(parents=True, exist_ok=False)
    protected_file = output / "protected.json.gz"
    with gzip.open(protected_file, "wt", encoding="utf-8") as stream:
        json.dump(protected, stream, separators=(",", ":"))

    ledger = output / "retired-files.jsonl.gz"
    summaries = []
    total_files = total_bytes = 0
    identities: dict[tuple[int, int], dict[str, int]] = {}
    with gzip.open(ledger, "wt", encoding="utf-8") as stream:
        for candidate in candidate_paths:
            count = size = 0
            for file_path, info in PRUNER.inventory(candidate):
                identity4 = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns)
                if identity4 not in hash_cache:
                    hash_cache[identity4] = PRUNER.digest(file_path)
                identity2 = (info.st_dev, info.st_ino)
                hardlink = identities.setdefault(identity2, {"links": info.st_nlink, "count": 0,
                                                               "stored": PRUNER.stored(file_path)})
                hardlink["count"] += 1
                stream.write(json.dumps({"path": str(file_path.relative_to(ROOT)),
                    "sha256": hash_cache[identity4], "bytes": info.st_size,
                    "mtime_ns": info.st_mtime_ns, "device": info.st_dev,
                    "file_id": info.st_ino}, separators=(",", ":")) + "\n")
                count += 1
                size += info.st_size
            summaries.append({"path": str(candidate.relative_to(ROOT)), "files": count,
                              "logical_bytes": size})
            total_files += count
            total_bytes += size

    old_manual_evidence = path(f"evidence/interactive_game/{PREVIOUS_MANUAL_DEFAULT}/result.json")
    previous_manual_status = json.loads(old_manual_evidence.read_text(encoding="utf-8-sig")).get("status")
    report = {
        "status": "PREVIEW_ONLY",
        "scope": "FIXED_20_DIRECTORY_RETIREMENT_PREVIEW_NO_DELETE",
        "root": str(ROOT),
        "candidate_rule": "Only the exact 20 fixed relative paths listed; failed combat is gated by newer PASS.",
        "combat_gate": {"candidate_run": COMBAT_FAILED, "candidate_status": "CONTINUOUS_INTERACTIVE_SDK_COMBAT_SMOKE_FAILED",
                        "replacement_run": COMBAT_PASS, "replacement_status": combat_status},
        "previous_manual_default": {"run_id": PREVIOUS_MANUAL_DEFAULT,
            "result_status": previous_manual_status, "launcher_referenced": previous_launcher_mentions,
            "zssave_count": len(prior_saves)},
        "kept": {"host_build": HOST, "fresh_restore": [FRESH, RESTORE],
                 "combat_pass": COMBAT_PASS, "manual_default": MANUAL_DEFAULT,
                 "bitmap_window_pass": BITMAP_PASS, "dispatch": DISPATCH,
                 "dispatch_lua": [DISPATCH_LUA, DISPATCH_LUA_RUN],
                 "manual_runtimes": manual_runs, "manual_save_count": len(manual_save_paths),
                 "restore_checkpoint_input": str(checkpoint.relative_to(ROOT))},
        "seed_documents": [str(item) for item in seed_paths],
        "protected_file_count": len(protected), "protected_json_documents": len(documents),
        "protected": {"path": str(protected_file), "sha256": PRUNER.digest(protected_file)},
        "ledger": {"path": str(ledger), "sha256": PRUNER.digest(ledger)},
        "directories": summaries, "files": total_files, "logical_bytes": total_bytes,
        "estimated_reclaimable_file_storage": sum(item["stored"] for item in identities.values()
            if item["links"] == item["count"]),
        "source_tests_tools_game_mods_saves_deleted": False,
        "Start-Engine.ps1_protected_after_frozen_promotion": str(launcher),
        "script_sha256": PRUNER.digest(PRUNER_PATH),
        "format_pruner": str(PRUNER_PATH), "format_pruner_sha256": PRUNER.digest(PRUNER_PATH),
        "planner": str(Path(__file__)), "planner_sha256": PRUNER.digest(Path(__file__)),
        "apply_note": "Preview only; this task did not apply the plan.",
    }
    plan_path = output / "plan.json"
    plan_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "plan": str(plan_path), "files": total_files,
        "logical_bytes": total_bytes, "directories": len(candidate_paths),
        "protected_files": len(protected), "protected_json_documents": len(documents)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
