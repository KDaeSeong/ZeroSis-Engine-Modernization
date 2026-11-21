#include "sdk_world_builder_map_file_host.h"
#include "sdk_world_builder_map_state.h"
#include <memory>

static unsigned checks=0;
#define CHECK(x) do { ++checks;if(!(x)){std::fprintf(stderr,"FAIL|%d|%s\n",__LINE__,#x);std::exit(2);} } while(0)
static void Dump(const CvWorldBuilderMap& m) {
    std::printf("MAP|%u|%u|%u|%u|%u|%u|%d|%u|%s|%s|%s|%s\n",m.GetWidth(),m.GetHeight(),m.GetPlayerCount(),m.GetCityStateCount(),m.GetTeamCount(),m.m_uiFlags,m.GetStartYear(),m.GetMaxTurns(),m.GetWorldType(),m.GetDefaultGameSpeed(),m.m_sMapName.c_str(),m.m_sMapDescription.c_str());
    for(uint i=0;i<m.GetPlotCount();++i){const CvWorldBuilderMap::PlotMapData& p=m.GetPlotData(i);const CvWorldBuilderMap::PlotScenarioData& s=m.GetPlotScenarioData(i);
        std::printf("PLOT|%u|%u|%u|%u|%u|%u|%u|%u|%u|%u|%u|%u|%u|%u|%u\n",i,p.GetTerrainType(),p.GetResourceType(),p.GetFeatureType(),p.GetFlags(),p.GetPlotHeight(),p.GetContinentType(),p.GetNaturalWonderType(),p.GetResourceAmount(),s.m_hCity.ToWord(),s.m_hUnitStack.ToWord(),s.m_byCulture,s.m_byImprovement,s.m_byRoute,s.m_byRouteOwner);
    }
    for(byte i=0;i<m.GetPlayerCount();++i){const CvWorldBuilderMap::Player& p=m.GetPlayer(i);std::printf("PLAYER|%u|%s|%s|%s|%s|%s|%s|%u|%u|%u|%u|%u|%u|%u\n",i,p.m_szLeaderName,p.m_szCivName,p.m_szCivType,p.m_szTeamColor,p.m_szEra,p.m_szHandicap,p.m_uiCulture,p.m_uiGold,p.m_uiStartX,p.m_uiStartY,p.m_byTeam,p.m_bPlayable,static_cast<uint>(p.m_kPolicies.count()));}
}
static void Types(CvWorldBuilderMapTypeDesc& t) {
    t.m_kTerrainTypes.Add("TERRAIN_GRASS");t.m_kTerrainTypes.Add("TERRAIN_PLAINS");
    t.m_kFeatures.Add("FEATURE_FOREST");t.m_kNaturalWonders.Add("FEATURE_CRATER");t.m_kResources.Add("RESOURCE_IRON");
    t.m_kImprovements.Add("IMPROVEMENT_MINE");t.m_kUnits.Add("UNIT_WARRIOR");t.m_kBuildingTypes.Add("BUILDING_MONUMENT");
    t.m_kTechs.Add("TECH_AGRICULTURE");t.m_kPolicies.Add("POLICY_TRADITION");t.m_kUnitPromotions.Add("PROMOTION_SCOUTING_1");
}
static void Populate(CvWorldBuilderMap& m) {
    m.Resize(4,3);m.SetPlayerCount(3);m.SetCityStateCount(2);m.SetTeamCount(5);m.SetWorldType("WORLDSIZE_SMALL");m.SetDefaultGameSpeed("GAMESPEED_QUICK");
    m.SetStartYear(-3000);m.SetMaxTurns(400);m.m_uiFlags=0x13;m.m_sMapName="Fixture map";m.m_sMapDescription="World builder x64 fixture";
    m.m_kVictoryTypes.Add("VICTORY_DOMINATION");m.m_kGameOptions.Add("GAMEOPTION_NO_BARBARIANS");
    for(uint i=0;i<m.GetPlotCount();++i){CvWorldBuilderMap::PlotMapData& p=m.GetPlotData(i);p.SetTerrainType(static_cast<byte>(i%2));p.SetResourceType(i%3?255:0);p.SetResourceAmount(static_cast<byte>(i));p.SetFeatureType(i%4?255:0);p.SetNaturalWonderType(i==7?0:255);p.SetContinentType(1);p.SetFlags(static_cast<byte>(i));p.SetPlotHeight(static_cast<CvWorldBuilderMap::PlotMapData::PlotHeight>(i%3));}
    for(byte i=0;i<3;++i){CvWorldBuilderMap::Player& p=m.GetPlayer(i);std::sprintf(p.m_szCivType,"CIVILIZATION_%u",i);p.m_byTeam=i;p.m_uiStartX=i;p.m_uiStartY=1;p.m_bPlayable=i!=1;p.m_uiGold=100+i;p.m_kPolicies.set(0);}
    m.GetCityState(0).m_byTeam=3;m.GetCityState(1).m_byTeam=4;m.GetCityState(0).m_uiGold=77;
    m.GetTeam(0).m_kTechs.set(0);m.m_kTeamsInContact.Set(0,1,true);m.m_kTeamsAtWar.Set(1,2,true);m.SetVisibility(2,1,0,true);
    CvWorldBuilderMap::Unit::Handle u=m.AddUnit(1,1);CHECK(u.Valid());m.m_kUnits[u]->m_byUnitType=0;m.m_kUnits[u]->m_byOwner=2;m.m_kUnits[u]->m_uiExperience=42;m.m_kUnits[u]->m_kPromotions.set(0);
    CvWorldBuilderMap::City::Handle c=m.m_kCities.Alloc();CHECK(c.Valid());m.GetPlotScenarioData(3,1).m_hCity=c;std::strcpy(m.m_kCities[c]->m_szName,"Test City");m.m_kCities[c]->m_byOwner=1;m.m_kCities[c]->m_kBuildings.set(0);
    m.m_aiCityStateInfluence[1][0]=234;
    m.m_kModData.m_kMapModData.AddField("enabled",true);m.m_kModData.m_kPlotModData.AddField("score",2.5f);m.m_kModData.InitDataEntries(m.GetPlotCount());
    m.m_kModData.GetMapDataEntry().SetFieldToDefault(0);for(uint i=0;i<m.GetPlotCount();++i)m.m_kModData.GetPlotDataEntry(i).SetFieldToDefault(0);
}
int main(int argc,char** argv) {
    InstallWorldMapFileHost();std::auto_ptr<CvWorldBuilderMap> m(new CvWorldBuilderMap);CvWorldBuilderMapTypeDesc types;Types(types);
    // Pre-v10 files have no influence section. Define the fixture's prior state
    // rather than hash incidental bytes left by the archived constructor.
    std::memset(m->m_aiCityStateInfluence,0,sizeof(m->m_aiCityStateInfluence));
    std::printf("SIZES|%u|%u|%u|%u|%u\n",static_cast<uint>(sizeof(CvWorldBuilderMap::Unit)),static_cast<uint>(sizeof(CvWorldBuilderMap::City)),static_cast<uint>(sizeof(CvWorldBuilderMap::Player)),static_cast<uint>(sizeof(CvWorldBuilderMap::Team)),static_cast<uint>(sizeof(CvWorldBuilderMap::PlotScenarioData)));
    if(argc<2 || !std::strcmp(argv[1],"baseline")){Dump(*m);m->Resize(2,2);Dump(*m);m->SetPlayerCount(1);Dump(*m);}
    else if(!std::strcmp(argv[1],"write")){
        Populate(*m);Dump(*m);worldMapTraceIO=true;CHECK(m->Save(L"memory",types,argc<4 || std::strcmp(argv[3],"plain")));worldMapTraceIO=false;
        CHECK(argc>=3);FILE* f=std::fopen(argv[2],"wb");CHECK(f!=NULL);CHECK(std::fwrite(&worldMapFile[0],1,worldMapFile.size(),f)==worldMapFile.size());CHECK(!std::fclose(f));
        std::printf("BYTES|%u\n",static_cast<uint>(worldMapFile.size()));
    } else if(!std::strcmp(argv[1],"read") || !std::strcmp(argv[1],"inspect")){
        CHECK(argc>=3);FILE* f=std::fopen(argv[2],"rb");CHECK(f!=NULL);CHECK(!std::fseek(f,0,SEEK_END));long n=std::ftell(f);CHECK(n>0);std::rewind(f);worldMapFile.resize(n);CHECK(std::fread(&worldMapFile[0],1,n,f)==static_cast<size_t>(n));CHECK(!std::fclose(f));
        SourceTypes(types,worldMapFile);worldMapTraceIO=true;bool loaded=m->Load(L"memory",types,argc<4 || std::strcmp(argv[3],"plain"));worldMapTraceIO=false;std::printf("LOADED|%u\n",loaded);CHECK(loaded);
        std::printf("SEMANTIC|%08x\n",SemanticHash(*m,argc>4?argv[4]:NULL));
        if(!std::strcmp(argv[1],"inspect"))std::printf("SUMMARY|%u|%u|%u|%u|%u\n",m->GetWidth(),m->GetHeight(),m->GetPlayerCount(),m->GetCityStateCount(),m->GetTeamCount());else Dump(*m);
    }else return 3;
    std::printf("PASS|%u\n",++checks);return 0;
}
