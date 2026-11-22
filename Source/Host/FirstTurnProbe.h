#pragma once
#include "HostServices.h"
#include "SdkGameSave.h"
#include "LocalTurnController.h"
#include "LocalSdkSession.h"
#include "FixturePromotionInput.h"
#include "TurnBenchmarkObservation.h"
#include <algorithm>
#include <array>
#include <chrono>

namespace ZeroSisHost {
// Initialize the post-map host services through public SDK operations, then
// exercise Update without changing the turn or player activation directly.
class FirstTurnProbe final {
public:
    void Begin(ICvGameContext3& context,HostState& host,const std::wstring& directory,const std::wstring& bundle,bool turnCycle=false){
        if(started_)throw std::logic_error("First-turn startup requires a fresh session");
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread())
            throw std::logic_error("First-turn startup requires the GameCore owner lock");
        started_=true;
        std::unique_ptr<ICvGame1> game(context.GetGame());
        std::unique_ptr<ICvMap1> map(context.GetMap());
        std::unique_ptr<ICvNetMessageHandler1> messages(context.GetNetMessageHandler());
        if(!messages)throw std::runtime_error("GameCore did not provide its local command receiver");
        if(!game || !map)throw std::runtime_error("First-turn startup did not receive its game/map interfaces");
        LocalSdkSession localSession(host,*messages,*game,context);
        SdkGameSave saves(context,host,directory,bundle);
        std::puts("FIRST_TURN_PLAYER_OPTIONS_SOURCE=SDK_DATABASE_DEFAULTS");
        if(game)Observe(*game,"before-start");
        if(!game || !map || !game->IsFinalInitialized() || game->GetGameTurn()!=0 ||
           game->GetElapsedGameTurns()!=0 || game->GetNumGameTurnActive()!=1 ||
           game->IsGameMultiPlayer() || game->GetActivePlayer()!=static_cast<PlayerTypes>(0) || map->NumPlots()<=0)
            throw std::logic_error("First-turn probe requires the configured fresh single-player game");
        std::puts("FIRST_TURN_PHASE=initialize_tactical_map");
        game->InitTacticalAnalysisMap(map->NumPlots());
        std::puts("FIRST_TURN_PHASE=initialize_player_plots");
        for(int id=0;id<MAX_PLAYERS;++id){
            std::unique_ptr<ICvPlayer1> player(game->GetPlayer(static_cast<PlayerTypes>(id)));
            if(!player || player->GetID()!=id)throw std::runtime_error("Missing initial player slot");
            player->LaterInit();
        }
        std::puts("FIRST_TURN_PHASE=game_started");
        game->DoGameStarted();
        std::unique_ptr<ICvPlayer1> local(game->GetPlayer(game->GetActivePlayer()));
        if(!local || !local->IsAlive() || !local->IsHuman() || !local->IsTurnActive())
            throw std::logic_error("The SDK did not activate the initial human player");
        std::puts("FIRST_TURN_PHASE=observe_initial_player");
        RequireWaiting(*game,*local);
        Observe(*game,"after-startup");
        std::puts("FIRST_TURN_PHASE=idle_updates");
        for(int update=0;update<3;++update){
            game->Update();
            if(!host.localCommands.IsQuiescent())throw std::runtime_error("GameCore left a local message bundle incomplete");
            if(host.scripts && *host.scripts->LastError())throw std::runtime_error(host.scripts->LastError());
            RequireWaiting(*game,*local);++updates_;
        }
        if(saves.Count()!=1)throw std::runtime_error("The SDK initial autosave was not persisted exactly once");
        const auto events=host.Events();
        const auto starts=std::count(events.begin(),events.end(),"ui-player-turn-status:0:0:");
        const auto localStarts=std::count(events.begin(),events.end(),"ui-active-player-turn-start");
        if(starts!=1 || localStarts!=1 ||
           std::find(events.begin(),events.end(),"ui-active-player-turn-end")!=events.end())
            throw std::runtime_error("Initial human turn notification sequence differs");
        if(!host.turnSignals.CivsProcessed() || !host.turnSignals.LocalPlayerProcessed() ||
           host.turnSignals.HasSentTurnComplete() ||
           std::count(events.begin(),events.end(),"local-ai-civs-processed")!=1 ||
           std::count(events.begin(),events.end(),"local-player-initial-ai-processed")!=1 ||
           std::count(events.begin(),events.end(),"local-turn-reminders-flush:0")!=3)
            throw std::runtime_error("Initial SDK turn acknowledgements differ");
        std::puts("FIRST_TURN_SIGNALS=1,1,0,3");
        values_={{game->GetGameTurn(),game->GetElapsedGameTurns(),static_cast<int>(game->GetActivePlayer()),
            game->GetNumGameTurnActive(),game->CountNumHumanGameTurnActive(),updates_}};
        Observe(*game,"waiting-for-input");ready_=true;
        if(turnCycle)AdvanceOneTurn(*game,*local,host);
    }
    std::string Observation() const {
        if(!ready_)throw std::logic_error("First-turn startup has not completed");
        std::string result="FIRST_TURN_OBSERVATION=";
        for(std::size_t i=0;i<values_.size();++i){if(i)result+=",";result+=std::to_string(values_[i]);}
        return result;
    }
    static void AdvanceOneTurn(ICvGame1& game,ICvPlayer1& local,HostState& host,const char* prefix="TURN_CYCLE",int expectedUnitCount=2,bool fixturePromotions=false,bool fixtureUnitActions=false){
        if(expectedUnitCount < -1)throw std::invalid_argument("Invalid expected fixture unit count");
        const bool benchmark=TurnBenchmarkObservation::Enabled();
        std::string nativeOrder;
        if(benchmark){
            int unitCount=0;
            nativeOrder=TurnBenchmarkObservation::UnitOrder(local,unitCount);
            if(expectedUnitCount>=0 && !std::getenv("ZEROSIS_BENCHMARK_HUMAN") && expectedUnitCount!=unitCount)
                throw std::runtime_error("Original fixture starting unit count differs");
            expectedUnitCount=unitCount;
            std::printf("%s_BENCH_BEGIN=%d|%lu\n",prefix,game.GetGameTurn(),TurnBenchmarkObservation::SyncSeed(game));
        }
        const auto turnStarted=std::chrono::steady_clock::now();
        const int begin=game.GetGameTurn();
        if(begin<0 || begin==INT_MAX || game.GetElapsedGameTurns()!=begin || !local.IsTurnActive())
            throw std::logic_error("Turn cycle requires the configured human waiting turn");
        const int end=begin+1;
        const auto previous=host.Events();
        LocalTurnController controller(host,game);
        auto& scripts=*host.scripts;
        struct Thread {
            ScriptSystem& scripts;lua_State* vm=nullptr;
            ~Thread(){if(vm)scripts.FreeLuaThread(vm);}
        } thread{scripts};
        thread.vm=scripts.CreateLuaThread("Local end-turn command");
        // A manual Next Turn input requires the SDK's wait-for-end-turn player
        // preference. Send the ordinary option command; never set UI readiness.
        host.localCommands.SendPlayerOption(PLAYEROPTION_WAIT_END_TURN,true);
        std::printf("%s_PLAYER_OPTION=PLAYEROPTION_WAIT_END_TURN:1\n",prefix);
        game.UpdateTestEndTurn();
        if(fixtureUnitActions && !fixturePromotions)throw std::invalid_argument("SDK unit actions require fixture promotion inputs");
        if(fixturePromotions)FixturePromotionInput::Apply(scripts,thread.vm,host,fixtureUnitActions);
        std::string skip=benchmark?"local skipped={}\n":"";
        skip+=R"lua(
local player=Players[Game.GetActivePlayer()]
local count=0
for unit in player:Units() do
    assert(unit:CanStartMission(MissionTypes.MISSION_SKIP,-1,-1,unit:GetPlot(),0))
    unit:PushMission(MissionTypes.MISSION_SKIP,-1,-1,0,0,1)
)lua";
        if(benchmark)skip+="    skipped[#skipped+1]=unit:GetID()\n";
        skip+=R"lua(
    count=count+1
end
assert(not player:HasReadyUnit(), 'Local skip commands did not exhaust ready units')
)lua";
        if(benchmark)skip+="\nZeroSisTurnBenchmarkSkips=table.concat(skipped,',')\n";
        if(expectedUnitCount>=0)
            skip+="\nassert(count=="+std::to_string(expectedUnitCount)+", 'Initial fixture unit count differs')\n";
        std::printf("%s_INPUT=MISSION_SKIP_EACH_UNIT_THEN_CONTROL_ENDTURN\n",prefix);
        if(!scripts.Execute(thread.vm,skip.data(),skip.size()))throw std::runtime_error(scripts.LastError());
        game.UpdateTestEndTurn();
        const char command[]="local p=Players[Game.GetActivePlayer()]; assert(Game.CanDoControl(ControlTypes.CONTROL_ENDTURN), 'End-turn blocked: '..p:GetEndTurnBlockingType()..' ready='..tostring(p:HasReadyUnit())..' busy='..tostring(p:HasBusyUnit())); Game.DoControl(ControlTypes.CONTROL_ENDTURN)";
        if(!scripts.Execute(thread.vm,command,sizeof(command)-1))throw std::runtime_error(scripts.LastError());
        controller.CommitCompletion();
        unsigned updates=0;
        for(;updates<256;++updates){
            game.Update();
            // This fixture explicitly closes supported informational popups
            // with their real Escape handler after recording the shown tree.
            // Decision popups remain unsupported and are never auto-selected.
            if(host.closeInformationalPopup)host.closeInformationalPopup();
            if(!host.localCommands.IsQuiescent() || *scripts.LastError())
                throw std::runtime_error("Turn update left incomplete commands or a script failure");
            if(game.GetGameTurn()==begin && !host.turnSignals.HasSentTurnComplete())
                throw std::runtime_error("The SDK cancelled the requested turn completion");
            std::printf("%s_STATE=%u|%d,%d,%d,%d,%d\n",prefix,updates+1,game.GetGameTurn(),game.GetElapsedGameTurns(),
                game.GetNumGameTurnActive(),game.CountNumHumanGameTurnActive(),local.IsTurnActive()?1:0);
            if(game.GetGameTurn()<begin || game.GetGameTurn()>end || game.GetElapsedGameTurns()!=game.GetGameTurn())
                throw std::runtime_error("SDK turn cycle advanced outside its one-turn boundary");
            if(game.GetGameTurn()==end && local.IsTurnActive())break;
        }
        if(updates==256 || game.GetNumGameTurnActive()!=1 || game.CountNumHumanGameTurnActive()!=1 ||
           !local.IsAlive() || !local.IsHuman() || host.turnSignals.HasSentTurnComplete() || host.turnSignals.HasSentTurnAllComplete())
            throw std::runtime_error("SDK did not return to the next human turn with fresh completion signals");
        const auto turnDurationUs=std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now()-turnStarted).count();
        if(benchmark)TurnBenchmarkObservation::End(game,host,thread.vm,prefix,previous.size(),nativeOrder);
        for(unsigned idle=0;idle<3;++idle){
            game.Update();
            if(game.GetGameTurn()!=end || game.GetElapsedGameTurns()!=end || !local.IsTurnActive() ||
               game.GetNumGameTurnActive()!=1 || game.CountNumHumanGameTurnActive()!=1 || *scripts.LastError())
                throw std::runtime_error("The next human turn advanced without a new input");
        }
        const auto events=host.Events();
        const auto delta=[&](const std::string& key){return std::count(events.begin(),events.end(),key)-std::count(previous.begin(),previous.end(),key);};
        if(delta("ui-active-player-turn-end")!=1 || delta("ui-active-player-turn-start")!=1 ||
           delta("new-game-turn:"+std::to_string(end))!=1 || delta("local-turn-boundary:"+std::to_string(begin))!=1)
            throw std::runtime_error("SDK turn boundary notifications differ");
        for(int id=0;id<MAX_PLAYERS;++id){
            std::unique_ptr<ICvPlayer1> player(game.GetPlayer(static_cast<PlayerTypes>(id)));
            if(!player || !player->IsAlive())continue;
            int cursor=0,units=0;
            std::unique_ptr<ICvUnit1> unit(player->FirstUnit(&cursor));
            while(unit){++units;unit.reset(player->NextUnit(&cursor));}
            std::printf("%s_PLAYER=%d,%d,%d,%d,%d\n",prefix,id,player->IsHuman()?1:0,
                player->IsTurnActive()?1:0,player->GetNumCities(),units);
        }
        std::printf("%s_OBSERVATION=%d,%d,%d,%d,1,1,%u,3\n",prefix,begin,end,game.GetElapsedGameTurns(),static_cast<int>(game.GetActivePlayer()),updates+1);
        std::printf("%s_DURATION_US=%lld\n",prefix,static_cast<long long>(turnDurationUs));
    }
private:
    static void RequireWaiting(ICvGame1& game,ICvPlayer1& local){
        if(game.GetGameTurn()!=0 || game.GetElapsedGameTurns()!=0 || game.GetNumGameTurnActive()!=1 ||
           game.CountNumHumanGameTurnActive()!=1 || !local.IsTurnActive() || !local.IsHuman() || !local.IsAlive())
            throw std::runtime_error("Human initial turn advanced or deactivated without completion input");
    }
    static void Observe(ICvGame1& game,const char* phase){
        std::printf("FIRST_TURN_STATE=%s|%d,%d,%d,%d,%d\n",phase,game.GetGameTurn(),game.GetElapsedGameTurns(),
            static_cast<int>(game.GetActivePlayer()),game.GetNumGameTurnActive(),game.CountNumHumanGameTurnActive());
    }
    std::array<int,6> values_{};
    int updates_=0;
    bool started_=false,ready_=false;
};
}
