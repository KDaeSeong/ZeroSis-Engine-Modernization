// SDK ownership bodies with instrumented child types, member state, reset and hotkeys.
// No GameCore DLL or game files are opened.
#include <algorithm>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <new>
#include <stdexcept>
#include <string>
#include <vector>
#include "ZeroSisLuaBorrowed.h"

unsigned checks=0, region=0, scalarAttempt=0, failScalarAttempt=0;
bool failArray=false, failNextScalar=false;
struct Injected { int point; };
void Check(bool ok,unsigned line) { ++checks;if(!ok){std::printf("FAIL|%u\n",line);std::fflush(stdout);std::exit(2);} }
#define CHECK(c) Check(!!(c),__LINE__)
struct ArrayRecord { void* p=nullptr;unsigned region=0; } arrays[8];
unsigned liveArrays=0, liveBuffers=0;
void* operator new(std::size_t size) {
    ++scalarAttempt;
    if(failNextScalar || (failScalarAttempt && scalarAttempt==failScalarAttempt)) { failNextScalar=false;throw std::bad_alloc(); }
    void* p=std::malloc(size?size:1);if(!p)throw std::bad_alloc();return p;
}
void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p,std::size_t) noexcept { std::free(p); }
void* operator new[](std::size_t size) {
    if(failArray){failArray=false;throw std::bad_alloc();}
    void* p=std::malloc(size?size:1);if(!p)throw std::bad_alloc();
    for(auto& row:arrays)if(!row.p){row={p,region};++liveArrays;if(region==2)++liveBuffers;return p;}
    std::free(p);throw std::bad_alloc();
}
void operator delete[](void* p) noexcept {
    if(!p)return;
    for(auto& row:arrays)if(row.p==p){if(row.region==2)--liveBuffers;row={};--liveArrays;std::free(p);return;}
    CHECK(false);
}
void operator delete[](void* p,std::size_t) noexcept { ::operator delete[](p); }
struct ObjectRecord { void* p=nullptr;void(*destroy)(void*)=nullptr;int kind=-1,owner=-1; } objects[4096];
unsigned liveObjects=0;
void Register(void* p,void(*destroy)(void*),int kind,int owner) {
    for(auto& row:objects)if(!row.p){row={p,destroy,kind,owner};++liveObjects;return;}CHECK(false);
}
void Unregister(void* p) {
    for(auto& row:objects)if(row.p==p){row={};--liveObjects;return;}CHECK(false);
}
unsigned ReclaimObservedLeaks() {
    unsigned count=0;
    for(auto& row:objects)if(row.p){auto destroy=row.destroy;void* p=row.p;destroy(p);++count;}
    CHECK(liveObjects==0);return count;
}
void ReclaimBuffers() { for(auto& row:arrays)if(row.p && row.region==2)::operator delete[](row.p); }
#define FNEW(type,pool,flags) new type
#define SAFE_DELETE(p) do {delete(p);(p)=nullptr;}while(false)
#define SAFE_DELETE_ARRAY(p) do {delete[](p);(p)=nullptr;}while(false)
#define CvAssert(c) CHECK(c)
#include "startup_owners_fields.h"

namespace Actors {
int currentOwner=-1,constructionAttempt=0,failOwner=-1,failKind=-1,failMode=0,failPoint=0;
unsigned failures=0,originalLeaks=0,normalCases=0;
void Point(int point) { if(currentOwner==failOwner && failPoint==point)throw Injected{point}; }
struct Tag { Tag(){currentOwner=constructionAttempt++;} };
template<int Kind> struct Child {
    template<class... Args> explicit Child(Args&&...) {
        if(currentOwner==failOwner && failKind==Kind && failMode==2)throw Injected{Kind};
        Register(this,[](void* p){delete static_cast<Child*>(p);},Kind,currentOwner);
    }
    ~Child(){Unregister(this);}
    static void* operator new(std::size_t bytes) {
        if(currentOwner==failOwner && failKind==Kind && failMode==1)throw std::bad_alloc();
        return ::operator new(bytes);
    }
    static void operator delete(void* p) noexcept {::operator delete(p);}
    void Uninit() noexcept {}
};
#define CHILD_ALIAS(field,kind,index) using kind=Child<index>;
PLAYER_OWNERS(CHILD_ALIAS)
#undef CHILD_ALIAS
using CvTeamTechs=Child<30>;
using PlayerTypes=int;
using TeamTypes=int;
const int NO_PLAYER=-1;
struct Globals {void* GetGameBuildings(){return this;}} GC;
struct Collection {int point;void clear(){Point(point);}void ClearAll(){Point(point);}};
class CvPlayer {
public:
    Tag tag;
#define OWNER_FIELD(field,kind,index) kind* field=nullptr;
    PLAYER_OWNERS(OWNER_FIELD)
#undef OWNER_FIELD
    Child<26>* m_pNotifications=nullptr;
    Child<27>* m_pDiplomacyRequests=nullptr;
    int m_iNextOperationID=-1,m_eID=NO_PLAYER;
    Collection m_aiPlots{101},m_bfEverConqueredBy{102},m_aiGreatWorkYieldChange{103},m_aiSiphonLuxuryCount{104};
    CvPlayer();~CvPlayer();
    void reset(int id,bool constructor) {
        CHECK(id==NO_PLAYER && constructor);
#define CHECK_PRESENT(field,kind,index) CHECK(field!=nullptr);
        PLAYER_OWNERS(CHECK_PRESENT)
#undef CHECK_PRESENT
        Point(105);Point(106);
    }
    void uninit() {
#define CHECK_PRESENT(field,kind,index) CHECK(field!=nullptr);
        PLAYER_OWNERS(CHECK_PRESENT)
#undef CHECK_PRESENT
    }
};
class CvPlayerAI:public CvPlayer {
public:
    static CvPlayerAI* m_aPlayers;
    static void initStatics();static void freeStatics();
    CvPlayerAI();~CvPlayerAI();
    void AI_reset(){Point(107);}
    void AI_uninit() noexcept {}
};
CvPlayerAI* CvPlayerAI::m_aPlayers=nullptr;
class CvTeam {
public:
    Tag tag;
    static CvTeam* m_aTeams;
#define NULL_FIELD(field) int* field=nullptr;
    TEAM_NULL_FIELDS(NULL_FIELD)
#undef NULL_FIELD
    CvTeamTechs* m_pTeamTechs=nullptr;
    int m_eID=-1;
    CvTeam();~CvTeam();static void initStatics();static void freeStatics();
    void reset(int id,bool constructor) {CHECK(id==0 && constructor && m_pTeamTechs);Point(201);Point(202);}
    void uninit(){CHECK(m_pTeamTechs!=nullptr);m_pTeamTechs->Uninit();}
};
CvTeam* CvTeam::m_aTeams=nullptr;
void ClearFaults(){failOwner=failKind=-1;failMode=failPoint=0;failScalarAttempt=0;failNextScalar=failArray=false;}
void Reset(){CHECK(liveObjects==0 && liveArrays==0);region=1;ClearFaults();constructionAttempt=0;currentOwner=-1;}
void Cleanup(bool team){if(team)CvTeam::freeStatics();else CvPlayerAI::freeStatics();}
void Start(bool team){if(team)CvTeam::initStatics();else CvPlayerAI::initStatics();}
void CheckPublished(bool team) {
    const int count=team?REALLY_MAX_TEAMS:MAX_PLAYERS;
    CHECK(liveObjects==static_cast<unsigned>(count*(team?1:26)));
    for(int i=0;i<count;++i)CHECK((team?CvTeam::m_aTeams[i].m_eID:CvPlayerAI::m_aPlayers[i].m_eID)==i);
}
void Finish(bool team) {
    Cleanup(team);
#ifdef STARTUP_OWNERS_ORIGINAL
    CHECK(liveObjects==(team?0u:MAX_PLAYERS));originalLeaks+=ReclaimObservedLeaks();
#else
    CHECK(liveObjects==0);
#endif
    CHECK(liveArrays==0);
}
void Success(bool team) {Reset();Start(team);CheckPublished(team);Finish(team);++normalCases;}
void Failure(bool team,int owner,int kind,int mode,int point) {
    Reset();failOwner=owner;failKind=kind;failMode=mode;failPoint=point;
    bool caught=false;
    try {Start(team);}catch(const std::bad_alloc&){CHECK(mode==1);caught=true;}
    catch(const Injected& e){CHECK((mode==2 && e.point==kind) || e.point==point);caught=true;}
    CHECK(caught && liveArrays==0);CHECK(team?CvTeam::m_aTeams==nullptr:CvPlayerAI::m_aPlayers==nullptr);++failures;
#ifdef STARTUP_OWNERS_ORIGINAL
    // A derived AI-constructor failure runs the already-completed CvPlayer base
    // destructor; only its original missing culture delete remains in that case.
    const unsigned expected=team?(kind==30?0u:1u):static_cast<unsigned>(owner+(point==107?1:(point?26:kind)));
    CHECK(liveObjects==expected);originalLeaks+=ReclaimObservedLeaks();
#else
    CHECK(liveObjects==0);
#endif
    Success(team);
}
void Duplicate(bool team) {
    Reset();Start(team);auto* players=CvPlayerAI::m_aPlayers;auto* teams=CvTeam::m_aTeams;
    bool caught=false;try{Start(team);}catch(const std::logic_error&){caught=true;}
#ifdef STARTUP_OWNERS_ORIGINAL
    CHECK(!caught);CHECK(team?CvTeam::m_aTeams!=teams:CvPlayerAI::m_aPlayers!=players);
    Cleanup(team);if(team)delete[] teams;else delete[] players;
    originalLeaks+=ReclaimObservedLeaks();CHECK(liveArrays==0);
#else
    CHECK(caught && (team?CvTeam::m_aTeams==teams:CvPlayerAI::m_aPlayers==players));CheckPublished(team);Finish(team);
#endif
}
void Run() {
    for(bool team:{false,true}){
        Reset();failArray=true;bool caught=false;try{Start(team);}catch(const std::bad_alloc&){caught=true;}
        CHECK(caught && liveArrays==0 && liveObjects==0);++failures;Success(team);
    }
    for(int owner:{0,1,MAX_PLAYERS-1}) {
        for(int kind=0;kind<26;++kind)for(int mode=1;mode<=2;++mode)Failure(false,owner,kind,mode,0);
        for(int point=101;point<=107;++point)Failure(false,owner,-1,0,point);
    }
    for(int owner:{0,1,REALLY_MAX_TEAMS-1}) {
        for(int mode=1;mode<=2;++mode)Failure(true,owner,30,mode,0);
        Failure(true,owner,-1,0,201);Failure(true,owner,-1,0,202);
    }
    Duplicate(false);Duplicate(true);Success(false);Success(true);
    std::printf("ACTORS|failures=%u|successful_retries_and_cycles=%u|observed_original_child_leaks=%u|players=%d|teams=%d\n",failures,normalCases,originalLeaks,MAX_PLAYERS,REALLY_MAX_TEAMS);
    CHECK(failures==191 && normalCases==193);
}
}

namespace Actions {
enum ActionSubTypes {ACTIONSUBTYPE_COMMAND,ACTIONSUBTYPE_INTERFACEMODE,ACTIONSUBTYPE_BUILD,ACTIONSUBTYPE_PROMOTION,
                     ACTIONSUBTYPE_SPECIALIST,ACTIONSUBTYPE_CONTROL,ACTIONSUBTYPE_AUTOMATE,ACTIONSUBTYPE_MISSION};
using CommandTypes=int;using InterfaceModeTypes=int;using BuildTypes=int;using PromotionTypes=int;
using SpecialistTypes=int;using ControlTypes=int;using MissionTypes=int;using CvString=std::string;
int NUM_COMMAND_TYPES=4,NUM_INTERFACEMODE_TYPES=4,NUM_CONTROL_TYPES=4;
int faultMode=0,faultIndex=-1,actionAttempt=0,currentAction=-1,publishCalls=0,buildCount=4;
unsigned failures=0,originalBuffers=0,originalActions=0;
void Point(int mode){if(faultMode==mode && currentAction==faultIndex)throw Injected{mode};}
struct CvActionInfo {
    int index=-1,subtype=-1;
    CvActionInfo(){Register(this,[](void* p){delete static_cast<CvActionInfo*>(p);},100,currentAction);}
    ~CvActionInfo(){Unregister(this);}
    static void* operator new(std::size_t bytes){currentAction=actionAttempt++;if(faultMode==4 && currentAction==faultIndex)throw std::bad_alloc();return ::operator new(bytes);}
    static void operator delete(void* p)noexcept{::operator delete(p);}
    void setOriginalIndex(int v){Point(5);index=v;}
    void setSubType(ActionSubTypes v){Point(6);subtype=v;}
};
struct Rule {
    int priority=0,actionIndex=-1,mission=-1,command=-1;
    std::string hotkey;
    int getOrderPriority()const{return priority;}
    void setActionInfoIndex(int v){Point(7);actionIndex=v;}
    void setMissionType(int v){mission=v;}
    int getMissionType()const{return mission;}
    void SetCommandType(int v){command=v;}
    int GetCommandType()const{return command;}
    const char* getHotKey()const{return "K";}
    bool isShiftDown()const{return true;}bool isAltDown()const{return false;}bool isCtrlDown()const{return true;}
    const char* GetDescription()const{return "DESCRIPTION";}
    CvString CreateHotKeyFromDescription(const char*,bool,bool,bool){Point(8);return "Ctrl+Shift+K";}
    void setHotKeyDescription(const char*,const char*,const CvString& value){Point(9);hotkey=value;}
};
using CvCommandInfo=Rule;using CvInterfaceModeInfo=Rule;using CvBuildInfo=Rule;using CvPromotionEntry=Rule;
using CvSpecialistInfo=Rule;using CvControlInfo=Rule;using CvAutomateInfo=Rule;using CvMissionInfo=Rule;
struct Globals {
    Rule rows[8][4];std::vector<CvActionInfo*> actions;
    Rule* At(int kind,int index){CHECK(index>=0 && index<4);return index==1?nullptr:&rows[kind][index];}
    std::vector<CvActionInfo*>& getActionInfo(){
        if(publishCalls++>0 && faultMode==10 && currentAction==faultIndex){actions.shrink_to_fit();failNextScalar=true;}
        return actions;
    }
    int getNumBuildInfos()const{return buildCount;}int getNumPromotionInfos()const{return 4;}
    int getNumSpecialistInfos()const{return 4;}int getNumAutomateInfos()const{return 4;}
    Rule* getCommandInfo(int i){return At(0,i);}Rule* getInterfaceModeInfo(int i){return At(1,i);}
    Rule* getBuildInfo(int i){return At(2,i);}Rule* getPromotionInfo(int i){return At(3,i);}
    Rule* getSpecialistInfo(int i){return At(4,i);}Rule* getControlInfo(int i){return At(5,i);}
    Rule* getAutomateInfo(int i){return At(6,i);}Rule* getMissionInfo(int i){return At(7,i);}
    int getInfoTypeForString(const char*)const{return 0;}
    void Clear(){for(auto* p:actions)delete p;actions.clear();std::vector<CvActionInfo*>().swap(actions);}
} GC;
struct CvTypes{static int getNUM_MISSION_TYPES(){return 4;}};
struct cvStopWatch{cvStopWatch(const char*,const char*){}};
class CvDllDatabaseUtility {
public:
    bool SetGlobalActionInfo();
    void orderHotkeyInfo(int**,int*,int);
    void LogMsg(const char*,...)const{}
} loader;
void Reset(){
    CHECK(liveObjects==0 && liveArrays==0);region=2;faultMode=0;faultIndex=-1;actionAttempt=0;currentAction=-1;publishCalls=0;buildCount=4;
    failArray=failNextScalar=false;failScalarAttempt=0;scalarAttempt=0;
    for(int k=0;k<8;++k)for(int i=0;i<4;++i){GC.rows[k][i]=Rule{};GC.rows[k][i].priority=(k*5+i)%7;}
}
std::vector<int> hotkeyOrdinals;
void Success(bool trace){
    Reset();CHECK(loader.SetGlobalActionInfo());CHECK(GC.actions.size()==24 && liveObjects==24 && liveBuffers==0);
    int priorPriority=1000;hotkeyOrdinals.clear();
    for(unsigned i=0;i<GC.actions.size();++i){
        auto* a=GC.actions[i];auto* rule=GC.At(a->subtype,a->index);CHECK(rule && rule->actionIndex==static_cast<int>(i));
        CHECK(rule->priority<=priorPriority);priorPriority=rule->priority;
        if(a->subtype==3 || a->subtype==4){CHECK(rule->hotkey=="Ctrl+Shift+K");hotkeyOrdinals.push_back(static_cast<int>(i));}
        if(trace)std::printf("NORMAL|%u|%d|%d|%d|%d|%d|%s\n",i,a->subtype,a->index,rule->priority,rule->mission,rule->command,rule->hotkey.c_str());
    }
    CHECK(hotkeyOrdinals.size()==6);GC.Clear();CHECK(liveObjects==0 && liveArrays==0);
}
void Failure(int mode,int index){
    Reset();faultMode=mode;faultIndex=index;
    if(mode==1)failArray=true;
    if(mode==2)failScalarAttempt=1;
    if(mode==3)failScalarAttempt=2;
    bool caught=false;
    try{loader.SetGlobalActionInfo();}catch(const std::bad_alloc&){CHECK(mode<=4 || mode==10);caught=true;}
    catch(const Injected& e){CHECK(e.point==mode);caught=true;}
    CHECK(caught);++failures;failScalarAttempt=0;failNextScalar=false;
    const unsigned published=static_cast<unsigned>(GC.actions.size());
#ifdef STARTUP_OWNERS_ORIGINAL
    CHECK(liveBuffers==(mode==1?0u:1u));CHECK(liveObjects==published+(mode>=5?1u:0u));originalBuffers+=liveBuffers;originalActions+=liveObjects-published;
#else
    CHECK(liveBuffers==0 && liveObjects==published);
#endif
    GC.Clear();ReclaimObservedLeaks();ReclaimBuffers();CHECK(liveObjects==0 && liveArrays==0);Success(false);
}
void Run(){
    std::puts("NORMAL_BEGIN");Success(true);std::puts("NORMAL_END");
    // Capture the six promotion/specialist positions before retries overwrite the vector.
    const auto hotkeys=hotkeyOrdinals;
    Failure(1,-1);Failure(2,-1);Failure(3,-1);
    for(int i=0;i<24;++i){for(int mode=4;mode<=7;++mode)Failure(mode,i);Failure(10,i);}
    for(int i:hotkeys){Failure(8,i);Failure(9,i);}
#ifndef STARTUP_OWNERS_ORIGINAL
    for(int count:{-1,536870912,2147483647}){Reset();buildCount=count;CHECK(!loader.SetGlobalActionInfo());CHECK(liveArrays==0 && liveObjects==0);}
#endif
    CHECK(failures==135);
    std::printf("ACTIONS|failures=%u|original_buffer_leaks=%u|original_unpublished_action_leaks=%u|8_subtypes|gaps_and_ties|retry\n",failures,originalBuffers,originalActions);
}
}

#include "startup_owners_fixture.h"
int main(){
    Actors::Run();Actions::Run();CHECK(liveObjects==0 && liveArrays==0);
#ifdef STARTUP_OWNERS_ORIGINAL
    std::puts("ORIGINAL|partial_child_leaks|culture_owner_missing|duplicate_arrays_replaced|action_buffer_and_entry_leaks");
#else
    std::puts("CANDIDATE|26_player_children_and_team_child_scoped|culture_deleted|duplicate_arrays_preserved|action_buffer_and_entry_scoped|checked_action_counts");
#endif
    std::puts("SCOPE|exact_sdk_ownership_bodies_and_sort|instrumented_member_child_reset_hotkey_services|no_player_initializer_list|no_gamecore_loaded");
    std::printf("PASS|%u\n",checks);
}
