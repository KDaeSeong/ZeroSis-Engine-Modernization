#include "OriginalWaterPackage.h"
#include <cstdio>
#include <fstream>

namespace Water=ZeroSisPresentation::OriginalWater;
namespace Fog=ZeroSisPresentation::OriginalFog;
namespace Sha=ZeroSisPresentation::OriginalTerrain;
namespace {
unsigned checks=0;
void Check(bool value){++checks;if(!value)throw std::runtime_error("Original water package regression");}
std::vector<unsigned char> Read(const std::string& path){
    std::ifstream stream(path,std::ios::binary|std::ios::ate);Check(stream.good());const auto count=stream.tellg();
    Check(count>=0 && count<=16*1024*1024);std::vector<unsigned char> bytes(static_cast<std::size_t>(count));stream.seekg(0);
    if(!bytes.empty())stream.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(bytes.size()));Check(stream.good());return bytes;
}
std::vector<unsigned char> DecodeTop(const Water::WaterPackage& package,const Water::Asset& asset){
    // Reuse the independently validated existing CPU DDS decoder. Copy only
    // this selected DDS, not another entire terrain/fog/water package.
    Fog::FogPackage temporary;const auto* raw=Water::AssetData(package,asset);temporary.bytes.assign(raw,raw+asset.bytes);
    Fog::Asset ref;ref.role=Fog::AssetRole::Cloud1;ref.bytes=asset.bytes;temporary.assets.push_back(ref);
    return Fog::DecodeTopRgba(temporary,Fog::AssetRole::Cloud1);
}
void Close(double actual,double expected){Check(std::abs(actual-expected)<=1e-12);}
void Band(std::ifstream& stream,const Water::CoastBand& band){
    double height=0,offset=0;unsigned character=0,terrain=0;stream>>height>>offset>>character>>terrain;Check(stream.good());
    Close(band.height,height);Close(band.offset,offset);Check(band.character==character && band.terrainType==terrain);
}
void Actual(const std::string& filename,const std::string& metadata){
    std::ifstream stream(metadata);Check(stream.good());unsigned count=0,blobCount=0;std::size_t bytes=0;std::string sha;
    stream>>count>>blobCount>>bytes>>sha;Check(stream.good() && count==25 && blobCount==24 && bytes==5180388 &&
        sha=="2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc");
    const auto package=Water::DecodePackage(Read(filename),sha);Check(package.assets.size()==count && package.bytes.size()==bytes);
    for(unsigned index=1;index<=count;++index){
        unsigned role=0,blob=0,format=0,width=0,height=0,mips=0;std::size_t offset=0,size=0;std::string name,rawSha;
        stream>>role>>blob>>offset>>size>>format>>width>>height>>mips>>rawSha>>name;Check(stream.good() && role==index);
        const auto& asset=Water::FindAsset(package,static_cast<Water::AssetRole>(role));
        Check(asset.name==name && asset.blobIndex==blob && asset.offset==offset && asset.bytes==size);
        Check(Sha::Sha256Hex(Water::AssetData(package,asset),asset.bytes)==rawSha);
        if(index<=14){
            const auto& texture=asset.texture;Check(static_cast<unsigned>(texture.format)==format && texture.width==width && texture.height==height &&
                texture.mips==mips && texture.levels.size()==mips);
            for(unsigned mip=0;mip<mips;++mip){
                std::size_t at=0,length=0,pitch=0;unsigned x=0,y=0;stream>>at>>length>>pitch>>x>>y;Check(stream.good());
                const auto& level=texture.levels[mip];Check(level.offset==at && level.bytes==length && level.rowPitch==pitch && level.width==x && level.height==y &&
                    level.offset+level.bytes<=asset.offset+asset.bytes);
            }
            std::string decodedSha;stream>>decodedSha;Check(stream.good());const auto rgba=DecodeTop(package,asset);
            Check(rgba.size()==static_cast<std::size_t>(width)*height*4 && Sha::Sha256Hex(rgba.data(),rgba.size())==decodedSha);
        }else Check(asset.texture.format==Water::TextureFormat::None);
    }
    Check(package.assets[15].offset==package.assets[16].offset && package.assets[15].bytes==package.assets[16].bytes);
    Check(package.styles.size()==13 && package.profiles.size()==9);
    for(const auto& style:package.styles){
        std::string name;double high=0,low=0;stream>>name>>high>>low;Check(stream.good() && style.name==name);
        Close(style.highSmoothing,high);Close(style.lowSmoothing,low);Band(stream,style.highBeach);Band(stream,style.lowBeach);Band(stream,style.waterline);
    }
    for(const auto& profile:package.profiles){
        unsigned role=0,points=0;std::string name;stream>>role>>points>>name;Check(stream.good() && points==100 && profile.points.size()==100 &&
            static_cast<unsigned>(profile.role)==role && profile.name==name);
        for(const auto& point:profile.points){double x=0,y=0,z=0;stream>>x>>y>>z;Check(stream.good());Close(point.x,x);Close(point.y,y);Close(point.z,z);}
    }
    Check(package.styles[0].highBeach.height==.2244 && package.styles[11].highBeach.character==6 && package.styles[12].waterline.character==65535);
    bool rejected=false;try{Water::FindAsset(package,static_cast<Water::AssetRole>(26));}catch(const std::invalid_argument&){rejected=true;}Check(rejected);
    Water::Asset bad;bad.offset=package.bytes.size()+1;bad.bytes=1;rejected=false;
    try{Water::AssetData(package,bad);}catch(const std::invalid_argument&){rejected=true;}Check(rejected);
}
unsigned Fixtures(const std::string& directory){
    std::ifstream stream(directory+"/cases.txt");Check(stream.good());unsigned count=0;stream>>count;Check(count>=61 && count<=100);
    for(unsigned index=0;index<count;++index){
        unsigned accepted=0;std::string sha,name,label;stream>>accepted>>sha>>name>>label;Check(stream.good() && accepted<=1);
        bool rejected=false;
        try{const auto parsed=Water::DecodePackage(Read(directory+"/"+name),sha);Check(parsed.assets.size()==25 && parsed.styles.size()==13 && parsed.profiles.size()==9);}
        catch(const std::invalid_argument&){rejected=true;}
        if(rejected!=(accepted==0))std::fprintf(stderr,"Fixture mismatch: %s\n",label.c_str());Check(rejected==(accepted==0));
    }
    return count;
}
}
int main(int argc,char** argv){
    try{Check(argc==4);Actual(argv[1],argv[2]);const auto cases=Fixtures(argv[3]);
        std::printf("PASS_ORIGINAL_WATER_PACKAGE checks=%u fixtures=%u assets=25 textures=14 styles=13 profiles=9 points=900\n",checks,cases);return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"FAIL: %s\n",error.what());return 1;}
}
