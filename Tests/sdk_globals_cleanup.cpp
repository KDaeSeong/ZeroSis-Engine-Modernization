// Execute exact extracted SDK cleanup bodies. Unrelated globals and host services
// are instrumented substitutes; this is not full GameCore initialization/shutdown.
#include <cstdio>
#include <cstdlib>
#include <new>
#include <string>
#include <vector>

#include "sdk_gc_cleanup_scope.h"
namespace CvTypes { inline void ResetTypes() noexcept {} }
#ifdef GLOBALS_ORIGINAL
#define CLEANUP_FIXTURE(g) (g).uninit()
#else
#define CLEANUP_FIXTURE(g) RunInstrumentedCleanup((g),gDLL)
#endif

namespace {
int checks = 0;
void Check(bool value, const char* message) {
    ++checks;
    if (!value) {
        std::fprintf(stderr, "FAIL|%s\n", message);
        std::exit(1);
    }
}
struct Observation {
    int holders = 0, entries = 0, arrays = 0, tokens = 0, finders = 0;
    int players = 0, teams = 0, release = 0, host = 0;
    int holderDeleted = 0, entryDeleted = 0, arrayDeleted = 0;
    bool inUninit = false;
    bool hostExpected = false;
    std::vector<std::string> order;
} observed;
struct Token {
    const char* name;
    bool finder;
    Token(const char* value, bool path) : name(value), finder(path) {
        ++observed.tokens;
        if (finder) ++observed.finders;
    }
    ~Token() {
        Check(observed.players == 1 && observed.teams == 1, "borrowers precede owned objects");
        if (finder)
            Check(observed.release == 1 && observed.host == (observed.hostExpected ? 1 : 0),
                  "query and host precede finder cleanup");
        else
            Check(observed.release == 0, "ordinary owners precede query release");
        observed.order.emplace_back(name);
        --observed.tokens;
        if (finder) --observed.finders;
    }
};
struct CvPlayerAI {
    static void freeStatics() {
        ++observed.players;
        observed.order.emplace_back("players");
    }
};
struct CvTeam {
    static void freeStatics() {
        ++observed.teams;
        observed.order.emplace_back("teams");
    }
};
struct Query {
    void Release() {
        ++observed.release;
        observed.order.emplace_back("query");
        Check(observed.tokens == observed.finders, "non-finder owners released before query");
    }
};
struct Host {
    void UninitGlobals() {
        ++observed.host;
        observed.order.emplace_back("host");
        Check(observed.release == 1, "query released before host");
#ifndef GLOBALS_ORIGINAL
        Check(observed.holders == 0 && observed.entries == 0 && observed.arrays == 0,
              "strategy ownership released before host");
#endif
    }
};
Host* gDLL = nullptr;
int* MakeArray() {
    int* value = new int[7]{};
    ++observed.arrays;
    return value;
}
template<class T> void DeleteArray(T*& value) {
    if (value) {
        --observed.arrays;
        ++observed.arrayDeleted;
        delete[] value;
        value = nullptr;
    }
}
}

#define SAFE_DELETE(value) do { delete (value); (value) = nullptr; } while (false)
#define SAFE_DELETE_ARRAY(value) DeleteArray(value)

class CvAICityStrategyEntry {
public:
    int* m_piFlavorValue = nullptr;
    int* m_piPersonalityFlavorThresholdMod = nullptr;
    ~CvAICityStrategyEntry(void);
    static void* operator new(std::size_t bytes) {
        void* value = std::malloc(bytes);
        if (!value) throw std::bad_alloc();
        ++observed.entries;
        return value;
    }
    static void operator delete(void* value) noexcept {
        --observed.entries;
        ++observed.entryDeleted;
        std::free(value);
    }
};

class CvAICityStrategies {
public:
    std::vector<CvAICityStrategyEntry*> m_paAICityStrategyEntries;
    CvAICityStrategies(void);
    ~CvAICityStrategies(void);
    void DeleteArray();
    static void* operator new(std::size_t bytes) {
        void* value = std::malloc(bytes);
        if (!value) throw std::bad_alloc();
        ++observed.holders;
        return value;
    }
    static void operator delete(void* value) noexcept {
        Check(observed.entries == 0 && observed.arrays == 0, "children released before holder storage");
        if (observed.inUninit)
            Check(observed.players == 1 && observed.teams == 1 && observed.release == 0,
                  "strategy cleanup between borrowers and query release");
        --observed.holders;
        ++observed.holderDeleted;
        observed.order.emplace_back("strategy");
        std::free(value);
    }
};

#include "globals_cleanup_fields.h"
class CvGlobals {
public:
#define DECLARE_FIELD(name, finder) Token* name = nullptr;
    GLOBALS_OTHER_FIELDS(DECLARE_FIELD)
#undef DECLARE_FIELD
    CvAICityStrategies* m_pAICityStrategies = nullptr;
    Query m_kGlobalDefinesLookup;
    void releaseDatabaseLoadUtility() {} // Loader ownership is exercised in sdk_database_loader.cpp.
    void uninit();
    void deleteInfoArrays() {} // Rule storage is exercised in sdk_info_cleanup.cpp.
};
#include "globals_cleanup_fixture.h"

namespace {
int cases = 0, holderCases = 0, hostCases = 0;
int leakedHolders = 0, leakedEntries = 0, leakedArrays = 0;
void RunCase(bool holder, int count, int mask, bool preclear, bool host, bool tokens) {
    Check(observed.holders == 0 && observed.entries == 0 && observed.arrays == 0 && observed.tokens == 0,
          "previous case cleaned");
    observed = Observation{};
    observed.hostExpected = host;
    CvGlobals globals;
    Host service;
    gDLL = host ? &service : nullptr;
    if (tokens) {
#define ALLOCATE_FIELD(name, finder) globals.name = new Token(#name, finder);
        GLOBALS_OTHER_FIELDS(ALLOCATE_FIELD)
#undef ALLOCATE_FIELD
    }
    const int expectedArrays = count * (((mask & 1) ? 1 : 0) + ((mask & 2) ? 1 : 0));
    if (holder) {
        ++holderCases;
        globals.m_pAICityStrategies = new CvAICityStrategies;
        auto& entries = globals.m_pAICityStrategies->m_paAICityStrategyEntries;
        // Null slots model incomplete cache population without inventing ownership.
        entries.push_back(nullptr);
        for (int i = 0; i < count; ++i) {
            auto* entry = new CvAICityStrategyEntry;
            if (mask & 1) entry->m_piFlavorValue = MakeArray();
            if (mask & 2) entry->m_piPersonalityFlavorThresholdMod = MakeArray();
            entries.push_back(entry);
        }
        entries.push_back(nullptr);
        if (preclear) {
            globals.m_pAICityStrategies->DeleteArray();
            Check(entries.empty() && observed.entries == 0 && observed.arrays == 0,
                  "preclear releases contents");
            globals.m_pAICityStrategies->DeleteArray();
            Check(observed.entryDeleted == count && observed.arrayDeleted == expectedArrays,
                  "repeated container clear does not delete twice");
        }
    }
    observed.inUninit = true;
    CLEANUP_FIXTURE(globals); // Exactly once: no claim about whole GC duplicate shutdown.
    observed.inUninit = false;
    ++cases;
    if (host) ++hostCases;
    Check(observed.players == 1 && observed.teams == 1, "both borrower cleanup calls");
    Check(observed.order[0] == "players" && observed.order[1] == "teams", "borrower cleanup order");
    Check(observed.release == 1 && observed.host == (host ? 1 : 0), "query and optional host preserved");
    Check(observed.tokens == 0 && observed.finders == 0, "other owned resources cleaned");
#define CHECK_FIELD(name, finder) Check(globals.name == nullptr, "other field reset: " #name);
    GLOBALS_OTHER_FIELDS(CHECK_FIELD)
#undef CHECK_FIELD
#ifdef GLOBALS_ORIGINAL
    Check(observed.holders == (holder ? 1 : 0), "original leaves holder allocated");
    Check(observed.entries == (preclear ? 0 : count), "original leaves uncleared entries allocated");
    Check(observed.arrays == (preclear ? 0 : expectedArrays), "original leaves uncleared arrays allocated");
    leakedHolders += observed.holders;
    leakedEntries += observed.entries;
    leakedArrays += observed.arrays;
    // Only after recording the original defect, clean up the test process.
    SAFE_DELETE(globals.m_pAICityStrategies);
#else
    Check(globals.m_pAICityStrategies == nullptr, "candidate clears strategy owner pointer");
    Check(observed.holders == 0 && observed.entries == 0 && observed.arrays == 0,
          "candidate releases entire strategy ownership");
#endif
    Check(observed.holderDeleted == (holder ? 1 : 0), "exactly one holder deletion");
    Check(observed.entryDeleted == count && observed.arrayDeleted == expectedArrays,
          "all allocated child storage deleted once");
    gDLL = nullptr;
}
}

int main() {
    for (bool host : {false, true}) {
        for (bool tokens : {false, true}) {
            RunCase(false, 0, 0, false, host, tokens);
            for (int count : {0, 1, 5, 32})
                for (int mask = 0; mask != 4; ++mask)
                    for (bool preclear : {false, true})
                        RunCase(true, count, mask, preclear, host, tokens);
        }
    }
    std::printf("CASES|%d|holder_cases=%d|host_cases=%d\n", cases, holderCases, hostCases);
#ifdef GLOBALS_ORIGINAL
    std::printf("ORIGINAL_LEAK|holders=%d|entries=%d|arrays=%d\n", leakedHolders, leakedEntries, leakedArrays);
#else
    std::printf("CANDIDATE_CLEAN|holders=%d|entries=%d|arrays=%d\n", observed.holders, observed.entries, observed.arrays);
    std::puts("ORDER|players|teams|owned_strategy|query|optional_host|finders");
#endif
    std::puts("SCOPE|exact_cleanup_bodies|instrumented_other_owners|no_gamecore_loaded");
    std::printf("PASS|%d\n", checks);
}
