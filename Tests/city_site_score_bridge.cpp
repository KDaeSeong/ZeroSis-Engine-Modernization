#include "CitySiteScoreBridge.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <set>
#include <stdexcept>
#include <vector>

namespace {
int checks = 0;
void Require(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
ZeroSisCitySiteInput EmptyInput() {
    ZeroSisCitySiteInput input{};
    input.abi_version = ZEROSIS_CITY_SITE_ABI_VERSION;
    input.config_version = ZEROSIS_CITY_SITE_CONFIG_VERSION;
    return input;
}
ZeroSisCitySiteResult Sentinel(std::int32_t base) {
    ZeroSisCitySiteResult result{};
    for (std::size_t i = 0; i < 4; ++i) result.values[i] = base + static_cast<std::int32_t>(i);
    return result;
}
void RequireEqual(const ZeroSisCitySiteResult& actual,
                  const std::array<std::int32_t, 4>& expected, const char* message) {
    for (std::size_t i = 0; i < 4; ++i) Require(actual.values[i] == expected[i], message);
}
void RequireUnchanged(const std::vector<ZeroSisCitySiteResult>& values, std::int32_t base) {
    for (std::size_t i = 0; i < values.size(); ++i)
        for (std::size_t j = 0; j < 4; ++j)
            Require(values[i].values[j] == base + static_cast<std::int32_t>(i * 10 + j),
                    "Failed batch exposed a partial result");
}
std::array<ZeroSisCitySiteInput, 4> ValidInputs() {
    std::array<ZeroSisCitySiteInput, 4> inputs{{EmptyInput(), EmptyInput(), EmptyInput(), EmptyInput()}};
    auto& one = inputs[0];
    one.tile_count = 2;
    one.ring_weights[0] = 3;
    // The home plot is ignored even when its arithmetic would overflow.
    one.cells[0] = {1, {INT32_MAX, INT32_MAX, INT32_MAX, INT32_MAX}, 1, 0, 1, 0};
    one.cells[1] = {1, {1, 2, 3, 4}, 1, 0, 1, 0};
    auto& varied = inputs[1];
    varied.tile_count = 6;
    varied.ring_weights[0] = 3;
    varied.ring_weights[1] = -2;
    varied.ring_weights[2] = 7;
    varied.cells[1] = one.cells[1];
    varied.cells[2] = {2, {100, 200, 300, 400}, 1, 1, 1, 0};
    varied.cells[3] = {3, {INT32_MAX, INT32_MAX, INT32_MAX, INT32_MAX}, 0, 0, 1, 0};
    varied.cells[4] = {2, {5, -1, 0, 2}, 1, 0, 0, 0};
    // Original helpers retain the prior multiplier outside rings 1, 2, 3.
    varied.cells[5] = {4, {2, 2, 2, 1}, 1, 0, 1, 0};
    auto& full = inputs[3];
    full.tile_count = ZEROSIS_CITY_SITE_MAX_TILES;
    full.ring_weights[0] = 1;
    for (std::size_t index = 1; index < ZEROSIS_CITY_SITE_MAX_TILES; ++index)
        full.cells[index] = {1, {1, 2, 3, 4}, 1, 0, static_cast<std::uint8_t>(index % 3 == 0), 0};
    return inputs;
}
void CheckSuccessfulMetrics(const ZeroSisCitySiteMetrics& metrics, std::uint32_t count,
                            std::uint32_t workers) {
    Require(metrics.abi_version == ZEROSIS_CITY_SITE_ABI_VERSION &&
            metrics.config_version == ZEROSIS_CITY_SITE_CONFIG_VERSION,
            "Metrics ABI/configuration differs");
    Require(metrics.status == ZEROSIS_CITY_SITE_OK && metrics.requested_workers == workers,
            "Metrics status/request differs");
    Require(metrics.jobs_total == count && metrics.jobs_started == count && metrics.jobs_completed == count,
            "Complete batch accounting differs");
    Require(metrics.workers_started == (count < workers ? count : workers),
            "Created thread accounting differs");
    if (!count) {
        Require(metrics.worker_threads_used == 0 && metrics.maximum_overlapping_jobs == 0,
                "Empty batch reports scoring invocations");
    } else {
        Require(metrics.maximum_overlapping_jobs >= 1 &&
                metrics.maximum_overlapping_jobs <= metrics.worker_threads_used &&
                metrics.worker_threads_used <= metrics.workers_started,
                "Invocation counts are inconsistent");
    }
    std::set<std::uint32_t> ids;
    std::uint32_t jobs = 0;
    for (std::uint32_t index = 0; index < 4; ++index) {
        if (index < metrics.worker_threads_used) {
            Require(metrics.worker_thread_ids[index] != 0 && metrics.worker_job_counts[index] != 0,
                    "A used worker has no identity or work");
            Require(ids.insert(metrics.worker_thread_ids[index]).second, "Duplicate worker thread ID");
            jobs += metrics.worker_job_counts[index];
        } else {
            Require(metrics.worker_thread_ids[index] == 0 && metrics.worker_job_counts[index] == 0,
                    "Unused worker metrics are not zero");
        }
    }
    Require(jobs == count, "Per-thread job count does not cover the complete batch");
}
void TestValidBatches() {
    const auto inputs = ValidInputs();
    const std::array<std::array<std::int32_t, 4>, 4> expected{{
        {{3, 6, 9, 18}}, {{-11, 4, 5, -4}}, {{0, 0, 0, 0}}, {{63, 126, 189, 336}},
    }};
    for (const std::uint32_t workers : {1U, 2U, 4U}) {
        std::array<ZeroSisCitySiteResult, 4> output{};
        ZeroSisCitySiteMetrics metrics{};
        Require(ZeroSisEvaluateCitySites(inputs.data(), 4, workers, output.data(), &metrics) ==
                    ZEROSIS_CITY_SITE_OK, "Valid POD batch failed");
        for (std::size_t i = 0; i < output.size(); ++i)
            RequireEqual(output[i], expected[i], "C ABI changed the hand-calculated yield vector");
        CheckSuccessfulMetrics(metrics, 4, workers);
        // Repeated joins must leave no state or results from the preceding call.
        Require(ZeroSisEvaluateCitySites(inputs.data(), 1, workers, output.data(), &metrics) ==
                    ZEROSIS_CITY_SITE_OK, "Valid single-site repeat failed");
        RequireEqual(output[0], expected[0], "Repeated batch changed its yield vector");
        CheckSuccessfulMetrics(metrics, 1, workers);
    }
}
void TestEmptyAndArguments() {
    for (const std::uint32_t workers : {1U, 2U, 4U}) {
        ZeroSisCitySiteMetrics metrics{};
        Require(ZeroSisEvaluateCitySites(nullptr, 0, workers, nullptr, &metrics) ==
                    ZEROSIS_CITY_SITE_OK, "Empty null batch failed");
        CheckSuccessfulMetrics(metrics, 0, workers);
    }
    auto input = EmptyInput();
    auto output = Sentinel(201);
    ZeroSisCitySiteMetrics metrics{};
    for (const std::uint32_t invalid : {0U, 3U, 5U, UINT32_MAX}) {
        Require(ZeroSisEvaluateCitySites(&input, 1, invalid, &output, &metrics) ==
                    ZEROSIS_CITY_SITE_INVALID_INPUT, "Unsupported worker count was accepted");
        RequireEqual(output, {{201, 202, 203, 204}}, "Invalid worker count wrote output");
        Require(metrics.status == ZEROSIS_CITY_SITE_INVALID_INPUT && metrics.workers_started == 0,
                "Invalid worker count launched a batch");
    }
    Require(ZeroSisEvaluateCitySites(nullptr, 1, 1, &output, &metrics) ==
                ZEROSIS_CITY_SITE_INVALID_INPUT, "Nonempty null input was accepted");
    Require(ZeroSisEvaluateCitySites(&input, 1, 1, nullptr, &metrics) ==
                ZEROSIS_CITY_SITE_INVALID_INPUT, "Nonempty null output was accepted");
    Require(ZeroSisEvaluateCitySites(&input, 1, 1, &output, nullptr) ==
                ZEROSIS_CITY_SITE_INVALID_INPUT, "Null metrics was accepted");
    RequireEqual(output, {{201, 202, 203, 204}}, "Invalid pointers wrote output");
}
template<class Mutate> void CheckLateInvalid(Mutate mutate) {
    const auto valid = ValidInputs();
    std::array<ZeroSisCitySiteInput, 3> inputs{{valid[0], valid[1], valid[3]}};
    mutate(inputs.back());
    std::vector<ZeroSisCitySiteResult> output;
    for (std::int32_t index = 0; index < 3; ++index) output.push_back(Sentinel(301 + index * 10));
    ZeroSisCitySiteMetrics metrics{};
    Require(ZeroSisEvaluateCitySites(inputs.data(), 3, 2, output.data(), &metrics) ==
                ZEROSIS_CITY_SITE_INVALID_INPUT, "Malformed late input was accepted");
    RequireUnchanged(output, 301);
    Require(metrics.status == ZEROSIS_CITY_SITE_INVALID_INPUT && metrics.jobs_started == 0 &&
            metrics.workers_started == 0, "Invalid input launched scoring jobs");
}
void TestLateMalformedInputs() {
    CheckLateInvalid([](auto& input) { input.abi_version = 2; });
    CheckLateInvalid([](auto& input) { input.config_version = 2; });
    CheckLateInvalid([](auto& input) { input.reserved = 1; });
    CheckLateInvalid([](auto& input) { input.tile_count = ZEROSIS_CITY_SITE_MAX_TILES + 1; });
    CheckLateInvalid([](auto& input) { input.cells[63].present = 2; });
    CheckLateInvalid([](auto& input) { input.cells[63].foreign_owned = 2; });
    CheckLateInvalid([](auto& input) { input.cells[63].science_clear = 2; });
    CheckLateInvalid([](auto& input) { input.cells[63].reserved = 1; });
}
template<class Mutate> void CheckLateOverflow(Mutate mutate) {
    const auto valid = ValidInputs();
    std::array<ZeroSisCitySiteInput, 3> inputs{{valid[0], valid[1], EmptyInput()}};
    auto& overflow = inputs.back();
    overflow.tile_count = 3;
    overflow.ring_weights[0] = 1;
    overflow.cells[1].present = overflow.cells[2].present = 1;
    overflow.cells[1].ring_distance = overflow.cells[2].ring_distance = 1;
    mutate(overflow);
    for (const std::uint32_t workers : {1U, 2U, 4U}) {
        std::vector<ZeroSisCitySiteResult> output;
        for (std::int32_t index = 0; index < 3; ++index) output.push_back(Sentinel(401 + index * 10));
        ZeroSisCitySiteMetrics metrics{};
        Require(ZeroSisEvaluateCitySites(inputs.data(), 3, workers, output.data(), &metrics) ==
                    ZEROSIS_CITY_SITE_OVERFLOW, "Overflowing late input was accepted");
        RequireUnchanged(output, 401);
        Require(metrics.status == ZEROSIS_CITY_SITE_OVERFLOW && metrics.jobs_completed == 3,
                "Overflow status or all-job staging differs");
    }
}
void TestLateArithmeticOverflow() {
    CheckLateOverflow([](auto& input) { input.ring_weights[0] = 2; input.cells[1].yields[1] = INT32_MAX; });
    CheckLateOverflow([](auto& input) {
        input.cells[1].yields[0] = INT32_MAX; input.cells[1].yields[3] = 1;
    });
    CheckLateOverflow([](auto& input) {
        input.cells[1].yields[2] = INT32_MAX; input.cells[2].yields[2] = 1;
    });
    CheckLateOverflow([](auto& input) {
        input.ring_weights[0] = INT32_MAX;
        input.cells[1].science_clear = input.cells[2].science_clear = 1;
    });
    CheckLateOverflow([](auto& input) {
        input.cells[1].yields[0] = INT32_MAX;
        input.cells[2].science_clear = 1;
    });
}
} // namespace

int main() {
    try {
        TestValidBatches();
        TestEmptyAndArguments();
        TestLateMalformedInputs();
        TestLateArithmeticOverflow();
        std::printf("CITY_SITE_SCORE_BRIDGE_BOUNDARY_PASS checks=%d GAMECORE_LOADED=false\n", checks);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "CITY_SITE_SCORE_BRIDGE_BOUNDARY_FAIL checks=%d error=%s\n", checks, error.what());
        return 1;
    }
}
