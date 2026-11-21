#pragma once
namespace ZeroSisPresentation { namespace OriginalDynamicShadow {
// Prefix for both receivers. DYNAMIC_SHADOW_SLOT is t43 for terrain and t11
// for water. The private producer and all receivers share the same b5 layout.
static const char SamplingSource[]=R"HLSL(
cbuffer DynamicShadow:register(b5){row_major float4x4 shadowViewProjection;
    float4 shadowPlacement,shadowMapInfo,dynamicShadowInfo;};
Texture2D<float> DynamicShadowDepth:register(DYNAMIC_SHADOW_SLOT);
float SampleDynamicShadow(float3 world){
    if(dynamicShadowInfo.x<0.5)return 0;
    float4 projected=mul(float4(world,1),shadowViewProjection);
    if(!all(isfinite(projected))||projected.w<=0)return 0;
    float3 p=projected.xyz/projected.w;
    if(any(abs(p.xy)>1)||p.z<0||p.z>1)return 0;
    float2 at=(p.xy*float2(0.5,-0.5)+0.5)*dynamicShadowInfo.y-0.5;
    int2 origin=int2(floor(at));float2 fraction=frac(at);float result=0;
    [unroll]for(int y=0;y<2;++y)[unroll]for(int x=0;x<2;++x){
        int2 tap=origin+int2(x,y);if(any(tap<0)||any(tap>=(int)dynamicShadowInfo.y))continue;
        float depth=DynamicShadowDepth.Load(int3(tap,0));
        if(p.z-dynamicShadowInfo.z>depth)result+=(x?fraction.x:1-fraction.x)*(y?fraction.y:1-fraction.y);
    }
    return saturate(result)*dynamicShadowInfo.w;
}
)HLSL";
static const char ProducerSource[]=R"HLSL(
cbuffer DynamicShadow:register(b5){row_major float4x4 shadowViewProjection;
    float4 shadowPlacement,shadowMapInfo,dynamicShadowInfo;};
Texture2D<uint2> ShadowPlotState:register(t0);
struct V{float3 p:POSITION;};
struct P{float4 p:SV_POSITION;float2 world:TEXCOORD0;};
P groundVertex(V v){P p;float3 world=v.p+float3(shadowPlacement.x,0,shadowPlacement.y);
    p.p=mul(float4(world,1),shadowViewProjection);p.world=float2(shadowPlacement.z+v.p.x,shadowPlacement.w-v.p.z/0.866025404);return p;}
int RoundAway(float v){return v<0?-(int)floor(-v+0.5):(int)floor(v+0.5);}
int Wrapped(int v,int span){uint m=v<0?uint(-(v+1))+1u:uint(v);uint r=m%uint(span);return v<0&&r!=0?span-int(r):int(r);}
void groundPixel(P p){
    float q=p.world.x-p.world.y*0.5;float3 f=float3(q,p.world.y,-q-p.world.y);
    int3 c=int3(RoundAway(f.x),RoundAway(f.y),RoundAway(f.z));float3 d=abs(float3(c)-f);
    if(d.x>d.y&&d.x>d.z)c.x=-c.y-c.z;else if(d.y>d.z)c.y=-c.x-c.z;else c.z=-c.x-c.y;
    int2 cell=int2(c.x+(int)floor(c.y*0.5),c.y);
    if(shadowMapInfo.z>0.5)cell.x=Wrapped(cell.x,(int)shadowMapInfo.x);
    if(shadowMapInfo.w>0.5)cell.y=Wrapped(cell.y,(int)shadowMapInfo.y);
    if(any(cell<0)||cell.x>=(int)shadowMapInfo.x||cell.y>=(int)shadowMapInfo.y)discard;
    if(ShadowPlotState.Load(int3(cell,0)).y==0)discard;
}
float4 unitVertex(V v):SV_POSITION{return mul(float4(v.p,1),shadowViewProjection);}
)HLSL";
}}
