#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace zerosis::found_value {

inline constexpr std::int32_t kRadius = 7;
inline constexpr std::int32_t kDiameter = 2 * kRadius + 1;
inline constexpr std::size_t kOffsetCount = static_cast<std::size_t>(kDiameter * kDiameter);
inline constexpr std::size_t kCenterOffset = static_cast<std::size_t>(kRadius * kDiameter + kRadius);
inline constexpr std::size_t kDistanceCount = 8;

enum class Status : std::uint8_t {
    ok,
    invalid_snapshot,
    unsupported_path,
    overflow,
};

enum class OwnerKind : std::uint8_t {
    unowned,
    player,
    other,
};

enum class Path : std::uint8_t {
    settler_no_yield_no_coast_only,
    other,
};

struct Tile {
    bool present = false;
    std::int32_t distance = 0;
    OwnerKind owner = OwnerKind::unowned;
    bool city = false;
    bool city_owner_is_major = false;

    std::int32_t food_value = 0;
    std::int32_t happiness_value = 0;
    std::int32_t production_value = 0;
    std::int32_t gold_value = 0;
    std::int32_t science_value = 0;
    std::int32_t faith_value = 0;
    std::int32_t resource_value = 0;
    // Candidate-relative precomputed result of ComputeStrategicValue. The
    // owner capture cache must key this helper by unique plot and distance.
    std::int32_t strategic_value = 0;

    bool forest = false;
    bool jungle = false;
    bool wetlands = false;
    bool natural_wonder = false;
    bool desert_without_resource = false;
    bool hills = false;
    std::int32_t adjacent_mountains = 0;
    bool unimproved = false;
};

// Values in this structure are owned observations captured on the game thread.
// Tile helper values must be computed once per unique map plot and reused by
// each candidate whose radius includes that plot.
struct Snapshot {
    Path path = Path::other;
    bool valid = false;
    bool has_player = false;
    bool center_present = false;
    bool capital_present = false;
    bool center_can_found_visible = false;
    bool center_can_found_full = false;
    bool center_has_unique_luxury = false;
    bool center_has_resource_for_team = false;
    bool center_is_river = false;
    bool center_is_coastal = false;
    bool coastal_civilization = false;
    bool human_player = false;
    bool faith_from_unimproved_forest = false;
    bool move_friendly_woods_as_road = false;
    bool gets_natural_wonder_yield_modifier = false;
    bool is_inca = false;
    bool is_brazil = false;
    bool is_morocco = false;
    bool is_netherlands = false;

    std::int32_t center_area = 0;
    std::int32_t capital_area = 0;
    std::int32_t naval_flavor = 0;
    std::int32_t growth_flavor = 0;
    std::int32_t expansion_flavor = 0;
    std::int32_t boldness = 0;

    std::array<std::int32_t, kDistanceCount> ring_modifier{};
    std::int32_t settler_food_multiplier = 0;
    std::int32_t settler_happiness_multiplier = 0;
    std::int32_t settler_production_multiplier = 0;
    std::int32_t settler_gold_multiplier = 0;
    std::int32_t settler_science_multiplier = 0;
    std::int32_t settler_faith_multiplier = 0;
    std::int32_t faith_flavor_multiplier = 0;
    std::int32_t settler_resource_multiplier = 0;
    std::int32_t settler_strategic_multiplier = 0;
    std::int32_t build_on_resource_percent = 0;
    std::int32_t build_on_river_percent = 0;
    std::int32_t build_on_coast_percent = 0;
    std::int32_t min_city_range = 0;
    std::int32_t min_water_size_for_ocean = 0;
    std::int32_t brazil_multiplier = 0;
    std::int32_t spain_multiplier = 0;
    std::int32_t morocco_multiplier = 0;
    std::int32_t netherlands_multiplier = 0;
    std::int32_t inca_multiplier = 0;
    std::int32_t major_civ_count = 0;

    std::array<Tile, kOffsetCount> tiles{};
};

struct Result {
    Status status = Status::invalid_snapshot;
    std::int32_t score = 0;
};

inline bool checked_add(std::int32_t left, std::int32_t right, std::int32_t& out) noexcept {
    const std::int64_t value = static_cast<std::int64_t>(left) + right;
    if (value < (std::numeric_limits<std::int32_t>::min)() ||
        value > (std::numeric_limits<std::int32_t>::max)()) return false;
    out = static_cast<std::int32_t>(value);
    return true;
}

inline bool checked_subtract(std::int32_t left, std::int32_t right,
                             std::int32_t& out) noexcept {
    const std::int64_t value = static_cast<std::int64_t>(left) - right;
    if (value < (std::numeric_limits<std::int32_t>::min)() ||
        value > (std::numeric_limits<std::int32_t>::max)()) return false;
    out = static_cast<std::int32_t>(value);
    return true;
}

inline bool checked_multiply(std::int32_t left, std::int32_t right,
                             std::int32_t& out) noexcept {
    const std::int64_t value = static_cast<std::int64_t>(left) * right;
    if (value < (std::numeric_limits<std::int32_t>::min)() ||
        value > (std::numeric_limits<std::int32_t>::max)()) return false;
    out = static_cast<std::int32_t>(value);
    return true;
}

inline bool checked_divide(std::int32_t value, std::int32_t divisor,
                           std::int32_t& out) noexcept {
    if (divisor == 0 ||
        (value == (std::numeric_limits<std::int32_t>::min)() && divisor == -1)) return false;
    out = value / divisor;
    return true;
}

inline bool add_to(std::int32_t& target, std::int32_t value) noexcept {
    return checked_add(target, value, target);
}

inline bool multiply_into(std::int32_t& target, std::int32_t value) noexcept {
    return checked_multiply(target, value, target);
}

inline bool divide_into(std::int32_t& target, std::int32_t value) noexcept {
    return checked_divide(target, value, target);
}

inline Result evaluate(const Snapshot& input) noexcept {
    if (input.path != Path::settler_no_yield_no_coast_only)
        return {Status::unsupported_path, 0};
    if (!input.valid || !input.has_player || !input.center_present ||
        input.min_city_range < 0 ||
        input.major_civ_count < 0 || input.major_civ_count > 64)
        return {Status::invalid_snapshot, 0};
    if (!input.capital_present && input.capital_area != 0)
        return {Status::invalid_snapshot, 0};

    const Tile& center = input.tiles[kCenterOffset];
    if (!center.present || center.distance != 0) return {Status::invalid_snapshot, 0};
    if (!input.center_can_found_visible || !input.center_can_found_full)
        return {Status::ok, 0};

    std::int32_t rtn_value = 0;
    std::int32_t total_food_value = 0;
    std::int32_t total_happiness_value = 0;
    std::int32_t total_production_value = 0;
    std::int32_t total_gold_value = 0;
    std::int32_t total_science_value = 0;
    std::int32_t total_faith_value = 0;
    std::int32_t total_resource_value = 0;
    std::int32_t total_strategic_value = 0;
    std::int32_t celtic_forest_count = 0;
    std::int32_t iroquois_forest_count = 0;
    std::int32_t brazil_jungle_count = 0;
    std::int32_t natural_wonder_count = 0;
    std::int32_t desert_count = 0;
    std::int32_t wetlands_count = 0;
    std::int32_t closest_city_of_mine = 999;
    std::int32_t closest_enemy_city = 999;
    // Source quirk: PlotFoundValue initializes iFaithValue before the map scan,
    // but does not clear it with the other per-plot yield values. Preserve the
    // resulting dx/dy-order carry at center/rings four and five.
    std::int32_t faith_value = 0;

    for (std::int32_t dx = -kRadius; dx <= kRadius; ++dx) {
        for (std::int32_t dy = -kRadius; dy <= kRadius; ++dy) {
            const std::size_t index = static_cast<std::size_t>((dx + kRadius) * kDiameter + dy + kRadius);
            const Tile& tile = input.tiles[index];
            if (!tile.present) continue;
            if (tile.distance < 0) return {Status::invalid_snapshot, 0};
            if (tile.distance > kRadius) continue;

            if (tile.owner == OwnerKind::unowned || tile.owner == OwnerKind::player) {
                if (closest_city_of_mine > tile.distance && tile.city)
                    closest_city_of_mine = tile.distance;

                if (tile.distance <= 5) {
                    const std::int32_t distance = tile.distance;
                    const std::int32_t ring = input.ring_modifier[static_cast<std::size_t>(distance)];
                    std::int32_t food = 0;
                    std::int32_t production = 0;
                    std::int32_t gold = 0;
                    std::int32_t science = 0;
                    std::int32_t happiness = 0;
                    std::int32_t resources = 0;
                    std::int32_t strategic = 0;

                    if (distance > 0 && distance <= 3) {
                        food = ring;
                        if (!multiply_into(food, tile.food_value) ||
                            !multiply_into(food, input.settler_food_multiplier)) return {Status::overflow, 0};
                        production = ring;
                        if (!multiply_into(production, tile.production_value) ||
                            !multiply_into(production, input.settler_production_multiplier)) return {Status::overflow, 0};
                        gold = ring;
                        if (!multiply_into(gold, tile.gold_value) ||
                            !multiply_into(gold, input.settler_gold_multiplier)) return {Status::overflow, 0};
                        science = ring;
                        if (!multiply_into(science, tile.science_value) ||
                            !multiply_into(science, input.settler_science_multiplier)) return {Status::overflow, 0};
                        faith_value = ring;
                        if (!multiply_into(faith_value, tile.faith_value) ||
                            !multiply_into(faith_value, input.settler_faith_multiplier)) return {Status::overflow, 0};
                    }

                    if (distance <= 5 && tile.owner == OwnerKind::unowned) {
                        happiness = ring;
                        if (!multiply_into(happiness, tile.happiness_value) ||
                            !multiply_into(happiness, input.settler_happiness_multiplier)) return {Status::overflow, 0};
                        resources = ring;
                        if (!multiply_into(resources, tile.resource_value) ||
                            !multiply_into(resources, input.settler_resource_multiplier)) return {Status::overflow, 0};
                        if (distance != 0) {
                            strategic = tile.strategic_value;
                            if (!multiply_into(strategic, input.settler_strategic_multiplier))
                                return {Status::overflow, 0};
                        }
                    }

                    if (!add_to(total_food_value, food) || !add_to(total_happiness_value, happiness) ||
                        !add_to(total_production_value, production) || !add_to(total_gold_value, gold) ||
                        !add_to(total_science_value, science) || !add_to(total_faith_value, faith_value) ||
                        !add_to(total_resource_value, resources) || !add_to(total_strategic_value, strategic))
                        return {Status::overflow, 0};

                    std::int32_t plot_value = food;
                    if (!add_to(plot_value, happiness) || !add_to(plot_value, production) ||
                        !add_to(plot_value, gold) || !add_to(plot_value, science) ||
                        !add_to(plot_value, faith_value) || !add_to(plot_value, resources))
                        return {Status::overflow, 0};
                    if (plot_value == 0) {
                        std::int32_t penalty = ring;
                        if (!multiply_into(penalty, input.settler_food_multiplier) ||
                            !multiply_into(penalty, 2) || !checked_subtract(plot_value, penalty, plot_value))
                            return {Status::overflow, 0};
                    }
                    if (!add_to(plot_value, strategic)) return {Status::overflow, 0};

                    if (tile.natural_wonder && distance > 0 && distance <= 3) {
                        std::int32_t bonus = plot_value;
                        if (!multiply_into(bonus, 2) || !add_to(bonus, 500) ||
                            !add_to(plot_value, bonus)) return {Status::overflow, 0};
                    }
                    if (plot_value > 0 && tile.owner == OwnerKind::player &&
                        !divide_into(plot_value, 4)) return {Status::overflow, 0};
                    if (!add_to(rtn_value, plot_value)) return {Status::overflow, 0};

                    if (tile.forest && distance <= 5) {
                        if (!add_to(iroquois_forest_count, 1)) return {Status::overflow, 0};
                        if (distance == 1 && tile.unimproved &&
                            !add_to(celtic_forest_count, 1)) return {Status::overflow, 0};
                    } else if (tile.jungle && distance <= 3) {
                        if (!add_to(brazil_jungle_count, 1)) return {Status::overflow, 0};
                    } else if (tile.wetlands && distance <= 3) {
                        if (!add_to(wetlands_count, 1)) return {Status::overflow, 0};
                    }
                    if (tile.natural_wonder && distance <= 1 &&
                        !add_to(natural_wonder_count, 1)) return {Status::overflow, 0};
                    if (tile.desert_without_resource && distance <= 3 &&
                        !add_to(desert_count, 1)) return {Status::overflow, 0};

                    if (input.is_inca && tile.hills && distance <= 3 &&
                        tile.adjacent_mountains > 0 && tile.adjacent_mountains < 6) {
                        std::int32_t bonus = tile.adjacent_mountains;
                        if (!multiply_into(bonus, input.inca_multiplier) ||
                            !add_to(bonus, input.inca_multiplier) || !add_to(rtn_value, bonus))
                            return {Status::overflow, 0};
                    }
                }
            } else if (closest_enemy_city > tile.distance && tile.city && tile.city_owner_is_major) {
                closest_enemy_city = tile.distance;
            }
        }
    }

    if (input.faith_from_unimproved_forest) {
        if (celtic_forest_count >= 3) {
            std::int32_t bonus = 2;
            if (!multiply_into(bonus, 1000) || !multiply_into(bonus, input.faith_flavor_multiplier) ||
                !add_to(rtn_value, bonus)) return {Status::overflow, 0};
        } else if (celtic_forest_count >= 1) {
            std::int32_t bonus = 1000;
            if (!multiply_into(bonus, input.faith_flavor_multiplier) ||
                !add_to(rtn_value, bonus)) return {Status::overflow, 0};
        }
    } else if (input.move_friendly_woods_as_road) {
        std::int32_t bonus = iroquois_forest_count;
        if (!multiply_into(bonus, 10) || !add_to(rtn_value, bonus)) return {Status::overflow, 0};
    } else if (input.gets_natural_wonder_yield_modifier) {
        std::int32_t bonus = natural_wonder_count;
        if (!multiply_into(bonus, input.spain_multiplier) || !add_to(rtn_value, bonus))
            return {Status::overflow, 0};
    }

    if (input.is_brazil) {
        std::int32_t bonus = brazil_jungle_count;
        if (!multiply_into(bonus, input.brazil_multiplier) || !add_to(rtn_value, bonus))
            return {Status::overflow, 0};
    }
    if (input.is_morocco) {
        std::int32_t bonus = desert_count;
        if (!multiply_into(bonus, input.morocco_multiplier) || !add_to(rtn_value, bonus))
            return {Status::overflow, 0};
    }
    if (input.is_netherlands) {
        std::int32_t bonus = wetlands_count;
        if (!multiply_into(bonus, input.netherlands_multiplier) || !add_to(rtn_value, bonus))
            return {Status::overflow, 0};
    }

    if (rtn_value < 0) rtn_value = 0;
    if (input.center_has_resource_for_team) {
        std::int32_t adjustment = rtn_value;
        if (!multiply_into(adjustment, input.build_on_resource_percent) ||
            !divide_into(adjustment, 100) || !add_to(rtn_value, adjustment))
            return {Status::overflow, 0};
    }
    if (input.center_is_river) {
        std::int32_t adjustment = rtn_value;
        if (!multiply_into(adjustment, input.build_on_river_percent) ||
            !divide_into(adjustment, 100) || !add_to(rtn_value, adjustment))
            return {Status::overflow, 0};
    }
    if (input.center_is_coastal) {
        std::int32_t adjustment = rtn_value;
        if (!multiply_into(adjustment, input.build_on_coast_percent) ||
            !divide_into(adjustment, 100) || !add_to(rtn_value, adjustment))
            return {Status::overflow, 0};
        if (input.naval_flavor > 7) {
            adjustment = rtn_value;
            if (!multiply_into(adjustment, input.build_on_coast_percent) ||
                !divide_into(adjustment, 100) || !add_to(rtn_value, adjustment))
                return {Status::overflow, 0};
        }
        if (input.coastal_civilization) {
            if (rtn_value > 0 && !add_to(rtn_value, 25)) return {Status::overflow, 0};
            if (!multiply_into(rtn_value, 2)) return {Status::overflow, 0};
        }
    }

    if (input.human_player) {
        if (closest_city_of_mine == 3 && !divide_into(rtn_value, 2))
            return {Status::overflow, 0};
    } else {
        std::int32_t sweet_spot = 5;
        if (input.growth_flavor > 7 && !add_to(sweet_spot, 1)) return {Status::overflow, 0};
        if (input.expansion_flavor > 7 && !add_to(sweet_spot, -1)) return {Status::overflow, 0};
        if (input.growth_flavor < 4 && !add_to(sweet_spot, -1)) return {Status::overflow, 0};
        if (input.expansion_flavor < 4 && !add_to(sweet_spot, 1)) return {Status::overflow, 0};
        if (sweet_spot < 4) sweet_spot = 4;
        if (sweet_spot > 6) sweet_spot = 6;

        if (closest_city_of_mine == sweet_spot) {
            if (!multiply_into(rtn_value, 175) || !divide_into(rtn_value, 100))
                return {Status::overflow, 0};
        } else if (closest_city_of_mine < sweet_spot) {
            if (!divide_into(rtn_value, 2)) return {Status::overflow, 0};
        } else if (closest_city_of_mine > 7) {
            if (!multiply_into(rtn_value, 2) || !divide_into(rtn_value, 3))
                return {Status::overflow, 0};
        }

        if (input.boldness < 4) {
            if (closest_enemy_city <= 4) {
                if (!divide_into(rtn_value, 4)) return {Status::overflow, 0};
            } else if (closest_enemy_city == 5 && !divide_into(rtn_value, 2))
                return {Status::overflow, 0};
        } else if (input.boldness > 7) {
            if (closest_enemy_city <= 5 && closest_city_of_mine < 8 &&
                (!multiply_into(rtn_value, 3) || !divide_into(rtn_value, 2)))
                return {Status::overflow, 0};
        } else if (closest_enemy_city < 5 &&
                   (!multiply_into(rtn_value, 2) || !divide_into(rtn_value, 3)))
            return {Status::overflow, 0};

        if (input.capital_area != input.center_area && closest_city_of_mine < 7 &&
            (!multiply_into(rtn_value, 3) || !divide_into(rtn_value, 2)))
            return {Status::overflow, 0};
    }

    if (rtn_value < 0) rtn_value = 0;
    if (input.center_has_unique_luxury && !multiply_into(rtn_value, 2))
        return {Status::overflow, 0};
    return {Status::ok, rtn_value};
}

} // namespace zerosis::found_value
