#pragma once

// CPU reference for the pinned original Water PS operations. This header has
// no graphics, SDK, RNG, clock or file dependencies. Runtime constants and the
// LEAN-header-scale binding remain explicit candidates.
#include <algorithm>
#include <array>
#include <cmath>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalWaterOptics {

constexpr double ShaderLog2E=static_cast<double>(1.442695f);
constexpr double ShaderGamma=static_cast<double>(2.2f);
// The DXBC literal is 0x3ee8ba2f, not the rounded decimal 0.454545f and not
// float(1/float(2.2)). Keep the recorded original coefficient.
constexpr double ShaderInverseGamma=0.4545454680919647216796875;
constexpr double ShaderWideMultiplier=static_cast<double>(0.005f);

struct Vec2 {double x=0,y=0;};
struct Vec3 {double x=0,y=0,z=0;};
struct Rgba {double r=0,g=0,b=0,a=1;};
struct Moments5 {double meanX=0,meanY=0,xx=0,yy=0,xy=0;};
struct Symmetric2 {double xx=0,yy=0,xy=0;};
struct Mixture {Vec2 mean;Symmetric2 second,covariance;Vec2 scaledWeights;};
struct GaussianResult {double value=0,q=0,determinant=0;bool rejected=true;};
struct HalfSlope {Vec2 value;bool valid=false;};
struct LinearReflection {Vec3 rgb;double alpha=0;};

struct CandidateOpticsPolicy {
    // File outputScale -> original cb1[13].x is a compatibility inference.
    double scale=static_cast<double>(0.33f);
    double primaryK=64,secondaryK=32,reflectionStrength=0.12;
    std::array<double,4> uvScales={{1.0/512,1.0/704,1.0/960,1.0/384}};
    double uvTranslation=0.01,horizontalEpsilon=0.000001;
    Vec3 primaryWarpOrigin{},secondaryWarpOrigin{};
    double primaryWarpMix=1,secondaryWarpMix=1;
};

namespace Detail {
inline void Require(bool value,const char* reason){if(!value)throw std::invalid_argument(reason);}
inline bool Finite(double value,double bound=1000000){return std::isfinite(value)&&std::abs(value)<=bound;}
inline void Vector(Vec2 value,double bound=1000000){Require(Finite(value.x,bound)&&Finite(value.y,bound),"Invalid optics vector2");}
inline void Vector(Vec3 value,double bound=1000000){Require(Finite(value.x,bound)&&Finite(value.y,bound)&&Finite(value.z,bound),"Invalid optics vector3");}
inline void Sample(Moments5 value){Require(Finite(value.meanX)&&Finite(value.meanY)&&Finite(value.xx)&&Finite(value.yy)&&Finite(value.xy),"Invalid decoded LEAN moments");}
inline void Covariance(Symmetric2 value){Require(Finite(value.xx,1e24)&&Finite(value.yy,1e24)&&Finite(value.xy,1e24),"Invalid optics covariance");}
inline void Scale(double value){Require(std::isfinite(value)&&value>=0.000001&&value<=16,"Invalid original optics scale");}
inline void K(double value){Require(std::isfinite(value)&&value>=0.000001&&value<=1000000000,"Invalid original optics lobe parameter");}
inline double ColourPower(double value,double exponent){
    Require(std::isfinite(value)&&value>=0&&value<=1e100,"Invalid original optics RGB domain");
    return value==0?0:std::exp2(std::log2(value)*exponent);
}
}

inline Moments5 FromScalars(double meanX,double meanY,double xx,double yy,double xy){
    const Moments5 result{meanX,meanY,xx,yy,xy};Detail::Sample(result);return result;
}
inline Moments5 FromArray(const std::array<double,5>& value){return FromScalars(value[0],value[1],value[2],value[3],value[4]);}
inline void Validate(const CandidateOpticsPolicy& policy){
    Detail::Scale(policy.scale);Detail::K(policy.primaryK);Detail::K(policy.secondaryK);
    Detail::Require(Detail::Finite(policy.reflectionStrength)&&policy.reflectionStrength>=0&&
        policy.reflectionStrength<=16&&Detail::Finite(policy.uvTranslation)&&
        std::isfinite(policy.horizontalEpsilon)&&policy.horizontalEpsilon>=0&&policy.horizontalEpsilon<=0.01,
        "Invalid candidate optics policy");
    for(const auto value:policy.uvScales)Detail::Require(Detail::Finite(value)&&std::abs(value)<=4096,"Invalid candidate optics UV scale");
    Detail::Vector(policy.primaryWarpOrigin);Detail::Vector(policy.secondaryWarpOrigin);
    Detail::Require(Detail::Finite(policy.primaryWarpMix)&&Detail::Finite(policy.secondaryWarpMix),"Invalid candidate view warp");
}
inline Vec2 NormalizedLayerWeights(double first,double second,double scale){
    Detail::Scale(scale);
    Detail::Require(Detail::Finite(first)&&Detail::Finite(second)&&first>=0&&second>=0&&first+second>0,
        "Invalid nonnegative optics layer weights");
    const double sum=first+second;
    return {first/sum/scale,second/sum/scale};
}
inline Vec2 WeightsFromBlendRG(double red,double green,double scale){
    Detail::Require(std::isfinite(red)&&std::isfinite(green)&&red>=0&&red<=1&&green>=0&&green<=1,"Invalid original water blend sample");
    const double x=2*red-1,y=2*green-1;
    return NormalizedLayerWeights(x-y+2,-x-y+2,scale);
}
inline Mixture MixLayers(Moments5 first,Moments5 second,Vec2 weights,double scale){
    Detail::Sample(first);Detail::Sample(second);
    const auto w=NormalizedLayerWeights(weights.x,weights.y,scale);
    const Vec2 a{w.x*first.meanX,w.x*first.meanY},b{w.y*second.meanX,w.y*second.meanY};
    Mixture result;result.scaledWeights=w;result.mean={a.x+b.x,a.y+b.y};
    // Keep the shader's raw-second-moment construction, including layer cross
    // products, before subtracting the mixed mean outer product.
    result.second={w.x*w.x*first.xx+w.y*w.y*second.xx+2*a.x*b.x,
                   w.x*w.x*first.yy+w.y*w.y*second.yy+2*a.y*b.y,
                   w.x*w.x*first.xy+w.y*w.y*second.xy+a.x*b.y+a.y*b.x};
    result.covariance={result.second.xx-result.mean.x*result.mean.x,
                       result.second.yy-result.mean.y*result.mean.y,
                       result.second.xy-result.mean.x*result.mean.y};
    Detail::Vector(result.mean,1e12);Detail::Covariance(result.covariance);return result;
}
inline GaussianResult GaussianLobe(Symmetric2 covariance,Vec2 halfSlope,double k,bool wide=false){
    Detail::Covariance(covariance);Detail::Vector(halfSlope,1e12);Detail::K(k);
    const double diagonal=(wide?16.0:1.0)/k;
    const double a=covariance.xx+diagonal,d=covariance.yy+diagonal,b=covariance.xy;
    GaussianResult result;result.determinant=a*d-b*b;
    // The original computes invalid intermediate divisions/sqrt before movc.
    // Early rejection is a finite CPU safety policy outside the valid domain.
    if(result.determinant<=0)return result;
    result.q=(halfSlope.x*halfSlope.x*d+halfSlope.y*(a*halfSlope.y-2*b*halfSlope.x))*0.5/result.determinant;
    Detail::Require(std::isfinite(result.q),"Nonfinite original optics exponent");
    if(result.q>=16)return result;
    result.value=std::exp2(result.q*(-ShaderLog2E))/std::sqrt(result.determinant);
    if(wide)result.value*=ShaderWideMultiplier;
    Detail::Require(std::isfinite(result.value),"Nonfinite original optics lobe");result.rejected=false;return result;
}
inline Vec3 NormalizeView(Vec3 value){
    Detail::Vector(value);const double length=std::sqrt(value.x*value.x+value.y*value.y+value.z*value.z);
    Detail::Require(length>0,"Zero original optics view vector");return {value.x/length,value.y/length,value.z/length};
}
inline HalfSlope WarpedHalfSlope(Vec3 normalizedView,Vec3 light,Vec3 origin,double amount,Vec2 mean,double horizontalEpsilon=0){
    Detail::Vector(normalizedView);Detail::Vector(light);Detail::Vector(origin);Detail::Vector(mean,1e12);
    Detail::Require(Detail::Finite(amount)&&std::isfinite(horizontalEpsilon)&&horizontalEpsilon>=0&&horizontalEpsilon<=0.01,
        "Invalid original optics half vector policy");
    Vec3 warp{origin.x+amount*(normalizedView.x-origin.x),origin.y+amount*(normalizedView.y-origin.y),
              origin.z+amount*(normalizedView.z-origin.z)};
    const double length=std::sqrt(warp.x*warp.x+warp.y*warp.y+warp.z*warp.z);
    if(length==0)return {};
    warp={warp.x/length+light.x,warp.y/length+light.y,warp.z/length+light.z};
    if(std::abs(warp.z)<=horizontalEpsilon)return {};
    const Vec2 value{warp.x/warp.z-mean.x,warp.y/warp.z-mean.y};
    Detail::Vector(value,1e12);return {value,true};
}
inline double RetailFresnel(Vec2 mean,Vec3 normalizedView){
    Detail::Vector(mean,1e12);Detail::Vector(normalizedView);
    // N=(mean.x,mean.y,1) is not normalised; there is no clamp or F0 here.
    const double base=1-(mean.x*normalizedView.x+mean.y*normalizedView.y+normalizedView.z);
    const double square=base*base,fourth=square*square;const double result=base*fourth;
    Detail::Require(std::isfinite(result),"Nonfinite original optics Fresnel");return result;
}
inline double RetailDiffuse(Vec2 mean,Vec3 light){
    Detail::Vector(mean,1e12);Detail::Vector(light);
    return (std::max)(0.0,(std::min)(1.0,mean.x*light.x+mean.y*light.y+light.z));
}
inline Vec2 ProjectedReflectionUv(double clipX,double clipY,double clipW){
    Detail::Require(Detail::Finite(clipX)&&Detail::Finite(clipY)&&Detail::Finite(clipW)&&clipW!=0,
        "Invalid original reflection projection");
    const Vec2 result{clipX/clipW*0.5-0.5,clipY/clipW*(-0.5)-0.5};
    Detail::Vector(result);return result;
}
inline std::array<Vec2,4> ReflectionUvs(Vec2 projected,Symmetric2 covariance,double secondaryDeterminant){
    Detail::Vector(projected);Detail::Covariance(covariance);
    Detail::Require(Detail::Finite(secondaryDeterminant),"Invalid original reflection determinant");
    const Vec2 base{projected.x+6*covariance.xx,projected.y+6*covariance.yy};
    const auto tap=[&](double x,double y){const Vec2 value{base.x+x*secondaryDeterminant,base.y+y*secondaryDeterminant};
        Detail::Vector(value);return value;};
    // The asymmetric third Y offset is present in the pinned original PS2.
    return {{tap(2,2),tap(2,-2),tap(-2,6),tap(-2,-2)}};
}
inline LinearReflection AverageReflectionLinear(const std::array<Rgba,4>& taps){
    for(const auto tap:taps)Detail::Require(Detail::Finite(tap.r)&&Detail::Finite(tap.g)&&Detail::Finite(tap.b)&&Detail::Finite(tap.a),
        "Invalid original reflection sample");
    const auto average=[&](double Rgba::*component){
        double value=taps[0].*component*0.25+taps[1].*component*0.25;
        value=taps[2].*component*0.25+value;value=taps[3].*component*0.25+value;return value;};
    return {{Detail::ColourPower(average(&Rgba::r),ShaderGamma),Detail::ColourPower(average(&Rgba::g),ShaderGamma),
             Detail::ColourPower(average(&Rgba::b),ShaderGamma)},average(&Rgba::a)};
}
inline Vec3 EncodeLighting(Vec3 linear){return {Detail::ColourPower(linear.x,ShaderInverseGamma),
    Detail::ColourPower(linear.y,ShaderInverseGamma),Detail::ColourPower(linear.z,ShaderInverseGamma)};}

}}
