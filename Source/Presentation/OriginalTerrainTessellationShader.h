#pragma once
#include "OriginalTerrainTessellationModel.h"
#include "OriginalTerrainPatchPlacement.h"

namespace ZeroSisPresentation { namespace OriginalTerrainTessellation {
// The original 160-byte b7 prefix and explicitly supplied basis stay usable
// for a single patch. Batched world draws append the grid and its exact span.
struct alignas(16) DomainConstants {
    std::array<float,16> domainViewProjection{};
    Basis cubicBasis=RetailBasis();
    std::array<float,4> patchPlacement{};
    std::array<float,4> domainPolicy{};
    std::array<std::uint32_t,4> patchGrid{{1,1,0,0}};

    void SetPlacement(const OriginalTerrain::PatchWorld::Placement& patch) noexcept {
        patchPlacement=patch.originSpacing;
        patchGrid=patch.grid;
    }
};
static_assert(sizeof(DomainConstants)==176,"Unexpected terrain domain constant buffer size");

inline DomainConstants WorldDomainConstants(const std::array<float,16>& displayViewProjection){
    DomainConstants result;
    result.domainViewProjection=displayViewProjection;
    constexpr float perTexel=1.0f/OriginalTerrainCacheSampling::SourceTexelsPerHex;
    // Row vectors: scale source X and source row into display X and -Z
    // before projection. Heights supplied by the world mesh are in display Y.
    for(unsigned i=0;i<4;++i){
        result.domainViewProjection[i]*=perTexel;
        result.domainViewProjection[8+i]*=-OriginalTerrain::RowSpacing*perTexel;
    }
    result.domainPolicy={{1,1,0,0}};
    return result;
}

static const char ShaderSource[]=R"HLSL(
cbuffer DomainPolicy:register(b7){
    row_major float4x4 domainViewProjection;
    // FXC records this default in reflection metadata. Upload DomainConstants for a draw.
    float4 cubicBasis[4]={
        float4(-0.125,  0.875, -0.875, 0.125),
        float4( 0.375, -1.500,  1.125, 0.000),
        float4(-0.375,  0.000,  0.375, 0.000),
        float4( 0.125,  0.750,  0.125, 0.000)
    };
    float4 patchPlacement; // plane origin XY, spacing per patch in X and Y
    float4 domainPolicy; // integer factor, Y scale, Y offset, reserved
    uint4 patchGrid; // columns, rows, exact terminal intervals X/Y (zero for a legacy single patch)
};
uint2 GridSize(){return max(patchGrid.xy,uint2(1,1));}
float4 PatchClip(float2 gridPosition,float displayHeight){
    float2 offset=gridPosition*patchPlacement.zw;
    // Snap the very last node to the integer span of a clipped cell. Interior
    // edges are evaluated from the same grid coordinate on both patches.
    if(patchGrid.z!=0u && gridPosition.x==float(GridSize().x))offset.x=float(patchGrid.z);
    if(patchGrid.w!=0u && gridPosition.y==float(GridSize().y))offset.y=float(patchGrid.w);
    const float2 plane=patchPlacement.xy+offset;
    return mul(float4(plane.x,displayHeight,plane.y,1),domainViewProjection);
}
struct WorldVertex{float3 p:POSITION;float2 uv:TEXCOORD0;float light:TEXCOORD1;
    float4 w0:TEXCOORD2;float4 w1:TEXCOORD3;float3 normal:TEXCOORD5;};
struct WorldPixel{float4 p:SV_POSITION;float2 uv:TEXCOORD0;float height:TEXCOORD1;
    float light:TEXCOORD2;float4 w0:TEXCOORD3;float4 w1:TEXCOORD4;float3 normal:TEXCOORD5;};
WorldPixel worldVertexMain(WorldVertex v){
    WorldPixel o;o.p=PatchClip(v.uv*float2(GridSize()),v.p.y);o.uv=v.uv;o.height=v.p.y;
    o.light=v.light;o.w0=v.w0;o.w1=v.w1;o.normal=v.normal;return o;
}
struct Control{float height:TEXCOORD0;float2 uv:TEXCOORD1;float light:TEXCOORD2;
    float4 w0:TEXCOORD3;float4 w1:TEXCOORD4;float3 normal:TEXCOORD5;};
Control vertexMain(float height:POSITION){Control result=(Control)0;result.height=height;return result;}
Control worldControlMain(WorldVertex v){
    Control o;o.height=v.p.y;o.uv=v.uv;o.light=v.light;o.w0=v.w0;o.w1=v.w1;o.normal=v.normal;return o;
}
struct Patch{float edges[4]:SV_TessFactor;float inside[2]:SV_InsideTessFactor;};
Patch patchMain(InputPatch<Control,16> controls,uint patch:SV_PrimitiveID){
    Patch result;[unroll]for(uint i=0;i<4;++i)result.edges[i]=domainPolicy.x;
    result.inside[0]=result.inside[1]=domainPolicy.x;return result;
}
[domain("quad")][partitioning("integer")][outputtopology("triangle_ccw")]
[outputcontrolpoints(16)][patchconstantfunc("patchMain")]
Control hullMain(InputPatch<Control,16> controls,uint id:SV_OutputControlPointID,uint patch:SV_PrimitiveID){return controls[id];}
struct DomainOutput{float4 position:SV_POSITION;float2 uv:TEXCOORD0;float height:TEXCOORD1;};
float BicubicHeight(float2 uv,const OutputPatch<Control,16> controls){
    float2 square=uv*uv,cube=square*uv;
    float4 horizontal=square.x*cubicBasis[1];
    horizontal=cubicBasis[0]*cube.x+horizontal;
    horizontal=cubicBasis[2]*uv.x+horizontal;horizontal+=cubicBasis[3];
    float4 rows=float4(dot(horizontal,float4(controls[0].height,controls[1].height,controls[2].height,controls[3].height)),
        dot(horizontal,float4(controls[4].height,controls[5].height,controls[6].height,controls[7].height)),
        dot(horizontal,float4(controls[8].height,controls[9].height,controls[10].height,controls[11].height)),
        dot(horizontal,float4(controls[12].height,controls[13].height,controls[14].height,controls[15].height)));
    float4 vertical=float4(dot(cubicBasis[0],rows),dot(cubicBasis[1],rows),dot(cubicBasis[2],rows),dot(cubicBasis[3],rows));
    return dot(vertical,float4(cube.y,square.y,uv.y,1));
}
float2 Lattice(uint patchId,float2 uv){uint columns=GridSize().x;return float2(patchId%columns,patchId/columns)+uv;}
[domain("quad")]
DomainOutput domainMain(Patch patch,float2 uv:SV_DomainLocation,const OutputPatch<Control,16> controls,uint patchId:SV_PrimitiveID){
    float h=BicubicHeight(uv,controls);float2 lattice=Lattice(patchId,uv);
    DomainOutput result;result.position=PatchClip(lattice,h*domainPolicy.y+domainPolicy.z);
    result.uv=lattice/float2(GridSize());result.height=h;return result;
}
[domain("quad")]
WorldPixel worldDomainMain(Patch patch,float2 uv:SV_DomainLocation,const OutputPatch<Control,16> c,uint patchId:SV_PrimitiveID){
    float2 lattice=Lattice(patchId,uv);
    float4 w=float4((1-uv.x)*(1-uv.y),uv.x*(1-uv.y),(1-uv.x)*uv.y,uv.x*uv.y);
    float height=BicubicHeight(uv,c);
    // Join the existing triangle ring at its actual control heights. Both
    // submissions have one edge segment, including next to unexplored chunks.
    if(any(lattice==0) || any(lattice==float2(GridSize())))
        height=dot(w,float4(c[5].height,c[6].height,c[9].height,c[10].height));
    WorldPixel o;o.height=height;o.p=PatchClip(lattice,height);
    o.uv=w.x*c[5].uv+w.y*c[6].uv+w.z*c[9].uv+w.w*c[10].uv;
    o.light=dot(w,float4(c[5].light,c[6].light,c[9].light,c[10].light));
    o.w0=w.x*c[5].w0+w.y*c[6].w0+w.z*c[9].w0+w.w*c[10].w0;
    o.w1=w.x*c[5].w1+w.y*c[6].w1+w.z*c[9].w1+w.w*c[10].w1;
    o.normal=w.x*c[5].normal+w.y*c[6].normal+w.z*c[9].normal+w.w*c[10].normal;
    return o;
}
)HLSL";
}}
