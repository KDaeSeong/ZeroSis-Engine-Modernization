#include "WorldTerrainRenderer.h"
#include "WorldTerrainReuse.h"
#include "OriginalTerrainPackage.h"
#include "OriginalTerrainBinding.h"
#include "OriginalTerrainGeometry.h"
#include "OriginalTerrainVertexPreparation.h"
#include "OriginalTerrainShader.h"
#include "OriginalTerrainTessellationShader.h"
#include "OriginalTerrainLod.h"
#include "OriginalFogBinding.h"
#include "OriginalFogModel.h"
#include "OriginalFogState.h"
#include "OriginalFogPackage.h"
#include "OriginalFogShader.h"
#include "OriginalWaterBinding.h"
#include "OriginalWaterModel.h"
#include "OriginalWaterState.h"
#include "OriginalWaterPackage.h"
#include "OriginalWaterShader.h"
#include "OriginalWaterBridge.h"
#include "OriginalWaterSurfaceBinding.h"
#include "OriginalWaterSurfaceModel.h"
#include "OriginalWaterLeanPackage.h"
#include "OriginalWaterOpticsModel.h"
#include "OriginalWaterSurfaceShader.h"
#include "OriginalWaterBlendState.h"
#include "OriginalReflectionContract.h"
#include "OriginalLightingPackage.h"
#include "OriginalLightingBinding.h"
#include "OriginalLightingState.h"
#include "OriginalLightingFieldModel.h"
#include "OriginalLightingFieldBinding.h"
#include "OriginalLightingFieldShader.h"
#include "OriginalDynamicShadowModel.h"
#include "OriginalDynamicShadowShader.h"
#include "OriginalScreenLightingShader.h"
#include "OriginalScreenLightPackage.h"
#include "WorldUnitAssets.h"
#include "WorldUnitArtSelection.h"
#include <Windows.h>
#include <d3d11.h>
#include <dxgi.h>
#include <d3dcompiler.h>
#include <DirectXMath.h>
#include <wrl/client.h>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <limits>
#include <memory>
#include <set>
#include <stdexcept>

#pragma comment(lib,"d3d11.lib")
#pragma comment(lib,"d3dcompiler.lib")
namespace ZeroSisPresentation {
namespace {
using Microsoft::WRL::ComPtr;
using namespace DirectX;
void Require(bool ok,const char* text){if(!ok)throw std::runtime_error(text);}
void Check(HRESULT hr,const char* text){if(FAILED(hr)){
    char value[160]{};sprintf_s(value,"%s (0x%08lx)",text,static_cast<unsigned long>(hr));
    throw std::runtime_error(value);
}}
std::uint32_t Word(const unsigned char* p){return std::uint32_t(p[0]) | (std::uint32_t(p[1])<<8) |
    (std::uint32_t(p[2])<<16) | (std::uint32_t(p[3])<<24);}
struct Reader {
    std::vector<unsigned char> data;std::size_t cursor=0;
    explicit Reader(const std::wstring& path){
        std::ifstream file(std::filesystem::path(path),std::ios::binary|std::ios::ate);
        Require(file.good(),"Cannot open sealed terrain asset package");
        const auto size=file.tellg();Require(size>=16 && size<=128*1024*1024,"Terrain package exceeds its bound");
        data.resize(static_cast<std::size_t>(size));file.seekg(0);
        file.read(reinterpret_cast<char*>(data.data()),size);Require(file.good(),"Truncated terrain package read");
    }
    const unsigned char* Take(std::size_t size){Require(size<=data.size()-cursor,"Truncated terrain package record");
        const auto* p=data.data()+cursor;cursor+=size;return p;}
    std::uint32_t U32(){return Word(Take(4));}
};
struct Piece {std::uint32_t width=0,height=0;std::vector<std::uint16_t> red;};
struct Material {ComPtr<ID3D11ShaderResourceView> texture;};
struct Vertex {float x,y,z,u,v,light,fog,water;std::uint32_t pick;};
struct Group {std::vector<Vertex> vertices;};
#include "OriginalTerrainGpuTypes.inc"
#include "OriginalFogGpuTypes.inc"
#include "OriginalWaterGpuTypes.inc"
#include "OriginalWaterSurfaceGpuTypes.inc"
#include "OriginalLightingGpuTypes.inc"
#include "OriginalLightingFieldGpuTypes.inc"
#include "OriginalDynamicShadowGpuTypes.inc"
#include "OriginalScreenLightingGpuTypes.inc"
struct GroundMesh {ComPtr<ID3D11Buffer> buffer;UINT count=0;};
struct GroundData {
    std::map<std::pair<unsigned,unsigned>,GroundMesh> groups;
    TerrainFrame metadata;
    std::unique_ptr<OriginalGroundData> original;
};
struct FrameTargets {
    std::uint32_t width=0,height=0;
    bool fogEnabled=false,surfaceEnabled=false,lightingEnabled=false;
    ComPtr<ID3D11Texture2D> color,ids,depth,colorStaging,idStaging,specular,materialHeight;
    ComPtr<ID3D11Texture2D> fogColor;
    ComPtr<ID3D11RenderTargetView> colorView,idView,specularView,materialHeightView;
    ComPtr<ID3D11RenderTargetView> fogColorView;
    ComPtr<ID3D11RenderTargetView> colorRawView;
    ComPtr<ID3D11ShaderResourceView> colorResource,depthResource;
    ComPtr<ID3D11Texture2D> waterFragment;
    ComPtr<ID3D11RenderTargetView> waterFragmentView;
    ComPtr<ID3D11ShaderResourceView> waterFragmentResource;
    ComPtr<ID3D11DepthStencilView> depthView;
};
struct UnitBuffer {ComPtr<ID3D11Buffer> buffer;UINT capacity=0;};
struct Cache {
    ComPtr<ID3D11Device> device;ComPtr<ID3D11DeviceContext> context;
    ComPtr<ID3D11VertexShader> vs;ComPtr<ID3D11PixelShader> ps;
    ComPtr<ID3D11InputLayout> layout;ComPtr<ID3D11Buffer> constants,clipConstants;
    ComPtr<ID3D11SamplerState> sampler;ComPtr<ID3D11RasterizerState> raster;
    ComPtr<ID3D11DepthStencilState> depthState;ComPtr<ID3D11BlendState> blendState;
    std::map<std::pair<unsigned,unsigned>,Material> materials;
    std::unique_ptr<UnitAssetCatalog> units;
    std::unique_ptr<OriginalCatalog> original;
    std::unique_ptr<FogCatalog> fog;
    std::unique_ptr<WaterCatalog> water;
    std::unique_ptr<WaterSurfaceCatalog> waterSurface;
    std::unique_ptr<LightingCatalog> lighting;
    std::unique_ptr<LightingFieldBaker> lightingFieldBaker;
    std::unique_ptr<DynamicShadowMap> dynamicShadow;
    std::unique_ptr<ScreenLightingGpu> screenLighting;
    std::unique_ptr<ScreenLightCatalog> screenLight;
    std::array<Piece,5> pieces;std::wstring package;bool hardware=false;
    WorldTerrainReuse<GroundData> ground;
    std::unique_ptr<FrameTargets> targets;
    std::map<unsigned,UnitBuffer> unitBuffers;
    explicit Cache(const std::wstring& path,ID3D11Device* suppliedDevice=nullptr,
                   ID3D11DeviceContext* suppliedContext=nullptr):package(path){
        Require((suppliedDevice==nullptr)==(suppliedContext==nullptr),"Terrain device and immediate context must be supplied together");
        D3D_FEATURE_LEVEL level{};const D3D_FEATURE_LEVEL levels[]={D3D_FEATURE_LEVEL_11_0};
        if(suppliedDevice){
            device=suppliedDevice;context=suppliedContext;
            const D3D11_DEVICE_CONTEXT_TYPE type=context->GetType();
            Require(type==D3D11_DEVICE_CONTEXT_IMMEDIATE,"Terrain rendering requires the caller's immediate context");
            ComPtr<ID3D11Device> contextDevice;context->GetDevice(&contextDevice);
            Require(contextDevice.Get()==device.Get(),"Terrain immediate context belongs to a different device");
            ComPtr<IDXGIDevice> dxgi;ComPtr<IDXGIAdapter> baseAdapter;ComPtr<IDXGIAdapter1> adapter;
            DXGI_ADAPTER_DESC1 adapterDesc{};
            if(SUCCEEDED(device.As(&dxgi))&&SUCCEEDED(dxgi->GetAdapter(&baseAdapter))&&
               SUCCEEDED(baseAdapter.As(&adapter))&&SUCCEEDED(adapter->GetDesc1(&adapterDesc)))
                hardware=(adapterDesc.Flags&DXGI_ADAPTER_FLAG_SOFTWARE)==0;
        }else{
            HRESULT hr=D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,0,levels,1,D3D11_SDK_VERSION,&device,&level,&context);
            hardware=SUCCEEDED(hr);
            if(FAILED(hr))Check(D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,0,levels,1,D3D11_SDK_VERSION,&device,&level,&context),"Terrain D3D11 device");
        }
        static const char shader[]=R"HLSL(
cbuffer Camera : register(b0) { row_major float4x4 viewProjection; };
cbuffer ReflectionClip : register(b2) {float4 clipInfo;};
Texture2D Diffuse : register(t0); SamplerState GroundSampler : register(s0);
struct V {float3 p:POSITION;float2 uv:TEXCOORD0;float light:TEXCOORD1;
          float fog:TEXCOORD2;float water:TEXCOORD3;uint pick:TEXCOORD4;};
struct P {float4 p:SV_POSITION;float2 uv:TEXCOORD0;float light:TEXCOORD1;
          float fog:TEXCOORD2;float water:TEXCOORD3;nointerpolation uint pick:TEXCOORD4;float height:TEXCOORD5;};
P vertexMain(V v) {P p;p.p=mul(float4(v.p,1),viewProjection);p.uv=v.uv;
    p.light=v.light;p.fog=v.fog;p.water=v.water;p.pick=v.pick;p.height=v.p.y;return p;}
struct O {float4 color:SV_Target0;uint pick:SV_Target1;uint waterFragment:SV_Target4;};
O pixelMain(P p) {O o;o.pick=p.pick;o.waterFragment=0;
    if(clipInfo.y>0.5 && (p.height<clipInfo.x||p.fog<0))discard;
    if(p.fog<0) {o.color=float4(0.002,0.003,0.004,1);return o;}
    float3 c=Diffuse.Sample(GroundSampler,p.uv).rgb;
    c=lerp(c,float3(0.005,0.10,0.19),p.water*0.72);
    o.color=float4(c*p.light*p.fog,1);return o;}
)HLSL";
        ComPtr<ID3DBlob> vsBytes,psBytes,diagnostic;
        Check(D3DCompile(shader,sizeof(shader)-1,"WorldTerrainRenderer",nullptr,nullptr,"vertexMain","vs_5_0",
            D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_WARNINGS_ARE_ERRORS,0,&vsBytes,&diagnostic),"Terrain vertex shader compilation");
        Check(D3DCompile(shader,sizeof(shader)-1,"WorldTerrainRenderer",nullptr,nullptr,"pixelMain","ps_5_0",
            D3DCOMPILE_ENABLE_STRICTNESS|D3DCOMPILE_WARNINGS_ARE_ERRORS,0,&psBytes,&diagnostic),"Terrain pixel shader compilation");
        Check(device->CreateVertexShader(vsBytes->GetBufferPointer(),vsBytes->GetBufferSize(),nullptr,&vs),"Terrain vertex shader");
        Check(device->CreatePixelShader(psBytes->GetBufferPointer(),psBytes->GetBufferSize(),nullptr,&ps),"Terrain pixel shader");
        const D3D11_INPUT_ELEMENT_DESC elements[]={
            {"POSITION",0,DXGI_FORMAT_R32G32B32_FLOAT,0,0,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",0,DXGI_FORMAT_R32G32_FLOAT,0,12,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",1,DXGI_FORMAT_R32_FLOAT,0,20,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",2,DXGI_FORMAT_R32_FLOAT,0,24,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",3,DXGI_FORMAT_R32_FLOAT,0,28,D3D11_INPUT_PER_VERTEX_DATA,0},
            {"TEXCOORD",4,DXGI_FORMAT_R32_UINT,0,32,D3D11_INPUT_PER_VERTEX_DATA,0}};
        Check(device->CreateInputLayout(elements,static_cast<UINT>(std::size(elements)),vsBytes->GetBufferPointer(),vsBytes->GetBufferSize(),&layout),"Terrain vertex layout");
        D3D11_BUFFER_DESC cb{};cb.ByteWidth=64;cb.Usage=D3D11_USAGE_DEFAULT;cb.BindFlags=D3D11_BIND_CONSTANT_BUFFER;
        Check(device->CreateBuffer(&cb,nullptr,&constants),"Terrain camera buffer");
        cb.ByteWidth=16;Check(device->CreateBuffer(&cb,nullptr,&clipConstants),"Terrain reflection clip buffer");
        D3D11_SAMPLER_DESC sd{};sd.Filter=D3D11_FILTER_ANISOTROPIC;sd.AddressU=sd.AddressV=sd.AddressW=D3D11_TEXTURE_ADDRESS_WRAP;
        sd.MaxAnisotropy=4;sd.ComparisonFunc=D3D11_COMPARISON_NEVER;sd.MaxLOD=D3D11_FLOAT32_MAX;
        Check(device->CreateSamplerState(&sd,&sampler),"Terrain sampler");
        D3D11_RASTERIZER_DESC rd{};rd.FillMode=D3D11_FILL_SOLID;rd.CullMode=D3D11_CULL_NONE;rd.DepthClipEnable=TRUE;
        Check(device->CreateRasterizerState(&rd,&raster),"Terrain rasterizer");
        D3D11_DEPTH_STENCIL_DESC dd{};dd.DepthEnable=TRUE;dd.DepthWriteMask=D3D11_DEPTH_WRITE_MASK_ALL;dd.DepthFunc=D3D11_COMPARISON_LESS;
        Check(device->CreateDepthStencilState(&dd,&depthState),"Terrain depth state");
        D3D11_BLEND_DESC blend{};blend.RenderTarget[0].RenderTargetWriteMask=D3D11_COLOR_WRITE_ENABLE_ALL;
        Check(device->CreateBlendState(&blend,&blendState),"Terrain opaque blend state");
        Reader r(path);
        if(std::memcmp(r.data.data(),"ZSTERR02",8)==0){original=LoadOriginalCatalog(device.Get(),std::move(r.data));return;}
        Require(std::memcmp(r.Take(8),"ZSTERR01",8)==0 && r.U32()==1,"Unknown terrain package version");
        const unsigned count=r.U32();Require(count>0 && count<=96,"Invalid terrain material count");
        for(unsigned i=0;i<count;++i){
            const unsigned continent=r.U32(),id=r.U32(),bytes=r.U32();
            Require(continent<=4 && id<=255 && bytes>=128,"Invalid terrain material record");
            const auto* dds=r.Take(bytes);
            Require(std::memcmp(dds,"DDS ",4)==0 && Word(dds+4)==124 && Word(dds+76)==32 &&
                    Word(dds+80)==4 && Word(dds+84)==0x35545844 && Word(dds+112)==0,"Terrain diffuse is not bounded 2D BC3 DDS");
            const unsigned w=Word(dds+16),h=Word(dds+12),mips=std::max(1u,Word(dds+28));
            Require(w>0 && h>0 && w<=4096 && h<=4096 && mips<=13,"Terrain diffuse dimensions exceed bounds");
            std::vector<D3D11_SUBRESOURCE_DATA> levelsData;std::size_t offset=128;
            for(unsigned m=0;m<mips;++m){
                const unsigned mw=std::max(1u,w>>m),mh=std::max(1u,h>>m),pitch=((mw+3)/4)*16;
                const std::size_t size=static_cast<std::size_t>(pitch)*((mh+3)/4);
                Require(size<=bytes-offset,"Truncated terrain BC3 mip chain");
                levelsData.push_back({dds+offset,pitch,static_cast<UINT>(size)});offset+=size;
            }
            Require(offset==bytes,"Unexpected terrain DDS trailing payload");
            D3D11_TEXTURE2D_DESC td{};td.Width=w;td.Height=h;td.MipLevels=mips;td.ArraySize=1;
            td.Format=DXGI_FORMAT_BC3_UNORM_SRGB;td.SampleDesc.Count=1;td.Usage=D3D11_USAGE_IMMUTABLE;td.BindFlags=D3D11_BIND_SHADER_RESOURCE;
            ComPtr<ID3D11Texture2D> texture;Check(device->CreateTexture2D(&td,levelsData.data(),&texture),"Terrain diffuse upload");
            Material material;Check(device->CreateShaderResourceView(texture.Get(),nullptr,&material.texture),"Terrain diffuse view");
            Require(materials.emplace(std::make_pair(continent,id),std::move(material)).second,"Duplicate terrain material identity");
        }
        Require(r.U32()==pieces.size(),"Incomplete terrain height pieces");std::set<unsigned> seen;
        for(unsigned i=0;i<pieces.size();++i){
            const unsigned kind=r.U32(),bytes=r.U32();Require(kind<pieces.size() && seen.insert(kind).second && bytes>=128,"Invalid height piece identity");
            const auto* dds=r.Take(bytes);const auto w=Word(dds+16),h=Word(dds+12);
            const unsigned mips=std::max(1u,Word(dds+28));std::size_t expected=128;
            Require(mips<=8,"Invalid terrain height mip count");
            for(unsigned mipLevel=0;mipLevel<mips;++mipLevel)expected+=static_cast<std::size_t>(std::max(1u,w>>mipLevel))*std::max(1u,h>>mipLevel)*8;
            Require(std::memcmp(dds,"DDS ",4)==0 && Word(dds+4)==124 && Word(dds+76)==32 && Word(dds+80)==4 &&
                Word(dds+84)==36 && w==128 && h==128 && bytes==expected && Word(dds+112)==0,
                "Terrain height piece is not a complete 128x128 A16B16G16R16 DDS");
            auto& p=pieces[kind];p.width=w;p.height=h;p.red.reserve(w*h);
            for(unsigned n=0;n<w*h;++n){const auto* channels=dds+128+n*8;
                Require(std::memcmp(channels,channels+2,2)==0 && std::memcmp(channels,channels+4,2)==0,"Height RGB channels disagree");
                p.red.push_back(static_cast<std::uint16_t>(channels[0]|(static_cast<unsigned>(channels[1])<<8)));}
        }
        Require(r.cursor==r.data.size(),"Trailing terrain package records");
    }
};
unsigned MaterialId(const WorldViewPlot& p){
    if(!p.revealed)return 2;
    if(p.water)return p.terrain.find("COAST")!=std::string::npos?5u:15u;
    if(p.mountain)return 10;
    if(p.terrain.find("DESERT")!=std::string::npos)return 26;
    if(p.terrain.find("PLAINS")!=std::string::npos)return 27;
    if(p.terrain.find("SNOW")!=std::string::npos)return 30;
    if(p.terrain.find("TUNDRA")!=std::string::npos)return p.hills?32u:44u;
    if(p.feature.find("MARSH")!=std::string::npos)return 0;
    return 2;
}
float SampleHeight(const Piece& p,float x,float z){
    const float u=std::clamp(x+0.5f,0.0f,1.0f)*static_cast<float>(p.width-1);
    const float v=std::clamp(0.5f-z/1.15470053838f,0.0f,1.0f)*static_cast<float>(p.height-1);
    const auto ix=static_cast<unsigned>(u),iy=static_cast<unsigned>(v);
    const auto jx=std::min(ix+1,p.width-1),jy=std::min(iy+1,p.height-1);
    const float a=u-static_cast<float>(ix),b=v-static_cast<float>(iy);
    const float top=(1-a)*p.red[iy*p.width+ix]+a*p.red[iy*p.width+jx];
    const float bottom=(1-a)*p.red[jy*p.width+ix]+a*p.red[jy*p.width+jx];
    return (1-b)*top+b*bottom;
}
// Preserve sampled source relief, but fade to a shared zero edge until retail
// piece neighbourhood assembly and height units have been reconstructed.
float Height(const Cache& cache,const WorldViewPlot& p,float x,float z,float edge){
    if(!p.revealed || p.water || (!p.hills&&!p.mountain))return 0;
    const auto& piece=cache.pieces[p.mountain?2:1];
    const float relief=std::max(0.0f,(SampleHeight(piece,x,z)-15300.0f)/65535.0f);
    const float t=std::clamp((1-edge)*6.0f,0.0f,1.0f);
    return relief*2.3f*(t*t*(3-2*t));
}
#include "OriginalLightingGpu.inc"
#include "OriginalLightingFieldGpu.inc"
#include "OriginalLightingFieldBridge.inc"
#include "OriginalScreenLightingGpu.inc"
#include "OriginalTerrainGpu.inc"
FrameTargets& Targets(Cache& cache,unsigned width,unsigned height,bool fogEnabled,bool surfaceEnabled,bool lightingEnabled){
    if(cache.targets && cache.targets->width==width && cache.targets->height==height && cache.targets->fogEnabled==fogEnabled&&cache.targets->surfaceEnabled==surfaceEnabled&&cache.targets->lightingEnabled==lightingEnabled)return *cache.targets;
    auto next=std::make_unique<FrameTargets>();next->width=width;next->height=height;next->fogEnabled=fogEnabled;next->surfaceEnabled=surfaceEnabled;next->lightingEnabled=lightingEnabled;
    D3D11_TEXTURE2D_DESC td{};td.Width=width;td.Height=height;td.MipLevels=td.ArraySize=1;td.SampleDesc.Count=1;
    td.Usage=D3D11_USAGE_DEFAULT;td.BindFlags=D3D11_BIND_RENDER_TARGET|(fogEnabled?D3D11_BIND_SHADER_RESOURCE:0);
    td.Format=fogEnabled||surfaceEnabled||lightingEnabled?DXGI_FORMAT_B8G8R8A8_TYPELESS:DXGI_FORMAT_B8G8R8A8_UNORM_SRGB;
    Check(cache.device->CreateTexture2D(&td,nullptr,&next->color),"Terrain color target");
    D3D11_RENDER_TARGET_VIEW_DESC colorView{};colorView.Format=DXGI_FORMAT_B8G8R8A8_UNORM_SRGB;colorView.ViewDimension=D3D11_RTV_DIMENSION_TEXTURE2D;
    Check(cache.device->CreateRenderTargetView(next->color.Get(),&colorView,&next->colorView),"Terrain color view");
    if(surfaceEnabled||lightingEnabled){colorView.Format=DXGI_FORMAT_B8G8R8A8_UNORM;
        Check(cache.device->CreateRenderTargetView(next->color.Get(),&colorView,&next->colorRawView),"Encoded terrain and water colour view");}
    if(fogEnabled){
        D3D11_SHADER_RESOURCE_VIEW_DESC view{};view.Format=DXGI_FORMAT_B8G8R8A8_UNORM;view.ViewDimension=D3D11_SRV_DIMENSION_TEXTURE2D;view.Texture2D.MipLevels=1;
        Check(cache.device->CreateShaderResourceView(next->color.Get(),&view,&next->colorResource),"Original fog scene colour view");
        td.Format=DXGI_FORMAT_B8G8R8A8_UNORM;td.BindFlags=D3D11_BIND_RENDER_TARGET;
        Check(cache.device->CreateTexture2D(&td,nullptr,&next->fogColor),"Original fog colour target");
        Check(cache.device->CreateRenderTargetView(next->fogColor.Get(),nullptr,&next->fogColorView),"Original fog colour view");
        td.Format=DXGI_FORMAT_R8_UINT;td.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;
        Check(cache.device->CreateTexture2D(&td,nullptr,&next->waterFragment),"Water fragment fog marker target");
        Check(cache.device->CreateRenderTargetView(next->waterFragment.Get(),nullptr,&next->waterFragmentView),"Water fragment fog marker view");
        Check(cache.device->CreateShaderResourceView(next->waterFragment.Get(),nullptr,&next->waterFragmentResource),"Water fragment fog marker resource");
    }
    td.BindFlags=D3D11_BIND_RENDER_TARGET;
    td.Format=DXGI_FORMAT_R32_UINT;Check(cache.device->CreateTexture2D(&td,nullptr,&next->ids),"Terrain plot ID target");
    Check(cache.device->CreateRenderTargetView(next->ids.Get(),nullptr,&next->idView),"Terrain ID view");
    td.Format=fogEnabled?DXGI_FORMAT_R32_TYPELESS:DXGI_FORMAT_D32_FLOAT;
    td.BindFlags=D3D11_BIND_DEPTH_STENCIL|(fogEnabled?D3D11_BIND_SHADER_RESOURCE:0);
    Check(cache.device->CreateTexture2D(&td,nullptr,&next->depth),"Terrain depth buffer");
    D3D11_DEPTH_STENCIL_VIEW_DESC depthView{};depthView.Format=DXGI_FORMAT_D32_FLOAT;depthView.ViewDimension=D3D11_DSV_DIMENSION_TEXTURE2D;
    Check(cache.device->CreateDepthStencilView(next->depth.Get(),&depthView,&next->depthView),"Terrain depth view");
    if(fogEnabled){
        D3D11_SHADER_RESOURCE_VIEW_DESC view{};view.Format=DXGI_FORMAT_R32_FLOAT;view.ViewDimension=D3D11_SRV_DIMENSION_TEXTURE2D;view.Texture2D.MipLevels=1;
        Check(cache.device->CreateShaderResourceView(next->depth.Get(),&view,&next->depthResource),"Original fog depth view");
    }
    if(cache.original){
        td.Format=DXGI_FORMAT_R16G16B16A16_FLOAT;td.BindFlags=D3D11_BIND_RENDER_TARGET;
        Check(cache.device->CreateTexture2D(&td,nullptr,&next->specular),"Original squared specular target");
        Check(cache.device->CreateRenderTargetView(next->specular.Get(),nullptr,&next->specularView),"Original squared specular view");
        td.Format=DXGI_FORMAT_R16_FLOAT;
        Check(cache.device->CreateTexture2D(&td,nullptr,&next->materialHeight),"Original mixed material height target");
        Check(cache.device->CreateRenderTargetView(next->materialHeight.Get(),nullptr,&next->materialHeightView),"Original mixed material height view");
    }
    cache.targets.swap(next);return *cache.targets;
}
#include "OriginalFogGpu.inc"
#include "OriginalWaterGpu.inc"
#include "WorldTerrainUnits.inc"
#include "OriginalDynamicShadowGpu.inc"
#include "OriginalWaterSurfaceTargets.inc"
#include "OriginalWaterReflection.inc"
#include "OriginalWaterSurfaceGpu.inc"
void ReadBack(Cache& cache,ID3D11Texture2D* texture,ComPtr<ID3D11Texture2D>& staging,
              void* destination,unsigned width,unsigned height){
    if(!staging){
        D3D11_TEXTURE2D_DESC desc{};texture->GetDesc(&desc);desc.Usage=D3D11_USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
        Check(cache.device->CreateTexture2D(&desc,nullptr,&staging),"Terrain readback buffer");
    }
    cache.context->CopyResource(staging.Get(),texture);D3D11_MAPPED_SUBRESOURCE mapped{};
    Check(cache.context->Map(staging.Get(),0,D3D11_MAP_READ,0,&mapped),"Terrain readback map");
    auto* target=static_cast<unsigned char*>(destination);const auto* source=static_cast<const unsigned char*>(mapped.pData);
    for(unsigned y=0;y<height;++y)std::memcpy(target+static_cast<std::size_t>(y)*width*4,source+static_cast<std::size_t>(y)*mapped.RowPitch,width*4);
    cache.context->Unmap(staging.Get(),0);
}

}
namespace {
bool RenderWorldTerrainImpl(const WorldView& view,std::uint32_t width,std::uint32_t height,std::uint32_t mapWidth,
                            Cache& cache,ID3D11Texture2D* callerTarget,TerrainFrame* frame,std::wstring* error){
    try{
        Require(frame && width>0 && height>0 && width<=4096 && height<=4096 && mapWidth>0 && mapWidth<=width,"Invalid terrain render dimensions");
        Require(!view.terrainAssetsPath.empty() && view.plots.size()<=500000,"Terrain assets or bounded world snapshot missing");
        Require(view.gridWidth>0 && view.gridHeight>0 && std::isfinite(view.tileWidth) && view.tileWidth>=WorldCameraZoom::Minimum && view.tileWidth<=WorldCameraZoom::Maximum,"Invalid terrain camera");
        Require(!cache.original || !view.wrapY || view.gridHeight%2==0,"Original terrain requires even row count for vertical wrapping");
        const bool fogEnabled=!view.fogAssetsPath.empty();
        const bool waterEnabled=!view.waterAssetsPath.empty();
        const bool surfaceEnabled=!view.waterSurfaceAssetsPath.empty();
        const bool lightingEnabled=!view.lightingAssetsPath.empty();
        const auto screenPolicy=OSL::ResolvePolicy(view.screenLightingPolicy);
        const unsigned reflectionSide=screenPolicy.reflection?OSL::OriginalReflectionSide:OSL::OriginalDisabledReflectionSide;
        Require(!lightingEnabled||cache.original,"Original lighting requires original V2 terrain");
        std::unique_ptr<LightingCatalog> lightingCandidate;LightingCatalog* activeLighting=nullptr;
        if(lightingEnabled){
            if(!cache.lighting||cache.lighting->path!=view.lightingAssetsPath)lightingCandidate=LoadLightingCatalog(cache,view.lightingAssetsPath);
            activeLighting=lightingCandidate?lightingCandidate.get():cache.lighting.get();
        }
        Require(!surfaceEnabled||(waterEnabled&&cache.original),"Water surface mode requires original V2 terrain and water assets");
        std::unique_ptr<WaterSurfaceCatalog> surfaceCandidate;
        std::unique_ptr<WaterSurfaceGeometry> surfaceGeometryCandidate;
        std::unique_ptr<SurfaceTargets> surfaceTargetsCandidate;
        std::unique_ptr<ScreenLightCatalog> screenLightCandidate;
        ScreenLightCatalog* activeScreenLight=nullptr;
        const bool screenLightEnabled=!view.screenLightingAssetsPath.empty();
        Require(!screenLightEnabled||lightingEnabled,"Screen light mode requires the original lighting package");
        if(screenLightEnabled){
            if(!cache.screenLight||cache.screenLight->path!=view.screenLightingAssetsPath)
                screenLightCandidate=LoadOriginalScreenLightCatalog(cache,view.screenLightingAssetsPath);
            activeScreenLight=screenLightCandidate?screenLightCandidate.get():cache.screenLight.get();
        }
        WaterSurfaceCatalog* activeSurface=nullptr;const WaterSurfaceGeometry* surfaceGeometry=nullptr;SurfaceTargets* surfaceTargets=nullptr;
        if(surfaceEnabled){
            if(!cache.waterSurface||cache.waterSurface->path!=view.waterSurfaceAssetsPath)surfaceCandidate=LoadWaterSurfaceCatalog(cache,view.waterSurfaceAssetsPath);
            activeSurface=surfaceCandidate?surfaceCandidate.get():cache.waterSurface.get();
        }
        Require(!waterEnabled||cache.original,"Original water requires the sealed V2 terrain renderer");
        Require(!waterEnabled||(std::isfinite(view.waterAnimationSeconds)&&std::abs(view.waterAnimationSeconds)<=1000000000),"Invalid water presentation clock");
        std::unique_ptr<WaterCatalog> waterCandidate;std::unique_ptr<WaterGeometry> waterGeometryCandidate;
        WaterCatalog* activeWater=nullptr;const WaterGeometry* waterGeometry=nullptr;
        OW::Grid waterGrid;
        if(waterEnabled){
            waterGrid=OW::CaptureWaterGrid(view);
            if(!cache.water||cache.water->path!=view.waterAssetsPath)waterCandidate=LoadWaterCatalog(cache,view.waterAssetsPath);
            activeWater=waterCandidate?waterCandidate.get():cache.water.get();
        }
        Require(!fogEnabled || cache.original,"Original fog requires the sealed V2 terrain renderer");
        Require(!fogEnabled || (std::isfinite(view.fogAnimationSeconds)&&std::abs(view.fogAnimationSeconds)<=1000000000),"Invalid original fog presentation clock");
        std::unique_ptr<FogCatalog> fogCandidate;
        std::unique_ptr<FogMask> maskCandidate;
        FogCatalog* activeFog=nullptr;const FogMask* fogMask=nullptr;
        if(fogEnabled){
            if(!cache.fog || cache.fog->path!=view.fogAssetsPath)fogCandidate=LoadFogCatalog(cache,view.fogAssetsPath);
            activeFog=fogCandidate?fogCandidate.get():cache.fog.get();
            auto state=OF::CaptureFogGrid(view);
            if(!activeFog->mask || !OF::SameFogGrid(activeFog->mask->key,state))maskCandidate=PrepareFogMask(cache,std::move(state));
            fogMask=maskCandidate?maskCandidate.get():activeFog->mask.get();
        }
        const auto deviceTag=reinterpret_cast<std::uintptr_t>(cache.device.Get());
        const auto contextTag=reinterpret_cast<std::uintptr_t>(cache.context.Get());
        const GroundData* groundData=cache.ground.Find(view,width,height,mapWidth,deviceTag,contextTag);
        std::unique_ptr<GroundData> candidate;
        std::unique_ptr<WorldTerrainGroundKey> candidateKey;
        TerrainFrame result;
        if(groundData)result=groundData->metadata;
        else{
            candidateKey=std::make_unique<WorldTerrainGroundKey>(WorldTerrainGroundKey::Capture(view,width,height,mapWidth,deviceTag,contextTag));
            candidate=std::make_unique<GroundData>();
        }
        result.hardware=cache.hardware;
        if(!view.unitAssetsPath.empty()&&(!cache.units||cache.units->path!=view.unitAssetsPath)){
            auto units=std::make_unique<UnitAssetCatalog>(UnitAssetCatalog::Load(cache.device.Get(),view.unitAssetsPath));
            cache.units=std::move(units);cache.unitBuffers.clear();
        }
        if(!view.unitAssetsPath.empty())cache.units->Animate(view.animationSeconds);
        else cache.unitBuffers.clear();
        const float distance=static_cast<float>(height)/(2.0f*std::tan(XM_PIDIV4/2)*view.tileWidth*1.5f);
        const auto camera=XMMatrixLookAtLH(XMVectorSet(0,distance*0.65f,-distance*0.7599342f,0),XMVectorZero(),XMVectorSet(0,1,0,0));
        const auto projection=XMMatrixPerspectiveFovLH(XM_PIDIV4,static_cast<float>(mapWidth)/static_cast<float>(height),0.1f,150.0f);
        const auto matrix=camera*projection;XMFLOAT4X4 constants;XMStoreFloat4x4(&constants,matrix);
        cache.context->UpdateSubresource(cache.constants.Get(),0,nullptr,&constants,0,0);
        if(candidate){
            if(cache.original)PrepareOriginalGround(view,cache,camera,matrix,width,height,mapWidth,*candidate,result);
            else{
            std::map<std::pair<unsigned,unsigned>,Group> groups;
            const float corners[6][2]={{0,0.577350269f},{0.5f,0.288675135f},{0.5f,-0.288675135f},
                                      {0,-0.577350269f},{-0.5f,-0.288675135f},{-0.5f,0.288675135f}};
            for(const auto& p:view.plots){
                int dx=p.x-view.cameraX,dy=p.y-view.cameraY;
                if(view.wrapX){if(dx>view.gridWidth/2)dx-=view.gridWidth;else if(dx<-view.gridWidth/2)dx+=view.gridWidth;}
                if(view.wrapY){if(dy>view.gridHeight/2)dy-=view.gridHeight;else if(dy<-view.gridHeight/2)dy+=view.gridHeight;}
                if(std::abs(dx)>48 || std::abs(dy)>48)continue;
                const float wx=static_cast<float>(dx)+static_cast<float>((p.y&1)-(view.cameraY&1))*0.5f,wz=-static_cast<float>(dy)*0.866025404f;
                const auto inCamera=XMVector3TransformCoord(XMVectorSet(wx,0.5f,wz,0),camera);
                const float cz=XMVectorGetZ(inCamera),extent=(cz+3)*std::tan(XM_PIDIV4/2);
                if(cz < -3 || cz>153 || std::abs(XMVectorGetX(inCamera))>extent*static_cast<float>(mapWidth)/static_cast<float>(height)+3 ||
                   std::abs(XMVectorGetY(inCamera))>extent+3)continue;
                const unsigned id=MaterialId(p);unsigned continent=p.revealed?static_cast<unsigned>(p.continent):4u;
                if(continent>4)continent=4;
                if(p.revealed && (p.water || p.terrain.find("SNOW")!=std::string::npos))continent=0;
                auto material=std::make_pair(continent,id);
                if(!cache.materials.count(material))material={0,id};
                if(!cache.materials.count(material))material={4,id};
                Require(cache.materials.count(material)!=0,"Selected terrain material is absent from the original catalog");
                auto& vertices=groups[material].vertices;
                unsigned pick=0;if(p.revealed&&p.visible){
                    Require(p.index>=0,"Invalid terrain plot index");result.picking.keys.push_back(WorldViewHitKey::Plot(p.index));
                    pick=static_cast<unsigned>(result.picking.keys.size());}
                const float fog=!p.revealed?-1.0f:p.visible?1.0f:0.30f;
                const unsigned divisions=p.revealed && (p.hills||p.mountain)?(cz>distance*2?6u:12u):1u;
                Require(result.triangles+6ull*divisions*divisions<=3000000,"Terrain mesh exceeds its triangle bound");
                const auto vertex=[&](unsigned sector,unsigned a,unsigned b){
                    const float fa=static_cast<float>(a)/static_cast<float>(divisions),fb=static_cast<float>(b)/static_cast<float>(divisions);
                    const auto* c=corners[sector];const auto* d=corners[(sector+1)%6];
                    const float x=c[0]*fa+d[0]*fb,z=c[1]*fa+d[1]*fb;
                    // World UVs remain stable when the camera pans. Their units are
                    // provisional until original TerrainDef texture scale is calibrated.
                    return Vertex{wx+x,Height(cache,p,x,z,fa+fb),wz+z,
                        (static_cast<float>(p.x)+static_cast<float>(p.y&1)*0.5f+x)*0.8f,
                        (-static_cast<float>(p.y)*0.866025404f+z)*0.8f,1,fog,p.revealed&&p.water?1.0f:0.0f,pick};
                };
                const auto triangle=[&](Vertex a,Vertex b,Vertex c){
                    const auto normal=XMVector3Normalize(XMVector3Cross(XMVectorSet(b.x-a.x,b.y-a.y,b.z-a.z,0),XMVectorSet(c.x-a.x,c.y-a.y,c.z-a.z,0)));
                    const float lit=0.48f+0.52f*std::abs(XMVectorGetX(XMVector3Dot(normal,XMVector3Normalize(XMVectorSet(-0.4f,0.8f,-0.4f,0)))));
                    a.light=b.light=c.light=lit;vertices.push_back(a);vertices.push_back(b);vertices.push_back(c);++result.triangles;
                };
                for(unsigned s=0;s<6;++s)for(unsigned a=0;a<divisions;++a)for(unsigned b=0;b<divisions-a;++b){
                    triangle(vertex(s,a,b),vertex(s,a+1,b),vertex(s,a,b+1));
                    if(a+b+1<divisions)triangle(vertex(s,a+1,b),vertex(s,a+1,b+1),vertex(s,a,b+1));
                }
                const auto projected=XMVector4Transform(XMVectorSet(wx,Height(cache,p,0,0,0),wz,1),matrix);
                const float pw=XMVectorGetW(projected),pz=XMVectorGetZ(projected);
                if(pw>0 && pz>=0 && pz<=pw){
                    const float px=(XMVectorGetX(projected)/pw+1)*0.5f*static_cast<float>(mapWidth);
                    const float py=(1-XMVectorGetY(projected)/pw)*0.5f*static_cast<float>(height);
                    if(px>=0 && px<static_cast<float>(mapWidth) && py>=0 && py<static_cast<float>(height))result.centers.emplace(p.index,TerrainProjection{px,py});
                }
            }
            Require(result.triangles<=3000000,"Terrain mesh exceeds its triangle bound");
            for(const auto& entry:groups){
                const auto& vertices=entry.second.vertices;Require(vertices.size()*sizeof(Vertex)<=UINT_MAX,"Terrain vertex buffer exceeds D3D11 bound");
                if(vertices.empty())continue;
                D3D11_BUFFER_DESC bd{};bd.ByteWidth=static_cast<UINT>(vertices.size()*sizeof(Vertex));bd.Usage=D3D11_USAGE_IMMUTABLE;bd.BindFlags=D3D11_BIND_VERTEX_BUFFER;
                D3D11_SUBRESOURCE_DATA initial{vertices.data(),0,0};GroundMesh mesh;mesh.count=static_cast<UINT>(vertices.size());
                Check(cache.device->CreateBuffer(&bd,&initial,&mesh.buffer),"Terrain mesh upload");
                candidate->groups.emplace(entry.first,std::move(mesh));
            }
            }
            groundData=candidate.get();
        }
        if(lightingEnabled)PrepareLightingFields(view,cache,*groundData->original);
        if(waterEnabled){
            if(!activeWater->geometry||activeWater->geometry->riversOnly!=surfaceEnabled||!OW::SameWaterGrid(activeWater->geometry->key,waterGrid)||
                activeWater->geometry->surface.lock()!=groundData->original->surface)
                waterGeometryCandidate=PrepareWaterGeometry(cache,*activeWater,waterGrid,groundData->original->surface,surfaceEnabled);
            waterGeometry=waterGeometryCandidate?waterGeometryCandidate.get():activeWater->geometry.get();
        }
        if(surfaceEnabled){
            if(!activeSurface->geometry||!OW::SameWaterGrid(activeSurface->geometry->key,waterGrid)||
                activeSurface->geometry->surface.lock()!=groundData->original->surface)
                surfaceGeometryCandidate=PrepareWaterSurfaceGeometry(cache,std::move(waterGrid),groundData->original->surface);
            surfaceGeometry=surfaceGeometryCandidate?surfaceGeometryCandidate.get():activeSurface->geometry.get();
            if(surfaceGeometry->vertices){
                if(!activeSurface->targets||activeSurface->targets->width!=width||activeSurface->targets->height!=height||activeSurface->targets->mapWidth!=mapWidth||activeSurface->targets->reflectionWidth!=reflectionSide)
                    surfaceTargetsCandidate=CreateWaterSurfaceTargets(cache,width,height,mapWidth,reflectionSide);
                surfaceTargets=surfaceTargetsCandidate?surfaceTargetsCandidate.get():activeSurface->targets.get();
            }
        }
        const auto unitGroups=PrepareTerrainUnits(view,cache,*groundData,result);UploadTerrainUnits(cache,unitGroups);
        auto& surfaces=Targets(cache,width,height,fogEnabled,surfaceEnabled,lightingEnabled);
        if(surfaceTargets)DrawDynamicShadow(view,cache,*groundData->original,unitGroups);
        else cache.dynamicShadow.reset();
        SurfaceTargets* reflectionTargets=surfaceTargets;
        if(reflectionTargets){
            if(screenPolicy.reflection)DrawWaterReflection(cache,*groundData,unitGroups,*reflectionTargets,matrix,WB::WorldPlaneCandidate);
            else{
                // Equivalent black input for disabled reflection; do not render
                // an unnecessary scene or retain a stale previous reflection.
                reflectionTargets->reflectionProjectionValid=false;
                ID3D11ShaderResourceView* clear[45]{};cache.context->PSSetShaderResources(0,45,clear);
                cache.context->OMSetRenderTargets(0,nullptr,nullptr);const float black[4]={0,0,0,0};
                cache.context->ClearRenderTargetView(reflectionTargets->reflectionRawView.Get(),black);
                cache.context->ClearDepthStencilView(reflectionTargets->reflectionDepthView.Get(),D3D11_CLEAR_DEPTH,1,0);
            }
        }
        const float background[4]={0.002f,0.003f,0.004f,1},zero[4]={0,0,0,0};
        // Working color/depth are cleared on every pose. Cached metadata is
        // ground-only; no depth containing an old unit pose is restored.
        cache.context->ClearRenderTargetView(surfaces.colorView.Get(),background);cache.context->ClearRenderTargetView(surfaces.idView.Get(),zero);
        if(fogEnabled)cache.context->ClearRenderTargetView(surfaces.waterFragmentView.Get(),zero);
        cache.context->ClearDepthStencilView(surfaces.depthView.Get(),D3D11_CLEAR_DEPTH,1,0);
        ID3D11RenderTargetView* targets[]={lightingEnabled?surfaces.colorRawView.Get():surfaces.colorView.Get(),surfaces.idView.Get(),surfaces.specularView.Get(),surfaces.materialHeightView.Get()};
        if(cache.original){cache.context->ClearRenderTargetView(surfaces.specularView.Get(),zero);cache.context->ClearRenderTargetView(surfaces.materialHeightView.Get(),zero);}
        cache.context->OMSetRenderTargets(cache.original?4:2,targets,surfaces.depthView.Get());
        cache.context->OMSetDepthStencilState(cache.depthState.Get(),0);cache.context->OMSetBlendState(cache.blendState.Get(),nullptr,0xffffffffu);
        cache.context->RSSetState(cache.raster.Get());
        D3D11_VIEWPORT viewport{0,0,static_cast<float>(mapWidth),static_cast<float>(height),0,1};cache.context->RSSetViewports(1,&viewport);
        cache.context->IASetInputLayout(cache.layout.Get());cache.context->IASetPrimitiveTopology(D3D11_PRIMITIVE_TOPOLOGY_TRIANGLELIST);
        cache.context->VSSetShader(cache.vs.Get(),nullptr,0);cache.context->PSSetShader(cache.ps.Get(),nullptr,0);
        cache.context->GSSetShader(nullptr,nullptr,0);cache.context->HSSetShader(nullptr,nullptr,0);cache.context->DSSetShader(nullptr,nullptr,0);
        cache.context->SOSetTargets(0,nullptr,nullptr);cache.context->SetPredication(nullptr,FALSE);
        ID3D11Buffer* cb=cache.constants.Get();cache.context->VSSetConstantBuffers(0,1,&cb);
        const float noClip[4]={0,0,0,0};cache.context->UpdateSubresource(cache.clipConstants.Get(),0,nullptr,noClip,0,0);
        ID3D11Buffer* clip=cache.clipConstants.Get();cache.context->PSSetConstantBuffers(2,1,&clip);
        ID3D11SamplerState* sampler=cache.sampler.Get();cache.context->PSSetSamplers(0,1,&sampler);
        if(groundData->original)DrawOriginalGround(view,cache,*groundData->original,matrix,fogEnabled,activeLighting,
            activeScreenLight?activeScreenLight->texture.Get():nullptr,mapWidth,height);
        else for(const auto& entry:groundData->groups){
            ID3D11Buffer* vb=entry.second.buffer.Get();const UINT stride=sizeof(Vertex),offset=0;cache.context->IASetVertexBuffers(0,1,&vb,&stride,&offset);
            ID3D11ShaderResourceView* texture=cache.materials.at(entry.first).texture.Get();cache.context->PSSetShaderResources(0,1,&texture);
            cache.context->Draw(entry.second.count,0);
        }
        if(waterEnabled)DrawOriginalWater(view,cache,*activeWater,*waterGeometry,*groundData->original,surfaces,distance,fogEnabled);
        if(surfaceTargets){
            if(fogEnabled)DrawOriginalFog(view,cache,surfaces,*activeFog,*fogMask,*groundData->original,matrix,distance,mapWidth,height,true);
            DrawWaterSurface(view,cache,*activeWater,*activeSurface,*surfaceGeometry,*groundData->original,surfaces,*surfaceTargets,matrix,distance,mapWidth,height,fogEnabled,activeFog,fogMask);
        }
        if(!unitGroups.empty()){
            ID3D11RenderTargetView* output[]={surfaces.colorView.Get(),nullptr,nullptr,nullptr,surfaces.waterFragmentView.Get()};
            cache.context->OMSetRenderTargets(fogEnabled?5:1,output,surfaces.depthView.Get());
            DrawTerrainUnits(cache,unitGroups);
        }
        cache.context->OMSetRenderTargets(0,nullptr,nullptr);
        ID3D11ShaderResourceView* nullResource=nullptr;cache.context->PSSetShaderResources(0,1,&nullResource);
        ID3D11Buffer* noClipBuffer=nullptr;cache.context->PSSetConstantBuffers(2,1,&noClipBuffer);
        if(fogEnabled)DrawOriginalFog(view,cache,surfaces,*activeFog,*fogMask,*groundData->original,matrix,distance,mapWidth,height);
        ID3D11Texture2D* finalColour=fogEnabled?surfaces.fogColor.Get():surfaces.color.Get();
        if(!callerTarget){
            result.bgra.resize(static_cast<std::size_t>(width)*height*4);
            ReadBack(cache,finalColour,surfaces.colorStaging,result.bgra.data(),width,height);
        }
        if(candidate){
            result.picking.indices.resize(static_cast<std::size_t>(width)*height);
            ReadBack(cache,surfaces.ids.Get(),surfaces.idStaging,result.picking.indices.data(),width,height);
            for(auto it=result.centers.begin();it!=result.centers.end();){
                // Projected vertices can land on a silhouette between pixel centres.
                // Keep the nearest covered sample of this same plot, never a sample
                // from an occluding neighbour. Fully occluded anchors stay absent.
                const int px=static_cast<int>(it->second.x),py=static_cast<int>(it->second.y);
                int selectedX=-1,selectedY=-1,best=100;
                for(int oy=-4;oy<=4;++oy)for(int ox=-4;ox<=4;++ox){
                    const int x=px+ox,y=py+oy,score=ox*ox+oy*oy;
                    if(x<0||y<0||x>=static_cast<int>(mapWidth)||y>=static_cast<int>(height)||score>=best)continue;
                    const auto key=result.picking.indices[static_cast<std::size_t>(y)*width+static_cast<unsigned>(x)];
                    if(key>0 && key<=result.picking.keys.size() && result.picking.keys[key-1]==WorldViewHitKey::Plot(it->first)){
                        selectedX=x;selectedY=y;best=score;
                    }
                }
                if(selectedX<0)it=result.centers.erase(it);
                else{it->second={static_cast<float>(selectedX)+0.5f,static_cast<float>(selectedY)+0.5f};++it;}
            }
            // CityView highlights follow the visible raster contour, including
            // occlusion by a foreground hill, instead of a separate flat hex.
            for(unsigned y=0;y<height;++y){
                std::uint32_t runId=0;unsigned runX=0;
                const auto flush=[&](unsigned end){
                    if(!runId)return;
                    const auto key=result.picking.keys[runId-1];
                    const int index=static_cast<int>(static_cast<std::uint32_t>(key));
                    result.projectedPlots[index].spans.push_back({static_cast<int>(y),static_cast<int>(runX),static_cast<int>(end-runX)});
                };
                for(unsigned x=0;x<mapWidth;++x){
                    const auto offset=static_cast<std::size_t>(y)*width+x;
                    const auto id=result.picking.indices[offset];
                    const bool edge=id && (x==0 || x+1==mapWidth || y==0 || y+1==height ||
                        result.picking.indices[offset-1]!=id || result.picking.indices[offset+1]!=id ||
                        result.picking.indices[offset-width]!=id || result.picking.indices[offset+width]!=id);
                    const auto next=edge?id:0;
                    if(next!=runId){flush(x);runId=next;runX=x;}
                }
                flush(mapWidth);
            }
            for(const auto& center:result.centers){
                auto& plot=result.projectedPlots[center.first];plot.centerX=center.second.x;plot.centerY=center.second.y;plot.anchorVisible=true;
            }
            // Own a separate copy: WorldViewRenderer moves the returned picking and
            // projections into its scene, so they cannot also own this cache entry.
            candidate->metadata.picking=result.picking;
            candidate->metadata.centers=result.centers;
            candidate->metadata.projectedPlots=result.projectedPlots;
            candidate->metadata.triangles=result.triangles;
            candidate->metadata.bicubicPatches=result.bicubicPatches;
            candidate->metadata.terrainGridLevel=result.terrainGridLevel;
        }
        if(callerTarget)cache.context->CopyResource(callerTarget,finalColour);
        if(candidate){
            auto surface=candidate->original?candidate->original->surface:std::shared_ptr<OriginalSurface>();
            const auto lod=candidate->original?candidate->original->lod:OT::Lod::History{};
            cache.ground.Publish(std::move(*candidateKey),std::move(candidate));
            if(surface){
                surface->lastLod=lod;
                cache.original->surface=std::move(surface);
            }
        }
        // All potentially failing frame work precedes these no-throw owner swaps.
        if(maskCandidate)activeFog->mask=std::move(maskCandidate);
        if(fogCandidate)cache.fog=std::move(fogCandidate);
        if(waterGeometryCandidate)activeWater->geometry=std::move(waterGeometryCandidate);
        if(waterCandidate)cache.water=std::move(waterCandidate);
        if(surfaceGeometryCandidate)activeSurface->geometry=std::move(surfaceGeometryCandidate);
        if(surfaceTargetsCandidate)activeSurface->targets=std::move(surfaceTargetsCandidate);
        if(surfaceCandidate)cache.waterSurface=std::move(surfaceCandidate);
        if(screenLightCandidate)cache.screenLight=std::move(screenLightCandidate);
        else if(!screenLightEnabled)cache.screenLight.reset();
        if(lightingCandidate)cache.lighting=std::move(lightingCandidate);
        *frame=std::move(result);return true;
    }catch(const std::exception& ex){if(error){error->assign(L"Terrain renderer: ");for(const char* p=ex.what();*p;++p)error->push_back(static_cast<unsigned char>(*p));}return false;}
}
}

namespace {
void SetTerrainFailure(std::wstring* error,const std::exception& ex){
    if(!error)return;error->assign(L"Terrain renderer: ");
    for(const char* p=ex.what();*p;++p)error->push_back(static_cast<unsigned char>(*p));
}
}

namespace {
std::unique_ptr<Cache>& LegacyTerrainCache(){static thread_local std::unique_ptr<Cache> value;return value;}
std::unique_ptr<Cache>& GpuTerrainCache(){static thread_local std::unique_ptr<Cache> value;return value;}
}
void ReleaseWorldTerrainResources(){GpuTerrainCache().reset();LegacyTerrainCache().reset();}

bool RenderWorldTerrain(const WorldView& view,std::uint32_t width,std::uint32_t height,
                        std::uint32_t mapWidth,TerrainFrame* frame,std::wstring* error){
    try{
        Require(frame!=nullptr,"Terrain frame output is null");
        auto& retained=LegacyTerrainCache();
        if(!retained||retained->package!=view.terrainAssetsPath)
            retained=std::make_unique<Cache>(view.terrainAssetsPath);
        return RenderWorldTerrainImpl(view,width,height,mapWidth,*retained,nullptr,frame,error);
    }catch(const std::exception& ex){SetTerrainFailure(error,ex);return false;}
}

bool RenderWorldTerrainToTexture(const WorldView& view,std::uint32_t width,std::uint32_t height,
                                 std::uint32_t mapWidth,ID3D11Device* device,
                                 ID3D11DeviceContext* context,ID3D11Texture2D* targetTexture,
                                 TerrainFrame* frame,std::wstring* error){
    try{
        Require(device&&context&&targetTexture&&frame,"Terrain GPU target arguments are null");
        Require(width>0&&height>0&&width<=4096&&height<=4096&&mapWidth>0&&mapWidth<=width,
                "Invalid terrain render dimensions");
        const D3D11_DEVICE_CONTEXT_TYPE type=context->GetType();
        Require(type==D3D11_DEVICE_CONTEXT_IMMEDIATE,"Terrain rendering requires the caller's immediate context");
        ComPtr<ID3D11Device> contextDevice;context->GetDevice(&contextDevice);
        Require(contextDevice.Get()==device,"Terrain immediate context belongs to a different device");
        ComPtr<ID3D11Device> targetDevice;targetTexture->GetDevice(&targetDevice);
        Require(targetDevice.Get()==device,"Terrain target texture belongs to a different device");
        D3D11_TEXTURE2D_DESC desc{};targetTexture->GetDesc(&desc);
        Require(desc.Width==width&&desc.Height==height&&desc.MipLevels==1&&desc.ArraySize==1&&
                desc.SampleDesc.Count==1&&desc.Format==DXGI_FORMAT_B8G8R8A8_UNORM&&
                desc.Usage==D3D11_USAGE_DEFAULT&&desc.CPUAccessFlags==0&&
                (desc.BindFlags&D3D11_BIND_RENDER_TARGET)&&(desc.BindFlags&D3D11_BIND_SHADER_RESOURCE),
                "Terrain target must be a matching single-sample BGRA8_UNORM default RT|SRV texture");
        auto& retained=GpuTerrainCache();
        if(!retained||retained->package!=view.terrainAssetsPath||retained->device.Get()!=device||retained->context.Get()!=context)
            retained=std::make_unique<Cache>(view.terrainAssetsPath,device,context);
        return RenderWorldTerrainImpl(view,width,height,mapWidth,*retained,targetTexture,frame,error);
    }catch(const std::exception& ex){SetTerrainFailure(error,ex);return false;}
}

}
