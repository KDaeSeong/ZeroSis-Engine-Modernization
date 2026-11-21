#pragma once
#include "UiPopupContext.h"
#include "SdkStateSnapshot.h"
#include <algorithm>
#include <sstream>

namespace ZeroSisHost {
// An opt-in input scenario, not a world-state seeder. Every mutation is the
// stock ProductionPopup callback delivered through the existing SDK adapter.
class EconomicOverviewSmokeFixture final {
public:
    struct Action final {std::uint64_t key=0;unsigned virtualKey=0;};
    bool Started() const {return started_;}
    bool Complete() const {return stage_==20;}
    int SelectedUnit() const {if(!Complete())throw std::logic_error("Economic smoke is incomplete");return selectedUnit_;}

    template<class Live>
    Action Advance(HostState& host,ICvGameContext3& core,Live& live,const std::wstring& directory,
                   bool restored,int city,bool uiActive,bool topActive,UiPopupKind kind,
                   const std::vector<UiInputTarget>& top,const std::vector<UiInputTarget>& targets,
                   const std::vector<std::uint64_t>& published,std::uint64_t generation,unsigned revision){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread() ||
           !host.scripts || !host.scripts->IsQuiescent() || !host.localCommands.IsQuiescent())
            throw std::logic_error("Economic smoke requires its quiescent SDK owner lock");
        if(stage_<1 || stage_>19)throw std::logic_error("Economic smoke advanced outside stages 1..19");
        std::unique_ptr<ICvGame1> game(core.GetGame());
        if(!game)throw std::runtime_error("Economic smoke has no SDK game");
        const auto state=SdkStateSnapshot::Capture(host);
        if(!started_){
            if(uiActive || !topActive || !live.CanChooseProduction(city))
                throw std::runtime_error("Economic smoke needs the completed ordinary decision city and TopPanel");
            city_=city;owner_=game->GetActivePlayer();turn_=game->GetGameTurn();before_=state;started_=true;
            SdkStateSnapshot::Write(directory+L"\\economic-before-state.txt",before_);
            std::printf("INTERACTIVE_ECONOMIC_FIXTURE=%s|%d|%d|%d|NO_SDK_SETUP\n",restored?"RESTORED":"FRESH",owner_,turn_,city_);
        }
        if(game->GetActivePlayer()!=owner_ || game->GetGameTurn()!=turn_ || city!=city_)
            throw std::runtime_error("Economic smoke changed owner, turn or source city before completion");
        if(stage_<=13 && state!=before_)
            throw std::runtime_error("Economic browsing or production cancellation changed sampled SDK state");
        if(stage_>14 && state!=after_)
            throw std::runtime_error("Economic return/reopen changed sampled SDK state after its production choice");
        const auto exists=[&](std::uint64_t key){return std::find(published.begin(),published.end(),key)!=published.end();};
        const auto find=[&](const std::vector<UiInputTarget>& rows,const char* id,int payload,bool matchPayload){
            std::uint64_t key=0;
            for(const auto& row:rows)if(row.id==id && (!matchPayload || (row.hasVoid1 && row.void1==payload)) && exists(row.key)){
                if(!row.key || key)throw std::runtime_error(std::string("Economic smoke has duplicate visible callback: ")+id);
                key=row.key;
            }
            if(!key)throw std::runtime_error(std::string("Economic smoke lacks published original callback: ")+id);
            return key;
        };
        const auto tab=[&](unsigned slot){
            if(!uiActive || kind!=UiPopupKind::EconomicOverview)
                throw std::runtime_error("Economic smoke lost its original parent context");
            bool present=false;
            for(const auto& row:targets){
                const auto child=row.key>>48;
                if(child==slot)present=true;
                else if(child==1 || child==2)throw std::runtime_error("Hidden economic child leaked callback targets");
            }
            if(!present)throw std::runtime_error("Economic smoke has no callbacks from its expected visible child");
        };
        const auto saveUi=[&](const wchar_t* name){
            SdkStateSnapshot::Write(directory+L"\\economic-"+name+L"-ui.json",live.CaptureUi().snapshot);
        };
        Action action;const char* id=nullptr;int payload=-1;
        switch(stage_){
        case 1:case 16:
            if(uiActive || !topActive)throw std::runtime_error("Economic entry did not return to the original TopPanel");
            id="GoldPerTurn";action.key=find(top,id,-1,false);break;
        case 2:case 3:
            tab(1);id="SortPopulation";payload=0;action.key=find(targets,id,payload,true);break;
        case 4:case 5:
            tab(1);id="CityToggle";action.key=find(targets,id,-1,false);break;
        case 6:case 14:case 17:
            if(stage_!=17)tab(1);
            else if(!uiActive || kind!=UiPopupKind::EconomicOverview)throw std::runtime_error("Economic reopen lost its parent");
            if(stage_==14){
                if(live.ProductionUnit(city_)!=selectedUnit_ || selectedUnit_==oldUnit_)
                    throw std::runtime_error("Economic selection did not apply the different SDK training order");
                returnedRow_=find(targets,"ProdButton",city_,true);
                if(returnedRow_==choiceRow_)throw std::runtime_error("Economic production return did not rebuild its original city row");
                RequireProductionDelta(before_,state,owner_,city_,selectedUnit_);after_=state;
                saveUi(L"selected-returned");SdkStateSnapshot::Write(directory+L"\\economic-after-state.txt",after_);
                const int queued=live.CityInteger(city_,"GetOrderQueueLength()");
                if(queued!=1)throw std::runtime_error("Economic production selection did not replace its exact original queue");
                std::ostringstream out;out<<"{\"schema\":\"ZEROSIS_ECONOMIC_SELECTION_V1\",\"owner\":"<<owner_
                    <<",\"turn\":"<<turn_<<",\"city\":"<<city_<<",\"oldUnit\":"<<oldUnit_<<",\"selectedUnit\":"<<selectedUnit_
                    <<",\"beforeRow\":"<<choiceRow_<<",\"returnedRow\":"<<returnedRow_<<",\"queueLength\":"<<queued<<"}\n";
                SdkStateSnapshot::Write(directory+L"\\economic-selection.json",out.str());
                std::printf("INTERACTIVE_ECONOMIC_PRODUCTION_VERIFIED=%d|%d|%d|%llu|%llu|1\n",city_,oldUnit_,selectedUnit_,
                    static_cast<unsigned long long>(choiceRow_),static_cast<unsigned long long>(returnedRow_));
            }
            id="HappinessButton";action.key=find(targets,id,-1,false);break;
        case 7:case 8:
            tab(2);id="CityUnhappinessToggle";action.key=find(targets,id,-1,false);break;
        case 9:
            tab(2);id="GeneralInfoButton";action.key=find(targets,id,-1,false);break;
        case 10:case 12:
            tab(1);id="ProdButton";payload=city_;action.key=find(targets,id,payload,true);
            if(stage_==10){cancelRow_=action.key;saveUi(L"cancel-before");}
            else{
                if(action.key==cancelRow_)throw std::runtime_error("Economic cancellation did not refresh its retained General city row");
                choiceRow_=action.key;oldUnit_=live.ProductionUnit(city_);saveUi(L"cancel-returned");
                SdkStateSnapshot::Write(directory+L"\\economic-cancel-returned-state.txt",state);
            }
            break;
        case 11:
            if(!uiActive || kind!=UiPopupKind::Production)throw std::runtime_error("Economic cancellation did not open original ProductionPopup");
            id="CloseButton";action.key=find(targets,id,-1,false);break;
        case 13:
            if(!uiActive || kind!=UiPopupKind::Production)throw std::runtime_error("Economic selection did not reopen original ProductionPopup");
            for(const auto& row:targets)if(row.id=="Button" && row.hasVoid1 && row.hasVoid2 && row.void1==6 &&
                row.void2>=0 && row.void2!=oldUnit_ && exists(row.key) && live.CanTrain(city_,row.void2) &&
                (selectedUnit_<0 || row.void2<selectedUnit_)){
                selectedUnit_=row.void2;action.key=row.key;
            }
            if(!action.key || selectedUnit_<0)throw std::runtime_error("Economic ProductionPopup has no different legal published training item");
            id="Button";payload=selectedUnit_;saveUi(L"choice");break;
        case 15:
            tab(2);id="CloseButton";action.key=find(targets,id,-1,false);break;
        case 18:
            tab(2);id="KEY_ESCAPE";action.virtualKey=27;break;
        case 19:
            if(uiActive || !topActive)throw std::runtime_error("Economic Escape did not restore TopPanel world input");
            SdkStateSnapshot::Write(directory+L"\\economic-returned-state.txt",state);
            std::printf("INTERACTIVE_ECONOMIC_COMPLETE=%llu|%u|%d|%d|CANCEL_AND_DIFFERENT_PRODUCTION\n",
                static_cast<unsigned long long>(generation),revision,turn_,selectedUnit_);++stage_;return action;
        default:throw std::logic_error("Unhandled bounded economic smoke stage");
        }
        if(generation<=lastGeneration_ || revision<=lastRevision_)
            throw std::runtime_error("Economic smoke reused a published scene generation/revision");
        std::printf("INTERACTIVE_ECONOMIC_ACTION=%u|%s|%llu|%llu|%u|%d\n",stage_,id,
            static_cast<unsigned long long>(action.virtualKey?action.virtualKey:action.key),
            static_cast<unsigned long long>(generation),revision,payload);
        lastGeneration_=generation;lastRevision_=revision;++stage_;return action;
    }
private:
    static void RequireProductionDelta(const std::string& before,const std::string& after,int owner,int city,int unit){
        std::istringstream a(before),b(after);std::string x,y;unsigned changed=0;
        const auto fields=[](const std::string& line){std::vector<std::string> out;std::istringstream input(line);std::string value;
            while(std::getline(input,value,'|'))out.push_back(value);return out;};
        while(std::getline(a,x)){
            if(!std::getline(b,y))throw std::runtime_error("Economic production removed an SDK state row");
            if(x==y)continue;
            auto old=fields(x),now=fields(y);
            if(old.size()!=12 || now.size()!=12 || old[0]!="C" || now[0]!="C" ||
               old[1]!=std::to_string(owner) || old[2]!=std::to_string(city) || now[8]!=std::to_string(unit) || now[9]!="-1")
                throw std::runtime_error("Economic production changed an unrelated sampled SDK row");
            for(std::size_t i=0;i<old.size();++i)if(i!=7 && i!=8 && i!=9 && old[i]!=now[i])
                throw std::runtime_error("Economic production changed non-production city state");
            ++changed;
        }
        if(std::getline(b,y) || changed!=1)throw std::runtime_error("Economic production did not change exactly its sampled city production row");
    }
    unsigned stage_=1,lastRevision_=0;std::uint64_t lastGeneration_=0,cancelRow_=0,choiceRow_=0,returnedRow_=0;
    bool started_=false;int owner_=-1,turn_=-1,city_=-1,oldUnit_=-1,selectedUnit_=-1;
    std::string before_,after_;
};
}
