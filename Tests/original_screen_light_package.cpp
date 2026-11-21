#include "OriginalScreenLightPackage.h"
#include <array>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>
#include <string>

namespace P=ZeroSisPresentation::OriginalScreenLightAssets;
namespace H=ZeroSisPresentation::OriginalTerrain;
namespace {
unsigned checks=0,rejections=0;
void Check(bool condition,const char* reason){++checks;if(!condition){std::fprintf(stderr,"FAIL %s\n",reason);std::exit(1);}}
template<class Action>void Reject(Action action,const char* reason){bool rejected=false;try{action();}catch(const std::invalid_argument&){rejected=true;}Check(rejected,reason);++rejections;}
using Pixel=std::array<unsigned char,4>;
std::array<unsigned,3> Colour565(unsigned word){
    const unsigned r=(word>>11)&31,g=(word>>5)&63,b=word&31;
    return {{(r<<3)|(r>>2),(g<<2)|(g>>4),(b<<3)|(b>>2)}};
}
// Independent CPU expansion used only by this test. The production path
// validates and uploads unchanged BC3 blocks, without a software pixel decoder.
std::vector<unsigned char> DecodeTop(const P::Package& package){
    const auto& top=package.texture.levels.front();std::vector<unsigned char> bgra(1024u*1024u*4u);
    for(unsigned by=0;by<256;++by)for(unsigned bx=0;bx<256;++bx){
        const auto* block=package.bytes.data()+top.offset+(by*256u+bx)*16u;
        const unsigned a0=block[0],a1=block[1];std::array<unsigned,8> alpha{{a0,a1,0,0,0,0,0,0}};
        if(a0>a1){for(unsigned i=1;i<=6;++i)alpha[i+1]=((7-i)*a0+i*a1)/7;}
        else{for(unsigned i=1;i<=4;++i)alpha[i+1]=((5-i)*a0+i*a1)/5;alpha[6]=0;alpha[7]=255;}
        std::uint64_t alphaBits=0;for(unsigned i=0;i<6;++i)alphaBits|=std::uint64_t(block[i+2])<<(8*i);
        const auto c0=Colour565(unsigned(block[8])|(unsigned(block[9])<<8));
        const auto c1=Colour565(unsigned(block[10])|(unsigned(block[11])<<8));
        std::array<std::array<unsigned,3>,4> colours{{c0,c1,{{0,0,0}},{{0,0,0}}}};
        for(unsigned channel=0;channel<3;++channel){colours[2][channel]=(2*c0[channel]+c1[channel])/3;colours[3][channel]=(c0[channel]+2*c1[channel])/3;}
        const auto colourBits=P::Word(block+12);
        for(unsigned texel=0;texel<16;++texel){
            const unsigned x=bx*4+texel%4,y=by*4+texel/4;const auto& colour=colours[(colourBits>>(2*texel))&3];
            const auto at=(static_cast<std::size_t>(y)*1024+x)*4;
            bgra[at]=static_cast<unsigned char>(colour[2]);bgra[at+1]=static_cast<unsigned char>(colour[1]);bgra[at+2]=static_cast<unsigned char>(colour[0]);
            bgra[at+3]=static_cast<unsigned char>(alpha[(alphaBits>>(3*texel))&7]);
        }
    }
    return bgra;
}
}
int main(int argc,char** argv){
    Check(argc==2,"Exactly one explicit immutable package input");
    std::ifstream stream(argv[1],std::ios::binary);Check(stream.good(),"Explicit package path opens");
    std::vector<unsigned char> bytes{std::istreambuf_iterator<char>(stream),std::istreambuf_iterator<char>()};
    Check(bytes.size()==P::PackageBytes,"Exact package size");
    const auto original=bytes;const auto package=P::DecodePackage(std::move(bytes),P::PackageSha256);
    Check(package.bytes==original,"Production decoder preserves every original byte");
    Check(package.texture.width==1024&&package.texture.height==1024&&package.texture.mips==11&&package.texture.levels.size()==11,"Original11 mip dimensions");
    std::size_t next=176;unsigned side=1024;
    for(unsigned i=0;i<11;++i){
        const auto& mip=package.texture.levels[i];const std::size_t pitch=((side+3)/4)*16;
        Check(mip.level==i&&mip.width==side&&mip.height==side&&mip.offset==next&&mip.rowPitch==pitch&&mip.bytes==pitch*((side+3)/4),"Every mip extent and row pitch");
        next+=mip.bytes;side=side>1?side/2:1;
    }
    Check(next==package.bytes.size(),"No omitted tail or padding");
    const auto pixels=DecodeTop(package);
    Check(H::Sha256Hex(pixels.data(),pixels.size())=="d8965fcc45460d1411b269a3864139db88b0aa7370b4dade15b2d0a376729bc1","All1048576 decoded pixels match existing FTXT BC3 reference");
    for(unsigned length=0;length<128;++length)Reject([&]{P::DecodePackage(std::vector<unsigned char>(original.begin(),original.begin()+length),P::PackageSha256);},"Truncated header rejects");
    auto altered=original;altered.push_back(0);Reject([&]{P::DecodePackage(altered,P::PackageSha256);},"Trailing payload rejects");
    for(unsigned index:{0u,8u,12u,16u,48u,132u,176u,1398303u}){
        altered=original;altered[index]^=1;
        Reject([&]{P::DecodePackage(altered,P::PackageSha256);},"Changed outer pinned bytes reject");
        const auto repinned=H::Sha256Hex(altered.data(),altered.size());
        Reject([&]{P::DecodePackage(altered,repinned);},"Repinned malformed magic/version/extent/inner DDS rejects");
    }
    Reject([&]{P::DecodePackage(original,std::string(64,'g'));},"Non-hex outer pin rejects");
    Reject([&]{P::DecodePackage(original,"");},"Absent outer pin rejects");
    std::printf("PASS_ORIGINAL_SCREEN_LIGHT_PACKAGE checks=%u rejected=%u mip_levels=11 decoded_pixels=1048576 native_graphics_calls=0\n",checks,rejections);
    return 0;
}
