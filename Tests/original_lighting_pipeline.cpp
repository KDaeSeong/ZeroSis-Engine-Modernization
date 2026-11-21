// Exercise the production key/publication policy together with new selectors.
#define main PriorGroundRegressionMain
#include "world_terrain_reuse.cpp"
#undef main
#include "OriginalLightingState.h"

namespace {
void LightingKey(){
    auto view=Fixture();view.lightingAssetsPath=L"original-lighting.sha256";
    const auto key=Capture(view);
    Require(key.Matches(view,80,60,70,11,12));
    auto changed=view;changed.lightingAssetsPath+=L"-different";
    Require(!key.Matches(changed,80,60,70,11,12));
    changed=view;changed.lightingAssetsPath.clear();Require(!key.Matches(changed,80,60,70,11,12));
    auto detached=view;auto owned=Capture(detached);detached.lightingAssetsPath.clear();
    Require(owned.Matches(view,80,60,70,11,12));
    WorldTerrainReuse<Payload> cache;cache.Publish(Capture(view),std::make_unique<Payload>(41));
    const auto* old=Find(cache,view);Require(old&&old->serial==41);
    changed=view;changed.lightingAssetsPath+=L"-candidate";
    auto candidateKey=Capture(changed);auto candidate=std::make_unique<Payload>(42);
    failAllocation=true;bool failed=false;
    try{cache.Publish(std::move(candidateKey),std::move(candidate));}catch(const std::bad_alloc&){failed=true;}
    Require(failed&&!failAllocation&&!candidate&&Find(cache,view)==old&&!Find(cache,changed));
    cache.Publish(Capture(changed),std::make_unique<Payload>(43));
    Require(!Find(cache,view)&&Find(cache,changed)->serial==43);cache.Clear();Require(alive==0);
    for(unsigned tick=0;tick<120;++tick){
        changed=view;changed.animationSeconds=tick/30.0;changed.waterAnimationSeconds=tick/20.0;
        changed.fogAnimationSeconds=tick/10.0;changed.turn=static_cast<int>(tick);
        Require(key.Matches(changed,80,60,70,11,12));
    }
}
template<class Change>void BadLightingGrid(const WorldView& view,Change change){
    auto altered=view;change(altered);bool rejected=false;
    try{OriginalLighting::CaptureLightingSelectors(altered);}catch(const std::invalid_argument&){rejected=true;}
    Require(rejected);
}
void LightingSelectors(){
    WorldView view{};view.gridWidth=40;view.gridHeight=24;
    for(int y=0;y<view.gridHeight;++y)for(int x=0;x<view.gridWidth;++x){
        WorldViewPlot plot{};plot.x=x;plot.y=y;plot.index=y*view.gridWidth+x;
        plot.revealed=(x+y)%3!=0;plot.continent=(x+2*y)%5;plot.water=(x+y)%7==0;
        view.plots.push_back(plot);
    }
    const auto original=OriginalLighting::CaptureLightingSelectors(view);Require(original.size()==960);
    for(std::size_t i=0;i<view.plots.size();++i){
        const auto& plot=view.plots[i];Require(original[i]==(plot.revealed?(plot.water?0:plot.continent):255));
    }
    auto poison=view;
    for(auto& plot:poison.plots)if(!plot.revealed){
        plot.continent=std::numeric_limits<int>::min();plot.water=!plot.water;
        plot.terrainId=std::numeric_limits<int>::max();plot.mountain=true;
        plot.terrain.assign(1024,'X');plot.feature.assign(1024,'Y');
    }
    Require(OriginalLighting::CaptureLightingSelectors(poison)==original);
    poison=view;for(auto& plot:poison.plots)plot.visible=!plot.visible;
    Require(OriginalLighting::CaptureLightingSelectors(poison)==original);
    poison=view;poison.plots.clear();const auto empty=OriginalLighting::CaptureLightingSelectors(poison);
    for(auto selector:empty)Require(selector==255);
    BadLightingGrid(view,[](WorldView& v){v.gridWidth=0;});
    BadLightingGrid(view,[](WorldView& v){v.gridWidth=std::numeric_limits<int>::max();});
    BadLightingGrid(view,[](WorldView& v){v.plots[0].x=-1;});
    BadLightingGrid(view,[](WorldView& v){v.plots[0].y=v.gridHeight;});
    BadLightingGrid(view,[](WorldView& v){v.plots.push_back(v.plots[0]);});
    BadLightingGrid(view,[](WorldView& v){v.plots[1].continent=5;});
    BadLightingGrid(view,[](WorldView& v){v.plots[1].continent=-1;});
    auto water=view;water.plots[1].water=true;water.plots[1].continent=-1;
    Require(OriginalLighting::CaptureLightingSelectors(water)[1]==0);
}
}
int main(){
    if(PriorGroundRegressionMain()!=0)return 1;
    try{
        const unsigned previous=checks;LightingKey();LightingSelectors();Require(alive==0);
        std::printf("PASS_ORIGINAL_LIGHTING_PIPELINE checks=%u prior=%u\n",checks-previous,previous);return 0;
    }catch(const std::exception& error){failAllocation=false;std::fprintf(stderr,"FAIL: %s\n",error.what());return 1;}
}
