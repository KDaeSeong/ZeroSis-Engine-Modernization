#pragma once
#include <cstdint>
#include <stdexcept>
#include <utility>
#include <vector>

namespace ZeroSisHost {
// The outer host owns this state across destruction of the gameplay window,
// UI, SDK wrappers and GameCore module. It retains only host-owned bytes.
class MenuLifecycle final {
public:
    enum class Destination { None,MainMenu,Restart,ExitProcess };
    struct Identity {int owner=-1,turn=-1;std::uint64_t generation=0;};
    struct Request {Destination destination=Destination::None;Identity identity;};
    void BeginGame(Identity identity){
        if(attached_ || pending_ || identity.owner<0 || identity.turn<0 || !identity.generation || identity.generation<=generation_)
            throw std::logic_error("Lifecycle attachment requires a fresh game generation");
        identity_=identity;generation_=identity.generation;attached_=true;frontEnd_=false;
    }
    void Queue(Destination destination,Identity current,bool callbacksQuiescent,bool timerReleased){
        if(!attached_ || pending_ || destination==Destination::None || !callbacksQuiescent || !timerReleased ||
           current.owner!=identity_.owner || current.turn<identity_.turn || current.generation!=identity_.generation)
            throw std::logic_error("Lifecycle transition lost its completed owner callback or generation");
        request_={destination,current};pending_=true;
    }
    bool BlocksGameplay() const noexcept {return pending_;}
    const Request& Pending() const {if(!pending_)throw std::logic_error("No lifecycle handoff is pending");return request_;}
    Request AfterCoreUnloaded(bool windowGone,bool scriptsGone,bool moduleGone){
        if(!pending_ || !attached_ || !windowGone || !scriptsGone || !moduleGone)
            throw std::logic_error("Lifecycle handoff requires complete old-window and Core cleanup");
        auto result=request_;request_={};pending_=false;attached_=false;return result;
    }
    void EnterFrontEnd(bool viewReady){
        if(attached_ || pending_ || !viewReady)throw std::logic_error("Main menu requires its actual initialized front-end view");
        frontEnd_=true;
    }
    bool IsFrontEnd() const noexcept {return frontEnd_;}
private:
    Identity identity_;Request request_;std::uint64_t generation_=0;
    bool attached_=false,pending_=false,frontEnd_=false;
};
}
