#include "SdkLogFile.h"
#include <atomic>
#include <climits>
#include <cstdio>
#include <cstring>
#include <thread>
#include <vector>
#include <CvString.h>
#include "logging_callers_fixture.h"

static std::atomic<unsigned> checks{0};
#define CHECK(x) do{++checks;if(!(x)){std::fprintf(stderr,"FAIL|%d|%s|win32=%lu\n",__LINE__,#x,GetLastError());std::exit(2);}}while(0)
static std::wstring root;
static std::wstring Path(const wchar_t* n){return root+L"\\"+n;}
static std::string Read(const wchar_t* name){
    HANDLE h=CreateFileW(Path(name).c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);CHECK(h!=INVALID_HANDLE_VALUE);
    LARGE_INTEGER n{};CHECK(GetFileSizeEx(h,&n));CHECK(n.QuadPart<2000000);
    std::string data(static_cast<size_t>(n.QuadPart),'\0');DWORD got=0;
    CHECK(ReadFile(h,data.empty()?nullptr:&data[0],static_cast<DWORD>(data.size()),&got,nullptr));CHECK(got==data.size());CHECK(CloseHandle(h));return data;
}
static void Write(const wchar_t* name,const std::string& data){
    HANDLE h=CreateFileW(Path(name).c_str(),GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);CHECK(h!=INVALID_HANDLE_VALUE);
    DWORD done=0;CHECK(WriteFile(h,data.data(),static_cast<DWORD>(data.size()),&done,nullptr));CHECK(done==data.size());CHECK(CloseHandle(h));
}
enum class Fault {None,Open,Write,WriteZero,WriteOver,WriteNoError,Flush,FlushNoError,Close,CloseNoError,Rename,Console};
class Api final : public ZeroSisLogging::LogApi {
public:
    Fault fault=Fault::None;unsigned after=0,calls=0,live=0,flushes=0,consoles=0;DWORD chunk=UINT_MAX;std::string console;
    bool Trip(Fault f) noexcept {
        if(f!=fault || calls++<after)return false;
        fault=Fault::None;SetLastError(ERROR_DISK_FULL);return true;
    }
    HANDLE Open(const wchar_t* p,DWORD a,DWORD s,DWORD c,DWORD f) noexcept override{
        if(Trip(Fault::Open))return INVALID_HANDLE_VALUE;HANDLE h=FileApi::Open(p,a,s,c,f);if(h!=INVALID_HANDLE_VALUE)++live;return h;
    }
    BOOL Write(HANDLE h,const void* p,DWORD n,DWORD* done) noexcept override{
        if(Trip(Fault::Write)){*done=0;return FALSE;}
        if(Trip(Fault::WriteNoError)){*done=0;SetLastError(ERROR_SUCCESS);return FALSE;}
        if(Trip(Fault::WriteZero)){*done=0;return TRUE;}
        if(Trip(Fault::WriteOver)){*done=n+1;return TRUE;}
        return FileApi::Write(h,p,(std::min)(n,chunk),done);
    }
    BOOL Flush(HANDLE h) noexcept override{++flushes;if(Trip(Fault::FlushNoError)){SetLastError(ERROR_SUCCESS);return FALSE;}return Trip(Fault::Flush)?FALSE:FileApi::Flush(h);}
    BOOL Close(HANDLE h) noexcept override{if(Trip(Fault::CloseNoError)){SetLastError(ERROR_SUCCESS);return FALSE;}if(Trip(Fault::Close))return FALSE;BOOL ok=FileApi::Close(h);if(ok)--live;return ok;}
    BOOL Rename(const wchar_t* a,const wchar_t* b) noexcept override{return Trip(Fault::Rename)?FALSE:LogApi::Rename(a,b);}
    BOOL Console(const char* p,DWORD n) noexcept override{
        ++consoles;if(Trip(Fault::Console))return FALSE;
        try{console.append(p,n);return TRUE;}catch(...){SetLastError(ERROR_NOT_ENOUGH_MEMORY);return FALSE;}
    }
    void Time(SYSTEMTIME& t) noexcept override {t={2026,9,5,25,12,34,56,789};}
};
static void Basic(){
    CHECK(FILogFileMgr::PeekInstance()==nullptr);auto& fallback=FILogFileMgr::GetInstance();
    CHECK(FILogFileMgr::PeekInstance()==&fallback);CHECK(!fallback.IsLoggingEnabled());
    FILogFile* unavailable=fallback.GetLog("unconfigured.log",0);CHECK(unavailable!=nullptr);unavailable->Msg("not written");
    CHECK(GetFileAttributesW(Path(L"unconfigured.log").c_str())==INVALID_FILE_ATTRIBUTES);
    Api api;ZeroSisLogging::NativeLogManager manager(api);CHECK(manager.Configure(root.c_str()));ZeroSisLogging::NativeLogManager::Bind(&manager);
    CHECK(&FILogFileMgr::GetInstance()==&manager);CHECK(manager.IsLoggingEnabled());
    FILogFile* log=manager.GetLog(u8"\uD55C\uAE00_\U0001F30F.log",FILogFile::kDontTimeStamp,"title 100% literal");
    CHECK(log==manager.GetLog(L"\uD55C\uAE00_\U0001F30F.log",0,"ignored"));
    CHECK(log->GetFlags()==FILogFile::kDontTimeStamp);
    log->Msg("rate=%s %% %d %llu %.2f",u8"\uD55C\uAE00",-7,42ull,1.25);
    log->DebugMsg("%s","100% %s %n untouched");log->WarningMsg("warning");log->ErrorMsg("error\n");
    const std::string expected=u8"title 100% literal\r\nrate=\uD55C\uAE00 % -7 42 1.25\r\n[DEBUG] 100% %s %n untouched\r\n[WARNING] warning\r\n[ERROR] error\n";
    CHECK(Read(L"\uD55C\uAE00_\U0001F30F.log")==expected);
    auto state=manager.GetStatus(log);CHECK(state.received==4 && state.written==4 && !state.failed && state.open);
    log->Close();log->Open();log->Msg("again");log->Close();CHECK(Read(L"\uD55C\uAE00_\U0001F30F.log")==expected+"again\r\n");
    CHECK(std::wcsstr(log->GetFileName(),L"\uD55C\uAE00_")!=nullptr);
    auto* timed=manager.GetLog("timed.log",FILogFile::kWriteToConsole);
    timed->Msg("clock");CHECK(Read(L"timed.log")=="[2026-09-25 12:34:56.789 UTC] clock\r\n");CHECK(api.console==Read(L"timed.log"));
    auto* upper=manager.GetLog("Case.log",FILogFile::kDontTimeStamp);CHECK(upper==manager.GetLog("CASE.LOG",0));upper->Msg("case");
    manager.DisableLogging();CHECK(!manager.IsLoggingEnabled());log->Msg("skipped %s",nullptr);
    CHECK(manager.GetStatus(log).skipped==1);CHECK(!manager.GetStatus(log).open);
    manager.EnableLogging();log->Msg("enabled");CHECK(manager.GetStatus(log).written==6);
    CHECK(manager.DeleteLog(log));CHECK(!manager.DeleteLog(log));log->Msg("retired");CHECK(manager.GetStatus(log).retired && manager.GetStatus(log).failed==1);
    auto* replacement=manager.GetLog(L"\uD55C\uAE00_\U0001F30F.log",FILogFile::kDontTimeStamp);CHECK(replacement!=log);
    replacement->Msg("replacement");CHECK(manager.DeleteLog(L"\uD55C\uAE00_\U0001F30F.log"));
    CHECK(!manager.DeleteLog(L"missing.log"));CHECK(!manager.Configure(root.c_str()));
    ZeroSisLogging::NativeLogManager::Bind(nullptr);
    std::printf("BASIC|utf8_names|formatting|timestamp|severity|console|disable|retired_pointer\n");
}
static void BufferedAndArchive(){
    Api api;ZeroSisLogging::NativeLogManager manager(api);CHECK(manager.Configure(root.c_str()));
    auto* log=manager.GetLog("buffer.log",FILogFile::kDontTimeStamp|FILogFile::kDontFlushOnWrite);
    log->SetBufSize(128);log->Msg("one");log->Msg("two");CHECK(Read(L"buffer.log").empty());
    CHECK(manager.GetStatus(log).pending==2 && manager.GetStatus(log).written==0);
    log->SetFlags(FILogFile::kDontTimeStamp);CHECK(Read(L"buffer.log")=="one\r\ntwo\r\n");
    CHECK(manager.GetStatus(log).pending==0 && manager.GetStatus(log).written==2);
    log->Archive(L"buffer.1.log");CHECK(Read(L"buffer.1.log")=="one\r\ntwo\r\n");
    CHECK(GetFileAttributesW(Path(L"buffer.log").c_str())==INVALID_FILE_ATTRIBUTES);
    log->Msg("new");log->Archive(L"buffer.1.log");CHECK(manager.GetStatus(log).lastError!=ERROR_SUCCESS);
    CHECK(Read(L"buffer.1.log")=="one\r\ntwo\r\n");CHECK(Read(L"buffer.log")=="new\r\n");
    log->Open();log->Msg("recovered");log->Close();CHECK(Read(L"buffer.log")=="new\r\nrecovered\r\n");
    log->Archive(L"..\\escape");CHECK(manager.GetStatus(log).lastError!=ERROR_SUCCESS);
    auto* sized=manager.GetLog("sized.log",FILogFile::kDontTimeStamp|FILogFile::kDontFlushOnWrite);
    sized->SetBufSize(8);sized->Msg("a");sized->Msg("b");sized->Msg("c");
    CHECK(Read(L"sized.log")=="a\r\nb\r\n");CHECK(manager.GetStatus(sized).pending==1);sized->Close();
    CHECK(Read(L"sized.log")=="a\r\nb\r\nc\r\n");
    std::printf("BUFFER|batch_drain|archive_no_overwrite|reopen_append\n");
}
static void Invalid(){
    Api api;ZeroSisLogging::NativeLogManager manager(api);CHECK(manager.Configure(root.c_str()));
    const wchar_t* names[]={L"",L"..",L"..\\bad",L"C:\\bad",L"CON",L"LPT1.log",L"trailing.",L"a:b",L"a/b"};
    for(auto* name:names){auto* log=manager.GetLog(name,0);CHECK(log!=nullptr);log->Msg("rejected");CHECK(manager.GetStatus(log).failed>0);}
    auto* rejected=manager.GetLog("\xc0\xaf",0);CHECK(rejected!=nullptr);rejected->Msg("rejected");
    auto* log=manager.GetLog("invalid.log",FILogFile::kDontTimeStamp);log->Msg("baseline");log->Close();
    int value=123;
    const char* invalid[]={"trailing%","%n","%I64n","%1000000000d","%Q"};
    for(const char* fmt:invalid){
        log->Open();log->Msg(fmt,&value);CHECK(manager.GetStatus(log).lastError!=ERROR_SUCCESS);log->Close();
        CHECK(Read(L"invalid.log")=="baseline\r\n");CHECK(value==123);
    }
    log->Open();log->SetFlags(0x80000000u);CHECK(log->GetFlags()==FILogFile::kDontTimeStamp);log->Close();
    log->Open();log->SetBufSize(-1);CHECK(manager.GetStatus(log).lastError!=ERROR_SUCCESS);log->Close();
    log->Open();std::string huge(1024*1024+1,'x');log->Msg("%s",huge.c_str());CHECK(manager.GetStatus(log).lastError!=ERROR_SUCCESS);log->Close();
    CHECK(Read(L"invalid.log")=="baseline\r\n");
    std::printf("INVALID|names|percent_n|invalid_formats|oversize|flags|buffer_size\n");
}
static void Faults(){
    unsigned cases=0;
    for(auto fault:{Fault::Open,Fault::Write,Fault::WriteZero,Fault::WriteOver,Fault::WriteNoError,Fault::Flush,Fault::FlushNoError}){
        for(unsigned buffered=0;buffered<2;++buffered){
            Write(L"fault.log","seed\r\n");Api api;ZeroSisLogging::NativeLogManager manager(api);CHECK(manager.Configure(root.c_str()));
            auto* log=manager.GetLog("fault.log",FILogFile::kDontTimeStamp|(buffered?FILogFile::kDontFlushOnWrite:0));
            if(buffered)log->SetBufSize(128);
            api.fault=fault;api.chunk=3;api.after=(fault==Fault::Write || fault==Fault::WriteZero || fault==Fault::WriteOver || fault==Fault::WriteNoError)?2:0;
            log->Msg("abcdefghi");log->Close();
            CHECK(Read(L"fault.log")=="seed\r\n");CHECK(!api.live);
            CHECK(manager.GetStatus(log).failed==1);CHECK(!manager.GetStatus(log).rollbackFailures);
            log->Open();log->Msg("retry");log->Close();CHECK(Read(L"fault.log")=="seed\r\nretry\r\n");++cases;
        }
    }
    {
        Api api;ZeroSisLogging::NativeLogManager manager(api);CHECK(manager.Configure(root.c_str()));
        auto* log=manager.GetLog("close.log",FILogFile::kDontTimeStamp);log->Msg("kept");api.fault=Fault::Close;log->Close();
        CHECK(!api.live);CHECK(manager.GetStatus(log).lastError!=ERROR_SUCCESS);CHECK(Read(L"close.log")=="kept\r\n");++cases;
        log->Open();api.fault=Fault::Rename;api.calls=0;log->Archive(L"close.archived.log");
        CHECK(manager.GetStatus(log).lastError!=ERROR_SUCCESS);CHECK(Read(L"close.log")=="kept\r\n");++cases;
        log->Open();log->SetFlags(FILogFile::kDontTimeStamp|FILogFile::kWriteToConsole);api.fault=Fault::Console;api.calls=0;log->Msg("file survives");
        CHECK(manager.GetStatus(log).consoleErrors==1);CHECK(Read(L"close.log")=="kept\r\nfile survives\r\n");++cases;
    }
    {
        Api api;ZeroSisLogging::NativeLogManager manager(api);CHECK(manager.Configure(root.c_str()));
        auto* log=manager.GetLog("close_no_error.log",FILogFile::kDontTimeStamp);log->Msg("retained");api.fault=Fault::CloseNoError;log->Close();
        CHECK(manager.GetStatus(log).lastError!=ERROR_SUCCESS);CHECK(!api.live);CHECK(Read(L"close_no_error.log")=="retained\r\n");++cases;
    }
    Write(L"readonly.log","old\r\n");CHECK(SetFileAttributesW(Path(L"readonly.log").c_str(),FILE_ATTRIBUTE_READONLY));
    {
        Api api;ZeroSisLogging::NativeLogManager manager(api);CHECK(manager.Configure(root.c_str()));
        auto* log=manager.GetLog("readonly.log",0);log->Msg("denied");CHECK(manager.GetStatus(log).failed==1);CHECK(!api.live);++cases;
    }
    CHECK(SetFileAttributesW(Path(L"readonly.log").c_str(),FILE_ATTRIBUTE_NORMAL));CHECK(Read(L"readonly.log")=="old\r\n");
    std::printf("FAULTS|%u|prior_records_preserved|partial_append_rollback|explicit_recovery\n",cases);
}
static void Concurrent(){
    ZeroSisLogging::NativeLogManager manager;CHECK(manager.Configure(root.c_str()));
    auto* shared=manager.GetLog("concurrent.log",FILogFile::kDontTimeStamp|FILogFile::kDontFlushOnWrite);
    std::vector<std::thread> workers;
    for(unsigned w=0;w<8;++w)workers.emplace_back([&,w]{
        for(unsigned i=0;i<200;++i){auto* log=manager.GetLog("CONCURRENT.LOG",0);CHECK(log==shared);log->Msg("%u,%u,payload",w,i);}
    });
    for(auto& t:workers)t.join();shared->Close();
    const auto s=manager.GetStatus(shared);CHECK(s.received==1600 && s.written==1600 && !s.failed && !s.pending);
    CHECK(Read(L"concurrent.log").size()>16000);
    std::printf("WORKERS|8|1600_shared_log_records\n");
}
static void Callers(){
    ZeroSisLogging::NativeLogManager manager;CHECK(manager.Configure(root.c_str()));
    auto* log=manager.GetLog("sdk_callers.log",FILogFile::kDontTimeStamp|FILogFile::kDontFlushOnWrite);
    ExerciseLoggingCallers(log);log->Close();
    const auto status=manager.GetStatus(log);CHECK(status.written==155 && status.received==155 && !status.failed);
    CHECK(Read(L"sdk_callers.log").size()>4000);
    std::printf("SDK_CALLERS|155|literal_percent_strings|actual_CvString_and_pointer_arguments\n");
}
int wmain(int argc,wchar_t** argv){
    CHECK(argc==2);root=argv[1];Basic();BufferedAndArchive();Invalid();Faults();Concurrent();Callers();
    std::printf("PASS|%u\n",checks.load());return 0;
}
