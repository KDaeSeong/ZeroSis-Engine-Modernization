#pragma once
#include "../FileSystem/SdkFileSystem.h"
#include <tchar.h>
#include <FireWorks/FILogFile.h>
#include <cstdint>
#include <memory>
#ifdef _UNICODE
#error The current BNW GameCore logging ABI uses narrow TCHAR.
#endif

namespace ZeroSisLogging {
struct Status {
    std::uint64_t received=0,written=0,skipped=0,failed=0,pending=0;
    std::uint64_t consoleErrors=0,rollbackFailures=0;
    DWORD lastError=ERROR_SUCCESS;
    bool open=false,retired=false;
};
class LogApi : public ZeroSisFileSystem::FileApi {
public:
    virtual BOOL Rename(const wchar_t* from,const wchar_t* to) noexcept;
    virtual BOOL Console(const char* text,DWORD bytes) noexcept;
    virtual void Time(SYSTEMTIME& time) noexcept;
};
LogApi& WindowsLogApi();

class NativeLogManager final : public FILogFileMgr {
public:
    explicit NativeLogManager(LogApi& api=WindowsLogApi());
    ~NativeLogManager() override;
    // Configuration/binding and destruction require quiescent consumers.
    bool Configure(const wchar_t* existingDirectory) noexcept;
    static void Bind(NativeLogManager*) noexcept;
    Status GetStatus(const FILogFile*) const noexcept;
    void EnableLogging() override;
    void DisableLogging() override;
    FILogFile* GetLog(LPCWSTR,uint,const TCHAR* title=nullptr) override;
    FILogFile* GetLog(LPCSTR,uint,const TCHAR* title=nullptr) override;
    bool DeleteLog(FILogFile*) override;
    bool DeleteLog(LPCWSTR) override;
    bool IsLoggingEnabled() override;
private:
    struct Impl;
    std::unique_ptr<Impl> impl_;
};
} // namespace ZeroSisLogging

