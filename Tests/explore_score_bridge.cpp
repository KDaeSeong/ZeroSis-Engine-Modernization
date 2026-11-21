#include "ExploreScoreBridge.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <vector>

namespace {
int checks = 0;

void Require(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}

ZeroSisExploreScoreInput MakeInput(std::uint8_t domain = 0) {
    ZeroSisExploreScoreInput input{};
    input.domain = domain;
    constexpr std::array<std::array<std::int8_t, 2>, 9> offsets{{
        {{-1, -1}}, {{-1, 0}}, {{-1, 1}}, {{0, -1}}, {{0, 0}},
        {{0, 1}}, {{1, -1}}, {{1, 0}}, {{1, 1}},
    }};
    for (std::size_t i = 0; i < offsets.size(); ++i) {
        input.plots[i].offset_x = offsets[i][0];
        input.plots[i].offset_y = offsets[i][1];
    }
    return input;
}

// Source-shaped reference over the public C POD, independent of the bridge copy.
std::int32_t ReferenceScore(const ZeroSisExploreScoreInput& input) {
    std::int32_t result = 0;
    for (const auto& plot : input.plots) {
        if (!plot.exists || plot.is_center_plot || plot.revealed) continue;
        if (plot.adjacent_revealed && plot.distance_from_origin > 1) {
            bool visible_edge = false;
            for (const auto& adjacent : plot.adjacent_plots) {
                if (adjacent.exists && adjacent.revealed && adjacent.distance_from_origin <= 1 &&
                    plot.origin_can_see_candidate) {
                    visible_edge = true;
                    break;
                }
            }
            if (!visible_edge) continue;
        }
        if (!plot.adjacent_revealed) {
            result += 100;
        } else if (input.domain == 1) {
            if (plot.water || (plot.has_feature && plot.feature_impassable)) result += 10;
            else if (plot.mountain || plot.hills ||
                     (plot.has_feature && plot.feature_see_through_change_positive)) result += 100;
            else result += 200;
        } else if (input.domain == 0) {
            if (plot.mountain || plot.water) result += 10;
            else if (plot.hills) result += 200;
            else result += 100;
        }
        result += 1 - plot.distance_from_origin;
    }
    return result;
}

void RequireSentinels(const std::array<std::int32_t, 4>& scores, std::int32_t base,
                      const char* message) {
    for (std::size_t i = 0; i < scores.size(); ++i)
        Require(scores[i] == base + static_cast<std::int32_t>(i), message);
}

void TestInvalidDistance(std::int32_t distance, bool neighbor) {
    auto input = MakeInput();
    if (neighbor) {
        input.plots[1].exists = 1;
        input.plots[1].adjacent_revealed = 1;
        input.plots[1].distance_from_origin = 2;
        input.plots[1].adjacent_plots[0] = {1, 1, distance};
    } else {
        input.plots[1].exists = 1;
        input.plots[1].distance_from_origin = distance;
    }
    std::array<std::int32_t, 1> score{{0x13572468}};
    ZeroSisExploreBatchMetrics metrics{};
    const auto status = ZeroSisEvaluateExploreScores(&input, 1, 1, score.data(), &metrics);
    Require(status == 1, "extreme distance was accepted");
    Require(score[0] == 0x13572468, "invalid distance exposed an output score");
}

void TestInvalidInputsAreAtomic() {
    for (const auto distance : {std::numeric_limits<std::int32_t>::min(),
                                std::numeric_limits<std::int32_t>::max()}) {
        TestInvalidDistance(distance, false);
        TestInvalidDistance(distance, true);
    }

    std::array<ZeroSisExploreScoreInput, 3> inputs{{MakeInput(), MakeInput(1), MakeInput(2)}};
    inputs[2].plots[8].offset_x = 0;
    std::array<std::int32_t, 3> scores{{101, 102, 103}};
    ZeroSisExploreBatchMetrics metrics{};
    Require(ZeroSisEvaluateExploreScores(inputs.data(), 3, 2, scores.data(), &metrics) == 1,
            "malformed final offset was accepted");
    RequireSentinels({scores[0], scores[1], scores[2], 104}, 101,
                     "late invalid input exposed earlier scores");

    inputs[2] = MakeInput();
    inputs[2].domain = 3;
    scores = {{101, 102, 103}};
    Require(ZeroSisEvaluateExploreScores(inputs.data(), 3, 2, scores.data(), &metrics) == 1,
            "malformed final domain was accepted");
    RequireSentinels({scores[0], scores[1], scores[2], 104}, 101,
                     "late invalid domain exposed earlier scores");
}

void TestEmptyAndInvalidArguments() {
    ZeroSisExploreBatchMetrics metrics{};
    Require(ZeroSisEvaluateExploreScores(nullptr, 0, 1, nullptr, &metrics) == 0,
            "empty null batch was rejected");
    Require(metrics.workers_started == 0 && metrics.jobs_started == 0 && metrics.jobs_completed == 0 &&
            metrics.worker_threads_used == 0 && metrics.maximum_overlapping_jobs == 0,
            "empty null batch reported worker activity");
    Require(ZeroSisEvaluateExploreScores(nullptr, 0, 3, nullptr, &metrics) == 1,
            "empty batch accepted an unsupported worker count");

    auto input = MakeInput();
    std::array<std::int32_t, 1> score{{0x24681357}};
    Require(ZeroSisEvaluateExploreScores(&input, 1, 3, score.data(), &metrics) == 1,
            "unsupported worker count was accepted");
    Require(score[0] == 0x24681357, "invalid worker count changed score output");
    Require(ZeroSisEvaluateExploreScores(nullptr, 1, 1, score.data(), &metrics) == 1,
            "nonempty null input was accepted");
    Require(score[0] == 0x24681357, "null input changed score output");
    Require(ZeroSisEvaluateExploreScores(&input, 1, 1, nullptr, &metrics) == 1,
            "nonempty null output was accepted");
    Require(ZeroSisEvaluateExploreScores(&input, 1, 1, score.data(), nullptr) == 1,
            "null metrics was accepted");
    Require(score[0] == 0x24681357, "null metrics changed score output");
}

std::array<ZeroSisExploreScoreInput, 4> ValidInputs() {
    std::array<ZeroSisExploreScoreInput, 4> inputs{{MakeInput(0), MakeInput(1), MakeInput(2), MakeInput(0)}};
    auto& land = inputs[0].plots[1];
    land.exists = 1; land.adjacent_revealed = 1; land.distance_from_origin = 1; land.hills = 1;
    auto& sea = inputs[1].plots[2];
    sea.exists = 1; sea.adjacent_revealed = 1; sea.distance_from_origin = 2;
    sea.origin_can_see_candidate = 1;
    sea.adjacent_plots[3] = {1, 1, 1};
    sea.has_feature = 1; sea.feature_see_through_change_positive = 1;
    auto& unsupported = inputs[2].plots[5];
    unsupported.exists = 1; unsupported.adjacent_revealed = 1; unsupported.distance_from_origin = 1;
    auto& hidden_edge = inputs[3].plots[7];
    hidden_edge.exists = 1; hidden_edge.adjacent_revealed = 1; hidden_edge.distance_from_origin = 2;
    hidden_edge.adjacent_plots[0] = {1, 1, 2};
    return inputs;
}

void TestValidWorkerCounts() {
    const auto inputs = ValidInputs();
    std::array<std::int32_t, 4> expected{};
    for (std::size_t i = 0; i < inputs.size(); ++i) expected[i] = ReferenceScore(inputs[i]);
    for (const std::uint32_t workers : {1U, 2U, 4U}) {
        std::array<std::int32_t, 4> scores{{-1, -1, -1, -1}};
        ZeroSisExploreBatchMetrics metrics{};
        Require(ZeroSisEvaluateExploreScores(inputs.data(), static_cast<std::uint32_t>(inputs.size()),
                                             workers, scores.data(), &metrics) == 0,
                "valid batch failed");
        Require(scores == expected, "C ABI output differs from pure reference");
        Require(metrics.workers_started == workers && metrics.jobs_started == inputs.size() &&
                metrics.jobs_completed == inputs.size(), "valid batch accounting differs");
        Require(metrics.worker_threads_used >= 1 && metrics.worker_threads_used <= workers &&
                metrics.maximum_overlapping_jobs >= 1 &&
                metrics.maximum_overlapping_jobs <= metrics.worker_threads_used,
                "valid invocation metrics are inconsistent");
        for (std::uint32_t i = 0; i < metrics.worker_threads_used; ++i)
            Require(metrics.worker_ids[i] == i + 1, "worker ID assignment is not per-batch ordered");
    }
}
} // namespace

int main() {
    try {
        TestInvalidInputsAreAtomic();
        TestEmptyAndInvalidArguments();
        TestValidWorkerCounts();
        std::printf("EXPLORE_SCORE_BRIDGE_BOUNDARY_PASS checks=%d GAMECORE_LOADED=false\n", checks);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "EXPLORE_SCORE_BRIDGE_BOUNDARY_FAIL checks=%d error=%s\n", checks, error.what());
        return 1;
    }
}
