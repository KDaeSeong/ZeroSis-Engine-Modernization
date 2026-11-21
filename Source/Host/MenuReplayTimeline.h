#pragma once
#include "MenuReplayData.h"
#include <cmath>
#include <memory>
#include <numeric>

namespace ZeroSisHost {
struct MenuReplayPlot final {
    int x=0,y=0,plotType=-1,terrain=-1,feature=-1,terrainSampleTurn=-1,owner=-1,cityOwner=-1;
    unsigned char riverBits=0;bool terrainReferenceOnly=false;
};
struct MenuReplayFrame final {
    int turn=0,width=0,height=0;bool playing=false;
    // The SDK exports final terrain only. Its sample turn is retained explicitly.
    bool usesFinalTerrainReference=false;
    std::vector<MenuReplayPlot> plots;std::vector<MenuReplayMessage> messages;
};
struct MenuReplaySeries final {int playerIndex=-1;std::vector<MenuReplayPoint> points;};
struct MenuReplayGraph final {
    std::size_t dataSetIndex=0;std::string name;int initialTurn=0,finalTurn=0,minimum=0,maximum=0;
    std::vector<MenuReplaySeries> series;
};
class MenuReplayTimeline final {
public:
    explicit MenuReplayTimeline(std::shared_ptr<const MenuReplayDocument> document):document_(std::move(document)){
        if(!document_)throw std::invalid_argument("Replay timeline requires an owned parsed document");
        const auto& doc=*document_;order_.resize(doc.messages.size());std::iota(order_.begin(),order_.end(),std::size_t(0));
        std::stable_sort(order_.begin(),order_.end(),[&](std::size_t a,std::size_t b){return doc.messages[a].turn<doc.messages[b].turn;});
        frame_.width=doc.width;frame_.height=doc.height;frame_.plots.resize(doc.plots.size());
        turn_=doc.initialTurn;Rebuild();
    }
    const MenuReplayDocument& Document() const noexcept{return *document_;}
    const MenuReplayFrame& Frame() const noexcept{return frame_;}
    int Turn() const noexcept{return turn_;}
    bool Playing() const noexcept{return playing_;}
    void SetPlaying(bool value) noexcept {playing_=value;frame_.playing=value;elapsed_=0;}
    void TogglePlaying() noexcept {SetPlaying(!playing_);}
    bool Seek(int turn){
        if(turn<document_->initialTurn || turn>document_->finalTurn)throw std::out_of_range("Replay seek escaped its recorded turns");
        if(turn==turn_)return false;const int previous=turn_;turn_=turn;elapsed_=0;
        if(turn<previous)Rebuild();else Refresh(false);return true;
    }
    bool Advance(double seconds){
        if(!std::isfinite(seconds) || seconds<0 || seconds>60)throw std::invalid_argument("Replay update requires bounded finite elapsed time");
        if(!playing_ || document_->initialTurn==document_->finalTurn)return false;
        elapsed_+=seconds;const auto steps=static_cast<unsigned>(std::floor(elapsed_/0.25));
        if(!steps)return false;elapsed_-=steps*0.25;
        const auto span=static_cast<unsigned>(document_->finalTurn-document_->initialTurn+1);
        const int next=document_->initialTurn+static_cast<int>((static_cast<unsigned>(turn_-document_->initialTurn)+steps)%span);
        if(next==turn_)return false;const int previous=turn_;turn_=next;
        if(next<previous || steps>=span)Rebuild();else Refresh(false);return true;
    }
    MenuReplayGraph Graph(std::size_t dataSet) const {
        const auto& doc=*document_;if(dataSet>=doc.dataSetNames.size())throw std::out_of_range("Replay dataset is absent");
        MenuReplayGraph graph;graph.dataSetIndex=dataSet;graph.name=doc.dataSetNames[dataSet];
        graph.initialTurn=doc.initialTurn;graph.finalTurn=doc.finalTurn;bool any=false;
        for(std::size_t p=0;p<doc.players.size();++p){MenuReplaySeries series;series.playerIndex=static_cast<int>(p);
            if(dataSet<doc.players[p].dataSets.size())series.points=doc.players[p].dataSets[dataSet];
            for(const auto& point:series.points){if(!any){graph.minimum=graph.maximum=point.value;any=true;}
                else{graph.minimum=std::min(graph.minimum,point.value);graph.maximum=std::max(graph.maximum,point.value);}}
            graph.series.push_back(std::move(series));}
        return graph;
    }
private:
    void Rebuild(){
        cursor_=0;
        for(std::size_t i=0;i<frame_.plots.size();++i){frame_.plots[i]=MenuReplayPlot{};
            frame_.plots[i].x=static_cast<int>(i%static_cast<std::size_t>(document_->width));
            frame_.plots[i].y=static_cast<int>(i/static_cast<std::size_t>(document_->width));}
        Refresh(true);
    }
    void Refresh(bool){
        const auto& doc=*document_;frame_.turn=turn_;frame_.playing=playing_;frame_.usesFinalTerrainReference=false;
        for(std::size_t i=0;i<doc.plots.size();++i){const auto& history=doc.plots[i];auto& target=frame_.plots[i];
            if(history.empty())continue;
            auto found=std::upper_bound(history.begin(),history.end(),turn_,[](int turn,const MenuReplayPlotState& state){return turn<state.turn;});
            const bool future=found==history.begin();if(!future)--found;
            target.plotType=found->plotType;target.terrain=found->terrain;target.feature=found->feature;
            target.riverBits=found->riverBits;target.terrainSampleTurn=found->turn;target.terrainReferenceOnly=future;
            frame_.usesFinalTerrainReference=frame_.usesFinalTerrainReference || future;
        }
        while(cursor_<order_.size() && doc.messages[order_[cursor_]].turn<=turn_){
            const auto& message=doc.messages[order_[cursor_++]];
            for(const auto& position:message.plots){if(position.x<0)continue;
                auto& plot=frame_.plots[static_cast<std::size_t>(position.x+position.y*doc.width)];
                if(message.type==2)plot.owner=message.player;
                else if(message.type==1 || message.type==3)plot.cityOwner=message.player;
                else if(message.type==4)plot.cityOwner=-1;}
        }
        frame_.messages.clear();
        for(const auto index:order_){const auto& message=doc.messages[index];if(message.turn>turn_)break;
            if(message.turn==turn_)frame_.messages.push_back(message);}
    }
    std::shared_ptr<const MenuReplayDocument> document_;std::vector<std::size_t> order_;
    MenuReplayFrame frame_;std::size_t cursor_=0;int turn_=0;bool playing_=false;double elapsed_=0;
};
}
