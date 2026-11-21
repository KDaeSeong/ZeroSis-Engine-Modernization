#pragma once
#include "OriginalLightingModel.h"
#include "OriginalTerrainModel.h"
#include "OriginalTerrainBinding.h"
#include <algorithm>
#include <cstdint>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalLighting { namespace Field {
namespace Terrain=::ZeroSisPresentation::OriginalTerrain;
constexpr unsigned TexelsPerHex=64;
constexpr unsigned MaxTileExtent=68;
constexpr std::size_t MaxChunkFieldBytes=110ull*1024;
constexpr double RowSpacing=static_cast<double>(0.866025404f);
constexpr double RayRise=0.3144854605197906494140625; // DXBC 0x3ea1043d.
constexpr double Inverse96=0.010416666977107524871826171875; // DXBC 0x3c2aaaab.
struct Domain {unsigned width=0,height=0;bool wrapX=false,wrapY=false;std::vector<std::uint8_t> revealed;};
struct TileSpec {unsigned column=0,row=0,side=64,halo=1;};
struct NormalPolicy {double strength=16;}; // Proven normal-call constant; source cache remains a candidate.
struct NormalTile {
    unsigned width=0,height=0,column=0,row=0,halo=0;
    std::vector<std::array<float,3>> encoded;
    std::vector<std::uint8_t> flags; // bit0: explored centre; bit1: all eight supported taps.
    unsigned materialSamples=0;std::uint64_t fallbackTaps=0;
};
struct ShadowParams {
    double directionX=-1,directionY=1;
    double texelWorldX=1.0/64,texelWorldY=RowSpacing/64;
    double heightScale=static_cast<double>(Terrain::HeightWorldScaleCandidate)/255;
    double heightOffset=static_cast<double>(Terrain::HeightOffsetCandidate);
    double biasAndStrength=0.125;
};
struct ShadowResult {double value=0,lit=1;unsigned steps=0,samples=0;bool complete=false;};
struct ShadowTile {
    unsigned width=0,height=0,column=0,row=0,halo=0;
    std::vector<float> values;std::vector<std::uint8_t> complete;
    std::uint64_t samples=0;unsigned incompleteTexels=0;
};
namespace Detail {
inline void Require(bool condition,const char* message){if(!condition)throw std::invalid_argument(message);}
inline void Finite(double value){Require(std::isfinite(value),"Nonfinite lighting field input");}
inline void Unit(double value){Require(std::isfinite(value)&&value>=0&&value<=1,"Lighting field sample is outside UNORM domain");}
inline double Saturate(double value){Finite(value);return (std::max)(0.0,(std::min)(1.0,value));}
inline bool Shape(const Domain& domain) noexcept {
    return domain.width>0&&domain.height>0&&domain.width<=256&&domain.height<=256&&
        static_cast<std::uint64_t>(domain.width)*domain.height<=16384&&
        domain.revealed.size()==static_cast<std::size_t>(domain.width)*domain.height&&(!domain.wrapY||domain.height%2==0);
}
inline void Validate(const Domain& domain,const Terrain::Atlas& atlas){
    Require(Shape(domain),"Invalid bounded lighting field domain");Terrain::Detail::AtlasShape(atlas);
    Require(atlas.width==domain.width*64&&atlas.height==domain.height*64&&atlas.originX==-32&&atlas.originY==0&&
        atlas.wrapX==domain.wrapX&&atlas.wrapY==domain.wrapY,"Lighting field atlas/domain alignment differs");
    for(const auto state:domain.revealed)Require(state<=1,"Invalid lighting field reveal byte");
}
inline void Tile(const Domain& domain,const TileSpec& spec){
    Require(spec.side==64&&spec.halo<=2&&spec.column<domain.width&&spec.row<domain.height,"Invalid canonical lighting tile");
}
inline unsigned Extent(const TileSpec& spec){return spec.side+2*spec.halo;}
inline double Coordinate(unsigned tile,unsigned at,unsigned halo){return tile*64.0+at-halo+0.5;}
inline int Wrap(int value,unsigned span){const int length=static_cast<int>(span),remainder=value%length;return remainder<0?remainder+length:remainder;}
inline double Canonical(double value,unsigned span,bool wrap){
    return wrap?value-std::floor(value/span)*span:value;
}
inline bool RevealedAt(const Domain& domain,double x,double y){
    // Geometry world X*64 and -worldZ/RowSpacing*64 map directly to atlas indices.
    // Atlas origin is validated above and is never added to a field sample index.
    const double row=y/64,q=x/64-row*0.5;auto cell=Terrain::CubeToOffset(Terrain::RoundCube({q,row,-q-row}));
    if(domain.wrapX)cell[0]=Wrap(cell[0],domain.width);if(domain.wrapY)cell[1]=Wrap(cell[1],domain.height);
    return cell[0]>=0&&cell[1]>=0&&cell[0]<static_cast<int>(domain.width)&&cell[1]<static_cast<int>(domain.height)&&
        domain.revealed[static_cast<std::size_t>(cell[1])*domain.width+cell[0]]!=0;
}
inline bool KnownNode(const Domain& domain,const Terrain::Atlas& atlas,int x,int y){
    if(domain.wrapX)x=Wrap(x,atlas.width);if(domain.wrapY)y=Wrap(y,atlas.height);
    if(x<0||y<0||x>=static_cast<int>(atlas.width)||y>=static_cast<int>(atlas.height))return false;
    if(!RevealedAt(domain,x,y))return false;
    return atlas.known[static_cast<std::size_t>(y)*atlas.width+static_cast<unsigned>(x)]!=0;
}
inline bool KnownSupport(const Domain& domain,const Terrain::Atlas& atlas,double x,double y){
    if(!std::isfinite(x)||!std::isfinite(y)||std::abs(x)>1000000||std::abs(y)>1000000)return false;
    if(!RevealedAt(domain,x,y))return false;
    const int ix=static_cast<int>(std::floor(x)),iy=static_cast<int>(std::floor(y));
    // Strict support policy checks all four source nodes before any height read,
    // including zero-weight bilinear corners at integer sample positions.
    return KnownNode(domain,atlas,ix,iy)&&KnownNode(domain,atlas,ix+1,iy)&&
        KnownNode(domain,atlas,ix,iy+1)&&KnownNode(domain,atlas,ix+1,iy+1);
}
inline std::size_t At(const Terrain::Atlas& atlas,int x,int y){
    if(atlas.wrapX)x=Wrap(x,atlas.width);if(atlas.wrapY)y=Wrap(y,atlas.height);
    return static_cast<std::size_t>(y)*atlas.width+static_cast<unsigned>(x);
}
inline double Alpha(const Terrain::Atlas& atlas,double x,double y,double offset){
    const int ix=static_cast<int>(std::floor(x)),iy=static_cast<int>(std::floor(y));
    const double fx=x-ix,fy=y-iy;
    const auto sample=[&](int dx,int dy){const double value=static_cast<double>(atlas.heights[At(atlas,ix+dx,iy+dy)])+offset;
        return Saturate(value);};
    const double a=sample(0,0),b=sample(1,0),c=sample(0,1),d=sample(1,1);
    return (a+(b-a)*fx)*(1-fy)+(c+(d-c)*fx)*fy;
}
inline void ShadowDomain(const ShadowParams& params,bool bounded){
    Finite(params.directionX);Finite(params.directionY);Finite(params.texelWorldX);Finite(params.texelWorldY);
    Finite(params.heightScale);Finite(params.heightOffset);Finite(params.biasAndStrength);
    Require(std::abs(params.directionX)<=1000000&&std::abs(params.directionY)<=1000000&&
        params.texelWorldX>=0&&params.texelWorldX<=1000000&&params.texelWorldY>=0&&params.texelWorldY<=1000000&&
        params.heightScale>=0&&params.heightScale<=1024&&params.heightOffset>=0&&params.heightOffset<=1,
        "Invalid lighting shadow calibration");
    if(bounded)Unit(params.biasAndStrength);
}
}
template<class View>Domain CaptureDomain(const View& view){
    Detail::Require(view.gridWidth>0&&view.gridHeight>0&&view.gridWidth<=256&&view.gridHeight<=256&&
        static_cast<std::uint64_t>(view.gridWidth)*view.gridHeight<=16384,"Invalid lighting field detached dimensions");
    Domain result;result.width=static_cast<unsigned>(view.gridWidth);result.height=static_cast<unsigned>(view.gridHeight);
    result.wrapX=view.wrapX;result.wrapY=view.wrapY;
    const auto count=static_cast<std::size_t>(result.width)*result.height;
    Detail::Require(view.plots.size()<=count,"Lighting field detached plot list exceeds map coverage");
    result.revealed.assign(count,0);std::vector<std::uint8_t> seen(count,0);
    for(const auto& plot:view.plots){Detail::Require(plot.x>=0&&plot.y>=0&&plot.x<view.gridWidth&&plot.y<view.gridHeight,
            "Invalid lighting field detached plot coordinate");
        const auto index=static_cast<std::size_t>(plot.y)*result.width+static_cast<unsigned>(plot.x);
        Detail::Require(!seen[index],"Duplicate lighting field detached coordinate");seen[index]=1;
        result.revealed[index]=static_cast<std::uint8_t>(plot.revealed?1u:0u);}
    Detail::Require(Detail::Shape(result),"Unsupported lighting field wrapping");return result;
}
inline unsigned TileExtent(const TileSpec& spec){Detail::Require(spec.side==64&&spec.halo<=2,"Invalid lighting tile extent");return Detail::Extent(spec);}
inline std::vector<std::uint8_t> BuildKnownSupport(const Domain& domain,const Terrain::Atlas& atlas,const TileSpec& spec){
    Detail::Validate(domain,atlas);Detail::Tile(domain,spec);const unsigned extent=Detail::Extent(spec);
    std::vector<std::uint8_t> result(static_cast<std::size_t>(extent)*extent,0);
    for(unsigned y=0;y<extent;++y)for(unsigned x=0;x<extent;++x)result[static_cast<std::size_t>(y)*extent+x]=static_cast<std::uint8_t>(
        Detail::KnownSupport(domain,atlas,Detail::Coordinate(spec.column,x,spec.halo),Detail::Coordinate(spec.row,y,spec.halo))?1u:0u);
    return result;
}
template<class MaterialHeight>NormalTile BuildNormalTile(const Domain& domain,const Terrain::Atlas& atlas,const TileSpec& spec,
    MaterialHeight materialHeight,const NormalPolicy& policy=NormalPolicy{}){
    Detail::Validate(domain,atlas);Detail::Tile(domain,spec);Detail::Require(spec.halo<=1,"Normal tile needs one additional source halo");
    Detail::Finite(policy.strength);TileSpec heightSpec=spec;++heightSpec.halo;
    const unsigned heightSide=Detail::Extent(heightSpec),side=Detail::Extent(spec);
    const auto support=BuildKnownSupport(domain,atlas,heightSpec);std::vector<float> heights(support.size(),0);
    NormalTile result;result.width=result.height=side;result.column=spec.column;result.row=spec.row;result.halo=spec.halo;
    result.encoded.resize(static_cast<std::size_t>(side)*side,{{0.5f,0.5f,1}});result.flags.assign(result.encoded.size(),0);
    for(unsigned y=0;y<heightSide;++y)for(unsigned x=0;x<heightSide;++x){const auto at=static_cast<std::size_t>(y)*heightSide+x;
        if(!support[at])continue;
        const double px=Detail::Canonical(Detail::Coordinate(spec.column,x,heightSpec.halo),atlas.width,domain.wrapX),
            py=Detail::Canonical(Detail::Coordinate(spec.row,y,heightSpec.halo),atlas.height,domain.wrapY);
        const double value=materialHeight(px,py);Detail::Unit(value);heights[at]=static_cast<float>(value);++result.materialSamples;
    }
    const int dx[8]={-1,-1,1,1,-1,1,0,0},dy[8]={0,-1,-1,0,1,1,-1,1};
    for(unsigned y=0;y<side;++y)for(unsigned x=0;x<side;++x){const unsigned hx=x+1,hy=y+1;const auto center=static_cast<std::size_t>(hy)*heightSide+hx;
        if(!support[center])continue;std::array<double,8> taps{};bool complete=true;
        for(unsigned tap=0;tap<8;++tap){const auto at=static_cast<std::size_t>(static_cast<int>(hy)+dy[tap])*heightSide+
                static_cast<unsigned>(static_cast<int>(hx)+dx[tap]);
            if(support[at])taps[tap]=heights[at];else{taps[tap]=heights[center];complete=false;++result.fallbackTaps;}}
        const auto normal=OriginalLighting::SobelNormal(taps,policy.strength);const auto at=static_cast<std::size_t>(y)*side+x;
        result.encoded[at]={{static_cast<float>(normal.encoded.r),static_cast<float>(normal.encoded.g),static_cast<float>(normal.encoded.b)}};
        result.flags[at]=static_cast<std::uint8_t>(complete?3u:1u);
    }
    Detail::Require(heights.size()*sizeof(float)+support.size()+result.encoded.size()*sizeof(result.encoded[0])+result.flags.size()<=MaxChunkFieldBytes,
        "Normal tile exceeded its owned field payload budget");return result;
}
inline ShadowResult RawShadow40(double initialAlpha,const std::array<double,40>& alpha,double stepLength,const ShadowParams& params){
    Detail::ShadowDomain(params,false);Detail::Unit(initialAlpha);Detail::Require(std::isfinite(stepLength)&&stepLength>=0,"Invalid shadow step length");
    const double rise=stepLength*RayRise;double ray=(initialAlpha*params.heightScale)*255+params.biasAndStrength;
    ray+=rise;double lit=1;
    for(const auto sample:alpha){Detail::Unit(sample);ray+=rise;Detail::Finite(ray);
        const double height=(sample*255)*params.heightScale,soft=1-Detail::Saturate((sample*255-64)*Inverse96);
        if(ray<height)lit=(std::min)(lit,soft);
    }
    const double value=(1-lit)*params.biasAndStrength;Detail::Finite(value);return {value,lit,40,41,true};
}
template<class Known,class Sample>ShadowResult GuardedShadow40(double x,double y,const ShadowParams& params,Known known,Sample sample){
    Detail::ShadowDomain(params,true);Detail::Require(std::isfinite(x)&&std::isfinite(y)&&std::abs(x)<=1000000&&std::abs(y)<=1000000,"Invalid shadow origin");
    const double span=(std::max)(std::abs(params.directionX),std::abs(params.directionY));ShadowResult result;
    if(span==0||!known(x,y))return result;
    const double dx=params.directionX/span,dy=params.directionY/span;
    const double wx=dx*params.texelWorldX,wy=dy*params.texelWorldY,stepLength=std::sqrt(wx*wx+wy*wy);
    const double initial=sample(x,y);++result.samples;Detail::Unit(initial);std::array<double,40> alpha{};
    x+=dx;y+=dy;
    for(unsigned i=0;i<40;++i){x+=dx;y+=dy;
        if(!known(x,y))return result;alpha[i]=sample(x,y);++result.samples;++result.steps;Detail::Unit(alpha[i]);}
    return RawShadow40(initial,alpha,stepLength,params);
}
inline ShadowTile BuildShadowTile(const Domain& domain,const Terrain::Atlas& atlas,const TileSpec& spec,const ShadowParams& params=ShadowParams{}){
    Detail::Validate(domain,atlas);Detail::Tile(domain,spec);Detail::ShadowDomain(params,true);const unsigned side=Detail::Extent(spec);
    ShadowTile result;result.width=result.height=side;result.column=spec.column;result.row=spec.row;result.halo=spec.halo;
    result.values.assign(static_cast<std::size_t>(side)*side,0);result.complete.assign(result.values.size(),0);
    const auto known=[&](double x,double y){return Detail::KnownSupport(domain,atlas,x,y);};
    const auto sample=[&](double x,double y){return Detail::Alpha(atlas,x,y,params.heightOffset);};
    for(unsigned y=0;y<side;++y)for(unsigned x=0;x<side;++x){const auto shadow=GuardedShadow40(Detail::Coordinate(spec.column,x,spec.halo),
            Detail::Coordinate(spec.row,y,spec.halo),params,known,sample);const auto at=static_cast<std::size_t>(y)*side+x;
        result.values[at]=static_cast<float>(shadow.value);result.complete[at]=static_cast<std::uint8_t>(shadow.complete?1u:0u);result.samples+=shadow.samples;
        if(!shadow.complete)++result.incompleteTexels;}
    Detail::Require(result.values.size()*sizeof(float)+result.complete.size()<=MaxChunkFieldBytes,"Shadow tile exceeded owned field payload budget");return result;
}
inline std::uint16_t ToUnorm16(double value){return static_cast<std::uint16_t>(std::floor(Detail::Saturate(value)*65535+0.5));}
inline double FromUnorm16(std::uint16_t value){return value/65535.0;}
}}}
