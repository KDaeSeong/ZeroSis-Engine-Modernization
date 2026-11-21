#include "MenuReplayGraphGeometry.h"
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>

namespace {
using namespace ZeroSisHost;
void Check(bool valid,const char* message){if(!valid)throw std::runtime_error(message);}
class Reader final {
public:
    explicit Reader(const char* path){
        std::ifstream input(path,std::ios::binary);Check(bool(input),"Cannot open graph geometry goldens");
        bytes_.assign(std::istreambuf_iterator<char>(input),std::istreambuf_iterator<char>());
        Check(bytes_.size()>=12 && bytes_.size()<=32u*1024u*1024u &&
            std::memcmp(bytes_.data(),"ZSGEO001",8)==0,"Graph geometry fixture version/size differs");cursor_=8;
    }
    std::uint32_t U32(){
        Check(Left()>=4,"Truncated graph geometry integer");std::uint32_t value=0;
        for(unsigned i=0;i<4;++i)value|=std::uint32_t(bytes_[cursor_++])<<(8*i);return value;
    }
    int I32(){const auto bits=U32();std::int32_t value=0;std::memcpy(&value,&bits,4);return value;}
    std::int64_t I64(){
        Check(Left()>=8,"Truncated graph geometry int64");std::int64_t value=0;
        std::memcpy(&value,bytes_.data()+cursor_,8);cursor_+=8;return value;
    }
    std::string Text(){
        const auto length=U32();Check(length<=4096 && length<=Left(),"Graph fixture text out of bounds");
        std::string value(reinterpret_cast<const char*>(bytes_.data()+cursor_),length);cursor_+=length;return value;
    }
    std::vector<MenuReplayPoint> History(){
        const auto kind=U32(),count=U32();Check(count<=1000001,"Graph fixture history out of bounds");
        std::vector<MenuReplayPoint> result;result.reserve(count);
        if(kind==0){for(std::uint32_t i=0;i<count;++i){const int turn=I32(),value=I32();result.push_back({turn,value});}}
        else{
            Check(kind==1,"Unknown graph fixture generator");const int first=I32(),pattern=I32(),low=I32(),high=I32(),spike=I32();
            for(std::uint32_t i=0;i<count;++i){
                int value=low;
                if(pattern==1)value=low+static_cast<int>(i);
                else if(pattern==2)value=(i&1u)?high:low;
                else if(pattern==3)value=i==static_cast<std::uint32_t>(spike)?high:low;
                else Check(pattern==0,"Unknown graph fixture value pattern");
                result.push_back({first+static_cast<int>(i),value});
            }
        }
        return result;
    }
    std::size_t Left() const {return bytes_.size()-cursor_;}
private:
    std::vector<unsigned char> bytes_;std::size_t cursor_=0;
};
std::uint64_t Fingerprint(const MenuReplayDocument& document){
    std::uint64_t value=1469598103934665603ull;
    const auto mix=[&](std::uint32_t word){value^=word;value*=1099511628211ull;};
    mix(static_cast<std::uint32_t>(document.initialTurn));mix(static_cast<std::uint32_t>(document.finalTurn));
    for(const auto& player:document.players)for(const auto& history:player.dataSets){mix(static_cast<std::uint32_t>(history.size()));
        for(const auto& point:history){mix(static_cast<std::uint32_t>(point.turn));mix(static_cast<std::uint32_t>(point.value));}}
    for(unsigned char byte:document.rawBytes)mix(byte);
    return value;
}
template<class Function> void Throws(Function function){
    bool failed=false;try{function();}catch(const std::exception&){failed=true;}
    Check(failed,"Malformed graph geometry input was not rejected");
}
unsigned InvalidBounds(){
    MenuReplayDocument document;document.initialTurn=0;document.finalTurn=100;document.dataSetNames={"DATA"};
    document.players.resize(1);document.players[0].dataSets={{{0,0},{100,4}}};
    unsigned count=0;
    Throws([&]{BuildMenuReplayGraphGeometry(document,1);});++count;
    auto invalid=document;invalid.dataSetNames.clear();Throws([&]{BuildMenuReplayGraphGeometry(invalid,0);});++count;
    invalid=document;invalid.dataSetNames.resize(257);Throws([&]{BuildMenuReplayGraphGeometry(invalid,0);});++count;
    invalid=document;invalid.players.resize(65);Throws([&]{BuildMenuReplayGraphGeometry(invalid,0);});++count;
    invalid=document;invalid.players[0].dataSets.resize(2);Throws([&]{BuildMenuReplayGraphGeometry(invalid,0);});++count;
    for(const auto bounds:std::vector<std::pair<int,int>>{{-1,100},{100,99},{0,10000001},{0,1000001}}){
        invalid=document;invalid.initialTurn=bounds.first;invalid.finalTurn=bounds.second;
        Throws([&]{BuildMenuReplayGraphGeometry(invalid,0);});++count;
    }
    for(const auto history:std::vector<std::vector<MenuReplayPoint>>{
            {{0,1},{0,2}},{{1,1},{0,2}},{{-1,1}},{{101,1}}}){
        invalid=document;invalid.players[0].dataSets={history};
        Throws([&]{BuildMenuReplayGraphGeometry(invalid,0);});++count;
    }
    invalid=document;invalid.finalTurn=1000000;invalid.players[0].dataSets[0].resize(1000002);
    Throws([&]{BuildMenuReplayGraphGeometry(invalid,0);});++count;
    invalid=MenuReplayDocument{};invalid.initialTurn=0;invalid.finalTurn=1000000;invalid.dataSetNames={"DATA"};
    invalid.players.resize(2);invalid.players[0].dataSets.resize(1);invalid.players[1].dataSets.resize(1);
    auto& first=invalid.players[0].dataSets[0];first.reserve(1000001);
    for(int turn=0;turn<=1000000;++turn)first.push_back({turn,turn});
    invalid.players[1].dataSets[0].resize(1000000);
    Throws([&]{BuildMenuReplayGraphGeometry(invalid,0);});++count;
    return count;
}
}

int main(int argc,char** argv){
    try{
        Check(argc==2,"Expected one graph geometry golden file");Reader input(argv[1]);
        const auto cases=input.U32();Check(cases>0 && cases<=4096,"Graph golden case count differs");
        std::size_t checkedLines=0,rawPoints=0,largestHistory=0,maxSegments=0;
        for(std::uint32_t test=0;test<cases;++test){
            const auto name=input.Text();MenuReplayDocument document;
            document.initialTurn=input.I32();document.finalTurn=input.I32();
            const auto selected=input.U32(),names=input.U32(),players=input.U32();
            Check(names<=256 && players<=64,"Graph golden document bounds differ");
            document.dataSetNames.resize(names);for(std::uint32_t i=0;i<names;++i)document.dataSetNames[i]="DATA_"+std::to_string(i);
            document.players.resize(players);std::vector<bool> hidden;
            std::vector<const MenuReplayPoint*> addresses;
            for(auto& player:document.players){
                hidden.push_back(input.U32()!=0);const auto histories=input.U32();Check(histories<=names,"Graph fixture dataset count differs");
                player.dataSets.reserve(histories);
                for(std::uint32_t i=0;i<histories;++i){player.dataSets.push_back(input.History());
                    addresses.push_back(player.dataSets.back().data());largestHistory=(std::max)(largestHistory,player.dataSets.back().size());}
            }
            document.rawBytes={0x52,0x41,0x57,0,0xff,0x11};
            const auto before=Fingerprint(document);const auto actual=BuildMenuReplayGraphGeometry(document,selected);
            Check(actual.hasData==(input.U32()!=0),"Original Lua graph data availability differs");
            if(actual.hasData){
                Check(actual.minTurn==input.I32() && actual.maxTurn==input.I32(),"Original padded graph domain differs");
                Check(actual.minScore==input.I64() && actual.maxScore==input.I64(),"Original graph score range differs");
                for(auto tick:actual.verticalTicks)Check(tick==input.I64(),"Original graph vertical marker differs");
            }
            Check(actual.series.size()==players,"Graph player ordering differs");
            std::size_t visible=0;
            for(std::size_t player=0;player<actual.series.size();++player){
                const auto& series=actual.series[player];const auto lines=input.U32();
                Check(series.playerIndex==static_cast<int>(player) && series.lines.size()==lines,"Original graph segment count differs");
                for(const auto& line:series.lines){
                    const int sx=input.I32(),sy=input.I32(),ex=input.I32(),ey=input.I32();
                    if(line.startX!=sx || line.startY!=sy || line.endX!=ex || line.endY!=ey)
                        throw std::runtime_error("Original graph line differs in "+name+" player "+std::to_string(player));
                    Check(line.startX>=0 && line.startX<=720 && line.endX>=0 && line.endX<=720 &&
                          line.startY>=0 && line.startY<=360 && line.endY>=0 && line.endY<=360,
                          "Graph segment escaped original canvas");
                    ++checkedLines;if(!hidden[player])++visible;
                }
            }
            Check(visible==input.U32(),"Hidden graph-series rendering filter differs from original Lua");
            Check(actual.rawPointCount==input.U32() && actual.totalSegments<=6400,"Graph raw-point or segment bound differs");
            Check(Fingerprint(document)==before,"Graph projection modified an owned document");
            std::size_t address=0;
            for(const auto& player:document.players)for(const auto& history:player.dataSets)
                Check(history.data()==addresses[address++],"Graph projection replaced owned point storage");
            rawPoints+=actual.rawPointCount;maxSegments=(std::max)(maxSegments,actual.totalSegments);
        }
        Check(input.Left()==0,"Trailing graph golden bytes");const auto invalid=InvalidBounds();
        std::cout<<"{\"status\":\"PASS_VERBATIM_ORIGINAL_LUA_GRAPH_GEOMETRY_CXX14\",\"cases\":"<<cases
            <<",\"matched_lines\":"<<checkedLines<<",\"visited_recorded_points\":"<<rawPoints
            <<",\"largest_history\":"<<largestHistory<<",\"maximum_case_segments\":"<<maxSegments
            <<",\"invalid_bounds_checks\":"<<invalid<<",\"source_documents_unchanged\":true,\"host_sdk_window_gpu_execution\":false}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
