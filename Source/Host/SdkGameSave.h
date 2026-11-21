#pragma once
#include "HostServices.h"
#include "NativeSaveArchive.h"
#include <FireWorks/FMemoryStream.h>

namespace ZeroSisHost {
// All SDK adapters and their callables remain inside an owner-thread WithCore
// operation. The service writes actual SDK data, without faking save success.
class SdkGameSave final {
public:
    SdkGameSave(ICvGameContext3& context,HostState& host,const std::wstring& directory,const std::wstring& bundle)
        :context_(context),host_(host),directory_(directory){
        ReadFileHandle file(bundle+L"\\bundle.manifest");std::array<unsigned char,16385> bytes{};
        const DWORD size=file.Read(bytes.data(),static_cast<DWORD>(bytes.size()));
        if(!size || size==bytes.size())throw std::runtime_error("Save bundle identity is invalid");
        bundle_.assign(bytes.begin(),bytes.begin()+size);
        if(host_.autoSave || host_.autoSaveRunning)throw std::logic_error("An autosave provider is already bound");
        host_.autoSave=[this](bool initial,bool postTurn){Save(initial,postTurn);};
    }
    ~SdkGameSave(){host_.autoSave=nullptr;}
    SdkGameSave(const SdkGameSave&)=delete;
    SdkGameSave& operator=(const SdkGameSave&)=delete;
    unsigned Count() const noexcept {return count_;}
    const std::wstring& LastPath() const noexcept {return lastPath_;}
    std::wstring Checkpoint(){
        const auto archive=Capture(false,false);const auto bytes=archive.Encode();
        const auto path=directory_+L"\\checkpoint-turn-"+std::to_wstring(archive.turn)+L".zssave";
        NativeSaveArchive::WriteAtomic(path,bytes);
        std::printf("NATIVE_CHECKPOINT_WRITTEN=%s\nNATIVE_CHECKPOINT_OBSERVATION=%d,%d,%d,%u,%zu\n",Utf8(path).c_str(),
            archive.turn,archive.elapsed,archive.activePlayer,static_cast<unsigned>(archive.sections.size()),bytes.size());
        return path;
    }
    NativeSaveArchive Capture(bool initial,bool postTurn){
        if(host_.gameThread!=GetCurrentThreadId() || !host_.gameLock.HeldByCurrentThread())
            throw std::logic_error("Saving requires the GameCore owner lock");
        std::unique_ptr<ICvPreGame1> pregame(context_.GetPreGame());
        std::unique_ptr<ICvGame1> game(context_.GetGame());
        std::unique_ptr<ICvMap1> map(context_.GetMap());
        if(!pregame || !game || !map || !game->IsFinalInitialized() || game->IsGameMultiPlayer())
            throw std::logic_error("Saving requires an initialized single-player game");
        NativeSaveArchive archive;archive.flags=(initial?1u:0u)|(postTurn?2u:0u);
        archive.turn=game->GetGameTurn();archive.elapsed=game->GetElapsedGameTurns();archive.activePlayer=game->GetActivePlayer();
        archive.sections.push_back({NativeSaveArchive::Bundle,0,bundle_});
        Add(archive,NativeSaveArchive::Pregame,0,[&](FDataStream& stream){pregame->write(stream);});
        Add(archive,NativeSaveArchive::Game,0,[&](FDataStream& stream){game->Write(stream);});
        Add(archive,NativeSaveArchive::Map,0,[&](FDataStream& stream){map->Write(stream);});
        Add(archive,NativeSaveArchive::Supporting,0,[&](FDataStream& stream){game->WriteSupportingClassData(stream);});
        for(unsigned id=0;id<MAX_TEAMS;++id){
            std::unique_ptr<ICvTeam1> team(context_.GetTeam(static_cast<TeamTypes>(id)));
            if(!team)throw std::runtime_error("Saving did not receive an SDK team slot");
            Add(archive,NativeSaveArchive::Team,id,[&](FDataStream& stream){team->Write(stream);});
        }
        for(unsigned id=0;id<MAX_PLAYERS;++id){
            std::unique_ptr<ICvPlayer1> player(game->GetPlayer(static_cast<PlayerTypes>(id)));
            if(!player || player->GetID()!=static_cast<int>(id))throw std::runtime_error("Saving did not receive an SDK player slot");
            Add(archive,NativeSaveArchive::Player,id,[&](FDataStream& stream){player->Write(stream);});
        }
        if(game->GetGameTurn()!=archive.turn || game->GetElapsedGameTurns()!=archive.elapsed || game->GetActivePlayer()!=archive.activePlayer)
            throw std::runtime_error("SDK save changed the game turn identity");
        archive.Validate();return archive;
    }
private:
    template<class Writer> static void Add(NativeSaveArchive& archive,unsigned kind,unsigned index,Writer writer){
        FMemoryStream stream;writer(stream);
        if(!stream.GetEOF() || stream.GetPosition()!=stream.GetEOF())throw std::runtime_error("SDK save section is incomplete");
        const auto* bytes=reinterpret_cast<const unsigned char*>(stream.GetBuf());
        archive.sections.push_back({kind,index,std::vector<unsigned char>(bytes,bytes+stream.GetEOF())});
    }
    void Save(bool initial,bool postTurn){
        std::puts("NATIVE_SAVE_PHASE=serialize_sdk_state");
        const auto archive=Capture(initial,postTurn);const auto bytes=archive.Encode();
        const auto path=directory_+L"\\autosave-"+std::to_wstring(count_)+L"-turn-"+std::to_wstring(archive.turn)+L".zssave";
        std::puts("NATIVE_SAVE_PHASE=persist_and_verify");NativeSaveArchive::WriteAtomic(path,bytes);
        lastPath_=path;++count_;
        host_.Record("autosave-written:"+std::to_string(archive.turn)+":"+std::to_string(bytes.size()));
        std::printf("NATIVE_SAVE_WRITTEN=%s\nNATIVE_SAVE_OBSERVATION=%d,%d,%d,%u,%zu\n",Utf8(path).c_str(),
            archive.turn,archive.elapsed,archive.activePlayer,static_cast<unsigned>(archive.sections.size()),bytes.size());
    }
    ICvGameContext3& context_;
    HostState& host_;
    const std::wstring directory_;
    std::vector<unsigned char> bundle_;
    std::wstring lastPath_;
    unsigned count_=0;
};
}
