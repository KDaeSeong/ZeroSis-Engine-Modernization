#pragma once
#include "OriginalWaterOpticsModel.h"
#include <array>
#include <cmath>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalLighting {
namespace Optics=::ZeroSisPresentation::OriginalWaterOptics;
using Rgb=Optics::Vec3;
using Rgba=Optics::Rgba;
constexpr double IrradianceScale=static_cast<double>(1.7f);
constexpr double CacheFloor=static_cast<double>(0.001f);
constexpr double WaterShadowCoefficient=static_cast<double>(-0.67f);
constexpr double WaterFogBase=static_cast<double>(0.4f);

namespace Detail {
inline void Require(bool value,const char* reason){if(!value)throw std::invalid_argument(reason);}
inline void Scalar(double value){Require(std::isfinite(value),"Nonfinite lighting scalar");}
inline void Colour(Rgb value){Scalar(value.x);Scalar(value.y);Scalar(value.z);}
inline void Colour(Rgba value){Scalar(value.r);Scalar(value.g);Scalar(value.b);Scalar(value.a);}
inline void Unit(double value){Require(std::isfinite(value)&&value>=0&&value<=1,"Lighting channel outside normalized domain");}
inline double Saturate(double value){Scalar(value);return (std::max)(0.0,(std::min)(1.0,value));}
inline Rgb Add(Rgb a,Rgb b){return {a.x+b.x,a.y+b.y,a.z+b.z};}
inline Rgb Scale(Rgb a,double b){return {a.x*b,a.y*b,a.z*b};}
inline Rgb Product(Rgb a,Rgb b){return {a.x*b.x,a.y*b.y,a.z*b.z};}
inline Rgb Mix(Rgb a,Rgb b,double t){return {a.x+t*(b.x-a.x),a.y+t*(b.y-a.y),a.z+t*(b.z-a.z)};}
inline double Power(double value,double exponent){
    Require(std::isfinite(value)&&value>=0&&value<=1e100,"Lighting power requires finite nonnegative RGB");
    const double result=value==0?0:std::exp2(std::log2(value)*exponent);Scalar(result);return result;
}
inline Rgb Power(Rgb value,double exponent){return {Power(value.x,exponent),Power(value.y,exponent),Power(value.z,exponent)};}
inline Rgb Encoded(Rgb linear){return Power(linear,Optics::ShaderInverseGamma);}
inline Rgb RgbOf(Rgba value){return {value.r,value.g,value.b};}
inline Rgba RgbaOf(Rgb value,double alpha){return {value.x,value.y,value.z,alpha};}
inline double Dot(Rgb a,Rgb b){return a.x*b.x+a.y*b.y+a.z*b.z;}
}

struct SobelResult {Rgb normal;Rgba encoded;double sx=0,sy=0;};
// Shader sample order: (-a,+z),(-a,-b),(+a,-b),(+a,+z),
// (-a,+b),(+a,+b),(+z,-b),(+z,+b). Runtime offsets are caller inputs.
inline SobelResult SobelNormal(const std::array<double,8>& height,double strength){
    for(const auto value:height)Detail::Scalar(value);Detail::Scalar(strength);
    const double sx=(height[1]-height[2]+2*height[0])+(height[4]-height[5]-2*height[3]),
        sy=(height[1]+height[2]+2*height[6])+(-height[4]-height[5]-2*height[7]);
    const double nx=-strength*sx,ny=strength*sy,length=std::sqrt(nx*nx+ny*ny+16);
    Detail::Require(std::isfinite(length)&&length>0,"Invalid lighting Sobel magnitude");
    const Rgb n{nx/length,ny/length,4/length};return {n,{0.5+n.x*0.5,0.5+n.y*0.5,0.5+n.z*0.5,0},sx,sy};
}
// Privacy policy separate from the original eight-tap algebra: no unknown tap
// callback executes; missing taps use a supplied explored centre height.
template<class Sample>SobelResult GuardedSobel(bool revealed,const std::array<bool,8>& known,double centerHeight,
    double strength,Sample sample){
    if(!revealed)return {{0,0,1},{0.5,0.5,1,0},0,0};
    Detail::Scalar(centerHeight);std::array<double,8> taps{};
    for(unsigned i=0;i<8;++i)taps[i]=known[i]?sample(i):centerHeight;
    return SobelNormal(taps,strength);
}
inline Rgb DecodeTerrainNormal(Rgb base,Rgb encoded){
    Detail::Colour(base);Detail::Colour(encoded);
    const double tx=std::sqrt(base.z*base.z+base.x*base.x),by=std::sqrt(base.z*base.z+base.y*base.y);
    Detail::Require(std::isfinite(tx)&&std::isfinite(by)&&tx>0&&by>0,"Degenerate original terrain normal basis");
    const Rgb t{-base.z/tx,0,base.x/tx},b{0,base.z/by,-base.y/by},m{2*encoded.x-1,2*encoded.y-1,2*encoded.z-1};
    const auto result=Detail::Add(Detail::Add(Detail::Scale(t,m.x),Detail::Scale(b,m.y)),Detail::Scale(base,m.z));
    Detail::Colour(result);return result; // Base and result are not renormalized.
}
struct TerrainBakeInput {
    Rgb baseNormal{0,0,1},normalSample{0.5,0.5,1},albedo{},light{0,0,1};
    Rgba specular{0,0,0,0};double shadowR=0;bool specularEnabled=false;
};
struct TerrainBakeResult {
    Rgb normal{},diffuseLinear{},diffuseEncoded{},diffuse{},specularLinear{},specularEncoded{},specular{};
    double specularAlpha=0;bool discarded=false;
};
inline Rgb TerrainDiffuseLinear(Rgb albedo,Rgb first,Rgb second,double shadowR){
    Detail::Colour(albedo);Detail::Colour(first);Detail::Colour(second);Detail::Scalar(shadowR);
    // Shadow R extrapolates here; only the specular attenuation saturates.
    const auto irradiance=Detail::Mix(Detail::Scale(first,IrradianceScale),Detail::Scale(second,IrradianceScale),shadowR);
    const auto result=Detail::Add(Detail::Product(albedo,irradiance),{CacheFloor,CacheFloor,CacheFloor});Detail::Colour(result);return result;
}
inline Rgba TerrainSpecularLinear(double normalDotLight,Rgba sample,double shadowR){
    Detail::Colour(sample);Detail::Unit(sample.a);Detail::Scalar(shadowR);
    const double exponent=64*sample.a+1,scale=Detail::Power(Detail::Saturate(normalDotLight),exponent)*exponent*Detail::Saturate(1-shadowR);
    const Rgba result{sample.r*scale,sample.g*scale,sample.b*scale,sample.a*scale};Detail::Colour(result);return result;
}
template<class CubeA,class CubeB,class Lut>TerrainBakeResult BakeTerrain(const TerrainBakeInput& input,CubeA cubeA,CubeB cubeB,Lut lut){
    TerrainBakeResult result;result.normal=DecodeTerrainNormal(input.baseNormal,input.normalSample);
    const auto first=cubeA(result.normal),second=cubeB(result.normal);
    result.diffuseLinear=TerrainDiffuseLinear(input.albedo,first,second,input.shadowR);
    result.diffuseEncoded=Detail::Encoded(result.diffuseLinear);result.diffuse=lut(result.diffuseEncoded);Detail::Colour(result.diffuse);
    if(input.specularEnabled){Detail::Colour(input.light);
        const auto specular=TerrainSpecularLinear(Detail::Dot(input.light,result.normal),input.specular,input.shadowR);
        result.specularLinear=Detail::RgbOf(specular);result.specularAlpha=specular.a;
        result.specularEncoded=Detail::Encoded(result.specularLinear);result.specular=lut(result.specularEncoded);Detail::Colour(result.specular);}
    return result;
}
template<class Fetch,class CubeA,class CubeB,class Lut>TerrainBakeResult GuardedBakeTerrain(bool revealed,Fetch fetch,CubeA cubeA,CubeB cubeB,Lut lut){
    if(!revealed){TerrainBakeResult result;result.discarded=true;return result;}return BakeTerrain(fetch(),cubeA,cubeB,lut);
}

struct WaterCompositeInput {
    Rgba depthSample{};double rawHeight=0,lambert=0,fresnel=0;
    Optics::GaussianResult primary{},primaryWide{},secondary{};
    Rgb primaryLight{},secondaryLight{};Optics::LinearReflection reflection{};
    double reflectionStrength=0,shadowSample=0,shadowStrength=0;
};
struct WaterLightingResult {Rgb preShadow{},shadowed{},encoded{};double alpha=0,secondaryDepthTerm=0;};
inline WaterLightingResult AssembleWater(const WaterCompositeInput& input){
    Detail::Colour(input.depthSample);Detail::Unit(input.depthSample.a);Detail::Scalar(input.rawHeight);Detail::Unit(input.lambert);Detail::Scalar(input.fresnel);
    Detail::Colour(input.primaryLight);Detail::Colour(input.secondaryLight);Detail::Colour(input.reflection.rgb);Detail::Scalar(input.reflection.alpha);
    Detail::Scalar(input.reflectionStrength);Detail::Scalar(input.shadowSample);Detail::Scalar(input.shadowStrength);
    for(const auto* lobe:{&input.primary,&input.primaryWide,&input.secondary}){
        Detail::Scalar(lobe->value);Detail::Require(lobe->value>=0&&(!lobe->rejected||lobe->value==0),"Invalid original water Gaussian value/rejection");}
    // Secondary q survives the original movc rejection of its Gaussian value.
    Detail::Scalar(input.secondary.q);const double q=input.secondary.q;
    WaterLightingResult result;result.secondaryDepthTerm=Detail::Saturate(4*input.rawHeight)*(q*q*q);Detail::Scalar(result.secondaryDepthTerm);
    const auto depth=Detail::RgbOf(input.depthSample);
    const auto highlights=Detail::Add(Detail::Scale(input.primaryLight,input.primary.value),Detail::Scale(input.secondaryLight,input.secondary.value));
    result.preShadow=Detail::Scale(Detail::Add(depth,Detail::Scale(highlights,input.fresnel)),input.lambert);
    result.preShadow=Detail::Add(result.preShadow,Detail::Scale(Detail::Product(depth,input.primaryLight),input.primaryWide.value));
    result.preShadow=Detail::Add(result.preShadow,Detail::Scale(input.reflection.rgb,input.reflectionStrength));
    result.preShadow=Detail::Add(result.preShadow,Detail::Scale(depth,result.secondaryDepthTerm));Detail::Colour(result.preShadow);
    const double shadow=Detail::Saturate(input.shadowSample)*input.shadowStrength;
    // Keep x + (-.67)*(shadow*x), rather than adding an unproven clamp.
    result.shadowed=Detail::Add(result.preShadow,Detail::Scale(Detail::Scale(result.preShadow,shadow),WaterShadowCoefficient));
    Detail::Colour(result.shadowed);result.encoded=Detail::Encoded(result.shadowed);
    result.alpha=Detail::Saturate(input.reflection.alpha*input.depthSample.a+input.depthSample.a);return result;
}

struct PostInput {
    Rgba overlay{0,0,0,0};double maskR=1,maskB=1,fogFactor=0;Rgb fogColour{};
};
inline Rgb PremultipliedOver(Rgb colour,Rgba overlay){
    Detail::Colour(colour);Detail::Colour(overlay);Detail::Unit(overlay.a);
    const auto result=Detail::Add(Detail::Scale(colour,1-overlay.a),Detail::RgbOf(overlay));Detail::Colour(result);return result;
}
template<class Lut>Rgb FinishRgb(Rgb colour,Rgb replacement,const PostInput& post,Lut lut){
    Detail::Colour(replacement);Detail::Unit(post.maskR);Detail::Unit(post.maskB);Detail::Unit(post.fogFactor);Detail::Colour(post.fogColour);
    const auto overlay=PremultipliedOver(colour,post.overlay),base=Detail::Mix(replacement,overlay,post.maskR);
    const auto transformed=lut(base);Detail::Colour(transformed);
    const auto mixed=Detail::Mix(base,transformed,post.maskR*(1-post.maskB)),fogged=Detail::Mix(mixed,post.fogColour,post.fogFactor);
    Detail::Colour(fogged);return fogged;
}
struct TerrainFinalInput {
    Rgb litCache{},specularCache{},screenLight{},replacement{};
    bool useLitCache=true,useScreenLight=false;
    double worldMaskSample=0,worldMaskStrength=0;
    PostInput post;
};
inline Rgb TerrainCacheCombination(const TerrainFinalInput& input){
    const auto lit=input.useLitCache?input.litCache:Rgb{};Detail::Colour(lit);
    if(!input.useScreenLight)return lit;
    Detail::Colour(input.screenLight);
    // Final TerrainShader t8 is baked specular, confirmed by both chunk callers.
    const auto linear=Detail::Add(Detail::Product(Detail::Power(input.specularCache,Optics::ShaderGamma),input.screenLight),
        Detail::Power(lit,Optics::ShaderGamma));return Detail::Encoded(linear);
}
template<class WorldLut,class FowLut>Rgba FinalTerrain(const TerrainFinalInput& input,WorldLut worldLut,FowLut fowLut){
    const auto cached=TerrainCacheCombination(input);Detail::Scalar(input.worldMaskStrength);
    const double amount=Detail::Saturate(input.worldMaskSample)*input.worldMaskStrength;
    const auto world=worldLut(cached);Detail::Colour(world);const auto colour=Detail::Mix(cached,world,amount);
    return Detail::RgbaOf(FinishRgb(colour,input.replacement,input.post,fowLut),1);
}
template<class Fetch,class WorldLut,class FowLut>Rgba GuardedFinalTerrain(bool revealed,Rgb safeReplacement,Fetch fetch,WorldLut worldLut,FowLut fowLut){
    if(!revealed){Detail::Colour(safeReplacement);return Detail::RgbaOf(safeReplacement,1);}return FinalTerrain(fetch(),worldLut,fowLut);
}
struct WaterPixel {WaterLightingResult lighting;Rgba colour{0,0,0,0};bool discarded=true;};
template<class Fetch,class FowLut>WaterPixel GuardedWater(bool revealed,const PostInput& post,Fetch fetch,FowLut fowLut){
    if(!revealed)return {};Detail::Unit(post.maskR);if(post.maskR==0)return {};
    WaterPixel result;result.lighting=AssembleWater(fetch());const Rgb replacement{WaterFogBase,WaterFogBase,WaterFogBase};
    result.colour=Detail::RgbaOf(FinishRgb(result.lighting.encoded,replacement,post,fowLut),result.lighting.alpha);result.discarded=false;return result;
}
}}
