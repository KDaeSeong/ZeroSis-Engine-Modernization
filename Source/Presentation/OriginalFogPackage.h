#pragma once
#include "OriginalTerrainSha256.h"
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalFog {
enum class AssetRole:std::uint32_t {Cloud1=1,Cloud2,Cloud3,FlowField,FogDiffuse,DistanceRamp,FowColourKey,FogColour,FluidSettings};
enum class TextureFormat {None,Bc1,Bc3,Bgra8};
struct TextureLevel {std::size_t offset=0,bytes=0,rowPitch=0;unsigned width=0,height=0;};
struct Texture {TextureFormat format=TextureFormat::None;unsigned width=0,height=0,mips=0;std::vector<TextureLevel> levels;};
struct Asset {AssetRole role=AssetRole::Cloud1;std::string name;std::size_t offset=0,bytes=0;Texture texture;};
struct FogPackage {std::vector<unsigned char> bytes;std::vector<Asset> assets;std::array<float,3> fogColour={{0,0,0}};};
inline void Require(bool value,const char* message){if(!value)throw std::invalid_argument(message);}
inline std::uint32_t Word(const unsigned char* p){return std::uint32_t(p[0])|(std::uint32_t(p[1])<<8)|
    (std::uint32_t(p[2])<<16)|(std::uint32_t(p[3])<<24);}
inline unsigned Half(const unsigned char* p){return unsigned(p[0])|(unsigned(p[1])<<8);}
inline const char* RoleName(unsigned role){
    static const char* const names[]={"fogcloudtile_dif_01.dds","fogcloudtile_dif_02.dds","fogcloudtile_dif_03.dds",
        "flowfield.dds","fx_fog_dif.dds","fogramp.dds","terrainfow_generic_colorkey.tga","fogcolor.csv","fluidfowsettings.xml"};
    Require(role>=1 && role<=9,"Invalid fog asset role");return names[role-1];
}
inline Texture DecodeTexture(const unsigned char* raw,std::size_t size,std::size_t packageOffset){
    Require(size>=128 && size<=5u*1024u*1024u && std::memcmp(raw,"DDS ",4)==0 && Word(raw+4)==124 &&
        (Word(raw+8)&0x1007)==0x1007 && Word(raw+24)==0 && Word(raw+76)==32 && Word(raw+112)==0,"Invalid bounded fog DDS header");
    Texture result;result.width=Word(raw+16);result.height=Word(raw+12);result.mips=std::max(1u,Word(raw+28));
    Require(result.width && result.height && result.width<=2048 && result.height<=2048,"Fog DDS dimensions exceed bound");
    unsigned maximumMips=0;for(auto dimension=std::max(result.width,result.height);dimension;dimension>>=1)++maximumMips;
    Require(result.mips<=maximumMips,"Fog DDS mip count exceeds its dimensions");
    unsigned block=0;
    if(Word(raw+80)==4 && (Word(raw+84)==0x31545844 || Word(raw+84)==0x35545844)){
        result.format=Word(raw+84)==0x31545844?TextureFormat::Bc1:TextureFormat::Bc3;block=result.format==TextureFormat::Bc1?8u:16u;
    }else{
        Require(Word(raw+80)==0x41 && Word(raw+84)==0 && Word(raw+88)==32 && Word(raw+92)==0xff0000 &&
            Word(raw+96)==0xff00 && Word(raw+100)==0xff && Word(raw+104)==0xff000000,"Unsupported fog DDS channel masks");
        result.format=TextureFormat::Bgra8;
    }
    std::size_t cursor=128;
    for(unsigned mip=0;mip<result.mips;++mip){
        const auto width=std::max(1u,result.width>>mip),height=std::max(1u,result.height>>mip);
        const std::size_t pitch=block?static_cast<std::size_t>((width+3)/4)*block:static_cast<std::size_t>(width)*4;
        const std::size_t count=pitch*(block?(height+3)/4:height);
        Require(cursor<=size && count<=size-cursor,"Truncated fog DDS mip payload");
        Require(packageOffset<=16u*1024u*1024u && cursor<=16u*1024u*1024u-packageOffset,"Fog DDS package offset exceeds bound");
        result.levels.push_back({packageOffset+cursor,count,pitch,width,height});cursor+=count;
    }
    Require(cursor==size,"Fog DDS mip chain extent differs");return result;
}
inline void ValidateTga(const unsigned char* raw,std::size_t count){
    Require(count>=18 && count<=300000,"Unbounded FOW colour TGA");
    Require(raw[0]==0 && raw[1]==0 && raw[2]==2 && Half(raw+3)==0 && Half(raw+5)==0 && raw[7]==0 &&
        Half(raw+8)==0 && Half(raw+10)==0 && raw[16]==32 && (raw[17]==8 || raw[17]==24 || raw[17]==40 || raw[17]==56),
        "Unsupported FOW colour TGA encoding/origin");
    const auto width=Half(raw+12),height=Half(raw+14);const auto pixels=static_cast<std::size_t>(width)*height;
    Require(width && height && width<=4096 && height<=2048 && pixels>=32768 && pixels<=65536,"Unbounded FOW colour TGA dimensions");
    const auto end=18+pixels*4;
    Require(count==end || (count==end+26 && std::all_of(raw+end,raw+end+8,[](unsigned char c){return c==0;}) &&
        std::memcmp(raw+end+8,"TRUEVISION-XFILE.\0",18)==0),"FOW colour TGA extent/footer differs");
}
inline std::array<float,3> DecodeFogColour(const unsigned char* raw,std::size_t count){
    Require(count && count<=128,"Unbounded fog colour CSV");std::size_t cursor=0;std::array<float,3> result={{0,0,0}};
    const auto spaces=[&](){while(cursor<count && (raw[cursor]==' ' || raw[cursor]=='\t' || raw[cursor]=='\r' || raw[cursor]=='\n'))++cursor;};
    for(unsigned channel=0;channel<3;++channel){
        spaces();unsigned value=0,digits=0;
        while(cursor<count && raw[cursor]>='0' && raw[cursor]<='9'){
            Require(++digits<=3,"Fog colour CSV component exceeds digit bound");value=value*10+unsigned(raw[cursor++]-'0');
        }
        Require(digits && value<=255,"Fog colour CSV component exceeds byte range");result[channel]=static_cast<float>(value)/255.0f;
        spaces();if(channel<2){Require(cursor<count && raw[cursor]==',',"Fog colour CSV delimiter differs");++cursor;}
    }
    spaces();Require(cursor==count,"Fog colour CSV trailing data");return result;
}
inline FogPackage DecodePackage(std::vector<unsigned char> bytes,const std::string& expectedSha){
    Require(bytes.size()>=16 && bytes.size()<=16u*1024u*1024u,"Fog package exceeds its bound");
    Require(expectedSha.size()==64 && OriginalTerrain::Sha256Hex(bytes.data(),bytes.size())==expectedSha,"Fog package outer SHA256 differs");
    FogPackage result;result.bytes=std::move(bytes);const auto& raw=result.bytes;std::size_t cursor=0;
    const auto take=[&](std::size_t count){Require(count<=raw.size()-cursor,"Truncated fog package");const auto* p=raw.data()+cursor;cursor+=count;return p;};
    const auto u32=[&](){return Word(take(4));};
    Require(std::memcmp(take(8),"ZSFOG001",8)==0 && u32()==1 && u32()==9,"Unknown fog package format/count");
    for(unsigned index=1;index<=9;++index){
        const auto role=u32(),nameBytes=u32(),size=u32();const auto* digest=take(32);
        Require(role==index && nameBytes && nameBytes<=64 && size && size<=5u*1024u*1024u,"Invalid ordered fog record bounds");
        const auto* text=take(nameBytes);const std::string name(reinterpret_cast<const char*>(text),nameBytes);
        Require(name==RoleName(role),"Noncanonical fog asset name");const auto offset=cursor;const auto* data=take(size);
        const auto hash=OriginalTerrain::Sha256(data,size);Require(std::memcmp(hash.data(),digest,32)==0,"Fog asset SHA256 differs");
        Asset asset;asset.role=static_cast<AssetRole>(role);asset.name=name;asset.offset=offset;asset.bytes=size;
        if(role<=6){
            asset.texture=DecodeTexture(data,size,offset);
            const auto expected=(role==2)?TextureFormat::Bc1:(role==4 || role==6)?TextureFormat::Bgra8:TextureFormat::Bc3;
            Require(asset.texture.format==expected,"Fog role DDS codec differs");
        }else if(role==7)ValidateTga(data,size);
        else if(role==8)result.fogColour=DecodeFogColour(data,size);
        else{
            Require(size<=4096 && size>=5 && std::memcmp(data,"<?xml",5)==0,"Invalid bounded FluidFOW XML");
            const std::string xml(reinterpret_cast<const char*>(data),size);
            Require(xml.find("<FluidFOWSettings>")!=std::string::npos && xml.find("</FluidFOWSettings>")!=std::string::npos,"Invalid FluidFOW settings root");
        }
        result.assets.push_back(std::move(asset));
    }
    Require(cursor==raw.size(),"Fog package has trailing bytes");return result;
}
inline const Asset& FindAsset(const FogPackage& package,AssetRole role){
    const auto index=static_cast<unsigned>(role);Require(index>=1 && index<=package.assets.size(),"Missing fog asset role");
    const auto& asset=package.assets[index-1];Require(asset.role==role,"Fog asset role differs");return asset;
}
inline const unsigned char* AssetData(const FogPackage& package,const Asset& asset){
    Require(asset.offset<=package.bytes.size() && asset.bytes<=package.bytes.size()-asset.offset,"Fog asset range outside package");
    return package.bytes.data()+asset.offset;
}
inline std::array<unsigned char,4> Expand565(unsigned value){
    const auto r=(value>>11)&31,g=(value>>5)&63,b=value&31;
    return {{static_cast<unsigned char>((r<<3)|(r>>2)),static_cast<unsigned char>((g<<2)|(g>>4)),static_cast<unsigned char>((b<<3)|(b>>2)),255}};
}
inline std::vector<unsigned char> DecodeTopRgba(const FogPackage& package,AssetRole role){
    const auto& asset=FindAsset(package,role);Require(static_cast<unsigned>(role)<=6,"Fog role is not a DDS texture");
    const auto* data=AssetData(package,asset);const auto texture=DecodeTexture(data,asset.bytes,asset.offset);
    const auto width=texture.width,height=texture.height;std::vector<unsigned char> result(static_cast<std::size_t>(width)*height*4);
    if(texture.format==TextureFormat::Bgra8){
        for(std::size_t i=0;i<static_cast<std::size_t>(width)*height;++i){
            result[i*4]=data[128+i*4+2];result[i*4+1]=data[128+i*4+1];result[i*4+2]=data[128+i*4];result[i*4+3]=data[128+i*4+3];
        }
        return result;
    }
    const bool bc3=texture.format==TextureFormat::Bc3;const unsigned blockBytes=bc3?16u:8u;
    for(unsigned by=0;by<(height+3)/4;++by)for(unsigned bx=0;bx<(width+3)/4;++bx){
        const auto* block=data+128+(static_cast<std::size_t>(by)*((width+3)/4)+bx)*blockBytes;
        const auto* colour=block+(bc3?8:0);const auto c0=Half(colour),c1=Half(colour+2);const auto selectors=Word(colour+4);
        std::array<std::array<unsigned char,4>,4> palette={{Expand565(c0),Expand565(c1),{{0,0,0,255}},{{0,0,0,255}}}};
        for(unsigned channel=0;channel<3;++channel){
            if(bc3 || c0>c1){
                palette[2][channel]=static_cast<unsigned char>((2u*palette[0][channel]+palette[1][channel])/3);
                palette[3][channel]=static_cast<unsigned char>((palette[0][channel]+2u*palette[1][channel])/3);
            }else palette[2][channel]=static_cast<unsigned char>((unsigned(palette[0][channel])+palette[1][channel])/2);
        }
        if(!bc3 && c0<=c1)palette[3][3]=0;
        std::array<unsigned char,8> alpha={{255,255,255,255,255,255,255,255}};std::uint64_t alphaSelectors=0;
        if(bc3){
            alpha[0]=block[0];alpha[1]=block[1];
            if(alpha[0]>alpha[1])for(unsigned k=1;k<=6;++k)alpha[k+1]=static_cast<unsigned char>(((7-k)*unsigned(alpha[0])+k*unsigned(alpha[1]))/7);
            else{for(unsigned k=1;k<=4;++k)alpha[k+1]=static_cast<unsigned char>(((5-k)*unsigned(alpha[0])+k*unsigned(alpha[1]))/5);alpha[6]=0;alpha[7]=255;}
            for(unsigned k=0;k<6;++k)alphaSelectors|=static_cast<std::uint64_t>(block[k+2])<<(8*k);
        }
        for(unsigned y=0;y<4 && by*4+y<height;++y)for(unsigned x=0;x<4 && bx*4+x<width;++x){
            const auto pixel=y*4+x;auto rgba=palette[(selectors>>(pixel*2))&3];if(bc3)rgba[3]=alpha[(alphaSelectors>>(pixel*3))&7];
            const auto target=(static_cast<std::size_t>(by*4+y)*width+bx*4+x)*4;
            std::copy(rgba.begin(),rgba.end(),result.begin()+target);
        }
    }
    return result;
}
// Asset-backed candidate: standard TGA origin, first 32^3 logical pixels,
// R/x fastest. Retail loader and sampler equivalence remain unverified.
inline std::vector<unsigned char> CandidateFowLut32Rgba(const FogPackage& package){
    const auto& asset=FindAsset(package,AssetRole::FowColourKey);const auto* raw=AssetData(package,asset);ValidateTga(raw,asset.bytes);
    const auto width=Half(raw+12),height=Half(raw+14);const bool top=(raw[17]&32)!=0,right=(raw[17]&16)!=0;
    std::vector<unsigned char> result(32768u*4);
    for(unsigned i=0;i<32768;++i){
        auto x=i%width,y=i/width;if(right)x=width-1-x;if(!top)y=height-1-y;
        const auto* bgra=raw+18+(static_cast<std::size_t>(y)*width+x)*4;
        result[i*4]=bgra[2];result[i*4+1]=bgra[1];result[i*4+2]=bgra[0];result[i*4+3]=bgra[3];
    }
    return result;
}
}}
