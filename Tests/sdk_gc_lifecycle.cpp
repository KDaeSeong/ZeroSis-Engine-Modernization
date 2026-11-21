#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <atomic>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <new>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>
#include "ZeroSisHostBinding.h"
#include "ZeroSisGlobalsLifecycle.h"

static std::atomic<unsigned> checks(0);
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x); std::abort(); } } while(0)
#define SAFE_DELETE(x) do { delete (x); (x)=nullptr; } while(0)
struct Injected { int position; };
static int point=0,failAt=0,liveOwners=0,loaderRefs=0,hostStarts=0,hostStops=0,hostFailures=0;
static bool hostActive=false,infoActive=false,reenter=false,noDatabase=false,noLoader=false,hostFailAfter=false;
static unsigned reentries=0,contextDestructions=0,hostReleases=0;
static std::vector<std::string> trace;
static std::mutex pauseMutex;
static std::condition_variable pauseCv;
static bool pauseHost=false,hostEntered=false,releaseHost=false;
static void Reenter();
static void Checkpoint(const char* name) {
    trace.push_back(name); ++point;
    if(reenter) Reenter();
    if(point==failAt) throw Injected{point};
}
struct Owner {
    explicit Owner(const char* n):name(n) { ++liveOwners; }
    ~Owner() { trace.push_back("delete:"+name); --liveOwners; }
    std::string name;
};
static Owner* NewOwner(const char* name) { Checkpoint(name); return new Owner(name); }
#define FNEW(type,category,flags) NewOwner(#type)
enum DirectionTypes { DIRECTION_NORTHEAST, DIRECTION_EAST, DIRECTION_SOUTHEAST, DIRECTION_SOUTHWEST, DIRECTION_WEST, DIRECTION_NORTHWEST, NUM_DIRECTION_TYPES };
static constexpr int NUM_CITY_PLOTS=37,CITY_PLOTS_DIAMETER=7;
using GreatWorkArtifactClass=int;
using GreatWorkSlotType=int;
using MissionTypes=int;
static constexpr int NO_GREAT_WORK_ARTIFACT_CLASS=-1,NO_GREAT_WORK_SLOT=-1,NO_MISSION=-1;
namespace CvTypes { void ResetTypes() noexcept; }
#include "gc_lifecycle_types.h"
struct Host {
    void InitGlobals() {
        ++hostStarts; Checkpoint("host-enter"); hostActive=true; Checkpoint("host-partial");
        std::unique_lock<std::mutex> lock(pauseMutex);
        if(pauseHost) { hostEntered=true; pauseCv.notify_all(); pauseCv.wait(lock,[]{return releaseHost;}); }
    }
    void UninitGlobals() {
        ++hostStops; trace.push_back("host-cleanup");
        if(reenter) Reenter();
        if(hostFailAfter) hostActive=false;
        if(hostFailures>0) { --hostFailures; throw std::runtime_error("host cleanup injection"); }
        hostActive=false;
    }
    template<class T> T* QueryInterface() { return static_cast<T*>(this); }
    static void operator delete(void*) noexcept { ++hostReleases; }
};
using ICvEngineUtility1=Host;
using ICvEngineUtility4=Host;
struct Defines { void Release() { trace.push_back("defines-release"); } };
namespace Database {
struct Connection {
    bool Execute(Defines&,const char*) { Checkpoint("defines-query");return true; }
};
}
struct ICvDLLDatabaseUtility1 {
    bool PerformDatabasePostProcessing() { Checkpoint("database-postprocess");return true; }
    bool CacheGameDatabaseData() { Checkpoint("database-cache"); infoActive=true;CorruptTypes();Checkpoint("database-partial");return true; }
    static void operator delete(void*) noexcept { --loaderRefs; }
};
static ICvDLLDatabaseUtility1 loader;
struct CvPlayerAI {
    static Owner* players;
    static void initStatics() { Checkpoint("players");players=new Owner("players"); }
    static void freeStatics() { trace.push_back("players-cleanup");SAFE_DELETE(players); }
};
struct CvTeam {
    static Owner* teams;
    static void initStatics() { Checkpoint("teams");teams=new Owner("teams"); }
    static void freeStatics() { trace.push_back("teams-cleanup");SAFE_DELETE(teams); }
};
Owner* CvPlayerAI::players=nullptr;
Owner* CvTeam::teams=nullptr;
struct CvGlobals {
    Host* host=nullptr;
    bool retainedLoader=false;
    Defines m_kGlobalDefinesLookup;
    int m_aiPlotDirectionX[6]{},m_aiPlotDirectionY[6]{},m_aiCityPlotX[37]{},m_aiCityPlotY[37]{},m_aiCityPlotPriority[37]{};
    DirectionTypes m_aeTurnLeftDirection[6]{},m_aeTurnRightDirection[6]{};
    int m_aaiXYCityPlot[7][7]{};
    void init(); void uninit();
    Host* getDLLIFace() { return host; }
    void setDLLIFace(Host* h) { host=h; }
    ICvDLLDatabaseUtility1* getDatabaseLoadUtility() {
        Checkpoint("database-loader"); if(noLoader)return nullptr;
        if(!retainedLoader) { retainedLoader=true;++loaderRefs; }
        ++loaderRefs; return &loader;
    }
    void releaseDatabaseLoadUtility() {
        trace.push_back("loader-release");if(retainedLoader){retainedLoader=false;--loaderRefs;}
    }
    void deleteInfoArrays() {
        CHECK(liveOwners==0 && !hostActive);trace.push_back("info-cleanup");infoActive=false;
    }
#include "gc_lifecycle_fields.h"
};
static CvGlobals GC;
static Host host;
static Database::Connection database;
static Database::Connection* GetGameDatabase() { Checkpoint("database-connection");return noDatabase ? nullptr : &database; }
#define gDLL GC.host
#define CvAssertMsg(x,message) CHECK(x)
struct CvDllGameContext {
    ~CvDllGameContext() { ++contextDestructions; }
    static CvDllGameContext* s_pSingleton;
    static HANDLE s_hHeap;
    void Init(); void Uninit();
    static bool SetDLLIFace(ICvEngineUtility1*);
    static bool ShutdownSingleton();
};
CvDllGameContext* CvDllGameContext::s_pSingleton=nullptr;
HANDLE CvDllGameContext::s_hHeap=INVALID_HANDLE_VALUE;
#include "gc_lifecycle_fixture.h"
static CvDllGameContext context;

static void Reenter() {
    try { context.Init();CHECK(false); }catch(const std::logic_error&){}
    try { context.Uninit();CHECK(false); }catch(const std::logic_error&){}
    CHECK(!CvDllGameContext::SetDLLIFace(nullptr) && GetLastError()==ERROR_BUSY);
    CHECK(!CvDllGameContext::ShutdownSingleton() && GetLastError()==ERROR_BUSY);
    ++reentries;
}
static void Reset() {
    CHECK(liveOwners==0 && loaderRefs==0 && !hostActive && !infoActive);
    point=failAt=hostStarts=hostStops=hostFailures=0;
    reenter=noDatabase=noLoader=hostFailAfter=false;
    GC.host=&host;CvTypes::ResetTypes();trace.clear();
}
#ifndef GC_LIFECYCLE_ORIGINAL
static bool IsPhase(ZeroSisGlobalsLifecycle::Phase phase) {
    ZeroSisHostBinding::Lease lease(ZeroSisHostBinding::ProcessGate());CHECK(static_cast<bool>(lease));
    return ZeroSisGlobalsLifecycle::ProcessState().GetPhase()==phase;
}
static std::size_t CleanupPosition() {
    ZeroSisHostBinding::Lease lease(ZeroSisHostBinding::ProcessGate());CHECK(static_cast<bool>(lease));
    return ZeroSisGlobalsLifecycle::ProcessState().NextCleanupStep();
}
#endif
static void CheckClean() { CHECK(liveOwners==0 && loaderRefs==0 && !hostActive && !infoActive); }

int main() {
    Reset();context.Init();const int total=point;
    CHECK(liveOwners==40 && loaderRefs==1 && hostActive && infoActive && TypesArePopulated());
    CHECK(GC.m_aiPlotDirectionX[1]==1 && GC.m_aiPlotDirectionY[5]==1 && GC.m_aaiXYCityPlot[3][3]==0);
    context.Uninit();CheckClean();
#ifdef GC_LIFECYCLE_ORIGINAL
    CHECK(TypesArePopulated());
#else
    CHECK(TypesAreDefaults() && IsPhase(ZeroSisGlobalsLifecycle::Phase::Idle));
#endif
    std::printf("NORMAL_TRACE:");for(const auto& item:trace)std::printf("%s|",item.c_str());std::puts("");
    unsigned originalRemaining=0;
    for(int i=1;i<=total;++i) {
        Reset();failAt=i;
        try { context.Init();CHECK(false); }catch(const Injected& error){CHECK(error.position==i);}
        failAt=0;
#ifdef GC_LIFECYCLE_ORIGINAL
        originalRemaining+=static_cast<unsigned>(liveOwners);context.Uninit();
#else
        CheckClean();CHECK(TypesAreDefaults() && IsPhase(ZeroSisGlobalsLifecycle::Phase::Idle));
        CHECK(hostStops==(i>1 ? 1 : 0));
        const auto before=trace;context.Uninit();CHECK(trace==before);
#endif
        CheckClean();context.Init();CHECK(TypesArePopulated());context.Uninit();CheckClean();
    }
    std::printf("FAILURE_POINTS:%d ORIGINAL_REMAINING:%u\n",total,originalRemaining);
    for(int kind=0;kind<2;++kind) {
        Reset();noDatabase=kind==0;noLoader=kind==1;
        try{context.Init();CHECK(false);}catch(const std::runtime_error&){}
#ifdef GC_LIFECYCLE_ORIGINAL
        context.Uninit();
#endif
        CheckClean();
    }
#ifndef GC_LIFECYCLE_ORIGINAL
    Reset();GC.host=nullptr;
    try{context.Init();CHECK(false);}catch(const std::runtime_error&){}
    CHECK(hostStarts==0 && hostStops==0);CheckClean();CHECK(IsPhase(ZeroSisGlobalsLifecycle::Phase::Idle));
    Reset();context.Init();const auto readyTrace=trace;const int readyPoint=point;
    try{context.Init();CHECK(false);}catch(const std::logic_error&){}
    CHECK(trace==readyTrace && point==readyPoint && IsPhase(ZeroSisGlobalsLifecycle::Phase::Ready));
    CHECK(!CvDllGameContext::SetDLLIFace(nullptr) && GetLastError()==ERROR_BUSY);
    CHECK(!CvDllGameContext::ShutdownSingleton() && GetLastError()==ERROR_BUSY);
    CHECK(GC.host==&host && contextDestructions==0 && hostReleases==0);
    context.Uninit();CheckClean();const auto closedTrace=trace;context.Uninit();CHECK(trace==closedTrace);

    for(int after=0;after<2;++after)for(int startupFailure=0;startupFailure<2;++startupFailure) {
        Reset();hostFailAfter=after!=0;hostFailures=2;
        if(startupFailure) {
            failAt=total;try{context.Init();CHECK(false);}catch(const Injected& error){CHECK(error.position==total);}
            failAt=0;
        } else {
            context.Init();try{context.Uninit();CHECK(false);}catch(const std::runtime_error&){}
        }
        CHECK(IsPhase(ZeroSisGlobalsLifecycle::Phase::CleanupPending));
        CHECK(liveOwners==(startupFailure ? 11 : 12) && loaderRefs==0 && infoActive);
        CHECK(CleanupPosition()==30);
        const auto pendingTrace=trace;const int pendingOwners=liveOwners;
        try{context.Init();CHECK(false);}catch(const std::logic_error&){}
        CHECK(!CvDllGameContext::SetDLLIFace(nullptr) && GetLastError()==ERROR_BUSY);
        CHECK(!CvDllGameContext::ShutdownSingleton() && GetLastError()==ERROR_BUSY);
        CHECK(trace==pendingTrace && liveOwners==pendingOwners && GC.host==&host);
        try{context.Uninit();CHECK(false);}catch(const std::runtime_error&){}
        CHECK(trace.size()==pendingTrace.size()+1 && trace.back()=="host-cleanup" && liveOwners==pendingOwners);
        context.Uninit();CheckClean();CHECK(hostStops==3 && TypesAreDefaults());
        CHECK(IsPhase(ZeroSisGlobalsLifecycle::Phase::Idle));
        context.Init();context.Uninit();CheckClean();
    }
    Reset();reenter=true;context.Init();context.Uninit();reenter=false;
    CHECK(reentries==static_cast<unsigned>(total+1));CheckClean();
    Reset();{
        std::lock_guard<std::mutex> lock(pauseMutex);pauseHost=true;hostEntered=false;releaseHost=false;
    }
    std::thread owner([]{context.Init();});
    {std::unique_lock<std::mutex> lock(pauseMutex);CHECK(pauseCv.wait_for(lock,std::chrono::seconds(5),[]{return hostEntered;}));}
    std::vector<std::thread> workers;
    for(int i=0;i<8;++i)workers.emplace_back([]{for(int n=0;n<16;++n){
        try{context.Init();CHECK(false);}catch(const std::logic_error&){}
        try{context.Uninit();CHECK(false);}catch(const std::logic_error&){}
        CHECK(!CvDllGameContext::SetDLLIFace(nullptr) && GetLastError()==ERROR_BUSY);
        CHECK(!CvDllGameContext::ShutdownSingleton() && GetLastError()==ERROR_BUSY);
    }});
    for(auto& worker:workers)worker.join();
    {std::lock_guard<std::mutex> lock(pauseMutex);releaseHost=true;pauseHost=false;}pauseCv.notify_all();owner.join();
    CHECK(IsPhase(ZeroSisGlobalsLifecycle::Phase::Ready));context.Uninit();CheckClean();
    for(int cycle=0;cycle<64;++cycle){Reset();context.Init();context.Uninit();CHECK(TypesAreDefaults());CheckClean();}
    std::printf("CANDIDATE_RECOVERY:45_CHECKPOINTS 68_TYPES 4_CLEANUP_RETRY_CASES 512_BUSY_CALLS 64_RESTARTS REENTRY:%u\n",reentries);
#endif
    CorruptTypes();CvTypes::ResetTypes();CHECK(TypesAreDefaults());
    GC.host=nullptr;CHECK(CvDllGameContext::ShutdownSingleton());CheckClean();
    std::printf("GC_LIFECYCLE_PASS checks=%u\n",checks.load());return 0;
}
