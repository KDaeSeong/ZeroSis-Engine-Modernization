#pragma once
namespace ZeroSisPresentation { namespace OriginalTerrainTessellation {
// Compile-ready HS/DS reconstruction. This stage is deliberately not selected
// by the renderer until the original basis and patch-input scale are supplied.
static const char ShaderSource[]=R"HLSL(
cbuffer DomainPolicy:register(b7){
    row_major float4x4 domainViewProjection;
    float4 cubicBasis[4];
    float4 patchPlacement; // start X, start Z, span X, span Z
    float4 domainPolicy; // integer factor, Y scale, Y offset, reserved
};
struct Control{float height:TEXCOORD0;};
Control vertexMain(float height:POSITION){Control result;result.height=height;return result;}
struct Patch{float edges[4]:SV_TessFactor;float inside[2]:SV_InsideTessFactor;};
Patch patchMain(InputPatch<Control,16> controls,uint patch:SV_PrimitiveID){
    Patch result;[unroll]for(uint i=0;i<4;++i)result.edges[i]=domainPolicy.x;
    result.inside[0]=result.inside[1]=domainPolicy.x;return result;
}
[domain("quad")][partitioning("integer")][outputtopology("triangle_ccw")]
[outputcontrolpoints(16)][patchconstantfunc("patchMain")]
Control hullMain(InputPatch<Control,16> controls,uint id:SV_OutputControlPointID,uint patch:SV_PrimitiveID){return controls[id];}
struct DomainOutput{float4 position:SV_POSITION;float2 uv:TEXCOORD0;float height:TEXCOORD1;};
[domain("quad")]
DomainOutput domainMain(Patch patch,float2 uv:SV_DomainLocation,const OutputPatch<Control,16> controls){
    float2 square=uv*uv,cube=square*uv;
    float4 horizontal=square.x*cubicBasis[1];
    horizontal=cubicBasis[0]*cube.x+horizontal;
    horizontal=cubicBasis[2]*uv.x+horizontal;horizontal+=cubicBasis[3];
    float4 rows=float4(dot(horizontal,float4(controls[0].height,controls[1].height,controls[2].height,controls[3].height)),
        dot(horizontal,float4(controls[4].height,controls[5].height,controls[6].height,controls[7].height)),
        dot(horizontal,float4(controls[8].height,controls[9].height,controls[10].height,controls[11].height)),
        dot(horizontal,float4(controls[12].height,controls[13].height,controls[14].height,controls[15].height)));
    float4 vertical=float4(dot(cubicBasis[0],rows),dot(cubicBasis[1],rows),dot(cubicBasis[2],rows),dot(cubicBasis[3],rows));
    float h=dot(vertical,float4(cube.y,square.y,uv.y,1));
    DomainOutput result;float3 world=float3(patchPlacement.x+uv.x*patchPlacement.z,h*domainPolicy.y+domainPolicy.z,
                                          patchPlacement.y+uv.y*patchPlacement.w);
    result.position=mul(float4(world,1),domainViewProjection);result.uv=uv;result.height=h;return result;
}
)HLSL";
}}
