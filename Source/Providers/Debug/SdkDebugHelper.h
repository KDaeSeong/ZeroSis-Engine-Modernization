#pragma once
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <tchar.h>
#include <psapi.h>
#include <cstring>
#include <cstdint>
#include <FireWorks/Win32/FDebugHelper.h>
#ifdef _UNICODE
#error The BNW debug ABI currently uses narrow TCHAR; output strings are UTF-8.
#endif

namespace ZeroSisDebug {
// One owner must coordinate every DbgHelp user in the host process. None of
// these methods, initialization, or shutdown may run under the loader lock.
class DebugApi {
public:
    virtual ~DebugApi() = default;
    virtual BOOL OpenProcess(HANDLE* result) noexcept;
    virtual BOOL CloseProcess(HANDLE process) noexcept;
    virtual BOOL Initialize(HANDLE process) noexcept;
    virtual BOOL Cleanup(HANDLE process) noexcept;
    virtual BOOL NativeModule(HANDLE process, HMODULE module, MODULEINFO* info) noexcept;
    virtual DWORD ModulePath(HMODULE module, wchar_t* path, DWORD capacity) noexcept;
    virtual BOOL Modules(HANDLE process, HMODULE* modules, DWORD bytes, DWORD* needed) noexcept;
    virtual DWORD64 Load(HANDLE process, const wchar_t* path, DWORD64 base, DWORD size) noexcept;
    virtual BOOL ModuleInfo(HANDLE process, DWORD64 address, IMAGEHLP_MODULEW64* info) noexcept;
    virtual BOOL Unload(HANDLE process, DWORD64 base) noexcept;
    virtual BOOL Symbol(HANDLE process, DWORD64 address, SYMBOL_INFOW* info) noexcept;
    virtual BOOL Line(HANDLE process, DWORD64 address, IMAGEHLP_LINEW64* line) noexcept;
    virtual BOOL Walk(DWORD machine, HANDLE process, HANDLE thread, STACKFRAME64* frame, CONTEXT* context) noexcept;
};

constexpr unsigned MaxWalkFrames = 256;
enum class WalkStop {
    None, ConsumerStopped, BackendStopped, BackendFailure, InvalidInput,
    SessionUnavailable, RepeatedFrame, DepthLimit, ConsumerException
};
struct Status {
    bool initialized = false;
    bool ownsProcessHandle = false;
    DWORD lastError = ERROR_SUCCESS;
    std::uint64_t moduleLoads = 0;
    std::uint64_t failures = 0;
    std::uint64_t walks = 0;
    unsigned activeWalks = 0;
    unsigned lastWalkFrames = 0;
    WalkStop lastWalkStop = WalkStop::None;
};

// Backend replacement and destruction require quiescent SDK consumers.
// Replacement fails while a singleton (including failed cleanup) remains.
bool SetBackend(DebugApi* api) noexcept;
Status GetStatus() noexcept;
bool Shutdown() noexcept;
}
