// Real private-store/session/binding with value-only display/audio and the
// exact extracted SDK getter. No GameCore, HWND, GPU or audio provider runs.
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS
#include "MenuOptionsHostBinding.h"
#include <atomic>
#include <fstream>
#include <iostream>
#include <iterator>
#include <thread>
#include <type_traits>

using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
template<class F>static void Reject(F fn){bool rejected=false;try{fn();}catch(const std::exception&){rejected=true;}Check(rejected,"Invalid operation was accepted");}
struct Audio final {
    unsigned volume=100;
    void SetVolumePercent(unsigned value){if(value>100)throw std::runtime_error("volume");volume=value;}
    unsigned VolumePercent()const{return volume;}
};
struct Host final {
    std::shared_ptr<MenuOptionsSession> menuOptions;
    std::shared_ptr<MenuOptionsStore> menuOptionsStore;
    std::shared_ptr<Audio> uiAudio;
    bool policyInfoInitialized=true,policyInfo=false;
    const std::shared_ptr<std::atomic<bool>> noRewardPopupsCommitted=std::make_shared<std::atomic<bool>>(false);
    bool noRewardPopupsApplied=false;
};
struct GetterBase {virtual ~GetterBase()=default;virtual bool IsOptionNoRewardPopups()=0;};
class Getter final : public GetterBase {
    std::shared_ptr<Host> state_;
public:
    explicit Getter(std::shared_ptr<Host> state):state_(std::move(state)){}
#include "reward_popup_sdk_getter.inc"
};
struct Window final {
    struct DisplaySettings {std::uint32_t width=1280,height=720;bool fullscreen=false,vsync=true;};
    DisplaySettings state;unsigned calls=0,failOnCall=0;bool mismatch=false;
    bool ApplyDisplaySettings(const DisplaySettings& value,DisplaySettings* actual,std::wstring* error){
        ++calls;if(calls==failOnCall){*error=L"controlled display failure";return false;}
        state=value;*actual=state;if(mismatch)actual->width=999;return true;
    }
};
static std::wstring Directory(const std::wstring& root,const wchar_t* name){
    const auto path=root+L"\\"+name;if(!CreateDirectoryW(path.c_str(),nullptr))throw std::runtime_error("Private fixture directory already exists");return path;
}
static std::string Read(const std::wstring& path){std::ifstream file(path.c_str(),std::ios::binary);return {std::istreambuf_iterator<char>(file),{}};}
static void Seed(const std::wstring& directory,const std::string& bytes){const auto path=directory+L"\\menu-options.zssettings";std::ofstream file(path.c_str(),std::ios::binary);file<<bytes;if(!file)throw std::runtime_error("Cannot seed private fixture");}
static const auto factory=[](){return std::make_shared<Audio>();};
static void StartupAndCache(const std::wstring& root){
    auto host=std::make_shared<Host>();const auto cell=host->noRewardPopupsCommitted;Getter sdk(host);Window window;
    const auto directory=Directory(root,L"startup");EnsureHostMenuOptions(*host,directory,factory);
    Check(!sdk.IsOptionNoRewardPopups() && !host->noRewardPopupsApplied && host->menuOptions->Supports("noRewardPopups"),"Initial defaultfalse or real capability changed");
    const auto session=host->menuOptions;EnsureHostMenuOptions(*host,directory,factory);
    Check(host->menuOptions==session && host->noRewardPopupsCommitted==cell,"Repeated Ensure replaced the session or committed cell");
    session->Begin(0,1);session->Set("noRewardPopups",1);
    Check(session->Get("noRewardPopups",true)==1 && !sdk.IsOptionNoRewardPopups(),"Cached draft leaked to the SDK getter");
    const auto staged=ApplyHostMenuOptions(*host,window,session->Cached());
    Check(staged.noRewardPopups && host->noRewardPopupsApplied && !sdk.IsOptionNoRewardPopups(),"Backend staging published before the actual commit");
    ApplyHostMenuOptions(*host,window,session->Committed());session->Cancel(0,1);
    Check(!host->noRewardPopupsApplied && !sdk.IsOptionNoRewardPopups() && host->menuOptionsStore->SchemaVersion()==0,"Cancelled draft changed confirmed data");
    session->Begin(0,2);session->Set("noRewardPopups",1);unsigned persisted=0;
    session->Apply(0,2,[&](const MenuOptionsValues& value){
        Check(!sdk.IsOptionNoRewardPopups(),"SDK getter changed during candidate application");return ApplyHostMenuOptions(*host,window,value);
    },[&](const MenuOptionsValues& value){
        Check(!sdk.IsOptionNoRewardPopups(),"SDK getter changed before persistence");host->menuOptionsStore->WriteAtomic(value);++persisted;
        Check(!sdk.IsOptionNoRewardPopups(),"SDK getter changed before persistence returned");
    });
    Check(persisted==1 && sdk.IsOptionNoRewardPopups() && session->Committed().noRewardPopups && host->noRewardPopupsApplied,"Successful commit was not published to the actual getter");
    const auto saved=Read(directory+L"\\menu-options.zssettings");
    Check(saved.rfind("ZEROSIS_PRIVATE_MENU_OPTIONS_V3\n",0)==0 && saved.find("noRewardPopups=1\n")!=std::string::npos,"Canonical V3 reward preference missing");
    session->Begin(0,3);session->Set("noRewardPopups",0);
    Reject([&]{session->Apply(0,3,[&](const MenuOptionsValues& value){return ApplyHostMenuOptions(*host,window,value);},[&](const MenuOptionsValues&){
        Check(sdk.IsOptionNoRewardPopups(),"Failed persistence observed an unconfirmed value");throw std::runtime_error("controlled persistence failure");});});
    Check(sdk.IsOptionNoRewardPopups() && host->noRewardPopupsApplied && session->Committed().noRewardPopups && !session->Faulted(),"Persistence failure changed the confirmed snapshot or lost staging rollback");
    Check(Read(directory+L"\\menu-options.zssettings")==saved,"Failed apply changed private settings bytes");session->Cancel(0,3);
    session->Begin(0,4);std::atomic<bool> stop{false},leaked{false},wrongThreadRejected{false};
    std::thread reader([&]{try{session->Set("noRewardPopups",0);}catch(const std::logic_error&){wrongThreadRejected=true;}
        while(!stop.load(std::memory_order_acquire))if(!sdk.IsOptionNoRewardPopups())leaked=true;});
    for(unsigned i=0;i<10000;++i)session->Set("noRewardPopups",static_cast<int>(i&1));
    stop.store(true,std::memory_order_release);reader.join();session->Cancel(0,4);
    Check(wrongThreadRejected && !leaked && sdk.IsOptionNoRewardPopups(),"Worker reader accessed the UI cache or rejected an atomic committed read");
}
static void DisplayPreview(const std::wstring& root){
    auto host=std::make_shared<Host>();Getter sdk(host);Window window;const auto directory=Directory(root,L"preview");EnsureHostMenuOptions(*host,directory,factory);
    auto& session=*host->menuOptions;const auto apply=[&](const MenuOptionsValues& value){return ApplyHostMenuOptions(*host,window,value);};
    const auto persist=[&](const MenuOptionsValues& value){host->menuOptionsStore->WriteAtomic(value);};
    session.Begin(0,1);session.Set("noRewardPopups",1);session.Set("windowWidth",1600);session.Set("windowHeight",900);
    session.PreviewResolution(0,1,apply);Check(!sdk.IsOptionNoRewardPopups() && !host->noRewardPopupsApplied && session.Cached().noRewardPopups,"Display preview leaked an unrelated reward draft");
    session.RejectResolution(0,1,apply);Check(!sdk.IsOptionNoRewardPopups() && !host->noRewardPopupsApplied && session.Cached().noRewardPopups,"Display rejection changed committed reward data");
    session.Set("windowWidth",1600);session.Set("windowHeight",900);
    session.PreviewResolution(0,1,apply);session.ConfirmResolution(0,1,apply,persist);
    Check(!sdk.IsOptionNoRewardPopups() && !session.Committed().noRewardPopups && session.Cached().noRewardPopups,"Display confirmation published the reward draft");
    session.CommitNonResolution(0,1,apply,persist);Check(sdk.IsOptionNoRewardPopups() && host->noRewardPopupsApplied,"Explicit non-resolution commit did not publish reward value");session.Cancel(0,1);
    session.Begin(0,2);session.Set("noRewardPopups",0);session.Set("windowWidth",1920);session.Set("windowHeight",1080);
    session.CommitNonResolution(0,2,apply,persist);Check(!sdk.IsOptionNoRewardPopups() && session.ResolutionChanged(),"Partial commit lost reward value or pending display fields");
    session.PreviewResolution(0,2,apply);session.RejectResolution(0,2,apply);Check(!sdk.IsOptionNoRewardPopups(),"Reverting a later display candidate changed an already confirmed preference");session.Cancel(0,2);
}
static void Failures(const std::wstring& root){
    {
        auto host=std::make_shared<Host>();Getter sdk(host);Window window;EnsureHostMenuOptions(*host,Directory(root,L"rollback_failure"),factory);
        auto& session=*host->menuOptions;session.Begin(0,1);session.Set("noRewardPopups",1);window.failOnCall=2;
        Reject([&]{session.Apply(0,1,[&](const MenuOptionsValues& value){return ApplyHostMenuOptions(*host,window,value);},[](const MenuOptionsValues&){throw std::runtime_error("controlled persistence failure");});});
        Check(session.Faulted() && !sdk.IsOptionNoRewardPopups() && host->noRewardPopupsApplied,"Rollback failure published candidate data or concealed its applied staging");
    }
    {
        auto host=std::make_shared<Host>();Getter sdk(host);Window window;EnsureHostMenuOptions(*host,Directory(root,L"readback_failure"),factory);
        auto& session=*host->menuOptions;session.Begin(0,1);session.Set("noRewardPopups",1);window.mismatch=true;unsigned persists=0;
        Reject([&]{session.Apply(0,1,[&](const MenuOptionsValues& value){return ApplyHostMenuOptions(*host,window,value);},[&](const MenuOptionsValues&){++persists;});});
        Check(session.Faulted() && !sdk.IsOptionNoRewardPopups() && persists==0,"Readback mismatch published or persisted an unconfirmed flag");
    }
    {
        auto host=std::make_shared<Host>();const auto cell=host->noRewardPopupsCommitted;const auto directory=Directory(root,L"audio_setup_failure");MenuOptionsValues initial;initial.noRewardPopups=true;const auto encoded=MenuOptionsValues::Encode(initial);Seed(directory,encoded);
        Reject([&]{EnsureHostMenuOptions(*host,directory,[](){return std::shared_ptr<Audio>{};});});
        Check(host->noRewardPopupsCommitted==cell && !cell->load() && !host->noRewardPopupsApplied && !host->menuOptions && !host->menuOptionsStore && !host->uiAudio,"Fallible setup bound/published a partially constructed host");
        Check(Read(directory+L"\\menu-options.zssettings")==encoded,"Failed initialization rewrote existing private bytes");
    }
}
static void LegacyAndLifetime(const std::wstring& root){
    const std::string legacy="ZEROSIS_PRIVATE_MENU_OPTIONS_V2\nnoBasicHelp=0\nhideTouchHelp=0\nuiCueVolumePercent=100\nwindowWidth=1280\nwindowHeight=720\nfullscreen=0\nvsync=1\npolicyInfo=0\n";
    const auto directory=Directory(root,L"legacy_v2");Seed(directory,legacy);
    {
        auto host=std::make_shared<Host>();Getter sdk(host);EnsureHostMenuOptions(*host,directory,factory);
        Check(!sdk.IsOptionNoRewardPopups() && !host->noRewardPopupsApplied && !host->menuOptions->Committed().noRewardPopups && host->menuOptionsStore->SchemaVersion()==2,"Legacy V2 defaultfalse initialization changed");
        Check(Read(directory+L"\\menu-options.zssettings")==legacy,"Legacy V2 read performed migration");
    }
    const auto present=Directory(root,L"confirmed_startup");MenuOptionsValues initial;initial.noRewardPopups=true;Seed(present,MenuOptionsValues::Encode(initial));
    auto host=std::make_shared<Host>();std::weak_ptr<Host> weak=host;const auto cell=host->noRewardPopupsCommitted;EnsureHostMenuOptions(*host,present,factory);
    Check(cell->load(std::memory_order_acquire) && host->noRewardPopupsApplied,"Startup did not bind the decoded confirmed true flag");
    const auto session=host->menuOptions;host.reset();Check(weak.expired() && cell.use_count()>=2,"Host cell lifetime depends on the HostState object");
    session->Begin(0,1);session->Set("noRewardPopups",0);session->Apply(0,1,[](const MenuOptionsValues& value){return value;},[](const MenuOptionsValues&){});
    Check(!cell->load(std::memory_order_acquire),"Session lost the shared committed publication cell after Host destruction");
}
int wmain(int argc,wchar_t** argv){try{
    if(argc!=2)throw std::runtime_error("Expected exact owned private fixture directory");
    static_assert(std::is_const<decltype(Host::noRewardPopupsCommitted)>::value,"Publication cell pointer must remain immutable");
    StartupAndCache(argv[1]);DisplayPreview(argv[1]);Failures(argv[1]);LegacyAndLifetime(argv[1]);
    std::cout<<"{\"status\":\"PASS_REAL_HOST_BINDING_COMMITTED_REWARD_SNAPSHOT\",\"checks\":"<<checks<<",\"cached_edits_while_worker_reads\":10000,\"actual_sdk_getter_body\":true,\"apply_persist_and_rollback_failure_isolation\":true,\"shared_cell_lifetime\":true,\"host_sdk_hwnd_gpu_or_audio_executed\":false}\n";return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}}
