#pragma once
#include "HostServices.h"
#include "HostFailure.h"

namespace ZeroSisHost {
class ModuleBackend {
public:
    virtual ~ModuleBackend()=default;
    virtual void Open()=0;
    virtual ICvGameContext1* GetContext()=0;
    virtual bool ShutdownCore()=0;
    virtual bool Close()=0;
};

enum class SessionPhase { Empty,Starting,CoreInitialized,Stopping,CleanupPending };
class Session {
public:
    Session()=default;
    Session(const Session&)=delete;
    Session& operator=(const Session&)=delete;
    // A failed shutdown must retain this complete session and its DB/backend.
    // The executable quarantines the owning Run object on unrecoverable failure.
    ~Session(){if(phase_.load()!=SessionPhase::Empty)std::terminate();}
    SessionPhase Phase() const noexcept {return phase_.load(std::memory_order_acquire);}
    ErrorSnapshot CleanupError() const noexcept {return cleanupError_;} // Caller must be quiescent; returned value is independent.

    void Initialize(ModuleBackend& backend,std::shared_ptr<HostState> state,Database::Connection& database) {
        Mutation mutation(*this);
        if(Phase()!=SessionPhase::Empty)throw std::logic_error("Native host session already active or requires cleanup");
        if(!state)throw std::invalid_argument("Native host state missing");
        if(state->gameThread!=GetCurrentThreadId())throw std::logic_error("Native host initialization requires the owner thread");
        if(state->scripts && (state->scripts->IsClosed() || !state->scripts->IsQuiescent()))
            throw std::logic_error("Native host initialization requires an open, quiescent script service");
        phase_.store(SessionPhase::Starting);backend_=&backend;state_=std::move(state);cleanupError_.Clear();
        ErrorSnapshot failure;
        try {
            engine_.reset(new EngineServices(state_));ui_.reset(new UserInterface(state_));
            // Open is armed before entry: the backend must retain/close partial resources.
            moduleTouched_=true;backend_->Open();
            bootstrapTouched_=true;ICvGameContext1* base=backend_->GetContext();
            if(!base)throw std::runtime_error("GameCore did not return a context");
            context_=base->QueryInterface<ICvGameContext3>();
            if(!context_)throw std::runtime_error("GameCore lacks ICvGameContext3");
            GameCall call(*state_);
            databaseTouched_=true;context_->SetGameDatabase(&database);
            uiTouched_=true;context_->SetEngineUserInterface(ui_.get());
            bindingTouched_=true;
            if(!context_->SetDLLIFace(engine_.get()))throw std::runtime_error("GameCore rejected the engine service interface");
            context_->SetGraphicsInitialized(false);
            globalsTouched_=true;context_->Init();
            if(state_->scripts)state_->scripts->BindGameLibraries(context_->GetScriptSystemUtility(),engine_.get());
            phase_.store(SessionPhase::CoreInitialized,std::memory_order_release);
            return;
        } catch(const std::exception& error) {failure.Capture(error);}
          catch(...) {failure.CaptureUnknown();}
        // The foreign exception must be destroyed before Cleanup can FreeLibrary.
        try{Cleanup();}
        catch(const std::exception& error){
            cleanupError_.Capture(error);phase_.store(SessionPhase::CleanupPending);
        } catch(...){
            cleanupError_.CaptureUnknown();phase_.store(SessionPhase::CleanupPending);
        }
        throw HostOperationError(failure);
    }

    void Shutdown() {
        Mutation mutation(*this);
        if(Phase()==SessionPhase::Empty)return;
        if(state_->gameThread!=GetCurrentThreadId())throw std::logic_error("Native host shutdown requires the owner thread");
        ErrorSnapshot failure;
        try{Cleanup();return;}
        catch(const std::exception& error){failure.Capture(error);}
        catch(...){failure.CaptureUnknown();}
        cleanupError_=failure;phase_.store(SessionPhase::CleanupPending);
        // Callers may retain this host-owned error across a successful retry.
        throw HostOperationError(failure);
    }

    // A game operation borrows the singleton only while the session cannot be
    // reentered or shut down. Foreign exceptions never escape across DLL unload.
    template<class Operation> void WithCore(Operation&& operation) {
        Mutation mutation(*this);
        if(Phase()!=SessionPhase::CoreInitialized || !context_ || !state_)
            throw std::logic_error("Game operation requires an initialized core");
        if(state_->gameThread!=GetCurrentThreadId() || (state_->scripts && !state_->scripts->IsQuiescent()))
            throw std::logic_error("Game operation requires its owner thread and quiescent scripts");
        ErrorSnapshot failure;
        try{GameCall call(*state_);operation(*context_);return;}
        catch(const std::exception& error){failure.Capture(error);}
        catch(...){failure.CaptureUnknown();}
        throw HostOperationError(failure);
    }

private:
    class Mutation {
    public:
        explicit Mutation(Session& session):session_(session){
            if(session_.busy_.test_and_set(std::memory_order_acquire))throw std::logic_error("Native host lifecycle mutation is busy");
        }
        ~Mutation(){session_.busy_.clear(std::memory_order_release);}
    private:Session& session_;
    };
    void Cleanup() {
        if(state_ && state_->scripts && !state_->scripts->IsQuiescent())
            throw std::logic_error("Cannot stop GameCore during an active script callback");
        phase_.store(SessionPhase::Stopping,std::memory_order_release);
        if(context_) {
            GameCall call(*state_);
            if(globalsTouched_){context_->Uninit();globalsTouched_=false;}
            // GameCore has released its borrowed VM handles. Remaining Lua finalizers
            // finish while the module and engine/DB adapters are still available.
            if(state_->scripts && !state_->scripts->Close())throw std::runtime_error("Script cleanup is pending");
            if(bindingTouched_){
                SetLastError(ERROR_SUCCESS);
                // This SDK returns false after successfully publishing nullptr.
                if(!context_->SetDLLIFace(nullptr) && GetLastError()!=ERROR_SUCCESS)
                    throw std::runtime_error("GameCore could not detach engine services");
                bindingTouched_=false;
            }
            if(uiTouched_){context_->SetEngineUserInterface(nullptr);uiTouched_=false;}
            if(databaseTouched_){context_->SetGameDatabase(nullptr);databaseTouched_=false;}
            context_=nullptr; // Shutdown may delete the singleton even when heap cleanup later fails.
        }
        if(state_ && state_->scripts && !state_->scripts->Close())throw std::runtime_error("Script cleanup is pending");
        if(bootstrapTouched_){if(!backend_->ShutdownCore())throw std::runtime_error("GameCore bootstrap cleanup is pending");bootstrapTouched_=false;}
        if(moduleTouched_){if(!backend_->Close())throw std::runtime_error("GameCore module release is pending");moduleTouched_=false;}
        ui_.reset();engine_.reset();state_.reset();backend_=nullptr;cleanupError_.Clear();
        phase_.store(SessionPhase::Empty,std::memory_order_release);
    }
    std::atomic_flag busy_=ATOMIC_FLAG_INIT;
    std::atomic<SessionPhase> phase_{SessionPhase::Empty};
    ErrorSnapshot cleanupError_;
    ModuleBackend* backend_=nullptr;
    ICvGameContext3* context_=nullptr; // Borrowed singleton; only ShutdownCore destroys it.
    std::shared_ptr<HostState> state_;
    std::unique_ptr<EngineServices> engine_;
    std::unique_ptr<UserInterface> ui_;
    bool moduleTouched_=false,bootstrapTouched_=false,databaseTouched_=false,uiTouched_=false,bindingTouched_=false,globalsTouched_=false;
};
}
