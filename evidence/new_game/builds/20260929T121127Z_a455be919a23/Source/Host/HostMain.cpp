#include "HostRun.h"
#include <cstdio>
#include <type_traits>
static_assert(sizeof(void*)==8,"Native host requires x64");
static_assert(!std::is_abstract<ZeroSisHost::EngineServices>::value,"Engine SDK slots incomplete");
static_assert(!std::is_abstract<ZeroSisHost::UserInterface>::value,"UI SDK slots incomplete");
static void RequireGameCoreAbsent() {
    for(const wchar_t* name:{L"CvGameCoreDLL.dll",L"CvGameCoreDLL_Expansion1.dll",L"CvGameCoreDLL_Expansion2.dll",L"CvGameCoreDLL_Expansion2_x64.dll",L"CvGameCoreDLL_Expansion2_x64_probe.dll"})
        if(GetModuleHandleW(name))throw std::runtime_error("A GameCore module was unexpectedly loaded in non-loading mode");
}
int wmain(int argc,wchar_t** argv) {
    std::setvbuf(stdout,nullptr,_IONBF,0);
    std::unique_ptr<ZeroSisHost::HostRun> run;
    try {
        RequireGameCoreAbsent();
        if(argc==2 && std::wcscmp(argv[1],L"--capabilities")==0) {
            std::puts("ZeroSis' native x64 host: SDK EngineUtility4 / UserInterface2 / GameContext3.");
            std::puts("Modes: --verify-bundle; --check-data <language>; --initialize <language>; --check-core <language>; --check-new-game <language>; --check-first-turn <language>; --check-turn-cycle <language>; --check-save-restore <language>.");
            std::puts("Unsupported engine/UI services throw named errors. Turn-cycle diagnostics cover one configured single-player turn.");
            std::puts("GAMECORE_LOADED=false");return 0;
        }
        if(argc==2 && std::wcscmp(argv[1],L"--verify-bundle")==0) {
            ZeroSisHost::VerifiedBundle bundle(ZeroSisHost::ExecutableDirectory());
            RequireGameCoreAbsent();
            std::printf("BUNDLE_VERIFIED files=%u architecture=x64 GAMECORE_LOADED=false\n",ZeroSisHost::HostBundleFileCount);return 0;
        }
        const bool checkData=argc==3 && std::wcscmp(argv[1],L"--check-data")==0;
        const bool initialize=argc==3 && std::wcscmp(argv[1],L"--initialize")==0;
        const bool checkCore=argc==3 && std::wcscmp(argv[1],L"--check-core")==0;
        const bool checkRestore=argc==3 && std::wcscmp(argv[1],L"--check-save-restore")==0;
        const bool checkTurnCycle=checkRestore || (argc==3 && std::wcscmp(argv[1],L"--check-turn-cycle")==0);
        const bool checkFirstTurn=checkTurnCycle || (argc==3 && std::wcscmp(argv[1],L"--check-first-turn")==0);
        const bool checkNewGame=checkFirstTurn || (argc==3 && std::wcscmp(argv[1],L"--check-new-game")==0);
        if(!checkData && !initialize && !checkCore && !checkNewGame) {
            std::fputs("Usage: ZeroSisHost_x64 --capabilities | --verify-bundle | --check-data <language> | --initialize <language> | --check-core <language> | --check-new-game <language> | --check-first-turn <language> | --check-turn-cycle <language> | --check-save-restore <language>\n",stderr);return 2;
        }
        run.reset(new ZeroSisHost::HostRun(ZeroSisHost::ExecutableDirectory()));
        run->Prepare(ZeroSisHost::Utf8(argv[2]));
        std::printf("SESSION_DIRECTORY=%s\n",ZeroSisHost::Utf8(run->SessionDirectory()).c_str());
        std::puts(run->DataObservation().c_str());
        if(initialize || checkCore || checkNewGame){run->InitializeCore();std::puts(checkNewGame?
            "CORE_INITIALIZED; attempting isolated new game.":"CORE_INITIALIZED; new game and turn execution remain unimplemented.");}
        if(checkCore)std::puts(run->CoreObservation().c_str());
        if(checkNewGame)std::puts(run->NewGameObservation().c_str());
        if(checkFirstTurn)std::puts(run->FirstTurnObservation(checkTurnCycle).c_str());
        std::wstring checkpoint;std::string checkpointState;
        if(checkRestore)checkpoint=run->SaveCheckpoint(checkpointState);
        run->Shutdown();
        if(checkCore)std::puts(run->CoreShutdownObservation().c_str());
        RequireGameCoreAbsent();
        if(initialize || checkCore || checkNewGame)std::puts("CORE_MODULE_UNLOADED=true");
        if(checkRestore){
            run.reset();
            std::puts("NATIVE_RESTORE_FRESH_SESSION=true");
            run.reset(new ZeroSisHost::HostRun(ZeroSisHost::ExecutableDirectory()));
            run->Prepare(ZeroSisHost::Utf8(argv[2]));
            std::printf("RESTORE_SESSION_DIRECTORY=%s\n",ZeroSisHost::Utf8(run->SessionDirectory()).c_str());
            run->InitializeCore();run->RestoreCheckpoint(checkpoint,checkpointState);
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
