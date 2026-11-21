#pragma once
#include "OriginalIceContract.h"
#include "OriginalTerrainSha256.h"
#include <cstring>
#include <string>

namespace ZeroSisPresentation { namespace OriginalIce {
inline std::uint32_t Word(const unsigned char* p)noexcept{return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
inline void VerifySource(const std::vector<unsigned char>& raw,const std::string& expectedSha){
    Require(expectedSha.size()==64&&raw.size()<=4u*1024u*1024u&&OriginalTerrain::Sha256Hex(raw.data(),raw.size())==expectedSha,
        "Original ice source SHA differs");
}
struct Level {unsigned width=0,height=0;std::size_t offset=0,bytes=0,rowPitch=0;};
struct LeanTexture {unsigned width=0,height=0,mips=0;float outputScale=0;std::array<std::vector<Level>,2> planes;};
inline unsigned MipCount(unsigned width,unsigned height)noexcept{unsigned count=0;for(auto value=std::max(width,height);value;value>>=1)++count;return count;}
// Only the two original8-bit ice planes. Water's16-bit package remains intact.
inline LeanTexture DecodeLean8(const unsigned char* raw,std::size_t bytes){
    Require(raw&&bytes>=41&&bytes<=4u*1024u*1024u&&std::memcmp(raw,"LEAN",4)==0,"Invalid bounded ice LEAN");
    LeanTexture result;const auto scale=Word(raw+4);std::memcpy(&result.outputScale,&scale,4);
    result.width=Word(raw+8);result.height=Word(raw+12);result.mips=Word(raw+16);
    Require(std::isfinite(result.outputScale)&&result.outputScale>0&&result.outputScale<=16&&result.width>0&&result.height>0&&
        result.width<=1024&&result.height<=1024&&result.mips==MipCount(result.width,result.height)&&Word(raw+20)==1&&raw[32]==1,
        "Unsupported ice LEAN shape/encoding");
    std::size_t texels=0;for(unsigned mip=0;mip<result.mips;++mip)texels+=std::size_t(std::max(1u,result.width>>mip))*std::max(1u,result.height>>mip);
    const std::size_t second=36+texels*4;
    Require(Word(raw+24)==36&&Word(raw+28)==second&&bytes==second+texels,"Ice LEAN two-plane extent differs");
    for(unsigned plane=0;plane<2;++plane){std::size_t cursor=plane?second:36;const unsigned channels=plane?1u:4u;
        for(unsigned mip=0;mip<result.mips;++mip){const unsigned w=std::max(1u,result.width>>mip),h=std::max(1u,result.height>>mip);
            const std::size_t pitch=std::size_t(w)*channels,count=pitch*h;
            Require(cursor<=bytes&&count<=bytes-cursor,"Truncated ice LEAN plane");result.planes[plane].push_back({w,h,cursor,count,pitch});cursor+=count;}
        Require(cursor==(plane?bytes:second),"Ice LEAN plane has trailing bytes");}
    return result;
}
inline std::array<unsigned,5> ReadLeanTexel(const unsigned char* raw,std::size_t bytes,unsigned mip,unsigned x,unsigned y){
    const auto texture=DecodeLean8(raw,bytes);Require(mip<texture.mips,"Invalid ice LEAN mip");std::array<unsigned,5> result{};
    for(unsigned plane=0;plane<2;++plane){const auto& level=texture.planes[plane][mip];const unsigned channels=plane?1u:4u;
        Require(x<level.width&&y<level.height,"Ice LEAN texel escapes mip");const auto offset=level.offset+std::size_t(y)*level.rowPitch+std::size_t(x)*channels;
        for(unsigned channel=0;channel<channels;++channel)result[plane?4:channel]=raw[offset+channel];}
    return result;
}
enum class DdsRole {Diffuse,SideDiffuse,Environment,Displacement};
enum class DdsFormat {Bc1Unorm,Bc3Unorm,R8Unorm};
struct DdsTexture {DdsFormat format=DdsFormat::R8Unorm;unsigned width=0,height=0,mips=0,faces=1;std::vector<Level> levels;};
inline DdsTexture DecodeDds(const unsigned char* raw,std::size_t bytes,DdsRole role){
    Require(raw&&bytes>=128&&bytes<=4u*1024u*1024u&&std::memcmp(raw,"DDS ",4)==0,"Invalid bounded ice DDS");
    const auto word=[&](unsigned index){return Word(raw+index*4);};DdsTexture result;
    Require(word(1)==124&&(word(2)&0x1007)==0x1007&&word(6)==0&&word(19)==32,"Unsupported ice DDS header");
    result.width=word(4);result.height=word(3);result.mips=std::max(1u,word(7));
    Require(result.width>0&&result.height>0&&result.width<=2048&&result.height<=2048&&result.mips==MipCount(result.width,result.height),"Unsupported ice DDS dimensions/mips");
    unsigned block=0;
    if(role==DdsRole::Environment){Require(word(20)==4&&word(21)==0x31545844&&word(28)==0xfe00&&result.width==result.height,"Ice environment must be original BC1 cube");
        result.format=DdsFormat::Bc1Unorm;result.faces=6;block=8;}
    else if(role==DdsRole::Displacement){Require(word(20)==0x20000&&word(21)==0&&word(22)==8&&word(23)==255&&word(24)==0&&word(25)==0&&word(26)==0&&word(28)==0,
        "Ice displacement must be original L8");result.format=DdsFormat::R8Unorm;}
    else{Require((role==DdsRole::Diffuse||role==DdsRole::SideDiffuse)&&word(20)==4&&word(21)==0x35545844&&word(28)==0,"Ice diffuse must be original BC3");
        result.format=DdsFormat::Bc3Unorm;block=16;}
    std::size_t cursor=128;
    for(unsigned face=0;face<result.faces;++face)for(unsigned mip=0;mip<result.mips;++mip){
        const unsigned w=std::max(1u,result.width>>mip),h=std::max(1u,result.height>>mip);
        const std::size_t pitch=block?std::size_t((w+3)/4)*block:w,count=pitch*(block?(h+3)/4:h);
        Require(cursor<=bytes&&count<=bytes-cursor,"Truncated ice DDS face/mip");result.levels.push_back({w,h,cursor,count,pitch});cursor+=count;}
    Require(cursor==bytes,"Ice DDS has trailing bytes");return result;
}
}}
