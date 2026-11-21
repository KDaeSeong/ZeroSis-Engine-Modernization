// Exact SDK constructors/destructors and map reset/uninit, with explicitly
// instrumented game reset, timer, host, GUID and container seams. No game I/O.
#include <algorithm>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <new>
#include <vector>

namespace {
int checks = 0;
void Check(bool okay, const char* message) {
    ++checks;
    if (!okay) { std::fprintf(stderr, "FAIL|%s\n", message); std::exit(1); }
}
struct Injected { int point; };
struct Allocation { void* address = nullptr; std::size_t bytes = 0; bool live = false; };
Allocation allocations[32];
int arrayAttempts = 0, failArray = 0, liveArrays = 0;
int gameFault = 0, mapFault = 0, resourceCount = 0;
int timerStarts = 0, timerStops = 0, gameResets = 0, hostCalls = 0;
int gameFailures = 0, mapFailures = 0, successCases = 0;
int originalGameLeaks = 0, originalMapLeaks = 0, originalMapCounts = 0;
void CleanRecordedLeaks() {
    for (auto& row : allocations)
        if (row.live) delete[] static_cast<int*>(row.address);
    Check(liveArrays == 0, "test process cleanup complete");
}
}

void* operator new[](std::size_t bytes) {
    ++arrayAttempts;
    if (failArray == arrayAttempts) throw std::bad_alloc();
    void* address = std::malloc(bytes ? bytes : 1);
    if (!address) throw std::bad_alloc();
    for (auto& row : allocations) {
        if (!row.live) {
            row = {address, bytes, true};
            ++liveArrays;
            return address;
        }
    }
    std::free(address);
    throw std::bad_alloc();
}
void operator delete[](void* address) noexcept {
    if (!address) return;
    for (auto& row : allocations) {
        if (row.live && row.address == address) {
            row.live = false;
            --liveArrays;
            std::free(address);
            return;
        }
    }
    Check(false, "array delete must match live allocation");
}
void operator delete[](void* address, std::size_t) noexcept { ::operator delete[](address); }

constexpr int MAX_PLAYERS = 64, MAX_TEAMS = 64, NO_HANDICAP = -1, NO_WORLDSIZE = -1;
#define FNEW(type, pool, tag) new type
#define SAFE_DELETE_ARRAY(value) do { delete[] (value); (value) = nullptr; } while (false)
#define CvAssert(value) Check((value), "SDK assertion")
#define CvAssertMsg(value, message) Check((value), (message))
#include "construction_fields.h"
#include "construction_map_init.h"

struct Timer {
    void Start() { ++timerStarts; if (gameFault == 1) throw Injected{1}; }
    void Stop() { ++timerStops; if (gameFault == 2) throw Injected{2}; }
};
struct Random { explicit Random(bool) {} };

class CvGame {
public:
    Random m_jonRand;
    Timer m_endTurnTimer;
    int m_endTurnTimerSemaphore;
    Timer m_curTurnTimer, m_timeSinceGameTurnStart;
    float m_fCurrentTurnTimerPauseDelta;
    bool m_sentAutoMoves, m_bForceEndingTurn;
    int* m_pDiploResponseQuery;
    bool m_bFOW, m_bArchaeologyTriggered;
    int m_lastTurnAICivsProcessed;
#define DECLARE_OWNED(name, size) int* name = nullptr;
    GAME_OWNED_FIELDS(DECLARE_OWNED)
#undef DECLARE_OWNED
#define DECLARE_NULL(name) int* name = nullptr;
    GAME_NULL_FIELDS(DECLARE_NULL)
#undef DECLARE_NULL
    CvGame();
    ~CvGame();
    void reset(int handicap, bool constructorCall) {
        ++gameResets;
        Check(handicap == NO_HANDICAP && constructorCall, "original constructor reset arguments");
        Check(liveArrays == 7, "all arrays available to reset");
        if (gameFault == 3) throw Injected{3};
        int ordinal = 0;
#define RESET_ARRAY(name, size) \
        for (int i = 0; i < size; ++i) name[i] = 0; \
        ++ordinal; if (gameFault == 4 && ordinal == 3) throw Injected{4};
        GAME_OWNED_FIELDS(RESET_ARRAY)
#undef RESET_ARRAY
        if (gameFault == 5) throw Injected{5};
        if (gameFault == 6) throw std::bad_alloc();
    }
    void uninit() {
        // Only the non-throwing ownership boundary is substituted here.
        Check(liveArrays == 7, "destructor sees retained arrays");
    }
    void CheckValues() const {
        Check(timerStarts == 1 && timerStops == 1 && gameResets == 1, "unchanged game success call order");
#define CHECK_ARRAY(name, size) \
        Check(name != nullptr, "published array: " #name); \
        for (int i = 0; i < size; ++i) Check(name[i] == 0, "reset array contents: " #name);
        GAME_OWNED_FIELDS(CHECK_ARRAY)
#undef CHECK_ARRAY
#define CHECK_NULL(name) Check(name == nullptr, "other constructor null field: " #name);
        GAME_NULL_FIELDS(CHECK_NULL)
#undef CHECK_NULL
        Check(m_pDiploResponseQuery == nullptr && m_endTurnTimerSemaphore == 0
              && m_fCurrentTurnTimerPauseDelta == 0.f && !m_sentAutoMoves && !m_bForceEndingTurn
              && m_bFOW && !m_bArchaeologyTriggered && m_lastTurnAICivsProcessed == -1,
              "other game constructor values unchanged");
    }
};

int sgCvMapInstanceCount = 0;
struct PreGame {
    static int worldSize() { return NO_WORLDSIZE; }
};
namespace CvPreGame { int worldSize() { return PreGame::worldSize(); } }
struct WorldInfo { int getGridWidth() const { return 0; } int getGridHeight() const { return 0; } };
struct Globals { int getNumResourceInfos() const { return resourceCount; } } GC;
struct Guid { unsigned value = 0; };
int CoCreateGuid(Guid* value) { value->value = 123; return 0; }
struct List {
    int id;
    explicit List(int number) : id(number) {}
    void Uninit() noexcept {}
    void RemoveAll() { if (mapFault == id) throw Injected{10 + id}; }
};
struct Host {
    void DoMapSetup(int plots) {
        ++hostCalls;
        Check(plots == 0 && sgCvMapInstanceCount == 1, "map setup observes original constructor state");
        if (mapFault == 3) throw Injected{13};
    }
} host;
Host* gDLL = &host;

class CvMap {
public:
#define DECLARE_MAP_NULL(name) int* name = nullptr;
    MAP_NULL_FIELDS(DECLARE_MAP_NULL)
#undef DECLARE_MAP_NULL
    int m_iAIMapHints = -1, m_iGridWidth = -1, m_iGridHeight = -1, m_iGridSize = -1;
    int m_iLandPlots = -1, m_iOwnedPlots = -1, m_iNumNaturalWonders = -1;
    int m_iTopLatitude = 90, m_iBottomLatitude = -90;
    bool m_bWrapX = false, m_bWrapY = true;
    Guid m_guid;
    List m_areas{1}, m_landmasses{2}, m_kPlotManager{0};
    std::vector<int> m_vDeferredFogPlots;
    CvMap();
    ~CvMap();
    void reset(CvMapInitData* pInitInfo);
    void uninit();
    WorldInfo getWorldInfo() const { return {}; }
    int numPlots() const { return m_iGridSize; }
    void CheckValues() const {
        Check(hostCalls == 1 && sgCvMapInstanceCount == 1, "successful live map");
        Check(m_iGridWidth == 0 && m_iGridHeight == 0 && m_iGridSize == 0
              && m_iLandPlots == 0 && m_iOwnedPlots == 0 && m_iNumNaturalWonders == 0
              && m_iAIMapHints == 0 && m_iTopLatitude == 90 && m_iBottomLatitude == -90
              && m_bWrapX && !m_bWrapY && m_guid.value == 123, "unchanged default map state");
        Check(liveArrays == (resourceCount ? 2 : 0), "map owns resource arrays");
        for (int i = 0; i < resourceCount; ++i)
            Check(m_paiNumResource[i] == 0 && m_paiNumResourceOnLand[i] == 0, "resource counts zeroed");
    }
};
#include "construction_fixture.h"

namespace {
void Configure(int allocation, int game, int map, int resources) {
    Check(liveArrays == 0 && sgCvMapInstanceCount == 0, "new attempt starts without owned remnants");
    arrayAttempts = 0; failArray = allocation; gameFault = game; mapFault = map;
    resourceCount = resources; timerStarts = 0; timerStops = 0; gameResets = 0; hostCalls = 0;
}
void GameSuccess() {
    Configure(0, 0, 0, 0);
    { CvGame game; game.CheckValues(); Check(arrayAttempts == 7, "seven original allocation requests"); }
    Check(liveArrays == 0, "game destructor releases all seven arrays");
    ++successCases;
}
void GameFailure(int allocation, int fault) {
    Configure(allocation, fault, 0, 0);
    bool caught = false;
    try { CvGame game; }
    catch (const std::bad_alloc&) { caught = allocation != 0 || fault == 6; }
    catch (const Injected& value) { caught = allocation == 0 && value.point == fault; }
    Check(caught, "original game exception type and payload preserved");
    ++gameFailures;
#ifdef CONSTRUCTION_ORIGINAL
    const int expected = allocation ? allocation - 1 : 7;
    Check(liveArrays == expected, "original game constructor leaves prior arrays");
    originalGameLeaks += liveArrays;
    CleanRecordedLeaks();
#else
    Check(liveArrays == 0, "throwing game constructor releases arrays");
#endif
    GameSuccess();
}
void MapSuccess(int resources) {
    Configure(0, 0, 0, resources);
    { CvMap map; map.CheckValues(); }
    Check(liveArrays == 0 && sgCvMapInstanceCount == 0, "map destructor restores ownership and counter");
    ++successCases;
}
void MapFailure(int allocation, int fault, int resources) {
    Configure(allocation, 0, fault, resources);
    bool caught = false;
    try { CvMap map; }
    catch (const std::bad_alloc&) { caught = allocation != 0; }
    catch (const Injected& value) { caught = allocation == 0 && value.point == 10 + fault; }
    Check(caught, "original map exception type and payload preserved");
    ++mapFailures;
#ifdef CONSTRUCTION_ORIGINAL
    const int expected = allocation ? allocation - 1 : (resources ? 2 : 0);
    Check(liveArrays == expected && sgCvMapInstanceCount == 1, "original map ownership and counter survive failure");
    originalMapLeaks += liveArrays;
    originalMapCounts += sgCvMapInstanceCount;
    CleanRecordedLeaks();
    // Restore only the instrumented original test state, after recording it.
    sgCvMapInstanceCount = 0;
#else
    Check(liveArrays == 0 && sgCvMapInstanceCount == 0, "throwing map constructor cleans and restores counter");
#endif
    MapSuccess(resources);
}
}

int main() {
    GameSuccess();
    for (int allocation = 1; allocation <= 7; ++allocation) GameFailure(allocation, 0);
    for (int fault = 1; fault <= 6; ++fault) GameFailure(0, fault);
    for (int resources : {0, 1, 129}) {
        MapSuccess(resources);
        if (resources)
            for (int allocation = 1; allocation <= 2; ++allocation) MapFailure(allocation, 0, resources);
        for (int fault = 1; fault <= 3; ++fault) MapFailure(0, fault, resources);
    }
    std::printf("FAILURES|game=%d|map=%d|successful_constructions=%d\n", gameFailures, mapFailures, successCases);
#ifdef CONSTRUCTION_ORIGINAL
    std::printf("ORIGINAL_REMAINS|game_arrays=%d|map_arrays=%d|map_counts=%d\n",
                originalGameLeaks, originalMapLeaks, originalMapCounts);
#else
    std::printf("CANDIDATE_CLEAN|arrays=%d|map_count=%d\n", liveArrays, sgCvMapInstanceCount);
#endif
    std::puts("RETRY|every_failed_construction_followed_by_success");
    std::puts("SCOPE|instrumented_game_reset_host_containers|no_gamecore_loaded|no_game_database_io");
    std::printf("PASS|%d\n", checks);
}
