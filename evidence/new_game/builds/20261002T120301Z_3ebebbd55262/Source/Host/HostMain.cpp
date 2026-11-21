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
            std::puts("Modes: --verify-bundle; --check-data <language>; --initialize <language>; --check-core <language>; --check-new-game <language>; --check-first-turn <language>; --check-turn-cycle <language>; --check-save-restore <language> [extra-turns]; --check-save-restore-ui <language> [extra-turns]; --check-save-restore-ui-promotions <language> <extra-turns>; --check-save-restore-ui-actions <language> <extra-turns>; --check-found-city <language>; --check-city-decisions <language>.");
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
        const bool checkCityDecisions=argc==3 && std::wcscmp(argv[1],L"--check-city-decisions")==0;
        const bool checkFoundCity=checkCityDecisions || (argc==3 && std::wcscmp(argv[1],L"--check-found-city")==0);
        const bool fixtureUnitActions=argc==4 && std::wcscmp(argv[1],L"--check-save-restore-ui-actions")==0;
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
        const bool checkNewGame=checkFirstTurn || (argc==3 && std::wcscmp(argv[1],L"--check-new-game")==0);
        if(!checkData && !initialize && !checkCore && !checkNewGame) {
            std::fputs("Usage: ZeroSisHost_x64 --capabilities | --verify-bundle | --check-data <language> | --initialize <language> | --check-core <language> | --check-new-game <language> | --check-first-turn <language> | --check-turn-cycle <language> | --check-save-restore <language> [extra-turns] | --check-save-restore-ui <language> [extra-turns] | --check-save-restore-ui-promotions <language> <extra-turns> | --check-save-restore-ui-actions <language> <extra-turns> | --check-found-city <language> | --check-city-decisions <language>\n",stderr);return 2;
        }
        run.reset(new ZeroSisHost::HostRun(ZeroSisHost::ExecutableDirectory()));
        run->Prepare(ZeroSisHost::Utf8(argv[2]));
        std::printf("SESSION_DIRECTORY=%s\n",ZeroSisHost::Utf8(run->SessionDirectory()).c_str());
        std::puts(run->DataObservation().c_str());
        if(initialize || checkCore || checkNewGame){run->InitializeCore();std::puts(checkNewGame?
            "CORE_INITIALIZED; attempting isolated new game.":"CORE_INITIALIZED; new game and turn execution remain unimplemented.");}
        if(checkUi)run->EnableUiPopups();
        if(checkCore)std::puts(run->CoreObservation().c_str());
        if(checkNewGame)std::puts(run->NewGameObservation().c_str());
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
            if(checkCityDecisions)run->RestoreFoundCityCheckpoint(checkpoint,checkpointState,founded,&decisions);
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
            run->InitializeCore();if(checkUi)run->EnableUiPopups();
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
