#include "OriginalTerrainMaterialSampler.h"
#include "OriginalTerrainBinding.h"
#include <cstdio>
#include <fstream>

namespace M=ZeroSisPresentation::OriginalTerrainMaterial;
namespace T=ZeroSisPresentation::OriginalTerrain;
namespace {
std::uint64_t checks=0;unsigned rejected=0;
void Check(bool value){++checks;if(!value)throw std::runtime_error("Material sampler regression");}
void Near(double a,double b){Check(std::isfinite(a) && std::isfinite(b) && std::abs(a-b)<1e-12);}
template<class F>void Reject(F fn){bool bad=false;try{fn();}catch(const std::invalid_argument&){bad=true;}Check(bad);++rejected;}
std::vector<unsigned char> Read(const std::string& path){std::ifstream f(path,std::ios::binary|std::ios::ate);Check(f.good());const auto n=f.tellg();Check(n>=24 && n<=128*1024*1024);
    std::vector<unsigned char> raw(static_cast<std::size_t>(n));f.seekg(0);f.read(reinterpret_cast<char*>(raw.data()),static_cast<std::streamsize>(raw.size()));Check(f.good());return raw;}
void Word(std::vector<unsigned char>& data,unsigned at,unsigned value){for(unsigned i=0;i<4;++i)data[at+i]=static_cast<unsigned char>(value>>(8*i));}
std::vector<unsigned char> Synthetic(){std::vector<unsigned char> raw(192);std::memcpy(raw.data(),"DDS ",4);Word(raw,4,124);Word(raw,8,0x1007);Word(raw,12,8);Word(raw,16,8);
    Word(raw,28,1);Word(raw,76,32);Word(raw,80,4);Word(raw,84,0x35545844);
    for(unsigned block=0;block<4;++block){const unsigned at=128+block*16;raw[at]=block&1?20:240;raw[at+1]=block&1?240:20;
        std::uint64_t alpha=0;for(unsigned i=0;i<16;++i)alpha|=static_cast<std::uint64_t>(i%8)<<(3*i);
        for(unsigned i=0;i<6;++i)raw[at+2+i]=static_cast<unsigned char>(alpha>>(8*i));
        const unsigned c0=block&1?0xf800:0x07e0,c1=block&1?0x001f:0xf800;raw[at+8]=static_cast<unsigned char>(c0);raw[at+9]=static_cast<unsigned char>(c0>>8);
        raw[at+10]=static_cast<unsigned char>(c1);raw[at+11]=static_cast<unsigned char>(c1>>8);Word(raw,at+12,0xe4e4e4e4);}
    return raw;}
void Golden(){auto raw=Synthetic();const auto view=M::DdsMip0View(raw.data(),raw.size());
    const unsigned reds[2][4]={{0,255,85,170},{255,0,170,85}},alphas[2][8]={{240,20,208,177,145,114,82,51},{20,240,64,108,152,196,0,255}};
    for(unsigned y=0;y<8;++y)for(unsigned x=0;x<8;++x){const unsigned block=(y/4)*2+x/4,pixel=(y%4)*4+x%4;
        Near(M::ReadRed(view,x,y),reds[block&1][pixel%4]/255.0);Near(M::ReadAlpha(view,x,y),alphas[block&1][pixel%8]/255.0);
        Near(M::SampleRedBilinear(view,(x+.5)/8,(y+.5)/8),M::ReadRed(view,x,y));Near(M::SampleAlphaBilinear(view,(x+.5)/8,(y+.5)/8),M::ReadAlpha(view,x,y));}
    Near(M::SampleRedBilinear(view,0,0),.25*(M::ReadRed(view,7,7)+M::ReadRed(view,0,7)+M::ReadRed(view,7,0)+M::ReadRed(view,0,0)));
    Near(M::SampleAlphaBilinear(view,-.125,1.125),M::SampleAlphaBilinear(view,.875,.125));
    Near(M::SampleRedBilinear(view,-3,-2,M::AddressMode::Clamp),M::ReadRed(view,0,0));
    Near(M::SampleAlphaBilinear(view,3,2,M::AddressMode::Clamp),M::ReadAlpha(view,7,7));
    auto opaque=raw;for(unsigned i=0;i<4;++i)opaque[128+i*16]=opaque[129+i*16]=255;
    const auto solid=M::DdsMip0View(opaque.data(),opaque.size());std::array<M::Layer,8> layers{};
    layers[0].diffuse=solid;layers[0].weight=.5;layers[0].source=M::HeightSource::DeclaredMissing;
    layers[1].diffuse=solid;layers[1].weight=.5;layers[1].source=M::HeightSource::Null;
    auto blend=M::BlendHeight(true,layers,2);Near(blend.height,.25);Near(blend.totalWeight,1);Check(blend.sampledSlots==2);
    layers[0].weight=.01;layers[0].diffuse={};blend=M::BlendHeight(true,layers,2);Near(blend.height,0);Check(blend.sampledSlots==1);
    layers[0].weight=.5;Reject([&](){M::BlendHeight(true,layers,2);});
    auto unknown=M::BlendHeight(false,layers,999);Near(unknown.height,0);Check(unknown.sampledSlots==0);
    Reject([&](){M::BlendHeight(true,layers,9);});Reject([&](){M::ReadAlpha(view,8,0);});Reject([&](){M::ReadRed(view,0,8);});
    for(double value:{std::numeric_limits<double>::quiet_NaN(),std::numeric_limits<double>::infinity(),1e10}){
        Reject([&](){M::SampleRedBilinear(view,value,0);});Reject([&](){M::SampleAlphaBilinear(view,0,value);});}
    auto invalid=view;invalid.bytes--;Reject([&](){M::ReadRed(invalid,0,0);});invalid=view;invalid.data=nullptr;Reject([&](){M::ReadAlpha(invalid,0,0);});
    invalid=view;invalid.width=0;Reject([&](){M::Validate(invalid);});invalid=view;invalid.height=4097;Reject([&](){M::Validate(invalid);});
    Reject([&](){M::DdsMip0View(raw.data(),raw.size()-1);});Reject([&](){M::DdsMip0View(nullptr,raw.size());});
    Reject([&](){M::SampleRedBilinear(view,0,0,static_cast<M::AddressMode>(7));});Reject([&](){M::Address(0,0,M::AddressMode::Wrap);});
}
unsigned Actual(const std::string& filename,const std::string& reference){
    const auto package=T::DecodePackage(Read(filename),T::PackageSha256);std::ifstream f(reference);Check(f.good());unsigned textures=0;f>>textures;Check(textures==59);unsigned samples=0;
    for(unsigned i=0;i<textures;++i){unsigned index=0,width=0,height=0,count=0;f>>index>>width>>height>>count;Check(f.good());const auto view=M::ViewMip0(package,index);
        Check(view.width==width && view.height==height);for(unsigned j=0;j<count;++j){unsigned channel=0,mode=0;double u=0,v=0,expected=0;f>>channel>>mode>>u>>v>>expected;Check(f.good() && channel<=1 && mode<=1);
            const auto address=mode?M::AddressMode::Clamp:M::AddressMode::Wrap;
            Near(channel?M::SampleAlphaBilinear(view,u,v,address):M::SampleRedBilinear(view,u,v,address),expected);++samples;}}
    Reject([&](){M::ViewMip0(package,static_cast<unsigned>(package.textures.size()));});Reject([&](){M::ViewMip0(package,T::NullTexture);});
    return samples;
}
}
int main(int argc,char** argv){try{Check(argc==3);Golden();const auto samples=Actual(argv[1],argv[2]);
    std::printf("PASS_MATERIAL_BORROWED_BC3_SAMPLER checks=%llu actual_samples=%u textures=59 rejected=%u\n",static_cast<unsigned long long>(checks),samples,rejected);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"FAIL:%s\n",error.what());return 1;}}
