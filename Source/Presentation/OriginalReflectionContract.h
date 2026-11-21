#pragma once
// Retail Raw reflection classes and WaterShader resource/sampler contract.
// Runtime matrices, plane and missing scene providers remain separate inputs.
#include <array>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalReflection {
constexpr unsigned TypelessRgba8Format=27,UnormRgba8Format=28,SrgbRgba8Format=29;
constexpr unsigned ReflectionMapWaterSlot=4;
constexpr unsigned LinearFilter=21,WrapAddress=1,SamplerIndex=0;
enum class Scene:unsigned {Units=0x40,Wonders=0x20,Landmarks=0x02,Ice=0x01};
constexpr unsigned SceneMask=0x63;
constexpr std::array<Scene,4> DrawOrder{{Scene::Units,Scene::Wonders,Scene::Landmarks,Scene::Ice}};
struct Plan {unsigned requested=0,available=0,draw=0,missing=0;};
inline Plan MakePlan(unsigned requested,unsigned available){
    if((requested|available)&~SceneMask)throw std::invalid_argument("Unknown original reflection scene class");
    return {requested,available,requested&available,requested&~available};
}
inline bool Includes(const Plan& plan,Scene scene)noexcept{return (plan.draw&static_cast<unsigned>(scene))!=0;}
constexpr bool ReflectionSrvDecodesSrgb=false;
// WaterPS explicitly applies RGB^2.2 after averaging encoded Raw reflection taps.
// Terrain's final t9 consumes a separate static DDS without this conversion.
constexpr bool WaterConsumerExplicitGamma=true,TerrainConsumerExplicitGamma=false;
}}
