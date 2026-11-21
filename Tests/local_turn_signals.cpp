#include "LocalTurnSignals.h"
#include <cstdio>
#include <memory>
#include <stdexcept>

using ZeroSisHost::LocalTurnSignals;

namespace {
int checks=0;
void Require(bool condition,const char* message){++checks;if(!condition)throw std::runtime_error(message);}

template<typename Exception,typename Function>
void RequireThrows(Function&& function,const char* message){
    bool caught=false;
    try{function();}catch(const Exception&){caught=true;}
    Require(caught,message);
}

void TestTurnTaggedAcksAndParticipant(){
    LocalTurnSignals signals;
    int turn=0;
    signals.Bind([&turn]{return turn;},3);
    Require(!signals.CivsProcessed() && !signals.LocalPlayerProcessed(),"New session started with stale acknowledgements");
    Require(!signals.HasSentTurnComplete() && !signals.HasReceivedTurnComplete(3),"New session started with stale completion");
    Require(!signals.HasSentTurnAllComplete() && !signals.HasReceivedTurnAllComplete(3),
        "New session started with stale all-complete confirmation");
    signals.AcknowledgeCivs();
    Require(signals.CivsProcessed(),"Civ acknowledgement did not match current turn");
    Require(!signals.LocalPlayerProcessed(),"Civ acknowledgement satisfied player barrier");
    signals.AcknowledgeLocalPlayer();
    Require(signals.LocalPlayerProcessed(),"Local player acknowledgement did not match current turn");
    signals.SendTurnComplete();
    Require(signals.HasSentTurnComplete(),"Turn completion send was not recorded");
    Require(signals.HasReceivedTurnComplete(3),"Local participant did not receive its own completion");
    Require(!signals.HasReceivedTurnComplete(2),"Another player received the local participant completion");
    Require(!signals.HasSentTurnAllComplete() && !signals.HasReceivedTurnAllComplete(3),
        "First completion acknowledgement was mistaken for all-complete");
    Require(!signals.HasReceivedTurnAllComplete(2),"Another player received the local all-complete confirmation");
    signals.ConfirmLocalCompletion();
    Require(signals.HasSentTurnAllComplete() && signals.HasReceivedTurnAllComplete(3),
        "Confirmed local completion did not publish all-complete");
    Require(!signals.HasReceivedTurnAllComplete(2),"All-complete confirmation escaped local participant gating");
    ++turn;
    Require(!signals.CivsProcessed() && !signals.LocalPlayerProcessed(),"Prior-turn barriers satisfied the next turn");
    Require(!signals.HasSentTurnComplete() && !signals.HasReceivedTurnComplete(3),"Prior-turn completion satisfied the next turn");
    Require(!signals.HasSentTurnAllComplete() && !signals.HasReceivedTurnAllComplete(3),
        "Prior-turn all-complete satisfied the next turn");
    signals.AcknowledgeCivs();
    signals.AcknowledgeLocalPlayer();
    signals.SendTurnComplete();
    signals.ConfirmLocalCompletion();
    Require(signals.CivsProcessed() && signals.LocalPlayerProcessed() && signals.HasReceivedTurnComplete(3) &&
        signals.HasReceivedTurnAllComplete(3),
        "Current-turn acknowledgements failed after advancing the SDK turn");
    signals.Unbind();
    signals.Unbind();
    RequireThrows<std::logic_error>([&]{signals.CivsProcessed();},"Unbound turn query was accepted");
    RequireThrows<std::logic_error>([&]{signals.AcknowledgeLocalPlayer();},"Unbound acknowledgement was accepted");
    RequireThrows<std::logic_error>([&]{signals.SendTurnComplete();},"Unbound completion send was accepted");
    RequireThrows<std::logic_error>([&]{signals.HasReceivedTurnComplete(3);},"Unbound participant query was accepted");
    RequireThrows<std::logic_error>([&]{signals.ConfirmLocalCompletion();},"Unbound completion confirm was accepted");
    RequireThrows<std::logic_error>([&]{signals.HasSentTurnAllComplete();},"Unbound all-complete query was accepted");
    RequireThrows<std::logic_error>([&]{signals.CancelTurnComplete();},"Unbound completion cancel was accepted");
}

void TestRebindStartsFreshSession(){
    LocalTurnSignals signals;
    int turn=6;
    signals.Bind([&turn]{return turn;},4);
    signals.AcknowledgeCivs();
    signals.AcknowledgeLocalPlayer();
    signals.SendTurnComplete();
    signals.ConfirmLocalCompletion();
    Require(signals.CivsProcessed() && signals.LocalPlayerProcessed() && signals.HasReceivedTurnComplete(4),
        "First session acknowledgement setup failed");
    Require(signals.HasReceivedTurnAllComplete(4),"First session all-complete setup failed");
    signals.Unbind();
    signals.Bind([&turn]{return turn;},7);
    Require(!signals.CivsProcessed() && !signals.LocalPlayerProcessed() && !signals.HasSentTurnComplete() &&
        !signals.HasSentTurnAllComplete(),
        "Rebind reused same-turn acknowledgements from the prior session");
    Require(!signals.HasReceivedTurnComplete(4) && !signals.HasReceivedTurnComplete(7) &&
        !signals.HasReceivedTurnAllComplete(4) && !signals.HasReceivedTurnAllComplete(7),
        "Rebind reused a prior participant completion");
    signals.SendTurnComplete();
    Require(signals.HasReceivedTurnComplete(7) && !signals.HasReceivedTurnComplete(4) &&
        !signals.HasReceivedTurnAllComplete(7),
        "Rebound session did not update its local participant");
    signals.Unbind();
}

void TestCompletionConfirmationAndCancellation(){
    LocalTurnSignals signals;
    int turn=0;
    signals.Bind([&turn]{return turn;},2);
    signals.AcknowledgeCivs();
    signals.AcknowledgeLocalPlayer();
    RequireThrows<std::logic_error>([&]{signals.ConfirmLocalCompletion();},
        "All-complete was confirmed without a completion acknowledgement");
    signals.CancelTurnComplete();
    Require(!signals.HasSentTurnComplete() && !signals.HasSentTurnAllComplete(),
        "No-op cancellation changed empty completion state");
    signals.SendTurnComplete();
    Require(signals.HasSentTurnComplete() && !signals.HasSentTurnAllComplete(),
        "Completion acknowledgement was not separate from confirmation");
    signals.ConfirmLocalCompletion();
    Require(signals.HasSentTurnAllComplete(),"Valid completion acknowledgement could not be confirmed");
    signals.ConfirmLocalCompletion();
    Require(signals.HasReceivedTurnAllComplete(2),"Repeated confirmation was not idempotent");
    signals.CancelTurnComplete();
    Require(!signals.HasSentTurnComplete() && !signals.HasReceivedTurnComplete(2) &&
        !signals.HasSentTurnAllComplete() && !signals.HasReceivedTurnAllComplete(2),
        "Cancellation did not clear both per-turn completion signals");
    Require(signals.CivsProcessed() && signals.LocalPlayerProcessed(),
        "Cancellation changed unrelated processing acknowledgements");
    RequireThrows<std::logic_error>([&]{signals.ConfirmLocalCompletion();},
        "Cancelled acknowledgement remained confirmable");
    signals.SendTurnComplete();
    signals.ConfirmLocalCompletion();
    ++turn;
    Require(!signals.HasSentTurnComplete() && !signals.HasSentTurnAllComplete(),
        "Next turn inherited either completion signal");
    signals.Unbind();
}

void TestCallbackLifetimeAndReentrantBinding(){
    LocalTurnSignals signals;
    auto lifetime=std::make_shared<int>(91);
    std::weak_ptr<int> weak=lifetime;
    auto callbackLifetime=lifetime;
    int recursiveQueries=0,bindRejections=0;
    signals.Bind([&,callbackLifetime]{
        Require(*callbackLifetime==91,"Turn callback capture changed");
        try{(void)signals.CivsProcessed();}catch(const std::logic_error&){++recursiveQueries;}
        signals.Unbind();
        Require(!weak.expired(),"Unbind destroyed the executing turn callback");
        try{signals.Bind([]{return 0;},2);}catch(const std::logic_error&){++bindRejections;}
        return 9;
    },1);
    lifetime.reset();
    callbackLifetime.reset();
    RequireThrows<std::logic_error>([&]{signals.AcknowledgeCivs();},"Callback-time Unbind result was accepted");
    Require(recursiveQueries==1 && bindRejections==1,"Callback reentrancy was not rejected");
    Require(weak.expired(),"Turn callback target remained alive after invocation returned");
    RequireThrows<std::logic_error>([&]{signals.CivsProcessed();},"Callback-time Unbind left a bound session");
    signals.Bind([]{return 9;},5);
    Require(!signals.CivsProcessed() && !signals.HasSentTurnComplete(),"Post-callback Bind reused old session signals");
    signals.AcknowledgeCivs();
    Require(signals.CivsProcessed(),"Rebind after callback Unbind failed");
    signals.Unbind();

    LocalTurnSignals directBind;
    directBind.Bind([&directBind,&bindRejections]{
        try{directBind.Bind([]{return 1;},0);}catch(const std::logic_error&){++bindRejections;}
        return 1;
    },0);
    Require(directBind.CivsProcessed()==false,"Turn callback side effect changed acknowledgement state");
    Require(bindRejections==2,"Bind while an existing turn source was active was accepted");
    directBind.Unbind();
}

void TestCallbackExceptionRecovery(){
    LocalTurnSignals signals;
    int calls=0;
    signals.Bind([&calls]()->int{
        if(++calls==1)throw std::runtime_error("turn source failure");
        return 2;
    },0);
    RequireThrows<std::runtime_error>([&]{signals.AcknowledgeCivs();},"Turn source exception was swallowed");
    Require(!signals.CivsProcessed(),"Failed turn source set a civ acknowledgement");
    signals.AcknowledgeCivs();
    Require(signals.CivsProcessed(),"Callback guard did not recover after an exception");
    signals.Unbind();

    LocalTurnSignals invalid;
    invalid.Bind([]{return -1;},0);
    RequireThrows<std::logic_error>([&]{invalid.SendTurnComplete();},"Invalid negative SDK turn was accepted");
    invalid.Unbind();
}
}

int main(){
    try{
        TestTurnTaggedAcksAndParticipant();
        TestRebindStartsFreshSession();
        TestCompletionConfirmationAndCancellation();
        TestCallbackLifetimeAndReentrantBinding();
        TestCallbackExceptionRecovery();
        std::printf("LOCAL_TURN_SIGNALS_PASS checks=%d GAMECORE_LOADED=false\n",checks);
        return 0;
    }catch(const std::exception& error){
        std::fprintf(stderr,"LOCAL_TURN_SIGNALS_FAIL checks=%d reason=%s\n",checks,error.what());
        return 1;
    }
}
