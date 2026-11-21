#pragma once
#include "MenuFrontEndAssets.h"
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <cstdio>
#include <limits>
#include <set>
using namespace ZeroSisHost;
using ZeroSisPresentation::Scene;
inline std::vector<unsigned char> Read(const std::wstring& path){
    std::ifstream file(path,std::ios::binary|std::ios::ate);if(!file)throw std::runtime_error("Fixture file missing");
    const auto size=file.tellg();if(size<0 || size>16*1024*1024)throw std::runtime_error("Fixture file exceeds bound");
    std::vector<unsigned char> data(static_cast<std::size_t>(size));file.seekg(0);file.read(reinterpret_cast<char*>(data.data()),static_cast<std::streamsize>(data.size()));return data;
}
inline std::uint32_t U32(const std::vector<unsigned char>& data,std::size_t& pos){
    if(pos>data.size() || data.size()-pos<4)throw std::runtime_error("Fixture packet truncated");
    std::uint32_t value;std::memcpy(&value,data.data()+pos,4);pos+=4;return value;
}
inline std::wstring Widen(const std::string& text){
    const int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),nullptr,0);
    if(size<=0)throw std::runtime_error("Fixture UTF-8 conversion failed");std::wstring result(static_cast<std::size_t>(size),0);
    MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),&result[0],size);return result;
}
inline std::string Narrow(const std::wstring& text){
    const int size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),nullptr,0,nullptr,nullptr);
    if(size<=0)throw std::runtime_error("Fixture UTF-16 conversion failed");std::string result(static_cast<std::size_t>(size),0);
    WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),&result[0],size,nullptr,nullptr);return result;
}
namespace ZeroSisPresentation {
// File-only fixture replacement for the presentation library's external packet
// loader. No WIC, D2D, D3D, HWND, Host or SDK library is linked or loaded.
inline bool LoadScenePacket(const std::wstring& path,Scene* result,std::wstring*){
    const auto data=Read(path);if(data.size()<32 || std::memcmp(data.data(),"ZSUPIX02",8))return false;
    std::size_t pos=8;Scene scene{};scene.width=U32(data,pos);scene.height=U32(data,pos);
    const auto textures=U32(data,pos),sprites=U32(data,pos),hits=U32(data,pos),scrolls=U32(data,pos);
    if(textures>64 || sprites>10000 || hits || scrolls)return false;
    const auto parent=path.substr(0,path.find_last_of(L"\\/"));
    for(std::uint32_t n=0;n<textures;++n){const auto length=U32(data,pos);if(length>4096 || length>data.size()-pos)return false;
        const auto name=Widen(std::string(reinterpret_cast<const char*>(data.data()+pos),length));pos+=length;scene.textures.push_back({parent+L"\\"+name});}
    for(std::uint32_t n=0;n<sprites;++n){
        if(data.size()-pos<76)return false;Sprite sprite{};sprite.textureIndex=U32(data,pos);const auto low=U32(data,pos);sprite.controlKey=low|(std::uint64_t(U32(data,pos))<<32);
        std::memcpy(sprite.sourceRect,data.data()+pos,64);pos+=64;scene.sprites.push_back(sprite);
    }
    if(pos!=data.size())return false;*result=std::move(scene);return true;
}
}
