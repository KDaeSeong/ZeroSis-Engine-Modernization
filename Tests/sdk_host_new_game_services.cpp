// Contract tests for the host services consumed while initializing a new game.
#include "HostServices.h"
#include "ZeroSisHostBinding.h"
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iterator>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using namespace ZeroSisHost;

static unsigned checks=0;
static void Check(bool value,const char* expression,int line){
    ++checks;
    if(!value){std::fprintf(stderr,"FAILED line=%d %s\n",line,expression);std::exit(1);}
}
#define CHECK(value) Check((value),#value,__LINE__)

class PlotFixture final : public ICvPlot1 {
public:
    PlotFixture(int px,int py,FeatureTypes current):x(px),y(py),currentFeature(current){}
    void* DLLCALL QueryInterface(GUID) override { return nullptr; }
    void DLLCALL Destroy() override { ++destroyCalls; }
    TeamTypes DLLCALL GetTeam() const override { return static_cast<TeamTypes>(0); }
    FogOfWarModeTypes DLLCALL GetActiveFogOfWarMode() const override { return static_cast<FogOfWarModeTypes>(0); }
    void DLLCALL UpdateCenterUnit() override {}
    bool DLLCALL IsAdjacent(ICvPlot1*) const override { return false; }
    bool DLLCALL IsRiver() const override { return false; }
    ICvPlot1* DLLCALL GetNeighboringPlot(DirectionTypes) const override { return nullptr; }
    int DLLCALL GetBuildTime(BuildTypes,PlayerTypes) const override { return 0; }
    bool DLLCALL IsVisible(TeamTypes,bool) const override { return false; }
    bool DLLCALL IsCity() const override { return false; }
    bool DLLCALL IsEnemyCity(ICvUnit1*) const override { return false; }
    bool DLLCALL IsFighting() const override { return false; }
    bool DLLCALL IsTradeRoute(PlayerTypes) const override { return false; }
    bool DLLCALL IsImpassable() const override { return false; }
    void DLLCALL GetPosition(int& px,int& py) const override { px=x;py=y; }
    bool DLLCALL IsNEOfRiver() const override { return false; }
    bool DLLCALL IsWOfRiver() const override { return false; }
    bool DLLCALL IsNWOfRiver() const override { return false; }
    FlowDirectionTypes DLLCALL GetRiverEFlowDirection() const override { return static_cast<FlowDirectionTypes>(0); }
    FlowDirectionTypes DLLCALL GetRiverSEFlowDirection() const override { return static_cast<FlowDirectionTypes>(0); }
    FlowDirectionTypes DLLCALL GetRiverSWFlowDirection() const override { return static_cast<FlowDirectionTypes>(0); }
    PlayerTypes DLLCALL GetOwner() const override { return static_cast<PlayerTypes>(0); }
    PlotTypes DLLCALL GetPlotType() const override { return static_cast<PlotTypes>(0); }
    bool DLLCALL IsWater() const override { return false; }
    bool DLLCALL IsHills() const override { return false; }
    bool DLLCALL IsOpenGround() const override { return true; }
    bool DLLCALL IsMountain() const override { return false; }
    TerrainTypes DLLCALL GetTerrainType() const override { return static_cast<TerrainTypes>(0); }
    FeatureTypes DLLCALL GetFeatureType() const override { ++featureReads;return currentFeature; }
    ResourceTypes DLLCALL GetResourceType(TeamTypes) const override { return static_cast<ResourceTypes>(0); }
    int DLLCALL GetNumResource() const override { return 0; }
    ImprovementTypes DLLCALL GetImprovementType() const override { return static_cast<ImprovementTypes>(0); }
    bool DLLCALL IsImprovementPillaged() const override { return false; }
    GenericWorldAnchorTypes DLLCALL GetWorldAnchor() const override { return static_cast<GenericWorldAnchorTypes>(0); }
    int DLLCALL GetWorldAnchorData() const override { return 0; }
    RouteTypes DLLCALL GetRouteType() const override { return static_cast<RouteTypes>(0); }
    bool DLLCALL IsRoutePillaged() const override { return false; }
    ICvCity1* DLLCALL GetPlotCity() const override { return nullptr; }
    ICvCity1* DLLCALL GetWorkingCity() const override { return nullptr; }
    bool DLLCALL IsRevealed(TeamTypes,bool) const override { return false; }
    ImprovementTypes DLLCALL GetRevealedImprovementType(TeamTypes,bool) const override { return static_cast<ImprovementTypes>(0); }
    int DLLCALL GetBuildProgress(BuildTypes) const override { return 0; }
    bool DLLCALL GetAnyBuildProgress() const override { return false; }
    void DLLCALL UpdateLayout(bool) override {}
    ICvUnit1* DLLCALL GetCenterUnit() override { return nullptr; }
    int DLLCALL GetNumUnits() const override { return 0; }
    ICvUnit1* DLLCALL GetUnitByIndex(int) const override { return nullptr; }
    void DLLCALL AddUnit(ICvUnit1*,bool) override {}
    void DLLCALL RemoveUnit(ICvUnit1*,bool) override {}
    const IDInfo* DLLCALL NextUnitNode(const IDInfo*) const override { return nullptr; }
    IDInfo* DLLCALL NextUnitNode(IDInfo*) override { return nullptr; }
    IDInfo* DLLCALL HeadUnitNode() override { return nullptr; }
    int DLLCALL GetPlotIndex() const override { return -1; }
    char DLLCALL GetContinentType() const override { return 0; }
    FAutoArchive& DLLCALL GetSyncArchive() override { throw std::logic_error("Unexpected plot fixture archive access"); }

    const int x,y;
    const FeatureTypes currentFeature;
    mutable unsigned featureReads=0;
    unsigned destroyCalls=0;
};

template<class Operation> static void RejectInvalid(Operation operation){
    bool rejected=false;
    try{operation();}catch(const std::invalid_argument&){rejected=true;}
    CHECK(rejected);
}

static bool SlotIsOpen(HostState& state,PlayerTypes player){
    std::lock_guard<std::mutex> guard(state.dataMutex);
    return state.openPlayerSlots[static_cast<std::size_t>(player)];
}

static void CheckAllSlotsClosed(HostState& state){
    std::lock_guard<std::mutex> guard(state.dataMutex);
    CHECK(std::none_of(state.openPlayerSlots.begin(),state.openPlayerSlots.end(),[](bool open){return open;}));
}

static void SlotStateAndValidation(EngineServices& primary,ICvEngineUtility4& first,ICvEngineUtility4& second,
                                   const std::shared_ptr<HostState>& state){
    const auto regular=static_cast<PlayerTypes>(5);
    const auto boundary=static_cast<PlayerTypes>(MAX_PLAYERS-1);
    first.openSlot(regular);
    CHECK(SlotIsOpen(*state,regular) && !SlotIsOpen(*state,boundary));
    second.closeSlot(regular);
    CHECK(!SlotIsOpen(*state,regular));
    second.openSlot(boundary);
    CHECK(SlotIsOpen(*state,boundary));

    const auto before=state->Events();
    RejectInvalid([&]{first.openSlot(static_cast<PlayerTypes>(-1));});
    RejectInvalid([&]{second.closeSlot(static_cast<PlayerTypes>(MAX_PLAYERS));});
    CHECK(state->Events()==before && !SlotIsOpen(*state,regular) && SlotIsOpen(*state,boundary));

    primary.InitGlobals();
    CHECK(state->globalsStarted.load());
    CheckAllSlotsClosed(*state);
}

static void GameplayNotifications(ICvEngineUtility4& first,ICvEngineUtility4& second,
                                   ICvUserInterface2& uiFirst,ICvUserInterface2& uiSecond,
                                   const std::shared_ptr<HostState>& state){
    CHECK(!uiFirst.IsDontShowPopups() && !uiSecond.IsDontShowPopups());
    uiFirst.SetDontShowPopups(true);
    CHECK(uiSecond.IsDontShowPopups());
    uiSecond.SetDontShowPopups(false);
    CHECK(!uiFirst.IsDontShowPopups() && !uiSecond.IsDontShowPopups());

    const auto teamA=static_cast<TeamTypes>(3);
    const auto teamB=static_cast<TeamTypes>(9);
    const auto technology=static_cast<TechTypes>(42);
    PlotFixture plot(7,11,static_cast<FeatureTypes>(3));
    first.GameplayMetTeam(teamA,teamB);
    second.GameplayWarStateChanged(teamA,teamB,true);
    first.GameplayWarStateChanged(teamB,teamA,false);
    second.GameplayTechAcquired(teamA,technology);
    first.GameplayYieldMightHaveChanged(&plot);
    second.GameplayFeatureChanged(&plot,static_cast<FeatureTypes>(17));
    first.GameplayFeatureChanged(&plot,NO_FEATURE); // Removing a feature is valid too.
    CHECK(plot.featureReads==0 && plot.destroyCalls==0); // Use the supplied value and borrow the adapter.
    CHECK(uiFirst.isDirty(PlotData_DIRTY_BIT));
    uiFirst.PublishEndTurnDirty();

    char ownedTag[]="new-game-player-start";
    uiSecond.PublishPlayerTurnStatus(CvDLLInterfaceIFaceBase::TURN_START,static_cast<PlayerTypes>(5),ownedTag);
    std::memset(ownedTag,'x',sizeof(ownedTag)-1);
    ownedTag[sizeof(ownedTag)-1]='\0';
    uiFirst.PublishActivePlayerTurnStart();
    uiSecond.PublishPlayerTurnStatus(CvDLLInterfaceIFaceBase::TURN_STEP,static_cast<PlayerTypes>(6),nullptr);
    uiSecond.PublishActivePlayerTurnEnd();
    uiFirst.PublishPlayerTurnStatus(CvDLLInterfaceIFaceBase::TURN_END,static_cast<PlayerTypes>(5),"settled");

    const std::vector<std::string> expected={
        "player-slot-open:5",
        "player-slot-close:5",
        "player-slot-open:"+std::to_string(MAX_PLAYERS-1),
        "host-globals-started",
        "ui-dont-show-popups:1",
        "ui-dont-show-popups:0",
        "gameplay-met-team:3:9",
        "gameplay-war-state:3:9:1",
        "gameplay-war-state:9:3:0",
        "gameplay-tech-acquired:3:42",
        "gameplay-plot-yield:7:11",
        "gameplay-plot-feature:7:11:17",
        "gameplay-plot-feature:7:11:-1",
        "ui-end-turn-dirty",
        "ui-player-turn-status:0:5:new-game-player-start",
        "ui-active-player-turn-start",
        "ui-player-turn-status:2:6:",
        "ui-active-player-turn-end",
        "ui-player-turn-status:1:5:settled"
    };
    CHECK(state->Events()==expected);

    const auto beforeInvalid=state->Events();
    RejectInvalid([&]{first.GameplayMetTeam(static_cast<TeamTypes>(-1),teamB);});
    RejectInvalid([&]{second.GameplayWarStateChanged(teamA,static_cast<TeamTypes>(MAX_TEAMS),true);});
    RejectInvalid([&]{first.GameplayTechAcquired(static_cast<TeamTypes>(-1),technology);});
    RejectInvalid([&]{second.GameplayTechAcquired(teamA,static_cast<TechTypes>(-1));});
    RejectInvalid([&]{first.GameplayYieldMightHaveChanged(nullptr);});
    RejectInvalid([&]{second.GameplayFeatureChanged(nullptr,static_cast<FeatureTypes>(1));});
    RejectInvalid([&]{first.GameplayFeatureChanged(&plot,static_cast<FeatureTypes>(-2));});
    RejectInvalid([&]{uiFirst.PublishPlayerTurnStatus(CvDLLInterfaceIFaceBase::TURN_START,
        static_cast<PlayerTypes>(MAX_PLAYERS),"invalid-player");});
    RejectInvalid([&]{uiSecond.PublishPlayerTurnStatus(static_cast<CvDLLInterfaceIFaceBase::TURN_STATUS_TYPE>(-1),
        static_cast<PlayerTypes>(5),"invalid-status");});
    RejectInvalid([&]{uiFirst.PublishPlayerTurnStatus(static_cast<CvDLLInterfaceIFaceBase::TURN_STATUS_TYPE>(3),
        static_cast<PlayerTypes>(5),"invalid-status");});
    CHECK(state->Events()==beforeInvalid);
}

static void HeadlessSelection(ICvUserInterface2& first,ICvUserInterface2& second){
    CHECK(first.GetHeadSelectedUnit()==nullptr);
    CHECK(first.getSelectionPlot()==nullptr);
    CHECK(first.GetLengthSelectionList()==0);
    CHECK(second.GetHeadSelectedUnit()==nullptr);
    CHECK(second.getSelectionPlot()==nullptr);
    CHECK(second.GetLengthSelectionList()==0);
    const auto normalPlayer=static_cast<PlayerTypes>(5);
    CHECK(!first.IsUnitSelected(normalPlayer,0));
    CHECK(!second.IsUnitSelected(normalPlayer,17));
    // NO_PLAYER is a supported SDK sentinel; the query must remain a safe
    // negative result while this host's selection list is empty.
    CHECK(!first.IsUnitSelected(NO_PLAYER,0));
    CHECK(!second.IsUnitSelected(normalPlayer,-1));
}

static void UnitDimFlagValidation(ICvEngineUtility4& engine,const std::shared_ptr<HostState>& state){
    const auto before=state->Events();
    RejectInvalid([&]{engine.GameplayUnitShouldDimFlag(nullptr,true);});
    RejectInvalid([&]{engine.GameplayUnitFortify(nullptr,true);});
    CHECK(state->Events()==before);
}

static void UnavailablePlatform(ICvEngineUtility4& first,ICvEngineUtility4& second,
                                const std::shared_ptr<HostState>& state){
    CHECK(!EngineServices::PlatformStatisticsAvailable());
    CHECK(GetModuleHandleW(L"steam_api.dll")==nullptr && GetModuleHandleW(L"steam_api64.dll")==nullptr);
    const auto stat=ESTEAMSTAT_TILESDISCOVERED;
    const auto achievement=ACHIEVEMENT_1000TILES;
    const auto before=state->Events();
    int32 stored=12345;
    CHECK(!first.GetSteamStat(stat,&stored) && stored==12345);
    CHECK(!second.GetSteamStat(stat,nullptr));
    CHECK(!first.SetSteamStat(stat,1000));
    CHECK(!second.IncrementSteamStat(stat));
    CHECK(!first.IncrementSteamStatAndUnlock(stat,1000,achievement));
    first.UnlockAchievement(achievement);
    CHECK(!second.IsAchievementUnlocked(achievement));
    CHECK(!second.GetSteamStat(stat,&stored) && stored==12345);
    const auto after=state->Events();
    CHECK(after.size()==before.size()+8);
    CHECK(std::equal(before.begin(),before.end(),after.begin()));
    CHECK(after[before.size()+4]=="platform-stat-unavailable:increment-unlock:"+
        std::to_string(static_cast<int>(stat))+":1000:"+std::to_string(static_cast<int>(achievement)));
    CHECK(after[before.size()+5]=="platform-achievement-unavailable:unlock:"+std::to_string(static_cast<int>(achievement)));
    CHECK(GetModuleHandleW(L"steam_api.dll")==nullptr && GetModuleHandleW(L"steam_api64.dll")==nullptr);
}

static void NetworkIdentities(EngineServices& engine,const std::shared_ptr<HostState>& state){
    bool rejected=false;
    try{engine.getAssignedNetworkID(0);}catch(const std::logic_error&){rejected=true;}
    CHECK(rejected);
    state->gameLock.Enter();
    rejected=false;
    try{engine.getAssignedNetworkID(0);}catch(const std::logic_error&){rejected=true;}
    CHECK(rejected);
    state->assignedNetworkIds.fill(-1);state->networkAssignmentsReady=true;
    for(int id=0;id<MAX_PLAYERS;++id)CHECK(engine.getAssignedNetworkID(id)==-1);
    RejectInvalid([&]{engine.getAssignedNetworkID(-1);});
    RejectInvalid([&]{engine.getAssignedNetworkID(MAX_PLAYERS);});
    bool wrongThreadRejected=false;
    std::thread other([&]{try{engine.getAssignedNetworkID(0);}catch(const std::logic_error&){wrongThreadRejected=true;}});
    other.join();CHECK(wrongThreadRejected);
    state->gameLock.Leave();
}

static void GlobalsRestart(EngineServices& engine,ICvEngineUtility4& adapter,UserInterface& ui,
                           ICvUserInterface2& uiAdapter,const std::shared_ptr<HostState>& state){
    const auto player=static_cast<PlayerTypes>(12);
    adapter.openSlot(player);
    uiAdapter.SetDontShowPopups(true);
    uiAdapter.setDirty(static_cast<InterfaceDirtyBits>(7),true);
    uiAdapter.setCycleSelectionCounter(11);
    engine.SetDone(true);
    CHECK(SlotIsOpen(*state,player));
    CHECK(uiAdapter.isDirty(static_cast<InterfaceDirtyBits>(7)) && uiAdapter.getCycleSelectionCounter()==11);

    engine.UninitGlobals();
    CHECK(!state->globalsStarted.load());
    engine.InitGlobals();
    CHECK(state->globalsStarted.load());
    CHECK(!ui.IsDontShowPopups() && !uiAdapter.IsDontShowPopups());
    CheckAllSlotsClosed(*state);
    CHECK(!ui.isDirty(static_cast<InterfaceDirtyBits>(7)) && ui.getCycleSelectionCounter()==0);
    CHECK(!engine.GetDone());
    CHECK(!state->networkAssignmentsReady);
    const auto events=state->Events();
    CHECK(events.size()>=2 && events[events.size()-2]=="host-globals-stopped" && events.back()=="host-globals-started");
}

int main(){
    try{
        auto state=std::make_shared<HostState>("C:\\new-game-services\\");
        EngineServices engine(state);UserInterface ui(state);
        ZeroSisHostBinding::Owned<ICvEngineUtility4> engineFirst(
            static_cast<ICvEngineUtility4*>(engine.QueryInterface(guidICvEngineUtility4)));
        ZeroSisHostBinding::Owned<ICvEngineUtility4> engineSecond(
            static_cast<ICvEngineUtility4*>(engine.QueryInterface(guidICvEngineUtility4)));
        ZeroSisHostBinding::Owned<ICvUserInterface2> uiFirst(
            static_cast<ICvUserInterface2*>(ui.QueryInterface(guidICvUserInterface2)));
        ZeroSisHostBinding::Owned<ICvUserInterface2> uiSecond(
            static_cast<ICvUserInterface2*>(ui.QueryInterface(guidICvUserInterface2)));
        CHECK(engineFirst && engineSecond && uiFirst && uiSecond);

        ui.setDirty(static_cast<InterfaceDirtyBits>(2),true);
        ui.setCycleSelectionCounter(4);
        SlotStateAndValidation(engine,*engineFirst,*engineSecond,state);
        CHECK(!ui.isDirty(static_cast<InterfaceDirtyBits>(2)) && ui.getCycleSelectionCounter()==0);
        GameplayNotifications(*engineFirst,*engineSecond,*uiFirst,*uiSecond,state);
        UnavailablePlatform(*engineFirst,*engineSecond,state);
        HeadlessSelection(*uiFirst,*uiSecond);
        UnitDimFlagValidation(*engineFirst,state);
        NetworkIdentities(engine,state);
        GlobalsRestart(engine,*engineSecond,ui,*uiFirst,state);
        HeadlessSelection(*uiSecond,*uiFirst);

        engine.UninitGlobals();
        CHECK(!state->globalsStarted.load() && !engine.HasGameCoreLock() && !engine.IsGameCoreExecuting());
        engineFirst.reset();engineSecond.reset();uiFirst.reset();uiSecond.reset();
        CHECK(state->engineAdapters==1 && state->userAdapters==1);
        std::printf("HOST_NEW_GAME_SERVICES_PASS checks=%u GAMECORE_LOADED=false\n",checks);
        return 0;
    }catch(const std::exception& error){
        std::fprintf(stderr,"UNEXPECTED: %s\n",error.what());return 1;
    }
}
