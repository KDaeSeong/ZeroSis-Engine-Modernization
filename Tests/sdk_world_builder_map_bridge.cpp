#ifdef ZEROSIS_MAP_BRIDGE_NATIVE
#include "map_fixture_bridge.h"
#include "SdkWorldBuilderMapBridge.h"
#else
#define main SealedMapReferenceMain
#include "sdk_world_builder_map.cpp"
#undef main
#endif

static void ReadInput(const char* path){FILE* f=std::fopen(path,"rb");CHECK(f!=NULL);CHECK(!std::fseek(f,0,SEEK_END));const long n=std::ftell(f);CHECK(n>0);std::rewind(f);worldMapFile.resize(n);CHECK(std::fread(&worldMapFile[0],1,n,f)==static_cast<size_t>(n));CHECK(!std::fclose(f));}
static void Remap(CvWorldBuilderMapTypeDesc& t,bool missing){
    CvWorldBuilderMapTypeDesc::TypeMap* maps[]={&t.m_kTerrainTypes,&t.m_kFeatures,&t.m_kNaturalWonders,&t.m_kResources,&t.m_kImprovements,&t.m_kUnits,&t.m_kTechs,&t.m_kPolicies,&t.m_kBuildingTypes,&t.m_kUnitPromotions};
    for(unsigned k=0;k<10;++k){std::vector<std::string> values;for(uint i=0;i<maps[k]->Size();++i){const char* value=maps[k]->Get(i);values.push_back(value?value:"");}maps[k]->Clear();
        if(!missing)for(size_t i=values.size();i>0;--i)maps[k]->Add(values[i-1].c_str());}
}
int main(int argc,char** argv){
    (void)&Dump;(void)&Types;CHECK(argc==4 || argc==5);InstallWorldMapFileHost();ReadInput(argv[1]);const std::string mode=argv[2];
    CvWorldBuilderMapTypeDesc types;SourceTypes(types,worldMapFile);if(mode=="reverse" || mode=="missing")Remap(types,mode=="missing");
    std::auto_ptr<CvWorldBuilderMap> map(new CvWorldBuilderMap);std::memset(map->m_aiCityStateInfluence,0,sizeof(map->m_aiCityStateInfluence));
    if(mode=="reuse" || mode=="reuse-plain")Populate(*map);
    const bool scenario=mode!="plain" && mode!="reuse-plain" && (worldMapFile[0]&128)!=0;
    const uint preview=CvWorldBuilderMap::PreviewPlayableCivCount(L"memory");bool loaded=false;
#ifdef ZEROSIS_MAP_BRIDGE_NATIVE
    if(mode=="recover"){
        const ZeroSisWorldBuilder::MapLoadResult result=ZeroSisWorldBuilder::LoadMapBytes(*map,worldMapFile.data(),worldMapFile.size(),types,scenario,ZeroSisWorldBuilder::MapReadPolicy::RebuildInvalidFreeLists);
        loaded=true;std::printf("RECOVERED|%u\n",result.recoveredAllocators);
    }else
#endif
    loaded=map->Load(L"memory",types,scenario);
    std::printf("LOAD|%u|PREVIEW|%u\n",loaded,preview);CHECK(loaded);
    std::printf("STATE|%08x\n",SemanticHash(*map,argv[3]));
    std::printf("SUMMARY|%u|%u|%u|%u|%u|%s|%s\n",map->GetWidth(),map->GetHeight(),map->GetPlayerCount(),map->GetCityStateCount(),map->GetTeamCount(),map->GetWorldType(),map->GetDefaultGameSpeed());
    if(argc==5){CHECK(map->Save(L"memory",types,scenario));FILE* f=std::fopen(argv[4],"wb");CHECK(f!=NULL);CHECK(std::fwrite(&worldMapFile[0],1,worldMapFile.size(),f)==worldMapFile.size());CHECK(!std::fclose(f));}
    std::printf("PASS|%u\n",checks);return 0;
}
