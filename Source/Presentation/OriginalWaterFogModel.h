#pragma once
#include "OriginalWaterFogBinding.h"
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <utility>

namespace ZeroSisPresentation { namespace OriginalWaterFog {
struct Rgb {double r=0,g=0,b=0;};
struct Rgba {double r=0,g=0,b=0,a=0;};
struct Parameters {double reveal=1,visible=1,distance=0;Rgba overlay{};Rgb fog{};};
struct Result {Rgba colour{};bool processed=false;};
enum class Route {Clouds,Land,Water};
enum class Fragment {Ground,OpaqueWater,CoastOverlay,RiverOverlay,Unit};
inline void Require(bool value,const char* message){if(!value)throw std::invalid_argument(message);}
inline void Finite(double value){Require(std::isfinite(value),"Nonfinite water fog input");}
inline void Colour(Rgb value){Finite(value.r);Finite(value.g);Finite(value.b);}
inline void Colour(Rgba value){Colour(Rgb{value.r,value.g,value.b});Finite(value.a);}
inline void Unit(double value){Require(std::isfinite(value)&&value>=0&&value<=1,"Water fog scalar outside normalized domain");}
inline Rgb Mix(Rgb a,Rgb b,double factor){return {a.r+(b.r-a.r)*factor,a.g+(b.g-a.g)*factor,a.b+(b.b-a.b)*factor};}
inline Route SelectRoute(bool explored,unsigned fragment)noexcept{return !explored?Route::Clouds:fragment==SurfaceFragment?Route::Water:Route::Land;}
inline unsigned WriteFragment(unsigned oldValue,Fragment kind,bool depthPassed){
    if(!depthPassed)return oldValue;
    if(kind==Fragment::OpaqueWater)return SurfaceFragment;
    if(kind==Fragment::Ground||kind==Fragment::Unit)return OtherFragment;
    Require(kind==Fragment::CoastOverlay||kind==Fragment::RiverOverlay,"Unknown fog fragment kind");return oldValue;
}
// Input RGB is already WaterPS gamma encoded. Colour-only operations preserve
// input alpha exactly; no hardware blending equivalence is implied.
template<class Lut>Rgba Apply(Rgba encoded,const Parameters& p,Lut lut){
    Colour(encoded);Unit(encoded.a);Colour(p.overlay);Unit(p.overlay.a);Colour(p.fog);Unit(p.reveal);Unit(p.visible);Unit(p.distance);
    const Rgb over{p.overlay.r+(1-p.overlay.a)*encoded.r,p.overlay.g+(1-p.overlay.a)*encoded.g,p.overlay.b+(1-p.overlay.a)*encoded.b};
    const double gray=static_cast<double>(ReplacementGray);const auto base=Mix({gray,gray,gray},over,p.reveal);
    const auto transformed=lut(base);Colour(transformed);const auto mapped=Mix(base,transformed,p.reveal*(1-p.visible));
    const auto result=Mix(mapped,p.fog,p.distance);Colour(result);return {result.r,result.g,result.b,encoded.a};
}
template<class Fetch,class Lut>Result Guarded(bool explored,unsigned fragment,Rgba publicFallback,Fetch fetch,Lut lut){
    if(SelectRoute(explored,fragment)!=Route::Water){Colour(publicFallback);return {publicFallback,false};}
    const auto input=fetch();return {Apply(input.first,input.second,lut),true};
}
}}
