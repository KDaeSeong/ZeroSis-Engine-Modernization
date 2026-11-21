// Execute extracted ownership callers without loading GameCore or game assets.
#define NOMINMAX
#include <windows.h>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <new>
#include <thread>
#include <vector>
#include "ZeroSisHostBinding.h"
#include "ZeroSisGlobalsLifecycle.h"
#define DLLCALL __stdcall
#include "host_binding_abi.h"

// Only QueryInterface/Destroy are exercised. Other engine service slots and the
// context's borrowers are instrumented; this is not a complete engine ABI test.
class ICvEngineUtility1 : public ICvUnknown {};
class ICvEngineUtility2 : public ICvEngineUtility1 {};
class ICvEngineUtility3 : public ICvEngineUtility2 {};
class ICvEngineUtility4 : public ICvEngineUtility3 {
public:
    static GUID DLLCALL GetInterfaceId() { return guidICvEngineUtility4; }
};
struct Globals {
    ICvEngineUtility4* current = nullptr;
    void releaseDatabaseLoadUtility() {} // Loader ownership is exercised in sdk_database_loader.cpp.
    ICvEngineUtility4* getDLLIFace() { return current; }
    void setDLLIFace(ICvEngineUtility4* value) { current = value; }
} GC;

std::atomic<unsigned> checks{0};
unsigned liveHosts = 0, destroyedHosts = 0, liveHeapHosts = 0, contextDestructions = 0;
unsigned heapAttempts = 0, failHeapDestroy = 0, callbackDenials = 0;
bool heapAlive = false, checkContextBorrower = false, reenterContext = false;
std::vector<unsigned> events;
void Check(bool ok, unsigned line) {
    ++checks;
    if (!ok) { std::printf("FAIL|%u|%lu\n", line, GetLastError()); std::fflush(stdout); std::exit(2); }
}
#define CHECK(c) Check(!!(c), __LINE__)

class CvDllGameContext {
public:
    static CvDllGameContext* s_pSingleton;
    static HANDLE s_hHeap;
    static bool SetDLLIFace(ICvEngineUtility1*);
    static bool ShutdownSingleton();
    ~CvDllGameContext();
};
CvDllGameContext* CvDllGameContext::s_pSingleton = nullptr;
HANDLE CvDllGameContext::s_hHeap = INVALID_HANDLE_VALUE;
struct BackendBase { virtual bool DestroyContext() noexcept = 0; };

void Reenter() {
    CHECK(!CvDllGameContext::SetDLLIFace(nullptr)); CHECK(GetLastError() == ERROR_BUSY);
    CHECK(!CvDllGameContext::ShutdownSingleton()); CHECK(GetLastError() == ERROR_BUSY);
    callbackDenials += 2;
}
CvDllGameContext::~CvDllGameContext() {
    ++contextDestructions; events.push_back(1);
    if (checkContextBorrower) CHECK(GC.getDLLIFace() != nullptr && liveHosts != 0 && heapAlive);
    if (reenterContext) Reenter();
}
BOOL TestHeapDestroy(HANDLE heap) {
    ++heapAttempts; events.push_back(3);
    CHECK(heapAlive && liveHeapHosts == 0);
    if (failHeapDestroy) { --failHeapDestroy; SetLastError(ERROR_NOT_ENOUGH_MEMORY); return FALSE; }
    const BOOL ok = ::HeapDestroy(heap);
    if (ok) heapAlive = false;
    return ok;
}
#define HeapDestroy TestHeapDestroy
#define SAFE_DELETE(value) do { delete (value); (value) = nullptr; } while (false)
#ifdef HOST_BINDING_ORIGINAL
// Preserve the historical SDK delete expression to observe this compiler's
// behavior. C5205 correctly diagnoses undefined nonvirtual-base deletion; the
// first diagnostic is retained in evidence. Candidate has no such exemption.
#pragma warning(push)
#pragma warning(disable: 5205)
#endif
#include "host_binding_fixture.h"
#ifdef HOST_BINDING_ORIGINAL
#pragma warning(pop)
#endif
#undef HeapDestroy

struct Host final : ICvEngineUtility4 {
    HANDLE heap;
    unsigned queries = 0;
    bool observe = false, reenter = false;
    ICvEngineUtility4* expected = nullptr;
    explicit Host(HANDLE h) : heap(h) { ++liveHosts; if (heap) ++liveHeapHosts; }
    void* DLLCALL QueryInterface(GUID id) override {
        CHECK(IsEqualGUID(id, guidICvEngineUtility4)); ++queries; return this;
    }
protected:
    void DLLCALL Destroy() override {
        if (observe) CHECK(GC.getDLLIFace() == expected);
        if (reenter) Reenter();
        events.push_back(2); ++destroyedHosts; --liveHosts;
        const HANDLE storage = heap;
        if (storage) { CHECK(heapAlive); --liveHeapHosts; }
        this->~Host();
        if (storage) CHECK(::HeapFree(storage, 0, this)); else ::operator delete(this);
    }
};
Host* MakeHost(bool privateHeap = false) {
    HANDLE heap = privateHeap ? CvDllGameContext::s_hHeap : nullptr;
    if (privateHeap) CHECK(heapAlive && heap != INVALID_HANDLE_VALUE);
    void* storage = heap ? ::HeapAlloc(heap, 0, sizeof(Host)) : ::operator new(sizeof(Host));
    CHECK(storage != nullptr);
    return ::new(storage) Host(heap);
}

struct Source final : ICvEngineUtility1 {
    Host* response = nullptr;
    unsigned queries = 0;
    bool throws = false, reenter = false;
    HANDLE entered = nullptr, resume = nullptr;
    void* DLLCALL QueryInterface(GUID id) override {
        CHECK(IsEqualGUID(id, guidICvEngineUtility4)); ++queries;
        if (reenter) Reenter();
        if (entered) { CHECK(SetEvent(entered)); CHECK(WaitForSingleObject(resume, 10000) == WAIT_OBJECT_0); }
        if (throws) throw std::bad_alloc();
        return response;
    }
protected:
    void DLLCALL Destroy() override { CHECK(false); } // Borrowed input, never owned.
};

void BeginContext() {
    CHECK(!heapAlive && CvDllGameContext::s_pSingleton == nullptr);
    CvDllGameContext::s_hHeap = ::HeapCreate(0, 0, 0);
    CHECK(CvDllGameContext::s_hHeap != nullptr);
    heapAlive = true;
    CvDllGameContext::s_pSingleton = new CvDllGameContext;
}

int main() {
    Backend backend;
#ifdef HOST_BINDING_ORIGINAL
    // Execute the historical delete-before-query path with separate inputs.
    // Never dereference its dangling result or invoke the unsafe self-alias case.
    Host* old = MakeHost(); GC.setDLLIFace(old);
    Source throwing; throwing.throws = true;
    try { CvDllGameContext::SetDLLIFace(&throwing); CHECK(false); } catch (const std::bad_alloc&) {}
    CHECK(GC.getDLLIFace() == old && liveHosts == 0 && destroyedHosts == 1);
    GC.setDLLIFace(nullptr);
    std::puts("ORIGINAL_THROW|old_released|published_pointer_dangling_not_dereferenced");
    GC.setDLLIFace(MakeHost()); Source unsupported;
    CHECK(!CvDllGameContext::SetDLLIFace(&unsupported));
    CHECK(GC.getDLLIFace() == nullptr && liveHosts == 0 && destroyedHosts == 2);
    std::puts("ORIGINAL_UNSUPPORTED|old_connection_lost");
    BeginContext(); old = MakeHost(); GC.setDLLIFace(old);
    CHECK(backend.DestroyContext());
    CHECK(GC.getDLLIFace() == nullptr && liveHosts == 1 && destroyedHosts == 2 && !heapAlive);
    std::puts("ORIGINAL_SHUTDOWN|owned_host_not_released");
    ZeroSisHostBinding::Release(old); // CRT allocation, valid after context heap exit.
#else
    CHECK(!CvDllGameContext::SetDLLIFace(nullptr) && GetLastError() == ERROR_SUCCESS);
    for (unsigned cycle = 0; cycle != 32; ++cycle) {
        Source attach; attach.response = MakeHost();
        CHECK(CvDllGameContext::SetDLLIFace(&attach) && attach.queries == 1);
        Host* old = attach.response;
        const unsigned before = destroyedHosts;
        CHECK(CvDllGameContext::SetDLLIFace(old) && old->queries == 0);
        Source alias; alias.response = old;
        CHECK(CvDllGameContext::SetDLLIFace(&alias) && alias.queries == 1);
        CHECK(destroyedHosts == before && GC.getDLLIFace() == old);
        Source unsupported;
        CHECK(!CvDllGameContext::SetDLLIFace(&unsupported) && GetLastError() == ERROR_NOT_SUPPORTED);
        CHECK(GC.getDLLIFace() == old && destroyedHosts == before);
        Source throwing; throwing.throws = true;
        try { CvDllGameContext::SetDLLIFace(&throwing); CHECK(false); } catch (const std::bad_alloc&) {}
        CHECK(GC.getDLLIFace() == old && destroyedHosts == before);
        Source replace; replace.response = MakeHost(); replace.reenter = true;
        old->observe = true; old->expected = replace.response; old->reenter = true;
        CHECK(CvDllGameContext::SetDLLIFace(&replace));
        CHECK(destroyedHosts == before + 1 && GC.getDLLIFace() == replace.response);
        replace.response->observe = true; replace.response->reenter = true;
        CHECK(!CvDllGameContext::SetDLLIFace(nullptr) && GetLastError() == ERROR_SUCCESS);
        CHECK(GC.getDLLIFace() == nullptr && destroyedHosts == before + 2 && liveHosts == 0);
    }
    std::puts("REPLACEMENT|32_cycles|unsupported_and_throw_preserve|identity_no_double_release|publish_before_destroy");
    // One query owns the gate; every competing mutation must fail without calling
    // the source, touching the context, or spinning on a lock held by callbacks.
    Source blocked; blocked.response = MakeHost();
    blocked.entered = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    blocked.resume = CreateEventW(nullptr, TRUE, FALSE, nullptr);
    CHECK(blocked.entered && blocked.resume);
    std::thread owner([&] { CHECK(CvDllGameContext::SetDLLIFace(&blocked)); });
    CHECK(WaitForSingleObject(blocked.entered, 10000) == WAIT_OBJECT_0);
    std::atomic<unsigned> rejected{0};
    std::vector<std::thread> workers;
    for (unsigned worker = 0; worker != 8; ++worker) workers.emplace_back([&] {
        for (unsigned call = 0; call != 32; ++call) {
            Source unused;
            CHECK(!CvDllGameContext::SetDLLIFace(&unused) && GetLastError() == ERROR_BUSY);
            CHECK(unused.queries == 0);
            CHECK(!CvDllGameContext::ShutdownSingleton() && GetLastError() == ERROR_BUSY);
            rejected += 2;
        }
    });
    for (auto& worker : workers) worker.join();
    CHECK(rejected == 512 && GC.getDLLIFace() == nullptr);
    CHECK(SetEvent(blocked.resume)); owner.join();
    CHECK(blocked.queries == 1 && GC.getDLLIFace() == blocked.response);
    CHECK(CloseHandle(blocked.entered)); CHECK(CloseHandle(blocked.resume));
    CHECK(!CvDllGameContext::SetDLLIFace(nullptr));
    std::puts("CONCURRENCY|8_workers|512_busy_rejections|query_called_once|gate_reusable");
    // An owned interface may itself reside in the context's real private heap.
    // Exercise callbacks and a failed HeapDestroy before a successful retry.
    for (unsigned fault = 0; fault != 2; ++fault) {
        BeginContext(); Host* host = MakeHost(true); GC.setDLLIFace(host);
        host->observe = true; host->reenter = true;
        checkContextBorrower = true; reenterContext = true;
        const unsigned releases = destroyedHosts, contexts = contextDestructions;
        events.clear(); failHeapDestroy = fault;
        const bool ok = backend.DestroyContext();
        CHECK(ok == (fault == 0));
        CHECK(events == std::vector<unsigned>({1, 2, 3}));
        CHECK(GC.getDLLIFace() == nullptr && liveHosts == 0 && liveHeapHosts == 0);
        CHECK(destroyedHosts == releases + 1 && contextDestructions == contexts + 1);
        CHECK(CvDllGameContext::s_pSingleton == nullptr && heapAlive == (fault != 0));
        if (fault) {
            CHECK(CvDllGameContext::s_hHeap != INVALID_HANDLE_VALUE);
            CHECK(GetLastError() == ERROR_NOT_ENOUGH_MEMORY);
            CHECK(backend.DestroyContext());
            CHECK(events == std::vector<unsigned>({1, 2, 3, 3}));
        }
        CHECK(CvDllGameContext::s_hHeap == INVALID_HANDLE_VALUE && !heapAlive);
        CHECK(backend.DestroyContext() && GetLastError() == ERROR_SUCCESS);
        CHECK(destroyedHosts == releases + 1 && contextDestructions == contexts + 1);
    }
    checkContextBorrower = reenterContext = false;
    // Binding without a context/heap also owns and must release the interface.
    GC.setDLLIFace(MakeHost()); CHECK(backend.DestroyContext());
    CHECK(liveHosts == 0 && GC.getDLLIFace() == nullptr);
    CHECK(callbackDenials == 200);
    std::puts("SHUTDOWN|context_then_host_then_heap|private_heap_host|failed_heap_retry|idempotent");
    std::puts("REENTRANCY|200_busy_rejections|query_release_context_callbacks");
#endif
    CHECK(liveHosts == 0 && liveHeapHosts == 0 && !heapAlive && GC.getDLLIFace() == nullptr);
    std::puts("SCOPE|exact_sdk_callers_and_release_dispatch|instrumented_host_context|no_gamecore_loaded");
    std::printf("PASS|%u\n", checks.load());
    return 0;
}
