#include "LocalGameCommands.h"
#include <cstdint>
#include <cstdio>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

using ZeroSisHost::LocalGameCommands;

namespace {
int checks=0;

void Require(bool condition,const char* message){
    ++checks;
    if(!condition)throw std::runtime_error(message);
}

template<typename Exception,typename Function>
void RequireThrows(Function&& function,const char* message){
    bool caught=false;
    try{function();}
    catch(const Exception&){caught=true;}
    Require(caught,message);
}

PlayerOptionTypes HashOption(unsigned value){return static_cast<PlayerOptionTypes>(value);}

void BindNoop(LocalGameCommands& commands){
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return true;});
}

void TestNestedFifoAndHashes(){
    LocalGameCommands commands;
    std::vector<std::pair<unsigned,bool>> received;
    commands.Bind([&received](PlayerOptionTypes option,bool value){
        received.push_back(std::make_pair(static_cast<unsigned>(option),value));
    },[](PlayerOptionTypes){return false;});
    const unsigned highA=0xF1493CD2u,highB=0xBF6E16AAu;
    commands.Begin();
    commands.SendPlayerOption(HashOption(highA),true);
    commands.Begin();
    commands.SendPlayerOption(HashOption(0x475DDB5Bu),false);
    commands.End();
    Require(received.empty(),"Nested bundle dispatched before outer End");
    commands.SendPlayerOption(HashOption(highB),true);
    commands.End();
    Require(received.size()==3,"Nested bundle command count differs");
    Require(received[0]==std::make_pair(highA,true),"First high-bit hash changed");
    Require(received[1]==std::make_pair(0x475DDB5Bu,false),"Nested FIFO command changed");
    Require(received[2]==std::make_pair(highB,true),"Second high-bit hash changed");
    Require(commands.IsQuiescent(),"Completed nested bundle is not quiescent");
}

void TestUnboundAndUnmatchedEnd(){
    LocalGameCommands commands;
    RequireThrows<std::logic_error>([&]{commands.Begin();},"Unbound Begin was accepted");
    RequireThrows<std::logic_error>([&]{commands.SendPlayerOption(HashOption(1),true);},"Unbound Send was accepted");
    RequireThrows<std::logic_error>([&]{commands.End();},"Unbound End was accepted");
    RequireThrows<std::logic_error>([&]{commands.GetPlayerOption(HashOption(1));},"Unbound lookup was accepted");
    RequireThrows<std::logic_error>([&]{commands.Bind({},[](PlayerOptionTypes){return true;});},"Empty handler was accepted");
    Require(!commands.IsBound() && commands.IsQuiescent(),"Unbound transport state differs");
    BindNoop(commands);
    RequireThrows<std::logic_error>([&]{commands.End();},"Unmatched End was accepted");
    Require(commands.IsBound() && commands.IsQuiescent(),"Unmatched End changed transport state");
}

void TestReentrantOperations(){
    LocalGameCommands commands;
    int rejected=0;
    commands.Bind([&](PlayerOptionTypes,bool){
        const auto expectRejected=[&](const std::function<void()>& operation){
            try{operation();}
            catch(const std::logic_error&){++rejected;}
        };
        expectRejected([&]{commands.Begin();});
        expectRejected([&]{commands.SendPlayerOption(HashOption(7),false);});
        expectRejected([&]{commands.End();});
        expectRejected([&]{commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return true;});});
        expectRejected([&]{commands.GetPlayerOption(HashOption(7));});
        commands.Unbind();
        Require(!commands.IsBound(),"Reentrant Unbind did not detach binding");
        expectRejected([&]{commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return true;});});
    },[](PlayerOptionTypes){return true;});
    commands.Begin();
    commands.SendPlayerOption(HashOption(8),true);
    commands.SendPlayerOption(HashOption(9),false);
    commands.End();
    Require(rejected==6,"Reentrant operation rejection count differs");
    Require(!commands.IsBound() && commands.IsQuiescent(),"Reentrant Unbind left stale state");
    BindNoop(commands);
    Require(commands.IsBound() && commands.IsQuiescent(),"Rebinding after callback Unbind failed");
    commands.Unbind();

    LocalGameCommands lookupCommands;
    int lookupRejected=0;
    auto lookupLifetime=std::make_shared<int>(73);
    std::weak_ptr<int> weakLookupLifetime=lookupLifetime;
    lookupCommands.Bind([](PlayerOptionTypes,bool){},[&,callbackLifetime=lookupLifetime](PlayerOptionTypes){
        Require(*callbackLifetime==73,"Lookup capture changed");
        const auto expectRejected=[&](const std::function<void()>& operation){
            try{operation();}
            catch(const std::logic_error&){++lookupRejected;}
        };
        expectRejected([&]{lookupCommands.Begin();});
        expectRejected([&]{lookupCommands.SendPlayerOption(HashOption(10),true);});
        expectRejected([&]{lookupCommands.End();});
        expectRejected([&]{lookupCommands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return true;});});
        expectRejected([&]{lookupCommands.GetPlayerOption(HashOption(10));});
        lookupCommands.Unbind();
        Require(!weakLookupLifetime.expired(),"Unbind destroyed the executing lookup target");
        expectRejected([&]{lookupCommands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return true;});});
        return true;
    });
    lookupLifetime.reset();
    Require(lookupCommands.GetPlayerOption(HashOption(11)),"Lookup result changed");
    Require(lookupRejected==6,"Reentrant lookup operation rejection count differs");
    Require(weakLookupLifetime.expired(),"Lookup callback target outlived its completed invocation");
    Require(!lookupCommands.IsBound(),"Lookup Unbind did not detach binding");
    Require(lookupCommands.IsQuiescent(),"Lookup left dispatch guard active");
    BindNoop(lookupCommands);
    Require(lookupCommands.IsBound(),"Rebinding after lookup Unbind failed");
}

void TestAbortUnbindKeepsCallbackAlive(){
    LocalGameCommands commands;
    auto lifetime=std::make_shared<int>(42);
    std::weak_ptr<int> weakLifetime=lifetime;
    auto callbackLifetime=lifetime;
    int calls=0;
    commands.Bind([&,callbackLifetime](PlayerOptionTypes,bool){
        ++calls;
        Require(*callbackLifetime==42,"Callback capture changed");
        commands.Unbind();
        Require(!weakLifetime.expired(),"Unbind destroyed the executing callback target");
        Require(!commands.IsBound(),"Unbind did not take effect during callback");
    },[](PlayerOptionTypes){return true;});
    lifetime.reset();
    callbackLifetime.reset();
    commands.Begin();
    commands.SendPlayerOption(HashOption(12),true);
    commands.SendPlayerOption(HashOption(13),false);
    commands.End();
    Require(calls==1,"Unbind did not abort remaining batch commands");
    Require(weakLifetime.expired(),"Callback target outlived its completed invocation");
    Require(!commands.IsBound() && commands.IsQuiescent(),"Aborted bundle left active state");
    BindNoop(commands);
    Require(commands.IsBound(),"Rebinding after aborted batch failed");
    commands.Unbind();
}

void TestSwapQueueAndLifetime(){
    LocalGameCommands commands;std::vector<int> order;
    const auto mission=static_cast<MissionTypes>(37);
    RequireThrows<std::logic_error>([&]{commands.SendSwapUnits(9,mission,4,5,0,true);},"Unbound swap was accepted");
    BindNoop(commands);
    RequireThrows<std::logic_error>([&]{commands.SendSwapUnits(9,mission,4,5,0,true);},"Swap without its own receiver was accepted");
    commands.Unbind();
    auto lifetime=std::make_shared<int>(17);std::weak_ptr<int> weak=lifetime;
    commands.Bind([&](PlayerOptionTypes,bool){order.push_back(1);},[](PlayerOptionTypes){return true;},
        {},{},{},{},{},{},{},[&,lifetime](int id,MissionTypes m,int x,int y,int flags,bool shift){
            Require(id==9 && m==mission && x==4 && y==5 && flags==0 && shift,"Swap lost its exact SDK tuple or queue flag");
            RequireThrows<std::logic_error>([&]{commands.SendSwapUnits(id,m,x,y,flags,shift);},"Reentrant swap was accepted");
            order.push_back(2);commands.Unbind();
            Require(!weak.expired() && *lifetime==17,"Unbind destroyed the active swap receiver");
        });
    lifetime.reset();commands.Begin();commands.Begin();
    commands.SendPlayerOption(HashOption(11),true);commands.SendSwapUnits(9,mission,4,5,0,true);
    commands.SendPlayerOption(HashOption(12),true);commands.End();
    Require(order.empty(),"Nested swap bundle executed before outer End");commands.End();
    Require(order==std::vector<int>({1,2}),"Swap delivery reordered or replayed after cancellation");
    Require(weak.expired() && !commands.IsBound() && commands.IsQuiescent(),"Swap callback or batch outlived unbind");
}

void TestWarAndDiplomacyFifoAndCancel(){
    LocalGameCommands commands;
    const auto rival=static_cast<TeamTypes>(4);
    const auto other=static_cast<PlayerTypes>(6);
    const auto event=FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR;
    RequireThrows<std::logic_error>([&]{commands.SendChangeWar(rival,true);},"Unbound war command was accepted");
    RequireThrows<std::logic_error>([&]{commands.SendFromUIDiploEvent(other,event,0,0);},"Unbound diplomacy event was accepted");
    BindNoop(commands);
    RequireThrows<std::logic_error>([&]{commands.SendChangeWar(rival,true);},"War command without its receiver was accepted");
    RequireThrows<std::logic_error>([&]{commands.SendFromUIDiploEvent(other,event,0,0);},"Diplomacy event without its receiver was accepted");
    commands.Unbind();

    std::vector<int> order;
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return true;},{},{},{},{},{},{},{},{},
        [&](TeamTypes team,bool war){
            Require(team==rival && war,"War command changed its exact SDK tuple");
            order.push_back(1);
        },[&](PlayerTypes player,FromUIDiploEventTypes receivedEvent,int arg1,int arg2){
            Require(player==other && receivedEvent==event && arg1==0 && arg2==0,"Diplomacy event changed its exact SDK tuple");
            order.push_back(2);
            commands.Unbind();
        });
    commands.Begin();commands.Begin();
    commands.SendChangeWar(rival,true);
    commands.SendFromUIDiploEvent(other,event,0,0);
    commands.SendChangeWar(static_cast<TeamTypes>(5),true);
    commands.End();
    Require(order.empty(),"Nested war bundle executed before outer End");
    commands.End();
    Require(order==std::vector<int>({1,2}),"War/diplomacy FIFO reordered or ignored nested cancellation");
    Require(!commands.IsBound() && commands.IsQuiescent(),"Nested diplomacy cancellation left stale state");
    BindNoop(commands);
    Require(commands.IsBound(),"Rebinding after nested diplomacy cancellation failed");
    commands.Unbind();
}

void TestExceptionsDoNotReplayStaleCommands(){
    LocalGameCommands commands;
    std::vector<unsigned> received;
    bool throwNow=true;
    commands.Bind([&](PlayerOptionTypes option,bool){
        received.push_back(static_cast<unsigned>(option));
        if(throwNow)throw std::runtime_error("handler failure");
    },[](PlayerOptionTypes){return true;});
    commands.Begin();
    commands.SendPlayerOption(HashOption(21),true);
    commands.SendPlayerOption(HashOption(22),true);
    commands.SendPlayerOption(HashOption(23),true);
    RequireThrows<std::runtime_error>([&]{commands.End();},"Handler exception was swallowed");
    Require(received.size()==1 && received[0]==21,"Handler exception did not stop current batch");
    Require(commands.IsQuiescent(),"Handler exception left queued bundle state");
    throwNow=false;
    commands.SendPlayerOption(HashOption(24),false);
    Require(received.size()==2 && received[1]==24,"Stale commands replayed after handler exception");

    int lookupCalls=0;
    LocalGameCommands lookupCommands;
    lookupCommands.Bind([](PlayerOptionTypes,bool){},[&](PlayerOptionTypes)->bool{
        ++lookupCalls;
        if(lookupCalls==1)throw std::runtime_error("lookup failure");
        return false;
    });
    RequireThrows<std::runtime_error>([&]{lookupCommands.GetPlayerOption(HashOption(25));},"Lookup exception was swallowed");
    Require(lookupCommands.IsQuiescent(),"Lookup exception left dispatch guard active");
    Require(!lookupCommands.GetPlayerOption(HashOption(25)),"Lookup did not recover after exception");
    Require(lookupCommands.IsQuiescent(),"Recovered lookup left dispatch guard active");
}
}

int main(){
    try{
        TestNestedFifoAndHashes();
        TestUnboundAndUnmatchedEnd();
        TestReentrantOperations();
        TestAbortUnbindKeepsCallbackAlive();
        TestExceptionsDoNotReplayStaleCommands();
        TestSwapQueueAndLifetime();
        TestWarAndDiplomacyFifoAndCancel();
        std::printf("LOCAL_GAME_COMMANDS_PASS checks=%d GAMECORE_LOADED=false\n",checks);
        return 0;
    }catch(const std::exception& error){
        std::fprintf(stderr,"LOCAL_GAME_COMMANDS_FAIL checks=%d reason=%s\n",checks,error.what());
        return 1;
    }
}
