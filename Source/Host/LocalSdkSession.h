#pragma once
#include "HostServices.h"

namespace ZeroSisHost {
// The receiver, game and context outlive this owner-thread scope. No SDK
// adapter or callable survives the scope or crosses a GameCore unload.
class LocalSdkSession final {
public:
    using MissionLegalityValidator=std::function<bool(int,MissionTypes,int,int,int)>;
    using CityTaskLegalityValidator=std::function<bool(int,TaskTypes,int,int,bool,bool,bool,bool)>;
    using LiberationLegalityValidator=std::function<bool(PlayerTypes,int)>;
    using WarLegalityValidator=std::function<bool(TeamTypes,TeamTypes)>;
    using PantheonLegalityValidator=std::function<bool(PlayerTypes,BeliefTypes)>;
    struct LiveMissionProfile final {
        MissionLegalityValidator canStartMission;
        CityTaskLegalityValidator canPerformCityTask;
        LiberationLegalityValidator canLiberatePlayer;
        WarLegalityValidator canDeclareWar;
        PantheonLegalityValidator canFoundPantheon;
    };
    // CvAStar.h: MOVE_DECLARE_WAR (0x00000020), consumed as a path/mission flag.
    // This is not CvUnit::MOVEFLAG_ATTACK (0x01), which is an internal move check.
    static constexpr int LiveAttackPathFlags=0x00000020;

    LocalSdkSession(HostState& host,ICvNetMessageHandler1& receiver,ICvGame1& game,ICvGameContext3& context)
        :LocalSdkSession(host,receiver,game,context,MissionLegalityValidator{},CityTaskLegalityValidator{},LiberationLegalityValidator{},WarLegalityValidator{},PantheonLegalityValidator{},false){}
    LocalSdkSession(HostState& host,ICvNetMessageHandler1& receiver,ICvGame1& game,ICvGameContext3& context,LiveMissionProfile profile)
        :LocalSdkSession(host,receiver,game,context,std::move(profile.canStartMission),std::move(profile.canPerformCityTask),std::move(profile.canLiberatePlayer),std::move(profile.canDeclareWar),std::move(profile.canFoundPantheon),true){}
private:
    LocalSdkSession(HostState& host,ICvNetMessageHandler1& receiver,ICvGame1& game,ICvGameContext3& context,MissionLegalityValidator missionValidator,CityTaskLegalityValidator cityTaskValidator,LiberationLegalityValidator liberationValidator,WarLegalityValidator warValidator,PantheonLegalityValidator pantheonValidator,bool liveMissionProfile):host_(host){
        RequireCommandOwner();
        if(host_.localSdkSessionBound || host_.selectLocalUnit || host_.localSelection.IsBound() || host_.localCommands.IsBound())
            throw std::logic_error("A local SDK session is already bound");
        try{
        host_.localSelection.Bind([&game](PlayerTypes owner){
            if(game.GetActivePlayer()!=owner)return false;
            std::unique_ptr<ICvPlayer1> player(game.GetPlayer(owner));
            return player && player->IsHuman() && player->IsAlive() && player->IsTurnActive();
        },[&game](PlayerTypes owner,int unitID)->ICvUnit1*{
            std::unique_ptr<ICvPlayer1> player(game.GetPlayer(owner));
            if(!player)return nullptr;
            std::unique_ptr<ICvUnit1> unit(player->GetUnit(unitID));
            if(unit && (unit->GetOwner()!=owner || unit->GetID()!=unitID || unit->IsDelayedDeathExported()))return nullptr;
            return unit.release();
        });
        host_.selectLocalUnit=[this,&game](int unitID){SelectLocalUnit(game,unitID);};
        LocalGameCommands::CityTaskHandler cityTaskHandler;
        LocalGameCommands::LiberatePlayerHandler liberationHandler;
        LocalGameCommands::PushMissionHandler swapHandler;
        LocalGameCommands::ChangeWarHandler changeWarHandler;
        LocalGameCommands::FromUIDiploEventHandler diploEventHandler;
        LocalGameCommands::FoundPantheonHandler foundPantheonHandler;
        if(liveMissionProfile){
            swapHandler=[this,&receiver,&game,&context](int unitID,MissionTypes mission,int x,int y,int flags,bool shift){
                RequireCommandOwner();
                const int move=context.GetInfoTypeForString("MISSION_MOVE_TO",true),swap=context.GetInfoTypeForString("MISSION_SWAP_UNITS",true);
                if(game.IsGameMultiPlayer() || unitID<0 || flags!=0 || move<0 || swap<0 ||
                   (static_cast<int>(mission)!=move && static_cast<int>(mission)!=swap))
                    throw std::invalid_argument("Local unit swap has an invalid command envelope");
                const auto active=game.GetActivePlayer();
                if(active<0 || active>=MAX_PLAYERS)throw std::logic_error("Local swap has no active player");
                std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
                const auto selected=host_.localSelection.Snapshot();
                if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive() ||
                   selected.size()!=1 || selected.front().first!=active || selected.front().second!=unitID)
                    throw std::logic_error("Local swap requires the active human's selected unit");
                std::unique_ptr<ICvUnit1> unit(player->GetUnit(unitID));std::unique_ptr<ICvMap1> map(context.GetMap());
                if(!unit || unit->GetOwner()!=active || unit->GetID()!=unitID || unit->IsBusy() || unit->IsDelayedDeathExported() ||
                   !map || x<0 || y<0 || x>=map->GetGridWidth() || y>=map->GetGridHeight())
                    throw std::invalid_argument("Local swap target is stale or outside the map");
                std::unique_ptr<ICvPlot1> plot(map->GetPlot(x,y));
                if(!plot || !unit->CanSwapWithUnitHere(plot.get()))throw std::logic_error("SDK rejected the local unit swap");
                plot.reset();map.reset();unit.reset();player.reset();
                receiver.ResponseSwapUnits(active,unitID,mission,x,y,flags,shift);
            };
            cityTaskHandler=[this,&receiver,&game,validator=std::move(cityTaskValidator)](int cityID,TaskTypes task,int data1,int data2,bool option,bool alt,bool shift,bool control){
                RequireCommandOwner();
                if(game.IsGameMultiPlayer())throw std::logic_error("Local city tasks are disabled for multiplayer sessions");
                if(cityID<0)throw std::invalid_argument("Local city task has a negative city ID");
                if(task!=TASK_RAZE && task!=TASK_CREATE_PUPPET && task!=TASK_ANNEX_PUPPET)
                    throw std::invalid_argument("Local city task is outside the supported capture decision tasks");
                if(data1!=-1 || data2!=-1 || option || alt || shift || control)
                    throw std::invalid_argument("Only the unmodified official local city task tuple is supported");
                const PlayerTypes active=game.GetActivePlayer();const int activeID=static_cast<int>(active);
                if(activeID<0 || activeID>=MAX_PLAYERS)throw std::logic_error("Local city task has no valid active player");
                std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
                if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())throw std::logic_error("Local city task requires the active human's live turn");
                std::unique_ptr<ICvCity1> city(player->GetCity(cityID));
                if(!city || city->GetID()!=cityID || city->GetOwner()!=active)throw std::invalid_argument("Local city task target is not owned by the active player");
                if(!validator || !validator(cityID,task,data1,data2,option,alt,shift,control))throw std::logic_error("SDK city task legality validator rejected the local task");
                city.reset();player.reset();
                receiver.ResponseCityDoTask(active,cityID,task,data1,data2,option,alt,shift,control);
            };
            liberationHandler=[this,&receiver,&game,validator=std::move(liberationValidator)](PlayerTypes liberated,int cityID){
                RequireCommandOwner();
                if(game.IsGameMultiPlayer())throw std::logic_error("Local city liberation is disabled for multiplayer sessions");
                const int liberatedID=static_cast<int>(liberated);
                if(cityID<0)throw std::invalid_argument("Local city liberation has a negative city ID");
                if(liberatedID<0 || liberatedID>=MAX_PLAYERS)throw std::invalid_argument("Local city liberation has an invalid player ID");
                const PlayerTypes active=game.GetActivePlayer();const int activeID=static_cast<int>(active);
                if(activeID<0 || activeID>=MAX_PLAYERS)throw std::logic_error("Local city liberation has no valid active player");
                if(liberated==active)throw std::invalid_argument("The active player cannot be the liberation recipient");
                std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
                if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())throw std::logic_error("Local city liberation requires the active human's live turn");
                std::unique_ptr<ICvCity1> city(player->GetCity(cityID));
                if(!city || city->GetID()!=cityID || city->GetOwner()!=active)throw std::invalid_argument("Local city liberation target is not owned by the active player");
                if(!validator || !validator(liberated,cityID))throw std::logic_error("SDK liberation legality validator rejected the local command");
                city.reset();player.reset();
                receiver.ResponseLiberatePlayer(active,liberated,cityID);
            };
            changeWarHandler=[this,&receiver,&game,&context,validator=std::move(warValidator)](TeamTypes rival,bool war){
                RequireCommandOwner();
                if(game.IsGameMultiPlayer())throw std::logic_error("Local war commands are disabled for multiplayer sessions");
                if(!war)throw std::invalid_argument("Local peace toggles are unsupported");
                const int rivalID=static_cast<int>(rival);
                if(rivalID<0 || rivalID>=MAX_TEAMS)throw std::invalid_argument("Local war command has an invalid rival team");
                const PlayerTypes active=game.GetActivePlayer();const int activeID=static_cast<int>(active);
                if(activeID<0 || activeID>=MAX_PLAYERS)throw std::logic_error("Local war command has no valid active player");
                std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
                if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())
                    throw std::logic_error("Local war commands require the active human's live turn");
                const TeamTypes activeTeam=player->GetTeam();
                if(activeTeam<0 || activeTeam>=MAX_TEAMS || rival==activeTeam)
                    throw std::invalid_argument("Local war command cannot target the active player's team");
                std::unique_ptr<ICvTeam1> targetTeam(context.GetTeam(rival));
                std::unique_ptr<ICvTeam1> sourceTeam(context.GetTeam(activeTeam));
                if(!targetTeam || !targetTeam->IsAlive() || targetTeam->IsBarbarian() || !sourceTeam ||
                   sourceTeam->IsAtWar(rival))
                    throw std::invalid_argument("Local war command target is dead, barbarian, or already at war");
                if(!validator || !validator(activeTeam,rival))
                    throw std::logic_error("SDK CanDeclareWar rejected or is unavailable for the local war command");
                sourceTeam.reset();targetTeam.reset();player.reset();
                receiver.ResponseChangeWar(active,rival,true);
            };
            diploEventHandler=[this,&receiver,&game,&context](PlayerTypes other,FromUIDiploEventTypes event,int arg1,int arg2){
                RequireCommandOwner();
                if(game.IsGameMultiPlayer())throw std::logic_error("Local diplomacy events are disabled for multiplayer sessions");
                if(event!=FROM_UI_DIPLO_EVENT_HUMAN_DECLARES_WAR || arg1!=0 || arg2!=0)
                    throw std::invalid_argument("Only the unmodified human-declares-war diplomacy event is supported");
                const int otherID=static_cast<int>(other);
                if(otherID<0 || otherID>=MAX_PLAYERS)throw std::invalid_argument("Local diplomacy event has an invalid target player");
                const PlayerTypes active=game.GetActivePlayer();const int activeID=static_cast<int>(active);
                if(activeID<0 || activeID>=MAX_PLAYERS)throw std::logic_error("Local diplomacy event has no valid active player");
                if(other==active)throw std::invalid_argument("Local diplomacy event cannot target the active player");
                std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
                std::unique_ptr<ICvPlayer1> target(game.GetPlayer(other));
                if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive() ||
                   !target || !target->IsAlive() || target->IsHuman() || target->IsMinorCiv() || target->IsBarbarian())
                    throw std::logic_error("Human-declares-war requires another living AI major on the active human's live turn");
                const TeamTypes activeTeam=player->GetTeam(),targetTeam=target->GetTeam();
                if(activeTeam<0 || activeTeam>=MAX_TEAMS || targetTeam<0 || targetTeam>=MAX_TEAMS || activeTeam==targetTeam)
                    throw std::invalid_argument("Local diplomacy event target is not on another valid team");
                std::unique_ptr<ICvTeam1> source(context.GetTeam(activeTeam));
                if(!source || !source->IsAtWar(targetTeam))
                    throw std::logic_error("Human-declares-war requires the active team to already be at war with the target");
                target.reset();player.reset();source.reset();
                receiver.ResponseDiplomacyFromUI(active,other,event,arg1,arg2);
            };
            foundPantheonHandler=[this,&receiver,&game,validator=std::move(pantheonValidator)](PlayerTypes owner,BeliefTypes belief){
                RequireCommandOwner();
                if(game.IsGameMultiPlayer())throw std::logic_error("Local pantheon founding is disabled for multiplayer sessions");
                if(owner<0 || owner>=MAX_PLAYERS || static_cast<int>(belief)<0)
                    throw std::invalid_argument("Local pantheon founding has an invalid player or belief ID");
                const int turn=game.GetGameTurn();
                const auto requirePlayer=[&game,owner](){
                    if(game.GetActivePlayer()!=owner)throw std::logic_error("Local pantheon founding does not belong to the active player");
                    std::unique_ptr<ICvPlayer1> player(game.GetPlayer(owner));
                    if(!player || player->GetID()!=owner || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())
                        throw std::logic_error("Local pantheon founding requires the active human's live turn");
                    std::unique_ptr<ICvCity1> capital(player->GetCapitalCity());
                    if(!capital || capital->GetOwner()!=owner || capital->GetID()<0)
                        throw std::logic_error("Local pantheon founding requires the active player's real capital");
                };
                requirePlayer();
                if(!validator || !validator(owner,belief))
                    throw std::logic_error("SDK pantheon legality rejected or is unavailable for the local command");
                if(game.GetGameTurn()!=turn)throw std::logic_error("Local pantheon founding changed its observed turn before dispatch");
                requirePlayer();
                std::unique_ptr<ICvNetMessageHandler2> pantheonReceiver(receiver.QueryInterface<ICvNetMessageHandler2>());
                if(!pantheonReceiver)throw std::logic_error("Local pantheon founding requires ICvNetMessageHandler2");
                pantheonReceiver->ResponseFoundPantheon(owner,belief);
                host_.Record("local-found-pantheon:"+std::to_string(static_cast<int>(owner))+":"+std::to_string(static_cast<int>(belief)));
            };
        }
        host_.localCommands.Bind([&receiver,&game](PlayerOptionTypes option,bool enabled){
            receiver.ResponsePlayerOption(game.GetActivePlayer(),option,enabled);
            std::unique_ptr<ICvPlayer1> player(game.GetPlayer(game.GetActivePlayer()));
            if(!player || player->IsOption(option)!=enabled)
                throw std::runtime_error("Local player option did not reach the SDK player state");
        },[&context](PlayerOptionTypes option){
            const int id=context.GetInfoTypeForHash(static_cast<unsigned>(option),true);
            if(id<0)throw std::invalid_argument("Unknown player option hash");
            std::unique_ptr<ICvPlayerOptionInfo1> info(context.GetPlayerOptionInfo(static_cast<PlayerOptionTypes>(id)));
            if(!info)throw std::invalid_argument("Player option hash has no rules entry");
            return info->GetDefault();
        },[this,&receiver,&game,&context](int unitID,CommandTypes command,int data1,int data2,bool alt){
            RequireCommandOwner();
            if(game.IsGameMultiPlayer())
                throw std::logic_error("Local unit commands are disabled for multiplayer sessions");
            if(alt)
                throw std::invalid_argument("Local unit command alt scope is unsupported");
            if(unitID<0)throw std::invalid_argument("Local unit command has a negative unit ID");
            const int commandID=static_cast<int>(command);
            if(commandID<0 || commandID>=static_cast<int>(NUM_COMMAND_TYPES))
                throw std::invalid_argument("Unknown local unit command");
            if(command==COMMAND_PROMOTION && (data1<0 || data1>=context.GetNumPromotionInfos()))
                throw std::invalid_argument("Local promotion command has no rules entry");
            const PlayerTypes active=game.GetActivePlayer();
            const int activeID=static_cast<int>(active);
            if(activeID<0 || activeID>=MAX_PLAYERS)
                throw std::logic_error("Local unit command has no valid active player");
            std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
            if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())
                throw std::logic_error("Local unit command requires the active human's live turn");
            std::unique_ptr<ICvUnit1> unit(player->GetUnit(unitID));
            if(!unit || unit->GetID()!=unitID || unit->GetOwner()!=active)
                throw std::invalid_argument("Local unit command target is not owned by the active player");
            if(unit->IsDelayedDeathExported())
                throw std::logic_error("Local unit command target is pending destruction");
            if(unit->IsBusy())
                throw std::logic_error("Local unit command target is busy");
            receiver.ResponseDoCommand(active,unitID,command,data1,data2,alt);
        },[this,&receiver,&game,&context,missionValidator=std::move(missionValidator),liveMissionProfile](int unitID,MissionTypes mission,int data1,int data2,int flags,bool shift){
            RequireCommandOwner();
            if(game.IsGameMultiPlayer())
                throw std::logic_error("Local push missions are disabled for multiplayer sessions");
            const int foundMissionID=context.GetInfoTypeForString("MISSION_FOUND",true);
            if(foundMissionID<0)throw std::logic_error("SDK has no MISSION_FOUND rules entry");
            const MissionTypes foundMission=static_cast<MissionTypes>(foundMissionID);
            const int moveMissionID=liveMissionProfile?context.GetInfoTypeForString("MISSION_MOVE_TO",true):-1;
            const int rangeAttackMissionID=liveMissionProfile?context.GetInfoTypeForString("MISSION_RANGE_ATTACK",true):-1;
            const int skipMissionID=liveMissionProfile?context.GetInfoTypeForString("MISSION_SKIP",true):-1;
            const int buildMissionID=liveMissionProfile?context.GetInfoTypeForString("MISSION_BUILD",true):-1;
            const int fortifyMissionID=liveMissionProfile?context.GetInfoTypeForString("MISSION_FORTIFY",true):-1;
            const int healMissionID=liveMissionProfile?context.GetInfoTypeForString("MISSION_HEAL",true):-1;
            const int sleepMissionID=liveMissionProfile?context.GetInfoTypeForString("MISSION_SLEEP",true):-1;
            const int alertMissionID=liveMissionProfile?context.GetInfoTypeForString("MISSION_ALERT",true):-1;
            const int pillageMissionID=liveMissionProfile?context.GetInfoTypeForString("MISSION_PILLAGE",true):-1;
            const MissionTypes moveMission=static_cast<MissionTypes>(moveMissionID);
            const MissionTypes rangeAttackMission=static_cast<MissionTypes>(rangeAttackMissionID);
            const MissionTypes skipMission=static_cast<MissionTypes>(skipMissionID);
            const MissionTypes buildMission=static_cast<MissionTypes>(buildMissionID);
            const MissionTypes fortifyMission=static_cast<MissionTypes>(fortifyMissionID);
            const MissionTypes healMission=static_cast<MissionTypes>(healMissionID);
            const MissionTypes sleepMission=static_cast<MissionTypes>(sleepMissionID);
            const MissionTypes alertMission=static_cast<MissionTypes>(alertMissionID);
            const MissionTypes pillageMission=static_cast<MissionTypes>(pillageMissionID);
            auto requireMissionInfo=[&context](MissionTypes type,const char* expected){
                std::unique_ptr<ICvMissionInfo1> info(context.GetMissionInfo(type));
                if(!info || !info->GetType() || std::string(info->GetType())!=expected)
                    throw std::logic_error(std::string("SDK ")+expected+" rules entry is inconsistent");
            };
            requireMissionInfo(foundMission,"MISSION_FOUND");
            const bool isFound=mission==foundMission;
            const bool isMove=liveMissionProfile && moveMissionID>=0 && mission==moveMission;
            const bool isRangeAttack=liveMissionProfile && rangeAttackMissionID>=0 && mission==rangeAttackMission;
            const bool isSkip=liveMissionProfile && skipMissionID>=0 && mission==skipMission;
            const bool isBuild=liveMissionProfile && buildMissionID>=0 && mission==buildMission;
            const bool isFortify=liveMissionProfile && fortifyMissionID>=0 && mission==fortifyMission;
            const bool isHeal=liveMissionProfile && healMissionID>=0 && mission==healMission;
            const bool isSleep=liveMissionProfile && sleepMissionID>=0 && mission==sleepMission;
            const bool isAlert=liveMissionProfile && alertMissionID>=0 && mission==alertMission;
            const bool isPillage=liveMissionProfile && pillageMissionID>=0 && mission==pillageMission;
            if(isMove)requireMissionInfo(moveMission,"MISSION_MOVE_TO");
            if(isRangeAttack)requireMissionInfo(rangeAttackMission,"MISSION_RANGE_ATTACK");
            if(isSkip)requireMissionInfo(skipMission,"MISSION_SKIP");
            if(isBuild)requireMissionInfo(buildMission,"MISSION_BUILD");
            if(isFortify)requireMissionInfo(fortifyMission,"MISSION_FORTIFY");
            if(isHeal)requireMissionInfo(healMission,"MISSION_HEAL");
            if(isSleep)requireMissionInfo(sleepMission,"MISSION_SLEEP");
            if(isAlert)requireMissionInfo(alertMission,"MISSION_ALERT");
            if(isPillage)requireMissionInfo(pillageMission,"MISSION_PILLAGE");
            if(isFound){
                if(data1!=-1 || data2!=-1 || flags!=0 || shift)
                    throw std::invalid_argument("Only the unmodified local founding mission is supported");
            }else if(isMove){
                if(flags!=0 && flags!=LiveAttackPathFlags)
                    throw std::invalid_argument("Local move mission has unsupported path flags");
            }else if(isRangeAttack){
                if(flags!=0)
                    throw std::invalid_argument("Local ranged attack has unsupported path flags");
            }else if(isSkip){
                if(data1!=-1 || data2!=-1 || flags!=0 || shift)
                    throw std::invalid_argument("Only the unmodified local skip mission is supported");
            }else if(isBuild){
                if(data2!=-1 || flags!=0 || shift)
                    throw std::invalid_argument("Only the unmodified local build mission tuple is supported");
                const int count=context.GetNumBuildInfos();
                if(data1<0 || count<=0 || data1>=count)
                    throw std::invalid_argument("Local build mission has an out-of-range BuildTypes ID");
                std::unique_ptr<ICvBuildInfo1> info(context.GetBuildInfo(static_cast<BuildTypes>(data1)));
                const char* type=info?info->GetType():nullptr;
                if(!type || !*type || context.GetInfoTypeForString(type,true)!=data1)
                    throw std::invalid_argument("Local build mission BuildTypes ID does not resolve to its SDK GameInfo row");
            }else if(isFortify || isHeal || isSleep || isAlert || isPillage){
                if(data1!=-1 || data2!=-1 || flags!=0 || shift)
                    throw std::invalid_argument("Only the unmodified local unit stance/action mission tuple is supported");
            }else{
                throw std::invalid_argument("Mission is outside the bound local mission profile");
            }
            if(unitID<0)throw std::invalid_argument("Local mission has a negative unit ID");
            const PlayerTypes active=game.GetActivePlayer();
            const int activeID=static_cast<int>(active);
            if(activeID<0 || activeID>=MAX_PLAYERS)
                throw std::logic_error("Local mission has no valid active player");
            std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
            if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())
                throw std::logic_error("Local mission requires the active human's live turn");
            const auto selected=host_.localSelection.Snapshot();
            if(selected.size()!=1 || selected.front().first!=active || selected.front().second!=unitID)
                throw std::logic_error("Local mission requires exactly its target as the selected unit");
            std::unique_ptr<ICvUnit1> unit(player->GetUnit(unitID));
            if(!unit || unit->GetID()!=unitID || unit->GetOwner()!=active)
                throw std::invalid_argument("Local mission target is not owned by the active player");
            if(unit->IsDelayedDeathExported())
                throw std::logic_error("Local mission target is pending destruction");
            if(unit->IsBusy())
                throw std::logic_error("Local mission target is busy");
            if(isMove || isRangeAttack){
                std::unique_ptr<ICvMap1> map(context.GetMap());
                if(!map)throw std::logic_error("Local attack mission has no SDK map");
                const int width=map->GetGridWidth(),height=map->GetGridHeight();
                if(data1<0 || data2<0 || data1>=width || data2>=height)
                    throw std::invalid_argument("Local attack mission coordinates are outside the SDK map");
                std::unique_ptr<ICvPlot1> plot(map->GetPlot(data1,data2));
                int plotX=-1,plotY=-1;if(plot)plot->GetPosition(plotX,plotY);
                if(!plot || plotX!=data1 || plotY!=data2)
                    throw std::invalid_argument("Local attack mission coordinates do not resolve to the requested SDK plot");
            }
            const bool requiresAttackMoves=isRangeAttack || (isMove && flags==LiveAttackPathFlags);
            if(requiresAttackMoves && unit->MovesLeft()<=0)
                throw std::logic_error("Local attack mission requires remaining movement points");
            if(!isFound && (!missionValidator || !missionValidator(unitID,mission,data1,data2,flags)))
                throw std::logic_error("SDK CanStartMission rejected the local mission");
            receiver.ResponsePushMission(active,unitID,mission,data1,data2,flags,shift);
        },[this,&receiver,&game,&context](int cityID,OrderTypes order,int data,bool alt,bool shift,bool control){
            RequireCommandOwner();
            if(game.IsGameMultiPlayer())throw std::logic_error("Local city orders are disabled for multiplayer sessions");
            LocalGameCommands::ValidateCityOrderEnvelope(cityID,order,data,alt,shift,control);
            if(order==ORDER_TRAIN){
                if(data>=context.GetNumUnitInfos())throw std::invalid_argument("Local training order has an invalid unit ID");
                std::unique_ptr<ICvUnitInfo1> info(context.GetUnitInfo(static_cast<UnitTypes>(data)));
                if(!info)throw std::invalid_argument("Local training order unit has no rules entry");
            }else if(order==ORDER_CONSTRUCT){
                if(data>=context.GetNumBuildingInfos())throw std::invalid_argument("Local construction order has an invalid building ID");
                std::unique_ptr<ICvBuildingInfo1> info(context.GetBuildingInfo(static_cast<BuildingTypes>(data)));
                if(!info)throw std::invalid_argument("Local construction order building has no rules entry");
            }else if(order==ORDER_CREATE){
                if(!host_.cityItemRulesReady)throw std::logic_error("Local project orders require the prepared city item rules index");
                if(!host_.validCityProjectTypes.count(data))throw std::invalid_argument("Local project order has no rules entry");
            }else{
                if(!host_.cityItemRulesReady)throw std::logic_error("Local process orders require the prepared city item rules index");
                if(!host_.validCityProcessTypes.count(data))throw std::invalid_argument("Local process order has no rules entry");
            }
            const PlayerTypes active=game.GetActivePlayer();const int activeID=static_cast<int>(active);
            if(activeID<0 || activeID>=MAX_PLAYERS)throw std::logic_error("Local training order has no valid active player");
            std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
            if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())throw std::logic_error("Local training order requires the active human's live turn");
            std::unique_ptr<ICvCity1> city(player->GetCity(cityID));
            if(!city || city->GetID()!=cityID || city->GetOwner()!=active)throw std::invalid_argument("Local city order target is not owned by the active player");
            // Civ V ProductionPopup sends (alt=false, shift=!Option1, control=true).
            // ResponseCityPushOrder performs the SDK's live CanTrain/CanConstruct/
            // CanCreate/CanMaintain checks while applying the actual order.
            receiver.ResponseCityPushOrder(active,cityID,order,data,alt,shift,control);
        },[this,&receiver,&game,&context](TechTypes tech,int discover,PlayerTypes stealFrom,bool shift){
            RequireCommandOwner();
            if(game.IsGameMultiPlayer())throw std::logic_error("Local research is disabled for multiplayer sessions");
            if(discover!=0 || stealFrom!=NO_PLAYER || shift)throw std::invalid_argument("Only normal local research selection is supported");
            const int techID=static_cast<int>(tech);
            if(techID<0 || techID>=context.GetNumTechInfos())throw std::invalid_argument("Local research selection has invalid technology");
            std::unique_ptr<ICvTechInfo1> info(context.GetTechInfo(tech));
            if(!info)throw std::invalid_argument("Local research technology has no rules entry");
            const PlayerTypes active=game.GetActivePlayer();const int activeID=static_cast<int>(active);
            if(activeID<0 || activeID>=MAX_PLAYERS)throw std::logic_error("Local research has no valid active player");
            std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
            if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())throw std::logic_error("Local research requires the active human's live turn");
            receiver.ResponseResearch(active,tech,discover,shift);
        },[this,&receiver,&game,&context](int cityID,UnitTypes unit,BuildingTypes building,ProjectTypes project,int purchaseYield){
            RequireCommandOwner();
            if(game.IsGameMultiPlayer())throw std::logic_error("Local city purchases are disabled for multiplayer sessions");
            LocalGameCommands::ValidateCityPurchaseEnvelope(cityID,unit,building,project,purchaseYield);
            const bool hasUnit=unit!=NO_UNIT,hasBuilding=building!=NO_BUILDING;
            if(hasUnit){
                const int id=static_cast<int>(unit);if(id<0 || id>=context.GetNumUnitInfos())throw std::invalid_argument("Local city purchase has an invalid unit ID");
                std::unique_ptr<ICvUnitInfo1> info(context.GetUnitInfo(unit));if(!info)throw std::invalid_argument("Local city purchase unit has no rules entry");
            }else if(hasBuilding){
                const int id=static_cast<int>(building);if(id<0 || id>=context.GetNumBuildingInfos())throw std::invalid_argument("Local city purchase has an invalid building ID");
                std::unique_ptr<ICvBuildingInfo1> info(context.GetBuildingInfo(building));if(!info)throw std::invalid_argument("Local city purchase building has no rules entry");
            }else if(static_cast<int>(project)<0){
                throw std::invalid_argument("Local city purchase has an invalid project ID");
            }else{
                if(!host_.cityItemRulesReady)throw std::logic_error("Local project purchases require the prepared city item rules index");
                if(!host_.validCityProjectTypes.count(static_cast<int>(project)))throw std::invalid_argument("Local city purchase project has no rules entry");
            }
            const PlayerTypes active=game.GetActivePlayer();const int activeID=static_cast<int>(active);
            if(activeID<0 || activeID>=MAX_PLAYERS)throw std::logic_error("Local city purchase has no valid active player");
            std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
            if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())throw std::logic_error("Local city purchase requires the active human's live turn");
            std::unique_ptr<ICvCity1> city(player->GetCity(cityID));
            if(!city || city->GetID()!=cityID || city->GetOwner()!=active)throw std::invalid_argument("Local city purchase target is not owned by the active player");
            ICvNetMessageHandler2* purchaseReceiver=receiver.QueryInterface<ICvNetMessageHandler2>();
            if(!purchaseReceiver)throw std::logic_error("The SDK receiver does not expose purchase-yield support (ICvNetMessageHandler2)");
            // The SDK receiver forwards the exact yield to CvCity::Purchase,
            // whose IsCanPurchase rules check is authoritative and mutating.
            purchaseReceiver->ResponseCityPurchase(active,cityID,unit,building,project,purchaseYield);
        },std::move(cityTaskHandler),std::move(liberationHandler),std::move(swapHandler),std::move(changeWarHandler),std::move(diploEventHandler),std::move(foundPantheonHandler));
        host_.turnSignals.Bind([&game](){return game.GetGameTurn();},game.GetActivePlayer());
        host_.localSdkSessionBound=true;
        }catch(...){
            host_.selectLocalUnit={};host_.localSelection.Unbind();host_.turnSignals.Unbind();host_.localCommands.Unbind();throw;
        }
    }
public:
    ~LocalSdkSession(){host_.selectLocalUnit={};host_.localSelection.Unbind();host_.turnSignals.Unbind();host_.localCommands.Unbind();host_.localSdkSessionBound=false;}
    LocalSdkSession(const LocalSdkSession&)=delete;
    LocalSdkSession& operator=(const LocalSdkSession&)=delete;
private:
    void SelectLocalUnit(ICvGame1& game,int unitID){
        RequireCommandOwner();
        if(game.IsGameMultiPlayer())throw std::logic_error("Local unit selection is disabled for multiplayer sessions");
        if(unitID<0)throw std::invalid_argument("Local unit selection has a negative unit ID");
        const PlayerTypes active=game.GetActivePlayer();const int activeID=static_cast<int>(active);
        if(activeID<0 || activeID>=MAX_PLAYERS)throw std::logic_error("Local unit selection has no valid active player");
        std::unique_ptr<ICvPlayer1> player(game.GetPlayer(active));
        if(!player || !player->IsHuman() || !player->IsAlive() || !player->IsTurnActive())
            throw std::logic_error("Local unit selection requires the active human's live turn");
        std::unique_ptr<ICvUnit1> unit(player->GetUnit(unitID));
        if(!unit || unit->GetID()!=unitID || unit->GetOwner()!=active)
            throw std::invalid_argument("Local unit selection target is not owned by the active player");
        if(unit->IsDelayedDeathExported())throw std::logic_error("Local unit selection target is pending destruction");
        if(unit->IsBusy())throw std::logic_error("Local unit selection target is busy");
        game.SelectUnit(unit.get(),true,false,false);
    }
    void RequireCommandOwner() const {
        LocalGameCommands::RequireOwnerLock(host_.gameThread==GetCurrentThreadId(),host_.gameLock.HeldByCurrentThread());
    }
    HostState& host_;
};
}
