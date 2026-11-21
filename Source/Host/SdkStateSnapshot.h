#pragma once
#include "HostServices.h"
#include "NativeSaveArchive.h"

namespace ZeroSisHost {
// A read-only semantic sample of real SDK objects. This deliberately does not
// claim to cover every serialized field or the engine's full deterministic state.
class SdkStateSnapshot final {
public:
    static std::string Capture(HostState& host){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread() ||
           !host.scripts || !host.scripts->IsQuiescent())
            throw std::logic_error("State snapshot requires a quiescent owner-thread game");
        auto& scripts=*host.scripts;
        struct Thread {ScriptSystem& scripts;lua_State* vm=nullptr;~Thread(){if(vm)scripts.FreeLuaThread(vm);}} thread{scripts};
        thread.vm=scripts.CreateLuaThread("Native save state comparison");
        static const char source[]=R"lua(
local rows={}
local function row(...)
  local values={...}
  for i=1,#values do
    local value=values[i]
    assert(type(value)=='number' or type(value)=='boolean' or type(value)=='string')
    if type(value)=='boolean' then value=value and 1 or 0 end
    values[i]=tostring(value)
    assert(not values[i]:find('[|\r\n]'))
  end
  rows[#rows+1]=table.concat(values,'|')
end
local function hex(value)
  local result={}
  for i=1,#value do result[i]=string.format('%02x',string.byte(value,i)) end
  return table.concat(result)
end
local function objects(iterator,state,first)
  local result={}
  for value in iterator,state,first do result[#result+1]=value end
  table.sort(result,function(a,b) return a:GetID()<b:GetID() end)
  return result
end
row('G',Game.GetGameTurn(),Game.GetElapsedGameTurns(),Game.GetActivePlayer(),Map.GetNumPlots())
for i=0,Map.GetNumPlots()-1 do
  local p=assert(Map.GetPlotByIndex(i))
  row('M',i,p:GetX(),p:GetY(),p:GetPlotType(),p:GetTerrainType(),p:GetFeatureType(),
      p:GetResourceType(-1),p:GetNumResource(),p:GetImprovementType(),p:GetRouteType(),p:GetOwner())
end
for id=0,63 do
  local p=assert(Players[id])
  row('P',id,p:IsAlive(),p:IsHuman(),p:IsTurnActive(),p:GetTeam(),p:GetNumCities(),p:GetNumUnits(),
      p:GetGold(),p:GetJONSCulture(),p:GetCurrentResearch())
  for _,u in ipairs(objects(p:Units())) do
    row('U',id,u:GetID(),u:GetUnitType(),u:GetX(),u:GetY(),u:GetMoves(),u:GetDamage(),
        u:GetExperience(),u:GetLevel(),u:GetActivityType(),u:IsEmbarked(),hex(u:GetScriptData()))
  end
  for _,c in ipairs(objects(p:Cities())) do
    row('C',id,c:GetID(),c:GetX(),c:GetY(),c:GetPopulation(),c:GetFoodTimes100(),c:GetProductionTimes100(),
        c:GetProductionUnit(),c:GetProductionBuilding(),c:GetDamage(),hex(c:GetNameKey()))
  end
  local t=assert(Teams[id])
  local techs={}
  for tech in GameInfo.Technologies() do techs[#techs+1]=tech.ID end
  table.sort(techs)
  for _,tech in ipairs(techs) do row('T',id,tech,t:IsHasTech(tech)) end
end
ZeroSisSaveStateSnapshot=table.concat(rows,'\n')..'\n'
)lua";
        if(!scripts.Execute(thread.vm,source,sizeof(source)-1))throw std::runtime_error(scripts.LastError());
        std::string output;
        if(!scripts.CallCFunction(thread.vm,&Collect,&output))throw std::runtime_error(scripts.LastError());
        return output;
    }
    static void Write(const std::wstring& path,const std::string& bytes){
        NativeSaveTransaction output(path);std::size_t at=0;
        while(at<bytes.size()){
            DWORD written=0;const auto count=static_cast<DWORD>((std::min<std::size_t>)(1024*1024,bytes.size()-at));
            if(!WriteFile(output.Get(),bytes.data()+at,count,&written,nullptr) || !written || written>count)
                throw std::runtime_error("State snapshot write failed");
            at+=written;
        }
        output.Commit();
    }
private:
    static int Collect(lua_State* vm){
        auto* output=static_cast<std::string*>(lua_touserdata(vm,1));
        if(!output)return luaL_error(vm,"State snapshot output is missing");
        lua_getglobal(vm,"ZeroSisSaveStateSnapshot");
        if(lua_type(vm,-1)!=LUA_TSTRING)return luaL_error(vm,"State snapshot is not a string");
        std::size_t size=0;const auto* value=lua_tolstring(vm,-1,&size);
        if(!size || size>16*1024*1024)return luaL_error(vm,"State snapshot size is invalid");
        output->assign(value,size);return 0;
    }
};
}
