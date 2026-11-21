#include "WorldBuilderMapWire.h"
#include "SdkWorldBuilderModDataWire.h"
#include <algorithm>
#include <cstring>
#include <limits>
#include <stdexcept>

namespace ZeroSisWorldBuilder {
namespace {
void Require(bool condition,const char* message) { if(!condition)throw std::invalid_argument(message); }
bool Supported(unsigned v) { return v==6 || v==7 || v==9 || v==10 || v==11 || v==12; }
std::uint32_t WordAt(const unsigned char* p) { return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24); }
unsigned HandleAt(const unsigned char* p) { return unsigned(p[0])|(unsigned(p[1])<<8); }
std::size_t PlotCount(const MapDocument& d) {
    Require(d.width<=32768 && d.height<=32768 && std::uint64_t(d.width)*d.height<=32768,"Map dimensions exceed SDK capacity");
    return std::size_t(d.width)*d.height;
}
std::size_t RelationSize(unsigned teams) { return (teams*(teams?teams-1:0)/2+7)/8; }
struct Reader {
    const unsigned char* p;std::size_t size,at=0;
    Reader(const void* data,std::size_t n):p(static_cast<const unsigned char*>(data)),size(n) {
        Require(data!=nullptr,"Null map file");Require(n<=UINT32_MAX,"Map file exceeds 32-bit file contract");
    }
    void Need(std::size_t n) const { Require(n<=size-at,"Truncated map file"); }
    unsigned char Byte() { Need(1);return p[at++]; }
    std::uint32_t Word() { Need(4);const auto result=WordAt(p+at);at+=4;return result; }
    MapBytes Bytes(std::size_t n) { Need(n);MapBytes out(p+at,p+at+n);at+=n;return out; }
    void Fixed(unsigned char* out,std::size_t n) { Need(n);std::memcpy(out,p+at,n);at+=n; }
};
void PutWord(MapBytes& out,std::uint32_t value) { for(unsigned i=0;i<4;++i)out.push_back(static_cast<unsigned char>(value>>(8*i))); }
void Append(MapBytes& out,const MapBytes& bytes) {
    Require(bytes.size()<=UINT32_MAX-out.size(),"Map output exceeds file capacity");out.insert(out.end(),bytes.begin(),bytes.end());
}
void PutSize(MapBytes& out,const MapBytes& bytes) { Require(bytes.size()<=UINT32_MAX,"Map section exceeds file capacity");PutWord(out,static_cast<std::uint32_t>(bytes.size())); }
void Terminated(const unsigned char* p,std::size_t n,const char* message) { Require(n && std::memchr(p,0,n)!=nullptr,message); }
void Text(const MapBytes& bytes) { if(!bytes.empty())Terminated(bytes.data(),bytes.size(),"Unterminated map text"); }
void Palette(const MapBytes& bytes) { Require(bytes.empty() || bytes.back()==0,"Unterminated map type palette"); }
void Groups(const MapBytes& bytes) {
    std::size_t p=0;
    while(p<bytes.size()) { const unsigned n=bytes[p++];Require(n>0 && n<bytes.size()-p,"Truncated map type group");
        Require(bytes[p+n]==0 && std::memchr(bytes.data()+p,0,n)==nullptr,"Invalid map type group string");p+=n+1; }
}
// Allocator format is a signed 32-bit free-list head followed by fixed-size
// records. The free-list uses record indices and -1, independently of pointer size.
std::size_t Slots(const MapBytes& bytes,std::size_t stride) {
    if(bytes.empty())return 0;
    Require(bytes.size()>=4 && (bytes.size()-4)%stride==0,"Invalid map allocator record size");
    const auto count=(bytes.size()-4)/stride;Require(count>0 && count<=65535,"Map allocator exceeds handle range");
    return count;
}
std::vector<bool> Live(const MapBytes& bytes,std::size_t stride) {
    const auto count=Slots(bytes,stride);if(!count)return {};
    std::vector<bool> result(count,true);std::uint32_t next=WordAt(bytes.data());
    while(next!=UINT32_MAX) { Require(next<count && result[next],"Invalid or cyclic map free list");result[next]=false;next=WordAt(bytes.data()+4+std::size_t(next)*stride); }
    return result;
}
void Handle(unsigned value,const std::vector<bool>& live) { Require(value==65535 || (value<live.size() && live[value]),"Map handle references absent or free record"); }
void ScenarioRecords(const MapDocument& d) {
    const auto unitStride=MapUnitStride(d.version),cityStride=MapCityStride(d.version),playerStride=MapPlayerStride(d.version);
    const auto units=Live(d.units,unitStride),cities=Live(d.cities,cityStride),names=Live(d.unitNames,64);
    std::vector<unsigned> next(units.size(),65535);
    for(std::size_t i=0;i<units.size();++i)if(units[i]) {
        const auto p=d.units.data()+4+i*unitStride;next[i]=HandleAt(p);Handle(next[i],units);
        if(d.version>=9)Handle(HandleAt(p+2),names);
    }
    // Each directed unit chain is checked once; malicious cycles cannot hang a loader.
    std::vector<unsigned char> color(units.size(),0);
    for(std::size_t i=0;i<units.size();++i)if(units[i] && color[i]==0) {
        std::size_t p=i;
        while(p!=65535 && color[p]==0) { color[p]=1;p=next[p]; }
        Require(p==65535 || color[p]!=1,"Cyclic map unit stack");p=i;
        while(p!=65535 && color[p]==1) { color[p]=2;p=next[p]; }
    }
    for(std::size_t i=0;i<cities.size();++i)if(cities[i])Terminated(d.cities.data()+4+i*cityStride,d.version>=9?64:56,"Unterminated map city name");
    for(std::size_t i=0;i<names.size();++i)if(names[i])Terminated(d.unitNames.data()+4+i*64,64,"Unterminated map unit name");
    std::vector<bool> placedUnits(units.size(),false),placedCities(cities.size(),false);
    for(std::size_t p=0;p<d.plotScenario.size();p+=8) {
        const unsigned city=HandleAt(d.plotScenario.data()+p);unsigned unit=HandleAt(d.plotScenario.data()+p+2);
        Handle(city,cities);Handle(unit,units);
        if(city!=65535){Require(!placedCities[city],"City belongs to multiple plots");placedCities[city]=true;}
        while(unit!=65535){Require(!placedUnits[unit],"Unit belongs to multiple plot stacks");placedUnits[unit]=true;unit=next[unit];}
    }
    for(std::size_t p=0;p<d.teams.size();p+=64)Terminated(d.teams.data()+p,32,"Unterminated map team name");
    for(const MapBytes* block:{&d.players,&d.cityStates})for(std::size_t p=0;p<block->size();p+=playerStride) {
        const auto strings=block->data()+p+32;
        const unsigned count=d.version>=9?6:4;
        for(unsigned i=0;i<count;++i)Terminated(strings+i*64,d.version<9 && i==3?60:64,"Unterminated map player string");
    }
}
void FixedScenarioSizes(const MapDocument& d,std::size_t plots) {
    Require(d.playerCount<=32 && d.cityStateCount<=64 && d.teamCount<=96,"Map participant count exceeds SDK capacity");
    const auto relations=RelationSize(d.teamCount);
    for(const auto& r:d.relationships)Require(r.size()==relations,"Wrong map relationship length");
    Require(d.influence.size()==(d.version>=10?std::size_t(d.playerCount)*64*4:0),"Wrong map influence length");
    Require(d.visibility.size()==(plots*d.teamCount+7)/8,"Wrong map visibility length");
    Require(d.teams.size()==std::size_t(d.teamCount)*64,"Wrong map team array length");
    Require(d.players.size()==std::size_t(d.playerCount)*MapPlayerStride(d.version),"Wrong map player array length");
    Require(d.cityStates.size()==std::size_t(d.cityStateCount)*MapPlayerStride(d.version),"Wrong map city-state array length");
    Require(d.plotScenario.size()==plots*8,"Wrong map scenario plot length");
}
void StoreWord(MapBytes& bytes,std::size_t offset,std::uint32_t value) { for(unsigned i=0;i<4;++i)bytes[offset+i]=static_cast<unsigned char>(value>>(8*i)); }
void RecoverInvalidLists(MapDocument& d) {
    FixedScenarioSizes(d,PlotCount(d));
    std::array<MapBytes*,3> pools{{&d.units,&d.unitNames,&d.cities}};
    const std::array<std::size_t,3> strides{{MapUnitStride(d.version),64,MapCityStride(d.version)}};
    std::array<std::vector<bool>,3> used,live;std::array<bool,3> invalid{};
    for(unsigned k=0;k<3;++k) {
        used[k].resize(Slots(*pools[k],strides[k]),false);
        try{live[k]=Live(*pools[k],strides[k]);}catch(const std::invalid_argument&){invalid[k]=true;}
    }
    if(!invalid[0] && !invalid[1] && !invalid[2])return;
    for(std::size_t p=0;p<d.plotScenario.size();p+=8) {
        const unsigned city=HandleAt(d.plotScenario.data()+p);unsigned unit=HandleAt(d.plotScenario.data()+p+2);
        if(city!=65535) { Require(city<used[2].size() && !used[2][city],"Invalid or shared city during free-list recovery");used[2][city]=true; }
        // A unit must belong to exactly one plot chain; shared/cyclic chains are
        // ambiguous and cannot be repaired by changing allocation metadata.
        while(unit!=65535) {
            Require(unit<used[0].size() && !used[0][unit],"Invalid or shared unit chain during free-list recovery");used[0][unit]=true;
            const auto record=d.units.data()+4+std::size_t(unit)*strides[0];
            if(d.version>=9) { const unsigned name=HandleAt(record+2);if(name!=65535){Require(name<used[1].size(),"Out-of-range name during free-list recovery");used[1][name]=true;} }
            unit=HandleAt(record);
        }
    }
    for(unsigned k=0;k<3;++k) {
        if(!invalid[k]) { for(std::size_t i=0;i<used[k].size();++i)Require(!used[k][i] || live[k][i],"Owned record is free in unaffected pool");continue; }
        std::uint32_t next=UINT32_MAX;
        // Descending construction yields a stable ascending free list. Only the
        // 4-byte list words in unreachable slots, plus the head, may change.
        for(std::size_t i=used[k].size();i>0;--i)if(!used[k][i-1]) { StoreWord(*pools[k],4+(i-1)*strides[k],next);next=static_cast<std::uint32_t>(i-1); }
        StoreWord(*pools[k],0,next);d.recoveredAllocators|=1u<<k;
    }
}
}
std::size_t MapUnitStride(unsigned v) { Require(Supported(v),"Unsupported map version");return v>=12?84:v>=9?48:12; }
std::size_t MapCityStride(unsigned v) { Require(Supported(v),"Unsupported map version");return v>=12?136:v>=9?104:100; }
std::size_t MapPlayerStride(unsigned v) { Require(Supported(v),"Unsupported map version");return v>=9?436:304; }

void ValidateMapDocument(const MapDocument& d) {
    Require(Supported(d.version),"Unsupported map version");const auto count=PlotCount(d);
    Require(d.plots.size()==count*8,"Wrong map plot array length");
    Require(d.playable<=32,"Map playable count exceeds SDK capacity");
    for(const auto& t:d.types)Palette(t);
    Text(d.name);Text(d.description);
    if(d.version<7)Require(d.name.empty(),"Version 6 has no map-name field");
    if(d.version>=11) { Require(d.worldType.size()<=64 && !d.worldType.empty(),"Invalid map world-type width");Text(d.worldType); }
    else Require(d.worldType.empty(),"Legacy version has no world-type field");
    if(!d.modData.empty()) { const auto mod=ReadModDocument(d.modData.data(),d.modData.size());
        Require(mod.plot.fields.size()<=(SIZE_MAX-mod.map.fields.size())/(count?count:1),"Map mod-data count overflow");
        Require(mod.values.size()==mod.map.fields.size()+count*mod.plot.fields.size(),"Map mod-data count disagrees with plot count"); }
    if(!d.hasScenario) {
        Require(d.playerCount==0 && d.cityStateCount==0 && d.teamCount==0,"Plain map has scenario participants");
        for(std::size_t i=4;i<d.types.size();++i)Require(d.types[i].empty(),"Plain map has scenario palette");
        Require(d.units.empty() && d.unitNames.empty() && d.cities.empty() && d.victories.empty() && d.options.empty(),"Plain map has scenario records");
        FixedScenarioSizes(d,0);return;
    }
    FixedScenarioSizes(d,count);Terminated(d.speed.data(),d.speed.size(),"Unterminated map game speed");
    if(d.version<9)Require(d.types[9].empty() && d.unitNames.empty(),"Legacy version has no promotions or custom unit names");
    Groups(d.victories);Groups(d.options);ScenarioRecords(d);
}

MapDocument ReadMapDocument(const void* bytes,std::size_t size,bool requireScenario,MapReadPolicy policy) {
    Require(policy==MapReadPolicy::Strict || policy==MapReadPolicy::RebuildInvalidFreeLists,"Invalid map read policy");
    Reader r(bytes,size);MapDocument d;const auto tag=r.Byte();d.version=tag&127;d.hasScenario=(tag&128)!=0;
    Require(Supported(d.version),"Unsupported map version");d.width=r.Word();d.height=r.Word();const auto count=PlotCount(d);
    d.playable=r.Byte();d.flags=r.Word();
    std::array<std::uint32_t,7> lengths{};const unsigned baseSections=d.version>=7?7:6;
    for(unsigned i=0;i<baseSections;++i)lengths[i]=r.Word();
    for(unsigned i=0;i<4;++i)d.types[i]=r.Bytes(lengths[i]);d.modData=r.Bytes(lengths[4]);
    if(d.version>=7) { d.name=r.Bytes(lengths[5]);d.description=r.Bytes(lengths[6]); }else d.description=r.Bytes(lengths[5]);
    if(d.version>=11)d.worldType=r.Bytes(r.Word());d.plots=r.Bytes(count*8);
    if(!d.hasScenario) { Require(!requireScenario,"Map scenario is missing");Require(r.at==size,"Trailing plain-map bytes");ValidateMapDocument(d);return d; }
    r.Fixed(d.speed.data(),d.speed.size());d.startingTurn=r.Word();d.maxTurns=r.Word();d.targetScore=r.Word();d.startYearBits=r.Word();
    d.playerCount=r.Byte();d.cityStateCount=r.Byte();d.teamCount=r.Byte();d.scenarioPadding=r.Byte();
    Require(d.playerCount<=32 && d.cityStateCount<=64 && d.teamCount<=96,"Map participant count exceeds SDK capacity");
    const unsigned typeCount=d.version>=9?6:5;
    std::array<std::uint32_t,6> typeLengths{};for(unsigned i=0;i<typeCount;++i)typeLengths[i]=r.Word();
    const auto unitBytes=r.Word();const auto nameBytes=d.version>=9?r.Word():0;const auto cityBytes=r.Word();const auto victoryBytes=r.Word(),optionBytes=r.Word();
    for(unsigned i=0;i<typeCount;++i)d.types[4+i]=r.Bytes(typeLengths[i]);
    d.units=r.Bytes(unitBytes);d.unitNames=r.Bytes(nameBytes);d.cities=r.Bytes(cityBytes);d.victories=r.Bytes(victoryBytes);d.options=r.Bytes(optionBytes);
    for(auto& relation:d.relationships)relation=r.Bytes(RelationSize(d.teamCount));
    if(d.version>=10)d.influence=r.Bytes(std::size_t(d.playerCount)*64*4);
    d.visibility=r.Bytes((count*d.teamCount+7)/8);
    d.teams=r.Bytes(std::size_t(d.teamCount)*64);d.players=r.Bytes(std::size_t(d.playerCount)*MapPlayerStride(d.version));
    d.cityStates=r.Bytes(std::size_t(d.cityStateCount)*MapPlayerStride(d.version));d.plotScenario=r.Bytes(count*8);
    Require(r.at==size,"Trailing map file bytes");if(policy==MapReadPolicy::RebuildInvalidFreeLists)RecoverInvalidLists(d);ValidateMapDocument(d);return d;
}

MapBytes WriteMapDocument(const MapDocument& d) {
    ValidateMapDocument(d);MapBytes out;out.push_back(static_cast<unsigned char>(d.version|(d.hasScenario?128:0)));
    PutWord(out,d.width);PutWord(out,d.height);out.push_back(d.playable);PutWord(out,d.flags);
    for(unsigned i=0;i<4;++i)PutSize(out,d.types[i]);PutSize(out,d.modData);if(d.version>=7)PutSize(out,d.name);PutSize(out,d.description);
    for(unsigned i=0;i<4;++i)Append(out,d.types[i]);Append(out,d.modData);if(d.version>=7)Append(out,d.name);Append(out,d.description);
    if(d.version>=11) { PutSize(out,d.worldType);Append(out,d.worldType); }Append(out,d.plots);
    if(!d.hasScenario)return out;
    out.insert(out.end(),d.speed.begin(),d.speed.end());PutWord(out,d.startingTurn);PutWord(out,d.maxTurns);PutWord(out,d.targetScore);PutWord(out,d.startYearBits);
    out.push_back(d.playerCount);out.push_back(d.cityStateCount);out.push_back(d.teamCount);out.push_back(d.scenarioPadding);
    const unsigned typeCount=d.version>=9?6:5;
    for(unsigned i=0;i<typeCount;++i)PutSize(out,d.types[4+i]);PutSize(out,d.units);if(d.version>=9)PutSize(out,d.unitNames);PutSize(out,d.cities);PutSize(out,d.victories);PutSize(out,d.options);
    for(unsigned i=0;i<typeCount;++i)Append(out,d.types[4+i]);Append(out,d.units);Append(out,d.unitNames);Append(out,d.cities);Append(out,d.victories);Append(out,d.options);
    for(const auto& relation:d.relationships)Append(out,relation);Append(out,d.influence);Append(out,d.visibility);
    Append(out,d.teams);Append(out,d.players);Append(out,d.cityStates);Append(out,d.plotScenario);return out;
}
}
