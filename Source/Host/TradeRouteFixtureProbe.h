#pragma once
#include "LocalSdkSession.h"
#include "LocalTurnController.h"
#include "SdkGameSave.h"
#include "SdkStateSnapshot.h"
#include "TradeRouteSmokeFixture.h"
#include <algorithm>
#include <cmath>
#include <climits>
#include <cstdio>
#include <cstring>
#include <iomanip>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace ZeroSisHost {
// Bounded headless diagnostic for trade-mission execution on a disposable
// fresh game. It records the SDK getters and TradeVisuals callbacks after each
// Update; it does not establish GUI, retail-rendering, or game-equivalence proof.
class TradeRouteFixtureProbe final {
public:
    static void Run(ICvGameContext3& context,const std::shared_ptr<HostState>& state,
                    const std::wstring& directory,const std::wstring& bundle){
        if(!state || state->gameThread!=GetCurrentThreadId() || !state->gameLock.HeldByCurrentThread())
            throw std::logic_error("Trade-route fixture requires the GameCore owner lock");
        if(!state->scripts || !state->scripts->GameLibrariesBound() || !state->scripts->IsQuiescent() ||
           state->localSdkSessionBound || !state->localCommands.IsQuiescent() ||
           state->popupVisible || state->addPopup || state->addArrayPopup || state->closeInformationalPopup)
            throw std::logic_error("Trade-route fixture requires a quiescent headless SDK session without UI context");

        std::unique_ptr<ICvGame1> game(context.GetGame());
        std::unique_ptr<ICvNetMessageHandler1> receiver(context.GetNetMessageHandler());
        if(!game || !receiver || !game->IsFinalInitialized() || game->IsGameMultiPlayer() ||
           game->GetGameTurn()!=0 || game->GetElapsedGameTurns()!=0 ||
           game->GetActivePlayer()!=static_cast<PlayerTypes>(0) || game->GetNumGameTurnActive()!=1 ||
           game->CountNumHumanGameTurnActive()!=1)
            throw std::logic_error("Trade-route diagnostic requires the fresh active human turn at turn zero");
        std::unique_ptr<ICvPlayer1> human(game->GetPlayer(static_cast<PlayerTypes>(0)));
        if(!human || !human->IsAlive() || !human->IsHuman() || !human->IsTurnActive())
            throw std::logic_error("Trade-route diagnostic has no active human player");

        LocalSdkSession localSession(*state,*receiver,*game,context);
        SdkGameSave saves(context,*state,directory,bundle);
        AwardRequests awardRequests(*state,context);
        ScriptSystem& scripts=*state->scripts;
        UnitContext unitContext{game.get()};
        ResearchContext researchContext{state};
        Thread thread(scripts,"Trade-route fixture diagnostic");
        if(!scripts.CallCFunction(thread.vm,&BindUnitContext,&unitContext) ||
           !scripts.CallCFunction(thread.vm,&BindResearchContext,&researchContext) ||
           !scripts.RegisterFunction(thread.vm,"ZeroSisTradeRouteObserveUnit",&ObserveUnit) ||
           !scripts.RegisterFunction(thread.vm,"ZeroSisTradeRouteSendResearch",&SendResearch))
            throw std::runtime_error(scripts.LastError());

        std::puts("TRADE_ROUTE_FIXTURE_PROBE_SCOPE=HEADLESS_SOURCE_DIAGNOSTIC_ONLY_GUI_AND_RETAIL_EQUIVALENCE_UNPROVEN");
        const auto plan=TradeRouteSmokeFixture::Prepare(*state,scripts,thread.vm,false);
        if(awardRequests.Count()!=2)
            throw std::runtime_error("Trade fixture did not issue exactly its two informational technology awards");
        WriteSample(directory,L"prepared",plan.before,state->tradeRoutes.SnapshotJson());
        ObserveUnits(scripts,thread.vm,0);

        const int mission=plan.missions.front().mission; // MissionTypes value returned by SDK Lua.
        TradeRouteSmokeFixture::Dispatch(*state,*receiver,plan,mission);
        game->Update();
        RecordUpdate(*game,*state,scripts,thread.vm,directory,1);
        RequireWaiting(*game,*state,0);

        ChooseProductionAndResearch(scripts,thread.vm);
        game->Update();
        RecordUpdate(*game,*state,scripts,thread.vm,directory,2);
        RequireWaiting(*game,*state,0);
        LocalTurnController controller(*state,*game);
        state->localCommands.SendPlayerOption(PLAYEROPTION_WAIT_END_TURN,true);
        std::puts("TRADE_ROUTE_FIXTURE_PLAYER_OPTION=PLAYEROPTION_WAIT_END_TURN:1");
        game->UpdateTestEndTurn();
        SkipHumanReadyUnits(scripts,thread.vm,*receiver);
        game->UpdateTestEndTurn();
        const int begin=game->GetGameTurn();
        if(begin!=0 || game->GetElapsedGameTurns()!=begin || !human->IsTurnActive())
            throw std::logic_error("Trade-route end-turn input left the original turn boundary");
        const char endTurn[]=R"lua(
local p=assert(Players[Game.GetActivePlayer()])
assert(Game.CanDoControl(ControlTypes.CONTROL_ENDTURN),
  'End-turn blocked: '..p:GetEndTurnBlockingType()..' ready='..tostring(p:HasReadyUnit())..' busy='..tostring(p:HasBusyUnit()))
Game.DoControl(ControlTypes.CONTROL_ENDTURN)
)lua";
        Execute(scripts,thread.vm,endTurn);
        controller.CommitCompletion();

        unsigned updates=2;bool nextHumanTurn=false;
        for(;updates<256;){
            game->Update();
            ++updates;
            RecordUpdate(*game,*state,scripts,thread.vm,directory,updates);
            if(!state->localCommands.IsQuiescent() || *scripts.LastError())
                throw std::runtime_error("Trade-route turn update left incomplete commands or a script failure");
            if(game->GetGameTurn()<begin || game->GetGameTurn()>begin+1 ||
               game->GetElapsedGameTurns()!=game->GetGameTurn())
                throw std::runtime_error("Trade-route diagnostic advanced beyond its one-turn bound");
            if(game->GetGameTurn()==begin+1 && human->IsTurnActive()){nextHumanTurn=true;break;}
        }
        if(!nextHumanTurn || game->GetGameTurn()!=begin+1 || game->GetNumGameTurnActive()!=1 ||
           game->CountNumHumanGameTurnActive()!=1 || !human->IsAlive() || !human->IsHuman() ||
           !human->IsTurnActive() || state->turnSignals.HasSentTurnComplete() ||
           state->turnSignals.HasSentTurnAllComplete())
            throw std::runtime_error("SDK did not return to the next human turn within 256 updates");

        const auto finalInventory=TradeRouteSmokeFixture::CaptureInventory(*state,scripts,thread.vm);
        EmitInventory("TRADE_ROUTE_FIXTURE_FINAL",finalInventory);
        WriteSample(directory,L"final",finalInventory,state->tradeRoutes.SnapshotJson());
        if(!TradeRouteSmokeFixture::MeetsSmokeMinimum(finalInventory))
            throw std::runtime_error("Trade-route final SDK inventory below minimum: active="+
                std::to_string(finalInventory.activePlayer)+" outbound="+std::to_string(finalInventory.outbound.size())+
                " inbound="+std::to_string(finalInventory.inbound.size())+
                " available="+std::to_string(finalInventory.available.size()));
        std::printf("TRADE_ROUTE_FIXTURE_AUTOSAVES=%u\n",saves.Count());
        std::puts("TRADE_ROUTE_FIXTURE_DIAGNOSTIC_PASS=ONE_NORMAL_SDK_TURN_ONLY");
    }

private:
    // A headless diagnostic records only these informational requests. It does
    // not claim that they were displayed or that any stock UI callback ran.
    // The interactive smoke separately exercises the original Continue button.
    class AwardRequests final {
    public:
        AwardRequests(HostState& host,ICvGameContext3& context):host_(host){
            const int techCount=context.GetNumTechInfos();
            host_.addPopup=[this,techCount](const CvPopupInfo& input){
                if(input.eButtonPopupType!=BUTTONPOPUP_TECH_AWARD || input.iData1!=0 || input.iData2!=0 ||
                   input.iData3<0 || input.iData3>=techCount || requests_.size()>=2)
                    throw std::runtime_error("Unexpected headless popup request: type="+
                        std::to_string(static_cast<int>(input.eButtonPopupType))+" data="+
                        std::to_string(input.iData1)+","+std::to_string(input.iData2)+","+std::to_string(input.iData3));
                requests_.emplace_back(input);
                std::printf("TRADE_ROUTE_PROBE_AWARD_REQUEST_RETAINED_NOT_DISPLAYED=%d|%d|%d\n",
                    input.iData1,input.iData2,input.iData3);
            };
        }
        ~AwardRequests(){host_.addPopup={};}
        std::size_t Count() const noexcept{return requests_.size();}
        AwardRequests(const AwardRequests&)=delete;AwardRequests& operator=(const AwardRequests&)=delete;
    private:
        HostState& host_;std::vector<OwnedPopupInfo> requests_;
    };
    struct Thread final {
        ScriptSystem& scripts;lua_State* vm=nullptr;
        Thread(ScriptSystem& service,const char* name):scripts(service),vm(service.CreateLuaThread(name)){
            if(!vm)throw std::runtime_error(service.LastError());
        }
        ~Thread(){if(vm)scripts.FreeLuaThread(vm);}
        Thread(const Thread&)=delete;Thread& operator=(const Thread&)=delete;
    };
    struct UnitContext final {ICvGame1* game=nullptr;};
    struct ResearchContext final {
        std::shared_ptr<HostState> state;
        EngineServices engine;
        explicit ResearchContext(const std::shared_ptr<HostState>& value):state(value),engine(value){}
    };

    static void Execute(ScriptSystem& scripts,lua_State* vm,const char* source){
        if(!scripts.Execute(vm,source,std::strlen(source)))throw std::runtime_error(scripts.LastError());
    }
    static int BindUnitContext(lua_State* vm){
        auto* value=static_cast<UnitContext*>(lua_touserdata(vm,1));
        if(!value || !value->game)throw std::invalid_argument("Trade-route unit observer context is absent");
        lua_pushvalue(vm,1);lua_setfield(vm,LUA_REGISTRYINDEX,"ZEROSIS_TRADE_ROUTE_UNIT_CONTEXT");return 0;
    }
    static int BindResearchContext(lua_State* vm){
        auto* value=static_cast<ResearchContext*>(lua_touserdata(vm,1));
        if(!value || !value->state)throw std::invalid_argument("Trade-route research context is absent");
        lua_pushvalue(vm,1);lua_setfield(vm,LUA_REGISTRYINDEX,"ZEROSIS_TRADE_ROUTE_RESEARCH_CONTEXT");return 0;
    }
    static int ReadLuaInteger(lua_State* vm,int index,int minimum,int maximum){
        if(lua_type(vm,index)!=LUA_TNUMBER)throw std::invalid_argument("Trade-route probe field is not numeric");
        const double value=lua_tonumber(vm,index);
        if(!std::isfinite(value) || value<minimum || value>maximum || std::floor(value)!=value)
            throw std::invalid_argument("Trade-route probe field is outside its integer range");
        return static_cast<int>(value);
    }
    static int ObserveUnit(lua_State* vm){
        if(lua_gettop(vm)!=6 || lua_type(vm,3)!=LUA_TBOOLEAN)
            throw std::invalid_argument("Trade-route unit observer requires owner,id,automated,moves,x,y");
        const int owner=ReadLuaInteger(vm,1,0,MAX_PLAYERS-1),id=ReadLuaInteger(vm,2,0,INT_MAX);
        const bool automated=lua_toboolean(vm,3)!=0;
        const int moves=ReadLuaInteger(vm,4,INT_MIN,INT_MAX);
        const int x=ReadLuaInteger(vm,5,0,INT_MAX),y=ReadLuaInteger(vm,6,0,INT_MAX);
        lua_getfield(vm,LUA_REGISTRYINDEX,"ZEROSIS_TRADE_ROUTE_UNIT_CONTEXT");
        auto* context=static_cast<UnitContext*>(lua_touserdata(vm,-1));lua_pop(vm,1);
        if(!context || !context->game)throw std::logic_error("Trade-route unit observer lost its SDK context");
        std::unique_ptr<ICvPlayer1> player(context->game->GetPlayer(static_cast<PlayerTypes>(owner)));
        std::unique_ptr<ICvUnit1> unit(player?player->GetUnit(id):nullptr);
        if(!player || player->GetID()!=owner || !unit || unit->GetOwner()!=owner || unit->GetID()!=id ||
           unit->GetMoves()!=moves || unit->GetX()!=x || unit->GetY()!=y)
            throw std::runtime_error("Lua unit observation differs from the public SDK unit interface");
        std::unique_ptr<ICvMissionData1> head(unit->GetHeadMissionData());
        std::printf("TRADE_ROUTE_PROBE_UNIT=%d|%d|%d|%d|%d|%d|%d|%d|%d|%d\n",
            context->game->GetGameTurn(),owner,id,automated?1:0,moves,x,y,
            head?static_cast<int>(head->GetMissionType()):-1,head?head->GetData1():-1,head?head->GetData2():-1);
        return 0;
    }
    static int SendResearch(lua_State* vm){
        if(lua_gettop(vm)!=4 || lua_type(vm,4)!=LUA_TBOOLEAN)
            throw std::invalid_argument("Original research command requires its four SDK arguments");
        const int tech=ReadLuaInteger(vm,1,0,INT_MAX),discover=ReadLuaInteger(vm,2,0,INT_MAX);
        const int steal=ReadLuaInteger(vm,3,-1,MAX_PLAYERS-1);const bool shift=lua_toboolean(vm,4)!=0;
        lua_getfield(vm,LUA_REGISTRYINDEX,"ZEROSIS_TRADE_ROUTE_RESEARCH_CONTEXT");
        auto* context=static_cast<ResearchContext*>(lua_touserdata(vm,-1));lua_pop(vm,1);
        if(!context || !context->state)throw std::logic_error("Research command lost its host context");
        context->engine.sendResearch(static_cast<TechTypes>(tech),discover,static_cast<PlayerTypes>(steal),shift);
        return 0;
    }
    static void ObserveUnits(ScriptSystem& scripts,lua_State* vm,int turn){
        std::string source="assert(Game.GetGameTurn()=="+std::to_string(turn)+")\n";
        source+=R"lua(
for _,owner in ipairs({0,1}) do
  local player=assert(Players[owner])
  for unit in player:Units() do
    assert(unit:GetOwner()==owner)
    ZeroSisTradeRouteObserveUnit(owner,unit:GetID(),unit:IsAutomated(),unit:GetMoves(),unit:GetX(),unit:GetY())
  end
end
)lua";
        Execute(scripts,vm,source.c_str());
    }
    static void ChooseProductionAndResearch(ScriptSystem& scripts,lua_State* vm){
        static const char source[]=R"lua(
local player=assert(Players[Game.GetActivePlayer()])
assert(Game.GetActivePlayer()==0 and Game.GetGameTurn()==0 and player:IsHuman() and player:IsAlive() and player:IsTurnActive())
local city=assert(player:GetCapitalCity())
assert(city:GetOrderQueueLength()==0 and player:GetCurrentResearch()==-1,
  'Fresh fixture capital already has a production or research choice')
local units={}
for info in GameInfo.Units() do if city:CanTrain(info.ID) then units[#units+1]=info.ID end end
table.sort(units)
local techs={}
for info in GameInfo.Technologies() do if player:CanResearch(info.ID) then techs[#techs+1]=info.ID end end
table.sort(techs)
local unit=assert(units[1],'No legal unit-production choice exists in the fixture capital')
local tech=assert(techs[1],'No legal research choice exists for the human player')
Game.CityPushOrder(city,OrderTypes.ORDER_TRAIN,unit,false,true,true)
Network=Network or {};Network.SendResearch=ZeroSisTradeRouteSendResearch
Network.SendResearch(tech,0,-1,false)
assert(city:GetProductionUnit()==unit and city:GetOrderQueueLength()==1)
assert(player:GetCurrentResearch()==tech)
print('TRADE_ROUTE_FIXTURE_CITY_RESEARCH='..city:GetID()..'|'..unit..'|'..tech)
)lua";
        Execute(scripts,vm,source);
    }
    struct SkipPlan final {int mission=-1;std::vector<int> units;};
    static int ReadSkipPlan(lua_State* vm){
        auto* plan=static_cast<SkipPlan*>(lua_touserdata(vm,1));
        if(!plan)throw std::invalid_argument("Missing headless skip-plan destination");
        lua_getglobal(vm,"ZeroSisTradeProbeSkipMission");plan->mission=ReadLuaInteger(vm,-1,0,INT_MAX);lua_pop(vm,1);
        lua_getglobal(vm,"ZeroSisTradeProbeSkipUnits");
        if(!lua_istable(vm,-1) || lua_objlen(vm,-1)>256)
            throw std::runtime_error("Invalid headless SDK skip-plan array");
        const std::size_t count=lua_objlen(vm,-1);
        for(std::size_t index=1;index<=count;++index){
            lua_rawgeti(vm,-1,static_cast<int>(index));const int id=ReadLuaInteger(vm,-1,0,INT_MAX);lua_pop(vm,1);
            if(std::find(plan->units.begin(),plan->units.end(),id)!=plan->units.end())
                throw std::runtime_error("Duplicate headless skip unit identity");
            plan->units.push_back(id);
        }
        lua_pop(vm,1);return 0;
    }
    static void SkipHumanReadyUnits(ScriptSystem& scripts,lua_State* vm,ICvNetMessageHandler1& receiver){
        static const char source[]=R"lua(
local player=assert(Players[Game.GetActivePlayer()])
local skip=assert(MissionTypes.MISSION_SKIP)
assert(type(skip)=='number' and skip>=0 and skip%1==0)
ZeroSisTradeProbeSkipMission=skip
ZeroSisTradeProbeSkipUnits={}
for unit in player:Units() do
  if not unit:IsAutomated() and not unit:IsDelayedDeath() and not unit:IsBusy() then
    assert(unit:CanStartMission(skip,-1,-1,unit:GetPlot(),0))
    ZeroSisTradeProbeSkipUnits[#ZeroSisTradeProbeSkipUnits+1]=unit:GetID()
  end
end
)lua";
        Execute(scripts,vm,source);
        SkipPlan plan;
        if(!scripts.CallCFunction(vm,&ReadSkipPlan,&plan))throw std::runtime_error(scripts.LastError());
        if(!scripts.IsQuiescent())throw std::logic_error("Skip dispatch must occur after the Lua callback returns");
        for(const int id:plan.units)
            receiver.ResponsePushMission(static_cast<PlayerTypes>(0),id,static_cast<MissionTypes>(plan.mission),-1,-1,0,false);
        Execute(scripts,vm,"assert(not Players[Game.GetActivePlayer()]:HasReadyUnit(),'Human ready units remain after SDK receiver skip inputs')");
        std::printf("TRADE_ROUTE_FIXTURE_HUMAN_SKIP_COUNT=%zu\n",plan.units.size());
    }
    static void RequireWaiting(ICvGame1& game,HostState& state,int turn){
        if(!state.localCommands.IsQuiescent() || !state.scripts->IsQuiescent() || *state.scripts->LastError() ||
           game.IsGameMultiPlayer() || game.GetGameTurn()!=turn || game.GetElapsedGameTurns()!=turn ||
           game.GetActivePlayer()!=static_cast<PlayerTypes>(0) || game.GetNumGameTurnActive()!=1 ||
           game.CountNumHumanGameTurnActive()!=1)
            throw std::runtime_error("Trade-route diagnostic left its exact active human turn boundary");
    }
    static void EmitInventory(const char* marker,const TradeRouteSmokeFixture::Inventory& inventory){
        std::printf("%s=%d|%d|%d|%zu|%zu|%zu\n",marker,inventory.activePlayer,inventory.turn,
            inventory.elapsed,inventory.outbound.size(),inventory.inbound.size(),inventory.available.size());
    }
    static void WriteSample(const std::wstring& directory,const std::wstring& stage,
                            const TradeRouteSmokeFixture::Inventory& inventory,const std::string& visuals){
        const std::wstring prefix=directory+L"\\trade-probe-"+stage;
        WriteJson(prefix+L"-inventory.json",TradeRouteSmokeFixture::SerializeInventory(inventory));
        WriteJson(prefix+L"-presentation.json",visuals);
    }
    static void WriteJson(const std::wstring& path,const std::string& json){
        if(json.empty() || json.size()>16u*1024u*1024u)
            throw std::runtime_error("Trade-route diagnostic JSON is empty or exceeds its bound");
        SdkStateSnapshot::Write(path,json);
    }
    static void RecordUpdate(ICvGame1& game,HostState& state,ScriptSystem& scripts,lua_State* vm,
                             const std::wstring& directory,unsigned index){
        const auto inventory=TradeRouteSmokeFixture::CaptureInventory(state,scripts,vm);
        EmitInventory("TRADE_ROUTE_PROBE_UPDATE",inventory);
        std::wostringstream stage;stage<<L"update-"<<std::setw(3)<<std::setfill(L'0')<<index;
        WriteSample(directory,stage.str(),inventory,state.tradeRoutes.SnapshotJson());
        ObserveUnits(scripts,vm,game.GetGameTurn());
    }
};
} // namespace ZeroSisHost
