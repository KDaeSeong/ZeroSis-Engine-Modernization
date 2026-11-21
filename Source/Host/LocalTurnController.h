#pragma once
#include "HostServices.h"

namespace ZeroSisHost {
// Transport for a single local human. Completion is committed only after the
// SDK accepted a user command and the local command queue has drained. Game
// counters, player activation and AI execution remain entirely inside the SDK.
class LocalTurnController final {
public:
    LocalTurnController(HostState& host,ICvGame1& game):host_(host),game_(game){
        if(game_.IsGameMultiPlayer() || host_.canAdvanceTurn || host_.beginTurnBoundary)
            throw std::logic_error("Local turn controller requires one single-player session");
        unsigned humans=0;
        for(int id=0;id<MAX_PLAYERS;++id){
            std::unique_ptr<ICvPlayer1> player(game_.GetPlayer(static_cast<PlayerTypes>(id)));
            if(!player)throw std::runtime_error("Missing local session player slot");
            if(player->IsAlive() && player->IsHuman()){
                ++humans;
                if(id!=game_.GetActivePlayer())throw std::logic_error("Remote human in local turn session");
            }
        }
        if(humans!=1)throw std::logic_error("Local turn transport requires exactly one live human");
        std::function<bool()> advance=[this](){return CanAdvance();};
        std::function<void()> boundary=[this](){
            if(!CanAdvance())throw std::logic_error("SDK turn boundary began before the local completion barrier");
            host_.Record("local-turn-boundary:"+std::to_string(game_.GetGameTurn()));
        };
        host_.canAdvanceTurn=std::move(advance);
        host_.beginTurnBoundary=std::move(boundary);
    }
    ~LocalTurnController(){host_.beginTurnBoundary=nullptr;host_.canAdvanceTurn=nullptr;}
    LocalTurnController(const LocalTurnController&)=delete;
    LocalTurnController& operator=(const LocalTurnController&)=delete;
    void CommitCompletion(){
        if(!host_.localCommands.IsQuiescent() || host_.autoSaveRunning ||
           !host_.turnSignals.HasSentTurnComplete() || !host_.turnSignals.CivsProcessed() ||
           !host_.turnSignals.LocalPlayerProcessed())
            throw std::logic_error("Local commands are not ready for turn completion");
        host_.turnSignals.ConfirmLocalCompletion();
        host_.Record("local-turn-all-complete:"+std::to_string(game_.GetGameTurn()));
    }
private:
    bool CanAdvance() const {
        return !game_.IsGameMultiPlayer() && game_.GetNumGameTurnActive()==0 &&
            host_.turnSignals.HasSentTurnAllComplete() && host_.localCommands.IsQuiescent() &&
            !host_.autoSaveRunning;
    }
    HostState& host_;
    ICvGame1& game_;
};
}
