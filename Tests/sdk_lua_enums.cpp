#include "SdkDatabaseIncludes.h"
#include "SdkFLuaIncludes.h"
#include "ZeroSisLuaEnums.h"
#include <map>
#include <cstdint>
#include <new>

static unsigned checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"FAIL|%u|line=%d|%s\n",checks,__LINE__,#x); std::exit(2); } } while (0)
static thread_local int cppBudget = -1;
static long long heapLive = 0;
void* operator new(std::size_t size) {
    if (cppBudget >= 0 && cppBudget-- == 0) { cppBudget = -1; throw std::bad_alloc(); }
    void* value = std::malloc(size ? size : 1);
    if (!value) throw std::bad_alloc();
    ++heapLive; return value;
}
void operator delete(void* value) noexcept { if (value) { --heapLive; std::free(value); } }
void* operator new[](std::size_t size) { return ::operator new(size); }
void operator delete[](void* value) noexcept { ::operator delete(value); }
void operator delete(void* value,std::size_t) noexcept { ::operator delete(value); }
void operator delete[](void* value,std::size_t) noexcept { ::operator delete(value); }

struct LuaMemory {
    int budget = -1;
    std::size_t blocks = 0;
    static void* Allocate(void* user,void* pointer,std::size_t oldSize,std::size_t size) {
        auto& memory = *static_cast<LuaMemory*>(user);
        if (!size) { if (pointer) { --memory.blocks; std::free(pointer); } return nullptr; }
        if (size > oldSize && memory.budget >= 0) {
            if (memory.budget == 0) return nullptr;
            --memory.budget;
        }
        void* value = std::realloc(pointer,size);
        if (value && !pointer) ++memory.blocks;
        return value;
    }
};
struct GlobalsFixture { Database::Connection* db = nullptr; Database::Connection* GetGameDatabase() { return db; } };
static GlobalsFixture GC;
class CvLuaEnums {
public:
    static void Register(lua_State*);
    static int pRegister(lua_State*);
    static void RegisterDynamicEnums(lua_State*,const char*,const char*,const char*,const char*);
};
#include "lua_enum_fixture.h"

static LuaMemory* activeMemory = nullptr;
static int wrapperBudget = -1;
static const char* wrapperTable = "Missions";
static unsigned wrapperErrors = 0;
static void CaptureError(const TCHAR*) { ++wrapperErrors; }
int CvLuaEnums::pRegister(lua_State* state) {
    // Representative entrypoint body only: the two wrappers above are extracted
    // exactly. This fixture does not register the other static SDK enum families.
    lua_getglobal(state,"EnumTarget");
    if (activeMemory) activeMemory->budget = wrapperBudget;
    RegisterDynamicEnums(state,wrapperTable,"ID","Type","NUM_MISSION_TYPES");
    return 0;
}
static void Seed(lua_State* state) {
    lua_newtable(state);
    lua_pushinteger(state,-1); lua_setfield(state,-2,"NO_MISSION");
    lua_pushstring(state,"NO_MISSION"); lua_rawseti(state,-2,-1);
    lua_pushinteger(state,919); lua_setfield(state,-2,"KeepExisting");
    lua_setglobal(state,"EnumTarget");
    lua_pushinteger(state,773);
}
struct Call {
    LuaMemory* memory;
    const char* table = "Missions";
    const char* id = "ID";
    const char* name = "Type";
    const char* count = "NUM_MISSION_TYPES";
    int luaBudget = -1;
    int allocationBudget = -1;
    bool nilDestination = false;
    bool returned = false;
    bool cppFailed = false;
    char error[512] = {};
};
static int Invoke(lua_State* state) {
    Call* call = static_cast<Call*>(lua_touserdata(state,1));
    if (call->nilDestination) lua_pushnil(state); else lua_getglobal(state,"EnumTarget");
    const int base = lua_gettop(state);
    const void* identity = lua_topointer(state,-1);
    call->memory->budget = call->luaBudget;
    cppBudget = call->allocationBudget;
    try {
        CvLuaEnums::RegisterDynamicEnums(state,call->table,call->id,call->name,call->count);
        call->returned = true;
        CHECK(lua_gettop(state) == base && lua_topointer(state,-1) == identity);
        return 0;
    } catch (const std::exception& error) {
        call->cppFailed = true;
        strncpy_s(call->error,sizeof(call->error),error.what(),_TRUNCATE);
    }
    // C++ exception scopes ended before the Lua error can longjmp.
    lua_pushstring(state,call->error);
    return lua_error(state);
}
static int Run(lua_State* state,Call& call) {
    const int base = lua_gettop(state);
    const int status = lua_cpcall(state,Invoke,&call);
    cppBudget = -1; call.memory->budget = -1;
    CHECK(lua_gettop(state) == base + (status ? 1 : 0));
    CHECK(lua_tointeger(state,1) == 773);
    lua_settop(state,base);
    return status;
}
static std::string Hex(const char* bytes,std::size_t size) {
    const char* digits = "0123456789abcdef";
    std::string value;
    for (std::size_t i=0;i<size;++i) {
        const auto byte = static_cast<unsigned char>(bytes[i]);
        value += digits[byte >> 4]; value += digits[byte & 15];
    }
    return value;
}
static std::string Value(lua_State* state,int index) {
    if (lua_type(state,index) == LUA_TSTRING) {
        std::size_t size = 0; const char* value = lua_tolstring(state,index,&size);
        return "s:" + Hex(value,size);
    }
    CHECK(lua_type(state,index) == LUA_TNUMBER);
    return "n:" + std::to_string(static_cast<long long>(lua_tointeger(state,index)));
}
static std::map<std::string,std::string> Table(lua_State* state) {
    std::map<std::string,std::string> values;
    lua_getglobal(state,"EnumTarget"); lua_pushnil(state);
    while (lua_next(state,-2)) { values.emplace(Value(state,-2),Value(state,-1)); lua_pop(state,1); }
    lua_pop(state,1); return values;
}
static void Print(lua_State* state,const char* label) {
    for (const auto& entry:Table(state)) std::printf("MAP|%s|%s|%s\n",label,entry.first.c_str(),entry.second.c_str());
}
static void Open(Database::Connection& db) {
    CHECK(db.Open(":memory:",Database::OPEN_READWRITE | Database::OPEN_CREATE));
    CHECK(db.Execute("CREATE TABLE Missions(ID INTEGER, Type TEXT)"));
    GC.db = &db;
}
static void Fill(Database::Connection& db) {
    CHECK(db.ExecuteMultiple("INSERT INTO Missions VALUES (0,'MISSION_ZERO'), (7,'MISSION_GAP'),"
        "(7,'MISSION_REPLACEMENT'), (8,'MISSION_ZERO'), (2147483647,'MAX_ID'),"
        "(-2147483648,'MIN_ID'),(11,''),(12,'\xED\x95\x9C\xEA\xB8\x80'),(13,'NUM_MISSION_TYPES');"));
}
static void Normal(const char* corpus) {
    Database::Connection db;
    if (corpus) { CHECK(db.Open(corpus,Database::OPEN_READONLY)); GC.db = &db; }
    else { Open(db); Fill(db); }
    const int before = db.StatementCount(); LuaMemory memory;
    auto* state = lua_newstate(LuaMemory::Allocate,&memory); CHECK(state); Seed(state);
    Call call{&memory}; CHECK(Run(state,call) == 0 && call.returned);
    const auto first = Table(state); CHECK(Run(state,call) == 0 && Table(state) == first);
    CHECK(db.StatementCount() == before);
    Print(state,corpus ? "corpus" : "normal");
    lua_close(state); CHECK(memory.blocks == 0);
    if (!corpus) {
        CHECK(db.Execute("DELETE FROM Missions"));
        state = lua_newstate(LuaMemory::Allocate,&memory); CHECK(state); Seed(state);
        CHECK(Run(state,call) == 0); Print(state,"empty");
        lua_close(state); CHECK(memory.blocks == 0);
        Fill(db); state = lua_newstate(LuaMemory::Allocate,&memory); CHECK(state); Seed(state);
        call.count = nullptr; CHECK(Run(state,call) == 0); Print(state,"no-count");
        lua_close(state); CHECK(memory.blocks == 0);
    }
    db.Close(); GC.db = nullptr;
}
static void SQLFailures() {
    Database::Connection db; Open(db); Fill(db);
    CHECK(db.Execute("CREATE VIEW BrokenStep AS SELECT ID, CASE WHEN ID=7 THEN abs(-9223372036854775808) ELSE Type END AS Type FROM Missions"));
    const char* tables[] = {"Missing", "Missions", "BrokenStep", "(SELECT 5 AS ID, 'COUNT_FAILURE' AS Type)"};
    for (unsigned i=0;i<4;++i) {
        LuaMemory memory; auto* state = lua_newstate(LuaMemory::Allocate,&memory); CHECK(state); Seed(state);
        const auto before = Table(state); Call call{&memory}; call.table = tables[i];
        if (i == 1) call.id = "MissingColumn";
        const int status = Run(state,call);
#ifdef LUA_ENUM_ORIGINAL
        CHECK(status == 0 && call.returned);
        std::printf("ORIGINAL_SQL_FAILURE_IGNORED|%u\n",i);
#else
        CHECK(status != 0 && call.cppFailed && !call.returned);
        CHECK(Table(state) == before);
        std::printf("CANDIDATE_SQL_FAILURE_PROPAGATED|%u|%s\n",i,call.error);
#endif
        CHECK(db.StatementCount() == 0);
        call.table = "Missions"; call.id = "ID"; call.returned = false;
        CHECK(Run(state,call) == 0 && call.returned);
        lua_close(state); CHECK(memory.blocks == 0);
    }
}
static void Unwind(const char* mode) {
    // Observe real provider statements; do not assume C longjmp skips MSVC x64
    // destructors. If a future configuration leaks, exit before touching the
    // potentially escaped command registry pointer.
    auto* db = new Database::Connection; Open(*db);
    const bool nullName = std::strcmp(mode,"unwind-null") == 0;
    CHECK(db->Execute(nullName ? "INSERT INTO Missions VALUES(0,NULL)" : "INSERT INTO Missions VALUES(0,'UNINTERNED_NAME_TO_ALLOCATE')"));
    LuaMemory memory; auto* state = lua_newstate(LuaMemory::Allocate,&memory); CHECK(state); Seed(state);
    Call call{&memory}; if (!nullName) call.luaBudget = 0;
    CHECK(Run(state,call) != 0 && !call.returned);
#ifdef LUA_ENUM_ORIGINAL
    std::printf("ORIGINAL_X64_UNWIND|%s|statements=%d|cpp_failed=%d\n",mode,db->StatementCount(),call.cppFailed);
    if(db->StatementCount()!=0) { std::fflush(stdout); std::_Exit(3); }
#else
    CHECK(db->StatementCount() == 0);
    if (nullName) CHECK(call.cppFailed);
    std::printf("CANDIDATE_QUERY_CLEANED|%s|statements=0\n",mode);
#endif
    lua_close(state); CHECK(memory.blocks == 0); delete db; GC.db = nullptr;
}
static void OriginalLuaFaults() {
    Database::Connection db; Open(db);
    for(int i=0;i<40;++i) {
        const auto sql="INSERT INTO Missions VALUES("+std::to_string(i)+",'LONG_MISSION_NAME_FOR_ALLOCATION_"+std::to_string(i)+"')";
        CHECK(db.Execute(sql.c_str()));
    }
    unsigned failed=0; bool succeeded=false;
    for(int point=0;point<1024;++point) {
        LuaMemory memory;auto* state=lua_newstate(LuaMemory::Allocate,&memory);CHECK(state);Seed(state);
        Call call{&memory};call.luaBudget=point;
        const int status=Run(state,call);
        if(db.StatementCount()!=0) { std::printf("X64_UNWIND_FAILURE|point=%d|statements=%d\n",point,db.StatementCount());std::fflush(stdout);std::_Exit(3); }
        if(status){++failed;Call retry{&memory};CHECK(Run(state,retry)==0);}else succeeded=true;
        CHECK(db.StatementCount()==0);lua_close(state);CHECK(memory.blocks==0);
        if(succeeded)break;
    }
    CHECK(succeeded && failed>10);
    std::printf("ORIGINAL_X64_LUA_FAILURES|%u|statements_restored_and_retry_passed\n",failed);
}
#ifndef LUA_ENUM_ORIGINAL
static void Faults() {
    Database::Connection db; Open(db);
    for (int i=0;i<40;++i) {
        const auto query = "INSERT INTO Missions VALUES(" + std::to_string(i) + ",'LONG_MISSION_NAME_FOR_ALLOCATION_" + std::to_string(i) + "')";
        CHECK(db.Execute(query.c_str()));
    }
    for (unsigned kind=0;kind<2;++kind) {
        unsigned failed = 0; bool succeeded = false;
        for (int point=0;point<1024;++point) {
            LuaMemory memory; auto* state = lua_newstate(LuaMemory::Allocate,&memory); CHECK(state); Seed(state);
            Call call{&memory}; if (kind == 0) call.luaBudget = point; else call.allocationBudget = point;
            const auto live = heapLive;
            const int status = Run(state,call);
            CHECK(heapLive == live && db.StatementCount() == 0);
            if (status) {
                ++failed; Call retry{&memory}; CHECK(Run(state,retry) == 0);
            } else { CHECK(call.returned); succeeded = true; }
            lua_getglobal(state,"EnumTarget"); lua_getfield(state,-1,"NUM_MISSION_TYPES");
            CHECK(lua_tointeger(state,-1) == 40); lua_pop(state,2);
            lua_close(state); CHECK(memory.blocks == 0);
            if (succeeded) break;
        }
        CHECK(succeeded && failed > 10);
        std::printf("ALLOCATION_FAILURES|%s|%u\n",kind ? "cpp" : "lua",failed);
    }
    for (unsigned i=0;i<8;++i) {
        LuaMemory memory; auto* state = lua_newstate(LuaMemory::Allocate,&memory); CHECK(state); Seed(state);
        Call call{&memory};
        if(i==0) GC.db=nullptr;
        if(i==1) call.table=nullptr;
        if(i==2) call.id=nullptr;
        if(i==3) call.name=nullptr;
        if(i==4) call.table="";
        if(i==5) call.id="";
        if(i==6) call.name="";
        if(i==7) call.nilDestination=true;
        CHECK(Run(state,call) != 0 && call.cppFailed); GC.db=&db;
        CHECK(db.StatementCount()==0); lua_close(state); CHECK(memory.blocks==0);
    }
    // Long query fields were formerly limited by an unchecked 255-byte buffer.
    const auto longName=std::string("T")+std::string(300,'q');
    CHECK(db.Execute(("CREATE TABLE "+longName+"(ID INTEGER,Type TEXT)").c_str()));
    CHECK(db.Execute(("INSERT INTO "+longName+" VALUES(3,'LONG_TABLE_OK')").c_str()));
    LuaMemory memory; auto* state=lua_newstate(LuaMemory::Allocate,&memory); CHECK(state); Seed(state);
    Call call{&memory}; call.table=longName.c_str(); CHECK(Run(state,call)==0);
    db.Close(); call.table="Missions"; CHECK(Run(state,call)!=0 && call.cppFailed);
    lua_close(state); CHECK(memory.blocks==0); GC.db=nullptr;
    std::puts("INPUT_FAILURES|8_invalid_arguments|closed_database|long_identifier_success");
}
#endif
static void Wrapper() {
    Database::Connection db; Open(db); Fill(db); FLua::SetErrorHandler(CaptureError);
    for (unsigned i=0;i<2;++i) {
        LuaMemory memory; auto* state=lua_newstate(LuaMemory::Allocate,&memory); CHECK(state); Seed(state);
        activeMemory=&memory; wrapperTable=i ? "Missions" : "Missing"; wrapperBudget=i ? 0 : -1;
        const auto errors=wrapperErrors; bool failed=false;
        try { CvLuaEnums::Register(state); } catch(const std::exception&) { failed=true; }
        memory.budget=-1; wrapperBudget=-1; activeMemory=nullptr;
#ifdef LUA_ENUM_ORIGINAL
        CHECK(!failed); CHECK(wrapperErrors==errors+(i ? 1 : 0));
        if (i) {
            CHECK(db.StatementCount()==0);
        }
#else
        CHECK(failed && wrapperErrors==errors+1 && db.StatementCount()==0);
        CHECK(lua_gettop(state)==1 && lua_tointeger(state,1)==773);
        CHECK(FLua::ms_CriticalSection.GetRecursionCount()==0);
        wrapperTable="Missions"; CvLuaEnums::Register(state);
#endif
        lua_close(state); CHECK(memory.blocks==0);
    }
#ifdef LUA_ENUM_ORIGINAL
    std::puts("ORIGINAL_REGISTER_IGNORED|query_and_lua_failure");
#else
    std::puts("CANDIDATE_REGISTER_PROPAGATED|query_and_lua_failure|retry_passed");
#endif
}
int main(int argc,char** argv) {
    if(argc<2) return 1;
    if(!std::strcmp(argv[1],"normal")) Normal(nullptr);
    else if(!std::strcmp(argv[1],"corpus") && argc==3) Normal(argv[2]);
    else if(!std::strcmp(argv[1],"sql-failures")) SQLFailures();
    else if(!std::strcmp(argv[1],"unwind-lua") || !std::strcmp(argv[1],"unwind-null")) Unwind(argv[1]);
    else if(!std::strcmp(argv[1],"original-lua-faults")) OriginalLuaFaults();
    else if(!std::strcmp(argv[1],"wrapper")) Wrapper();
#ifndef LUA_ENUM_ORIGINAL
    else if(!std::strcmp(argv[1],"faults")) Faults();
#endif
    else return 1;
    std::printf("PASS|%u\n",checks); return 0;
}
