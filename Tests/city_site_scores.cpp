#include "CitySiteScores.h"
#include "OrderedBatch.h"

#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <utility>
#include <vector>

enum YieldTypes { YIELD_FOOD = 0, YIELD_PRODUCTION = 1, YIELD_GOLD = 2, YIELD_SCIENCE = 3 };
constexpr int CITY_HOME_PLOT = 0;
constexpr int NO_RESOURCE = -1;
constexpr int NO_FEATURE = -1;
constexpr int NO_IMPROVEMENT = -1;

struct CvPlot {
    bool exists = true;
    int x = 0;
    int ring_distance = 0;
    std::array<int, 4> yields{};
    bool owned = false;
    int owner = -1;
    int resource = NO_RESOURCE;
    int feature = NO_FEATURE;
    bool hills = false;
    int improvement = NO_IMPROVEMENT;
    int getX() const { return x; }
    int getY() const { return 0; }
    int getYield(YieldTypes yield) const { return yields[static_cast<std::size_t>(yield)]; }
    bool isOwned() const { return owned; }
    int getOwner() const { return owner; }
    int getResourceType() const { return resource; }
    int getFeatureType() const { return feature; }
    bool isHills() const { return hills; }
    int getImprovementType() const { return improvement; }
};

struct FakePlayer { int id = 0; int GetID() const { return id; } };
struct FakeGlobals {
    int count = 18;
    int first = 4;
    int second = 2;
    int third = 1;
    int getAI_CITY_SPECIALIZATION_YIELD_NUM_TILES_CONSIDERED() const { return count; }
    int getAI_CITY_SPECIALIZATION_YIELD_WEIGHT_FIRST_RING() const { return first; }
    int getAI_CITY_SPECIALIZATION_YIELD_WEIGHT_SECOND_RING() const { return second; }
    int getAI_CITY_SPECIALIZATION_YIELD_WEIGHT_THIRD_RING() const { return third; }
};

static FakeGlobals GC;
static std::vector<CvPlot>* active_plots = nullptr;
static CvPlot* plotCity(int, int, int index) {
    if (active_plots == nullptr || index < 0 || static_cast<std::size_t>(index) >= active_plots->size()) return nullptr;
    CvPlot* plot = &(*active_plots)[static_cast<std::size_t>(index)];
    return plot->exists ? plot : nullptr;
}
static int plotDistance(int x1, int, int x2, int) { return std::abs(x1 - x2); }

class CvCitySpecializationAI {
public:
    FakePlayer* m_pPlayer = nullptr;
    int PlotValueForSpecificYield(CvPlot* pPlot, YieldTypes eYield);
    int PlotValueForScience(CvPlot* pPlot);
};

// The verifier inserts the two exact definitions extracted from the current SDK source here.
// CITY_SITE_ORIGINAL_HELPERS

struct Case {
    zerosis::city_site::SiteInput input;
    std::vector<CvPlot> plots;
    int tile_count = 0;
    int player_id = 7;
    std::array<int, 3> weights{{4, 2, 1}};
};

static Case make_case(const zerosis::city_site::SiteInput& input, int count,
                      std::array<int, 3> weights, int player_id = 7) {
    Case value;
    value.input = input;
    value.tile_count = count;
    value.weights = weights;
    value.player_id = player_id;
    value.plots.resize(static_cast<std::size_t>(count));
    for (int index = 0; index < count; ++index) {
        const auto& source = input.cells[static_cast<std::size_t>(index)];
        auto& target = value.plots[static_cast<std::size_t>(index)];
        target.exists = source.present || index == CITY_HOME_PLOT;
        target.ring_distance = source.ring_distance;
        target.x = index == CITY_HOME_PLOT ? 0 : source.ring_distance;
        target.yields = {{source.yields[0], source.yields[1], source.yields[2], source.yields[3]}};
        target.owned = source.foreign_owned;
        target.owner = source.foreign_owned ? player_id + 1 : player_id;
        target.resource = source.science_clear ? NO_RESOURCE : 0;
        target.feature = source.science_clear ? NO_FEATURE : 0;
        target.hills = !source.science_clear;
        target.improvement = source.science_clear ? NO_IMPROVEMENT : 0;
    }
    return value;
}

static void activate(Case& value, CvCitySpecializationAI& ai, FakePlayer& player) {
    GC.count = value.tile_count;
    GC.first = value.weights[0]; GC.second = value.weights[1]; GC.third = value.weights[2];
    player.id = value.player_id;
    ai.m_pPlayer = &player;
    active_plots = &value.plots;
}

static std::uint32_t random_state = 0x9e3779b9u;
static std::uint32_t next_random() {
    random_state ^= random_state << 13; random_state ^= random_state >> 17; random_state ^= random_state << 5;
    return random_state;
}

static Case random_case(int count) {
    zerosis::city_site::SiteInput input{};
    input.tile_count = static_cast<std::uint32_t>(count);
    std::array<int, 3> weights{{static_cast<int>(next_random() % 15) - 5,
                                static_cast<int>(next_random() % 15) - 5,
                                static_cast<int>(next_random() % 15) - 5}};
    input.ring_weights = {{weights[0], weights[1], weights[2]}};
    for (int index = 0; index < count; ++index) {
        auto& cell = input.cells[static_cast<std::size_t>(index)];
        cell.present = (next_random() % 5) != 0;
        cell.ring_distance = static_cast<int>(next_random() % 6); // includes unsupported 0, 4, 5
        for (auto& yield : cell.yields) yield = static_cast<int>(next_random() % 31) - 15;
        cell.foreign_owned = (next_random() % 6) == 0;
        const bool no_resource = (next_random() % 2) == 0;
        const bool no_feature = (next_random() % 2) == 0;
        const bool not_hills = (next_random() % 2) == 0;
        const bool no_improvement = (next_random() % 2) == 0;
        cell.science_clear = no_resource && no_feature && not_hills && no_improvement;
    }
    return make_case(input, count, weights);
}

struct SiteValues { std::array<int, 4> values{}; };
struct ScoreOperation {
    SiteValues operator()(const Case& value, const zerosis::concurrency::CancellationToken&) const {
        const auto scored = zerosis::city_site::evaluate_all(value.input);
        if (scored.status != zerosis::city_site::Status::ok) throw 1;
        return {scored.values};
    }
};

int main() {
    using namespace zerosis::city_site;
    using namespace zerosis::concurrency;
    std::uint32_t checks = 0;
    CvCitySpecializationAI ai;
    FakePlayer player;
    std::vector<Case> cases;

    // Explicit edge cases: absent cells preserve multiplier, unsupported rings preserve it,
    // foreign ownership resets it, and science-clear is the conjunction of all four fields.
    for (int distance = 0; distance <= 5; ++distance) {
        SiteInput input{}; input.tile_count = 5; input.ring_weights = {{7, -3, 5}};
        input.cells[1] = {true, 1, {{-4, 2, 3, -1}}, false, false};
        input.cells[2] = {false, 2, {{99, 99, 99, 99}}, false, true};
        input.cells[3] = {true, distance, {{6, -5, 0, 4}}, false, true};
        input.cells[4] = {true, 2, {{3, 1, -2, 5}}, true, true};
        cases.push_back(make_case(input, 5, {{7, -3, 5}}));
    }
    for (int mask = 0; mask < 16; ++mask) {
        SiteInput input{}; input.tile_count = 2; input.ring_weights = {{3, 2, 1}};
        input.cells[1] = {true, 1, {{2, -1, 4, 3}}, false, mask == 15};
        Case test = make_case(input, 2, {{3, 2, 1}});
        CvPlot& plot = test.plots[1];
        plot.resource = (mask & 1) ? NO_RESOURCE : 0;
        plot.feature = (mask & 2) ? NO_FEATURE : 0;
        plot.hills = (mask & 4) == 0;
        plot.improvement = (mask & 8) ? NO_IMPROVEMENT : 0;
        test.input.cells[1].science_clear = mask == 15;
        cases.push_back(std::move(test));
    }
    for (int count = 0; count <= 18; ++count) cases.push_back(random_case(count));
    for (int index = 0; index < 600; ++index) cases.push_back(random_case(1 + static_cast<int>(next_random() % 18)));

    std::vector<Job<Case>> jobs;
    for (std::size_t index = 0; index < cases.size(); ++index) jobs.push_back({index, cases[index]});
    const auto serial = evaluate_ordered(BatchStamp{1, 2, 3, 4, 5}, jobs, 1, ScoreOperation{});
    const auto parallel = evaluate_ordered(BatchStamp{1, 2, 3, 4, 5}, std::move(jobs), 4, ScoreOperation{});
    if (serial.status != BatchStatus::ready || parallel.status != BatchStatus::ready ||
        serial.rows.size() != cases.size() || parallel.rows.size() != cases.size() ||
        serial.workers_started != 1 || parallel.workers_started != 4 ||
        serial.jobs_started != cases.size() || serial.jobs_completed != cases.size() ||
        parallel.jobs_started != cases.size() || parallel.jobs_completed != cases.size()) return 2;

    for (std::size_t case_index = 0; case_index < cases.size(); ++case_index) {
        Case& test = cases[case_index]; activate(test, ai, player);
        CvPlot* center = test.plots.empty() ? nullptr : &test.plots[CITY_HOME_PLOT];
        const auto& actual = parallel.rows[case_index].value;
        const auto& serial_actual = serial.rows[case_index].value;
        const auto combined = evaluate_all(test.input);
        if (combined.status != Status::ok) return 3;
        for (std::size_t yield = 0; yield < 3; ++yield) {
            int oracle = center == nullptr ? 0 : ai.PlotValueForSpecificYield(center, static_cast<YieldTypes>(yield));
            const auto candidate = evaluate(test.input, yield);
            if (candidate.status != Status::ok || candidate.specific_yield_value != oracle ||
                combined.values[yield] != oracle || actual.values[yield] != oracle ||
                serial_actual.values[yield] != oracle) return 3;
            ++checks;
        }
        int science_oracle = center == nullptr ? 0 : ai.PlotValueForScience(center);
        const auto science_candidate = evaluate(test.input, 0);
        if (science_candidate.status != Status::ok || science_candidate.science_value != science_oracle ||
            combined.values[3] != science_oracle || actual.values[3] != science_oracle ||
            serial_actual.values[3] != science_oracle) return 4;
        ++checks;
    }

    // A kernel result is only defined when every original signed-int intermediate fits.
    SiteInput overflow{}; overflow.tile_count = 2; overflow.ring_weights = {{4, 2, 1}};
    overflow.cells[1] = {true, 1, {{(std::numeric_limits<std::int32_t>::max)(), 0, 0, 0}}, false, false};
    if (evaluate(overflow, 0).status != Status::overflow ||
        evaluate_all(overflow).status != Status::overflow) return 5;
    ++checks;
    SiteInput invalid{}; invalid.tile_count = static_cast<std::uint32_t>(kMaxTiles + 1);
    if (evaluate(invalid, 0).status != Status::invalid_input ||
        evaluate_all(invalid).status != Status::invalid_input) return 6;
    ++checks;

    std::printf("CITY_SITE_SCORES_PASS checks=%u jobs=%u serial_workers_started=%u workers_started=%u GAMECORE_LOADED=false\n",
                checks, static_cast<unsigned>(parallel.jobs_completed),
                static_cast<unsigned>(serial.workers_started),
                static_cast<unsigned>(parallel.workers_started));
    return 0;
}
