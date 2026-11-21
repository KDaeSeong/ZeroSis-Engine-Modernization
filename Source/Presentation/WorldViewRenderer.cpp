#include "WorldViewRenderer.h"
#include "WorldTerrainRenderer.h"

#include <Windows.h>
#include <d2d1.h>
#include <d3d11.h>
#include <dwrite.h>
#include <wincodec.h>
#include <wrl/client.h>

#include <algorithm>
#include <climits>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <limits>
#include <map>
#include <set>
#include <sstream>
#include <unordered_map>
#include <unordered_set>

#pragma comment(lib,"d2d1.lib")
#pragma comment(lib,"dwrite.lib")
#pragma comment(lib,"windowscodecs.lib")
#pragma comment(lib,"ole32.lib")

namespace ZeroSisPresentation {
namespace {
using Microsoft::WRL::ComPtr;
constexpr UINT kCanvasWidth=1280, kCanvasHeight=720;
constexpr UINT kWidth=1920, kHeight=1080;
constexpr float kRenderScale=1.5f;
constexpr float kMapRight=920.0f, kHudLeft=936.0f;
constexpr std::size_t kMaxObjects=500000;
constexpr std::size_t kMaxHits=500000;
constexpr std::uint64_t kKeyPrefix=0x5a57000000000000ull;
// The prefix already occupies bits 48..63. Put the hit domain in unused
// bits 32..47 so plot/unit/city/action IDs cannot alias each other.

bool Fail(std::wstring* error,const wchar_t* text) {
    if(error)*error=text;
    return false;
}
std::wstring HrText(const wchar_t* what,HRESULT hr) {
    wchar_t buffer[96]{};
    swprintf_s(buffer,L"%s failed (0x%08lx)",what,static_cast<unsigned long>(hr));
    return buffer;
}
bool Finite(float value) {return std::isfinite(value)!=0;}

struct ComApartment {
    HRESULT hr=CoInitializeEx(nullptr,COINIT_MULTITHREADED);
    ~ComApartment(){if(SUCCEEDED(hr))CoUninitialize();}
    bool usable() const {return SUCCEEDED(hr)||hr==RPC_E_CHANGED_MODE;}
};

struct Color {float r,g,b,a;};
D2D1_COLOR_F D2D(Color c){return D2D1::ColorF(c.r,c.g,c.b,c.a);}

Color TerrainColor(const WorldViewPlot& plot) {
    const auto& t=plot.terrain;
    if(t.find("OCEAN")!=std::string::npos || t.find("COAST")!=std::string::npos) return {0.08f,0.28f,0.43f,1};
    if(t.find("SNOW")!=std::string::npos || t.find("TUNDRA")!=std::string::npos) return {0.59f,0.64f,0.60f,1};
    if(t.find("DESERT")!=std::string::npos) return {0.70f,0.53f,0.29f,1};
    if(t.find("PLAINS")!=std::string::npos) return {0.46f,0.55f,0.28f,1};
    if(t.find("GRASS")!=std::string::npos) return {0.25f,0.48f,0.25f,1};
    if(t.find("MARSH")!=std::string::npos) return {0.27f,0.39f,0.31f,1};
    if(t.find("FLOOD")!=std::string::npos) return {0.47f,0.49f,0.25f,1};
    return {0.31f,0.36f,0.34f,1};
}
Color Dim(Color color,float factor) {color.r*=factor;color.g*=factor;color.b*=factor;return color;}

void FillRect(ID2D1RenderTarget* target,ID2D1SolidColorBrush* brush,D2D1_RECT_F rect,Color color) {
    brush->SetColor(D2D(color));target->FillRectangle(rect,brush);
}
void StrokeRect(ID2D1RenderTarget* target,ID2D1SolidColorBrush* brush,D2D1_RECT_F rect,Color color,float width=1.0f) {
    brush->SetColor(D2D(color));target->DrawRectangle(rect,brush,width);
}
void Line(ID2D1RenderTarget* target,ID2D1SolidColorBrush* brush,float x0,float y0,float x1,float y1,Color color,float width=1.0f) {
    brush->SetColor(D2D(color));target->DrawLine(D2D1::Point2F(x0,y0),D2D1::Point2F(x1,y1),brush,width);
}
void Ellipse(ID2D1RenderTarget* target,ID2D1SolidColorBrush* brush,float x,float y,float rx,float ry,Color fill,Color edge,float edgeWidth=1) {
    const auto e=D2D1::Ellipse(D2D1::Point2F(x,y),rx,ry);brush->SetColor(D2D(fill));target->FillEllipse(e,brush);
    brush->SetColor(D2D(edge));target->DrawEllipse(e,brush,edgeWidth);
}

bool DrawText(ID2D1RenderTarget* target,IDWriteFactory* write,IDWriteTextFormat* format,
              ID2D1SolidColorBrush* brush,const std::wstring& text,D2D1_RECT_F rect,
              Color color,std::wstring* error) {
    ComPtr<IDWriteTextLayout> layout;
    const float width=std::max(1.0f,rect.right-rect.left),height=std::max(1.0f,rect.bottom-rect.top);
    HRESULT hr=write->CreateTextLayout(text.data(),static_cast<UINT32>(text.size()),format,width,height,&layout);
    if(FAILED(hr)) {if(error)*error=HrText(L"DirectWrite text layout",hr);return false;}
    brush->SetColor(D2D(color));target->DrawTextLayout(D2D1::Point2F(rect.left,rect.top),layout.Get(),brush,D2D1_DRAW_TEXT_OPTIONS_CLIP);
    return true;
}

bool WritePng(IWICImagingFactory* wic,IWICBitmap* bitmap,const std::wstring& path,std::wstring* error) {
    ComPtr<IWICStream> stream;HRESULT hr=wic->CreateStream(&stream);
    if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG stream",hr);return false;}
    hr=stream->InitializeFromFilename(path.c_str(),GENERIC_WRITE);
    if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG output",hr);return false;}
    ComPtr<IWICBitmapEncoder> encoder;hr=wic->CreateEncoder(GUID_ContainerFormatPng,nullptr,&encoder);
    if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG encoder",hr);return false;}
    hr=encoder->Initialize(stream.Get(),WICBitmapEncoderNoCache);
    if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG encoder initialization",hr);return false;}
    ComPtr<IWICBitmapFrameEncode> frame;ComPtr<IPropertyBag2> options;
    hr=encoder->CreateNewFrame(&frame,&options);
    if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG frame",hr);return false;}
    hr=frame->Initialize(options.Get());
    if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG frame initialization",hr);return false;}
    hr=frame->SetSize(kWidth,kHeight);
    if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG frame size",hr);return false;}
    WICPixelFormatGUID format=GUID_WICPixelFormat32bppBGRA;hr=frame->SetPixelFormat(&format);
    if(FAILED(hr)||!IsEqualGUID(format,GUID_WICPixelFormat32bppBGRA)){
        if(error)*error=FAILED(hr)?HrText(L"WIC PNG pixel format",hr):L"WIC PNG encoder rejected 32-bit BGRA";return false;
    }
    ComPtr<IWICFormatConverter> converter;hr=wic->CreateFormatConverter(&converter);
    if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG converter",hr);return false;}
    hr=converter->Initialize(bitmap,GUID_WICPixelFormat32bppBGRA,WICBitmapDitherTypeNone,nullptr,0.0,WICBitmapPaletteTypeCustom);
    if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG conversion",hr);return false;}
    hr=frame->WriteSource(converter.Get(),nullptr);
    if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG pixels",hr);return false;}
    hr=frame->Commit();if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG frame commit",hr);return false;}
    hr=encoder->Commit();if(FAILED(hr)){if(error)*error=HrText(L"WIC PNG commit",hr);return false;}
    return true;
}

struct PlacedPlot {const WorldViewPlot* plot;float cx,cy;};
struct PlacedUnit {const WorldViewUnit* unit;float cx,cy;};

bool Hex(ID2D1Factory* factory,ID2D1RenderTarget* target,ID2D1SolidColorBrush* brush,
         float cx,float cy,float width,float height,Color fill,Color edge,float edgeWidth,std::wstring* error) {
    ComPtr<ID2D1PathGeometry> path;HRESULT hr=factory->CreatePathGeometry(&path);
    if(FAILED(hr)){if(error)*error=HrText(L"D2D hex geometry",hr);return false;}
    ComPtr<ID2D1GeometrySink> sink;hr=path->Open(&sink);
    if(FAILED(hr)){if(error)*error=HrText(L"D2D hex geometry sink",hr);return false;}
    const float points[6][2]={{cx,cy-height/2},{cx+width/2,cy-height/4},{cx+width/2,cy+height/4},
                              {cx,cy+height/2},{cx-width/2,cy+height/4},{cx-width/2,cy-height/4}};
    sink->BeginFigure(D2D1::Point2F(points[0][0],points[0][1]),D2D1_FIGURE_BEGIN_FILLED);
    for(int i=1;i<6;++i)sink->AddLine(D2D1::Point2F(points[i][0],points[i][1]));
    sink->EndFigure(D2D1_FIGURE_END_CLOSED);hr=sink->Close();
    if(FAILED(hr)){if(error)*error=HrText(L"D2D hex geometry close",hr);return false;}
    brush->SetColor(D2D(fill));target->FillGeometry(path.Get(),brush);
    brush->SetColor(D2D(edge));target->DrawGeometry(path.Get(),brush,edgeWidth);
    return true;
}

bool Validate(const WorldView& view,std::wstring* error) {
    if(view.gridWidth<=0||view.gridHeight<=0||view.gridWidth>100000||view.gridHeight>100000)
        return Fail(error,L"World grid dimensions are invalid");
    const std::uint64_t plots=static_cast<std::uint64_t>(view.gridWidth)*static_cast<std::uint64_t>(view.gridHeight);
    if(plots>INT_MAX||view.plots.size()>kMaxObjects||view.units.size()>kMaxObjects||view.cities.size()>kMaxObjects||
       view.plots.size()+view.units.size()>kMaxHits-32)
        return Fail(error,L"World DTO exceeds bounded plot/object limits");
    if(view.turn<0||view.activePlayer<0||view.activePlayer>=64||view.cameraX<0||view.cameraX>=view.gridWidth||
       view.cameraY<0||view.cameraY>=view.gridHeight)
        return Fail(error,L"World turn, active player or camera coordinate is out of range");
    if(!Finite(view.tileWidth)||view.tileWidth<WorldCameraZoom::Minimum||view.tileWidth>WorldCameraZoom::Maximum)
        return Fail(error,L"World tile width must be finite and within [24,112]");
    std::unordered_set<int> plotIds;std::set<std::pair<int,int>> coords,visibleCoords;
    for(const auto& p:view.plots){
        if(p.index<0||static_cast<std::uint64_t>(p.index)>=plots||p.x<0||p.x>=view.gridWidth||p.y<0||p.y>=view.gridHeight||
           p.index!=p.y*view.gridWidth+p.x||!plotIds.insert(p.index).second||!coords.insert({p.x,p.y}).second||
           (p.visible&&!p.revealed))
            return Fail(error,L"Plot identity/coordinate is invalid, duplicated or inconsistent");
        if(p.visible)visibleCoords.emplace(p.x,p.y);
        if(!view.terrainAssetsPath.empty() && (p.revealed?(p.continent<0||p.continent>4):
            (p.continent!=-1||p.water||p.hills||p.mountain||!p.terrain.empty()||!p.feature.empty())))
            return Fail(error,L"Terrain geometry/material facts are invalid or disclosed from an unrevealed plot");
        if(p.terrain.size()>256||p.feature.size()>256)return Fail(error,L"Plot type string exceeds its bound");
        if(p.improvementType < -1 || p.routeType < -1 || p.improvementName.size()>256 || p.routeName.size()>256)
            return Fail(error,L"Plot improvement/route identity or localized name exceeds its bound");
        if(p.improvementType>=0 ? p.improvementName.empty() : (!p.improvementName.empty() || p.improvementPillaged))
            return Fail(error,L"Plot improvement state and localized name are inconsistent");
        if(p.routeType>=0 ? p.routeName.empty() : (!p.routeName.empty() || p.routePillaged))
            return Fail(error,L"Plot route state and localized name are inconsistent");
        if(!p.visible && (p.improvementType>=0 || p.routeType>=0 || p.improvementPillaged || p.routePillaged ||
                          !p.improvementName.empty() || !p.routeName.empty()))
            return Fail(error,L"Infrastructure state from a currently hidden plot must not enter the presentation DTO");
    }
    std::set<std::pair<int,int>> unitIds;
    unsigned selectedCount=0;
    for(const auto& u:view.units){
        if(u.id<0||u.owner<0||u.owner>=64||!unitIds.emplace(u.owner,u.id).second||
           u.x<0||u.x>=view.gridWidth||u.y<0||u.y>=view.gridHeight||
           !coords.count({u.x,u.y})||(u.owner!=view.activePlayer&&!visibleCoords.count({u.x,u.y}))||u.moves<0||u.maxHitPoints<=0||
           u.damage<0||u.damage>u.maxHitPoints||u.name.size()>256||
           (u.owner==view.activePlayer&&u.hostile))
            return Fail(error,L"Unit identity, owner, coordinate or state is invalid");
        if(u.facingDirection < -1 || u.facingDirection>=6 || u.type.size()>256 || u.unitArtInfoTag.size()>256 ||
           u.artStylePrefix.size()>256 || u.artStyleSuffix.size()>256 || u.eraArtPrefix.size()>256)
            return Fail(error,L"Unit visual identity or facing exceeds its bound");
        if(u.selected&&(u.owner!=view.activePlayer||++selectedCount>1))
            return Fail(error,L"Selected unit must be unique and owned by the active player");
    }
    for(const auto& u:view.units)if(u.selected){
        const auto found=std::find_if(view.plots.begin(),view.plots.end(),[&](const WorldViewPlot& p){return p.x==u.x&&p.y==u.y;});
        // The owner's trade units can remain in the roster outside current
        // sight. Only their owner may retain that identity and selection;
        // unitsAt and the terrain renderer still omit hidden map art/picks.
        if(found==view.plots.end())
            return Fail(error,L"Selected unit is outside the captured map");
    }
    std::set<std::pair<int,int>> cityIds;
    for(const auto& c:view.cities){
        if(c.id<0||c.owner<0||c.owner>=64||!cityIds.emplace(c.owner,c.id).second||
           c.x<0||c.x>=view.gridWidth||c.y<0||c.y>=view.gridHeight||c.name.size()>256)
            return Fail(error,L"City identity, owner or coordinate is invalid");
    }
    if(view.selectedCity>=0 && std::none_of(view.cities.begin(),view.cities.end(),[&](const WorldViewCity& city){
        return city.id==view.selectedCity&&city.owner==view.activePlayer;
    }))return Fail(error,L"Selected city must be present in the visible owned-city snapshot");
    if(view.status.size()>2048)return Fail(error,L"World status string exceeds its bound");
    if(view.unitActions.size()>512 || view.unitActionPage<0 ||
       view.unitActionPage>=std::max(1,static_cast<int>((view.unitActions.size()+5)/6)))
        return Fail(error,L"Unit action list or page is outside its bound");
    std::unordered_set<int> actionIds;
    for(const auto& action:view.unitActions){
        if(selectedCount!=1 || action.index<0 || action.index>=512 || !actionIds.insert(action.index).second ||
           action.name.empty() || action.name.size()>256)
            return Fail(error,L"Unit action identity, label or selection is invalid");
    }
    return true;
}

} // namespace

std::uint64_t WorldViewHitKey::Plot(int plotIndex) noexcept {
    return kKeyPrefix|(1ull<<32)|static_cast<std::uint32_t>(plotIndex);
}
std::uint64_t WorldViewHitKey::OwnedUnit(int unitId) noexcept {
    return kKeyPrefix|(2ull<<32)|static_cast<std::uint32_t>(unitId);
}
std::uint64_t WorldViewHitKey::OwnedCity(int cityId) noexcept {
    return kKeyPrefix|(4ull<<32)|static_cast<std::uint32_t>(cityId);
}
std::uint64_t WorldViewHitKey::UnitAction(int actionIndex) noexcept {
    return kKeyPrefix|(5ull<<32)|static_cast<std::uint32_t>(actionIndex);
}
std::uint64_t WorldViewHitKey::Action(WorldViewAction action) noexcept {
    return kKeyPrefix|(3ull<<32)|static_cast<std::uint32_t>(action);
}

static bool RenderWorldViewImpl(const WorldView& view,const std::wstring* pngPath,
    ID3D11Device* device,ID3D11DeviceContext* context,ID3D11Texture2D* texture,
    Scene* scene,std::wstring* error,WorldViewProjection* projection,bool traceFrame) {
    if(projection)*projection={};
    if(error)error->clear();
    if(!scene)return Fail(error,L"World renderer Scene output pointer is null");
    const bool gpuTarget=texture!=nullptr;
    if(!gpuTarget && (!pngPath || pngPath->empty()))return Fail(error,L"World renderer PNG path is empty");
    if(gpuTarget){
        if(!device || !context || context->GetType()!=D3D11_DEVICE_CONTEXT_IMMEDIATE)
            return Fail(error,L"World GPU renderer requires a device and its immediate context");
        ComPtr<ID3D11Device> contextDevice,textureDevice;
        context->GetDevice(&contextDevice);texture->GetDevice(&textureDevice);
        D3D11_TEXTURE2D_DESC desc{};texture->GetDesc(&desc);
        if(contextDevice.Get()!=device || textureDevice.Get()!=device || desc.Width!=kWidth || desc.Height!=kHeight ||
           desc.Format!=DXGI_FORMAT_B8G8R8A8_UNORM || desc.MipLevels!=1 || desc.ArraySize!=1 ||
           desc.SampleDesc.Count!=1 || !(desc.BindFlags&D3D11_BIND_RENDER_TARGET))
            return Fail(error,L"World GPU renderer requires a same-device 1920x1080 BGRA8 render target");
    }
    if(!Validate(view,error))return false;
    scene->width=kWidth;scene->height=kHeight;scene->textures.clear();scene->sprites.clear();scene->hits.clear();scene->scrolls.clear();scene->pixelHits={};scene->lines.clear();
    try {
        ComApartment apartment;if(!apartment.usable())return Fail(error,HrText(L"COM initialization",apartment.hr).c_str());
        ComPtr<ID2D1Factory> d2d;HRESULT hr=D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED,d2d.GetAddressOf());
        if(FAILED(hr)){if(error)*error=HrText(L"Direct2D factory",hr);return false;}
        ComPtr<IWICImagingFactory> wic;hr=CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&wic));
        if(FAILED(hr)){if(error)*error=HrText(L"WIC factory",hr);return false;}
        ComPtr<IDWriteFactory> write;hr=DWriteCreateFactory(DWRITE_FACTORY_TYPE_SHARED,__uuidof(IDWriteFactory),reinterpret_cast<IUnknown**>(write.GetAddressOf()));
        if(FAILED(hr)){if(error)*error=HrText(L"DirectWrite factory",hr);return false;}
        ComPtr<IDWriteTextFormat> textFormat;hr=write->CreateTextFormat(L"Malgun Gothic",nullptr,DWRITE_FONT_WEIGHT_NORMAL,
            DWRITE_FONT_STYLE_NORMAL,DWRITE_FONT_STRETCH_NORMAL,16.0f,L"ko-KR",&textFormat);
        if(FAILED(hr)){if(error)*error=HrText(L"Malgun Gothic text format",hr);return false;}
        textFormat->SetWordWrapping(DWRITE_WORD_WRAPPING_WRAP);
        ComPtr<IDWriteTextFormat> infrastructureFormat;hr=write->CreateTextFormat(L"Malgun Gothic",nullptr,DWRITE_FONT_WEIGHT_BOLD,
            DWRITE_FONT_STYLE_NORMAL,DWRITE_FONT_STRETCH_NORMAL,8.0f,L"ko-KR",&infrastructureFormat);
        if(FAILED(hr)){if(error)*error=HrText(L"Infrastructure label text format",hr);return false;}
        infrastructureFormat->SetWordWrapping(DWRITE_WORD_WRAPPING_WRAP);
        ComPtr<IWICBitmap> bitmap;
        ComPtr<ID2D1RenderTarget> target;const auto props=D2D1::RenderTargetProperties(D2D1_RENDER_TARGET_TYPE_DEFAULT,
            D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_PREMULTIPLIED),96.0f,96.0f);
        if(gpuTarget){
            ComPtr<IDXGISurface> surface;hr=texture->QueryInterface(IID_PPV_ARGS(&surface));
            if(SUCCEEDED(hr))hr=d2d->CreateDxgiSurfaceRenderTarget(surface.Get(),props,&target);
        }else{
            hr=wic->CreateBitmap(kWidth,kHeight,GUID_WICPixelFormat32bppPBGRA,WICBitmapCacheOnLoad,&bitmap);
            if(SUCCEEDED(hr))hr=d2d->CreateWicBitmapRenderTarget(bitmap.Get(),props,&target);
        }
        if(FAILED(hr)){if(error)*error=HrText(L"D2D world target",hr);return false;}
        ComPtr<ID2D1SolidColorBrush> brush;hr=target->CreateSolidColorBrush(D2D1::ColorF(0,0),&brush);
        if(FAILED(hr)){if(error)*error=HrText(L"D2D world brush",hr);return false;}

        // The retained stock HUD owns presentation and input once all three panels are ready.
        const bool diagnosticHud=!(view.fullScreenUi ||
            (view.originalTopPanel && view.originalUnitPanel && view.originalActionInfoPanel));
        const float mapRight=diagnosticHud?kMapRight:static_cast<float>(kCanvasWidth);
        TerrainFrame terrain;const bool terrainActive=!view.terrainAssetsPath.empty();
        ComPtr<ID2D1Bitmap> terrainBitmap;
        if(terrainActive){
            if(gpuTarget){
                if(!RenderWorldTerrainToTexture(view,kWidth,kHeight,static_cast<UINT>(mapRight*kRenderScale),
                    device,context,texture,&terrain,error))return false;
            }else{
                if(!RenderWorldTerrain(view,kWidth,kHeight,static_cast<UINT>(mapRight*kRenderScale),&terrain,error))return false;
                const auto terrainProps=D2D1::BitmapProperties(D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_PREMULTIPLIED));
                hr=target->CreateBitmap(D2D1::SizeU(kWidth,kHeight),terrain.bgra.data(),kWidth*4,terrainProps,&terrainBitmap);
                if(FAILED(hr)){if(error)*error=HrText(L"D2D terrain composition",hr);return false;}
            }
            if(projection){
                projection->ready=true;projection->cameraX=view.cameraX;projection->cameraY=view.cameraY;
                projection->gridWidth=view.gridWidth;projection->gridHeight=view.gridHeight;
                projection->mapWidth=static_cast<int>(mapRight*kRenderScale);
                projection->plots=std::move(terrain.projectedPlots);
            }
            scene->pixelHits=std::move(terrain.picking);
            if(traceFrame)std::printf("WORLD_TERRAIN_FRAME=%u|%u|%u|%llu|%s|%zu\n",kWidth,kHeight,static_cast<UINT>(mapRight*kRenderScale),
                static_cast<unsigned long long>(terrain.triangles),terrain.hardware?"HARDWARE":"WARP",scene->pixelHits.keys.size());
            if(traceFrame&&!view.unitAssetsPath.empty())std::printf("WORLD_UNIT_MODEL_FRAME=%u|%llu|%zu\n",terrain.modelUnits,
                static_cast<unsigned long long>(terrain.unitTriangles),view.units.size());
        }
        target->SetTransform(D2D1::Matrix3x2F::Scale(kRenderScale,kRenderScale));
        target->BeginDraw();
        if(!gpuTarget || !terrainActive)target->Clear(D2D1::ColorF(0.035f,0.047f,0.055f,1));
        if(terrainActive && !gpuTarget)target->DrawBitmap(terrainBitmap.Get(),D2D1::RectF(0,0,kCanvasWidth,kCanvasHeight),1.0f,D2D1_BITMAP_INTERPOLATION_MODE_NEAREST_NEIGHBOR);
        FillRect(target.Get(),brush.Get(),D2D1::RectF(mapRight,0,kCanvasWidth,kCanvasHeight),{0.055f,0.067f,0.078f,1});
        FillRect(target.Get(),brush.Get(),D2D1::RectF(mapRight,0,mapRight+4,kCanvasHeight),{0.26f,0.29f,0.30f,1});

        const float tileW=view.tileWidth,tileH=tileW*1.15470053838f,rowPitch=tileH*0.75f;
        const float centerX=mapRight*0.5f,centerY=kCanvasHeight*0.5f;
        std::unordered_map<std::uint64_t,PlacedPlot> placed;
        std::unordered_map<std::uint64_t,std::vector<PlacedUnit>> unitsAt;
        std::unordered_map<std::uint64_t,const WorldViewCity*> citiesAt;
        placed.reserve(view.plots.size());
        const auto coordKey=[](int x,int y){return (static_cast<std::uint64_t>(static_cast<std::uint32_t>(y))<<32)|static_cast<std::uint32_t>(x);};
        for(const auto& p:view.plots){
            int dx=p.x-view.cameraX,dy=p.y-view.cameraY;
            if(view.wrapX){if(dx>view.gridWidth/2)dx-=view.gridWidth;else if(dx<-view.gridWidth/2)dx+=view.gridWidth;}
            if(view.wrapY){if(dy>view.gridHeight/2)dy-=view.gridHeight;else if(dy<-view.gridHeight/2)dy+=view.gridHeight;}
            float cx=centerX+dx*tileW+(((p.y&1)-(view.cameraY&1))*tileW*0.5f),cy=centerY+dy*rowPitch;
            if(terrainActive){const auto found=terrain.centers.find(p.index);
                if(found==terrain.centers.end()){cx=-1000000;cy=-1000000;}
                else{cx=found->second.x/kRenderScale;cy=found->second.y/kRenderScale;}}
            placed.emplace(coordKey(p.x,p.y),PlacedPlot{&p,cx,cy});
        }
        for(const auto& u:view.units){
            const auto found=placed.find(coordKey(u.x,u.y));
            if(found==placed.end()||!found->second.plot->revealed||!found->second.plot->visible)continue;
            unitsAt[coordKey(u.x,u.y)].push_back(PlacedUnit{&u,found->second.cx,found->second.cy});
        }
        for(const auto& c:view.cities){
            const auto found=placed.find(coordKey(c.x,c.y));
            if(found!=placed.end()&&found->second.plot->revealed&&found->second.plot->visible)citiesAt[coordKey(c.x,c.y)]=&c;
        }

        target->PushAxisAlignedClip(D2D1::RectF(0,0,mapRight,kCanvasHeight),D2D1_ANTIALIAS_MODE_ALIASED);
        for(const auto& p:view.plots){
            const auto& pos=placed.at(coordKey(p.x,p.y));const float cx=pos.cx,cy=pos.cy;
            if(cx+tileW<0||cx-tileW>mapRight||cy+tileH<0||cy-tileH>kCanvasHeight)continue;
            if(!terrainActive){
            if(!p.revealed){if(!Hex(d2d.Get(),target.Get(),brush.Get(),cx,cy,tileW,tileH,{0.018f,0.024f,0.03f,1},{0.045f,0.055f,0.062f,1},0.7f,error)){target->PopAxisAlignedClip();return false;}continue;}
            Color color=TerrainColor(p);if(p.water)color={0.08f,0.28f,0.43f,1};if(!p.visible)color=Dim(color,0.45f);
            if(p.hills){color.r=std::min(1.0f,color.r*1.2f+0.035f);color.g=std::min(1.0f,color.g*1.2f+0.035f);color.b=std::min(1.0f,color.b*1.2f+0.035f);}
            if(p.mountain){color=Dim(color,0.62f);}
            if(!Hex(d2d.Get(),target.Get(),brush.Get(),cx,cy,tileW,tileH,color,p.visible?Color{0.10f,0.14f,0.13f,1}:Color{0.07f,0.09f,0.08f,1},0.7f,error)){target->PopAxisAlignedClip();return false;}
            }
            {
                if(!terrainActive){
                if(p.mountain){Line(target.Get(),brush.Get(),cx,cy+tileH*.20f,cx,cy-tileH*.22f,{0.79f,0.80f,0.73f,1},2);
                    Line(target.Get(),brush.Get(),cx,cy-tileH*.22f,cx+tileW*.17f,cy+tileH*.18f,{0.66f,0.68f,0.62f,1},1.5f);
                    Line(target.Get(),brush.Get(),cx,cy-tileH*.22f,cx-tileW*.17f,cy+tileH*.18f,{0.74f,0.76f,0.69f,1},1.5f);}
                else if(p.hills){Line(target.Get(),brush.Get(),cx-tileW*.19f,cy+tileH*.10f,cx,cy-tileH*.09f,{0.60f,0.63f,0.39f,0.65f},1.2f);
                    Line(target.Get(),brush.Get(),cx,cy-tileH*.09f,cx+tileW*.18f,cy+tileH*.11f,{0.60f,0.63f,0.39f,0.65f},1.2f);}
                }
                if(!p.feature.empty()&&p.visible){
                    if(p.feature.find("FOREST")!=std::string::npos||p.feature.find("JUNGLE")!=std::string::npos){
                        Ellipse(target.Get(),brush.Get(),cx-tileW*.12f,cy,2.2f,3.6f,{0.14f,0.34f,0.18f,1},{0.06f,0.16f,0.09f,1},0.5f);
                        Ellipse(target.Get(),brush.Get(),cx+tileW*.11f,cy+2,2.2f,3.6f,{0.16f,0.38f,0.20f,1},{0.06f,0.16f,0.09f,1},0.5f);
                    }else if(p.feature.find("ICE")!=std::string::npos){
                        Line(target.Get(),brush.Get(),cx-tileW*.10f,cy-tileH*.08f,cx+tileW*.10f,cy+tileH*.08f,{0.82f,0.90f,0.91f,0.9f},1.2f);
                        Line(target.Get(),brush.Get(),cx+tileW*.10f,cy-tileH*.08f,cx-tileW*.10f,cy+tileH*.08f,{0.82f,0.90f,0.91f,0.9f},1.2f);
                    }else Ellipse(target.Get(),brush.Get(),cx,cy,2.0f,2.0f,{0.77f,0.69f,0.38f,1},{0.95f,0.87f,0.59f,1},0.5f);
                }
            }
            if(p.visible && (p.improvementType>=0 || p.routeType>=0)){
                std::wstring infrastructure;
                if(p.improvementType>=0)infrastructure=(p.improvementPillaged?L"!":L"")+p.improvementName;
                if(p.routeType>=0){if(!infrastructure.empty())infrastructure+=L"\n";
                    infrastructure+=(p.routePillaged?L"!":L"")+p.routeName;}
                const float labelWidth=tileW*.94f,labelHeight=tileH*.36f;
                const float labelX=cx-labelWidth*.5f,labelY=cy+tileH*.10f;
                const D2D1_RECT_F labelRect=D2D1::RectF(labelX,labelY,labelX+labelWidth,labelY+labelHeight);
                FillRect(target.Get(),brush.Get(),labelRect,{0.025f,0.035f,0.035f,0.86f});
                StrokeRect(target.Get(),brush.Get(),labelRect,{0.64f,0.61f,0.48f,0.78f},0.55f);
                if(!DrawText(target.Get(),write.Get(),infrastructureFormat.Get(),brush.Get(),infrastructure,
                    D2D1::RectF(labelX+1,labelY+1,labelX+labelWidth-1,labelY+labelHeight-1),
                    (p.improvementPillaged||p.routePillaged)?Color{0.96f,0.65f,0.52f,1}:Color{0.98f,0.94f,0.78f,1},error)){
                    target->PopAxisAlignedClip();return false;
                }
            }
            const auto key=coordKey(p.x,p.y);
            const bool ownUnits=unitsAt.find(key)!=unitsAt.end()&&std::any_of(unitsAt[key].begin(),unitsAt[key].end(),[&](const PlacedUnit& u){return u.unit->owner==view.activePlayer;});
            if(!terrainActive&&p.revealed&&p.visible&&!ownUnits){
                D2D1_RECT_F hit=D2D1::RectF(cx-tileW*.39f,cy-tileH*.22f,cx+tileW*.39f,cy+tileH*.22f);
                hit.left=std::max(0.0f,hit.left);hit.right=std::min(mapRight,hit.right);hit.top=std::max(0.0f,hit.top);hit.bottom=std::min(static_cast<float>(kCanvasHeight),hit.bottom);
                if(hit.right>hit.left&&hit.bottom>hit.top)scene->hits.push_back({WorldViewHitKey::Plot(p.index),{hit.left,hit.top,hit.right,hit.bottom}});
            }
        }
        for(const auto& pair:citiesAt){
            const auto& city=*pair.second;const auto& pos=placed.at(pair.first);const float x=pos.cx,y=pos.cy;
            const Color fill=city.owner==view.activePlayer?Color{0.72f,0.67f,0.42f,1}:Color{0.58f,0.31f,0.26f,1};
            const D2D1_RECT_F cityRect=D2D1::RectF(x-8,y-7,x+8,y+7);
            FillRect(target.Get(),brush.Get(),cityRect,fill);
            const bool selectedOwnedCity=city.owner==view.activePlayer&&city.id==view.selectedCity;
            StrokeRect(target.Get(),brush.Get(),cityRect,selectedOwnedCity?Color{1,0.96f,0.55f,1}:Color{0.95f,0.90f,0.66f,1},selectedOwnedCity?2.4f:1.3f);
            if(city.owner==view.activePlayer){
                D2D1_RECT_F cityHit=D2D1::RectF(x-12,y-11,x+12,y+11);
                cityHit.left=std::max(0.0f,cityHit.left);cityHit.right=std::min(mapRight,cityHit.right);
                cityHit.top=std::max(0.0f,cityHit.top);cityHit.bottom=std::min(static_cast<float>(kCanvasHeight),cityHit.bottom);
                if(cityHit.right>cityHit.left&&cityHit.bottom>cityHit.top)
                    scene->hits.push_back({WorldViewHitKey::OwnedCity(city.id),{cityHit.left,cityHit.top,cityHit.right,cityHit.bottom}});
            }
            if(!city.name.empty()&&!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),city.name,
                D2D1::RectF(x+9,y-9,mapRight,y+10),{0.96f,0.94f,0.82f,1},error)){target->PopAxisAlignedClip();return false;}
        }
        for(auto& pair:unitsAt){
            auto& stack=pair.second;const float cx=stack.front().cx,cy=stack.front().cy;
            const int cols=4;for(std::size_t n=0;n<stack.size();++n){
                const auto& u=*stack[n].unit;
                if(stack.size()>64){if(error)*error=L"More than 64 visible units occupy one plot";target->PopAxisAlignedClip();return false;}
                const int col=static_cast<int>(n%cols),row=static_cast<int>(n/cols);
                const float bx=cx+(col-1.5f)*tileW*.145f,by=cy+(row-(static_cast<int>((stack.size()+cols-1)/cols)-1)*.5f)*tileH*.16f;
                const bool owned=u.owner==view.activePlayer;
                const Color fill=u.selected?Color{0.94f,0.72f,0.20f,1}:owned?Color{0.16f,0.56f,0.76f,1}:
                    u.hostile?Color{0.66f,0.23f,0.20f,1}:Color{0.62f,0.48f,0.23f,1};
                const Color edge=u.selected?Color{1,0.96f,0.72f,1}:owned?Color{0.82f,0.91f,0.94f,1}:
                    u.hostile?Color{1,0.57f,0.48f,1}:Color{0.96f,0.83f,0.48f,1};
                Ellipse(target.Get(),brush.Get(),bx,by,4.2f,5.3f,fill,edge,u.selected?2.0f:1.0f);
                const float healthWidth=10.0f,healthHeight=1.8f;
                const float healthRatio=static_cast<float>(u.maxHitPoints-u.damage)/static_cast<float>(u.maxHitPoints);
                const auto healthRect=D2D1::RectF(bx-healthWidth*.5f,by+5.7f,bx+healthWidth*.5f,by+5.7f+healthHeight);
                FillRect(target.Get(),brush.Get(),healthRect,{0.22f,0.055f,0.05f,1});
                if(healthRatio>0.0f)FillRect(target.Get(),brush.Get(),
                    D2D1::RectF(healthRect.left,healthRect.top,healthRect.left+healthWidth*healthRatio,healthRect.bottom),
                    {0.30f,0.77f,0.34f,1});
                StrokeRect(target.Get(),brush.Get(),healthRect,{0.035f,0.045f,0.04f,1},0.45f);
                if(owned){
                    D2D1_RECT_F hit=D2D1::RectF(bx-3.2f,by-3.8f,bx+3.2f,by+3.8f);
                    // The raster is clipped above; its click rectangles must
                    // use the same map viewport when the camera moves away.
                    hit.left=std::max(0.0f,hit.left);hit.right=std::min(mapRight,hit.right);
                    hit.top=std::max(0.0f,hit.top);hit.bottom=std::min(static_cast<float>(kCanvasHeight),hit.bottom);
                    if(hit.right>hit.left && hit.bottom>hit.top)
                        scene->hits.push_back({WorldViewHitKey::OwnedUnit(u.id),{hit.left,hit.top,hit.right,hit.bottom}});
                }
            }
        }
        target->PopAxisAlignedClip();

        if(diagnosticHud){
        const Color cream{0.90f,0.88f,0.78f,1},muted{0.62f,0.66f,0.66f,1},gold{0.81f,0.70f,0.39f,1};
        if(!view.originalTopPanel){
            if(!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),L"전략 지도",D2D1::RectF(kHudLeft,22,1260,54),cream,error))return false;
            std::wstring turn=L"턴 "+std::to_wstring(view.turn)+L"   플레이어 "+std::to_wstring(view.activePlayer);
            if(!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),turn,D2D1::RectF(kHudLeft,64,1260,92),gold,error))return false;
        }
        Line(target.Get(),brush.Get(),kHudLeft,104,1260,104,{0.27f,0.31f,0.30f,1},1);
        // The retained stock panel owns selected-unit information and actions.
        // Keep the diagnostic fallback only while that panel is absent.
        if(!view.originalUnitPanel){
        std::wstring selected=L"선택된 유닛: 없음";
        for(const auto& u:view.units)if(u.selected&&u.owner==view.activePlayer){selected=L"선택된 유닛: "+(u.name.empty()?L"유닛 "+std::to_wstring(u.id):u.name);break;}
        if(!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),selected,D2D1::RectF(kHudLeft,122,1260,156),cream,error))return false;
        std::wstring unitDetails=L"이동력 / 체력: -";
        for(const auto& u:view.units)if(u.selected&&u.owner==view.activePlayer){unitDetails=L"이동력 "+std::to_wstring(u.moves)+
            L"   체력 "+std::to_wstring(u.maxHitPoints-u.damage)+L"/"+std::to_wstring(u.maxHitPoints);break;}
        if(!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),unitDetails,D2D1::RectF(kHudLeft,158,1260,184),muted,error))return false;
        }
        std::wstring cityDetails=L"선택된 도시: 없음";
        for(const auto& city:view.cities)if(city.id==view.selectedCity&&city.owner==view.activePlayer){
            cityDetails=L"선택된 도시: "+(city.name.empty()?L"도시 "+std::to_wstring(city.id):city.name);break;
        }
        if(!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),cityDetails,D2D1::RectF(kHudLeft,184,1260,204),muted,error))return false;
        std::wstring status=view.status.empty()?L"대기 중":view.status;
        if(!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),status,D2D1::RectF(kHudLeft,202,1260,276),cream,error))return false;
        Line(target.Get(),brush.Get(),kHudLeft,292,1260,292,{0.27f,0.31f,0.30f,1},1);

        struct ActionSpec {WorldViewAction action;const wchar_t* label;float x,y,w,h;};
        const ActionSpec actions[]={
            {WorldViewAction::NextUnit,L"다음 유닛",kHudLeft,314,150,40},
            {WorldViewAction::Skip,L"건너뛰기",1098,314,150,40},
            {WorldViewAction::Found,L"도시 건설",kHudLeft,364,150,40},
            {WorldViewAction::EndTurn,L"턴 종료",1098,364,150,40},
            {WorldViewAction::Save,L"저장",kHudLeft,414,150,40},
            {WorldViewAction::Close,L"닫기",1098,414,150,40},
            {WorldViewAction::Research,L"연구 선택",kHudLeft,464,150,40},
            {WorldViewAction::Production,L"생산 선택",1098,464,150,40},
            {WorldViewAction::PanLeft,L"◀",1098,514,44,38},
            {WorldViewAction::PanUp,L"▲",1146,514,44,38},
            {WorldViewAction::PanDown,L"▼",1194,514,44,38},
            {WorldViewAction::PanRight,L"▶",1242,514,38,38}
        };
        for(const auto& a:actions){
            if(view.originalActionInfoPanel && a.action==WorldViewAction::EndTurn)continue;
            if(view.originalUnitPanel && (a.action==WorldViewAction::Found || a.action==WorldViewAction::Skip))continue;
            D2D1_RECT_F rect=D2D1::RectF(a.x,a.y,a.x+a.w,a.y+a.h);
            FillRect(target.Get(),brush.Get(),rect,{0.12f,0.15f,0.16f,1});StrokeRect(target.Get(),brush.Get(),rect,{0.35f,0.40f,0.38f,1},1);
            if(!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),a.label,D2D1::RectF(a.x+7,a.y+8,a.x+a.w-7,a.y+a.h-3),cream,error))return false;
            scene->hits.push_back({WorldViewHitKey::Action(a.action),{a.x,a.y,a.x+a.w,a.y+a.h}});
        }
        if(!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),L"지도 이동",D2D1::RectF(kHudLeft,513,1080,545),muted,error))return false;
        if(!view.originalUnitPanel){
        const int actionPages=std::max(1,static_cast<int>((view.unitActions.size()+5)/6));
        const std::wstring actionTitle=L"유닛 행동  "+std::to_wstring(view.unitActionPage+1)+L"/"+std::to_wstring(actionPages);
        if(!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),actionTitle,D2D1::RectF(kHudLeft,563,1140,587),gold,error))return false;
        const auto actionButton=[&](std::uint64_t key,const std::wstring& label,float x,float y,float width){
            const auto rect=D2D1::RectF(x,y,x+width,y+34);
            FillRect(target.Get(),brush.Get(),rect,{0.12f,0.15f,0.16f,1});
            StrokeRect(target.Get(),brush.Get(),rect,{0.35f,0.40f,0.38f,1},1);
            if(!DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),label,D2D1::RectF(x+5,y+5,x+width-5,y+31),cream,error))return false;
            scene->hits.push_back({key,{rect.left,rect.top,rect.right,rect.bottom}});return true;
        };
        if(view.unitActionPage>0 && !actionButton(WorldViewHitKey::Action(WorldViewAction::UnitActionsPrevious),L"◀",1154,558,42))return false;
        if(view.unitActionPage+1<actionPages && !actionButton(WorldViewHitKey::Action(WorldViewAction::UnitActionsNext),L"▶",1206,558,42))return false;
        const std::size_t first=static_cast<std::size_t>(view.unitActionPage)*6;
        for(std::size_t i=first;i<std::min(first+6,view.unitActions.size());++i){
            const auto& action=view.unitActions[i];const auto slot=i-first;
            if(!actionButton(WorldViewHitKey::UnitAction(action.index),action.name,
                slot%2==0?kHudLeft:1098.0f,598.0f+static_cast<float>(slot/2)*38.0f,150.0f))return false;
        }
        if(view.unitActions.empty() && !DrawText(target.Get(),write.Get(),textFormat.Get(),brush.Get(),
            L"유닛을 선택하면 가능한 행동을 표시합니다.",D2D1::RectF(kHudLeft,600,1256,676),muted,error))return false;
        }
        }
        hr=target->EndDraw();if(FAILED(hr)){if(error)*error=HrText(L"Direct2D world drawing",hr);return false;}
        for(auto& hit:scene->hits)for(float& value:hit.bounds)value*=kRenderScale;
        if(scene->hits.size()>kMaxHits)return Fail(error,L"World hit map exceeds the native scene limit");
        if(!gpuTarget && !WritePng(wic.Get(),bitmap.Get(),*pngPath,error))return false;
        return true;
    }catch(const std::exception& ex){
        if(error){const char* text=ex.what();error->assign(L"World renderer exception: ");while(*text)error->push_back(static_cast<unsigned char>(*text++));}
        return false;
    }catch(...){return Fail(error,L"Unknown world renderer failure");}
}

bool RenderWorldView(const WorldView& view,const std::wstring& pngPath,Scene* scene,
                     std::wstring* error,WorldViewProjection* projection) {
    return RenderWorldViewImpl(view,&pngPath,nullptr,nullptr,nullptr,scene,error,projection,true);
}

bool RenderWorldViewToTexture(const WorldView& view,ID3D11Device* device,
                              ID3D11DeviceContext* context,ID3D11Texture2D* texture,
                              Scene* scene,std::wstring* error,WorldViewProjection* projection,bool traceFrame) {
    if(!texture)return Fail(error,L"World GPU target is null");
    return RenderWorldViewImpl(view,nullptr,device,context,texture,scene,error,projection,traceFrame);
}

}  // namespace ZeroSisPresentation
