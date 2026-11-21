#include "SdkWorldBuilderMapBridge.h"
#include "SdkWorldBuilderMapPool.h"
#include "SdkWorldBuilderModData.h"
#include <memory>
#include <type_traits>

namespace {
using namespace ZeroSisWorldBuilder;
typedef CvWorldBuilderMap Map;
typedef CvWorldBuilderMapTypeDesc Types;
uint U32(const byte* p){return uint(p[0])|(uint(p[1])<<8)|(uint(p[2])<<16)|(uint(p[3])<<24);}
word U16(const byte* p){return static_cast<word>(uint(p[0])|(uint(p[1])<<8));}
void P32(byte* p,uint n){for(uint i=0;i<4;++i)p[i]=static_cast<byte>(n>>(8*i));}
void P16(byte* p,word n){p[0]=static_cast<byte>(n);p[1]=static_cast<byte>(n>>8);}
int Signed(uint bits){int value;std::memcpy(&value,&bits,4);return value;}
template<size_t N> void Text(char (&out)[N],const byte* p,size_t size){
    const byte* end=static_cast<const byte*>(std::memchr(p,0,size));if(!end || static_cast<size_t>(end-p)>=N)throw std::invalid_argument("Invalid fixed map name");
    std::memset(out,0,N);std::memcpy(out,p,static_cast<size_t>(end-p));
}
template<size_t N> void TextBytes(byte* out,const char (&text)[N]){
    const char* end=static_cast<const char*>(std::memchr(text,0,N));if(!end)throw std::invalid_argument("Unterminated SDK map name");
    std::memset(out,0,N);std::memcpy(out,text,static_cast<size_t>(end-text));
}
template<size_t N> void ReadBits(std::bitset<N>& bits,const byte* p,size_t bytes){bits.reset();for(size_t i=0;i<std::min(N,bytes*8);++i)bits[i]=(p[i/8]&(1u<<(i%8)))!=0;}
template<size_t N> void WriteBits(byte* p,const std::bitset<N>& bits){std::memset(p,0,(N+7)/8);for(size_t i=0;i<N;++i)if(bits[i])p[i/8]|=static_cast<byte>(1u<<(i%8));}
std::array<const Types::TypeMap*,10> Maps(const Types& t){return {{&t.m_kTerrainTypes,&t.m_kFeatures,&t.m_kNaturalWonders,&t.m_kResources,&t.m_kImprovements,&t.m_kUnits,&t.m_kTechs,&t.m_kPolicies,&t.m_kBuildingTypes,&t.m_kUnitPromotions}};}
struct Lookup {
    std::array<std::vector<uint>,10> ids;std::array<bool,10> changed{};
    Lookup(const MapDocument& d,const Types& target){const auto maps=Maps(target);
        for(size_t i=0;i<10;++i){Types::TypeMap from;from.Deserialize(const_cast<byte*>(d.types[i].data()),d.types[i].size());changed[i]=Types::BuildLookupTable(from,*maps[i],ids[i]);}
    }
    uint Type(uint n,unsigned kind,uint invalid)const{
        if(n==invalid || !changed[kind])return n;
        return n<ids[kind].size() && ids[kind][n]<invalid?ids[kind][n]:invalid;
    }
    template<size_t N> void Bits(std::bitset<N>& bits,unsigned kind)const{
        if(!changed[kind])return;const std::bitset<N> before=bits;bits.reset();
        for(size_t i=0;i<N && i<ids[kind].size();++i)if(before[i] && ids[kind][i]<N)bits[ids[kind][i]]=true;
    }
};
MapBytes ModBytes(const CvWorldBuilderMapModData& mod){MapBytes bytes(mod.GetSerializedSize());mod.Serialize(bytes.data());return bytes;}
MapBytes StringBytes(const FStringA& value){const char* text=value.c_str();return MapBytes(text,text+std::strlen(text)+1);}
}

struct ZeroSisWorldBuilderMapBridgeAccess {
    template<class H> static H Handle(word n){return H(n);}
    template<class T,uint N> static void CopyPool(CvWorldBuilderMapElementAllocator<T,N>& out,const CvWorldBuilderMapElementAllocator<T,N>& in){
        if(in.m_uiSize>65535u || ((in.m_uiSize!=0)!=(in.m_aData!=NULL)))throw std::invalid_argument("Invalid source map pool");
        typedef typename CvWorldBuilderMapElementAllocator<T,N>::Entry Entry;
        Entry* data=NULL;
        if(in.m_uiSize){data=static_cast<Entry*>(FMALLOC(sizeof(Entry)*in.m_uiSize,c_eMPoolTypeGame,0));if(!data)throw std::bad_alloc();std::memcpy(data,in.m_aData,sizeof(Entry)*in.m_uiSize);}
        out.Release();out.m_aData=data;out.m_uiSize=in.m_uiSize;out.m_iFreeList=in.m_iFreeList;
    }
    template<class T,uint N> static void SwapPool(CvWorldBuilderMapElementAllocator<T,N>& a,CvWorldBuilderMapElementAllocator<T,N>& b)noexcept{
        std::swap(a.m_aData,b.m_aData);std::swap(a.m_uiSize,b.m_uiSize);std::swap(a.m_iFreeList,b.m_iFreeList);
    }
    static void FixedState(Map& target,const Map& source)noexcept{
        static_assert(std::is_nothrow_copy_assignable<Map::Player>::value,"Map player publication must not allocate");
        static_assert(std::is_nothrow_copy_assignable<decltype(target.m_kVisibility)>::value,"Map visibility publication must not allocate");
        target.m_kMapDesc=source.m_kMapDesc;target.m_kGameDesc=source.m_kGameDesc;target.m_uiFlags=source.m_uiFlags;
        std::copy_n(source.m_akMapData,Map::MaxMapSize,target.m_akMapData);std::copy_n(source.m_akScenarioData,Map::MaxMapSize,target.m_akScenarioData);
        std::copy_n(source.m_akPlayers,Map::MaxPlayers,target.m_akPlayers);std::copy_n(source.m_akCityStates,Map::MaxCityStates,target.m_akCityStates);std::copy_n(source.m_akTeams,Map::MaxTeams,target.m_akTeams);
        std::memcpy(target.m_aiCityStateInfluence,source.m_aiCityStateInfluence,sizeof(target.m_aiCityStateInfluence));std::memcpy(target.m_szWorldType,source.m_szWorldType,sizeof(target.m_szWorldType));
        target.m_kVisibility=source.m_kVisibility;target.m_kTeamsInContact=source.m_kTeamsInContact;target.m_kTeamsAtWar=source.m_kTeamsAtWar;
        target.m_kTeamsAtPermanentWarOrPeace=source.m_kTeamsAtPermanentWarOrPeace;target.m_kTeamsSharingOpenBorders=source.m_kTeamsSharingOpenBorders;target.m_kTeamsSharingDefensivePacts=source.m_kTeamsSharingDefensivePacts;
    }
    static void Clone(Map& target,const Map& source){
        FixedState(target,source);target.m_sMapName=source.m_sMapName;target.m_sMapDescription=source.m_sMapDescription;target.m_kVictoryTypes=source.m_kVictoryTypes;target.m_kGameOptions=source.m_kGameOptions;
        CopyPool(target.m_kUnits,source.m_kUnits);CopyPool(target.m_kCities,source.m_kCities);CopyPool(target.m_kUnitNames,source.m_kUnitNames);
    }
    static void SwapGroup(CvWorldBuilderMapTypeGroup& a,CvWorldBuilderMapTypeGroup& b)noexcept{std::swap(a.m_szBuffer,b.m_szBuffer);std::swap(a.m_uiBufferSize,b.m_uiBufferSize);}
    static void Publish(Map& target,Map& prepared,const MapBytes& mod){
        // This checked mod-data operation prepares its own storage and has a
        // strong guarantee. Everything after it is non-allocating/non-throwing.
        ZeroSisWorldBuilder::DeserializeModData(target.m_kModData,mod.data(),mod.size());
        FixedState(target,prepared);std::swap(target.m_sMapName.m_pszString,prepared.m_sMapName.m_pszString);std::swap(target.m_sMapDescription.m_pszString,prepared.m_sMapDescription.m_pszString);
        SwapGroup(target.m_kVictoryTypes,prepared.m_kVictoryTypes);SwapGroup(target.m_kGameOptions,prepared.m_kGameOptions);
        SwapPool(target.m_kUnits,prepared.m_kUnits);SwapPool(target.m_kCities,prepared.m_kCities);SwapPool(target.m_kUnitNames,prepared.m_kUnitNames);
    }
    template<class T,uint N,class Decode> static void ReadPool(CvWorldBuilderMapElementAllocator<T,N>& out,const MapBytes& bytes,size_t stride,Decode decode){
        out.Release();if(bytes.empty())return;
        const uint count=static_cast<uint>((bytes.size()-4)/stride);std::vector<byte> live(count,1);uint free=U32(bytes.data());
        while(free!=UINT_MAX){if(free>=count || !live[free])throw std::invalid_argument("Invalid map free list");live[free]=0;free=U32(bytes.data()+4+size_t(free)*stride);}
        typedef typename CvWorldBuilderMapElementAllocator<T,N>::Entry Entry;
        Entry* data=static_cast<Entry*>(FMALLOC(sizeof(Entry)*count,c_eMPoolTypeGame,0));if(!data)throw std::bad_alloc();
        // Install storage into the temporary map immediately so a decode
        // exception releases it with normal temporary-map destruction.
        out.m_aData=data;out.m_uiSize=count;out.m_iFreeList=Signed(U32(bytes.data()));std::memset(data,0,sizeof(Entry)*count);
        for(uint i=0;i<count;++i){const byte* p=bytes.data()+4+size_t(i)*stride;
            if(live[i]){T* value=new(&data[i])T();decode(*value,p);}else data[i].iNextFreeEntry=Signed(U32(p));}
    }
    template<class T,uint N,class Encode> static MapBytes WritePool(const CvWorldBuilderMapElementAllocator<T,N>& pool,size_t stride,Encode encode){
        const auto live=ZeroSisWorldBuilderMapPoolAccess::Allocated(pool);if(live.empty())return MapBytes();
        MapBytes bytes(4+live.size()*stride,0);P32(bytes.data(),static_cast<uint>(pool.m_iFreeList));
        for(uint i=0;i<pool.m_uiSize;++i){byte* p=bytes.data()+4+size_t(i)*stride;
            if(live[i])encode(*reinterpret_cast<const T*>(&pool.m_aData[i]),p);else P32(p,static_cast<uint>(pool.m_aData[i].iNextFreeEntry));}
        return bytes;
    }
    static void ReadUnit(Map::Unit& unit,const byte* p,unsigned version,const Lookup& lookup){
        if(version<9){Map::OldUnit old;old.m_hStackedUnit=Handle<Map::OldUnit::Handle>(U16(p));old.m_wExperience=U16(p+2);const uint health=U32(p+4);std::memcpy(&old.m_fHealth,&health,4);
            old.m_byUnitType=p[8];old.m_byOwner=p[9];old.m_byDirection=p[10];old.m_bFortified=(p[11]&1)!=0;old.m_bEmbarked=(p[11]&2)!=0;unit=Map::Unit(old);
        }else if(version<12){
            Map::UnitV2 old;old.m_hStackedUnit=Handle<Map::UnitV2::Handle>(U16(p));old.m_hCustomName=Handle<Map::UnitName::Handle>(U16(p+2));
            old.m_uiExperience=U32(p+4);old.m_uiHealth=U32(p+8);old.m_byUnitType=p[12];old.m_byOwner=p[13];old.m_byDirection=p[14];old.m_byFlags=p[15];ReadBits(old.m_kPromotions,p+16,32);
            unit=Map::Unit(old);
        }else{
            unit.m_hStackedUnit=Handle<Map::Unit::Handle>(U16(p));unit.m_hCustomName=Handle<Map::UnitName::Handle>(U16(p+2));unit.m_uiExperience=U32(p+4);unit.m_uiHealth=U32(p+8);
            unit.m_byUnitType=U32(p+12);unit.m_byOwner=p[16];unit.m_byDirection=p[17];unit.m_byFlags=p[18];ReadBits(unit.m_kPromotions,p+20,64);
        }
        unit.m_byUnitType=lookup.Type(unit.m_byUnitType,5,UINT_MAX);lookup.Bits(unit.m_kPromotions,9);
    }
    static void WriteUnit(const Map::Unit& u,byte* p){P16(p,u.m_hStackedUnit.ToWord());P16(p+2,u.m_hCustomName.ToWord());P32(p+4,u.m_uiExperience);P32(p+8,u.m_uiHealth);P32(p+12,u.m_byUnitType);p[16]=u.m_byOwner;p[17]=u.m_byDirection;p[18]=u.m_byFlags;WriteBits(p+20,u.m_kPromotions);}
    static void ReadCity(Map::City& city,const byte* p,unsigned version,const Lookup& lookup){
        if(version<9){Map::OldCity old;Text(old.m_szName,p,56);old.m_uiPopulation=U32(p+56);old.m_uiCulture=U32(p+60);old.m_byOwner=p[64];old.m_bLocalizedName=p[65]!=0;ReadBits(old.m_kBuildings,p+68,32);city=Map::City(old);}
        else{Text(city.m_szName,p,64);city.m_byOwner=p[64];city.m_byFlags=p[65];city.m_wPopulation=U16(p+66);city.m_uiHealth=U32(p+68);ReadBits(city.m_kBuildings,p+72,version>=12?64:32);}
        lookup.Bits(city.m_kBuildings,8);
    }
    static void WriteCity(const Map::City& c,byte* p){TextBytes(p,c.m_szName);p[64]=c.m_byOwner;p[65]=c.m_byFlags;P16(p+66,c.m_wPopulation);P32(p+68,c.m_uiHealth);WriteBits(p+72,c.m_kBuildings);}
    static void ReadPlayer(Map::Player& player,const byte* p,unsigned version,const Lookup& lookup){
        if(version<9){Map::OldPlayer old;ReadBits(old.m_kPolicies,p,32);Text(old.m_szCivType,p+32,64);Text(old.m_szTeamColor,p+96,64);Text(old.m_szEra,p+160,64);Text(old.m_szHandicap,p+224,60);
            old.m_uiCulture=U32(p+284);old.m_uiGold=U32(p+288);old.m_uiStartX=U32(p+292);old.m_uiStartY=U32(p+296);old.m_byTeam=p[300];old.m_bPlayable=p[301]!=0;player=Map::Player(old);
        }else{ReadBits(player.m_kPolicies,p,32);Text(player.m_szLeaderName,p+32,64);Text(player.m_szCivName,p+96,64);Text(player.m_szCivType,p+160,64);Text(player.m_szTeamColor,p+224,64);Text(player.m_szEra,p+288,64);Text(player.m_szHandicap,p+352,64);
            player.m_uiCulture=U32(p+416);player.m_uiGold=U32(p+420);player.m_uiStartX=U32(p+424);player.m_uiStartY=U32(p+428);player.m_byTeam=p[432];player.m_bPlayable=p[433]!=0;}
        lookup.Bits(player.m_kPolicies,7);
    }
    static void WritePlayer(const Map::Player& p,byte* out){WriteBits(out,p.m_kPolicies);TextBytes(out+32,p.m_szLeaderName);TextBytes(out+96,p.m_szCivName);TextBytes(out+160,p.m_szCivType);TextBytes(out+224,p.m_szTeamColor);TextBytes(out+288,p.m_szEra);TextBytes(out+352,p.m_szHandicap);
        P32(out+416,p.m_uiCulture);P32(out+420,p.m_uiGold);P32(out+424,p.m_uiStartX);P32(out+428,p.m_uiStartY);out[432]=p.m_byTeam;out[433]=p.m_bPlayable?1:0;
    }
    static void Read(Map& m,const MapDocument& d,const Types& types,bool scenario){
        const Lookup lookup(d,types);m.Resize(d.width,d.height);m.m_uiFlags=d.flags|(d.version<9?0x18u:0u);
        if(d.version>=7)m.m_sMapName=d.name.empty()?"":reinterpret_cast<const char*>(d.name.data());
        m.m_sMapDescription=d.description.empty()?"":reinterpret_cast<const char*>(d.description.data());
        if(d.version>=11)Text(m.m_szWorldType,d.worldType.data(),d.worldType.size());
        for(uint i=0;i<m.GetPlotCount();++i){const byte* p=d.plots.data()+size_t(i)*8;Map::PlotMapData& v=m.m_akMapData[i];
            v.SetTerrainType(static_cast<byte>(lookup.Type(p[0],0,255)));v.SetResourceType(static_cast<byte>(lookup.Type(p[1],3,255)));v.SetFeatureType(static_cast<byte>(lookup.Type(p[2],1,255)));
            v.SetFlags(p[3]);v.SetPlotHeight(static_cast<Map::PlotMapData::PlotHeight>(p[4]));v.SetContinentType(p[5]);v.SetNaturalWonderType(static_cast<byte>(lookup.Type(p[6],2,255)));v.SetResourceAmount(p[7]);}
        if(!scenario || !d.hasScenario)return;
        Text(m.m_kGameDesc.szDefaultSpeed,d.speed.data(),64);m.m_kGameDesc.uiStartingTurn=d.startingTurn;m.m_kGameDesc.uiMaxTurns=d.maxTurns;m.m_kGameDesc.uiTargetScore=d.targetScore;m.m_kGameDesc.iStartYear=Signed(d.startYearBits);
        m.m_kGameDesc.byPlayerCount=d.playerCount;m.m_kGameDesc.byCityStateCount=d.cityStateCount;m.m_kGameDesc.byTeamCount=d.teamCount;
        ReadPool(m.m_kUnits,d.units,MapUnitStride(d.version),[&](Map::Unit& u,const byte* p){ReadUnit(u,p,d.version,lookup);});
        ReadPool(m.m_kCities,d.cities,MapCityStride(d.version),[&](Map::City& c,const byte* p){ReadCity(c,p,d.version,lookup);});
        ReadPool(m.m_kUnitNames,d.unitNames,64,[](Map::UnitName& n,const byte* p){Text(n.m_szText,p,64);});
        m.m_kVictoryTypes.Deserialize(d.victories.data(),static_cast<uint>(d.victories.size()));m.m_kGameOptions.Deserialize(d.options.data(),static_cast<uint>(d.options.size()));
        if(!d.relationships[0].empty()){m.m_kTeamsInContact.Deserialize(d.relationships[0].data(),d.teamCount);m.m_kTeamsAtWar.Deserialize(d.relationships[1].data(),d.teamCount);
            m.m_kTeamsAtPermanentWarOrPeace.Deserialize(d.relationships[2].data(),d.teamCount);m.m_kTeamsSharingOpenBorders.Deserialize(d.relationships[3].data(),d.teamCount);m.m_kTeamsSharingDefensivePacts.Deserialize(d.relationships[4].data(),d.teamCount);}
        if(d.version>=10)for(uint i=0;i<d.playerCount;++i)for(uint j=0;j<64;++j)m.m_aiCityStateInfluence[i][j]=Signed(U32(d.influence.data()+(size_t(i)*64+j)*4));
        if(!d.visibility.empty())m.m_kVisibility.Deserialize(d.visibility.data(),m.GetPlotCount()*d.teamCount);
        for(uint i=0;i<d.teamCount;++i){const byte* p=d.teams.data()+i*64;Text(m.m_akTeams[i].m_szName,p,32);ReadBits(m.m_akTeams[i].m_kTechs,p+32,32);lookup.Bits(m.m_akTeams[i].m_kTechs,6);}
        for(uint i=0;i<d.playerCount;++i)ReadPlayer(m.m_akPlayers[i],d.players.data()+i*MapPlayerStride(d.version),d.version,lookup);
        for(uint i=0;i<d.cityStateCount;++i)ReadPlayer(m.m_akCityStates[i],d.cityStates.data()+i*MapPlayerStride(d.version),d.version,lookup);
        for(uint i=0;i<m.GetPlotCount();++i){const byte* p=d.plotScenario.data()+size_t(i)*8;Map::PlotScenarioData& v=m.m_akScenarioData[i];v.m_hCity=Handle<Map::City::Handle>(U16(p));v.m_hUnitStack=Handle<Map::Unit::Handle>(U16(p+2));
            v.m_byCulture=p[4];v.m_byImprovement=static_cast<byte>(lookup.Type(p[5],4,255));v.m_byRoute=p[6];v.m_byRouteOwner=p[7];}
        // Replaced pools invalidate references left outside the newly loaded map.
        for(uint i=m.GetPlotCount();i<Map::MaxMapSize;++i){m.m_akScenarioData[i].m_hCity=Map::City::Handle();m.m_akScenarioData[i].m_hUnitStack=Map::Unit::Handle();}
    }
    static MapDocument Write(const Map& m,const Types& types,bool scenario){
        MapDocument d;d.hasScenario=scenario;d.width=m.GetWidth();d.height=m.GetHeight();d.flags=m.m_uiFlags;d.modData=ModBytes(m.m_kModData);d.name=StringBytes(m.m_sMapName);d.description=StringBytes(m.m_sMapDescription);
        d.worldType.resize(64);TextBytes(d.worldType.data(),m.m_szWorldType);const auto maps=Maps(types);
        for(size_t i=0;i<(scenario?10u:4u);++i){d.types[i].resize(maps[i]->GetSerializedSize());if(!d.types[i].empty())maps[i]->Serialize(d.types[i].data());}
        d.plots.resize(size_t(m.GetPlotCount())*8);
        for(uint i=0;i<m.GetPlotCount();++i){byte* p=d.plots.data()+size_t(i)*8;const Map::PlotMapData& v=m.m_akMapData[i];p[0]=v.GetTerrainType();p[1]=v.GetResourceType();p[2]=v.GetFeatureType();p[3]=v.GetFlags();p[4]=static_cast<byte>(v.GetPlotHeight());p[5]=v.GetContinentType();p[6]=v.GetNaturalWonderType();p[7]=v.GetResourceAmount();}
        if(!scenario)return d;
        TextBytes(d.speed.data(),m.m_kGameDesc.szDefaultSpeed);d.startingTurn=m.m_kGameDesc.uiStartingTurn;d.maxTurns=m.m_kGameDesc.uiMaxTurns;d.targetScore=m.m_kGameDesc.uiTargetScore;d.startYearBits=static_cast<uint>(m.m_kGameDesc.iStartYear);
        d.playerCount=m.GetPlayerCount();d.cityStateCount=m.GetCityStateCount();d.teamCount=m.GetTeamCount();
        for(uint i=0;i<d.playerCount;++i)if(m.m_akPlayers[i].m_bPlayable)++d.playable;
        d.units=WritePool(m.m_kUnits,84,WriteUnit);d.cities=WritePool(m.m_kCities,136,WriteCity);d.unitNames=WritePool(m.m_kUnitNames,64,[](const Map::UnitName& n,byte* p){TextBytes(p,n.m_szText);});
        d.victories.resize(m.m_kVictoryTypes.GetSerializedSize());if(!d.victories.empty())m.m_kVictoryTypes.Serialize(d.victories.data());d.options.resize(m.m_kGameOptions.GetSerializedSize());if(!d.options.empty())m.m_kGameOptions.Serialize(d.options.data());
        const size_t relationBytes=(size_t(d.teamCount)*(d.teamCount?d.teamCount-1:0)/2+7)/8;
        for(auto& r:d.relationships)r.resize(relationBytes);
        if(relationBytes){m.m_kTeamsInContact.Serialize(d.relationships[0].data(),d.teamCount);m.m_kTeamsAtWar.Serialize(d.relationships[1].data(),d.teamCount);m.m_kTeamsAtPermanentWarOrPeace.Serialize(d.relationships[2].data(),d.teamCount);m.m_kTeamsSharingOpenBorders.Serialize(d.relationships[3].data(),d.teamCount);m.m_kTeamsSharingDefensivePacts.Serialize(d.relationships[4].data(),d.teamCount);}
        d.influence.resize(size_t(d.playerCount)*64*4);for(uint i=0;i<d.playerCount;++i)for(uint j=0;j<64;++j)P32(d.influence.data()+(size_t(i)*64+j)*4,static_cast<uint>(m.m_aiCityStateInfluence[i][j]));
        d.visibility.resize((size_t(m.GetPlotCount())*d.teamCount+7)/8);if(!d.visibility.empty())m.m_kVisibility.Serialize(d.visibility.data(),m.GetPlotCount()*d.teamCount);
        d.teams.resize(size_t(d.teamCount)*64);for(uint i=0;i<d.teamCount;++i){byte* p=d.teams.data()+i*64;TextBytes(p,m.m_akTeams[i].m_szName);WriteBits(p+32,m.m_akTeams[i].m_kTechs);}
        d.players.resize(size_t(d.playerCount)*436);for(uint i=0;i<d.playerCount;++i)WritePlayer(m.m_akPlayers[i],d.players.data()+i*436);
        d.cityStates.resize(size_t(d.cityStateCount)*436);for(uint i=0;i<d.cityStateCount;++i)WritePlayer(m.m_akCityStates[i],d.cityStates.data()+i*436);
        d.plotScenario.resize(size_t(m.GetPlotCount())*8);for(uint i=0;i<m.GetPlotCount();++i){byte* p=d.plotScenario.data()+size_t(i)*8;const Map::PlotScenarioData& v=m.m_akScenarioData[i];P16(p,v.m_hCity.ToWord());P16(p+2,v.m_hUnitStack.ToWord());p[4]=v.m_byCulture;p[5]=v.m_byImprovement;p[6]=v.m_byRoute;p[7]=v.m_byRouteOwner;}
        return d;
    }
};

namespace ZeroSisWorldBuilder {
MapLoadResult LoadMapBytes(Map& target,const void* bytes,size_t length,const Types& types,bool scenario,MapReadPolicy policy){
    const MapDocument d=ReadMapDocument(bytes,length,false,policy);std::unique_ptr<Map> prepared(new Map);
    ZeroSisWorldBuilderMapBridgeAccess::Clone(*prepared,target);ZeroSisWorldBuilderMapBridgeAccess::Read(*prepared,d,types,scenario);
    const MapBytes mod=d.modData.empty()?ModBytes(target.m_kModData):d.modData;
    ZeroSisWorldBuilderMapBridgeAccess::Publish(target,*prepared,mod);return {d.version,d.recoveredAllocators};
}
MapBytes SaveMapBytes(const Map& source,const Types& types,bool scenario){return WriteMapDocument(ZeroSisWorldBuilderMapBridgeAccess::Write(source,types,scenario));}
}
