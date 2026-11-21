#ifdef ZEROSIS_MAP_OPERATIONS_ONLY
// Generated verbatim from the sealed file fixture, excluding only its file-I/O
// entry point. The same Dump/Populate code runs in both architectures.
#include "map_fixture_operations.h"
#else
#define main MapFileReferenceMain
#include "sdk_world_builder_map.cpp"
#undef main
#endif

static void UnitRow(const char* label,const CvWorldBuilderMap::Unit& u) {
    std::printf("UNIT|%s|%u|%u|%u|%u|%u|%u|%u|%u|%u\n",label,u.m_hStackedUnit.ToWord(),u.m_hCustomName.ToWord(),u.m_uiExperience,u.m_uiHealth,u.m_byUnitType,u.m_byOwner,u.m_byDirection,u.m_byFlags,static_cast<unsigned>(u.m_kPromotions.count()));
}
static void CityRow(const char* label,const CvWorldBuilderMap::City& c) {
    std::printf("CITY|%s|%s|%u|%u|%u|%u|%u\n",label,c.m_szName,c.m_byOwner,c.m_byFlags,c.m_wPopulation,c.m_uiHealth,static_cast<unsigned>(c.m_kBuildings.count()));
}
static std::string stateOutputDirectory;
static void State(const char* label,const CvWorldBuilderMap& m) {
    const std::string output=stateOutputDirectory+"/"+label+".bin";
    std::printf("STATE|%s|%08x\n",label,SemanticHash(m,stateOutputDirectory.empty()?NULL:output.c_str()));Dump(m);
    for(uint i=0;i<m.GetPlotCount();++i){CvWorldBuilderMap::Unit::Handle u=m.GetPlotScenarioData(i).m_hUnitStack;unsigned limit=0;
        while(u.Valid()){CHECK(++limit<100);const CvWorldBuilderMap::Unit* p=m.m_kUnits[u];CHECK(p!=NULL);UnitRow(label,*p);u=p->m_hStackedUnit;}}
    std::printf("POOLS|%u|%u|%u|%u|%u|%u\n",m.m_kUnits.GetSerializedSize(),m.m_kCities.GetSerializedSize(),m.m_kUnitNames.GetSerializedSize(),m.m_kModData.m_kMapModData.GetFieldCount(),m.m_kModData.m_kPlotModData.GetFieldCount(),static_cast<uint>(m.m_kModData.GetSerializedSize()));
}
int main(int argc,char** argv) {
#ifndef ZEROSIS_MAP_OPERATIONS_ONLY
    InstallWorldMapFileHost();
#endif
    (void)&Types;(void)&SourceTypes; // Shared palette helpers are used by file tests.
    CHECK(argc==2 || argc==3);const char* mode=argv[1];if(argc==3)stateOutputDirectory=argv[2];
    std::printf("LAYOUT|%u|%u|%u|%u\n",static_cast<uint>(sizeof(CvWorldBuilderMap::Unit)),static_cast<uint>(sizeof(CvWorldBuilderMap::City)),static_cast<uint>(sizeof(CvWorldBuilderMap::Player)),static_cast<uint>(sizeof(CvWorldBuilderMap::Team)));
    std::auto_ptr<CvWorldBuilderMap> m(new CvWorldBuilderMap);std::memset(m->m_aiCityStateInfluence,0,sizeof(m->m_aiCityStateInfluence));
    if(!std::strcmp(mode,"defaults")) {
        CvWorldBuilderMap::Unit u;CvWorldBuilderMap::City c;UnitRow("new",u);CityRow("new",c);
        CvWorldBuilderMap::OldUnit old;old.m_wExperience=123;old.m_fHealth=0.375f;old.m_byUnitType=7;old.m_byOwner=8;old.m_byDirection=5;old.m_bFortified=true;old.m_bEmbarked=true;
        CvWorldBuilderMap::Unit converted(old);UnitRow("old",converted);
        CvWorldBuilderMap::UnitV2 v2;v2.m_uiExperience=4321;v2.m_uiHealth=12345;v2.m_byUnitType=255;v2.m_byOwner=33;v2.m_byDirection=6;v2.m_byFlags=7;v2.m_kPromotions.set(255);
        CvWorldBuilderMap::UnitName::Map names;v2.m_hCustomName=names.Alloc();CHECK(v2.m_hCustomName.Valid());
        CvWorldBuilderMap::Unit converted2(v2);UnitRow("v2",converted2);std::printf("V2-NAME|%u|%u\n",v2.m_hCustomName.ToWord(),converted2.m_hCustomName.ToWord());
        CvWorldBuilderMap::OldCity oldc;std::strcpy(oldc.m_szName,"OldCity");oldc.m_uiPopulation=123;oldc.m_uiCulture=987;oldc.m_byOwner=32;oldc.m_bLocalizedName=true;oldc.m_kBuildings.set(255);
        CvWorldBuilderMap::City cc(oldc);CityRow("old",cc);
        CvWorldBuilderMap::CityV2 c2;std::strcpy(c2.m_szName,"CityV2");c2.m_wPopulation=91;c2.m_uiHealth=56789;c2.m_byFlags=7;c2.m_byOwner=17;c2.m_kBuildings.set(255);
        CvWorldBuilderMap::City cc2(c2);CityRow("v2",cc2);
        State("empty",*m);m->SetPlayerCount(1);m->SetCityStateCount(1);m->SetTeamCount(1);State("default-counts",*m);
    }else if(!std::strcmp(mode,"resize")) {
        m->Resize(4,3);for(uint i=0;i<12;++i)m->GetPlotData(i).SetTerrainType(static_cast<byte>(i+1));State("original",*m);
        m->Resize(3,4);State("narrow",*m);m->Resize(6,5);State("grow",*m);m->Resize(2,2);State("shrink",*m);
    }else if(!std::strcmp(mode,"clear") || !std::strcmp(mode,"preserve")) {
        Populate(*m);m->GetPlotScenarioData(0).m_byCulture=2;m->GetPlotScenarioData(0).m_byImprovement=3;m->GetPlotScenarioData(0).m_byRoute=1;m->GetPlotScenarioData(0).m_byRouteOwner=2;
        State("before",*m);m->ClearScenarioData(!std::strcmp(mode,"preserve"));State("after",*m);
    }else if(!std::strcmp(mode,"swap")) {
        Populate(*m);m->GetPlotScenarioData(0).m_byCulture=0;m->GetPlotScenarioData(1).m_byCulture=2;m->GetPlotScenarioData(2).m_byCulture=32;m->GetPlotScenarioData(3).m_byCulture=33;
        m->GetPlotScenarioData(0).m_byRouteOwner=0;m->GetPlotScenarioData(1).m_byRouteOwner=2;
        for(uint i=0;i<32;++i)for(uint j=0;j<64;++j)m->m_aiCityStateInfluence[i][j]=static_cast<int>(i*1000+j);
        State("before",*m);m->SwapPlayers(0,2);State("major",*m);m->SwapCityStates(0,1);State("minor",*m);
        std::printf("EXTRA|%d|%d|%d|%d\n",m->m_aiCityStateInfluence[0][0],m->m_aiCityStateInfluence[2][1],m->m_aiCityStateInfluence[31][0],m->m_aiCityStateInfluence[31][1]);
    }else if(!std::strcmp(mode,"units")) {
        m->Resize(3,3);CvWorldBuilderMap::Unit::Handle a=m->AddUnit(1,1),b=m->AddUnit(1,1),c=m->AddUnit(1,1);CHECK(a.Valid() && b.Valid() && c.Valid());
        m->m_kUnits[a]->m_uiExperience=10;m->m_kUnits[b]->m_uiExperience=20;m->m_kUnits[c]->m_uiExperience=30;State("three",*m);
        CHECK(m->RemoveUnit(1,1,b));CHECK(!b.Valid());State("middle",*m);CHECK(m->RemoveUnit(1,1,c));State("head",*m);CHECK(m->RemoveUnit(1,1,a));State("none",*m);
    }else if(!std::strcmp(mode,"resize-fields")) {
        Populate(*m);m->GetPlotScenarioData(11).m_byCulture=2;m->m_kModData.GetPlotDataEntry(11).SetField(0,71.0f);
        State("populated",*m);m->Resize(2,2);State("small",*m);m->Resize(4,3);State("restored",*m);
        std::printf("RESIZE-FIELDS|%f|%u|%u\n",m->m_kModData.GetPlotDataEntry(11).GetFieldAsFloat(0),m->m_kUnits.GetSerializedSize(),m->m_kCities.GetSerializedSize());
    }else if(!std::strcmp(mode,"ownership")) {
        Populate(*m);CvWorldBuilderMap::Unit::Handle orphan=m->m_kUnits.Alloc();m->m_kUnits[orphan]->m_byOwner=2;
        CvWorldBuilderMap::City::Handle orphanCity=m->m_kCities.Alloc();m->m_kCities[orphanCity]->m_byOwner=2;
        CvWorldBuilderMap::Unit::Handle u=m->GetPlotScenarioData(5).m_hUnitStack;
        CvWorldBuilderMap::UnitName::Handle name=m->m_kUnitNames.Alloc();std::strcpy(m->m_kUnitNames[name]->m_szText,"Custom");m->m_kUnits[u]->m_hCustomName=name;
        m->SwapPlayers(0,2);std::printf("ORPHANS|%u|%u\n",m->m_kUnits[orphan]->m_byOwner,m->m_kCities[orphanCity]->m_byOwner);
        CHECK(m->RemoveUnit(1,1,u));CvWorldBuilderMap::UnitName::Handle next=m->m_kUnitNames.Alloc();
        std::printf("NAME-REUSE|%u|%u\n",name.ToWord(),next.ToWord());
        m->m_kTeamsAtWar.Set(0,4,true);m->m_kTeamsSharingOpenBorders.Set(0,4,true);
        m->ClearScenarioData();m->SetPlayerCount(3);m->SetCityStateCount(2);m->SetTeamCount(5);State("cleared-reenabled",*m);
        std::printf("CLEAR-EXTRA|%u|%u|%u|%u|%d\n",m->m_kTeamsAtWar.Get(0,4),m->m_kTeamsSharingOpenBorders.Get(0,4),m->GetVisibility(2,1,0),m->GetCityState(0).m_uiGold,m->m_aiCityStateInfluence[1][0]);
    }else if(!std::strcmp(mode,"all-plots")) {
        m->Resize(2,2);m->GetPlotData(1).SetTerrainType(7);m->GetPlotScenarioData(1).m_byImprovement=9;
        m->SetAllPlotData(m->GetPlotData(1),m->GetPlotScenarioData(1));m->Resize(3,3);State("all",*m);
        m->Resize(1,1);m->ClearScenarioData(true);m->Resize(3,3);State("hidden-preserved",*m);
        m->Resize(1,1);m->ClearScenarioData(false);m->Resize(3,3);State("hidden-cleared",*m);
    }else if(!std::strcmp(mode,"hidden-handles")) {
        Populate(*m);m->Resize(1,1);m->ClearScenarioData();m->Resize(4,3);
        // Do not dereference the archived dangling handles.
        std::printf("HIDDEN-HANDLES|%u|%u|%u|%u\n",m->GetPlotScenarioData(5).m_hUnitStack.ToWord(),m->GetPlotScenarioData(7).m_hCity.ToWord(),m->m_kUnits.GetSerializedSize(),m->m_kCities.GetSerializedSize());
    }else if(!std::strcmp(mode,"legacy")) {
        CvWorldBuilderMap::OldPlayer p;std::strcpy(p.m_szCivType,"LegacyCiv");std::strcpy(p.m_szTeamColor,"LegacyColor");std::strcpy(p.m_szEra,"LegacyEra");std::strcpy(p.m_szHandicap,"LegacyHandicap");
        p.m_uiCulture=31;p.m_uiGold=49;p.m_uiStartX=19;p.m_uiStartY=29;p.m_byTeam=7;p.m_bPlayable=false;p.m_kPolicies.set(255);
        m->SetPlayerCount(1);m->GetPlayer(0)=CvWorldBuilderMap::Player(p);State("legacy-player",*m);
        CvWorldBuilderMap::OldUnit::Map oldUnits;CvWorldBuilderMap::OldUnit::Handle oldHandle=oldUnits.Alloc();CHECK(oldHandle.Valid());
        CvWorldBuilderMap::UnitV2::Map v2Units;CvWorldBuilderMap::UnitV2::Handle v2Handle=v2Units.Alloc();CHECK(v2Handle.Valid());
        for(uint i=0;i<256;++i){CvWorldBuilderMap::OldUnit old;old.m_hStackedUnit=oldHandle;old.m_wExperience=static_cast<word>(i*257);old.m_fHealth=static_cast<float>(i)/255;old.m_byUnitType=static_cast<byte>(i);old.m_byOwner=static_cast<byte>(i%97);old.m_byDirection=static_cast<byte>(i%7);old.m_bFortified=(i&1)!=0;old.m_bEmbarked=(i&2)!=0;
            CvWorldBuilderMap::Unit converted(old);UnitRow("legacy-unit",converted);
            CvWorldBuilderMap::UnitV2 v2;v2.m_hStackedUnit=v2Handle;v2.m_kPromotions.set(i);CvWorldBuilderMap::Unit converted2(v2);CHECK(converted2.m_kPromotions[i]);CHECK(!converted2.m_kPromotions[i+256]);
            CvWorldBuilderMap::CityV2 city;city.m_kBuildings.set(i);CvWorldBuilderMap::City convertedCity(city);CHECK(convertedCity.m_kBuildings[i]);CHECK(!convertedCity.m_kBuildings[i+256]);
        }
    }else return 3;
    std::printf("PASS|%u\n",checks);return 0;
}
