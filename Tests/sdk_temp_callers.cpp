#include "SdkTempHeapIncludes.h"
#include <FireWorks/FMemoryStream.h>
#include "CvEmbeddedDatabaseIO.h"
#include <map>
#include <set>

static unsigned int checks=0;
static void require(bool value) { ++checks;if(!value) { fprintf(stderr,"FAIL|%u\n",checks);throw std::runtime_error("check"); } }
extern "C" void ZeroSisSdkTempHeapReturnNull(bool enabled);
typedef CvEmbeddedDatabase::NativeFiles Native;
static const unsigned int kCapacity=8192;

#ifdef TEMP_CALLER_ALLOCATION_FAULTS
static std::map<void*,size_t> allocated;
static size_t rejectAbove=static_cast<size_t>(-1),lastRequested=0;
static unsigned int rejectedAllocations=0;
// Fault-injection executable only. The regular executable links the production
// Foundation allocator. Both execute the actual patched SDK wrapper definitions.
void* FireMallocAlignedNoTracking(size_t size,size_t align,const char*,int) {
    lastRequested=size;
    if(size>rejectAbove) { ++rejectedAllocations;return NULL; }
    void* p=_aligned_malloc(size?size:1,align?align:sizeof(void*));if(p)allocated[p]=size;return p;
}
void FireFreeAlignedNoTracking(void* p) {
    if(p) { require(allocated.erase(p)==1);_aligned_free(p); }
}
#endif

static std::vector<byte> pattern(unsigned int size,unsigned int seed=29) {
    std::vector<byte> bytes(size);for(unsigned int i=0;i<size;++i)bytes[i]=static_cast<byte>(i*73+seed);return bytes;
}
static void writeFixture(const std::wstring& path,const std::vector<byte>& bytes) {
    HANDLE h=CreateFileW(path.c_str(),GENERIC_WRITE,0,NULL,CREATE_ALWAYS,FILE_ATTRIBUTE_NORMAL,NULL);require(h!=INVALID_HANDLE_VALUE);
    DWORD written=0;require(bytes.empty() || (WriteFile(h,&bytes[0],static_cast<DWORD>(bytes.size()),&written,NULL) && written==bytes.size()));require(CloseHandle(h)!=0);
}
static std::vector<byte> readFixture(const std::wstring& path) {
    HANDLE h=Native::Open(path.c_str());require(h!=INVALID_HANDLE_VALUE);LARGE_INTEGER size;require(Native::Size(h,&size)!=0 && size.QuadPart<=1048576);
    std::vector<byte> bytes(static_cast<size_t>(size.QuadPart));DWORD read=0;
    require(bytes.empty() || (Native::Read(h,&bytes[0],static_cast<DWORD>(bytes.size()),&read) && read==bytes.size()));require(Native::Close(h)!=0);return bytes;
}
static bool missing(const std::wstring& path) { return GetFileAttributesW(path.c_str())==INVALID_FILE_ATTRIBUTES; }
static void resetArena() {
    TempHeap* heap=GetTempHeap();require(heap->GetAvailable()==kCapacity);
    byte* p=heap->Allocate(kCapacity);require(p!=NULL);heap->DeAllocate(p);require(heap->GetAvailable()==kCapacity);
}

struct __declspec(align(64)) AlignedElement { byte bytes[64]; };
static void wrappers() {
    TempHeap* heap=GetTempHeap();
    { FTempArray<byte,c_eMPoolTypeGame,0> bytes(17);require(bytes.get()!=NULL && heap->OwnsAllocation(bytes.get()));memset(bytes.get(),19,17); }
    resetArena();
    { FTempArray<byte,c_eMPoolTypeGame,0> bytes(17);ZeroSisSdkTempHeapReturnNull(true); }
    ZeroSisSdkTempHeapReturnNull(false);resetArena(); // destructor retained the actual owning arena
    byte* full=heap->Allocate(kCapacity);require(full!=NULL);
    { FTempArray<byte,c_eMPoolTypeGame,0> bytes(257);require(bytes.get()!=NULL && !heap->OwnsAllocation(bytes.get()));memset(bytes.get(),23,257); }
    ZeroSisSdkTempHeapReturnNull(true);
    { FTempArray<byte,c_eMPoolTypeGame,0> bytes(0);require(bytes.get()==NULL); }
    require(FTempHeapFastVectorAllocator::AllocAligned(0,16,c_eMPoolTypeGame,0)==NULL);
    FTempHeapFastVectorAllocator::FreeAligned(NULL);ZeroSisSdkTempHeapReturnNull(false);
    require(heap->GetAvailable()==0);heap->DeAllocate(full);resetArena();
    { FTempArray<AlignedElement,c_eMPoolTypeGame,0> bytes(3);require(bytes.get()!=NULL && !heap->OwnsAllocation(reinterpret_cast<byte*>(bytes.get())) && !(reinterpret_cast<ULONG_PTR>(bytes.get())&63)); }
    bool unwound=false;try { FTempArray<byte,c_eMPoolTypeGame,0> bytes(16);throw std::runtime_error("unwind"); } catch(const std::runtime_error&) { unwound=true; }require(unwound);resetArena();
    for(unsigned int align=0;align<=64;align=align?align*2:1) {
        void* p=FTempHeapFastVectorAllocator::AllocAligned(41,align,c_eMPoolTypeGame,0);require(p!=NULL && (!align || !(reinterpret_cast<ULONG_PTR>(p)&(align-1))));
        require((heap->OwnsAllocation(static_cast<byte*>(p))!=0)==(align<=16));memset(p,27,41);FTempHeapFastVectorAllocator::FreeAligned(p);resetArena();
    }
    full=heap->Allocate(kCapacity);require(full!=NULL);
    void* p=FTempHeapFastVectorAllocator::AllocAligned(31,8,c_eMPoolTypeGame,0);require(p && !heap->OwnsAllocation(static_cast<byte*>(p)));FTempHeapFastVectorAllocator::FreeAligned(p);
    heap->DeAllocate(full);resetArena();
    unsigned int rejections=0;
    try { FTempHeapCheckedArrayBytes(static_cast<size_t>(-1),2); } catch(const std::length_error&) { ++rejections; }
    try { FTempHeapFastVectorAllocator::AllocAligned(31,3,c_eMPoolTypeGame,0); } catch(const std::invalid_argument&) { ++rejections; }
    require(rejections==2 && FTempHeapCheckedArrayBytes(0,static_cast<size_t>(-1))==0);
    printf("WRAPPERS|ZERO|POOLED|FALLBACK|ALIGN64|OWNER|UNWIND|OVERFLOW\n");
}

struct FaultFiles : Native {
    enum Mode { NONE,OPEN,SIZE,SIZE_WIDE,SIZE_NEGATIVE,READ,READ_ZERO,READ_EXCESS,READ_PARTIAL_FAIL,SIZE_RECHECK,SIZE_CHANGED,
        CLOSE,CREATE,WRITE,WRITE_ZERO,WRITE_EXCESS,WRITE_PARTIAL_FAIL,FLUSH,REPLACE,COLLISION,COLLISION_FOREVER,PARTIAL };
    static Mode mode;static unsigned int sizes,reads,writes,closes,creates;
    static std::set<HANDLE> live;static std::vector<std::wstring> created;static std::wstring collision;
    static void reset(Mode value) { require(live.empty());mode=value;sizes=reads=writes=closes=creates=0;created.clear();collision.clear(); }
    static BOOL fail() { SetLastError(ERROR_ACCESS_DENIED);return FALSE; }
    static HANDLE Open(const wchar_t* p) { if(mode==OPEN) { fail();return INVALID_HANDLE_VALUE; }HANDLE h=Native::Open(p);if(h!=INVALID_HANDLE_VALUE)live.insert(h);return h; }
    static BOOL Size(HANDLE h,LARGE_INTEGER* out) {
        ++sizes;if((mode==SIZE && sizes==1)||(mode==SIZE_RECHECK && sizes==2))return fail();
        if(!Native::Size(h,out))return FALSE;
        if(mode==SIZE_WIDE)out->QuadPart=static_cast<LONGLONG>(UINT_MAX)+1;
        if(mode==SIZE_NEGATIVE)out->QuadPart=-1;
        if(mode==SIZE_CHANGED && sizes==2)++out->QuadPart;
        return TRUE;
    }
    static BOOL Read(HANDLE h,void* p,DWORD n,DWORD* done) {
        ++reads;if(mode==READ || (mode==READ_PARTIAL_FAIL && reads==2))return fail();
        if(mode==READ_ZERO || mode==READ_EXCESS) { *done=mode==READ_ZERO?0:n+1;return TRUE; }
        return Native::Read(h,p,(mode==PARTIAL || mode==READ_PARTIAL_FAIL) && n>7?7:n,done);
    }
    static BOOL Write(HANDLE h,const void* p,DWORD n,DWORD* done) {
        ++writes;if(mode==WRITE || (mode==WRITE_PARTIAL_FAIL && writes==2))return fail();
        if(mode==WRITE_ZERO || mode==WRITE_EXCESS) { *done=mode==WRITE_ZERO?0:n+1;return TRUE; }
        return Native::Write(h,p,(mode==PARTIAL || mode==WRITE_PARTIAL_FAIL) && n>7?7:n,done);
    }
    static HANDLE Create(const wchar_t* p) {
        ++creates;
        if(mode==CREATE) { fail();return INVALID_HANDLE_VALUE; }
        if(mode==COLLISION_FOREVER || (mode==COLLISION && creates==1)) {
            if(mode==COLLISION) { collision=p;writeFixture(collision,pattern(11,199)); }
            SetLastError(ERROR_FILE_EXISTS);return INVALID_HANDLE_VALUE;
        }
        HANDLE h=Native::Create(p);if(h!=INVALID_HANDLE_VALUE) { live.insert(h);created.push_back(p); }return h;
    }
    static BOOL Flush(HANDLE h) { return mode==FLUSH?fail():Native::Flush(h); }
    static BOOL Close(HANDLE h) { ++closes;if(mode==CLOSE && closes==1)return fail();BOOL ok=Native::Close(h);if(ok)require(live.erase(h)==1);return ok; }
    static BOOL Replace(const wchar_t* a,const wchar_t* b) { return mode==REPLACE?fail():Native::Replace(a,b); }
    static void clean() { require(live.empty());for(size_t i=0;i<created.size();++i)require(missing(created[i]));resetArena(); }
};
FaultFiles::Mode FaultFiles::mode=FaultFiles::NONE;
unsigned int FaultFiles::sizes=0,FaultFiles::reads=0,FaultFiles::writes=0,FaultFiles::closes=0,FaultFiles::creates=0;
std::set<HANDLE> FaultFiles::live;std::vector<std::wstring> FaultFiles::created;std::wstring FaultFiles::collision;

struct FaultStream : FMemoryStream {
    unsigned int fault;FaultStream() : fault(0) {}
    unsigned int ReadIt(unsigned int count,void* out) {
        if(fault==1)throw std::runtime_error("injected stream read");
        return FMemoryStream::ReadIt(fault==2 && count?count-1:count,out);
    }
    unsigned int WriteIt(unsigned int count,const void* in) {
        if(fault==3)throw std::runtime_error("injected stream write");
        return FMemoryStream::WriteIt((fault==4 || (fault==5 && count>4)) && count?count-1:count,in);
    }
};

static void fileFailures(const std::wstring& path) {
    const std::vector<byte> original=pattern(73,51),payload=pattern(91,101);writeFixture(path,original);
    const FaultFiles::Mode saveFailures[]={FaultFiles::OPEN,FaultFiles::SIZE,FaultFiles::SIZE_WIDE,FaultFiles::SIZE_NEGATIVE,
        FaultFiles::READ,FaultFiles::READ_ZERO,FaultFiles::READ_EXCESS,FaultFiles::READ_PARTIAL_FAIL,FaultFiles::SIZE_RECHECK,FaultFiles::SIZE_CHANGED,FaultFiles::CLOSE};
    unsigned int failures=0;
    for(size_t i=0;i<sizeof(saveFailures)/sizeof(saveFailures[0]);++i) {
        FaultFiles::reset(saveFailures[i]);FMemoryStream s;s.WriteIt(3,"PRE");bool rejected=false;
        try { CvEmbeddedDatabase::WriteFileToStream<FaultFiles>(s,path); } catch(const std::exception&) { rejected=true; }
        require(rejected && s.GetEOF()==3 && !memcmp(s.GetBuf(),"PRE",3));require(readFixture(path)==original);FaultFiles::clean();++failures;
    }
    const FaultFiles::Mode loadFailures[]={FaultFiles::CREATE,FaultFiles::WRITE,FaultFiles::WRITE_ZERO,FaultFiles::WRITE_EXCESS,
        FaultFiles::WRITE_PARTIAL_FAIL,FaultFiles::FLUSH,FaultFiles::CLOSE,FaultFiles::REPLACE,FaultFiles::COLLISION_FOREVER};
    for(size_t i=0;i<sizeof(loadFailures)/sizeof(loadFailures[0]);++i) {
        FaultFiles::reset(loadFailures[i]);FMemoryStream s;s.WriteIt(static_cast<uint>(payload.size()),&payload[0]);s.Rewind();bool rejected=false;
        try { CvEmbeddedDatabase::ReadStreamToFile<FaultFiles>(s,path,static_cast<uint>(payload.size())); } catch(const std::exception&) { rejected=true; }
        require(rejected && readFixture(path)==original);FaultFiles::clean();++failures;
    }
    for(unsigned int mode=1;mode<=5;++mode) {
        FaultFiles::reset(FaultFiles::NONE);FaultStream s;
        if(mode<=2) { s.FMemoryStream::WriteIt(static_cast<uint>(payload.size()),&payload[0]);s.Rewind(); }
        s.fault=mode;bool rejected=false;
        try {
            if(mode<=2)CvEmbeddedDatabase::ReadStreamToFile<FaultFiles>(s,path,static_cast<uint>(payload.size()));
            else CvEmbeddedDatabase::WriteFileToStream<FaultFiles>(s,path);
        } catch(const std::exception&) { rejected=true; }
        require(rejected && readFixture(path)==original);FaultFiles::clean();++failures;
    }
    FaultFiles::reset(FaultFiles::NONE);FMemoryStream shortInput;shortInput.WriteIt(3,"BAD");shortInput.Rewind();bool rejected=false;
    try { CvEmbeddedDatabase::ReadStreamToFile<FaultFiles>(shortInput,path,100); } catch(const std::out_of_range&) { rejected=true; }
    require(rejected && shortInput.GetPosition()==0 && readFixture(path)==original);FaultFiles::clean();++failures;
    for(unsigned int collision=0;collision<2;++collision) {
        FaultFiles::reset(collision?FaultFiles::COLLISION:FaultFiles::PARTIAL);
        FMemoryStream s;CvEmbeddedDatabase::WriteFileToStream<FaultFiles>(s,path);s.Rewind();unsigned int length=0;s>>length;
        CvEmbeddedDatabase::ReadStreamToFile<FaultFiles>(s,path,length);require(readFixture(path)==original);FaultFiles::clean();
        if(collision) { require(!FaultFiles::collision.empty() && readFixture(FaultFiles::collision)==pattern(11,199));require(DeleteFileW(FaultFiles::collision.c_str())!=0); }
    }
    require(!(GetFileAttributesW(path.c_str())&FILE_ATTRIBUTE_TEMPORARY));require(failures==26);
    printf("IO_FAILURES|26|CACHE_PRESERVED|HANDLES_CLOSED|TEMPORARIES_REMOVED\nPARTIAL_IO|2|COLLISION_PRESERVED\n");
}

static void roundTrips(const std::wstring& path,const wchar_t* tracePath) {
    const uint sizes[]={0,1,15,16,17,255,256,8191,8192,8193,65537};
    FILE* out=_wfopen(tracePath,L"wb");require(out!=NULL);uint cases=0;
    for(unsigned int mode=0;mode<3;++mode)for(size_t index=0;index<sizeof(sizes)/sizeof(sizes[0]);++index) {
        const uint size=sizes[index];const std::vector<byte> data=pattern(size);writeFixture(path,data);
        FMemoryStream s;s.SetDesiredEndianNess(static_cast<FEndian::EEndianness>(mode));CvEmbeddedDatabase::Write(s,path);
        require(s.GetEOF()==size+4);const uint record[]={mode,size,s.GetEOF()};require(fwrite(record,sizeof(record),1,out)==1 && fwrite(s.GetBuf(),1,s.GetEOF(),out)==s.GetEOF());
        writeFixture(path,pattern(7,221));s.Rewind();uint count=UINT_MAX;s>>count;require(count==size);
        CvEmbeddedDatabase::Read(s,path,count);require(readFixture(path)==(size?data:pattern(7,221)));require(s.AtEnd());resetArena();++cases;
    }
    require(DeleteFileW(path.c_str())!=0);FMemoryStream absent;CvEmbeddedDatabase::Write(absent,path);
    require(absent.GetEOF()==4 && !memcmp(absent.GetBuf(),"\0\0\0\0",4));resetArena();
    require(fclose(out)==0);printf("DATABASE_ROUNDTRIPS|%u|MISSING_FILE_ZERO\n",cases);
}

#ifdef TEMP_CALLER_ALLOCATION_FAULTS
static void allocationFailures(const std::wstring& path) {
    TempHeap* heap=GetTempHeap();byte* full=heap->Allocate(kCapacity);require(full!=NULL);const size_t baseline=allocated.size();rejectAbove=0;
    unsigned int failures=0;try { FTempArray<byte,c_eMPoolTypeGame,0> a(31); } catch(const std::bad_alloc&) { ++failures; }
    try { FTempHeapFastVectorAllocator::AllocAligned(31,16,c_eMPoolTypeGame,0); } catch(const std::bad_alloc&) { ++failures; }
    require(allocated.size()==baseline && heap->GetAvailable()==0);heap->DeAllocate(full);resetArena();
    struct Pair { byte two[2]; };ZeroSisSdkTempHeapReturnNull(true);
    try { FTempArray<Pair,c_eMPoolTypeGame,0> huge(UINT_MAX); } catch(const std::bad_alloc&) { ++failures; }
    require(lastRequested==static_cast<size_t>(UINT_MAX)*2);ZeroSisSdkTempHeapReturnNull(false);resetArena();
    rejectAbove=static_cast<size_t>(-1);const std::vector<byte> bytes=pattern(kCapacity+1);writeFixture(path,bytes);rejectAbove=0;
    FaultFiles::reset(FaultFiles::NONE);FMemoryStream save;
    try { CvEmbeddedDatabase::WriteFileToStream<FaultFiles>(save,path); } catch(const std::bad_alloc&) { ++failures; }
    require(save.GetEOF()==0 && readFixture(path)==bytes);FaultFiles::clean();
    FMemoryStream load;load.WriteIt(static_cast<uint>(bytes.size()),&bytes[0]);load.Rewind();
    try { CvEmbeddedDatabase::ReadStreamToFile<FaultFiles>(load,path,static_cast<uint>(bytes.size())); } catch(const std::bad_alloc&) { ++failures; }
    require(load.GetPosition()==0 && readFixture(path)==bytes && allocated.size()==baseline);FaultFiles::clean();
    rejectAbove=static_cast<size_t>(-1);require(failures==5 && rejectedAllocations==5);
    printf("ALLOCATION_FAILURES|5|WIDE_REQUEST|8589934590|NO_LEAK\n");
}
#endif

int wmain(int argc,wchar_t** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);
    try {
        require(argc==3);const std::wstring path(argv[1]);require(missing(path));
        require(GetTempHeap()->Startup(kCapacity,NULL)==kCapacity);wrappers();roundTrips(path,argv[2]);fileFailures(path);
#ifdef TEMP_CALLER_ALLOCATION_FAULTS
        allocationFailures(path);
#endif
        require(DeleteFileW(path.c_str())!=0);GetTempHeap()->Shutdown();
#ifdef TEMP_CALLER_ALLOCATION_FAULTS
        require(allocated.empty());
#endif
        printf("PASS|%u\n",checks);return 0;
    } catch(const std::exception& e) { fprintf(stderr,"EXCEPTION|%s\n",e.what());return 1; }
}
