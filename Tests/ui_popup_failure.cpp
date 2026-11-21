// The verifier injects exact extracted UiPopupContext method bodies here.
// Fake SDK/script adapters test native recovery policy, not GameCore behavior.
#include <array>
#include <cstdio>
#include <cstring>
#include <exception>
#include <functional>
#include <iostream>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

struct lua_State { int integer=0; };
using lua_CFunction=int(*)(lua_State*);
using lua_Hook=void(*)(lua_State*,void*);
static constexpr int LUA_MASKCOUNT=8;
static void lua_sethook(lua_State*,lua_Hook,int,int) {}
static int lua_gettop(lua_State*) { return 2; }
static int Integer(lua_State* state,int) { return state->integer; }

@@TIMER_STATE@@

struct FakeGame {
    int increments=0,decrements=0,turn=1;
    bool throwIncrement=false,throwDecrement=false,mutateBeforeThrow=false;
    void EndTurnTimerSemaphoreIncrement(){
        ++increments;
        if(throwIncrement){if(mutateBeforeThrow)++decrements;throw std::runtime_error("increment SDK failure");}
    }
    void EndTurnTimerSemaphoreDecrement(){
        ++decrements;
        if(throwDecrement){if(mutateBeforeThrow)--decrements;throw std::runtime_error("decrement SDK failure");}
    }
    int GetGameTurn() const { return turn; }
};

struct FakeHost {
    bool popupVisible=false;
    std::function<void()> addPopup,closeInformationalPopup;
    std::vector<std::string> records;
    void Record(const std::string& value){records.push_back(value);}
};

struct FakeScripts {
    bool callbackSuccess=false,quiescent=true;
    int calls=0,frees=0;
    std::string error="INJECTED_ORIGINAL_SCRIPT_FAILURE";
    bool CallCFunction(lua_State* state,lua_CFunction function,void* argument){
        ++calls;
        if(!callbackSuccess)return false;
        (void)argument;
        return function(state)==0;
    }
    const char* LastError() const { return error.c_str(); }
    bool IsQuiescent() const { return quiescent; }
    void FreeLuaThread(lua_State*) { ++frees; }
};

struct UiPopupFailureFixture {
    FakeHost host_;
    FakeScripts scripts_;
    std::unique_ptr<FakeGame> game_{new FakeGame};
    std::unique_ptr<int> pregame_{new int(1)};
    lua_State* vm_=new lua_State;
    unsigned sequence_=4,instructions_=0;
    TimerState timerState_=TimerState::Released;
    bool active_=false,dispatching_=false,faulted_=false,timerRecoveryFailed_=false;
    void Require() const {}
    static void Budget(lua_State*,void*) {}
    static int Close(lua_State*) { return 0; }
    void WriteSnapshot(const char*) {}

    int NativeTimer(lua_State* state){
        auto& self=*this;
        const char* operation="timer";
@@TIMER_BLOCK@@
        throw std::logic_error("Unbalanced native UI timer request");
    }

@@CLOSE_METHOD@@
@@CALL_METHOD@@
@@FAULT_METHOD@@
@@STOP_METHOD@@
};

static void check(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}

int main(){
    int checks=0;
    try{
        // A shown-handler error occurs while the Lua timer is held. Call must
        // preserve the original error and make exactly one native compensation.
        {
            UiPopupFailureFixture f;
            lua_State state;state.integer=1;
            f.NativeTimer(&state);f.active_=true;f.host_.popupVisible=true;
            bool preserved=false;
            try{f.Call(&UiPopupFailureFixture::Close,nullptr);}
            catch(const std::runtime_error& e){preserved=std::string(e.what())=="INJECTED_ORIGINAL_SCRIPT_FAILURE";}
            check(preserved,"shown original error was not preserved");
            check(f.timerState_==TimerState::Released && f.game_->increments==1 && f.game_->decrements==1,
                  "shown failure did not balance timer exactly once");
            check(f.faulted_ && !f.active_ && !f.host_.popupVisible,"shown failure did not latch/close state");
            ++checks;
            f.Stop();
            check(f.vm_==nullptr && f.scripts_.frees==1,"Stop did not free a balanced faulted VM");
            ++checks;
        }

        // A processed-handler error happens after Lua has released the timer.
        // Recovery must keep the first failure and must not decrement again.
        {
            UiPopupFailureFixture f;
            lua_State state;state.integer=1;f.NativeTimer(&state);state.integer=-1;f.NativeTimer(&state);
            f.active_=true;
            bool preserved=false;
            try{f.Call(&UiPopupFailureFixture::Close,nullptr);}
            catch(const std::runtime_error& e){preserved=std::string(e.what())=="INJECTED_ORIGINAL_SCRIPT_FAILURE";}
            check(preserved && f.game_->decrements==1 && f.timerState_==TimerState::Released,
                  "processed failure retried decrement or lost the original error");
            ++checks;
            f.Stop();
            check(f.scripts_.frees==1,"processed Stop did not dispose balanced faulted VM");
            ++checks;
        }

        // If the SDK timer call throws during recovery, its pre-call unknown
        // state forbids retry and Stop refuses to destroy an uncertain session.
        {
            UiPopupFailureFixture f;
            lua_State state;state.integer=1;f.NativeTimer(&state);f.active_=true;
            f.game_->throwDecrement=true;
            bool preserved=false;
            try{f.Call(&UiPopupFailureFixture::Close,nullptr);}
            catch(const std::runtime_error& e){preserved=std::string(e.what())=="INJECTED_ORIGINAL_SCRIPT_FAILURE";}
            check(preserved && f.timerState_==TimerState::TransitionUnknown && f.timerRecoveryFailed_,
                  "recovery SDK failure did not preserve original error/uncertainty");
            const int decrements=f.game_->decrements;
            bool refused=false;
            try{f.Stop();}catch(const std::runtime_error&){refused=true;}
            check(refused && f.game_->decrements==decrements && f.scripts_.frees==0 && f.vm_!=nullptr,
                  "uncertain cleanup retried or freed VM");
            ++checks;
        }

        // A native decrement can throw before Lua's callback reports failure.
        // Keep the transition unknown and never issue a second decrement.
        {
            UiPopupFailureFixture f;
            lua_State state;state.integer=1;f.NativeTimer(&state);
            f.game_->throwDecrement=true;
            bool threw=false;
            try{state.integer=-1;f.NativeTimer(&state);}catch(const std::runtime_error& e){threw=std::string(e.what())=="decrement SDK failure";}
            check(threw && f.timerState_==TimerState::TransitionUnknown,"native timer exception did not mark transition unknown");
            const int decrements=f.game_->decrements;
            f.Fault();
            bool refused=false;try{f.Stop();}catch(const std::runtime_error&){refused=true;}
            check(refused && f.game_->decrements==decrements && f.scripts_.frees==0,
                  "unknown native transition was retried during cleanup");
            ++checks;
        }

        std::cout<<"UI_POPUP_FAILURE_COMPONENT_PASS checks="<<checks<<" GAMECORE_LOADED=false\n";
        return 0;
    }catch(const std::exception& e){std::cerr<<"UI_POPUP_FAILURE_COMPONENT_FAIL: "<<e.what()<<"\n";return 2;}
}
