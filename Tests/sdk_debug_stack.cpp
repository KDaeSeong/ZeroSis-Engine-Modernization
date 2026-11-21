#include "SdkDebugHelper.h"
#include <algorithm>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
std::atomic<unsigned> checks{0}, traces{0};
void Check(bool ok, unsigned line) {
    ++checks;
    if (!ok) { std::printf("FAIL|%u|error=%lu\n", line, GetLastError()); std::fflush(stdout); std::exit(2); }
}
#define CHECK(x) Check(!!(x), __LINE__)
unsigned originalCalls = 0;
bool originalContextNull = false;
BOOL WINAPI RecordOriginalWalk(DWORD machine, HANDLE, HANDLE, LPSTACKFRAME64, PVOID context,
    PREAD_PROCESS_MEMORY_ROUTINE64, PFUNCTION_TABLE_ACCESS_ROUTINE64,
    PGET_MODULE_BASE_ROUTINE64, PTRANSLATE_ADDRESS_ROUTINE64) {
    ++originalCalls;
    originalContextNull = machine == IMAGE_FILE_MACHINE_AMD64 && context == nullptr;
    return FALSE;
}
class OriginalWalkFixture {
public:
    HANDLE hCurrentProcess = GetCurrentProcess();
    template<class Function> void WalkStack(const CONTEXT& context, Function Func);
};
#define StackWalk64 RecordOriginalWalk
#include "original_stack_walk.inl"
#undef StackWalk64

enum class Mode { Native, Empty, AccessDenied, ZeroPc, ZeroStack, Repeat, Cycle, Infinite, EndAfterTwo, FailAfterTwo };
class Backend final : public ZeroSisDebug::DebugApi {
public:
    Mode mode = Mode::Native;
    HANDLE owned = nullptr;
    std::atomic<unsigned> inflight{0}, overlap{0}, walkCalls{0}, symbolCalls{0}, invalid{0};
    unsigned sequence = 0;
    struct Entry {
        Backend& b;
        explicit Entry(Backend& value) : b(value) { if (b.inflight.fetch_add(1)) ++b.overlap; std::this_thread::yield(); }
        ~Entry() { --b.inflight; }
    };
    BOOL Initialize(HANDLE process) noexcept override {
        owned = process;
        return DebugApi::Initialize(process);
    }
    BOOL Symbol(HANDLE process, DWORD64 address, SYMBOL_INFOW* info) noexcept override {
        Entry entry(*this);
        ++symbolCalls;
        return DebugApi::Symbol(process, address, info);
    }
    BOOL Walk(DWORD machine, HANDLE process, HANDLE thread, STACKFRAME64* frame, CONTEXT* context) noexcept override {
        Entry entry(*this);
        ++walkCalls;
        if (machine != IMAGE_FILE_MACHINE_AMD64 || process != owned || process == GetCurrentProcess()
            || thread != GetCurrentThread() || !context || !context->Rip || !context->Rsp) ++invalid;
        if (mode == Mode::Native) return DebugApi::Walk(machine, process, thread, frame, context);
        const unsigned step = sequence++;
        context->Rip += 1; // The provider must preserve the caller's CONTEXT.
        SetLastError(ERROR_SUCCESS);
        if (mode == Mode::Empty) return FALSE;
        if (mode == Mode::AccessDenied || (mode == Mode::FailAfterTwo && step == 2)) {
            SetLastError(ERROR_ACCESS_DENIED); return FALSE;
        }
        if (mode == Mode::EndAfterTwo && step == 2) return FALSE;
        unsigned identity = step;
        if (mode == Mode::Repeat) identity = 0;
        if (mode == Mode::Cycle) identity %= 2;
        frame->AddrPC.Offset = mode == Mode::ZeroPc ? 0 : 0x123400000ull + identity * 16;
        frame->AddrStack.Offset = mode == Mode::ZeroStack ? 0 : 0x234500000ull + identity * 32;
        return TRUE;
    }
    void Reset(Mode value) { mode = value; sequence = 0; }
};

extern "C" __declspec(dllexport) __declspec(noinline) void ZeroSisStackLeaf(FDebugHelper& helper) {
    CONTEXT context{};
    RtlCaptureContext(&context);
    const CONTEXT saved = context;
    std::vector<std::string> names;
    bool highAddress = false;
    helper.WalkStack(context, [&](STACKFRAME64& frame) {
        char name[512]{};
        highAddress = highAddress || frame.AddrPC.Offset > 0xffffffffull;
        if (helper.GetSymbolName(frame.AddrPC.Offset, name, sizeof(name))) names.emplace_back(name);
        return true;
    });
    CHECK(std::memcmp(&context, &saved, sizeof(context)) == 0);
    const auto leaf = std::find(names.begin(), names.end(), "ZeroSisStackLeaf");
    const auto middle = std::find(names.begin(), names.end(), "ZeroSisStackMiddle");
    const auto root = std::find(names.begin(), names.end(), "ZeroSisStackRoot");
    CHECK(leaf != names.end() && middle != names.end() && root != names.end() && leaf < middle && middle < root);
    CHECK(highAddress);
    CHECK(ZeroSisDebug::GetStatus().lastWalkStop == ZeroSisDebug::WalkStop::BackendStopped);
    ++traces;
}
extern "C" __declspec(dllexport) __declspec(noinline) void ZeroSisStackMiddle(FDebugHelper& helper) { ZeroSisStackLeaf(helper); }
extern "C" __declspec(dllexport) __declspec(noinline) void ZeroSisStackRoot(FDebugHelper& helper) { ZeroSisStackMiddle(helper); }

void Boundaries(Backend& backend, FDebugHelper& helper) {
    CONTEXT context{};
    RtlCaptureContext(&context);
    const CONTEXT saved = context;
    struct Case { Mode mode; unsigned frames; ZeroSisDebug::WalkStop stop; DWORD error; };
    const Case cases[] = {
        {Mode::Empty, 0, ZeroSisDebug::WalkStop::BackendFailure, ERROR_GEN_FAILURE},
        {Mode::AccessDenied, 0, ZeroSisDebug::WalkStop::BackendFailure, ERROR_ACCESS_DENIED},
        {Mode::ZeroPc, 0, ZeroSisDebug::WalkStop::BackendFailure, ERROR_INVALID_DATA},
        {Mode::ZeroStack, 0, ZeroSisDebug::WalkStop::BackendFailure, ERROR_INVALID_DATA},
        {Mode::Repeat, 1, ZeroSisDebug::WalkStop::RepeatedFrame, ERROR_INVALID_DATA},
        {Mode::Cycle, 2, ZeroSisDebug::WalkStop::RepeatedFrame, ERROR_INVALID_DATA},
        {Mode::Infinite, ZeroSisDebug::MaxWalkFrames, ZeroSisDebug::WalkStop::DepthLimit, ERROR_MORE_DATA},
        {Mode::EndAfterTwo, 2, ZeroSisDebug::WalkStop::BackendStopped, ERROR_SUCCESS},
        {Mode::FailAfterTwo, 2, ZeroSisDebug::WalkStop::BackendFailure, ERROR_ACCESS_DENIED},
    };
    for (const Case& c : cases) {
        backend.Reset(c.mode);
        unsigned delivered = 0;
        helper.WalkStack(context, [&](STACKFRAME64& frame) {
            ++delivered;
            frame.AddrStack.Offset = 0; frame.AddrPC.Offset = 0;
            return true;
        });
        const auto state = ZeroSisDebug::GetStatus();
        CHECK(delivered == c.frames && state.lastWalkFrames == c.frames);
        CHECK(state.lastWalkStop == c.stop && state.lastError == c.error);
        CHECK(state.activeWalks == 0 && std::memcmp(&context, &saved, sizeof(context)) == 0);
    }
    for (int kind = 0; kind < 3; ++kind) {
        CONTEXT invalid = context;
        if (kind == 0) invalid.ContextFlags = 0;
        if (kind == 1) invalid.Rip = 0;
        if (kind == 2) invalid.Rsp = 0;
        const unsigned before = backend.walkCalls.load();
        helper.WalkStack(invalid, [](STACKFRAME64&) { CHECK(false); return true; });
        CHECK(backend.walkCalls == before && ZeroSisDebug::GetStatus().lastError == ERROR_INVALID_PARAMETER);
    }
    CHECK(!ZeroSisDebug::WalkCurrentThread(backend.owned, context, nullptr, nullptr));
    CHECK(!ZeroSisDebug::WalkCurrentThread(GetCurrentProcess(), context,
        [](STACKFRAME64&, void*) { return true; }, nullptr));
    CHECK(ZeroSisDebug::GetStatus().lastError == ERROR_INVALID_STATE);
    backend.Reset(Mode::Infinite);
    unsigned delivered = 0;
    helper.WalkStack(context, [&](STACKFRAME64&) { ++delivered; return false; });
    CHECK(delivered == 1 && backend.sequence == 1);
    CHECK(ZeroSisDebug::GetStatus().lastWalkStop == ZeroSisDebug::WalkStop::ConsumerStopped);
    bool caught = false;
    try { helper.WalkStack(context, [](STACKFRAME64&) -> bool { throw std::runtime_error("test callback"); }); }
    catch (const std::runtime_error&) { caught = true; }
    CHECK(caught && ZeroSisDebug::GetStatus().activeWalks == 0);
    CHECK(ZeroSisDebug::GetStatus().lastWalkStop == ZeroSisDebug::WalkStop::ConsumerException);
    // The callback must run outside the DbgHelp lock while its session stays leased.
    helper.WalkStack(context, [&](STACKFRAME64&) {
        CHECK(!ZeroSisDebug::Shutdown() && GetLastError() == ERROR_BUSY);
        CHECK(!ZeroSisDebug::SetBackend(nullptr) && GetLastError() == ERROR_BUSY);
        HANDLE done = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        CHECK(done != nullptr);
        std::thread worker([&helper, done] {
            char name[512]{};
            CHECK(helper.GetSymbolName(reinterpret_cast<DWORD64>(&ZeroSisStackLeaf), name, sizeof(name)));
            SetEvent(done);
        });
        CHECK(WaitForSingleObject(done, 5000) == WAIT_OBJECT_0);
        worker.join();
        CHECK(CloseHandle(done));
        return false;
    });
    CHECK(ZeroSisDebug::GetStatus().activeWalks == 0);
    std::printf("BOUNDARIES|9_backend_cases|3_invalid_contexts|cycle_depth_limits|private_context|callback_exception\n");
    std::printf("CALLBACK|unlocked_cross_thread_symbol_query|shutdown_busy|lease_released\n");
}
}

int main() {
    CHECK(sizeof(FDebugHelper) == 24 && sizeof(void*) == 8);
    CONTEXT context{};
    RtlCaptureContext(&context);
    OriginalWalkFixture original;
    original.WalkStack(context, [](STACKFRAME64&) { return true; });
    CHECK(originalCalls == 1 && originalContextNull);
    std::printf("ORIGINAL_WALK|actual_SDK_template|AMD64_context_is_null|instrumented_API_boundary\n");
    Backend backend;
    CHECK(ZeroSisDebug::SetBackend(&backend));
    auto& helper = FDebugHelper::GetInstance();
    helper.WalkStack(context, [](STACKFRAME64&) { CHECK(false); return true; });
    CHECK(ZeroSisDebug::GetStatus().lastError == ERROR_INVALID_STATE && backend.walkCalls == 0);
    CHECK(helper.LoadSymbols());
    ZeroSisStackRoot(helper);
    Boundaries(backend, helper);
    backend.Reset(Mode::Native);
    std::vector<std::thread> workers;
    for (unsigned i = 0; i < 8; ++i) workers.emplace_back([&helper] {
        for (unsigned trace = 0; trace < 32; ++trace) ZeroSisStackRoot(helper);
    });
    for (auto& worker : workers) worker.join();
    CHECK(traces == 257 && backend.overlap == 0 && backend.invalid == 0);
    CHECK(ZeroSisDebug::GetStatus().activeWalks == 0);
    CHECK(ZeroSisDebug::Shutdown());
    CHECK(ZeroSisDebug::SetBackend(nullptr));
    std::printf("NATIVE_STACK|257_traces|leaf_middle_root_order|addresses_above_4GiB|original_context_unchanged\n");
    std::printf("THREADS|8|256_stack_traces|mixed_symbol_walk|0_backend_overlap\n");
    std::printf("PASS|%u\n", checks.load());
    return 0;
}
