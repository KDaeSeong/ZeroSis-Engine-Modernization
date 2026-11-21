#include "OriginalDynamicShadowModel.h"
#include <cstdio>
#include <limits>
#include <stdexcept>
namespace S=ZeroSisPresentation::OriginalDynamicShadow;
static unsigned checks=0;
void Check(bool v){++checks;if(!v){std::fprintf(stderr,"check=%u\n",checks);throw std::runtime_error("Shadow model regression");}}
void Near(double a,double b,double tolerance=1e-6){Check(std::abs(a-b)<tolerance);}
template<class F>void Reject(F f){bool rejected=false;try{f();}catch(const std::runtime_error&){rejected=true;}Check(rejected);}
int main(){try{
    S::Bounds bounds;const auto empty=S::Fit(bounds);Check(!empty.enabled&&empty.resolution==2048);
    unsigned reads=0;const auto sample=[&](unsigned,unsigned){++reads;return .4;};
    Near(S::Occlusion(true,empty,{0,0,0},0,sample),0);Check(reads==0);
    bounds.Add({-1,-1,-1});bounds.Add({1,1,1});
    const auto projection=S::Fit(bounds,2048,{0,1,0});Check(projection.enabled);
    const auto center=S::Project(projection,{0,0,0});Near(center.x,0);Near(center.y,0);Near(center.z,.5);
    Near(S::Occlusion(true,projection,{0,0,0},S::CandidateBias,sample),1);Check(reads==4);
    Near(S::Occlusion(false,projection,{std::numeric_limits<double>::quiet_NaN(),0,0},0,sample),0);Check(reads==4);
    Near(S::Occlusion(true,projection,{100,0,0},0,sample),0);Check(reads==4);
    const auto lit=[](unsigned,unsigned){return .8;};Near(S::Occlusion(true,projection,{0,0,0},0,lit),0);
    const auto corner=[](unsigned x,unsigned y){return x==1023&&y==1023?.1:.9;};
    Near(S::Occlusion(true,projection,{0,0,0},0,corner),.25);
    Near(S::Occlusion(true,projection,{0,0,0},.11,[](unsigned,unsigned){return .4;}),0);
    Reject([&](){S::Occlusion(true,projection,{0,0,0},0,[](unsigned,unsigned){return -1.;});});
    Reject([&](){S::Occlusion(true,projection,{0,0,0},-1,sample);});
    Reject([&](){S::Fit(bounds,15);});Reject([&](){S::Fit(bounds,4097);});Reject([&](){S::Fit(bounds,1000);});
    Reject([&](){S::Fit(bounds,2048,{0,0,0});});
    Reject([&](){S::Bounds b;b.Add({5000,0,0});});
    Reject([&](){S::Bounds b;b.Add({0,std::numeric_limits<double>::infinity(),0});});
    for(unsigned resolution: {16u,64u,512u,2048u,4096u})for(unsigned mode=0;mode<5;++mode){
        S::Bounds b;const double shift=static_cast<double>(mode)*13.124;
        b.Add({-48+shift,-.6,-44});b.Add({49+shift,5.25,45});
        const auto p=S::Fit(b,resolution);Check(p.enabled&&p.resolution==resolution);
        for(unsigned cornerMask=0;cornerMask<8;++cornerMask){const S::Vec3 v{cornerMask&1?b.maximum.x:b.minimum.x,
            cornerMask&2?b.maximum.y:b.minimum.y,cornerMask&4?b.maximum.z:b.minimum.z};const auto projected=S::Project(p,v);
            Check(projected.x>=-1&&projected.x<=1&&projected.y>=-1&&projected.y<=1&&projected.z>0&&projected.z<1);}
        const S::Vec3 receiver{shift,1,0};const double receiverDepth=S::Project(p,receiver).z;
        for(unsigned step=0;step<11;++step){const double amount=step/10.;
            const double expected=receiverDepth-S::CandidateBias>amount?1:0;
            Near(S::Occlusion(true,p,receiver,S::CandidateBias,[&](unsigned x,unsigned y){Check(x<resolution&&y<resolution);return amount;}),expected);}
    }
    Near(S::WaterAttenuation(0,1),1);Near(S::WaterAttenuation(1,1),.33);Near(S::WaterAttenuation(.5,1),.665);
    Near(S::WaterAttenuation(2,1),.33);Near(S::WaterAttenuation(-1,1),1);Near(S::WaterAttenuation(1,0),1);
    Reject([](){S::WaterAttenuation(.5,2);});
    std::printf("PASS_DYNAMIC_SHADOW checks=%u\n",checks);return 0;
}catch(const std::exception& ex){std::fprintf(stderr,"%s\n",ex.what());return 1;}}
