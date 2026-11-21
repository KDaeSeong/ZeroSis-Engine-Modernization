#include "../Source/Presentation/BitmapRenderer.h"

#include <Windows.h>
#include <wincodec.h>
#include <wrl/client.h>

#include <cstdint>
#include <cstdio>
#include <cwchar>
#include <cstring>
#include <fstream>
#include <limits>
#include <string>
#include <vector>

using Microsoft::WRL::ComPtr;
using namespace ZeroSisPresentation;

namespace {
int checks=0;
bool Expect(bool condition,const char* name) {
    ++checks;
    if (!condition) std::fprintf(stderr,"FAIL %s\n",name);
    return condition;
}
void Put32(std::vector<std::uint8_t>& b,std::uint32_t v) {
    for (int i=0;i<4;++i) b.push_back(static_cast<std::uint8_t>(v>>(i*8)));
}
void Put64(std::vector<std::uint8_t>& b,std::uint64_t v) {
    Put32(b,static_cast<std::uint32_t>(v)); Put32(b,static_cast<std::uint32_t>(v>>32));
}
void PutFloat(std::vector<std::uint8_t>& b,float value) {
    std::uint32_t bits=0; std::memcpy(&bits,&value,4); Put32(b,bits);
}
void PutFloats(std::vector<std::uint8_t>& b,const float* values,int count) {
    for (int i=0;i<count;++i) PutFloat(b,values[i]);
}
bool WriteBytes(const std::wstring& path,const std::vector<std::uint8_t>& bytes) {
    std::ofstream f(path,std::ios::binary|std::ios::trunc);
    return f && f.write(reinterpret_cast<const char*>(bytes.data()),static_cast<std::streamsize>(bytes.size())).good();
}
std::vector<std::uint8_t> DdsHeader(std::uint32_t width,std::uint32_t height,
                                    std::uint32_t flags,std::uint32_t fourCC,
                                    std::uint32_t bits) {
    std::vector<std::uint8_t> b(128,0); std::memcpy(b.data(),"DDS ",4);
    auto set=[&](std::size_t at,std::uint32_t v) { for(int i=0;i<4;++i)b[at+i]=static_cast<std::uint8_t>(v>>(i*8)); };
    const bool compressed=fourCC!=0;
    set(4,124); set(8,0x1007u|(compressed?0x80000u:0x8u)); set(12,height); set(16,width);
    set(20,compressed?8u:width*(bits/8u));
    set(76,32); set(80,flags); set(84,fourCC); set(88,bits); set(108,0x1000u);
    return b;
}
std::vector<std::uint8_t> DdsDx10Bc(std::uint32_t dxgi,const std::vector<std::uint8_t>& block) {
    std::vector<std::uint8_t> b=DdsHeader(4,4,0x4u,0x30315844u,0);
    b.resize(148,0);
    auto set=[&](std::size_t at,std::uint32_t v) { for(int i=0;i<4;++i)b[at+i]=static_cast<std::uint8_t>(v>>(i*8)); };
    set(20,static_cast<std::uint32_t>(block.size()));
    set(128,dxgi); set(132,3); set(136,0); set(140,1); set(144,0);
    b.insert(b.end(),block.begin(),block.end());
    return b;
}
bool WriteV2ScrollPacket(const std::wstring& path,const float* bounds,bool trailing=false) {
    std::vector<std::uint8_t> b; const char magic[]="ZSUPIX02"; b.insert(b.end(),magic,magic+8);
    Put32(b,2);Put32(b,2);Put32(b,0);Put32(b,0);Put32(b,0);Put32(b,bounds?1u:0u);
    if(bounds){Put64(b,0x9876u);PutFloats(b,bounds,4);}
    if(trailing)b.push_back(0x7f);
    return WriteBytes(path,b);
}
bool WritePacket(const std::wstring& path,const std::string& texture,
                 const std::vector<float>& source={0,0,2,2},
                 const std::vector<float>& target={0,0,2,2},
                 const std::vector<float>& clip={0,0,1,2},
                 const std::vector<float>& tint={1,0.5f,0.25f,0.5f},
                 bool trailing=false) {
    std::vector<std::uint8_t> b; const char magic[]="ZSUPIX01"; b.insert(b.end(),magic,magic+8);
    Put32(b,2); Put32(b,2); Put32(b,1); Put32(b,1); Put32(b,1);
    Put32(b,static_cast<std::uint32_t>(texture.size())); b.insert(b.end(),texture.begin(),texture.end());
    Put32(b,0); Put64(b,0x12345678u); PutFloats(b,source.data(),4); PutFloats(b,target.data(),4);
    PutFloats(b,clip.data(),4); PutFloats(b,tint.data(),4); Put64(b,0x12345678u);
    const float hit[4]={0,0,2,2}; PutFloats(b,hit,4);
    if (trailing) b.push_back(0x7f);
    return WriteBytes(path,b);
}
bool ReadPngPixels(const std::wstring& path,std::vector<std::uint8_t>* pixels,
                   UINT* width,UINT* height) {
    ComPtr<IWICImagingFactory> wic;
    HRESULT hr=CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&wic));
    if (FAILED(hr)) return false;
    ComPtr<IWICBitmapDecoder> decoder;
    hr=wic->CreateDecoderFromFilename(path.c_str(),nullptr,GENERIC_READ,WICDecodeMetadataCacheOnLoad,&decoder);
    if (FAILED(hr)) return false;
    ComPtr<IWICBitmapFrameDecode> frame;
    if (FAILED(decoder->GetFrame(0,&frame)) || FAILED(frame->GetSize(width,height))) return false;
    ComPtr<IWICFormatConverter> converter;
    if (FAILED(wic->CreateFormatConverter(&converter)) || FAILED(converter->Initialize(
        frame.Get(),GUID_WICPixelFormat32bppBGRA,WICBitmapDitherTypeNone,nullptr,0.0,WICBitmapPaletteTypeCustom))) return false;
    pixels->resize(static_cast<std::size_t>(*width)*(*height)*4);
    return SUCCEEDED(converter->CopyPixels(nullptr,*width*4,static_cast<UINT>(pixels->size()),pixels->data()));
}
void PrintError(const std::wstring& error) {
    const int needed=WideCharToMultiByte(CP_UTF8,0,error.c_str(),-1,nullptr,0,nullptr,nullptr);
    if (needed<=1) return;
    std::string text(static_cast<std::size_t>(needed), '\0');
    WideCharToMultiByte(CP_UTF8,0,error.c_str(),-1,&text[0],needed,nullptr,nullptr);
    std::fprintf(stderr,"%s\n",text.c_str());
}
}

int wmain(int argc,wchar_t** argv) {
    const HRESULT comInit=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    if (FAILED(comInit)) return 2;
    wchar_t temp[MAX_PATH]={};
    const bool retain=argc==3 && std::wcscmp(argv[1],L"--artifact-dir")==0;
    if (argc!=1 && !retain) return 2;
    if (retain) {
        if (!CreateDirectoryW(argv[2],nullptr) && GetLastError()!=ERROR_ALREADY_EXISTS) return 2;
        if (wcslen(argv[2])+100>=MAX_PATH) return 2;
        wcscpy_s(temp,argv[2]);
        const std::size_t n=wcslen(temp);
        if (n && temp[n-1]!=L'\\' && temp[n-1]!=L'/') wcscat_s(temp,L"\\");
    } else if (!GetTempPathW(MAX_PATH,temp)) return 2;
    const DWORD pid=GetCurrentProcessId();
    const std::wstring stem=std::wstring(temp)+L"ZeroSisBitmapRenderer_"+std::to_wstring(pid);
    const std::wstring alphaPath=stem+L"_alpha.dds", rgbaPath=stem+L"_rgba.dds";
    const std::wstring bcPath=stem+L"_bc.dds", bc2Path=stem+L"_bc2.dds", bc3Path=stem+L"_bc3.dds";
    const std::wstring packetPath=stem+L"_scene.packet";
    const std::wstring pngPath=stem+L"_scene.png", rgbaPng=stem+L"_rgba.png", bcPng=stem+L"_bc.png";
    std::vector<std::uint8_t> alpha=DdsHeader(2,2,0x2u,0,8);
    alpha.insert(alpha.end(),{255,128,0,64});
    std::vector<std::uint8_t> rgba=DdsHeader(1,1,0x41u,0,32);
    auto set=[&](std::vector<std::uint8_t>& b,std::size_t at,std::uint32_t v){for(int i=0;i<4;++i)b[at+i]=static_cast<std::uint8_t>(v>>(i*8));};
    set(rgba,92,0x00ff0000u); set(rgba,96,0x0000ff00u); set(rgba,100,0x000000ffu); set(rgba,104,0xff000000u);
    rgba.insert(rgba.end(),{0,0,255,128}); // half-alpha blue in BGRA storage
    std::vector<std::uint8_t> bc=DdsHeader(4,4,0x4u,0x31545844u,0);
    bc.insert(bc.end(),{0x00,0xf8,0xe0,0x07,0,0,0,0}); // solid red BC1 block
    std::vector<std::uint8_t> bc2Block(8,0xff); bc2Block.insert(bc2Block.end(),{0x00,0xf8,0xe0,0x07,0,0,0,0});
    std::vector<std::uint8_t> bc3Block={255,0,0,0,0,0,0,0,0x00,0xf8,0xe0,0x07,0,0,0,0};
    const std::vector<std::uint8_t> bc2=DdsDx10Bc(74,bc2Block), bc3=DdsDx10Bc(77,bc3Block);
    std::vector<std::uint8_t> wrapped=alpha;
    std::memcpy(wrapped.data()+28,"FTXTInterface",13);
    const std::wstring wrappedPath=stem+L"_wrapped.dds";
    if (!Expect(WriteBytes(alphaPath,alpha),"write alpha DDS") ||
        !Expect(WriteBytes(rgbaPath,rgba),"write RGBA32 DDS") ||
        !Expect(WriteBytes(bcPath,bc),"write BC1 DDS") ||
        !Expect(WriteBytes(bc2Path,bc2),"write DX10 BC2 DDS") ||
        !Expect(WriteBytes(bc3Path,bc3),"write DX10 BC3 DDS") ||
        !Expect(WriteBytes(wrappedPath,wrapped),"write proprietary-wrapper DDS fixture")) return 1;

    const std::string alphaName="ZeroSisBitmapRenderer_"+std::to_string(pid)+"_alpha.dds";
    if (!Expect(WritePacket(packetPath,alphaName),"write scene packet")) return 1;
    if (retain && !CopyFileW(packetPath.c_str(),(stem+L"_valid.packet").c_str(),FALSE)) return 2;
    Scene scene{}; std::wstring error;
    if (!Expect(LoadScenePacket(packetPath,&scene,&error),"load strict scene packet")) return 1;
    if (!Expect(scene.textures.size()==1 && scene.sprites.size()==1 && scene.hits.size()==1 && scene.scrolls.empty(),
                "legacy ZSUPIX01 packet owns textures, sprites and hits with no scroll records")) return 1;
    if (!Expect(RenderToPng(scene,pngPath,&error),"render alpha atlas PNG")) {
        std::fwprintf(stderr,L"%ls\n",error.c_str()); return 1;
    }
    std::vector<std::uint8_t> pixels; UINT width=0,height=0;
    if (!Expect(ReadPngPixels(pngPath,&pixels,&width,&height),"decode output PNG") ||
        !Expect(width==2 && height==2,"output PNG dimensions")) return 1;
    if (!Expect(pixels[2]==255 && pixels[1]>=127 && pixels[1]<=128 && pixels[0]>=63 && pixels[0]<=64 && pixels[3]==128,
                "alpha8 white atlas receives premultiplied RGBA tint")) return 1;
    if (!Expect(pixels[4+3]==0,"clip rectangle excludes pixels outside its right edge")) return 1;

    Scene rgbaScene{}; rgbaScene.width=1; rgbaScene.height=1; rgbaScene.textures.push_back({rgbaPath});
    Sprite rgbaSprite{}; rgbaSprite.controlKey=4; rgbaSprite.textureIndex=0;
    const float full[4]={0,0,1,1}, white[4]={1,1,1,1};
    std::memcpy(rgbaSprite.sourceRect,full,sizeof(full)); std::memcpy(rgbaSprite.targetRect,full,sizeof(full));
    std::memcpy(rgbaSprite.clipRect,full,sizeof(full)); std::memcpy(rgbaSprite.tintRGBA,white,sizeof(white));
    rgbaScene.sprites.push_back(rgbaSprite);
    if (!Expect(RenderToPng(rgbaScene,rgbaPng,&error),"render standard RGBA32 DDS")) return 1;
    pixels.clear();
    if (!Expect(ReadPngPixels(rgbaPng,&pixels,&width,&height) && pixels[0]==0 && pixels[1]==0 && pixels[2]==255 && pixels[3]==128,
                "RGBA32 DDS channels and alpha are preserved")) return 1;

    Scene bcScene{}; bcScene.width=4; bcScene.height=4; bcScene.textures.push_back({bcPath});
    Sprite bcSprite{}; bcSprite.controlKey=5; bcSprite.textureIndex=0;
    const float bcRect[4]={0,0,4,4}; std::memcpy(bcSprite.sourceRect,bcRect,sizeof(bcRect));
    std::memcpy(bcSprite.targetRect,bcRect,sizeof(bcRect)); std::memcpy(bcSprite.clipRect,bcRect,sizeof(bcRect));
    std::memcpy(bcSprite.tintRGBA,white,sizeof(white)); bcScene.sprites.push_back(bcSprite);
    if (!Expect(RenderToPng(bcScene,bcPng,&error),"WIC decodes standard BC1 DDS")) {
        std::fwprintf(stderr,L"%ls\n",error.c_str()); return 1;
    }
    pixels.clear();
    if (!Expect(ReadPngPixels(bcPng,&pixels,&width,&height) && pixels[2]>240 && pixels[0]<10,
                "BC1 block reaches the PNG renderer")) return 1;

    auto checkDx10Bc=[&](const std::wstring& texture,const std::wstring& output,const char* label) {
        Scene value{}; value.width=4; value.height=4; value.textures.push_back({texture});
        Sprite sprite{}; sprite.textureIndex=0; const float bounds[4]={0,0,4,4};
        std::memcpy(sprite.sourceRect,bounds,sizeof(bounds)); std::memcpy(sprite.targetRect,bounds,sizeof(bounds));
        std::memcpy(sprite.clipRect,bounds,sizeof(bounds)); std::memcpy(sprite.tintRGBA,white,sizeof(white));
        value.sprites.push_back(sprite);
        if (!Expect(RenderToPng(value,output,&error),label)) { PrintError(error); return false; }
        std::vector<std::uint8_t> decoded;
        return Expect(ReadPngPixels(output,&decoded,&width,&height) && decoded[2]>240 && decoded[3]>240,
                      "DX10 BC decode reaches WIC PNG output");
    };
    if (!checkDx10Bc(bc2Path,stem+L"_bc2.png","WIC decodes DX10 BC2 DDS") ||
        !checkDx10Bc(bc3Path,stem+L"_bc3.png","WIC decodes DX10 BC3 DDS")) return 1;

    std::vector<float> invalidSource={0,0,3,2};
    if (!Expect(WritePacket(packetPath,alphaName,invalidSource),"write out-of-atlas packet") ||
        !Expect(LoadScenePacket(packetPath,&scene,&error) && !RenderToPng(scene,pngPath,&error),"reject source rectangle beyond atlas")) return 1;
    if (!Expect(WritePacket(packetPath,alphaName,{0,0,std::numeric_limits<float>::quiet_NaN(),2}),"write NaN packet") ||
        !Expect(!LoadScenePacket(packetPath,&scene,&error),"reject NaN coordinates")) return 1;
    if (!Expect(WritePacket(packetPath,std::string("bad\xff",4)),"write invalid UTF-8 packet") ||
        !Expect(!LoadScenePacket(packetPath,&scene,&error),"reject invalid UTF-8 path")) return 1;
    if (!Expect(WritePacket(packetPath,std::string("bad\0path",8)),"write NUL path packet") ||
        !Expect(!LoadScenePacket(packetPath,&scene,&error),"reject NUL in texture path")) return 1;
    if (!Expect(WritePacket(packetPath,alphaName,{0,0,2,2},{0,0,2,2},{0,0,1,2},{1,1,1,1},true),"write trailing-byte packet") ||
        !Expect(!LoadScenePacket(packetPath,&scene,&error),"reject trailing bytes")) return 1;
    Scene bad=rgbaScene; bad.sprites[0].textureIndex=9;
    if (!Expect(!RenderToPng(bad,rgbaPng,&error),"reject missing texture index")) return 1;
    Scene tooLarge{}; tooLarge.width=16384; tooLarge.height=16384;
    if (!Expect(!RenderToPng(tooLarge,rgbaPng,&error),"reject unreasonable image allocation")) return 1;
    Scene wrappedScene{}; wrappedScene.width=2; wrappedScene.height=2; wrappedScene.textures.push_back({wrappedPath});
    Sprite wrappedSprite{}; wrappedSprite.textureIndex=0; std::memcpy(wrappedSprite.sourceRect,full,sizeof(full));
    const float rect2[4]={0,0,2,2}; std::memcpy(wrappedSprite.sourceRect,rect2,sizeof(rect2));
    std::memcpy(wrappedSprite.targetRect,rect2,sizeof(rect2)); std::memcpy(wrappedSprite.clipRect,rect2,sizeof(rect2));
    std::memcpy(wrappedSprite.tintRGBA,white,sizeof(white)); wrappedScene.sprites.push_back(wrappedSprite);
    if (!Expect(!RenderToPng(wrappedScene,rgbaPng,&error),"reject private FTXT texture instead of drawing a substitute")) return 1;

    const float viewport[4]={0,0,2,2};
    if (!Expect(WriteV2ScrollPacket(packetPath,viewport),"write ZSUPIX02 viewport packet") ||
        !Expect(LoadScenePacket(packetPath,&scene,&error) && scene.scrolls.size()==1 &&
                scene.scrolls[0].controlKey==0x9876u && scene.scrolls[0].bounds[2]==2,
                "ZSUPIX02 retains exact scroll viewport records after hit records")) return 1;
    if (!Expect(WriteV2ScrollPacket(packetPath,nullptr),"write empty ZSUPIX02 packet") ||
        !Expect(LoadScenePacket(packetPath,&scene,&error) && scene.scrolls.empty(),
                "empty Production ZSUPIX02 packet preserves zero scroll targets")) return 1;
    const float invalidViewport[4]={0,0,0,2};
    if (!Expect(WriteV2ScrollPacket(packetPath,invalidViewport),"write invalid ZSUPIX02 viewport") ||
        !Expect(!LoadScenePacket(packetPath,&scene,&error),"reject empty ZSUPIX02 viewport bounds")) return 1;
    if (!Expect(WriteV2ScrollPacket(packetPath,viewport,true),"write trailing ZSUPIX02 packet") ||
        !Expect(!LoadScenePacket(packetPath,&scene,&error),"reject trailing ZSUPIX02 bytes")) return 1;
    if (!Expect(WriteV2ScrollPacket(packetPath,viewport),"rewrite ZSUPIX02 record packet")) return 1;
    {
        std::ifstream input(packetPath,std::ios::binary|std::ios::ate);
        const auto length=input.tellg();
        input.seekg(0);std::vector<std::uint8_t> bytes(static_cast<std::size_t>(length));
        if (!input.read(reinterpret_cast<char*>(bytes.data()),length)) return 2;
        bytes.pop_back();
        if (!Expect(WriteBytes(packetPath,bytes),"write truncated ZSUPIX02 packet") ||
            !Expect(!LoadScenePacket(packetPath,&scene,&error),"reject truncated ZSUPIX02 scroll record")) return 1;
    }

    if (!retain) {
        DeleteFileW(alphaPath.c_str()); DeleteFileW(rgbaPath.c_str()); DeleteFileW(bcPath.c_str());
        DeleteFileW(bc2Path.c_str()); DeleteFileW(bc3Path.c_str()); DeleteFileW(wrappedPath.c_str());
        DeleteFileW(packetPath.c_str()); DeleteFileW(pngPath.c_str()); DeleteFileW(rgbaPng.c_str()); DeleteFileW(bcPng.c_str());
        DeleteFileW((stem+L"_bc2.png").c_str()); DeleteFileW((stem+L"_bc3.png").c_str());
    }
    CoUninitialize();
    std::printf("PASS|39|D2D/WIC alpha8, RGBA32, BC1/2/3, tint, clip, PNG, and strict ZSUPIX01/02 packet checks\n");
    return 0;
}
