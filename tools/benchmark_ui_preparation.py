"""Measure retained UI scene preparation without launching the Host or GameCore.

The benchmark uses one immutable scene snapshot per selected context, profiles
only render_ui_popup.prepare(), hashes its declared source inputs before and
after, and removes its uniquely owned temporary output tree.
"""
from __future__ import annotations

import cProfile
from datetime import datetime, timezone
import hashlib
import inspect
import json
import os
from pathlib import Path
import pstats
import re
import shutil
import stat
import statistics
import sys
import time
import uuid


PROJECT = Path(__file__).resolve().parents[1]
SOURCE_RUN = "20261008T225105Z_a09bb643b908"
CONTEXTS = ("city-view", "top-panel", "trade-route")
MAX_TEMP_BYTES = 512 * 1024 * 1024
GAME = Path(r"C:\Program Files (x86)\Steam\steamapps\common\Sid Meier's Civilization V")


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def checked_file(path: str | Path) -> Path:
    absolute = Path(os.path.abspath(os.fspath(path)))
    try:
        info = absolute.lstat()
    except OSError as error:
        raise RuntimeError(f"Cannot stat benchmark input: {absolute}: {error}") from error
    if not stat.S_ISREG(info.st_mode) or absolute.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
        raise RuntimeError(f"Expected regular non-reparse input file: {absolute}")
    return absolute


def add_input(inputs: dict[str, str], path: str | Path, expected: str | None = None) -> None:
    path = checked_file(path)
    actual = digest(path)
    if expected is not None and actual != expected:
        raise RuntimeError(f"Pinned input hash differs: {path}")
    inputs[str(path)] = actual


def add_manifest_sources(inputs: dict[str, str], manifest: dict) -> None:
    for row in manifest.get("pack_sources", []):
        add_input(inputs, row["path"], row["sha256"])
    for row in manifest.get("frozen_ui", []):
        original = row.get("original_path")
        if original and row.get("sha256"):
            add_input(inputs, original, row["sha256"])
    for row in manifest.get("font_sources", []):
        for path_key, hash_key in (("ggxml_path", "ggxml_sha256"),
                                   ("color_atlas_path", "color_atlas_sha256")):
            if row.get(path_key) and row.get(hash_key):
                add_input(inputs, row[path_key], row[hash_key])
        for sheet in row.get("sheets", []):
            if sheet.get("source_path") and sheet.get("source_sha256"):
                add_input(inputs, sheet["source_path"], sheet["source_sha256"])


def tree_inventory(root: Path) -> tuple[int, int]:
    count = 0
    size = 0
    for current, dirs, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in dirs:
            child = current_path / name
            if child.is_symlink() or getattr(child.lstat(), "st_file_attributes", 0) & 0x400:
                raise RuntimeError(f"Refusing reparse point under benchmark output: {child}")
        for name in files:
            child = current_path / name
            info = child.lstat()
            if child.is_symlink() or not child.is_file() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise RuntimeError(f"Refusing non-regular benchmark output: {child}")
            count += 1
            size += info.st_size
    return count, size


def profile_rows(profiler: cProfile.Profile, limit: int = 35) -> tuple[list[dict], list[dict]]:
    stats = pstats.Stats(profiler)
    rows = []
    all_rows = []
    for (filename, line, function), (primitive_calls, calls, self_seconds,
                                     cumulative_seconds, _callers) in stats.stats.items():
        row = {"file": os.path.abspath(filename) if filename != "~" else filename,
               "line": line, "function": function, "calls": calls,
               "self_seconds": self_seconds, "cumulative_seconds": cumulative_seconds}
        all_rows.append(row)
        name = function.casefold()
        if any(token in name for token in ("sha256", "decode_dds", "font", "atlas", "city_view_raster_rgba",
                                           "candidate_directory", "_reject_reparse", "fpk", "retain",
                                           "materialize", "copy", "rgba32")):
            rows.append(row)
    all_rows.sort(key=lambda row: row["cumulative_seconds"], reverse=True)
    rows.sort(key=lambda row: row["cumulative_seconds"], reverse=True)
    return all_rows[:limit], rows[:limit]


def measured_call(profiler: cProfile.Profile, category_totals: dict,
                  *, pack_paths: set[str], assets_module, scene_module, renderer_module,
                  snapshot: Path, directory: Path, manifest_path: Path, context: str,
                  input_copy_seconds: float) -> dict:
    original_sha = assets_module.sha256
    original_scene_sha = scene_module.sha256
    original_renderer_sha = renderer_module.sha256
    original_decode = assets_module.decode_dds
    sha_samples: list[tuple[str, float]] = []
    pack_hash_phases: dict[str, list[float]] = {"pack_catalog_initial": [],
                                                "pack_integrity_final": [], "other": []}
    decode_samples: list[float] = []

    def measured_sha(path):
        resolved = os.path.abspath(os.fspath(path))
        started = time.perf_counter()
        try:
            return original_sha(path)
        finally:
            elapsed = time.perf_counter() - started
            sha_samples.append((resolved, elapsed))
            if resolved in pack_paths:
                frame = inspect.currentframe().f_back
                phase = "other"
                while frame is not None:
                    if Path(frame.f_code.co_filename).name == "civ5_ui_assets.py":
                        caller = frame
                        while caller is not None and Path(caller.f_code.co_filename).name == "civ5_ui_assets.py":
                            owner = caller.f_locals.get("self")
                            if type(owner).__name__ == "UiAssets":
                                if caller.f_code.co_name == "__init__":
                                    phase = "pack_catalog_initial"
                                elif caller.f_code.co_name == "unchanged":
                                    phase = "pack_integrity_final"
                                break
                            caller = caller.f_back
                        break
                    frame = frame.f_back
                pack_hash_phases[phase].append(elapsed)

    def measured_decode(data, index_data=None):
        started = time.perf_counter()
        try:
            return original_decode(data, index_data)
        finally:
            decode_samples.append(time.perf_counter() - started)

    assets_module.sha256 = measured_sha
    scene_module.sha256 = measured_sha
    renderer_module.sha256 = measured_sha
    assets_module.decode_dds = measured_decode
    started = time.perf_counter()
    profiler.enable()
    try:
        renderer_module.prepare(snapshot, directory, manifest_path, closed=False, context=context)
    finally:
        profiler.disable()
        assets_module.sha256 = original_sha
        scene_module.sha256 = original_scene_sha
        renderer_module.sha256 = original_renderer_sha
        assets_module.decode_dds = original_decode
    elapsed = time.perf_counter() - started
    pack_calls = [(path, seconds) for path, seconds in sha_samples if path in pack_paths]
    category_totals["pack_full_hash_calls"] += len(pack_calls)
    category_totals["pack_full_hash_seconds"] += sum(seconds for _, seconds in pack_calls)
    category_totals["all_path_sha_calls"] += len(sha_samples)
    category_totals["all_path_sha_seconds"] += sum(seconds for _, seconds in sha_samples)
    category_totals["dds_decode_calls"] += len(decode_samples)
    category_totals["dds_decode_seconds"] += sum(decode_samples)
    category_totals["input_copy_seconds"] += input_copy_seconds
    all_profile, focus_profile = profile_rows(profiler)
    pack_hash_phases["pack_other"] = pack_hash_phases.pop("other")
    category_totals["pack_hash_phases"].append({
        key: {"calls": len(values), "seconds": sum(values)}
        for key, values in pack_hash_phases.items()})
    return {"wall_seconds": elapsed,
            "input_setup_copy_seconds": input_copy_seconds,
            "pack_hash_calls": len(pack_calls),
            "pack_hash_seconds": sum(seconds for _, seconds in pack_calls),
            "pack_hash_phases": {key: {"calls": len(values), "seconds": sum(values)}
                                 for key, values in pack_hash_phases.items()},
            "all_path_sha_calls": len(sha_samples),
            "all_path_sha_seconds": sum(seconds for _, seconds in sha_samples),
            "dds_decode_calls": len(decode_samples),
            "dds_decode_seconds": sum(decode_samples),
            "profile_top": all_profile,
            "profile_focus": focus_profile,
            "manifest_path": str(manifest_path)}


def unprofiled_call(renderer_module, snapshot: Path, directory: Path,
                    manifest_path: Path, context: str) -> dict:
    started = time.perf_counter()
    renderer_module.prepare(snapshot, directory, manifest_path, closed=False, context=context)
    return {"wall_seconds": time.perf_counter() - started,
            "profiling_enabled": False, "manifest_path": str(manifest_path)}


def output_file_map(root: Path) -> dict:
    """Hash only the scene packet and retained UI texture/source trees."""
    result = {}
    packet = root / "scene.packet"
    if packet.is_file():
        result["scene.packet/scene.packet"] = {"size": packet.stat().st_size,
                                                "sha256": digest(packet)}
    for category in ("textures", "source_assets", "source_ui"):
        folder = root / category
        if not folder.exists():
            continue
        for current, dirs, files in os.walk(folder, followlinks=False):
            current_path = Path(current)
            for name in dirs:
                child = current_path / name
                info = child.lstat()
                if child.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise RuntimeError(f"Refusing reparse point in output inventory: {child}")
            for name in files:
                child = current_path / name
                info = child.lstat()
                if child.is_symlink() or not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                    raise RuntimeError(f"Refusing non-regular output inventory file: {child}")
                rel = child.relative_to(root).as_posix()
                result[rel] = {"size": info.st_size, "sha256": digest(child)}
    return result


def output_map_summary(rows: dict) -> dict:
    groups = {name: {"files": 0, "bytes": 0} for name in
              ("scene.packet", "textures", "source_assets", "source_ui")}
    for relative, row in rows.items():
        category = relative.split("/", 1)[0]
        groups[category]["files"] += 1
        groups[category]["bytes"] += row["size"]
    return groups


def compare_file_maps(left: dict, right: dict) -> bool:
    return left == right


def checked_owned_directory_for_removal(path: Path, expected_parent: Path,
                                        expected_name: str) -> Path:
    """Resolve and reject reparse points before deleting one benchmark-owned tree."""
    lexical = Path(os.path.abspath(os.fspath(path)))
    parent_lexical = Path(os.path.abspath(os.fspath(expected_parent)))
    if lexical.parent != parent_lexical or lexical.name != expected_name:
        raise RuntimeError(f"Refusing cleanup outside exact owned directory: {lexical}")
    parent_real = parent_lexical.resolve(strict=True)
    path_real = lexical.resolve(strict=True)
    if path_real.parent != parent_real or path_real.name != expected_name:
        raise RuntimeError(f"Resolved cleanup path differs from exact owned directory: {path_real}")
    project_lexical = Path(os.path.abspath(os.fspath(PROJECT)))
    if parent_lexical != project_lexical and not parent_lexical.is_relative_to(project_lexical):
        raise RuntimeError(f"Cleanup parent escapes project workspace: {parent_lexical}")
    current = lexical
    while True:
        info = current.lstat()
        if current.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
            raise RuntimeError(f"Refusing cleanup through reparse point: {current}")
        if current == project_lexical:
            break
        if current.parent == current:
            raise RuntimeError("Cleanup ancestry did not reach the expected parent")
        current = current.parent
    return path_real


def pair_schedule() -> list[list[str]]:
    return [["serial", "thread"], ["thread", "serial"], ["serial", "thread"]]


def validate_comparison_json(doc: dict) -> None:
    """Pure contract validation used before touching source inputs or output folders."""
    if doc.get("status") != "PASS_UI_PACK_HASH_COMPARISON":
        raise ValueError("comparison status is not PASS")
    if doc.get("inputs_unchanged") is not True or doc.get("input_sha256_before") != doc.get("input_sha256_after"):
        raise ValueError("input hash boundary is incomplete")
    if len(doc.get("input_sha256_before", {})) < 63:
        raise ValueError("comparison requires at least 63 pinned inputs")
    if doc.get("temporary_output", {}).get("removed_after_measurement") is not True:
        raise ValueError("comparison temporary output was not removed")
    for context in CONTEXTS:
        row = doc.get("contexts", {}).get(context)
        if not row or row.get("baseline_packet_sha256") != row.get("packet_sha256"):
            raise ValueError(f"{context} packet differs from preserved baseline")
        pairs = row.get("pairs", [])
        if len(pairs) != 3:
            raise ValueError(f"{context} does not have three A/B pairs")
        for index, pair in enumerate(pairs):
            if pair.get("order") != pair_schedule()[index]:
                raise ValueError(f"{context} pair order is not alternating")
            if pair.get("packet_sha256") != row["baseline_packet_sha256"]:
                raise ValueError(f"{context} pair packet differs from preserved baseline")
            runs = pair.get("runs", {})
            if set(runs) != {"serial", "thread"}:
                raise ValueError(f"{context} pair is missing a mode")
            if not compare_file_maps(runs["serial"].get("outputs", {}), runs["thread"].get("outputs", {})):
                raise ValueError(f"{context} serial/thread output files differ")
            if pair.get("outputs_identical") is not True:
                raise ValueError(f"{context} pair is not marked identical")
            for mode in ("serial", "thread"):
                if runs[mode].get("packet_sha256") != row["baseline_packet_sha256"] or runs[mode].get("manifest_packet_sha256") != row["baseline_packet_sha256"]:
                    raise ValueError(f"{context} {mode} packet or manifest differs from baseline")


def compare_self_test() -> int:
    files = {"scene.packet/scene.packet": {"size": 4, "sha256": "a" * 64},
             "textures/x.dds": {"size": 2, "sha256": "b" * 64}}
    if not compare_file_maps(files, json.loads(json.dumps(files))):
        raise AssertionError("equal file maps were rejected")
    altered = json.loads(json.dumps(files))
    altered["textures/x.dds"]["size"] += 1
    if compare_file_maps(files, altered):
        raise AssertionError("different output maps were accepted")
    if pair_schedule() != [["serial", "thread"], ["thread", "serial"], ["serial", "thread"]]:
        raise AssertionError("A/B schedule did not alternate")
    good = {"status": "PASS_UI_PACK_HASH_COMPARISON", "inputs_unchanged": True,
            "input_sha256_before": {f"input-{i}": "0" * 64 for i in range(63)},
            "input_sha256_after": {f"input-{i}": "0" * 64 for i in range(63)},
            "temporary_output": {"removed_after_measurement": True}, "contexts": {}}
    for context in CONTEXTS:
        good["contexts"][context] = {"baseline_packet_sha256": "c" * 64,
                                     "packet_sha256": "c" * 64,
                                     "pairs": [{"order": order, "packet_sha256": "c" * 64,
                                                "outputs_identical": True,
                                                "runs": {"serial": {"outputs": files, "packet_sha256": "c" * 64,
                                                                      "manifest_packet_sha256": "c" * 64},
                                                         "thread": {"outputs": json.loads(json.dumps(files)),
                                                                      "packet_sha256": "c" * 64,
                                                                      "manifest_packet_sha256": "c" * 64}}}
                                               for order in pair_schedule()]}
    validate_comparison_json(good)
    bad = json.loads(json.dumps(good))
    bad["contexts"]["trade-route"]["pairs"][0]["runs"]["thread"]["outputs"]["textures/x.dds"]["sha256"] = "d" * 64
    try:
        validate_comparison_json(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("JSON contract accepted a texture hash mismatch")
    bad = json.loads(json.dumps(good))
    bad["contexts"]["city-view"]["pairs"][1]["packet_sha256"] = "e" * 64
    try:
        validate_comparison_json(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("JSON contract accepted a pair packet mismatch")
    print(json.dumps({"status": "PASS_UI_PACK_HASH_COMPARISON_SELF_TEST",
                      "checks": 6}, ensure_ascii=False))
    return 0


def compare_pack_hash_modes() -> int:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PROJECT / "tools"))
    import civ5_ui_assets as assets_module
    import ui_pixel_scene as scene_module
    import render_ui_popup as renderer_module
    original_pack_hash = assets_module._pack_sha256

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]
    source_evidence = PROJECT / "evidence/interactive_game" / SOURCE_RUN
    driver_path = checked_file(source_evidence / "driver_result.json")
    driver = json.loads(driver_path.read_text(encoding="utf-8"))
    baseline_path = checked_file(PROJECT / "evidence/ui_preparation_benchmark/20261009T014854Z_b4d31e34918b/result.json")
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    build_parent = PROJECT / "Build/UiPreparationBenchmark"
    evidence_dir = PROJECT / "evidence/ui_preparation_benchmark" / run_id
    temp_root = build_parent / run_id
    build_parent.mkdir(parents=True, exist_ok=True)
    evidence_dir.mkdir(parents=True, exist_ok=False)
    temp_root.mkdir(parents=False, exist_ok=False)

    scene_sources = {}
    before_inputs: dict[str, str] = {}
    report = {"status": "RUNNING_UI_PACK_HASH_COMPARISON", "run_id": run_id,
              "source_run_id": SOURCE_RUN, "baseline_report": str(baseline_path),
              "mode_definition": {
                  "thread": "current civ5_ui_assets._pack_sha256, ThreadPoolExecutor(max_workers=4) over all four complete FPK sha256 reads",
                  "serial_reference": "lambda paths: [assets_module.sha256(p) for p in paths], same paths and SHA-256 function, sequential complete reads; no digest cache",
                  "scope": "only pack digest scheduling changes; render_ui_popup.prepare wall time is measured with cProfile disabled"},
              "contexts": {}, "input_sha256_before": {}, "input_sha256_after": {},
              "inputs_unchanged": False,
              "temporary_output": {"path": str(temp_root), "limit_bytes": MAX_TEMP_BYTES,
                                   "removed_after_measurement": False}}
    journal = evidence_dir / "comparison_journal.json"

    def save_journal():
        journal.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    save_journal()
    try:
        for path in (driver_path, baseline_path):
            add_input(before_inputs, path)
        product_files = ("render_ui_popup.py", "ui_pixel_scene.py", "civ5_ui_assets.py",
                         "ui_bitmap_fonts.py", "benchmark_ui_preparation.py")
        for name in product_files:
            add_input(before_inputs, PROJECT / "tools" / name)
        for context in CONTEXTS:
            matches = [row for row in driver.get("scene_requests", []) if row.get("context") == context]
            if not matches:
                raise RuntimeError(f"Fresh source report has no {context} scene request")
            row = matches[0]
            source_manifest_path = checked_file(row["manifest"]["path"])
            source_folder = source_manifest_path.parent
            source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
            snapshot = checked_file(source_manifest["snapshot"]["path"])
            if digest(snapshot) != source_manifest["snapshot"]["sha256"]:
                raise RuntimeError(f"{context} snapshot differs from its pinned scene manifest")
            prep_path = checked_file(row["preparation_inputs"]["path"])
            prep = json.loads(prep_path.read_text(encoding="utf-8"))
            colors = checked_file(prep["colors"]["path"])
            icons = checked_file(prep["inline_icons"]["path"])
            for file_path, expected in ((snapshot, source_manifest["snapshot"]["sha256"]),
                                        (prep_path, row["preparation_inputs"]["sha256"]),
                                        (colors, prep["colors"]["sha256"]),
                                        (icons, prep["inline_icons"]["sha256"])):
                add_input(before_inputs, file_path, expected)
            add_input(before_inputs, source_manifest_path, row["manifest"]["sha256"])
            add_manifest_sources(before_inputs, source_manifest)
            scene_sources[context] = {"snapshot": snapshot, "colors": colors, "icons": icons,
                                      "source_scene_folder": source_folder,
                                      "snapshot_sha256": digest(snapshot)}
        first_session = next(iter(scene_sources.values()))["source_scene_folder"].parent
        run_root = PROJECT / "Build/InteractiveGameRuntime" / SOURCE_RUN
        for path in (first_session / "rules.db",
                     run_root / "interactive_ui_support/assets/inline_icons.json",
                     run_root / "interactive_ui_support/support_manifest.json"):
            add_input(before_inputs, path)
        report["input_sha256_before"] = before_inputs.copy()
        if len(before_inputs) < 63:
            raise RuntimeError(f"Expected at least 63 pinned inputs, found {len(before_inputs)}")
        baseline_packets = {context: baseline["contexts"][context]["runs"][0]["packet_sha256"]
                            for context in CONTEXTS}
        report["baseline_packet_sha256"] = baseline_packets
        save_journal()

        for context in CONTEXTS:
            source = scene_sources[context]
            context_result = {"snapshot_sha256": source["snapshot_sha256"],
                              "baseline_packet_sha256": baseline_packets[context], "pairs": []}
            report["contexts"][context] = context_result
            for pair_index, order in enumerate(pair_schedule(), start=1):
                pair_root = temp_root / f"{context}-pair-{pair_index}"
                pair_root.mkdir(parents=False, exist_ok=False)
                pair = {"pair": pair_index, "order": order, "runs": {},
                        "outputs_identical": False, "cleanup_complete": False}
                context_result["pairs"].append(pair)
                save_journal()
                try:
                    for mode in order:
                        target = pair_root / mode
                        target.mkdir(parents=False, exist_ok=False)
                        shutil.copy2(source["colors"], target / "inline_colors.json")
                        shutil.copy2(source["icons"], target / "inline_icons.json")
                        pack_calls = []
                        if mode == "thread":
                            strategy = original_pack_hash
                        else:
                            strategy = lambda paths: [assets_module.sha256(p) for p in paths]

                        def timed_strategy(paths):
                            path_list = list(paths)
                            started = time.perf_counter()
                            values = strategy(path_list)
                            pack_calls.append({"elapsed_seconds": time.perf_counter() - started,
                                               "path_count": len(path_list), "digest_count": len(values)})
                            return values

                        assets_module._pack_sha256 = timed_strategy
                        started = time.perf_counter()
                        prepare_error = None
                        try:
                            renderer_module.prepare(source["snapshot"], target,
                                                   target / "scene_manifest.json", closed=False,
                                                   context=context)
                        except BaseException as error:
                            prepare_error = error
                        finally:
                            elapsed = time.perf_counter() - started
                            assets_module._pack_sha256 = original_pack_hash
                        run_result = {"mode": mode, "profiling_enabled": False,
                                      "prepare_wall_seconds": elapsed,
                                      "pack_hash_calls": pack_calls,
                                      "pack_hash_elapsed_sum_seconds": sum(c["elapsed_seconds"] for c in pack_calls),
                                      "outputs": {}, "output_categories": output_map_summary({})}
                        if prepare_error is not None:
                            run_result["error"] = f"{type(prepare_error).__name__}: {prepare_error}"
                        pair["runs"][mode] = run_result
                        save_journal()
                        if prepare_error is not None:
                            raise prepare_error
                        manifest_doc = json.loads((target / "scene_manifest.json").read_text(encoding="utf-8"))
                        outputs = output_file_map(target)
                        packet_hash = outputs.get("scene.packet/scene.packet", {}).get("sha256")
                        run_result.update({"packet_sha256": packet_hash,
                                           "packet_bytes": outputs.get("scene.packet/scene.packet", {}).get("size"),
                                           "outputs": outputs,
                                           "output_categories": output_map_summary(outputs),
                                           "manifest_packet_sha256": manifest_doc["packet"]["sha256"]})
                        current_count, current_bytes = tree_inventory(temp_root)
                        if current_bytes > MAX_TEMP_BYTES:
                            raise RuntimeError(f"Temporary output exceeded cap after {context} pair {pair_index} {mode}")
                        pair["temporary_bytes_after_mode"] = current_bytes
                        pair["temporary_file_count_after_mode"] = current_count
                        save_journal()
                    serial = pair["runs"]["serial"]
                    threaded = pair["runs"]["thread"]
                    packet_hash = serial["packet_sha256"]
                    if packet_hash != threaded["packet_sha256"] or packet_hash != baseline_packets[context]:
                        raise RuntimeError(f"{context} pair {pair_index} packet SHA differs from baseline or other mode")
                    if serial["manifest_packet_sha256"] != packet_hash or threaded["manifest_packet_sha256"] != packet_hash:
                        raise RuntimeError(f"{context} pair {pair_index} manifest packet hash differs from file")
                    if not compare_file_maps(serial["outputs"], threaded["outputs"]):
                        raise RuntimeError(f"{context} pair {pair_index} serial/thread output inventories differ")
                    pair["packet_sha256"] = packet_hash
                    pair["outputs_identical"] = True
                except BaseException as error:
                    pair["error"] = f"{type(error).__name__}: {error}"
                    raise
                finally:
                    # Journal all measured output hashes before deleting only this exact pair tree.
                    save_journal()
                    if pair_root.exists():
                        safe_pair = checked_owned_directory_for_removal(
                            pair_root, temp_root, f"{context}-pair-{pair_index}")
                        checked_owned_directory_for_removal(temp_root, build_parent, run_id)
                        shutil.rmtree(safe_pair)
                    pair["cleanup_complete"] = not pair_root.exists()
                    save_journal()
                if not pair["cleanup_complete"]:
                    raise RuntimeError(f"Comparison pair cleanup failed: {pair_root}")

        assets_module._pack_sha256 = original_pack_hash
        report["summary"] = {}
        for context, context_result in report["contexts"].items():
            context_result["packet_sha256"] = context_result["pairs"][0]["packet_sha256"]
            serial_walls = [pair["runs"]["serial"]["prepare_wall_seconds"]
                            for pair in context_result["pairs"]]
            thread_walls = [pair["runs"]["thread"]["prepare_wall_seconds"]
                            for pair in context_result["pairs"]]
            serial_median = statistics.median(serial_walls)
            thread_median = statistics.median(thread_walls)
            report["summary"][context] = {
                "serial_wall_seconds": serial_walls,
                "thread_wall_seconds": thread_walls,
                "serial_wall_median_seconds": serial_median,
                "thread_wall_median_seconds": thread_median,
                "thread_over_serial_wall_ratio": thread_median / serial_median if serial_median else None,
                "packet_and_textures_source_files_identical_all_pairs": all(
                    pair["outputs_identical"] for pair in context_result["pairs"])}
        after_inputs = {}
        for path, expected in before_inputs.items():
            add_input(after_inputs, path, expected)
        report["input_sha256_after"] = after_inputs
        report["inputs_unchanged"] = after_inputs == before_inputs
        if not report["inputs_unchanged"]:
            raise RuntimeError("Pinned source or product input changed during comparison")
        count, size = tree_inventory(temp_root)
        report["temporary_output"].update({"file_count": count, "logical_bytes": size,
                                           "removed_after_measurement": False})
        if size != 0:
            raise RuntimeError("Temporary pair folders were not fully removed")
        safe_root = checked_owned_directory_for_removal(temp_root, build_parent, run_id)
        safe_root.rmdir()
        report["temporary_output"]["removed_after_measurement"] = True
        report["status"] = "PASS_UI_PACK_HASH_COMPARISON"
        validate_comparison_json(report)
        save_journal()
        (evidence_dir / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                   encoding="utf-8")
        print(json.dumps({"status": report["status"], "run_id": run_id,
                          "report": str(journal), "input_count": len(before_inputs),
                          "temporary_removed": True,
                          "contexts": {name: {"serial_wall_seconds": [p["runs"]["serial"]["prepare_wall_seconds"] for p in row["pairs"]],
                                              "thread_wall_seconds": [p["runs"]["thread"]["prepare_wall_seconds"] for p in row["pairs"]],
                                              "outputs_identical": all(p["outputs_identical"] for p in row["pairs"])}
                                       for name, row in report["contexts"].items()}}, ensure_ascii=False))
        return 0
    except BaseException as error:
        assets_module._pack_sha256 = original_pack_hash
        report["status"] = "FAIL_UI_PACK_HASH_COMPARISON"
        report["error"] = f"{type(error).__name__}: {error}"
        report["input_sha256_before"] = before_inputs.copy()
        after_inputs = {}
        try:
            for path in before_inputs:
                add_input(after_inputs, path)
            report["input_sha256_after"] = after_inputs
            report["inputs_unchanged"] = after_inputs == before_inputs
        except BaseException as hash_error:
            report["input_hash_after_error"] = f"{type(hash_error).__name__}: {hash_error}"
        try:
            report["temporary_output"].update({"file_count": tree_inventory(temp_root)[0],
                                               "logical_bytes": tree_inventory(temp_root)[1]})
        except OSError:
            pass
        if temp_root.exists():
            safe_root = checked_owned_directory_for_removal(temp_root, build_parent, run_id)
            shutil.rmtree(safe_root)
        report["temporary_output"]["removed_after_measurement"] = not temp_root.exists()
        save_journal()
        raise


def finalize_saved_comparison(run_id: str) -> int:
    if not re.fullmatch(r"20[0-9]{6}T[0-9]{6}Z_[0-9a-f]{12}", run_id):
        raise ValueError("Invalid comparison run identifier")
    evidence_dir = PROJECT / "evidence/ui_preparation_benchmark" / run_id
    journal = checked_file(evidence_dir / "comparison_journal.json")
    journal_hash = digest(journal)
    report = json.loads(journal.read_text(encoding="utf-8"))
    if report.get("error") != "ValueError: city-view packet differs from preserved baseline":
        raise ValueError("Journal does not contain the known post-measurement aggregation failure")
    if report.get("inputs_unchanged") is not True or report.get("input_sha256_before") != report.get("input_sha256_after"):
        raise ValueError("Saved measurement journal does not have matching input hashes")
    if report.get("temporary_output", {}).get("removed_after_measurement") is not True:
        raise ValueError("Saved measurement journal does not confirm temporary cleanup")
    report["recovered_aggregation_error"] = report.pop("error")
    report["status"] = "PASS_UI_PACK_HASH_COMPARISON"
    report["summary"] = {}
    for context in CONTEXTS:
        row = report["contexts"][context]
        pairs = row.get("pairs", [])
        if len(pairs) != 3:
            raise ValueError(f"Saved {context} journal does not contain three complete pairs")
        for pair_index, pair in enumerate(pairs):
            if pair.get("order") != pair_schedule()[pair_index] or pair.get("cleanup_complete") is not True:
                raise ValueError(f"Saved {context} pair {pair_index + 1} has invalid order or cleanup state")
            if not pair.get("outputs_identical") or not compare_file_maps(pair["runs"]["serial"]["outputs"], pair["runs"]["thread"]["outputs"]):
                raise ValueError(f"Saved {context} pair {pair_index + 1} does not prove output identity")
        row["packet_sha256"] = pairs[0]["packet_sha256"]
        serial_walls = [pair["runs"]["serial"]["prepare_wall_seconds"] for pair in pairs]
        thread_walls = [pair["runs"]["thread"]["prepare_wall_seconds"] for pair in pairs]
        serial_median = statistics.median(serial_walls)
        thread_median = statistics.median(thread_walls)
        report["summary"][context] = {
            "serial_wall_seconds": serial_walls,
            "thread_wall_seconds": thread_walls,
            "serial_wall_median_seconds": serial_median,
            "thread_wall_median_seconds": thread_median,
            "thread_over_serial_wall_ratio": thread_median / serial_median if serial_median else None,
            "packet_and_textures_source_files_identical_all_pairs": True}
    report["recovery_note"] = "Final summary derived only from the preserved completed journal; no scene preparation was rerun. The original journal remains unchanged."
    report["recovery_provenance"] = {
        "raw_journal": str(journal), "raw_journal_sha256": journal_hash,
        "raw_journal_status": "FAIL_UI_PACK_HASH_COMPARISON",
        "raw_journal_error": report["recovered_aggregation_error"],
        "repair": "populate context.packet_sha256 from the first validated pair before contract validation",
        "current_benchmark_tool_sha256": digest(PROJECT / "tools/benchmark_ui_preparation.py"),
        "captured_tool_sha256_at_measurement": report["input_sha256_before"].get(
            str(PROJECT / "tools/benchmark_ui_preparation.py"))}
    validate_comparison_json(report)
    result_path = evidence_dir / "result.json"
    if digest(journal) != journal_hash:
        raise RuntimeError("Raw measurement journal changed during finalization")
    with result_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "result": str(result_path),
                      "source_journal": str(journal), "reused_measurements": True}, ensure_ascii=False))
    return 0


def main() -> int:
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(PROJECT / "tools"))
    import civ5_ui_assets as assets_module
    import ui_pixel_scene as scene_module
    import render_ui_popup as renderer_module

    if not (PROJECT / "evidence/interactive_game" / SOURCE_RUN / "driver_result.json").is_file():
        raise RuntimeError("Pinned fresh source run is unavailable")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "_" + uuid.uuid4().hex[:12]
    source_evidence = PROJECT / "evidence/interactive_game" / SOURCE_RUN
    driver_path = checked_file(source_evidence / "driver_result.json")
    driver = json.loads(driver_path.read_text(encoding="utf-8"))
    build_parent = PROJECT / "Build/UiPreparationBenchmark"
    evidence_parent = PROJECT / "evidence/ui_preparation_benchmark"
    build_parent_was_present = build_parent.exists()
    build_parent.mkdir(parents=True, exist_ok=True)
    evidence_dir = evidence_parent / run_id
    evidence_dir.mkdir(parents=True, exist_ok=False)
    temp_root = build_parent / run_id
    temp_root.mkdir(parents=False, exist_ok=False)
    if temp_root.parent.absolute() != build_parent.absolute():
        raise RuntimeError("Benchmark output escaped its task-specific Build folder")

    scene_sources = {}
    before_inputs: dict[str, str] = {}
    try:
        add_input(before_inputs, driver_path)
        for name in ("render_ui_popup.py", "ui_pixel_scene.py", "civ5_ui_assets.py", "ui_bitmap_fonts.py"):
            add_input(before_inputs, PROJECT / "tools" / name)
        for context in CONTEXTS:
            matches = [row for row in driver.get("scene_requests", []) if row.get("context") == context]
            if not matches:
                raise RuntimeError(f"Fresh source report has no {context} scene request")
            row = matches[0]
            source_folder = checked_file(row["manifest"]["path"]).parent
            source_manifest = json.loads(Path(row["manifest"]["path"]).read_text(encoding="utf-8"))
            snapshot = checked_file(source_manifest["snapshot"]["path"])
            if digest(snapshot) != source_manifest["snapshot"]["sha256"]:
                raise RuntimeError(f"{context} snapshot differs from its pinned scene manifest")
            prep_inputs_path = checked_file(row["preparation_inputs"]["path"])
            prep_inputs = json.loads(prep_inputs_path.read_text(encoding="utf-8"))
            colors = checked_file(prep_inputs["colors"]["path"])
            icons = checked_file(prep_inputs["inline_icons"]["path"])
            add_input(before_inputs, snapshot, source_manifest["snapshot"]["sha256"])
            add_input(before_inputs, prep_inputs_path, row["preparation_inputs"]["sha256"])
            add_input(before_inputs, colors, prep_inputs["colors"]["sha256"])
            add_input(before_inputs, icons, prep_inputs["inline_icons"]["sha256"])
            for key in ("rules_database", "support_manifest", "inline_icons_frozen_source"):
                if key in prep_inputs:
                    add_input(before_inputs, prep_inputs[key]["path"], prep_inputs[key]["sha256"])
            add_input(before_inputs, row["manifest"]["path"], row["manifest"]["sha256"])
            add_manifest_sources(before_inputs, source_manifest)
            scene_sources[context] = {"row": row, "snapshot": snapshot,
                                     "colors": colors, "icons": icons,
                                     "source_scene_folder": str(source_folder),
                                     "source_manifest": str(row["manifest"]["path"]),
                                     "snapshot_sha256": digest(snapshot),
                                     "colors_sha256": digest(colors),
                                     "icons_sha256": digest(icons)}

        reference_bytes = 0
        for value in scene_sources.values():
            count, size = tree_inventory(Path(value["source_scene_folder"]))
            value["source_scene_file_count"] = count
            value["source_scene_logical_bytes"] = size
            reference_bytes += size
        if reference_bytes >= MAX_TEMP_BYTES:
            raise RuntimeError("Existing equivalent scene outputs exceed the 512 MiB benchmark cap")

        pack_paths = {os.path.abspath(GAME / "Resource/DX9" / name)
                      for name in assets_module.PACK_POLICY}
        totals = {"pack_full_hash_calls": 0, "pack_full_hash_seconds": 0.0,
                  "all_path_sha_calls": 0, "all_path_sha_seconds": 0.0,
                  "dds_decode_calls": 0, "dds_decode_seconds": 0.0,
                  "pack_hash_phases": [],
                  "input_copy_seconds": 0.0}
        context_results = {}
        for context in CONTEXTS:
            source = scene_sources[context]
            repeated = []
            for repeat_index in (1, 2):
                target = temp_root / f"{context}-{repeat_index}"
                target.mkdir(parents=False, exist_ok=False)
                copy_started = time.perf_counter()
                shutil.copy2(source["colors"], target / "inline_colors.json")
                shutil.copy2(source["icons"], target / "inline_icons.json")
                copy_seconds = time.perf_counter() - copy_started
                if repeat_index == 1:
                    result = unprofiled_call(renderer_module, Path(source["snapshot"]), target,
                                             target / "scene_manifest.json", context)
                    result["input_setup_copy_seconds"] = copy_seconds
                else:
                    profiler = cProfile.Profile()
                    result = measured_call(profiler, totals, pack_paths=pack_paths,
                                           assets_module=assets_module, scene_module=scene_module,
                                           renderer_module=renderer_module, snapshot=Path(source["snapshot"]),
                                           directory=target, manifest_path=target / "scene_manifest.json",
                                           context=context, input_copy_seconds=copy_seconds)
                    result["profiling_enabled"] = True
                manifest_doc = json.loads(Path(result["manifest_path"]).read_text(encoding="utf-8"))
                result.update({"repeat": repeat_index,
                               "packet_sha256": manifest_doc["packet"]["sha256"],
                               "packet_bytes": manifest_doc["packet"]["bytes"],
                               "output_directory": str(target)})
                files, output_bytes = tree_inventory(temp_root)
                if output_bytes > MAX_TEMP_BYTES:
                    raise RuntimeError(f"Temporary output exceeded 512 MiB after {context} repeat {repeat_index}")
                result.update({"output_file_count_after_run": files,
                               "output_logical_bytes_after_run": output_bytes})
                repeated.append(result)
            context_results[context] = {"source_snapshot": str(source["snapshot"]),
                                        "source_snapshot_sha256": source["snapshot_sha256"],
                                        "identical_packet_sha256": repeated[0]["packet_sha256"] == repeated[1]["packet_sha256"],
                                        "runs": repeated}

        after_inputs: dict[str, str] = {}
        for path, expected in before_inputs.items():
            add_input(after_inputs, path, expected)
        unchanged = before_inputs == after_inputs
        if not unchanged:
            raise RuntimeError("One or more pinned source inputs changed during benchmark")

        # Summarize profile work by exact source file and operations of interest.
        profile_groups = {"font_module": [], "asset_module": [], "renderer_module": [],
                          "scene_module": [], "focused_functions": []}
        for context, result in context_results.items():
            for run in result["runs"]:
                for row in run.get("profile_top", []):
                    if row["file"].endswith("ui_bitmap_fonts.py"):
                        profile_groups["font_module"].append(row)
                    elif row["file"].endswith("civ5_ui_assets.py"):
                        profile_groups["asset_module"].append(row)
                    elif row["file"].endswith("render_ui_popup.py"):
                        profile_groups["renderer_module"].append(row)
                    elif row["file"].endswith("ui_pixel_scene.py"):
                        profile_groups["scene_module"].append(row)
                profile_groups["focused_functions"].extend(run.get("profile_focus", []))
        report = {"status": "PASS_UI_PREPARATION_BENCHMARK",
                  "run_id": run_id, "source_run_id": SOURCE_RUN,
                  "scope": "render_ui_popup.prepare only; no Host, GameCore, SDK, or native game run",
                  "timing_note": "pack_hash_seconds is summed per-call elapsed time; with concurrent hashing, calls may overlap and this sum is not wall-clock time",
                  "contexts": context_results,
                  "measured_operations": totals,
                  "profile_groups": profile_groups,
                  "input_sha256_before": before_inputs,
                  "input_sha256_after": after_inputs,
                  "inputs_unchanged": unchanged,
                  "temporary_output": {"path": str(temp_root), "file_count": tree_inventory(temp_root)[0],
                                       "logical_bytes": tree_inventory(temp_root)[1],
                                       "limit_bytes": MAX_TEMP_BYTES,
                                       "equivalent_source_scenes_logical_bytes": reference_bytes,
                                       "removed_after_measurement": False}}
        # Final input hashes were just verified; cleanup is limited to this newly
        # created exact task folder under Build/UiPreparationBenchmark.
        inventory_files, inventory_bytes = tree_inventory(temp_root)
        if inventory_bytes > MAX_TEMP_BYTES:
            raise RuntimeError("Temporary output exceeded 512 MiB before cleanup")
        resolved_root = temp_root.absolute()
        if resolved_root.parent != build_parent.absolute() or resolved_root.name != run_id:
            raise RuntimeError("Refusing to remove a path outside the exact benchmark folder")
        shutil.rmtree(resolved_root)
        if resolved_root.exists():
            raise RuntimeError("Benchmark temporary output folder remains after cleanup")
        report["temporary_output"].update({"file_count": inventory_files,
                                           "logical_bytes": inventory_bytes,
                                           "removed_after_measurement": True})
        if not build_parent_was_present and not any(build_parent.iterdir()):
            build_parent.rmdir()
        (evidence_dir / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
        print(json.dumps({"status": report["status"], "run_id": run_id,
                          "report": str(evidence_dir / "result.json"),
                          "contexts": {key: {"wall_seconds": [run["wall_seconds"] for run in value["runs"]],
                                             "pack_hash_seconds": value["runs"][1]["pack_hash_seconds"],
                                             "dds_decode_seconds": value["runs"][1]["dds_decode_seconds"]}
                                       for key, value in context_results.items()},
                          "temporary_removed": True}, ensure_ascii=False))
        return 0
    except BaseException as error:
        if temp_root.exists():
            resolved_root = temp_root.absolute()
            if resolved_root.parent == build_parent.absolute() and resolved_root.name == run_id:
                shutil.rmtree(resolved_root)
        if not build_parent_was_present and build_parent.exists() and not any(build_parent.iterdir()):
            build_parent.rmdir()
        failure = {"status": "FAIL_UI_PREPARATION_BENCHMARK", "run_id": run_id,
                   "source_run_id": SOURCE_RUN, "error": f"{type(error).__name__}: {error}",
                   "temporary_output_removed": not temp_root.exists()}
        (evidence_dir / "result.json").write_text(json.dumps(failure, ensure_ascii=False, indent=2) + "\n",
                                                    encoding="utf-8")
        raise


if __name__ == "__main__":
    if sys.argv[1:] == ["--compare-pack-hash-self-test"]:
        raise SystemExit(compare_self_test())
    if sys.argv[1:] == ["--compare-pack-hash"]:
        raise SystemExit(compare_pack_hash_modes())
    if len(sys.argv) == 3 and sys.argv[1] == "--finalize-comparison":
        raise SystemExit(finalize_saved_comparison(sys.argv[2]))
    raise SystemExit(main())
