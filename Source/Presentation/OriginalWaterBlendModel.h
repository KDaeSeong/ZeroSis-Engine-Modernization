#pragma once
// Original Water stage blend index8, traced through the retail command wrapper,
// state-template initialization and OMSetBlendState. No graphics dependencies.
#include "OriginalWaterFogModel.h"
#include <algorithm>
#include <cmath>
#include <initializer_list>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalWaterBlend {
using Rgba=OriginalWaterFog::Rgba;
struct State {
    bool enabled=true,alphaToCoverage=false,independentBlend=false;
    unsigned sourceRgb=5,destinationRgb=6,rgbOperation=1;
    unsigned sourceAlpha=2,destinationAlpha=2,alphaOperation=1,writeMask=15;
};
constexpr unsigned RetailStateIndex=8;
constexpr unsigned FogCompleteFragment=2;
constexpr State RetailState{};
inline void Require(bool condition,const char* message){if(!condition)throw std::invalid_argument(message);}
inline void ValidateUnorm(Rgba value){
    for(double scalar:{value.r,value.g,value.b,value.a})
        Require(std::isfinite(scalar)&&scalar>=0&&scalar<=1,"Encoded UNORM blend input outside normalized domain");
}
inline double Opacity(double depthAlpha,double reflectionAlpha){
    Require(std::isfinite(depthAlpha)&&depthAlpha>=0&&depthAlpha<=1&&
        std::isfinite(reflectionAlpha)&&reflectionAlpha>=0&&reflectionAlpha<=1,"Invalid original water opacity sample");
    return (std::min)(1.0,depthAlpha+reflectionAlpha*depthAlpha);
}
// RGB uses SRC_ALPHA/INV_SRC_ALPHA. Alpha uses ONE/ONE, not the RGB factors.
// Saturation models the normalized target domain; quantization is a separate
// graphics implementation detail and is not claimed to be CPU bit-equivalent.
inline Rgba BlendUnorm(Rgba source,Rgba destination){
    ValidateUnorm(source);ValidateUnorm(destination);const double remain=1-source.a;
    return {source.r*source.a+destination.r*remain,source.g*source.a+destination.g*remain,
        source.b*source.a+destination.b*remain,(std::min)(1.0,source.a+destination.a)};
}
template<class Lut>Rgba FogBeforeBlend(Rgba encodedWater,Rgba foggedUnderlay,
    const OriginalWaterFog::Parameters& parameters,Lut lut){
    ValidateUnorm(foggedUnderlay);return BlendUnorm(OriginalWaterFog::Apply(encodedWater,parameters,lut),foggedUnderlay);
}
inline bool NeedsFinalFog(unsigned fragment)noexcept{return fragment!=FogCompleteFragment;}
}}
