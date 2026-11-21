#pragma once
#include "HostServices.h"
#include <algorithm>
#include <cmath>

namespace ZeroSisHost {
struct FoundCityChoice {
    int player=0,unit=0,mission=0,action=0,x=0,y=0,beforeCities=0,beforeUnits=0;
};
struct FoundCityResult {
    FoundCityChoice input;
    int city=0,population=0,afterUnits=0,updates=0;
};

// A separate, explicit fixture input. It selects the original starting settler
// and sends its registered SDK action. No unit, city, production, research or
// readiness state is written by this fixture. Only owned IDs survive Update.
class FoundCityProbe final {
public:
    static FoundCityResult Run(ICvGame1& game,HostState& host){
        Require(host);
        if(!host.localSdkSessionBound || !host.selectLocalUnit || !host.localCommands.IsQuiescent())
            throw std::logic_error("Founding input requires a quiescent local SDK session");
        FoundCityResult result;
        const auto previous=host.Events();
        auto& scripts=*host.scripts;
        {
            Thread thread(scripts,"Original starting settler action");
            if(!scripts.CallCFunction(thread.vm,&Bind,&host) ||
               !scripts.RegisterFunction(thread.vm,"ZeroSisFoundSelectUnit",&Select))
                throw std::runtime_error(scripts.LastError());
            static const char source[]=R"lua(
local active=Game.GetActivePlayer()
local player=assert(Players[active])
assert(active==0 and Game.GetGameTurn()==0 and Game.GetElapsedGameTurns()==0)
assert(player:IsHuman() and player:IsAlive() and player:IsTurnActive())
assert(player:GetNumCities()==0 and player:GetNumUnits()==2)
local mission=MissionTypes.MISSION_FOUND
assert(type(mission)=='number' and mission>=0 and mission%1==0)
local settlerType=assert(GameInfo.Units.UNIT_SETTLER).ID
local ids={}
for unit in player:Units() do
  if unit:GetUnitType()==settlerType and not unit:IsDelayedDeath() and not unit:IsBusy() and
     unit:CanStartMission(mission,-1,-1,unit:GetPlot(),0) then
    ids[#ids+1]=unit:GetID()
  end
end
table.sort(ids)
assert(#ids==1, 'The original fixture has no unique legal starting settler')
local id=ids[1]
local unit=assert(player:GetUnitByID(id))
local plot=assert(unit:GetPlot())
local start=assert(player:GetStartingPlot())
assert(plot:GetX()==start:GetX() and plot:GetY()==start:GetY(), 'Starting settler moved before its action')
local resource=plot:GetResourceType(-1)
for _,name in ipairs({'RESOURCE_ARTIFACTS','RESOURCE_HIDDEN_ARTIFACTS'}) do
  local info=GameInfo.Resources[name]
  assert(not info or resource~=info.ID, 'Founding requires an unsupported artifact confirmation')
end
ZeroSisFoundSelectUnit(id)
assert(type(GameInfoActions)=='table')
local action=nil
for index,info in pairs(GameInfoActions) do
  if info.Type=='MISSION_FOUND' and info.MissionType==mission and info.OriginalIndex==mission then
    assert(action==nil, 'Duplicate SDK founding action')
    assert(type(index)=='number' and index>=0 and index%1==0 and
           info.ActionInfoIndex==index and info.MissionData==-1 and not info.ConfirmCommand,
           'SDK founding action identity or confirmation contract differs')
    action=index
  end
end
assert(action, 'No registered SDK founding action')
assert(Game.CanHandleAction(action,nil,false), 'SDK rejected the selected starting settler action')
ZeroSisFoundCityChoice={active,id,mission,action,plot:GetX(),plot:GetY(),player:GetNumCities(),player:GetNumUnits()}
Game.HandleAction(action)
ZeroSisFoundActionSubmitted=true
)lua";
            if(!scripts.Execute(thread.vm,source,sizeof(source)-1) ||
               !scripts.CallCFunction(thread.vm,&Collect,&result.input))
                throw std::runtime_error(scripts.LastError());
        }
        const auto& input=result.input;
        std::printf("FOUND_CITY_ACTION=0,%d,%d,%d,%d,%d,%d,%d,%d\n",input.player,input.unit,
                    input.mission,input.action,input.x,input.y,input.beforeCities,input.beforeUnits);
        if(input.player!=0 || input.beforeCities!=0 || input.beforeUnits!=2)
            throw std::runtime_error("Founding action departed from the original starting fixture");
        // A send/receiver callback is not an acknowledgement of city creation.
        // Pump the actual SDK, then discard each fresh unit wrapper before the
        // next update. Never retain a settler pointer across its delayed death.
        for(int step=0;step<256;++step){
            game.Update();++result.updates;
            CheckWaiting(game,host);
            std::unique_ptr<ICvPlayer1> player(game.GetPlayer(static_cast<PlayerTypes>(input.player)));
            if(!player)throw std::runtime_error("Founding lost the active SDK player");
            std::unique_ptr<ICvUnit1> settler(player->GetUnit(input.unit));
            if(!settler)break;
            if(step==255)throw std::runtime_error("SDK did not finish the founding settler's delayed death");
        }
        Check(game,host,result,false);
        if(host.localSelection.Length()!=0)
            throw std::runtime_error("Founding left a destroyed settler in the local selection");
        const auto events=host.Events();
        const auto delta=[&](const std::string& value){
            return std::count(events.begin(),events.end(),value)-std::count(previous.begin(),previous.end(),value);
        };
        const std::string command="local-push-mission:"+std::to_string(input.unit)+":"+std::to_string(input.mission)+":-1:-1:0:0";
        if(delta(command)!=1 || delta("gameplay-unit-activate:"+std::to_string(input.player)+":"+std::to_string(input.unit))!=1 ||
           delta("gameplay-unit-mission-end:"+std::to_string(input.player)+":"+std::to_string(input.unit))!=1 ||
           delta("ui-city-message:0:"+std::to_string(input.player)+":"+std::to_string(result.city)+":"+std::to_string(input.player))!=1)
            throw std::runtime_error("Founding SDK command or owned presentation notifications differ");
        // CvUnit's destructor sends GameplayUnitDestroyed only when graphics
        // are initialized. Actual player lookup/count above prove destruction
        // in this headless profile; a renderer callback cannot be its oracle.
        {
            std::lock_guard<std::mutex> guard(host.dataMutex);
            const auto matches=std::count_if(host.presentationMessages.begin(),host.presentationMessages.end(),
                [&](const PresentationMessage& message){
                    return message.cityMessage && message.cityOwner==input.player && message.cityId==result.city &&
                        message.player==input.player && message.parentEvent==0 && message.length==-1 &&
                        message.type==MESSAGE_TYPE_MAJOR_EVENT && !message.text.empty() &&
                        message.flashX==input.x && message.flashY==input.y;
                });
            if(matches!=1)throw std::runtime_error("Founding city message was not retained with its exact SDK metadata");
        }
        std::printf("FOUND_CITY_OBSERVATION=0,%d,%d,%d,%d,%d,%d,0,1,2,%d,%d,%d\n",
                    input.player,input.unit,result.city,input.x,input.y,result.population,
                    result.afterUnits,result.updates,input.action);
        std::puts("FOUND_CITY_SELECTION_PRUNED=true\nFOUND_CITY_INPUT_ROUTE=SDK_GAME_HANDLE_ACTION\nFOUND_CITY_NO_DECISION_SELECTED=true");
        return result;
    }

    static void Check(ICvGame1& game,HostState& host,FoundCityResult& expected,bool restored){
        CheckWaiting(game,host);
        const auto& input=expected.input;
        std::unique_ptr<ICvPlayer1> player(game.GetPlayer(static_cast<PlayerTypes>(input.player)));
        if(!player || player->GetNumCities()!=input.beforeCities+1)
            throw std::runtime_error("SDK did not preserve exactly one founded human city");
        std::unique_ptr<ICvUnit1> settler(player->GetUnit(input.unit));
        if(settler)throw std::runtime_error("Founding settler still exists in the actual SDK player");
        std::unique_ptr<ICvCity1> city(player->GetCapitalCity());
        if(!city || city->GetOwner()!=input.player || city->GetID()<0 || city->GetX()!=input.x || city->GetY()!=input.y || city->GetPopulation()<1)
            throw std::runtime_error("Founded SDK capital differs from the selected original starting plot");
        const int units=CountUnits(*player);
        if(units!=input.beforeUnits-1)throw std::runtime_error("Founding consumed units beyond the one starting settler");
        if(restored){
            if(city->GetID()!=expected.city || city->GetPopulation()!=expected.population || units!=expected.afterUnits)
                throw std::runtime_error("Fresh-session restore changed the founded capital or surviving units");
            std::printf("FOUND_CITY_RESTORED_OBSERVATION=0,%d,%d,%d,%d,%d,%d,1,%d\n",
                        input.player,input.unit,expected.city,input.x,input.y,expected.population,expected.afterUnits);
        }else{
            expected.city=city->GetID();expected.population=city->GetPopulation();expected.afterUnits=units;
        }
    }
private:
    struct Thread {
        ScriptSystem& scripts;lua_State* vm=nullptr;
        Thread(ScriptSystem& service,const char* label):scripts(service),vm(service.CreateLuaThread(label)){}
        ~Thread(){if(vm)scripts.FreeLuaThread(vm);}
    };
    static int CountUnits(ICvPlayer1& player){
        int cursor=0,count=0;
        std::unique_ptr<ICvUnit1> unit(player.FirstUnit(&cursor));
        while(unit){if(count==INT_MAX)throw std::overflow_error("Founding unit count overflow");++count;unit.reset(player.NextUnit(&cursor));}
        return count;
    }
    static void Require(const HostState& host){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread())
            throw std::logic_error("Founding input requires the GameCore owner lock");
        if(!host.scripts || !host.scripts->GameLibrariesBound() || !host.scripts->IsQuiescent())
            throw std::logic_error("Founding input requires the quiescent actual SDK script service");
    }
    static void CheckWaiting(ICvGame1& game,HostState& host){
        Require(host);
        if(game.IsGameMultiPlayer() || game.GetGameTurn()!=0 || game.GetElapsedGameTurns()!=0 ||
           game.GetActivePlayer()!=static_cast<PlayerTypes>(0) || game.GetNumGameTurnActive()!=1 ||
           game.CountNumHumanGameTurnActive()!=1 || !host.localCommands.IsQuiescent() || *host.scripts->LastError())
            throw std::runtime_error("Founding advanced beyond the original human waiting turn");
        std::unique_ptr<ICvPlayer1> player(game.GetPlayer(static_cast<PlayerTypes>(0)));
        if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())
            throw std::runtime_error("Founding did not preserve the active human's live turn");
    }
    static int Bind(lua_State* vm){lua_pushvalue(vm,1);lua_setfield(vm,LUA_REGISTRYINDEX,"ZEROSIS_FOUND_INPUT_HOST");return 0;}
    static int Integer(lua_State* vm,int index){
        if(lua_type(vm,index)!=LUA_TNUMBER)throw std::invalid_argument("Founding choice is not an integer");
        const double value=lua_tonumber(vm,index);
        if(!std::isfinite(value) || value<0 || value>INT_MAX || std::floor(value)!=value)
            throw std::invalid_argument("Founding choice is outside its integer range");
        return static_cast<int>(value);
    }
    static int Select(lua_State* vm){
        if(lua_gettop(vm)!=1)throw std::invalid_argument("Founding selection has the wrong arity");
        const int id=Integer(vm,1);
        lua_getfield(vm,LUA_REGISTRYINDEX,"ZEROSIS_FOUND_INPUT_HOST");
        auto* host=static_cast<HostState*>(lua_touserdata(vm,-1));lua_pop(vm,1);
        if(!host)throw std::logic_error("Founding selection host is absent");
        if(host->gameThread!=GetCurrentThreadId() || !host->gameLock.HeldByCurrentThread() || !host->selectLocalUnit)
            throw std::logic_error("Founding selection requires the bound owner-thread SDK input");
        host->selectLocalUnit(id);return 0;
    }
    static int Collect(lua_State* vm){
        auto* choice=static_cast<FoundCityChoice*>(lua_touserdata(vm,1));
        if(!choice)throw std::invalid_argument("Founding choice destination is missing");
        lua_settop(vm,0);lua_getglobal(vm,"ZeroSisFoundActionSubmitted");
        if(lua_type(vm,-1)!=LUA_TBOOLEAN || !lua_toboolean(vm,-1))throw std::runtime_error("Founding action was not submitted");
        lua_pop(vm,1);lua_getglobal(vm,"ZeroSisFoundCityChoice");
        if(!lua_istable(vm,-1) || lua_objlen(vm,-1)!=8)throw std::runtime_error("Founding choice schema differs");
        int values[8];for(int index=0;index<8;++index){lua_rawgeti(vm,-1,index+1);values[index]=Integer(vm,-1);lua_pop(vm,1);}
        *choice={values[0],values[1],values[2],values[3],values[4],values[5],values[6],values[7]};return 0;
    }
};
}
