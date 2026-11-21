#include "LocalSdkSession.h"
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

void TestMixedBatchOrderAndFields(){
    LocalGameCommands commands;
    std::vector<std::string> received;
    commands.Bind([&](PlayerOptionTypes option,bool value){
        received.push_back("option:"+std::to_string(static_cast<unsigned>(option))+":"+(value?"1":"0"));
    },[](PlayerOptionTypes){return false;},[&](int unitID,CommandTypes command,int data1,int data2,bool alt){
        received.push_back("unit:"+std::to_string(unitID)+":"+std::to_string(static_cast<int>(command))+":"+
            std::to_string(data1)+":"+std::to_string(data2)+":"+(alt?"1":"0"));
    });
    const unsigned optionHash=0xF1493CD2u;
    commands.Begin();
    commands.SendPlayerOption(HashOption(optionHash),true);
    commands.SendUnitCommand(17,COMMAND_PROMOTION,23,-1,false);
    commands.SendPlayerOption(HashOption(0x475DDB5Bu),false);
    commands.SendUnitCommand(17,COMMAND_WAKE,4,9,false);
    Require(received.empty(),"Mixed batch dispatched before outer End");
    commands.End();
    Require(received.size()==4,"Mixed batch command count differs");
    Require(received[0]=="option:"+std::to_string(optionHash)+":1","First player option moved or changed");
    Require(received[1]=="unit:17:"+std::to_string(static_cast<int>(COMMAND_PROMOTION))+":23:-1:0","Promotion command fields changed");
    Require(received[2]=="option:"+std::to_string(0x475DDB5Bu)+":0","Second player option moved or changed");
    Require(received[3]=="unit:17:"+std::to_string(static_cast<int>(COMMAND_WAKE))+":4:9:0","Second unit command moved or changed");
    Require(commands.IsQuiescent(),"Mixed batch did not return to quiescence");
}

void TestOptionalHandlerRejectsUnitSend(){
    LocalGameCommands commands;
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return true;});
    RequireThrows<std::logic_error>([&]{commands.SendUnitCommand(2,COMMAND_PROMOTION,1,-1);},
        "Unit command without a receiver was accepted");
    Require(commands.IsBound() && commands.IsQuiescent(),"Rejected unit send changed bound transport state");
}

void TestUnitUnbindCancelsMixedBatchAndKeepsHandlerAlive(){
    LocalGameCommands commands;
    auto lifetime=std::make_shared<int>(91);
    std::weak_ptr<int> weakLifetime=lifetime;
    int unitCalls=0,optionCalls=0,reentrantRejects=0;
    commands.Bind([&](PlayerOptionTypes,bool){++optionCalls;},[](PlayerOptionTypes){return false;},
        [&,callbackLifetime=lifetime](int unitID,CommandTypes command,int data1,int data2,bool alt){
            ++unitCalls;
            Require(*callbackLifetime==91,"Unit callback capture changed");
            Require(unitID==8 && command==COMMAND_PROMOTION && data1==6 && data2==-1 && !alt,
                "Unit command callback fields changed");
            try{commands.SendUnitCommand(8,COMMAND_PROMOTION,7,-1);}
            catch(const std::logic_error&){++reentrantRejects;}
            commands.Unbind();
            Require(!weakLifetime.expired(),"Unbind destroyed the executing unit callback target");
            Require(!commands.IsBound(),"Unit callback Unbind did not detach binding");
        });
    lifetime.reset();
    commands.Begin();
    commands.SendUnitCommand(8,COMMAND_PROMOTION,6,-1);
    commands.SendPlayerOption(HashOption(5),true);
    commands.SendUnitCommand(8,COMMAND_WAKE,1,2);
    commands.End();
    Require(unitCalls==1 && optionCalls==0,"Unit unbind did not cancel the remaining mixed batch");
    Require(reentrantRejects==1,"Reentrant unit send was not rejected");
    Require(weakLifetime.expired(),"Unit callback capture outlived completed dispatch");
    Require(!commands.IsBound() && commands.IsQuiescent(),"Cancelled mixed batch left stale state");
    commands.Bind([](PlayerOptionTypes,bool){},[](PlayerOptionTypes){return false;});
    Require(commands.IsBound(),"Rebind after unit callback cancellation failed");
}
}

int main(){
    try{
        TestMixedBatchOrderAndFields();
        TestOptionalHandlerRejectsUnitSend();
        TestUnitUnbindCancelsMixedBatchAndKeepsHandlerAlive();
        std::printf("LOCAL_UNIT_COMMANDS_PASS checks=%d GAMECORE_LOADED=false\n",checks);
        return 0;
    }catch(const std::exception& error){
        std::fprintf(stderr,"LOCAL_UNIT_COMMANDS_FAIL checks=%d reason=%s\n",checks,error.what());
        return 1;
    }
}
