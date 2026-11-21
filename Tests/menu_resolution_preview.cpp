#include "MenuOptionsContract.h"
#include "MenuOptionsStore.h"
#include <algorithm>
#include <cstdio>
#include <fstream>
#include <iostream>
#include <memory>
#include <vector>
using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool ok,const char* why){++checks;if(!ok)throw std::runtime_error(why);}
template<class F>static void Reject(F fn,const char* why){bool caught=false;try{fn();}catch(const std::exception&){caught=true;}Check(caught,why);}
static MenuOptionsCapabilities All(){MenuOptionsCapabilities c;c.noBasicHelp=c.uiCueVolume=c.windowResolution=c.fullscreen=c.vsync=c.policyInfo=true;return c;}
static MenuOptionsValues DisplayOnly(MenuOptionsValues base,const MenuOptionsValues& draft){base.windowWidth=draft.windowWidth;base.windowHeight=draft.windowHeight;base.fullscreen=draft.fullscreen;return base;}
static MenuOptionsValues NonDisplayOnly(MenuOptionsValues draft,const MenuOptionsValues& base){draft.windowWidth=base.windowWidth;draft.windowHeight=base.windowHeight;draft.fullscreen=base.fullscreen;return draft;}
struct Backend final {
    MenuOptionsValues actual{};std::vector<MenuOptionsValues> requests;std::vector<unsigned> throws,mismatches;
    std::function<void()> hook;
    MenuOptionsValues Apply(const MenuOptionsValues& next){
        requests.push_back(next);actual=next;if(hook)hook();const auto call=static_cast<unsigned>(requests.size());
        if(std::find(throws.begin(),throws.end(),call)!=throws.end())throw std::runtime_error("controlled partial backend failure");
        if(std::find(mismatches.begin(),mismatches.end(),call)!=mismatches.end())actual.vsync=!actual.vsync;
        return actual;
    }
    MenuOptionsSession::ApplyBackend Callback(){return [this](const MenuOptionsValues& v){return Apply(v);};}
};
struct Persistence final {
    std::string bytes=MenuOptionsValues::Encode(MenuOptionsValues{});unsigned calls=0;bool fail=false;std::function<void()> hook;
    void Write(const MenuOptionsValues& v){++calls;if(hook)hook();if(fail)throw std::runtime_error("controlled atomic persistence failure");bytes=MenuOptionsValues::Encode(v);}
    MenuOptionsSession::Persist Callback(){return [this](const MenuOptionsValues& v){Write(v);};}
};
static void Draft(MenuOptionsSession& s,unsigned bits,unsigned resolution){
    s.Set("noBasicHelp",bits&1);s.Set("hideTouchHelp",(bits>>1)&1);s.Set("vsync",(bits>>2)&1);s.Set("policyInfo",(bits>>3)&1);s.Set("uiCueVolumePercent",static_cast<int>(31+bits));
    const int widths[]={1024,1600,1920},heights[]={768,900,1080};s.Set("windowWidth",widths[resolution%3]);s.Set("windowHeight",heights[resolution%3]);s.Set("fullscreen",resolution>=3?1:0);
}
static void HealthyPreview(const MenuOptionsSession& s,const Backend& b,const MenuOptionsValues& base,const MenuOptionsValues& draft){
    Check(s.Active() && s.ResolutionPreviewActive() && !s.Faulted(),"Preview did not retain its healthy options owner");
    Check(s.Committed()==base && s.Cached()==draft && b.actual==DisplayOnly(base,draft),"Preview leaked non-display drafts or changed canonical state");
}
static void Faulted(const MenuOptionsSession& s){Check(s.Faulted() && !s.Active() && !s.ResolutionPreviewActive(),"Rollback failure did not fault/close/release preview");}
static std::string Read(const std::wstring& path){std::ifstream file(path,std::ios::binary);if(!file)throw std::runtime_error("Owned file read failed");return {std::istreambuf_iterator<char>(file),std::istreambuf_iterator<char>()};}
static void NewFile(const std::wstring& path,const std::string& bytes){
    HANDLE file=CreateFileW(path.c_str(),GENERIC_WRITE,0,nullptr,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr);
    if(file==INVALID_HANDLE_VALUE)throw std::runtime_error("Owned fixture file already exists or cannot be created");DWORD written=0;
    const bool ok=WriteFile(file,bytes.data(),static_cast<DWORD>(bytes.size()),&written,nullptr)!=FALSE && written==bytes.size() && FlushFileBuffers(file)!=FALSE;CloseHandle(file);
    if(!ok)throw std::runtime_error("Owned fixture write incomplete");
}
static std::wstring Child(const std::wstring& owned,const wchar_t* name){
    const auto path=owned+L"\\"+name;if(!CreateDirectoryW(path.c_str(),nullptr))throw std::runtime_error("Owned fixture child must be new");return path;
}
static void Workflows(){
    const MenuOptionsValues base;
    for(unsigned bits=0;bits<16;++bits)for(unsigned resolution=0;resolution<6;++resolution){
        for(unsigned ending=0;ending<4;++ending){
            MenuOptionsSession s(base,All());Backend b;Persistence p;s.Begin(3,7);Draft(s,bits,resolution);const auto draft=s.Cached();const auto apply=b.Callback();const auto persist=p.Callback();
            Check(s.ResolutionChanged(),"Pending original display not detected");s.PreviewResolution(3,7,apply);HealthyPreview(s,b,base,draft);
            Check(b.requests.size()==1 && p.calls==0,"Preview persisted preferences or issued extra backend work");
            if(ending==0){
                s.ConfirmResolution(3,7,apply,persist);const auto confirmed=DisplayOnly(base,draft);
                Check(s.Active() && !s.ResolutionPreviewActive() && !s.ResolutionChanged() && s.Committed()==confirmed && s.Cached()==draft,"Yes failed to update only the confirmed display baseline");
                Check(b.actual==confirmed && p.bytes==MenuOptionsValues::Encode(confirmed) && p.calls==1,"Yes persisted an unrelated preference draft");
                s.Apply(3,7,apply,persist);Check(!s.Active() && s.Committed()==draft && b.actual==draft && p.bytes==MenuOptionsValues::Encode(draft),"Final OK did not apply the preserved non-display drafts");
            }else if(ending==1){
                s.RejectResolution(3,7,apply);Check(s.Active() && !s.ResolutionPreviewActive() && !s.ResolutionChanged() && s.Cached()==NonDisplayOnly(draft,base) && b.actual==base && p.calls==0,"No/timeout API did not restore display and preserve other drafts");s.Cancel(3,7);
            }else if(ending==2){s.Cancel(3,7);Check(!s.Active() && !s.ResolutionPreviewActive() && b.actual==base && p.calls==0,"Cancel did not restore its live preview before discarding edits");
            }else{s.Discard();Check(!s.Active() && !s.ResolutionPreviewActive() && b.actual==base && p.calls==0,"Shutdown did not restore its live preview without player/turn");}
        }
        // Original OnOK commits non-resolution drafts first. Rejecting its
        // subsequent resolution prompt must not undo that successful commit.
        MenuOptionsSession s(base,All());Backend b;Persistence p;s.Begin(9,11);Draft(s,bits,resolution);const auto draft=s.Cached(),nonDisplay=NonDisplayOnly(draft,base);const auto apply=b.Callback();const auto persist=p.Callback();
        s.CommitNonResolution(9,11,apply,persist);Check(s.Active() && s.Committed()==nonDisplay && s.Cached()==draft && s.ResolutionChanged(),"Original OK partial commit discarded pending display or transaction");
        Check(b.actual==nonDisplay && p.bytes==MenuOptionsValues::Encode(nonDisplay),"Original OK published display before its confirmation");
        s.PreviewResolution(9,11,apply);HealthyPreview(s,b,nonDisplay,draft);s.RejectResolution(9,11,apply);
        Check(s.Active() && s.Cached()==nonDisplay && s.Committed()==nonDisplay && b.actual==nonDisplay && p.bytes==MenuOptionsValues::Encode(nonDisplay),"No/timeout reverted already committed Game/Graphics/Audio");
        const auto calls=b.requests.size();const auto writes=p.calls;s.Apply(9,11,apply,persist);Check(!s.Active() && b.requests.size()==calls && p.calls==writes,"Unchanged final OK repeated partial persistence");
    }
    // Repeated previews use the most recent Yes as their rollback baseline.
    MenuOptionsSession s(base,All());Backend b;Persistence p;s.Begin(4,5);Draft(s,15,0);const auto first=s.Cached();s.PreviewResolution(4,5,b.Callback());s.ConfirmResolution(4,5,b.Callback(),p.Callback());const auto confirmed=DisplayOnly(base,first);
    s.Set("windowWidth",1920);s.Set("windowHeight",1080);s.Set("fullscreen",1);const auto second=s.Cached();s.PreviewResolution(4,5,b.Callback());s.RejectResolution(4,5,b.Callback());
    Check(s.Committed()==confirmed && s.Cached()==NonDisplayOnly(second,confirmed) && b.actual==confirmed && p.bytes==MenuOptionsValues::Encode(confirmed),"A second No did not return to the last confirmed resolution");s.Discard();
}
static void FailuresAndModal(){
    const MenuOptionsValues base;
    for(unsigned restoreFailure=0;restoreFailure<2;++restoreFailure){
        MenuOptionsSession partial(base,All());Backend actual;Persistence disk;partial.Begin(5,8);Draft(partial,11,1);const auto draft=partial.Cached();disk.fail=true;
        if(restoreFailure)actual.throws.push_back(2);
        Reject([&]{partial.CommitNonResolution(5,8,actual.Callback(),disk.Callback());},"Partial canonical persistence failure was swallowed");
        Check(disk.bytes==MenuOptionsValues::Encode(base),"Failed partial persistence changed canonical bytes");
        if(restoreFailure)Faulted(partial);
        else Check(partial.Active() && !partial.Faulted() && partial.Committed()==base && partial.Cached()==draft && actual.actual==base,"Failed partial persistence discarded pending resolution or failed exact rollback");
        partial.Discard();
    }
    for(unsigned stage=0;stage<4;++stage)for(unsigned mismatch=0;mismatch<2;++mismatch){
        if(stage==2 && mismatch)continue;
        MenuOptionsSession s(base,All());Backend b;Persistence p;s.Begin(2,6);Draft(s,15,2);const auto draft=s.Cached();
        if(stage==0){(mismatch?b.mismatches:b.throws).push_back(1);Reject([&]{s.PreviewResolution(2,6,b.Callback());},"Failed initial preview was accepted");}
        else if(stage==1){s.PreviewResolution(2,6,b.Callback());(mismatch?b.mismatches:b.throws).push_back(2);Reject([&]{s.ConfirmResolution(2,6,b.Callback(),p.Callback());},"Failed confirmation readback was accepted");}
        else if(stage==2){s.PreviewResolution(2,6,b.Callback());p.fail=true;Reject([&]{s.ConfirmResolution(2,6,b.Callback(),p.Callback());},"Failed atomic resolution persistence was accepted");}
        else{(mismatch?b.mismatches:b.throws).push_back(1);Reject([&]{s.CommitNonResolution(2,6,b.Callback(),p.Callback());},"Failed non-resolution partial commit was accepted");}
        Check(s.Active() && !s.Faulted() && !s.ResolutionPreviewActive() && s.Committed()==base && b.actual==base,"Recoverable preview/partial commit failure did not restore exact old backend");
        Check(s.Cached()==(stage==3?draft:NonDisplayOnly(draft,base)) && p.bytes==MenuOptionsValues::Encode(base),"Failure draft/canonical policy differs");s.Discard();
    }
    for(unsigned action=0;action<6;++action)for(unsigned mismatch=0;mismatch<2;++mismatch){
        MenuOptionsSession s(base,All());Backend b;Persistence p;s.Begin(2,6);Draft(s,7,2);
        if(action==0){(mismatch?b.mismatches:b.throws)={1,2};Reject([&]{s.PreviewResolution(2,6,b.Callback());},"Failed preview rollback was swallowed");}
        else if(action==5){(mismatch?b.mismatches:b.throws)={1,2};Reject([&]{s.CommitNonResolution(2,6,b.Callback(),p.Callback());},"Failed partial-commit rollback was swallowed");}
        else{
            s.PreviewResolution(2,6,b.Callback());
            if(action==1){p.fail=true;(mismatch?b.mismatches:b.throws).push_back(3);Reject([&]{s.ConfirmResolution(2,6,b.Callback(),p.Callback());},"Failed confirmation rollback was swallowed");}
            else{(mismatch?b.mismatches:b.throws).push_back(2);
                if(action==2)Reject([&]{s.RejectResolution(2,6,b.Callback());},"Failed No restore was swallowed");
                if(action==3)Reject([&]{s.Cancel(2,6);},"Failed Cancel restore was swallowed");
                if(action==4)s.Discard(); // Must not throw into the old noexcept controller destructor.
            }
        }
        Faulted(s);Check(p.bytes==MenuOptionsValues::Encode(base),"Faulting rollback published corrupt canonical settings");
        Reject([&]{s.Begin(2,6);},"Faulted session reopened");Reject([&]{s.Set("windowWidth",1280);},"Faulted session edited");s.Discard();Faulted(s);
    }
    MenuOptionsSession s(base,All());Backend b;Persistence p;s.Begin(1,2);Draft(s,5,1);s.PreviewResolution(1,2,b.Callback());const auto saved=s.Cached();const auto count=b.requests.size();
    Reject([&]{s.Set("noBasicHelp",1);},"Preview modal bypass by preference edit");Reject([&]{s.Set("windowWidth",1280);},"Preview modal bypass by display edit");Reject([&]{s.ResetDefaults();},"Preview modal bypass by defaults");
    Reject([&]{s.Apply(1,2,b.Callback(),p.Callback());},"Preview modal bypass by final Apply");Reject([&]{s.CommitNonResolution(1,2,b.Callback(),p.Callback());},"Preview modal bypass by partial commit");Reject([&]{s.PreviewResolution(1,2,b.Callback());},"Nested preview accepted");Reject([&]{s.Begin(1,2);},"Nested owner accepted");
    Reject([&]{s.ConfirmResolution(2,2,b.Callback(),p.Callback());},"Changed player confirmed preview");Reject([&]{s.RejectResolution(1,3,b.Callback());},"Changed turn rejected preview");Reject([&]{s.Cancel(1,3);},"Changed turn cancelled preview");
    Reject([&]{s.ConfirmResolution(1,2,{},p.Callback());},"Missing confirmation backend accepted");Reject([&]{s.ConfirmResolution(1,2,b.Callback(),{});},"Missing atomic confirmation persistence accepted");Reject([&]{s.RejectResolution(1,2,{});},"Missing rejection backend accepted");
    Check(s.Cached()==saved && s.ResolutionPreviewActive() && b.requests.size()==count && p.calls==0,"Rejected modal/stale calls changed preview state");s.Discard();
    MenuOptionsSession noChange(base,All());noChange.Begin(1,2);Reject([&]{noChange.PreviewResolution(1,2,b.Callback());},"Unchanged resolution preview accepted");noChange.Discard();
}
static void LifetimeAndRegression(){
    const MenuOptionsValues base;
    for(unsigned ending=0;ending<6;++ending){
        auto s=std::make_shared<MenuOptionsSession>(base,All());Backend b;Persistence p;std::weak_ptr<int> token;
        s->Begin(1,2);Draft(*s,3,0);
        {auto lease=std::make_shared<int>(1);token=lease;MenuOptionsSession::ApplyBackend snapshot=[&b,lease](const MenuOptionsValues& v){Check(*lease==1,"Preview snapshot outlived its context");return b.Apply(v);};s->PreviewResolution(1,2,snapshot);}
        Check(!token.expired(),"Preview failed to retain its owned restore callback");
        if(ending==0)s->ConfirmResolution(1,2,b.Callback(),p.Callback());
        if(ending==1)s->RejectResolution(1,2,b.Callback());if(ending==2)s->Cancel(1,2);if(ending==3)s->Discard();
        if(ending==4){p.fail=true;Reject([&]{s->ConfirmResolution(1,2,b.Callback(),p.Callback());},"Injected persistence failure was swallowed");}
        if(ending==5){b.throws.push_back(2);s->Discard();Faulted(*s);}
        Check(token.expired(),"Completed/faulted preview retained a Window-lifetime callback");s->Discard();
    }
    // Reproduce the existing controller destructor pattern with a session that
    // outlives the controller. Its restore failure must not reach terminate.
    auto persistent=std::make_shared<MenuOptionsSession>(base,All());Backend b;
    struct Controller final {
        std::shared_ptr<MenuOptionsSession> session;
        ~Controller() noexcept {try{session->Discard();}catch(...){std::terminate();}}
    };
    {Controller controller{persistent};persistent->Begin(1,2);Draft(*persistent,2,0);persistent->PreviewResolution(1,2,b.Callback());b.throws.push_back(2);}
    Faulted(*persistent);
    MenuOptionsSession ordinary(base,All());Backend normal;Persistence p;const auto apply=normal.Callback();const auto persist=p.Callback();
    ordinary.Begin(1,2);ordinary.Apply(1,2,apply,persist);Check(!ordinary.Active() && normal.requests.empty() && p.calls==0,"Ordinary unchanged Apply regressed");
    ordinary.Begin(1,3);ordinary.Set("uiCueVolumePercent",55);ordinary.Cancel(1,3);Check(normal.requests.empty() && p.calls==0 && ordinary.Committed()==base,"Ordinary Cancel changed a backend");
    ordinary.Begin(1,4);ordinary.Set("policyInfo",1);ordinary.Discard();Check(normal.requests.empty() && ordinary.Committed()==base,"Ordinary Discard changed a backend");
    ordinary.Begin(1,5);Draft(ordinary,9,1);const auto full=ordinary.Cached();ordinary.Apply(1,5,apply,persist);Check(!ordinary.Active() && ordinary.Committed()==full && normal.actual==full && p.bytes==MenuOptionsValues::Encode(full),"Ordinary full Apply behavior changed");
    ordinary.Begin(1,6);ordinary.Set("uiCueVolumePercent",12);const auto committed=ordinary.Committed();p.fail=true;Reject([&]{ordinary.Apply(1,6,apply,persist);},"Ordinary atomic failure accepted");Check(ordinary.Active() && !ordinary.Faulted() && normal.actual==committed && ordinary.Committed()==committed,"Ordinary failed Apply rollback regressed");ordinary.Discard();
    MenuOptionsSession partial(base,All());Backend onlyDisplay;Persistence disk;partial.Begin(2,3);partial.Set("windowWidth",1600);partial.CommitNonResolution(2,3,onlyDisplay.Callback(),disk.Callback());Check(partial.Active() && partial.ResolutionChanged() && onlyDisplay.requests.empty() && disk.calls==0,"Unchanged non-display partial commit applied a pending resolution");partial.Discard();
    MenuOptionsSession owned(base,All());Backend reentrant;Persistence saved;owned.Begin(3,4);Draft(owned,7,1);unsigned blocked=0;
    reentrant.hook=[&]{
        Reject([&]{owned.Set("windowWidth",1280);},"Backend reentered Set");Reject([&]{owned.ResetDefaults();},"Backend reentered defaults");Reject([&]{owned.Cancel(3,4);},"Backend reentered Cancel");Reject([&]{owned.Discard();},"Backend reentered Discard");
        Reject([&]{owned.CommitNonResolution(3,4,reentrant.Callback(),saved.Callback());},"Backend reentered partial commit");Reject([&]{owned.RejectResolution(3,4,reentrant.Callback());},"Backend reentered preview rejection");++blocked;
    };
    owned.PreviewResolution(3,4,reentrant.Callback());owned.ConfirmResolution(3,4,reentrant.Callback(),saved.Callback());Check(blocked==2 && owned.Active() && !owned.ResolutionPreviewActive(),"Backend reentrancy guard lost owned preview state");reentrant.hook={};owned.Discard();
    MenuOptionsSession threaded(base,All());Backend threadBackend;Persistence threadDisk;threaded.Begin(4,5);Draft(threaded,6,1);threaded.PreviewResolution(4,5,threadBackend.Callback());std::exception_ptr failure;
    std::thread foreign([&]{try{
        Reject([&]{threaded.ResolutionChanged();},"Foreign thread read cached preview");Reject([&]{threaded.ResolutionPreviewActive();},"Foreign thread queried preview");Reject([&]{threaded.CommitNonResolution(4,5,threadBackend.Callback(),threadDisk.Callback());},"Foreign thread partial committed");
        Reject([&]{threaded.ConfirmResolution(4,5,threadBackend.Callback(),threadDisk.Callback());},"Foreign thread confirmed");Reject([&]{threaded.RejectResolution(4,5,threadBackend.Callback());},"Foreign thread rejected");Reject([&]{threaded.Cancel(4,5);},"Foreign thread cancelled");Reject([&]{threaded.Discard();},"Foreign thread discarded");
    }catch(...){failure=std::current_exception();}});foreign.join();if(failure)std::rethrow_exception(failure);threaded.Discard();
}
static void ActualOwnedStore(const std::wstring& owned){
    const MenuOptionsValues base;const std::string v1="ZEROSIS_PRIVATE_MENU_OPTIONS_V1\nnoBasicHelp=0\nhideTouchHelp=0\nuiCueVolumePercent=100\nwindowWidth=1280\nwindowHeight=720\nfullscreen=0\nvsync=1\n";
    const std::string v2="ZEROSIS_PRIVATE_MENU_OPTIONS_V2\nnoBasicHelp=0\nhideTouchHelp=0\nuiCueVolumePercent=100\nwindowWidth=1280\nwindowHeight=720\nfullscreen=0\nvsync=1\npolicyInfo=0\n";
    const std::string v3="ZEROSIS_PRIVATE_MENU_OPTIONS_V3\nnoBasicHelp=0\nhideTouchHelp=0\nuiCueVolumePercent=100\nwindowWidth=1280\nwindowHeight=720\nfullscreen=0\nvsync=1\npolicyInfo=0\nnoRewardPopups=0\n";
    Check(MenuOptionsValues::Decode(v1)==base && MenuOptionsValues::Decode(v2)==base && MenuOptionsValues::Encode(base)==v3,"Legacy V1/V2 reads or explicit appended V3 bytes changed");
    Reject([&]{MenuOptionsValues::Decode(v2+"preview=1\n");},"Transient preview entered canonical V2");Reject([&]{MenuOptionsValues::Decode("ZEROSIS_PRIVATE_MENU_OPTIONS_V4\n");},"Unknown schema was accepted");
    const auto first=Child(owned,L"v1_confirm");const auto settings=first+L"\\menu-options.zssettings";NewFile(settings,v1);MenuOptionsValues confirmed;
    {
        MenuOptionsStore store(first);Check(store.SchemaVersion()==1 && Read(settings)==v1 && store.Read()==base && Read(settings)==v1,"Reading V1 rewrote original bytes");
        MenuOptionsSession s(store.Read(),All());Backend b;s.Begin(1,2);Draft(s,15,3);const auto draft=s.Cached();confirmed=DisplayOnly(base,draft);
        s.PreviewResolution(1,2,b.Callback());Check(Read(settings)==v1,"Unconfirmed preview wrote V1 preference bytes");s.ConfirmResolution(1,2,b.Callback(),[&](const MenuOptionsValues& v){store.WriteAtomic(v);});
        Check(s.Active() && store.SchemaVersion()==3 && store.Read()==confirmed && Read(settings)==MenuOptionsValues::Encode(confirmed) && s.Cached()==draft,"Real atomic V1-toV3 display confirmation did not preserve other cached edits");s.Discard();
    }
    {MenuOptionsStore reopened(first);Check(reopened.SchemaVersion()==3 && reopened.Read()==confirmed,"Restart readback lost exactly confirmed canonical resolution");}
    const auto blocked=Child(owned,L"blocked_atomic");NewFile(blocked+L"\\menu-options.zssettings",v2);NewFile(blocked+L"\\menu-options.pending","owned-existing-pending");
    {
        MenuOptionsStore store(blocked);MenuOptionsSession s(store.Read(),All());Backend b;s.Begin(1,2);Draft(s,7,2);const auto draft=s.Cached();s.PreviewResolution(1,2,b.Callback());
        Reject([&]{s.ConfirmResolution(1,2,b.Callback(),[&](const MenuOptionsValues& v){store.WriteAtomic(v);});},"Real CREATE_NEW atomic failure was accepted");
        Check(!s.ResolutionPreviewActive() && s.Active() && !s.Faulted() && s.Committed()==base && s.Cached()==NonDisplayOnly(draft,base) && b.actual==base,"Real store failure did not restore display/session exactly");
        Check(Read(blocked+L"\\menu-options.zssettings")==v2 && Read(blocked+L"\\menu-options.pending")=="owned-existing-pending","Atomic failure overwrote prior canonical or preexisting pending bytes");s.Discard();
        MenuOptionsSession partial(store.Read(),All());Backend original;partial.Begin(7,8);Draft(partial,9,1);const auto allDrafts=partial.Cached();
        Reject([&]{partial.CommitNonResolution(7,8,original.Callback(),[&](const MenuOptionsValues& v){store.WriteAtomic(v);});},"Real partial atomic persistence failure was accepted");
        Check(partial.Active() && !partial.Faulted() && !partial.ResolutionPreviewActive() && partial.Committed()==base && partial.Cached()==allDrafts && original.actual==base && Read(blocked+L"\\menu-options.zssettings")==v2,"Real partial atomic failure did not preserve pending display, other drafts and prior bytes");partial.Discard();
    }
    const auto originalOk=Child(owned,L"original_ok_then_no");
    {
        MenuOptionsStore store(originalOk);MenuOptionsSession s(store.Read(),All());Backend b;s.Begin(8,9);Draft(s,13,4);const auto expected=NonDisplayOnly(s.Cached(),base);
        const auto persist=[&](const MenuOptionsValues& v){store.WriteAtomic(v);};s.CommitNonResolution(8,9,b.Callback(),persist);const auto bytes=Read(originalOk+L"\\menu-options.zssettings");
        s.PreviewResolution(8,9,b.Callback());s.RejectResolution(8,9,b.Callback());Check(store.Read()==expected && s.Committed()==expected && s.Cached()==expected && b.actual==expected && Read(originalOk+L"\\menu-options.zssettings")==bytes,"Original OK then No lost its already published non-display settings");s.Discard();
    }
}
int wmain(int argc,wchar_t** argv){try{
    if(argc!=2)throw std::runtime_error("Expected one exact owned file-only test directory");const std::wstring owned(argv[1]);const auto attrs=GetFileAttributesW(owned.c_str());
    if(owned.size()<3 || owned[1]!=L':' || attrs==INVALID_FILE_ATTRIBUTES || !(attrs&FILE_ATTRIBUTE_DIRECTORY) || attrs&FILE_ATTRIBUTE_REPARSE_POINT)throw std::runtime_error("Invalid owned preference fixture directory");
    Workflows();FailuresAndModal();LifetimeAndRegression();ActualOwnedStore(owned);
    std::cout<<"{\"status\":\"PASS_TRANSIENT_RESOLUTION_PREVIEW_AND_CANONICAL_V3_STORE\",\"checks\":"<<checks<<",\"combined_preference_resolution_cases\":96,\"display_only_and_original_ok_workflows\":480,\"actual_owned_store_cases\":3,\"v1_read_preserved\":true,\"legacy_v1_v2_read_bytes_preserved\":true,\"explicit_new_write_schema\":3,\"display_only_preview_excludes_other_drafts\":true,\"non_resolution_partial_commit_preserves_pending_display\":true,\"discard_restore_failure_does_not_escape_destructor\":true,\"native_window_sdk_gpu_or_audio_executed\":false}"<<std::endl;return 0;
}catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}
