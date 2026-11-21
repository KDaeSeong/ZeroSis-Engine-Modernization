#pragma once
#include "UiPopupContext.h"
#include "UiPanelRepaint.h"
#include <chrono>
#include <deque>
#include <exception>
#include <limits>

namespace ZeroSisHost {

// The world session owns the popup router. SDK callbacks only enqueue work:
// constructing/replacing a Lua context happens after the callback has returned.
class InteractiveUiSession final {
public:
    struct Frame final {
        std::string context,snapshot,cityBackdrop;
        std::vector<UiInputTarget> clicks,scrolls;
        std::string economicBackdrop;
        bool textInputEnabled=false;
        std::uint64_t textInputOwner=0;
    };
    struct ActionInfoObservation final {
        int owner=-1,turn=-1,blockingType=-1,notificationIndex=-1;
        bool canEndTurn=false;
        std::vector<NotificationPresentation> notifications;
    };
    InteractiveUiSession(std::shared_ptr<HostState> host,ICvGameContext3& core,std::wstring directory)
        :owner_(std::move(host)),host_(CheckedHost(owner_)),core_(&core),directory_(std::move(directory)) {
        Require();
        if(host_.addPopup || host_.addArrayPopup || host_.addLeaderMessage || host_.routeWarStateChanged || host_.closeInformationalPopup || host_.resolveCity)
            throw std::logic_error("Interactive UI needs an unbound popup router");
        try{
            host_.uiOptionsPath=directory_+L"\\ui-options.json";
            host_.resolveCity=[this](PlayerTypes owner,int id)->ICvCity1*{
                Require();if(!core_ || owner<0 || owner>=MAX_PLAYERS || id<0)return nullptr;
                std::unique_ptr<ICvGame1> game(core_->GetGame());
                std::unique_ptr<ICvPlayer1> player(game?game->GetPlayer(owner):nullptr);
                return player && player->IsAlive()?player->GetCity(id):nullptr;
            };
            host_.addPopup=[this](const CvPopupInfo& input){Queue(OwnedPopupInfo(input));};
            host_.addArrayPopup=[this](const OwnedPopupInfo& input){Queue(input);};
            host_.addLeaderMessage=[this](const OwnedLeaderMessage& input){QueueLeader(input);};
            host_.routeWarStateChanged=[this](const OwnedWarStateChanged& input){QueueWarStateChanged(input);};
            host_.closeInformationalPopup=[this](){Require();closePending_=true;};
        }catch(...){host_.resolveCity={};host_.addPopup={};host_.addArrayPopup={};host_.addLeaderMessage={};host_.routeWarStateChanged={};host_.closeInformationalPopup={};throw;}
    }
    ~InteractiveUiSession(){if(popup_ || idleProduction_ || suspendedCapture_ || suspendedCity_ || suspendedEconomic_ || suspendedGameMenu_ || suspendedSaveMenu_ || unitPanel_ || topPanel_ || actionInfoPanel_ || notificationPanel_ || core_)std::terminate();}
    void Stop(){
        Require();stopping_=true;pending_.clear();leaderWarStates_.clear();closePending_=false;
        textInputOwner_=0;
        DiscardIdleProduction();
        if(HasEconomicContext())StopEconomicContexts();
        if(popup_){popup_->Stop();popup_.reset();}
        if(suspendedSaveMenu_){suspendedSaveMenu_->Stop();suspendedSaveMenu_.reset();}
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
    bool HasModal() const {Require();return (popup_ && popup_->IsActive()) || suspendedCapture_ || suspendedCity_ || suspendedEconomic_ || suspendedGameMenu_ || suspendedSaveMenu_ || !pending_.empty();}
    bool IsActive() const {Require();return popup_ && popup_->IsActive();}
    bool IsPantheonCommitBoundary(int owner,int turn,int belief) const {
        Require();
        if(stopping_ || !popup_ || kind_!=UiPopupKind::Pantheon || suspendedCapture_ || suspendedCity_ ||
           suspendedEconomic_ || suspendedGameMenu_)return false;
        return popup_->IsPantheonCommitBoundary(owner,turn,belief);
    }
    void RefreshSocialPolicy(){
        Require();
        if(!popup_ || kind_!=UiPopupKind::SocialPolicy || stopping_ || !pending_.empty())
            throw std::logic_error("Policy refresh requires the active original policy router context");
        popup_->RefreshSocialPolicy();
    }
    bool HasCityView() const {Require();return suspendedCity_ || (popup_ && kind_==UiPopupKind::CityView && popup_->IsActive());}
    void OpenGameMenu(){
        Require();if(stopping_ || HasModal() || popup_ || !host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("Game menu entry requires an idle UI router after its original callback");
        const auto folder=directory_+L"\\play-context-"+std::to_wstring(++contextSequence_);
        if(!CreateDirectoryW(folder.c_str(),nullptr))throw std::runtime_error("Cannot allocate original GameMenu context directory");
        kind_=UiPopupKind::GameMenu;
        popup_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,kind_,false,true));
        popup_->OpenGameMenu();opened_=std::chrono::steady_clock::now();
        std::printf("INTERACTIVE_UI_OPENED=%u|game-menu\n",contextSequence_);
    }
    std::vector<GameMenuRequest> TakeGameMenuRequests(){
        Require();if(!host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("Game menu request handoff requires completed Lua callbacks");
        std::vector<GameMenuRequest> result;
        if(topPanel_)result=topPanel_->TakeGameMenuRequests();
        if(popup_ && (kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::ExitConfirm || kind_==UiPopupKind::SaveMenu)){
            auto requests=popup_->TakeGameMenuRequests();
            for(auto& request:requests)result.emplace_back(std::move(request));
        }
        if(result.size()>1)throw std::logic_error("One UI callback cannot dispatch multiple game menu commands");
        return result;
    }
    void FinishGameMenuForTransition(){
        Require();
        if(!host_.scripts || !host_.scripts->IsQuiescent() || !pending_.empty() || suspendedGameMenu_ || suspendedSaveMenu_)
            throw std::logic_error("Game transition requires the completed original menu callback");
        if(popup_){
            if(kind_!=UiPopupKind::GameMenu)throw std::logic_error("Game transition has another active popup");
            popup_->CloseInformationalPopup();Update();
        }
        if(HasModal() || popup_ || host_.popupVisible)throw std::logic_error("Game transition did not release its original modal lifetime");
    }
    void OpenMenuOptions(){OpenPrivateMenu(UiPopupKind::MenuOptions,{});}
    void OpenTouchHelp(){OpenPrivateMenu(UiPopupKind::TouchHelp,{});}
    void OpenMapMenu(std::shared_ptr<const UiMapMenuCatalog> catalog){
        if(!catalog)throw std::invalid_argument("Map menu requires a catalog");
        auto bound=std::make_shared<UiMapMenuCatalog>(*catalog);
        bound->parentContext=kind_==UiPopupKind::SaveMenu?"SaveMenu":"GameMenu";
        OpenPrivateMenu(UiPopupKind::MapMenu,std::move(bound));
    }
    std::vector<MapMenuRequest> TakeMapMenuRequests(){
        Require();
        if(!popup_ || kind_!=UiPopupKind::MapMenu || !suspendedGameMenu_)throw std::logic_error("Map handoff requires its original retained parent");
        return popup_->TakeMapMenuRequests();
    }
    void RefreshMapMenu(std::shared_ptr<const UiMapMenuCatalog> catalog){
        Require();if(!popup_ || kind_!=UiPopupKind::MapMenu)throw std::logic_error("Map refresh lost its child context");
        if(!catalog)throw std::invalid_argument("Map refresh requires a catalog");
        auto bound=std::make_shared<UiMapMenuCatalog>(*catalog);
        bound->parentContext=suspendedSaveMenu_?"SaveMenu":"GameMenu";
        popup_->RefreshMapMenu(std::move(bound));
    }
    void FinishMapMenuForSave(){
        Require();Update();
        if(popup_ && kind_==UiPopupKind::SaveMenu){CloseCurrent();Update();}
        FinishGameMenuForTransition();
    }
    void OpenExitConfirm(){
        Require();
        if(stopping_ || !popup_ || kind_!=UiPopupKind::GameMenu || !popup_->IsActive() ||
           suspendedGameMenu_ || suspendedCity_ || suspendedCapture_ || suspendedEconomic_ ||
           !pending_.empty() || !host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("Exit confirmation requires its sole retained original GameMenu parent");
        const auto before=SdkStateSnapshot::Capture(host_);
        suspendedGameMenu_=std::move(popup_);gameMenuOpened_=opened_;
        try{
            const auto folder=directory_+L"\\play-exit-confirm-"+std::to_wstring(++contextSequence_);
            if(!CreateDirectoryW(folder.c_str(),nullptr))
                throw std::runtime_error("Cannot allocate original ExitConfirm child directory");
            kind_=UiPopupKind::ExitConfirm;
            popup_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,kind_,false,true));
            popup_->OpenExitConfirm();opened_=std::chrono::steady_clock::now();
            if(before!=SdkStateSnapshot::Capture(host_))
                throw std::runtime_error("ExitConfirm entry changed SDK gameplay");
            std::printf("INTERACTIVE_UI_OPENED=%u|exit-confirm\n",contextSequence_);
        }catch(...){
            if(popup_){popup_->Stop();popup_.reset();}
            popup_=std::move(suspendedGameMenu_);kind_=UiPopupKind::GameMenu;opened_=gameMenuOpened_;
            host_.popupVisible=popup_ && popup_->IsActive();throw;
        }
    }
    void FinishExitConfirmForExit(){
        Require();
        if(!popup_ || kind_!=UiPopupKind::GameMenu || !popup_->IsActive() || suspendedGameMenu_ ||
           !pending_.empty() || !host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("Confirmed exit must return through its original GameMenu parent");
        CloseCurrent();Update();
        if(HasModal() || popup_ || host_.popupVisible)
            throw std::logic_error("Confirmed exit did not release its original parent modal lifetime");
    }
    void OpenSaveMenu(std::shared_ptr<const UiSaveMenuCatalog> catalog){
        Require();
        if(stopping_ || !popup_ || kind_!=UiPopupKind::GameMenu || !popup_->IsActive() ||
           suspendedGameMenu_ || suspendedCity_ || suspendedCapture_ || suspendedEconomic_ ||
           !pending_.empty() || !host_.scripts || !host_.scripts->IsQuiescent() || !catalog || !catalog->nameAvailable)
            throw std::logic_error("SaveMenu entry requires its sole retained original GameMenu parent");
        const auto before=SdkStateSnapshot::Capture(host_);
        suspendedGameMenu_=std::move(popup_);gameMenuOpened_=opened_;
        try{
            const auto folder=directory_+L"\\play-context-"+std::to_wstring(++contextSequence_);
            if(!CreateDirectoryW(folder.c_str(),nullptr))throw std::runtime_error("Cannot allocate original SaveMenu child directory");
            kind_=UiPopupKind::SaveMenu;
            popup_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,kind_,false,true,nullptr,-1,std::move(catalog)));
            popup_->OpenSaveMenu();opened_=std::chrono::steady_clock::now();
            if(before!=SdkStateSnapshot::Capture(host_))throw std::runtime_error("SaveMenu entry changed SDK gameplay");
            std::printf("INTERACTIVE_UI_OPENED=%u|save-menu\n",contextSequence_);
        }catch(...){
            if(popup_){popup_->Stop();popup_.reset();}
            popup_=std::move(suspendedGameMenu_);kind_=UiPopupKind::GameMenu;opened_=gameMenuOpened_;
            host_.popupVisible=popup_ && popup_->IsActive();throw;
        }
    }
    void OpenLoadMenu(std::shared_ptr<const UiLoadMenuCatalog> catalog){
        Require();
        if(stopping_ || !popup_ || kind_!=UiPopupKind::GameMenu || !popup_->IsActive() ||
           suspendedGameMenu_ || suspendedCity_ || suspendedCapture_ || suspendedEconomic_ ||
           !pending_.empty() || !host_.scripts || !host_.scripts->IsQuiescent() || !catalog || !catalog->canLoad ||
           catalog->profile!=UiLoadMenuCatalog::Profile::OwnedCurrentExactBundleNoAdditionalContent)
            throw std::logic_error("LoadMenu entry requires its sole retained original GameMenu parent and verified catalog");
        const auto before=SdkStateSnapshot::Capture(host_);
        suspendedGameMenu_=std::move(popup_);gameMenuOpened_=opened_;
        try{
            const auto folder=directory_+L"\\play-context-"+std::to_wstring(++contextSequence_);
            if(!CreateDirectoryW(folder.c_str(),nullptr))throw std::runtime_error("Cannot allocate original LoadMenu child directory");
            kind_=UiPopupKind::LoadMenu;
            popup_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,kind_,false,true,nullptr,-1,{},std::move(catalog)));
            popup_->OpenLoadMenu();opened_=std::chrono::steady_clock::now();
            if(before!=SdkStateSnapshot::Capture(host_))throw std::runtime_error("LoadMenu entry changed SDK gameplay");
            std::printf("INTERACTIVE_UI_OPENED=%u|load-menu\n",contextSequence_);
        }catch(...){
            if(popup_){popup_->Stop();popup_.reset();}
            popup_=std::move(suspendedGameMenu_);kind_=UiPopupKind::GameMenu;opened_=gameMenuOpened_;
            host_.popupVisible=popup_ && popup_->IsActive();throw;
        }
    }
    std::vector<SaveMenuRequest> TakeSaveMenuRequests(){
        Require();
        if(!popup_ || kind_!=UiPopupKind::SaveMenu || !suspendedGameMenu_)
            throw std::logic_error("SaveMenu handoff requires its retained original parent");
        return popup_->TakeSaveMenuRequests();
    }
    std::vector<LoadMenuRequest> TakeLoadMenuRequests(){
        Require();
        if(!popup_ || kind_!=UiPopupKind::LoadMenu || !suspendedGameMenu_)
            throw std::logic_error("LoadMenu handoff requires its retained original parent");
        return popup_->TakeLoadMenuRequests();
    }
    void FinishSaveMenuForSave(){
        Require();
        if(!popup_ || kind_!=UiPopupKind::GameMenu || !popup_->IsActive() || suspendedGameMenu_ ||
           !pending_.empty() || !host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("Named save must return through its original GameMenu parent before saving");
        CloseCurrent();Update();
        if(HasModal() || popup_ || host_.popupVisible)
            throw std::logic_error("Named save did not settle the original parent modal lifetime");
    }
    void FinishLoadMenuForLoad(){
        Require();
        if(!popup_ || kind_!=UiPopupKind::GameMenu || !popup_->IsActive() || suspendedGameMenu_ ||
           !pending_.empty() || !host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("Load handoff must return through its original GameMenu parent first");
        CloseCurrent();Update();
        if(HasModal() || popup_ || host_.popupVisible)
            throw std::logic_error("Load handoff did not settle the original parent modal lifetime");
    }
    bool ShowGameMenuUnavailable(const std::string& action,const std::string& message){
        Require();if(!popup_ || kind_!=UiPopupKind::GameMenu || !popup_->IsActive())return false;
        popup_->ShowGameMenuUnavailable(action,message);return true;
    }
    void OpenCity(int id){
        Require();if(HasModal() || popup_ || !host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("Owned city entry requires an idle UI router");
        std::unique_ptr<ICvGame1> game(core_->GetGame());
        const auto owner=game->GetActivePlayer();
        std::unique_ptr<ICvCity1> city(host_.resolveCity(owner,id));
        if(!city || city->GetOwner()!=owner || city->GetID()!=id)
            throw std::invalid_argument("Owned city entry lost its exact SDK city");
        UserInterface frontend(owner_);frontend.SetCityScreenViewingMode(false);
        frontend.selectCity(city.get(),false);frontend.setCityScreenUp(true);city.reset();game.reset();
        const auto folder=directory_+L"\\play-context-"+std::to_wstring(++contextSequence_);
        if(!CreateDirectoryW(folder.c_str(),nullptr))throw std::runtime_error("Cannot allocate owned CityView context directory");
        kind_=UiPopupKind::CityView;popup_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,kind_,false,true));
        popup_->SubmitCityView(owner,id,false);opened_=std::chrono::steady_clock::now();
        std::printf("INTERACTIVE_UI_OPENED=%u|city-view\n",contextSequence_);
        std::printf("INTERACTIVE_OWNED_CITY_OPENED=%d|%d\n",static_cast<int>(owner),id);
    }
    bool CaptureDecisionMatches(int city,int liberated=-2) const {
        Require();return (popup_ && popup_->CaptureDecisionMatches(city,liberated)) ||
            (suspendedCapture_ && suspendedCapture_->CaptureDecisionMatches(city,liberated));
    }
    bool HasCaptureDecision() const {
        Require();if(suspendedCapture_ || (popup_ && kind_==UiPopupKind::CityCapture && popup_->IsActive()))return true;
        for(const auto& request:pending_)if(request.popup && request.popup->type==BUTTONPOPUP_CITY_CAPTURED)return true;
        return false;
    }
    std::uint64_t CapturedPuppetKey(){
        Require();if(!popup_)throw std::logic_error("No captured-city popup");return popup_->CapturedPuppetKey();
    }
    std::uint64_t CapturedViewKey(){Require();if(!popup_)throw std::logic_error("No captured-city popup");return popup_->CapturedViewKey();}
    std::uint64_t CityViewExitKey(){Require();if(!popup_)throw std::logic_error("No CityView");return popup_->CityViewExitKey();}
    std::uint64_t LeaderBackKey(){
        Require();if(!popup_ || kind_!=UiPopupKind::LeaderHead || !popup_->IsActive())
            throw std::logic_error("No active leader-head context");return popup_->LeaderBackKey();
    }
    bool HasLeaderDecision() const {
        Require();return host_.pendingLeaderMessages!=0 ||
            (popup_ && kind_==UiPopupKind::LeaderHead && popup_->HasLeaderDecision());
    }
    void Queue(const CvPopupInfo& input){Queue(OwnedPopupInfo(input));}
    void Queue(const OwnedPopupInfo& input){
        Require();Kind(input.type);
        if(pending_.size()>=64)throw std::length_error("Interactive popup queue exceeds 64 requests");
        pending_.emplace_back(input);
        std::printf("INTERACTIVE_UI_QUEUED=%d|%d|%d|%d\n",static_cast<int>(input.type),input.Data(0),input.Data(1),input.Data(2));
        if(input.type==BUTTONPOPUP_CITY_CAPTURED)
            std::printf("INTERACTIVE_CITY_CAPTURE_POPUP=%d|%d|%d|%d|%d|%u|%u\n",input.Data(0),input.Data(1),input.Data(2),input.Data(3),input.Data(4),input.Option(0)?1u:0u,input.Option(1)?1u:0u);
    }
    void QueueLeader(const OwnedLeaderMessage& input){
        Require();if(!core_)throw std::logic_error("Diplomatic message requires a live game context");
        std::unique_ptr<ICvGame1> game(core_->GetGame());
        if(!game)throw std::runtime_error("Diplomatic message has no SDK game interface");
        const PlayerTypes receiver=game->GetActivePlayer();
        if(receiver<0 || receiver>=MAX_PLAYERS)
            throw std::runtime_error("Diplomatic message has no valid active human receiver");
        std::unique_ptr<ICvPlayer1> player(game->GetPlayer(receiver));
        if(!player || player->GetID()!=receiver || !player->IsAlive() || !player->IsHuman())
            throw std::runtime_error("Diplomatic message receiver is not the active living human player");
        if(pending_.size()>=64 || host_.pendingLeaderMessages==UINT_MAX)
            throw std::length_error("Interactive diplomacy queue exceeds its bounded capacity");
        OwnedLeaderMessage owned(input.player,input.state,input.text.c_str(),input.animation,input.data1,receiver);
        pending_.emplace_back(owned);
        ++host_.pendingLeaderMessages;
        std::printf("INTERACTIVE_DIPLOMACY_QUEUED=%d|%d|%d|%d|%d|%zu\n",receiver,static_cast<int>(owned.player),
            static_cast<int>(owned.state),static_cast<int>(owned.animation),owned.data1,owned.text.size());
    }
    void QueueWarStateChanged(const OwnedWarStateChanged& input){
        Require();if(stopping_ || !popup_ || kind_!=UiPopupKind::LeaderHead || !popup_->IsActive() ||
            !popup_->HasLeaderDecision() || !host_.leaderRootUp)return;
        if(leaderWarStates_.size()>=64)throw std::length_error("Active LeaderHead war-state queue exceeds 64 events");
        leaderWarStates_.emplace_back(contextSequence_,input);
    }
    bool Update(){
        Require();bool changed=false;
        if(popup_ && (kind_==UiPopupKind::MenuOptions || kind_==UiPopupKind::TouchHelp || kind_==UiPopupKind::MapMenu) && !popup_->IsActive()){
            if(!suspendedGameMenu_ || (kind_==UiPopupKind::MapMenu && popup_->HasPendingMapMenuRequests()))
                throw std::logic_error("Private menu return requires completed handoff and its retained parent");
            const auto before=SdkStateSnapshot::Capture(host_);
            popup_->Stop();popup_.reset();
            if(suspendedSaveMenu_){popup_=std::move(suspendedSaveMenu_);kind_=UiPopupKind::SaveMenu;opened_=mapParentOpened_;}
            else{popup_=std::move(suspendedGameMenu_);kind_=UiPopupKind::GameMenu;opened_=gameMenuOpened_;}
            host_.popupVisible=popup_->IsActive();
            if(!host_.popupVisible || before!=SdkStateSnapshot::Capture(host_))throw std::runtime_error("Private menu return lost its parent or changed SDK gameplay");
            changed=true;
        }
        if(popup_ && kind_==UiPopupKind::ExitConfirm && !popup_->IsActive()){
            if(!suspendedGameMenu_ || popup_->HasPendingGameMenuRequests())
                throw std::logic_error("ExitConfirm return requires completed request handoff and its retained parent");
            const auto before=SdkStateSnapshot::Capture(host_);
            popup_->Stop();popup_.reset();popup_=std::move(suspendedGameMenu_);
            kind_=UiPopupKind::GameMenu;opened_=gameMenuOpened_;host_.popupVisible=popup_->IsActive();
            if(!host_.popupVisible || before!=SdkStateSnapshot::Capture(host_))
                throw std::runtime_error("ExitConfirm return lost its parent or changed gameplay");
            changed=true;std::puts("INTERACTIVE_EXIT_CONFIRM_PARENT_RETURNED=STATE_UNCHANGED");
        }
        if(popup_ && kind_==UiPopupKind::LoadMenu && !popup_->IsActive()){
            if(!suspendedGameMenu_ || popup_->HasPendingLoadMenuRequests())
                throw std::logic_error("LoadMenu return requires completed request handoff and its retained parent");
            const auto before=SdkStateSnapshot::Capture(host_);
            popup_->Stop();popup_.reset();popup_=std::move(suspendedGameMenu_);
            kind_=UiPopupKind::GameMenu;opened_=gameMenuOpened_;host_.popupVisible=popup_->IsActive();
            if(!host_.popupVisible || before!=SdkStateSnapshot::Capture(host_))
                throw std::runtime_error("LoadMenu return lost its parent or changed gameplay");
            changed=true;std::puts("INTERACTIVE_LOAD_MENU_PARENT_RETURNED=STATE_UNCHANGED");
        }
        if(popup_ && kind_==UiPopupKind::SaveMenu && !popup_->IsActive()){
            if(!suspendedGameMenu_ || popup_->HasPendingSaveMenuRequests())
                throw std::logic_error("SaveMenu return requires completed request handoff and its retained parent");
            const auto before=SdkStateSnapshot::Capture(host_);
            popup_->Stop();popup_.reset();popup_=std::move(suspendedGameMenu_);
            kind_=UiPopupKind::GameMenu;opened_=gameMenuOpened_;host_.popupVisible=popup_->IsActive();
            if(!host_.popupVisible || before!=SdkStateSnapshot::Capture(host_))
                throw std::runtime_error("SaveMenu return lost its parent or changed gameplay");
            changed=true;std::puts("INTERACTIVE_SAVE_MENU_PARENT_RETURNED=STATE_UNCHANGED");
        }
        if(HasEconomicContext() && !EconomicScopeMatches()){
            StopEconomicContexts();changed=true;
            std::puts("INTERACTIVE_ECONOMIC_SCOPE_CLOSED=ACTIVE_PLAYER_OR_TURN_CHANGED");
        }
        if(popup_ && kind_==UiPopupKind::CityCapture && popup_->IsActive()){
            int owner=-1,city=-1;
            if(popup_->TakeCityViewRequest(owner,city)){
                if(suspendedCapture_)throw std::logic_error("CityView cannot cover another CityView");
                suspendedCapture_=std::move(popup_);captureOpened_=opened_;
                const auto folder=directory_+L"\\play-context-"+std::to_wstring(++contextSequence_);
                if(!CreateDirectoryW(folder.c_str(),nullptr))throw std::runtime_error("Cannot allocate original CityView context directory");
                kind_=UiPopupKind::CityView;
                popup_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,kind_,false,true));
                popup_->SubmitCityView(owner,city);opened_=std::chrono::steady_clock::now();changed=true;
                std::printf("INTERACTIVE_UI_OPENED=%u|city-view\n",contextSequence_);
            }
        }
        if(popup_ && kind_==UiPopupKind::CityView && !popup_->IsActive()){
            if(suspendedCapture_){
                popup_->Stop();popup_.reset();popup_=std::move(suspendedCapture_);
                kind_=UiPopupKind::CityCapture;opened_=captureOpened_;popup_->ReturnFromCityView();changed=true;
            }
        }
        if(popup_ && kind_==UiPopupKind::CityView && popup_->IsActive()){
            CvPopupInfo production;
            if(popup_->TakeCityProductionRequest(production)){
                if(suspendedCity_ || suspendedCapture_ || suspendedEconomic_)throw std::logic_error("City production cannot cover another retained parent");
                suspendedCity_=std::move(popup_);cityOpened_=opened_;
                PrepareProductionContext();
                popup_->Submit(production);changed=true;
                std::printf("INTERACTIVE_UI_OPENED=%u|production\n",contextSequence_);
            }
        }
        if(popup_ && kind_==UiPopupKind::Production && !popup_->IsActive() && suspendedCity_){
            RetainOrStopCurrentPopup();popup_=std::move(suspendedCity_);
            kind_=UiPopupKind::CityView;opened_=cityOpened_;popup_->ReturnFromCityProduction();changed=true;
        }
        if(popup_ && kind_==UiPopupKind::EconomicOverview && popup_->IsActive()){
            try{
                int city=-1;
                if(popup_->TakeEconomicProductionRequest(city)){
                    if(city<0 || suspendedEconomic_ || suspendedCity_ || suspendedCapture_)
                        throw std::logic_error("Economic production requires its sole retained overview parent");
                    suspendedEconomic_=std::move(popup_);economicOpened_=opened_;
                    PrepareProductionContext();
                    popup_->Submit(CvPopupInfo(BUTTONPOPUP_CHOOSEPRODUCTION,city,-1,-1,0,false,false));
                    changed=true;
                    std::printf("INTERACTIVE_UI_OPENED=%u|production\nINTERACTIVE_ECONOMIC_PRODUCTION_OPENED=%d|%d|%d\n",
                        contextSequence_,static_cast<int>(economicOwner_),city,economicTurn_);
                }
            }catch(...){StopEconomicContexts();throw;}
        }
        if(popup_ && kind_==UiPopupKind::Production && !popup_->IsActive() && suspendedEconomic_){
            try{
                RetainOrStopCurrentPopup();popup_=std::move(suspendedEconomic_);
                kind_=UiPopupKind::EconomicOverview;opened_=economicOpened_;
                popup_->RefreshEconomicOverview();changed=true;
                std::printf("INTERACTIVE_ECONOMIC_PRODUCTION_RETURNED=%d|%d\n",static_cast<int>(economicOwner_),economicTurn_);
            }catch(...){StopEconomicContexts();throw;}
        }
        if(popup_ && kind_==UiPopupKind::LeaderHead && popup_->IsActive() &&
           !leaderWarStates_.empty() && host_.scripts && host_.scripts->IsQuiescent()){
            while(!leaderWarStates_.empty()){
                PendingWarState notification=std::move(leaderWarStates_.front());leaderWarStates_.pop_front();
                if(notification.contextSequence!=contextSequence_)continue;
                if(!popup_ || kind_!=UiPopupKind::LeaderHead || !popup_->IsActive() || !popup_->HasLeaderDecision()){
                    leaderWarStates_.clear();break;
                }
                popup_->WarStateChanged(notification.change);changed=true;
            }
        }
        if(closePending_ && !HasCaptureDecision() && !HasLeaderDecision()){closePending_=false;CloseCurrent();changed=true;}
        if(popup_ && !popup_->IsActive()){
            CvPopupInfo deferred;
            const bool hasDeferred=popup_->TakeDeferredPopup(&deferred);
            if(kind_==UiPopupKind::LeaderHead){
                leaderWarStates_.clear();
                if(!host_.pendingLeaderMessages)throw std::logic_error("Leader-head context closed without a pending message");
                --host_.pendingLeaderMessages;host_.leaderRootUp=false;
            }
            RetainOrStopCurrentPopup();changed=true;
            if(kind_==UiPopupKind::EconomicOverview){economicOwner_=NO_PLAYER;economicTurn_=-1;}
            if(hasDeferred)pending_.emplace_front(OwnedPopupInfo(deferred));
        }
        if(!popup_ && !pending_.empty()){
            PendingEntry request=std::move(pending_.front());pending_.pop_front();
            kind_=request.leader?UiPopupKind::LeaderHead:Kind(request.popup->type);
            if(kind_==UiPopupKind::Production)PrepareProductionContext();
            else{
                const auto folder=directory_+L"\\play-context-"+std::to_wstring(++contextSequence_);
                if(!CreateDirectoryW(folder.c_str(),nullptr))
                    throw std::runtime_error("Cannot allocate an immutable interactive UI context directory");
                popup_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,kind_,false,true));
            }
            if(kind_==UiPopupKind::EconomicOverview){
                try{
                    std::unique_ptr<ICvGame1> game(core_->GetGame());
                    if(!game)throw std::logic_error("Economic overview requires its current SDK game");
                    economicOwner_=game->GetActivePlayer();economicTurn_=game->GetGameTurn();
                    popup_->Submit(*request.popup);
                }catch(...){StopEconomicContexts();throw;}
            }else if(request.leader)popup_->SubmitLeader(*request.leader);
            else popup_->Submit(*request.popup);
            if(kind_!=UiPopupKind::Production)opened_=std::chrono::steady_clock::now();
            changed=true;
            std::printf("INTERACTIVE_UI_OPENED=%u|%s\n",contextSequence_,Name(kind_));
        }
        return changed;
    }
    bool Dispatch(const ZeroSisPresentation::BitmapInputEvent& input){
        Require();if(!popup_ || !popup_->IsActive())return false;
        if(HasEconomicContext()){
            if(!EconomicScopeMatches()){StopEconomicContexts();return true;}
            try{return popup_->DispatchExternalWindowInput(input);}
            catch(...){StopEconomicContexts();throw;}
        }
        return popup_->DispatchExternalWindowInput(input);
    }
    void CloseCurrent(){
        Require();if(!popup_ || !popup_->IsActive())return;
        const bool economic=HasEconomicContext();
        if(economic && !EconomicScopeMatches()){StopEconomicContexts();return;}
        try{
            popup_->DispatchInput(UiInputKind::PointerMove,0);
            popup_->CloseInformationalPopup();
        }catch(...){if(economic)StopEconomicContexts();throw;}
    }
    void CloseAll(){
        Require();if(HasCaptureDecision() || HasLeaderDecision())
            throw std::logic_error("Mandatory city or diplomacy decision requires completion before closing UI");
        pending_.clear();leaderWarStates_.clear();closePending_=false;
        for(unsigned depth=0;popup_ && depth<3;++depth){
            CloseCurrent();
            if(popup_ && kind_==UiPopupKind::ExitConfirm){
                const auto requests=popup_->TakeGameMenuRequests();
                if(!requests.empty())
                    throw std::logic_error("Window close cannot discard a pending confirmed exit request");
            }
            if(popup_ && kind_==UiPopupKind::LoadMenu){
                const auto requests=popup_->TakeLoadMenuRequests();
                if(requests.size()!=1 || requests[0].kind!=LoadMenuRequest::Kind::Close || !requests[0].fileName.empty())
                    throw std::logic_error("Window close cannot discard a pending LoadMenu load request");
            }
            Update();
        }
        if(popup_ || suspendedCity_ || suspendedEconomic_ || suspendedGameMenu_)throw std::logic_error("Interactive close did not release its retained parent context");
        if(host_.popupVisible)throw std::logic_error("Interactive UI close left a visible popup");
        DiscardIdleProduction();
    }
    std::uint64_t TextInputOwner(){
        Require();
        if(!popup_ || (kind_!=UiPopupKind::SaveMenu && kind_!=UiPopupKind::MapMenu) || !popup_->IsActive())return textInputOwner_=0;
        const auto focus=popup_->SaveMenuTextInputFocusToken();
        if(!focus)return textInputOwner_=0;
        std::unique_ptr<ICvGame1> game(core_->GetGame());
        if(!game)throw std::logic_error("SaveMenu text owner lost its SDK game");
        const auto player=game->GetActivePlayer();const int turn=game->GetGameTurn();
        if(!textInputOwner_ || textInputContext_!=contextSequence_ || textInputFocus_!=focus ||
           textInputPlayer_!=player || textInputTurn_!=turn){
            if(textInputSerial_==((std::numeric_limits<std::uint64_t>::max)()))
                throw std::overflow_error("SaveMenu text ownership lifetime is exhausted");
            textInputOwner_=++textInputSerial_;textInputContext_=contextSequence_;
            textInputFocus_=focus;textInputPlayer_=player;textInputTurn_=turn;
        }
        return textInputOwner_;
    }
    Frame Capture(){
        Require();if(!popup_ || !popup_->IsActive())throw std::logic_error("No active interactive popup to capture");
        const auto before=SdkStateSnapshot::Capture(host_);
        const double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-opened_).count();
        Frame result{Name(kind_),popup_->CaptureFrame(seconds),{},popup_->InputTargets(),popup_->ScrollTargets()};
        result.textInputOwner=TextInputOwner();result.textInputEnabled=result.textInputOwner!=0;
        if(suspendedCity_){
            const double citySeconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-cityOpened_).count();
            result.cityBackdrop=suspendedCity_->CaptureFrame(citySeconds);
        }
        if(suspendedEconomic_){
            if(suspendedCity_ || kind_!=UiPopupKind::Production || !EconomicScopeMatches())
                throw std::logic_error("Economic backdrop lost its sole live production child");
            const double economicSeconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-economicOpened_).count();
            result.economicBackdrop=suspendedEconomic_->CaptureFrame(economicSeconds);
        }
        if(SdkStateSnapshot::Capture(host_)!=before)
            throw std::runtime_error("Interactive UI capture changed gameplay state");
        return result;
    }
    void VerifySnapshot(const std::string& expected,const std::string& cityBackdrop,const std::string& economicBackdrop={}){
        Require();if(!popup_ || !popup_->IsActive() || popup_->SnapshotForExternalScene()!=expected)
            throw std::runtime_error("Interactive UI state changed while preparing its scene");
        if((!cityBackdrop.empty())!=static_cast<bool>(suspendedCity_) ||
           (suspendedCity_ && suspendedCity_->SnapshotForExternalScene()!=cityBackdrop))
            throw std::runtime_error("Retained CityView backdrop changed while preparing its child scene");
        if((!economicBackdrop.empty())!=static_cast<bool>(suspendedEconomic_) ||
           (suspendedEconomic_ && (!EconomicScopeMatches() || suspendedEconomic_->SnapshotForExternalScene()!=economicBackdrop)))
            throw std::runtime_error("Retained economic backdrop changed while preparing its production scene");
    }
    Frame CaptureUnitPanel(){
        Require();if(HasModal())return {};
        if(!unitPanel_){
            const auto folder=directory_+L"\\play-unit-panel";
            if(!CreateDirectoryW(folder.c_str(),nullptr))throw std::runtime_error("Cannot allocate original UnitPanel context directory");
            unitPanel_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,UiPopupKind::UnitPanel,false,true));
            unitOpened_=std::chrono::steady_clock::now();
        }
        if(!unitPanel_->RefreshUnitPanel())return {};
        const double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-unitOpened_).count();
        return {"unit-panel",unitPanel_->CaptureFrame(seconds),{},unitPanel_->InputTargets(),unitPanel_->ScrollTargets()};
    }
    bool DispatchUnitPanel(const ZeroSisPresentation::BitmapInputEvent& input,bool* frameChanged=nullptr){
        if(frameChanged)*frameChanged=false;
        Require();if(HasModal() || !unitPanel_ || !unitPanel_->IsActive())return false;
        return UiPanelRepaint::Dispatch(input.kind==ZeroSisPresentation::BitmapInputKind::PointerMove,frameChanged,
            [&](){return unitPanel_->DispatchExternalWindowInput(input);},
            [&](){return unitPanel_->SnapshotForExternalScene();});
    }
    void VerifyUnitPanelSnapshot(const std::string& snapshot){
        Require();if(HasModal() || !unitPanel_ || !unitPanel_->IsActive() || unitPanel_->SnapshotForExternalScene()!=snapshot)
            throw std::runtime_error("Original UnitPanel changed while preparing its world overlay");
    }
    Frame CaptureTopPanel(){
        Require();if(HasModal())return {};
        if(!topPanel_){
            const auto folder=directory_+L"\\play-top-panel";
            if(!CreateDirectoryW(folder.c_str(),nullptr))throw std::runtime_error("Cannot allocate original TopPanel context directory");
            topPanel_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,UiPopupKind::TopPanel,false,true));
            topOpened_=std::chrono::steady_clock::now();
        }
        if(!topPanel_->RefreshTopPanel())return {};
        const double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-topOpened_).count();
        return {"top-panel",topPanel_->CaptureFrame(seconds),{},topPanel_->InputTargets(),topPanel_->ScrollTargets()};
    }
    bool DispatchTopPanel(const ZeroSisPresentation::BitmapInputEvent& input,bool* frameChanged=nullptr){
        if(frameChanged)*frameChanged=false;
        Require();if(HasModal() || !topPanel_ || !topPanel_->IsActive())return false;
        return UiPanelRepaint::Dispatch(input.kind==ZeroSisPresentation::BitmapInputKind::PointerMove,frameChanged,
            [&](){return topPanel_->DispatchExternalWindowInput(input);},
            [&](){return topPanel_->SnapshotForExternalScene();});
    }
    void VerifyTopPanelSnapshot(const std::string& snapshot){
        Require();if(HasModal() || !topPanel_ || !topPanel_->IsActive() || topPanel_->SnapshotForExternalScene()!=snapshot)
            throw std::runtime_error("Original TopPanel changed while preparing its world overlay");
    }
    Frame CaptureActionInfoPanel(){
        Require();if(HasModal())return {};
        if(!actionInfoPanel_){
            const auto folder=directory_+L"\\play-action-info-panel";
            if(!CreateDirectoryW(folder.c_str(),nullptr))throw std::runtime_error("Cannot allocate original ActionInfoPanel context directory");
            actionInfoPanel_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,UiPopupKind::ActionInfoPanel,false,true));
            actionInfoOpened_=std::chrono::steady_clock::now();
        }
        if(!actionInfoPanel_->RefreshActionInfoPanel())return {};
        const double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-actionInfoOpened_).count();
        return {"action-info-panel",actionInfoPanel_->CaptureFrame(seconds),{},actionInfoPanel_->InputTargets(),actionInfoPanel_->ScrollTargets()};
    }
    bool DispatchActionInfoPanel(const ZeroSisPresentation::BitmapInputEvent& input,bool* frameChanged=nullptr){
        if(frameChanged)*frameChanged=false;
        Require();if(HasModal() || !actionInfoPanel_ || !actionInfoPanel_->IsActive())return false;
        return UiPanelRepaint::Dispatch(input.kind==ZeroSisPresentation::BitmapInputKind::PointerMove,frameChanged,
            [&](){return actionInfoPanel_->DispatchExternalWindowInput(input);},
            [&](){return actionInfoPanel_->SnapshotForExternalScene();});
    }
    std::vector<ActionInfoRequest> TakeActionInfoRequests(){
        Require();if(!actionInfoPanel_)return {};return actionInfoPanel_->TakeActionInfoRequests();
    }
    void VerifyActionInfoPanelSnapshot(const std::string& snapshot){
        Require();if(HasModal() || !actionInfoPanel_ || !actionInfoPanel_->IsActive() ||
            actionInfoPanel_->SnapshotForExternalScene()!=snapshot)
            throw std::runtime_error("Original ActionInfoPanel changed while preparing its world overlay");
    }
    Frame CaptureNotificationPanel(){
        Require();if(HasModal())return {};
        if(!actionInfoPanel_ || !actionInfoPanel_->IsActive())
            throw std::logic_error("Original NotificationPanel requires its visible ActionInfoPanel parent");
        if(!notificationPanel_){
            const auto folder=directory_+L"\\play-notification-panel";
            if(!CreateDirectoryW(folder.c_str(),nullptr))throw std::runtime_error("Cannot allocate original NotificationPanel context directory");
            notificationPanel_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,UiPopupKind::NotificationPanel,false,true));
            notificationOpened_=std::chrono::steady_clock::now();
        }
        if(!notificationPanel_->RefreshNotificationPanel())return {};
        const double seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-notificationOpened_).count();
        return {"notification-panel",notificationPanel_->CaptureFrame(seconds),{},notificationPanel_->InputTargets(),notificationPanel_->ScrollTargets()};
    }
    bool DispatchNotificationPanel(const ZeroSisPresentation::BitmapInputEvent& input,bool* frameChanged=nullptr){
        if(frameChanged)*frameChanged=false;
        Require();if(HasModal() || !notificationPanel_ || !notificationPanel_->IsActive())return false;
        return UiPanelRepaint::Dispatch(input.kind==ZeroSisPresentation::BitmapInputKind::PointerMove,frameChanged,
            [&](){return notificationPanel_->DispatchExternalWindowInput(input);},
            [&](){return notificationPanel_->SnapshotForExternalScene();});
    }
    std::vector<ActionInfoRequest> TakeNotificationRequests(){
        Require();if(!notificationPanel_)return {};return notificationPanel_->TakeActionInfoRequests();
    }
    void VerifyNotificationPanelSnapshot(const std::string& snapshot){
        Require();if(HasModal() || !notificationPanel_ || !notificationPanel_->IsActive() ||
            notificationPanel_->SnapshotForExternalScene()!=snapshot)
            throw std::runtime_error("Original NotificationPanel changed while preparing its world overlay");
    }
    ActionInfoObservation ObserveActionInfoPanel(){
        Require();
        if(HasModal() || !actionInfoPanel_ || !actionInfoPanel_->IsActive() || !host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("ActionInfoPanel observation requires its idle nonmodal context");
        std::unique_ptr<ICvGame1> game(core_->GetGame());
        if(!game || game->IsGameMultiPlayer() || game->IsNetworkMultiPlayer())
            throw std::logic_error("ActionInfoPanel observation requires the live local singleplayer game");
        ActionInfoObservation result;result.owner=game->GetActivePlayer();result.turn=game->GetGameTurn();
        std::unique_ptr<ICvPlayer1> player(game->GetPlayer(static_cast<PlayerTypes>(result.owner)));
        if(!player || !player->IsAlive() || !player->IsHuman())throw std::logic_error("ActionInfoPanel owner is not the live human player");
        // These blocker queries are LuaPlayer bindings, not ICvPlayer1
        // interface methods; InteractiveGameSession fills them via its live VM.
        {std::lock_guard<std::mutex> guard(host_.dataMutex);result.canEndTurn=host_.canEndTurn;
            for(const auto& item:host_.notifications)if(item.second.player==result.owner)result.notifications.push_back(item.second);}
        return result;
    }
    UiPopupKind ActiveKind() const {Require();if(!popup_)throw std::logic_error("No active popup kind");return kind_;}
    int TechAwardTechnology() const {Require();if(!popup_)throw std::logic_error("No active technology award context");return popup_->TechAwardTechnology();}
    std::vector<UiInputTarget> Targets(){Require();return popup_?popup_->InputTargets():std::vector<UiInputTarget>{};}
    int SelectedPolicyTenet(){Require();if(!popup_ || kind_!=UiPopupKind::SocialPolicy)
        throw std::logic_error("Selected tenet has no original active policy popup");return popup_->SelectedPolicyTenet();}
private:
    void OpenPrivateMenu(UiPopupKind child,std::shared_ptr<const UiMapMenuCatalog> catalog){
        Require();
        const bool fromSave=kind_==UiPopupKind::SaveMenu && child==UiPopupKind::MapMenu;
        if(stopping_ || !popup_ || !popup_->IsActive() ||
           (!fromSave && (kind_!=UiPopupKind::GameMenu || suspendedGameMenu_)) ||
           (fromSave && !suspendedGameMenu_) || suspendedSaveMenu_ || suspendedCity_ || suspendedCapture_ || suspendedEconomic_ ||
           !pending_.empty() || !host_.scripts || !host_.scripts->IsQuiescent() ||
           (child==UiPopupKind::MapMenu)!=!!catalog)
            throw std::logic_error("Private menu child requires its sole original settled parent");
        const auto before=SdkStateSnapshot::Capture(host_);
        if(fromSave){suspendedSaveMenu_=std::move(popup_);mapParentOpened_=opened_;}
        else{suspendedGameMenu_=std::move(popup_);gameMenuOpened_=opened_;}
        try{
            const auto folder=directory_+L"\\play-menu-"+std::to_wstring(++contextSequence_);
            if(!CreateDirectoryW(folder.c_str(),nullptr))throw std::runtime_error("Cannot allocate private original menu context");
            kind_=child;
            popup_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,kind_,false,true,nullptr,-1,{},{},std::move(catalog)));
            popup_->OpenPrivateMenu();opened_=std::chrono::steady_clock::now();
            if(before!=SdkStateSnapshot::Capture(host_))throw std::runtime_error("Private menu entry changed SDK gameplay");
        }catch(...){
            if(popup_){popup_->Stop();popup_.reset();}
            if(fromSave){popup_=std::move(suspendedSaveMenu_);kind_=UiPopupKind::SaveMenu;opened_=mapParentOpened_;}
            else{popup_=std::move(suspendedGameMenu_);kind_=UiPopupKind::GameMenu;opened_=gameMenuOpened_;}
            host_.popupVisible=popup_ && popup_->IsActive();throw;
        }
    }
    std::unique_ptr<UiPopupContext> suspendedSaveMenu_;
    std::chrono::steady_clock::time_point mapParentOpened_;
    static HostState& CheckedHost(const std::shared_ptr<HostState>& host){
        if(!host)throw std::invalid_argument("Interactive UI owner is missing");return *host;
    }
    static const char* Name(UiPopupKind kind){
        switch(kind){case UiPopupKind::Production:return "production";case UiPopupKind::Research:return "research";
            case UiPopupKind::ResearchTree:return "research-tree";case UiPopupKind::Ranking:return "ranking";
            case UiPopupKind::GoodyHutReward:return "goody-hut-reward";
            case UiPopupKind::TechAward:return "tech-award";case UiPopupKind::DeclareWar:return "declare-war";
            case UiPopupKind::CityCapture:return "city-capture";case UiPopupKind::LeaderHead:return "diplomacy";
            case UiPopupKind::CityView:return "city-view";case UiPopupKind::UnitPanel:return "unit-panel";
            case UiPopupKind::TopPanel:return "top-panel";case UiPopupKind::TradeRoute:return "trade-route";
            case UiPopupKind::GameMenu:return "game-menu";
            case UiPopupKind::ExitConfirm:return "exit-confirm";
            case UiPopupKind::MenuOptions:return "menu-options";
            case UiPopupKind::TouchHelp:return "touch-help";
            case UiPopupKind::MapMenu:return "map-menu";
            case UiPopupKind::SaveMenu:return "save-menu";
            case UiPopupKind::LoadMenu:return "load-menu";
            case UiPopupKind::Pantheon:return "pantheon";
            case UiPopupKind::SocialPolicy:return "social-policy";case UiPopupKind::EconomicOverview:return "economic-overview";
            case UiPopupKind::EconomicGeneral:case UiPopupKind::EconomicHappiness:
                throw std::logic_error("Embedded economic children cannot be routed as independent popups");}
        throw std::logic_error("Unknown interactive UI kind");
    }
    static UiPopupKind Kind(ButtonPopupTypes type){
        // BNW declares this hashed popup ID outside the legacy enum members.
        if(type==BUTTONPOPUP_TRADE_ROUTE_OVERVIEW)return UiPopupKind::TradeRoute;
        switch(type){case BUTTONPOPUP_CHOOSEPRODUCTION:return UiPopupKind::Production;
            case BUTTONPOPUP_CHOOSEPOLICY:return UiPopupKind::SocialPolicy;
            case BUTTONPOPUP_FOUND_PANTHEON:return UiPopupKind::Pantheon;
            case BUTTONPOPUP_ECONOMIC_OVERVIEW:return UiPopupKind::EconomicOverview;
            case BUTTONPOPUP_CHOOSETECH:return UiPopupKind::Research;
            case BUTTONPOPUP_TECH_TREE:return UiPopupKind::ResearchTree;
            case BUTTONPOPUP_GOODY_HUT_REWARD:return UiPopupKind::GoodyHutReward;
            case BUTTONPOPUP_TECH_AWARD:return UiPopupKind::TechAward;
            case BUTTONPOPUP_WHOS_WINNING:return UiPopupKind::Ranking;
            case BUTTONPOPUP_CITY_CAPTURED:return UiPopupKind::CityCapture;
            case BUTTONPOPUP_DECLAREWARMOVE:case BUTTONPOPUP_DECLAREWARRANGESTRIKE:return UiPopupKind::DeclareWar;
            default:Unsupported("Interactive popup type has no original retained context");}
    }
    void Require() const {
        if(host_.gameThread!=GetCurrentThreadId() || !host_.gameLock.HeldByCurrentThread())
            throw std::logic_error("Interactive UI router requires the GameCore owner lock");
    }
    bool HasEconomicContext() const {
        return suspendedEconomic_ || (popup_ && kind_==UiPopupKind::EconomicOverview);
    }
    bool EconomicScopeMatches() const {
        if(!core_ || economicOwner_<0 || economicOwner_>=MAX_PLAYERS || economicTurn_<0)
            throw std::logic_error("Retained economic overview has no owner/turn identity");
        std::unique_ptr<ICvGame1> game(core_->GetGame());
        return game && game->GetActivePlayer()==economicOwner_ && game->GetGameTurn()==economicTurn_;
    }
    void DiscardIdleProduction(){
        if(idleProduction_){idleProduction_->Stop();idleProduction_.reset();}
    }
    void PrepareProductionContext(){
        if(!core_)throw std::logic_error("Production reuse requires the current SDK session");
        std::unique_ptr<ICvGame1> game(core_->GetGame());
        if(!game)throw std::runtime_error("Production popup requires the current SDK game");
        const auto activePlayer=game->GetActivePlayer();
        const auto openSequence=++contextSequence_;
        if(idleProduction_ && !idleProduction_->CanReuseProductionFor(*core_,activePlayer))
            DiscardIdleProduction();
        if(idleProduction_){
            popup_=std::move(idleProduction_);
            // The retained VM keeps its original presentation clock epoch.
            opened_=idleProductionOpened_;
            std::printf("INTERACTIVE_PRODUCTION_CONTEXT_REUSED=%u|%d\n",openSequence,static_cast<int>(activePlayer));
        }
        else{
            const auto folder=directory_+L"\\play-context-"+std::to_wstring(openSequence);
            if(!CreateDirectoryW(folder.c_str(),nullptr))
                throw std::runtime_error("Cannot allocate an immutable interactive UI context directory");
            popup_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,UiPopupKind::Production,false,true));
            opened_=std::chrono::steady_clock::now();
        }
        kind_=UiPopupKind::Production;
    }
    void RetainOrStopCurrentPopup(){
        if(!popup_)return;
        bool retain=false;
        if(kind_==UiPopupKind::Production && core_ && !host_.popupVisible){
            std::unique_ptr<ICvGame1> game(core_->GetGame());
            retain=game && popup_->CanReuseProductionFor(*core_,game->GetActivePlayer());
        }
        if(retain){
            DiscardIdleProduction();
            idleProductionOpened_=opened_;
            idleProduction_=std::move(popup_);
        }else{popup_->Stop();popup_.reset();}
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
    struct PendingEntry final {
        std::unique_ptr<OwnedPopupInfo> popup;
        std::unique_ptr<OwnedLeaderMessage> leader;
        explicit PendingEntry(const OwnedPopupInfo& value):popup(new OwnedPopupInfo(value)){}
        explicit PendingEntry(const OwnedLeaderMessage& value):leader(new OwnedLeaderMessage(value)){}
    };
    struct PendingWarState final {
        unsigned contextSequence;
        OwnedWarStateChanged change;
        PendingWarState(unsigned sequence,const OwnedWarStateChanged& value):contextSequence(sequence),change(value){}
    };
    std::shared_ptr<HostState> owner_;HostState& host_;ICvGameContext3* core_;
    std::wstring directory_;std::unique_ptr<UiPopupContext> popup_,idleProduction_,suspendedCapture_,suspendedCity_,suspendedEconomic_,suspendedGameMenu_,unitPanel_,topPanel_,actionInfoPanel_,notificationPanel_;std::deque<PendingEntry> pending_;
    std::deque<PendingWarState> leaderWarStates_;
    UiPopupKind kind_=UiPopupKind::Ranking;unsigned contextSequence_=0;bool closePending_=false,stopping_=false;
    std::uint64_t textInputSerial_=0,textInputOwner_=0,textInputFocus_=0;
    unsigned textInputContext_=0;PlayerTypes textInputPlayer_=NO_PLAYER;int textInputTurn_=-1;
    PlayerTypes economicOwner_=NO_PLAYER;int economicTurn_=-1;
    std::chrono::steady_clock::time_point opened_,idleProductionOpened_,captureOpened_,cityOpened_,economicOpened_,gameMenuOpened_,unitOpened_,topOpened_,actionInfoOpened_,notificationOpened_;
};
}
