#define NOMINMAX
#include "OriginalWaterBlendState.h"
#include "OriginalReflectionContract.h"
#include "OriginalScreenLightingModel.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>

namespace B=ZeroSisPresentation::OriginalWaterBlend;
namespace F=ZeroSisPresentation::OriginalWaterFog;
namespace R=ZeroSisPresentation::OriginalReflection;
namespace S=ZeroSisPresentation::OriginalScreenLighting;
namespace {
unsigned checks=0;
void Check(bool value,const char* label){++checks;if(!value){std::fprintf(stderr,"FAIL %s\n",label);std::exit(1);}}
void Near(double a,double b,const char* label){Check(std::isfinite(a)&&std::abs(a-b)<2e-12,label);}
template<class Action>void Reject(Action action,const char* label){bool bad=false;try{action();}catch(const std::invalid_argument&){bad=true;}Check(bad,label);}
}
int main(){
    const auto desc=B::MakeMrtDescription();const auto& colour=desc.RenderTarget[0];
    Check(!desc.AlphaToCoverageEnable&&desc.IndependentBlendEnable,"Isolated integer MRT protection");
    Check(colour.BlendEnable&&colour.SrcBlend==D3D11_BLEND_SRC_ALPHA&&colour.DestBlend==D3D11_BLEND_INV_SRC_ALPHA&&
        colour.BlendOp==D3D11_BLEND_OP_ADD&&colour.SrcBlendAlpha==D3D11_BLEND_ONE&&colour.DestBlendAlpha==D3D11_BLEND_ONE&&
        colour.BlendOpAlpha==D3D11_BLEND_OP_ADD&&colour.RenderTargetWriteMask==15,"Recovered OM state8 descriptor");
    for(unsigned i=1;i<8;++i)Check(!desc.RenderTarget[i].BlendEnable&&desc.RenderTarget[i].RenderTargetWriteMask==15,"Integer MRT blending disabled");
    const auto coast=B::MakeMrtDescription(false);
    Check(coast.RenderTarget[1].RenderTargetWriteMask==0&&coast.RenderTarget[4].RenderTargetWriteMask==15,"Coast preserves pick but writes fog class");
    for(unsigned depth=0;depth<=128;++depth)for(unsigned reflection=0;reflection<=64;++reflection){
        const double d=depth/128.0,r=reflection/64.0;
        const double expected=d*(1+r)<1?d*(1+r):1;
        Near(B::Opacity(d,r),expected,"Original MAD_SAT alpha reference");
    }
    for(unsigned step=0;step<=128;++step)for(unsigned background=0;background<=32;++background){
        const double a=step/128.0,d=background/32.0;
        const auto result=B::BlendUnorm({.25,.75,1,a},{1,.125,0,d});
        Near(result.r,1-.75*a,"Encoded red alpha blend");
        Near(result.g,.125+.625*a,"Encoded green alpha blend");
        Near(result.b,a,"Encoded blue alpha blend");
        Near(result.a,a+d>1?1:a+d,"Original additive alpha differs from source-over alpha");
    }
    F::Parameters fog;fog.reveal=.75;fog.visible=.25;fog.distance=.4;
    fog.overlay={.1,.05,.025,.2};fog.fog={.6,.7,.8};
    const auto lut=[](F::Rgb v){return F::Rgb{v.r*v.r,v.g*v.g,v.b*v.b};};
    const B::Rgba source{.8,.6,.3,.35},underlay{.1,.2,.7,1};
    const auto actual=B::FogBeforeBlend(source,underlay,fog,lut);
    // Separately derive stock overlay->gray/FOW->nonlinear LUT->distance->OM.
    const auto lane=[&](double src,double dst,double overlay,double fogColour){
        const double gray=0.4000000059604644775390625; // Original float32 literal 0x3ecccccd.
        const double base=gray+(.75)*(overlay+.8*src-gray);
        const double mapped=base+(.75*.75)*(base*base-base);
        const double fogged=mapped+.4*(fogColour-mapped);
        return fogged*.35+dst*.65;
    };
    Near(actual.r,lane(.8,.1,.1,.6),"Fog-before-blend red independent equation");
    Near(actual.g,lane(.6,.2,.05,.7),"Fog-before-blend green independent equation");
    Near(actual.b,lane(.3,.7,.025,.8),"Fog-before-blend blue independent equation");
    const auto wrong=F::Apply(B::BlendUnorm(source,underlay),fog,lut);
    Check(std::abs(actual.r-wrong.r)>.01,"Post-composite FOW is not equivalent");
    Check(!B::NeedsFinalFog(2)&&B::NeedsFinalFog(0)&&B::NeedsFinalFog(1),"Completed underlay/water bypass final fog");
    unsigned plans=0;
    for(unsigned requested=0;requested<128;++requested)for(unsigned available=0;available<128;++available){
        if((requested|available)&~R::SceneMask)continue;
        const auto plan=R::MakePlan(requested,available);++plans;
        Check(plan.draw==(requested&available)&&plan.missing==(requested&~available),"Exact four original reflection scene masks");
        for(auto scene:R::DrawOrder)Check(R::Includes(plan,scene)==((requested&available&static_cast<unsigned>(scene))!=0),"Original reflection draw order selection");
    }
    Check(plans==256&&R::DrawOrder[0]==R::Scene::Units&&R::DrawOrder[3]==R::Scene::Ice,"Four classes exclude terrain and forests");
    Check(R::TypelessRgba8Format==27&&R::UnormRgba8Format==28&&R::SrgbRgba8Format==29&&R::LinearFilter==21&&R::WrapAddress==1&&!R::ReflectionSrvDecodesSrgb,"Recovered Raw RGBA/UNORM/linear-wrap contract");
    const auto raw=S::Combine({}, {1,1,1},{.5,.5,.5},{true,true,true});
    Near(raw.x,std::pow(.5,0.4545454680919647216796875),"Terrain t9 consumes raw encoded sample without decode");
    const auto constants=S::MakeConstants(1920,1080,S::Policy{},true);
    Check(constants.flags[3]==0,"Removed candidate decode flag is reserved zero");
    const double nan=std::numeric_limits<double>::quiet_NaN();
    Reject([&]{B::Opacity(nan,0);},"Nonfinite opacity rejected");
    Reject([]{B::Opacity(.5,-.1);},"Negative sample alpha rejected");
    Reject([&]{B::BlendUnorm({nan,0,0,1},{0,0,0,1});},"Nonfinite source rejected");
    Reject([]{R::MakePlan(4,0);},"Forests cannot be silently assigned an original Raw class");
    std::printf("PASS_ORIGINAL_WATER_BLEND checks=%u plans=%u native_graphics_calls=0\n",checks,plans);return 0;
}
