#pragma once
#include "HostServices.h"
#include "NativeSaveArchive.h"
#include <FireWorks/FMemoryStream.h>
#include <cstdint>

namespace ZeroSisHost {
struct MenuLifecycleEndGame final {
    int owner=-1,turn=-1,winner=-1,victory=-1,finalScore=0;
    std::uint64_t generation=0;
    std::wstring replayPath,scorePath;
    std::vector<unsigned char> replay;
    // A local victory record is distinct from Steam/online leaderboards.
    bool localVictoryRecorded=false,platformLeaderboardAvailable=false;
};

// Used only through bound host adapters while the outgoing Core is still
// alive. Retained presentation receives an owned packet after callbacks finish.
class MenuLifecycleRetirement final {
public:
    MenuLifecycleRetirement(ICvGameContext3& context,HostState& host,std::wstring directory)
        :context_(context),host_(host),directory_(std::move(directory)){}
    void Prepare(int owner,int turn,std::uint64_t generation){
        RequireOwner();
        if(prepared_ || owner<0 || owner>=MAX_PLAYERS || turn<0 || !generation ||
           host_.autoSaveRunning || !host_.scripts || !host_.scripts->IsQuiescent() || !host_.localCommands.IsQuiescent())
            throw std::logic_error("Retirement requires one settled generation-bound local callback");
        std::unique_ptr<ICvGame1> game(context_.GetGame());
        std::unique_ptr<ICvPlayer1> player(game?game->GetPlayer(static_cast<PlayerTypes>(owner)):nullptr);
        if(!game || !player || !game->IsFinalInitialized() || game->IsGameMultiPlayer() ||
           game->GetGameState()!=GAMESTATE_ON || game->GetActivePlayer()!=owner || game->GetGameTurn()!=turn ||
           !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive())
            throw std::logic_error("Retirement lost its initialized active human game");
        packet_.owner=owner;packet_.turn=turn;packet_.generation=generation;
        const auto stem=L"\\retirement-"+std::to_wstring(generation)+L"-turn-"+std::to_wstring(turn);
        packet_.replayPath=directory_+stem+L".Civ5Replay";packet_.scorePath=directory_+stem+L"-score.json";
        // Verify actual export and private-directory persistence before the
        // SDK mutates GAMESTATE_OVER. SaveReplay overwrites this preflight
        // with the genuine final replay after the SDK adds its final message.
        const auto bytes=ExportReplay(*game);Persist(packet_.replayPath,bytes);
        prepared_=true;
    }
    bool SaveReplay(){
        RequirePrepared();auto game=Game();
        if(game->GetGameState()!=GAMESTATE_OVER || replayWritten_)
            throw std::logic_error("Final replay requires one SDK game-over transition");
        auto bytes=ExportReplay(*game);Persist(packet_.replayPath,bytes);
        packet_.replay=std::move(bytes);replayWritten_=true;return true;
    }
    bool RecordVictoryInformation(int score){
        RequirePrepared();auto game=Game();
        if(!replayWritten_ || packet_.localVictoryRecorded || game->GetGameState()!=GAMESTATE_OVER)
            throw std::logic_error("Local victory record requires the persisted final replay");
        std::unique_ptr<ICvPlayer1> player(game->GetPlayer(static_cast<PlayerTypes>(packet_.owner)));
        if(!player)throw std::runtime_error("Final score player is missing");
        const int actual=player->GetScore(true,game->GetActiveTeam()==game->GetWinner());
        if(score!=actual)throw std::runtime_error("SDK final score differs from the victory callback");
        packet_.winner=static_cast<int>(game->GetWinner());packet_.victory=static_cast<int>(game->GetVictory());packet_.finalScore=score;
        const auto text=std::string("{\"schema\":\"zerosis.private_retirement_score.v1\",\"owner\":")+
            std::to_string(packet_.owner)+",\"turn\":"+std::to_string(packet_.turn)+",\"generation\":"+
            std::to_string(packet_.generation)+",\"winner\":"+std::to_string(packet_.winner)+",\"victory\":"+
            std::to_string(packet_.victory)+",\"finalScore\":"+std::to_string(score)+
            ",\"platformLeaderboardAvailable\":false}";
        Persist(packet_.scorePath,{text.begin(),text.end()});packet_.localVictoryRecorded=true;return true;
    }
    bool RecordLeaderboardScore(int score){
        RequirePrepared();
        if(!packet_.localVictoryRecorded || score!=packet_.finalScore)
            throw std::logic_error("Leaderboard callback lost the recorded final score");
        // No platform provider is bound in this offline host. Returning false
        // preserves that capability result instead of reporting a fake upload.
        return false;
    }
    void OpenEndGameMenu(){
        RequirePrepared();auto game=Game();
        if(game->GetGameState()!=GAMESTATE_OVER || !replayWritten_ || !packet_.localVictoryRecorded || endGameQueued_)
            throw std::logic_error("End-game presentation requires one completed replay and final-score sequence");
        endGameQueued_=true;
    }
    bool Pending() const noexcept {return endGameQueued_ && !taken_;}
    MenuLifecycleEndGame Take(){
        RequirePrepared();
        if(!Pending() || !host_.scripts || !host_.scripts->IsQuiescent() || !host_.localCommands.IsQuiescent())
            throw std::logic_error("End-game packet may leave only after SDK and Lua callbacks finish");
        taken_=true;return std::move(packet_);
    }
private:
    void RequireOwner() const {
        if(host_.gameThread!=GetCurrentThreadId() || !host_.gameLock.HeldByCurrentThread())
            throw std::logic_error("Retirement provider requires the GameCore owner lock");
    }
    void RequirePrepared() const {RequireOwner();if(!prepared_ || taken_)throw std::logic_error("Retirement provider is not armed");}
    std::unique_ptr<ICvGame1> Game(){
        std::unique_ptr<ICvGame1> game(context_.GetGame());
        if(!game || game->IsGameMultiPlayer() || game->GetActivePlayer()!=packet_.owner || game->GetGameTurn()!=packet_.turn)
            throw std::logic_error("Retirement provider lost its active owner or turn");
        return game;
    }
    static std::vector<unsigned char> ExportReplay(ICvGame1& game){
        FMemoryStream stream;game.WriteReplay(stream);
        if(stream.GetEOF()<8 || stream.GetEOF()>64u*1024u*1024u || stream.GetPosition()!=stream.GetEOF())
            throw std::runtime_error("SDK replay export is incomplete or exceeds its bound");
        const auto* bytes=reinterpret_cast<const unsigned char*>(stream.GetBuf());return {bytes,bytes+stream.GetEOF()};
    }
    static void Persist(const std::wstring& path,const std::vector<unsigned char>& bytes){
        if(bytes.empty() || bytes.size()>64u*1024u*1024u)throw std::invalid_argument("Retirement artifact exceeds its byte bound");
        // NativeSaveArchive::WriteAtomic validates the .zssave envelope. Replay
        // and score files deliberately use the transaction, not that format.
        NativeSaveTransaction output(path);std::size_t at=0;
        while(at<bytes.size()){
            const auto count=static_cast<DWORD>(std::min<std::size_t>(bytes.size()-at,1024u*1024u));DWORD written=0;
            if(!WriteFile(output.Get(),bytes.data()+at,count,&written,nullptr) || !written || written>count)
                throw std::runtime_error("Retirement artifact write was incomplete");
            at+=written;
        }
        output.Commit();ReadFileHandle input(path);LARGE_INTEGER size;
        if(!GetFileSizeEx(input.Get(),&size) || size.QuadPart!=static_cast<LONGLONG>(bytes.size()))
            throw std::runtime_error("Retirement artifact persisted a different byte count");
        std::vector<unsigned char> actual(bytes.size());at=0;
        while(at<actual.size()){
            const auto count=static_cast<DWORD>(std::min<std::size_t>(actual.size()-at,1024u*1024u));
            const auto read=input.Read(actual.data()+at,count);
            if(!read || read>count)throw std::runtime_error("Retirement artifact readback was truncated");
            at+=read;
        }
        if(actual!=bytes)throw std::runtime_error("Retirement artifact readback differs from the exported bytes");
    }
    ICvGameContext3& context_;HostState& host_;std::wstring directory_;MenuLifecycleEndGame packet_;
    bool prepared_=false,replayWritten_=false,endGameQueued_=false,taken_=false;
};
}
