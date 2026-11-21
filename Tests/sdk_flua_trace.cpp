#include "SdkFLuaIncludes.h"
static unsigned checks = 0;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"FAIL|%u|%d|%s\n",checks,__LINE__,#x); std::exit(2); } } while (0)
static std::vector<std::string> errors;
static void CaptureError(const TCHAR* message) { errors.push_back(message); }
static int Noop(lua_State*) { return 0; }
static int finalized = 0;
static int Finalize(lua_State*) { ++finalized; return 0; }
static int Upvalue(lua_State* state) {
    FLua::Value value(state,lua_upvalueindex(1)), environment(state,LUA_ENVIRONINDEX);
    CHECK(value.GetAs<int>()==58 && environment.GetType()==FLua::TYPE_TABLE);
    CHECK(lua_gettop(state)==0); return 0;
}
static void Emit(const char* name, const FLua::Value& value) {
    lua_State* state = value.GetLuaState();
    const int before = state ? lua_gettop(state) : 0;
    std::printf("VALUE|%s|%d|%d|%s|%d|",name,value.Valid(),value.GetType(),value.GetTypeName(),value.IsNil());
    if (value.Push()) {
        const int type = lua_type(state,-1);
        if (type == LUA_TSTRING) {
            size_t length = 0; const char* bytes = lua_tolstring(state,-1,&length);
            for (size_t i=0;i<length;++i) std::printf("%02x",static_cast<unsigned char>(bytes[i]));
        } else if (type == LUA_TNUMBER) std::printf("%.17g",lua_tonumber(state,-1));
        else if (type == LUA_TBOOLEAN) std::printf("%d",lua_toboolean(state,-1));
        else std::printf("type%d",type);
        lua_pop(state,1);
    } else std::printf("absent");
    std::printf("\n"); CHECK(!state || lua_gettop(state)==before);
}
static void Values(lua_State* state) {
    std::printf("REGISTRY_SHARED|%d\n",FLua::SharedLuaRegistry::Get());
    FLua::Value empty; Emit("empty",empty); CHECK(!empty.Valid() && empty.GetRef()==LUA_NOREF);
    lua_pushnil(state); lua_pushboolean(state,0); lua_pushboolean(state,1);
    lua_pushnumber(state,-2147483648.0); lua_pushnumber(state,4294967295.0);
    lua_pushnumber(state,1.0/8); lua_pushlstring(state,"a\0b",3); lua_pushstring(state,"\xed\x95\x9c\xea\xb8\x80");
    lua_newtable(state); lua_pushcfunction(state,Noop); lua_newuserdata(state,8);
    lua_pushlightuserdata(state,&checks); lua_newthread(state);
    const int count=lua_gettop(state);
    for (int i=1;i<=count;++i) {
        FLua::Value a(state,i), b(state,i-count-1), copy(a), assigned;
        CHECK(a.Valid() && b.Valid()); CHECK(a==b); CHECK(copy==a);
        assigned=a; CHECK(assigned==a); CHECK(lua_gettop(state)==count);
        char label[32]; sprintf_s(label,"item%d",i); Emit(label,a);
        a.Clear(); a.Clear(); CHECK(!a.Valid() && !a.GetLuaState()); CHECK(copy==b && assigned==b);
        FLua::Table table(copy); CHECK(table.Valid()==(i==9));
        const bool pushed=table.Push(); CHECK(pushed==(i==9)); if(pushed)lua_pop(state,1);
        CHECK(lua_gettop(state)==count);
        if(i==1)CHECK(copy.GetRef()==LUA_REFNIL && copy.IsNil());
    }
    {
        FLua::Value globals(state,LUA_GLOBALSINDEX), registry(state,LUA_REGISTRYINDEX);
        CHECK(globals.GetType()==FLua::TYPE_TABLE && registry.GetType()==FLua::TYPE_TABLE);
        globals.Swap(registry); CHECK(globals.ToPointer()!=registry.ToPointer());
        FLua::Value replacement(state,1); replacement.Set(state,count); CHECK(replacement.GetType()==FLua::TYPE_THREAD);
    }
    lua_settop(state,0); lua_pushinteger(state,58); lua_pushcclosure(state,Upvalue,1);
    CHECK(lua_pcall(state,0,0,0)==0); std::printf("VALUES|%d|active_pseudo_indices\n",count);
}
static void Tables(lua_State* state) {
    FLua::SetErrorHandler(CaptureError); errors.clear();
    lua_newtable(state);
    {
        FLua::Table table(state,-1);
        for (int i=0;i<1024;++i) {
            table["MissionData"]=i-512; table["Visible"]=(i%2)==0;
            table["Type"]="\xed\x95\x9c\xea\xb8\x80"; table.SetField(i+1,i*7);
            CHECK(lua_gettop(state)==1);
            lua_getfield(state,1,"MissionData"); CHECK(lua_tointeger(state,-1)==i-512); lua_pop(state,1);
            lua_getfield(state,1,"Visible"); CHECK(lua_toboolean(state,-1)==((i%2)==0)); lua_pop(state,1);
            lua_rawgeti(state,1,i+1); CHECK(lua_tointeger(state,-1)==i*7); lua_pop(state,1);
        }
        lua_pushnil(state); FLua::Value nil(state,-1); lua_pop(state,1);
        table.SetField(nil,42); CHECK(errors.size()==1 && lua_gettop(state)==1);
        lua_State* other=luaL_newstate(); CHECK(other!=NULL);
        { lua_pushstring(other,"foreign"); FLua::Value key(other,-1); table.SetField(key,7); CHECK(errors.size()==2 && lua_gettop(other)==1); }
        lua_close(other); CHECK(lua_gettop(state)==1);
        for(size_t i=0;i<errors.size();++i)std::printf("ERROR|%s\n",errors[i].c_str());
        lua_newtable(state); lua_pushcfunction(state,Noop); lua_setfield(state,-2,"__newindex"); lua_setmetatable(state,1);
        table["raw_write"]=11; lua_getfield(state,1,"raw_write"); CHECK(lua_tointeger(state,-1)==11); lua_pop(state,1);
        table.SetField("metamethod_write",22); lua_getfield(state,1,"metamethod_write"); CHECK(lua_isnil(state,-1)); lua_pop(state,1);
    }
    lua_pop(state,1); std::printf("TABLES|1024|raw_and_metamethod\n");
}
static void Lifetime(lua_State* state) {
    finalized=0;
    {
        lua_newuserdata(state,16); lua_newtable(state); lua_pushcfunction(state,Finalize); lua_setfield(state,-2,"__gc"); lua_setmetatable(state,-2);
        FLua::Value a(state,-1), b(a); lua_pop(state,1);
        lua_gc(state,LUA_GCCOLLECT,0); CHECK(finalized==0);
        a.Clear(); lua_gc(state,LUA_GCCOLLECT,0); CHECK(finalized==0);
        b.Clear(); lua_gc(state,LUA_GCCOLLECT,0); CHECK(finalized==1);
    }
    lua_State* closing=luaL_newstate(); CHECK(closing!=NULL);
    lua_pushinteger(closing,21); FLua::Value a(closing,-1), b(a);
    lua_close(closing); a.LuaStateDestroyed(); b.LuaStateDestroyed();
    CHECK(!a.Valid() && !b.Valid() && !a.Push()); std::printf("LIFETIME|%d|detached\n",finalized);
}
static void SelfAssign(lua_State* state) {
    lua_pushinteger(state,17); FLua::Value value(state,-1); value=value;
    Emit("self",value); lua_pop(state,1);
}
static int CallReturn(lua_State* state) {
    int* data=static_cast<int*>(lua_touserdata(state,1));
    if(lua_gettop(state)!=1 || !data)return luaL_error(state,"bad callback argument");
    ++*data; lua_pushinteger(state,71); return 1;
}
static int CallFail(lua_State* state) { return luaL_error(state,"script failure %d",23); }
static int CallNested(lua_State* state) {
    void* data=lua_touserdata(state,1);
    if(!FLua::Details::CCallWithErrorHandling(state,CallReturn,data))return luaL_error(state,"nested failure");
    return 0;
}
struct MemberError {
    std::string message;
    void Capture(const TCHAR* text) { message=text; }
};
static void Calls(lua_State* state) {
    errors.clear(); FLua::SetErrorHandler(CaptureError); int count=0;
    lua_pushinteger(state,77);
    CHECK(FLua::Details::CCallWithErrorHandling(state,CallReturn,&count));
    CHECK(count==1 && lua_gettop(state)==1 && lua_tointeger(state,1)==77);
    CHECK(FLua::Details::CCallWithErrorHandling(state,CallNested,&count)); CHECK(count==2);
    CHECK(!FLua::Details::CCallWithErrorHandling(state,CallFail,NULL));
    CHECK(lua_gettop(state)==1 && errors.size()==1); std::printf("CALL_ERROR|%s\n",errors[0].c_str());
    CHECK(FLua::Details::CCallWithErrorHandling(state,CallReturn,&count)); CHECK(count==3);
    MemberError member; FLua::SetErrorHandler(FLua::ErrorHandler(&member,&MemberError::Capture));
    FLua::Details::Error("member:%d:%s",5,"ok"); CHECK(member.message=="member:5:ok");
    FLua::SetErrorHandler(CaptureError); lua_pop(state,1);
    std::printf("CALLS|%d|stack_and_reentry|member_handler\n",count);
}
struct Worker { lua_State* state; HANDLE ready; HANDLE start; unsigned count; LONG failed; };
static int Increment(lua_State* state) {
    lua_getglobal(state,"counter"); const lua_Integer counter=lua_tointeger(state,-1); lua_pop(state,1);
    SwitchToThread(); lua_pushinteger(state,counter+1); lua_setglobal(state,"counter"); return 0;
}
static unsigned __stdcall RunWorker(void* opaque) {
    Worker* worker=static_cast<Worker*>(opaque); SetEvent(worker->ready); WaitForSingleObject(worker->start,INFINITE);
    for(unsigned i=0;i<worker->count;++i)
        if(!FLua::Details::CCallWithErrorHandling(worker->state,Increment,NULL))InterlockedIncrement(&worker->failed);
    return 0;
}
static void Concurrent(lua_State* state) {
    for(unsigned n=1;n<=8;n*=2) {
        lua_pushinteger(state,0); lua_setglobal(state,"counter");
        HANDLE start=CreateEvent(NULL,TRUE,FALSE,NULL); CHECK(start!=NULL);
        Worker workers[8]; HANDLE threads[8]; HANDLE ready[8];
        for(unsigned i=0;i<n;++i) {
            ready[i]=CreateEvent(NULL,TRUE,FALSE,NULL); CHECK(ready[i]!=NULL);
            workers[i].state=state; workers[i].ready=ready[i]; workers[i].start=start; workers[i].count=512; workers[i].failed=0;
            threads[i]=reinterpret_cast<HANDLE>(_beginthreadex(NULL,0,RunWorker,&workers[i],0,NULL)); CHECK(threads[i]!=NULL);
        }
        CHECK(WaitForMultipleObjects(n,ready,TRUE,30000)==WAIT_OBJECT_0); SetEvent(start);
        CHECK(WaitForMultipleObjects(n,threads,TRUE,30000)==WAIT_OBJECT_0);
        for(unsigned i=0;i<n;++i) { CHECK(workers[i].failed==0); CloseHandle(threads[i]); CloseHandle(ready[i]); }
        CloseHandle(start); lua_getglobal(state,"counter"); CHECK(lua_tointeger(state,-1)==static_cast<lua_Integer>(n*512)); lua_pop(state,1);
        CHECK(lua_gettop(state)==0); std::printf("LOCKED_CALLS|%u|%u\n",n,n*512);
    }
}
#ifdef FLUA_CANDIDATE
static int destroyed=0;
struct CallbackOwner { ~CallbackOwner() { ++destroyed; } };
static int ThrowCpp(lua_State*) { CallbackOwner owner; throw std::runtime_error("native callback failure"); }
static void ThrowHandler(const TCHAR*) { throw std::runtime_error("error handler failure"); }
static int NonString(lua_State* state) { lua_newtable(state); return lua_error(state); }
struct AllocFault { int remaining; unsigned fired; };
static void* FaultAllocator(void* data,void* pointer,size_t,size_t size) {
    AllocFault* fault=static_cast<AllocFault*>(data);
    if(!size) { free(pointer); return NULL; }
    if(fault->remaining>=0 && fault->remaining--==0) { ++fault->fired; fault->remaining=-1; return NULL; }
    return realloc(pointer,size);
}
#endif
static void Harden(lua_State* state) {
#ifdef FLUA_CANDIDATE
    lua_pushinteger(state,41); FLua::Value value(state,-1);
    const int invalid[]={0,2,INT_MAX,-2,INT_MIN,LUA_ENVIRONINDEX,lua_upvalueindex(1)};
    unsigned rejected=0;
    for(unsigned i=0;i<sizeof(invalid)/sizeof(invalid[0]);++i) {
        try { value.Set(state,invalid[i]); } catch(const std::out_of_range&) { ++rejected; }
        CHECK(value.GetAs<int>()==41 && lua_gettop(state)==1);
    }
    try { value.Set(NULL,1); } catch(const std::invalid_argument&) { ++rejected; }
    CHECK(rejected==8 && value.GetAs<int>()==41);
    value=value; CHECK(value.GetAs<int>()==41);
    const std::string large(16384,'q'); errors.clear(); FLua::SetErrorHandler(CaptureError);
    FLua::Details::Error("long:%s:%d",large.c_str(),27);
    CHECK(errors.size()==1 && errors[0]==std::string("long:")+large+":27");
    lua_pop(state,1); std::printf("HARDEN|%u|long_error_16384|self_preserved\n",rejected);
    lua_pushinteger(state,91); errors.clear(); destroyed=0;
    CHECK(!FLua::Details::CCallWithErrorHandling(state,ThrowCpp,NULL));
    CHECK(destroyed==1 && errors.size()==1 && errors[0]=="Runtime Error: native callback failure");
    CHECK(lua_gettop(state)==1 && lua_tointeger(state,1)==91);
    FLua::SetErrorHandler(ThrowHandler); bool thrown=false;
    try { FLua::Details::CCallWithErrorHandling(state,CallFail,NULL); } catch(const std::runtime_error&) { thrown=true; }
    CHECK(thrown && lua_gettop(state)==1 && FLua::ms_CriticalSection.GetRecursionCount()==0);
    FLua::SetErrorHandler(CaptureError); errors.clear();
    CHECK(!FLua::Details::CCallWithErrorHandling(state,NonString,NULL));
    CHECK(errors.size()==1 && errors[0]=="Runtime Error: (non-string Lua error)");
    int count=0; CHECK(FLua::Details::CCallWithErrorHandling(state,CallReturn,&count) && count==1);
    lua_pop(state,1);
    AllocFault fault={-1,0}; lua_State* limited=lua_newstate(FaultAllocator,&fault); CHECK(limited!=NULL);
    fault.remaining=0; errors.clear();
    CHECK(!FLua::Details::CCallWithErrorHandling(limited,CallReturn,&count));
    CHECK(fault.fired==1 && lua_gettop(limited)==0 && errors.size()==1 && errors[0].find("Memory Allocation Error: ")==0);
    CHECK(FLua::Details::CCallWithErrorHandling(limited,CallReturn,&count));
    CHECK(lua_gettop(limited)==0 && FLua::ms_CriticalSection.GetRecursionCount()==0); lua_close(limited);
    std::printf("CALL_HARDEN|cpp_unwind|throwing_handler|non_string|allocation_failure_recovery\n");
#else
    (void)state;
#endif
}
int main(int argc,char** argv) {
    if(argc!=2)return 1;
    lua_State* state=luaL_newstate(); CHECK(state!=NULL);
    if(!std::strcmp(argv[1],"values"))Values(state);
    else if(!std::strcmp(argv[1],"tables"))Tables(state);
    else if(!std::strcmp(argv[1],"lifetime"))Lifetime(state);
    else if(!std::strcmp(argv[1],"self"))SelfAssign(state);
    else if(!std::strcmp(argv[1],"calls"))Calls(state);
    else if(!std::strcmp(argv[1],"concurrent"))Concurrent(state);
    else if(!std::strcmp(argv[1],"harden"))Harden(state);
    else return 1;
    CHECK(lua_gettop(state)==0); lua_close(state);
    std::printf("PASS|%u\n",checks); return 0;
}
