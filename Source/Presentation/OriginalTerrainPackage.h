#pragma once
#include "OriginalTerrainSha256.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalTerrain {
constexpr std::uint32_t NullTexture=0xffffffffu,DeclaredMissingTexture=0xfffffffeu;
struct PackageRow {
    unsigned row=0,continent=0,legacyId=0;float scale=0;unsigned projection=0;
    unsigned diffuse=NullTexture,height=NullTexture,specular=NullTexture;
};
struct PackageTexture {
    std::string name;std::size_t offset=0,bytes=0;
    unsigned width=0,height=0,mips=0;
};
struct TerrainPackage {
    std::vector<unsigned char> bytes;
    std::vector<PackageRow> rows;std::vector<PackageTexture> textures;
    std::size_t libraryOffset=0,libraryBytes=0;
};
inline std::uint32_t PackageWord(const unsigned char* p){return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|
    (std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
inline void PackageRequire(bool value,const char* message){if(!value)throw std::invalid_argument(message);}
inline TerrainPackage DecodePackage(std::vector<unsigned char> bytes,const std::string& expectedSha){
    PackageRequire(bytes.size()>=24 && bytes.size()<=128u*1024u*1024u,"Original terrain package exceeds its bound");
    PackageRequire(expectedSha.size()==64 && Sha256Hex(bytes.data(),bytes.size())==expectedSha,"Original terrain outer SHA256 differs");
    TerrainPackage result;result.bytes=std::move(bytes);const auto& raw=result.bytes;std::size_t cursor=0;
    const auto take=[&](std::size_t count){PackageRequire(count<=raw.size()-cursor,"Truncated original terrain package");
        const auto* p=raw.data()+cursor;cursor+=count;return p;};
    const auto u32=[&](){return PackageWord(take(4));};
    PackageRequire(std::memcmp(take(8),"ZSTERR02",8)==0 && u32()==2,"Unknown original terrain package version");
    const auto rowCount=u32(),textureCount=u32(),libraryBytes=u32();
    PackageRequire(rowCount>0 && rowCount<=64 && textureCount>0 && textureCount<=256 &&
        libraryBytes>=20 && libraryBytes<=32u*1024u*1024u,"Invalid original terrain package counts");
    std::set<std::pair<unsigned,unsigned>> identities;unsigned expanded=0;
    for(unsigned i=0;i<rowCount;++i){
        PackageRow row;row.row=u32();row.continent=u32();row.legacyId=u32();
        const auto scale=u32();std::memcpy(&row.scale,&scale,sizeof(scale));
        row.projection=u32();row.diffuse=u32();row.height=u32();row.specular=u32();
        PackageRequire(row.row==i && row.continent<=4 && row.legacyId<=255 && std::isfinite(row.scale) && row.scale>0 && row.scale<=16 &&
            row.projection<=1 && identities.emplace(row.continent,row.legacyId).second,"Invalid ordered TerrainDef row");
        const auto valid=[&](unsigned texture){return texture<textureCount || texture==NullTexture || texture==DeclaredMissingTexture;};
        PackageRequire(row.diffuse<textureCount && valid(row.height) && valid(row.specular),"Invalid original terrain texture reference");
        PackageRequire(row.height!=DeclaredMissingTexture || (row.row==8 && row.continent==0),"Unexpected missing terrain height declaration");
        PackageRequire(row.specular!=DeclaredMissingTexture,"Unexpected missing specular texture declaration");
        expanded+=row.projection?3u:1u;PackageRequire(expanded<=64,"Expanded original terrain materials exceed64");
        result.rows.push_back(row);
    }
    std::string previous;
    for(unsigned i=0;i<textureCount;++i){
        const auto nameBytes=u32(),count=u32();const auto* digest=take(32);
        PackageRequire(nameBytes>4 && nameBytes<=128 && count>=128 && count<=32u*1024u*1024u,"Invalid original DDS record bounds");
        const auto* text=take(nameBytes);std::string name(reinterpret_cast<const char*>(text),nameBytes);
        PackageRequire(((name[0]>='a'&&name[0]<='z')||(name[0]>='0'&&name[0]<='9')) &&
            std::all_of(name.begin(),name.end(),[](char c){return (c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='_'||c=='.'||c=='-'||c==' ';}) &&
            name.substr(name.size()-4)==".dds" && (i==0 || previous<name),"Unsafe or unordered original DDS name");
        previous=name;const auto offset=cursor;const auto* dds=take(count);const auto hash=Sha256(dds,count);
        PackageRequire(std::memcmp(hash.data(),digest,32)==0,"Original DDS SHA256 differs");
        PackageRequire(std::memcmp(dds,"DDS ",4)==0 && PackageWord(dds+4)==124 && (PackageWord(dds+8)&0x1007)==0x1007 &&
            PackageWord(dds+24)==0 && PackageWord(dds+76)==32 &&
            PackageWord(dds+80)==4 && PackageWord(dds+84)==0x35545844 && PackageWord(dds+112)==0,"Original terrain DDS must be bounded BC3");
        const auto width=PackageWord(dds+16),height=PackageWord(dds+12),mips=std::max(1u,PackageWord(dds+28));
        PackageRequire(width && height && width<=4096 && height<=4096 && mips<=13,"Original DDS dimensions exceed bound");
        unsigned maximumMips=0;for(auto dimension=std::max(width,height);dimension;dimension>>=1)++maximumMips;
        PackageRequire(mips<=maximumMips,"Original DDS mip count exceeds its dimensions");
        std::size_t expected=128;
        for(unsigned mip=0;mip<mips;++mip)expected+=static_cast<std::size_t>((std::max(1u,width>>mip)+3)/4)*((std::max(1u,height>>mip)+3)/4)*16;
        PackageRequire(expected==count,"Original DDS mip chain size differs");
        result.textures.push_back({name,offset,count,width,height,mips});
    }
    const auto* digest=take(32);result.libraryOffset=cursor;result.libraryBytes=libraryBytes;
    const auto* library=take(libraryBytes);const auto hash=Sha256(library,libraryBytes);
    PackageRequire(std::memcmp(hash.data(),digest,32)==0 && PackageWord(library)==20 && cursor==raw.size(),"Original piece library SHA/version or package extent differs");
    return result;
}
}}
