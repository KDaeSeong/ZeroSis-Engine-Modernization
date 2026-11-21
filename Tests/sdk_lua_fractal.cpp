#include "SdkFLuaIncludes.h"
#include "CvLuaCheckedInteger.h"
#include "ZeroSisLuaFractal.h"
#include "ZeroSisLuaFractalNumeric.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdint>
#include <climits>
#include <vector>
#include <string>
#include <algorithm>
#include <stdexcept>

static unsigned checks=0;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"FAIL|%u|line=%d|%s\n",checks,__LINE__,#x); std::exit(2); } } while (0)
struct LuaMemory {
    int budget=-1; std::size_t blocks=0;
    static void* Allocate(void* context,void* pointer,std::size_t oldSize,std::size_t size) {
        auto& m=*static_cast<LuaMemory*>(context);
        if (!size) { if (pointer) { --m.blocks; std::free(pointer); } return nullptr; }
        if (size>oldSize && m.budget>=0) { if (!m.budget) return nullptr; --m.budget; }
        void* value=std::realloc(pointer,size); if (value && !pointer) ++m.blocks; return value;
    }
};
static unsigned errors=0;
static void ErrorHandler(const TCHAR*) { ++errors; }
static void HashWord(std::uint64_t& hash,std::uint32_t value) {
    for (unsigned i=0;i<4;++i) { hash^=(value>>(i*8))&255; hash*=UINT64_C(1099511628211); }
}
// Numeric adapter only: exact release LCG/counter semantics, no real GC/log services.
class CvRandom {
public:
    std::uint32_t seed=0,calls=0; std::uint64_t trace=UINT64_C(14695981039346656037);
    int get(int bound,const char*) {
        ++calls; seed=seed*UINT32_C(1103515245)+UINT32_C(12345);
        const int value=static_cast<int>((static_cast<std::uint64_t>((seed>>16)&65535)*static_cast<unsigned short>(bound))/65536);
        HashWord(trace,static_cast<std::uint32_t>(bound)); HashWord(trace,static_cast<std::uint32_t>(value)); return value;
    }
};
static CvRandom mapRandom;
struct GameOwner { CvRandom& getMapRand() { return mapRandom; } };
struct GlobalsOwner { GameOwner game; GameOwner& getGame() { return game; } };
static GlobalsOwner GC;

#ifdef FRACTAL_LIFETIME_FIXTURE
static unsigned constructed=0,destroyed=0,nativeCalls=0,attempts=0;
static bool constructorFails=false;
static int observedX=-99,observedY=-99;
static const void* observedRifts=nullptr;
class CvFractal {
public:
#include "fractal_enum_fixture.h"
    CvFractal() { ++attempts; if (constructorFails) throw std::runtime_error("instrumented constructor failure"); ++constructed; }
    virtual ~CvFractal() { ++destroyed; }
    void fracInit(int,int,int,CvRandom&,int,CvFractal* rifts,int x,int y) {
        ++nativeCalls; observedRifts=rifts; observedX=x; observedY=y;
    }
    void ridgeBuilder(CvRandom&,int,int,int,int) { ++nativeCalls; }
    int getHeight(int,int) { ++nativeCalls; return 211; }
    int getHeightFromPercent(int) { ++nativeCalls; return 73; }
};
#else
typedef unsigned char byte;
typedef int DirectionTypes;
static const int NUM_DIRECTION_TYPES=6,c_eCiv5GameplayDLL=0;
template<class T,int N,bool Grow,int Pool,int Flags> using FStaticVector=std::vector<T>;
static int range(int value,int low,int high) { return std::max(low,std::min(value,high)); }
#define FAssert(condition) ((void)(condition))
#define CvAssertMsg(condition,message) ((void)(condition));
#define DEBUG_VARIABLE(value) ((void)(value))
#include "fractal_class_fixture.h"
#include "fractal_calculation_fixture.h"
#endif
#include "fractal_lua_fixture.h"

static lua_State* Open(LuaMemory& memory) {
    auto* L=lua_newstate(LuaMemory::Allocate,&memory); CHECK(L);
    luaL_openlibs(L); lua_pushinteger(L,773); return L;
}
#ifdef FRACTAL_LIFETIME_FIXTURE
static bool Call(lua_State* L,lua_CFunction function) {
    const int top=lua_gettop(L); const bool result=FLua::Details::CCallWithErrorHandling(L,function);
    CHECK(lua_gettop(L)==top && lua_tointeger(L,1)==773);
    CHECK(FLua::ms_CriticalSection.GetRecursionCount()==0); return result;
}
#endif
static bool Script(lua_State* L,const char* script,int results=0) {
    const int status=luaL_loadstring(L,script); CHECK(status==0);
    const int error=lua_pcall(L,0,results,0);
    if (error) { std::fprintf(stderr,"LUA|%s\n",lua_tostring(L,-1)); lua_pop(L,1); }
    return error==0;
}
#ifdef FRACTAL_LIFETIME_FIXTURE
static int Factory(lua_State* L) { CvLuaFractal::CreateFractal(L); lua_setglobal(L,"subject"); return 0; }
static int Destroy(lua_State* L) { lua_getglobal(L,"subject"); lua_replace(L,1); return CvLuaFractal::lDestroy(L); }
static int Height(lua_State* L) { lua_getglobal(L,"subject"); lua_replace(L,1); lua_pushinteger(L,50); return CvLuaFractal::lGetHeight(L); }
static int Ridges(lua_State* L) {
    lua_getglobal(L,"subject"); lua_replace(L,1); lua_pushinteger(L,3); lua_newtable(L);
    lua_pushinteger(L,1); lua_pushinteger(L,2); return CvLuaFractal::lBuildRidges(L);
}
static int Rifts(lua_State* L) {
    lua_pushinteger(L,41); lua_replace(L,1); lua_pushinteger(L,29); lua_pushinteger(L,3); lua_newtable(L);
    lua_getglobal(L,"subject"); lua_pushinteger(L,5); lua_pushinteger(L,5); return CvLuaFractal::lCreateRifts(L);
}
static void ResetCounts() { constructed=destroyed=nativeCalls=attempts=0; observedX=observedY=-99; observedRifts=nullptr; }
static void Lifetime() {
    ResetCounts(); LuaMemory memory; auto* L=Open(memory); CHECK(Call(L,Factory)); CHECK(constructed==1 && destroyed==0);
    CHECK(Call(L,Destroy)); CHECK(destroyed==1); CHECK(Call(L,Destroy));
#ifdef LUA_FRACTAL_ORIGINAL
    CHECK(destroyed==2); CHECK(Call(L,Height)); CHECK(nativeCalls==1);
#else
    CHECK(destroyed==1); CHECK(!Call(L,Height)); CHECK(!Call(L,Ridges)); CHECK(!Call(L,Rifts)); CHECK(nativeCalls==0);
#endif
    lua_close(L); CHECK(memory.blocks==0);
#ifdef LUA_FRACTAL_ORIGINAL
    CHECK(destroyed==3); std::puts("ORIGINAL_LIFETIME|destructions=3|method_after_destroy=accepted");
#else
    CHECK(destroyed==1); std::puts("CANDIDATE_LIFETIME|destructions=1|method_after_destroy=rejected");
#endif
}
static void Foreign() {
    for (unsigned mode=0;mode<3;++mode) {
        ResetCounts(); LuaMemory memory; auto* L=Open(memory); CvFractal* foreign=nullptr;
        // Construct a valid C++ spy in foreign userdata: observing acceptance does
        // not require dereferencing an invalid native address.
        void* raw=lua_newuserdata(L,sizeof(ZeroSisLuaFractal::Storage<CvFractal>)); foreign=new(raw) CvFractal();
        lua_pushvalue(L,-1); lua_setglobal(L,"foreign_storage");
        if (mode==1) {
            CHECK(Call(L,Factory)); lua_getglobal(L,"subject"); CHECK(lua_getmetatable(L,-1));
            lua_setmetatable(L,-3); lua_pop(L,1);
        }
        if (mode==2) { lua_pop(L,1); lua_pushlightuserdata(L,foreign); }
        lua_setglobal(L,"subject");
        const unsigned before=nativeCalls;
        if (mode!=2) {
#ifdef LUA_FRACTAL_ORIGINAL
            CHECK(Call(L,Height)); CHECK(Call(L,Ridges));
#else
            CHECK(!Call(L,Height)); CHECK(!Call(L,Ridges));
#endif
        }
#ifdef LUA_FRACTAL_ORIGINAL
        CHECK(Call(L,Rifts)); CHECK(observedRifts==foreign); CHECK(nativeCalls>before);
#else
        CHECK(!Call(L,Rifts)); CHECK(nativeCalls==before);
#endif
        bool nativeDestroyed=false;
#ifdef LUA_FRACTAL_ORIGINAL
        nativeDestroyed=Call(L,Destroy); CHECK(nativeDestroyed==(mode!=2));
#else
        CHECK(!Call(L,Destroy));
#endif
        // Clear any copied metatable and explicitly release the foreign spy once.
        if (mode!=2) { lua_getglobal(L,"subject"); lua_pushnil(L); lua_setmetatable(L,-2); lua_pop(L,1); }
        if (!nativeDestroyed) foreign->~CvFractal(); lua_close(L); CHECK(memory.blocks==0);
        std::printf("FOREIGN|%u|native_dispatch=%u\n",mode,nativeCalls-before);
    }
}
static void AllocationFailures() {
    unsigned failures=0,missingFinalizers=0; bool success=false;
    for (int budget=0;budget<256;++budget) {
        ResetCounts(); LuaMemory memory; auto* L=Open(memory); memory.budget=budget;
        const bool ok=Call(L,Factory); memory.budget=-1;
        lua_close(L); CHECK(memory.blocks==0);
        if (!ok) { ++failures; if (constructed!=destroyed) ++missingFinalizers; }
        else { CHECK(constructed==1 && destroyed==1); success=true; }
#ifndef LUA_FRACTAL_ORIGINAL
        CHECK(constructed==destroyed);
#endif
        if (success) break;
    }
    CHECK(success && failures>0);
#ifdef LUA_FRACTAL_ORIGINAL
    CHECK(missingFinalizers>0);
#else
    CHECK(missingFinalizers==0);
#endif
    std::printf("LUA_FAILURES|%u|missing_finalizers=%u\n",failures,missingFinalizers);
    ResetCounts(); LuaMemory memory; auto* L=Open(memory); constructorFails=true; CHECK(!Call(L,Factory));
    constructorFails=false; CHECK(attempts==1 && constructed==0 && destroyed==0); CHECK(Call(L,Factory));
    lua_close(L); CHECK(memory.blocks==0 && constructed==1 && destroyed==1);
    std::puts("CONSTRUCTOR_FAILURE|unconstructed_not_destroyed|retry_passed");
}
static void Collection() {
    ResetCounts(); LuaMemory memory; auto* L=Open(memory);
    for (int i=0;i<128;++i) CHECK(Call(L,Factory));
    lua_pushnil(L); lua_setglobal(L,"subject");
    memory.budget=0; lua_gc(L,LUA_GCCOLLECT,0); memory.budget=-1;
    CHECK(constructed==128 && destroyed==128); lua_gc(L,LUA_GCCOLLECT,0);
    CHECK(destroyed==128); lua_close(L); CHECK(memory.blocks==0 && destroyed==128);
    std::puts("COLLECTION|128_exactly_once|allocation_disabled|weak_ownership_does_not_retain");
}
static void Defaults() {
    LuaMemory memory; auto* L=Open(memory); CvLuaFractal::Register(L);
    CHECK(Script(L,"a=Fractal.Create(41,29,3,{})"));
    std::printf("CREATE_MISSING|%d|%d\n",observedX,observedY);
#ifdef LUA_FRACTAL_ORIGINAL
    CHECK(observedX==0 && observedY==0);
#else
    CHECK(observedX==7 && observedY==6);
#endif
    CHECK(Script(L,"b=Fractal.CreateRifts(41,29,3,{})"));
    std::printf("RIFTS_MISSING|%s|%d|%d\n",observedRifts ? "non_null" : "null",observedX,observedY);
#ifdef LUA_FRACTAL_ORIGINAL
    CHECK(observedRifts!=nullptr);
#else
    CHECK(observedRifts==nullptr && observedX==7 && observedY==6);
    CHECK(Script(L,"local ok=pcall(Fractal.CreateRifts,41,29,3,{},false);assert(not ok)"));
#endif
    lua_close(L); CHECK(memory.blocks==0);
}
#else
static void Mathematics() {
    const std::uint32_t seeds[]={0,1,UINT32_C(0xfedcba98)};
    const char* const variants[]={
        "a=Fractal.Create(41,29,3,{},5,5)",
        "a=Fractal.Create(41,29,3,{FRAC_WRAP_X=true,FRAC_WRAP_Y=true,FRAC_PERCENT=true,FRAC_INVERT_HEIGHTS=true},5,5)",
        "a=Fractal.Create(41,29,3,{FRAC_POLAR=true,FRAC_CENTER_RIFT=true},5,5)",
        "r=Fractal.Create(41,29,2,{FRAC_WRAP_X=true},5,5);a=Fractal.CreateRifts(41,29,3,{FRAC_WRAP_X=true},r,5,5);a:BuildRidges(3,{FRAC_WRAP_X=true},1,2)",
#ifdef LUA_FRACTAL_ORIGINAL
        "a=Fractal.Create(41,29,3,{},nil,nil)",
        "a=Fractal.CreateRifts(41,29,3,{},nil,nil,nil)"
#else
        "a=Fractal.Create(41,29,3,{})",
        "a=Fractal.CreateRifts(41,29,3,{})"
#endif
    };
    for (unsigned seed=0;seed<_countof(seeds);++seed) for (unsigned mode=0;mode<_countof(variants);++mode) {
        mapRandom=CvRandom(); mapRandom.seed=seeds[seed]; LuaMemory memory; auto* L=Open(memory); CvLuaFractal::Register(L);
        CHECK(Script(L,variants[mode]));
        CHECK(Script(L,"local values={};for y=0,28 do for x=0,40 do values[#values+1]=a:GetHeight(x,y) end end;for p=0,100 do values[#values+1]=a:GetHeight(p) end;return values",1));
        CHECK(lua_istable(L,-1) && lua_objlen(L,-1)==1290);
        std::uint64_t heights=UINT64_C(14695981039346656037);
        for (int i=1;i<=1290;++i) { lua_rawgeti(L,-1,i); CHECK(lua_type(L,-1)==LUA_TNUMBER); HashWord(heights,static_cast<std::uint32_t>(lua_tointeger(L,-1))); lua_pop(L,1); }
        lua_pop(L,1); CHECK(Script(L,"local get=a.GetHeight;assert(get(a,1,1)==a:GetHeight(1,1))"));
        std::printf("MATH|%u|%u|%016llx|%u|%u|%016llx\n",seeds[seed],mode,static_cast<unsigned long long>(heights),mapRandom.seed,mapRandom.calls,static_cast<unsigned long long>(mapRandom.trace));
        lua_close(L); CHECK(memory.blocks==0);
    }
}
#endif
int main(int argc,char** argv) {
    if (argc!=2) return 1; FLua::SetErrorHandler(ErrorHandler);
#ifdef FRACTAL_LIFETIME_FIXTURE
    if (!std::strcmp(argv[1],"lifetime")) Lifetime();
    else if (!std::strcmp(argv[1],"foreign")) Foreign();
    else if (!std::strcmp(argv[1],"faults")) AllocationFailures();
    else if (!std::strcmp(argv[1],"collection")) Collection();
    else if (!std::strcmp(argv[1],"defaults")) Defaults();
    else return 1;
#else
    if (!std::strcmp(argv[1],"math")) Mathematics(); else return 1;
#endif
    std::printf("PASS|%u\n",checks); return 0;
}
