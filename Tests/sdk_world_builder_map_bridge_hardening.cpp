#include "map_fixture_bridge.h"
#include "SdkWorldBuilderMapBridge.h"
#include "sdk_world_builder_map_bridge_fault_host.h"
#include <atomic>
#include <thread>

namespace {thread_local long long fault=-1;thread_local bool hit=false;std::atomic<long long> live(0);}
void* operator new(size_t n){if(fault>=0 && fault--==0){fault=-1;hit=true;throw std::bad_alloc();}void* p=std::malloc(n?n:1);if(!p)throw std::bad_alloc();++live;return p;}
void* operator new[](size_t n){return ::operator new(n);}
void operator delete(void* p)noexcept{if(p){--live;std::free(p);}}
void operator delete[](void* p)noexcept{::operator delete(p);}
void operator delete(void* p,size_t)noexcept{::operator delete(p);}
void operator delete[](void* p,size_t)noexcept{::operator delete(p);}
using namespace ZeroSisWorldBuilder;
typedef CvWorldBuilderMap Map;
typedef CvWorldBuilderMapTypeDesc TypesDesc;
template<class F> static void Rejected(F action){bool rejected=false;try{action();}catch(const std::exception&){rejected=true;}CHECK(rejected);}
template<class T,uint N> static MapBytes PoolBytes(const CvWorldBuilderMapElementAllocator<T,N>& pool){MapBytes out(pool.GetSerializedSize());if(!out.empty())pool.Serialize(out.data());return out;}
struct Snapshot {
    MapBytes wire,units,cities,names;unsigned hash;
    Snapshot(const Map& m,const TypesDesc& t):wire(SaveMapBytes(m,t)),units(PoolBytes(m.m_kUnits)),cities(PoolBytes(m.m_kCities)),names(PoolBytes(m.m_kUnitNames)),hash(SemanticHash(m,NULL)){}
    bool Same(const Map& m,const TypesDesc& t)const{return wire==SaveMapBytes(m,t) && units==PoolBytes(m.m_kUnits) && cities==PoolBytes(m.m_kCities) && names==PoolBytes(m.m_kUnitNames) && hash==SemanticHash(m,NULL);}
};
static void Truncations(const MapBytes& input,const TypesDesc& types){
    std::unique_ptr<Map> m(new Map);Populate(*m);m->GetPlayer(0).m_uiGold=123456;const Snapshot before(*m,types);
    for(size_t n=0;n<input.size();++n){Rejected([&]{LoadMapBytes(*m,input.data(),n,types);});CHECK(before.Same(*m,types));}
    Rejected([&]{LoadMapBytes(*m,NULL,input.size(),types);});CHECK(before.Same(*m,types));
    MapBytes bad=input;bad.push_back(0);Rejected([&]{LoadMapBytes(*m,bad.data(),bad.size(),types);});CHECK(before.Same(*m,types));
    for(unsigned v:{0u,5u,8u,13u,127u}){bad=input;bad[0]=static_cast<byte>(v|128);Rejected([&]{LoadMapBytes(*m,bad.data(),bad.size(),types);});CHECK(before.Same(*m,types));}
    bad=input;std::memset(bad.data()+1,255,4);Rejected([&]{LoadMapBytes(*m,bad.data(),bad.size(),types);});CHECK(before.Same(*m,types));
    std::printf("TRUNCATIONS|%u|state_preserved\n",static_cast<uint>(input.size()));
}
static void Faults(const MapBytes& input,const TypesDesc& types){
    unsigned failures=0,successes=0;
    for(unsigned operation=0;operation<3;++operation){bool completed=false;
        for(long long index=0;index<2048 && !completed;++index){const long long baseline=live;
            {
                std::unique_ptr<Map> m(new Map);Populate(*m);m->GetPlayer(0).m_uiGold=123456;const Snapshot before(*m,types);
                fault=index;hit=false;bool failed=false;MapBytes saved;
                try{if(operation==2)saved=SaveMapBytes(*m,types);else LoadMapBytes(*m,input.data(),input.size(),types,operation==0);}
                catch(const std::bad_alloc&){failed=true;}fault=-1;CHECK(failed==hit);
                if(failed){++failures;CHECK(before.Same(*m,types));}else{++successes;completed=true;if(operation==2)CHECK(saved==before.wire);else if(operation==0)CHECK(m->GetPlayer(0).m_uiGold==100);else CHECK(m->GetPlayer(0).m_uiGold==123456);}
            }
            CHECK(live==baseline);
        }CHECK(completed);
    }
    std::printf("FAULTS|%u|%u|cpp_new_failures_preserve_state_and_pool_bytes\n",failures,successes);
}
static void Io(const MapBytes& input,const TypesDesc& types){
    InstallFaultMapFileHost();std::unique_ptr<Map> m(new Map);Populate(*m);m->GetPlayer(0).m_uiGold=123456;const Snapshot before(*m,types);
    const MapIoFault readFailures[]={MapIoFault::CreateNull,MapIoFault::CreateClosed,MapIoFault::CreateThrow,MapIoFault::ReadZero,MapIoFault::ReadOver,MapIoFault::ReadThrow,MapIoFault::CloseBad,MapIoFault::CloseThrow,MapIoFault::LengthZero,MapIoFault::LengthThrow};
    for(auto f:readFailures){worldMapFile=input;mapIo=MapIoControl();mapIo.fault=f;mapIo.chunk=7;mapIo.failAfter=7;CHECK(!m->Load(L"memory",types));CHECK(!mapIo.live);CHECK(before.Same(*m,types));
        worldMapFile=input;mapIo=MapIoControl();mapIo.fault=f;mapIo.chunk=7;mapIo.failAfter=7;CHECK(Map::PreviewPlayableCivCount(L"memory")==0);CHECK(!mapIo.live);}
    mapIo=MapIoControl();CHECK(!m->Load(NULL,types));CHECK(!m->Load(L"",types));CHECK(!m->Save(NULL,types));CHECK(!m->Save(L"",types));CHECK(!Map::PreviewPlayableCivCount(NULL));CHECK(!mapIo.created);
    for(uint n=0;n<10;++n){worldMapFile.assign(n,0);CHECK(!Map::PreviewPlayableCivCount(L"memory"));CHECK(!mapIo.live);}
    worldMapFile=input;mapIo=MapIoControl();mapIo.chunk=7;CHECK(m->Load(L"memory",types));CHECK(!mapIo.live);CHECK(mapIo.closed==1);CHECK(Map::PreviewPlayableCivCount(L"memory")==2);
    const Snapshot loaded(*m,types);const MapIoFault writeFailures[]={MapIoFault::CreateNull,MapIoFault::CreateClosed,MapIoFault::CreateThrow,MapIoFault::WriteZero,MapIoFault::WriteOver,MapIoFault::WriteThrow,MapIoFault::CloseBad,MapIoFault::CloseThrow};
    for(auto f:writeFailures){worldMapFile=input;mapIo=MapIoControl();mapIo.fault=f;mapIo.chunk=7;mapIo.failAfter=7;CHECK(!m->Save(L"memory",types));CHECK(!mapIo.live);CHECK(loaded.Same(*m,types));}
    mapIo=MapIoControl();mapIo.chunk=7;CHECK(m->Save(L"memory",types));CHECK(worldMapFile==loaded.wire);CHECK(!mapIo.live);CHECK(mapIo.closed==1);
    // Invalid native state must fail before opening/truncating a destination.
    const auto u=m->GetPlotScenarioData(5).m_hUnitStack;m->m_kUnits[u]->m_hStackedUnit=u;mapIo=MapIoControl();worldMapFile=input;
    CHECK(!m->Save(L"memory",types));CHECK(!mapIo.created);CHECK(worldMapFile==input);m->m_kUnits[u]->m_hStackedUnit=Map::Unit::Handle();
    const auto c=m->GetPlotScenarioData(7).m_hCity;m->GetPlotScenarioData(0).m_hCity=c;CHECK(!m->Save(L"memory",types));CHECK(!mapIo.created);CHECK(worldMapFile==input);m->GetPlotScenarioData(0).m_hCity=Map::City::Handle();
    CHECK(loaded.Same(*m,types));std::printf("IO|10_read_preview_faults|8_write_faults|7_byte_chunks|invalid_before_open\n");
    InstallWorldMapFileHost();MapBytes().swap(worldMapFile);
}
static void LegacyVisibility(const MapBytes& input,const TypesDesc& types){
    MapDocument d=ReadMapDocument(input.data(),input.size());d.version=9;d.worldType.clear();d.influence.clear();d.units.clear();d.unitNames.clear();d.cities.clear();
    for(size_t i=0;i<d.plotScenario.size();i+=8)std::memset(d.plotScenario.data()+i,255,4);
    for(size_t i=0;i<d.visibility.size();++i)d.visibility[i]=static_cast<byte>(0xa5u^(i*37));const MapBytes bytes=WriteMapDocument(d);
    std::unique_ptr<Map> m(new Map);Populate(*m);for(uint i=0;i<32;++i)for(uint j=0;j<64;++j)m->m_aiCityStateInfluence[i][j]=-static_cast<int>(i*64+j+1);
    CHECK(LoadMapBytes(*m,bytes.data(),bytes.size(),types).sourceVersion==9);
    for(uint t=0;t<d.teamCount;++t)for(uint y=0;y<d.height;++y)for(uint x=0;x<d.width;++x){const size_t bit=x+y*d.width+t*d.width*d.height;CHECK(m->GetVisibility(x,y,t)==((d.visibility[bit/8]>>(bit%8))&1));}
    for(uint i=0;i<32;++i)for(uint j=0;j<64;++j)CHECK(m->m_aiCityStateInfluence[i][j]==-static_cast<int>(i*64+j+1));
    const auto saved=SaveMapBytes(*m,types);std::unique_ptr<Map> copy(new Map);LoadMapBytes(*copy,saved.data(),saved.size(),types);CHECK(SemanticHash(*m,NULL)==SemanticHash(*copy,NULL));
    std::printf("LEGACY9|60_wire_visibility_bits|2048_prior_influence_values|v12_roundtrip\n");
}
static void Workers(const MapBytes& input,const TypesDesc& types){
    std::unique_ptr<Map> expected(new Map);LoadMapBytes(*expected,input.data(),input.size(),types);const auto saved=SaveMapBytes(*expected,types);const unsigned hash=SemanticHash(*expected,NULL);
    std::atomic<unsigned> calls(0),failures(0);std::thread threads[4];
    for(auto& thread:threads)thread=std::thread([&]{try{for(unsigned i=0;i<32;++i){std::unique_ptr<Map> m(new Map);LoadMapBytes(*m,input.data(),input.size(),types);
        if(SaveMapBytes(*m,types)!=saved || SemanticHash(*m,NULL)!=hash)throw std::runtime_error("Independent bridge state differs");++calls;}}catch(...){++failures;}});
    for(auto& thread:threads)thread.join();CHECK(!failures);CHECK(calls==128);std::printf("WORKERS|4|128_independent_maps|load_save_state_equal\n");
}
int main(int argc,char** argv){
    (void)&Dump;CHECK(argc==2);FILE* file=std::fopen(argv[1],"rb");CHECK(file!=NULL);CHECK(!std::fseek(file,0,SEEK_END));const long n=std::ftell(file);CHECK(n>0);std::rewind(file);
    // Type strings are deliberately interned for process lifetime by the
    // existing provider. Establish that fixture palette before leak accounting.
    {TypesDesc warm;Types(warm);}const long long baseline=live;
    {MapBytes input(n);CHECK(std::fread(input.data(),1,input.size(),file)==input.size());CHECK(!std::fclose(file));TypesDesc types;Types(types);SourceTypes(types,input);
        Truncations(input,types);Faults(input,types);Io(input,types);LegacyVisibility(input,types);Workers(input,types);}
    CHECK(live==baseline);std::printf("ALLOCATIONS|%lld|%lld|process_lifetime_palette_baseline\n",live.load(),baseline);std::printf("PASS|%u\n",checks);
}
