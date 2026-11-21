"""Verify local evidence/artifact integrity. Does not rebuild or execute game/test binaries."""
from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from collect_baseline import PROJECT, digest, pe_header, read_text
from build_sdk_x64 import object_machine


def rows(relative: str) -> list[dict]:
    with (PROJECT / relative).open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def report(relative: str) -> dict:
    return json.loads((PROJECT / relative).read_text(encoding="utf-8"))


def main() -> None:
    issues, checks = [], []
    hash_cache = {}

    def check(name: str, condition: bool, count=None) -> None:
        checks.append({"name": name, "passed": bool(condition), "count": count})
        if not condition:
            issues.append(name)

    def hashes_match(entries) -> bool:
        passed = True
        for row in entries:
            path = Path(row["path"])
            if str(path) not in hash_cache:
                hash_cache[str(path)] = digest(path) if path.is_file() else None
            if hash_cache[str(path)] != row["sha256"]:
                issues.append(f"Hash mismatch or missing file: {path}")
                passed = False
        return passed

    for name, relative in (("original_m0_files", "evidence/2026-09-22/input_sha256.csv"),
                           ("m1_source_inputs", "evidence/m1/input_sha256.csv"),
                           ("reference_link_inputs", "evidence/link_dependencies/input_sha256.csv")):
        entries = rows(relative)
        check(name, hashes_match(entries), len(entries))

    manifest = report("evidence/sdk_reference/snapshot_manifest.json")
    check("sdk_snapshot_matches_original", hashes_match(
        {"path": entry["snapshot"], "sha256": entry["sha256"]} for entry in manifest), len(manifest))

    numeric = report("evidence/numerics/conformance.json")
    check("numeric_conformance_pass", numeric["status"] == "ISOLATED_NATIVE_NUMERIC_CONFORMANCE_PASS")
    check("tested_numeric_inputs", hashes_match({"path": path, "sha256": value}
          for path, value in numeric["input_sha256"].items()), len(numeric["input_sha256"]))
    check("numeric_executables_and_stage_header", hashes_match(numeric["builds"] + [numeric["stage_header"]]))
    check("stage_verification_matches", numeric == report("Stage/Numerics/verification.json"))
    check("numeric_record_accounting", numeric["records_compared_exactly"] == numeric["oracle_records_passed"]
          == sum(numeric["phase_counts"].values()) and numeric["trace_bytes"] == numeric["records_compared_exactly"] * 32)
    check("numeric_architectures", [pe_header(Path(row["path"]))["architecture"] for row in numeric["builds"]]
          == ["x86", "x64"])
    for architecture in ("x86", "x64"):
        log = (PROJECT / f"evidence/numerics/compile_{architecture}.txt").read_text(encoding="utf-8")
        check(f"numeric_{architecture}_no_warnings", not re.search(r"\bwarning\s+[A-Z]+\d+", log, re.I))

    crc = report("evidence/crc/conformance.json")
    jobs = report("evidence/ordered_jobs/conformance.json")
    state = report("evidence/state_commit/conformance.json")
    for name, component, expected_status, stage_report, builds in (
        ("crc", crc, "SDK_BINARY_CRC_X86_X64_CONFORMANCE_PASS", "Stage/Numerics/crc_verification.json", crc["builds"]),
        ("ordered_jobs", jobs, "ISOLATED_X64_ORDERED_JOB_CONFORMANCE_PASS", "Stage/Concurrency/verification.json", [jobs["build"]]),
        ("state_commit", state, "ISOLATED_X64_VALUE_STATE_COMMIT_CONFORMANCE_PASS", "Stage/State/verification.json", [state["build"]]),
    ):
        check(f"{name}_pass_and_stage_report", component["status"] == expected_status and component == report(stage_report))
        check(f"{name}_tested_inputs", hashes_match({"path": path, "sha256": value}
              for path, value in component["input_sha256"].items()), len(component["input_sha256"]))
        check(f"{name}_executables_and_stage", hashes_match(builds + [component["stage_header"]]))
        check(f"{name}_build_logs", hashes_match({"path": entry["log"], "sha256": entry["log_sha256"]} for entry in builds)
              and all(entry["compiler_and_linker_warnings"] == 0 for entry in builds))
    check("crc_architectures", [pe_header(Path(entry["path"]))["architecture"] for entry in crc["builds"]] == ["x86", "x64"])
    check("crc_reference_object_and_map", hashes_match([
        {"path": crc["reference"]["object"], "sha256": crc["reference"]["object_sha256"]},
        {"path": crc["builds"][0]["map"], "sha256": crc["reference"]["map_sha256"]}, crc["fixture"]]))
    check("crc_record_accounting", crc["whole_and_chunked_results_compared"] == crc["cases"] * 2
          and crc["trace_bytes"] == crc["cases"] * 20)
    check("ordered_jobs_trace_and_architecture", hashes_match([jobs["trace"]])
          and jobs["trace"]["sha256"] == jobs["expected_trace_sha256"]
          and pe_header(Path(jobs["build"]["path"]))["architecture"] == "x64")
    native_jobs = report("evidence/ordered_jobs/native_execution.json")
    check("ordered_jobs_execution_record", native_jobs["status"] == "PASS"
          and native_jobs["checks_passed"] == jobs["checks_passed"] and native_jobs["records"] == jobs["records_compared_to_python"]
          and len(native_jobs["runs"]) == jobs["native_runs"]
          and all(run["peak_inflight"] == run["workers"] == run["distinct_threads"]
                  and run["first_completion"] == list(reversed(range(run["workers"]))) for run in native_jobs["runs"]))

    check("state_commit_trace_architecture_and_dependencies", hashes_match(
          [state["trace"], state["native_execution"]] + state["staged_test_dependencies"])
          and state["trace"]["sha256"] == state["expected_trace_sha256"]
          and pe_header(Path(state["build"]["path"]))["architecture"] == "x64")
    native_state = report("evidence/state_commit/native_execution.json")
    check("state_commit_execution_record", native_state["status"] == "PASS"
          and native_state["scope"] == "ISOLATED_VALUE_STATE_NOT_GAMECORE"
          and native_state["case_names"] == state["case_names"]
          and len(set(native_state["case_names"])) == state["named_cases_passed"]
          and native_state["checks_passed"] == state["checks_passed"]
          and native_state["state_records"] == state["state_records_compared_to_python"]
          and native_state["committed_batches"] == state["committed_batches"]
          and native_state["scenarios"] == state["scenarios"] and native_state["steps"] == state["steps_per_scenario"]
          and native_state["workers"] == state["worker_configurations"] == [1, 2, 4])
    check("state_commit_record_accounting", state["committed_batches"]
          == state["scenarios"] * state["steps_per_scenario"] * len(state["worker_configurations"])
          and state["state_records_compared_to_python"] == state["committed_batches"] * 8
          and state["record_bytes"] == 52
          and state["trace_bytes"] == state["state_records_compared_to_python"] * state["record_bytes"]
          == Path(state["trace"]["path"]).stat().st_size)

    sdk = report("evidence/sdk_reference/build_result.json")
    check("reference_build_pass", sdk["status"] == "SDK_REFERENCE_BUILD_PASS" and sdk["exit_code"] == 0)
    check("reference_dll_and_build_support", hashes_match(sdk["outputs"] + sdk["build_support"]))
    check("reference_x86_architecture", all(pe_header(Path(row["path"]))["architecture"] == "x86"
          for row in sdk["outputs"]))

    x64 = report("evidence/sdk_x64/build_result.json")
    x64_manifest = report("evidence/sdk_x64/port_manifest.json")
    x64_link = report("evidence/sdk_x64/link_analysis.json")
    allocator = report("evidence/sdk_x64_allocator/conformance.json")
    boundaries = report("evidence/numeric_boundaries/conformance.json")
    lua_component = report("evidence/lua_component/build_result.json")
    lua_provider = report("evidence/lua_provider/build_result.json")
    lua_port = report("evidence/lua_provider/port_manifest.json")
    lua_reference = report("evidence/lua_reference/provider/conformance.json")
    port_stage = report("Stage/GameCore_x64/review_bundle.json")
    check("x64_port_generated_sources", hashes_match({"path": row["port"], "sha256": row["port_sha256"]}
          for row in x64_manifest), len(x64_manifest))
    check("x64_compile_objects", x64["status"] == "SDK_X64_ALL_OBJECTS_COMPILED"
          and len(x64["objects"]) == x64["translation_units_expected"] == 161
          and all(object_machine(Path(row["path"])) == row and row["architecture"] == "x64" for row in x64["objects"]),
          len(x64["objects"]))
    check("x64_compile_inputs_and_logs", hashes_match([x64["builder"], x64["manifest"], x64["patch_specification"],
          {"path": x64["compiler"], "sha256": x64["compiler_sha256"]}]
          + [{"path": execution[key], "sha256": execution[key + "_sha256"]}
             for execution in x64["executions"] for key in ("log", "response")])
          and all(execution["exit_code"] == 0 for execution in x64["executions"])
          and not x64["unique_error_lines"] and x64["original_files_unchanged"] and x64["generated_port_inputs_unchanged"])
    check("x64_pointer_warning_gate", not any(code in x64["warning_code_counts"] for code in ("C4302", "C4311", "C4312"))
          and all(all(flag in Path(execution["response"]).read_text(encoding="utf-8")
                      for flag in ("/we4302", "/we4311", "/we4312")) for execution in x64["executions"]))
    expected_support = {PROJECT / "Source/Porting" / name for name in (
        "CvAutoArchiveSupport.h", "CvCheckedNarrow.h", "CvEmbeddedDatabaseIO.h",
        "CvLuaCheckedInteger.h", "ZeroSisBootstrap.h", "ZeroSisHostBinding.h", "ZeroSisGlobalsLifecycle.h", "ZeroSisLuaEnums.h", "ZeroSisLuaFractal.h", "ZeroSisLuaFractalNumeric.h")}
    expected_support.add(PROJECT / "Source/LuaBorrowed/ZeroSisLuaBorrowed.h")
    check("x64_port_support_headers", len(x64["support_inputs"]) == len(expected_support)
          and {Path(row["path"]) for row in x64["support_inputs"]} == expected_support
          and hashes_match(x64["support_inputs"]))
    check("x64_numeric_warning_gate", x64["numeric_warning_gate"]["passed"]
          and x64["numeric_warning_gate"]["level"] == "/W3"
          and not x64["numeric_warning_gate"]["remaining_lines"]
          and not any(code in x64["warning_code_counts"] for code in ("C4244", "C4267", "C4838")))
    check("numeric_boundaries_inputs", boundaries["status"] == "SDK_X64_NUMERIC_BOUNDARIES_PASS"
          and hashes_match({"path": path, "sha256": value} for path, value in boundaries["input_sha256"].items()))
    check("numeric_boundaries_execution_artifacts", hashes_match([boundaries[key] for key in
          ("build", "native_execution", "fixtures", "trace", "notification_trace")]
          + [{"path": boundaries["build"]["log"], "sha256": boundaries["build"]["log_sha256"]}])
          and boundaries["build"]["compiler_and_linker_warnings"] == 0
          and pe_header(Path(boundaries["build"]["path"]))["architecture"] == "x64")
    native_boundaries = report("evidence/numeric_boundaries/native_execution.json")
    check("numeric_boundaries_oracle_accounting", native_boundaries == boundaries["native"]
          and native_boundaries["scope"] == "NUMERIC_AND_EXTRACTED_SDK_COMPONENTS_ONLY"
          and native_boundaries["records"] == 42250 and native_boundaries["lua_cases"] == 74
          and native_boundaries["lua_rejections"] == native_boundaries["lua_recoveries"] == 39
          and native_boundaries["notification_entries"] == 142
          and Path(boundaries["trace"]["path"]).stat().st_size == native_boundaries["records"] * 9
          and Path(boundaries["notification_trace"]["path"]).stat().st_size == 142 * 4
          and boundaries["trace"]["sha256"] == boundaries["expected_trace_sha256"]
          and boundaries["notification_trace"]["sha256"] == boundaries["expected_notification_sha256"])
    numeric_ledger = report("evidence/numeric_boundaries/edit_ledger.json")
    check("numeric_edit_ledger", numeric_ledger["baseline_diagnostic_locations"] == len(numeric_ledger["locations"]) == 479
          and numeric_ledger["patch_specification_sha256"] == x64["patch_specification"]["sha256"]
          and numeric_ledger["by_code"] == dict(Counter(row["code"] for row in numeric_ledger["locations"])))
    patch_plan=report('Source/Porting/sdk_x64_patches.json')
    previous_plan=json.loads(Path(numeric_ledger['unchanged_numeric_patch_baseline']['path']).read_text(encoding='utf-8'))
    serialization_patches=[p for p in patch_plan['patches'] if p['id'].startswith('serialization_')]
    check('numeric_patches_preserved_after_serialization_edits',hashes_match([numeric_ledger['unchanged_numeric_patch_baseline']])
          and [p for p in patch_plan['patches'] if not p['id'].startswith(('serialization_','temp_callers_','auto_callers_','db_callers_','localization_callers_','world_mod_access_','world_map_access_','world_map_bridge_access_','logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]==previous_plan['patches']
          and numeric_ledger['supplemental_non_numeric_patches']==[p['id'] for p in patch_plan['patches'] if p['id'].startswith(('serialization_','temp_callers_','auto_callers_','db_callers_','localization_callers_','world_mod_access_','world_map_access_','world_map_bridge_access_','logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]
          and len(serialization_patches)==9)
    check("lua_test_provider_provenance", lua_component["status"] == "LUA514_X64_COMPONENT_BUILT"
          and lua_component["translation_units"] == 29 and lua_component["runtime"] == "/MT"
          and lua_component["archive"]["sha256"] == "b038e225eaf2a5b57c9bcc35cd13aa8c6c8288ef493d52970c9545074098af3a"
          and hashes_match(lua_component["sources"] + [lua_component[key] for key in ("archive", "library", "builder", "log")]))
    check("lua_md_provider_inputs", lua_provider["status"] == "LUA51_X64_MD_PROVIDER_BUILT"
          and hashes_match(lua_port + [lua_provider[key] for key in
              ("library", "builder", "source_manifest", "patches", "compiler", "log", "response", "sdk_configuration")])
          and hashes_match({"path": row["upstream"], "sha256": row["upstream_sha256"]} for row in lua_port))
    check("lua_md_provider_objects", lua_provider["runtime"] == "/MD" and lua_provider["compiler_and_linker_warnings"] == 0
          and len(lua_provider["objects"]) == lua_provider["translation_units"] == 29
          and all(object_machine(Path(row["path"])) == row and row["architecture"] == "x64" for row in lua_provider["objects"]))
    check("lua_actual_reference_conformance", lua_reference["status"] == "SDK_LUA_X86_X64_CONFORMANCE_PASS"
          and lua_reference["different_results"] == 0 and lua_reference["numeric_inputs"] == 6218
          and lua_reference["rounding_modes"] == 4 and lua_reference["conversion_results"] == 74616
          and lua_reference["scripts_match_python_oracle"] and lua_reference["sdk_matches_python_rounding_oracle"]
          and lua_reference["library"] == lua_provider["library"] and lua_reference["runtime"] == "MD"
          and hashes_match({"path": path, "sha256": value} for path, value in lua_reference["input_sha256"].items()))
    reference_artifacts = [row[key] for row in lua_reference["runs"] for key in ("trace", "scripts", "build")]
    reference_artifacts += [lua_reference["runs"][0]["build"][key] for key in ("library", "dll", "dll_source", "map", "log")]
    reference_artifacts += [lua_reference["runs"][1]["build"]["log"], lua_reference["fixture"]]
    check("lua_actual_reference_artifacts", hashes_match(reference_artifacts)
          and lua_reference["runs"][0]["trace"]["sha256"] == lua_reference["runs"][1]["trace"]["sha256"]
          == lua_reference["oracle_trace_sha256"]
          and lua_reference["runs"][0]["build"]["pe"]["architecture"] == "x86"
          and lua_reference["runs"][1]["build"]["pe"]["architecture"] == "x64")
    lua_delta = report("evidence/lua_provider/link_delta.json")
    check("lua_link_closure", hashes_match(lua_delta["evidence"])
          and lua_delta["before"] == 342 and lua_delta["after"] == 302
          and len(lua_delta["resolved"]) == 40 and not lua_delta["added"] and not lua_delta["remaining_lua_c_api"]
          and any(entry['name']=='Lua51' and entry['library']==lua_provider['library'] for entry in x64_link['providers'])
          and not any(row['decorated_or_c_symbol'].startswith(('lua_','luaL_','luaopen_')) for row in rows('evidence/sdk_x64/link_unresolved_candidates.csv'))
          and boundaries["lua_library"] == lua_provider["library"] and boundaries["runtime"] == "/MD")
    from stream_evidence import validate as validate_stream_evidence
    streams,stream_conformance,stream_entry=validate_stream_evidence(PROJECT/'evidence/streams/provider/build_result.json')
    stream_delta=report('evidence/streams/link_delta.json')
    check('stream_provider_provenance',stream_entry in x64_link['providers'] and streams['runtime']=='/MD')
    check('stream_byte_oracle_accounting',stream_conformance['scalar_fields_compared']==92160
          and stream_conformance['serialized_bytes_compared']==405504
          and stream_conformance['random_records_per_endian']==2048 and stream_conformance['endian_modes']==3
          and len(stream_conformance['equal_reference_scenarios'])==12)
    check('stream_failure_invariants',stream_conformance['hardening_assertions']==31
          and stream_conformance['hardening_rejections']==13
          and {r['mode'] for r in stream_conformance['intentional_invalid_input_state_fixes']}=={'pastseek','pastskip'})
    check('stream_link_closure',hashes_match(stream_delta['evidence']) and stream_delta['before']==302
          and stream_delta['after']==278
          and len(stream_delta['resolved'])==24 and not stream_delta['added']
          and not set(stream_delta['resolved']).intersection(row['decorated_or_c_symbol'] for row in rows('evidence/sdk_x64/link_unresolved_candidates.csv')))
    check('stream_scope',not any((stream_conformance['game_launched'],stream_conformance['game_runtime_verified'],
          streams['game_launched'],streams['game_runtime_verified'],stream_delta['gamecore_linked'])))
    from serialization_evidence import validate as validate_serialization_evidence
    serialization,serialization_conformance,serialization_entry=validate_serialization_evidence(PROJECT/'evidence/serialization/candidate/build_result.json')
    serialization_delta=report('evidence/serialization/link_delta.json')
    check('serialization_provider_provenance',serialization_entry in x64_link['providers'] and serialization['runtime']=='/MD'
          and len(serialization['generated_extracts'])==2)
    check('serialization_enum_byte_oracle',serialization_conformance['enum_type_count']==81
          and serialization_conformance['enum_write_read_pairs']==409455
          and serialization_conformance['enum_bytes_per_architecture']==1622655
          and serialization_conformance['enum_wire_bytes']['GameTypes']==1)
    check('serialization_container_and_gamecore_extracts',serialization_conformance['ordered_container_wire_matches']==39
          and serialization_conformance['cross_architecture_container_reads']==90
          and serialization_conformance['existing_value_merge_append_checks']==48
          and set(serialization_conformance['extracted_gamecore_cases'])=={'replay_turn_data','replay_empty','vote_selection','vote_empty'})
    check('serialization_limits_and_order_differences',serialization_conformance['native_count_overflow_rejections']==2
          and serialization_conformance['unordered_logical_values_match']
          and len(serialization_conformance['unordered_wire_order_differences'])==6)
    check('serialization_link_closure',hashes_match(serialization_delta['evidence'])
          and serialization_delta['before']==278 and serialization_delta['after']==150
          and len(serialization_delta['resolved'])==128 and not serialization_delta['added']
          and sum('W4' in name for name in serialization_delta['resolved'])==126
          and not set(serialization_delta['resolved']).intersection(row['decorated_or_c_symbol'] for row in rows('evidence/sdk_x64/link_unresolved_candidates.csv'))
          and all(name in [e['name'] for e in x64_link['providers']] for name in ('Lua51','Streams','Serialization')))
    check('serialization_scope',not any((serialization['game_launched'],serialization_conformance['game_launched'],
          serialization_conformance['full_save_compatibility_verified'],serialization_conformance['game_determinism_verified'],
          serialization_delta['gamecore_linked'])))
    from foundation_evidence import validate as validate_foundation_evidence
    foundation,foundation_conformance,foundation_entry=validate_foundation_evidence(PROJECT/'evidence/foundation/build_result.json')
    foundation_delta=report('evidence/foundation/link_delta.json')
    check('foundation_provider_provenance',foundation_entry in x64_link['providers'] and foundation['runtime']=='/MD'
          and len(foundation['x64']['objects'])==4 and not foundation['x64']['warning_codes'])
    check('foundation_crc_oracle_and_layout',foundation_conformance['crc_cases']==8981
          and foundation_conformance['crc_results_per_architecture']==35924
          and foundation_conformance['crc_layouts']==9 and foundation_conformance['crc_invalid_input_rejections']==4)
    check('foundation_recursive_lock_concurrency',foundation_conformance['lock_workers']==[1,2,4]
          and foundation_conformance['protected_increments_per_architecture']==140000
          and foundation_conformance['lock_lifetimes_per_architecture']==512)
    check('foundation_clock_initialization_and_counter_brackets',foundation_conformance['clock_bracket_checks']=={'x86':384,'x64':384}
          and foundation_conformance['clock_worker_reads_per_architecture']==80000
          and foundation_conformance['x64_concurrent_clock_first_use_workers']==8)
    check('foundation_aligned_memory_and_high_addresses',foundation_conformance['allocations']['x64']['above_4gb']==378
          and foundation_conformance['allocations']['x86']['cases']==foundation_conformance['allocations']['x64']['cases']==378
          and foundation_conformance['allocation_thread_workers']==4 and foundation_conformance['threaded_allocations_per_architecture']==4096
          and foundation_conformance['native_allocation_overflow_rejections']==1)
    check('foundation_link_closure',hashes_match(foundation_delta['evidence']) and foundation_delta['before']==150
          and foundation_delta['after']==140
          and len(foundation_delta['resolved'])==10 and not foundation_delta['added']
          and not set(foundation_delta['resolved']).intersection(row['decorated_or_c_symbol'] for row in rows('evidence/sdk_x64/link_unresolved_candidates.csv'))
          and [e['name'] for e in x64_link['providers']][:4]==['Lua51','Streams','Serialization','Foundation'])
    check('foundation_scope',not any((foundation['game_launched'],foundation_conformance['game_launched'],
          foundation_conformance['game_multicore_verified'],foundation_conformance['game_performance_verified'],foundation_delta['gamecore_linked'])))
    from temp_heap_evidence import validate as validate_temp_heap_evidence
    temp_heap,temp_conformance,temp_entry=validate_temp_heap_evidence(PROJECT/'evidence/temp_heap/build_result.json')
    temp_delta=report('evidence/temp_heap/link_delta.json')
    check('temp_heap_provider_provenance',temp_entry in x64_link['providers'] and temp_heap['foundation']==foundation_entry
          and len(temp_heap['x64']['objects'])==1 and not temp_heap['x64']['warning_codes'])
    check('temp_heap_actual_sdk_and_model_traces',temp_conformance['matching_reference_probe']
          and temp_conformance['sequential_model']['operations']==13520 and temp_conformance['sequential_model']['arena_lifetimes']==22
          and len({r['sha256'] for r in temp_conformance['outputs']})==1)
    check('temp_heap_concurrent_allocation_and_capacity_pressure',temp_conformance['workers']==[1,2,4,8]
          and temp_conformance['concurrent_successful_allocations']==122880 and temp_conformance['concurrent_forced_capacity_rejections']==15360
          and temp_conformance['pressure_attempts']==400000 and sum(temp_conformance['pressure_results'].values())==400000)
    check('temp_heap_integer_lease_and_native_address_boundaries',temp_conformance['rounding_overflow_rejections']==15
          and temp_conformance['maximum_simultaneous_leases']==65535 and temp_conformance['lifecycle_or_release_rejections']==6
          and temp_conformance['native_address_space_reserved']==4294967296 and temp_conformance['committed_page_bytes']==8192
          and temp_conformance['tested_unsigned_offsets']==[2147483648,4294967280])
    check('temp_heap_engine_export_binding_and_failures',temp_conformance['host_first_use_workers']==8
          and temp_conformance['host_binding_calls']==8192 and temp_conformance['missing_host_rejections']==2
          and temp_conformance['null_host_rejections_and_recovery']==2)
    check('temp_heap_link_closure',hashes_match(temp_delta['evidence']) and temp_delta['before']==140
          and temp_delta['after']==137
          and len(temp_delta['resolved'])==3 and not temp_delta['added']
          and not set(temp_delta['resolved']).intersection(row['decorated_or_c_symbol'] for row in rows('evidence/sdk_x64/link_unresolved_candidates.csv'))
          and [e['name'] for e in x64_link['providers']][:5]==['Lua51','Streams','Serialization','Foundation','TempHeap'])
    check('temp_heap_scope',not any((temp_heap['game_launched'],temp_conformance['game_launched'],
          temp_conformance['game_multicore_verified'],temp_conformance['game_performance_verified'],temp_delta['gamecore_linked'])))
    from temp_heap_caller_evidence import validate as validate_temp_callers
    callers,caller_entry=validate_temp_callers();caller_delta=report('evidence/temp_heap_callers/link_delta.json')
    caller_base=numeric_ledger['unchanged_temp_heap_caller_baseline']
    caller_base_plan=json.loads(Path(caller_base['path']).read_text(encoding='utf-8'))
    check('temp_caller_patch_baseline',hashes_match([caller_base])
          and [p for p in patch_plan['patches'] if not p['id'].startswith(('temp_callers_','auto_callers_','db_callers_','localization_callers_','world_mod_access_','world_map_access_','world_map_bridge_access_','logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]==caller_base_plan['patches']
          and sum(p['id'].startswith('temp_callers_') for p in patch_plan['patches'])==6
          and len([p for p in patch_plan['patches'] if not p['id'].startswith(('auto_callers_','db_callers_','localization_callers_','world_mod_access_','world_map_access_','world_map_bridge_access_','logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))])==458)
    check('temp_caller_provenance_and_link_binding',x64_link['caller_patch_conformance']==caller_entry
          and all(entry in x64_link['providers'] for entry in callers['providers']) and callers['checked_bnwsdk_call_sites']==2)
    check('temp_caller_saved_field_and_utf16_file_roundtrip',callers['database_cases_per_executable']==33
          and callers['endian_modes']==3 and callers['save_field_count_bytes']==4
          and len({r['sha256'] for r in callers['outputs']})==1 and all('한글' in r['isolated_cache'] for r in callers['runs']))
    check('temp_caller_precommit_failure_cleanup',callers['io_failure_cases_per_executable']==26
          and callers['existing_cache_preserved_on_tested_precommit_failure'] and callers['temporary_files_cleaned']
          and callers['handles_and_temporary_buffers_released'])
    check('temp_caller_allocation_and_wrapper_boundaries',callers['injected_allocation_failures']==5
          and callers['tested_native_request_bytes']==8589934590 and callers['native_checks']=={'production':1009,'allocation_faults':1061})
    check('temp_caller_link_requirements',hashes_match(caller_delta['evidence'])
          and caller_delta['before']==caller_delta['after']==137
          and not caller_delta['added'] and not caller_delta['no_longer_required'])
    check('temp_caller_scope',not any((callers['game_launched'],callers['full_save_compatibility_verified'],
          callers['game_multicore_verified'],caller_delta['gamecore_linked'])))
    from auto_archive_evidence import validate as validate_auto_archive
    archive,archive_conformance,archive_entry=validate_auto_archive(PROJECT/'evidence/auto_archive/build_result.json')
    archive_delta=report('evidence/auto_archive/link_delta.json')
    check('auto_archive_provider_provenance',archive_entry in x64_link['providers']
          and len(archive['x64']['objects'])==3 and not archive['x64']['warning_codes'])
    check('auto_archive_actual_sdk_and_model_traces',archive_conformance['operations_per_architecture_per_endian']==4114
          and archive_conformance['endian_modes']==[0,1,2] and archive_conformance['trace_model_matches']==6)
    check('auto_archive_cross_architecture_and_templates',archive_conformance['exchange_wire_matches']==12
          and archive_conformance['cross_architecture_payload_reads']==24)
    check('auto_archive_failure_retention_and_bounds',archive_conformance['rejected_inputs_and_injected_failures']==156
          and archive_conformance['successful_write_retries']==120)
    check('auto_archive_diagnostic_text_boundary',archive_conformance['integer_diagnostic_matches']==131596
          and len(archive_conformance['diagnostic_float_differences'])==13 and archive_conformance['extreme_finite_formats']==5
          and all(d['type'] in ('FLOAT','DOUBLE','SPECIAL') for d in archive_conformance['diagnostic_float_differences']))
    check('auto_archive_link_closure',hashes_match(archive_delta['evidence']) and archive_delta['before']==137
          and archive_delta['after']==113
          and len(archive_delta['resolved'])==24 and not archive_delta['added'] and not archive_delta['remaining_archive_symbols']
          and not set(archive_delta['resolved']).intersection(row['decorated_or_c_symbol'] for row in rows('evidence/sdk_x64/link_unresolved_candidates.csv'))
          and [e['name'] for e in x64_link['providers']][:6]==['Lua51','Streams','Serialization','Foundation','TempHeap','AutoArchive'])
    check('auto_archive_scope',not any((archive['game_launched'],archive_conformance['game_launched'],
          archive_conformance['full_save_compatibility_verified'],archive_conformance['game_multicore_verified'],archive_delta['gamecore_linked'])))
    auto_base=numeric_ledger['unchanged_auto_archive_caller_baseline']
    auto_base_plan=json.loads(Path(auto_base['path']).read_text(encoding='utf-8'))
    auto_results=archive_conformance['caller_results'];life=auto_results['lifecycle'];mutation=auto_results['mutations'];concurrent=auto_results['concurrency']
    auto_caller_delta=report('evidence/auto_archive_callers/link_delta.json')
    check('auto_caller_patch_baseline',hashes_match([auto_base]) and len(patch_plan['patches'])==693
          and [p for p in patch_plan['patches'] if not p['id'].startswith(('auto_callers_','db_callers_','localization_callers_','world_mod_access_','world_map_access_','world_map_bridge_access_','logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]==auto_base_plan['patches']
          and sum(p['id'].startswith('auto_callers_') for p in patch_plan['patches'])==21)
    check('auto_caller_lifetime_cleanup',life['constructor_and_name_faults']==15 and life['registration_allocation_failures']==3
          and life['lifetime_cleanups']==21 and life['bounds_rejections']==16 and life['protected_owner_pages']==1)
    check('auto_caller_independent_owner_name_concurrency',concurrent['workers']==8 and concurrent['owner_lifetimes']==4096
          and concurrent['named_variable_lifetimes']==8192 and concurrent['first_pool_use_concurrent'] and concurrent['shared_name_pointer_equal'])
    check('auto_caller_vector_transactions',mutation['operation_kinds']==15 and mutation['pending_variants']==3
          and [mutation[k] for k in ('integer_allocation_failures','bool_allocation_failures','custom_allocation_failures','custom_value_failures')]==[119,96,167,531]
          and mutation['successful_mutations']==180 and mutation['truncated_vector_reads']==216 and mutation['growth_allocations']==41)
    auto_support=PROJECT/'Source/Porting/CvAutoArchiveSupport.h'
    check('auto_caller_compiled_abi',{'path':str(auto_support),'sha256':digest(auto_support)} in x64['support_inputs']
          and [life[k] for k in ('base_bytes','scalar_bytes','vector_bytes')]==[24,40,80] and len(x64['objects'])==161)
    check('auto_caller_link_requirements',hashes_match(auto_caller_delta['evidence'])
          and auto_caller_delta['before']==auto_caller_delta['after']==113
          and not auto_caller_delta['added'] and not auto_caller_delta['no_longer_required'] and not auto_caller_delta['gamecore_linked'])
    from database_evidence import validate as validate_database
    database,database_conformance,database_entry=validate_database(PROJECT/'evidence/database/candidate/build_result.json')
    database_delta=report('evidence/database/link_delta.json')
    check('database_native_dll_provenance',database_entry in x64_link['providers'] and database_conformance['required_import_count']==41
          and database_conformance['export_count']==113 and len(database['objects'])==3)
    check('database_actual_original_differential',database_conformance['exact_trace_pairs']==5 and database_conformance['bulk_rows']==1024
          and all(r['returncode']==0 for r in database_conformance['runs']))
    check('database_bidirectional_file_exchange',len(database_conformance['read_only_file_exchange'])==2
          and all(r['exact_read_trace'] and r['unchanged_by_readers'] for r in database_conformance['read_only_file_exchange']))
    check('database_lifetime_bounds_and_composite_keys',database_conformance['hardening_checks']==82)
    check('database_independent_connection_concurrency',database_conformance['workers']==8 and database_conformance['independent_connection_lifetimes']==64
          and database_conformance['concurrent_inserted_rows']==32768 and database_conformance['concurrency_checks']==131460)
    check('database_link_closure',hashes_match(database_delta['evidence']) and database_delta['before']==113
          and database_delta['after']==72 and len(database_delta['resolved'])==41
          and not database_delta['added'] and not database_delta['remaining_database_symbols']
          and set(database_delta['resolved'])=={p['required_import'] for p in database_conformance['provider_proof']}
          and [e['name'] for e in x64_link['providers']][:7]==['Lua51','Streams','Serialization','Foundation','TempHeap','AutoArchive','Database'])
    check('database_scope',not any((database_conformance['game_launched'],database_conformance['gamecore_loaded'],
          database_conformance['full_game_save_compatibility_verified'],database_conformance['game_multicore_verified'],database_delta['gamecore_linked'])))
    database_base=numeric_ledger['unchanged_database_caller_baseline'];database_prior=json.loads(Path(database_base['path']).read_text(encoding='utf-8'))
    database_assignment=report('evidence/database/assignment/conformance.json')
    check('database_assignment_source_migration',hashes_match([database_base]) and len(database_prior['patches'])==479
          and [p for p in patch_plan['patches'] if not p['id'].startswith(('db_callers_','localization_callers_','world_mod_access_','world_map_access_','world_map_bridge_access_','logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]==database_prior['patches']
          and sum(p['id'].startswith('db_callers_') for p in patch_plan['patches'])==1)
    check('database_assignment_prepare_then_commit',database_assignment['checks']==551 and database_assignment['failure_cases']==30
          and database_assignment['cpp_faults']==14 and database_assignment['sqlite_faults']==16 and database_assignment['success_cases']==4
          and database_assignment['production_objects']==database['objects'])
    from database_corpus_evidence import validate as validate_database_corpus
    corpus,corpus_entry=validate_database_corpus()
    check('database_cached_corpus_provenance',corpus['provider']==database_entry and hashes_match([corpus_entry]))
    check('database_cached_corpus_native_comparison',corpus['tables']==748 and corpus['rows']==188675 and corpus['values']==1116126
          and len(corpus['runs'])==6 and all(row['equal_table_digests_and_trace'] for row in corpus['comparisons']))
    check('database_cached_corpus_scope',corpus['originals_unchanged'] and corpus['copies_unchanged']
          and not corpus['game_launched'] and not corpus['gamecore_loaded']
          and all(not row['original_opened_by_harness'] for row in corpus['copies']))
    from flua_evidence import validate as validate_flua
    flua,flua_conformance,flua_entry=validate_flua(PROJECT/'evidence/flua/build_result.json')
    flua_delta=report('evidence/flua/link_delta.json')
    check('flua_native_implementation_provenance',flua_entry in x64_link['providers'] and len(flua['objects'])==1
          and len(flua_conformance['provider_proof'])==8)
    check('flua_actual_original_differential',len(flua_conformance['comparisons'])==5
          and all(p['exact'] for p in flua_conformance['comparisons']))
    check('flua_value_ownership_and_boundaries',flua_conformance['self_assignment_fixed'] and flua_conformance['rejected_inputs']==8
          and flua_conformance['table_writes_per_architecture']==4096)
    check('flua_protected_calls_and_cleanup',flua_conformance['locked_callbacks_per_architecture']==7680
          and flua_conformance['cpp_callback_unwind_verified'] and flua_conformance['error_handler_throw_cleanup_verified']
          and flua_conformance['protected_call_allocation_failure_recovery_verified'])
    check('flua_link_closure',hashes_match(flua_delta['evidence']) and flua_delta['before']==database_delta['after']==72
          and flua_delta['after']==64 and len(flua_delta['resolved'])==8
          and set(flua_delta['resolved'])==set(flua_conformance['required_symbols']) and not flua_delta['added'] and not flua_delta['remaining_flua_symbols'])
    check('flua_scope',not flua_conformance['gamecore_loaded'] and not flua_conformance['game_multicore_verified']
          and not flua_delta['gamecore_linked'])
    from string_evidence import validate as validate_strings
    strings,string_conformance,string_entry=validate_strings(PROJECT/'evidence/strings/build_result.json')
    string_delta=report('evidence/strings/link_delta.json')
    check('strings_native_implementation_provenance',string_entry in x64_link['providers'] and len(strings['objects'])==2
          and len(string_conformance['provider_proof'])==12)
    check('strings_actual_original_differential',len(string_conformance['comparisons'])==6
          and all(p['exact'] for p in string_conformance['comparisons']) and string_conformance['mutation_operations_per_architecture']==8192
          and string_conformance['corpus_oracle_matched'])
    check('strings_wire_and_cross_read',string_conformance['wire_oracle_matched'] and string_conformance['wire_bytes']==433098
          and string_conformance['wire_fields']==411 and len(string_conformance['cross_reads'])==2
          and all(p['exact'] for p in string_conformance['cross_reads']))
    check('strings_buffer_and_allocation_failure',all(string_conformance['intentional_defect_fixes'].values())
          and string_conformance['fault_cases']==20 and string_conformance['fault_success_cases']==15
          and string_conformance['boundary_rejections']==16 and string_conformance['stream_rejections']==15
          and strings['x64']['hardening']['production_objects']==strings['objects'])
    check('strings_link_closure',hashes_match(string_delta['evidence']) and string_delta['before']==flua_delta['after']==64
          and string_delta['after']==52 and len(string_delta['resolved'])==12
          and set(string_delta['resolved'])==set(string_conformance['required_symbols'])
          and not string_delta['added'] and not string_delta['remaining_string_symbols']
          and not set(string_delta['resolved']).intersection(r['decorated_or_c_symbol'] for r in rows('evidence/sdk_x64/link_unresolved_candidates.csv')))
    check('strings_scope',not any((string_conformance['gamecore_loaded'],string_conformance['game_multicore_verified'],
          string_conformance['full_game_save_compatibility_verified'],string_delta['gamecore_linked'])))
    from localization_icu_evidence import validate as validate_localization_icu
    icu,localization_backend,localization_numeric,localization_counts=validate_localization_icu()
    check('localization_icu_source_and_library_provenance',localization_counts['original_files']==642
          and localization_counts['icu_objects']==301 and localization_backend['compiler_warnings']==0
          and len(localization_numeric['production_implementation_proof'])==2)
    check('localization_icu_original_numeric_comparison',localization_numeric['numeric_outputs_compared']==22
          and localization_numeric['numeric_corpus_outputs_compared']==1140 and not localization_numeric['differences'])
    check('localization_icu_unicode_and_dynamic_boundaries',localization_numeric['case_outputs']==12
          and localization_numeric['unavailable_title_cases']==6 and localization_numeric['dynamic_and_unicode_boundaries'])
    check('localization_icu_failure_and_independent_calls',localization_numeric['nonfinite_rule_based_rejections']==48
          and localization_counts['known_original_defects']==1 and localization_numeric['concurrent_formatting_calls']==2048)
    check('localization_icu_component_scope',not localization_numeric['game_launched'] and not localization_numeric['gamecore_loaded']
          and not localization_backend['game_launched'] and not localization_backend['gamecore_loaded'])
    localization_stage=report('Stage/LocalizationICU/review_bundle.json')
    check('localization_icu_review_stage',localization_stage['status']=='LOCALIZATION_ICU_COMPONENT_REVIEW_BUNDLE_READY'
          and localization_stage['counts']==localization_counts and hashes_match(localization_stage['files'])
          and hashes_match({'path':row['source'],'sha256':row['sha256']} for row in localization_stage['files'])
          and localization_stage['numeric_backend_only'] and not localization_stage['gamecore_linked'] and not localization_stage['game_launched'])
    from localization_values_evidence import validate as validate_localization_values
    localization_values,localization_value_result,localization_grammar=validate_localization_values()
    check('localization_shared_original_differential',localization_value_result['exact_shared_trace']
          and localization_value_result['original_records']==50 and len(localization_value_result['production_proof'])==1)
    check('localization_shared_bounds_and_copy_lifetime',localization_value_result['independent_copies']==4096
          and [row['mode'] for row in localization_value_result['executions']]==['shared','parameters','boundaries']
          and not any(row['exit_code'] for row in localization_value_result['executions']))
    check('localization_original_grammar_observation_scope',len(localization_grammar['runs'])==4
          and not any(row['exit_code'] for row in localization_grammar['runs'])
          and not localization_grammar['game_launched'] and not localization_grammar['gamecore_loaded'])
    localization_value_stage=report('Stage/LocalizationValues/review_bundle.json')
    check('localization_shared_review_stage',localization_value_stage['status']=='LOCALIZATION_VALUES_REVIEW_BUNDLE_READY'
          and hashes_match(localization_value_stage['files'])
          and hashes_match({'path':row['source'],'sha256':row['sha256']} for row in localization_value_stage['files'])
          and not localization_value_stage['gamecore_linked'] and not localization_value_stage['game_launched'])
    from localization_provider_evidence import validate as validate_localization_provider
    localization,localization_result,localization_entry=validate_localization_provider()
    localization_counts=localization_result['validated_counts']
    localization_base=numeric_ledger['unchanged_localization_caller_baseline']
    localization_baseline=json.loads(Path(localization_base['path']).read_text(encoding='utf-8'))
    check('localization_sdk_patch_baseline',hashes_match([localization_base])
          and [p for p in patch_plan['patches'] if not p['id'].startswith(('localization_callers_','world_mod_access_','world_map_access_','world_map_bridge_access_','logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]==localization_baseline['patches']
          and len(localization_baseline['patches'])==480 and len(patch_plan['patches'])==693
          and all(p['file']=='CvLocalization/include/CvLocalization.h' for p in patch_plan['patches'] if p['id'].startswith('localization_callers_')))
    check('localization_native_sdk_provider_provenance',localization_entry in x64_link['providers']
          and len(localization['objects'])==3 and len(localization_result['production_proof'])==3)
    check('localization_original_string_dictionary_and_rule_comparison',localization_counts['comparison_runs']==37
          and localization_counts['native_assertions']==1987 and localization_counts['plural_rule_values']==8496
          and localization_counts['original_records_unchanged']==2236 and not localization_result['differences'])
    check('localization_explicit_behavioral_adjustments',localization_counts['intentional_adjusted_records']==8
          and {(r['kind'],r['mode']) for r in localization_result['intentional_differences']}=={('grammar','mutations'),('runtime','setters'),('runtime','edges')})
    check('localization_failure_lifetime_and_independent_calls',localization_counts['hardening_assertions']==74
          and localization_counts['independent_calls']==1024 and not localization_result['hardening'][0]['exit_code'])
    localization_delta=report('evidence/localization/link_delta.json')
    check('localization_link_delta',localization_delta['before']==52 and localization_delta['after']==36
          and len(localization_delta['resolved'])==16 and not localization_delta['added'] and not localization_delta['remaining_localization_symbols']
          and hashes_match(localization_delta['evidence'])
          and not set(localization_delta['resolved']).intersection(r['decorated_or_c_symbol'] for r in rows('evidence/sdk_x64/link_unresolved_candidates.csv')))
    localization_provider_stage=report('Stage/Localization/review_bundle.json')
    check('localization_provider_review_stage',localization_provider_stage['status']=='LOCALIZATION_PROVIDER_COMPONENT_REVIEW_BUNDLE_READY'
          and localization_provider_stage['counts']==localization_counts and hashes_match(localization_provider_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in localization_provider_stage['files']))
    check('localization_component_runtime_scope',not any((localization['game_launched'],localization['gamecore_loaded'],
          localization_result['game_launched'],localization_result['gamecore_loaded'],localization_delta['gamecore_linked'],
          localization_provider_stage['gamecore_linked'],localization_provider_stage['game_launched'])))
    from world_builder_types_evidence import validate as validate_world_builder_types
    world_types,world_result,world_entry=validate_world_builder_types()
    check('world_builder_types_production_provenance',world_entry in x64_link['providers'] and len(world_types['objects'])==2
          and world_types['sdk_port_manifest']==x64['manifest'] and len(world_result['production_proof']['candidate'])==3)
    check('world_builder_types_original_comparison',len(world_result['comparisons'])==9
          and sum(r['exact'] for r in world_result['comparisons'])==8
          and sum(r['intentional_self_assignment_fix'] for r in world_result['comparisons'])==1)
    check('world_builder_types_wire_and_operation_oracles',world_result['wire_bytes']==112 and world_result['wire_oracle_matched']
          and len(world_result['cross_reads'])==2 and world_result['operation_oracle']=='18a4fd15'
          and world_result['operations_per_architecture']==2048 and world_result['operation_oracle_matched'])
    check('world_builder_types_failure_and_independent_calls',world_result['fault_failures']==17 and world_result['fault_successes']==6
          and world_result['independent_calls']==4096 and sum(r['checks'] for r in world_result['runs'] if r['mode']=='hardening')==626)
    world_delta=report('evidence/world_builder/types/link_delta.json')
    required_world_types={'??0CvWorldBuilderMapTypeDesc@@QEAA@XZ','?Add@TypeMap@CvWorldBuilderMapTypeDesc@@QEAAIPEBD@Z',
                          '?Contains@CvWorldBuilderMapTypeGroup@@QEBA_NPEBD@Z'}
    check('world_builder_types_link_delta',world_delta['before']==localization_delta['after']==36 and world_delta['after']==33
          and set(world_delta['resolved'])==required_world_types and not world_delta['added'] and hashes_match(world_delta['evidence'])
          and not required_world_types.intersection(r['decorated_or_c_symbol'] for r in rows('evidence/sdk_x64/link_unresolved_candidates.csv')))
    world_stage=report('Stage/WorldBuilderTypes/review_bundle.json')
    check('world_builder_types_review_stage',world_stage['status']=='WORLD_BUILDER_TYPES_REVIEW_READY'
          and hashes_match(world_stage['files']) and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in world_stage['files']))
    check('world_builder_types_scope',not any((world_types['game_launched'],world_types['gamecore_loaded'],world_result['game_launched'],
          world_result['gamecore_loaded'],world_result['game_multicore_verified'],world_result['full_world_builder_verified'],
          world_delta['gamecore_linked'],world_stage['game_launched'],world_stage['gamecore_linked'],world_stage['full_world_builder_verified'])))
    from world_builder_mod_data_evidence import validate as validate_world_mod_data
    from world_builder_mod_access import patches as world_mod_access_patches
    mod_data,mod_result,mod_entry=validate_world_mod_data()
    mod_base=numeric_ledger['unchanged_world_builder_mod_baseline'];mod_prior=json.loads(Path(mod_base['path']).read_text(encoding='utf-8'))
    check('world_builder_mod_data_sdk_access_baseline',hashes_match([mod_base]) and len(mod_prior['patches'])==482
          and [p for p in patch_plan['patches'] if not p['id'].startswith(('world_mod_access_','world_map_access_','world_map_bridge_access_','logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]==mod_prior['patches']
          and [p for p in patch_plan['patches'] if p['id'].startswith('world_mod_access_')]==world_mod_access_patches()
          and len(patch_plan['patches'])==693)
    check('world_builder_mod_data_production_provenance',mod_entry in x64_link['providers'] and len(mod_data['objects'])==2
          and mod_data['sdk_port_manifest']==x64['manifest'] and mod_data['sdk_patch_specification']==x64['patch_specification']
          and len(mod_result['production_proof'])==len(mod_result['original_proof'])==16)
    check('world_builder_mod_data_original_and_wire_comparison',len(mod_result['comparisons'])==5
          and sum(r['exact'] for r in mod_result['comparisons'])==4 and len(mod_result['cross_reads'])==2
          and mod_result['wire_bytes']==2551 and mod_result['wire_oracle_matched'])
    check('world_builder_mod_data_fault_and_bounded_input',mod_result['fault_failures']==442 and mod_result['fault_successes']==9
          and mod_result['truncation_rejections']==1904 and sum(r['checks'] for r in mod_result['runs'] if r['mode']=='hardening')==6104
          and mod_result['independent_calls']==256)
    check('world_builder_mod_data_explicit_default_fix',mod_result['fresh_storage_initializes_defaults']
          and sum(r['intentional_fresh_default_initialization'] for r in mod_result['comparisons'])==1)
    mod_delta=report('evidence/world_builder/mod_data/link_delta.json')
    check('world_builder_mod_data_link_delta',mod_delta['before']==world_delta['after']==33 and mod_delta['after']==17
          and set(mod_delta['resolved'])==set(mod_result['required_symbols']) and len(mod_delta['resolved'])==16
          and not mod_delta['added'] and not mod_delta['remaining_mod_data_symbols'] and hashes_match(mod_delta['evidence'])
          and not set(mod_delta['resolved']).intersection(r['decorated_or_c_symbol'] for r in rows('evidence/sdk_x64/link_unresolved_candidates.csv')))
    mod_stage=report('Stage/WorldBuilderModData/review_bundle.json')
    check('world_builder_mod_data_review_stage',mod_stage['status']=='WORLD_BUILDER_MOD_DATA_REVIEW_READY'
          and hashes_match(mod_stage['files']) and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in mod_stage['files']))
    check('world_builder_mod_data_scope',mod_data['sdk_access_declarations_integrated'] and mod_result['sdk_access_declarations_integrated']
          and not any((mod_data['gamecore_loaded'],mod_data['game_launched'],mod_result['gamecore_loaded'],mod_result['game_launched'],
          mod_result['full_world_builder_verified'],mod_result['game_multicore_verified'],mod_delta['gamecore_linked'],
          mod_stage['gamecore_linked'],mod_stage['game_launched'],mod_stage['full_world_builder_verified'])))
    from world_builder_map_wire_evidence import validate as validate_map_wire
    map_wire,map_wire_result=validate_map_wire()
    map_rows=map_wire_result['corpus'];map_recovered=[r for r in map_rows if r['recovery_bits']]
    check('world_builder_map_file_production',len(map_wire['objects'])==2 and len(map_wire_result['production_proof'])==3)
    check('world_builder_map_file_installed_corpus',len(map_rows)==130 and map_wire_result['installed_inputs']==128
          and all(r['model_matched'] and r['wire_model_matched'] and r['original_read']['public_summary_matches'] for r in map_rows))
    check('world_builder_map_file_exact_and_recovered',sum(r['exact_roundtrip'] for r in map_rows)==127 and len(map_recovered)==3
          and all(r['original_read']['semantic_state_preserved'] for r in map_recovered)
          and sum(r['original_read']['semantic_bytes'] for r in map_recovered)==1521051)
    check('world_builder_map_file_bounds_and_failure',map_wire_result['hardening']['checks']==13639
          and map_wire_result['hardening']['fault_failures']==146 and map_wire_result['hardening']['fault_successes']==3
          and map_wire_result['hardening']['truncation_rejections']==6530)
    check('world_builder_map_file_changed_output_original_read',map_wire_result['mutation']['original_read_matches'])
    map_wire_stage=report('Stage/WorldBuilderMapFiles/review_bundle.json')
    check('world_builder_map_file_review_stage',map_wire_stage['status']=='WORLD_BUILDER_MAP_FILES_REVIEW_READY'
          and hashes_match(map_wire_stage['files']) and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in map_wire_stage['files']))
    check('world_builder_map_file_scope',not any((map_wire['sdk_map_object_integration'],map_wire['gamecore_loaded'],map_wire['game_launched'],
          map_wire_result['sdk_map_object_integration'],map_wire_result['gamecore_loaded'],map_wire_result['game_launched'],
          map_wire_result['game_multicore_verified'],map_wire_stage['sdk_map_object_integration'],map_wire_stage['gamecore_linked'],map_wire_stage['game_launched'])))
    from world_builder_map_object_evidence import validate as validate_map_object
    map_object,map_object_result,map_object_link=validate_map_object()
    from world_builder_map_access import patches as map_object_patches
    from world_builder_map_bridge_access import patches as map_bridge_patches
    map_base=numeric_ledger['unchanged_world_builder_map_baseline'];map_prior=json.loads(Path(map_base['path']).read_text(encoding='utf-8'))
    map_prefixes=('world_map_access_','world_map_bridge_access_')
    check('world_builder_map_sdk_access_baseline',hashes_match([map_base]) and len(map_prior['patches'])==488
          and [p for p in patch_plan['patches'] if not p['id'].startswith(map_prefixes+('logging_callers_','bootstrap_callers_','debug_callers_','globals_callers_','construction_callers_','host_callers_','db_postprocess_', 'db_loader_', 'info_cleanup_' ,'db_cache_', 'startup_owners_', 'gc_lifecycle_', 'lua_enum_', 'lua_registration_', 'lua_fractal_', 'fractal_numeric_', 'lua_borrowed_'))]==map_prior['patches']
          and [p for p in patch_plan['patches'] if p['id'].startswith(map_prefixes)]==map_object_patches()+map_bridge_patches()
          and len(patch_plan['patches'])==693 and map_object['sdk_port_manifest']==x64['manifest'])
    check('world_builder_map_object_native_production',len(map_object['objects'])==1 and len(map_object_result['native_sdk_symbol_proof'])==8)
    check('world_builder_map_object_original_comparison',len(map_object_result['runs'])==11
          and map_object_result['exact_state_records']==25 and map_object_result['exact_state_bytes']==66867)
    check('world_builder_map_object_hidden_reference_fix',sum(bool(r['intentional_adjustment']) for r in map_object_result['runs'])==1
          and any(r['case']=='hidden-handles' and r['intentional_adjustment'] for r in map_object_result['runs']))
    check('world_builder_map_object_failure_and_capacity',map_object_result['hardening']['checks']==131322
          and map_object_result['hardening']['cpp_allocation_failures']==24 and map_object_result['hardening']['successful_retries']==4)
    check('world_builder_map_object_link_experiment',map_object_link['before']==15 and map_object_link['after']==5
          and len(map_object_link['resolved'])==10 and not map_object_link['added'] and not map_object_link['official_link_report_replaced'])
    map_object_stage=report('Stage/WorldBuilderMapObject/review_bundle.json')
    check('world_builder_map_object_review_stage',map_object_stage['status']=='WORLD_BUILDER_MAP_OBJECT_REVIEW_READY'
          and hashes_match(map_object_stage['files']) and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in map_object_stage['files']))
    check('world_builder_map_object_scope',map_object['sdk_access_declarations_integrated'] and map_object_link['sdk_access_declarations_integrated']
          and map_object_stage['sdk_access_declarations_integrated'] and not any((map_object['file_bridge_implemented'],
          map_object_result['gamecore_linked'],map_object_result['gamecore_loaded'],map_object_result['game_launched'],
          map_object_link['gamecore_linked'],map_object_link['gamecore_loaded'],map_object_link['game_launched'],
          map_object_stage['file_bridge_implemented'],map_object_stage['gamecore_linked'],map_object_stage['game_launched'])))
    from world_builder_map_bridge_evidence import validate as validate_map_bridge
    map_bridge,map_bridge_result,map_bridge_link=validate_map_bridge()
    from world_builder_map_bridge_evidence import provider as map_bridge_provider
    _,_,map_bridge_entry=map_bridge_provider()
    check('world_builder_map_full_sdk_link',map_bridge_entry in x64_link['providers'] and len(x64_link['providers'])==16
          and map_bridge['sdk_port_manifest']==x64['manifest'] and map_bridge['sdk_patch_specification']==x64['patch_specification']
          and x64_link['linker_unresolved_symbol_total']==0 and map_bridge_link['official_response_unresolved_count']==0
          and map_bridge_link['baseline_excluded_providers']==['WorldBuilderMapBridge','FileSystem','Logging'])
    map_integration=report('evidence/world_builder/map_bridge/sdk_integration.json')
    check('world_builder_map_coherent_integration_record',map_integration['status']=='WORLD_BUILDER_MAP_SDK_INTEGRATION_PASS_NOT_GAME_RUNTIME'
          and hashes_match(map_integration[k] for k in ('verifier','gamecore_build','gamecore_link','map_build','map_conformance','map_link_trial',
              'map_object_conformance','dependency_refresh','baseline_patch_plan','patch_recipe'))
          and (map_integration['patch_count'],map_integration['added_access_declarations'],map_integration['gamecore_objects'],map_integration['providers'],map_integration['official_unresolved_symbols'])==(693,7,161,16,0)
          and map_integration['build_attempt']==x64['attempt'] and map_integration['map_headers_identical_to_compiled_sdk']
          and map_integration['production_filesystem_implemented'] and map_integration['gamecore_linked']
          and not any(map_integration[k] for k in ('sdk_object_layout_changed','original_game_or_sdk_changed','gamecore_loaded','game_launched','game_multicore_verified')))
    check('world_builder_map_bridge_native_production',len(map_bridge['objects'])==4 and len(map_bridge_result['native_sdk_symbol_proof'])==7
          and map_bridge['file_bridge_implemented'] and map_bridge_result['sdk_map_file_object_integration'])
    check('world_builder_map_bridge_original_corpus',len(map_bridge_result['corpus'])==130
          and sum(r['exact_observed_state'] for r in map_bridge_result['corpus'])==129
          and all(r['original_reread']['exact'] for r in map_bridge_result['corpus']))
    check('world_builder_map_bridge_legacy9_wire_correction',sum(bool(r['legacy9_correction']) for r in map_bridge_result['corpus'])==1
          and all(r['legacy9_correction']['candidate_matches_wire_bits'] and r['legacy9_correction']['original_instruction_sequence_matches']
                  for r in map_bridge_result['corpus'] if r['legacy9_correction']))
    check('world_builder_map_bridge_remap_and_reuse',len(map_bridge_result['mode_comparisons'])==12
          and all(r['exact_observed_state'] for r in map_bridge_result['mode_comparisons']))
    check('world_builder_map_bridge_failure_preservation',map_bridge_result['hardening']['checks']==16669
          and map_bridge_result['hardening']['cpp_allocation_failures']==267 and map_bridge_result['hardening']['successful_retries']==3
          and map_bridge_result['hardening']['truncation_rejections']==6530)
    check('world_builder_map_bridge_link_experiment',map_bridge_link['before']==15 and map_bridge_link['after']==2
          and len(map_bridge_link['resolved'])==13 and not map_bridge_link['added'] and not map_bridge_link['official_link_report_replaced'])
    map_bridge_stage=report('Stage/WorldBuilderMapBridge/review_bundle.json')
    check('world_builder_map_bridge_review_stage',map_bridge_stage['status']=='WORLD_BUILDER_MAP_BRIDGE_REVIEW_READY'
          and hashes_match(map_bridge_stage['files']) and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in map_bridge_stage['files']))
    check('world_builder_map_bridge_scope',map_bridge['sdk_access_declarations_integrated'] and map_bridge_result['sdk_access_declarations_integrated']
          and map_bridge_link['sdk_access_declarations_integrated'] and map_bridge_stage['sdk_access_declarations_integrated']
          and not any((map_bridge['production_filesystem_implemented'],
          map_bridge_result['atomic_file_replace_verified'],map_bridge_result['gamecore_linked'],map_bridge_result['gamecore_loaded'],map_bridge_result['game_launched'],map_bridge_result['game_multicore_verified'],
          map_bridge_link['gamecore_linked'],map_bridge_link['gamecore_loaded'],map_bridge_link['game_launched'],
          map_bridge_stage['production_filesystem_implemented'],map_bridge_stage['atomic_file_replace_verified'],map_bridge_stage['gamecore_linked'],map_bridge_stage['game_launched'])))
    from filesystem_evidence import validate as validate_filesystem,validate_link as validate_filesystem_link
    filesystem,filesystem_result,filesystem_entry=validate_filesystem();filesystem_link=validate_filesystem_link()
    check('filesystem_native_sdk_provider',filesystem_entry in x64_link['providers'] and filesystem['map_provider']==map_bridge_entry)
    check('filesystem_real_disk_and_map_tests',filesystem_result['execution']['checks']==1973 and filesystem_result['map_execution']['checks']==113
          and filesystem_result['execution']['failure_cases']==21 and filesystem_result['map_execution']['failure_cases']==12)
    check('filesystem_gamecore_link_delta',filesystem_link['before']==2 and filesystem_link['after']==1
          and filesystem_link['official_link']['sha256']==digest(PROJECT/'evidence/sdk_x64/link_analysis.json'))
    filesystem_stage=report('Stage/FileSystem/review_bundle.json')
    check('filesystem_review_stage',filesystem_stage['status']=='FILESYSTEM_REVIEW_READY' and hashes_match(filesystem_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in filesystem_stage['files']))
    check('filesystem_runtime_scope',filesystem_result['windows_file_io_executed']
          and not any(filesystem_result[k] for k in ('original_concrete_filesystem_oracle_available','power_loss_recovery_verified','pak_catalog_implemented','gamecore_loaded','game_launched','game_multicore_verified')))
    from logging_evidence import validate as validate_logging,validate_callers as validate_logging_callers,validate_link as validate_logging_link
    logging,logging_result,logging_entry=validate_logging();logging_link=validate_logging_link();logging_callers=validate_logging_callers()
    check('logging_native_sdk_provider',logging_entry in x64_link['providers'] and logging['filesystem_provider']==filesystem_entry
          and logging['sdk_port_manifest']==x64['manifest'] and logging['sdk_patch_specification']==x64['patch_specification'])
    check('logging_literal_sdk_caller_inventory',len(logging_callers['calls'])==155
          and len({r['file'] for r in logging_callers['calls']})==38
          and sum(p['id'].startswith('logging_callers_') for p in patch_plan['patches'])==48)
    check('logging_real_disk_and_failure_tests',logging_result['execution']['checks']==2169
          and logging_result['execution']['fault_cases']==19 and logging_result['execution']['exit_code']==0)
    check('logging_shared_file_records',logging_result['shared_records']==logging_result['shared_unique']==1600
          and logging_result['shared_exact_set'])
    check('logging_actual_sdk_prepared_text',logging_result['sdk_caller_records']==155 and logging_result['sdk_caller_exact'])
    logging_regression=json.loads(Path(logging_result['missing_error_code_regression']['path']).read_text(encoding='utf-8'))
    check('logging_missing_error_code_regression',hashes_match([logging_result['missing_error_code_regression']])
          and logging_regression['status']=='LOG_WRITE_FALSE_WITH_ZERO_ERROR_REPRODUCED' and logging_regression['exit_code']==2)
    check('logging_gamecore_link_delta',logging_link['before']==1 and logging_link['after']==0
          and logging_link['official_link']['sha256']==digest(PROJECT/'evidence/sdk_x64/link_analysis.json'))
    logging_stage=report('Stage/Logging/review_bundle.json')
    check('logging_review_stage',logging_stage['status']=='LOGGING_REVIEW_READY' and hashes_match(logging_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in logging_stage['files'])
          and logging_stage['official_gamecore_unresolved']==x64_link['linker_unresolved_symbol_total'])
    check('logging_runtime_scope',logging_result['windows_log_io_executed']
          and not any(logging_result[k] or logging_stage[k] for k in ('original_concrete_logger_oracle_available',
              'power_loss_recovery_verified','gamecore_loaded','game_launched','game_multicore_verified')))
    from debug_evidence import validate as validate_debug
    debug,debug_result,debug_link=validate_debug()
    check('debug_native_symbol_provider',debug['runtime']=='/MD' and debug_result['execution']['checks']==1730
          and debug_result['execution']['exit_code']==0 and debug_result['fault_cases']==19)
    check('debug_local_pdb_and_serialized_queries',debug_result['local_pdb_source_line']==22
          and debug_result['workers']==8 and debug_result['symbol_queries']==512 and debug_result['backend_overlap']==0)
    check('debug_real_gamecore_dll_link_candidate',debug_link['before']==3 and debug_link['after']==0
          and debug_link['gamecore_objects']==161 and debug_link['providers']==16
          and debug_link['runs'][1]['generated_dll'] and debug_link['runs'][1]['exit_code']==0
          and debug_link['official_link']['sha256']==digest(PROJECT/'evidence/sdk_x64/link_analysis.json'))
    debug_stage=report('Stage/Debug/review_bundle.json')
    check('debug_candidate_review_stage',debug_stage['status']=='DEBUG_SYMBOL_AND_LINK_CANDIDATE_REVIEW_READY'
          and hashes_match(debug_stage['files']) and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in debug_stage['files'])
          and debug_stage['candidate_dll_built'] and debug_stage['candidate_unresolved']==0 and debug_stage['official_unresolved']==0)
    check('debug_unfinished_bootstrap_and_game_scope',debug_result['windows_dbghelp_executed']
          and not any(debug_result[k] for k in ('original_debug_runtime_compared','sdk_stack_walk_verified',
              'official_gamecore_integrated','loader_lock_bootstrap_fixed','gamecore_loaded','game_launched','game_multicore_verified'))
          and not any(debug_link[k] for k in ('official_report_replaced','loader_lock_bootstrap_fixed','gamecore_loaded','game_launched','game_multicore_verified')))
    from debug_stack_evidence import validate as validate_debug_stack
    _,stack_result,stack_entry=validate_debug_stack()
    check('debug_stack_compiled_sdk_template',len(patch_plan['patches'])==693
          and sum(p['id'].startswith('debug_callers_') for p in patch_plan['patches'])==1
          and next(p for p in x64_link['providers'] if p['name']=='Debug')['stack_walk_callers']==stack_entry)
    check('debug_stack_actual_native_frames',stack_result['execution']['checks']==1081
          and stack_result['execution']['exit_code']==0 and stack_result['native_stack_traces']==257
          and stack_result['sdk_template_executed'])
    check('debug_stack_shared_symbol_serialization',stack_result['workers']==8
          and stack_result['concurrent_stack_traces']==256 and stack_result['backend_overlap']==0)
    check('debug_stack_failure_and_original_boundary',stack_result['backend_cases']==9
          and stack_result['invalid_context_cases']==3 and stack_result['original_null_context_observed_at_instrumented_api'])
    check('debug_stack_review_stage',debug_stage['sdk_stack_walk_checks']==1081 and debug_stage['sdk_stack_walk_verified'])
    check('debug_stack_scope',not any(stack_result[k] for k in (
          'original_null_context_passed_to_windows','native_stack_termination_proves_complete_trace',
          'get_call_stack_and_callstack_formatting_implemented','gamecore_loaded','game_launched','game_multicore_verified')))
    from bootstrap_evidence import validate as validate_bootstrap
    bootstrap,bootstrap_result,bootstrap_entry=validate_bootstrap()
    check('bootstrap_registered_compiled_callers',bootstrap_entry==x64_link['bootstrap_caller_conformance']
          and debug_link['bootstrap_callers']==bootstrap_entry and debug_link['explicit_bootstrap_integrated'])
    check('bootstrap_preserved_patch_baseline',len(patch_plan['patches'])==693
          and sum(p['id'].startswith('bootstrap_callers_') for p in patch_plan['patches'])==8)
    check('bootstrap_lifecycle_and_context_failures',[r['checks'] for r in bootstrap_result['runs'][:2]]==[501,118]
          and bootstrap_result['lifecycle_failures']==12 and bootstrap_result['context_creation_failures']==10)
    check('bootstrap_reproduced_original_defects',bootstrap_result['duplicate_original_context_reproduced']
          and bootstrap_result['partial_original_constructor_reproduced'])
    check('bootstrap_single_context_for_concurrent_requests',bootstrap_result['workers']==8
          and bootstrap_result['concurrent_start_calls']==256)
    bootstrap_stage=report('Stage/Bootstrap/review_bundle.json')
    check('bootstrap_review_stage',bootstrap_stage['status']=='BOOTSTRAP_CALLERS_REVIEW_READY'
          and hashes_match(bootstrap_stage['files']) and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in bootstrap_stage['files'])
          and bootstrap_stage['sdk_callers_compiled'] and bootstrap_stage['compiled_sdk_objects']==161)
    check('bootstrap_boundary_test_scope',bootstrap_result['context_adapter_types_instrumented']
          and not any(bootstrap_result[k] or bootstrap_stage.get(k,False) for k in ('actual_gamecore_context_executed','gamecore_loaded','game_launched','game_multicore_verified')))
    from globals_cleanup_evidence import validate as validate_globals_cleanup
    cleanup,cleanup_result,cleanup_entry=validate_globals_cleanup()
    check('globals_cleanup_compiled_sdk_bodies',cleanup_entry==x64_link['globals_cleanup_conformance']
          and len(patch_plan['patches'])==693
          and sum(p['id'].startswith('globals_callers_') for p in patch_plan['patches'])==1)
    check('globals_cleanup_original_and_candidate_regression',
          [r['checks'] for r in cleanup_result['runs']]==[11542,11604]
          and cleanup_result['cases_per_variant']==132 and cleanup_result['original_leaked_holders']==128
          and cleanup_result['original_leaked_entries']==608 and cleanup_result['original_leaked_arrays']==608
          and cleanup_result['candidate_live_ownership_after_cleanup']==0)
    cleanup_stage=report('Stage/GlobalsCleanup/review_bundle.json')
    check('globals_cleanup_source_build_stage',cleanup_stage['status']=='GLOBALS_CLEANUP_CALLERS_REVIEW_READY'
          and cleanup_stage['native_checks']==23146 and cleanup_stage['compiled_sdk_objects']==161
          and hashes_match(cleanup_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in cleanup_stage['files'])
          and port_stage.get('globals_cleanup_integrated')
          and any(r['source']==str(PROJECT/'Stage/GlobalsCleanup/review_bundle.json') for r in port_stage['files']))
    check('globals_cleanup_scope',cleanup_result['exact_cleanup_bodies_executed']
          and cleanup_result['other_owners_and_host_instrumented']
          and not any(cleanup_result[k] for k in ('whole_gc_init_uninit_verified','duplicate_gc_shutdown_verified',
              'gamecore_loaded','game_launched','game_multicore_verified')))
    from construction_evidence import validate as validate_construction
    construction,construction_result,construction_entry=validate_construction()
    check('construction_matches_compiled_sdk',construction_entry==x64_link['construction_conformance']
          and len(patch_plan['patches'])==693
          and sum(p['id'].startswith('construction_callers_') for p in patch_plan['patches'])==3)
    check('construction_original_defects_and_retry',
          [r['checks'] for r in construction_result['runs']]==[7902,7876]
          and construction_result['game_failure_cases']==13 and construction_result['map_failure_cases']==13
          and construction_result['successful_constructions_per_variant']==30
          and construction_result['original_constructor_defects_reproduced']
          and construction_result['candidate_constructor_storage_and_counter_restored'])
    construction_stage=report('Stage/Construction/review_bundle.json')
    check('construction_source_build_stage',construction_stage['status']=='CONSTRUCTION_CALLERS_REVIEW_READY'
          and construction_stage['native_checks']==15778 and construction_stage['compiled_sdk_objects']==161
          and hashes_match(construction_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in construction_stage['files'])
          and port_stage.get('construction_cleanup_integrated')
          and any(r['source']==str(PROJECT/'Stage/Construction/review_bundle.json') for r in port_stage['files']))
    check('construction_runtime_scope',construction_result['exact_sdk_bodies_executed']
          and construction_result['game_reset_timer_host_containers_instrumented']
          and not any(construction_result[k] for k in ('whole_gc_lifecycle_verified','host_side_effects_rolled_back',
              'real_game_reset_database_io_executed','gamecore_loaded','game_launched','game_multicore_verified')))
    from host_binding_evidence import validate as validate_host_binding
    host_binding,host_result,host_entry=validate_host_binding()
    check('host_binding_matches_compiled_sdk',host_entry==x64_link['host_binding_conformance']
          and len(patch_plan['patches'])==693
          and sum(p['id'].startswith('host_callers_') for p in patch_plan['patches'])==4)
    check('host_binding_failure_and_concurrency',
          [r['checks'] for r in host_result['runs']]==[14,1866]
          and host_result['original_defects_reproduced'] and host_result['candidate_failure_preservation_verified']
          and host_result['private_heap_host_destroyed_before_heap'] and host_result['heap_failure_retry_verified']
          and host_result['concurrent_mutation_busy_rejections']==512 and host_result['reentrant_mutation_busy_rejections']==200)
    host_stage=report('Stage/HostBinding/review_bundle.json')
    check('host_binding_source_build_stage',host_stage['status']=='HOST_BINDING_CALLERS_REVIEW_READY'
          and host_stage['native_checks']==1880 and host_stage['compiled_sdk_objects']==161
          and hashes_match(host_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in host_stage['files'])
          and port_stage.get('host_binding_integrated')
          and any(r['source']==str(PROJECT/'Stage/HostBinding/review_bundle.json') for r in port_stage['files']))
    check('host_binding_runtime_scope',host_result['exact_sdk_callers_and_release_dispatch_executed']
          and host_result['host_and_context_instrumented']
          and not any(host_result[k] for k in ('all_engine_interface_slots_verified','borrower_quiescence_enforced',
              'whole_gc_lifecycle_verified','gamecore_loaded','game_launched','game_multicore_verified')))
    from database_postprocess_evidence import validate as validate_database_postprocess
    post_build,post_result,post_entry=validate_database_postprocess()
    check('database_postprocess_matches_compiled_sdk',post_entry==x64_link['database_postprocess_conformance']
          and len(patch_plan['patches'])==693
          and sum(p['id'].startswith('db_postprocess_') for p in patch_plan['patches'])==3)
    check('database_postprocess_sql_failures_and_rules',
          [r['checks'] for r in post_result['runs']]==[820,1109,64]
          and post_result['normal_rule_outputs_equal'] and post_result['trigger_failure_cases']==8
          and post_result['outer_transaction_cases']==4 and post_result['deferred_commit_failure_rolled_back']
          and post_result['logger_exception_cleanup_verified'] and post_result['sqlite_whole_transaction_abort_propagated_as_exception']
          and len(post_result['corpus_comparisons'])==2
          and all(r['equal_defines_resources'] for r in post_result['corpus_comparisons']))
    post_stage=report('Stage/DatabasePostprocess/review_bundle.json')
    check('database_postprocess_source_build_stage',post_stage['status']=='DATABASE_POSTPROCESS_CALLERS_REVIEW_READY'
          and post_stage['native_checks']==1993 and post_stage['compiled_sdk_objects']==161
          and hashes_match(post_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in post_stage['files'])
          and port_stage.get('database_postprocess_integrated')
          and any(r['source']==str(PROJECT/'Stage/DatabasePostprocess/review_bundle.json') for r in port_stage['files']))
    check('database_postprocess_runtime_scope',post_result['global_database_accessor_instrumented']
          and post_result['same_accepted_x64_database_used_for_both_algorithms']
          and not any(post_result[k] for k in ('original_windows_game_binary_executed','gc_init_failure_propagation_implemented',
              'whole_gc_lifecycle_verified','all_sqlite_failure_modes_rollback_guaranteed',
              'gamecore_loaded','game_launched','game_multicore_verified')))
    from database_loader_evidence import validate as validate_database_loader
    loader_build,loader_result,loader_entry=validate_database_loader()
    check('database_loader_matches_compiled_sdk',loader_entry==x64_link['database_loader_conformance']
          and len(patch_plan['patches'])==693
          and sum(p['id'].startswith('db_loader_') for p in patch_plan['patches'])==5)
    check('database_loader_lifetime_cache_and_retry',
          [r['checks'] for r in loader_result['runs']]==[28,4180]
          and loader_result['candidate_restart_cycles']==64 and loader_result['candidate_exact_heap_frees']==208
          and loader_result['allocation_failure_retries']==16 and loader_result['heap_shutdown_failure_retries']==16
          and loader_result['caller_owned_references_preserved'] and loader_result['fresh_loader_reads_changed_rule_rows']
          and loader_result['factory_before_init_shutdown_verified'])
    loader_stage=report('Stage/DatabaseLoader/review_bundle.json')
    check('database_loader_source_build_stage',loader_stage['status']=='DATABASE_LOADER_CALLERS_REVIEW_READY'
          and loader_stage['native_checks']==4208 and loader_stage['compiled_sdk_objects']==161
          and hashes_match(loader_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in loader_stage['files'])
          and port_stage.get('database_loader_integrated')
          and any(r['source']==str(PROJECT/'Stage/DatabaseLoader/review_bundle.json') for r in port_stage['files']))
    check('database_loader_runtime_scope',loader_result['other_game_owners_and_prefetch_instrumented']
          and loader_result['real_private_windows_heap_used']
          and not any(loader_result[k] for k in ('external_borrower_quiescence_enforced', 'all_game_cache_teardown_complete',
              'gc_init_failure_propagation_implemented','whole_gc_lifecycle_verified','original_windows_game_binary_executed',
              'gamecore_loaded','game_launched','game_multicore_verified')))
    from info_cleanup_evidence import validate as validate_info_cleanup
    info_build,info_result,info_entry=validate_info_cleanup()
    check('info_cleanup_matches_compiled_sdk',info_entry==x64_link['info_cleanup_conformance']
          and len(patch_plan['patches'])==693
          and sum(p['id'].startswith('info_cleanup_') for p in patch_plan['patches'])==4)
    check('info_cleanup_ownership_failure_and_retry',
          [r['checks'] for r in info_result['runs']]==[3182,9557]
          and info_result['candidate_rule_collections_cleared']==40 and info_result['candidate_string_arrays_cleared']==2
          and info_result['partial_cleanup_states_per_variant']==82 and info_result['prefetch_failures_per_variant']==9
          and info_result['candidate_preserves_original_exceptions_and_published_entries']
          and info_result['candidate_caller_cleanup_and_retry_verified'] and info_result['borrower_cleanup_order_verified'])
    info_stage=report('Stage/InfoCleanup/review_bundle.json')
    check('info_cleanup_source_build_stage',info_stage['status']=='INFO_CLEANUP_CALLERS_REVIEW_READY'
          and info_stage['native_checks']==12739 and info_stage['compiled_sdk_objects']==161
          and hashes_match(info_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in info_stage['files'])
          and port_stage.get('info_cleanup_integrated')
          and any(r['source']==str(PROJECT/'Stage/InfoCleanup/review_bundle.json') for r in port_stage['files']))
    check('info_cleanup_runtime_scope',info_result['info_entries_and_game_borrowers_instrumented']
          and not any(info_result[k] for k in ('all_sql_and_cache_result_failures_propagated',
              'all_concrete_info_constructors_destructors_executed','external_borrower_quiescence_enforced',
              'gc_init_failure_propagation_implemented','whole_gc_lifecycle_verified','original_windows_game_binary_executed',
              'gamecore_loaded','game_launched','game_multicore_verified')))
    from database_cache_evidence import validate as validate_database_cache
    cache_build,cache_result,cache_entry=validate_database_cache()
    check('database_cache_matches_compiled_sdk',cache_entry==x64_link['database_cache_conformance']
          and len(patch_plan['patches'])==693 and sum(p['id'].startswith('db_cache_') for p in patch_plan['patches'])==7)
    check('database_cache_failure_propagation_and_corpus',
          [r['checks'] for r in cache_result['runs']]==[10893,12529] and cache_result['required_collection_count']==62
          and cache_result['candidate_error_propagation_and_retry_verified']
          and cache_result['candidate_database_phase_stops_before_players_teams']
          and cache_result['candidate_flavor_failure_preserves_previous_array']
          and cache_result['candidate_local_reference_destroy_dispatch_verified']
          and len(cache_result['corpus_comparisons'])==2)
    cache_stage=report('Stage/DatabaseCache/review_bundle.json')
    check('database_cache_source_build_stage',cache_stage['status']=='DATABASE_CACHE_CALLERS_REVIEW_READY'
          and cache_stage['native_checks']==23422 and cache_stage['compiled_sdk_objects']==161
          and hashes_match(cache_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in cache_stage['files'])
          and port_stage.get('database_cache_integrated')
          and any(r['source']==str(PROJECT/'Stage/DatabaseCache/review_bundle.json') for r in port_stage['files']))
    check('database_cache_runtime_scope',cache_result['concrete_info_and_game_stages_instrumented']
          and not any(cache_result[k] for k in ('entire_cache_atomic_rollback_verified','whole_gc_lifecycle_verified',
              'original_windows_game_binary_executed','gamecore_loaded','game_launched','game_multicore_verified')))
    from startup_owners_evidence import validate as validate_startup_owners
    owners_build,owners_result,owners_entry=validate_startup_owners()
    check('startup_owners_match_compiled_sdk',owners_entry==x64_link['startup_owners_conformance']
          and len(patch_plan['patches'])==693 and sum(p['id'].startswith('startup_owners_') for p in patch_plan['patches'])==9)
    check('startup_owners_failures_retries_and_normal_actions',
          [r['checks'] for r in owners_result['runs']]==[864826,860910]
          and owners_result['actor_failure_cases_per_variant']==191 and owners_result['action_failure_cases_per_variant']==135
          and owners_result['normal_action_order_and_metadata_equal'] and owners_result['candidate_direct_child_and_action_cleanup_verified']
          and owners_result['candidate_duplicate_array_preservation_verified'] and owners_result['candidate_failure_retry_verified'])
    owners_stage=report('Stage/StartupOwners/review_bundle.json')
    check('startup_owners_source_build_stage',owners_stage['status']=='STARTUP_OWNERS_CALLERS_REVIEW_READY'
          and owners_stage['native_checks']==1725736 and owners_stage['compiled_sdk_objects']==161
          and hashes_match(owners_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in owners_stage['files'])
          and port_stage.get('startup_owners_integrated')
          and any(r['source']==str(PROJECT/'Stage/StartupOwners/review_bundle.json') for r in port_stage['files']))
    check('startup_owners_runtime_scope',owners_result['child_types_reset_and_hotkey_services_instrumented']
          and not any(owners_result[k] for k in ('player_member_initializer_list_executed','all_nested_child_implementations_verified',
              'entire_action_metadata_transactional','whole_gc_lifecycle_verified','gamecore_loaded','game_launched','game_multicore_verified')))
    from gc_lifecycle_evidence import validate as validate_gc_lifecycle
    lifecycle_build,lifecycle_result,lifecycle_entry=validate_gc_lifecycle()
    check('gc_lifecycle_match_compiled_sdk',lifecycle_entry==x64_link['gc_lifecycle_conformance']
          and len(patch_plan['patches'])==693 and sum(p['id'].startswith('gc_lifecycle_') for p in patch_plan['patches'])==12)
    check('gc_lifecycle_failures_retries_normal_order',lifecycle_result['normal_call_order_equal']
          and [r['observations'] for r in lifecycle_result['runs']]==[[48,938],[48,0]]
          and (lifecycle_result['cleanup_checkpoints'],lifecycle_result['reset_type_count'],lifecycle_result['cleanup_retry_cases'],
               lifecycle_result['concurrent_busy_calls'],lifecycle_result['reentrant_boundaries'],lifecycle_result['restart_cycles'])==(45,68,4,512,49,64))
    lifecycle_stage=report('Stage/GCLifecycle/review_bundle.json')
    check('gc_lifecycle_source_build_stage',lifecycle_stage['status']=='GC_LIFECYCLE_CALLERS_REVIEW_READY'
          and lifecycle_stage['native_checks']==1747 and lifecycle_stage['compiled_sdk_objects']==161
          and hashes_match(lifecycle_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in lifecycle_stage['files'])
          and port_stage.get('gc_lifecycle_integrated')
          and any(r['source']==str(PROJECT/'Stage/GCLifecycle/review_bundle.json') for r in port_stage['files']))
    check('gc_lifecycle_runtime_scope',lifecycle_result['exact_gc_context_bodies_executed']
          and lifecycle_result['real_type_reset_executed'] and lifecycle_result['game_children_host_database_instrumented']
          and not any(lifecycle_result[k] for k in ('all_transitive_children_and_game_state_recovery_verified',
              'borrower_quiescence_enforced','gamecore_loaded','game_launched','game_multicore_verified')))
    from lua_enums_evidence import validate as validate_lua_enums
    enum_build,enum_result,enum_entry=validate_lua_enums()
    check('lua_enum_match_compiled_sdk',enum_entry==x64_link['lua_enum_conformance']
          and len(patch_plan['patches'])==693 and sum(p['id'].startswith('lua_enum_') for p in patch_plan['patches'])==3)
    check('lua_enum_real_db_lua_flua_failures',enum_result['native_checks']==5808 and len(enum_result['runs'])==28
          and enum_result['sql_failures_per_variant']==4 and enum_result['original_register_failure_suppression_reproduced'])
    check('lua_enum_x64_unwind_hypothesis_corrected',not enum_result['original_query_leaks_reproduced']
          and enum_result['original_x64_unwind_verified'] and enum_result['original_lua_failures_without_leak']=={'O2':56,'_od':56})
    check('lua_enum_success_values_and_failure_recovery',enum_result['corpus_rows']==58
          and enum_result['candidate_table_identity_and_normal_values_preserved']
          and enum_result['candidate_allocation_failures_per_optimization']=={'lua':57,'cpp':51}
          and enum_result['candidate_statement_stack_heap_recovery'] and enum_result['candidate_db_failures_before_table_mutation'])
    enum_stage=report('Stage/LuaEnums/review_bundle.json')
    check('lua_enum_source_build_stage',enum_stage['status']=='LUA_ENUM_CALLERS_REVIEW_READY'
          and hashes_match(enum_stage['files']) and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in enum_stage['files'])
          and port_stage.get('lua_enum_integrated') and enum_stage['native_checks']==5808)
    check('lua_enum_runtime_scope',enum_result['real_flua_wrapper_executed'] and not any(enum_result[k] for k in
          ('all_static_enum_families_registered','gamecore_loaded','game_launched','whole_game_library_registration_verified','game_multicore_verified')))
    from lua_registration_evidence import validate as validate_lua_registration
    registration_build,registration_result,registration_entry=validate_lua_registration()
    check('lua_registration_match_compiled_sdk',registration_entry==x64_link['lua_registration_conformance']
          and len(patch_plan['patches'])==693 and sum(p['id'].startswith('lua_registration_') for p in patch_plan['patches'])==10)
    check('lua_registration_exact_metadata_and_identity',registration_result['exact_sdk_function_bodies']==22
          and sum(registration_result['method_counts'].values())==1228
          and registration_result['candidate_success_metadata_and_borrowed_identity_preserved'])
    check('lua_registration_failure_short_circuit',registration_result['original_failure_suppression_reproduced']
          and registration_result['candidate_short_circuit_verified'] and registration_result['sequence_failure_boundaries']==7)
    check('lua_registration_allocation_and_cleanup',registration_result['native_checks']==243512
          and len(registration_result['runs'])==20 and registration_result['candidate_stack_lock_heap_recovery']
          and registration_build['entire_scoped_template_included']
          and sum(v['failures'] for v in registration_result['failure_sweeps']['candidate']['lua'].values())==3474)
    registration_stage=report('Stage/LuaRegistration/review_bundle.json')
    check('lua_registration_source_build_stage',registration_stage['status']=='LUA_REGISTRATION_CALLERS_REVIEW_READY'
          and hashes_match(registration_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in registration_stage['files'])
          and port_stage.get('lua_registration_integrated') and registration_stage['native_checks']==243512)
    check('lua_registration_runtime_scope',registration_result['real_lua_flua_executed'] and not any(registration_result[k] for k in
          ('gameplay_handler_bodies_executed','real_game_object_lifetimes_verified','gamecore_loaded',
           'game_launched','whole_game_library_registration_verified','game_multicore_verified')))
    from lua_fractal_evidence import validate as validate_lua_fractal
    fractal_build,fractal_result,fractal_entry=validate_lua_fractal()
    check('lua_fractal_match_compiled_sdk',fractal_entry==x64_link['lua_fractal_conformance']
          and len(patch_plan['patches'])==693 and sum(p['id'].startswith('lua_fractal_') for p in patch_plan['patches'])==7
          and fractal_build['candidate_matches_generated_sdk'])
    check('lua_fractal_type_and_destroy_boundaries',fractal_result['foreign_input_kinds']==3
          and fractal_result['original_duplicate_destruction_observed'] and fractal_result['original_foreign_native_dispatch_observed']
          and fractal_result['candidate_exactly_once_and_post_destroy_rejection'])
    check('lua_fractal_allocation_finalization_recovery',fractal_result['native_checks']==48986
          and len(fractal_result['runs'])==22 and fractal_result['tested_lifetime_optimizations']==['/O2','/Od']
          and fractal_result['lifetime_failure_sweeps']['candidate']=={'lua_failures':19,'missing_finalizers':0}
          and fractal_result['gc_objects_per_variant']==128
          and fractal_result['candidate_weak_registry_survives_finalization_without_retaining_objects'])
    check('lua_fractal_optional_arguments_before_output',fractal_result['original_missing_optional_arguments_misread']
          and fractal_result['candidate_defaults_parse_before_output']
          and fractal_result['omitted_defaults_vs_original_explicit_defaults_scenarios']==6)
    check('lua_fractal_calculation_and_rng_preserved',fractal_result['math_and_rng_traces_equal']
          and fractal_result['unchanged_input_math_scenarios']==12 and fractal_result['math_scenarios']==18
          and fractal_result['height_samples_per_scenario']==1290)
    fractal_stage=report('Stage/LuaFractal/review_bundle.json')
    check('lua_fractal_source_build_stage',fractal_stage['status']=='LUA_FRACTAL_CALLERS_REVIEW_READY'
          and hashes_match(fractal_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in fractal_stage['files'])
          and port_stage.get('lua_fractal_integrated') and fractal_stage['native_checks']==48986
          and any(r['source']==str(PROJECT/'Stage/LuaFractal/review_bundle.json') for r in port_stage['files']))
    check('lua_fractal_runtime_scope',fractal_result['real_lua_flua_executed']
          and fractal_result['real_calculation_bodies_executed_with_adapters'] and fractal_result['native_lifetime_is_instrumented']
          and not any(fractal_result[k] for k in ('actual_fractal_dynamic_resource_leak_proven','all_fractal_numeric_inputs_validated',
              'borrowed_game_object_lifetimes_verified','gamecore_loaded','game_launched','game_multicore_verified')))
    from fractal_numeric_evidence import validate as validate_fractal_numeric
    numeric_fractal_build,numeric_fractal_result,numeric_fractal_entry=validate_fractal_numeric()
    check('fractal_numeric_match_compiled_sdk',numeric_fractal_entry==x64_link['fractal_numeric_conformance']
          and len(patch_plan['patches'])==693 and sum(p['id'].startswith('fractal_numeric_') for p in patch_plan['patches'])==9
          and numeric_fractal_build['candidate_matches_generated_sdk'])
    check('fractal_numeric_original_faults_reproduced',numeric_fractal_result['original_integer_zero_division_reproduced']
          and numeric_fractal_result['original_asan_fault_inputs']==['exponent_8','short_hint_buffer','small_rift_grid']
          and all(r['expected_outcome_observed'] for r in numeric_fractal_result['runs']))
    check('fractal_numeric_normal_calculation_and_rng',numeric_fractal_result['normal_heights_and_rng_match']
          and numeric_fractal_result['normal_native_scenarios_per_configuration']==3186
          and numeric_fractal_result['normal_lua_scenarios_per_configuration']==18
          and numeric_fractal_result['tested_optimizations']==['/O2','/Od'])
    check('fractal_numeric_failure_preserves_state_and_rng',numeric_fractal_result['candidate_preflight_failure_preserves_state_and_rng']
          and numeric_fractal_result['invalid_initialization_and_ridge_rejections']=={'candidate':29,'candidate_od':29,'candidate_asan':29})
    check('fractal_numeric_ridge_budget_and_wide_blend',numeric_fractal_result['candidate_retry_failure_preserves_heights']
          and not numeric_fractal_result['candidate_retry_failure_rolls_back_rng']
          and numeric_fractal_result['retry_observations']['candidate'][0]=='2570'
          and numeric_fractal_result['wide_blend_observations']['candidate']==['6','0'])
    check('fractal_numeric_lua_recovery_and_sanitizer',numeric_fractal_result['candidate_cpp_errors_become_lua_errors']
          and numeric_fractal_result['candidate_asan_boundaries_rifts_lua_errors_pass']
          and numeric_fractal_result['native_checks']==556730 and len(numeric_fractal_result['runs'])==30)
    numeric_fractal_stage=report('Stage/FractalNumeric/review_bundle.json')
    check('fractal_numeric_source_build_stage',numeric_fractal_stage['status']=='FRACTAL_NUMERIC_CALLERS_REVIEW_READY'
          and hashes_match(numeric_fractal_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in numeric_fractal_stage['files'])
          and port_stage.get('fractal_numeric_integrated') and numeric_fractal_stage['native_checks']==556730)
    check('fractal_numeric_runtime_scope',numeric_fractal_result['native_fractal_class_and_calculation_bodies_executed']
          and numeric_fractal_result['numeric_rng_and_container_owner_adapters']
          and not any(numeric_fractal_result[k] for k in ('borrowed_game_object_lifetimes_verified','gamecore_loaded','game_launched','game_multicore_verified')))
    from lua_borrowed_evidence import validate as validate_lua_borrowed
    borrowed_build,borrowed_result,borrowed_entry=validate_lua_borrowed()
    borrowed_audit=report('evidence/lua_borrowed/lifecycle_audit.json')
    check('lua_borrowed_match_compiled_sdk',borrowed_entry==x64_link['lua_borrowed_conformance']
          and len(patch_plan['patches'])==693 and sum(p['id'].startswith('lua_borrowed_') for p in patch_plan['patches'])==64
          and borrowed_build['candidate_matches_generated_sdk'] and borrowed_result['actual_owner_hooks_integrated'])
    borrowed_runs={r['variant']:r['results'] for r in borrowed_result['runs']}
    check('lua_borrowed_references_reject_stale_and_forged',borrowed_result['native_checks']==27168
          and borrowed_runs['candidate']==borrowed_runs['candidate_od']
          and borrowed_runs['original']==borrowed_runs['original_od']
          and borrowed_runs['original']['forged_accepted']==3 and borrowed_runs['original']['stale_accepted']==1
          and borrowed_runs['candidate']['forged_accepted']==borrowed_runs['candidate']['stale_accepted']==0
          and borrowed_runs['candidate']['reentrant_rejections']==5 and borrowed_runs['candidate']['partial_registrations']==0)
    check('lua_borrowed_native_proxy_and_container_lifetimes',borrowed_audit['candidate_native_hooks']==34
          and len(borrowed_audit['bindings'])==9 and len(borrowed_audit['native_interfaces'])==4
          and borrowed_runs['candidate']['cross_translation_unit_registry']
          and borrowed_runs['candidate']['container_operations']==12
          and borrowed_runs['candidate']['tracked_at_exit']==borrowed_runs['candidate']['container_blocks_at_exit']==0)
    check('lua_borrowed_deal_self_assignment',borrowed_runs['candidate']['deal_copy_cases']==4
          and borrowed_runs['original']['deal_self_copy_losses']==3 and borrowed_runs['candidate']['deal_self_copy_losses']==0)
    borrowed_registry_lines=[line.strip() for line in read_text(Path(x64_link['link_map']['path'])).splitlines()
          if '?state@?1??State@ZeroSisLuaBorrowed@@' in line]
    check('lua_borrowed_linked_shared_registry',hashes_match([x64_link['link_map']])
          and borrowed_registry_lines==[x64_link['lua_borrowed_shared_registry_symbol']])
    borrowed_stage=report('Stage/LuaBorrowed/review_bundle.json')
    check('lua_borrowed_source_build_stage',borrowed_stage['status']=='LUA_BORROWED_CALLERS_REVIEW_READY'
          and hashes_match(borrowed_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in borrowed_stage['files'])
          and port_stage.get('lua_borrowed_integrated') and borrowed_stage['native_checks']==27168
          and any(r['source']==str(PROJECT/'Stage/LuaBorrowed/review_bundle.json') for r in port_stage['files']))
    check('lua_borrowed_runtime_scope',borrowed_result['native_proxy_bodies_executed']
          and borrowed_result['unit_destructor_body_with_instrumented_services_executed']
          and borrowed_result['sdk_container_operations_with_instrumented_elements_executed']
          and not any(borrowed_result[k] for k in ('actual_gameplay_owner_lifecycle_executed','gamecore_loaded','game_launched')))
    check("x64_allocator_tested_inputs", allocator["status"] == "SDK_X64_ALLOCATOR_COMPONENT_PASS"
          and hashes_match({"path": path, "sha256": value} for path, value in allocator["input_sha256"].items()))
    check("x64_allocator_execution_artifacts", hashes_match([allocator["build"], allocator["native_execution"],
          {"path": allocator["build"]["log"], "sha256": allocator["build"]["log_sha256"]}])
          and allocator["build"]["compiler_and_linker_warnings"] == 0
          and pe_header(Path(allocator["build"]["path"]))["architecture"] == "x64")
    native_allocator = report("evidence/sdk_x64_allocator/native_execution.json")
    check("x64_allocator_execution_accounting", native_allocator == allocator["native"]
          and native_allocator["status"] == "PASS" and native_allocator["scope"] == "SDK_HEADER_ALLOCATOR_ONLY"
          and native_allocator["layout_cases"] == 196 and native_allocator["allocations_above_4g"] == 197
          and native_allocator["rejected_overflows"] == 4 and native_allocator["pointer_bytes"] == 8
          and 0xffffffff < int(native_allocator["lowest_address"], 16) <= int(native_allocator["highest_address"], 16))
    check("x64_link_diagnostic_artifacts", hashes_match([x64_link[key] for key in
          ("analyzer", "diagnostics", "link_log", "link_response", "unresolved_candidates")]
          + [{"path": str(PROJECT / "evidence/sdk_x64/build_result.json"), "sha256": x64_link["build_result_sha256"]}])
          and x64_link["build_attempt"] == x64["attempt"])
    x64_diagnostics = rows("evidence/sdk_x64/compiler_diagnostics.csv")
    check("x64_link_and_warning_accounting", len(rows("evidence/sdk_x64/link_unresolved_candidates.csv"))
          == x64_link["parsed_unresolved_candidate_count"] == x64_link["linker_unresolved_symbol_total"]
          and x64_link["parsed_count_matches_linker"] and not x64_link["unparsed_unresolved_diagnostics"]
          and len(x64_diagnostics) == x64_link["diagnostic_locations"]
          and dict(Counter(row["code"] for row in x64_diagnostics)) == x64_link["diagnostic_location_codes"]
          and dict(Counter(row["category"] for row in x64_diagnostics)) == x64_link["diagnostic_categories"]
          and x64_link["status"] == "X64_LINK_PROBE_SUCCEEDED_UNTESTED" and x64_link["link_exit_code"] == 0
          and x64_link["generated_dll"] is not None and hashes_match([x64_link["generated_dll"]]))
    check("x64_port_review_stage", port_stage["status"] == "X64_COMPILE_AND_LINK_REVIEW_BUNDLE_READY"
          and hashes_match(port_stage["files"])
          and hashes_match({"path": row["source"], "sha256": row["sha256"]} for row in port_stage["files"])
          and port_stage["object_files"] == len(x64["objects"])
          and port_stage["modified_sdk_files"] == sum(bool(row["patch_ids"]) for row in x64_manifest)
          and port_stage['gamecore_linked'] and port_stage['explicit_bootstrap_integrated']
          and port_stage["unresolved_link_symbols"] == x64_link["linker_unresolved_symbol_total"])

    contract = report("evidence/m1/contract_inventory.json")
    declarations = rows("evidence/m1/interface_declarations.csv")
    calls = rows("evidence/m1/typed_call_candidates.csv")
    check("contract_inventory_rows", len(declarations) == contract["pure_virtual_declarations"]
          and len(calls) == contract["typed_call_candidates"]
          and dict(Counter(row["resolution"] for row in calls)) == contract["resolution_counts"])
    link = report("evidence/link_dependencies/link_inventory.json")
    requirements = rows("evidence/link_dependencies/object_requirements.csv")
    publics = rows("evidence/link_dependencies/final_map_publics.csv")
    check("link_inventory_rows", len(requirements) == link["unresolved_by_game_objects_unique_names"]
          and len(publics) == link["map_public_entries"]
          and sum(row["sdk_library"] == "True" for row in publics) == link["map_sdk_public_entries"]
          and len(rows("evidence/link_dependencies/object_summary.csv")) == link["object_files"])
    check("no_game_runtime_claim", not any((numeric["game_launched"], sdk["game_launched"],
          contract["game_launched"], link["game_launched"], numeric["multicore_game_execution_verified"],
          crc["game_launched"], jobs["game_launched"], jobs["game_multicore_execution_verified"],
          state["game_launched"], state["actual_gamecore_state_commit_verified"],
          state["game_multicore_execution_verified"], state["performance_improvement_measured"],
          x64["game_launched"], x64["runtime_verified"], x64["x64_gamecore_linked"],
          x64_link["game_launched"], x64_link["runtime_verified"], allocator["game_launched"], allocator["gamecore_runtime_verified"],
          port_stage["game_launched"], port_stage["gamecore_runtime_verified"])))
    check("numeric_and_lua_scope", not any((boundaries["game_launched"], boundaries["gamecore_runtime_verified"],
          lua_component["game_launched"], lua_component["gamecore_linked"], lua_provider["game_launched"],
          lua_provider["gamecore_runtime_verified"], lua_reference["game_launched"], lua_delta["gamecore_linked"])))

    from native_host_evidence import validate as validate_native_host
    host_build, host_result, host_bundle, host_services = validate_native_host()
    host_stage = report('Stage/NativeHost/review_bundle.json')
    check('native_host_sdk_abi_and_compiled_inputs', all(b['compiler_inputs'] for b in host_build['builds'].values())
          and [(r['slots'],r['implemented_slots']) for r in host_services] == [(260,22),(152,7)])
    check('native_host_lifecycle_and_real_data_scope', host_result['native_checks'] == 20948
          and len(host_result['runs']) == 24 and host_result['gamecore_lifecycle_instrumented']
          and host_result['real_database_localization_executed'] and not host_result['gamecore_loaded'])
    check('native_host_runtime_bundle', len(host_bundle['files']) == 9 and hashes_match(host_bundle['files'])
          and host_result['malformed_bundle_cases'] == 14 and host_result['bundle_inputs_unchanged'])
    check('native_host_map_audio_services', host_result['map_audio_native_checks'] == 12615
          and host_result['concurrent_map_reads'] == 4096 and host_result['concurrent_audio_lookups'] == 8192
          and [r['audio_counts'] for r in host_result['data_observations']] == [[10,7,1],[10,7,1]])
    check('native_host_script_sdk_calls_and_actual_lua', host_result['script_native_checks']==3201
          and host_result['real_lua_provider_executed'] and not host_result['game_script_libraries_registered']
          and [r['script_observation'] for r in host_result['data_observations']]==[[45,13,58],[45,16,61]])
    check('native_host_script_allocation_recovery_and_lifecycle', host_result['script_allocation_failures']=={'cpp':6,'lua_create':423,'lua_execute':135,'lua_event':117}
          and host_result['script_lifecycle_with_instrumented_core'] and host_result['script_foreign_thread_rejections']==160
          and host_result['script_restart_cycles']==32 and not host_result['original_event_semantics_verified'])
    check('native_host_installed_script_catalog_and_metadata', host_result['script_asset_native_checks']==1076
          and host_result['script_catalog_files']==36 and len(host_result['map_script_metadata'])==18
          and host_result['script_catalog_malformed_cases']==79
          and host_result['script_asset_failures']=={'catalog_cpp':498,'include_cpp':6,'include_lua':69})
    check('native_host_script_utility_binding_scope', host_result['script_utility_binding_compiled']
          and host_result['script_utility_registration_with_fixture'] and host_result['script_utility_binding_failure_cases']==3
          and not host_result['game_script_libraries_registered'] and not host_result['gamecore_loaded'])
    check('native_host_review_stage', host_stage['status'] == 'NATIVE_HOST_REVIEW_READY_NOT_GAME_RUNTIME'
          and hashes_match(host_stage['files']) and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in host_stage['files']))
    from host_exception_boundary_evidence import validate as validate_host_exceptions
    exception_build,exception_result,exception_entry=validate_host_exceptions()
    exception_stage=report('Stage/HostExceptionBoundary/review_bundle.json')
    check('native_host_foreign_exception_binding',report('evidence/host/services.json')['host_exception_boundary']==exception_entry
          and all(any(Path(r['path'])==PROJECT/'Source/Host/HostFailure.h' for r in host_build['builds'][name]['compiler_inputs'])
                  for name in ('host','tests')))
    check('native_host_foreign_exception_original_faults',exception_result['original_access_violations']==14
          and len(exception_result['runs'])==36 and exception_result['integrated_native_reference_error_executed'])
    check('native_host_foreign_exception_cleanup_and_retry',exception_result['candidate_successes']==22
          and exception_result['native_checks']==874 and exception_result['retained_host_error_after_unload']
          and exception_result['cleanup_diagnostic_copy_survives_retry'] and exception_result['long_and_null_message_defense']
          and exception_result['initialization_cleanup_dual_failure'] and exception_result['normal_restart_after_failure'])
    check('native_host_foreign_exception_review',exception_stage['status']=='HOST_EXCEPTION_BOUNDARY_REVIEW_READY'
          and hashes_match(exception_stage['files'])
          and hashes_match({'path':r['source'],'sha256':r['sha256']} for r in exception_stage['files'])
          and hashes_match([host_stage['host_exception_boundary_review']]))
    check('native_host_foreign_exception_scope',exception_result['real_fixture_dll_unloaded']
          and not exception_result['gamecore_loaded'] and not exception_result['game_launched'])
    from host_script_access_evidence import validate as validate_script_access
    access_build,access_result,access_entry=validate_script_access()
    check('native_host_script_access_binding',report('evidence/host/services.json')['host_script_access']==access_entry
          and host_build['script_access_build']==access_entry['build']
          and host_result['script_access_conformance']==access_entry['conformance'])
    check('native_host_script_access_original_missing_guard',access_result['original_accepted_calls']==120
          and access_result['original_unlocked_callbacks']==36 and len(access_result['runs'])==4)
    check('native_host_script_access_rejection_and_recovery',access_result['candidate_rejected_calls']==120
          and access_result['native_checks']==1440 and host_result['script_access_native_checks']==1440
          and all(r['observations']['recovery'] and r['observations']['lifecycle_query_failures']
                  for r in access_result['runs'] if r['name'].startswith('candidate')))
    check('native_host_script_access_review',host_stage['host_script_access']==access_entry
          and host_stage['host_script_access_native_checks']==1440
          and any(Path(r['source'])==PROJECT/'docs/M3_HOST_SCRIPT_ACCESS.md' for r in host_stage['files']))
    check('native_host_script_access_runtime_scope',not access_result['gamecore_loaded']
          and not access_result['game_launched'] and not access_result['game_multicore_verified'])
    from host_runtime_evidence import validate as validate_actual_core_runtime
    runtime_result,runtime_entry=validate_actual_core_runtime()
    runtime_stage=report('Stage/NativeHost/RuntimeReview/review_bundle.json')
    check('actual_core_initialization_two_languages',runtime_result['status']=='ACTUAL_GAMECORE_INITIALIZATION_AND_LUA_PASS'
          and [row['language'] for row in runtime_result['runs']]==['en_US','ko_KR']
          and runtime_result['gamecore_initialization_verified'])
    check('actual_core_sdk_lua_and_objects',runtime_result['actual_sdk_library_registration_executed']
          and runtime_result['actual_player_team_ids_per_run']==[64,64]
          and runtime_result['retired_player_team_handles_checked_per_run']==[1,1])
    check('actual_core_shutdown_and_unload',runtime_result['gamecore_shutdown_and_unload_verified'])
    check('actual_core_runtime_review',runtime_stage['status']=='ACTUAL_GAMECORE_INITIALIZATION_REVIEW_READY'
          and runtime_stage['runtime']==runtime_entry and hashes_match(runtime_stage['files'])
          and hashes_match({'path':row['source'],'sha256':row['sha256']} for row in runtime_stage['files']))
    check('actual_core_runtime_scope',not runtime_result['new_game_verified']
          and not runtime_result['turn_execution_verified'] and not runtime_result['game_multicore_verified'])
    from host_game_info_evidence import validate as validate_host_game_info
    game_info_result,game_info_entry=validate_host_game_info()
    check('host_game_info_compiled_binding',host_build['game_info_build']==game_info_entry['build']
          and host_result['game_info_conformance']==game_info_entry['conformance']
          and report('evidence/host/services.json')['host_game_info']==game_info_entry)
    check('host_game_info_failures_and_recovery',game_info_result['native_checks']>0
          and all(row['lua_query_failures']>0 and row['cpp_query_failures']>0 and row['vm_creation_failures']>0
                  for row in game_info_result['runs']))
    check('host_game_info_review',host_stage['host_game_info']==game_info_entry
          and host_stage['host_game_info_native_checks']==game_info_result['native_checks']
          and any(Path(row['source'])==PROJECT/'Tests/sdk_host_game_info.cpp' for row in host_stage['files']))
    check('actual_core_game_info_sql_comparison',runtime_result['game_info_global_present']
          and runtime_result['game_info_sql_comparison_verified'] and len(runtime_result['game_info_tables'])==12)
    check('host_game_info_scope',not game_info_result['gamecore_loaded']
          and not game_info_result['original_game_info_equivalence_verified'])

    evidence_files = sorted({
        str(path): {"path": str(path), "sha256": digest(path)}
        for directory in ("Source/Numerics", "Source/Concurrency", "Source/State", "Source/BuildSupport", "Source/Porting", "Source/Providers", "Source/Host", "Source/HostExceptionBoundary", "Source/HostScriptAccess", "Source/LuaBorrowed", "Source/Assets", "Tests", "tools", "docs")
        for path in (PROJECT / directory).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    }.values(), key=lambda row: row["path"])
    evidence_files.append({"path": str(PROJECT / "README.md"), "sha256": digest(PROJECT / "README.md")})
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "EVIDENCE_AND_ARTIFACT_INTEGRITY_PASS" if not issues else "INTEGRITY_FAILED",
              "checks": checks, "issues": issues, "project_source_manifest": evidence_files,
              "native_numeric_component_execution_previously_verified": numeric["status"] == "ISOLATED_NATIVE_NUMERIC_CONFORMANCE_PASS",
              "native_crc_component_execution_previously_verified": crc["status"] == "SDK_BINARY_CRC_X86_X64_CONFORMANCE_PASS",
              "native_ordered_jobs_execution_previously_verified": jobs["status"] == "ISOLATED_X64_ORDERED_JOB_CONFORMANCE_PASS",
              "native_value_state_commit_execution_previously_verified": state["status"] == "ISOLATED_X64_VALUE_STATE_COMMIT_CONFORMANCE_PASS",
              "x86_reference_dll_built": sdk["status"] == "SDK_REFERENCE_BUILD_PASS",
              "x64_gamecore_cpp_objects_compiled": len(x64["objects"]),
              "x64_gamecore_unresolved_link_symbols": x64_link["linker_unresolved_symbol_total"],
              "native_x64_sdk_allocator_execution_previously_verified": allocator["status"] == "SDK_X64_ALLOCATOR_COMPONENT_PASS",
              "native_x64_numeric_boundaries_previously_verified": boundaries["status"] == "SDK_X64_NUMERIC_BOUNDARIES_PASS",
              "x64_gamecore_built": debug_link['runs'][1]['generated_dll'],
              "x64_gamecore_build_scope": "OFFICIAL_COMPILED_AND_LINKED_DLL_WITH_EXPLICIT_BOOTSTRAP; BOUNDED_INITIALIZATION_AND_RULES_RUNTIME_VERIFIED_SEPARATELY",
              "actual_gamecore_initialization_verified": runtime_result['gamecore_initialization_verified'],
              "actual_game_info_rule_queries_verified": runtime_result['game_info_sql_comparison_verified'],
              "new_game_verified": runtime_result['new_game_verified'], "turn_execution_verified": runtime_result['turn_execution_verified'],
              "x64_gamecore_link_candidate": debug_link['runs'][1]['dll'],
              "x64_gamecore_candidate_unresolved_symbols": debug_link['after'],
              "x64_gamecore_official_dll": x64_link["generated_dll"], "x64_gamecore_official_linked": x64_link["link_exit_code"]==0, "game_launched": False,
              "game_multicore_or_performance_verified": False,
              "scope": "HASH_AND_REPORT_INTEGRITY_ONLY_NOT_NEW_RUNTIME_OR_GAME_TEST"}
    (PROJECT / "evidence/project_verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "checks", "issues", "scope")}, ensure_ascii=False))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
