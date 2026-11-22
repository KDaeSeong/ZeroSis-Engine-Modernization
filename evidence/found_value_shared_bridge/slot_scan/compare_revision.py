"""Compare the original dense scalar and both shared worker builds without a Civ V SDK."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
from struct import pack
from tempfile import TemporaryDirectory

root = Path(__file__).resolve().parents[3]
work = root / "Build/FoundValueSlotScan"
work.mkdir(parents=True, exist_ok=True)
src = root / "Source/Concurrency"
commit = "86ef92affe67b82e02c0789e25961b9de6eda465"
sys.path.insert(0, str(root / "tools"))
from verify_found_value_shared_bridge import initialize_msvc


def old(path):
    return subprocess.check_output(["git", "show", commit + ":" + path], cwd=root)


def between(text, start, end):
    return text[text.index(start):text.index(end)]


def sha(data):
    return hashlib.sha256(data).hexdigest()


baseline = work / "baseline"
baseline.mkdir(exist_ok=True)
for name in ("FoundValueScores.h", "FoundValueSharedScores.h", "FoundValueSharedBridge.cpp",
             "FoundValueSharedBridge.h", "FoundValueScoreBridge.h", "FoundValueCpuTrace.h",
             "OrderedBatch.h"):
    (baseline / name).write_bytes(old("Source/Concurrency/" + name))
dense_fixture = old("Tests/found_value_scores.cpp").decode("ascii")
shared_fixture = old("Tests/found_value_shared_scores.cpp").decode("ascii")
probe = work / "differential.cpp"
probe.write_text(r'''
#include "FoundValueSharedScores.h"
#include "OrderedBatch.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <vector>
using namespace zerosis::found_value;
using namespace zerosis::found_value_shared;
''' + between(dense_fixture, "static Snapshot make_base_snapshot()", "static bool source_oracle")
    + between(dense_fixture, "static std::uint32_t random_state", "struct WorkerResult")
    + between(shared_fixture, "static CommonSnapshot make_common(", "static bool compare_shared_case")
    + r'''
struct Fixture {
    Snapshot dense;
    CommonSnapshot common;
    Candidate candidate;
    std::vector<PlotFacts> facts;
};
int main() {
    using namespace zerosis::concurrency;
    const auto fixtures = [] {
        std::vector<Fixture> rows(512);
        for (auto& row : rows) {
            row.dense = random_snapshot();
            make_shared(row.dense, row.common, row.candidate, row.facts);
            if (validate_batch(row.common, row.facts.data(), row.facts.size(), &row.candidate, 1) != Status::ok)
                std::abort();
        }
        return rows;
    }();
    std::printf("LAYOUT %zu %zu %zu\n", sizeof(Tile), sizeof(Snapshot), kOffsetCount);
    std::printf("SERIAL");
    for (const auto& row : fixtures) {
        const auto scored = evaluate(row.dense);
        if (scored.status != Status::ok) return 1;
        std::printf(" %d", scored.score);
    }
    std::puts("");
    for (const auto workers : {1u, 2u, 4u}) {
        std::vector<Job<std::size_t>> jobs;
        for (std::size_t i = 0; i < fixtures.size(); ++i) jobs.push_back({i, i});
        const auto batch = evaluate_ordered(BatchStamp{}, std::move(jobs), workers,
            [&](std::size_t i, const CancellationToken&) {
                const auto& row = fixtures[i];
                return evaluate_shared_prevalidated(row.common, row.candidate, row.facts.data(), row.facts.size());
            });
        if (batch.status != BatchStatus::ready || batch.rows.size() != fixtures.size() ||
            batch.workers_started != workers || batch.jobs_completed != fixtures.size()) return 2;
        std::printf("WORKERS%u", workers);
        for (std::size_t i = 0; i < fixtures.size(); ++i) {
            if (batch.rows[i].id != i || batch.rows[i].value.status != Status::ok) return 3;
            std::printf(" %d", batch.rows[i].value.score);
        }
        std::puts("");
    }
}
''', encoding="utf-8")

with TemporaryDirectory(dir=work) as temp:
    compiler, _, env = initialize_msvc(Path(temp) / "environment")
flags = [str(compiler), "/nologo", "/std:c++17", "/EHsc", "/MD", "/permissive-",
         "/fp:strict", "/O2", "/W4", "/WX", "/utf-8"]
outputs = {}
for flavor, include in (("before", baseline), ("after", src)):
    destination = work / flavor
    destination.mkdir(exist_ok=True)
    def run(arguments):
        return subprocess.run(arguments, cwd=destination, env=env, check=True, capture_output=True)
    try:
        run([*flags, "/I" + str(include), "/c", "/FA", "/Fabridge.asm", "/Fobridge.obj",
             str(include / "FoundValueSharedBridge.cpp")])
        run([*flags, "/I" + str(include), str(probe), "/Fedifferential.exe"])
        output = run([str(destination / "differential.exe")]).stdout.decode("ascii")
    except subprocess.CalledProcessError as error:
        print((error.stdout + error.stderr).decode("mbcs", errors="replace"))
        raise
    (destination / "scores.txt").write_text(output, encoding="ascii")
    rows = {words[0]: [int(x) for x in words[1:]] for words in map(str.split, output.splitlines()) if words}
    if any(len(rows[key]) != 512 for key in ("SERIAL", "WORKERS1", "WORKERS2", "WORKERS4")):
        raise RuntimeError(f"{flavor} returned an incomplete score vector")
    outputs[flavor] = rows

serial = outputs["before"]["SERIAL"]
for flavor, rows in outputs.items():
    for key in ("SERIAL", "WORKERS1", "WORKERS2", "WORKERS4"):
        for index, (expected, actual) in enumerate(zip(serial, rows[key], strict=True)):
            if actual != expected:
                raise RuntimeError(f"{flavor}/{key} site {index}: {actual} != {expected}")
summary = {
    "baseline": commit, "msvc": str(compiler), "flags": flags[1:],
    "seed": "0x72a2f11d", "fixture_count": len(serial), "distinct_scores": len(set(serial)),
    "score_min": min(serial), "score_max": max(serial),
    "score_vector_i32le_sha256": sha(pack("<512i", *serial)),
    "old_dense_serial_equals_new_dense_serial_and_old_and_new_shared_workers_1_2_4": True,
    "layout_tile_snapshot_count": outputs["before"]["LAYOUT"],
    "frozen_generated_probe_sha256": sha(probe.read_bytes()),
    "sdk": False,
}
(work / "comparison.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
print(json.dumps(summary))
