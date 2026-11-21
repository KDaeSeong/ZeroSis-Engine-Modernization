#include "SdkDebugHelper.h"
#include <array>
#include <climits>
#include <cwchar>
#include <mutex>
#include <new>
#include <vector>

namespace {
ZeroSisDebug::DebugApi nativeApi;
ZeroSisDebug::DebugApi* api = &nativeApi;
std::recursive_mutex mutex;
ZeroSisDebug::Status status;
HANDLE symbolProcess = nullptr;
using Guard = std::lock_guard<std::recursive_mutex>;

bool Fail(DWORD error = GetLastError()) noexcept {
    status.lastError = error ? error : ERROR_GEN_FAILURE;
    ++status.failures;
    SetLastError(status.lastError);
    return false;
}
bool Success() noexcept {
    status.lastError = ERROR_SUCCESS;
    SetLastError(ERROR_SUCCESS);
    return true;
}
bool Ready(HANDLE& process) noexcept {
    if (status.initialized) return true;
    if (!process) {
        SetLastError(ERROR_SUCCESS);
        if (!api->OpenProcess(&process)) return Fail();
        if (!process || process == INVALID_HANDLE_VALUE) {
            process = nullptr;
            return Fail(ERROR_INVALID_HANDLE);
        }
        status.ownsProcessHandle = true;
    }
    SetLastError(ERROR_SUCCESS);
    if (!api->Initialize(process)) return Fail();
    status.initialized = true;
    symbolProcess = process;
    return Success();
}
bool Buffer(char* name, unsigned capacity) noexcept {
    if (!name || !capacity || capacity > INT_MAX) return Fail(ERROR_INVALID_PARAMETER);
    name[0] = '\0';
    return true;
}
bool Copy(const wchar_t* text, char* name, unsigned capacity) noexcept {
    if (!text) return Fail(ERROR_INVALID_DATA);
    const int bytes = WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, -1, nullptr, 0, nullptr, nullptr);
    if (!bytes) return Fail();
    if (static_cast<unsigned>(bytes) > capacity) return Fail(ERROR_INSUFFICIENT_BUFFER);
    if (!WideCharToMultiByte(CP_UTF8, WC_ERR_INVALID_CHARS, text, -1, name, static_cast<int>(capacity), nullptr, nullptr)) {
        name[0] = '\0';
        return Fail();
    }
    return Success();
}
DWORD64 Address(const CONTEXT& context) noexcept {
#ifdef _M_X64
    return context.Rip;
#else
    return context.Eip;
#endif
}
bool FinishWalk(unsigned frames, ZeroSisDebug::WalkStop stop, DWORD error = ERROR_SUCCESS) {
    Guard guard(mutex);
    ++status.walks;
    status.lastWalkFrames = frames;
    status.lastWalkStop = stop;
    return error ? Fail(error) : Success();
}
struct WalkUse {
    bool held = false;
    ~WalkUse() {
        if (held) { Guard guard(mutex); --status.activeWalks; }
    }
};
}

BOOL ZeroSisDebug::DebugApi::OpenProcess(HANDLE* result) noexcept {
    return DuplicateHandle(GetCurrentProcess(), GetCurrentProcess(), GetCurrentProcess(), result, 0, FALSE, DUPLICATE_SAME_ACCESS);
}
BOOL ZeroSisDebug::DebugApi::CloseProcess(HANDLE process) noexcept { return CloseHandle(process); }
BOOL ZeroSisDebug::DebugApi::Initialize(HANDLE process) noexcept {
    // DbgHelp options are process-wide; the host must route all users through
    // this owner. Avoid environment search paths, prompts, and symbol servers.
    SymSetOptions(SYMOPT_UNDNAME | SYMOPT_LOAD_LINES | SYMOPT_FAIL_CRITICAL_ERRORS |
                  SYMOPT_NO_PROMPTS | SYMOPT_IGNORE_NT_SYMPATH | SYMOPT_NO_IMAGE_SEARCH);
    return SymInitializeW(process, L"", FALSE);
}
BOOL ZeroSisDebug::DebugApi::Cleanup(HANDLE process) noexcept { return SymCleanup(process); }
BOOL ZeroSisDebug::DebugApi::NativeModule(HANDLE process, HMODULE module, MODULEINFO* info) noexcept {
    return GetModuleInformation(process, module, info, sizeof(*info));
}
DWORD ZeroSisDebug::DebugApi::ModulePath(HMODULE module, wchar_t* path, DWORD capacity) noexcept {
    return GetModuleFileNameW(module, path, capacity);
}
BOOL ZeroSisDebug::DebugApi::Modules(HANDLE process, HMODULE* modules, DWORD bytes, DWORD* needed) noexcept {
    return EnumProcessModulesEx(process, modules, bytes, needed, LIST_MODULES_ALL);
}
DWORD64 ZeroSisDebug::DebugApi::Load(HANDLE process, const wchar_t* path, DWORD64 base, DWORD size) noexcept {
    return SymLoadModuleExW(process, nullptr, path, nullptr, base, size, nullptr, 0);
}
BOOL ZeroSisDebug::DebugApi::ModuleInfo(HANDLE process, DWORD64 address, IMAGEHLP_MODULEW64* info) noexcept {
    return SymGetModuleInfoW64(process, address, info);
}
BOOL ZeroSisDebug::DebugApi::Unload(HANDLE process, DWORD64 base) noexcept { return SymUnloadModule64(process, base); }
BOOL ZeroSisDebug::DebugApi::Symbol(HANDLE process, DWORD64 address, SYMBOL_INFOW* info) noexcept {
    DWORD64 displacement = 0;
    return SymFromAddrW(process, address, &displacement, info);
}
BOOL ZeroSisDebug::DebugApi::Line(HANDLE process, DWORD64 address, IMAGEHLP_LINEW64* line) noexcept {
    DWORD displacement = 0;
    return SymGetLineFromAddrW64(process, address, &displacement, line);
}
BOOL ZeroSisDebug::DebugApi::Walk(DWORD machine, HANDLE process, HANDLE thread, STACKFRAME64* frame, CONTEXT* context) noexcept {
    return StackWalk64(machine, process, thread, frame, context, nullptr,
                       SymFunctionTableAccess64, SymGetModuleBase64, nullptr);
}

bool ZeroSisDebug::WalkCurrentThread(HANDLE process, const CONTEXT& context, StackVisitor visitor, void* user) {
    WalkUse use;
    {
        Guard guard(mutex);
        if (!visitor || (context.ContextFlags & CONTEXT_CONTROL) != CONTEXT_CONTROL || !Address(context)
#ifdef _M_X64
            || !context.Rsp
#else
            || !context.Esp
#endif
        ) return FinishWalk(0, WalkStop::InvalidInput, ERROR_INVALID_PARAMETER);
        if (!status.initialized || !process || process != symbolProcess)
            return FinishWalk(0, WalkStop::SessionUnavailable, ERROR_INVALID_STATE);
        ++status.activeWalks;
        use.held = true;
    }
    // StackWalk64 mutates CONTEXT. The caller's exception/capture record is immutable.
    CONTEXT working = context;
    STACKFRAME64 frame{};
    frame.AddrPC.Offset = Address(context);
#ifdef _M_X64
    constexpr DWORD machine = IMAGE_FILE_MACHINE_AMD64;
    frame.AddrStack.Offset = context.Rsp;
    frame.AddrFrame.Offset = context.Rbp;
#else
    constexpr DWORD machine = IMAGE_FILE_MACHINE_I386;
    frame.AddrStack.Offset = context.Esp;
    frame.AddrFrame.Offset = context.Ebp;
#endif
    frame.AddrPC.Mode = frame.AddrStack.Mode = frame.AddrFrame.Mode = AddrModeFlat;
    struct Identity { DWORD64 pc, stack; };
    std::array<Identity, MaxWalkFrames> visited{};
    unsigned count = 0;
    while (count < MaxWalkFrames) {
        BOOL advanced;
        DWORD error;
        {
            // Includes DbgHelp's function-table/module callbacks; shares the
            // symbol owner's lock. No client callback executes under this lock.
            Guard guard(mutex);
            SetLastError(ERROR_SUCCESS);
            advanced = api->Walk(machine, process, GetCurrentThread(), &frame, &working);
            error = GetLastError();
        }
        if (!advanced) {
            // DbgHelp usually leaves no error at either a natural end or an
            // unreadable frame. A partial trace must not claim complete unwinding.
            if (error || !count) return FinishWalk(count, WalkStop::BackendFailure, error ? error : ERROR_GEN_FAILURE);
            return FinishWalk(count, WalkStop::BackendStopped);
        }
        if (!frame.AddrPC.Offset) {
            if (!count) return FinishWalk(0, WalkStop::BackendFailure, ERROR_INVALID_DATA);
            return FinishWalk(count, WalkStop::BackendStopped);
        }
        if (!frame.AddrStack.Offset || frame.AddrPC.Mode != AddrModeFlat || frame.AddrStack.Mode != AddrModeFlat)
            return FinishWalk(count, WalkStop::BackendFailure, ERROR_INVALID_DATA);
        for (unsigned i = 0; i < count; ++i)
            if (visited[i].pc == frame.AddrPC.Offset && visited[i].stack == frame.AddrStack.Offset)
                return FinishWalk(count, WalkStop::RepeatedFrame, ERROR_INVALID_DATA);
        visited[count++] = {frame.AddrPC.Offset, frame.AddrStack.Offset};
        // Keep client mutation isolated from the native walker's frame.
        STACKFRAME64 observation = frame;
        try {
            if (!visitor(observation, user)) return FinishWalk(count, WalkStop::ConsumerStopped);
        } catch (...) {
            FinishWalk(count, WalkStop::ConsumerException, ERROR_EXCEPTION_IN_SERVICE);
            throw;
        }
    }
    return FinishWalk(count, WalkStop::DepthLimit, ERROR_MORE_DATA);
}

FDebugHelper* FDebugHelper::pInstance = nullptr;
FDebugHelper::FDebugHelper() : hCurrentProcess(nullptr), m_pExceptionTextCB(nullptr),
    m_pkCaptureStackBackTrace(&RtlCaptureStackBackTrace) {}
FDebugHelper::~FDebugHelper() = default;

FDebugHelper& FDebugHelper::GetInstance() {
    Guard guard(mutex);
    if (!pInstance) pInstance = new FDebugHelper();
    return *pInstance;
}

bool FDebugHelper::LoadSymbols(HMODULE module) {
    Guard guard(mutex);
    if (!module) return Fail(ERROR_INVALID_PARAMETER);
    if (!Ready(hCurrentProcess)) return false;
    MODULEINFO native{};
    SetLastError(ERROR_SUCCESS);
    if (!api->NativeModule(hCurrentProcess, module, &native)) return Fail();
    const DWORD64 base = reinterpret_cast<DWORD64>(native.lpBaseOfDll);
    if (base != reinterpret_cast<DWORD64>(module) || !native.SizeOfImage) return Fail(ERROR_INVALID_DATA);
    std::array<wchar_t, 32768> path{};
    SetLastError(ERROR_SUCCESS);
    const DWORD chars = api->ModulePath(module, path.data(), static_cast<DWORD>(path.size()));
    if (!chars) return Fail();
    if (chars >= path.size() || path[chars] != L'\0') return Fail(ERROR_FILENAME_EXCED_RANGE);
    SetLastError(ERROR_SUCCESS);
    const DWORD64 loaded = api->Load(hCurrentProcess, path.data(), base, native.SizeOfImage);
    const DWORD error = GetLastError();
    // DbgHelp returns 0/ERROR_SUCCESS for an already registered module.
    // Only a matching module record makes that idempotent success.
    if ((!loaded && error) || (loaded && loaded != base)) return Fail(error ? error : ERROR_INVALID_DATA);
    IMAGEHLP_MODULEW64 record{};
    record.SizeOfStruct = sizeof(record);
    SetLastError(ERROR_SUCCESS);
    if (!api->ModuleInfo(hCurrentProcess, base, &record)) return Fail();
    if (record.BaseOfImage != base || record.ImageSize != native.SizeOfImage) return Fail(ERROR_INVALID_DATA);
    ++status.moduleLoads;
    return Success();
}

bool FDebugHelper::LoadSymbols() {
    Guard guard(mutex);
    if (!Ready(hCurrentProcess)) return false;
    try {
        std::vector<HMODULE> modules(128);
        DWORD needed = 0;
        for (unsigned attempt = 0; attempt < 4; ++attempt) {
            SetLastError(ERROR_SUCCESS);
            const DWORD bytes = static_cast<DWORD>(modules.size() * sizeof(HMODULE));
            if (!api->Modules(hCurrentProcess, modules.data(), bytes, &needed)) return Fail();
            if (!needed || needed % sizeof(HMODULE)) return Fail(ERROR_INVALID_DATA);
            if (needed <= bytes) {
                for (size_t i = 0; i < needed / sizeof(HMODULE); ++i) {
                    if (!LoadSymbols(modules[i])) return false;
                }
                return Success();
            }
            if (needed / sizeof(HMODULE) > 4096) return Fail(ERROR_BUFFER_OVERFLOW);
            modules.resize(needed / sizeof(HMODULE));
        }
        return Fail(ERROR_RETRY);
    } catch (const std::bad_alloc&) { return Fail(ERROR_NOT_ENOUGH_MEMORY); }
}

void FDebugHelper::UnloadSymbols(HMODULE module) {
    Guard guard(mutex);
    if (!module) { Fail(ERROR_INVALID_PARAMETER); return; }
    if (!status.initialized) { Fail(ERROR_INVALID_STATE); return; }
    SetLastError(ERROR_SUCCESS);
    if (!api->Unload(hCurrentProcess, reinterpret_cast<DWORD64>(module))) { Fail(); return; }
    Success();
}

bool FDebugHelper::GetSymbolName(DWORD64 address, TCHAR* name, unsigned capacity) {
    Guard guard(mutex);
    if (!Buffer(name, capacity)) return false;
    if (!status.initialized || !address) return Fail(ERROR_INVALID_ADDRESS);
    alignas(SYMBOL_INFOW) std::array<unsigned char, sizeof(SYMBOL_INFOW) + 4096 * sizeof(wchar_t)> storage{};
    auto* symbol = reinterpret_cast<SYMBOL_INFOW*>(storage.data());
    symbol->SizeOfStruct = sizeof(*symbol);
    symbol->MaxNameLen = 4096;
    SetLastError(ERROR_SUCCESS);
    if (!api->Symbol(hCurrentProcess, address, symbol)) return Fail();
    if (symbol->NameLen >= 4096 || symbol->Name[symbol->NameLen] != L'\0') return Fail(ERROR_INVALID_DATA);
    return Copy(symbol->Name, name, capacity);
}
bool FDebugHelper::GetSymbolName(const CONTEXT& context, TCHAR* name, unsigned capacity) {
    return GetSymbolName(Address(context), name, capacity);
}

bool FDebugHelper::GetSymbolFileLine(DWORD64 address, TCHAR* name, DWORD* number, unsigned capacity) {
    Guard guard(mutex);
    if (number) *number = 0;
    if (!Buffer(name, capacity)) return false;
    if (!number) return Fail(ERROR_INVALID_PARAMETER);
    if (!status.initialized || !address) return Fail(ERROR_INVALID_ADDRESS);
    IMAGEHLP_LINEW64 line{};
    line.SizeOfStruct = sizeof(line);
    SetLastError(ERROR_SUCCESS);
    if (!api->Line(hCurrentProcess, address, &line)) return Fail();
    if (!line.LineNumber) return Fail(ERROR_INVALID_DATA);
    if (!Copy(line.FileName, name, capacity)) return false;
    *number = line.LineNumber;
    return Success();
}
bool FDebugHelper::GetSymbolFileLine(const CONTEXT& context, TCHAR* name, DWORD* number, unsigned capacity) {
    return GetSymbolFileLine(Address(context), name, number, capacity);
}

bool FDebugHelper::GetModuleName(DWORD64 address, TCHAR* name, unsigned capacity) {
    Guard guard(mutex);
    if (!Buffer(name, capacity)) return false;
    if (!status.initialized || !address) return Fail(ERROR_INVALID_ADDRESS);
    IMAGEHLP_MODULEW64 module{};
    module.SizeOfStruct = sizeof(module);
    SetLastError(ERROR_SUCCESS);
    if (!api->ModuleInfo(hCurrentProcess, address, &module)) return Fail();
    if (!std::wmemchr(module.ModuleName, L'\0', sizeof(module.ModuleName) / sizeof(wchar_t))) return Fail(ERROR_INVALID_DATA);
    return Copy(module.ModuleName, name, capacity);
}

void FDebugHelper::DestroyDebugHelper() {
    Guard guard(mutex);
    if (status.activeWalks) { Fail(ERROR_BUSY); return; }
    if (!pInstance) { Success(); return; }
    if (status.initialized) {
        SetLastError(ERROR_SUCCESS);
        if (!api->Cleanup(pInstance->hCurrentProcess)) { Fail(); return; }
        status.initialized = false;
    }
    if (pInstance->hCurrentProcess) {
        SetLastError(ERROR_SUCCESS);
        if (!api->CloseProcess(pInstance->hCurrentProcess)) { Fail(); return; }
        pInstance->hCurrentProcess = nullptr;
        symbolProcess = nullptr;
        status.ownsProcessHandle = false;
    }
    delete pInstance;
    pInstance = nullptr;
    Success();
}

bool ZeroSisDebug::SetBackend(DebugApi* backend) noexcept {
    Guard guard(mutex);
    if (FDebugHelper::GetCurrentInstance()) return Fail(ERROR_BUSY);
    api = backend ? backend : &nativeApi;
    status = Status{};
    return Success();
}
ZeroSisDebug::Status ZeroSisDebug::GetStatus() noexcept { Guard guard(mutex); return status; }
bool ZeroSisDebug::Shutdown() noexcept {
    Guard guard(mutex);
    FDebugHelper::DestroyDebugHelper();
    return FDebugHelper::GetCurrentInstance() == nullptr;
}
