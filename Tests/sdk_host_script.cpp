// Actual frozen SDK ABI and actual Lua 5.1 x64 provider. No GameCore module.
#include "HostServices.h"
#include "ZeroSisHostBinding.h"
#include <thread>
#include <cstdlib>
#include <new>
using namespace ZeroSisHost;
static std::atomic<unsigned> checks{0};
static void Check(bool ok,const char* expression,int line){
    ++checks;if(!ok){std::fprintf(stderr,"SCRIPT_FAILED line=%d %s\n",line,expression);std::exit(1);}
}
#define CHECK(value) Check((value),#value,__LINE__)
static thread_local int allocationBudget=-1;
static std::atomic<long long> allocations{0};
void* operator new(std::size_t size){
    if(allocationBudget>=0 && allocationBudget--==0){allocationBudget=-1;throw std::bad_alloc();}
    void* p=std::malloc(size?size:1);if(!p)throw std::bad_alloc();++allocations;return p;
}
void operator delete(void* p) noexcept{if(p){--allocations;std::free(p);}}
void* operator new[](std::size_t size){return ::operator new(size);}
void operator delete[](void* p) noexcept{::operator delete(p);}
void operator delete(void* p,std::size_t) noexcept{::operator delete(p);}
void operator delete[](void* p,std::size_t) noexcept{::operator delete(p);}
template<class F> static void Reject(F operation){bool caught=false;try{operation();}catch(const std::exception&){caught=true;}CHECK(caught);}
static bool Execute(ScriptSystem& system,lua_State* state,const char* text){return system.Execute(state,text,std::strlen(text));}

struct LuaMemory {
    int budget=-1;std::size_t bytes=0,blocks=0,rejections=0;
    static void* Allocate(void* context,void* pointer,std::size_t oldSize,std::size_t newSize){
        auto& memory=*static_cast<LuaMemory*>(context);
        if(!newSize){if(pointer){memory.bytes-=oldSize;--memory.blocks;std::free(pointer);}return nullptr;}
        if(newSize>oldSize && memory.budget>=0){
            if(!memory.budget){++memory.rejections;return nullptr;}--memory.budget;
        }
        void* result=std::realloc(pointer,newSize);
        if(result){if(!pointer)++memory.blocks;memory.bytes=memory.bytes-oldSize+newSize;}return result;
    }
};
static void Arguments(){
    ScriptSystem system;auto* args=system.CreateArgs(8);CHECK(system.ArgumentCount()==1);
    CHECK(args->Push(true)==0);CHECK(args->Push(INT_MIN)==1);CHECK(args->Push(1.25f)==2);
    const char text[]={'A',0,'B'};CHECK(args->Push(text,3)==3);CHECK(args->PushNULL()==4);CHECK(args->Push(nullptr,0)==5);
    bool b=false;int n=0;float f=0;char* s=nullptr;
    CHECK(args->Count()==6 && args->GetBool(0,b) && b && args->GetInt(1,n) && n==INT_MIN);
    CHECK(args->GetFloat(2,f) && f==1.25f && args->GetString(3,s) && std::memcmp(s,text,3)==0 && s[3]==0);
    s[2]='C';CHECK(args->GetString(3,s) && s[2]=='C');
    CHECK(args->GetType(4)==ICvEngineScriptSystemArgs1::ARGTYPE_NULL && args->GetType(999)==ICvEngineScriptSystemArgs1::ARGTYPE_NONE);
    CHECK(!args->GetInt(0,n) && n==INT_MIN && !args->GetBool(99,b) && b && !args->GetFloat(4,f) && f==1.25f);
    char* previous=s;CHECK(!args->GetString(0,s) && s==previous);
    Reject([&]{args->Push(nullptr,1);});Reject([&]{args->Push(std::numeric_limits<float>::infinity());});
    CHECK(args->Count()==6);system.DestroyArgs(args);CHECK(system.ArgumentCount()==0);system.DestroyArgs(args);
    CHECK(system.Close() && system.IsClosed() && system.Close());Reject([&]{system.CreateArgs();});
}
struct NestedCall {ScriptSystem* system;lua_State* state;int result=0;};
static int Nested(lua_State* state){
    CHECK(lua_type(state,1)==LUA_TLIGHTUSERDATA);auto* call=static_cast<NestedCall*>(lua_touserdata(state,1));CHECK(state==call->state);
    lua_getglobal(state,"calculate");lua_pushinteger(state,6);lua_pushinteger(state,7);
    CHECK(call->system->CallFunction(state,2,2));CHECK(lua_tointeger(state,-2)==42 && lua_tointeger(state,-1)==13);
    call->result=42;return 0;
}
static unsigned callbackDestructions=0;
static int ThrowNative(lua_State*){struct Cleanup{~Cleanup(){++callbackDestructions;}} cleanup;
    throw std::runtime_error("intentional native callback failure");}
static int RaiseLua(lua_State* state){return luaL_error(state,"intentional Lua callback failure");}
static void Calls(){
    ScriptSystem system;lua_State* state=system.CreateLuaThread("calls");lua_State* second=system.CreateLuaThread("independent");
    lua_pushinteger(state,918);const int base=lua_gettop(state);
    system.RegisterFile("Maps/Probe.lua","counter=(counter or 0)+1; function calculate(a,b) return a*b,a+b end");
    CHECK(system.LoadFile(state,"maps\\PROBE.LUA") && system.LoadFile(state,"Maps/Probe.lua"));
    CHECK(Execute(system,state,"assert(counter==2 and io==nil and os==nil and dofile==nil and loadfile==nil)"));
    CHECK(Execute(system,second,"assert(counter==nil)"));
    CHECK(!system.LoadFile(state,"missing.lua") && !system.LoadFile(state,"../Probe.lua"));
    Reject([&]{system.RegisterFile("C:/Probe.lua","");});
    CHECK(!Execute(system,state,"local =") && lua_gettop(state)==base);
    CHECK(!Execute(system,state,"error({reason='non-string'})") && std::strstr(system.LastError(),"non-string"));
    CHECK(!system.Execute(state,nullptr,2) && lua_gettop(state)==base);
    NestedCall nested{&system,state};CHECK(system.CallCFunction(state,Nested,&nested) && nested.result==42);
    CHECK(lua_gettop(state)==base && lua_tointeger(state,-1)==918);
    CHECK(!system.CallCFunction(state,RaiseLua,nullptr) && std::strstr(system.LastError(),"intentional Lua"));
    CHECK(!system.CallCFunction(state,ThrowNative,nullptr) && std::strstr(system.LastError(),"C++ script callback"));
    CHECK(system.RegisterFunction(state,"throwNative",ThrowNative));
    CHECK(!Execute(system,state,"throwNative()") && lua_gettop(state)==base);
    CHECK(Execute(system,state,"local ok=pcall(throwNative); assert(not ok)"));
    CHECK(callbackDestructions==3);
    CHECK(!system.CallFunction(state,0,0) && lua_gettop(state)==base);
    lua_getglobal(state,"calculate");lua_pushinteger(state,2);lua_pushinteger(state,5);
    CHECK(!system.CallFunction(state,2,UINT_MAX) && lua_gettop(state)==base+3);
    CHECK(system.CallFunction(state,2,128) && lua_gettop(state)==base+128);
    CHECK(lua_tointeger(state,base+1)==10 && lua_tointeger(state,base+2)==7 && lua_isnil(state,base+128));lua_settop(state,base);
    CHECK(Execute(system,state,"function fail() error('call failure') end"));lua_getglobal(state,"fail");
    CHECK(!system.CallFunction(state,0,1) && lua_gettop(state)==base);
    CHECK(Execute(system,state,"assert(counter==2)"));
    system.FreeLuaThread(second);system.FreeLuaThread(second);CHECK(system.ThreadCount()==1);
    system.FreeLuaThread(state);CHECK(system.ThreadCount()==0);
}
static void Events(){
    ScriptSystem system;auto* state=system.CreateLuaThread("first");auto* second=system.CreateLuaThread("second");
    auto* args=system.CreateArgs();args->Push(true);args->Push(-7);args->Push(1.25f);args->Push("A\0B",3);args->PushNULL();
    const char* source=R"lua(
trace=''; function first(...) assert(select('#',...)==5); local b,i,f,s,n=...;
 assert(b==true and i==-7 and f==1.25 and #s==3 and s:byte(2)==0 and n==nil); trace=trace..'A'; return false end
function second(...) trace=trace..'B'; return true end
GameEvents.Typed.Add(first); GameEvents.Typed.Add(second); GameEvents.Typed.Add(first)
GameEvents.Number.Add(function(...) assert(select('#',...)==5); return 2.25 end)
GameEvents.Number.Add(function(...) return 3.75 end)
GameEvents.NoArgs.Add(function(...) assert(select('#',...)==0); return true end)
GameEvents.Bad.Add(function() return '2' end)
GameEvents.Fraction.Add(function() return .5 end)
GameEvents.Overflow.Add(function() return 2147483648 end)
GameEvents.Infinite.Add(function() return 1/0 end)
GameEvents.Nil.Add(function() return nil end)
)lua";
    CHECK(Execute(system,state,source));bool value=false;
    CHECK(system.CallHook("Typed",args,value) && value);CHECK(Execute(system,state,"assert(trace=='ABA'); trace=''"));
    value=true;CHECK(system.CallTestAll("Typed",args,value) && !value);
    CHECK(Execute(system,state,"assert(trace=='ABA'); trace=''"));CHECK(system.CallTestAny("Typed",args,value) && value);
    CHECK(Execute(system,state,"GameEvents.Typed.Remove(first); trace=''"));
    CHECK(system.CallHook("Typed",args,value) && value && Execute(system,state,"assert(trace=='B')"));
    CHECK(system.CallHook("NoArgs",nullptr,value) && value);
    value=false;CHECK(!system.CallHook("Unsubscribed",args,value) && !value);
    value=true;CHECK(!system.CallTestAll("Unsubscribed",nullptr,value) && value);
    int integer=-71;float real=-71;
    CHECK(!system.CallAccumulator("Unsubscribed",nullptr,integer) && integer==-71);
    CHECK(!system.CallAccumulator("Unsubscribed",nullptr,real) && real==-71);
    CHECK(system.CallAccumulator("Number",args,integer) && integer==6);
    CHECK(system.CallAccumulator("Number",args,real) && real==6);
    for(const char* event:{"Bad","Fraction","Overflow","Infinite","Nil"}){integer=319;CHECK(!system.CallAccumulator(event,args,integer) && integer==319);}
    real=319;CHECK(!system.CallAccumulator("Infinite",args,real) && real==319);
    CHECK(system.CallAccumulator("Fraction",args,real) && real==.5f);
    value=true;CHECK(system.CallTestAny("Nil",nullptr,value) && !value);
    CHECK(Execute(system,second,"GameEvents.Number.Add(function(...) return 4 end)"));
    CHECK(system.CallAccumulator("Number",args,integer) && integer==10);
    CHECK(Execute(system,second,"GameEvents.Number.Add(function() error('late listener error') end)"));
    integer=55;CHECK(!system.CallAccumulator("Number",args,integer) && integer==55);
    ScriptArguments foreign(0);value=true;CHECK(!system.CallHook("NoArgs",&foreign,value) && value);
    system.DestroyArgs(args);
    auto* many=system.CreateArgs(512);for(int i=0;i<512;++i)many->Push(i);
    CHECK(Execute(system,state,"GameEvents.Many.Add(function(...) assert(select('#',...)==512); return select(512,...) end)"));
    CHECK(system.CallAccumulator("Many",many,integer) && integer==511);system.DestroyArgs(many);
}
static ScriptSystem* mutationSystem=nullptr;static lua_State* mutationTarget=nullptr;
static int MutateOther(lua_State*){
    CHECK(Execute(*mutationSystem,mutationTarget,"GameEvents.Cross.Remove(old); GameEvents.Cross.Add(new)"));
    Reject([&]{mutationSystem->CreateLuaThread("during dispatch");});mutationSystem->FreeLuaThread(mutationTarget);
    CHECK(mutationSystem->ThreadCount()==2);return 0;
}
static int NestedEvent(lua_State* state){
    int value=-1;CHECK(mutationSystem->CallAccumulator("Inner",nullptr,value));lua_pushinteger(state,value);return 1;
}
static void EventSnapshots(){
    ScriptSystem system;auto* first=system.CreateLuaThread("first");auto* second=system.CreateLuaThread("second");
    mutationSystem=&system;mutationTarget=second;CHECK(system.RegisterFunction(first,"mutateOther",MutateOther));
    CHECK(Execute(system,first,"GameEvents.Cross.Add(function() mutateOther(); return 1 end)"));
    CHECK(Execute(system,second,"old=function() return 10 end; new=function() return 100 end; GameEvents.Cross.Add(old)"));
    int value=-1;CHECK(system.CallAccumulator("Cross",nullptr,value) && value==11);
    CHECK(system.CallAccumulator("Cross",nullptr,value) && value==101);
    CHECK(system.RegisterFunction(first,"nestedEvent",NestedEvent));
    CHECK(Execute(system,first,R"lua(
GameEvents.Inner.Add(function() return 3 end)
GameEvents.Outer.Add(function() return nestedEvent()+1 end)
trace=''; local replacement=function() trace=trace..'C'; return true end
local later=function() trace=trace..'B'; return false end
GameEvents.Change.Add(function() trace=trace..'A'; GameEvents.Change.Remove(later); GameEvents.Change.Add(replacement); return false end)
GameEvents.Change.Add(later)
)lua"));
    CHECK(system.CallAccumulator("Outer",nullptr,value) && value==4);
    bool boolean=false;CHECK(system.CallHook("Change",nullptr,boolean) && !boolean);
    CHECK(Execute(system,first,"assert(trace=='AB'); trace=''"));
    CHECK(system.CallHook("Change",nullptr,boolean) && boolean);CHECK(Execute(system,first,"assert(trace=='AC')"));
    mutationSystem=nullptr;mutationTarget=nullptr;
}
static int TryClose(lua_State* state){
    auto& system=*static_cast<ScriptSystem*>(lua_touserdata(state,1));
    CHECK(!system.IsQuiescent() && !system.Close());system.FreeLuaThread(state);CHECK(system.ThreadCount()==1);return 0;
}
static void Ownership(){
    auto script=std::make_shared<ScriptSystem>();auto state=std::make_shared<HostState>("C:\\fixture\\",nullptr,nullptr,script);
    EngineServices engine(state);CHECK(engine.GetScriptSystem()==script.get());
    auto* queried=static_cast<ICvEngineUtility4*>(engine.QueryInterface(guidICvEngineUtility4));
    CHECK(queried->GetScriptSystem()==script.get());ZeroSisHostBinding::Release(queried);
    auto* vm=script->CreateLuaThread("owner");auto* args=script->CreateArgs();args->Push(1);
    CHECK(script->CallCFunction(vm,TryClose,script.get()) && script->IsQuiescent());
    std::thread wrong([&]{
        for(unsigned i=0;i<32;++i){
            bool value=true;CHECK(!script->CallHook("event",args,value) && value);
            CHECK(!Execute(*script,vm,"error('foreign')"));CHECK(!script->Close());
            script->DestroyArgs(args);script->FreeLuaThread(vm);
        }
        Reject([&]{script->CreateLuaThread("foreign");});Reject([&]{args->Count();});
    });wrong.join();
    CHECK(script->ForeignCalls()==160 && script->ThreadCount()==1 && script->ArgumentCount()==1);
    CHECK(script->Close() && script->ThreadCount()==0 && script->ArgumentCount()==0 && script->IsClosed());
    CHECK(!Execute(*script,vm,"return true"));Reject([&]{script->CreateLuaThread("closed");});
    for(unsigned i=0;i<32;++i){ScriptSystem cycle;auto* l=cycle.CreateLuaThread("cycle");CHECK(Execute(cycle,l,"assert(2+2==4)"));cycle.FreeLuaThread(l);CHECK(cycle.Close());}
}
static unsigned CppFailures(){
    unsigned failures=0;
    for(int point=0;point<32;++point){
        ScriptSystem system;const auto live=allocations.load();bool failed=false;allocationBudget=point;
        try{system.CreateArgs(64);}catch(const std::bad_alloc&){failed=true;}
        allocationBudget=-1;
        if(!failed){CHECK(system.ArgumentCount()==1);break;}
        ++failures;CHECK(system.ArgumentCount()==0 && allocations==live);
    }
    ScriptSystem system;auto* vm=system.CreateLuaThread("cpp");auto* args=system.CreateArgs();args->Push(4);
    CHECK(Execute(system,vm,"GameEvents.Cpp.Add(function(v) return v+1 end)"));
    for(int point=0;point<32;++point){
        int value=987;allocationBudget=point;const bool ok=system.CallAccumulator("Cpp",args,value);allocationBudget=-1;
        if(ok){CHECK(value==5);break;}
        ++failures;CHECK(value==987 && system.IsQuiescent());CHECK(system.CallAccumulator("Cpp",args,value) && value==5);
    }
    system.DestroyArgs(args);CHECK(failures>=5);return failures;
}
static unsigned LuaCreateFailures(){
    unsigned failures=0;bool reachedSuccess=false;
    for(int point=0;point<2048;++point){
        LuaMemory memory;memory.budget=point;
        {ScriptSystem system(LuaMemory::Allocate,&memory);bool failed=false;
            try{system.CreateLuaThread("allocation");}catch(const std::exception&){failed=true;}
            if(failed){++failures;CHECK(system.ThreadCount()==0 && memory.rejections>0);}
            else{CHECK(system.ThreadCount()==1);reachedSuccess=true;}
            CHECK(system.Close());
        }
        CHECK(memory.bytes==0 && memory.blocks==0);if(reachedSuccess)break;
    }
    CHECK(reachedSuccess && failures>20);return failures;
}
static unsigned LuaOperationFailures(bool event){
    unsigned failures=0;bool reachedSuccess=false;
    for(int point=0;point<512;++point){
        LuaMemory memory;
        {ScriptSystem system(LuaMemory::Allocate,&memory);auto* state=system.CreateLuaThread("operation");
            CHECK(Execute(system,state,"GameEvents.Allocation.Add(function() local a={}; for i=1,100 do a[i]=string.rep('x',i) end; return #a end)"));
            lua_pushinteger(state,612);const int base=lua_gettop(state);int output=612;memory.budget=point;
            const bool ok=event?system.CallAccumulator("Allocation",nullptr,output):Execute(system,state,"local t={}; for i=1,100 do t[i]=string.rep('y',i) end; assert(#t==100)");
            memory.budget=-1;CHECK(lua_gettop(state)==base && lua_tointeger(state,-1)==612 && system.IsQuiescent());
            if(ok){CHECK(!event || output==100);reachedSuccess=true;}
            else{++failures;CHECK(output==612 && memory.rejections>0);CHECK(Execute(system,state,"assert(3*7==21)"));
                if(event)CHECK(system.CallAccumulator("Allocation",nullptr,output) && output==100);
            }
            CHECK(system.Close());
        }
        CHECK(memory.bytes==0 && memory.blocks==0);if(reachedSuccess)break;
    }
    CHECK(reachedSuccess && failures>10);return failures;
}
static void ProtectedReserveFailure(){
    LuaMemory memory;ScriptSystem system(LuaMemory::Allocate,&memory);auto* state=system.CreateLuaThread("stack");
    CHECK(Execute(system,state,"function many() return 1 end"));lua_getglobal(state,"many");
    memory.budget=0;CHECK(!system.CallFunction(state,0,4000));memory.budget=-1;
    CHECK(lua_gettop(state)==1 && lua_isfunction(state,1));CHECK(system.CallFunction(state,0,4000));
    CHECK(lua_gettop(state)==4000 && lua_tointeger(state,1)==1 && lua_isnil(state,4000));lua_settop(state,0);
}
int main(){
    try{
        Arguments();Calls();Events();EventSnapshots();Ownership();const auto cpp=CppFailures();
        const auto creation=LuaCreateFailures(),execution=LuaOperationFailures(false),events=LuaOperationFailures(true);ProtectedReserveFailure();
        CHECK(GetModuleHandleW(L"CvGameCoreDLL_Expansion2_x64.dll")==nullptr);
        std::printf("HOST_SCRIPT_PASS checks=%u CPP_FAILURES=%u LUA_CREATE_FAILURES=%u LUA_EXECUTE_FAILURES=%u LUA_EVENT_FAILURES=%u FOREIGN_REJECTIONS=160 RESTARTS=32 GAMECORE_LOADED=false\n",
                    checks.load(),cpp,creation,execution,events);return 0;
    }catch(const std::exception& e){std::fprintf(stderr,"SCRIPT_UNEXPECTED: %s\n",e.what());return 1;}
}
