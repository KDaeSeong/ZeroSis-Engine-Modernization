#include "ExplorePlotScores.h"
#include "OrderedBatch.h"

#include <array>
#include <cstdio>
#include <stdexcept>
#include <vector>

using namespace zerosis::concurrency;

namespace {
int checks = 0;

void Require(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}

ExplorePlotScoreInput MakeInput() {
    ExplorePlotScoreInput input;
    input.domain = ExploreDomain::land;
    for (std::size_t index = 0; index < input.plots.size(); ++index) {
        input.plots[index].offset_x = kExplorePlotOffsetOrder[index][0];
        input.plots[index].offset_y = kExplorePlotOffsetOrder[index][1];
    }
    return input;
}

// Independent source-shaped oracle: explicit branch sequence and fixed
// expected scores, kept in the test translation unit.
std::int32_t ReferenceScore(const ExplorePlotScoreInput& input) {
    std::int32_t score = 0;
    for (const auto& plot : input.plots) {
        if (!plot.exists) continue;
        if (plot.is_center_plot) continue;
        if (plot.revealed) continue;

        if (plot.adjacent_revealed && plot.distance_from_origin > 1) {
            bool found_visible_edge = false;
            for (const auto& edge : plot.adjacent_plots) {
                if (edge.exists && edge.revealed && edge.distance_from_origin <= 1 &&
                    plot.origin_can_see_candidate) {
                    found_visible_edge = true;
                    break;
                }
            }
            if (!found_visible_edge) continue;
        }

        if (!plot.adjacent_revealed) {
            score += 100;
        } else if (input.domain == ExploreDomain::sea) {
            if (plot.water || (plot.has_feature && plot.feature_impassable)) score += 10;
            else if (plot.mountain || plot.hills ||
                     (plot.has_feature && plot.feature_see_through_change_positive)) score += 100;
            else score += 200;
        } else if (input.domain == ExploreDomain::land) {
            if (plot.mountain || plot.water) score += 10;
            else if (plot.hills) score += 200;
            else score += 100;
        }
        score += 1 - plot.distance_from_origin;
    }
    return score;
}

void TestOffsetOrderAndFilters() {
    const auto input = MakeInput();
    for (std::size_t index = 0; index < input.plots.size(); ++index) {
        Require(input.plots[index].offset_x == kExplorePlotOffsetOrder[index][0] &&
                input.plots[index].offset_y == kExplorePlotOffsetOrder[index][1],
                "Offset order drifted from x-outer/y-inner source loop");
    }

    auto filtered = input;
    filtered.plots[0].exists = false; // null plot
    filtered.plots[1].exists = true;
    filtered.plots[1].is_center_plot = true;
    filtered.plots[2].exists = true;
    filtered.plots[2].revealed = true;
    filtered.plots[3].exists = true;
    filtered.plots[3].distance_from_origin = 1;
    filtered.plots[3].adjacent_revealed = false;
    filtered.plots[4].exists = true;
    filtered.plots[4].is_center_plot = true;
    filtered.plots[4].adjacent_revealed = true;
    filtered.plots[4].distance_from_origin = 1;
    filtered.plots[5].exists = true;
    filtered.plots[5].adjacent_revealed = true;
    filtered.plots[5].distance_from_origin = 2;
    filtered.plots[5].adjacent_plots[0] = {true, true, 1};
    filtered.plots[5].origin_can_see_candidate = false;
    Require(score_explore_plot(filtered) == ReferenceScore(filtered), "Filter boundary mismatch");
    Require(score_explore_plot(filtered) == 100, "Null/self/revealed/blocked filters scored incorrectly");
}

void TestTerrainAndVisibilityCases() {
    auto input = MakeInput();
    input.domain = ExploreDomain::land;
    auto& land_bad = input.plots[0];
    land_bad.exists = true; land_bad.adjacent_revealed = true; land_bad.water = true;
    land_bad.distance_from_origin = 1;
    auto& land_hill = input.plots[1];
    land_hill.exists = true; land_hill.adjacent_revealed = true; land_hill.hills = true;
    land_hill.distance_from_origin = 1;
    auto& land_flat = input.plots[2];
    land_flat.exists = true; land_flat.adjacent_revealed = true;
    land_flat.distance_from_origin = 1;
    input.domain = ExploreDomain::land;
    Require(score_explore_plot(input) == ReferenceScore(input), "Land terrain score mismatch");
    Require(score_explore_plot(input) == 310, "Land bad/hills/flat scores mismatch");

    input = MakeInput();
    input.domain = ExploreDomain::sea;
    auto& sea_bad = input.plots[0];
    sea_bad.exists = true; sea_bad.adjacent_revealed = true; sea_bad.has_feature = true;
    sea_bad.feature_impassable = true; sea_bad.distance_from_origin = 1;
    auto& sea_good = input.plots[1];
    sea_good.exists = true; sea_good.adjacent_revealed = true; sea_good.has_feature = true;
    sea_good.feature_see_through_change_positive = true; sea_good.distance_from_origin = 1;
    auto& sea_best = input.plots[2];
    sea_best.exists = true; sea_best.adjacent_revealed = true; sea_best.distance_from_origin = 1;
    Require(score_explore_plot(input) == ReferenceScore(input), "Sea terrain score mismatch");
    Require(score_explore_plot(input) == 310, "Sea feature scores mismatch");

    auto& visible = input.plots[3];
    visible.exists = true; visible.adjacent_revealed = true; visible.distance_from_origin = 2;
    visible.adjacent_plots[5] = {true, true, 1};
    visible.origin_can_see_candidate = true;
    Require(score_explore_plot(input) == ReferenceScore(input), "Visible adjacent edge mismatch");
    Require(score_explore_plot(input) == 509, "Visible adjacent edge bonus mismatch");
    visible.adjacent_plots[5].distance_from_origin = 2;
    Require(score_explore_plot(input) == ReferenceScore(input), "Out-of-range adjacent edge mismatch");
    Require(score_explore_plot(input) == 310, "Out-of-range adjacent edge was accepted");
}

void TestDomainAndDistance() {
    auto input = MakeInput();
    input.domain = ExploreDomain::unsupported;
    input.plots[0].exists = true;
    input.plots[0].distance_from_origin = 0;
    input.plots[0].adjacent_revealed = true;
    input.plots[1].exists = true;
    input.plots[1].distance_from_origin = 2;
    input.plots[1].adjacent_revealed = false;
    Require(score_explore_plot(input) == ReferenceScore(input), "Unsupported domain behavior mismatch");
    Require(score_explore_plot(input) == 100, "Unsupported domain or distance bonus changed");
}

std::vector<Job<ExplorePlotScoreInput>> MakeJobs() {
    std::vector<Job<ExplorePlotScoreInput>> jobs;
    for (std::uint64_t id = 0; id < 36; ++id) {
        auto input = MakeInput();
        input.domain = (id % 2 == 0) ? ExploreDomain::land : ExploreDomain::sea;
        auto& first = input.plots[0];
        first.exists = true;
        first.adjacent_revealed = true;
        first.distance_from_origin = 1;
        first.water = (id % 3 == 0);
        first.hills = (id % 3 == 1);
        auto& second = input.plots[4];
        second.exists = (id % 4 != 0);
        second.revealed = (id % 5 == 0);
        second.distance_from_origin = 1;
        jobs.push_back({1000 - id, input});
    }
    return jobs;
}

void TestOrderedWorkers() {
    const auto jobs = MakeJobs();
    const BatchStamp stamp{7, 11, 13, 17, 19};
    std::vector<std::int32_t> expected;
    auto sorted_jobs = jobs;
    std::sort(sorted_jobs.begin(), sorted_jobs.end(), [](const auto& lhs, const auto& rhs) {
        return lhs.id < rhs.id;
    });
    for (const auto& job : sorted_jobs) expected.push_back(ReferenceScore(job.input));

    for (const std::size_t worker_count : {1U, 2U, 4U}) {
        const auto result = evaluate_ordered(stamp, jobs, worker_count,
            [](const ExplorePlotScoreInput& input, const CancellationToken&) {
                return score_explore_plot(input);
            });
        Require(result.status == BatchStatus::ready, "Worker batch did not complete");
        Require(result.stamp == stamp, "Batch stamp changed");
        Require(result.rows.size() == expected.size(), "Worker batch row count changed");
        for (std::size_t index = 0; index < result.rows.size(); ++index) {
            Require(result.rows[index].id == sorted_jobs[index].id, "Rows are not in stable ID order");
            Require(result.rows[index].value == expected[index], "Parallel result differs from reference");
        }
    }
}

void TestEmptyCancellationAndFailure() {
    const BatchStamp stamp{1, 2, 3, 4, 5};
    auto operation = [](const ExplorePlotScoreInput& input, const CancellationToken&) {
        return score_explore_plot(input);
    };
    const auto empty = evaluate_ordered<ExplorePlotScoreInput, decltype(operation)>(stamp, {}, 4, operation);
    Require(empty.status == BatchStatus::ready && empty.rows.empty(), "Empty batch was not ready and empty");

    CancellationSource cancellation;
    cancellation.request();
    const auto cancelled = evaluate_ordered(stamp, MakeJobs(), 4, operation, cancellation.token());
    Require(cancelled.status == BatchStatus::cancelled && cancelled.rows.empty(), "Pre-cancel was not honored");

    auto jobs = MakeJobs();
    const auto failing = [](const ExplorePlotScoreInput& input, const CancellationToken&) {
        if (input.plots[0].water) throw std::runtime_error("injected scoring failure");
        return score_explore_plot(input);
    };
    const auto failed = evaluate_ordered(stamp, jobs, 4, failing);
    Require(failed.status == BatchStatus::failed && failed.error != nullptr, "Worker failure was not reported");
    Require(failed.rows.empty(), "Failed batch exposed partial rows");
}
} // namespace

int main() {
    try {
        TestOffsetOrderAndFilters();
        TestTerrainAndVisibilityCases();
        TestDomainAndDistance();
        TestOrderedWorkers();
        TestEmptyCancellationAndFailure();
        std::printf("EXPLORE_PLOT_SCORES_PASS checks=%d GAMECORE_LOADED=false\n", checks);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "EXPLORE_PLOT_SCORES_FAIL checks=%d error=%s\n", checks, error.what());
        return 1;
    }
}
