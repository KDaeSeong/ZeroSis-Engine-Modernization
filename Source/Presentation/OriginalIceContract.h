#pragma once
// File-only recovery of IceShader inputs and draw submission. The original
// fracture/crack producer is not implemented; this contract supplies no mesh.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalIce {
constexpr unsigned FeatureCellMask=0x80,ReflectionSceneMask=0x01,EffectId=0x3b;
constexpr unsigned VertexFormatId=0x16,VertexStride=8,IndexBytes=2;
constexpr bool OriginalGeometryProviderAvailable=false;
constexpr bool OriginalMaterialProviderAvailable=false;
using Vec2=std::array<float,2>;
using Vec3=std::array<float,3>;
using Vec4=std::array<float,4>;
inline void Require(bool value,const char* why){if(!value)throw std::invalid_argument(why);}
inline unsigned char MarkFeatureCell(unsigned char flags)noexcept{return static_cast<unsigned char>(flags|FeatureCellMask);}
inline bool IsMarkedFeatureCell(unsigned char flags)noexcept{return (flags&FeatureCellMask)!=0;}
struct BoundsRecord {float minX=0,minY=0,maxX=0,maxY=0;std::uint32_t drawToken=0;};
static_assert(sizeof(BoundsRecord)==20,"Original ice bounds record must be20 bytes");
inline void ValidateBounds(const BoundsRecord& bounds){
    Require(std::isfinite(bounds.minX)&&std::isfinite(bounds.minY)&&std::isfinite(bounds.maxX)&&std::isfinite(bounds.maxY)&&
        bounds.minX<=bounds.maxX&&bounds.minY<=bounds.maxY,"Invalid original ice bounds");
}
// COMISS/JB rejects disjoint bounds; equality remains visible.
inline bool BoundsIntersect(const BoundsRecord& record,const BoundsRecord& view){
    ValidateBounds(record);ValidateBounds(view);
    return record.maxX>=view.minX&&view.maxX>=record.minX&&record.maxY>=view.minY&&view.maxY>=record.minY;
}
inline std::vector<std::uint32_t> VisibleDrawTokens(bool enabled,const std::vector<BoundsRecord>& records,const BoundsRecord& view){
    Require(records.size()<=1048576,"Unbounded original ice draw records");std::vector<std::uint32_t> result;
    if(!enabled||records.empty())return result;ValidateBounds(view);
    for(const auto& record:records)if(BoundsIntersect(record,view))result.push_back(record.drawToken);
    return result;
}
struct DecodedVertex {Vec2 position;Vec4 normalAndHeight;};
inline float Snorm16(const unsigned char* raw)noexcept{
    const unsigned word=unsigned(raw[0])|(unsigned(raw[1])<<8);
    const int signedValue=word>=32768?static_cast<int>(word)-65536:static_cast<int>(word);
    return std::max(-1.0f,signedValue/32767.0f);
}
// Format22: TEXCOORD0 R16G16_SNORM at0, TEXCOORD1 RGBA8_UNORM at4.
inline DecodedVertex DecodeVertex(const unsigned char* bytes,std::size_t count){
    Require(bytes&&count==VertexStride,"Original ice vertex must contain8 bytes");DecodedVertex result;
    result.position={{Snorm16(bytes),Snorm16(bytes+2)}};
    for(unsigned i=0;i<4;++i)result.normalAndHeight[i]=bytes[4+i]/255.0f;
    return result;
}
// Exact CB1[14] ordering of the recovered VS. Matrices and world extents are
// explicit caller inputs; this file does not invent a camera or height range.
struct VertexConstants {std::array<Vec4,14> rows;};
struct VertexOutput {Vec3 normal,world,toCamera;Vec2 clipXY,maskUv,unexploredUv;Vec4 clip;};
inline VertexOutput EvaluateVertex(const DecodedVertex& vertex,const VertexConstants& constants){
    for(const auto& row:constants.rows)for(const float value:row)Require(std::isfinite(value),"Nonfinite ice VS constant");
    for(const float value:vertex.position)Require(std::isfinite(value)&&value>=-1&&value<=1,"Invalid ice normalized position");
    for(const float value:vertex.normalAndHeight)Require(std::isfinite(value)&&value>=0&&value<=1,"Invalid ice normalized attribute");
    const auto& c=constants.rows;VertexOutput result;
    for(unsigned axis=0;axis<3;++axis)result.normal[axis]=vertex.normalAndHeight[axis]*2-1;
    for(unsigned axis=0;axis<2;++axis)result.world[axis]=(vertex.position[axis]*0.5f+0.5f)*(c[5][axis]-c[4][axis])+c[4][axis];
    result.world[2]=vertex.normalAndHeight[3]*c[6][0]+c[7][0];
    for(unsigned axis=0;axis<3;++axis)result.toCamera[axis]=c[12][axis]-result.world[axis];
    Vec2 mask;
    for(unsigned axis=0;axis<2;++axis)mask[axis]=result.world[1]*c[9][axis]+result.world[0]*c[8][axis]+result.world[2]*c[10][axis]+c[11][axis];
    result.maskUv={{mask[0]*0.5f-0.5f,mask[1]*-0.5f-0.5f}};
    for(unsigned axis=0;axis<4;++axis)result.clip[axis]=result.world[1]*c[1][axis]+result.world[0]*c[0][axis]+result.world[2]*c[2][axis]+c[3][axis];
    Require(result.clip[3]!=0,"Original ice projection has zero W");
    result.clipXY={{result.clip[0]/result.clip[3],result.clip[1]/result.clip[3]}};
    for(unsigned axis=0;axis<2;++axis)result.unexploredUv[axis]=(result.world[axis]+c[13][axis+2])*c[13][axis];
    return result;
}
inline Vec3 ProjectionWeights(const Vec3& normal){
    float lengthSquared=0;for(const float value:normal){Require(std::isfinite(value),"Invalid ice normal");lengthSquared+=value*value;}
    Require(lengthSquared>0&&std::isfinite(lengthSquared),"Zero or unbounded ice normal");
    Vec3 result;float sum=0;
    for(unsigned axis=0;axis<3;++axis){const float square=normal[axis]*normal[axis]/lengthSquared;result[axis]=square*square;sum+=result[axis];}
    for(float& value:result)value/=sum;return result;
}
struct Moments {double meanX=0,meanY=0,varianceXX=0,varianceYY=0,varianceXY=0;};
// Ice multiplies decoded slopes by S. It does not use WaterPS's divide-by-S.
// The recovered top projection uses RGBA.A for both YY and encoded cross;
// side projections consume the separate R8 plane for cross. Slot3 is unused.
inline Moments DecodeMoments(const std::array<double,4>& rgba,double cross,double shaderScale,bool topProjection){
    for(const double value:rgba)Require(std::isfinite(value)&&value>=0&&value<=1,"Invalid ice LEAN RGBA");
    Require(std::isfinite(cross)&&cross>=0&&cross<=1&&std::isfinite(shaderScale)&&shaderScale>0&&shaderScale<=16,
        "Invalid ice LEAN scale/cross");
    const double x=(2*rgba[0]-1)*shaderScale,y=(2*rgba[1]-1)*shaderScale,square=shaderScale*shaderScale;
    return {x,y,rgba[2]*square-x*x,rgba[3]*square-y*y,(2*(topProjection?rgba[3]:cross)-1)*square-x*y};
}
inline bool MaskDiscards(float explored){Require(std::isfinite(explored)&&explored>=0&&explored<=1,"Invalid ice exploration mask");return explored==0;}
inline Vec3 ApplyExplorationMask(const Vec3& gammaMaterial,const Vec3& unexplored,const Vec3& lutSample,float explored,float visible){
    Require(std::isfinite(explored)&&std::isfinite(visible)&&explored>=0&&explored<=1&&visible>=0&&visible<=1,"Invalid ice mask channels");
    Vec3 result;const float recolor=explored*(1-visible);
    for(unsigned axis=0;axis<3;++axis){
        Require(std::isfinite(gammaMaterial[axis])&&std::isfinite(unexplored[axis])&&std::isfinite(lutSample[axis]),"Invalid ice fog sample");
        const float base=unexplored[axis]+explored*(gammaMaterial[axis]-unexplored[axis]);result[axis]=base+recolor*(lutSample[axis]-base);
    }
    return result;
}
}}
