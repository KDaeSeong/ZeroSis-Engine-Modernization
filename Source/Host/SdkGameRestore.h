#pragma once
#include "HostServices.h"
#include "NativeSaveArchive.h"
#include "NativeRestoreContract.h"
#include <FireWorks/FMemoryStream.h>

namespace ZeroSisHost {
class SdkGameRestore final {
public:
    static NativeSaveArchive Load(ICvGameContext3& context,HostState& host,const std::wstring& path,const std::wstring& bundle){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread() || host.loadedGame)
            throw std::logic_error("Restore requires a fresh owner-thread session");
        auto archive=NativeSaveArchive::Decode(NativeSaveArchive::Read(path));
        LoadArchive(context,host,archive,bundle);
        return archive;
    }
    static void LoadArchive(ICvGameContext3& context,HostState& host,const NativeSaveArchive& archive,const std::wstring& bundle){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread() || host.loadedGame)
            throw std::logic_error("Restore requires a fresh owner-thread session");
        std::puts("NATIVE_RESTORE_PHASE=verify_archive");
        archive.Validate();
        ReadFileHandle identity(bundle+L"\\bundle.manifest");std::array<unsigned char,16385> bytes{};
        const DWORD size=identity.Read(bytes.data(),static_cast<DWORD>(bytes.size()));
        if(!size || size==bytes.size() || archive.sections[0].bytes!=std::vector<unsigned char>(bytes.begin(),bytes.begin()+size))
            throw std::invalid_argument("Native save was produced by a different engine bundle");
        std::unique_ptr<ICvPreGame1> pregame(context.GetPreGame());
        std::unique_ptr<ICvGame1> game(context.GetGame());
        std::unique_ptr<ICvMap1> map(context.GetMap());
        if(!pregame || !game || !map || game->IsFinalInitialized() || map->NumPlots()!=0)
            throw std::logic_error("Restore cannot replace an initialized game");
        const auto profile=StateProfile(context);
        NativeRestoreContract::PreflightGame(archive.sections[2].bytes,profile);
        host.loadedGame=true;
        std::puts("NATIVE_RESTORE_PHASE=pregame");
        pregame->resetGame();pregame->resetPlayers();
        Read(archive.sections[1],[&](FDataStream& stream){pregame->read(stream,true);});
        pregame->setGameStartType(GAME_LOADED);
        if(pregame->gameType()!=GAME_SINGLE_PLAYER || pregame->gameTurn()!=archive.turn ||
           pregame->activePlayer()!=static_cast<PlayerTypes>(archive.activePlayer))
            throw std::runtime_error("Restored pregame identity differs from the save envelope");
        // Network identities are session data, not saved player fields. This
        // offline host retains the SDK pregame's unassigned transport IDs.
        for(int id=0;id<MAX_PLAYERS;++id){
            const int network=pregame->netID(static_cast<PlayerTypes>(id));
            if(network!=-1)throw std::runtime_error("An offline restore cannot import a transport assignment");
            host.assignedNetworkIds[static_cast<std::size_t>(id)]=network;
        }
        host.networkAssignmentsReady=true;
        const bool newRandomSeed=NewRandomSeed(*pregame,*game);
        std::puts("NATIVE_RESTORE_PHASE=game");
        Read(archive.sections[2],[&](FDataStream& stream){game->Read(stream);});
        if(NewRandomSeed(*pregame,*game)!=newRandomSeed)
            throw std::runtime_error("SDK restore changed the new-random-seed option");
        std::puts("NATIVE_RESTORE_PHASE=map");
        Read(archive.sections[3],[&](FDataStream& stream){map->Read(stream);});
        std::puts("NATIVE_RESTORE_PHASE=supporting");
        Read(archive.sections[4],[&](FDataStream& stream){game->ReadSupportingClassData(stream);});
        std::puts("NATIVE_RESTORE_PHASE=teams");
        for(unsigned id=0;id<MAX_TEAMS;++id){
            std::unique_ptr<ICvTeam1> team(context.GetTeam(static_cast<TeamTypes>(id)));
            if(!team)throw std::runtime_error("Restore did not receive an SDK team slot");
            Read(archive.sections[5+id],[&](FDataStream& stream){team->Read(stream);});
        }
        std::puts("NATIVE_RESTORE_PHASE=players");
        for(unsigned id=0;id<MAX_PLAYERS;++id){
            std::unique_ptr<ICvPlayer1> player(game->GetPlayer(static_cast<PlayerTypes>(id)));
            if(!player)throw std::runtime_error("Restore did not receive an SDK player slot");
            Read(archive.sections[5+MAX_TEAMS+id],[&](FDataStream& stream){player->Read(stream);});
            if(player->GetID()!=static_cast<int>(id))throw std::runtime_error("Restored SDK player ID differs");
        }
        unsigned humans=0;
        for(int id=0;id<MAX_PLAYERS;++id){
            std::unique_ptr<ICvPlayer1> player(game->GetPlayer(static_cast<PlayerTypes>(id)));
            if(!player || player->GetID()!=id)throw std::runtime_error("Restored player slot is missing");
            if(player->IsAlive() && player->IsHuman()){
                ++humans;
                if(id!=archive.activePlayer || !player->IsTurnActive())
                    throw std::runtime_error("Restored save does not contain the expected active human");
            }
        }
        const auto surface=host.mapSurface.Snapshot();
        if(!game->IsFinalInitialized() || game->GetGameTurn()!=archive.turn || game->GetElapsedGameTurns()!=archive.elapsed ||
           game->GetActivePlayer()!=static_cast<PlayerTypes>(archive.activePlayer) || game->IsGameMultiPlayer() ||
           humans!=1 || game->GetNumGameTurnActive()!=1 || game->CountNumHumanGameTurnActive()!=1 ||
           map->GetGridWidth()<=0 || map->GetGridHeight()<=0 ||
           static_cast<long long>(map->GetGridWidth())*map->GetGridHeight()!=map->NumPlots() ||
           !surface || surface->dirtyPlots.size()!=static_cast<std::size_t>(map->NumPlots()))
            throw std::runtime_error("Restored SDK game/map identity differs");
        std::printf("NATIVE_RESTORE_SECTIONS_READ=%u\n",static_cast<unsigned>(archive.sections.size()-1));
    }
    static unsigned VerifyRoundtrip(ICvGameContext3& context,const NativeSaveArchive& before,const NativeSaveArchive& after){
        before.Validate();after.Validate();
        const auto profile=StateProfile(context);
        const auto layout=NativeRestoreContract::PreflightGame(before.sections[2].bytes,profile);
        std::unique_ptr<ICvPreGame1> pregame(context.GetPreGame());
        std::unique_ptr<ICvGame1> game(context.GetGame());
        if(!pregame || !game || pregame->gameType()!=GAME_SINGLE_PLAYER || game->IsGameMultiPlayer())
            throw std::logic_error("Native restore comparison requires single-player SDK state");
        const bool newRandomSeed=NewRandomSeed(*pregame,*game);
        Localization::String text=Localization::Lookup("TXT_KEY_MISC_RELOAD");
        if(!text.PushArgument(layout.sessions+1))
            throw std::runtime_error("Cannot format the native restore replay message");
        const char* utf8=text.toUTF8();
        if(!utf8)throw std::runtime_error("Native restore replay text is unavailable");
        const std::string expectedReloadText(utf8);
        const unsigned equal=NativeRestoreContract::Verify(before,after,profile,newRandomSeed,expectedReloadText);
        std::printf("NATIVE_RESTORE_CONTRACT_VERIFIED=SOURCE_ORDER_V1|%u|%d|%u|%u|%d|%d\n",
            equal,before.turn,before.flags,after.flags,layout.sessions,newRandomSeed?1:0);
        return equal;
    }
private:
    static RetailSaveStateProfile StateProfile(ICvGameContext3& context){
        char text[32]={};
        if(!context.GetDefineSTRING(text,sizeof(text),"NUM_VICTORY_POINT_AWARDS",false) || !text[0])
            throw std::runtime_error("Native restore victory width is unavailable");
        std::uint32_t width=0;std::size_t at=0;
        for(;at<sizeof(text) && text[at];++at){
            if(text[at]<'0' || text[at]>'9')
                throw std::runtime_error("Native restore victory width is not decimal");
            const auto digit=static_cast<std::uint32_t>(text[at]-'0');
            if(width>(4096u-digit)/10u)
                throw std::runtime_error("Native restore victory width exceeds its profile limit");
            width=width*10u+digit;
        }
        if(at==sizeof(text))throw std::runtime_error("Native restore victory width is unterminated");
        return RetailSaveStateProfile(width);
    }
    static bool NewRandomSeed(ICvPreGame1& pregame,ICvGame1& game){
        int value=0;
        if(!pregame.GetGameOption(GAMEOPTION_NEW_RANDOM_SEED,value))
            throw std::runtime_error("Native restore new-random-seed option is unavailable");
        // CvGame::isOption uses equality to one, not general nonzero truth.
        const bool enabled=value==1;
        if(game.IsOption(GAMEOPTION_NEW_RANDOM_SEED)!=enabled)
            throw std::runtime_error("Native restore option differs from the SDK reader policy");
        return enabled;
    }
    template<class Reader> static void Read(const NativeSaveSection& section,Reader reader){
        FMemoryStream stream(static_cast<int>(section.bytes.size()),section.bytes.data(),false);
        try{reader(stream);}
        catch(const std::exception& error){
            throw std::runtime_error("SDK restore section "+std::to_string(section.kind)+":"+std::to_string(section.index)+
                " at "+std::to_string(stream.GetPosition())+": "+error.what());
        }
        if(stream.GetPosition()!=section.bytes.size() || stream.GetEOF()!=section.bytes.size())
            throw std::runtime_error("SDK restore did not consume its complete save section: "+
                std::to_string(section.kind)+":"+std::to_string(section.index)+" position="+
                std::to_string(stream.GetPosition())+" size="+std::to_string(section.bytes.size()));
    }
};
}
