#pragma once
#include "GeneratedHostInterfaces.h"
#include "MapSurface.h"
#include "AudioCatalog.h"
#include "ScriptSystem.h"
#include <set>

namespace ZeroSisHost {
class CoreLock {
public:
    void Enter() {
        mutex_.lock();
        if(depth_==UINT_MAX){mutex_.unlock();throw std::overflow_error("GameCore lock recursion overflow");}
        if(depth_==0) owner_.store(GetCurrentThreadId(),std::memory_order_release);
        ++depth_;
    }
    bool TryEnter() {
        if(!mutex_.try_lock()) return false;
        if(depth_==UINT_MAX){mutex_.unlock();throw std::overflow_error("GameCore lock recursion overflow");}
        if(depth_==0) owner_.store(GetCurrentThreadId(),std::memory_order_release);
        ++depth_;return true;
    }
    void Leave() {
        if(!HeldByCurrentThread()) throw std::logic_error("GameCore lock release from a non-owner thread");
        if(--depth_==0) owner_.store(0,std::memory_order_release);
        mutex_.unlock();
    }
    bool HeldByCurrentThread() const noexcept { return owner_.load(std::memory_order_acquire)==GetCurrentThreadId(); }
private:
    std::recursive_mutex mutex_;
    std::atomic<DWORD> owner_{0};
    unsigned depth_=0;
};

struct HostState {
    explicit HostState(std::string cache,Database::Connection* mods=nullptr,std::shared_ptr<const AudioCatalog> catalog=nullptr,
                       std::shared_ptr<ScriptSystem> script=nullptr)
        : cacheDirectory(std::move(cache)),modsDatabase(mods),gameThread(GetCurrentThreadId()),audio(std::move(catalog)),scripts(std::move(script)) {
        if(cacheDirectory.empty() || (cacheDirectory.back()!='/' && cacheDirectory.back()!='\\'))
            throw std::invalid_argument("The isolated session cache directory requires a trailing separator");
        if(scripts && !scripts->IsOwner())throw std::invalid_argument("Script service belongs to a different thread");
    }
    CoreLock gameLock;
    const std::string cacheDirectory;
    Database::Connection* const modsDatabase;
    const DWORD gameThread;
    const std::shared_ptr<const AudioCatalog> audio;
    const std::shared_ptr<ScriptSystem> scripts;
    MapSurface mapSurface;
    std::set<std::string> missingAudioTags;
    std::atomic<unsigned> executing{0};
    std::atomic<bool> globalsStarted{false},done{false};
    std::atomic<unsigned> engineAdapters{0},userAdapters{0};
    std::mutex dataMutex;
    std::map<int,bool> dirty;
    int cycleSelection=0;
    std::vector<std::string> events;
    void Record(const std::string& message){std::lock_guard<std::mutex> guard(dataMutex);events.push_back(message);}
    std::vector<std::string> Events(){std::lock_guard<std::mutex> guard(dataMutex);return events;}
};

// Each QueryInterface result is an independently owned SDK adapter. Its shared
// state belongs to the host session and outlives GC's adapter/borrowed pointers.
class EngineServices final : public EngineServicesBase {
public:
    explicit EngineServices(std::shared_ptr<HostState> state):state_(std::move(state)){
        if(!state_)throw std::invalid_argument("Engine service state missing");++state_->engineAdapters;
    }
    ~EngineServices(){--state_->engineAdapters;}
    static void* operator new(std::size_t bytes){return ::operator new(bytes);}
    static void operator delete(void* p) noexcept {::operator delete(p);}
    void* DLLCALL QueryInterface(GUID id) override {
        if(id==guidICvUnknown || id==guidICvEngineUtility1 || id==guidICvEngineUtility2 || id==guidICvEngineUtility3 || id==guidICvEngineUtility4)
            return static_cast<ICvEngineUtility4*>(new EngineServices(state_));
        return nullptr;
    }
    void DLLCALL Destroy() override {delete this;}
    void InitGlobals() override {
        if(!IsGameCoreThread())throw std::logic_error("Host globals initialization requires the owner thread");
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        if(state_->globalsStarted)throw std::logic_error("Host globals already initialized");
        state_->globalsStarted=true;
        state_->mapSurface.Clear();state_->dirty.clear();state_->cycleSelection=0;
        state_->done=false;state_->missingAudioTags.clear();
        state_->events.push_back("host-globals-started");
    }
    void UninitGlobals() override {
        // Idempotent after a partially completed InitGlobals or an earlier retry.
        if(!IsGameCoreThread())throw std::logic_error("Host globals shutdown requires the owner thread");
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        state_->mapSurface.Clear();
        if(state_->globalsStarted)state_->events.push_back("host-globals-stopped");
        state_->globalsStarted=false;
    }
    const char* GetCacheFolderPath() override {return state_->cacheDirectory.c_str();}
    ICvEngineScriptSystem1* GetScriptSystem() override {
        if(!state_->scripts)Unsupported("ICvEngineUtility1::GetScriptSystem (service not configured)");
        return state_->scripts.get();
    }
    void DoMapSetup(int count) override {
        if(!state_->globalsStarted || !IsGameCoreThread() || !HasGameCoreLock())
            throw std::logic_error("Map setup requires active host globals, owner thread and GameCore lock");
        state_->mapSurface.Setup(count);
    }
    int GetAudioTagIndex(const char* tag,int category=-1) override {
        if(category!=AUDIOTAG_SOUNDSCAPE)Unsupported("ICvEngineUtility1::GetAudioTagIndex (audio category not implemented)");
        if(!state_->audio)Unsupported("ICvEngineUtility1::GetAudioTagIndex (catalog not configured)");
        const int index=state_->audio->Find(tag);
        if(index<0 && tag && *tag){std::lock_guard<std::mutex> guard(state_->dataMutex);state_->missingAudioTags.insert(tag);}
        return index;
    }
    bool ShouldValidateGameDatabase() const override {return true;}
    Database::Connection* GetModsDatabase() override {
        if(!state_->modsDatabase)Unsupported("ICvEngineUtility1::GetModsDatabase (database not configured)");
        return state_->modsDatabase;
    }
    bool IsHost() const override {return true;} // This executable's initial mode is local single player.
    bool IsPitbossHost() const override {return false;}
    void SetDone(bool value) override {state_->done=value;}
    bool GetDone() override {return state_->done;}
    bool GetAutorun() override {return false;}
    void GetGameCoreLock() override {state_->gameLock.Enter();}
    void ReleaseGameCoreLock() override {state_->gameLock.Leave();}
    bool TryGameCoreLock() override {return state_->gameLock.TryEnter();}
    bool HasGameCoreLock() override {return state_->gameLock.HeldByCurrentThread();}
    bool IsGameCoreThread() override {return state_->gameThread==GetCurrentThreadId();}
    bool IsGameCoreExecuting() override {return state_->executing.load(std::memory_order_acquire)!=0;}
    void netMessageDebugLog(const std::string& message) const override {state_->Record(message);}
private:
    std::shared_ptr<HostState> state_;
};

class UserInterface final : public UserInterfaceBase {
public:
    explicit UserInterface(std::shared_ptr<HostState> state):state_(std::move(state)){
        if(!state_)throw std::invalid_argument("UI service state missing");++state_->userAdapters;
    }
    ~UserInterface(){--state_->userAdapters;}
    static void* operator new(std::size_t bytes){return ::operator new(bytes);}
    static void operator delete(void* p) noexcept {::operator delete(p);}
    void* DLLCALL QueryInterface(GUID id) override {
        if(id==guidICvUnknown || id==guidICvUserInterface1 || id==guidICvUserInterface2)
            return static_cast<ICvUserInterface2*>(new UserInterface(state_));
        return nullptr;
    }
    void DLLCALL Destroy() override {delete this;}
    bool isDirty(InterfaceDirtyBits item) override {
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        const auto found=state_->dirty.find(static_cast<int>(item));return found!=state_->dirty.end() && found->second;
    }
    void setDirty(InterfaceDirtyBits item,bool value) override {std::lock_guard<std::mutex> guard(state_->dataMutex);state_->dirty[static_cast<int>(item)]=value;}
    int getCycleSelectionCounter() override {std::lock_guard<std::mutex> guard(state_->dataMutex);return state_->cycleSelection;}
    void setCycleSelectionCounter(int value) override {std::lock_guard<std::mutex> guard(state_->dataMutex);state_->cycleSelection=value;}
    void changeCycleSelectionCounter(int value) override {
        std::lock_guard<std::mutex> guard(state_->dataMutex);
        const long long next=static_cast<long long>(state_->cycleSelection)+value;
        if(next<INT_MIN || next>INT_MAX)throw std::overflow_error("UI selection counter overflow");
        state_->cycleSelection=static_cast<int>(next);
    }
private:
    std::shared_ptr<HostState> state_;
};

class GameCall {
public:
    explicit GameCall(HostState& state):state_(state){state_.gameLock.Enter();state_.executing.fetch_add(1,std::memory_order_release);}
    ~GameCall(){state_.executing.fetch_sub(1,std::memory_order_release);state_.gameLock.Leave();}
    GameCall(const GameCall&)=delete;
    GameCall& operator=(const GameCall&)=delete;
private:
    HostState& state_;
};
}
