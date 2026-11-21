#pragma once

#include "HostServices.h"
#include <CvLocalization.h>
#include <algorithm>
#include <cstdint>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace ZeroSisHost {

// A detached, owner-thread snapshot for strategic-view presentation. It owns
// only scalar values and strings; no SDK adapter escapes Capture().
struct WorldViewState final {
    struct Plot final {
        int index=-1, x=-1, y=-1;
        bool revealed=false, visible=false;
        int plotKind=-1;
        bool hills=false, mountain=false, water=false;
        std::string terrainType, featureType;
        int improvementType=-1, routeType=-1;
        bool improvementPillaged=false, routePillaged=false;
        std::string improvementName, routeName;
        int continent=-1;
        int terrainId=-1;
        bool naturalWonder=false;
        bool lake=false; // Not exposed by the unchanged public SDK interface.
        bool riverW=false,riverNW=false,riverNE=false;
        int flowE=-1,flowSE=-1,flowSW=-1;
    };
    struct Unit final {
        int owner=-1, id=-1, plotIndex=-1, x=-1, y=-1;
        int unitType=-1, moves=0, damage=0;
        std::string type, name;
        std::string unitArtInfoTag, artStylePrefix, artStyleSuffix, eraArtPrefix;
        int civilizationType=-1, artStyleType=-1, ownerEra=-1, facingDirection=NO_DIRECTION;
        bool unitArtInfoCulturalVariation=false, unitArtInfoEraVariation=false, embarked=false;
        bool selected=false;
        int maxHitPoints=100;
        bool hostile=false;
    };
    struct City final {
        int owner=-1, id=-1, plotIndex=-1, x=-1, y=-1;
        std::string rawName;
        std::string name;
    };

    int turn=-1, elapsedTurns=-1, activePlayer=-1, activeTeam=-1;
    int gridWidth=0, gridHeight=0;
    bool wrapX=false, wrapY=false;
    std::uint32_t mapRandomSeed=0;
    std::vector<Plot> plots;
    std::vector<Unit> ownedUnits;
    std::vector<Unit> visibleForeignUnits;
    std::vector<City> visibleCities;
    std::vector<std::pair<int,int>> selectedUnits;

    static std::string CopyUnitText(const char* text,const char* field) {
        if(!text)return {};
        const std::string value(text);
        if(value.size()>256)throw std::runtime_error(std::string("World view ")+field+" exceeds its bound");
        return value;
    }

    // Capture only detached identity and art-selection inputs. SDK interfaces
    // stay inside Capture() on the GameCore owner thread and under its lock.
    static void CaptureUnitVisual(ICvGameContext3& context,ICvGame1& game,ICvUnit1& source,ICvUnitInfo1& info,Unit& value) {
        if(static_cast<int>(source.GetOwner())!=value.owner)
            throw std::runtime_error("World view unit visual owner differs from its captured identity");
        value.unitType=static_cast<int>(source.GetUnitType());
        if(value.unitType<0 || value.unitType>=context.GetNumUnitInfos())
            throw std::runtime_error("World view unit type is outside the SDK info table");
        value.type=CopyUnitText(info.GetType(),"unit type");
        value.unitArtInfoTag=CopyUnitText(info.GetUnitArtInfoTag(),"unit art-info tag");
        value.unitArtInfoCulturalVariation=info.GetUnitArtInfoCulturalVariation();
        value.unitArtInfoEraVariation=info.GetUnitArtInfoEraVariation();

        value.civilizationType=static_cast<int>(source.GetCivilizationType());
        if(value.civilizationType<0 || value.civilizationType>=context.GetNumCivilizationInfos())
            throw std::runtime_error("World view unit civilization is outside the SDK info table");
        std::unique_ptr<ICvCivilizationInfo1> civilization(
            context.GetCivilizationInfo(static_cast<CivilizationTypes>(value.civilizationType)));
        if(!civilization)throw std::runtime_error("World view unit civilization art info is unavailable");
        value.artStyleType=static_cast<int>(civilization->GetArtStyleType());
        value.artStylePrefix=CopyUnitText(civilization->GetArtStylePrefix(),"civilization art prefix");
        value.artStyleSuffix=CopyUnitText(civilization->GetArtStyleSuffix(),"civilization art suffix");

        std::unique_ptr<ICvPlayer1> owner(game.GetPlayer(static_cast<PlayerTypes>(value.owner)));
        if(!owner || static_cast<int>(owner->GetID())!=value.owner)
            throw std::runtime_error("World view unit owner art context is unavailable");
        value.ownerEra=static_cast<int>(owner->GetCurrentEra());
        if(value.ownerEra<0 || value.ownerEra>=context.GetNumEraInfos())
            throw std::runtime_error("World view unit owner era is outside the SDK info table");
        std::unique_ptr<ICvEraInfo1> era(context.GetEraInfo(static_cast<EraTypes>(value.ownerEra)));
        if(!era)throw std::runtime_error("World view unit era art info is unavailable");
        value.eraArtPrefix=CopyUnitText(era->GetArtPrefix(),"era art prefix");

        // The SDK implementation returns NO_DIRECTION when the legacy LOS
        // filter is requested; false returns the unit's stored facing value.
        value.facingDirection=static_cast<int>(source.GetFacingDirection(false));
        if(value.facingDirection<NO_DIRECTION || value.facingDirection>=NUM_DIRECTION_TYPES)
            throw std::runtime_error("World view unit facing is outside the SDK direction range");
        value.embarked=source.IsEmbarked();
    }

    static WorldViewState Capture(ICvGameContext3& context, HostState& host) {
        if(GetCurrentThreadId()!=host.gameThread || !host.gameLock.HeldByCurrentThread())
            throw std::logic_error("World view capture requires the GameCore owner thread and lock");

        constexpr int kMaximumPlots=1'000'000;
        constexpr int kMaximumUnits=100'000;
        WorldViewState result;
        std::unique_ptr<ICvGame1> game(context.GetGame());
        std::unique_ptr<ICvMap1> map(context.GetMap());
        if(!game || !map) throw std::runtime_error("World view requires live Game and Map adapters");
        std::unique_ptr<ICvPreGame1> pregame(context.GetPreGame());
        if(!pregame)throw std::runtime_error("World view terrain requires the pregame seed interface");
        result.mapRandomSeed=pregame->mapRandomSeed();

        result.turn=game->GetGameTurn();
        result.elapsedTurns=game->GetElapsedGameTurns();
        result.activePlayer=static_cast<int>(game->GetActivePlayer());
        result.activeTeam=static_cast<int>(game->GetActiveTeam());
        result.gridWidth=map->GetGridWidth();
        result.gridHeight=map->GetGridHeight();
        result.wrapX=map->IsWrapX();
        result.wrapY=map->IsWrapY();
        const int plotCount=map->NumPlots();
        const auto expected=static_cast<long long>(result.gridWidth)*result.gridHeight;
        if(result.turn<0 || result.elapsedTurns<0 || result.activePlayer<0 || result.activePlayer>=MAX_PLAYERS ||
           result.activeTeam<0 || result.gridWidth<=0 || result.gridHeight<=0 || plotCount<=0 ||
           plotCount>kMaximumPlots || expected!=plotCount)
            throw std::runtime_error("World view received invalid game or map dimensions/state");

        std::unique_ptr<ICvPlayer1> active(game->GetPlayer(static_cast<PlayerTypes>(result.activePlayer)));
        if(!active || active->GetID()!=static_cast<PlayerTypes>(result.activePlayer) ||
           active->GetTeam()!=static_cast<TeamTypes>(result.activeTeam) || !active->IsAlive())
            throw std::runtime_error("World view active player/team identity is invalid");
        std::unique_ptr<ICvTeam1> activeTeam(context.GetTeam(static_cast<TeamTypes>(result.activeTeam)));
        if(!activeTeam || !activeTeam->IsAlive())
            throw std::runtime_error("World view active team adapter is invalid");

        result.plots.resize(static_cast<std::size_t>(plotCount));
        std::vector<bool> seen(static_cast<std::size_t>(plotCount),false);
        std::set<std::pair<int,int>> seenForeignUnits;
        std::size_t visibleUnitCount=0;
        for(int slot=0;slot<plotCount;++slot) {
            std::unique_ptr<ICvPlot1> plot(map->GetPlotByIndex(slot));
            if(!plot) throw std::runtime_error("World view map contains a missing plot adapter");
            int x=-1,y=-1;
            plot->GetPosition(x,y);
            const int index=plot->GetPlotIndex();
            if(index<0 || index>=plotCount || seen[static_cast<std::size_t>(index)] ||
               x<0 || x>=result.gridWidth || y<0 || y>=result.gridHeight || map->PlotNum(x,y)!=index)
                throw std::runtime_error("World view plot identity/coordinates are inconsistent");
            seen[static_cast<std::size_t>(index)]=true;

            Plot value;
            value.index=index; value.x=x; value.y=y;
            value.revealed=plot->IsRevealed(static_cast<TeamTypes>(result.activeTeam),false);
            value.visible=value.revealed && plot->IsVisible(static_cast<TeamTypes>(result.activeTeam),false);
            if(value.revealed) {
                value.continent=static_cast<unsigned char>(plot->GetContinentType());
                if(value.continent>4)throw std::runtime_error("Revealed plot has an unsupported terrain art continent");
                value.plotKind=static_cast<int>(plot->GetPlotType());
                value.hills=plot->IsHills();
                value.mountain=plot->IsMountain();
                value.water=plot->IsWater();
                value.riverW=plot->IsWOfRiver();value.riverNW=plot->IsNWOfRiver();value.riverNE=plot->IsNEOfRiver();
                if(value.riverW)value.flowE=static_cast<int>(plot->GetRiverEFlowDirection());
                if(value.riverNW)value.flowSE=static_cast<int>(plot->GetRiverSEFlowDirection());
                if(value.riverNE)value.flowSW=static_cast<int>(plot->GetRiverSWFlowDirection());
                if((value.flowE!=-1&&value.flowE!=0&&value.flowE!=3)||
                   (value.flowSE!=-1&&value.flowSE!=1&&value.flowSE!=4)||
                   (value.flowSW!=-1&&value.flowSW!=2&&value.flowSW!=5))
                    throw std::runtime_error("Revealed river edge has an inconsistent SDK flow direction");
                const auto terrainId=plot->GetTerrainType();
                value.terrainId=static_cast<int>(terrainId);
                if(terrainId>=0) {
                    std::unique_ptr<ICvTerrainInfo1> terrain(context.GetTerrainInfo(terrainId));
                    if(!terrain) throw std::runtime_error("Revealed plot terrain info is unavailable");
                    if(const char* type=terrain->GetType()) value.terrainType=type;
                }
                const auto featureId=plot->GetFeatureType();
                if(featureId>=0) {
                    std::unique_ptr<ICvFeatureInfo1> feature(context.GetFeatureInfo(featureId));
                    if(!feature) throw std::runtime_error("Revealed plot feature info is unavailable");
                    if(const char* type=feature->GetType()) value.featureType=type;
                    value.naturalWonder=feature->IsNaturalWonder();
                }
                // Current occupants and city ownership/name are intentionally
                // read only while currently visible, never from stale fog data.
                if(value.visible) {
                    const auto improvementId=plot->GetImprovementType();
                    if(improvementId>=0) {
                        std::unique_ptr<ICvImprovementInfo1> improvement(context.GetImprovementInfo(improvementId));
                        if(!improvement || !improvement->GetType() || !*improvement->GetType() ||
                           !improvement->GetText() || !*improvement->GetText())
                            throw std::runtime_error("Visible improvement lacks its actual SDK rule or localized name");
                        value.improvementType=static_cast<int>(improvementId);
                        value.improvementName=improvement->GetText();
                        value.improvementPillaged=plot->IsImprovementPillaged();
                    }
                    const auto routeId=plot->GetRouteType();
                    if(routeId>=0) {
                        const char* routeTextKey=nullptr;
                        if(routeId==ROUTE_ROAD)routeTextKey="TXT_KEY_ROUTE_ROAD";
                        else if(routeId==ROUTE_RAILROAD)routeTextKey="TXT_KEY_ROUTE_RAILROAD";
                        else throw std::runtime_error("Visible route type has no public SDK name adapter");
                        auto localized=Localization::Lookup(routeTextKey);
                        const char* routeText=localized.toUTF8();
                        if(!routeText || !*routeText || std::strcmp(routeText,routeTextKey)==0)
                            throw std::runtime_error("Visible route lacks its original localized name");
                        value.routeType=static_cast<int>(routeId);
                        value.routeName=routeText;
                        value.routePillaged=plot->IsRoutePillaged();
                    }
                    std::unique_ptr<ICvCity1> city(plot->GetPlotCity());
                    if(city) {
                        City cityValue;
                        cityValue.owner=static_cast<int>(city->GetOwner());
                        cityValue.id=city->GetID();
                        cityValue.plotIndex=index; cityValue.x=x; cityValue.y=y;
                        if(cityValue.owner<0 || cityValue.owner>=MAX_PLAYERS || cityValue.id<0 ||
                           city->GetX()!=x || city->GetY()!=y)
                            throw std::runtime_error("Visible city identity does not match its plot");
                        if(const char* name=city->GetName()) {
                            cityValue.rawName=name;
                            cityValue.name=cityValue.rawName;
                            // Built-in city names are localization keys loaded
                            // from the rules DB. Custom names remain verbatim.
                            if(host.builtInCityNames.count(cityValue.rawName)==1) {
                                auto localized=Localization::Lookup(cityValue.rawName.c_str());
                                const char* text=localized.toUTF8();
                                if(text && *text) cityValue.name=text;
                            }
                        }
                        result.visibleCities.push_back(std::move(cityValue));
                    }
                    const int unitsOnPlot=plot->GetNumUnits();
                    if(unitsOnPlot<0 || unitsOnPlot>kMaximumUnits)
                        throw std::runtime_error("Visible plot unit count exceeds the world-view safety bound");
                    for(int unitIndex=0;unitIndex<unitsOnPlot;++unitIndex) {
                        std::unique_ptr<ICvUnit1> occupant(plot->GetUnitByIndex(unitIndex));
                        if(!occupant)throw std::runtime_error("Visible plot contains a missing unit adapter");
                        if(++visibleUnitCount>static_cast<std::size_t>(kMaximumUnits))
                            throw std::runtime_error("Visible unit count exceeds the safety bound");
                        const auto owner=occupant->GetOwner();
                        const int id=occupant->GetID();
                        if(owner==static_cast<PlayerTypes>(result.activePlayer))continue;
                        const int ownerId=static_cast<int>(owner);
                        if(ownerId<0 || ownerId>=MAX_PLAYERS || id<0)
                            throw std::runtime_error("Visible foreign unit owner/id is invalid");
                        if(occupant->IsInvisible(static_cast<TeamTypes>(result.activeTeam),false) ||
                           occupant->IsDelayedDeathExported())continue;
                        if(!seenForeignUnits.emplace(ownerId,id).second)
                            throw std::runtime_error("Visible foreign unit owner/id is duplicated across plots");

                        std::unique_ptr<ICvPlot1> occupantPlot(occupant->GetPlot());
                        if(!occupantPlot)throw std::runtime_error("Visible foreign unit has no current plot adapter");
                        int unitX=-1,unitY=-1,unitPlotX=-1,unitPlotY=-1;
                        occupant->GetPosition(unitX,unitY);
                        occupantPlot->GetPosition(unitPlotX,unitPlotY);
                        const int unitPlotIndex=occupantPlot->GetPlotIndex();
                        if(unitPlotIndex!=index || unitPlotIndex<0 || unitPlotIndex>=plotCount ||
                           unitX!=x || unitY!=y || occupant->GetX()!=x || occupant->GetY()!=y ||
                           unitPlotX!=x || unitPlotY!=y || map->PlotNum(unitX,unitY)!=index)
                            throw std::runtime_error("Visible foreign unit plot identity/coordinates are inconsistent");

                        const int maxHitPoints=occupant->GetMaxHitPoints();
                        const int damage=occupant->GetDamage();
                        if(maxHitPoints<=0 || damage<0 || damage>maxHitPoints)
                            throw std::runtime_error("Visible foreign unit health state is invalid");
                        const auto unitTeam=occupant->GetTeam();
                        const int unitTeamId=static_cast<int>(unitTeam);
                        if(unitTeamId<0 || unitTeamId>=MAX_TEAMS)
                            throw std::runtime_error("Visible foreign unit team identity is invalid");

                        Unit foreign;
                        foreign.owner=ownerId;foreign.id=id;foreign.plotIndex=index;foreign.x=x;foreign.y=y;
                        foreign.damage=damage;foreign.maxHitPoints=maxHitPoints;
                        foreign.hostile=activeTeam->IsAtWar(unitTeam);
                        // Non-owned units are informational only; do not query move
                        // availability, selection, or any command-facing state.
                        foreign.moves=0;
                        std::unique_ptr<ICvUnitInfo1> info(occupant->GetUnitInfo());
                        if(!info)throw std::runtime_error("Visible foreign unit has no unit-info adapter");
                        CaptureUnitVisual(context,*game,*occupant,*info,foreign);
                        const CvString name=occupant->GetName();
                        foreign.name=name.c_str();
                        result.visibleForeignUnits.push_back(std::move(foreign));
                    }
                }
            }
            result.plots[static_cast<std::size_t>(index)]=std::move(value);
        }

        for(const auto& selected:host.localSelection.Snapshot())
            result.selectedUnits.emplace_back(static_cast<int>(selected.first),selected.second);
        int iterator=0;
        std::unique_ptr<ICvUnit1> unit(active->FirstUnit(&iterator));
        while(unit) {
            if(result.ownedUnits.size()>=static_cast<std::size_t>(kMaximumUnits))
                throw std::runtime_error("World view owned-unit count exceeds the safety cap");
            const int id=unit->GetID();
            const auto owner=unit->GetOwner();
            if(id<0 || owner!=static_cast<PlayerTypes>(result.activePlayer) || unit->IsDelayedDeathExported())
                throw std::runtime_error("World view encountered a stale or non-owned unit in active-player iteration");
            std::unique_ptr<ICvPlot1> unitPlot(unit->GetPlot());
            if(!unitPlot) throw std::runtime_error("Active-owned unit has no current plot");
            int x=-1,y=-1;
            unitPlot->GetPosition(x,y);
            const int index=unitPlot->GetPlotIndex();
            if(x<0 || x>=result.gridWidth || y<0 || y>=result.gridHeight || index<0 || index>=plotCount ||
               map->PlotNum(x,y)!=index)
                throw std::runtime_error("Active-owned unit is not on a validated map plot");
            // Trade visual units do not grant sight and may cross hidden
            // plots. Keep the owner's real roster/selection intact; map art
            // and hit targets remain restricted by the plot visibility mask.

            Unit value;
            value.owner=static_cast<int>(owner); value.id=id; value.plotIndex=index; value.x=x; value.y=y;
            value.moves=unit->MovesLeft(); value.damage=unit->GetDamage();
            value.maxHitPoints=unit->GetMaxHitPoints();
            value.selected=std::find(result.selectedUnits.begin(),result.selectedUnits.end(),
                std::make_pair(value.owner,value.id))!=result.selectedUnits.end();
            std::unique_ptr<ICvUnitInfo1> info(unit->GetUnitInfo());
            if(!info) throw std::runtime_error("Active-owned unit has no unit-info adapter");
            CaptureUnitVisual(context,*game,*unit,*info,value);
            const CvString name=unit->GetName();
            value.name=name.c_str();
            result.ownedUnits.push_back(std::move(value));
            unit.reset(active->NextUnit(&iterator));
        }

        for(const auto& selected:result.selectedUnits) {
            if(selected.first!=result.activePlayer || selected.second<0)
                throw std::runtime_error("Local selection contains a non-active-player identity");
            const auto found=std::find_if(result.ownedUnits.begin(),result.ownedUnits.end(),[&](const Unit& value){
                return value.owner==selected.first && value.id==selected.second;
            });
            if(found==result.ownedUnits.end())
                throw std::runtime_error("Local selection refers to a unit absent from the captured active-player roster");
        }
        return result;
    }
};

} // namespace ZeroSisHost
