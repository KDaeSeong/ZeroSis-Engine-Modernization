#include "OriginalLightingModel.h"
#include "original_lighting_golden.h"
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <limits>

namespace L=ZeroSisPresentation::OriginalLighting;
namespace O=ZeroSisPresentation::OriginalWaterOptics;
namespace {
unsigned checks=0;const char* section="start";
void Check(bool value,const char* reason){++checks;if(!value)throw std::runtime_error(reason);}
void Near(double a,double b,double tolerance=3e-11){const bool same=std::isfinite(a)&&std::isfinite(b)&&std::abs(a-b)<=tolerance*(1+std::abs(b));
    if(!same)std::fprintf(stderr,"section=%s check=%u actual=%.17g expected=%.17g\n",section,checks,a,b);Check(same,"Lighting independent scalar reference differs");}
void Near(L::Rgb a,L::Rgb b,double tolerance=3e-11){Near(a.x,b.x,tolerance);Near(a.y,b.y,tolerance);Near(a.z,b.z,tolerance);}
void Near(L::Rgba a,L::Rgba b,double tolerance=3e-11){Near(a.r,b.r,tolerance);Near(a.g,b.g,tolerance);Near(a.b,b.b,tolerance);Near(a.a,b.a,tolerance);}
template<class F>void Reject(F fn){bool rejected=false;try{fn();}catch(const std::invalid_argument&){rejected=true;}Check(rejected,"Malformed lighting input was accepted");}
std::uint32_t Bits(double value){const float f=static_cast<float>(value);std::uint32_t result=0;std::memcpy(&result,&f,4);return result;}
L::Rgb Lut(L::Rgb value){return {0.1+0.8*value.x,0.2+0.6*value.y,0.05+0.9*value.z};}
L::Rgb WorldLut(L::Rgb value){return {0.05+0.8*value.x,0.1+0.6*value.y,0.2+0.5*value.z};}
L::Rgb FowLut(L::Rgb value){return {0.01+0.9*value.z,0.02+0.8*value.y,0.03+0.7*value.x};}
L::Rgb Identity(L::Rgb value){return value;}
void Normals(){
    for(const auto& golden:GoldenSobel){const auto actual=L::SobelNormal(golden.height,golden.strength);
        Near(actual.sx,golden.sx);Near(actual.sy,golden.sy);Near(actual.normal,golden.normal);Near(actual.encoded,golden.encoded);
        Near(actual.normal.x*actual.normal.x+actual.normal.y*actual.normal.y+actual.normal.z*actual.normal.z,1);}
    for(const auto& golden:GoldenBasis)Near(L::DecodeTerrainNormal(golden.base,golden.sample),golden.expected);
    Near(L::DecodeTerrainNormal({0,0,2},{0.5,0.5,1}),{0,0,2},0);
    unsigned fetched=0;std::array<bool,8> known={{true,false,true,false,true,false,true,false}};
    const auto guarded=L::GuardedSobel(true,known,0.5,2,[&](unsigned index){Check(known[index],"Unknown Sobel callback executed");++fetched;return index/10.0;});
    const auto expected=L::SobelNormal({{0,0.5,0.2,0.5,0.4,0.5,0.6,0.5}},2);
    Near(guarded.normal,expected.normal);Check(fetched==4,"Guarded Sobel fetched an unused tap");
}
void Bake(){
    for(const auto& golden:GoldenBake){L::TerrainBakeInput input;input.baseNormal=golden.base;input.normalSample=golden.normal;
        input.albedo=golden.albedo;input.shadowR=golden.shadow;input.light=golden.light;input.specular=golden.specular;input.specularEnabled=true;
        unsigned cubeCalls=0,lutCalls=0;
        const auto a=[&](L::Rgb n){++cubeCalls;Near(n,golden.decoded);return golden.cubeA;};
        const auto b=[&](L::Rgb n){++cubeCalls;Near(n,golden.decoded);return golden.cubeB;};
        const auto lut=[&](L::Rgb colour){if(lutCalls==0)Near(colour,golden.diffuseEncoded);else Near(colour,golden.specularEncoded);++lutCalls;return Lut(colour);};
        const auto result=L::BakeTerrain(input,a,b,lut);Check(!result.discarded&&cubeCalls==2&&lutCalls==2,"CacheBake callback or target count differs");
        Near(result.normal,golden.decoded);Near(result.diffuseLinear,golden.diffuseLinear);Near(result.diffuseEncoded,golden.diffuseEncoded);Near(result.diffuse,Lut(golden.diffuseEncoded));
        Near(result.specularLinear,golden.specularLinear);Near(result.specularEncoded,golden.specularEncoded);Near(result.specular,Lut(golden.specularEncoded));Near(result.specularAlpha,golden.specularAlpha);
    }
    L::TerrainBakeInput neutral;neutral.albedo={0.2,0.3,0.4};neutral.specularEnabled=false;
    neutral.specular={-1,-1,-1,(std::numeric_limits<double>::quiet_NaN)()};unsigned luts=0;
    const auto result=L::BakeTerrain(neutral,[](L::Rgb){return L::Rgb{0.1,0.2,0.3};},[](L::Rgb){return L::Rgb{0.4,0.5,0.6};},[&](L::Rgb p){++luts;return p;});
    Check(luts==1&&result.specularAlpha==0,"Disabled specular read the absent target");
}
L::WaterCompositeInput WaterInput(const GoldenWater& row){L::WaterCompositeInput input;
    input.depthSample=row.depth;input.rawHeight=row.height;input.lambert=row.lambert;input.fresnel=row.fresnel;
    input.primary.value=row.g0;input.primary.rejected=row.g0==0;
    input.primaryWide.value=row.wide;input.primaryWide.rejected=row.wide==0;
    input.secondary.value=row.g1;input.secondary.q=row.q2;input.secondary.rejected=row.q2>=16;
    input.primaryLight=row.light0;input.secondaryLight=row.light1;input.reflection={row.reflection,row.reflectionAlpha};
    input.reflectionStrength=row.reflectionStrength;input.shadowSample=row.shadow;input.shadowStrength=row.shadowStrength;return input;
}
void Water(){bool rejectedQKept=false;
    for(const auto& golden:GoldenWaters){const auto input=WaterInput(golden);const auto result=L::AssembleWater(input);
        Near(result.preShadow,golden.preShadow);Near(result.shadowed,golden.shadowed);Near(result.encoded,golden.encoded);
        Near(result.alpha,golden.alpha);Near(result.secondaryDepthTerm,golden.depthTerm);
        if(input.secondary.rejected&&input.secondary.q>=16){Check(result.secondaryDepthTerm>1000,"Rejected secondary Gaussian erased its live q cubed term");rejectedQKept=true;}}
    Check(rejectedQKept,"Water tests missed the original rejected-q lifetime");
    auto input=WaterInput(GoldenWaters[0]);const auto base=L::AssembleWater(input);
    auto changed=input;changed.reflection.alpha=1;const auto alpha=L::AssembleWater(changed);
    Near(base.encoded,alpha.encoded);Near(alpha.alpha,(std::min)(1.0,input.depthSample.a*2));
}
void Final(){
    for(const auto& golden:GoldenFinals){L::TerrainFinalInput input;
        input.litCache=golden.lit;input.specularCache=golden.albedo;input.screenLight=golden.screen;input.useLitCache=golden.useLit;input.useScreenLight=golden.useScreen;
        input.worldMaskSample=golden.worldMask;input.worldMaskStrength=golden.worldStrength;input.replacement=golden.replacement;
        input.post.overlay=golden.overlay;input.post.maskR=golden.r;input.post.maskB=golden.b;input.post.fogFactor=golden.fog;input.post.fogColour=golden.fogColour;
        unsigned world=0,fow=0;
        const auto result=L::FinalTerrain(input,[&](L::Rgb c){++world;Near(c,golden.cached);return WorldLut(c);},
            [&](L::Rgb c){++fow;Near(c,golden.beforeFow);return FowLut(c);});
        Near(result,golden.result);Check(world==1&&fow==1,"Final terrain LUT sequence differs");
    }
    const auto& row=GoldenWaters[2];const auto input=WaterInput(row);L::PostInput post;
    post.overlay={0.02,0.03,0.04,0.25};post.maskR=0.6;post.maskB=0.25;post.fogFactor=0.35;post.fogColour={146.0/255,182.0/255,243.0/255};
    const auto result=L::GuardedWater(true,post,[&](){return input;},FowLut);
    Check(!result.discarded,"Known water incorrectly discarded");Near(result.colour,GoldenWaterPost);
    L::TerrainFinalInput unused;unused.useLitCache=false;unused.useScreenLight=false;
    unused.litCache=unused.specularCache=unused.screenLight={(std::numeric_limits<double>::quiet_NaN)(),0,0};
    Near(L::TerrainCacheCombination(unused),{0,0,0},0);
}
void PrivacyAndConstants(){
    unsigned calls=0;const double nan=(std::numeric_limits<double>::quiet_NaN)();
    volatile bool forbiddenCall=true;
    const auto fetchBake=[&]()->L::TerrainBakeInput{++calls;if(forbiddenCall)throw std::runtime_error("Unknown bake fetched");return {};};
    const auto cube=[&](L::Rgb)->L::Rgb{++calls;if(forbiddenCall)throw std::runtime_error("Unknown cube fetched");return {};};
    const auto fetchFinal=[&]()->L::TerrainFinalInput{++calls;if(forbiddenCall)throw std::runtime_error("Unknown final fetched");return {};};
    const auto fetchWater=[&]()->L::WaterCompositeInput{++calls;if(forbiddenCall)throw std::runtime_error("Unknown water fetched");return {};};
    for(unsigned iteration=0;iteration<100;++iteration){Check(L::GuardedBakeTerrain(false,fetchBake,cube,cube,cube).discarded,"Unknown bake not marked discarded");
        Near(L::GuardedFinalTerrain(false,{0.2,0.3,0.4},fetchFinal,cube,cube),{0.2,0.3,0.4,1},0);
        L::PostInput post;post.maskR=post.maskB=post.fogFactor=nan;post.overlay={nan,nan,nan,nan};
        const auto water=L::GuardedWater(false,post,fetchWater,cube);Check(water.discarded,"Unknown water not discarded");Near(water.colour,{0,0,0,0},0);
        const auto sobel=L::GuardedSobel(false,{{false,false,false,false,false,false,false,false}},nan,nan,[&](unsigned){++calls;return nan;});Near(sobel.encoded,{0.5,0.5,1,0},0);}
    L::PostInput empty;empty.maskR=0;Check(L::GuardedWater(true,empty,fetchWater,cube).discarded,"Original mask R zero did not discard before inputs");
    Check(calls==0,"Unexplored state accessed a lighting/material/LUT input");
    Check(Bits(L::IrradianceScale)==0x3fd9999au,"Original1.7 float changed");Check(Bits(L::CacheFloor)==0x3a83126fu,"Original.001 float changed");
    Check(Bits(L::WaterShadowCoefficient)==0xbf2b851fu,"Original shadow coefficient changed");Check(Bits(L::WaterFogBase)==0x3ecccccdu,"Original.4 float changed");
    Check(Bits(O::ShaderGamma)==0x400ccccdu&&Bits(O::ShaderInverseGamma)==0x3ee8ba2fu,"Original gamma literals changed");
}
void Malformed(){const double nan=(std::numeric_limits<double>::quiet_NaN)(),inf=(std::numeric_limits<double>::infinity)();
    Reject([&]{L::SobelNormal({{0,0,nan,0,0,0,0,0}},1);});Reject([&]{L::SobelNormal({{0,0,0,0,0,0,0,0}},inf);});
    Reject([&]{L::DecodeTerrainNormal({0,1,0},{0.5,0.5,1});});Reject([&]{L::DecodeTerrainNormal({1,0,0},{0.5,0.5,1});});
    Reject([&]{L::TerrainDiffuseLinear({nan,0,0},{1,1,1},{1,1,1},0);});Reject([&]{L::TerrainSpecularLinear(1,{1,1,1,2},0);});
    auto input=WaterInput(GoldenWaters[0]);auto bad=input;bad.secondary.q=nan;Reject([&]{L::AssembleWater(bad);});
    bad=input;bad.primary.rejected=true;bad.primary.value=1;Reject([&]{L::AssembleWater(bad);});
    bad=input;bad.rawHeight=inf;Reject([&]{L::AssembleWater(bad);});bad=input;bad.lambert=2;Reject([&]{L::AssembleWater(bad);});
    bad=input;bad.shadowSample=1;bad.shadowStrength=2;Reject([&]{L::AssembleWater(bad);});
    bad=input;bad.depthSample.r=-1;bad.primary.value=bad.secondary.value=bad.primaryWide.value=0;
    bad.primary.rejected=bad.secondary.rejected=bad.primaryWide.rejected=true;bad.reflectionStrength=0;bad.secondary.q=0;
    Reject([&]{L::AssembleWater(bad);});
    L::TerrainFinalInput final;final.post.maskR=nan;Reject([&]{L::FinalTerrain(final,Identity,Identity);});
    final={};final.post.overlay.a=2;Reject([&]{L::FinalTerrain(final,Identity,Identity);});
    final={};final.useScreenLight=true;final.specularCache={-1,0,0};Reject([&]{L::FinalTerrain(final,Identity,Identity);});
    final={};final.worldMaskStrength=inf;Reject([&]{L::FinalTerrain(final,Identity,Identity);});
    Reject([&]{L::PremultipliedOver({0,0,0},{nan,0,0,0});});
}
}
int main(){try{section="Normals";Normals();section="CacheBake";Bake();section="Water";Water();section="Final";Final();
    section="PrivacyAndConstants";PrivacyAndConstants();section="Malformed";Malformed();std::printf("PASS_ORIGINAL_LIGHTING_MODEL checks=%u\n",checks);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"Lighting model section=%s check=%u error=%s\n",section,checks,error.what());return 1;}}
