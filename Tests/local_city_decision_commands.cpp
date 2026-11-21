#include "LocalGameCommands.h"
#include <stdexcept>
#include <iostream>
#include <string>
#include <vector>

using ZeroSisHost::LocalGameCommands;
namespace {
int checks=0;
void Require(bool ok,const char* message){++checks;if(!ok)throw std::runtime_error(message);}
void RequireThrows(const std::function<void()>& call){bool threw=false;try{call();}catch(const std::logic_error&){threw=true;}Require(threw,"expected transport rejection");}
void RequireInvalid(const std::function<void()>& call){bool threw=false;try{call();}catch(const std::invalid_argument&){threw=true;}Require(threw,"expected invalid local command rejection");}
void TestNativeEnvelopeGuards(){
    LocalGameCommands::RequireOwnerLock(true,true);
    RequireThrows([]{LocalGameCommands::RequireOwnerLock(false,true);});
    RequireThrows([]{LocalGameCommands::RequireOwnerLock(true,false);});
    LocalGameCommands::ValidateCityOrderEnvelope(7,ORDER_TRAIN,19,false,false,true);
    LocalGameCommands::ValidateCityOrderEnvelope(7,ORDER_CONSTRUCT,21,false,true,true);
    RequireInvalid([]{LocalGameCommands::ValidateCityOrderEnvelope(-1,ORDER_TRAIN,1,false,true,true);});
    RequireInvalid([]{LocalGameCommands::ValidateCityOrderEnvelope(7,static_cast<OrderTypes>(99),1,false,true,true);});
    RequireInvalid([]{LocalGameCommands::ValidateCityOrderEnvelope(7,ORDER_TRAIN,1,true,true,true);});
    LocalGameCommands::ValidateCityPurchaseEnvelope(7,static_cast<UnitTypes>(1),NO_BUILDING,NO_PROJECT,YIELD_GOLD);
    RequireInvalid([]{LocalGameCommands::ValidateCityPurchaseEnvelope(7,NO_UNIT,NO_BUILDING,NO_PROJECT,YIELD_GOLD);});
    RequireInvalid([]{LocalGameCommands::ValidateCityPurchaseEnvelope(7,static_cast<UnitTypes>(1),static_cast<BuildingTypes>(1),NO_PROJECT,YIELD_GOLD);});
    RequireInvalid([]{LocalGameCommands::ValidateCityPurchaseEnvelope(7,static_cast<UnitTypes>(1),NO_BUILDING,NO_PROJECT,NO_YIELD);});
}
void TestLegacyBindAndFifo(){
    LocalGameCommands commands;std::vector<std::string> calls;
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;}); // original call shape remains source compatible
    commands.Unbind();
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;},{},{},
        [&](int city,OrderTypes order,int data,bool alt,bool shift,bool ctrl){calls.push_back("o:"+std::to_string(city)+":"+std::to_string(static_cast<int>(order))+":"+std::to_string(data)+":"+std::to_string(alt)+std::to_string(shift)+std::to_string(ctrl));},
        [&](TechTypes tech,int discover,PlayerTypes steal,bool shift){calls.push_back("r:"+std::to_string(static_cast<int>(tech))+":"+std::to_string(discover)+":"+std::to_string(static_cast<int>(steal))+":"+std::to_string(shift));},
        [&](int city,UnitTypes unit,BuildingTypes building,ProjectTypes project,int yield){calls.push_back("p:"+std::to_string(city)+":"+std::to_string(static_cast<int>(unit))+":"+std::to_string(static_cast<int>(building))+":"+std::to_string(static_cast<int>(project))+":"+std::to_string(yield));});
    commands.Begin();commands.SendPushOrder(7,ORDER_TRAIN,19,false,true,true);commands.SendPushOrder(7,ORDER_CONSTRUCT,21,false,false,true);commands.SendPushOrder(7,ORDER_CREATE,22,false,true,true);commands.SendPushOrder(7,ORDER_MAINTAIN,4,false,false,true);commands.SendResearch(static_cast<TechTypes>(3),0,NO_PLAYER,false);commands.SendCityPurchase(7,static_cast<UnitTypes>(19),NO_BUILDING,NO_PROJECT,YIELD_FAITH);Require(calls.empty(),"bundle dispatched early");commands.End();
    Require(calls.size()==6 && calls[0]=="o:7:0:19:011" && calls[1]=="o:7:1:21:001" && calls[2]=="o:7:2:22:011" && calls[3]=="o:7:3:4:001" && calls[4]=="r:3:0:-1:0" && calls[5]=="p:7:19:-1:-1:5","FIFO, official production tuple, or purchase yield changed");
    LocalGameCommands unbound;bool rejected=false;try{unbound.SendCityPurchase(7,static_cast<UnitTypes>(1),NO_BUILDING,NO_PROJECT,YIELD_GOLD);}catch(const std::logic_error&){rejected=true;}Require(rejected,"unbound purchase did not reject");
}
void TestCityDecisionFifoAndOptionalHandlers(){
    LocalGameCommands commands;std::vector<std::string> calls;
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;},{},{},{},{},{},
        [&](int city,TaskTypes task,int data1,int data2,bool option,bool alt,bool shift,bool control){
            calls.push_back("t:"+std::to_string(city)+":"+std::to_string(static_cast<int>(task))+":"+
                std::to_string(data1)+":"+std::to_string(data2)+":"+std::to_string(option)+
                std::to_string(alt)+std::to_string(shift)+std::to_string(control));
        },
        [&](PlayerTypes player,int city){calls.push_back("l:"+std::to_string(static_cast<int>(player))+":"+std::to_string(city));});
    commands.Begin();
    commands.SendCityTask(41,TASK_CREATE_PUPPET,-1,-1,false,false,false,false);
    commands.SendLiberatePlayer(static_cast<PlayerTypes>(7),41);
    commands.SendCityTask(52,TASK_RAZE,-1,-1,false,false,false,false);
    commands.SendCityTask(63,TASK_ANNEX_PUPPET,11,12,true,false,true,false);
    Require(calls.empty(),"city decision bundle dispatched before End");
    commands.End();
    Require(calls.size()==4 && calls[0]=="t:41:19:-1:-1:0000" && calls[1]=="l:7:41" &&
        calls[2]=="t:52:0:-1:-1:0000" && calls[3]=="t:63:20:11:12:1010",
        "city task tuple fields, liberation payload, or FIFO order changed");

    LocalGameCommands legacy;
    legacy.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;});
    bool taskRejected=false,liberationRejected=false;
    try{legacy.SendCityTask(41,TASK_ANNEX_PUPPET,-1,-1,false,false,false,false);}catch(const std::logic_error&){taskRejected=true;}
    try{legacy.SendLiberatePlayer(static_cast<PlayerTypes>(7),41);}catch(const std::logic_error&){liberationRejected=true;}
    Require(taskRejected && liberationRejected,"optional city handlers did not reject when unbound");
}
void TestCityDecisionFailureReentrancyAndCancellation(){
    LocalGameCommands commands;int taskCalls=0,liberationCalls=0;
    auto capture=std::make_shared<int>(23);std::weak_ptr<int> weak=capture;
    std::function<void(int,TaskTypes,int,int,bool,bool,bool,bool)> taskHandler=
        [&,held=capture](int,TaskTypes,int,int,bool,bool,bool,bool){
            ++taskCalls;Require(*held==23,"city task callback capture changed");
            RequireThrows([&]{commands.SendLiberatePlayer(static_cast<PlayerTypes>(3),8);});
            commands.Unbind();Require(!weak.expired(),"Unbind destroyed an in-flight city-task callback");
            throw std::logic_error("mock city task receiver failure");
        };
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;},{},{},{},{},{},taskHandler,
        [&](PlayerTypes,int){++liberationCalls;});
    capture.reset();taskHandler={};
    commands.Begin();commands.SendCityTask(8,TASK_ANNEX_PUPPET,-1,-1,false,false,false,false);
    commands.SendLiberatePlayer(static_cast<PlayerTypes>(3),8);
    RequireThrows([&]{commands.End();});
    Require(taskCalls==1 && liberationCalls==0 && commands.IsQuiescent() && !commands.IsBound(),
        "city callback exception or Unbind failed to cancel the remaining batch");
    Require(weak.expired(),"city task callback capture survived completed dispatch");

    LocalGameCommands liberationFailure;int liberationFailureCalls=0,taskAfterFailure=0;
    liberationFailure.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;},{},{},{},{},{},
        [&](int,TaskTypes,int,int,bool,bool,bool,bool){++taskAfterFailure;},
        [&](PlayerTypes,int){++liberationFailureCalls;throw std::logic_error("mock liberation receiver failure");});
    liberationFailure.Begin();liberationFailure.SendLiberatePlayer(static_cast<PlayerTypes>(2),4);
    liberationFailure.SendCityTask(4,TASK_RAZE,-1,-1,false,false,false,false);
    RequireThrows([&]{liberationFailure.End();});
    Require(liberationFailureCalls==1 && taskAfterFailure==0 && liberationFailure.IsQuiescent(),
        "liberation callback failure did not propagate or stop later work");
}
void TestFailureAndUnbindLifetime(){
    LocalGameCommands commands;int calls=0;auto capture=std::make_shared<int>(9);std::weak_ptr<int> weak=capture;
    std::function<void(int,OrderTypes,int,bool,bool,bool)> callback=[&,held=capture](int,OrderTypes,int,bool,bool,bool){++calls;if(calls==1){Require(*held==9,"callback capture changed");commands.Unbind();Require(!weak.expired(),"Unbind destroyed the in-flight callback");RequireThrows([&]{commands.SendResearch(static_cast<TechTypes>(1),0,NO_PLAYER,false);});throw std::logic_error("mock receiver failure");}};
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;},{},{},callback,[](TechTypes,int,PlayerTypes,bool){});
    capture.reset();callback={};
    commands.Begin();commands.SendPushOrder(1,ORDER_TRAIN,2,false,true,true);commands.SendResearch(static_cast<TechTypes>(1),0,NO_PLAYER,false);
    RequireThrows([&]{commands.End();});Require(calls==1 && commands.IsQuiescent() && !commands.IsBound(),"failed/cancelled batch retained work");Require(weak.expired(),"callback capture survived completed dispatch");
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;},{},{},[](int,OrderTypes,int,bool,bool,bool){},{});commands.Unbind();
}
}
namespace {
void BindPantheon(LocalGameCommands& commands,LocalGameCommands::FoundPantheonHandler handler,
                 LocalGameCommands::ResearchHandler research={},LocalGameCommands::CityTaskHandler task={}){
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;},
        {},{},{},std::move(research),{},std::move(task),{},{},{},{},std::move(handler));
}
void TestPantheonExactTupleMixedFifo(){
    LocalGameCommands commands;std::vector<std::string> calls;
    BindPantheon(commands,[&](PlayerTypes owner,BeliefTypes belief){
        calls.push_back("pantheon:"+std::to_string(static_cast<int>(owner))+":"+std::to_string(static_cast<int>(belief)));
    },[&](TechTypes tech,int discover,PlayerTypes steal,bool shift){
        Require(discover==0 && steal==NO_PLAYER && !shift,"mixed research tuple changed");
        calls.push_back("research:"+std::to_string(static_cast<int>(tech)));
    },[&](int city,TaskTypes task,int,int,bool,bool,bool,bool){
        Require(task==TASK_ANNEX_PUPPET,"mixed city task changed");calls.push_back("city:"+std::to_string(city));
    });
    commands.SendFoundPantheon(static_cast<PlayerTypes>(0),static_cast<BeliefTypes>(0));
    Require(calls==std::vector<std::string>{"pantheon:0:0"} && commands.IsQuiescent(),
        "immediate pantheon lost valid zero IDs or quiescence");
    commands.Begin();commands.SendResearch(static_cast<TechTypes>(3),0,NO_PLAYER,false);
    commands.Begin();commands.SendFoundPantheon(static_cast<PlayerTypes>(4),static_cast<BeliefTypes>(19));
    commands.End();Require(calls.size()==1,"inner bundle end delivered pantheon early");
    commands.SendCityTask(8,TASK_ANNEX_PUPPET,-1,-1,false,false,false,false);
    commands.SendFoundPantheon(static_cast<PlayerTypes>(2),static_cast<BeliefTypes>(27));
    Require(calls.size()==1,"mixed pantheon bundle delivered before outer End");commands.End();
    Require(calls==std::vector<std::string>{"pantheon:0:0","research:3","pantheon:4:19","city:8","pantheon:2:27"}
        && commands.IsQuiescent(),"pantheon exact tuple, nested mixed FIFO or quiescence changed");
}
void TestPantheonAdmissionAndCancellation(){
    LocalGameCommands unbound;
    RequireThrows([&]{unbound.SendFoundPantheon(static_cast<PlayerTypes>(0),static_cast<BeliefTypes>(1));});
    LocalGameCommands legacy;
    legacy.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;},{},{},{},{},{},{},{},{},{},{});
    RequireThrows([&]{legacy.SendFoundPantheon(static_cast<PlayerTypes>(0),static_cast<BeliefTypes>(1));});
    LocalGameCommands commands;int calls=0;
    BindPantheon(commands,[&](PlayerTypes,BeliefTypes){++calls;});
    RequireInvalid([&]{commands.SendFoundPantheon(NO_PLAYER,static_cast<BeliefTypes>(1));});
    RequireInvalid([&]{commands.SendFoundPantheon(static_cast<PlayerTypes>(MAX_PLAYERS),static_cast<BeliefTypes>(1));});
    RequireInvalid([&]{commands.SendFoundPantheon(static_cast<PlayerTypes>(0),static_cast<BeliefTypes>(-1));});
    Require(calls==0 && commands.IsQuiescent(),"invalid pantheon envelope reached receiver");
    commands.Begin();commands.SendFoundPantheon(static_cast<PlayerTypes>(0),static_cast<BeliefTypes>(1));
    commands.Unbind();Require(calls==0 && !commands.IsBound() && commands.IsQuiescent(),"Unbind retained pending pantheon work");
    RequireThrows([&]{commands.End();});
    BindPantheon(commands,[&](PlayerTypes,BeliefTypes){++calls;});commands.Begin();commands.End();
    Require(calls==0,"a new binding replayed cancelled pantheon work");
}
void TestPantheonFailureReentrancyAndLifetime(){
    LocalGameCommands commands;int calls=0,researchCalls=0;
    auto held=std::make_shared<int>(57);std::weak_ptr<int> weak=held;
    LocalGameCommands::FoundPantheonHandler callback=[&,capture=held](PlayerTypes owner,BeliefTypes belief){
        ++calls;Require(*capture==57 && owner==static_cast<PlayerTypes>(1) && belief==static_cast<BeliefTypes>(9),
            "in-flight pantheon callback tuple or capture changed");
        RequireThrows([&]{commands.SendFoundPantheon(owner,belief);});
        RequireThrows([&]{commands.Begin();});RequireThrows([&]{commands.End();});
        commands.Unbind();Require(!weak.expired(),"Unbind destroyed the in-flight pantheon handler");
        throw std::logic_error("mock pantheon receiver failed");
    };
    BindPantheon(commands,callback,[&](TechTypes,int,PlayerTypes,bool){++researchCalls;});
    held.reset();callback={};commands.Begin();
    commands.SendFoundPantheon(static_cast<PlayerTypes>(1),static_cast<BeliefTypes>(9));
    commands.SendResearch(static_cast<TechTypes>(1),0,NO_PLAYER,false);
    RequireThrows([&]{commands.End();});
    Require(calls==1 && researchCalls==0 && weak.expired() && !commands.IsBound() && commands.IsQuiescent(),
        "pantheon failure/Unbind failed to cancel later mixed work or release callback lifetime");
    LocalGameCommands failure;int rejectedCalls=0;bool reject=true;
    BindPantheon(failure,[&](PlayerTypes,BeliefTypes){++rejectedCalls;if(reject)throw std::logic_error("mock receiver failure");});
    failure.Begin();failure.SendFoundPantheon(static_cast<PlayerTypes>(0),static_cast<BeliefTypes>(1));
    failure.SendFoundPantheon(static_cast<PlayerTypes>(0),static_cast<BeliefTypes>(2));
    RequireThrows([&]{failure.End();});
    Require(rejectedCalls==1 && failure.IsBound() && failure.IsQuiescent(),"pantheon receiver exception leaked later work");
    reject=false;
    failure.SendFoundPantheon(static_cast<PlayerTypes>(0),static_cast<BeliefTypes>(3));
    Require(rejectedCalls==2 && failure.IsQuiescent(),"pantheon transport could not recover after a completed failure");
}
}
int main(){
    try{
        TestNativeEnvelopeGuards();TestLegacyBindAndFifo();TestCityDecisionFifoAndOptionalHandlers();
        TestCityDecisionFailureReentrancyAndCancellation();TestFailureAndUnbindLifetime();
        TestPantheonExactTupleMixedFifo();TestPantheonAdmissionAndCancellation();TestPantheonFailureReentrancyAndLifetime();
        std::cout<<"LOCAL_CITY_DECISION_COMMANDS_PASS checks="<<checks<<" GAMECORE_LOADED=false MOCK_SDK=true\n";
        return 0;
    }catch(const std::exception& error){
        std::cerr<<"LOCAL_CITY_DECISION_COMMANDS_FAIL "<<error.what()<<" GAMECORE_LOADED=false MOCK_SDK=true\n";
        return 1;
    }
}
