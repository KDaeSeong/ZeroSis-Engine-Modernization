// Real host adapters/session, actual frozen SDK declarations, instrumented GameCore.
// No GameCore object is linked or loaded by this executable.
#include "GameCoreSession.h"
#include "host_context_fixture.h"
#include "host_script_utility_fixture.h"
#include "ZeroSisHostBinding.h"
#include <thread>
#include <functional>
#include <cstdio>

using namespace ZeroSisHost;
static std::atomic<unsigned> checks{0};
static std::atomic<unsigned> withCoreSuccesses{0},withCoreRejections{0},withCoreOperationErrors{0};
static void Check(bool ok,const char* text,int line){++checks;if(!ok){std::fprintf(stderr,"FAILED line=%d %s\n",line,text);std::exit(1);}}
#define CHECK(value) Check((value),#value,__LINE__)
template<class F> static std::string Failure(F operation){
    try{operation();}catch(const std::exception& e){return e.what();}CHECK(false);return {};
}

struct Control {
    std::string fault;
    unsigned remaining=0;
    bool module=false,alive=false,globals=false,missingContext=false,missingInterface=false;
    bool detachRefusal=false,bootstrapRefusal=false,closeRefusal=false;
    Database::Connection* database=nullptr;
    ICvScriptSystemUtility1* scriptUtility=nullptr;
    ICvUserInterface2* ui=nullptr;
    ZeroSisHostBinding::Owned<ICvEngineUtility4> engine;
    std::vector<std::string> trace;
    std::function<void(const std::string&)> hook;
    void Hit(const std::string& name){
        trace.push_back(name);if(hook)hook(name);
        if(fault==name && remaining){--remaining;throw std::runtime_error("injected:"+name);}
    }
    unsigned Count(const std::string& name) const {
        return static_cast<unsigned>(std::count(trace.begin(),trace.end(),name));
    }
    void ContextLive(){CHECK(module && alive);}
    void Empty(){CHECK(!module && !alive && !globals && !database && !ui && !engine);}
};
class FakeContext final : public ContextFixtureBase {
public:
    explicit FakeContext(Control& control):c(control){}
    void* DLLCALL QueryInterface(GUID id) override {
        c.ContextLive();c.Hit("query.before");CHECK(id==guidICvGameContext3);c.Hit("query.after");
        return c.missingInterface?nullptr:static_cast<ICvGameContext3*>(this);
    }
    void DLLCALL Destroy() override {CHECK(false);} // The actual SDK singleton is borrowed.
    ICvScriptSystemUtility1* DLLCALL GetScriptSystemUtility() override{
        c.ContextLive();c.Hit("script-utility.before");c.Hit("script-utility.after");return c.scriptUtility;
    }
    void DLLCALL SetGameDatabase(Database::Connection* database) override {
        c.ContextLive();const std::string event=database?"database-set":"database-clear";
        c.Hit(event+".before");c.database=database;c.Hit(event+".after");
    }
    void DLLCALL SetEngineUserInterface(ICvUserInterface2* ui) override {
        c.ContextLive();const std::string event=ui?"ui-set":"ui-clear";
        c.Hit(event+".before");c.ui=ui;c.Hit(event+".after");
    }
    bool DLLCALL SetDLLIFace(ICvEngineUtility1* engine) override {
        c.ContextLive();const std::string event=engine?"bind":"detach";
        c.Hit(event+".before");
        if(!engine && c.detachRefusal){c.detachRefusal=false;SetLastError(ERROR_BUSY);return false;}
        CHECK(!c.globals);
        c.engine.reset(engine?engine->QueryInterface<ICvEngineUtility4>():nullptr);
        c.Hit(event+".after");SetLastError(ERROR_SUCCESS);return engine!=nullptr;
    }
    void DLLCALL SetGraphicsInitialized(bool initialized) override {
        c.ContextLive();c.Hit("graphics.before");CHECK(!initialized);c.Hit("graphics.after");
    }
    void DLLCALL Init() override {
        c.ContextLive();c.Hit("init.before");CHECK(c.database && c.ui && c.engine && !c.globals);
        CHECK(c.engine->HasGameCoreLock() && c.engine->IsGameCoreExecuting() && c.engine->IsGameCoreThread());
        c.globals=true;c.engine->InitGlobals();c.Hit("init.after");
    }
    void DLLCALL Uninit() override {
        c.ContextLive();c.Hit("uninit.before");CHECK(c.database && c.ui && c.engine);
        CHECK(c.engine->HasGameCoreLock() && c.engine->IsGameCoreExecuting());
        c.engine->UninitGlobals();c.globals=false;c.Hit("uninit.after");
    }
private:Control& c;
};
class FakeModule final : public ModuleBackend {
public:
    explicit FakeModule(Control& control):c(control),context(control){}
    void Open() override {c.Hit("open.before");CHECK(!c.module);c.module=true;c.Hit("open.after");}
    ICvGameContext1* GetContext() override {
        c.Hit("context-get.before");CHECK(c.module);c.alive=true;c.Hit("context-get.after");
        return c.missingContext?nullptr:&context;
    }
    bool ShutdownCore() override {
        c.Hit("core-stop.before");CHECK(!c.globals && !c.database && !c.ui && !c.engine);
        // Model a singleton already destroyed before a later heap cleanup failure.
        c.alive=false;
        if(c.bootstrapRefusal){c.bootstrapRefusal=false;return false;}
        c.Hit("core-stop.after");return true;
    }
    bool Close() override {
        c.Hit("module-close.before");CHECK(!c.alive && !c.globals && !c.database && !c.ui && !c.engine);
        if(c.closeRefusal){c.closeRefusal=false;return false;}
        c.module=false;c.Hit("module-close.after");return true;
    }
private:Control& c;FakeContext context;
};

static void AdaptersAndLocks(){
    CHECK(Failure([]{HostState state("");}).find("separator")!=std::string::npos);
    CHECK(Failure([]{EngineServices engine(nullptr);}).find("missing")!=std::string::npos);
    auto state=std::make_shared<HostState>("C:\\isolated-test\\");
    {
        EngineServices engine(state);UserInterface ui(state);
        const GUID engineIds[]={guidICvUnknown,guidICvEngineUtility1,guidICvEngineUtility2,guidICvEngineUtility3,guidICvEngineUtility4};
        const GUID uiIds[]={guidICvUnknown,guidICvUserInterface1,guidICvUserInterface2};
        for(const auto& id:engineIds){
            auto* owned=static_cast<ICvEngineUtility4*>(engine.QueryInterface(id));CHECK(owned && state->engineAdapters==2);
            CHECK(std::string(owned->GetCacheFolderPath())=="C:\\isolated-test\\");ZeroSisHostBinding::Release(owned);CHECK(state->engineAdapters==1);
        }
        for(const auto& id:uiIds){
            auto* owned=static_cast<ICvUserInterface2*>(ui.QueryInterface(id));CHECK(owned && state->userAdapters==2);
            ZeroSisHostBinding::Release(owned);CHECK(state->userAdapters==1);
        }
        CHECK(!engine.QueryInterface(guidICvGameContext3));CHECK(!ui.QueryInterface(guidICvGameContext3));
        CHECK(Failure([&]{engine.GetModsDatabase();}).find("GetModsDatabase")!=std::string::npos);
        CHECK(Failure([&]{engine.GetScriptSystem();}).find("GetScriptSystem")!=std::string::npos);
        engine.InitGlobals();CHECK(state->globalsStarted);
        CHECK(Failure([&]{engine.InitGlobals();}).find("already")!=std::string::npos);
        engine.UninitGlobals();engine.UninitGlobals();CHECK(!state->globalsStarted && state->Events().size()==2);
        CHECK(engine.IsHost() && !engine.IsPitbossHost() && !engine.GetAutorun());
        engine.SetDone(true);CHECK(engine.GetDone());engine.SetDone(false);CHECK(!engine.GetDone());
        CHECK(!engine.HasGameCoreLock() && !engine.IsGameCoreExecuting() && engine.IsGameCoreThread());
        engine.GetGameCoreLock();CHECK(engine.TryGameCoreLock());
        std::thread other([&]{
            CHECK(!engine.HasGameCoreLock() && !engine.IsGameCoreThread() && !engine.TryGameCoreLock());
            CHECK(Failure([&]{engine.ReleaseGameCoreLock();}).find("non-owner")!=std::string::npos);
        });other.join();
        engine.ReleaseGameCoreLock();CHECK(engine.HasGameCoreLock());engine.ReleaseGameCoreLock();CHECK(!engine.HasGameCoreLock());
        {GameCall first(*state);{GameCall second(*state);CHECK(state->executing==2);}CHECK(state->executing==1);}
        CHECK(state->executing==0 && !engine.HasGameCoreLock());
        const auto dirty=static_cast<InterfaceDirtyBits>(0);
        CHECK(!ui.isDirty(dirty) && state->dirty.empty());ui.setDirty(dirty,true);CHECK(ui.isDirty(dirty));ui.setDirty(dirty,false);CHECK(!ui.isDirty(dirty));
        ui.setCycleSelectionCounter(INT_MAX);CHECK(Failure([&]{ui.changeCycleSelectionCounter(1);}).find("overflow")!=std::string::npos);CHECK(ui.getCycleSelectionCounter()==INT_MAX);
        ui.setCycleSelectionCounter(INT_MIN);CHECK(Failure([&]{ui.changeCycleSelectionCounter(-1);}).find("overflow")!=std::string::npos);CHECK(ui.getCycleSelectionCounter()==INT_MIN);
        ui.setCycleSelectionCounter(0);
        unsigned protectedCount=0;
        std::vector<std::thread> workers;
        for(unsigned worker=0;worker<8;++worker)workers.emplace_back([&,worker]{
            for(unsigned i=0;i<128;++i){
                auto* adapter=static_cast<ICvEngineUtility4*>(engine.QueryInterface(guidICvEngineUtility4));
                {GameCall call(*state);++protectedCount;CHECK(adapter->HasGameCoreLock() && adapter->IsGameCoreExecuting());}
                adapter->netMessageDebugLog("worker:"+std::to_string(worker)+":"+std::to_string(i));
                ui.changeCycleSelectionCounter(1);ZeroSisHostBinding::Release(adapter);
            }
        });
        for(auto& worker:workers)worker.join();
        CHECK(protectedCount==1024 && ui.getCycleSelectionCounter()==1024 && state->Events().size()==1026);
        CHECK(state->engineAdapters==1 && state->userAdapters==1 && state->executing==0);
    }
    CHECK(state->engineAdapters==0 && state->userAdapters==0);
}

static void Sessions(){
    Database::Connection database;
    const std::vector<std::string> startup={"open","context-get","query","database-set","ui-set","bind","graphics","init"};
    const std::vector<std::string> shutdown={"uninit","detach","ui-clear","database-clear","core-stop","module-close"};
    for(const auto& stage:startup)for(const std::string when:{".before",".after"}){
        Control control;FakeModule backend(control);Session session;auto state=std::make_shared<HostState>("C:\\fixture\\");
        control.fault=stage+when;control.remaining=1;
        CHECK(Failure([&]{session.Initialize(backend,state,database);})=="injected:"+control.fault);
        CHECK(session.Phase()==SessionPhase::Empty && !session.CleanupError());control.Empty();
        CHECK(state->engineAdapters==0 && state->userAdapters==0 && !state->globalsStarted);
        session.Shutdown();
    }
    for(const auto& stage:shutdown)for(const std::string when:{".before",".after"}){
        Control control;FakeModule backend(control);Session session;auto state=std::make_shared<HostState>("C:\\fixture\\");
        session.Initialize(backend,state,database);
        control.fault=stage+when;control.remaining=2;
        for(unsigned retry=0;retry<2;++retry){
            CHECK(Failure([&]{session.Shutdown();})=="injected:"+control.fault);
            CHECK(session.Phase()==SessionPhase::CleanupPending && session.CleanupError());
            CHECK(state->engineAdapters>=1 && state->userAdapters==1);
            CHECK(Failure([&]{session.Initialize(backend,state,database);}).find("requires cleanup")!=std::string::npos);
        }
        session.Shutdown();CHECK(session.Phase()==SessionPhase::Empty && !session.CleanupError());control.Empty();
        const auto failedIndex=static_cast<std::size_t>(std::find(shutdown.begin(),shutdown.end(),stage)-shutdown.begin());
        for(std::size_t i=0;i<failedIndex;++i)CHECK(control.Count(shutdown[i]+".before")==1);
        CHECK(control.Count(stage+when)==3 && state->engineAdapters==0 && state->userAdapters==0);
    }
    for(unsigned kind=0;kind<3;++kind){
        Control control;FakeModule backend(control);Session session;auto state=std::make_shared<HostState>("C:\\fixture\\");
        session.Initialize(backend,state,database);
        if(kind==0)control.detachRefusal=true;if(kind==1)control.bootstrapRefusal=true;if(kind==2)control.closeRefusal=true;
        CHECK(!Failure([&]{session.Shutdown();}).empty());CHECK(session.Phase()==SessionPhase::CleanupPending);
        session.Shutdown();control.Empty();CHECK(session.Phase()==SessionPhase::Empty);
        if(kind==1)CHECK(control.Count("uninit.before")==1 && control.Count("core-stop.before")==2);
    }
    for(unsigned kind=0;kind<2;++kind){
        Control control;FakeModule backend(control);Session session;auto state=std::make_shared<HostState>("C:\\fixture\\");
        control.missingContext=kind==0;control.missingInterface=kind==1;
        CHECK(!Failure([&]{session.Initialize(backend,state,database);}).empty());control.Empty();CHECK(session.Phase()==SessionPhase::Empty);
    }
    {
        Control control;FakeModule backend(control);Session session;auto state=std::make_shared<HostState>("C:\\fixture\\");
        control.hook=[&](const std::string& event){
            if(event=="init.after"){control.fault="uninit.before";control.remaining=1;throw std::runtime_error("original-init-failure");}
        };
        CHECK(Failure([&]{session.Initialize(backend,state,database);})=="original-init-failure");
        CHECK(session.Phase()==SessionPhase::CleanupPending && session.CleanupError() && control.globals);
        control.hook=nullptr;session.Shutdown();control.Empty();
    }
    {
        Control control;FakeModule backend(control);Session session;auto state=std::make_shared<HostState>("C:\\fixture\\");
        unsigned reentries=0;
        control.hook=[&](const std::string&){CHECK(Failure([&]{session.Shutdown();}).find("busy")!=std::string::npos);++reentries;};
        session.Initialize(backend,state,database);CHECK(session.Phase()==SessionPhase::CoreInitialized);
        std::thread wrongOwner([&]{CHECK(Failure([&]{session.Shutdown();}).find("owner thread")!=std::string::npos);});wrongOwner.join();
        CHECK(Failure([&]{session.Initialize(backend,state,database);}).find("already active")!=std::string::npos);
        session.Shutdown();control.Empty();CHECK(reentries==28);
    }
    {
        Control control;FakeModule backend(control);Session session;auto state=std::make_shared<HostState>("C:\\fixture\\");
        control.hook=[&](const std::string& event){if(event=="init.after"){
            std::vector<std::thread> workers;
            for(unsigned worker=0;worker<8;++worker)workers.emplace_back([&]{for(unsigned i=0;i<64;++i)
                CHECK(Failure([&]{session.Shutdown();}).find("busy")!=std::string::npos);});
            for(auto& worker:workers)worker.join();
        }};
        session.Initialize(backend,state,database);session.Shutdown();control.Empty();
    }
    {
        Control control;FakeModule backend(control);Session session;auto state=std::make_shared<HostState>("C:\\fixture\\");
        CHECK(Failure([&]{session.WithCore([](ICvGameContext3&){});}).find("initialized core")!=std::string::npos);
        ++withCoreRejections;
        session.Initialize(backend,state,database);
        std::thread wrongOwner([&]{
            CHECK(Failure([&]{session.WithCore([](ICvGameContext3&){});}).find("owner thread")!=std::string::npos);
            ++withCoreRejections;
        });wrongOwner.join();
        session.WithCore([&](ICvGameContext3& context){
            (void)context;CHECK(control.alive);
            CHECK(state->gameLock.HeldByCurrentThread() && state->executing==1);
            ++withCoreSuccesses;
            CHECK(Failure([&]{session.WithCore([](ICvGameContext3&){});}).find("busy")!=std::string::npos);
            ++withCoreRejections;
            CHECK(Failure([&]{session.Shutdown();}).find("busy")!=std::string::npos);
            ++withCoreRejections;
            CHECK(Failure([&]{session.Initialize(backend,state,database);}).find("busy")!=std::string::npos);
            ++withCoreRejections;
            std::thread concurrent([&]{
                CHECK(Failure([&]{session.WithCore([](ICvGameContext3&){});}).find("busy")!=std::string::npos);
                ++withCoreRejections;
                CHECK(Failure([&]{session.Shutdown();}).find("busy")!=std::string::npos);
                ++withCoreRejections;
            });concurrent.join();
        });
        CHECK(!state->gameLock.HeldByCurrentThread() && state->executing==0 && session.Phase()==SessionPhase::CoreInitialized);
        CHECK(Failure([&]{session.WithCore([&](ICvGameContext3&){
            CHECK(state->gameLock.HeldByCurrentThread() && state->executing==1);
            throw std::runtime_error("intentional core operation failure");
        });}).find("intentional core operation failure")!=std::string::npos);
        ++withCoreOperationErrors;
        CHECK(!state->gameLock.HeldByCurrentThread() && state->executing==0 && session.Phase()==SessionPhase::CoreInitialized);
        control.bootstrapRefusal=true;
        CHECK(!Failure([&]{session.Shutdown();}).empty() && session.Phase()==SessionPhase::CleanupPending);
        CHECK(Failure([&]{session.WithCore([](ICvGameContext3&){});}).find("initialized core")!=std::string::npos);
        ++withCoreRejections;
        session.Shutdown();control.Empty();
    }
    {
        Control control;FakeModule backend(control);Session session;auto state=std::make_shared<HostState>("C:\\fixture\\");
        for(unsigned i=0;i<64;++i){session.Initialize(backend,state,database);session.Shutdown();control.Empty();}
        CHECK(control.Count("init.after")==64 && control.Count("uninit.after")==64 && state->Events().size()==128);
    }
}
static Control* scriptControl=nullptr;
static unsigned scriptFinalizers=0;
static int FinalizeScript(lua_State*){
    CHECK(scriptControl && scriptControl->module && scriptControl->alive && !scriptControl->globals);
    CHECK(scriptControl->database && scriptControl->ui && scriptControl->engine);
    CHECK(scriptControl->Count("uninit.after")==1 && scriptControl->Count("core-stop.before")==0);
    ++scriptFinalizers;return 0;
}
static int ShutdownFromScript(lua_State* state){
    auto* session=static_cast<Session*>(lua_touserdata(state,1));session->Shutdown();return 0;
}
static int WithCoreFromScript(lua_State* state){
    auto* session=static_cast<Session*>(lua_touserdata(state,1));
    session->WithCore([](ICvGameContext3&){});
    return 0;
}
static void ScriptLifecycle(){
    Database::Connection database;Control control;FakeModule backend(control);Session session;
    ScriptUtilityFixture utility;control.scriptUtility=&utility;
    auto scripts=std::make_shared<ScriptSystem>();auto state=std::make_shared<HostState>("C:\\fixture\\",nullptr,nullptr,scripts);
    session.Initialize(backend,state,database);lua_State* vm;
    {GameCall call(*state);vm=scripts->CreateLuaThread("lifetime");scriptControl=&control;
        CHECK(scripts->RegisterFunction(vm,"finalizeHostProbe",FinalizeScript));
        const char* source="retained=newproxy(true); getmetatable(retained).__gc=finalizeHostProbe";
        CHECK(scripts->Execute(vm,source,std::strlen(source)));
        // Exercise the active-callback shutdown boundary after passing the access guard.
        CHECK(!scripts->CallCFunction(vm,WithCoreFromScript,&session)
              && std::strstr(scripts->LastError(),"quiescent scripts") && state->gameLock.HeldByCurrentThread());
        ++withCoreRejections;
        CHECK(!scripts->CallCFunction(vm,ShutdownFromScript,&session)
              && std::strstr(scripts->LastError(),"active script callback") && state->gameLock.HeldByCurrentThread());
    }
    CHECK(control.globals && control.Count("uninit.before")==0 && scriptFinalizers==0);
    CHECK(session.Phase()==SessionPhase::CleanupPending && scripts->ThreadCount()==1);
    control.hook=[&](const std::string& event){if(event=="core-stop.before" || event=="module-close.before"){
        CHECK(scripts->IsClosed() && scripts->ThreadCount()==0 && scriptFinalizers==1);
    }};
    session.Shutdown();control.Empty();CHECK(session.Phase()==SessionPhase::Empty && scriptFinalizers==1);
    CHECK(Failure([&]{session.Initialize(backend,state,database);}).find("open, quiescent")!=std::string::npos);
    CHECK(session.Phase()==SessionPhase::Empty);scriptControl=nullptr;
    CHECK(utility.registrations==1 && utility.destroys==0 && !scripts->GameLibrariesBound());
    std::puts("SCRIPT_LIFECYCLE_PASS ACTIVE_SHUTDOWN_REJECTED=true FINALIZER_BEFORE_MODULE_RELEASE=true");
}
static void ScriptBindingFailures(){
    Database::Connection database;
    for(const char* fault:{"script-utility.before","script-utility.after","missing"}){
        Control control;FakeModule backend(control);Session session;ScriptUtilityFixture utility;
        if(std::string(fault)!="missing"){control.scriptUtility=&utility;control.fault=fault;control.remaining=1;}
        auto scripts=std::make_shared<ScriptSystem>();auto state=std::make_shared<HostState>("C:\\fixture\\",nullptr,nullptr,scripts);
        CHECK(!Failure([&]{session.Initialize(backend,state,database);}).empty());
        control.Empty();CHECK(session.Phase()==SessionPhase::Empty && scripts->IsClosed());
        CHECK(!state->engineAdapters && !state->userAdapters && !utility.registrations && !utility.destroys);
    }
    std::puts("SCRIPT_LIBRARY_BIND_FAILURES=3");
}
int main(){
    try{AdaptersAndLocks();Sessions();ScriptLifecycle();ScriptBindingFailures();
        CHECK(GetModuleHandleW(L"CvGameCoreDLL_Expansion2_x64.dll")==nullptr);
        std::printf("NATIVE_HOST_TEST_PASS checks=%u STARTUP_FAILURES=16 CLEANUP_RETRY_CASES=12 BUSY_CALLS=512 REENTRY=28 RESTARTS=64 SERVICE_WORK=1024 GAMECORE_LOADED=false WITHCORE_SUCCESS=%u WITHCORE_REJECTIONS=%u WITHCORE_OPERATION_ERRORS=%u\n",
            checks.load(),withCoreSuccesses.load(),withCoreRejections.load(),withCoreOperationErrors.load());return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"UNEXPECTED: %s\n",error.what());return 1;}
}
