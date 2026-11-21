#pragma once
#include "SdkHostIncludes.h"
#include <map>
#include <sstream>
#include <stdexcept>
#include <vector>

namespace ZeroSisHost {
// Owned presentation state, used only with the Host's GameCore owner lock.
// The SDK owns route simulation/save data. Its callbacks reconstruct this
// state on load; no borrowed arrays or game-object pointers survive a call.
class TradeRoutePresentation final {
public:
    struct Plot {int x,y;};
    struct Route {
        int player=-1;
        TradeConnectionType type=static_cast<TradeConnectionType>(-1);
        std::vector<Plot> plots;
        bool directionKnown=false,forwards=false;
    };
    void NewRoute(int route,int player,TradeConnectionType type,int count,const int* x,const int* y){
        RequireRoute(route);RequirePlayer(player);
        // CvTradeClasses.cpp caps all three NewRoute call sites to 256 plots.
        if(type<TRADE_CONNECTION_INTERNATIONAL || type>=NUM_TRADE_CONNECTION_TYPES || count<1 || count>256 || !x || !y)
            throw std::invalid_argument("Invalid trade route presentation path");
        Route next;next.player=player;next.type=type;
        next.plots.reserve(static_cast<std::size_t>(count));
        for(int i=0;i<count;++i){
            if(x[i]<0 || y[i]<0)throw std::invalid_argument("Invalid trade route presentation coordinate");
            next.plots.push_back({x[i],y[i]});
        }
        const auto previous=routes_.find(route);
        if(previous!=routes_.end()){
            next.directionKnown=previous->second.directionKnown;
            next.forwards=previous->second.forwards;
        }
        routes_[route]=std::move(next);
    }
    void UpdateDirection(int route,bool forwards){
        RequireRoute(route);
        // CreateTradeRoute -> MoveUnit emits this BEFORE the outer player
        // CreateTradeRoute emits NewRoute. Retain it without inventing a path.
        auto& value=routes_[route];value.directionKnown=true;value.forwards=forwards;
    }
    void DestroyRoute(int route,int player){
        RequireRoute(route);RequirePlayer(player);
        const auto value=routes_.find(route);
        // The temporary (-1) preview is destroyed for the active player even
        // when its path was created for a different origin owner.
        if(route!=-1 && value!=routes_.end() && value->second.player!=-1 && value->second.player!=player)
            throw std::invalid_argument("Trade route presentation owner mismatch");
        routes_.erase(route);
        if(hasPopup_ && popupRoute_==route)DeactivatePopup();
    }
    void ActivatePopup(int route){
        RequireRoute(route);const auto value=routes_.find(route);
        if(value==routes_.end() || value->second.plots.empty())
            throw std::logic_error("Trade route popup requires a retained SDK path");
        hasPopup_=true;popupRoute_=route;
    }
    void DeactivatePopup() noexcept {hasPopup_=false;popupRoute_=-1;}
    void Clear() noexcept {routes_.clear();DeactivatePopup();}
    const std::map<int,Route>& Routes() const noexcept {return routes_;}
    bool HasPopup() const noexcept {return hasPopup_;}
    int PopupRoute() const noexcept {return popupRoute_;}
    std::string SnapshotJson() const {
        std::ostringstream out;
        out<<"{\"schema\":\"ZEROSIS_TRADE_ROUTE_PRESENTATION_V1\",\"source\":\"SDK:TradeVisuals\","
              "\"worldRouteRenderingImplemented\":false,\"popupRoute\":";
        if(hasPopup_)out<<popupRoute_;else out<<"null";
        out<<",\"routes\":[";bool first=true;
        for(const auto& entry:routes_){
            if(!first)out<<',';first=false;
            const auto& value=entry.second;
            out<<"{\"index\":"<<entry.first<<",\"player\":"<<value.player<<",\"type\":"<<static_cast<int>(value.type)
               <<",\"directionKnown\":"<<(value.directionKnown?"true":"false")<<",\"forwards\":"<<(value.forwards?"true":"false")
               <<",\"plots\":[";bool firstPlot=true;
            for(const auto& plot:value.plots){if(!firstPlot)out<<',';firstPlot=false;out<<'['<<plot.x<<','<<plot.y<<']';}
            out<<"]}";
        }
        out<<"]}\n";return out.str();
    }
private:
    static void RequireRoute(int route){if(route<-1)throw std::invalid_argument("Invalid trade route presentation index");}
    static void RequirePlayer(int player){if(player<0 || player>=MAX_PLAYERS)throw std::invalid_argument("Invalid trade route presentation player");}
    std::map<int,Route> routes_;
    bool hasPopup_=false;
    int popupRoute_=-1;
};
}
