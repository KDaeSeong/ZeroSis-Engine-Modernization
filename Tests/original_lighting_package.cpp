#include "OriginalLightingPackage.h"
#include "OriginalLightingBinding.h"
#include <cstdio>
#include <fstream>

namespace L=ZeroSisPresentation::OriginalLighting;
namespace S=ZeroSisPresentation::OriginalTerrain;
namespace {
std::uint64_t checks=0,texels=0;unsigned rejectedApi=0;
void Check(bool value){++checks;if(!value)throw std::runtime_error("Original lighting package regression");}
template<class F>void Reject(F fn){bool rejected=false;try{fn();}catch(const std::invalid_argument&){rejected=true;}Check(rejected);++rejectedApi;}
std::vector<unsigned char> Read(const std::string& path){
    std::ifstream stream(path,std::ios::binary|std::ios::ate);Check(stream.good());const auto size=stream.tellg();Check(size>=0 && size<=3*1024*1024);
    std::vector<unsigned char> raw(static_cast<std::size_t>(size));stream.seekg(0);
    if(!raw.empty())stream.read(reinterpret_cast<char*>(raw.data()),static_cast<std::streamsize>(raw.size()));Check(stream.good());return raw;
}
void Actual(const std::string& filename,const std::string& reference){
    const auto package=L::DecodePackage(Read(filename),L::LightingPackageSha256);Check(package.assets.size()==15 && package.blobCount==9 && package.bytes.size()==730040);
    std::ifstream stream(reference);Check(stream.good());
    for(unsigned role=1;role<=15;++role){
        unsigned index=0,blob=0;std::size_t offset=0,count=0;std::string name,sha;stream>>index>>offset>>count>>blob>>name>>sha;Check(stream.good());
        const auto& asset=L::FindAsset(package,static_cast<L::AssetRole>(role));
        Check(index==role && asset.offset==offset && asset.bytes==count && asset.blobIndex==blob && asset.name==name);
        Check(S::Sha256Hex(L::AssetData(package,asset),asset.bytes)==sha);
        if(role<=10){unsigned width=0,height=0,mips=0,levels=0;stream>>width>>height>>mips>>levels;Check(stream.good());
            Check(asset.cube.width==width && asset.cube.height==height && asset.cube.mips==mips && asset.cube.levels.size()==levels && levels==48);
            for(unsigned i=0;i<levels;++i){unsigned face=0,mip=0,x=0,y=0;std::size_t at=0,bytes=0,pitch=0;std::string decoded;
                stream>>face>>mip>>x>>y>>at>>bytes>>pitch>>decoded;Check(stream.good());const auto& level=asset.cube.levels[i];
                Check(level.face==face && level.mip==mip && level.width==x && level.height==y && level.offset==at && level.bytes==bytes && level.rowPitch==pitch);
                Check(at>=asset.offset+128 && at+bytes<=asset.offset+asset.bytes && i==face*mips+mip);
                const auto rgba=L::DecodeCubeRgba(package,asset.role,face,mip);Check(rgba.size()==static_cast<std::size_t>(x)*y*4);
                Check(S::Sha256Hex(rgba.data(),rgba.size())==decoded);texels+=rgba.size()/4;
            }
        }else{std::size_t size=0;std::string decoded;stream>>size>>decoded;Check(stream.good());
            const auto rgba=L::CandidateTerrainLut32Rgba(package,role-11);Check(rgba.size()==size && size==131072);Check(S::Sha256Hex(rgba.data(),rgba.size())==decoded);texels+=rgba.size()/4;}
    }
    for(unsigned continent=0;continent<5;++continent){Check(static_cast<unsigned>(L::SunlightRole(continent))==1+continent);
        Check(static_cast<unsigned>(L::ShadowlightRole(continent))==6+continent);Check(static_cast<unsigned>(L::TerrainLutRole(continent))==11+continent);}
    Reject([&](){L::SunlightRole(5);});Reject([&](){L::ShadowlightRole(5);});Reject([&](){L::TerrainLutRole(5);});
    Reject([&](){L::FindAsset(package,static_cast<L::AssetRole>(0));});Reject([&](){L::FindAsset(package,static_cast<L::AssetRole>(16));});
    Reject([&](){L::DecodeCubeRgba(package,L::AssetRole::SunlightGeneric,6,0);});Reject([&](){L::DecodeCubeRgba(package,L::AssetRole::SunlightGeneric,0,8);});
    Reject([&](){L::DecodeCubeRgba(package,L::AssetRole::TerrainLutGeneric,0,0);});Reject([&](){L::CandidateTerrainLut32Rgba(package,5);});
    auto malformed=package;malformed.assets[0].offset=malformed.bytes.size();Reject([&](){L::DecodeCubeRgba(malformed,L::AssetRole::SunlightGeneric,0,0);});
    malformed=package;malformed.assets[10].bytes=1;Reject([&](){L::CandidateTerrainLut32Rgba(malformed,0);});
    const auto& asset=package.assets[0];Reject([&](){L::DecodeCubeTexture(L::AssetData(package,asset),asset.bytes,std::numeric_limits<std::size_t>::max());});
}
unsigned Fixtures(const std::string& directory){
    std::ifstream stream(directory+"/cases.txt");Check(stream.good());unsigned count=0;stream>>count;Check(count>=60 && count<=200);
    for(unsigned index=0;index<count;++index){unsigned accepted=0;std::string sha,name,label;stream>>accepted>>sha>>name>>label;Check(stream.good() && accepted<=1);
        bool rejected=false;try{const auto package=L::DecodePackage(Read(directory+"/"+name),sha);Check(package.assets.size()==15);
            if(accepted){for(unsigned role=1;role<=10;++role){const auto& asset=package.assets[role-1];
                    for(const auto& level:asset.cube.levels)Check(!L::DecodeCubeRgba(package,asset.role,level.face,level.mip).empty());}
                for(unsigned c=0;c<5;++c)Check(L::CandidateTerrainLut32Rgba(package,c).size()==131072);
                if(label=="valid_shared"){
                    const auto three=L::DecodeCubeRgba(package,L::AssetRole::SunlightGeneric,0,0);
                    const std::array<unsigned char,16> threeExpected={{0,0,255,255,0,255,0,255,0,127,127,255,0,0,0,0}};
                    Check(std::equal(threeExpected.begin(),threeExpected.end(),three.begin()));
                    const auto four=L::DecodeCubeRgba(package,L::AssetRole::SunlightGeneric,0,1);
                    const std::array<unsigned char,16> fourExpected={{255,0,0,255,0,255,0,255,170,85,0,255,85,170,0,255}};
                    Check(std::equal(fourExpected.begin(),fourExpected.end(),four.begin()));
                }}}
        catch(const std::invalid_argument&){rejected=true;}
        if(rejected!=(accepted==0))std::fprintf(stderr,"Fixture mismatch:%s\n",label.c_str());Check(rejected==(accepted==0));
    }
    return count;
}
}
int main(int argc,char** argv){
    try{Check(argc==4);Actual(argv[1],argv[2]);const auto fixtures=Fixtures(argv[3]);
        std::printf("PASS_ORIGINAL_LIGHTING_PACKAGE checks=%llu fixtures=%u assets=15 blobs=9 source_texels=%llu rejected_api=%u\n",
            static_cast<unsigned long long>(checks),fixtures,static_cast<unsigned long long>(texels),rejectedApi);return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"FAIL:%s\n",error.what());return 1;}
}
