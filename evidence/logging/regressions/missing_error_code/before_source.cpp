#include "SdkLogFile.h"
#include <algorithm>
#include <atomic>
#include <cstdarg>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <mutex>
#include <stdexcept>
#include <vector>

namespace ZeroSisLogging {
BOOL LogApi::Rename(const wchar_t* a,const wchar_t* b) noexcept {
    return MoveFileExW(a,b,MOVEFILE_WRITE_THROUGH); // Archive never overwrites.
}
BOOL LogApi::Console(const char* text,DWORD bytes) noexcept {
    HANDLE h=GetStdHandle(STD_OUTPUT_HANDLE);
    if(!h || h==INVALID_HANDLE_VALUE) {SetLastError(ERROR_INVALID_HANDLE);return FALSE;}
    DWORD mode=0,done=0;
    if(!GetConsoleMode(h,&mode)) return WriteFile(h,text,bytes,&done,nullptr) && done==bytes;
    try {
        const int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,static_cast<int>(bytes),nullptr,0);
        if(!size) return FALSE;
        std::vector<wchar_t> wide(static_cast<size_t>(size));
        if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text,static_cast<int>(bytes),wide.data(),size)) return FALSE;
        return WriteConsoleW(h,wide.data(),static_cast<DWORD>(size),&done,nullptr) && done==static_cast<DWORD>(size);
    } catch(...) {SetLastError(ERROR_NOT_ENOUGH_MEMORY);return FALSE;}
}
void LogApi::Time(SYSTEMTIME& time) noexcept {GetSystemTime(&time);}
LogApi& WindowsLogApi(){static LogApi api;return api;}

namespace {
constexpr size_t MaximumRecord=1024*1024;
constexpr uint ValidFlags=FILogFile::kDontTimeStamp|FILogFile::kDontFlushOnWrite|FILogFile::kWriteToConsole;
std::wstring Wide(const char* p) {
    if(!p) throw std::invalid_argument("Null log name");
    const int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,p,-1,nullptr,0);
    if(!size) throw std::invalid_argument("Invalid UTF-8 log name");
    std::vector<wchar_t> result(static_cast<size_t>(size));
    if(!MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,p,-1,result.data(),size)) throw std::invalid_argument("Invalid UTF-8 log name");
    return result.data();
}
bool Leaf(const wchar_t* p) noexcept {
    if(!p || !*p) return false;
    size_t n=0;
    for(;p[n];++n) if(n>=240 || p[n]<32 || std::wcschr(L"\\/:*?\"<>|",p[n])) return false;
    if(p[n-1]==L'.' || p[n-1]==L' ') return false;
    if(!WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,p,-1,nullptr,0,nullptr,nullptr)) return false;
    wchar_t prefix[8]{};size_t i=0;
    for(;i<7 && p[i] && p[i]!=L'.';++i) prefix[i]=p[i];
    if(!_wcsicmp(prefix,L"CON") || !_wcsicmp(prefix,L"PRN") || !_wcsicmp(prefix,L"AUX") || !_wcsicmp(prefix,L"NUL") ||
       (!_wcsnicmp(prefix,L"COM",3) && i==4 && prefix[3]>=L'1' && prefix[3]<=L'9') ||
       (!_wcsnicmp(prefix,L"LPT",3) && i==4 && prefix[3]>=L'1' && prefix[3]<=L'9')) return false;
    return true;
}
std::wstring Directory(const wchar_t* p) {
    if(!p || !*p) throw std::invalid_argument("Missing log directory");
    const DWORD count=GetFullPathNameW(p,0,nullptr,nullptr);
    if(!count || count>32000) throw std::invalid_argument("Invalid log directory");
    std::vector<wchar_t> text(count);
    if(!GetFullPathNameW(p,count,text.data(),nullptr)) throw std::invalid_argument("Invalid log directory");
    std::wstring path=text.data();
    if(path.compare(0,4,L"\\\\?\\")!=0) path=path.compare(0,2,L"\\\\")==0 ? L"\\\\?\\UNC\\"+path.substr(2) : L"\\\\?\\"+path;
    while(!path.empty() && (path.back()==L'\\' || path.back()==L'/'))path.pop_back();
    const DWORD attrs=GetFileAttributesW(path.c_str());
    if(attrs==INVALID_FILE_ATTRIBUTES || !(attrs&FILE_ATTRIBUTE_DIRECTORY)) throw std::invalid_argument("Log directory not found");
    return path;
}
void InvalidFormat(const wchar_t*,const wchar_t*,const wchar_t*,unsigned,uintptr_t) {}
class FormatGuard {
    _invalid_parameter_handler prior_;
public:
    FormatGuard():prior_(_set_thread_local_invalid_parameter_handler(InvalidFormat)){}
    ~FormatGuard(){_set_thread_local_invalid_parameter_handler(prior_);}
};
bool FormatAllowed(const char* text) noexcept {
    if(!text || strnlen_s(text,MaximumRecord+1)>MaximumRecord) return false;
    // Reject writes through varargs (%n), positional formats and runaway widths.
    // CRT performs remaining syntax validation under a scoped thread-local handler.
    for(const char* p=text;*p;++p) {
        if(*p!='%')continue;
        if(*++p=='%')continue;
        if(!*p)return false;
        while(*p && std::strchr("-+ #0",*p))++p;
        if(*p=='*')++p;
        else {size_t width=0;while(*p>='0' && *p<='9'){width=width*10+static_cast<unsigned>(*p++-'0');if(width>MaximumRecord)return false;}}
        if(*p=='.') {
            ++p;if(*p=='*')++p;
            else {size_t width=0;while(*p>='0' && *p<='9'){width=width*10+static_cast<unsigned>(*p++-'0');if(width>MaximumRecord)return false;}}
        }
        if(*p=='I') {++p;if(*p=='3' && p[1]=='2')p+=2;else if(*p=='6' && p[1]=='4')p+=2;}
        else if(*p=='h' || *p=='l'){const char length=*p++;if(*p==length)++p;}
        else if(*p && std::strchr("Lwztj",*p))++p;
        if(!*p || !std::strchr("diouxXaAeEfFgGcCsSp",*p))return false;
    }
    return true;
}
std::string Format(const char* text,va_list args) {
    if(!FormatAllowed(text)) throw std::invalid_argument("Invalid log format");
    FormatGuard guard;
    va_list countArgs;va_copy(countArgs,args);
    const int count=_vscprintf(text,countArgs);va_end(countArgs);
    if(count<0 || static_cast<size_t>(count)>MaximumRecord)throw std::invalid_argument("Log record too large");
    std::vector<char> data(static_cast<size_t>(count)+1);
    va_list writeArgs;va_copy(writeArgs,args);
    const int written=vsnprintf(data.data(),data.size(),text,writeArgs);va_end(writeArgs);
    if(written!=count)throw std::invalid_argument("Log format failed");
    return std::string(data.data(),static_cast<size_t>(count));
}
struct OrdinalLess {
    bool operator()(const std::wstring& a,const std::wstring& b) const noexcept {
        return CompareStringOrdinal(a.c_str(),-1,b.c_str(),-1,TRUE)==CSTR_LESS_THAN;
    }
};
class NativeLog final : public FILogFile {
public:
    NativeLog(LogApi& api,std::atomic<bool>& enabled,std::wstring path,uint flags,std::string title)
        :api_(api),enabled_(enabled),path_(std::move(path)),flags_(flags),title_(std::move(title)){}
    ~NativeLog() override {Close();}
    void Msg(const TCHAR* f,...) override {va_list a;va_start(a,f);Message("",f,a);va_end(a);}
    void DebugMsg(const TCHAR* f,...) override {va_list a;va_start(a,f);Message("[DEBUG] ",f,a);va_end(a);}
    void WarningMsg(const TCHAR* f,...) override {va_list a;va_start(a,f);Message("[WARNING] ",f,a);va_end(a);}
    void ErrorMsg(const TCHAR* f,...) override {va_list a;va_start(a,f);Message("[ERROR] ",f,a);va_end(a);}
    void SetFlags(uint flags) override {
        std::lock_guard<std::mutex> lock(mutex_);
        if(flags&~ValidFlags){Error(ERROR_INVALID_PARAMETER);return;}
        if(!Drain())return;
        flags_=flags;
    }
    uint GetFlags() const override {std::lock_guard<std::mutex> lock(mutex_);return flags_;}
    void SetBufSize(int bytes) override {
        std::lock_guard<std::mutex> lock(mutex_);
        if(bytes<0 || static_cast<size_t>(bytes)>MaximumRecord){Error(ERROR_INVALID_PARAMETER);return;}
        try {std::string next;next.reserve(static_cast<size_t>(bytes));if(!Drain())return;buffer_.swap(next);capacity_=static_cast<size_t>(bytes);}
        catch(...) {Error(ERROR_NOT_ENOUGH_MEMORY);}
    }
    LPCWSTR GetFileName() const override {return path_.c_str();}
    void Close() override {std::lock_guard<std::mutex> lock(mutex_);CloseUnlocked();}
    void Open() override {
        std::lock_guard<std::mutex> lock(mutex_);
        if(state_.retired || path_.empty()){Error(ERROR_INVALID_HANDLE);return;}
        if(!enabled_.load(std::memory_order_acquire)){Error(ERROR_NOT_READY);return;}
        if(handle_==INVALID_HANDLE_VALUE){state_.lastError=ERROR_SUCCESS;OpenUnlocked();}
    }
    void Archive(LPCWSTR leaf) override {
        std::lock_guard<std::mutex> lock(mutex_);
        if(state_.retired || path_.empty() || !Leaf(leaf)){Error(ERROR_INVALID_NAME);return;}
        try {
            const auto destination=path_.substr(0,path_.find_last_of(L'\\')+1)+leaf;
            if(CompareStringOrdinal(path_.c_str(),-1,destination.c_str(),-1,TRUE)==CSTR_EQUAL){Error(ERROR_INVALID_NAME);return;}
            if(!CloseUnlocked())return;
            if(!api_.Rename(path_.c_str(),destination.c_str())){Error(GetLastError());return;}
            state_.lastError=ERROR_SUCCESS; // Next message creates a new original name.
        } catch(...) {Error(ERROR_NOT_ENOUGH_MEMORY);}
    }
    Status Snapshot() const {
        std::lock_guard<std::mutex> lock(mutex_);Status s=state_;s.open=handle_!=INVALID_HANDLE_VALUE;return s;
    }
    void Retire() {std::lock_guard<std::mutex> lock(mutex_);CloseUnlocked();state_.retired=true;}
    void Reject(DWORD error) {std::lock_guard<std::mutex> lock(mutex_);Error(error);}
private:
    LogApi& api_;std::atomic<bool>& enabled_;const std::wstring path_;
    mutable std::mutex mutex_;
    HANDLE handle_=INVALID_HANDLE_VALUE;
    uint flags_;std::string title_,buffer_;size_t capacity_=0;
    Status state_;
    void Error(DWORD e) noexcept {state_.lastError=e?e:ERROR_GEN_FAILURE;SetLastError(state_.lastError);}
    bool OpenUnlocked() {
        if(handle_!=INVALID_HANDLE_VALUE)return true;
        if(state_.retired || path_.empty()){Error(ERROR_INVALID_HANDLE);return false;}
        handle_=api_.Open(path_.c_str(),GENERIC_READ|GENERIC_WRITE,FILE_SHARE_READ,OPEN_ALWAYS,FILE_ATTRIBUTE_NORMAL);
        if(handle_==INVALID_HANDLE_VALUE){Error(GetLastError());return false;}
        LARGE_INTEGER n{};
        if(!GetFileSizeEx(handle_,&n)){Error(GetLastError());return false;}
        if(n.QuadPart==0 && !title_.empty()) {
            std::string header=title_;if(header.back()!='\n')header+="\r\n";
            if(!Append(header,0,true))return false;
        }
        return true;
    }
    bool Append(const std::string& data,std::uint64_t records,bool flush) noexcept {
        LARGE_INTEGER start{};
        if(!GetFileSizeEx(handle_,&start) || !SetFilePointerEx(handle_,start,nullptr,FILE_BEGIN)){
            Error(GetLastError());state_.failed+=records;return false;
        }
        size_t at=0;DWORD failure=ERROR_SUCCESS;
        while(at<data.size()) {
            DWORD done=0;const DWORD n=static_cast<DWORD>(data.size()-at);
            if(!api_.Write(handle_,data.data()+at,n,&done)){failure=GetLastError();break;}
            if(!done || done>n){failure=ERROR_WRITE_FAULT;break;}
            at+=done;
        }
        if(!failure && flush && !api_.Flush(handle_))failure=GetLastError();
        if(failure) {
            // Exclusive writer sharing plus the per-log mutex allow truncation
            // back to the record/batch boundary after a partial append.
            if(!SetFilePointerEx(handle_,start,nullptr,FILE_BEGIN) || !SetEndOfFile(handle_))++state_.rollbackFailures;
            state_.failed+=records;Error(failure);return false;
        }
        state_.written+=records;state_.lastError=ERROR_SUCCESS;SetLastError(ERROR_SUCCESS);return true;
    }
    bool Drain() noexcept {
        if(buffer_.empty())return true;
        const auto count=state_.pending;
        const bool ok=Append(buffer_,count,true);
        buffer_.clear();state_.pending=0;return ok;
    }
    bool CloseUnlocked() noexcept {
        if(handle_==INVALID_HANDLE_VALUE)return state_.lastError==ERROR_SUCCESS;
        const bool drained=Drain();DWORD failure=state_.lastError;
        if(drained && !api_.Flush(handle_))failure=GetLastError();
        if(!api_.Close(handle_)){if(!failure)failure=GetLastError();api_.Close(handle_);}
        handle_=INVALID_HANDLE_VALUE;
        if(failure){Error(failure);return false;}
        return true;
    }
    void Message(const char* severity,const char* fmt,va_list args) noexcept {
        std::lock_guard<std::mutex> lock(mutex_);++state_.received;
        if(state_.retired || path_.empty()){++state_.failed;Error(ERROR_INVALID_HANDLE);return;}
        if(!enabled_.load(std::memory_order_acquire)){++state_.skipped;return;}
        try {
            std::string line=Format(fmt,args);
            std::string prefix;
            if(!(flags_&kDontTimeStamp)) {
                SYSTEMTIME t{};api_.Time(t);char timestamp[64]{};
                std::snprintf(timestamp,sizeof(timestamp),"[%04u-%02u-%02u %02u:%02u:%02u.%03u UTC] ",t.wYear,t.wMonth,t.wDay,t.wHour,t.wMinute,t.wSecond,t.wMilliseconds);
                prefix=timestamp;
            }
            line.insert(0,severity);line.insert(0,prefix);
            if(line.empty() || line.back()!='\n')line+="\r\n";
            if(line.size()>MaximumRecord){++state_.failed;Error(ERROR_BUFFER_OVERFLOW);return;}
            if(state_.lastError!=ERROR_SUCCESS){++state_.failed;SetLastError(state_.lastError);return;}
            if(!OpenUnlocked()){++state_.failed;return;}
            bool ok=true;
            if(capacity_ && (flags_&kDontFlushOnWrite) && line.size()<=capacity_) {
                if(buffer_.size()+line.size()>capacity_)ok=Drain();
                if(ok){buffer_+=line;++state_.pending;}
                else ++state_.failed;
            } else {
                if(!Drain()){++state_.failed;return;}
                ok=Append(line,1,!(flags_&kDontFlushOnWrite));
            }
            if(ok && (flags_&kWriteToConsole) && !api_.Console(line.data(),static_cast<DWORD>(line.size())))++state_.consoleErrors;
        } catch(const std::bad_alloc&) {++state_.failed;Error(ERROR_NOT_ENOUGH_MEMORY);}
        catch(...) {++state_.failed;Error(ERROR_INVALID_PARAMETER);}
    }
};
} // namespace

struct NativeLogManager::Impl {
    LogApi& api;
    std::atomic<bool> enabled{false};
    mutable std::mutex mutex;
    std::wstring root;
    NativeLog rejected;
    std::map<std::wstring,NativeLog*,OrdinalLess> active;
    std::vector<std::unique_ptr<NativeLog>> owned;
    explicit Impl(LogApi& a):api(a),rejected(a,enabled,L"",0,""){}
};
NativeLogManager::NativeLogManager(LogApi& api):impl_(new Impl(api)){}
NativeLogManager::~NativeLogManager()=default;
bool NativeLogManager::Configure(const wchar_t* p) noexcept {
    try {const auto path=Directory(p);std::lock_guard<std::mutex> lock(impl_->mutex);
        if(!impl_->owned.empty()){SetLastError(ERROR_BUSY);return false;}
        impl_->root=path;impl_->enabled.store(true,std::memory_order_release);SetLastError(ERROR_SUCCESS);return true;
    } catch(const std::bad_alloc&){SetLastError(ERROR_NOT_ENOUGH_MEMORY);return false;}
    catch(...){SetLastError(ERROR_INVALID_NAME);return false;}
}
Status NativeLogManager::GetStatus(const FILogFile* log) const noexcept {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    if(log==&impl_->rejected)return impl_->rejected.Snapshot();
    for(const auto& p:impl_->owned)if(p.get()==log)return p->Snapshot();
    Status result;result.lastError=ERROR_INVALID_HANDLE;return result;
}
void NativeLogManager::EnableLogging() {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    if(impl_->root.empty()){SetLastError(ERROR_NOT_READY);return;}
    impl_->enabled.store(true,std::memory_order_release);
}
void NativeLogManager::DisableLogging() {
    std::lock_guard<std::mutex> lock(impl_->mutex);impl_->enabled.store(false,std::memory_order_release);
    for(auto& p:impl_->owned)p->Close();
}
bool NativeLogManager::IsLoggingEnabled(){return impl_->enabled.load(std::memory_order_acquire);}
FILogFile* NativeLogManager::GetLog(LPCWSTR name,uint flags,const TCHAR* title) {
    try {
        if(!Leaf(name) || (flags&~ValidFlags) || (title && strnlen_s(title,MaximumRecord+1)>MaximumRecord))
            throw std::invalid_argument("Invalid log name, flags or title");
        std::lock_guard<std::mutex> lock(impl_->mutex);
        if(impl_->root.empty()){impl_->rejected.Reject(ERROR_NOT_READY);return &impl_->rejected;}
        auto existing=impl_->active.find(name);if(existing!=impl_->active.end())return existing->second;
        if(impl_->owned.size()>=4096){impl_->rejected.Reject(ERROR_TOO_MANY_OPEN_FILES);return &impl_->rejected;}
        std::unique_ptr<NativeLog> created(new NativeLog(impl_->api,impl_->enabled,impl_->root+L"\\"+name,flags,title?title:""));
        NativeLog* pointer=created.get();
        // Map insertion is prepared first; roll it back if the ownership vector fails.
        auto entry=impl_->active.emplace(name,pointer);
        try {impl_->owned.push_back(std::move(created));}catch(...){impl_->active.erase(entry.first);throw;}
        return pointer;
    } catch(const std::bad_alloc&){impl_->rejected.Reject(ERROR_NOT_ENOUGH_MEMORY);return &impl_->rejected;}
    catch(...){impl_->rejected.Reject(ERROR_INVALID_NAME);return &impl_->rejected;}
}
FILogFile* NativeLogManager::GetLog(LPCSTR name,uint flags,const TCHAR* title) {
    try {const auto wide=Wide(name);return GetLog(wide.c_str(),flags,title);}
    catch(const std::bad_alloc&){impl_->rejected.Reject(ERROR_NOT_ENOUGH_MEMORY);return &impl_->rejected;}
    catch(...){impl_->rejected.Reject(ERROR_INVALID_NAME);return &impl_->rejected;}
}
bool NativeLogManager::DeleteLog(FILogFile* log) {
    std::lock_guard<std::mutex> lock(impl_->mutex);
    for(auto i=impl_->active.begin();i!=impl_->active.end();++i)if(i->second==log){i->second->Retire();impl_->active.erase(i);return true;}
    return false;
}
bool NativeLogManager::DeleteLog(LPCWSTR name) {
    if(!name)return false;
    std::lock_guard<std::mutex> lock(impl_->mutex);const auto i=impl_->active.find(name);
    if(i==impl_->active.end())return false;
    i->second->Retire();impl_->active.erase(i);return true;
}
} // namespace ZeroSisLogging
namespace {
SRWLOCK logBindingLock=SRWLOCK_INIT;
ZeroSisLogging::NativeLogManager& DefaultLogs(){static ZeroSisLogging::NativeLogManager manager;return manager;}
}
FILogFileMgr* FILogFileMgr::ms_pInstance=nullptr;
FILogFileMgr* FILogFileMgr::PeekInstance(){
    AcquireSRWLockShared(&logBindingLock);FILogFileMgr* p=ms_pInstance;ReleaseSRWLockShared(&logBindingLock);return p;
}
FILogFileMgr& FILogFileMgr::GetInstance(){
    if(auto* p=PeekInstance())return *p;
    auto& fallback=DefaultLogs();
    AcquireSRWLockExclusive(&logBindingLock);
    if(!ms_pInstance)ms_pInstance=&fallback;
    FILogFileMgr* p=ms_pInstance;ReleaseSRWLockExclusive(&logBindingLock);return *p;
}
void ZeroSisLogging::NativeLogManager::Bind(NativeLogManager* manager) noexcept {
    AcquireSRWLockExclusive(&logBindingLock);ms_pInstance=manager;ReleaseSRWLockExclusive(&logBindingLock);
}
