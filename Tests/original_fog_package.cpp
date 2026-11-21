#include "OriginalFogPackage.h"
#include <cmath>
#include <cstdio>
#include <fstream>
#include <sstream>

namespace Fog=ZeroSisPresentation::OriginalFog;
namespace Sha=ZeroSisPresentation::OriginalTerrain;
namespace {
unsigned checks=0;
void Check(bool value){++checks;if(!value)throw std::runtime_error("Original fog package regression");}
std::vector<unsigned char> Read(const std::string& path){
    std::ifstream stream(path,std::ios::binary|std::ios::ate);Check(stream.good());
    const auto count=stream.tellg();Check(count>=0 && count<=16*1024*1024);
    std::vector<unsigned char> bytes(static_cast<std::size_t>(count));stream.seekg(0);
    if(!bytes.empty())stream.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(bytes.size()));
    Check(stream.good());return bytes;
}
void Actual(const std::string& path,const std::string& metadata){
    std::ifstream stream(metadata);Check(stream.good());unsigned count=0;std::size_t bytes=0;std::string sha;
    stream>>count>>bytes>>sha;Check(stream.good() && count==9 && bytes==8184971 &&
        sha=="42ae12554e1514dd48a9a5df25f47b4280d22d180dff29d169c602334e879bcc");
    const auto package=Fog::DecodePackage(Read(path),sha);Check(package.assets.size()==count && package.bytes.size()==bytes);
    Check(std::fabs(package.fogColour[0]-146.0f/255.0f)<1e-7f && std::fabs(package.fogColour[1]-182.0f/255.0f)<1e-7f &&
        std::fabs(package.fogColour[2]-243.0f/255.0f)<1e-7f);
    for(unsigned index=1;index<=count;++index){
        unsigned role=0,format=0,width=0,height=0,mips=0;std::size_t offset=0,size=0;std::string rawSha,name;
        stream>>role>>offset>>size>>format>>width>>height>>mips>>rawSha>>name;Check(stream.good() && role==index);
        const auto& asset=Fog::FindAsset(package,static_cast<Fog::AssetRole>(role));
        Check(asset.name==name && asset.offset==offset && asset.bytes==size);
        Check(Sha::Sha256Hex(Fog::AssetData(package,asset),asset.bytes)==rawSha);
        if(index<=6){
            const auto& texture=asset.texture;Check(static_cast<unsigned>(texture.format)==format && texture.width==width &&
                texture.height==height && texture.mips==mips && texture.levels.size()==mips);
            for(unsigned level=0;level<mips;++level){
                std::size_t levelOffset=0,levelBytes=0,pitch=0;unsigned levelWidth=0,levelHeight=0;
                stream>>levelOffset>>levelBytes>>pitch>>levelWidth>>levelHeight;Check(stream.good());
                const auto& parsed=texture.levels[level];Check(parsed.offset==levelOffset && parsed.bytes==levelBytes && parsed.rowPitch==pitch &&
                    parsed.width==levelWidth && parsed.height==levelHeight && parsed.offset+parsed.bytes<=offset+size);
            }
            std::string decodedSha;stream>>decodedSha;Check(stream.good());const auto decoded=Fog::DecodeTopRgba(package,asset.role);
            Check(decoded.size()==static_cast<std::size_t>(width)*height*4 && Sha::Sha256Hex(decoded.data(),decoded.size())==decodedSha);
        }else Check(asset.texture.format==Fog::TextureFormat::None);
    }
    std::string lutSha;stream>>lutSha;Check(stream.good());const auto lut=Fog::CandidateFowLut32Rgba(package);
    Check(lut.size()==32768u*4 && Sha::Sha256Hex(lut.data(),lut.size())==lutSha);
    Check(lut[0]==1 && lut[1]==1 && lut[2]==1 && lut[3]==255 && lut[lut.size()-4]==125 && lut[lut.size()-3]==125 && lut[lut.size()-2]==125);
    bool rejected=false;try{Fog::DecodeTopRgba(package,Fog::AssetRole::FogColour);}catch(const std::invalid_argument&){rejected=true;}Check(rejected);
    rejected=false;try{Fog::FindAsset(package,static_cast<Fog::AssetRole>(0));}catch(const std::invalid_argument&){rejected=true;}Check(rejected);
    rejected=false;try{Fog::FindAsset(package,static_cast<Fog::AssetRole>(10));}catch(const std::invalid_argument&){rejected=true;}Check(rejected);
    Fog::Asset bad;bad.offset=package.bytes.size()+1;bad.bytes=1;
    rejected=false;try{Fog::AssetData(package,bad);}catch(const std::invalid_argument&){rejected=true;}Check(rejected);
}
unsigned Fixtures(const std::string& directory){
    std::ifstream stream(directory+"/cases.txt");Check(stream.good());unsigned count=0;stream>>count;Check(count>=42 && count<100);
    for(unsigned i=0;i<count;++i){
        unsigned accepted=0,identity=0;std::string sha,name;stream>>accepted>>identity>>sha>>name;Check(stream.good() && accepted<=1 && identity<=1);
        bool rejected=false;
        try{
            const auto package=Fog::DecodePackage(Read(directory+"/"+name),sha);Check(package.assets.size()==9);
            if(identity){
                const auto lut=Fog::CandidateFowLut32Rgba(package);Check(lut.size()==32768u*4);
                for(unsigned pixel=0;pixel<32768;++pixel){
                    Check(lut[pixel*4]==3+8*(pixel%32) && lut[pixel*4+1]==3+8*((pixel/32)%32) &&
                        lut[pixel*4+2]==3+8*(pixel/1024) && lut[pixel*4+3]==255);
                }
            }
        }catch(const std::invalid_argument&){rejected=true;}
        Check(rejected==(accepted==0));
    }
    return count;
}
void Put(std::vector<unsigned char>& data,std::size_t offset,std::uint32_t value){
    for(unsigned i=0;i<4;++i)data[offset+i]=static_cast<unsigned char>(value>>(i*8));
}
std::vector<unsigned char> BlockDds(bool bc3,unsigned width,unsigned height,const std::vector<unsigned char>& block){
    std::vector<unsigned char> result(128);Put(result,0,0x20534444);Put(result,4,124);Put(result,8,0x1007);
    Put(result,12,height);Put(result,16,width);Put(result,28,1);Put(result,76,32);Put(result,80,4);
    Put(result,84,bc3?0x35545844:0x31545844);Put(result,108,0x1000);result.insert(result.end(),block.begin(),block.end());return result;
}
std::vector<unsigned char> DecodeBlock(std::vector<unsigned char> dds,bool bc3){
    Fog::FogPackage package;package.bytes=std::move(dds);package.assets.resize(2);const auto role=bc3?Fog::AssetRole::Cloud1:Fog::AssetRole::Cloud2;
    auto& asset=package.assets[bc3?0:1];asset.role=role;asset.bytes=package.bytes.size();return Fog::DecodeTopRgba(package,role);
}
void GoldenBlocks(){
    const std::vector<unsigned char> bc1={0x00,0xf8,0xe0,0x07,0xe4,0xe4,0xe4,0xe4};
    const auto rgba=DecodeBlock(BlockDds(false,4,4,bc1),false);
    const unsigned char expected[]={255,0,0,255,0,255,0,255,170,85,0,255,85,170,0,255};
    for(unsigned row=0;row<4;++row)for(unsigned i=0;i<16;++i)Check(rgba[row*16+i]==expected[i]);
    const std::vector<unsigned char> transparent={0,0,0xff,0xff,0xe4,0xe4,0xe4,0xe4};
    const auto small=DecodeBlock(BlockDds(false,3,2,transparent),false);Check(small.size()==24);
    const unsigned char half[]={0,0,0,255,255,255,255,255,127,127,127,255};
    for(unsigned row=0;row<2;++row)for(unsigned i=0;i<12;++i)Check(small[row*12+i]==half[i]);
    const auto full=DecodeBlock(BlockDds(false,4,4,transparent),false);Check(full[12]==0 && full[13]==0 && full[14]==0 && full[15]==0);
    for(unsigned mode=0;mode<2;++mode){
        std::vector<unsigned char> bc3(16);bc3[0]=mode?0:255;bc3[1]=mode?255:0;std::uint64_t bits=0;
        for(unsigned i=0;i<16;++i)bits|=static_cast<std::uint64_t>(i%8)<<(i*3);
        for(unsigned i=0;i<6;++i)bc3[i+2]=static_cast<unsigned char>(bits>>(i*8));
        // BC3 uses four-colour mode even when c0 < c1.
        bc3[8]=0;bc3[9]=0;bc3[10]=255;bc3[11]=255;bc3[12]=0xe4;bc3[13]=0xe4;bc3[14]=0xe4;bc3[15]=0xe4;
        const auto decoded=DecodeBlock(BlockDds(true,4,4,bc3),true);
        const unsigned char aHigh[]={255,0,218,182,145,109,72,36},aLow[]={0,255,51,102,153,204,0,255};
        const unsigned char colours[]={0,255,85,170};
        for(unsigned pixel=0;pixel<16;++pixel){
            Check(decoded[pixel*4]==colours[pixel%4] && decoded[pixel*4+1]==colours[pixel%4] && decoded[pixel*4+2]==colours[pixel%4]);
            Check(decoded[pixel*4+3]==(mode?aLow[pixel%8]:aHigh[pixel%8]));
        }
    }
}
}
int main(int argc,char** argv){
    try{Check(argc==4);Actual(argv[1],argv[2]);const auto fixtures=Fixtures(argv[3]);GoldenBlocks();
        std::printf("PASS_ORIGINAL_FOG_PACKAGE checks=%u fixtures=%u real_assets=9 textures=6 candidate_lut=32\n",checks,fixtures);return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"FAIL: %s\n",error.what());return 1;}
}
