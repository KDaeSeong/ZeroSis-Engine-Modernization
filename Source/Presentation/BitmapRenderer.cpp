#include "BitmapRenderer.h"
#include "SceneLineContract.h"

#include <d3d11.h>

#include <Windows.h>
#include <d2d1.h>
#include <dxgi.h>
#include <wincodec.h>
#include <wrl/client.h>

#include <algorithm>
#include <cmath>
#include <cwchar>
#include <cstring>
#include <fstream>
#include <limits>
#include <map>
#include <sstream>

#pragma comment(lib, "d2d1.lib")
#pragma comment(lib, "windowscodecs.lib")
#pragma comment(lib, "ole32.lib")

namespace ZeroSisPresentation {
namespace {
using Microsoft::WRL::ComPtr;
struct ComScope {
    HRESULT hr=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    ~ComScope() { if (SUCCEEDED(hr)) CoUninitialize(); }
};
constexpr std::uint32_t kMaxDimension = 16384;
constexpr std::uint64_t kMaxPixels = 16ull * 1024ull * 1024ull;
constexpr std::uint64_t kMaxDecodedTextureBytes = 512ull * 1024ull * 1024ull;
constexpr std::uint64_t kMaxPacketBytes = 128ull * 1024ull * 1024ull;
constexpr std::uint32_t kMaxTextures = 4096;
constexpr std::uint32_t kMaxSprites = 500000;
constexpr std::uint32_t kMaxHits = 500000;
constexpr std::uint32_t kMaxScrolls = 500000;
constexpr std::uint32_t kMaxPathBytes = 32768;

void SetError(std::wstring* error, const std::wstring& message) {
    if (error) *error = message;
}

bool Fail(std::wstring* error, const std::wstring& message) {
    SetError(error, message);
    return false;
}

std::wstring HrText(const wchar_t* operation, HRESULT hr) {
    std::wostringstream out;
    out << operation << L" failed (HRESULT 0x" << std::hex << static_cast<unsigned long>(hr) << L")";
    return out.str();
}

bool CheckedImageBytes(std::uint32_t width, std::uint32_t height,
                       std::uint64_t* bytes, std::wstring* error) {
    if (!width || !height || width > kMaxDimension || height > kMaxDimension ||
        static_cast<std::uint64_t>(width) * height > kMaxPixels) {
        return Fail(error, L"Image dimensions exceed renderer limits");
    }
    *bytes = static_cast<std::uint64_t>(width) * height * 4u;
    return true;
}

struct Reader {
    const std::vector<std::uint8_t>& bytes;
    std::size_t position = 0;

    bool Take(std::size_t amount, const std::uint8_t** value) {
        if (amount > bytes.size() - position) return false;
        *value = bytes.data() + position;
        position += amount;
        return true;
    }
    bool U32(std::uint32_t* value) {
        const std::uint8_t* p = nullptr;
        if (!Take(4, &p)) return false;
        *value = static_cast<std::uint32_t>(p[0]) |
                 (static_cast<std::uint32_t>(p[1]) << 8) |
                 (static_cast<std::uint32_t>(p[2]) << 16) |
                 (static_cast<std::uint32_t>(p[3]) << 24);
        return true;
    }
    bool U64(std::uint64_t* value) {
        std::uint32_t lo = 0, hi = 0;
        if (!U32(&lo) || !U32(&hi)) return false;
        *value = static_cast<std::uint64_t>(lo) | (static_cast<std::uint64_t>(hi) << 32);
        return true;
    }
    bool F32(float* value) {
        std::uint32_t bits = 0;
        if (!U32(&bits)) return false;
        std::memcpy(value, &bits, sizeof(bits));
        return std::isfinite(*value);
    }
};

bool Utf8ToWide(const std::uint8_t* bytes, std::uint32_t length,
                std::wstring* result, std::wstring* error) {
    if (!length || length > kMaxPathBytes || std::memchr(bytes, 0, length))
        return Fail(error, L"Texture path is empty, contains NUL, or exceeds the path limit");
    const int required = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS,
                                             reinterpret_cast<const char*>(bytes),
                                             static_cast<int>(length), nullptr, 0);
    if (required <= 0) return Fail(error, L"Texture path is not valid UTF-8");
    std::wstring wide(static_cast<std::size_t>(required), L'\0');
    if (MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS,
                            reinterpret_cast<const char*>(bytes), static_cast<int>(length),
                            &wide[0], required) != required)
        return Fail(error, L"Texture path could not be converted from UTF-8");
    *result = std::move(wide);
    return true;
}

bool ValidRect(const float rect[4], bool positive, bool bounded,
               float maxX, float maxY, const wchar_t* name, std::wstring* error) {
    for (int i = 0; i != 4; ++i) {
        if (!std::isfinite(rect[i])) return Fail(error, std::wstring(name) + L" has a non-finite coordinate");
    }
    if (positive ? !(rect[2] > rect[0] && rect[3] > rect[1])
                 : !(rect[2] >= rect[0] && rect[3] >= rect[1]))
        return Fail(error, std::wstring(name) + L" has inverted or empty bounds");
    for (int i=0;i!=4;++i) if (std::fabs(rect[i])>10000000.0f)
        return Fail(error,std::wstring(name)+L" exceeds coordinate limits");
    if (bounded && (rect[0] < 0.0f || rect[1] < 0.0f || rect[2] > maxX || rect[3] > maxY))
        return Fail(error, std::wstring(name) + L" is outside its texture");
    return true;
}

bool ParseSceneBytes(const std::vector<std::uint8_t>& bytes, const std::wstring& packetPath,
                     Scene* scene, std::wstring* error) {
    if (bytes.size() < 28 || bytes.size() > kMaxPacketBytes)
        return Fail(error, L"Packet size is outside supported limits");
    Reader reader{bytes};
    const std::uint8_t* magic = nullptr;
    if (!reader.Take(8, &magic)) return Fail(error,L"Truncated packet magic");
    const bool version2=std::memcmp(magic,"ZSUPIX02",8)==0;
    if (!version2 && std::memcmp(magic,"ZSUPIX01",8)!=0)
        return Fail(error,L"Packet magic is not ZSUPIX01 or ZSUPIX02");
    std::uint32_t width=0,height=0,textureCount=0,spriteCount=0,hitCount=0,scrollCount=0;
    if (!reader.U32(&width) || !reader.U32(&height) || !reader.U32(&textureCount) ||
        !reader.U32(&spriteCount) || !reader.U32(&hitCount))
        return Fail(error, L"Truncated packet header");
    if (version2 && !reader.U32(&scrollCount))
        return Fail(error,L"Truncated ZSUPIX02 scroll record count");
    std::uint64_t pixelBytes=0;
    if (!CheckedImageBytes(width,height,&pixelBytes,error)) return false;
    if (textureCount > kMaxTextures || spriteCount > kMaxSprites || hitCount > kMaxHits || scrollCount > kMaxScrolls)
        return Fail(error, L"Packet record count exceeds renderer limits");
    Scene parsed{};
    parsed.width=width; parsed.height=height;
    parsed.textures.reserve(textureCount);
    const std::size_t packetSlash=packetPath.find_last_of(L"\\/");
    const std::wstring packetDirectory=packetSlash==std::wstring::npos ? L"" : packetPath.substr(0,packetSlash+1);
    for (std::uint32_t i=0;i<textureCount;++i) {
        std::uint32_t length=0; const std::uint8_t* raw=nullptr; std::wstring path;
        if (!reader.U32(&length) || length > kMaxPathBytes || !reader.Take(length,&raw))
            return Fail(error, L"Truncated or oversized texture path");
        if (!Utf8ToWide(raw,length,&path,error)) return false;
        const bool absolute=(path.size()>=2 && path[1]==L':') ||
                            (path.size()>=2 && (path[0]==L'\\' || path[0]==L'/') && path[1]==L'\\');
        parsed.textures.push_back({absolute ? path : packetDirectory+path});
    }
    parsed.sprites.reserve(spriteCount);
    for (std::uint32_t i=0;i<spriteCount;++i) {
        Sprite s{};
        if (!reader.U32(&s.textureIndex) || !reader.U64(&s.controlKey))
            return Fail(error, L"Truncated sprite record");
        float* fields[]={s.sourceRect,s.targetRect,s.clipRect,s.tintRGBA};
        for (float* field:fields) for (int n=0;n!=4;++n)
            if (!reader.F32(&field[n])) return Fail(error,L"Sprite contains a truncated or non-finite float");
        if (!ValidRect(s.targetRect,true,false,0,0,L"Sprite target",error) ||
            !ValidRect(s.clipRect,false,false,0,0,L"Sprite clip",error)) return false;
        for (float value:s.tintRGBA) if (value<0.0f || value>1.0f)
            return Fail(error,L"Sprite tint is outside [0,1]");
        if (s.textureIndex==kSolidRectangleTexture) {
            if (!ValidRect(s.sourceRect,false,false,0,0,L"Solid source",error)) return false;
        } else {
            if (s.textureIndex>=textureCount) return Fail(error,L"Sprite references a missing texture");
            if (!ValidRect(s.sourceRect,true,false,0,0,L"Sprite source",error)) return false;
        }
        parsed.sprites.push_back(s);
    }
    parsed.hits.reserve(hitCount);
    for (std::uint32_t i=0;i<hitCount;++i) {
        HitRecord h{};
        if (!reader.U64(&h.controlKey)) return Fail(error,L"Truncated hit record");
        for (float& value:h.bounds) if (!reader.F32(&value)) return Fail(error,L"Invalid hit bounds");
        if (!ValidRect(h.bounds,true,false,0,0,L"Hit bounds",error)) return false;
        parsed.hits.push_back(h);
    }
    parsed.scrolls.reserve(scrollCount);
    for (std::uint32_t i=0;i<scrollCount;++i) {
        HitRecord h{};
        if (!reader.U64(&h.controlKey)) return Fail(error,L"Truncated scroll record");
        for (float& value:h.bounds) if (!reader.F32(&value)) return Fail(error,L"Invalid scroll bounds");
        if (!ValidRect(h.bounds,true,false,0,0,L"Scroll bounds",error)) return false;
        parsed.scrolls.push_back(h);
    }
    if (reader.position!=bytes.size()) return Fail(error,L"Packet has trailing bytes");
    *scene=std::move(parsed);
    return true;
}

std::uint32_t ReadU32(const std::uint8_t* p) {
    return static_cast<std::uint32_t>(p[0]) | (static_cast<std::uint32_t>(p[1])<<8) |
           (static_cast<std::uint32_t>(p[2])<<16) | (static_cast<std::uint32_t>(p[3])<<24);
}

struct DecodedTexture {
    std::uint32_t width=0,height=0;
    std::vector<std::uint8_t> bgra;
};

bool DecodeUncompressedDds(const std::wstring& path, DecodedTexture* out,
                           bool* handled, std::wstring* error) {
    *handled=false;
    std::ifstream file(path,std::ios::binary|std::ios::ate);
    if (!file) return Fail(error,L"Could not open DDS texture");
    const std::streamoff end=file.tellg();
    if (end<128 || static_cast<std::uint64_t>(end)>kMaxPacketBytes) {
        *handled=true;
        return Fail(error,L"DDS texture size is invalid or exceeds limits");
    }
    std::vector<std::uint8_t> data(static_cast<std::size_t>(end)); file.seekg(0);
    if (!file.read(reinterpret_cast<char*>(data.data()),static_cast<std::streamsize>(data.size()))) {
        *handled=true;
        return Fail(error,L"Could not read DDS texture bytes");
    }
    if (std::memcmp(data.data(),"DDS ",4)!=0) return true;
    *handled=true;
    if (ReadU32(data.data()+4)!=124 || ReadU32(data.data()+76)!=32)
        return Fail(error,L"DDS header is malformed");
    const std::uint32_t height=ReadU32(data.data()+12), width=ReadU32(data.data()+16);
    const std::uint32_t flags=ReadU32(data.data()+8), pfFlags=ReadU32(data.data()+80),
        fourCC=ReadU32(data.data()+84), bits=ReadU32(data.data()+88);
    // Firaxis FTXT atlases carry proprietary markers in legacy reserved/caps fields.
    // They must be reconstructed as standard DDS before entering this renderer.
    const char privateTag[]="FTXTInterface";
    for (std::size_t i=28;i+sizeof(privateTag)-1<=72;++i)
        if (std::memcmp(data.data()+i,privateTag,sizeof(privateTag)-1)==0)
            return Fail(error,L"Firaxis FTXT texture wrapper is unsupported; provide a standard DDS");
    if ((std::memcmp(data.data()+116,"BC001",5)==0 || std::memcmp(data.data()+116,"BC002",5)==0) ||
        (std::memcmp(data.data()+120,"BC001",5)==0 || std::memcmp(data.data()+120,"BC002",5)==0))
        return Fail(error,L"Firaxis BC00x texture wrapper is unsupported; provide a standard DDS");
    const bool alphaOnly=(pfFlags&0x2u) && !(pfFlags&0x4u) && fourCC==0 && bits==8;
    const bool rgba32=(pfFlags&0x40u) && !(pfFlags&0x4u) && fourCC==0 && bits==32;
    const bool legacyBc=(pfFlags&0x4u) &&
        (fourCC==0x31545844u || fourCC==0x33545844u || fourCC==0x35545844u); // DXT1/3/5
    if (!alphaOnly && !rgba32) {
        if (legacyBc) { *handled=false; return true; }
        if ((pfFlags&0x4u) && fourCC==0x30315844u) { // DX10 extension, 'DX10'
            if (data.size()<148) return Fail(error,L"DDS DX10 extension header is truncated");
            const std::uint32_t format=ReadU32(data.data()+128), dimension=ReadU32(data.data()+132),
                misc=ReadU32(data.data()+136), arraySize=ReadU32(data.data()+140);
            if (dimension!=3 || arraySize!=1 || (misc&0x4u))
                return Fail(error,L"DDS DX10 arrays/cubemaps/non-2D resources are unsupported");
            if (format==71 || format==74 || format==77) { *handled=false; return true; } // BC1/2/3 UNORM
            return Fail(error,L"DDS DX10 format is unsupported; only BC1/2/3 UNORM are accepted");
        }
        return Fail(error,L"DDS encoding is unsupported; only alpha8, RGBA32, and WIC BC1/2/3 are accepted");
    }
    std::uint64_t rgbaBytes=0;
    if (!CheckedImageBytes(width,height,&rgbaBytes,error)) return false;
    out->width=width; out->height=height; out->bgra.resize(static_cast<std::size_t>(rgbaBytes));
    const std::uint32_t alphaPitch=ReadU32(data.data()+20);
    if (alphaOnly) {
        const std::uint64_t row= (flags&0x8u) ? alphaPitch : width;
        if (row<width || row*height!=data.size()-128)
            return Fail(error,L"DDS alpha plane length/pitch does not match its dimensions");
        for (std::uint32_t y=0;y<height;++y) for (std::uint32_t x=0;x<width;++x) {
            const std::uint8_t a=data[128+static_cast<std::size_t>(y*row+x)];
            const std::size_t at=(static_cast<std::size_t>(y)*width+x)*4;
            out->bgra[at+0]=a; out->bgra[at+1]=a; out->bgra[at+2]=a; out->bgra[at+3]=a;
        }
        return true;
    }
    const std::uint32_t masks[4]={ReadU32(data.data()+92),ReadU32(data.data()+96),ReadU32(data.data()+100),ReadU32(data.data()+104)};
    int shifts[4]={0,0,0,0};
    for (int c=0;c!=4;++c) {
        if (c==3 && masks[c]==0) continue;
        if (!masks[c]) return Fail(error,L"DDS RGBA32 channel mask is empty");
        while (((masks[c]>>shifts[c])&1u)==0) ++shifts[c];
        if (masks[c]>>shifts[c] != 0xffu) return Fail(error,L"DDS RGBA32 channels must be 8-bit");
    }
    for (int a=0;a!=4;++a) for (int b=a+1;b!=4;++b)
        if (masks[a] && masks[b] && (masks[a]&masks[b])) return Fail(error,L"DDS RGBA32 masks overlap");
    if (!masks[0] || !masks[1] || !masks[2]) return Fail(error,L"DDS RGBA32 is missing an RGB channel");
    const std::uint64_t row=(flags&0x8u) ? alphaPitch : static_cast<std::uint64_t>(width)*4u;
    if (row<static_cast<std::uint64_t>(width)*4u || row*height!=data.size()-128)
        return Fail(error,L"DDS RGBA32 length/pitch does not match its dimensions");
    for (std::uint32_t y=0;y<height;++y) for (std::uint32_t x=0;x<width;++x) {
        const std::uint32_t pixel=ReadU32(data.data()+128+static_cast<std::size_t>(y*row+x*4u));
        std::uint8_t channel[4]={};
        for (int c=0;c!=4;++c) channel[c]=masks[c] ? static_cast<std::uint8_t>((pixel&masks[c])>>shifts[c]) : 255;
        const std::uint8_t a=channel[3]; const std::size_t at=(static_cast<std::size_t>(y)*width+x)*4;
        out->bgra[at+0]=static_cast<std::uint8_t>((static_cast<unsigned>(channel[2])*a+127u)/255u);
        out->bgra[at+1]=static_cast<std::uint8_t>((static_cast<unsigned>(channel[1])*a+127u)/255u);
        out->bgra[at+2]=static_cast<std::uint8_t>((static_cast<unsigned>(channel[0])*a+127u)/255u);
        out->bgra[at+3]=a;
    }
    return true;
}

bool DecodeWic(const std::wstring& path, IWICImagingFactory* wic,
               DecodedTexture* out, std::wstring* error) {
    ComPtr<IWICBitmapDecoder> decoder;
    HRESULT hr=wic->CreateDecoderFromFilename(path.c_str(),nullptr,GENERIC_READ,
                                              WICDecodeMetadataCacheOnLoad,&decoder);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC decoder creation",hr));
    ComPtr<IWICBitmapFrameDecode> frame;
    hr=decoder->GetFrame(0,&frame);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC first frame",hr));
    UINT width=0,height=0;
    hr=frame->GetSize(&width,&height);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC image dimensions",hr));
    std::uint64_t byteCount=0;
    if (!CheckedImageBytes(width,height,&byteCount,error)) return false;
    if (byteCount>kMaxDecodedTextureBytes) return Fail(error,L"Decoded texture exceeds memory limit");
    ComPtr<IWICFormatConverter> converter;
    hr=wic->CreateFormatConverter(&converter);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC format converter",hr));
    hr=converter->Initialize(frame.Get(),GUID_WICPixelFormat32bppPBGRA,WICBitmapDitherTypeNone,
                             nullptr,0.0,WICBitmapPaletteTypeCustom);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC conversion to premultiplied BGRA",hr));
    out->width=width; out->height=height; out->bgra.resize(static_cast<std::size_t>(byteCount));
    hr=converter->CopyPixels(nullptr,width*4,static_cast<UINT>(byteCount),out->bgra.data());
    if (FAILED(hr)) return Fail(error,HrText(L"WIC pixel decode",hr));
    return true;
}

bool DecodeTexture(const Texture& texture, IWICImagingFactory* wic,
                   DecodedTexture* out, std::wstring* error) {
    const std::size_t slash=texture.path.find_last_of(L"\\/");
    const std::size_t dot=texture.path.find_last_of(L'.');
    const std::wstring extension=(dot!=std::wstring::npos && (slash==std::wstring::npos || dot>slash)) ? texture.path.substr(dot) : L"";
    if (_wcsicmp(extension.c_str(),L".dds")==0) {
        bool handled=false;
        if (!DecodeUncompressedDds(texture.path,out,&handled,error)) return false;
        if (handled) return true;
    }
    return DecodeWic(texture.path,wic,out,error);
}

struct TintKey {
    std::uint32_t texture;
    std::uint32_t rgba[4];
    bool operator<(const TintKey& other) const {
        if (texture!=other.texture) return texture<other.texture;
        for (int i=0;i!=4;++i) if (rgba[i]!=other.rgba[i]) return rgba[i]<other.rgba[i];
        return false;
    }
};

TintKey MakeTintKey(std::uint32_t texture,const float tint[4]) {
    TintKey key{}; key.texture=texture;
    for (int i=0;i!=4;++i) std::memcpy(&key.rgba[i],&tint[i],sizeof(float));
    return key;
}

bool CreateWicBitmap(IWICImagingFactory* wic,const DecodedTexture& source,
                     const float tint[4],ComPtr<IWICBitmap>* bitmap,
                     std::wstring* error) {
    std::vector<std::uint8_t> pixels=source.bgra;
    for (std::size_t i=0;i<pixels.size();i+=4) {
        const float a=static_cast<float>(pixels[i+3])/255.0f;
        const float factors[3]={tint[2]*tint[3],tint[1]*tint[3],tint[0]*tint[3]};
        for (int c=0;c!=3;++c) {
            const float value=static_cast<float>(pixels[i+c])*factors[c];
            pixels[i+c]=static_cast<std::uint8_t>(std::min(255.0f,std::max(0.0f,std::floor(value+0.5f))));
        }
        pixels[i+3]=static_cast<std::uint8_t>(std::min(255.0f,std::max(0.0f,std::floor(a*tint[3]*255.0f+0.5f))));
    }
    const UINT stride=source.width*4;
    HRESULT hr=wic->CreateBitmapFromMemory(source.width,source.height,GUID_WICPixelFormat32bppPBGRA,
                                          stride,static_cast<UINT>(pixels.size()),pixels.data(),bitmap->GetAddressOf());
    if (FAILED(hr)) return Fail(error,HrText(L"WIC tinted texture creation",hr));
    return true;
}

bool SavePng(IWICImagingFactory* wic,IWICBitmap* bitmap,const std::wstring& path,
             std::wstring* error) {
    ComPtr<IWICStream> stream;
    HRESULT hr=wic->CreateStream(&stream);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG stream",hr));
    hr=stream->InitializeFromFilename(path.c_str(),GENERIC_WRITE);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG output",hr));
    ComPtr<IWICBitmapEncoder> encoder;
    hr=wic->CreateEncoder(GUID_ContainerFormatPng,nullptr,&encoder);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG encoder",hr));
    hr=encoder->Initialize(stream.Get(),WICBitmapEncoderNoCache);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG encoder initialization",hr));
    ComPtr<IWICBitmapFrameEncode> frame; ComPtr<IPropertyBag2> options;
    hr=encoder->CreateNewFrame(&frame,&options);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG frame",hr));
    hr=frame->Initialize(options.Get());
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG frame initialization",hr));
    UINT width=0,height=0;
    hr=bitmap->GetSize(&width,&height);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG source dimensions",hr));
    hr=frame->SetSize(width,height);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG frame size",hr));
    WICPixelFormatGUID format=GUID_WICPixelFormat32bppBGRA;
    hr=frame->SetPixelFormat(&format);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG pixel format",hr));
    if (!IsEqualGUID(format,GUID_WICPixelFormat32bppBGRA))
        return Fail(error,L"WIC PNG encoder did not accept 32-bit BGRA output");
    ComPtr<IWICFormatConverter> converter;
    hr=wic->CreateFormatConverter(&converter);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG converter",hr));
    hr=converter->Initialize(bitmap,GUID_WICPixelFormat32bppBGRA,WICBitmapDitherTypeNone,
                             nullptr,0.0,WICBitmapPaletteTypeCustom);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG straight-alpha conversion",hr));
    hr=frame->WriteSource(converter.Get(),nullptr);
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG pixels",hr));
    hr=frame->Commit();
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG frame commit",hr));
    hr=encoder->Commit();
    if (FAILED(hr)) return Fail(error,HrText(L"WIC PNG commit",hr));
    return true;
}

bool DrawSceneSprites(const Scene& scene,IWICImagingFactory* wic,ID2D1RenderTarget* target,
                      const std::vector<DecodedTexture>& decoded,std::wstring* error) {
    std::map<TintKey,ComPtr<ID2D1Bitmap>> textureCache;
    std::uint64_t tintedCacheBytes=0;
    ComPtr<ID2D1SolidColorBrush> solid;
    HRESULT hr=target->CreateSolidColorBrush(D2D1::ColorF(0,0,0,0),&solid);
    if (FAILED(hr)) return Fail(error,HrText(L"Direct2D solid brush",hr));
    bool drawOk=true;
    return DispatchScenePaint(scene,[&](const Sprite& sprite) {
        const D2D1_RECT_F destination=D2D1::RectF(sprite.targetRect[0],sprite.targetRect[1],sprite.targetRect[2],sprite.targetRect[3]);
        const D2D1_RECT_F clip=D2D1::RectF(sprite.clipRect[0],sprite.clipRect[1],sprite.clipRect[2],sprite.clipRect[3]);
        target->PushAxisAlignedClip(clip,D2D1_ANTIALIAS_MODE_ALIASED);
        if (sprite.textureIndex==kSolidRectangleTexture) {
            solid->SetColor(D2D1::ColorF(sprite.tintRGBA[0],sprite.tintRGBA[1],sprite.tintRGBA[2],sprite.tintRGBA[3]));
            target->FillRectangle(destination,solid.Get());
        } else {
            const std::uint32_t index=sprite.textureIndex;
            if (index>=decoded.size()) { SetError(error,L"Scene sprite references a missing texture"); drawOk=false; }
            else {
                const TintKey key=MakeTintKey(index,sprite.tintRGBA);
                auto found=textureCache.find(key);
                if (found==textureCache.end()) {
                    const std::uint64_t tintBytes=static_cast<std::uint64_t>(decoded[index].bgra.size());
                    if (tintBytes>kMaxDecodedTextureBytes-tintedCacheBytes) {
                        SetError(error,L"Tinted texture cache exceeds aggregate memory limit"); drawOk=false;
                    }
                    ComPtr<IWICBitmap> tinted;
                    if (drawOk && !CreateWicBitmap(wic,decoded[index],sprite.tintRGBA,&tinted,error)) drawOk=false;
                    else if (drawOk) {
                        ComPtr<ID2D1Bitmap> bitmap;
                        hr=target->CreateBitmapFromWicBitmap(tinted.Get(),nullptr,&bitmap);
                        if (FAILED(hr)) { SetError(error,HrText(L"Direct2D texture bitmap",hr)); drawOk=false; }
                        else { found=textureCache.emplace(key,std::move(bitmap)).first; tintedCacheBytes+=tintBytes; }
                    }
                }
                if (drawOk) {
                    const D2D1_RECT_F source=D2D1::RectF(sprite.sourceRect[0],sprite.sourceRect[1],sprite.sourceRect[2],sprite.sourceRect[3]);
                    target->DrawBitmap(found->second.Get(),destination,1.0f,D2D1_BITMAP_INTERPOLATION_MODE_LINEAR,&source);
                }
            }
        }
        target->PopAxisAlignedClip();
        return drawOk;
    },[&](const SceneLine& line) {
        const auto clip=D2D1::RectF(line.clipRect[0],line.clipRect[1],line.clipRect[2],line.clipRect[3]);
        target->PushAxisAlignedClip(clip,D2D1_ANTIALIAS_MODE_ALIASED);
        solid->SetColor(D2D1::ColorF(line.tintRGBA[0],line.tintRGBA[1],line.tintRGBA[2],line.tintRGBA[3]));
        target->DrawLine(D2D1::Point2F(line.start[0],line.start[1]),D2D1::Point2F(line.end[0],line.end[1]),solid.Get(),line.width);
        target->PopAxisAlignedClip();
        return true;
    },error);
}

bool ValidateSceneForRender(const Scene& scene,std::uint64_t* outputBytes,std::wstring* error) {
    if (!CheckedImageBytes(scene.width,scene.height,outputBytes,error)) return false;
    if (!ValidateSceneLines(scene,error)) return false;
    if (scene.textures.size()>kMaxTextures || scene.sprites.size()>kMaxSprites || scene.hits.size()>kMaxHits ||
        scene.scrolls.size()>kMaxScrolls)
        return Fail(error,L"Scene record count exceeds renderer limits");
    for (const Texture& texture:scene.textures) if (texture.path.empty())
        return Fail(error,L"Scene contains an empty texture path");
    for (const HitRecord& hit:scene.hits) if (!ValidRect(hit.bounds,true,false,0,0,L"Hit bounds",error)) return false;
    for (const HitRecord& hit:scene.scrolls) if (!ValidRect(hit.bounds,true,false,0,0,L"Scroll bounds",error)) return false;
    for (const Sprite& sprite:scene.sprites) {
        if (!ValidRect(sprite.targetRect,true,false,0,0,L"Sprite target",error) ||
            !ValidRect(sprite.clipRect,false,false,0,0,L"Sprite clip",error)) return false;
        for (float value:sprite.tintRGBA) if (!std::isfinite(value) || value<0.0f || value>1.0f)
            return Fail(error,L"Sprite tint is outside [0,1]");
        if (sprite.textureIndex==kSolidRectangleTexture) {
            if (!ValidRect(sprite.sourceRect,false,false,0,0,L"Solid source",error)) return false;
        } else if (sprite.textureIndex>=scene.textures.size()) {
            return Fail(error,L"Scene sprite references a missing texture");
        }
    }
    return true;
}

bool DecodeSceneTextures(const Scene& scene,IWICImagingFactory* wic,
                         std::vector<DecodedTexture>* decoded,std::wstring* error) {
    decoded->resize(scene.textures.size());
    std::uint64_t decodedTotal=0;
    for (std::size_t i=0;i<scene.textures.size();++i) {
        if (!DecodeTexture(scene.textures[i],wic,&(*decoded)[i],error)) return false;
        const std::uint64_t bytes=static_cast<std::uint64_t>((*decoded)[i].bgra.size());
        if (bytes>kMaxDecodedTextureBytes-decodedTotal)
            return Fail(error,L"Decoded texture cache exceeds aggregate memory limit");
        decodedTotal+=bytes;
    }
    for (const Sprite& sprite:scene.sprites) if (sprite.textureIndex!=kSolidRectangleTexture) {
        const DecodedTexture& texture=(*decoded)[sprite.textureIndex];
        if (!ValidRect(sprite.sourceRect,true,true,static_cast<float>(texture.width),
                       static_cast<float>(texture.height),L"Sprite source",error)) return false;
    }
    return true;
}
} // namespace

bool LoadScenePacket(const std::wstring& packetPath, Scene* scene, std::wstring* error) {
    if (!scene) return Fail(error,L"Scene output pointer is null");
    std::ifstream file(packetPath,std::ios::binary|std::ios::ate);
    if (!file) return Fail(error,L"Could not open scene packet");
    const std::streamoff end=file.tellg();
    if (end<0 || static_cast<std::uint64_t>(end)>kMaxPacketBytes)
        return Fail(error,L"Scene packet exceeds the supported size");
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(end)); file.seekg(0);
    if (!bytes.empty() && !file.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(bytes.size())))
        return Fail(error,L"Could not read scene packet");
    return ParseSceneBytes(bytes,packetPath,scene,error);
}

bool RenderToPng(const Scene& scene,const std::wstring& pngPath,std::wstring* error) {
    std::uint64_t outputBytes=0;
    if (!ValidateSceneForRender(scene,&outputBytes,error)) return false;
    HRESULT hr=CoInitializeEx(nullptr,COINIT_APARTMENTTHREADED);
    const bool uninitialize=SUCCEEDED(hr);
    if (FAILED(hr) && hr!=RPC_E_CHANGED_MODE) return Fail(error,HrText(L"COM initialization",hr));
    bool result=false;
    do {
        ComPtr<IWICImagingFactory> wic;
        hr=CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&wic));
        if (FAILED(hr)) { SetError(error,HrText(L"WIC factory",hr)); break; }
        ComPtr<ID2D1Factory> d2d;
        const D2D1_FACTORY_OPTIONS factoryOptions={};
        hr=D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED,factoryOptions,d2d.GetAddressOf());
        if (FAILED(hr)) { SetError(error,HrText(L"Direct2D factory",hr)); break; }
        ComPtr<IWICBitmap> targetBitmap;
        hr=wic->CreateBitmap(scene.width,scene.height,GUID_WICPixelFormat32bppPBGRA,
                             WICBitmapCacheOnLoad,&targetBitmap);
        if (FAILED(hr)) { SetError(error,HrText(L"WIC output bitmap",hr)); break; }
        D2D1_RENDER_TARGET_PROPERTIES props=D2D1::RenderTargetProperties(
            D2D1_RENDER_TARGET_TYPE_SOFTWARE,
            D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_PREMULTIPLIED),
            96.0f,96.0f,D2D1_RENDER_TARGET_USAGE_NONE,D2D1_FEATURE_LEVEL_DEFAULT);
        ComPtr<ID2D1RenderTarget> target;
        hr=d2d->CreateWicBitmapRenderTarget(targetBitmap.Get(),props,&target);
        if (FAILED(hr)) { SetError(error,HrText(L"Direct2D WIC render target",hr)); break; }

        std::vector<DecodedTexture> decoded;
        if (!DecodeSceneTextures(scene,wic.Get(),&decoded,error)) break;
        target->BeginDraw();
        target->Clear(D2D1::ColorF(0,0,0,0));
        const bool drawOk=DrawSceneSprites(scene,wic.Get(),target.Get(),decoded,error);
        hr=target->EndDraw();
        if (!drawOk) break;
        if (FAILED(hr)) { SetError(error,HrText(L"Direct2D EndDraw",hr)); break; }
        result=SavePng(wic.Get(),targetBitmap.Get(),pngPath,error);
    } while (false);
    if (uninitialize) CoUninitialize();
    return result;
}

static bool RenderSceneToTextureImpl(const Scene& scene,ID3D11Device* device,
                                     ID3D11DeviceContext* context,ID3D11Texture2D* targetTexture,
                                     bool clear,std::wstring* error) {
    std::uint64_t outputBytes=0;
    if (!ValidateSceneForRender(scene,&outputBytes,error)) return false;
    if (!device || !context || !targetTexture) return Fail(error,L"D3D11 scene target arguments are null");
    if (context->GetType()!=D3D11_DEVICE_CONTEXT_IMMEDIATE)
        return Fail(error,L"D3D11 scene composition requires the immediate context");
    ComPtr<ID3D11Device> contextDevice;
    context->GetDevice(&contextDevice);
    if (contextDevice.Get()!=device) return Fail(error,L"D3D11 context belongs to a different device");
    ComPtr<ID3D11Device> targetDevice;
    targetTexture->GetDevice(&targetDevice);
    if (targetDevice.Get()!=device) return Fail(error,L"D3D11 target belongs to a different device");
    D3D11_TEXTURE2D_DESC desc{};
    targetTexture->GetDesc(&desc);
    if (desc.Width!=scene.width || desc.Height!=scene.height || desc.MipLevels!=1 || desc.ArraySize!=1 ||
        desc.SampleDesc.Count!=1 || desc.Format!=DXGI_FORMAT_B8G8R8A8_UNORM ||
        !(desc.BindFlags&D3D11_BIND_RENDER_TARGET))
        return Fail(error,L"D3D11 scene target must be matching single-sample BGRA8 render-target texture");
    ComPtr<IDXGISurface> surface;
    HRESULT hr=targetTexture->QueryInterface(IID_PPV_ARGS(&surface));
    if (FAILED(hr)) return Fail(error,HrText(L"D3D11 target DXGI surface",hr));
    ComScope apartment;
    hr=apartment.hr;
    if (FAILED(hr) && hr!=RPC_E_CHANGED_MODE) return Fail(error,HrText(L"COM initialization",hr));
    bool result=false;
    do {
        ComPtr<IWICImagingFactory> wic;
        hr=CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&wic));
        if (FAILED(hr)) { SetError(error,HrText(L"WIC factory",hr)); break; }
        ComPtr<ID2D1Factory> d2d;
        const D2D1_FACTORY_OPTIONS factoryOptions={};
        hr=D2D1CreateFactory(D2D1_FACTORY_TYPE_SINGLE_THREADED,factoryOptions,d2d.GetAddressOf());
        if (FAILED(hr)) { SetError(error,HrText(L"Direct2D factory",hr)); break; }
        D2D1_RENDER_TARGET_PROPERTIES props=D2D1::RenderTargetProperties(
            D2D1_RENDER_TARGET_TYPE_DEFAULT,
            D2D1::PixelFormat(DXGI_FORMAT_B8G8R8A8_UNORM,D2D1_ALPHA_MODE_PREMULTIPLIED),
            96.0f,96.0f,D2D1_RENDER_TARGET_USAGE_NONE,D2D1_FEATURE_LEVEL_DEFAULT);
        ComPtr<ID2D1RenderTarget> target;
        hr=d2d->CreateDxgiSurfaceRenderTarget(surface.Get(),props,&target);
        if (FAILED(hr)) { SetError(error,HrText(L"Direct2D D3D11 surface target",hr)); break; }
        std::vector<DecodedTexture> decoded;
        if (!DecodeSceneTextures(scene,wic.Get(),&decoded,error)) break;
        target->BeginDraw();
        if (clear) target->Clear(D2D1::ColorF(0,0,0,0));
        const bool drawOk=DrawSceneSprites(scene,wic.Get(),target.Get(),decoded,error);
        hr=target->EndDraw();
        if (!drawOk) break;
        if (FAILED(hr)) { SetError(error,HrText(L"Direct2D D3D11 surface EndDraw",hr)); break; }
        result=true;
    } while(false);
    return result;
}

bool RenderSceneToD3D11Texture(const Scene& scene,ID3D11Device* device,
                               ID3D11DeviceContext* context,ID3D11Texture2D* target,
                               std::wstring* error) {
    return RenderSceneToTextureImpl(scene,device,context,target,true,error);
}

bool OverlaySceneOnD3D11Texture(const Scene& scene,ID3D11Device* device,
                                ID3D11DeviceContext* context,ID3D11Texture2D* target,
                                std::wstring* error) {
    return RenderSceneToTextureImpl(scene,device,context,target,false,error);
}

bool CaptureD3D11TextureToPng(ID3D11Device* device,ID3D11DeviceContext* context,
                             ID3D11Texture2D* texture,const std::wstring& png,
                             std::wstring* error) {
    if (!device || !context || !texture || png.empty()) return Fail(error,L"GPU capture arguments are null or empty");
    ComPtr<ID3D11Device> contextDevice,textureDevice;
    context->GetDevice(&contextDevice);texture->GetDevice(&textureDevice);
    if (contextDevice.Get()!=device || textureDevice.Get()!=device ||
        context->GetType()!=D3D11_DEVICE_CONTEXT_IMMEDIATE)
        return Fail(error,L"GPU capture requires one device and its immediate context");
    D3D11_TEXTURE2D_DESC desc{};texture->GetDesc(&desc);
    std::uint64_t bytes=0;
    if (!CheckedImageBytes(desc.Width,desc.Height,&bytes,error)) return false;
    if (desc.Format!=DXGI_FORMAT_B8G8R8A8_UNORM || desc.MipLevels!=1 || desc.ArraySize!=1 ||
        desc.SampleDesc.Count!=1) return Fail(error,L"GPU capture requires a single BGRA8 surface");
    std::vector<std::uint8_t> pixels;
    try { pixels.resize(static_cast<std::size_t>(bytes)); }
    catch (const std::bad_alloc&) { return Fail(error,L"Could not allocate GPU capture pixels"); }
    desc.Usage=D3D11_USAGE_STAGING;desc.BindFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;desc.MiscFlags=0;
    ComPtr<ID3D11Texture2D> staging;
    HRESULT hr=device->CreateTexture2D(&desc,nullptr,&staging);
    if (FAILED(hr)) return Fail(error,HrText(L"GPU capture staging texture",hr));
    context->CopyResource(staging.Get(),texture);
    D3D11_MAPPED_SUBRESOURCE mapped{};
    hr=context->Map(staging.Get(),0,D3D11_MAP_READ,0,&mapped);
    if (FAILED(hr)) return Fail(error,HrText(L"GPU capture readback",hr));
    for (UINT y=0;y<desc.Height;++y)
        std::memcpy(pixels.data()+static_cast<std::size_t>(y)*desc.Width*4,
                    static_cast<const std::uint8_t*>(mapped.pData)+static_cast<std::size_t>(y)*mapped.RowPitch,desc.Width*4);
    context->Unmap(staging.Get(),0);
    ComScope apartment;
    if (FAILED(apartment.hr) && apartment.hr!=RPC_E_CHANGED_MODE)
        return Fail(error,HrText(L"GPU capture COM initialization",apartment.hr));
    ComPtr<IWICImagingFactory> wic;
    hr=CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,IID_PPV_ARGS(&wic));
    if (FAILED(hr)) return Fail(error,HrText(L"GPU capture WIC factory",hr));
    ComPtr<IWICBitmap> bitmap;
    hr=wic->CreateBitmapFromMemory(desc.Width,desc.Height,GUID_WICPixelFormat32bppPBGRA,
        desc.Width*4,static_cast<UINT>(pixels.size()),pixels.data(),&bitmap);
    if (FAILED(hr)) return Fail(error,HrText(L"GPU capture WIC bitmap",hr));
    HANDLE file=CreateFileW(png.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if (file==INVALID_HANDLE_VALUE) return Fail(error,L"GPU capture destination already exists or cannot be created");
    CloseHandle(file);
    if (!SavePng(wic.Get(),bitmap.Get(),png,error)) { DeleteFileW(png.c_str());return false; }
    return true;
}

} // namespace ZeroSisPresentation

#ifdef ZEROSIS_BITMAP_RENDERER_CLI
#include <iostream>
int wmain(int argc,wchar_t** argv) {
    using namespace ZeroSisPresentation;
    if (argc!=3) {
        std::wcerr << L"usage: BitmapRenderer.exe <scene.packet> <output.png>\n";
        return 2;
    }
    Scene scene{}; std::wstring error;
    if (!LoadScenePacket(argv[1],&scene,&error)) {
        std::wcerr << L"error: " << error << L"\n"; return 1;
    }
    if (!RenderToPng(scene,argv[2],&error)) {
        std::wcerr << L"error: " << error << L"\n"; return 1;
    }
    std::wcout << L"BITMAP_RENDER_PASS width=" << scene.width << L" height=" << scene.height
               << L" sprites=" << scene.sprites.size() << L" textures=" << scene.textures.size()
               << L" hits=" << scene.hits.size() << L" scope=OFFSCREEN_D2D_WIC\n";
    return 0;
}
#endif
