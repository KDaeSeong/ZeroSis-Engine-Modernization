#include "FoundValueScoreBridge.h"

#include "FoundValueScores.h"
#include "OrderedBatch.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

#include <algorithm>
#include <array>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <exception>
#include <limits>
#include <memory>
#include <mutex>
#include <thread>
#include <vector>

namespace {
using zerosis::concurrency::BatchStamp;
using zerosis::concurrency::BatchStatus;
using zerosis::concurrency::CancellationToken;
using zerosis::concurrency::Job;
using zerosis::found_value::OwnerKind;
using zerosis::found_value::Path;
using zerosis::found_value::Result;
using zerosis::found_value::Snapshot;
using zerosis::found_value::Status;

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

struct OwnedJob {
    std::uint32_t index;
    Snapshot snapshot;
};

struct WorkerOutput {
    Result result;
    std::uint32_t worker_slot;
};

class ScoreOperation {
public:
    explicit ScoreOperation(std::shared_ptr<InvocationState> state) : state_(std::move(state)) {}

    WorkerOutput operator()(const OwnedJob& input, const CancellationToken&) const {
        const auto slot = state_->Enter();
        if (slot == 0) return {{Status::invalid_snapshot, 0}, 0};
        struct Exit {
            InvocationState& state;
            ~Exit() { state.Leave(); }
        } exit{*state_};
        return {zerosis::found_value::evaluate(input.snapshot), slot};
    }

private:
    std::shared_ptr<InvocationState> state_;
};

bool Flag(const std::uint32_t value) noexcept { return value <= 1; }

bool CopyInput(const ZeroSisFoundValueInput& source, Snapshot& target) noexcept {
    if (source.abi_version != ZEROSIS_FOUND_VALUE_ABI_VERSION ||
        source.config_version != ZEROSIS_FOUND_VALUE_CONFIG_VERSION ||
        source.reserved[0] != 0 || source.reserved[1] != 0 ||
        source.reserved[2] != 0 || source.reserved[3] != 0) return false;
    const std::uint32_t flags[] = {
        source.valid, source.has_player, source.center_present, source.capital_present,
        source.center_can_found_visible, source.center_can_found_full,
        source.center_has_unique_luxury, source.center_has_resource_for_team,
        source.center_is_river, source.center_is_coastal, source.coastal_civilization,
        source.human_player, source.faith_from_unimproved_forest,
        source.move_friendly_woods_as_road, source.gets_natural_wonder_yield_modifier,
        source.is_inca, source.is_brazil, source.is_morocco, source.is_netherlands,
    };
    for (const auto flag : flags) if (!Flag(flag)) return false;
    if (source.path != ZEROSIS_FOUND_VALUE_PATH_SETTLER_NO_YIELD_NO_COAST_ONLY)
        target.path = Path::other;
    else
        target.path = Path::settler_no_yield_no_coast_only;

    target.valid = source.valid != 0;
    target.has_player = source.has_player != 0;
    target.center_present = source.center_present != 0;
    target.capital_present = source.capital_present != 0;
    target.center_can_found_visible = source.center_can_found_visible != 0;
    target.center_can_found_full = source.center_can_found_full != 0;
    target.center_has_unique_luxury = source.center_has_unique_luxury != 0;
    target.center_has_resource_for_team = source.center_has_resource_for_team != 0;
    target.center_is_river = source.center_is_river != 0;
    target.center_is_coastal = source.center_is_coastal != 0;
    target.coastal_civilization = source.coastal_civilization != 0;
    target.human_player = source.human_player != 0;
    target.faith_from_unimproved_forest = source.faith_from_unimproved_forest != 0;
    target.move_friendly_woods_as_road = source.move_friendly_woods_as_road != 0;
    target.gets_natural_wonder_yield_modifier = source.gets_natural_wonder_yield_modifier != 0;
    target.is_inca = source.is_inca != 0;
    target.is_brazil = source.is_brazil != 0;
    target.is_morocco = source.is_morocco != 0;
    target.is_netherlands = source.is_netherlands != 0;

    target.center_area = source.center_area;
    target.capital_area = source.capital_area;
    target.naval_flavor = source.naval_flavor;
    target.growth_flavor = source.growth_flavor;
    target.expansion_flavor = source.expansion_flavor;
    target.boldness = source.boldness;
    for (std::size_t index = 0; index < target.ring_modifier.size(); ++index)
        target.ring_modifier[index] = source.ring_modifier[index];
    target.settler_food_multiplier = source.settler_food_multiplier;
    target.settler_happiness_multiplier = source.settler_happiness_multiplier;
    target.settler_production_multiplier = source.settler_production_multiplier;
    target.settler_gold_multiplier = source.settler_gold_multiplier;
    target.settler_science_multiplier = source.settler_science_multiplier;
    target.settler_faith_multiplier = source.settler_faith_multiplier;
    target.faith_flavor_multiplier = source.faith_flavor_multiplier;
    target.settler_resource_multiplier = source.settler_resource_multiplier;
    target.settler_strategic_multiplier = source.settler_strategic_multiplier;
    target.build_on_resource_percent = source.build_on_resource_percent;
    target.build_on_river_percent = source.build_on_river_percent;
    target.build_on_coast_percent = source.build_on_coast_percent;
    target.min_city_range = source.min_city_range;
    target.min_water_size_for_ocean = source.min_water_size_for_ocean;
    target.brazil_multiplier = source.brazil_multiplier;
    target.spain_multiplier = source.spain_multiplier;
    target.morocco_multiplier = source.morocco_multiplier;
    target.netherlands_multiplier = source.netherlands_multiplier;
    target.inca_multiplier = source.inca_multiplier;
    target.major_civ_count = source.major_civ_count;

    for (std::size_t index = 0; index < target.tiles.size(); ++index) {
        const auto& from = source.tiles[index];
        if (!Flag(from.present) || !Flag(from.city) || !Flag(from.city_owner_is_major) ||
            !Flag(from.forest) || !Flag(from.jungle) || !Flag(from.wetlands) ||
            !Flag(from.natural_wonder) || !Flag(from.desert_without_resource) ||
            !Flag(from.hills) || !Flag(from.unimproved) ||
            from.owner > ZEROSIS_FOUND_VALUE_OWNER_OTHER) return false;
        auto& to = target.tiles[index];
        to.present = from.present != 0;
        to.distance = from.distance;
        to.owner = static_cast<OwnerKind>(from.owner);
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
    }
    return true;
}

struct MemoryRange { std::uintptr_t begin; std::uintptr_t end; };

bool MakeRange(const void* pointer, std::size_t bytes, MemoryRange& range) noexcept {
    if (bytes == 0) { range = {0, 0}; return true; }
    if (pointer == nullptr) return false;
    const auto begin = reinterpret_cast<std::uintptr_t>(pointer);
    if (bytes > (std::numeric_limits<std::uintptr_t>::max)() - begin) return false;
    range = {begin, begin + bytes};
    return true;
}

bool Overlaps(const MemoryRange& left, const MemoryRange& right) noexcept {
    return left.begin != left.end && right.begin != right.end &&
           left.begin < right.end && right.begin < left.end;
}

bool ValidWorkerCount(const std::uint32_t count) noexcept {
    return count == 1 || count == 2 || count == 4;
}

void CopyMetrics(InvocationState& state, ZeroSisFoundValueMetrics& metrics) {
    std::lock_guard<std::mutex> lock(state.mutex);
    metrics.worker_threads_used = state.used;
    metrics.maximum_overlapping_jobs = state.maximum_overlap;
    for (std::uint32_t index = 0; index < state.used; ++index) {
        metrics.worker_thread_ids[index] = state.thread_ids[index];
        metrics.worker_job_counts[index] = state.job_counts[index];
    }
}

std::int32_t ReturnFailure(ZeroSisFoundValueMetrics& metrics, const std::uint32_t status) noexcept {
    metrics.status = status;
    return static_cast<std::int32_t>(status);
}
} // namespace

extern "C" std::int32_t ZeroSisFoundValueEvaluateBatch(
    const ZeroSisFoundValueInput* inputs, const std::uint32_t count,
    const ZeroSisFoundValueConfig* config, ZeroSisFoundValueResult* results,
    ZeroSisFoundValueMetrics* metrics) {
    if (metrics == nullptr) return ZEROSIS_FOUND_VALUE_INVALID_INPUT;
    if (count > (std::numeric_limits<std::size_t>::max)() / sizeof(ZeroSisFoundValueInput) ||
        count > (std::numeric_limits<std::size_t>::max)() / sizeof(ZeroSisFoundValueResult))
        return ZEROSIS_FOUND_VALUE_INVALID_INPUT;
    MemoryRange input_range{}, output_range{}, metrics_range{}, config_range{};
    if (!MakeRange(inputs, static_cast<std::size_t>(count) * sizeof(ZeroSisFoundValueInput), input_range) ||
        !MakeRange(results, static_cast<std::size_t>(count) * sizeof(ZeroSisFoundValueResult), output_range) ||
        !MakeRange(metrics, sizeof(*metrics), metrics_range) ||
        (config != nullptr && !MakeRange(config, sizeof(*config), config_range)))
        return ZEROSIS_FOUND_VALUE_INVALID_INPUT;
    if (Overlaps(input_range, output_range) || Overlaps(input_range, metrics_range) ||
        Overlaps(output_range, metrics_range) ||
        (config != nullptr && (Overlaps(input_range, config_range) ||
                               Overlaps(output_range, config_range) ||
                               Overlaps(metrics_range, config_range))))
        return ZEROSIS_FOUND_VALUE_INVALID_INPUT;

    *metrics = {};
    metrics->abi_version = ZEROSIS_FOUND_VALUE_ABI_VERSION;
    metrics->config_version = ZEROSIS_FOUND_VALUE_CONFIG_VERSION;
    if (config == nullptr) return ReturnFailure(*metrics, ZEROSIS_FOUND_VALUE_INVALID_INPUT);
    const ZeroSisFoundValueConfig owned_config = *config;
    metrics->requested_workers = owned_config.requested_workers;
    metrics->owner_thread_id = owned_config.owner_thread_id;
    if (owned_config.abi_version != ZEROSIS_FOUND_VALUE_ABI_VERSION ||
        owned_config.config_version != ZEROSIS_FOUND_VALUE_CONFIG_VERSION ||
        owned_config.reserved[0] != 0 || owned_config.reserved[1] != 0 ||
        owned_config.reserved[2] != 0 || owned_config.reserved[3] != 0 ||
        !ValidWorkerCount(owned_config.requested_workers))
        return ReturnFailure(*metrics, ZEROSIS_FOUND_VALUE_INVALID_INPUT);
    if (owned_config.owner_thread_id != static_cast<std::uint32_t>(::GetCurrentThreadId()))
        return ReturnFailure(*metrics, ZEROSIS_FOUND_VALUE_WRONG_OWNER_THREAD);

    const auto started = std::chrono::steady_clock::now();
    try {
        std::vector<Job<OwnedJob>> jobs;
        jobs.reserve(count);
        for (std::uint32_t index = 0; index < count; ++index) {
            Snapshot snapshot{};
            if (!CopyInput(inputs[index], snapshot))
                return ReturnFailure(*metrics, ZEROSIS_FOUND_VALUE_INVALID_INPUT);
            jobs.push_back({index, {index, std::move(snapshot)}});
        }
        metrics->jobs_total = count;
        if (count == 0) return ReturnFailure(*metrics, ZEROSIS_FOUND_VALUE_OK);

        auto invocation = std::make_shared<InvocationState>();
        const BatchStamp stamp{0, 0, 0, 0, 0};
        const auto batch = zerosis::concurrency::evaluate_ordered(
            stamp, std::move(jobs), owned_config.requested_workers, ScoreOperation(invocation));
        metrics->jobs_started = static_cast<std::uint32_t>(batch.jobs_started);
        metrics->jobs_completed = static_cast<std::uint32_t>(batch.jobs_completed);
        metrics->workers_started = static_cast<std::uint32_t>(batch.workers_started);
        CopyMetrics(*invocation, *metrics);
        metrics->worker_batch_us = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count());

        if (batch.status != BatchStatus::ready || batch.rows.size() != count)
            return ReturnFailure(*metrics, ZEROSIS_FOUND_VALUE_BATCH_FAILURE);
        for (std::uint32_t index = 0; index < count; ++index) {
            if (batch.rows[index].id != index || batch.rows[index].value.worker_slot == 0)
                return ReturnFailure(*metrics, ZEROSIS_FOUND_VALUE_BATCH_FAILURE);
            const auto status = batch.rows[index].value.result.status;
            if (status != Status::ok) {
                const std::uint32_t mapped = status == Status::overflow ? ZEROSIS_FOUND_VALUE_OVERFLOW :
                    status == Status::unsupported_path ? ZEROSIS_FOUND_VALUE_UNSUPPORTED_PATH :
                    ZEROSIS_FOUND_VALUE_INVALID_SNAPSHOT;
                return ReturnFailure(*metrics, mapped);
            }
        }
        for (std::uint32_t index = 0; index < count; ++index) {
            results[index].score = batch.rows[index].value.result.score;
            results[index].status = ZEROSIS_FOUND_VALUE_OK;
        }
        return ReturnFailure(*metrics, ZEROSIS_FOUND_VALUE_OK);
    } catch (...) {
        metrics->worker_batch_us = static_cast<std::uint64_t>(
            std::chrono::duration_cast<std::chrono::microseconds>(
                std::chrono::steady_clock::now() - started).count());
        return ReturnFailure(*metrics, ZEROSIS_FOUND_VALUE_BATCH_FAILURE);
    }
}
