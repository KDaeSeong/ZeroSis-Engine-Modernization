#pragma once

#include <array>
#include <cstdint>

namespace zerosis::concurrency {

// Values are copied from the game thread before evaluation. No SDK objects or
// pointers cross into this kernel.
enum class ExploreDomain : std::uint8_t { land, sea, unsupported };

struct ExploreNeighborObservation {
    bool exists = false;
    bool revealed = false;
    std::int32_t distance_from_origin = 0;
};

struct ExplorePlotObservation {
    std::int8_t offset_x = 0;
    std::int8_t offset_y = 0;
    bool exists = false; // plotXYWithRangeCheck returned a plot
    bool is_center_plot = false;
    bool revealed = false;
    bool adjacent_revealed = false;
    std::int32_t distance_from_origin = 0;
    // Result of pPlot->canSeePlot(candidate, team, range, NO_DIRECTION).
    bool origin_can_see_candidate = false;
    std::array<ExploreNeighborObservation, 6> adjacent_plots{};
    bool water = false;
    bool mountain = false;
    bool hills = false;
    bool has_feature = false;
    bool feature_impassable = false;
    bool feature_see_through_change_positive = false;
};

struct ExplorePlotScoreInput {
    ExploreDomain domain = ExploreDomain::land;
    // CvEconomicAI::ScoreExplorePlot is called with range 1 by UpdatePlots.
    std::array<ExplorePlotObservation, 9> plots{};
};

inline constexpr std::array<std::array<std::int8_t, 2>, 9> kExplorePlotOffsetOrder{{
    {{-1, -1}}, {{-1, 0}}, {{-1, 1}},
    {{0, -1}}, {{0, 0}}, {{0, 1}},
    {{1, -1}}, {{1, 0}}, {{1, 1}},
}};

inline std::int32_t score_explore_plot(const ExplorePlotScoreInput& input) noexcept {
    constexpr std::int32_t bad_score = 10;
    constexpr std::int32_t good_score = 100;
    constexpr std::int32_t really_good_score = 200;
    constexpr std::int32_t adjacency_bonus = 1;
    constexpr std::int32_t range = 1;
    std::int32_t result = 0;

    // This order is the original x-outer/y-inner loop over [-1, 1].
    for (const auto& plot : input.plots) {
        if (!plot.exists || plot.is_center_plot || plot.revealed) continue;

        if (plot.adjacent_revealed) {
            if (plot.distance_from_origin > 1) {
                bool view_blocked = true;
                for (const auto& adjacent : plot.adjacent_plots) {
                    if (!adjacent.exists || !adjacent.revealed) continue;
                    if (adjacent.distance_from_origin > range) continue;
                    // The SDK query has no adjacent-plot parameter; its result
                    // is the same for each qualifying revealed neighbor.
                    if (plot.origin_can_see_candidate) {
                        view_blocked = false;
                        break;
                    }
                }
                if (view_blocked) continue;
            }

            switch (input.domain) {
            case ExploreDomain::sea:
                if (plot.water || (plot.has_feature && plot.feature_impassable)) {
                    result += bad_score;
                } else if (plot.mountain || plot.hills ||
                           (plot.has_feature && plot.feature_see_through_change_positive)) {
                    result += good_score;
                } else {
                    result += really_good_score;
                }
                break;
            case ExploreDomain::land:
                if (plot.mountain || plot.water) result += bad_score;
                else if (plot.hills) result += really_good_score;
                else result += good_score;
                break;
            case ExploreDomain::unsupported:
                // The original switch has no default branch.
                break;
            }
        } else {
            result += good_score;
        }

        result += (range - plot.distance_from_origin) * adjacency_bonus;
    }
    return result;
}

} // namespace zerosis::concurrency
