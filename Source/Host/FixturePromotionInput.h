#pragma once
#include "HostServices.h"
#include <cmath>

namespace ZeroSisHost {
// Explicit input policy for the isolated continuation fixture. This uses the
// normal local SDK receiver and never edits promotion, experience or readiness
// state directly. The optional action route selects through ICvGame1 and uses
// the SDK's registered GameInfoActions / Game.HandleAction entry points. The
// fixture still supplies the user's choices; no interactive renderer is implied.
class FixturePromotionInput final {
public:
    static void Apply(ScriptSystem& scripts,lua_State* vm,HostState& host,bool unitActions=false){
        Require(host);
        if(!scripts.CallCFunction(vm,&Bind,&host) ||
           (!unitActions && !scripts.RegisterFunction(vm,"ZeroSisFixturePromote",&Send)) ||
           !scripts.RegisterFunction(vm,"ZeroSisFixturePromotionObserved",&Observe))
            throw std::runtime_error(scripts.LastError());
        if(unitActions && (!scripts.RegisterFunction(vm,"ZeroSisFixtureSelectUnit",&Select) ||
                          !scripts.RegisterFunction(vm,"ZeroSisFixtureActionObserved",&ObserveAction)))
            throw std::runtime_error(scripts.LastError());
        std::puts("EXTENDED_TURN_CYCLE_PROMOTION_POLICY=SHOCK_1_SHOCK_2_SHOCK_3_FIRST_LEGAL");
        if(unitActions)std::puts("EXTENDED_TURN_CYCLE_INPUT_ROUTE=SDK_GAME_HANDLE_ACTION");
        static const char source[]=R"lua(
local player=assert(Players[Game.GetActivePlayer()])
assert(player:IsHuman() and player:IsAlive() and player:IsTurnActive())
local choices={'PROMOTION_SHOCK_1','PROMOTION_SHOCK_2','PROMOTION_SHOCK_3'}
local ids={}
for unit in player:Units() do ids[#ids+1]=unit:GetID() end
table.sort(ids)
for _,id in ipairs(ids) do
  local unit=assert(player:GetUnitByID(id))
  while unit:IsPromotionReady() do
    local selected,selectedName=nil,nil
    for _,name in ipairs(choices) do
      local info=assert(GameInfo.UnitPromotions[name], 'Fixture promotion is absent: '..name)
      if not unit:IsHasPromotion(info.ID) and
         unit:CanDoCommand(CommandTypes.COMMAND_PROMOTION,info.ID,-1,0,1) then
        selected=info.ID; selectedName=name; break
      end
    end
    assert(selected, 'Fixture requires an explicit promotion outside its fixed input policy')
    local level,experience=unit:GetLevel(),unit:GetExperience()
    local action=nil
    if throughActions then
      ZeroSisFixtureSelectUnit(id)
      assert(type(GameInfoActions)=='table', 'The actual SDK action registry is absent')
      for index,info in pairs(GameInfoActions) do
        if info.Type==selectedName and info.CommandType==CommandTypes.COMMAND_PROMOTION and
           info.CommandData==selected and info.OriginalIndex==selected then
          assert(action==nil, 'Duplicate SDK promotion action')
          assert(type(index)=='number' and index>=0 and index%1==0 and
                 info.ActionInfoIndex==index and not info.ConfirmCommand,
                 'SDK promotion action identity or confirmation contract differs')
          action=index
        end
      end
      assert(action, 'The selected promotion has no registered SDK action')
      assert(Game.CanHandleAction(action,nil,false), 'The SDK rejected the selected unit action')
      Game.HandleAction(action)
    else
      ZeroSisFixturePromote(id,selected)
    end
    assert(unit:IsHasPromotion(selected), 'SDK did not apply the requested promotion')
    assert(unit:GetLevel()==level+1, 'SDK promotion did not advance exactly one level')
    assert(unit:GetExperience()==experience, 'Ordinary promotion changed experience')
    if throughActions then
      ZeroSisFixtureActionObserved(Game.GetGameTurn(),Game.GetActivePlayer(),id,selected,action)
    end
    ZeroSisFixturePromotionObserved(Game.GetGameTurn(),Game.GetActivePlayer(),id,selected,
      level,unit:GetLevel(),experience,unit:GetExperience())
  end
end
)lua";
        const std::string input=std::string("local throughActions=")+(unitActions?"true\n":"false\n")+source;
        if(!scripts.Execute(vm,input.data(),input.size()))throw std::runtime_error(scripts.LastError());
    }
private:
    static void Require(const HostState& host){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread())
            throw std::logic_error("Fixture unit input requires the GameCore owner lock");
    }
    static int Bind(lua_State* state){
        // HostState outlives this per-turn VM, including lua_close finalizers.
        lua_pushvalue(state,1);lua_setfield(state,LUA_REGISTRYINDEX,"ZEROSIS_FIXTURE_INPUT_HOST");return 0;
    }
    static HostState& From(lua_State* state){
        lua_getfield(state,LUA_REGISTRYINDEX,"ZEROSIS_FIXTURE_INPUT_HOST");
        auto* host=static_cast<HostState*>(lua_touserdata(state,-1));lua_pop(state,1);
        if(!host)throw std::logic_error("Fixture input host is missing");
        Require(*host);return *host;
    }
    static int Integer(lua_State* state,int index){
        if(lua_type(state,index)!=LUA_TNUMBER)throw std::invalid_argument("Fixture input requires an integer");
        const double value=lua_tonumber(state,index);
        if(!std::isfinite(value) || value<0 || value>INT_MAX || std::floor(value)!=value)
            throw std::invalid_argument("Fixture input integer is outside its range");
        return static_cast<int>(value);
    }
    static int Send(lua_State* state){
        auto& host=From(state);
        if(lua_gettop(state)!=2)throw std::invalid_argument("Fixture promotion input arity differs");
        const int unit=Integer(state,1),promotion=Integer(state,2);
        host.localCommands.SendUnitCommand(unit,COMMAND_PROMOTION,promotion,-1,false);
        host.Record("fixture-unit-promotion:"+std::to_string(unit)+":"+std::to_string(promotion));
        return 0;
    }
    static int Observe(lua_State* state){
        From(state);
        if(lua_gettop(state)!=8)throw std::invalid_argument("Fixture promotion observation arity differs");
        int values[8];for(int index=0;index<8;++index)values[index]=Integer(state,index+1);
        if(values[1]>=MAX_PLAYERS || values[4]==INT_MAX || values[5]!=values[4]+1 || values[6]!=values[7])
            throw std::runtime_error("Fixture promotion observation is invalid");
        std::printf("EXTENDED_TURN_CYCLE_PROMOTION=%d,%d,%d,%d,%d,%d,%d,%d\n",
            values[0],values[1],values[2],values[3],values[4],values[5],values[6],values[7]);
        return 0;
    }
    static int Select(lua_State* state){
        auto& host=From(state);
        if(lua_gettop(state)!=1)throw std::invalid_argument("Fixture selection input arity differs");
        const int unit=Integer(state,1);
        if(!host.selectLocalUnit)throw std::logic_error("Local SDK selection input is not bound");
        host.selectLocalUnit(unit);
        return 0;
    }
    static int ObserveAction(lua_State* state){
        auto& host=From(state);
        if(lua_gettop(state)!=5)throw std::invalid_argument("Fixture action observation arity differs");
        int values[5];for(int index=0;index<5;++index)values[index]=Integer(state,index+1);
        if(values[1]>=MAX_PLAYERS)throw std::invalid_argument("Fixture action player is outside SDK slots");
        host.Record("fixture-unit-promotion:"+std::to_string(values[2])+":"+std::to_string(values[3]));
        host.Record("fixture-unit-action:"+std::to_string(values[2])+":"+std::to_string(values[4]));
        std::printf("EXTENDED_TURN_CYCLE_ACTION=%d,%d,%d,%d,%d\n",
            values[0],values[1],values[2],values[3],values[4]);
        return 0;
    }
};
}
