#include "WorldTerrainReuse.h"
#include "WorldTerrainRenderer.h"
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <new>
#include <utility>

namespace {bool failAllocation=false;unsigned checks=0;int alive=0,destroyed=0;}
void* operator new(std::size_t size){
    if(failAllocation){failAllocation=false;throw std::bad_alloc();}
    if(void* value=std::malloc(size?size:1))return value;
    throw std::bad_alloc();
}
void operator delete(void* value) noexcept {std::free(value);}
void operator delete(void* value,std::size_t) noexcept {std::free(value);}

using namespace ZeroSisPresentation;
namespace {
void Require(bool value){++checks;if(!value)throw std::runtime_error("Ground cache regression");}
WorldView Fixture(){
    WorldView view{};view.gridWidth=40;view.gridHeight=24;view.wrapX=true;
    view.cameraX=12;view.cameraY=8;view.tileWidth=56;view.terrainAssetsPath=L"sealed-ground.zsterr";
    WorldViewPlot first{};first.index=7;first.x=12;first.y=8;first.continent=2;
    first.revealed=first.visible=true;first.terrain="TERRAIN_GRASS";first.feature="FEATURE_MARSH";
    auto second=first;second.index=9;second.x=13;second.hills=true;
    view.plots={first,second};return view;
}
struct Payload {
    TerrainFrame metadata;int serial;
    explicit Payload(int value):serial(value){++alive;}
    ~Payload(){--alive;++destroyed;}
};
WorldTerrainGroundKey Capture(const WorldView& view){return WorldTerrainGroundKey::Capture(view,80,60,70,11,12);}
const Payload* Find(const WorldTerrainReuse<Payload>& cache,const WorldView& view){return cache.Find(view,80,60,70,11,12);}
template<class Change>void Miss(const WorldTerrainGroundKey& key,Change change){
    auto other=Fixture();change(other);Require(!key.Matches(other,80,60,70,11,12));
}
template<class Change>void Invalid(Change change){
    auto other=Fixture();change(other);bool rejected=false;
    try{Capture(other);}catch(const std::invalid_argument&){rejected=true;}
    Require(rejected);
}
void Keys(){
    auto view=Fixture();auto key=Capture(view);Require(key.Matches(view,80,60,70,11,12));
    Miss(key,[](WorldView& v){++v.gridWidth;});Miss(key,[](WorldView& v){++v.gridHeight;});
    Miss(key,[](WorldView& v){++v.cameraX;});Miss(key,[](WorldView& v){++v.cameraY;});
    Miss(key,[](WorldView& v){v.wrapX=!v.wrapX;});Miss(key,[](WorldView& v){v.wrapY=!v.wrapY;});
    Miss(key,[](WorldView& v){v.tileWidth+=8;});Miss(key,[](WorldView& v){v.terrainAssetsPath+=L"-changed";});
    Miss(key,[](WorldView& v){v.plots.pop_back();});Miss(key,[](WorldView& v){std::swap(v.plots[0],v.plots[1]);});
    Miss(key,[](WorldView& v){++v.plots[0].index;});Miss(key,[](WorldView& v){++v.plots[0].x;});
    Miss(key,[](WorldView& v){++v.plots[0].y;});Miss(key,[](WorldView& v){++v.plots[0].continent;});
    Miss(key,[](WorldView& v){v.plots[0].revealed=false;});Miss(key,[](WorldView& v){v.plots[0].visible=false;});
    Miss(key,[](WorldView& v){v.plots[0].water=true;});Miss(key,[](WorldView& v){v.plots[0].hills=true;});
    Miss(key,[](WorldView& v){v.plots[0].mountain=true;});Miss(key,[](WorldView& v){v.plots[0].terrain+="_CHANGED";});
    Miss(key,[](WorldView& v){v.plots[0].feature.clear();});
    Miss(key,[](WorldView& v){++v.mapRandomSeed;});
    Miss(key,[](WorldView& v){v.plots[0].naturalWonder=true;});
    Miss(key,[](WorldView& v){++v.plots[0].terrainId;});
    Require(!key.Matches(view,81,60,70,11,12));Require(!key.Matches(view,80,61,70,11,12));
    Require(!key.Matches(view,80,60,69,11,12));Require(!key.Matches(view,80,60,70,13,12));
    Require(!key.Matches(view,80,60,70,11,13));
    auto detached=view;auto owned=Capture(detached);detached.plots[0].terrain.assign(512,'X');detached.plots.clear();
    Require(owned.Matches(view,80,60,70,11,12));
    auto unitOnly=view;unitOnly.turn=9;unitOnly.activePlayer=2;unitOnly.selectedCity=5;
    unitOnly.fullScreenUi=unitOnly.originalTopPanel=unitOnly.originalActionInfoPanel=unitOnly.originalUnitPanel=true;
    unitOnly.status=L"UI changed";unitOnly.unitActionPage=4;unitOnly.unitAssetsPath=L"units-new";
    unitOnly.plots[0].improvementType=8;unitOnly.plots[0].routeType=3;
    unitOnly.plots[0].improvementPillaged=unitOnly.plots[0].routePillaged=true;
    unitOnly.plots[0].improvementName=L"Improvement";unitOnly.plots[0].routeName=L"Route";
    unitOnly.units.push_back(WorldViewUnit{});unitOnly.cities.push_back(WorldViewCity{});
    unitOnly.unitActions.push_back({1,L"Action"});
    for(unsigned tick=0;tick<120;++tick){
        unitOnly.animationSeconds=static_cast<double>(tick)/30;
        unitOnly.units[0].x=static_cast<int>(tick);unitOnly.units[0].facingDirection=static_cast<int>(tick%6);
        Require(key.Matches(unitOnly,80,60,70,11,12));
    }
    Invalid([](WorldView& v){v.gridWidth=0;});Invalid([](WorldView& v){v.gridHeight=-1;});
    Invalid([](WorldView& v){v.tileWidth=23;});Invalid([](WorldView& v){v.tileWidth=113;});
    Invalid([](WorldView& v){v.tileWidth=std::numeric_limits<float>::quiet_NaN();});
    Invalid([](WorldView& v){v.tileWidth=std::numeric_limits<float>::infinity();});
    const std::array<unsigned,3> invalidDimensions[]={{0,60,1},{80,0,1},{4097,60,70},{80,4097,70},{80,60,0},{80,60,81}};
    for(const auto& dims:invalidDimensions){
        bool rejected=false;try{WorldTerrainGroundKey::Capture(view,dims[0],dims[1],dims[2],0,0);}
        catch(const std::invalid_argument&){rejected=true;}Require(rejected);
    }
    Require(WorldTerrainGroundKey::Capture(view,4096,4096,4096,0,0).Matches(view,4096,4096,4096,0,0));
}
void Publication(){
    auto view=Fixture();WorldTerrainReuse<Payload> cache;Require(!Find(cache,view));
    auto first=std::make_unique<Payload>(1);
    first->metadata.picking.indices={0,1,2,1};first->metadata.picking.keys={107,109};
    first->metadata.centers[7]={1.5f,2.5f};first->metadata.projectedPlots[7].spans.push_back({2,1,3});
    first->metadata.triangles=24;
    cache.Publish(Capture(view),std::move(first));const auto* saved=Find(cache,view);
    Require(saved && saved->serial==1 && alive==1);
    TerrainFrame returned=saved->metadata;Scene scene{};WorldViewProjection projection{};
    scene.pixelHits=std::move(returned.picking);projection.plots=std::move(returned.projectedPlots);
    scene.pixelHits.indices.clear();scene.pixelHits.keys.clear();projection.plots.clear();
    Require(Find(cache,view)==saved);Require(saved->metadata.picking.indices==std::vector<std::uint32_t>({0,1,2,1}));
    Require(saved->metadata.picking.keys==std::vector<std::uint64_t>({107,109}));
    Require(saved->metadata.projectedPlots.at(7).spans[0]==std::array<int,3>({2,1,3}));
    Require(saved->metadata.centers.at(7).x==1.5f && saved->metadata.triangles==24);
    bool rejected=false;try{cache.Publish(Capture(view),nullptr);}catch(const std::invalid_argument&){rejected=true;}
    Require(rejected && Find(cache,view)==saved && alive==1);
    auto changed=view;++changed.cameraX;auto key=Capture(changed);auto second=std::make_unique<Payload>(2);
    const int oldDestroyed=destroyed;failAllocation=true;bool failed=false;
    try{cache.Publish(std::move(key),std::move(second));}catch(const std::bad_alloc&){failed=true;}
    Require(failed && !failAllocation && !second && Find(cache,view)==saved && !Find(cache,changed));
    Require(alive==1 && destroyed==oldDestroyed+1);
    cache.Publish(Capture(changed),std::make_unique<Payload>(3));
    Require(!Find(cache,view) && Find(cache,changed)->serial==3 && alive==1);
    Require(destroyed==oldDestroyed+2);cache.Clear();Require(!Find(cache,changed) && alive==0);
    cache.Clear();Require(alive==0);
}
}
int main(){
    try{Keys();Publication();Require(alive==0);std::printf("PASS_WORLD_TERRAIN_REUSE checks=%u\n",checks);return 0;}
    catch(const std::exception& ex){failAllocation=false;std::fprintf(stderr,"FAIL: %s\n",ex.what());return 1;}
}
