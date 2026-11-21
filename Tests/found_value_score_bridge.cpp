#include "FoundValueScoreBridge.h"

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <Windows.h>

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>

namespace {
constexpr std::size_t kCenter = 7u * 15u + 7u;
std::uint32_t checks = 0;

ZeroSisFoundValueInput base_input() {
    ZeroSisFoundValueInput value{};
    value.abi_version = ZEROSIS_FOUND_VALUE_ABI_VERSION;
    value.config_version = ZEROSIS_FOUND_VALUE_CONFIG_VERSION;
    value.path = ZEROSIS_FOUND_VALUE_PATH_SETTLER_NO_YIELD_NO_COAST_ONLY;
    value.valid = value.has_player = value.center_present = value.capital_present = 1;
    value.center_can_found_visible = value.center_can_found_full = 1;
    value.center_area = value.capital_area = 1;
    value.min_city_range = 3;
    value.min_water_size_for_ocean = 10;
    value.major_civ_count = 18;
    const std::int32_t rings[8] = {1, 6, 3, 2, 1, 1, 0, 0};
    std::memcpy(value.ring_modifier, rings, sizeof(rings));
    value.settler_food_multiplier = 15;
    value.settler_happiness_multiplier = 6;
    value.settler_production_multiplier = 3;
    value.settler_gold_multiplier = 2;
    value.settler_science_multiplier = 1;
    value.settler_faith_multiplier = 1;
    value.faith_flavor_multiplier = 1;
    value.settler_resource_multiplier = 1;
    value.settler_strategic_multiplier = 1;
    value.build_on_resource_percent = -50;
    value.build_on_river_percent = 15;
    value.build_on_coast_percent = 40;
    value.brazil_multiplier = 1000;
    value.spain_multiplier = 55000;
    value.morocco_multiplier = 1000;
    value.netherlands_multiplier = 2000;
    value.inca_multiplier = 500;
    value.tiles[kCenter].present = 1;
    value.tiles[kCenter].distance = 0;
    value.tiles[kCenter].owner = ZEROSIS_FOUND_VALUE_OWNER_UNOWNED;
    return value;
}

void set_tile(ZeroSisFoundValueInput& value, int dx, int dy, int distance,
              std::int32_t food, std::int32_t faith = 0) {
    const auto index = static_cast<std::size_t>((dx + 7) * 15 + dy + 7);
    auto& tile = value.tiles[index];
    tile.present = 1;
    tile.distance = distance;
    tile.owner = ZEROSIS_FOUND_VALUE_OWNER_UNOWNED;
    tile.food_value = food;
    tile.faith_value = faith;
}

ZeroSisFoundValueConfig config(std::uint32_t workers) {
    ZeroSisFoundValueConfig value{};
    value.abi_version = ZEROSIS_FOUND_VALUE_ABI_VERSION;
    value.config_version = ZEROSIS_FOUND_VALUE_CONFIG_VERSION;
    value.requested_workers = workers;
    value.owner_thread_id = static_cast<std::uint32_t>(::GetCurrentThreadId());
    return value;
}

bool check_metrics(const ZeroSisFoundValueMetrics& metrics, std::uint32_t count,
                   std::uint32_t workers) {
    if (metrics.abi_version != ZEROSIS_FOUND_VALUE_ABI_VERSION ||
        metrics.config_version != ZEROSIS_FOUND_VALUE_CONFIG_VERSION ||
        metrics.status != ZEROSIS_FOUND_VALUE_OK || metrics.jobs_total != count ||
        metrics.jobs_started != count || metrics.jobs_completed != count ||
        metrics.workers_started == 0 || metrics.workers_started > workers ||
        metrics.worker_threads_used == 0 || metrics.worker_threads_used > metrics.workers_started ||
        metrics.maximum_overlapping_jobs == 0 || metrics.maximum_overlapping_jobs > metrics.worker_threads_used ||
        metrics.owner_thread_id == 0) return false;
    std::uint32_t sum = 0;
    for (std::uint32_t index = 0; index < metrics.worker_threads_used; ++index) {
        if (metrics.worker_thread_ids[index] == 0 || metrics.worker_job_counts[index] == 0) return false;
        sum += metrics.worker_job_counts[index];
        for (std::uint32_t prior = 0; prior < index; ++prior)
            if (metrics.worker_thread_ids[index] == metrics.worker_thread_ids[prior]) return false;
    }
    return sum == count;
}

bool unchanged(const ZeroSisFoundValueResult* results, std::uint32_t count,
               const ZeroSisFoundValueResult* before) {
    return std::memcmp(results, before, static_cast<std::size_t>(count) * sizeof(*results)) == 0;
}

bool check_batch_determinism() {
    std::array<ZeroSisFoundValueInput, 48> inputs{};
    for (std::size_t index = 0; index < inputs.size(); ++index) {
        inputs[index] = base_input();
        set_tile(inputs[index], 1, 0, 1, static_cast<std::int32_t>(index % 9 + 1),
                 static_cast<std::int32_t>(index % 4));
        inputs[index].human_player = static_cast<std::uint32_t>(index & 1u);
        inputs[index].faith_from_unimproved_forest = static_cast<std::uint32_t>((index % 3u) == 0);
        inputs[index].faith_flavor_multiplier = 17;
        inputs[index].settler_faith_multiplier = 2;
    }
    std::array<ZeroSisFoundValueResult, 48> serial{};
    std::array<ZeroSisFoundValueResult, 48> parallel{};
    ZeroSisFoundValueMetrics serial_metrics{}, parallel_metrics{};
    const auto one = config(1);
    const auto four = config(4);
    if (ZeroSisFoundValueEvaluateBatch(inputs.data(), static_cast<std::uint32_t>(inputs.size()),
        &one, serial.data(), &serial_metrics) != ZEROSIS_FOUND_VALUE_OK) return false;
    if (ZeroSisFoundValueEvaluateBatch(inputs.data(), static_cast<std::uint32_t>(inputs.size()),
        &four, parallel.data(), &parallel_metrics) != ZEROSIS_FOUND_VALUE_OK) return false;
    if (std::memcmp(serial.data(), parallel.data(), sizeof(serial)) != 0 ||
        !check_metrics(serial_metrics, static_cast<std::uint32_t>(inputs.size()), 1) ||
        !check_metrics(parallel_metrics, static_cast<std::uint32_t>(inputs.size()), 4)) return false;
    ++checks;
    return true;
}

bool check_faith_flavor_is_distinct() {
    auto input = base_input();
    input.human_player = 1;
    input.faith_from_unimproved_forest = 1;
    input.settler_faith_multiplier = 2;
    input.faith_flavor_multiplier = 17;
    set_tile(input, 1, 0, 1, 0, 0);
    auto& forest = input.tiles[static_cast<std::size_t>((1 + 7) * 15 + 7)];
    forest.forest = 1;
    forest.unimproved = 1;
    ZeroSisFoundValueResult first{}, second{};
    ZeroSisFoundValueMetrics metrics{};
    auto owner = config(1);
    if (ZeroSisFoundValueEvaluateBatch(&input, 1, &owner, &first, &metrics) != ZEROSIS_FOUND_VALUE_OK)
        return false;
    input.faith_flavor_multiplier = 23;
    if (ZeroSisFoundValueEvaluateBatch(&input, 1, &owner, &second, &metrics) != ZEROSIS_FOUND_VALUE_OK ||
        second.score - first.score != 6000) {
        std::fprintf(stderr, "FAITH_FLAVOR_VALUES first=%d second=%d delta=%d\n",
                     first.score, second.score, second.score - first.score);
        return false;
    }
    ++checks;
    return true;
}

bool check_failure_atomicity() {
    const auto owner = config(2);
    std::array<ZeroSisFoundValueInput, 2> inputs{{base_input(), base_input()}};
    std::array<ZeroSisFoundValueResult, 2> outputs{{{12345, 91}, {-6789, 92}}};
    auto before = outputs;
    ZeroSisFoundValueMetrics metrics{};
    inputs[1].valid = 2;
    if (ZeroSisFoundValueEvaluateBatch(inputs.data(), 2, &owner, outputs.data(), &metrics) !=
        ZEROSIS_FOUND_VALUE_INVALID_INPUT || !unchanged(outputs.data(), 2, before.data())) return false;
    ++checks;

    inputs[1] = base_input();
    inputs[1].path = 99;
    if (ZeroSisFoundValueEvaluateBatch(inputs.data(), 2, &owner, outputs.data(), &metrics) !=
        ZEROSIS_FOUND_VALUE_UNSUPPORTED_PATH || !unchanged(outputs.data(), 2, before.data())) return false;
    ++checks;

    inputs[1] = base_input();
    inputs[1].settler_food_multiplier = (std::numeric_limits<std::int32_t>::max)();
    inputs[1].ring_modifier[1] = 2;
    set_tile(inputs[1], 1, 0, 1, (std::numeric_limits<std::int32_t>::max)());
    if (ZeroSisFoundValueEvaluateBatch(inputs.data(), 2, &owner, outputs.data(), &metrics) !=
        ZEROSIS_FOUND_VALUE_OVERFLOW || !unchanged(outputs.data(), 2, before.data())) return false;
    ++checks;
    return true;
}

bool check_invalid_contracts() {
    auto input = base_input();
    ZeroSisFoundValueResult output{54321, 77};
    const auto before = output;
    ZeroSisFoundValueMetrics metrics{};
    auto owner = config(1);
    owner.owner_thread_id = owner.owner_thread_id == UINT32_MAX ? 1u : owner.owner_thread_id + 1u;
    if (ZeroSisFoundValueEvaluateBatch(&input, 1, &owner, &output, &metrics) !=
        ZEROSIS_FOUND_VALUE_WRONG_OWNER_THREAD || std::memcmp(&output, &before, sizeof(output)) != 0) return false;
    ++checks;

    owner = config(3);
    if (ZeroSisFoundValueEvaluateBatch(&input, 1, &owner, &output, &metrics) !=
        ZEROSIS_FOUND_VALUE_INVALID_INPUT || std::memcmp(&output, &before, sizeof(output)) != 0) return false;
    ++checks;

    owner = config(1);
    input.tiles[kCenter].owner = 99;
    if (ZeroSisFoundValueEvaluateBatch(&input, 1, &owner, &output, &metrics) !=
        ZEROSIS_FOUND_VALUE_INVALID_INPUT || std::memcmp(&output, &before, sizeof(output)) != 0) return false;
    ++checks;

    input = base_input();
    input.tiles[0].forest = 2;
    if (ZeroSisFoundValueEvaluateBatch(&input, 1, &owner, &output, &metrics) !=
        ZEROSIS_FOUND_VALUE_INVALID_INPUT || std::memcmp(&output, &before, sizeof(output)) != 0) return false;
    ++checks;

    // The bridge rejects overlapping input/output ranges before touching either.
    alignas(8) std::array<unsigned char, sizeof(ZeroSisFoundValueInput)> overlap{};
    std::memcpy(overlap.data(), &input, sizeof(input));
    const auto overlap_before = overlap;
    const auto overlap_status = ZeroSisFoundValueEvaluateBatch(
        reinterpret_cast<const ZeroSisFoundValueInput*>(overlap.data()), 1, &owner,
        reinterpret_cast<ZeroSisFoundValueResult*>(overlap.data()), &metrics);
    if (overlap_status != ZEROSIS_FOUND_VALUE_INVALID_INPUT || overlap != overlap_before) return false;
    ++checks;

    if (ZeroSisFoundValueEvaluateBatch(nullptr, 0, &owner, nullptr, &metrics) != ZEROSIS_FOUND_VALUE_OK ||
        metrics.jobs_total != 0 || metrics.jobs_started != 0 || metrics.workers_started != 0) return false;
    ++checks;
    return true;
}
} // namespace

int main() {
    if (!check_batch_determinism()) {
        std::fprintf(stderr, "FAIL deterministic_owned_batch\n");
        return 1;
    }
    if (!check_faith_flavor_is_distinct()) {
        std::fprintf(stderr, "FAIL distinct_faith_flavor_mapping\n");
        return 2;
    }
    if (!check_failure_atomicity()) {
        std::fprintf(stderr, "FAIL all_or_nothing_failure_paths\n");
        return 3;
    }
    if (!check_invalid_contracts()) {
        std::fprintf(stderr, "FAIL input_owner_overlap_or_empty_contract\n");
        return 4;
    }
    std::printf("FOUND_VALUE_SCORE_BRIDGE_PASS checks=%u GAMECORE_LOADED=false\n", checks);
    return 0;
}
