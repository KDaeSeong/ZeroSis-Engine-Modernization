#include "OriginalWaterOpticsModel.h"
#include "original_water_optics_golden.h"
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>

namespace O=ZeroSisPresentation::OriginalWaterOptics;
namespace {
unsigned checks=0;
const char* section="start";
void Check(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
void Near(double actual,double expected,double tolerance=2e-11){
    const bool equal=std::isfinite(actual)&&std::isfinite(expected)&&std::abs(actual-expected)<=tolerance*(1+std::abs(expected));
    if(!equal)std::fprintf(stderr,"section=%s check=%u actual=%.17g expected=%.17g\n",section,checks,actual,expected);
    Check(equal,"Optics numeric reference differs");
}
template<class Fn>void Reject(Fn fn){bool rejected=false;try{fn();}catch(const std::invalid_argument&){rejected=true;}
    Check(rejected,"Malformed optics input was accepted");}
std::uint32_t FloatBits(double value){const float f=static_cast<float>(value);std::uint32_t result=0;std::memcpy(&result,&f,4);return result;}
void Mixtures(){
    section="mixed moments";
    for(unsigned index=0;index<256;++index){
        const double t=static_cast<double>(index)/255;
        const O::Vec2 firstMean{0.3*t-0.1,0.25-0.4*t},secondMean{0.2-0.5*t,0.4*t-0.2};
        const O::Symmetric2 firstCov{0.01+0.04*t,0.02+0.01*t,0.001-0.002*t},
            secondCov{0.04-0.02*t,0.03+0.03*t,-0.003+0.004*t};
        const auto first=O::FromScalars(firstMean.x,firstMean.y,firstCov.xx+firstMean.x*firstMean.x,
            firstCov.yy+firstMean.y*firstMean.y,firstCov.xy+firstMean.x*firstMean.y);
        const auto second=O::FromArray({{secondMean.x,secondMean.y,secondCov.xx+secondMean.x*secondMean.x,
            secondCov.yy+secondMean.y*secondMean.y,secondCov.xy+secondMean.x*secondMean.y}});
        const double scale=index%2?static_cast<double>(0.33f):static_cast<double>(0.7f);
        const double a=(index%11)+1.0,b=(index%7)+0.25;
        const auto actual=O::MixLayers(first,second,{a,b},scale);
        const double w0=(a/(a+b))/scale,w1=(b/(a+b))/scale;
        const double mx=w0*firstMean.x+w1*secondMean.x,my=w0*firstMean.y+w1*secondMean.y;
        // Independent centred-variable covariance: no raw moment cross-products.
        const O::Symmetric2 covariance{w0*w0*firstCov.xx+w1*w1*secondCov.xx,
            w0*w0*firstCov.yy+w1*w1*secondCov.yy,w0*w0*firstCov.xy+w1*w1*secondCov.xy};
        Near(actual.mean.x,mx);Near(actual.mean.y,my);
        Near(actual.covariance.xx,covariance.xx);Near(actual.covariance.yy,covariance.yy);Near(actual.covariance.xy,covariance.xy);
        Near(actual.second.xx,covariance.xx+mx*mx);Near(actual.second.yy,covariance.yy+my*my);
        Near(actual.second.xy,covariance.xy+mx*my);Near(actual.scaledWeights.x,w0);Near(actual.scaledWeights.y,w1);
    }
    const auto edge=O::MixLayers({0.2,0.3,0.1,0.2,0.04},{-0.4,0.1,0.3,0.2,-0.01},{0,3},0.5);
    Near(edge.mean.x,-0.8);Near(edge.mean.y,0.2);
    const auto weights=O::WeightsFromBlendRG(0.75,0.25,0.5);
    Near(weights.x,1.2);Near(weights.y,0.8);
}
void Gaussian(){
    section="independent eigenbasis Gaussian";
    for(const auto& test:GoldenOpticsGaussians){
        const auto actual=O::GaussianLobe({test.xx,test.yy,test.xy},{test.x,test.y},test.k,test.wide);
        Check(actual.rejected==test.rejected,"Gaussian cutoff differs");
        Near(actual.determinant,test.determinant,3e-11);
        Near(actual.q,test.q,3e-10);Near(actual.value,test.value,3e-10);
    }
    section="Gaussian boundaries";
    const auto zero=O::GaussianLobe({-1,0,0},{1,1},1);
    Check(zero.rejected&&zero.value==0&&zero.determinant==0,"Zero determinant must reject");
    Check(O::GaussianLobe({-2,0,0},{1,1},1).rejected,"Negative determinant must reject");
    const auto cutoff=O::GaussianLobe({0,0,0},{4,4},1);
    Check(cutoff.rejected&&cutoff.q==16&&cutoff.value==0,"q=16 must reject");
    Check(!O::GaussianLobe({0,0,0},{4,3.999},1).rejected,"q<16 must remain");
    const auto negativeQ=O::GaussianLobe({-2,-2,0},{1,1},1);
    Check(!negativeQ.rejected&&negativeQ.q<0&&negativeQ.value>1,"Do not add an original PSD or q>=0 rule");
    const auto wide=O::GaussianLobe({0,0,0},{0,0},16,true);
    Near(wide.value,O::ShaderWideMultiplier);
}
void Directions(){
    section="Fresnel and half-vector domains";
    Near(O::RetailFresnel({0,0},{0,0,1}),0);
    Near(O::RetailFresnel({0,0},{1,0,0}),1);
    Near(O::RetailFresnel({2,0},{1,0,0}),-1);
    Near(O::RetailFresnel({-1,0},{1,0,0}),32);
    Near(O::RetailDiffuse({0,0},{0,0,-1}),0);Near(O::RetailDiffuse({0,0},{0,0,2}),1);
    const auto view=O::NormalizeView({3,4,12});Near(view.x,3.0/13);Near(view.y,4.0/13);Near(view.z,12.0/13);
    const auto half=O::WarpedHalfSlope({0,0,1},{0.5,-0.25,1},{0,0,0},1,{0.1,0.2});
    Check(half.valid,"Valid half vector rejected");Near(half.value.x,0.15);Near(half.value.y,-0.325);
    Check(!O::WarpedHalfSlope({1,0,0},{0,0,0},{0,0,0},1,{0,0}).valid,"Horizontal half vector must use finite fallback");
    Check(!O::WarpedHalfSlope({0,0,1},{0,0,1},{0,0,0},0,{0,0}).valid,"Zero warped vector must use finite fallback");
    Check(!O::WarpedHalfSlope({1,0,0},{0,0,1e-10},{0,0,0},1,{0,0},1e-6).valid,"Candidate horizon threshold ignored");
    Check(O::WarpedHalfSlope({1,0,0},{0,0,1e-10},{0,0,0},1,{0,0},0).valid,"Exact nonzero horizon must remain without epsilon policy");
}
void Reflection(){
    section="reflection taps and gamma order";
    const auto uv=O::ProjectedReflectionUv(0.4,-0.8,2);
    Near(uv.x,-0.4);Near(uv.y,-0.3);
    const auto taps=O::ReflectionUvs({0.2,-0.4},{0.1,0.2,0.03},0.01);
    const double expected[4][2]={{0.82,0.82},{0.82,0.78},{0.78,0.86},{0.78,0.78}};
    for(unsigned i=0;i<4;++i){Near(taps[i].x,expected[i][0]);Near(taps[i].y,expected[i][1]);}
    const auto average=O::AverageReflectionLinear({{{1,0,0,0},{0,0.5,0,1},{0,1,0,0.5},{0,2,0,0.25}}});
    Near(average.rgb.x,std::pow(0.25,O::ShaderGamma));Near(average.rgb.y,std::pow(0.875,O::ShaderGamma));
    Near(average.rgb.z,0);Near(average.alpha,0.4375);
    Check(std::abs(average.rgb.x-0.25)>0.1,"Gamma applied before four-tap averaging");
    const auto encoded=O::EncodeLighting({0,0.25,4});
    Near(encoded.x,0);Near(encoded.y,std::pow(0.25,O::ShaderInverseGamma));Near(encoded.z,std::pow(4.0,O::ShaderInverseGamma));
    Check(FloatBits(O::ShaderGamma)==0x400ccccdu,"Original gamma literal changed");
    Check(FloatBits(O::ShaderInverseGamma)==0x3ee8ba2fu,"Original inverse-gamma literal changed");
    Check(FloatBits(O::ShaderLog2E)==0x3fb8aa3bu,"Original exponential literal changed");
    Check(FloatBits(O::ShaderWideMultiplier)==0x3ba3d70au,"Original wide-lobe literal changed");
}
void Malformed(){
    section="finite and parameter rejection";
    const auto nan=(std::numeric_limits<double>::quiet_NaN)(),inf=(std::numeric_limits<double>::infinity)();
    O::CandidateOpticsPolicy policy;O::Validate(policy);++checks;
    for(const double value:{nan,inf,-1.0,0.0,1e-7,17.0}){
        Reject([&](){auto p=policy;p.scale=value;O::Validate(p);});
    }
    for(const double value:{nan,inf,-1.0,0.0,1e-7,1e10}){
        Reject([&](){O::GaussianLobe({0,0,0},{0,0},value);});
    }
    Reject([&](){O::FromArray({{nan,0,0,0,0}});});
    Reject([&](){O::MixLayers({},{},{0,0},1);});
    Reject([&](){O::MixLayers({},{},{-1,2},1);});
    Reject([&](){O::WeightsFromBlendRG(-0.1,0.5,1);});
    Reject([&](){O::GaussianLobe({nan,0,0},{0,0},1);});
    Reject([&](){O::GaussianLobe({0,0,0},{inf,0},1);});
    Reject([&](){O::NormalizeView({0,0,0});});
    Reject([&](){O::RetailFresnel({nan,0},{0,0,1});});
    Reject([&](){O::ProjectedReflectionUv(0,0,0);});
    Reject([&](){O::ProjectedReflectionUv(inf,0,1);});
    Reject([&](){O::ReflectionUvs({1e7,0},{0,0,0},0);});
    Reject([&](){O::EncodeLighting({-0.1,0,0});});
    Reject([&](){O::EncodeLighting({nan,0,0});});
    Reject([&](){auto p=policy;p.uvScales[3]=inf;O::Validate(p);});
    Reject([&](){auto p=policy;p.horizontalEpsilon=-1;O::Validate(p);});
    Reject([&](){O::WarpedHalfSlope({0,0,1},{0,0,1},{0,0,0},inf,{0,0});});
}
}
int main(){try{Mixtures();Gaussian();Directions();Reflection();Malformed();
    std::printf("PASS_ORIGINAL_WATER_OPTICS checks=%u gaussian_cases=%u\n",checks,static_cast<unsigned>(sizeof(GoldenOpticsGaussians)/sizeof(GoldenOpticsGaussians[0])));return 0;
}catch(const std::exception& error){std::fprintf(stderr,"FAIL_OPTICS section=%s check=%u reason=%s\n",section,checks,error.what());return 1;}}
