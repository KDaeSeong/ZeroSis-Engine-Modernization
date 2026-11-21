#pragma once
namespace ZeroSisPresentation { namespace OriginalWater {
static const char ShaderSource[]=R"HLSL(
cbuffer Camera:register(b0){row_major float4x4 viewProjection;};
cbuffer Draw:register(b1){
    float4 placement; // camera-relative offset X/Z, unwrapped copy offset X/Z
    float4 mapInfo; // width/height/wrapX/wrapY
    float4 shade; // presentation time, height-world-scale, raw-height-offset, fog post-pass enabled
    float4 uvScales;
    float4 eye; // local camera eye XYZ, retail units per hex
    float4 motion; // candidate water and river translations
};
Texture2D<float4> WaterDepth:register(t0);
Texture2D<float4> WaterBumps:register(t1);
Texture2D<float4> WaterSky:register(t2);
Texture2D<float4> RiverAlpha:register(t3);
Texture2D<float4> RiverDiffuse:register(t4);
Texture2D<float4> RiverRough:register(t5);
Texture2D<float4> RiverSmooth:register(t6);
Texture2D<float4> CoastWave:register(t7);
Texture2D<float4> BankDiffuse:register(t8);
Texture2D<float4> BankEnd1:register(t9);
Texture2D<float4> BankEnd2:register(t10);
Texture2D<float4> BankHeight:register(t11);
Texture2D<float4> GenericBankDiffuse:register(t12);
Texture2D<float4> GenericBankSpecular:register(t13);
Texture2D<uint2> PlotState:register(t14);
SamplerState WrapSampler:register(s0);
SamplerState ClampSampler:register(s1);
struct V{float3 p:POSITION;float2 uv:TEXCOORD0;float kind:TEXCOORD1;float depth:TEXCOORD2;float flow:TEXCOORD3;};
struct P{float4 p:SV_POSITION;float2 world:TEXCOORD0;float2 uv:TEXCOORD1;float depth:TEXCOORD2;
    nointerpolation float kind:TEXCOORD3;nointerpolation float flow:TEXCOORD4;float3 local:TEXCOORD5;float2 canonical:TEXCOORD6;};
P vertexMain(V v){
    P p;p.local=v.p+float3(placement.x,0,placement.y);p.p=mul(float4(p.local,1),viewProjection);
    p.world=v.p.xz+placement.zw;p.canonical=v.p.xz;p.uv=v.uv;p.depth=v.depth;p.kind=v.kind;p.flow=v.flow;return p;
}
int RoundAway(float v){return v<0?-(int)floor(-v+0.5):(int)floor(v+0.5);}
int Wrapped(int value,int span){uint m=value<0?uint(-(value+1))+1u:uint(value);uint r=m%uint(span);return value<0&&r!=0?span-int(r):int(r);}
bool PlotAt(float2 world,out int2 cell){
    float row=-world.y/0.866025404,q=world.x-row*0.5;float3 f=float3(q,row,-q-row);
    int3 c=int3(RoundAway(f.x),RoundAway(f.y),RoundAway(f.z));float3 d=abs(float3(c)-f);
    if(d.x>d.y&&d.x>d.z)c.x=-c.y-c.z;else if(d.y>d.z)c.y=-c.x-c.z;else c.z=-c.x-c.y;
    cell=int2(c.x+(int)floor(c.y*0.5),c.y);
    if(mapInfo.z>0.5)cell.x=Wrapped(cell.x,(int)mapInfo.x);if(mapInfo.w>0.5)cell.y=Wrapped(cell.y,(int)mapInfo.y);
    return cell.x>=0&&cell.y>=0&&cell.x<(int)mapInfo.x&&cell.y<(int)mapInfo.y;
}
float4 pixelMain(P p):SV_Target0{
    int2 cell;if(!PlotAt(p.world,cell))discard;
    uint2 state=PlotState.Load(int3(cell,0));if(state.y==0)discard;
    // All material reads follow exact explored ownership. No ID/depth output.
    float2 retail=p.canonical*float2(1,-1)*eye.w;
    float translation=shade.x*motion.x;
    // These four UV symmetries are confirmed by the original Water VS.
    float2 a=retail*uvScales.x+translation;
    float2 b=retail*float2(-1,1)*uvScales.y+translation;
    float2 c=-retail*uvScales.z+translation;
    float2 d=retail*float2(1,-1)*uvScales.w+translation;
    float2 perturb=(WaterBumps.Sample(WrapSampler,a).rg+WaterBumps.Sample(WrapSampler,b).rg+
        WaterBumps.Sample(WrapSampler,c).rg+WaterBumps.Sample(WrapSampler,d).rg)*0.5-1;
    float3 n=normalize(float3(-perturb.x*0.18,1,-perturb.y*0.18));
    float3 towardEye=normalize(eye.xyz-p.local);
    // Candidate simple Fresnel replaces the deferred original LEAN covariance/Gaussian renderer.
    float fresnel=0.03+0.97*pow(1-saturate(dot(n,towardEye)),5);
    // Confirmed original lookup coordinate. Raw h reconstruction remains calibrated to the candidate terrain atlas.
    float u=1-saturate(4*p.depth);
    float4 deep=WaterDepth.SampleLevel(ClampSampler,float2(u,0),0);
    float3 sky=WaterSky.SampleLevel(ClampSampler,float2(saturate(n.x*0.5+0.5),saturate(reflect(-towardEye,n).y*0.5+0.5)),0).rgb;
    float3 colour=lerp(deep.rgb,sky,fresnel*0.7)*(0.75+0.25*n.y);float alpha=saturate(0.8+deep.a*0.2);
    if(p.kind>0.5){
        float2 along=float2(p.uv.x-shade.x*motion.y*p.flow,p.uv.y);
        float4 bank=lerp(BankDiffuse.Sample(WrapSampler,p.uv),GenericBankDiffuse.Sample(WrapSampler,p.uv),0.5);
        float4 cap=lerp(BankEnd1.Sample(WrapSampler,p.uv),BankEnd2.Sample(WrapSampler,p.uv),step(0.5,p.uv.y));
        float bankHeight=BankHeight.Sample(WrapSampler,p.uv).r;
        float glint=GenericBankSpecular.Sample(WrapSampler,p.uv).r;
        float across=saturate(p.uv.y);float bankEdge=smoothstep(0.25,0.48,abs(across-0.5));
        if(p.kind<1.5){
            float4 foam=CoastWave.Sample(WrapSampler,float2(p.uv.x-shade.x*motion.x,across));
            colour=lerp(bank.rgb,foam.rgb,saturate(p.depth));alpha=(0.15+foam.a*0.45)*(1-abs(across*2-1));
        }else{
            float4 river=RiverDiffuse.Sample(WrapSampler,along);
            float2 rough=(RiverRough.Sample(WrapSampler,along).rg+RiverSmooth.Sample(WrapSampler,along).rg)*0.5;
            colour=lerp(river.rgb*(0.8+rough.x*0.2),lerp(bank.rgb,cap.rgb,0.15),bankEdge);
            alpha=RiverAlpha.Sample(WrapSampler,along).a*(1-smoothstep(0.43,0.5,abs(across-0.5)));
        }
        colour=colour*(0.9+bankHeight*0.1)+glint*0.015;
    }
    float fog=shade.w>0.5||state.y==2?1.0:0.30;
    return float4(colour*colour*fog,saturate(alpha));
}
)HLSL";
}}
