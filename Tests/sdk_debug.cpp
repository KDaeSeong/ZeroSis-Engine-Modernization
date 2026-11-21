#include "SdkDebugHelper.h"
#include <array>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cwchar>
#include <thread>
#include <vector>

namespace {
std::atomic<unsigned> checks{0};
void Check(bool condition, unsigned line) {
    ++checks;
    if (!condition) {
        std::printf("FAIL|%u|error=%lu\n", line, GetLastError());
        std::fflush(stdout);
        std::exit(2);
    }
}
#define CHECK(x) Check(!!(x), __LINE__)
constexpr DWORD anchorFirst = __LINE__ + 1;
extern "C" __declspec(dllexport) __declspec(noinline) int ZeroSisDebugAnchor(int input) {
    volatile int value = input + 137;
    return value;
}
constexpr DWORD anchorLast = __LINE__ - 1;
DWORD64 Anchor() { return reinterpret_cast<DWORD64>(&ZeroSisDebugAnchor); }
HMODULE Module() { return GetModuleHandleW(nullptr); }

enum class Fault { None, Open, Initialize, NativeModule, Path, LongPath, Load, ZeroLoad,
    ModuleInfo, WrongBase, WrongSize, Cleanup, Close, Symbol, Line, ZeroLine, Unload,
    Modules, HugeModules, OddModules };

class Backend final : public ZeroSisDebug::DebugApi {
public:
    Fault fault = Fault::None;
    unsigned opens = 0, initializations = 0, cleanups = 0, closes = 0;
    bool uniqueHandle = true, unicodeSymbol = false;
    std::atomic<unsigned> inflight{0}, overlap{0}, queries{0};
    bool Take(Fault value) noexcept {
        if (fault != value) return false;
        fault = Fault::None;
        SetLastError(ERROR_SUCCESS);
        return true;
    }
    BOOL OpenProcess(HANDLE* result) noexcept override {
        ++opens;
        if (Take(Fault::Open)) return FALSE;
        const BOOL ok = DebugApi::OpenProcess(result);
        uniqueHandle = uniqueHandle && (!ok || (*result != GetCurrentProcess() && *result != INVALID_HANDLE_VALUE));
        return ok;
    }
    BOOL CloseProcess(HANDLE process) noexcept override {
        ++closes;
        return Take(Fault::Close) ? FALSE : DebugApi::CloseProcess(process);
    }
    BOOL Initialize(HANDLE process) noexcept override {
        ++initializations;
        return Take(Fault::Initialize) ? FALSE : DebugApi::Initialize(process);
    }
    BOOL Cleanup(HANDLE process) noexcept override {
        ++cleanups;
        return Take(Fault::Cleanup) ? FALSE : DebugApi::Cleanup(process);
    }
    BOOL NativeModule(HANDLE process, HMODULE module, MODULEINFO* info) noexcept override {
        return Take(Fault::NativeModule) ? FALSE : DebugApi::NativeModule(process, module, info);
    }
    DWORD ModulePath(HMODULE module, wchar_t* path, DWORD capacity) noexcept override {
        if (Take(Fault::Path)) return 0;
        if (Take(Fault::LongPath)) return capacity;
        return DebugApi::ModulePath(module, path, capacity);
    }
    DWORD64 Load(HANDLE process, const wchar_t* path, DWORD64 base, DWORD size) noexcept override {
        if (Take(Fault::Load)) { SetLastError(ERROR_ACCESS_DENIED); return 0; }
        if (Take(Fault::ZeroLoad)) return 0;
        return DebugApi::Load(process, path, base, size);
    }
    BOOL ModuleInfo(HANDLE process, DWORD64 address, IMAGEHLP_MODULEW64* info) noexcept override {
        if (Take(Fault::ModuleInfo)) return FALSE;
        const BOOL result = DebugApi::ModuleInfo(process, address, info);
        if (Take(Fault::WrongBase)) ++info->BaseOfImage;
        if (Take(Fault::WrongSize)) ++info->ImageSize;
        return result;
    }
    BOOL Unload(HANDLE process, DWORD64 base) noexcept override {
        return Take(Fault::Unload) ? FALSE : DebugApi::Unload(process, base);
    }
    BOOL Modules(HANDLE process, HMODULE* modules, DWORD bytes, DWORD* needed) noexcept override {
        if (Take(Fault::Modules)) return FALSE;
        if (Take(Fault::HugeModules)) { *needed = 4097 * sizeof(HMODULE); return TRUE; }
        if (Take(Fault::OddModules)) { *needed = 1; return TRUE; }
        return DebugApi::Modules(process, modules, bytes, needed);
    }
    BOOL Symbol(HANDLE process, DWORD64 address, SYMBOL_INFOW* info) noexcept override {
        if (Take(Fault::Symbol)) return FALSE;
        if (inflight.fetch_add(1) != 0) ++overlap;
        std::this_thread::yield();
        BOOL result;
        if (unicodeSymbol) {
            constexpr wchar_t text[] = L"\ud55c\uae00Symbol";
            std::wcscpy(info->Name, text);
            info->NameLen = static_cast<ULONG>(std::wcslen(text));
            result = TRUE;
        } else result = DebugApi::Symbol(process, address, info);
        ++queries;
        --inflight;
        return result;
    }
    BOOL Line(HANDLE process, DWORD64 address, IMAGEHLP_LINEW64* line) noexcept override {
        if (Take(Fault::Line)) return FALSE;
        const BOOL ok = DebugApi::Line(process, address, line);
        if (Take(Fault::ZeroLine)) line->LineNumber = 0;
        return ok;
    }
};

void SymbolsAndThreads() {
    Backend backend;
    CHECK(ZeroSisDebug::SetBackend(&backend));
    auto& helper = FDebugHelper::GetInstance();
    CHECK(!ZeroSisDebug::GetStatus().initialized && backend.opens == 0);
    CHECK(&helper == &FDebugHelper::GetInstance());
    CHECK(!helper.LoadSymbols(static_cast<HMODULE>(nullptr)));
    CHECK(GetLastError() == ERROR_INVALID_PARAMETER && backend.opens == 0);
    CHECK(helper.LoadSymbols(Module()));
    CHECK(helper.LoadSymbols(Module()));
    CHECK(backend.opens == 1 && backend.initializations == 1 && backend.uniqueHandle);
    CHECK(!ZeroSisDebug::SetBackend(nullptr) && GetLastError() == ERROR_BUSY);
    std::array<char, 4096> name{};
    CHECK(helper.GetSymbolName(Anchor(), name.data(), static_cast<unsigned>(name.size())));
    CHECK(std::strcmp(name.data(), "ZeroSisDebugAnchor") == 0);
    CONTEXT context{};
    context.Rip = Anchor();
    CHECK(helper.GetSymbolName(context, name.data(), static_cast<unsigned>(name.size())));
    CHECK(std::strcmp(name.data(), "ZeroSisDebugAnchor") == 0);
    DWORD number = 0;
    CHECK(helper.GetSymbolFileLine(Anchor(), name.data(), &number, static_cast<unsigned>(name.size())));
    CHECK(std::strstr(name.data(), "sdk_debug.cpp") != nullptr && number >= anchorFirst && number <= anchorLast);
    std::printf("SOURCE_LINE|%lu|%lu|%lu\n", number, anchorFirst, anchorLast);
    CHECK(helper.GetSymbolFileLine(context, name.data(), &number, static_cast<unsigned>(name.size())));
    CHECK(helper.GetModuleName(Anchor(), name.data(), static_cast<unsigned>(name.size())));
    CHECK(std::strstr(name.data(), "debug") != nullptr);
    char tinyBuffer[4] = {'x', 'y', 'z', 'w'};
    CHECK(!helper.GetSymbolName(Anchor(), tinyBuffer, 1));
    CHECK(GetLastError() == ERROR_INSUFFICIENT_BUFFER && tinyBuffer[0] == 0 && tinyBuffer[1] == 'y' && tinyBuffer[3] == 'w');
    CHECK(!helper.GetSymbolName(Anchor(), nullptr, 20));
    CHECK(!helper.GetSymbolName(Anchor(), tinyBuffer, 0) && GetLastError() == ERROR_INVALID_PARAMETER);
    CHECK(!helper.GetSymbolName(static_cast<DWORD64>(0), name.data(), static_cast<unsigned>(name.size())) && name[0] == 0);
    CHECK(!helper.GetSymbolFileLine(Anchor(), name.data(), nullptr, static_cast<unsigned>(name.size())) && name[0] == 0);
    backend.unicodeSymbol = true;
    CHECK(helper.GetSymbolName(Anchor(), name.data(), static_cast<unsigned>(name.size())));
    CHECK(std::strcmp(name.data(), u8"\ud55c\uae00Symbol") == 0);
    backend.unicodeSymbol = false;
    constexpr unsigned workers = 8, perWorker = 64;
    const unsigned before = backend.queries.load();
    std::vector<std::thread> threads;
    for (unsigned w = 0; w < workers; ++w) threads.emplace_back([&helper, perWorker] {
        for (unsigned i = 0; i < perWorker; ++i) {
            char symbol[128]{};
            CHECK(&FDebugHelper::GetInstance() == &helper);
            CHECK(helper.GetSymbolName(Anchor(), symbol, sizeof(symbol)));
            CHECK(std::strcmp(symbol, "ZeroSisDebugAnchor") == 0);
        }
    });
    for (auto& thread : threads) thread.join();
    CHECK(backend.queries == before + workers * perWorker && backend.overlap == 0);
    std::printf("THREADS|8|512_symbol_queries|0_backend_overlap\n");
    helper.UnloadSymbols(Module());
    CHECK(ZeroSisDebug::GetStatus().lastError == ERROR_SUCCESS);
    CHECK(!helper.GetSymbolName(Anchor(), name.data(), static_cast<unsigned>(name.size())) && name[0] == 0);
    CHECK(helper.LoadSymbols(Module()));
    CHECK(helper.GetSymbolName(Anchor(), name.data(), static_cast<unsigned>(name.size())));
    CHECK(helper.LoadSymbols());
    CHECK(ZeroSisDebug::Shutdown());
    CHECK(backend.cleanups == 1 && backend.closes == 1);
    CHECK(!ZeroSisDebug::GetStatus().initialized && !ZeroSisDebug::GetStatus().ownsProcessHandle);
    CHECK(ZeroSisDebug::Shutdown());
    CHECK(ZeroSisDebug::SetBackend(nullptr));
    std::printf("SYMBOLS|real_local_PDB|name_line_module|unload_reload|UTF8\n");
}

void Failures() {
    const Fault loadFaults[] = {Fault::Open, Fault::Initialize, Fault::NativeModule, Fault::Path,
        Fault::LongPath, Fault::Load, Fault::ZeroLoad, Fault::ModuleInfo, Fault::WrongBase, Fault::WrongSize};
    for (Fault fault : loadFaults) {
        Backend backend;
        CHECK(ZeroSisDebug::SetBackend(&backend));
        auto& helper = FDebugHelper::GetInstance();
        backend.fault = fault;
        CHECK(!helper.LoadSymbols(Module()));
        CHECK(GetLastError() != ERROR_SUCCESS && ZeroSisDebug::GetStatus().failures >= 1);
        CHECK(helper.LoadSymbols(Module()));
        CHECK(backend.uniqueHandle);
        CHECK(ZeroSisDebug::Shutdown());
        CHECK(backend.cleanups == 1 && backend.closes == 1);
        CHECK(ZeroSisDebug::SetBackend(nullptr));
    }
    for (Fault fault : {Fault::Cleanup, Fault::Close}) {
        Backend backend;
        CHECK(ZeroSisDebug::SetBackend(&backend));
        auto& helper = FDebugHelper::GetInstance();
        CHECK(helper.LoadSymbols(Module()));
        backend.fault = fault;
        CHECK(!ZeroSisDebug::Shutdown());
        CHECK(GetLastError() != ERROR_SUCCESS && ZeroSisDebug::GetStatus().ownsProcessHandle);
        CHECK(FDebugHelper::GetCurrentInstance() == &helper);
        CHECK(!ZeroSisDebug::SetBackend(nullptr));
        CHECK(ZeroSisDebug::Shutdown());
        CHECK(backend.cleanups == (fault == Fault::Cleanup ? 2u : 1u));
        CHECK(backend.closes == (fault == Fault::Close ? 2u : 1u));
        CHECK(ZeroSisDebug::SetBackend(nullptr));
    }
    for (Fault fault : {Fault::Symbol, Fault::Line, Fault::ZeroLine, Fault::Unload, Fault::Modules, Fault::HugeModules, Fault::OddModules}) {
        Backend backend;
        CHECK(ZeroSisDebug::SetBackend(&backend));
        auto& helper = FDebugHelper::GetInstance();
        CHECK(helper.LoadSymbols(Module()));
        backend.fault = fault;
        char name[4096] = "sentinel";
        DWORD number = 99;
        if (fault == Fault::Symbol) CHECK(!helper.GetSymbolName(Anchor(), name, sizeof(name)) && name[0] == 0);
        else if (fault == Fault::Line || fault == Fault::ZeroLine) CHECK(!helper.GetSymbolFileLine(Anchor(), name, &number, sizeof(name)) && name[0] == 0 && number == 0);
        else if (fault == Fault::Unload) helper.UnloadSymbols(Module());
        else CHECK(!helper.LoadSymbols());
        CHECK(GetLastError() != ERROR_SUCCESS);
        CHECK(helper.LoadSymbols(Module()));
        CHECK(helper.GetSymbolName(Anchor(), name, sizeof(name)));
        CHECK(ZeroSisDebug::Shutdown());
        CHECK(ZeroSisDebug::SetBackend(nullptr));
    }
    std::printf("FAULTS|19|failed_calls_reported|retry|cleanup_handle_retained\n");
}
}

int main() {
    CHECK(sizeof(void*) == 8 && sizeof(FDebugHelper) == 24);
    CHECK(ZeroSisDebugAnchor(5) == 142);
    SymbolsAndThreads();
    Failures();
    std::printf("PASS|%u\n", checks.load());
    return 0;
}
