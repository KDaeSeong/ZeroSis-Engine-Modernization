#include "../Source/Presentation/BitmapRenderer.h"
#include "../Source/Presentation/BitmapWindow.h"
#include "../Source/Presentation/BitmapEditorInput.h"

#include <Windows.h>
#include <d3d11.h>
#include <werapi.h>
#include <wincodec.h>
#include <wrl/client.h>

#include <atomic>
#include <cmath>
#include <cstdio>
#include <cwchar>
#include <cstring>
#include <string>
#include <thread>
#include <utility>
#include <vector>

using namespace ZeroSisPresentation;

namespace ZeroSisPresentation {
// Exercise the actual native re-entry branch deterministically, without
// depending on a graphics driver's timing or sending input to other windows.
struct BitmapWindowReentryTestAccess {
    static void CloseDuringDispatch(BitmapWindow& window) {
        window.inWindowProc_=true;
        SendMessageW(window.NativeHandle(),WM_CLOSE,0,0);
        window.inWindowProc_=false;
    }
    static void CharacterDuringDispatch(BitmapWindow& window,std::uint32_t codeUnit) {
        window.inWindowProc_=true;
        SendMessageW(window.NativeHandle(),WM_IME_CHAR,codeUnit,1);
        window.inWindowProc_=false;
    }
    static void RawTextPayload(BitmapWindow& window,UINT message,WPARAM value) {
        // Win32 may narrow a posted WM_CHAR payload before delivery. Exercise
        // the real handler's oversized-payload guard before that marshaling.
        BitmapWindow::WindowProc(window.NativeHandle(),message,value,1);
    }
};
}

namespace {
int checks=0;
int pixelChecks=0;
bool Expect(bool condition,const char* name) {
    ++checks;
    if (!condition) std::fprintf(stderr,"FAIL %s\n",name);
    return condition;
}
bool Near(float a,float b,float epsilon=0.05f) { return std::fabs(a-b)<=epsilon; }
void PrintError(const std::wstring& value) {
    const int size=WideCharToMultiByte(CP_UTF8,0,value.c_str(),-1,nullptr,0,nullptr,nullptr);
    if (size<=1) return;
    std::string text(static_cast<std::size_t>(size),'\0');
    WideCharToMultiByte(CP_UTF8,0,value.c_str(),-1,&text[0],size,nullptr,nullptr);
    std::fprintf(stderr,"%s\n",text.c_str());
}
bool ReadFrame(const std::wstring& path,UINT width,UINT height,std::vector<BYTE>* pixels) {
    using Microsoft::WRL::ComPtr;
    ComPtr<IWICImagingFactory> factory;
    ComPtr<IWICBitmapDecoder> decoder;
    ComPtr<IWICBitmapFrameDecode> frame;
    ComPtr<IWICFormatConverter> converter;
    HRESULT hr=CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&factory));
    if(SUCCEEDED(hr))hr=factory->CreateDecoderFromFilename(path.c_str(),nullptr,GENERIC_READ,WICDecodeMetadataCacheOnLoad,&decoder);
    if(SUCCEEDED(hr))hr=decoder->GetFrame(0,&frame);
    UINT actualWidth=0,actualHeight=0;
    if(SUCCEEDED(hr))hr=frame->GetSize(&actualWidth,&actualHeight);
    if(FAILED(hr) || actualWidth!=width || actualHeight!=height)return false;
    if(SUCCEEDED(hr))hr=factory->CreateFormatConverter(&converter);
    if(SUCCEEDED(hr))hr=converter->Initialize(frame.Get(),GUID_WICPixelFormat32bppRGBA,WICBitmapDitherTypeNone,
                                              nullptr,0.0,WICBitmapPaletteTypeCustom);
    if(FAILED(hr))return false;
    pixels->resize(static_cast<std::size_t>(width)*height*4);
    return SUCCEEDED(converter->CopyPixels(nullptr,width*4,static_cast<UINT>(pixels->size()),pixels->data()));
}
bool WriteTexturePng(const std::wstring& path) {
    using Microsoft::WRL::ComPtr;
    HRESULT apartment=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    const bool uninitialize=SUCCEEDED(apartment);
    if(FAILED(apartment) && apartment!=RPC_E_CHANGED_MODE)return false;
    constexpr UINT width=8,height=8,stride=width*4,bytes=stride*height;
    std::vector<BYTE> rgba(bytes);
    for(UINT y=0;y<height;++y)for(UINT x=0;x<width;++x){
        BYTE* pixel=rgba.data()+static_cast<std::size_t>(y*stride+x*4);
        if(y<4 && x<4){pixel[0]=255;pixel[1]=0;pixel[2]=0;pixel[3]=255;}
        else if(y<4){pixel[0]=0;pixel[1]=255;pixel[2]=0;pixel[3]=255;}
        else if(x<4){pixel[0]=0;pixel[1]=0;pixel[2]=255;pixel[3]=128;}
        else {pixel[0]=255;pixel[1]=255;pixel[2]=0;pixel[3]=255;}
    }
    ComPtr<IWICImagingFactory> wic;ComPtr<IWICBitmap> source;ComPtr<IWICFormatConverter> converter;
    ComPtr<IWICStream> stream;ComPtr<IWICBitmapEncoder> encoder;ComPtr<IWICBitmapFrameEncode> frame;
    HRESULT hr=CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&wic));
    if(SUCCEEDED(hr))hr=wic->CreateBitmapFromMemory(width,height,GUID_WICPixelFormat32bppRGBA,stride,bytes,rgba.data(),&source);
    if(SUCCEEDED(hr))hr=wic->CreateFormatConverter(&converter);
    if(SUCCEEDED(hr))hr=converter->Initialize(source.Get(),GUID_WICPixelFormat32bppBGRA,WICBitmapDitherTypeNone,
                                               nullptr,0.0,WICBitmapPaletteTypeCustom);
    if(SUCCEEDED(hr))hr=wic->CreateStream(&stream);
    if(SUCCEEDED(hr))hr=stream->InitializeFromFilename(path.c_str(),GENERIC_WRITE);
    if(SUCCEEDED(hr))hr=wic->CreateEncoder(GUID_ContainerFormatPng,nullptr,&encoder);
    if(SUCCEEDED(hr))hr=encoder->Initialize(stream.Get(),WICBitmapEncoderNoCache);
    if(SUCCEEDED(hr))hr=encoder->CreateNewFrame(&frame,nullptr);
    if(SUCCEEDED(hr))hr=frame->Initialize(nullptr);
    if(SUCCEEDED(hr))hr=frame->SetSize(width,height);
    WICPixelFormatGUID format=GUID_WICPixelFormat32bppBGRA;
    if(SUCCEEDED(hr))hr=frame->SetPixelFormat(&format);
    if(SUCCEEDED(hr) && !IsEqualGUID(format,GUID_WICPixelFormat32bppBGRA))hr=WINCODEC_ERR_UNSUPPORTEDPIXELFORMAT;
    if(SUCCEEDED(hr))hr=frame->WriteSource(converter.Get(),nullptr);
    if(SUCCEEDED(hr))hr=frame->Commit();
    if(SUCCEEDED(hr))hr=encoder->Commit();
    if(uninitialize)CoUninitialize();
    return SUCCEEDED(hr);
}
bool CompareGpuCapture(const std::wstring& reference,const std::wstring& capture,
                       UINT width,UINT height,int tolerance=4) {
    std::vector<BYTE> expected,actual;
    if(!ReadFrame(reference,width,height,&expected)||!ReadFrame(capture,width,height,&actual))return false;
    for(std::size_t i=0;i<expected.size();i+=4){
        for(int channel=0;channel<3;++channel){
            const int composited=(static_cast<int>(expected[i+channel])*expected[i+3]+127)/255;
            if(std::abs(static_cast<int>(actual[i+channel])-composited)>tolerance)return false;
        }
        if(actual[i+3]!=255)return false;
    }
    return true;
}
bool ClosePixel(const std::vector<BYTE>& pixels,UINT width,UINT x,UINT y,int r,int g,int b,int tolerance=3) {
    const std::size_t i=(static_cast<std::size_t>(y)*width+x)*4;
    return std::abs(static_cast<int>(pixels[i])-r)<=tolerance &&
           std::abs(static_cast<int>(pixels[i+1])-g)<=tolerance &&
           std::abs(static_cast<int>(pixels[i+2])-b)<=tolerance && pixels[i+3]==255;
}
bool Pixel(const std::vector<BYTE>& pixels,UINT width,UINT x,UINT y,BYTE red,BYTE green,BYTE blue) {
    const std::size_t i=(static_cast<std::size_t>(y)*width+x)*4;
    return pixels[i]==red && pixels[i+1]==green && pixels[i+2]==blue && pixels[i+3]==255;
}
bool PixelExpect(bool condition,const char* name) {
    ++pixelChecks;
    if (!condition) std::fprintf(stderr,"FAIL pixel picking: %s\n",name);
    return condition;
}

bool ClickLogical(BitmapWindow& window,float logicalX,float logicalY,std::uint64_t expected,
                  const char* name,std::uint64_t expectedGeneration=0,
                  BitmapInputKind kind=BitmapInputKind::ControlClick,bool rightButton=false,
                  std::uint32_t modifiers=0) {
    RECT client{};
    if(!GetClientRect(window.NativeHandle(),&client))return PixelExpect(false,name);
    const BitmapDisplayRect display=BitmapWindow::ComputeDisplayRect(
        static_cast<std::uint32_t>(client.right),static_cast<std::uint32_t>(client.bottom));
    const int x=static_cast<int>(std::ceil(display.left+logicalX*(display.right-display.left)/1920.0f));
    const int y=static_cast<int>(std::ceil(display.top+logicalY*(display.bottom-display.top)/1080.0f));
    const LPARAM point=MAKELPARAM(x,y);
    std::wstring error;
    std::vector<BitmapInputEvent> events;
    const UINT down=rightButton?WM_RBUTTONDOWN:WM_LBUTTONDOWN;
    const UINT up=rightButton?WM_RBUTTONUP:WM_LBUTTONUP;
    const WPARAM button=rightButton?MK_RBUTTON:MK_LBUTTON;
    const WPARAM modKeys=((modifiers&1u)?MK_SHIFT:0)|((modifiers&2u)?MK_CONTROL:0);
    if(!PostMessageW(window.NativeHandle(),down,button,point) ||
       !window.PumpMessages(&error) || !window.DrainInputs(&events,&error) || !events.empty())
        return PixelExpect(false,"mouse down does not issue a gameplay click");
    if(!PostMessageW(window.NativeHandle(),up,modKeys,point) ||
       !window.PumpMessages(&error) || !window.DrainInputs(&events,&error))return PixelExpect(false,name);
    if(expected==0)return PixelExpect(events.empty(),name);
    return PixelExpect(events.size()==1 && events[0].kind==kind &&
                  events[0].controlKey==expected &&
                  events[0].modifiers==modifiers &&
                  (!expectedGeneration || events[0].sceneGeneration==expectedGeneration),name);
}

bool RunPixelHitTests(BitmapWindow& window,const std::wstring& png) {
    constexpr std::uint32_t width=1920,height=1080;
    Scene scene{};scene.width=width;scene.height=height;
    scene.hits.push_back({77,{30,30,60,60}});
    scene.hits.push_back({88,{35,35,55,55}});
    scene.pixelHits.indices.resize(static_cast<std::size_t>(width)*height);
    scene.pixelHits.keys={111,222};
    scene.pixelHits.indices[40u*width+40u]=1;
    scene.pixelHits.indices[401u*width+301u]=2;
    std::wstring error;
    if(!PixelExpect(window.UpdateSceneRetainingInput(scene,png,&error),
               "commit UI rectangles and a world pixel map to the existing window"))return false;
    if(!ClickLogical(window,40.0f,40.0f,88,"overlapping UI rectangles keep reverse-order priority over pixel picking"))return false;
    if(!ClickLogical(window,40.0f,40.0f,88,"left release preserves Shift and Control modifiers",0,
                     BitmapInputKind::ControlClick,false,3))return false;
    if(!ClickLogical(window,300.0f,400.0f,222,"non-rectangular world pixel resolves through floor coordinates"))return false;
    if(!ClickLogical(window,40.0f,40.0f,88,"native right release keeps UI rectangle priority and modifiers",0,
                     BitmapInputKind::ControlRightClick,true,3))return false;
    if(!ClickLogical(window,300.0f,400.0f,222,"native right release resolves a world pixel hit",0,
                     BitmapInputKind::ControlRightClick,true,0))return false;
    if(!ClickLogical(window,304.0f,400.0f,0,"zero pixel index is unselectable beside a shaped hit"))return false;

    RECT client{}; GetClientRect(window.NativeHandle(),&client);
    const BitmapDisplayRect display=BitmapWindow::ComputeDisplayRect(
        static_cast<std::uint32_t>(client.right),static_cast<std::uint32_t>(client.bottom));
    const auto point=[&](float lx,float ly){return MAKELPARAM(
        static_cast<int>(std::ceil(display.left+lx*(display.right-display.left)/1920.0f)),
        static_cast<int>(std::ceil(display.top+ly*(display.bottom-display.top)/1080.0f)));};
    std::vector<BitmapInputEvent> domainEvents;
    PostMessageW(window.NativeHandle(),WM_RBUTTONDOWN,MK_RBUTTON,point(40,40));
    PostMessageW(window.NativeHandle(),WM_RBUTTONUP,0,point(300,400));
    PostMessageW(window.NativeHandle(),WM_LBUTTONDOWN,MK_LBUTTON,point(300,400));
    PostMessageW(window.NativeHandle(),WM_LBUTTONUP,0,point(40,40));
    PostMessageW(window.NativeHandle(),WM_RBUTTONDOWN,MK_RBUTTON,point(10,10));
    PostMessageW(window.NativeHandle(),WM_RBUTTONUP,0,point(300,400));
    if(!PixelExpect(window.PumpMessages(&error) && window.DrainInputs(&domainEvents,&error) && domainEvents.empty(),
                    "UI/world drags and letterbox-to-world releases cannot create actions"))return false;

    PostMessageW(window.NativeHandle(),WM_RBUTTONDOWN,MK_RBUTTON,point(40,40));
    PostMessageW(window.NativeHandle(),WM_RBUTTONUP,0,point(32,32));
    const bool rightReleasePumped=window.PumpMessages(&error) && window.DrainInputs(&domainEvents,&error);
    const bool rightReleaseValid=rightReleasePumped && domainEvents.size()==1 &&
        domainEvents[0].kind==BitmapInputKind::ControlRightClick && domainEvents[0].controlKey==77 &&
        Near(domainEvents[0].logicalX,32,1.0f)&&Near(domainEvents[0].logicalY,32,1.5f);
    if(!rightReleaseValid) {
        std::fprintf(stderr,"RIGHT_RELEASE_DIAG|pumped=%d|count=%zu|error=%ls\n",rightReleasePumped?1:0,domainEvents.size(),error.c_str());
        for(const BitmapInputEvent& event:domainEvents)
            std::fprintf(stderr,"RIGHT_RELEASE_EVENT|kind=%u|key=%llu|x=%.3f|y=%.3f|gen=%llu|mods=%u\n",
                static_cast<unsigned>(event.kind),static_cast<unsigned long long>(event.controlKey),event.logicalX,event.logicalY,
                static_cast<unsigned long long>(event.sceneGeneration),event.modifiers);
    }
    if(!PixelExpect(rightReleaseValid,"right release coordinate resolves the final overlapping UI target"))return false;

    PostMessageW(window.NativeHandle(),WM_RBUTTONDOWN,MK_RBUTTON,point(40,40));
    PostMessageW(window.NativeHandle(),WM_CANCELMODE,0,0);
    PostMessageW(window.NativeHandle(),WM_RBUTTONUP,0,point(40,40));
    if(!PixelExpect(window.PumpMessages(&error) && window.DrainInputs(&domainEvents,&error) && domainEvents.empty(),
                    "capture cancellation invalidates the pending native right press"))return false;

    const std::uint64_t generation=window.SceneGeneration();
    const auto reject=[&](Scene invalid,const char* name){
        error.clear();
        return PixelExpect(!window.UpdateScene(invalid,png,&error) && window.SceneGeneration()==generation,name);
    };
    Scene invalid=scene;invalid.pixelHits.indices.pop_back();
    if(!reject(std::move(invalid),"pixel table rejects dimensions other than empty or width times height"))return false;
    invalid=scene;invalid.pixelHits.indices[40u*width+40u]=3;
    if(!reject(std::move(invalid),"pixel table rejects indices outside its key table"))return false;
    invalid=scene;invalid.pixelHits.keys[1]=invalid.pixelHits.keys[0];
    if(!reject(std::move(invalid),"pixel table rejects duplicate keys"))return false;
    invalid=scene;invalid.pixelHits.keys[0]=0;
    if(!reject(std::move(invalid),"pixel table rejects zero keys"))return false;
    invalid=scene;invalid.pixelHits.keys.resize(500001);
    if(!reject(std::move(invalid),"pixel table rejects more than 500000 keys"))return false;

    PostMessageW(window.NativeHandle(),WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(1920,200));
    PostMessageW(window.NativeHandle(),WM_LBUTTONUP,0,MAKELPARAM(1920,200));
    PostMessageW(window.NativeHandle(),WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(400,-1));
    PostMessageW(window.NativeHandle(),WM_LBUTTONUP,0,MAKELPARAM(400,-1));
    std::vector<BitmapInputEvent> events;
    if(!PixelExpect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.empty(),
               "client coordinates outside the logical image produce no world or UI hit"))return false;
    if(!ClickLogical(window,300.0f,400.0f,222,"rejected map contracts preserve the active pixel hit map"))return false;

    Scene failedReplacement=scene;failedReplacement.pixelHits.keys[1]=333;
    error.clear();
    if(!PixelExpect(!window.UpdateScene(failedReplacement,png+L".pixel_missing",&error) &&
                    window.SceneGeneration()==generation,
               "bitmap decode failure does not commit the replacement pixel map"))return false;
    if(!ClickLogical(window,300.0f,400.0f,222,"bitmap decode failure retains the previous pixel hit map"))return false;

    Scene next=scene;next.pixelHits.keys[1]=333;
    next.pixelHits.indices[40u*width+40u]=0;
    if(!PixelExpect(window.UpdateSceneRetainingInput(next,png,&error) && window.SceneGeneration()==generation+1,
               "retaining update commits pixel map and advances generation atomically"))return false;
    if(!ClickLogical(window,300.0f,400.0f,333,"updated pixel map is active in the new generation"))return false;
    Scene empty{};empty.width=width;empty.height=height;
    if(!PixelExpect(window.UpdateScene(empty,L"",&error) && window.SceneGeneration()==generation+2,
               "empty replacement clears the prior pixel map"))return false;
    PostMessageW(window.NativeHandle(),WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(150,250));
    PostMessageW(window.NativeHandle(),WM_LBUTTONUP,0,MAKELPARAM(150,250));
    if(!PixelExpect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.empty(),
               "empty replacement leaves no stale pixel picking target"))return false;

    if(!PixelExpect(window.UpdateSceneRetainingInput(scene,png,&error),
                    "restore a UI and world scene for stale-press cancellation"))return false;
    const LPARAM uiPoint=point(40,40);
    PostMessageW(window.NativeHandle(),WM_RBUTTONDOWN,MK_RBUTTON,uiPoint);
    if(!PixelExpect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.empty(),
                    "right-button down remains pending without issuing an action"))return false;
    if(!PixelExpect(window.UpdateSceneRetainingInput(scene,png,&error),
                    "scene replacement commits while a native press is held"))return false;
    PostMessageW(window.NativeHandle(),WM_RBUTTONUP,0,uiPoint);
    PostMessageW(window.NativeHandle(),WM_RBUTTONUP,0,uiPoint);
    PostMessageW(window.NativeHandle(),WM_LBUTTONUP,0,uiPoint);
    if(!PixelExpect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.empty(),
                    "old-generation, unmatched, and duplicate releases are ignored"))return false;
    std::fprintf(stderr,"PIXEL_HIT_TESTS_PASS|%d\n",pixelChecks);
    return true;
}

bool RunGpuSceneTests(const std::wstring& prefix,bool retainArtifacts) {
    constexpr std::uint32_t width=1920,height=1080;
    const std::wstring texturePath=prefix+L"_gpu_texture.png";
    const std::wstring referencePath=prefix+L"_gpu_reference.png";
    const std::wstring legacyCapturePath=prefix+L"_gpu_legacy_capture.png";
    const std::wstring capturePath=prefix+L"_gpu_capture.png";
    const std::wstring resizedPath=prefix+L"_gpu_resized.png";
    const std::wstring afterFailurePath=prefix+L"_gpu_after_failure.png";
    const std::wstring legacyTransitionPath=prefix+L"_gpu_transition_legacy.png";
    const std::wstring gpuTransitionPath=prefix+L"_gpu_transition_gpu.png";
    std::wstring error;
    if(!Expect(WriteTexturePng(texturePath),"write a real WIC PNG texture with opaque and translucent texels"))return false;
    Scene scene{};scene.width=width;scene.height=height;scene.textures.push_back({texturePath});
    scene.hits.push_back({901,{100,100,180,180}});
    scene.pixelHits.indices.resize(static_cast<std::size_t>(width)*height);
    scene.pixelHits.keys={902};
    // A small interior ID-raster patch avoids making this test depend on the
    // final ceil/floor quantization step at 1280x720 and letterboxed 800x600.
    for(std::uint32_t y=397;y<=403;++y)for(std::uint32_t x=248;x<=252;++x)
        scene.pixelHits.indices[static_cast<std::size_t>(y)*width+x]=1;
    Sprite textured{};textured.textureIndex=0;
    const float source[4]={0,0,8,8},target[4]={100,100,500,500},clip[4]={200,150,400,450};
    const float tint[4]={0.5f,1.0f,1.0f,1.0f};
    std::memcpy(textured.sourceRect,source,sizeof(source));std::memcpy(textured.targetRect,target,sizeof(target));
    std::memcpy(textured.clipRect,clip,sizeof(clip));std::memcpy(textured.tintRGBA,tint,sizeof(tint));
    scene.sprites.push_back(textured);
    Sprite solid{};solid.textureIndex=kSolidRectangleTexture;
    const float unit[4]={0,0,1,1},overlay[4]={300,300,350,350},all[4]={0,0,1920,1080};
    const float yellow[4]={1,1,0,1};
    std::memcpy(solid.sourceRect,unit,sizeof(unit));std::memcpy(solid.targetRect,overlay,sizeof(overlay));
    std::memcpy(solid.clipRect,all,sizeof(all));std::memcpy(solid.tintRGBA,yellow,sizeof(yellow));
    scene.sprites.push_back(solid);
    if(!Expect(RenderToPng(scene,referencePath,&error),"render the same texture scene through the retained PNG reference path"))return false;
    BitmapWindow legacyReference;
    if(!Expect(legacyReference.Create(scene,referencePath,L"Hidden legacy PNG reference",1280,720,false,&error),
               "create an independent hidden window for the legacy PNG presentation reference")){PrintError(error);return false;}
    if(!Expect(legacyReference.ResizeClient(1280,720,&error),"resize legacy reference window to the bounded test client")){PrintError(error);return false;}
    RECT legacyClient{};
    if(!Expect(GetClientRect(legacyReference.NativeHandle(),&legacyClient) && legacyClient.right==1280 && legacyClient.bottom==720,
               "legacy reference capture uses its actual 1280 by 720 client dimensions"))return false;
    if(!Expect(legacyReference.CaptureFrame(legacyCapturePath,&error),"capture the legacy PNG scene at the same client size as GPU mode")){PrintError(error);return false;}
    BitmapWindow window;
    if(!Expect(window.CreateGpuScene(scene,L"Hidden retained GPU scene test",1280,720,false,&error),
               "create a hidden window from a retained GPU scene without a PNG round trip")) {PrintError(error);return false;}
    if(!Expect(window.SceneGeneration()==1 && window.EnableGameplayInput(true,&error) &&
               window.ResizeClient(1280,720,&error) && window.PumpMessages(&error),
               "GPU scene creation commits generation one, sizes the hidden client, and enables input")){PrintError(error);return false;}
    RECT gpuClient{};
    if(!Expect(GetClientRect(window.NativeHandle(),&gpuClient) && gpuClient.right==1280 && gpuClient.bottom==720,
               "GPU capture uses its actual 1280 by 720 client dimensions"))return false;
    if(!Expect(window.CaptureFrame(capturePath,&error),"capture the GPU scene output from its HWND swap chain"))return false;
    if(!Expect(CompareGpuCapture(legacyCapturePath,capturePath,1280,720),
               "GPU scene output matches the legacy PNG presentation at equal client dimensions"))return false;
    std::vector<BYTE> captured;
    if(!Expect(ReadFrame(capturePath,1280,720,&captured),"decode the GPU scene capture for semantic pixel checks"))return false;
    if(!PixelExpect(ClosePixel(captured,1280,120,133,0,0,0),"clip excludes texels outside the sprite clip rectangle"))return false;
    if(!PixelExpect(ClosePixel(captured,1280,167,133,128,0,0),"UV selection and tint preserve the top-left source quadrant"))return false;
    if(!PixelExpect(ClosePixel(captured,1280,233,133,0,255,0),"UV selection reaches the adjacent source quadrant"))return false;
    if(!PixelExpect(ClosePixel(captured,1280,167,267,0,0,128),"PNG source alpha is premultiplied and composited over black"))return false;
    if(!PixelExpect(ClosePixel(captured,1280,213,213,255,255,0),"later solid sprite is ordered above the texture sprite"))return false;
    if(!ClickLogical(window,120.0f,120.0f,901,"GPU scene UI rectangle remains clickable",1))return false;
    if(!ClickLogical(window,250.0f,400.0f,902,"GPU scene retains non-rectangular world pixel picking",1))return false;

    const std::uint64_t generation=window.SceneGeneration();
    Scene missingTexture=scene;missingTexture.textures[0].path=texturePath+L".missing";
    error.clear();
    if(!Expect(!window.UpdateGpuScene(missingTexture,&error) && window.SceneGeneration()==generation,
               "GPU texture decode failure leaves prior scene generation committed"))return false;
    if(!Expect(window.CaptureFrame(afterFailurePath,&error) &&
               CompareGpuCapture(legacyCapturePath,afterFailurePath,1280,720),
               "failed GPU replacement preserves the currently displayed texture and pixels"))return false;
    if(!ClickLogical(window,250.0f,400.0f,902,"failed GPU replacement preserves the previous picking map",generation))return false;

    if(!Expect(PostMessageW(window.NativeHandle(),WM_KEYDOWN,VK_TAB,1) && window.PumpMessages(&error),
               "queue a command before retaining a GPU replacement"))return false;
    Scene changed=scene;changed.hits[0].controlKey=911;changed.pixelHits.keys[0]=912;
    std::vector<BitmapInputEvent> retained;
    if(!Expect(window.UpdateGpuSceneRetainingInput(changed,&error) && window.SceneGeneration()==generation+1 &&
               window.DrainInputs(&retained,&error) && retained.size()==1 &&
               retained[0].kind==BitmapInputKind::KeyDown && retained[0].virtualKey==VK_TAB &&
               retained[0].sceneGeneration==generation,
               "retaining GPU update atomically commits a new scene generation"))return false;
    if(!ClickLogical(window,120.0f,120.0f,911,"new GPU UI hit map becomes active with its committed generation",generation+1))return false;
    if(!ClickLogical(window,250.0f,400.0f,912,"new GPU pixel map becomes active with its committed generation",generation+1))return false;
    std::vector<BYTE> resizedPixels;
    if(!Expect(window.ResizeClient(800,600,&error) && window.PumpMessages(&error) &&
               window.CaptureFrame(resizedPath,&error) && ReadFrame(resizedPath,800,600,&resizedPixels) &&
               Pixel(resizedPixels,800,0,0,0,0,0) && Pixel(resizedPixels,800,133,208,255,255,0),
               "resized hidden HWND redraws the retained GPU scene with a 4:3 letterbox and expected sprite pixels"))return false;
    if(!ClickLogical(window,120.0f,120.0f,911,"letterboxed resize preserves logical UI hit coordinates",generation+1))return false;

    if(!Expect(window.UpdateScene(scene,referencePath,&error) && window.SceneGeneration()==generation+2 &&
               window.CaptureFrame(legacyTransitionPath,&error),
               "legacy PNG update can replace a retained GPU scene and present a captured frame"))return false;
    if(!Expect(window.UpdateGpuScene(changed,&error) && window.SceneGeneration()==generation+3 &&
               window.CaptureFrame(gpuTransitionPath,&error) &&
               CompareGpuCapture(legacyTransitionPath,gpuTransitionPath,800,600),
               "retained GPU scene can replace a legacy PNG scene with matching presented pixels"))return false;
    if(!ClickLogical(window,250.0f,400.0f,912,"GPU picking remains aligned after a legacy-to-GPU transition",generation+3))return false;
    std::fprintf(stderr,"GPU_SCENE_TESTS_PASS|retained_target|png_reference|alpha_clip_uv_order|input_generation|resize|legacy_transition\n");
    window.PumpMessages(&error);
    if(!retainArtifacts){
        DeleteFileW(texturePath.c_str());DeleteFileW(referencePath.c_str());DeleteFileW(legacyCapturePath.c_str());
        DeleteFileW(capturePath.c_str());DeleteFileW(resizedPath.c_str());DeleteFileW(afterFailurePath.c_str());
        DeleteFileW(legacyTransitionPath.c_str());DeleteFileW(gpuTransitionPath.c_str());
    }
    return true;
}

bool PaintGreenBase(ID3D11Device* device,ID3D11DeviceContext* context,ID3D11Texture2D* target,
                    ID3D11Device** observedDevice,std::wstring* error) {
    if(!device||!context||!target||!observedDevice)return false;
    *observedDevice=device;
    Microsoft::WRL::ComPtr<ID3D11RenderTargetView> view;
    const HRESULT hr=device->CreateRenderTargetView(target,nullptr,&view);
    if(FAILED(hr)){
        if(error)*error=L"CreateRenderTargetView failed in prepared-frame fixture";
        return false;
    }
    const float green[4]={0.0f,1.0f,0.0f,1.0f};
    context->ClearRenderTargetView(view.Get(),green);
    return true;
}

bool FailGpuPaint(ID3D11Device*,ID3D11DeviceContext*,ID3D11Texture2D*,std::wstring* error) {
    if(error)*error=L"intentional prepared-frame painter failure";
    return false;
}

bool PaintSolidBase(ID3D11Device* device,ID3D11DeviceContext* context,ID3D11Texture2D* target,
                    const float color[4],std::wstring* error) {
    if(!device||!context||!target||!color)return false;
    Microsoft::WRL::ComPtr<ID3D11RenderTargetView> view;
    const HRESULT hr=device->CreateRenderTargetView(target,nullptr,&view);
    if(FAILED(hr)){
        if(error)*error=L"CreateRenderTargetView failed in prepared-refresh fixture";
        return false;
    }
    context->ClearRenderTargetView(view.Get(),color);
    return true;
}

bool RunPreparedGpuRefreshTests(const std::wstring& prefix,bool retainArtifacts) {
    constexpr std::uint32_t width=1920,height=1080;
    const std::wstring texturePath=prefix+L"_refresh_texture.png";
    const std::wstring oldFramePath=prefix+L"_refresh_old.png";
    const std::wstring failedFramePath=prefix+L"_refresh_failed.png";
    const std::wstring candidatePath=prefix+L"_refresh_candidate.png";
    const std::wstring refreshedPath=prefix+L"_refresh_new.png";
    std::wstring error;
    if(!Expect(WriteTexturePng(texturePath),"write the texture used by prepared-frame refresh geometry checks"))return false;
    Scene scene{};scene.width=width;scene.height=height;scene.textures.push_back({texturePath});
    scene.hits.push_back({901,{100,100,180,180}});
    scene.scrolls.push_back({904,{400,400,600,600}});
    scene.pixelHits.indices.resize(static_cast<std::size_t>(width)*height);
    scene.pixelHits.keys={903};
    scene.pixelHits.indices[450u*width+350u]=1;
    Sprite sprite{};sprite.textureIndex=0;
    const float source[4]={0,0,8,8},target[4]={0,0,1920,1080},clip[4]={0,0,1920,1080};
    const float tint[4]={1,1,1,1};
    std::memcpy(sprite.sourceRect,source,sizeof(source));std::memcpy(sprite.targetRect,target,sizeof(target));
    std::memcpy(sprite.clipRect,clip,sizeof(clip));std::memcpy(sprite.tintRGBA,tint,sizeof(tint));
    scene.sprites.push_back(sprite);

    BitmapWindow window;
    const float green[4]={0,1,0,1},blue[4]={0,0,1,1};
    if(!Expect(window.PrepareGpuFrame([&](ID3D11Device* d,ID3D11DeviceContext* c,ID3D11Texture2D* t,std::wstring* e){
                   return PaintSolidBase(d,c,t,green,e);
               },&error) && window.OverlayPreparedGpuFrame(scene,&error) &&
               window.CreatePreparedGpuScene(scene,L"Hidden prepared GPU refresh test",1280,720,false,&error),
               "create an open retained scene with hit, scroll, and pixel geometry")){PrintError(error);return false;}
    if(!Expect(window.EnableGameplayInput(true,&error) && window.EnableProductionPointerInput(true,&error,false),
               "enable gameplay keys and synthetic scroll input for refresh preservation checks"))return false;
    const std::uint64_t generation=window.SceneGeneration();
    if(!Expect(generation==1 && window.CaptureFrame(oldFramePath,&error),"capture the committed frame before refresh"))return false;
    std::vector<BYTE> oldFrame;
    if(!Expect(ReadFrame(oldFramePath,1280,720,&oldFrame),"decode the committed pre-refresh frame"))return false;

    if(!Expect(window.PrepareGpuFrame([&](ID3D11Device* d,ID3D11DeviceContext* c,ID3D11Texture2D* t,std::wstring* e){
                   return PaintSolidBase(d,c,t,blue,e);
               },&error) && window.OverlayPreparedGpuFrame(scene,&error) &&
               window.CapturePreparedGpuFrame(candidatePath,&error),
               "prepare and capture a visibly different candidate for the active geometry")){PrintError(error);return false;}
    std::vector<BYTE> candidate;
    if(!Expect(ReadFrame(candidatePath,width,height,&candidate) && Pixel(candidate,width,500,1000,0,0,255),
               "prepared refresh candidate preserves blue beneath same-color translucent UI"))return false;
    const std::vector<BYTE> preparedFrameBefore=candidate;

    unsigned rejectionIndex=0;std::vector<std::wstring> rejectionCaptures;
    const auto reject=[&](Scene invalid,const char* name){
        error.clear();
        if(!Expect(!window.RefreshPreparedGpuFrame(invalid,&error) && window.SceneGeneration()==generation,name))return false;
        const unsigned rejection=++rejectionIndex;
        const auto visiblePath=rejection==1?failedFramePath:prefix+L"_refresh_failed_"+std::to_wstring(rejection)+L".png";
        rejectionCaptures.push_back(visiblePath);
        std::vector<BYTE> visibleAfter;
        const bool visibleCaptured=window.CaptureFrame(visiblePath,&error);
        if(!visibleCaptured)PrintError(error);
        if(!Expect(visibleCaptured && ReadFrame(visiblePath,1280,720,&visibleAfter) &&
                   visibleAfter==oldFrame,
                   "rejected geometry preserves the previous visible frame pixel-for-pixel"))return false;
        std::vector<BYTE> preparedAfter;
        const auto afterPath=prefix+L"_refresh_candidate_after_"+std::to_wstring(rejection)+L".png";
        rejectionCaptures.push_back(afterPath);
        const bool captured=window.CapturePreparedGpuFrame(afterPath,&error);
        if(!captured)PrintError(error);
        return Expect(captured && ReadFrame(afterPath,width,height,&preparedAfter) && preparedAfter==preparedFrameBefore,
                      "rejected geometry preserves the full prepared candidate pixel-for-pixel");
    };
    Scene invalid=scene;invalid.hits[0].controlKey=911;
    if(!reject(invalid,"prepared refresh rejects a changed hit control key"))return false;
    invalid=scene;invalid.hits[0].bounds[2]+=1.0f;
    if(!reject(invalid,"prepared refresh rejects changed hit bounds"))return false;
    invalid=scene;invalid.scrolls[0].controlKey=914;
    if(!reject(invalid,"prepared refresh rejects a changed scroll control key"))return false;
    invalid=scene;invalid.scrolls[0].bounds[2]+=1.0f;
    if(!reject(invalid,"prepared refresh rejects changed scroll bounds"))return false;
    invalid=scene;invalid.pixelHits.keys[0]=913;
    if(!reject(invalid,"prepared refresh rejects changed pixel keys"))return false;
    invalid=scene;invalid.pixelHits.indices[450u*width+350u]=0;
    if(!reject(invalid,"prepared refresh rejects changed pixel indices"))return false;
    invalid=scene;invalid.width=width-1;
    if(!reject(invalid,"prepared refresh rejects changed scene dimensions"))return false;

    POINT scrollPoint{333,300};ClientToScreen(window.NativeHandle(),&scrollPoint);
    if(!Expect(PostMessageW(window.NativeHandle(),WM_KEYDOWN,VK_TAB,1) &&
               PostMessageW(window.NativeHandle(),WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(80,80)) &&
               PostMessageW(window.NativeHandle(),WM_MOUSEWHEEL,MAKEWPARAM(0,WHEEL_DELTA),MAKELPARAM(scrollPoint.x,scrollPoint.y)) &&
               window.PumpMessages(&error),"dispatch key, hit, and scroll inputs before a successful refresh"))return false;
    if(!Expect(window.RefreshPreparedGpuFrame(scene,&error) && window.SceneGeneration()==generation &&
               window.CaptureFrame(refreshedPath,&error),
               "matching prepared refresh switches the visible GPU frame without changing scene generation")){PrintError(error);return false;}
    std::vector<BYTE> refreshed;
    if(!Expect(ReadFrame(refreshedPath,1280,720,&refreshed) && refreshed!=oldFrame &&
               Pixel(refreshed,1280,333,667,0,0,255),
               "successful refresh presents the prepared candidate pixels"))return false;
    if(!Expect(PostMessageW(window.NativeHandle(),WM_LBUTTONUP,0,MAKELPARAM(80,80)) &&
               window.PumpMessages(&error),
               "release after visual-only refresh uses the preserved press generation"))return false;
    std::vector<BitmapInputEvent> events;
    if(!Expect(window.DrainInputs(&events,&error) && events.size()==3 &&
               events[0].kind==BitmapInputKind::KeyDown && events[0].virtualKey==VK_TAB &&
               events[1].kind==BitmapInputKind::Scroll && events[1].controlKey==904 &&
               events[2].kind==BitmapInputKind::ControlClick && events[2].controlKey==901 &&
               events[0].sceneGeneration==generation && events[1].sceneGeneration==generation &&
               events[2].sceneGeneration==generation,
               "visual refresh preserves the held press generation and release follows existing inputs"))return false;
    PostMessageW(window.NativeHandle(),WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(80,80));
    PostMessageW(window.NativeHandle(),WM_LBUTTONUP,0,MAKELPARAM(80,80));
    if(!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.size()==1 &&
               events[0].kind==BitmapInputKind::ControlClick && events[0].controlKey==901 &&
               events[0].sceneGeneration==generation,
               "hit testing remains usable after refresh with unchanged geometry"))return false;
    if(!Expect(!window.RefreshPreparedGpuFrame(scene,&error) && window.SceneGeneration()==generation,
               "successful refresh consumes its candidate and a second refresh without preparation is rejected"))return false;
    if(!retainArtifacts){
        DeleteFileW(texturePath.c_str());DeleteFileW(oldFramePath.c_str());DeleteFileW(failedFramePath.c_str());
        DeleteFileW(candidatePath.c_str());DeleteFileW(refreshedPath.c_str());
        for(const auto& path:rejectionCaptures)DeleteFileW(path.c_str());
    }
    std::fprintf(stderr,"PREPARED_GPU_REFRESH_TESTS_PASS|same_geometry|failure_preservation|candidate_consumption|input_generation|pixel_scroll_hits\n");
    return true;
}

bool RunPreparedGpuFrameTests(const std::wstring& prefix,bool retainArtifacts) {
    constexpr std::uint32_t width=1920,height=1080;
    const std::wstring texturePath=prefix+L"_prepared_gpu_texture.png";
    const std::wstring candidatePath=prefix+L"_prepared_gpu_candidate.png";
    const std::wstring overlaidCandidatePath=prefix+L"_prepared_gpu_overlaid_candidate.png";
    const std::wstring presentedPath=prefix+L"_prepared_gpu_presented.png";
    const std::wstring failurePath=prefix+L"_prepared_gpu_after_failure.png";
    const std::wstring overlayFailurePath=prefix+L"_prepared_gpu_after_overlay_failure.png";
    std::wstring error;
    if(!Expect(WriteTexturePng(texturePath),"write the alpha fixture for prepared GPU composition"))return false;
    Scene scene{};scene.width=width;scene.height=height;scene.textures.push_back({texturePath});
    scene.hits.push_back({901,{100,100,180,180}});
    Sprite sprite{};sprite.textureIndex=0;
    const float source[4]={0,0,8,8},target[4]={0,0,1920,1080},clip[4]={0,0,1920,1080};
    const float tint[4]={1,1,1,1};
    std::memcpy(sprite.sourceRect,source,sizeof(source));std::memcpy(sprite.targetRect,target,sizeof(target));
    std::memcpy(sprite.clipRect,clip,sizeof(clip));std::memcpy(sprite.tintRGBA,tint,sizeof(tint));
    scene.sprites.push_back(sprite);

    BitmapWindow window;
    ID3D11Device* painterDevice=nullptr;
    if(!Expect(window.PrepareGpuFrame([&](ID3D11Device* device,ID3D11DeviceContext* context,
                                         ID3D11Texture2D* frame,std::wstring* why){
                   return PaintGreenBase(device,context,frame,&painterDevice,why);
               },&error),"prepare a private GPU candidate before creating an HWND")){PrintError(error);return false;}
    if(!Expect(window.CapturePreparedGpuFrame(candidatePath,&error),
               "capture the private prepared candidate before HWND creation")){PrintError(error);return false;}
    std::vector<BYTE> candidate;
    if(!Expect(ReadFrame(candidatePath,width,height,&candidate) &&
               Pixel(candidate,width,0,0,0,255,0),
               "prepared candidate snapshot retains its full 1920 by 1080 green base"))return false;
    if(!Expect(window.OverlayPreparedGpuFrame(scene,&error),
               "alpha-compose the UI scene over the prepared candidate without clearing it")){PrintError(error);return false;}
    if(!Expect(window.CapturePreparedGpuFrame(overlaidCandidatePath,&error) &&
               ReadFrame(overlaidCandidatePath,width,height,&candidate) &&
               ClosePixel(candidate,width,100,100,255,0,0) &&
               ClosePixel(candidate,width,100,800,0,127,128),
               "prepared overlay preserves opaque and translucent source alpha over the green base"))return false;
    if(!Expect(window.CreatePreparedGpuScene(scene,L"Hidden prepared GPU scene",1280,720,false,&error),
               "commit the prepared and overlaid candidate into the same hidden HWND")){PrintError(error);return false;}
    if(!Expect(window.EnableGameplayInput(true,&error),"enable synthetic input for prepared-scene hit and generation checks"))return false;
    BitmapFrameInfo info{};
    if(!Expect(window.SceneGeneration()==1 && window.GetFrameInfo(&info,&error) &&
               info.deviceIdentity==static_cast<std::uint64_t>(reinterpret_cast<std::uintptr_t>(painterDevice)),
               "prepared painter and committed HWND share the same D3D device"))return false;
    if(!Expect(!window.UpdatePreparedGpuSceneRetainingInput(scene,&error) && window.SceneGeneration()==1,
               "prepared commit consumes its candidate so a second commit without preparation is rejected"))return false;
    if(!Expect(window.ResizeClient(1280,720,&error) && window.PumpMessages(&error) &&
               window.CaptureFrame(presentedPath,&error),
               "present the prepared candidate through the bounded 1280 by 720 client")){PrintError(error);return false;}
    std::vector<BYTE> presented;
    if(!Expect(ReadFrame(presentedPath,1280,720,&presented) &&
               ClosePixel(presented,1280,67,67,255,0,0) &&
               ClosePixel(presented,1280,67,533,0,127,128),
               "same-window capture preserves prepared-frame alpha composition"))return false;

    const std::uint64_t generation=window.SceneGeneration();
    if(!Expect(!window.PrepareGpuFrame(FailGpuPaint,&error) && window.SceneGeneration()==generation,
               "failed painter preparation does not replace the committed frame or generation"))return false;
    if(!Expect(window.CaptureFrame(failurePath,&error) &&
               ReadFrame(failurePath,1280,720,&candidate) && candidate==presented,
               "failed painter leaves the last presented pixels unchanged"))return false;
    if(!ClickLogical(window,120,120,901,"failed preparation retains the committed hit target",generation))return false;

    if(!Expect(window.PrepareGpuFrame([&](ID3D11Device* device,ID3D11DeviceContext* context,
                                          ID3D11Texture2D* frame,std::wstring* why){
                   return PaintGreenBase(device,context,frame,&painterDevice,why);
               },&error),"prepare another candidate for overlay failure atomicity"))return false;
    Scene invalid=scene;invalid.textures[0].path=texturePath+L".missing";
    if(!Expect(!window.OverlayPreparedGpuFrame(invalid,&error) && window.SceneGeneration()==generation,
               "failed overlay keeps the committed scene generation"))return false;
    if(!Expect(window.CaptureFrame(overlayFailurePath,&error) && ReadFrame(overlayFailurePath,1280,720,&candidate) &&
               candidate==presented,
               "failed overlay leaves the last presented pixels unchanged"))return false;
    if(!ClickLogical(window,120,120,901,"failed overlay retains the committed hit target",generation))return false;

    BitmapWindow noPending;
    if(!Expect(!noPending.CreatePreparedGpuScene(scene,L"No pending candidate",1280,720,false,&error) &&
               !noPending.IsOpen(),"prepared scene commit rejects a missing candidate without creating an HWND"))return false;

    if(!Expect(window.PrepareGpuFrame([&](ID3D11Device* device,ID3D11DeviceContext* context,
                                          ID3D11Texture2D* frame,std::wstring* why){
                   return PaintGreenBase(device,context,frame,&painterDevice,why);
               },&error),"prepare a candidate for the retained-input update API"))return false;
    Scene changed=scene;changed.hits[0].controlKey=902;
    if(!Expect(window.OverlayPreparedGpuFrame(changed,&error),"overlay the next retained GPU scene"))return false;
    std::vector<BitmapInputEvent> queued;
    if(!Expect(PostMessageW(window.NativeHandle(),WM_KEYDOWN,VK_TAB,1) && window.PumpMessages(&error),
               "queue an input before committing a prepared scene"))return false;
    if(!Expect(window.UpdatePreparedGpuSceneRetainingInput(changed,&error) &&
               window.SceneGeneration()==generation+1 && window.DrainInputs(&queued,&error) &&
               queued.size()==1 && queued[0].kind==BitmapInputKind::KeyDown &&
               queued[0].virtualKey==VK_TAB && queued[0].sceneGeneration==generation,
               "prepared retained update advances generation while preserving the posted input generation"))return false;
    if(!ClickLogical(window,120,120,902,"prepared retained update commits its new hit map",generation+1))return false;
    const std::wstring updatedPath=prefix+L"_prepared_gpu_after_update.png";
    if(!Expect(window.ResizeClient(800,600,&error) && window.PumpMessages(&error) &&
               window.CaptureFrame(updatedPath,&error),"resize and redraw the retained prepared GPU scene"))return false;
    std::vector<BYTE> updated;
    if(!Expect(ReadFrame(updatedPath,800,600,&updated) &&
               ClosePixel(updated,800,50,100,255,0,0) &&
               ClosePixel(updated,800,50,400,0,127,128),
               "resized prepared scene retains its alpha-composited world frame"))return false;

    std::fprintf(stderr,"PREPARED_GPU_FRAME_TESTS_PASS|prepare_before_hwnd|same_device_overlay|alpha_composition|commit_consumes|failure_atomicity|hit_generation|retained_resize|no_pending_rejected\n");
    if(!retainArtifacts){
        DeleteFileW(texturePath.c_str());DeleteFileW(candidatePath.c_str());DeleteFileW(overlaidCandidatePath.c_str());
        DeleteFileW(presentedPath.c_str());DeleteFileW(failurePath.c_str());
        DeleteFileW(overlayFailurePath.c_str());DeleteFileW(updatedPath.c_str());
    }
    return true;
}

bool RunUnicodeTextInputTests(const Scene& scene,const std::wstring& png) {
    std::wstring error;
    BitmapWindow window;
    if(!Expect(window.Create(scene,png,L"Hidden Unicode input test",800,600,false,&error) &&
               window.PumpMessages(&error),"create an isolated hidden Unicode input window"))return false;
    const HWND hwnd=window.NativeHandle();
    std::vector<BitmapInputEvent> events;
    auto drain=[&](){return window.PumpMessages(&error) && window.DrainInputs(&events,&error);};
    PostMessageW(hwnd,WM_CHAR,0x41,1);PostMessageW(hwnd,WM_IME_CHAR,0xd55c,1);
    PostMessageW(hwnd,WM_UNICHAR,0x1f600,1);PostMessageW(hwnd,WM_KEYDOWN,VK_BACK,1);
    if(!Expect(drain() && events.empty(),"text input is disabled by default without changing normal popup keys"))return false;
    std::atomic<bool> foreignEnable{true};
    std::thread foreign([&](){std::wstring failure;foreignEnable.store(window.EnableTextInput(true,&failure));});
    foreign.join();
    if(!Expect(!foreignEnable.load() && window.EnableTextInput(true,&error),
               "only the HWND owner can opt in to Unicode text input"))return false;
    if(!Expect(SendMessageW(hwnd,WM_UNICHAR,UNICODE_NOCHAR,1)==TRUE,
               "Unicode capability probe is acknowledged without adding text"))return false;
    PostMessageW(hwnd,WM_CHAR,0x41,1);
    PostMessageW(hwnd,WM_IME_CHAR,0xd55c,1);PostMessageW(hwnd,WM_IME_CHAR,0xae00,1);
    PostMessageW(hwnd,WM_CHAR,0xd83d,1);PostMessageW(hwnd,WM_CHAR,0xde00,1);
    PostMessageW(hwnd,WM_UNICHAR,0x1f680,1);
    if(!Expect(drain() && events.size()==5,"Latin, Korean committed IME text and supplementary scalars arrive exactly once"))return false;
    const std::uint32_t scalars[]={0x41,0xd55c,0xae00,0x1f600,0x1f680};
    for(std::size_t i=0;i<events.size();++i)
        if(!Expect(events[i].kind==BitmapInputKind::TextInput && events[i].unicodeScalar==scalars[i] &&
                   events[i].virtualKey==0 && events[i].controlKey==0 && events[i].sceneGeneration==1,
                   "Unicode text event preserves scalar and generation without using gameplay/control keys"))return false;

    const std::uint32_t keys[]={VK_BACK,VK_BACK,VK_DELETE,VK_LEFT,VK_RIGHT,VK_HOME,VK_END,VK_RETURN,VK_ESCAPE};
    for(std::size_t i=0;i<9;++i)
        PostMessageW(hwnd,WM_KEYDOWN,keys[i],i==1?static_cast<LPARAM>(1|(1ll<<30)):1);
    PostMessageW(hwnd,WM_CHAR,8,1);PostMessageW(hwnd,WM_CHAR,13,1);
    if(!Expect(drain() && events.size()==9,"editing keys and repeated Backspace remain keys without duplicate control characters"))return false;
    for(std::size_t i=0;i<events.size();++i)
        if(!Expect(events[i].kind==BitmapInputKind::KeyDown && events[i].virtualKey==keys[i] && events[i].unicodeScalar==0,
                   "text mode preserves each exact editing virtual key"))return false;

    PostMessageW(hwnd,WM_CHAR,0xd83d,1);PostMessageW(hwnd,WM_CHAR,0x42,1);
    PostMessageW(hwnd,WM_CHAR,0xde00,1);PostMessageW(hwnd,WM_UNICHAR,0xd800,1);
    PostMessageW(hwnd,WM_UNICHAR,0x110000,1);PostMessageW(hwnd,WM_CHAR,0x110000,1);
    PostMessageW(hwnd,WM_CHAR,0,1);PostMessageW(hwnd,WM_CHAR,9,1);PostMessageW(hwnd,WM_CHAR,0x85,1);
#if defined(_WIN64)
    BitmapWindowReentryTestAccess::RawTextPayload(window,WM_CHAR,(static_cast<WPARAM>(1)<<32)|0x41);
    BitmapWindowReentryTestAccess::RawTextPayload(window,WM_UNICHAR,(static_cast<WPARAM>(1)<<32)|0x41);
#endif
    const bool malformedDrained=drain();
    if(!malformedDrained || events.size()!=1 || events[0].unicodeScalar!=0x42)
        for(const auto& event:events)
            std::fprintf(stderr,"TEXT_REJECTION_EVENT|kind=%u|scalar=%u|key=%u\n",
                static_cast<unsigned>(event.kind),event.unicodeScalar,event.virtualKey);
    if(!Expect(malformedDrained && events.size()==1 && events[0].unicodeScalar==0x42,
               "malformed UTF-16, control characters and oversized handler payloads cannot become text"))return false;
    PostMessageW(hwnd,WM_CHAR,0xd83d,1);
    if(!Expect(drain() && events.empty(),"unpaired UTF-16 prefix never escapes as text"))return false;
    SendMessageW(hwnd,WM_KILLFOCUS,0,0);PostMessageW(hwnd,WM_CHAR,0xde00,1);
    if(!Expect(drain() && events.empty(),"focus loss clears an unfinished surrogate pair"))return false;
    PostMessageW(hwnd,WM_CHAR,0xd83d,1);
    if(!Expect(drain() && events.empty() && window.EnableTextInput(false,&error) && window.EnableTextInput(true,&error),
               "text mode can close and reopen without retaining a UTF-16 prefix"))return false;
    PostMessageW(hwnd,WM_CHAR,0xde00,1);
    if(!Expect(drain() && events.empty(),"new text-owning context cannot finish the old context's surrogate"))return false;

    PostMessageW(hwnd,WM_CHAR,0xd83d,1);
    if(!Expect(drain() && events.empty() && window.UpdateScene(scene,png,&error),
               "committing replacement geometry clears an uncommitted UTF-16 prefix"))return false;
    PostMessageW(hwnd,WM_CHAR,0xde00,1);PostMessageW(hwnd,WM_CHAR,0x5a,1);
    if(!Expect(drain() && events.size()==1 && events[0].unicodeScalar==0x5a &&
               events[0].sceneGeneration==2,"new-generation text cannot join old-generation surrogate input"))return false;
    PostMessageW(hwnd,WM_CHAR,0x58,1);PostMessageW(hwnd,WM_CHAR,0xd83d,1);
    if(!Expect(window.PumpMessages(&error) && window.UpdateSceneRetainingInput(scene,png,&error) &&
               window.DrainInputs(&events,&error) && events.size()==1 && events[0].unicodeScalar==0x58 &&
               events[0].sceneGeneration==2 && window.SceneGeneration()==3,
               "retaining commit preserves completed text with its original generation"))return false;
    PostMessageW(hwnd,WM_CHAR,0xde00,1);
    if(!Expect(drain() && events.empty(),"retaining commit also clears unfinished UTF-16 input"))return false;

    BitmapWindowReentryTestAccess::CharacterDuringDispatch(window,0xac00);
    if(!Expect(window.DrainInputs(&events,&error) && events.size()==1 && events[0].unicodeScalar==0xac00 &&
               events[0].sceneGeneration==3,"synchronous default-IME character reentry is retained exactly once"))return false;
    SendMessageW(hwnd,WM_IME_STARTCOMPOSITION,0,0);
    PostMessageW(hwnd,WM_KEYDOWN,VK_RETURN,1);PostMessageW(hwnd,WM_KEYDOWN,VK_BACK,1);
    if(!Expect(drain() && events.empty(),"IME composition owns Return and Backspace instead of invoking a save or deleting committed text"))return false;
    SendMessageW(hwnd,WM_IME_ENDCOMPOSITION,0,0);PostMessageW(hwnd,WM_KEYDOWN,VK_BACK,1);
    if(!Expect(drain() && events.size()==1 && events[0].virtualKey==VK_BACK,
               "editing resumes when the native IME composition ends"))return false;
    if(!Expect(window.EnableTextInput(false,&error),"text-owning UI can disable its native text channel"))return false;
    PostMessageW(hwnd,WM_CHAR,0xd55c,1);PostMessageW(hwnd,WM_KEYDOWN,VK_BACK,1);
    if(!Expect(drain() && events.empty(),"disabled text and edit keys cannot leak into gameplay"))return false;
    PostMessageW(hwnd,WM_CLOSE,0,0);
    if(!Expect(drain() && events.size()==1 && events[0].kind==BitmapInputKind::CloseRequest &&
               !window.EnableTextInput(true,&error),"closed HWND rejects re-enabling text input"))return false;
    std::fprintf(stderr,"UNICODE_TEXT_INPUT_TESTS_PASS|explicit_opt_in|korean_committed_scalars|surrogate_validation|edit_keys|focus_lifetime|scene_generation|ime_reentry|composition_key_ownership\n");
    return true;
}

bool RunEditorRefreshInputTests() {
    std::wstring error;BitmapWindow window;
    Scene scene{};scene.width=1920;scene.height=1080;
    scene.hits.push_back({33,{100,100,300,150}});
    if(!Expect(window.CreateGpuScene(scene,L"Hidden same-editor refresh test",800,600,false,&error) &&
               window.EnableGameplayInput(true,&error) && window.EnableTextInput(true,&error,1001),
               "create a bounded original-editor input owner on one hidden GPU HWND"))return false;
    SetFocus(window.NativeHandle());
    if(!Expect(GetFocus()==window.NativeHandle(),"the editor test owns genuine native HWND focus"))return false;
    BitmapTextInputState initial{};
    if(!Expect(window.GetTextInputState(&initial,&error) && initial.enabled && initial.editorOwner==1001 && initial.focusEpoch,
               "native state exposes exact editor owner and native focus lifetime"))return false;
    std::atomic<bool> foreignState{true};
    std::thread foreign([&](){BitmapTextInputState state;std::wstring why;foreignState.store(window.GetTextInputState(&state,&why));});foreign.join();
    if(!Expect(!foreignState.load(),"foreign thread cannot inspect owned text focus state"))return false;
    Sleep(2); // Coordinated producer barrier after the explicit editor transition.
    const HWND hwnd=window.NativeHandle();BitmapEditorInputBuffer deferred;
    deferred.Bind(initial.editorOwner,initial.focusEpoch);
    bool closed=false;unsigned pointers=0;std::vector<BitmapInputEvent> rejected,events;
    const auto capture=[&](){return window.PumpMessages(&error) &&
        DrainBitmapPreparationInputs(window,closed,rejected,pointers,&error,window.SceneGeneration(),&deferred);};
    PostMessageW(hwnd,WM_CHAR,0x41,1);PostMessageW(hwnd,WM_IME_CHAR,0xd55c,1);PostMessageW(hwnd,WM_IME_CHAR,0xae00,1);
    if(!Expect(capture() && rejected.empty() && deferred.Size()==3,
               "real rapid Latin and Korean messages survive the production packet-wait drain"))return false;
    const auto prepare=[&](){return window.PrepareGpuFrame([](ID3D11Device* device,ID3D11DeviceContext* context,
                                                            ID3D11Texture2D* target,std::wstring*){
        Microsoft::WRL::ComPtr<ID3D11RenderTargetView> view;
        if(FAILED(device->CreateRenderTargetView(target,nullptr,&view)))return false;
        const float color[]={0.1f,0.2f,0.3f,1.0f};context->ClearRenderTargetView(view.Get(),color);return true;
    },&error);};
    if(!Expect(prepare(),"prepare a private GPU refresh while the NameBox owner is retained"))return false;
    PostMessageW(hwnd,WM_CHAR,0x42,1);PostMessageW(hwnd,WM_CHAR,0xd83d,1);
    if(!Expect(window.UpdatePreparedGpuSceneRetainingInput(scene,&error,initial.editorOwner,initial.focusEpoch) &&
               DrainBitmapPreparationInputs(window,closed,rejected,pointers,&error,1,&deferred) &&
               window.SceneGeneration()==2 && rejected.empty() && deferred.Size()==4,
               "same-editor scene commit retains old-generation text and an unfinished UTF-16 prefix"))return false;
    PostMessageW(hwnd,WM_CHAR,0xde00,1);
    const std::uint32_t keys[]={VK_BACK,VK_BACK,VK_BACK,VK_LEFT,VK_DELETE,VK_HOME,VK_END};
    for(const auto key:keys)PostMessageW(hwnd,WM_KEYDOWN,key,static_cast<LPARAM>(1|(1ll<<30)));
    if(!Expect(capture() && rejected.empty() && deferred.Size()==12,
               "surrogate completion and repeated edit keys survive the next preparation drain"))return false;
    deferred.Drain(initial.editorOwner,initial.focusEpoch,events);
    if(!Expect(events.size()==12 && events[0].unicodeScalar==0x41 && events[1].unicodeScalar==0xd55c &&
               events[2].unicodeScalar==0xae00 && events[3].unicodeScalar==0x42 && events[4].unicodeScalar==0x1f600 &&
               events[0].sceneGeneration==1 && events[3].sceneGeneration==1 && events[4].sceneGeneration==2,
               "rapid refresh replay preserves every exact Unicode scalar, order and original geometry generation"))return false;
    bool editsValid=true;
    for(std::size_t i=0;i<7;++i)editsValid=editsValid && events[5+i].virtualKey==keys[i];
    for(const auto& event:events)editsValid=editsValid &&
        BitmapEditorInputBuffer::Matches(event,initial.editorOwner,initial.focusEpoch) &&
        !BitmapEditorInputBuffer::IsTerminalAction(event,true);
    if(!Expect(editsValid,"the actual host action policy consumes all same-batch Backspace/Delete/caret edits"))return false;
    const auto retainedExample=events.front();
    deferred.Bind(initial.editorOwner,initial.focusEpoch);
    PostMessageW(hwnd,WM_KEYDOWN,VK_RETURN,1);PostMessageW(hwnd,WM_KEYDOWN,VK_ESCAPE,1);
    PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(84,127));PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(84,127));
    if(!Expect(capture() && deferred.Size()==0 && rejected.size()==3 &&
               rejected[0].virtualKey==VK_RETURN && rejected[1].virtualKey==VK_ESCAPE &&
               rejected[2].kind==BitmapInputKind::ControlClick,
               "terminal keys and geometry clicks remain rejected during UI preparation"))return false;
    if(!Expect(BitmapEditorInputBuffer::IsTerminalAction(rejected[0],false) &&
               BitmapEditorInputBuffer::IsTerminalAction(rejected[1],false) &&
               BitmapEditorInputBuffer::IsTerminalAction(rejected[2],false),
               "Return Escape and Save-style clicks retain the host terminal-action barrier"))return false;
    if(!Expect(prepare() && !window.UpdatePreparedGpuSceneRetainingInput(scene,&error,1002,initial.focusEpoch) &&
               window.SceneGeneration()==2,"a different child owner cannot claim the prepared editor refresh"))return false;
    if(!Expect(!window.UpdatePreparedGpuSceneRetainingInput(scene,&error,1001,initial.focusEpoch+1) &&
               window.SceneGeneration()==2,"an old or invented native focus epoch cannot claim a prepared editor refresh"))return false;
    if(!Expect(window.UpdatePreparedGpuSceneRetainingInput(scene,&error,1001,initial.focusEpoch),
               "rejected editor refresh leaves its private GPU candidate usable by the true owner"))return false;
    PostMessageW(hwnd,WM_CHAR,0x43,1);
    if(!Expect(capture() && deferred.Size()==1,"retain a completed letter before losing native focus"))return false;
    PostMessageW(hwnd,WM_CHAR,0xd83d,1);if(!window.PumpMessages(&error))return false;
    SetFocus(nullptr);BitmapTextInputState unfocused{};
    if(!Expect(GetFocus()!=hwnd && window.GetTextInputState(&unfocused,&error) && !unfocused.enabled && unfocused.focusEpoch!=initial.focusEpoch &&
               unfocused.editorOwner==initial.editorOwner,"native focus loss advances its epoch without changing the logical editor owner"))return false;
    deferred.Drain(unfocused.editorOwner,unfocused.focusEpoch,events);
    if(!Expect(events.empty() && deferred.Size()==0,"queued same-child text is discarded after native focus loss"))return false;
    Sleep(2);PostMessageW(hwnd,WM_CHAR,0x5a,1);PostMessageW(hwnd,WM_IME_CHAR,0xd55c,1);
    PostMessageW(hwnd,WM_UNICHAR,0x1f600,1);PostMessageW(hwnd,WM_KEYDOWN,VK_BACK,1);
    if(!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.empty(),
               "fresh letters IME text supplementary input and edit keys are rejected while native focus is lost"))return false;
    if(!Expect(window.EnableTextInput(true,&error,1001) && window.GetTextInputState(&unfocused,&error) && !unfocused.enabled,
               "repeated render opt-in cannot revive an unfocused native editor"))return false;
    if(!Expect(prepare() && window.UpdatePreparedGpuSceneRetainingInput(scene,&error) &&
               window.EnableTextInput(true,&error,1001) && window.GetTextInputState(&unfocused,&error) && !unfocused.enabled,
               "a scene refresh cannot restore native focus without WM_SETFOCUS"))return false;
    SetFocus(hwnd);
    if(!Expect(GetFocus()==hwnd && window.GetTextInputState(&unfocused,&error) && unfocused.enabled &&
               unfocused.focusEpoch!=initial.focusEpoch,"native focus regain enables only its fresh native epoch"))return false;
    const auto beforeCancelEpoch=unfocused.focusEpoch;
    SendMessageW(hwnd,WM_CANCELMODE,0,0);
    if(!Expect(window.GetTextInputState(&unfocused,&error) && unfocused.enabled &&
               unfocused.focusEpoch!=beforeCancelEpoch && GetFocus()==hwnd,
               "mode cancellation invalidates old editor input while genuine native focus remains usable"))return false;
    Sleep(2);PostMessageW(hwnd,WM_CHAR,0xde00,1);
    if(!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.empty(),
               "native refocus cannot finish a surrogate from the previous focus lifetime"))return false;
    deferred.Bind(unfocused.editorOwner,unfocused.focusEpoch);
    PostMessageW(hwnd,WM_CHAR,0x44,1);
    if(!Expect(capture() && deferred.Size()==1,"a new native focus lifetime can retain newly committed text"))return false;
    PostMessageW(hwnd,WM_CHAR,0x45,1);PostMessageW(hwnd,WM_KEYDOWN,VK_BACK,1);
    if(!Expect(window.EnableTextInput(true,&error,1002),"a different child or Lua focus owner replaces native text ownership"))return false;
    BitmapTextInputState replacement{};
    if(!Expect(window.GetTextInputState(&replacement,&error) && replacement.editorOwner==1002 &&
               replacement.focusEpoch!=unfocused.focusEpoch,"replacement child gets a distinct native editor epoch"))return false;
    deferred.Drain(replacement.editorOwner,replacement.focusEpoch,events);
    if(!Expect(events.empty() && window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.empty(),
               "old child deferred and raw queued edits cannot be retagged to the new child"))return false;
    if(!Expect(!BitmapEditorInputBuffer::Matches(retainedExample,replacement.editorOwner,replacement.focusEpoch),
               "old player turn child or Lua focus ownership never matches a fresh editor token"))return false;
    deferred.Bind(initial.editorOwner,initial.focusEpoch);
    for(std::size_t i=0;i<BitmapEditorInputBuffer::Limit;++i)deferred.Retain(retainedExample);
    bool overflow=false;try{deferred.Retain(retainedExample);}catch(const std::length_error&){overflow=true;}
    if(!Expect(overflow && deferred.Size()==BitmapEditorInputBuffer::Limit,
               "continuous input reaches a fixed deferral bound and fails visibly instead of silently dropping edits"))return false;
    deferred.Clear();
    if(!Expect(deferred.Size()==0,"clearing an editor epoch releases all deferred events"))return false;
    Sleep(2);deferred.Bind(replacement.editorOwner,replacement.focusEpoch);
    PostMessageW(hwnd,WM_CHAR,0x46,1);PostMessageW(hwnd,WM_CLOSE,0,0);
    if(!Expect(capture() && closed && deferred.Size()==0,
               "deferred save-and-close remains terminal and clears editor replay"))return false;
    std::fprintf(stderr,"EDITOR_REFRESH_INPUT_TESTS_PASS|rapid_packet_wait|repeated_edits|original_generations|same_editor_surrogate|owner_focus_rejection|terminal_geometry_barrier|bounded_queue\n");
    return true;
}

bool RunRetainingInputTests(const Scene& scene,const Scene& replacementScene,
                           const std::wstring& png,const std::wstring& replacementPng,
                           const std::wstring& tinyPng) {
    std::wstring error;
    BitmapWindow window;
    if (!Expect(window.Create(scene,png,L"Hidden retained-input test",800,600,false,&error),
                "create an independent hidden window for retained-input generations")) return false;
    const HWND hwnd=window.NativeHandle();
    if (!Expect(window.EnableGameplayInput(true,&error) && window.PumpMessages(&error) &&
                window.EnableProductionPointerInput(true,&error,false),
                "enable deferred close and deterministic synthetic pointer input")) return false;

    PostMessageW(hwnd,WM_KEYDOWN,VK_RETURN,1);
    if (!Expect(window.PumpMessages(&error),"queue a pending input before failed replacement")) return false;
    Scene invalidScene=replacementScene;
    invalidScene.hits[0].bounds[2]=invalidScene.hits[0].bounds[0];
    std::vector<BitmapInputEvent> events;
    if (!Expect(!window.UpdateSceneRetainingInput(invalidScene,replacementPng,&error) &&
                window.SceneGeneration()==1 && window.DrainInputs(&events,&error) && events.size()==1 &&
                events[0].kind==BitmapInputKind::KeyDown && events[0].virtualKey==VK_RETURN &&
                events[0].sceneGeneration==1,
                "invalid replacement preserves the active generation and pending command")) return false;

    PostMessageW(hwnd,WM_KEYDOWN,VK_ESCAPE,1);
    if (!Expect(window.PumpMessages(&error),"queue input before a PNG resource failure")) return false;
    if (!Expect(!window.UpdateSceneRetainingInput(replacementScene,tinyPng,&error) &&
                window.SceneGeneration()==1 && window.DrainInputs(&events,&error) && events.size()==1 &&
                events[0].kind==BitmapInputKind::KeyDown && events[0].virtualKey==VK_ESCAPE &&
                events[0].sceneGeneration==1,
                "decode failure preserves the active generation and pending command")) return false;

    // A deterministic backlog larger than the update pump budget proves the method
    // returns without relying on a timer or a racing continuous producer thread.
    std::size_t postedMoves=0;
    for (int i=0;i<1024;++i)
        if (PostMessageW(hwnd,WM_MOUSEMOVE,0,MAKELPARAM(100,100))) ++postedMoves;
    if (!Expect(postedMoves>256,"prepare more posted pointer messages than the update pump budget")) return false;
    if (!Expect(window.UpdateSceneRetainingInput(replacementScene,replacementPng,&error) &&
                window.SceneGeneration()==2 && window.DrainInputs(&events,&error) && !events.empty() &&
                events.front().kind==BitmapInputKind::PointerMove && events.front().sceneGeneration==1,
                "bounded update commits through a large input backlog and retains old generation")) return false;
    MSG queuedMove{};
    if (!Expect(PeekMessageW(&queuedMove,hwnd,WM_MOUSEMOVE,WM_MOUSEMOVE,PM_NOREMOVE)!=FALSE,
                "bounded update leaves the unprocessed pointer backlog queued")) return false;
    if (!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error),
                "ordinary pumping resumes after the bounded scene update")) return false;

    PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(100,100));
    PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(100,100));
    if (!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.size()==1 &&
                events[0].kind==BitmapInputKind::ControlClick && events[0].controlKey==22 &&
                events[0].sceneGeneration==2,
                "input after commit maps to the new scene and generation")) return false;
    const BOOL pointerPosted=PostMessageW(hwnd,WM_MOUSEMOVE,0,MAKELPARAM(100,100));
    const BOOL clickPosted=PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(100,100));
    const BOOL clickReleased=PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(100,100));
    const BOOL closePosted=IsWindow(hwnd);
    if(closePosted)BitmapWindowReentryTestAccess::CloseDuringDispatch(window);
    if (!Expect(pointerPosted && clickPosted && clickReleased && closePosted,
                "post pointer/click and send a reentrant CloseRequest for old-generation retention")) return false;
    if (!Expect(window.PumpMessages(&error) && window.NativeHandle()==hwnd,
                "gameplay close is queued without destroying the owned window")) return false;
    if (!Expect(window.UpdateSceneRetainingInput(scene,png,&error) && window.SceneGeneration()==3,
                "valid replacement commits once while old pointer, click, and close remain queued")) return false;
    const bool drained=window.DrainInputs(&events,&error);
    bool pointer=false,click=false,close=false,allOldGeneration=true;
    for (const BitmapInputEvent& event:events) {
        allOldGeneration=allOldGeneration && event.sceneGeneration==2;
        if (event.kind==BitmapInputKind::PointerMove && event.controlKey==22) pointer=true;
        if (event.kind==BitmapInputKind::ControlClick && event.controlKey==22) click=true;
        if (event.kind==BitmapInputKind::CloseRequest) close=true;
    }
    if (!Expect(drained && pointer && click && close && allOldGeneration,
                "post-commit drain retains pointer, click, and CloseRequest with their original generation")) return false;

    BitmapWindowReentryTestAccess::CloseDuringDispatch(window);
    if (!Expect(window.NativeHandle()==hwnd && window.IsOpen(),
                "reentrant gameplay WM_CLOSE preserves its owned HWND for save")) return false;
    if (!Expect(window.DrainInputs(&events,&error) && events.empty(),
                "reentrant duplicate gameplay WM_CLOSE preserves the one-shot close request")) return false;

    BitmapWindow overflowWindow;
    if (!Expect(overflowWindow.Create(scene,png,L"Hidden overflow retention test",800,600,false,&error),
                "create an independent hidden overflow test window")) return false;
    if (!Expect(overflowWindow.EnableGameplayInput(true,&error) &&
                overflowWindow.PumpMessages(&error) &&
                overflowWindow.EnableProductionPointerInput(true,&error,false),
                "enable overflow test inputs and settle initial window messages")) return false;
    POINT wheelPoint{100,400};
    ClientToScreen(overflowWindow.NativeHandle(),&wheelPoint);
    for (int i=0;i<4097;++i)
        PostMessageW(overflowWindow.NativeHandle(),WM_MOUSEWHEEL,MAKEWPARAM(0,WHEEL_DELTA),
                     MAKELPARAM(wheelPoint.x,wheelPoint.y));
    PostMessageW(overflowWindow.NativeHandle(),WM_CLOSE,0,0);
    if (!Expect(overflowWindow.PumpMessages(&error),"fill the bounded queue and retain deferred close")) return false;
    if (!Expect(overflowWindow.UpdateSceneRetainingInput(replacementScene,replacementPng,&error) &&
                overflowWindow.SceneGeneration()==2,
                "scene commit preserves both overflow state and queued close")) return false;
    error.clear();
    const bool overflowDrain=overflowWindow.DrainInputs(&events,&error);
    bool retainedClose=false,oldGeneration=true;
    for (const BitmapInputEvent& event:events) {
        retainedClose=retainedClose || event.kind==BitmapInputKind::CloseRequest;
        oldGeneration=oldGeneration && event.sceneGeneration==1;
    }
    if (!Expect(!overflowDrain && events.size()==4096 && retainedClose && oldGeneration &&
                error.find(L"queue overflowed")!=std::wstring::npos,
                "overflow drain reports incomplete input while returning CloseRequest and old generations")) return false;
    return true;
}
}

static int RunBitmapWindowTests(int argc,wchar_t** argv) {
    const bool retain=argc==3 && std::wcscmp(argv[1],L"--artifact-dir")==0;
    if (argc!=1 && !retain) return 2;
    float x=0,y=0;
    if (!Expect(!BitmapWindow::MapClientPointToLogical(800,600,400,74,&x,&y),
                "letterbox bar cannot map to a control")) return 1;
    BitmapDisplayRect r=BitmapWindow::ComputeDisplayRect(800,600);
    if (!Expect(Near(r.left,0)&&Near(r.top,75)&&Near(r.right,800)&&Near(r.bottom,525),
                "4:3 client letterboxes a 16:9 scene")) return 1;
    if (!Expect(BitmapWindow::MapClientPointToLogical(800,600,400,300,&x,&y)&&Near(x,960)&&Near(y,540),
                "center maps through the same aspect transform")) return 1;
    if (!Expect(!BitmapWindow::MapClientPointToLogical(800,600,800,300,&x,&y),
                "display right boundary is excluded")) return 1;
    r=BitmapWindow::ComputeDisplayRect(900,1600);
    if (!Expect(Near(r.left,0)&&Near(r.right,900)&&Near(r.top,546.875f)&&Near(r.bottom,1053.125f),
                "portrait resize centers the full-ratio scene")) return 1;
    if (!Expect(BitmapWindow::MapClientPointToLogical(900,1600,450,800,&x,&y)&&Near(x,960)&&Near(y,540),
                "portrait center round-trips to logical center")) return 1;
    r=BitmapWindow::ComputeDisplayRect(2560,1440);
    if (!Expect(Near(r.left,0)&&Near(r.top,0)&&Near(r.right,2560)&&Near(r.bottom,1440),
                "high-resolution 16:9 client has no letterbox")) return 1;

    wchar_t temp[MAX_PATH]={};
    if (retain) {
        if (!CreateDirectoryW(argv[2],nullptr) && GetLastError()!=ERROR_ALREADY_EXISTS) return 2;
        if (wcslen(argv[2])+100>=MAX_PATH) return 2;
        wcscpy_s(temp,argv[2]); const std::size_t n=wcslen(temp);
        if (n && temp[n-1]!=L'\\' && temp[n-1]!=L'/') wcscat_s(temp,L"\\");
    } else if (!GetTempPathW(MAX_PATH,temp)) return 2;
    const std::wstring prefix=std::wstring(temp)+L"ZeroSisBitmapWindow_"+std::to_wstring(GetCurrentProcessId());
    const std::wstring png=prefix+L"_scene.png";
    Scene scene{}; scene.width=1920; scene.height=1080;
    scene.hits.push_back({11,{0,0,960,540}});
    scene.hits.push_back({22,{960,0,1920,540}});
    scene.scrolls.push_back({33,{0,0,960,1080}});
    scene.scrolls.push_back({44,{960,0,1920,1080}});
    Sprite red{}; red.controlKey=11; red.textureIndex=kSolidRectangleTexture;
    const float unit[4]={0,0,1,1}, left[4]={0,0,960,540}, all[4]={0,0,1920,1080};
    const float redTint[4]={1,0,0,1}, blueTint[4]={0,0,1,1};
    std::memcpy(red.sourceRect,unit,sizeof(unit)); std::memcpy(red.targetRect,left,sizeof(left));
    std::memcpy(red.clipRect,all,sizeof(all)); std::memcpy(red.tintRGBA,redTint,sizeof(redTint));
    Sprite blue{}; blue.controlKey=22; blue.textureIndex=kSolidRectangleTexture;
    std::memcpy(blue.sourceRect,unit,sizeof(unit)); std::memcpy(blue.targetRect,all,sizeof(all));
    std::memcpy(blue.clipRect,all,sizeof(all)); std::memcpy(blue.tintRGBA,blueTint,sizeof(blueTint));
    scene.sprites.push_back(blue); scene.sprites.push_back(red);
    std::wstring error;
    if (!Expect(RenderToPng(scene,png,&error),"create the retained scene PNG through renderer API")) return 1;

    {
        BitmapWindow failedCreate;
        const std::wstring missing=prefix+L"_missing.png";
        if (!Expect(!failedCreate.Create(scene,missing,L"Missing PNG",800,600,false,&error),
                    "missing PNG fails after the one allowed creation attempt")) return 1;
        if (!Expect(!failedCreate.Create(scene,png,L"Retry forbidden",800,600,false,&error),
                    "failed Create cannot retry or increment COM apartment initialization")) return 1;
    }

    BitmapWindow window;
    if (!Expect(window.Create(scene,png,L"Hidden bitmap presenter test",800,600,false,&error),
                "create an owned hidden HWND") || !Expect(window.NativeHandle()!=nullptr && window.IsOpen(),
                "hidden window remains open")) {
        DeleteFileW(png.c_str()); return 1;
    }
    HWND hwnd=window.NativeHandle();
    if (!Expect(window.ResizeClient(800,600,&error),"resize hidden HWND to letterboxed client")) return 1;
    if (!Expect(window.PumpMessages(&error),"pump only owning-thread window messages")) return 1;
    RECT client{}; GetClientRect(hwnd,&client);
    if (!Expect(client.right==800 && client.bottom==600,"requested client size is exact")) return 1;
    const std::wstring frameInitial=prefix+L"_frame_800x600.png";
    if(!Expect(window.CaptureFrame(frameInitial,&error),"capture the HWND swap-chain back buffer")) { PrintError(error); return 1; }
    std::vector<BYTE> initialPixels,afterRefusal;
    if(!Expect(ReadFrame(frameInitial,800,600,&initialPixels) &&
               Pixel(initialPixels,800,0,0,0,0,0) && Pixel(initialPixels,800,200,200,255,0,0) &&
               Pixel(initialPixels,800,600,200,0,0,255) && Pixel(initialPixels,800,200,450,0,0,255),
               "GPU readback contains the displayed opaque scene and black letterbox"))return 1;
    BitmapFrameInfo firstInfo{};
    if(!Expect(window.GetFrameInfo(&firstInfo,&error) && firstInfo.clientWidth==800 && firstInfo.clientHeight==600 &&
               firstInfo.renderCount>0 && firstInfo.presentCount>0 && firstInfo.lastPresentResult>=0 &&
               firstInfo.deviceKind!=BitmapDeviceKind::Unknown && firstInfo.deviceIdentity!=0 && window.SceneGeneration()==1,
               "GPU frame metadata binds valid device, client, buffer and successful Present"))return 1;
    if(!Expect(!window.CaptureFrame(frameInitial,&error) && ReadFrame(frameInitial,800,600,&afterRefusal) &&
               initialPixels==afterRefusal,"repeated capture rejects overwrite and preserves all retained pixels"))return 1;
    if(!Expect(!window.ResizeClient(32768,32768,&error),"frame memory limit rejects a giant client before resize"))return 1;

    std::atomic<bool> foreignPump{true},foreignDrain{true},foreignCapture{true},foreignInfo{true},foreignUpdate{true};
    std::thread foreign([&] {
        std::wstring threadError;
        std::vector<BitmapInputEvent> threadEvents;
        foreignPump.store(window.PumpMessages(&threadError));
        threadError.clear();
        foreignDrain.store(window.DrainInputs(&threadEvents,&threadError));
        foreignCapture.store(window.CaptureFrame(prefix+L"_foreign.png",&threadError));
        BitmapFrameInfo info{};
        foreignInfo.store(window.GetFrameInfo(&info,&threadError));
        foreignUpdate.store(window.UpdateScene(scene,png,&threadError));
    });
    foreign.join();
    if (!Expect(!foreignPump.load(),"message pumping rejects a non-owner thread")) return 1;
    if (!Expect(!foreignDrain.load(),"input draining rejects a non-owner thread")) return 1;
    if(!Expect(!foreignCapture.load() && !foreignInfo.load() &&
               GetFileAttributesW((prefix+L"_foreign.png").c_str())==INVALID_FILE_ATTRIBUTES,
               "GPU capture and metadata reject a non-owner thread without creating a file"))return 1;
    if(!Expect(!foreignUpdate.load(),"scene update rejects a non-owner thread"))return 1;

    const LPARAM initial=1;
    PostMessageW(hwnd,WM_KEYDOWN,VK_ESCAPE,initial);
    PostMessageW(hwnd,WM_KEYDOWN,VK_ESCAPE,static_cast<LPARAM>(1|(1ll<<30)));
    PostMessageW(hwnd,WM_KEYDOWN,VK_RETURN,initial);
    PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(100,100));
    PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(100,100));
    if (!Expect(window.PumpMessages(&error),"dispatch owned synthetic input messages")) return 1;
    std::vector<BitmapInputEvent> events;
    if (!Expect(window.DrainInputs(&events,&error)&&events.size()==3,"drain only non-repeat Escape, Enter, and hit click")) return 1;
    if (!Expect(events[0].kind==BitmapInputKind::KeyDown && events[0].virtualKey==VK_ESCAPE &&
                events[1].kind==BitmapInputKind::KeyDown && events[1].virtualKey==VK_RETURN,
                "key events contain only requested virtual keys")) return 1;
    if (!Expect(events[2].kind==BitmapInputKind::ControlClick && events[2].controlKey==11 &&
                Near(events[2].logicalX,240)&&Near(events[2].logicalY,60),
                "click uses displayed-image transform and frontmost control hit")) return 1;

    POINT wheelPoint{100,400}; // Inside panel 33 but outside every clickable row.
    ClientToScreen(hwnd,&wheelPoint);
    PostMessageW(hwnd,WM_MOUSEMOVE,0,MAKELPARAM(100,100));
    PostMessageW(hwnd,WM_MOUSEWHEEL,MAKEWPARAM(0,WHEEL_DELTA),MAKELPARAM(wheelPoint.x,wheelPoint.y));
    if(!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.empty(),
               "ranking-compatible window ignores pointer and wheel messages until production opt-in"))return 1;
    if(!Expect(window.EnableProductionPointerInput(true,&error),
               "owner thread can explicitly enable production pointer input"))return 1;
    PostMessageW(hwnd,WM_MOUSEMOVE,0,MAKELPARAM(100,100));
    PostMessageW(hwnd,WM_MOUSEMOVE,0,MAKELPARAM(600,100));
    PostMessageW(hwnd,WM_MOUSEWHEEL,MAKEWPARAM(0,WHEEL_DELTA),MAKELPARAM(wheelPoint.x,wheelPoint.y));
    const bool pointerPump=window.PumpMessages(&error) && window.DrainInputs(&events,&error);
    // TrackMouseEvent can deliver an immediate WM_MOUSELEAVE for a hidden test HWND.
    // Preserve that real leave event after the coalesced move and independent wheel.
    if(!pointerPump || (events.size()!=2 && events.size()!=3) || events[0].kind!=BitmapInputKind::PointerMove || events[0].controlKey!=22 ||
       events[0].sceneGeneration!=window.SceneGeneration() || events[1].kind!=BitmapInputKind::Scroll ||
       events[1].controlKey!=33 || !Near(events[1].scrollDelta,-48.0f) ||
       events[1].sceneGeneration!=window.SceneGeneration() ||
       (events.size()==3 && (events[2].kind!=BitmapInputKind::PointerMove || events[2].controlKey!=0))) {
        std::fprintf(stderr,"POINTER_SCROLL_DEBUG|pump=%d|count=%zu|error=%ls\n",pointerPump?1:0,events.size(),error.c_str());
        for(const auto& event:events)
            std::fprintf(stderr,"POINTER_SCROLL_EVENT|kind=%u|key=%llu|x=%.2f|y=%.2f|delta=%.2f|generation=%llu\n",
                static_cast<unsigned>(event.kind),static_cast<unsigned long long>(event.controlKey),
                event.logicalX,event.logicalY,event.scrollDelta,static_cast<unsigned long long>(event.sceneGeneration));
    }
    if(!Expect(pointerPump && (events.size()==2 || events.size()==3) &&
               events[0].kind==BitmapInputKind::PointerMove && events[0].controlKey==22 &&
               events[0].sceneGeneration==window.SceneGeneration() &&
               events[1].kind==BitmapInputKind::Scroll && events[1].controlKey==33 &&
               Near(events[1].scrollDelta,-48.0f) && events[1].sceneGeneration==window.SceneGeneration() &&
               (events.size()==2 || (events[2].kind==BitmapInputKind::PointerMove && events[2].controlKey==0)),
               "production pointer coalescing, client mapping, topmost row ownership, and 48-pixel wheel policy"))return 1;
    POINT letterboxPoint{400,74};
    ClientToScreen(hwnd,&letterboxPoint);
    PostMessageW(hwnd,WM_MOUSEMOVE,0,MAKELPARAM(400,74));
    PostMessageW(hwnd,WM_MOUSEWHEEL,MAKEWPARAM(0,WHEEL_DELTA),MAKELPARAM(letterboxPoint.x,letterboxPoint.y));
    PostMessageW(hwnd,WM_MOUSELEAVE,0,0);
    if(!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.size()==1 &&
               events[0].kind==BitmapInputKind::PointerMove && events[0].controlKey==0,
               "letterbox/leave clears hover while empty-space wheel has no row target"))return 1;
    if(!Expect(window.EnableProductionPointerInput(false,&error) &&
               window.DrainInputs(&events,&error) && events.size()==1 &&
               events[0].kind==BitmapInputKind::PointerMove && events[0].controlKey==0,
               "disabling production pointer input queues a final hover release"))return 1;
    if(!Expect(window.EnableProductionPointerInput(true,&error,false),
               "production test mode can re-enable input with automatic leave tracking disabled"))return 1;
    PostMessageW(hwnd,WM_MOUSEMOVE,0,MAKELPARAM(100,100));
    PostMessageW(hwnd,WM_MOUSEMOVE,0,MAKELPARAM(600,100));
    if(!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.size()==1 &&
               events[0].kind==BitmapInputKind::PointerMove && events[0].controlKey==22,
               "disabled automatic leave tracking preserves posted pointer move without real-cursor synthesis"))return 1;
    PostMessageW(hwnd,WM_MOUSELEAVE,0,0);
    if(!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.size()==1 &&
               events[0].kind==BitmapInputKind::PointerMove && events[0].controlKey==0,
               "synthetic profile accepts its explicit posted leave transition"))return 1;
    if(!Expect(window.EnableProductionPointerInput(false,&error) &&
               window.DrainInputs(&events,&error) && events.size()==1 && events[0].controlKey==0,
               "manual leave state remains safely releasable on opt-out"))return 1;
    if(!Expect(window.EnableProductionPointerInput(true,&error),
               "production default restores automatic leave tracking"))return 1;
    for(std::size_t i=0;i<4097;++i)
        PostMessageW(hwnd,WM_MOUSEWHEEL,MAKEWPARAM(0,WHEEL_DELTA),MAKELPARAM(wheelPoint.x,wheelPoint.y));
    if(!Expect(window.PumpMessages(&error) && !window.DrainInputs(&events,&error) &&
               events.size()==4096 && error.find(L"queue overflowed")!=std::wstring::npos,
               "scroll storm preserves the bounded input queue overflow signal"))return 1;
    if(!Expect(window.DrainInputs(&events,&error) && events.empty(),
               "overflow report drains the bounded partial batch exactly once"))return 1;
    if(!Expect(window.EnableProductionPointerInput(false,&error) &&
               window.DrainInputs(&events,&error) && events.size()==1 &&
               events[0].kind==BitmapInputKind::PointerMove && events[0].controlKey==0,
               "overflow recovery still releases production hover on opt-out"))return 1;

    if (!Expect(window.ResizeClient(1000,700,&error),"resize to a second client geometry")) { PrintError(error); return 1; }
    if(!Expect(window.PumpMessages(&error),"resized GPU surface message pump succeeds")) { PrintError(error); return 1; }
    GetClientRect(hwnd,&client);
    if (client.right!=1000 || client.bottom!=700)
        std::fprintf(stderr,"actual client size %ldx%ld\n",client.right,client.bottom);
    if (!Expect(client.right==1000 && client.bottom==700,"resized client keeps requested dimensions")) return 1;
    const std::wstring frameResized=prefix+L"_frame_1000x700.png";
    std::vector<BYTE> resizedPixels;
    if(!Expect(window.CaptureFrame(frameResized,&error) && ReadFrame(frameResized,1000,700,&resizedPixels) &&
               Pixel(resizedPixels,1000,0,0,0,0,0) && Pixel(resizedPixels,1000,250,200,255,0,0) &&
               Pixel(resizedPixels,1000,750,200,0,0,255) && Pixel(resizedPixels,1000,250,500,0,0,255),
               "resize recreates the swap-chain target and captures the expected scene")) { PrintError(error); return 1; }
    BitmapFrameInfo resizedInfo{};
    if(!Expect(window.GetFrameInfo(&resizedInfo,&error) && resizedInfo.clientWidth==1000 && resizedInfo.clientHeight==700 &&
               resizedInfo.renderCount>firstInfo.renderCount && resizedInfo.presentCount>firstInfo.presentCount &&
               resizedInfo.lastPresentResult>=0 && resizedInfo.deviceKind==firstInfo.deviceKind &&
               resizedInfo.deviceIdentity==firstInfo.deviceIdentity,
               "resize preserves device identity and advances render/Present counters"))return 1;
    PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(500,349));
    PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(500,349));
    PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(500,350));
    PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(500,350));
    if (!Expect(window.PumpMessages(&error)&&window.DrainInputs(&events,&error)&&events.size()==1 &&
                events[0].kind==BitmapInputKind::ControlClick&&events[0].controlKey==22,
                "hit right edge is inclusive for adjacent control while bottom edge is excluded")) return 1;
    if (!Expect(!BitmapWindow::MapClientPointToLogical(1920,1080,1920,540,&x,&y),
                "logical scene right and bottom boundaries are excluded")) return 1;

    Scene replacementScene=scene;
    const float replacementRight[4]={960,0,1920,540};
    const float replacementLeft[4]={0,0,960,540};
    std::memcpy(replacementScene.sprites[1].targetRect,replacementRight,sizeof(replacementRight));
    std::memcpy(replacementScene.hits[0].bounds,replacementRight,sizeof(replacementRight));
    std::memcpy(replacementScene.hits[1].bounds,replacementLeft,sizeof(replacementLeft));
    const std::wstring replacementPng=prefix+L"_replacement_scene.png";
    if(!Expect(RenderToPng(replacementScene,replacementPng,&error),"prepare a replacement scene image"))return 1;

    PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(250,200));
    PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(250,200));
    if(!Expect(!window.UpdateScene(replacementScene,replacementPng,&error),
               "queued old-scene input blocks a scene update"))return 1;
    if(!Expect(window.DrainInputs(&events,&error) && events.size()==1 &&
               events[0].kind==BitmapInputKind::ControlClick && events[0].controlKey==11 &&
               events[0].sceneGeneration==window.SceneGeneration(),
               "queued click keeps its old-scene generation for the current callback"))return 1;
    if(!Expect(window.UpdateScene(replacementScene,replacementPng,&error),
               "update scene after the old input batch is drained")) { PrintError(error); return 1; }
    const std::uint64_t replacementGeneration=window.SceneGeneration();
    const std::wstring frameUpdated=prefix+L"_frame_updated.png";
    std::vector<BYTE> updatedPixels;
    BitmapFrameInfo updatedInfo{};
    if(!Expect(replacementGeneration==2 && window.CaptureFrame(frameUpdated,&error) &&
               ReadFrame(frameUpdated,1000,700,&updatedPixels) &&
               Pixel(updatedPixels,1000,0,0,0,0,0) && Pixel(updatedPixels,1000,250,200,0,0,255) &&
               Pixel(updatedPixels,1000,750,200,255,0,0) &&
               window.GetFrameInfo(&updatedInfo,&error) && window.NativeHandle()==hwnd &&
               updatedInfo.clientWidth==1000 && updatedInfo.clientHeight==700 &&
               updatedInfo.deviceKind==resizedInfo.deviceKind &&
               updatedInfo.deviceIdentity==resizedInfo.deviceIdentity &&
               updatedInfo.renderCount>resizedInfo.renderCount && updatedInfo.presentCount>resizedInfo.presentCount,
               "scene update changes actual back-buffer pixels while preserving HWND and GPU device"))return 1;
    PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(250,200));
    PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(250,200));
    PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(750,200));
    PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(750,200));
    if(!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.size()==2 &&
               events[0].kind==BitmapInputKind::ControlClick && events[0].controlKey==22 &&
               events[1].kind==BitmapInputKind::ControlClick && events[1].controlKey==11 &&
               events[0].sceneGeneration==replacementGeneration && events[1].sceneGeneration==replacementGeneration,
               "updated hit regions map clicks to their new keys and generation"))return 1;

    Scene emptyScene{}; emptyScene.width=1920; emptyScene.height=1080;
    Scene invalidScene=replacementScene;
    invalidScene.hits[0].bounds[2]=invalidScene.hits[0].bounds[0];
    if(!Expect(!window.UpdateScene(invalidScene,replacementPng,&error),
               "invalid replacement hit bounds are rejected"))return 1;
    Scene tinyScene{}; tinyScene.width=16; tinyScene.height=16;
    const std::wstring tinyPng=prefix+L"_wrong_size.png";
    if(!Expect(RenderToPng(tinyScene,tinyPng,&error),"prepare a valid PNG with the wrong logical dimensions"))return 1;
    if(!Expect(!window.UpdateScene(replacementScene,tinyPng,&error) &&
               !window.UpdateScene(emptyScene,tinyPng,&error),
               "provided PNG dimensions are validated for nonempty and empty scenes"))return 1;
    const std::wstring frameAfterFailure=prefix+L"_frame_after_failed_update.png";
    std::vector<BYTE> afterFailedUpdate;
    BitmapFrameInfo afterFailureInfo{};
    if(!Expect(window.SceneGeneration()==replacementGeneration && window.CaptureFrame(frameAfterFailure,&error) &&
               ReadFrame(frameAfterFailure,1000,700,&afterFailedUpdate) && afterFailedUpdate==updatedPixels &&
               window.GetFrameInfo(&afterFailureInfo,&error) && window.NativeHandle()==hwnd &&
               afterFailureInfo.deviceKind==updatedInfo.deviceKind &&
               afterFailureInfo.deviceIdentity==updatedInfo.deviceIdentity,
               "failed scene validation preserves displayed pixels, generation, HWND, and device"))return 1;
    PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(250,200));
    PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(250,200));
    if(!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.size()==1 &&
               events[0].controlKey==22 && events[0].sceneGeneration==replacementGeneration,
               "failed update preserves the active scene hit targets"))return 1;

    if(!Expect(window.UpdateScene(emptyScene,L"",&error) && window.SceneGeneration()==3,
               "empty closed scene clears scene data without replacing the HWND"))return 1;
    const std::wstring frameEmpty=prefix+L"_frame_empty.png";
    std::vector<BYTE> emptyPixels;
    BitmapFrameInfo emptyInfo{};
    if(!Expect(window.CaptureFrame(frameEmpty,&error) && ReadFrame(frameEmpty,1000,700,&emptyPixels) &&
               Pixel(emptyPixels,1000,0,0,0,0,0) && Pixel(emptyPixels,1000,250,200,0,0,0) &&
               Pixel(emptyPixels,1000,750,500,0,0,0) && window.NativeHandle()==hwnd &&
               window.GetFrameInfo(&emptyInfo,&error) && emptyInfo.deviceIdentity==firstInfo.deviceIdentity,
               "empty scene presents a black back buffer through the same HWND"))return 1;
    PostMessageW(hwnd,WM_LBUTTONDOWN,MK_LBUTTON,MAKELPARAM(250,200));
    PostMessageW(hwnd,WM_LBUTTONUP,0,MAKELPARAM(250,200));
    PostMessageW(hwnd,WM_KEYDOWN,VK_ESCAPE,1);
    if(!Expect(window.PumpMessages(&error) && window.DrainInputs(&events,&error) && events.size()==1 &&
               events[0].kind==BitmapInputKind::KeyDown && events[0].virtualKey==VK_ESCAPE &&
               events[0].sceneGeneration==window.SceneGeneration(),
               "empty hit map rejects old control clicks while retaining current-generation keys"))return 1;

    if(!RunPixelHitTests(window,png))return 1;

    PostMessageW(hwnd,WM_CLOSE,0,0);
    if (!Expect(window.PumpMessages(&error)&&!window.IsOpen(),"WM_CLOSE destroys only its owned HWND")) return 1;
    if (!Expect(window.DrainInputs(&events,&error)&&events.size()==1&&events[0].kind==BitmapInputKind::CloseRequest,
                "window close is reported as a distinct queue event")) return 1;
    if (!Expect(!window.Create(scene,png,L"Recreate forbidden",800,600,false,&error),
                "WM_CLOSE does not permit one-shot object recreation")) return 1;
    if(!Expect(!window.CaptureFrame(prefix+L"_closed.png",&error) && !window.GetFrameInfo(&resizedInfo,&error),
               "closed window rejects GPU capture and metadata"))return 1;
    if(!Expect(!window.UpdateScene(scene,png,&error) && window.SceneGeneration()==0,
               "closed window rejects scene update and generation lookup"))return 1;
    if(!RunUnicodeTextInputTests(scene,png))return 1;
    if(!RunEditorRefreshInputTests())return 1;
    if(!RunRetainingInputTests(scene,replacementScene,png,replacementPng,tinyPng)) return 1;
    if(!RunGpuSceneTests(prefix,retain))return 1;
    if(!RunPreparedGpuFrameTests(prefix,retain))return 1;
    if(!RunPreparedGpuRefreshTests(prefix,retain))return 1;
    if (!retain) {
        DeleteFileW(png.c_str()); DeleteFileW(frameInitial.c_str()); DeleteFileW(frameResized.c_str());
        DeleteFileW(replacementPng.c_str()); DeleteFileW(frameUpdated.c_str()); DeleteFileW(tinyPng.c_str());
        DeleteFileW(frameAfterFailure.c_str()); DeleteFileW(frameEmpty.c_str());
    }
    std::printf("PASS|%d|hidden owned GPU HWND, PNG and retained-scene capture, resize, one-shot COM lifetime, owner-thread checks, and isolated input queue\n",checks);
    return 0;
}

static LONG WINAPI BitmapWindowUnhandledException(EXCEPTION_POINTERS* info) {
    const DWORD code=info && info->ExceptionRecord ? info->ExceptionRecord->ExceptionCode : 0;
    const void* address=info && info->ExceptionRecord ? info->ExceptionRecord->ExceptionAddress : nullptr;
    MEMORY_BASIC_INFORMATION memory{};
    HMODULE module=nullptr;
    if (address && VirtualQuery(address,&memory,sizeof(memory))==sizeof(memory))
        module=static_cast<HMODULE>(memory.AllocationBase);
    wchar_t modulePath[MAX_PATH]={};
    if (module) GetModuleFileNameW(module,modulePath,MAX_PATH);
    char moduleUtf8[MAX_PATH*4]={};
    if (modulePath[0]) WideCharToMultiByte(CP_UTF8,0,modulePath,-1,moduleUtf8,sizeof(moduleUtf8),nullptr,nullptr);
    std::fprintf(stderr,"UNHANDLED_EXCEPTION|code=0x%08lX|address=%p|module=%s|base=%p\n",
                 static_cast<unsigned long>(code),address,moduleUtf8,module);
    std::fflush(stderr);
    return EXCEPTION_EXECUTE_HANDLER;
}

int wmain(int argc,wchar_t** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX);
    const HRESULT wer=WerSetFlags(WER_FAULT_REPORTING_NO_UI);
    if (FAILED(wer)) { std::fprintf(stderr,"WER_FLAGS_FAILED|hr=0x%08lX\n",static_cast<unsigned long>(wer)); return 2; }
    SetUnhandledExceptionFilter(BitmapWindowUnhandledException);
    std::fprintf(stderr,"TEST_PROCESS_START|pid=%lu\n",static_cast<unsigned long>(GetCurrentProcessId()));
    std::fflush(stderr);
    __try {
        return RunBitmapWindowTests(argc,argv);
    } __except(BitmapWindowUnhandledException(GetExceptionInformation())) {
        return 0xe0000001u;
    }
}
