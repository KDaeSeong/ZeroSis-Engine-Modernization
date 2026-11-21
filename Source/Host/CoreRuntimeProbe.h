#pragma once
#include "HostServices.h"
#include <array>

namespace ZeroSisHost {
// This probe calls the actual bound SDK libraries. It never fabricates game objects.
// The VM deliberately outlives GC.Uninit so its last callback can test retired handles.
class CoreRuntimeProbe {
public:
    void Begin(HostState& host) {
        if(started_)throw std::logic_error("Core runtime probe already started");
        if(!host.scripts || !host.scripts->GameLibrariesBound())throw std::logic_error("Core libraries are not bound");
        started_=true;host_=&host;GameCall call(host);auto& scripts=*host.scripts;
        auto* vm=scripts.CreateLuaThread("Actual GameCore runtime probe");
        const char* source=R"lua(
local players,teams,types=0,0,0
for id,player in pairs(Players) do assert(player:GetID()==id); players=players+1 end
for id,team in pairs(Teams) do assert(team:GetID()==id); teams=teams+1 end
for name,value in pairs(GameInfoTypes) do assert(type(name)=='string' and type(value)=='number'); types=types+1 end
local width,height=Map.GetGridSize()
ZeroSisCoreObservation={players,teams,width,height,Map.GetNumPlots(),Game.GetGameTurn(),types,
    GameInfoTypes.UNIT_SETTLER,GameInfoTypes.CIVILIZATION_AMERICA,GameInfoTypes.BUILDING_MONUMENT,
    type(GameInfo)=='table' and 1 or 0}
assert(type(GameInfo)=='table')
local tables={'Worlds','Terrains','Features','Resources','Improvements','Eras',
  'Civilizations','Units','Buildings','MapScripts','Map_Sizes','Natural_Wonder_Placement'}
ZeroSisGameInfoObservation={}
for index,name in ipairs(tables) do
  local count=0
  for row in GameInfo[name]() do
    count=count+1
    if row.ID~=nil and row.Type~=nil then
      assert(GameInfo[name][row.ID].Type==row.Type and GameInfo[name][row.Type].ID==row.ID)
    end
  end
  ZeroSisGameInfoObservation[index]=count
end
local noGoodies,wonders,settlers=0,0,0
for era in GameInfo.Eras() do
  assert(type(era.NoGoodies)=='boolean')
  if era.NoGoodies then noGoodies=noGoodies+1 end
end
for feature in GameInfo.Features{NaturalWonder=true} do
  assert(feature.NaturalWonder==true); wonders=wonders+1
end
for unit in GameInfo.Units{Class='UNITCLASS_SETTLER',Combat=0} do settlers=settlers+1 end
ZeroSisGameInfoObservation[13]=GameInfo.Terrains.TERRAIN_GRASS.ID
ZeroSisGameInfoObservation[14]=GameInfo.Eras.ERA_ANCIENT.NoGoodies and 1 or 0
ZeroSisGameInfoObservation[15]=noGoodies
ZeroSisGameInfoObservation[16]=wonders
ZeroSisGameInfoObservation[17]=settlers
assert(GameInfo.Units("Type='UNIT_SETTLER'")().ID==GameInfoTypes.UNIT_SETTLER)
)lua";
        if(!scripts.Execute(vm,source,std::strlen(source)))throw std::runtime_error(scripts.LastError());
        if(!scripts.CallCFunction(vm,&CollectAndRetain,this))throw std::runtime_error(scripts.LastError());
        if(values_[0]!=MAX_PLAYERS || values_[1]!=MAX_TEAMS || values_[2]!=0 || values_[3]!=0 || values_[4]!=0 || values_[6]<=0 || values_[10]!=1)
            throw std::runtime_error("Unexpected initialized GameCore/Lua object state");
        observed_=true;
    }
    int TypeValue(unsigned index) const{return values_.at(7+index);}
    std::string Observation() const {
        if(!observed_)throw std::logic_error("Core runtime probe is incomplete");
        std::string result="CORE_LUA_OBSERVATION=";
        for(std::size_t i=0;i<values_.size();++i){if(i)result+=",";result+=std::to_string(values_[i]);}
        result+="\nGAME_INFO_OBSERVATION=";
        for(std::size_t i=0;i<gameInfo_.size();++i){if(i)result+=",";result+=std::to_string(gameInfo_[i]);}
        return result;
    }
    std::string ShutdownObservation() const {
        if(!observed_ || finalizers_!=1 || !closedAfterGlobals_ || !locked_ || !playerRetired_ || !teamRetired_)
            throw std::runtime_error("Actual GameCore borrowed-handle retirement was not verified");
        return "CORE_LUA_SHUTDOWN_PASS finalizers=1 player_retired=true team_retired=true owner_lock=true globals_stopped=true";
    }
private:
    template<std::size_t N> static void Collect(lua_State* vm,const char* name,std::array<int,N>& values){
        lua_getglobal(vm,name);if(!lua_istable(vm,-1))luaL_error(vm,"Core observations missing");
        for(std::size_t i=0;i<N;++i){
            lua_rawgeti(vm,-1,static_cast<int>(i+1));
            if(lua_type(vm,-1)!=LUA_TNUMBER)luaL_error(vm,"Core observation is not numeric");
            const auto value=lua_tonumber(vm,-1);
            if(!std::isfinite(value) || value<INT_MIN || value>INT_MAX || std::floor(value)!=value)luaL_error(vm,"Core observation is not an integer");
            values[i]=static_cast<int>(value);lua_pop(vm,1);
        }
        lua_pop(vm,1);
    }
    static int CollectAndRetain(lua_State* vm){
        auto* self=static_cast<CoreRuntimeProbe*>(lua_touserdata(vm,1));lua_settop(vm,0);
        Collect(vm,"ZeroSisCoreObservation",self->values_);Collect(vm,"ZeroSisGameInfoObservation",self->gameInfo_);
        lua_newuserdata(vm,1);lua_newtable(vm);
        lua_pushlightuserdata(vm,self);lua_pushcclosure(vm,&Finalize,1);lua_setfield(vm,-2,"__gc");
        lua_setmetatable(vm,-2);lua_setglobal(vm,"ZeroSisCoreRetirementProbe");return 0;
    }
    static bool Retired(lua_State* vm,const char* table){
        const int base=lua_gettop(vm);lua_getglobal(vm,table);
        if(!lua_istable(vm,-1)){lua_settop(vm,base);return false;}
        lua_rawgeti(vm,-1,0);
        if(!lua_istable(vm,-1)){lua_settop(vm,base);return false;}
        lua_getfield(vm,-1,"GetID");lua_pushvalue(vm,-2);
        const bool failed=lua_pcall(vm,1,1,0)!=0;
        const bool stale=failed && lua_type(vm,-1)==LUA_TSTRING && std::strstr(lua_tostring(vm,-1),"Not a valid instance.");
        lua_settop(vm,base);return stale;
    }
    static int Finalize(lua_State* vm){
        auto* self=static_cast<CoreRuntimeProbe*>(lua_touserdata(vm,lua_upvalueindex(1)));
        ++self->finalizers_;
        self->closedAfterGlobals_=!self->host_->globalsStarted.load();
        self->locked_=self->host_->gameThread==GetCurrentThreadId() && self->host_->gameLock.HeldByCurrentThread();
        self->playerRetired_=Retired(vm,"Players");self->teamRetired_=Retired(vm,"Teams");return 0;
    }
    HostState* host_=nullptr;
    std::array<int,11> values_{};
    std::array<int,17> gameInfo_{};
    unsigned finalizers_=0;
    bool started_=false,observed_=false,closedAfterGlobals_=false,locked_=false,playerRetired_=false,teamRetired_=false;
};
}
