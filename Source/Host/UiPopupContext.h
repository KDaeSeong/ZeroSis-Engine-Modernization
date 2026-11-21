#pragma once
#include "HostServices.h"
#include "UiPopupAssets.generated.h"
#include "UiAudioPlayback.h"
#include "SdkStateSnapshot.h"
#include "UiSnapshotJson.h"
#include "UiLocaleArguments.h"
#include <CvLocalization.h>
#include <array>
#include <cstdlib>
#include "UiInputDispatch.h"
#include "UiSaveMenuContract.h"
#include "UiLoadMenuContract.h"
#include "UiMapMenuContract.h"
#include "MenuOptionsStore.h"
#include "MenuOptionsHostBinding.h"
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
#include "UiWindowPresentation.h"
#include "../Presentation/BitmapSliderInput.h"
#endif

namespace ZeroSisHost {
enum class UiPopupKind { Ranking,Production,Research,ResearchTree,CityCapture,LeaderHead,CityView,TechAward,UnitPanel,DeclareWar,TopPanel,TradeRoute,SocialPolicy,EconomicOverview,EconomicGeneral,EconomicHappiness,ActionInfoPanel,NotificationPanel,GameMenu,SaveMenu,LoadMenu,Pantheon,GoodyHutReward,ExitConfirm,MenuOptions,TouchHelp,MapMenu };
struct GameMenuRequest final {
    enum class Kind { Open,QuickSave,Unavailable,OpenSaveMenu,OpenLoadMenu,OpenExitConfirm,ExitGame,OpenMenuOptions,OpenTouchHelp,OpenMapMenu,MainMenu,Restart,Retire };
    Kind kind;int owner,turn;std::string action;
};
// One persistent official UI-script VM per explicitly enabled host session.
// The control tree is retained for presentation; this is not a pixel renderer.
class UiPopupContext final {
public:
    UiPopupContext(std::shared_ptr<HostState> host,ICvGameContext3& core,std::wstring directory,bool windowPresentation=false,bool displayResize=false,bool refreshClosed=false,UiPopupKind kind=UiPopupKind::Ranking,bool liveProduction=false,bool externalRouting=false,UiPopupContext* economicOwner=nullptr,int economicSlot=-1,std::shared_ptr<const UiSaveMenuCatalog> saveMenuCatalog={},std::shared_ptr<const UiLoadMenuCatalog> loadMenuCatalog={},std::shared_ptr<const UiMapMenuCatalog> mapMenuCatalog={})
        :hostOwner_(std::move(host)),host_(CheckedHost(hostOwner_)),scripts_(CheckedScripts(host_)),frontend_(hostOwner_),core_(&core),directory_(std::move(directory)),kind_(kind),saveMenuCatalog_(std::move(saveMenuCatalog)),loadMenuCatalog_(std::move(loadMenuCatalog)),economicOwner_(economicOwner),economicSlot_(economicSlot),windowPresentation_(windowPresentation),displayResize_(displayResize),refreshClosed_(refreshClosed),liveProduction_(liveProduction),externalRouting_(externalRouting),mapMenuCatalog_(std::move(mapMenuCatalog)) {
        Require();
        const bool economicParent=kind_==UiPopupKind::EconomicOverview && !economicOwner_;
        const bool economicChild=kind_==UiPopupKind::EconomicGeneral || kind_==UiPopupKind::EconomicHappiness;
        if((economicParent && economicSlot_!=-1) || (economicChild && (!economicOwner_ || economicSlot_!=(kind_==UiPopupKind::EconomicGeneral?1:2))) ||
           (!economicParent && !economicChild && (economicOwner_ || economicSlot_!=-1)))
            throw std::invalid_argument("Embedded EconomicOverview context ownership is invalid");
        if(economicParent)initializingEconomic_=true;
        if(!host_.uiAudio)host_.uiAudio=std::make_shared<UiAudioPlayback>();
        EnsureMenuOptions();
        if(kind_==UiPopupKind::SocialPolicy && !host_.policyInfoInitialized){
            const char* value=std::getenv("ZEROSIS_UI_POLICY_INFO");
            if(!value || (std::strcmp(value,"0")!=0 && std::strcmp(value,"1")!=0))
                throw std::invalid_argument("SocialPolicy requires an explicit frozen PolicyInfo option");
            host_.policyInfo=value[0]=='1';host_.policyInfoInitialized=true;
        }
        if(IsResearch() || kind_==UiPopupKind::CityView || kind_==UiPopupKind::UnitPanel){
            const char* small=std::getenv("ZEROSIS_UI_SMALL_ASSETS");
            if(!small || (std::strcmp(small,"0")!=0 && std::strcmp(small,"1")!=0))
                throw std::invalid_argument("Original UI requires an explicit frozen SmallUIAssets option");
            smallUiAssets_=small[0]=='1';
            std::printf(kind_==UiPopupKind::UnitPanel?"UNIT_PANEL_UI_SMALL_ASSETS=%u\n":kind_==UiPopupKind::CityView?"CITY_VIEW_UI_SMALL_ASSETS=%u\n":kind_==UiPopupKind::ResearchTree?"RESEARCH_TREE_UI_SMALL_ASSETS=%u\n":"RESEARCH_UI_SMALL_ASSETS=%u\n",smallUiAssets_?1u:0u);
        }
        if((kind_==UiPopupKind::UnitPanel || kind_==UiPopupKind::TopPanel || IsNotificationInputPanel()) && !externalRouting_)
            throw std::logic_error("Original world panels require the world session router");
        if((economicParent || economicChild) && !externalRouting_)
            throw std::logic_error("Original EconomicOverview contexts require the world session router");
        if((kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SaveMenu || kind_==UiPopupKind::LoadMenu || kind_==UiPopupKind::ExitConfirm || IsPrivateMenuChild()) && !externalRouting_)
            throw std::logic_error("Original GameMenu requires the world session router");
        if(externalRouting_ && windowPresentation_)
            throw std::logic_error("Externally routed popup contexts cannot create a standalone UI window");
        if(kind_==UiPopupKind::ResearchTree && windowPresentation_)
            throw std::logic_error("Research tree requires its separate multi-scene window protocol");
        if(liveProduction_ && (kind_!=UiPopupKind::Production || !refreshClosed_))
            throw std::logic_error("Live production requires the owned GPU production context");
        if(displayResize_ && !windowPresentation_)throw std::logic_error("Display/resize requires native UI window presentation");
        if(refreshClosed_ && !displayResize_)throw std::logic_error("Closed-scene refresh requires the GPU display profile");
#if !defined(ZEROSIS_UI_WINDOW_PRESENTATION)
        if(windowPresentation_)throw std::logic_error("This host was built without native UI window presentation");
#endif
        game_.reset(core.GetGame());pregame_.reset(core.GetPreGame());
        if(!game_ || !pregame_ || (externalRouting_ ? (!host_.addPopup || !host_.closeInformationalPopup)
                                                     : (host_.addPopup || host_.closeInformationalPopup)))
            throw std::logic_error("UI popup context requires the expected native popup router ownership");
        if(IsNotificationInputPanel() && (game_->IsGameMultiPlayer() || game_->IsNetworkMultiPlayer()))
            throw std::logic_error("Original ActionInfoPanel currently requires the actual local singleplayer session");
        if(kind_==UiPopupKind::SaveMenu && (!saveMenuCatalog_ || !saveMenuCatalog_->nameAvailable))
            throw std::invalid_argument("SaveMenu requires its immutable current-session catalog");
        if(kind_!=UiPopupKind::SaveMenu && saveMenuCatalog_)
            throw std::invalid_argument("Save catalog cannot be attached to another popup kind");
        if(kind_==UiPopupKind::LoadMenu && (!loadMenuCatalog_ || !loadMenuCatalog_->canLoad ||
           loadMenuCatalog_->profile!=UiLoadMenuCatalog::Profile::OwnedCurrentExactBundleNoAdditionalContent))
            throw std::invalid_argument("LoadMenu requires its immutable exact-bundle catalog and verified content profile");
        if(kind_!=UiPopupKind::LoadMenu && loadMenuCatalog_)
            throw std::invalid_argument("Load catalog cannot be attached to another popup kind");
        if(kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SaveMenu || kind_==UiPopupKind::LoadMenu || kind_==UiPopupKind::ExitConfirm || IsPrivateMenuChild()){
            gameMenuOwner_=game_->GetActivePlayer();gameMenuTurn_=game_->GetGameTurn();
            RequireGameMenuOwner();
        }
        if(kind_==UiPopupKind::LoadMenu)RequireLoadMenuOwner();
        if((kind_==UiPopupKind::MapMenu)!=!!mapMenuCatalog_)throw std::invalid_argument("Map menu catalog/context mismatch");
        try{
            for(const auto& script:UiAssets::scripts)
                scripts_.RegisterFile(script.name,std::string(script.data,script.size));
            if(kind_==UiPopupKind::DeclareWar){
                if(!externalRouting_)throw std::logic_error("DeclareWar requires the original world session router");
                warCommandsVm_=scripts_.CreateLuaThread("BNW original war command commit");
                if(!warCommandsVm_)throw std::runtime_error(scripts_.LastError());
            }
            vm_=scripts_.CreateLuaThread(IsPrivateMenuChild()?"Owned original menu child":kind_==UiPopupKind::GoodyHutReward?"BNW original goody-hut reward UI":kind_==UiPopupKind::Pantheon?"BNW original Pantheon UI":kind_==UiPopupKind::ExitConfirm?"BNW original ExitConfirm child UI":kind_==UiPopupKind::LoadMenu?"BNW LoadMenu child UI":kind_==UiPopupKind::SaveMenu?"BNW SaveMenu child UI":kind_==UiPopupKind::GameMenu?"BNW GameMenu UI":kind_==UiPopupKind::NotificationPanel?"BNW NotificationPanel UI":kind_==UiPopupKind::ActionInfoPanel?"BNW ActionInfoPanel UI":kind_==UiPopupKind::SocialPolicy?"BNW SocialPolicy UI":kind_==UiPopupKind::TradeRoute?"BNW TradeRouteOverview UI":kind_==UiPopupKind::TopPanel?"BNW TopPanel UI":kind_==UiPopupKind::UnitPanel?"BNW UnitPanel UI":kind_==UiPopupKind::CityView?"BNW CityView UI":kind_==UiPopupKind::Ranking?"BNW ranking popup UI":kind_==UiPopupKind::Production?"BNW production popup UI":kind_==UiPopupKind::CityCapture?"BNW captured city popup UI":kind_==UiPopupKind::LeaderHead?"BNW leader message UI":kind_==UiPopupKind::TechAward?"BNW technology award UI":kind_==UiPopupKind::ResearchTree?"BNW research tree UI":kind_==UiPopupKind::EconomicOverview?"BNW EconomicOverview UI":economicChild?"BNW EconomicOverview embedded UI":"BNW research popup UI");
            if(!scripts_.CallCFunction(vm_,&Bind,this) ||
               !scripts_.RegisterFunction(vm_,"ZeroSisUiNative",&Native) ||
               !scripts_.LoadFile(vm_,"SharedFontMetrics") ||
               !scripts_.LoadFile(vm_,kind_==UiPopupKind::MenuOptions?"MenuOptionsLayout":kind_==UiPopupKind::TouchHelp?"TouchHelpLayout":kind_==UiPopupKind::MapMenu?"MapMenuLayout":kind_==UiPopupKind::GoodyHutReward?"GoodyHutRewardLayout":kind_==UiPopupKind::Pantheon?"PantheonLayout":kind_==UiPopupKind::ExitConfirm?"ExitConfirmLayout":kind_==UiPopupKind::LoadMenu?"LoadMenuLayout":kind_==UiPopupKind::SaveMenu?"SaveMenuLayout":kind_==UiPopupKind::GameMenu?"GameMenuLayout":kind_==UiPopupKind::NotificationPanel?"NotificationPanelLayout":kind_==UiPopupKind::ActionInfoPanel?"ActionInfoPanelLayout":kind_==UiPopupKind::EconomicOverview?"EconomicOverviewLayout":kind_==UiPopupKind::EconomicGeneral?"EconomicGeneralLayout":kind_==UiPopupKind::EconomicHappiness?"EconomicHappinessLayout":kind_==UiPopupKind::SocialPolicy?"SocialPolicyLayout":kind_==UiPopupKind::TradeRoute?"TradeRouteLayout":kind_==UiPopupKind::TopPanel?"TopPanelLayout":kind_==UiPopupKind::DeclareWar?"DeclareWarLayout":kind_==UiPopupKind::UnitPanel?(smallUiAssets_?"UnitPanelSmallLayout":"UnitPanelLayout"):kind_==UiPopupKind::CityView?(smallUiAssets_?"CityViewSmallLayout":"CityViewLayout"):kind_==UiPopupKind::Ranking?"WhosWinningLayout":kind_==UiPopupKind::Production?"ProductionLayout":kind_==UiPopupKind::CityCapture?"GenericPopupLayout":kind_==UiPopupKind::LeaderHead?"LeaderHeadRootLayout":kind_==UiPopupKind::TechAward?"TechAwardLayout":kind_==UiPopupKind::ResearchTree?"TechTreeLayout":"TechLayout") ||
               !scripts_.LoadFile(vm_,"ZeroSisUiScene") ||
               (kind_==UiPopupKind::Production && !scripts_.LoadFile(vm_,"ProductionCommandGuard")) ||
               (IsResearch() && !scripts_.LoadFile(vm_,"ResearchCommandGuard")) ||
               (kind_!=UiPopupKind::UnitPanel && kind_!=UiPopupKind::MenuOptions && !scripts_.LoadFile(vm_,kind_==UiPopupKind::TouchHelp?"TouchControlsMenu":kind_==UiPopupKind::MapMenu?"SaveMapMenu":kind_==UiPopupKind::GoodyHutReward?"GoodyHutPopup":kind_==UiPopupKind::Pantheon?"ChoosePantheonPopup":kind_==UiPopupKind::ExitConfirm?"ExitConfirm":kind_==UiPopupKind::LoadMenu?"LoadMenu":kind_==UiPopupKind::SaveMenu?"SaveMenu":kind_==UiPopupKind::GameMenu?"GameMenu":kind_==UiPopupKind::NotificationPanel?"NotificationPanel":kind_==UiPopupKind::ActionInfoPanel?"ActionInfoPanel":kind_==UiPopupKind::EconomicOverview?"EconomicOverview":kind_==UiPopupKind::EconomicGeneral?"EconomicGeneralInfo":kind_==UiPopupKind::EconomicHappiness?"HappinessInfo":kind_==UiPopupKind::SocialPolicy?"SocialPolicyPopup":kind_==UiPopupKind::TradeRoute?"TradeRouteOverview":kind_==UiPopupKind::TopPanel?"TopPanel":kind_==UiPopupKind::DeclareWar?"DeclareWarPopup":kind_==UiPopupKind::CityView?"CityView":kind_==UiPopupKind::Ranking?"WhosWinningPopup":kind_==UiPopupKind::Production?"ProductionPopup":kind_==UiPopupKind::CityCapture?"GenericPopup":kind_==UiPopupKind::LeaderHead?"LeaderHeadRoot":kind_==UiPopupKind::TechAward?"TechAwardPopup":kind_==UiPopupKind::ResearchTree?"TechTree":"TechPopup")))
                throw std::runtime_error(scripts_.LastError());
            if(economicParent){
                economicChildren_[0].reset(new UiPopupContext(hostOwner_,core,directory_,false,false,false,UiPopupKind::EconomicGeneral,false,true,this,1));
                economicChildren_[1].reset(new UiPopupContext(hostOwner_,core,directory_,false,false,false,UiPopupKind::EconomicHappiness,false,true,this,2));
                initializingEconomic_=false;
            }
            if(!externalRouting_){
                host_.addPopup=[this](const CvPopupInfo& input){Submit(input);};
                host_.closeInformationalPopup=[this](){CloseInformationalPopup();};
            }
        }catch(...){
            initializingEconomic_=false;
            for(auto& child:economicChildren_)if(child){try{child->Stop();}catch(...){}child.reset();}
            if(!externalRouting_){host_.addPopup={};host_.closeInformationalPopup={};}
            if(vm_){scripts_.FreeLuaThread(vm_);vm_=nullptr;}
            ReleaseWarResources();
            throw;
        }
        std::puts(IsPrivateMenuChild()?"UI_POPUP_CONTEXT=OWNED_ORIGINAL_MENU_CHILD":kind_==UiPopupKind::GoodyHutReward?"UI_POPUP_CONTEXT=OFFICIAL_BNW_GOODY_HUT_REWARD":kind_==UiPopupKind::Pantheon?"UI_POPUP_CONTEXT=OFFICIAL_BNW_CHOOSE_PANTHEON":kind_==UiPopupKind::ExitConfirm?"UI_POPUP_CONTEXT=OFFICIAL_EXIT_CONFIRM_CHILD":kind_==UiPopupKind::LoadMenu?"UI_POPUP_CONTEXT=OFFICIAL_BNW_LOAD_MENU_CHILD":kind_==UiPopupKind::SaveMenu?"UI_POPUP_CONTEXT=OFFICIAL_BNW_SAVE_MENU_CHILD":kind_==UiPopupKind::GameMenu?"UI_POPUP_CONTEXT=OFFICIAL_BNW_GAME_MENU":kind_==UiPopupKind::NotificationPanel?"UI_POPUP_CONTEXT=OFFICIAL_BNW_NOTIFICATION_PANEL":kind_==UiPopupKind::ActionInfoPanel?"UI_POPUP_CONTEXT=OFFICIAL_BNW_ACTION_INFO_PANEL":kind_==UiPopupKind::SocialPolicy?"UI_POPUP_CONTEXT=OFFICIAL_BNW_SOCIAL_POLICY":kind_==UiPopupKind::TradeRoute?"UI_POPUP_CONTEXT=OFFICIAL_BNW_TRADE_ROUTE_OVERVIEW":kind_==UiPopupKind::TopPanel?"UI_POPUP_CONTEXT=OFFICIAL_BNW_TOP_PANEL":kind_==UiPopupKind::DeclareWar?"UI_POPUP_CONTEXT=OFFICIAL_BNW_DECLARE_WAR":kind_==UiPopupKind::UnitPanel?"UI_POPUP_CONTEXT=OFFICIAL_BNW_UNIT_PANEL":kind_==UiPopupKind::CityView?"UI_POPUP_CONTEXT=OFFICIAL_BNW_CITY_VIEW":kind_==UiPopupKind::Ranking?"UI_POPUP_CONTEXT=OFFICIAL_BNW_WHOS_WINNING_PERSISTENT_VM_RETAINED_CONTROLS":
                  kind_==UiPopupKind::Production?"UI_POPUP_CONTEXT=OFFICIAL_BNW_PRODUCTION_PERSISTENT_VM_RETAINED_CONTROLS":
                  kind_==UiPopupKind::CityCapture?"UI_POPUP_CONTEXT=OFFICIAL_BNW_CITY_CAPTURE_GENERIC_POPUP":
                  kind_==UiPopupKind::LeaderHead?"UI_POPUP_CONTEXT=OFFICIAL_BNW_LEADER_HEAD_ROOT":
                  kind_==UiPopupKind::TechAward?"UI_POPUP_CONTEXT=OFFICIAL_BNW_TECH_AWARD":
                  kind_==UiPopupKind::ResearchTree?"UI_POPUP_CONTEXT=OFFICIAL_BNW_RESEARCH_TREE_PERSISTENT_VM_RETAINED_CONTROLS":
                  kind_==UiPopupKind::EconomicOverview?"UI_POPUP_CONTEXT=OFFICIAL_BNW_ECONOMIC_OVERVIEW_WITH_RETAINED_CHILD_VMS":
                  kind_==UiPopupKind::EconomicGeneral?"UI_POPUP_CONTEXT=OFFICIAL_BNW_ECONOMIC_GENERAL_CHILD_VM":
                  kind_==UiPopupKind::EconomicHappiness?"UI_POPUP_CONTEXT=OFFICIAL_BNW_ECONOMIC_HAPPINESS_CHILD_VM":
                  "UI_POPUP_CONTEXT=OFFICIAL_BNW_RESEARCH_PERSISTENT_VM_RETAINED_CONTROLS");
    }
    ~UiPopupContext(){if(vm_)std::terminate();}
    UiPopupContext(const UiPopupContext&)=delete;
    UiPopupContext& operator=(const UiPopupContext&)=delete;
    void OpenGameMenu(){
        Require();RequireGameMenuOwner();
        if(!vm_ || active_ || dispatching_ || faulted_ || !scripts_.IsQuiescent() ||
           timerState_!=TimerState::Released || gameMenuInput_ || gameMenuReady_ || !gameMenuRequests_.empty())
            throw std::logic_error("GameMenu entry requires its idle owned context");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        Call(&OpenGameMenuLua,nullptr);
        bool shown=false;Call(&ObserveActive,&shown);
        if(!shown || timerState_!=TimerState::Held || before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("Original GameMenu entry changed gameplay or failed its modal timer contract");
        active_=true;host_.popupVisible=true;++sequence_;shownSnapshot_=WriteSnapshot("shown");
        std::printf("INTERACTIVE_GAME_MENU_SHOWN=%d|%d|%u|1|STATE_UNCHANGED\n",gameMenuOwner_,gameMenuTurn_,sequence_);
    }
    void OpenPrivateMenu(){
        Require();RequirePrivateMenuOwner();EnsureMenuOptions();
        if(active_ || dispatching_ || timerState_!=TimerState::Released || !scripts_.IsQuiescent())
            throw std::logic_error("Private menu entry requires its idle timer-free child");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        CallPrivateMenu(kind_==UiPopupKind::MenuOptions?"OpenMenuOptions":kind_==UiPopupKind::TouchHelp?"OpenTouchHelp":"OpenMapMenu");
        bool shown=false;Call(&ObserveActive,&shown);
        if(!shown || timerState_!=TimerState::Released || before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("Private menu changed gameplay or its parent-owned timer at entry");
        active_=true;host_.popupVisible=true;++sequence_;shownSnapshot_=WriteSnapshot("shown");
    }
    bool HasPendingMapMenuRequests() const {Require();return mapMenuReady_ || !mapMenuRequests_.empty();}
    std::vector<MapMenuRequest> TakeMapMenuRequests(){
        Require();RequirePrivateMenuOwner();
        if(kind_!=UiPopupKind::MapMenu || privateMenuInput_ || dispatching_ || !scripts_.IsQuiescent() || timerState_!=TimerState::Released)
            throw std::logic_error("Map handoff requires its completed child callback");
        if(mapMenuRequests_.empty())return {};
        if(!mapMenuReady_ || mapMenuRequests_.size()!=1)throw std::logic_error("Map mutation is not ready for handoff");
        const auto& request=mapMenuRequests_.front();
        if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn() ||
           (request.kind==MapMenuRequest::Kind::Delete)!=active_)
            throw std::logic_error("Map mutation lost its owner or original save/delete return boundary");
        std::vector<MapMenuRequest> result;result.swap(mapMenuRequests_);mapMenuReady_=false;return result;
    }
    void RefreshMapMenu(std::shared_ptr<const UiMapMenuCatalog> catalog){
        Require();RequirePrivateMenuOwner();
        if(kind_!=UiPopupKind::MapMenu || !active_ || dispatching_ || HasPendingMapMenuRequests() || !catalog || !catalog->nameAvailable)
            throw std::logic_error("Map catalog refresh requires its settled active child");
        mapMenuCatalog_=std::move(catalog);CallPrivateMenu("RefreshMapMenu");
        ++revision_;const auto phase="updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());
    }
    void OpenExitConfirm(){
        Require();RequireExitConfirmOwner();
        if(!vm_ || active_ || dispatching_ || stopping_ || faulted_ || !scripts_.IsQuiescent() ||
           timerState_!=TimerState::Released || exitConfirmInput_ || exitConfirmClosed_ ||
           gameMenuReady_ || !gameMenuRequests_.empty())
            throw std::logic_error("ExitConfirm entry requires its idle timer-free owned child");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        Call(&OpenExitConfirmLua,nullptr);
        bool shown=false;Call(&ObserveActive,&shown);
        if(!shown || timerState_!=TimerState::Released || before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("Original ExitConfirm entry changed gameplay or its parent-owned timer");
        active_=true;host_.popupVisible=true;++sequence_;shownSnapshot_=WriteSnapshot("shown");
        std::printf("INTERACTIVE_EXIT_CONFIRM_SHOWN=%d|%d|%u|0|STATE_UNCHANGED\n",gameMenuOwner_,gameMenuTurn_,sequence_);
    }
    void OpenSaveMenu(){
        Require();RequireSaveMenuOwner();
        if(!vm_ || active_ || dispatching_ || faulted_ || !scripts_.IsQuiescent() ||
           timerState_!=TimerState::Released || saveMenuInput_ || saveMenuReady_ || !saveMenuRequests_.empty())
            throw std::logic_error("SaveMenu entry requires its idle timer-free child context");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        Call(&OpenSaveMenuLua,nullptr);
        bool shown=false;Call(&ObserveActive,&shown);
        if(!shown || timerState_!=TimerState::Released || before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("Original SaveMenu entry changed gameplay or its parent-owned timer");
        active_=true;host_.popupVisible=true;++sequence_;shownSnapshot_=WriteSnapshot("shown");
        std::printf("INTERACTIVE_SAVE_MENU_SHOWN=%d|%d|%u|0|STATE_UNCHANGED\n",gameMenuOwner_,gameMenuTurn_,sequence_);
    }
    void OpenLoadMenu(){
        Require();RequireLoadMenuOwner();
        if(!vm_ || active_ || dispatching_ || faulted_ || !scripts_.IsQuiescent() ||
           timerState_!=TimerState::Released || loadMenuInput_ || loadMenuReady_ ||
           !loadMenuRequests_.empty() || loadMenuCursorToken_!=0)
            throw std::logic_error("LoadMenu entry requires its idle timer-free child context");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        Call(&OpenLoadMenuLua,nullptr);
        bool shown=false;Call(&ObserveActive,&shown);
        if(!shown || timerState_!=TimerState::Released || loadMenuCursorToken_!=0 ||
           before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("Original LoadMenu entry changed gameplay, cursor, or its parent-owned timer");
        active_=true;host_.popupVisible=true;++sequence_;shownSnapshot_=WriteSnapshot("shown");
        std::printf("INTERACTIVE_LOAD_MENU_SHOWN=%d|%d|%u|0|STATE_UNCHANGED\n",gameMenuOwner_,gameMenuTurn_,sequence_);
    }
    bool HasPendingLoadMenuRequests() const {Require();return loadMenuReady_ || !loadMenuRequests_.empty();}
    std::vector<LoadMenuRequest> TakeLoadMenuRequests(){
        Require();RequireLoadMenuOwner();
        if(dispatching_ || loadMenuInput_ || faulted_ || !scripts_.IsQuiescent() || timerState_!=TimerState::Released)
            throw std::logic_error("LoadMenu requests require a completed timer-free child callback");
        if(!loadMenuReady_){
            if(!loadMenuRequests_.empty())throw std::logic_error("LoadMenu has an uncommitted callback request");
            return {};
        }
        try{
            const bool loading=loadMenuRequests_.size()==2 && loadMenuRequests_.front().kind==LoadMenuRequest::Kind::Load;
            if(active_ || loadMenuRequests_.empty() || loadMenuRequests_.size()>2 ||
               loadMenuRequests_.back().kind!=LoadMenuRequest::Kind::Close ||
               (loadMenuRequests_.size()==2 && !loading) || loadMenuCursorToken_!=(loading?1:0))
                throw std::logic_error("LoadMenu command has not completed its original load/return boundary");
            for(const auto& request:loadMenuRequests_)
                if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn())
                    throw std::logic_error("LoadMenu owner or turn changed before handoff");
            if(loading && !CanLoadMenuFile(FindLoadMenuFile(loadMenuRequests_.front().fileName.c_str())))
                throw std::runtime_error("LoadMenu file changed or became incompatible before handoff");
            std::vector<LoadMenuRequest> result;result.swap(loadMenuRequests_);loadMenuReady_=false;
            RestoreLoadMenuCursor();return result;
        }catch(...){Fault();throw;}
    }
    bool HasPendingSaveMenuRequests() const {Require();return saveMenuReady_ || !saveMenuRequests_.empty();}
    bool SaveMenuTextInputEnabled(){
        Require();if(kind_==UiPopupKind::MapMenu)RequirePrivateMenuOwner();else RequireSaveMenuOwner();
        if(!active_ || dispatching_ || !scripts_.IsQuiescent())return false;
        bool enabled=false;Call(&ObserveSaveMenuTextInputLua,&enabled);return enabled;
    }
    std::uint64_t SaveMenuTextInputFocusToken(){
        Require();if(kind_==UiPopupKind::MapMenu)RequirePrivateMenuOwner();else RequireSaveMenuOwner();
        if(!active_ || dispatching_ || !scripts_.IsQuiescent())return 0;
        std::uint64_t token=0;Call(&ObserveSaveMenuTextInputFocusLua,&token);return token;
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
           (saveMenuRequests_.size()==2 && saveMenuRequests_.front().kind!=SaveMenuRequest::Kind::Save &&
            saveMenuRequests_.front().kind!=SaveMenuRequest::Kind::Overwrite))
            throw std::logic_error("SaveMenu command has not completed its original save/return boundary");
        for(const auto& request:saveMenuRequests_){
            if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn())
                throw std::logic_error("SaveMenu owner or turn changed before handoff");
            if((request.kind==SaveMenuRequest::Kind::Overwrite)!=!!request.expected ||
               (request.kind==SaveMenuRequest::Kind::Close && !request.name.empty()))
                throw std::logic_error("SaveMenu command has an invalid overwrite or close payload");
            if(request.expected && (!saveMenuCatalog_->overwriteSupported || !request.expected->header ||
               !SameUiSaveMenuObservation(FindSaveMenuFile(request.expected->fileName.c_str()),*request.expected)))
                throw std::logic_error("SaveMenu overwrite lost its immutable listed observation");
        }
        std::vector<SaveMenuRequest> result;result.swap(saveMenuRequests_);saveMenuReady_=false;return result;
    }
    bool HasPendingGameMenuRequests() const {Require();return gameMenuReady_ || !gameMenuRequests_.empty();}
    std::vector<GameMenuRequest> TakeGameMenuRequests(){
        Require();
        if((kind_!=UiPopupKind::GameMenu && kind_!=UiPopupKind::TopPanel && kind_!=UiPopupKind::ExitConfirm && kind_!=UiPopupKind::SaveMenu) || !externalRouting_ ||
           dispatching_ || gameMenuInput_ || topPanelInput_ || exitConfirmInput_ || saveMenuInput_ || faulted_ || !scripts_.IsQuiescent())
            throw std::logic_error("GameMenu handoff requires its completed original owner callback");
        if(!gameMenuReady_){
            if(!gameMenuRequests_.empty())throw std::logic_error("GameMenu request has no completed input boundary");
            return {};
        }
        if(gameMenuRequests_.size()!=1)throw std::logic_error("GameMenu handoff must contain exactly one request");
        for(const auto& request:gameMenuRequests_){
            if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn())
                throw std::logic_error("GameMenu request owner or turn changed before handoff");
            if(kind_==UiPopupKind::ExitConfirm){
                if(request.kind!=GameMenuRequest::Kind::ExitGame || request.action!="ExitGame" || active_ ||
                   !exitConfirmClosed_ || timerState_!=TimerState::Released)
                    throw std::logic_error("ExitConfirm handoff requires its completed original Yes callback");
            }else if(kind_==UiPopupKind::SaveMenu){
                if(request.kind!=GameMenuRequest::Kind::OpenMapMenu || !active_ || timerState_!=TimerState::Released || !saveMenuRequests_.empty())
                    throw std::logic_error("Nested map handoff lost its original SaveMenu parent");
            }else if(request.kind==GameMenuRequest::Kind::Open){
                if(kind_!=UiPopupKind::TopPanel || !active_ || timerState_!=TimerState::Released)
                    throw std::logic_error("GameMenu open request left its nonmodal TopPanel callback");
            }else{
                if(kind_!=UiPopupKind::GameMenu || request.kind==GameMenuRequest::Kind::ExitGame ||
                   timerState_!=((active_ && request.kind!=GameMenuRequest::Kind::MainMenu)?TimerState::Held:TimerState::Released) ||
                   (request.kind==GameMenuRequest::Kind::QuickSave && active_) ||
                   (request.kind==GameMenuRequest::Kind::OpenExitConfirm && (!active_ || request.action!="ExitConfirm")))
                    throw std::logic_error("GameMenu command has not reached its original return boundary");
            }
        }
        std::vector<GameMenuRequest> result;result.swap(gameMenuRequests_);gameMenuReady_=false;return result;
    }
    void ShowGameMenuUnavailable(const std::string& action,const std::string& message){
        Require();RequireGameMenuOwner();
        if(!vm_ || !active_ || dispatching_ || !scripts_.IsQuiescent() ||
           timerState_!=TimerState::Held || gameMenuInput_ || gameMenuReady_ ||
           !gameMenuRequests_.empty() || gameMenuCursorToken_!=0)
            throw std::logic_error("GameMenu notice requires its active owner after request handoff");
        if(action.find('\0')!=std::string::npos || !IsGameMenuUnavailableAction(action.c_str()) ||
           message.empty() || message.size()>4096 || message.find('\0')!=std::string::npos)
            throw std::invalid_argument("GameMenu notice requires an original action and bounded text");
        Utf8Length(message.c_str());
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        GameMenuNoticeCall input{&action,&message};Call(&ShowGameMenuUnavailableLua,&input);
        bool shown=false;Call(&ObserveActive,&shown);
        if(!shown || timerState_!=TimerState::Held || !scripts_.IsQuiescent() ||
           gameMenuCursorToken_!=0 || !gameMenuRequests_.empty() ||
           before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("GameMenu notice changed gameplay or its original modal ownership");
        ++revision_;const auto phase="updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());
        std::printf("INTERACTIVE_GAME_MENU_UNAVAILABLE_SHOWN=%d|%d|%s|STATE_UNCHANGED\n",
            gameMenuOwner_,gameMenuTurn_,action.c_str());
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
            if((kind_!=UiPopupKind::GameMenu && kind_!=UiPopupKind::SaveMenu && kind_!=UiPopupKind::LoadMenu && kind_!=UiPopupKind::ExitConfirm && !IsPrivateMenuChild()) ||
               timerRecoveryFailed_ || timerState_!=TimerState::Released || !scripts_.IsQuiescent())throw;
            std::fprintf(stderr,"UI_POPUP_MENU_STOP_CLOSE_FAILURE=%s\n",error.what());
            Fault();
        }catch(...){
            Require();
            if((kind_!=UiPopupKind::GameMenu && kind_!=UiPopupKind::SaveMenu && kind_!=UiPopupKind::LoadMenu && kind_!=UiPopupKind::ExitConfirm && !IsPrivateMenuChild()) ||
               timerRecoveryFailed_ || timerState_!=TimerState::Released || !scripts_.IsQuiescent())throw;
            std::fprintf(stderr,"UI_POPUP_MENU_STOP_CLOSE_FAILURE=unknown\n");
            Fault();
        }
        if(kind_==UiPopupKind::GameMenu)RestoreGameMenuCursor();
        if(kind_==UiPopupKind::LoadMenu)RestoreLoadMenuCursor();
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
    void Submit(const CvPopupInfo& input){Submit(OwnedPopupInfo(input));}
    void Submit(const OwnedPopupInfo& input){
        Require();
        if(kind_==UiPopupKind::LeaderHead || kind_==UiPopupKind::CityView || kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::LoadMenu || kind_==UiPopupKind::ExitConfirm || IsPrivateMenuChild())throw std::invalid_argument("Leader, city, and game-menu screens require their own entry point");
        if(kind_==UiPopupKind::DeclareWar?(input.type!=BUTTONPOPUP_DECLAREWARMOVE && input.type!=BUTTONPOPUP_DECLAREWARRANGESTRIKE):
           input.type!=(kind_==UiPopupKind::GoodyHutReward?BUTTONPOPUP_GOODY_HUT_REWARD:kind_==UiPopupKind::Pantheon?BUTTONPOPUP_FOUND_PANTHEON:kind_==UiPopupKind::EconomicOverview?BUTTONPOPUP_ECONOMIC_OVERVIEW:kind_==UiPopupKind::SocialPolicy?BUTTONPOPUP_CHOOSEPOLICY:kind_==UiPopupKind::TradeRoute?BUTTONPOPUP_TRADE_ROUTE_OVERVIEW:kind_==UiPopupKind::Ranking?BUTTONPOPUP_WHOS_WINNING:kind_==UiPopupKind::Production?BUTTONPOPUP_CHOOSEPRODUCTION:kind_==UiPopupKind::CityCapture?BUTTONPOPUP_CITY_CAPTURED:kind_==UiPopupKind::TechAward?BUTTONPOPUP_TECH_AWARD:kind_==UiPopupKind::ResearchTree?BUTTONPOPUP_TECH_TREE:BUTTONPOPUP_CHOOSETECH))
            Unsupported("UI popup type does not match its selected official context");
        if(kind_==UiPopupKind::EconomicGeneral || kind_==UiPopupKind::EconomicHappiness)
            Unsupported("Embedded EconomicOverview child contexts cannot receive popup submissions");
        if(faulted_)throw std::logic_error("UI popup context is faulted and must be stopped");
        if(!vm_ || active_ || dispatching_)throw std::logic_error("UI popup is closed, already active or reentered");
        if(kind_==UiPopupKind::GoodyHutReward && (input.data.size()<2 || input.Data(0)<0 || input.Data(1)<0))
            throw std::invalid_argument("Goody-hut reward requires its original reward ID and nonnegative special value");
        if(kind_==UiPopupKind::Pantheon){
            if(input.Data(1)!=1 || sequence_==UINT_MAX)
                throw std::invalid_argument("Pantheon popup requires its original Pantheon-only payload");
            pantheonOwner_=game_->GetActivePlayer();pantheonTurn_=game_->GetGameTurn();
            pantheonGeneration_=sequence_+1;RequirePantheonOwner(false);
        }
        if(kind_==UiPopupKind::SocialPolicy){
            policyOwner_=game_->GetActivePlayer();
            if(policyOwner_<0 || policyOwner_>=MAX_PLAYERS)
                throw std::logic_error("SocialPolicy requires a valid active player");
        }
        if(kind_==UiPopupKind::EconomicOverview){
            const int owner=game_->GetActivePlayer();
            if(!host_.localSdkSessionBound || game_->IsGameMultiPlayer() || input.Data(0)!=owner ||
               owner<0 || owner>=MAX_PLAYERS)
                throw std::logic_error("EconomicOverview requires its original active local-player popup payload");
            std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(owner)));
            if(!player || !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive())
                throw std::logic_error("EconomicOverview requires the living active human turn");
            economicOwnerId_=owner;economicTurn_=game_->GetGameTurn();
        }
        if(kind_==UiPopupKind::DeclareWar)PrepareWarInput(input);
        if(kind_==UiPopupKind::TradeRoute){
            tradeRouteOwner_=game_->GetActivePlayer();
            if(tradeRouteOwner_<0 || tradeRouteOwner_>=MAX_PLAYERS)
                throw std::logic_error("TradeRoute overview requires a valid active player");
        }
        if(kind_==UiPopupKind::Production){
            if(input.Data(0)<0)throw std::invalid_argument("Production popup requires its original city identity");
            productionCity_=input.Data(0);productionOwner_=game_->GetActivePlayer();
        }
        if(kind_==UiPopupKind::TechAward &&
           (input.Data(0)!=game_->GetActivePlayer() || input.Data(1)!=0 || input.Data(2)<0))
            throw std::invalid_argument("Technology award requires its active-player, zero, technology payload");
        if(kind_==UiPopupKind::TechAward)techAwardTechnology_=input.Data(2);
        if(kind_==UiPopupKind::CityCapture){
            if(input.data.size()!=5 || input.options.size()!=2 || input.Data(0)<0 || input.Data(4)<-1 || input.Data(4)>=MAX_PLAYERS)
                throw std::invalid_argument("BNW city capture requires its complete five-integer/two-option payload");
            captureCity_=input.Data(0);captureOwner_=game_->GetActivePlayer();captureLiberated_=input.Data(4);
            captureDecisionDone_=false;
        }
        OwnedPopupInfo value(input);
        Call(&Dispatch,&value);
        if(timerState_!=(RetainsTimer()?TimerState::Held:TimerState::Released))
            throw std::runtime_error("Official popup native timer state differs from its context contract");
        active_=true;host_.popupVisible=true;
        if(kind_==UiPopupKind::EconomicOverview)ApplyEconomicVisibility(false);
        ++sequence_;
        shownSnapshot_=WriteSnapshot("shown");
        if(kind_==UiPopupKind::TechAward)
            std::printf("INTERACTIVE_TECH_AWARD_SHOWN=%d|%d|%d|%d|1\n",input.Data(0),input.Data(1),input.Data(2),game_->GetGameTurn());
        if(kind_==UiPopupKind::TradeRoute)
            std::printf("INTERACTIVE_TRADE_ROUTE_SHOWN=%d|%d|%d|%d|1\n",tradeRouteOwner_,input.Data(0),input.Data(1),game_->GetGameTurn());
        if(kind_==UiPopupKind::SocialPolicy)
            std::printf("INTERACTIVE_SOCIAL_POLICY_SHOWN=%d|%d|%d|%d|1\n",policyOwner_,input.Data(0),input.Data(1),game_->GetGameTurn());
        if(kind_==UiPopupKind::EconomicOverview)
            std::printf("INTERACTIVE_ECONOMIC_OVERVIEW_SHOWN=%d|%d|%d|1\n",economicOwnerId_,input.Data(0),economicTurn_);
        host_.Record("ui-popup-shown:"+std::to_string(sequence_)+":"+std::to_string(game_->GetGameTurn()));
    }
    void SubmitLeader(const OwnedLeaderMessage& input){
        Require();
        if(kind_!=UiPopupKind::LeaderHead || !externalRouting_ || !vm_ || active_ || dispatching_ || faulted_ || leaderMessage_)
            throw std::logic_error("Leader message requires its idle owned original context");
        if(input.receiver!=game_->GetActivePlayer())throw std::logic_error("Leader message receiver changed before presentation");
        std::unique_ptr<ICvPlayer1> receiver(game_->GetPlayer(static_cast<PlayerTypes>(input.receiver)));
        if(!receiver || !receiver->IsAlive() || !receiver->IsHuman() || pregame_->isNetworkMultiplayerGame())
            throw std::logic_error("Leader presentation requires its local living human receiver");
        receiver.reset();leaderMessage_.reset(new OwnedLeaderMessage(input));
        const std::string payload="{\"receiver\":"+std::to_string(input.receiver)+",\"player\":"+
            std::to_string(static_cast<int>(input.player))+",\"state\":"+std::to_string(static_cast<int>(input.state))+
            ",\"animation\":"+std::to_string(static_cast<int>(input.animation))+",\"data1\":"+std::to_string(input.data1)+
            ",\"text\":"+UiSnapshotJson::Quote(input.text)+"}\n";
        SdkStateSnapshot::Write(directory_+L"\\leader-message-input.json",payload);
        Call(&DispatchLeader,leaderMessage_.get());
        bool shown=false;Call(&ObserveActive,&shown);
        if(!shown || !host_.leaderRootUp || timerState_!=TimerState::Released)
            throw std::runtime_error("Original leader root did not present the complete SDK message");
        active_=true;host_.popupVisible=true;++sequence_;
        shownSnapshot_=WriteSnapshot("shown");
        std::printf("INTERACTIVE_DIPLOMACY_SHOWN=%d|%d|%d|%d|%d|%zu\n",input.receiver,static_cast<int>(input.player),
            static_cast<int>(input.state),static_cast<int>(input.animation),input.data1,input.text.size());
    }
    void SubmitCityView(int owner,int city,bool viewingMode=true){
        Require();
        if(kind_!=UiPopupKind::CityView || !externalRouting_ || !vm_ || active_ || faulted_ ||
           owner!=game_->GetActivePlayer() || frontend_.IsCityScreenViewingMode()!=viewingMode || !frontend_.isCityScreenUp())
            throw std::logic_error("CityView requires its selected owned city and explicit viewing mode");
        {std::unique_ptr<ICvCity1> selected(frontend_.getHeadSelectedCity());
         if(!selected || selected->GetOwner()!=owner || selected->GetID()!=city)
             throw std::logic_error("CityView identity changed before original entry");}
        cityViewOwner_=owner;cityViewCity_=city;cityViewReadOnly_=viewingMode;
        Call(&EnterCityView,nullptr);
        if(!pendingCityCitizens_ || !scripts_.IsQuiescent())
            throw std::logic_error("Original CityView entry did not queue its citizen refresh");
        pendingCityCitizens_=false;
        SdkStateSnapshot::Write(directory_+L"\\city-enter-before-citizens.txt",SdkStateSnapshot::Capture(host_));
        {std::unique_ptr<ICvNetMessageHandler1> receiver(core_->GetNetMessageHandler());
         if(!receiver)throw std::runtime_error("CityView has no original citizen update receiver");
         receiver->ResponseUpdateCityCitizens(static_cast<PlayerTypes>(owner),city);}
        SdkStateSnapshot::Write(directory_+L"\\city-enter-after-citizens.txt",SdkStateSnapshot::Capture(host_));
        Call(&RefreshCityView,nullptr);
        bool shown=false;Call(&ObserveActive,&shown);
        if(!shown || timerState_!=TimerState::Released)throw std::runtime_error("Original CityView did not enter its shown state");
        active_=true;host_.popupVisible=true;++sequence_;shownSnapshot_=WriteSnapshot("shown");
        std::printf("INTERACTIVE_CITY_VIEW_SHOWN=%d|%d|%u\n",owner,city,viewingMode?1u:0u);
    }
    bool TakeCityProductionRequest(CvPopupInfo& output){
        Require();if(!cityProductionRequest_)return false;
        if(kind_!=UiPopupKind::CityView || !active_ || cityViewReadOnly_ || !scripts_.IsQuiescent())
            throw std::logic_error("City production handoff requires its active editable city context");
        output=*cityProductionRequest_;cityProductionRequest_.reset();
        bool hidden=false;Call(&CityProductionVisibility,&hidden);
        return true;
    }
    void ReturnFromCityProduction(){
        Require();if(kind_!=UiPopupKind::CityView || !active_ || cityViewReadOnly_ || !scripts_.IsQuiescent())
            throw std::logic_error("Production return requires its retained editable city context");
        bool hidden=true;Call(&CityProductionVisibility,&hidden);Call(&RefreshCityView,nullptr);
        host_.popupVisible=true;++revision_;const auto phase="production-returned-"+std::to_string(revision_);WriteSnapshot(phase.c_str());
        std::printf("INTERACTIVE_CITY_PRODUCTION_RETURNED=%d|%d\n",cityViewOwner_,cityViewCity_);
    }
    bool TakeEconomicProductionRequest(int& cityId){
        Require();
        if(kind_!=UiPopupKind::EconomicOverview || !economicProductionPending_)return false;
        if(!active_ || faulted_ || !scripts_.IsQuiescent() || !economicChildren_[0] || economicChildren_[0]->dispatching_ ||
           game_->GetActivePlayer()!=economicOwnerId_ || game_->GetGameTurn()!=economicTurn_)
            throw std::logic_error("Economic production handoff is not at its original callback boundary");
        const int requested=pendingEconomicProductionCity_;economicProductionPending_=false;pendingEconomicProductionCity_=-1;
        if(requested<0){
            std::printf("INTERACTIVE_ECONOMIC_PRODUCTION_SKIPPED=PUPPET|%d|%d\n",economicOwnerId_,economicTurn_);
            return false;
        }
        const int owner=game_->GetActivePlayer();
        if(owner<0 || owner>=MAX_PLAYERS)throw std::logic_error("Economic production request has no active player");
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(owner)));
        std::unique_ptr<ICvCity1> city(player?player->GetCity(requested):nullptr);
        if(!player || !city || city->GetOwner()!=owner)
            throw std::logic_error("Economic production request lost its original active-player city");
        // The stock ProductionPopup closes without presenting for a puppet city.
        // Consume that original callback without suspending the economic screen.
        if(city->IsPuppet())return false;
        cityId=requested;return true;
    }
    void RefreshEconomicOverview(){
        Require();
        if(kind_!=UiPopupKind::EconomicOverview || !externalRouting_ || !vm_ || !active_ || faulted_ || dispatching_ ||
           !scripts_.IsQuiescent() || economicProductionPending_ || !economicChildren_[0] || !economicChildren_[1] ||
           game_->GetActivePlayer()!=economicOwnerId_ || game_->GetGameTurn()!=economicTurn_)
            throw std::logic_error("EconomicOverview refresh requires its idle retained parent context");
        host_.popupVisible=true;
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        bool shown=false;Call(&RefreshEconomicLua,&shown);
        if(!shown || timerState_!=TimerState::Held)
            throw std::runtime_error("Original EconomicOverview refresh did not retain its shown parent timer");
        active_=true;ApplyEconomicVisibility(false);
        if(before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("EconomicOverview refresh changed gameplay or synchronous RNG");
        ++revision_;const auto phase="production-returned-"+std::to_string(revision_);WriteSnapshot(phase.c_str());
    }
    bool TakeCityViewRequest(int& owner,int& city){
        Require();if(!pendingCityView_)return false;
        if(kind_!=UiPopupKind::CityCapture || !active_ || !cityViewBarrier_ || captureDecisionDone_ || !scripts_.IsQuiescent())
            throw std::logic_error("CityView handoff is not at the captured-city callback boundary");
        pendingCityView_=false;owner=captureOwner_;city=captureCity_;return true;
    }
    void ReturnFromCityView(){
        Require();
        if(kind_!=UiPopupKind::CityCapture || !active_ || !cityViewBarrier_ || captureDecisionDone_ ||
           frontend_.isCityScreenUp() || frontend_.IsCityScreenViewingMode())
            throw std::logic_error("Captured-city return requires its closed original CityView");
        Call(&CityViewReturned,nullptr);
        if(cityViewBarrier_)throw std::logic_error("Original captured-city listener did not release EmptyPopup");
        host_.popupVisible=true;++revision_;const auto phase="returned-"+std::to_string(revision_);WriteSnapshot(phase.c_str());
        std::printf("INTERACTIVE_CITY_VIEW_RETURNED=%d|%d\n",captureOwner_,captureCity_);
    }
    void WarStateChanged(const OwnedWarStateChanged& change){
        Require();
        if(kind_!=UiPopupKind::LeaderHead || !externalRouting_ || !active_ || faulted_ || dispatching_ ||
           !leaderMessage_ || leaderDecisionDone_ || pendingLeaderLeave_ || !host_.leaderRootUp ||
           leaderMessage_->receiver!=game_->GetActivePlayer() || !scripts_.IsQuiescent())
            throw std::logic_error("War-state delivery requires its active quiescent original LeaderHead context");
        OwnedWarStateChanged owned(change);Call(&DispatchWarStateChanged,&owned);
        if(!active_ || faulted_ || !host_.leaderRootUp)
            throw std::runtime_error("Original LeaderHead war-state handler closed or faulted its context");
        ++revision_;const auto phase="updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());
    }
    void CloseInformationalPopup(){
        Require();
        if(!vm_)return;
        if(IsPrivateMenuChild()){
            if(!faulted_ && active_){
                for(unsigned attempt=0;attempt<2 && active_;++attempt)DispatchInput(UiInputKind::KeyDown,VK_ESCAPE);
                if(active_)throw std::logic_error("Menu child failed to close through its original Escape handler");
            }
            active_=false;
            if(host_.menuOptions && (kind_==UiPopupKind::MenuOptions || kind_==UiPopupKind::TouchHelp) && host_.menuOptions->Active())host_.menuOptions->Discard();
            if(stopping_ || faulted_){mapMenuRequests_.clear();mapMenuReady_=false;privateMenuInput_=false;}
            return;
        }
        if((kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SaveMenu || kind_==UiPopupKind::LoadMenu || kind_==UiPopupKind::ExitConfirm || IsPrivateMenuChild()) && !faulted_){
            try{if(kind_==UiPopupKind::ExitConfirm)RequireExitConfirmOwner();else if(kind_==UiPopupKind::LoadMenu)RequireLoadMenuOwner();else if(kind_==UiPopupKind::SaveMenu)RequireSaveMenuOwner();else RequireGameMenuOwner();}
            catch(...){if(!faulted_)throw;}
        }
        if(kind_==UiPopupKind::ExitConfirm){
            if(!faulted_ && active_){
                DispatchInput(UiInputKind::KeyDown,VK_ESCAPE);
                if(active_)throw std::logic_error("Original ExitConfirm did not cancel during owner-requested close");
            }
            active_=false;
            if(stopping_ || faulted_){
                gameMenuRequests_.clear();gameMenuReady_=false;exitConfirmInput_=false;
                exitConfirmYesInput_=false;exitConfirmCloseInput_=false;exitConfirmClosed_=false;
            }
            return;
        }
        if(kind_==UiPopupKind::LoadMenu){
            if(!faulted_ && active_){
                // The first Escape may only collapse the original PullDown.
                // A second reaches the original OnBack, without inventing a
                // load or mutating the retained parent-owned timer.
                for(unsigned attempt=0;attempt<2 && active_;++attempt)DispatchInput(UiInputKind::KeyDown,VK_ESCAPE);
                if(active_)throw std::logic_error("Original LoadMenu did not close during its owner-requested return");
            }
            active_=false;
            // Normal closing publishes the original completed callback for
            // TakeLoadMenuRequests. Only destruction or fault discards it.
            if(stopping_ || faulted_){
                loadMenuRequests_.clear();loadMenuReady_=false;loadMenuInput_=false;
                RestoreLoadMenuCursor();
            }
            return;
        }
        if(kind_==UiPopupKind::SaveMenu){
            if(!faulted_ && active_){
                // Escape first cancels the original confirmation, if present.
                // Only the next Escape reaches OnBack and closes the child.
                for(unsigned attempt=0;attempt<2 && active_;++attempt)DispatchInput(UiInputKind::KeyDown,VK_ESCAPE);
                if(active_)throw std::logic_error("Original SaveMenu did not close during its owner-requested return");
                TakeSaveMenuRequests();
            }
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
    bool IsActive() const {Require();return active_;}
    bool CanReuseProductionFor(const ICvGameContext3& core,PlayerTypes activePlayer) const {
        Require();
        return activePlayer>=0 && activePlayer<MAX_PLAYERS &&
            kind_==UiPopupKind::Production && core_==&core && externalRouting_ &&
            vm_ && !stopping_ && !active_ && !dispatching_ && !faulted_ && !timerRecoveryFailed_ &&
            timerState_==TimerState::Released && scripts_.IsQuiescent() && game_ &&
            productionOwner_==activePlayer && game_->GetActivePlayer()==activePlayer &&
            !host_.deferCityPurchase && !purchaseCommand_ && !pendingPurchaseSound_;
    }
    int TechAwardTechnology() const {
        Require();if(kind_!=UiPopupKind::TechAward || !active_)throw std::logic_error("No active original technology award");
        return techAwardTechnology_;
    }
    bool CaptureDecisionMatches(int city,int liberated=-2) const {
        Require();return kind_==UiPopupKind::CityCapture && !captureDecisionDone_ &&
            captureOwner_==game_->GetActivePlayer() && captureCity_==city &&
            (liberated==-2 || (liberated>=0 && captureLiberated_==liberated));
    }
    std::uint64_t CapturedPuppetKey(){
        Require();if(kind_!=UiPopupKind::CityCapture || !active_)throw std::logic_error("No active capture popup for its puppet button");
        std::uint64_t result=0;Call(&ReadCapturePuppetKey,&result);return result;
    }
    std::uint64_t CapturedViewKey(){
        Require();if(kind_!=UiPopupKind::CityCapture || !active_ || cityViewBarrier_)throw std::logic_error("No captured-city View button");
        std::uint64_t result=0;Call(&ReadCaptureViewKey,&result);return result;
    }
    std::uint64_t CityViewExitKey(){
        Require();if(kind_!=UiPopupKind::CityView || !active_)throw std::logic_error("No original CityView return button");
        std::uint64_t result=0;Call(&ReadCityViewExitKey,&result);return result;
    }
    std::uint64_t LeaderBackKey(){
        Require();if(kind_!=UiPopupKind::LeaderHead || !active_ || leaderDecisionDone_)
            throw std::logic_error("No active original leader return button");
        std::uint64_t result=0;Call(&ReadLeaderBackKey,&result);return result;
    }
    bool HasLeaderDecision() const {
        Require();return kind_==UiPopupKind::LeaderHead && leaderMessage_ && !leaderDecisionDone_;
    }
    bool IsPantheonCommitBoundary(int owner,int turn,int belief) const {
        Require();
        if(kind_!=UiPopupKind::Pantheon || !externalRouting_ || active_ || faulted_ || !pantheonCommit_ ||
           timerState_!=TimerState::Released || !scripts_.IsQuiescent())return false;
        const auto& command=*pantheonCommit_;
        return command.owner==owner && command.turn==turn && command.belief==belief &&
            owner==pantheonOwner_ && turn==pantheonTurn_ && owner==game_->GetActivePlayer() && turn==game_->GetGameTurn() &&
            command.generation==pantheonGeneration_ && command.generation==sequence_ && command.revision==revision_;
    }
    bool TakeDeferredPopup(CvPopupInfo* output){
        Require();
        if(!externalRouting_ || !output)throw std::logic_error("Deferred popup handoff requires an external router and output");
        if(dispatching_)throw std::logic_error("Deferred popup cannot be taken during its Lua callback");
        if(!deferredPopupReady_)return false;
        if(kind_!=UiPopupKind::Research || active_ || timerState_!=TimerState::Released || !researchTreeRequested_)
            throw std::logic_error("Deferred TechTree popup is not at its closed owner-thread handoff boundary");
        *output=CvPopupInfo(BUTTONPOPUP_TECH_TREE,-1,requestedTreeSteal_);
        deferredPopupReady_=false;researchTreeRequested_=false;
        return true;
    }
    void Tick(double seconds){
        Require();
        if(!std::isfinite(seconds) || seconds<frameTime_ || seconds>86400.0)
            throw std::invalid_argument("UI owner clock must be finite, monotonic and bounded");
        // The three retained VMs compose one frame. A child's lack of a
        // turn semaphore does not give its presentation clock a separate epoch.
        if(kind_==UiPopupKind::EconomicOverview){
            for(const auto& child:economicChildren_){
                if(!child || child->economicOwner_!=this || !child->vm_ || child->faulted_ ||
                   child->dispatching_ || child->frameTime_>seconds)
                    throw std::logic_error("Economic child cannot follow its owner's presentation clock");
                child->Require();
            }
        }
        frameTime_=seconds;
        if(kind_==UiPopupKind::EconomicOverview)
            for(auto& child:economicChildren_)child->Tick(seconds);
    }
    std::string CaptureFrame(double seconds){
        Tick(seconds);++revision_;const auto phase="frame-"+std::to_string(revision_);
        return WriteSnapshot(phase.c_str());
    }
    std::string SnapshotForExternalScene(){
        Require();
        if(!externalRouting_)throw std::logic_error("External scene snapshots require an externally routed popup context");
        return SnapshotText();
    }
    bool RefreshTopPanel(){
        Require();
        if(kind_!=UiPopupKind::TopPanel || !externalRouting_ || !vm_ || faulted_ || dispatching_ ||
           !scripts_.IsQuiescent() || topPanelInput_ || topPanelPopup_ || gameMenuReady_ || !gameMenuRequests_.empty())
            throw std::logic_error("TopPanel refresh requires its idle owned context");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        bool shown=false;Call(&RefreshTopPanelLua,&shown);active_=shown;topPanelOwner_=game_->GetActivePlayer();
        if(timerState_!=TimerState::Released || before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("Original TopPanel refresh changed gameplay or its nonmodal timer contract");
        return active_;
    }
    bool RefreshActionInfoPanel(){
        Require();
        if(kind_!=UiPopupKind::ActionInfoPanel || !externalRouting_ || !vm_ || faulted_ || dispatching_ ||
           !scripts_.IsQuiescent() || actionInfoInput_ || actionInfoReady_ || !actionInfoRequests_.empty())
            throw std::logic_error("ActionInfoPanel refresh requires its idle owned context");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        bool shown=false;Call(&RefreshActionInfoPanelLua,&shown);active_=shown;
        actionInfoOwner_=game_->GetActivePlayer();actionInfoTurn_=game_->GetGameTurn();
        if(timerState_!=TimerState::Released || before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("Original ActionInfoPanel refresh changed gameplay or its nonmodal timer contract");
        return active_;
    }
    bool RefreshNotificationPanel(){
        Require();
        if(kind_!=UiPopupKind::NotificationPanel || !externalRouting_ || !vm_ || faulted_ || dispatching_ ||
           !scripts_.IsQuiescent() || actionInfoInput_ || actionInfoReady_ || !actionInfoRequests_.empty())
            throw std::logic_error("NotificationPanel refresh requires its idle owned context");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        bool shown=false;Call(&RefreshNotificationPanelLua,&shown);active_=shown;
        actionInfoOwner_=game_->GetActivePlayer();actionInfoTurn_=game_->GetGameTurn();
        if(timerState_!=TimerState::Released || before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("Original NotificationPanel refresh changed gameplay or its nonmodal timer contract");
        return active_;
    }
    std::vector<ActionInfoRequest> TakeActionInfoRequests(){
        Require();
        if(!IsNotificationInputPanel() || !externalRouting_ || dispatching_ || actionInfoInput_ ||
           !scripts_.IsQuiescent() || faulted_ || timerState_!=TimerState::Released)
            throw std::logic_error("ActionInfoPanel requests require their completed owner callback");
        if(!actionInfoReady_){
            if(!actionInfoRequests_.empty())throw std::logic_error("ActionInfoPanel has uncommitted callback requests");
            return {};
        }
        if(!active_ || actionInfoOwner_!=game_->GetActivePlayer() || actionInfoTurn_!=game_->GetGameTurn())
            throw std::logic_error("ActionInfoPanel request owner or turn changed before handoff");
        std::vector<ActionInfoRequest> result;result.swap(actionInfoRequests_);actionInfoReady_=false;return result;
    }
    bool RefreshUnitPanel(){
        Require();
        if(kind_!=UiPopupKind::UnitPanel || !externalRouting_ || !vm_ || faulted_ || dispatching_ ||
           !scripts_.IsQuiescent() || unitAction_)
            throw std::logic_error("UnitPanel refresh requires its idle owned context");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        bool shown=false;Call(&RefreshUnitPanelLua,&shown);active_=shown;
        if(timerState_!=TimerState::Released || before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("Original UnitPanel refresh changed gameplay or its nonmodal timer contract");
        return active_;
    }
    void RefreshSocialPolicy(){
        Require();RequirePolicyOwner();
        if(!vm_ || dispatching_ || !scripts_.IsQuiescent() || policyInput_ || policyCommand_ ||
           pendingPolicySound_ || policyInfoCachePending_)
            throw std::logic_error("Policy refresh requires an idle owned original context");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        Call(&PolicyDirty,nullptr);
        if(before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed() || timerState_!=TimerState::Held)
            throw std::runtime_error("Original policy refresh changed gameplay or its held timer");
    }
    unsigned long SynchronousRandomSeed(){
        Require();std::unique_ptr<ICvRandom1> random(game_->GetRandomNumberGenerator());
        if(!random)throw std::runtime_error("UI synchronous RNG interface is missing");
        return random->GetSeed();
    }
    std::vector<UiInputTarget> InputTargets(){
        Require();std::vector<UiInputTarget> output;UiInputTargetsRequest request{&output,kind_!=UiPopupKind::Ranking,false,kind_==UiPopupKind::UnitPanel || kind_==UiPopupKind::TopPanel || kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SaveMenu || kind_==UiPopupKind::LoadMenu || kind_==UiPopupKind::ExitConfirm || IsNotificationInputPanel() || IsPrivateMenuChild()};
        Call(&UiInputDispatch::CollectTargets,&request);
        if(kind_==UiPopupKind::MenuOptions){
            std::vector<UiInputTarget> sliders;UiInputTargetsRequest sliderRequest{&sliders};sliderRequest.slider=true;
            Call(&UiInputDispatch::CollectTargets,&sliderRequest);
            for(auto& slider:sliders){
                for(const auto& target:output)if(target.key==slider.key)
                    throw std::logic_error("Slider and click targets share an input identity");
                output.push_back(std::move(slider));
            }
        }
        AppendEconomicTargets(output,false);return output;
    }
    int SelectedPolicyTenet(){
        Require();RequirePolicyOwner();int result=-1;
        Call(&ReadSelectedPolicyTenet,&result);return result;
    }
    std::vector<UiInputTarget> ScrollTargets(){
        Require();std::vector<UiInputTarget> output;UiInputTargetsRequest request{&output,false,true};
        Call(&UiInputDispatch::CollectTargets,&request);AppendEconomicTargets(output,true);return output;
    }
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
    bool DispatchExternalWindowInput(const ZeroSisPresentation::BitmapInputEvent& event){
        Require();
        if(!externalRouting_ || windowPresentation_)
            throw std::logic_error("External window input requires a router-owned context without a private window");
        return DispatchWindowInput(event);
    }
#endif
    bool DispatchInput(UiInputKind kind,std::uint64_t key,double delta=0.0){
        Require();
        if(kind==UiInputKind::TextInput && kind_!=UiPopupKind::SaveMenu && kind_!=UiPopupKind::MapMenu)return false;
        if(!active_ || faulted_){
            if(kind_==UiPopupKind::ResearchTree)
                std::printf("RESEARCH_TREE_UI_INPUT=%u|%llu|%.17g|0|0|%u\n",static_cast<unsigned>(kind),
                    static_cast<unsigned long long>(key),delta,timerState_==TimerState::Held?1u:0u);
            return false;
        }
        if(kind_==UiPopupKind::EconomicOverview){
            unsigned slot=0;std::uint64_t localKey=0;
            if(DecodeEconomicKey(key,slot,localKey)){
                auto& child=economicChildren_[slot-1];
                if(!child || !child->active_ || !economicChildVisible_[slot-1])return false;
                const bool consumed=child->DispatchInput(kind,localKey,delta);
                std::printf("INTERACTIVE_ECONOMIC_OVERVIEW_CHILD_INPUT=%u|%llu|%u|%u|%u|%u\n",
                    static_cast<unsigned>(kind),static_cast<unsigned long long>(key),consumed?1u:0u,
                    active_?1u:0u,timerState_==TimerState::Held?1u:0u,slot);
                if(consumed){++revision_;const auto phase="child-updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());}
                return consumed;
            }
        }
        if(economicOwner_ && !economicOwner_->active_)return false;
        UiInputRequest request;request.kind=kind;request.key=key;request.delta=delta;
        if(IsNotificationInputPanel()){
            if(actionInfoInput_ || actionInfoReady_ || !actionInfoRequests_.empty() ||
               actionInfoOwner_!=game_->GetActivePlayer() || actionInfoTurn_!=game_->GetGameTurn())
                throw std::logic_error("ActionInfoPanel input lost its refreshed owner/turn scope");
            actionInfoInput_=true;actionInfoInputKind_=kind;
            try{Call(&UiInputDispatch::Dispatch,&request);}
            catch(...){actionInfoInput_=false;actionInfoRequests_.clear();throw;}
            actionInfoInput_=false;
            if(!actionInfoRequests_.empty()){
                if(!request.consumed || !scripts_.IsQuiescent() ||
                   (kind!=UiInputKind::LeftClick && kind!=UiInputKind::RightClick))
                    throw std::logic_error("ActionInfoPanel request escaped its completed original click callback");
                actionInfoReady_=true;
            }
            std::printf(kind_==UiPopupKind::NotificationPanel?"INTERACTIVE_NOTIFICATION_INPUT=%u|%llu|%u|%d|%d|%zu|0\n":"INTERACTIVE_ACTION_INFO_INPUT=%u|%llu|%u|%d|%d|%zu|0\n",
                static_cast<unsigned>(kind),static_cast<unsigned long long>(key),request.consumed?1u:0u,
                actionInfoOwner_,actionInfoTurn_,actionInfoRequests_.size());
            return request.consumed;
        }
        if(kind_==UiPopupKind::LoadMenu){
            RequireLoadMenuOwner();
            if(loadMenuInput_ || loadMenuReady_ || !loadMenuRequests_.empty() ||
               loadMenuCursorToken_!=0 || timerState_!=TimerState::Released)
                throw std::logic_error("LoadMenu input requires its refreshed timer-free child scope");
            const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
            loadMenuInput_=true;loadMenuInputKind_=kind;
            try{Call(&UiInputDispatch::Dispatch,&request);}
            catch(...){loadMenuInput_=false;loadMenuRequests_.clear();loadMenuReady_=false;RestoreLoadMenuCursor();throw;}
            loadMenuInput_=false;
            bool stillActive=false;Call(&ObserveActive,&stillActive);
            if(!scripts_.IsQuiescent() || timerState_!=TimerState::Released ||
               before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
                throw std::runtime_error("Original LoadMenu input changed gameplay or its parent-owned timer");
            if(!loadMenuRequests_.empty()){
                const bool loading=loadMenuRequests_.size()==2 &&
                    loadMenuRequests_.front().kind==LoadMenuRequest::Kind::Load &&
                    loadMenuRequests_.back().kind==LoadMenuRequest::Kind::Close;
                const bool closing=loadMenuRequests_.size()==1 && loadMenuRequests_.front().kind==LoadMenuRequest::Kind::Close;
                if(!request.consumed || stillActive || (!loading && !closing) ||
                   loadMenuCursorToken_!=(loading?1:0) ||
                   (kind!=UiInputKind::LeftClick && kind!=UiInputKind::KeyDown))
                    throw std::logic_error("LoadMenu request escaped its completed original callback");
                loadMenuReady_=true;
            }else if(!stillActive || loadMenuCursorToken_!=0)
                throw std::logic_error("LoadMenu closed or changed cursor without its original completed request");
            active_=stillActive;host_.popupVisible=true;
            if(request.consumed){
                if(active_){++revision_;const auto phase="updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());}
                else WriteSnapshot("closed");
            }
            std::printf("INTERACTIVE_LOAD_MENU_INPUT=%u|%llu|%u|%d|%d|%u|0|%zu|STATE_UNCHANGED\n",
                static_cast<unsigned>(kind),static_cast<unsigned long long>(key),request.consumed?1u:0u,
                gameMenuOwner_,gameMenuTurn_,active_?1u:0u,loadMenuRequests_.size());
            return request.consumed;
        }
        if(IsPrivateMenuChild()){
            RequirePrivateMenuOwner();
            if(privateMenuInput_ || mapMenuReady_ || !mapMenuRequests_.empty() || timerState_!=TimerState::Released)
                throw std::logic_error("Menu child input requires its refreshed timer-free owner scope");
            const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
            privateMenuInputId_.clear();
            if(kind==UiInputKind::LeftClick)for(const auto& target:InputTargets())
                if(target.key==key && !target.consumeMouseOnly)privateMenuInputId_=target.id;
            privateMenuInput_=true;privateMenuInputKind_=kind;privateMenuInputKey_=key;
            try{Call(&UiInputDispatch::Dispatch,&request);}
            catch(...){privateMenuInput_=false;privateMenuInputId_.clear();mapMenuRequests_.clear();mapMenuReady_=false;throw;}
            privateMenuInput_=false;privateMenuInputId_.clear();
            bool stillActive=false;Call(&ObserveActive,&stillActive);
            if(!scripts_.IsQuiescent() || timerState_!=TimerState::Released || before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
                throw std::runtime_error("Private menu input changed SDK gameplay or parent timer ownership");
            if(!mapMenuRequests_.empty()){
                if(mapMenuRequests_.size()!=1 || !request.consumed || (kind!=UiInputKind::LeftClick && kind!=UiInputKind::KeyDown) ||
                   ((mapMenuRequests_.front().kind==MapMenuRequest::Kind::Delete)!=stillActive))
                    throw std::logic_error("Map mutation escaped its original completed input/return boundary");
                mapMenuReady_=true;
            }
            active_=stillActive;host_.popupVisible=true;
            if(request.consumed){
                if(active_){++revision_;const auto phase="updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());}
                else WriteSnapshot("closed");
            }
            return request.consumed;
        }
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
            if(!gameMenuRequests_.empty()){
                if(gameMenuRequests_.size()!=1 || !request.consumed || kind!=UiInputKind::LeftClick || !stillActive ||
                   gameMenuRequests_.front().kind!=GameMenuRequest::Kind::OpenMapMenu || !saveMenuRequests_.empty())
                    throw std::logic_error("Nested map entry escaped the original SaveMenu callback");
                gameMenuReady_=true;
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
        if(kind_==UiPopupKind::TradeRoute && tradeRouteOwner_!=game_->GetActivePlayer())
            throw std::logic_error("TradeRoute input lost its active-player scope");
        if(kind_==UiPopupKind::ExitConfirm){
            RequireExitConfirmOwner();
            if(exitConfirmInput_ || exitConfirmClosed_ || gameMenuReady_ || !gameMenuRequests_.empty() || timerState_!=TimerState::Released)
                throw std::logic_error("ExitConfirm input requires its active timer-free original modal");
            const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
            exitConfirmYesInput_=false;exitConfirmCloseInput_=kind==UiInputKind::KeyDown && key==VK_ESCAPE;
            if(kind==UiInputKind::LeftClick){
                for(const auto& target:InputTargets()){
                    if(target.key==key && !target.consumeMouseOnly && (target.id=="Yes" || target.id=="No")){
                        exitConfirmYesInput_=target.id=="Yes";exitConfirmCloseInput_=true;
                    }
                }
            }
            exitConfirmInput_=true;exitConfirmInputKind_=kind;
            try{Call(&UiInputDispatch::Dispatch,&request);}
            catch(...){
                exitConfirmInput_=false;exitConfirmYesInput_=false;exitConfirmCloseInput_=false;
                gameMenuRequests_.clear();gameMenuReady_=false;throw;
            }
            exitConfirmInput_=false;exitConfirmYesInput_=false;exitConfirmCloseInput_=false;
            bool stillActive=false;Call(&ObserveActive,&stillActive);
            if(!scripts_.IsQuiescent() || timerState_!=TimerState::Released || exitConfirmClosed_==stillActive ||
               before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
                throw std::runtime_error("Original ExitConfirm input changed gameplay or failed its modal return contract");
            if(!gameMenuRequests_.empty()){
                const auto& command=gameMenuRequests_.front();
                if(gameMenuRequests_.size()!=1 || !request.consumed || kind!=UiInputKind::LeftClick || stillActive ||
                   command.kind!=GameMenuRequest::Kind::ExitGame || command.action!="ExitGame" ||
                   command.owner!=game_->GetActivePlayer() || command.turn!=game_->GetGameTurn())
                    throw std::logic_error("ExitConfirm exit escaped its completed original Yes callback");
                gameMenuReady_=true;
            }
            active_=stillActive;host_.popupVisible=active_;
            if(request.consumed){
                if(active_){++revision_;const auto phase="updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());}
                else WriteSnapshot("closed");
            }
            std::printf("INTERACTIVE_EXIT_CONFIRM_INPUT=%u|%llu|%u|%d|%d|%u|%zu|STATE_UNCHANGED\n",
                static_cast<unsigned>(kind),static_cast<unsigned long long>(key),request.consumed?1u:0u,
                gameMenuOwner_,gameMenuTurn_,active_?1u:0u,gameMenuRequests_.size());
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
            const bool mainMenuReturn=gameMenuRequests_.size()==1 && gameMenuRequests_.front().kind==GameMenuRequest::Kind::MainMenu;
            if(!scripts_.IsQuiescent() || gameMenuCursorToken_!=(mainMenuReturn?1:0) ||
               timerState_!=((stillActive && !mainMenuReturn)?TimerState::Held:TimerState::Released) ||
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
            if(mainMenuReturn)RestoreGameMenuCursor();
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
        if(kind_==UiPopupKind::TopPanel){
            if(topPanelInput_ || topPanelPopup_ || topPanelOwner_!=game_->GetActivePlayer() ||
               gameMenuReady_ || !gameMenuRequests_.empty())
                throw std::logic_error("TopPanel input lost its active-player scope");
            topPanelInput_=true;topPanelInputKind_=kind;
            try{Call(&UiInputDispatch::Dispatch,&request);}
            catch(...){topPanelInput_=false;topPanelPopup_.reset();gameMenuRequests_.clear();gameMenuReady_=false;throw;}
            topPanelInput_=false;
            if(!gameMenuRequests_.empty()){
                if(!request.consumed || kind!=UiInputKind::LeftClick || topPanelPopup_ ||
                   !scripts_.IsQuiescent() || gameMenuRequests_.front().owner!=game_->GetActivePlayer() ||
                   gameMenuRequests_.front().turn!=game_->GetGameTurn())
                    throw std::logic_error("TopPanel game-menu request escaped its completed original click callback");
                gameMenuReady_=true;
            }
            if(topPanelPopup_){
                auto popup=std::move(topPanelPopup_);
                if(!request.consumed || !scripts_.IsQuiescent() || !host_.addPopup || topPanelOwner_!=game_->GetActivePlayer())
                    throw std::logic_error("TopPanel popup escaped its completed original callback");
                host_.addPopup(*popup);
                std::printf("INTERACTIVE_TOP_PANEL_POPUP=%d|%d|%d\n",topPanelOwner_,static_cast<int>(popup->eButtonPopupType),popup->iData2);
            }
            return request.consumed;
        }
        if(kind_==UiPopupKind::UnitPanel){
            if(unitInput_ || unitAction_)throw std::logic_error("UnitPanel command scope is already occupied");
            unitInput_=true;
            try{Call(&UiInputDispatch::Dispatch,&request);}
            catch(...){unitInput_=false;unitAction_.reset();throw;}
            unitInput_=false;
            if(unitAction_){
                const auto command=*unitAction_;unitAction_.reset();
                if(!request.consumed || !scripts_.IsQuiescent())throw std::logic_error("UnitPanel action escaped its consumed callback");
                ValidateUnitSelection(command);
                auto checked=command;Call(&ValidateUnitAction,&checked);
                ValidateUnitSelection(command);
                game_->HandleAction(command.action);
                std::printf("INTERACTIVE_ORIGINAL_UNIT_ACTION=%d|%d|%d|%d\n",command.owner,command.unit,command.turn,command.action);
            }
            return request.consumed;
        }
        const bool cityInput=kind_==UiPopupKind::CityView;
        const bool productionInput=kind_==UiPopupKind::Production;
        const bool warInput=kind_==UiPopupKind::DeclareWar;
        const bool policyInput=kind_==UiPopupKind::SocialPolicy;
        const bool pantheonInput=kind_==UiPopupKind::Pantheon;
        if(pantheonInput){
            RequirePantheonOwner(true);
            if(pantheonInput_ || pantheonCommand_ || pendingPantheonSound_ || pantheonCommandsApplied_)
                throw std::logic_error("Pantheon input command scope is already occupied");
            pantheonEntryBelief_=-1;
            if(kind==UiInputKind::LeftClick){PantheonEntry entry{key,-1};Call(&ReadPantheonEntry,&entry);pantheonEntryBelief_=entry.belief;}
        }
        const unsigned policyCommandsAtEntry=policyCommandsApplied_;
        if(policyInput){
            RequirePolicyOwner();
            if(policyInput_ || policyCommand_ || pendingPolicySound_ || policyInfoCachePending_)
                throw std::logic_error("Policy input command scope is already occupied");
        }
        if(warInput && (warInput_ || !warCommands_.empty()))
            throw std::logic_error("War input command scope is already occupied");
        if(productionInput && (host_.deferCityPurchase || purchaseCommand_ || pendingPurchaseSound_))
            throw std::logic_error("Purchase input command scope is already bound");
        if(cityInput && (host_.deferCityTask || host_.deferCityOrder || !cityCommands_.empty() || pendingBuyTileSound_))
            throw std::logic_error("City input command scope is already bound");
        if(economicOwner_){economicInput_=true;economicInputKind_=kind;}
        try{
            if(warInput)warInput_=true;
            if(policyInput)policyInput_=true;
            if(pantheonInput)pantheonInput_=true;
            if(productionInput){
                host_.deferCityPurchase=[this](int city,UnitTypes unit,BuildingTypes building,ProjectTypes project,int yield){
                    RequirePurchaseInput(city);
                    if(purchaseCommand_)throw std::logic_error("Original production callback issued duplicate purchases");
                    LocalGameCommands::ValidateCityPurchaseEnvelope(city,unit,building,project,yield);
                    purchaseCommand_.reset(new PurchaseCommand{productionOwner_,city,static_cast<int>(unit),
                        static_cast<int>(building),static_cast<int>(project),yield,game_->GetGameTurn()});
                };
            }
            if(cityInput){
                host_.deferCityTask=[this](int city,TaskTypes task,int data1,int data2,bool option,bool alt,bool shift,bool control){
                    QueueCityCommand({CityCommandKind::Task,city,static_cast<int>(task),data1,data2,option,alt,shift,control});
                };
                host_.deferCityOrder=[this](int city,int index,bool swap){
                    QueueCityCommand({swap?CityCommandKind::SwapOrder:CityCommandKind::PopOrder,city,index});
                };
            }
            Call(&UiInputDispatch::Dispatch,&request);
        }
        catch(...){
            if(economicOwner_)economicInput_=false;
            if(warInput){warInput_=false;warCommands_.clear();}
            if(policyInput){policyInput_=false;policyCommand_.reset();pendingPolicySound_=false;policyInfoCachePending_=false;}
            if(pantheonInput){pantheonInput_=false;pantheonEntryBelief_=-1;pantheonCommand_.reset();pendingPantheonSound_=false;}
            if(cityInput){host_.deferCityTask={};host_.deferCityOrder={};cityCommands_.clear();pendingBuyTileSound_=false;}
            if(productionInput){host_.deferCityPurchase={};purchaseCommand_.reset();pendingPurchaseSound_=false;}
            throw;
        }
        if(warInput)warInput_=false;
        if(economicOwner_)economicInput_=false;
        if(policyInput)policyInput_=false;
        if(pantheonInput){pantheonInput_=false;pantheonEntryBelief_=-1;}
        if(cityInput){host_.deferCityTask={};host_.deferCityOrder={};}
        if(productionInput)host_.deferCityPurchase={};
        if(policyCommand_){
            auto command=std::move(policyCommand_);
            if(!request.consumed || !pendingPolicySound_ || !scripts_.IsQuiescent() || !host_.localCommands.IsQuiescent())
                throw std::logic_error("Policy command escaped its completed original callback");
            ValidatePolicyOwner(*command);
            Call(&ValidatePolicyCommand,command.get());
            ValidatePolicyOwner(*command);
            if(!scripts_.IsQuiescent())throw std::logic_error("Policy receiver cannot enter while Lua is on-stack");
            {std::unique_ptr<ICvNetMessageHandler1> receiver(core_->GetNetMessageHandler());
             if(!receiver)throw std::runtime_error("Policy command has no original SDK receiver");
             const auto owner=static_cast<PlayerTypes>(command->owner);
             if(command->ideology){
                 std::unique_ptr<ICvNetMessageHandler3> bnw(receiver->QueryInterface<ICvNetMessageHandler3>());
                 if(!bnw)throw std::runtime_error("Ideology change has no original BNW receiver");
                 bnw->ResponseChangeIdeology(owner);
             }else receiver->ResponseUpdatePolicies(owner,command->isPolicy,command->id,command->value);}
            ++policyCommandsApplied_;
            std::printf("INTERACTIVE_SOCIAL_POLICY_COMMAND=%d|%d|%u|%u|%d\n",command->owner,command->id,
                command->isPolicy?1u:0u,command->value?1u:0u,command->turn);
            pendingPolicySound_=false;
            host_.uiAudio->Request2D("AS2D_INTERFACE_POLICY");
            Call(&PolicyDirty,nullptr);
        }
        if(policyInput && (pendingPolicySound_ || policyInfoCachePending_))
            throw std::logic_error("Policy input left an uncommitted sound or display preference");
        if(purchaseCommand_){
            auto command=std::move(purchaseCommand_);
            if(!request.consumed || !pendingPurchaseSound_ || !scripts_.IsQuiescent() || !host_.localCommands.IsQuiescent() ||
               !host_.localSdkSessionBound || game_->IsGameMultiPlayer() ||
               command->owner!=game_->GetActivePlayer() || command->turn!=game_->GetGameTurn())
                throw std::logic_error("Purchase lost its completed original input and local SDK boundary");
            Call(&ValidatePurchaseCommand,command.get());
            if(!scripts_.IsQuiescent())throw std::logic_error("Purchase receiver cannot enter while Lua is on-stack");
            EngineServices engine(hostOwner_);
            engine.sendPurchase(command->city,static_cast<UnitTypes>(command->unit),static_cast<BuildingTypes>(command->building),
                static_cast<ProjectTypes>(command->project),command->yield);
            std::printf("INTERACTIVE_CITY_PURCHASE_DELIVERED=%d|%d|%d|%d|%d|%d|%d\n",command->owner,command->city,
                command->unit,command->building,command->project,command->yield,command->turn);
            pendingPurchaseSound_=false;
            host_.uiAudio->Request2D(command->yield==YIELD_GOLD?"AS2D_INTERFACE_CITY_SCREEN_PURCHASE":"AS2D_INTERFACE_FAITH_PURCHASE");
        }
        if(!cityCommands_.empty()){
            RequireEditableCity();
            // Validate the complete original callback batch before the first
            // mutation. Specialist clicks may first disable auto-assignment.
            for(auto& command:cityCommands_)Call(&ValidateCityCommand,&command);
            auto commands=std::move(cityCommands_);cityCommands_.clear();
            bool specialistAutomationDelivered=false;
            for(auto& command:commands){
                command.afterSpecialistAutomation=specialistAutomationDelivered;
                RequireEditableCity();Call(&ValidateCityCommand,&command);
                if(!scripts_.IsQuiescent())throw std::logic_error("City receiver cannot enter while Lua is on-stack");
                {std::unique_ptr<ICvNetMessageHandler1> receiver(core_->GetNetMessageHandler());
                 if(!receiver)throw std::runtime_error("City command has no original SDK receiver");
                 const auto owner=static_cast<PlayerTypes>(cityViewOwner_);
                 switch(command.kind){
                 case CityCommandKind::Task:receiver->ResponseCityDoTask(owner,command.city,static_cast<TaskTypes>(command.data1),command.data2,command.data3,command.option,command.alt,command.shift,command.control);break;
                 case CityCommandKind::BuyPlot:receiver->ResponseCityBuyPlot(owner,command.city,command.data1,command.data2);break;
                 case CityCommandKind::SellBuilding:receiver->ResponseSellBuilding(owner,command.city,static_cast<BuildingTypes>(command.data1));break;
                 case CityCommandKind::PopOrder:receiver->ResponseCityPopOrder(owner,command.city,command.data1);break;
                 case CityCommandKind::SwapOrder:receiver->ResponseCitySwapOrder(owner,command.city,command.data1);break;
                 }}
                specialistAutomationDelivered=command.kind==CityCommandKind::Task &&
                    command.data1==TASK_NO_AUTO_ASSIGN_SPECIALISTS && command.option;
                std::printf("INTERACTIVE_CITY_COMMAND_DELIVERED=%d|%d|%u|%d|%d|%d|%u|%u|%u|%u\n",cityViewOwner_,command.city,
                    static_cast<unsigned>(command.kind),command.data1,command.data2,command.data3,
                    command.option?1u:0u,command.alt?1u:0u,command.shift?1u:0u,command.control?1u:0u);
            }
            if(pendingBuyTileSound_){
                pendingBuyTileSound_=false;
                // Sound starts only after the original gameplay receiver, with
                // Lua off-stack. Device failures do not undo a purchased plot.
                host_.uiAudio->Request2D("AS2D_INTERFACE_BUY_TILE");
            }
            Call(&RefreshCityView,nullptr);
        }
        if(pendingCitySetting_){
            if(kind_!=UiPopupKind::CityView || !active_ || cityViewReadOnly_ || cityViewExit_ ||
               !scripts_.IsQuiescent() || !host_.localSdkSessionBound || game_->IsNetworkMultiPlayer() ||
               cityViewOwner_!=game_->GetActivePlayer() || frontend_.IsCityScreenViewingMode() || !frontend_.isCityScreenUp())
                throw std::logic_error("City setting requires the active local editable city boundary");
            {std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(cityViewOwner_)));
             std::unique_ptr<ICvCity1> city(frontend_.getHeadSelectedCity());
             if(!player || !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive() || !city || city->IsPuppet() ||
                city->GetOwner()!=cityViewOwner_ || city->GetID()!=cityViewCity_)
                 throw std::logic_error("City setting lost its eligible active human city");}
            const int operation=pendingCitySetting_,value=pendingCitySettingValue_;pendingCitySetting_=0;
            {std::unique_ptr<ICvNetMessageHandler1> receiver(core_->GetNetMessageHandler());
             if(!receiver)throw std::runtime_error("City setting has no original SDK receiver");
             if(operation==1)receiver->ResponseSetCityAIFocus(static_cast<PlayerTypes>(cityViewOwner_),cityViewCity_,static_cast<CityAIFocusTypes>(value));
             else receiver->ResponseSetCityAvoidGrowth(static_cast<PlayerTypes>(cityViewOwner_),cityViewCity_,value!=0);}
            Call(&RefreshCityView,nullptr);
            std::printf("INTERACTIVE_CITY_SETTING_APPLIED=%d|%d|%d|%d\n",cityViewOwner_,cityViewCity_,operation,value);
        }
        if(researchDirtyPending_){
            researchDirtyPending_=false;
            Call(&ResearchDirty,nullptr);
            ++researchDirtyDispatches_;
            std::printf("RESEARCH_TREE_UI_RESEARCH_DIRTY=%u\n",researchDirtyDispatches_);
        }
        bool stillActive=false;Call(&ObserveActive,&stillActive);
        if(kind_==UiPopupKind::CityView && !stillActive){
            if(!cityViewExit_ || frontend_.isCityScreenUp() || frontend_.IsCityScreenViewingMode())
                throw std::logic_error("CityView closed without its original exit event and selection cleanup");
            std::unique_ptr<ICvCity1> selected(frontend_.getHeadSelectedCity());
            if(selected)throw std::logic_error("CityView exit retained a selected city");
            std::printf("INTERACTIVE_CITY_VIEW_CLOSED=%d|%d|0|0|0\n",cityViewOwner_,cityViewCity_);
        }
        if(pendingCaptureAction_!=0){
            if(kind_!=UiPopupKind::CityCapture || stillActive || !scripts_.IsQuiescent())
                throw std::logic_error("Captured-city command requires a completed original popup callback");
            const int action=pendingCaptureAction_;pendingCaptureAction_=0;
            EngineServices engine(hostOwner_);
            if(action==1)engine.sendDoTask(captureCity_,pendingCaptureTask_,-1,-1,false,false,false,false);
            else engine.SendLiberateMinor(static_cast<PlayerTypes>(captureLiberated_),captureCity_);
            captureDecisionDone_=true;
            std::printf("INTERACTIVE_CITY_CAPTURE_DECISION=%d|%d|%d|%d\n",captureOwner_,captureCity_,action,
                action==1?static_cast<int>(pendingCaptureTask_):captureLiberated_);
        }
        if(pendingLeaderLeave_){
            if(kind_!=UiPopupKind::LeaderHead || !leaderMessage_ || leaderDecisionDone_ || stillActive ||
               host_.leaderRootUp || !scripts_.IsQuiescent() || leaderMessage_->receiver!=game_->GetActivePlayer())
                throw std::logic_error("Leader completion requires its returned original UI and quiescent receiver");
            std::unique_ptr<ICvPlayer1> receiver(game_->GetPlayer(static_cast<PlayerTypes>(leaderMessage_->receiver)));
            if(!receiver || !receiver->IsAlive() || !receiver->IsHuman())
                throw std::logic_error("Leader completion lost its living human receiver");
            pendingLeaderLeave_=false;
            receiver->ActiveDiplomacyRequestComplete();receiver.reset();leaderDecisionDone_=true;
            std::printf("INTERACTIVE_DIPLOMACY_COMPLETE=%d|%d|%d|%d|%d\n",leaderMessage_->receiver,
                static_cast<int>(leaderMessage_->player),static_cast<int>(leaderMessage_->state),
                static_cast<int>(leaderMessage_->animation),leaderMessage_->data1);
        }
        const auto expected=RetainsTimer() && stillActive?TimerState::Held:TimerState::Released;
        if(timerState_!=expected)throw std::runtime_error("UI input left an invalid popup timer state");
        active_=stillActive;
        if(!economicOwner_)host_.popupVisible=active_;
        if(pantheonCommand_){
            auto command=std::move(pantheonCommand_);
            if(!request.consumed || active_ || timerState_!=TimerState::Released || !pendingPantheonSound_ ||
               pantheonUnitPanelHidden_ || !scripts_.IsQuiescent() || !host_.localCommands.IsQuiescent() ||
               command->owner!=pantheonOwner_ || command->turn!=pantheonTurn_ ||
               command->generation!=pantheonGeneration_ || command->generation!=sequence_ || command->revision!=revision_)
                throw std::logic_error("Pantheon command escaped its completed original confirmation callback");
            RequirePantheonOwner(false);pendingPantheonSound_=false;
            if(pantheonCommit_)throw std::logic_error("Pantheon transport is already in flight");
            pantheonCommit_=command.get();
            try{host_.localCommands.SendFoundPantheon(static_cast<PlayerTypes>(command->owner),static_cast<BeliefTypes>(command->belief));}
            catch(...){pantheonCommit_=nullptr;throw;}
            pantheonCommit_=nullptr;
            ++pantheonCommandsApplied_;
            if(!host_.uiAudio)throw std::logic_error("Pantheon policy cue has no configured audio service");
            host_.uiAudio->Request2D("AS2D_INTERFACE_POLICY");
            std::printf("INTERACTIVE_PANTHEON_COMMAND=%d|%d|%d|%u\n",command->owner,command->belief,command->turn,command->generation);
        }
        if(pantheonInput && pendingPantheonSound_)
            throw std::logic_error("Pantheon input left an uncommitted policy cue");
        if(kind_==UiPopupKind::EconomicOverview)ApplyEconomicVisibility(false);
        if(warInput){
            try{CommitWarCommands(request.consumed,stillActive);}
            catch(...){warCommands_.clear();Fault();throw;}
        }
        if(request.consumed){
            if(active_){
                ++revision_;
                if(!economicOwner_){const auto phase="updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());}
            }
            else if(!economicOwner_){WriteSnapshot("closed");host_.Record("ui-popup-closed:"+std::to_string(sequence_)+":"+std::to_string(game_->GetGameTurn()));}
        }
        if(kind_==UiPopupKind::ResearchTree)
            std::printf("RESEARCH_TREE_UI_INPUT=%u|%llu|%.17g|%u|%u|%u\n",static_cast<unsigned>(kind),
                static_cast<unsigned long long>(key),delta,request.consumed?1u:0u,active_?1u:0u,
                timerState_==TimerState::Held?1u:0u);
        if(policyInput)
            std::printf("INTERACTIVE_SOCIAL_POLICY_INPUT=%u|%llu|%.17g|%u|%u|%u|%d|%u\n",static_cast<unsigned>(kind),
                static_cast<unsigned long long>(key),delta,request.consumed?1u:0u,active_?1u:0u,
                timerState_==TimerState::Held?1u:0u,game_->GetGameTurn(),policyCommandsApplied_!=policyCommandsAtEntry?1u:0u);
        return request.consumed;
    }
    // Exact stock fixture: use actual CanTrain choices, then dispatch the real
    // retained button key and its stock enum/item void payload.
    int ChooseProductionUnit(int cityID){
        Require();
        if(kind_!=UiPopupKind::Production || !active_)throw std::logic_error("Production fixture requires a shown official context");
        const auto beforeChoice=SdkStateSnapshot::Capture(host_);
        const auto previousEvents=host_.Events();
        std::fprintf(stdout,"PRODUCTION_UI_INPUT_STAGE=legal-begin\n");std::fflush(stdout);
        ProductionChoice choice{cityID,-1};Call(&LegalProductionUnit,&choice);
        if(SdkStateSnapshot::Capture(host_)!=beforeChoice || host_.Events()!=previousEvents)
            throw std::runtime_error("Out-of-input UI purchase changed gameplay or commands");
        std::puts("PRODUCTION_UI_OUT_OF_INPUT_PURCHASE_REJECTED_BEFORE_MUTATION=true");
        std::fprintf(stdout,"PRODUCTION_UI_INPUT_STAGE=legal-end|unit=%d\n",choice.unit);std::fflush(stdout);
        const auto targets=InputTargets();std::uint64_t key=0;
        std::fprintf(stdout,"PRODUCTION_UI_INPUT_STAGE=targets-end|count=%zu\n",targets.size());std::fflush(stdout);
        for(const auto& target:targets)if(target.hasVoidPayload && target.void1==6 && target.void2==choice.unit){
            if(key)throw std::runtime_error("Production fixture has duplicate legal unit buttons");key=target.key;
        }
        std::fprintf(stdout,"PRODUCTION_UI_INPUT_STAGE=dispatch-begin|key=%llu\n",static_cast<unsigned long long>(key));std::fflush(stdout);
        if(!key)throw std::runtime_error("Official production fixture has no legal retained unit button");
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
        if(windowPresentation_){
            shownSnapshot_=WriteSnapshot("window");
            std::printf("UI_WINDOW_EXPECTED_CONTROL=%u|%llu|%d|%d\n",sequence_,
                static_cast<unsigned long long>(key),cityID,choice.unit);
            std::vector<std::uint64_t> keys;for(const auto& target:targets)keys.push_back(target.key);
            try{
                if(liveProduction_){
                    UiWindowPresentation::ServeProduction(sequence_,game_->GetGameTurn(),directory_,shownSnapshot_,
                        [this](){return SnapshotText();},[this](){return active_;},
                        [this](const ZeroSisPresentation::BitmapInputEvent& event){return DispatchWindowInput(event);},
                        [this](){std::vector<std::uint64_t> output;for(const auto& target:InputTargets())output.push_back(target.key);return output;},
                        [this](){std::vector<std::uint64_t> output;for(const auto& target:ScrollTargets())output.push_back(target.key);return output;},
                        [this](unsigned revision){
                            // Explicit owner clock for this recorded input profile; it
                            // advances presentation animation without a GameCore update.
                            if(active_)Tick(frameTime_+0.125);
                            const auto phase="live-"+std::to_string(revision);WriteSnapshot(phase.c_str());
                            return directory_+L"\\ui-popup-"+std::to_wstring(sequence_)+L"-live-"+std::to_wstring(revision)+L".json";
                        });
                }else UiWindowPresentation::Serve(sequence_,game_->GetGameTurn(),directory_,shownSnapshot_,keys,
                    [this](){return SnapshotText();},[this](){return active_;},
                    [this](const ZeroSisPresentation::BitmapInputEvent& event){return DispatchWindowInput(event);},
                    displayResize_,refreshClosed_,[this](){
                        std::vector<std::uint64_t> output;
                        for(const auto& target:InputTargets())output.push_back(target.key);return output;
                    },true,key);
            }catch(...){presentationFailed_=true;throw;}
        }else
#endif
        if(!DispatchInput(UiInputKind::LeftClick,key))
            throw std::runtime_error("Official production button did not accept its retained input");
        if(active_)
            throw std::runtime_error("Official replace-production button did not accept and close its input");
        std::fprintf(stdout,"PRODUCTION_UI_INPUT_STAGE=dispatch-end\n");std::fflush(stdout);
        std::printf("PRODUCTION_UI_SELECTION=%d,%d,%llu\n",cityID,choice.unit,static_cast<unsigned long long>(key));
        return choice.unit;
    }
    // Keep the official TechSelected callback and its normal research tuple.
    int ChooseResearchTechnology(){
        Require();
        if(kind_!=UiPopupKind::Research || !active_)
            throw std::logic_error("Research selection requires a shown official TechPopup");
        ResearchChoice choice{static_cast<int>(game_->GetActivePlayer()),-1};
        const auto before=SdkStateSnapshot::Capture(host_);
        Call(&LegalResearchTechnology,&choice);
        if(SdkStateSnapshot::Capture(host_)!=before)
            throw std::runtime_error("Research legality lookup changed SDK gameplay state");
        const auto targets=InputTargets();std::uint64_t key=0;
        for(const auto& target:targets)if(target.id=="TechButton" && target.hasVoidPayload && target.void1==choice.tech && target.void2==0){
            if(key)throw std::runtime_error("Research has duplicate retained technology buttons");
            key=target.key;
        }
        if(!key)throw std::runtime_error("Legal research has no actual retained TechButton");
        std::printf("RESEARCH_UI_LEGAL_CHOICE=%d,%d,%llu\n",choice.player,choice.tech,static_cast<unsigned long long>(key));
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
        if(windowPresentation_){
            WriteSnapshot("window");
            const auto snapshot=SnapshotText();
            std::vector<std::uint64_t> keys;for(const auto& target:targets)keys.push_back(target.key);
            std::printf("UI_WINDOW_EXPECTED_CONTROL=%u|%llu|%d|%d\n",sequence_,static_cast<unsigned long long>(key),choice.player,choice.tech);
            try{UiWindowPresentation::Serve(sequence_,game_->GetGameTurn(),directory_,snapshot,keys,
                [this](){return SnapshotText();},[this](){return active_;},
                [this](const ZeroSisPresentation::BitmapInputEvent& event){return DispatchWindowInput(event);},
                displayResize_,refreshClosed_,[this](){std::vector<std::uint64_t> keys;for(const auto& target:InputTargets())keys.push_back(target.key);return keys;},
                true,key,true);
            }catch(...){presentationFailed_=true;throw;}
        }else
#endif
        if(!DispatchInput(UiInputKind::LeftClick,key))
            throw std::runtime_error("Official TechSelected did not accept its retained button");
        if(active_)throw std::runtime_error("Official TechSelected did not close its popup");
        std::printf("RESEARCH_UI_SELECTION=%d,%d,%llu\n",choice.player,choice.tech,static_cast<unsigned long long>(key));
        return choice.tech;
    }
    CvPopupInfo OpenResearchTree(){
        Require();
        if(kind_!=UiPopupKind::Research || !active_ || researchTreeRequested_)
            throw std::logic_error("Research-tree handoff requires a shown original TechPopup");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        std::uint64_t key=0;
        for(const auto& target:InputTargets())if(target.id=="OpenTTButton"){
            if(key)throw std::runtime_error("Research tree has duplicate original open buttons");
            key=target.key;
        }
        if(!key || !DispatchInput(UiInputKind::LeftClick,key) || active_ || !researchTreeRequested_ ||
           timerState_!=TimerState::Released)
            throw std::runtime_error("Original OpenTechTree did not close and request its deferred tree context");
        if(SdkStateSnapshot::Capture(host_)!=before || SynchronousRandomSeed()!=seed)
            throw std::runtime_error("Original research-tree handoff changed SDK gameplay or RNG");
        std::printf("RESEARCH_TREE_UI_HANDOFF=%llu|%d|%d\n",static_cast<unsigned long long>(key),
                    static_cast<int>(BUTTONPOPUP_TECH_TREE),requestedTreeSteal_);
        researchTreeRequested_=false;
        return CvPopupInfo(BUTTONPOPUP_TECH_TREE,-1,requestedTreeSteal_);
    }
    int ChooseResearchTreeTechnology(){
        Require();
        if(kind_!=UiPopupKind::ResearchTree || !active_ || timerState_!=TimerState::Held)
            throw std::logic_error("Research-tree selection requires its active original context");
        ResearchChoice choice{static_cast<int>(game_->GetActivePlayer()),-1};
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        Call(&LegalResearchTechnology,&choice);
        if(SdkStateSnapshot::Capture(host_)!=before || SynchronousRandomSeed()!=seed)
            throw std::runtime_error("Research-tree legality lookup changed SDK gameplay or RNG");
        std::uint64_t key=0;
        for(const auto& target:InputTargets())if(target.id=="TechButton" && target.hasVoidPayload &&
           target.void1==choice.tech && target.void2==0){
            if(key)throw std::runtime_error("Research tree has duplicate retained technology buttons");
            key=target.key;
        }
        if(!key || !DispatchInput(UiInputKind::LeftClick,key) || !active_ ||
           timerState_!=TimerState::Held || researchDirtyDispatches_!=1)
            throw std::runtime_error("Original tree selection did not remain shown and refresh from its SDK command");
        int selected=-1;Call(&CurrentResearch,&selected);
        if(selected!=choice.tech || SynchronousRandomSeed()!=seed)
            throw std::runtime_error("Research-tree command did not select the exact SDK technology or preserve RNG");
        std::printf("RESEARCH_TREE_UI_SELECTION=%d,%d,%llu\n",choice.player,choice.tech,static_cast<unsigned long long>(key));
        std::puts("RESEARCH_TREE_UI_SELECTION_REMAINS_OPEN=true\nRESEARCH_TREE_UI_TIMER_AFTER_SELECTION=1");
        const auto afterSelection=SdkStateSnapshot::Capture(host_);
        TreeScrollObservation initial;Call(&ObserveTreeScroll,&initial);
        if(initial.offset!=0.0 || initial.maximum<240.0)
            throw std::runtime_error("Original research tree has no measurable horizontal range for this fixture");
        if(!DispatchInput(UiInputKind::Scroll,initial.key,240.0))
            throw std::runtime_error("Research tree rejected its horizontal scroll input");
        TreeScrollObservation moved;Call(&ObserveTreeScroll,&moved);
        if(moved.key!=initial.key || moved.offset!=240.0 || moved.maximum!=initial.maximum)
            throw std::runtime_error("Research-tree horizontal scroll did not move its original viewport");
        if(!DispatchInput(UiInputKind::Scroll,initial.key,-240.0))
            throw std::runtime_error("Research tree rejected its horizontal reset input");
        TreeScrollObservation reset;Call(&ObserveTreeScroll,&reset);
        if(reset.key!=initial.key || reset.offset!=0.0 || reset.maximum!=initial.maximum ||
           SdkStateSnapshot::Capture(host_)!=afterSelection || SynchronousRandomSeed()!=seed)
            throw std::runtime_error("Research-tree scroll/reset changed gameplay, RNG or its measured range");
        std::printf("RESEARCH_TREE_UI_HORIZONTAL_SCROLL=%llu|%.17g|%.17g|%.17g|%.17g\n",
                    static_cast<unsigned long long>(initial.key),initial.offset,moved.offset,reset.offset,initial.maximum);
        if(!DispatchInput(UiInputKind::KeyDown,27) || active_ || timerState_!=TimerState::Released)
            throw std::runtime_error("Original tree Escape did not close and balance its timer");
        if(DispatchInput(UiInputKind::LeftClick,key) || DispatchInput(UiInputKind::KeyDown,27))
            throw std::runtime_error("Closed research tree accepted stale input");
        if(SdkStateSnapshot::Capture(host_)!=afterSelection || SynchronousRandomSeed()!=seed)
            throw std::runtime_error("Research-tree close/stale input changed SDK gameplay or RNG");
        std::puts("RESEARCH_TREE_UI_STALE_INPUT_REJECTED=true\nRESEARCH_TREE_UI_TIMER_SEMAPHORE=0");
        return choice.tech;
    }
private:
    enum class WarCommandKind {Change,Diplomacy,Move,Mission,InterfaceMode};
    struct WarCommand {WarCommandKind kind;int a=0,b=0,c=0,d=0;};
    void ReleaseWarResources(){
        if(warCommandsVm_){scripts_.FreeLuaThread(warCommandsVm_);warCommandsVm_=nullptr;}
        scratchDeal_.reset();
        if(ownsScratchDeal_){deals_->DestroyDeal(scratchDealId_);ownsScratchDeal_=false;}
        deals_.reset();scriptUtility_.reset();warCommands_.clear();warInput_=false;
    }
    void EnsureDeals(){
        if(kind_!=UiPopupKind::DeclareWar)throw std::logic_error("Current deals require the original DeclareWar context");
        if(!deals_)deals_.reset(game_->GetGameDeals());
        if(!deals_)throw std::runtime_error("SDK current-deal interface is unavailable");
    }
    void EnsureScratchDeal(){
        EnsureDeals();
        if(!ownsScratchDeal_){scratchDealId_=deals_->CreateDeal();ownsScratchDeal_=true;}
        if(!scratchDeal_)scratchDeal_.reset(deals_->GetDeal(scratchDealId_));
        if(!scriptUtility_)scriptUtility_.reset(core_->GetScriptSystemUtility());
        if(!scratchDeal_ || !scriptUtility_)throw std::runtime_error("SDK scratch-deal Lua bridge is unavailable");
    }
    static int PushScratchDeal(lua_State* state){
        auto& self=*static_cast<UiPopupContext*>(lua_touserdata(state,1));
        self.scriptUtility_->PushCvDealInstance(state,self.scratchDeal_.get());
        lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_SCRATCH_RESULT");return 0;
    }
    void PrepareWarInput(const OwnedPopupInfo& input){
        if(!externalRouting_ || game_->IsGameMultiPlayer() || !host_.localSdkSessionBound ||
           input.Option(0) || input.Data(0)<0 || input.Data(0)>=MAX_TEAMS || input.Data(1)<0 || input.Data(2)<0)
            throw std::invalid_argument("DeclareWar world input has an invalid local team/plot envelope");
        warOwner_=game_->GetActivePlayer();warTurn_=game_->GetGameTurn();warRival_=input.Data(0);
        warX_=input.Data(1);warY_=input.Data(2);warRange_=input.type==BUTTONPOPUP_DECLAREWARRANGESTRIKE;
        {std::unique_ptr<ICvUnit1> selected(frontend_.GetHeadSelectedUnit());
         if(!selected)throw std::logic_error("DeclareWar lost the selected world unit");
         warUnit_=selected->GetID();}
        {std::unique_ptr<ICvMap1> map(core_->GetMap());
         if(!map || warX_>=map->GetGridWidth() || warY_>=map->GetGridHeight())
             throw std::invalid_argument("DeclareWar target lies outside the current map");}
        warDecisionDone_=false;warCommands_.clear();ValidateWarIdentity();
        std::printf("INTERACTIVE_DECLARE_WAR_INPUT=%d|%d|%d|%d|%d|%d|%u\n",
            warOwner_,warUnit_,warTurn_,warRival_,warX_,warY_,warRange_?1u:0u);
    }
    void ValidateWarIdentity(){
        if(kind_!=UiPopupKind::DeclareWar || !host_.localSdkSessionBound || game_->IsGameMultiPlayer() ||
           game_->GetActivePlayer()!=warOwner_ || game_->GetGameTurn()!=warTurn_ || warDecisionDone_)
            throw std::logic_error("DeclareWar callback no longer owns its original human turn");
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(warOwner_)));
        std::unique_ptr<ICvUnit1> unit(frontend_.GetHeadSelectedUnit());
        const auto selected=host_.localSelection.Snapshot();
        std::unique_ptr<ICvTeam1> rival(core_->GetTeam(static_cast<TeamTypes>(warRival_)));
        if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive() ||
           !unit || unit->GetOwner()!=warOwner_ || unit->GetID()!=warUnit_ || unit->IsDelayedDeathExported() ||
           selected.size()!=1 || selected.front().first!=warOwner_ || selected.front().second!=warUnit_ ||
           !rival || !rival->IsAlive() || rival->IsAtWar(player->GetTeam()) || player->GetTeam()==warRival_)
            throw std::logic_error("DeclareWar selection or rival identity changed");
    }
    void RequireWarInput(){
        if(!warInput_ || !dispatching_ || !active_ || faulted_ || timerState_!=TimerState::Held)
            throw std::logic_error("War command requires its original active input callback");
        ValidateWarIdentity();
        if(warCommands_.size()>=4)throw std::length_error("DeclareWar callback exceeded its stock command sequence");
    }
    void CommitWarCommands(bool consumed,bool stillActive){
        if(warCommands_.empty())return;
        if(!consumed || stillActive || !scripts_.IsQuiescent() || timerState_!=TimerState::Released)
            throw std::logic_error("War command escaped its completed original confirmation callback");
        ValidateWarIdentity();
        std::unique_ptr<ICvTeam1> rival(core_->GetTeam(static_cast<TeamTypes>(warRival_)));
        const auto leader=rival->GetLeaderID();
        std::unique_ptr<ICvPlayer1> other(game_->GetPlayer(leader));
        if(!other || !other->IsAlive())throw std::logic_error("DeclareWar has no live rival leader");
        const bool diplomaticResponse=!other->IsMinorCiv() && !other->IsHuman();
        std::size_t index=0;
        const auto expect=[&](WarCommandKind kind,int a,int b=0,int c=0,int d=0){
            if(index>=warCommands_.size())throw std::logic_error("Original war callback omitted a required command");
            const auto& command=warCommands_[index++];
            if(command.kind!=kind || command.a!=a || command.b!=b || command.c!=c || command.d!=d)
                throw std::logic_error("Original war callback changed its command order or tuple");
        };
        expect(WarCommandKind::Change,warRival_,1);
        if(diplomaticResponse)expect(WarCommandKind::Diplomacy,FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR,leader);
        if(warRange_){
            expect(WarCommandKind::Mission,GAMEMESSAGE_PUSH_MISSION,core_->GetInfoTypeForString("MISSION_RANGE_ATTACK",true),warX_,warY_);
            expect(WarCommandKind::InterfaceMode,INTERFACEMODE_SELECTION);
        }else expect(WarCommandKind::Move,warX_,warY_);
        if(index!=warCommands_.size())throw std::logic_error("Original war callback included an extra command");
        // Release borrowed adapters before declaration can change diplomacy,
        // current deals, or the target unit. Re-resolve each gameplay command.
        other.reset();rival.reset();
        auto commands=std::move(warCommands_);warCommands_.clear();
        for(const auto& command:commands){
            if(command.kind==WarCommandKind::Change){
                EngineServices engine(hostOwner_);engine.sendChangeWar(static_cast<TeamTypes>(command.a),true);
            }else if(command.kind==WarCommandKind::Diplomacy){
                ExecuteWarSdk("Game.DoFromUIDiploEvent("+std::to_string(command.a)+","+
                    std::to_string(command.b)+",0,0)");
            }else if(command.kind==WarCommandKind::Move || command.kind==WarCommandKind::Mission){
                const ConfirmedWarContinuation continuation{warOwner_,warUnit_,warTurn_,warX_,warY_,warRange_};
                if(host_.confirmedWarContinuation)throw std::logic_error("Confirmed war continuation reentered");
                struct ContinuationScope final {
                    HostState& host;
                    ContinuationScope(HostState& value,const ConfirmedWarContinuation& command):host(value){host.confirmedWarContinuation=&command;}
                    ~ContinuationScope(){host.confirmedWarContinuation=nullptr;}
                } scope(host_,continuation);
                if(command.kind==WarCommandKind::Move){
                    std::unique_ptr<ICvMap1> map(core_->GetMap());
                    std::unique_ptr<ICvPlot1> plot(map?map->GetPlot(command.a,command.b):nullptr);
                    if(!plot)throw std::runtime_error("Confirmed war movement lost its map plot");
                    game_->SelectionListMove(plot.get(),false);
                }else{
                    ExecuteWarSdk("Game.SelectionListGameNetMessage("+std::to_string(command.a)+","+
                        std::to_string(command.b)+","+std::to_string(command.c)+","+std::to_string(command.d)+",0,false,false)");
                }
            }else frontend_.setInterfaceMode(static_cast<InterfaceModeTypes>(command.a));
            std::printf("INTERACTIVE_DECLARE_WAR_COMMAND=%u|%d|%d|%d|%d\n",
                static_cast<unsigned>(command.kind),command.a,command.b,command.c,command.d);
        }
        warDecisionDone_=true;
        std::printf("INTERACTIVE_DECLARE_WAR_CONFIRMED=%d|%d|%d|%d|%d|%u\n",
            warOwner_,warUnit_,warRival_,warX_,warY_,warRange_?1u:0u);
    }
    void ExecuteWarSdk(const std::string& code){
        if(!warCommandsVm_ || !scripts_.IsQuiescent())throw std::logic_error("War SDK call requires its post-callback VM");
        if(!scripts_.Execute(warCommandsVm_,code.data(),code.size(),"original-war-command"))
            throw std::runtime_error(scripts_.LastError());
    }
    struct EconomicVisibilityRequest {bool visible=false,initialize=false;};
    static constexpr std::uint64_t EconomicGeneralKeyBase=1ULL<<48;
    static constexpr std::uint64_t EconomicHappinessKeyBase=2ULL<<48;
    static constexpr std::uint64_t EmbeddedKeySpan=1ULL<<32;
    static bool DecodeEconomicKey(std::uint64_t key,unsigned& slot,std::uint64_t& localKey) noexcept {
        const auto decode=[&](std::uint64_t base,unsigned candidate){
            if(key<base || key-base>=EmbeddedKeySpan)return false;
            slot=candidate;localKey=key-base;return localKey!=0;
        };
        return decode(EconomicGeneralKeyBase,1) || decode(EconomicHappinessKeyBase,2);
    }
    void AppendEconomicTargets(std::vector<UiInputTarget>& output,bool scroll){
        if(kind_!=UiPopupKind::EconomicOverview || !active_)return;
        for(unsigned slot=1;slot<=2;++slot){
            auto& child=economicChildren_[slot-1];
            if(!child || !child->active_ || !economicChildVisible_[slot-1])continue;
            auto targets=scroll?child->ScrollTargets():child->InputTargets();
            const auto base=slot==1?EconomicGeneralKeyBase:EconomicHappinessKeyBase;
            for(auto& target:targets){
                if(target.key==0 || target.key>=EmbeddedKeySpan || base>UiInputDispatch::MaxExactLuaInteger-target.key)
                    throw std::logic_error("Embedded EconomicOverview input key exceeds its exact namespace");
                target.key+=base;output.push_back(std::move(target));
            }
        }
        if(output.size()>UiInputDispatch::MaxTargets)
            throw std::length_error("EconomicOverview input targets exceed the native bound");
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
    bool IsResearch() const {return kind_==UiPopupKind::Research || kind_==UiPopupKind::ResearchTree;}
    bool RetainsTimer() const {return kind_==UiPopupKind::GoodyHutReward || kind_==UiPopupKind::Pantheon || kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SocialPolicy || kind_==UiPopupKind::TradeRoute || kind_==UiPopupKind::EconomicOverview || kind_==UiPopupKind::Ranking || kind_==UiPopupKind::ResearchTree || kind_==UiPopupKind::TechAward || kind_==UiPopupKind::DeclareWar;}
    bool SupportsExternalPointerScroll() const {
        return externalRouting_ && (kind_==UiPopupKind::GoodyHutReward || kind_==UiPopupKind::Pantheon || kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SaveMenu || kind_==UiPopupKind::LoadMenu || kind_==UiPopupKind::ExitConfirm || kind_==UiPopupKind::Production || kind_==UiPopupKind::Research || kind_==UiPopupKind::ResearchTree || kind_==UiPopupKind::CityCapture || kind_==UiPopupKind::LeaderHead || kind_==UiPopupKind::CityView || kind_==UiPopupKind::TechAward || kind_==UiPopupKind::UnitPanel || kind_==UiPopupKind::DeclareWar || kind_==UiPopupKind::TopPanel || IsNotificationInputPanel() || kind_==UiPopupKind::TradeRoute || kind_==UiPopupKind::SocialPolicy || kind_==UiPopupKind::EconomicOverview || kind_==UiPopupKind::EconomicGeneral || kind_==UiPopupKind::EconomicHappiness || IsPrivateMenuChild());
    }
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
    unsigned long RandomSeed() {
        std::unique_ptr<ICvRandom1> random(game_->GetRandomNumberGenerator());
        if(!random)throw std::runtime_error("UI input synchronous RNG interface is missing");
        return random->GetSeed();
    }
    bool DispatchWindowInput(const ZeroSisPresentation::BitmapInputEvent& event) {
        Require();
        // Keep right input on this UI surface until its original right-click
        // callbacks are connected; never reinterpret it as a map command.
        if(event.kind==ZeroSisPresentation::BitmapInputKind::ControlRightClick && !IsNotificationInputPanel())return false;
        const auto before=RandomSeed();const bool held=timerState_==TimerState::Held;
        UiInputRequest request;
        bool mappedSlider=false;
        if(kind_==UiPopupKind::MenuOptions && (event.kind==ZeroSisPresentation::BitmapInputKind::ControlDrag ||
                                              event.kind==ZeroSisPresentation::BitmapInputKind::ControlClick)){
            for(const auto& target:InputTargets())if(target.key==event.controlKey && target.slider){
                request.kind=UiInputKind::SliderValue;request.key=target.key;
                if(!ZeroSisPresentation::NormalizeHorizontalSlider(target.x,target.y,target.width,target.height,
                    event.logicalX,event.logicalY,event.kind==ZeroSisPresentation::BitmapInputKind::ControlDrag,request.delta))return false;
                mappedSlider=true;break;
            }
        }
        if(event.kind==ZeroSisPresentation::BitmapInputKind::ControlDrag && !mappedSlider)return false;
        if(!mappedSlider)switch(event.kind){
        case ZeroSisPresentation::BitmapInputKind::ControlClick:request.kind=UiInputKind::LeftClick;request.key=event.controlKey;break;
        case ZeroSisPresentation::BitmapInputKind::ControlRightClick:request.kind=UiInputKind::RightClick;request.key=event.controlKey;break;
        case ZeroSisPresentation::BitmapInputKind::TextInput:
            if(kind_!=UiPopupKind::SaveMenu && kind_!=UiPopupKind::MapMenu)return false;
            request.kind=UiInputKind::TextInput;request.key=event.unicodeScalar;break;
        case ZeroSisPresentation::BitmapInputKind::KeyDown:request.kind=UiInputKind::KeyDown;request.key=event.virtualKey;break;
        case ZeroSisPresentation::BitmapInputKind::CloseRequest:request.kind=UiInputKind::KeyDown;request.key=VK_ESCAPE;break;
        case ZeroSisPresentation::BitmapInputKind::PointerMove:
            if(!liveProduction_ && !SupportsExternalPointerScroll())throw std::runtime_error("Pointer input is not enabled for this popup profile");
            request.kind=UiInputKind::PointerMove;request.key=event.controlKey;break;
        case ZeroSisPresentation::BitmapInputKind::Scroll:
            if(!liveProduction_ && !SupportsExternalPointerScroll())throw std::runtime_error("Scroll input is not enabled for this popup profile");
            request.kind=UiInputKind::Scroll;request.key=event.controlKey;request.delta=event.scrollDelta;break;
        default:throw std::runtime_error("Unknown native production input kind");
        }
        const bool readonlyRichInput=request.kind==UiInputKind::PointerMove || request.kind==UiInputKind::Scroll;
        const bool observeGameplay=IsNotificationInputPanel() || (liveProduction_ && kind_==UiPopupKind::Production) ||
            (externalRouting_ && (kind_==UiPopupKind::GoodyHutReward || kind_==UiPopupKind::Pantheon || kind_==UiPopupKind::Production || kind_==UiPopupKind::TechAward || kind_==UiPopupKind::DeclareWar || kind_==UiPopupKind::TopPanel || kind_==UiPopupKind::TradeRoute || kind_==UiPopupKind::SocialPolicy || kind_==UiPopupKind::EconomicOverview || kind_==UiPopupKind::EconomicGeneral || kind_==UiPopupKind::EconomicHappiness || ((IsResearch() || kind_==UiPopupKind::UnitPanel) && readonlyRichInput)));
        const bool warWasConfirmed=warDecisionDone_;
        const unsigned policyCommandsBefore=policyCommandsApplied_;
        const unsigned pantheonCommandsBefore=pantheonCommandsApplied_;
        const std::string beforeState=observeGameplay?SdkStateSnapshot::Capture(host_):std::string{};
        if(kind_!=UiPopupKind::Ranking)
            request.consumed=DispatchInput(request.kind,request.key,request.delta);
        else if(active_ && held && !faulted_)Call(&UiInputDispatch::Dispatch,&request);
        const auto after=RandomSeed();
        std::printf("UI_WINDOW_INPUT=%u|%u|%llu|%u|%lu|%lu|%u|%u|%d|%lu\n",sequence_,
            static_cast<unsigned>(request.kind),static_cast<unsigned long long>(request.key),request.consumed?1u:0u,
            before,after,held?1u:0u,timerState_==TimerState::Held?1u:0u,game_->GetGameTurn(),
            static_cast<unsigned long>(GetCurrentThreadId()));
        const bool confirmedWar=kind_==UiPopupKind::DeclareWar && !warWasConfirmed && warDecisionDone_;
        const bool confirmedPolicy=kind_==UiPopupKind::SocialPolicy && policyCommandsApplied_!=policyCommandsBefore;
        const bool confirmedPantheon=kind_==UiPopupKind::Pantheon && pantheonCommandsApplied_!=pantheonCommandsBefore;
        if(before!=after && (readonlyRichInput || (!confirmedWar && !confirmedPolicy && !confirmedPantheon && kind_!=UiPopupKind::UnitPanel && (kind_!=UiPopupKind::CityCapture || !captureDecisionDone_))))
            throw std::runtime_error("Official informational-popup input changed synchronous RNG");
        if(kind_!=UiPopupKind::Ranking){
            const auto expectedTimer=RetainsTimer() && active_?TimerState::Held:TimerState::Released;
            if(timerState_!=expectedTimer)
                throw std::runtime_error("Official popup input changed its timer contract");
            if(observeGameplay){
                const bool unchanged=SdkStateSnapshot::Capture(host_)==beforeState;
                if(readonlyRichInput && !unchanged)
                    throw std::runtime_error("Pointer or scroll input changed SDK gameplay state");
                if(active_ && !unchanged && !confirmedPolicy)throw std::runtime_error("Nonclosing input without an owned SDK command changed gameplay state");
                if((kind_==UiPopupKind::SocialPolicy && !confirmedPolicy || kind_==UiPopupKind::Pantheon && !confirmedPantheon) && !unchanged)
                    throw std::runtime_error("Unconfirmed social-policy input changed SDK gameplay state");
                if(kind_==UiPopupKind::GoodyHutReward){
                    if(!unchanged)throw std::runtime_error("Original goody-hut reward input changed gameplay state");
                }
                if(kind_==UiPopupKind::TechAward){
                    if(!unchanged)throw std::runtime_error("Original technology award input changed gameplay state");
                    if(request.consumed && !active_)
                        std::printf("INTERACTIVE_TECH_AWARD_CLOSED=%llu|%d|0|STATE_UNCHANGED\n",static_cast<unsigned long long>(request.key),game_->GetGameTurn());
                }
                if(kind_==UiPopupKind::TradeRoute){
                    if(!unchanged)throw std::runtime_error("Original trade-route overview input changed gameplay state");
                    std::printf("INTERACTIVE_TRADE_ROUTE_INPUT=%u|%llu|%.17g|%u|%u|%u|STATE_UNCHANGED\n",
                        static_cast<unsigned>(request.kind),static_cast<unsigned long long>(request.key),request.delta,
                        request.consumed?1u:0u,active_?1u:0u,timerState_==TimerState::Held?1u:0u);
                }
                if(kind_==UiPopupKind::DeclareWar){
                    if(!confirmedWar && !unchanged)throw std::runtime_error("Unconfirmed war input changed SDK gameplay state");
                    std::printf("INTERACTIVE_DECLARE_WAR_OBSERVATION=%u|%llu|%u|%u|%u|%u\n",
                        static_cast<unsigned>(request.kind),static_cast<unsigned long long>(request.key),
                        request.consumed?1u:0u,active_?1u:0u,confirmedWar?1u:0u,unchanged?1u:0u);
                }
                if(kind_==UiPopupKind::Production)
                    std::printf("UI_PRODUCTION_WINDOW_GAMEPLAY=%u|%u|%llu|%u|%u|%.17g\n",sequence_,
                        static_cast<unsigned>(request.kind),static_cast<unsigned long long>(request.key),active_?1u:0u,
                        unchanged?1u:0u,request.delta);
            }
            return request.consumed;
        }
        if(request.consumed) {
            if(timerState_!=TimerState::Released)throw std::runtime_error("Official input did not release popup timer");
            active_=false;host_.popupVisible=false;
            WriteSnapshot("closed");
            host_.Record("ui-popup-closed:"+std::to_string(sequence_)+":"+std::to_string(game_->GetGameTurn()));
        }else if(active_ && timerState_!=TimerState::Held)
            throw std::runtime_error("Rejected input changed popup timer");
        return request.consumed;
    }
#endif
    struct TextResult {const char* data;std::size_t bytes;};
    struct ProductionChoice {int city,unit;};
    struct ResearchChoice {int player,tech;};
    struct TreeScrollObservation {std::uint64_t key=0;double offset=0.0,maximum=0.0;};
    enum class TimerState {Released,Held,TransitionUnknown};
    static constexpr unsigned InstructionBudget=2000000;
    // The complete original tree has many more controls than the chooser.
    // Preserve a finite per-call guard while measuring its actual opcode cost.
    static constexpr unsigned ResearchTreeInstructionBudget=8000000;
    // The stock SDK ring can retain 99 notifications. Its unchanged Lua
    // relayouts after every add/remove: the measured 99-row refresh/stop
    // costs about 56M/54M opcodes. Keep this allowance on those bulk calls;
    // a mouse callback still receives the ordinary 2M guard.
    static constexpr unsigned NotificationBulkInstructionBudget=128000000;
    unsigned InstructionLimit(lua_CFunction function) const {
        if(kind_==UiPopupKind::NotificationPanel){
            if(function==&RefreshNotificationPanelLua || function==&StopNotificationPanelLua)
                return NotificationBulkInstructionBudget;
            return function==&UiInputDispatch::Dispatch?InstructionBudget:ResearchTreeInstructionBudget;
        }
        return (kind_==UiPopupKind::ResearchTree || kind_==UiPopupKind::CityView || kind_==UiPopupKind::SocialPolicy || kind_==UiPopupKind::EconomicOverview || kind_==UiPopupKind::EconomicGeneral || kind_==UiPopupKind::EconomicHappiness)?ResearchTreeInstructionBudget:InstructionBudget;
    }
    static HostState& CheckedHost(const std::shared_ptr<HostState>& host){
        if(!host)throw std::invalid_argument("UI context owner is missing");return *host;
    }
    static ScriptSystem& CheckedScripts(HostState& host){
        if(!host.scripts || host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread())
            throw std::logic_error("UI context requires its script service and GameCore owner lock");
        return *host.scripts;
    }
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
    void RequireGameMenuOwner(){
        if((kind_!=UiPopupKind::GameMenu && kind_!=UiPopupKind::SaveMenu && kind_!=UiPopupKind::LoadMenu && kind_!=UiPopupKind::ExitConfirm && !IsPrivateMenuChild()) || !externalRouting_ || !pregame_ || faulted_)
            throw std::logic_error("GameMenu query is outside its original owned context");
        RequireOwnedMenuPlayer();
    }
    void RequireExitConfirmOwner(){
        if(kind_!=UiPopupKind::ExitConfirm || !externalRouting_ || !pregame_ || faulted_)
            throw std::logic_error("ExitConfirm query is outside its original owned child context");
        RequireOwnedMenuPlayer();
    }
    void MarkExitConfirmClosed(){
        RequireExitConfirmOwner();
        if(!active_ || !dispatching_ || !exitConfirmInput_ || !exitConfirmCloseInput_ || exitConfirmClosed_ ||
           gameMenuReady_ || !gameMenuRequests_.empty() || timerState_!=TimerState::Released)
            throw std::logic_error("ExitConfirm close requires its original Yes, No or Escape callback");
        exitConfirmClosed_=true;
    }
    void QueueConfirmedExit(){
        RequireExitConfirmOwner();
        if(!active_ || !dispatching_ || !exitConfirmInput_ || exitConfirmInputKind_!=UiInputKind::LeftClick ||
           !exitConfirmYesInput_ || !exitConfirmClosed_ || gameMenuReady_ || !gameMenuRequests_.empty() ||
           timerState_!=TimerState::Released)
            throw std::logic_error("Exit requires exactly one original Yes callback after PopModal");
        gameMenuRequests_.push_back({GameMenuRequest::Kind::ExitGame,gameMenuOwner_,gameMenuTurn_,"ExitGame"});
    }
    void RequireSaveMenuOwner(){
        if(kind_!=UiPopupKind::SaveMenu || !externalRouting_ || !saveMenuCatalog_ || !saveMenuCatalog_->nameAvailable || faulted_)
            throw std::logic_error("SaveMenu query is outside its immutable owned child context");
        RequireOwnedMenuPlayer();
    }
    void RequireLoadMenuOwner(){
        if(kind_!=UiPopupKind::LoadMenu || !externalRouting_ || !loadMenuCatalog_ || !loadMenuCatalog_->canLoad || faulted_ ||
           loadMenuCatalog_->profile!=UiLoadMenuCatalog::Profile::OwnedCurrentExactBundleNoAdditionalContent)
            throw std::logic_error("LoadMenu query is outside its immutable exact-bundle child context");
        RequireOwnedMenuPlayer();
        if(!host_.activeMods || host_.activeMods->Size()!=0)
            throw std::logic_error("LoadMenu content profile requires its authoritative empty activation manifest");
    }
    const UiSaveMenuFile& FindLoadMenuFile(const char* path){
        RequireLoadMenuOwner();
        if(!path || !*path)throw std::invalid_argument("LoadMenu requires a listed nonempty path");
        if(IsDeletedMenuFile(path))throw std::invalid_argument("LoadMenu file was already deleted from this context");
        for(const auto& file:loadMenuCatalog_->files)if(file.fileName==path)return file;
        throw std::invalid_argument("LoadMenu requested a file outside its immutable session list");
    }
    bool CanLoadMenuFile(const UiSaveMenuFile& file){
        RequireLoadMenuOwner();
        if(!file.header || file.header->gameType!=static_cast<int>(GAME_SINGLE_PLAYER))return false;
        const bool compatible=loadMenuCatalog_->canLoad(file.fileName);
        RequireOwnedMenuPlayer();return compatible;
    }
    void QueueLoadMenuRequest(LoadMenuRequest::Kind kind,const char* path){
        RequireLoadMenuOwner();
        if(!active_ || !dispatching_ || !loadMenuInput_ || loadMenuReady_ || timerState_!=TimerState::Released ||
           (loadMenuInputKind_!=UiInputKind::LeftClick && loadMenuInputKind_!=UiInputKind::KeyDown))
            throw std::logic_error("LoadMenu callback requires its original owned input boundary");
        if(kind==LoadMenuRequest::Kind::Load){
            if(stopping_ || !loadMenuRequests_.empty() || loadMenuCursorToken_!=1 ||
               !CanLoadMenuFile(FindLoadMenuFile(path)))
                throw std::invalid_argument("LoadMenu load request is duplicated, stale, or incompatible");
        }else if(loadMenuRequests_.size()>1 ||
                 (!loadMenuRequests_.empty() && loadMenuRequests_.front().kind!=LoadMenuRequest::Kind::Load) ||
                 loadMenuCursorToken_!=(loadMenuRequests_.empty()?0:1))
            throw std::logic_error("LoadMenu close request is duplicated or out of order");
        loadMenuRequests_.push_back({kind,gameMenuOwner_,gameMenuTurn_,path?path:""});
        std::printf("INTERACTIVE_LOAD_MENU_REQUEST_QUEUED=%u|%d|%d\n",static_cast<unsigned>(kind),gameMenuOwner_,gameMenuTurn_);
    }
    void RestoreLoadMenuCursor() noexcept {
        if(!loadMenuCursorToken_)return;
        if(const auto arrow=LoadCursorW(nullptr,MAKEINTRESOURCEW(32512)))SetCursor(arrow);
        loadMenuCursorToken_=0;
    }
    void QueueSaveMenuRequest(SaveMenuRequest::Kind kind,const char* name){
        RequireSaveMenuOwner();
        if(!active_ || !dispatching_ || !saveMenuInput_ || saveMenuReady_ || timerState_!=TimerState::Released ||
           (saveMenuInputKind_!=UiInputKind::LeftClick && saveMenuInputKind_!=UiInputKind::KeyDown))
            throw std::logic_error("SaveMenu callback requires its original owned input boundary");
        if(kind==SaveMenuRequest::Kind::Save){
            if(stopping_ || !saveMenuRequests_.empty() || !name || !*name || std::strlen(name)>128 || Utf8Length(name)>32)
                throw std::invalid_argument("SaveMenu named request is invalid or duplicated");
            if(!saveMenuCatalog_->nameAvailable(std::string(name)))
                throw std::invalid_argument("SaveMenu named request is unavailable");
        }else if(kind!=SaveMenuRequest::Kind::Close || (name && *name) || saveMenuRequests_.size()>1 ||
                 (!saveMenuRequests_.empty() && saveMenuRequests_.front().kind!=SaveMenuRequest::Kind::Save &&
                  saveMenuRequests_.front().kind!=SaveMenuRequest::Kind::Overwrite))
            throw std::logic_error("SaveMenu close request is invalid, duplicated or out of order");
        saveMenuRequests_.push_back({kind,gameMenuOwner_,gameMenuTurn_,name?name:"",nullptr});
        std::printf("INTERACTIVE_SAVE_MENU_REQUEST_QUEUED=%u|%d|%d\n",static_cast<unsigned>(kind),gameMenuOwner_,gameMenuTurn_);
    }
    void QueueSaveMenuOverwrite(const char* name,const char* listedPath){
        RequireSaveMenuOwner();
        if(!active_ || !dispatching_ || stopping_ || !saveMenuInput_ || saveMenuInputKind_!=UiInputKind::LeftClick ||
           saveMenuReady_ || loadMenuReady_ || loadMenuCursorToken_ || timerState_!=TimerState::Released ||
           !saveMenuRequests_.empty() || !loadMenuRequests_.empty() || !saveMenuCatalog_->overwriteSupported ||
           !name || !*name || std::strlen(name)>128 || Utf8Length(name)>32)
            throw std::logic_error("SaveMenu overwrite requires its one-use original confirmation input");
        const auto& listed=FindSaveMenuFile(listedPath);
        if(!listed.header || std::count_if(saveMenuCatalog_->files.begin(),saveMenuCatalog_->files.end(),
                [&listed](const UiSaveMenuFile& file){return file.fileName==listed.fileName;})!=1)
            throw std::invalid_argument("SaveMenu overwrite requires one known immutable listed observation");
        auto expected=std::make_shared<UiSaveMenuFile>(listed);
        expected->header=std::make_shared<const UiSaveMenuHeader>(*listed.header);
        saveMenuRequests_.push_back({SaveMenuRequest::Kind::Overwrite,gameMenuOwner_,gameMenuTurn_,name,std::move(expected)});
        std::printf("INTERACTIVE_SAVE_MENU_REQUEST_QUEUED=%u|%d|%d\n",
            static_cast<unsigned>(SaveMenuRequest::Kind::Overwrite),gameMenuOwner_,gameMenuTurn_);
    }
    const UiSaveMenuFile& FindSaveMenuFile(const char* path){
        RequireSaveMenuOwner();
        if(!path || !*path || IsDeletedMenuFile(path))
            throw std::invalid_argument("SaveMenu requires a live listed path");
        for(const auto& file:saveMenuCatalog_->files)if(file.fileName==path)return file;
        throw std::invalid_argument("SaveMenu requested a file outside its immutable session list");
    }
    bool IsDeletedMenuFile(const std::string& path) const {
        return std::find(deletedMenuFiles_.begin(),deletedMenuFiles_.end(),path)!=deletedMenuFiles_.end();
    }
    bool MenuDeletionSupported(){
        if(kind_==UiPopupKind::SaveMenu){RequireSaveMenuOwner();return !!saveMenuCatalog_->deleteFile;}
        RequireLoadMenuOwner();return !!loadMenuCatalog_->deleteFile;
    }
    bool CanDeleteMenuFile(const UiSaveMenuFile& file){
        // Eligibility is not authorization. The filesystem service rechecks
        // identity, checksum, header and bundle on the final exclusive handle.
        return MenuDeletionSupported() && !!file.header && !IsDeletedMenuFile(file.fileName);
    }
    void DeleteMenuFile(const char* path){
        const bool saving=kind_==UiPopupKind::SaveMenu;
        const auto& file=saving?FindSaveMenuFile(path):FindLoadMenuFile(path);
        const bool input=saving?saveMenuInput_:loadMenuInput_;
        const auto inputKind=saving?saveMenuInputKind_:loadMenuInputKind_;
        if(!active_ || !dispatching_ || stopping_ || !input || inputKind!=UiInputKind::LeftClick ||
           timerState_!=TimerState::Released || saveMenuReady_ || loadMenuReady_ || loadMenuCursorToken_ ||
           !saveMenuRequests_.empty() || !loadMenuRequests_.empty() || !CanDeleteMenuFile(file))
            throw std::logic_error("Save deletion requires its settled original confirmation input");
        // Allocate the tombstone before the irreversible operation. If the
        // service rejects the observation, the immutable view is unchanged.
        deletedMenuFiles_.push_back(file.fileName);
        try{
            if(saving)saveMenuCatalog_->deleteFile(file);else loadMenuCatalog_->deleteFile(file);
        }catch(...){deletedMenuFiles_.pop_back();throw;}
        std::printf("INTERACTIVE_OWNED_SAVE_DELETED=%d|%d\n",gameMenuOwner_,gameMenuTurn_);
    }
    static void PushSaveMenuHeader(lua_State* state,const UiSaveMenuHeader& header){
        lua_newtable(state);
        Field(state,"PlayerCivilization",header.playerCivilization);Field(state,"GameSpeed",header.gameSpeed);
        Field(state,"StartEra",header.startEra);Field(state,"TurnNumber",header.turnNumber);
        Field(state,"Difficulty",header.difficulty);Field(state,"WorldSize",header.worldSize);
        Field(state,"CurrentEra",header.currentEra);Field(state,"GameType",header.gameType);
        lua_pushlstring(state,header.mapScript.data(),header.mapScript.size());lua_setfield(state,-2,"MapScript");
        lua_pushlstring(state,header.leaderName.data(),header.leaderName.size());lua_setfield(state,-2,"LeaderName");
        lua_pushlstring(state,header.civilizationName.data(),header.civilizationName.size());lua_setfield(state,-2,"CivilizationName");
    }
    void RequireEmptyMenuModManifest(){
        RequireGameMenuOwner();
        if(!host_.activeMods || host_.activeMods->Size()!=0)
            throw std::logic_error("GameMenu mod queries require the authoritative empty activation manifest");
    }
    static bool IsGameMenuUnavailableAction(const char* action){
        return action && (std::strcmp(action,"LoadMenu")==0 ||
            std::strcmp(action,"SaveMapMenu")==0 || std::strcmp(action,"OptionsMenu_InGame")==0 ||
            std::strcmp(action,"TouchControlsMenu")==0 || std::strcmp(action,"Restart")==0 ||
            std::strcmp(action,"Retire")==0 || std::strcmp(action,"ExitToMainMenu")==0 || std::strcmp(action,"ExitGame")==0);
    }
    void QueueGameMenuRequest(GameMenuRequest::Kind kind,const char* action){
        Require();
        if(kind==GameMenuRequest::Kind::ExitGame ||
           (kind==GameMenuRequest::Kind::OpenExitConfirm && (!action || std::strcmp(action,"ExitConfirm")!=0)) ||
           !externalRouting_ || !active_ || faulted_ || !dispatching_ || gameMenuReady_ || !gameMenuRequests_.empty())
            throw std::logic_error("GameMenu callback may publish exactly one owned request");
        const int owner=game_->GetActivePlayer(),turn=game_->GetGameTurn();
        RequireLocalMenuPlayer(owner,turn);
        if(kind==GameMenuRequest::Kind::Open){
            if(kind_!=UiPopupKind::TopPanel || !topPanelInput_ || topPanelInputKind_!=UiInputKind::LeftClick ||
               topPanelPopup_ || topPanelOwner_!=owner || timerState_!=TimerState::Released)
                throw std::logic_error("GameMenu opening requires the original TopPanel left-click callback");
        }else{
            RequireGameMenuOwner();
            if(!gameMenuInput_ || gameMenuInputKind_!=UiInputKind::LeftClick ||
               (timerState_!=TimerState::Held && timerState_!=TimerState::Released) ||
               (kind==GameMenuRequest::Kind::QuickSave && timerState_!=TimerState::Released))
                throw std::logic_error("GameMenu command is outside its original click/return boundary");
        }
        gameMenuRequests_.push_back({kind,owner,turn,action});
        std::printf("INTERACTIVE_GAME_MENU_REQUEST_QUEUED=%u|%d|%d|%s\n",
            static_cast<unsigned>(kind),owner,turn,action);
    }
    void RestoreGameMenuCursor() noexcept {
        if(!gameMenuCursorToken_)return;
        if(const auto arrow=LoadCursorW(nullptr,MAKEINTRESOURCEW(32512)))SetCursor(arrow);
        gameMenuCursorToken_=0;
    }
    static std::string NormalizedMenuMapPath(const char* input){
        if(!input || !*input || std::strlen(input)>=MAX_PATH)
            throw std::invalid_argument("GameMenu map identity is empty or exceeds the SDK preview path bound");
        std::string result(input);
        for(auto& value:result){if(value=='\\')value='/';else if(value>='A' && value<='Z')value=static_cast<char>(value-'A'+'a');}
        return result;
    }
    struct GameMenuMapPreviewCall {ICvWorldBuilderMapLoader1* loader;const char* filename;};
    static int ReadGameMenuMapPreview(lua_State* state){
        const auto* input=static_cast<const GameMenuMapPreviewCall*>(lua_touserdata(state,1));
        if(!input || !input->loader || !input->filename)throw std::invalid_argument("GameMenu preview input is missing");
        lua_settop(state,0);lua_pushstring(state,input->filename);
        const int count=input->loader->GetMapPreview(state);
        if(count!=1 || (lua_type(state,-1)!=LUA_TTABLE && lua_type(state,-1)!=LUA_TNIL))
            throw std::runtime_error("SDK map preview did not return its original table-or-nil result");
        lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_GAME_MENU_MAP_PREVIEW");return 0;
    }
    void RequireActionInfoInput(){
        Require();
        if(!IsNotificationInputPanel() || !externalRouting_ || !active_ || faulted_ ||
           !dispatching_ || !actionInfoInput_ || actionInfoReady_ ||
           (actionInfoInputKind_!=UiInputKind::LeftClick && actionInfoInputKind_!=UiInputKind::RightClick) ||
           timerState_!=TimerState::Released || !host_.localSdkSessionBound ||
           actionInfoOwner_!=game_->GetActivePlayer() || actionInfoTurn_!=game_->GetGameTurn() ||
           actionInfoOwner_<0 || actionInfoOwner_>=MAX_PLAYERS)
            throw std::logic_error("ActionInfoPanel command requires its refreshed active-player click callback");
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(actionInfoOwner_)));
        if(!player || !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive())
            throw std::logic_error("ActionInfoPanel command requires the active human SDK turn");
    }
    void QueueActionInfoRequest(ActionInfoRequest::Kind kind,int id=-1,int x=-1,int y=-1){
        RequireActionInfoInput();
        if(kind_==UiPopupKind::NotificationPanel &&
           (kind!=ActionInfoRequest::Kind::ActivateNotification && kind!=ActionInfoRequest::Kind::RemoveNotification))
            throw std::logic_error("Original NotificationPanel only activates or dismisses an SDK notification");
        if(actionInfoRequests_.size()>=2)
            throw std::logic_error("Original ActionInfoPanel callback exceeded its two-command envelope");
        actionInfoRequests_.push_back({kind,id,x,y,actionInfoOwner_,actionInfoTurn_});
    }
    bool IsNotificationInputPanel() const {
        return kind_==UiPopupKind::ActionInfoPanel || kind_==UiPopupKind::NotificationPanel;
    }
    static int PushNotificationRows(lua_State* state){
        const auto* rows=static_cast<const std::vector<NotificationPresentation>*>(lua_touserdata(state,1));
        if(!rows)throw std::invalid_argument("NotificationPanel SDK rows are missing");
        lua_settop(state,0);lua_newtable(state);int index=0;
        for(const auto& row:*rows){
            lua_newtable(state);Field(state,"id",row.id);Field(state,"type",static_cast<int>(row.type));
            Field(state,"gameData",row.gameData);Field(state,"extraGameData",row.extraGameData);
            Field(state,"player",static_cast<int>(row.player));Field(state,"x",row.x);Field(state,"y",row.y);
            lua_pushlstring(state,row.tooltip.data(),row.tooltip.size());lua_setfield(state,-2,"tooltip");
            lua_pushlstring(state,row.summary.data(),row.summary.size());lua_setfield(state,-2,"summary");
            lua_rawseti(state,-2,++index);
        }
        lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_NOTIFICATION_ROWS");return 0;
    }
    static UiPopupContext& From(lua_State* state){
        lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_CONTEXT");
        auto* self=static_cast<UiPopupContext*>(lua_touserdata(state,-1));lua_pop(state,1);
        if(!self)throw std::logic_error("Native UI context is missing");
        self->Require();return *self;
    }
    static int Bind(lua_State* state){
        lua_pushvalue(state,1);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_CONTEXT");return 0;
    }
    static const char* Text(lua_State* state,int index){
        if(lua_type(state,index)!=LUA_TSTRING)throw std::invalid_argument("UI adapter expects text");
        std::size_t bytes=0;const char* value=lua_tolstring(state,index,&bytes);
        if(std::strlen(value)!=bytes)throw std::invalid_argument("NUL in UI adapter text");return value;
    }
    static int Integer(lua_State* state,int index){
        if(lua_type(state,index)!=LUA_TNUMBER)throw std::invalid_argument("UI adapter expects a number");
        const auto value=lua_tonumber(state,index);
        if(!std::isfinite(value) || value<INT_MIN || value>INT_MAX || std::floor(value)!=value)
            throw std::invalid_argument("UI adapter expects an exact integer");
        return static_cast<int>(value);
    }
    static std::uint32_t FileTimeWord(lua_State* state,int index){
        if(lua_type(state,index)!=LUA_TNUMBER)throw std::invalid_argument("FILETIME word must be a number");
        const auto value=lua_tonumber(state,index);
        if(!std::isfinite(value) || value<0 || value>4294967295.0 || std::floor(value)!=value)
            throw std::invalid_argument("FILETIME word must be an exact unsigned 32-bit integer");
        return static_cast<std::uint32_t>(value);
    }
    static std::string Localize(lua_State* state){
        auto value=Localization::Lookup(Text(state,2));
        for(int index=3;index<=lua_gettop(state);++index){
            // Retail Locale.Lookup/ConvertTextKey type dispatch: boolean->int, number->double, string->text.
            const bool accepted=PushRetailLocaleArgument(state,index,value,
                [state](int at){return Localization::Lookup(Text(state,at));});
            if(!accepted)throw std::runtime_error("Localization argument was rejected");
        }
        std::size_t bytes=0;const char* output=value.toUTF8(bytes);
        if(!output)throw std::runtime_error("UI localization could not be composed");
        return std::string(output,bytes);
    }
    static int PushText(lua_State* state){
        const auto* output=static_cast<const TextResult*>(lua_touserdata(state,1));
        lua_pushlstring(state,output->data,output->bytes);
        lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");return 0;
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
    static std::string TextOperation(lua_State* state,const char* operation){
        if(std::strcmp(operation,"localeNumber")==0){
            if(lua_gettop(state)!=3 || lua_type(state,2)!=LUA_TNUMBER)
                throw std::invalid_argument("Invalid UI number-format arity or value");
            const char* pattern=Text(state,3);
            if(std::strcmp(pattern,"#.##")!=0)
                throw std::invalid_argument("UI number formatting requires the original #.## pattern");
            Localization::String formatted("{1:number #.##}");
            // The SDK exports the double overload; its ParameterArgument
            // overload is internal to the provider and has no import symbol.
            if(!formatted.PushArgument(static_cast<double>(lua_tonumber(state,2))))
                throw std::runtime_error("UI number argument was rejected");
            std::size_t bytes=0;const char* output=formatted.toUTF8(bytes,1);
            if(!output || bytes==0)throw std::runtime_error("UI localized number formatting failed or returned empty text");
            Utf8Length(output);
            return std::string(output,bytes);
        }
        const char* text=Text(state,2);
        if(std::strcmp(operation,"localeTruncate")==0){
            if(lua_gettop(state)!=4 || lua_type(state,4)!=LUA_TBOOLEAN)
                throw std::invalid_argument("Invalid UI truncation arity or suffix option");
            const int maximum=Integer(state,3);const bool ellipsis=lua_toboolean(state,4)!=0;
            if(maximum<0 || maximum>4096)throw std::invalid_argument("Invalid UI truncation limit");
            const auto length=Utf8Length(text);
            if(length<=static_cast<std::size_t>(maximum))return std::string(text);
            const int suffix=ellipsis?std::min(maximum,3):0;
            const int keep=maximum-suffix;const auto bytes=std::strlen(text);std::size_t end=0;
            for(int i=0;i<keep;++i)end=Utf8Next(text,bytes,end);
            return std::string(text,end)+std::string(static_cast<std::size_t>(suffix),'.');
        }
        if(std::strcmp(operation,"localeSubstring")==0){
            if(lua_gettop(state)!=4)throw std::invalid_argument("Invalid UI substring arity");
            const int start=Integer(state,3),count=Integer(state,4);
            const auto length=Utf8Length(text);
            if(start<1 || count<0 || static_cast<std::size_t>(start-1)>length ||
               static_cast<std::size_t>(count)>length-static_cast<std::size_t>(start-1))
                throw std::invalid_argument("UI substring range exceeds Unicode text");
            const auto bytes=std::strlen(text);std::size_t begin=0,end=0;
            for(int i=1;i<start;++i)begin=Utf8Next(text,bytes,begin);
            end=begin;for(int i=0;i<count;++i)end=Utf8Next(text,bytes,end);
            return std::string(text+begin,end-begin);
        }
        if(lua_gettop(state)!=2)throw std::invalid_argument("Invalid UI case transform arity");
        // The retained provider exposes ICU case transforms through its tested
        // composition grammar; standalone ParameterTransforms methods are not
        // exported by this provider and must not be treated as callable APIs.
        Utf8Length(text);Localization::String input(text);
        Localization::String output(std::strcmp(operation,"localeUpper")==0?"{1:upper}":"{1:lower}");
        if(!output.PushArgument(input))throw std::runtime_error("UI Unicode case transform argument was rejected");
        std::size_t bytes=0;const char* result=output.toUTF8(bytes);
        if(!result)throw std::runtime_error("UI Unicode case transform failed");
        return std::string(result,bytes);
    }
    static int Native(lua_State* state){
        auto& self=From(state);const char* operation=Text(state,1);
        int menuResult=0;if(self.TryMenuNative(state,operation,menuResult))return menuResult;
        if(std::strcmp(operation,"loadMenuOpen")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::GameMenu)
                throw std::invalid_argument("LoadMenu opening requires its original GameMenu callback");
            self.QueueGameMenuRequest(GameMenuRequest::Kind::OpenLoadMenu,"LoadMenu");return 0;
        }
        if(std::strcmp(operation,"loadMenuGameTypes")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("LoadMenu game types take no arguments");
            self.RequireLoadMenuOwner();lua_newtable(state);
            lua_pushnumber(state,static_cast<lua_Number>(GAME_TYPE_NONE));lua_setfield(state,-2,"GAME_TYPE_NONE");
            lua_pushnumber(state,static_cast<lua_Number>(GAME_SINGLE_PLAYER));lua_setfield(state,-2,"GAME_SINGLE_PLAYER");
            lua_pushnumber(state,static_cast<lua_Number>(GAME_NETWORK_MULTIPLAYER));lua_setfield(state,-2,"GAME_NETWORK_MULTIPLAYER");
            lua_pushnumber(state,static_cast<lua_Number>(GAME_HOTSEAT_MULTIPLAYER));lua_setfield(state,-2,"GAME_HOTSEAT_MULTIPLAYER");
            lua_pushnumber(state,static_cast<lua_Number>(GAME_EMAIL_MULTIPLAYER));lua_setfield(state,-2,"GAME_EMAIL_MULTIPLAYER");
            return 1;
        }
        if(std::strcmp(operation,"loadMenuInGameView")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("LoadMenu in-game view query takes no arguments");
            self.RequireLoadMenuOwner();lua_pushboolean(state,true);return 1;
        }
        if(std::strcmp(operation,"loadMenuCloudSaves")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("LoadMenu cloud inventory takes no arguments");
            self.RequireLoadMenuOwner();
            // This supported profile has no connected cloud provider. The stock
            // show handler queries it even while its local list is selected.
            lua_newtable(state);return 1;
        }
        if(std::strcmp(operation,"saveMenuDeleteSupported")==0 || std::strcmp(operation,"loadMenuDeleteSupported")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Save deletion capability takes no arguments");
            if(operation[0]=='s')self.RequireSaveMenuOwner();else self.RequireLoadMenuOwner();
            lua_pushboolean(state,self.MenuDeletionSupported()?1:0);return 1;
        }
        if(std::strcmp(operation,"saveMenuCanDelete")==0 || std::strcmp(operation,"loadMenuCanDelete")==0 ||
           std::strcmp(operation,"saveMenuDelete")==0 || std::strcmp(operation,"loadMenuDelete")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("Save deletion query takes one listed path");
            const bool saving=operation[0]=='s';
            const auto& file=saving?self.FindSaveMenuFile(Text(state,2)):self.FindLoadMenuFile(Text(state,2));
            if(std::strcmp(operation,"saveMenuCanDelete")==0 || std::strcmp(operation,"loadMenuCanDelete")==0)
                lua_pushboolean(state,self.CanDeleteMenuFile(file)?1:0);
            else {self.DeleteMenuFile(file.fileName.c_str());lua_pushboolean(state,1);}
            return 1;
        }
        if(std::strcmp(operation,"loadMenuFiles")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("LoadMenu file list takes no arguments");
            self.RequireLoadMenuOwner();lua_newtable(state);int index=0;
            for(const auto& file:self.loadMenuCatalog_->files){
                if(self.IsDeletedMenuFile(file.fileName))continue;
                if(file.fileName.empty() || file.fileName.find('\0')!=std::string::npos || index==10000)
                    throw std::invalid_argument("LoadMenu immutable file catalog is invalid or unbounded");
                Utf8Length(file.fileName.c_str());
                lua_pushlstring(state,file.fileName.data(),file.fileName.size());lua_rawseti(state,-2,++index);
            }
            return 1;
        }
        if(std::strcmp(operation,"loadMenuHeader")==0 || std::strcmp(operation,"loadMenuModificationTime")==0 ||
           std::strcmp(operation,"loadMenuModificationTimeRaw")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("LoadMenu file query takes one listed path");
            const auto& file=self.FindLoadMenuFile(Text(state,2));
            if(std::strcmp(operation,"loadMenuHeader")==0){
                if(file.header)PushSaveMenuHeader(state,*file.header);else lua_pushnil(state);
            }else if(std::strcmp(operation,"loadMenuModificationTimeRaw")==0){
                lua_pushnumber(state,static_cast<lua_Number>(file.modificationTimeHigh));
                lua_pushnumber(state,static_cast<lua_Number>(file.modificationTimeLow));return 2;
            }else lua_pushlstring(state,file.modificationTime.data(),file.modificationTime.size());
            return 1;
        }
        if(std::strcmp(operation,"loadMenuCompareFileTime")==0){
            if(lua_gettop(state)!=5)throw std::invalid_argument("LoadMenu time comparison takes four FILETIME words");
            self.RequireLoadMenuOwner();
            const auto firstHigh=FileTimeWord(state,2),firstLow=FileTimeWord(state,3);
            const auto secondHigh=FileTimeWord(state,4),secondLow=FileTimeWord(state,5);
            const FILETIME first{static_cast<DWORD>(firstLow),static_cast<DWORD>(firstHigh)};
            const FILETIME second{static_cast<DWORD>(secondLow),static_cast<DWORD>(secondHigh)};
            lua_pushnumber(state,static_cast<lua_Number>(::CompareFileTime(&first,&second)));return 1;
        }
        if(std::strcmp(operation,"loadMenuCanLoad")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("LoadMenu compatibility takes one listed path");
            const auto& file=self.FindLoadMenuFile(Text(state,2));
            // The original menu enables loading only for zero; five is its
            // explicit incompatible-profile result, never a fabricated success.
            lua_pushnumber(state,self.CanLoadMenuFile(file)?0:5);return 1;
        }
        if(std::strcmp(operation,"loadMenuRequiredContent")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("LoadMenu required content takes one listed path");
            const auto& file=self.FindLoadMenuFile(Text(state,2));
            if(!file.header)throw std::invalid_argument("Unknown LoadMenu header has no verified content requirements");
            // RequireLoadMenuOwner already verified the explicit exact-bundle,
            // no-additional-content profile and authoritative empty activation.
            lua_newtable(state); // DLC requirements, the first original return.
            lua_newtable(state); // Mod requirements, the second original return.
            return 2;
        }
        if(std::strcmp(operation,"loadMenuLoad")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("Original LoadMenu load takes one listed path");
            self.QueueLoadMenuRequest(LoadMenuRequest::Kind::Load,Text(state,2));return 0;
        }
        if(std::strcmp(operation,"loadMenuClose")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Original LoadMenu close takes no arguments");
            self.QueueLoadMenuRequest(LoadMenuRequest::Kind::Close,nullptr);return 0;
        }
        if(std::strcmp(operation,"loadMenuCursor")==0){
            self.RequireLoadMenuOwner();
            if(lua_gettop(state)!=2 || !self.active_ || !self.loadMenuInput_ || !self.dispatching_ || self.stopping_ ||
               (self.loadMenuInputKind_!=UiInputKind::LeftClick && self.loadMenuInputKind_!=UiInputKind::KeyDown) ||
               !self.loadMenuRequests_.empty() || self.loadMenuReady_)
                throw std::logic_error("LoadMenu cursor changes require its original input callback");
            const int token=Integer(state,2);
            if(token!=1 || self.loadMenuCursorToken_!=0)
                throw std::invalid_argument("LoadMenu supports its original single arrow-to-wait transition");
            const auto cursor=LoadCursorW(nullptr,MAKEINTRESOURCEW(32514));
            if(!cursor)throw std::runtime_error("Original LoadMenu wait cursor could not be loaded");
            const int previous=self.loadMenuCursorToken_;SetCursor(cursor);self.loadMenuCursorToken_=token;
            lua_pushinteger(state,previous);return 1;
        }
        if(std::strcmp(operation,"localeHasTextKey")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("Locale.HasTextKey takes one text key");
            self.RequireLoadMenuOwner();const char* key=Text(state,2);Utf8Length(key);
            std::size_t size=0;lua_tolstring(state,2,&size);
            if(size>UINT_MAX)throw std::invalid_argument("Locale.HasTextKey text exceeds the SDK byte-length range");
            lua_pushboolean(state,Localization::GetStringDictionary().HasKey(key,static_cast<unsigned>(size)));return 1;
        }
        if(std::strcmp(operation,"saveMenuOpen")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::GameMenu)
                throw std::invalid_argument("SaveMenu opening requires its original GameMenu callback");
            self.QueueGameMenuRequest(GameMenuRequest::Kind::OpenSaveMenu,"SaveMenu");return 0;
        }
        if(std::strcmp(operation,"saveMenuSave")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("Original SaveMenu save takes one name");
            self.QueueSaveMenuRequest(SaveMenuRequest::Kind::Save,Text(state,2));return 0;
        }
        if(std::strcmp(operation,"saveMenuOverwriteSupported")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("SaveMenu overwrite capability takes no arguments");
            self.RequireSaveMenuOwner();lua_pushboolean(state,self.saveMenuCatalog_->overwriteSupported?1:0);return 1;
        }
        if(std::strcmp(operation,"saveMenuOverwrite")==0){
            if(lua_gettop(state)!=3)throw std::invalid_argument("SaveMenu overwrite takes one name and one listed path");
            self.QueueSaveMenuOverwrite(Text(state,2),Text(state,3));return 0;
        }
        if(std::strcmp(operation,"saveMenuClose")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Original SaveMenu close takes no arguments");
            self.QueueSaveMenuRequest(SaveMenuRequest::Kind::Close,nullptr);return 0;
        }
        if(std::strcmp(operation,"saveMenuCurrent")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("SaveMenu current header takes no arguments");
            self.RequireSaveMenuOwner();PushSaveMenuHeader(state,self.saveMenuCatalog_->current);return 1;
        }
        if(std::strcmp(operation,"saveMenuGameTypes")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("SaveMenu game types take no arguments");
            self.RequireSaveMenuOwner();lua_newtable(state);
            lua_pushnumber(state,static_cast<lua_Number>(GAME_TYPE_NONE));lua_setfield(state,-2,"GAME_TYPE_NONE");
            lua_pushnumber(state,static_cast<lua_Number>(GAME_SINGLE_PLAYER));lua_setfield(state,-2,"GAME_SINGLE_PLAYER");
            lua_pushnumber(state,static_cast<lua_Number>(GAME_NETWORK_MULTIPLAYER));lua_setfield(state,-2,"GAME_NETWORK_MULTIPLAYER");
            lua_pushnumber(state,static_cast<lua_Number>(GAME_HOTSEAT_MULTIPLAYER));lua_setfield(state,-2,"GAME_HOTSEAT_MULTIPLAYER");
            lua_pushnumber(state,static_cast<lua_Number>(GAME_EMAIL_MULTIPLAYER));lua_setfield(state,-2,"GAME_EMAIL_MULTIPLAYER");
            return 1;
        }
        if(std::strcmp(operation,"saveMenuFiles")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("SaveMenu file list takes no arguments");
            self.RequireSaveMenuOwner();lua_newtable(state);int index=0;
            for(const auto& file:self.saveMenuCatalog_->files){
                if(self.IsDeletedMenuFile(file.fileName))continue;
                lua_pushlstring(state,file.fileName.data(),file.fileName.size());lua_rawseti(state,-2,++index);
            }
            return 1;
        }
        if(std::strcmp(operation,"saveMenuHeader")==0 || std::strcmp(operation,"saveMenuModificationTime")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("SaveMenu file query takes one listed path");
            const auto& file=self.FindSaveMenuFile(Text(state,2));
            if(std::strcmp(operation,"saveMenuHeader")==0){
                if(file.header)PushSaveMenuHeader(state,*file.header);else lua_pushnil(state);
            }else lua_pushlstring(state,file.modificationTime.data(),file.modificationTime.size());
            return 1;
        }
        if(std::strcmp(operation,"saveMenuNameAvailable")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("SaveMenu availability query takes one name");
            self.RequireSaveMenuOwner();bool available=false;
            {const std::string name(Text(state,2));available=name.size()<=128 && self.saveMenuCatalog_->nameAvailable(name);}
            lua_pushboolean(state,available);return 1;
        }
        if(std::strcmp(operation,"gameMenuOpen")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("GameMenu open takes no arguments");
            self.QueueGameMenuRequest(GameMenuRequest::Kind::Open,"GameMenu");return 0;
        }
        if(std::strcmp(operation,"gameMenuQuickSave")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Original GameMenu quick-save takes no arguments");
            self.QueueGameMenuRequest(GameMenuRequest::Kind::QuickSave,"QuickSave");return 0;
        }
        if(std::strcmp(operation,"gameMenuExitConfirm")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::GameMenu)
                throw std::invalid_argument("ExitConfirm opening requires its original GameMenu callback");
            self.QueueGameMenuRequest(GameMenuRequest::Kind::OpenExitConfirm,"ExitConfirm");return 0;
        }
        if(std::strcmp(operation,"exitConfirmInGame")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("ExitConfirm InGame lookup takes no arguments");
            self.RequireExitConfirmOwner();lua_pushboolean(state,true);return 1;
        }
        if(std::strcmp(operation,"exitConfirmClose")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("ExitConfirm PopModal takes no arguments");
            self.MarkExitConfirmClosed();return 0;
        }
        if(std::strcmp(operation,"exitConfirmExit")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("ExitConfirm UI.ExitGame takes no arguments");
            self.QueueConfirmedExit();return 0;
        }
        if(std::strcmp(operation,"gameMenuUnavailable")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("GameMenu unavailable action takes its original action name");
            const char* action=Text(state,2);
            if(!IsGameMenuUnavailableAction(action))throw std::invalid_argument("GameMenu unavailable action is outside the retained original menu");
            self.QueueGameMenuRequest(GameMenuRequest::Kind::Unavailable,action);return 0;
        }
        if(std::strcmp(operation,"gameMenuPreGame")==0){
            self.RequireGameMenuOwner();
            if(lua_gettop(state)<2)throw std::invalid_argument("GameMenu pregame query requires its selector");
            const char* selector=Text(state,2);
            if(std::strcmp(selector,"leaderName")==0 || std::strcmp(selector,"civilizationShortDescription")==0 ||
               std::strcmp(selector,"mapScript")==0){
                const bool map=std::strcmp(selector,"mapScript")==0;
                if(lua_gettop(state)!=(map?2:3))throw std::invalid_argument("Invalid GameMenu identity query arity");
                const int id=map?0:Integer(state,3);
                if(!map && (id<0 || id>=MAX_PLAYERS))throw std::invalid_argument("GameMenu identity player is outside SDK slots");
                int status=0;
                {
                    const CvString value=map?self.pregame_->mapScriptName():std::strcmp(selector,"leaderName")==0?
                        self.pregame_->leaderName(static_cast<PlayerTypes>(id)):
                        self.pregame_->civilizationShortDescription(static_cast<PlayerTypes>(id));
                    TextResult text{value.data(),value.size()};status=lua_cpcall(state,&PushText,&text);
                }
                if(status)return lua_error(state);
                lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");
                lua_pushnil(state);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");return 1;
            }
            if(std::strcmp(selector,"handicap")==0){
                if(lua_gettop(state)!=3)throw std::invalid_argument("GameMenu handicap query requires one SDK player");
                const int id=Integer(state,3);if(id<0 || id>=MAX_PLAYERS)throw std::invalid_argument("Invalid GameMenu handicap player");
                lua_pushinteger(state,static_cast<int>(self.pregame_->handicap(static_cast<PlayerTypes>(id))));return 1;
            }
            if(std::strcmp(selector,"victory")==0){
                if(lua_gettop(state)!=3)throw std::invalid_argument("GameMenu victory query requires one SDK victory");
                const int id=Integer(state,3);
                if(id<0 || id>=self.core_->GetNumVictoryInfos())throw std::invalid_argument("Invalid GameMenu victory ID");
                lua_pushboolean(state,self.pregame_->isVictory(static_cast<VictoryTypes>(id)));return 1;
            }
            if(std::strcmp(selector,"gameOption")==0){
                if(lua_gettop(state)!=3)throw std::invalid_argument("GameMenu option query requires one original option type");
                const char* name=Text(state,3);if(!*name || std::strlen(name)>256)throw std::invalid_argument("Invalid GameMenu option name");
                int value=0;
                if(self.pregame_->GetGameOption(name,value))lua_pushinteger(state,value);else lua_pushnil(state);
                return 1;
            }
            if(lua_gettop(state)!=2)throw std::invalid_argument("GameMenu scalar pregame query takes no value argument");
            if(std::strcmp(selector,"worldSize")==0)lua_pushinteger(state,static_cast<int>(self.pregame_->worldSize()));
            else if(std::strcmp(selector,"gameSpeed")==0)lua_pushinteger(state,static_cast<int>(self.pregame_->gameSpeed()));
            else if(std::strcmp(selector,"era")==0)lua_pushinteger(state,static_cast<int>(self.pregame_->era()));
            else if(std::strcmp(selector,"loadWBScenario")==0)lua_pushboolean(state,self.pregame_->loadWBScenario());
            else throw std::invalid_argument("Unsupported GameMenu pregame selector");
            return 1;
        }
        if(std::strcmp(operation,"gameMenuActivatedMods")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Activated mod query takes no arguments");
            self.RequireEmptyMenuModManifest();
            std::puts("INTERACTIVE_GAME_MENU_ACTIVATED_MODS=0|SESSION_MANIFEST");lua_newtable(state);return 1;
        }
        if(std::strcmp(operation,"gameMenuModPropertyContains")==0){
            if(lua_gettop(state)!=3)throw std::invalid_argument("GameMenu mod property query requires a property and value");
            self.RequireEmptyMenuModManifest();const char* property=Text(state,2);
            if((std::strcmp(property,"DisableQuickSave")!=0 && std::strcmp(property,"DisableLoadGameOption")!=0 &&
                std::strcmp(property,"DisableSaveGameOption")!=0) || std::strcmp(Text(state,3),"1")!=0)
                throw std::invalid_argument("GameMenu mod property query differs from the original saving policy");
            lua_pushboolean(state,false);return 1;
        }
        if(std::strcmp(operation,"gameMenuModProperty")==0){
            if(lua_gettop(state)!=4 || Integer(state,3)<1 || std::strcmp(Text(state,4),"Name")!=0)
                throw std::invalid_argument("GameMenu mod name query requires its original ID, version and Name tuple");
            self.RequireEmptyMenuModManifest();
            if(!self.host_.activeMods->Contains(Text(state,2)))
                throw std::invalid_argument("GameMenu requested the property of a mod absent from the activation manifest");
            throw std::logic_error("Nonempty GameMenu activation properties require the versioned mod manifest implementation");
        }
        if(std::strcmp(operation,"gameMenuMapPreview")==0 || std::strcmp(operation,"loadMenuMapPreview")==0){
            const bool loadPreview=std::strcmp(operation,"loadMenuMapPreview")==0;
            if(loadPreview)self.RequireLoadMenuOwner();else self.RequireGameMenuOwner();
            if(lua_gettop(state)!=2)throw std::invalid_argument("Menu map preview requires its original map filename");
            int status=0;
            {
                const char* filename=Text(state,2);std::string original;
                if(loadPreview){
                    Utf8Length(filename);
                    const auto identity=NormalizedMenuMapPath(filename);
                    for(const auto& file:self.loadMenuCatalog_->files){
                        if(!file.header || NormalizedMenuMapPath(file.header->mapScript.c_str())!=identity)continue;
                        if(!original.empty() && original!=file.header->mapScript)
                            throw std::invalid_argument("LoadMenu preview has ambiguous original map path aliases");
                        original=file.header->mapScript;
                    }
                    if(original.empty())
                        throw std::invalid_argument("LoadMenu preview map is absent from its immutable known-header catalog");
                    // This profile already requires the exact current bundle.
                    // Still bind preview permission to a listed observed header,
                    // and resolve only a frozen Lua map, never a WorldBuilder file.
                    if(identity.size()<4 || identity.compare(identity.size()-4,4,".lua")!=0 ||
                       !self.scripts_.HasFile(original.c_str()))
                        throw std::logic_error("LoadMenu preview requires its registered frozen Lua map; WorldBuilder preview is unsupported");
                }else{
                    const CvString current=self.pregame_->mapScriptName();original=current.c_str();
                    if(NormalizedMenuMapPath(filename)!=NormalizedMenuMapPath(original.c_str()))
                        throw std::invalid_argument("GameMenu preview must retain the actual SDK map identity");
                    if(self.pregame_->isWBMapScript() || !self.scripts_.HasFile(original.c_str()))
                        throw std::logic_error("GameMenu preview requires the frozen script map; WorldBuilder file resolution is not connected");
                }
                auto* loader=self.core_->GetWorldBuilderMapLoader();
                if(!loader)throw std::runtime_error("SDK WorldBuilder preview interface is unavailable");
                // The interface is a borrowed singleton. Its SDK query returns
                // nil for this actual script map, rather than fabricating a preview.
                GameMenuMapPreviewCall call{loader,loadPreview?original.c_str():filename};status=lua_cpcall(state,&ReadGameMenuMapPreview,&call);
            }
            if(status)return lua_error(state);
            lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_GAME_MENU_MAP_PREVIEW");
            std::printf("%s=SDK_QUERY|%s\n",loadPreview?"INTERACTIVE_LOAD_MENU_MAP_PREVIEW":"INTERACTIVE_GAME_MENU_MAP_PREVIEW",lua_isnil(state,-1)?"nil":"table");
            lua_pushnil(state);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_GAME_MENU_MAP_PREVIEW");return 1;
        }
        if(std::strcmp(operation,"gameMenuInterfaceMode")==0){
            self.RequireGameMenuOwner();
            if(lua_gettop(state)!=2 || Integer(state,2)!=static_cast<int>(INTERFACEMODE_SELECTION))
                throw std::invalid_argument("Original GameMenu only restores the selection interface mode");
            self.frontend_.setInterfaceMode(INTERFACEMODE_SELECTION);return 0;
        }
        if(std::strcmp(operation,"gameMenuCursor")==0){
            self.RequireGameMenuOwner();
            if(lua_gettop(state)!=2 || !self.gameMenuInput_ || !self.dispatching_)
                throw std::logic_error("GameMenu cursor changes require its original input callback");
            const int token=Integer(state,2);
            if(token!=0 && token!=1)throw std::invalid_argument("GameMenu cursor supports only original arrow/wait tokens");
            const auto cursor=LoadCursorW(nullptr,MAKEINTRESOURCEW(token==1?32514:32512));
            if(!cursor)throw std::runtime_error("Original GameMenu cursor could not be loaded");
            const int previous=self.gameMenuCursorToken_;SetCursor(cursor);self.gameMenuCursorToken_=token;
            lua_pushinteger(state,previous);return 1;
        }
        if(std::strcmp(operation,"notificationPanelTouchScreen")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::NotificationPanel)
                throw std::logic_error("Touch availability belongs to the original NotificationPanel host query");
            lua_pushboolean(state,GetSystemMetrics(SM_MAXIMUMTOUCHES)>0);return 1;
        }
        if(std::strcmp(operation,"notificationPanelRows")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::NotificationPanel || !self.externalRouting_)
                throw std::logic_error("Notification rows require the original world NotificationPanel");
            const auto owner=self.game_->GetActivePlayer();
            if(owner<0 || owner>=MAX_PLAYERS)throw std::logic_error("NotificationPanel active player is invalid");
            std::vector<NotificationPresentation> rows;
            {std::lock_guard<std::mutex> guard(self.host_.dataMutex);
             for(const auto& item:self.host_.notifications)if(item.second.player==owner)rows.push_back(item.second);}
            // Lua allocations are protected so a failed table build cannot
            // unwind across the owned copied notification vector.
            const int status=lua_cpcall(state,&PushNotificationRows,&rows);
            if(status)throw std::runtime_error("Cannot copy the owned SDK notification rows into Lua");
            lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_NOTIFICATION_ROWS");
            lua_pushnil(state);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_NOTIFICATION_ROWS");return 1;
        }
        if(std::strcmp(operation,"notificationPanelActivateNotification")==0 ||
           std::strcmp(operation,"notificationPanelRemoveNotification")==0){
            if(lua_gettop(state)!=2 || self.kind_!=UiPopupKind::NotificationPanel)
                throw std::invalid_argument("NotificationPanel request requires its original notification ID");
            const int id=Integer(state,2);if(id<0)throw std::invalid_argument("Notification ID is negative");
            self.RequireActionInfoInput();
            bool exists=false;
            {std::lock_guard<std::mutex> guard(self.host_.dataMutex);
             exists=self.host_.notifications.find({self.actionInfoOwner_,id})!=self.host_.notifications.end();}
            // An SDK notification can expire before a queued click reaches its
            // original callback. Consume that old UI action without faulting
            // the persistent VM or issuing a gameplay command.
            if(!exists){
                std::printf("INTERACTIVE_NOTIFICATION_REQUEST_REJECTED=%d|%d|%d|EXPIRED_SDK_NOTIFICATION\n",
                    id,self.actionInfoOwner_,self.actionInfoTurn_);
                lua_pushboolean(state,false);return 1;
            }
            self.QueueActionInfoRequest(std::strcmp(operation,"notificationPanelActivateNotification")==0?
                ActionInfoRequest::Kind::ActivateNotification:ActionInfoRequest::Kind::RemoveNotification,id);
            lua_pushboolean(state,true);return 1;
        }
        if(std::strcmp(operation,"actionInfoCanEndTurn")==0 || std::strcmp(operation,"actionInfoWaitingForRemotePlayers")==0 ||
           std::strcmp(operation,"actionInfoMultiplayer")==0 || std::strcmp(operation,"actionInfoNetTurnComplete")==0 ||
           std::strcmp(operation,"actionInfoNetTurnAllComplete")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::ActionInfoPanel ||
               self.game_->IsGameMultiPlayer() || self.game_->IsNetworkMultiPlayer())
                throw std::logic_error("ActionInfoPanel query requires its actual singleplayer context");
            if(std::strcmp(operation,"actionInfoCanEndTurn")==0)lua_pushboolean(state,self.frontend_.canEndTurn());
            else if(std::strcmp(operation,"actionInfoWaitingForRemotePlayers")==0)lua_pushboolean(state,self.frontend_.waitingForRemotePlayers());
            else if(std::strcmp(operation,"actionInfoMultiplayer")==0)lua_pushboolean(state,self.game_->IsGameMultiPlayer());
            // Singleplayer has no network turn-completion barrier. This is a
            // guarded network-profile fact, never an invented gameplay readiness.
            else lua_pushboolean(state,false);
            return 1;
        }
        if(std::strcmp(operation,"actionInfoActivateNotification")==0 || std::strcmp(operation,"actionInfoRemoveNotification")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("ActionInfoPanel notification request requires its original ID");
            const int id=Integer(state,2);
            if(id<0)throw std::invalid_argument("ActionInfoPanel blocking notification ID is negative");
            const auto kind=std::strcmp(operation,"actionInfoActivateNotification")==0?
                ActionInfoRequest::Kind::ActivateNotification:ActionInfoRequest::Kind::RemoveNotification;
            self.QueueActionInfoRequest(kind,id);return 0;
        }
        if(std::strcmp(operation,"actionInfoEndTurn")==0){
            if(lua_gettop(state)!=2 || Integer(state,2)!=static_cast<int>(CONTROL_ENDTURN) ||
               self.actionInfoInputKind_!=UiInputKind::LeftClick)
                throw std::invalid_argument("ActionInfoPanel may only queue original left-click end-turn control");
            self.QueueActionInfoRequest(ActionInfoRequest::Kind::EndTurn,static_cast<int>(CONTROL_ENDTURN));return 0;
        }
        if(std::strcmp(operation,"actionInfoSelectUnit")==0){
            if(lua_gettop(state)!=3)throw std::invalid_argument("ActionInfoPanel unit request requires owner and ID");
            self.RequireActionInfoInput();const int owner=Integer(state,2),id=Integer(state,3);
            if(owner!=self.actionInfoOwner_ || id<0)throw std::invalid_argument("ActionInfoPanel selected unit owner is stale");
            {std::unique_ptr<ICvPlayer1> player(self.game_->GetPlayer(static_cast<PlayerTypes>(owner)));
             std::unique_ptr<ICvUnit1> unit(player?player->GetUnit(id):nullptr);
             if(!unit || unit->GetOwner()!=owner)throw std::invalid_argument("ActionInfoPanel selected SDK unit is missing");}
            self.QueueActionInfoRequest(ActionInfoRequest::Kind::SelectUnit,id);return 0;
        }
        if(std::strcmp(operation,"actionInfoLookAt")==0){
            if(lua_gettop(state)!=4)throw std::invalid_argument("ActionInfoPanel camera request requires its original plot and type");
            self.RequireActionInfoInput();const int x=Integer(state,2),y=Integer(state,3),type=Integer(state,4);
            if(type!=static_cast<int>(CAMERALOOKAT_NORMAL))throw std::invalid_argument("ActionInfoPanel changed its original normal camera request");
            {std::unique_ptr<ICvMap1> map(self.core_->GetMap());std::unique_ptr<ICvPlot1> plot(map?map->GetPlot(x,y):nullptr);
             if(!plot)throw std::invalid_argument("ActionInfoPanel camera target is not an actual SDK plot");}
            self.QueueActionInfoRequest(ActionInfoRequest::Kind::LookAt,type,x,y);return 0;
        }
        if(std::strcmp(operation,"actionInfoGameplayFx")==0){
            if(lua_gettop(state)!=4 || Integer(state,4)!=-1)
                throw std::invalid_argument("ActionInfoPanel GameplayFX requires its original two hex coordinates and -1");
            self.RequireActionInfoInput();const int x=Integer(state,2),y=Integer(state,3);
            self.host_.Record("ui-action-info-gameplay-fx-unrendered:"+std::to_string(x)+":"+std::to_string(y));return 0;
        }
        if(std::strcmp(operation,"economicChildHidden")==0){
            if(self.kind_!=UiPopupKind::EconomicOverview || self.economicOwner_ || lua_gettop(state)!=3 ||
               lua_type(state,3)!=LUA_TBOOLEAN || (!self.initializingEconomic_ && !self.dispatching_))
                throw std::logic_error("Economic child visibility must come from its original parent callback");
            const char* controlId=Text(state,2);
            const int slot=std::strcmp(controlId,"EconomicGeneralInfo")==0?1:
                std::strcmp(controlId,"HappinessInfo")==0?2:0;
            if(slot<1 || slot>2)throw std::invalid_argument("Economic child visibility ID is outside the two original contexts");
            self.economicChildVisible_[slot-1]=lua_toboolean(state,3)==0;
            self.economicChildVisibilityDirty_[slot-1]=true;
            return 0;
        }
        if(std::strcmp(operation,"economicChooseProduction")==0){
            if(self.kind_!=UiPopupKind::EconomicGeneral || !self.economicOwner_ || self.economicSlot_!=1 ||
               lua_gettop(state)!=2 || !self.economicInput_ || self.economicInputKind_!=UiInputKind::LeftClick || !self.dispatching_ || !self.active_ ||
               !self.economicOwner_->active_ || self.economicOwner_->economicProductionPending_ ||
               self.economicOwner_->economicOwnerId_!=self.game_->GetActivePlayer() ||
               self.economicOwner_->economicTurn_!=self.game_->GetGameTurn())
                throw std::logic_error("Economic production request must come from the visible original child input");
            const int cityId=Integer(state,2),owner=self.game_->GetActivePlayer();
            if(owner<0 || owner>=MAX_PLAYERS || cityId<0)throw std::invalid_argument("Economic production request has an invalid city");
            std::unique_ptr<ICvPlayer1> player(self.game_->GetPlayer(static_cast<PlayerTypes>(owner)));
            std::unique_ptr<ICvCity1> city(player?player->GetCity(cityId):nullptr);
            if(!player || !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive() || !city || city->GetOwner()!=owner)
                throw std::logic_error("Economic production request lost its original active human city");
            const bool puppet=city->IsPuppet();
            self.economicOwner_->pendingEconomicProductionCity_=puppet?-1:cityId;
            self.economicOwner_->economicProductionPending_=true;
            std::printf("INTERACTIVE_ECONOMIC_PRODUCTION_REQUEST=%d|%d|%u|%d\n",owner,cityId,puppet?1u:0u,self.game_->GetGameTurn());
            return 0;
        }
        if(std::strcmp(operation,"policyInfo")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::SocialPolicy || !self.host_.policyInfoInitialized)
                throw std::invalid_argument("PolicyInfo requires the frozen original policy context option");
            lua_pushboolean(state,self.host_.policyInfo);return 1;
        }
        if(std::strcmp(operation,"cachePolicyInfo")==0){
            self.RequirePolicyInput();
            if(lua_gettop(state)!=2 || lua_type(state,2)!=LUA_TBOOLEAN || self.policyInfoCachePending_ || self.policyCommand_)
                throw std::invalid_argument("PolicyInfo cache requires one original checkbox callback");
            self.policyInfoCached_=lua_toboolean(state,2)!=0;self.policyInfoCachePending_=true;return 0;
        }
        if(std::strcmp(operation,"commitPolicyInfo")==0){
            self.RequirePolicyInput();
            if(lua_gettop(state)!=1 || !self.policyInfoCachePending_ || self.policyCommand_ || self.host_.uiOptionsPath.empty())
                throw std::invalid_argument("PolicyInfo commit has no owned cached display preference");
            self.EnsureMenuOptions();
            auto& options=*self.host_.menuOptions;
            if(options.Active())throw std::logic_error("Policy preference cannot overwrite another open options transaction");
            options.Begin(self.policyOwner_,self.game_->GetGameTurn());
            try{
                options.Set("policyInfo",self.policyInfoCached_?1:0);
                options.Apply(self.policyOwner_,self.game_->GetGameTurn(),self.host_.applyMenuOptions,
                    [&self](const MenuOptionsValues& value){self.host_.menuOptionsStore->WriteAtomic(value);});
            }catch(...){if(options.Active() && !options.Faulted())options.Discard();throw;}
            if(self.host_.policyInfo!=self.policyInfoCached_)
                throw std::logic_error("Policy preference backend did not read back the canonical value");
            self.policyInfoCachePending_=false;return 0;
        }
        if(std::strcmp(operation,"updatePolicies")==0){
            self.RequirePolicyInput();
            if(lua_gettop(state)!=4 || lua_type(state,3)!=LUA_TBOOLEAN || lua_type(state,4)!=LUA_TBOOLEAN ||
               !lua_toboolean(state,4) || self.policyCommand_ || self.policyInfoCachePending_)
                throw std::invalid_argument("Policy adoption requires one original confirmed update");
            const int id=Integer(state,2);
            if(id<0)throw std::invalid_argument("Original policy or branch identifier is negative");
            self.policyCommand_.reset(new PolicyCommand{self.policyOwner_,id,self.game_->GetGameTurn(),
                lua_toboolean(state,3)!=0,true,false});return 0;
        }
        if(std::strcmp(operation,"changeIdeology")==0){
            self.RequirePolicyInput();
            if(lua_gettop(state)!=1 || self.policyCommand_ || self.policyInfoCachePending_)
                throw std::invalid_argument("Ideology change requires one original confirmation");
            self.policyCommand_.reset(new PolicyCommand{self.policyOwner_,-1,self.game_->GetGameTurn(),false,true,true});return 0;
        }
        if(std::strcmp(operation,"policyAudio")==0){
            self.RequirePolicyInput();
            if(lua_gettop(state)!=2 || std::strcmp(Text(state,2),"AS2D_INTERFACE_POLICY")!=0 ||
               !self.policyCommand_ || self.pendingPolicySound_)
                throw std::invalid_argument("Policy audio requires its original queued confirmation callback");
            self.pendingPolicySound_=true;return 0;
        }
        if(std::strcmp(operation,"numCurrentDeals")==0 || std::strcmp(operation,"loadCurrentDeal")==0){
            const bool load=std::strcmp(operation,"loadCurrentDeal")==0;
            if(lua_gettop(state)!=(load?3:2) || self.kind_!=UiPopupKind::DeclareWar)
                throw std::invalid_argument("Invalid original current-deal query");
            const int player=Integer(state,2);
            if(player!=self.game_->GetActivePlayer())throw std::invalid_argument("Current deals must belong to the active player");
            self.EnsureDeals();const auto count=self.deals_->GetNumCurrentDeals(static_cast<PlayerTypes>(player));
            if(!load){lua_pushnumber(state,static_cast<lua_Number>(count));return 1;}
            const int index=Integer(state,3);
            if(index<0 || static_cast<unsigned>(index)>=count)throw std::invalid_argument("Current-deal index is outside the SDK list");
            self.EnsureScratchDeal();
            std::unique_ptr<ICvDeal1> current(self.deals_->GetCurrentDeal(static_cast<PlayerTypes>(player),static_cast<unsigned>(index)));
            if(!current)throw std::runtime_error("Current SDK deal disappeared before the UI copied it");
            self.scratchDeal_->CopyFrom(current.get());return 0;
        }
        if(std::strcmp(operation,"scratchDeal")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Invalid scratch-deal query arity");
            self.EnsureScratchDeal();
            const int status=lua_cpcall(state,&PushScratchDeal,&self);
            if(status)return lua_error(state);
            lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_SCRATCH_RESULT");
            lua_pushnil(state);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_SCRATCH_RESULT");return 1;
        }
        if(std::strcmp(operation,"declareWarChange")==0){
            if(lua_gettop(state)!=3 || lua_type(state,3)!=LUA_TBOOLEAN || !lua_toboolean(state,3))
                throw std::invalid_argument("Original declaration must carry a team and true");
            self.RequireWarInput();self.warCommands_.push_back({WarCommandKind::Change,Integer(state,2),1});return 0;
        }
        if(std::strcmp(operation,"declareWarDiplo")==0){
            if(lua_gettop(state)!=5)throw std::invalid_argument("Original war diplomacy callback needs its four arguments");
            self.RequireWarInput();self.warCommands_.push_back({WarCommandKind::Diplomacy,Integer(state,2),Integer(state,3),Integer(state,4),Integer(state,5)});return 0;
        }
        if(std::strcmp(operation,"declareWarMove")==0){
            if(lua_gettop(state)!=6)throw std::invalid_argument("Original confirmed war movement needs plot and three flags");
            for(int index=4;index<=6;++index)if(lua_type(state,index)!=LUA_TBOOLEAN || lua_toboolean(state,index))
                throw std::invalid_argument("Original confirmed war movement clears all modifier flags");
            self.RequireWarInput();self.warCommands_.push_back({WarCommandKind::Move,Integer(state,2),Integer(state,3)});return 0;
        }
        if(std::strcmp(operation,"declareWarMission")==0){
            if(lua_gettop(state)!=5)throw std::invalid_argument("Original war ranged callback needs its four arguments");
            self.RequireWarInput();self.warCommands_.push_back({WarCommandKind::Mission,Integer(state,2),Integer(state,3),Integer(state,4),Integer(state,5)});return 0;
        }
        if(std::strcmp(operation,"declareWarInterfaceMode")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("Original war callback needs its final interface mode");
            self.RequireWarInput();self.warCommands_.push_back({WarCommandKind::InterfaceMode,Integer(state,2)});return 0;
        }
        if(std::strcmp(operation,"activatedModEntryPoints")==0){
            if(lua_gettop(state)!=2 ||
               !((self.kind_==UiPopupKind::LeaderHead && std::strcmp(Text(state,2),"DiplomacyUIAddin")==0) ||
                 (self.kind_==UiPopupKind::CityView && std::strcmp(Text(state,2),"CityViewUIAddin")==0)))
                throw std::invalid_argument("Activated entry-point query differs from the original UI context");
            if(!self.host_.activeMods || self.host_.activeMods->Size()!=0)
                throw std::runtime_error("Diplomacy UI entry points require an authoritative empty active-mod manifest");
            std::printf("UI_ACTIVE_MOD_ENTRY_POINTS=%s|0\n",Text(state,2));lua_newtable(state);return 1;
        }
        if(std::strcmp(operation,"leaderName")==0 || std::strcmp(operation,"civilizationShortDescription")==0){
            if(lua_gettop(state)!=2 || self.kind_!=UiPopupKind::LeaderHead)
                throw std::invalid_argument("Leader identity query requires the original LeaderHead context and one player");
            const int id=Integer(state,2);
            if(id<0 || id>=MAX_PLAYERS)throw std::invalid_argument("Leader identity query has an invalid player slot");
            int status=0;
            {
                std::string copied;
                const CvString value=std::strcmp(operation,"leaderName")==0?
                    self.pregame_->leaderName(static_cast<PlayerTypes>(id)):
                    self.pregame_->civilizationShortDescription(static_cast<PlayerTypes>(id));
                copied.assign(value.data(),value.size());
                TextResult result{copied.data(),copied.size()};
                status=lua_cpcall(state,&PushText,&result);
            }
            if(status)return lua_error(state);
            lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");
            lua_pushnil(state);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");return 1;
        }
        if(std::strcmp(operation,"snapshotJson")==0){
            if(lua_gettop(state)!=3 || lua_type(state,2)!=LUA_TTABLE || lua_type(state,3)!=LUA_TTABLE)
                throw std::invalid_argument("Invalid UI snapshot JSON arity or tables");
            int status=0;
            {
                const auto output=UiSnapshotJson::Encode(state,2,3);
                TextResult value{output.data(),output.size()};
                status=lua_cpcall(state,&PushText,&value);
            }
            if(status)return lua_error(state);
            lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");
            lua_pushnil(state);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");return 1;
        }
        if(std::strcmp(operation,"locale")==0){
            int status=0;
            {
                const auto output=Localize(state);TextResult value{output.data(),output.size()};
                // Keep C++ ownership outside the protected Lua allocation. A Lua
                // OOM returns normally before the string's destructor executes.
                status=lua_cpcall(state,&PushText,&value);
            }
            if(status)return lua_error(state);
            lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");
            lua_pushnil(state);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");return 1;
        }
        if(std::strcmp(operation,"localeNumber")==0 || std::strcmp(operation,"localeUpper")==0 || std::strcmp(operation,"localeLower")==0 ||
           std::strcmp(operation,"localeSubstring")==0 || std::strcmp(operation,"localeTruncate")==0){
            if(std::strcmp(operation,"localeNumber")==0 &&
               self.kind_!=UiPopupKind::EconomicGeneral && self.kind_!=UiPopupKind::EconomicHappiness)
                throw std::invalid_argument("UI number formatting is restricted to original EconomicOverview child contexts");
            int status=0;
            {const auto output=TextOperation(state,operation);TextResult value{output.data(),output.size()};
             status=lua_cpcall(state,&PushText,&value);}
            if(status)return lua_error(state);
            lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");
            lua_pushnil(state);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_TEXT_RESULT");return 1;
        }
        if(std::strcmp(operation,"localeLength")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("Invalid UI length arity");
            const auto length=Utf8Length(Text(state,2));lua_pushnumber(state,static_cast<lua_Number>(length));return 1;
        }
        if(std::strcmp(operation,"localeCompare")==0){
            if(lua_gettop(state)!=3)throw std::invalid_argument("Invalid UI comparison arity");
            const char* a=Text(state,2);const char* b=Text(state,3);Utf8Length(a);Utf8Length(b);int result=0;
            if(!Localization::GetCurrentLanguage().Compare(a,std::strlen(a),b,std::strlen(b),result))
                throw std::runtime_error("UI localized comparison failed");
            lua_pushinteger(state,result);return 1;
        }
        if(std::strcmp(operation,"localeEndsWith")==0){
            if(lua_gettop(state)!=3)throw std::invalid_argument("Invalid UI suffix arity");
            const char* a=Text(state,2);const char* b=Text(state,3);Utf8Length(a);Utf8Length(b);
            const auto bytes=std::strlen(a),suffix=std::strlen(b);
            lua_pushboolean(state,suffix<=bytes && std::memcmp(a+bytes-suffix,b,suffix)==0);return 1;
        }
        if(std::strcmp(operation,"screenSize")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Invalid logical UI viewport arity");
            lua_pushinteger(state,1920);lua_pushinteger(state,1080);return 2;
        }
        if(std::strcmp(operation,"pantheonContext")==0){
            if(self.kind_!=UiPopupKind::Pantheon || lua_gettop(state)!=1)
                throw std::invalid_argument("Pantheon context query requires its original context");
            lua_pushinteger(state,self.pantheonOwner_);lua_pushinteger(state,self.pantheonTurn_);
            lua_pushinteger(state,self.pantheonGeneration_);lua_pushinteger(state,self.pantheonCommandsApplied_);return 4;
        }
        if(std::strcmp(operation,"pantheonHudVisibility")==0){
            if(self.kind_!=UiPopupKind::Pantheon || lua_gettop(state)!=3 ||
               std::strcmp(Text(state,2),"/InGame/WorldView/UnitPanel/Base")!=0 || lua_type(state,3)!=LUA_TBOOLEAN)
                throw std::invalid_argument("Pantheon HUD request differs from the original UnitPanel lookup");
            self.pantheonUnitPanelHidden_=lua_toboolean(state,3)!=0;return 0;
        }
        if(std::strcmp(operation,"foundPantheon")==0){
            self.RequirePantheonOwner(true);
            if(lua_gettop(state)!=3 || !self.pantheonInput_ || !self.dispatching_ || self.pantheonCommand_ ||
               self.pantheonCommandsApplied_ || self.pantheonEntryBelief_<0 ||
               Integer(state,2)!=self.pantheonOwner_ || Integer(state,3)!=self.pantheonEntryBelief_)
                throw std::logic_error("Pantheon request differs from its captured original confirmation");
            self.pantheonCommand_.reset(new PantheonCommand{self.pantheonOwner_,self.pantheonEntryBelief_,self.pantheonTurn_,self.pantheonGeneration_,self.revision_});
            return 0;
        }
        if(std::strcmp(operation,"pantheonAudio")==0){
            if(lua_gettop(state)!=2 || !self.pantheonInput_ || !self.dispatching_ || !self.pantheonCommand_ ||
               self.pendingPantheonSound_ || !self.host_.uiAudio || std::strcmp(Text(state,2),"AS2D_INTERFACE_POLICY")!=0)
                throw std::logic_error("Pantheon cue requires its queued original confirmation");
            self.pendingPantheonSound_=true;return 0;
        }
        if(std::strcmp(operation,"uiFrameTime")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Invalid UI owner clock arity");
            lua_pushnumber(state,self.frameTime_);return 1;
        }
        if(std::strcmp(operation,"headSelectedCity")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Invalid UI selected city arity");
            int owner=-1,city=-1;
            {std::unique_ptr<ICvCity1> selected(self.frontend_.getHeadSelectedCity());
             if(selected){owner=selected->GetOwner();city=selected->GetID();}}
            if(owner<0){lua_pushnil(state);lua_pushnil(state);}else{lua_pushinteger(state,owner);lua_pushinteger(state,city);}return 2;
        }
        if(std::strcmp(operation,"activePlayer")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::TopPanel)
                throw std::invalid_argument("Active-player query requires the original TopPanel");
            const int player=self.game_->GetActivePlayer();
            if(player<0 || player>=MAX_PLAYERS)throw std::logic_error("TopPanel has no active player");
            lua_pushinteger(state,player);return 1;
        }
        if(std::strcmp(operation,"queueTopPanelPopup")==0){
            if(lua_gettop(state)!=3 || self.kind_!=UiPopupKind::TopPanel || !self.active_ || self.faulted_ ||
               !self.topPanelInput_ || !self.dispatching_ || self.topPanelPopup_ ||
               self.topPanelOwner_!=self.game_->GetActivePlayer() || self.timerState_!=TimerState::Released)
                throw std::logic_error("TopPanel popup requires its original active input callback");
            const int type=Integer(state,2),data2=Integer(state,3);
            if((type!=static_cast<int>(BUTTONPOPUP_TECH_TREE) && type!=static_cast<int>(BUTTONPOPUP_TRADE_ROUTE_OVERVIEW) &&
                type!=static_cast<int>(BUTTONPOPUP_CHOOSEPOLICY) && type!=static_cast<int>(BUTTONPOPUP_ECONOMIC_OVERVIEW)) || data2!=-1)
                throw std::invalid_argument("TopPanel overview context is not connected yet");
            const int data0=type==static_cast<int>(BUTTONPOPUP_ECONOMIC_OVERVIEW)?self.topPanelOwner_:-1;
            self.topPanelPopup_.reset(new CvPopupInfo(static_cast<ButtonPopupTypes>(type),data0,-1));return 0;
        }
        if(std::strcmp(operation,"isTouchScreen")==0){
            if(lua_gettop(state)!=1 || (self.kind_!=UiPopupKind::UnitPanel && self.kind_!=UiPopupKind::GameMenu))
                throw std::invalid_argument("Invalid original UI device query");
            lua_pushboolean(state,self.kind_==UiPopupKind::GameMenu?GetSystemMetrics(SM_MAXIMUMTOUCHES)>0:false);return 1;
        }
        if(std::strcmp(operation,"unitPanelAction")==0){
            if(lua_gettop(state)!=2 || self.kind_!=UiPopupKind::UnitPanel || !self.unitInput_ ||
               !self.active_ || !self.dispatching_ || self.faulted_ || self.unitAction_)
                throw std::logic_error("UnitPanel action requires its original input callback");
            const int action=Integer(state,2);
            if(action<0)throw std::invalid_argument("Original action index is negative");
            std::unique_ptr<ICvUnit1> unit(self.frontend_.GetHeadSelectedUnit());
            if(!unit)throw std::logic_error("UnitPanel action lost its selected unit");
            UnitActionCommand command{static_cast<int>(unit->GetOwner()),unit->GetID(),self.game_->GetGameTurn(),action};
            self.ValidateUnitSelection(command);
            self.unitAction_.reset(new UnitActionCommand(command));return 0;
        }
        if(std::strcmp(operation,"cityScreenViewingMode")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Invalid CityView mode arity");
            lua_pushboolean(state,self.frontend_.IsCityScreenViewingMode());return 1;
        }
        if(std::strcmp(operation,"setCityScreenViewingMode")==0){
            if(lua_gettop(state)!=2 || lua_type(state,2)!=LUA_TBOOLEAN ||
               (self.kind_!=UiPopupKind::CityCapture && self.kind_!=UiPopupKind::CityView))
                throw std::invalid_argument("Invalid CityView mode request");
            const bool value=lua_toboolean(state,2)!=0;
            if(value && (self.kind_!=UiPopupKind::CityCapture || !self.active_ || !self.cityViewBarrier_))
                throw std::logic_error("Viewing mode requires the queued original EmptyPopup barrier");
            self.frontend_.SetCityScreenViewingMode(value);return 0;
        }
        if(std::strcmp(operation,"cityViewBarrier")==0){
            if(lua_gettop(state)!=2 || lua_type(state,2)!=LUA_TBOOLEAN || self.kind_!=UiPopupKind::CityCapture ||
               !self.active_ || self.captureDecisionDone_ || self.pendingCaptureAction_)
                throw std::logic_error("CityView barrier requires an unresolved captured-city popup");
            const bool value=lua_toboolean(state,2)!=0;
            if(value==self.cityViewBarrier_)throw std::logic_error("Duplicate CityView barrier transition");
            self.cityViewBarrier_=value;return 0;
        }
        if(std::strcmp(operation,"selectCityAtPlot")==0){
            if(lua_gettop(state)!=3 || self.kind_!=UiPopupKind::CityCapture || !self.active_ ||
               !self.cityViewBarrier_ || self.pendingCityView_ || self.captureDecisionDone_ || !self.frontend_.IsCityScreenViewingMode())
                throw std::logic_error("CityView selection requires its original captured-city callback");
            const int x=Integer(state,2),y=Integer(state,3);
            {std::unique_ptr<ICvMap1> map(self.core_->GetMap());std::unique_ptr<ICvPlot1> plot(map?map->GetPlot(x,y):nullptr);
             std::unique_ptr<ICvCity1> city(plot?plot->GetPlotCity():nullptr);
             if(!city || city->GetOwner()!=self.captureOwner_ || city->GetID()!=self.captureCity_)
                 throw std::invalid_argument("CityView selection differs from its captured city");
             self.frontend_.selectCity(city.get(),false);self.frontend_.setCityScreenUp(true);}
            self.pendingCityView_=true;return 0;
        }
        if(std::strcmp(operation,"cityScreenUp")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Invalid CityView visibility arity");
            lua_pushboolean(state,self.frontend_.isCityScreenUp());return 1;
        }
        if(std::strcmp(operation,"clearSelectedCities")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::CityView)throw std::invalid_argument("Invalid city selection clear");
            self.frontend_.clearSelectedCities();return 0;
        }
        if(std::strcmp(operation,"exitCityScreen")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::CityView || self.cityViewExit_ ||
               self.frontend_.isCityScreenUp() || self.frontend_.IsCityScreenViewingMode())
                throw std::logic_error("CityView exit did not release its original selection and viewing mode");
            self.cityViewExit_=true;return 0;
        }
        if(std::strcmp(operation,"updateCityCitizens")==0){
            if(lua_gettop(state)!=2 || self.kind_!=UiPopupKind::CityView || self.pendingCityCitizens_ ||
               Integer(state,2)!=self.cityViewCity_ || self.cityViewOwner_!=self.game_->GetActivePlayer())
                throw std::invalid_argument("City citizen update differs from original selected CityView");
            self.pendingCityCitizens_=true;return 0;
        }
        if(std::strcmp(operation,"cityProductionPopup")==0){
            if(lua_gettop(state)!=7 || self.kind_!=UiPopupKind::CityView || !self.active_ ||
               self.cityViewReadOnly_ || self.cityProductionRequest_ || self.pendingCitySetting_ || !self.cityCommands_.empty() || self.cityViewOwner_!=self.game_->GetActivePlayer() ||
               Integer(state,2)!=BUTTONPOPUP_CHOOSEPRODUCTION || Integer(state,3)!=self.cityViewCity_ ||
               Integer(state,4)!=-1 || Integer(state,5)!=-1 || lua_type(state,6)!=LUA_TBOOLEAN || lua_type(state,7)!=LUA_TBOOLEAN)
                throw std::invalid_argument("Production popup differs from its original owned-city request");
            self.cityProductionRequest_.reset(new CvPopupInfo(BUTTONPOPUP_CHOOSEPRODUCTION,self.cityViewCity_,-1,-1,0,
                lua_toboolean(state,6)!=0,lua_toboolean(state,7)!=0));
            return 0;
        }
        if(std::strcmp(operation,"citySetFocus")==0 || std::strcmp(operation,"citySetAvoidGrowth")==0){
            if(lua_gettop(state)!=3 || self.kind_!=UiPopupKind::CityView || !self.active_ || self.cityViewReadOnly_ ||
               self.pendingCitySetting_ || self.cityProductionRequest_ || !self.cityCommands_.empty() || self.cityViewOwner_!=self.game_->GetActivePlayer() ||
               Integer(state,2)!=self.cityViewCity_ || self.timerState_!=TimerState::Released)
                throw std::invalid_argument("City setting differs from its original selected city callback");
            const bool focus=std::strcmp(operation,"citySetFocus")==0;
            int value=0;
            if(focus){value=Integer(state,3);if(value<NO_CITY_AI_FOCUS_TYPE || value>=NUM_CITY_AI_FOCUS_TYPES)
                throw std::invalid_argument("City focus is outside the original SDK enum");}
            else {if(lua_type(state,3)!=LUA_TBOOLEAN)throw std::invalid_argument("City growth option is not boolean");value=lua_toboolean(state,3)?1:0;}
            self.pendingCitySetting_=focus?1:2;self.pendingCitySettingValue_=value;return 0;
        }
        if(std::strcmp(operation,"ownedCityTask")==0){
            if(lua_gettop(state)!=9)throw std::invalid_argument("Invalid original CityView task arity");
            for(int index=6;index<=9;++index)if(lua_type(state,index)!=LUA_TBOOLEAN)
                throw std::invalid_argument("CityView task modifiers must be normalized original booleans");
            self.QueueCityCommand({CityCommandKind::Task,Integer(state,2),Integer(state,3),Integer(state,4),Integer(state,5),
                lua_toboolean(state,6)!=0,lua_toboolean(state,7)!=0,lua_toboolean(state,8)!=0,lua_toboolean(state,9)!=0});
            return 0;
        }
        if(std::strcmp(operation,"ownedCityBuyPlot")==0 || std::strcmp(operation,"ownedCitySellBuilding")==0){
            const bool buy=std::strcmp(operation,"ownedCityBuyPlot")==0;
            if(lua_gettop(state)!=(buy?4:3))throw std::invalid_argument("Invalid original CityView purchase/sell arity");
            self.QueueCityCommand({buy?CityCommandKind::BuyPlot:CityCommandKind::SellBuilding,
                Integer(state,2),Integer(state,3),buy?Integer(state,4):0});return 0;
        }
        if(std::strcmp(operation,"audioPlay2DSound")==0){
            if(self.kind_==UiPopupKind::Production){
                if(lua_gettop(state)!=2 || lua_type(state,2)!=LUA_TSTRING || !self.purchaseCommand_ || self.pendingPurchaseSound_)
                    throw std::invalid_argument("Purchase audio requires its original queued production callback");
                self.RequirePurchaseInput(self.purchaseCommand_->city);
                const char* expected=self.purchaseCommand_->yield==YIELD_GOLD?"AS2D_INTERFACE_CITY_SCREEN_PURCHASE":"AS2D_INTERFACE_FAITH_PURCHASE";
                if(std::strcmp(lua_tostring(state,2),expected)!=0)
                    throw std::invalid_argument("Purchase audio differs from the original purchase currency");
                self.pendingPurchaseSound_=true;return 0;
            }
            if(lua_gettop(state)!=2 || lua_type(state,2)!=LUA_TSTRING ||
               std::strcmp(lua_tostring(state,2),"AS2D_INTERFACE_BUY_TILE")!=0 ||
               self.kind_!=UiPopupKind::CityView || !self.dispatching_ || !self.host_.deferCityTask ||
               self.pendingBuyTileSound_ || self.cityCommands_.size()!=1 ||
               self.cityCommands_.front().kind!=CityCommandKind::BuyPlot)
                throw std::invalid_argument("Tile-purchase audio requires its original queued CityView purchase callback");
            self.pendingBuyTileSound_=true;return 0;
        }
        if(std::strcmp(operation,"interfaceMode")==0){
            if(self.kind_!=UiPopupKind::CityView || (lua_gettop(state)!=1 && lua_gettop(state)!=2))
                throw std::invalid_argument("Invalid CityView interface mode arity");
            if(lua_gettop(state)==2)self.frontend_.setInterfaceMode(static_cast<InterfaceModeTypes>(Integer(state,2)));
            lua_pushinteger(state,static_cast<int>(self.frontend_.getInterfaceMode()));return 1;
        }
        if(std::strcmp(operation,"headSelectedUnit")==0 || std::strcmp(operation,"lastSelectedUnit")==0){
            // CityView already uses this selection contract during entry and
            // exit. Share the read-only head query with the non-modal panel;
            // last-selected restoration remains owned by CityView.
            const bool head=std::strcmp(operation,"headSelectedUnit")==0;
            if(lua_gettop(state)!=1 || (self.kind_!=UiPopupKind::CityView &&
                !(head && (self.kind_==UiPopupKind::UnitPanel || self.kind_==UiPopupKind::ActionInfoPanel))))
                throw std::invalid_argument("Invalid UI unit selection query");
            int owner=-1,id=-1;
            {std::unique_ptr<ICvUnit1> unit(head?self.frontend_.GetHeadSelectedUnit():self.frontend_.getLastSelectedUnit());
             if(unit){owner=unit->GetOwner();id=unit->GetID();}}
            if(owner<0){lua_pushnil(state);lua_pushnil(state);}else{lua_pushinteger(state,owner);lua_pushinteger(state,id);}return 2;
        }
        if(std::strcmp(operation,"selectUnit")==0){
            if(lua_gettop(state)!=3 || self.kind_!=UiPopupKind::CityView)throw std::invalid_argument("Invalid CityView unit restore");
            const int owner=Integer(state,2),id=Integer(state,3);
            if(owner!=self.game_->GetActivePlayer() || id<0)throw std::invalid_argument("CityView unit restore owner is stale");
            {std::unique_ptr<ICvPlayer1> player(self.game_->GetPlayer(static_cast<PlayerTypes>(owner)));
             std::unique_ptr<ICvUnit1> unit(player?player->GetUnit(id):nullptr);
             if(!unit)throw std::invalid_argument("CityView prior unit no longer exists");
             self.game_->SelectUnit(unit.get(),true,false,false);}return 0;
        }
        if(std::strcmp(operation,"lookAtSelectionPlot")==0){
            if(lua_gettop(state)!=1 || (self.kind_!=UiPopupKind::CityView && self.kind_!=UiPopupKind::UnitPanel))throw std::invalid_argument("Invalid selected-plot camera request");
            {std::unique_ptr<ICvUnit1> unit(self.frontend_.GetHeadSelectedUnit());std::unique_ptr<ICvPlot1> plot(unit?unit->GetPlot():nullptr);
             if(!plot)throw std::logic_error("Selected-unit camera request has no live plot");
             self.frontend_.lookAt(plot.get(),CAMERALOOKAT_NORMAL);}return 0;
        }
        if(std::strcmp(operation,"noBasicHelp")==0 || std::strcmp(operation,"noCitizenWarning")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Invalid frontend option arity");
            // Private Host presentation preferences; retail INI files are not read.
            lua_pushboolean(state,std::strcmp(operation,"noBasicHelp")==0 && self.host_.menuOptions && self.host_.menuOptions->Committed().noBasicHelp);return 1;
        }
        if(std::strcmp(operation,"cityPlotPosition")==0 || std::strcmp(operation,"cityViewProjection")==0){
            const bool project=std::strcmp(operation,"cityPlotPosition")==0;
            if(self.kind_!=UiPopupKind::CityView || lua_gettop(state)!=(project?3:1))
                throw std::invalid_argument("Invalid CityView projection request");
            int cx=0,cy=0,width=0,height=0;bool wrapX=false,wrapY=false;int owner=-1,cityID=-1;
            {std::unique_ptr<ICvMap1> map(self.core_->GetMap());std::unique_ptr<ICvCity1> city(self.frontend_.getHeadSelectedCity());
             if(!map || !city)throw std::logic_error("CityView projection has no selected live city");
             std::unique_ptr<ICvPlot1> plot(city->Plot());
             if(!plot)throw std::logic_error("CityView projection city has no plot");
             plot->GetPosition(cx,cy);width=map->GetGridWidth();height=map->GetGridHeight();wrapX=map->IsWrapX();wrapY=map->IsWrapY();
             owner=city->GetOwner();cityID=city->GetID();}
#if defined(ZEROSIS_WORLD_TERRAIN)
            const auto& terrainProjection=self.host_.cityWorldProjection;
            const bool terrainReady=terrainProjection.ready && terrainProjection.cameraX==cx && terrainProjection.cameraY==cy &&
                terrainProjection.gridWidth==width && terrainProjection.gridHeight==height && terrainProjection.mapWidth==1920;
#endif
            if(project){
                const int x=Integer(state,2),y=Integer(state,3);
                if(x<0 || x>=width || y<0 || y>=height)throw std::invalid_argument("CityView projection plot is outside map");
#if defined(ZEROSIS_WORLD_TERRAIN)
                if(terrainReady){
                    const auto found=terrainProjection.plots.find(y*width+x);
                    // Missing/occluded centers stay outside the viewport. Never
                    // manufacture a flat-map click target over hidden terrain.
                    const bool visible=found!=terrainProjection.plots.end() && found->second.anchorVisible;
                    lua_pushnumber(state,visible?found->second.centerX:-1000000);
                    lua_pushnumber(state,visible?found->second.centerY:-1000000);lua_pushnumber(state,0);return 3;
                }
#endif
                int dx=x-cx,dy=y-cy;
                if(wrapX){if(dx>width/2)dx-=width;else if(dx<-width/2)dx+=width;}
                if(wrapY){if(dy>height/2)dy-=height;else if(dy<-height/2)dy+=height;}
                lua_pushnumber(state,960.0+dx*84.0+((y&1)-(cy&1))*42.0);
                lua_pushnumber(state,540.0+dy*84.0*1.15470053838*0.75);lua_pushnumber(state,0);return 3;
            }
            lua_newtable(state);
            lua_pushinteger(state,owner);lua_setfield(state,-2,"owner");lua_pushinteger(state,cityID);lua_setfield(state,-2,"city");
            lua_pushboolean(state,self.frontend_.IsCityScreenViewingMode());lua_setfield(state,-2,"viewingMode");
            lua_pushboolean(state,false);lua_setfield(state,-2,"retailWorldProjectionVerified");
            lua_newtable(state);
#if defined(ZEROSIS_WORLD_TERRAIN)
            if(terrainReady){
                lua_pushliteral(state,"ZEROSIS_D3D11_CITY_VIEW_RASTER_V1");lua_setfield(state,-2,"policy");
                lua_pushnumber(state,static_cast<lua_Number>(terrainProjection.frameGeneration));lua_setfield(state,-2,"frameGeneration");
                lua_pushinteger(state,1920);lua_setfield(state,-2,"viewportWidth");lua_pushinteger(state,1080);lua_setfield(state,-2,"viewportHeight");
                lua_pushinteger(state,terrainProjection.mapWidth);lua_setfield(state,-2,"mapWidth");
                lua_newtable(state);
                for(const auto& item:terrainProjection.plots){
                    lua_newtable(state);lua_pushnumber(state,item.second.centerX);lua_setfield(state,-2,"centerX");
                    lua_pushnumber(state,item.second.centerY);lua_setfield(state,-2,"centerY");
                    lua_pushboolean(state,item.second.anchorVisible);lua_setfield(state,-2,"anchorVisible");
                    lua_newtable(state);int spanIndex=0;
                    for(const auto& span:item.second.spans){
                        lua_newtable(state);for(int i=0;i<3;++i){lua_pushinteger(state,span[static_cast<std::size_t>(i)]);lua_rawseti(state,-2,i+1);}
                        lua_rawseti(state,-2,++spanIndex);
                    }
                    lua_setfield(state,-2,"spans");lua_setfield(state,-2,std::to_string(item.first).c_str());
                }
                lua_setfield(state,-2,"plots");
            }else
#endif
            {lua_pushliteral(state,"ZEROSIS_2D_CITY_VIEW_V1");lua_setfield(state,-2,"policy");}
            lua_pushinteger(state,cx);lua_setfield(state,-2,"cameraX");lua_pushinteger(state,cy);lua_setfield(state,-2,"cameraY");
            lua_pushinteger(state,width);lua_setfield(state,-2,"gridWidth");lua_pushinteger(state,height);lua_setfield(state,-2,"gridHeight");
            lua_pushboolean(state,wrapX);lua_setfield(state,-2,"wrapX");lua_pushboolean(state,wrapY);lua_setfield(state,-2,"wrapY");
            lua_pushnumber(state,84);lua_setfield(state,-2,"tileWidth");lua_pushnumber(state,960);lua_setfield(state,-2,"centerX");
            lua_pushnumber(state,540);lua_setfield(state,-2,"centerY");lua_setfield(state,-2,"projection");return 1;
        }
        if(std::strcmp(operation,"tutorialRequest")==0){
            if(self.kind_!=UiPopupKind::CityView || lua_gettop(state)!=3 || std::strcmp(Text(state,2),"CITY_SCREEN")!=0 ||
               lua_type(state,3)!=LUA_TBOOLEAN)throw std::invalid_argument("Invalid tutorial event observation");
            std::printf("UI_TUTORIAL_EVENT_UNHANDLED=CITY_SCREEN|%s|NO_REGISTERED_TUTORIAL_CONTEXT\n",lua_toboolean(state,3)?"queue":"dismiss");
            return 0;
        }
        if(std::strcmp(operation,"optionalCityIncludeExists")==0){
            if(self.kind_!=UiPopupKind::CityView || lua_gettop(state)!=2 || std::strcmp(Text(state,2),"TutorialPopupScreen")!=0)
                throw std::invalid_argument("Unexpected optional CityView include");
            const bool found=self.scripts_.HasFile("TutorialPopupScreen");
            if(!found)std::puts("UI_OPTIONAL_INCLUDE_MISSING=TutorialPopupScreen|NO_SOURCE_IN_FROZEN_CATALOG");
            lua_pushboolean(state,found);return 1;
        }
        if(std::strcmp(operation,"unitPortrait")==0){
            if(lua_gettop(state)!=3)throw std::invalid_argument("Invalid unit portrait arity");
            const int unit=Integer(state,2);
            // Stock TechButtonInclude omits the optional portrait owner.
            const int owner=lua_isnil(state,3)?static_cast<int>(self.game_->GetActivePlayer()):Integer(state,3);
            if(unit<0 || unit>=self.core_->GetNumUnitInfos() || owner<0 || owner>=MAX_PLAYERS)
                throw std::invalid_argument("Invalid unit portrait identity");
            {std::unique_ptr<ICvUnitInfo1> info(self.core_->GetUnitInfo(static_cast<UnitTypes>(unit)));
             std::unique_ptr<ICvPlayer1> player(self.game_->GetPlayer(static_cast<PlayerTypes>(owner)));
             if(!info || !player || !player->IsAlive())throw std::invalid_argument("Unit portrait lacks actual SDK rules/player");}
            // Public ICvUnitInfo has no portrait fields. Read the actual owned
            // rules VM; cultural/era portrait remapping remains an explicit gate.
            lua_getglobal(state,"GameInfo");lua_getfield(state,-1,"Units");lua_pushinteger(state,unit);lua_gettable(state,-2);
            if(!lua_istable(state,-1))throw std::runtime_error("Unit portrait rules row is missing");
            lua_getfield(state,-1,"PortraitIndex");const int index=Integer(state,-1);lua_pop(state,1);
            if(index<0)throw std::runtime_error("Unit portrait index is negative");
            lua_pushinteger(state,index);lua_getfield(state,-2,"IconAtlas");Text(state,-1);return 2;
        }
        if(std::strcmp(operation,"specificCityInfoDirty")==0){
            if(lua_gettop(state)!=4)throw std::invalid_argument("Invalid city refresh arity");
            const int owner=Integer(state,2),cityID=Integer(state,3),update=Integer(state,4);
            if(owner<0 || owner>=MAX_PLAYERS || cityID<0 || update<0 || update>=NUM_CITY_UPDATE_TYPES)
                throw std::invalid_argument("Invalid city refresh identity/type");
            {std::unique_ptr<ICvPlayer1> player(self.game_->GetPlayer(static_cast<PlayerTypes>(owner)));
             std::unique_ptr<ICvCity1> city(player?player->GetCity(cityID):nullptr);
             if(!city || city->GetOwner()!=static_cast<PlayerTypes>(owner))throw std::invalid_argument("City refresh refers to an absent city");
             self.frontend_.SetSpecificCityInfoDirty(city.get(),static_cast<CityUpdateTypes>(update));}
            return 0;
        }
        if(std::strcmp(operation,"lookAt")==0){
            if(lua_gettop(state)!=4)throw std::invalid_argument("Invalid camera request arity");
            const int x=Integer(state,2),y=Integer(state,3),type=Integer(state,4);
            {std::unique_ptr<ICvMap1> map(self.core_->GetMap());std::unique_ptr<ICvPlot1> plot(map?map->GetPlot(x,y):nullptr);
             if(!plot)throw std::invalid_argument("Camera request has no actual map plot");
             self.frontend_.lookAt(plot.get(),static_cast<CameraLookAtTypes>(type));}
            return 0;
        }
        if(std::strcmp(operation,"smallUiAssets")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("SmallUIAssets takes no arguments");
            lua_pushboolean(state,self.smallUiAssets_);return 1;
        }
        if(std::strcmp(operation,"uiShift")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::ResearchTree)
                throw std::invalid_argument("UI shift observation requires the owned research tree");
            lua_pushboolean(state,false);return 1;
        }
        if(std::strcmp(operation,"requestTechTree")==0){
            if(lua_gettop(state)!=3 || Integer(state,2)!=static_cast<int>(BUTTONPOPUP_TECH_TREE) || Integer(state,3)!=-1)
                throw std::invalid_argument("Only the original normal research-tree popup request is supported");
        if(self.kind_!=UiPopupKind::Research || !self.active_ || self.faulted_ ||
           self.timerState_!=TimerState::Released || self.researchTreeRequested_ || self.deferredPopupReady_)
            throw std::logic_error("Research tree requires a closed original chooser and one deferred owner request");
            self.requestedTreeSteal_=Integer(state,3);self.researchTreeRequested_=true;
            if(self.externalRouting_)self.deferredPopupReady_=true;
            self.host_.Record("ui-popup-request:TechTree:"+std::to_string(static_cast<int>(BUTTONPOPUP_TECH_TREE))+":-1");return 0;
        }
        if(std::strcmp(operation,"sendResearch")==0){
            if(lua_gettop(state)!=5 || lua_type(state,5)!=LUA_TBOOLEAN)
                throw std::invalid_argument("Network.SendResearch requires its original four arguments");
            if(!self.IsResearch() || !self.active_ || self.faulted_ || !self.host_.localSdkSessionBound ||
               self.timerState_!=(self.RetainsTimer()?TimerState::Held:TimerState::Released))
                throw std::logic_error("Research requires the active owned TechPopup and bound SDK receiver");
            const int tech=Integer(state,2),discover=Integer(state,3),steal=Integer(state,4);
            const bool shift=lua_toboolean(state,5)!=0;
            if(tech<0)throw std::invalid_argument("Research technology is negative");
            if(discover!=0 || steal!=-1 || shift)
                throw std::invalid_argument("Only normal local research selection is supported");
            EngineServices engine(self.hostOwner_);
            engine.sendResearch(static_cast<TechTypes>(tech),discover,static_cast<PlayerTypes>(steal),shift);
            if(self.kind_==UiPopupKind::ResearchTree)self.researchDirtyPending_=true;
            return 0;
        }
        if(std::strcmp(operation,"leaderRootUp")==0){
            if(self.kind_!=UiPopupKind::LeaderHead)
                throw std::invalid_argument("Leader-root state is outside its owned context");
            if(lua_gettop(state)==1){lua_pushboolean(state,self.host_.leaderRootUp);return 1;}
            if(lua_gettop(state)!=2 || lua_type(state,2)!=LUA_TBOOLEAN)
                throw std::invalid_argument("Invalid original leader-root visibility request");
            const bool up=lua_toboolean(state,2)!=0;
            if(up && (!self.leaderMessage_ || self.leaderDecisionDone_))
                throw std::logic_error("Leader root has no owned SDK message");
            self.host_.leaderRootUp=up;return 0;
        }
        if(std::strcmp(operation,"uiCursor")==0){
            if((self.kind_!=UiPopupKind::LeaderHead && self.kind_!=UiPopupKind::DeclareWar) || lua_gettop(state)!=2 || Integer(state,2)!=0)
                throw std::invalid_argument("This frontend provides its default arrow cursor token only");
            // The retained frontend starts and remains on its default cursor.
            // Retail cursor shapes and alternate cursor tokens are not mapped.
            lua_pushinteger(state,0);return 1;
        }
        if(std::strcmp(operation,"leaveLeader")==0){
            if(self.kind_!=UiPopupKind::LeaderHead || !self.leaderMessage_ || !self.active_ || self.faulted_ ||
               self.leaderDecisionDone_ || self.pendingLeaderLeave_ || lua_gettop(state)!=1 ||
               self.leaderMessage_->receiver!=self.game_->GetActivePlayer() || self.timerState_!=TimerState::Released)
                throw std::logic_error("Leader return requires its active original message callback");
            self.pendingLeaderLeave_=true;return 0;
        }
        if(std::strcmp(operation,"sendCityTask")==0 || std::strcmp(operation,"sendCityLiberation")==0){
            if(self.kind_!=UiPopupKind::CityCapture || !self.active_ || self.faulted_ || self.captureDecisionDone_ ||
               self.pendingCaptureAction_!=0 || !self.host_.localSdkSessionBound || self.timerState_!=TimerState::Released ||
               self.captureOwner_!=self.game_->GetActivePlayer())
                throw std::logic_error("City decision requires its active original capture popup");
            const bool task=std::strcmp(operation,"sendCityTask")==0;
            if(lua_gettop(state)!=(task?9:3))throw std::invalid_argument("Invalid captured-city command arity");
            if(task){
                const int city=Integer(state,2),kind=Integer(state,3);
                if(city!=self.captureCity_ || Integer(state,4)!=-1 || Integer(state,5)!=-1 ||
                   (kind!=TASK_RAZE && kind!=TASK_CREATE_PUPPET && kind!=TASK_ANNEX_PUPPET))
                    throw std::invalid_argument("Captured-city task differs from its original popup payload");
                for(int index=6;index<=9;++index)if(lua_type(state,index)!=LUA_TBOOLEAN || lua_toboolean(state,index))
                    throw std::invalid_argument("Captured-city task has unsupported modifiers");
                self.pendingCaptureTask_=static_cast<TaskTypes>(kind);self.pendingCaptureAction_=1;
            }else{
                if(Integer(state,2)!=self.captureLiberated_ || self.captureLiberated_<0 || Integer(state,3)!=self.captureCity_)
                    throw std::invalid_argument("Liberation differs from the SDK capture eligibility payload");
                self.pendingCaptureAction_=2;
            }
            // Do not enter a second SDK Lua query while this UI VM is on-stack.
            // DispatchInput validates and commits after the stock callback exits.
            return 0;
        }
        if(std::strcmp(operation,"searchForPediaEntry")==0)
            Unsupported("UI encyclopedia requires its official retained context");
        if(std::strcmp(operation,"requirePurchaseInput")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("Invalid purchase input arity");
            self.RequirePurchaseInput(Integer(state,2));return 0;
        }
        if(std::strcmp(operation,"civilization")==0 || std::strcmp(operation,"playerColor")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("Invalid PreGame UI adapter arity");
            const int id=Integer(state,2);
            if(id<NO_PLAYER || id>=MAX_PLAYERS)throw std::invalid_argument("Invalid UI player slot");
            const int value=id==NO_PLAYER?-1:(operation[0]=='c'?
                static_cast<int>(self.pregame_->civilization(static_cast<PlayerTypes>(id))):
                static_cast<int>(self.pregame_->playerColor(static_cast<PlayerTypes>(id))));
            lua_pushinteger(state,value);return 1;
        }
        if(std::strcmp(operation,"timer")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("Invalid UI timer adapter arity");
            const int delta=Integer(state,2);
            if(delta==1 && self.timerState_==TimerState::Released){
                self.timerState_=TimerState::TransitionUnknown;
                self.game_->EndTurnTimerSemaphoreIncrement();
                self.timerState_=TimerState::Held;return 0;
            }
            if(delta==-1 && self.timerState_==TimerState::Held){
                self.timerState_=TimerState::TransitionUnknown;
                self.game_->EndTurnTimerSemaphoreDecrement();
                self.timerState_=TimerState::Released;return 0;
            }
            throw std::logic_error("Unbalanced native UI timer request");
        }
        if(std::strcmp(operation,"randomSeed")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Invalid UI RNG observation arity");
            unsigned long value=0;
            {
                std::unique_ptr<ICvRandom1> random(self.game_->GetRandomNumberGenerator());
                if(!random)throw std::runtime_error("GameCore synchronous RNG interface is missing");
                value=random->GetSeed();
            }
            lua_pushnumber(state,static_cast<lua_Number>(value));return 1;
        }
        throw std::invalid_argument(std::string("Unknown native UI adapter request: ")+operation);
    }
    static void Field(lua_State* state,const char* name,int value){lua_pushinteger(state,value);lua_setfield(state,-2,name);}
    static int Dispatch(lua_State* state){
        const auto* popup=static_cast<const OwnedPopupInfo*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"Submit");lua_newtable(state);
        Field(state,"Type",static_cast<int>(popup->type));Field(state,"Flags",popup->flags);
        char field[32];
        for(std::size_t index=0;index<popup->data.size();++index){
            std::snprintf(field,sizeof(field),"Data%zu",index+1);Field(state,field,popup->data[index]);
        }
        for(std::size_t index=0;index<popup->options.size();++index){
            std::snprintf(field,sizeof(field),"Option%zu",index+1);
            lua_pushboolean(state,popup->options[index]);lua_setfield(state,-2,field);
        }
        lua_pushlstring(state,popup->text.data(),popup->text.size());lua_setfield(state,-2,"Text");
        lua_call(state,1,0);return 0;
    }
    static int DispatchLeader(lua_State* state){
        const auto* message=static_cast<const OwnedLeaderMessage*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"SubmitLeader");lua_newtable(state);
        Field(state,"player",static_cast<int>(message->player));Field(state,"state",static_cast<int>(message->state));
        Field(state,"animation",static_cast<int>(message->animation));Field(state,"data1",message->data1);
        lua_pushlstring(state,message->text.data(),message->text.size());lua_setfield(state,-2,"text");
        lua_call(state,1,0);return 0;
    }
    static int DispatchWarStateChanged(lua_State* state){
        const auto* change=static_cast<const OwnedWarStateChanged*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!change)throw std::invalid_argument("Owned LeaderHead war-state event is missing");
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"WarStateChanged");
        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("LeaderHead war-state Lua entry point is missing");
        lua_pushinteger(state,static_cast<int>(change->first));lua_pushinteger(state,static_cast<int>(change->second));
        lua_pushboolean(state,change->war);lua_call(state,3,0);return 0;
    }
    static int Close(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"Close");lua_call(state,0,0);return 0;
    }
    static int OpenGameMenuLua(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"OpenGameMenu");
        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("Original GameMenu entry bridge is missing");
        lua_call(state,0,0);return 0;
    }
    static int OpenExitConfirmLua(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"OpenExitConfirm");
        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("Original ExitConfirm entry bridge is missing");
        lua_call(state,0,0);return 0;
    }
    static int OpenSaveMenuLua(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"OpenSaveMenu");
        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("Original SaveMenu entry bridge is missing");
        lua_call(state,0,0);return 0;
    }
    static int OpenLoadMenuLua(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"OpenLoadMenu");
        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("Original LoadMenu entry bridge is missing");
        lua_call(state,0,0);return 0;
    }
    static int ObserveSaveMenuTextInputLua(lua_State* state){
        auto* enabled=static_cast<bool*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"IsTextInputEnabled");
        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("Original SaveMenu text focus export is missing");
        lua_call(state,0,1);
        if(!enabled || lua_type(state,-1)!=LUA_TBOOLEAN)throw std::runtime_error("SaveMenu text focus observation is invalid");
        *enabled=lua_toboolean(state,-1)!=0;return 0;
    }
    static int ObserveSaveMenuTextInputFocusLua(lua_State* state){
        auto* token=static_cast<std::uint64_t*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"GetTextInputFocusToken");
        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("Original SaveMenu focus lifetime export is missing");
        lua_call(state,0,1);
        if(!token || lua_type(state,-1)!=LUA_TNUMBER)throw std::runtime_error("SaveMenu focus lifetime is not numeric");
        const lua_Number value=lua_tonumber(state,-1);
        if(!std::isfinite(static_cast<double>(value)) || value<0 || value>9007199254740991.0 || std::floor(value)!=value)
            throw std::runtime_error("SaveMenu focus lifetime is not an exact nonnegative integer");
        *token=static_cast<std::uint64_t>(value);return 0;
    }
    static int CloseGameMenuLua(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"CloseGameMenu");
        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("Original GameMenu return bridge is missing");
        lua_call(state,0,0);return 0;
    }
    struct GameMenuNoticeCall {const std::string* action;const std::string* message;};
    static int ShowGameMenuUnavailableLua(lua_State* state){
        const auto* input=static_cast<const GameMenuNoticeCall*>(lua_touserdata(state,1));
        if(!input || !input->action || !input->message)throw std::invalid_argument("GameMenu notice input is missing");
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"ShowGameMenuUnavailable");
        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("GameMenu unavailable notice bridge is missing");
        lua_pushlstring(state,input->action->data(),input->action->size());
        lua_pushlstring(state,input->message->data(),input->message->size());lua_call(state,2,0);return 0;
    }
    static int ObserveActive(lua_State* state){
        auto* active=static_cast<bool*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"IsActive");lua_call(state,0,1);
        if(!active || lua_type(state,-1)!=LUA_TBOOLEAN)throw std::runtime_error("UI active observation is invalid");
        *active=lua_toboolean(state,-1)!=0;return 0;
    }
    static int RefreshTopPanelLua(lua_State* state){
        auto* active=static_cast<bool*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisTopPanelRefresh");lua_call(state,0,1);
        if(!active || lua_type(state,-1)!=LUA_TBOOLEAN)throw std::runtime_error("Original TopPanel refresh did not report visibility");
        *active=lua_toboolean(state,-1)!=0;return 0;
    }
    static int RefreshActionInfoPanelLua(lua_State* state){
        auto* active=static_cast<bool*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"actionInfoPanelRefresh");lua_call(state,0,1);
        if(!active || lua_type(state,-1)!=LUA_TBOOLEAN)throw std::runtime_error("Original ActionInfoPanel refresh did not report visibility");
        *active=lua_toboolean(state,-1)!=0;return 0;
    }
    static int StopActionInfoPanelLua(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"actionInfoPanelStop");lua_call(state,0,0);return 0;
    }
    static int RefreshNotificationPanelLua(lua_State* state){
        auto* active=static_cast<bool*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"notificationPanelRefresh");lua_call(state,0,1);
        if(!active || lua_type(state,-1)!=LUA_TBOOLEAN)throw std::runtime_error("Original NotificationPanel refresh did not report visibility");
        *active=lua_toboolean(state,-1)!=0;return 0;
    }
    static int StopNotificationPanelLua(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"notificationPanelStop");lua_call(state,0,0);return 0;
    }
    static int StopTopPanel(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisTopPanelStop");lua_call(state,0,0);return 0;
    }
    static int RefreshUnitPanelLua(lua_State* state){
        auto* active=static_cast<bool*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"unitPanelRefresh");lua_call(state,0,1);
        if(!active || lua_type(state,-1)!=LUA_TBOOLEAN)throw std::runtime_error("Original UnitPanel refresh did not report visibility");
        *active=lua_toboolean(state,-1)!=0;return 0;
    }
    static int SetEconomicVisibilityLua(lua_State* state){
        const auto* request=static_cast<const EconomicVisibilityRequest*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!request)throw std::invalid_argument("Economic child visibility request is missing");
        lua_getglobal(state,"ZeroSisEconomicSetVisible");
        if(!lua_isfunction(state,-1))throw std::runtime_error("Original embedded EconomicOverview visibility entry point is missing");
        lua_pushboolean(state,request->visible);lua_pushboolean(state,request->initialize);lua_call(state,2,0);return 0;
    }
    static int RefreshEconomicLua(lua_State* state){
        auto* active=static_cast<bool*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisEconomicRefresh");
        if(!lua_isfunction(state,-1))throw std::runtime_error("Original EconomicOverview refresh entry point is missing");
        lua_call(state,0,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"IsActive");lua_call(state,0,1);
        if(!active || lua_type(state,-1)!=LUA_TBOOLEAN)throw std::runtime_error("Original EconomicOverview refresh did not report visibility");
        *active=lua_toboolean(state,-1)!=0;return 0;
    }
    static int StopUnitPanel(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"unitPanelStop");lua_call(state,0,0);return 0;
    }
    static int AbortCapture(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"AbortCapture");lua_call(state,0,0);return 0;
    }
    static int ReadCapturePuppetKey(lua_State* state){
        auto* key=static_cast<std::uint64_t*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"FindCaptureButton");
        lua_pushliteral(state,"TXT_KEY_POPUP_PUPPET_CAPTURED_CITY");lua_call(state,1,1);
        const double value=lua_tonumber(state,-1);
        if(!key || lua_type(state,-1)!=LUA_TNUMBER || !std::isfinite(value) || value<1 ||
           value>static_cast<double>(UiInputDispatch::MaxExactLuaInteger) || std::floor(value)!=value)
            return luaL_error(state,"Captured-city puppet button key is invalid");
        *key=static_cast<std::uint64_t>(value);return 0;
    }
    static int EnterCityView(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"EnterCityView");lua_call(state,0,0);return 0;
    }
    static int RefreshCityView(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"RefreshCityView");lua_call(state,0,0);return 0;
    }
    static int CityProductionVisibility(lua_State* state){
        auto* hidden=static_cast<bool*>(lua_touserdata(state,1));
        if(!hidden)return luaL_error(state,"City production visibility payload is missing");
        const bool value=*hidden;lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");
        lua_getfield(state,-1,"CityProductionVisibility");lua_pushboolean(state,value);lua_call(state,1,0);return 0;
    }
    static int CityViewReturned(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"ReturnFromCityView");lua_call(state,0,0);return 0;
    }
    static int ReadCaptureViewKey(lua_State* state){
        auto* key=static_cast<std::uint64_t*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"FindCaptureButton");
        lua_pushliteral(state,"TXT_KEY_POPUP_VIEW_CITY");lua_call(state,1,1);
        const int value=Integer(state,-1);if(!key || value<1)return luaL_error(state,"Captured-city View button key is invalid");
        *key=static_cast<std::uint64_t>(value);return 0;
    }
    static int ReadCityViewExitKey(lua_State* state){
        auto* key=static_cast<std::uint64_t*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"FindCityViewExitButton");lua_call(state,0,1);
        const int value=Integer(state,-1);if(!key || value<1)return luaL_error(state,"CityView return button key is invalid");
        *key=static_cast<std::uint64_t>(value);return 0;
    }
    static int AbortLeader(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"AbortLeader");lua_call(state,0,0);return 0;
    }
    static int ReadLeaderBackKey(lua_State* state){
        auto* key=static_cast<std::uint64_t*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"FindLeaderBackButton");lua_call(state,0,1);
        const double value=lua_tonumber(state,-1);
        if(!key || lua_type(state,-1)!=LUA_TNUMBER || !std::isfinite(value) || value<1 ||
           value>static_cast<double>(UiInputDispatch::MaxExactLuaInteger) || std::floor(value)!=value)
            return luaL_error(state,"Leader return button key is invalid");
        *key=static_cast<std::uint64_t>(value);return 0;
    }
    static int ResearchDirty(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"Events");lua_getfield(state,-1,"SerialEventResearchDirty");
        lua_call(state,0,0);return 0;
    }
    static int PolicyDirty(lua_State* state){
        lua_settop(state,0);lua_getglobal(state,"Events");lua_getfield(state,-1,"EventPoliciesDirty");
        lua_call(state,0,0);return 0;
    }
    static int CurrentResearch(lua_State* state){
        auto* output=static_cast<int*>(lua_touserdata(state,1));lua_settop(state,0);
        static const char source[]=R"lua(return assert(Players[Game.GetActivePlayer()]):GetCurrentResearch())lua";
        if(luaL_loadbuffer(state,source,sizeof(source)-1,"Actual selected research"))return lua_error(state);
        lua_call(state,0,1);if(!output)return luaL_error(state,"Research output is missing");
        *output=Integer(state,-1);return 0;
    }
    static int ObserveTreeScroll(lua_State* state){
        auto* output=static_cast<TreeScrollObservation*>(lua_touserdata(state,1));lua_settop(state,0);
        static const char source[]=R"lua(
local result
for _,target in ipairs(ZeroSisUi.GetScrollTargets()) do
  if target.id=='TechTreeScrollPanel' then
    assert(not result and target.event=='Scroll' and target.orientation=='horizontal')
    result=target
  end
end
assert(result and type(result.scrollX)=='number' and type(result.maximumScroll)=='number')
return result.key,result.scrollX,result.maximumScroll
)lua";
        if(luaL_loadbuffer(state,source,sizeof(source)-1,"Research-tree measured scroll"))return lua_error(state);
        lua_call(state,0,3);
        if(!output || lua_type(state,-3)!=LUA_TNUMBER ||
           lua_type(state,-2)!=LUA_TNUMBER || lua_type(state,-1)!=LUA_TNUMBER)
            return luaL_error(state,"Invalid measured tree scroll observation");
        const double keyValue=lua_tonumber(state,-3);
        if(!std::isfinite(keyValue) || keyValue<1.0 || keyValue>static_cast<double>(UiInputDispatch::MaxExactLuaInteger) ||
           std::floor(keyValue)!=keyValue)
            return luaL_error(state,"Invalid exact tree scroll target key");
        const auto key=static_cast<std::uint64_t>(keyValue);
        const double offset=lua_tonumber(state,-2),maximum=lua_tonumber(state,-1);
        if(!std::isfinite(offset) || !std::isfinite(maximum) || offset<0 || maximum<offset)
            return luaL_error(state,"Nonfinite or out-of-range tree scroll observation");
        output->key=key;output->offset=offset;output->maximum=maximum;return 0;
    }
    static int LegalProductionUnit(lua_State* state){
        auto* output=static_cast<ProductionChoice*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!output || output->city<0)throw std::invalid_argument("Production fixture city is invalid");
        lua_pushinteger(state,output->city);lua_setglobal(state,"ZeroSisUiFixtureCity");
        static const char source[]=R"lua(
local player=assert(Players[Game.GetActivePlayer()])
assert(player:IsHuman() and player:IsAlive() and player:IsTurnActive())
local city=assert(player:GetCityByID(ZeroSisUiFixtureCity))
assert(city:GetOwner()==Game.GetActivePlayer() and city:GetOrderQueueLength()==0)
local ids={}
for info in GameInfo.Units() do if city:CanTrain(info.ID) then ids[#ids+1]=info.ID end end
table.sort(ids)
local unit=assert(ids[1],'Production fixture has no legal original unit')
local purchased,reason=pcall(Game.CityPurchaseUnit,city,unit,YieldTypes.YIELD_GOLD)
assert(not purchased and type(reason)=='string' and
  reason:find('Purchase requires its original production input callback',1,true),
  'Out-of-input purchase was not rejected before SDK mutation')
return unit
)lua";
        if(luaL_loadbuffer(state,source,sizeof(source)-1,"Original production fixture legal choice"))return lua_error(state);
        lua_call(state,0,1);output->unit=Integer(state,-1);return 0;
    }
    static int LegalResearchTechnology(lua_State* state){
        auto* output=static_cast<ResearchChoice*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!output || output->player<0)throw std::invalid_argument("Research selection has no active player");
        static const char source[]=R"lua(
local player=assert(Players[Game.GetActivePlayer()])
assert(player:IsHuman() and player:IsAlive() and player:IsTurnActive())
assert(player:GetCurrentResearch()==-1 and player:GetNumFreeTechs()==0)
local ids={}
for info in GameInfo.Technologies() do if player:CanResearch(info.ID) then ids[#ids+1]=info.ID end end
table.sort(ids)
return assert(ids[1],'Research selection has no legal original technology')
)lua";
        if(luaL_loadbuffer(state,source,sizeof(source)-1,"Original research legal choice"))return lua_error(state);
        lua_call(state,0,1);output->tech=Integer(state,-1);return 0;
    }
    static int Snapshot(lua_State* state){
        auto* output=static_cast<std::string*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"Snapshot");lua_call(state,0,1);
        if(lua_type(state,-1)!=LUA_TSTRING)throw std::runtime_error("UI snapshot is not text");
        std::size_t bytes=0;const char* value=lua_tolstring(state,-1,&bytes);
        output->assign(value,bytes);return 0;
    }
    static void Budget(lua_State* state,lua_Debug*){
        // The registry slot is installed once before the hook is enabled.
        lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_UI_CONTEXT");
        auto* self=static_cast<UiPopupContext*>(lua_touserdata(state,-1));lua_pop(state,1);
        if(!self || self->instructions_>=self->callInstructionLimit_)luaL_error(state,"UI instruction budget exhausted");
        self->instructions_+=1000;
    }
    enum class CityCommandKind {Task=1,BuyPlot=2,SellBuilding=3,PopOrder=4,SwapOrder=5};
    struct CityCommand {
        CityCommandKind kind;int city;int data1=0,data2=0,data3=0;
        bool option=false,alt=false,shift=false,control=false,afterSpecialistAutomation=false;
    };
    struct PurchaseCommand {int owner,city,unit,building,project,yield,turn;};
    struct UnitActionCommand {int owner,unit,turn,action;};
    struct PolicyCommand {int owner,id,turn;bool isPolicy,value,ideology;};
    struct PantheonCommand {int owner,belief,turn;unsigned generation,revision;};
    struct PantheonEntry {std::uint64_t key;int belief;};
    void RequirePantheonOwner(bool shown){
        if(kind_!=UiPopupKind::Pantheon || faulted_ || !externalRouting_ || !host_.localSdkSessionBound ||
           game_->IsGameMultiPlayer() || pantheonOwner_!=game_->GetActivePlayer() || pantheonTurn_!=game_->GetGameTurn() ||
           pantheonOwner_<0 || pantheonOwner_>=MAX_PLAYERS || !pantheonGeneration_ ||
           (shown && (!active_ || timerState_!=TimerState::Held)))
            throw std::logic_error("Pantheon input lost its captured active local owner or turn");
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(pantheonOwner_)));
        if(!player || !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive())
            throw std::logic_error("Pantheon input requires its living active human turn");
    }
    static int ReadPantheonEntry(lua_State* state){
        auto* entry=static_cast<PantheonEntry*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!entry)throw std::invalid_argument("Pantheon input observation has no owner");
        lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"PantheonInputObservation");
        lua_pushnumber(state,static_cast<lua_Number>(entry->key));lua_call(state,1,1);
        entry->belief=Integer(state,-1);return 0;
    }
    void RequirePolicyOwner(){
        if(kind_!=UiPopupKind::SocialPolicy || !active_ || faulted_ || !externalRouting_ ||
           !host_.localSdkSessionBound || game_->IsGameMultiPlayer() || policyOwner_!=game_->GetActivePlayer() ||
           policyOwner_<0 || policyOwner_>=MAX_PLAYERS || timerState_!=TimerState::Held)
            throw std::logic_error("Policy command lost its active local human popup boundary");
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(policyOwner_)));
        if(!player || !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive())
            throw std::logic_error("Policy command lost its living active human turn");
    }
    void RequirePolicyInput(){
        RequirePolicyOwner();
        if(!policyInput_ || !dispatching_)
            throw std::logic_error("Policy command requires its original input callback");
    }
    void ValidatePolicyOwner(const PolicyCommand& command){
        RequirePolicyOwner();
        if(command.owner!=policyOwner_ || command.turn!=game_->GetGameTurn())
            throw std::logic_error("Policy owner or turn changed before SDK execution");
    }
    static int ValidatePolicyCommand(lua_State* state){
        const auto* command=static_cast<PolicyCommand*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!command)throw std::invalid_argument("Policy validation has no owned command");
        lua_getglobal(state,command->ideology?"ZeroSisPolicyValidateIdeologyChange":"ZeroSisPolicyValidateCommand");
        if(command->ideology)lua_call(state,0,1);
        else {lua_pushinteger(state,command->id);lua_pushboolean(state,command->isPolicy);
              lua_pushboolean(state,command->value);lua_call(state,3,1);}
        if(lua_type(state,-1)!=LUA_TBOOLEAN || !lua_toboolean(state,-1))
            throw std::logic_error("SDK rejected the original policy command before execution");
        return 0;
    }
    static int ReadSelectedPolicyTenet(lua_State* state){
        auto* output=static_cast<int*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!output)throw std::invalid_argument("Selected tenet query has no owned output");
        lua_getglobal(state,"ZeroSisPolicySelectedTenet");lua_call(state,0,1);
        *output=Integer(state,-1);
        if(*output<0)throw std::logic_error("Original selected tenet ID is negative");
        return 0;
    }
    void ValidateUnitSelection(const UnitActionCommand& command){
        if(kind_!=UiPopupKind::UnitPanel || !host_.localSdkSessionBound || game_->IsGameMultiPlayer() ||
           frontend_.isCityScreenUp() || host_.popupVisible || command.owner!=game_->GetActivePlayer() ||
           command.turn!=game_->GetGameTurn() || command.action<0)
            throw std::logic_error("Original unit action lost its local world turn");
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(command.owner)));
        std::unique_ptr<ICvUnit1> unit(frontend_.GetHeadSelectedUnit());
        if(!player || !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive() || !unit ||
           unit->GetOwner()!=command.owner || unit->GetID()!=command.unit)
            throw std::logic_error("Original unit action selection changed before execution");
    }
    static int ValidateUnitAction(lua_State* state){
        auto* command=static_cast<UnitActionCommand*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!command)throw std::invalid_argument("Original unit action has no owned command");
        lua_getglobal(state,"GameInfoActions");lua_rawgeti(state,-1,command->action);
        if(!lua_istable(state,-1))throw std::invalid_argument("Original unit action is absent from the SDK registry");
        lua_settop(state,0);lua_getglobal(state,"Game");lua_getfield(state,-1,"CanHandleAction");
        lua_pushinteger(state,command->action);lua_call(state,1,1);
        if(lua_type(state,-1)!=LUA_TBOOLEAN || !lua_toboolean(state,-1))
            throw std::logic_error("SDK rejected the original unit action before execution");
        return 0;
    }
    void RequirePurchaseInput(int city){
        if(kind_!=UiPopupKind::Production || !active_ || faulted_ || !dispatching_ || !host_.deferCityPurchase ||
           city!=productionCity_ || productionOwner_!=game_->GetActivePlayer() || !host_.localSdkSessionBound ||
           game_->IsGameMultiPlayer())
            throw std::logic_error("Purchase requires its original production input callback");
    }
    static int ValidatePurchaseCommand(lua_State* state){
        auto* command=static_cast<PurchaseCommand*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!command)throw std::invalid_argument("Missing owned purchase command");
        lua_getglobal(state,"ZeroSisValidateProductionPurchase");
        lua_pushinteger(state,command->city);lua_pushinteger(state,command->unit);lua_pushinteger(state,command->building);
        lua_pushinteger(state,command->project);lua_pushinteger(state,command->yield);lua_call(state,5,0);return 0;
    }
    void QueueCityCommand(CityCommand command){
        if(kind_!=UiPopupKind::CityView || !active_ || faulted_ || !dispatching_ || !host_.deferCityTask ||
           cityViewReadOnly_ || cityViewExit_ || pendingCitySetting_ || cityProductionRequest_ ||
           command.city!=cityViewCity_ || cityViewOwner_!=game_->GetActivePlayer() || timerState_!=TimerState::Released)
            throw std::logic_error("City command requires the original editable selected-city input callback");
        if(!cityCommands_.empty()){
            const auto& first=cityCommands_.front();
            if(cityCommands_.size()!=1 || first.kind!=CityCommandKind::Task || first.data1!=TASK_NO_AUTO_ASSIGN_SPECIALISTS ||
               !first.option || command.kind!=CityCommandKind::Task ||
               (command.data1!=TASK_ADD_SPECIALIST && command.data1!=TASK_REMOVE_SPECIALIST))
                throw std::logic_error("CityView callback issued an unexpected command batch");
        }
        cityCommands_.push_back(command);
    }
    void RequireEditableCity(){
        if(kind_!=UiPopupKind::CityView || !active_ || cityViewReadOnly_ || cityViewExit_ ||
           !scripts_.IsQuiescent() || !host_.localSdkSessionBound || game_->IsGameMultiPlayer() ||
           cityViewOwner_!=game_->GetActivePlayer() || frontend_.IsCityScreenViewingMode() || !frontend_.isCityScreenUp())
            throw std::logic_error("City command requires the active local editable city boundary");
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(cityViewOwner_)));
        std::unique_ptr<ICvCity1> city(frontend_.getHeadSelectedCity());
        if(!player || !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive() || !city || city->IsPuppet() ||
           city->GetOwner()!=cityViewOwner_ || city->GetID()!=cityViewCity_)
            throw std::logic_error("City command lost its eligible active human city");
    }
    static int ValidateCityCommand(lua_State* state){
        const auto& command=*static_cast<CityCommand*>(lua_touserdata(state,1));
        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"ValidateCityCommand");
        lua_pushinteger(state,static_cast<int>(command.kind));lua_pushinteger(state,command.city);
        lua_pushinteger(state,command.data1);lua_pushinteger(state,command.data2);lua_pushinteger(state,command.data3);
        lua_pushboolean(state,command.option);lua_pushboolean(state,command.alt);
        lua_pushboolean(state,command.shift);lua_pushboolean(state,command.control);
        lua_pushboolean(state,command.afterSpecialistAutomation);
        lua_call(state,10,0);return 0;
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
        exitConfirmInput_=false;exitConfirmYesInput_=false;exitConfirmCloseInput_=false;exitConfirmClosed_=false;
        saveMenuRequests_.clear();saveMenuReady_=false;saveMenuInput_=false;
        loadMenuRequests_.clear();loadMenuReady_=false;loadMenuInput_=false;RestoreLoadMenuCursor();
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
    std::shared_ptr<HostState> hostOwner_;HostState& host_;ScriptSystem& scripts_;UserInterface frontend_;
    ICvGameContext3* core_;std::wstring directory_;UiPopupKind kind_=UiPopupKind::Ranking;int techAwardTechnology_=-1;
    UiPopupContext* economicOwner_=nullptr;int economicSlot_=-1;
    std::unique_ptr<ICvGame1> game_;std::unique_ptr<ICvPreGame1> pregame_;
    std::unique_ptr<ICvGameDeals1> deals_;std::unique_ptr<ICvDeal1> scratchDeal_;
    std::unique_ptr<ICvScriptSystemUtility1> scriptUtility_;
    unsigned scratchDealId_=0;bool ownsScratchDeal_=false;
    lua_State* warCommandsVm_=nullptr;std::vector<WarCommand> warCommands_;
    int warOwner_=-1,warUnit_=-1,warTurn_=-1,warRival_=-1,warX_=-1,warY_=-1;
    bool warRange_=false,warInput_=false,warDecisionDone_=false;
    lua_State* vm_=nullptr;
    unsigned sequence_=0,instructions_=0,revision_=0,callInstructionLimit_=InstructionBudget;double frameTime_=0.0;
    unsigned researchDirtyDispatches_=0;int requestedTreeSteal_=-1;
    int captureOwner_=-1,captureCity_=-1,captureLiberated_=-1,pendingCaptureAction_=0;
    TaskTypes pendingCaptureTask_=TASK_CREATE_PUPPET;bool captureDecisionDone_=false;
    bool cityViewBarrier_=false,pendingCityView_=false,pendingCityCitizens_=false,cityViewExit_=false;
    int cityViewOwner_=-1,cityViewCity_=-1;
    bool cityViewReadOnly_=true;
    std::unique_ptr<CvPopupInfo> cityProductionRequest_;
    int pendingCitySetting_=0,pendingCitySettingValue_=0;
    std::vector<CityCommand> cityCommands_;
    bool pendingBuyTileSound_=false,pendingPurchaseSound_=false;
    int productionOwner_=-1,productionCity_=-1;
    std::unique_ptr<PurchaseCommand> purchaseCommand_;
    std::unique_ptr<UnitActionCommand> unitAction_;bool unitInput_=false;
    std::unique_ptr<CvPopupInfo> topPanelPopup_;bool topPanelInput_=false;int topPanelOwner_=-1;
    UiInputKind topPanelInputKind_=UiInputKind::KeyDown;
    std::shared_ptr<const UiSaveMenuCatalog> saveMenuCatalog_;
    std::shared_ptr<const UiLoadMenuCatalog> loadMenuCatalog_;
    std::vector<std::string> deletedMenuFiles_;
    std::vector<SaveMenuRequest> saveMenuRequests_;
    bool saveMenuInput_=false,saveMenuReady_=false;
    UiInputKind saveMenuInputKind_=UiInputKind::KeyDown;
    std::vector<LoadMenuRequest> loadMenuRequests_;
    bool loadMenuInput_=false,loadMenuReady_=false;
    UiInputKind loadMenuInputKind_=UiInputKind::KeyDown;
    int loadMenuCursorToken_=0;
    std::vector<GameMenuRequest> gameMenuRequests_;
    int gameMenuOwner_=-1,gameMenuTurn_=-1,gameMenuCursorToken_=0;
    bool gameMenuInput_=false,gameMenuReady_=false;
    UiInputKind gameMenuInputKind_=UiInputKind::KeyDown;
    bool exitConfirmInput_=false,exitConfirmYesInput_=false,exitConfirmCloseInput_=false,exitConfirmClosed_=false;
    UiInputKind exitConfirmInputKind_=UiInputKind::KeyDown;
    std::vector<ActionInfoRequest> actionInfoRequests_;
    bool actionInfoInput_=false,actionInfoReady_=false;int actionInfoOwner_=-1,actionInfoTurn_=-1;
    UiInputKind actionInfoInputKind_=UiInputKind::KeyDown;
    int tradeRouteOwner_=-1;
    int policyOwner_=-1;unsigned policyCommandsApplied_=0;
    int pantheonOwner_=-1,pantheonTurn_=-1,pantheonEntryBelief_=-1;
    unsigned pantheonGeneration_=0,pantheonCommandsApplied_=0;
    std::unique_ptr<PantheonCommand> pantheonCommand_;
    const PantheonCommand* pantheonCommit_=nullptr;
    bool pantheonInput_=false,pendingPantheonSound_=false,pantheonUnitPanelHidden_=false;
    std::unique_ptr<PolicyCommand> policyCommand_;
    bool policyInput_=false,pendingPolicySound_=false,policyInfoCached_=false,policyInfoCachePending_=false;
    std::unique_ptr<OwnedLeaderMessage> leaderMessage_;
    std::array<std::unique_ptr<UiPopupContext>,2> economicChildren_;
    int pendingEconomicProductionCity_=-1,economicOwnerId_=-1,economicTurn_=-1;
    bool initializingEconomic_=false,economicInput_=false,economicVisibilityInitialized_=false;
    UiInputKind economicInputKind_=UiInputKind::KeyDown;
    bool economicProductionPending_=false;
    bool economicChildVisible_[2]={false,false};
    bool economicChildVisibilityDirty_[2]={false,false};
    bool pendingLeaderLeave_=false,leaderDecisionDone_=false;
    TimerState timerState_=TimerState::Released;
    bool active_=false,dispatching_=false,faulted_=false,timerRecoveryFailed_=false,smallUiAssets_=false;
    bool researchDirtyPending_=false,researchTreeRequested_=false,deferredPopupReady_=false;
    bool windowPresentation_=false,displayResize_=false,refreshClosed_=false,liveProduction_=false,externalRouting_=false,stopping_=false,presentationFailed_=false;
    std::string shownSnapshot_;
    #include "UiMenuNative.inc"
};
}

