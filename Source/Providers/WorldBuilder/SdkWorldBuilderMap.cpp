#include "SdkWorldBuilderMapPool.h"
#include <cmath>

namespace {
template<size_t N> void CopyName(char (&out)[N],const char* text) {
    if(!text)throw std::invalid_argument("Null WorldBuilder name");
    const size_t length=std::strlen(text);
    if(length>=N)throw std::length_error("WorldBuilder name exceeds its fixed field");
    // Callers can pass a substring of the destination.
    std::memmove(out,text,length+1);std::memset(out+length+1,0,N-length-1);
}
template<size_t N,size_t M> void CopyBits(std::bitset<N>& out,const std::bitset<M>& in) {
    out.reset();for(size_t i=0;i<std::min(N,M);++i)out[i]=in[i];
}
byte Swapped(byte value,byte a,byte b) { return value==a?b:value==b?a:value; }
typedef CvWorldBuilderMap Map;
typedef ZeroSisWorldBuilderMapPoolAccess Pool;
struct Owners { std::vector<word> units,cities; };
Owners ReachableOwners(const Map& m) {
    const std::vector<byte> units=Pool::Allocated(m.m_kUnits),cities=Pool::Allocated(m.m_kCities);
    std::vector<byte> unitSeen(units.size(),0),citySeen(cities.size(),0);Owners result;
    for(uint i=0;i<m.GetPlotCount();++i){
        const Map::PlotScenarioData& plot=m.GetPlotScenarioData(i);
        if(plot.m_hCity.Valid()){
            const word city=plot.m_hCity.ToWord();
            if(city>=cities.size() || !cities[city] || citySeen[city])throw std::logic_error("Invalid WorldBuilder city ownership");
            citySeen[city]=1;result.cities.push_back(city);
        }
        Map::Unit::Handle next=plot.m_hUnitStack;
        while(next.Valid()){
            const word unit=next.ToWord();
            if(unit>=units.size() || !units[unit] || unitSeen[unit])throw std::logic_error("Invalid WorldBuilder unit ownership");
            unitSeen[unit]=1;result.units.push_back(unit);next=m.m_kUnits[next]->m_hStackedUnit;
        }
    }
    return result;
}
void SwapOwners(Map& m,const Owners& owners,byte a,byte b) {
    for(uint i=0;i<m.GetPlotCount();++i){Map::PlotScenarioData& p=m.GetPlotScenarioData(i);p.m_byCulture=Swapped(p.m_byCulture,a,b);p.m_byRouteOwner=Swapped(p.m_byRouteOwner,a,b);}
    for(word i:owners.units){Map::Unit* p=Pool::At(m.m_kUnits,i);p->m_byOwner=Swapped(p->m_byOwner,a,b);}
    for(word i:owners.cities){Map::City* p=Pool::At(m.m_kCities,i);p->m_byOwner=Swapped(p->m_byOwner,a,b);}
}
}

CvWorldBuilderMap::PlotMapData CvWorldBuilderMap::sm_kErrorPlotMapData;
CvWorldBuilderMap::PlotScenarioData CvWorldBuilderMap::sm_kErrorPlotScenarioData;
CvWorldBuilderMap::Player CvWorldBuilderMap::sm_kErrorPlayer;
CvWorldBuilderMap::Team CvWorldBuilderMap::sm_kErrorTeam;

CvWorldBuilderMap::PlotMapData::PlotMapData():m_byTerrainType(0),m_byResourceType(255),m_byFeatureType(255),m_byFlags(0),m_byPlotHeight(0),m_byContinentType(0),m_byNaturalWonderType(255),m_byResourceAmount(0){}
CvWorldBuilderMap::PlotScenarioData::PlotScenarioData():m_byCulture(255),m_byImprovement(255),m_byRoute(255),m_byRouteOwner(255){}
CvWorldBuilderMap::OldUnit::OldUnit():m_wExperience(0),m_fHealth(1.0f),m_byUnitType(255),m_byOwner(255),m_byDirection(0),m_bFortified(false),m_bEmbarked(false){}
CvWorldBuilderMap::UnitV2::UnitV2():m_uiExperience(0),m_uiHealth(MaxHealth),m_byUnitType(255),m_byOwner(255),m_byDirection(0),m_byFlags(0){}
CvWorldBuilderMap::Unit::Unit():m_uiExperience(0),m_uiHealth(MaxHealth),m_byUnitType(InvalidUnitType),m_byOwner(255),m_byDirection(0),m_byFlags(0){}
CvWorldBuilderMap::Unit::Unit(const OldUnit& old):Unit(){
    const float health=old.m_fHealth*MaxHealth;
    if(!std::isfinite(health) || health<0 || static_cast<double>(health)>UINT_MAX)throw std::out_of_range("Legacy unit health exceeds its wire field");
    m_hStackedUnit=Pool::Handle<Handle>(old.m_hStackedUnit.ToWord());m_uiExperience=old.m_wExperience;m_uiHealth=static_cast<uint>(health);
    m_byUnitType=old.m_byUnitType;m_byOwner=old.m_byOwner;m_byDirection=old.m_byDirection;m_byFlags=static_cast<byte>((old.m_bFortified?UNIT_FORTIFIED:0)|(old.m_bEmbarked?UNIT_EMBARKED:0));
}
CvWorldBuilderMap::Unit::Unit(const UnitV2& old):Unit(){
    // The archived SDK conversion intentionally leaves the custom-name handle
    // invalid, even when the V2 record refers to an allocated name slot.
    m_hStackedUnit=Pool::Handle<Handle>(old.m_hStackedUnit.ToWord());m_uiExperience=old.m_uiExperience;m_uiHealth=old.m_uiHealth;
    m_byUnitType=old.m_byUnitType;m_byOwner=old.m_byOwner;m_byDirection=old.m_byDirection;m_byFlags=old.m_byFlags;CopyBits(m_kPromotions,old.m_kPromotions);
}
CvWorldBuilderMap::OldCity::OldCity():m_uiPopulation(1),m_uiCulture(0),m_byOwner(255),m_bLocalizedName(false){std::memset(m_szName,0,sizeof(m_szName));}
CvWorldBuilderMap::CityV2::CityV2():m_byOwner(255),m_byFlags(0),m_wPopulation(1),m_uiHealth(MaxHealth){std::memset(m_szName,0,sizeof(m_szName));}
CvWorldBuilderMap::City::City():m_byOwner(255),m_byFlags(0),m_wPopulation(1),m_uiHealth(MaxHealth){std::memset(m_szName,0,sizeof(m_szName));}
CvWorldBuilderMap::City::City(const OldCity& old):City(){
    if(!std::memchr(old.m_szName,0,sizeof(old.m_szName)))throw std::invalid_argument("Unterminated legacy city name");
    if(old.m_uiPopulation>USHRT_MAX)throw std::out_of_range("Legacy city population exceeds its wire field");
    CopyName(m_szName,old.m_szName);m_byOwner=old.m_byOwner;m_byFlags=old.m_bLocalizedName?CITY_LOCALIZED_NAME:0;m_wPopulation=static_cast<word>(old.m_uiPopulation);
    // The archived OldCity conversion clears its legacy building bits.
}
CvWorldBuilderMap::City::City(const CityV2& old):City(){
    if(!std::memchr(old.m_szName,0,sizeof(old.m_szName)))throw std::invalid_argument("Unterminated legacy city name");
    CopyName(m_szName,old.m_szName);m_byOwner=old.m_byOwner;m_byFlags=old.m_byFlags;m_wPopulation=old.m_wPopulation;m_uiHealth=old.m_uiHealth;CopyBits(m_kBuildings,old.m_kBuildings);
}
CvWorldBuilderMap::Team::Team(){std::memset(m_szName,0,sizeof(m_szName));}
CvWorldBuilderMap::OldPlayer::OldPlayer():m_uiCulture(0),m_uiGold(0),m_uiStartX(UINT_MAX),m_uiStartY(UINT_MAX),m_byTeam(255),m_bPlayable(true){
    std::memset(m_szCivType,0,sizeof(m_szCivType));std::memset(m_szTeamColor,0,sizeof(m_szTeamColor));std::memset(m_szEra,0,sizeof(m_szEra));std::memset(m_szHandicap,0,sizeof(m_szHandicap));
}
CvWorldBuilderMap::Player::Player():m_uiCulture(0),m_uiGold(0),m_uiStartX(UINT_MAX),m_uiStartY(UINT_MAX),m_byTeam(255),m_bPlayable(true){
    std::memset(m_szLeaderName,0,sizeof(m_szLeaderName));std::memset(m_szCivName,0,sizeof(m_szCivName));
    std::memset(m_szCivType,0,sizeof(m_szCivType));std::memset(m_szTeamColor,0,sizeof(m_szTeamColor));std::memset(m_szEra,0,sizeof(m_szEra));std::memset(m_szHandicap,0,sizeof(m_szHandicap));
}
CvWorldBuilderMap::Player::Player(const OldPlayer& old):Player(){
    if(!std::memchr(old.m_szCivType,0,sizeof(old.m_szCivType)) || !std::memchr(old.m_szTeamColor,0,sizeof(old.m_szTeamColor)) || !std::memchr(old.m_szEra,0,sizeof(old.m_szEra)) || !std::memchr(old.m_szHandicap,0,sizeof(old.m_szHandicap)))throw std::invalid_argument("Unterminated legacy player name");
    // Like OldCity buildings, archived OldPlayer conversion clears policy bits.
    CopyName(m_szCivType,old.m_szCivType);CopyName(m_szTeamColor,old.m_szTeamColor);CopyName(m_szEra,old.m_szEra);CopyName(m_szHandicap,old.m_szHandicap);
    m_uiCulture=old.m_uiCulture;m_uiGold=old.m_uiGold;m_uiStartX=old.m_uiStartX;m_uiStartY=old.m_uiStartY;m_byTeam=old.m_byTeam;m_bPlayable=old.m_bPlayable;
}
CvWorldBuilderMap::MapDescription::MapDescription():uiWidth(0),uiHeight(0){}
CvWorldBuilderMap::GameDescription::GameDescription():uiStartingTurn(0),uiMaxTurns(0),uiTargetScore(0),iStartYear(-4000),byPlayerCount(0),byCityStateCount(0),byTeamCount(0){std::memset(szDefaultSpeed,0,sizeof(szDefaultSpeed));}
CvWorldBuilderMap::CvWorldBuilderMap():m_uiFlags(FLAG_WORLD_WRAP|FLAG_TRANSFERABLE){std::memset(m_szWorldType,0,sizeof(m_szWorldType));std::memset(m_aiCityStateInfluence,0,sizeof(m_aiCityStateInfluence));}
CvWorldBuilderMap::~CvWorldBuilderMap(){}
void CvWorldBuilderMap::Resize(uint width,uint height){
    if(width>MaxMapSize || height>MaxMapSize || (height && width>MaxMapSize/height))throw std::out_of_range("WorldBuilder map exceeds fixed plot capacity");
    // Archived Resize only changes the dimensions; hidden plot/scenario/mod
    // records remain in place, including when the original size is restored.
    m_kMapDesc.uiWidth=width;m_kMapDesc.uiHeight=height;
}
void CvWorldBuilderMap::SetDefaultGameSpeed(const char* speed){CopyName(m_kGameDesc.szDefaultSpeed,speed);}
void CvWorldBuilderMap::SetWorldType(const char* world){CopyName(m_szWorldType,world);}
void CvWorldBuilderMap::SetAllPlotData(const PlotMapData& plot,const PlotScenarioData& scenario){
    // Values may alias one of our own elements.
    const PlotMapData p=plot;const PlotScenarioData s=scenario;
    for(uint i=0;i<GetPlotCount();++i){m_akMapData[i]=p;m_akScenarioData[i]=s;}
}
void CvWorldBuilderMap::ClearScenarioData(bool preserveImprovements){
    m_kGameDesc=GameDescription();m_kVisibility.Reset();
    for(uint i=0;i<GetPlotCount();++i){const byte improvement=m_akScenarioData[i].m_byImprovement;m_akScenarioData[i]=PlotScenarioData();if(preserveImprovements)m_akScenarioData[i].m_byImprovement=improvement;}
    // Pools are released even when the map was shrunk. Clear their hidden
    // references too, so a later grow cannot resurrect freed unit/city handles.
    for(uint i=GetPlotCount();i<MaxMapSize;++i){m_akScenarioData[i].m_hCity=City::Handle::InvalidHandle();m_akScenarioData[i].m_hUnitStack=Unit::Handle::InvalidHandle();}
    m_kUnits.Release();m_kCities.Release();m_kUnitNames.Release();m_kVictoryTypes.Clear();m_kGameOptions.Clear();
    std::memset(m_aiCityStateInfluence,0,sizeof(m_aiCityStateInfluence));
}
CvWorldBuilderMap::Unit::Handle CvWorldBuilderMap::AddUnit(uint x,uint y){
    if(x>=GetWidth() || y>=GetHeight())return Unit::Handle::InvalidHandle();
    // Check all active ownership before mutating a shared pool. A locally valid
    // chain can still be referenced by a second plot.
    ReachableOwners(*this);PlotScenarioData& plot=m_akScenarioData[GetPlotIndex(x,y)];const Unit::Handle handle=Pool::Allocate(m_kUnits);
    if(handle.Valid()){m_kUnits[handle]->m_hStackedUnit=plot.m_hUnitStack;plot.m_hUnitStack=handle;}return handle;
}
bool CvWorldBuilderMap::RemoveUnit(uint x,uint y,Unit::Handle& handle){
    if(x>=GetWidth() || y>=GetHeight() || !handle.Valid())return false;
    ReachableOwners(*this);PlotScenarioData& plot=m_akScenarioData[GetPlotIndex(x,y)];Unit::Handle* link=&plot.m_hUnitStack;
    while(link->Valid() && *link!=handle)link=&m_kUnits[*link]->m_hStackedUnit;
    if(!link->Valid())return false;
    if(&handle==link)throw std::invalid_argument("Removal handle aliases owned stack link");
    const Unit::Handle next=m_kUnits[handle]->m_hStackedUnit;
    *link=next;
    // Custom-name slots can be shared; the archived operation retains them.
    m_kUnits.Free(handle);return true;
}
void CvWorldBuilderMap::SwapPlayers(byte a,byte b){
    if(a>=GetPlayerCount() || b>=GetPlayerCount())throw std::out_of_range("Invalid WorldBuilder player swap");if(a==b)return;
    const Owners owners=ReachableOwners(*this);std::swap(m_akPlayers[a],m_akPlayers[b]);SwapOwners(*this,owners,a,b);
    for(uint i=0;i<GetCityStateCount();++i)std::swap(m_aiCityStateInfluence[a][i],m_aiCityStateInfluence[b][i]);
}
void CvWorldBuilderMap::SwapCityStates(byte a,byte b){
    if(a>=GetCityStateCount() || b>=GetCityStateCount())throw std::out_of_range("Invalid WorldBuilder city-state swap");if(a==b)return;
    const Owners owners=ReachableOwners(*this);std::swap(m_akCityStates[a],m_akCityStates[b]);SwapOwners(*this,owners,static_cast<byte>(a+MaxPlayers),static_cast<byte>(b+MaxPlayers));
    for(uint i=0;i<GetPlayerCount();++i)std::swap(m_aiCityStateInfluence[i][a],m_aiCityStateInfluence[i][b]);
}
