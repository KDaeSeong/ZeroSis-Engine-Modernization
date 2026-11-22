#pragma once
#include "GeneratedHostInterfaces.h"
#include "MapSurface.h"
#include "AudioCatalog.h"
#include "ScriptSystem.h"
#include "LocalGameCommands.h"
#include "LocalTurnSignals.h"
#include "CombatPresentation.h"
#include "ActiveModCatalog.h"
#include "LocalUnitSelection.h"
#include "TradeRoutePresentation.h"
#include "MenuOptionsContract.h"
#include <set>
#if defined(ZEROSIS_WORLD_TERRAIN)
#include "../Presentation/WorldViewRenderer.h"
#endif

namespace ZeroSisHost {
class UiAudioPlayback;
class MenuOptionsStore;
class CoreLock {
public:
    void Enter() {
        mutex_.lock();
        if(depth_==UINT_MAX){mutex_.unlock();throw std::overflow_error("GameCore lock recursion overflow");}
        if(depth_==0) owner_.store(GetCurrentThreadId(),std::memory_order_release);
        ++depth_;
    }
    bool TryEnter() {
        if(!mutex_.try_lock()) return false;
        if(depth_==UINT_MAX){mutex_.unlock();throw std::overflow_error("GameCore lock recursion overflow");}
        if(depth_==0) owner_.store(GetCurrentThreadId(),std::memory_order_release);
        ++depth_;return true;
    }
    void Leave() {
        if(!HeldByCurrentThread()) throw std::logic_error("GameCore lock release from a non-owner thread");
        if(--depth_==0) owner_.store(0,std::memory_order_release);
        mutex_.unlock();
    }
    bool HeldByCurrentThread() const noexcept { return owner_.load(std::memory_order_acquire)==GetCurrentThreadId(); }
private:
    std::recursive_mutex mutex_;
    std::atomic<DWORD> owner_{0};
    unsigned depth_=0;
};

struct PresentationMessage {
    unsigned parentEvent=0;
    bool cityMessage=false;
    PlayerTypes cityOwner=NO_PLAYER;
    int cityId=-1;
    PlayerTypes player=NO_PLAYER;
    bool force=false;
    int length=0;
    std::string text,icon;
    std::basic_string<TCHAR> sound;
    InterfaceMessageTypes type=MESSAGE_TYPE_INFO;
    ColorTypes flashColor=NO_COLOR;
    int flashX=-1,flashY=-1;
    bool offScreenArrows=false,onScreenArrows=false;
};
struct NotificationPresentation {
    int id=-1;
    NotificationTypes type=static_cast<NotificationTypes>(-1);
    std::string tooltip,summary;
    int gameData=-1,extraGameData=-1;
    PlayerTypes player=NO_PLAYER;
    int x=-1,y=-1;
};
// Original ActionInfoPanel callbacks are copied while Lua is on the stack,
// then validated and routed only after the callback has returned.
struct ActionInfoRequest {
    enum class Kind { LookAt,SelectUnit,ActivateNotification,RemoveNotification,EndTurn } kind=Kind::SelectUnit;
    int id=-1,x=-1,y=-1,owner=-1,turn=-1;
};
inline bool IsSupportedActionInfoNotification(NotificationTypes type) noexcept {
    switch(type){
    case NOTIFICATION_TECH:case NOTIFICATION_FREE_TECH:case NOTIFICATION_TECH_AWARD:
    case NOTIFICATION_POLICY:case NOTIFICATION_FREE_POLICY:case NOTIFICATION_PRODUCTION:
    case NOTIFICATION_UNIT_PROMOTION:case NOTIFICATION_FOUND_PANTHEON:
    case NOTIFICATION_PANTHEON_FOUNDED_ACTIVE_PLAYER:return true;
    default:return false;
    }
}
struct CameraPresentation {
    int plotIndex=-1,x=-1,y=-1;
    CameraLookAtTypes type=CAMERALOOKAT_NORMAL;
};
struct PopupTextPresentation {
    int x=-1,y=-1;
    float delay=0;
    std::string text;
};
struct OwnedInputModifiers { bool alt=false,shift=false,control=false; };

// Own the ICvUserInterface2 stack-array payload before its SDK caller returns.
struct OwnedPopupInfo final {
    ButtonPopupTypes type;
    std::vector<int> data;
    std::vector<bool> options;
    int flags=0;
    std::string text;
    explicit OwnedPopupInfo(const CvPopupInfo& input):type(input.eButtonPopupType),
        data{input.iData1,input.iData2,input.iData3},options{input.bOption1,input.bOption2},flags(input.iFlags){
        const char* end=static_cast<const char*>(std::memchr(input.szText,0,sizeof(input.szText)));
        if(!end)throw std::invalid_argument("Unterminated popup text");
        text.assign(input.szText,end);
    }
    OwnedPopupInfo(int popupType,int intCount,const int* ints,int boolCount,const bool* bools)
        :type(static_cast<ButtonPopupTypes>(popupType)){
        if(intCount<0 || intCount>64 || boolCount<0 || boolCount>64 ||
           (intCount && !ints) || (boolCount && !bools))
            throw std::invalid_argument("Invalid array popup payload");
        if(intCount)data.assign(ints,ints+intCount);
        if(boolCount)options.assign(bools,bools+boolCount);
    }
    int Data(std::size_t index) const {return index<data.size()?data[index]:0;}
    bool Option(std::size_t index) const {return index<options.size()?options[index]:false;}
};

struct OwnedLeaderMessage final {
    static constexpr std::size_t MaxTextBytes=65536;
    PlayerTypes player=NO_PLAYER;
    DiploUIStateTypes state=NO_DIPLO_UI_STATE;
    std::string text;
    LeaderheadAnimationTypes animation=NO_LEADERHEAD_ANIM;
    int data1=-1;
    int receiver=-1;
    OwnedLeaderMessage(PlayerTypes messagePlayer,DiploUIStateTypes messageState,const char* message,
                       LeaderheadAnimationTypes messageAnimation,int messageData1=-1,int messageReceiver=-1)
        :player(messagePlayer),state(messageState),animation(messageAnimation),data1(messageData1),receiver(messageReceiver){
        if(player<0 || player>=MAX_PLAYERS || (state<NO_DIPLO_UI_STATE || state>=NUM_DIPLO_UI_STATES) ||
           (receiver!=-1 && (receiver<0 || receiver>=MAX_PLAYERS)) || !message)
            throw std::invalid_argument("Invalid diplomatic leader message identity or text");
        std::size_t bytes=0;
        while(bytes<=MaxTextBytes && message[bytes])++bytes;
        if(bytes>MaxTextBytes)throw std::length_error("Diplomatic leader message exceeds the owned text bound");
        const bool validAnimation=messageAnimation==NO_LEADERHEAD_ANIM ||
            (messageAnimation>=LEADERHEAD_ANIM_INTRO && messageAnimation<=LEADERHEAD_ANIM_HATE_IDLE) ||
            messageAnimation==LEADERHEAD_ANIM_LETS_HEAR_IT || messageAnimation==LEADERHEAD_ANIM_YES ||
            messageAnimation==LEADERHEAD_ANIM_NO || messageAnimation==LEADERHEAD_ANIM_POSITIVE ||
            messageAnimation==LEADERHEAD_ANIM_NEGATIVE || messageAnimation==LEADERHEAD_ANIM_HATE_POSITIVE ||
            messageAnimation==LEADERHEAD_ANIM_HATE_NEGATIVE;
        if(!validAnimation)throw std::invalid_argument("Invalid diplomatic leader animation");
        if(bytes && MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,message,static_cast<int>(bytes),nullptr,0)<=0)
            throw std::invalid_argument("Diplomatic leader message is not valid UTF-8");
        text.assign(message,bytes);
    }
};

struct OwnedWarStateChanged final {
    TeamTypes first,second;
    bool war;
    OwnedWarStateChanged(TeamTypes team1,TeamTypes team2,bool atWar):first(team1),second(team2),war(atWar){
        if(first<0 || first>=MAX_TEAMS || second<0 || second>=MAX_TEAMS)
            throw std::invalid_argument("Invalid owned team war notification");
    }
};

struct ConfirmedWarContinuation final {
    int owner=-1,unit=-1,turn=-1,x=-1,y=-1;
    bool ranged=false;
};

struct HostState {
    explicit HostState(std::string cache,Database::Connection* mods=nullptr,std::shared_ptr<const AudioCatalog> catalog=nullptr,
                       std::shared_ptr<ScriptSystem> script=nullptr,std::shared_ptr<const ActiveModCatalog> activation=nullptr)
        : cacheDirectory(std::move(cache)),modsDatabase(mods),gameThread(GetCurrentThreadId()),audio(std::move(catalog)),scripts(std::move(script)),activeMods(std::move(activation)) {
        if(cacheDirectory.empty() || (cacheDirectory.back()!='/' && cacheDirectory.back()!='\\'))
            throw std::invalid_argument("The isolated session cache directory requires a trailing separator");
        if(scripts && !scripts->IsOwner())throw std::invalid_argument("Script service belongs to a different thread");
        if(activeMods && activeMods->Size()!=0)
            throw std::invalid_argument("Active mods require a versioned activation/save manifest that this host does not yet implement");
        localSelection.SetOwnerCheck([this](){return gameThread==GetCurrentThreadId() && gameLock.HeldByCurrentThread();});
    }
    CoreLock gameLock;
    const std::string cacheDirectory;
    Database::Connection* const modsDatabase;
    const DWORD gameThread;
    const std::shared_ptr<const AudioCatalog> audio;
    const std::shared_ptr<ScriptSystem> scripts;
    const std::shared_ptr<const ActiveModCatalog> activeMods;
    MapSurface mapSurface;
    LocalGameCommands localCommands;
    LocalTurnSignals turnSignals;
    LocalUnitSelection localSelection;
    TradeRoutePresentation tradeRoutes;
    OwnedInputModifiers ownedInputModifiers{};
    std::function<void(int)> selectLocalUnit;
    std::function<void(bool,bool)> autoSave;
    std::function<bool()> saveReplay;
    std::function<bool(int)> recordVictoryInformation;
    std::function<bool(int)> recordLeaderboardScore;
    std::function<void()> restartGame;
    std::function<void()> openEndGameMenu;
    std::shared_ptr<MenuOptionsSession> menuOptions;
    std::shared_ptr<MenuOptionsStore> menuOptionsStore;
    std::function<MenuOptionsValues(const MenuOptionsValues&)> applyMenuOptions;
    std::function<bool()> canAdvanceTurn;
    std::function<void()> beginTurnBoundary;
    bool localSdkSessionBound=false;
    const ConfirmedWarContinuation* confirmedWarContinuation=nullptr;
    // Bound only while an original CityView input callback is on the Lua stack.
    // The receiver executes after that callback returns, on the owning thread.
    std::function<void(int,TaskTypes,int,int,bool,bool,bool,bool)> deferCityTask;
    std::function<void(int,int,bool)> deferCityOrder;
    std::function<void(int,UnitTypes,BuildingTypes,ProjectTypes,int)> deferCityPurchase;
    // UI sounds belong to the host session, including after their popup closes.
    std::shared_ptr<UiAudioPlayback> uiAudio;
    // Per-isolated-session display preferences, separate from SDK save data.
    std::wstring uiOptionsPath;
    bool policyInfoInitialized=false,policyInfo=false;
    // SDK readers share one stable committed snapshot. The session publishes
    // it only after persistence; applied staging belongs to the UI owner.
    const std::shared_ptr<std::atomic<bool>> noRewardPopupsCommitted=std::make_shared<std::atomic<bool>>(false);
    bool noRewardPopupsApplied=false;
    std::function<void(const CvPopupInfo&)> addPopup;
    std::function<void(const OwnedPopupInfo&)> addArrayPopup;
    std::function<void(const OwnedLeaderMessage&)> addLeaderMessage;
    std::function<void(const OwnedWarStateChanged&)> routeWarStateChanged;
    // City UI state is an owned identity only. The resolver creates a fresh
    // caller-owned SDK wrapper for each lookup; never retain an ICvCity1* here.
    PlayerTypes selectedCityOwner=NO_PLAYER;
    int selectedCityId=-1;
    IDInfo selectedCityNode;
    bool cityScreenUp=false;
    bool cityScreenViewingMode=false;
#if defined(ZEROSIS_WORLD_TERRAIN)
    ZeroSisPresentation::WorldViewProjection cityWorldProjection;
#endif
    std::function<ICvCity1*(PlayerTypes,int)> resolveCity;
    unsigned pendingLeaderMessages=0;
    bool leaderRootUp=false;
    std::function<void()> closeInformationalPopup;
    bool popupVisible=false,combatFocus=false;
    bool autoSaveRunning=false;
    std::atomic<bool> loadedGame{false};
    std::set<std::string> missingAudioTags;
    std::set<std::string> builtInCityNames;
    // Populated once from the SDK rules database on the owner thread before
    // city commands can target projects or processes. Treat as frozen at ready.
    std::set<int> validCityProjectTypes,validCityProcessTypes;
    bool cityItemRulesReady=false;
    std::atomic<unsigned> executing{0};
    std::atomic<bool> globalsStarted{false},done{false};
    std::atomic<unsigned> engineAdapters{0},userAdapters{0};
    std::mutex dataMutex;
    std::map<int,bool> dirty;
    std::array<bool,MAX_PLAYERS> openPlayerSlots{};
    std::array<int,MAX_PLAYERS> assignedNetworkIds{};
    bool networkAssignmentsReady=false;
    bool dontShowPopups=false;
    bool selectedUnitRevealingNewPlots=false;
    bool policyNotificationSeen=false;
    bool canEndTurn=false,hasMovedUnit=false,noSelectionCycle=false;
    bool advisorCityAttackInterrupt=false,advisorBadAttackInterrupt=false;
    int cycleSelection=0;
    InterfaceModeTypes interfaceMode=INTERFACEMODE_SELECTION;
    std::vector<std::string> events;
    std::vector<CombatPresentation> combatPresentations;
    std::vector<PresentationMessage> presentationMessages;
    std::vector<CameraPresentation> cameraPresentations;
    std::vector<PopupTextPresentation> popupTexts;
    std::map<std::pair<int,int>,NotificationPresentation> notifications;
    // Set only while the retained ActionInfoPanel route invokes the original
    // SDK notification callback. Adapter side effects are staged for the
    // caller to drain after CvNotifications::Activate has returned.
    PlayerTypes actionInfoOwner=NO_PLAYER;
    int actionInfoTurn=-1;
    bool actionInfoActivationInProgress=false;
    std::vector<ActionInfoRequest> actionInfoAdapterRequests;
    void Record(const std::string& message){std::lock_guard<std::mutex> guard(dataMutex);events.push_back(message);}
    std::vector<std::string> Events(){std::lock_guard<std::mutex> guard(dataMutex);return events;}
    void RecordCombat(CombatPresentation value){
        std::string message=std::string("gameplay-combat:")+(value.cityEvent?"city":"unit")+":"+
            std::to_string(value.plotIndex)+":"+(value.visualize?"1":"0")+":"+(value.ranged?"1":"0");
        for(const auto& participant:value.participants)
            message+="|"+std::to_string(participant.unitOwner)+","+std::to_string(participant.unitId)+","+
                std::to_string(participant.cityOwner)+","+std::to_string(participant.cityId)+","+
                std::to_string(participant.damageInflicted)+","+std::to_string(participant.finalDamage);
        std::lock_guard<std::mutex> guard(dataMutex);
        events.push_back(std::move(message));
        try{combatPresentations.push_back(std::move(value));}
        catch(...){events.pop_back();throw;}
    }
};

// Each QueryInterface result is an independently owned SDK adapter. Its shared
// state belongs to the host session and outlives GC's adapter/borrowed pointers.
class EngineServices final : public EngineServicesBase {
public:
    explicit EngineServices(std::shared_ptr<HostState> state):state_(std::move(state)){
        if(!state_)throw std::invalid_argument("Engine service state missing");++state_->engineAdapters;
    }
    ~EngineServices(){--state_->engineAdapters;}
    static void* operator new(std::size_t bytes){return ::operator new(bytes);}
    static void operator delete(void* p) noexcept {::operator delete(p);}
    void* DLLCALL QueryInterface(GUID id) override {
        if(id==guidICvUnknown || id==guidICvEngineUtility1 || id==guidICvEngineUtility2 || id==guidICvEngineUtility3 || id==guidICvEngineUtility4)
            return static_cast<ICvEngineUtility4*>(new EngineServices(state_));
        return nullptr;
    }
    void DLLCALL Destroy() override {delete this;}
    bool saveReplay() override {
        RequireCommandOwner();if(!state_->saveReplay)Unsupported("ICvEngineUtility1::saveReplay (unbound session provider)");
        return state_->saveReplay();
    }
    bool RecordVictoryInformation(int score) override {
        RequireCommandOwner();if(!state_->recordVictoryInformation)Unsupported("ICvEngineUtility1::RecordVictoryInformation (unbound session provider)");
        return state_->recordVictoryInformation(score);
    }
    bool RecordLeaderboardScore(int score) override {
        RequireCommandOwner();if(!state_->recordLeaderboardScore)Unsupported("ICvEngineUtility1::RecordLeaderboardScore (unbound session provider)");
        return state_->recordLeaderboardScore(score);
    }
    void RestartGame() override {
        RequireCommandOwner();if(!state_->restartGame)Unsupported("ICvEngineUtility1::RestartGame (unbound session provider)");
        state_->restartGame();
    }
    bool IsDLCValid(const GUID& id) const override {
        RequireCommandOwner();
        // This host has no platform entitlement/validation connection. The SDK
        // currently asks this only for the Ancient Wonders Steam achievement.
        // Rules/content presence is not evidence of a validated entitlement.
        char text[37];
        const int count=std::snprintf(text,sizeof(text),"%08lx-%04x-%04x-%02x%02x-%02x%02x%02x%02x%02x%02x",
            static_cast<unsigned long>(id.Data1),static_cast<unsigned>(id.Data2),static_cast<unsigned>(id.Data3),
            static_cast<unsigned>(id.Data4[0]),static_cast<unsigned>(id.Data4[1]),static_cast<unsigned>(id.Data4[2]),
            static_cast<unsigned>(id.Data4[3]),static_cast<unsigned>(id.Data4[4]),static_cast<unsigned>(id.Data4[5]),
            static_cast<unsigned>(id.Data4[6]),static_cast<unsigned>(id.Data4[7]));
        if(count!=36)throw std::runtime_error("DLC validation query identity could not be retained");
        state_->Record(std::string("platform-dlc-validation-unavailable:")+text);
        return false;
    }
    bool IsModActivated(const char* id) override {
        RequireCommandOwner();
        if(!state_->activeMods)throw std::logic_error("Session mod activation has not been configured");
        const bool active=state_->activeMods->Contains(id);
        state_->Record(std::string("mod-activation-query:")+id+":"+(active?"1":"0"));return active;
    }
    bool IsModActivated(const char* id,int version) override {
        RequireCommandOwner();
        if(!state_->activeMods)throw std::logic_error("Session mod activation has not been configured");
        // Only the explicit empty activation profile is currently loadable.
        // No version can be active there; do not infer the retail comparison
        // semantics for a nonempty profile from this query.
        const bool active=state_->activeMods->Contains(id);
        state_->Record(std::string("mod-activation-query:")+id+":"+std::to_string(version)+":"+(active?"1":"0"));return active;
    }
    void InitGlobals() override {
        if(!IsGameCoreThread())throw std::logic_error("Host globals initialization requires the owner thread");
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        if(state_->globalsStarted)throw std::logic_error("Host globals already initialized");
        state_->globalsStarted=true;
        state_->mapSurface.Clear();state_->dirty.clear();state_->cycleSelection=0;
        state_->done=false;state_->missingAudioTags.clear();state_->openPlayerSlots.fill(false);state_->dontShowPopups=false;
        state_->assignedNetworkIds.fill(-1);state_->networkAssignmentsReady=false;
        state_->combatPresentations.clear();state_->presentationMessages.clear();
        state_->cameraPresentations.clear();
        state_->popupTexts.clear();
        state_->notifications.clear();
        state_->tradeRoutes.Clear();
        state_->popupVisible=false;state_->combatFocus=false;state_->selectedUnitRevealingNewPlots=false;
        state_->policyNotificationSeen=false;
        state_->events.push_back("host-globals-started");
    }
    void UninitGlobals() override {
        // Idempotent after a partially completed InitGlobals or an earlier retry.
        if(!IsGameCoreThread())throw std::logic_error("Host globals shutdown requires the owner thread");
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->mapSurface.Clear();
        state_->tradeRoutes.Clear();
        if(state_->globalsStarted)state_->events.push_back("host-globals-stopped");
        state_->globalsStarted=false;
    }
    const char* GetCacheFolderPath() override {return state_->cacheDirectory.c_str();}
    ICvEngineScriptSystem1* GetScriptSystem() override {
        if(!state_->scripts)Unsupported("ICvEngineUtility1::GetScriptSystem (service not configured)");
        return state_->scripts.get();
    }
    void DoMapSetup(int count) override {
        if(!state_->globalsStarted || !IsGameCoreThread() || !HasGameCoreLock())
            throw std::logic_error("Map setup requires active host globals, owner thread and GameCore lock");
        state_->mapSurface.Setup(count);
    }
    int GetAudioTagIndex(const char* tag,int category=-1) override {
        if(category!=AUDIOTAG_SOUNDSCAPE)Unsupported("ICvEngineUtility1::GetAudioTagIndex (audio category not implemented)");
        if(!state_->audio)Unsupported("ICvEngineUtility1::GetAudioTagIndex (catalog not configured)");
        const int index=state_->audio->Find(tag);
        if(index<0 && tag && *tag){std::lock_guard<std::mutex> guard(state_->dataMutex);state_->missingAudioTags.insert(tag);}
        return index;
    }
    bool ShouldValidateGameDatabase() const override {return true;}
    void stripSpecialCharacters(CvString& name) override {
        RequireCommandOwner();
        // Built-in DB localization keys contain no special characters to
        // strip. Free-form renaming needs a separately verified text contract.
        if(state_->builtInCityNames.count(name.c_str())!=1)
            Unsupported("ICvEngineUtility1::stripSpecialCharacters (non-catalog name)");
        state_->Record(std::string("city-name-key-accepted:")+name.c_str());
    }
    Database::Connection* GetModsDatabase() override {
        if(!state_->modsDatabase)Unsupported("ICvEngineUtility1::GetModsDatabase (database not configured)");
        return state_->modsDatabase;
    }
    bool IsHost() const override {return true;} // This executable's initial mode is local single player.
    bool altKey() override {RequireCommandOwner();return state_->ownedInputModifiers.alt;}
    bool shiftKey() override {RequireCommandOwner();return state_->ownedInputModifiers.shift;}
    bool ctrlKey() override {RequireCommandOwner();return state_->ownedInputModifiers.control;}
    int getAssignedNetworkID(int player) override {
        RequireCommandOwner();
        if(player<0 || player>=MAX_PLAYERS)throw std::invalid_argument("Network identity player is outside the SDK slots");
        if(!state_->networkAssignmentsReady)throw std::logic_error("Local session network identities are not configured");
        return state_->assignedNetworkIds[static_cast<std::size_t>(player)];
    }
    bool IsPitbossHost() const override {return false;}
    // The native host exposes no FireTuner listener or attachment mechanism.
    // CvGame retains any historical flag read from its own saved state.
    bool TunerEverConnected() override {return false;}
    void SetAdvisorCityAttackInterrupt(bool value) override {RequireCommandOwner();state_->advisorCityAttackInterrupt=value;}
    bool GetAdvisorCityAttackInterrupt() override {RequireCommandOwner();return state_->advisorCityAttackInterrupt;}
    void SetAdvisorBadAttackInterrupt(bool value) override {RequireCommandOwner();state_->advisorBadAttackInterrupt=value;}
    bool GetAdvisorBadAttackInterrupt() override {RequireCommandOwner();return state_->advisorBadAttackInterrupt;}
    void SendAICivsProcessed() const override {
        RequireCommandOwner();state_->turnSignals.AcknowledgeCivs();state_->Record("local-ai-civs-processed");
    }
    bool allAICivsProcessedThisTurn() const override {RequireCommandOwner();return state_->turnSignals.CivsProcessed();}
    void sendPlayerInitialAIProcessed() const override {
        RequireCommandOwner();state_->turnSignals.AcknowledgeLocalPlayer();state_->Record("local-player-initial-ai-processed");
    }
    bool allAIProcessedThisTurn() const override {RequireCommandOwner();return state_->turnSignals.LocalPlayerProcessed();}
    void sendTurnComplete() override {
        RequireCommandOwner();state_->turnSignals.SendTurnComplete();state_->Record("local-turn-complete");
    }
    bool HasSentTurnComplete() override {RequireCommandOwner();return state_->turnSignals.HasSentTurnComplete();}
    bool HasReceivedTurnComplete(PlayerTypes player) override {
        RequireCommandOwner();
        if(player<0 || player>=MAX_PLAYERS)throw std::invalid_argument("Invalid turn-complete player");
        return state_->turnSignals.HasReceivedTurnComplete(player);
    }
    bool HasSentTurnAllComplete() override {RequireCommandOwner();return state_->turnSignals.HasSentTurnAllComplete();}
    bool HasReceivedTurnAllComplete(PlayerTypes player) override {
        RequireCommandOwner();
        if(player<0 || player>=MAX_PLAYERS)throw std::invalid_argument("Invalid turn-all-complete player");
        return state_->turnSignals.HasReceivedTurnAllComplete(player);
    }
    bool HasReceivedTurnAllCompleteFromAllPlayers() override {
        RequireCommandOwner();return state_->turnSignals.HasSentTurnAllComplete();
    }
    bool sendTurnUnready() override {
        RequireCommandOwner();
        const bool cancelled=state_->turnSignals.HasSentTurnComplete();
        state_->turnSignals.CancelTurnComplete();
        if(cancelled)state_->Record("local-turn-complete-cancelled");
        return cancelled;
    }
    bool CanAdvanceTurn() override {
        RequireCommandOwner();
        if(!state_->canAdvanceTurn)throw std::logic_error("Turn advancement requires a local session controller");
        return state_->canAdvanceTurn();
    }
    void DoTurn() override {
        RequireCommandOwner();
        if(!state_->beginTurnBoundary)throw std::logic_error("Turn boundary requires a local session controller");
        state_->beginTurnBoundary();
    }
    void GameplayTurnChanged(int turn) override {
        RequireCommandOwner();if(turn<0)throw std::invalid_argument("Invalid turn change notification");
        state_->Record("gameplay-turn-changed:"+std::to_string(turn));
    }
    void GameplayGoldenAgeStarted() override {
        RequireCommandOwner();
        // CvPlayer has already changed golden-age state, yields and replay
        // history. Retain its presentation notification for the host consumer.
        state_->Record("gameplay-golden-age-started");
    }
    void GameplayGoldenAgeEnded() override {
        RequireCommandOwner();
        state_->Record("gameplay-golden-age-ended");
    }
    void PublishNewGameTurn(int turn) override {
        RequireCommandOwner();if(turn<0)throw std::invalid_argument("Invalid new-turn notification");
        state_->Record("new-game-turn:"+std::to_string(turn));
    }
    void FlushTurnReminders() override {
        RequireCommandOwner();
        // Single local player sessions have no remote reminder queue. Enqueueing
        // remote reminders remains unsupported, so none can be silently lost.
        state_->Record("local-turn-reminders-flush:0");
    }
    void BeginSendBundle() override {RequireCommandOwner();state_->localCommands.Begin();}
    void EndSendBundle() override {RequireCommandOwner();state_->localCommands.End();}
    void sendPlayerOption(PlayerOptionTypes option,bool value) override {
        RequireCommandOwner();state_->localCommands.SendPlayerOption(option,value);
        state_->Record("local-player-option:"+std::to_string(static_cast<int>(option))+":"+(value?"1":"0"));
    }
    void sendDoTask(int cityID,TaskTypes task,int data1,int data2,bool option,bool alt,bool shift,bool control) override {
        RequireCommandOwner();
        if(state_->deferCityTask){state_->deferCityTask(cityID,task,data1,data2,option,alt,shift,control);return;}
        state_->localCommands.SendCityTask(cityID,task,data1,data2,option,alt,shift,control);
        state_->Record("local-city-task:"+std::to_string(cityID)+":"+std::to_string(static_cast<int>(task)));
    }
    void sendPopOrder(int cityID,int index) override {
        RequireCommandOwner();
        if(!state_->deferCityOrder)Unsupported("City order removal requires an active original CityView callback");
        state_->deferCityOrder(cityID,index,false);
    }
    void sendSwapOrder(int cityID,int index) override {
        RequireCommandOwner();
        if(!state_->deferCityOrder)Unsupported("City order swap requires an active original CityView callback");
        state_->deferCityOrder(cityID,index,true);
    }
    void SendLiberateMinor(PlayerTypes liberated,int cityID) override {
        RequireCommandOwner();state_->localCommands.SendLiberatePlayer(liberated,cityID);
        state_->Record("local-city-liberation:"+std::to_string(static_cast<int>(liberated))+":"+std::to_string(cityID));
    }
    void sendDoCommand(int unitID,CommandTypes command,int data1,int data2,bool alt) override {
        RequireCommandOwner();state_->localCommands.SendUnitCommand(unitID,command,data1,data2,alt);
        state_->Record("local-unit-command:"+std::to_string(unitID)+":"+std::to_string(static_cast<int>(command))+":"+
            std::to_string(data1)+":"+std::to_string(data2)+":"+(alt?"1":"0"));
    }
    void sendPushMission(int unitID,MissionTypes mission,int data1,int data2,int flags,bool shift) override {
        RequireCommandOwner();state_->localCommands.SendPushMission(unitID,mission,data1,data2,flags,shift);
        state_->Record("local-push-mission:"+std::to_string(unitID)+":"+std::to_string(static_cast<int>(mission))+":"+
            std::to_string(data1)+":"+std::to_string(data2)+":"+std::to_string(flags)+":"+(shift?"1":"0"));
    }
    void sendSwapUnits(int unitID,MissionTypes mission,int data1,int data2,int flags,bool shift) override {
        RequireCommandOwner();state_->localCommands.SendSwapUnits(unitID,mission,data1,data2,flags,shift);
        state_->Record("local-swap-units:"+std::to_string(unitID)+":"+std::to_string(static_cast<int>(mission))+":"+
            std::to_string(data1)+":"+std::to_string(data2)+":"+std::to_string(flags)+":"+(shift?"1":"0"));
    }
    void sendPushOrder(int cityID,OrderTypes order,int data,bool alt,bool shift,bool control) override {
        RequireCommandOwner();state_->localCommands.SendPushOrder(cityID,order,data,alt,shift,control);
        state_->Record("local-city-order:"+std::to_string(cityID)+":"+std::to_string(static_cast<int>(order))+":"+
            std::to_string(data)+":"+(alt?"1":"0")+":"+(shift?"1":"0")+":"+(control?"1":"0"));
    }
    void sendPurchase(int cityID,UnitTypes unit,BuildingTypes building,ProjectTypes project,int purchaseYield) override {
        RequireCommandOwner();
        if(state_->deferCityPurchase){state_->deferCityPurchase(cityID,unit,building,project,purchaseYield);return;}
        state_->localCommands.SendCityPurchase(cityID,unit,building,project,purchaseYield);
        state_->Record("local-city-purchase:"+std::to_string(cityID)+":"+std::to_string(static_cast<int>(unit))+":"+
            std::to_string(static_cast<int>(building))+":"+std::to_string(static_cast<int>(project))+":"+std::to_string(purchaseYield));
    }
    void sendResearch(TechTypes tech,int discover,PlayerTypes stealFrom,bool shift) override {
        RequireCommandOwner();state_->localCommands.SendResearch(tech,discover,stealFrom,shift);
        state_->Record("local-research:"+std::to_string(static_cast<int>(tech))+":"+std::to_string(discover)+":"+
            std::to_string(static_cast<int>(stealFrom))+":"+(shift?"1":"0"));
    }
    void SendFoundPantheon(PlayerTypes owner,BeliefTypes belief) override {
        RequireCommandOwner();state_->localCommands.SendFoundPantheon(owner,belief);
    }
    void sendChangeWar(TeamTypes team,bool war) override {
        RequireCommandOwner();state_->localCommands.SendChangeWar(team,war);
        state_->Record("local-change-war:"+std::to_string(static_cast<int>(team))+":"+(war?"1":"0"));
    }
    void sendFromUIDiploEvent(PlayerTypes other,FromUIDiploEventTypes event,int arg1,int arg2) override {
        RequireCommandOwner();state_->localCommands.SendFromUIDiploEvent(other,event,arg1,arg2);
        state_->Record("local-diplo-event:"+std::to_string(static_cast<int>(other))+":"+
            std::to_string(static_cast<int>(event))+":"+std::to_string(arg1)+":"+std::to_string(arg2));
    }
    bool getPlayerOption(PlayerOptionTypes option) override {
        RequireCommandOwner();return state_->localCommands.GetPlayerOption(option);
    }
    void AutoSave(bool initial=false,bool postTurn=false) override {
        RequireCommandOwner();
        if(state_->autoSaveRunning)throw std::logic_error("Reentrant SDK autosave is unsupported");
        if(!state_->autoSave)throw std::logic_error("SDK autosave requires a bound save provider");
        const auto save=state_->autoSave;
        struct Saving {bool& active;explicit Saving(bool& flag):active(flag){active=true;}~Saving(){active=false;}} scope(state_->autoSaveRunning);
        save(initial,postTurn);
    }
    // This isolated executable has no Steam connection or account state.
    // Report unavailable statistics, never fabricate successful platform writes
    // or unlocked achievements. Failed reads leave caller-owned output intact.
    static constexpr bool PlatformStatisticsAvailable() noexcept {return false;}
    void UnlockAchievement(EAchievement achievement) override {
        state_->Record("platform-achievement-unavailable:unlock:"+std::to_string(static_cast<int>(achievement)));
    }
    bool IsAchievementUnlocked(EAchievement achievement) const override {
        state_->Record("platform-achievement-unavailable:query:"+std::to_string(static_cast<int>(achievement)));
        return false;
    }
    bool GetSteamStat(ESteamStat stat,int32* output) const override {
        (void)output;
        state_->Record("platform-stat-unavailable:get:"+std::to_string(static_cast<int>(stat)));
        return false;
    }
    bool SetSteamStat(ESteamStat stat,int32 value) override {
        state_->Record("platform-stat-unavailable:set:"+std::to_string(static_cast<int>(stat))+":"+std::to_string(value));
        return false;
    }
    bool IncrementSteamStat(ESteamStat stat) override {
        state_->Record("platform-stat-unavailable:increment:"+std::to_string(static_cast<int>(stat)));
        return false;
    }
    bool IncrementSteamStatAndUnlock(ESteamStat stat,int threshold,EAchievement achievement) override {
        state_->Record("platform-stat-unavailable:increment-unlock:"+std::to_string(static_cast<int>(stat))+":"+
            std::to_string(threshold)+":"+std::to_string(static_cast<int>(achievement)));
        return false;
    }
    void openSlot(PlayerTypes player) override {SetSlot(player,true);}
    void closeSlot(PlayerTypes player) override {SetSlot(player,false);}
    void GameplayMetTeam(TeamTypes mine,TeamTypes theirs) override {
        if(mine<0 || mine>=MAX_TEAMS || theirs<0 || theirs>=MAX_TEAMS)
            throw std::invalid_argument("Invalid team contact notification");
        state_->Record("gameplay-met-team:"+std::to_string(static_cast<int>(mine))+":"+std::to_string(static_cast<int>(theirs)));
    }
    void GameplayWarStateChanged(TeamTypes first,TeamTypes second,bool war) override {
        if(first<0 || first>=MAX_TEAMS || second<0 || second>=MAX_TEAMS)
            throw std::invalid_argument("Invalid team war notification");
        state_->Record("gameplay-war-state:"+std::to_string(static_cast<int>(first))+":"+
            std::to_string(static_cast<int>(second))+":"+(war?"1":"0"));
        if(state_->routeWarStateChanged){
            const OwnedWarStateChanged changed(first,second,war);
            state_->routeWarStateChanged(changed);
        }
    }
    void GameplayTechAcquired(TeamTypes team,TechTypes technology) override {
        if(team<0 || team>=MAX_TEAMS || technology<0)throw std::invalid_argument("Invalid acquired technology notification");
        state_->Record("gameplay-tech-acquired:"+std::to_string(static_cast<int>(team))+":"+std::to_string(static_cast<int>(technology)));
    }
    void GameplayYieldMightHaveChanged(ICvPlot1* plot) override {
        if(!plot)throw std::invalid_argument("Yield notification requires a plot");
        int x=0,y=0;plot->GetPosition(x,y);
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->events.push_back("gameplay-plot-yield:"+std::to_string(x)+":"+std::to_string(y));
        state_->dirty[static_cast<int>(PlotData_DIRTY_BIT)]=true;
    }
    void GameplayFeatureChanged(ICvPlot1* plot,FeatureTypes newFeature) override {
        if(!plot)throw std::invalid_argument("Feature notification requires a plot");
        if(newFeature<NO_FEATURE)throw std::invalid_argument("Invalid feature notification value");
        // CvPlot::setFeatureType sends this callback before storing the new
        // value, so preserve the supplied value instead of querying the plot.
        int x=0,y=0;plot->GetPosition(x,y);
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->events.push_back("gameplay-plot-feature:"+std::to_string(x)+":"+
            std::to_string(y)+":"+std::to_string(static_cast<int>(newFeature)));
        state_->dirty[static_cast<int>(PlotData_DIRTY_BIT)]=true;
    }
    void GameplayUnitShouldDimFlag(ICvUnit1* unit,bool dim) override {
        if(!unit)throw std::invalid_argument("Unit dim-flag notification requires a unit");
        // The DLL adapter is borrowed. Copy its stable identity immediately and
        // retain only host-owned scalar values after returning from this call.
        const PlayerTypes owner=unit->GetOwner();
        const int unitId=unit->GetID();
        if(owner<0 || owner>=MAX_PLAYERS || unitId<0)
            throw std::invalid_argument("Invalid unit dim-flag notification identity");
        // Record a notification, not a live-unit registry: graphics-disabled
        // SDK sessions do not emit every unit-destruction callback.
        state_->Record("gameplay-unit-dim-flag:"+std::to_string(static_cast<int>(owner))+":"+
            std::to_string(unitId)+":"+(dim?"1":"0"));
    }
    void GameplayUnitFortify(ICvUnit1* unit,bool fortified) override {
        if(!unit)throw std::invalid_argument("Unit fortification notification requires a unit");
        const auto owner=unit->GetOwner();const int id=unit->GetID();
        if(owner<0 || owner>=MAX_PLAYERS || id<0)
            throw std::invalid_argument("Invalid unit fortification notification identity");
        // Presentation notification only; the SDK owns the fortification rules.
        state_->Record("gameplay-unit-fortify:"+std::to_string(static_cast<int>(owner))+":"+
            std::to_string(id)+":"+(fortified?"1":"0"));
    }
    uint GameplayCityCombat(ICvCombatInfo1* info) override {
        RequireCommandOwner();state_->RecordCombat(CombatPresentation::Capture(info,true));
        // No renderer event was scheduled. The SDK resolves combat itself
        // immediately after this callback and accepts zero as no parent event.
        return 0;
    }
    uint GameplayUnitCombat(ICvCombatInfo1* info) override {
        RequireCommandOwner();state_->RecordCombat(CombatPresentation::Capture(info,false));return 0;
    }
    void GameplayUnitSetDamage(ICvUnit1* unit,int damage,int previous) override {
        RequireCommandOwner();
        if(damage<0 || previous<0)throw std::invalid_argument("Invalid unit damage notification");
        state_->Record(UnitIdentity(unit,"gameplay-unit-damage:")+":"+std::to_string(damage)+":"+std::to_string(previous));
    }
    void GameplayUnitDestroyedInCombat(ICvUnit1* unit) override {
        RequireCommandOwner();state_->Record(UnitIdentity(unit,"gameplay-unit-destroyed-in-combat:"));
    }
    void GameplayUnitDestroyed(ICvUnit1* unit) override {
        RequireCommandOwner();state_->Record(UnitIdentity(unit,"gameplay-unit-destroyed:"));
    }
    void GameplayUnitActivate(ICvUnit1* unit) override {
        RequireCommandOwner();state_->Record(UnitIdentity(unit,"gameplay-unit-activate:"));
    }
    void GameplayUnitMissionEnd(ICvUnit1* unit) override {
        RequireCommandOwner();state_->Record(UnitIdentity(unit,"gameplay-unit-mission-end:"));
    }
    void GameplayUnitWork(ICvUnit1* unit,int workType) override {
        RequireCommandOwner();
        // The SDK supplies -1 to end work and a build/route value to begin it.
        state_->Record(UnitIdentity(unit,"gameplay-unit-work:")+":"+std::to_string(workType));
    }
    void GameplayDoFX(ICvPlot1* plot,int type=-1) override {
        RequireCommandOwner();
        int x=-1,y=-1;if(plot)plot->GetPosition(x,y);
        state_->Record("gameplay-effect:"+std::to_string(x)+":"+std::to_string(y)+":"+std::to_string(type));
    }
    void GameplayMinimapNotification(int x,int y,int id) override {
        RequireCommandOwner();
        if(id<=0)throw std::invalid_argument("Minimap notification requires a positive notification marker");
        state_->Record("gameplay-minimap-notification:"+std::to_string(id)+":"+std::to_string(x)+":"+std::to_string(y));
    }
    void GameplayCityCreated(ICvCity1* city,EraTypes era) override {
        if(!city || city->GetOwner()<0 || city->GetOwner()>=MAX_PLAYERS || city->GetID()<0 || era<0)
            throw std::invalid_argument("Invalid city creation notification");
        state_->Record("gameplay-city-created:"+std::to_string(static_cast<int>(city->GetOwner()))+":"+
            std::to_string(city->GetID())+":"+std::to_string(city->GetX())+":"+std::to_string(city->GetY())+":"+std::to_string(static_cast<int>(era)));
    }
    void GameplayCityCaptured(ICvCity1* city,PlayerTypes newOwner) override {
        RequireCommandOwner();RecordCityRemoval(city,newOwner,"gameplay-city-captured:");
    }
    void GameplayCityDestroyed(ICvCity1* city,PlayerTypes responsible) override {
        RequireCommandOwner();RecordCityRemoval(city,responsible,"gameplay-city-destroyed:");
    }
    void RecordCityRemoval(ICvCity1* city,PlayerTypes other,const char* prefix){
        if(!city || city->GetOwner()<0 || city->GetOwner()>=MAX_PLAYERS || city->GetID()<0 ||
           other<NO_PLAYER || other>=MAX_PLAYERS)
            throw std::invalid_argument("Invalid city capture/destruction notification");
        // The SDK deletes the old city immediately after this callback.
        // Retain scalar presentation identity only, never the borrowed adapter.
        state_->Record(std::string(prefix)+std::to_string(static_cast<int>(city->GetOwner()))+":"+
            std::to_string(city->GetID())+":"+std::to_string(city->GetX())+":"+std::to_string(city->GetY())+":"+
            std::to_string(static_cast<int>(other)));
    }
    void GameplayCitySetDamage(ICvCity1* city,int damage,int previous) override {
        if(!city || city->GetOwner()<0 || city->GetOwner()>=MAX_PLAYERS || city->GetID()<0 || damage<0 || previous<0)
            throw std::invalid_argument("Invalid city damage notification");
        state_->Record("gameplay-city-damage:"+std::to_string(static_cast<int>(city->GetOwner()))+":"+
            std::to_string(city->GetID())+":"+std::to_string(damage)+":"+std::to_string(previous));
    }
    void GameplayCityPopulationChanged(ICvCity1* city,int population) override {
        if(!city || city->GetOwner()<0 || city->GetOwner()>=MAX_PLAYERS || city->GetID()<0 || population<0)
            throw std::invalid_argument("Invalid city population notification");
        state_->Record("gameplay-city-population:"+std::to_string(static_cast<int>(city->GetOwner()))+":"+
            std::to_string(city->GetID())+":"+std::to_string(population));
    }
    void GameplayUnitVisibility(ICvUnit1* unit,bool visible,bool changeInvisibility=false,float blendTime=0.5f) override {
        if(!unit || unit->GetOwner()<0 || unit->GetOwner()>=MAX_PLAYERS || unit->GetID()<0 || !std::isfinite(blendTime) || blendTime<0)
            throw std::invalid_argument("Invalid unit visibility notification");
        state_->Record("gameplay-unit-visibility:"+std::to_string(static_cast<int>(unit->GetOwner()))+":"+
            std::to_string(unit->GetID())+":"+(visible?"1":"0")+":"+(changeInvisibility?"1":"0")+":"+std::to_string(blendTime));
    }
    void GameplayUnitMoved(ICvUnit1* unit,const CvPlotIndexVector& plots) override {
        const auto surface=state_->mapSurface.Snapshot();
        if(!unit || unit->GetOwner()<0 || unit->GetOwner()>=MAX_PLAYERS || unit->GetID()<0 || !surface)
            throw std::invalid_argument("Unit movement notification requires a valid unit and map");
        std::string event="gameplay-unit-moved:"+std::to_string(static_cast<int>(unit->GetOwner()))+":"+std::to_string(unit->GetID());
        for(const int plot:plots){
            if(plot<0 || static_cast<std::size_t>(plot)>=surface->dirtyPlots.size())throw std::invalid_argument("Invalid movement plot index");
            event+=":"+std::to_string(plot);
        }
        state_->Record(event);
    }
    void SetDone(bool value) override {state_->done=value;}
    bool GetDone() override {return state_->done;}
    bool GetAutorun() override {return false;}
    void GetGameCoreLock() override {state_->gameLock.Enter();}
    void ReleaseGameCoreLock() override {state_->gameLock.Leave();}
    bool TryGameCoreLock() override {return state_->gameLock.TryEnter();}
    bool HasGameCoreLock() override {return state_->gameLock.HeldByCurrentThread();}
    bool IsGameCoreThread() override {return state_->gameThread==GetCurrentThreadId();}
    bool IsGameCoreExecuting() override {return state_->executing.load(std::memory_order_acquire)!=0;}
    bool IsProcessingGameCoreMessages() override {return !state_->localCommands.IsQuiescent();}
    void netMessageDebugLog(const std::string& message) const override {state_->Record(message);}
    void GameplayDiplomacyAILeaderMessage(PlayerTypes player,DiploUIStateTypes state,const char* text,
                                          LeaderheadAnimationTypes animation,int data1=-1) override {
        RequireCommandOwner();
        if(!state_->addLeaderMessage)Unsupported("ICvEngineUtility1::GameplayDiplomacyAILeaderMessage");
        const OwnedLeaderMessage owned(player,state,text,animation,data1);
        state_->addLeaderMessage(owned);
    }
    void GameplayMinimapUnitSelect(int x,int y) override {
        RequireCommandOwner();if(x<0 || y<0)throw std::invalid_argument("Invalid minimap selection notification");
        state_->Record("gameplay-minimap-unit-select:"+std::to_string(x)+":"+std::to_string(y));
    }
    void TradeVisuals_NewRoute(int route,int player,TradeConnectionType type,int count,int x[],int y[]) override {
        RequireCommandOwner();state_->tradeRoutes.NewRoute(route,player,type,count,x,y);
        state_->Record("trade-visuals-new-route:"+std::to_string(route)+":"+std::to_string(player)+":"+
            std::to_string(static_cast<int>(type))+":"+std::to_string(count));
    }
    void TradeVisuals_UpdateRouteDirection(int route,bool forwards) override {
        RequireCommandOwner();state_->tradeRoutes.UpdateDirection(route,forwards);
        state_->Record("trade-visuals-update-route-direction:"+std::to_string(route)+":"+(forwards?"1":"0"));
    }
    void TradeVisuals_DestroyRoute(int route,int player) override {
        RequireCommandOwner();state_->tradeRoutes.DestroyRoute(route,player);
        state_->Record("trade-visuals-destroy-route:"+std::to_string(route)+":"+std::to_string(player));
    }
    void TradeVisuals_ActivatePopupRoute(int route) override {
        RequireCommandOwner();state_->tradeRoutes.ActivatePopup(route);
        state_->Record("trade-visuals-activate-popup-route:"+std::to_string(route));
    }
    void TradeVisuals_DeactivatePopupRoute() override {
        RequireCommandOwner();state_->tradeRoutes.DeactivatePopup();state_->Record("trade-visuals-deactivate-popup-route");
    }
private:
    static std::string UnitIdentity(ICvUnit1* unit,const char* prefix){
        if(!unit)throw std::invalid_argument("Unit presentation requires a borrowed unit");
        const int owner=static_cast<int>(unit->GetOwner()),id=unit->GetID();
        if(owner<0 || owner>=MAX_PLAYERS || id<0)throw std::invalid_argument("Invalid unit presentation identity");
        return std::string(prefix)+std::to_string(owner)+":"+std::to_string(id);
    }
    void RequireCommandOwner() const {
        if(state_->gameThread!=GetCurrentThreadId() || !state_->gameLock.HeldByCurrentThread())
            throw std::logic_error("Local SDK commands require the GameCore owner lock");
    }
    void SetSlot(PlayerTypes player,bool open){
        if(player<0 || player>=MAX_PLAYERS)throw std::invalid_argument("Invalid host player slot");
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->events.push_back(std::string(open?"player-slot-open:":"player-slot-close:")+std::to_string(static_cast<int>(player)));
        state_->openPlayerSlots[static_cast<std::size_t>(player)]=open;
    }
    std::shared_ptr<HostState> state_;
};

class UserInterface final : public UserInterfaceBase {
public:
    explicit UserInterface(std::shared_ptr<HostState> state):state_(std::move(state)){
        if(!state_)throw std::invalid_argument("UI service state missing");++state_->userAdapters;
    }
    ~UserInterface(){--state_->userAdapters;}
    static void* operator new(std::size_t bytes){return ::operator new(bytes);}
    static void operator delete(void* p) noexcept {::operator delete(p);}
    void* DLLCALL QueryInterface(GUID id) override {
        if(id==guidICvUnknown || id==guidICvUserInterface1 || id==guidICvUserInterface2)
            return static_cast<ICvUserInterface2*>(new UserInterface(state_));
        return nullptr;
    }
    void DLLCALL Destroy() override {delete this;}
    void OpenEndGameMenu() override {
        RequireUiOwner();if(!state_->openEndGameMenu)Unsupported("ICvUserInterface1::OpenEndGameMenu (unbound session provider)");
        state_->openEndGameMenu();
    }
    void AddPopup(int type,int intCount,const int* ints,int boolCount,const bool* bools) override {
        if(state_->gameThread!=GetCurrentThreadId() || !state_->gameLock.HeldByCurrentThread())
            throw std::logic_error("Array popup dispatch requires the GameCore owner lock");
        if(!state_->addArrayPopup)Unsupported("ICvUserInterface2::AddPopup");
        const OwnedPopupInfo owned(type,intCount,ints,boolCount,bools);
        state_->addArrayPopup(owned);
    }
    void AddPopup(const CvPopupInfo& popup) override {
        if(state_->gameThread!=GetCurrentThreadId() || !state_->gameLock.HeldByCurrentThread())
            throw std::logic_error("UI popup dispatch requires the GameCore owner lock");
        if(!state_->addPopup){
#if defined(ZEROSIS_HEADLESS_TURN_HOST)
            std::fprintf(stderr,"FULL_TURN_UNBOUND_POPUP=%d,%d,%d,%d\n",int(popup.eButtonPopupType),
                         popup.iData1,popup.iData2,popup.iData3);
#endif
            Unsupported("ICvUserInterface1::AddPopup");
        }
        state_->addPopup(popup);
    }
    void lookAtSelectionPlot(bool release=false) override {
        RequireUiOwner();
        // Every current SDK caller uses false. Camera-release semantics belong
        // to the unavailable original frontend and must not be silently ignored.
        if(release)Unsupported("ICvUserInterface1::lookAtSelectionPlot(bRelease=true) (camera release unavailable)");
        // selectCity can retain a prior unit selection; the active city takes
        // precedence until clearSelectedCities returns control to that unit.
        std::unique_ptr<ICvCity1> city(getHeadSelectedCity());
        std::unique_ptr<ICvUnit1> unit;
        std::unique_ptr<ICvPlot1> plot;
        if(city)plot.reset(city->Plot());
        else {
            unit.reset(GetHeadSelectedUnit());
            if(!unit)return; // No selected entity means no camera request.
            plot.reset(unit->GetPlot());
        }
        if(!plot)throw std::logic_error("Selected entity has no live SDK plot");
        lookAt(plot.get(),CAMERALOOKAT_NORMAL);
    }
    void lookAt(const ICvPlot1* plot,CameraLookAtTypes type) override {
        if(state_->gameThread!=GetCurrentThreadId() || !state_->gameLock.HeldByCurrentThread())
            throw std::logic_error("Camera requests require the GameCore owner lock");
        if(!plot || type<CAMERALOOKAT_NORMAL || type>CAMERALOOKAT_HOTSEAT)
            throw std::invalid_argument("Invalid camera presentation request");
        CameraPresentation value;value.plotIndex=plot->GetPlotIndex();
        plot->GetPosition(value.x,value.y);value.type=type;
        if(value.plotIndex<0)throw std::invalid_argument("Camera request has no map plot");
        if(state_->actionInfoActivationInProgress){
            if(state_->actionInfoOwner<0 || state_->actionInfoOwner>=MAX_PLAYERS || state_->actionInfoTurn<0)
                throw std::logic_error("ActionInfo notification callback lost its owner/turn stamp");
            ActionInfoRequest request;request.kind=ActionInfoRequest::Kind::LookAt;
            request.id=static_cast<int>(type);request.x=value.x;request.y=value.y;
            request.owner=state_->actionInfoOwner;request.turn=state_->actionInfoTurn;
            if(state_->actionInfoAdapterRequests.size()>=16)throw std::length_error("SDK notification emitted too many deferred camera requests");
            state_->actionInfoAdapterRequests.push_back(request);return;
        }
        const auto event="ui-camera:"+std::to_string(value.plotIndex)+":"+std::to_string(static_cast<int>(type));
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->events.push_back(event);
        try{state_->cameraPresentations.push_back(value);}
        catch(...){state_->events.pop_back();throw;}
    }
    bool CanDoInterfaceMode(InterfaceModeTypes mode,bool testVisible=false) override {
        RequireUiOwner();(void)testVisible;return mode==INTERFACEMODE_SELECTION;
    }
    void AddPopupText(int x,int y,const char* text,float delay=0) override {
        if(state_->gameThread!=GetCurrentThreadId() || !state_->gameLock.HeldByCurrentThread())
            throw std::logic_error("Floating text requires the GameCore owner lock");
        if(x<0 || y<0 || !text || !std::isfinite(delay) || delay<0)
            throw std::invalid_argument("Invalid floating text presentation");
        PopupTextPresentation value;value.x=x;value.y=y;value.delay=delay;value.text=text;
        const auto event="ui-popup-text:"+std::to_string(x)+":"+std::to_string(y);
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->events.push_back(event);
        try{state_->popupTexts.push_back(std::move(value));}
        catch(...){state_->events.pop_back();throw;}
    }
    uint AddMessage(uint parentEvent,PlayerTypes player,bool force,int length,const char* text,LPCTSTR sound=nullptr,
        InterfaceMessageTypes type=MESSAGE_TYPE_INFO,LPCSTR icon=nullptr,ColorTypes flashColor=NO_COLOR,
        int flashX=-1,int flashY=-1,bool offScreenArrows=false,bool onScreenArrows=false) override {
        if(state_->gameThread!=GetCurrentThreadId() || !state_->gameLock.HeldByCurrentThread())
            throw std::logic_error("Game messages require the GameCore owner lock");
        // CvTeam::announceTechToPlayers sends -1 for the single-player
        // research message. Preserve that SDK sentinel, as AddCityMessage does.
        if(player<0 || player>=MAX_PLAYERS || length<-1 || !text)
            throw std::invalid_argument("Invalid game message notification");
        PresentationMessage message;
        message.parentEvent=parentEvent;message.player=player;message.force=force;message.length=length;
        message.text=text;if(sound)message.sound=sound;if(icon)message.icon=icon;
        message.type=type;message.flashColor=flashColor;message.flashX=flashX;message.flashY=flashY;
        message.offScreenArrows=offScreenArrows;message.onScreenArrows=onScreenArrows;
        const std::string event="ui-message:"+std::to_string(parentEvent)+":"+std::to_string(static_cast<int>(player));
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->events.push_back(event);
        try{state_->presentationMessages.push_back(std::move(message));}
        catch(...){state_->events.pop_back();throw;}
        std::printf("UI_GAME_MESSAGE_RETAINED=%u|%d|%d|%d|%zu\n",parentEvent,static_cast<int>(player),length,
            static_cast<int>(type),state_->presentationMessages.back().text.size());
        return 0; // Recorded for the presentation consumer; no renderer event ID.
    }
    uint AddCityMessage(uint parentEvent,const IDInfo& cityID,PlayerTypes player,bool force,int length,const char* text,
        LPCTSTR sound=nullptr,InterfaceMessageTypes type=MESSAGE_TYPE_INFO,LPCSTR icon=nullptr,ColorTypes flashColor=NO_COLOR,
        int flashX=-1,int flashY=-1,bool offScreenArrows=false,bool onScreenArrows=false) override {
        RequireUiOwner();
        if(cityID.eOwner<0 || cityID.eOwner>=MAX_PLAYERS || cityID.iID<0 || player<0 || player>=MAX_PLAYERS || length<-1 || !text)
            throw std::invalid_argument("Invalid city message notification");
        PresentationMessage message;
        message.parentEvent=parentEvent;message.cityMessage=true;message.cityOwner=cityID.eOwner;message.cityId=cityID.iID;
        message.player=player;message.force=force;message.length=length;message.text=text;
        if(sound)message.sound=sound;if(icon)message.icon=icon;
        message.type=type;message.flashColor=flashColor;message.flashX=flashX;message.flashY=flashY;
        message.offScreenArrows=offScreenArrows;message.onScreenArrows=onScreenArrows;
        const std::string event="ui-city-message:"+std::to_string(parentEvent)+":"+
            std::to_string(static_cast<int>(cityID.eOwner))+":"+std::to_string(cityID.iID)+":"+std::to_string(static_cast<int>(player));
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->events.push_back(event);
        try{state_->presentationMessages.push_back(std::move(message));}
        catch(...){state_->events.pop_back();throw;}
        return 0;
    }
    void PublishEndTurnDirty() const override {
        // Preserve the engine's refresh notification for the host presentation
        // consumer, including headless sessions that have no visible button.
        state_->Record("ui-end-turn-dirty");
    }
    void AddNotification(int id,NotificationTypes type,const char* tooltip,const char* summary,int gameData,
        int extraGameData,PlayerTypes player,int x=-1,int y=-1) override {
        if(state_->gameThread!=GetCurrentThreadId() || !state_->gameLock.HeldByCurrentThread())
            throw std::logic_error("Notifications require the GameCore owner lock");
        if(id<0 || player<0 || player>=MAX_PLAYERS || !tooltip || !summary)
            throw std::invalid_argument("Invalid notification presentation");
        NotificationPresentation value;
        value.id=id;value.type=type;value.tooltip=tooltip;value.summary=summary;
        value.gameData=gameData;value.extraGameData=extraGameData;value.player=player;value.x=x;value.y=y;
        const auto key=std::make_pair(static_cast<int>(player),id);
        const auto event="ui-notification-add:"+std::to_string(static_cast<int>(player))+":"+std::to_string(id)+":"+
            std::to_string(static_cast<int>(type));
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->events.push_back(event);
        try{state_->notifications.insert_or_assign(key,std::move(value));}
        catch(...){state_->events.pop_back();throw;}
    }
    void RemoveNotification(int id,PlayerTypes player) override {
        if(state_->gameThread!=GetCurrentThreadId() || !state_->gameLock.HeldByCurrentThread())
            throw std::logic_error("Notifications require the GameCore owner lock");
        if(id<0 || player<0 || player>=MAX_PLAYERS)throw std::invalid_argument("Invalid notification removal");
        const auto key=std::make_pair(static_cast<int>(player),id);
        const auto event="ui-notification-remove:"+std::to_string(static_cast<int>(player))+":"+std::to_string(id);
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        // The SDK may expire a notification before it was broadcast to this UI.
        state_->events.push_back(event);state_->notifications.erase(key);
    }
    void PublishPlayerTurnStatus(CvDLLInterfaceIFaceBase::TURN_STATUS_TYPE status,PlayerTypes player,const char* tag=nullptr) override {
        if(player<0 || player>=MAX_PLAYERS || status<CvDLLInterfaceIFaceBase::TURN_START || status>CvDLLInterfaceIFaceBase::TURN_STEP)
            throw std::invalid_argument("Invalid player turn notification");
        state_->Record("ui-player-turn-status:"+std::to_string(static_cast<int>(status))+":"+
            std::to_string(static_cast<int>(player))+":"+(tag?tag:""));
    }
    void PublishActivePlayerTurnStart() override {state_->Record("ui-active-player-turn-start");}
    void PublishActivePlayerTurnEnd() override {state_->Record("ui-active-player-turn-end");}
    bool IsLoadedGame() const override {return state_->loadedGame.load(std::memory_order_acquire);}
    // No text input or diplomatic presentation is opened by this headless
    // host; requests to open one still fail at their unsupported entry point.
    bool isFocused() override {return state_->popupVisible;}
    bool isFocusedWidget() override {return state_->popupVisible;}
    bool isPopupUp() override {return state_->popupVisible;}
    bool isPopupQueued() override {return false;} // The supported single context is dispatched immediately.
    bool IsPopupQueueEmpty() override {return !state_->popupVisible;}
    bool isCombatFocus() override {return state_->combatFocus;}
    void setCombatFocus(bool value) override {
        if(state_->gameThread!=GetCurrentThreadId() || !state_->gameLock.HeldByCurrentThread())
            throw std::logic_error("Combat focus changes require the GameCore owner lock");
        state_->Record(std::string("ui-combat-focus:")+(value?"1":"0"));
        state_->combatFocus=value;
    }
    void ActivateNotification(int id,NotificationTypes type,const char* text,int x,int y,int gameData,
        int extraGameData,PlayerTypes player) override {
        RequireUiOwner();
        if(!state_->actionInfoActivationInProgress || player!=state_->actionInfoOwner || id<0 || !text ||
           !IsSupportedActionInfoNotification(type))
            throw std::logic_error("SDK notification activation did not match a verified ActionInfo route");
        const auto key=std::make_pair(static_cast<int>(player),id);
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        const auto found=state_->notifications.find(key);
        if(found==state_->notifications.end() || found->second.type!=type || found->second.tooltip!=text || found->second.x!=x || found->second.y!=y ||
           found->second.gameData!=gameData || found->second.extraGameData!=extraGameData)
            throw std::logic_error("SDK notification activation differs from the retained original notification");
        state_->events.push_back("ui-notification-activate:"+std::to_string(static_cast<int>(player))+":"+
            std::to_string(id)+":"+std::to_string(static_cast<int>(type)));
    }
    bool isDiploActive() override {RequireUiOwner();return state_->leaderRootUp || state_->pendingLeaderMessages!=0;}
    bool isCityScreenUp() override {RequireUiOwner();return state_->cityScreenUp;}
    bool IsCityScreenViewingMode() const {
        RequireUiOwner();return state_->cityScreenViewingMode;
    }
    void SetCityScreenViewingMode(bool value) {
        RequireUiOwner();
        if(state_->cityScreenViewingMode==value)return;
        state_->cityScreenViewingMode=value;
        state_->Record(std::string("ui-city-viewing-mode:")+(value?"1":"0"));
    }
    void setCityScreenUp(bool value) override {
        RequireUiOwner();
        if(state_->cityScreenUp==value)return;
        state_->cityScreenUp=value;
        state_->Record(std::string("ui-city-screen:")+(value?"1":"0"));
    }
    bool canEndTurn() const override {std::lock_guard<std::mutex> guard(state_->dataMutex);return state_->canEndTurn;}
    void setCanEndTurn(bool value) override {std::lock_guard<std::mutex> guard(state_->dataMutex);state_->canEndTurn=value;}
    bool isHasMovedUnit() override {std::lock_guard<std::mutex> guard(state_->dataMutex);return state_->hasMovedUnit;}
    void setHasMovedUnit(bool value) override {std::lock_guard<std::mutex> guard(state_->dataMutex);state_->hasMovedUnit=value;}
    void setNoSelectionListCycle(bool value) override {std::lock_guard<std::mutex> guard(state_->dataMutex);state_->noSelectionCycle=value;}
    bool IsSPAutoEndTurnEnabled() override {return false;}
    bool IsOptionNoRewardPopups() override {return state_->noRewardPopupsCommitted->load(std::memory_order_acquire);}
    bool waitingForRemotePlayers() const override {return false;}
    void UpdateEndTurn() override {state_->Record("ui-update-end-turn");}
    bool IsPolicyNotificationSeen() const override {RequireUiOwner();return state_->policyNotificationSeen;}
    void SetPolicyNotificationSeen(bool value) override {
        RequireUiOwner();state_->Record(std::string("ui-policy-notification-seen:")+(value?"1":"0"));
        state_->policyNotificationSeen=value;
    }
    void SetEndTurnBlockingChanged(EndTurnBlockingTypes previous,EndTurnBlockingTypes next) override {
        state_->Record("ui-end-turn-blocking:"+std::to_string(static_cast<int>(previous))+":"+std::to_string(static_cast<int>(next)));
    }
    void doTurn() override {state_->Record("ui-turn-boundary");}
    void setInterfaceMode(InterfaceModeTypes mode) override {
        RequireUiOwner();
        if(mode!=INTERFACEMODE_SELECTION &&
           ((mode!=INTERFACEMODE_PURCHASE_PLOT && mode!=INTERFACEMODE_CITY_PLOT_SELECTION) ||
            !state_->cityScreenUp || state_->cityScreenViewingMode || state_->selectedCityId<0))
            Unsupported("Interface mode requires its editable selected CityView");
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->interfaceMode=mode;state_->events.push_back("ui-interface-mode:"+std::to_string(static_cast<int>(mode)));
    }
    InterfaceModeTypes getInterfaceMode() override {
        std::lock_guard<std::mutex> guard(state_->dataMutex);return state_->interfaceMode;
    }
    bool IsDontShowPopups() const override {
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        return state_->dontShowPopups;
    }
    void SetDontShowPopups(bool value) override {
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        if(state_->dontShowPopups==value)return;
        state_->dontShowPopups=value;
        state_->events.push_back(std::string("ui-dont-show-popups:")+(value?"1":"0"));
    }
    // This executable creates headless sessions without a selection input
    // controller. Selection mutations remain unsupported, so the valid initial
    // selection stays empty throughout these sessions.
    ICvUnit1* GetHeadSelectedUnit() override {RequireUiOwner();return state_->localSelection.Head();}
    bool RemoveFromSelectionList(ICvUnit1* unit) override {
        RequireUiOwner();if(!unit)throw std::invalid_argument("Selection removal requires a borrowed unit");
        return state_->localSelection.Remove(unit->GetOwner(),unit->GetID());
    }
    ICvUnit1* getLastSelectedUnit() override {RequireUiOwner();return state_->localSelection.Last();}
    void setLastSelectedUnit(ICvUnit1* unit) override {
        RequireUiOwner();if(!unit){state_->localSelection.ClearLast();return;}
        state_->localSelection.SetLast(unit->GetOwner(),unit->GetID());
    }
    void selectCity(ICvCity1* city,bool testProduction=false) override {
        RequireUiOwner();
        if(testProduction)
            Unsupported("ICvUserInterface1::selectCity(bTestProduction=true) (production-aware CityView selection is not implemented)");
        if(!city)throw std::invalid_argument("City selection requires a borrowed city");
        const PlayerTypes owner=city->GetOwner();const int id=city->GetID();
        if(owner<0 || owner>=MAX_PLAYERS || id<0)
            throw std::invalid_argument("City selection identity is outside SDK limits");
        if(!state_->resolveCity)
            throw std::logic_error("City selection requires a live SDK city resolver");
        std::unique_ptr<ICvCity1> resolved(state_->resolveCity(owner,id));
        if(!resolved || resolved->GetOwner()!=owner || resolved->GetID()!=id)
            throw std::invalid_argument("City selection refers to an absent or changed SDK city");
        state_->selectedCityOwner=owner;state_->selectedCityId=id;
        state_->Record("ui-city-select:"+std::to_string(static_cast<int>(owner))+":"+std::to_string(id));
    }
    void clearSelectedCities() override {
        RequireUiOwner();
        state_->selectedCityOwner=NO_PLAYER;state_->selectedCityId=-1;state_->cityScreenUp=false;
        state_->Record("ui-city-selection-cleared");
    }
    ICvPlot1* getSelectionPlot() override {
        RequireUiOwner();std::unique_ptr<ICvUnit1> unit(state_->localSelection.Head());return unit?unit->GetPlot():nullptr;
    }
    int GetLengthSelectionList() override {RequireUiOwner();return state_->localSelection.Length();}
    bool IsUnitSelected(PlayerTypes playerID,int unitID) override {
        RequireUiOwner();return state_->localSelection.IsSelected(playerID,unitID);
    }
    void selectUnit(ICvUnit1* unit,bool clear,bool toggle=false,bool sound=false) override {
        RequireUiOwner();
        if(state_->actionInfoActivationInProgress){
            if(!unit || !clear || toggle || sound || unit->GetOwner()!=state_->actionInfoOwner || unit->GetID()<0 ||
               unit->IsDelayedDeathExported())
                throw std::invalid_argument("SDK notification selected an invalid or unowned unit");
            ActionInfoRequest request;request.kind=ActionInfoRequest::Kind::SelectUnit;
            request.id=unit->GetID();request.owner=state_->actionInfoOwner;request.turn=state_->actionInfoTurn;
            if(state_->actionInfoAdapterRequests.size()>=16)throw std::length_error("SDK notification emitted too many deferred unit selections");
            state_->actionInfoAdapterRequests.push_back(request);return;
        }
        (void)unit;(void)clear;(void)toggle;(void)sound;
        Unsupported("ICvUserInterface1::selectUnit (native ICvGame1::SelectUnit input is required)");
    }
    void selectGroup(ICvUnit1* unit,bool shift,bool control,bool alt) override {
        RequireUiOwner();(void)unit;(void)shift;(void)control;(void)alt;
        Unsupported("ICvUserInterface1::selectGroup (multi-unit selection is unsupported)");
    }
    void selectAll(ICvPlot1* plot) override {
        RequireUiOwner();(void)plot;Unsupported("ICvUserInterface1::selectAll (multi-unit selection is unsupported)");
    }
    bool IsSelectedUnitRevealingNewPlots() const override {RequireUiOwner();return state_->selectedUnitRevealingNewPlots;}
    void SetSelectedUnitRevealingNewPlots(bool value) override {
        RequireUiOwner();state_->Record(std::string("ui-selected-unit-revealing-new-plots:")+(value?"1":"0"));
        state_->selectedUnitRevealingNewPlots=value;
    }
    void ClearSelectionList() override {RequireUiOwner();state_->localSelection.Clear();state_->selectedUnitRevealingNewPlots=false;}
    void InsertIntoSelectionList(ICvUnit1* unit,bool clear,bool toggle,bool group=false,bool sound=false,bool minimalChange=false) override {
        RequireUiOwner();if(!unit)throw std::invalid_argument("Selection insertion requires a borrowed unit");
        if(sound)Unsupported("ICvUserInterface1::InsertIntoSelectionList (selection sound unavailable)");
        state_->localSelection.InsertSingle(unit->GetOwner(),unit->GetID(),clear,toggle,group,minimalChange);
        if(clear)state_->selectedUnitRevealingNewPlots=false;
    }
    ICvEnumerator* GetSelectedUnits() override {RequireUiOwner();return state_->localSelection.CreateEnumerator();}
    void makeSelectionListDirty() override {RequireUiOwner();state_->localSelection.MarkDirty();}
    bool isCitySelected(ICvCity1* city) override {
        RequireUiOwner();
        if(!city || state_->selectedCityOwner==NO_PLAYER || state_->selectedCityId<0)return false;
        std::unique_ptr<ICvCity1> selected(getHeadSelectedCity());
        return selected && selected->GetOwner()==city->GetOwner() && selected->GetID()==city->GetID();
    }
    ICvCity1* getHeadSelectedCity() override {
        RequireUiOwner();
        if(state_->selectedCityOwner==NO_PLAYER && state_->selectedCityId==-1)return nullptr;
        if(state_->selectedCityOwner<0 || state_->selectedCityOwner>=MAX_PLAYERS || state_->selectedCityId<0)
            throw std::logic_error("Owned city-selection identity is internally inconsistent");
        if(!state_->resolveCity)throw std::logic_error("Selected city lookup requires a live SDK city resolver");
        std::unique_ptr<ICvCity1> resolved(state_->resolveCity(state_->selectedCityOwner,state_->selectedCityId));
        if(!resolved || resolved->GetOwner()!=state_->selectedCityOwner || resolved->GetID()!=state_->selectedCityId){
            state_->selectedCityOwner=NO_PLAYER;state_->selectedCityId=-1;state_->cityScreenUp=false;
            state_->Record("ui-city-selection-stale-cleared");return nullptr;
        }
        return resolved.release();
    }
    bool isCitySelection() override {
        RequireUiOwner();std::unique_ptr<ICvCity1> selected(getHeadSelectedCity());return static_cast<bool>(selected);
    }
    IDInfo* headSelectedCitiesNode() override {
        RequireUiOwner();std::unique_ptr<ICvCity1> selected(getHeadSelectedCity());
        if(!selected){state_->selectedCityNode.reset();return nullptr;}
        state_->selectedCityNode=IDInfo(selected->GetOwner(),selected->GetID());
        return &state_->selectedCityNode;
    }
    IDInfo* nextSelectedCitiesNode(IDInfo* node) override {
        RequireUiOwner();
        if(node!=&state_->selectedCityNode)throw std::invalid_argument("Unknown selected city node");
        return nullptr;
    }
    const IDInfo* nextSelectedCitiesNode(const IDInfo* node) const override {
        RequireUiOwner();
        if(node!=&state_->selectedCityNode)throw std::invalid_argument("Unknown selected city node");
        return nullptr;
    }
    void SetSpecificCityInfoDirty(ICvCity1* city,CityUpdateTypes update) override {
        if(!city || city->GetOwner()<0 || city->GetOwner()>=MAX_PLAYERS || city->GetID()<0)
            throw std::invalid_argument("City refresh requires a valid borrowed city");
        state_->Record("ui-city-dirty:"+std::to_string(static_cast<int>(city->GetOwner()))+":"+
            std::to_string(city->GetID())+":"+std::to_string(static_cast<int>(update)));
    }
    void UpdateCountryBorder(ICvPlot1* plot) override {
        if(!plot)throw std::invalid_argument("Border refresh requires a borrowed plot");
        int x=0,y=0;plot->GetPosition(x,y);
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->events.push_back("ui-country-border:"+std::to_string(x)+":"+std::to_string(y));
        state_->dirty[static_cast<int>(NationalBorders_DIRTY_BIT)]=true;
    }
    void AddDeferredWonderCommand(WonderCommandType command,ICvCity1* city,BuildingTypes building,int state) override {
        if(!city || city->GetOwner()<0 || city->GetOwner()>=MAX_PLAYERS || city->GetID()<0 || building<0)
            throw std::invalid_argument("Deferred building presentation requires a valid city and building");
        // Copy the presentation command; the borrowed city adapter cannot be
        // retained past this callback. A renderer can consume these in order.
        state_->Record("ui-building-command:"+std::to_string(static_cast<int>(command))+":"+
            std::to_string(static_cast<int>(city->GetOwner()))+":"+std::to_string(city->GetID())+":"+
            std::to_string(static_cast<int>(building))+":"+std::to_string(state));
    }
    bool isDirty(InterfaceDirtyBits item) override {
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        const auto found=state_->dirty.find(static_cast<int>(item));return found!=state_->dirty.end() && found->second;
    }
    void setDirty(InterfaceDirtyBits item,bool value) override {std::lock_guard<std::mutex> guard(state_->dataMutex);state_->dirty[static_cast<int>(item)]=value;}
    int getCycleSelectionCounter() override {std::lock_guard<std::mutex> guard(state_->dataMutex);return state_->cycleSelection;}
    void setCycleSelectionCounter(int value) override {std::lock_guard<std::mutex> guard(state_->dataMutex);state_->cycleSelection=value;}
    void changeCycleSelectionCounter(int value) override {
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        const long long next=static_cast<long long>(state_->cycleSelection)+value;
        if(next<INT_MIN || next>INT_MAX)throw std::overflow_error("UI selection counter overflow");
        state_->cycleSelection=static_cast<int>(next);
    }
private:
    void RequireUiOwner() const {
        if(state_->gameThread!=GetCurrentThreadId() || !state_->gameLock.HeldByCurrentThread())
            throw std::logic_error("Local UI selection requires the GameCore owner lock");
    }
    std::shared_ptr<HostState> state_;
};

class GameCall {
public:
    explicit GameCall(HostState& state):state_(state){state_.gameLock.Enter();state_.executing.fetch_add(1,std::memory_order_release);}
    ~GameCall(){state_.executing.fetch_sub(1,std::memory_order_release);state_.gameLock.Leave();}
    GameCall(const GameCall&)=delete;
    GameCall& operator=(const GameCall&)=delete;
private:
    HostState& state_;
};
}
