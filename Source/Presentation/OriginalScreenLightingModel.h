#pragma once
#include "OriginalLightingModel.h"
#include <array>
#include <cmath>
#include <cstddef>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalScreenLighting {
using Rgb=OriginalLighting::Rgb;
using Uv=std::array<double,2>;
constexpr unsigned OriginalReflectionSide=1024;
constexpr unsigned OriginalDisabledReflectionSide=32;
constexpr unsigned MaximumViewportSide=4096;
// These are renderer-local values. They neither read nor persist original INI
// options. The original default-rule proof is distinct from current values.
struct Policy {
    unsigned terrainDetailLevel=3,reflectionLevel=1;
    int diffuseOverride=-1,specularOverride=-1;
};
struct ResolvedPolicy {bool diffuse=true,specular=true,reflection=true;};
inline void Require(bool condition,const char* message){
    if(!condition)throw std::invalid_argument(message);
}
inline void Scalar(double value){Require(std::isfinite(value),"Nonfinite screen reflection value");}
inline void Colour(const Rgb& value){
    Scalar(value.x);Scalar(value.y);Scalar(value.z);
    Require(value.x>=0 && value.y>=0 && value.z>=0,"Negative screen reflection colour");
}
inline ResolvedPolicy ResolvePolicy(const Policy& policy){
    Require(policy.terrainDetailLevel<=3 && policy.reflectionLevel<=1,"Unsupported renderer quality value");
    Require(policy.diffuseOverride>=-1 && policy.diffuseOverride<=1 &&
        policy.specularOverride>=-1 && policy.specularOverride<=1,"Unsupported renderer gate override");
    ResolvedPolicy result;
    result.diffuse=policy.diffuseOverride<0 || policy.diffuseOverride!=0;
    result.specular=policy.specularOverride<0?policy.terrainDetailLevel==3:policy.specularOverride!=0;
    result.reflection=policy.reflectionLevel==1;return result;
}
// Original TerrainShader VS3 o5=clip.xy/clip.w; PS0 uv=.5*o5+.5.
inline Uv UvFromClip(double x,double y,double w){
    Scalar(x);Scalar(y);Scalar(w);Require(w!=0,"Zero screen reflection clip w");
    const Uv result{{.5*(x/w)+.5,.5*(y/w)+.5}};Scalar(result[0]);Scalar(result[1]);return result;
}
inline Uv UvFromPixel(double x,double y,unsigned width,unsigned height){
    Scalar(x);Scalar(y);Require(width && height && width<=MaximumViewportSide && height<=MaximumViewportSide,
        "Unsupported screen reflection viewport");
    return {{x/static_cast<double>(width),1-y/static_cast<double>(height)}};
}
// Exact consumer: t9 is the static original specscreenmap DDS sampled through
// UNORM LINEAR_CLAMP. It is independent of WaterShader's Raw reflection map.
// No extra gamma conversion belongs inside this operation.
inline Rgb Combine(const Rgb& diffuse,const Rgb& specular,const Rgb& reflection,const ResolvedPolicy& policy){
    OriginalLighting::TerrainFinalInput input;input.useLitCache=policy.diffuse;
    input.useScreenLight=policy.specular;input.litCache=diffuse;
    input.specularCache=specular;input.screenLight=reflection;
    return OriginalLighting::TerrainCacheCombination(input);
}
template<class Fetch>Rgb GuardedCombine(bool revealed,const Rgb& safeReplacement,
    const Rgb& diffuse,const Rgb& specular,const Policy& policy,double clipX,double clipY,double clipW,Fetch fetch){
    if(!revealed){Colour(safeReplacement);return safeReplacement;}
    const auto resolved=ResolvePolicy(policy);
    if(!resolved.specular)return Combine(diffuse,specular,Rgb{},resolved);
    const auto sample=fetch(UvFromClip(clipX,clipY,clipW));Colour(sample);
    return Combine(diffuse,specular,sample,resolved);
}
struct Constants {std::array<float,4> viewport{},flags{};};
static_assert(sizeof(Constants)==32,"Screen reflection constant layout differs");
inline Constants MakeConstants(unsigned width,unsigned height,const Policy& policy,bool available){
    Require(width && height && width<=MaximumViewportSide && height<=MaximumViewportSide,
        "Unsupported screen reflection viewport");
    const auto resolved=ResolvePolicy(policy);Constants result;
    result.viewport={{static_cast<float>(width),static_cast<float>(height),1.0f/static_cast<float>(width),1.0f/static_cast<float>(height)}};
    result.flags={{available && resolved.specular?1.0f:0.0f,
        resolved.diffuse?1.0f:0.0f,resolved.specular?1.0f:0.0f,0}};
    return result;
}
}}
