"""Publish the bounded framing diagnostics; preserve runtime and small backups."""
from __future__ import annotations
import sys
sys.dont_write_bytecode = True
import ctypes
from ctypes import wintypes
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path

PROJECT = Path(__file__).absolute().parents[1]
BASE = PROJECT / "evidence/retail_save_container/map_trace"
STAGE = BASE / "chunk_frames_component"


def main():
    assert os.name == "nt" and not sys.flags.optimize and len(sys.argv) == 1
    helper = PROJECT / "tools/probe_public_retail_save.py"
    assert hashlib.sha256(helper.read_bytes()).hexdigest() == "f2b340a42248f94ede0e2849bccfdfd8d1588c3c7b29d8c98526f2a7538aa962"
    import probe_public_retail_save as g
    assert Path(g.__file__).absolute() == helper
    def pinned(path, digest):
        row = g.artifact(path)
        assert row["sha256"] == digest, str(path)
        return row, g.read_json(path)
    public_pin, public = pinned(STAGE / "public_result.json", "9219e7b264e4190127a29f7d81f6bdfb403637221e1fd0d7ef275559dc7b614d")
    unit_pin, unit = pinned(STAGE / "test_e852fb22b6c91ccf4959/result.json", "c1752ad645d2ae30bdfcdbc84102d5042667fe0ac5dcab0119d9abb0242d0935")
    pre_pin, pre = pinned(BASE / "input_chunk_preflight.json", "28b185224fe8cc2ca555147c3583038d485a5bc6c15d804512de67e93e58b84a")
    baseline_pin = g.artifact(pre["protected_baseline"]["path"])
    assert baseline_pin["sha256"] == pre["protected_baseline"]["sha256"]
    baseline = g.read_json(Path(baseline_pin["path"]))
    revisions = {row["path"]: row for row in pre["intentional_metadata_revisions"].values()}
    protected = []
    for row in baseline["protected"]:
        expected = revisions.get(row["path"], row)
        actual = g.artifact(row["path"])
        assert all(actual[key] == expected[key] for key in ("bytes", "sha256", "file_identity"))
        if "mtime_ns" in expected:
            assert actual["mtime_ns"] == expected["mtime_ns"]
        protected.append(actual)
    assert len(protected) == 45 and unit["test"]["checks"] == 193
    assert public["forbidden_access_attempts"] == [] and len(public["child_commands"]) == 6
    summaries = []
    for case in public["cases"]:
        n = case["wire"]["observation"]
        assert len(case["header"]["observation"]["chunk_frames"]["frames"]) == 11
        assert n["game_map"]["plots"] == 4160 and n["teams_completed"] == 64 and case["zlib_eof"] is False
        assert all(n[key] is False for key in ("complete_save_verified", "restore_approved", "full_engine_goal_complete"))
        summaries.append({"fixture_id": case["fixture"]["id"], "inflated_bytes": case["inflated_bytes"],
            "inflated_sha256": case["inflated_sha256"], "map_end_offset": n["game_map"]["map_end_offset"],
            "plots": 4160, "teams": n["teams_completed"], "players": n["players_completed"],
            "array_records_completed": n["array_records_completed"], "supporting": n["supporting"],
            "last_completed_offset": n["last_completed_offset"], "remainder": n["remaining_input_bytes"],
            "zero_remainder": n["declared_sequence_has_zero_remainder"], "error": n["error"]})
    jpl, riva = summaries
    assert jpl["fixture_id"] == "jpl_before" and jpl["players"] == 35 and jpl["error"]["code"] == 6
    assert riva["fixture_id"] == "rivar_settler12" and riva["players"] == 64 and riva["zero_remainder"]
    out = g.ordinary(STAGE / "publication")
    assert not out.exists(), "Publication is single-use"
    index = PROJECT / "evidence/save_menu/20261013_original_screen/current_progress.json"
    document = PROJECT / "docs/M7_RETAIL_SAVE_BOUNDARY.md"
    before = {path: g.artifact(path) for path in (index, document)}
    originals = {path: path.read_bytes() for path in before}
    backups = {path: out / (path.name + ".before.gz") for path in before}
    backup_bytes = {path: gzip.compress(raw, mtime=0) for path, raw in originals.items()}
    assert all(gzip.decompress(backup_bytes[path]) == raw for path, raw in originals.items())
    source_paths = [PROJECT / name for name in ("Source/Host/RetailSaveChunkFrames.h", "Tests/retail_save_chunk_frames.cpp",
        "Tests/retail_public_probe.cpp", "tools/check_retail_inflate_input_chunks.py", "tools/trace_retail_length_prefixed_frames.py",
        "tools/verify_retail_chunk_frames.py", "tools/check_retail_length_frames.py", "tools/publish_retail_length_frames.py")]
    fixed_paths = [BASE / name for name in ("input_chunk_preflight.json", "input_chunk_comparison.json", "declared_frames_trace.json",
        "retail_public_probe.boolean_and_frames_change.11aa0940.json", "source_backups/retail_public_probe.before_boolean_and_frames.11aa0940.cpp.gz")]
    build_roots = [PROJECT / "Build/RetailChunkFrames/e852fb22b6c91ccf4959", PROJECT / "Build/RetailPublicProbe/f1b14e8ea0a23f2d14bc"]
    scope = source_paths + fixed_paths + [path for directory in [STAGE, *build_roots] for path in directory.rglob("*") if path.is_file()]
    scope = list(dict.fromkeys(scope))
    for directory in build_roots:
        assert {path.name for path in directory.iterdir()} == {"RetailPublicProbe.exe", "compile.rsp", "dependencies.json"}
    assert not list(STAGE.rglob("*failed_attempt.json"))
    current_inputs = [g.artifact(path) for path in scope]
    sdk_source = PROJECT / "Source/SDK_BNW_x64/CvGameCoreDLL_Expansion2/CvUnit.cpp"
    sdk_pin = g.artifact(sdk_source)
    assert sdk_pin["sha256"] == "92670270dbf6c031f7c4d2424b73528b691a95a37aebff060a661607a881a5a6"
    # Query allocation from FILE_STANDARD_INFO, not compressed/logical size.
    class Standard(ctypes.Structure):
        _fields_ = [("AllocationSize", ctypes.c_longlong), ("EndOfFile", ctypes.c_longlong),
            ("NumberOfLinks", wintypes.DWORD), ("DeletePending", ctypes.c_ubyte), ("Directory", ctypes.c_ubyte)]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    create, info, close = kernel.CreateFileW, kernel.GetFileInformationByHandleEx, kernel.CloseHandle
    create.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
    create.restype = wintypes.HANDLE
    info.argtypes = [wintypes.HANDLE,ctypes.c_int,ctypes.c_void_p,wintypes.DWORD]; info.restype = wintypes.BOOL
    close.argtypes = [wintypes.HANDLE]; close.restype = wintypes.BOOL
    def allocated(path):
        g.ordinary(path, file=True)
        handle = create(str(path), 0x80, 7, None, 3, 0x00200000, None)
        assert handle != ctypes.c_void_p(-1).value
        try:
            value = Standard()
            assert info(handle, 1, ctypes.byref(value), ctypes.sizeof(value))
            assert value.EndOfFile == path.stat().st_size and not value.Directory and not value.DeletePending
            return value.AllocationSize
        finally:
            assert close(handle)
    before_allocated = {path: allocated(path) for path in before}
    receipt, post = out / "progress_update.json", out / "post_checks.json"
    writable = {g.key(path) for path in [index, document, *backups.values(), receipt, post]}
    readable = {g.key(Path(row["path"])) for row in [*current_inputs, *protected, sdk_pin, public_pin, unit_pin, pre_pin, baseline_pin]}
    readable |= writable
    def audit(event, args):
        if event == "subprocess.Popen" or event.startswith(("socket.","urllib.","http.client.","ctypes.dlopen")) or event in ("os.system","os.startfile","os.remove","os.rmdir","os.rename","os.link","os.symlink"):
            raise RuntimeError("Forbidden publication action: " + event)
        if event == "os.mkdir" and g.key(args[0]) != g.key(out):
            raise RuntimeError("Unexpected publication directory")
        if event == "open" and isinstance(args[0],(str,bytes,os.PathLike)):
            key = g.key(args[0])
            writing = isinstance(args[1],str) and any(ch in args[1] for ch in "wax+") or isinstance(args[2],int) and bool(args[2] & (os.O_WRONLY|os.O_RDWR|os.O_CREAT|os.O_TRUNC|os.O_APPEND))
            assert key in (writable if writing else readable), "Unexpected publication path"
            if writing:
                writable.remove(key)
    sys.addaudithook(audit)
    out.mkdir()
    for path, backup in backups.items():
        with backup.open("xb") as stream:
            stream.write(backup_bytes[path])
    now = datetime.now(timezone.utc).isoformat()
    stage = {"status": "CPP_LENGTH_PREFIX_FRAMING_COMPONENT_AND_PUBLIC_WIRE_OBSERVED", "utc": now,
        "component_proof": unit_pin, "public_diagnostics": public_pin, "header": g.artifact(source_paths[0]),
        "test": g.artifact(source_paths[1]), "probe_source": g.artifact(source_paths[2]),
        "profile": "caller_declared_u32_length_payloads_to_raw_end", "frames_per_case": 11, "checks": 193,
        "cases": summaries, "later_length_words_previously_fed_to_zlib_bytes_per_case": 40,
        "producer_contract_verified": False, "zlib_stream_eof_observed": False, "retail_outer_sequence_verified": False,
        "complete_save_verified": False, "ruleset_compatibility_verified": False, "sdk_restore_verified": False,
        "integrated_into_current_host": False, "runtime_hold_unchanged": True, "full_engine_goal_complete": False}
    addition = """
## Current length-prefix framing and public wire diagnostics

The previous flat compressed-tail diagnostic passed ten later four-byte length words into zlib. Both pinned public files instead cover their exact raw remainder with eleven little-endian length/payload frames. The new `RetailSaveChunkFrames.h` requires an explicit caller profile and returns zero-copy spans, with typed bounds and budget errors. It does not identify the producer finish contract or approve loading. Existing Pregame prefix fields, canonical bool default and wire schema are unchanged. The optional public diagnostic selects the existing SDK-byte bool policy explicitly.

The x64 O2 framing component passes 193 checks, including 52 rejected inputs and 34 small literal cuts. Three cuts exactly on complete-frame boundaries are correctly accepted; there is no invented final-frame marker. The two eleven-frame length controls use opaque synthetic payloads. Both component and public executables import only Kernel32; no SDK, GameCore, Host or window executes.

The actual C++ header spans feed one Python zlib decoder per public file, with no reset or flush. Only RAM holds raw, inflated and embedded database bytes. JPL produces 21,151,963 bytes, Riva 16,727,961 bytes, matching the independently recorded output hashes. Neither reaches zlib stream EOF; producer completeness remains unverified. The fixed profile is awards=5, grand=4, projects=6, SDK-byte booleans, and the caller-declared Game/Map/64 Teams/64 Players/Supporting sequence. Its outer order is still an experiment.

Both files frame all 4,160 plots and their Map tails; exact Map ends are 6,926,871 (JPL) and 6,862,029 (Riva), matching the separate coordinate trace. Both frame 64 ordered Teams. Riva additionally frames all 64 Players, 30 cities, 66 units, one army, one operation and the 16,916-byte Supporting tail, ending at byte 16,727,961 with zero remainder. These are structural wire observations, not semantic state or restore validation.

JPL frames 35 Players, with 1,038,283 completed array records. The unchanged shared default budget is 1,048,576, leaving 10,293 records when slot 35 begins; it rejects at byte 15,367,711. No automatic retry, profile guessing, resynchronization, limit change or load approval was added. This later stage supersedes the older corruption-driven Map/Player-prefix failures only for these exact inputs and declared profiles. The retained partial observations remain historical evidence.

Evidence: `evidence/retail_save_container/map_trace/chunk_frames_component/test_e852fb22b6c91ccf4959/result.json`, `public_result.json`, and `publication/progress_update.json`. Only one current component build and one public diagnostic build were added; objects and environment scripts were retired. Source backups contain changed files only. Existing SDK/runtime bundles, launcher, original game, MODS, settings and user saves are untouched. Producer finish/completeness, the remaining JPL record-budget gate, real SDK restore and save reopening, original UI/3D/full gameplay and measured multicore performance remain open.
"""
    assert addition.splitlines()[1].encode() not in originals[document]
    with document.open("wb") as stream:
        stream.write(originals[document] + b"\n" + addition.encode("utf-8"))
    stage["documentation"] = g.artifact(document)
    progress = json.loads(originals[index].decode("utf-8-sig"))
    assert progress["schema"] and progress["full_engine_goal_complete"] is False and progress["latest_sdk_source_matches_base_link_candidate"] is False
    preserved = {key:progress[key] for key in ("schema","full_goal","requirements","default_publication","latest_source_matches_linked_candidate","latest_sdk_source_matches_base_link_candidate")}
    progress["utc"] = now
    progress["status"] = "RETAIL_FRAMING_RIVA_SEQUENCE_OBSERVED_JPL_RECORD_BUDGET_AND_RESTORE_PENDING"
    progress["current_goal_turn_classification"] = "progress"
    assert "retail_length_prefix_framing_stage" not in progress
    progress["retail_length_prefix_framing_stage"] = stage
    with index.open("wb") as stream:
        stream.write((json.dumps(progress,ensure_ascii=False,indent=2)+"\n").encode("utf-8"))
    reread = g.read_json(index)
    assert all(reread[key] == value for key,value in preserved.items())
    after = {path:g.artifact(path) for path in before}
    g.unchanged([row for row in protected if row["path"] not in {str(index),str(document)}] + current_inputs + [sdk_pin])
    g.write_json(receipt, {"schema":"zerosis.retail.length_frames.publication.v1","status":"PASS_BOUNDED_FRAMING_PROGRESS_PUBLICATION",
        "utc":now,"component":unit_pin,"public":public_pin,"changed_metadata":[{"before":before[path],"after":after[path],
        "backup":g.artifact(backups[path]),"backup_roundtrip_verified":True} for path in before],
        "protected_other_files_unchanged":43,"sdk_working_unit_source_unchanged":sdk_pin,"runtime_hold_unchanged":True,
        "sdk_or_game_executed":False,"full_engine_goal_complete":False})
    scope += [*backups.values(),receipt]
    # Existing modified metadata/probe bytes are not counted as wholly new data.
    new_scope = [path for path in scope if path != source_paths[2]]
    measurements, unique = [], set()
    for path in new_scope:
        row = g.artifact(path)
        row["allocated_file_data_bytes"] = allocated(path)
        ident = tuple(row["file_identity"])
        row["unique_file_identity_first_occurrence"] = ident not in unique
        unique.add(ident); measurements.append(row)
    allocated_total = sum(row["allocated_file_data_bytes"] for row in measurements if row["unique_file_identity_first_occurrence"])
    logical_total = sum(row["bytes"] for row in measurements if row["unique_file_identity_first_occurrence"])
    retired = unit["retired_logical_bytes"] + public["retired_logical_bytes"]
    g.write_json(post,{"schema":"zerosis.retail.length_frames.post.v1","status":"PASS_FRAMING_SOURCE_PUBLICATION_PROTECTION_AND_TIDINESS",
        "utc":now,"protected_files":[after.get(Path(row["path"]),row) for row in protected],
        "source_and_proof_files":measurements,"new_material_scope_unique_logical_bytes":logical_total,
        "new_material_scope_unique_allocated_file_data_bytes":allocated_total,
        "scope_excludes_this_post_receipt_existing_modified_metadata_and_existing_probe_source":True,
        "metadata_logical_delta_bytes":sum(after[path]["bytes"]-before[path]["bytes"] for path in before),
        "metadata_allocated_file_data_delta_bytes":sum(allocated(path)-before_allocated[path] for path in before),
        "probe_source_logical_delta_bytes":3517,"retired_intermediate_logical_bytes":retired,
        "retired_physical_allocation_or_volume_free_change_measured":False,
        "whole_project_storage_rescanned":False,"no_native_sdk_or_game_execution":True,"full_engine_goal_complete":False})
    print(json.dumps({"publication":g.artifact(receipt),"post":g.artifact(post),"retired_logical_bytes":retired,
        "new_material_scope_allocated_file_data_bytes":allocated_total,"new_material_scope_logical_bytes":logical_total,
        "metadata_logical_delta_bytes":sum(after[path]["bytes"]-before[path]["bytes"] for path in before)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
