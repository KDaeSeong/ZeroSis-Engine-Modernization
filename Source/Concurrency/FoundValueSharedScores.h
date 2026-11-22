#pragma once

#include "FoundValueScores.h"

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace zerosis::found_value_shared {

using namespace zerosis::found_value;
using CommonSnapshot = Snapshot;

inline constexpr std::uint32_t kMissingPlot = (std::numeric_limits<std::uint32_t>::max)();

struct PlotFacts {
    Tile tile{};
    std::array<std::int32_t, kDistanceCount> strategic_by_distance{};
};

struct Slot {
    std::uint32_t map_plot_index = kMissingPlot;
    std::int32_t distance = 0;
};

struct Candidate {
    std::uint32_t center_plot_index = kMissingPlot;
    bool center_can_found_visible = false;
    bool center_can_found_full = false;
    bool center_has_unique_luxury = false;
    bool center_has_resource_for_team = false;
    bool center_is_river = false;
    bool center_is_coastal = false;
    std::int32_t center_area = 0;
    std::array<Slot, kOffsetCount> slots{};
};

inline bool zero_tile(const Tile& tile) noexcept {
    return !tile.present && tile.distance == 0 && tile.owner == OwnerKind::unowned &&
           !tile.city && !tile.city_owner_is_major && tile.food_value == 0 &&
           tile.happiness_value == 0 && tile.production_value == 0 && tile.gold_value == 0 &&
           tile.science_value == 0 && tile.faith_value == 0 && tile.resource_value == 0 &&
           tile.strategic_value == 0 && !tile.forest && !tile.jungle && !tile.wetlands &&
           !tile.natural_wonder && !tile.desert_without_resource && !tile.hills &&
           tile.adjacent_mountains == 0 && !tile.unimproved;
}

inline Status validate_common(const CommonSnapshot& common) noexcept {
    if (common.path != Path::settler_no_yield_no_coast_only) return Status::unsupported_path;
    if (!common.valid || !common.has_player || !common.center_present ||
        common.center_can_found_visible || common.center_can_found_full ||
        common.center_has_unique_luxury || common.center_has_resource_for_team ||
        common.center_is_river || common.center_is_coastal || common.center_area != 0 ||
        common.min_city_range < 0 || common.major_civ_count < 0 || common.major_civ_count > 64 ||
        (!common.capital_present && common.capital_area != 0))
        return Status::invalid_snapshot;
    for (const Tile& tile : common.tiles) {
        if (!zero_tile(tile)) return Status::invalid_snapshot;
    }
    return Status::ok;
}

inline Status validate_facts(const PlotFacts* facts, std::size_t fact_count) noexcept {
    if ((fact_count != 0 && facts == nullptr) || fact_count > kMissingPlot)
        return Status::invalid_snapshot;
    for (std::size_t index = 0; index < fact_count; ++index) {
        const PlotFacts& fact = facts[index];
        if (fact.tile.distance != 0 || fact.tile.strategic_value != 0 ||
            fact.strategic_by_distance[0] != 0 || fact.strategic_by_distance[6] != 0 ||
            fact.strategic_by_distance[7] != 0)
            return Status::invalid_snapshot;
    }
    return Status::ok;
}

inline Status validate_candidate(const Candidate& candidate, const PlotFacts* facts,
                                 std::size_t fact_count) noexcept {
    if (facts == nullptr || candidate.center_plot_index >= fact_count)
        return Status::invalid_snapshot;
    for (std::size_t offset = 0; offset < kOffsetCount; ++offset) {
        const Slot& slot = candidate.slots[offset];
        if (slot.map_plot_index == kMissingPlot) {
            if (slot.distance != 0) return Status::invalid_snapshot;
            continue;
        }
        if (slot.map_plot_index >= fact_count || slot.distance < 0 ||
            slot.distance >= static_cast<std::int32_t>(kDistanceCount) ||
            !facts[slot.map_plot_index].tile.present)
            return Status::invalid_snapshot;
    }
    const Slot& center = candidate.slots[kCenterOffset];
    if (center.map_plot_index != candidate.center_plot_index || center.distance != 0 ||
        !facts[candidate.center_plot_index].tile.present)
        return Status::invalid_snapshot;
    return Status::ok;
}

inline Status validate_batch(const CommonSnapshot& common, const PlotFacts* facts,
                             std::size_t fact_count, const Candidate* candidates,
                             std::size_t candidate_count) noexcept {
    const Status common_status = validate_common(common);
    if (common_status != Status::ok) return common_status;
    const Status facts_status = validate_facts(facts, fact_count);
    if (facts_status != Status::ok) return facts_status;
    if (candidate_count != 0 && candidates == nullptr) return Status::invalid_snapshot;
    for (std::size_t index = 0; index < candidate_count; ++index) {
        const Status candidate_status = validate_candidate(candidates[index], facts, fact_count);
        if (candidate_status != Status::ok) return candidate_status;
    }
    return Status::ok;
}

// Precondition: the exact common/facts/candidate bytes passed validate_batch,
// and have remained immutable since that validation completed.
inline Result evaluate_shared_prevalidated(const CommonSnapshot& common,
                                           const Candidate& candidate,
                                           const PlotFacts* facts,
                                           std::size_t fact_count) noexcept {
    (void)fact_count;
    const auto tile_at = [&candidate, facts](std::size_t offset) noexcept -> detail::ScoringTile {
        const Slot& slot = candidate.slots[offset];
        if (slot.map_plot_index == kMissingPlot) return {};
        const PlotFacts& fact = facts[slot.map_plot_index];
        const auto distance = static_cast<std::size_t>(slot.distance);
        return {&fact.tile, slot.distance, fact.strategic_by_distance[distance]};
    };
    return detail::score_site(common, candidate, tile_at);
}

inline Result evaluate_shared(const CommonSnapshot& common, const Candidate& candidate,
                              const PlotFacts* facts, std::size_t fact_count) noexcept {
    const Status status = validate_batch(common, facts, fact_count, &candidate, 1);
    if (status != Status::ok) return {status, 0};
    return evaluate_shared_prevalidated(common, candidate, facts, fact_count);
}

} // namespace zerosis::found_value_shared
