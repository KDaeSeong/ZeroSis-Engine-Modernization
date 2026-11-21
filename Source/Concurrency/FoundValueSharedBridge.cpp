#include "FoundValueSharedBridge.h"

#include "FoundValueSharedScores.h"
#include "OrderedBatch.h"
#include "FoundValueCpuTrace.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <memory>
#include <mutex>
#include <thread>
#include <utility>
#include <vector>

namespace {
namespace fv = zerosis::found_value;
namespace shared = zerosis::found_value_shared;
using zerosis::concurrency::BatchStamp;
using zerosis::concurrency::BatchStatus;
using zerosis::concurrency::CancellationToken;
using zerosis::concurrency::Job;

struct MemoryRange { std::uintptr_t begin; std::uintptr_t end; };

bool MakeRange(const void* pointer, const std::size_t bytes, MemoryRange& range) noexcept {
    if (bytes == 0) { range = {0, 0}; return true; }
    if (pointer == nullptr) return false;
    const auto begin = reinterpret_cast<std::uintptr_t>(pointer);
    if (bytes > (std::numeric_limits<std::uintptr_t>::max)() - begin) return false;
    range = {begin, begin + bytes};
    return true;
}

bool Overlaps(const MemoryRange& a, const MemoryRange& b) noexcept {
    return a.begin != a.end && b.begin != b.end && a.begin < b.end && b.begin < a.end;
}

bool Flag(const std::uint32_t value) noexcept { return value <= 1; }

bool ValidWorkers(const std::uint32_t value) noexcept {
    return value == 1 || value == 2 || value == 4;
}

std::uint32_t MapStatus(const fv::Status value) noexcept {
    switch (value) {
    case fv::Status::ok: return ZEROSIS_FOUND_VALUE_OK;
    case fv::Status::unsupported_path: return ZEROSIS_FOUND_VALUE_UNSUPPORTED_PATH;
    case fv::Status::overflow: return ZEROSIS_FOUND_VALUE_OVERFLOW;
    case fv::Status::invalid_snapshot: return ZEROSIS_FOUND_VALUE_INVALID_SNAPSHOT;
    }
    return ZEROSIS_FOUND_VALUE_INVALID_SNAPSHOT;
}

struct InvocationState {
    std::mutex mutex;
    std::array<std::uint32_t, ZEROSIS_FOUND_VALUE_WORKER_SLOTS> thread_ids{};
    std::array<std::uint32_t, ZEROSIS_FOUND_VALUE_WORKER_SLOTS> job_counts{};
    std::uint32_t used = 0;
    std::uint32_t active = 0;
    std::uint32_t maximum_overlap = 0;

    std::uint32_t Enter() {
        const auto id = static_cast<std::uint32_t>(::GetCurrentThreadId());
        std::lock_guard<std::mutex> lock(mutex);
        std::uint32_t slot = 0;
        while (slot < used && thread_ids[slot] != id) ++slot;
        if (slot == used) {
            if (used == thread_ids.size()) return 0;
            thread_ids[used++] = id;
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

struct OwnedBatch {
    shared::CommonSnapshot common{};
    std::vector<shared::PlotFacts> plots;
    std::vector<shared::Candidate> candidates;
};

std::atomic<std::uint64_t> g_last_issued_batch_id{0};
thread_local std::uint64_t g_owner_last_batch_id = 0;
thread_local std::uint32_t g_owner_last_batch_thread_id = 0;

std::uint64_t NextTraceBatchId() noexcept {
    LARGE_INTEGER counter = {};
    if (!::QueryPerformanceCounter(&counter) || counter.QuadPart <= 0) return 0;
    std::uint64_t candidate = static_cast<std::uint64_t>(counter.QuadPart);
    std::uint64_t previous = g_last_issued_batch_id.load(std::memory_order_relaxed);
    for (;;) {
        if (candidate <= previous) {
            if (previous == (std::numeric_limits<std::uint64_t>::max)()) return 0;
            candidate = previous + 1;
        }
        if (g_last_issued_batch_id.compare_exchange_weak(previous, candidate,
                std::memory_order_relaxed, std::memory_order_relaxed)) return candidate;
    }
}

struct WorkerOutput { fv::Result result{}; std::uint32_t worker_slot = 0; };

class SharedOperation {
public:
    SharedOperation(std::shared_ptr<const OwnedBatch> batch,
                    std::shared_ptr<InvocationState> state,
                    const ZeroSisConcurrency::FoundValueCpuTraceBatch* trace_batch)
        : batch_(std::move(batch)), state_(std::move(state)), trace_batch_(trace_batch) {}

    WorkerOutput operator()(const std::uint32_t& candidate_index,
                            const CancellationToken&) const {
        const auto slot = state_->Enter();
        if (slot == 0) return {{fv::Status::invalid_snapshot, 0}, 0};
        struct Exit { InvocationState& state; ~Exit() { state.Leave(); } } exit{*state_};
        const auto& candidate = batch_->candidates[candidate_index];
        ZeroSisConcurrency::FoundValueCpuTraceJob trace_job(*trace_batch_, candidate_index,
            static_cast<std::uint32_t>(batch_->plots.size()));
        return {shared::evaluate_shared_prevalidated(batch_->common, candidate,
            batch_->plots.empty() ? nullptr : batch_->plots.data(), batch_->plots.size()), slot};
    }

private:
    std::shared_ptr<const OwnedBatch> batch_;
    std::shared_ptr<InvocationState> state_;
    const ZeroSisConcurrency::FoundValueCpuTraceBatch* trace_batch_;
};

void CopyMetrics(InvocationState& state, ZeroSisFoundValueMetrics& metrics) {
    std::lock_guard<std::mutex> lock(state.mutex);
    metrics.worker_threads_used = state.used;
    metrics.maximum_overlapping_jobs = state.maximum_overlap;
    for (std::uint32_t index = 0; index < state.used; ++index) {
        metrics.worker_thread_ids[index] = state.thread_ids[index];
        metrics.worker_job_counts[index] = state.job_counts[index];
    }
}

std::int32_t Fail(ZeroSisFoundValueMetrics& metrics, const std::uint32_t status) noexcept {
    metrics.status = status;
    return static_cast<std::int32_t>(status);
}

bool ValidCommonAbi(const ZeroSisFoundValueSharedCommon& c) noexcept {
    if (c.abi_version != ZEROSIS_FOUND_VALUE_SHARED_ABI_VERSION ||
        c.config_version != ZEROSIS_FOUND_VALUE_CONFIG_VERSION ||
        c.valid > 1 || c.has_player > 1 || c.center_present != 1 || c.capital_present > 1 ||
        c.center_can_found_visible != 0 || c.center_can_found_full != 0 ||
        c.center_has_unique_luxury != 0 || c.center_has_resource_for_team != 0 ||
        c.center_is_river != 0 || c.center_is_coastal != 0 || c.center_area != 0 ||
        c.coastal_civilization > 1 || c.human_player > 1 ||
        c.faith_from_unimproved_forest > 1 || c.move_friendly_woods_as_road > 1 ||
        c.gets_natural_wonder_yield_modifier > 1 || c.is_inca > 1 || c.is_brazil > 1 ||
        c.is_morocco > 1 || c.is_netherlands > 1 || c.reserved[0] != 0 || c.reserved[1] != 0 ||
        c.reserved[2] != 0 || c.reserved[3] != 0) return false;
    return true;
}

fv::Status CopyCommon(const ZeroSisFoundValueSharedCommon& from,
                      shared::CommonSnapshot& to) noexcept {
    to.path = from.path == ZEROSIS_FOUND_VALUE_PATH_SETTLER_NO_YIELD_NO_COAST_ONLY
        ? fv::Path::settler_no_yield_no_coast_only : fv::Path::other;
    to.valid = from.valid != 0;
    to.has_player = from.has_player != 0;
    to.center_present = from.center_present != 0;
    to.capital_present = from.capital_present != 0;
    to.coastal_civilization = from.coastal_civilization != 0;
    to.human_player = from.human_player != 0;
    to.faith_from_unimproved_forest = from.faith_from_unimproved_forest != 0;
    to.move_friendly_woods_as_road = from.move_friendly_woods_as_road != 0;
    to.gets_natural_wonder_yield_modifier = from.gets_natural_wonder_yield_modifier != 0;
    to.is_inca = from.is_inca != 0;
    to.is_brazil = from.is_brazil != 0;
    to.is_morocco = from.is_morocco != 0;
    to.is_netherlands = from.is_netherlands != 0;
    to.center_area = from.center_area;
    to.capital_area = from.capital_area;
    to.naval_flavor = from.naval_flavor;
    to.growth_flavor = from.growth_flavor;
    to.expansion_flavor = from.expansion_flavor;
    to.boldness = from.boldness;
    for (std::size_t i = 0; i < to.ring_modifier.size(); ++i) to.ring_modifier[i] = from.ring_modifier[i];
    to.settler_food_multiplier = from.settler_food_multiplier;
    to.settler_happiness_multiplier = from.settler_happiness_multiplier;
    to.settler_production_multiplier = from.settler_production_multiplier;
    to.settler_gold_multiplier = from.settler_gold_multiplier;
    to.settler_science_multiplier = from.settler_science_multiplier;
    to.settler_faith_multiplier = from.settler_faith_multiplier;
    to.faith_flavor_multiplier = from.faith_flavor_multiplier;
    to.settler_resource_multiplier = from.settler_resource_multiplier;
    to.settler_strategic_multiplier = from.settler_strategic_multiplier;
    to.build_on_resource_percent = from.build_on_resource_percent;
    to.build_on_river_percent = from.build_on_river_percent;
    to.build_on_coast_percent = from.build_on_coast_percent;
    to.min_city_range = from.min_city_range;
    to.min_water_size_for_ocean = from.min_water_size_for_ocean;
    to.brazil_multiplier = from.brazil_multiplier;
    to.spain_multiplier = from.spain_multiplier;
    to.morocco_multiplier = from.morocco_multiplier;
    to.netherlands_multiplier = from.netherlands_multiplier;
    to.inca_multiplier = from.inca_multiplier;
    to.major_civ_count = from.major_civ_count;
    return fv::Status::ok;
}

bool CopyTile(const ZeroSisFoundValueTile& from, fv::Tile& to) noexcept {
    if (!Flag(from.present) || !Flag(from.city) || !Flag(from.city_owner_is_major) ||
        !Flag(from.forest) || !Flag(from.jungle) || !Flag(from.wetlands) ||
        !Flag(from.natural_wonder) || !Flag(from.desert_without_resource) ||
        !Flag(from.hills) || !Flag(from.unimproved) ||
        from.owner > ZEROSIS_FOUND_VALUE_OWNER_OTHER) return false;
    to.present = from.present != 0;
    to.distance = from.distance;
    to.owner = static_cast<fv::OwnerKind>(from.owner);
    to.city = from.city != 0;
    to.city_owner_is_major = from.city_owner_is_major != 0;
    to.food_value = from.food_value;
    to.happiness_value = from.happiness_value;
    to.production_value = from.production_value;
    to.gold_value = from.gold_value;
    to.science_value = from.science_value;
    to.faith_value = from.faith_value;
    to.resource_value = from.resource_value;
    to.strategic_value = from.strategic_value;
    to.forest = from.forest != 0;
    to.jungle = from.jungle != 0;
    to.wetlands = from.wetlands != 0;
    to.natural_wonder = from.natural_wonder != 0;
    to.desert_without_resource = from.desert_without_resource != 0;
    to.hills = from.hills != 0;
    to.adjacent_mountains = from.adjacent_mountains;
    to.unimproved = from.unimproved != 0;
    return true;
}

bool CopyPlot(const ZeroSisFoundValueSharedPlot& from, shared::PlotFacts& to) noexcept {
    if (!CopyTile(from.tile, to.tile)) return false;
    for (std::size_t i = 0; i < to.strategic_by_distance.size(); ++i)
        to.strategic_by_distance[i] = from.strategic_by_distance[i];
    return true;
}

bool CopyCandidate(const ZeroSisFoundValueSharedCandidate& from, shared::Candidate& to) noexcept {
    const std::uint32_t flags[] = {from.center_can_found_visible, from.center_can_found_full,
        from.center_has_unique_luxury, from.center_has_resource_for_team,
        from.center_is_river, from.center_is_coastal};
    for (const auto flag : flags) if (!Flag(flag)) return false;
    for (const auto value : from.reserved) if (value != 0) return false;
    to.center_plot_index = from.center_plot_index;
    to.center_can_found_visible = from.center_can_found_visible != 0;
    to.center_can_found_full = from.center_can_found_full != 0;
    to.center_has_unique_luxury = from.center_has_unique_luxury != 0;
    to.center_has_resource_for_team = from.center_has_resource_for_team != 0;
    to.center_is_river = from.center_is_river != 0;
    to.center_is_coastal = from.center_is_coastal != 0;
    to.center_area = from.center_area;
    for (std::size_t i = 0; i < to.slots.size(); ++i) {
        to.slots[i].map_plot_index = from.slots[i].map_plot_index;
        to.slots[i].distance = from.slots[i].distance;
    }
    return true;
}

} // namespace

extern "C" std::int32_t ZeroSisFoundValueEvaluateSharedBatch(
    const ZeroSisFoundValueSharedCommon* common,
    const ZeroSisFoundValueSharedPlot* plots, const std::uint32_t plot_count,
    const ZeroSisFoundValueSharedCandidate* candidates, const std::uint32_t candidate_count,
    const ZeroSisFoundValueConfig* config, ZeroSisFoundValueResult* results,
    ZeroSisFoundValueMetrics* metrics) {
    g_owner_last_batch_id = 0;
    g_owner_last_batch_thread_id = static_cast<std::uint32_t>(::GetCurrentThreadId());
    if (metrics == nullptr || common == nullptr || config == nullptr) return ZEROSIS_FOUND_VALUE_INVALID_INPUT;
    if (plot_count > (std::numeric_limits<std::size_t>::max)() / sizeof(*plots) ||
        candidate_count > (std::numeric_limits<std::size_t>::max)() / sizeof(*candidates) ||
        candidate_count > (std::numeric_limits<std::size_t>::max)() / sizeof(*results))
        return ZEROSIS_FOUND_VALUE_INVALID_INPUT;

    MemoryRange ranges[6]{};
    if (!MakeRange(common, sizeof(*common), ranges[0]) ||
        !MakeRange(plots, static_cast<std::size_t>(plot_count) * sizeof(*plots), ranges[1]) ||
        !MakeRange(candidates, static_cast<std::size_t>(candidate_count) * sizeof(*candidates), ranges[2]) ||
        !MakeRange(config, sizeof(*config), ranges[3]) ||
        !MakeRange(results, static_cast<std::size_t>(candidate_count) * sizeof(*results), ranges[4]) ||
        !MakeRange(metrics, sizeof(*metrics), ranges[5])) return ZEROSIS_FOUND_VALUE_INVALID_INPUT;
    for (std::size_t i = 0; i < 6; ++i)
        for (std::size_t j = i + 1; j < 6; ++j)
            if (Overlaps(ranges[i], ranges[j])) return ZEROSIS_FOUND_VALUE_INVALID_INPUT;

    *metrics = {};
    metrics->abi_version = ZEROSIS_FOUND_VALUE_ABI_VERSION;
    metrics->config_version = ZEROSIS_FOUND_VALUE_CONFIG_VERSION;
    const ZeroSisFoundValueConfig owned_config = *config;
    metrics->requested_workers = owned_config.requested_workers;
    metrics->owner_thread_id = owned_config.owner_thread_id;
    if (owned_config.owner_thread_id != static_cast<std::uint32_t>(::GetCurrentThreadId()))
        return Fail(*metrics, ZEROSIS_FOUND_VALUE_WRONG_OWNER_THREAD);
    if (owned_config.abi_version != ZEROSIS_FOUND_VALUE_ABI_VERSION ||
        owned_config.config_version != ZEROSIS_FOUND_VALUE_CONFIG_VERSION ||
        !ValidWorkers(owned_config.requested_workers) || owned_config.reserved[0] != 0 ||
        owned_config.reserved[1] != 0 || owned_config.reserved[2] != 0 || owned_config.reserved[3] != 0)
        return Fail(*metrics, ZEROSIS_FOUND_VALUE_INVALID_INPUT);
    if (!ValidCommonAbi(*common)) return Fail(*metrics, ZEROSIS_FOUND_VALUE_INVALID_INPUT);

    const auto started = std::chrono::steady_clock::now();
    try {
        auto owned = std::make_shared<OwnedBatch>();
        const auto common_status = CopyCommon(*common, owned->common);
        if (common_status != fv::Status::ok) return Fail(*metrics, MapStatus(common_status));
        owned->plots.resize(plot_count);
        for (std::uint32_t i = 0; i < plot_count; ++i)
            if (!CopyPlot(plots[i], owned->plots[i]))
                return Fail(*metrics, ZEROSIS_FOUND_VALUE_INVALID_INPUT);
        owned->candidates.resize(candidate_count);
        for (std::uint32_t i = 0; i < candidate_count; ++i)
            if (!CopyCandidate(candidates[i], owned->candidates[i]))
                return Fail(*metrics, ZEROSIS_FOUND_VALUE_INVALID_INPUT);
        const auto candidate_status = shared::validate_batch(owned->common,
            owned->plots.empty() ? nullptr : owned->plots.data(), owned->plots.size(),
            owned->candidates.empty() ? nullptr : owned->candidates.data(), owned->candidates.size());
        if (candidate_status != fv::Status::ok)
            return Fail(*metrics, MapStatus(candidate_status));

        metrics->jobs_total = candidate_count;
        if (candidate_count == 0) return Fail(*metrics, ZEROSIS_FOUND_VALUE_OK);

        std::vector<Job<std::uint32_t>> jobs;
        jobs.reserve(candidate_count);
        for (std::uint32_t i = 0; i < candidate_count; ++i) jobs.push_back({i, i});
        auto state = std::make_shared<InvocationState>();
        const BatchStamp stamp{0, 0, 0, 0, 0};
        zerosis::concurrency::BatchResult<WorkerOutput> batch{stamp};
        const std::uint64_t trace_batch_id = NextTraceBatchId();
        if (trace_batch_id == 0) return Fail(*metrics, ZEROSIS_FOUND_VALUE_BATCH_FAILURE);
        {
            ZeroSisConcurrency::FoundValueCpuTraceBatch trace_batch(trace_batch_id);
            batch = zerosis::concurrency::evaluate_ordered(stamp, std::move(jobs),
                owned_config.requested_workers, SharedOperation(owned, state, &trace_batch));
        } // The trace batch closes only after evaluate_ordered joins every worker.
        metrics->jobs_started = static_cast<std::uint32_t>(batch.jobs_started);
        metrics->jobs_completed = static_cast<std::uint32_t>(batch.jobs_completed);
        metrics->workers_started = static_cast<std::uint32_t>(batch.workers_started);
        CopyMetrics(*state, *metrics);
        metrics->worker_batch_us = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count());
        if (batch.status != BatchStatus::ready || batch.rows.size() != candidate_count)
            return Fail(*metrics, ZEROSIS_FOUND_VALUE_BATCH_FAILURE);
        for (std::uint32_t i = 0; i < candidate_count; ++i) {
            if (batch.rows[i].id != i || batch.rows[i].value.worker_slot == 0)
                return Fail(*metrics, ZEROSIS_FOUND_VALUE_BATCH_FAILURE);
            const auto status = batch.rows[i].value.result.status;
            if (status != fv::Status::ok) return Fail(*metrics, MapStatus(status));
        }
        for (std::uint32_t i = 0; i < candidate_count; ++i) {
            results[i].score = batch.rows[i].value.result.score;
            results[i].status = ZEROSIS_FOUND_VALUE_OK;
        }
        g_owner_last_batch_id = trace_batch_id;
        return Fail(*metrics, ZEROSIS_FOUND_VALUE_OK);
    } catch (...) {
        metrics->worker_batch_us = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count());
        return Fail(*metrics, ZEROSIS_FOUND_VALUE_BATCH_FAILURE);
    }
}

extern "C" std::uint64_t ZeroSisFoundValueSharedLastBatchId(void) {
    if (g_owner_last_batch_thread_id != static_cast<std::uint32_t>(::GetCurrentThreadId())) return 0;
    return g_owner_last_batch_id;
}
