#include "map_fixture_operations.h"
#include "SdkWorldBuilderMapPool.h"
#include <atomic>
#include <thread>
#include <limits>

namespace {thread_local long long fault=-1;thread_local bool hit=false;std::atomic<long long> live(0);}
void* operator new(size_t n){if(fault>=0 && fault--==0){fault=-1;hit=true;throw std::bad_alloc();}void* p=std::malloc(n?n:1);if(!p)throw std::bad_alloc();++live;return p;}
void* operator new[](size_t n){return ::operator new(n);}
void operator delete(void* p)noexcept{if(p){--live;std::free(p);}}
void operator delete[](void* p)noexcept{::operator delete(p);}
void operator delete(void* p,size_t)noexcept{::operator delete(p);}
void operator delete[](void* p,size_t)noexcept{::operator delete(p);}

typedef CvWorldBuilderMap Map;
typedef ZeroSisWorldBuilderMapPoolAccess Pool;
template<class F> static void Rejected(F action){bool rejected=false;try{action();}catch(const std::exception&){rejected=true;}CHECK(rejected);}
template<class T,uint N> static std::vector<byte> PoolBytes(const CvWorldBuilderMapElementAllocator<T,N>& p){std::vector<byte> bytes(p.GetSerializedSize());if(!bytes.empty())p.Serialize(bytes.data());return bytes;}
struct Snapshot {
    unsigned hash;std::vector<byte> units,cities,names;
    explicit Snapshot(const Map& m):hash(SemanticHash(m,NULL)),units(PoolBytes(m.m_kUnits)),cities(PoolBytes(m.m_kCities)),names(PoolBytes(m.m_kUnitNames)){}
    bool Same(const Map& m)const{return hash==SemanticHash(m,NULL) && units==PoolBytes(m.m_kUnits) && cities==PoolBytes(m.m_kCities) && names==PoolBytes(m.m_kUnitNames);}
};
static void Boundaries(){
    std::unique_ptr<Map> m(new Map);Populate(*m);const Snapshot before(*m);
    const uint sizes[][2]={{UINT_MAX,2},{2,UINT_MAX},{32769,0},{0,32769},{32768,2},{32768,32768}};
    for(const auto& size:sizes){Rejected([&]{m->Resize(size[0],size[1]);});CHECK(before.Same(*m));}
    m->Resize(32768,1);CHECK(m->GetPlotCount()==32768);m->Resize(0,0);CHECK(!m->GetPlotCount());m->Resize(4,3);CHECK(before.Same(*m));
    const std::string limit(63,'a'),over(64,'b');m->SetWorldType(limit.c_str());m->SetDefaultGameSpeed(limit.c_str());const Snapshot names(*m);
    Rejected([&]{m->SetWorldType(over.c_str());});Rejected([&]{m->SetDefaultGameSpeed(over.c_str());});Rejected([&]{m->SetWorldType(NULL);});Rejected([&]{m->SetDefaultGameSpeed(NULL);});CHECK(names.Same(*m));
    m->SetWorldType(m->GetWorldType()+1);CHECK(std::strlen(m->GetWorldType())==62);m->SetDefaultGameSpeed(m->GetDefaultGameSpeed()+2);CHECK(std::strlen(m->GetDefaultGameSpeed())==61);
    Map::OldUnit old;const float bad[]={-1.0f,std::numeric_limits<float>::infinity(),std::numeric_limits<float>::quiet_NaN(),std::numeric_limits<float>::max()};
    for(float value:bad){old.m_fHealth=value;Rejected([&]{Map::Unit converted(old);});}
    old.m_fHealth=1.5f;CHECK(Map::Unit(old).m_uiHealth==150000);
    Map::OldCity city;city.m_uiPopulation=65536;Rejected([&]{Map::City converted(city);});city.m_uiPopulation=65535;CHECK(Map::City(city).m_wPopulation==65535);
    std::memset(city.m_szName,'x',sizeof(city.m_szName));Rejected([&]{Map::City converted(city);});
    Map::OldPlayer player;std::memset(player.m_szHandicap,'x',sizeof(player.m_szHandicap));Rejected([&]{Map::Player converted(player);});
    const Snapshot swaps(*m);Rejected([&]{m->SwapPlayers(0,3);});Rejected([&]{m->SwapCityStates(2,0);});CHECK(swaps.Same(*m));
    m->SwapPlayers(1,1);m->SwapCityStates(0,0);CHECK(swaps.Same(*m));
    std::printf("BOUNDARIES|dimensions|fixed_names|legacy_conversions|swap_indices\n");
}
static void Ownership(){
    std::unique_ptr<Map> m(new Map);m->Resize(2,2);m->SetPlayerCount(2);m->SetCityStateCount(1);
    Map::Unit::Handle a=m->AddUnit(0,0),b=m->AddUnit(0,0);CHECK(a.Valid() && b.Valid());const Snapshot before(*m);
    CHECK(!m->AddUnit(2,0).Valid());CHECK(!m->RemoveUnit(1,1,a));CHECK(a.Valid());CHECK(before.Same(*m));
    Rejected([&]{m->RemoveUnit(0,0,m->GetPlotScenarioData(0).m_hUnitStack);});
    Rejected([&]{m->RemoveUnit(0,0,m->m_kUnits[b]->m_hStackedUnit);});CHECK(before.Same(*m));
    m->GetPlotScenarioData(1).m_hUnitStack=b;const Snapshot shared(*m);Rejected([&]{m->SwapPlayers(0,1);});Rejected([&]{m->AddUnit(0,0);});Rejected([&]{m->RemoveUnit(0,0,b);});CHECK(shared.Same(*m));m->GetPlotScenarioData(1).m_hUnitStack=Map::Unit::Handle();
    m->m_kUnits[a]->m_hStackedUnit=b;const std::vector<byte> cyclic=PoolBytes(m->m_kUnits);
    Rejected([&]{m->AddUnit(0,0);});Rejected([&]{m->RemoveUnit(0,0,a);});Rejected([&]{m->SwapPlayers(0,1);});CHECK(cyclic==PoolBytes(m->m_kUnits));CHECK(m->GetPlotScenarioData(0).m_hUnitStack==b);
    m->m_kUnits[a]->m_hStackedUnit=Map::Unit::Handle();CHECK(before.Same(*m));
    Map::Unit::Handle stale=b;m->m_kUnits.Free(stale);const std::vector<byte> freed=PoolBytes(m->m_kUnits);
    Rejected([&]{m->AddUnit(0,0);});Rejected([&]{m->RemoveUnit(0,0,b);});CHECK(freed==PoolBytes(m->m_kUnits));
    m->GetPlotScenarioData(0).m_hUnitStack=a;m->ClearScenarioData();CHECK(!m->m_kUnits.GetSerializedSize());
    Populate(*m);m->Resize(1,1);m->ClearScenarioData();m->Resize(4,3);CHECK(!m->GetPlotScenarioData(5).m_hUnitStack.Valid());CHECK(!m->GetPlotScenarioData(7).m_hCity.Valid());
    Map::Unit::Handle fresh=m->AddUnit(1,1);CHECK(fresh.Valid());CHECK(m->m_kUnits[fresh]->m_hStackedUnit==Map::Unit::Handle());
    std::printf("OWNERSHIP|wrong_plot|alias|shared|cycle|freed|hidden_clear\n");
}
static void Capacity(){
    std::unique_ptr<Map> m(new Map);m->Resize(1,1);Map::Unit::Handle last;
    for(uint i=0;i<65535;++i){last=Pool::Allocate(m->m_kUnits);CHECK(last.Valid());CHECK(last.ToWord()==i);}
    m->m_kUnits[last]->m_uiExperience=1984;CHECK(!m->AddUnit(0,0).Valid());CHECK(!m->GetPlotScenarioData(0).m_hUnitStack.Valid());CHECK(m->m_kUnits[last]->m_uiExperience==1984);
    Map::Unit::Handle spare=Pool::Handle<Map::Unit::Handle>(32768);m->m_kUnits.Free(spare);Map::Unit::Handle reused=m->AddUnit(0,0);CHECK(reused.ToWord()==32768);CHECK(m->m_kUnits[reused]->m_uiExperience==0);
    CHECK(Pool::Allocated(m->m_kUnits).size()==65535);std::printf("CAPACITY|65535_unique_handles|exhaustion|reuse\n");
}
static void Faults(){
    unsigned failures=0,successes=0;
    for(unsigned operation=0;operation<4;++operation){bool completed=false;
        for(long long index=0;index<128 && !completed;++index){const long long baseline=live;
            {
                std::unique_ptr<Map> m(new Map);Populate(*m);Map::Unit::Handle unit=m->GetPlotScenarioData(5).m_hUnitStack;const Snapshot before(*m);
                fault=index;hit=false;bool failed=false;
                try{if(operation==0)CHECK(m->AddUnit(1,1).Valid());else if(operation==1)CHECK(m->RemoveUnit(1,1,unit));else if(operation==2)m->SwapPlayers(0,2);else m->SwapCityStates(0,1);}
                catch(const std::bad_alloc&){failed=true;}fault=-1;CHECK(failed==hit);
                if(failed){++failures;CHECK(before.Same(*m));CHECK(unit.Valid());}else{++successes;completed=true;}
            }
            CHECK(live==baseline);
        }CHECK(completed);
    }
    std::printf("FAULTS|%u|%u|cpp_new_failures_preserve_state_and_pool_bytes\n",failures,successes);
}
static void Workers(){
    std::atomic<unsigned> calls(0),failures(0);std::thread threads[4];
    for(unsigned t=0;t<4;++t)threads[t]=std::thread([&]{
        try{for(unsigned i=0;i<64;++i){std::unique_ptr<Map> m(new Map);m->Resize(8,8);m->SetPlayerCount(2);m->SetCityStateCount(1);
            for(uint x=0;x<8;++x){Map::Unit::Handle u=m->AddUnit(x,0);if(!u.Valid())throw std::runtime_error("Worker unit allocation");m->m_kUnits[u]->m_byOwner=0;m->m_kUnits[u]->m_uiExperience=i*8+x;}
            m->SwapPlayers(0,1);for(uint x=0;x<8;++x){Map::Unit::Handle u=m->GetPlotScenarioData(x,0).m_hUnitStack;
                if(m->m_kUnits[u]->m_byOwner!=1 || m->m_kUnits[u]->m_uiExperience!=i*8+x || !m->RemoveUnit(x,0,u) || u.Valid())throw std::runtime_error("Worker state mismatch");}
            m->ClearScenarioData();if(m->m_kUnits.GetSerializedSize())throw std::runtime_error("Worker pool release");++calls;}}
        catch(...){++failures;}
    });
    for(auto& thread:threads)thread.join();CHECK(!failures);CHECK(calls==256);std::printf("WORKERS|4|256_independent_maps|2048_units\n");
}
int main(){(void)&Types;(void)&SourceTypes;(void)&Dump;Boundaries();Ownership();Capacity();Faults();Workers();CHECK(live==0);std::printf("PASS|%u\n",checks);}
