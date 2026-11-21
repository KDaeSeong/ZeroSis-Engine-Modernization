// Actual HostServices selection-camera boundary with instrumented SDK adapters.
// This component does not load GameCore, execute original Lua or display a window.
#include "HostServices.h"
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <thread>
using namespace ZeroSisHost;
namespace {
unsigned checks=0;
void Check(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
template<class E,class F>void Reject(F f,const char* message){bool caught=false;try{f();}catch(const E&){caught=true;}Check(caught,message);}
struct Counts {
    int plots=0,units=0,cities=0,createdPlots=0,createdUnits=0,createdCities=0,plotReads=0,positionReads=0;
    int unitIndex=11,cityIndex=22;
    bool throwPosition=false,nullUnitPlot=false,nullCityPlot=false,delayedDeath=false;
};
class PlotMock final:public ICvPlot1 {
public:
    explicit PlotMock(Counts& c,int index=123,int x=7,int y=9):c_(c),index_(index),x_(x),y_(y){++c_.createdPlots;}
    void SetPosition(int index,int x,int y){index_=index;x_=x;y_=y;}
    static void operator delete(void* p) noexcept{::operator delete(p);}
    void* DLLCALL QueryInterface(GUID) override{return nullptr;} void DLLCALL Destroy() override{++c_.plots;delete this;}
    TeamTypes DLLCALL GetTeam()const override{return static_cast<TeamTypes>(0);} FogOfWarModeTypes DLLCALL GetActiveFogOfWarMode()const override{return static_cast<FogOfWarModeTypes>(0);}
    void DLLCALL UpdateCenterUnit()override{} bool DLLCALL IsAdjacent(ICvPlot1*)const override{return false;} bool DLLCALL IsRiver()const override{return false;}
    ICvPlot1* DLLCALL GetNeighboringPlot(DirectionTypes)const override{return nullptr;} int DLLCALL GetBuildTime(BuildTypes,PlayerTypes)const override{return 0;}
    bool DLLCALL IsVisible(TeamTypes,bool)const override{return false;} bool DLLCALL IsCity()const override{return false;} bool DLLCALL IsEnemyCity(ICvUnit1*)const override{return false;}
    bool DLLCALL IsFighting()const override{return false;} bool DLLCALL IsTradeRoute(PlayerTypes)const override{return false;} bool DLLCALL IsImpassable()const override{return false;}
    void DLLCALL GetPosition(int& x,int& y)const override{++c_.positionReads;if(c_.throwPosition)throw std::runtime_error("injected position failure");x=x_;y=y_;} bool DLLCALL IsNEOfRiver()const override{return false;} bool DLLCALL IsWOfRiver()const override{return false;}
    bool DLLCALL IsNWOfRiver()const override{return false;} FlowDirectionTypes DLLCALL GetRiverEFlowDirection()const override{return static_cast<FlowDirectionTypes>(0);}
    FlowDirectionTypes DLLCALL GetRiverSEFlowDirection()const override{return static_cast<FlowDirectionTypes>(0);} FlowDirectionTypes DLLCALL GetRiverSWFlowDirection()const override{return static_cast<FlowDirectionTypes>(0);}
    PlayerTypes DLLCALL GetOwner()const override{return NO_PLAYER;} PlotTypes DLLCALL GetPlotType()const override{return static_cast<PlotTypes>(0);} bool DLLCALL IsWater()const override{return false;}
    bool DLLCALL IsHills()const override{return false;} bool DLLCALL IsOpenGround()const override{return true;} bool DLLCALL IsMountain()const override{return false;}
    TerrainTypes DLLCALL GetTerrainType()const override{return static_cast<TerrainTypes>(0);} FeatureTypes DLLCALL GetFeatureType()const override{return NO_FEATURE;}
    ResourceTypes DLLCALL GetResourceType(TeamTypes)const override{return static_cast<ResourceTypes>(0);} int DLLCALL GetNumResource()const override{return 0;}
    ImprovementTypes DLLCALL GetImprovementType()const override{return static_cast<ImprovementTypes>(0);} bool DLLCALL IsImprovementPillaged()const override{return false;}
    GenericWorldAnchorTypes DLLCALL GetWorldAnchor()const override{return static_cast<GenericWorldAnchorTypes>(0);} int DLLCALL GetWorldAnchorData()const override{return 0;}
    RouteTypes DLLCALL GetRouteType()const override{return static_cast<RouteTypes>(0);} bool DLLCALL IsRoutePillaged()const override{return false;}
    ICvCity1* DLLCALL GetPlotCity()const override{return nullptr;} ICvCity1* DLLCALL GetWorkingCity()const override{return nullptr;}
    bool DLLCALL IsRevealed(TeamTypes,bool)const override{return false;} ImprovementTypes DLLCALL GetRevealedImprovementType(TeamTypes,bool)const override{return static_cast<ImprovementTypes>(0);}
    int DLLCALL GetBuildProgress(BuildTypes)const override{return 0;} bool DLLCALL GetAnyBuildProgress()const override{return false;} void DLLCALL UpdateLayout(bool)override{}
    ICvUnit1* DLLCALL GetCenterUnit()override{return nullptr;} int DLLCALL GetNumUnits()const override{return 0;} ICvUnit1* DLLCALL GetUnitByIndex(int)const override{return nullptr;}
    void DLLCALL AddUnit(ICvUnit1*,bool)override{} void DLLCALL RemoveUnit(ICvUnit1*,bool)override{} const IDInfo* DLLCALL NextUnitNode(const IDInfo*)const override{return nullptr;}
    IDInfo* DLLCALL NextUnitNode(IDInfo*)override{return nullptr;} IDInfo* DLLCALL HeadUnitNode()override{return nullptr;} int DLLCALL GetPlotIndex()const override{++c_.plotReads;return index_;}
    char DLLCALL GetContinentType()const override{return 0;} FAutoArchive& DLLCALL GetSyncArchive()override{throw std::logic_error("unexpected archive access");}
private: Counts& c_;int index_,x_,y_;
};

class UnitMock final:public ICvUnit1 {
public:
    UnitMock(Counts& c,int owner,int id):c_(c),owner_(owner),id_(id){++c_.createdUnits;}
    static void operator delete(void* p) noexcept{::operator delete(p);}
    void* DLLCALL QueryInterface(GUID)override{return nullptr;} void DLLCALL Destroy()override{++c_.units;delete this;}
    int DLLCALL GetID()const override{return id_;} PlayerTypes DLLCALL GetOwner()const override{return static_cast<PlayerTypes>(owner_);}
    int DLLCALL GetDamage()const override{return 0;} int DLLCALL GetMoves()const override{return 0;} bool DLLCALL IsSelected()const override{return false;} int DLLCALL GetMaxHitPoints()const override{return 100;}
    CivilizationTypes DLLCALL GetCivilizationType()const override{return static_cast<CivilizationTypes>(0);} TeamTypes DLLCALL GetTeam()const override{return static_cast<TeamTypes>(0);} DomainTypes DLLCALL GetDomainType()const override{return static_cast<DomainTypes>(0);}
    bool DLLCALL IsCombatUnit()const override{return true;} bool DLLCALL IsBarbarian()const override{return false;} bool DLLCALL IsHoveringUnit()const override{return false;} bool DLLCALL IsInvisible(TeamTypes,bool)const override{return false;}
    bool DLLCALL CanMoveImpassable()const override{return false;} DirectionTypes DLLCALL GetFacingDirection(bool)const override{return static_cast<DirectionTypes>(0);} ICvPlot1* DLLCALL GetPlot()const override{return c_.nullUnitPlot?nullptr:new PlotMock(c_,c_.unitIndex,3,4);}
    ICvUnitInfo1* DLLCALL GetUnitInfo()const override{return nullptr;} bool DLLCALL IsEmbarked()const override{return false;} bool DLLCALL IsGarrisoned()const override{return false;}
    ICvMissionData1* DLLCALL GetHeadMissionData()const override{return nullptr;} UnitCombatTypes DLLCALL GetUnitCombatType()override{return static_cast<UnitCombatTypes>(0);}
    int DLLCALL GetX()const override{return 7;} int DLLCALL GetY()const override{return 9;} void DLLCALL GetPosition(int& x,int& y)const override{x=7;y=9;}
    bool DLLCALL CanSwapWithUnitHere(ICvPlot1*)const override{return false;} bool DLLCALL CanEmbarkOnto(ICvPlot1*,ICvPlot1*,bool)const override{return false;}
    bool DLLCALL CanDisembarkOnto(ICvPlot1*,ICvPlot1*,bool)const override{return false;} bool DLLCALL IsFirstTimeSelected()const override{return false;}
    UnitTypes DLLCALL GetUnitType()const override{return static_cast<UnitTypes>(0);} bool DLLCALL IsDelayedDeathExported()const override{return c_.delayedDeath;} bool DLLCALL IsBusy()const override{return false;}
    void DLLCALL SetupGraphical()override{} CvString DLLCALL GetName()const override{return CvString();} void DLLCALL DoCommand(CommandTypes,int,int)override{}
    bool DLLCALL CanDoInterfaceMode(InterfaceModeTypes,bool)override{return false;} IDInfo DLLCALL GetIDInfo()const override{return IDInfo();} int DLLCALL MovesLeft()const override{return 0;}
    bool DLLCALL CanMoveInto(ICvPlot1*,byte)const override{return false;} TeamTypes DLLCALL GetDeclareWarMove(ICvPlot1*)const override{return static_cast<TeamTypes>(0);} bool DLLCALL ReadyToSelect()const override{return false;}
    bool DLLCALL CanWork()const override{return false;} bool DLLCALL CanFound()const override{return false;} FAutoArchive& DLLCALL GetSyncArchive()override{throw std::logic_error("unexpected archive access");}
private: Counts& c_;int owner_,id_;
};

class CityMock final:public ICvCity1 {
public:
    CityMock(Counts& c,int owner,int id):c_(c),owner_(owner),id_(id){++c_.createdCities;}
    static void operator delete(void* p) noexcept{::operator delete(p);}
    void* DLLCALL QueryInterface(GUID)override{return nullptr;} void DLLCALL Destroy()override{++c_.cities;delete this;}
    int DLLCALL GetID()const override{return id_;} PlayerTypes DLLCALL GetOwner()const override{return static_cast<PlayerTypes>(owner_);} int DLLCALL GetMaxHitPoints()const override{return 200;}
    void DLLCALL GetPosition(int& x,int& y)const override{x=7;y=9;} ICvPlot1* DLLCALL Plot()const override{return c_.nullCityPlot?nullptr:new PlotMock(c_,c_.cityIndex,13,14);} int DLLCALL GetPopulation()const override{return 1;}
    const char* DLLCALL GetName()const override{return "mock";} bool DLLCALL CanBuyPlot(int,int,bool)override{return false;} CitySizeTypes DLLCALL GetCitySizeType()const override{return static_cast<CitySizeTypes>(0);}
    const char* DLLCALL GetCityBombardEffectTag()const override{return "";} TeamTypes DLLCALL GetTeam()const override{return static_cast<TeamTypes>(0);} bool DLLCALL IsPuppet()const override{return false;}
    int DLLCALL GetX()const override{return 7;} int DLLCALL GetY()const override{return 9;} int DLLCALL GetStrengthValue(bool)const override{return 0;} int DLLCALL FoodDifference(bool)const override{return 0;}
    int DLLCALL GetFoodTurnsLeft()const override{return 0;} int DLLCALL GetYieldRate(int)const override{return 0;} int DLLCALL GetJONSCulturePerTurn()const override{return 0;} IDInfo DLLCALL GetIDInfo()const override{return IDInfo();}
    bool DLLCALL IsWorkingPlot(ICvPlot1*)const override{return false;} bool DLLCALL CanWork(ICvPlot1*)const override{return false;} ICvPlot1* DLLCALL GetCityPlotFromIndex(int)const override{return nullptr;}
    FAutoArchive& DLLCALL GetSyncArchive()override{throw std::logic_error("unexpected archive access");}
private: Counts& c_;int owner_,id_;
};

void Run(){
    Counts counts;int unitResolves=0,cityResolves=0;
    bool unitExists=true,cityExists=true,wrongCityIdentity=false;
    auto state=std::make_shared<HostState>("selection-camera-component/",nullptr,nullptr,nullptr);
    UserInterface ui(state);
    ICvUserInterface2& abi=ui;
    Reject<std::logic_error>([&]{abi.lookAtSelectionPlot();},"Unlocked camera query was accepted");
    Check(state->cameraPresentations.empty() && state->Events().empty(),"Unlocked query emitted a camera event");
    {
        GameCall locked(*state);
        state->localSelection.Bind([](PlayerTypes owner){return owner==static_cast<PlayerTypes>(0);},
            [&](PlayerTypes owner,int id)->ICvUnit1*{
                ++unitResolves;
                return unitExists?new UnitMock(counts,static_cast<int>(owner),id):nullptr;
            });
        state->resolveCity=[&](PlayerTypes owner,int id)->ICvCity1*{
            ++cityResolves;
            return cityExists?new CityMock(counts,static_cast<int>(owner),wrongCityIdentity?id+1:id):nullptr;
        };
        const auto selectUnit=[&](int id){
            std::unique_ptr<ICvUnit1> unit(new UnitMock(counts,0,id));
            ui.InsertIntoSelectionList(unit.get(),true,false,false,false,false);
        };
        const auto selectCity=[&](){
            std::unique_ptr<ICvCity1> city(new CityMock(counts,0,42));ui.selectCity(city.get());
        };
        const auto expectFocus=[&](int index,int x,int y){
            Check(!state->cameraPresentations.empty(),"No owned camera presentation was queued");
            const auto& focus=state->cameraPresentations.back();
            Check(focus.plotIndex==index && focus.x==x && focus.y==y && focus.type==CAMERALOOKAT_NORMAL,
                  "Camera presentation does not identify the actual selected plot");
        };
        abi.lookAtSelectionPlot();
        Check(state->cameraPresentations.empty() && state->Events().empty(),"Empty selection moved the camera");
        Check(unitResolves==0 && cityResolves==0,"Empty selection resolved a fabricated entity");

        selectUnit(7);
        const auto selected=state->localSelection.Snapshot();
        const auto firstSize=state->cameraPresentations.size();
        abi.lookAtSelectionPlot();expectFocus(11,3,4);
        Check(state->cameraPresentations.size()==firstSize+1,"Unit focus was duplicated");
        Check(state->localSelection.Snapshot()==selected,"Camera focus changed the selected unit");
        Check(state->Events().back()=="ui-camera:11:0","Camera focus skipped the ordinary presentation event");
        Check(counts.createdPlots==counts.plots && counts.createdUnits==counts.units,"Unit focus retained SDK adapters");

        selectCity();const int unitBeforeCity=unitResolves;
        const auto both=state->localSelection.Snapshot();const int afterSnapshot=unitResolves;
        abi.lookAtSelectionPlot();expectFocus(22,13,14);
        Check(unitResolves==afterSnapshot && afterSnapshot>unitBeforeCity,"Selected city did not take precedence over retained unit");
        Check(state->selectedCityOwner==static_cast<PlayerTypes>(0) && state->selectedCityId==42,
              "Camera focus changed the selected city");
        Check(state->localSelection.Snapshot()==both,"City focus removed the retained unit selection");
        Check(counts.createdCities==counts.cities && counts.createdPlots==counts.plots,"City focus retained SDK adapters");
        ui.clearSelectedCities();abi.lookAtSelectionPlot();expectFocus(11,3,4);

        const int beforeReleaseUnit=unitResolves,beforeReleaseCity=cityResolves;
        const auto beforeReleaseCamera=state->cameraPresentations.size();const auto beforeReleaseEvents=state->Events();
        Reject<UnsupportedService>([&]{abi.lookAtSelectionPlot(true);},"Unimplemented camera release was silently accepted");
        Check(unitResolves==beforeReleaseUnit && cityResolves==beforeReleaseCity,"Unsupported release accessed a selection");
        Check(state->cameraPresentations.size()==beforeReleaseCamera && state->Events()==beforeReleaseEvents,
              "Unsupported release changed camera state");

        bool wrongThreadRejected=false;
        std::thread other([&]{try{abi.lookAtSelectionPlot();}catch(const std::logic_error&){wrongThreadRejected=true;}});
        other.join();
        Check(wrongThreadRejected,"Wrong-thread camera query was accepted");
        Check(unitResolves==beforeReleaseUnit && cityResolves==beforeReleaseCity,"Wrong-thread query reached SDK resolvers");

        counts.nullUnitPlot=true;const auto beforeBad=state->cameraPresentations.size();
        Reject<std::logic_error>([&]{abi.lookAtSelectionPlot();},"Live unit without a plot was accepted");
        counts.nullUnitPlot=false;
        Check(state->cameraPresentations.size()==beforeBad,"Missing unit plot emitted a camera request");
        Check(state->localSelection.Snapshot()==selected,"Missing plot changed the selected identity");
        Check(counts.createdUnits==counts.units,"Missing unit plot leaked its adapter");

        counts.unitIndex=-1;
        Reject<std::invalid_argument>([&]{abi.lookAtSelectionPlot();},"Invalid plot index bypassed the existing camera guard");
        counts.unitIndex=11;
        counts.throwPosition=true;
        Reject<std::runtime_error>([&]{abi.lookAtSelectionPlot();},"Injected plot read failure was swallowed");
        counts.throwPosition=false;
        Check(state->cameraPresentations.size()==beforeBad,"Invalid plot emitted a camera request");
        Check(counts.createdUnits==counts.units && counts.createdPlots==counts.plots,"Failed plot read leaked SDK adapters");

        selectCity();counts.nullCityPlot=true;
        Reject<std::logic_error>([&]{abi.lookAtSelectionPlot();},"Selected city without a plot fell back to an unrelated unit");
        counts.nullCityPlot=false;
        Check(state->cameraPresentations.size()==beforeBad,"Missing city plot moved the camera");
        Check(counts.createdCities==counts.cities,"Missing city plot leaked its adapter");
        wrongCityIdentity=true;abi.lookAtSelectionPlot();wrongCityIdentity=false;expectFocus(11,3,4);
        Check(state->selectedCityOwner==NO_PLAYER && state->selectedCityId==-1,"Stale city identity was not invalidated");

        const auto beforeDeferred=state->cameraPresentations.size();const auto eventsBeforeDeferred=state->Events();
        state->actionInfoActivationInProgress=true;state->actionInfoOwner=static_cast<PlayerTypes>(0);state->actionInfoTurn=5;
        abi.lookAtSelectionPlot();
        Check(state->cameraPresentations.size()==beforeDeferred && state->Events()==eventsBeforeDeferred,
              "Notification callback bypassed the deferred camera boundary");
        Check(state->actionInfoAdapterRequests.size()==1,"Deferred camera request missing or duplicated");
        const auto& deferred=state->actionInfoAdapterRequests.back();
        Check(deferred.kind==ActionInfoRequest::Kind::LookAt && deferred.owner==static_cast<PlayerTypes>(0) &&
              deferred.turn==5 && deferred.x==3 && deferred.y==4,"Deferred camera request lost selection or owner/turn");
        state->actionInfoActivationInProgress=false;state->actionInfoAdapterRequests.clear();
        state->actionInfoOwner=NO_PLAYER;state->actionInfoTurn=-1;

        unitExists=false;abi.lookAtSelectionPlot();
        Check(state->cameraPresentations.size()==beforeDeferred && state->localSelection.Length()==0,
              "Missing unit was focused or left selected");
        unitExists=true;selectUnit(8);counts.delayedDeath=true;abi.lookAtSelectionPlot();counts.delayedDeath=false;
        Check(state->cameraPresentations.size()==beforeDeferred && state->localSelection.Length()==0,
              "Delayed-death unit was focused or left selected");
        state->localSelection.Unbind();abi.lookAtSelectionPlot();
        Check(state->cameraPresentations.size()==beforeDeferred,"Unbound empty selection created a camera request");
        Check(counts.createdPlots==counts.plots && counts.createdUnits==counts.units && counts.createdCities==counts.cities,
              "Owned SDK wrappers outlived the camera calls");
    }
    Reject<std::logic_error>([&]{abi.lookAtSelectionPlot();},"Unlocked query after teardown was accepted");
}
}
int main(){
    try{Run();std::printf("SELECTION_CAMERA_COMPONENT_PASS checks=%u SDK_ADAPTERS_MOCKED=true GAMECORE_LOADED=false\n",checks);return 0;}
    catch(const std::exception& error){std::fprintf(stderr,"SELECTION_CAMERA_COMPONENT_FAIL checks=%u reason=%s\n",checks,error.what());return 1;}
}
