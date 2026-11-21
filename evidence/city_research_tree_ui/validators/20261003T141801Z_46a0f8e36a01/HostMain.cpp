#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
// The SDK PCH intentionally suppresses Win32 UI declarations. Import the full
// window API first only for this explicitly separate presentation host.
#include <Windows.h>
#endif
#include "HostRun.h"
#include <cstdio>
#include <cstdlib>
#include <type_traits>
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
#include <werapi.h>
#pragma comment(lib,"wer.lib")
#endif
static_assert(sizeof(void*)==8,"Native host requires x64");
static_assert(!std::is_abstract<ZeroSisHost::EngineServices>::value,"Engine SDK slots incomplete");
static_assert(!std::is_abstract<ZeroSisHost::UserInterface>::value,"UI SDK slots incomplete");
static void RequireGameCoreAbsent() {
    for(const wchar_t* name:{L"CvGameCoreDLL.dll",L"CvGameCoreDLL_Expansion1.dll",L"CvGameCoreDLL_Expansion2.dll",L"CvGameCoreDLL_Expansion2_x64.dll",L"CvGameCoreDLL_Expansion2_x64_probe.dll"})
        if(GetModuleHandleW(name))throw std::runtime_error("A GameCore module was unexpectedly loaded in non-loading mode");
}
static std::wstring AbsoluteCheckpoint(const wchar_t* path){
    if(!path || !*path)throw std::invalid_argument("Interactive restore requires a checkpoint path");
    const DWORD size=GetFullPathNameW(path,0,nullptr,nullptr);
    if(!size)throw std::runtime_error("Cannot resolve the checkpoint path");
    std::vector<wchar_t> buffer(size);
    const DWORD count=GetFullPathNameW(path,size,buffer.data(),nullptr);
    if(!count || count>=size)throw std::runtime_error("Cannot resolve the checkpoint path");
    const DWORD attributes=GetFileAttributesW(buffer.data());
    if(attributes==INVALID_FILE_ATTRIBUTES || (attributes&FILE_ATTRIBUTE_DIRECTORY))
        throw std::invalid_argument("Interactive restore checkpoint is not a file");
    return std::wstring(buffer.data(),count);
}
static int RunHostMain(int argc,wchar_t** argv) {
    std::setvbuf(stdout,nullptr,_IONBF,0);
    std::unique_ptr<ZeroSisHost::HostRun> run;
    try {
        RequireGameCoreAbsent();
        if(argc==2 && std::wcscmp(argv[1],L"--capabilities")==0) {
            std::puts("ZeroSis' native x64 host: SDK EngineUtility4 / UserInterface2 / GameContext3.");
            std::puts("Modes: --verify-bundle; --check-data <language>; --initialize <language>; --check-core <language>; --check-new-game <language>; --check-first-turn <language>; --check-turn-cycle <language>; --check-save-restore <language> [extra-turns]; --check-save-restore-ui <language> [extra-turns]; --check-save-restore-ui-promotions <language> <extra-turns>; --check-save-restore-ui-actions <language> <extra-turns>; --check-found-city <language>; --check-city-decisions <language>; --check-city-production-ui <language>; --check-city-research-ui <language>.");
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
            std::puts("Presentation test: --check-save-restore-ui-window-actions <language> 48; owned HWND with posted test input. ZEROSIS_UI_WINDOW_PROFILE=display-resize enables GPU display/resize captures; display-refresh also redraws the officially closed context on the same window.");
            std::puts("Production hit test: --check-city-production-ui-window <language>; owned unit hit, GPU resize/closed refresh, normal turn and native restore. No human-input or retail-equivalence proof.");
            std::puts("Research input: --check-city-research-ui-window <language>; official TechSelected, owned hit, GPU refresh, normal turn and native restore.");
            std::puts("Research tree: --check-city-research-tree-ui <language>; original chooser handoff, normal research, dirty refresh, horizontal scroll and Escape through owner Lua dispatch; HWND proof remains separate.");
            std::puts("Live production input: --check-city-production-ui-live <language>; category, pointer, panel wheel and scene-generation input boundaries before unit selection.");
            std::puts("Continuous game: --play <language>; persistent strategic world window, owned unit selection/movement, explicit actions, normal end-turn and native saves. --play-smoke uses the same loop with finite posted HWND input.");
            std::puts("Resume game: --play-load <language> <checkpoint>; load a private native save from the exact same engine bundle and continue in the world window. --play-load-smoke validates the same path with posted input.");
#endif
            std::puts("Unsupported engine/UI services throw named errors. Turn-cycle diagnostics cover one configured single-player turn.");
            std::puts("GAMECORE_LOADED=false");return 0;
        }
        if(argc==2 && std::wcscmp(argv[1],L"--verify-bundle")==0) {
            ZeroSisHost::VerifiedBundle bundle(ZeroSisHost::ExecutableDirectory());
            RequireGameCoreAbsent();
            std::printf("BUNDLE_VERIFIED files=%u architecture=x64 GAMECORE_LOADED=false\n",ZeroSisHost::HostBundleFileCount);return 0;
        }
        const bool checkData=argc==3 && std::wcscmp(argv[1],L"--check-data")==0;
        const bool playLoadSmoke=argc==4 && std::wcscmp(argv[1],L"--play-load-smoke")==0;
        const bool playLoad=playLoadSmoke || (argc==4 && std::wcscmp(argv[1],L"--play-load")==0);
        const bool playSmoke=playLoadSmoke || (argc==3 && std::wcscmp(argv[1],L"--play-smoke")==0);
        const bool play=playLoad || playSmoke || (argc==3 && std::wcscmp(argv[1],L"--play")==0);
        const std::wstring playCheckpoint=playLoad?AbsoluteCheckpoint(argv[3]):L"";
#if !defined(ZEROSIS_UI_WINDOW_PRESENTATION)
        if(play)throw std::invalid_argument("Interactive gameplay requires the window presentation host build");
#endif
        const bool initialize=argc==3 && std::wcscmp(argv[1],L"--initialize")==0;
        const bool checkCore=argc==3 && std::wcscmp(argv[1],L"--check-core")==0;
        const bool checkResearchTree=argc==3 && std::wcscmp(argv[1],L"--check-city-research-tree-ui")==0;
        const bool checkResearchWindow=argc==3 && std::wcscmp(argv[1],L"--check-city-research-ui-window")==0;
        const bool checkResearchUi=checkResearchTree || checkResearchWindow || (argc==3 && std::wcscmp(argv[1],L"--check-city-research-ui")==0);
        const bool checkProductionLive=argc==3 && std::wcscmp(argv[1],L"--check-city-production-ui-live")==0;
        const bool checkProductionWindow=checkProductionLive || (argc==3 && std::wcscmp(argv[1],L"--check-city-production-ui-window")==0);
#if !defined(ZEROSIS_UI_WINDOW_PRESENTATION)
        if(checkProductionWindow || checkResearchWindow)throw std::invalid_argument("Production hit input requires a window presentation host build");
#endif
        const bool checkProductionUi=checkProductionWindow || (argc==3 && std::wcscmp(argv[1],L"--check-city-production-ui")==0);
        const bool checkCityDecisions=checkResearchUi || checkProductionUi || (argc==3 && std::wcscmp(argv[1],L"--check-city-decisions")==0);
        const bool checkFoundCity=checkCityDecisions || (argc==3 && std::wcscmp(argv[1],L"--check-found-city")==0);
        const bool checkUiWindow=argc==4 && std::wcscmp(argv[1],L"--check-save-restore-ui-window-actions")==0;
        const char* uiWindowProfile=std::getenv("ZEROSIS_UI_WINDOW_PROFILE");
        const bool refreshClosed=uiWindowProfile && std::strcmp(uiWindowProfile,"display-refresh")==0;
        const bool displayResize=refreshClosed || (uiWindowProfile && std::strcmp(uiWindowProfile,"display-resize")==0);
        if(uiWindowProfile && *uiWindowProfile && (!(checkUiWindow || checkProductionWindow || checkResearchWindow) || !displayResize))
            throw std::invalid_argument("UI window profile requires the explicit window action mode and display-resize or display-refresh value");
        if(checkResearchWindow)std::puts("UI_WINDOW_MODE=LIVE_OFFICIAL_RESEARCH_VM_OWNED_GPU_HWND_CLOSED_SCENE_REFRESH_POSTED_TEST_INPUT");
        if(checkProductionWindow)std::puts(checkProductionLive?
            "UI_WINDOW_MODE=LIVE_OFFICIAL_PRODUCTION_VM_CATEGORY_POINTER_SCROLL_SCENE_GENERATIONS_POSTED_TEST_INPUT":
            "UI_WINDOW_MODE=LIVE_OFFICIAL_PRODUCTION_VM_OWNED_GPU_HWND_CLOSED_SCENE_REFRESH_POSTED_TEST_INPUT");
        if(checkUiWindow)std::puts(refreshClosed?
            "UI_WINDOW_MODE=LIVE_OFFICIAL_VM_OWNED_GPU_HWND_CLOSED_SCENE_REFRESH_POSTED_TEST_INPUT":displayResize?
            "UI_WINDOW_MODE=LIVE_OFFICIAL_VM_OWNED_GPU_HWND_DISPLAY_RESIZE_POSTED_TEST_INPUT":
            "UI_WINDOW_MODE=LIVE_OFFICIAL_VM_OWNED_HIDDEN_HWND_POSTED_TEST_INPUT");
        const bool fixtureUnitActions=checkUiWindow || (argc==4 && std::wcscmp(argv[1],L"--check-save-restore-ui-actions")==0);
        const bool fixturePromotions=fixtureUnitActions || (argc==4 && std::wcscmp(argv[1],L"--check-save-restore-ui-promotions")==0);
        const bool checkUi=fixturePromotions || ((argc==3 || argc==4) && std::wcscmp(argv[1],L"--check-save-restore-ui")==0);
        const bool checkRestore=checkUi || ((argc==3 || argc==4) && std::wcscmp(argv[1],L"--check-save-restore")==0);
        unsigned extraTurns=0;
        if(checkRestore && argc==4){
            const std::wstring value=argv[3];
            if(value.empty() || value.size()>2 || value.find_first_not_of(L"0123456789")!=std::wstring::npos)
                throw std::invalid_argument("Additional restored turns must be a decimal integer from 1 to 98");
            extraTurns=static_cast<unsigned>(std::stoul(value));
            if(!extraTurns || extraTurns>98)throw std::invalid_argument("Additional restored turns must be from 1 to 98");
        }
        const bool checkTurnCycle=checkRestore || (argc==3 && std::wcscmp(argv[1],L"--check-turn-cycle")==0);
        const bool checkFirstTurn=checkFoundCity || checkTurnCycle || (argc==3 && std::wcscmp(argv[1],L"--check-first-turn")==0);
        const bool checkNewGame=(play && !playLoad) || checkFirstTurn || (argc==3 && std::wcscmp(argv[1],L"--check-new-game")==0);
        if(!checkData && !initialize && !checkCore && !checkNewGame && !play) {
            std::fputs("Usage: ZeroSisHost_x64 --capabilities | --verify-bundle | --check-data <language> | --initialize <language> | --check-core <language> | --check-new-game <language> | --check-first-turn <language> | --check-turn-cycle <language> | --check-save-restore <language> [extra-turns] | --check-save-restore-ui <language> [extra-turns] | --check-save-restore-ui-promotions <language> <extra-turns> | --check-save-restore-ui-actions <language> <extra-turns> | --check-found-city <language> | --check-city-decisions <language> | --check-city-production-ui <language> | --check-city-production-ui-window <language> | --check-city-research-ui <language> | --check-city-research-ui-window <language> | --check-city-research-tree-ui <language>\n",stderr);return 2;
        }
        run.reset(new ZeroSisHost::HostRun(ZeroSisHost::ExecutableDirectory()));
        run->Prepare(ZeroSisHost::Utf8(argv[2]));
        std::printf("SESSION_DIRECTORY=%s\n",ZeroSisHost::Utf8(run->SessionDirectory()).c_str());
        std::puts(run->DataObservation().c_str());
        if(initialize || checkCore || checkNewGame || play){run->InitializeCore();std::puts(playLoad?
            "CORE_INITIALIZED; restoring private interactive checkpoint.":checkNewGame?
            "CORE_INITIALIZED; attempting isolated new game.":"CORE_INITIALIZED; new game and turn execution remain unimplemented.");}
        if(checkUi)run->EnableUiPopups(checkUiWindow,displayResize,refreshClosed);
        if(checkCore)std::puts(run->CoreObservation().c_str());
        if(checkNewGame)std::puts(run->NewGameObservation().c_str());
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
        if(play){
            run->InteractivePlay(playSmoke,playCheckpoint);run->Shutdown();RequireGameCoreAbsent();
            std::puts("INTERACTIVE_PLAY_SHUTDOWN_PASS GAMECORE_LOADED=true GAMECORE_UNLOADED=true");return 0;
        }
#endif
        if(checkFirstTurn)std::puts(run->FirstTurnObservation(checkTurnCycle).c_str());
        ZeroSisHost::FoundCityResult founded;
        if(checkFoundCity)founded=run->FoundCityObservation();
        std::wstring checkpoint;std::string checkpointState;
        if(checkRestore || checkFoundCity)checkpoint=run->SaveCheckpoint(checkpointState);
        run->Shutdown();
        if(checkCore)std::puts(run->CoreShutdownObservation().c_str());
        RequireGameCoreAbsent();
        if(initialize || checkCore || checkNewGame)std::puts("CORE_MODULE_UNLOADED=true");
        if(checkFoundCity){
            run.reset();std::puts("FOUND_CITY_RESTORE_FRESH_SESSION=true");
            run.reset(new ZeroSisHost::HostRun(ZeroSisHost::ExecutableDirectory()));
            run->Prepare(ZeroSisHost::Utf8(argv[2]));
            std::printf("FOUND_CITY_RESTORE_SESSION_DIRECTORY=%s\n",ZeroSisHost::Utf8(run->SessionDirectory()).c_str());
            run->InitializeCore();
            ZeroSisHost::CityDecisionResult decisions;
            if(checkCityDecisions)run->RestoreFoundCityCheckpoint(checkpoint,checkpointState,founded,&decisions,checkProductionUi,checkProductionWindow,checkProductionLive,checkResearchUi,checkResearchWindow,checkResearchTree);
            else run->RestoreFoundCityCheckpoint(checkpoint,checkpointState,founded);
            std::wstring decisionCheckpoint;std::string decisionState;
            if(checkCityDecisions)decisionCheckpoint=run->SaveCheckpoint(decisionState);
            run->Shutdown();RequireGameCoreAbsent();
            if(checkCityDecisions){
                run.reset();std::puts("CITY_DECISION_RESTORE_FRESH_SESSION=true");
                run.reset(new ZeroSisHost::HostRun(ZeroSisHost::ExecutableDirectory()));
                run->Prepare(ZeroSisHost::Utf8(argv[2]));
                std::printf("CITY_DECISION_RESTORE_SESSION_DIRECTORY=%s\n",ZeroSisHost::Utf8(run->SessionDirectory()).c_str());
                run->InitializeCore();
                run->RestoreCityDecisionCheckpoint(decisionCheckpoint,decisionState,decisions);
                run->Shutdown();RequireGameCoreAbsent();
                std::puts("CITY_DECISION_RESTORED_CORE_MODULE_UNLOADED=true\nCITY_DECISION_SHUTDOWN_PASS GAMECORE_LOADED=true CITY_DECISIONS_ACCEPTED=true TURN_ADVANCE_VERIFIED=true CITY_DECISION_RESTORE_VERIFIED=true");
                if(checkResearchUi)std::puts(checkResearchTree?
                    "RESEARCH_TREE_UI_SHUTDOWN_PASS ORIGINAL_POPUP_CALLBACK=true SDK_RECEIVER=true TURN_AND_NATIVE_RESTORE=true RETAIL_UI_EQUIVALENCE=false":
                    "RESEARCH_UI_SHUTDOWN_PASS ORIGINAL_POPUP_CALLBACK=true SDK_RECEIVER=true TURN_AND_NATIVE_RESTORE=true RETAIL_UI_EQUIVALENCE=false");
                if(checkProductionUi)std::puts("PRODUCTION_UI_SHUTDOWN_PASS ORIGINAL_POPUP_CALLBACK=true SDK_RECEIVER=true TURN_AND_NATIVE_RESTORE=true RETAIL_UI_EQUIVALENCE=false");
                return 0;
            }
            std::puts("FOUND_CITY_RESTORED_CORE_MODULE_UNLOADED=true\nFOUND_CITY_SHUTDOWN_PASS GAMECORE_LOADED=true CITY_CREATED=true CITY_RESTORE_VERIFIED=true TURN_ADVANCE_VERIFIED=false");
            return 0;
        }
        if(checkRestore){
            run.reset();
            std::puts("NATIVE_RESTORE_FRESH_SESSION=true");
            run.reset(new ZeroSisHost::HostRun(ZeroSisHost::ExecutableDirectory()));
            run->Prepare(ZeroSisHost::Utf8(argv[2]));
            std::printf("RESTORE_SESSION_DIRECTORY=%s\n",ZeroSisHost::Utf8(run->SessionDirectory()).c_str());
            run->InitializeCore();if(checkUi)run->EnableUiPopups(checkUiWindow,displayResize,refreshClosed);
            run->RestoreCheckpoint(checkpoint,checkpointState,extraTurns,fixturePromotions,fixtureUnitActions);
            run->Shutdown();RequireGameCoreAbsent();
            std::puts("RESTORED_CORE_MODULE_UNLOADED=true\nNATIVE_RESTORE_SHUTDOWN_PASS GAMECORE_LOADED=true RESTORE_VERIFIED=true RESUMED_TURN_VERIFIED=true");
            return 0;
        }
        if(checkTurnCycle){std::puts("TURN_CYCLE_SHUTDOWN_PASS GAMECORE_LOADED=true TURN_CYCLE_VERIFIED=true");return 0;}
        if(checkFirstTurn){std::puts("FIRST_TURN_SHUTDOWN_PASS GAMECORE_LOADED=true TURN_ENTRY_VERIFIED=true TURNS_VERIFIED=false");return 0;}
        if(checkNewGame){std::puts("NEW_GAME_SHUTDOWN_PASS GAMECORE_LOADED=true TURNS_VERIFIED=false");return 0;}
        std::puts(checkData?"HOST_DATA_CHECK_PASS GAMECORE_LOADED=false":"CORE_SHUTDOWN_PASS GAMECORE_LOADED=true GAMEPLAY_VERIFIED=false");
        return 0;
    } catch(const std::exception& error) {
        std::fprintf(stderr,"HOST_FAILURE: %s\n",error.what());
    } catch(...) {std::fputs("HOST_FAILURE: unknown exception\n",stderr);}
    if(run) {
        try{run->Shutdown();RequireGameCoreAbsent();std::fputs("HOST_CLEANUP_PASS\nCORE_MODULE_UNLOADED=true\n",stderr);}
        catch(...) {
            // No DLL unload or dependency destruction while cleanup is pending.
            run.release();std::fputs("HOST_CLEANUP_PENDING: dependencies retained until process termination\n",stderr);return 3;
        }
    }
    return 1;
}

#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
static LONG HostWindowException(EXCEPTION_POINTERS* info) {
    const DWORD code=info && info->ExceptionRecord?info->ExceptionRecord->ExceptionCode:0;
    const void* address=info && info->ExceptionRecord?info->ExceptionRecord->ExceptionAddress:nullptr;
    MEMORY_BASIC_INFORMATION memory{};HMODULE module=nullptr;
    if(address && VirtualQuery(address,&memory,sizeof(memory))==sizeof(memory))
        module=static_cast<HMODULE>(memory.AllocationBase);
    wchar_t path[MAX_PATH]={};char text[MAX_PATH*4]={};
    if(module)GetModuleFileNameW(module,path,MAX_PATH);
    if(path[0])WideCharToMultiByte(CP_UTF8,0,path,-1,text,sizeof(text),nullptr,nullptr);
    std::fprintf(stderr,"HOST_NATIVE_EXCEPTION|code=0x%08lX|address=%p|module=%s|base=%p\n",
        static_cast<unsigned long>(code),address,text,module);
    if(info && info->ExceptionRecord){
        const auto* record=info->ExceptionRecord;
        for(DWORD i=0;i<record->NumberParameters && i<EXCEPTION_MAXIMUM_PARAMETERS;++i)
            std::fprintf(stderr,"HOST_NATIVE_EXCEPTION_PARAMETER|index=%lu|value=0x%llX\n",
                static_cast<unsigned long>(i),static_cast<unsigned long long>(record->ExceptionInformation[i]));
    }
    if(info && info->ContextRecord){
        const auto* context=info->ContextRecord;
        std::fprintf(stderr,"HOST_NATIVE_EXCEPTION_CONTEXT|rip=0x%llX|rsp=0x%llX|rcx=0x%llX|rdx=0x%llX|r8=0x%llX|r9=0x%llX\n",
            static_cast<unsigned long long>(context->Rip),static_cast<unsigned long long>(context->Rsp),
            static_cast<unsigned long long>(context->Rcx),static_cast<unsigned long long>(context->Rdx),
            static_cast<unsigned long long>(context->R8),static_cast<unsigned long long>(context->R9));
    }
    std::fflush(stderr);return EXCEPTION_EXECUTE_HANDLER;
}
#endif

int wmain(int argc,wchar_t** argv) {
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX|SEM_NOOPENFILEERRORBOX);
    if(FAILED(WerSetFlags(WER_FAULT_REPORTING_NO_UI))) {
        std::fputs("HOST_FAILURE: Could not suppress diagnostic WER UI\n",stderr);return 1;
    }
    std::fprintf(stderr,"UI_WINDOW_PROCESS_START=%lu\n",static_cast<unsigned long>(GetCurrentProcessId()));
    std::fflush(stderr);
    __try {return RunHostMain(argc,argv);}
    __except(HostWindowException(GetExceptionInformation())) {return static_cast<int>(0xe0000001u);}
#else
    return RunHostMain(argc,argv);
#endif
}
