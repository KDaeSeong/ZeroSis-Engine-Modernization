#include "FoundValueSharedScores.h"

#define main found_value_scores_legacy_main
#include "found_value_scores_template.cpp"
#undef main

#include <cstring>

using namespace zerosis::found_value_shared;

static CommonSnapshot make_common(const Snapshot& source) {
    CommonSnapshot common = source;
    common.center_can_found_visible = false;
    common.center_can_found_full = false;
    common.center_has_unique_luxury = false;
    common.center_has_resource_for_team = false;
    common.center_is_river = false;
    common.center_is_coastal = false;
    common.center_area = 0;
    common.tiles = {};
    return common;
}

static void make_shared(const Snapshot& source, CommonSnapshot& common,
                        Candidate& candidate, std::vector<PlotFacts>& facts) {
    common = make_common(source);
    candidate = {};
    candidate.center_plot_index = static_cast<std::uint32_t>(kCenterOffset);
    candidate.center_can_found_visible = source.center_can_found_visible;
    candidate.center_can_found_full = source.center_can_found_full;
    candidate.center_has_unique_luxury = source.center_has_unique_luxury;
    candidate.center_has_resource_for_team = source.center_has_resource_for_team;
    candidate.center_is_river = source.center_is_river;
    candidate.center_is_coastal = source.center_is_coastal;
    candidate.center_area = source.center_area;
    facts.assign(kOffsetCount, PlotFacts{});
    for (std::size_t offset = 0; offset < kOffsetCount; ++offset) {
        const Tile& tile = source.tiles[offset];
        if (!tile.present) {
            candidate.slots[offset] = {kMissingPlot, 0};
            continue;
        }
        PlotFacts& fact = facts[offset];
        fact.tile = tile;
        fact.tile.distance = 0;
        const std::int32_t distance = tile.distance;
        if (distance >= 1 && distance <= 5)
            fact.strategic_by_distance[static_cast<std::size_t>(distance)] = tile.strategic_value;
        fact.tile.strategic_value = 0;
        candidate.slots[offset] = {static_cast<std::uint32_t>(offset), distance};
    }
}

static bool compare_shared_case(const char* name, const Snapshot& source) {
    std::int32_t oracle = 0;
    if (!source_oracle(source, oracle)) return false;
    const Result dense = evaluate(source);
    CommonSnapshot common{};
    Candidate candidate{};
    std::vector<PlotFacts> facts;
    make_shared(source, common, candidate, facts);
    const Result shared = evaluate_shared(common, candidate, facts.data(), facts.size());
    if (dense.status != Status::ok || dense.score != oracle ||
        shared.status != dense.status || shared.score != dense.score) {
        std::fprintf(stderr, "SHARED_CASE_FAIL name=%s dense_status=%u dense=%d shared_status=%u shared=%d oracle=%d\n",
                     name, static_cast<unsigned>(dense.status), dense.score,
                     static_cast<unsigned>(shared.status), shared.score, oracle);
        return false;
    }
    ++check_count;
    return true;
}

static bool expect_status(const char* name, Status expected, const Result& result) {
    if (result.status != expected || result.score != 0) {
        std::fprintf(stderr, "SHARED_STATUS_FAIL name=%s expected=%u actual=%u score=%d\n",
                     name, static_cast<unsigned>(expected), static_cast<unsigned>(result.status), result.score);
        return false;
    }
    ++check_count;
    return true;
}

int main() {
    Snapshot base = make_base_snapshot();
    Tile tile{};
    tile.owner = OwnerKind::unowned;
    tile.food_value = 3;
    tile.strategic_value = 41;
    set_tile(base, 1, 0, 1, tile);
    tile.food_value = 2;
    tile.strategic_value = 73;
    set_tile(base, 2, 0, 2, tile);
    if (!compare_shared_case("distance_indexed_strategic", base)) return 1;

    Snapshot clipped = make_base_snapshot();
    tile = {};
    tile.owner = OwnerKind::unowned;
    tile.food_value = 4;
    set_tile(clipped, -7, -7, 7, tile);
    set_tile(clipped, 7, 7, 7, tile);
    if (!compare_shared_case("clipped_outer_corners", clipped)) return 2;

    Snapshot traits = make_base_snapshot();
    traits.is_inca = true;
    traits.faith_from_unimproved_forest = true;
    traits.faith_flavor_multiplier = 12;
    traits.center_is_coastal = true;
    traits.center_is_river = true;
    traits.center_has_resource_for_team = true;
    for (int dx = -1; dx <= 1; ++dx) {
        tile = {};
        tile.owner = OwnerKind::unowned;
        tile.forest = true;
        tile.unimproved = true;
        tile.hills = true;
        tile.adjacent_mountains = 2;
        tile.faith_value = 1;
        set_tile(traits, dx, 1, 1, tile);
    }
    if (!compare_shared_case("traits_and_center_adjustments", traits)) return 3;

    Snapshot duplicate = make_base_snapshot();
    tile = {};
    tile.owner = OwnerKind::unowned;
    tile.food_value = 2;
    tile.strategic_value = 19;
    set_tile(duplicate, 1, 0, 1, tile);
    tile.strategic_value = 37;
    set_tile(duplicate, 2, 0, 2, tile);
    std::int32_t duplicate_oracle = 0;
    if (!source_oracle(duplicate, duplicate_oracle)) return 4;
    CommonSnapshot duplicate_common{};
    Candidate duplicate_candidate{};
    std::vector<PlotFacts> duplicate_facts;
    make_shared(duplicate, duplicate_common, duplicate_candidate, duplicate_facts);
    const std::size_t distance_one_offset = static_cast<std::size_t>(8 * kDiameter + kRadius);
    const std::size_t distance_two_offset = static_cast<std::size_t>(9 * kDiameter + kRadius);
    const std::uint32_t repeated = duplicate_candidate.slots[distance_one_offset].map_plot_index;
    const Slot& distance_one_slot = duplicate_candidate.slots[distance_one_offset];
    const Slot& distance_two_slot = duplicate_candidate.slots[distance_two_offset];
    if (repeated == kMissingPlot || repeated >= duplicate_facts.size() ||
        distance_one_slot.distance != 1 || distance_two_slot.distance != 2 ||
        distance_two_slot.map_plot_index == kMissingPlot ||
        distance_two_slot.map_plot_index >= duplicate_facts.size()) {
        std::fprintf(stderr,
                     "SHARED_DUPLICATE_FIXTURE_FAIL first_index=%u first_distance=%d second_index=%u second_distance=%d facts=%zu\n",
                     repeated, distance_one_slot.distance, distance_two_slot.map_plot_index,
                     distance_two_slot.distance, duplicate_facts.size());
        return 20;
    }
    duplicate_candidate.slots[distance_two_offset].map_plot_index = repeated;
    duplicate_facts.at(repeated).strategic_by_distance[2] = 37;
    duplicate_facts.resize(kOffsetCount);
    const Result duplicate_dense = evaluate(duplicate);
    const Result duplicate_shared = evaluate_shared(duplicate_common, duplicate_candidate,
                                                      duplicate_facts.data(), duplicate_facts.size());
    if (duplicate_dense.status != Status::ok || duplicate_dense.score != duplicate_oracle ||
        duplicate_shared.status != duplicate_dense.status || duplicate_shared.score != duplicate_dense.score)
        return 5;
    ++check_count;

    Snapshot faith_carry = make_base_snapshot();
    tile = {};
    tile.owner = OwnerKind::unowned;
    tile.faith_value = 2;
    set_tile(faith_carry, -1, 0, 1, tile);
    tile = {};
    tile.owner = OwnerKind::unowned;
    set_tile(faith_carry, 0, 4, 4, tile);
    set_tile(faith_carry, 0, 5, 5, tile);
    if (!compare_shared_case("source_faith_carry_distance4_5", faith_carry)) return 6;

    Snapshot no_capital = make_base_snapshot();
    no_capital.capital_present = false;
    no_capital.capital_area = 0;
    no_capital.center_area = 1;
    if (!compare_shared_case("missing_capital_zero_sentinel", no_capital)) return 7;

    Snapshot cannot_found = make_base_snapshot();
    cannot_found.center_can_found_full = false;
    if (!compare_shared_case("can_found_false_center_facts", cannot_found)) return 8;

    Snapshot generated = make_base_snapshot();
    std::vector<Snapshot> random_cases;
    random_cases.reserve(512);
    for (int index = 0; index < 512; ++index) random_cases.push_back(random_snapshot());
    for (std::size_t index = 0; index < random_cases.size(); ++index) {
        if (!compare_shared_case("generated_clipped_or_wrapped", random_cases[index])) return 9;
    }
    (void)generated;

    CommonSnapshot common{};
    Candidate candidate{};
    std::vector<PlotFacts> facts;
    make_shared(base, common, candidate, facts);
    if (!expect_status("valid_batch", Status::ok,
                       {validate_batch(common, facts.data(), facts.size(), &candidate, 1), 0})) return 10;
    Candidate bad = candidate;
    bad.slots[0].map_plot_index = static_cast<std::uint32_t>(facts.size());
    if (!expect_status("out_of_range_reference", Status::invalid_snapshot,
                       {validate_batch(common, facts.data(), facts.size(), &bad, 1), 0})) return 11;
    bad = candidate;
    bad.slots[0] = {kMissingPlot, 1};
    if (!expect_status("missing_slot_distance", Status::invalid_snapshot,
                       {validate_batch(common, facts.data(), facts.size(), &bad, 1), 0})) return 12;
    bad = candidate;
    bad.slots[kCenterOffset].map_plot_index = static_cast<std::uint32_t>(kCenterOffset + 1);
    if (!expect_status("center_slot_mismatch", Status::invalid_snapshot,
                       {validate_batch(common, facts.data(), facts.size(), &bad, 1), 0})) return 13;
    bad = candidate;
    bad.slots[0].distance = 8;
    if (!expect_status("distance_out_of_range", Status::invalid_snapshot,
                       {validate_batch(common, facts.data(), facts.size(), &bad, 1), 0})) return 14;
    bad = candidate;
    bad.slots[0] = {0, 0};
    facts[0].tile.present = false;
    if (!expect_status("reference_to_absent_fact", Status::invalid_snapshot,
                       {validate_batch(common, facts.data(), facts.size(), &bad, 1), 0})) return 15;
    make_shared(base, common, candidate, facts);
    facts[0].strategic_by_distance[6] = 1;
    if (!expect_status("reserved_strategic_distance", Status::invalid_snapshot,
                       {validate_batch(common, facts.data(), facts.size(), &candidate, 1), 0})) return 16;
    make_shared(base, common, candidate, facts);
    common.tiles[3].present = true;
    if (!expect_status("common_must_be_tile_free", Status::invalid_snapshot,
                       {validate_batch(common, facts.data(), facts.size(), &candidate, 1), 0})) return 17;
    make_shared(base, common, candidate, facts);
    common.path = Path::other;
    if (!expect_status("unsupported_path", Status::unsupported_path,
                       {validate_batch(common, facts.data(), facts.size(), &candidate, 1), 0})) return 18;

    Snapshot overflow = make_base_snapshot();
    overflow.settler_food_multiplier = (std::numeric_limits<std::int32_t>::max)();
    overflow.ring_modifier[1] = 2;
    tile = {};
    tile.owner = OwnerKind::unowned;
    tile.food_value = (std::numeric_limits<std::int32_t>::max)();
    set_tile(overflow, 1, 0, 1, tile);
    make_shared(overflow, common, candidate, facts);
    const CommonSnapshot before_common = common;
    const Candidate before_candidate = candidate;
    const std::vector<PlotFacts> before_facts = facts;
    const Result overflow_result = evaluate_shared(common, candidate, facts.data(), facts.size());
    if (overflow_result.status != Status::overflow || overflow_result.score != 0 ||
        common.path != before_common.path || candidate.center_plot_index != before_candidate.center_plot_index ||
        facts.size() != before_facts.size() ||
        facts[1].tile.food_value != before_facts[1].tile.food_value ||
        facts[1].strategic_by_distance[1] != before_facts[1].strategic_by_distance[1]) return 19;
    ++check_count;

    std::printf("FOUND_VALUE_SHARED_SCORES_PASS checks=%u candidates=%zu dense_bytes=%zu shared_candidate_bytes=%zu GAMECORE_LOADED=false SOURCE_ORACLE=EXTRACTED\n",
                check_count, random_cases.size(), sizeof(Snapshot), sizeof(Candidate));
    return 0;
}

// The verifier appends the exact original SDK function bodies here.
