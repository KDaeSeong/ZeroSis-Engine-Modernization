#pragma once

// Pure CPU reference for the retail fog shader operations. The mask layout,
// sampler state, raster resolution and cloud motion are explicit candidates.
// No terrain, heights, material IDs, picking IDs or game RNG enter this model.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalFog {

constexpr unsigned CandidateTexelsPerHex=16;
constexpr std::size_t DefaultMaxMaskTexels=4ull*1024*1024;
constexpr double RowSpacing=0.866025404;
constexpr double ShaderLog2E=static_cast<double>(1.442695f);

struct Colour {float r=0,g=0,b=0,a=1;};
struct Vec3 {double x=0,y=0,z=0;}; // Retail coordinates: Z is up.
struct Cell {bool revealed=false,visible=false;};
struct Grid {int width=0,height=0;bool wrapX=false,wrapY=false;std::vector<Cell> cells;};
struct Mask {float r=0,g=1,b=0;}; // Candidate: explored, cloud, currently visible.
struct MaskTexture {unsigned width=0,height=0;std::vector<Mask> texels;};
struct ImageView {const Colour* texels=nullptr;unsigned width=0,height=0;std::size_t count=0;};
struct Lut3DView {const Colour* texels=nullptr;unsigned width=0,height=0,depth=0;std::size_t count=0;};
enum class AddressMode {Clamp,Wrap};
struct FlowLayer {double scale=0,speedU=0,speedV=0,phaseU=0,phaseV=0;};
constexpr FlowLayer CandidateFlowLayers[3]={
    {1.0/8.0,0.009,0.004,0,0},
    {1.0/11.0,-0.006,0.008,0.37,0.13},
    {1.0/15.0,0.003,-0.007,0.71,0.43}};

inline MaskTexture BuildMask(const Grid& grid,unsigned texelsPerHex=CandidateTexelsPerHex,
    std::size_t maxTexels=DefaultMaxMaskTexels);
inline Mask SampleMask(const MaskTexture& texture,double u,double v,bool wrapX,bool wrapY);
inline std::array<double,2> MaskUv(double worldX,double worldZ,int gridWidth,int gridHeight);
inline Colour Sample2D(const ImageView& image,double u,double v,AddressMode mode=AddressMode::Clamp);
inline Colour SampleLut(const Lut3DView& lut,const Colour& coordinate);
inline Colour MixReplacement(const Colour& terrain,const Colour& replacement,const Mask& mask,bool exactRevealed);
inline Colour BlendFow(const Colour& terrain,const Colour& replacement,const Mask& mask,
    const Colour& lutColour,bool exactRevealed);
inline Colour ApplyFow(const Colour& terrain,const Colour& replacement,const Mask& mask,
    const Lut3DView& lut,bool exactRevealed);
inline std::array<double,2> DistanceRampUv(double screenNdcY,double row);
inline double DistanceFogFactor(Vec3 retailDelta,double heightK,double density,double rampRed);
inline Colour ApplyDistanceFog(const Colour& colour,const Colour& fogColour,double factor);
inline std::array<double,2> FlowUv(double worldX,double worldZ,double seconds,unsigned layer);

namespace Detail {
inline void Require(bool condition,const char* message){if(!condition)throw std::invalid_argument(message);}
inline double Unit(double value){Require(std::isfinite(value),"Nonfinite original fog value");return (std::max)(0.0,(std::min)(1.0,value));}
inline void FiniteColour(const Colour& value){Require(std::isfinite(value.r)&&std::isfinite(value.g)&&
    std::isfinite(value.b)&&std::isfinite(value.a),"Nonfinite original fog colour");}
inline void ValidMask(const Mask& value){Require(std::isfinite(value.r)&&std::isfinite(value.g)&&std::isfinite(value.b)&&
    value.r>=0&&value.r<=1&&value.g>=0&&value.g<=1&&value.b>=0&&value.b<=value.r,
    "Invalid original fog visibility mask");}
inline int Wrap(int value,int span){const int result=value%span;return result<0?result+span:result;}
inline int Axis(int value,int span,bool wrap){return wrap?Wrap(value,span):(std::max)(0,(std::min)(span-1,value));}
inline int FloorHalf(int value){return value/2-((value<0&&value%2)?1:0);}
inline std::array<int,2> Owner(double x,double row){
    const double q=x-row*0.5,z=-q-row;
    int iq=static_cast<int>(std::round(q)),ir=static_cast<int>(std::round(row)),iz=static_cast<int>(std::round(z));
    const double dq=std::abs(iq-q),dr=std::abs(ir-row),dz=std::abs(iz-z);
    if(dq>dr&&dq>dz)iq=-ir-iz;else if(dr>dz)ir=-iq-iz;
    return {{iq+FloorHalf(ir),ir}};
}
inline Colour Mix(const Colour& a,const Colour& b,double amount){
    return {static_cast<float>(a.r+(b.r-a.r)*amount),static_cast<float>(a.g+(b.g-a.g)*amount),
        static_cast<float>(a.b+(b.b-a.b)*amount),static_cast<float>(a.a+(b.a-a.a)*amount)};
}
inline Mask Mix(const Mask& a,const Mask& b,double amount){
    return {static_cast<float>(a.r+(b.r-a.r)*amount),static_cast<float>(a.g+(b.g-a.g)*amount),
        static_cast<float>(a.b+(b.b-a.b)*amount)};
}
inline std::size_t Count(unsigned width,unsigned height,unsigned depth=1){
    Require(width>0&&height>0&&depth>0&&width<=16384&&height<=16384&&depth<=16384,
        "Invalid original fog texture dimensions");
    constexpr std::size_t limit=16ull*1024*1024;
    Require(width<=limit/height&&static_cast<std::size_t>(width)*height<=limit/depth,
        "Original fog texture exceeds the controlled sample bound");
    return static_cast<std::size_t>(width)*height*depth;
}
struct LinearAxis {int first=0,second=0;double fraction=0;};
inline LinearAxis Coordinates(double coordinate,unsigned size,bool wrap){
    Require(std::isfinite(coordinate)&&std::abs(coordinate)<=1000000,"Invalid original fog texture coordinate");
    const double normal=wrap?coordinate-std::floor(coordinate):Unit(coordinate);
    const double texel=normal*size-0.5;const int first=static_cast<int>(std::floor(texel));
    return {Axis(first,static_cast<int>(size),wrap),Axis(first+1,static_cast<int>(size),wrap),texel-first};
}
inline void GridShape(const Grid& grid){
    Require(grid.width>0&&grid.height>0&&grid.width<=256&&grid.height<=256&&
        static_cast<std::size_t>(grid.width)*grid.height<=16384&&
        grid.cells.size()==static_cast<std::size_t>(grid.width)*grid.height,
        "Invalid original fog grid shape");
    Require(!grid.wrapY||grid.height%2==0,"Odd-height vertical original fog wrapping is unsupported");
    for(const auto& cell:grid.cells)Require(!cell.visible||cell.revealed,"Visible original fog cell is unexplored");
}
}

inline MaskTexture BuildMask(const Grid& grid,unsigned texelsPerHex,std::size_t maxTexels){
    Detail::GridShape(grid);
    Detail::Require(texelsPerHex>=4&&texelsPerHex<=64&&maxTexels>0&&maxTexels<=DefaultMaxMaskTexels,
        "Invalid bounded original fog raster policy");
    MaskTexture result;result.width=static_cast<unsigned>(grid.width)*texelsPerHex;
    result.height=static_cast<unsigned>(grid.height)*texelsPerHex;
    const auto count=static_cast<std::size_t>(result.width)*result.height;
    Detail::Require(count<=maxTexels,"Original fog mask exceeds its texel budget");
    result.texels.resize(count);
    for(unsigned y=0;y<result.height;++y)for(unsigned x=0;x<result.width;++x){
        auto cell=Detail::Owner((x+0.5)/texelsPerHex,(y+0.5)/texelsPerHex);
        if(grid.wrapX)cell[0]=Detail::Wrap(cell[0],grid.width);if(grid.wrapY)cell[1]=Detail::Wrap(cell[1],grid.height);
        if(cell[0]<0||cell[1]<0||cell[0]>=grid.width||cell[1]>=grid.height)continue;
        const auto& state=grid.cells[static_cast<std::size_t>(cell[1])*grid.width+cell[0]];
        result.texels[static_cast<std::size_t>(y)*result.width+x]={state.revealed?1.0f:0.0f,
            state.revealed?0.0f:1.0f,state.visible?1.0f:0.0f};
    }
    // Candidate mask construction; retail mask target dimensions and CPU writes are not established.
    const unsigned kernel[5]={1,4,6,4,1};std::vector<Mask> temporary(count);
    for(unsigned pass=0;pass<2;++pass){
        for(unsigned y=0;y<result.height;++y)for(unsigned x=0;x<result.width;++x){
            float explored=0,visible=0;
            for(int tap=-2;tap<=2;++tap){
                const int sx=Detail::Axis(static_cast<int>(x)+(pass==0?tap:0),static_cast<int>(result.width),grid.wrapX);
                const int sy=Detail::Axis(static_cast<int>(y)+(pass==1?tap:0),static_cast<int>(result.height),grid.wrapY);
                const auto& sample=result.texels[static_cast<std::size_t>(sy)*result.width+sx];
                const float weight=static_cast<float>(kernel[tap+2])/16;
                explored+=sample.r*weight;visible+=sample.b*weight;
            }
            temporary[static_cast<std::size_t>(y)*result.width+x]={explored,1-explored,visible};
        }
        result.texels.swap(temporary);
    }
    return result;
}
inline Mask SampleMask(const MaskTexture& texture,double u,double v,bool wrapX,bool wrapY){
    Detail::Require(texture.texels.size()==Detail::Count(texture.width,texture.height)&&
        texture.texels.size()<=DefaultMaxMaskTexels,"Invalid original fog mask texture");
    const auto x=Detail::Coordinates(u,texture.width,wrapX),y=Detail::Coordinates(v,texture.height,wrapY);
    const auto at=[&](int sx,int sy)->const Mask&{const auto& value=texture.texels[static_cast<std::size_t>(sy)*texture.width+sx];
        Detail::ValidMask(value);return value;};
    return Detail::Mix(Detail::Mix(at(x.first,y.first),at(x.second,y.first),x.fraction),
        Detail::Mix(at(x.first,y.second),at(x.second,y.second),x.fraction),y.fraction);
}
inline std::array<double,2> MaskUv(double worldX,double worldZ,int gridWidth,int gridHeight){
    Detail::Require(gridWidth>0&&gridHeight>0&&gridWidth<=256&&gridHeight<=256&&std::isfinite(worldX)&&
        std::isfinite(worldZ)&&std::abs(worldX)<=1000000&&std::abs(worldZ)<=1000000,"Invalid original fog world coordinate");
    return {{worldX/gridWidth,-worldZ/(RowSpacing*gridHeight)}};
}
inline Colour Sample2D(const ImageView& image,double u,double v,AddressMode mode){
    Detail::Require(image.texels&&image.count==Detail::Count(image.width,image.height),"Invalid original fog image view");
    Detail::Require(mode==AddressMode::Clamp||mode==AddressMode::Wrap,"Invalid original fog sampler address mode");
    const bool wrap=mode==AddressMode::Wrap;
    const auto x=Detail::Coordinates(u,image.width,wrap),y=Detail::Coordinates(v,image.height,wrap);
    const auto at=[&](int sx,int sy)->const Colour&{const auto& value=image.texels[static_cast<std::size_t>(sy)*image.width+sx];
        Detail::FiniteColour(value);return value;};
    return Detail::Mix(Detail::Mix(at(x.first,y.first),at(x.second,y.first),x.fraction),
        Detail::Mix(at(x.first,y.second),at(x.second,y.second),x.fraction),y.fraction);
}
inline Colour SampleLut(const Lut3DView& lut,const Colour& coordinate){
    Detail::Require(lut.texels&&lut.count==Detail::Count(lut.width,lut.height,lut.depth),"Invalid original fog 3D LUT view");
    Detail::FiniteColour(coordinate);
    const auto x=Detail::Coordinates(coordinate.r,lut.width,false),y=Detail::Coordinates(coordinate.g,lut.height,false),
        z=Detail::Coordinates(coordinate.b,lut.depth,false);
    const auto at=[&](int sx,int sy,int sz)->const Colour&{const auto& value=
        lut.texels[(static_cast<std::size_t>(sz)*lut.height+sy)*lut.width+sx];Detail::FiniteColour(value);return value;};
    const auto plane=[&](int sz){return Detail::Mix(Detail::Mix(at(x.first,y.first,sz),at(x.second,y.first,sz),x.fraction),
        Detail::Mix(at(x.first,y.second,sz),at(x.second,y.second,sz),x.fraction),y.fraction);};
    return Detail::Mix(plane(z.first),plane(z.second),z.fraction);
}
inline Colour MixReplacement(const Colour& terrain,const Colour& replacement,const Mask& mask,bool exactRevealed){
    Detail::FiniteColour(replacement);
    // Exact ownership gates the smoothed mask before any terrain or LUT value is consumed.
    if(!exactRevealed)return {replacement.r,replacement.g,replacement.b,1};
    Detail::ValidMask(mask);if(mask.r==0)return {replacement.r,replacement.g,replacement.b,1};
    Detail::FiniteColour(terrain);const auto result=Detail::Mix(replacement,terrain,mask.r);
    return {result.r,result.g,result.b,1};
}
inline Colour BlendFow(const Colour& terrain,const Colour& replacement,const Mask& mask,
    const Colour& lutColour,bool exactRevealed){
    const auto base=MixReplacement(terrain,replacement,mask,exactRevealed);
    if(!exactRevealed)return base;
    const double amount=static_cast<double>(mask.r)*(1-mask.b);
    if(amount==0)return base;
    Detail::FiniteColour(lutColour);const auto result=Detail::Mix(base,lutColour,amount);
    return {result.r,result.g,result.b,1};
}
inline Colour ApplyFow(const Colour& terrain,const Colour& replacement,const Mask& mask,
    const Lut3DView& lut,bool exactRevealed){
    const auto base=MixReplacement(terrain,replacement,mask,exactRevealed);
    if(!exactRevealed||mask.r==0||mask.b==1)return base;
    return BlendFow(terrain,replacement,mask,SampleLut(lut,base),true);
}
inline std::array<double,2> DistanceRampUv(double screenNdcY,double row){
    Detail::Require(std::isfinite(screenNdcY)&&std::isfinite(row),"Invalid original fog ramp coordinate");
    return {{screenNdcY*0.5+0.5,row}};
}
inline double DistanceFogFactor(Vec3 retailDelta,double heightK,double density,double rampRed){
    Detail::Require(std::isfinite(retailDelta.x)&&std::isfinite(retailDelta.y)&&std::isfinite(retailDelta.z)&&
        std::abs(retailDelta.x)<=1000000&&std::abs(retailDelta.y)<=1000000&&std::abs(retailDelta.z)<=1000000&&
        std::isfinite(heightK)&&std::isfinite(density)&&heightK>=0&&density>=0,
        "Invalid original distance fog parameters");
    const double ramp=Detail::Unit(rampRed);
    if(heightK==0||density==0||ramp==0)return 0;
    constexpr double ln2=0.69314718055994530942;
    const double k=heightK*(ShaderLog2E*ln2),distanceSquared=retailDelta.x*retailDelta.x+
        retailDelta.y*retailDelta.y+retailDelta.z*retailDelta.z;
    // expm1 is stable near horizontal rays. At delta.z == 0 the shader has 0/0;
    // the continuous limit below is an explicit finite safety policy.
    const double integral=retailDelta.z==0?-k:-std::expm1(retailDelta.z*k)/retailDelta.z;
    const double exponent=integral*distanceSquared*density*(ShaderLog2E*ln2);
    if(distanceSquared==0)return 0;
    return -std::expm1((std::min)(exponent,0.0))*ramp;
}
inline Colour ApplyDistanceFog(const Colour& colour,const Colour& fogColour,double factor){
    Detail::FiniteColour(colour);Detail::FiniteColour(fogColour);
    const auto result=Detail::Mix(colour,fogColour,Detail::Unit(factor));return {result.r,result.g,result.b,1};
}
inline std::array<double,2> FlowUv(double worldX,double worldZ,double seconds,unsigned layer){
    Detail::Require(std::isfinite(worldX)&&std::isfinite(worldZ)&&std::isfinite(seconds)&&
        std::abs(worldX)<=1000000&&std::abs(worldZ)<=1000000&&std::abs(seconds)<=1000000000&&layer<3,
        "Invalid candidate original fog flow coordinate");
    const auto& spec=CandidateFlowLayers[layer];
    const double u=worldX*spec.scale+seconds*spec.speedU+spec.phaseU,
        v=worldZ*spec.scale+seconds*spec.speedV+spec.phaseV;
    return {{u-std::floor(u),v-std::floor(v)}};
}
}}
