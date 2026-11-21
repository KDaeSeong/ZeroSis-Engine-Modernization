#include "OriginalWaterFogModel.h"
#include "OriginalLightingModel.h"
#include <array>
#include <cstdio>
#include <limits>
#include <utility>

namespace W=ZeroSisPresentation::OriginalWaterFog;
namespace L=ZeroSisPresentation::OriginalLighting;
namespace {
std::uint64_t checks=0;unsigned rejected=0;
void Check(bool value){++checks;if(!value)throw std::runtime_error("Water fog regression");}
void Near(double a,double b){Check(std::isfinite(a)&&std::isfinite(b)&&std::abs(a-b)<2e-13);}
template<class F>void Reject(F fn){bool caught=false;try{fn();}catch(const std::invalid_argument&){caught=true;}Check(caught);++rejected;}
W::Rgb Lut(W::Rgb c){return {1-c.b,.2+.6*c.r,.1+.7*c.g};}
void CrossReference(){
    for(double r:{0.0,.125,.5,1.0})for(double b:{0.0,.25,.75,1.0})for(double d:{0.0,.125,.5,1.0})
    for(double oa:{0.0,.25,1.0})for(double alpha:{0.0,.125,.5,1.0}){
        W::Rgba input{.125,.5,.875,alpha};W::Parameters p;p.reveal=r;p.visible=b;p.distance=d;p.overlay={oa*.15,oa*.3,oa*.6,oa};p.fog={.7,.1,.25};
        unsigned lutCalls=0;W::Rgb received{};
        const auto output=W::Apply(input,p,[&](W::Rgb c){++lutCalls;received=c;return Lut(c);});
        const double gray=static_cast<double>(.4f);const auto expectedR=gray*(1-r)+(p.overlay.r+(1-oa)*input.r)*r;
        const auto expectedG=gray*(1-r)+(p.overlay.g+(1-oa)*input.g)*r,expectedB=gray*(1-r)+(p.overlay.b+(1-oa)*input.b)*r;
        Near(received.r,expectedR);Near(received.g,expectedG);Near(received.b,expectedB);Check(lutCalls==1);
        L::PostInput post;post.overlay={p.overlay.r,p.overlay.g,p.overlay.b,p.overlay.a};post.maskR=r;post.maskB=b;post.fogFactor=d;post.fogColour={p.fog.r,p.fog.g,p.fog.b};
        const auto reference=L::FinishRgb({input.r,input.g,input.b},{gray,gray,gray},post,[](L::Rgb c){const auto v=Lut({c.x,c.y,c.z});return L::Rgb{v.r,v.g,v.b};});
        Near(output.r,reference.x);Near(output.g,reference.y);Near(output.b,reference.z);Check(output.a==alpha);
        if(r==0&&d==0){Near(output.r,gray);Near(output.g,gray);Near(output.b,gray);}
        if(d==1){Near(output.r,p.fog.r);Near(output.g,p.fog.g);Near(output.b,p.fog.b);}
    }
}
void FragmentRouting(){
    std::array<unsigned,64> marker{};marker.fill(W::OtherFragment);unsigned water=0,land=0,clouds=0,fetches=0,luts=0;
    for(unsigned y=0;y<8;++y)for(unsigned x=0;x<8;++x){const auto at=y*8+x;
        marker[at]=W::WriteFragment(marker[at],W::Fragment::OpaqueWater,true);
        marker[at]=W::WriteFragment(marker[at],W::Fragment::CoastOverlay,true);
        marker[at]=W::WriteFragment(marker[at],W::Fragment::RiverOverlay,true);
        const bool unit=x>=2&&x<6&&y>=2&&y<6;
        marker[at]=W::WriteFragment(marker[at],W::Fragment::Unit,unit);
        Check(marker[at]==(unit?0u:1u));const auto route=W::SelectRoute(true,marker[at]);
        if(route==W::Route::Water)++water;else if(route==W::Route::Land)++land;else ++clouds;
        const auto result=W::Guarded(true,marker[at],W::Rgba{.8,.7,.6,.5},[&](){++fetches;return std::make_pair(W::Rgba{.25,.5,.75,.375},W::Parameters{});},
            [&](W::Rgb c){++luts;return c;});Check(result.processed==!unit);Check(result.colour.a==(unit?.5:.375));
        if(unit){Near(result.colour.r,.8);Near(result.colour.g,.7);Near(result.colour.b,.6);}
    }
    Check(water==48&&land==16&&clouds==0&&fetches==48&&luts==48);
    Check(W::WriteFragment(1,W::Fragment::Unit,false)==1);Check(W::WriteFragment(1,W::Fragment::Ground,true)==0);
    // An unknown centre never fetches scene colour, overlay, mask parameters or LUT.
    for(unsigned value:{0u,1u,2u,255u}){
        Check(W::SelectRoute(false,value)==W::Route::Clouds);unsigned reads=0;volatile bool poison=true;
        auto output=W::Guarded(false,value,W::Rgba{.1,.2,.3,1},[&]()->std::pair<W::Rgba,W::Parameters>{++reads;if(poison)throw std::runtime_error("Hidden read");return {W::Rgba{},W::Parameters{}};},
            [&](W::Rgb c)->W::Rgb{++reads;if(poison)throw std::runtime_error("Hidden LUT read");return c;});Check(!output.processed&&reads==0);Near(output.colour.r,.1);
    }
    Check(W::SelectRoute(true,0)==W::Route::Land&&W::SelectRoute(true,255)==W::Route::Land);
    W::Parameters p;p.reveal=.5;p.visible=.25;p.distance=.25;const W::Rgba encoded{.125,.5,.875,.625};
    const auto once=W::Apply(encoded,p,Lut),twice=W::Apply(once,p,Lut);
    Check(std::abs(once.r-twice.r)>1e-4);Check(once.a==encoded.a&&twice.a==encoded.a);
}
void Invalid(){
    W::Parameters p;W::Rgba c{.1,.2,.3,.4};const double nan=std::numeric_limits<double>::quiet_NaN();
    for(double value:{-.1,1.1,nan,std::numeric_limits<double>::infinity()}){
        auto b=p;b.reveal=value;Reject([&](){W::Apply(c,b,Lut);});b=p;b.visible=value;Reject([&](){W::Apply(c,b,Lut);});
        b=p;b.distance=value;Reject([&](){W::Apply(c,b,Lut);});b=p;b.overlay.a=value;Reject([&](){W::Apply(c,b,Lut);});
        auto a=c;a.a=value;Reject([&](){W::Apply(a,p,Lut);});}
    auto b=p;b.overlay.r=nan;Reject([&](){W::Apply(c,b,Lut);});b=p;b.fog.b=nan;Reject([&](){W::Apply(c,b,Lut);});
    Reject([&](){W::Apply(c,p,[&](W::Rgb){return W::Rgb{nan,0,0};});});
    Reject([&](){W::WriteFragment(0,static_cast<W::Fragment>(99),true);});
}
}
int main(){try{CrossReference();FragmentRouting();Invalid();std::printf("PASS_WATER_FOG_ALPHA_ORDER_MARKER_GUARDS checks=%llu rejected=%u cases=768 water_pixels=48 unit_pixels=16\n",static_cast<unsigned long long>(checks),rejected);return 0;
}catch(const std::exception& e){std::fprintf(stderr,"FAIL:%s\n",e.what());return 1;}}
