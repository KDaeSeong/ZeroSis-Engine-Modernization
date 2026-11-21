// Nonwindow component fixture. Native methods/fragments are inserted verbatim
// from the current headers; SDK/Lua/OS and snapshot-I/O APIs are substitutes.
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <deque>
#include <exception>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include "UiSaveMenuContract.h"
using namespace ZeroSisHost;
enum class UiPopupKind { Ranking,Production,Research,ResearchTree,CityCapture,LeaderHead,CityView,TechAward,UnitPanel,DeclareWar,TopPanel,TradeRoute,SocialPolicy,EconomicOverview,EconomicGeneral,EconomicHappiness,ActionInfoPanel,NotificationPanel,GameMenu,SaveMenu };
struct GameMenuRequest final {
    enum class Kind { Open,QuickSave,Unavailable,OpenSaveMenu };
    Kind kind;int owner,turn;std::string action;
};
enum class UiInputKind : std::uint32_t { KeyDown=1, LeftClick=2, PointerMove=3, Scroll=4, RightClick=5, TextInput=6 };
struct UiInputRequest final {
    UiInputKind kind=UiInputKind::KeyDown;
    std::uint64_t key=0;
    bool consumed=false;
    double delta=0.0;
};
class UiPopupContext;
struct lua_State {UiPopupContext* context;};
using lua_CFunction=int(*)(lua_State*);
using lua_Hook=void(*)(lua_State*,void*);
constexpr int LUA_MASKCOUNT=8,VK_ESCAPE=27,MAX_PLAYERS=64,NO_PLAYER=-1;
using PlayerTypes=int;
struct World {
    int player=0,turn=12,timer=1,decrements=0,frees=0,luaCalls=0,frontEndClears=0;
    bool alive=true,human=true,turnActive=true,initialized=true,multiplayer=false,network=false;
    bool playerMissing=false,lockHeld=true,busy=false,throwDecrement=false,throwAfterDecrement=false;
    bool snapshotIoFailure=false,closeLuaFailure=false,changeTurnInsideLua=false,unknownCloseFailure=false;
    bool loseLockOnPlayerQuery=false,faultObservedInsideScript=false,unknownSnapshotFailure=false;
    std::vector<std::string> trace;
};
static unsigned currentThread=7;
unsigned GetCurrentThreadId(){return currentThread;}
void lua_sethook(lua_State*,lua_Hook,int,int){}
const wchar_t* MAKEINTRESOURCEW(unsigned){return nullptr;}
void* LoadCursorW(void*,const wchar_t*){return nullptr;}
void SetCursor(void*){throw std::logic_error("No cursor call is permitted in the fixture");}
struct ICvPlayer1 {
    World& w;
    bool IsAlive()const{return w.alive;}
    bool IsHuman()const{return w.human;}
    bool IsTurnActive()const{return w.turnActive;}
};
struct ICvRandom1 {unsigned long GetSeed()const{return 12345;}};
struct ICvGame1 {
    World& w;
    bool IsFinalInitialized()const{return w.initialized;}
    bool IsGameMultiPlayer()const{return w.multiplayer;}
    bool IsNetworkMultiPlayer()const{return w.network;}
    int GetActivePlayer()const{return w.player;}
    int GetGameTurn()const{return w.turn;}
    ICvPlayer1* GetPlayer(PlayerTypes){
        if(w.loseLockOnPlayerQuery){w.lockHeld=false;throw std::logic_error("mock query lost owner lock");}
        return w.playerMissing?nullptr:new ICvPlayer1{w};
    }
    ICvRandom1* GetRandomNumberGenerator(){return new ICvRandom1;}
    void EndTurnTimerSemaphoreDecrement(){
        ++w.decrements;w.trace.push_back("sdk-timer-decrement");
        if(w.throwDecrement)throw std::runtime_error("mock SDK decrement failure");
        --w.timer;
        if(w.throwAfterDecrement)throw std::runtime_error("mock SDK decrement failed after mutation");
    }
};
struct GameDeals {void DestroyDeal(unsigned){throw std::logic_error("No deal is owned by a menu fixture");}};
struct ScriptSystem {
    World& w;unsigned depth=0;std::string lastError;
    bool IsQuiescent()const{return !depth && !w.busy;}
    bool CallCFunction(lua_State*,lua_CFunction,void*);
    const char* LastError()const{return lastError.c_str();}
    void FreeLuaThread(lua_State* state){++w.frees;w.trace.push_back("free-vm");delete state;}
};
struct HostState {
    struct Lock {World& w;bool HeldByCurrentThread()const{return w.lockHeld;}};
    World& w;unsigned gameThread=7;Lock gameLock;
    bool localSdkSessionBound=true,popupVisible=true,actionInfoActivationInProgress=false,leaderRootUp=false;
    int actionInfoOwner=0,actionInfoTurn=12,pendingLeaderMessages=0;
    std::vector<int> actionInfoAdapterRequests;
    std::function<void()> addPopup,addArrayPopup,addLeaderMessage,routeWarStateChanged,closeInformationalPopup,resolveCity;
    explicit HostState(World& world):w(world),gameLock{world}{}
    void Record(const std::string& value){w.trace.push_back(value);}
};
struct UserInterface {
    std::shared_ptr<HostState> host;
    explicit UserInterface(std::shared_ptr<HostState> value):host(std::move(value)){}
    void clearSelectedCities(){++host->w.frontEndClears;}
    void SetCityScreenViewingMode(bool){}
};
struct SdkStateSnapshot {
    static World* world;
    static std::array<int,2> Capture(const HostState& h){return {h.w.player,h.w.turn};}
    static void Write(const std::wstring&,const std::string&){
        if(world->unknownSnapshotFailure)throw 17;
        if(world->snapshotIoFailure)throw std::runtime_error("mock snapshot I/O failure");
    }
};
World* SdkStateSnapshot::world=nullptr;
struct UiInputDispatch {
    static int Dispatch(lua_State*){return 91;}
    static int CollectTargets(lua_State*){return 92;}
};
class UiPopupContext {
public:
    enum class TimerState {Released,Held,TransitionUnknown};
    HostState& host_;ScriptSystem& scripts_;std::unique_ptr<ICvGame1> game_;
    std::unique_ptr<int> pregame_,scratchDeal_,scriptUtility_;std::unique_ptr<GameDeals> deals_;
    std::shared_ptr<const UiSaveMenuCatalog> saveMenuCatalog_;
    lua_State* vm_=nullptr;lua_State* warCommandsVm_=nullptr;int* core_=nullptr;
    UiPopupKind kind_;UiPopupContext* economicOwner_=nullptr;std::wstring directory_=L"nonwindow";
    bool active_=true,dispatching_=false,faulted_=false,stopping_=false,externalRouting_=true;
    bool timerRecoveryFailed_=false,saveMenuInput_=false,saveMenuReady_=false,gameMenuReady_=false,gameMenuInput_=false;
    bool captureDecisionDone_=false,leaderDecisionDone_=false,pendingLeaderLeave_=false;
    bool ownsScratchDeal_=false,warInput_=false,economicVisibilityInitialized_=false;
    TimerState timerState_;unsigned sequence_,revision_=0,instructions_=0,callInstructionLimit_=0,scratchDealId_=0;
    int gameMenuOwner_=0,gameMenuTurn_=12,captureCity_=0;
    std::uint64_t gameMenuCursorToken_=0;
    UiInputKind saveMenuInputKind_=UiInputKind::KeyDown,gameMenuInputKind_=UiInputKind::KeyDown;
    std::vector<SaveMenuRequest> saveMenuRequests_;
    std::vector<GameMenuRequest> gameMenuRequests_;
    std::vector<int> actionInfoRequests_,warCommands_;
    bool actionInfoReady_=false;std::unique_ptr<int> topPanelPopup_,unitAction_;
    std::array<std::unique_ptr<UiPopupContext>,2> economicChildren_;
    std::array<bool,2> economicChildVisible_{{false,false}},economicChildVisibilityDirty_{{false,false}};
    static constexpr std::uint64_t EconomicGeneralKeyBase=1ULL<<48,EconomicHappinessKeyBase=2ULL<<48;
    struct EconomicVisibilityRequest {bool visible,first;};
    UiPopupContext(HostState& h,ScriptSystem& s,World& w,UiPopupKind kind,unsigned seq)
        :host_(h),scripts_(s),game_(new ICvGame1{w}),pregame_(new int(1)),kind_(kind),
         timerState_(kind==UiPopupKind::GameMenu?TimerState::Held:TimerState::Released),sequence_(seq){
        vm_=new lua_State{this};core_=pregame_.get();
        auto catalog=std::make_shared<UiSaveMenuCatalog>();
        catalog->nameAvailable=[](const std::string& name){return !name.empty();};saveMenuCatalog_=catalog;
        SdkStateSnapshot::world=&w;
    }
    // Fixture allocation cleanup is not a proof of the native destructor.
    ~UiPopupContext(){delete vm_;}
    static void Budget(lua_State*,void*){}
    static unsigned InstructionLimit(lua_CFunction){return 1000;}
#define SCRIPT_TOKEN(name,id) static int name(lua_State*){return id;}
    SCRIPT_TOKEN(CloseGameMenuLua,1) SCRIPT_TOKEN(Close,2)
    SCRIPT_TOKEN(StopNotificationPanelLua,3) SCRIPT_TOKEN(StopActionInfoPanelLua,4)
    SCRIPT_TOKEN(StopTopPanel,5) SCRIPT_TOKEN(StopUnitPanel,6)
    SCRIPT_TOKEN(AbortCapture,7) SCRIPT_TOKEN(AbortLeader,8)
    SCRIPT_TOKEN(Dispatch,9) SCRIPT_TOKEN(Snapshot,10)
    SCRIPT_TOKEN(ResearchDirty,11) SCRIPT_TOKEN(PolicyDirty,12)
    SCRIPT_TOKEN(ValidatePolicyCommand,13) SCRIPT_TOKEN(RefreshNotificationPanelLua,14)
    SCRIPT_TOKEN(ObserveActive,15) SCRIPT_TOKEN(SetEconomicVisibilityLua,16)
#undef SCRIPT_TOKEN
void Require() const {
        if(host_.gameThread!=GetCurrentThreadId() || !host_.gameLock.HeldByCurrentThread())
            throw std::logic_error("UI script execution requires the GameCore owner lock");
    }
void RequireLocalMenuPlayer(int owner,int turn){
        Require();
        if(!game_ || !host_.localSdkSessionBound || !game_->IsFinalInitialized() ||
           game_->IsGameMultiPlayer() || game_->IsNetworkMultiPlayer() || owner<0 || owner>=MAX_PLAYERS ||
           owner!=game_->GetActivePlayer() || turn!=game_->GetGameTurn())
            throw std::logic_error("GameMenu requires its actual initialized local player and turn");
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(owner)));
        if(!player || !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive())
            throw std::logic_error("GameMenu requires the living active human turn");
    }
void RequireGameMenuOwner(){
        if((kind_!=UiPopupKind::GameMenu && kind_!=UiPopupKind::SaveMenu) || !externalRouting_ || !pregame_ || faulted_)
            throw std::logic_error("GameMenu query is outside its original owned context");
        RequireOwnedMenuPlayer();
    }
void RequireSaveMenuOwner(){
        if(kind_!=UiPopupKind::SaveMenu || !externalRouting_ || !saveMenuCatalog_ || !saveMenuCatalog_->nameAvailable || faulted_)
            throw std::logic_error("SaveMenu query is outside its immutable owned child context");
        RequireOwnedMenuPlayer();
    }
void QueueSaveMenuRequest(SaveMenuRequest::Kind kind,const char* name){
        RequireSaveMenuOwner();
        if(!active_ || !dispatching_ || !saveMenuInput_ || saveMenuReady_ || timerState_!=TimerState::Released ||
           (saveMenuInputKind_!=UiInputKind::LeftClick && saveMenuInputKind_!=UiInputKind::KeyDown))
            throw std::logic_error("SaveMenu callback requires its original owned input boundary");
        if(kind==SaveMenuRequest::Kind::Save){
            if(!saveMenuRequests_.empty() || !name || !*name || std::strlen(name)>128 || Utf8Length(name)>32)
                throw std::invalid_argument("SaveMenu named request is invalid or duplicated");
            if(!saveMenuCatalog_->nameAvailable(std::string(name)))
                throw std::invalid_argument("SaveMenu named request is unavailable");
        }else if(saveMenuRequests_.size()>1 || (!saveMenuRequests_.empty() && saveMenuRequests_.front().kind!=SaveMenuRequest::Kind::Save))
            throw std::logic_error("SaveMenu close request is duplicated or out of order");
        saveMenuRequests_.push_back({kind,gameMenuOwner_,gameMenuTurn_,name?name:""});
        std::printf("INTERACTIVE_SAVE_MENU_REQUEST_QUEUED=%u|%d|%d\n",static_cast<unsigned>(kind),gameMenuOwner_,gameMenuTurn_);
    }
std::vector<SaveMenuRequest> TakeSaveMenuRequests(){
        Require();RequireSaveMenuOwner();
        if(dispatching_ || saveMenuInput_ || faulted_ || !scripts_.IsQuiescent() || timerState_!=TimerState::Released)
            throw std::logic_error("SaveMenu requests require a completed timer-free child callback");
        if(!saveMenuReady_){
            if(!saveMenuRequests_.empty())throw std::logic_error("SaveMenu has an uncommitted callback request");
            return {};
        }
        if(active_ || saveMenuRequests_.empty() || saveMenuRequests_.size()>2 ||
           saveMenuRequests_.back().kind!=SaveMenuRequest::Kind::Close ||
           (saveMenuRequests_.size()==2 && saveMenuRequests_.front().kind!=SaveMenuRequest::Kind::Save))
            throw std::logic_error("SaveMenu command has not completed its original save/return boundary");
        for(const auto& request:saveMenuRequests_)
            if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn())
                throw std::logic_error("SaveMenu owner or turn changed before handoff");
        std::vector<SaveMenuRequest> result;result.swap(saveMenuRequests_);saveMenuReady_=false;return result;
    }
void Stop(){
        Require();
        if(!vm_)return;
        if(economicOwner_){
            if(active_ || timerState_!=TimerState::Released || !scripts_.IsQuiescent())
                throw std::logic_error("Embedded economic VM must be hidden and timer-free before release");
            scripts_.FreeLuaThread(vm_);vm_=nullptr;ReleaseWarResources();pregame_.reset();game_.reset();core_=nullptr;
            std::printf("UI_POPUP_CONTEXT_CLOSED=%u\n",sequence_);return;
        }
        stopping_=true;
        try{CloseInformationalPopup();}
        catch(const std::exception& error){
            Require();
            if((kind_!=UiPopupKind::GameMenu && kind_!=UiPopupKind::SaveMenu) ||
               timerRecoveryFailed_ || timerState_!=TimerState::Released || !scripts_.IsQuiescent())throw;
            std::fprintf(stderr,"UI_POPUP_MENU_STOP_CLOSE_FAILURE=%s\n",error.what());
            Fault();
        }catch(...){
            Require();
            if((kind_!=UiPopupKind::GameMenu && kind_!=UiPopupKind::SaveMenu) ||
               timerRecoveryFailed_ || timerState_!=TimerState::Released || !scripts_.IsQuiescent())throw;
            std::fprintf(stderr,"UI_POPUP_MENU_STOP_CLOSE_FAILURE=unknown\n");
            Fault();
        }
        if(kind_==UiPopupKind::GameMenu)RestoreGameMenuCursor();
        if(kind_==UiPopupKind::EconomicOverview){
            ApplyEconomicVisibility(false);
            for(auto& child:economicChildren_)if(child){child->Stop();child.reset();}
        }
        if(timerRecoveryFailed_ || timerState_==TimerState::TransitionUnknown)
            throw std::runtime_error("UI popup timer state is uncertain; refusing to retry a timer transition");
        if(timerState_!=TimerState::Released)
            throw std::logic_error("UI popup timer must be balanced before context destruction");
        if(!scripts_.IsQuiescent())throw std::logic_error("Cannot stop UI popup VM during a script callback");
        if(!externalRouting_){host_.addPopup={};host_.closeInformationalPopup={};}
        scripts_.FreeLuaThread(vm_);vm_=nullptr;ReleaseWarResources();pregame_.reset();game_.reset();core_=nullptr;
        std::printf("UI_POPUP_CONTEXT_CLOSED=%u\n",sequence_);
    }
void CloseInformationalPopup(){
        Require();
        if(!vm_)return;
        if((kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SaveMenu) && !faulted_){
            try{if(kind_==UiPopupKind::SaveMenu)RequireSaveMenuOwner();else RequireGameMenuOwner();}
            catch(...){if(!faulted_)throw;}
        }
        if(kind_==UiPopupKind::SaveMenu){
            if(!faulted_ && active_){DispatchInput(UiInputKind::KeyDown,VK_ESCAPE);TakeSaveMenuRequests();}
            active_=false;saveMenuRequests_.clear();saveMenuReady_=false;return;
        }
        if(IsNotificationInputPanel()){
            if(!faulted_)Call(kind_==UiPopupKind::NotificationPanel?&StopNotificationPanelLua:&StopActionInfoPanelLua,nullptr);
            active_=false;actionInfoRequests_.clear();actionInfoReady_=false;return;
        }
        if(kind_==UiPopupKind::TopPanel){
            if(!faulted_)Call(&StopTopPanel,nullptr);
            active_=false;topPanelPopup_.reset();gameMenuRequests_.clear();gameMenuReady_=false;return;
        }
        if(kind_==UiPopupKind::UnitPanel){
            if(!faulted_)Call(&StopUnitPanel,nullptr);
            active_=false;unitAction_.reset();return;
        }
        if(faulted_){
            if(timerRecoveryFailed_ || timerState_!=TimerState::Released)
                throw std::runtime_error("Faulted UI popup has an uncertain timer state; refusing Lua reentry");
            active_=false;if(!economicOwner_)host_.popupVisible=false;
            if(kind_==UiPopupKind::EconomicOverview)ApplyEconomicVisibility(false);
            return;
        }
        if(!active_){if(kind_==UiPopupKind::EconomicOverview)ApplyEconomicVisibility(false);return;}
        if(kind_==UiPopupKind::CityCapture && !captureDecisionDone_){
            if(!stopping_)throw std::logic_error("A captured city requires an explicit original decision before closing");
            Call(&AbortCapture,nullptr);active_=false;host_.popupVisible=false;
            host_.Record("ui-city-capture-abandoned-on-session-stop:"+std::to_string(captureCity_));return;
        }
        if(kind_==UiPopupKind::LeaderHead && !leaderDecisionDone_){
            if(!stopping_)throw std::logic_error("Leader message requires its original return callback before closing");
            Call(&AbortLeader,nullptr);pendingLeaderLeave_=false;host_.leaderRootUp=false;
            active_=false;host_.popupVisible=false;
            host_.Record("ui-leader-message-abandoned-on-session-stop");return;
        }
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
        if(windowPresentation_ && kind_==UiPopupKind::Ranking && !stopping_ && !presentationFailed_) {
            try {
                std::vector<UiInputTarget> targets;UiInputTargetsRequest request{&targets};
                Call(&UiInputDispatch::CollectTargets,&request);
                std::vector<std::uint64_t> keys;
                for(const auto& target:targets)keys.push_back(target.key);
                UiWindowPresentation::Serve(sequence_,game_->GetGameTurn(),directory_,shownSnapshot_,keys,
                    [this](){return SnapshotText();},[this](){return active_;},
                    [this](const ZeroSisPresentation::BitmapInputEvent& event){return DispatchWindowInput(event);},displayResize_,refreshClosed_,
                    [this](){
                        std::vector<UiInputTarget> targets;UiInputTargetsRequest request{&targets};
                        Call(&UiInputDispatch::CollectTargets,&request);
                        std::vector<std::uint64_t> keys;
                        for(const auto& target:targets)keys.push_back(target.key);
                        return keys;
                    });
                return;
            }catch(...){presentationFailed_=true;throw;}
        }
#endif
        Call(kind_==UiPopupKind::GameMenu?&CloseGameMenuLua:&Close,nullptr);
        if(timerState_!=TimerState::Released)throw std::runtime_error("Official popup did not release the native timer semaphore");
        active_=false;if(!economicOwner_)host_.popupVisible=false;
        if(kind_==UiPopupKind::EconomicOverview)ApplyEconomicVisibility(false);
        WriteSnapshot("closed");
        host_.Record("ui-popup-closed:"+std::to_string(sequence_)+":"+std::to_string(game_->GetGameTurn()));
    }
void Call(lua_CFunction function,void* argument){
        if(dispatching_)throw std::logic_error("UI dispatch reentered");
        dispatching_=true;instructions_=0;callInstructionLimit_=InstructionLimit(function);lua_sethook(vm_,&Budget,LUA_MASKCOUNT,1000);
        try{
            const bool success=scripts_.CallCFunction(vm_,function,argument);
            lua_sethook(vm_,nullptr,0,0);dispatching_=false;
            if(kind_==UiPopupKind::ResearchTree || kind_==UiPopupKind::Research || kind_==UiPopupKind::SocialPolicy){
                const char* phase=function==&Dispatch?"popup":function==&Snapshot?"snapshot":
                    function==&UiInputDispatch::Dispatch?"input":function==&ResearchDirty?"research-dirty":
                    function==&PolicyDirty?"policy-dirty":function==&ValidatePolicyCommand?"policy-validation":
                    function==&UiInputDispatch::CollectTargets?"targets":"observation";
                std::printf("%s=%s|%u|%u|%u\n",kind_==UiPopupKind::SocialPolicy?"SOCIAL_POLICY_UI_INSTRUCTION_COST":kind_==UiPopupKind::ResearchTree?
                    "RESEARCH_TREE_UI_INSTRUCTION_COST":"RESEARCH_UI_INSTRUCTION_COST",phase,instructions_,
                    callInstructionLimit_,success?1u:0u);
            }
            if(kind_==UiPopupKind::NotificationPanel){
                const char* phase=function==&RefreshNotificationPanelLua?"refresh":
                    function==&StopNotificationPanelLua?"stop":function==&Snapshot?"snapshot":
                    function==&UiInputDispatch::Dispatch?"input":
                    function==&UiInputDispatch::CollectTargets?"targets":"observation";
                std::printf("NOTIFICATION_PANEL_UI_INSTRUCTION_COST=%s|%u|%u|%u\n",
                    phase,instructions_,callInstructionLimit_,success?1u:0u);
            }
            if(!success){
                std::array<char,2048> originalError{};
                const char* detail=scripts_.LastError();
                std::snprintf(originalError.data(),originalError.size(),"%s",detail&&*detail?detail:"Lua UI callback failed");
                Fault();
                if(timerRecoveryFailed_)
                    std::fprintf(stderr,"UI_POPUP_TIMER_RECOVERY_FAILED original=%s\n",originalError.data());
                throw std::runtime_error(originalError.data());
            }
        }catch(...){
            if(dispatching_){lua_sethook(vm_,nullptr,0,0);dispatching_=false;}
            if(!faulted_)Fault();
            throw;
        }
    }
void Fault() noexcept {
        if(faulted_)return;
        faulted_=true;active_=false;
        gameMenuRequests_.clear();gameMenuReady_=false;RestoreGameMenuCursor();
        saveMenuRequests_.clear();saveMenuReady_=false;saveMenuInput_=false;
        if(!economicOwner_ && kind_!=UiPopupKind::UnitPanel && kind_!=UiPopupKind::TopPanel)host_.popupVisible=false;
        if(timerState_==TimerState::Held){
            // Mark uncertain before the SDK call. If it throws after changing
            // the counter, later Close/Stop must never issue a second decrement.
            timerState_=TimerState::TransitionUnknown;
            try{
                game_->EndTurnTimerSemaphoreDecrement();
                timerState_=TimerState::Released;
                std::fprintf(stderr,"UI_POPUP_TIMER_RECOVERED_AFTER_LUA_FAILURE\n");
            }catch(const std::exception& error){
                timerRecoveryFailed_=true;
                std::fprintf(stderr,"UI_POPUP_TIMER_RECOVERY_EXCEPTION=%s\n",error.what());
            }catch(...){
                timerRecoveryFailed_=true;
                std::fprintf(stderr,"UI_POPUP_TIMER_RECOVERY_EXCEPTION=unknown\n");
            }
        }else if(timerState_==TimerState::TransitionUnknown){
            timerRecoveryFailed_=true;
            std::fprintf(stderr,"UI_POPUP_TIMER_RECOVERY_UNCERTAIN_NO_RETRY\n");
        }
    }
void RestoreGameMenuCursor() noexcept {
        if(!gameMenuCursorToken_)return;
        if(const auto arrow=LoadCursorW(nullptr,MAKEINTRESOURCEW(32512)))SetCursor(arrow);
        gameMenuCursorToken_=0;
    }
void ReleaseWarResources(){
        if(warCommandsVm_){scripts_.FreeLuaThread(warCommandsVm_);warCommandsVm_=nullptr;}
        scratchDeal_.reset();
        if(ownsScratchDeal_){deals_->DestroyDeal(scratchDealId_);ownsScratchDeal_=false;}
        deals_.reset();scriptUtility_.reset();warCommands_.clear();warInput_=false;
    }
bool IsNotificationInputPanel() const {
        return kind_==UiPopupKind::ActionInfoPanel || kind_==UiPopupKind::NotificationPanel;
    }
void ApplyEconomicVisibility(bool initialize){
        if(kind_!=UiPopupKind::EconomicOverview)return;
        for(unsigned slot=1;slot<=2;++slot){
            auto& child=economicChildren_[slot-1];if(!child || !child->vm_)continue;
            if(child->faulted_){child->active_=false;continue;}
            const bool visible=active_ && economicChildVisible_[slot-1];
            const bool first=initialize || !child->economicVisibilityInitialized_;
            if(!first && !economicChildVisibilityDirty_[slot-1] && child->active_==visible)continue;
            EconomicVisibilityRequest request{visible,first};
            child->Call(&SetEconomicVisibilityLua,&request);
            child->active_=visible;child->economicVisibilityInitialized_=true;economicChildVisibilityDirty_[slot-1]=false;
        }
    }
std::string EmbeddedEconomicSnapshots(){
        if(kind_!=UiPopupKind::EconomicOverview)return {};
        if(!economicChildren_[0] || !economicChildren_[1])throw std::logic_error("EconomicOverview lost one of its retained child VMs");
        auto general=economicChildren_[0]->SnapshotText();
        auto happiness=economicChildren_[1]->SnapshotText();
        return "\"embeddedContexts\":[{\"controlId\":\"EconomicGeneralInfo\",\"keyBase\":"+
            std::to_string(EconomicGeneralKeyBase)+",\"snapshot\":"+general+"},{\"controlId\":\"HappinessInfo\",\"keyBase\":"+
            std::to_string(EconomicHappinessKeyBase)+",\"snapshot\":"+happiness+"}]";
    }
unsigned long SynchronousRandomSeed(){
        Require();std::unique_ptr<ICvRandom1> random(game_->GetRandomNumberGenerator());
        if(!random)throw std::runtime_error("UI synchronous RNG interface is missing");
        return random->GetSeed();
    }
static std::size_t Utf8Next(const char* text,std::size_t bytes,std::size_t offset){
        if(offset>=bytes)throw std::invalid_argument("UTF-8 offset exceeds text");
        const auto first=static_cast<unsigned char>(text[offset]);
        unsigned count=0,code=0,minimum=0;
        if(first<0x80){count=1;code=first;}
        else if(first>=0xc2 && first<=0xdf){count=2;code=first&0x1f;minimum=0x80;}
        else if(first>=0xe0 && first<=0xef){count=3;code=first&0x0f;minimum=0x800;}
        else if(first>=0xf0 && first<=0xf4){count=4;code=first&7;minimum=0x10000;}
        else throw std::invalid_argument("Invalid UTF-8 leading byte");
        if(bytes-offset<count)throw std::invalid_argument("Truncated UTF-8 text");
        for(unsigned i=1;i<count;++i){const auto next=static_cast<unsigned char>(text[offset+i]);
            if((next&0xc0)!=0x80)throw std::invalid_argument("Invalid UTF-8 continuation");code=(code<<6)|(next&0x3f);}
        if(code<minimum || code>0x10ffff || (code>=0xd800 && code<=0xdfff))
            throw std::invalid_argument("Invalid UTF-8 code point");
        return offset+count;
    }
static std::size_t Utf8Length(const char* text){
        const auto bytes=std::strlen(text);std::size_t length=0;
        for(std::size_t offset=0;offset<bytes;++length)offset=Utf8Next(text,bytes,offset);
        return length;
    }
std::string SnapshotText(){
        std::string output;Call(&Snapshot,&output);
        if(kind_==UiPopupKind::EconomicOverview){
            if(output.empty() || output.back()!='}' || output.find("\"embeddedContexts\"")!=std::string::npos)
                throw std::runtime_error("EconomicOverview parent snapshot cannot be safely extended");
            const auto embedded=EmbeddedEconomicSnapshots();
            output.insert(output.size()-1,","+embedded);
        }
        return output;
    }
std::string WriteSnapshot(const char* phase){
        auto output=SnapshotText();
        const auto name=L"ui-popup-"+std::to_wstring(sequence_)+L"-"+std::wstring(phase,phase+std::strlen(phase))+L".json";
        SdkStateSnapshot::Write(directory_+L"\\"+name,output);
        std::printf("UI_POPUP_%s=%u,%d,%zu\n",phase,sequence_,game_->GetGameTurn(),output.size());
        return output;
    }
void RequireOwnedMenuPlayer(){
        Require();
        try{RequireLocalMenuPlayer(gameMenuOwner_,gameMenuTurn_);}
        catch(const std::exception& error){
            Require();
            std::fprintf(stderr,"UI_POPUP_MENU_SCOPE_FAILURE=%s\n",error.what());
            if(!dispatching_ && scripts_.IsQuiescent())Fault();
            throw;
        }catch(...){
            Require();
            std::fprintf(stderr,"UI_POPUP_MENU_SCOPE_FAILURE=unknown\n");
            if(!dispatching_ && scripts_.IsQuiescent())Fault();
            throw;
        }
    }
    bool DispatchInput(UiInputKind kind,std::uint64_t key,double delta=0.0){
        Require();
        if(kind==UiInputKind::TextInput && kind_!=UiPopupKind::SaveMenu)return false;
        if(!active_ || faulted_){
            if(kind_==UiPopupKind::ResearchTree)
                std::printf("RESEARCH_TREE_UI_INPUT=%u|%llu|%.17g|0|0|%u\n",static_cast<unsigned>(kind),
                    static_cast<unsigned long long>(key),delta,timerState_==TimerState::Held?1u:0u);
            return false;
        }

        UiInputRequest request;request.kind=kind;request.key=key;request.delta=delta;
        if(kind_==UiPopupKind::SaveMenu){
            RequireSaveMenuOwner();
            if(saveMenuInput_ || saveMenuReady_ || !saveMenuRequests_.empty() || timerState_!=TimerState::Released)
                throw std::logic_error("SaveMenu input requires its refreshed timer-free child scope");
            const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
            saveMenuInput_=true;saveMenuInputKind_=kind;
            try{Call(&UiInputDispatch::Dispatch,&request);}
            catch(...){saveMenuInput_=false;saveMenuRequests_.clear();saveMenuReady_=false;throw;}
            saveMenuInput_=false;
            bool stillActive=false;Call(&ObserveActive,&stillActive);
            if(!scripts_.IsQuiescent() || timerState_!=TimerState::Released ||
               before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
                throw std::runtime_error("Original SaveMenu input changed gameplay or its parent-owned timer");
            if(!saveMenuRequests_.empty()){
                if(!request.consumed || stillActive ||
                   (kind!=UiInputKind::LeftClick && kind!=UiInputKind::KeyDown))
                    throw std::logic_error("SaveMenu request escaped its completed original callback");
                saveMenuReady_=true;
            }
            active_=stillActive;
            // The retained parent remains modal even after the child closes.
            host_.popupVisible=true;
            if(request.consumed){
                if(active_){++revision_;const auto phase="updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());}
                else WriteSnapshot("closed");
            }
            std::printf("INTERACTIVE_SAVE_MENU_INPUT=%u|%llu|%u|%d|%d|%u|0|%zu|STATE_UNCHANGED\n",
                static_cast<unsigned>(kind),static_cast<unsigned long long>(key),request.consumed?1u:0u,
                gameMenuOwner_,gameMenuTurn_,active_?1u:0u,saveMenuRequests_.size());
            return request.consumed;
        }
        if(kind_==UiPopupKind::GameMenu){
            RequireGameMenuOwner();
            if(gameMenuInput_ || gameMenuReady_ || !gameMenuRequests_.empty() || timerState_!=TimerState::Held)
                throw std::logic_error("GameMenu input requires its refreshed modal owner scope");
            const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
            gameMenuInput_=true;gameMenuInputKind_=kind;
            try{Call(&UiInputDispatch::Dispatch,&request);}
            catch(...){gameMenuInput_=false;gameMenuRequests_.clear();gameMenuReady_=false;RestoreGameMenuCursor();throw;}
            gameMenuInput_=false;
            bool stillActive=false;Call(&ObserveActive,&stillActive);
            if(!scripts_.IsQuiescent() || gameMenuCursorToken_!=0 ||
               timerState_!=(stillActive?TimerState::Held:TimerState::Released) ||
               before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
                throw std::runtime_error("Original GameMenu input changed gameplay, cursor, or its modal timer contract");
            if(!gameMenuRequests_.empty()){
                if(!request.consumed || kind!=UiInputKind::LeftClick ||
                   gameMenuRequests_.front().owner!=game_->GetActivePlayer() ||
                   gameMenuRequests_.front().turn!=game_->GetGameTurn() ||
                   (gameMenuRequests_.front().kind==GameMenuRequest::Kind::QuickSave && stillActive))
                    throw std::logic_error("GameMenu request escaped its completed original click callback");
                gameMenuReady_=true;
            }
            active_=stillActive;host_.popupVisible=active_;
            if(request.consumed){
                if(active_){++revision_;const auto phase="updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());}
                else WriteSnapshot("closed");
            }
            std::printf("INTERACTIVE_GAME_MENU_INPUT=%u|%llu|%u|%d|%d|%u|%u|%zu|STATE_UNCHANGED\n",
                static_cast<unsigned>(kind),static_cast<unsigned long long>(key),request.consumed?1u:0u,
                gameMenuOwner_,gameMenuTurn_,active_?1u:0u,timerState_==TimerState::Held?1u:0u,gameMenuRequests_.size());
            return request.consumed;
        }
        throw std::logic_error("The fixture excludes unrelated input contexts");
    }
};
bool ScriptSystem::CallCFunction(lua_State* state,lua_CFunction token,void* argument){
    auto& c=*state->context;++depth;++w.luaCalls;
    try{
        if(token==&UiInputDispatch::Dispatch || token==&UiPopupContext::CloseGameMenuLua || token==&UiPopupContext::Close){
            w.trace.push_back(c.kind_==UiPopupKind::SaveMenu?"lua-child-close":"lua-parent-close");
            if(w.changeTurnInsideLua){++w.turn;w.changeTurnInsideLua=false;}
            if(c.kind_==UiPopupKind::SaveMenu)c.RequireSaveMenuOwner();else if(c.kind_==UiPopupKind::GameMenu)c.RequireGameMenuOwner();
            if(w.closeLuaFailure)throw std::runtime_error("mock Lua close failure");
            if(w.unknownCloseFailure)throw 17;
            if(c.kind_==UiPopupKind::SaveMenu){
                auto& request=*static_cast<UiInputRequest*>(argument);
                if(request.key==101)c.QueueSaveMenuRequest(SaveMenuRequest::Kind::Save,"nonwindow");
                c.QueueSaveMenuRequest(SaveMenuRequest::Kind::Close,nullptr);request.consumed=true;
            }else if(c.timerState_==UiPopupContext::TimerState::Held){
                c.timerState_=UiPopupContext::TimerState::TransitionUnknown;
                c.game_->EndTurnTimerSemaphoreDecrement();c.timerState_=UiPopupContext::TimerState::Released;
            }
            c.active_=false;
        }else if(token==&UiPopupContext::ObserveActive)*static_cast<bool*>(argument)=c.active_;
        else if(token==&UiPopupContext::Snapshot)*static_cast<std::string*>(argument)="{}";
        else throw std::logic_error("Unexpected script API token in menu fixture");
        --depth;return true;
    }catch(const std::exception& e){w.faultObservedInsideScript=c.faulted_;lastError=e.what();--depth;return false;}
    catch(...){w.faultObservedInsideScript=c.faulted_;lastError="mock unknown Lua close failure";--depth;return false;}
}
class InteractiveUiSession {
public:
    std::shared_ptr<HostState> owner_;HostState& host_;int* core_;
    std::unique_ptr<UiPopupContext> popup_,idleProduction_,suspendedGameMenu_,suspendedCity_,suspendedCapture_,suspendedEconomic_,
        unitPanel_,topPanel_,notificationPanel_,actionInfoPanel_;
    std::deque<int> pending_,leaderWarStates_;bool stopping_=false,closePending_=false;
    std::uint64_t textInputOwner_=9;int economicOwner_=NO_PLAYER,economicTurn_=-1;
    UiPopupKind kind_=UiPopupKind::SaveMenu;
    explicit InteractiveUiSession(std::shared_ptr<HostState> h):owner_(std::move(h)),host_(*owner_),core_(&host_.w.turn){}
void Require() const {
        if(host_.gameThread!=GetCurrentThreadId() || !host_.gameLock.HeldByCurrentThread())
            throw std::logic_error("Interactive UI router requires the GameCore owner lock");
    }
void Stop(){
        Require();stopping_=true;pending_.clear();leaderWarStates_.clear();closePending_=false;
        textInputOwner_=0;
        DiscardIdleProduction();
        if(HasEconomicContext())StopEconomicContexts();
        if(popup_){popup_->Stop();popup_.reset();}
        if(suspendedGameMenu_){suspendedGameMenu_->Stop();suspendedGameMenu_.reset();}
        if(suspendedCity_){suspendedCity_->Stop();suspendedCity_.reset();}
        if(suspendedCapture_){suspendedCapture_->Stop();suspendedCapture_.reset();}
        if(unitPanel_){unitPanel_->Stop();unitPanel_.reset();}
        if(topPanel_){topPanel_->Stop();topPanel_.reset();}
        if(notificationPanel_){notificationPanel_->Stop();notificationPanel_.reset();}
        if(actionInfoPanel_){actionInfoPanel_->Stop();actionInfoPanel_.reset();}
        host_.actionInfoActivationInProgress=false;host_.actionInfoOwner=NO_PLAYER;host_.actionInfoTurn=-1;
        host_.actionInfoAdapterRequests.clear();
        UserInterface frontend(owner_);frontend.clearSelectedCities();frontend.SetCityScreenViewingMode(false);host_.resolveCity={};
        host_.pendingLeaderMessages=0;host_.leaderRootUp=false;
        host_.addPopup={};host_.addArrayPopup={};host_.addLeaderMessage={};host_.routeWarStateChanged={};host_.closeInformationalPopup={};core_=nullptr;
        std::puts("INTERACTIVE_UI_ROUTER_STOPPED=true");
    }
bool HasEconomicContext() const {
        return suspendedEconomic_ || (popup_ && kind_==UiPopupKind::EconomicOverview);
    }
void DiscardIdleProduction(){
        if(idleProduction_){idleProduction_->Stop();idleProduction_.reset();}
    }
void StopEconomicContexts(){
        if(suspendedEconomic_ && popup_ && kind_!=UiPopupKind::Production)
            throw std::logic_error("Retained economic overview is covered by an unrelated popup");
        std::exception_ptr failure;
        const auto stop=[&failure](std::unique_ptr<UiPopupContext>& context){
            if(!context)return;
            try{context->Stop();context.reset();}
            catch(...){if(!failure)failure=std::current_exception();}
        };
        if(suspendedEconomic_ || (popup_ && kind_==UiPopupKind::EconomicOverview))stop(popup_);
        stop(suspendedEconomic_);
        if(!HasEconomicContext()){economicOwner_=NO_PLAYER;economicTurn_=-1;}
        if(failure)std::rethrow_exception(failure);
    }
};
struct Pair {
    World w;ScriptSystem scripts{w};std::shared_ptr<HostState> host=std::make_shared<HostState>(w);
    InteractiveUiSession ui{host};
    Pair(){ui.popup_.reset(new UiPopupContext(*host,scripts,w,UiPopupKind::SaveMenu,2));
           ui.suspendedGameMenu_.reset(new UiPopupContext(*host,scripts,w,UiPopupKind::GameMenu,1));}
};
static unsigned checks=0,cases=0;
void check(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
std::string rejected(const std::function<void()>& callback){
    try{callback();}catch(const std::exception& e){return e.what();}throw std::runtime_error("Expected rejection");
}
void stopped(Pair& p,bool expectLua){
    p.ui.Stop();check(!p.ui.popup_ && !p.ui.suspendedGameMenu_,"Both menu VMs must be released");
    check(p.w.timer==0 && p.w.decrements==1,"Parent timer must be decremented exactly once");
    check(p.w.frees==2 && !p.ui.core_,"Router and both VMs must be stopped");
    check(!p.host->popupVisible && p.ui.textInputOwner_==0,"Stopped UI and editor ownership must be cleared");
    check((p.w.luaCalls>0)==expectLua,"Stale/faulted scopes must not reenter Lua");
    const auto attempts=p.w.decrements,calls=p.w.luaCalls,frees=p.w.frees;p.ui.Stop();
    check(p.w.decrements==attempts && p.w.luaCalls==calls && p.w.frees==frees,"Repeated Stop must be idempotent");
}
int main(){
 try{
    {Pair p;++cases;stopped(p,true);}
    {Pair p;++cases;check(p.ui.popup_->DispatchInput(UiInputKind::LeftClick,101),"Stock Save/Close callback must complete");
     auto requests=p.ui.popup_->TakeSaveMenuRequests();check(requests.size()==2 && requests[0].kind==SaveMenuRequest::Kind::Save &&
        requests[1].kind==SaveMenuRequest::Kind::Close,"Original Save then OnBack order must remain unchanged");
     check(p.w.timer==1 && p.w.decrements==0,"Child callback must keep parent timer held");
     stopped(p,true);}
    const std::vector<std::function<void(Pair&)>> loss={
      [](Pair& p){p.w.player=1;},[](Pair& p){++p.w.turn;},[](Pair& p){p.w.alive=false;},
      [](Pair& p){p.w.human=false;},[](Pair& p){p.w.turnActive=false;},[](Pair& p){p.w.playerMissing=true;},
      [](Pair& p){p.w.initialized=false;},[](Pair& p){p.w.multiplayer=true;},[](Pair& p){p.w.network=true;},
      [](Pair& p){p.host->localSdkSessionBound=false;}
    };
    for(const auto& mutate:loss){Pair p;++cases;mutate(p);
      const auto error=rejected([&](){p.ui.popup_->DispatchInput(UiInputKind::KeyDown,VK_ESCAPE);});
      check(error.find("GameMenu requires")!=std::string::npos,"Original owner rejection must remain observable");
      check(p.ui.popup_->faulted_ && !p.ui.popup_->active_,"Rejected stale child must become faulted");
      check(p.w.decrements==0 && p.w.luaCalls==0,"Released child must not decrement or call Lua");stopped(p,false);}
    {Pair p;++cases;++p.w.turn;stopped(p,false);}
    {Pair p;++cases;++p.w.turn;const auto error=rejected([&](){p.ui.suspendedGameMenu_->RequireGameMenuOwner();});
     check(!error.empty() && p.w.decrements==1,"Direct stale parent guard must release its known held timer");stopped(p,false);}
    {Pair p;++cases;p.ui.popup_->Fault();p.ui.popup_->Fault();p.ui.suspendedGameMenu_->Fault();p.ui.suspendedGameMenu_->Fault();stopped(p,false);}
    {Pair p;++cases;p.w.closeLuaFailure=true;stopped(p,true);check(p.scripts.lastError=="mock Lua close failure","Close failure must retain original script diagnostic");}
    {Pair p;++cases;p.w.unknownCloseFailure=true;stopped(p,true);check(p.scripts.lastError=="mock unknown Lua close failure","Unknown callback failure must remain recorded");}
    {Pair p;++cases;p.w.snapshotIoFailure=true;stopped(p,true);}
    {Pair p;++cases;p.w.unknownSnapshotFailure=true;stopped(p,true);}
    {Pair p;++cases;p.w.changeTurnInsideLua=true;
     check(rejected([&](){p.ui.popup_->DispatchInput(UiInputKind::KeyDown,VK_ESCAPE);}).find("GameMenu requires")!=std::string::npos,
       "Protected script failure must retain actual scope diagnostic");
     check(p.scripts.depth==0 && p.ui.popup_->faulted_ && p.w.decrements==0 && !p.w.faultObservedInsideScript,
       "Protected child fault must wait until script unwinds");
     const auto calls=p.w.luaCalls;p.ui.Stop();check(p.w.luaCalls==calls && p.w.decrements==1 && p.w.frees==2,"Stale parent must stop without Lua reentry after child failure");}
    for(const bool wrongThread:{false,true}){Pair p;++cases;if(wrongThread)currentThread=8;else p.w.lockHeld=false;
     check(!rejected([&](){p.ui.Stop();}).empty(),"Wrong thread/lock Stop must reject");
     check(!p.ui.popup_->faulted_ && !p.ui.suspendedGameMenu_->faulted_ && p.w.decrements==0 && p.w.frees==0 && p.w.luaCalls==0,
       "Missing lock/thread must not fault, decrement or reenter Lua");currentThread=7;p.w.lockHeld=true;stopped(p,true);}
    {Pair p;++cases;p.w.loseLockOnPlayerQuery=true;
     check(rejected([&](){p.ui.popup_->RequireSaveMenuOwner();}).find("owner lock")!=std::string::npos,"Scope catch must recheck owner lock");
     check(!p.ui.popup_->faulted_ && p.w.decrements==0,"Lock lost during guard must prevent recovery");p.w.loseLockOnPlayerQuery=false;p.w.lockHeld=true;stopped(p,true);}
    for(const bool mutateBeforeThrow:{false,true}){Pair p;++cases;++p.w.turn;
     p.w.throwDecrement=!mutateBeforeThrow;p.w.throwAfterDecrement=mutateBeforeThrow;
     check(!rejected([&](){p.ui.Stop();}).empty(),"Uncertain SDK decrement must stop teardown");
     check(p.w.decrements==1 && p.w.frees==1 && p.ui.suspendedGameMenu_->timerRecoveryFailed_,"Known-held parent transition may be attempted only once");
     check(!rejected([&](){p.ui.Stop();}).empty() && p.w.decrements==1,"Repeated uncertain Stop must never retry decrement");}
    {Pair p;++cases;p.ui.popup_->timerState_=UiPopupContext::TimerState::TransitionUnknown;p.ui.popup_->Fault();
     check(!rejected([&](){p.ui.Stop();}).empty() && p.w.decrements==0 && p.w.frees==0,"Unknown child timer must fail closed");
     check(!rejected([&](){p.ui.Stop();}).empty() && p.w.decrements==0,"Unknown child timer must remain unretried");}
    {Pair p;++cases;p.ui.popup_->timerRecoveryFailed_=true;p.ui.popup_->faulted_=true;
     check(!rejected([&](){p.ui.Stop();}).empty() && p.w.decrements==0 && p.w.frees==0,"Recovery-failed flag must prevent cleanup success");}
    {Pair p;++cases;++p.w.turn;p.w.busy=true;
     check(!rejected([&](){p.ui.Stop();}).empty() && !p.ui.popup_->faulted_ && p.w.decrements==0 && p.w.frees==0,
       "Nonquiescent script must not be recovered by scope guard");p.w.busy=false;stopped(p,false);}
    {Pair p;++cases;p.ui.popup_->kind_=UiPopupKind::Ranking;p.w.snapshotIoFailure=true;
     check(!rejected([&](){p.ui.Stop();}).empty() && p.w.frees==0 && p.w.decrements==0,
       "Nonmenu close failure must preserve existing teardown behavior");}
    std::printf("SAVE_MENU_SCOPE_COMPONENT_PASS=%u|%u\n",cases,checks);return 0;
 }catch(const std::exception& e){std::fprintf(stderr,"COMPONENT_ASSERTION_FAILED=%s\n",e.what());return 1;}
}
