#pragma once
namespace ZeroSisPresentation { namespace OriginalLightingField {
// Recovered retail path: mixed material-height -> NormalCalculate, cardinal
// offsets and strength16 are confirmed. Our resolution,half cache,mip0 and
// sampler/texel-coordinate choices remain explicit implementation candidates.
static const char HeightShaderSource[]=R"HLSL(
cbuffer Field : register(b4) {
    float4 materials[8]; // scale, expanded projection, height-presence, unused
    float4 origin; // canonical chunk column,row,world units per hex,active slots
    float4 parameters; // normal strength,map width,map height,wrap flags
    float4 worldAdapter; // original height origin,original Y metric,unused,unused
};
Texture2D Diffuse[8] : register(t0);
Texture2D HeightMap[8] : register(t8);
Texture2D<uint> Known : register(t16);
SamplerState RawWrap : register(s0);
struct V {float3 p:POSITION;float2 uv:TEXCOORD0;float4 w0:TEXCOORD2;float4 w1:TEXCOORD3;};
struct P {float4 p:SV_POSITION;float2 uv:TEXCOORD0;float height:TEXCOORD1;float4 w0:TEXCOORD2;float4 w1:TEXCOORD3;};
P vertexMain(V v){
    P p;float2 clip=(v.uv*64+2)/68;
    p.p=float4(clip*float2(2,-2)+float2(-1,1),0,1);p.uv=v.uv;p.height=v.p.y;p.w0=v.w0;p.w1=v.w1;return p;
}
float pixelMain(P p):SV_Target0{
    int2 at=int2(p.p.xy);if(Known.Load(int3(at,0))==0)return 0;
    float weights[8]={p.w0.x,p.w0.y,p.w0.z,p.w0.w,p.w1.x,p.w1.y,p.w1.z,p.w1.w};
    // Match the CPU producer's canonical callback coordinates for wrap halos.
    float2 tile=origin.xy+p.uv;uint wrapFlags=(uint)parameters.w;
    if((wrapFlags&1)!=0)tile.x-=floor(tile.x/parameters.y)*parameters.y;
    if((wrapFlags&2)!=0)tile.y-=floor(tile.y/parameters.z)*parameters.z;
    float3 world=float3(tile.x*origin.z,tile.y*worldAdapter.y*origin.z,p.height*origin.z+worldAdapter.x);
    float total=0,height=0;
    [unroll]for(int i=0;i<8;++i){
        if(i<(int)origin.w && weights[i]>0.01){
            float4 material=materials[i];float2 uv;
            if(material.y<0.5)uv=world.xy*material.x*0.33;
            else if(material.y<1.5)uv=world.xz*material.x*0.66;
            else uv=world.yz*material.x*0.66;
            // Explicit mip0 candidate, preserving raw UNORM alpha and height.
            float a=Diffuse[i].SampleLevel(RawWrap,uv,0).a,a2=a*a,a4=a2*a2,W=a4*a4*weights[i];
            float h=material.z>0.5?HeightMap[i].SampleLevel(RawWrap,uv,0).r:(material.z< -0.5?0.5:0);
            total+=W;height+=W*h;
        }
    }
    return total>0.00000001?height/total:0;
}
)HLSL";
static const char NormalShaderSource[]=R"HLSL(
cbuffer Field : register(b4) {
    float4 materials[8];float4 origin;float4 parameters;float4 worldAdapter;
};
Texture2D<float> Height : register(t0);
Texture2D<uint> Known : register(t1);
struct P {float4 p:SV_POSITION;};
P vertexMain(uint id:SV_VertexID){
    float2 uv=float2((id<<1)&2,id&2);P p;p.p=float4(uv*float2(2,-2)+float2(-1,1),0,1);return p;
}
float Tap(int2 at,float center){if(Known.Load(int3(at,0))==0)return center;return Height.Load(int3(at,0));}
float4 pixelMain(P p):SV_Target0{
    int2 c=int2(p.p.xy)+int2(1,1);
    if(Known.Load(int3(c,0))==0)return float4(0.5,0.5,1,0);
    float center=Height.Load(int3(c,0));
    float left=Tap(c+int2(-1,0),center),nw=Tap(c+int2(-1,-1),center),ne=Tap(c+int2(1,-1),center),right=Tap(c+int2(1,0),center);
    float sw=Tap(c+int2(-1,1),center),se=Tap(c+int2(1,1),center),north=Tap(c+int2(0,-1),center),south=Tap(c+int2(0,1),center);
    float sx=(nw-ne+2*left)+(sw-se-2*right),sy=(nw+ne+2*north)+(-sw-se-2*south);
    float3 normal=normalize(float3(-parameters.x*sx,parameters.x*sy,4));
    return float4(normal*0.5+0.5,0);
}
)HLSL";
}}
