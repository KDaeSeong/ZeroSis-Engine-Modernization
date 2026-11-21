#include "MenuOptionsContract.h"
#include "MenuOptionsStore.h"
#include <cstdio>
#include <fstream>
#include <sstream>

using namespace ZeroSisHost;
static int checks=0;
static void Check(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
template<class F> static void Reject(F&& fn,const char* message){bool rejected=false;try{fn();}catch(const std::exception&){rejected=true;}Check(rejected,message);}
static std::wstring ownedDirectory;static unsigned retiredFiles=0;
static std::wstring Join(const std::wstring& path,const wchar_t* name){return path+L"\\"+name;}
static bool Exists(const std::wstring& path){return GetFileAttributesW(path.c_str())!=INVALID_FILE_ATTRIBUTES;}
static std::string Read(const std::wstring& path){std::ifstream f(path,std::ios::binary);return {std::istreambuf_iterator<char>(f),std::istreambuf_iterator<char>()};}
// Retire only this fixture's temporary data within its owned directory. The
// Python owner hashes/measures and deletes every retired path after execution,
// including both aliases of the intentional hardlink-rejection fixture.
static void Remove(const std::wstring& path){
    if(!Exists(path))return;
    if(path.compare(0,ownedDirectory.size()+1,ownedDirectory+L"\\")!=0 || path.find(L'\\',ownedDirectory.size()+1)!=std::wstring::npos)
        throw std::runtime_error("Test-data retirement escaped its exact owned directory");
    const auto attrs=GetFileAttributesW(path.c_str());if(attrs&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT))throw std::runtime_error("Unsafe owned fixture retirement");
    const auto name=path.substr(ownedDirectory.size()+1);const auto retired=Join(ownedDirectory,(L"retired_"+std::to_wstring(retiredFiles++)+L"_"+name).c_str());
    if(!MoveFileExW(path.c_str(),retired.c_str(),MOVEFILE_WRITE_THROUGH))throw std::runtime_error("Cannot retain exact owned test data for cleanup measurement");
}
int wmain(int argc,wchar_t** argv){
    try {
        if(argc!=2)throw std::runtime_error("Need the explicit owned test directory");
        const std::wstring directory(argv[1]);const auto attrs=GetFileAttributesW(directory.c_str());ownedDirectory=directory;
        if(directory.size()<3 || directory[1]!=L':' || attrs==INVALID_FILE_ATTRIBUTES || !(attrs&FILE_ATTRIBUTE_DIRECTORY) || attrs&FILE_ATTRIBUTE_REPARSE_POINT)throw std::runtime_error("Bad owned test directory");
        MenuOptionsValues initial;
        const auto canonical=MenuOptionsValues::Encode(initial);
        Check(MenuOptionsValues::Decode(canonical)==initial,"Canonical round trip failed");
        Check(MenuOptionsValues::SchemaVersion(canonical)==3,"New private settings did not encode V3");
        const std::string legacy="ZEROSIS_PRIVATE_MENU_OPTIONS_V1\nnoBasicHelp=0\nhideTouchHelp=0\nuiCueVolumePercent=100\nwindowWidth=1280\nwindowHeight=720\nfullscreen=0\nvsync=1\n";
        const std::string legacyV2="ZEROSIS_PRIVATE_MENU_OPTIONS_V2\nnoBasicHelp=0\nhideTouchHelp=0\nuiCueVolumePercent=100\nwindowWidth=1280\nwindowHeight=720\nfullscreen=0\nvsync=1\npolicyInfo=0\n";
        Check(MenuOptionsValues::Decode(legacy)==initial,"Original canonical V1 was not readable");
        Check(MenuOptionsValues::Decode(legacyV2)==initial,"Original canonical V2 was not readable");
        auto extended=initial;extended.policyInfo=true;
        Check(MenuOptionsValues::Decode(MenuOptionsValues::Encode(extended)).policyInfo,"Existing PolicyInfo did not survive new V3 round trip");
        for(const auto& bad:std::vector<std::string>{"",canonical+"x",canonical.substr(0,canonical.size()-1),
            "ZEROSIS_PRIVATE_MENU_OPTIONS_V2\n",std::string(513,'x')})
            Reject([&]{MenuOptionsValues::Decode(bad);},"Malformed private settings accepted");
        auto bad=canonical;bad.replace(bad.find("fullscreen=0"),12,"fullscreen=2");
        Reject([&]{MenuOptionsValues::Decode(bad);},"Non-boolean private setting accepted");
        bad=canonical;bad.replace(bad.find("noBasicHelp=0"),13,"noBasicHelp=00");
        Reject([&]{MenuOptionsValues::Decode(bad);},"Noncanonical private setting accepted");
        MenuOptionsCapabilities caps;caps.noBasicHelp=true;caps.uiCueVolume=true;
        caps.windowResolution=true;caps.fullscreen=true;caps.vsync=true;
        MenuOptionsSession session(initial,caps);auto actual=initial;int applies=0,persists=0;
        const auto apply=[&](const MenuOptionsValues& next){++applies;actual=next;return actual;};
        const auto persist=[&](const MenuOptionsValues&){++persists;};
        Reject([&]{session.Set("noBasicHelp",1);},"Inactive edit accepted");
        Reject([&]{session.Begin(-1,1);},"Bad transaction owner accepted");
        session.Begin(0,3);Reject([&]{session.Begin(0,3);},"Nested options transaction accepted");
        session.Set("noBasicHelp",1);session.Set("uiCueVolumePercent",30);
        Check(actual==initial && session.Committed()==initial,"Cached edits changed runtime before Apply");
        Reject([&]{session.Cancel(0,4);},"Changed turn cancelled stale transaction");
        Reject([&]{session.Apply(1,3,apply,persist);},"Changed owner applied stale transaction");
        session.Cancel(0,3);Check(applies==0 && persists==0 && actual==initial,"Cancel called a backend");
        session.Begin(0,3);session.Apply(0,3,apply,persist);
        Check(applies==0 && persists==0,"Unchanged Apply wrote settings");
        session.Begin(0,4);session.Set("uiCueVolumePercent",40);session.Set("fullscreen",1);
        session.Set("windowWidth",1600);session.Set("windowHeight",900);session.Set("vsync",0);
        session.Apply(0,4,apply,persist);
        Check(applies==1 && persists==1 && actual==session.Committed() && !session.Active(),"Apply did not commit verified backend values");
        const auto committed=actual;
        session.Begin(0,5);session.Set("noBasicHelp",1);
        Reject([&]{session.Apply(0,5,apply,[&](const MenuOptionsValues&){throw std::runtime_error("disk full");});},"Persistence failure was swallowed");
        Check(actual==committed && session.Committed()==committed && session.Active(),"Persistence failure did not rollback runtime");
        Reject([&]{session.Apply(0,5,[&](const MenuOptionsValues& next){actual=next;actual.vsync=!next.vsync;return actual;},persist);},"Wrong backend readback accepted");
        Check(session.Faulted(),"Rollback mismatch did not fault the transaction");
        MenuOptionsCapabilities none;MenuOptionsSession disabled(initial,none);disabled.Begin(0,1);
        Reject([&]{disabled.Set("fullscreen",1);},"Unsupported option edit succeeded");
        Reject([&]{disabled.Set("noBasicHelp",1);},"Unsupported noBasicHelp edit succeeded");
        Reject([&]{disabled.Set("retailMusic",1);},"Unknown option edit succeeded");
        disabled.Set("hideTouchHelp",1);disabled.ResetDefaults();Check(disabled.Get("hideTouchHelp")==0,"Defaults did not reset private touch help");
        Reject([&]{disabled.Set("policyInfo",1);},"Unsupported policy display option edit succeeded");
        disabled.Discard();
        {
            auto actualPolicy=initial;MenuOptionsCapabilities policyCaps;policyCaps.policyInfo=true;
            MenuOptionsSession policy(initial,policyCaps);policy.Begin(0,1);policy.Set("policyInfo",1);
            Check(!policy.Committed().policyInfo && !actualPolicy.policyInfo,"PolicyInfo changed before explicit Apply");
            Reject([&]{policy.Set("policyInfo",2);},"PolicyInfo accepted a non-boolean integer");
            int policyWrites=0;
            const auto applyPolicy=[&](const MenuOptionsValues& v){actualPolicy=v;return actualPolicy;};
            Reject([&]{policy.Apply(0,1,applyPolicy,[&](const MenuOptionsValues&){throw std::runtime_error("fixture disk failure");});},
                "Failed PolicyInfo persistence succeeded");
            Check(!actualPolicy.policyInfo && policy.Active(),"PolicyInfo failure did not rollback its actual backend");
            policy.Apply(0,1,applyPolicy,[&](const MenuOptionsValues&){++policyWrites;});
            Check(actualPolicy.policyInfo && policy.Committed().policyInfo && policyWrites==1,"PolicyInfo did not commit actual readback exactly once");
            policy.Begin(0,2);policy.ResetDefaults();Check(policy.Get("policyInfo")==0,"PolicyInfo defaults did not edit the private cache");
            policy.Cancel(0,2);Check(policy.Committed().policyInfo,"Cancelled PolicyInfo defaults persisted");
        }
        MenuOptionsSession failed(initial,caps);failed.Begin(0,1);failed.Set("uiCueVolumePercent",75);bool once=true;
        Reject([&]{failed.Apply(0,1,[&](const MenuOptionsValues& next){actual=next;if(once){once=false;throw std::runtime_error("partial apply");}return actual;},persist);},"Partial backend failure was swallowed");
        Check(actual==initial && failed.Active() && !failed.Faulted(),"Partial backend failure did not restore original state");
        failed.Cancel(0,1);
        MenuOptionsValues saved=initial;saved.hideTouchHelp=true;saved.uiCueVolumePercent=20;
        {
            MenuOptionsStore store(directory);
            Check(store.Read()==initial,"Missing private preferences did not use defaults");
            Reject([&]{MenuOptionsStore other(directory);},"Concurrent private preference writer accepted");
            store.WriteAtomic(saved);Check(store.Read()==saved,"Atomic private preferences did not read back");
            Check(!Exists(Join(directory,L"menu-options.pending")),"Committed pending file remained");
            std::ofstream(Join(directory,L"menu-options.pending"))<<"other task";
            Reject([&]{store.WriteAtomic(initial);},"Existing unrelated pending file was overwritten");
            Check(Read(Join(directory,L"menu-options.pending"))=="other task","Foreign pending data was deleted");
            Remove(Join(directory,L"menu-options.pending"));
            std::ofstream(Join(directory,L"menu-options.zssettings"),std::ios::app)<<"external";
            Reject([&]{store.WriteAtomic(initial);},"External preference edit was overwritten");
        }
        Reject([&]{MenuOptionsStore invalid(directory);},"Corrupt existing preferences were silently reset");
        Remove(Join(directory,L"menu-options.zssettings"));
        {
            MenuOptionsStore store(directory);store.WriteAtomic(saved);
        }
        {
            MenuOptionsStore reopened(directory);Check(reopened.Read()==saved,"Preference reopen lost persisted values");
        }
        Remove(Join(directory,L"menu-options.zssettings"));
        {
            std::ofstream(Join(directory,L"menu-options.zssettings"),std::ios::binary)<<legacy;
            MenuOptionsStore oldStore(directory);auto adopted=oldStore.Read();
            Check(oldStore.SchemaVersion()==1 && Read(Join(directory,L"menu-options.zssettings"))==legacy,
                "Reading V1 rewrote original private preference bytes");
            adopted.policyInfo=true; // The production factory supplies its actual legacy backend value.
            MenuOptionsCapabilities migratedCaps;migratedCaps.policyInfo=true;migratedCaps.noBasicHelp=true;
            MenuOptionsSession migrated(adopted,migratedCaps);auto actualLegacy=adopted;int migrations=0;
            const auto applyLegacy=[&](const MenuOptionsValues& next){actualLegacy=next;return actualLegacy;};
            const auto persistLegacy=[&](const MenuOptionsValues& next){oldStore.WriteAtomic(next);++migrations;};
            migrated.Begin(0,1);migrated.Apply(0,1,applyLegacy,persistLegacy);
            Check(migrations==0 && Read(Join(directory,L"menu-options.zssettings"))==legacy && oldStore.SchemaVersion()==1,
                "Unchanged Apply unnecessarily rewrote legacy private settings");
            migrated.Begin(0,2);migrated.Set("noBasicHelp",1);migrated.Apply(0,2,applyLegacy,persistLegacy);
            Check(migrations==1 && oldStore.SchemaVersion()==3 && oldStore.Read().policyInfo &&
                MenuOptionsValues::SchemaVersion(Read(Join(directory,L"menu-options.zssettings")))==3,
                "First successful changed commit did not preserve adopted PolicyInfo while migrating to V3");
        }
        Remove(Join(directory,L"menu-options.zssettings"));
        {
            const std::string unknown="ZEROSIS_PRIVATE_MENU_OPTIONS_V99\npolicyInfo=1\n";
            std::ofstream(Join(directory,L"menu-options.zssettings"),std::ios::binary)<<unknown;
            Reject([&]{MenuOptionsStore future(directory);},"Unknown future preferences were accepted");
            Check(Read(Join(directory,L"menu-options.zssettings"))==unknown,"Unknown future preference bytes were changed");
        }
        Remove(Join(directory,L"menu-options.zssettings"));
        std::ofstream(Join(directory,L"protected-test-input.txt"),std::ios::binary)<<canonical;
        const bool hardlinkCreated=CreateHardLinkW(Join(directory,L"menu-options.zssettings").c_str(),Join(directory,L"protected-test-input.txt").c_str(),nullptr)!=FALSE;
        const DWORD hardlinkError=hardlinkCreated?0:GetLastError();
        if(hardlinkCreated)Reject([&]{MenuOptionsStore hardlink(directory);},"Hardlinked preferences accepted");
        Check(Read(Join(directory,L"protected-test-input.txt"))==canonical,"Protected dedicated input changed");
        Remove(Join(directory,L"menu-options.zssettings"));
        Remove(Join(directory,L"protected-test-input.txt"));
        Remove(Join(directory,L"menu-options.lock"));
        std::printf("{\"status\":\"PASS\",\"checks\":%d,\"hardlinkFixtureExecuted\":%s,\"hardlinkFixtureError\":%lu,\"hostExecuted\":false,\"sdkExecuted\":false,\"hwndCreated\":false}\n",checks,hardlinkCreated?"true":"false",static_cast<unsigned long>(hardlinkError));
        return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}
}
