#include "CitySiteScoreBridge.h"

#include "CitySiteScores.h"
#include "OrderedBatch.h"
#include "../Diagnostics/CitySiteCpuTrace.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <exception>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

namespace {
using namespace zerosis::concurrency;
using zerosis::city_site::AllResult;
using zerosis::city_site::Cell;
using zerosis::city_site::SiteInput;
using zerosis::city_site::Status;

struct InvocationState {
    std::mutex mutex;
    std::array<std::uint32_t, 4> thread_ids{};
    std::array<std::uint32_t, 4> job_counts{};
    std::uint32_t used = 0;
    std::uint32_t active = 0;
    std::uint32_t maximum_overlap = 0;

    std::uint32_t Enter() {
        const std::uint32_t os_id = static_cast<std::uint32_t>(::GetCurrentThreadId());
        std::lock_guard<std::mutex> lock(mutex);
        std::uint32_t slot = 0;
        while (slot < used && thread_ids[slot] != os_id) ++slot;
        if (slot == used) {
            if (used == thread_ids.size()) return 0;
            thread_ids[used++] = os_id;
        }
        ++job_counts[slot];
        ++active;
        maximum_overlap = (std::max)(maximum_overlap, active);
        return slot + 1;
    }

    void Leave() noexcept {
        std::lock_guard<std::mutex> lock(mutex);
        if (active != 0) --active;
    }
};

struct WorkerOutput {
    AllResult result;
    std::uint32_t worker_slot;
};

struct OwnedSiteInput {
    std::uint32_t job_index;
    SiteInput site;
};

class CitySiteOperation {
public:
    CitySiteOperation(std::shared_ptr<InvocationState> state,
                      const ZeroSisDiagnostics::CitySiteCpuTraceBatch& trace)
        : state_(std::move(state)), trace_(&trace) {}

    WorkerOutput operator()(const OwnedSiteInput& input, const CancellationToken&) const {
        const auto slot = state_->Enter();
        struct LeaveOnExit {
            InvocationState& state;
            ~LeaveOnExit() { state.Leave(); }
        } leave{*state_};
        if (slot == 0) return {{Status::invalid_input, {}}, 0};
        AllResult scored;
        {
            ZeroSisDiagnostics::CitySiteCpuTraceJob trace(*trace_, input.job_index,
                                                         input.site.tile_count);
            scored = zerosis::city_site::evaluate_all(input.site);
        }
        return {scored, slot};
    }

private:
    std::shared_ptr<InvocationState> state_;
    const ZeroSisDiagnostics::CitySiteCpuTraceBatch* trace_;
};

bool CopyInput(const ZeroSisCitySiteInput& source, SiteInput& target) noexcept {
    if (source.abi_version != ZEROSIS_CITY_SITE_ABI_VERSION ||
        source.config_version != ZEROSIS_CITY_SITE_CONFIG_VERSION ||
        source.reserved != 0 || source.tile_count > ZEROSIS_CITY_SITE_MAX_TILES) return false;
    target.tile_count = source.tile_count;
    for (std::size_t ring = 0; ring < target.ring_weights.size(); ++ring)
        target.ring_weights[ring] = source.ring_weights[ring];
    for (std::size_t index = 0; index < target.cells.size(); ++index) {
        const auto& from = source.cells[index];
        if (from.present > 1 || from.foreign_owned > 1 || from.science_clear > 1 || from.reserved != 0)
            return false;
        auto& to = target.cells[index];
        to.present = from.present != 0;
        to.ring_distance = from.ring_distance;
        for (std::size_t yield = 0; yield < to.yields.size(); ++yield)
            to.yields[yield] = from.yields[yield];
        to.foreign_owned = from.foreign_owned != 0;
        to.science_clear = from.science_clear != 0;
    }
    return true;
}

void CopyMetrics(InvocationState& state, ZeroSisCitySiteMetrics& metrics) {
    std::lock_guard<std::mutex> lock(state.mutex);
    metrics.worker_threads_used = state.used;
    metrics.maximum_overlapping_jobs = state.maximum_overlap;
    for (std::uint32_t i = 0; i < state.used; ++i) {
        metrics.worker_thread_ids[i] = state.thread_ids[i];
        metrics.worker_job_counts[i] = state.job_counts[i];
    }
}
} // namespace

extern "C" std::int32_t ZeroSisEvaluateCitySites(const ZeroSisCitySiteInput* inputs,
                                                   const std::uint32_t count,
                                                   const std::uint32_t worker_count,
                                                   ZeroSisCitySiteResult* results,
                                                   ZeroSisCitySiteMetrics* metrics) {
    if (metrics == nullptr) return ZEROSIS_CITY_SITE_INVALID_INPUT;
    *metrics = {};
    metrics->abi_version = ZEROSIS_CITY_SITE_ABI_VERSION;
    metrics->config_version = ZEROSIS_CITY_SITE_CONFIG_VERSION;
    metrics->requested_workers = worker_count;
    if ((count != 0 && (inputs == nullptr || results == nullptr)) ||
        (worker_count != 1 && worker_count != 2 && worker_count != 4)) {
        metrics->status = ZEROSIS_CITY_SITE_INVALID_INPUT;
        return ZEROSIS_CITY_SITE_INVALID_INPUT;
    }

    const auto started = std::chrono::steady_clock::now();
    try {
        std::vector<Job<OwnedSiteInput>> jobs;
        jobs.reserve(count);
        for (std::uint32_t index = 0; index < count; ++index) {
            SiteInput owned{};
            if (!CopyInput(inputs[index], owned)) {
                metrics->status = ZEROSIS_CITY_SITE_INVALID_INPUT;
                return ZEROSIS_CITY_SITE_INVALID_INPUT;
            }
            jobs.push_back({index, {index, std::move(owned)}});
        }
        if (count == 0) {
            metrics->status = ZEROSIS_CITY_SITE_OK;
            return ZEROSIS_CITY_SITE_OK;
        }

        // No SDK pointers enter tracing or workers. The synchronous batch joins
        // all workers before this owner-thread trace registration is released.
        static std::atomic<std::uint64_t> next_trace_batch{1};
        const auto trace_id = next_trace_batch.fetch_add(1, std::memory_order_relaxed);
        ZeroSisDiagnostics::CitySiteCpuTraceBatch trace(trace_id);
        auto invocation = std::make_shared<InvocationState>();
        const BatchStamp stamp{0, 0, 0, 0, 0};
        const auto batch = evaluate_ordered(stamp, std::move(jobs), worker_count,
                                           CitySiteOperation(invocation, trace));
        metrics->jobs_total = count;
        metrics->jobs_started = static_cast<std::uint32_t>(batch.jobs_started);
        metrics->jobs_completed = static_cast<std::uint32_t>(batch.jobs_completed);
        metrics->workers_started = static_cast<std::uint32_t>(batch.workers_started);
        CopyMetrics(*invocation, *metrics);
        if (trace.Enabled()) {
            std::printf("ZEROSIS_CITY_SITE_CPU_TRACE batch_id=%llu process_id=%u requested_workers=%u sites=%u workers_started=%u\n",
                        static_cast<unsigned long long>(trace_id),
                        static_cast<unsigned int>(::GetCurrentProcessId()), worker_count,
                        count, metrics->workers_started);
            std::fflush(stdout);
        }
        metrics->worker_batch_us = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count());
        if (batch.status != BatchStatus::ready || batch.rows.size() != count) {
            metrics->status = ZEROSIS_CITY_SITE_BATCH_FAILURE;
            return ZEROSIS_CITY_SITE_BATCH_FAILURE;
        }
        for (std::uint32_t index = 0; index < count; ++index) {
            if (batch.rows[index].id != index || batch.rows[index].value.worker_slot == 0 ||
                batch.rows[index].value.result.status != Status::ok) {
                const auto status = batch.rows[index].value.result.status == Status::overflow
                    ? ZEROSIS_CITY_SITE_OVERFLOW : ZEROSIS_CITY_SITE_BATCH_FAILURE;
                metrics->status = status;
                return status;
            }
        }
        for (std::uint32_t index = 0; index < count; ++index)
            for (std::size_t yield = 0; yield < 4; ++yield)
                results[index].values[yield] = batch.rows[index].value.result.values[yield];
        metrics->status = ZEROSIS_CITY_SITE_OK;
        return ZEROSIS_CITY_SITE_OK;
    } catch (...) {
        metrics->worker_batch_us = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count());
        metrics->status = ZEROSIS_CITY_SITE_BATCH_FAILURE;
        return ZEROSIS_CITY_SITE_BATCH_FAILURE;
    }
}
