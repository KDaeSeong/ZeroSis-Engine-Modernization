#pragma once
#include "OriginalTerrainSha256.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalWaterLean {
// River roles are reserved; this version deliberately accepts only the one
// water texture used by the current surface shader.
enum class AssetRole:std::uint32_t {WaterBumps=1,RiverRough=2,RiverSmooth=3};
enum class TextureFormat {Rgba16Unorm,R16Unorm};
struct Level {std::size_t offset=0,bytes=0,rowPitch=0,slicePitch=0;unsigned width=0,height=0;};
struct Plane {TextureFormat format=TextureFormat::Rgba16Unorm;unsigned channels=0;std::vector<Level> levels;};
struct Texture {
    unsigned width=0,height=0,mips=0;float outputScale=0;unsigned char flagAt32=0;
    std::array<unsigned char,3> opaquePadding={{0,0,0}};std::array<Plane,2> planes;
};
struct Asset {AssetRole role=AssetRole::WaterBumps;std::string name;std::size_t offset=0,bytes=0;Texture texture;};
struct LeanPackage {std::vector<unsigned char> bytes;std::vector<Asset> assets;};
struct EncodedTexel {std::array<double,4> rgba={{0,0,0,0}};double crossR=0;};
struct Moments {double meanX=0,meanY=0,secondXX=0,secondYY=0,secondXY=0;};
inline void Require(bool value,const char* reason){if(!value)throw std::invalid_argument(reason);}
inline std::uint32_t Word(const unsigned char* p){return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|(std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
inline unsigned Half(const unsigned char* p){return unsigned(p[0])|(unsigned(p[1])<<8);}
inline Texture DecodeTexture(const unsigned char* raw,std::size_t size,std::size_t packageOffset){
    Require(size>=46 && size<=4u*1024u*1024u && std::memcmp(raw,"LEAN",4)==0,"Invalid bounded water LEAN texture");
    Texture result;const auto scale=Word(raw+4);std::memcpy(&result.outputScale,&scale,sizeof(scale));
    result.width=Word(raw+8);result.height=Word(raw+12);result.mips=Word(raw+16);result.flagAt32=raw[32];
    std::copy(raw+33,raw+36,result.opaquePadding.begin());
    Require(std::isfinite(result.outputScale) && result.outputScale>0 && result.outputScale<=16 && result.width && result.height &&
        result.width<=1024 && result.height<=1024 && Word(raw+20)==2 && result.flagAt32==1,"Unsupported water LEAN shape/encoding");
    unsigned maximumMips=0;for(auto dimension=std::max(result.width,result.height);dimension;dimension>>=1)++maximumMips;
    Require(result.mips==maximumMips,"Water LEAN must contain a full mip chain");
    std::size_t texels=0;for(unsigned level=0;level<result.mips;++level)
        texels+=static_cast<std::size_t>(std::max(1u,result.width>>level))*std::max(1u,result.height>>level);
    const std::size_t second=36+texels*8;
    Require(Word(raw+24)==36 && Word(raw+28)==second && size==second+texels*2,"Water LEAN two-plane extent differs");
    Require(packageOffset<=8u*1024u*1024u && size<=8u*1024u*1024u-packageOffset,"Water LEAN texture escapes package bound");
    for(unsigned plane=0;plane<2;++plane){
        auto& descriptor=result.planes[plane];descriptor.channels=plane?1u:4u;
        descriptor.format=plane?TextureFormat::R16Unorm:TextureFormat::Rgba16Unorm;std::size_t cursor=plane?second:36;
        for(unsigned level=0;level<result.mips;++level){
            const auto width=std::max(1u,result.width>>level),height=std::max(1u,result.height>>level);
            const std::size_t pitch=static_cast<std::size_t>(width)*descriptor.channels*2,count=pitch*height;
            Require(cursor<=size && count<=size-cursor,"Truncated water LEAN mip plane");
            descriptor.levels.push_back({packageOffset+cursor,count,pitch,count,width,height});cursor+=count;
        }
        Require(cursor==(plane?size:second),"Water LEAN mip plane has trailing data");
    }
    return result;
}
inline LeanPackage DecodePackage(std::vector<unsigned char> bytes,const std::string& expectedSha){
    Require(bytes.size()>=16 && bytes.size()<=8u*1024u*1024u,"Water LEAN package exceeds size bound");
    Require(expectedSha.size()==64 && OriginalTerrain::Sha256Hex(bytes.data(),bytes.size())==expectedSha,"Water LEAN outer SHA256 differs");
    LeanPackage result;result.bytes=std::move(bytes);const auto& raw=result.bytes;std::size_t cursor=0;
    const auto take=[&](std::size_t count){Require(count<=raw.size()-cursor,"Truncated water LEAN package");const auto* p=raw.data()+cursor;cursor+=count;return p;};
    const auto u32=[&](){return Word(take(4));};
    Require(std::memcmp(take(8),"ZSWLEAN1",8)==0 && u32()==1 && u32()==1,"Unknown water LEAN format/count");
    const auto role=u32(),nameBytes=u32(),count=u32();const auto* digest=take(32);
    Require(role==1 && nameBytes>0 && nameBytes<=64 && count>=46 && count<=4u*1024u*1024u,"Invalid water LEAN record bounds/role");
    const auto* text=take(nameBytes);const std::string name(reinterpret_cast<const char*>(text),nameBytes);
    Require(name=="waterbumps16.lean","Noncanonical water LEAN name");const auto offset=cursor;const auto* data=take(count);
    const auto sha=OriginalTerrain::Sha256(data,count);Require(std::memcmp(sha.data(),digest,32)==0,"Water LEAN asset SHA256 differs");
    Asset asset;asset.role=AssetRole::WaterBumps;asset.name=name;asset.offset=offset;asset.bytes=count;asset.texture=DecodeTexture(data,count,offset);
    result.assets.push_back(std::move(asset));Require(cursor==raw.size(),"Water LEAN package trailing data");return result;
}
inline const Asset& FindAsset(const LeanPackage& package,AssetRole role){
    Require(role==AssetRole::WaterBumps && package.assets.size()==1 && package.assets[0].role==role,"Unsupported water LEAN role");return package.assets[0];
}
inline const unsigned char* AssetData(const LeanPackage& package,const Asset& asset){
    Require(asset.bytes>0 && asset.offset<=package.bytes.size() && asset.bytes<=package.bytes.size()-asset.offset,"Water LEAN asset outside package");
    return package.bytes.data()+asset.offset;
}
inline EncodedTexel ReadTexelUnorm(const LeanPackage& package,AssetRole role,unsigned mip,unsigned x,unsigned y){
    const auto& asset=FindAsset(package,role);AssetData(package,asset);const auto& texture=asset.texture;
    Require(texture.width>0 && texture.height>0 && texture.width<=1024 && texture.height<=1024 && texture.mips<=11 && mip<texture.mips,
        "Invalid water LEAN texel mip");EncodedTexel result;
    for(unsigned plane=0;plane<2;++plane){
        const auto& descriptor=texture.planes[plane];const unsigned channels=plane?1u:4u;
        Require(descriptor.channels==channels && descriptor.format==(plane?TextureFormat::R16Unorm:TextureFormat::Rgba16Unorm) &&
            descriptor.levels.size()==texture.mips,"Invalid water LEAN plane descriptor");const auto& level=descriptor.levels[mip];
        Require(level.width==std::max(1u,texture.width>>mip) && level.height==std::max(1u,texture.height>>mip) && x<level.width && y<level.height &&
            level.rowPitch==static_cast<std::size_t>(level.width)*channels*2 && level.bytes==level.rowPitch*level.height && level.slicePitch==level.bytes &&
            level.offset>=asset.offset && level.offset<=asset.offset+asset.bytes && level.bytes<=asset.offset+asset.bytes-level.offset,
            "Water LEAN texel escaped mip bounds");
        const auto offset=level.offset+static_cast<std::size_t>(y)*level.rowPitch+static_cast<std::size_t>(x)*channels*2;
        for(unsigned channel=0;channel<channels;++channel){
            const double value=Half(package.bytes.data()+offset+channel*2)/65535.0;
            if(plane)result.crossR=value;else result.rgba[channel]=value;
        }
    }
    return result;
}
// Water PS2 channel decode. The caller supplies shader S explicitly. Binding S
// to Texture::outputScale is a calibration candidate, not a recovered link.
inline Moments DecodeMoments(const EncodedTexel& raw,bool mirrorX=false,double shaderScale=1.0){
    for(const auto value:raw.rgba)Require(std::isfinite(value) && value>=0 && value<=1,"Invalid encoded LEAN RGBA");
    Require(std::isfinite(raw.crossR) && raw.crossR>=0 && raw.crossR<=1 && std::isfinite(shaderScale) &&
        shaderScale>=0.000001 && shaderScale<=1000000,"Invalid LEAN cross moment or shader scale");
    const double sign=mirrorX?-1.0:1.0,square=shaderScale*shaderScale;
    return {sign*(2*raw.rgba[0]-1)/shaderScale,(2*raw.rgba[1]-1)/shaderScale,
        raw.rgba[2]/square,raw.rgba[3]/square,sign*(2*raw.crossR-1)/square};
}
}}
