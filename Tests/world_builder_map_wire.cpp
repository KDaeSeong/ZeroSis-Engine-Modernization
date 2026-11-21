#include "WorldBuilderMapWire.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <stdexcept>
using namespace ZeroSisWorldBuilder;
static std::uint32_t Hash(const MapBytes& b) { std::uint32_t h=2166136261u;for(auto v:b){h^=v;h*=16777619u;}return h; }
static void Block(const char* name,const MapBytes& b) { std::printf("BLOCK|%s|%zu|%08x\n",name,b.size(),Hash(b)); }
static MapBytes Read(const char* name) {
    FILE* f=nullptr;if(fopen_s(&f,name,"rb") || !f)throw std::runtime_error("open input");
    if(std::fseek(f,0,SEEK_END))throw std::runtime_error("seek input");const long n=std::ftell(f);if(n<0)throw std::runtime_error("size input");
    std::rewind(f);MapBytes b(static_cast<std::size_t>(n));const auto got=std::fread(b.data(),1,b.size(),f);std::fclose(f);if(got!=b.size())throw std::runtime_error("read input");return b;
}
int main(int argc,char** argv) {
    if(argc<3)return 2;
    try {
        const auto b=Read(argv[1]);const bool recover=argc>3 && std::strcmp(argv[3],"recover")==0;
        auto d=ReadMapDocument(b.data(),b.size(),false,recover?MapReadPolicy::RebuildInvalidFreeLists:MapReadPolicy::Strict);
        const bool mutate=argc>3 && std::strcmp(argv[3],"mutate")==0;
        if(mutate) { d.flags^=1;d.maxTurns+=7;const char name[]="Changed map name longer than original";d.name.assign(name,name+sizeof(name));if(!d.plots.empty())d.plots[7]=23; }
        const auto out=WriteMapDocument(d);
        if(!mutate && !d.recoveredAllocators && b!=out)throw std::runtime_error("wire roundtrip differs");
        FILE* f=nullptr;if(fopen_s(&f,argv[2],"wb") || !f)throw std::runtime_error("open output");
        const auto written=std::fwrite(out.data(),1,out.size(),f);const auto close=std::fclose(f);if(written!=out.size() || close)throw std::runtime_error("write output");
        std::printf("SUMMARY|%u|%u|%u|%u|%u\n",d.width,d.height,d.playerCount,d.cityStateCount,d.teamCount);
        std::printf("HEADER|%u|%u|%u|%u|%u|%u|%u|%u\n",d.version,unsigned(d.hasScenario),d.playable,d.flags,unsigned(d.hasScenario),d.startingTurn,d.maxTurns,d.startYearBits);
        std::printf("RECOVERY|%u\n",d.recoveredAllocators);
        const char* names[]={"terrain","feature","wonder","resource","improvement","unit","tech","policy","building","promotion"};
        for(unsigned i=0;i<10;++i)Block(names[i],d.types[i]);
        Block("mod",d.modData);Block("name",d.name);Block("description",d.description);Block("world",d.worldType);Block("plots",d.plots);
        Block("units",d.units);Block("unit_names",d.unitNames);Block("cities",d.cities);Block("victories",d.victories);Block("options",d.options);
        for(unsigned i=0;i<5;++i){char name[20];sprintf_s(name,"relationship_%u",i);Block(name,d.relationships[i]);}
        Block("influence",d.influence);Block("visibility",d.visibility);Block("teams",d.teams);Block("players",d.players);Block("city_states",d.cityStates);Block("plot_scenario",d.plotScenario);
        std::printf("PASS|1\n");return 0;
    }catch(const std::exception& e){std::fprintf(stderr,"REJECT|%s\n",e.what());return 3;}
}
