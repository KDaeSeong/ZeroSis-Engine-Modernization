// Executes extracted SDK constructor/heap bodies with observable adapter types.
// This is a caller-boundary test, not construction of the full GameCore context.
#define NOMINMAX
#include <windows.h>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <new>
#include "ZeroSisHostBinding.h"
#include "ZeroSisGlobalsLifecycle.h"

namespace {
unsigned checks = 0, heapCreates = 0, heapDestroys = 0, heapAllocations = 0;
unsigned contextMemory = 0, liveAdapters = 0;
bool heapOwned = false, failCreate = false, failContext = false;
int failAllocationAt = -1, failConstructorAt = -1;
unsigned failDestroy = 0;
void Check(bool condition, unsigned line) {
    ++checks;
    if (!condition) { std::printf("FAIL|%u|%lu\n", line, GetLastError()); std::fflush(stdout); std::exit(2); }
}
#define CHECK(c) Check(!!(c), __LINE__)
HANDLE TestHeapCreate(DWORD flags, SIZE_T initial, SIZE_T maximum) {
    ++heapCreates;
    if (failCreate) { failCreate = false; SetLastError(ERROR_NOT_ENOUGH_MEMORY); return nullptr; }
    HANDLE heap = ::HeapCreate(flags, initial, maximum);
    if (heap) heapOwned = true;
    return heap;
}
BOOL TestHeapDestroy(HANDLE heap) {
    ++heapDestroys;
    if (failDestroy) { --failDestroy; SetLastError(ERROR_SUCCESS); return FALSE; }
    const BOOL ok = ::HeapDestroy(heap);
    if (ok) heapOwned = false;
    return ok;
}
void* TestHeapAlloc(HANDLE heap, DWORD flags, SIZE_T bytes) {
    const unsigned index = heapAllocations++;
    if (failAllocationAt >= 0 && index == static_cast<unsigned>(failAllocationAt)) {
        failAllocationAt = -1; SetLastError(ERROR_NOT_ENOUGH_MEMORY); return nullptr;
    }
    return ::HeapAlloc(heap, flags, bytes);
}
void ResetFaults() {
    heapCreates = heapDestroys = heapAllocations = 0;
    failCreate = failContext = false;
    failAllocationAt = failConstructorAt = -1; failDestroy = 0;
}
}

class CvDllGameContext;
// This component exercises context allocation with no attached host. The host
// binding component separately executes the real ICvUnknown release dispatcher.
struct ICvEngineUtility4 {
    static void operator delete(void*) { std::abort(); }
};
struct NullHostGlobals {
    void releaseDatabaseLoadUtility() {} // No loader in this context-only fixture.
    ICvEngineUtility4* getDLLIFace() { return nullptr; }
    void setDLLIFace(ICvEngineUtility4* p) { if (p) std::abort(); }
} GC;
template<unsigned Index> class Adapter {
public:
    Adapter() {
        if (failConstructorAt == static_cast<int>(Index)) { failConstructorAt = -1; throw std::bad_alloc(); }
        ++liveAdapters;
    }
    ~Adapter() { --liveAdapters; }
    static void* operator new(size_t bytes);
    static void operator delete(void* pointer);
};
using CvDllNetworkSyncronization = Adapter<0>;
using CvDllNetMessageHandler = Adapter<1>;
using CvDllScriptSystemUtility = Adapter<2>;
using CvDllWorldBuilderMapLoader = Adapter<3>;

class CvDllGameContext {
public:
    CvDllGameContext();
    ~CvDllGameContext() {
        delete m_pNetworkSyncronizer; delete m_pNetMessageHandler;
        delete m_pScriptSystemUtility; delete m_pWorldBuilderMapLoader;
    }
    static void InitializeSingleton();
    static void DestroySingleton();
#ifndef BOOTSTRAP_ORIGINAL
    static bool ShutdownSingleton();
#endif
    static void* Allocate(size_t bytes);
    static void Free(void* pointer) { CHECK(HeapFree(s_hHeap, 0, pointer)); }
    static void* operator new(size_t bytes) {
        if (failContext) { failContext = false; throw std::bad_alloc(); }
        void* pointer = ::operator new(bytes); ++contextMemory; return pointer;
    }
    static void operator delete(void* pointer) { --contextMemory; ::operator delete(pointer); }
    static CvDllGameContext* s_pSingleton;
    static HANDLE s_hHeap;
private:
    CvDllNetworkSyncronization* m_pNetworkSyncronizer;
    CvDllNetMessageHandler* m_pNetMessageHandler;
    CvDllScriptSystemUtility* m_pScriptSystemUtility;
    CvDllWorldBuilderMapLoader* m_pWorldBuilderMapLoader;
    unsigned m_uiRngCounter, m_uiNetInitInfoCounter, m_uiNetLoadGameInfoCounter;
};
template<unsigned Index> void* Adapter<Index>::operator new(size_t bytes) { return CvDllGameContext::Allocate(bytes); }
template<unsigned Index> void Adapter<Index>::operator delete(void* pointer) { CvDllGameContext::Free(pointer); }
CvDllGameContext* CvDllGameContext::s_pSingleton = nullptr;
HANDLE CvDllGameContext::s_hHeap = INVALID_HANDLE_VALUE;

#define HeapCreate TestHeapCreate
#define HeapDestroy TestHeapDestroy
#define HeapAlloc TestHeapAlloc
#define FAssert(value) CHECK(value)
#define FNEW(value, pool, tag) new value
#define SAFE_DELETE(value) do { delete (value); (value) = nullptr; } while (false)
#include "bootstrap_context_fixture.h"

int main(int argc, char**) {
#ifdef BOOTSTRAP_ORIGINAL
    if (argc == 1) {
        CvDllGameContext::InitializeSingleton();
        CvDllGameContext* first = CvDllGameContext::s_pSingleton;
        CvDllGameContext::InitializeSingleton();
        CHECK(first != CvDllGameContext::s_pSingleton && contextMemory == 2 && liveAdapters == 8);
        CvDllGameContext::DestroySingleton();
        std::printf("ORIGINAL_DUPLICATE|contexts=%u|adapters=%u|heap=%u\n", contextMemory, liveAdapters, heapOwned ? 1u : 0u);
    } else {
        failConstructorAt = 2;
        try { CvDllGameContext::InitializeSingleton(); CHECK(false); } catch (const std::bad_alloc&) {}
        CHECK(CvDllGameContext::s_pSingleton == nullptr && contextMemory == 0 && liveAdapters == 2 && heapOwned);
        std::printf("ORIGINAL_PARTIAL|contexts=%u|adapters=%u|heap=%u\n", contextMemory, liveAdapters, heapOwned ? 1u : 0u);
        TestHeapDestroy(CvDllGameContext::s_hHeap);
    }
    // The reference defect intentionally leaves adapter destructors uncalled.
    // Its isolated process exits; no game allocation or module was involved.
#else
    (void)argc;
    CHECK(CvDllGameContext::ShutdownSingleton());
    CvDllGameContext::InitializeSingleton();
    CvDllGameContext* first = CvDllGameContext::s_pSingleton;
    CvDllGameContext::InitializeSingleton();
    CHECK(first == CvDllGameContext::s_pSingleton && contextMemory == 1 && liveAdapters == 4 && heapCreates == 1);
    CHECK(CvDllGameContext::ShutdownSingleton());
    CHECK(CvDllGameContext::ShutdownSingleton());
    CHECK(contextMemory == 0 && liveAdapters == 0 && !heapOwned);
    unsigned failures = 0;
    for (int mode = 0; mode < 10; ++mode) {
        ResetFaults();
        if (mode == 0) failCreate = true;
        else if (mode == 1) failContext = true;
        else if (mode < 6) failAllocationAt = mode - 2;
        else failConstructorAt = mode - 6;
        try { CvDllGameContext::InitializeSingleton(); CHECK(false); } catch (const std::bad_alloc&) {}
        CHECK(contextMemory == 0 && liveAdapters == 0 && !heapOwned && CvDllGameContext::s_pSingleton == nullptr);
        CHECK(CvDllGameContext::s_hHeap == INVALID_HANDLE_VALUE);
        CvDllGameContext::InitializeSingleton();
        CHECK(CvDllGameContext::ShutdownSingleton());
        CHECK(contextMemory == 0 && liveAdapters == 0 && !heapOwned);
        ++failures;
    }
    ResetFaults(); failConstructorAt = 2; failDestroy = 2;
    try { CvDllGameContext::InitializeSingleton(); CHECK(false); } catch (const std::bad_alloc&) {}
    CHECK(contextMemory == 0 && liveAdapters == 0 && heapOwned);
    CHECK(!CvDllGameContext::ShutdownSingleton() && heapOwned);
    CHECK(CvDllGameContext::ShutdownSingleton() && !heapOwned);
    ResetFaults();
    CvDllGameContext::InitializeSingleton(); failDestroy = 1;
    CHECK(!CvDllGameContext::ShutdownSingleton());
    CHECK(heapOwned && CvDllGameContext::s_pSingleton == nullptr && contextMemory == 0 && liveAdapters == 0);
    try { CvDllGameContext::InitializeSingleton(); CHECK(false); } catch (const std::bad_alloc&) {}
    CHECK(CvDllGameContext::ShutdownSingleton() && !heapOwned);
    try { CvDllGameContext::Allocate(16); CHECK(false); } catch (const std::bad_alloc&) {}
    std::printf("CONTEXT_FAILURES|%u|all_four_adapter_allocations_and_constructors|clean_retry\n", failures);
    std::printf("CONTEXT_RECOVERY|idempotent|partial_constructor_no_leak|failed_heap_destroy_retained\n");
    std::printf("PASS|%u\n", checks);
#endif
    return 0;
}
