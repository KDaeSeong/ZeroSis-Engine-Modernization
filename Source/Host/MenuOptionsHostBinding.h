#pragma once
#include "MenuOptionsStore.h"
#include <cstdlib>
#include <cstring>
#include <cwchar>
#include <memory>
#include <string>

namespace ZeroSisHost {

inline std::wstring HostMenuOptionsDirectory(){
    wchar_t executable[32768]{};
    const DWORD size=GetModuleFileNameW(nullptr,executable,32768);
    if(!size || size>=32768)throw std::runtime_error("Cannot locate private Host options");
    const std::wstring path(executable,size);const auto split=path.find_last_of(L'\\');
    if(split==std::wstring::npos)throw std::runtime_error("Private Host executable has no parent directory");
    return path.substr(0,split);
}

// One canonical session/store is shared by the SDK-free front end and in-game
// options. The audio factory constructs an owner but does not start playback.
template<class Host,class AudioFactory>
void EnsureHostMenuOptions(Host& host,const std::wstring& ownedDirectory,const AudioFactory& audioFactory){
    if(host.menuOptions){
        if(!host.menuOptionsStore || !host.uiAudio)throw std::logic_error("Private options binding is incomplete");
        if(_wcsicmp(host.menuOptionsStore->Path().c_str(),(ownedDirectory+L"\\menu-options.zssettings").c_str())!=0)
            throw std::logic_error("Private options cannot switch their owned directory");
        return;
    }
    if(host.menuOptionsStore)throw std::logic_error("Private option store exists without its session");
    auto store=std::make_shared<MenuOptionsStore>(ownedDirectory);
    bool initialized=host.policyInfoInitialized,policyInfo=host.policyInfo;
    if(!initialized){
        const char* policy=std::getenv("ZEROSIS_UI_POLICY_INFO");
        if(policy){
            if(std::strcmp(policy,"0")!=0 && std::strcmp(policy,"1")!=0)
                throw std::invalid_argument("PolicyInfo seed must be an explicit boolean");
            policyInfo=policy[0]=='1';initialized=true;
        }
    }
    auto initial=store->Read();
    if(store->SchemaVersion()<2)initial.policyInfo=policyInfo;
    else {policyInfo=initial.policyInfo;initialized=true;}
    MenuOptionsCapabilities caps;caps.noBasicHelp=true;caps.uiCueVolume=true;caps.policyInfo=initialized;
    caps.windowResolution=true;caps.fullscreen=true;caps.vsync=true;caps.noRewardPopups=true;
    auto session=std::make_shared<MenuOptionsSession>(initial,caps);
    auto audio=host.uiAudio?host.uiAudio:audioFactory();
    if(!audio)throw std::logic_error("Private menu options require an owned UI audio provider");
    session->BindNoRewardPopupsSnapshot(host.noRewardPopupsCommitted);
    host.noRewardPopupsApplied=initial.noRewardPopups;
    host.policyInfo=policyInfo;host.policyInfoInitialized=initialized;
    host.uiAudio=std::move(audio);host.menuOptionsStore=std::move(store);host.menuOptions=std::move(session);
}

inline std::string HostMenuDisplayError(const std::wstring& value){
    if(value.empty())return "Cannot apply private menu display settings";
    if(value.size()>32768)throw std::runtime_error("Menu display error exceeds its bound");
    const int length=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,value.data(),static_cast<int>(value.size()),nullptr,0,nullptr,nullptr);
    if(length<=0)return "Cannot encode private menu display error";
    std::string result(static_cast<std::size_t>(length),'\0');
    if(WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,value.data(),static_cast<int>(value.size()),&result[0],length,nullptr,nullptr)!=length)
        throw std::runtime_error("Menu display error conversion was incomplete");
    return result;
}

// Window is the actual BitmapWindow in production. SDK-free fixtures exercise
// the same readback/rollback contract without constructing an HWND or device.
template<class Host,class Window>
MenuOptionsValues ApplyHostMenuOptions(Host& host,Window& window,const MenuOptionsValues& value){
    MenuOptionsValues::Validate(value);
    if(!host.uiAudio)throw std::logic_error("Private options require an owned UI audio provider");
    const typename Window::DisplaySettings requested{static_cast<std::uint32_t>(value.windowWidth),
        static_cast<std::uint32_t>(value.windowHeight),value.fullscreen,value.vsync};
    typename Window::DisplaySettings actual{};std::wstring why;
    if(!window.ApplyDisplaySettings(requested,&actual,&why))throw std::runtime_error(HostMenuDisplayError(why));
    host.uiAudio->SetVolumePercent(static_cast<unsigned>(value.uiCueVolumePercent));
    host.policyInfo=value.policyInfo;host.policyInfoInitialized=true;
    host.noRewardPopupsApplied=value.noRewardPopups;
    auto result=value;result.windowWidth=static_cast<int>(actual.width);result.windowHeight=static_cast<int>(actual.height);
    result.fullscreen=actual.fullscreen;result.vsync=actual.vsync;
    result.uiCueVolumePercent=static_cast<int>(host.uiAudio->VolumePercent());result.policyInfo=host.policyInfo;
    result.noRewardPopups=host.noRewardPopupsApplied;
    return result;
}

} // namespace ZeroSisHost
