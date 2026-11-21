// The verifier injects the exact prepared FindBestSites/helper bodies into this
// source template. SDK types and the bridge are source-shaped mocks; no GameCore
// module is loaded and no native SDK state is changed.
#include "CitySiteScoreBridge.h"

#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

enum YieldTypes { YIELD_FOOD = 0, YIELD_PRODUCTION = 1, YIELD_GOLD = 2, YIELD_SCIENCE = 3 };
static const int CITY_HOME_PLOT = 0;
static const int NO_RESOURCE = -1;
static const int NO_FEATURE = -1;
static const int NO_IMPROVEMENT = -1;
static const int NO_TEAM = -1;

struct CvPlot {
    int id = -1;
    int x = 0;
    int y = 0;
    int owner = -1;
    int resource = NO_RESOURCE;
    int feature = NO_FEATURE;
    int improvement = NO_IMPROVEMENT;
    bool hills = false;
    std::array<int, 4> yields{{0, 0, 0, 0}};
    int getX() const { return x; }
    int getY() const { return y; }
    int getYield(YieldTypes value) const { return yields[static_cast<std::size_t>(value)]; }
    bool isOwned() const { return owner != -1; }
    int getOwner() const { return owner; }
    int getResourceType() const { return resource; }
    int getFeatureType() const { return feature; }
    bool isHills() const { return hills; }
    int getImprovementType() const { return improvement; }
};

struct CvPlayer {
    int id = 0;
    int cities = 1;
    int GetID() const { return id; }
    int getNumCities() const { return cities; }
};

struct CvCity { int x = 0; int y = 0; int getX() const { return x; } int getY() const { return y; } };

struct MockDll {
    bool owner_thread = true;
    bool lock_held = true;
    int owner_queries = 0;
    int lock_queries = 0;
    bool IsGameCoreThread() { ++owner_queries; return owner_thread; }
    bool HasGameCoreLock() { ++lock_queries; return lock_held; }
};
static MockDll g_dll;
static MockDll* gDLL = &g_dll;

struct MockMap {
    std::array<CvPlot, 4> sites{};
    std::array<std::array<CvPlot, ZEROSIS_CITY_SITE_MAX_TILES>, 4> cells{};
    CvCity nearest_city{};
    int site_count = 3;
    int reads = 0;
    int eligibility_calls = 0;
    int numPlots() { ++reads; return site_count; }
    CvPlot* plotByIndexUnchecked(int index) { ++reads; return index >= 0 && index < site_count ? &sites[index] : NULL; }
    CvCity* findCity(int, int, int, int, bool) { ++reads; return &nearest_city; }
    CvPlot* cellFor(int site, int cell) {
        return site >= 0 && site < 4 && cell >= 0 && cell < ZEROSIS_CITY_SITE_MAX_TILES
            ? &cells[static_cast<std::size_t>(site)][static_cast<std::size_t>(cell)] : NULL;
    }
};
static MockMap g_map;

struct CvSiteEvaluatorForSettler {
    bool CanFound(CvPlot* plot, CvPlayer*, bool) { ++g_map.eligibility_calls; return plot != NULL; }
};
static CvSiteEvaluatorForSettler g_site_evaluator;

struct MockGame {
    int turn = 7;
    CvSiteEvaluatorForSettler* GetSettlerSiteEvaluator() { return &g_site_evaluator; }
    int getGameTurn() const { return turn; }
};
static MockGame g_game;

struct MockGC {
    int tile_count = 4;
    std::array<int, 3> weights{{3, 2, 1}};
    int reads = 0;
    int getAI_CITY_SPECIALIZATION_YIELD_NUM_TILES_CONSIDERED() { ++reads; return tile_count; }
    int getAI_CITY_SPECIALIZATION_YIELD_WEIGHT_FIRST_RING() { ++reads; return weights[0]; }
    int getAI_CITY_SPECIALIZATION_YIELD_WEIGHT_SECOND_RING() { ++reads; return weights[1]; }
    int getAI_CITY_SPECIALIZATION_YIELD_WEIGHT_THIRD_RING() { ++reads; return weights[2]; }
    int getSETTLER_EVALUATION_DISTANCE() { ++reads; return 20; }
    MockMap& getMap() { ++reads; return g_map; }
    MockGame& getGame() { ++reads; return g_game; }
};
static MockGC GC;

static int plotDistance(int x1, int y1, int x2, int y2) {
    const int dx = x1 > x2 ? x1 - x2 : x2 - x1;
    const int dy = y1 > y2 ? y1 - y2 : y2 - y1;
    return dx + dy;
}

static CvPlot* plotCity(int x, int y, int index) {
    for (int site = 0; site < g_map.site_count; ++site) {
        if (g_map.sites[static_cast<std::size_t>(site)].x == x &&
            g_map.sites[static_cast<std::size_t>(site)].y == y)
            return g_map.cellFor(site, index);
    }
    return NULL;
}

struct TrackedValues {
    struct Slot {
        TrackedValues* owner;
        int index;
        operator int() const { return owner->values[static_cast<std::size_t>(index)]; }
        Slot& operator=(int value) {
            owner->values[static_cast<std::size_t>(index)] = value;
            ++owner->writes;
            return *this;
        }
    };
    std::array<int, 4> values{{0, 0, 0, 0}};
    int writes = 0;
    Slot operator[](int index) { return Slot{this, index}; }
};

static CvPlayer g_player;
static int g_log_best_sites_calls = 0;
class CvCitySpecializationAI {
public:
    CvPlayer* m_pPlayer = &g_player;
    TrackedValues m_iBestValue;
    void FindBestSites();
    int PlotValueForSpecificYield(CvPlot* pPlot, YieldTypes eYield);
    int PlotValueForScience(CvPlot* pPlot);
    void LogBestSites() { ++g_log_best_sites_calls; }
};

/*__GENERATED_PATCH_HELPERS__*/
/*__ORIGINAL_SCALAR_HELPERS__*/
/*__GENERATED_FIND_BEST_SITES__*/

static int g_bridge_status = -1;
static bool g_corrupt_output = false;
static int g_bridge_calls = 0;
static unsigned int g_bridge_count = 0;
static unsigned int g_bridge_workers = 0;
static bool add32(std::int64_t value, int& result) {
    if (value < (std::numeric_limits<int>::min)() || value > (std::numeric_limits<int>::max)()) return false;
    result = static_cast<int>(value);
    return true;
}
static bool evaluate_mock(const ZeroSisCitySiteInput& input, ZeroSisCitySiteResult& output) {
    int specific[3] = {0, 0, 0};
    int science_food = 0;
    int science_clear = 0;
    int multiplier = 0;
    for (unsigned int index = 0; index < input.tile_count; ++index) {
        if (index == CITY_HOME_PLOT) continue;
        const ZeroSisCitySiteCell& cell = input.cells[index];
        if (!cell.present) continue;
        if (cell.foreign_owned) multiplier = 0;
        else if (cell.ring_distance == 1) multiplier = input.ring_weights[0];
        else if (cell.ring_distance == 2) multiplier = input.ring_weights[1];
        else if (cell.ring_distance == 3) multiplier = input.ring_weights[2];
        for (int yield = 0; yield < 3; ++yield) {
            int product = 0;
            if (!add32(static_cast<std::int64_t>(cell.yields[yield]) * multiplier, product) ||
                !add32(static_cast<std::int64_t>(specific[yield]) + product, specific[yield])) return false;
        }
        int potential = 0;
        int product = 0;
        if (!add32(static_cast<std::int64_t>(cell.yields[0]) + cell.yields[3], potential) ||
            !add32(static_cast<std::int64_t>(potential) * multiplier, product) ||
            !add32(static_cast<std::int64_t>(science_food) + product, science_food)) return false;
        if (cell.science_clear && !add32(static_cast<std::int64_t>(science_clear) + multiplier, science_clear)) return false;
    }
    int science = 0;
    if (!add32(static_cast<std::int64_t>(science_food) + science_clear, science)) return false;
    output.values[0] = specific[0];
    output.values[1] = specific[1];
    output.values[2] = specific[2];
    output.values[3] = science;
    return true;
}

extern "C" int32_t ZeroSisEvaluateCitySites(const ZeroSisCitySiteInput* inputs, uint32_t count,
                                              uint32_t workers, ZeroSisCitySiteResult* results,
                                              ZeroSisCitySiteMetrics* metrics) {
    ++g_bridge_calls;
    g_bridge_count = count;
    g_bridge_workers = workers;
    std::memset(metrics, 0, sizeof(*metrics));
    metrics->abi_version = ZEROSIS_CITY_SITE_ABI_VERSION;
    metrics->config_version = ZEROSIS_CITY_SITE_CONFIG_VERSION;
    metrics->requested_workers = workers;
    metrics->jobs_total = count;
    metrics->jobs_started = count;
    metrics->jobs_completed = count;
    metrics->status = g_bridge_status >= 0 ? static_cast<uint32_t>(g_bridge_status) : ZEROSIS_CITY_SITE_OK;
    if (g_bridge_status >= 0) return g_bridge_status;
    std::vector<ZeroSisCitySiteResult> staged(count);
    for (uint32_t index = 0; index < count; ++index) {
        if (!evaluate_mock(inputs[index], staged[index])) {
            metrics->status = ZEROSIS_CITY_SITE_OVERFLOW;
            return ZEROSIS_CITY_SITE_OVERFLOW;
        }
    }
    for (uint32_t index = 0; index < count; ++index) results[index] = staged[index];
    if (g_corrupt_output && count != 0) ++results[0].values[0];
    return ZEROSIS_CITY_SITE_OK;
}

namespace {
int checks = 0;
void Require(bool condition, const char* message) {
    ++checks;
    if (!condition) throw std::runtime_error(message);
}
void RequireValues(const CvCitySpecializationAI& ai, const std::array<int, 4>& expected,
                   const char* message) {
    for (std::size_t i = 0; i < expected.size(); ++i)
        Require(ai.m_iBestValue.values[i] == expected[i], message);
}
void FillPlot(CvPlot& plot, int id, int x, int y, const std::array<int, 4>& yields) {
    plot.id = id; plot.x = x; plot.y = y; plot.owner = -1;
    plot.resource = NO_RESOURCE; plot.feature = NO_FEATURE; plot.improvement = NO_IMPROVEMENT;
    plot.hills = false; plot.yields = yields;
}
void ResetState(int site_count = 3) {
    g_dll = MockDll{}; gDLL = &g_dll;
    g_map = MockMap{}; g_map.site_count = site_count;
    g_map.nearest_city.x = 0; g_map.nearest_city.y = 0;
    GC = MockGC{}; g_game = MockGame{}; g_player = CvPlayer{};
    g_log_best_sites_calls = 0;
    g_bridge_status = -1; g_corrupt_output = false;
    g_bridge_calls = 0; g_bridge_count = 0; g_bridge_workers = 0;
    for (int site = 0; site < site_count; ++site) {
        const int x = site + 1;
        FillPlot(g_map.sites[static_cast<std::size_t>(site)], site, x, 0, {{0, 0, 0, 0}});
        FillPlot(g_map.cells[static_cast<std::size_t>(site)][0], site, x, 0, {{0, 0, 0, 0}});
        FillPlot(g_map.cells[static_cast<std::size_t>(site)][1], 100 + site, x + 1, 0,
                 {{3 + site, 2 + site, 1 + site, 4 + site}});
        FillPlot(g_map.cells[static_cast<std::size_t>(site)][2], 200 + site, x + 2, 0,
                 {{5 + site, 1 + site, 3 + site, 2 + site}});
        FillPlot(g_map.cells[static_cast<std::size_t>(site)][3], 300 + site, x + 3, 0,
                 {{1 + site, 3 + site, 2 + site, 1 + site}});
        if (site == 1) g_map.cells[1][2].owner = 1;
        if (site == 2) g_map.cells[2][3].hills = true;
    }
    _putenv_s("ZEROSIS_CITY_SITE_WORKERS", "2");
}
void ExpectThrow(CvCitySpecializationAI& ai, const char* message) {
    bool threw = false;
    try { ai.FindBestSites(); }
    catch (const std::exception&) { threw = true; }
    Require(threw, message);
}
void TestWrongOwnerAndLockPrecedeReads() {
    for (int mode = 0; mode < 2; ++mode) {
        ResetState();
        CvCitySpecializationAI ai;
        ai.m_iBestValue.values = {{71, 72, 73, 74}};
        if (mode == 0) g_dll.owner_thread = false;
        else g_dll.lock_held = false;
        ExpectThrow(ai, "Wrong thread or missing lock was accepted");
        Require(g_map.reads == 0 && GC.reads == 0 && g_map.eligibility_calls == 0,
                "Owner/lock rejection read game state before failing");
        Require(ai.m_iBestValue.writes == 0 && ai.m_iBestValue.values == std::array<int, 4>{{71,72,73,74}},
                "Owner/lock rejection changed best values");
        Require(g_bridge_calls == 0 && g_log_best_sites_calls == 0,
                "Owner/lock rejection entered scoring or logging");
        Require(g_dll.owner_queries == 1 && g_dll.lock_queries == (mode == 0 ? 0 : 1),
                "Owner/lock guard order changed");
    }
}
void TestCaptureFailurePreservesPriorValues() {
    ResetState(); GC.tile_count = ZEROSIS_CITY_SITE_MAX_TILES + 1;
    CvCitySpecializationAI ai; ai.m_iBestValue.values = {{81,82,83,84}};
    ExpectThrow(ai, "Malformed snapshot was accepted");
    RequireValues(ai, {{81,82,83,84}}, "Capture failure changed prior values");
    Require(ai.m_iBestValue.writes == 0 && g_bridge_calls == 0,
            "Capture failure committed or entered bridge");
}
void TestBridgeFailureAndOverflowPreservePriorValues() {
    for (int status : {ZEROSIS_CITY_SITE_BATCH_FAILURE, ZEROSIS_CITY_SITE_OVERFLOW}) {
        ResetState(); g_bridge_status = status;
        CvCitySpecializationAI ai; ai.m_iBestValue.values = {{91,92,93,94}};
        ExpectThrow(ai, "Bridge failure status was accepted");
        RequireValues(ai, {{91,92,93,94}}, "Bridge failure changed prior values");
        Require(ai.m_iBestValue.writes == 0 && g_bridge_calls == 1,
                "Bridge failure committed output or skipped bridge");
    }
    ResetState();
    g_map.cells[0][1].yields[0] = (std::numeric_limits<int>::max)();
    CvCitySpecializationAI ai; ai.m_iBestValue.values = {{101,102,103,104}};
    ExpectThrow(ai, "Arithmetic overflow was accepted");
    RequireValues(ai, {{101,102,103,104}}, "Arithmetic overflow changed prior values");
    Require(ai.m_iBestValue.writes == 0, "Arithmetic overflow committed a partial result");
}
void TestShadowMismatchPreservesPriorValues() {
    ResetState(); g_corrupt_output = true;
    CvCitySpecializationAI ai; ai.m_iBestValue.values = {{111,112,113,114}};
    ExpectThrow(ai, "Scalar shadow mismatch was accepted");
    RequireValues(ai, {{111,112,113,114}}, "Shadow mismatch changed prior values");
    Require(ai.m_iBestValue.writes == 0 && g_bridge_calls == 1,
            "Shadow mismatch committed or skipped bridge");
}
std::array<int, 4> ScalarOracle(CvCitySpecializationAI& ai) {
    std::array<int, 4> best{{0,0,0,0}};
    for (int index = 0; index < g_map.site_count; ++index) {
        CvPlot* plot = &g_map.sites[static_cast<std::size_t>(index)];
        best[0] = (std::max)(best[0], ai.PlotValueForSpecificYield(plot, YIELD_FOOD));
        best[1] = (std::max)(best[1], ai.PlotValueForSpecificYield(plot, YIELD_PRODUCTION));
        best[2] = (std::max)(best[2], ai.PlotValueForSpecificYield(plot, YIELD_GOLD));
        best[3] = (std::max)(best[3], ai.PlotValueForScience(plot));
    }
    return best;
}
void TestWorkerSuccessIsOneFourYieldCommit() {
    ResetState(); CvCitySpecializationAI ai;
    const auto expected = ScalarOracle(ai);
    ai.m_iBestValue.values = {{-1,-2,-3,-4}}; ai.m_iBestValue.writes = 0;
    ai.FindBestSites();
    RequireValues(ai, expected, "Worker reduction differs from scalar max values");
    Require(ai.m_iBestValue.writes == 4, "Worker success did not make exactly one four-value commit");
    Require(g_bridge_calls == 1 && g_bridge_count == 3 && g_bridge_workers == 2,
            "Worker bridge received different eligible count or worker request");
    Require(g_log_best_sites_calls == 1, "Successful worker mode skipped best-site logging");
}
void TestEmptyEligibleBatchClearsToZero() {
    ResetState(0); CvCitySpecializationAI ai;
    ai.m_iBestValue.values = {{121,122,123,124}};
    ai.FindBestSites();
    RequireValues(ai, {{0,0,0,0}}, "Empty eligible batch did not clear best values");
    Require(ai.m_iBestValue.writes == 4 && g_bridge_calls == 1 && g_bridge_count == 0,
            "Empty eligible batch did not complete one zero-result commit");
}
void TestScalarModeMatchesOriginalSuccessfulResult() {
    ResetState(); _putenv_s("ZEROSIS_CITY_SITE_WORKERS", "0");
    CvCitySpecializationAI ai;
    const auto expected = ScalarOracle(ai);
    ai.m_iBestValue.values = {{131,132,133,134}}; ai.m_iBestValue.writes = 0;
    ai.FindBestSites();
    RequireValues(ai, expected, "Worker-count zero changed original scalar result");
    Require(g_bridge_calls == 0 && g_log_best_sites_calls == 1,
            "Scalar mode invoked the bridge or skipped logging");
}
} // namespace

int main() {
    try {
        TestWrongOwnerAndLockPrecedeReads();
        TestCaptureFailurePreservesPriorValues();
        TestBridgeFailureAndOverflowPreservePriorValues();
        TestShadowMismatchPreservesPriorValues();
        TestWorkerSuccessIsOneFourYieldCommit();
        TestEmptyEligibleBatchClearsToZero();
        TestScalarModeMatchesOriginalSuccessfulResult();
        std::printf("CITY_SITE_SDK_COMMIT_PASS checks=%d SOURCE_SHAPED_MOCKS=true GAMECORE_LOADED=false\n", checks);
        return 0;
    } catch (const std::exception& error) {
        std::fprintf(stderr, "CITY_SITE_SDK_COMMIT_FAIL checks=%d error=%s\n", checks, error.what());
        return 1;
    }
}
