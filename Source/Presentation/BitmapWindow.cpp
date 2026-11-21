#include "BitmapWindow.h"
#include "SceneLineContract.h"
#include "BitmapKeyPolicy.h"

#include <d2d1.h>
#include <d3d11.h>
#include <dxgi1_2.h>
#include <wincodec.h>
#include <windowsx.h>
#include <imm.h>
#include <wrl/client.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <mutex>
#include <new>
#include <limits>
#include <unordered_set>

#pragma comment(lib,"d2d1.lib")
#pragma comment(lib,"d3d11.lib")
#pragma comment(lib,"dxgi.lib")
#pragma comment(lib,"windowscodecs.lib")
#pragma comment(lib,"ole32.lib")
#pragma comment(lib,"user32.lib")
#pragma comment(lib,"gdi32.lib")
#pragma comment(lib,"imm32.lib")

namespace ZeroSisPresentation {
namespace {
using Microsoft::WRL::ComPtr;
constexpr wchar_t kWindowClass[] = L"ZeroSis.BitmapWindow.v1";
constexpr std::uint32_t kLogicalWidth = 1920;
constexpr std::uint32_t kLogicalHeight = 1080;
constexpr std::size_t kMaxQueuedInputs = 4096;
constexpr std::size_t kMaxRetainingUpdateMessages = 256;
constexpr std::uint64_t kMaxFrameBytes = 256ull * 1024ull * 1024ull;
constexpr float kPrototypeScrollPixelsPerNotch = 48.0f;
std::mutex g_classMutex;
ATOM g_windowClass = 0;

std::wstring HrMessage(const wchar_t* action,HRESULT hr) {
    wchar_t code[24]={}; swprintf_s(code,L"0x%08lx",static_cast<unsigned long>(hr));
    return std::wstring(action)+L" failed (HRESULT "+code+L")";
}

bool ValidFrameDimensions(std::uint32_t width,std::uint32_t height) {
    return width!=0 && height!=0 && width<=32768 && height<=32768 &&
           static_cast<std::uint64_t>(width)*height*4ull<=kMaxFrameBytes;
}

bool ValidSceneContract(const Scene& scene,std::wstring* error) {
    if (!ValidateSceneLines(scene,error)) return false;
    if (scene.width!=kLogicalWidth || scene.height!=kLogicalHeight) {
        if(error)*error=L"Scene must use the retained 1920x1080 logical dimensions";
        return false;
    }
    for (const HitRecord& hit:scene.hits) {
        for (float value:hit.bounds) if (!std::isfinite(value)) {
            if(error)*error=L"Hit record contains a non-finite coordinate";
            return false;
        }
        if (!(hit.bounds[2]>hit.bounds[0] && hit.bounds[3]>hit.bounds[1]) ||
            hit.bounds[0]<0 || hit.bounds[1]<0 || hit.bounds[2]>kLogicalWidth || hit.bounds[3]>kLogicalHeight) {
            if(error)*error=L"Hit record is outside the logical scene or has empty bounds";
            return false;
        }
    }
    for (const HitRecord& hit:scene.scrolls) {
        for (float value:hit.bounds) if (!std::isfinite(value)) {
            if(error)*error=L"Scroll record contains a non-finite coordinate";
            return false;
        }
        if (!(hit.bounds[2]>hit.bounds[0] && hit.bounds[3]>hit.bounds[1]) ||
            hit.bounds[0]<0 || hit.bounds[1]<0 || hit.bounds[2]>kLogicalWidth || hit.bounds[3]>kLogicalHeight) {
            if(error)*error=L"Scroll record is outside the logical scene or has empty bounds";
            return false;
        }
    }
    const PixelHitMap& pixelHits=scene.pixelHits;
    constexpr std::size_t kMaxPixelHitKeys=500000;
    if (pixelHits.indices.size()!=0 && pixelHits.indices.size()!=
        static_cast<std::uint64_t>(scene.width)*static_cast<std::uint64_t>(scene.height)) {
        if(error)*error=L"Pixel hit index count must be empty or match the logical scene dimensions";
        return false;
    }
    if (pixelHits.keys.size()>kMaxPixelHitKeys) {
        if(error)*error=L"Pixel hit key table exceeds 500000 entries";
        return false;
    }
    try {
        std::unordered_set<std::uint64_t> uniquePixelKeys;
        uniquePixelKeys.reserve(pixelHits.keys.size());
        for (const std::uint64_t key:pixelHits.keys) {
            if (key==0 || !uniquePixelKeys.insert(key).second) {
                if(error)*error=L"Pixel hit keys must be nonzero and unique";
                return false;
            }
        }
    } catch (const std::bad_alloc&) { if(error)*error=L"Could not validate the pixel hit key table"; return false; }
    for (const std::uint32_t index:pixelHits.indices) {
        if (index>pixelHits.keys.size()) {
            if(error)*error=L"Pixel hit index references a missing key";
            return false;
        }
    }
    return true;
}

} // namespace

struct BitmapWindow::Impl {
    ComPtr<IWICImagingFactory> wic;
    ComPtr<IWICBitmap> source;
    ComPtr<ID3D11Texture2D> sceneTexture;
    ComPtr<ID3D11Texture2D> preparedTexture;
    ComPtr<ID2D1Factory> d2d;
    ComPtr<ID3D11Device> device;
    ComPtr<ID3D11DeviceContext> context;
    ComPtr<IDXGISwapChain1> swapChain;
    ComPtr<IDXGISurface> surface;
    ComPtr<ID3D11Texture2D> staging;
    ComPtr<ID2D1RenderTarget> target;
    ComPtr<ID2D1Bitmap> bitmap;
    BitmapDeviceKind deviceKind=BitmapDeviceKind::Unknown;
    std::uint64_t renderCount=0;
    std::uint64_t presentCount=0;
    HRESULT lastPresentResult=S_OK;
    bool lastPresentOccluded=false;
    bool verticalSync=true;
    std::wstring renderFailure;
    bool DecodeSceneBitmap(const std::wstring& path,std::uint32_t expectedWidth,
                           std::uint32_t expectedHeight,ComPtr<IWICBitmap>* decoded,
                           std::wstring* error);
    bool CreateSceneTexture(std::uint32_t width,std::uint32_t height,
                            ComPtr<ID3D11Texture2D>* texture,std::wstring* error);
    bool DrawGpuScene(const Scene& scene,ComPtr<ID3D11Texture2D>* texture,std::wstring* error);
    bool ShareSceneTexture(ID3D11Texture2D* texture,ComPtr<ID2D1Bitmap>* shared,std::wstring* error);
};

BitmapWindow::BitmapWindow()
    : hwnd_(nullptr),ownerThreadId_(0),logicalWidth_(kLogicalWidth),logicalHeight_(kLogicalHeight),
      dpi_(96),closing_(false),closeQueued_(false),inWindowProc_(false),queueOverflow_(false),
      productionPointerInputEnabled_(false),gameplayInputEnabled_(false),textInputEnabled_(false),nativeTextFocused_(false),
      imeCompositionActive_(false),pendingHighSurrogate_(0),editorOwner_(0),textFocusEpoch_(1),
      textInputCutoffTick_(0),textInputCutoffActive_(false),automaticLeaveTracking_(true),trackingMouseLeave_(false),comInitialized_(false),
      creationAttempted_(false),sceneGeneration_(0),inputCutoffTick_(0),
      inputCutoffActive_(false),impl_(new(std::nothrow) Impl()) {}

BitmapWindow::~BitmapWindow() {
    if (ownerThreadId_ && GetCurrentThreadId()!=ownerThreadId_) {
        // The object owns apartment-bound COM interfaces and an HWND userdata pointer.
        // Continuing would strand both resources and leave callbacks targeting dead storage.
        RaiseFailFastException(nullptr,nullptr,0);
        __assume(0);
    }
#if defined(ZEROSIS_BITMAP_WINDOW_DIAGNOSTICS)
    std::fprintf(stderr,"WINDOW_DTOR|enter|hwnd=%p|owner_tid=%lu\n",hwnd_,static_cast<unsigned long>(ownerThreadId_)); std::fflush(stderr);
#endif
    if(impl_ && impl_->swapChain)impl_->swapChain->SetFullscreenState(FALSE,nullptr);
    if (hwnd_ && GetCurrentThreadId()==ownerThreadId_) DestroyWindow(hwnd_);
#if defined(ZEROSIS_BITMAP_WINDOW_DIAGNOSTICS)
    std::fprintf(stderr,"WINDOW_DTOR|before_render_target_release\n"); std::fflush(stderr);
#endif
    ReleaseRenderTarget();
#if defined(ZEROSIS_BITMAP_WINDOW_DIAGNOSTICS)
    std::fprintf(stderr,"WINDOW_DTOR|before_impl_release\n"); std::fflush(stderr);
#endif
    delete impl_;
    impl_=nullptr;
#if defined(ZEROSIS_BITMAP_WINDOW_DIAGNOSTICS)
    std::fprintf(stderr,"WINDOW_DTOR|after_impl_release|com_initialized=%d\n",comInitialized_?1:0); std::fflush(stderr);
#endif
    // WIC and the Direct2D factory are COM objects. Release every owned
    // interface while this apartment is still initialized.
    if (comInitialized_ && GetCurrentThreadId()==ownerThreadId_) CoUninitialize();
#if defined(ZEROSIS_BITMAP_WINDOW_DIAGNOSTICS)
    if (comInitialized_) { std::fprintf(stderr,"WINDOW_COM|uninitialize|this=%p\n",this); std::fflush(stderr); }
    std::fprintf(stderr,"WINDOW_DTOR|complete\n"); std::fflush(stderr);
#endif
}

bool BitmapWindow::Impl::DecodeSceneBitmap(const std::wstring& path,std::uint32_t expectedWidth,
                                           std::uint32_t expectedHeight,ComPtr<IWICBitmap>* decoded,
                                           std::wstring* error) {
    if (!decoded) { if(error)*error=L"Decoded scene bitmap output is null"; return false; }
    HRESULT hr=S_OK;
    if (!wic) hr=CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,
                                  IID_PPV_ARGS(&wic));
    if (FAILED(hr)) { if(error)*error=HrMessage(L"Create WIC factory",hr); return false; }
    ComPtr<IWICBitmapDecoder> decoder;
    hr=wic->CreateDecoderFromFilename(path.c_str(),nullptr,GENERIC_READ,
                                      WICDecodeMetadataCacheOnLoad,&decoder);
    if (FAILED(hr)) { if(error)*error=HrMessage(L"Decode retained scene PNG",hr); return false; }
    ComPtr<IWICBitmapFrameDecode> frame;
    hr=decoder->GetFrame(0,&frame);
    if (FAILED(hr)) { if(error)*error=HrMessage(L"Read scene PNG frame",hr); return false; }
    UINT width=0,height=0; hr=frame->GetSize(&width,&height);
    if (FAILED(hr) || width!=expectedWidth || height!=expectedHeight) {
        if(error)*error=FAILED(hr)?HrMessage(L"Read scene PNG dimensions",hr):L"Scene PNG must be exactly 1920x1080";
        return false;
    }
    ComPtr<IWICFormatConverter> converter;
    hr=wic->CreateFormatConverter(&converter);
    if (FAILED(hr)) { if(error)*error=HrMessage(L"Create scene PNG converter",hr); return false; }
    hr=converter->Initialize(frame.Get(),GUID_WICPixelFormat32bppPBGRA,WICBitmapDitherTypeNone,
                             nullptr,0.0,WICBitmapPaletteTypeCustom);
    if (FAILED(hr)) { if(error)*error=HrMessage(L"Convert scene PNG to premultiplied BGRA",hr); return false; }
    hr=wic->CreateBitmapFromSource(converter.Get(),WICBitmapCacheOnLoad,decoded->GetAddressOf());
    if (FAILED(hr)) { if(error)*error=HrMessage(L"Retain scene PNG pixels",hr); return false; }
    return true;
}

bool BitmapWindow::LoadBitmap(const std::wstring& path,std::wstring* error) {
    return impl_->DecodeSceneBitmap(path,logicalWidth_,logicalHeight_,&impl_->source,error);
}

bool BitmapWindow::Impl::CreateSceneTexture(std::uint32_t width,std::uint32_t height,
                                           ComPtr<ID3D11Texture2D>* texture,std::wstring* error) {
    D3D11_TEXTURE2D_DESC desc{};
    desc.Width=width;desc.Height=height;desc.MipLevels=1;desc.ArraySize=1;
    desc.Format=DXGI_FORMAT_B8G8R8A8_UNORM;desc.SampleDesc.Count=1;
    desc.Usage=D3D11_USAGE_DEFAULT;desc.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;
    const HRESULT hr=device->CreateTexture2D(&desc,nullptr,texture->GetAddressOf());
    if (FAILED(hr)) { if(error)*error=HrMessage(L"Create candidate GPU scene texture",hr); return false; }
    return true;
}

bool BitmapWindow::Impl::DrawGpuScene(const Scene& scene,ComPtr<ID3D11Texture2D>* texture,
                                      std::wstring* error) {
    if (!CreateSceneTexture(scene.width,scene.height,texture,error)) return false;
    // This new texture is not bound to any D3D stage or the visible swap chain.
    return RenderSceneToD3D11Texture(scene,device.Get(),context.Get(),texture->Get(),error);
}

bool BitmapWindow::Impl::ShareSceneTexture(ID3D11Texture2D* texture,
                                          ComPtr<ID2D1Bitmap>* shared,std::wstring* error) {
    ComPtr<IDXGISurface> sceneSurface;
    HRESULT hr=texture->QueryInterface(IID_PPV_ARGS(&sceneSurface));
    if (SUCCEEDED(hr)) {
        const D2D1_BITMAP_PROPERTIES props=D2D1::BitmapProperties(
            D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_PREMULTIPLIED),96.0f,96.0f);
        hr=target->CreateSharedBitmap(__uuidof(IDXGISurface),sceneSurface.Get(),&props,shared->GetAddressOf());
    }
    if (FAILED(hr)) { if(error)*error=HrMessage(L"Share GPU scene texture with window target",hr); return false; }
    return true;
}

bool BitmapWindow::Create(const Scene& scene,const std::wstring& renderedPng,
                          const std::wstring& title,std::uint32_t clientWidth,
                          std::uint32_t clientHeight,bool show,std::wstring* error) {
    return CreateImpl(scene,&renderedPng,title,clientWidth,clientHeight,show,false,error);
}

bool BitmapWindow::CreateGpuScene(const Scene& scene,const std::wstring& title,
                                  std::uint32_t clientWidth,std::uint32_t clientHeight,
                                  bool show,std::wstring* error) {
    return CreateImpl(scene,nullptr,title,clientWidth,clientHeight,show,false,error);
}

bool BitmapWindow::InitializeOwner(std::wstring* error) {
    if (ownerThreadId_) return OnOwnerThread(error);
    ownerThreadId_=GetCurrentThreadId();
    const HRESULT com=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    if (SUCCEEDED(com)) comInitialized_=true;
    else if (com!=RPC_E_CHANGED_MODE) {
        ownerThreadId_=0;if(error)*error=HrMessage(L"Initialize COM",com);return false;
    }
#if defined(ZEROSIS_BITMAP_WINDOW_DIAGNOSTICS)
    if (comInitialized_) { std::fprintf(stderr,"WINDOW_COM|initialize|this=%p\n",this);std::fflush(stderr); }
#endif
    return true;
}

bool BitmapWindow::PrepareGpuFrame(const GpuFramePainter& painter,std::wstring* error) {
    if (!impl_ || (creationAttempted_ && (!hwnd_ || closing_))) {
        if(error)*error=L"Cannot prepare a GPU frame for a closed or failed window";return false;
    }
    if (!InitializeOwner(error)) return false;
    impl_->preparedTexture.Reset();
    if (!painter) { if(error)*error=L"GPU frame painter is empty";return false; }
    if (!impl_->renderFailure.empty()) { if(error)*error=impl_->renderFailure;return false; }
    if (!EnsureGpuDevice(error)) return false;
    ComPtr<ID3D11Texture2D> candidate;
    if (!impl_->CreateSceneTexture(logicalWidth_,logicalHeight_,&candidate,error)) return false;
    bool painted=false;
    try { painted=painter(impl_->device.Get(),impl_->context.Get(),candidate.Get(),error); }
    catch (...) { if(error)*error=L"GPU frame painter threw an exception"; }
    impl_->context->OMSetRenderTargets(0,nullptr,nullptr);
    if (!painted) return false;
    impl_->preparedTexture=std::move(candidate);
    return true;
}

bool BitmapWindow::OverlayPreparedGpuFrame(const Scene& scene,std::wstring* error) {
    if (!OnOwnerThread(error)) return false;
    if (!impl_ || !impl_->preparedTexture) { if(error)*error=L"No GPU frame is prepared";return false; }
    bool drawn=false;
    try { drawn=OverlaySceneOnD3D11Texture(scene,impl_->device.Get(),impl_->context.Get(),
                                          impl_->preparedTexture.Get(),error); }
    catch (...) { if(error)*error=L"GPU scene overlay threw an exception"; }
    if (!drawn) impl_->preparedTexture.Reset();
    return drawn;
}

bool BitmapWindow::CapturePreparedGpuFrame(const std::wstring& png,std::wstring* error) {
    if (!OnOwnerThread(error)) return false;
    if (!impl_ || !impl_->preparedTexture) { if(error)*error=L"No GPU frame is prepared";return false; }
    return CaptureD3D11TextureToPng(impl_->device.Get(),impl_->context.Get(),impl_->preparedTexture.Get(),png,error);
}

bool BitmapWindow::CreatePreparedGpuScene(const Scene& scene,const std::wstring& title,
                                          std::uint32_t clientWidth,std::uint32_t clientHeight,
                                          bool show,std::wstring* error) {
    return CreateImpl(scene,nullptr,title,clientWidth,clientHeight,show,true,error);
}

bool BitmapWindow::CreateImpl(const Scene& scene,const std::wstring* renderedPng,
                              const std::wstring& title,std::uint32_t clientWidth,
                              std::uint32_t clientHeight,bool show,bool preparedGpu,std::wstring* error) {
    if (creationAttempted_ || hwnd_ || !impl_) { if(error)*error=L"Window creation is one-shot or renderer allocation failed"; return false; }
    if (ownerThreadId_ && !OnOwnerThread(error)) return false;
    if (preparedGpu && !impl_->preparedTexture) { if(error)*error=L"No GPU frame is prepared";return false; }
    if (!ValidSceneContract(scene,error)) return false;
    if (!ValidFrameDimensions(clientWidth,clientHeight)) {
        if(error)*error=L"Window requires a 1920x1080 scene and client dimensions within 32768 and 256 MiB limits";
        return false;
    }
    creationAttempted_=true;
    if (!InitializeOwner(error)) return false;
    std::vector<HitRecord> nextHits,nextScrolls;
    PixelHitMap nextPixelHits;
    try { nextHits=scene.hits; nextScrolls=scene.scrolls; nextPixelHits=scene.pixelHits; }
    catch (const std::bad_alloc&) { if(error)*error=L"Could not retain initial scene input records"; return false; }
    if (renderedPng && !LoadBitmap(*renderedPng,error)) return false;
    hits_.swap(nextHits);
    scrolls_.swap(nextScrolls);
    pixelHits_.indices.swap(nextPixelHits.indices);
    pixelHits_.keys.swap(nextPixelHits.keys);
    sceneGeneration_=1;
    worldWheelGeneration_=0;
    {
        std::lock_guard<std::mutex> guard(g_classMutex);
        if (!g_windowClass) {
            WNDCLASSEXW wc{}; wc.cbSize=sizeof(wc); wc.hInstance=GetModuleHandleW(nullptr);
            wc.lpfnWndProc=&BitmapWindow::WindowProc; wc.lpszClassName=kWindowClass;
            wc.hCursor=LoadCursorW(nullptr,MAKEINTRESOURCEW(32512)); wc.style=CS_HREDRAW|CS_VREDRAW;
            g_windowClass=RegisterClassExW(&wc);
            if (!g_windowClass && GetLastError()!=ERROR_CLASS_ALREADY_EXISTS) {
                if(error)*error=L"RegisterClassExW failed"; return false;
            }
            if (!g_windowClass) g_windowClass=1;
        }
    }
    const DWORD style=WS_OVERLAPPEDWINDOW;
    RECT outer{0,0,static_cast<LONG>(clientWidth),static_cast<LONG>(clientHeight)};
    dpi_=96;
    if (!AdjustWindowRectEx(&outer,style,FALSE,0)) { if(error)*error=L"AdjustWindowRectEx failed"; return false; }
    hwnd_=CreateWindowExW(0,kWindowClass,title.c_str(),style,CW_USEDEFAULT,CW_USEDEFAULT,
                          outer.right-outer.left,outer.bottom-outer.top,nullptr,nullptr,
                          GetModuleHandleW(nullptr),this);
    if (!hwnd_) { if(error)*error=L"CreateWindowExW failed"; return false; }
    dpi_=GetDpiForWindow(hwnd_);
    if (!EnsureRenderTarget(error)) { DestroyWindow(hwnd_); hwnd_=nullptr; return false; }
    if (!renderedPng) {
        if (preparedGpu) impl_->sceneTexture=impl_->preparedTexture;
        else if (!impl_->DrawGpuScene(scene,&impl_->sceneTexture,error)) {
            DestroyWindow(hwnd_);hwnd_=nullptr;return false;
        }
        if (!impl_->ShareSceneTexture(impl_->sceneTexture.Get(),&impl_->bitmap,error)) {
            DestroyWindow(hwnd_);hwnd_=nullptr;return false;
        }
    }
    impl_->preparedTexture.Reset();
    if (show) ShowWindow(hwnd_,SW_SHOWNOACTIVATE);
    InvalidateRect(hwnd_,nullptr,FALSE);
    return true;
}

bool BitmapWindow::UpdateScene(const Scene& scene,const std::wstring& renderedPng,std::wstring* error) {
    return UpdateSceneImpl(scene,&renderedPng,false,false,error);
}

bool BitmapWindow::UpdateSceneRetainingInput(const Scene& scene,const std::wstring& renderedPng,
                                             std::wstring* error) {
    return UpdateSceneImpl(scene,&renderedPng,true,false,error);
}

bool BitmapWindow::UpdateGpuScene(const Scene& scene,std::wstring* error) {
    return UpdateSceneImpl(scene,nullptr,false,false,error);
}

bool BitmapWindow::UpdateGpuSceneRetainingInput(const Scene& scene,std::wstring* error) {
    return UpdateSceneImpl(scene,nullptr,true,false,error);
}

bool BitmapWindow::UpdatePreparedGpuSceneRetainingInput(const Scene& scene,std::wstring* error,
                                                       std::uint64_t editorOwner,std::uint64_t textFocusEpoch) {
    return UpdateSceneImpl(scene,nullptr,true,true,error,editorOwner,textFocusEpoch);
}

bool BitmapWindow::RefreshPreparedGpuFrame(const Scene& scene,std::wstring* error) {
    if (!OnOwnerThread(error) || !hwnd_ || closing_) {
        if(error && (!hwnd_ || closing_))*error=L"Cannot refresh a closed BitmapWindow";
        return false;
    }
    if (!ValidateSceneLines(scene,error)) return false;
    if (!impl_->preparedTexture) { if(error)*error=L"No GPU frame is prepared";return false; }
    const auto sameHits=[](const std::vector<HitRecord>& a,const std::vector<HitRecord>& b) {
        if(a.size()!=b.size())return false;
        for(std::size_t i=0;i<a.size();++i) {
            if(a[i].controlKey!=b[i].controlKey)return false;
            for(unsigned j=0;j<4;++j)if(a[i].bounds[j]!=b[i].bounds[j])return false;
        }
        return true;
    };
    if(scene.width!=logicalWidth_ || scene.height!=logicalHeight_ ||
       !sameHits(scene.hits,hits_) || !sameHits(scene.scrolls,scrolls_) ||
       scene.pixelHits.indices!=pixelHits_.indices || scene.pixelHits.keys!=pixelHits_.keys) {
        if(error)*error=L"Visual refresh cannot change committed input geometry";
        return false;
    }
    if (!impl_->renderFailure.empty()) { if(error)*error=impl_->renderFailure;return false; }
    if (!EnsureRenderTarget(error)) return false;
    ComPtr<ID2D1Bitmap> candidate;
    if(!impl_->ShareSceneTexture(impl_->preparedTexture.Get(),&candidate,error))return false;
    impl_->bitmap=std::move(candidate);
    impl_->source.Reset();
    impl_->sceneTexture=std::move(impl_->preparedTexture);
    InvalidateRect(hwnd_,nullptr,FALSE);
    return true;
}

bool BitmapWindow::UpdateSceneImpl(const Scene& scene,const std::wstring* renderedPng,
                                   bool retainPendingInput,bool preparedGpu,std::wstring* error,
                                   std::uint64_t editorOwner,std::uint64_t textFocusEpoch) {
    if (!OnOwnerThread(error) || !hwnd_) {
        if (error && !hwnd_) *error=L"Cannot update a closed BitmapWindow";
        return false;
    }
    if (preparedGpu && !impl_->preparedTexture) { if(error)*error=L"No GPU frame is prepared";return false; }
    const bool retainEditor=editorOwner && textFocusEpoch;
    if((editorOwner!=0)!=(textFocusEpoch!=0) ||
       (retainEditor && (!retainPendingInput || !textInputEnabled_ || !nativeTextFocused_ ||
        editorOwner!=editorOwner_ || textFocusEpoch!=textFocusEpoch_))) {
        if(error)*error=L"Editor refresh requires the exact current text owner and native focus epoch";
        return false;
    }
    if (!ValidSceneContract(scene,error)) return false;
    if (sceneGeneration_==((std::numeric_limits<std::uint64_t>::max)())) {
        if(error)*error=L"BitmapWindow scene generation is exhausted";
        return false;
    }
    if (!retainPendingInput && !pending_.empty()) {
        if(error)*error=L"Drain pending input events before updating the scene";
        return false;
    }
    const bool emptyScene=IsSceneEmpty(scene);
    if (!emptyScene && renderedPng && renderedPng->empty()) {
        if(error)*error=L"A nonempty scene requires a retained PNG";
        return false;
    }
    std::vector<HitRecord> nextHits,nextScrolls;
    PixelHitMap nextPixelHits;
    try { nextHits=scene.hits; nextScrolls=scene.scrolls; nextPixelHits=scene.pixelHits; }
    catch (const std::bad_alloc&) { if(error)*error=L"Could not retain updated scene input records"; return false; }
    ComPtr<IWICBitmap> nextSource;
    if (renderedPng && !renderedPng->empty() &&
        !impl_->DecodeSceneBitmap(*renderedPng,logicalWidth_,logicalHeight_,&nextSource,error))
        return false;
    if (emptyScene) nextSource.Reset();
    ComPtr<ID3D11Texture2D> nextTexture;
    if (preparedGpu) nextTexture=impl_->preparedTexture;
    else if (!renderedPng && !emptyScene &&
        (!EnsureRenderTarget(error) || !impl_->DrawGpuScene(scene,&nextTexture,error))) return false;
    if (retainPendingInput) {
        // Dispatch a finite prefix so a continuously replenished message queue cannot
        // prevent the scene commit. Messages still queued after this budget are handled
        // by the host's ordinary pump after it drains the retained old-generation batch.
        const HWND updateWindow=hwnd_;
        MSG msg{};
        std::size_t dispatched=0;
        while (hwnd_==updateWindow && dispatched<kMaxRetainingUpdateMessages &&
               PeekMessageW(&msg,updateWindow,0,0,PM_REMOVE)) {
            TranslateMessage(&msg);
            DispatchMessageW(&msg);
            ++dispatched;
        }
    } else if (!PumpMessages(error)) {
        return false;
    }
    if (!hwnd_) { if(error)*error=L"BitmapWindow closed while applying the scene update"; return false; }
    if (!retainPendingInput && !pending_.empty()) {
        if(error)*error=L"Queued old-scene input was retained; drain it before retrying the scene update";
        return false;
    }
    if (!impl_->renderFailure.empty()) { if(error)*error=impl_->renderFailure; return false; }
    if (!EnsureRenderTarget(error)) return false;
    ComPtr<ID2D1Bitmap> nextBitmap;
    if (nextTexture) {
        if (!impl_->ShareSceneTexture(nextTexture.Get(),&nextBitmap,error)) return false;
    } else if (nextSource) {
        const HRESULT hr=impl_->target->CreateBitmapFromWicBitmap(nextSource.Get(),nullptr,&nextBitmap);
        if (FAILED(hr)) { if(error)*error=HrMessage(L"Create updated scene bitmap",hr); return false; }
    }
    impl_->bitmap=nextBitmap;
    impl_->source=nextSource;
    impl_->sceneTexture=nextTexture;
    impl_->preparedTexture.Reset();
    hits_.swap(nextHits);
    scrolls_.swap(nextScrolls);
    pixelHits_.indices.swap(nextPixelHits.indices);
    pixelHits_.keys.swap(nextPixelHits.keys);
    ++sceneGeneration_;
    worldWheelGeneration_=0;
    // A same-editor refresh may span UTF-16 code units. Geometry-only callers
    // must not join a prefix to a different editor or native focus lifetime.
    if(!retainEditor || editorOwner!=editorOwner_ || textFocusEpoch!=textFocusEpoch_) {
        if(editorOwner_)InvalidateTextFocus(true,false);
        else pendingHighSurrogate_=0;
    }
    // A press belongs to the geometry generation where it began. Do not let a
    // later release activate a replacement scene. Visual-only refresh does not
    // pass through this commit path and therefore keeps its press intact.
    CancelPointerPresses();
    inputCutoffTick_=GetTickCount();
    inputCutoffActive_=true;
    InvalidateRect(hwnd_,nullptr,FALSE);
    return true;
}

std::uint64_t BitmapWindow::SceneGeneration() const {
    return OnOwnerThread(nullptr) && hwnd_?sceneGeneration_:0;
}

bool BitmapWindow::OnOwnerThread(std::wstring* error) const {
    if (GetCurrentThreadId()==ownerThreadId_) return true;
    if (error) *error=L"BitmapWindow methods must run on the HWND owning thread";
    return false;
}

bool BitmapWindow::IsInputMessageCurrent() const {
    // Best-effort filtering only: equal millisecond timestamps are ambiguous.
    // The managed producer barrier, not this timestamp, defines the strict API epoch.
    if (!inputCutoffActive_) return true;
    const LONG messageTime=GetMessageTime();
    if (messageTime==-1) return true;
    return static_cast<LONG>(static_cast<DWORD>(messageTime)-inputCutoffTick_)>=0;
}

bool BitmapWindow::IsTextInputMessageCurrent() const {
    if(!editorOwner_)return IsInputMessageCurrent();
    if(!textInputCutoffActive_)return true;
    const LONG messageTime=GetMessageTime();
    if(messageTime==-1)return true;
    // A native/editor focus transition has its own cutoff. Same-editor scene
    // refresh leaves it untouched; ambiguous equal-tick transition input fails closed.
    return static_cast<LONG>(static_cast<DWORD>(messageTime)-textInputCutoffTick_)>0;
}

void BitmapWindow::Show(bool visible) {
    if (!hwnd_ || GetCurrentThreadId()!=ownerThreadId_) return;
    if (!visible) { ShowWindow(hwnd_,SW_HIDE); return; }
    if (!SetWindowPos(hwnd_,HWND_TOP,0,0,0,0,
                      SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE|SWP_SHOWWINDOW)) {
        const DWORD lastError=GetLastError();
        LatchRenderFailure(HrMessage(L"Raise owned HWND without activating it",
            HRESULT_FROM_WIN32(lastError?lastError:ERROR_GEN_FAILURE)));
    }
}

bool BitmapWindow::ReadDisplaySettings(DisplaySettings* settings,std::wstring* error) const {
    if(!settings || !OnOwnerThread(error) || !hwnd_ || !impl_ || !impl_->swapChain)return false;
    RECT client{};BOOL fullscreen=FALSE;
    if(!GetClientRect(hwnd_,&client) || FAILED(impl_->swapChain->GetFullscreenState(&fullscreen,nullptr))){
        if(error)*error=L"Cannot read the owned window display settings";return false;
    }
    settings->width=static_cast<std::uint32_t>(client.right-client.left);
    settings->height=static_cast<std::uint32_t>(client.bottom-client.top);
    settings->fullscreen=fullscreen!=FALSE;settings->vsync=impl_->verticalSync;return true;
}

bool BitmapWindow::ApplyDisplaySettings(const DisplaySettings& requested,DisplaySettings* actual,std::wstring* error){
    DisplaySettings before;
    if(!actual || inWindowProc_ || !ReadDisplaySettings(&before,error))return false;
    if(!ValidFrameDimensions(requested.width,requested.height) || requested.width<640 || requested.height<480){
        if(error)*error=L"Display dimensions are outside the supported range";return false;
    }
    auto apply=[this](const DisplaySettings& value,std::wstring* failure){
        if(value.fullscreen){
            ComPtr<IDXGIOutput> output;
            DXGI_SWAP_CHAIN_DESC1 desc{};DXGI_MODE_DESC desired{},mode{};
            desired.Width=value.width;desired.Height=value.height;desired.Format=DXGI_FORMAT_B8G8R8A8_UNORM;
            if(FAILED(impl_->swapChain->GetDesc1(&desc)) ||
               FAILED(impl_->swapChain->GetContainingOutput(&output))){
                if(failure)*failure=L"Cannot identify the owned window display output";return false;
            }
            desired.Format=desc.Format;
            if(FAILED(output->FindClosestMatchingMode(&desired,&mode,impl_->device.Get())) ||
               mode.Width!=value.width || mode.Height!=value.height){
                if(failure)*failure=L"The display does not support this fullscreen resolution";return false;
            }
            if(FAILED(impl_->swapChain->ResizeTarget(&mode)) ||
               FAILED(impl_->swapChain->SetFullscreenState(TRUE,output.Get()))){
                if(failure)*failure=L"Cannot apply the requested fullscreen display mode";return false;
            }
        }else{
            if(FAILED(impl_->swapChain->SetFullscreenState(FALSE,nullptr)) || !ResizeClient(value.width,value.height,failure))return false;
        }
        impl_->verticalSync=value.vsync;
        return true;
    };
    std::wstring failure;
    const bool applied=apply(requested,&failure) && ReadDisplaySettings(actual,&failure) &&
        actual->width==requested.width && actual->height==requested.height &&
        actual->fullscreen==requested.fullscreen && actual->vsync==requested.vsync;
    if(applied)return true;
    std::wstring rollback;
    DisplaySettings restored;
    if(!apply(before,&rollback) || !ReadDisplaySettings(&restored,&rollback) ||
       restored.width!=before.width || restored.height!=before.height ||
       restored.fullscreen!=before.fullscreen || restored.vsync!=before.vsync){
        LatchRenderFailure(L"Display settings rollback failed: "+rollback);
        if(error)*error=impl_->renderFailure;return false;
    }
    if(error)*error=failure.empty()?L"The display did not accept the exact requested settings":failure;
    return false;
}

bool BitmapWindow::ResizeClient(std::uint32_t width,std::uint32_t height,std::wstring* error) {
    if (!OnOwnerThread(error) || !hwnd_) return false;
    if (!ValidFrameDimensions(width,height)) {
        if(error)*error=L"Requested client size exceeds the 32768 or 256 MiB frame limit"; return false;
    }
    if (!impl_->renderFailure.empty()) { if(error)*error=impl_->renderFailure; return false; }
    RECT rect{0,0,static_cast<LONG>(width),static_cast<LONG>(height)};
    const DWORD style=static_cast<DWORD>(GetWindowLongPtrW(hwnd_,GWL_STYLE));
    const DWORD exStyle=static_cast<DWORD>(GetWindowLongPtrW(hwnd_,GWL_EXSTYLE));
    if (!AdjustWindowRectExForDpi(&rect,style,FALSE,exStyle,dpi_)) {
        if(error)*error=L"AdjustWindowRectExForDpi failed"; return false;
    }
    LONG outerWidth=rect.right-rect.left,outerHeight=rect.bottom-rect.top;
    LONG actualWidth=0,actualHeight=0;
    for (int attempt=0;attempt!=3;++attempt) {
        if (!SetWindowPos(hwnd_,nullptr,0,0,outerWidth,outerHeight,SWP_NOMOVE|SWP_NOZORDER|SWP_NOACTIVATE)) {
            if(error)*error=L"SetWindowPos failed"; return false;
        }
        RECT actual{};
        if (!GetClientRect(hwnd_,&actual)) { if(error)*error=L"GetClientRect failed after resize"; return false; }
        actualWidth=actual.right-actual.left; actualHeight=actual.bottom-actual.top;
        const LONG dx=static_cast<LONG>(width)-actualWidth;
        const LONG dy=static_cast<LONG>(height)-actualHeight;
        if (!impl_->renderFailure.empty()) { if(error)*error=impl_->renderFailure; return false; }
        if (!dx && !dy) return true;
        outerWidth+=dx; outerHeight+=dy;
    }
    if(error) {
        wchar_t message[160]={};
        swprintf_s(message,L"Windows could not satisfy requested client size %ux%u (actual %ldx%ld)",
                   width,height,actualWidth,actualHeight);
        *error=message;
    }
    return false;
}

bool BitmapWindow::PumpMessages(std::wstring* error) {
    if (!OnOwnerThread(error) || !hwnd_) return false;
    const HWND ownedWindow=hwnd_;
    MSG msg{};
    while (PeekMessageW(&msg,ownedWindow,0,0,PM_REMOVE)) {
        TranslateMessage(&msg); DispatchMessageW(&msg);
    }
    if (!impl_->renderFailure.empty()) { if(error)*error=impl_->renderFailure; return false; }
    return true;
}

bool BitmapWindow::CaptureFrame(const std::wstring& png,std::wstring* error) {
    if (!OnOwnerThread(error) || !hwnd_) return false;
    if (!impl_->renderFailure.empty()) { if(error)*error=impl_->renderFailure; return false; }
    return RenderFrame(&png,error);
}

bool BitmapWindow::GetFrameInfo(BitmapFrameInfo* info,std::wstring* error) const {
    if (!info) { if(error)*error=L"Frame info output is null"; return false; }
    if (!OnOwnerThread(error) || !hwnd_) return false;
    RECT client{};
    if (!GetClientRect(hwnd_,&client)) { if(error)*error=L"GetClientRect failed while reading frame info"; return false; }
    if (!impl_->swapChain) { if(error)*error=L"DXGI swap chain is not initialized"; return false; }
    DXGI_SWAP_CHAIN_DESC1 desc{};
    const HRESULT hr=impl_->swapChain->GetDesc1(&desc);
    if (FAILED(hr)) { if(error)*error=HrMessage(L"Read DXGI back-buffer dimensions",hr); return false; }
    const UINT clientWidth=static_cast<UINT>(client.right-client.left);
    const UINT clientHeight=static_cast<UINT>(client.bottom-client.top);
    if (desc.Width!=clientWidth || desc.Height!=clientHeight) {
        if(error)*error=L"DXGI back-buffer dimensions do not match the HWND client dimensions";
        return false;
    }
    info->clientWidth=clientWidth;
    info->clientHeight=clientHeight;
    info->renderCount=impl_->renderCount;
    info->presentCount=impl_->presentCount;
    info->lastPresentResult=static_cast<std::int32_t>(impl_->lastPresentResult);
    info->deviceKind=impl_->deviceKind;
    info->deviceIdentity=static_cast<std::uint64_t>(reinterpret_cast<std::uintptr_t>(impl_->device.Get()));
    info->lastPresentOccluded=impl_->lastPresentOccluded;
    return true;
}

bool BitmapWindow::DrainInputs(std::vector<BitmapInputEvent>* events,std::wstring* error) {
    if (!events) { if(error)*error=L"Input output vector is null"; return false; }
    if (!OnOwnerThread(error)) return false;
    events->clear();
    if (queueOverflow_) {
        queueOverflow_=false; events->swap(pending_);
        if(error)*error=L"BitmapWindow input queue overflowed; returned events may be incomplete";
        return false;
    }
    events->swap(pending_);
    return true;
}

bool BitmapWindow::EnableGameplayInput(bool enabled,std::wstring* error) {
    if(!OnOwnerThread(error) || !hwnd_)return false;
    if(!enabled && !SetWorldWheelViewport(nullptr,error))return false;
    gameplayInputEnabled_=enabled;return true;
}

bool BitmapWindow::SetWorldWheelViewport(const BitmapDisplayRect* viewport,std::wstring* error) {
    if(!OnOwnerThread(error) || !hwnd_ || closing_){
        if(error && (!hwnd_ || closing_))*error=L"World wheel input requires an open BitmapWindow";
        return false;
    }
    if(viewport && (!gameplayInputEnabled_ || !productionPointerInputEnabled_ || !sceneGeneration_ ||
        !std::isfinite(viewport->left) || !std::isfinite(viewport->top) ||
        !std::isfinite(viewport->right) || !std::isfinite(viewport->bottom) ||
        viewport->left<0.0f || viewport->top<0.0f || viewport->right<=viewport->left ||
        viewport->bottom<=viewport->top || viewport->right>static_cast<float>(logicalWidth_) ||
        viewport->bottom>static_cast<float>(logicalHeight_))){
        if(error)*error=L"World wheel viewport requires enabled gameplay pointer input and valid scene bounds";
        return false;
    }
    if(viewport && worldWheelGeneration_==sceneGeneration_ &&
        viewport->left==worldWheelViewport_.left && viewport->top==worldWheelViewport_.top &&
        viewport->right==worldWheelViewport_.right && viewport->bottom==worldWheelViewport_.bottom)return true;
    worldWheelViewport_=viewport?*viewport:BitmapDisplayRect{};
    worldWheelGeneration_=viewport?sceneGeneration_:0;
    // Explicit ownership changes cannot replay old world wheel input on rebind.
    pending_.erase(std::remove_if(pending_.begin(),pending_.end(),[](const BitmapInputEvent& event){
        return event.kind==BitmapInputKind::WorldWheel;
    }),pending_.end());
    return true;
}

bool BitmapWindow::EnableTextInput(bool enabled,std::wstring* error,std::uint64_t editorOwner) {
    if(!OnOwnerThread(error) || !hwnd_ || closing_){
        if(error && (!hwnd_ || closing_))*error=L"Text input requires an open BitmapWindow";
        return false;
    }
    if(!enabled && editorOwner){if(error)*error=L"Disabled text input cannot have an editor owner";return false;}
    if(textInputEnabled_==enabled && editorOwner_==editorOwner)return true;
    const bool boundTransition=editorOwner_ || editorOwner;
    // Discard raw old-owner editor messages before the new owner is installed.
    // No SDK/Lua function is reached while changing native ownership.
    InvalidateTextFocus(true,boundTransition);
    textInputEnabled_=enabled;
    editorOwner_=editorOwner;
    return true;
}

bool BitmapWindow::GetTextInputState(BitmapTextInputState* state,std::wstring* error) const {
    if(!state){if(error)*error=L"Text input state output is null";return false;}
    if(!OnOwnerThread(error) || !hwnd_ || closing_)return false;
    *state={editorOwner_,textFocusEpoch_,textInputEnabled_ && (!editorOwner_ || nativeTextFocused_)};return true;
}

bool BitmapWindow::EnableProductionPointerInput(bool enabled,std::wstring* error,bool automaticLeaveTracking) {
    if (!OnOwnerThread(error) || !hwnd_ || closing_) {
        if (error && !hwnd_) *error=L"Production pointer input requires an open BitmapWindow";
        return false;
    }
    if(!enabled && !SetWorldWheelViewport(nullptr,error))return false;
    if (productionPointerInputEnabled_==enabled && automaticLeaveTracking_==automaticLeaveTracking) return true;
    if (!enabled && productionPointerInputEnabled_)
        QueuePointerMove(-1,-1); // Release retained hover before opting out.
    if (productionPointerInputEnabled_ && trackingMouseLeave_ && !automaticLeaveTracking) {
        TRACKMOUSEEVENT cancel{};cancel.cbSize=sizeof(cancel);cancel.dwFlags=TME_CANCEL|TME_LEAVE;cancel.hwndTrack=hwnd_;
        TrackMouseEvent(&cancel);
        trackingMouseLeave_=false;
    }
    productionPointerInputEnabled_=enabled;
    automaticLeaveTracking_=automaticLeaveTracking;
    if (!enabled) trackingMouseLeave_=false;
    return true;
}

bool BitmapWindow::IsOpen() const { return GetCurrentThreadId()==ownerThreadId_ && hwnd_!=nullptr && !closing_; }
HWND BitmapWindow::NativeHandle() const { return GetCurrentThreadId()==ownerThreadId_?hwnd_:nullptr; }

BitmapDisplayRect BitmapWindow::ComputeDisplayRect(std::uint32_t clientWidth,std::uint32_t clientHeight) {
    BitmapDisplayRect rect{};
    if (!clientWidth || !clientHeight) return rect;
    const double sx=static_cast<double>(clientWidth)/kLogicalWidth;
    const double sy=static_cast<double>(clientHeight)/kLogicalHeight;
    const double scale=(std::min)(sx,sy);
    const double width=kLogicalWidth*scale,height=kLogicalHeight*scale;
    rect.left=static_cast<float>((clientWidth-width)*0.5);
    rect.top=static_cast<float>((clientHeight-height)*0.5);
    rect.right=static_cast<float>(rect.left+width);
    rect.bottom=static_cast<float>(rect.top+height);
    return rect;
}

bool BitmapWindow::MapClientPointToLogical(std::uint32_t clientWidth,std::uint32_t clientHeight,
                                           std::int32_t x,std::int32_t y,float* logicalX,float* logicalY) {
    if (!logicalX || !logicalY) return false;
    const BitmapDisplayRect rect=ComputeDisplayRect(clientWidth,clientHeight);
    if (x<rect.left || y<rect.top || x>=rect.right || y>=rect.bottom) return false;
    *logicalX=(static_cast<float>(x)-rect.left)*kLogicalWidth/(rect.right-rect.left);
    *logicalY=(static_cast<float>(y)-rect.top)*kLogicalHeight/(rect.bottom-rect.top);
    return *logicalX>=0 && *logicalY>=0 && *logicalX<kLogicalWidth && *logicalY<kLogicalHeight;
}

bool BitmapWindow::EnsureGpuDevice(std::wstring* error) {
    if (!impl_->wic) {
        const HRESULT hr=CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,
                                           IID_PPV_ARGS(&impl_->wic));
        if (FAILED(hr)) { if(error)*error=HrMessage(L"Create WIC factory",hr); return false; }
    }
    if (!impl_->d2d) {
        const D2D1_FACTORY_OPTIONS options={};
        const HRESULT hr=D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED,options,impl_->d2d.GetAddressOf());
        if (FAILED(hr)) { if(error)*error=HrMessage(L"Create Direct2D factory",hr); return false; }
    }
    if (!impl_->device) {
        const UINT flags=D3D11_CREATE_DEVICE_BGRA_SUPPORT;
        D3D_FEATURE_LEVEL selected{};
        HRESULT hr=D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,flags,nullptr,0,
                                     D3D11_SDK_VERSION,&impl_->device,&selected,&impl_->context);
        if (SUCCEEDED(hr)) impl_->deviceKind=BitmapDeviceKind::Hardware;
        else {
            impl_->device.Reset(); impl_->context.Reset();
            hr=D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,flags,nullptr,0,
                                 D3D11_SDK_VERSION,&impl_->device,&selected,&impl_->context);
            if (FAILED(hr)) { if(error)*error=HrMessage(L"Create D3D11 hardware and WARP devices",hr); return false; }
            impl_->deviceKind=BitmapDeviceKind::Warp;
        }
    }
    return true;
}

bool BitmapWindow::EnsureRenderTarget(std::wstring* error) {
    if (impl_->target) return true;
    if (!EnsureGpuDevice(error)) return false;
    RECT client{}; if (!GetClientRect(hwnd_,&client)) { if(error)*error=L"GetClientRect failed"; return false; }
    const UINT width=static_cast<UINT>(client.right-client.left);
    const UINT height=static_cast<UINT>(client.bottom-client.top);
    if (!width || !height || width>32768 || height>32768 ||
        static_cast<std::uint64_t>(width)*height*4ull>kMaxFrameBytes) {
        if(error)*error=L"Swap-chain client dimensions exceed the frame memory limit";
        return false;
    }
    if (!impl_->swapChain) {
        ComPtr<IDXGIDevice> dxgiDevice;
        HRESULT hr=impl_->device.As(&dxgiDevice);
        if (FAILED(hr)) { if(error)*error=HrMessage(L"Query IDXGIDevice",hr); return false; }
        ComPtr<IDXGIAdapter> adapter;
        hr=dxgiDevice->GetAdapter(&adapter);
        if (FAILED(hr)) { if(error)*error=HrMessage(L"Get D3D11 DXGI adapter",hr); return false; }
        ComPtr<IDXGIFactory2> factory;
        hr=adapter->GetParent(IID_PPV_ARGS(&factory));
        if (FAILED(hr)) { if(error)*error=HrMessage(L"Get DXGI factory",hr); return false; }
        DXGI_SWAP_CHAIN_DESC1 desc{};
        desc.Width=width; desc.Height=height; desc.Format=DXGI_FORMAT_B8G8R8A8_UNORM;
        desc.SampleDesc.Count=1; desc.BufferUsage=DXGI_USAGE_RENDER_TARGET_OUTPUT;
        desc.BufferCount=2; desc.Scaling=DXGI_SCALING_STRETCH;
        desc.SwapEffect=DXGI_SWAP_EFFECT_FLIP_SEQUENTIAL;
        desc.AlphaMode=DXGI_ALPHA_MODE_IGNORE;
        hr=factory->CreateSwapChainForHwnd(impl_->device.Get(),hwnd_,&desc,nullptr,nullptr,&impl_->swapChain);
        if (FAILED(hr)) { if(error)*error=HrMessage(L"Create HWND DXGI swap chain",hr); return false; }
        factory->MakeWindowAssociation(hwnd_,DXGI_MWA_NO_ALT_ENTER);
    }
    if (!impl_->swapChain) { if(error)*error=L"DXGI swap chain is unavailable"; return false; }
    HRESULT hr=impl_->swapChain->GetBuffer(0,IID_PPV_ARGS(&impl_->surface));
    if (FAILED(hr)) { if(error)*error=HrMessage(L"Get DXGI back-buffer surface",hr); return false; }
    D2D1_RENDER_TARGET_PROPERTIES props=D2D1::RenderTargetProperties(
        D2D1_RENDER_TARGET_TYPE_DEFAULT,
        D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_PREMULTIPLIED),
        96.0f,96.0f,D2D1_RENDER_TARGET_USAGE_NONE,D2D1_FEATURE_LEVEL_DEFAULT);
    hr=impl_->d2d->CreateDxgiSurfaceRenderTarget(impl_->surface.Get(),props,&impl_->target);
    if (FAILED(hr)) { impl_->surface.Reset(); if(error)*error=HrMessage(L"Create Direct2D DXGI surface target",hr); return false; }
    if (impl_->sceneTexture) {
        if (!impl_->ShareSceneTexture(impl_->sceneTexture.Get(),&impl_->bitmap,error)) {
            ReleaseRenderTarget();return false;
        }
    } else if (impl_->source) {
        hr=impl_->target->CreateBitmapFromWicBitmap(impl_->source.Get(),nullptr,&impl_->bitmap);
        if (FAILED(hr)) { ReleaseRenderTarget(); if(error)*error=HrMessage(L"Create scene bitmap",hr); return false; }
    }
    return true;
}

void BitmapWindow::ReleaseRenderTarget() {
    if (!impl_) return;
    impl_->bitmap.Reset(); impl_->target.Reset(); impl_->surface.Reset();
}

void BitmapWindow::LatchRenderFailure(const std::wstring& error) {
    if (impl_ && impl_->renderFailure.empty()) impl_->renderFailure=error;
}

bool BitmapWindow::RenderFrame(const std::wstring* capturePng,std::wstring* error) {
    std::wstring localError;
    std::wstring* failure=error?error:&localError;
    if (!EnsureRenderTarget(failure)) { LatchRenderFailure(*failure); return false; }
    RECT client{};
    if (!GetClientRect(hwnd_,&client)) { *failure=L"GetClientRect failed before drawing"; LatchRenderFailure(*failure); return false; }
    const UINT width=static_cast<UINT>(client.right-client.left),height=static_cast<UINT>(client.bottom-client.top);
    if (!width || !height) return true;
    const BitmapDisplayRect display=ComputeDisplayRect(width,height);
    impl_->target->BeginDraw();
    impl_->target->SetAntialiasMode(D2D1_ANTIALIAS_MODE_ALIASED);
    impl_->target->Clear(D2D1::ColorF(0,0,0,1));
    if (impl_->bitmap) {
        const D2D1_RECT_F destination=D2D1::RectF(display.left,display.top,display.right,display.bottom);
        const D2D1_RECT_F source=D2D1::RectF(0,0,static_cast<float>(logicalWidth_),static_cast<float>(logicalHeight_));
        impl_->target->DrawBitmap(impl_->bitmap.Get(),destination,1.0f,
                                  D2D1_BITMAP_INTERPOLATION_MODE_NEAREST_NEIGHBOR,&source);
    }
    HRESULT hr=impl_->target->EndDraw();
    if (FAILED(hr)) {
        *failure=HrMessage(L"Direct2D EndDraw",hr);
        LatchRenderFailure(*failure);
        ReleaseRenderTarget(); return false;
    }
    ++impl_->renderCount;
    if (capturePng) {
        const DWORD attrs=GetFileAttributesW(capturePng->c_str());
        if (attrs!=INVALID_FILE_ATTRIBUTES) {
            *failure=L"Capture destination already exists; refusing to overwrite";
            return false;
        }
        HANDLE reservation=CreateFileW(capturePng->c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,
                                       FILE_ATTRIBUTE_NORMAL,nullptr);
        if (reservation==INVALID_HANDLE_VALUE) {
            *failure=L"Create capture destination without overwrite failed";
            return false;
        }
        CloseHandle(reservation);
        bool captureOk=false;
        std::wstring readbackFailure;
        ComPtr<ID3D11Texture2D> backBuffer;
        hr=impl_->swapChain->GetBuffer(0,IID_PPV_ARGS(&backBuffer));
        if (SUCCEEDED(hr)) {
            D3D11_TEXTURE2D_DESC desc{}; backBuffer->GetDesc(&desc);
            if (desc.Width!=width || desc.Height!=height) {
                readbackFailure=L"DXGI back-buffer dimensions do not match the HWND client dimensions";
                hr=E_INVALIDARG;
            } else {
                desc.Usage=D3D11_USAGE_STAGING; desc.BindFlags=0; desc.MiscFlags=0;
                desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ; desc.SampleDesc.Count=1; desc.SampleDesc.Quality=0;
                hr=impl_->device->CreateTexture2D(&desc,nullptr,&impl_->staging);
            }
        }
        if (SUCCEEDED(hr)) {
            impl_->context->CopyResource(impl_->staging.Get(),backBuffer.Get());
            D3D11_MAPPED_SUBRESOURCE mapped{};
            hr=impl_->context->Map(impl_->staging.Get(),0,D3D11_MAP_READ,0,&mapped);
            if (SUCCEEDED(hr)) {
                const std::uint64_t stride=static_cast<std::uint64_t>(width)*4ull;
                const std::uint64_t byteCount=stride*height;
                std::vector<BYTE> bgra;
                if (width<=32768 && height<=32768 && mapped.RowPitch>=stride &&
                    static_cast<std::uint64_t>(mapped.RowPitch)*height<=kMaxFrameBytes && byteCount<=kMaxFrameBytes) {
                    try { bgra.resize(static_cast<std::size_t>(byteCount)); }
                    catch (const std::bad_alloc&) { hr=E_OUTOFMEMORY; }
                    if (SUCCEEDED(hr)) {
                        for (UINT y=0;y<height;++y) {
                            const BYTE* input=static_cast<const BYTE*>(mapped.pData)+static_cast<std::size_t>(y)*mapped.RowPitch;
                            BYTE* output=bgra.data()+static_cast<std::size_t>(y)*static_cast<std::size_t>(stride);
                            for (UINT x=0;x<width;++x) {
                                output[x*4]=input[x*4]; output[x*4+1]=input[x*4+1];
                                output[x*4+2]=input[x*4+2]; output[x*4+3]=255;
                            }
                        }
                    }
                } else hr=E_INVALIDARG;
                impl_->context->Unmap(impl_->staging.Get(),0);
                if (SUCCEEDED(hr)) {
                    ComPtr<IWICBitmap> pixels;
                    hr=impl_->wic->CreateBitmapFromMemory(width,height,GUID_WICPixelFormat32bppBGRA,
                        static_cast<UINT>(stride),static_cast<UINT>(byteCount),bgra.data(),&pixels);
                    ComPtr<IWICBitmapEncoder> encoder;
                    ComPtr<IWICBitmapFrameEncode> frame;
                    ComPtr<IWICStream> stream;
                    if (SUCCEEDED(hr)) hr=impl_->wic->CreateStream(&stream);
                    if (SUCCEEDED(hr)) hr=stream->InitializeFromFilename(capturePng->c_str(),GENERIC_WRITE);
                    if (SUCCEEDED(hr)) hr=impl_->wic->CreateEncoder(GUID_ContainerFormatPng,nullptr,&encoder);
                    if (SUCCEEDED(hr)) hr=encoder->Initialize(stream.Get(),WICBitmapEncoderNoCache);
                    if (SUCCEEDED(hr)) hr=encoder->CreateNewFrame(&frame,nullptr);
                    if (SUCCEEDED(hr)) hr=frame->Initialize(nullptr);
                    if (SUCCEEDED(hr)) hr=frame->SetSize(width,height);
                    WICPixelFormatGUID format=GUID_WICPixelFormat32bppBGRA;
                    if (SUCCEEDED(hr)) hr=frame->SetPixelFormat(&format);
                    if (SUCCEEDED(hr) && format!=GUID_WICPixelFormat32bppBGRA) hr=WINCODEC_ERR_UNSUPPORTEDPIXELFORMAT;
                    ComPtr<IWICFormatConverter> converter;
                    if (SUCCEEDED(hr)) hr=impl_->wic->CreateFormatConverter(&converter);
                    if (SUCCEEDED(hr)) hr=converter->Initialize(pixels.Get(),GUID_WICPixelFormat32bppBGRA,
                        WICBitmapDitherTypeNone,nullptr,0.0,WICBitmapPaletteTypeCustom);
                    if (SUCCEEDED(hr)) hr=frame->WriteSource(converter.Get(),nullptr);
                    if (SUCCEEDED(hr)) hr=frame->Commit();
                    if (SUCCEEDED(hr)) hr=encoder->Commit();
                }
            }
        }
        impl_->staging.Reset();
        if (FAILED(hr)) {
            DeleteFileW(capturePng->c_str());
            *failure=readbackFailure.empty()?HrMessage(L"Read back and encode DXGI frame",hr):readbackFailure;
        } else captureOk=true;
        if (!captureOk) return false;
    }
    hr=impl_->swapChain->Present(impl_->verticalSync?1u:0u,0);
    impl_->lastPresentResult=hr;
    impl_->lastPresentOccluded=(hr==DXGI_STATUS_OCCLUDED);
    if (FAILED(hr)) {
        *failure=HrMessage(L"DXGI Present",hr);
        LatchRenderFailure(*failure); return false;
    }
    ++impl_->presentCount;
    if (hr==DXGI_STATUS_OCCLUDED) return true;
    return true;
}

void BitmapWindow::QueueKey(std::uint32_t key) {
    if (pending_.size()>=kMaxQueuedInputs) { queueOverflow_=true; return; }
    BitmapInputEvent event{BitmapInputKind::KeyDown,0,key,0,0,sceneGeneration_};
    if(textInputEnabled_ && (!editorOwner_ || nativeTextFocused_) &&
       (key==VK_BACK || key==VK_DELETE || key==VK_LEFT || key==VK_RIGHT || key==VK_HOME || key==VK_END)) {
        event.editorOwner=editorOwner_;event.textFocusEpoch=textFocusEpoch_;
    }
    pending_.push_back(event);
}

void BitmapWindow::QueueTextScalar(std::uint32_t scalar) {
    if(!textInputEnabled_ || (editorOwner_ && !nativeTextFocused_) || !hwnd_ || closing_ || scalar<0x20 || scalar>0x10ffff ||
       (scalar>=0x7f && scalar<=0x9f) || (scalar>=0xd800 && scalar<=0xdfff))return;
    if(pending_.size()>=kMaxQueuedInputs){queueOverflow_=true;return;}
    BitmapInputEvent event{BitmapInputKind::TextInput,0,0,0,0,sceneGeneration_};
    event.unicodeScalar=scalar;
    event.editorOwner=editorOwner_;event.textFocusEpoch=textFocusEpoch_;
    pending_.push_back(event);
}

void BitmapWindow::QueueUtf16Character(std::uint32_t codeUnit) {
    if(codeUnit>0xffff){pendingHighSurrogate_=0;return;}
    if(codeUnit>=0xd800 && codeUnit<=0xdbff){
        pendingHighSurrogate_=static_cast<std::uint16_t>(codeUnit);return;
    }
    const auto prefix=pendingHighSurrogate_;pendingHighSurrogate_=0;
    if(codeUnit>=0xdc00 && codeUnit<=0xdfff){
        if(prefix)QueueTextScalar(0x10000u+((static_cast<std::uint32_t>(prefix)-0xd800u)<<10)+(codeUnit-0xdc00u));
        return;
    }
    QueueTextScalar(codeUnit);
}

void BitmapWindow::ResetTextInput(bool cancelComposition) {
    pendingHighSurrogate_=0;
    if(!cancelComposition)return;
    const bool composing=imeCompositionActive_;imeCompositionActive_=false;
    if(composing && hwnd_){
        const HIMC context=ImmGetContext(hwnd_);
        if(context){ImmNotifyIME(context,NI_COMPOSITIONSTR,CPS_CANCEL,0);ImmReleaseContext(hwnd_,context);}
    }
}

void BitmapWindow::InvalidateTextFocus(bool cancelComposition,bool discardQueuedMessages) {
    ResetTextInput(cancelComposition);
    if(textFocusEpoch_==((std::numeric_limits<std::uint64_t>::max)())) {
        textInputEnabled_=false;editorOwner_=0;queueOverflow_=true;
    } else ++textFocusEpoch_;
    textInputCutoffTick_=GetTickCount();textInputCutoffActive_=true;
    if(discardQueuedMessages && hwnd_) {
        const UINT kinds[]={WM_CHAR,WM_IME_CHAR,WM_UNICHAR,WM_KEYDOWN,
                            WM_IME_STARTCOMPOSITION,WM_IME_COMPOSITION,WM_IME_ENDCOMPOSITION};
        MSG message{};
        for(const auto kind:kinds) {
            std::size_t count=0;
            while(count<kMaxQueuedInputs && PeekMessageW(&message,hwnd_,kind,kind,PM_REMOVE))++count;
            if(count==kMaxQueuedInputs)queueOverflow_=true;
        }
    }
}

std::uint64_t BitmapWindow::HitTestLogicalPoint(float logicalX,float logicalY,bool* uiHit) const {
    if (uiHit) *uiHit=false;
    for (auto it=hits_.rbegin();it!=hits_.rend();++it) {
        const float* b=it->bounds;
        if (logicalX>=b[0] && logicalY>=b[1] && logicalX<b[2] && logicalY<b[3]) {
            if (uiHit) *uiHit=true;
            return it->controlKey;
        }
    }
    if (!std::isfinite(logicalX) || !std::isfinite(logicalY) || logicalX<0.0f || logicalY<0.0f ||
        logicalX>=static_cast<float>(logicalWidth_) || logicalY>=static_cast<float>(logicalHeight_) ||
        pixelHits_.indices.empty()) return 0;
    const auto x=static_cast<std::uint32_t>(std::floor(logicalX));
    const auto y=static_cast<std::uint32_t>(std::floor(logicalY));
    const std::size_t offset=static_cast<std::size_t>(y)*logicalWidth_+x;
    const std::uint32_t index=pixelHits_.indices[offset];
    if (index==0 || index>pixelHits_.keys.size()) return 0;
    return pixelHits_.keys[index-1];
}

std::uint64_t BitmapWindow::HitTestScrollLogicalPoint(float logicalX,float logicalY,bool* viewportHit) const {
    if(viewportHit)*viewportHit=false;
    for (auto it=scrolls_.rbegin();it!=scrolls_.rend();++it) {
        const float* b=it->bounds;
        if (logicalX>=b[0] && logicalY>=b[1] && logicalX<b[2] && logicalY<b[3]) {
            if(viewportHit)*viewportHit=true;
            return it->controlKey;
        }
    }
    return 0;
}

void BitmapWindow::QueueClick(BitmapInputKind kind,std::int32_t x,std::int32_t y,
                              std::uint64_t generation,bool startedOnUi,std::uint32_t modifiers,
                              const BitmapPointerPress* press) {
    RECT client{}; if (!hwnd_ || !GetClientRect(hwnd_,&client)) return;
    float logicalX=0,logicalY=0;
    if (!MapClientPointToLogical(static_cast<std::uint32_t>(client.right),
                                 static_cast<std::uint32_t>(client.bottom),x,y,&logicalX,&logicalY)) return;
    bool releasedOnUi=false;
    const std::uint64_t key=HitTestLogicalPoint(logicalX,logicalY,&releasedOnUi);
    // A UI press cannot become a world pick by dragging off a control, nor may a
    // world press turn into a UI callback. Compare hit domains, never key ranges.
    if (!key || releasedOnUi!=startedOnUi || generation!=sceneGeneration_) return;
    if (pending_.size()>=kMaxQueuedInputs) { queueOverflow_=true; return; }
    BitmapInputEvent event{kind,key,0,logicalX,logicalY,generation};
    event.modifiers=modifiers;
    if(press)StampBitmapPointerPress(event,*press);
    pending_.push_back(event);
}

void BitmapWindow::CancelPointerPresses() {
    leftPress_={}; rightPress_={};
    if (hwnd_ && GetCapture()==hwnd_) ReleaseCapture();
}

bool BitmapWindow::EnableControlDragInput(bool enabled,std::wstring* error) {
    if(!OnOwnerThread(error) || !hwnd_ || inWindowProc_)return false;
    if(controlDragInputEnabled_ && !enabled)CancelPointerPresses();
    controlDragInputEnabled_=enabled;return true;
}

bool BitmapWindow::HasControlDragCapture() const {
    return GetCurrentThreadId()==ownerThreadId_ && hwnd_ && controlDragInputEnabled_ &&
        leftPress_.active && leftPress_.uiHit && leftPress_.key &&
        leftPress_.generation==sceneGeneration_ && GetCapture()==hwnd_;
}

void BitmapWindow::QueueControlDrag(std::int32_t x,std::int32_t y) {
    if(!HasControlDragCapture() || closing_)return;
    RECT client{};float logicalX=0,logicalY=0;
    if(!GetClientRect(hwnd_,&client) || !MapClientPointToLogical(
        static_cast<std::uint32_t>(client.right),static_cast<std::uint32_t>(client.bottom),
        x,y,&logicalX,&logicalY))return;
    BitmapInputEvent event{BitmapInputKind::ControlDrag,leftPress_.key,0,logicalX,logicalY,sceneGeneration_};
    StampBitmapPointerPress(event,leftPress_);
    QueueBitmapControlDrag(pending_,event,kMaxQueuedInputs,queueOverflow_);
}

BitmapInputEvent BitmapWindow::CurrentPointerInput() const {
    BitmapInputEvent event{BitmapInputKind::PointerMove,0,0,0,0,0};
    if(GetCurrentThreadId()!=ownerThreadId_)return event;
    event.sceneGeneration=sceneGeneration_;
    if(!productionPointerInputEnabled_ || !hwnd_ || closing_)return event;
    POINT point{};RECT client{};
    if(!GetCursorPos(&point) || !ScreenToClient(hwnd_,&point) || !GetClientRect(hwnd_,&client) ||
       client.right<=0 || client.bottom<=0)return event;
    float logicalX=0,logicalY=0;
    if(!MapClientPointToLogical(static_cast<std::uint32_t>(client.right),
        static_cast<std::uint32_t>(client.bottom),point.x,point.y,&logicalX,&logicalY))return event;
    event.logicalX=logicalX;event.logicalY=logicalY;
    event.controlKey=HitTestLogicalPoint(logicalX,logicalY);
    return event;
}

void BitmapWindow::QueuePointerMove(std::int32_t x,std::int32_t y) {
    if (!productionPointerInputEnabled_ || !hwnd_ || closing_) return;
    float logicalX=0,logicalY=0;
    std::uint64_t key=0;
    RECT client{};
    if (GetClientRect(hwnd_,&client) &&
        MapClientPointToLogical(static_cast<std::uint32_t>(client.right),
                                static_cast<std::uint32_t>(client.bottom),x,y,&logicalX,&logicalY))
        key=HitTestLogicalPoint(logicalX,logicalY);
    BitmapInputEvent event{BitmapInputKind::PointerMove,key,0,logicalX,logicalY,sceneGeneration_};
    if (!pending_.empty() && pending_.back().kind==BitmapInputKind::PointerMove &&
        pending_.back().sceneGeneration==sceneGeneration_) {
        pending_.back()=event;
        return;
    }
    if (pending_.size()>=kMaxQueuedInputs) { queueOverflow_=true; return; }
    pending_.push_back(event);
}

void BitmapWindow::QueueScroll(std::int32_t x,std::int32_t y,std::int32_t wheelDelta) {
    if (!productionPointerInputEnabled_ || !hwnd_ || closing_ || !wheelDelta) return;
    RECT client{}; if (!GetClientRect(hwnd_,&client)) return;
    float logicalX=0,logicalY=0;
    if (!MapClientPointToLogical(static_cast<std::uint32_t>(client.right),
                                 static_cast<std::uint32_t>(client.bottom),x,y,&logicalX,&logicalY)) return;
    bool scrollViewport=false;
    const std::uint64_t key=HitTestScrollLogicalPoint(logicalX,logicalY,&scrollViewport);
    if(scrollViewport){
        if(!key)return; // An empty or callback-free ScrollPanel still owns its viewport.
        const float delta=-static_cast<float>(wheelDelta)*(kPrototypeScrollPixelsPerNotch/static_cast<float>(WHEEL_DELTA));
        if (!std::isfinite(delta) || delta==0.0f) return;
        if (pending_.size()>=kMaxQueuedInputs) { queueOverflow_=true; return; }
        pending_.push_back({BitmapInputKind::Scroll,key,0,logicalX,logicalY,sceneGeneration_,delta});
        return;
    }
    bool uiHit=false;
    HitTestLogicalPoint(logicalX,logicalY,&uiHit);
    if(uiHit || !gameplayInputEnabled_ || !worldWheelGeneration_ || worldWheelGeneration_!=sceneGeneration_ ||
        logicalX<worldWheelViewport_.left || logicalY<worldWheelViewport_.top ||
        logicalX>=worldWheelViewport_.right || logicalY>=worldWheelViewport_.bottom)return;
    BitmapInputEvent event{BitmapInputKind::WorldWheel,0,0,logicalX,logicalY,sceneGeneration_};
    event.wheelDelta=wheelDelta;
    if(!pending_.empty() && pending_.back().kind==BitmapInputKind::WorldWheel &&
        pending_.back().sceneGeneration==sceneGeneration_ &&
        (pending_.back().wheelDelta>0)==(wheelDelta>0)){
        const std::int64_t total=static_cast<std::int64_t>(pending_.back().wheelDelta)+wheelDelta;
        if(total<(std::numeric_limits<std::int32_t>::min)() || total>(std::numeric_limits<std::int32_t>::max)()){
            queueOverflow_=true;return;
        }
        event.wheelDelta=static_cast<std::int32_t>(total);
        pending_.back()=event;return;
    }
    if (pending_.size()>=kMaxQueuedInputs) { queueOverflow_=true; return; }
    pending_.push_back(event);
}

void BitmapWindow::QueueClose() {
    if (closeQueued_) return;
    closeQueued_=true;if(!gameplayInputEnabled_)closing_=true;
    if (pending_.size()>=kMaxQueuedInputs) {
        queueOverflow_=true;
        auto found=std::find_if(pending_.begin(),pending_.end(),[](const BitmapInputEvent& e){return e.kind!=BitmapInputKind::CloseRequest;});
        if (found!=pending_.end()) pending_.erase(found);
    }
    pending_.push_back({BitmapInputKind::CloseRequest,0,0,0,0,sceneGeneration_});
}

LRESULT CALLBACK BitmapWindow::WindowProc(HWND hwnd,UINT message,WPARAM wParam,LPARAM lParam) {
    BitmapWindow* self=reinterpret_cast<BitmapWindow*>(GetWindowLongPtrW(hwnd,GWLP_USERDATA));
    if (message==WM_NCCREATE) {
        CREATESTRUCTW* create=reinterpret_cast<CREATESTRUCTW*>(lParam);
        self=static_cast<BitmapWindow*>(create->lpCreateParams);
        SetWindowLongPtrW(hwnd,GWLP_USERDATA,reinterpret_cast<LONG_PTR>(self));
        if (self) self->hwnd_=hwnd;
    }
    if (!self) return DefWindowProcW(hwnd,message,wParam,lParam);
    if (self->inWindowProc_) {
        // DestroyWindow synchronously re-enters with lifecycle messages from WM_CLOSE.
        // Keep painting/input handlers guarded while still releasing HWND-owned state.
        if (message==WM_DESTROY) { self->closing_=true; self->ReleaseRenderTarget(); }
        if (message==WM_NCDESTROY) {
            SetWindowLongPtrW(hwnd,GWLP_USERDATA,0);
            self->hwnd_=nullptr;
            self->closing_=true;
        }
        // A sent close can re-enter while rendering/COM dispatches messages.
        // Preserve the gameplay save-and-close queue even in that path:
        // DefWindowProc would otherwise destroy the HWND immediately.
        if (message==WM_SIZE || message==WM_DPICHANGED || message==WM_CLOSE ||
            message==WM_CHAR || message==WM_IME_CHAR || message==WM_UNICHAR ||
            message==WM_IME_STARTCOMPOSITION || message==WM_IME_ENDCOMPOSITION ||
            message==WM_KILLFOCUS || message==WM_CANCELMODE || message==WM_SETFOCUS)
            return self->HandleMessage(message,wParam,lParam);
        return DefWindowProcW(hwnd,message,wParam,lParam);
    }
    self->inWindowProc_=true;
    const LRESULT result=self->HandleMessage(message,wParam,lParam);
    self->inWindowProc_=false;
    if (message==WM_NCDESTROY) {
        SetWindowLongPtrW(hwnd,GWLP_USERDATA,0);
        self->hwnd_=nullptr;
        self->closing_=true;
    }
    return result;
}

LRESULT BitmapWindow::HandleMessage(UINT message,WPARAM wParam,LPARAM lParam) {
    switch(message) {
    case WM_ERASEBKGND: return 1;
    case WM_PAINT: {
        PAINTSTRUCT ps{}; BeginPaint(hwnd_,&ps);
        std::wstring failure;
        if (!RenderFrame(nullptr,&failure)) LatchRenderFailure(failure.empty()?L"BitmapWindow paint failed":failure);
        EndPaint(hwnd_,&ps); return 0;
    }
    case WM_SIZE:
        if (impl_->swapChain && LOWORD(lParam) && HIWORD(lParam)) {
            ReleaseRenderTarget();
            impl_->staging.Reset();
            impl_->context->ClearState();
            const HRESULT hr=impl_->swapChain->ResizeBuffers(0,LOWORD(lParam),HIWORD(lParam),
                                                              DXGI_FORMAT_UNKNOWN,0);
            if (FAILED(hr)) LatchRenderFailure(HrMessage(L"Resize DXGI swap-chain buffers",hr));
        }
        InvalidateRect(hwnd_,nullptr,FALSE); return 0;
    case WM_DPICHANGED: {
        dpi_=HIWORD(wParam);
        const RECT* suggested=reinterpret_cast<const RECT*>(lParam);
        SetWindowPos(hwnd_,nullptr,suggested->left,suggested->top,
                     suggested->right-suggested->left,suggested->bottom-suggested->top,
                     SWP_NOZORDER|SWP_NOACTIVATE);
        ReleaseRenderTarget(); InvalidateRect(hwnd_,nullptr,FALSE); return 0;
    }
    case WM_KEYDOWN: {
        if(textInputEnabled_ && editorOwner_ && !nativeTextFocused_)return 0;
        const bool editingKey=textInputEnabled_ && (wParam==VK_BACK || wParam==VK_DELETE ||
            wParam==VK_LEFT || wParam==VK_RIGHT || wParam==VK_HOME || wParam==VK_END);
        // Return/Backspace/Escape belong to the IME while composing. A commit
        // must not also invoke the focused EditBox's save/cancel callback.
        if(textInputEnabled_ && imeCompositionActive_)return DefWindowProcW(hwnd_,message,wParam,lParam);
        if ((editingKey?IsTextInputMessageCurrent():IsInputMessageCurrent()) && ((lParam&(1ll<<30))==0 || editingKey)) {
            if (wParam==VK_ESCAPE || wParam==VK_RETURN ||
                ShouldQueueBitmapGameplayNavigationKey(gameplayInputEnabled_,static_cast<std::uint32_t>(wParam)) || editingKey)
                QueueKey(static_cast<std::uint32_t>(wParam));
            else if(!textInputEnabled_) {
                std::printf("UI_WINDOW_KEY_IGNORED=%llu|%u\n",
                            static_cast<unsigned long long>(sceneGeneration_),static_cast<unsigned>(wParam));
                std::fflush(stdout);
            }
        }
        return 0;
    }
    case WM_CHAR:
    case WM_IME_CHAR:
        // Consume the IME result here instead of passing WM_IME_CHAR back to
        // DefWindowProc, which could translate it into another character path.
        if(textInputEnabled_ && (!editorOwner_ || nativeTextFocused_) && IsTextInputMessageCurrent()){
            if(wParam<=0xffff)QueueUtf16Character(static_cast<std::uint32_t>(wParam));
            else pendingHighSurrogate_=0;
        }
        return 0;
    case WM_UNICHAR:
        if(wParam==UNICODE_NOCHAR)return TRUE;
        if(textInputEnabled_ && (!editorOwner_ || nativeTextFocused_) && IsTextInputMessageCurrent()){
            pendingHighSurrogate_=0;
            if(wParam<=0x10ffff)QueueTextScalar(static_cast<std::uint32_t>(wParam));
        }
        return 0;
    case WM_IME_STARTCOMPOSITION:
        if(textInputEnabled_ && (!editorOwner_ || nativeTextFocused_) && IsTextInputMessageCurrent()){
            pendingHighSurrogate_=0;imeCompositionActive_=true;
        }
        return DefWindowProcW(hwnd_,message,wParam,lParam);
    case WM_IME_ENDCOMPOSITION:
        pendingHighSurrogate_=0;imeCompositionActive_=false;
        return DefWindowProcW(hwnd_,message,wParam,lParam);
    case WM_LBUTTONDOWN:
    case WM_RBUTTONDOWN: {
        if (!IsInputMessageCurrent()) return 0;
        PointerPress& press=message==WM_LBUTTONDOWN?leftPress_:rightPress_;
        if (press.active) return 0; // Ignore duplicate downs until a real cancellation/up.
        RECT client{}; float logicalX=0,logicalY=0; bool uiHit=false; std::uint64_t downKey=0;
        if (GetClientRect(hwnd_,&client) &&
            MapClientPointToLogical(static_cast<std::uint32_t>(client.right),
                                    static_cast<std::uint32_t>(client.bottom),
                                    GET_X_LPARAM(lParam),GET_Y_LPARAM(lParam),&logicalX,&logicalY))
            downKey=HitTestLogicalPoint(logicalX,logicalY,&uiHit);
        if (!downKey) return 0; // Letterbox/empty space cannot seed a later world action.
        if(!BeginBitmapPointerPress(press,pointerPressSequence_,uiHit,sceneGeneration_,downKey,logicalX,logicalY)){
            queueOverflow_=true;return 0;
        }
        SetCapture(hwnd_);
        if (GetCapture()!=hwnd_) press={};
        else if(message==WM_LBUTTONDOWN)QueueControlDrag(GET_X_LPARAM(lParam),GET_Y_LPARAM(lParam));
        return 0;
    }
    case WM_LBUTTONUP:
    case WM_RBUTTONUP: {
        PointerPress& press=message==WM_LBUTTONUP?leftPress_:rightPress_;
        if (!press.active) return 0; // Unmatched or duplicate up.
        const PointerPress started=press;
        press={};
        if (IsInputMessageCurrent() && started.generation==sceneGeneration_) {
            BitmapInputKind kind=BitmapInputKind::ControlClick;
            std::uint32_t modifiers=0;
            if (wParam&MK_SHIFT) modifiers|=1u;
            if (wParam&MK_CONTROL) modifiers|=2u;
            if (GetKeyState(VK_MENU)&0x8000) modifiers|=4u;
            if (message==WM_RBUTTONUP) kind=BitmapInputKind::ControlRightClick;
            QueueClick(kind,GET_X_LPARAM(lParam),GET_Y_LPARAM(lParam),
                       started.generation,started.uiHit,modifiers,&started);
        }
        if (!leftPress_.active && !rightPress_.active && GetCapture()==hwnd_) ReleaseCapture();
        return 0;
    }
    case WM_CAPTURECHANGED:
        CancelPointerPresses();
        return 0;
    case WM_KILLFOCUS:
        nativeTextFocused_=false;CancelPointerPresses();InvalidateTextFocus(true,editorOwner_!=0);
        return 0;
    case WM_CANCELMODE:
        CancelPointerPresses();InvalidateTextFocus(true,editorOwner_!=0);
        nativeTextFocused_=GetFocus()==hwnd_;return 0;
    case WM_SETFOCUS:
        if(!nativeTextFocused_)InvalidateTextFocus(true,editorOwner_!=0);
        nativeTextFocused_=true;return 0;
    case WM_MOUSEMOVE:
        if (productionPointerInputEnabled_ && IsInputMessageCurrent()) {
            if (automaticLeaveTracking_ && !trackingMouseLeave_) {
                TRACKMOUSEEVENT track{};track.cbSize=sizeof(track);track.dwFlags=TME_LEAVE;track.hwndTrack=hwnd_;
                trackingMouseLeave_=TrackMouseEvent(&track)!=FALSE;
            }
            if(HasControlDragCapture() && (wParam&MK_LBUTTON))QueueControlDrag(GET_X_LPARAM(lParam),GET_Y_LPARAM(lParam));
            else QueuePointerMove(GET_X_LPARAM(lParam),GET_Y_LPARAM(lParam));
        }
        return 0;
    case WM_MOUSELEAVE:
        trackingMouseLeave_=false;
        if (productionPointerInputEnabled_ && IsInputMessageCurrent()) QueuePointerMove(-1,-1);
        return 0;
    case WM_MOUSEWHEEL:
        if (productionPointerInputEnabled_ && IsInputMessageCurrent()) {
            POINT point{GET_X_LPARAM(lParam),GET_Y_LPARAM(lParam)};
            if (ScreenToClient(hwnd_,&point))
                QueueScroll(point.x,point.y,static_cast<std::int16_t>(HIWORD(wParam)));
        }
        return 0;
    case WM_CLOSE:
        textInputEnabled_=false;nativeTextFocused_=false;editorOwner_=0;InvalidateTextFocus(true,false);
        CancelPointerPresses(); QueueClose(); if(!gameplayInputEnabled_)DestroyWindow(hwnd_); return 0;
    case WM_DESTROY:
        textInputEnabled_=false;nativeTextFocused_=false;editorOwner_=0;InvalidateTextFocus(true,false);
        CancelPointerPresses(); closing_=true; ReleaseRenderTarget();
        impl_->staging.Reset(); impl_->swapChain.Reset(); return 0;
    default: return DefWindowProcW(hwnd_,message,wParam,lParam);
    }
}

} // namespace ZeroSisPresentation
