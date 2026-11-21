#pragma once
#include "sdk_world_builder_map_file_host.h"

// The reference reader receives the type dictionaries stored in its input.
// It therefore preserves IDs instead of replacing unknown fixture-only types.
static void SourceTypes(CvWorldBuilderMapTypeDesc& t,const std::vector<byte>& bytes) {
    const unsigned version=bytes.empty()?0:bytes[0]&127;
    if(version!=6 && version!=7 && version!=9 && version!=10 && version!=11 && version!=12)throw std::runtime_error("Reference palette version");
    const size_t baseWords=version>=7?8:7;if(bytes.size()<10+baseWords*4)throw std::runtime_error("Reference palette header");
    const byte* raw=&bytes[0];unsigned width=0,height=0;std::memcpy(&width,raw+1,4);std::memcpy(&height,raw+5,4);
    unsigned lengths[8]={0};std::memcpy(lengths,raw+10,baseWords*4);size_t offset=10+baseWords*4;
    CvWorldBuilderMapTypeDesc::TypeMap* maps[]={&t.m_kTerrainTypes,&t.m_kFeatures,&t.m_kNaturalWonders,&t.m_kResources,&t.m_kImprovements,&t.m_kUnits,&t.m_kTechs,&t.m_kPolicies,&t.m_kBuildingTypes,&t.m_kUnitPromotions};
    for(unsigned i=0;i<10;++i)maps[i]->Clear();
    for(unsigned i=1;i<baseWords;++i){if(lengths[i]>bytes.size()-offset)throw std::runtime_error("Reference palette section");if(i<=4 && lengths[i])maps[i-1]->Deserialize(const_cast<byte*>(raw+offset),lengths[i]);offset+=lengths[i];}
    if(version>=11){if(bytes.size()-offset<4)throw std::runtime_error("Reference world header");unsigned n;std::memcpy(&n,raw+offset,4);offset+=4;if(n>bytes.size()-offset)throw std::runtime_error("Reference world field");offset+=n;}
    const unsigned long long plots=static_cast<unsigned long long>(width)*height;
    if(plots>32768 || plots*8>bytes.size()-offset)throw std::runtime_error("Reference plot array");offset+=static_cast<size_t>(plots)*8;
    if(!(bytes[0]&128))return;
    const unsigned mapCount=version>=9?6:5;const size_t header=version>=9?128:120;
    if(bytes.size()-offset<header)throw std::runtime_error("Reference scenario header");
    unsigned sizes[6]={0};std::memcpy(sizes,raw+offset+84,mapCount*4);offset+=header;
    for(unsigned i=0;i<mapCount;++i){if(sizes[i]>bytes.size()-offset)throw std::runtime_error("Reference scenario palette");if(sizes[i])maps[4+i]->Deserialize(const_cast<byte*>(raw+offset),sizes[i]);offset+=sizes[i];}
}
class StateHasher {
    unsigned value;
    std::vector<byte> records;
public:
    StateHasher():value(2166136261u){}
    void Byte(unsigned char b){value^=b;value*=16777619u;records.push_back(b);}
    void Number(unsigned n){for(unsigned i=0;i<4;++i)Byte(static_cast<unsigned char>(n>>(8*i)));}
    void String(const char* s){const size_t n=std::strlen(s);Number(static_cast<unsigned>(n));for(size_t i=0;i<n;++i)Byte(static_cast<unsigned char>(s[i]));}
    template<size_t N> void Bits(const std::bitset<N>& b){for(size_t i=0;i<N;++i)Byte(b[i]?1:0);}
    void Player(const CvWorldBuilderMap::Player& p){Bits(p.m_kPolicies);String(p.m_szLeaderName);String(p.m_szCivName);String(p.m_szCivType);String(p.m_szTeamColor);String(p.m_szEra);String(p.m_szHandicap);Number(p.m_uiCulture);Number(p.m_uiGold);Number(p.m_uiStartX);Number(p.m_uiStartY);Number(p.m_byTeam);Number(p.m_bPlayable);}
    unsigned Value()const{return value;}
    void Write(const char* path)const{if(!path)return;FILE* f=std::fopen(path,"wb");if(!f)throw std::runtime_error("Reference state open");const size_t n=std::fwrite(&records[0],1,records.size(),f);const int closed=std::fclose(f);if(n!=records.size() || closed)throw std::runtime_error("Reference state write");}
};
static unsigned SemanticHash(const CvWorldBuilderMap& m,const char* output) {
    StateHasher h;h.Number(m.GetWidth());h.Number(m.GetHeight());h.Number(m.m_uiFlags);h.Number(m.GetPlayerCount());h.Number(m.GetCityStateCount());h.Number(m.GetTeamCount());
    h.Number(static_cast<unsigned>(m.GetStartYear()));h.Number(m.GetMaxTurns());h.String(m.GetDefaultGameSpeed());h.String(m.GetWorldType());h.String(m.m_sMapName.c_str());h.String(m.m_sMapDescription.c_str());
    for(uint i=0;i<m.GetPlotCount();++i){const CvWorldBuilderMap::PlotMapData& p=m.GetPlotData(i);const CvWorldBuilderMap::PlotScenarioData& s=m.GetPlotScenarioData(i);
        h.Number(p.GetTerrainType());h.Number(p.GetResourceType());h.Number(p.GetFeatureType());h.Number(p.GetFlags());h.Number(p.GetPlotHeight());h.Number(p.GetContinentType());h.Number(p.GetNaturalWonderType());h.Number(p.GetResourceAmount());
        h.Number(s.m_hCity.ToWord());h.Number(s.m_hUnitStack.ToWord());h.Number(s.m_byCulture);h.Number(s.m_byImprovement);h.Number(s.m_byRoute);h.Number(s.m_byRouteOwner);
        if(s.m_hCity.Valid()){const CvWorldBuilderMap::City* c=m.m_kCities[s.m_hCity];if(!c)throw std::runtime_error("Reference city handle");h.String(c->m_szName);h.Number(c->m_byOwner);h.Number(c->m_byFlags);h.Number(c->m_wPopulation);h.Number(c->m_uiHealth);h.Bits(c->m_kBuildings);}
        CvWorldBuilderMap::Unit::Handle u=s.m_hUnitStack;unsigned limit=0;
        while(u.Valid()){if(++limit>65535)throw std::runtime_error("Reference unit cycle");const CvWorldBuilderMap::Unit* unit=m.m_kUnits[u];if(!unit)throw std::runtime_error("Reference unit handle");h.Number(u.ToWord());h.Number(unit->m_hStackedUnit.ToWord());h.Number(unit->m_hCustomName.ToWord());h.Number(unit->m_uiExperience);h.Number(unit->m_uiHealth);h.Number(unit->m_byUnitType);h.Number(unit->m_byOwner);h.Number(unit->m_byDirection);h.Number(unit->m_byFlags);h.Bits(unit->m_kPromotions);
            if(unit->m_hCustomName.Valid()){const CvWorldBuilderMap::UnitName* name=m.m_kUnitNames[unit->m_hCustomName];if(!name)throw std::runtime_error("Reference unit name");h.String(name->m_szText);}u=unit->m_hStackedUnit;}
    }
    for(byte i=0;i<m.GetPlayerCount();++i){h.Player(m.GetPlayer(i));for(uint j=0;j<CvWorldBuilderMap::MaxCityStates;++j)h.Number(static_cast<unsigned>(m.m_aiCityStateInfluence[i][j]));}
    for(byte i=0;i<m.GetCityStateCount();++i)h.Player(m.GetCityState(i));
    for(byte i=0;i<m.GetTeamCount();++i){const CvWorldBuilderMap::Team& t=m.GetTeam(i);h.String(t.m_szName);h.Bits(t.m_kTechs);
        for(byte j=0;j<i;++j){h.Number(m.m_kTeamsInContact.Get(i,j));h.Number(m.m_kTeamsAtWar.Get(i,j));h.Number(m.m_kTeamsAtPermanentWarOrPeace.Get(i,j));h.Number(m.m_kTeamsSharingOpenBorders.Get(i,j));h.Number(m.m_kTeamsSharingDefensivePacts.Get(i,j));}
        for(uint y=0;y<m.GetHeight();++y)for(uint x=0;x<m.GetWidth();++x)h.Number(m.GetVisibility(x,y,i));
    }
    std::vector<byte> data(m.m_kModData.GetSerializedSize());m.m_kModData.Serialize(&data[0]);for(size_t i=0;i<data.size();++i)h.Byte(data[i]);
    const CvWorldBuilderMapTypeGroup* groups[]={&m.m_kVictoryTypes,&m.m_kGameOptions};
    for(unsigned i=0;i<2;++i){data.resize(groups[i]->GetSerializedSize());if(!data.empty())groups[i]->Serialize(&data[0]);h.Number(static_cast<unsigned>(data.size()));for(size_t j=0;j<data.size();++j)h.Byte(data[j]);}
    h.Write(output);return h.Value();
}
