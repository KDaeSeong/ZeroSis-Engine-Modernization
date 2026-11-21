#pragma once
namespace ZeroSisPresentation { namespace OriginalScreenLighting {
// Included before final terrain. t44 adapts original TerrainShader t9's static
// specscreenmap DDS, not WaterShader's dynamic Raw reflection texture.
static const char ShaderSource[]=R"HLSL(
cbuffer OriginalScreenReflection : register(b6) {
    float4 screenReflectionViewport; // width,height,1/width,1/height
    float4 screenReflectionFlags; // available,diffuse,specular,reserved-zero
};
Texture2D<float4> ScreenReflection : register(t44);
SamplerState ScreenReflectionSampler : register(s5);
float2 OriginalScreenReflectionUv(float2 pixel) {
    return float2(pixel.x*screenReflectionViewport.z,1-pixel.y*screenReflectionViewport.w);
}
float3 ReadOriginalScreenReflection(float2 pixel,bool revealed) {
    if(!revealed || screenReflectionFlags.x<0.5)return 0;
    return max(ScreenReflection.Sample(ScreenReflectionSampler,OriginalScreenReflectionUv(pixel)).rgb,0);
}
float3 CombineOriginalScreenReflection(float3 diffuseCache,float3 specularCache,float2 pixel,bool revealed) {
    if(!revealed)return 0;
    float3 diffuse=screenReflectionFlags.y>0.5?diffuseCache:0;
    if(screenReflectionFlags.z<0.5)return diffuse;
    float3 linearColour=pow(max(specularCache,0),2.2000000476837158203125)*
        ReadOriginalScreenReflection(pixel,revealed)+pow(max(diffuse,0),2.2000000476837158203125);
    return pow(max(linearColour,0),0.4545454680919647216796875);
}
)HLSL";
}}
