#include "WorldTerrainReuse.h"
#include "OriginalWaterState.h"
#include <cstdio>
#include <algorithm>

using namespace ZeroSisPresentation;
namespace Water=ZeroSisPresentation::OriginalWater;
namespace {
unsigned checks=0;
void Check(bool value,const char* reason){++checks;if(!value)throw std::runtime_error(reason);}
WorldView Fixture(){
    WorldView view{};view.gridWidth=4;view.gridHeight=4;view.wrapX=view.wrapY=true;
    view.cameraX=view.cameraY=1;view.tileWidth=56;view.terrainAssetsPath=L"ground-package";
    view.waterAssetsPath=L"water-package";view.fogAssetsPath=L"fog-package";
    for(int y=0;y<4;++y)for(int x=0;x<4;++x){WorldViewPlot plot{};plot.index=y*4+x;plot.x=x;plot.y=y;
        plot.revealed=plot.visible=true;plot.water=x%2!=0;plot.continent=plot.water?0:2;plot.terrainId=plot.water?6:0;
        plot.terrain=plot.water?"TERRAIN_OCEAN":"TERRAIN_GRASS";view.plots.push_back(plot);}
    view.plots[5].riverW=true;view.plots[5].flowE=0;
    view.plots[6].riverNW=true;view.plots[6].flowSE=1;
    view.plots[7].riverNE=true;view.plots[7].flowSW=2;
    return view;
}
WorldTerrainGroundKey Ground(const WorldView& view){return WorldTerrainGroundKey::Capture(view,80,60,70,11,12);}
template<class Change>void Mutation(Change change,bool groundSame,bool waterSame){
    const auto original=Fixture();const auto ground=Ground(original);const auto water=Water::CaptureWaterGrid(original);
    auto other=original;change(other);
    Check(ground.Matches(other,80,60,70,11,12)==groundSame,"Ground invalidation differs from separated water key policy");
    Check(Water::SameWaterGrid(water,Water::CaptureWaterGrid(other))==waterSame,"Water topology invalidation differs from ground key policy");
}
void Keys(){
    Mutation([](WorldView& v){v.plots[0].riverW=true;v.plots[0].flowE=0;},true,false);
    Mutation([](WorldView& v){v.plots[0].riverNW=true;v.plots[0].flowSE=1;},true,false);
    Mutation([](WorldView& v){v.plots[0].riverNE=true;v.plots[0].flowSW=2;},true,false);
    Mutation([](WorldView& v){v.plots[5].flowE=3;},true,false);
    Mutation([](WorldView& v){v.plots[6].flowSE=4;},true,false);
    Mutation([](WorldView& v){v.plots[7].flowSW=5;},true,false);
    Mutation([](WorldView& v){v.plots[5].flowE=-1;},true,false);
    Mutation([](WorldView& v){v.plots[0].flowE=v.plots[0].flowSE=v.plots[0].flowSW=999;},true,true);
    Mutation([](WorldView& v){v.plots[0].visible=false;},false,true);
    Mutation([](WorldView& v){v.plots[0].revealed=v.plots[0].visible=false;},false,false);
    Mutation([](WorldView& v){v.plots[0].water=true;},false,false);
    Mutation([](WorldView& v){v.plots[0].hills=true;},false,false);
    Mutation([](WorldView& v){v.plots[0].mountain=true;},false,false);
    Mutation([](WorldView& v){v.plots[0].terrainId=2;},false,false);
    Mutation([](WorldView& v){v.plots[1].lake=true;},true,false);
    Mutation([](WorldView& v){++v.cameraX;},false,true);
    Mutation([](WorldView& v){++v.cameraY;},false,true);
    Mutation([](WorldView& v){v.tileWidth+=8;},false,true);
    Mutation([](WorldView& v){++v.mapRandomSeed;},false,true);
    Mutation([](WorldView& v){v.animationSeconds=1.25;},true,true);
    Mutation([](WorldView& v){v.fogAnimationSeconds=2.5;},true,true);
    Mutation([](WorldView& v){v.waterAnimationSeconds=4.75;},true,true);
    Mutation([](WorldView& v){v.waterAssetsPath+=L"-new";},true,true);
    Mutation([](WorldView& v){v.fogAssetsPath+=L"-new";},true,true);
    Mutation([](WorldView& v){v.terrainAssetsPath+=L"-new";},false,true);
    Mutation([](WorldView& v){v.unitAssetsPath+=L"-new";},true,true);
    Mutation([](WorldView& v){++v.turn;++v.activePlayer;v.selectedCity=4;v.units.push_back(WorldViewUnit{});},true,true);
    Mutation([](WorldView& v){std::reverse(v.plots.begin(),v.plots.end());},false,true);
    Mutation([](WorldView& v){v.plots[0].improvementType=19;v.plots[0].routeType=3;},true,true);
    auto original=Fixture();const auto ground=Ground(original);const auto water=Water::CaptureWaterGrid(original);
    Check(!ground.Matches(original,81,60,70,11,12),"Viewport change reused ground key");
    Check(!ground.Matches(original,80,61,70,11,12),"Viewport height reused ground key");
    Check(!ground.Matches(original,80,60,69,11,12),"Map viewport reused ground key");
    Check(!ground.Matches(original,80,60,70,13,12),"Device change reused ground key");
    Check(!ground.Matches(original,80,60,70,11,13),"Context change reused ground key");
    Check(Water::SameWaterGrid(water,Water::CaptureWaterGrid(original)),"Device/viewport check changed detached state");
    auto detached=original;detached.plots[0].water=true;detached.plots.clear();
    Check(ground.Matches(original,80,60,70,11,12),"Owned ground snapshot changed with detached input");
    Check(Water::SameWaterGrid(water,Water::CaptureWaterGrid(original)),"Owned water snapshot changed with detached input");
}
}
int main(){try{Keys();std::printf("PASS_ORIGINAL_WATER_CACHE_KEYS checks=%u\n",checks);return 0;}
catch(const std::exception& error){std::fprintf(stderr,"Water/ground key separation: %s\n",error.what());return 1;}}
