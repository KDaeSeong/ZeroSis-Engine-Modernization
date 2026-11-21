#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <limits>

namespace zerosis::city_site {

// Owned observations only. The caller captures these from CvPlot on the game
// thread; this kernel has no SDK, database, Lua, or game-state references.
inline constexpr std::size_t kYieldCount = 4; // FOOD, PRODUCTION, GOLD, SCIENCE
inline constexpr std::size_t kMaxTiles = 64;

struct Cell {
    bool present = false;
    std::int32_t ring_distance = 0;
    std::array<std::int32_t, kYieldCount> yields{};
    bool foreign_owned = false;
    bool science_clear = false;
};

struct SiteInput {
    std::array<Cell, kMaxTiles> cells{};
    std::uint32_t tile_count = 0;
    std::array<std::int32_t, 3> ring_weights{};
};

enum class Status : std::uint8_t { ok, invalid_input, overflow };

struct Result {
    Status status = Status::invalid_input;
    std::int32_t specific_yield_value = 0;
    std::int32_t science_value = 0;
};

struct AllResult {
    Status status = Status::invalid_input;
    std::array<std::int32_t, kYieldCount> values{};
};

inline bool add_int32(std::int32_t left, std::int32_t right, std::int32_t& out) noexcept {
    const std::int64_t value = static_cast<std::int64_t>(left) + right;
    if (value < (std::numeric_limits<std::int32_t>::min)() ||
        value > (std::numeric_limits<std::int32_t>::max)()) return false;
    out = static_cast<std::int32_t>(value);
    return true;
}

inline bool multiply_int32(std::int32_t left, std::int32_t right, std::int32_t& out) noexcept {
    const std::int64_t value = static_cast<std::int64_t>(left) * right;
    if (value < (std::numeric_limits<std::int32_t>::min)() ||
        value > (std::numeric_limits<std::int32_t>::max)()) return false;
    out = static_cast<std::int32_t>(value);
    return true;
}

inline Result evaluate(const SiteInput& input, const std::size_t yield_index,
                       const std::size_t home_plot_index = 0) noexcept {
    if (input.tile_count > kMaxTiles || yield_index >= kYieldCount ||
        (input.tile_count != 0 && home_plot_index >= input.tile_count)) return {};

    std::int32_t specific_total = 0;
    std::int32_t science_food_total = 0;
    std::int32_t science_clear_total = 0;
    std::int32_t multiplier = 0;
    for (std::uint32_t index = 0; index < input.tile_count; ++index) {
        if (index == home_plot_index) continue;
        const Cell& cell = input.cells[index];
        if (!cell.present) continue;

        if (cell.foreign_owned) {
            multiplier = 0;
        } else if (cell.ring_distance == 1) {
            multiplier = input.ring_weights[0];
        } else if (cell.ring_distance == 2) {
            multiplier = input.ring_weights[1];
        } else if (cell.ring_distance == 3) {
            multiplier = input.ring_weights[2];
        }

        std::int32_t product = 0;
        if (!multiply_int32(cell.yields[yield_index], multiplier, product) ||
            !add_int32(specific_total, product, specific_total))
            return {Status::overflow, 0, 0};

        std::int32_t science_potential = 0;
        if (!add_int32(cell.yields[0], cell.yields[3], science_potential) ||
            !multiply_int32(science_potential, multiplier, product) ||
            !add_int32(science_food_total, product, science_food_total))
            return {Status::overflow, 0, 0};
        if (cell.science_clear && !add_int32(science_clear_total, multiplier, science_clear_total))
            return {Status::overflow, 0, 0};
    }

    std::int32_t science_total = 0;
    if (!add_int32(science_food_total, science_clear_total, science_total))
        return {Status::overflow, 0, 0};
    return {Status::ok, specific_total, science_total};
}

// FindBestSites consumes FOOD, PRODUCTION, GOLD, and SCIENCE for each site.
// This combined form traverses owned observations once and reuses the exact
// multiplier transition and science intermediate for that visit.
inline AllResult evaluate_all(const SiteInput& input,
                              const std::size_t home_plot_index = 0) noexcept {
    if (input.tile_count > kMaxTiles ||
        (input.tile_count != 0 && home_plot_index >= input.tile_count)) return {};

    std::array<std::int32_t, 3> specific_totals{};
    std::int32_t science_food_total = 0;
    std::int32_t science_clear_total = 0;
    std::int32_t multiplier = 0;
    for (std::uint32_t index = 0; index < input.tile_count; ++index) {
        if (index == home_plot_index) continue;
        const Cell& cell = input.cells[index];
        if (!cell.present) continue;

        if (cell.foreign_owned) {
            multiplier = 0;
        } else if (cell.ring_distance == 1) {
            multiplier = input.ring_weights[0];
        } else if (cell.ring_distance == 2) {
            multiplier = input.ring_weights[1];
        } else if (cell.ring_distance == 3) {
            multiplier = input.ring_weights[2];
        }

        for (std::size_t yield = 0; yield < specific_totals.size(); ++yield) {
            std::int32_t product = 0;
            if (!multiply_int32(cell.yields[yield], multiplier, product) ||
                !add_int32(specific_totals[yield], product, specific_totals[yield]))
                return {Status::overflow, {}};
        }

        std::int32_t science_potential = 0;
        std::int32_t product = 0;
        if (!add_int32(cell.yields[0], cell.yields[3], science_potential) ||
            !multiply_int32(science_potential, multiplier, product) ||
            !add_int32(science_food_total, product, science_food_total))
            return {Status::overflow, {}};
        if (cell.science_clear && !add_int32(science_clear_total, multiplier, science_clear_total))
            return {Status::overflow, {}};
    }

    std::int32_t science_value = 0;
    if (!add_int32(science_food_total, science_clear_total, science_value))
        return {Status::overflow, {}};
    return {Status::ok, {{specific_totals[0], specific_totals[1], specific_totals[2], science_value}}};
}

} // namespace zerosis::city_site
