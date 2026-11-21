#pragma once
#include "HostServices.h"
#include <FireWorks/FMemoryStream.h>
#include <array>
#include <memory>
#include <vector>

namespace ZeroSisHost {
namespace MenuLifecycleDetail {
inline bool SameGuid(const GUID& a,const GUID& b) noexcept {return std::memcmp(&a,&b,sizeof(GUID))==0;}
// These host-owned adapters are consumed synchronously by SetDLCAvailable.
// No pointer to the outgoing SDK survives the transition.
class Package final : public ICvDlcPackageInfo1 {
public:
    explicit Package(GUID value):value_(value){}
    static void* operator new(std::size_t bytes){return ::operator new(bytes);}
    static void operator delete(void* p) noexcept {::operator delete(p);}
    void* DLLCALL QueryInterface(GUID id) override {
        if(SameGuid(id,ICvUnknown::GetInterfaceId()) || SameGuid(id,ICvDlcPackageInfo1::GetInterfaceId())){++references_;return this;}
        return nullptr;
    }
    GUID DLLCALL GetPackageID() override {return value_;}
protected:
    void DLLCALL Destroy() override {if(!--references_)delete this;}
private:GUID value_;unsigned references_=1;
};
class Packages final : public ICvEnumerator {
public:
    explicit Packages(const std::vector<GUID>& values):values_(values){}
    static void* operator new(std::size_t bytes){return ::operator new(bytes);}
    static void operator delete(void* p) noexcept {::operator delete(p);}
    void* DLLCALL QueryInterface(GUID id) override {
        if(SameGuid(id,ICvUnknown::GetInterfaceId()) || SameGuid(id,ICvEnumerator::GetInterfaceId())){++references_;return this;}
        return nullptr;
    }
    bool DLLCALL MoveNext() override {if(next_>=values_.size()){current_=values_.size();return false;}current_=next_++;return true;}
    void DLLCALL Reset() override {next_=0;current_=values_.size();}
    ICvUnknown* DLLCALL GetCurrent() override {return current_<values_.size()?new Package(values_[current_]):nullptr;}
protected:
    void DLLCALL Destroy() override {if(!--references_)delete this;}
private:std::vector<GUID> values_;std::size_t next_=0,current_=static_cast<std::size_t>(-1);unsigned references_=1;
};
inline std::vector<GUID> ReadPackages(ICvEnumerator* raw){
    std::unique_ptr<ICvEnumerator> items(raw);
    if(!items)throw std::runtime_error("Pregame DLC enumerator is missing");
    std::vector<GUID> result;
    while(items->MoveNext()){
        std::unique_ptr<ICvUnknown> unknown(items->GetCurrent());
        std::unique_ptr<ICvDlcPackageInfo1> item(unknown?unknown->QueryInterface<ICvDlcPackageInfo1>():nullptr);
        if(!item || result.size()>=4096)throw std::runtime_error("Pregame DLC list is invalid or exceeds its bound");
        const auto value=item->GetPackageID();
        for(const auto& prior:result)if(SameGuid(prior,value))throw std::runtime_error("Pregame DLC list contains a duplicate package");
        result.push_back(value);
    }
    return result;
}
inline bool SamePackages(const std::vector<GUID>& a,const std::vector<GUID>& b){
    if(a.size()!=b.size())return false;
    for(std::size_t i=0;i<a.size();++i)if(!SameGuid(a[i],b[i]))return false;
    return true;
}
inline std::vector<unsigned char> WritePregame(ICvPreGame1& pregame){
    FMemoryStream stream;pregame.write(stream);
    if(!stream.GetEOF() || stream.GetEOF()>16u*1024u*1024u || stream.GetPosition()!=stream.GetEOF())
        throw std::runtime_error("Pregame setup serialization is incomplete or exceeds its bound");
    const auto* begin=reinterpret_cast<const unsigned char*>(stream.GetBuf());
    return {begin,begin+stream.GetEOF()};
}
}

// Captures the actual current setup, including public fields omitted by the
// SDK's version-6 archive. This is an in-memory handoff, not a new save format.
class MenuLifecycleSetup final {
public:
    static MenuLifecycleSetup Capture(ICvGameContext3& context,HostState& host,const std::vector<unsigned char>& bundle){
        RequireOwner(host);
        if(bundle.empty() || bundle.size()>16384)throw std::invalid_argument("Restart setup lacks an exact bundle identity");
        std::unique_ptr<ICvPreGame1> pregame(context.GetPreGame());
        std::unique_ptr<ICvGame1> game(context.GetGame());
        if(!pregame || !game || !game->IsFinalInitialized() || game->IsGameMultiPlayer() ||
           pregame->gameType()!=GAME_SINGLE_PLAYER || pregame->loadWBScenario() || pregame->isWBMapScript())
            throw std::logic_error("Restart requires an initialized ordinary single-player map");
        MenuLifecycleSetup out;out.bundle_=bundle;out.pregame_=MenuLifecycleDetail::WritePregame(*pregame);
        out.active_=pregame->activePlayer();out.handicap_=pregame->handicap(out.active_);
        out.mapSeed_=pregame->mapRandomSeed();out.syncSeed_=pregame->syncRandomSeed();
        out.quickMovement_=pregame->quickMovement();out.persist_=pregame->GetPersistSettings();
        out.allowed_=MenuLifecycleDetail::ReadPackages(pregame->GetDLCAllowed());
        for(int i=0;i<MAX_PLAYERS;++i){
            const auto player=static_cast<PlayerTypes>(i);
            if(pregame->netID(player)!=-1)throw std::logic_error("Offline restart cannot retain transport assignments");
            out.available_[static_cast<std::size_t>(i)]=MenuLifecycleDetail::ReadPackages(pregame->GetDLCAvailable(player));
            out.civPackages_[static_cast<std::size_t>(i)]=pregame->civilizationKeyPackageID(player);
            out.leaderPackages_[static_cast<std::size_t>(i)]=pregame->leaderKeyPackageID(player);
            out.civilizations_[static_cast<std::size_t>(i)]=pregame->civilization(player);
            out.leaders_[static_cast<std::size_t>(i)]=pregame->leaderHead(player);
        }
        if(out.active_!=game->GetActivePlayer() || out.active_<0 || out.active_>=MAX_PLAYERS)
            throw std::logic_error("Restart setup lost the active player identity");
        return out;
    }
    void ApplyAndStart(ICvGameContext3& context,HostState& host,const std::vector<unsigned char>& bundle) const {
        RequireOwner(host);
        if(bundle!=bundle_ || pregame_.empty() || host.loadedGame)
            throw std::logic_error("Restart requires the same bundle and a fresh non-restored session");
        std::unique_ptr<ICvPreGame1> pregame(context.GetPreGame());
        std::unique_ptr<ICvGame1> game(context.GetGame());std::unique_ptr<ICvMap1> map(context.GetMap());
        if(!pregame || !game || !map || game->IsFinalInitialized() || map->NumPlots()!=0)
            throw std::logic_error("Restart may not replace an initialized SDK game");
        pregame->resetGame();pregame->resetPlayers();
        FMemoryStream input(static_cast<int>(pregame_.size()),pregame_.data(),false);
        pregame->read(input,true);
        if(input.GetPosition()!=pregame_.size() || input.GetEOF()!=pregame_.size() ||
           MenuLifecycleDetail::WritePregame(*pregame)!=pregame_)
            throw std::runtime_error("Restart setup did not roundtrip byte-for-byte through the current SDK");
        pregame->clearDLCAllowed();for(const auto& id:allowed_)pregame->setDLCAllowed(id,true);
        for(int i=0;i<MAX_PLAYERS;++i){
            const auto player=static_cast<PlayerTypes>(i);const auto index=static_cast<std::size_t>(i);
            std::unique_ptr<ICvEnumerator> packages(new MenuLifecycleDetail::Packages(available_[index]));
            pregame->SetDLCAvailable(player,packages.get());
            pregame->setCivilizationKeyPackageID(player,civPackages_[index]);
            pregame->setLeaderKeyPackageID(player,leaderPackages_[index]);
            if(pregame->civilization(player)!=civilizations_[index] || pregame->leaderHead(player)!=leaders_[index] ||
               !MenuLifecycleDetail::SameGuid(pregame->civilizationKeyPackageID(player),civPackages_[index]) ||
               !MenuLifecycleDetail::SameGuid(pregame->leaderKeyPackageID(player),leaderPackages_[index]) ||
               !MenuLifecycleDetail::SamePackages(MenuLifecycleDetail::ReadPackages(pregame->GetDLCAvailable(player)),available_[index]))
                throw std::runtime_error("Restart setup changed a civilization, leader, or DLC slot");
            host.assignedNetworkIds[index]=pregame->netID(player);
        }
        pregame->setQuickMovement(quickMovement_);pregame->setPersistSettings(persist_);
        if(!MenuLifecycleDetail::SamePackages(MenuLifecycleDetail::ReadPackages(pregame->GetDLCAllowed()),allowed_) ||
           pregame->quickMovement()!=quickMovement_ || pregame->GetPersistSettings()!=persist_)
            throw std::runtime_error("Restart setup changed supplemental pregame settings");
        // Only lifetime fields change. All map/game options, slots, names,
        // victories and both initial seeds remain the captured current setup.
        pregame->setGameType(GAME_SINGLE_PLAYER,GAME_NEW);pregame->setGameStarted(false);
        pregame->setGameTurn(0);pregame->setLoadFileName(CvString(""));
        if(pregame->mapRandomSeed()!=mapSeed_ || pregame->syncRandomSeed()!=syncSeed_ ||
           pregame->activePlayer()!=active_ || pregame->handicap(active_)!=handicap_)
            throw std::runtime_error("Restart lifetime normalization changed the setup identity or seeds");
        host.networkAssignmentsReady=true;game->Init(handicap_);
        if(!game->Init2() || *host.scripts->LastError() || !game->IsFinalInitialized() || game->IsGameMultiPlayer())
            throw std::runtime_error("Captured-setup restart could not initialize the fresh game");
    }
    const std::vector<unsigned char>& BundleIdentity() const noexcept {return bundle_;}
    const std::vector<unsigned char>& PregameBytes() const noexcept {return pregame_;}
private:
    static void RequireOwner(HostState& host){
        if(host.gameThread!=GetCurrentThreadId() || !host.gameLock.HeldByCurrentThread() || !host.scripts ||
           !host.scripts->IsQuiescent() || !host.localCommands.IsQuiescent() || host.autoSaveRunning)
            throw std::logic_error("Menu setup requires its settled owner-thread GameCore boundary");
    }
    std::vector<unsigned char> bundle_,pregame_;
    std::vector<GUID> allowed_;std::array<std::vector<GUID>,MAX_PLAYERS> available_;
    std::array<GUID,MAX_PLAYERS> civPackages_{},leaderPackages_{};
    std::array<CivilizationTypes,MAX_PLAYERS> civilizations_{};std::array<LeaderHeadTypes,MAX_PLAYERS> leaders_{};
    PlayerTypes active_=NO_PLAYER;HandicapTypes handicap_=NO_HANDICAP;unsigned mapSeed_=0,syncSeed_=0;
    bool quickMovement_=false,persist_=false;
};
}
