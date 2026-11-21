#pragma once

#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <condition_variable>
#include <limits>
#include <mutex>
#include <stdexcept>

#include <Windows.h>
#include <TraceLoggingProvider.h>

TRACELOGGING_DEFINE_PROVIDER(
    g_foundValueCpuTraceProvider,
    "ZeroSis.FoundValueCpuTrace",
    (0x49a604e1, 0x6c99, 0x4e01, 0xb4, 0x1d, 0x73, 0x69, 0x4f, 0x22, 0x90, 0xa6));

namespace ZeroSisConcurrency {
namespace detail {
struct FoundValueCpuTraceState {
    std::mutex mutex;
    std::condition_variable noJobs;
    bool registered = false;
    bool closing = false;
    std::uint64_t activeBatch = 0;
    std::uint64_t activeJobs = 0;
};

inline FoundValueCpuTraceState& TraceState() {
    static FoundValueCpuTraceState state;
    return state;
}

inline bool TraceEnabledByEnvironment() noexcept {
    char value[8] = {};
    const DWORD length = GetEnvironmentVariableA("ZEROSIS_FOUND_VALUE_CPU_TRACE", value, static_cast<DWORD>(sizeof(value)));
    return length == 1 && value[0] == '1';
}
} // namespace detail

// Construct on the coordinator thread before scheduling, destroy after all
// pure-score jobs join. Trace is observational and defaults off.
class FoundValueCpuTraceBatch final {
public:
    explicit FoundValueCpuTraceBatch(std::uint64_t batchId)
        : batchId_(batchId), enabled_(false) {
        if (!detail::TraceEnabledByEnvironment())
            return;
        auto& state = detail::TraceState();
        std::lock_guard<std::mutex> guard(state.mutex);
        if (state.registered)
            throw std::logic_error("FoundValue CPU trace batches cannot overlap");
        const ULONG status = TraceLoggingRegister(g_foundValueCpuTraceProvider);
        if (status != ERROR_SUCCESS)
            throw std::runtime_error("FoundValue TraceLogging provider registration failed");
        state.registered = true;
        state.closing = false;
        state.activeBatch = batchId_;
        state.activeJobs = 0;
        enabled_ = true;
        TraceLoggingWrite(g_foundValueCpuTraceProvider, "BatchBegin",
            TraceLoggingUInt64(batchId_, "batchId"),
            TraceLoggingUInt32(::GetCurrentProcessId(), "processId"),
            TraceLoggingUInt32(::GetCurrentThreadId(), "ownerTid"));
    }
    ~FoundValueCpuTraceBatch() noexcept {
        if (!enabled_)
            return;
        auto& state = detail::TraceState();
        {
            std::unique_lock<std::mutex> guard(state.mutex);
            if (!state.registered || state.activeBatch != batchId_)
                return;
            state.closing = true;
            state.noJobs.wait(guard, [&state] { return state.activeJobs == 0; });
        }
        TraceLoggingWrite(g_foundValueCpuTraceProvider, "BatchEnd",
            TraceLoggingUInt64(batchId_, "batchId"),
            TraceLoggingUInt32(::GetCurrentThreadId(), "ownerTid"));
        TraceLoggingUnregister(g_foundValueCpuTraceProvider);
        {
            std::lock_guard<std::mutex> guard(state.mutex);
            state.registered = false;
            state.closing = false;
            state.activeBatch = 0;
        }
    }
    FoundValueCpuTraceBatch(const FoundValueCpuTraceBatch&) = delete;
    FoundValueCpuTraceBatch& operator=(const FoundValueCpuTraceBatch&) = delete;
    FoundValueCpuTraceBatch(FoundValueCpuTraceBatch&&) = delete;
    FoundValueCpuTraceBatch& operator=(FoundValueCpuTraceBatch&&) = delete;
    bool Enabled() const noexcept { return enabled_; }
    std::uint64_t BatchId() const noexcept { return batchId_; }
private:
    std::uint64_t batchId_;
    bool enabled_;
};

class FoundValueCpuTraceJob final {
public:
    FoundValueCpuTraceJob(const FoundValueCpuTraceBatch& batch,
                          std::uint32_t jobIndex,
                          std::uint32_t factCount) noexcept
        : batchId_(batch.BatchId()), jobIndex_(jobIndex), factCount_(factCount),
          scoreBeginQpc_(0), active_(false) {
        if (!batch.Enabled())
            return;
        auto& state = detail::TraceState();
        {
            std::lock_guard<std::mutex> guard(state.mutex);
            if (!state.registered || state.closing || state.activeBatch != batchId_)
                return;
            ++state.activeJobs;
            active_ = true;
        }
        TraceLoggingWrite(g_foundValueCpuTraceProvider, "JobBegin",
            TraceLoggingUInt64(batchId_, "batchId"),
            TraceLoggingUInt32(jobIndex_, "jobIndex"),
            TraceLoggingUInt32(::GetCurrentThreadId(), "workerTid"),
            TraceLoggingUInt32(::GetCurrentProcessId(), "processId"),
            TraceLoggingUInt32(factCount_, "factCount"));
        LARGE_INTEGER begin = {};
        QueryPerformanceCounter(&begin);
        scoreBeginQpc_ = begin.QuadPart;
    }
    ~FoundValueCpuTraceJob() noexcept {
        if (!active_)
            return;
        LARGE_INTEGER end = {}, frequency = {};
        QueryPerformanceCounter(&end);
        QueryPerformanceFrequency(&frequency);
        TraceLoggingWrite(g_foundValueCpuTraceProvider, "JobEnd",
            TraceLoggingUInt64(batchId_, "batchId"),
            TraceLoggingUInt32(jobIndex_, "jobIndex"),
            TraceLoggingUInt32(::GetCurrentThreadId(), "workerTid"),
            TraceLoggingUInt32(::GetCurrentProcessId(), "processId"),
            TraceLoggingUInt32(factCount_, "factCount"),
            TraceLoggingInt64(scoreBeginQpc_, "scoreBeginQpc"),
            TraceLoggingInt64(end.QuadPart, "scoreEndQpc"),
            TraceLoggingInt64(frequency.QuadPart, "qpcFrequency"));
        auto& state = detail::TraceState();
        {
            std::lock_guard<std::mutex> guard(state.mutex);
            if (state.activeJobs != 0)
                --state.activeJobs;
            if (state.activeJobs == 0)
                state.noJobs.notify_all();
        }
    }
    FoundValueCpuTraceJob(const FoundValueCpuTraceJob&) = delete;
    FoundValueCpuTraceJob& operator=(const FoundValueCpuTraceJob&) = delete;
    FoundValueCpuTraceJob(FoundValueCpuTraceJob&&) = delete;
    FoundValueCpuTraceJob& operator=(FoundValueCpuTraceJob&&) = delete;
private:
    std::uint64_t batchId_;
    std::uint32_t jobIndex_;
    std::uint32_t factCount_;
    std::int64_t scoreBeginQpc_;
    bool active_;
};

struct FoundValueTraceMarker {
    bool begin;
    std::uint64_t batchId;
    std::uint32_t jobIndex;
    std::uint32_t workerTid;
    std::uint32_t processId;
    std::uint32_t factCount;
    std::uint64_t timestamp;
};

struct FoundValueCpuSlice {
    std::uint32_t processId, workerTid, processorIndex, group, groupProcessor, physicalCore;
    std::uint64_t begin, end;
};

struct FoundValueConcurrencyProof {
    std::uint64_t batchId;
    std::uint32_t firstJob, firstTid, firstCore, secondJob, secondTid, secondCore;
    std::uint64_t begin, end;
};

inline bool FindFoundValueDistinctCoreOverlap(const FoundValueTraceMarker* markers,
                                               std::size_t markerCount,
                                               const FoundValueCpuSlice* slices,
                                               std::size_t sliceCount,
                                               FoundValueConcurrencyProof* proof) noexcept {
    if ((markerCount && !markers) || (sliceCount && !slices) || !proof)
        return false;
    for (std::size_t i=0;i<markerCount;++i) {
        if (markers[i].factCount==0) return false;
        if (!markers[i].begin) continue;
        for (std::size_t j=i+1;j<markerCount;++j)
            if (markers[j].begin && markers[j].processId==markers[i].processId && markers[j].batchId==markers[i].batchId && markers[j].jobIndex==markers[i].jobIndex) return false;
    }
    for (std::size_t i=0;i<markerCount;++i) {
        if (!markers[i].begin) continue;
        std::size_t ends=0; const FoundValueTraceMarker* end=nullptr;
        for (std::size_t j=0;j<markerCount;++j)
            if (!markers[j].begin && markers[j].processId==markers[i].processId && markers[j].batchId==markers[i].batchId && markers[j].jobIndex==markers[i].jobIndex && markers[j].workerTid==markers[i].workerTid) {++ends;end=&markers[j];}
        if (ends!=1 || !end || markers[i].processId!=end->processId || markers[i].factCount!=end->factCount || markers[i].timestamp>=end->timestamp) return false;
        for (std::size_t j=i+1;j<markerCount;++j)
            if (markers[j].begin && markers[j].processId==markers[i].processId && markers[j].batchId==markers[i].batchId && markers[j].jobIndex==markers[i].jobIndex && markers[j].workerTid==markers[i].workerTid) return false;
    }
    for (std::size_t i=0;i<markerCount;++i) if (!markers[i].begin) {
        std::size_t begins=0;
        for (std::size_t j=0;j<markerCount;++j)
            if (markers[j].begin && markers[j].processId==markers[i].processId && markers[j].batchId==markers[i].batchId && markers[j].jobIndex==markers[i].jobIndex && markers[j].workerTid==markers[i].workerTid) ++begins;
        if (begins!=1) return false;
    }
    for (std::size_t i=0;i<markerCount;++i) {
        if (!markers[i].begin) continue;
        const FoundValueTraceMarker* endI=nullptr;
        for (std::size_t k=0;k<markerCount;++k)
            if (!markers[k].begin && markers[k].processId==markers[i].processId && markers[k].batchId==markers[i].batchId && markers[k].jobIndex==markers[i].jobIndex && markers[k].workerTid==markers[i].workerTid) endI=&markers[k];
        for (std::size_t j=i+1;j<markerCount;++j) {
            if (!markers[j].begin || markers[j].batchId!=markers[i].batchId || markers[j].workerTid==markers[i].workerTid || markers[j].processId!=markers[i].processId) continue;
            const FoundValueTraceMarker* endJ=nullptr;
            for (std::size_t k=0;k<markerCount;++k)
                if (!markers[k].begin && markers[k].processId==markers[j].processId && markers[k].batchId==markers[j].batchId && markers[k].jobIndex==markers[j].jobIndex && markers[k].workerTid==markers[j].workerTid) endJ=&markers[k];
            if (!endI || !endJ || markers[i].jobIndex==markers[j].jobIndex) continue;
            for (std::size_t a=0;a<sliceCount;++a) {
                const auto& first=slices[a];
                if (first.processId!=markers[i].processId || first.workerTid!=markers[i].workerTid || first.physicalCore==(std::numeric_limits<std::uint32_t>::max)() || first.begin>=first.end) continue;
                const std::uint64_t firstBegin=first.begin>markers[i].timestamp?first.begin:markers[i].timestamp;
                const std::uint64_t firstEnd=first.end<endI->timestamp?first.end:endI->timestamp;
                if (firstBegin>=firstEnd) continue;
                for (std::size_t b=0;b<sliceCount;++b) {
                    const auto& second=slices[b];
                    if (second.processId!=markers[j].processId || second.workerTid!=markers[j].workerTid || second.physicalCore==(std::numeric_limits<std::uint32_t>::max)() || second.physicalCore==first.physicalCore || second.processorIndex==first.processorIndex || second.begin>=second.end) continue;
                    const std::uint64_t secondBegin=second.begin>markers[j].timestamp?second.begin:markers[j].timestamp;
                    const std::uint64_t secondEnd=second.end<endJ->timestamp?second.end:endJ->timestamp;
                    const std::uint64_t overlapBegin=firstBegin>secondBegin?firstBegin:secondBegin;
                    const std::uint64_t overlapEnd=firstEnd<secondEnd?firstEnd:secondEnd;
                    if (overlapBegin<overlapEnd) {
                        *proof={markers[i].batchId,markers[i].jobIndex,first.workerTid,first.physicalCore,markers[j].jobIndex,second.workerTid,second.physicalCore,overlapBegin,overlapEnd};
                        return true;
                    }
                }
            }
        }
    }
    return false;
}
} // namespace ZeroSisConcurrency
