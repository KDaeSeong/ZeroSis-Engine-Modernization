#include "FoundValueSharedBridge.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <thread>
#include <vector>

namespace {
constexpr std::size_t kCenterOffset = 7u * 15u + 7u;
std::uint32_t checks = 0;

ZeroSisFoundValueSharedCommon common() {
    ZeroSisFoundValueSharedCommon c{};
    c.abi_version = ZEROSIS_FOUND_VALUE_SHARED_ABI_VERSION;
    c.config_version = ZEROSIS_FOUND_VALUE_CONFIG_VERSION;
    c.path = ZEROSIS_FOUND_VALUE_PATH_SETTLER_NO_YIELD_NO_COAST_ONLY;
    c.valid = c.has_player = c.center_present = c.capital_present = 1;
    c.capital_area = 1;
    c.min_city_range = 3;
    c.min_water_size_for_ocean = 10;
    c.major_civ_count = 18;
    const std::int32_t rings[8] = {1, 6, 3, 2, 1, 1, 0, 0};
    std::memcpy(c.ring_modifier, rings, sizeof(rings));
    c.settler_food_multiplier = 15;
    c.settler_happiness_multiplier = 6;
    c.settler_production_multiplier = 3;
    c.settler_gold_multiplier = 2;
    c.settler_science_multiplier = 1;
    c.settler_faith_multiplier = 2;
    c.faith_flavor_multiplier = 17;
    c.settler_resource_multiplier = 1;
    c.settler_strategic_multiplier = 1;
    c.build_on_resource_percent = -50;
    c.build_on_river_percent = 15;
    c.build_on_coast_percent = 40;
    c.brazil_multiplier = 1000;
    c.spain_multiplier = 55000;
    c.morocco_multiplier = 1000;
    c.netherlands_multiplier = 2000;
    c.inca_multiplier = 500;
    return c;
}

ZeroSisFoundValueConfig config(const std::uint32_t workers) {
    ZeroSisFoundValueConfig c{};
    c.abi_version = ZEROSIS_FOUND_VALUE_ABI_VERSION;
    c.config_version = ZEROSIS_FOUND_VALUE_CONFIG_VERSION;
    c.requested_workers = workers;
    c.owner_thread_id = static_cast<std::uint32_t>(::GetCurrentThreadId());
    return c;
}

ZeroSisFoundValueSharedPlot fact(const std::uint32_t index) {
    ZeroSisFoundValueSharedPlot p{};
    p.tile.present = 1;
    p.tile.distance = 0;
    p.tile.owner = ZEROSIS_FOUND_VALUE_OWNER_UNOWNED;
    p.tile.food_value = static_cast<std::int32_t>(index % 7u + 1u);
    p.tile.production_value = static_cast<std::int32_t>(index % 5u + 1u);
    p.tile.gold_value = static_cast<std::int32_t>(index % 3u);
    p.tile.science_value = static_cast<std::int32_t>(index % 4u);
    p.tile.faith_value = static_cast<std::int32_t>(index % 6u);
    p.tile.happiness_value = static_cast<std::int32_t>(index % 3u);
    p.tile.resource_value = static_cast<std::int32_t>(index % 4u);
    p.tile.forest = static_cast<std::uint32_t>((index % 3u) == 0);
    p.tile.unimproved = static_cast<std::uint32_t>((index % 2u) == 0);
    for (std::size_t distance = 1; distance <= 5; ++distance)
        p.strategic_by_distance[distance] = static_cast<std::int32_t>(index + distance * 2u);
    return p;
}

ZeroSisFoundValueSharedCandidate candidate(const std::uint32_t center,
                                           const std::uint32_t neighbor) {
    ZeroSisFoundValueSharedCandidate c{};
    c.center_plot_index = center;
    c.center_can_found_visible = c.center_can_found_full = 1;
    c.center_has_resource_for_team = static_cast<std::uint32_t>((center % 2u) != 0);
    c.center_is_river = static_cast<std::uint32_t>((center % 3u) == 0);
    c.center_is_coastal = static_cast<std::uint32_t>((center % 5u) == 0);
    c.center_area = 1;
    for (auto& slot : c.slots) {
        slot.map_plot_index = ZEROSIS_FOUND_VALUE_SHARED_MISSING_PLOT;
        slot.distance = 0;
    }
    c.slots[kCenterOffset] = {center, 0};
    c.slots[static_cast<std::size_t>((1 + 7) * 15 + 7)] = {neighbor, 1};
    c.slots[static_cast<std::size_t>((2 + 7) * 15 + 7)] = {neighbor, 2};
    c.slots[static_cast<std::size_t>((3 + 7) * 15 + 7)] = {neighbor, 3};
    c.slots[static_cast<std::size_t>((4 + 7) * 15 + 7)] = {neighbor, 4};
    c.slots[static_cast<std::size_t>((5 + 7) * 15 + 7)] = {neighbor, 5};
    return c;
}

void copy_common_to_dense(const ZeroSisFoundValueSharedCommon& from,
                          ZeroSisFoundValueInput& to) {
    to.abi_version = ZEROSIS_FOUND_VALUE_ABI_VERSION;
    to.config_version = ZEROSIS_FOUND_VALUE_CONFIG_VERSION;
    to.path = from.path;
    to.valid = from.valid;
    to.has_player = from.has_player;
    to.center_present = 1;
    to.capital_present = from.capital_present;
    to.coastal_civilization = from.coastal_civilization;
    to.human_player = from.human_player;
    to.faith_from_unimproved_forest = from.faith_from_unimproved_forest;
    to.move_friendly_woods_as_road = from.move_friendly_woods_as_road;
    to.gets_natural_wonder_yield_modifier = from.gets_natural_wonder_yield_modifier;
    to.is_inca = from.is_inca;
    to.is_brazil = from.is_brazil;
    to.is_morocco = from.is_morocco;
    to.is_netherlands = from.is_netherlands;
    to.capital_area = from.capital_area;
    to.naval_flavor = from.naval_flavor;
    to.growth_flavor = from.growth_flavor;
    to.expansion_flavor = from.expansion_flavor;
    to.boldness = from.boldness;
    std::memcpy(to.ring_modifier, from.ring_modifier, sizeof(to.ring_modifier));
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
}

ZeroSisFoundValueInput dense_reference(const ZeroSisFoundValueSharedCommon& c,
    const ZeroSisFoundValueSharedCandidate& candidate_value,
    const std::vector<ZeroSisFoundValueSharedPlot>& plots) {
    ZeroSisFoundValueInput input{};
    copy_common_to_dense(c, input);
    input.center_area = candidate_value.center_area;
    input.center_can_found_visible = candidate_value.center_can_found_visible;
    input.center_can_found_full = candidate_value.center_can_found_full;
    input.center_has_unique_luxury = candidate_value.center_has_unique_luxury;
    input.center_has_resource_for_team = candidate_value.center_has_resource_for_team;
    input.center_is_river = candidate_value.center_is_river;
    input.center_is_coastal = candidate_value.center_is_coastal;
    for (std::size_t offset = 0; offset < ZEROSIS_FOUND_VALUE_TILE_COUNT; ++offset) {
        const auto& slot = candidate_value.slots[offset];
        if (slot.map_plot_index == ZEROSIS_FOUND_VALUE_SHARED_MISSING_PLOT) continue;
        input.tiles[offset] = plots[slot.map_plot_index].tile;
        input.tiles[offset].distance = slot.distance;
        input.tiles[offset].strategic_value = plots[slot.map_plot_index].strategic_by_distance[slot.distance];
    }
    return input;
}

bool same_results(const std::vector<ZeroSisFoundValueResult>& a,
                  const std::vector<ZeroSisFoundValueResult>& b) {
    return a.size() == b.size() && std::memcmp(a.data(), b.data(), a.size() * sizeof(a[0])) == 0;
}

bool check_ordered_dense_differential() {
    auto c = common();
    std::vector<ZeroSisFoundValueSharedPlot> plots;
    for (std::uint32_t i = 0; i < 96; ++i) plots.push_back(fact(i));
    std::vector<ZeroSisFoundValueSharedCandidate> candidates;
    for (std::uint32_t i = 0; i < 48; ++i) candidates.push_back(candidate(i, i + 48));

    std::array<std::vector<ZeroSisFoundValueResult>, 3> outputs;
    std::array<std::uint64_t, 3> batch_ids{};
    const std::uint32_t worker_counts[] = {1, 2, 4};
    for (std::size_t mode = 0; mode < 3; ++mode) {
        outputs[mode].resize(candidates.size());
        ZeroSisFoundValueMetrics metrics{};
        auto cfg = config(worker_counts[mode]);
        const auto status = ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(),
            static_cast<std::uint32_t>(plots.size()), candidates.data(),
            static_cast<std::uint32_t>(candidates.size()), &cfg, outputs[mode].data(), &metrics);
        if (status != ZEROSIS_FOUND_VALUE_OK || metrics.jobs_total != candidates.size() ||
            metrics.jobs_started != candidates.size() || metrics.jobs_completed != candidates.size() ||
            metrics.workers_started == 0 || metrics.workers_started > worker_counts[mode] ||
            metrics.worker_threads_used == 0 ||
            metrics.worker_threads_used > metrics.workers_started ||
            metrics.maximum_overlapping_jobs == 0 ||
            metrics.maximum_overlapping_jobs > metrics.worker_threads_used) return false;
        batch_ids[mode] = ZeroSisFoundValueSharedLastBatchId();
        if (batch_ids[mode] == 0 || (mode != 0 && batch_ids[mode] <= batch_ids[mode - 1])) return false;
        std::uint32_t job_sum = 0;
        for (std::uint32_t i = 0; i < metrics.worker_threads_used; ++i) {
            if (metrics.worker_thread_ids[i] == 0 || metrics.worker_job_counts[i] == 0 ||
                metrics.worker_thread_ids[i] == cfg.owner_thread_id) return false;
            job_sum += metrics.worker_job_counts[i];
            for (std::uint32_t j = 0; j < i; ++j)
                if (metrics.worker_thread_ids[i] == metrics.worker_thread_ids[j]) return false;
        }
        if (job_sum != candidates.size()) return false;
        ++checks;
    }
    if (!same_results(outputs[0], outputs[1]) || !same_results(outputs[0], outputs[2])) return false;

    std::vector<ZeroSisFoundValueInput> dense(candidates.size());
    std::vector<ZeroSisFoundValueResult> expected(candidates.size());
    for (std::size_t i = 0; i < candidates.size(); ++i)
        dense[i] = dense_reference(c, candidates[i], plots);
    ZeroSisFoundValueMetrics dense_metrics{};
    auto cfg = config(2);
    if (ZeroSisFoundValueEvaluateBatch(dense.data(), static_cast<std::uint32_t>(dense.size()),
            &cfg, expected.data(), &dense_metrics) != ZEROSIS_FOUND_VALUE_OK ||
        !same_results(outputs[0], expected)) return false;
    std::uint64_t other_thread_batch_id = UINT64_MAX;
    std::thread other_thread([&other_thread_batch_id]() {
        other_thread_batch_id = ZeroSisFoundValueSharedLastBatchId();
    });
    other_thread.join();
    if (other_thread_batch_id != 0 || ZeroSisFoundValueSharedLastBatchId() != batch_ids[2]) return false;
    ++checks;
    checks += static_cast<std::uint32_t>(candidates.size());
    return true;
}

bool check_layout_and_center_override() {
    // The header static_asserts guard every C layout size/offset at compile time.
    auto c = common();
    std::vector<ZeroSisFoundValueSharedPlot> plots{fact(0), fact(1)};
    auto candidate_value = candidate(0, 1);
    ZeroSisFoundValueResult shared_result{}, dense_result{};
    ZeroSisFoundValueMetrics metrics{};
    auto cfg = config(1);
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, &candidate_value, 1,
            &cfg, &shared_result, &metrics) != ZEROSIS_FOUND_VALUE_OK) return false;
    const auto dense = dense_reference(c, candidate_value, plots);
    if (ZeroSisFoundValueEvaluateBatch(&dense, 1, &cfg, &dense_result, &metrics) !=
            ZEROSIS_FOUND_VALUE_OK || std::memcmp(&shared_result, &dense_result, sizeof(dense_result)) != 0)
        return false;
    candidate_value.center_can_found_full = 0;
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, &candidate_value, 1,
            &cfg, &shared_result, &metrics) != ZEROSIS_FOUND_VALUE_OK || shared_result.score != 0) return false;
    ++checks;
    return true;
}

bool check_prelaunch_validation_and_failure_atomicity() {
    auto c = common();
    std::vector<ZeroSisFoundValueSharedPlot> plots{fact(0), fact(1)};
    std::array<ZeroSisFoundValueSharedCandidate, 2> candidates{{candidate(0, 1), candidate(1, 0)}};
    auto cfg = config(4);
    std::array<ZeroSisFoundValueResult, 2> output{{{12345, 91}, {-6789, 92}}};
    const auto original = output;
    ZeroSisFoundValueMetrics metrics{};

    candidates[1].slots[kCenterOffset].map_plot_index = 99;
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, candidates.data(), 2,
            &cfg, output.data(), &metrics) != ZEROSIS_FOUND_VALUE_INVALID_SNAPSHOT ||
        !same_results(std::vector<ZeroSisFoundValueResult>(output.begin(), output.end()),
                      std::vector<ZeroSisFoundValueResult>(original.begin(), original.end())) ||
        metrics.jobs_started != 0 || metrics.workers_started != 0 ||
        ZeroSisFoundValueSharedLastBatchId() != 0) return false;
    ++checks;

    candidates[1] = candidate(1, 0);
    candidates[1].slots[0].map_plot_index = ZEROSIS_FOUND_VALUE_SHARED_MISSING_PLOT;
    candidates[1].slots[0].distance = 1;
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, candidates.data(), 2,
            &cfg, output.data(), &metrics) != ZEROSIS_FOUND_VALUE_INVALID_SNAPSHOT ||
        std::memcmp(output.data(), original.data(), sizeof(output)) != 0 || metrics.jobs_started != 0 ||
        ZeroSisFoundValueSharedLastBatchId() != 0) return false;
    ++checks;

    candidates[1] = candidate(1, 0);
    plots[1].strategic_by_distance[6] = 9;
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, candidates.data(), 2,
            &cfg, output.data(), &metrics) != ZEROSIS_FOUND_VALUE_INVALID_SNAPSHOT ||
        std::memcmp(output.data(), original.data(), sizeof(output)) != 0 || metrics.jobs_started != 0) return false;
    ++checks;

    plots[1].strategic_by_distance[6] = 0;
    plots[1].tile.food_value = (std::numeric_limits<std::int32_t>::max)();
    c.settler_food_multiplier = 2;
    c.ring_modifier[1] = 2;
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, candidates.data(), 2,
            &cfg, output.data(), &metrics) != ZEROSIS_FOUND_VALUE_OVERFLOW ||
        std::memcmp(output.data(), original.data(), sizeof(output)) != 0 ||
        metrics.jobs_started == 0 || metrics.jobs_completed == 0) return false;
    if (ZeroSisFoundValueSharedLastBatchId() != 0) return false;
    ++checks;
    return true;
}

bool check_invalid_ranges_and_empty_batch() {
    auto c = common();
    auto cfg = config(1);
    ZeroSisFoundValueMetrics metrics{};
    ZeroSisFoundValueResult result{654321, 77};
    const auto before = result;
    auto candidate_value = candidate(0, 1);
    std::vector<ZeroSisFoundValueSharedPlot> plots{fact(0), fact(1)};

    cfg.owner_thread_id = cfg.owner_thread_id == UINT32_MAX ? 1u : cfg.owner_thread_id + 1u;
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, &candidate_value, 1,
            &cfg, &result, &metrics) != ZEROSIS_FOUND_VALUE_WRONG_OWNER_THREAD ||
        std::memcmp(&result, &before, sizeof(result)) != 0) return false;
    ++checks;
    cfg = config(3);
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, &candidate_value, 1,
            &cfg, &result, &metrics) != ZEROSIS_FOUND_VALUE_INVALID_INPUT ||
        std::memcmp(&result, &before, sizeof(result)) != 0) return false;
    ++checks;

    c.center_is_river = 1;
    cfg = config(1);
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, &candidate_value, 1,
            &cfg, &result, &metrics) != ZEROSIS_FOUND_VALUE_INVALID_INPUT ||
        std::memcmp(&result, &before, sizeof(result)) != 0) return false;
    ++checks;
    c = common();

    c.path = 99;
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, &candidate_value, 1,
            &cfg, &result, &metrics) != ZEROSIS_FOUND_VALUE_UNSUPPORTED_PATH ||
        std::memcmp(&result, &before, sizeof(result)) != 0) return false;
    ++checks;
    c = common();
    c.abi_version = ZEROSIS_FOUND_VALUE_SHARED_ABI_VERSION + 1u;
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, &candidate_value, 1,
            &cfg, &result, &metrics) != ZEROSIS_FOUND_VALUE_INVALID_INPUT ||
        std::memcmp(&result, &before, sizeof(result)) != 0) return false;
    ++checks;
    c = common();
    c.center_area = 2;
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2, &candidate_value, 1,
            &cfg, &result, &metrics) != ZEROSIS_FOUND_VALUE_INVALID_INPUT ||
        std::memcmp(&result, &before, sizeof(result)) != 0) return false;
    ++checks;
    c = common();

    alignas(8) std::array<unsigned char, sizeof(ZeroSisFoundValueSharedCandidate)> overlap{};
    std::memcpy(overlap.data(), &candidate_value, sizeof(candidate_value));
    const auto overlap_before = overlap;
    auto* aliased_output = reinterpret_cast<ZeroSisFoundValueResult*>(overlap.data());
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, plots.data(), 2,
            reinterpret_cast<const ZeroSisFoundValueSharedCandidate*>(overlap.data()), 1,
            &cfg, aliased_output, &metrics) != ZEROSIS_FOUND_VALUE_INVALID_INPUT || overlap != overlap_before)
        return false;
    ++checks;

    if (ZeroSisFoundValueEvaluateSharedBatch(&c, nullptr, 0, nullptr, 0,
            &cfg, nullptr, &metrics) != ZEROSIS_FOUND_VALUE_OK || metrics.jobs_total != 0 ||
        metrics.jobs_started != 0 || metrics.workers_started != 0 ||
        ZeroSisFoundValueSharedLastBatchId() != 0) return false;
    ++checks;

    const auto* wrapped = reinterpret_cast<const ZeroSisFoundValueSharedPlot*>(
        (std::numeric_limits<std::uintptr_t>::max)() - 7u);
    if (ZeroSisFoundValueEvaluateSharedBatch(&c, wrapped, 1, &candidate_value, 1,
            &cfg, &result, &metrics) != ZEROSIS_FOUND_VALUE_INVALID_INPUT ||
        std::memcmp(&result, &before, sizeof(result)) != 0) return false;
    ++checks;
    return true;
}
} // namespace

int main() {
    if (!check_layout_and_center_override()) {
        std::fprintf(stderr, "FAIL shared_layout_center_override\n"); return 1;
    }
    if (!check_ordered_dense_differential()) {
        std::fprintf(stderr, "FAIL ordered_worker_and_dense_differential\n"); return 2;
    }
    if (!check_prelaunch_validation_and_failure_atomicity()) {
        std::fprintf(stderr, "FAIL complete_prevalidation_and_atomic_results\n"); return 3;
    }
    if (!check_invalid_ranges_and_empty_batch()) {
        std::fprintf(stderr, "FAIL owner_flags_overlap_and_empty_batch\n"); return 4;
    }
    std::printf("FOUND_VALUE_SHARED_BRIDGE_PASS checks=%u GAMECORE_LOADED=false TRACE_CAPTURED=false\n", checks);
    return 0;
}
