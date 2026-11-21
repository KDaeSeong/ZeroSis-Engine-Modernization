#pragma once
#include "MenuReplayData.h"
#include "MenuReplayCalendar.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace ZeroSisHost {
struct MenuReplayGraphLine final {int startX=0,startY=0,endX=0,endY=0;};
struct MenuReplayGraphSeriesGeometry final {
    int playerIndex=-1;
    std::vector<MenuReplayGraphLine> lines;
};
struct MenuReplayGraphGeometry final {
    bool hasData=false;
    int minTurn=0,maxTurn=4;
    std::int64_t minScore=0,maxScore=0;
    std::array<std::int64_t,5> verticalTicks{};
    std::array<int,101> sampledTurns{};
    std::size_t rawPointCount=0,totalSegments=0;
    std::vector<MenuReplayGraphSeriesGeometry> series;
};

// ReplayViewer.lua draws 100 segments on its 720x360 GraphCanvas. Its two
// endpoint lookups both use floor(turn), rather than interpolating neighboring
// records. Preserve that original display policy, not an independent stride or
// an all-recorded-points extension. The owned raw document is never changed.
inline MenuReplayGraphGeometry BuildMenuReplayGraphGeometry(
    const MenuReplayDocument& document,std::size_t dataSet) {
    const auto require=[](bool valid,const char* reason){
        if(!valid)throw std::runtime_error(reason);
    };
    require(document.dataSetNames.size()<=256 && dataSet<document.dataSetNames.size(),
        "Unsupported replay graph dataset");
    require(document.players.size()<=64,"Unsupported replay graph roster size");
    const auto domain=MenuReplayGraphDomain::Create(document.initialTurn,document.finalTurn);
    MenuReplayGraphGeometry result;result.minTurn=domain.minTurn;result.maxTurn=domain.maxTurn;
    result.series.resize(document.players.size());
    // The original maximum begins at zero, including negative-only datasets.
    std::int64_t minimum=0,maximum=0;
    for(std::size_t player=0;player<document.players.size();++player){
        const auto& entry=document.players[player];result.series[player].playerIndex=static_cast<int>(player);
        require(entry.dataSets.size()<=document.dataSetNames.size(),"Unsupported replay player dataset count");
        if(dataSet>=entry.dataSets.size())continue;
        const auto& points=entry.dataSets[dataSet];
        require(points.size()<=1000001 && points.size()<=2000000-result.rawPointCount,
            "Unsupported replay graph recorded-point budget");
        result.rawPointCount+=points.size();
        int previous=-1;
        for(const auto& point:points){
            require(point.turn>=document.initialTurn && point.turn<=document.finalTurn && point.turn>previous,
                "Unsupported replay graph turn order or interval");
            previous=point.turn;
            if(!result.hasData){minimum=point.value;result.hasData=true;}
            else if(point.value<minimum)minimum=point.value;
            if(point.value>maximum)maximum=point.value;
        }
    }
    const int span=result.maxTurn-result.minTurn;
    std::array<int,101> x{};
    for(std::size_t i=0;i<result.sampledTurns.size();++i){
        // Do not replace this operation order with integer/rational arithmetic:
        // the original double division/multiplication can round an integral
        // sample position down before floor (for example some 100-turn spans).
        const double increment=static_cast<double>(i)/100.0;
        result.sampledTurns[i]=result.minTurn+static_cast<int>(std::floor(increment*static_cast<double>(span)));
        x[i]=static_cast<int>(std::floor(increment*720.0));
    }
    if(!result.hasData)return result;
    const std::int64_t range=maximum-minimum;
    // This adds four even when range is already divisible by four. It also
    // handles constant datasets without an invented symmetric padding rule.
    const std::int64_t newRange=range+4-range%4;
    result.minScore=minimum;result.maxScore=minimum+newRange;
    for(std::size_t i=0;i<result.verticalTicks.size();++i)
        result.verticalTicks[i]=minimum+static_cast<std::int64_t>(i)*(newRange/4);
    const double yScale=360.0/static_cast<double>(newRange);
    for(std::size_t player=0;player<document.players.size();++player){
        const auto& entry=document.players[player];
        if(dataSet>=entry.dataSets.size())continue;
        const auto& points=entry.dataSets[dataSet];
        std::array<const MenuReplayPoint*,101> values{};
        for(std::size_t i=0;i<values.size();++i){
            const int turn=result.sampledTurns[i];
            const auto found=std::lower_bound(points.begin(),points.end(),turn,
                [](const MenuReplayPoint& point,int selected){return point.turn<selected;});
            if(found!=points.end() && found->turn==turn)values[i]=&*found;
        }
        auto& lines=result.series[player].lines;lines.reserve(100);
        for(std::size_t i=0;i<100;++i){
            if(!values[i] || !values[i+1])continue;
            const double first=static_cast<double>(values[i]->value)-static_cast<double>(minimum);
            const double second=static_cast<double>(values[i+1]->value)-static_cast<double>(minimum);
            lines.push_back({x[i],360-static_cast<int>(std::floor(first*yScale)),
                             x[i+1],360-static_cast<int>(std::floor(second*yScale))});
        }
        result.totalSegments+=lines.size();
    }
    return result;
}
}
