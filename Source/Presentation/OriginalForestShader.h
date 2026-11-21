#pragma once
namespace ZeroSisPresentation { namespace OriginalForest {
// ForestShader pass0 equations recovered from the pinned original SM5 DXBC.
// This is a compilable stage contract; production submission still requires
// verified GR2 mesh decoding and the original placement/binding inputs.
static const char ShaderSource[]=R"HLSL(
cbuffer ForestConstants:register(b1){float4 c[15];};
cbuffer ForestInstances:register(b7){float4 instances[90];};
Texture2D ForestDiffuse:register(t0);Texture2D ForestOverlay:register(t1);
Texture2D SceneOverlay:register(t3);Texture2D FogRamp:register(t4);
Texture3D ForestColourKey:register(t5);Texture2D FogMask:register(t6);
Texture2D Replacement:register(t7);Texture3D FowColourKey:register(t8);
SamplerState DiffuseSampler:register(s0);SamplerState OverlaySampler:register(s1);
SamplerState SceneSampler:register(s3);SamplerState RampSampler:register(s4);
SamplerState ColourSampler:register(s5);SamplerState MaskSampler:register(s6);
SamplerState ReplacementSampler:register(s7);SamplerState FowSampler:register(s8);
struct V{float3 position:POSITION;float3 normal:NORMAL;float2 uv:TEXCOORD0;uint4 instance:BLENDINDICES;};
struct P{float4 position:SV_POSITION;float4 texcoord:TEXCOORD0;float3 centre:TEXCOORD1;float4 fog:TEXCOORD2;};
P vertexMain(V input){
    P output;float4 instance=instances[input.instance.x];
    float3 world=input.position*instance.w+instance.xyz;
    float4 clip=(world.y*c[1]+world.x*c[0])+world.z*c[2]+c[3];
    output.position=clip;output.centre=instance.xyz;
    output.texcoord=float4(input.uv,(world.xy+c[8].zw)*c[8].xy);
    float2 mask=(world.y*c[5].xy+world.x*c[4].xy)+world.z*c[6].xy+c[7].xy;
    output.fog=float4(mask*float2(0.5,-0.5)-0.5,clip.xy/clip.w);return output;
}
float4 pixelMain(P input):SV_Target0{
    float2 mask=FogMask.Sample(MaskSampler,input.fog.xy).xz;
    // The original rejects mask R==0. This stage also orders that guard before
    // material reads; the owner must submit only exact-known forest instances.
    if(mask.x==0)discard;
    float4 colour=ForestDiffuse.Sample(DiffuseSampler,input.texcoord.xy);
    if(colour.a<0.1)discard;
    float4 overlay=ForestOverlay.Sample(OverlaySampler,input.centre.xy*0.001);
    const float3 chromaU=float3(-0.147130,-0.288860,0.436000),chromaV=float3(0.615000,-0.514990,-0.100010);
    float u=lerp(dot(colour.rgb,chromaU),dot(overlay.rgb,chromaU),overlay.a);
    float v=lerp(dot(colour.rgb,chromaV),dot(overlay.rgb,chromaV),overlay.a);
    float3 rgb=float3(colour.r+1.139830*v,colour.r-0.394650*u-0.580600*v,colour.r+2.032110*u);
    rgb=ForestColourKey.Sample(ColourSampler,rgb).rgb;
    float4 scene=SceneOverlay.Sample(SceneSampler,input.position.xy/c[9].xy);
    rgb=rgb*(1-scene.a*c[10].x)+scene.rgb*c[10].x;
    rgb=lerp(Replacement.Sample(ReplacementSampler,input.texcoord.zw).rgb,rgb,mask.x);
    rgb=lerp(rgb,FowColourKey.Sample(FowSampler,rgb).rgb,mask.x*(1-mask.y));
    float ramp=FogRamp.Sample(RampSampler,float2(input.fog.w*0.5+0.5,c[14].w)).r;
    float3 delta=input.centre-c[12].xyz;float distanceSquared=dot(delta,delta);
    float expHeight=exp(delta.z*c[14].x);
    float amount=1-min(exp((1-expHeight)*distanceSquared*c[14].y/delta.z),1);
    return float4(lerp(rgb,c[13].rgb,amount*ramp),colour.a);
}
)HLSL";
}}
