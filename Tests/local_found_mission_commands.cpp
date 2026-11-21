#include "LocalGameCommands.h"
#include <cstdio>
#include <stdexcept>
#include <string>
#include <vector>

using ZeroSisHost::LocalGameCommands;

namespace {
int checks=0;
void Require(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
template<class E,class F> void Throws(F&& f,const char* message){bool caught=false;try{f();}catch(const E&){caught=true;}Require(caught,message);}

void TestOrderedMissionTransport(){
    LocalGameCommands commands;
    std::vector<std::string> received;
    commands.Bind([&](PlayerOptionTypes,bool){received.push_back("option");},[](PlayerOptionTypes){return false;},
        [&](int id,CommandTypes,int,int,bool){received.push_back("unit:"+std::to_string(id));},
        [&](int id,MissionTypes mission,int a,int b,int flags,bool shift){
            received.push_back("mission:"+std::to_string(id)+":"+std::to_string(static_cast<int>(mission))+":"+
                std::to_string(a)+":"+std::to_string(b)+":"+std::to_string(flags)+":"+(shift?"1":"0"));
        });
    const auto found=static_cast<MissionTypes>(0xF1234567u);
    commands.Begin();
    commands.SendUnitCommand(4,COMMAND_PROMOTION,2,-1,false);
    commands.SendPushMission(4,found,-1,-1,0,false);
    commands.SendPlayerOption(static_cast<PlayerOptionTypes>(0xF2345678u),true);
    Require(received.empty(),"Bundled mission escaped before End");
    commands.End();
    Require(received.size()==3,"Bundle did not deliver every queued command");
    Require(received[0]=="unit:4","Unit command order changed");
    Require(received[1]=="mission:4:"+std::to_string(static_cast<int>(found))+":-1:-1:0:0","Found payload changed");
    Require(received[2]=="option","Mission transport changed neighboring command order");
    Require(commands.IsQuiescent(),"Completed mission bundle is not quiescent");
}

void TestMissingBindingAndReentrantCancellation(){
    LocalGameCommands absent;
    Throws<std::logic_error>([&]{absent.SendPushMission(1,static_cast<MissionTypes>(7),-1,-1,0,false);},"Unbound mission accepted");
    LocalGameCommands noMissionHandler;
    noMissionHandler.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;});
    Throws<std::logic_error>([&]{noMissionHandler.SendPushMission(1,static_cast<MissionTypes>(7),-1,-1,0,false);},"Mission accepted without receiver");
    Require(noMissionHandler.IsQuiescent(),"Missing receiver changed transport state");

    LocalGameCommands commands;
    std::vector<int> received;
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;},
        [&](int id,CommandTypes,int,int,bool){received.push_back(id);},
        [&](int id,MissionTypes,int,int,int,bool){
            received.push_back(id);
            Throws<std::logic_error>([&]{commands.SendPushMission(99,static_cast<MissionTypes>(7),-1,-1,0,false);},"Reentrant mission accepted");
            commands.Unbind();
            Require(!commands.IsBound(),"Callback Unbind did not detach receiver");
        });
    commands.Begin();
    commands.SendPushMission(5,static_cast<MissionTypes>(8),-1,-1,0,false);
    commands.SendUnitCommand(6,COMMAND_WAKE,0,0,false);
    commands.End();
    Require(received.size()==1 && received[0]==5,"Unbind failed to cancel remaining commands");
    Require(!commands.IsBound() && commands.IsQuiescent(),"Cancelled mission bundle left stale state");
}
}

int main(){
    try{TestOrderedMissionTransport();TestMissingBindingAndReentrantCancellation();
        std::printf("LOCAL_FOUND_MISSION_TRANSPORT_PASS checks=%d GAMECORE_LOADED=false\n",checks);return 0;
    }catch(const std::exception& error){
        std::fprintf(stderr,"LOCAL_FOUND_MISSION_TRANSPORT_FAIL checks=%d reason=%s\n",checks,error.what());return 1;
    }
}
