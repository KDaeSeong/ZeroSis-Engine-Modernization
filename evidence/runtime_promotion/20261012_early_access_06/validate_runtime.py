#!/usr/bin/env python3
"""Bounded static integrity check for the prepared EA 0.6 manual runtime.

This validator reads manifests, frozen build inputs, and artifact hashes only.
It never starts the native game or changes project source, launchers, or docs.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


PROJECT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
RUN_ID = "20261012T121847Z_732a6d5f07ea"
UI_SOURCE_RUN = "20261011T124731Z_b821f4b6c26a"
HOST_BUILD_ID = "20261011T124501Z_5bf7bf678d40"
RUNTIME_ROOT = PROJECT / "Build/InteractiveGameRuntime"
RUN_EVIDENCE = PROJECT / "evidence/interactive_game" / RUN_ID
UI_SOURCE_EVIDENCE = PROJECT / "evidence/interactive_game" / UI_SOURCE_RUN
HOST_BUILD_EVIDENCE = PROJECT / "evidence/ui_window_host" / HOST_BUILD_ID


class ValidationError(RuntimeError):
    pass


def need(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def read_json(path: Path) -> dict:
    need(path.is_file(), f"Missing JSON artifact: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def artifact(path: Path) -> dict:
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": digest(path)}


def load_ui_source_contract(strict_resolve: bool) -> dict:
    """Use the interactive runner's existing frozen UI-source verifier."""
    tools = PROJECT / "tools"
    sys.path.insert(0, str(tools))
    spec = importlib.util.spec_from_file_location("ea06_run_interactive_game", tools / "run_interactive_game.py")
    need(spec is not None and spec.loader is not None, "Could not load existing UI support verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if strict_resolve:
        return module.frozen_ui_support_source(UI_SOURCE_RUN)
    # The managed filesystem denies Win32 final-path resolution for workspace
    # files, while ordinary reads and hashes are allowed. The selected source
    # paths are also checked against their known run roots and recorded hashes.
    original_resolve = Path.resolve
    try:
        def workspace_lexical_resolve(self: Path, strict: bool = False) -> Path:
            is_junction = getattr(self, "is_junction", lambda: False)
            if self.is_symlink() or is_junction():
                raise ValidationError(f"Reparse point in frozen UI support path: {self}")
            if strict and not self.exists():
                raise FileNotFoundError(self)
            return self.absolute()
        Path.resolve = workspace_lexical_resolve
        return module.frozen_ui_support_source(UI_SOURCE_RUN)
    finally:
        Path.resolve = original_resolve


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict-resolve", action="store_true",
                        help="Use the existing verifier with normal strict Path.resolve behavior")
    parser.add_argument("--output", default="runtime_validation.json",
                        help="Write the report to a JSON filename inside this evidence directory")
    args = parser.parse_args()
    output_name = Path(args.output)
    if output_name.name != args.output or output_name.suffix.lower() != ".json":
        parser.error("--output must be a JSON filename, not a path")
    report = {
        "schema": 1,
        "status": "FAIL",
        "scope": "STATIC_PREPARED_MANUAL_RUNTIME_INTEGRITY_ONLY",
        "path_resolution_mode": ("STRICT_UI_SOURCE_LEXICAL_CANDIDATE_PATHS" if args.strict_resolve
                                  else "LEXICAL_WITH_REPARSE_GUARD"),
        "strict_ui_source_resolve": args.strict_resolve,
        "recorded_utc": datetime.now(timezone.utc).isoformat(),
        "candidate": {"run_id": RUN_ID},
        "checks": {},
        "limits": [
            "No native executable was started; this report does not prove live UI, gameplay, save/load, or human acceptance.",
            "Retail Civ V save compatibility and full RNG equivalence are outside this static check.",
            ("The existing UI-source verifier used normal strict Path.resolve checks; candidate runtime path comparisons remain lexical absolute-path and hash checks." if args.strict_resolve else
             "UI-source validation used lexical paths with a reparse-point guard because this sandbox denied Win32 final-path resolution; candidate runtime path comparisons are lexical absolute-path and hash checks. Run with --strict-resolve for strict UI-source canonical-path proof."),
        ],
    }
    try:
        runtime = (RUNTIME_ROOT / RUN_ID).absolute()
        request_path = RUN_EVIDENCE / "request.json"
        request = read_json(request_path)
        need(request.get("run_id") == RUN_ID, "Prepared request run ID mismatch")
        need(Path(request.get("cwd", "")).absolute() == runtime, "Prepared request cwd differs from its runtime")
        need(request.get("smoke") is False, "Candidate request is not smoke=false")
        need(not request.get("resume_from") and not request.get("resume_from_run"),
             "Candidate request unexpectedly resumes another run")
        need(request.get("input_profile") == "MANUAL_CONTINUOUS_GAME_LOOP", "Candidate is not the manual loop profile")
        for flag in ("decisions", "research_tree", "game_menu_smoke", "trade_route_smoke", "social_policy_smoke",
                     "social_policy_tenets", "economic_overview_smoke", "tech_award", "unit_actions",
                     "combat_smoke", "city_capture_smoke", "worker_build"):
            need(request.get(flag) in (False, None), f"Manual request has fixture flag enabled: {flag}")
        need(request.get("stage_or_mods_changed") is False, "Candidate reports Stage or MODS changed")
        report["candidate"].update({
            "request": artifact(request_path),
            "runtime": str(runtime),
            "input_profile": request["input_profile"],
            "smoke": request["smoke"],
            "resume_from": request.get("resume_from"),
            "stage_or_mods_changed": request["stage_or_mods_changed"],
        })
        report["checks"]["manual_request"] = "PASS"

        # The Host executable is checked against the exact frozen UI host build.
        host_build_path = HOST_BUILD_EVIDENCE / "build_result.json"
        host_build = read_json(host_build_path)
        need(host_build.get("build_id") == HOST_BUILD_ID, "Frozen Host build ID mismatch")
        need(host_build.get("status") == "UI_WINDOW_HOST_CANDIDATE_BUILT", "Frozen Host build did not pass")
        source_host = Path(host_build["executable"]["path"]).absolute()
        runtime_host = runtime / "ZeroSisHost_x64.exe"
        expected_host_sha = host_build["executable"]["sha256"]
        need(digest(source_host) == expected_host_sha, "Frozen Host executable differs from its build record")
        need(digest(runtime_host) == expected_host_sha, "Manual runtime Host differs from the frozen Host build")
        report["checks"]["host"] = {
            "status": "PASS", "build_id": HOST_BUILD_ID,
            "source": artifact(source_host), "runtime": artifact(runtime_host),
        }

        # Compare every project-source header frozen for this Host build with
        # both its recorded digest and the current source file.
        header_rows = [row for row in host_build.get("compiler_inputs", [])
                       if row.get("root_name") == "project"
                       and row.get("relative_path", "").replace("/", "\\").startswith("Source\\")
                       and row.get("relative_path", "").lower().endswith(".h")]
        need(bool(header_rows), "Frozen Host record contains no project header inputs")
        checked_headers = []
        for row in header_rows:
            frozen = Path(row["path"]).absolute()
            source = Path(row["original_path"]).absolute()
            expected = row["sha256"]
            need(digest(frozen) == expected, f"Frozen header changed: {row['relative_path']}")
            need(digest(source) == expected, f"Frozen header differs from current source: {row['relative_path']}")
            checked_headers.append({"relative_path": row["relative_path"], "sha256": expected})
        report["checks"]["frozen_project_headers"] = {
            "status": "PASS", "count": len(checked_headers), "all_frozen_equal_current_source": True,
            "rows": checked_headers,
        }

        # Validate the exact runtime input inventory and the sealed bundle manifest.
        input_rows = request.get("runtime_inputs")
        need(isinstance(input_rows, list) and bool(input_rows), "Request runtime_inputs is not a nonempty list")
        names = [Path(row["path"]).name for row in input_rows]
        need(len(names) == len(set(names)), "Duplicate names in request runtime_inputs")
        actual_rows = []
        for row in input_rows:
            target = Path(row["path"]).absolute()
            need(target.parent == runtime, f"Runtime input escaped candidate directory: {target.name}")
            actual_hash = digest(target)
            actual_size = target.stat().st_size
            need(actual_hash == row.get("sha256"), f"Request input hash mismatch: {target.name}")
            if isinstance(row.get("bytes"), int):
                need(actual_size == row["bytes"], f"Request input size mismatch: {target.name}")
            actual_rows.append({"name": target.name, "bytes": actual_size, "sha256": actual_hash})
        manifest_path = runtime / "bundle.manifest"
        expected_manifest = "ZEROSIS_HOST_BUNDLE_V4\n" + "".join(
            f"{Path(row['path']).name}|{row['sha256']}\n" for row in input_rows
            if Path(row["path"]).name != "bundle.manifest")
        need(manifest_path.read_text(encoding="ascii") == expected_manifest,
             "Runtime bundle.manifest differs from request runtime_inputs")
        materializations = request.get("materializations", [])
        need(isinstance(materializations, list), "Request materializations is not a list")
        material_by_target = {Path(row.get("target", "")).absolute(): row for row in materializations}
        need(len(material_by_target) == len(materializations), "Duplicate materialization targets")
        input_by_target = {Path(row["path"]).absolute(): row for row in input_rows}
        for target, material in material_by_target.items():
            row = input_by_target.get(target)
            need(row is not None and material.get("sha256", row.get("sha256")) == row.get("sha256"),
                 f"Materialization inventory mismatch: {target.name}")
            need(digest(target) == row.get("sha256"), f"Materialized input bytes differ: {target.name}")
            if "read_only" in material:
                need(material["read_only"] is True, f"Runtime materialization is not read-only: {target.name}")
        report["checks"]["runtime_input_manifest"] = {
            "status": "PASS", "count": len(actual_rows), "bundle_manifest": artifact(manifest_path),
            "materialization_count": len(materializations), "rows": actual_rows,
        }

        # Existing PASS UI-source verification plus candidate-copy comparison.
        source_contract = load_ui_source_contract(args.strict_resolve)
        source_result = read_json(UI_SOURCE_EVIDENCE / "result.json")
        source_request_path = UI_SOURCE_EVIDENCE / "request.json"
        support_record_path = RUN_EVIDENCE / "interactive_ui_support.json"
        support_record = read_json(support_record_path)
        copied = support_record.get("copied_from_run", {})
        need(copied.get("run_id") == UI_SOURCE_RUN and copied.get("status") == source_contract["status"],
             "Candidate UI support points to a different source run or status")
        for key in ("result_sha256", "request_sha256", "support_record_sha256", "support_manifest_sha256"):
            expected = source_contract[key]
            need(copied.get(key) == expected, f"Candidate UI support source pin differs: {key}")
        need(source_result.get("status") == source_contract["status"] and source_result.get("failures") == [],
             "Frozen UI source run is not a clean PASS")
        candidate_manifest_ref = support_record.get("frozen_support_manifest", {})
        candidate_manifest_path = Path(candidate_manifest_ref.get("path", "")).absolute()
        need(candidate_manifest_path == runtime / "interactive_ui_support/support_manifest.json",
             "Candidate support manifest escaped the runtime support folder")
        candidate_manifest = read_json(candidate_manifest_path)
        candidate_inventory = request.get("interactive_ui_support_inventory", {})
        source_files = source_contract["files"]
        frozen_names = list(source_files)
        for name in frozen_names:
            source_sha = source_files[name]["sha256"]
            if name in ("inline_icons", "asset_preparation_provenance"):
                row = support_record[name]
                manifest_row = candidate_manifest[name]
                inventory_row = candidate_inventory[name]
            else:
                row = support_record["tools"][name]
                manifest_row = candidate_manifest["tools"][name]
                inventory_row = candidate_inventory["tools"][name]
            frozen_ref = row.get("frozen", {})
            frozen_path = Path(frozen_ref.get("path", "")).absolute()
            need(frozen_ref.get("sha256") == source_sha and digest(frozen_path) == source_sha,
                 f"Candidate frozen UI support differs from PASS source: {name}")
            need(manifest_row.get("sha256") == source_sha and digest(Path(manifest_row["path"]).absolute()) == source_sha,
                 f"Candidate support manifest entry differs from PASS source: {name}")
            need(inventory_row.get("frozen", {}).get("sha256") == source_sha,
                 f"Candidate request support inventory differs from PASS source: {name}")
        need(candidate_manifest_ref.get("sha256") == candidate_inventory.get("frozen_support_manifest", {}).get("sha256"),
             "Candidate support manifest request pin differs")
        need(digest(candidate_manifest_path) == candidate_manifest_ref["sha256"],
             "Candidate support manifest hash differs from its request")
        need(request.get("ui_support_from_run", {}).get("run_id") == UI_SOURCE_RUN,
             "Request does not name the approved frozen UI source run")
        report["checks"]["frozen_ui_support"] = {
            "status": "PASS", "source_run": UI_SOURCE_RUN, "source_status": source_contract["status"],
            "source_result": artifact(UI_SOURCE_EVIDENCE / "result.json"),
            "source_request": artifact(source_request_path),
            "candidate_support_record": artifact(support_record_path),
            "candidate_manifest": artifact(candidate_manifest_path),
            "verified_components": frozen_names,
        }

        # Compare every non-Host, non-manifest runtime asset with the passing UI source run.
        source_request = read_json(source_request_path)
        source_inputs = {Path(row["path"]).name: row for row in source_request["runtime_inputs"]}
        current_inputs = {Path(row["path"]).name: row for row in input_rows}
        shared_names = sorted((set(source_inputs) & set(current_inputs)) - {"ZeroSisHost_x64.exe", "bundle.manifest"})
        need(shared_names, "No shared runtime inputs found for comparison")
        shared_rows = []
        for name in shared_names:
            left, right = source_inputs[name], current_inputs[name]
            need(left.get("sha256") == right.get("sha256"), f"Shared runtime input hash changed: {name}")
            source_file = Path(left["path"]).absolute()
            runtime_file = Path(right["path"]).absolute()
            need(digest(source_file) == digest(runtime_file) == right["sha256"], f"Shared runtime bytes differ: {name}")
            shared_rows.append({"name": name, "bytes": runtime_file.stat().st_size, "sha256": right["sha256"]})
        report["checks"]["shared_runtime_assets"] = {
            "status": "PASS", "source_run": UI_SOURCE_RUN, "count": len(shared_rows), "rows": shared_rows,
        }

        report["status"] = "PASS"
    except Exception as exc:  # retain a compact, reviewable failure record
        report["failure"] = f"{type(exc).__name__}: {exc}"
    report["validator"] = artifact(Path(__file__))
    out_path = OUT / output_name.name
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "path": str(out_path),
                      "failure": report.get("failure")}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
