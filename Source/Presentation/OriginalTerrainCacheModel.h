#pragma once
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalTerrainCache {

struct Point { double x=0,y=0,z=0; };
struct Matrix { std::array<std::int32_t,16> values{}; };

namespace Detail {
inline void Require(bool value,const char* message){if(!value)throw std::invalid_argument(message);}
inline Matrix Identity(){Matrix result;for(unsigned i=0;i<4;++i)result.values[i*4+i]=1;return result;}
inline Matrix Multiply(const Matrix& left,const Matrix& right){
    Matrix result;
    for(unsigned row=0;row<4;++row)for(unsigned column=0;column<4;++column){
        std::int64_t value=0;
        for(unsigned k=0;k<4;++k)value+=static_cast<std::int64_t>(left.values[row*4+k])*right.values[k*4+column];
        Require(value>=-2147483647LL-1 && value<=2147483647LL,"Terrain orientation matrix overflow");
        result.values[row*4+column]=static_cast<std::int32_t>(value);
    }
    return result;
}
}

// Retail 0x75f2a0 accumulates T * R(0) * mirror. The helper 0x6ea000
// updates both its left operand and the explicit output. Match cells use
// row-vector multiplication; the translation is mirrored with the point.
inline Matrix OrientationMatrix(unsigned orientation){
    Detail::Require(orientation<4,"Unknown terrain piece orientation");
    static const std::int32_t translations[4][3]={{0,0,0},{1,-3,2},{-4,0,4},{-2,-3,5}};
    static const std::int32_t mirrors[4][16]={
        {1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1},
        {0,0,-1,0,0,-1,0,0,-1,0,0,0,0,0,0,1},
        {0,0,1,0,0,1,0,0,1,0,0,0,0,0,0,1},
        {-1,0,0,0,0,-1,0,0,0,0,-1,0,0,0,0,1}};
    Matrix translation=Detail::Identity(),rotation,mirror;
    for(unsigned axis=0;axis<3;++axis)translation.values[12+axis]=translations[orientation][axis];
    // The original turn-zero matrix has -1 off diagonal. It is identity
    // on the cube-coordinate plane x+y+z=0, not on arbitrary 3D vectors.
    rotation.values={{0,-1,-1,0,-1,0,-1,0,-1,-1,0,0,0,0,0,1}};
    for(unsigned i=0;i<16;++i)mirror.values[i]=mirrors[orientation][i];
    return Detail::Multiply(Detail::Multiply(translation,rotation),mirror);
}

inline Point OrientPoint(Point point,unsigned orientation){
    Detail::Require(std::isfinite(point.x)&&std::isfinite(point.y)&&std::isfinite(point.z)&&
        std::abs(point.x)<=1000000&&std::abs(point.y)<=1000000&&std::abs(point.z)<=1000000&&
        std::abs(point.x+point.y+point.z)<=0.00000001,"Invalid terrain cube-plane point");
    const auto matrix=OrientationMatrix(orientation);
    Point result;
    result.x=point.x*matrix.values[0]+point.y*matrix.values[4]+point.z*matrix.values[8]+matrix.values[12];
    result.y=point.x*matrix.values[1]+point.y*matrix.values[5]+point.z*matrix.values[9]+matrix.values[13];
    result.z=point.x*matrix.values[2]+point.y*matrix.values[6]+point.z*matrix.values[10]+matrix.values[14];
    return result;
}

struct ScratchSettings {
    unsigned terrainDetailLevel=0;
    // Numeric capability class read by the original 0x453f80 branch.
    // Its mapping to a current device must be supplied separately.
    int backendClass=0;
    bool advancedCacheAllowed=false;
};
struct ScratchLayout {
    unsigned width=0,height=0,mipLevels=0;
};

inline unsigned FullMipCount(unsigned extent){
    Detail::Require(extent>0&&extent<=16384,"Invalid terrain cache extent");
    unsigned result=0;do{++result;extent>>=1;}while(extent);return result;
}
inline ScratchLayout SelectScratchLayout(const ScratchSettings& settings){
    Detail::Require(settings.terrainDetailLevel<=3&&settings.backendClass>=0&&settings.backendClass<=255,
        "Invalid terrain cache quality inputs");
    const bool advanced=settings.backendClass>=8&&settings.advancedCacheAllowed;
    const unsigned extent=settings.terrainDetailLevel==0?128u:settings.terrainDetailLevel==1?256u:
        settings.terrainDetailLevel==2?(advanced?512u:256u):512u;
    return {extent,extent,FullMipCount(extent)};
}
inline unsigned MipExtent(unsigned extent,unsigned level){
    const unsigned count=FullMipCount(extent);
    Detail::Require(level<count,"Terrain cache mip is outside its allocation");
    const unsigned value=extent>>level;return value?value:1;
}
inline std::uint64_t LogicalMipBytes(unsigned extent,unsigned bytesPerTexel){
    Detail::Require(bytesPerTexel==4||bytesPerTexel==8,"Unsupported original scratch texel size");
    const unsigned count=FullMipCount(extent);std::uint64_t result=0;
    for(unsigned mip=0;mip<count;++mip){const std::uint64_t side=MipExtent(extent,mip);result+=side*side*bytesPerTexel;}
    return result; // Logical payload; driver/heap allocation is not inferred.
}

struct NormalDescriptor {
    unsigned resourceFormat,renderViewFormat,sampleViewFormat;
    unsigned samplerIndex,filter,addressU,addressV,addressW;
};
inline NormalDescriptor NormalCacheDescriptor() noexcept {
    // DXGI27 RGBA8 typeless, RTV/SRV28 UNORM. Sampler5 is LINEAR_CLAMP
    // with sRGB flag0. The extra SRGB29 SRV exists but is not selected.
    return {27,28,28,5,0x15,3,3,3};
}
inline std::array<float,3> DecodeNormalRgba8(const std::array<std::uint8_t,4>& pixel) noexcept {
    // This GPU normal cache differs from the separate CPU byte-XY codec
    // recovered in OriginalTerrainNormal::DecodeCachedXY.
    constexpr float reciprocal=1.0f/255.0f;
    return {{(pixel[0]*reciprocal)*2-1,(pixel[1]*reciprocal)*2-1,(pixel[2]*reciprocal)*2-1}};
}

struct TexelAxisSample {unsigned before=0,after=0;double fraction=0;};
inline TexelAxisSample LinearClampAxis(double uv,unsigned extent){
    Detail::Require(std::isfinite(uv)&&std::abs(uv)<=1000000&&extent>0&&extent<=16384,
        "Invalid terrain cache sample coordinate");
    const double coordinate=uv*extent-0.5;
    const double lower=std::floor(coordinate);
    const auto clamp=[extent](double value){return value<0?0u:value>=extent?extent-1:static_cast<unsigned>(value);};
    return {clamp(lower),clamp(lower+1),coordinate-lower};
}

}}
