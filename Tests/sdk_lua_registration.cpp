#include "SdkFLuaIncludes.h"
#include "ZeroSisLuaFractalNumeric.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <vector>
#include <string>
#include <stdexcept>
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
static unsigned capturedErrors = 0, gameplayFixtureCalls = 0;
static int failingGetter = -1, failingPlayer = -1, failingTeam = -1;
static bool failingTypes = false;
static void CaptureError(const TCHAR*) { ++capturedErrors; }
namespace Lua = FLua::Details;
using FLua::Table;
// Only registration metadata executes. These owners do not represent live game objects.
struct CvMap {}; struct CvGame {}; struct CvPlayerAI { int id; }; struct CvTeam { int id; };
typedef int PlayerTypes; typedef int TeamTypes;
static CvPlayerAI players[64]; static CvTeam teams[64];
static CvPlayerAI& GET_PLAYER(PlayerTypes id) {
    if (id == failingPlayer) throw std::runtime_error("instrumented player access failed");
    CHECK(id >= 0 && id < 64); return players[id];
}
static CvTeam& GET_TEAM(TeamTypes id) {
    if (id == failingTeam) throw std::runtime_error("instrumented team access failed");
    CHECK(id >= 0 && id < 64); return teams[id];
}
struct CvActionInfo {
    int row;
    void Read(int field) const { if (row == 1 && field == failingGetter) throw std::runtime_error("instrumented action field failed"); }
#define INT_GETTER(name, field) int name() const { Read(field); return row * 101 + field - 9; }
#define BOOL_GETTER(name, field) bool name() const { Read(field); return (row + field) % 2 != 0; }
#define TEXT_GETTER(name, field, text) const char* name() const { Read(field); return text; }
    INT_GETTER(getMissionData,0) INT_GETTER(getCommandData,1) INT_GETTER(getAutomateType,2)
    INT_GETTER(getInterfaceModeType,3) INT_GETTER(getMissionType,4) INT_GETTER(getCommandType,5)
    INT_GETTER(getControlType,6) INT_GETTER(getOriginalIndex,7)
    BOOL_GETTER(isConfirmCommand,8) BOOL_GETTER(isVisible,9) INT_GETTER(getSubType,10)
    TEXT_GETTER(GetType,11,"FIXTURE_ACTION") TEXT_GETTER(GetTextKey,12,"TXT_KEY_FIXTURE")
    INT_GETTER(getActionInfoIndex,13) INT_GETTER(getHotKeyVal,14) INT_GETTER(getHotKeyPriority,15)
    INT_GETTER(getHotKeyValAlt,16) INT_GETTER(getHotKeyPriorityAlt,17) INT_GETTER(getOrderPriority,18)
    BOOL_GETTER(isAltDown,19) BOOL_GETTER(isShiftDown,20) BOOL_GETTER(isCtrlDown,21)
    BOOL_GETTER(isAltDownAlt,22) BOOL_GETTER(isShiftDownAlt,23) BOOL_GETTER(isCtrlDownAlt,24)
    TEXT_GETTER(getHotKeyString,25,"Ctrl+A") TEXT_GETTER(GetHelp,26,"한글 도움말")
    TEXT_GETTER(GetDisabledHelp,27,"")
#undef INT_GETTER
#undef BOOL_GETTER
#undef TEXT_GETTER
};
struct CvGlobals {
    typedef std::map<std::string,int> InfosMap;
    std::vector<CvActionInfo*> actions;
    InfosMap types;
    std::vector<CvActionInfo*>& getActionInfo() { return actions; }
    const InfosMap& GetInfoTypes() {
        if (failingTypes) throw std::runtime_error("instrumented type access failed");
        return types;
    }
};
static CvGlobals GC;
static CvActionInfo actions[] = {{0},{1},{2}};
class CvLuaEnums { public: static void Register(lua_State* L) {
    // Sequence sentinel only; the real enum registration is tested separately.
    lua_newtable(L); lua_setglobal(L,"EnumSequenceSentinel");
} };
struct LuaSupport { static void RegisterScriptData(lua_State*); };
struct MethodSpec { const char* name; lua_CFunction function; };
#include "lua_registration_fixture.h"

typedef void (*Registrar)(lua_State*);
static const Registrar registrars[] = {CvLuaFractal::Register,CvLuaGameInfo::Register,CvLuaMap::Register,
    CvLuaGame::Register,CvLuaPlayer::Register,CvLuaTeam::Register};
static const char* const libraryNames[] = {"Fractal","GameInfo","Map","Game","Player","Team"};
static const char* const globalNames[] = {"Fractal","GameInfoActions","Map","Game","Players","Teams"};
static lua_State* Open(LuaMemory& memory) {
    auto* L = lua_newstate(LuaMemory::Allocate,&memory); CHECK(L);
    lua_pushinteger(L,773); return L;
}
static bool Invoke(lua_State* L,Registrar registrar) {
    bool failed = false;
    try { registrar(L); } catch (const std::exception&) { failed = true; }
    CHECK(lua_gettop(L) == 1 && lua_tointeger(L,1) == 773);
    CHECK(FLua::ms_CriticalSection.GetRecursionCount() == 0);
    return failed;
}
static bool Exists(lua_State* L,const char* name) {
    lua_getglobal(L,name); const bool value = !lua_isnil(L,-1); lua_pop(L,1); return value;
}
static void BadGlobal(lua_State* L,const char* name) { lua_pushinteger(L,9); lua_setglobal(L,name); }
static void SeedExisting(lua_State* L,const char* name) {
    lua_newtable(L); lua_pushinteger(L,919); lua_setfield(L,-2,"KeepExisting"); lua_setglobal(L,name);
}
static const void* Identity(lua_State* L,const char* name) {
    lua_getglobal(L,name); const void* value = lua_topointer(L,-1); lua_pop(L,1); return value;
}
static void Methods(lua_State* L,const char* name,const MethodSpec* methods,std::size_t count,bool print) {
    lua_getglobal(L,name); CHECK(lua_istable(L,-1));
    unsigned functions = 0; lua_pushnil(L);
    while (lua_next(L,-2)) { if (lua_iscfunction(L,-1)) ++functions; lua_pop(L,1); }
    CHECK(functions == count);
    for (std::size_t i=0;i<count;++i) {
        lua_getfield(L,-1,methods[i].name);
        CHECK(lua_iscfunction(L,-1) && lua_tocfunction(L,-1) == methods[i].function);
        lua_pop(L,1);
        if (print) std::printf("METHOD|%s|%s\n",name,methods[i].name);
    }
    lua_pop(L,1);
}
static const char* const actionNames[] = {"MissionData","CommandData","AutomateType","InterfaceModeType",
    "MissionType","CommandType","ControlType","OriginalIndex","ConfirmCommand","Visible","SubType","Type","TextKey",
    "ActionInfoIndex","HotKeyVal","HotKeyPriority","HotKeyValAlt","HotKeyPriorityAlt","OrderPriority",
    "AltDown","ShiftDown","CtrlDown","AltDownAlt","ShiftDownAlt","CtrlDownAlt","HotKey","Help","DisabledHelp"};
static void GameInfo(lua_State* L,bool print) {
    lua_getglobal(L,"GameInfoActions"); CHECK(lua_istable(L,-1));
    unsigned rows = 0; lua_pushnil(L);
    while (lua_next(L,-2)) { ++rows; lua_pop(L,1); } CHECK(rows == 3);
    for (int row=0;row<3;++row) {
        lua_rawgeti(L,-1,row); CHECK(lua_istable(L,-1));
        unsigned fields = 0; lua_pushnil(L); while (lua_next(L,-2)) { ++fields; lua_pop(L,1); }
        CHECK(fields == 28);
        for (int field=0;field<28;++field) {
            lua_getfield(L,-1,actionNames[field]);
            const char* text = field==11 ? "FIXTURE_ACTION" : field==12 ? "TXT_KEY_FIXTURE" : field==25 ? "Ctrl+A" : field==26 ? "한글 도움말" : field==27 ? "" : nullptr;
            if (text) {
                CHECK(lua_type(L,-1)==LUA_TSTRING && std::strcmp(lua_tostring(L,-1),text)==0);
                if (print) std::printf("ACTION|%d|%s|s:%s\n",row,actionNames[field],text);
            } else if (field==8 || field==9 || (field>=19 && field<=24)) {
                const bool value = (row+field)%2 != 0;
                CHECK(lua_type(L,-1)==LUA_TBOOLEAN && (lua_toboolean(L,-1)!=0)==value);
                if (print) std::printf("ACTION|%d|%s|b:%d\n",row,actionNames[field],value ? 1 : 0);
            } else {
                CHECK(lua_type(L,-1)==LUA_TNUMBER && lua_tointeger(L,-1)==row*101+field-9);
                if (print) std::printf("ACTION|%d|%s|n:%d\n",row,actionNames[field],row*101+field-9);
            }
            lua_pop(L,1);
        }
        lua_pop(L,1);
    }
    lua_pop(L,1); lua_getglobal(L,"GameInfoTypes"); CHECK(lua_istable(L,-1));
    for (const auto& value:GC.types) {
        lua_getfield(L,-1,value.first.c_str()); CHECK(lua_type(L,-1)==LUA_TNUMBER && lua_tointeger(L,-1)==value.second);
        lua_pop(L,1); if (print) std::printf("TYPE|%s|%d\n",value.first.c_str(),value.second);
    }
    lua_pop(L,1);
}
static void Instances(lua_State* L,bool player,const void** identities,bool verifyPrior) {
    static_assert(MAX_PLAYERS==64 && MAX_TEAMS==64,"SDK owner count changed");
    lua_getglobal(L,player ? "Players" : "Teams"); CHECK(lua_istable(L,-1));
    for (int i=0;i<64;++i) {
        lua_rawgeti(L,-1,i); CHECK(lua_istable(L,-1));
        if (verifyPrior) CHECK(lua_topointer(L,-1)==identities[i]); else identities[i]=lua_topointer(L,-1);
        lua_getfield(L,-1,"__instance");
        CHECK(lua_type(L,-1)==LUA_TLIGHTUSERDATA && lua_touserdata(L,-1)==(player ? static_cast<void*>(&players[i]) : static_cast<void*>(&teams[i])));
        lua_pop(L,1); CHECK(lua_getmetatable(L,-1)); lua_getfield(L,-1,"__index");
        lua_getglobal(L,player ? "Player" : "Team"); CHECK(lua_rawequal(L,-1,-2)); lua_pop(L,4);
    }
    lua_pop(L,1);
    lua_getglobal(L,player ? "Player" : "Team"); lua_getfield(L,-1,"__instances");
    CHECK(lua_istable(L,-1) && lua_getmetatable(L,-1)); lua_getfield(L,-1,"__mode");
    CHECK(lua_type(L,-1)==LUA_TSTRING && std::strcmp(lua_tostring(L,-1),"v")==0); lua_pop(L,4);
}
static void Validate(lua_State* L,int kind,bool print) {
    switch (kind) {
    case 0: Methods(L,"Fractal",FractalMethods,_countof(FractalMethods),print); break;
    case 1: GameInfo(L,print); break;
    case 2: Methods(L,"Map",MapMethods,_countof(MapMethods),print); break;
    case 3: Methods(L,"Game",GameMethods,_countof(GameMethods),print); break;
    case 4: Methods(L,"Player",PlayerMethods,_countof(PlayerMethods),print); break;
    case 5: Methods(L,"Team",TeamMethods,_countof(TeamMethods),print); break;
    }
    CHECK(lua_gettop(L)==1 && gameplayFixtureCalls==0);
}
static void Normal() {
    for (int kind=0;kind<6;++kind) {
        const auto heapBefore=heapLive; LuaMemory memory; auto* L=Open(memory);
        if (kind!=1) SeedExisting(L,globalNames[kind]);
        const auto identity=Identity(L,globalNames[kind]);
        CHECK(!Invoke(L,registrars[kind])); Validate(L,kind,true);
        const void* instances[64]={}; if (kind>=4) Instances(L,kind==4,instances,false);
        CHECK(!Invoke(L,registrars[kind])); Validate(L,kind,false);
        if (kind!=1) {
            CHECK(Identity(L,globalNames[kind])==identity);
            lua_getglobal(L,globalNames[kind]); lua_getfield(L,-1,"KeepExisting"); CHECK(lua_tointeger(L,-1)==919); lua_pop(L,2);
        }
        if (kind>=4) Instances(L,kind==4,instances,true);
        lua_close(L); CHECK(memory.blocks==0 && heapLive==heapBefore);
    }
    std::puts("NORMAL|six_registrars|preserved_methods_values_and_borrowed_identity|gameplay_calls=0");
}
static void ResetFailures() { failingGetter=-1; failingPlayer=-1; failingTeam=-1; failingTypes=false; cppBudget=-1; }
static void SequenceFailures() {
    const char* const nextGlobals[]={"GameInfoActions","GameInfoTypes","Map","Game","Players","Teams",nullptr};
    for (int failure=0;failure<7;++failure) {
        const auto heapBefore=heapLive; LuaMemory memory; auto* L=Open(memory);
        if (failure==0) BadGlobal(L,"Fractal");
        if (failure==1) failingGetter=10;
        if (failure==2) failingTypes=true;
        if (failure==3) BadGlobal(L,"Map");
        if (failure==4) BadGlobal(L,"Game");
        if (failure==5) failingPlayer=3;
        if (failure==6) failingTeam=3;
        const auto before=capturedErrors;
        const bool failed=Invoke(L,LuaSupport::RegisterScriptData);
        CHECK(capturedErrors==before+1 && Exists(L,"EnumSequenceSentinel"));
#ifdef LUA_REGISTRATION_ORIGINAL
        CHECK(!failed);
        if (nextGlobals[failure]) CHECK(Exists(L,nextGlobals[failure]));
        std::printf("ORIGINAL_IGNORED|%d|later_registration_continued\n",failure);
#else
        CHECK(failed);
        if (nextGlobals[failure]) CHECK(!Exists(L,nextGlobals[failure]));
        std::printf("CANDIDATE_STOPPED|%d|incomplete_vm_discarded\n",failure);
#endif
        ResetFailures(); lua_close(L); CHECK(memory.blocks==0 && heapLive==heapBefore);
        L=Open(memory); CHECK(!Invoke(L,LuaSupport::RegisterScriptData));
        for (int kind=0;kind<6;++kind) Validate(L,kind,false);
        lua_close(L); CHECK(memory.blocks==0 && heapLive==heapBefore);
    }
}
static void Faults(bool cpp) {
    for (int kind=0;kind<6;++kind) {
        unsigned failures=0,partial=0; bool completed=false;
        for (int budget=0;budget<8192;++budget) {
            const auto heapBefore=heapLive; LuaMemory memory; auto* L=Open(memory);
            const auto before=capturedErrors;
            if (cpp) cppBudget=budget; else memory.budget=budget;
            const bool failed=Invoke(L,registrars[kind]);
            cppBudget=-1; memory.budget=-1;
            const bool error=capturedErrors!=before;
#ifdef LUA_REGISTRATION_ORIGINAL
            CHECK(!failed);
#else
            CHECK(failed==error);
#endif
            if (error) {
                ++failures; if (Exists(L,globalNames[kind])) ++partial;
            } else { Validate(L,kind,false); completed=true; }
            lua_close(L); CHECK(memory.blocks==0 && heapLive==heapBefore);
            if (completed) break;
        }
        CHECK(completed && (cpp || failures>0));
        std::printf("FAULTS|%s|%s|%u|partial=%u|stack_lock_heap_restored\n",cpp ? "cpp" : "lua",libraryNames[kind],failures,partial);
        LuaMemory memory; auto* L=Open(memory); CHECK(!Invoke(L,registrars[kind])); Validate(L,kind,false);
        lua_close(L); CHECK(memory.blocks==0);
    }
}
static void FailureExceptionAllocation() {
    unsigned failedAllocations=0;
    for (int budget=0;budget<3;++budget) {
        const auto heapBefore=heapLive; LuaMemory memory; auto* L=Open(memory); BadGlobal(L,"Map");
        const auto before=capturedErrors; cppBudget=budget;
        const bool failed=Invoke(L,CvLuaMap::Register); cppBudget=-1;
        // FLua itself allocates its error message before calling the error handler.
        // Failure there already throws in the original, before its ignored bool return.
        if (budget==0) { CHECK(failed && capturedErrors==before); ++failedAllocations; }
        else {
            CHECK(capturedErrors==before+1);
#ifdef LUA_REGISTRATION_ORIGINAL
            CHECK(!failed);
#else
            CHECK(failed);
#endif
        }
        lua_close(L); CHECK(memory.blocks==0 && heapLive==heapBefore);
    }
    std::printf("ERROR_EXCEPTION_ALLOCATION|%u|error_formatting_allocation_failure|stack_lock_heap_restored\n",failedAllocations);
}
int main(int argc,char** argv) {
    if (argc!=2) return 1;
    for (auto& action:actions) GC.actions.push_back(&action);
    GC.types={{"FIXTURE_ZERO",0},{"FIXTURE_NEGATIVE",-1},{"FIXTURE_MAX",2147483647},{"한글_타입",73}};
    FLua::SetErrorHandler(CaptureError);
    if (!std::strcmp(argv[1],"normal")) Normal();
    else if (!std::strcmp(argv[1],"sequence")) SequenceFailures();
    else if (!std::strcmp(argv[1],"lua-faults")) Faults(false);
    else if (!std::strcmp(argv[1],"cpp-faults")) Faults(true);
    else if (!std::strcmp(argv[1],"exception-allocation")) FailureExceptionAllocation();
    else return 1;
    CHECK(gameplayFixtureCalls==0); std::printf("PASS|%u\n",checks); return 0;
}
