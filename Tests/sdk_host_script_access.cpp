#if SCRIPT_ACCESS_ORIGINAL
#include "../Source/HostScriptAccess/HostServices.h"
#else
#include "HostServices.h"
#endif
#include "host_script_utility_fixture.h"
#include "../Source/LuaBorrowed/ZeroSisLuaBorrowed.h"
#include <thread>
#include <future>
#include <cstdio>
#include <cstdlib>
using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool ok,const char* expression,int line){++checks;if(!ok){std::fprintf(stderr,"SCRIPT_ACCESS_FAILED line=%d %s\n",line,expression);std::exit(1);}}
#define CHECK(value) Check((value),#value,__LINE__)
static const char* methods[]={"LoadFile","Execute","RegisterFunction","CallCFunction","CallFunction","CallHook","CallTestAll","CallTestAny","CallAccumulatorInt","CallAccumulatorFloat"};
static const char* conditions[]={"unlocked","worker_lock","wrong_owner","owner_query_exception","lock_query_exception","lock_query_unknown"};
static unsigned touches=0,unlockedTouches=0,finalizers=0;
static EngineServices* activeEngine=nullptr;
static int Touch(lua_State* state){
    ++touches;if(!activeEngine->HasGameCoreLock() || !activeEngine->IsGameCoreThread())++unlockedTouches;
    lua_pushinteger(state,7);return 1;
}
class EngineView final : public EngineServicesBase {
public:
    explicit EngineView(EngineServices& engine):engine_(engine){}
    int fault=0;
    bool IsGameCoreThread() override{
        if(fault==2)return false;
        if(fault==3)throw std::runtime_error("owner query failure");
        return engine_.IsGameCoreThread();
    }
    bool HasGameCoreLock() override{
        if(fault==4)throw std::runtime_error("lock query failure");
        if(fault==5)throw 51;
        return engine_.HasGameCoreLock();
    }
private:EngineServices& engine_;
};
static bool Execute(ScriptSystem& scripts,lua_State* state,const char* code){return scripts.Execute(state,code,std::strlen(code));}
static bool Operation(unsigned method,ScriptSystem& scripts,lua_State* state){
    switch(method){
    case 0:return scripts.LoadFile(state,"access");
    case 1:return Execute(scripts,state,"Touch()");
    case 2:return scripts.RegisterFunction(state,"NewFunction",Touch);
    case 3:return scripts.CallCFunction(state,Touch,nullptr);
    case 4:return scripts.CallFunction(state,0,1);
    case 5:{bool value=false;const bool ok=scripts.CallHook("Access",nullptr,value);CHECK(ok?value:!value);return ok;}
    case 6:{bool value=false;const bool ok=scripts.CallTestAll("Access",nullptr,value);CHECK(ok?value:!value);return ok;}
    case 7:{bool value=false;const bool ok=scripts.CallTestAny("Access",nullptr,value);CHECK(ok?value:!value);return ok;}
    case 8:{int value=97;const bool ok=scripts.CallAccumulator("Access",nullptr,value);CHECK(value==(ok?7:97));return ok;}
    case 9:{float value=97;const bool ok=scripts.CallAccumulator("Access",nullptr,value);CHECK(value==(ok?7.0f:97.0f));return ok;}
    default:throw std::logic_error("Unknown script access operation");
    }
}
static void PrepareStack(lua_State* vm,unsigned method){lua_settop(vm,0);lua_pushinteger(vm,671);if(method==4)lua_getglobal(vm,"AccessFunction");}
static unsigned Matrix(){
    unsigned accepted=0;
    for(unsigned condition=0;condition<6;++condition)for(unsigned method=0;method<10;++method){
        auto scripts=std::make_shared<ScriptSystem>();auto state=std::make_shared<HostState>("C:\\fixture\\",nullptr,nullptr,scripts);
        EngineServices engine(state);EngineView view(engine);ScriptUtilityFixture library;activeEngine=&engine;
        library.registration=[](lua_State* vm){lua_pushcfunction(vm,Touch);lua_setglobal(vm,"Touch");};
        scripts->RegisterFile("access.lua","Touch()");lua_State* vm=nullptr;
        {GameCall game(*state);scripts->BindGameLibraries(&library,&view);vm=scripts->CreateLuaThread("access matrix");
            CHECK(Execute(*scripts,vm,"GameEvents.Access.Add(function() return Touch() end); function AccessFunction() return Touch() end"));
            PrepareStack(vm,method);
        }
        const unsigned before=touches,unlockedBefore=unlockedTouches;bool ok=false;
        if(condition==0)ok=Operation(method,*scripts,vm);
        else if(condition==1){
            std::promise<void> held,release;auto ready=held.get_future();auto wait=release.get_future();
            std::thread worker([&]{engine.GetGameCoreLock();held.set_value();wait.wait();engine.ReleaseGameCoreLock();});
            ready.get();ok=Operation(method,*scripts,vm);release.set_value();worker.join();
        }else{
            GameCall game(*state);view.fault=static_cast<int>(condition);ok=Operation(method,*scripts,vm);view.fault=0;
        }
        accepted+=ok?1u:0u;
        const unsigned callbacks=touches-before,unlocked=unlockedTouches-unlockedBefore;
#if SCRIPT_ACCESS_ORIGINAL
        CHECK(ok && callbacks==(method==2?0u:1u));
        CHECK(unlocked==((condition<2 && method!=2)?1u:0u));
#else
        CHECK(!ok && callbacks==0 && unlocked==0);
        CHECK(std::strstr(scripts->LastError(),"GameCore")!=nullptr);
#endif
        {GameCall game(*state);
            CHECK(lua_gettop(vm)==(method==4?2:1) && lua_tointeger(vm,1)==671);
            if(method==4)CHECK(ok?lua_tointeger(vm,2)==7:lua_isfunction(vm,2));
            lua_getglobal(vm,"NewFunction");CHECK((lua_isfunction(vm,-1)!=0)==(ok && method==2));lua_pop(vm,1);
            PrepareStack(vm,method);const unsigned retryBefore=touches;
            CHECK(Operation(method,*scripts,vm));CHECK(touches-retryBefore==(method==2?0u:1u));
            CHECK(scripts->IsQuiescent() && engine.HasGameCoreLock() && engine.IsGameCoreExecuting());
            CHECK(scripts->Close());
        }
        CHECK(!engine.HasGameCoreLock() && !engine.IsGameCoreExecuting() && library.destroys==0);
        std::printf("SCRIPT_ACCESS_CASE condition=%s method=%s accepted=%u callbacks=%u unlocked_callbacks=%u recovery=1\n",conditions[condition],methods[method],ok?1u:0u,callbacks,unlocked);
    }
    activeEngine=nullptr;return accepted;
}
#if !SCRIPT_ACCESS_ORIGINAL
struct Owner {int value=43;};
static ZeroSisLuaBorrowed::NativeReference<Owner>* borrowed=nullptr;
static int ReadBorrowed(lua_State* vm){CHECK(activeEngine->HasGameCoreLock() && activeEngine->IsGameCoreThread());lua_pushinteger(vm,(*borrowed)->value);return 1;}
static int ThrowNative(lua_State*){throw std::runtime_error("native callback failure");}
static int Finalize(lua_State*){CHECK(activeEngine->HasGameCoreLock() && activeEngine->IsGameCoreThread());++finalizers;return 0;}
static void LifecycleQueries(){
    for(int fault=2;fault<=5;++fault){
        auto scripts=std::make_shared<ScriptSystem>();auto state=std::make_shared<HostState>("C:\\fixture\\",nullptr,nullptr,scripts);
        EngineServices engine(state);EngineView view(engine);ScriptUtilityFixture library;GameCall game(*state);
        scripts->BindGameLibraries(&library,&view);auto* vm=scripts->CreateLuaThread("lifecycle queries");view.fault=fault;
        bool failed=false;try{scripts->CreateLuaThread("invalid access");}catch(const std::logic_error&){failed=true;}
        CHECK(failed);scripts->FreeLuaThread(vm);CHECK(scripts->ThreadCount()==1);
        CHECK(!scripts->Close() && scripts->GameLibrariesBound() && !scripts->IsClosed());
        CHECK(scripts->IsQuiescent() && engine.HasGameCoreLock());view.fault=0;CHECK(scripts->Close());
    }
    std::puts("SCRIPT_ACCESS_LIFECYCLE_QUERIES_PASS REJECTED=12 RETRY_CLOSED=4");
}
static void RecoveryAndOwnership(){
    auto scripts=std::make_shared<ScriptSystem>();auto state=std::make_shared<HostState>("C:\\fixture\\",nullptr,nullptr,scripts);
    EngineServices engine(state);ScriptUtilityFixture library;activeEngine=&engine;lua_State* vm=nullptr;
    Owner owner;ZeroSisLuaBorrowed::NativeReference<Owner> reference(&owner);borrowed=&reference;
    {GameCall game(*state);scripts->BindGameLibraries(&library,&engine);vm=scripts->CreateLuaThread("recovery");
        CHECK(scripts->RegisterFunction(vm,"ReadBorrowed",ReadBorrowed));CHECK(scripts->RegisterFunction(vm,"ThrowNative",ThrowNative));
        CHECK(scripts->RegisterFunction(vm,"Touch",Touch));
        scripts->RegisterFile("access.lua","Touch()");
        CHECK(Execute(*scripts,vm,"GameEvents.Access.Add(function() return Touch() end); function AccessFunction() return Touch() end"));
        lua_pushinteger(vm,991);CHECK(Execute(*scripts,vm,"assert(ReadBorrowed()==43)"));
        ZeroSisLuaBorrowed::Invalidate(&owner);
        CHECK(!Execute(*scripts,vm,"ReadBorrowed()") && std::strstr(scripts->LastError(),"no longer exists"));
        CHECK(lua_gettop(vm)==1 && lua_tointeger(vm,1)==991 && scripts->IsQuiescent());
        reference.Reset(&owner);CHECK(Execute(*scripts,vm,"assert(ReadBorrowed()==43)"));
        CHECK(!Execute(*scripts,vm,"ThrowNative()") && std::strstr(scripts->LastError(),"native callback failure"));
        CHECK(!Execute(*scripts,vm,"error('Lua callback failure')") && std::strstr(scripts->LastError(),"Lua callback failure"));
        CHECK(lua_gettop(vm)==1 && lua_tointeger(vm,1)==991 && engine.IsGameCoreExecuting());
        lua_newuserdata(vm,1);lua_newtable(vm);lua_pushcfunction(vm,Finalize);lua_setfield(vm,-2,"__gc");lua_setmetatable(vm,-2);lua_setglobal(vm,"kept_finalizer");
        // The owner keeps the lock while a foreign thread tries every execution API.
        PrepareStack(vm,4);const unsigned before=touches;unsigned denied=0;
        std::thread worker([&]{
            for(unsigned method=0;method<10;++method)if(!Operation(method,*scripts,vm))++denied;
            if(!scripts->Close())++denied;scripts->FreeLuaThread(vm);
            bool failed=false;try{scripts->CreateLuaThread("foreign");}catch(const std::exception&){failed=true;}if(failed)++denied;
        });worker.join();
        CHECK(denied==12 && scripts->ForeignCalls()==12 && touches==before);
        CHECK(lua_gettop(vm)==2 && lua_isfunction(vm,2) && scripts->ThreadCount()==1 && finalizers==0);
    }
    const unsigned before=touches;
    CHECK(!Execute(*scripts,vm,"ReadBorrowed()") && touches==before);
    bool failed=false;try{scripts->CreateLuaThread("unlocked");}catch(const std::exception&){failed=true;}CHECK(failed);
    scripts->FreeLuaThread(vm);CHECK(scripts->ThreadCount()==1 && !scripts->Close() && finalizers==0);
    {GameCall game(*state);PrepareStack(vm,4);CHECK(scripts->CallFunction(vm,0,1));CHECK(lua_tointeger(vm,-1)==7);
        CHECK(scripts->Close() && finalizers==1 && !scripts->GameLibrariesBound());}
    CHECK(!engine.HasGameCoreLock() && !engine.IsGameCoreExecuting());
    borrowed=nullptr;activeEngine=nullptr;
    std::puts("SCRIPT_ACCESS_RECOVERY_PASS STALE_NATIVE_REFERENCE=true FOREIGN_REJECTIONS=12 FINALIZER_LOCKED=true GAMECORE_LOADED=false");
}
#endif
int main(){
    const unsigned accepted=Matrix();
#if !SCRIPT_ACCESS_ORIGINAL
    LifecycleQueries();RecoveryAndOwnership();
#endif
    for(const wchar_t* name:{L"CvGameCoreDLL.dll",L"CvGameCoreDLL_Expansion1.dll",L"CvGameCoreDLL_Expansion2.dll",L"CvGameCoreDLL_Expansion2_x64.dll",L"CvGameCoreDLL_Expansion2_x64_probe.dll"})CHECK(GetModuleHandleW(name)==nullptr);
    std::printf("HOST_SCRIPT_ACCESS_PASS checks=%u original=%u cases=60 accepted=%u GAMECORE_LOADED=false\n",checks,SCRIPT_ACCESS_ORIGINAL,accepted);return 0;
}
