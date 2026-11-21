#include "lua.hpp"
#include "ZeroSisLuaBorrowed.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>
#include <atomic>
#include <stdexcept>
#include <memory>
#include <set>

static std::atomic<unsigned> checks{0};
static unsigned partialRegistrations = 0;
static unsigned isNoneIncorrect = 0;
#define CHECK(x) do { ++checks; if (!(x)) { std::fprintf(stderr,"FAIL|line=%d|%s\n",__LINE__,#x); std::exit(2); } } while (0)
#ifdef LUA_BORROWED_ORIGINAL
static const bool candidate = false;
#else
static const bool candidate = true;
#endif

struct LuaMemory
{
    int budget = -1;
    std::size_t blocks = 0, bytes = 0;
    static void* Allocate(void* context, void* pointer, std::size_t oldSize, std::size_t size)
    {
        auto& memory = *static_cast<LuaMemory*>(context);
        if (!size)
        {
            if (pointer) { --memory.blocks; memory.bytes -= oldSize; std::free(pointer); }
            return NULL;
        }
        if (size > oldSize && memory.budget >= 0)
        {
            if (!memory.budget) return NULL;
            --memory.budget;
        }
        void* result = std::realloc(pointer, size);
        if (result)
        {
            if (!pointer) { ++memory.blocks; oldSize = 0; }
            memory.bytes += size - oldSize;
        }
        return result;
    }
};

static thread_local int registrationAction = 0;
static thread_local const void* invalidateDuringRegistration = NULL;
static unsigned metamethodCalls = 0;
static unsigned nativeExceptionsDestroyed = 0;
struct RegistrationFailure : std::exception
{
    const char* what() const noexcept override { return "instrumented native registration failure"; }
    ~RegistrationFailure() noexcept override { ++nativeExceptionsDestroyed; }
};
static int UnexpectedIndex(lua_State*) { ++metamethodCalls; return 0; }
static int InvalidateFinalizer(lua_State* L)
{
    ZeroSisLuaBorrowed::Invalidate(lua_touserdata(L, lua_upvalueindex(1)));
    return 0;
}
static void Methods(lua_State* L, int table)
{
    lua_pushinteger(L, 17);
    lua_setfield(L, table, "registered");
    if (registrationAction == 1) ZeroSisLuaBorrowed::Invalidate(invalidateDuringRegistration);
    if (registrationAction == 2) lua_gc(L, LUA_GCCOLLECT, 0);
    if (registrationAction == 3) luaL_error(L, "injected method registration failure");
    if (registrationAction == 4) throw RegistrationFailure();
    if (registrationAction == 5) throw 17;
}

// Native owners are instruments; actual scoped template and IsNone bodies are extracted.
typedef int PlayerTypes;
struct CvUnit;
struct CvDeal;
struct ICvUnit1;
struct ICvDeal1;
class CvDllUnit;
static void UnitUninitObserved(CvUnit*);
static void UnitDestroyedObserved(CvUnit*);
static void UnitMapRemovalObserved(int, int, int, int);
struct EngineInstrument
{
    bool GetDone() { return false; }
    void GameplayUnitDestroyed(ICvUnit1*);
};
struct PlotManagerInstrument { void RemoveUnit(int id, int x, int y, int layer) { UnitMapRemovalObserved(id, x, y, layer); } };
struct MapInstrument { PlotManagerInstrument manager; PlotManagerInstrument& plotManager() { return manager; } };
struct GlobalsInstrument
{
    bool graphics = false; MapInstrument map;
    bool IsGraphicsInitialized() { return graphics; }
    MapInstrument& getMap() { return map; }
    CvDeal* UnwrapDealPointer(ICvDeal1*);
};
static EngineInstrument engineInstrument;
static EngineInstrument* gDLL = &engineInstrument;
static GlobalsInstrument GC;
namespace FSerialization { static std::set<CvUnit*> unitsToCheck; }
static const int DEFAULT_UNIT_MAP_LAYER = 0;
template<class T> using auto_ptr = std::unique_ptr<T>; // Only constructor/get/destruction are used by the exact body.
// Real SDK container code, with only the allocation service replaced for this executable.
static const unsigned c_eMPoolTypeContainer = 0, c_eCiv5GameplayDLL = 1;
static unsigned containerBlocks = 0, containerOperations = 0;
static void* ContainerAllocate(std::size_t bytes, std::size_t alignment)
{
    void* result = _aligned_malloc(bytes, alignment);
    if (!result) throw std::bad_alloc();
    ++containerBlocks;
    return result;
}
static void ContainerFree(void* pointer)
{
    if (pointer) { CHECK(containerBlocks > 0); --containerBlocks; _aligned_free(pointer); }
}
#define FMALLOCALIGNED(bytes,alignment,pool,sub) ContainerAllocate(bytes,alignment)
#define FFREEALIGNED(pointer) ContainerFree(pointer)
#include "FFastVector.h"
#define VALIDATE_OBJECT
#define OBJECT_DESTROYED UnitDestroyedObserved(this);
using TradedItemList = std::vector<int>; // Clear/iteration/copy adapter, not the full native trade-item list.
#include "lua_borrowed_fixture.h"
CvDeal* GlobalsInstrument::UnwrapDealPointer(ICvDeal1* value)
{
    return value ? static_cast<CvDllDeal*>(value)->GetInstance() : NULL;
}
extern "C" void PeerInvalidate(const void*);
extern "C" const void* PeerTracking();
extern "C" void* PeerCityRegistry();

static CvUnit* observedUnit = NULL;
static CvDllUnit* retainedUnitProxy = NULL;
static lua_State* observedUnitLua = NULL;
static int observedUnitTable = 0;
static unsigned unitNotifications = 0, unitMapRemovals = 0, unitUninits = 0, unitDestructions = 0;
void EngineInstrument::GameplayUnitDestroyed(ICvUnit1* value)
{
    CHECK(observedUnit && !retainedUnitProxy);
    auto* proxy = static_cast<CvDllUnit*>(value);
    CHECK(proxy->GetInstance() == observedUnit && proxy->GetID() == 61);
    CHECK(CvLuaUnit::GetInstance(observedUnitLua, observedUnitTable, false) == observedUnit);
    retainedUnitProxy = new CvDllUnit(proxy->GetInstance());
    ++unitNotifications;
}
static void UnitMapRemovalObserved(int id, int x, int y, int layer)
{
    CHECK(observedUnit && unitNotifications == 1 && retainedUnitProxy);
    CHECK(id == 61 && x == 5 && y == 9 && layer == 3);
    CHECK(retainedUnitProxy->GetInstance() == observedUnit && retainedUnitProxy->GetID() == 61);
    ++unitMapRemovals;
}
static void UnitUninitObserved(CvUnit* unit)
{
    if (unit != observedUnit) return;
    CHECK(unitNotifications == 1 && unitMapRemovals == 1);
    CHECK((retainedUnitProxy->GetInstance() == NULL) == candidate);
    CHECK((CvLuaUnit::GetInstance(observedUnitLua, observedUnitTable, false) == NULL) == candidate);
    ++unitUninits;
}
static void UnitDestroyedObserved(CvUnit* unit)
{
    if (unit != observedUnit) return;
    CHECK(unitUninits == 1);
    CHECK((retainedUnitProxy->GetInstance() == NULL) == candidate);
    ++unitDestructions;
}

static std::size_t Tracked()
{
    std::size_t total = 0;
    auto& state = ZeroSisLuaBorrowed::State();
    AcquireSRWLockShared(&state.lock);
    for (const auto* head : state.buckets)
        for (auto* item = head; item; item = item->next) ++total;
    ReleaseSRWLockShared(&state.lock);
    return total;
}
template<class T> static bool IsRegistryKey(void* key)
{
    return key == ZeroSisLuaBorrowed::RegistryKey<T, 0>() || key == ZeroSisLuaBorrowed::RegistryKey<T, 1>() || key == ZeroSisLuaBorrowed::RegistryKey<T, 2>();
}
static void AssertRegistryKeys(lua_State* L)
{
    lua_pushnil(L);
    while (lua_next(L, LUA_REGISTRYINDEX))
    {
        if (lua_type(L, -2) == LUA_TLIGHTUSERDATA)
        {
            void* key = lua_touserdata(L, -2);
            CHECK(IsRegistryKey<CvArea>(key) || IsRegistryKey<CvCity>(key) || IsRegistryKey<CvDeal>(key) ||
                IsRegistryKey<CvLeague>(key) || IsRegistryKey<CvPlot>(key) || IsRegistryKey<CvUnit>(key) ||
                IsRegistryKey<CvPlayerAI>(key) || IsRegistryKey<CvTeam>(key) || IsRegistryKey<CvTeamTechs>(key));
        }
        lua_pop(L, 1);
    }
}
static lua_State* Open(LuaMemory& memory)
{
    auto* L = lua_newstate(LuaMemory::Allocate, &memory);
    CHECK(L);
    luaL_openlibs(L);
    lua_pushinteger(L, 719);
    return L;
}
static void Close(lua_State* L, LuaMemory& memory)
{
    memory.budget = -1;
    AssertRegistryKeys(L);
    lua_close(L);
    CHECK(memory.blocks == 0 && memory.bytes == 0);
}
template<class Binding, class Native> static int PushThunk(lua_State* L)
{
    Binding::Push(L, static_cast<Native*>(lua_touserdata(L, 1)));
    return 1;
}
template<class Binding, class Native> static bool Push(lua_State* L, Native* pointer, LuaMemory* memory = NULL, int budget = -1)
{
    const int top = lua_gettop(L);
    lua_pushcfunction(L, (PushThunk<Binding, Native>));
    lua_pushlightuserdata(L, pointer);
    if (memory) memory->budget = budget;
    const int status = lua_pcall(L, 1, 1, 0);
    if (memory) memory->budget = -1;
    CHECK(lua_gettop(L) == top + 1 && lua_tointeger(L, 1) == 719);
    return status == 0;
}
static int CityRead(lua_State* L)
{
    CvCity* city = CvLuaCity::GetInstance(L);
    lua_pushinteger(L, city->marker);
    return 1;
}
static bool ReadCity(lua_State* L, int table, int expected)
{
    table = ZeroSisLuaBorrowed::AbsoluteIndex(L, table);
    lua_pushcfunction(L, CityRead);
    lua_pushvalue(L, table);
    const int status = lua_pcall(L, 1, 1, 0);
    if (!status) CHECK(lua_tointeger(L, -1) == expected);
    lua_pop(L, 1);
    return status == 0;
}
static void RawPointer(lua_State* L, int table, const void* pointer)
{
    table = ZeroSisLuaBorrowed::AbsoluteIndex(L, table);
    lua_pushlightuserdata(L, const_cast<void*>(pointer));
    lua_setfield(L, table, "__instance");
}
static void Collect(lua_State* L)
{
    lua_gc(L, LUA_GCCOLLECT, 0);
    lua_gc(L, LUA_GCCOLLECT, 0);
}

static unsigned Basic()
{
    LuaMemory memory;
    auto* L = Open(memory);
    CvCity city; city.marker = 31;
    CvCity other; other.marker = 62;
    CvUnit unit;
    CHECK((Push<CvLuaCity>(L, &city)));
    const int live = lua_gettop(L);
    CHECK(CvLuaCity::GetInstance(L, live) == &city);
    CHECK(CvLuaCity::GetInstance(L, -1) == &city);
    CHECK(ReadCity(L, live, 31));
    lua_pushinteger(L, 901); lua_setfield(L, live, "custom");
    CHECK((Push<CvLuaCity>(L, &city)));
    CHECK(lua_rawequal(L, live, -1));
    lua_getfield(L, -1, "custom"); CHECK(lua_tointeger(L, -1) == 901); lua_pop(L, 2);
    unsigned accepted = 0;
    lua_newtable(L); RawPointer(L, -1, &city);
    accepted += CvLuaCity::GetInstance(L, -1, false) != NULL;
    CHECK((CvLuaCity::GetInstance(L, -1, false) != NULL) == !candidate); lua_pop(L, 1);
    CHECK((Push<CvLuaUnit>(L, &unit)));
    accepted += CvLuaCity::GetInstance(L, -1, false) != NULL;
    CHECK((CvLuaCity::GetInstance(L, -1, false) != NULL) == !candidate); lua_pop(L, 1);
    RawPointer(L, live, &other);
    accepted += CvLuaCity::GetInstance(L, live, false) != NULL;
    CHECK((CvLuaCity::GetInstance(L, live, false) != NULL) == !candidate);
    RawPointer(L, live, &city);
    // Metatable-provided pointers must never grant native access.
    lua_newtable(L); lua_newtable(L); lua_pushcfunction(L, UnexpectedIndex); lua_setfield(L, -2, "__index"); lua_setmetatable(L, -2);
    CHECK(CvLuaCity::GetInstance(L, -1, false) == NULL); lua_pop(L, 1);
    CHECK(metamethodCalls == (candidate ? 0u : 1u));
    if (candidate) CHECK(CvLuaCity::GetInstance(L, 0, false) == NULL);
    CHECK(CvLuaCity::GetInstance(L, 100, false) == NULL);
    CHECK((Push<CvLuaCity>(L, static_cast<CvCity*>(NULL)))); CHECK(lua_isnil(L, -1)); lua_pop(L, 1);
    // A forged object installed in the public cache must be replaced.
    lua_getglobal(L, CvLuaCity::GetTypeName()); lua_getfield(L, -1, "__instances");
    lua_pushlightuserdata(L, &other); lua_newtable(L); RawPointer(L, -1, &other);
    lua_pushinteger(L, 777); lua_setfield(L, -2, "forged"); lua_rawset(L, -3); lua_pop(L, 2);
    CHECK((Push<CvLuaCity>(L, &other)));
    lua_getfield(L, -1, "forged"); CHECK((lua_tointeger(L, -1) == 777) == !candidate); lua_pop(L, 2);
    // Caller-requested errors remain protected and leave the stack unchanged.
    RawPointer(L, live, NULL); CHECK(!ReadCity(L, live, 31)); RawPointer(L, live, &city);
    Close(L, memory); CHECK(Tracked() == 0);
    return accepted;
}

static unsigned Lifetimes()
{
    LuaMemory first, second;
    auto* A = Open(first); auto* B = Open(second);
    alignas(CvCity) unsigned char storage[sizeof(CvCity)];
    auto* city = new(storage) CvCity; city->marker = 11;
    CHECK((Push<CvLuaCity>(A, city))); CHECK((Push<CvLuaCity>(B, city)));
    const int old = lua_gettop(A);
    ZeroSisLuaBorrowed::Invalidate(city);
    CHECK((CvLuaCity::GetInstance(A, old, false) == NULL) == candidate);
    CHECK((CvLuaCity::GetInstance(B, -1, false) == NULL) == candidate);
    city->~CvCity(); city = new(storage) CvCity; city->marker = 22;
    CHECK((Push<CvLuaCity>(A, city)));
    CHECK((lua_rawequal(A, old, -1) != 0) == !candidate);
    CHECK(ReadCity(A, -1, 22));
    const unsigned stale = CvLuaCity::GetInstance(A, old, false) != NULL;
    CHECK(stale == (candidate ? 0u : 1u));
    {
        ZeroSisLuaBorrowed::InvalidationScope outer(city);
        CHECK((Push<CvLuaCity>(A, city)) == !candidate); lua_pop(A, 1);
        { ZeroSisLuaBorrowed::InvalidationScope nested(city); CHECK((Push<CvLuaCity>(A, city)) == !candidate); lua_pop(A, 1); }
        CHECK((Push<CvLuaCity>(A, city)) == !candidate); lua_pop(A, 1);
    }
    CHECK((Push<CvLuaCity>(A, city))); CHECK(ReadCity(A, -1, 22));
    Close(B, second); Close(A, first); CHECK(Tracked() == 0);
    city->~CvCity();
    return stale;
}

static unsigned AllocationFailures()
{
    unsigned failures = 0;
    bool passed = false;
    for (int budget = 0; budget < 256; ++budget)
    {
        LuaMemory memory; auto* L = Open(memory); CvCity city;
        const bool ok = Push<CvLuaCity>(L, &city, &memory, budget);
        lua_pop(L, 1);
        if (!ok) ++failures;
        else { CHECK(CvLuaCity::GetInstance(L, 1, false) == NULL); passed = true; }
        Collect(L);
        // Failed setup must be recoverable in the same VM.
        CHECK((Push<CvLuaCity>(L, &city)));
        lua_getglobal(L, CvLuaCity::GetTypeName()); lua_getfield(L, -1, "registered");
        const bool complete = lua_tointeger(L, -1) == 17;
        if (!complete) ++partialRegistrations;
        CHECK(complete || !candidate); lua_pop(L, 2);
        CHECK(CvLuaCity::GetInstance(L, -1, false) == &city);
        Close(L, memory); CHECK(Tracked() == 0);
        if (ok) break;
    }
    CHECK(passed && failures > 0);
    return failures;
}

static unsigned Reentrancy()
{
    unsigned rejected = 0;
    for (int action = 1; action <= (candidate ? 5 : 3); ++action)
    {
        LuaMemory memory; auto* L = Open(memory); CvCity city;
        if (action == 2)
        {
            lua_newuserdata(L, 1); lua_newtable(L);
            lua_pushlightuserdata(L, &city); lua_pushcclosure(L, InvalidateFinalizer, 1);
            lua_setfield(L, -2, "__gc"); lua_setmetatable(L, -2); lua_pop(L, 1);
        }
        registrationAction = action; invalidateDuringRegistration = &city;
        const bool ok = Push<CvLuaCity>(L, &city);
        rejected += !ok;
        CHECK(ok == (action < 3 && !candidate)); lua_pop(L, 1);
        if (action == 4) CHECK(nativeExceptionsDestroyed == 1);
        registrationAction = 0; invalidateDuringRegistration = NULL;
        CHECK((Push<CvLuaCity>(L, &city)));
        CHECK(CvLuaCity::GetInstance(L, -1, false) == &city);
        Close(L, memory); CHECK(Tracked() == 0);
    }
    return rejected;
}

template<class Binding, class Native> static unsigned IsNoneOne(lua_State* L, Native& native)
{
    CHECK((Push<Binding>(L, &native)));
    const int table = lua_gettop(L);
    unsigned errors = 0;
    for (int invalid = 0; invalid < 2; ++invalid)
    {
        if (invalid) ZeroSisLuaBorrowed::Invalidate(&native);
        lua_pushcfunction(L, Binding::lIsNone); lua_pushvalue(L, table);
        const int status = lua_pcall(L, 1, 1, 0);
        errors += status != 0;
        const bool correct = !status && lua_type(L, -1) == LUA_TBOOLEAN && lua_toboolean(L, -1) == invalid;
        if (!correct) ++isNoneIncorrect;
        if (candidate) CHECK(correct);
        lua_pop(L, 1);
    }
    lua_pop(L, 1);
    return errors;
}
static unsigned IsNone()
{
    LuaMemory memory; auto* L = Open(memory);
    CvCity city; CvUnit unit; CvArea area; CvPlot plot; CvLeague league; CvTeam team;
    unsigned errors = 0;
    errors += IsNoneOne<CvLuaCity>(L, city); errors += IsNoneOne<CvLuaUnit>(L, unit);
    errors += IsNoneOne<CvLuaArea>(L, area); errors += IsNoneOne<CvLuaPlot>(L, plot);
    errors += IsNoneOne<CvLuaLeague>(L, league); errors += IsNoneOne<CvLuaTeam>(L, team);
    Close(L, memory); CHECK(Tracked() == 0);
    return errors;
}
static void GarbageCollection()
{
    LuaMemory memory; auto* L = Open(memory);
    std::vector<CvCity> cities(1024);
    lua_gc(L, LUA_GCSTOP, 0);
    for (auto& city : cities) { CHECK((Push<CvLuaCity>(L, &city))); lua_pop(L, 1); }
    CHECK(Tracked() == (candidate ? 1024u : 0u));
    memory.budget = 0;
    Collect(L);
    CHECK(Tracked() == 0);
    memory.budget = -1;
    for (auto& city : cities) { CHECK((Push<CvLuaCity>(L, &city))); lua_pop(L, 1); }
    memory.budget = 0;
    lua_close(L);
    CHECK(memory.blocks == 0 && memory.bytes == 0 && Tracked() == 0);
}
static int LateInvalidation(lua_State* L)
{
    auto* request = static_cast<ZeroSisLuaBorrowed::Request<CvCity>*>(lua_touserdata(L, 1));
    lua_newtable(L); RawPointer(L, -1, request->pointer);
    ZeroSisLuaBorrowed::Attach(L, -1, request);
    ZeroSisLuaBorrowed::StoreResult(L, request);
    ZeroSisLuaBorrowed::Invalidate(request->pointer);
    return 0;
}
static int LatePush(lua_State* L)
{
    ZeroSisLuaBorrowed::Push(L, static_cast<CvCity*>(lua_touserdata(L, 1)), LateInvalidation);
    return 1;
}
static void PublicationFailure()
{
    LuaMemory memory; auto* L = Open(memory); CvCity city;
    lua_pushcfunction(L, LatePush); lua_pushlightuserdata(L, &city);
    CHECK(lua_pcall(L, 1, 1, 0) != 0); lua_pop(L, 1);
    Collect(L); CHECK(Tracked() == 0);
    Close(L, memory);
}
template<class Binding, class Native> static void OpaqueType(lua_State* L)
{
    Native native;
    CHECK((Push<Binding>(L, &native)));
    CHECK(Binding::GetInstance(L, -1, false) == &native);
    ZeroSisLuaBorrowed::Invalidate(&native);
    CHECK((Binding::GetInstance(L, -1, false) == NULL) == candidate);
    lua_pop(L, 1);
}
static void RemainingTypes()
{
    LuaMemory memory; auto* L = Open(memory);
    OpaqueType<CvLuaDeal, CvDeal>(L);
    OpaqueType<CvLuaPlayer, CvPlayerAI>(L);
    OpaqueType<CvLuaTeamTech, CvTeamTechs>(L);
    Close(L, memory); CHECK(Tracked() == 0);
}
static void ConcurrentMetadata()
{
    std::vector<std::thread> workers;
    for (unsigned worker = 0; worker < 8; ++worker)
        workers.emplace_back([] {
            LuaMemory memory; auto* L = Open(memory); CvCity city;
            for (unsigned iteration = 0; iteration < 64; ++iteration)
            {
                CHECK((Push<CvLuaCity>(L, &city)));
                CHECK(CvLuaCity::GetInstance(L, -1, false) == &city);
                ZeroSisLuaBorrowed::Invalidate(&city);
                CHECK((CvLuaCity::GetInstance(L, -1, false) == NULL) == candidate);
                lua_pop(L, 1);
                if (iteration % 16 == 0) Collect(L);
            }
            Close(L, memory);
        });
    for (auto& worker : workers) worker.join();
    CHECK(Tracked() == 0);
}
static void TokenFinalization()
{
    if (!candidate) return;
    LuaMemory memory; auto* L = Open(memory); CvCity city;
    CHECK((Push<CvLuaCity>(L, &city)));
    const int wrapper = lua_gettop(L);
    lua_pushlightuserdata(L, ZeroSisLuaBorrowed::RegistryKey<CvCity, 0>());
    lua_rawget(L, LUA_REGISTRYINDEX); lua_pushvalue(L, wrapper); lua_rawget(L, -2);
    const int token = lua_gettop(L);
    CHECK(lua_type(L, token) == LUA_TUSERDATA && Tracked() == 1);
    // A foreign full userdata must not be read as an intrusive native node.
    void* foreign = lua_newuserdata(L, sizeof(ZeroSisLuaBorrowed::Entry));
    std::memset(foreign, 0xA5, sizeof(ZeroSisLuaBorrowed::Entry));
    const int fake = lua_gettop(L);
    lua_getmetatable(L, token); lua_setmetatable(L, fake);
    lua_pushcfunction(L, ZeroSisLuaBorrowed::Finalize<CvCity>); lua_pushvalue(L, fake);
    CHECK(lua_pcall(L, 1, 0, 0) == 0 && Tracked() == 1);
    for (unsigned repeat = 0; repeat < 2; ++repeat)
    {
        lua_pushcfunction(L, ZeroSisLuaBorrowed::Finalize<CvCity>); lua_pushvalue(L, token);
        CHECK(lua_pcall(L, 1, 0, 0) == 0 && Tracked() == 0);
        CHECK(CvLuaCity::GetInstance(L, wrapper, false) == NULL);
    }
    lua_settop(L, 1);
    CHECK((Push<CvLuaCity>(L, &city)));
    memory.budget = 0;
    CHECK(CvLuaCity::GetInstance(L, -1, false) == &city);
    CHECK(CvLuaCity::GetInstance(L, -99, false) == NULL);
    memory.budget = -1;
    try { ZeroSisLuaBorrowed::InvalidationScope scope(&city); throw 17; }
    catch (int value) { CHECK(value == 17); }
    CHECK((Push<CvLuaCity>(L, &city)));
    CHECK(CvLuaCity::GetInstance(L, -1, false) == &city);
    Close(L, memory); CHECK(Tracked() == 0);
}
static int ProxyValue(CvDllCity& value) { return value.GetID(); }
static int ProxyValue(CvDllUnit& value) { return value.GetID(); }
static int ProxyValue(CvDllPlot& value) { return value.GetOwner(); }
static int ProxyValue(CvDllDeal& value) { return value.GetFromPlayer(); }
template<class Native, class Proxy, class Interface> static void Gateway(
    void (CvDllScriptSystemUtility::*push)(lua_State*, Interface*),
    Interface* (CvDllScriptSystemUtility::*get)(lua_State*, int, bool))
{
    LuaMemory memory; auto* L = Open(memory); Native native; native.marker = 77;
    {
        Proxy proxy(&native); CvDllScriptSystemUtility utility;
        CHECK(proxy.GetInstance() == &native && ProxyValue(proxy) == 77);
        (utility.*push)(L, &proxy); const int table = lua_gettop(L); CHECK(lua_istable(L, table));
        auto* roundtrip = (utility.*get)(L, table, false);
        CHECK(roundtrip && static_cast<Proxy*>(roundtrip)->GetInstance() == &native);
        delete roundtrip;
        if (candidate)
        {
            {
                ZeroSisLuaBorrowed::SuspensionScope change(&native);
                CHECK(proxy.GetInstance() == NULL);
                CHECK((utility.*get)(L, table, false) == NULL);
                bool rejected = false;
                try { (void)ProxyValue(proxy); } catch (const ZeroSisLuaBorrowed::InvalidNativeReference&) { rejected = true; }
                CHECK(rejected);
                native.marker = 88;
            }
            CHECK(proxy.GetInstance() == &native && ProxyValue(proxy) == 88);
            roundtrip = (utility.*get)(L, table, false);
            CHECK(roundtrip && static_cast<Proxy*>(roundtrip)->GetInstance() == &native); delete roundtrip;
            (utility.*push)(NULL, &proxy); CHECK((utility.*get)(NULL, 1, false) == NULL);
        }
        PeerInvalidate(&native);
        CHECK((proxy.GetInstance() == NULL) == candidate);
        (utility.*push)(L, &proxy); CHECK((lua_isnil(L, -1) != 0) == candidate); lua_pop(L, 1);
        roundtrip = (utility.*get)(L, table, false);
        CHECK((roundtrip == NULL) == candidate); delete roundtrip;
        if (candidate)
        {
            bool rejected = false;
            try { (void)ProxyValue(proxy); } catch (const ZeroSisLuaBorrowed::InvalidNativeReference&) { rejected = true; }
            CHECK(rejected);
        }
    }
    Close(L, memory); CHECK(Tracked() == 0);
}
static void NativeReferences()
{
    CHECK(PeerTracking() == &ZeroSisLuaBorrowed::State());
    CHECK((PeerCityRegistry() == ZeroSisLuaBorrowed::RegistryKey<CvCity, 0>()));
    {
        CvCity city; city.marker = 49;
        ZeroSisLuaBorrowed::NativeReference<CvCity> first(&city), copy(first), assigned;
        assigned = copy;
        CHECK(first.Get() == &city && copy->GetID() == 49 && (*assigned).marker == 49);
        PeerInvalidate(&city);
        CHECK(!first.Get() && !copy.Get() && !assigned.Get());
        ZeroSisLuaBorrowed::NativeReference<CvCity> fresh(&city);
        CHECK(fresh.Get() == &city && !first.Get());
        fresh.Reset(); CHECK(!fresh.Get());
    }
    CHECK(Tracked() == 0);
    Gateway<CvCity, CvDllCity>(&CvDllScriptSystemUtility::PushCvCityInstance, &CvDllScriptSystemUtility::GetCvCityInstance);
    Gateway<CvUnit, CvDllUnit>(&CvDllScriptSystemUtility::PushCvUnitInstance, &CvDllScriptSystemUtility::GetCvUnitInstance);
    Gateway<CvPlot, CvDllPlot>(&CvDllScriptSystemUtility::PushCvPlotInstance, &CvDllScriptSystemUtility::GetCvPlotInstance);
    Gateway<CvDeal, CvDllDeal>(&CvDllScriptSystemUtility::PushCvDealInstance, &CvDllScriptSystemUtility::GetCvDealInstance);
}
static void UnitDestruction()
{
    LuaMemory memory; auto* L = Open(memory);
    observedUnit = new CvUnit; observedUnit->marker = 61;
    observedUnit->m_iMapLayer = 3; observedUnit->m_iX = 5; observedUnit->m_iY = 9;
    CHECK((Push<CvLuaUnit>(L, observedUnit))); observedUnitLua = L; observedUnitTable = lua_gettop(L);
    GC.graphics = true;
    delete observedUnit;
    GC.graphics = false;
    CHECK(unitNotifications == 1 && unitMapRemovals == 1 && unitUninits == 1 && unitDestructions == 1);
    CHECK((retainedUnitProxy->GetInstance() == NULL) == candidate);
    CHECK((CvLuaUnit::GetInstance(L, observedUnitTable, false) == NULL) == candidate);
    delete retainedUnitProxy; retainedUnitProxy = NULL;
    observedUnit = NULL; observedUnitLua = NULL;
    Close(L, memory); CHECK(Tracked() == 0);
}
static unsigned dealSelfCopyLosses = 0, dealCopyCases = 0;
static void DealCopies()
{
    LuaMemory memory; auto* L = Open(memory);
    for (int count : {0, 1, 3, 32})
    {
        CvDeal source, target;
        source.m_eFromPlayer = 1; source.m_eToPlayer = 2;
        source.m_iDuration = 30; source.m_iFinalTurn = 85; source.m_iStartTurn = 55;
        source.m_ePeaceTreatyType = 3; source.m_eSurrenderingPlayer = 4;
        source.m_eDemandingPlayer = 5; source.m_eRequestingPlayer = 6;
        source.m_bConsideringForRenewal = true; source.m_bCheckedForRenewal = false; source.m_bDealCancelled = true;
        for (int i = 0; i < count; ++i) source.m_TradedItems.push_back(10 + i);
        CvDllDeal sourceProxy(&source), targetProxy(&target);
        CHECK((Push<CvLuaDeal>(L, &target))); const int table = lua_gettop(L);
        targetProxy.CopyFrom(&sourceProxy);
        CHECK(target.m_eFromPlayer == 1 && target.m_eToPlayer == 2);
        CHECK(target.m_iDuration == 30 && target.m_iFinalTurn == 85 && target.m_iStartTurn == 55);
        CHECK(target.m_ePeaceTreatyType == 3 && target.m_eSurrenderingPlayer == 4);
        CHECK(target.m_eDemandingPlayer == 5 && target.m_eRequestingPlayer == 6);
        CHECK(target.m_bConsideringForRenewal && !target.m_bCheckedForRenewal && target.m_bDealCancelled);
        CHECK(target.m_TradedItems == source.m_TradedItems);
        CHECK(CvLuaDeal::GetInstance(L, table, false) == &target);
        targetProxy.CopyFrom(&targetProxy); // The actual SDK gateway permits an alias to itself.
        if (count && target.m_TradedItems.empty()) ++dealSelfCopyLosses;
        CHECK(candidate ? target.m_TradedItems == source.m_TradedItems : target.m_TradedItems.empty());
        CHECK(CvLuaDeal::GetInstance(L, table, false) == &target);
        CHECK((Push<CvLuaDeal>(L, &target)));
        CHECK(lua_rawequal(L, table, -1));
        lua_settop(L, 1); ++dealCopyCases;
    }
    Close(L, memory); CHECK(Tracked() == 0);
}
template<class Binding, class Native, unsigned Capacity> static void ContainerLifetimes()
{
    LuaMemory memory; auto* L = Open(memory); Native value; value.marker = 71;
    int lastTable = 0; Native* lastPointer = NULL;
    {
        FStaticVector<Native, Capacity, false, c_eCiv5GameplayDLL> values;
        values.push_back(value);
        Native* first = &values[0];
        CHECK((Push<Binding>(L, first))); const int firstTable = lua_gettop(L);
        while (values.size() < Capacity) values.push_back(value);
        CHECK(&values[0] == first && Binding::GetInstance(L, firstTable, false) == first);
        ++containerOperations;
        values.push_back(value); // Actual SDK growth copies then destroys the old elements.
        CHECK(&values[0] != first && values.size() == Capacity + 1);
        CHECK((Binding::GetInstance(L, firstTable, false) == NULL) == candidate);
        ++containerOperations;
        Native* second = &values[0];
        CHECK((Push<Binding>(L, second))); const int secondTable = lua_gettop(L);
        values.clear();
        CHECK((Binding::GetInstance(L, secondTable, false) == NULL) == candidate);
        value.marker = 72; values.push_back(value);
        CHECK(&values[0] == second && values[0].marker == 72);
        CHECK((Push<Binding>(L, second))); const int reusedTable = lua_gettop(L);
        CHECK((lua_rawequal(L, secondTable, reusedTable) == 0) == candidate);
        ++containerOperations;
        FStaticVector<Native, Capacity, false, c_eCiv5GameplayDLL> replacement;
        value.marker = 73; replacement.push_back(value);
        values = replacement; // The actual assignment ends every old element's lifetime.
        CHECK(&values[0] == second && values[0].marker == 73);
        CHECK((Binding::GetInstance(L, reusedTable, false) == NULL) == candidate);
        CHECK((Push<Binding>(L, &values[0]))); const int assignedTable = lua_gettop(L);
        ++containerOperations;
        values.pop_back();
        CHECK(values.empty());
        CHECK((Binding::GetInstance(L, assignedTable, false) == NULL) == candidate);
        ++containerOperations;
        values.push_back(value); lastPointer = &values[0];
        CHECK((Push<Binding>(L, lastPointer))); lastTable = lua_gettop(L);
        CHECK(Binding::GetInstance(L, lastTable, false) == lastPointer);
    }
    CHECK((Binding::GetInstance(L, lastTable, false) == NULL) == candidate);
    ++containerOperations;
    Close(L, memory); CHECK(Tracked() == 0 && containerBlocks == 0);
}
int main()
{
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    const unsigned forged = Basic(), stale = Lifetimes();
    const unsigned allocations = AllocationFailures(), rejected = Reentrancy(), isNoneErrors = IsNone();
    GarbageCollection(); PublicationFailure(); RemainingTypes(); ConcurrentMetadata(); TokenFinalization();
    NativeReferences(); UnitDestruction();
    DealCopies();
    ContainerLifetimes<CvLuaDeal, CvDeal, 20>();
    ContainerLifetimes<CvLuaLeague, CvLeague, 2>();
    CHECK((isNoneIncorrect == 0) == candidate);
    std::printf("{\"candidate\":%s,\"checks\":%u,\"forged_accepted\":%u,\"stale_accepted\":%u,\"allocation_failures\":%u,\"partial_registrations\":%u,\"reentrant_rejections\":%u,\"is_none_errors\":%u,\"is_none_incorrect\":%u,\"native_proxy_kinds\":4,\"unit_notifications\":%u,\"cross_translation_unit_registry\":true,\"container_operations\":%u,\"container_blocks_at_exit\":%u,\"deal_copy_cases\":%u,\"deal_self_copy_losses\":%u,\"tracked_at_exit\":%zu}\n",
        candidate ? "true" : "false", checks.load(), forged, stale, allocations, partialRegistrations, rejected, isNoneErrors, isNoneIncorrect, unitNotifications, containerOperations, containerBlocks, dealCopyCases, dealSelfCopyLosses, Tracked());
    return 0;
}
