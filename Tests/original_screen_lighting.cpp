#include "OriginalScreenLightingModel.h"
#include "screen_lighting_goldens.h"
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <cstdlib>
#include <limits>

namespace SL=ZeroSisPresentation::OriginalScreenLighting;
namespace {
unsigned checks=0;
void Check(bool condition,const char* label){
    ++checks;if(!condition){std::fprintf(stderr,"FAIL %s\n",label);std::exit(1);}
}
void Near(double actual,double expected,const char* label,double tolerance=8e-12){
    Check(std::isfinite(actual)&&std::abs(actual-expected)<=tolerance,label);
}
void Near(SL::Rgb actual,SL::Rgb expected,const char* label){
    Near(actual.x,expected.x,label);Near(actual.y,expected.y,label);Near(actual.z,expected.z,label);
}
template<class Action>void Reject(Action action,const char* label){
    bool rejected=false;try{action();}catch(const std::invalid_argument&){rejected=true;}Check(rejected,label);
}
SL::Rgb Colour(const double* value){return {value[0],value[1],value[2]};}
}
int main(){
    Check(sizeof(SL::Constants)==32&&offsetof(SL::Constants,flags)==16,"GPU constant layout");
    Check(SL::OriginalReflectionSide==1024&&SL::OriginalDisabledReflectionSide==32,"Original reflection dimensions");
    for(unsigned detail=0;detail<4;++detail)for(unsigned reflection=0;reflection<2;++reflection)
        for(int diffuse=-1;diffuse<=1;++diffuse)for(int specular=-1;specular<=1;++specular){
            SL::Policy policy;policy.terrainDetailLevel=detail;policy.reflectionLevel=reflection;
            policy.diffuseOverride=diffuse;policy.specularOverride=specular;
            const bool expectedDiffuse=diffuse==-1||diffuse==1;
            const bool expectedSpecular=specular==-1?detail==3:specular==1;
            const auto resolved=SL::ResolvePolicy(policy);
            Check(resolved.diffuse==expectedDiffuse&&resolved.specular==expectedSpecular&&resolved.reflection==(reflection==1),
                "Original detail/debug/reflection rules");
            const auto constants=SL::MakeConstants(1273,744,policy,true);
            Check(constants.flags[0]==(expectedSpecular?1.f:0.f)&&
                constants.flags[1]==(expectedDiffuse?1.f:0.f)&&constants.flags[2]==(expectedSpecular?1.f:0.f)&&constants.flags[3]==0,
                "GPU flags preserve original gates");
            Check(constants.viewport[0]==1273&&constants.viewport[1]==744&&
                constants.viewport[2]==1.f/1273.f&&constants.viewport[3]==1.f/744.f,"Viewport reciprocal binding");
            unsigned fetches=0;const SL::Rgb diffuseColour{.25,.5,.75},specularColour{.5,.25,.75};
            const auto result=SL::GuardedCombine(true,{9,9,9},diffuseColour,specularColour,policy,0,0,2,
                [&](SL::Uv uv){++fetches;Near(uv[0],.5,"Known NDC sampleU");Near(uv[1],.5,"Known NDC sampleV");return SL::Rgb{.5,.5,.5};});
            Check(fetches==(expectedSpecular?1u:0u),"Water reflection quality cannot disable static t9");
            if(!expectedSpecular)Near(result,expectedDiffuse?diffuseColour:SL::Rgb{},"Raw diffuse branch bypasses gamma");
        }
    for(const auto& fixture:ScreenGoldens){
        const auto actual=SL::Combine(Colour(fixture.diffuse),Colour(fixture.specular),Colour(fixture.reflection),{true,true,true});
        Near(actual,Colour(fixture.expected),"Independent original composite golden");
    }
    const auto raw=SL::Combine({}, {1,1,1},{.5,.5,.5},{true,true,true});
    Near(raw.x,ScreenHalfEncoded,"Raw reflection sample has no implicit decode");
    // The phase10 retail resource/sampler proof removes the producer decode.
    // Retain its numerical counterexample only as a negative regression oracle.
    const double wrongDecode=std::pow(.5,static_cast<double>(2.2f));
    const SL::Rgb decoded{wrongDecode,wrongDecode,wrongDecode};
    const auto adapted=SL::Combine({}, {1,1,1},decoded,{true,true,true});
    Near(adapted.x,ScreenHalfRoundtrip,"Rejected producer decode counterexample");
    Check(raw.x-adapted.x>.2,"Incorrect double gamma produces a material difference");
    const unsigned sizes[]={1,2,31,1024,1273,4096};
    for(auto width:sizes)for(auto height:sizes)for(unsigned index=0;index<97;++index){
        const double x=(static_cast<double>(index)-13.5)*width/71.0;
        const double y=(static_cast<double>(index)*7-41.5)*height/631.0;
        const double w=(index&1)?3.25:.125;
        const auto pixel=SL::UvFromPixel(x,y,width,height);
        const auto clip=SL::UvFromClip((2*x/width-1)*w,(1-2*y/height)*w,w);
        Near(pixel[0],clip[0],"D3D viewport original NDC x");Near(pixel[1],clip[1],"D3D viewport original NDC y");
    }
    const auto outside=SL::UvFromClip(4,-4,1);
    Check(outside[0]==2.5&&outside[1]==-1.5,"Original UV calculation does not clamp coordinates");
    const double nan=std::numeric_limits<double>::quiet_NaN();
    for(unsigned i=0;i<64;++i){
        unsigned fetches=0;SL::Policy poison;poison.terrainDetailLevel=999;poison.specularOverride=8;
        const auto hidden=SL::GuardedCombine(false,{.1,.2,.3},{nan,nan,nan},{nan,nan,nan},poison,nan,nan,0,
            [&](SL::Uv){++fetches;return SL::Rgb{nan,nan,nan};});
        Near(hidden,{.1,.2,.3},"Hidden material/coordinates/policy remain unread");
        Check(fetches==0,"Unknown material cannot enter reflection sampler");
    }
    SL::Policy disabled;disabled.specularOverride=0;
    Near(SL::GuardedCombine(true,{}, {.2,.3,.4},{nan,nan,nan},disabled,nan,nan,0,
        [nan](SL::Uv){return SL::Rgb{nan,nan,nan};}),{.2,.3,.4},"Disabled specular ignores invalid unused data");
    const auto unavailable=SL::MakeConstants(1024,1024,SL::Policy{},false);
    Check(unavailable.flags[0]==0&&unavailable.flags[2]==1,"Unavailable RT supplies zero without changing specular rule");
    SL::Policy invalid;
    invalid.terrainDetailLevel=4;Reject([&]{SL::ResolvePolicy(invalid);},"Invalid detail rejected");
    invalid=SL::Policy{};invalid.reflectionLevel=2;Reject([&]{SL::ResolvePolicy(invalid);},"Invalid reflection setting rejected");
    invalid=SL::Policy{};invalid.diffuseOverride=2;Reject([&]{SL::ResolvePolicy(invalid);},"Invalid diffuse override rejected");
    invalid=SL::Policy{};invalid.specularOverride=-2;Reject([&]{SL::ResolvePolicy(invalid);},"Invalid specular override rejected");
    Reject([]{SL::UvFromClip(0,0,0);},"Zero projection divisor rejected");
    Reject([&]{SL::UvFromClip(nan,0,1);},"Nonfinite clip rejected");
    Reject([]{SL::UvFromPixel(0,0,0,1);},"Zero viewport rejected");
    Reject([]{SL::MakeConstants(4097,1,SL::Policy{},true);},"Oversized viewport rejected");
    Reject([&]{SL::Colour({nan,0,0});},"Nonfinite reflection sample rejected");
    Reject([]{SL::Colour({-.1,0,0});},"Negative reflection sample rejected");
    std::printf("PASS_ORIGINAL_SCREEN_LIGHTING checks=%u\n",checks);return 0;
}
