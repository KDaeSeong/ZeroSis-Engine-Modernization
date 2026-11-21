#pragma once
#include <windows.h>
#include <climits>
#include <stdexcept>
#include <string>
#include <FireWorks/FDataStream.h>
#include <FireWorks/FTempHeap.h>

// The saved representation remains one SDK uint32 count followed by raw bytes.
// These functions manage the cache file and buffer, not the enclosing game/save
// transaction. The caller must discard a failed save and abort a failed load.
namespace CvEmbeddedDatabase {
struct NativeFiles {
    static HANDLE Open(const wchar_t* path) {
        return CreateFileW(path, GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE, NULL,
            OPEN_EXISTING, FILE_FLAG_SEQUENTIAL_SCAN, NULL);
    }
    static HANDLE Create(const wchar_t* path) {
        return CreateFileW(path, GENERIC_WRITE, 0, NULL, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, NULL);
    }
    static BOOL Size(HANDLE file, LARGE_INTEGER* size) { return GetFileSizeEx(file, size); }
    static BOOL Read(HANDLE file, void* data, DWORD size, DWORD* transferred) { return ReadFile(file, data, size, transferred, NULL); }
    static BOOL Write(HANDLE file, const void* data, DWORD size, DWORD* transferred) { return WriteFile(file, data, size, transferred, NULL); }
    static BOOL Flush(HANDLE file) { return FlushFileBuffers(file); }
    static BOOL Close(HANDLE file) { return CloseHandle(file); }
    static BOOL Replace(const wchar_t* from, const wchar_t* to) { return MoveFileExW(from, to, MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH); }
    static BOOL Remove(const wchar_t* path) { return DeleteFileW(path); }
};

inline void Fail(const char* operation) {
    const DWORD error = GetLastError();
    throw std::runtime_error(std::string("Embedded database ") + operation + " failed (Windows " + std::to_string(error) + ")");
}

template<class Files> class Handle {
public:
    explicit Handle(HANDLE value) : value_(value) {}
    ~Handle() { if (value_ != INVALID_HANDLE_VALUE) Files::Close(value_); }
    HANDLE get() const { return value_; }
    void Close() {
        if (value_ == INVALID_HANDLE_VALUE) return;
        if (!Files::Close(value_)) Fail("close");
        value_ = INVALID_HANDLE_VALUE;
    }
private:
    Handle(const Handle&);
    Handle& operator=(const Handle&);
    HANDLE value_;
};

template<class Files> class PreparedFile {
public:
    explicit PreparedFile(const std::wstring& destination)
        : destination_(destination), value_(INVALID_HANDLE_VALUE), owned_(false) {
        static volatile LONG sequence = 0;
        for (unsigned int attempt = 0; attempt < 128; ++attempt) {
            // CREATE_NEW is the authority for ownership, even after a PID is
            // reused or another module generated the same candidate filename.
            temporary_ = destination_ + L".zerosis-tmp-" + std::to_wstring(GetCurrentProcessId())
                + L"-" + std::to_wstring(static_cast<unsigned long>(InterlockedIncrement(&sequence)));
            value_ = Files::Create(temporary_.c_str());
            if (value_ != INVALID_HANDLE_VALUE) { owned_ = true; return; }
            const DWORD error = GetLastError();
            if (error != ERROR_FILE_EXISTS && error != ERROR_ALREADY_EXISTS) Fail("temporary create");
        }
        SetLastError(ERROR_FILE_EXISTS); Fail("temporary name reservation");
    }
    ~PreparedFile() {
        if (value_ != INVALID_HANDLE_VALUE) Files::Close(value_);
        if (owned_) Files::Remove(temporary_.c_str());
    }
    HANDLE get() const { return value_; }
    void Commit() {
        if (!Files::Flush(value_)) Fail("flush");
        if (!Files::Close(value_)) Fail("temporary close");
        value_ = INVALID_HANDLE_VALUE;
        if (!Files::Replace(temporary_.c_str(), destination_.c_str())) Fail("replace");
        owned_ = false;
    }
private:
    PreparedFile(const PreparedFile&);
    PreparedFile& operator=(const PreparedFile&);
    std::wstring destination_, temporary_;
    HANDLE value_;
    bool owned_;
};

template<class Files> void WriteFileToStream(FDataStream& stream, const std::wstring& path) {
    HANDLE opened = Files::Open(path.c_str());
    if (opened == INVALID_HANDLE_VALUE) {
        const DWORD error = GetLastError();
        if (error != ERROR_FILE_NOT_FOUND && error != ERROR_PATH_NOT_FOUND) Fail("open");
        stream << static_cast<unsigned int>(0);
        return;
    }
    Handle<Files> file(opened);
    LARGE_INTEGER nativeSize;
    if (!Files::Size(file.get(), &nativeSize)) Fail("size");
    if (nativeSize.QuadPart < 0 || static_cast<unsigned long long>(nativeSize.QuadPart) > UINT_MAX)
        throw std::length_error("Embedded database exceeds the existing uint32 save field");
    const unsigned int size = static_cast<unsigned int>(nativeSize.QuadPart);
    FTempArray<byte, c_eMPoolTypeGame, 0> buffer(size);
    unsigned int offset = 0;
    while (offset < size) {
        DWORD count = 0;
        if (!Files::Read(file.get(), buffer.get() + offset, size - offset, &count)) Fail("read");
        if (!count || count > size - offset) throw std::runtime_error("Embedded database ended before its recorded size");
        offset += count;
    }
    LARGE_INTEGER after;
    if (!Files::Size(file.get(), &after)) Fail("size recheck");
    if (after.QuadPart != nativeSize.QuadPart) throw std::runtime_error("Embedded database size changed while saving");
    file.Close();
    // Allocation and file-read failures occur before any database field bytes
    // are written. A stream failure still invalidates the enclosing save.
    stream << size;
    if (size && stream.WriteIt(size, buffer.get()) != size)
        throw std::runtime_error("Short embedded database stream write");
}

template<class Files> void ReadStreamToFile(FDataStream& stream, const std::wstring& path, unsigned int size) {
    if (!size) return; // Preserve the SDK's absent-payload behavior.
    if (size > stream.GetSizeLeft()) throw std::out_of_range("Embedded database extends past the saved stream");
    FTempArray<byte, c_eMPoolTypeGame, 0> buffer(size);
    if (stream.ReadIt(size, buffer.get()) != size) throw std::runtime_error("Short embedded database stream read");
    // The old cache stays untouched until a complete, flushed replacement has
    // been prepared in the same directory and all handles are closed.
    PreparedFile<Files> file(path);
    unsigned int offset = 0;
    while (offset < size) {
        DWORD count = 0;
        if (!Files::Write(file.get(), buffer.get() + offset, size - offset, &count)) Fail("write");
        if (!count || count > size - offset) throw std::runtime_error("Short embedded database file write");
        offset += count;
    }
    file.Commit();
}

inline void Write(FDataStream& stream, const std::wstring& path) { WriteFileToStream<NativeFiles>(stream, path); }
inline void Read(FDataStream& stream, const std::wstring& path, unsigned int size) { ReadStreamToFile<NativeFiles>(stream, path, size); }
}
