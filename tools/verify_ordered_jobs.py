"""Build/run x64 ordered-job component checks, without any GameCore or game state."""
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


def oracle():
    for batch in range(24):
        for workers in (1, 2, 4):
            for index in range(64):
                seed = 0xa5a5a5a5 ^ (((batch + 1) * 1664525 + index * 1013904223) & 0xffffffff)
                length = (index * 37 + batch * 13) % 1025
                data = bytes((k * 73 + (k >> 3) * 19 + index * 7 + batch * 11) & 255 for k in range(length))
                value = zlib.crc32(data, seed ^ 0xffffffff) ^ 0xffffffff
                yield struct.pack("<4I", batch, workers, batch * 100000 + index, value)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vs", type=Path, required=True)
    args = parser.parse_args()
    build = PROJECT / "Build/OrderedJobs/x64"
    evidence = PROJECT / "evidence/ordered_jobs"
    sources = [PROJECT / "Source/Concurrency/OrderedBatch.h", PROJECT / "Source/Numerics/CvCompatibleCrc32.h",
               PROJECT / "Tests/ordered_batch_test.cpp"]
    before = {str(path): digest(path) for path in sources}
    executable = build_program(name="ordered_batch_test", architecture="x64", vs=args.vs, directory=build,
                               evidence=evidence, source=sources[2], includes=[PROJECT / "Source"])
    trace = build / "results.bin"
    execution = checked_run([executable["path"], trace], cwd=build, timeout=60)
    output = execution.stdout.decode("utf-8")
    native = json.loads(output)
    (evidence / "native_execution.json").write_text(json.dumps(native, indent=2) + "\n", encoding="utf-8")
    expected = b"".join(oracle())
    if trace.read_bytes() != expected or native["status"] != "PASS" or native["records"] != len(expected) // 16:
        raise RuntimeError("Native ordered results differ from independent Python oracle")
    if len(native["runs"]) != 72 or any(run["distinct_threads"] != run["workers"]
           or run["peak_inflight"] != run["workers"] or run["first_completion"] != list(reversed(range(run["workers"])))
           for run in native["runs"]):
        raise RuntimeError("Worker overlap and deliberately reversed completion were not observed")
    if any(digest(Path(path)) != value for path, value in before.items()):
        raise RuntimeError("Ordered-job input changed during execution")
    stage = PROJECT / "Stage/Concurrency"
    stage.mkdir(parents=True, exist_ok=True)
    staged = stage / "OrderedBatch.h"
    shutil.copyfile(sources[0], staged)
    result = {"captured_at_utc": datetime.now(timezone.utc).isoformat(),
              "status": "ISOLATED_X64_ORDERED_JOB_CONFORMANCE_PASS",
              "input_sha256": before, "build": executable, "checks_passed": native["checks_passed"],
              "batches": 24, "worker_configurations": [1, 2, 4], "native_runs": len(native["runs"]),
              "records_compared_to_python": len(expected) // 16,
              "trace": {"path": str(trace), "sha256": digest(trace)},
              "expected_trace_sha256": hashlib.sha256(expected).hexdigest(),
              "stage_header": {"path": str(staged), "sha256": digest(staged)},
              "verified": ["canonical 64-bit job ID order", "reversed callback completion", "worker-count result equality",
                           "observed distinct threads and overlapping in-flight callbacks", "invalid counts and duplicate IDs",
                           "empty/single-job batches", "pre-cancel and in-flight cancellation", "worker exception and full join",
                           "no partial rows on cancellation/failure", "peer-failure cooperative cancellation without parent cancellation",
                           "independent next batch after failure", "CRC input validation"],
              "not_verified": ["physical-core instruction overlap", "thread creation resource failure injection", "race sanitizer",
                               "game-state commit identity/idempotency", "worker safety of arbitrary external callbacks",
                               "actual game turns, gameplay RNG, saving, speedup"],
              "game_launched": False, "game_multicore_execution_verified": False, "performance_improvement_measured": False}
    serialized = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    (evidence / "conformance.json").write_text(serialized, encoding="utf-8")
    (stage / "verification.json").write_text(serialized, encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("status", "checks_passed", "batches", "worker_configurations",
          "native_runs", "records_compared_to_python", "game_multicore_execution_verified")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
