#pragma once
namespace ZeroSisPresentation { namespace OriginalIce {
// Recovered IceShader VS only. No guessed pixel shader or fracture mesh is
// supplied. The original PS remains pinned disassembly evidence.
inline const char* VertexShaderSource()noexcept{return R"ICE(
cbuffer IceConstants : register(b1) {float4 I[14];}
struct IceInput {float2 position:TEXCOORD0;float4 normalHeight:TEXCOORD1;};
struct IceOutput {
    float3 normal:TEXCOORD0;float3 world:TEXCOORD1;float3 toCamera:TEXCOORD2;
    float2 clipXY:TEXCOORD3;float2 maskUv:TEXCOORD4;float2 unexploredUv:TEXCOORD5;
    float4 clip:SV_Position;
};
IceOutput OriginalIceVS(IceInput input){
    IceOutput output;
    output.normal=input.normalHeight.xyz*2-1;
    float3 world;
    world.xy=(input.position*.5+.5)*(I[5].xy-I[4].xy)+I[4].xy;
    world.z=input.normalHeight.w*I[6].x+I[7].x;
    output.world=world;output.toCamera=I[12].xyz-world;
    float2 mask=world.y*I[9].xy+world.x*I[8].xy+world.z*I[10].xy+I[11].xy;
    output.maskUv=mask*float2(.5,-.5)-.5;
    output.clip=world.y*I[1]+world.x*I[0]+world.z*I[2]+I[3];
    output.clipXY=output.clip.xy/output.clip.w;
    output.unexploredUv=(world.xy+I[13].zw)*I[13].xy;
    return output;
}
)ICE";}
}}
