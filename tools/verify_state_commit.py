"""Build/run x64 value-state publication checks. No GameCore or game state is loaded."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import struct
import zlib

from collect_baseline import PROJECT, digest
from native_build import build_program, checked_run


CASE_NAMES = [
    "commit_once_shared_request_and_immutable_snapshot",
    "foreign_owner_cannot_consume_request",
    "destroyed_owner_identity_cannot_be_reused",
    "competing_result_becomes_stale_after_commit",
    "new_session_rejects_old_work",
    "turn_phase_and_direct_replacement_invalidate_work",
    "unchanged_context_is_idempotent",
    "all_stamp_fields_are_bound",
    "missing_extra_duplicate_unsorted_unknown_jobs_rejected",
    "failed_and_cancelled_worker_results_are_not_applied",
    "domain_generation_owner_base_and_delta_rejected_atomically",
    "prepare_exception_rolls_back_and_request_is_terminal",
    "candidate_copy_and_publish_move_failure_preserve_state",
    "cancel_before_and_during_prepare_discards_candidate",
    "another_thread_can_cancel_while_candidate_is_prepared",
    "late_cancel_cannot_undo_published_state",
    "wrong_thread_cannot_commit_or_mutate_owner",
    "reentrant_commit_and_owner_mutation_rejected",
    "revision_and_session_exhaustion_do_not_wrap",
    "invalid_request_issuance_has_no_effect",
    "scheduling_statistics_do_not_affect_state_decisions",
]
RECORD = struct.Struct("<IIIQQQqQ")


def oracle():
    """Independent serial integer model: session/context, entity edits, then CRC deltas."""
    for scenario in range(24):
        for workers in (1, 2, 4):
            entities = [{"id": 0x100000000 + i + 1, "generation": 1, "owner": i % 4,
                         "value": 100000 + scenario * 101 + i * 17} for i in range(8)]
            session, revision, turn, phase, applied = 1, 0, 0, 0, 0
            for step in range(32):
                if step == 16:
                    session, revision, turn, phase = session + 1, 0, step, step % 3
                if (turn, phase) != (step, step % 3):
                    turn, phase, revision = step, step % 3, revision + 1
                if step and step % 7 == 0:
                    changed = entities[(step // 7) % len(entities)]
                    changed["generation"] += 1
                    changed["owner"] = (changed["owner"] + 1) % 4
                    revision += 1
                for entity in entities:
                    bits = entity["value"] & 0xffffffffffffffff
                    data = struct.pack("<6I", entity["id"] & 0xffffffff, entity["id"] >> 32,
                                       entity["generation"], entity["owner"], bits & 0xffffffff, bits >> 32)
                    raw_crc = zlib.crc32(data) ^ 0xffffffff
                    entity["value"] += raw_crc % 19 - 9
                applied += len(entities)
                revision += 1
                for entity in entities:
                    yield RECORD.pack(scenario, workers, step, session, revision, entity["id"], entity["value"], applied)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vs", type=Path, required=True)
    args = parser.parse_args()
    build = PROJECT / "Build/StateCommit/x64"
    evidence = PROJECT / "evidence/state_commit"
    sources = [PROJECT / "Source/State/VersionedState.h", PROJECT / "Source/Concurrency/OrderedBatch.h",
               PROJECT / "Source/Numerics/CvCompatibleCrc32.h", PROJECT / "Tests/state_commit_test.cpp",
               Path(__file__).resolve(), PROJECT / "tools/native_build.py"]
    before = {str(path): digest(path) for path in sources}
    executable = build_program(name="state_commit_test", architecture="x64", vs=args.vs, directory=build,
                               evidence=evidence, source=sources[3], includes=[PROJECT / "Source"])
    trace = build / "results.bin"
    execution = checked_run([executable["path"], trace], cwd=build, timeout=180)
    native = json.loads(execution.stdout.decode("utf-8"))
    native_path = evidence / "native_execution.json"
    native_path.write_text(json.dumps(native, indent=2) + "\n", encoding="utf-8")
    expected = b"".join(oracle())
    if (native["status"] != "PASS" or native["scope"] != "ISOLATED_VALUE_STATE_NOT_GAMECORE"
            or native["case_names"] != CASE_NAMES or native["checks_passed"] <= 0
            or native["scenarios"] != 24 or native["steps"] != 32 or native["workers"] != [1, 2, 4]
            or native["committed_batches"] != 24 * 3 * 32
            or native["state_records"] != len(expected) // RECORD.size):
        raise RuntimeError("Native state test coverage/accounting mismatch")
    if trace.read_bytes() != expected:
        raise RuntimeError("Published state trace differs from independent Python serial model")
    if any(digest(Path(path)) != value for path, value in before.items()):
        raise RuntimeError("State component input changed during execution")
    stage = PROJECT / "Stage/State"
    stage.mkdir(parents=True, exist_ok=True)
    staged = stage / "VersionedState.h"
    shutil.copyfile(sources[0], staged)
    dependencies = [{"path": str(PROJECT / "Stage/Concurrency/OrderedBatch.h"), "sha256": digest(sources[1])},
                    {"path": str(PROJECT / "Stage/Numerics/CvCompatibleCrc32.h"), "sha256": digest(sources[2])}]
    if any(not Path(row["path"]).is_file() or digest(Path(row["path"])) != row["sha256"] for row in dependencies):
        raise RuntimeError("Staged dependencies differ from the tested source dependencies")
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "ISOLATED_X64_VALUE_STATE_COMMIT_CONFORMANCE_PASS",
              "input_sha256": before, "build": executable,
              "named_cases_passed": len(CASE_NAMES), "checks_passed": native["checks_passed"],
              "case_names": CASE_NAMES, "scenarios": native["scenarios"], "steps_per_scenario": native["steps"],
              "worker_configurations": native["workers"], "committed_batches": native["committed_batches"],
              "state_records_compared_to_python": native["state_records"], "record_bytes": RECORD.size,
              "trace_bytes": len(expected), "trace": {"path": str(trace), "sha256": digest(trace)},
              "expected_trace_sha256": hashlib.sha256(expected).hexdigest(),
              "native_execution": {"path": str(native_path), "sha256": digest(native_path)},
              "stage_header": {"path": str(staged), "sha256": digest(staged)},
              "staged_test_dependencies": dependencies,
              "verified": ["owner-bound immutable value snapshots and shared request identity",
                           "in-memory at-most-once publication across copied requests/results",
                           "stale session/revision/turn/phase and foreign owner rejection",
                           "exact expected result IDs, count, order and ready/error checks",
                           "domain rejection, prepare exception and injected state copy/move failure preserve live state",
                           "cancellation before/during prepare, including cancellation from another thread",
                           "late cancellation does not undo published state",
                           "owner-thread and preparation reentrancy guards",
                           "session/revision overflow rejection and unchanged context idempotency",
                           "real OrderedBatch workers 1/2/4 produce matching Python-model state traces"],
              "not_verified": ["actual GameCore state extraction, entity rules or commit adapters",
                               "shallow/shared mutable state or arbitrary callbacks with external effects",
                               "persistent replay/deduplication or save/load recovery",
                               "process crash/power loss durability", "real memory exhaustion",
                               "batch-counter exhaustion injection", "race sanitizer or formal memory-model proof",
                               "physical-core instruction overlap", "whole-state copying cost or game speedup"],
              "game_launched": False, "actual_gamecore_state_commit_verified": False,
              "game_multicore_execution_verified": False, "performance_improvement_measured": False}
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    (evidence / "conformance.json").write_text(serialized, encoding="utf-8")
    (stage / "verification.json").write_text(serialized, encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "named_cases_passed", "checks_passed", "committed_batches",
          "state_records_compared_to_python", "game_multicore_execution_verified")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
