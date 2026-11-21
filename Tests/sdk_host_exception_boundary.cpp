// Actual Session plus a real disposable exception DLL and instrumented SDK context.
#if BOUNDARY_BASELINE
#include "OriginalGameCoreSession.h"
#else
#include "GameCoreSession.h"
#endif
#include "host_context_fixture.h"
#include "host_exception_fixture.h"
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <cstring>

using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool value,int line){++checks;if(!value){std::fprintf(stderr,"FAILED line=%d\n",line);std::exit(10);}}
#define CHECK(value) Check((value),__LINE__)
static void AbsentGameCore(){
    for(const wchar_t* name:{L"CvGameCoreDLL.dll",L"CvGameCoreDLL_Expansion1.dll",L"CvGameCoreDLL_Expansion2.dll",L"CvGameCoreDLL_Expansion2_x64.dll",L"CvGameCoreDLL_Expansion2_x64_probe.dll"})
        CHECK(!GetModuleHandleW(name));
}
struct FixtureState {
    std::function<void()> initialize,shutdown;
    ICvEngineUtility1* engine=nullptr;
    bool globals=false;
};
class Context final : public ContextFixtureBase {
public:
    explicit Context(FixtureState& state):state_(state){}
    void* DLLCALL QueryInterface(GUID id) override {return id==guidICvGameContext3?static_cast<ICvGameContext3*>(this):nullptr;}
    void DLLCALL SetGameDatabase(Database::Connection*) override {}
    void DLLCALL SetEngineUserInterface(ICvUserInterface2*) override {}
    bool DLLCALL SetDLLIFace(ICvEngineUtility1* value) override {state_.engine=value;SetLastError(ERROR_SUCCESS);return value!=nullptr;}
    void DLLCALL SetGraphicsInitialized(bool value) override {CHECK(!value);}
    void DLLCALL Init() override {
        state_.engine->InitGlobals();state_.globals=true;
        if(state_.initialize)state_.initialize();
    }
    void DLLCALL Uninit() override {
        if(state_.shutdown)state_.shutdown();
        state_.engine->UninitGlobals();state_.globals=false;
    }
private:FixtureState& state_;
};
class Module final : public ModuleBackend {
public:
    Module(const wchar_t* path,FixtureState& state,ExceptionProbe& probe):path_(path),state_(state),probe_(probe),context_(state){}
    ~Module(){CHECK(!module_);}
    void Open() override {
        module_=LoadLibraryExW(path_.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_DEFAULT_DIRS);
        CHECK(module_!=nullptr);FARPROC address=GetProcAddress(module_,"GetThrowForeign");CHECK(address!=nullptr);
        using Getter=ThrowForeignError(*)();Getter getter=nullptr;
        static_assert(sizeof(address)==sizeof(getter),"Function-pointer width");std::memcpy(&getter,&address,sizeof(getter));throw_=getter();
    }
    ICvGameContext1* GetContext() override {return &context_;}
    bool ShutdownCore() override {CHECK(!state_.globals && !state_.engine);return true;}
    bool Close() override {
        if(!module_)return true;
        std::printf("BEFORE_UNLOAD live=%d created=%d destroyed=%d\n",probe_.live,probe_.created,probe_.destroyed);std::fflush(stdout);
        maximumLiveAtClose=(std::max)(maximumLiveAtClose,probe_.live);
        CHECK(FreeLibrary(module_)!=FALSE);module_=nullptr;throw_=nullptr;
        CHECK(!GetModuleHandleW(path_.c_str()));++closes;
        return true;
    }
    void Throw(ForeignError kind){CHECK(module_ && throw_);throw_(&probe_,kind);CHECK(false);}
    bool Loaded() const{return module_!=nullptr;}
    int maximumLiveAtClose=0;unsigned closes=0;
private:std::wstring path_;FixtureState& state_;ExceptionProbe& probe_;Context context_;HMODULE module_=nullptr;ThrowForeignError throw_=nullptr;
};
static std::string Observe(std::exception_ptr failure,ForeignError kind){
    (void)kind;
    try{std::rethrow_exception(failure);}
#if !BOUNDARY_BASELINE
    catch(const HostOperationError& error){
        const auto snapshot=error.Details();CHECK(snapshot.Present());
        CHECK(snapshot.Origin()==(kind==ForeignError::Unknown?ErrorOrigin::Unknown:ErrorOrigin::Standard));
        CHECK(snapshot.Truncated()==(kind==ForeignError::LongMessage));
        return error.what();
    }
#endif
    catch(const std::exception& error){const char* text=error.what();return text?text:"null";}
    catch(...){return "unknown";}
}
static std::exception_ptr Capture(const std::function<void()>& function){
    try{function();}catch(...){return std::current_exception();}CHECK(false);return nullptr;
}
int wmain(int argc,wchar_t** argv){
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    _set_abort_behavior(0,_WRITE_ABORT_MSG|_CALL_REPORTFAULT);
    CHECK(argc==3);AbsentGameCore();
    const std::wstring scenario=argv[2];
    const bool initial=scenario.find(L"init-")==0;
    const bool dual=scenario==L"dual-standard";
#if BOUNDARY_BASELINE
    if(scenario.find(L"withcore-")==0)return 77; // The frozen original Session has no WithCore entry point.
    const bool withCore=false;
#else
    const bool withCore=scenario.find(L"withcore-")==0;
#endif
    const ForeignError kind=scenario.find(L"unknown")!=std::wstring::npos?ForeignError::Unknown:
        scenario.find(L"borrowed")!=std::wstring::npos?ForeignError::Borrowed:
        scenario.find(L"long")!=std::wstring::npos?ForeignError::LongMessage:
        scenario.find(L"null")!=std::wstring::npos?ForeignError::NullMessage:ForeignError::Standard;
    ExceptionProbe probe;FixtureState fixture;Module module(argv[1],fixture,probe);Session session;
    Database::Connection database;auto state=std::make_shared<HostState>("C:\\exception-component\\");
    unsigned initialFailures=initial||dual?1u:0u,shutdownFailures=initial||withCore?0u:1u;
    fixture.initialize=[&]{if(initialFailures){--initialFailures;module.Throw(kind);}};
    fixture.shutdown=[&]{if(shutdownFailures){--shutdownFailures;module.Throw(dual?ForeignError::Unknown:kind);}};
    std::exception_ptr retained;
    if(initial||dual){retained=Capture([&]{session.Initialize(module,state,database);});}
#if !BOUNDARY_BASELINE
    else if(withCore){
        session.Initialize(module,state,database);
        retained=Capture([&]{session.WithCore([&](ICvGameContext3&){module.Throw(kind);});});
        CHECK(session.Phase()==SessionPhase::CoreInitialized && module.Loaded());
        CHECK(!state->gameLock.HeldByCurrentThread() && state->executing==0 && probe.live==0);
    }
#endif
    else {session.Initialize(module,state,database);retained=Capture([&]{session.Shutdown();});}
    const bool pending=!initial&&!withCore;
    CHECK((session.Phase()==SessionPhase::CleanupPending)==pending);
    CHECK(static_cast<bool>(session.CleanupError())==pending);
    CHECK(module.Loaded()==(pending||withCore));
    if(pending){
#if !BOUNDARY_BASELINE
        const ErrorSnapshot snapshot=session.CleanupError();CHECK(snapshot.Present());
        CHECK(snapshot.Origin()==(dual||kind==ForeignError::Unknown?ErrorOrigin::Unknown:ErrorOrigin::Standard));
#endif
        session.Shutdown();
#if !BOUNDARY_BASELINE
        CHECK(snapshot.Present() && !session.CleanupError());
#endif
    }
    else if(withCore)session.Shutdown();
    CHECK(session.Phase()==SessionPhase::Empty && !session.CleanupError() && !module.Loaded());
    // Deliberately retain/rethrow after actual FreeLibrary, exactly the unsafe old lifetime.
    const std::string message=Observe(retained,kind);retained=nullptr;
#if !BOUNDARY_BASELINE
    const std::string expected=kind==ForeignError::Unknown?"Unknown native exception":
        kind==ForeignError::Borrowed?"Native gameplay object no longer exists or is changing state":
        kind==ForeignError::NullMessage?"Native exception without a message":
        kind==ForeignError::LongMessage?std::string(1023,'L'):"foreign-module-failure";
    CHECK(message==expected);
    CHECK(module.maximumLiveAtClose==0 && probe.live==0 && probe.created==probe.destroyed);
#endif
    CHECK(module.closes==1 && !state->gameLock.HeldByCurrentThread() && state->executing==0);
    CHECK(!state->engineAdapters && !state->userAdapters && !state->globalsStarted);
    session.Initialize(module,state,database);CHECK(session.Phase()==SessionPhase::CoreInitialized);
    session.Shutdown();CHECK(session.Phase()==SessionPhase::Empty && module.closes==2 && !module.Loaded());
    CHECK(!state->gameLock.HeldByCurrentThread() && state->executing==0 && !state->engineAdapters && !state->userAdapters);
    AbsentGameCore();
    std::printf("HOST_EXCEPTION_BOUNDARY_PASS checks=%u live_at_close=%d live_at_exit=%d created=%d destroyed=%d message_bytes=%zu GAMECORE_LOADED=false WITHCORE_PATH=%s\n",
        checks,module.maximumLiveAtClose,probe.live,probe.created,probe.destroyed,message.size(),withCore?"true":"false");
    return 0;
}
