// Exact SDK ownership/cache bodies; real private Windows heap and SQLite provider.
// Other GC owners, host callbacks and game-data prefetch are observable substitutes.
#define NOMINMAX
#include <windows.h>
#include <cstdio>
#include <cstdlib>
#include <map>
#include <set>
#include <string>
#include <vector>
#include <new>
#include "SdkDatabaseIncludes.h"
#include "sdk_gc_cleanup_scope.h"
#ifdef DATABASE_LOADER_ORIGINAL
#define CLEANUP_FIXTURE(g) (g).uninit()
#else
#define CLEANUP_FIXTURE(g) RunInstrumentedCleanup((g),gDLL)
#endif

#include "ZeroSisHostBinding.h"
#define DLLCALL __stdcall
class CvString;
#include "database_loader_abi.h"

unsigned checks = 0, freed = 0, leakedAtHeapEnd = 0, prefetches = 0, validations = 0;
unsigned hostStops = 0, contextStops = 0, queryStops = 0, failAlloc = 0, failHeap = 0;
bool heapAlive = false;
std::set<void*> allocations;
Database::Connection testDatabase;
void Check(bool ok, unsigned line) {
    ++checks;
    if (!ok) { std::printf("FAIL|%u|%lu\n", line, GetLastError()); std::fflush(stdout); std::exit(2); }
}
#define CHECK(c) Check(!!(c), __LINE__)

struct ICvEngineUtility4 : ICvUnknown { virtual void UninitGlobals() = 0; };
struct UnrelatedOwner {};
struct CvPlayerAI { static void freeStatics() {} };
struct CvTeam { static void freeStatics() {} };
struct Query { void Release() { ++queryStops; } };
class CvGlobals {
public:
    // The real singleton has static zero initialization; this fixture initializes
    // the same field explicitly and makes no claim about local CvGlobals objects.
    ICvDLLDatabaseUtility1* m_pkDatabaseLoadUtility = nullptr;
    ICvEngineUtility4* host = nullptr;
    Query m_kGlobalDefinesLookup;
    std::map<std::string, int> types;
#include "database_loader_fields.h"
    ICvDLLDatabaseUtility1* getDatabaseLoadUtility();
    void releaseDatabaseLoadUtility();
    void uninit();
    void deleteInfoArrays() {} // Rule storage is exercised in sdk_info_cleanup.cpp.
    void infoTypeFromStringReset() { types.clear(); }
    void setInfoTypeFromString(const char* type, int id) { types[type] = id; }
    ICvEngineUtility4* getDLLIFace() { return host; }
    void setDLLIFace(ICvEngineUtility4* value) { host = value; }
} GC;
#define DB testDatabase
#define gDLL GC.host
#define CvAssertMsg(c, text) CHECK(c)
#define SAFE_DELETE(p) do { delete (p); (p) = nullptr; } while (false)
struct CvTypes { static void ResetTypes() noexcept {} static void AcquireTypes(Database::Connection& value) { CHECK(&value == &testDatabase); } };
class CvDllGameContext {
public:
    static HANDLE s_hHeap;
    static CvDllGameContext* s_pSingleton;
    static void* Allocate(size_t);
    static void Free(void*);
    static bool ShutdownSingleton();
    ~CvDllGameContext() { ++contextStops; CHECK(heapAlive); }
};
HANDLE CvDllGameContext::s_hHeap = INVALID_HANDLE_VALUE;
CvDllGameContext* CvDllGameContext::s_pSingleton = nullptr;

void* ObservedHeapAlloc(HANDLE heap, DWORD flags, SIZE_T bytes) {
    CHECK(heapAlive && heap == CvDllGameContext::s_hHeap);
    if (failAlloc) { --failAlloc; SetLastError(ERROR_NOT_ENOUGH_MEMORY); return nullptr; }
    void* p = ::HeapAlloc(heap, flags, bytes);
    if (p) CHECK(allocations.insert(p).second);
    return p;
}
BOOL ObservedHeapFree(HANDLE heap, DWORD flags, void* p) {
    CHECK(heapAlive && heap == CvDllGameContext::s_hHeap);
    CHECK(allocations.erase(p) == 1);
    ++freed;
    const BOOL ok = ::HeapFree(heap, flags, p);
    CHECK(ok != FALSE);
    return ok;
}
BOOL ObservedHeapDestroy(HANDLE heap) {
    CHECK(heapAlive && heap == CvDllGameContext::s_hHeap && GC.host == nullptr);
#ifndef DATABASE_LOADER_ORIGINAL
    CHECK(allocations.empty() && GC.m_pkDatabaseLoadUtility == nullptr);
#endif
    if (failHeap) { --failHeap; SetLastError(ERROR_NOT_ENOUGH_MEMORY); return FALSE; }
    leakedAtHeapEnd += static_cast<unsigned>(allocations.size());
    const BOOL ok = ::HeapDestroy(heap);
    CHECK(ok != FALSE);
    allocations.clear(); heapAlive = false;
    return ok;
}
#define HeapAlloc ObservedHeapAlloc
#define HeapFree ObservedHeapFree
#define HeapDestroy ObservedHeapDestroy
#include "database_loader_fixture.h"
#undef HeapAlloc
#undef HeapFree
#undef HeapDestroy

// These game-specific cache operations are not covered by the ownership test.
bool CvDllDatabaseUtility::ValidateGameDatabase() { ++validations; return true; }
bool CvDllDatabaseUtility::LoadGlobalDefines() { return true; }
bool CvDllDatabaseUtility::PrefetchGameData() { ++prefetches; return true; }
bool CvDllDatabaseUtility::UpdatePlayableCivilizationCounts() { return true; }
bool CvDllDatabaseUtility::SetGlobalActionInfo() { return true; }
bool CvDllDatabaseUtility::PerformDatabasePostProcessing() { return true; }
void CvDllDatabaseUtility::LogMsg(const char*, ...) const {}

struct Host final : ICvEngineUtility4 {
    void* DLLCALL QueryInterface(GUID) override { return nullptr; }
    void UninitGlobals() override {
        CHECK(queryStops != 0 && heapAlive);
#ifndef DATABASE_LOADER_ORIGINAL
        CHECK(GC.m_pkDatabaseLoadUtility == nullptr);
#endif
        ++hostStops;
    }
protected:
    void DLLCALL Destroy() override {
        CHECK(heapAlive);
#ifndef DATABASE_LOADER_ORIGINAL
        CHECK(allocations.empty() && GC.m_pkDatabaseLoadUtility == nullptr);
#endif
        // Stack-owned test host: observe the SDK release boundary without deletion.
    }
};
CvDllDatabaseUtility* Concrete(ICvDLLDatabaseUtility1* value) {
    return static_cast<CvDllDatabaseUtility*>(value);
}
void Release(ICvDLLDatabaseUtility1*& value) {
    ZeroSisHostBinding::Release(value); value = nullptr;
}
void Begin(Host& host) {
    CHECK(!heapAlive && allocations.empty() && GC.m_pkDatabaseLoadUtility == nullptr);
    CvDllGameContext::s_hHeap = ::HeapCreate(0, 0, 0);
    CHECK(CvDllGameContext::s_hHeap != nullptr);
    heapAlive = true;
    CvDllGameContext::s_pSingleton = new CvDllGameContext;
    GC.host = &host;
}
void Rule(int id) {
    CHECK(testDatabase.Execute("DELETE FROM Rules"));
    Database::Results insert;
    CHECK(testDatabase.Execute(insert, "INSERT INTO Rules(ID,Type) VALUES(?,'RULE')"));
    CHECK(insert.Bind(1, id) && insert.Execute());
}
void Cache(ICvDLLDatabaseUtility1* value, int id) {
    const unsigned before = prefetches;
    CHECK(value->CacheGameDatabaseData());
    CHECK(prefetches == before + 1 && GC.types.at("RULE") == id);
    CHECK(value->CacheGameDatabaseData() && prefetches == before + 1);
}
int main() {
    CHECK(testDatabase.Open(":memory:", Database::OPEN_READWRITE | Database::OPEN_CREATE));
    CHECK(testDatabase.Execute("CREATE TABLE Rules(ID INTEGER,Type TEXT)"));
#ifdef DATABASE_LOADER_ORIGINAL
    Host host; Begin(host); Rule(1);
    auto* one = GC.getDatabaseLoadUtility();
    CHECK(Concrete(one)->GetReferenceCount() == 2); Cache(one, 1);
    auto* retained = one; Release(one);
    CLEANUP_FIXTURE(GC);
    CHECK(GC.m_pkDatabaseLoadUtility == retained && allocations.size() == 1 && freed == 0);
    Rule(2); auto* next = GC.getDatabaseLoadUtility();
    CHECK(next == retained && Concrete(next)->GetReferenceCount() == 2);
    CHECK(next->CacheGameDatabaseData() && prefetches == 1 && GC.types.at("RULE") == 1);
    Release(next);
    std::puts("ORIGINAL_UNINIT|retained_reference_not_released|cache_skips_changed_rules");
    CHECK(CvDllGameContext::ShutdownSingleton());
    CHECK(leakedAtHeapEnd == 1 && freed == 0 && GC.m_pkDatabaseLoadUtility == retained);
    // Observe but never dereference the pointer after its private heap is gone.
    GC.m_pkDatabaseLoadUtility = nullptr;
    std::puts("ORIGINAL_SHUTDOWN|heap_ends_with_live_loader|dangling_factory_pointer_not_dereferenced");
#else
    for (int cycle = 0; cycle < 64; ++cycle) {
        Host host; Begin(host); Rule(100 + cycle);
        auto* one = GC.getDatabaseLoadUtility();
        auto* two = GC.getDatabaseLoadUtility();
        CHECK(one == two && Concrete(one)->GetReferenceCount() == 3);
        GUID unsupported{}; CHECK(one->QueryInterface(unsupported) == nullptr);
        CHECK(Concrete(one)->GetReferenceCount() == 3);
        Cache(one, 100 + cycle);
        Release(two); Release(one);
        CLEANUP_FIXTURE(GC);
        CHECK(allocations.empty() && GC.m_pkDatabaseLoadUtility == nullptr);
        GC.releaseDatabaseLoadUtility(); // repeated owner release is harmless
        Rule(200 + cycle);
        one = GC.getDatabaseLoadUtility(); Cache(one, 200 + cycle);
        CHECK(Concrete(one)->GetReferenceCount() == 2);
        CLEANUP_FIXTURE(GC); // caller reference survives the GC-owned reference release
        CHECK(allocations.size() == 1 && Concrete(one)->GetReferenceCount() == 1);
        two = GC.getDatabaseLoadUtility();
        CHECK(two != one && Concrete(two)->GetReferenceCount() == 2);
        CHECK(Concrete(one)->GetReferenceCount() == 1);
        Cache(two, 200 + cycle);
        Release(one); Release(two);
        // Exercise factory-before-init cleanup: no matching uninit for this owner.
        CHECK(CvDllGameContext::ShutdownSingleton());
        CHECK(allocations.empty() && GC.m_pkDatabaseLoadUtility == nullptr);
        CHECK(CvDllGameContext::ShutdownSingleton());
    }
    std::puts("RESTART|64_cycles|fresh_cache_reads_changed_rules|separate_query_references_survive_owner_release");
    for (int attempt = 0; attempt < 16; ++attempt) {
        Host host; Begin(host); failAlloc = 1;
        try { GC.getDatabaseLoadUtility(); CHECK(false); } catch (const std::bad_alloc&) {}
        CHECK(GC.m_pkDatabaseLoadUtility == nullptr && allocations.empty());
        auto* one = GC.getDatabaseLoadUtility();
        CHECK(Concrete(one)->GetReferenceCount() == 2);
        Cache(one, 263);
        Rule(300 + attempt); CHECK(one->FlushGameDatabaseData()); Cache(one, 300 + attempt);
        Rule(263); Release(one);
        failHeap = 1;
        CHECK(!CvDllGameContext::ShutdownSingleton());
        CHECK(GetLastError() == ERROR_NOT_ENOUGH_MEMORY && heapAlive && allocations.empty());
        CHECK(GC.m_pkDatabaseLoadUtility == nullptr && GC.host == nullptr);
        CHECK(CvDllGameContext::ShutdownSingleton() && !heapAlive);
    }
    CHECK(leakedAtHeapEnd == 0 && freed == 208 && contextStops == 80 && hostStops == 128);
    CHECK(validations == prefetches && prefetches == 224);
    std::puts("FAILURE|16_allocation_failures_and_retry|16_heap_shutdown_failures_and_retry|208_exact_releases");
    std::puts("SHUTDOWN|context_then_loader_then_host_then_heap|factory_before_init|idempotent_owner_release");
#endif
    testDatabase.Close();
    std::puts("SCOPE|exact_sdk_refcounts_cache_and_lifecycle_bodies|real_private_heap_and_sqlite|instrumented_other_game_owners|no_gamecore_loaded");
    std::printf("PASS|%u\n", checks);
}
