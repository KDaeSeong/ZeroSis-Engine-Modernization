#include "../Source/Diagnostics/CitySiteCpuTrace.h"

#include <Windows.h>

#include <cstdint>
#include <cstdio>
#include <limits>
#include <stdexcept>

using namespace ZeroSisDiagnostics;

namespace {
constexpr std::uint32_t kUnknown = (std::numeric_limits<std::uint32_t>::max)();

bool Expect(bool condition, const char* name, int& checks) {
    ++checks;
    if (!condition) {
        std::fprintf(stderr, "FAIL %s\n", name);
        return false;
    }
    return true;
}

void AddJob(TraceMarker* markers, std::size_t offset, std::uint32_t process,
            std::uint64_t batch, std::uint32_t job, std::uint32_t tid,
            std::uint64_t begin, std::uint64_t end) {
    markers[offset] = {true, batch, job, tid, process, 12, begin};
    markers[offset + 1] = {false, batch, job, tid, process, 12, end};
}

CpuSlice Slice(std::uint32_t process, std::uint32_t tid, std::uint32_t core,
               std::uint64_t begin, std::uint64_t end) {
    return {process, tid, core, 0, static_cast<std::uint8_t>(core), core, begin, end};
}
}

int main() {
    int checks = 0;
    TraceMarker markers[4] = {};
    AddJob(markers, 0, 55, 7, 0, 100, 100, 200);
    AddJob(markers, 2, 55, 7, 1, 200, 110, 210);
    CpuSlice slices[2] = {Slice(55, 100, 3, 120, 160), Slice(55, 200, 8, 130, 170)};
    ConcurrencyProof proof = {};

    if (!Expect(FindDistinctCoreOverlap(markers, 4, slices, 2, &proof), "different physical cores overlap", checks)) return 1;
    if (!Expect(proof.batchId == 7 && proof.firstTid == 100 && proof.secondTid == 200 &&
                proof.begin == 130 && proof.end == 160, "proof is clamped to actual job and CPU slices", checks)) return 1;

    slices[1].physicalCore = 3;
    if (!Expect(!FindDistinctCoreOverlap(markers, 4, slices, 2, &proof), "same physical core is not proof", checks)) return 1;
    slices[1].physicalCore = 8;
    slices[1].processorIndex = slices[0].processorIndex;
    if (!Expect(!FindDistinctCoreOverlap(markers, 4, slices, 2, &proof), "same logical processor cannot claim two cores", checks)) return 1;
    slices[1].processorIndex = 8;
    slices[1].begin = 201;
    if (!Expect(!FindDistinctCoreOverlap(markers, 4, slices, 2, &proof), "disjoint CPU slices are not proof", checks)) return 1;
    slices[1].begin = 130;
    slices[1].processId = 56;
    if (!Expect(!FindDistinctCoreOverlap(markers, 4, slices, 2, &proof), "different process is not proof", checks)) return 1;
    slices[1].processId = 55;
    slices[1].physicalCore = kUnknown;
    if (!Expect(!FindDistinctCoreOverlap(markers, 4, slices, 2, &proof), "unknown core is not proof", checks)) return 1;

    TraceMarker malformed[3] = {markers[0], markers[1], markers[2]};
    if (!Expect(!FindDistinctCoreOverlap(malformed, 3, slices, 2, &proof), "unpaired marker is not proof", checks)) return 1;
    TraceMarker zeroWork[4] = {markers[0], markers[1], markers[2], markers[3]};
    zeroWork[0].siteCount = 0;
    if (!Expect(!FindDistinctCoreOverlap(zeroWork, 4, slices, 2, &proof), "zero site count is not proof", checks)) return 1;
    TraceMarker duplicateJob[4] = {};
    AddJob(duplicateJob, 0, 55, 7, 0, 100, 100, 200);
    AddJob(duplicateJob, 2, 55, 7, 0, 200, 110, 210);
    if (!Expect(!FindDistinctCoreOverlap(duplicateJob, 4, slices, 2, &proof), "duplicate job index across TIDs is malformed", checks)) return 1;
    TraceMarker reusedTidDifferentProcess[4] = {};
    AddJob(reusedTidDifferentProcess, 0, 55, 7, 0, 100, 100, 200);
    AddJob(reusedTidDifferentProcess, 2, 56, 7, 1, 100, 110, 210);
    CpuSlice reusedSlices[2] = {Slice(55, 100, 3, 120, 160), Slice(56, 100, 8, 130, 170)};
    if (!Expect(!FindDistinctCoreOverlap(reusedTidDifferentProcess, 4, reusedSlices, 2, &proof), "reused TID across PIDs is not shared execution", checks)) return 1;

    if (_putenv_s("ZEROSIS_CITY_SITE_CPU_TRACE", "") != 0) return 2;
    {
        CitySiteCpuTraceBatch disabled(8);
        if (!Expect(!disabled.Enabled(), "provider defaults off", checks)) return 3;
    }
    if (_putenv_s("ZEROSIS_CITY_SITE_CPU_TRACE", "1") != 0) return 4;
    {
        CitySiteCpuTraceBatch enabled(9);
        if (!Expect(enabled.Enabled(), "explicit environment opt-in registers provider", checks)) return 5;
        {
            CitySiteCpuTraceJob job(enabled, 4, 95);
        }
        bool rejected = false;
        try {
            CitySiteCpuTraceBatch overlap(10);
        } catch (const std::logic_error&) {
            rejected = true;
        }
        if (!Expect(rejected, "overlapping enabled batch is rejected", checks)) return 6;
    }
    if (_putenv_s("ZEROSIS_CITY_SITE_CPU_TRACE", "") != 0) return 7;

    std::printf("CITY_SITE_CPU_TRACE_OFFLINE_PASS checks=%d capture=false GAMECORE_LOADED=false\n", checks);
    return 0;
}
