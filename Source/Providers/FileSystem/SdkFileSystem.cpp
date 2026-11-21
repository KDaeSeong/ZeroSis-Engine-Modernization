#include "SdkFileSystem.h"
#include <algorithm>
#include <atomic>
#include <climits>
#include <memory>
#include <new>
#include <vector>

namespace ZeroSisFileSystem {
HANDLE FileApi::Open(const wchar_t* p, DWORD a, DWORD s, DWORD c, DWORD f) noexcept {
    return CreateFileW(p, a, s, nullptr, c, f, nullptr);
}
BOOL FileApi::Read(HANDLE h, void* p, DWORD n, DWORD* done) noexcept { return ReadFile(h,p,n,done,nullptr); }
BOOL FileApi::Write(HANDLE h, const void* p, DWORD n, DWORD* done) noexcept { return WriteFile(h,p,n,done,nullptr); }
BOOL FileApi::Flush(HANDLE h) noexcept { return FlushFileBuffers(h); }
BOOL FileApi::Close(HANDLE h) noexcept { return CloseHandle(h); }
BOOL FileApi::Commit(const wchar_t* a, const wchar_t* b) noexcept {
    // Same-directory staging: never use COPY_ALLOWED or delete the old file first.
    return MoveFileExW(a,b,MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH);
}
BOOL FileApi::Remove(const wchar_t* p) noexcept { return DeleteFileW(p); }
FileApi& WindowsApi() { static FileApi api; return api; }

namespace {
FileErr Error(DWORD e) noexcept {
    switch(e) {
    case ERROR_SUCCESS: return FILE_OK;
    case ERROR_FILE_NOT_FOUND: case ERROR_PATH_NOT_FOUND: return FILE_NOTFOUND;
    case ERROR_FILE_EXISTS: case ERROR_ALREADY_EXISTS: return FILE_ALREADYEXISTS;
    case ERROR_INVALID_NAME: case ERROR_BAD_PATHNAME: case ERROR_FILENAME_EXCED_RANGE:
    case ERROR_NO_UNICODE_TRANSLATION: return FILE_BADNAME;
    case ERROR_INVALID_PARAMETER: case ERROR_INVALID_HANDLE: case ERROR_ACCESS_DENIED:
    case ERROR_SHARING_VIOLATION: case ERROR_NOT_SUPPORTED: return FILE_BADMODE;
    case ERROR_NEGATIVE_SEEK: case ERROR_SEEK: return FILE_BADSEEK;
    case ERROR_DISK_FULL: case ERROR_HANDLE_DISK_FULL: return FILE_DISKFULL;
    default: return FILE_CORRUPT;
    }
}
FileErr Report(DWORD e) noexcept { SetLastError(e); return Error(e); }

std::wstring Wide(const char* p) {
    if(!p || !*p) { SetLastError(ERROR_INVALID_NAME); return {}; }
    const int n=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,p,-1,nullptr,0);
    if(!n) return {};
    std::vector<wchar_t> out(static_cast<size_t>(n));
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,p,-1,out.data(),n)) return {};
    return out.data();
}
std::wstring Absolute(const wchar_t* p) {
    if(!p || !*p) { SetLastError(ERROR_INVALID_NAME); return {}; }
    if(!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,p,-1,nullptr,0,nullptr,nullptr)) return {};
    // Device namespaces and streams are outside the regular-file contract.
    std::wstring input(p);
    if(input.compare(0,4,L"\\\\.\\")==0) { SetLastError(ERROR_INVALID_NAME); return {}; }
    if(input.compare(0,4,L"\\\\?\\")==0) {
        if(input.compare(0,8,L"\\\\?\\UNC\\")!=0 &&
           !(input.size()>6 && input[5]==L':' && input[6]==L'\\')) {
            SetLastError(ERROR_INVALID_NAME); return {};
        }
    }
    const DWORD needed=GetFullPathNameW(p,0,nullptr,nullptr);
    if(!needed || needed>32760) { if(needed) SetLastError(ERROR_FILENAME_EXCED_RANGE); return {}; }
    std::vector<wchar_t> out(needed);
    const DWORD n=GetFullPathNameW(p,needed,out.data(),nullptr);
    if(!n || n>=needed) { if(n) SetLastError(ERROR_FILENAME_EXCED_RANGE); return {}; }
    std::wstring path(out.data(),n);
    const size_t colon=path.find(L':',path.compare(0,4,L"\\\\?\\")==0 ? 6 : 2);
    if(colon!=std::wstring::npos) { SetLastError(ERROR_INVALID_NAME); return {}; }
    if(path.compare(0,4,L"\\\\?\\")!=0) {
        if(path.compare(0,2,L"\\\\")==0) path=L"\\\\?\\UNC\\"+path.substr(2);
        else path=L"\\\\?\\"+path;
    }
    return path;
}

class Handle {
public:
    FileApi& api;
    HANDLE value=INVALID_HANDLE_VALUE;
    explicit Handle(FileApi& a) noexcept : api(a) {}
    ~Handle() { if(!Close()) Close(); }
    bool Close() noexcept {
        if(value==INVALID_HANDLE_VALUE) return true;
        if(!api.Close(value)) return false;
        value=INVALID_HANDLE_VALUE; return true;
    }
    Handle(const Handle&)=delete;
    Handle& operator=(const Handle&)=delete;
};

class NativeFile final : public FIFile {
public:
    explicit NativeFile(FileApi& a) noexcept : api_(a) {}
    ~NativeFile() override { Abandon(); } // Destruction never publishes a transaction.
    FileErr Open(const char* p, OpenMode mode, dword flags, uint buffer) override {
        try {
            const auto wide=Wide(p);
            if(wide.empty()) return Fail(GetLastError());
            return Open(wide.c_str(),mode,flags,buffer);
        } catch(...) { return Fail(ERROR_NOT_ENOUGH_MEMORY); }
    }
    FileErr Open(const wchar* p, OpenMode mode, dword flags, uint) override {
        if(IsOpen()) return Fail(ERROR_INVALID_HANDLE);
        Abandon(); error_=ERROR_SUCCESS; position_=length_=0; name_.clear();
        if(mode!=modeRead && mode!=modeWrite && mode!=modeEdit) return Fail(ERROR_INVALID_PARAMETER);
        // Typed endian conversion, text encoding and asynchronous I/O belong to
        // different contracts. Never silently accept an unimplemented flag.
        if(flags & ~(FFILE_FLAG_RANDOM_ACCESS | FFILE_FLAG_HIDE_ERRORS)) return Fail(ERROR_NOT_SUPPORTED);
        mode_=mode;
        try {
            name_=Absolute(p);
            if(name_.empty()) return Fail(GetLastError());
            const DWORD attributes=FILE_ATTRIBUTE_NORMAL |
                ((flags&FFILE_FLAG_RANDOM_ACCESS) ? FILE_FLAG_RANDOM_ACCESS : FILE_FLAG_SEQUENTIAL_SCAN);
            if(mode==modeRead) {
                handle_=api_.Open(name_.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,OPEN_EXISTING,attributes);
                if(!IsOpen()) return Fail(GetLastError());
                if(!Measure()) { const auto e=error_; Abandon(); return Report(e); }
                SetLastError(ERROR_SUCCESS); return FILE_OK;
            }
            Handle source(api_);
            uint previousLength=0;
            if(mode==modeEdit) {
                source.value=api_.Open(name_.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,OPEN_EXISTING,attributes);
                if(source.value==INVALID_HANDLE_VALUE) return Fail(GetLastError());
                LARGE_INTEGER size{};
                if(GetFileType(source.value)!=FILE_TYPE_DISK || !GetFileSizeEx(source.value,&size))
                    return Fail(ERROR_INVALID_HANDLE);
                if(size.QuadPart<0 || size.QuadPart>UINT_MAX) return Fail(ERROR_FILE_TOO_LARGE);
                previousLength=static_cast<uint>(size.QuadPart);
            }
            const auto slash=name_.find_last_of(L'\\');
            const std::wstring parent=name_.substr(0,slash+1);
            static std::atomic<unsigned long long> serial{0};
            for(unsigned attempt=0;attempt<64;++attempt) {
                const auto candidate=parent+L".zerosis-txn-"+std::to_wstring(GetCurrentProcessId())+
                    L"-"+std::to_wstring(serial.fetch_add(1,std::memory_order_relaxed))+L".tmp";
                // Prepare all potentially throwing state before creating the file.
                temporary_=candidate;
                handle_=api_.Open(temporary_.c_str(),GENERIC_READ|GENERIC_WRITE,0,CREATE_NEW,attributes);
                if(IsOpen()) break;
                const DWORD e=GetLastError();
                temporary_.clear(); // Never delete a name whose creation failed.
                if(e!=ERROR_FILE_EXISTS && e!=ERROR_ALREADY_EXISTS) return Fail(e);
            }
            if(!IsOpen()) return Fail(ERROR_FILE_EXISTS);
            byte block[65536];
            uint remaining=previousLength;
            while(remaining) {
                const DWORD requested=(std::min)(remaining,static_cast<uint>(sizeof(block)));
                DWORD got=0;
                if(!api_.Read(source.value,block,requested,&got)) { Fail(GetLastError()); break; }
                if(!got || got>requested) { Fail(ERROR_READ_FAULT); break; }
                uint at=0;
                while(at<got) {
                    const uint written=Write(block+at,got-at);
                    if(!written) break;
                    at+=written;
                }
                if(error_!=ERROR_SUCCESS) break;
                remaining-=got;
            }
            if(error_==ERROR_SUCCESS && !source.Close()) Fail(GetLastError());
            if(error_!=ERROR_SUCCESS) { const DWORD e=error_; Abandon(); return Report(e); }
            position_=0; SetLastError(ERROR_SUCCESS); return FILE_OK;
        } catch(...) {
            Fail(ERROR_NOT_ENOUGH_MEMORY); Abandon(); return Report(error_);
        }
    }
    FileErr Close() override {
        if(!IsOpen()) return Report(error_);
        Unmap();
        const bool writing=mode_!=modeRead;
        if(writing && error_==ERROR_SUCCESS && !api_.Flush(handle_)) Fail(GetLastError());
        if(!api_.Close(handle_)) {
            Fail(GetLastError());
            // A close failure must not publish. Retry only while still owning
            // this handle; the backend contract leaves failed closes open.
            Abandon();
            return Report(error_);
        }
        handle_=INVALID_HANDLE_VALUE;
        if(writing && error_==ERROR_SUCCESS) {
            if(api_.Commit(temporary_.c_str(),name_.c_str())) temporary_.clear();
            else Fail(GetLastError());
        }
        Abandon();
        return Report(error_);
    }
    const wchar_t* GetFileName() override { return name_.c_str(); }
    byte* GetViewPtr() const override { return const_cast<NativeFile*>(this)->Map(); }
    byte* GetViewCaret() const override {
        byte* p=GetViewPtr();
        return p && position_<=length_ ? p+position_ : nullptr;
    }
    byte* GetViewEnd() const override { byte* p=GetViewPtr(); return p ? p+length_ : nullptr; }
    uint GetLength() const override { return length_; }
    void SetLength(uint n) override {
        if(!Writable()) return;
        if(n>length_) { ZeroExtend(n); return; }
        if(!At(n) || !SetEndOfFile(handle_)) { Fail(GetLastError()); return; }
        length_=n; // Preserve the logical cursor, even beyond a truncated end.
        SetLastError(ERROR_SUCCESS);
    }
    bool IsOpen() const override { return handle_!=INVALID_HANDLE_VALUE; }
    bool IsMapped() const override { return view_!=nullptr; }
    uint Seek(long offset, SeekMode origin) override {
        if(!IsOpen()) { Fail(ERROR_INVALID_HANDLE); return UINT_MAX; }
        long long base=0;
        if(origin==current) base=position_;
        else if(origin==end) base=length_;
        else if(origin!=begin) { Fail(ERROR_INVALID_PARAMETER); return UINT_MAX; }
        const long long next=base+offset;
        if(next<0 || next>UINT_MAX) { Fail(ERROR_NEGATIVE_SEEK); return UINT_MAX; }
        position_=static_cast<uint>(next); SetLastError(ERROR_SUCCESS); return position_;
    }
    uint SeekToBegin() override { return Seek(0,begin); }
    uint SeekToEnd() override { return Seek(0,end); }
    uint GetPosition() override { return position_; }
    void Rewind() override { SeekToBegin(); }
    bool IsEOF() override { return position_>=length_; }
    uint Read(void* p, uint n) override {
        if(!IsOpen() || mode_==modeWrite || (n && !p)) { Fail(ERROR_INVALID_PARAMETER); return 0; }
        if(error_!=ERROR_SUCCESS) { SetLastError(error_); return 0; }
        if(position_>=length_ || !n) { SetLastError(ERROR_SUCCESS); return 0; }
        const DWORD wanted=(std::min)(n,length_-position_);
        DWORD got=0;
        if(!At(position_) || !api_.Read(handle_,p,wanted,&got)) { Fail(GetLastError()); return 0; }
        if(!got || got>wanted) { Fail(ERROR_READ_FAULT); return 0; }
        position_+=got; SetLastError(ERROR_SUCCESS); return got;
    }
    uint Write(const void* p, uint n) override {
        if(!Writable()) return 0;
        if(n && !p) { Fail(ERROR_INVALID_PARAMETER); return 0; }
        if(n>UINT_MAX-position_) { Fail(ERROR_FILE_TOO_LARGE); return 0; }
        if(!n) { SetLastError(ERROR_SUCCESS); return 0; }
        if(position_>length_ && !ZeroExtend(position_)) return 0;
        DWORD done=0;
        if(!At(position_) || !api_.Write(handle_,p,n,&done)) { Fail(GetLastError()); return 0; }
        if(!done || done>n) { Fail(ERROR_WRITE_FAULT); return 0; }
        position_+=done; length_=(std::max)(length_,position_);
        SetLastError(ERROR_SUCCESS); return done;
    }
    uint Flush() override {
        if(!IsOpen()) { Fail(ERROR_INVALID_HANDLE); return 0; }
        if(error_!=ERROR_SUCCESS) { SetLastError(error_); return 0; }
        if(mode_!=modeRead && !api_.Flush(handle_)) { Fail(GetLastError()); return 0; }
        SetLastError(ERROR_SUCCESS); return 1;
    }
private:
    FileApi& api_;
    HANDLE handle_=INVALID_HANDLE_VALUE, mapping_=nullptr;
    byte* view_=nullptr;
    std::wstring name_,temporary_;
    OpenMode mode_=modeRead;
    uint position_=0,length_=0;
    DWORD error_=ERROR_SUCCESS;

    FileErr Fail(DWORD e) noexcept {
        if(!e) e=ERROR_GEN_FAILURE;
        if(error_==ERROR_SUCCESS) error_=e;
        return Report(error_);
    }
    bool Measure() noexcept {
        LARGE_INTEGER n{};
        if(GetFileType(handle_)!=FILE_TYPE_DISK) { Fail(ERROR_INVALID_HANDLE); return false; }
        if(!GetFileSizeEx(handle_,&n)) { Fail(GetLastError()); return false; }
        if(n.QuadPart<0 || n.QuadPart>UINT_MAX) { Fail(ERROR_FILE_TOO_LARGE); return false; }
        length_=static_cast<uint>(n.QuadPart); return true;
    }
    bool At(uint n) noexcept {
        LARGE_INTEGER p{}; p.QuadPart=n;
        return SetFilePointerEx(handle_,p,nullptr,FILE_BEGIN)!=FALSE;
    }
    bool Writable() noexcept {
        if(error_!=ERROR_SUCCESS) { SetLastError(error_); return false; }
        if(!IsOpen() || mode_==modeRead) { Fail(ERROR_ACCESS_DENIED); return false; }
        return true;
    }
    bool ZeroExtend(uint target) noexcept {
        byte zero[65536]{};
        while(length_<target) {
            const DWORD wanted=(std::min)(target-length_,static_cast<uint>(sizeof(zero)));
            DWORD done=0;
            if(!At(length_) || !api_.Write(handle_,zero,wanted,&done)) { Fail(GetLastError()); return false; }
            if(!done || done>wanted) { Fail(ERROR_WRITE_FAULT); return false; }
            length_+=done;
        }
        SetLastError(ERROR_SUCCESS); return true;
    }
    byte* Map() noexcept {
        if(view_) return view_;
        if(!IsOpen() || mode_!=modeRead) { Fail(ERROR_NOT_SUPPORTED); return nullptr; }
        if(!length_) { SetLastError(ERROR_SUCCESS); return nullptr; }
        if(error_!=ERROR_SUCCESS) { SetLastError(error_); return nullptr; }
        mapping_=CreateFileMappingW(handle_,nullptr,PAGE_READONLY,0,0,nullptr);
        if(!mapping_) { Fail(GetLastError()); return nullptr; }
        view_=static_cast<byte*>(MapViewOfFile(mapping_,FILE_MAP_READ,0,0,0));
        if(!view_) { const DWORD e=GetLastError(); CloseHandle(mapping_); mapping_=nullptr; Fail(e); }
        return view_;
    }
    void Unmap() noexcept {
        if(view_) { UnmapViewOfFile(view_); view_=nullptr; }
        if(mapping_) { CloseHandle(mapping_); mapping_=nullptr; }
    }
    void Abandon() noexcept {
        Unmap();
        if(IsOpen()) { if(!api_.Close(handle_)) api_.Close(handle_); handle_=INVALID_HANDLE_VALUE; }
        if(!temporary_.empty()) { api_.Remove(temporary_.c_str()); temporary_.clear(); }
    }
};

class DefaultAllocator final : public FIFile::Allocator {
public:
    byte* Allocate(uint n) override { return new(std::nothrow) byte[n]; }
    void Delete(byte* p) override { delete[] p; }
};
NativeFileSystem& DefaultSystem() { static NativeFileSystem system; return system; }
} // namespace

FIFile* NativeFileSystem::Create(const wchar* name, FIFile::OpenMode mode, dword flags, uint buffer) {
    try {
        std::unique_ptr<NativeFile> result(new NativeFile(api_));
        if(name) result->Open(name,mode,flags,buffer);
        return result.release();
    } catch(...) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return nullptr; }
}
FIFile* NativeFileSystem::Create(const char* name, FIFile::OpenMode mode, dword flags, uint buffer) {
    try {
        std::unique_ptr<NativeFile> result(new NativeFile(api_));
        if(name) result->Open(name,mode,flags,buffer);
        return result.release();
    } catch(...) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return nullptr; }
}
FileErr NativeFileSystem::Delete(const wchar* p) {
    try { const auto path=Absolute(p); if(path.empty()) return Error(GetLastError());
        return api_.Remove(path.c_str()) ? Report(ERROR_SUCCESS) : Error(GetLastError());
    } catch(...) { return Report(ERROR_NOT_ENOUGH_MEMORY); }
}
FileErr NativeFileSystem::Delete(const char* p) {
    try { const auto path=Wide(p); return path.empty() ? Error(GetLastError()) : Delete(path.c_str()); }
    catch(...) { return Report(ERROR_NOT_ENOUGH_MEMORY); }
}
FileErr NativeFileSystem::ReadAll(const wchar* p, byte** output, size_t* size, dword flags, FIFile::Allocator& allocator) {
    if(output) *output=nullptr;
    if(size) *size=0;
    if(!output || !size) return Report(ERROR_INVALID_PARAMETER);
    byte* buffer=nullptr;
    try {
        NativeFile file(api_);
        const FileErr opened=file.Open(p,FIFile::modeRead,flags,FFILE_DEFAULT_BUFFER_SIZE);
        if(opened!=FILE_OK) return opened;
        const uint length=file.GetLength();
        if(length) {
            buffer=allocator.Allocate(length);
            if(!buffer) return Report(ERROR_NOT_ENOUGH_MEMORY);
        }
        uint at=0;
        while(at<length) {
            const uint done=file.Read(buffer+at,length-at);
            if(!done) {
                const DWORD e=GetLastError();
                allocator.Delete(buffer); buffer=nullptr; return Report(e ? e : ERROR_READ_FAULT);
            }
            at+=done;
        }
        const FileErr closed=file.Close();
        if(closed!=FILE_OK) {
            const DWORD e=GetLastError();
            if(buffer) allocator.Delete(buffer);
            return Report(e);
        }
        *output=buffer; *size=length; return Report(ERROR_SUCCESS);
    } catch(...) {
        if(buffer) allocator.Delete(buffer);
        return Report(ERROR_NOT_ENOUGH_MEMORY);
    }
}
FileErr NativeFileSystem::ReadAll(const char* p, byte** output, size_t* size, dword flags, FIFile::Allocator& allocator) {
    if(output) *output=nullptr;
    if(size) *size=0;
    try { const auto path=Wide(p); return path.empty() ? Error(GetLastError()) : ReadAll(path.c_str(),output,size,flags,allocator); }
    catch(...) { return Report(ERROR_NOT_ENOUGH_MEMORY); }
}
FileErr NativeFileSystem::ReadAll(const wchar* p, byte** output, size_t* size, dword flags) {
    DefaultAllocator allocator; return ReadAll(p,output,size,flags,allocator);
}
FileErr NativeFileSystem::ReadAll(const char* p, byte** output, size_t* size, dword flags) {
    DefaultAllocator allocator; return ReadAll(p,output,size,flags,allocator);
}
bool NativeFileSystem::Exist(const wchar* p) {
    try { const auto path=Absolute(p); if(path.empty()) return false;
        const DWORD a=GetFileAttributesW(path.c_str());
        return a!=INVALID_FILE_ATTRIBUTES && !(a&FILE_ATTRIBUTE_DIRECTORY);
    } catch(...) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return false; }
}
bool NativeFileSystem::Exist(const char* p) {
    try { const auto path=Wide(p); return !path.empty() && Exist(path.c_str()); }
    catch(...) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return false; }
}
uint NativeFileSystem::GetLength(const wchar* p) {
    NativeFile file(api_);
    if(file.Open(p,FIFile::modeRead,FFILE_FLAG_DEFAULT,FFILE_DEFAULT_BUFFER_SIZE)!=FILE_OK) return 0;
    const uint n=file.GetLength();
    return file.Close()==FILE_OK ? n : 0;
}
uint NativeFileSystem::GetLength(const char* p) {
    try { const auto path=Wide(p); return path.empty() ? 0 : GetLength(path.c_str()); }
    catch(...) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return 0; }
}
FFileTimestamp NativeFileSystem::GetLastWriteTime(const char* p) {
    FILETIME zero{};
    try {
        const auto wide=Wide(p);
        if(wide.empty()) return FFileTimestamp(zero);
        const auto path=Absolute(wide.c_str());
        if(path.empty()) return FFileTimestamp(zero);
        WIN32_FILE_ATTRIBUTE_DATA info{};
        if(!GetFileAttributesExW(path.c_str(),GetFileExInfoStandard,&info) || (info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY))
            return FFileTimestamp(zero);
        SetLastError(ERROR_SUCCESS); return FFileTimestamp(info.ftLastWriteTime);
    } catch(...) { SetLastError(ERROR_NOT_ENOUGH_MEMORY); return FFileTimestamp(zero); }
}
} // namespace ZeroSisFileSystem

namespace { SRWLOCK bindingLock=SRWLOCK_INIT; }
FIFileSystem* FIFileSystem::ms_pInstance=nullptr;
FIFileSystem& FIFileSystem::GetInstance() {
    AcquireSRWLockShared(&bindingLock);
    FIFileSystem* const instance=ms_pInstance;
    ReleaseSRWLockShared(&bindingLock);
    return instance ? *instance : FFileSystem::GetInstance();
}
void FIFileSystem::SetInstance(FIFileSystem* instance) {
    AcquireSRWLockExclusive(&bindingLock); ms_pInstance=instance; ReleaseSRWLockExclusive(&bindingLock);
}
FFileSystem& FFileSystem::GetInstance() { static FFileSystem system; return system; }
FFileInstance::FFileInstance(const char* p, FIFile::OpenMode m, dword f, uint b)
    : m_pkFile(FIFileSystem::GetInstance().Create(p,m,f,b)) { if(!m_pkFile) throw std::bad_alloc(); }
FFileInstance::FFileInstance(const wchar* p, FIFile::OpenMode m, dword f, uint b)
    : m_pkFile(FIFileSystem::GetInstance().Create(p,m,f,b)) { if(!m_pkFile) throw std::bad_alloc(); }
FFileInstance::~FFileInstance() {
    // SDK RAII facade preserves auto-close. Call Close explicitly to observe errors.
    try { if(m_pkFile && m_pkFile->IsOpen()) m_pkFile->Close(); } catch(...) {}
    delete m_pkFile;
}
#define FS ZeroSisFileSystem::DefaultSystem()
FIFile* FFileSystem::Create(const char* p,FIFile::OpenMode m,dword f,uint b){return FS.Create(p,m,f,b);}
FIFile* FFileSystem::Create(const wchar* p,FIFile::OpenMode m,dword f,uint b){return FS.Create(p,m,f,b);}
FileErr FFileSystem::Delete(const char* p){return FS.Delete(p);}
FileErr FFileSystem::Delete(const wchar* p){return FS.Delete(p);}
FileErr FFileSystem::ReadAll(const char* p,byte** b,size_t* n,dword f){return FS.ReadAll(p,b,n,f);}
FileErr FFileSystem::ReadAll(const wchar* p,byte** b,size_t* n,dword f){return FS.ReadAll(p,b,n,f);}
FileErr FFileSystem::ReadAll(const char* p,byte** b,size_t* n,dword f,FIFile::Allocator& a){return FS.ReadAll(p,b,n,f,a);}
FileErr FFileSystem::ReadAll(const wchar* p,byte** b,size_t* n,dword f,FIFile::Allocator& a){return FS.ReadAll(p,b,n,f,a);}
bool FFileSystem::Exist(const char* p){return FS.Exist(p);}
bool FFileSystem::Exist(const wchar* p){return FS.Exist(p);}
uint FFileSystem::GetLength(const char* p){return FS.GetLength(p);}
uint FFileSystem::GetLength(const wchar* p){return FS.GetLength(p);}
FFileTimestamp FFileSystem::GetLastWriteTime(const char* p){return FS.GetLastWriteTime(p);}
bool FFileSystem::IsFileCatalogEnabled(){return FS.IsFileCatalogEnabled();}
FFileErrorHandler* FFileSystem::GetErrorHandler(){return FS.GetErrorHandler();}
#undef FS
