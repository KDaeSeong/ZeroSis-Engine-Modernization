#pragma once
#include "FirstTurnProbe.h"
#include "FoundCityProbe.h"
#include <array>
#include <cmath>

namespace ZeroSisHost {
struct CityDecisionResult {
    // turn, elapsed, player, city, trained unit type, research tech, queue size,
    // production stored/needed, research progress/left, population.
    std::array<int,12> before{},after{};
};

// One explicit headless fixture decision. Legal choices and postconditions use
// the original SDK Lua APIs. The small Network frontend forwards the stock
// SendResearch tuple to EngineServices; it does not emulate SDK research state.
class CityDecisionProbe final {
public:
    static CityDecisionResult Run(ICvGame1& game,const std::shared_ptr<HostState>& host,
                                  const FoundCityResult& founded,bool productionAlreadyChosen=false,bool researchAlreadyChosen=false){
        Require(game,*host,0);
        CityDecisionResult result;
        const auto previous=host->Events();
        {
            Context input(host);
            Thread thread(*host->scripts);
            auto& scripts=*host->scripts;
            if(!scripts.CallCFunction(thread.vm,&Bind,&input) ||
               !scripts.RegisterFunction(thread.vm,"ZeroSisCitySendResearch",&SendResearch))
                throw std::runtime_error(scripts.LastError());
            std::string source="local expectedCity="+std::to_string(founded.city)+"\n";
            source+=std::string("local productionAlreadyChosen=")+(productionAlreadyChosen?"true\n":"false\n");
            source+=std::string("local researchAlreadyChosen=")+(researchAlreadyChosen?"true\n":"false\n");
            source+=R"lua(
local player=assert(Players[Game.GetActivePlayer()])
assert(Game.GetActivePlayer()==0 and Game.GetGameTurn()==0 and player:IsHuman() and player:IsAlive() and player:IsTurnActive())
local city=assert(player:GetCityByID(expectedCity))
assert(city:GetOwner()==0 and city:IsCapital() and player:GetNumCities()==1)
assert(city:GetOrderQueueLength()==(productionAlreadyChosen and 1 or 0) and (researchAlreadyChosen or player:GetCurrentResearch()==-1), 'The fixture decision queue differs')
local units={}
for info in GameInfo.Units() do if city:CanTrain(info.ID) then units[#units+1]=info.ID end end
table.sort(units)
local unit=assert(units[1], 'No legal original unit-production choice')
local techs={}
for info in GameInfo.Technologies() do if player:CanResearch(info.ID) then techs[#techs+1]=info.ID end end
table.sort(techs)
local tech=assert(techs[1], 'No legal original research choice')
assert(city:CanTrain(unit) and player:CanResearch(tech))
if productionAlreadyChosen then assert(city:GetProductionUnit()==unit,'Official popup selected a different legal fixture unit')
else Game.CityPushOrder(city,OrderTypes.ORDER_TRAIN,unit,false,true,true) end
if researchAlreadyChosen then assert(player:GetCurrentResearch()==tech,'Official TechPopup selected a different legal technology')
else Network={SendResearch=ZeroSisCitySendResearch};Network.SendResearch(tech,0,-1,false) end
assert(city:GetProductionUnit()==unit and city:GetOrderQueueLength()==1, 'SDK did not accept the production order')
assert(player:GetCurrentResearch()==tech, 'SDK did not accept the research choice')
local teamTechs=assert(Teams[player:GetTeam()]:GetTeamTechs())
assert(city:GetProduction()==0 and city:GetProductionNeeded()>0 and teamTechs:GetResearchLeft(tech)>0)
ZeroSisCityDecisionObservation={Game.GetGameTurn(),Game.GetElapsedGameTurns(),Game.GetActivePlayer(),city:GetID(),
  unit,tech,city:GetOrderQueueLength(),city:GetProduction(),city:GetProductionNeeded(),
  player:GetResearchProgress(tech),teamTechs:GetResearchLeft(tech),city:GetPopulation()}
)lua";
            Execute(scripts,thread.vm,source);
            if(!scripts.CallCFunction(thread.vm,&Collect,&result.before))
                throw std::runtime_error(scripts.LastError());
        }
        if(!host->scripts->IsQuiescent() || !host->localCommands.IsQuiescent())
            throw std::runtime_error("City decision left live Lua wrappers or queued commands");
        Emit("CITY_DECISION_BEFORE_TURN",result.before);
        const auto events=host->Events();
        const auto delta=[&](const std::string& value){return std::count(events.begin(),events.end(),value)-std::count(previous.begin(),previous.end(),value);};
        const std::string order="local-city-order:"+std::to_string(founded.city)+":"+
            std::to_string(static_cast<int>(ORDER_TRAIN))+":"+std::to_string(result.before[4])+":0:1:1";
        const std::string research="local-research:"+std::to_string(result.before[5])+":0:-1:0";
        if(delta(order)!=(productionAlreadyChosen?0:1) || delta(research)!=(researchAlreadyChosen?0:1))
            throw std::runtime_error("City decision did not use exactly its original command tuples");
        // The stock client pumps SDK Update after an input. Notification
        // expiry belongs to that update; UpdateTestEndTurn alone reads the
        // existing notification list and does not expire satisfied choices.
        game.Update();
        Require(game,*host,0);
        const auto afterNotifications=Observe(*host,result.before);
        if(afterNotifications!=result.before)
            throw std::runtime_error("Decision notification update changed the waiting game state");
        Emit("CITY_DECISION_AFTER_NOTIFICATION_UPDATE",afterNotifications);
        std::puts("CITY_DECISION_NOTIFICATION_UPDATE=SDK_UPDATE_WITHOUT_TURN_ADVANCE");
        std::unique_ptr<ICvPlayer1> human(game.GetPlayer(static_cast<PlayerTypes>(0)));
        if(!human)throw std::runtime_error("City decision lost its active human player");
        FirstTurnProbe::AdvanceOneTurn(game,*human,*host,"CITY_DECISION_TURN_CYCLE",founded.afterUnits);
        Require(game,*host,1);
        result.after=Observe(*host,result.before);
        if(result.after[7]<=result.before[7] || result.after[9]<=result.before[9] ||
           result.after[8]!=result.before[8] || result.after[10]>=result.before[10])
            throw std::runtime_error("Normal SDK turn did not advance the selected production and research");
        Emit("CITY_DECISION_AFTER_TURN",result.after);
        return result;
    }

    static void CheckRestored(ICvGame1& game,HostState& host,const CityDecisionResult& expected){
        Require(game,host,1);
        const auto actual=Observe(host,expected.after);
        if(actual!=expected.after)throw std::runtime_error("Restored city production or research differs");
        Emit("CITY_DECISION_RESTORED",actual);
    }

private:
    struct Context {
        std::shared_ptr<HostState> host;
        EngineServices engine;
        explicit Context(const std::shared_ptr<HostState>& state):host(state),engine(state){}
    };
    struct Thread {
        ScriptSystem& scripts;lua_State* vm=nullptr;
        explicit Thread(ScriptSystem& service):scripts(service),vm(service.CreateLuaThread("Original city and research decisions")){
            if(!vm)throw std::runtime_error(service.LastError());
        }
        ~Thread(){if(vm)scripts.FreeLuaThread(vm);}
    };
    static void Require(ICvGame1& game,HostState& host,int turn){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread())
            throw std::logic_error("City decision requires the GameCore owner lock");
        if(!host.scripts || !host.scripts->GameLibrariesBound() || !host.scripts->IsQuiescent() ||
           !host.localSdkSessionBound || !host.localCommands.IsQuiescent())
            throw std::logic_error("City decision requires a quiescent bound local SDK session");
        if(game.IsGameMultiPlayer() || game.GetGameTurn()!=turn || game.GetElapsedGameTurns()!=turn ||
           game.GetActivePlayer()!=static_cast<PlayerTypes>(0) || game.GetNumGameTurnActive()!=1 ||
           game.CountNumHumanGameTurnActive()!=1)
            throw std::runtime_error("City decision left its exact normal human turn boundary");
    }
    static void Execute(ScriptSystem& scripts,lua_State* vm,const std::string& source){
        if(!scripts.Execute(vm,source.data(),source.size()))throw std::runtime_error(scripts.LastError());
    }
    static int Integer(lua_State* vm,int index,int minimum=0){
        if(lua_type(vm,index)!=LUA_TNUMBER)throw std::invalid_argument("City decision input is not an integer");
        const double value=lua_tonumber(vm,index);
        if(!std::isfinite(value) || value<minimum || value>INT_MAX || std::floor(value)!=value)
            throw std::invalid_argument("City decision input is outside its integer range");
        return static_cast<int>(value);
    }
    static int Bind(lua_State* vm){lua_pushvalue(vm,1);lua_setfield(vm,LUA_REGISTRYINDEX,"ZEROSIS_CITY_DECISION_CONTEXT");return 0;}
    static int SendResearch(lua_State* vm){
        if(lua_gettop(vm)!=4 || lua_type(vm,4)!=LUA_TBOOLEAN)
            throw std::invalid_argument("Network.SendResearch requires its four original arguments");
        const int tech=Integer(vm,1),discover=Integer(vm,2),steal=Integer(vm,3,-1);
        const bool shift=lua_toboolean(vm,4)!=0;
        lua_getfield(vm,LUA_REGISTRYINDEX,"ZEROSIS_CITY_DECISION_CONTEXT");
        auto* input=static_cast<Context*>(lua_touserdata(vm,-1));lua_pop(vm,1);
        if(!input || !input->host)throw std::logic_error("Research frontend has no owner context");
        input->engine.sendResearch(static_cast<TechTypes>(tech),discover,static_cast<PlayerTypes>(steal),shift);
        return 0;
    }
    static int Collect(lua_State* vm){
        auto* result=static_cast<std::array<int,12>*>(lua_touserdata(vm,1));
        if(!result)throw std::invalid_argument("City observation destination is absent");
        lua_settop(vm,0);lua_getglobal(vm,"ZeroSisCityDecisionObservation");
        if(!lua_istable(vm,-1) || lua_objlen(vm,-1)!=result->size())
            throw std::runtime_error("City decision observation schema differs");
        for(std::size_t i=0;i<result->size();++i){lua_rawgeti(vm,-1,static_cast<int>(i+1));(*result)[i]=Integer(vm,-1);lua_pop(vm,1);}
        return 0;
    }
    static std::array<int,12> Observe(HostState& host,const std::array<int,12>& expected){
        Thread thread(*host.scripts);
        std::string source="local expectedCity,localUnit,localTech="+std::to_string(expected[3])+","+std::to_string(expected[4])+","+std::to_string(expected[5])+"\n";
        source+=R"lua(
local player=assert(Players[Game.GetActivePlayer()])
assert(player:IsHuman() and player:IsAlive() and player:IsTurnActive() and player:GetNumCities()==1)
local city=assert(player:GetCityByID(expectedCity))
assert(city:GetOwner()==0 and city:IsCapital() and city:GetProductionUnit()==localUnit and player:GetCurrentResearch()==localTech)
assert(city:GetOrderQueueLength()==1)
local teamTechs=assert(Teams[player:GetTeam()]:GetTeamTechs())
ZeroSisCityDecisionObservation={Game.GetGameTurn(),Game.GetElapsedGameTurns(),Game.GetActivePlayer(),city:GetID(),
  localUnit,localTech,city:GetOrderQueueLength(),city:GetProduction(),city:GetProductionNeeded(),
  player:GetResearchProgress(localTech),teamTechs:GetResearchLeft(localTech),city:GetPopulation()}
)lua";
        Execute(*host.scripts,thread.vm,source);
        std::array<int,12> result{};
        if(!host.scripts->CallCFunction(thread.vm,&Collect,&result))throw std::runtime_error(host.scripts->LastError());
        return result;
    }
    static void Emit(const char* name,const std::array<int,12>& values){
        std::printf("%s=",name);
        for(std::size_t i=0;i<values.size();++i)std::printf("%s%d",i?",":"",values[i]);
        std::puts("");
    }
};
}
