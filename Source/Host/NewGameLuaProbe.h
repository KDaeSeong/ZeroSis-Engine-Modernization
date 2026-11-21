#pragma once

#include "HostServices.h"
#include <climits>
#include <cmath>
#include <cstring>

namespace ZeroSisHost {

struct NewGameLuaObservation {
    int plots;
    int land;
    int water;
    int missingTerrain;
    int majorPlayers;
    int minorPlayers;
    int majorUnits;
    int minorUnits;
};

struct NewGameLuaProbeDetail final {
    static int ObservationInteger(lua_State* state,int index) {
        if(lua_type(state,index)!=LUA_TNUMBER)
            return luaL_error(state,"New-game observation field is not numeric");
        const lua_Number value=lua_tonumber(state,index);
        if(!std::isfinite(value) || value<INT_MIN || value>INT_MAX || std::floor(value)!=value)
            return luaL_error(state,"New-game observation field is not an exact integer");
        return static_cast<int>(value);
    }
    static int CollectObservation(lua_State* state) {
        auto* output=static_cast<NewGameLuaObservation*>(lua_touserdata(state,1));
        if(!output)return luaL_error(state,"New-game observation destination is missing");
        lua_settop(state,0);
        lua_getglobal(state,"ZeroSisNewGameObservation");
        if(!lua_istable(state,-1))return luaL_error(state,"New-game Lua observation table is missing");
        lua_rawgeti(state,-1,1);output->plots=ObservationInteger(state,-1);lua_pop(state,1);
        lua_rawgeti(state,-1,2);output->land=ObservationInteger(state,-1);lua_pop(state,1);
        lua_rawgeti(state,-1,3);output->water=ObservationInteger(state,-1);lua_pop(state,1);
        lua_rawgeti(state,-1,4);output->missingTerrain=ObservationInteger(state,-1);lua_pop(state,1);
        lua_rawgeti(state,-1,5);output->majorPlayers=ObservationInteger(state,-1);lua_pop(state,1);
        lua_rawgeti(state,-1,6);output->minorPlayers=ObservationInteger(state,-1);lua_pop(state,1);
        lua_rawgeti(state,-1,7);output->majorUnits=ObservationInteger(state,-1);lua_pop(state,1);
        lua_rawgeti(state,-1,8);output->minorUnits=ObservationInteger(state,-1);lua_pop(state,1);
        lua_pop(state,1);
        return 0;
    }
};

// Reads real SDK Lua objects from the initialized GameCore. The caller must
// already hold HostState's owner-thread GameCore lock; the borrowed VM is
// returned before this function exits.
inline NewGameLuaObservation InspectNewGameLua(HostState& host) {
    if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread())
        throw std::logic_error("New-game Lua inspection requires the GameCore owner lock");
    if(!host.scripts || !host.scripts->GameLibrariesBound() || host.scripts->IsClosed() || !host.scripts->IsQuiescent())
        throw std::logic_error("New-game Lua inspection requires an open, quiescent GameCore script service");

    auto& scripts=*host.scripts;
    struct LuaThread final {
        ICvEngineScriptSystem1& service;
        lua_State* state=nullptr;
        ~LuaThread(){if(state)service.FreeLuaThread(state);}
    } thread{scripts};

    thread.state=scripts.CreateLuaThread("New game state inspection");
    static const char source[]=R"lua(
local plots=Map.GetNumPlots()
assert(type(plots)=='number' and plots>0 and plots%1==0, 'Map has no initialized plots')
local land,water,missingTerrain=0,0,0
for index=0,plots-1 do
  local plot=Map.GetPlotByIndex(index)
  assert(plot~=nil, 'Map.GetPlotByIndex returned no real plot')
  local terrain=plot:GetTerrainType()
  local plotType=plot:GetPlotType()
  local isWater=plot:IsWater()
  assert(type(terrain)=='number' and terrain%1==0, 'Plot terrain is not an integer')
  assert(type(plotType)=='number' and plotType%1==0 and plotType>=0 and plotType<PlotTypes.NUM_PLOT_TYPES,
    'Plot type is invalid')
  assert(type(isWater)=='boolean', 'Plot water state is not boolean')
  assert(isWater==(plotType==PlotTypes.PLOT_OCEAN), 'Plot type and water state disagree')
  if not GameInfo.Terrains[terrain] then missingTerrain=missingTerrain+1 end
  if isWater then water=water+1 else land=land+1 end
end

local majorPlayers,minorPlayers,majorUnits,minorUnits=0,0,0,0
for id,player in pairs(Players) do
  assert(type(id)=='number' and type(player)=='table', 'Players contains an invalid SDK entry')
  assert(player:GetID()==id, 'Players key differs from SDK player ID')
  if player:IsAlive() and not player:IsBarbarian() then
    if player:IsMinorCiv() then
      minorPlayers=minorPlayers+1
      minorUnits=minorUnits+player:GetNumUnits()
    else
      majorPlayers=majorPlayers+1
      assert(player:GetStartingPlot()~=nil, 'An active major has no starting plot')
      local units=player:GetNumUnits()
      assert(units>0, 'An active major has no initial units')
      majorUnits=majorUnits+units
    end
  end
end

ZeroSisNewGameObservation={plots,land,water,missingTerrain,majorPlayers,minorPlayers,majorUnits,minorUnits}
)lua";
    if(!scripts.Execute(thread.state,source,sizeof(source)-1))
        throw std::runtime_error(scripts.LastError());

    NewGameLuaObservation result{};
    if(!scripts.CallCFunction(thread.state,&NewGameLuaProbeDetail::CollectObservation,&result))
        throw std::runtime_error(scripts.LastError());
    if(result.plots<=0 || result.land<=0 || result.water<=0)
        throw std::runtime_error("New-game Lua map has no plots, land or water");
    if(result.missingTerrain!=0)
        throw std::runtime_error("New-game Lua map contains plots with unknown terrain");
    if(result.majorPlayers!=2 || result.minorPlayers!=2)
        throw std::runtime_error("New-game Lua player counts differ from the configured two majors and two city-states");
    if(result.majorUnits<=0)
        throw std::runtime_error("New-game Lua inspection found no major starting units");
    return result;
}

}
