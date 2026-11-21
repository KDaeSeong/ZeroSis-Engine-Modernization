#pragma once
// The SDK ABI is unchanged. Narrow paths use strict UTF-8; wide paths use UTF-16.
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#include <string>
#include <FireWorks/FFireTypes.h>
#ifndef KILOBYTE
#define KILOBYTE 1024
#endif
#include <FireWorks/FFileSystem.h>

namespace ZeroSisFileSystem {
// A per-filesystem OS boundary, also used by deterministic failure tests.
// Overrides must not throw, and failed Commit must leave both names unchanged.
class FileApi {
public:
    virtual ~FileApi() = default;
    virtual HANDLE Open(const wchar_t*, DWORD access, DWORD share, DWORD creation, DWORD flags) noexcept;
    virtual BOOL Read(HANDLE, void*, DWORD, DWORD*) noexcept;
    virtual BOOL Write(HANDLE, const void*, DWORD, DWORD*) noexcept;
    virtual BOOL Flush(HANDLE) noexcept;
    virtual BOOL Close(HANDLE) noexcept;
    virtual BOOL Commit(const wchar_t* temporary, const wchar_t* destination) noexcept;
    virtual BOOL Remove(const wchar_t*) noexcept;
};
FileApi& WindowsApi();

// Files are single-owner objects. Independent files can be used concurrently.
// Callers serialize edits to the same destination and quiesce before rebinding.
class NativeFileSystem final : public FIFileSystem {
public:
    explicit NativeFileSystem(FileApi& api = WindowsApi()) noexcept : api_(api) {}
    FIFile* Create(const char* name = nullptr, FIFile::OpenMode mode = FIFile::modeRead,
        dword flags = FFILE_FLAG_DEFAULT, uint buffer = FFILE_DEFAULT_BUFFER_SIZE) override;
    FIFile* Create(const wchar* name, FIFile::OpenMode mode = FIFile::modeRead,
        dword flags = FFILE_FLAG_DEFAULT, uint buffer = FFILE_DEFAULT_BUFFER_SIZE) override;
    FileErr Delete(const char*) override;
    FileErr Delete(const wchar*) override;
    FileErr ReadAll(const char*, byte**, size_t*, dword = FFILE_FLAG_DEFAULT) override;
    FileErr ReadAll(const wchar*, byte**, size_t*, dword = FFILE_FLAG_DEFAULT) override;
    FileErr ReadAll(const char*, byte**, size_t*, dword, FIFile::Allocator&) override;
    FileErr ReadAll(const wchar*, byte**, size_t*, dword, FIFile::Allocator&) override;
    bool Exist(const char*) override;
    bool Exist(const wchar*) override;
    uint GetLength(const char*) override;
    uint GetLength(const wchar*) override;
    FFileTimestamp GetLastWriteTime(const char*) override;
    bool IsFileCatalogEnabled() override { return false; }
    FFileErrorHandler* GetErrorHandler() override { return nullptr; }
private:
    FileApi& api_;
};
} // namespace ZeroSisFileSystem

