#pragma once
#include "OriginalTerrainPackage.h"
#include <limits>

namespace ZeroSisPresentation { namespace OriginalTerrainMaterial {
// Test/reference-only borrowed mip0 view. Its owning TerrainPackage/raw DDS
// must outlive every sample. The production GPU catalogue retains no raw copy.
struct Bc3View {const unsigned char* data=nullptr;std::size_t bytes=0;unsigned width=0,height=0;};
enum class AddressMode {Wrap,Clamp};
enum class HeightSource {Texture,Null,DeclaredMissing};
inline void Require(bool value,const char* message){if(!value)throw std::invalid_argument(message);}
inline std::uint32_t Word(const unsigned char* p){return OriginalTerrain::PackageWord(p);}
inline unsigned Half(const unsigned char* p){return unsigned(p[0])|(unsigned(p[1])<<8);}
inline void Validate(Bc3View view){
    Require(view.data && view.width && view.height && view.width<=4096 && view.height<=4096,"Invalid borrowed BC3 dimensions");
    const auto count=static_cast<std::size_t>((view.width+3)/4)*((view.height+3)/4)*16;
    Require(view.bytes==count,"Borrowed BC3 extent differs");
}
inline Bc3View DdsMip0View(const unsigned char* raw,std::size_t bytes){
    Require(raw && bytes>=128 && bytes<=32u*1024u*1024u && std::memcmp(raw,"DDS ",4)==0 && Word(raw+4)==124 &&
        (Word(raw+8)&0x1007)==0x1007 && Word(raw+24)==0 && Word(raw+76)==32 && Word(raw+80)==4 && Word(raw+84)==0x35545844 && Word(raw+112)==0,
        "Reference material DDS is not bounded two-dimensional BC3");
    const auto width=Word(raw+16),height=Word(raw+12),mips=std::max(1u,Word(raw+28));
    Require(width && height && width<=4096 && height<=4096,"Reference material dimensions exceed bound");
    unsigned maximumMips=0;for(auto value=std::max(width,height);value;value>>=1)++maximumMips;
    Require(mips<=maximumMips,"Reference material mip count exceeds dimensions");
    std::size_t count=128;
    for(unsigned i=0;i<mips;++i)count+=static_cast<std::size_t>((std::max(1u,width>>i)+3)/4)*((std::max(1u,height>>i)+3)/4)*16;
    Require(count==bytes,"Reference material DDS full extent differs");
    Bc3View result{raw+128,static_cast<std::size_t>((width+3)/4)*((height+3)/4)*16,width,height};Validate(result);return result;
}
inline Bc3View ViewMip0(const OriginalTerrain::TerrainPackage& package,unsigned textureIndex){
    Require(textureIndex<package.textures.size(),"Missing reference material texture");const auto& texture=package.textures[textureIndex];
    Require(texture.offset<=package.bytes.size() && texture.bytes<=package.bytes.size()-texture.offset,"Reference material offset outside package");
    const auto result=DdsMip0View(package.bytes.data()+texture.offset,texture.bytes);
    Require(result.width==texture.width && result.height==texture.height && texture.mips==std::max(1u,Word(package.bytes.data()+texture.offset+28)),
        "Reference material header/metadata dimensions differ");return result;
}
inline const unsigned char* Block(Bc3View view,unsigned x,unsigned y){
    Validate(view);Require(x<view.width && y<view.height,"Reference material texel outside mip0");
    return view.data+(static_cast<std::size_t>(y/4)*((view.width+3)/4)+x/4)*16;
}
inline double ReadRed(Bc3View view,unsigned x,unsigned y){
    const auto* block=Block(view,x,y)+8;const unsigned c0=(Half(block)>>11)&31,c1=(Half(block+2)>>11)&31;
    const unsigned r0=(c0<<3)|(c0>>2),r1=(c1<<3)|(c1>>2);const unsigned palette[4]={r0,r1,(2*r0+r1)/3,(r0+2*r1)/3};
    // DXT5 uses the four-colour palette even when endpoint0<=endpoint1.
    return static_cast<double>(palette[(Word(block+4)>>(2*((y&3)*4+(x&3))))&3])/255.0;
}
inline double ReadAlpha(Bc3View view,unsigned x,unsigned y){
    const auto* block=Block(view,x,y);unsigned palette[8]={block[0],block[1],0,0,0,0,0,255};
    if(palette[0]>palette[1])for(unsigned i=1;i<=6;++i)palette[i+1]=((7-i)*palette[0]+i*palette[1])/7;
    else for(unsigned i=1;i<=4;++i)palette[i+1]=((5-i)*palette[0]+i*palette[1])/5;
    std::uint64_t indices=0;for(unsigned i=0;i<6;++i)indices|=static_cast<std::uint64_t>(block[i+2])<<(8*i);
    return static_cast<double>(palette[(indices>>(3*((y&3)*4+(x&3))))&7])/255.0;
}
inline unsigned Address(int value,unsigned span,AddressMode mode){
    Require(span && span<=4096 && (mode==AddressMode::Wrap || mode==AddressMode::Clamp),"Invalid reference material address mode");
    if(mode==AddressMode::Clamp)return static_cast<unsigned>(std::max(0,std::min(value,static_cast<int>(span)-1)));
    int r=value%static_cast<int>(span);if(r<0)r+=static_cast<int>(span);return static_cast<unsigned>(r);
}
template<class Read>double Bilinear(Bc3View view,double u,double v,AddressMode mode,Read read){
    Validate(view);Require(std::isfinite(u) && std::isfinite(v) && std::abs(u)<=1e9 && std::abs(v)<=1e9,"Invalid reference material UV");
    Require(mode==AddressMode::Wrap || mode==AddressMode::Clamp,"Invalid reference material address mode");
    if(mode==AddressMode::Wrap){u-=std::floor(u);v-=std::floor(v);}else{u=std::max(0.0,std::min(1.0,u));v=std::max(0.0,std::min(1.0,v));}
    const double tx=u*view.width-0.5,ty=v*view.height-0.5;const int x=static_cast<int>(std::floor(tx)),y=static_cast<int>(std::floor(ty));
    const double fx=tx-x,fy=ty-y;double result=0;
    for(int dy=0;dy<2;++dy)for(int dx=0;dx<2;++dx)result+=(dx?fx:1-fx)*(dy?fy:1-fy)*read(view,Address(x+dx,view.width,mode),Address(y+dy,view.height,mode));
    return result;
}
inline double SampleRedBilinear(Bc3View view,double u,double v,AddressMode mode=AddressMode::Wrap){return Bilinear(view,u,v,mode,ReadRed);}
inline double SampleAlphaBilinear(Bc3View view,double u,double v,AddressMode mode=AddressMode::Wrap){return Bilinear(view,u,v,mode,ReadAlpha);}
struct Layer {Bc3View diffuse,height;double u=0,v=0,weight=0;HeightSource source=HeightSource::Null;};
struct HeightResult {double height=0,totalWeight=0;unsigned sampledSlots=0;};
inline HeightResult BlendHeight(bool revealed,const std::array<Layer,8>& layers,unsigned activeCount,AddressMode mode=AddressMode::Wrap){
    HeightResult result;if(!revealed)return result;Require(activeCount<=8,"Reference material slots exceed8");
    for(unsigned i=0;i<activeCount;++i){const auto& layer=layers[i];Require(std::isfinite(layer.weight) && layer.weight>=0 && layer.weight<=1,"Invalid reference material weight");
        if(layer.weight<=0.01)continue;const auto alpha=SampleAlphaBilinear(layer.diffuse,layer.u,layer.v,mode);
        const double a2=alpha*alpha,a4=a2*a2,weight=a4*a4*layer.weight;double height=0;
        if(layer.source==HeightSource::Texture)height=SampleRedBilinear(layer.height,layer.u,layer.v,mode);
        else if(layer.source==HeightSource::DeclaredMissing)height=0.5;
        else Require(layer.source==HeightSource::Null,"Unknown reference material height source");
        result.height+=weight*height;result.totalWeight+=weight;++result.sampledSlots;
    }
    result.height=result.totalWeight>1e-8?result.height/result.totalWeight:0;return result;
}
}}
