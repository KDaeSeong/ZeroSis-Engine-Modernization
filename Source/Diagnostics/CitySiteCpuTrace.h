#pragma once

#include <cstdint>
#include <cstddef>

namespace ZeroSisDiagnostics {

// Trace markers are opt-in and observational. This session must be constructed
// on the GameCore owner thread before scheduling and destroyed there only after
// every submitted job has returned. An enabled overlapping session is rejected.
class CitySiteCpuTraceBatch final {
public:
    explicit CitySiteCpuTraceBatch(std::uint64_t batchId);
    ~CitySiteCpuTraceBatch() noexcept;

    CitySiteCpuTraceBatch(const CitySiteCpuTraceBatch&) = delete;
    CitySiteCpuTraceBatch& operator=(const CitySiteCpuTraceBatch&) = delete;
    CitySiteCpuTraceBatch(CitySiteCpuTraceBatch&&) = delete;
    CitySiteCpuTraceBatch& operator=(CitySiteCpuTraceBatch&&) = delete;

    bool Enabled() const noexcept { return enabled_; }
    std::uint64_t BatchId() const noexcept { return batchId_; }

private:
    std::uint64_t batchId_;
    bool enabled_;
};

class CitySiteCpuTraceJob final {
public:
    CitySiteCpuTraceJob(const CitySiteCpuTraceBatch& batch,
                        std::uint32_t jobIndex,
                        std::uint32_t siteCount) noexcept;
    ~CitySiteCpuTraceJob() noexcept;

    CitySiteCpuTraceJob(const CitySiteCpuTraceJob&) = delete;
    CitySiteCpuTraceJob& operator=(const CitySiteCpuTraceJob&) = delete;
    CitySiteCpuTraceJob(CitySiteCpuTraceJob&&) = delete;
    CitySiteCpuTraceJob& operator=(CitySiteCpuTraceJob&&) = delete;

private:
    std::uint64_t batchId_;
    std::uint32_t jobIndex_;
    std::uint32_t siteCount_;
    std::int64_t scoreBeginQpc_;
    bool active_;
};

struct TraceMarker {
    bool begin;
    std::uint64_t batchId;
    std::uint32_t jobIndex;
    std::uint32_t workerTid;
    std::uint32_t processId;
    std::uint32_t siteCount;
    std::uint64_t timestamp;
};

struct CpuSlice {
    std::uint32_t processId;
    std::uint32_t workerTid;
    std::uint32_t processorIndex;
    std::uint32_t group;
    std::uint32_t groupProcessor;
    std::uint32_t physicalCore;
    std::uint64_t begin;
    std::uint64_t end;
};

struct ConcurrencyProof {
    std::uint64_t batchId;
    std::uint32_t firstJob;
    std::uint32_t firstTid;
    std::uint32_t firstCore;
    std::uint32_t secondJob;
    std::uint32_t secondTid;
    std::uint32_t secondCore;
    std::uint64_t begin;
    std::uint64_t end;
};

// Returns true only for well-paired markers with real execution slices that
// overlap on different physical cores. Unknown-core slices never prove it.
bool FindDistinctCoreOverlap(const TraceMarker* markers,
                            std::size_t markerCount,
                            const CpuSlice* slices,
                            std::size_t sliceCount,
                            ConcurrencyProof* proof) noexcept;

} // namespace ZeroSisDiagnostics
