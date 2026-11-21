#pragma once
namespace ZeroSisPresentation { namespace OriginalWater { namespace Surface {
static const char ShaderSource[]=R"HLSL(
cbuffer Camera:register(b0){row_major float4x4 viewProjection;};
cbuffer Surface:register(b1){
    row_major float4x4 reflectionViewProjection;
    float4 placement,mapInfo,eye,viewport,reflectionInfo,opticsInfo,uvScales,motion;
    float4 light0,light1,absorption,warp0,warp1;
    float4 lightColour0,lightColour1,shadowInfo;
    float4 fogDistance,fogColour,waterOverlay;
};
Texture2D<float4> LeanMean:register(t0);
Texture2D<float> LeanCross:register(t1);
Texture2D<float4> ReflectionCache:register(t2);
Texture2D<float4> DepthColour:register(t6);
Texture2D<float4> CoastWave:register(t8);
Texture2D<uint2> PlotState:register(t9);
Texture2D<uint> WaterMask:register(t10);
Texture2D<float4> FogMask:register(t12);
Texture3D<float4> FowColourKey:register(t13);
Texture2D<float4> FogRamp:register(t14);
SamplerState WrapSampler:register(s0);
SamplerState ClampSampler:register(s1);
SamplerState MaskSampler:register(s2);
struct V{float3 p:POSITION;float2 uv:TEXCOORD0;float kind:TEXCOORD1;float depth:TEXCOORD2;float flow:TEXCOORD3;};
struct P{float4 p:SV_POSITION;float2 world:TEXCOORD0;float2 uv:TEXCOORD1;float rawHeight:TEXCOORD2;
    nointerpolation float kind:TEXCOORD3;float3 local:TEXCOORD4;float2 canonical:TEXCOORD5;float4 reflection:TEXCOORD6;};
P vertexMain(V v){P p;p.local=v.p+float3(placement.x,0,placement.y);p.p=mul(float4(p.local,1),viewProjection);
    p.world=v.p.xz+placement.zw;p.canonical=v.p.xz;p.uv=v.uv;p.rawHeight=v.depth;p.kind=v.kind;
    p.reflection=mul(float4(p.local,1),reflectionViewProjection);return p;}
int RoundAway(float v){return v<0?-(int)floor(-v+0.5):(int)floor(v+0.5);}
int Wrapped(int v,int span){uint m=v<0?uint(-(v+1))+1u:uint(v);uint r=m%uint(span);return v<0&&r!=0?span-int(r):int(r);}
bool PlotAt(float2 w,out int2 cell){
    float row=-w.y/0.866025404,q=w.x-row*0.5;float3 f=float3(q,row,-q-row);int3 c=int3(RoundAway(f.x),RoundAway(f.y),RoundAway(f.z));
    float3 d=abs(float3(c)-f);if(d.x>d.y&&d.x>d.z)c.x=-c.y-c.z;else if(d.y>d.z)c.y=-c.x-c.z;else c.z=-c.x-c.y;
    cell=int2(c.x+(int)floor(c.y*0.5),c.y);if(mapInfo.z>0.5)cell.x=Wrapped(cell.x,(int)mapInfo.x);if(mapInfo.w>0.5)cell.y=Wrapped(cell.y,(int)mapInfo.y);
    return cell.x>=0&&cell.y>=0&&cell.x<(int)mapInfo.x&&cell.y<(int)mapInfo.y;
}
void Moments(float2 uv,bool mirrorX,out float2 mean,out float3 second){
    float4 a=LeanMean.Sample(WrapSampler,uv);float cross=LeanCross.Sample(WrapSampler,uv);
    mean=a.rg*2-1;second=float3(a.b,a.a,cross*2-1);
    if(mirrorX){mean.x=-mean.x;second.z=-second.z;}
}
void Mixture(float2 uv0,float2 uv1,out float2 mean,out float3 covariance){
    float2 m0,m1;float3 s0,s1;Moments(uv0,false,m0,s0);Moments(uv1,true,m1,s1);
    // Equal runtime blend weights are a candidate. Apply scale exactly once.
    float2 weights=float2(0.5,0.5)/opticsInfo.x;float2 a=m0*weights.x,b=m1*weights.y;
    mean=a+b;float3 second=s0*weights.x*weights.x+s1*weights.y*weights.y+
        float3(2*a.x*b.x,2*a.y*b.y,a.x*b.y+a.y*b.x);
    covariance=second-float3(mean.x*mean.x,mean.y*mean.y,mean.x*mean.y);
}
float Gaussian(float3 covariance,float2 halfSlope,float k,bool wide,out float determinant,out float q){
    float diagonal=(wide?16.0:1.0)/k,a=covariance.x+diagonal,d=covariance.y+diagonal,b=covariance.z;
    q=0;determinant=a*d-b*b;if(determinant<=0)return 0;
    q=(halfSlope.x*halfSlope.x*d+halfSlope.y*(a*halfSlope.y-2*b*halfSlope.x))*0.5/determinant;
    if(!isfinite(q)){q=0;return 0;}
    if(q>=16)return 0;
    float result=exp2(-q*1.442695)/sqrt(determinant)*(wide?0.005:1.0);
    return isfinite(result)?result:0; // Finite policy outside the original valid domain.
}
float2 HalfSlope(float3 v,float2 mean,float3 light,float4 warp){
    float3 w=normalize(lerp(warp.xyz,v,warp.w))+light;
    // Explicit finite candidate guard for the original horizontal division.
    return abs(w.z)>0.000001?w.xy/w.z-mean:float2(1000000,1000000);
}
float RetailFresnel(float2 mean,float3 v){
    float base=1-(mean.x*v.x+mean.y*v.y+v.z),square=base*base,fourth=square*square;return base*fourth;
}
float3 Encoded(float3 colour){return pow(max(colour,0),0.4545454680919647216796875);}
float3 Reflection(float4 projected,float3 covariance,float determinant,out float coverage){
    // Retail WaterPS divides the dedicated projector by W, then uses
    // (.5*x-.5,-.5*y-.5). Integer UV offsets are equivalent under WRAP.
    // Raw is UNORM; the separate terrain t9 is a static DDS, not this image.
    float2 base=projected.xy/projected.w*float2(0.5,-0.5)-0.5+6*covariance.xy;
    float4 r=ReflectionCache.Sample(WrapSampler,base+float2(2,2)*determinant)*0.25;
    r+=ReflectionCache.Sample(WrapSampler,base+float2(2,-2)*determinant)*0.25;
    r=ReflectionCache.Sample(WrapSampler,base+float2(-2,6)*determinant)*0.25+r;
    r=ReflectionCache.Sample(WrapSampler,base+float2(-2,-2)*determinant)*0.25+r;
    coverage=saturate(r.a);return pow(max(r.rgb,0),2.2);
}
float WaterDistanceFactor(P p){
    float3 delta=(p.local-eye.xyz).xzy*float3(1,-1,1)*fogDistance.w;
    float exponent;
    // Finite horizontal-ray handling is the existing isolated safety policy.
    if(abs(delta.z)<0.0001)exponent=-fogDistance.x*(0.6931471805599453*1.442695)*dot(delta,delta)*fogDistance.y;
    else exponent=(1-exp2(delta.z*fogDistance.x*1.442695))*dot(delta,delta)*fogDistance.y/delta.z;
    float amount=1-min(exp2(exponent*1.442695),1);
    float rampU=1-p.p.y/viewport.y;
    return saturate(amount)*FogRamp.Sample(ClampSampler,float2(rampU,fogDistance.z)).r;
}
float4 FogBeforeBlend(float4 encoded,P p){
    if(motion.z<0.5)return encoded;
    float2 maskUv=float2(p.world.x/mapInfo.x,-p.world.y/(0.866025404*mapInfo.y));
    float3 mask=FogMask.Sample(MaskSampler,maskUv).rgb;
    float3 overlay=waterOverlay.rgb+(1-waterOverlay.a)*encoded.rgb;
    float3 colour=lerp(float3(0.4,0.4,0.4),overlay,mask.r);
    float3 transformed=FowColourKey.Sample(ClampSampler,colour).rgb;
    colour=lerp(colour,transformed,mask.r*(1-mask.b));
    return float4(lerp(colour,fogColour.rgb,WaterDistanceFactor(p)),encoded.a);
}
struct O{float4 colour:SV_Target0;uint pick:SV_Target1;uint waterFragment:SV_Target4;};
O pixelMain(P p){
    O o;o.colour=0;o.pick=0;o.waterFragment=0;int2 cell;if(!PlotAt(p.world,cell))discard;
    uint2 state=PlotState.Load(int3(cell,0));if(state.y==0)discard;
    if(p.kind<0.5&&WaterMask.Load(int3(cell,0))==0)discard;
    o.pick=state.x;
    // Class2 denotes colour already fogged before the original alpha blend.
    // Units overwrite the class to zero and take the later ordinary fog pass.
    o.waterFragment=motion.z>0.5?2u:0u;
    if(p.kind>0.5){
        float4 foam=CoastWave.Sample(WrapSampler,float2(p.uv.x-reflectionInfo.w*motion.x,p.uv.y));
        // Coast shape/foam opacity remain independent reconstruction candidates.
        o.colour=FogBeforeBlend(float4(Encoded(foam.rgb*foam.rgb),saturate(foam.a*(1-abs(p.uv.y*2-1))*0.65)),p);return o;
    }
    float2 retail=p.canonical*float2(1,-1)*eye.w;float t=reflectionInfo.w*motion.x;
    float2 uv0=retail*uvScales.x+t,uv1=retail*float2(-1,1)*uvScales.y+t,mean;float3 covariance;Mixture(uv0,uv1,mean,covariance);
    float3 currentView=normalize(eye.xyz-p.local),view=currentView.xzy*float3(1,-1,1);
    float det0,wide0,det1,q0,qWide0,q1;
    float2 h0=HalfSlope(view,mean,light0.xyz,warp0),h1=HalfSlope(view,mean,light1.xyz,warp1);
    float lobe0=Gaussian(covariance,h0,opticsInfo.y,false,det0,q0);
    float lobeWide0=Gaussian(covariance,h0,opticsInfo.y,true,wide0,qWide0);
    float lobe1=Gaussian(covariance,h1,opticsInfo.z,false,det1,q1);
    float4 deep=DepthColour.SampleLevel(ClampSampler,float2(1-saturate(4*p.rawHeight),0),0);
    // Original t6.rgb is used directly; no additional pow2.2 is in this path.
    float coverage=0;float3 reflected=0;
    // Deny invalid or disabled projectors before any reflection sample.
    if(det1>0&&motion.w>0.5&&all(isfinite(p.reflection))&&abs(p.reflection.w)>0.00000001)
        reflected=Reflection(p.reflection,covariance,det1,coverage);
    float f=RetailFresnel(mean,view),diffuse=saturate(dot(float3(mean,1),light0.xyz));
    float3 lit=diffuse*(deep.rgb+f*(lobe0*lightColour0.rgb+lobe1*lightColour1.rgb));
    lit+=lobeWide0*deep.rgb*lightColour0.rgb+reflected*opticsInfo.w;
    // r1.w retains the secondary exponent even when its Gaussian is rejected
    // at q>=16. This depth term is not the secondary lobe cubed.
    float depthFactor=saturate(4*p.rawHeight);
    float qSquared=q1*q1,qCubed=qSquared*q1;
    if(!isfinite(qCubed))qCubed=0;
    lit+=depthFactor*qCubed*deep.rgb;
    float shadowAmount=saturate(SampleDynamicShadow(p.local))*shadowInfo.y;
    float3 shadowed=shadowAmount*lit;lit=shadowed*(-0.67)+lit;
    if(!all(isfinite(lit)))lit=deep.rgb;
    // Original stage8 uses SRC_ALPHA/INV_SRC_ALPHA RGB and ONE/ONE alpha.
    // The destination is already fogged; no scene readback/refraction copy is used.
    float opacity=saturate(deep.a*(1+coverage));
    o.colour=FogBeforeBlend(float4(Encoded(lit),opacity),p);return o;
}
)HLSL";
}}}
