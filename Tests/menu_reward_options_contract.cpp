#include "MenuOptionsContract.h"
#include "MenuOptionsStore.h"
#include "MenuResolutionCountdown.h"
#include "MenuResolutionPreviewClock.h"
#include <algorithm>
#include <array>
#include <fstream>
#include <iostream>
#include <type_traits>
#include <vector>
using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool ok,const char* why){++checks;if(!ok)throw std::runtime_error(why);}
template<class F>static void Reject(F fn,const char* why){bool rejected=false;try{fn();}catch(const std::exception&){rejected=true;}Check(rejected,why);}
static MenuOptionsCapabilities All(){MenuOptionsCapabilities c;c.noBasicHelp=c.uiCueVolume=c.windowResolution=c.fullscreen=c.vsync=c.policyInfo=c.noRewardPopups=true;return c;}
static MenuOptionsValues DisplayOnly(MenuOptionsValues base,const MenuOptionsValues& draft){base.windowWidth=draft.windowWidth;base.windowHeight=draft.windowHeight;base.fullscreen=draft.fullscreen;return base;}
static MenuOptionsValues NonDisplayOnly(MenuOptionsValues draft,const MenuOptionsValues& base){draft.windowWidth=base.windowWidth;draft.windowHeight=base.windowHeight;draft.fullscreen=base.fullscreen;return draft;}
static const std::string V1="ZEROSIS_PRIVATE_MENU_OPTIONS_V1\nnoBasicHelp=0\nhideTouchHelp=0\nuiCueVolumePercent=100\nwindowWidth=1280\nwindowHeight=720\nfullscreen=0\nvsync=1\n";
static const std::string V2="ZEROSIS_PRIVATE_MENU_OPTIONS_V2\nnoBasicHelp=0\nhideTouchHelp=0\nuiCueVolumePercent=100\nwindowWidth=1280\nwindowHeight=720\nfullscreen=0\nvsync=1\npolicyInfo=0\n";
static const std::string V3="ZEROSIS_PRIVATE_MENU_OPTIONS_V3\nnoBasicHelp=0\nhideTouchHelp=0\nuiCueVolumePercent=100\nwindowWidth=1280\nwindowHeight=720\nfullscreen=0\nvsync=1\npolicyInfo=0\nnoRewardPopups=0\n";
struct Backend final {
    MenuOptionsValues applied{};std::shared_ptr<std::atomic<bool>> confirmed;bool expected=false;
    std::vector<unsigned> fail,mismatch;unsigned calls=0;std::function<void()> hook;
    MenuOptionsValues Apply(const MenuOptionsValues& v){
        ++calls;if(confirmed)Check(confirmed->load(std::memory_order_acquire)==expected,"Unconfirmed apply or rollback published reward state");applied=v;if(hook)hook();
        if(std::find(fail.begin(),fail.end(),calls)!=fail.end())throw std::runtime_error("controlled applied staging failure");
        if(std::find(mismatch.begin(),mismatch.end(),calls)!=mismatch.end())applied.noRewardPopups=!applied.noRewardPopups;
        return applied;
    }
    MenuOptionsSession::ApplyBackend Callback(){return [this](const MenuOptionsValues& v){return Apply(v);};}
};
struct Persist final {
    std::string bytes=V3;std::shared_ptr<std::atomic<bool>> confirmed;bool expected=false,fail=false;unsigned calls=0;
    void Write(const MenuOptionsValues& v){++calls;if(confirmed)Check(confirmed->load(std::memory_order_acquire)==expected,"Reward value published before persistence succeeded");if(fail)throw std::runtime_error("controlled atomic persistence failure");bytes=MenuOptionsValues::Encode(v);}
    MenuOptionsSession::Persist Callback(){return [this](const MenuOptionsValues& v){Write(v);};}
};
static void Draft(MenuOptionsSession& s,unsigned bits,unsigned resolution,bool reward){
    s.Set("noBasicHelp",bits&1);s.Set("hideTouchHelp",(bits>>1)&1);s.Set("vsync",(bits>>2)&1);s.Set("policyInfo",(bits>>3)&1);s.Set("uiCueVolumePercent",static_cast<int>(40+bits));s.Set("noRewardPopups",reward?1:0);
    s.Set("windowWidth",resolution?1920:1600);s.Set("windowHeight",resolution?1080:900);s.Set("fullscreen",resolution?1:0);
}
static void Codec(){
    const MenuOptionsValues defaults;Check(MenuOptionsValues::Encode(defaults)==V3,"New V3 field ordering or canonical bytes differ");
    for(const auto& text:{V1,V2,V3}){const auto v=MenuOptionsValues::Decode(text);Check(v==defaults && !v.noRewardPopups,"Legacy defaults changed or gained an implicit reward setting");}
    Check(MenuOptionsValues::SchemaVersion(V1)==1 && MenuOptionsValues::SchemaVersion(V2)==2 && MenuOptionsValues::SchemaVersion(V3)==3,"Existing private version identifiers changed");
    auto enabled=defaults;enabled.noRewardPopups=true;Check(enabled!=defaults && MenuOptionsValues::Decode(MenuOptionsValues::Encode(enabled))==enabled,"Reward value missing from equality/encoding/decoding");
    for(const auto& bytes:std::vector<std::string>{V1+"noRewardPopups=1\n",V2+"noRewardPopups=1\n",V3+"noRewardPopups=1\n",V3+"x",V3.substr(0,V3.find("noRewardPopups=")),"ZEROSIS_PRIVATE_MENU_OPTIONS_V4\n",std::string(513,'x')})Reject([&]{MenuOptionsValues::Decode(bytes);},"Malformed or ambiguous versioned preferences accepted");
    for(const auto& value:{"2","-1","00","01","true",""}){auto bad=V3;const std::string key="noRewardPopups=0";bad.replace(bad.find(key),key.size(),std::string("noRewardPopups=")+value);Reject([&]{MenuOptionsValues::Decode(bad);},"Noncanonical reward boolean accepted");}
    MenuOptionsSession disabled(defaults,{});disabled.Begin(1,2);Check(!disabled.Supports("noRewardPopups") && disabled.Get("noRewardPopups")==0,"Reward capability default changed");Reject([&]{disabled.Set("noRewardPopups",1);},"Unsupported reward option edited");disabled.Discard();
    MenuOptionsSession enabledSession(defaults,All());enabledSession.Begin(1,2);enabledSession.Set("noRewardPopups",1);Check(enabledSession.Get("noRewardPopups")==1 && enabledSession.Get("noRewardPopups",false)==0,"Reward draft became committed without Apply");
    Reject([&]{enabledSession.Set("noRewardPopups",2);},"Reward Set accepted a non-boolean integer");enabledSession.ResetDefaults();Check(enabledSession.Get("noRewardPopups")==0,"Reward default reset failed");enabledSession.Discard();
}
static void Binding(){
    static_assert(noexcept(std::declval<std::atomic<bool>&>().store(false,std::memory_order_release)),"Confirmed publication must be noexcept");
    static_assert(std::is_nothrow_copy_assignable<std::shared_ptr<std::atomic<bool>>>::value,"Snapshot retention must be noexcept");
    MenuOptionsValues initial;initial.noRewardPopups=true;auto snapshot=std::make_shared<std::atomic<bool>>(false);MenuOptionsSession s(initial,All());
    Reject([&]{s.BindNoRewardPopupsSnapshot({});},"Null snapshot accepted");Check(!snapshot->load(),"Rejected null binding published anything");s.BindNoRewardPopupsSnapshot(snapshot);Check(snapshot->load(std::memory_order_acquire),"Decoded committed initial value was not published");
    auto replacement=std::make_shared<std::atomic<bool>>(false);Reject([&]{s.BindNoRewardPopupsSnapshot(replacement);},"Stable snapshot was replaced");Reject([&]{s.BindNoRewardPopupsSnapshot(snapshot);},"Same pointer rebound twice");Check(!replacement->load(),"Rejected replacement was written");
    MenuOptionsSession active({},All());active.Begin(1,2);auto untouched=std::make_shared<std::atomic<bool>>(true);Reject([&]{active.BindNoRewardPopupsSnapshot(untouched);},"Snapshot bound during a transaction");Check(untouched->load(),"Active bind rejection changed caller atomic");active.Discard();active.BindNoRewardPopupsSnapshot(untouched);Check(!untouched->load(),"Failed guard poisoned later valid binding");
    MenuOptionsSession foreign({},All());bool rejected=false;std::thread worker([&]{try{foreign.BindNoRewardPopupsSnapshot(replacement);}catch(const std::logic_error&){rejected=true;}});worker.join();Check(rejected && !replacement->load(),"Foreign thread bound/published the snapshot");
    Backend b;Persist p;s.Begin(1,2);s.Set("noRewardPopups",0);b.applied=initial;b.confirmed=snapshot;b.expected=true;p.confirmed=snapshot;p.expected=true;p.bytes=MenuOptionsValues::Encode(initial);
    b.hook=[&]{Reject([&]{s.BindNoRewardPopupsSnapshot(replacement);},"Backend operation bound a snapshot");};s.Apply(1,2,b.Callback(),p.Callback());Check(!snapshot->load() && s.Committed().noRewardPopups==false && !replacement->load(),"Stable pointer did not publish successful commit");
    std::weak_ptr<std::atomic<bool>> retained;
    {auto stable=std::make_shared<std::atomic<bool>>(true);retained=stable;MenuOptionsSession owner({},All());owner.BindNoRewardPopupsSnapshot(stable);stable.reset();Check(!retained.expired() && !retained.lock()->load(),"Session did not retain stable snapshot ownership");}
    Check(retained.expired(),"Destroyed session leaked its stable snapshot");
}
static void PreviewMatrix(){
    for(unsigned initialReward=0;initialReward<2;++initialReward)for(unsigned bits=0;bits<16;++bits)for(unsigned resolution=0;resolution<2;++resolution){
        for(unsigned ending=0;ending<5;++ending){
            MenuOptionsValues base;base.noRewardPopups=initialReward!=0;MenuOptionsSession s(base,All());auto snapshot=std::make_shared<std::atomic<bool>>(!base.noRewardPopups);s.BindNoRewardPopupsSnapshot(snapshot);s.Begin(4,5);Draft(s,bits,resolution,!base.noRewardPopups);const auto draft=s.Cached();
            Backend b;b.applied=base;b.confirmed=snapshot;b.expected=base.noRewardPopups;Persist disk;disk.bytes=MenuOptionsValues::Encode(base);disk.confirmed=snapshot;disk.expected=base.noRewardPopups;
            if(ending>=3){s.CommitNonResolution(4,5,b.Callback(),disk.Callback());const auto nonDisplay=NonDisplayOnly(draft,base);
                Check(s.Committed()==nonDisplay && s.Cached()==draft && snapshot->load()==draft.noRewardPopups && s.Active(),"Original OK did not publish only successfully committed non-display values");b.expected=disk.expected=draft.noRewardPopups;
            }
            const auto baseline=s.Committed();const auto writes=disk.calls;s.PreviewResolution(4,5,b.Callback());Check(s.ResolutionPreviewActive() && s.Cached()==draft && s.Committed()==baseline && b.applied==DisplayOnly(baseline,draft) && snapshot->load()==baseline.noRewardPopups && disk.calls==writes,"Display preview leaked a reward or other non-display draft");
            if(ending==0 || ending==4){s.ConfirmResolution(4,5,b.Callback(),disk.Callback());Check(s.Active() && !s.ResolutionPreviewActive() && s.Committed()==DisplayOnly(baseline,draft) && s.Cached()==draft && snapshot->load()==baseline.noRewardPopups,"Display Yes changed a pending reward draft or its committed publication");}
            else if(ending==1 || ending==3){
                MenuResolutionCountdown countdown;MenuResolutionPreviewClock clock;countdown.Start();clock.Start(21000);double delta=0;Check(clock.Sample(21001,true,&delta) && delta==.001 && !countdown.Advance(delta),"Post-apply clock consumed the prior21seconds");
                Check(clock.Sample(81001,true,&delta) && countdown.Advance(delta) && !countdown.Active(),"Unclamped stall did not expire original20second prompt");s.RejectResolution(4,5,b.Callback());Check(s.Active() && s.Cached()==NonDisplayOnly(draft,baseline) && s.Committed()==baseline && snapshot->load()==baseline.noRewardPopups && disk.calls==writes,"No/timeout undid confirmed reward or published a pending reward");
            }else{s.Cancel(4,5);Check(!s.Active() && !s.ResolutionPreviewActive() && s.Committed()==baseline && snapshot->load()==baseline.noRewardPopups && disk.calls==writes,"Cancel published or undid reward state");}
            s.Discard();Check(snapshot->load()==s.Committed().noRewardPopups,"Shutdown changed confirmed atomic away from canonical state");
        }
    }
}
static void Failures(){
    for(unsigned initialReward=0;initialReward<2;++initialReward)for(unsigned operation=0;operation<4;++operation)for(unsigned mode=0;mode<3;++mode){
        MenuOptionsValues base;base.noRewardPopups=initialReward!=0;MenuOptionsSession s(base,All());auto snapshot=std::make_shared<std::atomic<bool>>(false);s.BindNoRewardPopupsSnapshot(snapshot);s.Begin(4,5);Draft(s,15,1,!base.noRewardPopups);const auto draft=s.Cached();
        Backend b;b.applied=base;b.confirmed=snapshot;b.expected=base.noRewardPopups;Persist disk;disk.bytes=MenuOptionsValues::Encode(base);disk.confirmed=snapshot;disk.expected=base.noRewardPopups;
        if(operation<2){if(mode==0)b.mismatch={1};else{disk.fail=true;if(mode==2)b.fail={2};}
            if(operation==0)Reject([&]{s.Apply(4,5,b.Callback(),disk.Callback());},"Failed reward Apply accepted");else Reject([&]{s.CommitNonResolution(4,5,b.Callback(),disk.Callback());},"Failed reward partial commit accepted");
        }else if(operation==2){if(mode==0)b.mismatch={1};else b.fail=mode==2?std::vector<unsigned>{1,2}:std::vector<unsigned>{1};Reject([&]{s.PreviewResolution(4,5,b.Callback());},"Preview accepted failed reward staging/readback");}
        else{s.PreviewResolution(4,5,b.Callback());if(mode==0)b.mismatch={2};else{disk.fail=true;if(mode==2)b.fail={3};}Reject([&]{s.ConfirmResolution(4,5,b.Callback(),disk.Callback());},"Failed display confirmation accepted");}
        Check(snapshot->load(std::memory_order_acquire)==base.noRewardPopups && disk.bytes==MenuOptionsValues::Encode(base),"Failed operation published unconfirmed reward or preference bytes");
        if(mode==2){Check(s.Faulted() && !s.Active() && !s.ResolutionPreviewActive(),"Failed rollback did not fail closed");auto other=std::make_shared<std::atomic<bool>>(!base.noRewardPopups);Reject([&]{s.BindNoRewardPopupsSnapshot(other);},"Faulted session rebound snapshot");Check(other->load()==!base.noRewardPopups,"Faulted bind wrote caller atomic");}
        else{Check(s.Active() && !s.Faulted() && s.Committed()==base && !s.ResolutionPreviewActive() && b.applied==base,"Recoverable failure did not restore exact committed backend");Check(s.Cached()==(operation<2?draft:NonDisplayOnly(draft,base)),"Failure unexpectedly lost preserved draft fields");}
        s.Discard();Check(snapshot->load()==base.noRewardPopups,"Fault/shutdown path published draft reward");
    }
}
static void ConcurrentGetter(){
    MenuOptionsSession s({},All());auto confirmed=std::make_shared<std::atomic<bool>>(true);s.BindNoRewardPopupsSnapshot(confirmed);
    std::atomic<unsigned> phase{0},ack{0};std::atomic<bool> stop{false};std::array<bool,5> observed{};
    std::thread reader([&]{for(unsigned wanted=1;wanted<=5 && !stop.load(std::memory_order_acquire);++wanted){
        while(phase.load(std::memory_order_acquire)<wanted && !stop.load(std::memory_order_acquire))std::this_thread::yield();
        if(stop.load(std::memory_order_acquire))break;observed[wanted-1]=confirmed->load(std::memory_order_acquire);ack.store(wanted,std::memory_order_release);
    }});
    struct Join final {std::atomic<bool>& stop;std::thread& thread;~Join(){stop.store(true,std::memory_order_release);if(thread.joinable())thread.join();}} join{stop,reader};
    auto sample=[&](unsigned number,bool expected){phase.store(number,std::memory_order_release);unsigned attempts=0;while(ack.load(std::memory_order_acquire)<number && ++attempts<1000000)std::this_thread::yield();Check(ack.load(std::memory_order_acquire)==number && observed[number-1]==expected,"Concurrent acquire getter saw staged/cache/failed reward value");};
    s.Begin(1,2);s.Set("noRewardPopups",1);sample(1,false);
    s.Apply(1,2,[&](const MenuOptionsValues& value){sample(2,false);return value;},[&](const MenuOptionsValues&){sample(3,false);});sample(4,true);
    s.Begin(1,3);s.Set("noRewardPopups",0);Reject([&]{s.Apply(1,3,[](const MenuOptionsValues& value){return value;},[](const MenuOptionsValues&){throw std::runtime_error("controlled persist failure");});},"Concurrent failure fixture unexpectedly persisted");sample(5,true);s.Discard();
}
static std::string Read(const std::wstring& path){std::ifstream stream(path,std::ios::binary);if(!stream)throw std::runtime_error("Owned preference read failed");return {std::istreambuf_iterator<char>(stream),std::istreambuf_iterator<char>()};}
static void NewFile(const std::wstring& path,const std::string& bytes){HANDLE file=CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);if(file==INVALID_HANDLE_VALUE)throw std::runtime_error("Owned preference fixture must be new");DWORD written=0;const bool ok=WriteFile(file,bytes.data(),static_cast<DWORD>(bytes.size()),&written,nullptr)!=FALSE && written==bytes.size() && FlushFileBuffers(file)!=FALSE;CloseHandle(file);if(!ok)throw std::runtime_error("Owned preference fixture write incomplete");}
static std::wstring Child(const std::wstring& root,const wchar_t* name){const auto path=root+L"\\"+name;if(!CreateDirectoryW(path.c_str(),nullptr))throw std::runtime_error("Owned preference child must be new");return path;}
static void Store(const std::wstring& root){
    for(unsigned version=1;version<=2;++version){const auto directory=Child(root,version==1?L"legacy_v1":L"legacy_v2");const auto path=directory+L"\\menu-options.zssettings";const auto original=version==1?V1:V2;NewFile(path,original);MenuOptionsValues promoted;
        {MenuOptionsStore store(directory);MenuOptionsSession s(store.Read(),All());auto snapshot=std::make_shared<std::atomic<bool>>(true);s.BindNoRewardPopupsSnapshot(snapshot);Backend b;b.confirmed=snapshot;unsigned writes=0;
            const auto persist=[&](const MenuOptionsValues& v){Check(!snapshot->load() && !s.Committed().noRewardPopups,"Reward published before actual atomic Store publication");store.WriteAtomic(v);Check(!snapshot->load() && !s.Committed().noRewardPopups,"Reward published inside persistence callback");++writes;};
            Check(store.SchemaVersion()==static_cast<int>(version) && Read(path)==original && !snapshot->load(),"Legacy read rewrote bytes or reward default");s.Begin(1,2);s.Apply(1,2,b.Callback(),persist);Check(writes==0 && Read(path)==original && store.SchemaVersion()==static_cast<int>(version),"No-op Accept migrated legacy preferences");
            s.Begin(1,3);s.Set("noRewardPopups",1);s.Cancel(1,3);s.Begin(1,4);s.Set("noRewardPopups",1);s.Discard();Check(Read(path)==original && !snapshot->load(),"Cancelled legacy reward draft migrated or published");
            s.Begin(1,5);s.Set("noRewardPopups",1);s.Set("windowWidth",1600);s.Set("windowHeight",900);s.PreviewResolution(1,5,b.Callback());s.RejectResolution(1,5,b.Callback());s.Cancel(1,5);Check(Read(path)==original && store.SchemaVersion()==static_cast<int>(version),"Rejected display preview migrated a pending reward draft");
            s.Begin(1,6);s.Set("noRewardPopups",1);s.Apply(1,6,b.Callback(),persist);promoted=s.Committed();Check(writes==1 && store.SchemaVersion()==3 && snapshot->load() && Read(path)==MenuOptionsValues::Encode(promoted),"Explicit changed legacy commit did not publish exact V3 and confirmed reward");
        }
        {MenuOptionsStore reopened(directory);Check(reopened.SchemaVersion()==3 && reopened.Read()==promoted && reopened.Read().noRewardPopups,"Restart lost upgraded confirmed reward");}
    }
    const auto blocked=Child(root,L"blocked_pending");NewFile(blocked+L"\\menu-options.zssettings",V2);NewFile(blocked+L"\\menu-options.pending","owned-pending");
    {MenuOptionsStore store(blocked);MenuOptionsSession s(store.Read(),All());auto snapshot=std::make_shared<std::atomic<bool>>(true);s.BindNoRewardPopupsSnapshot(snapshot);Backend b;b.confirmed=snapshot;s.Begin(1,2);s.Set("noRewardPopups",1);Reject([&]{s.Apply(1,2,b.Callback(),[&](const MenuOptionsValues& v){store.WriteAtomic(v);});},"Occupied pending file did not reject actual atomic Store write");Check(!snapshot->load() && !s.Committed().noRewardPopups && s.Active() && !s.Faulted() && store.SchemaVersion()==2 && Read(blocked+L"\\menu-options.zssettings")==V2 && Read(blocked+L"\\menu-options.pending")=="owned-pending","Failed legacy upgrade published or overwrote bytes");s.Discard();}
    const auto display=Child(root,L"display_only");NewFile(display+L"\\menu-options.zssettings",V1);
    {MenuOptionsStore store(display);MenuOptionsSession s(store.Read(),All());auto snapshot=std::make_shared<std::atomic<bool>>(true);s.BindNoRewardPopupsSnapshot(snapshot);Backend b;b.confirmed=snapshot;s.Begin(1,2);s.Set("noRewardPopups",1);s.Set("windowWidth",1600);s.Set("windowHeight",900);s.PreviewResolution(1,2,b.Callback());s.ConfirmResolution(1,2,b.Callback(),[&](const MenuOptionsValues& v){store.WriteAtomic(v);});Check(store.SchemaVersion()==3 && !snapshot->load() && !store.Read().noRewardPopups && !s.Committed().noRewardPopups && s.Cached().noRewardPopups && s.Active(),"Dedicated display Yes persisted a pending reward draft");s.Discard();}
    const auto partial=Child(root,L"partial_then_timeout");NewFile(partial+L"\\menu-options.zssettings",V2);
    {MenuOptionsStore store(partial);MenuOptionsSession s(store.Read(),All());auto snapshot=std::make_shared<std::atomic<bool>>(true);s.BindNoRewardPopupsSnapshot(snapshot);Backend b;b.confirmed=snapshot;s.Begin(1,2);s.Set("noRewardPopups",1);s.Set("windowWidth",1920);s.Set("windowHeight",1080);s.CommitNonResolution(1,2,b.Callback(),[&](const MenuOptionsValues& v){store.WriteAtomic(v);});b.expected=true;const auto committed=Read(partial+L"\\menu-options.zssettings");s.PreviewResolution(1,2,b.Callback());s.RejectResolution(1,2,b.Callback());Check(snapshot->load() && store.Read().noRewardPopups && s.Committed().noRewardPopups && Read(partial+L"\\menu-options.zssettings")==committed && store.SchemaVersion()==3,"Later display No undid explicitly committed reward setting");s.Discard();}
    const auto unknown=Child(root,L"unknown_schema");const std::string future="ZEROSIS_PRIVATE_MENU_OPTIONS_V99\nnoRewardPopups=1\n";NewFile(unknown+L"\\menu-options.zssettings",future);Reject([&]{MenuOptionsStore store(unknown);},"Unknown future preferences were reset/accepted");Check(Read(unknown+L"\\menu-options.zssettings")==future,"Unknown preference bytes changed");
}
int wmain(int argc,wchar_t** argv){try{
    if(argc!=2)throw std::runtime_error("Expected one exact owned file-only preference directory");const std::wstring root(argv[1]);const auto attrs=GetFileAttributesW(root.c_str());if(root.size()<3 || root[1]!=L':' || attrs==INVALID_FILE_ATTRIBUTES || !(attrs&FILE_ATTRIBUTE_DIRECTORY) || attrs&FILE_ATTRIBUTE_REPARSE_POINT)throw std::runtime_error("Invalid owned preference directory");
    Codec();Binding();PreviewMatrix();Failures();ConcurrentGetter();Store(root);
    std::cout<<"{\"status\":\"PASS_REWARD_V3_LEGACY_READ_AND_CONFIRMED_ATOMIC_PUBLICATION\",\"checks\":"<<checks<<",\"preview_workflows\":320,\"failure_workflows\":24,\"controlled_store_cases\":6,\"cross_thread_atomic_samples\":5,\"legacy_v1_v2_read_bytes_preserved\":true,\"changed_explicit_commit_only_migration\":true,\"stable_noexcept_release_publication\":true,\"native_host_sdk_window_gpu_or_audio_executed\":false}"<<std::endl;return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<std::endl;return 1;}}
