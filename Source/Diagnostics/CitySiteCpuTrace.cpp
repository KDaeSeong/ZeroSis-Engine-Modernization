#include "CitySiteCpuTrace.h"

#include <Windows.h>
#include <TraceLoggingProvider.h>

#include <condition_variable>
#include <cstdlib>
#include <limits>
#include <mutex>
#include <stdexcept>

TRACELOGGING_DEFINE_PROVIDER(
    g_citySiteCpuTraceProvider,
    "ZeroSis.CitySiteCpuTrace",
    (0x2d76305f, 0x91f4, 0x4d48, 0x9b, 0x32, 0x28, 0x15, 0x07, 0x66, 0x9f, 0x73));

namespace ZeroSisDiagnostics {
namespace {
struct ProviderState {
    std::mutex mutex;
    std::condition_variable noJobs;
    bool registered = false;
    bool closing = false;
    std::uint64_t activeBatch = 0;
    std::uint64_t activeJobs = 0;
};

ProviderState& State() {
    static ProviderState state;
    return state;
}

bool IsEnabledByEnvironment() noexcept {
    char value[8] = {};
    const DWORD length = GetEnvironmentVariableA("ZEROSIS_CITY_SITE_CPU_TRACE", value, static_cast<DWORD>(sizeof(value)));
    return length == 1 && value[0] == '1';
}

void EmitBatchEnd(std::uint64_t batchId) noexcept {
    TraceLoggingWrite(g_citySiteCpuTraceProvider, "BatchEnd",
        TraceLoggingUInt64(batchId, "batchId"),
        TraceLoggingUInt32(::GetCurrentThreadId(), "ownerTid"));
}
} // namespace

CitySiteCpuTraceBatch::CitySiteCpuTraceBatch(std::uint64_t batchId)
    : batchId_(batchId), enabled_(false) {
    if (!IsEnabledByEnvironment())
        return;

    ProviderState& state = State();
    std::lock_guard<std::mutex> guard(state.mutex);
    if (state.registered)
        throw std::logic_error("CitySite CPU trace batches cannot overlap");

    const ULONG status = TraceLoggingRegister(g_citySiteCpuTraceProvider);
    if (status != ERROR_SUCCESS)
        throw std::runtime_error("TraceLogging provider registration failed");

    state.registered = true;
    state.closing = false;
    state.activeBatch = batchId_;
    state.activeJobs = 0;
    enabled_ = true;
    TraceLoggingWrite(g_citySiteCpuTraceProvider, "BatchBegin",
        TraceLoggingUInt64(batchId_, "batchId"),
        TraceLoggingUInt32(::GetCurrentProcessId(), "processId"),
        TraceLoggingUInt32(::GetCurrentThreadId(), "ownerTid"));
}

CitySiteCpuTraceBatch::~CitySiteCpuTraceBatch() noexcept {
    if (!enabled_)
        return;

    ProviderState& state = State();
    {
        std::unique_lock<std::mutex> guard(state.mutex);
        if (!state.registered || state.activeBatch != batchId_)
            return;
        state.closing = true;
        state.noJobs.wait(guard, [&state] { return state.activeJobs == 0; });
    }

    EmitBatchEnd(batchId_);
    TraceLoggingUnregister(g_citySiteCpuTraceProvider);
    {
        std::lock_guard<std::mutex> guard(state.mutex);
        state.registered = false;
        state.closing = false;
        state.activeBatch = 0;
    }
}

CitySiteCpuTraceJob::CitySiteCpuTraceJob(const CitySiteCpuTraceBatch& batch,
                                         std::uint32_t jobIndex,
                                         std::uint32_t siteCount) noexcept
    : batchId_(batch.BatchId()), jobIndex_(jobIndex), siteCount_(siteCount), scoreBeginQpc_(0), active_(false) {
    if (!batch.Enabled())
        return;

    ProviderState& state = State();
    {
        std::lock_guard<std::mutex> guard(state.mutex);
        if (!state.registered || state.closing || state.activeBatch != batchId_)
            return;
        ++state.activeJobs;
        active_ = true;
    }

    TraceLoggingWrite(g_citySiteCpuTraceProvider, "JobBegin",
        TraceLoggingUInt64(batchId_, "batchId"),
        TraceLoggingUInt32(jobIndex_, "jobIndex"),
        TraceLoggingUInt32(::GetCurrentThreadId(), "workerTid"),
        TraceLoggingUInt32(::GetCurrentProcessId(), "processId"),
        TraceLoggingUInt32(siteCount_, "siteCount"));
    LARGE_INTEGER scoreBegin = {};
    QueryPerformanceCounter(&scoreBegin);
    scoreBeginQpc_ = scoreBegin.QuadPart;
}

CitySiteCpuTraceJob::~CitySiteCpuTraceJob() noexcept {
    if (!active_)
        return;

    LARGE_INTEGER scoreEnd = {};
    QueryPerformanceCounter(&scoreEnd);
    LARGE_INTEGER frequency = {};
    QueryPerformanceFrequency(&frequency);

    TraceLoggingWrite(g_citySiteCpuTraceProvider, "JobEnd",
        TraceLoggingUInt64(batchId_, "batchId"),
        TraceLoggingUInt32(jobIndex_, "jobIndex"),
        TraceLoggingUInt32(::GetCurrentThreadId(), "workerTid"),
        TraceLoggingUInt32(::GetCurrentProcessId(), "processId"),
        TraceLoggingUInt32(siteCount_, "siteCount"),
        TraceLoggingInt64(scoreBeginQpc_, "scoreBeginQpc"),
        TraceLoggingInt64(scoreEnd.QuadPart, "scoreEndQpc"),
        TraceLoggingInt64(frequency.QuadPart, "qpcFrequency"));

    ProviderState& state = State();
    {
        std::lock_guard<std::mutex> guard(state.mutex);
        if (state.activeJobs != 0)
            --state.activeJobs;
        if (state.activeJobs == 0)
            state.noJobs.notify_all();
    }
}

bool FindDistinctCoreOverlap(const TraceMarker* markers,
                             std::size_t markerCount,
                             const CpuSlice* slices,
                             std::size_t sliceCount,
                             ConcurrencyProof* proof) noexcept {
    if ((markerCount != 0 && markers == nullptr) || (sliceCount != 0 && slices == nullptr) || proof == nullptr)
        return false;

    for (std::size_t i = 0; i < markerCount; ++i) {
        if (markers[i].siteCount == 0)
            return false;
        if (!markers[i].begin)
            continue;
        for (std::size_t j = i + 1; j < markerCount; ++j) {
            if (markers[j].begin && markers[j].processId == markers[i].processId &&
                markers[j].batchId == markers[i].batchId && markers[j].jobIndex == markers[i].jobIndex)
                return false; // A scheduler job index is unique within a process batch.
        }
    }

    for (std::size_t i = 0; i < markerCount; ++i) {
        if (!markers[i].begin)
            continue;
        std::size_t ends = 0;
        const TraceMarker* end = nullptr;
        for (std::size_t j = 0; j < markerCount; ++j) {
            if (!markers[j].begin && markers[j].processId == markers[i].processId && markers[j].batchId == markers[i].batchId &&
                markers[j].jobIndex == markers[i].jobIndex && markers[j].workerTid == markers[i].workerTid) {
                ++ends;
                end = &markers[j];
            }
        }
        if (ends != 1 || end == nullptr || markers[i].processId != end->processId ||
            markers[i].siteCount != end->siteCount || markers[i].timestamp >= end->timestamp)
            return false;
        for (std::size_t j = i + 1; j < markerCount; ++j) {
            if (markers[j].begin && markers[j].processId == markers[i].processId && markers[j].batchId == markers[i].batchId &&
                markers[j].jobIndex == markers[i].jobIndex && markers[j].workerTid == markers[i].workerTid)
                return false;
        }
    }
    for (std::size_t i = 0; i < markerCount; ++i) {
        if (markers[i].begin)
            continue;
        std::size_t begins = 0;
        for (std::size_t j = 0; j < markerCount; ++j) {
            if (markers[j].begin && markers[j].processId == markers[i].processId && markers[j].batchId == markers[i].batchId &&
                markers[j].jobIndex == markers[i].jobIndex && markers[j].workerTid == markers[i].workerTid)
                ++begins;
        }
        if (begins != 1)
            return false;
    }

    for (std::size_t i = 0; i < markerCount; ++i) {
        if (!markers[i].begin)
            continue;
        const TraceMarker* endI = nullptr;
        for (std::size_t k = 0; k < markerCount; ++k) {
            if (!markers[k].begin && markers[k].processId == markers[i].processId && markers[k].batchId == markers[i].batchId &&
                markers[k].jobIndex == markers[i].jobIndex && markers[k].workerTid == markers[i].workerTid)
                endI = &markers[k];
        }
        for (std::size_t j = i + 1; j < markerCount; ++j) {
            if (!markers[j].begin || markers[j].batchId != markers[i].batchId ||
                markers[j].workerTid == markers[i].workerTid || markers[j].processId != markers[i].processId)
                continue;
            const TraceMarker* endJ = nullptr;
            for (std::size_t k = 0; k < markerCount; ++k) {
                if (!markers[k].begin && markers[k].processId == markers[j].processId && markers[k].batchId == markers[j].batchId &&
                    markers[k].jobIndex == markers[j].jobIndex && markers[k].workerTid == markers[j].workerTid)
                    endJ = &markers[k];
            }
            if (!endI || !endJ || markers[i].jobIndex == markers[j].jobIndex)
                continue;
            for (std::size_t a = 0; a < sliceCount; ++a) {
                const CpuSlice& first = slices[a];
                if (first.processId != markers[i].processId || first.workerTid != markers[i].workerTid ||
                    first.physicalCore == (std::numeric_limits<std::uint32_t>::max)() || first.begin >= first.end)
                    continue;
                const std::uint64_t firstBegin = (first.begin > markers[i].timestamp) ? first.begin : markers[i].timestamp;
                const std::uint64_t firstEnd = (first.end < endI->timestamp) ? first.end : endI->timestamp;
                if (firstBegin >= firstEnd)
                    continue;
                for (std::size_t b = 0; b < sliceCount; ++b) {
                    const CpuSlice& second = slices[b];
                    if (second.processId != markers[j].processId || second.workerTid != markers[j].workerTid ||
                        second.physicalCore == (std::numeric_limits<std::uint32_t>::max)() ||
                        second.physicalCore == first.physicalCore || second.processorIndex == first.processorIndex ||
                        second.begin >= second.end)
                        continue;
                    const std::uint64_t secondBegin = (second.begin > markers[j].timestamp) ? second.begin : markers[j].timestamp;
                    const std::uint64_t secondEnd = (second.end < endJ->timestamp) ? second.end : endJ->timestamp;
                    const std::uint64_t overlapBegin = (firstBegin > secondBegin) ? firstBegin : secondBegin;
                    const std::uint64_t overlapEnd = (firstEnd < secondEnd) ? firstEnd : secondEnd;
                    if (overlapBegin < overlapEnd) {
                        proof->batchId = markers[i].batchId;
                        proof->firstJob = markers[i].jobIndex;
                        proof->firstTid = first.workerTid;
                        proof->firstCore = first.physicalCore;
                        proof->secondJob = markers[j].jobIndex;
                        proof->secondTid = second.workerTid;
                        proof->secondCore = second.physicalCore;
                        proof->begin = overlapBegin;
                        proof->end = overlapEnd;
                        return true;
                    }
                }
            }
        }
    }
    return false;
}

} // namespace ZeroSisDiagnostics
