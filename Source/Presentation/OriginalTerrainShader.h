#pragma once
namespace ZeroSisPresentation { namespace OriginalTerrain {
static const char ShaderSource[]=R"HLSL(
cbuffer Camera : register(b0) { row_major float4x4 viewProjection; };
cbuffer ReflectionClip : register(b2) {float4 clipInfo;}; // plane Y, enabled
cbuffer OriginalLighting : register(b3) {
    float4 lightingInfo; // enabled, shadow fallback, field enabled, world-LUT strength
    float4 specularAxis,compositionInfo,screenLighting,overlayColour;
};
cbuffer Chunk : register(b1) {
    float4 materials[8]; // scale, expanded projection, height-present, specular-present
    float4 placement; // camera-relative X/Z, unwrapped draw column/row
    float4 mapInfo; // width, height, wrapX, wrapY
    float4 textureOrigin; // canonical chunk column/row, retail units/hex, active slots
    float4 fogInfo; // FOW enabled,lighting enabled,original height origin,original Y metric
};
Texture2D Diffuse[8] : register(t0);
Texture2D HeightMap[8] : register(t8);
Texture2D Specular[8] : register(t16);
Texture2D<uint2> PlotState : register(t24); // independent picking-index and revealed/visible state
Texture2D<uint> LightingSelector : register(t25);
TextureCube Sunlight[5] : register(t26);
TextureCube Shadowlight[5] : register(t31);
Texture3D TerrainLut[5] : register(t36);
Texture2D<float4> DetailNormalField : register(t41);
Texture2D<float> HeightShadowField : register(t42);
SamplerState GroundSampler : register(s0);
SamplerState LightingSampler : register(s1);
struct V {float3 p:POSITION;float2 uv:TEXCOORD0;float light:TEXCOORD1;
          float4 w0:TEXCOORD2;float4 w1:TEXCOORD3;float3 normal:TEXCOORD5;};
struct P {float4 p:SV_POSITION;float2 uv:TEXCOORD0;float height:TEXCOORD1;
          float light:TEXCOORD2;float4 w0:TEXCOORD3;float4 w1:TEXCOORD4;float3 normal:TEXCOORD5;};
P vertexMain(V v){
    P p;p.p=mul(float4(v.p+float3(placement.x,0,placement.y),1),viewProjection);
    p.uv=v.uv;p.height=v.p.y;p.light=v.light;p.w0=v.w0;p.w1=v.w1;p.normal=v.normal;return p;
}
float3 LightingEncode(float3 value){return pow(max(value,0),0.4545454680919647216796875);}
float3 LookupTerrain(uint continent,float3 colour){
    float3 result=colour;
    [unroll]for(uint i=0;i<5;++i)if(continent==i)result=TerrainLut[i].SampleLevel(LightingSampler,colour,0).rgb;
    return result;
}
float3 TerrainCacheBake(uint continent,float3 n,float3 materialNormal,float shadow,float3 albedo,float4 specular,out float4 bakedSpecular){
    // Exact CacheBake tangent basis. The mixed-height/Sobel chain follows the
    // original path; our cache formats and shadow routing are current candidates.
    float tx=max(dot(n.xz,n.xz),0.000000000001),by=max(dot(n.yz,n.yz),0.000000000001);
    float3 tangent=float3(-n.z,0,n.x)*rsqrt(tx),bitangent=float3(0,n.z,-n.y)*rsqrt(by);
    float3 N=tangent*materialNormal.x+bitangent*materialNormal.y+n*materialNormal.z;
    float3 sun=0,shade=0;
    [unroll]for(uint j=0;j<5;++j)if(continent==j){
        sun=Sunlight[j].SampleLevel(LightingSampler,N,0).rgb;
        shade=Shadowlight[j].SampleLevel(LightingSampler,N,0).rgb;
    }
    float3 irradianceBase=sun*1.7,irradianceDelta=shade*1.7-irradianceBase;
    float3 irradiance=shadow*irradianceDelta+irradianceBase;
    float3 diffuse=LookupTerrain(continent,LightingEncode(albedo*irradiance+0.001));
    float exponent=64*specular.a+1;
    float4 reflected=pow(saturate(dot(specularAxis.xyz,N)),exponent)*exponent*saturate(1-shadow)*specular;
    bakedSpecular=float4(LookupTerrain(continent,LightingEncode(reflected.rgb)),reflected.a);
    return diffuse;
}
float3 TerrainComposition(uint continent,float3 baked,float3 bakedSpecular,float2 screen){
    float3 colour=CombineOriginalScreenReflection(baked,bakedSpecular,screen,true);
    float amount=saturate(compositionInfo.z)*lightingInfo.w;
    if(amount!=0)colour=lerp(colour,LookupTerrain(continent,colour),amount);
    // The original world-mask source and premultiplied overlay are not bound
    // in this isolated stage; their neutral inputs are explicit candidates.
    return overlayColour.rgb+(1-overlayColour.a)*colour;
}
int RoundAway(float v){return v<0?-(int)floor(-v+0.5):(int)floor(v+0.5);}
int Wrapped(int value,int span){
    uint magnitude=value<0?uint(-(value+1))+1u:uint(value);
    uint r=magnitude%uint(span);
    return value<0 && r!=0?span-int(r):int(r);
}
bool PlotAt(float2 uv,out int2 cell){
    float row=placement.w+uv.y;
    float q=placement.z+uv.x-row*0.5;
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
struct O {float4 color:SV_Target0;uint pick:SV_Target1;
          float4 specularSquared:SV_Target2;float materialHeight:SV_Target3;};
O pixelMain(P p){
    if(clipInfo.y>0.5 && p.height<clipInfo.x)discard;
    O o;o.color=float4(0.002,0.003,0.004,1);o.pick=0;o.specularSquared=0;o.materialHeight=0;
    int2 cell;if(!PlotAt(p.uv,cell))discard;
    uint2 state=PlotState.Load(int3(cell,0));
    // Reveal state is separate from picking: explored-but-hidden terrain still
    // contributes to material blending. Unknown terrain never samples materials.
    if(state.y==0){if(clipInfo.y>0.5)discard;return o;}
    o.pick=state.x;
    float weights[8]={p.w0.x,p.w0.y,p.w0.z,p.w0.w,p.w1.x,p.w1.y,p.w1.z,p.w1.w};
    float4 diffuseSum=0,specularSum=0;float heightSum=0,total=0;
    float3 world=float3((textureOrigin.x+p.uv.x)*textureOrigin.z,
        (textureOrigin.y+p.uv.y)*fogInfo.w*textureOrigin.z,p.height*textureOrigin.z+fogInfo.z);
    [unroll]for(int i=0;i<8;++i){
        if(i<(int)textureOrigin.w && weights[i]>0.01){
            float4 material=materials[i];float2 uv;
            if(material.y<0.5)uv=world.xy*material.x*0.33;
            else if(material.y<1.5)uv=world.xz*material.x*0.66;
            else uv=world.yz*material.x*0.66;
            // UNORM SRVs preserve the original raw samples before explicit d^2/s^2.
            float4 d=Diffuse[i].Sample(GroundSampler,uv);
            float a2=d.a*d.a,a4=a2*a2,W=a4*a4*weights[i];
            float h=material.z>0.5?HeightMap[i].Sample(GroundSampler,uv).r:(material.z< -0.5?0.5:0.0);
            float4 s=material.w>0.5?Specular[i].Sample(GroundSampler,uv):0;
            diffuseSum+=W*d*d;specularSum+=W*s*s;heightSum+=W*h;total+=W;
        }
    }
    if(total>0.00000001){
        float fog=fogInfo.x>0.5 || state.y==2?1.0:0.30;
        o.color=float4((diffuseSum.rgb/total)*p.light*fog,1);
        o.specularSquared=specularSum/total;o.materialHeight=heightSum/total;
        if(fogInfo.y>0.5){
            uint continent=LightingSelector.Load(int3(cell,0));if(continent>4)discard;
            float3 albedo=diffuseSum.rgb/total;
            float3 detailNormal=float3(0,0,1);float shadow=lightingInfo.y;
            if(lightingInfo.z>0.5){
                float2 fieldUv=(p.uv*64+1)/66;
                detailNormal=DetailNormalField.SampleLevel(LightingSampler,fieldUv,0).rgb*2-1;
                shadow=HeightShadowField.SampleLevel(LightingSampler,fieldUv,0);
            }
            float4 bakedSpecular;
            float3 baked=TerrainCacheBake(continent,p.normal,detailNormal,shadow,albedo,specularSum/total,bakedSpecular);
            float3 composed=TerrainComposition(continent,baked,bakedSpecular.rgb,p.p.xy);
            // This mode writes encoded RGB through an explicit UNORM RTV.
            // The auxiliary output retains baked specular for diagnostics;
            // final t8 composition follows the traced original route above.
            if(fog<1)composed=LightingEncode(pow(max(composed,0),2.2)*fog);
            o.color=float4(composed,1);
            o.specularSquared=bakedSpecular;
        }
    }
    return o;
}
)HLSL";
}}
