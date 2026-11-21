// Real SQLite with exact SDK cache/prefetch/type bodies and a contiguous GC phase.
// Concrete info records, game stages, strings and the host reference are instrumented.
#include "SdkDatabaseIncludes.h"
#include "ZeroSisHostBinding.h"
#include <map>
#include <unordered_map>
#include <cstdarg>
#include <limits>
namespace std { namespace tr1 { using std::unordered_map; } }
using std::make_pair;
using std::auto_ptr;
#define DLLCALL __stdcall
#include "database_cache_abi.h"

unsigned checks=0, liveInfo=0, liveStrings=0, assertions=0;
unsigned defineCalls=0, playableCalls=0, actionCalls=0, validationCalls=0;
unsigned playerCalls=0, teamCalls=0, factoryCalls=0, releaseCalls=0, postCalls=0, phaseCacheCalls=0;
int failStage=0, entryFailure=0, failId=-1, stringAssignFailure=-1;
bool databaseAvailable=true, loaderAvailable=true, postSuccess=true, phaseCacheSuccess=true;
bool phaseUsesActualCache=false;
std::string failTable, activeTable;
std::vector<std::string> collectionCalls;
void Check(bool ok,unsigned line) { ++checks; if(!ok) { std::printf("FAIL|%u|table=%s|mode=%d|id=%d\n",line,activeTable.c_str(),entryFailure,failId);std::fflush(stdout);std::exit(2); } }
#define CHECK(c) Check(!!(c),__LINE__)
#define CvAssertMsg(c,m) do { if(!(c)) ++assertions; } while(false);
#define CvAssert(c) CvAssertMsg(c,"")
#define FNEW(value,pool,flags) new value
Database::Connection ruleDatabase;
#define DB ruleDatabase
struct cvStopWatch {
    cvStopWatch(const char* name,const char*) {
        if(std::strcmp(name,"PrefetchGameData")!=0) { activeTable=name; collectionCalls.push_back(name); }
    }
};
struct CvDatabaseUtility {
    int MaxRows(const char* table) {
        char sql[256];sprintf_s(sql,"SELECT max(rowid) from %s",table);
        Database::Results r;int maximum=0;
        if(DB.Execute(r,sql)) if(r.Step()) maximum=r.GetInt(0)+1;
        return maximum;
    }
};
struct CvString {
    std::string value;
    CvString() { ++liveStrings; }
    ~CvString() { --liveStrings; }
    CvString& operator=(const char* p) {
        if(stringAssignFailure==0) throw std::runtime_error("flavor assignment failure");
        if(stringAssignFailure>0) --stringAssignFailure;
        value=p?p:"";return *this;
    }
};
struct Info {
    int id=-1;
    std::string type;
    Info() { ++liveInfo; }
    ~Info() { --liveInfo; }
    bool CacheResults(Database::Results& row,CvDatabaseUtility&) {
        id=row.GetInt("ID");const char* p=row.GetText("Type");type=p?p:"";
        if(activeTable==failTable && id==failId) {
            if(entryFailure==1) return false;
            if(entryFailure==2) throw std::runtime_error("entry cache failure");
        }
        return true;
    }
};
struct CvNotificationXMLEntries {
    std::vector<Info*>* entries=nullptr;
    std::vector<Info*>& GetNotificationEntries() { return *entries; }
};
using GreatWorkArtifactClass=int;
using GreatWorkSlotType=int;
using MissionTypes=int;
const int NO_GREAT_WORK_ARTIFACT_CLASS=-1, NO_GREAT_WORK_SLOT=-1, NO_MISSION=-1;
struct FILogFile { enum { kDontTimeStamp }; void WarningMsg(const char*,...) {} };
struct LogManager { FILogFile* GetLog(const char*,int) { static FILogFile log;return &log; } } LOGFILEMGR;
struct CvTypes { static void AcquireTypes(Database::Connection&); };
#include "database_cache_data.h"
struct CvPlayerAI { static void initStatics() { ++playerCalls; } };
struct CvTeam { static void initStatics() { ++teamCalls; } };
class CvGlobals {
public:
    std::vector<Info*> lists[62];
    CvNotificationXMLEntries notifications;
    bool haveNotifications=true;
    CvString* flavors=nullptr;
    int flavorCount=0;
    std::map<std::string,int> infoMap;
    Database::Results m_kGlobalDefinesLookup;
    void infoTypeFromStringReset() { infoMap.clear(); }
    void setInfoTypeFromString(const char* type,int id) { infoMap[type]=id; }
    CvString*& getFlavorTypes() { return flavors; }
    void setNumFlavorTypes(int count) { flavorCount=count; }
    Database::Connection* GetGameDatabase() { return databaseAvailable?&DB:nullptr; }
    ICvDLLDatabaseUtility1* getDatabaseLoadUtility();
    void DatabasePhase();
    void Clear() {
        m_kGlobalDefinesLookup.Release();
        for(auto& list:lists) { for(auto* p:list) delete p;list.clear(); }
        delete[] flavors;flavors=nullptr;flavorCount=0;infoMap.clear();
    }
#include "database_cache_getters.h"
} GC;
class CvDllDatabaseUtility {
public:
    bool m_bGameDatabaseNeedsCaching=true;
    template<class T> bool PrefetchCollection(std::vector<T*>&,const char*);
    bool PrefetchGameData();
    bool CacheGameDatabaseData();
    bool ValidateGameDatabase() { ++validationCalls;return false; } // Deliberate optional diagnostic.
    bool ValidatePrefetchProcess() { ++validationCalls;return false; }
    bool LoadGlobalDefines() { ++defineCalls;return failStage!=1; }
    bool UpdatePlayableCivilizationCounts() { ++playableCalls;return failStage!=2; }
    bool SetGlobalActionInfo() { ++actionCalls;return failStage!=3; }
    void LogMsg(const char*,...) const {}
};
CvDllDatabaseUtility cacheLoader;
struct PhaseLoader : ICvDLLDatabaseUtility1 {
    unsigned refs=1;
    void* DLLCALL QueryInterface(GUID) override { ++refs;return this; }
    bool DLLCALL CacheGameDatabaseData() override { ++phaseCacheCalls;return phaseUsesActualCache?cacheLoader.CacheGameDatabaseData():phaseCacheSuccess; }
    bool DLLCALL FlushGameDatabaseData() override { return true; }
    bool DLLCALL PerformDatabasePostProcessing() override { ++postCalls;return postSuccess; }
    void DLLCALL Destroy() override { CHECK(refs>1);--refs;++releaseCalls; }
} phaseLoader;
ICvDLLDatabaseUtility1* CvGlobals::getDatabaseLoadUtility() {
    ++factoryCalls;if(!loaderAvailable)return nullptr;
    ++phaseLoader.refs;return &phaseLoader;
}
#include "database_cache_fixture.h"

void Sql(const std::string& sql) {
    bool ok=DB.Execute(sql.c_str());
    if(!ok) std::printf("SQL_FAILURE|%s|%s\n",sql.c_str(),DB.ErrorMessage());
    CHECK(ok);
}
void Reset() {
    GC.Clear();DB.Close();CHECK(liveInfo==0 && liveStrings==0);
    CHECK(DB.Open(":memory:",Database::OPEN_READWRITE|Database::OPEN_CREATE));
    defineCalls=playableCalls=actionCalls=validationCalls=0;
    playerCalls=teamCalls=factoryCalls=releaseCalls=postCalls=phaseCacheCalls=0;
    failStage=entryFailure=0;failId=-1;failTable.clear();collectionCalls.clear();
    databaseAvailable=loaderAvailable=postSuccess=phaseCacheSuccess=true;
    phaseUsesActualCache=false;cacheLoader.m_bGameDatabaseNeedsCaching=true;
    stringAssignFailure=-1;GC.haveNotifications=true;ResetTypes();
    CHECK(phaseLoader.refs==1);
}
void CreateRules() {
    for(const char* name:ruleTables) {
        Sql(std::string("CREATE TABLE ")+name+"(ID INTEGER PRIMARY KEY, Type TEXT)");
        Sql(std::string("INSERT INTO ")+name+" VALUES(0,'"+name+"_ZERO'),(2,'"+name+"_TWO')");
    }
    Sql("CREATE TABLE Defines(Name TEXT,Value INTEGER)");
    Sql("CREATE TABLE Flavors(ID INTEGER PRIMARY KEY,Type TEXT)");
    Sql("INSERT INTO Flavors VALUES(0,'FLAVOR_ZERO'),(2,'FLAVOR_TWO')");
    Sql("CREATE TABLE GreatWorkArtifactClasses(ID INTEGER PRIMARY KEY,Type TEXT)");
    Sql("CREATE TABLE GreatWorkSlots(ID INTEGER PRIMARY KEY,Type TEXT)");
    Sql("CREATE TABLE OptionalMetadata(Data TEXT)");
    Sql("INSERT INTO OptionalMetadata VALUES('no info columns')");
    Sql("CREATE TABLE CustomInfo(ID INTEGER,Type TEXT)");
    Sql("INSERT INTO CustomInfo VALUES(-7,'CUSTOM_NEGATIVE'),(11,NULL)");
}
void ClearList(std::vector<Info*>& list) { for(auto* p:list) delete p;list.clear(); }
void DirectPrefetch() {
    Reset();Sql("CREATE TABLE Rules(ID INTEGER,Type TEXT)");
    Sql("INSERT INTO Rules VALUES(-1,'RESERVED'),(0,'ZERO'),(2,'TWO'),(5,'FIVE')");
    std::vector<Info*> list;
    for(unsigned i=0;i<16;++i) {
        CHECK(cacheLoader.PrefetchCollection(list,"Rules"));CHECK(list.size()==6);
        CHECK(list[0]->type=="ZERO" && !list[1] && list[2]->type=="TWO" && !list[3] && !list[4] && list[5]->type=="FIVE");
        CHECK(liveInfo==3);
    }
    failTable="Rules";failId=2;entryFailure=1;
    bool ok=cacheLoader.PrefetchCollection(list,"Rules");
#ifdef DATABASE_CACHE_ORIGINAL
    CHECK(ok && list.size()==6 && liveInfo==3);
#else
    CHECK(!ok && list.size()==2 && liveInfo==1);
#endif
    entryFailure=2;bool caught=false;
    try { cacheLoader.PrefetchCollection(list,"Rules"); }
    catch(const std::runtime_error& e) { CHECK(std::string(e.what())=="entry cache failure");caught=true; }
    CHECK(caught && liveInfo==1);ClearList(list);entryFailure=0;
    list.push_back(new Info);auto* previous=list[0];
    ok=cacheLoader.PrefetchCollection(list,"Missing");
#ifdef DATABASE_CACHE_ORIGINAL
    CHECK(ok && list.empty());(void)previous;
#else
    CHECK(!ok && list.size()==1 && list[0]==previous);
#endif
    ClearList(list);
    Sql("CREATE VIEW Broken AS SELECT 0 AS ID, abs(-9223372036854775808) AS Type");
    CHECK(DB.Execute("SELECT 1"));
    ok=cacheLoader.PrefetchCollection(list,"Broken");
#ifdef DATABASE_CACHE_ORIGINAL
    CHECK(ok);
#else
    CHECK(!ok);
#endif
    CHECK(DB.ErrorCode()!=101 && list.empty());
    Sql("CREATE TABLE NoID(Type TEXT)");
    ok=cacheLoader.PrefetchCollection(list,"NoID");
#ifdef DATABASE_CACHE_ORIGINAL
    CHECK(ok);
#else
    CHECK(!ok);
    for(const char* value : {"2147483648","9223372036854775807","1.5","'not-an-id'"}) {
        Sql(std::string("CREATE VIEW Invalid AS SELECT ")+value+" AS ID,'BAD' AS Type");
        CHECK(!cacheLoader.PrefetchCollection(list,"Invalid"));CHECK(liveInfo==0);Sql("DROP VIEW Invalid");
    }
#endif
    Sql("CREATE VIEW Duplicates AS SELECT 0 AS ID,'ONE' AS Type UNION ALL SELECT 0,'TWO'");
    ok=cacheLoader.PrefetchCollection(list,"Duplicates");
#ifdef DATABASE_CACHE_ORIGINAL
    CHECK(ok && liveInfo==2);
#else
    CHECK(!ok && liveInfo==1);
#endif
    ClearList(list);CHECK(liveInfo==0);
    std::puts("PREFETCH|normal_gaps_reserved_ids|cache_false|exception|prepare|step|schema|duplicates");
}
void CollectionStages() {
    for(unsigned i=0;i<62;++i) {
        Reset();CreateRules();failTable=ruleTables[i];failId=0;entryFailure=1;
        bool ok=cacheLoader.CacheGameDatabaseData();
#ifdef DATABASE_CACHE_ORIGINAL
        CHECK(ok && !cacheLoader.m_bGameDatabaseNeedsCaching && collectionCalls.size()==62 && actionCalls==1);
#else
        CHECK(!ok && cacheLoader.m_bGameDatabaseNeedsCaching && collectionCalls.size()==i+1 && playableCalls==0 && actionCalls==0);
        CHECK(GC.lists[i].empty());
#endif
        GC.Clear();entryFailure=0;collectionCalls.clear();cacheLoader.m_bGameDatabaseNeedsCaching=true;
        CHECK(cacheLoader.CacheGameDatabaseData());CHECK(!cacheLoader.m_bGameDatabaseNeedsCaching && collectionCalls.size()==62);
        const auto before=collectionCalls.size();CHECK(cacheLoader.CacheGameDatabaseData());CHECK(collectionCalls.size()==before);
        CHECK(GC.infoMap["CUSTOM_NEGATIVE"]==-7 && GC.infoMap.count("no info columns")==0);
        CHECK(GC.flavorCount==3 && GC.flavors[0].value=="FLAVOR_ZERO" && GC.flavors[1].value.empty() && GC.flavors[2].value=="FLAVOR_TWO");
    }
    Reset();CreateRules();GC.haveNotifications=false;CHECK(cacheLoader.PrefetchGameData());CHECK(collectionCalls.size()==61);
    for(int stage=1;stage<=3;++stage) {
        Reset();CreateRules();failStage=stage;CHECK(!cacheLoader.CacheGameDatabaseData());CHECK(cacheLoader.m_bGameDatabaseNeedsCaching);
#ifndef DATABASE_CACHE_ORIGINAL
        if(stage==1) CHECK(collectionCalls.empty() && playableCalls==0 && actionCalls==0);
        if(stage==2) CHECK(collectionCalls.size()==62 && actionCalls==0);
        if(stage==3) CHECK(actionCalls==1);
#endif
    }
    Reset();DB.Close();bool ok=cacheLoader.CacheGameDatabaseData();
#ifdef DATABASE_CACHE_ORIGINAL
    CHECK(ok && defineCalls==1 && actionCalls==1);
#else
    CHECK(!ok && defineCalls==0 && actionCalls==0 && cacheLoader.m_bGameDatabaseNeedsCaching);
#endif
    std::puts("STAGES|62_collection_failures|caller_cleanup_retry|cached_short_circuit|optional_diagnostics|3_helper_failures");
}
void FlavorFailures() {
#ifndef DATABASE_CACHE_ORIGINAL
    const char* failures[]={
        "", "CREATE TABLE Flavors(Other INTEGER)",
        "CREATE VIEW Flavors AS SELECT 0 AS rowid,0 AS ID,abs(-9223372036854775808) AS Type",
        "CREATE VIEW Flavors AS SELECT 0 AS rowid,7 AS ID,'BAD' AS Type",
        "CREATE VIEW Flavors AS SELECT 0 AS rowid,0 AS ID,NULL AS Type",
        "CREATE VIEW Flavors AS SELECT 2147483647 AS rowid,0 AS ID,'BAD' AS Type",
        "CREATE VIEW Flavors AS SELECT 0 AS rowid,0 AS ID,'A' AS Type UNION ALL SELECT 1,0,'B'",
        "CREATE VIEW Flavors AS SELECT 0 AS rowid,0.5 AS ID,'BAD' AS Type"};
    for(const char* sql:failures) {
        Reset();CreateRules();Sql("DROP TABLE Flavors");if(*sql)Sql(sql);
        GC.flavors=new CvString[2];GC.flavorCount=2;GC.flavors[0]="PREVIOUS";auto* previous=GC.flavors;
        CHECK(!cacheLoader.PrefetchGameData());CHECK(GC.flavors==previous && GC.flavorCount==2 && liveStrings==2 && GC.flavors[0].value=="PREVIOUS");
    }
    Reset();CreateRules();GC.flavors=new CvString[2];GC.flavorCount=2;GC.flavors[0]="PREVIOUS";auto* previous=GC.flavors;
    stringAssignFailure=1;bool caught=false;
    try { cacheLoader.PrefetchGameData(); } catch(const std::runtime_error& e) { caught=std::string(e.what())=="flavor assignment failure"; }
    CHECK(caught && GC.flavors==previous && GC.flavorCount==2 && liveStrings==2);
    stringAssignFailure=-1;CHECK(cacheLoader.PrefetchGameData());CHECK(GC.flavors!=previous && GC.flavorCount==3 && liveStrings==3);
    Sql("DELETE FROM Flavors");CHECK(cacheLoader.PrefetchGameData());CHECK(GC.flavorCount==1 && liveStrings==1 && GC.flavors[0].value.empty());
    std::puts("FLAVORS|8_malformed_sql_cases|assignment_exception|previous_array_preserved|retry|empty_maxrows_preserved");
#endif
}
void TypeFailures() {
    for(const char* table:{"GreatWorkArtifactClasses","GreatWorkSlots","Missions"}) for(int mode=0;mode<2;++mode) {
        Reset();CreateRules();Sql(std::string("DROP TABLE ")+table);
        if(mode==1) Sql(std::string("CREATE VIEW ")+table+" AS SELECT abs(-9223372036854775808) AS Type,0 AS ID");
        bool caught=false;try { CvTypes::AcquireTypes(DB); } catch(const std::runtime_error&) { caught=true; }
#ifdef DATABASE_CACHE_ORIGINAL
        CHECK(!caught);
#else
        CHECK(caught);
#endif
    }
#ifndef DATABASE_CACHE_ORIGINAL
    Reset();CreateRules();Sql("INSERT INTO GreatWorkArtifactClasses VALUES(0,NULL)");
    bool caught=false;try { cacheLoader.CacheGameDatabaseData(); } catch(const std::runtime_error&) { caught=true; }
    CHECK(caught && cacheLoader.m_bGameDatabaseNeedsCaching && actionCalls==0);
#endif
    std::puts("TYPES|3_prepare_failures|3_step_failures|existing_missing_enum_diagnostics_retained");
}
void DatabasePhaseTests() {
    for(int mode=0;mode<4;++mode) {
        Reset();CreateRules();
        if(mode==1)Sql("DROP TABLE Defines");
        if(mode==2)postSuccess=false;
        if(mode==3)phaseCacheSuccess=false;
        bool caught=false;try { GC.DatabasePhase(); } catch(const std::runtime_error&) { caught=true; }
        CHECK(releaseCalls==1 && phaseLoader.refs==1 && factoryCalls==1);
#ifdef DATABASE_CACHE_ORIGINAL
        CHECK(!caught && playerCalls==1 && teamCalls==1 && postCalls==1 && phaseCacheCalls==1);
#else
        CHECK(caught==(mode!=0) && playerCalls==(mode==0?1u:0u) && teamCalls==playerCalls);
        CHECK(postCalls==(mode==1?0u:1u));CHECK(phaseCacheCalls==((mode==1 || mode==2)?0u:1u));
#endif
    }
#ifndef DATABASE_CACHE_ORIGINAL
    Reset();databaseAvailable=false;bool caught=false;
    try { GC.DatabasePhase(); } catch(const std::runtime_error&) { caught=true; }
    CHECK(caught && factoryCalls==0 && playerCalls==0 && teamCalls==0);
    Reset();loaderAvailable=false;caught=false;
    try { GC.DatabasePhase(); } catch(const std::runtime_error&) { caught=true; }
    CHECK(caught && factoryCalls==1 && releaseCalls==0 && playerCalls==0);
    Reset();CreateRules();phaseUsesActualCache=true;failTable="Technologies";failId=0;entryFailure=1;caught=false;
    try { GC.DatabasePhase(); } catch(const std::runtime_error&) { caught=true; }
    CHECK(caught && playerCalls==0 && teamCalls==0 && releaseCalls==1 && cacheLoader.m_bGameDatabaseNeedsCaching);
    GC.Clear();entryFailure=0;GC.DatabasePhase();CHECK(playerCalls==1 && teamCalls==1 && releaseCalls==2 && !cacheLoader.m_bGameDatabaseNeedsCaching);
#endif
    std::puts("GC_PHASE|defines_prepare|postprocess_false|cache_false|local_reference_release|no_whole_gc_execution");
}
void Hex(const std::string& value) { for(unsigned char c:value)std::printf("%02x",c); }
int Corpus(const char* path) {
    CHECK(DB.Open(path,Database::OPEN_READONLY));
    bool success=false;std::string failure;
    try { success=cacheLoader.CacheGameDatabaseData(); }
    catch(const std::exception& error) { failure=error.what(); }
    if(!success) {
        const bool pending=cacheLoader.m_bGameDatabaseNeedsCaching;
        GC.Clear();DB.Close();CHECK(liveInfo==0 && liveStrings==0);
        std::printf("CORPUS_FAILURE|%s|cache_pending=%u|actions=%u|live_after_cleanup=%u\n",failure.c_str(),pending?1u:0u,actionCalls,liveInfo+liveStrings);
        return 3;
    }
    std::printf("CORPUS_RESULT|%u\n",success?1u:0u);CHECK(success);
    for(unsigned i=0;i<62;++i) {
        std::printf("LIST|%s|%llu\n",ruleTables[i],static_cast<unsigned long long>(GC.lists[i].size()));
        for(std::size_t j=0;j<GC.lists[i].size();++j) {
            auto* p=GC.lists[i][j];std::printf("ROW|%llu|",static_cast<unsigned long long>(j));
            if(p) { std::printf("%d|",p->id);Hex(p->type); } else std::printf("NULL");
            std::putchar('\n');
        }
    }
    std::printf("FLAVOR_COUNT|%d\n",GC.flavorCount);
    for(int i=0;i<GC.flavorCount;++i) { std::printf("FLAVOR|%d|",i);Hex(GC.flavors[i].value);std::putchar('\n'); }
    for(const auto& pair:GC.infoMap) { std::printf("LOOKUP|%d|",pair.second);Hex(pair.first);std::putchar('\n'); }
    for(const auto& item:typeValues) std::printf("TYPE|%s|%d\n",item.name,*item.value);
    std::printf("MISSION_COUNT|%u\n",s_uiNUM_MISSION_TYPES);
    GC.Clear();DB.Close();CHECK(liveInfo==0 && liveStrings==0);
    return 0;
}
int main(int argc,char** argv) {
    if(argc==2)return Corpus(argv[1]);
    DirectPrefetch();CollectionStages();FlavorFailures();TypeFailures();DatabasePhaseTests();
    GC.Clear();DB.Close();CHECK(liveInfo==0 && liveStrings==0 && phaseLoader.refs==1);
#ifdef DATABASE_CACHE_ORIGINAL
    std::puts("ORIGINAL|ignored_sql_cache_and_phase_failures_reproduced");
#else
    std::puts("CANDIDATE|checked_sql_cache_and_phase_failures|stops_before_players_teams|partial_state_requires_caller_cleanup");
#endif
    std::puts("SCOPE|real_sqlite|exact_sdk_cache_types_prefetch_contiguous_gc_db_phase|instrumented_info_game_host|no_gamecore_loaded");
    std::printf("PASS|%u\n",checks);
}
