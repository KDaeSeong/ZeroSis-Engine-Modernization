#include "WorldBuilderMapWire.h"
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>
#include <stdexcept>
#include <thread>
using namespace ZeroSisWorldBuilder;
namespace { thread_local long long fault=-1;thread_local bool hit=false;std::atomic<long long> live(0);unsigned checks=0; }
void* operator new(std::size_t n) { if(fault>=0 && fault--==0){fault=-1;hit=true;throw std::bad_alloc();}void* p=std::malloc(n?n:1);if(!p)throw std::bad_alloc();++live;return p; }
void* operator new[](std::size_t n) { return ::operator new(n); }
void operator delete(void* p) noexcept { if(p){--live;std::free(p);} }
void operator delete[](void* p) noexcept { ::operator delete(p); }
void operator delete(void* p,std::size_t) noexcept { ::operator delete(p); }
void operator delete[](void* p,std::size_t) noexcept { ::operator delete(p); }
#define CHECK(x) do{++checks;if(!(x)){std::fprintf(stderr,"FAIL|%d|%s\n",__LINE__,#x);std::exit(2);}}while(0)
template<class F> void Reject(F f) { bool bad=false;try{f();}catch(const std::exception&){bad=true;}CHECK(bad); }
int main(int argc,char** argv) {
    CHECK(argc==2);FILE* f=nullptr;CHECK(!fopen_s(&f,argv[1],"rb") && f);CHECK(!std::fseek(f,0,SEEK_END));const long n=std::ftell(f);CHECK(n>0);std::rewind(f);
    MapBytes b(static_cast<std::size_t>(n));CHECK(std::fread(b.data(),1,b.size(),f)==b.size());CHECK(!std::fclose(f));
    const auto d=ReadMapDocument(b.data(),b.size(),true);CHECK(WriteMapDocument(d)==b);
    const auto baseline=live.load();
    for(std::size_t size=0;size<b.size();++size){Reject([&]{ReadMapDocument(b.data(),size,true);});CHECK(live==baseline);}
    Reject([&]{ReadMapDocument(nullptr,b.size());});
    {auto bad=b;bad.push_back(0);Reject([&]{ReadMapDocument(bad.data(),bad.size());});}
    for(const auto offset:{0,1,5,9,14,18,22,26,30,34,38}) {auto bad=b;bad[offset]=255;Reject([&]{ReadMapDocument(bad.data(),bad.size(),true);});}
    for(unsigned test=0;test<17;++test) {
        auto bad=d;
        switch(test) {
        case 0:bad.width=UINT32_MAX;break;
        case 1:bad.plots.pop_back();break;
        case 2:bad.playerCount=33;break;
        case 3:bad.speed.fill('x');break;
        case 4:bad.types[0].back()='x';break;
        case 5:bad.worldType.assign(65,0);break;
        case 6:bad.modData.pop_back();break;
        case 7:bad.units[0]=255;bad.units[1]=255;bad.units[2]=0;bad.units[3]=0;break;
        case 8:bad.units[4]=0;bad.units[5]=0;break; // allocated unit points to itself
        case 9:bad.units[4]=1;bad.units[5]=0;break; // points to a free unit
        case 10:bad.plotScenario[0]=1;bad.plotScenario[1]=0;break; // free city
        case 11:bad.units[6]=0;bad.units[7]=0;break; // absent custom-name record
        case 12:bad.visibility.pop_back();break;
        case 13:bad.influence.clear();break;
        case 14:bad.victories.back()='x';break;
        case 15:bad.plotScenario[0]=bad.plotScenario[1]=0;break; // duplicate city ownership
        case 16:bad.plotScenario[2]=bad.plotScenario[3]=0;break; // duplicate unit ownership
        }
        Reject([&]{WriteMapDocument(bad);});CHECK(WriteMapDocument(d)==b);
    }
    CHECK(live==baseline);
    Reject([&]{ReadMapDocument(b.data(),b.size(),true,static_cast<MapReadPolicy>(99));});
    // Fixture's unit-pool head is at byte 662, established by the original
    // SDK's write trace. Damage only that head, preserving all live unit data.
    MapBytes damaged=b;CHECK(damaged.size()>666);damaged[662]=254;damaged[663]=damaged[664]=damaged[665]=255;
    Reject([&]{ReadMapDocument(damaged.data(),damaged.size(),true);});
    {const auto recovered=ReadMapDocument(damaged.data(),damaged.size(),true,MapReadPolicy::RebuildInvalidFreeLists);CHECK(recovered.recoveredAllocators==1);CHECK(WriteMapDocument(recovered)==b);}
    {auto cycle=damaged;cycle[666]=cycle[667]=0;Reject([&]{ReadMapDocument(cycle.data(),cycle.size(),true,MapReadPolicy::RebuildInvalidFreeLists);});}
    const auto faultBaseline=live.load();unsigned failures=0,successes=0;
    for(unsigned op=0;op<3;++op) {
        bool success=false;
        for(long long index=0;index<1024 && !success;++index) {
            hit=false;fault=index;
            try{if(op==0){const auto decoded=ReadMapDocument(b.data(),b.size(),true);CHECK(decoded.width==4);}else if(op==1){const auto encoded=WriteMapDocument(d);CHECK(encoded==b);}else{const auto recovered=ReadMapDocument(damaged.data(),damaged.size(),true,MapReadPolicy::RebuildInvalidFreeLists);CHECK(recovered.recoveredAllocators==1);CHECK(WriteMapDocument(recovered)==b);}fault=-1;CHECK(!hit);success=true;++successes;}
            catch(const std::bad_alloc&){fault=-1;CHECK(hit);++failures;}
            CHECK(live==faultBaseline);CHECK(WriteMapDocument(d)==b);
        }
        CHECK(success);
    }
    std::atomic<unsigned> calls(0);
    {std::thread workers[4];for(auto& w:workers)w=std::thread([&]{for(unsigned i=0;i<32;++i){const auto parsed=ReadMapDocument(b.data(),b.size(),true);if(WriteMapDocument(parsed)==b)++calls;}});for(auto& w:workers)w.join();}
    CHECK(calls==128);CHECK(live==faultBaseline);
    std::printf("TRUNCATIONS|%zu\nFAULTS|%u|%u\nWORKERS|4|128\nPASS|%u\n",b.size(),failures,successes,checks);return 0;
}
