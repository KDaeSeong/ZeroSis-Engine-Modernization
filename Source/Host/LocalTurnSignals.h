#pragma once
#include <cstdint>
#include <functional>
#include <memory>
#include <stdexcept>
#include <utility>

namespace ZeroSisHost {
// Single local participant: acknowledgements are tagged with the SDK's current
// game turn and binding session. No signal changes game or player state.
class LocalTurnSignals final {
public:
    void Bind(std::function<int()> turn,int localPlayer){
        if(querying_)throw std::logic_error("Local turn signals cannot bind from their turn callback");
        if(binding_ || !turn || localPlayer<0)
            throw std::logic_error("Local turn signals require one SDK turn source and local player");
        const auto binding=std::make_shared<Binding>(std::move(turn),localPlayer);
        ResetAcknowledgements();
        AdvanceSession();
        binding_=binding;
    }

    // Unbind is idempotent. An in-flight callback keeps its target alive, but
    // its result is rejected because the binding session has ended.
    void Unbind() noexcept {
        binding_.reset();
        ResetAcknowledgements();
        AdvanceSession();
    }

    void AcknowledgeCivs(){const auto now=Current();civsTurn_=now.turn;civsSession_=now.session;}
    void AcknowledgeLocalPlayer(){const auto now=Current();playerTurn_=now.turn;playerSession_=now.session;}
    bool CivsProcessed() const {const auto now=Current();return civsSession_==now.session && civsTurn_==now.turn;}
    bool LocalPlayerProcessed() const {const auto now=Current();return playerSession_==now.session && playerTurn_==now.turn;}
    void SendTurnComplete(){const auto now=Current();completeTurn_=now.turn;completeSession_=now.session;}
    bool HasSentTurnComplete() const {const auto now=Current();return completeSession_==now.session && completeTurn_==now.turn;}
    bool HasReceivedTurnComplete(int player) const {
        const auto now=Current();
        return player==now.localPlayer && completeSession_==now.session && completeTurn_==now.turn;
    }
    void ConfirmLocalCompletion(){
        const auto now=Current();
        if(completeSession_!=now.session || completeTurn_!=now.turn)
            throw std::logic_error("Local turn completion cannot be confirmed before its acknowledgement");
        allCompleteTurn_=now.turn;allCompleteSession_=now.session;
    }
    bool HasSentTurnAllComplete() const {
        const auto now=Current();return allCompleteSession_==now.session && allCompleteTurn_==now.turn;
    }
    bool HasReceivedTurnAllComplete(int player) const {
        const auto now=Current();
        return player==now.localPlayer && allCompleteSession_==now.session && allCompleteTurn_==now.turn;
    }
    void CancelTurnComplete(){
        const auto now=Current();
        if(completeSession_==now.session && completeTurn_==now.turn){completeSession_=0;completeTurn_=-1;}
        if(allCompleteSession_==now.session && allCompleteTurn_==now.turn){allCompleteSession_=0;allCompleteTurn_=-1;}
    }

private:
    struct Binding {
        Binding(std::function<int()> callback,int player):turn(std::move(callback)),localPlayer(player){}
        std::function<int()> turn;
        int localPlayer;
    };
    struct CurrentTurn {
        int turn;
        int localPlayer;
        std::uint64_t session;
    };
    class QueryScope final {
    public:
        explicit QueryScope(const LocalTurnSignals& owner):owner_(owner){owner_.querying_=true;}
        ~QueryScope(){owner_.querying_=false;}
        QueryScope(const QueryScope&)=delete;
        QueryScope& operator=(const QueryScope&)=delete;
    private:
        const LocalTurnSignals& owner_;
    };

    CurrentTurn Current() const {
        if(querying_)throw std::logic_error("Reentrant local turn query is unsupported");
        const auto binding=binding_;
        if(!binding)throw std::logic_error("Local turn signals are not bound to the SDK");
        const std::uint64_t session=session_;
        QueryScope scope(*this);
        const int turn=binding->turn();
        if(binding_!=binding || session_!=session)
            throw std::logic_error("Local turn signal session changed during SDK query");
        if(turn<0)throw std::logic_error("Invalid SDK turn for local signals");
        return CurrentTurn{turn,binding->localPlayer,session};
    }

    void ResetAcknowledgements() noexcept {
        civsTurn_=playerTurn_=completeTurn_=allCompleteTurn_=-1;
        civsSession_=playerSession_=completeSession_=allCompleteSession_=0;
    }
    void AdvanceSession() noexcept {++session_;}

    std::shared_ptr<const Binding> binding_;
    std::uint64_t session_=0;
    int civsTurn_=-1,playerTurn_=-1,completeTurn_=-1,allCompleteTurn_=-1;
    std::uint64_t civsSession_=0,playerSession_=0,completeSession_=0,allCompleteSession_=0;
    mutable bool querying_=false;
};
}
