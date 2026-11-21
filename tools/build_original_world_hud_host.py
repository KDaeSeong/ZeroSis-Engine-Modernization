"""Build one sealed original-HUD Host; --preflight only reads authenticated inputs.

The old five-TU recipes are relocated unchanged. No asset preparation, dependency
discovery, automatic retry, Host/SDK loading, window, or runtime launch is allowed.
"""
from __future__ import annotations

import argparse
import codecs
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import struct
import subprocess
import sys
import types

PROJECT = Path(__file__).absolute().parents[1]
PROFILE = PROJECT / "evidence/original_world_hud/host_build/inputs.json"
PROFILE_SHA = "db8dbd4d0c3e854dda26cf6786f4d34de3fb0b0750a8f8fe2d9b8d764c3ad594"
HELPER_SHA = "07f50b1ab7482591792b44cc8767f27c709884f5f487b0eada7459f28c8da558"
PARENT_ID = "20261024T042219Z_e6399c82ee5c"
PARENT_ROOT = PROJECT / "Build/UiWindowHost" / PARENT_ID
STAGE_ROOT = PROJECT / "evidence/original_world_hud/host_build"
COUNTS = (465, 266, 270, 279, 301)
CHANGED = frozenset(("Source/Presentation/WorldViewRenderer.cpp", "Source/Presentation/BitmapWindow.h",
    "Source/Presentation/BitmapWindow.cpp", "Source/Presentation/WorldCameraControls.h", "Source/Host/InteractiveGameLoop.h"))
OPERATIONAL = frozenset(("tools/run_interactive_game.py", "tools/retained_host_runtime_input.py", "tools/prepare_latest_engine_pair.py"))
METADATA = frozenset(("evidence/save_menu/20261013_original_screen/current_progress.json", "docs/M7_RETAIL_SAVE_BOUNDARY.md"))
REFERENCE_NAMES = frozenset(("baseline_build", "baseline_attestation", "baseline_retirement", "source_audit", "component",
    "final_source_audit", "operational_revisions", "metadata_publication", "prepared_request", "prior_pair_final_audit",
    "build_helpers", "static_pe_parser"))


def load_helpers():
    """Authenticate source before evaluating its definitions, never its main."""
    path = PROJECT / "tools/build_native_restore_host.py"
    for parent in (path, *path.parents):
        info = parent.lstat()
        if info.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise RuntimeError("Build helper path contains a reparse point")
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != 44968:
        raise RuntimeError("Frozen build helper size or type differs")
    with path.open("rb") as stream:
        raw = stream.read(44969)
    after = path.stat()
    if (not stat.S_ISREG(before.st_mode) or len(raw) != 44968 or hashlib.sha256(raw).hexdigest() != HELPER_SHA or
        (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_file_attributes) !=
        (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_file_attributes)):
        raise RuntimeError("Frozen build helper differs")
    module = types.ModuleType("zerosis_original_hud_host_build_helpers")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def artifacts(value):
    if isinstance(value, dict):
        if isinstance(value.get("path"), str) and isinstance(value.get("sha256"), str):
            yield value
        for child in value.values():
            yield from artifacts(child)
    elif isinstance(value, list):
        for child in value:
            yield from artifacts(child)


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--preflight", action="store_true", help="Validate the sealed graph without writes or children")
    options = cli.parse_args()
    if os.name != "nt" or not sys.dont_write_bytecode or sys.flags.optimize:
        raise RuntimeError("Use normal Windows Python -B")
    if any(value for name, value in os.environ.items() if name.upper() in ("CL", "_CL_", "LINK")):
        raise RuntimeError("Inherited CL/_CL_/LINK options are forbidden before any child")
    for encoding in ("mbcs", "utf-8-sig", "utf-8", "ascii"):
        codecs.lookup(encoding)
    gzip.compress(b"warm", mtime=0)
    n = load_helpers()
    scope = n.Scope()
    require, key = n.require, n.key

    def pair(row):
        return key(row["path"]), row["sha256"]

    def same(left, right):
        return pair(left) == pair(right) and left.get("bytes") == right.get("bytes")

    def sealed(row):
        value = dict(row)
        identity = value.get("file_identity")
        if isinstance(identity, str) and re.fullmatch(r"\d+:\d+", identity):
            value["file_identity"] = [int(item) for item in identity.split(":")]
        return scope.sealed(value)

    tool = scope.ref(Path(__file__).absolute())
    profile_ref = n.pin(scope, PROFILE, PROFILE_SHA, 4795)
    profile = scope.json(PROFILE)
    require(profile.get("schema") == "zerosis.original_world_hud.host_build_inputs.v1" and
        profile["baseline_build_id"] == PARENT_ID and set(profile["references"]) == REFERENCE_NAMES and
        set(profile["changed_production_paths"]) == CHANGED and len(profile["changed_production_paths"]) == 5 and
        (profile["compiler_dependency_count"], profile["source_manifest_count"], profile["current_source_count"],
         profile["protected_artifact_count"]) == (549, 85, 592, 1961) and tuple(profile["dependency_counts"]) == COUNTS and
        profile["historical_exception_counts"] == dict(production_sources=5, operational_sources=3, metadata=2) and
        profile["source_files_added"] == 0 and profile["source_file_count_changed"] is False and
        profile["planned_direct_children"] == 7 and profile["copied_source_limit_bytes"] == 524288 and
        all(profile[name] is False for name in ("library_or_import_or_ui_payload_changes_allowed", "host_sdk_or_window_execution_allowed",
            "complete_runtime_or_asset_copies_allowed", "default_promotion_allowed", "full_engine_goal_complete")), "Build authority differs")
    refs = {name: sealed(row) for name, row in profile["references"].items()}
    require(refs["build_helpers"]["sha256"] == HELPER_SHA and key(refs["build_helpers"]["path"]) == key(n.__file__) and
        key(refs["static_pe_parser"]["path"]) == key(n.PARSER) and refs["static_pe_parser"]["sha256"] == n.PARSER_SHA,
        "Authenticated helper locations differ")
    documents = {name: scope.json(row["path"]) for name, row in refs.items() if name not in ("build_helpers", "static_pe_parser")}
    base, audit, retirement = (documents[name] for name in ("baseline_build", "baseline_attestation", "baseline_retirement"))
    require(base["status"] == "UI_WINDOW_HOST_CANDIDATE_BUILT" and base["build_id"] == PARENT_ID and
        len(base["compiler_inputs"]) == 549 and len(base["sources"]) == 85 and len(base["current_source_inputs"]) == 592 and
        len(base["protected_artifacts"]) == 1961 and len(base["implicit_libraries"]) == 8 and
        audit["status"] == "PASS_CURRENT_NATIVE_RESTORE_HOST_STATIC_ATTESTATION" and same(audit["build_result"], refs["baseline_build"]) and
        audit["compiler_dependency_union"] == 549 and audit["source_manifest_verified"] == 85 and audit["current_inputs_verified"] == 592 and
        audit["protected_artifacts_verified"] == 1961 and audit["host_or_sdk_or_window_executed"] is False,
        "Retained parent inventory or attestation differs")
    require(retirement["status"] == "PASS_VERIFIED_CURRENT_HOST_INTERMEDIATES_RETIRED" and
        retirement["all_targets_absent"] is True and retirement["deleted_files"] == 6 and
        retirement["host_sdk_or_ui_executed"] is False and same(retirement["independent_static_attestation"], refs["baseline_attestation"]) and
        same(retirement["executable"], base["executable"]), "Parent retirement differs")
    plan = scope.json(sealed(retirement["plan"])["path"])
    old_run = scope.json(sealed(audit["run"])["path"])
    require(plan["schema"] == "zerosis.native_restore.host_intermediate_retirement_plan.v1" and plan["target_files"] == 6 and
        same(plan["build_result"], refs["baseline_build"]) and same(plan["executable"], base["executable"]) and
        old_run["status"] == "PASS_CURRENT_NATIVE_RESTORE_HOST_BUILD_ONLY" and same(old_run["build_result"], refs["baseline_build"]),
        "Parent retained-object provenance differs")
    units = base["final_compilation"]["translation_units"]
    require(tuple(row["translation_unit"] for row in units) == n.UNITS and len(old_run["actual_objects"]) == len(audit["units"]) == 5,
        "Parent TU inventory differs")
    targets = {key(row["path"]): row for row in plan["targets"]}
    retired, expected_targets = {}, {key(PARENT_ROOT / "read_build_environment.cmd")}
    for index, (row, obj, attested, name, stem) in enumerate(zip(units, old_run["actual_objects"], audit["units"], n.UNITS, n.STEMS)):
        path = PARENT_ROOT / f"final/tu_{index:02d}_{name}/obj/{stem}.obj"
        require(key(row["object"]["path"]) == key(path) and same(row["object"], obj) and same(obj, targets[key(path)]) and
            row["returncode"] == attested["returncode"] == 0 and attested["coff_machine"] == "0x8664" and
            attested["object_bytes"] == obj["bytes"] and attested["dependencies"] == COUNTS[index], "Parent object proof differs")
        retired[pair(obj)] = obj
        expected_targets.add(key(path))
    environment_target = targets[key(PARENT_ROOT / "read_build_environment.cmd")]
    require(set(targets) == expected_targets and {key(path) for path in retirement["deleted_paths"]} == expected_targets and
        environment_target["bytes"] == 140 and environment_target["sha256"] == "fbea552a6bb1afe675455702d2bcb52b666cb58115922a59f508f1cefc0e55bf" and
        not any(os.path.lexists(path) for path in expected_targets), "Unexpected or present parent retirement target")

    changed = {key(PROJECT / relative) for relative in CHANGED}
    old_inputs = {key(row["original_path"]): row for row in base["compiler_inputs"]}
    current_before = {key(row["path"]): row for row in base["current_source_inputs"]}
    protected_before = {pair(row): row for row in base["protected_artifacts"]}
    require(len(old_inputs) == 549 and len(current_before) == 592 and changed <= set(old_inputs) & set(current_before), "Parent input identities differ")
    historical, revisions, current = {}, [], {}

    def recover(before, backup, category, after):
        require(pair(before) not in historical and pair(before) in protected_before and same(before, protected_before[pair(before)]),
            "Historical exception is not anchored in the parent protected graph")
        annotation = n.historical(scope, backup, before)
        actual = sealed(after)
        require(key(actual["path"]) == key(before["path"]), "Historical replacement path differs")
        historical[pair(before)] = before
        return dict(category=category, before=annotation, after=actual)

    source = documents["source_audit"]
    require(source["status"] == "PASS_FIVE_PRODUCTION_SOURCE_CHANGES_BACKED_AND_COMPONENT_COMPILE_VERIFIED" and
        source["anchored_prior_build"] == PARENT_ID and len(source["changes"]) == 5 and
        {key(row["before"]["path"]) for row in source["changes"]} == changed, "Five-source authority differs")
    for revision in source["changes"]:
        before, after = revision["before"], revision["after"]
        path = key(before["path"])
        require(same(before, dict(old_inputs[path], path=before["path"])) and same(before, current_before[path]) and
            n.within(revision["backup"]["path"], PROJECT / "evidence/original_world_hud/source_backups"), "Source before differs from e639")
        value = recover(before, revision["backup"], "production_source", after)
        revisions.append(value)
        current[path] = value["after"]
    require(sum(row["bytes"] for row in current.values()) <= profile["copied_source_limit_bytes"], "Changed source copies exceed the bound")
    operational = documents["operational_revisions"]
    require(operational["schema"] == "zerosis.native_restore.operational_revisions.v1" and operational["build_id"] == PARENT_ID,
        "Operational revision ledger schema differs")
    require(same(operational["build_result"], refs["baseline_build"]) and len(operational["revisions"]) == 3 and
        operational["compiled_host_sources_changed"] is False and operational["host_or_sdk_executed"] is False and
        {key(row["before"]["path"]) for row in operational["revisions"]} == {key(PROJECT / path) for path in OPERATIONAL},
        "Operational revision authority differs")
    compiled_paths = set(old_inputs) | set(current_before) | {key(row["original_source"]) for row in base["sources"]}
    operational_recovery = []
    for revision in operational["revisions"]:
        require(key(revision["before"]["path"]) not in compiled_paths and
            n.within(revision["backup"]["path"], PROJECT / "evidence/native_restore_contract/pair_preparation/source_backups"),
            "Operational exception overlaps the compiled closure or escapes its backup root")
        operational_recovery.append(recover(revision["before"], revision["backup"], "operational_source", revision["after"]))
    publication = documents["metadata_publication"]
    require(publication["status"] == "PASS_CURRENT_RESTORE_HOST_PROOF_PUBLISHED_WITHOUT_RUNTIME_PROMOTION" and
        same(publication["build_result"], refs["baseline_build"]) and len(publication["changed_metadata"]) == 2 and
        {key(row["before"]["path"]) for row in publication["changed_metadata"]} == {key(PROJECT / path) for path in METADATA},
        "Historical documentation authority differs")
    metadata_recovery = []
    for revision in publication["changed_metadata"]:
        before = revision["before"]
        require(revision["gzip_roundtrip_verified"] is True and key(before["path"]) not in compiled_paths and
            n.within(revision["backup"]["path"], PROJECT / "evidence/native_restore_contract/publication"), "Historical documentation backup differs")
        metadata_recovery.append(recover(before, revision["backup"], "metadata", scope.ref(before["path"])))
    require(len(historical) == 10, "Historical exception inventory differs")
    inherited_metadata = []
    require(len(base["historical_metadata_recovery"]) == 2, "Inherited b9 documentation inventory differs")
    for row in base["historical_metadata_recovery"]:
        require(key(row["original_path"]) in {key(PROJECT / path) for path in METADATA}, "Inherited documentation path differs")
        inherited_metadata.append(n.historical(scope, row["backup"], dict(path=row["original_path"], bytes=row["bytes"], sha256=row["sha256"])))

    historical_visits, retired_visits = set(), set()
    for row in artifacts(base):
        identifier = pair(row)
        if identifier in historical:
            require(row.get("bytes") == historical[identifier]["bytes"], "Historical byte count differs")
            historical_visits.add(identifier)
        elif identifier in retired:
            require(row.get("bytes") == retired[identifier]["bytes"], "Retired object byte count differs")
            retired_visits.add(identifier)
        else:
            sealed(row)
    require(historical_visits == set(historical) and retired_visits == set(retired), "Unconsumed historical source or retired object")
    live = {path: current[path] if path in current else sealed(row) for path, row in current_before.items()}
    require(len(live) == 592, "Current source count differs")
    component, final_audit = documents["component"], documents["final_source_audit"]
    require(component["status"] == "PASS_ORIGINAL_WORLD_HUD_SOFTWARE_COMPONENT_O2_OD" and
        {row["mode"] for row in component["modes"]} == {"O2", "Od"} and component["host_or_sdk_or_window_executed"] is False and
        final_audit["status"] == "PASS_ORIGINAL_WORLD_HUD_SOURCE_COMPONENT_PUBLICATION_AND_CLEANUP_AUDIT" and
        final_audit["production_sources_rehashed"] == final_audit["changed_source_backup_roundtrips_verified"] == 5 and
        final_audit["current_host_main_and_window_compile_only_passed"] is True and final_audit["host_or_sdk_or_window_executed"] is False,
        "Current component or syntax proof differs")
    for row in component["protected_inputs_unchanged"]:
        sealed(row)
    for row in component["actual_current_host_main_and_bitmap_window_syntax"]:
        require(row["returncode"] == 0, "Current production syntax compile failed")
        for name in ("exact_prior_response", "current_response", "log"):
            sealed(row[name])
    previous_component = scope.json(sealed(base["native_restore_contract_component"])["path"])
    toolchain = set()
    for row in previous_component["inputs"]:
        name = Path(row["path"]).name.casefold()
        if name in {"cl.exe", "c1xx.dll", "c2.dll", "link.exe", "vcvars64.bat"}:
            require(n.within(row["path"], n.VS), "Compiler input escaped its root")
            sealed(row)
            toolchain.add(name)
    require(toolchain == {"cl.exe", "c1xx.dll", "c2.dll", "link.exe", "vcvars64.bat"}, "Compiler frontend inventory differs")
    request, pair_audit = documents["prepared_request"], documents["prior_pair_final_audit"]
    require(request["run_id"] == pair_audit["run_id"] == "20261024T050152Z_fd0465b26387" and
        pair_audit["status"] == "PASS_CURRENT_RESTORE_PAIR_PUBLICATION_AND_RETAINED_INPUTS_AUDIT" and
        pair_audit["current_host_or_sdk_executed"] is False and len(request["runtime_inputs"]) == 24 and
        key(request["cwd"]) == key(PROJECT / "Build/InteractiveGameRuntime" / request["run_id"]), "Current prepared-pair protection differs")
    runtime = []
    for row in request["runtime_inputs"]:
        require(n.within(row["path"], Path(request["cwd"])), "Prepared input escaped its retained runtime")
        runtime.append(sealed(row))

    old_frozen = {key(row["path"]): row for row in base["compiler_inputs"]}
    donors = {}
    for group in ("compiler_inputs", "sources", "provider_inputs", "system_libraries", "build_tools", "implicit_libraries"):
        for row in base[group]:
            require(n.within(row["path"], PARENT_ROOT / "frozen"), "Frozen donor escaped e639")
            donors[key(row["path"])] = sealed(row)
    for row in [*base["provider_reports"].values(), base["ui_assets"]]:
        require(n.within(row["path"], PARENT_ROOT / "frozen"), "Frozen metadata donor escaped e639")
        donors[key(row["path"])] = sealed(row)
    require(len(donors) == 592 and len(old_frozen) == 549, "Frozen donor union differs")
    require(key(base["shared_lua_build"]["path"]) in donors and
        same(base["shared_lua_build"], donors[key(base["shared_lua_build"]["path"])]),
        "Shared Lua metadata is not already one of the sealed 592 donors")
    old_deps, response_texts = {}, {}
    for index, row in enumerate(units):
        paths, _ = n.dependencies(scope, row["dependency_report"])
        require(paths <= set(old_frozen) and len(paths) == COUNTS[index], "Parent TU dependency closure differs")
        old_deps[n.UNITS[index]] = paths
        sealed(row["response"])
        response_texts[n.UNITS[index]] = scope.read(row["response"]["path"], 16384).decode("utf-8-sig")
    require(set.union(*old_deps.values()) == set(old_frozen), "Parent compiler dependency union differs")
    require({row["name"].casefold() for row in base["implicit_libraries"]} ==
        {"msvcrt.lib", "msvcprt.lib", "vcruntime.lib", "oldnames.lib", "bcrypt.lib", "kernel32.lib", "ucrt.lib", "uuid.lib"},
        "Frozen UUID-inclusive library inventory differs")
    link_text = scope.read(base["link_response"]["path"], 16384).decode("utf-8-sig")
    parser = n.parser_module(scope)
    generated = PROJECT / "Source/Host/UiPopupAssets.generated.h"
    generated_ref = n.pin(scope, generated, "333cf40c942e2545c83372084ed276e2aec11ab9fd7cbf4744f8c0c4e7c48da9")
    arrays, order = parser.parse_catalog(scope.read(generated, 32 * 1024 * 1024))
    previous_pe = parser.PE(scope.read(base["executable"]["path"], 32 * 1024 * 1024))
    previous_catalog = n.catalog_summary(previous_pe.catalog(arrays, order))
    previous_imports = previous_pe.imports()
    require(previous_catalog == base["catalog"] == audit["catalog"] and previous_catalog["entry_count"] == 67 and
        previous_catalog["ordered_payload_manifest_sha256"] == "db76873a3dff1360b89a4b57cc6c0da51893ace2efb234c5f83b739227bb411c" and
        len(previous_imports) == len(set(previous_imports)) == 24 and set(previous_imports) == set(base["imports"]["dependencies"]) and
        previous_pe.occurrences(n.MARKER) == [audit["restore_contract_marker"]["rva"]], "Parent PE/payload/marker provenance differs")
    cmd_key = key(Path(r"C:\Windows\System32\cmd.exe"))
    require(cmd_key in scope.rows, "Command interpreter is absent from the sealed parent inputs")
    cmd_row = scope.rows[cmd_key]
    cmd = Path(cmd_row["path"])
    sealed(cmd_row)
    scope.ref(n.VCVARS)
    signature = hashlib.sha256((PROFILE_SHA + "|" + "|".join(refs[name]["sha256"] for name in
        ("source_audit", "component", "final_source_audit"))).encode("ascii")).hexdigest()[:20]
    stage = STAGE_ROOT / signature
    identifier = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ_") + signature[:12]
    build = PROJECT / "Build/UiWindowHost" / identifier
    output = PROJECT / "evidence/ui_window_host" / identifier
    for path in (stage, build, output):
        n.ordinary(path, file=False)
        require(not os.path.lexists(path), "Single-use semantic attempt already exists; do not repeat compilation")
    require(shutil.disk_usage(PROJECT).free >= 384 * 1024 * 1024, "Insufficient space for the bounded build")
    scope.stable()
    if options.preflight:
        print(json.dumps(dict(status="PASS_CURRENT_ORIGINAL_WORLD_HUD_HOST_PREFLIGHT", signature=signature,
            compiler_dependency_count=549, source_manifest_count=85, current_source_count=592, changed_sources=5, added_headers=0,
            frozen_donors=592, planned_hardlinks=587, planned_source_copies=5, source_copy_bytes=sum(row["bytes"] for row in current.values()),
            planned_child_commands=7, historical_exception_counts=profile["historical_exception_counts"], unique_pinned_inputs=len(scope.rows),
            created_files=0, child_commands=0, host_or_sdk_or_window_executed=False, full_engine_goal_complete=False)))
        return 0

    scope.roots = (build, stage, output)
    scope.parents = {key(STAGE_ROOT)}
    stage.mkdir(); build.mkdir(); output.mkdir()
    preflight_protected = list(scope.rows.values())
    replacements = {pair(dict(row["before"], path=row["before"]["original_path"])): row["after"]
        for row in [*revisions, *operational_recovery, *metadata_recovery]}
    protected = [replacements[pair(row)] if pair(row) in replacements else sealed(row) for row in base["protected_artifacts"]]
    require(len(protected) == 1961 and {key(row["path"]) for row in protected} ==
        {key(row["path"]) for row in base["protected_artifacts"]}, "Current protected graph differs")
    materialized, completed, objects = {}, [], []
    commands = scope.commands

    def relocate(path):
        require(n.within(path, PARENT_ROOT), "Relocation escaped the successful parent")
        return build / Path(path).relative_to(PARENT_ROOT)

    def replace_root(text):
        value = text.replace(str(PARENT_ROOT), str(build)).replace(PARENT_ROOT.as_posix(), build.as_posix())
        require(str(PARENT_ROOT) not in value and PARENT_ROOT.as_posix() not in value, "Parent root remains in a response")
        return value

    def freeze(row, source_path=None):
        target = relocate(row["path"])
        if key(target) in materialized:
            return materialized[key(target)]
        n.ordinary(target, file=False)
        target.parent.mkdir(parents=True, exist_ok=True)
        if source_path is None:
            require(key(row["path"]) in donors, "Unregistered frozen donor")
            scope.links[key(target)] = key(row["path"])
            os.link(row["path"], target)
            method = "attested_snapshot_hardlink"
            expected = row
        else:
            require(key(source_path) in changed, "Unapproved changed source")
            raw = scope.read(source_path, profile["copied_source_limit_bytes"])
            with target.open("xb") as stream:
                stream.write(raw)
            scope.copies.add(key(target)); os.chmod(target, stat.S_IREAD)
            method, expected = "owned_changed_source_copy", current[key(source_path)]
        actual = scope.ref(target)
        require(all(actual[name] == expected[name] for name in ("bytes", "sha256")), "Materialized bytes differ")
        require(source_path is not None or actual["file_identity"] == donors[key(row["path"])]["file_identity"], "Hardlink identity differs")
        require(source_path is None or actual["file_identity"] != current[key(source_path)]["file_identity"], "Changed live source was hardlinked")
        result = {**row, **actual, "materialization": method}
        result.pop("reused_from_path", None)
        if source_path is None:
            result["reused_from_path"] = row["path"]
        materialized[key(target)] = result
        return result

    def execute(command, cwd, log, phase, env=None):
        scope.pending = dict(command=[str(word) for word in command], cwd=str(cwd))
        try:
            result = subprocess.run(scope.pending["command"], cwd=cwd, env=env, capture_output=True,
                timeout=300, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.BELOW_NORMAL_PRIORITY_CLASS)
        except subprocess.TimeoutExpired as error:
            log.write_bytes((error.stderr or b"") if phase == "environment" else (error.stdout or b"") + (error.stderr or b""))
            if commands:
                commands[-1].update(phase=phase, log=scope.ref(log), timed_out=True)
            raise
        finally:
            scope.pending = None
        log.write_bytes(result.stderr if phase == "environment" else result.stdout + result.stderr)
        commands[-1].update(returncode=result.returncode, phase=phase, log=scope.ref(log))
        require(result.returncode == 0, "Child failed; retained log: " + str(log))
        if phase != "environment":
            require(not re.search(r"\bwarning\s+(?:C|LNK)\d+", (result.stdout + result.stderr).decode("mbcs", errors="replace"), re.I),
                "Compiler/linker warning; retained log: " + str(log))
        return result

    try:
        planned = [([str(cmd), "/d", "/c", str(build / "read_build_environment.cmd")], build)]
        planned += [([base["compiler"]["path"], "@" + str(relocate(row["response"]["path"]))], relocate(row["response"]["path"]).parent) for row in units]
        planned += [([base["linker"]["path"], "@" + str(relocate(base["link_response"]["path"]))], relocate(base["link_response"]["path"]).parent)]
        scope.allowed_commands = {(tuple(words), key(cwd)) for words, cwd in planned}
        require(len(scope.allowed_commands) == 7, "Exact child inventory differs")
        started = stage / "started.json"
        n.write(started, dict(schema="zerosis.original_world_hud.host_build_started.v1", utc=datetime.now(timezone.utc).isoformat(),
            signature=signature, build_id=identifier, profile=profile_ref, builder=tool, baseline_build=refs["baseline_build"], proofs=refs,
            current_inputs=list(live.values()), protected_artifacts=preflight_protected, source_revisions=revisions,
            historical_operational_recovery=operational_recovery, historical_metadata_recovery=metadata_recovery,
            inherited_historical_metadata_recovery=inherited_metadata, frozen_donors=list(donors.values()),
            planned_commands=[dict(command=words, cwd=str(cwd)) for words, cwd in planned], no_automatic_retry=True,
            host_or_sdk_or_window_execution_allowed=False, full_engine_goal_complete=False))
        started_ref = scope.ref(started)
        compiler_inputs = [freeze(row, row["original_path"] if key(row["original_path"]) in changed else None) for row in base["compiler_inputs"]]
        sources = [{**freeze(row, row["original_source"] if key(row["original_source"]) in changed else None),
            "original_source": row["original_source"], "relative_path": row["relative_path"]} for row in base["sources"]]
        providers, systems, tools, implicit = ([freeze(row) for row in base[group]] for group in
            ("provider_inputs", "system_libraries", "build_tools", "implicit_libraries"))
        provider_reports = {name: freeze(row) for name, row in base["provider_reports"].items()}
        assets = freeze(base["ui_assets"])
        require(len(materialized) == 592 and sum(row["materialization"] == "owned_changed_source_copy" for row in materialized.values()) == 5 and
            sum(row["bytes"] for row in materialized.values() if row["materialization"] == "owned_changed_source_copy") <= profile["copied_source_limit_bytes"],
            "Materialized donor/copy scope differs")
        setup = build / "read_build_environment.cmd"
        with setup.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(f'@echo off\ncall "{n.VCVARS}" >nul\nif errorlevel 1 exit /b 1\nset\n')
        initialized = execute([cmd, "/d", "/c", setup], build, stage / "environment.stderr.log", "environment")
        env = {name.upper(): value for name, value in os.environ.items()}
        for line in initialized.stdout.decode("mbcs", errors="replace").splitlines():
            if "=" in line and not line.startswith("="):
                name, value = line.split("=", 1); env[name.upper()] = value
        require(not any(env.get(name) for name in ("CL", "_CL_", "LINK")), "Initialized CL/_CL_/LINK options are forbidden")
        compiler = shutil.which("cl.exe", path=env.get("PATH"))
        require(compiler is not None and key(compiler) == key(base["compiler"]["path"]), "Initialized compiler differs")
        compiler = base["compiler"]["path"]
        sealed(base["compiler"]); sealed(base["linker"])
        frozen = build / "frozen"
        env["INCLUDE"] = ";".join(str(frozen / "include_roots" / ("system_%02d" % index)) for index in range(len(base["system_include_roots"])))
        env["LIB"] = str(frozen / "implicit_libraries"); env["LIBPATH"] = ""
        (build / "tmp").mkdir(); env["TMP"] = env["TEMP"] = str(build / "tmp"); env["VSLANG"] = "1033"
        closure = {key(row["path"]) for row in compiler_inputs}
        library_names = {row["name"].casefold() for row in implicit} | {Path(row["path"]).name.casefold() for row in providers + systems}
        union = set()
        for index, (name, stem, old) in enumerate(zip(n.UNITS, n.STEMS, units)):
            response, dependency = relocate(old["response"]["path"]), relocate(old["dependency_report"]["path"])
            response.parent.mkdir(parents=True); (response.parent / "obj").mkdir()
            with response.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(replace_root(response_texts[name]))
            response_before = scope.ref(response)
            execute([compiler, "@" + str(response)], response.parent, stage / ("compile_" + name + ".log"), "compile", env)
            sealed(response_before)
            expected = {key(relocate(path)) for path in old_deps[name]}
            actual, visits = n.dependencies(scope, scope.ref(dependency))
            require(actual == expected and actual <= closure and len(actual) == COUNTS[index], "Actual TU dependency set differs: " + name)
            union.update(actual)
            object_path = response.parent / "obj" / (stem + ".obj")
            raw = scope.read(object_path, 64 * 1024 * 1024)
            coff, defaults = parser.coff(raw), n.object_defaults(raw)
            require(coff["machine_hex"] == "0x8664" and set(defaults) <= library_names, "COFF requests an unpinned library")
            row = dict(translation_unit=name, command=[str(compiler), "@" + str(response)], response=scope.ref(response),
                dependency_report=scope.ref(dependency), log=scope.ref(stage / ("compile_" + name + ".log")), object=scope.ref(object_path),
                returncode=0, expected_dependency_count=len(expected), actual_dependency_count=len(actual), dependency_visits=visits,
                default_libraries=defaults, coff_machine=coff["machine_hex"], coff_sections=coff["section_count"])
            completed.append(row); objects.append(row["object"])
            n.write(stage / ("compiled_" + name + ".json"), row)
            print(json.dumps(dict(phase="compiled", translation_unit=name, object_bytes=row["object"]["bytes"])), flush=True)
        require(union == closure and len(closure) == 549 and len(sources) == 85, "Final compiler union differs")
        link_response = relocate(base["link_response"]["path"])
        rewritten = replace_root(link_text)
        linked_objects = re.findall(r'^"([^"\n]+\.obj)"$', rewritten.replace("\r\n", "\n"), re.I | re.M)
        require([key(path) for path in linked_objects] == [key(row["path"]) for row in objects], "Link does not consume exactly the new five objects")
        with link_response.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(rewritten)
        response_before = scope.ref(link_response)
        before_link = [sealed(row) for row in objects]
        execute([base["linker"]["path"], "@" + str(link_response)], link_response.parent, stage / "link.log", "link", env)
        sealed(response_before)
        require([sealed(row) for row in objects] == before_link, "Link changed an object")
        executable, mapfile = relocate(base["executable"]["path"]), relocate(base["map"]["path"])
        pe = parser.PE(scope.read(executable, 32 * 1024 * 1024))
        imports = pe.imports()
        catalog = n.catalog_summary(pe.catalog(arrays, order))
        require(len(imports) == len(set(imports)) == 24 and set(imports) == set(previous_imports), "Actual PE imports differ")
        require(all(catalog[name] == previous_catalog[name] for name in ("entry_count", "stride", "total_payload_bytes", "ordered_payload_manifest_sha256")),
            "New PE changed its exact ordered 67 payloads")
        marker_rvas = pe.occurrences(n.MARKER)
        require(len(marker_rvas) == 1, "New PE lacks the unique read-only restore marker")
        map_text = scope.read(mapfile, 16 * 1024 * 1024).decode("mbcs", errors="strict")
        mapped_libs = {match.casefold().removesuffix(".lib") + ".lib" for match in re.findall(r"\s([\w.-]+):\S+\.(?:obj|dll)\s*$", map_text, re.I | re.M)}
        require(mapped_libs <= library_names, "Link map reports an unpinned library")
        imports_log = stage / "imports.static.json"
        n.write(imports_log, dict(source="PURE_FILE_BACKED_PE_IMPORT_DIRECTORY", dependencies=imports, image=scope.ref(executable)))
        for row in materialized.values():
            sealed(row)
        scope.stable()
        require(len(commands) == 7 and not scope.allowed_commands and all(row["returncode"] == 0 for row in commands), "Exact seven-command build scope differs")
        by_original = {key(row["original_source"]): row for row in sources}
        window_sources = [by_original[key(row["original_source"])] for row in base["window_sources"]]
        marker = dict(ascii=n.MARKER.decode("ascii"), rva=marker_rvas[0], inclusion_evidence_only=True)
        report = dict(schema=base["schema"], status="UI_WINDOW_HOST_CANDIDATE_BUILT", build_id=identifier,
            baseline_build=refs["baseline_build"], original_world_hud_builder=tool, profile=profile_ref, original_world_hud_profile=profile_ref,
            original_world_hud_component=refs["component"], original_world_hud_source_audit=refs["source_audit"],
            original_world_hud_final_source_audit=refs["final_source_audit"], native_restore_contract_component=base["native_restore_contract_component"],
            compiler=sealed(base["compiler"]), linker=sealed(base["linker"]), dumpbin=sealed(base["dumpbin"]),
            compiler_version="MSVC x64; exact per-unit C++14/C++17 and source charset; /O2; /MD", toolchain=base["toolchain"],
            definitions=base["definitions"], system_include_roots=base["system_include_roots"], compiler_inputs=compiler_inputs,
            compiler_dependency_count=549, sources=sources, window_sources=window_sources, provider_inputs=providers,
            system_libraries=systems, libraries=providers + systems, system_library_names=base["system_library_names"], implicit_libraries=implicit,
            implicit_libraries_before=[donors[key(row["path"])] | {"name": row["name"]} for row in base["implicit_libraries"]],
            implicit_libraries_after=[sealed(row) | {"name": row["name"]} for row in implicit],
            actual_implicit_library_namesfrommap=sorted(mapped_libs & {row["name"].casefold() for row in implicit}), build_tools=tools,
            provider_reports=provider_reports, shared_lua_build=freeze(base["shared_lua_build"]), ui_assets=assets,
            ui_asset_preparation=dict(status="UNCHANGED_ATTESTED_67_PAYLOAD_CATALOG_REUSED", executed=False),
            dependency_discovery=dict(executed=False, reason="Exact retained e639 five-TU dependency sets; five backed source replacements and no new headers."),
            final_compilation=dict(translation_units=completed), final_dependency_reports={row["translation_unit"]: row["dependency_report"] for row in completed},
            response=completed[0]["response"], dependency_report=completed[0]["dependency_report"], link_response=scope.ref(link_response),
            link_log=scope.ref(stage / "link.log"), map=scope.ref(mapfile), executable={**scope.ref(executable),
                "pe": dict(architecture="x64", pe_format="PE32+", is_dll=False)}, imports=dict(dependencies=imports, log=scope.ref(imports_log), source="PURE_PYTHON_STATIC_PE"),
            catalog=catalog, restore_contract_marker=marker, link_snapshot=dict(response=scope.ref(link_response), objects_before=before_link, objects_after=objects, returncode=0),
            current_source_inputs=list(live.values()), protected_artifacts=protected, started=started_ref,
            preflight_protected_artifact_count=len(preflight_protected), prepared_runtime_inputs=runtime,
            sources_changed_from_baseline=[current[path] for path in sorted(changed)],
            new_source_inputs=[], source_revision_provenance=revisions, historical_operational_recovery=operational_recovery,
            historical_metadata_recovery=metadata_recovery, inherited_historical_metadata_recovery=inherited_metadata,
            final_environment={name: env.get(name, "") for name in ("INCLUDE", "LIB", "LIBPATH", "TMP", "TEMP", "VSLANG", "CL", "_CL_", "LINK")},
            frozen_input_reuse=dict(hardlinked_files=587, hardlinked_logical_bytes=sum(row["bytes"] for row in materialized.values() if row["materialization"] == "attested_snapshot_hardlink"),
                copied_files=5, copied_source_bytes=sum(row["bytes"] for row in current.values()), donor_content_and_metadata_preserved=True),
            scope="Five current original-HUD Host compilations and one private x64 link; static PE/payload/contract-marker verification only.",
            source_inputs_unchanged=True, provider_inputs_unchanged=True, host_runtime_executed=False, gamecore_loaded=False,
            sdk_linked=False, mods_updated=False, stage_updated=False, default_promoted=False, sdk_restore_verified=False,
            native_restore_approved=False, actual_window_wheel_routing_verified=False, full_engine_goal_complete=False, forbidden_access_attempts=scope.denied)
        result_path = output / "build_result.json"
        n.write(result_path, report)
        run = dict(schema="zerosis.original_world_hud.host_build_run.v1", status="PASS_CURRENT_ORIGINAL_WORLD_HUD_HOST_BUILD_ONLY",
            utc=datetime.now(timezone.utc).isoformat(), signature=signature, build_id=identifier, profile=profile_ref, builder=tool,
            baseline_build=refs["baseline_build"], proofs=refs, started=started_ref, build_result=scope.ref(result_path), commands=commands,
            actual_objects=objects, catalog=catalog, restore_contract_marker=marker, compiler_dependency_count=549, actual_dependency_counts=list(COUNTS),
            current_source_count=592, source_manifest_count=85, protected_runtime_inputs_unchanged=24, retained_runtime_inputs=runtime,
            historical_exception_counts=profile["historical_exception_counts"], input_files_unchanged=True, objects_retained_for_separate_cleanup=True,
            no_automatic_retry=True, host_or_sdk_or_window_executed=False, original_game_or_user_state_accessed=False, network_used=False,
            sdk_restore_verified=False, native_restore_approved=False, default_promoted=False, actual_window_wheel_routing_verified=False,
            full_engine_goal_complete=False, forbidden_access_attempts=scope.denied)
        n.write(stage / "run.json", run)
        print(json.dumps(dict(status=run["status"], build_id=identifier, build_result=scope.ref(result_path), run=scope.ref(stage / "run.json"),
            executable=scope.ref(executable), child_commands=7)), flush=True)
        return 0
    except BaseException as error:
        n.write(stage / "failure.json", dict(schema="zerosis.original_world_hud.host_build_failure.v1", status="FAILED_DO_NOT_REPLAY",
            utc=datetime.now(timezone.utc).isoformat(), signature=signature, builder=tool, profile=profile_ref, error_type=type(error).__name__,
            error=str(error)[:4000], commands=commands, completed_translation_units=completed, forbidden_access_attempts=scope.denied,
            objects_and_logs_retained=True, compilation_retry_allowed=False, host_or_sdk_or_window_executed=False, full_engine_goal_complete=False))
        raise


if __name__ == "__main__":
    raise SystemExit(main())
