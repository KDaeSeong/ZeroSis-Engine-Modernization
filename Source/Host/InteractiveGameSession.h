#pragma once
#include "WorldViewState.h"
#include "LocalSdkSession.h"
#include "LocalTurnController.h"
#include "SdkGameSave.h"
#include "SdkGameRestore.h"
#include "NativeSaveCatalog.h"
#include "SdkStateSnapshot.h"
#include "InteractiveUiSession.h"
#include "TradeRouteSmokeFixture.h"
#include "SocialPolicySmokeFixture.h"
#include "MenuLifecycleSetup.h"
#include "MenuLifecycleRetirement.h"
#include "NativeMapCatalog.h"
#include <algorithm>
#include <array>

namespace ZeroSisHost {

// Lives until explicit Stop(), before GameCore unload. Every method that touches
// SDK objects is called in a short owner-thread Session::WithCore operation.
class InteractiveGameSession final {
public:
    struct LoadHandoff final {
        std::shared_ptr<const NativeSaveArchive> archive;
        std::wstring fileName;
        std::shared_ptr<const MenuLifecycleSetup> setup;
        std::shared_ptr<const MenuLifecycleEndGame> endGame;
        bool mainMenu=false,restart=false;
        bool HasTransition() const noexcept {return !!archive || mainMenu || restart || !!endGame;}
    };
    struct UnitAction final {int unit,mission,data1,data2;std::string name;};
    struct BuildObservation final {int unit,plot,build,progress,time,improvement,expected,mission,missionBuild,moves;};
    struct CombatSmokeFixture final {int kind,attackerOwner,attacker,defenderOwner,defender,x,y;};
    struct DeclareWarSmokeFixture final {int ranged,owner,unit,rivalPlayer,rivalTeam,targetUnit,x,y;};
    struct CityCaptureSmokeFixture final {int attackerOwner,attacker,defenderOwner,oldCity,x,y,capitalCity,defenderCitiesBefore,declaredWar,capitalCreated,metForFixture;};
    struct CapturedCityObservation final {int cityID,owner,isPuppet,isRazing,originalOwner;};
    InteractiveGameSession(std::shared_ptr<HostState> host,std::wstring directory,std::wstring bundle)
        :owner_(std::move(host)),host_(CheckedHost(owner_)),directory_(std::move(directory)),bundle_(std::move(bundle)){}
    ~InteractiveGameSession(){if(vm_ || local_ || game_ || map_ || team_ || receiver_ || saves_ || saveCatalog_ || turns_ || ui_ || core_ || retirement_)std::terminate();}
    void Begin(ICvGameContext3& context,const std::wstring& checkpoint=L"",
               std::shared_ptr<const NativeSaveArchive> decodedArchive={}){
        Owner();if(game_ || vm_)throw std::logic_error("Interactive game already started");
        std::shared_ptr<const NativeSaveArchive> restored=std::move(decodedArchive);
        if(restored || !checkpoint.empty()){
            if(restored)SdkGameRestore::LoadArchive(context,host_,*restored,bundle_);
            else restored=std::make_shared<const NativeSaveArchive>(SdkGameRestore::Load(context,host_,checkpoint,bundle_));
            std::printf("INTERACTIVE_RESTORE_CHECKPOINT=%s\nINTERACTIVE_RESTORE_IDENTITY=%d|%d|%d|%zu\n",
                Utf8(checkpoint).c_str(),restored->turn,restored->elapsed,restored->activePlayer,restored->sections.size());
        }
        game_.reset(context.GetGame());map_.reset(context.GetMap());receiver_.reset(context.GetNetMessageHandler());
        if(!game_ || !map_ || !receiver_ || !game_->IsFinalInitialized() || game_->IsGameMultiPlayer())
            throw std::logic_error("Interactive game requires an initialized single-player SDK game");
        team_.reset(context.GetTeam(game_->GetActiveTeam()));
        if(!team_ || !team_->IsAlive())throw std::logic_error("Interactive game requires a live active team");
        vm_=host_.scripts->CreateLuaThread("Interactive game commands");
        moveMission_=Mission(context,"MISSION_MOVE_TO");swapMission_=Mission(context,"MISSION_SWAP_UNITS");skipMission_=Mission(context,"MISSION_SKIP");
        foundMission_=Mission(context,"MISSION_FOUND");rangeMission_=Mission(context,"MISSION_RANGE_ATTACK");
        LocalSdkSession::LiveMissionProfile profile{[this](int unit,MissionTypes mission,int x,int y,int flags){
            return IsMissionLegal(unit,mission,x,y,flags);
        },[this](int city,TaskTypes task,int data1,int data2,bool option,bool alt,bool shift,bool control){
            return IsCaptureCityTaskLegal(city,task,data1,data2,option,alt,shift,control);
        },[this](PlayerTypes liberated,int city){
            return IsCaptureCityLiberationLegal(liberated,city);
        },[this](TeamTypes from,TeamTypes rival){
            return Query("ZeroSisLiveResult=assert(Teams["+std::to_string(static_cast<int>(from))+
                "]):CanDeclareWar("+std::to_string(static_cast<int>(rival))+")");
        }};
        profile.canFoundPantheon=[this](PlayerTypes player,BeliefTypes belief){
            return IsPantheonLegal(player,belief);
        };
        local_.reset(new LocalSdkSession(host_,*receiver_,*game_,context,std::move(profile)));
        saves_.reset(new SdkGameSave(context,host_,directory_,bundle_));
        core_=&context;saveCatalog_=std::make_shared<NativeSaveCatalog>(directory_);
        mapCatalog_=std::make_shared<NativeMapCatalog>(directory_);
        retirement_.reset(new MenuLifecycleRetirement(context,host_,directory_));
        host_.saveReplay=[this](){return retirement_->SaveReplay();};
        host_.recordVictoryInformation=[this](int score){return retirement_->RecordVictoryInformation(score);};
        host_.recordLeaderboardScore=[this](int score){return retirement_->RecordLeaderboardScore(score);};
        host_.openEndGameMenu=[this](){retirement_->OpenEndGameMenu();};
        host_.restartGame=[this](){
            Owner();if(!restartArmed_ || restartObserved_)throw std::logic_error("SDK restart callback has no unique owner request");
            restartObserved_=true;
        };
        const auto nativeAutoSave=host_.autoSave;
        host_.autoSave=[this,nativeAutoSave](bool initial,bool postTurn){
            saveCatalog_->PrepareForMutation();
            nativeAutoSave(initial,postTurn);
            saveCatalog_->ObserveWrittenSave(saves_->LastPath(),CaptureSaveMenuHeader());
        };
        turns_.reset(new LocalTurnController(host_,*game_));
        game_->InitTacticalAnalysisMap(map_->NumPlots());
        for(int id=0;id<MAX_PLAYERS;++id){
            std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(id)));
            if(!player || player->GetID()!=id)throw std::runtime_error("Interactive startup lacks a player slot");
            player->LaterInit();
        }
        game_->DoGameStarted();
        // CvPlayer::Write does not serialize m_aOptions. This interactive
        // profile's explicit manual end-turn preference is session policy,
        // so bind it through the ordinary SDK option command on fresh/load.
        // The SDK still decides readiness; no canEndTurn value is forced.
        host_.localCommands.SendPlayerOption(PLAYEROPTION_WAIT_END_TURN,true);
        std::puts("INTERACTIVE_MANUAL_END_TURN_POLICY=PLAYEROPTION_WAIT_END_TURN:1");
        std::string beforeIdle;
        if(restored){
            beforeIdle=SdkStateSnapshot::Capture(host_);
            const auto written=saves_->Capture(false,false);
            const unsigned equal=SdkGameRestore::VerifyRoundtrip(context,*restored,written);
            if(restored->sections[2].bytes!=written.sections[2].bytes)
                std::printf("INTERACTIVE_RESTORE_SECTION_CHANGED=%u|%u\n",restored->sections[2].kind,restored->sections[2].index);
            NativeSaveArchive::WriteAtomic(directory_+L"\\play-restored-checkpoint.zssave",written.Encode());
            std::printf("INTERACTIVE_RESTORE_SECTIONS_EQUAL=%u|%zu\n",equal,restored->sections.size());
        }
        for(unsigned update=0;update<3;++update)game_->Update();
        Check();
        if(!HumanTurn() || !host_.turnSignals.CivsProcessed() || !host_.turnSignals.LocalPlayerProcessed())
            throw std::runtime_error("Interactive SDK startup did not reach the human input boundary");
        if(restored){
            if(game_->GetGameTurn()!=restored->turn || game_->GetElapsedGameTurns()!=restored->elapsed ||
               game_->GetActivePlayer()!=restored->activePlayer || SdkStateSnapshot::Capture(host_)!=beforeIdle)
                throw std::runtime_error("Interactive restored human turn changed during idle startup");
            std::puts("INTERACTIVE_RESTORE_IDLE_STATE_UNCHANGED=true");
        }
        ui_.reset(new InteractiveUiSession(owner_,context,directory_));
        status_=L"\uc67c\ucabd \ud074\ub9ad\uc73c\ub85c \uc720\ub2db \uc120\ud0dd, \uc624\ub978\ucabd \ud074\ub9ad\uc73c\ub85c \uc774\ub3d9\ud569\ub2c8\ub2e4.";
        std::printf("INTERACTIVE_GAME_STARTED=%d|%d|%d|%d\n",game_->GetGameTurn(),game_->GetActivePlayer(),map_->GetGridWidth(),map_->GetGridHeight());
    }
    void Stop(){
        Owner();if(host_.scripts && !host_.scripts->IsQuiescent())throw std::logic_error("Interactive callbacks must finish before shutdown");
        if(ui_){ui_->Stop();ui_.reset();}
        host_.saveReplay={};host_.recordVictoryInformation={};host_.recordLeaderboardScore={};
        host_.openEndGameMenu={};host_.restartGame={};host_.applyMenuOptions={};
        retirement_.reset();pendingLifecycle_=LoadHandoff{};restartArmed_=restartObserved_=false;
        mapMenuCatalog_.reset();mapCatalog_.reset();
        loadMenuCatalog_.reset();loadMenuBundleManifest_.clear();pendingLoad_=LoadHandoff{};pendingExit_=false;
        turns_.reset();saves_.reset();saveCatalog_.reset();core_=nullptr;local_.reset();
        if(vm_){host_.scripts->FreeLuaThread(vm_);vm_=nullptr;}
        receiver_.reset();team_.reset();map_.reset();game_.reset();
        std::puts("INTERACTIVE_GAME_SESSION_STOPPED=true");
    }
    bool Select(int unitID){
        Owner();if(!HumanTurn())return Reject(L"\ud604\uc7ac\ub294 \uc720\ub2db\uc744 \uc120\ud0dd\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");
        const auto unit=Unit(unitID);
        if(!unit || unit->IsBusy() || unit->IsDelayedDeathExported())return Reject(L"\uc120\ud0dd\ud560 \uc218 \uc5c6\ub294 \uc720\ub2db\uc785\ub2c8\ub2e4.");
        host_.selectLocalUnit(unitID);
        status_=L"\uc774\ub3d9\ud560 \ud0c0\uc77c\uc744 \uc624\ub978\ucabd \ubc84\ud2bc\uc73c\ub85c \ud074\ub9ad\ud558\uc2ed\uc2dc\uc624.";
        std::printf("INTERACTIVE_UNIT_SELECTED=%d|%d|%d|%d\n",game_->GetGameTurn(),unitID,unit->GetX(),unit->GetY());return true;
    }
    void SelectInitialReadyUnit(bool restored){
        Owner();
        if(!HumanTurn() || !host_.scripts || !host_.scripts->IsQuiescent() || !host_.localCommands.IsQuiescent() ||
           !host_.selectLocalUnit || (ui_ && ui_->HasModal()) || host_.popupVisible || host_.cityScreenUp)
            throw std::logic_error("Initial unit selection requires the settled human world-input boundary");
        // Begin/restore and play-initial-state are observed before this ordinary
        // selection command. SelectUnit legitimately increments the serialized
        // m_iEverSelectedCount; the semantic sample below does not cover it and
        // must not be interpreted as byte-identical complete SDK/save state.
        const auto before=SdkStateSnapshot::Capture(host_);
        SdkStateSnapshot::Write(directory_+L"\\play-initial-selection-before-state.txt",before);
        std::unique_ptr<ICvRandom1> random(game_->GetRandomNumberGenerator());
        if(!random)throw std::logic_error("Initial unit selection has no synchronous RNG");
        const auto seed=random->GetSeed();const auto selected=host_.localSelection.Snapshot();
        const auto ready=ReadyUnits();int unitID=-1;const char* outcome="none-ready";
        if(!selected.empty()){
            if(selected.size()!=1 || selected.front().first!=game_->GetActivePlayer())
                throw std::logic_error("Initial unit selection found an invalid existing selection");
            unitID=selected.front().second;outcome="existing";
        }else if(!ready.empty()){
            unitID=ready.front();
            const auto unit=Unit(unitID);
            if(!unit || !unit->ReadyToSelect() || unit->IsBusy() || unit->IsDelayedDeathExported() || !Select(unitID))
                throw std::runtime_error("Initial ready unit became unavailable before native selection");
            const auto actual=host_.localSelection.Snapshot();
            if(actual.size()!=1 || actual.front().first!=game_->GetActivePlayer() || actual.front().second!=unitID)
                throw std::runtime_error("Initial native selection did not retain its ready unit");
            outcome="selected";
        }
        Check();const auto after=SdkStateSnapshot::Capture(host_);
        SdkStateSnapshot::Write(directory_+L"\\play-initial-selection-after-state.txt",after);
        if(before!=after || seed!=random->GetSeed())
            throw std::runtime_error("Initial unit selection changed the semantic gameplay sample or synchronous RNG");
        std::printf("INTERACTIVE_INITIAL_UNIT_SELECTION=%s|%d|%d|%d|%zu|%s|SEMANTIC_SAMPLE_UNCHANGED|RNG_UNCHANGED|SDK_SELECTION_EFFECTS_ALLOWED\n",
            restored?"restore":"fresh",game_->GetGameTurn(),game_->GetActivePlayer(),unitID,ready.size(),outcome);
    }
    bool SelectPlot(int x,int y){
        Owner();if(!HumanTurn() || !InMap(x,y) || (ui_ && ui_->HasModal()))return false;
        std::unique_ptr<ICvPlot1> plot(map_->GetPlot(x,y));if(!plot)return false;
        // LocationSelect lives in the closed engine. Resolve an owned unit
        // without issuing a mission; an empty tile clears the unit selection.
        const int count=plot->GetNumUnits();if(count<0 || count>100000)throw std::runtime_error("Selection plot exceeds its unit bound");
        for(int index=0;index<count;++index){
            std::unique_ptr<ICvUnit1> unit(plot->GetUnitByIndex(index));
            if(unit && unit->GetOwner()==game_->GetActivePlayer() && !unit->IsBusy() && !unit->IsDelayedDeathExported())
                return Select(unit->GetID());
        }
        host_.localSelection.Clear();host_.selectedUnitRevealingNewPlots=false;
        std::printf("INTERACTIVE_PLOT_SELECTION_CLEARED=%d|%d|%d\n",game_->GetGameTurn(),x,y);return true;
    }
    bool Move(int x,int y,bool shift=false){
        Owner();if(!HumanTurn() || !InMap(x,y) || (ui_ && ui_->HasModal()))return false;
        const auto selection=host_.localSelection.Snapshot();
        if(selection.size()!=1 || selection.front().first!=game_->GetActivePlayer())return false;
        const int id=selection.front().second;auto unit=Unit(id);
        std::unique_ptr<ICvPlot1> target(map_->GetPlot(x,y));
        if(!unit || !target || unit->IsBusy() || unit->IsDelayedDeathExported())return false;
        const int rangeRival=ReadIntegerQuery("ZeroSisLiveInteger=assert(Players[Game.GetActivePlayer()]:GetUnitByID("+
            std::to_string(id)+")):GetDeclareWarRangeStrike(assert(Map.GetPlot("+std::to_string(x)+","+std::to_string(y)+")))");
        if(rangeRival!=NO_TEAM){
            if(!ui_ || rangeRival<0 || rangeRival>=MAX_TEAMS)throw std::logic_error("World range declaration has no valid original UI route");
            ui_->Queue(CvPopupInfo(BUTTONPOPUP_DECLAREWARRANGESTRIKE,rangeRival,x,y,0,false,false));
            std::printf("INTERACTIVE_DECLARE_WAR_WORLD_ROUTE=%d|%d|%d|%d|%d|1\n",game_->GetGameTurn(),id,rangeRival,x,y);return true;
        }
        // Original WorldView.lua: a plain right release on the current plot
        // cancels orders; Shift preserves the append-to-queue meaning.
        if(!shift && unit->GetX()==x && unit->GetY()==y){
            unit.reset();target.reset();
            host_.localCommands.SendUnitCommand(id,COMMAND_CANCEL_ALL,-1,-1,false);
            game_->Update();Check();
            std::printf("INTERACTIVE_WORLD_ORDER_CANCELLED=%d|%d|%d|%d\n",game_->GetGameTurn(),id,x,y);return true;
        }
        const bool hostile=VisibleHostile(*target,unit->GetTeam());
        if(hostile && Query("ZeroSisLiveResult=assert(Players[Game.GetActivePlayer()]:GetUnitByID("+
                std::to_string(id)+")):CanRangeStrikeAt("+std::to_string(x)+","+std::to_string(y)+",true,false)")){
            // Stock WorldView uses MOVE_TO for air strikes and RANGE_ATTACK
            // for ground ranged units, rather than testing IsRanged alone.
            const auto mission=unit->GetDomainType()==DOMAIN_AIR?moveMission_:rangeMission_;
            unit.reset();target.reset();
            return SendSelectedMission(mission,x,y,L"\uacf5\uaca9 \uba85\ub839\uc744 \ubcf4\ub0c8\uc2b5\ub2c8\ub2e4.",0,shift);
        }
        // The original SDK move/attack path queues DeclareWarPopup before it
        // changes war state. Its retained Yes/No callbacks own the decision.
        const int moveRival=unit->GetDeclareWarMove(target.get());
        const bool swap=unit->CanSwapWithUnitHere(target.get());
        if(!swap && !CanStartMission(id,moveMission_,x,y))return false;
        unit.reset();
        // CvGame decides MOVE_TO versus SWAP_UNITS and forwards the queue
        // flag through the real SDK receiver. Alt/Ctrl are intentionally not
        // passed: the original BNW Lua wrapper also ignores them for movement.
        game_->SelectionListMove(target.get(),shift);target.reset();
        game_->Update();Check();
        if(moveRival!=NO_TEAM && ui_ && ui_->HasModal()){
            std::printf("INTERACTIVE_DECLARE_WAR_WORLD_ROUTE=%d|%d|%d|%d|%d|0\n",game_->GetGameTurn(),id,moveRival,x,y);return true;
        }
        std::printf("INTERACTIVE_WORLD_MOVE_ROUTE=%d|%d|%d|%d|%d|%d\n",game_->GetGameTurn(),id,x,y,shift?1:0,swap?1:0);
        std::printf("INTERACTIVE_MISSION_ACCEPTED=%d|%d|%d|%d|%d\n",game_->GetGameTurn(),id,static_cast<int>(swap?swapMission_:moveMission_),x,y);return true;
    }
    // Finite smoke fixture: exhausted movement makes a queued destination
    // observable without waiting for a whole turn. Manual input never calls it.
    void PrepareQueuedMoveSmoke(int id){
        Owner();if(!HumanTurn())throw std::logic_error("Queued movement fixture requires the human turn");
        Execute("assert(Players[Game.GetActivePlayer()]:GetUnitByID("+std::to_string(id)+")):FinishMoves()");
        std::printf("INTERACTIVE_QUEUED_MOVE_FIXTURE=%d|FINISH_MOVES\n",id);
    }
    std::array<int,6> ObserveQueuedMove(int id){
        Owner();auto unit=Unit(id);if(!unit)throw std::logic_error("Queued movement unit is missing");
        std::unique_ptr<ICvMissionData1> mission(unit->GetHeadMissionData());
        return {{unit->GetX(),unit->GetY(),unit->MovesLeft(),mission?static_cast<int>(mission->GetMissionType()):-1,
            mission?mission->GetData1():-1,mission?mission->GetData2():-1}};
    }
    bool Skip(){return SendSelectedMission(skipMission_,-1,-1,L"\uc120\ud0dd\ud55c \uc720\ub2db\uc774 \uc774\ubc88 \ud134\uc744 \ub300\uae30\ud569\ub2c8\ub2e4.");}
    bool Found(){return SendSelectedMission(foundMission_,-1,-1,L"\ub3c4\uc2dc\ub97c \uac74\uc124\ud588\uc2b5\ub2c8\ub2e4.");}
    std::vector<UnitAction> AvailableUnitActions(ICvGameContext3& context){
        Owner();std::vector<UnitAction> result;if(!HumanTurn() || (ui_ && ui_->HasModal()))return result;
        const auto selected=host_.localSelection.Snapshot();
        if(selected.size()!=1 || selected.front().first!=game_->GetActivePlayer())return result;
        const int id=selected.front().second;const auto unit=Unit(id);
        // The original UnitPanel.lua hides these mission actions without
        // movement points. CanStartMission alone does not enforce that UI gate.
        if(!unit || unit->MovesLeft()<=0 || unit->IsBusy() || unit->IsDelayedDeathExported())return result;
        // Enumerate only real SDK build rows before asking CanStartMission.
        // An arbitrary Lua/DTO integer must never reach GC.getBuildInfo first.
        const int count=context.GetNumBuildInfos();
        if(count<0 || count>4096)throw std::runtime_error("SDK build catalog exceeds the interactive bound");
        std::string builds="{";
        for(int index=0;index<count;++index){
            std::unique_ptr<ICvBuildInfo1> info(context.GetBuildInfo(static_cast<BuildTypes>(index)));
            if(!info)continue;
            const char* type=info->GetType();
            if(!type || !*type || context.GetInfoTypeForString(type,true)!=index)
                throw std::runtime_error("Interactive build catalog identity differs from SDK rules");
            builds+=std::to_string(index)+",";
        }
        builds+="}";
        Execute("local p=assert(Players[Game.GetActivePlayer()]);local u=assert(p:GetUnitByID("+std::to_string(id)+"));"
            "ZeroSisLiveUnitActions={};local function add(m,d1,d2,label) "
            "assert(m and m.ID>=0);if u:CanStartMission(m.ID,d1,d2,u:GetPlot(),0) then "
            "table.insert(ZeroSisLiveUnitActions,{u:GetID(),m.ID,d1,d2,label or m.Description}) end end;"
            "for _,name in ipairs({'MISSION_FORTIFY','MISSION_HEAL','MISSION_SLEEP','MISSION_ALERT','MISSION_PILLAGE'}) do "
            "add(assert(GameInfo.Missions[name]),-1,-1) end;"
            "local mission=assert(GameInfo.Missions.MISSION_BUILD);for _,id in ipairs("+builds+") do "
            "local build=assert(GameInfo.Builds[id]);assert(build.ID==id);add(mission,id,-1,build.Description) end");
        if(!host_.scripts->CallCFunction(vm_,&ReadUnitActions,&result))throw std::runtime_error(host_.scripts->LastError());
        for(auto& action:result){
            if(action.unit!=id)throw std::runtime_error("Interactive action belongs to another unit");
            auto localized=Localization::Lookup(action.name.c_str());const char* text=localized.toUTF8();
            if(!text || !*text)throw std::runtime_error("Interactive action has no localized label");
            action.name=text;
        }
        return result;
    }
    bool PerformUnitAction(const UnitAction& action){
        Owner();const auto selected=host_.localSelection.Snapshot();
        if(selected.size()!=1 || selected.front().first!=game_->GetActivePlayer() || selected.front().second!=action.unit)
            return Reject(L"\uc120\ud0dd\ud55c \uc720\ub2db\uc774 \ubc14\ub00c\uc5c8\uc2b5\ub2c8\ub2e4.");
        const auto unit=Unit(action.unit);
        if(!unit || unit->MovesLeft()<=0)
            return Reject(L"\ub0a8\uc740 \uc774\ub3d9\ub825\uc774 \uc5c6\uc2b5\ub2c8\ub2e4.");
        const bool accepted=SendSelectedMission(static_cast<MissionTypes>(action.mission),action.data1,action.data2,
            L"\uc720\ub2db \ud589\ub3d9\uc744 \uc2dc\uc791\ud588\uc2b5\ub2c8\ub2e4.");
        if(accepted)std::printf("INTERACTIVE_UNIT_ACTION=%d|%d|%d|%d|%d\n",game_->GetGameTurn(),action.unit,action.mission,action.data1,action.data2);
        return accepted;
    }
    // Only the explicit finite smoke driver calls this setup. Manual games
    // obtain workers through the ordinary SDK production rules.
    int CreateWorkerBuildSmokeFixture(){
        Owner();if(!HumanTurn() || (ui_ && ui_->HasModal()))throw std::logic_error("Worker fixture requires an idle human turn");
        return ReadIntegerQuery("local id=Game.GetActivePlayer();local p=assert(Players[id]);"
            "local build=assert(GameInfo.Builds.BUILD_FARM);local target=nil;"
            "for i=0,Map.GetNumPlots()-1 do local plot=Map.GetPlotByIndex(i);"
            "if plot:GetOwner()==id and not plot:IsCity() and plot:GetImprovementType()==-1 and "
            "plot:GetNumUnits()==0 and p:CanBuild(plot,build.ID,0,0,1) then target=plot;break end end;"
            "assert(target,'Worker fixture has no owned legal unimproved farm plot');"
            "local u=assert(p:InitUnit(assert(GameInfo.Units.UNIT_WORKER).ID,target:GetX(),target:GetY(),-1));"
            "assert(u:CanStartMission(assert(GameInfo.Missions.MISSION_BUILD).ID,build.ID,-1,target,0));"
            "ZeroSisLiveInteger=u:GetID()");
    }
    // Finite --combat smoke only. These are explicit units and a one-HP ranged
    // target, not replacements for production, combat rules, or manual games.
    CombatSmokeFixture CreateCombatSmokeFixture(int kind){
        Owner();if(!HumanTurn() || (ui_ && ui_->HasModal()) || (kind!=0 && kind!=1))
            throw std::logic_error("Combat fixture requires an idle human turn and a known scenario");
        Execute("local id=Game.GetActivePlayer();local p=assert(Players[id]);local team=p:GetTeam();"
            "local barbarian=nil;for n=0,63 do local other=assert(Players[n]);if other:IsBarbarian() then barbarian=other;break end end;"
            "assert(barbarian and Teams[team]:IsAtWar(barbarian:GetTeam()),'Combat fixture requires the existing barbarian war');"
            "local function free(plot) return plot and plot:IsVisible(team,false) and not plot:IsWater() and not plot:IsMountain() "
            "and not plot:IsCity() and plot:GetNumUnits()==0 and (plot:GetOwner()==-1 or plot:GetOwner()==id) end;"
            "local origin,target=nil,nil;for i=0,Map.GetNumPlots()-1 do local a=Map.GetPlotByIndex(i);if free(a) then "
            "for d=0,5 do local b=Map.PlotDirection(a:GetX(),a:GetY(),d);if free(b) and barbarian:CanFound(b:GetX(),b:GetY()) then origin,target=a,b;break end end end;"
            "if origin then break end end;assert(origin and target,'No visible empty adjacent combat fixture plots');"
            "local a=assert(p:InitUnit(assert(GameInfo.Units."+std::string(kind==0?"UNIT_WARRIOR":"UNIT_ARCHER")+
            ").ID,origin:GetX(),origin:GetY(),-1));"
            "local b=assert(barbarian:InitUnit(assert(GameInfo.Units.UNIT_WARRIOR).ID,target:GetX(),target:GetY(),-1));"
            +std::string(kind==1?"b:SetDamage(b:GetMaxHitPoints()-1);":"")+
            "assert(a:GetX()==origin:GetX() and a:GetY()==origin:GetY() and b:GetX()==target:GetX() and b:GetY()==target:GetY());"
            "ZeroSisLiveCombatFixture={a:GetID(),barbarian:GetID(),b:GetID(),target:GetX(),target:GetY()}");
        CombatSmokeFixture result{kind,static_cast<int>(game_->GetActivePlayer()),-1,-1,-1,-1,-1};
        int* fields[]={&result.attacker,&result.defenderOwner,&result.defender,&result.x,&result.y};
        for(int index=0;index<5;++index)*fields[index]=ReadIntegerQuery("ZeroSisLiveInteger=ZeroSisLiveCombatFixture["+std::to_string(index+1)+"]");
        if(!IsAttackLegal(result.attacker,result.x,result.y,kind==1))throw std::runtime_error("Original SDK rejected the combat fixture target");
        return result;
    }
    // Finite --declare-war smoke only. Real SDK units start at peace; the
    // original popup must make the only war decision through native input.
    DeclareWarSmokeFixture CreateDeclareWarSmokeFixture(bool ranged){
        Owner();if(!HumanTurn() || (ui_ && ui_->HasModal()))
            throw std::logic_error("War fixture requires an idle human turn");
        Execute("local id=Game.GetActivePlayer();local p=assert(Players[id]);local team=p:GetTeam();"
            "local ownTeam=assert(Teams[team]);local rival=nil;for n=0,63 do local other=Players[n];"
            "if other and n~=id and other:IsAlive() and not other:IsHuman() and not other:IsMinorCiv() and not other:IsBarbarian() "
            "and other:GetTeam()~=team and not ownTeam:IsAtWar(other:GetTeam()) "
            "and (not ownTeam:IsHasMet(other:GetTeam()) or ownTeam:CanDeclareWar(other:GetTeam())) "
            "then rival=other;break end end;assert(rival,'No peaceful living major for original war fixture');"
            "if not ownTeam:IsHasMet(rival:GetTeam()) then ownTeam:Meet(rival:GetTeam(),false) end;"
            "assert(ownTeam:CanDeclareWar(rival:GetTeam()),'Original SDK rejected declaration after meeting the fixture major');"
            "local function free(plot) return plot and plot:IsVisible(team,false) and not plot:IsWater() and not plot:IsMountain() "
            "and not plot:IsCity() and plot:GetNumUnits()==0 and plot:GetOwner()==-1 end;"
            "local origin,target=nil,nil;for i=0,Map.GetNumPlots()-1 do local a=Map.GetPlotByIndex(i);if free(a) then "
            "for d=0,5 do local b=Map.PlotDirection(a:GetX(),a:GetY(),d);if free(b) then origin,target=a,b;break end end end;"
            "if origin then break end end;assert(origin and target,'No visible adjacent peaceful fixture plots');"
            "local a=assert(p:InitUnit(assert(GameInfo.Units."+std::string(ranged?"UNIT_ARCHER":"UNIT_WARRIOR")+
            ").ID,origin:GetX(),origin:GetY(),-1));"
            "local b=assert(rival:InitUnit(assert(GameInfo.Units.UNIT_WARRIOR).ID,target:GetX(),target:GetY(),-1));"
            +std::string(ranged?"b:SetDamage(b:GetMaxHitPoints()-1);":"")+
            "assert(not ownTeam:IsAtWar(rival:GetTeam()),'Fixture must not declare war');"
            +std::string(ranged?"assert(a:GetDeclareWarRangeStrike(target)==rival:GetTeam(),"
                "'Original SDK did not request ranged war confirmation for this fixture');":"")+
            "ZeroSisLiveWarFixture={a:GetID(),rival:GetID(),rival:GetTeam(),b:GetID(),target:GetX(),target:GetY()}");
        DeclareWarSmokeFixture result{ranged?1:0,static_cast<int>(game_->GetActivePlayer()),-1,-1,-1,-1,-1,-1};
        int* fields[]={&result.unit,&result.rivalPlayer,&result.rivalTeam,&result.targetUnit,&result.x,&result.y};
        for(int index=0;index<6;++index)*fields[index]=ReadIntegerQuery("ZeroSisLiveInteger=ZeroSisLiveWarFixture["+std::to_string(index+1)+"]");
        if(result.unit<0 || result.rivalPlayer<0 || result.rivalTeam<0 || result.targetUnit<0 || !InMap(result.x,result.y) ||
           DeclareWarFixtureAtWar(result))throw std::runtime_error("Original war fixture has an invalid identity or is already hostile");
        if(!ranged){
            // The SDK exposes GetDeclareWarMove through ICvUnit1, not Lua.
            // Use the same native query as the ordinary world move route.
            auto unit=Unit(result.unit);
            std::unique_ptr<ICvPlot1> target(map_->GetPlot(result.x,result.y));
            if(!unit || !target || unit->GetDeclareWarMove(target.get())!=result.rivalTeam)
                throw std::runtime_error("Original SDK did not request move war confirmation for this fixture");
        }
        return result;
    }
    bool DeclareWarFixtureAtWar(const DeclareWarSmokeFixture& fixture){
        Owner();return Query("ZeroSisLiveResult=Teams[Players[Game.GetActivePlayer()]:GetTeam()]:IsAtWar("+
            std::to_string(fixture.rivalTeam)+")");
    }
    // Finite --city-capture smoke only. Capture must still happen through the
    // ordinary selected-unit Move path; this only creates the legal fixture.
    CityCaptureSmokeFixture CreateCityCaptureSmokeFixture(){
        Owner();if(!HumanTurn() || (ui_ && ui_->HasModal()))
            throw std::logic_error("City-capture fixture requires an idle human turn");
        Execute("local id=Game.GetActivePlayer();local p=assert(Players[id]);local team=p:GetTeam();"
            "local defender,capital=nil,nil;local capitalCreated=0;for n=0,63 do local other=assert(Players[n]);"
            "if n~=id and other:IsAlive() and not other:IsHuman() and not other:IsMinorCiv() and not other:IsBarbarian() then "
            "local city=other:GetCapitalCity();local start=other:GetStartingPlot();"
            "if city then defender,capital=other,city;break elseif start and not start:IsWater() and not start:IsMountain() and not start:IsCity() "
            "and other:CanFound(start:GetX(),start:GetY()) then defender=other;break end end end;"
            "assert(defender,'City-capture fixture needs a living AI major with a capital or valid starting plot');"
            "if not capital then local start=assert(defender:GetStartingPlot());"
            "capital=assert(defender:InitCity(start:GetX(),start:GetY()),'Original InitCity rejected the major starting-plot capital');"
            "assert(defender:GetCapitalCity() and defender:GetCapitalCity():GetID()==capital:GetID(),"
            "'Original SDK founding did not establish the starting-plot capital');capitalCreated=1 end;"
            "local defenderTeam=defender:GetTeam();local attackingTeam=assert(Teams[team]);"
            "local metForFixture=0;if not attackingTeam:IsHasMet(defenderTeam) then "
            "attackingTeam:Meet(defenderTeam,true);metForFixture=1 end;"
            "assert(attackingTeam:IsHasMet(defenderTeam),'Original SDK Meet did not establish reciprocal contact');"
            "local wasAtWar=attackingTeam:IsAtWar(defenderTeam);local declaredWar=0;"
            "if not wasAtWar then assert(attackingTeam:CanDeclareWar(defenderTeam),'SDK forbids war declaration against fixture major');"
            "attackingTeam:DeclareWar(defenderTeam);declaredWar=1 end;"
            "assert(attackingTeam:IsAtWar(defenderTeam),'Original SDK DeclareWar did not establish hostility');"
            "local function free(plot) return plot and plot:IsVisible(team,false) and not plot:IsWater() and not plot:IsMountain() "
            "and not plot:IsCity() and plot:GetNumUnits()==0 and plot:GetOwner()==-1 end;"
            "local origin,target=nil,nil;for i=0,Map.GetNumPlots()-1 do local a=Map.GetPlotByIndex(i);if free(a) then "
            "for d=0,5 do local b=Map.PlotDirection(a:GetX(),a:GetY(),d);if free(b) and defender:CanFound(b:GetX(),b:GetY()) then origin,target=a,b;break end end end;"
            "if origin then break end end;assert(origin and target,'No visible adjacent plot where defender CanFound a second city');"
            "assert(capital:GetX()~=target:GetX() or capital:GetY()~=target:GetY(),'Capture target must remain non-capital');"
            "local city=assert(defender:InitCity(target:GetX(),target:GetY()),'Original InitCity rejected legal second-city plot');"
            "assert(city:GetOwner()==defender:GetID() and city:GetX()==target:GetX() and city:GetY()==target:GetY());"
            "assert(defender:GetNumCities()>=2 and defender:GetCapitalCity():GetID()==capital:GetID(),'Fixture must preserve original capital and another city');"
            "local cityName=city:GetName();assert(type(cityName)=='string' and cityName~='',"
            "'Original major city naming did not assign a name');"
            "city:SetDamage(city:GetMaxHitPoints()-1);"
            "assert(city:GetDamage()==city:GetMaxHitPoints()-1,'City fixture did not retain one hit point');"
            "local attacker=assert(p:InitUnit(assert(GameInfo.Units.UNIT_WARRIOR).ID,origin:GetX(),origin:GetY(),-1));"
            "assert(attacker:GetOwner()==id and origin:GetNumUnits()==1 and target:GetNumUnits()==0);"
            "ZeroSisLiveCityCaptureFixture={id,attacker:GetID(),defender:GetID(),city:GetID(),target:GetX(),target:GetY(),capital:GetID(),defender:GetNumCities()-1,declaredWar,capitalCreated,metForFixture}");
        CityCaptureSmokeFixture result{-1,-1,-1,-1,-1,-1,-1,-1,0,0,0};
        int* fields[]={&result.attackerOwner,&result.attacker,&result.defenderOwner,&result.oldCity,&result.x,&result.y,
            &result.capitalCity,&result.defenderCitiesBefore,&result.declaredWar,&result.capitalCreated,&result.metForFixture};
        for(int index=0;index<11;++index)*fields[index]=ReadIntegerQuery(
            "ZeroSisLiveInteger=ZeroSisLiveCityCaptureFixture["+std::to_string(index+1)+"]");
        if(result.attackerOwner!=static_cast<int>(game_->GetActivePlayer()) || result.attacker<0 ||
            result.defenderOwner<0 || result.defenderOwner>=MAX_PLAYERS || result.oldCity<0 || !InMap(result.x,result.y) ||
            !IsAttackLegal(result.attacker,result.x,result.y,false))
            throw std::runtime_error("Original SDK rejected the city-capture smoke fixture");
        std::unique_ptr<ICvPlayer1> defender(game_->GetPlayer(static_cast<PlayerTypes>(result.defenderOwner)));
        std::unique_ptr<ICvCity1> city(defender?defender->GetCity(result.oldCity):nullptr);
        std::unique_ptr<ICvCity1> capital(defender?defender->GetCity(result.capitalCity):nullptr);
        std::unique_ptr<ICvPlot1> target(map_->GetPlot(result.x,result.y));
        std::unique_ptr<ICvCity1> plotCity(target?target->GetPlotCity():nullptr);
        if(!defender || defender->IsBarbarian() || defender->IsMinorCiv() || defender->IsHuman() ||
            defender->GetNumCities()<2 || !capital || capital->GetID()!=result.capitalCity ||
            !city || city->GetID()!=result.oldCity ||
            city->GetOwner()!=result.defenderOwner || !plotCity || plotCity->GetID()!=result.oldCity || plotCity->GetOwner()!=result.defenderOwner)
            throw std::runtime_error("City-capture fixture does not resolve to a non-final second city of a living major");
        return result;
    }
    CapturedCityObservation ObserveCapturedCityAtPlot(int x,int y){
        Owner();if(!InMap(x,y))throw std::invalid_argument("Captured-city observation plot is outside the map");
        Execute("local plot=assert(Map.GetPlot("+std::to_string(x)+","+std::to_string(y)+"));"
            "local city=plot:GetPlotCity();if city then ZeroSisLiveCapturedCityObservation={city:GetID(),city:GetOwner(),"
            "city:IsPuppet() and 1 or 0,city:IsRazing() and 1 or 0,city:GetOriginalOwner()} "
            "else ZeroSisLiveCapturedCityObservation={-1,-1,0,0,-1} end");
        CapturedCityObservation result{-1,-1,0,0,-1};
        if(!host_.scripts->CallCFunction(vm_,&ReadCapturedCityObservation,&result))
            throw std::runtime_error(host_.scripts->LastError());
        return result;
    }
    // Read-only smoke evidence supplements the unchanged save/snapshot format.
    // Keep these private SDK observations out of the visible world DTO.
    void TraceCityGovernance(const char* phase){
        Owner();if(!phase || (std::strcmp(phase,"initial") && std::strcmp(phase,"final")))
            throw std::invalid_argument("Unknown city-governance observation phase");
        Execute("local count=0;for id=0,"+std::to_string(MAX_PLAYERS-1)+" do local p=assert(Players[id]);"
            "local capital=p:GetCapitalCity();for city in p:Cities() do count=count+1;"
            "print('INTERACTIVE_CITY_GOVERNANCE="+std::string(phase)+"|'..id..'|'..city:GetID()..'|'..city:GetOwner()..'|'..city:GetX()..'|'..city:GetY()..'|'.."
            "(city:IsPuppet() and 1 or 0)..'|'..(city:IsRazing() and 1 or 0)..'|'..city:GetOriginalOwner()..'|'.."
            "(capital and capital:GetID() or -1)..'|'..p:GetNumCities()..'|'..(p:IsAlive() and 1 or 0)) end end;"
            "print('INTERACTIVE_CITY_GOVERNANCE_COUNT="+std::string(phase)+"|'..count);"
            "for id=0,"+std::to_string(MAX_PLAYERS-1)+" do for city in Players[id]:Cities() do "
            "print('INTERACTIVE_CITY_CITIZENS_STATE="+std::string(phase)+"|'..id..'|'..city:GetID()..'|'..city:GetFocusType()..'|'.."
            "(city:IsForcedAvoidGrowth() and 1 or 0)) end end");
    }
    bool CombatSmokeUnitAlive(int owner,int id){
        Owner();if(owner<0 || owner>=MAX_PLAYERS || id<0)throw std::invalid_argument("Combat observation identity is invalid");
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(owner)));
        std::unique_ptr<ICvUnit1> unit(player?player->GetUnit(id):nullptr);
        return unit && unit->GetOwner()==owner && unit->GetID()==id && !unit->IsDelayedDeathExported();
    }
    BuildObservation ObserveBuild(ICvGameContext3& context,int unitID,int buildID){
        Owner();const auto unit=Unit(unitID);
        if(!unit || buildID<0 || buildID>=context.GetNumBuildInfos())throw std::invalid_argument("Build observation target is invalid");
        std::unique_ptr<ICvBuildInfo1> info(context.GetBuildInfo(static_cast<BuildTypes>(buildID)));
        std::unique_ptr<ICvPlot1> plot(map_->GetPlot(unit->GetX(),unit->GetY()));
        std::unique_ptr<ICvMissionData1> mission(unit->GetHeadMissionData());
        if(!info || !plot || !info->GetType() || context.GetInfoTypeForString(info->GetType(),true)!=buildID)
            throw std::runtime_error("Build observation does not resolve to the original SDK catalog and plot");
        return {unitID,plot->GetPlotIndex(),buildID,plot->GetBuildProgress(static_cast<BuildTypes>(buildID)),
            plot->GetBuildTime(static_cast<BuildTypes>(buildID),game_->GetActivePlayer()),
            static_cast<int>(plot->GetImprovementType()),info->GetImprovement(),
            mission?static_cast<int>(mission->GetMissionType()):-1,mission?mission->GetData1():-1,unit->MovesLeft()};
    }
    bool EndTurn(){
        Owner();if(!HumanTurn())return Reject(L"\uc774\ubbf8 \ub2e4\uc74c \ud134\uc744 \ucc98\ub9ac \uc911\uc785\ub2c8\ub2e4.");
        if(ui_ && ui_->HasModal())return Reject(L"\uba3c\uc800 \uc5f4\ub9b0 \uc120\ud0dd \ucc3d\uc744 \ucc98\ub9ac\ud558\uc2ed\uc2dc\uc624.");
        game_->UpdateTestEndTurn();
        if(!Query("ZeroSisLiveResult=Game.CanDoControl(ControlTypes.CONTROL_ENDTURN)"))
            return Reject(L"\uba3c\uc800 \ub0a8\uc740 \uc720\ub2db \ud589\ub3d9\uacfc \ud544\uc218 \uc120\ud0dd\uc744 \ucc98\ub9ac\ud558\uc2ed\uc2dc\uc624.");
        const char command[]="Game.DoControl(ControlTypes.CONTROL_ENDTURN)";
        Execute(command);turns_->CommitCompletion();
        turnBefore_=game_->GetGameTurn();if(turnBefore_==INT_MAX)throw std::overflow_error("Interactive turn counter exhausted");
        advancing_=true;updates_=0;status_=L"\ub2e4\uc74c \ud134\uc744 \ucc98\ub9ac \uc911\uc785\ub2c8\ub2e4.";
        std::printf("INTERACTIVE_END_TURN_ACCEPTED=%d\n",turnBefore_);return true;
    }
    bool Tick(){
        Owner();if(!advancing_)return false;
        game_->Update();Check();++updates_;
        const int turn=game_->GetGameTurn();
        if(turn<turnBefore_ || turn>turnBefore_+1 || game_->GetElapsedGameTurns()!=turn)
            throw std::runtime_error("Interactive SDK update escaped its requested turn boundary");
        if(turn==turnBefore_+1 && HumanTurnRaw()){
            advancing_=false;status_=L"\ub2e4\uc74c \ud134\uc785\ub2c8\ub2e4. \uc720\ub2db\uc744 \uc120\ud0dd\ud558\uc2ed\uc2dc\uc624.";
            std::printf("INTERACTIVE_NEXT_HUMAN_TURN=%d|%u\n",turn,updates_);return true;
        }
        if(updates_>=512)throw std::runtime_error("Interactive SDK did not return to a human turn within 512 updates");
        return false;
    }
    std::wstring Save(){
        Owner();if(advancing_ || !host_.localCommands.IsQuiescent() || host_.autoSaveRunning ||
            (ui_ && ui_->HasModal()) || HasMandatoryUiDecision())
            throw std::logic_error("Interactive save requires a settled command and turn boundary");
        saveCatalog_->PrepareForMutation();
        const auto archive=saves_->Capture(false,false);
        const auto path=directory_+L"\\play-save-"+std::to_wstring(++saveCount_)+L"-turn-"+std::to_wstring(archive.turn)+L".zssave";
        NativeSaveArchive::WriteAtomic(path,archive.Encode());
        saveCatalog_->ObserveWrittenSave(path,CaptureSaveMenuHeader());
        status_=L"\ud604\uc7ac \uac8c\uc784\uc744 \uc800\uc7a5\ud588\uc2b5\ub2c8\ub2e4.";
        std::printf("INTERACTIVE_NATIVE_SAVE=%d|%s\n",archive.turn,Utf8(path).c_str());return path;
    }
    std::shared_ptr<const UiSaveMenuCatalog> CaptureSaveMenuCatalog(){
        Owner();
        if(!saveCatalog_ || !ui_ || ui_->ActiveKind()!=UiPopupKind::GameMenu || !ui_->HasModal() ||
           !HumanTurn() || host_.autoSaveRunning || !host_.localCommands.IsQuiescent() ||
           !host_.scripts || !host_.scripts->IsQuiescent() || HasMandatoryUiDecision())
            throw std::logic_error("SaveMenu catalog requires its settled retained GameMenu owner");
        auto snapshot=std::make_shared<UiSaveMenuCatalog>();
        snapshot->current=CaptureSaveMenuHeader();snapshot->files=saveCatalog_->List();
        // This callback is deliberately filesystem-only when invoked by the UI
        // VM. A shared owner makes the immutable snapshot safe to retain.
        const auto catalog=saveCatalog_;
        snapshot->nameAvailable=[catalog](const std::string& name){return catalog->NameAvailable(name);};
        ReadFileHandle identity(bundle_+L"\\bundle.manifest");std::array<unsigned char,16385> bytes{};
        const DWORD size=identity.Read(bytes.data(),static_cast<DWORD>(bytes.size()));
        if(!size || size==bytes.size())throw std::runtime_error("SaveMenu deletion bundle identity is invalid");
        const std::vector<unsigned char> manifest(bytes.begin(),bytes.begin()+size);
        snapshot->deleteFile=[catalog,manifest](const UiSaveMenuFile& listed){catalog->DeleteListed(listed,manifest);};
        // Retain the authoritative observation independently of the child VM.
        // The writer is called only after the original child and parent exit.
        snapshot->overwriteSupported=true;
        saveMenuBundleManifest_=manifest;saveMenuCatalog_=snapshot;
        return snapshot;
    }
    std::shared_ptr<const UiLoadMenuCatalog> CaptureLoadMenuCatalog(){
        Owner();
        if(!saveCatalog_ || !ui_ || ui_->ActiveKind()!=UiPopupKind::GameMenu || !ui_->HasModal() ||
           !HumanTurn() || host_.autoSaveRunning || !host_.localCommands.IsQuiescent() ||
           !host_.scripts || !host_.scripts->IsQuiescent() || HasMandatoryUiDecision() || pendingLoad_.archive ||
           !host_.activeMods || host_.activeMods->Size()!=0)
            throw std::logic_error("LoadMenu catalog requires its settled current owner and explicit empty active-mod profile");
        ReadFileHandle identity(bundle_+L"\\bundle.manifest");std::array<unsigned char,16385> bytes{};
        const DWORD size=identity.Read(bytes.data(),static_cast<DWORD>(bytes.size()));
        if(!size || size==bytes.size())throw std::runtime_error("LoadMenu bundle identity is invalid");
        std::vector<unsigned char> manifest(bytes.begin(),bytes.begin()+size);
        auto snapshot=std::make_shared<UiLoadMenuCatalog>();snapshot->files=saveCatalog_->List();
        // Only observed previews may be selected. Validate their exact archive
        // and bundle before exposing the no-additional-content profile.
        for(const auto& listed:snapshot->files)if(listed.header)
            saveCatalog_->ReadLoadArchive(listed.fileName,listed,manifest);
        const auto catalog=saveCatalog_;
        snapshot->canLoad=[catalog,listed=snapshot->files,manifest](const std::string& path){
            try{
                const auto entry=std::find_if(listed.begin(),listed.end(),[&path](const UiSaveMenuFile& file){return file.fileName==path;});
                return entry!=listed.end() && entry->header && !!catalog->ReadLoadArchive(path,*entry,manifest);
            }catch(...){return false;}
        };
        snapshot->deleteFile=[catalog,manifest](const UiSaveMenuFile& listed){catalog->DeleteListed(listed,manifest);};
        snapshot->profile=UiLoadMenuCatalog::Profile::OwnedCurrentExactBundleNoAdditionalContent;
        loadMenuBundleManifest_=std::move(manifest);
        return snapshot;
    }
    bool HasPendingExit(){Owner();return pendingExit_;}
    bool HasPendingLoad(){Owner();return !!pendingLoad_.archive;}
    bool HasPendingLifecycle(){Owner();return pendingLifecycle_.HasTransition();}
    LoadHandoff TakePendingLifecycle(){
        Owner();if(!pendingLifecycle_.HasTransition())return {};
        if(pendingExit_ || pendingLoad_.archive || !host_.scripts || !host_.scripts->IsQuiescent() ||
           !host_.localCommands.IsQuiescent() || host_.autoSaveRunning || host_.popupVisible || (ui_ && ui_->HasModal()))
            throw std::logic_error("Lifecycle handoff requires a callback-free completed menu exit");
        LoadHandoff out=std::move(pendingLifecycle_);pendingLifecycle_=LoadHandoff{};return out;
    }
    LoadHandoff TakePendingLoad(){
        Owner();if(!pendingLoad_.archive)return {};
        if(!host_.scripts || !host_.scripts->IsQuiescent() || !host_.localCommands.IsQuiescent() ||
           !HumanTurn() || host_.autoSaveRunning || host_.popupVisible || (ui_ && ui_->HasModal()) || HasMandatoryUiDecision())
            throw std::logic_error("Load handoff requires its settled, callback-free original UI exit");
        LoadHandoff result=std::move(pendingLoad_);pendingLoad_=LoadHandoff{};return result;
    }
    std::wstring SaveNamed(const std::string& name){
        Owner();
        if(!saveCatalog_ || !saves_ || !HumanTurn() || !host_.localCommands.IsQuiescent() || host_.autoSaveRunning ||
           !host_.scripts || !host_.scripts->IsQuiescent() || host_.popupVisible ||
           (ui_ && ui_->HasModal()) || HasMandatoryUiDecision())
            throw std::logic_error("Named save requires the completed child and parent return boundary");
        saveCatalog_->PrepareForMutation();
        if(!saveCatalog_->NameAvailable(name)){
            Reject(L"\uc774 \uc774\ub984\uc73c\ub85c\ub294 \ud604\uc7ac \uc138\uc158\uc5d0 \uc800\uc7a5\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");return L"";
        }
        const auto archive=saves_->Capture(false,false);
        const auto header=CaptureSaveMenuHeader();
        const auto path=saveCatalog_->WriteNew(name,archive,header);
        status_=L"\ud604\uc7ac \uac8c\uc784\uc744 \uc800\uc7a5\ud588\uc2b5\ub2c8\ub2e4.";
        std::printf("INTERACTIVE_NATIVE_SAVE=%d|%s\nINTERACTIVE_SAVE_MENU_NAMED_SAVE=%d|%d|%s\n",
            archive.turn,Utf8(path).c_str(),archive.activePlayer,archive.turn,Utf8(path).c_str());return path;
    }
    NativeSaveCatalog::ReplacementResult SaveNamedOverwrite(const SaveMenuRequest& request){
        Owner();
        if(!saveCatalog_ || !saves_ || !HumanTurn() || !host_.localCommands.IsQuiescent() || host_.autoSaveRunning ||
           !host_.scripts || !host_.scripts->IsQuiescent() || host_.popupVisible ||
           (ui_ && ui_->HasModal()) || HasMandatoryUiDecision())
            throw std::logic_error("Save overwrite requires the completed child and parent return boundary");
        if(request.kind!=SaveMenuRequest::Kind::Overwrite || !request.expected || !request.expected->header ||
           request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn() || request.name.empty() ||
           !saveMenuCatalog_ || !saveMenuCatalog_->overwriteSupported || saveMenuBundleManifest_.empty())
            throw std::logic_error("Save overwrite lost its confirmed owner, turn or retained catalog");
        const UiSaveMenuFile* listed=nullptr;
        for(const auto& file:saveMenuCatalog_->files)if(file.fileName==request.expected->fileName){
            if(listed)throw std::logic_error("Save overwrite retained catalog contains ambiguous targets");
            listed=&file;
        }
        if(!listed || !listed->header || !SameUiSaveMenuObservation(*listed,*request.expected))
            throw std::logic_error("Save overwrite target differs from its retained immutable observation");
        saveCatalog_->PrepareForMutation();
        // Prepare presentation strings before any irreversible storage step.
        std::wstring saved=L"\ud604\uc7ac \uac8c\uc784\uc744 \uc800\uc7a5\ud588\uc2b5\ub2c8\ub2e4.";
        std::wstring savedPending=L"\uac8c\uc784\uc740 \uc800\uc7a5\ub418\uc5c8\uc73c\ub098 \uc774\uc804 \uc800\uc7a5 \ubcf5\uad6c \uc790\ub8cc\uc758 \ud6c4\uc18d \uc815\ub9ac\uac00 \ud544\uc694\ud569\ub2c8\ub2e4.";
        std::wstring notCommitted=L"\uae30\uc874 \uc800\uc7a5\uc744 \ubc14\uafb8\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4.";
        std::wstring recoveryRequired=L"\uc800\uc7a5 \uad50\uccb4\ub97c \uc911\ub2e8\ud588\uc2b5\ub2c8\ub2e4. \ubcf4\uc874\ub41c \uae30\uc874 \uc800\uc7a5\uc758 \ubcf5\uad6c\uac00 \ud544\uc694\ud569\ub2c8\ub2e4.";
        const auto archive=saves_->Capture(false,false);
        const auto header=CaptureSaveMenuHeader();
        auto result=saveCatalog_->WriteListedReplacement(*request.expected,archive,header,saveMenuBundleManifest_);
        if(result.committed){
            // No diagnostic allocation failure may turn a committed save into
            // an ordinary failure that invites another destructive attempt.
            status_.swap(result.recoveryRequired?savedPending:saved);
            std::printf("INTERACTIVE_SAVE_MENU_OVERWRITE_COMMITTED=%d|%d|%u\n",
                archive.activePlayer,archive.turn,result.recoveryRequired?1u:0u);
            if(result.recoveryRequired)std::fprintf(stderr,"INTERACTIVE_SAVE_MENU_OVERWRITE_COMMITTED_RECOVERY_PENDING=1\n");
        }else{
            status_.swap(result.recoveryRequired?recoveryRequired:notCommitted);
            std::fprintf(stderr,"INTERACTIVE_SAVE_MENU_OVERWRITE_NOT_COMMITTED=%u\n",result.recoveryRequired?1u:0u);
            if(result.recoveryRequired)std::fprintf(stderr,"INTERACTIVE_SAVE_MENU_OVERWRITE_RECOVERY_REQUIRED=1\n");
        }
        std::fprintf(stderr,"INTERACTIVE_SAVE_MENU_OVERWRITE_DIAGNOSTIC=%s\n",result.diagnostic?result.diagnostic:"none");
        try{
            if(result.committed)std::printf("INTERACTIVE_NATIVE_SAVE=%d|%s\n",archive.turn,Utf8(result.path).c_str());
            if(result.recoveryRequired && !result.recoveryPath.empty())std::fprintf(stderr,"INTERACTIVE_SAVE_MENU_OVERWRITE_RECOVERY_PATH=%s\n",Utf8(result.recoveryPath).c_str());
        }catch(...){std::fprintf(stderr,"INTERACTIVE_SAVE_MENU_OVERWRITE_PATH_DIAGNOSTIC_UNAVAILABLE=1\n");}
        if(!result.committed && result.recoveryRequired)
            throw std::runtime_error("Owned save replacement did not commit; RECOVERY_REQUIRED; preserved recovery path is in the diagnostic log");
        return result;
    }
    std::vector<int> ReadyUnits(){
        Owner();std::vector<int> result;if(!HumanTurn())return result;
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(game_->GetActivePlayer()));
        int iterator=0;std::unique_ptr<ICvUnit1> unit(player->FirstUnit(&iterator));
        while(unit){if(unit->ReadyToSelect() && !unit->IsBusy() && !unit->IsDelayedDeathExported())result.push_back(unit->GetID());unit.reset(player->NextUnit(&iterator));}
        return result;
    }
    bool IsAdjacentMoveLegal(int id,int x,int y){
        Owner();if(!HumanTurn() || x<0 || x>=map_->GetGridWidth() || y<0 || y>=map_->GetGridHeight())return false;
        auto unit=Unit(id);if(!unit || unit->MovesLeft()<=0)return false;
        std::unique_ptr<ICvPlot1> from(unit->GetPlot()),to(map_->GetPlot(x,y));
        return from && to && from->IsAdjacent(to.get()) && unit->CanMoveInto(to.get(),0) && CanStartMission(id,moveMission_,x,y);
    }
    // Read-only guards for the first naturally produced civilian's stacked city.
    // Original SDK movement remains the only operation that resolves the stack.
    bool IsProductionCivilianStack(ICvGameContext3& context,int id,int produced,int city){
        Owner();if(!HumanTurn() || (ui_ && ui_->HasModal()) || id<0 || produced<0 || id==produced || !OwnsCity(city))return false;
        return Query("local p=assert(Players[Game.GetActivePlayer()]);local u=p:GetUnitByID("+std::to_string(id)+
            ");local v=p:GetUnitByID("+std::to_string(produced)+");local c=p:GetCityByID("+std::to_string(city)+
            ");local plot=u and u:GetPlot();ZeroSisLiveResult=u~=nil and v~=nil and c~=nil and plot~=nil and "
            "u:GetOwner()==Game.GetActivePlayer() and v:GetOwner()==Game.GetActivePlayer() and "
            "u:GetUnitType()==v:GetUnitType() and u:GetDomainType()==v:GetDomainType() and "
            "not u:IsCombatUnit() and not v:IsCombatUnit() and not u:IsCargo() and not v:IsCargo() and "
            "u:GetX()==c:GetX() and u:GetY()==c:GetY() and v:GetX()==c:GetX() and v:GetY()==c:GetY() and "
            "GameDefines.PLOT_UNIT_LIMIT==1 and plot:GetNumFriendlyUnitsOfType(u,false)==2 and "
            "not u:CanHold(plot) and not u:CanStartMission("+std::to_string(static_cast<int>(Mission(context,"MISSION_SKIP")))+
            ",-1,-1,plot,0) or false");
    }
    bool IsVacantAdjacentMoveLegal(int id,int x,int y){
        Owner();if(!IsAdjacentMoveLegal(id,x,y))return false;
        std::unique_ptr<ICvPlot1> plot(map_->GetPlot(x,y));return plot && plot->GetNumUnits()==0;
    }
    bool IsFortifyLegal(ICvGameContext3& context,int id){
        Owner();if(!HumanTurn() || (ui_ && ui_->HasModal()))return false;
        const auto unit=Unit(id);
        return unit && unit->MovesLeft()>0 && !unit->IsBusy() && !unit->IsDelayedDeathExported() &&
            CanStartMission(id,Mission(context,"MISSION_FORTIFY"),-1,-1);
    }
    bool IsAdvancing() const noexcept{return advancing_;}
    const std::wstring& Status() const noexcept{return status_;}
    bool OpenResearch(){
        Owner();if(!HumanTurn() || ui_->HasModal())return false;
        ui_->Queue(CvPopupInfo(BUTTONPOPUP_CHOOSETECH,static_cast<int>(game_->GetActivePlayer()),-1,-1,0,false,false));
        return true;
    }
    bool OwnsCity(int id){
        Owner();if(id<0)return false;
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(game_->GetActivePlayer()));
        std::unique_ptr<ICvCity1> city(player?player->GetCity(id):nullptr);
        return city && city->GetID()==id && city->GetOwner()==game_->GetActivePlayer();
    }
    bool CanChooseProduction(int id){
        Owner();if(!OwnsCity(id))return false;
        // Original ProductionPopup.OnPopup rejects puppet cities in
        // production mode. Venice's exception applies only to purchase.
        return Query("ZeroSisLiveResult=not assert(Players[Game.GetActivePlayer()]:GetCityByID("+
            std::to_string(id)+")):IsPuppet()");
    }
    bool OpenProduction(int id){
        Owner();if(!HumanTurn() || ui_->HasModal() || !OwnsCity(id))return false;
        if(!CanChooseProduction(id)){
            status_=L"\uad34\ub8b0\ub3c4\uc2dc\ub294 \uc0dd\uc0b0\uc744 \uc9c1\uc811 \uc120\ud0dd\ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.";
            std::printf("INTERACTIVE_PRODUCTION_REJECTED=%d|PUPPET_CITY\n",id);return false;
        }
        ui_->Queue(CvPopupInfo(BUTTONPOPUP_CHOOSEPRODUCTION,id,-1,-1,0,false,false));return true;
    }
    bool OpenCity(int id){
        Owner();if(!HumanTurn() || !ui_ || ui_->HasModal() || !OwnsCity(id))return false;
        ui_->OpenCity(id);return true;
    }
    bool OpenGameMenu(){
        Owner();if(!HumanTurn() || !ui_ || ui_->HasModal() || host_.autoSaveRunning ||
            !host_.localCommands.IsQuiescent() || !host_.scripts || !host_.scripts->IsQuiescent())return false;
        ui_->OpenGameMenu();Check();return true;
    }
    bool HasCityView(){Owner();return ui_ && ui_->HasCityView();}
    bool UpdateUi(){Owner();return ui_ && ui_->Update();}
    bool HasUi(){Owner();return ui_ && ui_->IsActive();}
    bool DispatchUi(const ZeroSisPresentation::BitmapInputEvent& input){
        Owner();if(!ui_ || !ui_->IsActive())return false;
        const bool gameMenu=ui_->ActiveKind()==UiPopupKind::GameMenu;
        const bool exitConfirm=ui_->ActiveKind()==UiPopupKind::ExitConfirm;
        const bool saveMenu=ui_->ActiveKind()==UiPopupKind::SaveMenu;
        const bool loadMenu=ui_->ActiveKind()==UiPopupKind::LoadMenu;
        const bool mapMenu=ui_->ActiveKind()==UiPopupKind::MapMenu;
        const bool presentationMenu=ui_->ActiveKind()==UiPopupKind::MenuOptions || ui_->ActiveKind()==UiPopupKind::TouchHelp;
        const bool consumed=ui_->Dispatch(input);
        if(saveMenu){
            // Stock OnSave/OnYes publishes [Save or Overwrite,Close], then OnBack hides the child.
            // Keep its requests before Update returns to the retained parent.
            // Text edits, selection and Back must not advance the SDK game.
            auto requests=ui_->TakeSaveMenuRequests();
            auto children=ui_->TakeGameMenuRequests();
            if(!children.empty()){
                if(!requests.empty())throw std::logic_error("SaveMenu child opening conflicts with a save or close command");
                ui_->Update();ApplyGameMenuRequests(children);
            }else ApplySaveMenuRequests(requests);
            Check();
        }else if(loadMenu){
            auto requests=ui_->TakeLoadMenuRequests();
            ApplyLoadMenuRequests(requests);Check();
        }else if(mapMenu){
            auto requests=ui_->TakeMapMenuRequests();
            ApplyMapMenuRequests(requests);Check();
        }else if(presentationMenu){
            ui_->Update();Check();
        }else if(gameMenu || exitConfirm){
            // OnQuickSave calls the original OnReturn before UI.QuickSave.
            // Collect its request before Update releases the closed Lua VM,
            // then save only at the existing nonmodal owner boundary.
            auto requests=ui_->TakeGameMenuRequests();
            ui_->Update();ApplyGameMenuRequests(requests);Check();
        }else if(consumed && (input.kind==ZeroSisPresentation::BitmapInputKind::ControlClick ||
            input.kind==ZeroSisPresentation::BitmapInputKind::KeyDown)){game_->Update();Check();}
        return consumed;
    }
    InteractiveUiSession::Frame CaptureUi(){Owner();return ui_->Capture();}
    std::uint64_t UiTextInputOwner(){Owner();return ui_?ui_->TextInputOwner():0;}
    InteractiveUiSession::Frame CaptureUnitPanel(){Owner();return ui_->CaptureUnitPanel();}
    InteractiveUiSession::Frame CaptureTopPanel(){Owner();return ui_->CaptureTopPanel();}
    bool DispatchTopPanel(const ZeroSisPresentation::BitmapInputEvent& input,bool* frameChanged=nullptr){
        if(frameChanged)*frameChanged=false;
        Owner();if(!ui_)return false;
        bool changed=false;
        const bool consumed=ui_->DispatchTopPanel(input,frameChanged?&changed:nullptr);
        ApplyGameMenuRequests(ui_->TakeGameMenuRequests());
        if(frameChanged)*frameChanged=changed;
        return consumed;
    }
    void VerifyTopPanelSnapshot(const std::string& snapshot){Owner();ui_->VerifyTopPanelSnapshot(snapshot);}
    InteractiveUiSession::Frame CaptureActionInfoPanel(){
        Owner();if(!ui_)return {};
        // The original HUD remains on screen while the AI advances. Refresh
        // its SDK end-turn blocker only on the live human boundary; during an
        // AI turn the stock Lua context renders its own waiting state.
        if(HumanTurn())game_->UpdateTestEndTurn();
        return ui_->CaptureActionInfoPanel();
    }
    InteractiveUiSession::ActionInfoObservation ObserveActionInfoPanel(){
        Owner();if(!HumanTurn() || !ui_)throw std::logic_error("ActionInfo observation requires the live human turn");
        game_->UpdateTestEndTurn();auto result=ui_->ObserveActionInfoPanel();
        result.blockingType=ReadIntegerQuery("ZeroSisLiveInteger=assert(Players[Game.GetActivePlayer()]):GetEndTurnBlockingType()");
        result.notificationIndex=ReadIntegerQuery("ZeroSisLiveInteger=assert(Players[Game.GetActivePlayer()]):GetEndTurnBlockingNotificationIndex()");
        return result;
    }
    void VerifyActionInfoPanelSnapshot(const std::string& snapshot){Owner();if(ui_)ui_->VerifyActionInfoPanelSnapshot(snapshot);}
    InteractiveUiSession::Frame CaptureNotificationPanel(){Owner();return ui_?ui_->CaptureNotificationPanel():InteractiveUiSession::Frame{};}
    void VerifyNotificationPanelSnapshot(const std::string& snapshot){Owner();if(ui_)ui_->VerifyNotificationPanelSnapshot(snapshot);}
    bool DispatchNotificationPanel(const ZeroSisPresentation::BitmapInputEvent& input,bool* frameChanged=nullptr){
        if(frameChanged)*frameChanged=false;
        Owner();if(!HumanTurn() || !ui_ || ui_->HasModal())return false;
        bool changed=false;
        const bool consumed=ui_->DispatchNotificationPanel(input,frameChanged?&changed:nullptr);if(!consumed)return false;
        const bool applied=ApplyOriginalNotificationRequests(ui_->TakeNotificationRequests());
        if(frameChanged)*frameChanged=applied && changed;
        return applied;
    }
    bool DispatchActionInfoPanel(const ZeroSisPresentation::BitmapInputEvent& input,bool* frameChanged=nullptr){
        if(frameChanged)*frameChanged=false;
        Owner();if(!HumanTurn() || !ui_ || ui_->HasModal())return false;
        bool changed=false;
        const bool consumed=ui_->DispatchActionInfoPanel(input,frameChanged?&changed:nullptr);if(!consumed)return false;
        const bool applied=ApplyOriginalNotificationRequests(ui_->TakeActionInfoRequests());
        if(frameChanged)*frameChanged=applied && changed;
        return applied;
    }
    bool ApplyOriginalNotificationRequests(const std::vector<ActionInfoRequest>& requests){
        Owner();if(!HumanTurn() || !ui_ || !host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("Original HUD commands require the live human boundary after their Lua callback");
        for(std::size_t index=0;index<requests.size();++index){
            const auto& request=requests[index];
            if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn())
                throw std::logic_error("ActionInfo callback request escaped its live owner/turn");
            switch(request.kind){
            case ActionInfoRequest::Kind::LookAt:{
                if(request.id<CAMERALOOKAT_NORMAL || request.id>CAMERALOOKAT_HOTSEAT || !InMap(request.x,request.y))
                    throw std::invalid_argument("ActionInfo requested an invalid original camera target");
                std::unique_ptr<ICvPlot1> plot(map_->GetPlot(request.x,request.y));
                if(!plot)throw std::invalid_argument("ActionInfo camera target disappeared from the SDK map");
                UserInterface frontend(owner_);frontend.lookAt(plot.get(),static_cast<CameraLookAtTypes>(request.id));
                break;
            }
            case ActionInfoRequest::Kind::SelectUnit:
                if(!Select(request.id))return false;
                break;
            case ActionInfoRequest::Kind::ActivateNotification:{
                NotificationPresentation notification;
                {
                    std::lock_guard<std::mutex> guard(host_.dataMutex);
                    const auto found=host_.notifications.find({static_cast<int>(request.owner),request.id});
                    if(found==host_.notifications.end() || found->second.player!=request.owner)return false;
                    if(!IsSupportedActionInfoNotification(found->second.type))
                        return Reject(L"\uc774 \uc54c\ub9bc \uc720\ud615\uc740 \uc544\uc9c1 \uc6d0\ubcf8 \ud654\uba74\uc5d0 \uc5f0\uacb0\ub418\uc9c0 \uc54a\uc558\uc2b5\ub2c8\ub2e4.");
                    notification=found->second;
                }
                if(notification.type==NOTIFICATION_TECH_AWARD && notification.extraGameData==-1)
                    return Reject(L"\ud544\uc218 \uc6d0\ubcf8 \uae30\uc220 \ubcf4\uc0c1 \ub370\uc774\ud130\uac00 \uc5c6\ub294 \uc54c\ub9bc\uc740 \uc5f4 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");
                if(notification.type==NOTIFICATION_PRODUCTION){
                    if(!InMap(notification.x,notification.y))return Reject(L"\uc0dd\uc0b0 \uc54c\ub9bc\uc758 \uc6d0\ubcf8 \uc88c\ud45c\uac00 \ud604\uc7ac \uc9c0\ub3c4\uc640 \uc77c\uce58\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.");
                    std::unique_ptr<ICvPlot1> plot(map_->GetPlot(notification.x,notification.y));
                    std::unique_ptr<ICvCity1> city(plot?plot->GetPlotCity():nullptr);
                    if(!city || city->GetOwner()!=request.owner || city->IsPuppet())
                        return Reject(L"\uc774 \uc0dd\uc0b0 \uc54c\ub9bc\uc740 \ud604\uc7ac \uc5f0\uacb0\ub41c \uc18c\uc720 \ub3c4\uc2dc \uc120\ud0dd\ucc3d\uc744 \uc5f4 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");
                }
                std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(request.owner)));
                if(!player || !player->IsAlive() || player->GetID()!=request.owner)return false;
                host_.actionInfoAdapterRequests.clear();host_.actionInfoOwner=static_cast<PlayerTypes>(request.owner);host_.actionInfoTurn=request.turn;
                host_.actionInfoActivationInProgress=true;
                try{player->ActivateNotification(request.id);}
                catch(...){host_.actionInfoActivationInProgress=false;host_.actionInfoOwner=NO_PLAYER;host_.actionInfoTurn=-1;
                    host_.actionInfoAdapterRequests.clear();throw;}
                host_.actionInfoActivationInProgress=false;host_.actionInfoOwner=NO_PLAYER;host_.actionInfoTurn=-1;
                std::vector<ActionInfoRequest> adapterRequests;adapterRequests.swap(host_.actionInfoAdapterRequests);
                for(const auto& adapted:adapterRequests){
                    if(adapted.owner!=request.owner || adapted.turn!=request.turn)
                        throw std::logic_error("SDK notification adapter request lost its owner/turn identity");
                    if(adapted.kind==ActionInfoRequest::Kind::LookAt){
                        if(!InMap(adapted.x,adapted.y) || adapted.id<CAMERALOOKAT_NORMAL || adapted.id>CAMERALOOKAT_HOTSEAT)
                            throw std::invalid_argument("SDK notification requested an invalid camera target");
                        std::unique_ptr<ICvPlot1> plot(map_->GetPlot(adapted.x,adapted.y));
                        if(!plot)throw std::invalid_argument("SDK notification camera plot disappeared");
                        UserInterface frontend(owner_);frontend.lookAt(plot.get(),static_cast<CameraLookAtTypes>(adapted.id));
                    }else if(adapted.kind==ActionInfoRequest::Kind::SelectUnit){
                        if(!Select(adapted.id))return false;
                    }else throw std::logic_error("SDK notification emitted an unexpected deferred adapter request");
                }
                ui_->Update();
                break;
            }
            case ActionInfoRequest::Kind::RemoveNotification:{
                {std::lock_guard<std::mutex> guard(host_.dataMutex);
                    if(host_.notifications.find({static_cast<int>(request.owner),request.id})==host_.notifications.end())return false;}
                std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(static_cast<PlayerTypes>(request.owner)));
                if(!player || !player->IsAlive() || !player->MayUserDismissNotification(request.id))
                    return Reject(L"\uc774 \uc6d0\ubcf8 \uc54c\ub9bc\uc740 \uc0ac\uc6a9\uc790\uac00 \ub2eb\uc744 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");
                player->DismissNotification(request.id,true);break;
            }
            case ActionInfoRequest::Kind::EndTurn:
                if(request.id!=CONTROL_ENDTURN || index+1!=requests.size())
                    throw std::logic_error("ActionInfo end-turn request is malformed or not last in its callback batch");
                if(!EndTurn())return false;
                break;
            }
        }
        if(host_.scripts && !host_.scripts->IsQuiescent())throw std::logic_error("ActionInfo dispatch left a Lua callback active");
        return true;
    }
    // The finite --trade-route test calls this once. Manual sessions never
    // create fixture cities, technologies or units. AI missions execute during
    // the ordinary following turn, before the overview round-trip assertion.
    void PrepareTradeRoutesSmoke(bool fresh){
        Owner();if(!HumanTurn() || HasUi())throw std::logic_error("TradeRoute fixture requires the idle active human turn");
        const auto plan=TradeRouteSmokeFixture::Prepare(host_,*host_.scripts,vm_,!fresh);
        if(fresh){
            std::puts("INTERACTIVE_TRADE_ROUTE_FIXTURE_AI_ROLE=PLAYER_1_CREATED_CARAVANS_ONLY|UNITAI_UNKNOWN");
            const int mission=ReadIntegerQuery("ZeroSisLiveInteger=assert(MissionTypes.MISSION_ESTABLISH_TRADE_ROUTE)");
            TradeRouteSmokeFixture::Dispatch(host_,*receiver_,plan,mission);
            game_->Update();Check();
            std::printf("INTERACTIVE_TRADE_ROUTE_FIXTURE=FRESH|%d|%d|%d|%zu|%d\n",
                plan.activePlayer,plan.turn,plan.elapsed,plan.missions.size(),plan.createdCities);
        }else{
            if(!TradeRouteSmokeFixture::MeetsSmokeMinimum(plan.before))
                throw std::runtime_error("Restored trade-route fixture lost its real SDK routes");
            std::printf("INTERACTIVE_TRADE_ROUTE_FIXTURE=RESTORED|%d|%d|%d|0|0\n",plan.activePlayer,plan.turn,plan.elapsed);
        }
    }
    void RequireTradeRoutesSmokeReady(){
        Owner();const auto inventory=TradeRouteSmokeFixture::CaptureInventory(host_,*host_.scripts,vm_);
        if(!TradeRouteSmokeFixture::MeetsSmokeMinimum(inventory))
            throw std::runtime_error("SDK trade-route fixture minimum failed: player="+std::to_string(inventory.activePlayer)+
                " turn="+std::to_string(inventory.turn)+" outbound="+std::to_string(inventory.outbound.size())+
                " inbound="+std::to_string(inventory.inbound.size())+" available="+std::to_string(inventory.available.size()));
        std::printf("INTERACTIVE_TRADE_ROUTE_INVENTORY_READY=%d|%d|%zu|%zu|%zu\n",inventory.activePlayer,inventory.turn,
            inventory.outbound.size(),inventory.inbound.size(),inventory.available.size());
    }
    std::string CaptureTradeRoutesSmoke(){
        Owner();return TradeRouteSmokeFixture::SerializeInventory(TradeRouteSmokeFixture::CaptureInventory(host_,*host_.scripts,vm_));
    }
    std::string CaptureTradeVisualsSmoke(){
        Owner();return host_.tradeRoutes.SnapshotJson();
    }
    SocialPolicySmokeFixture::Inventory PrepareSocialPolicySmoke(bool fresh){
        Owner();if(!HumanTurn() || HasUi())throw std::logic_error("Policy fixture requires its idle active human turn");
        const auto result=SocialPolicySmokeFixture::Prepare(host_,*host_.scripts,vm_,fresh);
        if(fresh){game_->Update();Check();}
        return result;
    }
    SocialPolicySmokeFixture::Inventory ObserveSocialPolicySmoke(){
        Owner();return SocialPolicySmokeFixture::Capture(host_,*host_.scripts,vm_);
    }
    SocialPolicySmokeFixture::Inventory PreparePolicyTenetSmoke(bool fresh){
        Owner();if(!HumanTurn() || HasUi())throw std::logic_error("Tenet prerequisites require the idle active human turn");
        const auto result=SocialPolicySmokeFixture::PrepareTenets(host_,*host_.scripts,vm_,fresh);
        if(fresh){game_->Update();Check();}return result;
    }
    SocialPolicySmokeFixture::Inventory FundPaidPolicyTenetSmoke(){
        Owner();if(!HumanTurn() || !HasUi() || UiKind()!=UiPopupKind::SocialPolicy)
            throw std::logic_error("Paid tenet culture requires its settled original popup");
        const auto result=SocialPolicySmokeFixture::FundPaidTenet(host_,*host_.scripts,vm_);
        game_->Update();Check();ui_->RefreshSocialPolicy();return result;
    }
    int SelectedPolicyTenet(){Owner();return ui_->SelectedPolicyTenet();}
    SocialPolicySmokeFixture::Inventory FundSecondSocialPolicySmoke(){
        Owner();if(!HumanTurn() || !HasUi() || UiKind()!=UiPopupKind::SocialPolicy)
            throw std::logic_error("Second policy culture fixture requires its original settled popup");
        const auto result=SocialPolicySmokeFixture::FundSecondChoice(host_,*host_.scripts,vm_);
        game_->Update();Check();ui_->RefreshSocialPolicy();return result;
    }
    int OriginalUnitMissionAction(int mission){
        if(mission<0)throw std::invalid_argument("Original mission identity is invalid");
        return ReadIntegerQuery("ZeroSisLiveInteger=-1;local wanted=assert(GameInfo.Missions["+std::to_string(mission)+
            "]);for index,info in pairs(GameInfoActions) do if info.Type==wanted.Type then "
            "assert(ZeroSisLiveInteger==-1 and info.MissionType==wanted.ID and info.ActionInfoIndex==index);"
            "ZeroSisLiveInteger=index end end;assert(ZeroSisLiveInteger>=0)");
    }
    int OriginalUnitBuildAction(int build){
        if(build<0)throw std::invalid_argument("Original build identity is invalid");
        return ReadIntegerQuery("ZeroSisLiveInteger=-1;local wanted=assert(GameInfo.Builds["+std::to_string(build)+
            "]);local mission=assert(GameInfo.Missions.MISSION_BUILD);for index,info in pairs(GameInfoActions) do "
            "if info.Type==wanted.Type then assert(ZeroSisLiveInteger==-1 and "
            "info.SubType==ActionSubTypes.ACTIONSUBTYPE_BUILD and info.MissionType==mission.ID and "
            "info.MissionData==wanted.ID and info.OriginalIndex==wanted.ID and info.ActionInfoIndex==index);"
            "ZeroSisLiveInteger=index end end;assert(ZeroSisLiveInteger>=0)");
    }
    bool DispatchUnitPanel(const ZeroSisPresentation::BitmapInputEvent& input,bool* frameChanged=nullptr){
        if(frameChanged)*frameChanged=false;
        Owner();if(!ui_)return false;
        bool changed=false;
        const bool consumed=ui_->DispatchUnitPanel(input,frameChanged?&changed:nullptr);
        if(consumed && input.kind==ZeroSisPresentation::BitmapInputKind::ControlClick){game_->Update();Check();}
        if(frameChanged)*frameChanged=changed;
        return consumed;
    }
    void VerifyUnitPanelSnapshot(const std::string& snapshot){Owner();ui_->VerifyUnitPanelSnapshot(snapshot);}
    void VerifyUiSnapshot(const std::string& snapshot,const std::string& cityBackdrop,const std::string& economicBackdrop={}){
        Owner();ui_->VerifySnapshot(snapshot,cityBackdrop,economicBackdrop);
    }
    bool HasMandatoryCityDecision(){Owner();return ui_ && ui_->HasCaptureDecision();}
    bool HasMandatoryUiDecision(){Owner();return ui_ && (ui_->HasCaptureDecision() || ui_->HasLeaderDecision());}
    void CloseUi(){Owner();if(HasMandatoryUiDecision())throw std::logic_error("Mandatory original UI callback must complete before closing UI");if(ui_)ui_->CloseAll();}
    UiPopupKind UiKind(){Owner();return ui_->ActiveKind();}
    int TechAwardTechnology(){Owner();return ui_->TechAwardTechnology();}
    std::vector<UiInputTarget> UiTargets(){Owner();return ui_->Targets();}
    std::uint64_t CapturedViewKey(){Owner();if(!ui_)throw std::logic_error("Interactive UI is not available");return ui_->CapturedViewKey();}
    std::uint64_t CityViewExitKey(){Owner();if(!ui_)throw std::logic_error("Interactive UI is not available");return ui_->CityViewExitKey();}
    std::uint64_t CapturedPuppetKey(){Owner();if(!ui_)throw std::logic_error("Interactive UI is not available");return ui_->CapturedPuppetKey();}
    std::uint64_t LeaderBackKey(){Owner();if(!ui_)throw std::logic_error("Interactive UI is not available");return ui_->LeaderBackKey();}
    int CurrentResearch(){return ReadIntegerQuery("ZeroSisLiveInteger=assert(Players[Game.GetActivePlayer()]):GetCurrentResearch()");}
    bool HasTechnology(int tech){return Query("ZeroSisLiveResult=assert(Teams[Players[Game.GetActivePlayer()]:GetTeam()]):IsHasTech("+std::to_string(tech)+")");}
    void PrepareResearchCompletionSmoke(int tech){
        Owner();if(HasUi() || !HumanTurn() || tech<0)throw std::logic_error("Research fixture requires its settled human turn");
        // The original UI selected this technology. Prepare an explicit
        // incomplete amount only; normal doResearch must earn the final point.
        Execute("local id=Game.GetActivePlayer();local p=assert(Players[id]);local team=assert(Teams[p:GetTeam()]);"
            "local tech="+std::to_string(tech)+";assert(GameInfo.Technologies[tech] and p:GetCurrentResearch()==tech and not team:IsHasTech(tech));"
            "local t=assert(team:GetTeamTechs());local before=p:GetResearchProgress(tech);local cost=p:GetResearchCost(tech);"
            "local science=p:GetScienceTimes100();assert(cost>1 and science>=100);t:SetResearchProgress(tech,cost-1,id);"
            "assert(not team:IsHasTech(tech) and p:GetCurrentResearch()==tech and p:GetResearchProgress(tech)==cost-1);"
            "print('INTERACTIVE_RESEARCH_COMPLETION_FIXTURE='..Game.GetGameTurn()..'|'..id..'|'..p:GetTeam()..'|'..tech..'|'..before..'|'..(cost-1)..'|'..cost..'|'..science..'|0')");
    }
    int CityFocus(int city){return ReadIntegerQuery("ZeroSisLiveInteger=assert(Players[Game.GetActivePlayer()]:GetCityByID("+std::to_string(city)+")):GetFocusType()");}
    bool CityAvoidGrowth(int city){return ReadIntegerQuery("ZeroSisLiveInteger=assert(Players[Game.GetActivePlayer()]:GetCityByID("+std::to_string(city)+")):IsForcedAvoidGrowth() and 1 or 0")!=0;}
    int PrepareCityManagementSmoke(int city){
        Owner();if(HasUi())throw std::logic_error("City UI fixture must precede the original screen entry");
        Execute("local p=assert(Players[Game.GetActivePlayer()]);local c=assert(p:GetCityByID("+std::to_string(city)+"));"
            "local b=assert(GameInfoTypes.BUILDING_WORKSHOP);local oldGold=p:GetGold();local oldPopulation=c:GetPopulation();"
            "local oldBuilding=c:GetNumRealBuilding(b);if oldGold<200 then p:ChangeGold(200-oldGold) end;"
            "if oldPopulation<3 then c:ChangePopulation(3-oldPopulation,true) end;"
            "if oldBuilding==0 then c:SetNumRealBuilding(b,1) end;"
            "print('INTERACTIVE_CITY_UI_FIXTURE='..c:GetID()..'|'..oldGold..'|'..p:GetGold()..'|'..oldPopulation..'|'..c:GetPopulation()..'|'..b..'|'..oldBuilding..'|'..c:GetNumRealBuilding(b));"
            "ZeroSisLiveInteger=b");
        return ReadIntegerQuery("ZeroSisLiveInteger=assert(GameInfoTypes.BUILDING_WORKSHOP)");
    }
    bool CityNoAutoSpecialists(int city){return CityInteger(city,"IsNoAutoAssignSpecialists() and 1 or 0")!=0;}
    int CitySpecialists(int city,int building){return CityInteger(city,"GetNumSpecialistsInBuilding("+std::to_string(building)+")");}
    int CityBuildingCount(int city,int building){return CityInteger(city,"GetNumRealBuilding("+std::to_string(building)+")");}
    bool CityForcedPlot(int city,int index){return CityPlotInteger(city,index,"c:IsForcedWorkingPlot(plot) and 1 or 0")!=0;}
    bool CityWorkedPlot(int city,int index){return CityPlotInteger(city,index,"c:IsWorkingPlot(plot) and 1 or 0")!=0;}
    bool CityCanWorkPlot(int city,int index){return CityPlotInteger(city,index,"c:CanWork(plot) and 1 or 0")!=0;}
    int CityPlotOwner(int city,int index){return CityPlotInteger(city,index,"plot:GetOwner()");}
    int CityPlotCost(int city,int index){return CityPlotInteger(city,index,"c:GetBuyPlotCost(plot:GetX(),plot:GetY())");}
    int ActiveGold(){return ReadIntegerQuery("ZeroSisLiveInteger=assert(Players[Game.GetActivePlayer()]):GetGold()");}
    void PrepareCityPurchaseSmoke(int city){
        Owner();if(HasUi())throw std::logic_error("Purchase fixture must precede the original screen entry");
        Execute("local p=assert(Players[Game.GetActivePlayer()]);local c=assert(p:GetCityByID("+std::to_string(city)+"));"
            "local before=p:GetGold();if before<5000 then p:ChangeGold(5000-before) end;"
            "print('INTERACTIVE_CITY_PURCHASE_FIXTURE='..c:GetID()..'|'..before..'|'..p:GetGold());"
            "local team=assert(Teams[p:GetTeam()]);local tech=assert(GameInfoTypes.TECH_POTTERY);local known=team:IsHasTech(tech);"
            // Only prepare a purchase prerequisite. This does not test normal
            // research completion or its separate reward popup.
            "if not known then team:GetTeamTechs():SetHasTech(tech,true) end;"
            "assert(team:IsHasTech(tech));print('INTERACTIVE_CITY_PURCHASE_TECH_FIXTURE='..p:GetTeam()..'|'..tech..'|'..(known and 1 or 0)..'|1')");
    }
    struct PurchaseObservation {int price=0,gold=0,faith=0,count=0;bool legal=false;};
    PurchaseObservation ObservePurchase(int city,int selection,int item){
        Owner();if(city<0 || item<0 || selection<0 || selection>5)throw std::invalid_argument("Invalid stock purchase selection");
        const int slot=selection%3;const bool gold=selection<3;
        const std::string prefix="local p=assert(Players[Game.GetActivePlayer()]);local c=assert(p:GetCityByID("+
            std::to_string(city)+"));local id="+std::to_string(item)+";";
        const std::string price=slot==0?(gold?"c:GetUnitPurchaseCost(id)":"c:GetUnitFaithPurchaseCost(id,true)"):
            slot==1?(gold?"c:GetBuildingPurchaseCost(id)":"c:GetBuildingFaithPurchaseCost(id)"):"c:GetProjectPurchaseCost(id)";
        PurchaseObservation result;
        result.price=ReadIntegerQuery(prefix+"ZeroSisLiveInteger="+price);
        result.gold=ReadIntegerQuery(prefix+"ZeroSisLiveInteger=p:GetGold()");
        result.faith=ReadIntegerQuery(prefix+"ZeroSisLiveInteger=p:GetFaith()");
        result.count=ReadIntegerQuery(prefix+(slot==0?
            "local n=0;for u in p:Units() do if u:GetUnitType()==id then n=n+1 end end;ZeroSisLiveInteger=n":
            slot==1?"ZeroSisLiveInteger=c:GetNumBuilding(id)":"ZeroSisLiveInteger=Teams[p:GetTeam()]:GetProjectCount(id)"));
        result.legal=Query(prefix+"ZeroSisLiveResult=c:IsCanPurchase(true,true,"+
            (slot==0?"id,-1,-1":slot==1?"-1,id,-1":"-1,-1,id")+",YieldTypes."+(gold?"YIELD_GOLD":"YIELD_FAITH")+")");
        return result;
    }
    int CityInteger(int city,const std::string& query){return ReadIntegerQuery("ZeroSisLiveInteger=assert(Players[Game.GetActivePlayer()]:GetCityByID("+std::to_string(city)+")):"+query);}
    int CityPlotInteger(int city,int index,const std::string& query){return ReadIntegerQuery("local c=assert(Players[Game.GetActivePlayer()]:GetCityByID("+std::to_string(city)+"));local plot=assert(c:GetCityIndexPlot("+std::to_string(index)+"));ZeroSisLiveInteger="+query);}
    int UnitActivity(int id){return ReadIntegerQuery("ZeroSisLiveInteger=assert(Players[Game.GetActivePlayer()]:GetUnitByID("+std::to_string(id)+")):GetActivityType()");}
    int ProductionUnit(int city){return ReadIntegerQuery("ZeroSisLiveInteger=assert(Players[Game.GetActivePlayer()]:GetCityByID("+std::to_string(city)+")):GetProductionUnit()");}
    bool CanResearch(int tech){Owner();return Query("ZeroSisLiveResult=assert(Players[Game.GetActivePlayer()]):CanResearch("+std::to_string(tech)+")");}
    bool CanTrain(int city,int unit){Owner();return Query("ZeroSisLiveResult=assert(Players[Game.GetActivePlayer()]:GetCityByID("+std::to_string(city)+")):CanTrain("+std::to_string(unit)+")");}
    struct ProductionObservation final {int length=-1,unit=-1,production=-1,needed=-1;};
    ProductionObservation ObserveProduction(int city){
        Owner();if(!OwnsCity(city))throw std::logic_error("Production observation requires the active player's city");
        return {CityInteger(city,"GetOrderQueueLength()"),ProductionUnit(city),
                CityInteger(city,"GetProduction()"),CityInteger(city,"GetProductionNeeded()")};
    }
    // Natural research can outlast any particular city order. Keep the existing
    // DecisionState production contract for the separate initial decision gate.
    std::array<int,12> ObserveResearch(int tech,bool allowCompleted=false){
        Owner();Execute("local p=assert(Players[Game.GetActivePlayer()]);local team=assert(Teams[p:GetTeam()]);"
            "assert(GameInfo.Technologies["+std::to_string(tech)+"] and (p:GetCurrentResearch()=="+std::to_string(tech)+
            (allowCompleted?" or team:IsHasTech("+std::to_string(tech)+")":"")+
            "));local t=assert(team:GetTeamTechs());ZeroSisLiveDecision={Game.GetGameTurn(),Game.GetElapsedGameTurns(),"
            "Game.GetActivePlayer(),0,0,"+std::to_string(tech)+",0,0,0,p:GetResearchProgress("+std::to_string(tech)+"),"
            "t:GetResearchLeft("+std::to_string(tech)+"),0}");
        std::array<int,12> result{};
        if(!host_.scripts->CallCFunction(vm_,&ReadDecision,&result))throw std::runtime_error(host_.scripts->LastError());
        return result;
    }
    std::array<int,12> DecisionState(int city,int unit,int tech,bool allowCompleted=false){
        Owner();Execute("local p=assert(Players[Game.GetActivePlayer()]);local c=assert(p:GetCityByID("+std::to_string(city)+
            "));assert(c:GetOwner()==Game.GetActivePlayer() and c:GetProductionUnit()=="+std::to_string(unit)+
            " and (p:GetCurrentResearch()=="+std::to_string(tech)+
            (allowCompleted?" or Teams[p:GetTeam()]:IsHasTech("+std::to_string(tech)+")":"")+
            "));local t=assert(Teams[p:GetTeam()]:GetTeamTechs());"
            "ZeroSisLiveDecision={Game.GetGameTurn(),Game.GetElapsedGameTurns(),Game.GetActivePlayer(),c:GetID(),"+
            std::to_string(unit)+","+std::to_string(tech)+",c:GetOrderQueueLength(),c:GetProduction(),c:GetProductionNeeded(),"
            "p:GetResearchProgress("+std::to_string(tech)+"),t:GetResearchLeft("+std::to_string(tech)+"),c:GetPopulation()}");
        std::array<int,12> result{};
        if(!host_.scripts->CallCFunction(vm_,&ReadDecision,&result))throw std::runtime_error(host_.scripts->LastError());
        return result;
    }
private:
    std::shared_ptr<const UiMapMenuCatalog> CaptureMapMenuCatalog(){
        Owner();
        if(!core_ || !mapCatalog_ || !ui_ || !HumanTurn() || host_.autoSaveRunning ||
           !host_.scripts || !host_.scripts->IsQuiescent() || !host_.localCommands.IsQuiescent() || HasMandatoryUiDecision())
            throw std::logic_error("Map menu requires its settled current human owner");
        std::unique_ptr<ICvPreGame1> pregame(core_->GetPreGame());
        std::unique_ptr<ICvWorldInfo1> world(pregame?pregame->GetWorldInfo():nullptr);
        if(!pregame || !world || !world->GetType() || !*world->GetType())throw std::runtime_error("Map menu setup metadata is missing");
        auto catalog=std::make_shared<UiMapMenuCatalog>();catalog->files=mapCatalog_->List();
        const auto script=pregame->mapScriptName();catalog->mapScript.assign(script.data(),script.size());
        catalog->worldType=world->GetType();catalog->worldSize=static_cast<int>(pregame->worldSize());
        const auto maps=mapCatalog_;catalog->nameAvailable=[maps](const std::string& name){return maps->NameAvailable(name);};
        mapMenuCatalog_=catalog;return catalog;
    }
    void ApplyMapMenuRequests(const std::vector<MapMenuRequest>& requests){
        Owner();
        if(!ui_ || !core_ || !mapCatalog_ || !mapMenuCatalog_ || !HumanTurn() || host_.autoSaveRunning ||
           !host_.scripts || !host_.scripts->IsQuiescent() || !host_.localCommands.IsQuiescent() || HasMandatoryUiDecision())
            throw std::logic_error("Map menu mutation requires its completed active human callback");
        if(requests.empty()){ui_->Update();return;}
        if(requests.size()!=1)throw std::logic_error("Map menu callback queued more than one mutation");
        const auto& request=requests.front();
        const bool save=request.kind==MapMenuRequest::Kind::Save;
        const bool overwrite=request.kind==MapMenuRequest::Kind::Overwrite;
        const bool remove=request.kind==MapMenuRequest::Kind::Delete;
        if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn() ||
           (!save && !overwrite && !remove) || (!!request.expected!=(overwrite || remove)))
            throw std::logic_error("Map menu command lost its owner, turn, or selected file identity");
        if(request.expected){
            const auto& expected=*request.expected;
            const auto found=std::find_if(mapMenuCatalog_->files.begin(),mapMenuCatalog_->files.end(),[&](const UiMapMenuFile& listed){
                return listed.path==expected.path && listed.name==expected.name && listed.identity==expected.identity &&
                    listed.checksum==expected.checksum && listed.bytes==expected.bytes && listed.timeHigh==expected.timeHigh && listed.timeLow==expected.timeLow;
            });
            if(found==mapMenuCatalog_->files.end())throw std::logic_error("Map menu selected an unlisted or changed file observation");
        }
        const auto before=SdkStateSnapshot::Capture(host_);
        if(remove){
            mapCatalog_->Delete(*request.expected);
            ui_->RefreshMapMenu(CaptureMapMenuCatalog());
        }else{
            ui_->Update();ui_->FinishMapMenuForSave();
            const auto output=mapCatalog_->Save(request.name,request.expected,[this](const std::wstring& path,const std::string& name){
                std::unique_ptr<ICvWorldBuilderMapLoader1> writer(core_->GetWorldBuilderMapLoader());
                if(!writer)throw std::runtime_error("SDK map writer is unavailable");
                return writer->Save(path.c_str(),name.c_str());
            });
            std::printf("INTERACTIVE_MAP_MENU_SAVED=%d|%d|%s|%llu\n",request.owner,request.turn,output.path.c_str(),static_cast<unsigned long long>(output.bytes));
            mapMenuCatalog_.reset();
        }
        if(SdkStateSnapshot::Capture(host_)!=before)throw std::runtime_error("Map menu serialization changed the semantic gameplay sample");
    }
    UiSaveMenuHeader CaptureSaveMenuHeader(){
        Owner();if(!core_ || !game_)throw std::logic_error("Save preview requires the live SDK owner");
        const auto active=game_->GetActivePlayer();
        std::unique_ptr<ICvPreGame1> pregame(core_->GetPreGame());
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(active));
        if(!pregame || !player || player->GetID()!=active || !player->IsAlive() || !player->IsHuman() || game_->IsGameMultiPlayer())
            throw std::logic_error("Save preview requires a real initialized local single-player identity");
        const auto text=[](const CvString& value){return std::string(value.data(),value.size());};
        UiSaveMenuHeader header;
        header.playerCivilization=static_cast<int>(pregame->civilization(active));
        header.gameSpeed=static_cast<int>(pregame->gameSpeed());header.startEra=static_cast<int>(pregame->era());
        header.turnNumber=game_->GetElapsedGameTurns();header.difficulty=static_cast<int>(pregame->handicap(active));
        header.worldSize=static_cast<int>(pregame->worldSize());header.currentEra=static_cast<int>(player->GetCurrentEra());
        header.gameType=static_cast<int>(pregame->gameType());header.mapScript=text(pregame->mapScriptName());
        header.leaderName=text(pregame->leaderName(active));header.civilizationName=text(pregame->civilizationDescription(active));
        return header;
    }
    static HostState& CheckedHost(const std::shared_ptr<HostState>& host){
        if(!host)throw std::invalid_argument("Interactive game owner is missing");return *host;
    }
    void Owner() const{LocalGameCommands::RequireOwnerLock(host_.gameThread==GetCurrentThreadId(),host_.gameLock.HeldByCurrentThread());}
    bool HumanTurnRaw(){
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(game_->GetActivePlayer()));
        return player && player->IsAlive() && player->IsHuman() && player->IsTurnActive();
    }
    bool HumanTurn(){return !advancing_ && HumanTurnRaw();}
    std::unique_ptr<ICvUnit1> Unit(int id){
        if(id<0)return nullptr;std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(game_->GetActivePlayer()));
        if(!player)return nullptr;std::unique_ptr<ICvUnit1> unit(player->GetUnit(id));
        if(!unit || unit->GetOwner()!=game_->GetActivePlayer() || unit->GetID()!=id)return nullptr;return unit;
    }
    static MissionTypes Mission(ICvGameContext3& context,const char* name){
        const int id=context.GetInfoTypeForString(name,true);
        if(id<0)throw std::runtime_error(std::string("Interactive mission rules missing: ")+name);
        std::unique_ptr<ICvMissionInfo1> info(context.GetMissionInfo(static_cast<MissionTypes>(id)));
        if(!info || !info->GetType() || std::strcmp(info->GetType(),name)!=0)throw std::runtime_error("Interactive mission identity differs");
        return static_cast<MissionTypes>(id);
    }
    struct BoolValue {bool value=false;};
    static int ReadUnitActions(lua_State* state){
        auto* output=static_cast<std::vector<UnitAction>*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisLiveUnitActions");
        if(!output || !lua_istable(state,-1) || lua_objlen(state,-1)>512)
            return luaL_error(state,"Interactive unit action list exceeds its bound");
        const std::size_t count=lua_objlen(state,-1);
        for(std::size_t i=0;i<count;++i){
            lua_rawgeti(state,-1,static_cast<int>(i+1));
            if(!lua_istable(state,-1) || lua_objlen(state,-1)!=5)return luaL_error(state,"Invalid unit action row");
            int values[4]{};
            for(int field=1;field<=4;++field){
                lua_rawgeti(state,-1,field);const double value=lua_tonumber(state,-1);
                if(lua_type(state,-1)!=LUA_TNUMBER || !std::isfinite(value) || value<(field<=2?0:-1) || value>INT_MAX || std::floor(value)!=value)
                    return luaL_error(state,"Invalid unit action integer");
                values[field-1]=static_cast<int>(value);lua_pop(state,1);
            }
            lua_rawgeti(state,-1,5);
            if(lua_type(state,-1)!=LUA_TSTRING)return luaL_error(state,"Invalid unit action label type");
            std::size_t size=0;const char* label=lua_tolstring(state,-1,&size);
            if(!label || size==0 || size>1024 || std::memchr(label,0,size))
                return luaL_error(state,"Invalid unit action label");
            output->push_back({values[0],values[1],values[2],values[3],std::string(label,size)});
            lua_pop(state,2);
        }
        return 0;
    }
    static int ReadDecision(lua_State* state){
        auto* output=static_cast<std::array<int,12>*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisLiveDecision");
        if(!output || !lua_istable(state,-1) || lua_objlen(state,-1)!=output->size())
            return luaL_error(state,"Interactive city observation schema differs");
        for(std::size_t i=0;i<output->size();++i){
            lua_rawgeti(state,-1,static_cast<int>(i+1));const double value=lua_tonumber(state,-1);
            if(lua_type(state,-1)!=LUA_TNUMBER || !std::isfinite(value) || value<0 || value>INT_MAX || std::floor(value)!=value)
                return luaL_error(state,"Interactive city observation is not a bounded integer");
            (*output)[i]=static_cast<int>(value);lua_pop(state,1);
        }
        return 0;
    }
    static int ReadCapturedCityObservation(lua_State* state){
        auto* output=static_cast<CapturedCityObservation*>(lua_touserdata(state,1));lua_settop(state,0);
        lua_getglobal(state,"ZeroSisLiveCapturedCityObservation");
        if(!output || !lua_istable(state,-1) || lua_objlen(state,-1)!=5)
            return luaL_error(state,"Captured-city observation schema differs");
        int values[5]{};
        for(int field=1;field<=5;++field){
            lua_rawgeti(state,-1,field);const double value=lua_tonumber(state,-1);
            if(lua_type(state,-1)!=LUA_TNUMBER || !std::isfinite(value) || value<INT_MIN || value>INT_MAX || std::floor(value)!=value)
                return luaL_error(state,"Captured-city observation field is not a bounded integer");
            values[field-1]=static_cast<int>(value);lua_pop(state,1);
        }
        if(values[0]<0){
            if(values[0]!=-1 || values[1]!=-1 || values[2]!=0 || values[3]!=0 || values[4]!=-1)
                return luaL_error(state,"Empty captured-city observation has inconsistent sentinels");
        }else if(values[1]<0 || values[1]>=MAX_PLAYERS ||
            (values[2]!=0 && values[2]!=1) || (values[3]!=0 && values[3]!=1) ||
            values[4]<-1 || values[4]>=MAX_PLAYERS){
            return luaL_error(state,"Captured-city observation identity or flags are invalid");
        }
        *output={values[0],values[1],values[2],values[3],values[4]};return 0;
    }
    static int ReadInteger(lua_State* state){
        auto* result=static_cast<int*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!result)return luaL_error(state,"Interactive integer output is missing");
        lua_getglobal(state,"ZeroSisLiveInteger");
        if(lua_type(state,-1)!=LUA_TNUMBER)return luaL_error(state,"Interactive observation is not an integer");
        const double value=lua_tonumber(state,-1);
        if(!std::isfinite(value) || value<INT_MIN || value>INT_MAX || std::floor(value)!=value)
            return luaL_error(state,"Interactive observation is outside the integer range");
        *result=static_cast<int>(value);return 0;
    }
    int ReadIntegerQuery(const std::string& code){
        Owner();Execute(code);int result=-1;
        if(!host_.scripts->CallCFunction(vm_,&ReadInteger,&result))throw std::runtime_error(host_.scripts->LastError());
        return result;
    }
    static int ReadBool(lua_State* state){
        auto* result=static_cast<BoolValue*>(lua_touserdata(state,1));lua_settop(state,0);
        if(!result)return luaL_error(state,"Interactive query output is missing");
        lua_getglobal(state,"ZeroSisLiveResult");
        if(lua_type(state,-1)!=LUA_TBOOLEAN)return luaL_error(state,"Interactive query did not return a bool");
        result->value=lua_toboolean(state,-1)!=0;return 0;
    }
    void Execute(const std::string& code){
        const auto* continuation=host_.confirmedWarContinuation;
        if(!host_.scripts->IsQuiescent() && (!continuation || !MatchesWarContinuation(
            continuation->unit,continuation->x,continuation->y,continuation->ranged)))
            throw std::logic_error("Interactive script execution requires quiescence or the exact confirmed war continuation");
        if(!host_.scripts->Execute(vm_,code.data(),code.size(),"interactive-command"))throw std::runtime_error(host_.scripts->LastError());
    }
    bool Query(const std::string& code){
        Execute(code);BoolValue result;
        if(!host_.scripts->CallCFunction(vm_,&ReadBool,&result))throw std::runtime_error(host_.scripts->LastError());return result.value;
    }
    bool IsPantheonLegal(PlayerTypes owner,BeliefTypes belief){
        Owner();
        // The original popup has already closed and released its timer. Only
        // read the SDK from this separate command VM after its Lua unwinds.
        // LocalGameCommands is dispatching here, so it is not quiescent yet.
        if(!game_ || !core_ || !vm_ || !host_.scripts || !host_.scripts->IsQuiescent() ||
           advancing_ || static_cast<int>(owner)<0 || static_cast<int>(owner)>=MAX_CIV_PLAYERS ||
           static_cast<int>(belief)<0 || game_->GetActivePlayer()!=owner ||
           game_->IsGameMultiPlayer() || game_->GetGameState()==GAMESTATE_OVER)return false;
        const int turn=game_->GetGameTurn();
        if(ui_ && ui_->HasModal() && !ui_->IsPantheonCommitBoundary(owner,turn,belief))return false;
        std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(owner));
        if(!player || player->GetID()!=owner || !player->IsAlive() || !player->IsHuman() || !player->IsTurnActive())return false;
        std::unique_ptr<ICvCity1> capital(player->GetCapitalCity());
        if(!capital || capital->GetOwner()!=owner)return false;
        const bool allowed=Query("local p=Players["+std::to_string(static_cast<int>(owner))+"] ;"
            "ZeroSisLiveResult=false;"
            "if p and not p:HasCreatedPantheon() and p:CanCreatePantheon(true) then "
            "for _,id in ipairs(assert(Game.GetAvailablePantheonBeliefs())) do "
            "if id=="+std::to_string(static_cast<int>(belief))+" then ZeroSisLiveResult=true;break end end end");
        return allowed && game_->GetActivePlayer()==owner && game_->GetGameTurn()==turn &&
            !advancing_ && player->IsAlive() && player->IsHuman() && player->IsTurnActive();
    }
    bool IsCaptureCityTaskLegal(int cityID,TaskTypes task,int data1,int data2,bool option,bool alt,bool shift,bool control){
        Owner();
        if(!HumanTurn() || !ui_ || data1!=-1 || data2!=-1 || option || alt || shift || control ||
            (task!=TASK_ANNEX_PUPPET && task!=TASK_CREATE_PUPPET && task!=TASK_RAZE) ||
            !ui_->CaptureDecisionMatches(cityID,-2) || !OwnsCity(cityID))return false;
        const int taskID=static_cast<int>(task);
        return Query("local id=Game.GetActivePlayer();local p=Players[id];local c=p and p:GetCityByID("+
            std::to_string(cityID)+");local task="+std::to_string(taskID)+";"
            "local capture=c~=nil and c:GetOwner()==id;"
            "local allowed=false;"
            "if task==TaskTypes.TASK_ANNEX_PUPPET then allowed=capture and not p:MayNotAnnex() "
            "elseif task==TaskTypes.TASK_CREATE_PUPPET then allowed=capture "
            "elseif task==TaskTypes.TASK_RAZE then allowed=capture and p:CanRaze(c) end;"
            "ZeroSisLiveResult=allowed");
    }
    bool IsCaptureCityLiberationLegal(PlayerTypes liberated,int cityID){
        Owner();const int liberatedID=static_cast<int>(liberated);
        if(!HumanTurn() || !ui_ || !OwnsCity(cityID) ||
            !ui_->CaptureDecisionMatches(cityID,liberatedID))return false;
        // The exact recipient comes from the pending original popup. A dead
        // recipient remains eligible for the SDK's liberation rules.
        return true;
    }
    bool CanStartMission(int id,MissionTypes mission,int x,int y){
        Owner();const std::string code="local p=Players[Game.GetActivePlayer()]; local u=p and p:GetUnitByID("+std::to_string(id)+
            "); ZeroSisLiveResult=u~=nil and u:CanStartMission("+std::to_string(static_cast<int>(mission))+","+
            std::to_string(x)+","+std::to_string(y)+",u:GetPlot(),0) or false";
        return Query(code);
    }
    bool InMap(int x,int y) const{return x>=0 && x<map_->GetGridWidth() && y>=0 && y<map_->GetGridHeight();}
    bool VisibleHostile(ICvPlot1& plot,TeamTypes activeTeam){
        // Never enumerate hidden occupants, even for an unsuccessful click.
        if(activeTeam<0 || activeTeam>=MAX_TEAMS || !plot.IsVisible(activeTeam,false))return false;
        if(activeTeam!=game_->GetActiveTeam() || !team_)return false;
        std::unique_ptr<ICvCity1> city(plot.GetPlotCity());
        if(city){
            const auto owner=city->GetOwner();
            if(owner<0 || owner>=MAX_PLAYERS)throw std::runtime_error("Visible combat city has an invalid owner");
            std::unique_ptr<ICvPlayer1> player(game_->GetPlayer(owner));
            if(player && team_->IsAtWar(player->GetTeam()))return true;
        }
        const int count=plot.GetNumUnits();
        if(count<0 || count>100000)throw std::runtime_error("Visible combat plot exceeds its unit bound");
        for(int index=0;index<count;++index){
            std::unique_ptr<ICvUnit1> target(plot.GetUnitByIndex(index));
            if(!target || target->IsDelayedDeathExported() || target->IsInvisible(activeTeam,false))continue;
            const auto other=target->GetTeam();
            if(other<0 || other>=MAX_TEAMS)throw std::runtime_error("Visible combat target has an invalid team");
            if(team_->IsAtWar(other))return true;
        }
        return false;
    }
    bool IsAttackLegal(int id,int x,int y,bool ranged){
        Owner();if(!HumanTurn() || !InMap(x,y) || ((ui_ && ui_->HasModal()) && !MatchesWarContinuation(id,x,y,ranged)))return false;
        auto unit=Unit(id);if(!unit || unit->MovesLeft()<=0 || unit->IsBusy() || unit->IsDelayedDeathExported())return false;
        std::unique_ptr<ICvPlot1> target(map_->GetPlot(x,y));
        if(!target || !VisibleHostile(*target,unit->GetTeam()))return false;
        if(ranged)return Query("ZeroSisLiveResult=assert(Players[Game.GetActivePlayer()]:GetUnitByID("+
            std::to_string(id)+")):CanRangeStrikeAt("+std::to_string(x)+","+std::to_string(y)+",true,true)") &&
            CanStartMission(id,rangeMission_,x,y);
        std::unique_ptr<ICvPlot1> origin(unit->GetPlot());
        // CvUnit::MOVEFLAG_ATTACK is 0x01. The pathfinder/mission flag 0x20 is
        // only sent after this adjacent target needs NO new declaration of war.
        return origin && origin->IsAdjacent(target.get()) && unit->GetDeclareWarMove(target.get())==NO_TEAM &&
            unit->CanMoveInto(target.get(),static_cast<byte>(0x01)) && CanStartMission(id,moveMission_,x,y);
    }
    bool MatchesWarContinuation(int id,int x,int y,bool ranged){
        const auto* continuation=host_.confirmedWarContinuation;
        if(!continuation || continuation->owner!=game_->GetActivePlayer() || continuation->turn!=game_->GetGameTurn() ||
           continuation->unit!=id || continuation->x!=x || continuation->y!=y || continuation->ranged!=ranged)return false;
        const auto selection=host_.localSelection.Snapshot();
        return selection.size()==1 && selection.front().first==continuation->owner && selection.front().second==id;
    }
    bool IsMissionLegal(int id,MissionTypes mission,int x,int y,int flags){
        if(mission==rangeMission_)return flags==0 && IsAttackLegal(id,x,y,true);
        if(mission==moveMission_ && flags==LocalSdkSession::LiveAttackPathFlags)return IsAttackLegal(id,x,y,false);
        return flags==0 && CanStartMission(id,mission,x,y);
    }
    bool SendSelectedMission(MissionTypes mission,int x,int y,const wchar_t* success,int flags=0,bool shift=false){
        Owner();if(!HumanTurn())return Reject(L"\ud604\uc7ac\ub294 \uc720\ub2db \uba85\ub839\uc744 \ubcf4\ub0bc \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");
        const auto selection=host_.localSelection.Snapshot();
        if(selection.size()!=1 || selection.front().first!=game_->GetActivePlayer())
            return Reject(L"\uba3c\uc800 \uc720\ub2db \ud558\ub098\ub97c \uc120\ud0dd\ud558\uc2ed\uc2dc\uc624.");
        if((mission==moveMission_ || mission==rangeMission_) && !InMap(x,y))
            return Reject(L"\uc9c0\ub3c4 \ubc16\uc758 \uc88c\ud45c\uc785\ub2c8\ub2e4.");
        const int id=selection.front().second;auto unit=Unit(id);
        if(!unit || unit->IsBusy() || unit->IsDelayedDeathExported() || !IsMissionLegal(id,mission,x,y,flags))
            return Reject(L"\uc774 \uc720\ub2db\uc740 \uc694\uccad\ud55c \ud589\ub3d9\uc744 \ud560 \uc218 \uc5c6\uc2b5\ub2c8\ub2e4.");
        unit.reset();
        host_.localCommands.SendPushMission(id,mission,x,y,flags,shift);
        game_->Update();Check();status_=success;
        std::printf("INTERACTIVE_MISSION_ACCEPTED=%d|%d|%d|%d|%d\n",game_->GetGameTurn(),id,static_cast<int>(mission),x,y);return true;
    }
    void ApplySaveMenuRequests(const std::vector<SaveMenuRequest>& requests){
        Owner();
        if(!ui_ || !host_.scripts || !host_.scripts->IsQuiescent() || !host_.localCommands.IsQuiescent() || !HumanTurn())
            throw std::logic_error("SaveMenu handoff requires its completed local owner callback");
        if(requests.empty()){ui_->Update();return;}
        const bool save=requests.size()==2 && requests[0].kind==SaveMenuRequest::Kind::Save &&
            requests[1].kind==SaveMenuRequest::Kind::Close;
        const bool overwrite=requests.size()==2 && requests[0].kind==SaveMenuRequest::Kind::Overwrite &&
            requests[1].kind==SaveMenuRequest::Kind::Close;
        if(!save && !overwrite && !(requests.size()==1 && requests[0].kind==SaveMenuRequest::Kind::Close))
            throw std::logic_error("SaveMenu callback order must be Save or Overwrite then Close, or Close only");
        for(const auto& request:requests){
            if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn() ||
               (request.kind==SaveMenuRequest::Kind::Close && !request.name.empty()) ||
               (request.kind==SaveMenuRequest::Kind::Overwrite)!=!!request.expected)
                throw std::logic_error("SaveMenu command lost its active owner, turn, overwrite or close identity");
        }
        ui_->Update();
        if(save || overwrite){
            ui_->FinishSaveMenuForSave();
            if(overwrite)SaveNamedOverwrite(requests[0]);
            else{
                const auto path=SaveNamed(requests[0].name);
                if(path.empty())std::printf("INTERACTIVE_SAVE_MENU_NAMED_SAVE_REJECTED=%d|%d\n",requests[0].owner,requests[0].turn);
            }
        }
    }
    void ApplyLoadMenuRequests(const std::vector<LoadMenuRequest>& requests){
        Owner();
        if(!ui_ || !loadMenuCatalog_ || !saveCatalog_ || pendingLoad_.archive ||
           !host_.scripts || !host_.scripts->IsQuiescent() || !host_.localCommands.IsQuiescent() ||
           !HumanTurn() || host_.autoSaveRunning || HasMandatoryUiDecision())
            throw std::logic_error("LoadMenu handoff requires its completed local owner callback and original catalog");
        if(requests.empty()){ui_->Update();return;}
        const bool load=requests.size()==2 && requests[0].kind==LoadMenuRequest::Kind::Load &&
            requests[1].kind==LoadMenuRequest::Kind::Close;
        if(!load && !(requests.size()==1 && requests[0].kind==LoadMenuRequest::Kind::Close))
            throw std::logic_error("LoadMenu callback order must be Load then Close, or Close only");
        for(const auto& request:requests){
            if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn() ||
               (request.kind==LoadMenuRequest::Kind::Close && !request.fileName.empty()))
                throw std::logic_error("LoadMenu command lost its active owner, turn or close identity");
        }
        LoadHandoff handoff;
        if(load){
            const auto& fileName=requests[0].fileName;
            const auto& files=loadMenuCatalog_->files;
            const auto listed=std::find_if(files.begin(),files.end(),[&fileName](const UiSaveMenuFile& file){return file.fileName==fileName;});
            if(listed==files.end() || !listed->header ||
               loadMenuCatalog_->profile!=UiLoadMenuCatalog::Profile::OwnedCurrentExactBundleNoAdditionalContent)
                throw std::logic_error("LoadMenu request did not select an observed original catalog entry");
            // Preserve this exact checked handle's decoded immutable archive.
            // The old path becomes diagnostic data; teardown never reopens it.
            handoff.archive=saveCatalog_->ReadLoadArchive(fileName,*listed,loadMenuBundleManifest_);
            handoff.fileName=LoadFileName(fileName);
        }
        ui_->Update();
        if(load){
            ui_->FinishLoadMenuForLoad();
            pendingLoad_=std::move(handoff);
            std::printf("INTERACTIVE_LOAD_MENU_HANDOFF_READY=%d|%d|%s\n",requests[0].owner,requests[0].turn,requests[0].fileName.c_str());
        }
        loadMenuCatalog_.reset();loadMenuBundleManifest_.clear();
    }
    static std::wstring LoadFileName(const std::string& path){
        if(path.empty() || path.size()>static_cast<std::size_t>(INT_MAX) || path.find('\0')!=std::string::npos)
            throw std::invalid_argument("Load handoff has an invalid UTF-8 diagnostic path");
        const int count=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path.data(),static_cast<int>(path.size()),nullptr,0);
        if(count<=0)throw std::invalid_argument("Load handoff path is not valid UTF-8");
        std::wstring result(static_cast<std::size_t>(count),L'\0');
        if(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,path.data(),static_cast<int>(path.size()),&result[0],count)!=count)
            throw std::runtime_error("Load handoff path conversion failed");
        return result;
    }
    void ApplyGameMenuRequests(const std::vector<GameMenuRequest>& requests){
        Owner();if(requests.empty())return;
        if(requests.size()!=1 || pendingExit_ || pendingLoad_.archive || pendingLifecycle_.HasTransition() || !ui_ ||
           !host_.scripts || !host_.scripts->IsQuiescent() || !host_.localCommands.IsQuiescent())
            throw std::logic_error("Game menu commands require exactly one completed owner callback");
        const auto& request=requests.front();
        if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn() || !HumanTurn())
            throw std::logic_error("Game menu command lost its active human player or turn");
        if(request.kind==GameMenuRequest::Kind::Unavailable){
            status_=L"\uc544\uc9c1 \uc5f0\uacb0\ub418\uc9c0 \uc54a\uc740 \uba54\ub274 \uae30\ub2a5\uc785\ub2c8\ub2e4.";
            if(ui_)ui_->ShowGameMenuUnavailable(request.action,Utf8(status_));
            std::printf("INTERACTIVE_GAME_MENU_UNAVAILABLE=%d|%d|%s\n",request.owner,request.turn,request.action.c_str());return;
        }
        if(request.kind==GameMenuRequest::Kind::MainMenu || request.kind==GameMenuRequest::Kind::Restart ||
           request.kind==GameMenuRequest::Kind::Retire){
            if(host_.autoSaveRunning || HasMandatoryUiDecision() || loadMenuCatalog_ || !core_)
                throw std::logic_error("Menu lifecycle command conflicts with a save, load, or mandatory decision");
            ReadFileHandle file(bundle_+L"\\bundle.manifest");std::array<unsigned char,16385> bytes{};
            const auto size=file.Read(bytes.data(),static_cast<DWORD>(bytes.size()));
            if(!size || size==bytes.size())throw std::runtime_error("Menu lifecycle bundle identity is invalid");
            auto setup=std::make_shared<const MenuLifecycleSetup>(MenuLifecycleSetup::Capture(*core_,host_,{bytes.begin(),bytes.begin()+size}));
            // Capturing is read-only and precedes original timer release. No
            // lifecycle operation can unload the old SDK from a Lua callback.
            if(request.kind==GameMenuRequest::Kind::Retire){
                if(!retirement_)throw std::logic_error("Retirement provider was not installed");
                retirement_->Prepare(request.owner,request.turn,++lifecycleGeneration_);
            }
            ui_->FinishGameMenuForTransition();
            LoadHandoff handoff;handoff.setup=std::move(setup);
            if(request.kind==GameMenuRequest::Kind::MainMenu)handoff.mainMenu=true;
            else if(request.kind==GameMenuRequest::Kind::Restart){
                restartArmed_=true;restartObserved_=false;
                Execute("assert(Game.CanDoControl(ControlTypes.CONTROL_RESTART_GAME));Game.DoControl(ControlTypes.CONTROL_RESTART_GAME)");
                restartArmed_=false;
                if(!restartObserved_)throw std::runtime_error("Original SDK restart control omitted its host callback");
                handoff.restart=true;
            }else{
                Execute("assert(Game.CanDoControl(ControlTypes.CONTROL_RETIRE));Game.DoControl(ControlTypes.CONTROL_RETIRE)");
                if(!retirement_->Pending() || game_->GetGameState()!=GAMESTATE_OVER)
                    throw std::runtime_error("Original SDK retirement omitted its completed end-game sequence");
                handoff.endGame=std::make_shared<const MenuLifecycleEndGame>(retirement_->Take());
            }
            pendingLifecycle_=std::move(handoff);
            std::printf("INTERACTIVE_MENU_LIFECYCLE_READY=%d|%d|%s|NO_EXTRA_TICK\n",request.owner,request.turn,request.action.c_str());return;
        }
        if(request.kind==GameMenuRequest::Kind::Open){
            if(OpenGameMenu())return;
        }else if(request.kind==GameMenuRequest::Kind::OpenSaveMenu){
            ui_->OpenSaveMenu(CaptureSaveMenuCatalog());return;
        }else if(request.kind==GameMenuRequest::Kind::OpenLoadMenu){
            auto catalog=CaptureLoadMenuCatalog();
            ui_->OpenLoadMenu(catalog);loadMenuCatalog_=std::move(catalog);return;
        }else if(request.kind==GameMenuRequest::Kind::OpenMapMenu){
            ui_->OpenMapMenu(CaptureMapMenuCatalog());return;
        }else if(request.kind==GameMenuRequest::Kind::OpenMenuOptions){
            ui_->OpenMenuOptions();return;
        }else if(request.kind==GameMenuRequest::Kind::OpenTouchHelp){
            ui_->OpenTouchHelp();return;
        }else if(request.kind==GameMenuRequest::Kind::OpenExitConfirm){
            if(request.action!="ExitConfirm" || host_.autoSaveRunning || HasMandatoryUiDecision())
                throw std::logic_error("ExitConfirm request lost its original action or settled human owner");
            ui_->OpenExitConfirm();return;
        }else if(request.kind==GameMenuRequest::Kind::ExitGame){
            if(request.action!="ExitGame" || host_.autoSaveRunning || HasMandatoryUiDecision() || loadMenuCatalog_)
                throw std::logic_error("Confirmed exit conflicts with a save, load, or mandatory decision");
            // No save or SDK command is issued. The loop leaves after this
            // completed callback and its original parent has released its timer.
            ui_->FinishExitConfirmForExit();
            if(ui_->HasModal() || host_.popupVisible || !host_.scripts->IsQuiescent() ||
               !host_.localCommands.IsQuiescent())
                throw std::logic_error("Confirmed exit left an active modal or callback");
            pendingExit_=true;
            std::printf("INTERACTIVE_EXIT_GAME_HANDOFF_READY=%d|%d|NO_SAVE_NO_GAMEPLAY_COMMAND\n",request.owner,request.turn);return;
        }else if(request.kind==GameMenuRequest::Kind::QuickSave){
            if(ui_ && !ui_->HasModal() && !HasMandatoryUiDecision() && !host_.popupVisible && !host_.autoSaveRunning){
                const auto path=Save();
                std::printf("INTERACTIVE_GAME_MENU_QUICKSAVE=%d|%d|%s\n",request.owner,request.turn,Utf8(path).c_str());return;
            }
        }else throw std::logic_error("Unknown original game menu command");
        status_=L"\ub2e4\ub978 \uac8c\uc784 \ucc98\ub9ac\uac00 \ub05d\ub09c \ub4a4 \ub2e4\uc2dc \uc2dc\ub3c4\ud558\uc2ed\uc2dc\uc624.";
        std::printf("INTERACTIVE_GAME_MENU_COMMAND_REJECTED=%d|%d|%s\n",request.owner,request.turn,request.action.c_str());
    }
    bool Reject(const wchar_t* reason){status_=reason;std::printf("INTERACTIVE_INPUT_REJECTED=%s\n",Utf8(status_).c_str());return false;}
    void Check(){
        if(!host_.localCommands.IsQuiescent() || (host_.scripts && *host_.scripts->LastError()))
            throw std::runtime_error("Interactive SDK left commands or scripts incomplete");
    }
    std::shared_ptr<HostState> owner_;HostState& host_;std::wstring directory_,bundle_,status_;
    ICvGameContext3* core_=nullptr;std::shared_ptr<NativeSaveCatalog> saveCatalog_;
    std::shared_ptr<const UiSaveMenuCatalog> saveMenuCatalog_;
    std::vector<unsigned char> saveMenuBundleManifest_;
    std::shared_ptr<const UiLoadMenuCatalog> loadMenuCatalog_;
    std::vector<unsigned char> loadMenuBundleManifest_;
    LoadHandoff pendingLoad_;
    LoadHandoff pendingLifecycle_;
    std::unique_ptr<MenuLifecycleRetirement> retirement_;
    std::shared_ptr<NativeMapCatalog> mapCatalog_;
    std::shared_ptr<const UiMapMenuCatalog> mapMenuCatalog_;
    std::uint64_t lifecycleGeneration_=0;
    bool restartArmed_=false,restartObserved_=false;
    bool pendingExit_=false;
    std::unique_ptr<InteractiveUiSession> ui_;
    std::unique_ptr<ICvGame1> game_;std::unique_ptr<ICvMap1> map_;std::unique_ptr<ICvNetMessageHandler1> receiver_;
    std::unique_ptr<ICvTeam1> team_;
    std::unique_ptr<LocalSdkSession> local_;std::unique_ptr<SdkGameSave> saves_;std::unique_ptr<LocalTurnController> turns_;
    lua_State* vm_=nullptr;MissionTypes moveMission_=NO_MISSION,swapMission_=NO_MISSION,skipMission_=NO_MISSION,foundMission_=NO_MISSION,rangeMission_=NO_MISSION;
    int turnBefore_=-1;unsigned updates_=0,saveCount_=0;bool advancing_=false;
};
}
