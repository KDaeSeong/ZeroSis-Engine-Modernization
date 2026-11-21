#pragma once

#include <exception>
#include <atomic>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>

namespace ZeroSisHost {

// Private Host presentation preferences. These are neither retail INI keys nor
// SDK/save options. Never serialize this contract into a GameCore save stream.
struct MenuOptionsValues final {
    bool noBasicHelp=false,hideTouchHelp=false;
    int uiCueVolumePercent=100,windowWidth=1280,windowHeight=720;
    bool fullscreen=false,vsync=true,policyInfo=false,noRewardPopups=false;
    bool operator==(const MenuOptionsValues& v) const noexcept {
        return noBasicHelp==v.noBasicHelp && hideTouchHelp==v.hideTouchHelp &&
            uiCueVolumePercent==v.uiCueVolumePercent && windowWidth==v.windowWidth &&
            windowHeight==v.windowHeight && fullscreen==v.fullscreen && vsync==v.vsync && policyInfo==v.policyInfo && noRewardPopups==v.noRewardPopups;
    }
    bool operator!=(const MenuOptionsValues& v) const noexcept {return !(*this==v);}
    static void Validate(const MenuOptionsValues& v) {
        if(v.uiCueVolumePercent<0 || v.uiCueVolumePercent>100 ||
           v.windowWidth<800 || v.windowWidth>7680 || v.windowHeight<600 || v.windowHeight>4320)
            throw std::invalid_argument("Private menu option value is outside its supported range");
    }
    // V1/V2 are accepted without rewriting. A changed explicit commit publishes
    // V3. Callers seed legacy policyInfo from its actual old backend;
    // it is not a retail setting or a GameCore save-schema migration.
    static int SchemaVersion(const std::string& bytes) {
        if(bytes.rfind("ZEROSIS_PRIVATE_MENU_OPTIONS_V1\n",0)==0)return 1;
        if(bytes.rfind("ZEROSIS_PRIVATE_MENU_OPTIONS_V2\n",0)==0)return 2;
        if(bytes.rfind("ZEROSIS_PRIVATE_MENU_OPTIONS_V3\n",0)==0)return 3;
        throw std::invalid_argument("Private menu options schema is unknown");
    }
    static std::string Encode(const MenuOptionsValues& v) {return Canonical(v,3);}
private:
    static std::string Canonical(const MenuOptionsValues& v,int version) {
        Validate(v);
        return std::string("ZEROSIS_PRIVATE_MENU_OPTIONS_V")+std::to_string(version)+"\n"+
            "noBasicHelp="+(v.noBasicHelp?"1":"0")+"\nhideTouchHelp="+(v.hideTouchHelp?"1":"0")+
            "\nuiCueVolumePercent="+std::to_string(v.uiCueVolumePercent)+
            "\nwindowWidth="+std::to_string(v.windowWidth)+"\nwindowHeight="+std::to_string(v.windowHeight)+
            "\nfullscreen="+(v.fullscreen?"1":"0")+"\nvsync="+(v.vsync?"1":"0")+"\n"+
            (version>=2?std::string("policyInfo=")+(v.policyInfo?"1":"0")+"\n":std::string{})+
            (version>=3?std::string("noRewardPopups=")+(v.noRewardPopups?"1":"0")+"\n":std::string{});
    }
public:
    static MenuOptionsValues Decode(const std::string& bytes) {
        if(bytes.size()>512)throw std::invalid_argument("Private menu options file is too large");
        const int version=SchemaVersion(bytes);
        const std::string prefix=std::string("ZEROSIS_PRIVATE_MENU_OPTIONS_V")+std::to_string(version)+"\n";
        std::size_t at=prefix.size();
        const auto number=[&](const char* key)->int {
            const std::string name=std::string(key)+"=";
            if(bytes.compare(at,name.size(),name)!=0)throw std::invalid_argument("Private menu options key/order is invalid");
            at+=name.size();const auto start=at;int value=0;
            while(at<bytes.size() && bytes[at]>='0' && bytes[at]<='9'){
                if(at-start>=5)throw std::invalid_argument("Private menu options integer is too large");
                value=value*10+(bytes[at++]-'0');
            }
            if(at==start || at>=bytes.size() || bytes[at++]!='\n')
                throw std::invalid_argument("Private menu options integer is malformed");
            return value;
        };
        const auto boolean=[&](const char* key)->bool {
            const int value=number(key);
            if(value!=0 && value!=1)throw std::invalid_argument("Private menu options boolean is malformed");
            return value!=0;
        };
        MenuOptionsValues v;v.noBasicHelp=boolean("noBasicHelp");v.hideTouchHelp=boolean("hideTouchHelp");
        v.uiCueVolumePercent=number("uiCueVolumePercent");v.windowWidth=number("windowWidth");
        v.windowHeight=number("windowHeight");v.fullscreen=boolean("fullscreen");v.vsync=boolean("vsync");
        if(version>=2)v.policyInfo=boolean("policyInfo");
        if(version>=3)v.noRewardPopups=boolean("noRewardPopups");
        Validate(v);
        if(at!=bytes.size() || Canonical(v,version)!=bytes)
            throw std::invalid_argument("Private menu options are not canonical or contain trailing data");
        return v;
    }
};

struct MenuOptionsCapabilities final {
    bool noBasicHelp=false,uiCueVolume=false,windowResolution=false,fullscreen=false,vsync=false,policyInfo=false,noRewardPopups=false;
    bool Supports(const std::string& key) const {
        if(key=="noBasicHelp")return noBasicHelp;
        if(key=="hideTouchHelp")return true;
        if(key=="uiCueVolumePercent")return uiCueVolume;
        if(key=="windowWidth" || key=="windowHeight")return windowResolution;
        if(key=="fullscreen")return fullscreen;
        if(key=="vsync")return vsync;
        if(key=="policyInfo")return policyInfo;
        if(key=="noRewardPopups")return noRewardPopups;
        throw std::invalid_argument("Unknown private menu option capability");
    }
};

class MenuOptionsSession final {
public:
    using ApplyBackend=std::function<MenuOptionsValues(const MenuOptionsValues&)>;
    // Must atomically persist the complete canonical value or leave the old
    // bytes intact and throw. The store below supplies this strict callback.
    using Persist=std::function<void(const MenuOptionsValues&)>;
    MenuOptionsSession(MenuOptionsValues initial,MenuOptionsCapabilities capabilities)
        :owner_(std::this_thread::get_id()),committed_(initial),cached_(initial),caps_(capabilities) {
        MenuOptionsValues::Validate(initial);
    }
    MenuOptionsSession(const MenuOptionsSession&)=delete;
    MenuOptionsSession& operator=(const MenuOptionsSession&)=delete;
    // Bind the Host's stable confirmed snapshot only after its fallible setup.
    // The pointer is never replaced and no callback runs after persistence.
    void BindNoRewardPopupsSnapshot(const std::shared_ptr<std::atomic<bool>>& snapshot) {
        Require();
        if(active_ || backendOperation_ || !snapshot || noRewardPopupsSnapshot_)
            throw std::logic_error("Reward preference snapshot needs one inactive owned binding");
        noRewardPopupsSnapshot_=snapshot;PublishNoRewardPopups();
    }
    void Begin(int owner,int turn) {
        Require();
        if(active_ || backendOperation_ || owner<0 || turn<0)throw std::logic_error("Menu options need one inactive owned transaction");
        player_=owner;turn_=turn;cached_=committed_;active_=true;
    }
    void Set(const std::string& key,int value) {
        RequireEditable();
        if(!caps_.Supports(key))throw std::logic_error("Menu option has no actual Host backend");
        auto next=cached_;
        if(key=="uiCueVolumePercent")next.uiCueVolumePercent=value;
        else if(key=="windowWidth")next.windowWidth=value;
        else if(key=="windowHeight")next.windowHeight=value;
        else {
            if(value!=0 && value!=1)throw std::invalid_argument("Menu option requires a boolean integer");
            if(key=="noBasicHelp")next.noBasicHelp=value!=0;
            else if(key=="hideTouchHelp")next.hideTouchHelp=value!=0;
            else if(key=="fullscreen")next.fullscreen=value!=0;
            else if(key=="vsync")next.vsync=value!=0;
            else if(key=="policyInfo")next.policyInfo=value!=0;
            else if(key=="noRewardPopups")next.noRewardPopups=value!=0;
            else throw std::invalid_argument("Unknown private menu option");
        }
        MenuOptionsValues::Validate(next);cached_=next;
    }
    int Get(const std::string& key,bool cached=true) const {
        Require();if(cached && !active_)throw std::logic_error("Cached menu options need a transaction");
        const auto& v=cached?cached_:committed_;
        if(key=="noBasicHelp")return v.noBasicHelp?1:0;
        if(key=="hideTouchHelp")return v.hideTouchHelp?1:0;
        if(key=="uiCueVolumePercent")return v.uiCueVolumePercent;
        if(key=="windowWidth")return v.windowWidth;
        if(key=="windowHeight")return v.windowHeight;
        if(key=="fullscreen")return v.fullscreen?1:0;
        if(key=="vsync")return v.vsync?1:0;
        if(key=="policyInfo")return v.policyInfo?1:0;
        if(key=="noRewardPopups")return v.noRewardPopups?1:0;
        throw std::invalid_argument("Unknown private menu option");
    }
    void ResetDefaults() {
        RequireEditable();const MenuOptionsValues defaults;
        if(caps_.noBasicHelp)cached_.noBasicHelp=defaults.noBasicHelp;
        cached_.hideTouchHelp=defaults.hideTouchHelp;
        if(caps_.uiCueVolume)cached_.uiCueVolumePercent=defaults.uiCueVolumePercent;
        if(caps_.windowResolution){cached_.windowWidth=defaults.windowWidth;cached_.windowHeight=defaults.windowHeight;}
        if(caps_.fullscreen)cached_.fullscreen=defaults.fullscreen;
        if(caps_.vsync)cached_.vsync=defaults.vsync;
        if(caps_.policyInfo)cached_.policyInfo=defaults.policyInfo;
        if(caps_.noRewardPopups)cached_.noRewardPopups=defaults.noRewardPopups;
    }
    void Apply(int owner,int turn,const ApplyBackend& apply,const Persist& persist) {
        Scope(owner,turn);RequireEditable();
        if(!apply || !persist)throw std::invalid_argument("Menu options require actual apply/readback and atomic persistence");
        if(cached_==committed_){active_=false;return;}
        BackendOperation operation(backendOperation_);CommitCandidate(cached_,apply,persist);active_=false;
    }
    bool ResolutionChanged() const {
        RequireActive();return cached_.windowWidth!=committed_.windowWidth || cached_.windowHeight!=committed_.windowHeight || cached_.fullscreen!=committed_.fullscreen;
    }
    bool ResolutionPreviewActive() const {
        if(owner_!=std::this_thread::get_id())throw std::logic_error("Menu preview status requires its owner thread");
        return resolutionPreview_;
    }
    // The original OK path commits Game/Graphics/Audio before asking about a
    // changed resolution. The independent Apply Resolution button skips this.
    // Both paths retain the owned options transaction and its remaining draft.
    void CommitNonResolution(int owner,int turn,const ApplyBackend& apply,const Persist& persist) {
        Scope(owner,turn);RequireEditable();
        if(!apply || !persist)throw std::invalid_argument("Partial menu commit requires actual apply/readback and atomic persistence");
        auto candidate=cached_;CopyResolution(candidate,committed_);
        if(candidate==committed_)return;
        BackendOperation operation(backendOperation_);CommitCandidate(candidate,apply,persist);
    }
    void PreviewResolution(int owner,int turn,const ApplyBackend& apply) {
        Scope(owner,turn);RequireEditable();
        if(!apply || !ResolutionChanged())throw std::invalid_argument("Resolution preview needs one changed supported display and actual backend");
        // Copy before changing a backend. The snapshot exists only while the
        // controller owns this preview and must be cleared before its Window
        // dies. Cancel/Discard can then restore without an SDK player/turn.
        ApplyBackend snapshot(apply);auto candidate=committed_;CopyResolution(candidate,cached_);
        resolutionRollback_.swap(snapshot);resolutionCandidate_=candidate;resolutionPreview_=true;
        BackendOperation operation(backendOperation_);
        try {
            if(apply(candidate)!=candidate)throw std::runtime_error("Host did not read back the exact resolution preview");
        }catch(...) {
            const auto original=std::current_exception();RestorePreview(resolutionRollback_);std::rethrow_exception(original);
        }
    }
    void ConfirmResolution(int owner,int turn,const ApplyBackend& apply,const Persist& persist) {
        Scope(owner,turn);RequirePreview();
        if(!apply || !persist)throw std::invalid_argument("Resolution confirmation needs actual readback and atomic persistence");
        BackendOperation operation(backendOperation_);
        try {
            if(apply(resolutionCandidate_)!=resolutionCandidate_)throw std::runtime_error("Host resolution preview confirmation readback mismatch");
            persist(resolutionCandidate_);
        }catch(...) {
            const auto original=std::current_exception();RestorePreview(resolutionRollback_);std::rethrow_exception(original);
        }
        // No fallible operation follows successful atomic publication. Only
        // the confirmed display baseline changes; other cached edits survive.
        committed_=resolutionCandidate_;PublishNoRewardPopups();ClearPreview();
    }
    void RejectResolution(int owner,int turn,const ApplyBackend& apply) {
        Scope(owner,turn);RequirePreview();
        if(!apply)throw std::invalid_argument("Resolution rejection requires its actual backend");
        BackendOperation operation(backendOperation_);RestorePreview(apply);
    }
    void Cancel(int owner,int turn) {
        Scope(owner,turn);
        if(backendOperation_)throw std::logic_error("Cannot cancel menu options during a backend operation");
        if(resolutionPreview_){BackendOperation operation(backendOperation_);RestorePreview(resolutionRollback_);}
        cached_=committed_;active_=false;
    }
    // Shutdown discards uncommitted edits without requiring a still-live SDK
    // player/turn. A preview snapshot is restored while its controller/Window
    // still lives, then released on every path. Restore failure faults/closes
    // this session and is not thrown from an owner-thread controller destructor.
    // A wrong thread or a reentrant backend call still violates ownership.
    void Discard() {
        if(owner_!=std::this_thread::get_id())throw std::logic_error("Menu shutdown requires its owner thread");
        if(backendOperation_)throw std::logic_error("Cannot discard menu options during a backend operation");
        if(resolutionPreview_){
            BackendOperation operation(backendOperation_);
            try{RestorePreview(resolutionRollback_);}catch(...){FaultPreview();}
        }
        cached_=committed_;active_=false;
    }
    bool Active() const {
        if(owner_!=std::this_thread::get_id())throw std::logic_error("Menu status requires its owner thread");
        return active_;
    }
    bool Faulted() const noexcept {return faulted_;}
    bool Supports(const std::string& key) const {Require();return caps_.Supports(key);}
    const MenuOptionsValues& Committed() const {Require();return committed_;}
    const MenuOptionsValues& Cached() const {RequireActive();return cached_;}
private:
    void PublishNoRewardPopups() noexcept {
        if(noRewardPopupsSnapshot_)noRewardPopupsSnapshot_->store(committed_.noRewardPopups,std::memory_order_release);
    }
    class BackendOperation final {
    public:
        explicit BackendOperation(bool& active):active_(active){
            if(active_)throw std::logic_error("Menu backend operations cannot reenter");active_=true;
        }
        ~BackendOperation() noexcept {active_=false;}
        BackendOperation(const BackendOperation&)=delete;
        BackendOperation& operator=(const BackendOperation&)=delete;
    private:bool& active_;
    };
    static void CopyResolution(MenuOptionsValues& target,const MenuOptionsValues& source) noexcept {
        target.windowWidth=source.windowWidth;target.windowHeight=source.windowHeight;target.fullscreen=source.fullscreen;
    }
    void ClearPreview() noexcept {
        resolutionPreview_=false;ApplyBackend{}.swap(resolutionRollback_);
    }
    void FaultPreview() noexcept {
        faulted_=true;active_=false;cached_=committed_;ClearPreview();
    }
    void RestorePreview(const ApplyBackend& apply) {
        try{
            if(!apply || apply(committed_)!=committed_)throw std::runtime_error("Host resolution restore readback mismatch");
        }catch(...){
            FaultPreview();throw std::runtime_error("Host resolution rollback failed; session is faulted");
        }
        CopyResolution(cached_,committed_);ClearPreview();
    }
    void CommitCandidate(const MenuOptionsValues& candidate,const ApplyBackend& apply,const Persist& persist) {
        try{
            if(apply(candidate)!=candidate)throw std::runtime_error("Host did not read back requested menu options");
            persist(candidate);
        }catch(...){
            const auto original=std::current_exception();
            try{
                if(apply(committed_)!=committed_)throw std::runtime_error("Host option rollback readback mismatch");
            }catch(...){
                faulted_=true;active_=false;
                throw std::runtime_error("Host menu option rollback failed; session is faulted");
            }
            std::rethrow_exception(original);
        }
        committed_=candidate;PublishNoRewardPopups();
    }
    void Require() const {
        if(owner_!=std::this_thread::get_id() || faulted_)
            throw std::logic_error("Menu options require their healthy owner thread");
    }
    void RequireActive() const {Require();if(!active_)throw std::logic_error("Menu options transaction is inactive");}
    void RequireEditable() const {
        RequireActive();if(resolutionPreview_ || backendOperation_)throw std::logic_error("Menu resolution preview is modal or its backend is busy");
    }
    void RequirePreview() const {
        RequireActive();if(!resolutionPreview_ || backendOperation_)throw std::logic_error("Resolution confirmation requires its idle owned preview");
    }
    void Scope(int owner,int turn) const {
        RequireActive();
        if(owner!=player_ || turn!=turn_)throw std::logic_error("Menu options lost their captured player/turn");
    }
    std::thread::id owner_;
    MenuOptionsValues committed_,cached_;
    std::shared_ptr<std::atomic<bool>> noRewardPopupsSnapshot_;
    MenuOptionsValues resolutionCandidate_{};ApplyBackend resolutionRollback_;
    MenuOptionsCapabilities caps_;
    int player_=-1,turn_=-1;
    bool active_=false,faulted_=false,resolutionPreview_=false,backendOperation_=false;
};
}
