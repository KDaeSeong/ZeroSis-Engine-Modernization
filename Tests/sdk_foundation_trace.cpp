// C++03-compatible harness for actual SDK classes on both architectures.
#include "SdkFoundationIncludes.h"
#include <cerrno>

static unsigned int checks=0;
static void require(bool value) { ++checks; if(!value) { fprintf(stderr,"FAIL|%u\n",checks); throw std::runtime_error("check"); } }
static void probe() {
    const dword polynomials[]={static_cast<dword>(CRC32),CRC16,CCITT,CRC14,CRC12,0,1,0xffffffffUL,0x82f63b78UL};
    for(unsigned int i=0;i<sizeof(polynomials)/sizeof(polynomials[0]);++i) {
        FCRC crc(polynomials[i]);
        printf("CRC|%08lx|%08lx|%08lx\n",polynomials[i],crc.Calc("123456789",9),crc.CalcBits("123456789",9));
    }
    printf("CRC_GLOBAL|%08lx\n",g_CRC32.Calc("123456789",9));
    FCriticalSection lock;
    printf("LOCK|%d|%d\n",lock.GetLockCount(),lock.GetRecursionCount());
    lock.Enter();printf("LOCK|%d|%d\n",lock.GetLockCount(),lock.GetRecursionCount());
    require(lock.Try());printf("LOCK|%d|%d\n",lock.GetLockCount(),lock.GetRecursionCount());
    lock.Leave();lock.Leave();printf("LOCK|%d|%d\n",lock.GetLockCount(),lock.GetRecursionCount());
    printf("TIMER_BEFORE|%I64d|%I64d|%.17g\n",FTimer::m_qMark,FTimer::m_qRate,FTimer::m_fFreq);
    const double first=FTimer::Read(); LARGE_INTEGER now;require(QueryPerformanceCounter(&now)!=0);
    const double after=FTimer::Read(); const double offset=FTimer::Read(now.QuadPart);
    printf("TIMER_AFTER|%I64d|%I64d|%.17g|%.17g|%.17g|%.17g\n",FTimer::m_qMark,FTimer::m_qRate,FTimer::m_fFreq,first,after,offset);
    const size_t aligns[]={1,2,4,8,16,32,64,256,4096};
    for(unsigned int a=0;a<sizeof(aligns)/sizeof(aligns[0]);++a) {
        void* memory=FireMallocAlignedNoTracking(37,aligns[a],__FILE__,__LINE__);require(memory!=NULL);
        require((reinterpret_cast<size_t>(memory)&(aligns[a]-1))==0);memset(memory,0x41,37);FireFreeAlignedNoTracking(memory);
    }
    FireFreeAlignedNoTracking(NULL);printf("ALIGNED|9\n");
}
static void crcTrace(const char* inputPath,const char* outputPath) {
    FILE* input=fopen(inputPath,"rb");require(input!=NULL);
    FILE* output=fopen(outputPath,"wb");require(output!=NULL);
    char magic[8];require(fread(magic,1,8,input)==8 && !memcmp(magic,"ZFC00001",8));
    unsigned int count=0;require(fread(&count,4,1,input)==1 && count<100000);
    for(unsigned int i=0;i<count;++i) {
        unsigned int row[5];require(fread(row,4,5,input)==5 && row[0]==i && row[3]<=1048576 && row[4]<=row[3]);
        std::vector<byte> data(row[3]+1);require(fread(&data[0],1,row[3],input)==row[3]);
        FCRC crc(row[1]);const int length=static_cast<int>(row[3]);const int split=static_cast<int>(row[4]);
        const dword direct=crc.Calc(&data[0],length,row[2]);
        const dword bits=crc.CalcBits(&data[0],length,row[2]);
        const dword chained=crc.Calc(&data[split],length-split,crc.Calc(&data[0],split,row[2]));
        const dword global=g_CRC32.Calc(&data[0],length,row[2]);
        const dword values[]={row[0],row[1],row[2],row[3],direct,bits,chained,global};
        require(fwrite(values,4,8,output)==8);
        require(direct==bits && bits==chained);
    }
    require(fgetc(input)==EOF && !ferror(input));fclose(input);require(fclose(output)==0);
    printf("CRC_RECORDS|%u\n",count);
}
static void crcLayouts(const char* path) {
    FILE* file=fopen(path,"wb");require(file!=NULL);
    const dword polys[]={static_cast<dword>(CRC32),CRC16,CCITT,CRC14,CRC12,0,1,0xffffffffUL,0x82f63b78UL};
    for(unsigned int i=0;i<sizeof(polys)/sizeof(polys[0]);++i) {
        FCRC crc(polys[i]);require(sizeof(crc)==1032);require(fwrite(&crc,1,sizeof(crc),file)==sizeof(crc));
    }
    require(fclose(file)==0);printf("CRC_LAYOUTS|9|1032\n");
}

struct LockState {
    FCriticalSection lock;
    HANDLE gate,attempted,acquired;
    volatile LONG active,failures;
    unsigned __int64 count;
    DWORD ids[4];
    LockState():gate(NULL),attempted(NULL),acquired(NULL),active(0),failures(0),count(0) { memset(ids,0,sizeof(ids)); }
};
struct LockWorker { LockState* state;unsigned int slot;bool blocked; };
static unsigned int __stdcall lockWorker(void* context) {
    LockWorker& worker=*static_cast<LockWorker*>(context);LockState& state=*worker.state;
    state.ids[worker.slot]=GetCurrentThreadId();
    if(worker.blocked) {
        if(state.lock.Try()) { InterlockedIncrement(&state.failures);state.lock.Leave(); }
        SetEvent(state.attempted);state.lock.Enter();SetEvent(state.acquired);++state.count;state.lock.Leave();
    } else {
        if(WaitForSingleObject(state.gate,10000)!=WAIT_OBJECT_0) { InterlockedIncrement(&state.failures);return 1; }
        for(unsigned int i=0;i<20000;++i) {
            FScopedCriticalSection held(state.lock);
            if(InterlockedIncrement(&state.active)!=1)InterlockedIncrement(&state.failures);
            if((i&15)==0) {
                if(!state.lock.Try())InterlockedIncrement(&state.failures);
                else { if(state.lock.GetRecursionCount()!=2)InterlockedIncrement(&state.failures);state.lock.Leave(); }
            }
            ++state.count;InterlockedDecrement(&state.active);
        }
    }
    return 0;
}
static HANDLE startThread(unsigned int (__stdcall* entry)(void*),void* context) {
    const uintptr_t thread=_beginthreadex(NULL,0,entry,context,0,NULL);require(thread!=0);return reinterpret_cast<HANDLE>(thread);
}
static void joinThread(HANDLE thread) {
    require(WaitForSingleObject(thread,10000)==WAIT_OBJECT_0);DWORD result=99;
    require(GetExitCodeThread(thread,&result)!=0 && result==0);require(CloseHandle(thread)!=0);
}
static void locks() {
    {
        LockState state;state.attempted=CreateEvent(NULL,TRUE,FALSE,NULL);state.acquired=CreateEvent(NULL,TRUE,FALSE,NULL);
        require(state.attempted && state.acquired);state.lock.Enter();state.lock.Enter();require(state.lock.GetRecursionCount()==2);
        LockWorker worker={&state,0,true};HANDLE thread=startThread(lockWorker,&worker);
        require(WaitForSingleObject(state.attempted,10000)==WAIT_OBJECT_0);
        require(WaitForSingleObject(state.acquired,0)==WAIT_TIMEOUT);
        state.lock.Leave();require(state.lock.GetRecursionCount()==1);require(WaitForSingleObject(state.acquired,0)==WAIT_TIMEOUT);
        state.lock.Leave();require(WaitForSingleObject(state.acquired,10000)==WAIT_OBJECT_0);joinThread(thread);
        require(state.failures==0 && state.count==1 && state.lock.GetRecursionCount()==0);
        CloseHandle(state.attempted);CloseHandle(state.acquired);
        try { FScopedCriticalSection held(state.lock);throw 7; } catch(int) {}
        require(state.lock.GetRecursionCount()==0 && state.lock.Try());state.lock.Leave();
    }
    for(unsigned int workers=1;workers<=4;workers*=2) {
        LockState state;state.gate=CreateEvent(NULL,TRUE,FALSE,NULL);require(state.gate!=NULL);
        LockWorker contexts[4];HANDLE threads[4];
        for(unsigned int i=0;i<workers;++i) { contexts[i].state=&state;contexts[i].slot=i;contexts[i].blocked=false;threads[i]=startThread(lockWorker,&contexts[i]); }
        require(SetEvent(state.gate)!=0);
        for(unsigned int i=0;i<workers;++i)joinThread(threads[i]);
        require(state.count==workers*20000 && state.active==0 && state.failures==0 && state.lock.GetRecursionCount()==0);
        for(unsigned int i=0;i<workers;++i)for(unsigned int j=0;j<i;++j)require(state.ids[i]!=state.ids[j]);
        CloseHandle(state.gate);printf("LOCK_WORKERS|%u|%I64u\n",workers,state.count);
    }
    for(unsigned int i=0;i<512;++i) { FCriticalSection lock;require(lock.Try());require(lock.GetRecursionCount()==1);lock.Leave();require(lock.GetRecursionCount()==0); }
    printf("LOCK_LIFETIMES|512\n");
}

struct TimerWorker {
    HANDLE gate;double first,last;__int64 mark,rate;unsigned int failures;
};
static unsigned int __stdcall timerWorker(void* context) {
    TimerWorker& value=*static_cast<TimerWorker*>(context);value.failures=0;
    if(WaitForSingleObject(value.gate,10000)!=WAIT_OBJECT_0)return 1;
    try {
        value.first=FTimer::Read();value.last=value.first;
        for(unsigned int i=0;i<10000;++i) { double next=FTimer::Read();if(next<value.last)++value.failures;value.last=next; }
        value.mark=FTimer::m_qMark;value.rate=FTimer::m_qRate;
    } catch(...) { ++value.failures; }
    return value.failures?1:0;
}
static void timers(const char* path) {
    require(FTimer::m_fFreq==0 && FTimer::m_qMark==0 && FTimer::m_qRate==0);
#ifndef FOUNDATION_CANDIDATE
    // The original SDK does not serialize first-use initialization. Compare
    // its valid serial initialization; stress simultaneous first use in x64.
    FTimer::Read();
#endif
    HANDLE gate=CreateEvent(NULL,TRUE,FALSE,NULL);require(gate!=NULL);
    TimerWorker values[8];HANDLE threads[8];
    for(unsigned int i=0;i<8;++i) { values[i].gate=gate;threads[i]=startThread(timerWorker,&values[i]); }
    require(SetEvent(gate)!=0);
    for(unsigned int i=0;i<8;++i) { joinThread(threads[i]);require(values[i].failures==0 && values[i].first>=0 && values[i].last>=values[i].first);
        require(values[i].mark==FTimer::m_qMark && values[i].rate==FTimer::m_qRate); }
    CloseHandle(gate);LARGE_INTEGER rate={0},now={0};require(QueryPerformanceFrequency(&rate)!=0 && QueryPerformanceCounter(&now)!=0);
    require(FTimer::m_qRate==rate.QuadPart && FTimer::m_fFreq==1.0/static_cast<double>(rate.QuadPart));
    const __int64 minimum=static_cast<__int64>(static_cast<unsigned __int64>(1)<<63);
    const __int64 offsets[]={0,1,-1,FTimer::m_qMark,FTimer::m_qMark-1,FTimer::m_qMark+1,now.QuadPart,
        now.QuadPart+rate.QuadPart,now.QuadPart-rate.QuadPart,minimum,minimum+1,~minimum};
    FILE* file=fopen(path,"wb");require(file!=NULL);
    for(unsigned int repetition=0;repetition<32;++repetition)for(unsigned int i=0;i<sizeof(offsets)/sizeof(offsets[0]);++i) {
        LARGE_INTEGER before,after;require(QueryPerformanceCounter(&before)!=0);double seconds=FTimer::Read(offsets[i]);require(QueryPerformanceCounter(&after)!=0);
        const __int64 data[]={before.QuadPart,after.QuadPart,offsets[i],FTimer::m_qMark,FTimer::m_qRate};
        require(fwrite(data,8,5,file)==5 && fwrite(&FTimer::m_fFreq,8,1,file)==1 && fwrite(&seconds,8,1,file)==1);
    }
    require(fclose(file)==0);
    FTimer timer;require(static_cast<float>(timer)==0);timer.StartWithOffset(0.25f);
    require(timer.Peek()>=0.25f-4*FLT_EPSILON);
    const float stopped=timer.Stop();require(static_cast<float>(timer)==stopped);Sleep(1);
    require(timer.Peek()>=stopped && static_cast<float>(timer)==stopped);
    require(timer.Start()==0 && static_cast<float>(timer)==0 && timer.Peek()>=0);
    printf("TIMER|8|80000|384\n");
}

static volatile LONG invalidArguments=0;
static void invalidParameter(const wchar_t*,const wchar_t*,const wchar_t*,unsigned int,uintptr_t) { InterlockedIncrement(&invalidArguments); }
struct AllocationWorker { HANDLE gate;unsigned int slot,failures; };
static unsigned int __stdcall allocationWorker(void* context) {
    AllocationWorker& value=*static_cast<AllocationWorker*>(context);value.failures=0;
    if(WaitForSingleObject(value.gate,10000)!=WAIT_OBJECT_0)return 1;
    for(unsigned int i=0;i<1024;++i) {
        const size_t size=(i*17+value.slot*13)%2048,alignment=static_cast<size_t>(1)<<(i%9);
        byte* memory=static_cast<byte*>(FireMallocAlignedNoTracking(size,alignment,__FILE__,__LINE__));
        if(!memory) { ++value.failures;continue; }
        if(reinterpret_cast<size_t>(memory)&(alignment-1))++value.failures;
        memset(memory,static_cast<int>((i+value.slot)&255),size);
        for(size_t j=0;j<size;++j)if(memory[j]!=static_cast<byte>((i+value.slot)&255))++value.failures;
        FireFreeAlignedNoTracking(memory);
    }
    return value.failures?1:0;
}
static void allocations() {
    _invalid_parameter_handler previous=_set_invalid_parameter_handler(invalidParameter);
    const size_t sizes[]={0,1,2,3,7,8,15,16,31,32,63,64,65,127,255,256,257,4095,4096,4097,65537};
    const size_t alignments[]={0,1,2,4,8,16,32,64,128,256,512,1024,2048,4096,8192,16384,32768,65536};
    unsigned int cases=0,highAddresses=0;
    for(unsigned int a=0;a<sizeof(alignments)/sizeof(alignments[0]);++a)for(unsigned int i=0;i<sizeof(sizes)/sizeof(sizes[0]);++i) {
        const size_t alignment=alignments[a];const size_t actualAlignment=alignment?alignment:sizeof(void*);
        byte* memory=static_cast<byte*>(FireMallocAlignedNoTracking(sizes[i],alignment,__FILE__,__LINE__));require(memory!=NULL);
        require((reinterpret_cast<size_t>(memory)&(actualAlignment-1))==0);
        for(size_t j=0;j<sizes[i];++j)memory[j]=static_cast<byte>((j*19+i)&255);
        for(size_t j=0;j<sizes[i];++j)require(memory[j]==static_cast<byte>((j*19+i)&255));
        if(static_cast<unsigned __int64>(reinterpret_cast<size_t>(memory))>0xffffffffULL)++highAddresses;
        FireFreeAlignedNoTracking(memory);++cases;
    }
    void* fromCrt=_aligned_malloc(65,64);require(fromCrt!=NULL);FireFreeAlignedNoTracking(fromCrt);
    void* toCrt=FireMallocAlignedNoTracking(65,64,__FILE__,__LINE__);require(toCrt!=NULL);_aligned_free(toCrt);
    FireFreeAlignedNoTracking(NULL);
    const size_t invalidAlignments[]={0,3,6,65535};
    for(unsigned int i=0;i<sizeof(invalidAlignments)/sizeof(invalidAlignments[0]);++i) {
        errno=0;void* result=FireMallocAlignedNoTracking(37,invalidAlignments[i],__FILE__,__LINE__);
        printf("ALLOC_BOUNDARY|%u|%d|%d\n",static_cast<unsigned int>(invalidAlignments[i]),result!=NULL,errno);
        require(i==0 ? result!=NULL && errno==0 : result==NULL && errno==EINVAL);
        if(result)FireFreeAlignedNoTracking(result);
    }
    errno=0;void* zero=FireMallocAlignedNoTracking(0,16,__FILE__,__LINE__);
    printf("ALLOC_ZERO|%d|%d\n",zero!=NULL,errno);require(zero!=NULL && errno==0);if(zero)FireFreeAlignedNoTracking(zero);
#ifdef FOUNDATION_CANDIDATE
    require(highAddresses>0);
    errno=0;require(FireMallocAlignedNoTracking(static_cast<size_t>(-1),64,__FILE__,__LINE__)==NULL && errno==ENOMEM);
#endif
    _set_invalid_parameter_handler(previous);
    printf("ALLOCATIONS|%u|%u|%ld\n",cases,highAddresses,invalidArguments);
    HANDLE gate=CreateEvent(NULL,TRUE,FALSE,NULL);require(gate!=NULL);HANDLE threads[4];AllocationWorker contexts[4];
    for(unsigned int i=0;i<4;++i) { contexts[i].gate=gate;contexts[i].slot=i;threads[i]=startThread(allocationWorker,&contexts[i]); }
    require(SetEvent(gate)!=0);for(unsigned int i=0;i<4;++i) { joinThread(threads[i]);require(contexts[i].failures==0); }
    CloseHandle(gate);printf("ALLOC_THREADS|4|4096\n");
}
#ifdef FOUNDATION_CANDIDATE
static void invalidCrc() {
    unsigned int rejected=0;
    for(unsigned int i=0;i<4;++i) {
        try { if(i<2)g_CRC32.Calc(NULL,i==0?-1:1);else g_CRC32.CalcBits(NULL,i==2?-1:1); }
        catch(const std::invalid_argument&) { ++rejected; }
    }
    require(rejected==4 && g_CRC32.Calc(NULL,0,0x12345678)==0x12345678 && g_CRC32.CalcBits(NULL,0,0x12345678)==0x12345678);
    printf("CRC_REJECTIONS|4\n");
}
#endif
int main(int argc,char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);setvbuf(stdout,NULL,_IONBF,0);
    try { require(argc>=2);if(!strcmp(argv[1],"probe"))probe();
        else if(!strcmp(argv[1],"crc")) { require(argc==4);crcTrace(argv[2],argv[3]); }
        else if(!strcmp(argv[1],"layout")) { require(argc==3);crcLayouts(argv[2]); }
        else if(!strcmp(argv[1],"locks")) locks();
        else if(!strcmp(argv[1],"timer")) { require(argc==3);timers(argv[2]); }
        else if(!strcmp(argv[1],"allocation"))allocations();
#ifdef FOUNDATION_CANDIDATE
        else if(!strcmp(argv[1],"invalid"))invalidCrc();
#endif
        else require(false);
        printf("PASS|%u\n",checks);return 0;
    } catch(...) { fprintf(stderr,"UNEXPECTED_EXCEPTION\n");return 1; }
}
