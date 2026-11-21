#include "sdk_filesystem_faults.h"
#include <atomic>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <thread>
#include <vector>
#include <winioctl.h>

static std::atomic<unsigned> checks{0};
#define CHECK(x) do {++checks;if(!(x)){std::fprintf(stderr,"FAIL|%d|%s|win32=%lu\n",__LINE__,#x,GetLastError());std::exit(2);}}while(0)
using File=std::unique_ptr<FIFile>;
static std::wstring root;
static std::wstring Path(const wchar_t* name) { return root+L"\\"+name; }
static std::string Utf8(const std::wstring& p) {
    const int n=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,p.c_str(),-1,nullptr,0,nullptr,nullptr);
    CHECK(n>0);std::vector<char> v(n);
    CHECK(WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,p.c_str(),-1,v.data(),n,nullptr,nullptr)==n);
    return v.data();
}
static void RawWrite(const std::wstring& path,const std::vector<byte>& bytes) {
    HANDLE h=CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,nullptr);CHECK(h!=INVALID_HANDLE_VALUE);
    DWORD done=0;CHECK(WriteFile(h,bytes.data(),static_cast<DWORD>(bytes.size()),&done,nullptr));CHECK(done==bytes.size());CHECK(CloseHandle(h));
}
static std::vector<byte> RawRead(const std::wstring& path) {
    HANDLE h=CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);CHECK(h!=INVALID_HANDLE_VALUE);
    LARGE_INTEGER n{};CHECK(GetFileSizeEx(h,&n));CHECK(n.QuadPart<=10000000);
    std::vector<byte> out(static_cast<size_t>(n.QuadPart));DWORD done=0;
    CHECK(ReadFile(h,out.data(),static_cast<DWORD>(out.size()),&done,nullptr));CHECK(done==out.size());CHECK(CloseHandle(h));return out;
}
static unsigned Temps() {
    WIN32_FIND_DATAW d{};HANDLE h=FindFirstFileW(Path(L".zerosis-txn-*").c_str(),&d);
    if(h==INVALID_HANDLE_VALUE) { CHECK(GetLastError()==ERROR_FILE_NOT_FOUND);return 0; }
    unsigned n=1;while(FindNextFileW(h,&d))++n;CHECK(FindClose(h));return n;
}
static void WholeWrite(FIFile& f,const std::vector<byte>& b) {
    uint at=0;while(at<b.size()){const uint n=f.Write(b.data()+at,static_cast<uint>(b.size()-at));CHECK(n>0);at+=n;}
}
class CountingAllocator final : public FIFile::Allocator {
public:
    int live=0;bool fail=false,throws=false;
    byte* Allocate(uint n) override {if(throws)throw std::bad_alloc();if(fail)return nullptr;++live;return new byte[n];}
    void Delete(byte* p) override {if(p){--live;delete[] p;}}
};
static void Basic() {
    auto& fs=FFileSystem::GetInstance();
    CHECK(&FIFileSystem::GetInstance()==&fs);CHECK(!fs.IsFileCatalogEnabled());CHECK(fs.GetErrorHandler()==nullptr);
    File unopened(fs.Create());CHECK(unopened && !unopened->IsOpen());CHECK(unopened->Close()==FILE_OK);
    const auto p=Path(L"\uC9C0\uB3C4_\U0001F30F.bin");const auto utf=Utf8(p);
    const std::vector<byte> old={1,3,5,7},fresh={2,4,6,8,10};
    RawWrite(p,old);CHECK(fs.Exist(p.c_str()));CHECK(fs.Exist(utf.c_str()));CHECK(!fs.Exist(root.c_str()));
    CHECK(fs.GetLength(p.c_str())==old.size());CHECK(fs.GetLength(utf.c_str())==old.size());
    WIN32_FILE_ATTRIBUTE_DATA attr{};CHECK(GetFileAttributesExW(p.c_str(),GetFileExInfoStandard,&attr));
    CHECK(fs.GetLastWriteTime(utf.c_str())==FFileTimestamp(attr.ftLastWriteTime));
    {
        File f(fs.Create(utf.c_str(),FIFile::modeWrite));CHECK(f && f->IsOpen());WholeWrite(*f,fresh);
        CHECK(RawRead(p)==old);CHECK(Temps()==1);CHECK(f->Flush()==1);CHECK(RawRead(p)==old);
        CHECK(f->Close()==FILE_OK);CHECK(f->Close()==FILE_OK);CHECK(!f->IsOpen());
    }
    CHECK(RawRead(p)==fresh);CHECK(Temps()==0);
    { File f(fs.Create(p.c_str(),FIFile::modeWrite));WholeWrite(*f,old); }
    CHECK(RawRead(p)==fresh);CHECK(Temps()==0); // Abandoned transaction.
    {
        File f(fs.Create(p.c_str(),FIFile::modeRead,FFILE_FLAG_RANDOM_ACCESS));CHECK(f->IsOpen());
        CHECK(!f->IsMapped());byte* view=f->GetViewPtr();CHECK(view!=nullptr);CHECK(f->IsMapped());
        CHECK(std::memcmp(view,fresh.data(),fresh.size())==0);CHECK(static_cast<size_t>(f->GetViewEnd()-view)==fresh.size());
        MEMORY_BASIC_INFORMATION region{};CHECK(VirtualQuery(view,&region,sizeof(region))==sizeof(region));CHECK(region.Protect==PAGE_READONLY);
        CHECK(f->Seek(2,FIFile::begin)==2);CHECK(f->GetViewCaret()==view+2);
        byte b[10]{};CHECK(f->Read(b,10)==3);CHECK(b[0]==6 && b[2]==10);CHECK(f->IsEOF());CHECK(f->Read(b,1)==0);
        CHECK(f->Seek(-1,FIFile::end)==4);CHECK(f->Read(b,1)==1 && b[0]==10);
        f->Rewind();CHECK(f->GetPosition()==0);CHECK(f->Close()==FILE_OK);CHECK(!f->IsMapped());
    }
    {
        File f(fs.Create(p.c_str(),FIFile::modeEdit));CHECK(f->GetLength()==fresh.size());CHECK(f->GetPosition()==0);
        CHECK(f->Seek(1,FIFile::begin)==1);const byte b=99;CHECK(f->Write(&b,1)==1);
        f->SetLength(9);CHECK(f->GetLength()==9 && f->GetPosition()==2);
        CHECK(f->SeekToEnd()==9);CHECK(f->Seek(3,FIFile::current)==12);CHECK(f->Write(&b,1)==1);
        CHECK(f->Close()==FILE_OK);
        CHECK(RawRead(p)==std::vector<byte>({2,99,6,8,10,0,0,0,0,0,0,0,99}));
    }
    {
        File f(fs.Create(p.c_str(),FIFile::modeEdit));CHECK(f->SeekToEnd()==13);f->SetLength(3);
        CHECK(f->GetPosition()==13 && f->GetLength()==3 && f->IsEOF());CHECK(f->Close()==FILE_OK);
        CHECK(RawRead(p)==std::vector<byte>({2,99,6}));
    }
    byte* b=nullptr;size_t n=0;CHECK(fs.ReadAll(utf.c_str(),&b,&n)==FILE_OK);CHECK(n==3 && b[1]==99);delete[] b;
    CountingAllocator alloc;CHECK(fs.ReadAll(p.c_str(),&b,&n,0,alloc)==FILE_OK);CHECK(n==3 && alloc.live==1);alloc.Delete(b);
    alloc.fail=true;b=reinterpret_cast<byte*>(1);n=42;CHECK(fs.ReadAll(p.c_str(),&b,&n,0,alloc)!=FILE_OK);CHECK(!b && !n && !alloc.live);
    alloc.fail=false;alloc.throws=true;CHECK(fs.ReadAll(p.c_str(),&b,&n,0,alloc)!=FILE_OK);CHECK(!b && !n && !alloc.live);
    CHECK(fs.ReadAll(p.c_str(),nullptr,&n)!=FILE_OK);CHECK(n==0);
    CHECK(fs.ReadAll(p.c_str(),&b,nullptr)!=FILE_OK);CHECK(b==nullptr);
    const auto empty=Path(L"empty");RawWrite(empty,{});
    CHECK(fs.ReadAll(empty.c_str(),&b,&n)==FILE_OK);CHECK(!b && !n);
    {File f(fs.Create(empty.c_str()));CHECK(f->IsOpen());CHECK(!f->GetViewPtr());CHECK(f->IsEOF());CHECK(f->Close()==FILE_OK);}
    {FFileInstance f(p.c_str(),FIFile::modeWrite);WholeWrite(*f,old);}
    CHECK(RawRead(p)==old);CHECK(fs.Delete(utf.c_str())==FILE_OK);CHECK(!fs.Exist(p.c_str()));
    CHECK(fs.Delete(p.c_str())==FILE_NOTFOUND);
    std::printf("BASIC|utf8_utf16|transaction|mapping|edit|zero_extension|readall|sdk_facades\n");
}
static void Invalid() {
    auto& fs=FFileSystem::GetInstance();
    const auto p=Path(L"invalid.bin");const std::vector<byte> original={8,6,4,2};RawWrite(p,original);
    const dword unsupported[]={1ul,8ul,FFILE_FLAG_BIG_ENDIAN,FFILE_FLAG_UNICODE,0xfffffffful};
    for(dword flags : unsupported) {
        File f(fs.Create(p.c_str(),FIFile::modeWrite,flags));CHECK(f && !f->IsOpen());CHECK(RawRead(p)==original);
    }
    {File f(fs.Create("\xc0\xaf",FIFile::modeWrite));CHECK(f && !f->IsOpen());}
    {File f(fs.Create(L"",FIFile::modeWrite));CHECK(f && !f->IsOpen());}
    {File f(fs.Create(p.c_str(),static_cast<FIFile::OpenMode>(0)));CHECK(f && !f->IsOpen());}
    {File f(fs.Create((p+L":stream").c_str(),FIFile::modeWrite));CHECK(f && !f->IsOpen());}
    {File f(fs.Create(Path(L"missing\\no.bin").c_str(),FIFile::modeWrite));CHECK(f && !f->IsOpen());}
    {File f(fs.Create(p.c_str(),FIFile::modeWrite));CHECK(f->Seek(-1,FIFile::begin)==UINT_MAX);CHECK(f->Close()!=FILE_OK);}
    {File f(fs.Create(p.c_str(),FIFile::modeWrite));CHECK(f->Write(nullptr,1)==0);CHECK(f->Close()!=FILE_OK);}
    {File f(fs.Create(p.c_str(),FIFile::modeWrite));CHECK(!f->GetViewPtr());CHECK(f->Close()!=FILE_OK);}
    {File f(fs.Create(p.c_str(),FIFile::modeRead));byte b=1;CHECK(f->Write(&b,1)==0);CHECK(f->Close()!=FILE_OK);}
    {File f(fs.Create(p.c_str(),FIFile::modeRead));CHECK(f->Seek(LONG_MAX,FIFile::begin)==LONG_MAX);CHECK(f->Seek(LONG_MAX,FIFile::current)==UINT_MAX-1);
        CHECK(f->Seek(1,FIFile::current)==UINT_MAX);CHECK(GetLastError()==ERROR_SUCCESS);CHECK(f->Seek(1,FIFile::current)==UINT_MAX);CHECK(GetLastError()!=ERROR_SUCCESS);}
    CHECK(RawRead(p)==original);CHECK(Temps()==0);
    const auto big=Path(L"over_4gb.sparse");
    HANDLE h=CreateFileW(big.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);CHECK(h!=INVALID_HANDLE_VALUE);
    DWORD returned=0;CHECK(DeviceIoControl(h,FSCTL_SET_SPARSE,nullptr,0,nullptr,0,&returned,nullptr));
    LARGE_INTEGER size{};size.QuadPart=0x100000000ll;CHECK(SetFilePointerEx(h,size,nullptr,FILE_BEGIN));CHECK(SetEndOfFile(h));CHECK(CloseHandle(h));
    {File f(fs.Create(big.c_str()));CHECK(f && !f->IsOpen());}
    {File f(fs.Create(big.c_str(),FIFile::modeEdit));CHECK(f && !f->IsOpen());}
    CHECK(DeleteFileW(big.c_str()));CHECK(Temps()==0);
    std::printf("BOUNDARIES|unsupported_flags|invalid_paths|seek_overflow|4GiB_file_rejected\n");
}
static void Faults() {
    const auto p=Path(L"fault.bin");const std::vector<byte> old(101,11),fresh(173,22);
    unsigned faultRuns=0;
    for(const auto fault:{FsFault::Write,FsFault::WriteZero,FsFault::WriteOver,FsFault::Flush,FsFault::Close,FsFault::Commit}) {
        for(unsigned after:{0u,2u}) {
            RawWrite(p,old);FaultFileApi api;ZeroSisFileSystem::NativeFileSystem fs(api);
            File f(fs.Create(p.c_str(),FIFile::modeWrite));CHECK(f && f->IsOpen());
            api.chunk=7;api.fault=fault;api.failAfter=(fault==FsFault::Write || fault==FsFault::WriteZero || fault==FsFault::WriteOver) ? after : 0;
            uint at=0;while(at<fresh.size()){uint done=f->Write(fresh.data()+at,static_cast<uint>(fresh.size()-at));if(!done)break;at+=done;}
            CHECK(f->Close()!=FILE_OK);CHECK(f->Close()!=FILE_OK);f.reset();
            CHECK(RawRead(p)==old);CHECK(Temps()==0);CHECK(api.live==0);
            CHECK(api.commits==(fault==FsFault::Commit ? 1u : 0u));++faultRuns;
        }
    }
    for(const auto fault:{FsFault::Read,FsFault::ReadZero,FsFault::ReadOver,FsFault::Close}) {
        FaultFileApi api;ZeroSisFileSystem::NativeFileSystem fs(api);
        api.fault=fault;api.chunk=7;api.failAfter=fault==FsFault::Close?0:2;
        CountingAllocator alloc;byte* b=reinterpret_cast<byte*>(1);size_t n=13;
        CHECK(fs.ReadAll(p.c_str(),&b,&n,0,alloc)!=FILE_OK);CHECK(!b && !n && !alloc.live);
        CHECK(api.live==0);CHECK(RawRead(p)==old);++faultRuns;
    }
    for(const auto fault:{FsFault::Open,FsFault::Read,FsFault::Write}) {
        FaultFileApi api;ZeroSisFileSystem::NativeFileSystem fs(api);api.fault=fault;
        File f(fs.Create(p.c_str(),FIFile::modeEdit));CHECK(f && !f->IsOpen());f.reset();
        CHECK(api.live==0);CHECK(RawRead(p)==old);CHECK(Temps()==0);++faultRuns;
    }
    {
        FaultFileApi api;ZeroSisFileSystem::NativeFileSystem fs(api);api.chunk=3;
        File f(fs.Create(p.c_str(),FIFile::modeEdit));CHECK(f->IsOpen());WholeWrite(*f,fresh);CHECK(f->Close()==FILE_OK);
        byte* b=nullptr;size_t n=0;CHECK(fs.ReadAll(p.c_str(),&b,&n)==FILE_OK);CHECK(n==fresh.size());CHECK(!std::memcmp(b,fresh.data(),n));delete[] b;CHECK(api.live==0);
    }
    for(unsigned locked=0;locked<2;++locked) {
        RawWrite(p,old);
        HANDLE held=INVALID_HANDLE_VALUE;
        if(locked) {held=CreateFileW(p.c_str(),GENERIC_READ,FILE_SHARE_READ,nullptr,OPEN_EXISTING,FILE_ATTRIBUTE_NORMAL,nullptr);CHECK(held!=INVALID_HANDLE_VALUE);}
        else CHECK(SetFileAttributesW(p.c_str(),FILE_ATTRIBUTE_READONLY));
        File f(FFileSystem::GetInstance().Create(p.c_str(),FIFile::modeWrite));CHECK(f->IsOpen());WholeWrite(*f,fresh);CHECK(f->Close()!=FILE_OK);
        if(locked) CHECK(CloseHandle(held));else CHECK(SetFileAttributesW(p.c_str(),FILE_ATTRIBUTE_NORMAL));
        CHECK(RawRead(p)==old);CHECK(Temps()==0);++faultRuns;
    }
    std::printf("FAULTS|%u|destination_preserved|no_open_handles|no_temporary_files\n",faultRuns);
}
static void Concurrent() {
    std::vector<std::thread> workers;
    for(unsigned worker=0;worker<4;++worker) workers.emplace_back([worker]{
        const auto p=Path((L"worker-"+std::to_wstring(worker)+L".bin").c_str());
        for(unsigned step=0;step<32;++step) {
            const std::vector<byte> value(2000+step,static_cast<byte>(worker*32+step));
            auto& fs=FIFileSystem::GetInstance();File f(fs.Create(p.c_str(),FIFile::modeWrite));CHECK(f && f->IsOpen());
            WholeWrite(*f,value);CHECK(f->Close()==FILE_OK);CHECK(RawRead(p)==value);
        }
    });
    for(auto& thread:workers) thread.join();
    CHECK(Temps()==0);
    std::printf("WORKERS|4|128_independent_file_transactions\n");
}
class CollisionApi final : public ZeroSisFileSystem::FileApi {
public:
    std::wstring occupied;
    bool collision=false;
    HANDLE Open(const wchar_t* p,DWORD a,DWORD s,DWORD c,DWORD f) noexcept override {
        if(c==CREATE_NEW && !collision) {
            collision=true;occupied=p;
            HANDLE h=FileApi::Open(p,GENERIC_WRITE,0,CREATE_NEW,FILE_ATTRIBUTE_NORMAL);
            if(h==INVALID_HANDLE_VALUE) return h;
            DWORD done=0;const byte marker=79;
            CHECK(WriteFile(h,&marker,1,&done,nullptr));CHECK(done==1);CHECK(CloseHandle(h));
        }
        return FileApi::Open(p,a,s,c,f);
    }
};
static void PathsAndSnapshots() {
    auto& fs=FFileSystem::GetInstance();const auto p=Path(L"collision.bin");
    CollisionApi api;ZeroSisFileSystem::NativeFileSystem collisionFs(api);
    {File f(collisionFs.Create(p.c_str(),FIFile::modeWrite));CHECK(f->IsOpen());WholeWrite(*f,{5,6});CHECK(f->Close()==FILE_OK);}
    CHECK(api.collision);CHECK(RawRead(api.occupied)==std::vector<byte>({79}));CHECK(DeleteFileW(api.occupied.c_str()));
    CHECK(RawRead(p)==std::vector<byte>({5,6}));
    File old(fs.Create(p.c_str()));byte* view=old->GetViewPtr();CHECK(view && view[0]==5);
    {File f(fs.Create(p.c_str(),FIFile::modeWrite));WholeWrite(*f,{9,8});CHECK(f->Close()!=FILE_OK);}
    CHECK(view[0]==5 && view[1]==6);CHECK(RawRead(p)==std::vector<byte>({5,6}));CHECK(old->Close()==FILE_OK);
    File snapshot(fs.Create(p.c_str()));
    {File f(fs.Create(p.c_str(),FIFile::modeWrite));WholeWrite(*f,{9,8});CHECK(f->Close()!=FILE_OK);}
    byte retained[2]{};CHECK(snapshot->Read(retained,2)==2);CHECK(retained[0]==5 && retained[1]==6);
    CHECK(snapshot->Close()==FILE_OK);CHECK(RawRead(p)==std::vector<byte>({5,6}));
    {File f(fs.Create(p.c_str(),FIFile::modeWrite));WholeWrite(*f,{9,8});CHECK(f->Close()==FILE_OK);}
    CHECK(RawRead(p)==std::vector<byte>({9,8}));
    const auto longParent=L"\\\\?\\"+root+L"\\"+std::wstring(180,L'x');
    CHECK(CreateDirectoryW(longParent.c_str(),nullptr));
    const auto longPath=longParent+L"\\"+std::wstring(240,L'y')+L".bin";
    {File f(fs.Create(longPath.c_str(),FIFile::modeWrite));CHECK(f && f->IsOpen());WholeWrite(*f,{1,2,3});CHECK(f->Close()==FILE_OK);}
    CHECK(RawRead(longPath)==std::vector<byte>({1,2,3}));CHECK(fs.Delete(longPath.c_str())==FILE_OK);CHECK(RemoveDirectoryW(longParent.c_str()));
    FaultFileApi closeApi;ZeroSisFileSystem::NativeFileSystem closeFs(closeApi);closeApi.fault=FsFault::Close;
    {File f(closeFs.Create(p.c_str(),FIFile::modeEdit));CHECK(f && !f->IsOpen());}
    CHECK(!closeApi.live);CHECK(RawRead(p)==std::vector<byte>({9,8}));CHECK(Temps()==0);
    std::printf("PATHS|collision_preserved|open_target_rejected|retry_after_close|long_unicode_paths|edit_source_close_failure\n");
}
int wmain(int argc,wchar_t** argv) {
    CHECK(argc==2);root=argv[1];CHECK(GetFileAttributesW(root.c_str())&FILE_ATTRIBUTE_DIRECTORY);
    Basic();Invalid();Faults();PathsAndSnapshots();Concurrent();
    CHECK(Temps()==0);std::printf("PASS|%u\n",checks.load());return 0;
}
