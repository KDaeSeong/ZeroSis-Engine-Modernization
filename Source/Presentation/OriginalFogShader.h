#pragma once
#include "OriginalWaterFogBinding.h"
namespace ZeroSisPresentation { namespace OriginalFog {
static const char ShaderSource[]=R"HLSL(
cbuffer Fog : register(b0) {
    row_major float4x4 inverseViewProjection;
    float4 viewport; // map width, height, global camera centre X/Z
    float4 mapInfo; // width, height, wrapX, wrapY
    float4 camera; // local camera eye XYZ, presentation seconds
    float4 distanceParameters; // height K, density, ramp row, retail units/hex
    float4 fogColour;
    float4 flow[3]; // scale, speed U/V, phase U (candidate)
    float4 phase; // phase V per layer, flow displacement (candidate)
    float4 waterOverlay; // neutral until the original overlay producer is bound
};
Texture2D<float4> SceneColour : register(t0); // raw encoded bytes, not an sRGB decode
Texture2D<float> SceneDepth : register(t1);
Texture2D<float4> MaskTexture : register(t2);
Texture2D<uint2> PlotState : register(t3); // exact state, independent of smooth mask
Texture2D<float4> Cloud1 : register(t4);
Texture2D<float4> Cloud2 : register(t5);
Texture2D<float4> Cloud3 : register(t6);
Texture2D<float4> FlowField : register(t7);
Texture2D<float4> FogDiffuse : register(t8);
Texture3D<float4> FowColourKey : register(t9);
Texture2D<float4> FogRamp : register(t10);
Texture2D<uint> WaterFragment : register(t11); // exact fragment class, never plot.water
SamplerState ClampSampler : register(s0);
SamplerState WrapSampler : register(s1);
SamplerState MaskSampler : register(s2);
float4 vertexMain(uint id:SV_VertexID):SV_POSITION {
    float2 uv=float2((id<<1)&2,id&2);
    return float4(uv*float2(2,-2)+float2(-1,1),0,1);
}
int RoundAway(float v){return v<0?-(int)floor(-v+0.5):(int)floor(v+0.5);}
int Wrapped(int value,int span){
    uint magnitude=value<0?uint(-(value+1))+1u:uint(value);
    uint r=magnitude%uint(span);
    return value<0 && r!=0?span-int(r):int(r);
}
bool PlotAt(float2 world,out int2 cell){
    float row=-world.y/0.866025404;
    float q=world.x-row*0.5;
    float3 f=float3(q,row,-q-row);
    int3 c=int3(RoundAway(f.x),RoundAway(f.y),RoundAway(f.z));
    float3 d=abs(float3(c)-f);
    if(d.x>d.y && d.x>d.z)c.x=-c.y-c.z;
    else if(d.y>d.z)c.y=-c.x-c.z;else c.z=-c.x-c.y;
    cell=int2(c.x+(int)floor(c.y*0.5),c.y);
    if(mapInfo.z>0.5)cell.x=Wrapped(cell.x,(int)mapInfo.x);
    if(mapInfo.w>0.5)cell.y=Wrapped(cell.y,(int)mapInfo.y);
    return cell.x>=0&&cell.y>=0&&cell.x<(int)mapInfo.x&&cell.y<(int)mapInfo.y;
}
float2 FlowUv(float2 world,int layer){
    return frac(world*flow[layer].x+camera.w*flow[layer].yz+float2(flow[layer].w,phase[layer]));
}
float3 Replacement(float2 world,float cloudMask){
    // Simple three-layer motion and flow displacement are explicit candidates.
    float2 displacement=(FlowField.Sample(WrapSampler,world/16.0).rg*2-1)*phase.w;
    float4 a=Cloud1.Sample(WrapSampler,FlowUv(world,0)+displacement);
    float4 b=Cloud2.Sample(WrapSampler,FlowUv(world,1)-displacement);
    float4 c=Cloud3.Sample(WrapSampler,FlowUv(world,2)+displacement.yx);
    float3 clouds=(a.rgb*a.a+b.rgb*b.a+c.rgb*c.a)/max(a.a+b.a+c.a,0.00001);
    float4 detail=FogDiffuse.Sample(WrapSampler,world/4.0+displacement);
    float3 base=fogColour.rgb*0.12;
    float amount=cloudMask<0.01?0:saturate(cloudMask)*(0.45+detail.a*0.55);
    return lerp(base,clouds*lerp(0.7,1.0,detail.rgb),amount);
}
float DistanceFactor(float3 local,float ndcY){
    // Retail Z-up delta and exact DXBC operation order, except the finite
    // horizontal-ray limit. Runtime K/density/row remain calibration candidates.
    float3 delta=(local-camera.xyz).xzy*float3(1,-1,1)*distanceParameters.w;
    float exponent;
    if(abs(delta.z)<0.0001){
        exponent=-distanceParameters.x*(0.6931471805599453*1.442695)*dot(delta,delta)*distanceParameters.y;
    }else{
        exponent=(1-exp2(delta.z*distanceParameters.x*1.442695))*dot(delta,delta)*distanceParameters.y/delta.z;
    }
    float amount=1-min(exp2(exponent*1.442695),1);
    return saturate(amount)*FogRamp.Sample(ClampSampler,float2(ndcY*0.5+0.5,distanceParameters.z)).r;
}
float4 WaterFogBase(float4 colour,float3 mask){
    // Original gamma has already been applied by WaterPS. Overlay is premultiplied.
    float3 over=waterOverlay.rgb+(1-waterOverlay.a)*colour.rgb;
    return float4(lerp(float3(0.4,0.4,0.4),over,mask.r),colour.a);
}
float4 WaterFogFinish(float4 colour,float3 transformed,float3 mask,float factor){
    float3 mapped=lerp(colour.rgb,transformed,mask.r*(1-mask.b));
    return float4(lerp(mapped,fogColour.rgb,factor),colour.a);
}
float4 SceneFog(float4 position,uint fragment) {
    int2 pixel=int2(position.xy);
    float4 output=0;
    // The underlay and source water were fogged before their alpha blend.
    // Repeating the colour LUT or distance fog on that composite is incorrect.
    [branch]if(fragment==2)output=SceneColour.Load(int3(pixel,0));
    else{
        float depth=SceneDepth.Load(int3(pixel,0));
        [branch]if(depth>=1)output=SceneColour.Load(int3(pixel,0));
        else{
            float2 ndc=float2(position.x/viewport.x*2-1,1-position.y/viewport.y*2);
            float4 homogeneous=mul(float4(ndc,depth,1),inverseViewProjection);
            float3 local=homogeneous.xyz/homogeneous.w;
            float2 world=local.xz+viewport.zw;
            int2 cell;
            [branch]if(!PlotAt(world,cell))output=SceneColour.Load(int3(pixel,0));
            else{
                uint2 state=PlotState.Load(int3(cell,0));
                float3 mask=MaskTexture.Sample(MaskSampler,float2(world.x/mapInfo.x,-world.y/(0.866025404*mapInfo.y))).rgb;
                // Exact state blocks scene and LUT reads for unknown cells.
                [branch]if(state.y==0){
                    float3 clouds=Replacement(world,mask.g);
                    output=float4(lerp(clouds,fogColour.rgb,DistanceFactor(local,ndc.y)),1);
                }else{
                    [branch]if(fragment==1){
                        float4 water=WaterFogBase(SceneColour.Load(int3(pixel,0)),mask);
                        float3 transformedWater=FowColourKey.Sample(ClampSampler,water.rgb).rgb;
                        output=WaterFogFinish(water,transformedWater,mask,DistanceFactor(local,ndc.y));
                    }else{
                        float3 terrain=SceneColour.Load(int3(pixel,0)).rgb;
                        float3 result=lerp(Replacement(world,mask.g),terrain,mask.r);
                        float3 transformed=FowColourKey.Sample(ClampSampler,result).rgb;
                        result=lerp(result,transformed,mask.r*(1-mask.b));
                        output=float4(lerp(result,fogColour.rgb,DistanceFactor(local,ndc.y)),1);
                    }
                }
            }
        }
    }
    return output;
}
float4 pixelMain(float4 position:SV_POSITION):SV_Target0 {
    return SceneFog(position,WaterFragment.Load(int3(int2(position.xy),0)));
}
struct UnderlayFogOutput{float4 colour:SV_Target0;uint fogClass:SV_Target1;};
UnderlayFogOutput underlayMain(float4 position:SV_POSITION){
    // This entry never reads WaterFragment, so its R8 view can be an output.
    UnderlayFogOutput result;result.colour=SceneFog(position,0);result.fogClass=2;return result;
}
)HLSL";
}}
