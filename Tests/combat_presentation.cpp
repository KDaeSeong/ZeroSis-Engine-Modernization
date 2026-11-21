// Isolated combat-presentation capture regression. This is a mock boundary
// test; it does not load GameCore or claim retail-runtime equivalence.
#include "HostServices.h"
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool v,const char* e,int line){++checks;if(!v){std::fprintf(stderr,"FAILED line=%d %s\n",line,e);std::exit(1);}}
#define CHECK(v) Check((v),#v,__LINE__)

struct Counts { int plots=0,units=0,cities=0,infoDestroy=0,plotReads=0,positionReads=0; };

class PlotMock final:public ICvPlot1 {
public:
    explicit PlotMock(Counts& c,int index=123,int x=7,int y=9):c_(c),index_(index),x_(x),y_(y){}
    void SetPosition(int index,int x,int y){index_=index;x_=x;y_=y;}
    static void operator delete(void* p) noexcept{::operator delete(p);}
    void* DLLCALL QueryInterface(GUID) override{return nullptr;} void DLLCALL Destroy() override{++c_.plots;delete this;}
    TeamTypes DLLCALL GetTeam()const override{return static_cast<TeamTypes>(0);} FogOfWarModeTypes DLLCALL GetActiveFogOfWarMode()const override{return static_cast<FogOfWarModeTypes>(0);}
    void DLLCALL UpdateCenterUnit()override{} bool DLLCALL IsAdjacent(ICvPlot1*)const override{return false;} bool DLLCALL IsRiver()const override{return false;}
    ICvPlot1* DLLCALL GetNeighboringPlot(DirectionTypes)const override{return nullptr;} int DLLCALL GetBuildTime(BuildTypes,PlayerTypes)const override{return 0;}
    bool DLLCALL IsVisible(TeamTypes,bool)const override{return false;} bool DLLCALL IsCity()const override{return false;} bool DLLCALL IsEnemyCity(ICvUnit1*)const override{return false;}
    bool DLLCALL IsFighting()const override{return false;} bool DLLCALL IsTradeRoute(PlayerTypes)const override{return false;} bool DLLCALL IsImpassable()const override{return false;}
    void DLLCALL GetPosition(int& x,int& y)const override{++c_.positionReads;x=x_;y=y_;} bool DLLCALL IsNEOfRiver()const override{return false;} bool DLLCALL IsWOfRiver()const override{return false;}
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
    UnitMock(Counts& c,int owner,int id):c_(c),owner_(owner),id_(id){}
    static void operator delete(void* p) noexcept{::operator delete(p);}
    void* DLLCALL QueryInterface(GUID)override{return nullptr;} void DLLCALL Destroy()override{++c_.units;delete this;}
    int DLLCALL GetID()const override{return id_;} PlayerTypes DLLCALL GetOwner()const override{return static_cast<PlayerTypes>(owner_);}
    int DLLCALL GetDamage()const override{return 0;} int DLLCALL GetMoves()const override{return 0;} bool DLLCALL IsSelected()const override{return false;} int DLLCALL GetMaxHitPoints()const override{return 100;}
    CivilizationTypes DLLCALL GetCivilizationType()const override{return static_cast<CivilizationTypes>(0);} TeamTypes DLLCALL GetTeam()const override{return static_cast<TeamTypes>(0);} DomainTypes DLLCALL GetDomainType()const override{return static_cast<DomainTypes>(0);}
    bool DLLCALL IsCombatUnit()const override{return true;} bool DLLCALL IsBarbarian()const override{return false;} bool DLLCALL IsHoveringUnit()const override{return false;} bool DLLCALL IsInvisible(TeamTypes,bool)const override{return false;}
    bool DLLCALL CanMoveImpassable()const override{return false;} DirectionTypes DLLCALL GetFacingDirection(bool)const override{return static_cast<DirectionTypes>(0);} ICvPlot1* DLLCALL GetPlot()const override{return nullptr;}
    ICvUnitInfo1* DLLCALL GetUnitInfo()const override{return nullptr;} bool DLLCALL IsEmbarked()const override{return false;} bool DLLCALL IsGarrisoned()const override{return false;}
    ICvMissionData1* DLLCALL GetHeadMissionData()const override{return nullptr;} UnitCombatTypes DLLCALL GetUnitCombatType()override{return static_cast<UnitCombatTypes>(0);}
    int DLLCALL GetX()const override{return 7;} int DLLCALL GetY()const override{return 9;} void DLLCALL GetPosition(int& x,int& y)const override{x=7;y=9;}
    bool DLLCALL CanSwapWithUnitHere(ICvPlot1*)const override{return false;} bool DLLCALL CanEmbarkOnto(ICvPlot1*,ICvPlot1*,bool)const override{return false;}
    bool DLLCALL CanDisembarkOnto(ICvPlot1*,ICvPlot1*,bool)const override{return false;} bool DLLCALL IsFirstTimeSelected()const override{return false;}
    UnitTypes DLLCALL GetUnitType()const override{return static_cast<UnitTypes>(0);} bool DLLCALL IsDelayedDeathExported()const override{return false;} bool DLLCALL IsBusy()const override{return false;}
    void DLLCALL SetupGraphical()override{} CvString DLLCALL GetName()const override{return CvString();} void DLLCALL DoCommand(CommandTypes,int,int)override{}
    bool DLLCALL CanDoInterfaceMode(InterfaceModeTypes,bool)override{return false;} IDInfo DLLCALL GetIDInfo()const override{return IDInfo();} int DLLCALL MovesLeft()const override{return 0;}
    bool DLLCALL CanMoveInto(ICvPlot1*,byte)const override{return false;} TeamTypes DLLCALL GetDeclareWarMove(ICvPlot1*)const override{return static_cast<TeamTypes>(0);} bool DLLCALL ReadyToSelect()const override{return false;}
    bool DLLCALL CanWork()const override{return false;} bool DLLCALL CanFound()const override{return false;} FAutoArchive& DLLCALL GetSyncArchive()override{throw std::logic_error("unexpected archive access");}
private: Counts& c_;int owner_,id_;
};

class CityMock final:public ICvCity1 {
public:
    CityMock(Counts& c,int owner,int id):c_(c),owner_(owner),id_(id){}
    static void operator delete(void* p) noexcept{::operator delete(p);}
    void* DLLCALL QueryInterface(GUID)override{return nullptr;} void DLLCALL Destroy()override{++c_.cities;delete this;}
    int DLLCALL GetID()const override{return id_;} PlayerTypes DLLCALL GetOwner()const override{return static_cast<PlayerTypes>(owner_);} int DLLCALL GetMaxHitPoints()const override{return 200;}
    void DLLCALL GetPosition(int& x,int& y)const override{x=7;y=9;} ICvPlot1* DLLCALL Plot()const override{return nullptr;} int DLLCALL GetPopulation()const override{return 1;}
    const char* DLLCALL GetName()const override{return "mock";} bool DLLCALL CanBuyPlot(int,int,bool)override{return false;} CitySizeTypes DLLCALL GetCitySizeType()const override{return static_cast<CitySizeTypes>(0);}
    const char* DLLCALL GetCityBombardEffectTag()const override{return "";} TeamTypes DLLCALL GetTeam()const override{return static_cast<TeamTypes>(0);} bool DLLCALL IsPuppet()const override{return false;}
    int DLLCALL GetX()const override{return 7;} int DLLCALL GetY()const override{return 9;} int DLLCALL GetStrengthValue(bool)const override{return 0;} int DLLCALL FoodDifference(bool)const override{return 0;}
    int DLLCALL GetFoodTurnsLeft()const override{return 0;} int DLLCALL GetYieldRate(int)const override{return 0;} int DLLCALL GetJONSCulturePerTurn()const override{return 0;} IDInfo DLLCALL GetIDInfo()const override{return IDInfo();}
    bool DLLCALL IsWorkingPlot(ICvPlot1*)const override{return false;} bool DLLCALL CanWork(ICvPlot1*)const override{return false;} ICvPlot1* DLLCALL GetCityPlotFromIndex(int)const override{return nullptr;}
    FAutoArchive& DLLCALL GetSyncArchive()override{throw std::logic_error("unexpected archive access");}
private: Counts& c_;int owner_,id_;
};

struct Info final:ICvCombatInfo1 {
    mutable Counts counts; mutable int reads=0; int count=0,maxCount=4; const CvCombatMemberEntry* member=nullptr; bool throwDamage=false; bool nullPlot=false; bool unit=true,city=true;
    int owner=2,unitId=44,cityOwner=2,cityId=55,plotIndex=123,nullMemberAt=-1; mutable int destructions=0;
    void* DLLCALL QueryInterface(GUID)override{return nullptr;} void DLLCALL Destroy()override{++destructions;}
    ICvUnit1* DLLCALL GetUnit(BattleUnitTypes t)const override{++reads;return unit&&t==static_cast<BattleUnitTypes>(0)?new UnitMock(counts,owner,unitId):nullptr;}
    ICvCity1* DLLCALL GetCity(BattleUnitTypes t)const override{++reads;return city&&t==static_cast<BattleUnitTypes>(0)?new CityMock(counts,cityOwner,cityId):nullptr;}
    ICvPlot1* DLLCALL GetPlot()const override{++reads;return nullPlot?nullptr:new PlotMock(counts,plotIndex);}
    bool DLLCALL GetAttackerAdvances()const override{return true;} bool DLLCALL GetVisualizeCombat()const override{return false;} bool DLLCALL GetDefenderRetaliates()const override{return true;}
    int DLLCALL GetNuclearDamageLevel()const override{return 3;} bool DLLCALL GetAttackIsRanged()const override{return true;} bool DLLCALL GetAttackIsBombingMission()const override{return false;}
    bool DLLCALL GetAttackIsAirSweep()const override{return true;} bool DLLCALL GetDefenderCaptured()const override{return false;}
    int DLLCALL GetDamageInflicted(BattleUnitTypes)const override{if(throwDamage)throw std::runtime_error("injected getter failure");return 17;}
    int DLLCALL GetFinalDamage(BattleUnitTypes)const override{return 29;} const CvCombatMemberEntry* DLLCALL GetDamageMember(int index)const override{return index==nullMemberAt?nullptr:member;}
    int DLLCALL GetDamageMemberCount()const override{return count;} int DLLCALL GetMaxDamageMemberCount()const override{return maxCount;} void* DLLCALL TEMPGetRawCombatInfo()const override{return nullptr;}
};

template<class F> static void Reject(F f){bool rejected=false;try{f();}catch(const std::invalid_argument&){rejected=true;}CHECK(rejected);}
template<class F> static void RejectException(F f){bool rejected=false;try{f();}catch(const std::exception&){rejected=true;}CHECK(rejected);}
int main(){
    auto state=std::make_shared<HostState>("combat-test/"); EngineServices engine(state);
    UserInterface ui(state);
    bool activationNoLock=false;
    try{engine.IsModActivated("01234567-89ab-cdef-0123-456789abcdef");}
    catch(const std::logic_error&){activationNoLock=true;}
    CHECK(activationNoLock&&state->Events().empty());
    {
        GameCall call(*state);
        RejectException([&]{engine.IsModActivated("01234567-89ab-cdef-0123-456789abcdef");});
        RejectException([&]{engine.IsModActivated("0123456789abcdef0123456789abcdef",1);});
    }

    auto emptyActivation=std::make_shared<const ActiveModCatalog>(std::vector<ActiveModCatalog::Entry>{});
    auto configuredState=std::make_shared<HostState>("combat-empty-activation/",nullptr,nullptr,nullptr,emptyActivation);
    EngineServices activationEngine(configuredState);
    {
        GameCall call(*configuredState);
        CHECK(!activationEngine.IsModActivated("01234567-89ab-CDEF-0123-456789abcdef"));
        CHECK(!activationEngine.IsModActivated("0123456789ABCDEF0123456789ABCDEF"));
        CHECK(!activationEngine.IsModActivated("01234567-89AB-CDEF-0123-456789ABCDEF",0));
        CHECK(!activationEngine.IsModActivated("0123456789abcdef0123456789abcdef",99));
        const auto events=configuredState->Events().size();
        Reject([&]{activationEngine.IsModActivated("not-a-guid");});
        Reject([&]{activationEngine.IsModActivated(nullptr,1);});
        CHECK(configuredState->Events().size()==events);
    }
    auto nonemptyActivation=std::make_shared<const ActiveModCatalog>(std::vector<ActiveModCatalog::Entry>{
        {"01234567-89ab-cdef-0123-456789abcdef",1}});
    CHECK(nonemptyActivation->Contains("01234567-89AB-CDEF-0123-456789ABCDEF"));
    CHECK(nonemptyActivation->Contains("0123456789ABCDEF0123456789ABCDEF"));
    std::shared_ptr<HostState> nonemptyState;
    RejectException([&]{nonemptyState=std::make_shared<HostState>("combat-nonempty-activation/",nullptr,nullptr,nullptr,nonemptyActivation);});
    CHECK(!nonemptyState);

    struct DeliveredCommand {int unit;CommandTypes command;int data1,data2;bool alt;};
    std::vector<DeliveredCommand> delivered;
    state->localCommands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;},
        [&](int unit,CommandTypes command,int data1,int data2,bool alt){delivered.push_back({unit,command,data1,data2,alt});});
    const auto eventsBeforeCommand=state->Events().size();
    bool commandNoLock=false;
    try{engine.sendDoCommand(71,COMMAND_PROMOTION,5,6,false);}catch(const std::logic_error&){commandNoLock=true;}
    CHECK(commandNoLock&&delivered.empty()&&state->Events().size()==eventsBeforeCommand);
    {GameCall call(*state);engine.sendDoCommand(71,COMMAND_PROMOTION,5,6,false);}
    CHECK(delivered.size()==1&&delivered[0].unit==71&&delivered[0].command==COMMAND_PROMOTION&&
          delivered[0].data1==5&&delivered[0].data2==6&&!delivered[0].alt);
    state->localCommands.Unbind();

    Counts uiCounts;
    PlotMock cameraPlot(uiCounts,123,7,9);
    const auto cameraEvents=state->Events().size();
    const auto cameraReads=uiCounts.plotReads+uiCounts.positionReads;
    bool cameraNoLock=false;try{ui.lookAt(&cameraPlot,CAMERALOOKAT_NORMAL);}catch(const std::logic_error&){cameraNoLock=true;}
    CHECK(cameraNoLock&&state->cameraPresentations.empty()&&state->Events().size()==cameraEvents);
    CHECK(uiCounts.plotReads+uiCounts.positionReads==cameraReads);
    const auto textNoLock=state->popupTexts.size();
    bool textNoLockRejected=false;try{ui.AddPopupText(7,9,"unlocked");}catch(const std::logic_error&){textNoLockRejected=true;}
    CHECK(textNoLockRejected&&state->popupTexts.size()==textNoLock);
    const auto focusEvents=state->Events().size();
    bool focusNoLock=false;try{ui.setCombatFocus(true);}catch(const std::logic_error&){focusNoLock=true;}
    CHECK(focusNoLock&&!state->combatFocus&&state->Events().size()==focusEvents);

    Info info;
    const int untouched=info.reads;
    bool noLock=false;try{engine.GameplayUnitCombat(&info);}catch(const std::logic_error&){noLock=true;}CHECK(noLock&&info.reads==untouched);
    bool wrongThread=false;{std::thread t([&]{try{engine.GameplayCityCombat(&info);}catch(const std::logic_error&){wrongThread=true;}});t.join();}
    CHECK(wrongThread&&info.reads==untouched&&state->combatPresentations.empty());
    {GameCall call(*state);
        CHECK(engine.GameplayUnitCombat(&info)==0);CHECK(state->combatPresentations.size()==1);
        const auto& got=state->combatPresentations.back();CHECK(!got.cityEvent&&got.plotIndex==123&&got.plotX==7&&got.plotY==9);
        CHECK(got.attackerAdvances&&!got.visualize&&got.defenderRetaliates&&got.ranged&&!got.bombing&&got.airSweep&&!got.defenderCaptured&&got.nuclearDamageLevel==3);
        CHECK(got.participants[0].hasUnit&&got.participants[0].unitOwner==2&&got.participants[0].unitId==44&&got.participants[0].unitX==7);
        CHECK(got.participants[0].hasCity&&got.participants[0].cityOwner==2&&got.participants[0].cityId==55&&got.participants[0].damageInflicted==17&&got.participants[0].finalDamage==29);
        CHECK(info.counts.plots==1&&info.counts.units==1&&info.counts.cities==1&&info.destructions==0);
        Info city;CHECK(engine.GameplayCityCombat(&city)==0&&state->combatPresentations.back().cityEvent);
        const auto before=state->combatPresentations.size();
        Info bad;bad.nullPlot=true;Reject([&]{engine.GameplayCityCombat(&bad);});CHECK(state->combatPresentations.size()==before);
        Info badPlot;badPlot.plotIndex=-1;Reject([&]{engine.GameplayCityCombat(&badPlot);});CHECK(badPlot.counts.plots==1);
        const auto beforeMalformed=state->combatPresentations.size();
        Info badCount;badCount.count=-1;Reject([&]{engine.GameplayUnitCombat(&badCount);});
        Info tooMany;tooMany.count=33;tooMany.maxCount=33;Reject([&]{engine.GameplayUnitCombat(&tooMany);});
        Info overMax;overMax.count=2;overMax.maxCount=1;Reject([&]{engine.GameplayUnitCombat(&overMax);});
        Info nullMember;nullMember.count=1;nullMember.member=nullptr;Reject([&]{engine.GameplayUnitCombat(&nullMember);});
        CvCombatMemberEntry invalidEntry{};invalidEntry.m_ePlayer=static_cast<PlayerTypes>(MAX_PLAYERS);invalidEntry.m_iID=3;
        Info invalidMember;invalidMember.count=1;invalidMember.member=&invalidEntry;Reject([&]{engine.GameplayUnitCombat(&invalidMember);});
        CvCombatMemberEntry firstEntry{};firstEntry.m_ePlayer=static_cast<PlayerTypes>(2);firstEntry.m_iID=12;
        Info invalidLast;invalidLast.count=2;invalidLast.member=&firstEntry;invalidLast.nullMemberAt=1;
        Reject([&]{engine.GameplayUnitCombat(&invalidLast);});
        Info badUnit;badUnit.owner=MAX_PLAYERS;Reject([&]{engine.GameplayUnitCombat(&badUnit);});CHECK(badUnit.counts.units==1&&badUnit.counts.cities==0);
        Info badUnitId;badUnitId.unitId=-1;Reject([&]{engine.GameplayUnitCombat(&badUnitId);});
        Info badCity;badCity.cityId=-1;Reject([&]{engine.GameplayUnitCombat(&badCity);});CHECK(badCity.counts.cities==1);
        Info badCityOwner;badCityOwner.cityOwner=MAX_PLAYERS;Reject([&]{engine.GameplayUnitCombat(&badCityOwner);});
        Info throws;throws.throwDamage=true;RejectException([&]{engine.GameplayUnitCombat(&throws);});CHECK(throws.counts.plots==1&&throws.counts.units==1&&throws.counts.cities==1);
        const auto afterFailures=state->combatPresentations.size();Reject([&]{engine.GameplayUnitCombat(nullptr);});CHECK(state->combatPresentations.size()==afterFailures);
        CHECK(state->combatPresentations.size()==beforeMalformed);
        CvCombatMemberEntry entry{};entry.m_ePlayer=static_cast<PlayerTypes>(2);entry.m_iID=88;entry.m_fWeaponOption=1.25f;
        Info copy;copy.count=1;copy.member=&entry;engine.GameplayUnitCombat(&copy);entry.m_iID=99;entry.m_fWeaponOption=9.0f;
        const auto& member=state->combatPresentations.back().damageMembers[0];CHECK(member.GetID()==88&&member.m_fWeaponOption==1.25f);
        Info empty;empty.count=0;empty.maxCount=0;empty.member=nullptr;empty.unit=false;empty.city=false;engine.GameplayUnitCombat(&empty);
        CHECK(state->combatPresentations.back().damageMembers.empty()&&!state->combatPresentations.back().participants[0].hasUnit&&!state->combatPresentations.back().participants[0].hasCity);
        UnitMock* notificationUnit=new UnitMock(info.counts,3,91);
        engine.GameplayUnitSetDamage(notificationUnit,40,12);engine.GameplayUnitDestroyed(notificationUnit);engine.GameplayUnitDestroyedInCombat(notificationUnit);
        CHECK(info.counts.units==1);delete notificationUnit;CHECK(info.counts.units==1);
        char tooltip[]="copied tooltip",summary[]="copied summary";
        ui.AddNotification(7,static_cast<NotificationTypes>(-17),tooltip,summary,23,24,static_cast<PlayerTypes>(3),5,6);
        tooltip[0]='X';summary[0]='Y';
        const auto key=std::make_pair(3,7);CHECK(state->notifications.at(key).tooltip=="copied tooltip"&&state->notifications.at(key).summary=="copied summary");
        ui.AddNotification(7,static_cast<NotificationTypes>(-18),"replacement","new",30,31,static_cast<PlayerTypes>(4));
        CHECK(state->notifications.size()==2&&state->notifications.at(std::make_pair(4,7)).tooltip=="replacement");
        ui.RemoveNotification(7,static_cast<PlayerTypes>(3));CHECK(state->notifications.size()==1&&state->notifications.count(std::make_pair(4,7))==1);
        Reject([&]{ui.AddNotification(9,static_cast<NotificationTypes>(0),nullptr,"",0,0,static_cast<PlayerTypes>(0));});

        ui.lookAt(&cameraPlot,CAMERALOOKAT_NORMAL);
        CHECK(state->cameraPresentations.size()==1&&state->cameraPresentations[0].plotIndex==123&&
              state->cameraPresentations[0].x==7&&state->cameraPresentations[0].y==9&&
              state->cameraPresentations[0].type==CAMERALOOKAT_NORMAL);
        cameraPlot.SetPosition(999,30,40);
        CHECK(state->cameraPresentations[0].plotIndex==123&&state->cameraPresentations[0].x==7&&state->cameraPresentations[0].y==9);
        const auto beforeBadCameraEvents=state->Events().size();
        Reject([&]{ui.lookAt(nullptr,CAMERALOOKAT_NORMAL);});
        Reject([&]{ui.lookAt(&cameraPlot,static_cast<CameraLookAtTypes>(-1));});
        cameraPlot.SetPosition(-1,2,3);
        Reject([&]{ui.lookAt(&cameraPlot,CAMERALOOKAT_NORMAL);});
        CHECK(state->cameraPresentations.size()==1&&state->Events().size()==beforeBadCameraEvents);

        char popupText[]="owned popup text";
        ui.AddPopupText(10,20,popupText,0.25f);
        popupText[0]='X';
        CHECK(state->popupTexts.size()==1&&state->popupTexts[0].x==10&&state->popupTexts[0].y==20&&
              state->popupTexts[0].delay==0.25f&&state->popupTexts[0].text=="owned popup text");
        const auto beforeBadText=state->popupTexts.size();
        const auto beforeBadTextEvents=state->Events().size();
        Reject([&]{ui.AddPopupText(-1,20,"bad");});
        Reject([&]{ui.AddPopupText(10,-1,"bad");});
        Reject([&]{ui.AddPopupText(10,20,nullptr);});
        Reject([&]{ui.AddPopupText(10,20,"bad",-0.1f);});
        Reject([&]{ui.AddPopupText(10,20,"bad",std::numeric_limits<float>::infinity());});
        CHECK(state->popupTexts.size()==beforeBadText&&state->Events().size()==beforeBadTextEvents);

        ui.setCombatFocus(true);CHECK(state->combatFocus);
        ui.setCombatFocus(false);CHECK(!state->combatFocus);
        const auto focusMessages=state->Events();
        CHECK(focusMessages[focusMessages.size()-2]=="ui-combat-focus:1"&&focusMessages.back()=="ui-combat-focus:0");
        CHECK(uiCounts.plots==0);
    }
    bool notificationNoLock=false;try{ui.AddNotification(9,static_cast<NotificationTypes>(0),nullptr,"",0,0,static_cast<PlayerTypes>(0));}catch(const std::logic_error&){notificationNoLock=true;}
    CHECK(notificationNoLock);
    CHECK(info.destructions==0);
    std::printf("COMBAT_PRESENTATION_PASS checks=%u GAMECORE_LOADED=false\n",checks);return 0;
}
