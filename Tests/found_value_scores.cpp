#include "FoundValueScores.h"

#include <array>
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <string>
#include <thread>
#include <vector>

using namespace zerosis::found_value;

using PlayerTypes = int;
using TeamTypes = int;
using YieldTypes = int;
using FlavorTypes = int;
using CivilizationTypes = int;
using ImprovementTypes = int;
using FeatureTypes = int;
using ResourceTypes = int;
using TerrainTypes = int;

constexpr int NO_PLAYER = -1;
constexpr int NO_TEAM = -1;
constexpr int NO_YIELD = -1;
constexpr int YIELD_FOOD = 0;
constexpr int YIELD_PRODUCTION = 1;
constexpr int YIELD_GOLD = 2;
constexpr int YIELD_SCIENCE = 3;
constexpr int YIELD_FAITH = 5;
constexpr int NO_IMPROVEMENT = -1;
constexpr int NO_FEATURE = -1;
constexpr int NO_RESOURCE = -1;
constexpr int FEATURE_FOREST = 1;
constexpr int FEATURE_JUNGLE = 2;
constexpr int FEATURE_MARSH = 3;
constexpr int FEATURE_FLOOD_PLAINS = 4;
constexpr int TERRAIN_DESERT = 1;
constexpr int IMPROVEMENT_TERRACE_FARM = 1;
constexpr int IMPROVEMENT_BRAZILWOOD_CAMP = 2;
constexpr int IMPROVEMENT_KASBAH = 3;
constexpr int IMPROVEMENT_POLDER = 4;
constexpr int CIV_INCA = 1;
constexpr int CIV_BRAZIL = 2;
constexpr int CIV_MOROCCO = 3;
constexpr int CIV_NETHERLANDS = 4;
constexpr int kPlayerId = 7;
constexpr int NUM_CITY_RINGS = 3;
constexpr int MAX_MAJOR_CIVS = 18;
constexpr int GAMEOPTION_ONE_CITY_CHALLENGE = 1;

#define CvAssert(value) ((void)(value))

template <typename T>
constexpr T max(T left, T right) { return left > right ? left : right; }
template <typename T>
constexpr T min(T left, T right) { return left < right ? left : right; }

struct CvArea {
    int id = 0;
    int cities_per_player = 0;
    int getCitiesPerPlayer(PlayerTypes) const { return cities_per_player; }
    bool isWater() const { return false; }
};

static const Snapshot* active_snapshot = nullptr;
static std::array<CvArea, 1> active_areas{};

struct CvPlot {
    int index = 0;
    int getX() const { return index; }
    int getY() const { return 0; }
    bool isCity() const { return active_snapshot->tiles[static_cast<std::size_t>(index)].city; }
    PlayerTypes getOwner() const {
        const OwnerKind owner = active_snapshot->tiles[static_cast<std::size_t>(index)].owner;
        if (owner == OwnerKind::unowned) return NO_PLAYER;
        if (owner == OwnerKind::player) return kPlayerId;
        return active_snapshot->tiles[static_cast<std::size_t>(index)].city_owner_is_major
            ? kPlayerId + 1 : MAX_MAJOR_CIVS;
    }
    bool isNaturalWonder() const { return active_snapshot->tiles[static_cast<std::size_t>(index)].natural_wonder; }
    bool IsNaturalWonder() const { return isNaturalWonder(); }
    FeatureTypes getFeatureType() const {
        const Tile& tile = active_snapshot->tiles[static_cast<std::size_t>(index)];
        if (tile.forest) return FEATURE_FOREST;
        if (tile.jungle) return FEATURE_JUNGLE;
        if (tile.wetlands) return (index & 1) ? FEATURE_MARSH : FEATURE_FLOOD_PLAINS;
        return NO_FEATURE;
    }
    ImprovementTypes getImprovementType() const {
        return active_snapshot->tiles[static_cast<std::size_t>(index)].unimproved ? NO_IMPROVEMENT : 10;
    }
    ResourceTypes getResourceType() const {
        return active_snapshot->tiles[static_cast<std::size_t>(index)].desert_without_resource ? NO_RESOURCE : 10;
    }
    ResourceTypes getResourceType(TeamTypes) const {
        if (index == static_cast<int>(kCenterOffset))
            return active_snapshot->center_has_resource_for_team ? 10 : NO_RESOURCE;
        return getResourceType();
    }
    TerrainTypes getTerrainType() const {
        return active_snapshot->tiles[static_cast<std::size_t>(index)].desert_without_resource ? TERRAIN_DESERT : 0;
    }
    bool isHills() const { return active_snapshot->tiles[static_cast<std::size_t>(index)].hills; }
    int GetNumAdjacentMountains() const { return active_snapshot->tiles[static_cast<std::size_t>(index)].adjacent_mountains; }
    bool isRiver() const { return index == static_cast<int>(kCenterOffset) && active_snapshot->center_is_river; }
    bool isCoastalLand(int) const { return index == static_cast<int>(kCenterOffset) && active_snapshot->center_is_coastal; }
    CvArea* area() const { return &active_areas[0]; }
    int getArea() const { return active_snapshot->center_area; }
    bool isOwned() const { return getOwner() != NO_PLAYER; }
};

static std::array<CvPlot, kOffsetCount> active_plots{};
static CvPlot* plotXY(int, int, int dx, int dy) {
    if (dx < -kRadius || dx > kRadius || dy < -kRadius || dy > kRadius) return nullptr;
    const std::size_t index = static_cast<std::size_t>((dx + kRadius) * kDiameter + dy + kRadius);
    return active_snapshot->tiles[index].present ? &active_plots[index] : nullptr;
}
static int plotDistance(int, int, int x2, int) {
    return active_snapshot->tiles[static_cast<std::size_t>(x2)].distance;
}

struct FakeTraits {
    bool IsFaithFromUnimprovedForest() const { return active_snapshot->faith_from_unimproved_forest; }
    bool IsMoveFriendlyWoodsAsRoad() const { return active_snapshot->move_friendly_woods_as_road; }
    int GetNaturalWonderYieldModifier() const { return active_snapshot->gets_natural_wonder_yield_modifier ? 1 : 0; }
    bool WillGetUniqueLuxury(CvArea*) const { return active_snapshot->center_has_unique_luxury; }
};
struct FakeGrandStrategy {
    int GetPersonalityAndGrandStrategy(FlavorTypes flavor) const {
        if (flavor == 12) return active_snapshot->expansion_flavor;
        if (flavor == 13) return active_snapshot->growth_flavor;
        return active_snapshot->naval_flavor;
    }
};
struct FakeDiplomacy { int GetBoldness() const { return active_snapshot->boldness; } };
struct FakeCity { int getArea() const { return active_snapshot->capital_area; } };
struct FakeCivilization { bool isCoastalCiv() const { return active_snapshot->coastal_civilization; } };

class CvPlayer {
public:
    PlayerTypes GetID() const { return kPlayerId; }
    TeamTypes getTeam() const { return 2; }
    bool isHuman() const { return active_snapshot->human_player; }
    int getNumCities() const { return 0; }
    FakeTraits* GetPlayerTraits() { return &traits; }
    FakeGrandStrategy* GetGrandStrategyAI() { return &grand_strategy; }
    FakeDiplomacy* GetDiplomacyAI() { return &diplomacy; }
    FakeCity* getCapitalCity() { return active_snapshot->capital_present ? &capital : nullptr; }
    CivilizationTypes getCivilizationType() const {
        if (active_snapshot->is_inca) return CIV_INCA;
        if (active_snapshot->is_brazil) return CIV_BRAZIL;
        if (active_snapshot->is_morocco) return CIV_MOROCCO;
        if (active_snapshot->is_netherlands) return CIV_NETHERLANDS;
        return 0;
    }
    FakeCivilization getCivilizationInfo() const { return {}; }
    FakeTraits traits;
    FakeGrandStrategy grand_strategy;
    FakeDiplomacy diplomacy;
    FakeCity capital;
};

struct CvImprovementEntry {
    CivilizationTypes required_civilization = 0;
    bool IsSpecificCivRequired() const { return true; }
    CivilizationTypes GetRequiredCivilization() const { return required_civilization; }
};
struct FakeGlobals {
    bool final_initialized = true;
    bool game_option_occ = false;
    bool isFinalInitialized() const { return final_initialized; }
    bool isOption(int) const { return game_option_occ; }
    FakeGlobals& getGame() { return *this; }
    int getInfoTypeForString(const char* name, bool) const {
        const std::string value(name);
        if (value == "IMPROVEMENT_TERRACE_FARM") return IMPROVEMENT_TERRACE_FARM;
        if (value == "IMPROVEMENT_BRAZILWOOD_CAMP") return IMPROVEMENT_BRAZILWOOD_CAMP;
        if (value == "IMPROVEMENT_KASBAH") return IMPROVEMENT_KASBAH;
        if (value == "IMPROVEMENT_POLDER") return IMPROVEMENT_POLDER;
        return -1;
    }
    CvImprovementEntry* getImprovementInfo(ImprovementTypes improvement) {
        static CvImprovementEntry entries[5]{{}, {CIV_INCA}, {CIV_BRAZIL}, {CIV_MOROCCO}, {CIV_NETHERLANDS}};
        return improvement >= 1 && improvement <= 4 ? &entries[improvement] : nullptr;
    }
    int getSETTLER_FOOD_MULTIPLIER() const { return active_snapshot->settler_food_multiplier; }
    int getSETTLER_HAPPINESS_MULTIPLIER() const { return active_snapshot->settler_happiness_multiplier; }
    int getSETTLER_PRODUCTION_MULTIPLIER() const { return active_snapshot->settler_production_multiplier; }
    int getSETTLER_GOLD_MULTIPLIER() const { return active_snapshot->settler_gold_multiplier; }
    int getSETTLER_SCIENCE_MULTIPLIER() const { return active_snapshot->settler_science_multiplier; }
    int getSETTLER_FAITH_MULTIPLIER() const { return active_snapshot->settler_faith_multiplier; }
    int getSETTLER_RESOURCE_MULTIPLIER() const { return active_snapshot->settler_resource_multiplier; }
    int getSETTLER_STRATEGIC_MULTIPLIER() const { return active_snapshot->settler_strategic_multiplier; }
    int getBUILD_ON_RESOURCE_PERCENT() const { return active_snapshot->build_on_resource_percent; }
    int getBUILD_ON_RIVER_PERCENT() const { return active_snapshot->build_on_river_percent; }
    int getSETTLER_BUILD_ON_COAST_PERCENT() const { return active_snapshot->build_on_coast_percent; }
    int getMIN_WATER_SIZE_FOR_OCEAN() const { return active_snapshot->min_water_size_for_ocean; }
};
static FakeGlobals GC;

class CvCitySiteEvaluator {
public:
    virtual ~CvCitySiteEvaluator() = default;
    virtual bool CanFound(CvPlot* plot, const CvPlayer*, bool visible) const {
        (void)plot;
        return visible ? active_snapshot->center_can_found_visible : active_snapshot->center_can_found_full;
    }
    virtual int PlotFoundValue(CvPlot* plot, CvPlayer* player, YieldTypes yield = NO_YIELD, bool coast = true);
    int ComputeFoodValue(CvPlot* plot, CvPlayer*) { return active_snapshot->tiles[static_cast<std::size_t>(plot->index)].food_value; }
    int ComputeHappinessValue(CvPlot* plot, CvPlayer*) { return active_snapshot->tiles[static_cast<std::size_t>(plot->index)].happiness_value; }
    int ComputeProductionValue(CvPlot* plot, CvPlayer*) { return active_snapshot->tiles[static_cast<std::size_t>(plot->index)].production_value; }
    int ComputeGoldValue(CvPlot* plot, CvPlayer*) { return active_snapshot->tiles[static_cast<std::size_t>(plot->index)].gold_value; }
    int ComputeScienceValue(CvPlot* plot, CvPlayer*) { return active_snapshot->tiles[static_cast<std::size_t>(plot->index)].science_value; }
    int ComputeFaithValue(CvPlot* plot, CvPlayer*) { return active_snapshot->tiles[static_cast<std::size_t>(plot->index)].faith_value; }
    int ComputeTradeableResourceValue(CvPlot* plot, CvPlayer*) { return active_snapshot->tiles[static_cast<std::size_t>(plot->index)].resource_value; }
    int ComputeStrategicValue(CvPlot* plot, CvPlayer*, int) { return active_snapshot->tiles[static_cast<std::size_t>(plot->index)].strategic_value; }

    int m_iFlavorMultiplier[16]{};
    int m_iRingModifier[16]{};
    int m_iExpansionIndex = 12;
    int m_iGrowthIndex = 13;
    int m_iNavalIndex = 14;
    int m_iBrazilMultiplier = 1000;
    int m_iSpainMultiplier = 55000;
    int m_iMorrocoMultiplier = 1000;
    int m_iNetherlandsMultiplier = 2000;
    int m_iIncaMultiplier = 500;
};

class CvSiteEvaluatorForSettler : public CvCitySiteEvaluator {
public:
    int PlotFoundValue(CvPlot* plot, CvPlayer* player, YieldTypes yield = NO_YIELD, bool coast = true);
};

// The verifier inserts the byte-faithful SDK bodies at this marker.
// FOUND_VALUE_ORIGINAL_FUNCTION_BODIES

static void activate(const Snapshot& snapshot, CvCitySiteEvaluator& evaluator) {
    active_snapshot = &snapshot;
    for (std::size_t index = 0; index < kOffsetCount; ++index) active_plots[index].index = static_cast<int>(index);
    for (std::size_t index = 0; index < kDistanceCount; ++index)
        evaluator.m_iRingModifier[index] = snapshot.ring_modifier[index];
    evaluator.m_iFlavorMultiplier[YIELD_FAITH] = snapshot.faith_flavor_multiplier;
    evaluator.m_iBrazilMultiplier = snapshot.brazil_multiplier;
    evaluator.m_iSpainMultiplier = snapshot.spain_multiplier;
    evaluator.m_iMorrocoMultiplier = snapshot.morocco_multiplier;
    evaluator.m_iNetherlandsMultiplier = snapshot.netherlands_multiplier;
    evaluator.m_iIncaMultiplier = snapshot.inca_multiplier;
    active_areas[0].id = snapshot.center_area;
    active_areas[0].cities_per_player = 1;
}

static Snapshot make_base_snapshot() {
    Snapshot result{};
    result.path = Path::settler_no_yield_no_coast_only;
    result.valid = true;
    result.has_player = true;
    result.center_present = true;
    result.capital_present = true;
    result.center_can_found_visible = true;
    result.center_can_found_full = true;
    result.center_area = 1;
    result.capital_area = 1;
    result.min_city_range = 3;
    result.min_water_size_for_ocean = 10;
    result.major_civ_count = 18;
    result.ring_modifier = {{1, 6, 3, 2, 1, 1, 0, 0}};
    result.settler_food_multiplier = 15;
    result.settler_happiness_multiplier = 6;
    result.settler_production_multiplier = 3;
    result.settler_gold_multiplier = 2;
    result.settler_science_multiplier = 1;
    result.settler_faith_multiplier = 1;
    result.settler_resource_multiplier = 1;
    result.settler_strategic_multiplier = 1;
    result.build_on_resource_percent = -50;
    result.build_on_river_percent = 15;
    result.build_on_coast_percent = 40;
    result.brazil_multiplier = 1000;
    result.spain_multiplier = 55000;
    result.morocco_multiplier = 1000;
    result.netherlands_multiplier = 2000;
    result.inca_multiplier = 500;
    result.tiles[kCenterOffset].present = true;
    result.tiles[kCenterOffset].distance = 0;
    result.tiles[kCenterOffset].owner = OwnerKind::unowned;
    return result;
}

static void set_tile(Snapshot& value, int dx, int dy, int distance, const Tile& tile) {
    const std::size_t index = static_cast<std::size_t>((dx + kRadius) * kDiameter + dy + kRadius);
    value.tiles[index] = tile;
    value.tiles[index].present = true;
    value.tiles[index].distance = distance;
}

static bool source_oracle(const Snapshot& snapshot, std::int32_t& result) {
    CvSiteEvaluatorForSettler settler;
    CvPlayer player;
    activate(snapshot, settler);
    CvPlot* center = &active_plots[kCenterOffset];
    const int base_value = settler.CvCitySiteEvaluator::PlotFoundValue(center, &player, NO_YIELD, false);
    const int value = settler.PlotFoundValue(center, &player, NO_YIELD, false);
    const std::int64_t expected_wrapper = snapshot.center_has_unique_luxury
        ? static_cast<std::int64_t>(base_value) * 2 : base_value;
    if (expected_wrapper != value) {
        std::fprintf(stderr, "ORACLE_WRAPPER_MISMATCH base=%d wrapper=%d unique=%d\n",
                     base_value, value, snapshot.center_has_unique_luxury ? 1 : 0);
        return false;
    }
    if (snapshot.center_can_found_visible && snapshot.center_can_found_full) result = value;
    else result = 0;
    return true;
}

static std::uint32_t check_count = 0;
static bool compare_case(const char* name, const Snapshot& snapshot) {
    std::int32_t oracle = 0;
    if (!source_oracle(snapshot, oracle)) return false;
    const Result result = evaluate(snapshot);
    if (result.status != Status::ok || result.score != oracle) {
        std::fprintf(stderr, "CASE_FAIL name=%s status=%u kernel=%d oracle=%d\n",
                     name, static_cast<unsigned>(result.status), result.score, oracle);
        return false;
    }
    ++check_count;
    return true;
}

static bool check_atomic_overflow(const char* name, Snapshot snapshot) {
    const Result result = evaluate(snapshot);
    if (result.status != Status::overflow || result.score != 0) {
        std::fprintf(stderr, "OVERFLOW_FAIL name=%s status=%u score=%d\n",
                     name, static_cast<unsigned>(result.status), result.score);
        return false;
    }
    ++check_count;
    return true;
}

static std::uint32_t random_state = 0x72a2f11du;
static std::uint32_t next_random() {
    random_state ^= random_state << 13;
    random_state ^= random_state >> 17;
    random_state ^= random_state << 5;
    return random_state;
}

static Snapshot random_snapshot() {
    Snapshot value = make_base_snapshot();
    value.human_player = (next_random() & 1u) != 0;
    value.faith_from_unimproved_forest = (next_random() & 7u) == 0;
    value.move_friendly_woods_as_road = !value.faith_from_unimproved_forest && (next_random() & 7u) == 0;
    value.gets_natural_wonder_yield_modifier = !value.faith_from_unimproved_forest && !value.move_friendly_woods_as_road && (next_random() & 7u) == 0;
    switch (next_random() % 5u) {
    case 1: value.is_inca = true; break;
    case 2: value.is_brazil = true; break;
    case 3: value.is_morocco = true; break;
    case 4: value.is_netherlands = true; break;
    default: break;
    }
    value.faith_flavor_multiplier = static_cast<int>(next_random() % 24u);
    value.center_has_resource_for_team = (next_random() & 3u) == 0;
    value.center_is_river = (next_random() & 3u) == 0;
    value.center_is_coastal = (next_random() & 3u) == 0;
    value.coastal_civilization = (next_random() & 3u) == 0;
    value.center_has_unique_luxury = (next_random() & 7u) == 0;
    value.growth_flavor = static_cast<int>(next_random() % 13u);
    value.expansion_flavor = static_cast<int>(next_random() % 13u);
    value.naval_flavor = static_cast<int>(next_random() % 13u);
    value.boldness = static_cast<int>(next_random() % 11u);
    value.center_area = (next_random() & 1u) ? 1 : 2;
    value.capital_area = (next_random() & 1u) ? 1 : 2;
    for (int dx = -kRadius; dx <= kRadius; ++dx) {
        for (int dy = -kRadius; dy <= kRadius; ++dy) {
            const int distance = (std::abs(dx) + std::abs(dy) + std::abs(dx + dy)) / 2;
            if (distance == 0 || distance > 7 || (next_random() % 4u) == 0) continue;
            Tile tile{};
            tile.owner = static_cast<OwnerKind>(next_random() % 3u);
            tile.city = (next_random() % 31u) == 0;
            tile.city_owner_is_major = (next_random() & 1u) != 0;
            tile.food_value = static_cast<int>(next_random() % 31u) - 8;
            tile.production_value = static_cast<int>(next_random() % 21u) - 5;
            tile.gold_value = static_cast<int>(next_random() % 15u) - 4;
            tile.science_value = static_cast<int>(next_random() % 10u) - 2;
            tile.faith_value = static_cast<int>(next_random() % 8u) - 1;
            tile.happiness_value = static_cast<int>(next_random() % 8u) - 1;
            tile.resource_value = static_cast<int>(next_random() % 12u) - 2;
            tile.strategic_value = static_cast<int>(next_random() % 12u) - 3;
            tile.forest = (next_random() % 9u) == 0;
            tile.jungle = !tile.forest && (next_random() % 13u) == 0;
            tile.wetlands = !tile.forest && !tile.jungle && (next_random() % 17u) == 0;
            tile.natural_wonder = (next_random() % 41u) == 0;
            if (tile.natural_wonder) {
                tile.forest = false;
                tile.jungle = false;
                tile.wetlands = false;
            }
            tile.desert_without_resource = (next_random() % 7u) == 0;
            tile.hills = (next_random() & 1u) != 0;
            tile.adjacent_mountains = static_cast<int>(next_random() % 7u);
            tile.unimproved = (next_random() & 1u) != 0;
            set_tile(value, dx, dy, distance, tile);
        }
    }
    return value;
}

struct WorkerResult { Result result; };
static std::vector<Result> evaluate_parallel(const std::vector<Snapshot>& snapshots, unsigned worker_count) {
    std::vector<Result> results(snapshots.size());
    std::atomic<std::size_t> next{0};
    std::vector<std::thread> workers;
    for (unsigned worker = 0; worker < worker_count; ++worker) {
        workers.emplace_back([&] {
            for (;;) {
                const std::size_t index = next.fetch_add(1, std::memory_order_relaxed);
                if (index >= snapshots.size()) break;
                results[index] = evaluate(snapshots[index]);
            }
        });
    }
    for (auto& worker : workers) worker.join();
    return results;
}

int main() {
    Snapshot base = make_base_snapshot();
    Tile tile{};
    tile.food_value = 2; tile.production_value = 1; tile.gold_value = 3;
    tile.science_value = 1; tile.faith_value = 1; tile.happiness_value = 2;
    tile.resource_value = 3;
    tile.strategic_value = 5;
    tile.owner = OwnerKind::unowned;
    set_tile(base, 1, 0, 1, tile);
    tile.owner = OwnerKind::player;
    tile.city = true;
    set_tile(base, 0, 1, 1, tile);
    if (!compare_case("base_order_and_friendly_city", base)) return 1;

    Snapshot foreign = make_base_snapshot();
    tile = {}; tile.owner = OwnerKind::other; tile.city = true; tile.city_owner_is_major = true;
    tile.food_value = 10; tile.natural_wonder = true;
    set_tile(foreign, -1, 0, 1, tile);
    tile.owner = OwnerKind::unowned; tile.city = false; tile.natural_wonder = false;
    tile.food_value = 2; tile.production_value = 2;
    set_tile(foreign, 1, 0, 1, tile);
    foreign.boldness = 2;
    if (!compare_case("foreign_owner_enemy_city", foreign)) return 2;

    Snapshot minor_foreign = make_base_snapshot();
    minor_foreign.boldness = 2;
    tile = {}; tile.owner = OwnerKind::other; tile.city = true;
    tile.city_owner_is_major = false;
    set_tile(minor_foreign, -1, 0, 1, tile);
    if (!compare_case("foreign_minor_city_not_enemy", minor_foreign)) return 23;

    Snapshot wonder = make_base_snapshot();
    tile = {}; tile.owner = OwnerKind::unowned; tile.natural_wonder = true; tile.food_value = 2;
    set_tile(wonder, 2, -1, 3, tile);
    wonder.gets_natural_wonder_yield_modifier = true;
    if (!compare_case("natural_wonder_and_spain", wonder)) return 3;

    Snapshot traits = make_base_snapshot();
    traits.is_inca = true;
    traits.faith_from_unimproved_forest = true;
    traits.faith_flavor_multiplier = 12;
    for (int dx = -1; dx <= 1; ++dx) {
        tile = {}; tile.owner = OwnerKind::unowned; tile.forest = true; tile.unimproved = true;
        tile.hills = true; tile.adjacent_mountains = 2; tile.faith_value = 1;
        set_tile(traits, dx, 1, 1, tile);
    }
    if (!compare_case("civ_traits_and_forest", traits)) return 4;

    Snapshot one_forest = make_base_snapshot();
    one_forest.faith_from_unimproved_forest = true;
    one_forest.faith_flavor_multiplier = 12;
    tile = {}; tile.owner = OwnerKind::unowned; tile.forest = true; tile.unimproved = true;
    set_tile(one_forest, 1, 0, 1, tile);
    if (!compare_case("single_celtic_forest_flavor", one_forest)) return 19;

    Snapshot faith_carry = make_base_snapshot();
    tile = {}; tile.owner = OwnerKind::unowned; tile.faith_value = 2;
    set_tile(faith_carry, -1, 0, 1, tile);
    tile = {}; tile.owner = OwnerKind::unowned;
    set_tile(faith_carry, 0, 4, 4, tile);
    set_tile(faith_carry, 0, 5, 5, tile);
    if (!compare_case("source_faith_carry_distance4_5", faith_carry)) return 24;

    Snapshot brazil = make_base_snapshot();
    brazil.is_brazil = true;
    tile = {}; tile.owner = OwnerKind::unowned; tile.jungle = true; tile.food_value = 1;
    set_tile(brazil, 1, 0, 1, tile);
    if (!compare_case("brazil_jungle_trait", brazil)) return 20;
    Snapshot morocco = make_base_snapshot();
    morocco.is_morocco = true;
    tile = {}; tile.owner = OwnerKind::unowned; tile.desert_without_resource = true; tile.food_value = 1;
    set_tile(morocco, 1, 0, 1, tile);
    if (!compare_case("morocco_desert_trait", morocco)) return 21;
    Snapshot netherlands = make_base_snapshot();
    netherlands.is_netherlands = true;
    tile = {}; tile.owner = OwnerKind::unowned; tile.wetlands = true; tile.food_value = 1;
    set_tile(netherlands, 1, 0, 1, tile);
    if (!compare_case("netherlands_wetland_trait", netherlands)) return 22;

    Snapshot coast_river = make_base_snapshot();
    coast_river.center_has_resource_for_team = true;
    coast_river.center_is_river = true; coast_river.center_is_coastal = true;
    coast_river.coastal_civilization = true; coast_river.naval_flavor = 8;
    tile = {}; tile.owner = OwnerKind::unowned; tile.food_value = 1; tile.gold_value = 3;
    set_tile(coast_river, 1, 0, 1, tile);
    if (!compare_case("river_coast_resource", coast_river)) return 5;

    Snapshot missing = make_base_snapshot();
    missing.center_present = false;
    if (evaluate(missing).status != Status::invalid_snapshot) return 6;
    ++check_count;
    Snapshot cannot_found = make_base_snapshot();
    cannot_found.center_can_found_full = false;
    if (!compare_case("can_found_false", cannot_found)) return 7;
    Snapshot visible_false = make_base_snapshot();
    visible_false.center_can_found_visible = false;
    if (!compare_case("visible_can_found_false", visible_false)) return 8;
    Snapshot unsupported = make_base_snapshot();
    unsupported.path = Path::other;
    if (evaluate(unsupported).status != Status::unsupported_path) return 9;
    ++check_count;

    Snapshot negative = make_base_snapshot();
    tile = {}; tile.owner = OwnerKind::unowned; tile.food_value = -10;
    tile.production_value = -8; tile.science_value = -3;
    set_tile(negative, 1, 0, 1, tile);
    if (!compare_case("negative_clamp", negative)) return 10;

    Snapshot truncation = make_base_snapshot();
    truncation.build_on_coast_percent = 33; truncation.center_is_coastal = true;
    truncation.center_area = 2; truncation.capital_area = 1;
    truncation.growth_flavor = 8; truncation.expansion_flavor = 8;
    tile = {}; tile.owner = OwnerKind::unowned; tile.food_value = 1; tile.production_value = 1;
    set_tile(truncation, 1, 0, 1, tile);
    if (!compare_case("division_truncation_order", truncation)) return 11;

    Snapshot no_capital = make_base_snapshot();
    no_capital.capital_present = false;
    no_capital.capital_area = 0; // Mirrors the source's NULL-initialized iCapitalArea.
    no_capital.center_area = 1;
    tile = {}; tile.owner = OwnerKind::unowned; tile.food_value = 2;
    set_tile(no_capital, 1, 0, 1, tile);
    tile = {}; tile.owner = OwnerKind::player; tile.city = true;
    set_tile(no_capital, -3, 3, 6, tile);
    if (!compare_case("missing_capital_zero_area_sentinel", no_capital)) return 16;
    Snapshot inconsistent_no_capital = make_base_snapshot();
    inconsistent_no_capital.capital_present = false;
    inconsistent_no_capital.capital_area = 1;
    if (evaluate(inconsistent_no_capital).status != Status::invalid_snapshot) return 17;
    ++check_count;

    Snapshot overflow = make_base_snapshot();
    overflow.settler_food_multiplier = (std::numeric_limits<std::int32_t>::max)();
    overflow.ring_modifier[1] = 2; tile = {}; tile.owner = OwnerKind::unowned;
    tile.food_value = (std::numeric_limits<std::int32_t>::max)();
    set_tile(overflow, 1, 0, 1, tile);
    if (!check_atomic_overflow("multiply_atomicity", overflow)) return 12;
    Snapshot overflow_late = make_base_snapshot();
    tile = {}; tile.owner = OwnerKind::unowned; tile.food_value = 1;
    set_tile(overflow_late, 1, 0, 1, tile);
    overflow_late.center_is_coastal = true;
    overflow_late.build_on_coast_percent = (std::numeric_limits<std::int32_t>::max)();
    overflow_late.tiles[kCenterOffset].food_value = (std::numeric_limits<std::int32_t>::max)();
    if (!check_atomic_overflow("late_adjustment_atomicity", overflow_late)) return 13;

    std::vector<Snapshot> random_cases;
    random_cases.reserve(512);
    for (int index = 0; index < 512; ++index) random_cases.push_back(random_snapshot());
    const auto parallel = evaluate_parallel(random_cases, 4);
    for (std::size_t index = 0; index < random_cases.size(); ++index) {
        std::int32_t oracle = 0;
        if (!source_oracle(random_cases[index], oracle)) return 18;
        const Result serial = evaluate(random_cases[index]);
        if (serial.status != parallel[index].status || serial.score != parallel[index].score) return 14;
        if (serial.status == Status::ok && serial.score != oracle) {
            std::fprintf(stderr, "RANDOM_ORACLE_FAIL index=%zu kernel=%d oracle=%d human=%d civ=%d%d%d%d nw=%d faith_trait=%d faith_flavor=%d unique=%d resource=%d river=%d coast=%d naval=%d growth=%d expansion=%d bold=%d area=%d/%d\n",
                         index, serial.score, oracle, random_cases[index].human_player ? 1 : 0,
                         random_cases[index].is_inca ? 1 : 0, random_cases[index].is_brazil ? 1 : 0,
                         random_cases[index].is_morocco ? 1 : 0, random_cases[index].is_netherlands ? 1 : 0,
                         random_cases[index].gets_natural_wonder_yield_modifier ? 1 : 0,
                         random_cases[index].faith_from_unimproved_forest ? 1 : 0,
                         random_cases[index].faith_flavor_multiplier,
                         random_cases[index].center_has_unique_luxury ? 1 : 0,
                         random_cases[index].center_has_resource_for_team ? 1 : 0,
                         random_cases[index].center_is_river ? 1 : 0,
                         random_cases[index].center_is_coastal ? 1 : 0,
                         random_cases[index].naval_flavor, random_cases[index].growth_flavor,
                         random_cases[index].expansion_flavor, random_cases[index].boldness,
                         random_cases[index].capital_area, random_cases[index].center_area);
            return 15;
        }
        ++check_count;
    }

    std::printf("FOUND_VALUE_SCORES_PASS checks=%u candidates=%u workers=4 GAMECORE_LOADED=false SOURCE_ORACLE=EXTRACTED\n",
                check_count, static_cast<unsigned>(random_cases.size()));
    return 0;
}
