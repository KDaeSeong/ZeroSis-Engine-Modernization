#pragma once

#include "HostServices.h"
#include "ScriptSystem.h"
#include "UiSnapshotJson.h"
#include <sstream>
#include <algorithm>
#include <cmath>
#include <climits>
#include <cstring>
#include <string>
#include <utility>
#include <vector>

namespace ZeroSisHost {

// Explicitly opt-in disposable-game fixture. It uses the SDK Lua city/unit
// constructors and the SDK trade-route mission/receiver path; route rows are
// never synthesized in Lua. Restore callers must pass restore=true, which
// performs inventory only and leaves the restored world untouched.
// The two fixture-created AI caravans use UNITAI_UNKNOWN only until their
// queued missions consume them. This prevents HomelandAI from replacing the
// explicit fixture orders; normal owner turns and AutoMission still execute.
class TradeRouteSmokeFixture final {
public:
    struct RouteRow final {
        int fromOwner=-1,toOwner=-1,fromCity=-1,toCity=-1,domain=-1,turnsLeft=-1;
        int fromGPT=0,toGPT=0,toFood=0,toProduction=0,fromScience=0,toScience=0;
        int toReligion=-1,toPressure=0,fromReligion=-1,fromPressure=0,fromTourism=0,toTourism=0;
        int fromCivilization=-1,toCivilization=-1;
        std::string fromName,toName;
    };
    struct Inventory final {
        int activePlayer=-1,turn=-1,elapsed=-1;
        std::vector<RouteRow> outbound,inbound,available;
    };
    struct Mission final {
        int owner=-1,unit=-1,mission=-1,destinationPlot=-1,connectionType=-1;
        int originX=-1,originY=-1,destinationX=-1,destinationY=-1;
        bool outbound=false;
    };
    struct Plan final {
        int activePlayer=-1,turn=-1,elapsed=-1;
        int createdCities=0;
        std::vector<Mission> missions;
        Inventory before;
        bool restored=false;
    };

    static Plan Prepare(HostState& host,ScriptSystem& scripts,lua_State* vm,bool restore){
        RequireOwner(host,scripts);
        if(!vm || !scripts.GameLibrariesBound())
            throw std::logic_error("Trade-route fixture requires the quiescent SDK Lua VM");
        Plan result;result.restored=restore;
        if(!restore){
            const std::string source=FreshSetupLua();
            if(!scripts.Execute(vm,source.data(),source.size(),"trade-route-smoke-setup"))
                throw std::runtime_error(scripts.LastError());
            if(!scripts.CallCFunction(vm,&ReadPlan,&result))
                throw std::runtime_error(scripts.LastError());
            if(result.activePlayer!=0 || result.turn!=0 || result.elapsed!=0 || result.missions.size()!=4)
                throw std::runtime_error("Trade-route setup did not return the bounded fresh-game mission plan");
            if(result.createdCities!=2)
                throw std::runtime_error("Trade-route fixture must create exactly two nearby player 1 cities");
            unsigned outbound=0,inbound=0;
            for(const auto& mission:result.missions){
                if(mission.owner<0 || mission.owner>=MAX_PLAYERS || mission.unit<0 || mission.mission<0 ||
                   mission.destinationPlot<0 || mission.connectionType!=static_cast<int>(TRADE_CONNECTION_INTERNATIONAL) ||
                   mission.originX<0 || mission.originY<0 || mission.destinationX<0 || mission.destinationY<0)
                    throw std::runtime_error("Trade-route setup returned an invalid SDK mission tuple");
                if(mission.outbound){if(mission.owner!=0)throw std::runtime_error("Outbound fixture owner is not player 0");++outbound;}
                else{if(mission.owner==0)throw std::runtime_error("Inbound fixture owner is player 0");++inbound;}
            }
            if(outbound!=2 || inbound!=2)
                throw std::runtime_error("Trade-route setup did not prepare two outbound and two inbound SDK missions");
        }
        result.before=CaptureInventory(host,scripts,vm);
        if(!restore && (result.before.activePlayer!=0 || result.before.available.size()<2))
            throw std::runtime_error("SDK trade-route inventory lacks the expected fresh player or available rows");
        if(restore){result.activePlayer=result.before.activePlayer;result.turn=result.before.turn;result.elapsed=result.before.elapsed;}
        return result;
    }

    static Inventory CaptureInventory(HostState& host,ScriptSystem& scripts,lua_State* vm){
        RequireOwner(host,scripts);
        if(!vm || !scripts.GameLibrariesBound())
            throw std::logic_error("Trade-route inventory requires the quiescent SDK Lua VM");
        static const char source[]=R"lua(
local p=assert(Players[Game.GetActivePlayer()])
local function canonical(rows)
  assert(type(rows)=='table','SDK trade-route getter did not return a table')
  local result={}
  for i,row in ipairs(rows) do
    assert(type(row)=='table','SDK trade-route row is not a table')
    local from=assert(row.FromCity,'SDK route row has no FromCity userdata')
    local to=assert(row.ToCity,'SDK route row has no ToCity userdata')
    assert(type(from)=='table' and type(rawget(from,'__instance'))=='userdata',
           'SDK FromCity wrapper is not backed by its native userdata instance')
    assert(type(to)=='table' and type(rawget(to,'__instance'))=='userdata',
           'SDK ToCity wrapper is not backed by its native userdata instance')
    result[i]={row.FromID,row.ToID,from:GetID(),to:GetID(),row.Domain,row.TurnsLeft,
      row.FromCityName,row.ToCityName,from:GetOwner(),to:GetOwner(),
      row.FromGPT,row.ToGPT,row.ToFood,row.ToProduction,row.FromScience,row.ToScience,
      row.ToReligion,row.ToPressure,row.FromReligion,row.FromPressure,row.FromTourism,row.ToTourism,
      row.FromCivilizationType,row.ToCivilizationType}
  end
  return result
end
ZeroSisTradeRouteInventory={Game.GetActivePlayer(),Game.GetGameTurn(),Game.GetElapsedGameTurns(),
  canonical(p:GetTradeRoutes()),canonical(p:GetTradeRoutesToYou()),canonical(p:GetTradeRoutesAvailable())}
)lua";
        Inventory result;
        if(!scripts.Execute(vm,source,sizeof(source)-1,"trade-route-sdk-inventory") ||
           !scripts.CallCFunction(vm,&ReadInventory,&result))
            throw std::runtime_error(scripts.LastError());
        return result;
    }

    // CvDllNetMessageHandler::ResponsePushMission enters the SDK's
    // dispatchingNetMessage guard before calling CvUnit::PushMission, which
    // is required for human-owned units. The SDK will execute this ordinary
    // mission; this method only queues the tuples returned by Prepare().
    static void Dispatch(HostState& host,ICvNetMessageHandler1& receiver,const Plan& plan,int expectedMission){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread() ||
           !host.localCommands.IsQuiescent())
            throw std::logic_error("Trade-route dispatch requires the quiescent GameCore owner lock");
        if(expectedMission<0 || plan.restored || plan.activePlayer!=0 || plan.turn!=0 || plan.elapsed!=0 || plan.missions.size()!=4)
            throw std::logic_error("Only a fresh explicit trade-route fixture plan may be dispatched");
        unsigned outbound=0,inbound=0;
        std::vector<std::pair<int,int>> ownerUnitIds;
        int firstOutboundTarget=-1,secondOutboundTarget=-1;
        for(const auto& mission:plan.missions){
            if(mission.owner<0 || mission.owner>=MAX_PLAYERS || mission.unit<0 || mission.mission<0 ||
               mission.mission!=expectedMission || mission.destinationPlot<0 ||
               mission.connectionType!=static_cast<int>(TRADE_CONNECTION_INTERNATIONAL))
                throw std::invalid_argument("Trade-route dispatch tuple is outside its verified bounds");
            const auto identity=std::make_pair(mission.owner,mission.unit);
            if(std::find(ownerUnitIds.begin(),ownerUnitIds.end(),identity)!=ownerUnitIds.end())
                throw std::invalid_argument("Trade-route smoke plan reuses a unit ID");
            ownerUnitIds.push_back(identity);
            if(mission.outbound){
                if(mission.owner!=0 || ++outbound>2)
                    throw std::invalid_argument("Outbound trade-route tuple must belong to player 0");
                if(firstOutboundTarget<0)firstOutboundTarget=mission.destinationPlot;
                else secondOutboundTarget=mission.destinationPlot;
            }else if(mission.owner==1){
                ++inbound;
            }else throw std::invalid_argument("Inbound trade-route tuple must belong to player 1");
        }
        if(outbound!=2 || inbound!=2 || firstOutboundTarget<0 || secondOutboundTarget<0 ||
           firstOutboundTarget==secondOutboundTarget)
            throw std::invalid_argument("Trade-route plan must contain two distinct player 0 destinations and two player 1 routes");
        for(const auto& mission:plan.missions){
            receiver.ResponsePushMission(static_cast<PlayerTypes>(mission.owner),mission.unit,
                static_cast<MissionTypes>(mission.mission),mission.destinationPlot,mission.connectionType,0,false);
        }
    }

    static bool MeetsSmokeMinimum(const Inventory& inventory){
        return inventory.activePlayer==0 && inventory.outbound.size()>=2 &&
            inventory.inbound.size()>=2 && inventory.available.size()>=2;
    }

    static std::string SerializeInventory(const Inventory& inventory){
        std::ostringstream output;
        output<<"{\"schema\":\"ZEROSIS_TRADE_ROUTE_SDK_INVENTORY_V1\",\"source\":\"SDK:GetTradeRoutes/GetTradeRoutesToYou/GetTradeRoutesAvailable\""
              <<",\"activePlayer\":"<<inventory.activePlayer<<",\"turn\":"<<inventory.turn<<",\"elapsed\":"<<inventory.elapsed;
        AppendRows(output,"outbound",inventory.outbound);AppendRows(output,"inbound",inventory.inbound);
        AppendRows(output,"available",inventory.available);output<<"}\n";return output.str();
    }

private:
    static std::string FreshSetupLua(){
        std::string source="local fixtureAI="+std::to_string(static_cast<int>(UNITAI_UNKNOWN))+"\n";
        source+=R"lua(
assert(Game.GetActivePlayer()==0 and Game.GetGameTurn()==0 and Game.GetElapsedGameTurns()==0,
       'Synthetic trade-route setup is fresh-game only')
local p=assert(Players[0])
assert(p:IsAlive() and p:IsHuman() and p:IsTurnActive(),'Player 0 is not the active human')
assert(not ZeroSisTradeRouteFixturePrepared,'Trade-route fixture setup was already requested')
local rival=assert(Players[1])
assert(rival:IsAlive() and not rival:IsMinorCiv() and not rival:IsBarbarian() and rival:GetTeam()~=p:GetTeam(),
       'The bounded fixture requires player 1 to be a live rival major')
local connection=)lua";
        source+=std::to_string(static_cast<int>(TRADE_CONNECTION_INTERNATIONAL));
        source+=R"lua(
local mission=assert(MissionTypes.MISSION_ESTABLISH_TRADE_ROUTE)
local caravan=assert(GameInfo.Units.UNIT_CARAVAN).ID
local function cityFor(player)
  local city=player:GetCapitalCity()
  if city then return city end
  local start=player:GetStartingPlot()
  assert(start,'Fixture player has no existing capital or starting plot')
  local existing=start:GetPlotCity()
  if existing then
    assert(existing:GetOwner()==player:GetID(),'Fixture starting plot belongs to another city')
    return existing
  end
  assert(not start:IsWater() and not start:IsMountain() and player:CanFound(start:GetX(),start:GetY()),
         'SDK rejected the fixture starting plot as a legal city site')
  local created=assert(player:InitCity(start:GetX(),start:GetY(),1,1),'SDK InitCity failed for fixture start')
  assert(created:GetOwner()==player:GetID() and created:IsCapital(),'SDK did not create the fixture capital')
  return created
end
local home=cityFor(p)
local originalForeignCapital=cityFor(rival)
local pTeam=assert(Teams[p:GetTeam()]);local rivalTeam=assert(Teams[rival:GetTeam()])
assert(not pTeam:IsAtWar(rival:GetTeam()),'Trade-route fixture cannot use a rival at war')
pTeam:Meet(rival:GetTeam(),true);rivalTeam:Meet(p:GetTeam(),true)
assert(pTeam:IsHasMet(rival:GetTeam()) and rivalTeam:IsHasMet(p:GetTeam()),'SDK did not establish reciprocal team contact')
local nearbySites={}
for index=0,Map.GetNumPlots()-1 do
  local plot=Map.GetPlotByIndex(index)
  if plot and not plot:IsWater() and not plot:IsMountain() and not plot:IsCity() and
     plot:GetArea()==home:Plot():GetArea() then
    local distance=Map.PlotDistance(home:GetX(),home:GetY(),plot:GetX(),plot:GetY())
    if distance>=4 and distance<=8 and rival:CanFound(plot:GetX(),plot:GetY()) then
      nearbySites[#nearbySites+1]=plot
    end
  end
end
local firstSite,secondSite=nil,nil
table.sort(nearbySites,function(a,b)
  local da=Map.PlotDistance(home:GetX(),home:GetY(),a:GetX(),a:GetY())
  local db=Map.PlotDistance(home:GetX(),home:GetY(),b:GetX(),b:GetY())
  if da==db then return a:GetPlotIndex()<b:GetPlotIndex() end
  return da<db
end)
for i=1,#nearbySites do
  for j=i+1,#nearbySites do
    local distance=Map.PlotDistance(nearbySites[i]:GetX(),nearbySites[i]:GetY(),nearbySites[j]:GetX(),nearbySites[j]:GetY())
    if distance>=4 then firstSite,secondSite=nearbySites[i],nearbySites[j];break end
  end
  if firstSite then break end
end
assert(firstSite and secondSite,'Player 1 has fewer than two legal nearby city sites with safe spacing')
local foreignA=assert(rival:InitCity(firstSite:GetX(),firstSite:GetY(),1,1),
                      'SDK InitCity rejected player 1 nearby city site A')
assert(foreignA:GetOwner()==1 and rival:CanFound(secondSite:GetX(),secondSite:GetY()),
       'Player 1 second nearby site became illegal after founding city A')
local foreignB=assert(rival:InitCity(secondSite:GetX(),secondSite:GetY(),1,1),
                      'SDK InitCity rejected player 1 nearby city site B')
assert(foreignA:GetID()~=foreignB:GetID() and foreignA:GetOwner()==1 and foreignB:GetOwner()==1 and
       rival:GetCapitalCity():GetID()==originalForeignCapital:GetID() and rival:GetNumCities()>=3,
       'SDK did not preserve player 1 capital and create two distinct nearby cities')
home:Plot():SetRevealed(rival:GetTeam(),true,0)
foreignA:Plot():SetRevealed(p:GetTeam(),true,0)
foreignB:Plot():SetRevealed(p:GetTeam(),true,0)

local function ensureSlots(player,wanted)
  local team=assert(Teams[player:GetTeam()])
  local techs=assert(team:GetTeamTechs())
  local attempts=0
  while player:GetNumInternationalTradeRoutesAvailable()<wanted do
    attempts=attempts+1;assert(attempts<16,'No real technology grants the required trade-route capacity')
    local choices={}
    for info in GameInfo.Technologies() do
      if (info.InternationalTradeRoutesChange or 0)>0 and not techs:HasTech(info.ID) then
        choices[#choices+1]=info
      end
    end
    table.sort(choices,function(a,b)return a.ID<b.ID end)
    local choice=assert(choices[1],'SDK rules contain no unused positive trade-route-capacity technology')
    -- Omit the broken optional ePlayer/bFirst slots in this SDK wrapper:
    -- the two-argument call reaches CvTeam::setHasTech with bFirst=false.
    team:SetHasTech(choice.ID,true)
    assert(techs:HasTech(choice.ID),'SDK rejected the real trade-route-capacity technology')
  end
end
ensureSlots(p,2)
ensureSlots(rival,2)

local function legalRoute(owner,from,to)
  local unit=owner:InitUnit(caravan,from:GetX(),from:GetY())
  assert(unit and unit:GetUnitType()==caravan and unit:GetDomainType()==DomainTypes.DOMAIN_LAND,
         'SDK did not create a land caravan at its real origin city')
  local plot=to:Plot()
  local target=plot:GetPlotIndex()
  local at=unit:CanMakeTradeRouteAt(from:Plot(),to:GetX(),to:GetY(),connection)
  local canStart=unit:CanStartMission(mission,target,connection,from:Plot(),0)
  return unit,at,canStart,target
end

local outA,outAAt,outACan,outATarget=legalRoute(p,home,foreignA)
local outB,outBAt,outBCan,outBTarget=legalRoute(p,home,foreignB)
local inA,inAAt,inACan,inATarget=legalRoute(rival,foreignA,home)
local inB,inBAt,inBCan,inBTarget=legalRoute(rival,foreignB,home)
-- Only these disposable fixture units opt out of AI target selection. The
-- public mission receiver and ordinary AI AutoMission phase still own route
-- creation. Neither the AI player nor the turn scheduler is changed.
assert(type(fixtureAI)=='number' and fixtureAI>=0,'Missing SDK fixture AI-role value')
for _,unit in ipairs({inA,inB}) do
  unit:SetUnitAIType(fixtureAI)
  assert(unit:GetUnitAIType()==fixtureAI and not unit:IsAutomated(),
         'Fixture caravan did not retain its explicit AI-role exception')
  assert(unit:CanStartMission(mission,home:Plot():GetPlotIndex(),connection,unit:GetPlot(),0),
         'Fixture AI-role exception changed SDK trade mission eligibility')
end
assert(outAAt and outACan and outBAt and outBCan and inAAt and inACan and inBAt and inBCan,
       'SDK CanMakeTradeRouteAt/CanStartMission rejected one or more real player 0/player 1 city routes')
local routes=assert(p:GetTradeRoutesAvailable())
assert(#routes>=2,'SDK GetTradeRoutesAvailable returned fewer than two real available rows')
local plan={
  {0,outA:GetID(),mission,outATarget,connection,home:GetX(),home:GetY(),foreignA:GetX(),foreignA:GetY(),true},
  {0,outB:GetID(),mission,outBTarget,connection,home:GetX(),home:GetY(),foreignB:GetX(),foreignB:GetY(),true},
  {1,inA:GetID(),mission,inATarget,connection,foreignA:GetX(),foreignA:GetY(),home:GetX(),home:GetY(),false},
  {1,inB:GetID(),mission,inBTarget,connection,foreignB:GetX(),foreignB:GetY(),home:GetX(),home:GetY(),false}}
ZeroSisTradeRouteMissionPlan={Game.GetActivePlayer(),Game.GetGameTurn(),Game.GetElapsedGameTurns(),plan,2}
ZeroSisTradeRouteFixturePrepared=true
)lua";
        return source;
    }

    static int Integer(lua_State* state,int index,int minimum,int maximum){
        if(lua_type(state,index)!=LUA_TNUMBER)throw std::runtime_error("Trade-route evidence field is not numeric");
        const double value=lua_tonumber(state,index);
        if(!std::isfinite(value) || value<minimum || value>maximum || std::floor(value)!=value)
            throw std::runtime_error("Trade-route evidence field is outside its integer bounds");
        return static_cast<int>(value);
    }
    static std::string String(lua_State* state,int index){
        if(lua_type(state,index)!=LUA_TSTRING)throw std::runtime_error("Trade-route city name is not text");
        std::size_t size=0;const char* value=lua_tolstring(state,index,&size);
        if(!value || size==0 || size>256 || std::memchr(value,0,size))
            throw std::runtime_error("Trade-route city name is empty or outside its bound");
        return std::string(value,size);
    }
    static int IndexInteger(lua_State* state,int table,int index,int minimum,int maximum){
        lua_rawgeti(state,table,index);const int value=Integer(state,-1,minimum,maximum);lua_pop(state,1);return value;
    }
    static std::string IndexString(lua_State* state,int table,int index){
        lua_rawgeti(state,table,index);std::string value=String(state,-1);lua_pop(state,1);return value;
    }
    static void ReadRouteRows(lua_State* state,int table,std::vector<RouteRow>& rows){
        if(!lua_istable(state,table))throw std::runtime_error("SDK trade-route inventory row set is not a table");
        const std::size_t count=lua_objlen(state,table);
        if(count>1024)throw std::runtime_error("SDK trade-route inventory exceeded 1024 rows");
        for(std::size_t i=0;i<count;++i){
            lua_rawgeti(state,table,static_cast<int>(i+1));const int row=lua_gettop(state);
            if(!lua_istable(state,row) || lua_objlen(state,row)!=24)
                throw std::runtime_error("SDK trade-route inventory row schema is sparse or incomplete");
            RouteRow value;
            value.fromOwner=IndexInteger(state,row,1,0,MAX_PLAYERS-1);
            value.toOwner=IndexInteger(state,row,2,0,MAX_PLAYERS-1);
            value.fromCity=IndexInteger(state,row,3,0,INT_MAX);
            value.toCity=IndexInteger(state,row,4,0,INT_MAX);
            value.domain=IndexInteger(state,row,5,0,16);
            value.turnsLeft=IndexInteger(state,row,6,INT_MIN,INT_MAX);
            value.fromName=IndexString(state,row,7);value.toName=IndexString(state,row,8);
            if(IndexInteger(state,row,9,0,MAX_PLAYERS-1)!=value.fromOwner ||
               IndexInteger(state,row,10,0,MAX_PLAYERS-1)!=value.toOwner)
                throw std::runtime_error("SDK route owner IDs differ from the resolved city userdata owners");
            value.fromGPT=IndexInteger(state,row,11,INT_MIN,INT_MAX);
            value.toGPT=IndexInteger(state,row,12,INT_MIN,INT_MAX);
            value.toFood=IndexInteger(state,row,13,INT_MIN,INT_MAX);
            value.toProduction=IndexInteger(state,row,14,INT_MIN,INT_MAX);
            value.fromScience=IndexInteger(state,row,15,INT_MIN,INT_MAX);
            value.toScience=IndexInteger(state,row,16,INT_MIN,INT_MAX);
            value.toReligion=IndexInteger(state,row,17,INT_MIN,INT_MAX);
            value.toPressure=IndexInteger(state,row,18,INT_MIN,INT_MAX);
            value.fromReligion=IndexInteger(state,row,19,INT_MIN,INT_MAX);
            value.fromPressure=IndexInteger(state,row,20,INT_MIN,INT_MAX);
            value.fromTourism=IndexInteger(state,row,21,INT_MIN,INT_MAX);
            value.toTourism=IndexInteger(state,row,22,INT_MIN,INT_MAX);
            value.fromCivilization=IndexInteger(state,row,23,0,MAX_PLAYERS-1);
            value.toCivilization=IndexInteger(state,row,24,0,MAX_PLAYERS-1);
            rows.push_back(std::move(value));lua_pop(state,1);
        }
    }
    static int ReadInventory(lua_State* state){
        Inventory* out=static_cast<Inventory*>(lua_touserdata(state,1));
        lua_settop(state,0);lua_getglobal(state,"ZeroSisTradeRouteInventory");
        if(!lua_istable(state,-1) || lua_objlen(state,-1)!=6)
            return luaL_error(state,"SDK trade-route inventory schema differs");
        if(!out)return luaL_error(state,"SDK trade-route inventory destination is missing");
        const int root=lua_gettop(state);
        try{
            lua_rawgeti(state,root,1);out->activePlayer=Integer(state,-1,0,MAX_PLAYERS-1);lua_pop(state,1);
            lua_rawgeti(state,root,2);out->turn=Integer(state,-1,0,INT_MAX);lua_pop(state,1);
            lua_rawgeti(state,root,3);out->elapsed=Integer(state,-1,0,INT_MAX);lua_pop(state,1);
            lua_rawgeti(state,root,4);ReadRouteRows(state,-1,out->outbound);lua_pop(state,1);
            lua_rawgeti(state,root,5);ReadRouteRows(state,-1,out->inbound);lua_pop(state,1);
            lua_rawgeti(state,root,6);ReadRouteRows(state,-1,out->available);lua_pop(state,1);
            for(const auto& row:out->outbound)if(row.fromOwner!=out->activePlayer)
                throw std::runtime_error("GetTradeRoutes returned a row outside active-player origin scope");
            for(const auto& row:out->inbound)if(row.toOwner!=out->activePlayer || row.fromOwner==row.toOwner)
                throw std::runtime_error("GetTradeRoutesToYou returned a row outside inbound scope");
            for(const auto& row:out->available)if(row.fromOwner!=out->activePlayer)
                throw std::runtime_error("GetTradeRoutesAvailable returned a row outside active-player origin scope");
        }catch(const std::exception& error){return luaL_error(state,"%s",error.what());}
        return 0;
    }
    static int ReadPlan(lua_State* state){
        Plan* out=static_cast<Plan*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisTradeRouteMissionPlan");
        if(!out || !lua_istable(state,-1) || lua_objlen(state,-1)!=5)
            return luaL_error(state,"SDK trade-route mission plan schema differs");
        const int root=lua_gettop(state);
        try{
            lua_rawgeti(state,root,1);out->activePlayer=Integer(state,-1,0,MAX_PLAYERS-1);lua_pop(state,1);
            lua_rawgeti(state,root,2);out->turn=Integer(state,-1,0,INT_MAX);lua_pop(state,1);
            lua_rawgeti(state,root,3);out->elapsed=Integer(state,-1,0,INT_MAX);lua_pop(state,1);
            lua_rawgeti(state,root,4);
            if(!lua_istable(state,-1) || lua_objlen(state,-1)!=4)throw std::runtime_error("SDK trade-route plan must contain exactly four missions");
            const int rows=lua_gettop(state);
            for(int i=1;i<=4;++i){
                lua_rawgeti(state,rows,i);const int row=lua_gettop(state);
                if(!lua_istable(state,row) || lua_objlen(state,row)!=10)throw std::runtime_error("SDK trade-route plan row schema differs");
                int v[9]{};for(int field=1;field<=9;++field){lua_rawgeti(state,row,field);v[field-1]=Integer(state,-1,0,INT_MAX);lua_pop(state,1);}
                lua_rawgeti(state,row,10);if(lua_type(state,-1)!=LUA_TBOOLEAN)throw std::runtime_error("SDK trade-route plan direction is not boolean");
                const bool outbound=lua_toboolean(state,-1)!=0;lua_pop(state,1);
                out->missions.push_back({v[0],v[1],v[2],v[3],v[4],v[5],v[6],v[7],v[8],outbound});
                lua_pop(state,1);
            }
            lua_pop(state,1);
            lua_rawgeti(state,root,5);out->createdCities=Integer(state,-1,2,2);lua_pop(state,1);
        }catch(const std::exception& error){return luaL_error(state,"%s",error.what());}
        return 0;
    }

    static void AppendRows(std::ostringstream& output,const char* name,const std::vector<RouteRow>& rows){
        output<<",\""<<name<<"\":[";
        for(std::size_t i=0;i<rows.size();++i){
            const auto& row=rows[i];if(i)output<<',';
            output<<"{\"fromOwner\":"<<row.fromOwner<<",\"toOwner\":"<<row.toOwner
                  <<",\"fromCityId\":"<<row.fromCity<<",\"toCityId\":"<<row.toCity
                  <<",\"fromCityUserdataResolved\":true,\"toCityUserdataResolved\":true"
                  <<",\"fromCityWrapperType\":\"table\",\"fromCityNativeInstanceType\":\"userdata\""
                  <<",\"toCityWrapperType\":\"table\",\"toCityNativeInstanceType\":\"userdata\""
                  <<",\"domain\":"<<row.domain<<",\"turnsLeft\":"<<row.turnsLeft
                  <<",\"fromCityName\":"<<UiSnapshotJson::Quote(row.fromName)
                  <<",\"toCityName\":"<<UiSnapshotJson::Quote(row.toName)
                  <<",\"fromGPT\":"<<row.fromGPT<<",\"toGPT\":"<<row.toGPT
                  <<",\"toFood\":"<<row.toFood<<",\"toProduction\":"<<row.toProduction
                  <<",\"fromScience\":"<<row.fromScience<<",\"toScience\":"<<row.toScience
                  <<",\"toReligion\":"<<row.toReligion<<",\"toPressure\":"<<row.toPressure
                  <<",\"fromReligion\":"<<row.fromReligion<<",\"fromPressure\":"<<row.fromPressure
                  <<",\"fromTourism\":"<<row.fromTourism<<",\"toTourism\":"<<row.toTourism
                  <<",\"fromCivilizationType\":"<<row.fromCivilization
                  <<",\"toCivilizationType\":"<<row.toCivilization<<'}';
        }
        output<<']';
    }
    static void RequireOwner(const HostState& host,const ScriptSystem& scripts){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread() ||
           !scripts.IsQuiescent() || !host.localCommands.IsQuiescent())
            throw std::logic_error("Trade-route fixture requires a quiescent GameCore owner-thread scope");
    }
};

} // namespace ZeroSisHost
