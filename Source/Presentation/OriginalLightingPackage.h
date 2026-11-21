#pragma once
#include "OriginalFogPackage.h"
#include <limits>

namespace ZeroSisPresentation { namespace OriginalLighting {
enum class AssetRole:std::uint32_t {SunlightGeneric=1,SunlightAmerica,SunlightAsia,SunlightAfrica,SunlightEurope,
    ShadowlightGeneric,ShadowlightAmerica,ShadowlightAsia,ShadowlightAfrica,ShadowlightEurope,
    TerrainLutGeneric,TerrainLutAmerica,TerrainLutAsia,TerrainLutAfrica,TerrainLutEurope};
struct CubeLevel {unsigned face=0,mip=0,width=0,height=0;std::size_t offset=0,bytes=0,rowPitch=0;};
struct Cube {unsigned width=0,height=0,mips=0;std::vector<CubeLevel> levels;};
struct Asset {AssetRole role=AssetRole::SunlightGeneric;std::string name;unsigned blobIndex=0;std::size_t offset=0,bytes=0;Cube cube;};
struct LightingPackage {std::vector<unsigned char> bytes;std::vector<Asset> assets;unsigned blobCount=0;};
inline void Require(bool value,const char* message){if(!value)throw std::invalid_argument(message);}
inline std::uint32_t Word(const unsigned char* p){return OriginalFog::Word(p);}
inline const char* RoleName(unsigned role){
    static const char* const names[]={"sunlight_generic_terrain.dds","sunlight_america_terrain.dds","sunlight_asia_terrain.dds",
        "sunlight_africa_terrain.dds","sunlight_europe_terrain.dds","shadowlight_generic_terrain.dds","shadowlight_america_terrain.dds",
        "shadowlight_asia_terrain.dds","shadowlight_africa_terrain.dds","shadowlight_europe_terrain.dds","terrain_generic_colorkey.tga",
        "terrain_america_colorkey.tga","terrain_asia_colorkey.tga","terrain_africa_colorkey.tga","terrain_europe_colorkey.tga"};
    Require(role>=1 && role<=15,"Invalid lighting role");return names[role-1];
}
inline AssetRole SunlightRole(unsigned continent){Require(continent<=4,"Invalid lighting continent");return static_cast<AssetRole>(1+continent);}
inline AssetRole ShadowlightRole(unsigned continent){Require(continent<=4,"Invalid lighting continent");return static_cast<AssetRole>(6+continent);}
inline AssetRole TerrainLutRole(unsigned continent){Require(continent<=4,"Invalid lighting continent");return static_cast<AssetRole>(11+continent);}
inline Cube DecodeCubeTexture(const unsigned char* raw,std::size_t count,std::size_t packageOffset){
    Require(count>=128 && count<=300000 && raw && std::memcmp(raw,"DDS ",4)==0 && Word(raw+4)==124 && Word(raw+8)==0x21007 &&
        Word(raw+24)==0 && Word(raw+76)==32 && Word(raw+80)==4 && Word(raw+84)==0x31545844 && Word(raw+108)==0x401008 &&
        Word(raw+112)==0xfe00,"Invalid bounded lighting cube DDS header/caps");
    for(unsigned offset=88;offset<=104;offset+=4)Require(Word(raw+offset)==0,"Unexpected lighting DDS pixel masks");
    // Retail retains a COLO/R_NA tool tag in caps3/caps4/reserved. Preserve
    // these opaque bytes; texture shape is bounded by caps2 and exact extent.
    Cube result;result.width=Word(raw+16);result.height=Word(raw+12);result.mips=Word(raw+28);
    Require(result.width && result.width<=128 && result.height==result.width && (result.width&(result.width-1))==0,"Invalid lighting cube dimensions");
    unsigned mips=0;for(auto size=result.width;size;size>>=1)++mips;Require(result.mips==mips,"Lighting cube requires full mip chain");
    Require(packageOffset<=2u*1024u*1024u && count<=2u*1024u*1024u-packageOffset,"Lighting cube absolute offset exceeds bound");
    std::size_t cursor=128;
    for(unsigned face=0;face<6;++face)for(unsigned mip=0;mip<mips;++mip){
        const auto size=std::max(1u,result.width>>mip);const std::size_t pitch=static_cast<std::size_t>((size+3)/4)*8,countBytes=pitch*((size+3)/4);
        Require(cursor<=count && countBytes<=count-cursor,"Truncated lighting cube face/mip");
        result.levels.push_back({face,mip,size,size,packageOffset+cursor,countBytes,pitch});cursor+=countBytes;
    }
    Require(cursor==count,"Lighting cube extent/trailing bytes differ");return result;
}
inline LightingPackage DecodePackage(std::vector<unsigned char> bytes,const std::string& expectedSha){
    Require(bytes.size()>=20 && bytes.size()<=2u*1024u*1024u,"Lighting package exceeds bound");
    Require(expectedSha.size()==64 && OriginalTerrain::Sha256Hex(bytes.data(),bytes.size())==expectedSha,"Lighting outer SHA differs");
    LightingPackage result;result.bytes=std::move(bytes);const auto& raw=result.bytes;std::size_t cursor=0;
    const auto take=[&](std::size_t count){Require(cursor<=raw.size() && count<=raw.size()-cursor,"Truncated lighting package");const auto* p=raw.data()+cursor;cursor+=count;return p;};
    const auto u32=[&](){return Word(take(4));};
    Require(std::memcmp(take(8),"ZSLIGHT1",8)==0 && u32()==1 && u32()==15,"Unknown lighting format/count");
    result.blobCount=u32();Require(result.blobCount && result.blobCount<=15,"Invalid lighting blob count");
    unsigned seen=0;std::array<bool,15> referenced{};
    for(unsigned role=1;role<=15;++role){
        const auto index=u32(),length=u32(),blob=u32();Require(index==role && length && length<=64 && blob<result.blobCount,"Invalid ordered lighting descriptor");
        const auto* text=take(length);const std::string name(reinterpret_cast<const char*>(text),length);Require(name==RoleName(role),"Noncanonical lighting asset name");
        if(!referenced[blob]){Require(blob==seen,"Lighting blobs not in first-reference order");referenced[blob]=true;++seen;}
        Asset asset;asset.role=static_cast<AssetRole>(role);asset.name=name;asset.blobIndex=blob;result.assets.push_back(std::move(asset));
    }
    Require(seen==result.blobCount,"Unreferenced lighting blob");
    struct Blob {std::size_t offset=0,bytes=0;std::array<unsigned char,32> sha{};};std::vector<Blob> blobs;
    for(unsigned index=0;index<result.blobCount;++index){
        const auto count=u32();Require(count && count<=300000,"Unbounded lighting blob");const auto* expected=take(32);const auto offset=cursor;const auto* data=take(count);
        const auto sha=OriginalTerrain::Sha256(data,count);Require(std::memcmp(expected,sha.data(),32)==0,"Lighting blob SHA differs");
        for(const auto& previous:blobs)Require(previous.sha!=sha,"Duplicate lighting blob bytes");
        blobs.push_back({offset,count,sha});
    }
    Require(cursor==raw.size(),"Lighting package has trailing data");
    for(auto& asset:result.assets){const auto& blob=blobs[asset.blobIndex];asset.offset=blob.offset;asset.bytes=blob.bytes;
        if(static_cast<unsigned>(asset.role)<=10)asset.cube=DecodeCubeTexture(raw.data()+asset.offset,asset.bytes,asset.offset);
        else OriginalFog::ValidateTga(raw.data()+asset.offset,asset.bytes);
    }
    return result;
}
inline const Asset& FindAsset(const LightingPackage& package,AssetRole role){
    const auto index=static_cast<unsigned>(role);Require(index>=1 && index<=package.assets.size(),"Missing lighting asset role");
    const auto& asset=package.assets[index-1];Require(asset.role==role,"Lighting asset role differs");return asset;
}
inline const unsigned char* AssetData(const LightingPackage& package,const Asset& asset){
    Require(asset.offset<=package.bytes.size() && asset.bytes<=package.bytes.size()-asset.offset,"Lighting asset range outside package");
    return package.bytes.data()+asset.offset;
}
// Standard TGA origin -> first32^3 pixels -> R/x-fastest. Retail loader,
// runtime LUT selection and sampler equivalence remain unverified candidates.
inline std::vector<unsigned char> CandidateTerrainLut32Rgba(const LightingPackage& package,unsigned continent){
    const auto& asset=FindAsset(package,TerrainLutRole(continent));const auto* raw=AssetData(package,asset);OriginalFog::ValidateTga(raw,asset.bytes);
    const auto width=OriginalFog::Half(raw+12),height=OriginalFog::Half(raw+14);const bool top=(raw[17]&32)!=0,right=(raw[17]&16)!=0;
    std::vector<unsigned char> result(32768u*4);
    for(unsigned i=0;i<32768;++i){auto x=i%width,y=i/width;if(right)x=width-1-x;if(!top)y=height-1-y;
        const auto* bgra=raw+18+(static_cast<std::size_t>(y)*width+x)*4;
        result[i*4]=bgra[2];result[i*4+1]=bgra[1];result[i*4+2]=bgra[0];result[i*4+3]=bgra[3];
    }
    return result;
}
inline std::vector<unsigned char> DecodeCubeRgba(const LightingPackage& package,AssetRole role,unsigned face,unsigned mip){
    Require(static_cast<unsigned>(role)<=10,"Lighting LUT is not a cube");const auto& asset=FindAsset(package,role);
    const auto cube=DecodeCubeTexture(AssetData(package,asset),asset.bytes,asset.offset);Require(face<6 && mip<cube.mips,"Invalid lighting face/mip");
    const auto& level=cube.levels[face*cube.mips+mip];const auto* raw=package.bytes.data()+level.offset;
    std::vector<unsigned char> result(static_cast<std::size_t>(level.width)*level.height*4);
    for(unsigned by=0;by<(level.height+3)/4;++by)for(unsigned bx=0;bx<(level.width+3)/4;++bx){
        const auto* block=raw+static_cast<std::size_t>(by)*level.rowPitch+bx*8;const auto c0=OriginalFog::Half(block),c1=OriginalFog::Half(block+2);const auto selectors=Word(block+4);
        std::array<std::array<unsigned char,4>,4> palette={{OriginalFog::Expand565(c0),OriginalFog::Expand565(c1),{{0,0,0,255}},{{0,0,0,255}}}};
        for(unsigned channel=0;channel<3;++channel){if(c0>c1){palette[2][channel]=static_cast<unsigned char>((2u*palette[0][channel]+palette[1][channel])/3);
                palette[3][channel]=static_cast<unsigned char>((palette[0][channel]+2u*palette[1][channel])/3);}
            else palette[2][channel]=static_cast<unsigned char>((unsigned(palette[0][channel])+palette[1][channel])/2);}
        if(c0<=c1)palette[3][3]=0;
        for(unsigned y=0;y<4 && by*4+y<level.height;++y)for(unsigned x=0;x<4 && bx*4+x<level.width;++x){
            const auto& rgba=palette[(selectors>>(2*(y*4+x)))&3];const auto target=(static_cast<std::size_t>(by*4+y)*level.width+bx*4+x)*4;
            std::copy(rgba.begin(),rgba.end(),result.begin()+target);
        }
    }
    return result;
}
}}
