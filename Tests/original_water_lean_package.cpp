#include "OriginalWaterLeanPackage.h"
#include <cstdio>
#include <fstream>
#include <limits>

namespace Lean=ZeroSisPresentation::OriginalWaterLean;
namespace Sha=ZeroSisPresentation::OriginalTerrain;
namespace {
std::uint64_t checks=0;unsigned rejectedInputs=0;
void Check(bool value){++checks;if(!value)throw std::runtime_error("Water LEAN package regression");}
void Near(double a,double b,double tolerance=1e-13){Check(std::isfinite(a)&&std::isfinite(b)&&std::abs(a-b)<=tolerance);}
template<class F>void Reject(F fn){bool rejected=false;try{fn();}catch(const std::invalid_argument&){rejected=true;}Check(rejected);++rejectedInputs;}
std::vector<unsigned char> Read(const std::string& path){
    std::ifstream stream(path,std::ios::binary|std::ios::ate);Check(stream.good());const auto size=stream.tellg();Check(size>=0&&size<=8*1024*1024);
    std::vector<unsigned char> result(static_cast<std::size_t>(size));stream.seekg(0);
    if(!result.empty())stream.read(reinterpret_cast<char*>(result.data()),static_cast<std::streamsize>(result.size()));Check(stream.good());return result;
}
void AppendDouble(std::vector<unsigned char>& target,double value){
    static_assert(sizeof(double)==8 && std::numeric_limits<double>::is_iec559,"Reference requires IEEE754 binary64");
    std::uint64_t bits=0;std::memcpy(&bits,&value,8);for(unsigned i=0;i<8;++i)target.push_back(static_cast<unsigned char>(bits>>(8*i)));
}
void AppendMoments(std::vector<unsigned char>& target,const Lean::Moments& value){
    AppendDouble(target,value.meanX);AppendDouble(target,value.meanY);AppendDouble(target,value.secondXX);AppendDouble(target,value.secondYY);AppendDouble(target,value.secondXY);
}
void Actual(const std::string& filename,const std::string& reference){
    std::ifstream stream(reference);Check(stream.good());std::size_t count=0;std::string sha;stream>>count>>sha;
    Check(stream.good()&&count==3495363&&sha=="69c6780dbeb5f8605d8231cef944d0ec9392109b6ccc81a9d3b76ae83cfd0ef7");
    const auto package=Lean::DecodePackage(Read(filename),sha);const auto& asset=Lean::FindAsset(package,Lean::AssetRole::WaterBumps);
    std::size_t offset=0,size=0;unsigned width=0,height=0,mips=0,scaleBits=0,flag=0,pad0=0,pad1=0,pad2=0;std::string name,rawSha;
    stream>>offset>>size>>width>>height>>mips>>scaleBits>>flag>>pad0>>pad1>>pad2>>name>>rawSha;Check(stream.good());
    const auto& texture=asset.texture;unsigned actualBits=0;std::memcpy(&actualBits,&texture.outputScale,4);
    Check(asset.offset==offset&&asset.bytes==size&&asset.name==name&&texture.width==width&&texture.height==height&&texture.mips==mips&&actualBits==scaleBits&&
        texture.flagAt32==flag&&texture.opaquePadding[0]==pad0&&texture.opaquePadding[1]==pad1&&texture.opaquePadding[2]==pad2);
    Check(width==512&&height==512&&mips==10&&size==3495286&&package.assets.size()==1);
    Check(Sha::Sha256Hex(Lean::AssetData(package,asset),asset.bytes)==rawSha);
    for(unsigned level=0;level<mips;++level){
        for(unsigned plane=0;plane<2;++plane){
            std::size_t at=0,bytes=0,pitch=0,slice=0;unsigned x=0,y=0;std::string hash;
            stream>>at>>bytes>>pitch>>slice>>x>>y>>hash;Check(stream.good());const auto& descriptor=texture.planes[plane];const auto& mip=descriptor.levels[level];
            Check(descriptor.channels==(plane?1u:4u)&&descriptor.format==(plane?Lean::TextureFormat::R16Unorm:Lean::TextureFormat::Rgba16Unorm));
            Check(mip.offset==at&&mip.bytes==bytes&&mip.rowPitch==pitch&&mip.slicePitch==slice&&mip.width==x&&mip.height==y&&
                at>=asset.offset&&at+bytes<=asset.offset+asset.bytes);
            Check(Sha::Sha256Hex(package.bytes.data()+at,bytes)==hash);
        }
        std::string norm0,norm1,moments,mirror;stream>>norm0>>norm1>>moments>>mirror;Check(stream.good());
        const auto& mip=texture.planes[0].levels[level];std::vector<unsigned char> n0,n1,m0,m1;
        const auto texels=static_cast<std::size_t>(mip.width)*mip.height;n0.reserve(texels*32);n1.reserve(texels*8);m0.reserve(texels*40);m1.reserve(texels*40);
        for(unsigned y=0;y<mip.height;++y)for(unsigned x=0;x<mip.width;++x){
            const auto raw=Lean::ReadTexelUnorm(package,Lean::AssetRole::WaterBumps,level,x,y);
            for(const auto value:raw.rgba){Check(value>=0&&value<=1);AppendDouble(n0,value);}Check(raw.crossR>=0&&raw.crossR<=1);AppendDouble(n1,raw.crossR);
            AppendMoments(m0,Lean::DecodeMoments(raw,false,static_cast<double>(texture.outputScale)));
            AppendMoments(m1,Lean::DecodeMoments(raw,true,static_cast<double>(texture.outputScale)));
        }
        Check(Sha::Sha256Hex(n0.data(),n0.size())==norm0&&Sha::Sha256Hex(n1.data(),n1.size())==norm1);
        Check(Sha::Sha256Hex(m0.data(),m0.size())==moments&&Sha::Sha256Hex(m1.data(),m1.size())==mirror);
    }
    Reject([&](){Lean::ReadTexelUnorm(package,Lean::AssetRole::WaterBumps,10,0,0);});
    Reject([&](){Lean::ReadTexelUnorm(package,Lean::AssetRole::WaterBumps,0,512,0);});
    Reject([&](){Lean::ReadTexelUnorm(package,Lean::AssetRole::WaterBumps,0,0,512);});
    Reject([&](){Lean::FindAsset(package,Lean::AssetRole::RiverRough);});Reject([&](){Lean::FindAsset(package,Lean::AssetRole::RiverSmooth);});
    auto malformed=package;malformed.assets[0].texture.planes[0].levels[0].offset=package.bytes.size()-1;
    Reject([&](){Lean::ReadTexelUnorm(malformed,Lean::AssetRole::WaterBumps,0,0,0);});
    malformed=package;malformed.assets[0].texture.planes[0].levels[0].rowPitch=std::numeric_limits<std::size_t>::max();
    Reject([&](){Lean::ReadTexelUnorm(malformed,Lean::AssetRole::WaterBumps,0,0,0);});
}
unsigned Fixtures(const std::string& directory){
    std::ifstream stream(directory+"/cases.txt");Check(stream.good());unsigned count=0;stream>>count;Check(count>=48&&count<=100);
    for(unsigned index=0;index<count;++index){unsigned accepted=0;std::string sha,name,label;stream>>accepted>>sha>>name>>label;Check(stream.good()&&accepted<=1);
        bool rejected=false;try{const auto parsed=Lean::DecodePackage(Read(directory+"/"+name),sha);Check(parsed.assets.size()==1);}
        catch(const std::invalid_argument&){rejected=true;}
        if(rejected!=(accepted==0))std::fprintf(stderr,"Fixture mismatch:%s\n",label.c_str());Check(rejected==(accepted==0));
    }
    return count;
}
void GoldenMoments(){
    Lean::EncodedTexel raw;raw.rgba={{0,1,0.5,0.25}};raw.crossR=0.25;
    const auto signedValue=Lean::DecodeMoments(raw);Near(signedValue.meanX,-1);Near(signedValue.meanY,1);Near(signedValue.secondXX,.5);Near(signedValue.secondYY,.25);Near(signedValue.secondXY,-.5);
    const auto mirrored=Lean::DecodeMoments(raw,true);Near(mirrored.meanX,1);Near(mirrored.meanY,1);Near(mirrored.secondXX,.5);Near(mirrored.secondYY,.25);Near(mirrored.secondXY,.5);
    const auto scaled=Lean::DecodeMoments(raw,false,2);Near(scaled.meanX,-.5);Near(scaled.meanY,.5);Near(scaled.secondXX,.125);Near(scaled.secondYY,.0625);Near(scaled.secondXY,-.125);
    for(double scale:{0.0,-1.0,1e-10,1000001.0,std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()})
        Reject([&](){Lean::DecodeMoments(raw,false,scale);});
    for(unsigned channel=0;channel<5;++channel){auto bad=raw;if(channel==4)bad.crossR=std::numeric_limits<double>::quiet_NaN();else bad.rgba[channel]=std::numeric_limits<double>::quiet_NaN();
        Reject([&](){Lean::DecodeMoments(bad);});}
    auto bad=raw;bad.rgba[0]=1.001;Reject([&](){Lean::DecodeMoments(bad);});bad=raw;bad.crossR=-.001;Reject([&](){Lean::DecodeMoments(bad);});
}
}
int main(int argc,char** argv){
    try{Check(argc==4);Actual(argv[1],argv[2]);const auto fixtures=Fixtures(argv[3]);GoldenMoments();
        std::printf("PASS_ORIGINAL_WATER_LEAN_PACKAGE checks=%llu fixtures=%u assets=1 mips=10 planes=2 source_texels=349525 rejected_api=%u\n",
            static_cast<unsigned long long>(checks),fixtures,rejectedInputs);return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"FAIL:%s\n",error.what());return 1;}
}
