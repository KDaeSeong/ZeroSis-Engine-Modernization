#pragma once
#include <array>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalForest {
constexpr unsigned TileTextures=4,RandomTreesPerTile=360,GriddedTreesPerTile=0;
constexpr float OverlayAlpha=0.60f,MinimumSpacing=1.33f,AlphaCutoff=0.1f;
constexpr unsigned InstancesPerBatch=90;
constexpr std::size_t MaxInstances=262144;
struct Vector {float x=0,y=0,z=0;};
using Colour=std::array<float,4>;
struct Instance {bool revealed=false;Vector translation;float scale=1;};
struct Batch {std::array<std::array<float,4>,InstancesPerBatch> transforms{};unsigned count=0;};
inline bool Finite(Vector value)noexcept{return std::isfinite(value.x)&&std::isfinite(value.y)&&std::isfinite(value.z);}
inline bool PassesAlpha(float alpha){
    if(!std::isfinite(alpha)||alpha<0||alpha>1)throw std::invalid_argument("Invalid original forest alpha");
    return alpha>=AlphaCutoff;
}
inline void ValidateColour(const Colour& colour){
    for(const auto value:colour)if(!std::isfinite(value)||value<0||value>1)
        throw std::invalid_argument("Invalid original forest colour");
}
inline std::vector<Batch> BuildBatches(const std::vector<Instance>& instances){
    if(instances.size()>MaxInstances)throw std::invalid_argument("Forest instance bound exceeded");
    std::vector<Batch> result;
    for(const auto& instance:instances){
        if(!instance.revealed)continue;
        if(!Finite(instance.translation)||!std::isfinite(instance.scale)||instance.scale<=0||instance.scale>1000)
            throw std::invalid_argument("Invalid known forest transform");
        if(result.empty()||result.back().count==InstancesPerBatch)result.emplace_back();
        auto& batch=result.back();batch.transforms[batch.count++]={{instance.translation.x,instance.translation.y,instance.translation.z,instance.scale}};
    }
    return result;
}
inline Vector Transform(Vector point,const Batch& batch,unsigned index){
    if(!Finite(point)||batch.count>InstancesPerBatch||index>=batch.count)
        throw std::invalid_argument("Invalid original forest vertex or instance index");
    const auto& transform=batch.transforms[index];
    for(const auto value:transform)if(!std::isfinite(value))throw std::invalid_argument("Nonfinite original forest transform");
    if(transform[3]<=0||transform[3]>1000)throw std::invalid_argument("Invalid original forest scale");
    const Vector result{point.x*transform[3]+transform[0],point.y*transform[3]+transform[1],point.z*transform[3]+transform[2]};
    if(!Finite(result))throw std::invalid_argument("Original forest transform overflow");
    return result;
}
inline Colour ChromaOverlay(const Colour& base,const Colour& overlay){
    ValidateColour(base);ValidateColour(overlay);
    const float baseU=(-0.147130f*base[0]-0.288860f*base[1])+0.436000f*base[2];
    const float baseV=(0.615000f*base[0]-0.514990f*base[1])-0.100010f*base[2];
    const float overlayU=(-0.147130f*overlay[0]-0.288860f*overlay[1])+0.436000f*overlay[2];
    const float overlayV=(0.615000f*overlay[0]-0.514990f*overlay[1])-0.100010f*overlay[2];
    const float u=overlay[3]*(overlayU-baseU)+baseU,v=overlay[3]*(overlayV-baseV)+baseV;
    return {{base[0]+1.139830f*v,(base[0]-0.394650f*u)-0.580600f*v,base[0]+2.032110f*u,base[3]}};
}
// Original compressed GR2 decoding and the original random placement stream
// are prerequisites for production submission, not replaced by invented trees.
}}
