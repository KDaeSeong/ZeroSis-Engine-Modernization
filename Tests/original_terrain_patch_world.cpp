#include "OriginalTerrainGeometry.h"
#include "OriginalTerrainLod.h"
#include "OriginalTerrainTessellationShader.h"
#include "WorldTerrainRenderer.h"
#include <d3d11.h>
#include <d3dcompiler.h>
#include <wrl/client.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <limits>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

using Microsoft::WRL::ComPtr;
using namespace ZeroSisPresentation;
namespace T=OriginalTerrainTessellation;
namespace W=OriginalTerrain::PatchWorld;
namespace L=OriginalTerrain::Lod;

namespace {
void Check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}
void Ok(HRESULT hr,const char* message){
    if(FAILED(hr)){std::fprintf(stderr,"%s: 0x%08lx\n",message,static_cast<unsigned long>(hr));throw std::runtime_error(message);}
}
void Near(double actual,double expected,double tolerance=2e-5){
    if(!(std::abs(actual-expected)<=tolerance)){
        std::fprintf(stderr,"Coordinate %.12g expected %.12g\n",actual,expected);
        throw std::runtime_error("Unexpected world coordinate");
    }
}
template<class F> void Reject(F f){try{f();}catch(const std::invalid_argument&){return;}throw std::runtime_error("Invalid cell accepted");}

void CpuLayout(){
    // Every possible terminal cell width; ceil(intervals / 2^level) is an
    // independent expression for the retail inclusive-node recurrence.
    for(unsigned width=1;width<=64;++width)for(unsigned lod=0;lod<=4;++lod){
        const auto a=W::CellAxis(129+width,2,lod);
        const unsigned step=1u<<lod,expected=(width+step-1)/step;
        Check(a.firstTexel==128 && a.intervals==width && a.patches==expected,"Clipped cell/level size");
        Near(a.spacing,static_cast<double>(width)/expected,1e-6);
    }
    Near(W::NativeWorld(5,11,1),0);
    Near(W::NativeWorld(0,90,0.866f),-45.0*static_cast<double>(0.866f),0);
    const W::Frame f{134,90,-27,-16.0*static_cast<double>(0.866f)};
    const auto last=W::Place(f,2,1,-1,-1,1),first=W::Place(f,0,0,0,0,0);
    Check(last.grid==std::array<std::uint32_t,4>{{3,13,5,25}},"Rectangular patch grid");
    Near(last.originSpacing[0],-45,0);Near(last.originSpacing[1],-54,0);
    Near(last.originSpacing[0]+5,first.originSpacing[0],0);
    Near(last.originSpacing[1]+25,first.originSpacing[1],0);
    Reject([&]{W::Place(f,2,1,0,1,0);});Reject([&]{W::Place(f,3,1,3,1,0);});
    Reject([&]{W::Place(f,0,0,0,0,5);});Reject([]{W::CellAxis(1,0,0);});
    auto invalid=f;invalid.cameraWorldX=(std::numeric_limits<double>::infinity)();
    Reject([&]{W::Place(invalid,0,0,0,0,0);});

    OriginalTerrain::Atlas atlas;atlas.width=128;atlas.height=192;
    atlas.ids.resize(128*192);atlas.known.resize(128*192);atlas.heights.resize(128*192);
    std::fill(atlas.known.begin(),atlas.known.end(),std::uint8_t{1});
    Check(OriginalTerrain::HasPatchControls(atlas,0,0),"Fully known interior was rejected");
    atlas.wrapX=false;Check(!OriginalTerrain::HasPatchControls(atlas,1,0),"Bounded edge wrapped controls");
    atlas.wrapX=true;Check(OriginalTerrain::HasPatchControls(atlas,1,0),"Wrapped edge lost known controls");
    atlas.known[10*128]=0;atlas.heights[10*128]=std::numeric_limits<float>::quiet_NaN();
    Check(!OriginalTerrain::HasPatchControls(atlas,1,0),"Unknown wrapped control was accepted");
    for(int row:{0,1,2}){
        const auto frame=OriginalTerrain::PatchFrameForCamera(atlas,1,row);
        const auto draw=W::Place(frame,0,0,0,0,0);
        Near(draw.originSpacing[0],-64-32*(row%2),0);Near(draw.originSpacing[1],-64*row,0);
        const auto display=W::DisplayOrigin(draw);
        Near(display[0],-1.0-0.5*(row%2));Near(display[1],row*std::sqrt(3.0)/2);
    }
    atlas.originX=-16;atlas.originY=7;
    const auto shifted=W::Place(OriginalTerrain::PatchFrameForCamera(atlas,1,1),0,0,0,0,0);
    Near(shifted.originSpacing[0],-80,0);Near(shifted.originSpacing[1],-57,0);
}

ComPtr<ID3DBlob> Compile(const char* source,const char* entry,const char* profile){
    ComPtr<ID3DBlob> code,errors;
    const HRESULT hr=D3DCompile(source,std::strlen(source),"patch-world-test",nullptr,nullptr,entry,profile,
        D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_WARNINGS_ARE_ERRORS,0,&code,&errors);
    if(FAILED(hr)&&errors)std::fwrite(errors->GetBufferPointer(),1,errors->GetBufferSize(),stderr);
    Ok(hr,"Compile shader");return code;
}
struct Captured {float clip[4],uv[2],height;};
struct SurfaceControl {
    float position[3],uv[2],light;
    std::uint32_t materialWeights[2];
    float normal[3];
};
static_assert(sizeof(SurfaceControl)==44,"Unexpected production control vertex layout");

// At integer knots the original cubic kernel has weights 1/8, 6/8, 1/8.
// It adds 0.25 to x squared and 0.5 to twice y squared on this surface.
float SampleHeight(int x,int y){return static_cast<float>(x*x+2*y*y)/16.0f;}

struct Warp {
    ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;
    ComPtr<ID3D11VertexShader> vs,worldControls;ComPtr<ID3D11HullShader> hs;
    ComPtr<ID3D11DomainShader> ds,worldDomain;
    ComPtr<ID3D11GeometryShader> capture;ComPtr<ID3D11InputLayout> layout,worldLayout;
    Warp(){
        D3D_FEATURE_LEVEL actual;const D3D_FEATURE_LEVEL requested=D3D_FEATURE_LEVEL_11_0;
        Ok(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,&requested,1,
            D3D11_SDK_VERSION,&device,&actual,&context),"Create offscreen software device");
        Check(actual==requested,"WARP feature level");
        const auto v=Compile(T::ShaderSource,"vertexMain","vs_5_0"),h=Compile(T::ShaderSource,"hullMain","hs_5_0"),
                   d=Compile(T::ShaderSource,"domainMain","ds_5_0");
        Ok(device->CreateVertexShader(v->GetBufferPointer(),v->GetBufferSize(),nullptr,&vs),"Create patch VS");
        Ok(device->CreateHullShader(h->GetBufferPointer(),h->GetBufferSize(),nullptr,&hs),"Create patch HS");
        Ok(device->CreateDomainShader(d->GetBufferPointer(),d->GetBufferSize(),nullptr,&ds),"Create patch DS");
        const D3D11_INPUT_ELEMENT_DESC input={"POSITION",0,DXGI_FORMAT_R32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0};
        Ok(device->CreateInputLayout(&input,1,v->GetBufferPointer(),v->GetBufferSize(),&layout),"Patch input layout");
        const auto cv=Compile(T::ShaderSource,"worldControlMain","vs_5_0"),wd=Compile(T::ShaderSource,"worldDomainMain","ds_5_0");
        Ok(device->CreateVertexShader(cv->GetBufferPointer(),cv->GetBufferSize(),nullptr,&worldControls),"Create world control VS");
        Ok(device->CreateDomainShader(wd->GetBufferPointer(),wd->GetBufferSize(),nullptr,&worldDomain),"Create world DS");
        const D3D11_INPUT_ELEMENT_DESC inputs[]={
            {"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",1,DXGI_FORMAT_R32_FLOAT,0,20,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",2,DXGI_FORMAT_R8G8B8A8_UNORM,0,24,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",3,DXGI_FORMAT_R8G8B8A8_UNORM,0,28,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",5,DXGI_FORMAT_R32G32B32_FLOAT,0,32,D3D11_INPUT_PER_VERTEX_DATA,0}};
        Ok(device->CreateInputLayout(inputs,static_cast<UINT>(std::size(inputs)),cv->GetBufferPointer(),cv->GetBufferSize(),&worldLayout),
            "World control input layout");
        const char geometry[]=R"HLSL(
struct V{float4 p:SV_POSITION;float2 uv:TEXCOORD0;float h:TEXCOORD1;};
[maxvertexcount(3)] void copyTriangle(triangle V v[3],inout TriangleStream<V> output){
    for(uint i=0;i<3;++i)output.Append(v[i]);
})HLSL";
        const auto g=Compile(geometry,"copyTriangle","gs_5_0");
        const D3D11_SO_DECLARATION_ENTRY outputs[]={{0,"SV_POSITION",0,0,4,0},{0,"TEXCOORD",0,0,2,0},{0,"TEXCOORD",1,0,1,0}};
        const UINT stride=sizeof(Captured);
        Ok(device->CreateGeometryShaderWithStreamOutput(g->GetBufferPointer(),g->GetBufferSize(),outputs,3,&stride,1,
            D3D11_SO_NO_RASTERIZED_STREAM,nullptr,&capture),"Create coordinate capture GS");
    }

    unsigned CheckPatchDraw(const W::Placement& placement,double startX,double startY,unsigned spanX,unsigned spanY,bool worldSurface=false){
        // Nonidentity row-vector transform, including elevation in Z and XY in W.
        const std::array<float,16> vp={{0.5f,0,0,0.125f,0,1.5f,0.25f,0,0.25f,0,0.75f,0.125f,2,-1,0.5f,1}};
        auto constants=T::WorldDomainConstants(vp);constants.SetPlacement(placement);
        if(!worldSurface)constants.domainPolicy={{2,0.25f,-0.75f,0}};
        const unsigned cols=placement.grid[0],rows=placement.grid[1],patches=cols*rows;
        const unsigned factor=worldSurface?1:2;
        const UINT vertexCount=patches*factor*factor*6;
        const auto buffer=[&](UINT flags,UINT bytes,const void* data){
            D3D11_BUFFER_DESC desc{};desc.ByteWidth=bytes;desc.BindFlags=flags;
            desc.Usage=flags?D3D11_USAGE_DEFAULT:D3D11_USAGE_STAGING;
            desc.CPUAccessFlags=flags?0:D3D11_CPU_ACCESS_READ;
            D3D11_SUBRESOURCE_DATA initial{data,0,0};ComPtr<ID3D11Buffer> out;
            Ok(device->CreateBuffer(&desc,data?&initial:nullptr,&out),"Create capture buffer");return out;
        };
        ComPtr<ID3D11Buffer> input;
        UINT stride;
        if(worldSurface){
            std::vector<SurfaceControl> controls;
            controls.reserve(patches*16);
            for(unsigned row=0;row<rows;++row)for(unsigned col=0;col<cols;++col){
                for(int dy=-1;dy<=2;++dy)for(int dx=-1;dx<=2;++dx){
                    const int x=static_cast<int>(col)+dx,y=static_cast<int>(row)+dy;
                    SurfaceControl control{};
                    control.position[1]=SampleHeight(x,y);
                    control.uv[0]=static_cast<float>(x)/cols;control.uv[1]=static_cast<float>(y)/rows;
                    controls.push_back(control);
                }
            }
            stride=sizeof(SurfaceControl);
            input=buffer(D3D11_BIND_VERTEX_BUFFER,static_cast<UINT>(controls.size())*stride,controls.data());
        }else{
            const std::vector<float> heights(patches*16,7.0f);
            stride=sizeof(float);
            input=buffer(D3D11_BIND_VERTEX_BUFFER,static_cast<UINT>(heights.size())*stride,heights.data());
        }
        auto uniform=buffer(D3D11_BIND_CONSTANT_BUFFER,sizeof(constants),&constants);
        auto output=buffer(D3D11_BIND_STREAM_OUTPUT,vertexCount*sizeof(Captured),nullptr);
        auto readback=buffer(0,vertexCount*sizeof(Captured),nullptr);
        ComPtr<ID3D11Query> query;D3D11_QUERY_DESC queryDesc{D3D11_QUERY_SO_STATISTICS,0};
        Ok(device->CreateQuery(&queryDesc,&query),"Create stream-output query");
        const UINT zero=0;auto* vb=input.Get();auto* cb=uniform.Get();auto* so=output.Get();
        context->IASetInputLayout(worldSurface?worldLayout.Get():layout.Get());context->IASetVertexBuffers(0,1,&vb,&stride,&zero);
        context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_16_CONTROL_POINT_PATCHLIST);
        context->VSSetShader(worldSurface?worldControls.Get():vs.Get(),nullptr,0);context->HSSetShader(hs.Get(),nullptr,0);
        context->DSSetShader(worldSurface?worldDomain.Get():ds.Get(),nullptr,0);
        context->HSSetConstantBuffers(7,1,&cb);context->DSSetConstantBuffers(7,1,&cb);
        context->GSSetShader(capture.Get(),nullptr,0);context->SOSetTargets(1,&so,&zero);
        context->Begin(query.Get());context->Draw(patches*16,0);context->End(query.Get());context->SOSetTargets(0,nullptr,nullptr);
        context->CopyResource(readback.Get(),output.Get());D3D11_MAPPED_SUBRESOURCE mapped{};
        Ok(context->Map(readback.Get(),0,D3D11_MAP_READ,0,&mapped),"Read generated coordinates");
        std::vector<Captured> observed(vertexCount);
        std::memcpy(observed.data(),mapped.pData,observed.size()*sizeof(Captured));context->Unmap(readback.Get(),0);
        D3D11_QUERY_DATA_SO_STATISTICS stats{};
        Check(context->GetData(query.Get(),&stats,sizeof(stats),0)==S_OK &&
            stats.NumPrimitivesWritten==vertexCount/3 && stats.PrimitivesStorageNeeded==stats.NumPrimitivesWritten,"Missing generated triangles");
        std::set<std::pair<int,int>> lattice;
        for(const auto& o:observed){
            const int i=static_cast<int>(std::lround(o.uv[0]*cols*factor)),j=static_cast<int>(std::lround(o.uv[1]*rows*factor));
            Check(i>=0 && j>=0 && static_cast<unsigned>(i)<=factor*cols && static_cast<unsigned>(j)<=factor*rows,"Bad batch UV");
            const double u=static_cast<double>(i)/(factor*cols),v=static_cast<double>(j)/(factor*rows);
            Near(o.uv[0],u);Near(o.uv[1],v);
            const bool rim=i==0 || j==0 || static_cast<unsigned>(i)==cols || static_cast<unsigned>(j)==rows;
            const double rawHeight=worldSurface?SampleHeight(i,j)+(rim?0.0:0.75/16):7.0;
            const double elevation=worldSurface?rawHeight:1.0;
            Near(o.height,rawHeight);
            const double x=(startX+u*spanX)/64,z=-(startY+v*spanY)*std::sqrt(3.0)/128;
            Near(o.clip[0],x*.5+z*.25+2);Near(o.clip[1],elevation*1.5-1);
            Near(o.clip[2],elevation*.25+z*.75+.5);Near(o.clip[3],1+(x+z)*.125);
            lattice.emplace(i,j);
        }
        Check(lattice.size()==(factor*cols+1)*(factor*rows+1),"Two patches collapsed or left a gap");
        context->ClearState();return vertexCount;
    }
};

void CheckLod(){
    // For an orthographic view each opposite-corner pair has the same NDC length.
    std::array<float,16> vp={{1,0,0,0, 0,0,.125f,0, 0,1,0,0, -.5f,.4f,.5f,1}};
    const W::Placement cell={{{0,0,1,1}},{{64,64,64,64}}};
    Near(L::ProjectedFootprint(cell,vp,320,-1,1),80*std::sqrt(1.75));
    vp[3]=.5f; // w = 1 + x/2; the two screen-space diagonals have different lengths.
    Near(L::ProjectedFootprint(cell,vp,320,-1,1),80*std::hypot(5.0/6,std::sqrt(3.0)/2-2.0/15));
    vp[3]=0;
    vp[12]=5;
    Near(L::ProjectedFootprint(cell,vp,320,-1,1),0);
    vp[12]=0;vp[14]=0;
    Check(std::isinf(L::ProjectedFootprint(cell,vp,320,-1,1)),"Near-plane crossing selected a coarse grid");
    Near(L::RequestedLevel(0,64,4,2),4);
    Near(L::RequestedLevel(256,64,4,2),2.5);
    Near(L::RequestedLevel(1024,64,4,2),0.5);
    Near(L::RequestedLevel(4096,64,4,2),-1.5);
    Near(L::RequestedLevel((std::numeric_limits<double>::infinity)(),64,4,2),-2);
    const auto coarse=L::History{}.Update(2.125f);
    Near(coarse.band,.5);Near(coarse.Update(1.625f).accepted,2.125);
    const auto fine=coarse.Update(1.5f);
    Near(fine.band,-.25);Near(fine.Update(1.75f).accepted,1.5);Near(fine.Update(1.875f).accepted,1.875);
    Check(fine.Update(-1.25f).GridLevel()==0,"Negative levels may not coarsen the grid");

    const unsigned expectedTriangles[]={8192,2176,704,352,272};
    for(unsigned level=0;level<5;++level){
        const unsigned step=1u<<level,inner=64/step-2;
        const auto patch=W::Interior(cell,level);
        Check(patch.grid==std::array<std::uint32_t,4>{{inner,inner,inner*step,inner*step}},"Coarse world span");
        Near(patch.originSpacing[0],step);Near(patch.originSpacing[2],step);
        const auto geometry=L::BuildGridIndices(level);
        Check(geometry.controls.size()==inner*inner*16 && geometry.rim.size()/3+inner*inner*2==expectedTriangles[level],
            "Wrong number of coarse terrain primitives");
        std::map<std::pair<unsigned,unsigned>,std::pair<int,int>> edges;
        int doubledArea=0;
        const auto triangle=[&](unsigned a,unsigned b,unsigned c){
            const auto ix=[](unsigned n){return static_cast<int>(n%65);};
            const auto iy=[](unsigned n){return static_cast<int>(n/65);};
            const int area=(ix(b)-ix(a))*(iy(c)-iy(a))-(iy(b)-iy(a))*(ix(c)-ix(a));
            Check(a<65*65 && b<65*65 && c<65*65 && area>0,"Degenerate, reversed or out-of-range terrain triangle");
            doubledArea+=area;
            for(const auto& edge:{std::make_pair(a,b),std::make_pair(b,c),std::make_pair(c,a)}){
                auto& use=edges[std::minmax(edge.first,edge.second)];
                ++use.first;use.second+=edge.first<edge.second?1:-1;
            }
        };
        for(std::size_t i=0;i<geometry.rim.size();i+=3)triangle(geometry.rim[i],geometry.rim[i+1],geometry.rim[i+2]);
        for(unsigned q=0;q<inner*inner;++q){
            const auto* cp=geometry.controls.data()+16*q;
            for(unsigned i=0;i<16;++i){
                const unsigned x=(q%inner+i%4)*step,y=(q/inner+i/4)*step;
                Check(cp[i]==y*65+x,"Wrong coarse control or patch order");
            }
            triangle(cp[5],cp[6],cp[9]);triangle(cp[6],cp[10],cp[9]);
        }
        unsigned border=0;
        for(const auto& e:edges){
            const unsigned a=e.first.first,b=e.first.second;
            const bool horizontal=(a/65==0 || a/65==64) && a/65==b/65 && b==a+1;
            const bool vertical=(a%65==0 || a%65==64) && a%65==b%65 && b==a+65;
            if(horizontal || vertical){Check(e.second.first==1,"Duplicated external edge");++border;}
            else Check(e.second.first==2 && e.second.second==0,"Unmatched terrain edge or T-junction");
        }
        Check(border==256 && doubledArea==8192,"Missing unit-spaced boundary or uncovered surface");
    }
}

std::array<unsigned,2> WorldPass(Warp& warp,const wchar_t* package,const wchar_t* water,const wchar_t* waterSurface){
    constexpr UINT width=256,height=192;
    WorldView view{};view.gridWidth=5;view.gridHeight=4;view.wrapX=true;view.wrapY=false;
    view.cameraX=0;view.cameraY=1;view.tileWidth=48;view.terrainAssetsPath=package;view.mapRandomSeed=71;
    for(int y=0;y<view.gridHeight;++y)for(int x=0;x<view.gridWidth;++x){
        WorldViewPlot p{};p.index=y*view.gridWidth+x;p.x=x;p.y=y;p.terrain="TERRAIN_GRASS";p.terrainId=0;p.continent=1;
        p.hills=(x==0 && y==1) || (x==4 && y==2);
        p.mountain=x==3 && y==1;
        p.revealed=p.visible=true;view.plots.push_back(p);
    }
    D3D11_TEXTURE2D_DESC desc{};desc.Width=width;desc.Height=height;desc.Format=DXGI_FORMAT_B8G8R8A8_UNORM;
    desc.ArraySize=desc.MipLevels=desc.SampleDesc.Count=1;desc.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;
    ComPtr<ID3D11Texture2D> target;Ok(warp.device->CreateTexture2D(&desc,nullptr,&target),"Create offscreen world texture");
    bool expectCurves=true,expectShadow=false;
    unsigned observedLevel=0;
    const auto draw=[&](){
        TerrainFrame frame;std::wstring errors;
        D3D11_QUERY_DESC qd{D3D11_QUERY_PIPELINE_STATISTICS,0};ComPtr<ID3D11Query> stats;
        Ok(warp.device->CreateQuery(&qd,&stats),"Create world pipeline counters");
        warp.context->Begin(stats.Get());
        if(!RenderWorldTerrainToTexture(view,width,height,width,warp.device.Get(),warp.context.Get(),target.Get(),&frame,&errors)){
            std::fwprintf(stderr,L"%ls\n",errors.c_str());throw std::runtime_error("World terrain draw failed");
        }
        warp.context->End(stats.Get());warp.context->Flush();
        D3D11_QUERY_DATA_PIPELINE_STATISTICS counts{};
        HRESULT ready=S_FALSE;
        const auto deadline=GetTickCount64()+30000;
        while((ready=warp.context->GetData(stats.Get(),&counts,sizeof(counts),0))==S_FALSE && GetTickCount64()<deadline)Sleep(1);
        Check(ready==S_OK && (counts.DSInvocations!=0)==expectCurves && (counts.HSInvocations!=0)==expectCurves,
            "Unexpected tessellation stages in the published world draw");
        // The HS counter measures submitted patches directly. DS corner reuse
        // between the two triangles of a patch is implementation dependent.
        const auto expected=frame.bicubicPatches*(expectShadow?2:1);
        if(counts.HSInvocations!=expected || counts.DSInvocations<4*expected){
            std::fprintf(stderr,"World grid %u, patches %llu, shadow %d, observed HS %llu DS %llu, expected HS %llu\n",
                frame.terrainGridLevel,static_cast<unsigned long long>(frame.bicubicPatches),expectShadow?1:0,
                counts.HSInvocations,counts.DSInvocations,static_cast<unsigned long long>(expected));
            throw std::runtime_error("World and shadow patch counts differ");
        }
        observedLevel=frame.terrainGridLevel;
        Check(!frame.hardware && frame.triangles>0 && frame.picking.indices.size()==width*height,"World draw output");
        const int index=view.cameraY*view.gridWidth+view.cameraX;
        const auto center=frame.centers.at(index);
        Check(center.x>=0 && center.x<width && center.y>=0 && center.y<height,"Plot center outside view");
        const auto pixel=static_cast<unsigned>(center.y)*width+static_cast<unsigned>(center.x);
        const auto id=frame.picking.indices.at(pixel);
        Check(id!=0 && frame.picking.keys.at(id-1)==WorldViewHitKey::Plot(index),"Rendered world disagrees with plot selection");
        return frame.picking.indices;
    };
    const auto first=draw();Check(draw()==first,"Cached placement changed plot selection");
    view.cameraX=4;view.cameraY=2;Check(draw()!=first,"Camera or wrap change reused the old placement");
    view.cameraX=0;view.cameraY=1;Check(draw()==first,"Returning camera did not restore the world");
    view.tileWidth=WorldCameraZoom::Minimum;draw();const unsigned farLevel=observedLevel;
    view.tileWidth=WorldCameraZoom::Maximum;draw();const unsigned nearLevel=observedLevel;
    if(farLevel<=nearLevel)std::fprintf(stderr,"Far grid %u, near grid %u\n",farLevel,nearLevel);
    Check(farLevel>nearLevel,"Zoom did not select a coarser distance grid");
    view.tileWidth=48;draw();
    for(auto& plot:view.plots)plot.visible=plot.revealed=plot.x==view.cameraX && plot.y==view.cameraY;
    expectCurves=false;const auto fog=draw();
    Check(std::count(fog.begin(),fog.end(),0u)>0,"Unexplored plots received a selection ID");
    for(auto& plot:view.plots){
        plot.revealed=plot.visible=true;
        if(plot.y>=2){plot.water=true;plot.hills=false;plot.terrain="TERRAIN_COAST";plot.terrainId=5;}
    }
    view.wrapY=true;view.waterAssetsPath=water;view.waterSurfaceAssetsPath=waterSurface;
    expectCurves=expectShadow=true;draw();
    ReleaseWorldTerrainResources();
    return {{nearLevel,farLevel}};
}
}
int wmain(int argc,wchar_t** argv){
    try{
        Check(argc==4,"Pass the V2 terrain, water and water surface packages");CpuLayout();CheckLod();Warp warp;
        const W::Frame frame{134,90,-27,-16.0*static_cast<double>(0.866f)};
        unsigned vertices=warp.CheckPatchDraw(W::Place(frame,2,1,-1,-1,1),-45,-54,5,25);
        vertices+=warp.CheckPatchDraw(W::Place(frame,0,0,0,0,3),-40,-29,64,64);
        vertices+=warp.CheckPatchDraw(W::Place(frame,2,1,2,1,2),88,35,5,25);
        const unsigned surfaceVertices=warp.CheckPatchDraw(W::Place(frame,2,1,-1,-1,1),-45,-54,5,25,true);
        const auto levels=WorldPass(warp,argv[1],argv[2],argv[3]);
        std::printf("PASS_TERRAIN_PATCH_WORLD clipped_axis_cases=320 warp_vertices=%u world_surface_vertices=%u world_frames=9 lod_meshes=5 near_grid=%u far_grid=%u world_hs_ds_observed=1 shadow_draw_observed=1 native_game=0\n",
            vertices,surfaceVertices,levels[0],levels[1]);
        return 0;
    }catch(const std::exception& e){
        std::fprintf(stderr,"FAIL_TERRAIN_PATCH_WORLD %s\n",e.what());return 1;
    }
}
