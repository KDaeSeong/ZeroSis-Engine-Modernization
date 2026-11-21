#include "LocalSdkSession.h"
#include <cstdio>
#include <atomic>
#include <stdexcept>
#include <string>
#include <thread>

using ZeroSisHost::LocalUnitSelection;
namespace {
int checks=0;
void Require(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
template<class E,class F>void Throws(F&& f,const char* message){bool caught=false;try{f();}catch(const E&){caught=true;}Require(caught,message);}

void TestOwnerLockIsFirstAndEmptyHeadlessProfile(){
    LocalUnitSelection selection;int ownerChecks=0,activeChecks=0,resolves=0;bool locked=false;
    selection.SetOwnerCheck([&](){++ownerChecks;return locked;});
    locked=true;
    Require(selection.Length()==0,"Empty profile selection was not empty");
    Require(ownerChecks>=1,"Empty query skipped the owner-lock check");
    selection.Bind([&](PlayerTypes){++activeChecks;return true;},[&](PlayerTypes,int)->ICvUnit1*{++resolves;return nullptr;});
    locked=false;
    Throws<std::logic_error>([&](){selection.InsertSingle(static_cast<PlayerTypes>(0),3,true,false,false,false);},
        "Unlocked selection insertion was accepted");
    Require(activeChecks==0 && resolves==0,"Unlocked selection evaluated SDK callbacks before rejecting");
    locked=true;
    Throws<std::logic_error>([&](){selection.InsertSingle(static_cast<PlayerTypes>(0),3,true,false,false,false);},
        "Missing SDK unit was selected");
    Require(activeChecks==1 && resolves==1,"Locked selection did not resolve the fresh unit");
    Require(selection.Length()==0,"Rejected missing unit left stale selection state");
    const int before=resolves;
    Throws<std::invalid_argument>([&](){selection.InsertSingle(static_cast<PlayerTypes>(0),-1,true,false,false,false);},
        "Negative unit ID reached the selection resolver");
    Require(resolves==before,"Negative unit ID reached the SDK resolver");
}

void TestSelectionScopeFailsClosedAndEnumeratorExpires(){
    LocalUnitSelection selection;bool locked=true;int resolves=0,activeChecks=0;
    const auto ownerThread=std::this_thread::get_id();
    selection.SetOwnerCheck([&](){return locked && std::this_thread::get_id()==ownerThread;});
    selection.Bind([&](PlayerTypes){++activeChecks;return true;},[&](PlayerTypes,int)->ICvUnit1*{++resolves;return nullptr;});
    Throws<std::logic_error>([&](){selection.InsertSingle(static_cast<PlayerTypes>(0),9,false,false,false,false);},
        "Append selection was silently accepted");
    Throws<std::logic_error>([&](){selection.InsertSingle(static_cast<PlayerTypes>(0),9,true,true,false,false);},
        "Toggle selection was silently accepted");
    Throws<std::logic_error>([&](){selection.InsertSingle(static_cast<PlayerTypes>(0),9,true,false,true,false);},
        "Group selection was silently accepted");
    Require(resolves==0,"Unsupported selection scopes reached the resolver");
    std::unique_ptr<ICvEnumerator> enumerator(selection.CreateEnumerator());
    std::unique_ptr<ICvEnumerator> queried(static_cast<ICvEnumerator*>(enumerator->QueryInterface(guidICvEnumerator)));
    Require(queried.get()==enumerator.get(),"Enumerator QueryInterface did not return the reference-counted adapter");
    enumerator.reset();
    locked=false;
    Throws<std::logic_error>([&](){queried->MoveNext();},"Unlocked live enumerator advanced");
    Throws<std::logic_error>([&](){queried->Reset();},"Unlocked live enumerator reset");
    locked=true;
    std::atomic<bool> wrongThreadRejected{false};
    std::thread wrongThread([&](){try{queried->MoveNext();}catch(const std::logic_error&){wrongThreadRejected=true;}});
    wrongThread.join();
    Require(wrongThreadRejected.load(),"Wrong-thread live enumerator query was accepted");
    const auto epoch=selection.Epoch();selection.Unbind();
    Require(selection.Epoch()!=epoch,"Unbind did not advance the selection epoch");
    const int before=resolves;
    Require(!queried->MoveNext(),"Expired enumerator advanced after Unbind");
    Require(queried->GetCurrent()==nullptr,"Expired enumerator returned an SDK wrapper");
    Require(resolves==before,"Expired enumerator called the SDK resolver after Unbind");
    Require(!selection.IsBound() && selection.Length()==0,"Unbound selection did not return to the empty profile");
    queried.reset();
    locked=false;
    Throws<std::logic_error>([&](){selection.Bind([](PlayerTypes){return true;},[](PlayerTypes,int)->ICvUnit1*{return nullptr;});},
        "Unbound selection was rebound without owner lock");
}
}

int main(){
    try{
        TestOwnerLockIsFirstAndEmptyHeadlessProfile();
        TestSelectionScopeFailsClosedAndEnumeratorExpires();
        std::printf("LOCAL_UNIT_SELECTION_PASS checks=%d SDK_WRAPPER_MOCKED=true GAMECORE_LOADED=false\n",checks);
        return 0;
    }catch(const std::exception& error){
        std::fprintf(stderr,"LOCAL_UNIT_SELECTION_FAIL checks=%d reason=%s\n",checks,error.what());return 1;
    }
}
