#include "MenuOptionsHostBinding.h"
#include <filesystem>
#include <fstream>
#include <iostream>
#include <thread>
using namespace ZeroSisHost;
namespace fs=std::filesystem;
struct Audio final {unsigned volume=100;void SetVolumePercent(unsigned v){if(v>100)throw std::runtime_error("volume");volume=v;}unsigned VolumePercent()const{return volume;}};
struct Host final {std::shared_ptr<MenuOptionsSession> menuOptions;std::shared_ptr<MenuOptionsStore> menuOptionsStore;std::shared_ptr<Audio> uiAudio;bool policyInfoInitialized=true,policyInfo=true;
    const std::shared_ptr<std::atomic<bool>> noRewardPopupsCommitted=std::make_shared<std::atomic<bool>>(false);bool noRewardPopupsApplied=false;};
struct Window final {
    struct DisplaySettings {std::uint32_t width=1280,height=720;bool fullscreen=false,vsync=true;};
    DisplaySettings state;bool fail=false,mismatch=false;int calls=0;
    bool ApplyDisplaySettings(const DisplaySettings& requested,DisplaySettings* actual,std::wstring* error){
        ++calls;if(fail){*error=L"display failed";return false;}state=requested;*actual=state;if(mismatch)actual->width=999;return true;
    }
};
int checks=0;void Check(bool ok){++checks;if(!ok)throw std::runtime_error("Host option binding assertion failed");}
template<class F>void Reject(F f){bool rejected=false;try{f();}catch(const std::exception&){rejected=true;}Check(rejected);}
std::string Read(const fs::path& p){std::ifstream f(p,std::ios::binary);return {std::istreambuf_iterator<char>(f),{}};}
int wmain(int argc,wchar_t** argv){
    if(argc!=2)return 2;fs::path root=argv[1];if(!fs::is_empty(root))return 3;
    const auto create=[]{return std::make_shared<Audio>();};
    {
        Host h;Window w;EnsureHostMenuOptions(h,root.wstring(),create);Check(h.menuOptions && h.menuOptionsStore && h.uiAudio);
        const auto store=h.menuOptionsStore;const auto model=h.menuOptions;const auto audio=h.uiAudio;
        EnsureHostMenuOptions(h,root.wstring(),create);Check(h.menuOptions==model && h.menuOptionsStore==store && h.uiAudio==audio);
        Reject([&]{EnsureHostMenuOptions(h,(root/L"different").wstring(),create);});
        Check(h.menuOptions->Committed().policyInfo);Check(h.menuOptionsStore->SchemaVersion()==0);
        Check(!fs::exists(root/L"menu-options.zssettings"));
        h.menuOptions->Begin(0,0);h.menuOptions->Set("windowWidth",1600);h.menuOptions->Set("windowHeight",900);
        h.menuOptions->Set("uiCueVolumePercent",37);h.menuOptions->Set("policyInfo",0);
        h.menuOptions->Apply(0,0,[&](const MenuOptionsValues& v){return ApplyHostMenuOptions(h,w,v);},[&](const MenuOptionsValues& v){store->WriteAtomic(v);});
        Check(h.menuOptions->Committed().windowWidth==1600 && w.state.width==1600);
        Check(!h.policyInfo && h.uiAudio->volume==37);Check(store->SchemaVersion()==3);
        const auto saved=Read(root/L"menu-options.zssettings");Check(saved.rfind("ZEROSIS_PRIVATE_MENU_OPTIONS_V3\n",0)==0 && saved.find("policyInfo=0")!=std::string::npos && saved.find("noRewardPopups=0")!=std::string::npos);
        h.menuOptions->Begin(0,0);h.menuOptions->Set("policyInfo",1);h.menuOptions->Set("uiCueVolumePercent",99);
        Reject([&]{h.menuOptions->Apply(0,0,[&](const MenuOptionsValues& v){return ApplyHostMenuOptions(h,w,v);},[](const MenuOptionsValues&){throw std::runtime_error("persistence failed");});});
        Check(!h.policyInfo && h.uiAudio->volume==37 && w.state.width==1600);
        Check(h.menuOptions->Active() && !h.menuOptions->Faulted());Check(Read(root/L"menu-options.zssettings")==saved);
        h.menuOptions->Cancel(0,0);Check(!h.menuOptions->Active());
        const auto before=h.menuOptions->Committed();w.fail=true;
        Reject([&]{ApplyHostMenuOptions(h,w,before);});Check(!h.policyInfo && h.uiAudio->volume==37);w.fail=false;
        bool wrongThreadRejected=false;std::thread other([&]{try{h.menuOptions->Begin(0,0);}catch(const std::exception&){wrongThreadRejected=true;}});other.join();Check(wrongThreadRejected);
    }
    {
        Host h;h.policyInfo=true;EnsureHostMenuOptions(h,root.wstring(),create);
        Check(!h.policyInfo && h.policyInfoInitialized && h.menuOptions->Committed().uiCueVolumePercent==37);
        Check(h.menuOptionsStore->SchemaVersion()==3);
    }
    fs::remove(root/L"menu-options.zssettings");fs::remove(root/L"menu-options.lock");
    {
        const std::string legacy="ZEROSIS_PRIVATE_MENU_OPTIONS_V1\nnoBasicHelp=0\nhideTouchHelp=0\nuiCueVolumePercent=100\nwindowWidth=1280\nwindowHeight=720\nfullscreen=0\nvsync=1\n";
        {std::ofstream f(root/L"menu-options.zssettings",std::ios::binary);f<<legacy;}
        {Host h;EnsureHostMenuOptions(h,root.wstring(),create);Check(h.menuOptions->Committed().policyInfo && h.menuOptionsStore->SchemaVersion()==1);Check(Read(root/L"menu-options.zssettings")==legacy);}
        fs::remove(root/L"menu-options.zssettings");fs::remove(root/L"menu-options.lock");
    }
    {
        const std::string unknown="ZEROSIS_PRIVATE_MENU_OPTIONS_V99\noriginal=preserve\n";
        {std::ofstream f(root/L"menu-options.zssettings",std::ios::binary);f<<unknown;}
        Host h;Reject([&]{EnsureHostMenuOptions(h,root.wstring(),create);});Check(!h.menuOptions && !h.menuOptionsStore && !h.uiAudio);Check(Read(root/L"menu-options.zssettings")==unknown);
    }
    fs::remove(root/L"menu-options.zssettings");fs::remove(root/L"menu-options.lock");Check(fs::is_empty(root));
    std::cout<<"{\"status\":\"PASS_HOST_OPTION_BINDING_SDK_FREE\",\"checks\":"<<checks<<",\"host_or_sdk_or_window_executed\":false}\n";
}
