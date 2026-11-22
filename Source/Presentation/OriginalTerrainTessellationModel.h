#pragma once
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalTerrainTessellation {
using Basis=std::array<std::array<float,4>,4>;
using Heights=std::array<float,16>;
struct Sample {bool available=false;float height=0;};

// Retail TerrainShader cb1[10..13], recorded in claude_geometry/basis_retail_probe.json.
// Rows multiply t^3, t^2, t, 1. Columns follow the four consecutive controls.
inline constexpr Basis RetailBasis() noexcept {
    return {{{{-0.125f,  0.875f, -0.875f, 0.125f}},
             {{ 0.375f, -1.500f,  1.125f, 0.000f}},
             {{-0.375f,  0.000f,  0.375f, 0.000f}},
             {{ 0.125f,  0.750f,  0.125f, 0.000f}}}};
}

inline void ValidateBasis(const Basis& basis){
    for(const auto& row:basis)for(const auto value:row)
        if(!std::isfinite(value)||std::abs(value)>1000000)
            throw std::invalid_argument("Invalid original terrain bicubic basis");
}
inline float Dot(const std::array<float,4>& a,const std::array<float,4>& b) noexcept {
    return ((a[0]*b[0]+a[1]*b[1])+a[2]*b[2])+a[3]*b[3];
}
inline float Evaluate(const Heights& controls,const Basis& basis,float u,float v){
    if(!std::isfinite(u)||!std::isfinite(v)||u<0||u>1||v<0||v>1)
        throw std::invalid_argument("Invalid terrain domain coordinate");
    ValidateBasis(basis);
    for(const auto height:controls)if(!std::isfinite(height)||std::abs(height)>1000000)
        throw std::invalid_argument("Invalid terrain domain control height");
    const float u2=u*u,u3=u2*u,v2=v*v,v3=v2*v;
    std::array<float,4> horizontal{};
    for(unsigned axis=0;axis<4;++axis){
        float value=u2*basis[1][axis];value=basis[0][axis]*u3+value;
        value=basis[2][axis]*u+value;horizontal[axis]=value+basis[3][axis];
    }
    std::array<float,4> rows{};
    for(unsigned row=0;row<4;++row)
        rows[row]=Dot(horizontal,{{controls[row*4],controls[row*4+1],controls[row*4+2],controls[row*4+3]}});
    const std::array<float,4> vertical{{Dot(basis[0],rows),Dot(basis[1],rows),Dot(basis[2],rows),Dot(basis[3],rows)}};
    const float result=Dot(vertical,{{v3,v2,v,1}});
    if(!std::isfinite(result))throw std::invalid_argument("Nonfinite terrain bicubic result");
    return result;
}
inline Sample EvaluateKnown(const Heights& controls,const std::array<std::uint8_t,16>& known,
                            const Basis& basis,float u,float v){
    // Deny the whole footprint before reading any potentially private height.
    bool missing=false;
    for(const auto value:known){
        if(value>1)throw std::invalid_argument("Invalid terrain domain known state");
        missing=missing||value==0;
    }
    if(missing)return {};
    return {true,Evaluate(controls,basis,u,v)};
}
inline unsigned IntegerFactor(float factor){
    if(!std::isfinite(factor)||factor<1||factor>64)
        throw std::invalid_argument("Invalid terrain integer tessellation factor");
    return static_cast<unsigned>(std::ceil(factor));
}
}}
