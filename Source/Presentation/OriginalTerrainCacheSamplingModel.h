#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalTerrainCacheSampling {
// File-backed defaults copied by retail 0x67837e..0x6783a6. Object ownership
// includes the primary-to-renderer-base +8 adjustment. Runtime overrides and
// the current display origin are separate inputs, not implicit constants.
constexpr float SourceMetricXDefault=1.0f;
constexpr float SourceMetricYDefault=0.865999996662139892578125f;
constexpr float SourceMetricZDefault=0.20000000298023223876953125f;
constexpr float RawHeightReciprocal255=0.0039215688593685626983642578125f;
constexpr unsigned SourceTexelsPerHex=64;
constexpr float NormalizedHeightRangeDefault=
    (65535.0f*RawHeightReciprocal255)*SourceMetricZDefault/SourceTexelsPerHex;
struct ScratchFootprint {
    double originX=0,originY=0;
    unsigned cellsX=64,cellsY=64,side=128;
};
struct Coordinate {double x=0,y=0;};
struct SampleResult {std::array<float,4> value{{0,0,0,0}};bool complete=false;};
namespace Detail {
inline void Require(bool ok,const char* message){if(!ok)throw std::invalid_argument(message);}
inline void Finite(double value){Require(std::isfinite(value),"Nonfinite cache sampling input");}
inline void Scratch(const ScratchFootprint& f){
    Finite(f.originX);Finite(f.originY);
    Require(std::abs(f.originX)<=1000000&&std::abs(f.originY)<=1000000&&
        f.cellsX>0&&f.cellsY>0&&f.cellsX<=4096&&f.cellsY<=4096&&
        (f.side==128||f.side==256||f.side==512),"Invalid original scratch footprint");
}
inline std::uint16_t TruncateNormalized(double value){
    // Retail 0x70b4e7..0x70b529 uses x87 division, addition, double65535,
    // truncation and a low-word store. This reference uses double arithmetic;
    // extended-precision cutoff bit equivalence is not claimed. Out-of-domain
    // wrap/indefinite conversion is rejected as an explicit safety policy.
    Require(std::isfinite(value)&&value>=0&&value<=1,"Invalid normalized stamped height");
    return static_cast<std::uint16_t>(value*65535.0);
}
struct Axis {unsigned low=0,high=0;double fraction=0;};
inline Axis LinearClamp(double uv,unsigned side){
    Finite(uv);Require(side>0&&side<=4096&&std::abs(uv)<=1000000,"Invalid cache sample axis");
    const double position=uv*side-0.5,low=std::floor(position);
    const auto clamp=[&](double index){return static_cast<unsigned>((std::max)(0.0,
        (std::min)(static_cast<double>(side-1),index)));};
    return {clamp(low),clamp(low+1),position-low};
}
}
inline std::uint16_t FinalizeStampedHeight(float sum,float weight,float reference){
    Detail::Require(std::isfinite(sum)&&std::isfinite(weight)&&weight>0&&std::isfinite(reference),
        "Invalid original stamped height accumulator");
    return Detail::TruncateNormalized(static_cast<double>(sum)/weight+reference);
}
inline std::uint16_t QuantizeCenteredHeight(float centeredHeight,float reference){
    Detail::Require(std::isfinite(centeredHeight)&&std::isfinite(reference),"Invalid centered terrain height");
    return Detail::TruncateNormalized(static_cast<double>(centeredHeight)+reference);
}
inline float RawHeightToOriginalWorld(std::uint16_t raw,float metric=SourceMetricZDefault){
    Detail::Require(std::isfinite(metric)&&metric>0&&metric<=1024,"Invalid original height metric");
    // Preserve the two original SSE scalar multiplies, without reassociation.
    const float scalar=static_cast<float>(raw)*RawHeightReciprocal255;
    return scalar*metric;
}
inline float NormalizeOriginalHeight(std::uint16_t raw,float originalOrigin,
    float unitsPerHex=static_cast<float>(SourceTexelsPerHex),float metric=SourceMetricZDefault){
    Detail::Require(std::isfinite(originalOrigin)&&std::abs(originalOrigin)<=1000000&&
        std::isfinite(unitsPerHex)&&unitsPerHex>0&&unitsPerHex<=1000000,"Invalid terrain display transform");
    return (RawHeightToOriginalWorld(raw,metric)-originalOrigin)/unitsPerHex;
}
inline float RestoreOriginalHeight(float displayHeight,float originalOrigin,
    float unitsPerHex=static_cast<float>(SourceTexelsPerHex)){
    Detail::Require(std::isfinite(displayHeight)&&std::abs(displayHeight)<=1000000&&
        std::isfinite(originalOrigin)&&std::abs(originalOrigin)<=1000000&&std::isfinite(unitsPerHex)&&
        unitsPerHex>0&&unitsPerHex<=1000000,"Invalid terrain material coordinate transform");
    return displayHeight*unitsPerHex+originalOrigin;
}
inline Coordinate ScratchSampleUv(const ScratchFootprint& f,double sourceX,double sourceY){
    Detail::Scratch(f);Detail::Finite(sourceX);Detail::Finite(sourceY);
    return {(sourceX-f.originX+1)/(f.cellsX+1.0),(sourceY-f.originY+1)/(f.cellsY+1.0)};
}
inline Coordinate ScratchRasterUv(const ScratchFootprint& f,double sourceX,double sourceY){
    // Original cache vertices use 2*u-1-1/N (Y is reversed for rasterization).
    // Their texture coordinates retain u, so sample UV and raster UV differ.
    auto result=ScratchSampleUv(f,sourceX,sourceY);const double halfTexel=0.5/f.side;
    result.x-=halfTexel;result.y-=halfTexel;return result;
}
inline Coordinate ScratchRasterToSource(const ScratchFootprint& f,double rasterX,double rasterY){
    Detail::Scratch(f);Detail::Finite(rasterX);Detail::Finite(rasterY);
    return {f.originX-1+(rasterX+0.5)*(f.cellsX+1.0)/f.side,
        f.originY-1+(rasterY+0.5)*(f.cellsY+1.0)/f.side};
}
inline Coordinate HaloTexelCenter(unsigned x,unsigned y,unsigned side,unsigned halo){
    Detail::Require(side>0&&side<=4096&&halo<=16&&side>2*halo&&x<side&&y<side,
        "Invalid current halo footprint");
    // Current chunk halo adapter, not an assertion of original topology.
    return {static_cast<double>(x)-halo+0.5,static_cast<double>(y)-halo+0.5};
}
template<class Known,class Sample>SampleResult GuardedLinearClamp(Coordinate uv,
    unsigned width,unsigned height,Known known,Sample sample){
    const auto ax=Detail::LinearClamp(uv.x,width),ay=Detail::LinearClamp(uv.y,height);
    const unsigned xs[4]={ax.low,ax.high,ax.low,ax.high},ys[4]={ay.low,ay.low,ay.high,ay.high};
    SampleResult result;
    // Even zero-weight corners are checked before reading any numeric payload.
    // This conservative privacy rule is separate from retail texture filtering.
    for(unsigned i=0;i<4;++i)if(!known(xs[i],ys[i]))return result;
    std::array<std::array<float,4>,4> values;
    for(unsigned i=0;i<4;++i){values[i]=sample(xs[i],ys[i]);
        for(float value:values[i])Detail::Require(std::isfinite(value),"Nonfinite known cache sample");}
    for(unsigned c=0;c<4;++c){const double top=values[0][c]+(values[1][c]-values[0][c])*ax.fraction;
        const double bottom=values[2][c]+(values[3][c]-values[2][c])*ax.fraction;
        result.value[c]=static_cast<float>(top+(bottom-top)*ay.fraction);}
    result.complete=true;return result;
}
}}
