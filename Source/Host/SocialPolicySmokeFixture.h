#pragma once
#include "HostServices.h"
#include "ScriptSystem.h"
#include <algorithm>
#include <cmath>
#include <climits>
#include <sstream>
#include <vector>

namespace ZeroSisHost {

// Disposable posted-input smoke only. The fixture grants culture, never a
// policy. Original SocialPolicyPopup callbacks and the SDK receiver must earn
// both adoptions. Restored games are observed without any fixture mutation.
class SocialPolicySmokeFixture final {
public:
    struct Policy final {int id=-1,branch=-1;bool has=false,canAdopt=false,blocked=false;int level=0;};
    struct Branch final {int id=-1,freePolicy=-1;bool unlocked=false,canUnlock=false,blocked=false;};
    struct Inventory final {
        int activePlayer=-1,turn=-1,elapsed=-1,culture=-1,nextCost=-1,freePolicies=-1;
        int freeTenets=-1,ideology=-1;
        bool policySaving=false;
        std::vector<Policy> policies;std::vector<Branch> branches;
    };
    static Inventory Prepare(HostState& host,ScriptSystem& scripts,lua_State* vm,bool fresh){
        RequireOwner(host,scripts,vm);
        if(fresh){
            static const char setup[]=R"lua(
assert(Game.GetActivePlayer()==0 and Game.GetGameTurn()==0 and Game.GetElapsedGameTurns()==0,
       'Culture fixture is fresh-game only')
local p=assert(Players[0])
assert(p:IsAlive() and p:IsHuman() and p:IsTurnActive() and p:GetNumCities()>0,
       'Culture fixture requires the active human with an actual SDK city')
assert(not ZeroSisSocialPolicyFixturePrepared,'Culture fixture already prepared')
assert(p:GetNumFreePolicies()==0,'Culture fixture cannot use free-policy awards')
local before=p:GetJONSCulture();local cost=p:GetNextPolicyCost()
assert(before>=0 and before<cost and cost>0 and cost<=500,
       'Culture fixture cost or previous culture exceeds its bounded scenario')
p:SetJONSCulture(cost)
assert(p:GetJONSCulture()==cost,'SDK did not apply exact branch-cost culture fixture')
ZeroSisSocialPolicyFixturePrepared=true
print('INTERACTIVE_SOCIAL_POLICY_CULTURE_FIXTURE=1|'..before..'|'..(cost-before)..'|'..cost..'|'..Game.GetGameTurn())
)lua";
            if(!scripts.Execute(vm,setup,sizeof(setup)-1,"social-policy-smoke-culture"))
                throw std::runtime_error(scripts.LastError());
        }
        const auto result=Capture(host,scripts,vm);
        if(result.activePlayer!=0 || result.freePolicies!=0 || result.policySaving || result.nextCost<=0)
            throw std::runtime_error("Policy fixture requires the original non-saving paid-policy scenario");
        if(fresh && (result.culture!=result.nextCost ||
           std::none_of(result.branches.begin(),result.branches.end(),[](const Branch& b){return !b.unlocked && b.canUnlock && !b.blocked && b.freePolicy>=0;}))
           )
            throw std::runtime_error("Culture fixture has no actual legal paid SDK branch choice");
        if(!fresh && (std::count_if(result.policies.begin(),result.policies.end(),[](const Policy& p){return p.has;})<2 ||
            std::none_of(result.branches.begin(),result.branches.end(),[](const Branch& b){return b.unlocked;}) ||
            result.culture>=result.nextCost))
            throw std::runtime_error("Restored policy fixture lacks its saved adoptions or has another mandatory policy choice");
        std::printf("INTERACTIVE_SOCIAL_POLICY_FIXTURE=%s|%d|%d|%d|%d|%d\n",fresh?"FRESH":"RESTORED",
            result.activePlayer,result.turn,result.elapsed,result.culture,result.nextCost);
        return result;
    }
    static Inventory FundSecondChoice(HostState& host,ScriptSystem& scripts,lua_State* vm){
        RequireOwner(host,scripts,vm);
        static const char source[]=R"lua(
assert(ZeroSisSocialPolicyFixturePrepared and not ZeroSisSocialPolicySecondChoiceFunded and
       Game.GetGameTurn()==0 and Game.GetElapsedGameTurns()==0,'Second policy culture grant is fresh-game only')
local p=assert(Players[Game.GetActivePlayer()]);local cost=p:GetNextPolicyCost()
assert(p:IsHuman() and p:IsTurnActive() and p:GetNumFreePolicies()==0 and
       p:GetJONSCulture()==0 and p:GetNumPolicies()==1 and cost>0 and cost<=500,
       'Second culture fixture requires exactly the purchased branch opener')
p:SetJONSCulture(cost)
assert(p:GetJONSCulture()==cost,'SDK did not apply exact policy-cost culture fixture')
ZeroSisSocialPolicySecondChoiceFunded=true
print('INTERACTIVE_SOCIAL_POLICY_CULTURE_FIXTURE=2|0|'..cost..'|'..cost..'|'..Game.GetGameTurn())
)lua";
        if(!scripts.Execute(vm,source,sizeof(source)-1,"social-policy-smoke-second-culture"))
            throw std::runtime_error(scripts.LastError());
        return Capture(host,scripts,vm);
    }
    static Inventory Capture(HostState& host,ScriptSystem& scripts,lua_State* vm){
        RequireOwner(host,scripts,vm);
        static const char source[]=R"lua(
local p=assert(Players[Game.GetActivePlayer()])
local policies,branches={},{}
for row in GameInfo.Policies() do
  local branch=-1
  if row.PolicyBranchType then branch=assert(GameInfo.PolicyBranchTypes[row.PolicyBranchType]).ID end
  policies[#policies+1]={row.ID,branch,p:HasPolicy(row.ID),p:CanAdoptPolicy(row.ID),p:IsPolicyBlocked(row.ID),row.Level or 0}
end
for row in GameInfo.PolicyBranchTypes() do
  local opener=-1
  if row.FreePolicy then opener=assert(GameInfo.Policies[row.FreePolicy]).ID end
  branches[#branches+1]={row.ID,opener,p:IsPolicyBranchUnlocked(row.ID),p:CanUnlockPolicyBranch(row.ID),p:IsPolicyBranchBlocked(row.ID)}
end
table.sort(policies,function(a,b)return a[1]<b[1]end)
table.sort(branches,function(a,b)return a[1]<b[1]end)
ZeroSisSocialPolicyInventory={Game.GetActivePlayer(),Game.GetGameTurn(),Game.GetElapsedGameTurns(),
 p:GetJONSCulture(),p:GetNextPolicyCost(),p:GetNumFreePolicies(),policies,branches,
 Game.IsOption(GameOptionTypes.GAMEOPTION_POLICY_SAVING),p:GetNumFreeTenets(),p:GetLateGamePolicyTree()}
)lua";
        Inventory result;
        if(!scripts.Execute(vm,source,sizeof(source)-1,"social-policy-sdk-inventory") || !scripts.CallCFunction(vm,&Read,&result))
            throw std::runtime_error(scripts.LastError());
        return result;
    }
    static std::string Serialize(const Inventory& v){
        std::ostringstream out;
        out<<"{\"schema\":\"ZEROSIS_SOCIAL_POLICY_SDK_INVENTORY_V1\",\"source\":\"SDK:Policies/PolicyBranches/JONSCulture\""
           <<",\"activePlayer\":"<<v.activePlayer<<",\"turn\":"<<v.turn<<",\"elapsed\":"<<v.elapsed
           <<",\"culture\":"<<v.culture<<",\"nextCost\":"<<v.nextCost<<",\"freePolicies\":"<<v.freePolicies
           <<",\"freeTenets\":"<<v.freeTenets<<",\"ideology\":"<<v.ideology
           <<",\"policySaving\":"<<(v.policySaving?"true":"false")<<",\"policies\":[";
        bool first=true;for(const auto& p:v.policies){if(!first)out<<',';first=false;
            out<<"{\"id\":"<<p.id<<",\"branch\":"<<p.branch<<",\"has\":"<<(p.has?"true":"false")
               <<",\"canAdopt\":"<<(p.canAdopt?"true":"false")<<",\"blocked\":"<<(p.blocked?"true":"false")<<",\"level\":"<<p.level<<'}';}
        out<<"],\"branches\":[";first=true;for(const auto& b:v.branches){if(!first)out<<',';first=false;
            out<<"{\"id\":"<<b.id<<",\"freePolicy\":"<<b.freePolicy<<",\"unlocked\":"<<(b.unlocked?"true":"false")
               <<",\"canUnlock\":"<<(b.canUnlock?"true":"false")<<",\"blocked\":"<<(b.blocked?"true":"false")<<'}';}
        out<<"]}\n";return out.str();
    }
    static void RequireAdoption(const Inventory& before,const Inventory& after,int id,bool isPolicy){
        if(before.activePlayer!=after.activePlayer || before.turn!=after.turn || before.elapsed!=after.elapsed ||
           before.freePolicies!=0 || after.freePolicies!=0 || before.policySaving || after.policySaving || before.nextCost<=0 ||
           after.culture!=before.culture-before.nextCost || before.policies.size()!=after.policies.size() ||
           before.branches.size()!=after.branches.size())
            throw std::runtime_error("Original policy callback did not charge exactly its SDK culture cost");
        int expectedPolicy=id;
        if(!isPolicy){
            const auto branch=std::find_if(before.branches.begin(),before.branches.end(),[&](const Branch& b){return b.id==id;});
            if(branch==before.branches.end() || branch->unlocked || !branch->canUnlock || branch->blocked || branch->freePolicy<0)
                throw std::runtime_error("Original branch callback selected an unavailable SDK branch");
            expectedPolicy=branch->freePolicy;
        }
        unsigned policiesChanged=0,branchesChanged=0;
        for(std::size_t i=0;i<before.policies.size();++i){
            const auto& a=before.policies[i];const auto& b=after.policies[i];
            if(a.id!=b.id || a.branch!=b.branch || a.blocked!=b.blocked)
                throw std::runtime_error("Policy adoption changed unrelated policy identity or blocking");
            if(a.has!=b.has){
                if(a.id!=expectedPolicy || a.has || !b.has || (isPolicy && !a.canAdopt))
                    throw std::runtime_error("Original policy callback did not adopt exactly its selected SDK policy");
                ++policiesChanged;
            }
        }
        for(std::size_t i=0;i<before.branches.size();++i){
            const auto& a=before.branches[i];const auto& b=after.branches[i];
            if(a.id!=b.id || a.freePolicy!=b.freePolicy || a.blocked!=b.blocked)
                throw std::runtime_error("Policy adoption changed unrelated branch identity or blocking");
            if(a.unlocked!=b.unlocked){
                if(isPolicy || a.id!=id || a.unlocked || !b.unlocked)
                    throw std::runtime_error("Original policy callback changed another branch");
                ++branchesChanged;
            }
        }
        if(policiesChanged!=1 || branchesChanged!=(isPolicy?0u:1u))
            throw std::runtime_error("Original policy callback has an incomplete SDK adoption result");
    }
    // Prepare only prerequisites for the original tenet UI in a disposable
    // fresh smoke. Selecting an ideology through its normal era/selector UI is
    // a separate gate. No tenet is granted here, and restore is mutation-free.
    static Inventory PrepareTenets(HostState& host,ScriptSystem& scripts,lua_State* vm,bool fresh){
        RequireOwner(host,scripts,vm);
        if(fresh){
            static const char setup[]=R"lua(
assert(Game.GetActivePlayer()==0 and Game.GetGameTurn()==0 and Game.GetElapsedGameTurns()==0,
       'Tenet prerequisites are fresh-smoke only')
local p=assert(Players[0]);local b=assert(GameInfo.PolicyBranchTypes.POLICY_BRANCH_FREEDOM)
assert(not ZeroSisTenetFixturePrepared and p:IsAlive() and p:IsHuman() and p:IsTurnActive() and p:GetNumCities()>0,
       'Tenet prerequisites require the untouched active human city scenario')
assert(p:GetNumPolicies()==0 and p:GetNumFreePolicies()==0 and p:GetNumFreeTenets()==0 and
       p:GetLateGamePolicyTree()==-1 and p:GetJONSCulture()==0 and b.PurchaseByLevel,
       'Tenet prerequisite fixture would overwrite existing progression')
p:SetPolicyBranchUnlocked(b.ID,true,false)
assert(p:GetLateGamePolicyTree()==b.ID and p:GetNumFreeTenets()==2 and p:GetNumPolicies()==0 and
       p:GetNumFreePolicies()==0 and p:GetJONSCulture()==0,
       'SDK ideology prerequisite did not award its original two first-adopter choices')
ZeroSisTenetFixturePrepared=true
)lua";
            if(!scripts.Execute(vm,setup,sizeof(setup)-1,"social-policy-tenet-prerequisites"))
                throw std::runtime_error(scripts.LastError());
        }
        const auto result=Capture(host,scripts,vm);
        const auto owned=std::count_if(result.policies.begin(),result.policies.end(),[&](const Policy& p){
            return p.has && p.branch==result.ideology && p.level==1;
        });
        if(result.activePlayer!=0 || result.policySaving || result.freePolicies!=0 || result.ideology<0 ||
           (fresh?(result.freeTenets!=2 || owned!=0 || result.culture!=0):
                  (result.freeTenets!=0 || owned!=3 || result.culture>=result.nextCost)))
            throw std::runtime_error("Tenet fixture differs from its actual free/paid SDK scenario");
        std::printf("INTERACTIVE_SOCIAL_POLICY_TENET_FIXTURE=%s|%d|%d|%d|%d|%d\n",fresh?"FRESH":"RESTORED",
            result.activePlayer,result.turn,result.elapsed,result.ideology,result.freeTenets);
        return result;
    }
    static Inventory FundPaidTenet(HostState& host,ScriptSystem& scripts,lua_State* vm){
        RequireOwner(host,scripts,vm);
        static const char source[]=R"lua(
assert(ZeroSisTenetFixturePrepared and not ZeroSisPaidTenetFunded and Game.GetGameTurn()==0,
       'Paid tenet culture is a one-time fresh fixture')
local p=assert(Players[Game.GetActivePlayer()]);local cost=p:GetNextPolicyCost()
assert(p:GetNumFreePolicies()==0 and p:GetNumFreeTenets()==0 and p:GetJONSCulture()==0 and
       p:GetNumPolicies()==2 and cost>0 and cost<=500,'Paid tenet fixture lacks its two actual free adoptions')
p:SetJONSCulture(cost);assert(p:GetJONSCulture()==cost,'Exact tenet cost was not applied')
ZeroSisPaidTenetFunded=true
print('INTERACTIVE_SOCIAL_POLICY_TENET_CULTURE=0|'..cost..'|'..cost..'|'..Game.GetGameTurn())
)lua";
        if(!scripts.Execute(vm,source,sizeof(source)-1,"social-policy-paid-tenet-culture"))
            throw std::runtime_error(scripts.LastError());
        return Capture(host,scripts,vm);
    }
    static void RequireTenetAdoption(const Inventory& before,const Inventory& after,int selected){
        const bool free=before.freeTenets>0;
        if(before.activePlayer!=after.activePlayer || before.turn!=after.turn || before.elapsed!=after.elapsed ||
           before.ideology<0 || before.ideology!=after.ideology || before.freePolicies!=0 || after.freePolicies!=0 ||
           before.policySaving || after.policySaving || before.nextCost<=0 ||
           after.freeTenets!=before.freeTenets-(free?1:0) ||
           after.culture!=before.culture-(free?0:before.nextCost) ||
           before.policies.size()!=after.policies.size() || before.branches.size()!=after.branches.size())
            throw std::runtime_error("Original tenet adoption lost its SDK free-choice/culture cost contract");
        unsigned added=0;
        for(std::size_t i=0;i<before.policies.size();++i){
            const auto& a=before.policies[i];const auto& b=after.policies[i];
            if(a.id!=b.id || a.branch!=b.branch || a.level!=b.level || a.blocked!=b.blocked)
                throw std::runtime_error("Tenet adoption changed another policy identity or blocking");
            if(a.has!=b.has){
                if(a.id!=selected || a.has || !b.has || !a.canAdopt || a.blocked ||
                   a.branch!=before.ideology || a.level!=1)
                    throw std::runtime_error("Original selected level-one tenet was not exclusively adopted");
                ++added;
            }
        }
        for(std::size_t i=0;i<before.branches.size();++i){
            const auto& a=before.branches[i];const auto& b=after.branches[i];
            if(a.id!=b.id || a.freePolicy!=b.freePolicy || a.unlocked!=b.unlocked || a.blocked!=b.blocked)
                throw std::runtime_error("Tenet adoption changed unrelated SDK branches");
        }
        if(added!=1)throw std::runtime_error("Tenet confirmation did not add exactly one original policy");
    }
private:
    static void RequireOwner(HostState& host,ScriptSystem& scripts,lua_State* vm){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread() ||
           !host.localCommands.IsQuiescent() || !vm || !scripts.GameLibrariesBound())
            throw std::logic_error("Policy fixture needs its quiescent SDK Lua owner");
    }
    static int Integer(lua_State* state,int table,int field,int minimum=0){
        lua_rawgeti(state,table,field);const double v=lua_tonumber(state,-1);
        if(lua_type(state,-1)!=LUA_TNUMBER || !std::isfinite(v) || std::floor(v)!=v || v<minimum || v>INT_MAX)
            luaL_error(state,"Policy inventory integer is invalid");
        lua_pop(state,1);return static_cast<int>(v);
    }
    static bool Boolean(lua_State* state,int table,int field){
        lua_rawgeti(state,table,field);if(lua_type(state,-1)!=LUA_TBOOLEAN)luaL_error(state,"Policy inventory boolean is invalid");
        const bool result=lua_toboolean(state,-1)!=0;lua_pop(state,1);return result;
    }
    static int Read(lua_State* state){
        auto* result=static_cast<Inventory*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisSocialPolicyInventory");
        if(!result || !lua_istable(state,1) || lua_objlen(state,1)!=11)return luaL_error(state,"Policy inventory is invalid");
        result->activePlayer=Integer(state,1,1);result->turn=Integer(state,1,2);result->elapsed=Integer(state,1,3);
        result->culture=Integer(state,1,4);result->nextCost=Integer(state,1,5);result->freePolicies=Integer(state,1,6);
        result->policySaving=Boolean(state,1,9);
        result->freeTenets=Integer(state,1,10);result->ideology=Integer(state,1,11,-1);
        for(int field=7;field<=8;++field){
            lua_rawgeti(state,1,field);const int array=lua_gettop(state);const auto count=lua_objlen(state,array);
            if(!lua_istable(state,array) || !count || count>2048)return luaL_error(state,"Policy inventory rows exceed bounds");
            int previous=-1;
            for(std::size_t i=0;i<count;++i){
                lua_rawgeti(state,array,static_cast<int>(i+1));const int row=lua_gettop(state);
                if(!lua_istable(state,row) || lua_objlen(state,row)!=(field==7?6u:5u))return luaL_error(state,"Policy inventory row is invalid");
                const int id=Integer(state,row,1),other=Integer(state,row,2,-1);
                if(id<=previous)return luaL_error(state,"Policy inventory IDs are not sorted and unique");previous=id;
                const bool a=Boolean(state,row,3),b=Boolean(state,row,4),c=Boolean(state,row,5);
                if(field==7){const int level=Integer(state,row,6);if(level>3)return luaL_error(state,"Policy tenet level exceeds the original rules");
                    result->policies.push_back({id,other,a,b,c,level});}
                else result->branches.push_back({id,other,a,b,c});
                lua_pop(state,1);
            }
            lua_pop(state,1);
        }
        return 0;
    }
};
}
