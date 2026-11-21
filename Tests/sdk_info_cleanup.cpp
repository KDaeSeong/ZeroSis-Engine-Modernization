// Exact SDK container cleanup, uninit, lookup reset and prefetch templates.
// Rule entries and borrowers are instrumented; SQL uses the real x64 provider.
#include <cstdio>
#include <cstdlib>
#include <map>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>
#include "SdkDatabaseIncludes.h"
#include "sdk_gc_cleanup_scope.h"
namespace CvTypes { inline void ResetTypes() noexcept {} }
#ifdef INFO_CLEANUP_ORIGINAL
#define CLEANUP_FIXTURE(g) (g).uninit()
#else
#define CLEANUP_FIXTURE(g) RunInstrumentedCleanup((g),gDLL)
#endif


bool failNextAllocation = false;
void* operator new(std::size_t bytes) {
    if (failNextAllocation) { failNextAllocation = false; throw std::bad_alloc(); }
    void* p = std::malloc(bytes ? bytes : 1);
    if (!p) throw std::bad_alloc();
    return p;
}
void* operator new[](std::size_t bytes) { return ::operator new(bytes); }
void operator delete(void* p) noexcept { std::free(p); }
void operator delete[](void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete[](void* p, std::size_t) noexcept { std::free(p); }
unsigned checks = 0, entries = 0, children = 0, strings = 0, destroyed = 0;
unsigned borrowers = 0, expectedEntries = 0, expectedStrings = 0;
unsigned playerStops = 0, teamStops = 0, queryStops = 0, loaderStops = 0, hostStops = 0;
bool inUninit = false, expectHost = false;
int failureMode = 0, failureId = -1;
void Check(bool ok, unsigned line) {
    ++checks;
    if (!ok) { std::printf("FAIL|%u\n", line); std::fflush(stdout); std::exit(2); }
}
#define CHECK(c) Check(!!(c), __LINE__)
void BorrowedInfoStillPresent() { CHECK(entries == expectedEntries && strings == expectedStrings); }
struct CvDatabaseUtility {};
struct Info;
Info* lastConstructed = nullptr;
std::vector<Info*>* activeCollection = nullptr;
struct Info {
    int value = -1;
    std::unique_ptr<int[]> child;
    Info() { ++entries; lastConstructed = this; }
    ~Info() {
        if (inUninit) {
            CHECK(borrowers == 0 && playerStops == 1 && teamStops == 1);
            CHECK(queryStops == 1 && loaderStops == 1 && hostStops == (expectHost ? 1u : 0u));
        }
        if (child) --children;
        --entries; ++destroyed;
        if (lastConstructed == this) lastConstructed = nullptr;
    }
    bool CacheResults(Database::Results& result, CvDatabaseUtility&) {
        value = result.GetInt("ID");
        if (value == failureId && failureMode == 2) failNextAllocation = true;
        child.reset(new int[3]{}); ++children;
        if (value == failureId && failureMode == 1) throw std::runtime_error("cache entry failure");
        if (value == failureId && failureMode == 3) {
            activeCollection->shrink_to_fit(); // force allocation on the next publication
            failNextAllocation = true;
        }
        return true;
    }
};
struct CvString {
    CvString() { ++strings; }
    ~CvString() { --strings; }
};
struct Borrower {
    Borrower() { ++borrowers; }
    ~Borrower() { BorrowedInfoStillPresent(); --borrowers; }
};
struct CvPlayerAI { static void freeStatics() { BorrowedInfoStillPresent(); ++playerStops; } };
struct CvTeam { static void freeStatics() { BorrowedInfoStillPresent(); ++teamStops; } };
struct Query { void Release() { BorrowedInfoStillPresent(); ++queryStops; } };
struct Host { void UninitGlobals() { BorrowedInfoStillPresent(); ++hostStops; } };
Host* gDLL = nullptr;
#include "info_cleanup_fields.h"
class CvGlobals {
public:
#define DECLARE_INFO(name) std::vector<Info*> name;
    INFO_COLLECTION_FIELDS(DECLARE_INFO)
#undef DECLARE_INFO
#define DECLARE_BORROWER(name) Borrower* name = nullptr;
    INFO_BORROWER_FIELDS(DECLARE_BORROWER)
#undef DECLARE_BORROWER
    CvString* m_paszFootstepAudioTags = nullptr;
    CvString* m_paszFlavorTypes = nullptr;
    int m_iNumFootstepAudioTags = 0, m_iNumFlavorTypes = 0;
    int m_iNumPlayableCivilizationInfos = 0, m_iNumAIPlayableCivilizationInfos = 0;
    std::map<std::string,int> m_infosMap;
    std::map<unsigned,int> m_infosHashMap;
    Query m_kGlobalDefinesLookup;
    void uninit();
    void deleteInfoArrays();
    void infoTypeFromStringReset();
    CvString*& getFootstepAudioTags();
    void releaseDatabaseLoadUtility() { BorrowedInfoStillPresent(); ++loaderStops; }
} GC;
Database::Connection ruleDatabase;
#define DB ruleDatabase
#define FNEW(value, pool, flags) new value
#define SAFE_DELETE(p) do { delete (p); (p) = nullptr; } while (false)
#define SAFE_DELETE_ARRAY(p) do { delete[] (p); (p) = nullptr; } while (false)
#define CvAssertMsg(c, message) CHECK(c);
struct cvStopWatch { cvStopWatch(const char*, const char*) {} };
class CvDllDatabaseUtility {
public:
    template<class T> bool PrefetchCollection(std::vector<T*>& collection, const char* table);
};
#include "info_cleanup_fixture.h"

std::vector<std::vector<Info*>*> Collections(CvGlobals& globals) {
    std::vector<std::vector<Info*>*> result;
#define ADD_COLLECTION(name) result.push_back(&globals.name);
    INFO_COLLECTION_FIELDS(ADD_COLLECTION)
#undef ADD_COLLECTION
    return result;
}
void Reclaim(CvGlobals& globals) {
    for (auto* collection : Collections(globals)) { for (auto* info : *collection) delete info; collection->clear(); }
    SAFE_DELETE_ARRAY(globals.m_paszFlavorTypes);
    SAFE_DELETE_ARRAY(globals.m_paszFootstepAudioTags);
    globals.m_iNumFlavorTypes = globals.m_iNumFootstepAudioTags = 0;
    globals.m_iNumPlayableCivilizationInfos = globals.m_iNumAIPlayableCivilizationInfos = 0;
    globals.infoTypeFromStringReset();
}
void CleanupCase(unsigned count, unsigned generation) {
    CHECK(entries == 0 && children == 0 && strings == 0 && borrowers == 0);
    auto lists = Collections(GC); CHECK(lists.size() == 40);
    for (unsigned i = 0; i < count; ++i) {
        lists[i]->push_back(nullptr);
        auto* info = new Info; info->value = static_cast<int>(generation);
        info->child.reset(new int[3]{}); ++children;
        lists[i]->push_back(info); lists[i]->push_back(nullptr);
    }
    GC.m_paszFlavorTypes = new CvString[3]; GC.m_iNumFlavorTypes = 3;
    GC.m_paszFootstepAudioTags = new CvString[2]; GC.m_iNumFootstepAudioTags = 2;
    GC.m_iNumPlayableCivilizationInfos = 7; GC.m_iNumAIPlayableCivilizationInfos = 8;
    GC.m_infosMap["OLD_RULE"] = 5; GC.m_infosHashMap[1234] = 5;
    expectedEntries = entries; expectedStrings = strings;
    playerStops = teamStops = queryStops = loaderStops = hostStops = 0;
    expectHost = ((count + generation) % 2) != 0;
    Host host; gDLL = expectHost ? &host : nullptr;
    if (count % 2) {
#define MAKE_BORROWER(name) GC.name = new Borrower;
        INFO_BORROWER_FIELDS(MAKE_BORROWER)
#undef MAKE_BORROWER
    }
    inUninit = true; CLEANUP_FIXTURE(GC); inUninit = false;
    CHECK(borrowers == 0 && playerStops == 1 && teamStops == 1);
#ifdef INFO_CLEANUP_ORIGINAL
    CHECK(entries == count && strings == 5 && children == count);
    CHECK(GC.m_infosMap.count("OLD_RULE") == 1 && GC.m_infosHashMap.count(1234) == 1);
    GC.deleteInfoArrays();
    CHECK(entries == (count == 40 ? 1u : 0u) && strings == 3);
    CHECK(GC.m_iNumFlavorTypes == 3 && GC.m_iNumFootstepAudioTags == 2);
    CHECK(GC.m_iNumPlayableCivilizationInfos == 7 && GC.m_iNumAIPlayableCivilizationInfos == 8);
    Reclaim(GC); // Test-only reclamation of observed original leaks.
#else
    CHECK(entries == 0 && children == 0 && strings == 0);
    CHECK(GC.m_infosMap.empty() && GC.m_infosHashMap.empty());
    CHECK(GC.m_iNumFlavorTypes == 0 && GC.m_iNumFootstepAudioTags == 0);
    CHECK(GC.m_iNumPlayableCivilizationInfos == 0 && GC.m_iNumAIPlayableCivilizationInfos == 0);
    for (auto* list : lists) CHECK(list->empty());
    const unsigned before = destroyed; GC.deleteInfoArrays(); CHECK(destroyed == before);
#endif
    gDLL = nullptr;
    CHECK(entries == 0 && children == 0 && strings == 0);
}
void InstanceOwnership() {
    CvGlobals local;
    GC.m_paszFootstepAudioTags = new CvString[2];
    local.m_paszFootstepAudioTags = new CvString[3];
    local.deleteInfoArrays();
#ifdef INFO_CLEANUP_ORIGINAL
    CHECK(GC.m_paszFootstepAudioTags == nullptr && local.m_paszFootstepAudioTags != nullptr && strings == 3);
#else
    CHECK(GC.m_paszFootstepAudioTags != nullptr && local.m_paszFootstepAudioTags == nullptr && strings == 2);
#endif
    Reclaim(local); Reclaim(GC); CHECK(strings == 0);
}
void PrefetchTests() {
    CHECK(ruleDatabase.Open(":memory:", Database::OPEN_READWRITE | Database::OPEN_CREATE));
    CHECK(ruleDatabase.Execute("CREATE TABLE Rules(ID INTEGER,Type TEXT)"));
    CHECK(ruleDatabase.Execute("INSERT INTO Rules VALUES(0,'A'),(2,'B'),(5,'C'),(7,'D')"));
    CvDllDatabaseUtility loader;
    for (int cycle = 0; cycle < 16; ++cycle) {
        std::vector<Info*> list; activeCollection = &list;
        CHECK(loader.PrefetchCollection(list,"Rules")); CHECK(list.size() == 8);
        for (unsigned i = 0; i < 8; ++i) {
            const bool present = i == 0 || i == 2 || i == 5 || i == 7;
            CHECK((list[i] != nullptr) == present);
            if (present) CHECK(list[i]->value == static_cast<int>(i));
        }
        CHECK(entries == 4 && children == 4);
        CHECK(loader.PrefetchCollection(list,"Rules")); CHECK(entries == 4 && children == 4);
        deleteInfoArray(list); CHECK(entries == 0 && children == 0);
    }
    unsigned failures = 0;
    for (int mode = 1; mode <= 3; ++mode) {
        for (int id : {0,2,5,7}) {
            if (mode == 3 && id != 0) continue;
            std::vector<Info*> list; activeCollection = &list;
            failureMode = mode; failureId = id;
            bool caught = false;
            try { loader.PrefetchCollection(list,"Rules"); }
            catch (const std::bad_alloc&) { CHECK(mode == 2 || mode == 3); caught = true; }
            catch (const std::runtime_error& e) { CHECK(mode == 1 && std::string(e.what()) == "cache entry failure"); caught = true; }
            CHECK(caught && !failNextAllocation); ++failures;
            unsigned published = 0;
            for (auto* p : list) if (p) { ++published; CHECK(p->value < id); }
#ifdef INFO_CLEANUP_ORIGINAL
            CHECK(entries == published + 1 && lastConstructed != nullptr);
            delete lastConstructed; // Original unpublished object otherwise has no owner.
#else
            CHECK(entries == published && lastConstructed == nullptr);
#endif
            deleteInfoArray(list); CHECK(entries == 0 && children == 0);
            failureMode = 0; failureId = -1;
            CHECK(loader.PrefetchCollection(list,"Rules")); CHECK(entries == 4 && children == 4);
            deleteInfoArray(list); CHECK(entries == 0 && children == 0);
        }
    }
    CHECK(failures == 9); ruleDatabase.Close(); activeCollection = nullptr;
}
int main() {
    for (unsigned count = 0; count <= 40; ++count) for (unsigned generation = 0; generation < 2; ++generation) CleanupCase(count,generation);
    InstanceOwnership(); PrefetchTests();
#ifdef INFO_CLEANUP_ORIGINAL
    std::puts("ORIGINAL|uninit_retains_rule_storage|helper_omits_formation_flavors_counts_maps|wrong_instance_audio|9_unpublished_entry_leaks");
#else
    std::puts("CANDIDATE|40_rule_collections|2_owned_string_arrays|lookup_items_and_counts_reset|borrowers_before_rules|duplicate_clear_safe");
    std::puts("PREFETCH|9_exceptions_preserved|unpublished_entry_destroyed|published_entries_retained_until_caller_cleanup|retry_succeeds");
#endif
    CHECK(entries == 0 && children == 0 && strings == 0 && borrowers == 0);
    std::puts("CASES|82_partial_cleanup_states|2_generations|instance_ownership|16_normal_prefetch_cycles|9_prefetch_failures");
    std::puts("SCOPE|exact_sdk_cleanup_and_prefetch|real_sqlite|instrumented_info_entries_borrowers|no_gamecore_loaded");
    std::printf("PASS|%u\n", checks);
}
