#include "OriginalLightingModel.h"
#include "WorldViewRenderer.h"
#include "OriginalLightingFieldModel.h"
#include "OriginalLightingFieldBinding.h"
#include <memory>
#include <cstdio>
#include <limits>
namespace O=ZeroSisPresentation::OriginalWaterOptics;

namespace FieldPipeline {
using namespace ZeroSisPresentation;
unsigned assertions=0,loads=0,builds=0,failAt=0;
void Test(bool value){++assertions;if(!value)throw std::runtime_error("Lighting field integration failed");}
void Require(bool value,const char* message){if(!value)throw std::runtime_error(message);}
struct Handle {const void* Get() const noexcept{return this;}};
struct LightingField {Handle normal,shadow;};
struct LightingFieldBaker {};
struct OriginalCatalog {};
struct OriginalGpuMesh {
    OriginalTerrain::ChunkSlots slots;unsigned column=0,row=0;
    std::unique_ptr<LightingField> lightingField;
};
struct OriginalSurface {OriginalTerrain::Atlas atlas;};
struct OriginalDraw {std::shared_ptr<OriginalGpuMesh> mesh;};
struct OriginalGroundData {std::shared_ptr<OriginalSurface> surface;std::vector<OriginalDraw> draws;};
struct Cache {
    std::unique_ptr<OriginalCatalog> original=std::make_unique<OriginalCatalog>();
    std::unique_ptr<LightingFieldBaker> lightingFieldBaker;
};
std::unique_ptr<LightingFieldBaker> LoadLightingFieldBaker(Cache&){++loads;return std::make_unique<LightingFieldBaker>();}
std::unique_ptr<LightingField> BuildLightingField(Cache&,LightingFieldBaker&,OriginalCatalog&,OriginalSurface&,
    const OriginalGpuMesh&,const std::vector<unsigned char>& known,const std::vector<std::uint16_t>& shadow,float strength){
    ++builds;Test(known.size()==68*68&&shadow.size()==66*66&&strength==16);
    for(auto value:known)Test(value<=1);
    for(auto value:shadow)Test(value<=8192); // Current bias/strength .125, UNORM16 rounded.
    if(builds==failAt)throw std::runtime_error("Injected private GPU allocation failure");
    return std::make_unique<LightingField>();
}
#include "OriginalLightingFieldBridge.inc"

WorldView View(){
    WorldView view{};view.gridWidth=4;view.gridHeight=2;view.wrapX=true;
    for(int y=0;y<2;++y)for(int x=0;x<4;++x){WorldViewPlot plot{};plot.x=x;plot.y=y;
        plot.index=y*4+x;plot.revealed=true;plot.visible=true;view.plots.push_back(plot);}
    return view;
}
OriginalGroundData Ground(const WorldView& view){
    OriginalGroundData ground;ground.surface=std::make_shared<OriginalSurface>();auto& a=ground.surface->atlas;
    a.width=static_cast<unsigned>(view.gridWidth)*64;a.height=static_cast<unsigned>(view.gridHeight)*64;
    a.originX=-32;a.originY=0;a.wrapX=view.wrapX;a.wrapY=view.wrapY;
    a.ids.assign(static_cast<std::size_t>(a.width)*a.height,0);a.known.assign(a.ids.size(),1);
    a.heights.assign(a.ids.size(),0.32f-OriginalTerrain::HeightOffsetCandidate);
    auto first=std::make_shared<OriginalGpuMesh>();first->column=1;first->slots.count=1;
    auto second=std::make_shared<OriginalGpuMesh>();second->column=2;second->slots.count=1;
    auto empty=std::make_shared<OriginalGpuMesh>();empty->column=3;empty->slots.count=0;
    ground.draws={{first},{first},{second},{empty}};return ground;
}
void Ownership(){
    auto view=View();auto ground=Ground(view);Cache cache;
    PrepareLightingFields(view,cache,ground);Test(loads==1&&builds==2);
    const auto* first=ground.draws[0].mesh->lightingField.get();
    Test(first&&ground.draws[1].mesh->lightingField.get()==first&&ground.draws[2].mesh->lightingField);
    Test(!ground.draws[3].mesh->lightingField);
    // An invalid unused snapshot proves the ready-field return occurs before
    // any capture or sampling. Main renderer still validates its own view.
    auto unused=view;unused.gridWidth=0;unused.plots.clear();
    for(unsigned tick=0;tick<120;++tick){unused.animationSeconds=tick/30.0;PrepareLightingFields(unused,cache,ground);}
    Test(loads==1&&builds==2&&ground.draws[0].mesh->lightingField.get()==first);
    auto extra=std::make_shared<OriginalGpuMesh>();extra->column=0;extra->row=1;extra->slots.count=1;
    ground.draws.push_back({extra});failAt=builds+1;bool rejected=false;
    try{PrepareLightingFields(view,cache,ground);}catch(const std::runtime_error&){rejected=true;}
    Test(rejected&&!extra->lightingField&&ground.draws[0].mesh->lightingField.get()==first&&loads==1);
    failAt=0;PrepareLightingFields(view,cache,ground);Test(extra->lightingField!=nullptr&&loads==1&&builds==4);
    auto next=Ground(view);PrepareLightingFields(view,cache,next);Test(builds==6&&loads==1);
    Test(next.draws[0].mesh->lightingField.get()!=first);
    auto noMaterial=Ground(view);for(auto& draw:noMaterial.draws)draw.mesh->slots.count=0;Cache other;
    PrepareLightingFields(unused,other,noMaterial);Test(!other.lightingFieldBaker&&loads==1&&builds==6);
}
void FinalComposition(){
    namespace Lighting=ZeroSisPresentation::OriginalLighting;
    namespace Binding=Lighting::FieldBinding;
    Lighting::TerrainFinalInput input;input.litCache={0.25,0.5,0.75};input.specularCache={0.5,0.25,0.125};
    input.screenLight={Binding::ScreenLightCandidate,Binding::ScreenLightCandidate,Binding::ScreenLightCandidate};
    input.useScreenLight=true;
    const auto result=Lighting::TerrainCacheCombination(input);
    const double a[3]={0.25,0.5,0.75},b[3]={0.5,0.25,0.125},actual[3]={result.x,result.y,result.z};
    for(unsigned i=0;i<3;++i){const double expected=std::pow(std::pow(a[i],O::ShaderGamma)+std::pow(b[i],O::ShaderGamma),O::ShaderInverseGamma);
        Test(std::abs(actual[i]-expected)<1e-12);}
    input.screenLight={0,0,0};const auto none=Lighting::TerrainCacheCombination(input);
    Test(std::abs(none.x-input.litCache.x)<1e-7&&std::abs(none.y-input.litCache.y)<1e-7&&std::abs(none.z-input.litCache.z)<1e-7);
    input.useScreenLight=false;input.specularCache={(std::numeric_limits<double>::quiet_NaN)(),0,0};
    const auto disabled=Lighting::TerrainCacheCombination(input);Test(disabled.x==input.litCache.x);
    const auto defaults=Lighting::Field::ShadowParams{};
    Test(defaults.directionX==Binding::ShadowDirectionX&&defaults.directionY==Binding::ShadowDirectionY);
    Test(defaults.texelWorldX==Binding::TexelWorldX&&defaults.texelWorldY==Binding::TexelWorldY);
    Test(defaults.heightScale==Binding::ShadowHeightScale&&defaults.heightOffset==Binding::ShadowHeightOffset&&defaults.biasAndStrength==Binding::ShadowBiasAndStrength);
    Test(Lighting::Field::NormalPolicy{}.strength==Binding::NormalStrength);
}
}
int main(){
    try{FieldPipeline::Ownership();FieldPipeline::FinalComposition();
        std::printf("PASS_LIGHTING_FIELD_PIPELINE checks=%u builds=%u loads=%u\n",FieldPipeline::assertions,FieldPipeline::builds,FieldPipeline::loads);return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"Field pipeline: %s\n",error.what());return 1;}
}
