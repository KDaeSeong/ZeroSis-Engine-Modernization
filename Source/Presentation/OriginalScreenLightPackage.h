#pragma once
// Original TerrainShader t9 input. Independent of WaterShader's dynamic Raw
// reflection resource. Preserve the exact selected DDS and its eleven mips.
#include "OriginalTerrainSha256.h"
#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <utility>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalScreenLightAssets {
constexpr const char* PackageSha256="f02165b489bfe80557e1fd0246c0a2423f5494a28f4974d935120ea14528a0e0";
constexpr const char* DdsSha256="6f29e8b9c71a8e7ec4dd2983ac5fd46f45938635ec2bd2d1c113a6f40bc1455f";
constexpr std::size_t PackageBytes=1398304,DdsBytes=1398256,PackageHeaderBytes=48;
struct Level {unsigned level=0,width=0,height=0;std::size_t offset=0,bytes=0,rowPitch=0;};
struct Texture {unsigned width=0,height=0,mips=0;std::vector<Level> levels;};
struct Package {std::vector<unsigned char> bytes;Texture texture;};
inline void Require(bool condition,const char* reason){if(!condition)throw std::invalid_argument(reason);}
inline std::uint32_t Word(const unsigned char* p){return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|
    (std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
inline Package DecodePackage(std::vector<unsigned char> bytes,const std::string& pinnedSha){
    Require(bytes.size()==PackageBytes,"Screen light package exact size differs");
    Require(pinnedSha.size()==64&&std::all_of(pinnedSha.begin(),pinnedSha.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');})&&
        OriginalTerrain::Sha256Hex(bytes.data(),bytes.size())==pinnedSha,"Screen light package SHA differs");
    Require(std::memcmp(bytes.data(),"ZSSCRL01",8)==0&&Word(bytes.data()+8)==1&&Word(bytes.data()+12)==DdsBytes,
        "Screen light package magic/version/extent differs");
    const auto* dds=bytes.data()+PackageHeaderBytes;
    const auto digest=OriginalTerrain::Sha256(dds,DdsBytes);
    Require(std::memcmp(bytes.data()+16,digest.data(),32)==0&&OriginalTerrain::Sha256Hex(dds,DdsBytes)==DdsSha256,
        "Screen light inner original DDS SHA differs");
    Require(std::memcmp(dds,"DDS ",4)==0&&Word(dds+4)==124&&(Word(dds+8)&0x1007)==0x1007&&Word(dds+24)==0&&
        Word(dds+76)==32&&Word(dds+80)==4&&Word(dds+84)==0x35545844&&Word(dds+112)==0,"Screen light bounded BC3 DDS header differs");
    // This retained FTXT tool tag is not a BC0NN dictionary/index-map format.
    // GPU subresource bytes remain the original standard BC3 mip block stream.
    Require(std::memcmp(dds+32,"FTXTTerrain Heightfield",23)==0&&dds[55]==0&&std::memcmp(dds+116,"COLOR",5)==0,
        "Screen light original DDS tool metadata differs");
    Package result;result.texture.width=Word(dds+16);result.texture.height=Word(dds+12);result.texture.mips=Word(dds+28);
    Require(result.texture.width==1024&&result.texture.height==1024&&result.texture.mips==11,"Screen light dimensions/mip count differ");
    std::size_t cursor=PackageHeaderBytes+128;
    for(unsigned mip=0;mip<result.texture.mips;++mip){
        const auto side=(std::max)(1u,result.texture.width>>mip);
        const auto pitch=static_cast<std::size_t>((side+3)/4)*16,count=pitch*((side+3)/4);
        Require(cursor<=bytes.size()&&count<=bytes.size()-cursor,"Truncated screen light mip");
        result.texture.levels.push_back({mip,side,side,cursor,count,pitch});cursor+=count;
    }
    Require(cursor==bytes.size(),"Screen light package trailing data differs");
    result.bytes=std::move(bytes);return result;
}
}}
