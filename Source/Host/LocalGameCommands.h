#pragma once
#include "SdkHostIncludes.h"
#include <functional>
#include <limits>
#include <memory>
#include <stdexcept>
#include <utility>
#include <vector>

namespace ZeroSisHost {
// Single-player transport: retain bundle order and deliver to the real SDK
// message handler. Binding is scoped to an owner-thread, locked SDK operation.
// Callbacks may call Unbind to cancel the remaining batch. Other operations
// from a callback are rejected, and an in-flight callback remains alive until
// it returns.
class LocalGameCommands final {
public:
    using PlayerOptionHandler=std::function<void(PlayerOptionTypes,bool)>;
    using PlayerOptionLookup=std::function<bool(PlayerOptionTypes)>;
    using UnitCommandHandler=std::function<void(int,CommandTypes,int,int,bool)>;
    using PushMissionHandler=std::function<void(int,MissionTypes,int,int,int,bool)>;
    using PushOrderHandler=std::function<void(int,OrderTypes,int,bool,bool,bool)>;
    using ResearchHandler=std::function<void(TechTypes,int,PlayerTypes,bool)>;
    using CityPurchaseHandler=std::function<void(int,UnitTypes,BuildingTypes,ProjectTypes,int)>;
    using CityTaskHandler=std::function<void(int,TaskTypes,int,int,bool,bool,bool,bool)>;
    using LiberatePlayerHandler=std::function<void(PlayerTypes,int)>;
    using ChangeWarHandler=std::function<void(TeamTypes,bool)>;
    using FromUIDiploEventHandler=std::function<void(PlayerTypes,FromUIDiploEventTypes,int,int)>;
    using FoundPantheonHandler=std::function<void(PlayerTypes,BeliefTypes)>;

    static void RequireOwnerLock(bool ownerThread,bool lockHeld){
        if(!ownerThread || !lockHeld)throw std::logic_error("Local city commands require the GameCore owner lock");
    }
    static void ValidateCityOrderEnvelope(int cityID,OrderTypes order,int data,bool alt,bool shift,bool control){
        if(cityID<0 || data<0)throw std::invalid_argument("Local city order has a negative city or item ID");
        if(alt || !control || (order!=ORDER_TRAIN && order!=ORDER_CONSTRUCT && order!=ORDER_CREATE && order!=ORDER_MAINTAIN))
            throw std::invalid_argument("Local city order has an unsupported order or modifier tuple");
        (void)shift; // Both official ProductionPopup append and replace tuples are valid.
    }
    static void ValidateCityPurchaseEnvelope(int cityID,UnitTypes unit,BuildingTypes building,ProjectTypes project,int purchaseYield){
        if(cityID<0)throw std::invalid_argument("Local city purchase has a negative city ID");
        const bool hasUnit=unit!=NO_UNIT,hasBuilding=building!=NO_BUILDING,hasProject=project!=NO_PROJECT;
        if(static_cast<int>(hasUnit)+static_cast<int>(hasBuilding)+static_cast<int>(hasProject)!=1)
            throw std::invalid_argument("Local city purchase must name exactly one unit, building, or project");
        if((hasUnit && static_cast<int>(unit)<0) || (hasBuilding && static_cast<int>(building)<0) || (hasProject && static_cast<int>(project)<0))
            throw std::invalid_argument("Local city purchase has a negative item ID");
        if(purchaseYield!=YIELD_GOLD && purchaseYield!=YIELD_FAITH)
            throw std::invalid_argument("Local ProductionPopup purchase supports gold or faith only");
    }

    void Bind(PlayerOptionHandler handler,PlayerOptionLookup lookup,UnitCommandHandler unitHandler={},PushMissionHandler missionHandler={},PushOrderHandler orderHandler={},ResearchHandler researchHandler={},CityPurchaseHandler purchaseHandler={},CityTaskHandler cityTaskHandler={},LiberatePlayerHandler liberatePlayerHandler={},PushMissionHandler swapHandler={},ChangeWarHandler changeWarHandler={},FromUIDiploEventHandler diploEventHandler={},FoundPantheonHandler foundPantheonHandler={}){
        if(!handler || !lookup)throw std::invalid_argument("Local command transport requires an SDK receiver and option source");
        if(dispatching_ || binding_ || depth_ || !pending_.empty())
            throw std::logic_error("Local command transport is already active");
        binding_=std::make_shared<Callbacks>(std::move(handler),std::move(lookup),std::move(unitHandler),std::move(missionHandler),std::move(orderHandler),std::move(researchHandler),std::move(purchaseHandler),std::move(cityTaskHandler),std::move(liberatePlayerHandler),std::move(swapHandler),std::move(changeWarHandler),std::move(diploEventHandler),std::move(foundPantheonHandler));
    }

    // Unbind is idempotent. During a callback it detaches the binding at once,
    // clears queued work, and asks the active batch to stop after that callback.
    // The active callback storage is retained by its invocation until return.
    void Unbind() noexcept {
        binding_.reset();
        pending_.clear();
        depth_=0;
        if(dispatching_)dispatchCancelled_=true;
    }

    bool GetPlayerOption(PlayerOptionTypes option) const {
        const auto callbacks=RequireReceiver();
        DispatchScope scope(*this);
        return callbacks->lookup(option);
    }

    void Begin(){
        RequireReceiver();
        if(depth_==std::numeric_limits<unsigned>::max())
            throw std::overflow_error("Local message bundle nesting overflow");
        ++depth_;
    }

    void SendPlayerOption(PlayerOptionTypes option,bool value){
        const auto callbacks=RequireReceiver();
        // SDK options are 32-bit hashes, not sequential array indices. Values
        // with the high bit set are valid enum values and must remain intact.
        const Command command={Command::Kind::PlayerOption,option,value,0,NO_COMMAND,0,0,false,NO_MISSION,0,false};
        if(depth_)pending_.push_back(command);
        else Deliver(callbacks,std::vector<Command>{command});
    }

    void SendUnitCommand(int unitID,CommandTypes command,int data1,int data2,bool alt=false){
        const auto callbacks=RequireReceiver();
        if(!callbacks->unitHandler)
            throw std::logic_error("Local unit commands require a bound SDK receiver");
        const Command queued={Command::Kind::UnitCommand,static_cast<PlayerOptionTypes>(0),false,unitID,command,data1,data2,alt,NO_MISSION,0,false};
        if(depth_)pending_.push_back(queued);
        else Deliver(callbacks,std::vector<Command>{queued});
    }

    void SendPushMission(int unitID,MissionTypes mission,int data1,int data2,int flags,bool shift){
        const auto callbacks=RequireReceiver();
        if(!callbacks->missionHandler)
            throw std::logic_error("Local push missions require a bound SDK receiver");
        Command queued={Command::Kind::PushMission,static_cast<PlayerOptionTypes>(0),false,unitID,NO_COMMAND,data1,data2,false,mission,flags,shift};
        if(depth_)pending_.push_back(queued);
        else Deliver(callbacks,std::vector<Command>{queued});
    }

    void SendSwapUnits(int unitID,MissionTypes mission,int data1,int data2,int flags,bool shift){
        const auto callbacks=RequireReceiver();
        if(!callbacks->swapHandler)throw std::logic_error("Local unit swaps require a bound SDK receiver");
        Command queued={Command::Kind::SwapUnits,static_cast<PlayerOptionTypes>(0),false,unitID,NO_COMMAND,data1,data2,false,mission,flags,shift};
        if(depth_)pending_.push_back(queued);else Deliver(callbacks,std::vector<Command>{queued});
    }

    void SendPushOrder(int cityID,OrderTypes order,int data,bool alt,bool shift,bool control){
        const auto callbacks=RequireReceiver();if(!callbacks->orderHandler)throw std::logic_error("Local city orders require a bound SDK receiver");
        Command queued{};queued.kind=Command::Kind::PushOrder;queued.unitID=cityID;queued.order=order;queued.data1=data;queued.alt=alt;queued.shift=shift;queued.control=control;
        if(depth_)pending_.push_back(queued);else Deliver(callbacks,std::vector<Command>{queued});
    }
    void SendResearch(TechTypes tech,int discover,PlayerTypes stealFrom,bool shift){
        const auto callbacks=RequireReceiver();if(!callbacks->researchHandler)throw std::logic_error("Local research requires a bound SDK receiver");
        Command queued{};queued.kind=Command::Kind::Research;queued.tech=tech;queued.data1=discover;queued.stealFrom=stealFrom;queued.shift=shift;
        if(depth_)pending_.push_back(queued);else Deliver(callbacks,std::vector<Command>{queued});
    }
    void SendCityPurchase(int cityID,UnitTypes unit,BuildingTypes building,ProjectTypes project,int yield){
        const auto callbacks=RequireReceiver();if(!callbacks->purchaseHandler)throw std::logic_error("Local city purchases require a bound SDK receiver");
        Command queued{};queued.kind=Command::Kind::CityPurchase;queued.unitID=cityID;queued.purchaseUnit=unit;queued.purchaseBuilding=building;queued.purchaseProject=project;queued.data1=yield;
        if(depth_)pending_.push_back(queued);else Deliver(callbacks,std::vector<Command>{queued});
    }
    void SendCityTask(int cityID,TaskTypes task,int data1,int data2,bool option,bool alt,bool shift,bool control){
        const auto callbacks=RequireReceiver();if(!callbacks->cityTaskHandler)throw std::logic_error("Local city tasks require a bound SDK receiver");
        Command queued{};queued.kind=Command::Kind::CityTask;queued.unitID=cityID;queued.cityTask=task;queued.data1=data1;queued.data2=data2;queued.taskOption=option;queued.alt=alt;queued.shift=shift;queued.control=control;
        if(depth_)pending_.push_back(queued);else Deliver(callbacks,std::vector<Command>{queued});
    }
    void SendLiberatePlayer(PlayerTypes liberated,int cityID){
        const auto callbacks=RequireReceiver();if(!callbacks->liberatePlayerHandler)throw std::logic_error("Local city liberation requires a bound SDK receiver");
        Command queued{};queued.kind=Command::Kind::LiberatePlayer;queued.liberatedPlayer=liberated;queued.unitID=cityID;
        if(depth_)pending_.push_back(queued);else Deliver(callbacks,std::vector<Command>{queued});
    }
    void SendChangeWar(TeamTypes team,bool war){
        const auto callbacks=RequireReceiver();if(!callbacks->changeWarHandler)throw std::logic_error("Local war commands require a bound SDK receiver");
        Command queued{};queued.kind=Command::Kind::ChangeWar;queued.team=team;queued.value=war;
        if(depth_)pending_.push_back(queued);else Deliver(callbacks,std::vector<Command>{queued});
    }
    void SendFromUIDiploEvent(PlayerTypes other,FromUIDiploEventTypes event,int arg1,int arg2){
        const auto callbacks=RequireReceiver();if(!callbacks->diploEventHandler)throw std::logic_error("Local diplomacy events require a bound SDK receiver");
        Command queued{};queued.kind=Command::Kind::FromUIDiploEvent;queued.diploPlayer=other;queued.diploEvent=event;queued.data1=arg1;queued.data2=arg2;
        if(depth_)pending_.push_back(queued);else Deliver(callbacks,std::vector<Command>{queued});
    }
    void SendFoundPantheon(PlayerTypes owner,BeliefTypes belief){
        const auto callbacks=RequireReceiver();
        if(!callbacks->foundPantheonHandler)throw std::logic_error("Local pantheon founding requires a bound SDK receiver");
        if(owner<0 || owner>=MAX_PLAYERS || static_cast<int>(belief)<0)
            throw std::invalid_argument("Local pantheon founding has an invalid player or belief ID");
        Command queued{};queued.kind=Command::Kind::FoundPantheon;queued.pantheonOwner=owner;queued.pantheonBelief=belief;
        if(depth_)pending_.push_back(queued);else Deliver(callbacks,std::vector<Command>{queued});
    }

    void End(){
        const auto callbacks=RequireReceiver();
        if(!depth_)throw std::logic_error("Local message bundle end has no begin");
        if(--depth_==0){
            std::vector<Command> batch;
            batch.swap(pending_);
            Deliver(callbacks,batch);
        }
    }

    bool IsBound() const noexcept {return static_cast<bool>(binding_);}
    bool IsQuiescent() const noexcept {return depth_==0 && !dispatching_ && pending_.empty();}

private:
    struct Command {
        enum class Kind {PlayerOption,UnitCommand,PushMission,PushOrder,Research,CityPurchase,CityTask,LiberatePlayer,SwapUnits,ChangeWar,FromUIDiploEvent,FoundPantheon};
        Kind kind;
        PlayerOptionTypes option;
        bool value;
        int unitID;
        CommandTypes command;
        int data1,data2;
        bool alt;
        MissionTypes mission;
        int flags;
        bool shift;
        OrderTypes order;bool control;TechTypes tech;PlayerTypes stealFrom;
        UnitTypes purchaseUnit;BuildingTypes purchaseBuilding;ProjectTypes purchaseProject;TeamTypes team;PlayerTypes diploPlayer;FromUIDiploEventTypes diploEvent;
        TaskTypes cityTask;PlayerTypes liberatedPlayer;bool taskOption;
        PlayerTypes pantheonOwner;BeliefTypes pantheonBelief;
    };
    struct Callbacks {
        Callbacks(PlayerOptionHandler handlerValue,PlayerOptionLookup lookupValue,UnitCommandHandler unitHandlerValue,PushMissionHandler missionHandlerValue,PushOrderHandler orderHandlerValue,ResearchHandler researchHandlerValue,CityPurchaseHandler purchaseHandlerValue,CityTaskHandler cityTaskHandlerValue,LiberatePlayerHandler liberatePlayerHandlerValue,PushMissionHandler swapHandlerValue,ChangeWarHandler changeWarHandlerValue,FromUIDiploEventHandler diploEventHandlerValue,FoundPantheonHandler foundPantheonHandlerValue)
            :handler(std::move(handlerValue)),lookup(std::move(lookupValue)),unitHandler(std::move(unitHandlerValue)),missionHandler(std::move(missionHandlerValue)),orderHandler(std::move(orderHandlerValue)),researchHandler(std::move(researchHandlerValue)),purchaseHandler(std::move(purchaseHandlerValue)),cityTaskHandler(std::move(cityTaskHandlerValue)),liberatePlayerHandler(std::move(liberatePlayerHandlerValue)),swapHandler(std::move(swapHandlerValue)),changeWarHandler(std::move(changeWarHandlerValue)),diploEventHandler(std::move(diploEventHandlerValue)),foundPantheonHandler(std::move(foundPantheonHandlerValue)){}
        PlayerOptionHandler handler;
        PlayerOptionLookup lookup;
        UnitCommandHandler unitHandler;
        PushMissionHandler missionHandler;
        PushOrderHandler orderHandler;ResearchHandler researchHandler;
        CityPurchaseHandler purchaseHandler;
        CityTaskHandler cityTaskHandler;
        LiberatePlayerHandler liberatePlayerHandler;
        PushMissionHandler swapHandler;
        ChangeWarHandler changeWarHandler;
        FromUIDiploEventHandler diploEventHandler;
        FoundPantheonHandler foundPantheonHandler;
    };
    class DispatchScope final {
    public:
        explicit DispatchScope(const LocalGameCommands& owner):owner_(owner){
            owner_.dispatching_=true;
            owner_.dispatchCancelled_=false;
        }
        ~DispatchScope(){
            owner_.dispatching_=false;
            owner_.dispatchCancelled_=false;
        }
        DispatchScope(const DispatchScope&)=delete;
        DispatchScope& operator=(const DispatchScope&)=delete;
    private:
        const LocalGameCommands& owner_;
    };

    std::shared_ptr<const Callbacks> RequireReceiver() const {
        if(dispatching_)throw std::logic_error("Reentrant local command operations are unsupported");
        if(!binding_)throw std::logic_error("Local commands require a bound SDK receiver");
        return binding_;
    }

    void Deliver(const std::shared_ptr<const Callbacks>& callbacks,const std::vector<Command>& batch){
        DispatchScope scope(*this);
        for(const auto& command:batch){
            if(dispatchCancelled_)break;
            if(command.kind==Command::Kind::PlayerOption)
                callbacks->handler(command.option,command.value);
            else if(command.kind==Command::Kind::UnitCommand)
                callbacks->unitHandler(command.unitID,command.command,command.data1,command.data2,command.alt);
            else if(command.kind==Command::Kind::PushMission)
                callbacks->missionHandler(command.unitID,command.mission,command.data1,command.data2,command.flags,command.shift);
            else if(command.kind==Command::Kind::SwapUnits)
                callbacks->swapHandler(command.unitID,command.mission,command.data1,command.data2,command.flags,command.shift);
            else if(command.kind==Command::Kind::PushOrder)
                callbacks->orderHandler(command.unitID,command.order,command.data1,command.alt,command.shift,command.control);
            else if(command.kind==Command::Kind::Research)callbacks->researchHandler(command.tech,command.data1,command.stealFrom,command.shift);
            else if(command.kind==Command::Kind::CityPurchase)callbacks->purchaseHandler(command.unitID,command.purchaseUnit,command.purchaseBuilding,command.purchaseProject,command.data1);
            else if(command.kind==Command::Kind::CityTask)callbacks->cityTaskHandler(command.unitID,command.cityTask,command.data1,command.data2,command.taskOption,command.alt,command.shift,command.control);
            else if(command.kind==Command::Kind::LiberatePlayer)callbacks->liberatePlayerHandler(command.liberatedPlayer,command.unitID);
            else if(command.kind==Command::Kind::ChangeWar)callbacks->changeWarHandler(command.team,command.value);
            else if(command.kind==Command::Kind::FromUIDiploEvent)callbacks->diploEventHandler(command.diploPlayer,command.diploEvent,command.data1,command.data2);
            else callbacks->foundPantheonHandler(command.pantheonOwner,command.pantheonBelief);
        }
    }

    std::shared_ptr<const Callbacks> binding_;
    std::vector<Command> pending_;
    unsigned depth_=0;
    mutable bool dispatching_=false;
    mutable bool dispatchCancelled_=false;
};
}
