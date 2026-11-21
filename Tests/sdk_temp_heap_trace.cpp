#include "SdkTempHeapIncludes.h"
#include <algorithm>
static unsigned int checks=0;
static void require(bool value) { ++checks;if(!value) { fprintf(stderr,"FAIL|%u\n",checks);throw std::runtime_error("check"); } }
struct ProbeHeap : TempHeap {
    LONG leases() const { return m_Lock.m_uiLock; }
    LONG offset() const { return m_uiCurrentOffset; }
    byte* head() const { return m_pMemHead; }
    DWORD flags() const { return m_dwFlags; }
};
static void state(const char* label,const ProbeHeap& heap) {
    printf("STATE|%s|%u|%u|%ld|%ld|%lu|%d\n",label,heap.GetCapacity(),heap.GetAvailable(),heap.leases(),heap.offset(),heap.flags(),heap.head()!=NULL);
}
static void probe() {
    ProbeHeap heap;state("new",heap);printf("START|%u\n",heap.Startup(255,NULL));state("started",heap);
    byte* a=heap.Allocate(1);byte* b=heap.Allocate(17);byte* zero=heap.Allocate(0);require(a && b && zero);
    printf("OFFSETS|%u|%u|%u\n",static_cast<unsigned int>(a-heap.head()),static_cast<unsigned int>(b-heap.head()),static_cast<unsigned int>(zero-heap.head()));
    state("allocated",heap);printf("OWNS|%d|%d|%d|%d\n",heap.OwnsAllocation(a),heap.OwnsAllocation(zero),heap.OwnsAllocation(NULL),heap.OwnsAllocation(heap.head()+heap.GetCapacity()));
    heap.DeAllocate(b);state("release_b",heap);heap.DeAllocate(a);state("release_a",heap);heap.DeAllocate(zero);state("released_all",heap);
    byte* full=heap.Allocate(240);require(full!=NULL);byte* failed=heap.Allocate(16);printf("CAPACITY_FAIL|%d\n",failed==NULL);state("full",heap);
    heap.DeAllocate(full);heap.DeAllocate(NULL);state("reused",heap);
    heap.Shutdown();state("shutdown",heap);
    byte* external=static_cast<byte*>(_aligned_malloc(512,16));require(external!=NULL);
    printf("BORROWED_START|%u\n",heap.Startup(256,external));state("borrowed",heap);
    full=heap.Allocate(256);zero=heap.Allocate(0);require(full && zero);
    printf("END_ZERO|%u|%d\n",static_cast<unsigned int>(zero-heap.head()),heap.OwnsAllocation(zero));
    heap.DeAllocate(zero);heap.DeAllocate(full);heap.Shutdown();external[0]=42;require(external[0]==42);_aligned_free(external);
    TempHeap* global=GetTempHeap();require(global!=NULL && global==GetTempHeap());
    printf("HOST_START|%u\n",global->Startup(4096,NULL));byte* p=global->Allocate(23);require(p!=NULL);global->DeAllocate(p);global->Shutdown();
    printf("HOST_BOUND|1\n");
}

static void trace(const char* input,const char* output) {
    FILE* in=fopen(input,"r");FILE* out=fopen(output,"wb");require(in && out);
    ProbeHeap heap;std::vector<byte*> allocations;byte* borrowed=NULL;uint index=0,op,a,b;
    while(fscanf(in,"%u %u %u",&op,&a,&b)==3) {
        uint value=0;
        if(op==0 || op==1) {
            require(heap.head()==NULL && !borrowed);
            if(op==1) { borrowed=static_cast<byte*>(_aligned_malloc(static_cast<size_t>(a)+16,16));require(borrowed!=NULL); }
            value=heap.Startup(a,borrowed);require(heap.head()!=NULL);
        } else if(op==2) {
            if(allocations.size()<=a)allocations.resize(static_cast<size_t>(a)+1,NULL);
            require(allocations[a]==NULL);byte* p=heap.Allocate(b);allocations[a]=p;
            value=p?static_cast<uint>(p-heap.head()):UINT_MAX;
        } else if(op==3) {
            require(a<allocations.size() && allocations[a]!=NULL);heap.DeAllocate(allocations[a]);allocations[a]=NULL;
        } else if(op==4) {
            require(heap.leases()==0);heap.Shutdown();
            if(borrowed) { borrowed[0]=73;require(borrowed[0]==73);_aligned_free(borrowed);borrowed=NULL; }
        } else require(false);
        const uint row[]={index++,op,a,b,value,heap.GetCapacity(),heap.GetAvailable(),static_cast<uint>(heap.leases()),static_cast<uint>(heap.offset()),heap.flags()};
        require(fwrite(row,sizeof(row),1,out)==1);
    }
    require(feof(in)!=0 && heap.head()==NULL);fclose(in);require(fclose(out)==0);
    printf("TRACE|%u\n",index);
}

#ifdef TEMP_HEAP_CANDIDATE
static void boundaries() {
    ProbeHeap heap;
    require(!heap.Allocate(0) && !heap.Allocate(1) && heap.leases()==0 && heap.offset()==0);
    require(heap.Startup(1048576,NULL)==1048576);
    require((reinterpret_cast<ULONG_PTR>(heap.head())&4095)==0);
    for(uint i=0;i<15;++i)require(!heap.Allocate(UINT_MAX-i) && heap.leases()==0 && heap.offset()==0);
    require(!heap.Allocate(UINT_MAX-15) && heap.leases()==0 && heap.offset()==0);
    std::vector<byte*> leases;leases.reserve(65535);
    for(uint i=0;i<65535;++i) { byte* p=heap.Allocate(1);require(p && p==heap.head()+static_cast<size_t>(i)*16);leases.push_back(p); }
    require(heap.leases()==65535 && !heap.Allocate(1) && heap.leases()==65535);
    heap.DeAllocate(leases[0]);leases[0]=heap.Allocate(1);require(leases[0] && heap.leases()==65535);
    for(uint i=0;i<65535;++i)heap.DeAllocate(leases[i]);
    require(heap.leases()==0 && heap.offset()==0 && heap.GetAvailable()==heap.GetCapacity());
    uint rejected=0;byte* p=heap.Allocate(16);require(p!=NULL);
    try { heap.Startup(256,NULL); } catch(const std::logic_error&) { ++rejected; }
    try { heap.DeAllocate(p+1); } catch(const std::invalid_argument&) { ++rejected; }
    byte outside=0;try { heap.DeAllocate(&outside); } catch(const std::invalid_argument&) { ++rejected; }
    require(heap.leases()==1 && heap.offset()==16);heap.DeAllocate(p);
    try { heap.DeAllocate(p); } catch(const std::logic_error&) { ++rejected; }
    try { heap.Startup(256,NULL); } catch(const std::logic_error&) { ++rejected; }
    require(heap.leases()==0 && heap.offset()==0);heap.Shutdown();
    byte* borrowed=static_cast<byte*>(_aligned_malloc(512,16));require(borrowed!=NULL);
    try { heap.Startup(256,borrowed+1); } catch(const std::invalid_argument&) { ++rejected; }
    require(heap.head()==NULL && heap.leases()==0 && rejected==6);
    require(heap.Startup(256,borrowed)==256);p=heap.Allocate(1);require(p!=NULL);heap.DeAllocate(p);heap.Shutdown();_aligned_free(borrowed);
    printf("BOUNDARIES|15|65535|6\n");
}

static void largeOffsets() {
    SYSTEM_INFO systemInfo;GetSystemInfo(&systemInfo);require(systemInfo.dwPageSize==4096);
    const SIZE_T reservation=static_cast<SIZE_T>(1)<<32;
    byte* memory=static_cast<byte*>(VirtualAlloc(NULL,reservation,MEM_RESERVE,PAGE_READWRITE));require(memory!=NULL);
    require(reinterpret_cast<ULONG_PTR>(memory)>UINT_MAX);
    require(VirtualAlloc(memory,4096,MEM_COMMIT,PAGE_READWRITE)==memory);
    require(VirtualAlloc(memory+static_cast<SIZE_T>(0x80000000U),4096,MEM_COMMIT,PAGE_READWRITE)==memory+static_cast<SIZE_T>(0x80000000U));
    ProbeHeap heap;require(heap.Startup(0xfffffff0U,memory)==0xfffffff0U);
    byte* a=heap.Allocate(0x80000000U);byte* b=heap.Allocate(0x7ffffff0U);
    require(a==memory && b==memory+static_cast<SIZE_T>(0x80000000U));
    require(heap.GetAvailable()==0 && static_cast<uint>(heap.offset())==0xfffffff0U && heap.leases()==2);
    a[0]=57;b[0]=82;require(a[0]==57 && b[0]==82);
    require(!heap.Allocate(16) && heap.leases()==2 && heap.GetAvailable()==0);
    byte* zero=heap.Allocate(0);require(zero==memory+static_cast<SIZE_T>(0xfffffff0U) && !heap.OwnsAllocation(zero));
    heap.DeAllocate(b);heap.DeAllocate(a);require(heap.GetAvailable()==0);heap.DeAllocate(zero);
    require(heap.offset()==0 && heap.leases()==0 && heap.GetAvailable()==0xfffffff0U);
    heap.Shutdown();require(VirtualFree(memory,0,MEM_RELEASE)!=0);
    printf("LARGE_OFFSETS|4294967296|8192|2147483648|4294967280\n");
}

const uint kSlots=64,kBatches=128;
struct BatchWorker {
    ProbeHeap* heap;uint id;HANDLE go,ready,release,done;volatile LONG failures;
    byte* slots[kSlots];uint sizes[kSlots];
};
static byte pattern(uint id,uint batch,uint slot,uint byteIndex) { return static_cast<byte>(id*73+batch*29+slot*17+byteIndex); }
static unsigned __stdcall batchWork(void* input) {
    BatchWorker& w=*static_cast<BatchWorker*>(input);
    for(uint batch=0;batch<kBatches;++batch) {
        WaitForSingleObject(w.go,INFINITE);
        for(uint i=0;i<kSlots;++i) {
            w.sizes[i]=1+(w.id*37+batch*19+i*11)%255;w.slots[i]=w.heap->Allocate(w.sizes[i]);
            if(!w.slots[i])InterlockedIncrement(&w.failures);
            else for(uint j=0;j<w.sizes[i];++j)w.slots[i][j]=pattern(w.id,batch,i,j);
            if(i%8==0) { byte* failed=w.heap->Allocate(w.heap->GetCapacity());if(failed) { InterlockedIncrement(&w.failures);w.heap->DeAllocate(failed); } }
        }
        SetEvent(w.ready);WaitForSingleObject(w.release,INFINITE);
        for(uint k=0;k<kSlots;++k) {
            const uint i=(k*17+batch)%kSlots;
            if(w.slots[i]) {
                for(uint j=0;j<w.sizes[i];++j)if(w.slots[i][j]!=pattern(w.id,batch,i,j))InterlockedIncrement(&w.failures);
                w.heap->DeAllocate(w.slots[i]);
            }
        }
        SetEvent(w.done);
    }
    return 0;
}
struct Span { ULONG_PTR start,end;bool operator<(const Span& other) const { return start<other.start; } };
static void concurrentBatches() {
    for(uint workers=1;workers<=8;workers*=2) {
        ProbeHeap heap;const uint capacity=workers*kSlots*256;require(heap.Startup(capacity,NULL)==capacity);
        BatchWorker data[8];HANDLE threads[8],ready[8],done[8];
        for(uint w=0;w<workers;++w) {
            data[w].heap=&heap;data[w].id=w;data[w].failures=0;
            data[w].go=CreateEvent(NULL,FALSE,FALSE,NULL);data[w].ready=CreateEvent(NULL,FALSE,FALSE,NULL);
            data[w].release=CreateEvent(NULL,FALSE,FALSE,NULL);data[w].done=CreateEvent(NULL,FALSE,FALSE,NULL);
            require(data[w].go && data[w].ready && data[w].release && data[w].done);
            ready[w]=data[w].ready;done[w]=data[w].done;
            threads[w]=reinterpret_cast<HANDLE>(_beginthreadex(NULL,0,batchWork,&data[w],0,NULL));require(threads[w]!=NULL);
        }
        for(uint batch=0;batch<kBatches;++batch) {
            for(uint w=0;w<workers;++w)require(SetEvent(data[w].go)!=0);
            require(WaitForMultipleObjects(workers,ready,TRUE,10000)==WAIT_OBJECT_0);
            require(heap.leases()==static_cast<LONG>(workers*kSlots));
            std::vector<Span> spans;
            for(uint w=0;w<workers;++w) {
                require(data[w].failures==0);
                for(uint i=0;i<kSlots;++i) {
                    byte* p=data[w].slots[i];require(p && heap.OwnsAllocation(p) && !(reinterpret_cast<ULONG_PTR>(p)&15));
                    Span span={reinterpret_cast<ULONG_PTR>(p),reinterpret_cast<ULONG_PTR>(p)+((data[w].sizes[i]+15)&~15U)};spans.push_back(span);
                    for(uint j=0;j<data[w].sizes[i];++j)require(p[j]==pattern(w,batch,i,j));
                }
            }
            std::sort(spans.begin(),spans.end());for(size_t i=1;i<spans.size();++i)require(spans[i-1].end<=spans[i].start);
            for(uint w=0;w<workers;++w)require(SetEvent(data[w].release)!=0);
            require(WaitForMultipleObjects(workers,done,TRUE,10000)==WAIT_OBJECT_0);
            require(heap.leases()==0 && heap.offset()==0 && heap.GetAvailable()==capacity);
        }
        require(WaitForMultipleObjects(workers,threads,TRUE,10000)==WAIT_OBJECT_0);
        for(uint w=0;w<workers;++w) {
            require(data[w].failures==0);CloseHandle(threads[w]);CloseHandle(data[w].go);CloseHandle(data[w].ready);CloseHandle(data[w].release);CloseHandle(data[w].done);
        }
        heap.Shutdown();printf("BATCHES|%u|%u|%u\n",workers,kBatches,workers*kSlots*kBatches);
    }
}

struct PressureWorker { ProbeHeap* heap;uint id;HANDLE start;volatile LONG* owners;volatile LONG failures;uint allocated,failed; };
static unsigned __stdcall pressureWork(void* input) {
    PressureWorker& w=*static_cast<PressureWorker*>(input);WaitForSingleObject(w.start,INFINITE);
    for(uint i=0;i<50000;++i) {
        byte* p=w.heap->Allocate(16);
        if(!p) { ++w.failed;SwitchToThread();continue; }
        ++w.allocated;const size_t slot=static_cast<size_t>(p-w.heap->head())/16;
        if(slot>=2 || InterlockedCompareExchange(&w.owners[slot],static_cast<LONG>(w.id+1),0)!=0)InterlockedIncrement(&w.failures);
        else {
            memset(p,static_cast<int>(w.id+1),16);SwitchToThread();
            for(uint j=0;j<16;++j)if(p[j]!=w.id+1)InterlockedIncrement(&w.failures);
            InterlockedExchange(&w.owners[slot],0);
        }
        w.heap->DeAllocate(p);
    }
    return 0;
}
static void pressure() {
    ProbeHeap heap;require(heap.Startup(32,NULL)==32);volatile LONG owners[2]={0,0};
    HANDLE start=CreateEvent(NULL,TRUE,FALSE,NULL);require(start!=NULL);
    PressureWorker data[8];HANDLE threads[8];
    for(uint i=0;i<8;++i) {
        data[i].heap=&heap;data[i].id=i;data[i].start=start;data[i].owners=owners;data[i].failures=0;data[i].allocated=0;data[i].failed=0;
        threads[i]=reinterpret_cast<HANDLE>(_beginthreadex(NULL,0,pressureWork,&data[i],0,NULL));require(threads[i]!=NULL);
    }
    require(SetEvent(start)!=0 && WaitForMultipleObjects(8,threads,TRUE,20000)==WAIT_OBJECT_0);
    uint allocated=0,failed=0;for(uint i=0;i<8;++i) { require(data[i].failures==0);allocated+=data[i].allocated;failed+=data[i].failed;CloseHandle(threads[i]); }
    require(allocated && failed && allocated+failed==400000 && heap.leases()==0 && heap.offset()==0 && !owners[0] && !owners[1]);
    byte* p=heap.Allocate(32);require(p!=NULL);heap.DeAllocate(p);heap.Shutdown();CloseHandle(start);
    printf("PRESSURE|8|400000|%u|%u\n",allocated,failed);
}

extern "C" TempHeap* ZeroSisSdkTempHeapHost();
extern "C" void ZeroSisSdkTempHeapReturnNull(bool enabled);
struct HostWorker { TempHeap* expected;HANDLE start;volatile LONG failures; };
static unsigned __stdcall bindHost(void* input) {
    HostWorker& w=*static_cast<HostWorker*>(input);WaitForSingleObject(w.start,INFINITE);
    for(uint i=0;i<1024;++i)if(GetTempHeap()!=w.expected)InterlockedIncrement(&w.failures);
    return 0;
}
static void hostThreads() {
    TempHeap* expected=ZeroSisSdkTempHeapHost();require(expected!=NULL);
    HostWorker data[8];HANDLE threads[8];HANDLE start=CreateEvent(NULL,TRUE,FALSE,NULL);require(start!=NULL);
    for(uint i=0;i<8;++i) { data[i].expected=expected;data[i].start=start;data[i].failures=0;threads[i]=reinterpret_cast<HANDLE>(_beginthreadex(NULL,0,bindHost,&data[i],0,NULL));require(threads[i]!=NULL); }
    require(SetEvent(start)!=0 && WaitForMultipleObjects(8,threads,TRUE,10000)==WAIT_OBJECT_0);
    for(uint i=0;i<8;++i) { require(data[i].failures==0);CloseHandle(threads[i]); }CloseHandle(start);
    ZeroSisSdkTempHeapReturnNull(true);uint rejected=0;
    for(uint i=0;i<2;++i)try { GetTempHeap(); } catch(const std::runtime_error& e) { require(!strcmp(e.what(),"Engine host GetTempHeap returned null"));++rejected; }
    require(rejected==2);ZeroSisSdkTempHeapReturnNull(false);
    require(GetTempHeap()->Startup(256,NULL)==256);byte* p=GetTempHeap()->Allocate(16);require(p!=NULL);GetTempHeap()->DeAllocate(p);GetTempHeap()->Shutdown();
    printf("HOST_THREADS|8|8192\nNULL_HOST|2|RECOVERED\n");
}
#endif
int main(int argc,char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);
    try {
        require(argc>=2);
        if(!strcmp(argv[1],"probe"))probe();
        else if(!strcmp(argv[1],"trace")) { require(argc==4);trace(argv[2],argv[3]); }
#ifdef TEMP_HEAP_CANDIDATE
        else if(!strcmp(argv[1],"boundaries"))boundaries();
        else if(!strcmp(argv[1],"large"))largeOffsets();
        else if(!strcmp(argv[1],"batches"))concurrentBatches();
        else if(!strcmp(argv[1],"pressure"))pressure();
        else if(!strcmp(argv[1],"host"))hostThreads();
#endif
        else require(false);
        printf("PASS|%u\n",checks);return 0;
    }
    catch(...) { fprintf(stderr,"UNEXPECTED_EXCEPTION\n");return 1; }
}
