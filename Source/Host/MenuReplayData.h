#pragma once
#include <algorithm>
#include <cstdint>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

namespace ZeroSisHost {
struct MenuReplayPoint final {int turn=0,value=0;};
struct MenuReplayPosition final {int x=0,y=0;};
struct MenuReplayPlotState final {
    int turn=0,plotType=0,terrain=0,feature=255;unsigned char riverBits=0;
};
struct MenuReplayPlayer final {
    int civilization=-1,leader=-1,playerColor=-1,difficulty=-1;
    std::string leaderName,civilizationName,civilizationShortName,civilizationAdjective;
    std::vector<std::vector<MenuReplayPoint>> dataSets;
};
struct MenuReplayMessage final {
    int turn=0,type=-1,player=-1;std::string text;
    std::vector<MenuReplayPosition> plots;
};
struct MenuReplayDocument final {
    // This is the local BNW SDK WriteReplay stream, not a guessed retail wrapper.
    // CvReplayInfo.cpp writes version 1; CvReplayMessage.cpp writes version 2.
    int version=1,messageVersion=2,activePlayer=-1,worldSize=-1,climate=-1,seaLevel=-1,era=-1,gameSpeed=-1;
    int victoryType=-1,gameType=-1,initialTurn=0,startYear=0,finalTurn=0,calendar=-1,normalizedScore=0;
    int width=0,height=0;
    std::string mapScriptName,finalDate;
    std::vector<int> gameOptions,victoryTypes;
    std::vector<std::string> dataSetNames;
    std::vector<MenuReplayPlayer> players;
    std::vector<MenuReplayMessage> messages;
    std::vector<std::vector<MenuReplayPlotState>> plots;
    std::vector<unsigned char> rawBytes;
};

namespace MenuReplayReadDetail {
inline void Require(bool value,const char* reason){if(!value)throw std::runtime_error(reason);}
inline bool Utf8(const std::string& text){
    for(std::size_t at=0;at<text.size();){
        const auto first=static_cast<unsigned char>(text[at++]);
        if(!first)return false;
        if(first<128)continue;
        unsigned count=0;std::uint32_t code=0,minimum=0;
        if(first>=0xc2 && first<=0xdf){count=1;code=first&31u;minimum=0x80;}
        else if(first>=0xe0 && first<=0xef){count=2;code=first&15u;minimum=0x800;}
        else if(first>=0xf0 && first<=0xf4){count=3;code=first&7u;minimum=0x10000;}
        else return false;
        if(count>text.size()-at)return false;
        for(unsigned i=0;i<count;++i){const auto next=static_cast<unsigned char>(text[at++]);
            if((next&0xc0)!=0x80)return false;code=(code<<6)|(next&63u);}
        if(code<minimum || code>0x10ffff || (code>=0xd800 && code<=0xdfff))return false;
    }
    return true;
}
class Reader final {
public:
    explicit Reader(const std::vector<unsigned char>& raw):raw_(raw){
        Require(raw.size()>=8 && raw.size()<=64u*1024u*1024u,"Replay byte count is outside the 64 MiB bound");
    }
    std::size_t Left() const noexcept{return raw_.size()-at_;}
    unsigned char Byte(){Require(Left()>=1,"Truncated replay byte");return raw_[at_++];}
    std::uint32_t U32(){Require(Left()>=4,"Truncated replay integer");std::uint32_t value=0;
        for(unsigned i=0;i<4;++i)value|=std::uint32_t(Byte())<<(i*8);return value;}
    int I32(){const auto bits=U32();std::int32_t value;std::memcpy(&value,&bits,sizeof(value));return value;}
    int I16(){Require(Left()>=2,"Truncated replay coordinate");const auto low=Byte();const auto high=Byte();
        const std::uint16_t bits=std::uint16_t(low)|static_cast<std::uint16_t>(std::uint16_t(high)<<8);
        std::int16_t value;std::memcpy(&value,&bits,sizeof(value));return value;}
    std::uint32_t Count(std::uint32_t maximum,std::size_t minimumBytes){
        const auto count=U32();Require(count<=maximum && (!minimumBytes || count<=Left()/minimumBytes),
            "Replay collection count exceeds its stream or role bound");
        Require(count<=2000000u-entries_,"Replay aggregate entry budget exceeded");entries_+=count;return count;
    }
    std::string Text(){
        const auto count=Count(1024u*1024u,1);Require(count<=8u*1024u*1024u-textBytes_,"Replay text budget exceeded");
        textBytes_+=count;std::string value(reinterpret_cast<const char*>(raw_.data()+at_),count);at_+=count;
        Require(Utf8(value),"Replay text is not canonical UTF-8");return value;
    }
    std::vector<int> Integers(std::uint32_t bound){
        const auto count=Count(bound,4);std::vector<int> values;values.reserve(count);
        for(std::uint32_t i=0;i<count;++i)values.push_back(I32());return values;
    }
private:
    const std::vector<unsigned char>& raw_;std::size_t at_=0;std::uint32_t entries_=0,textBytes_=0;
};
}

inline MenuReplayDocument ReadMenuReplay(const std::vector<unsigned char>& raw){
    using namespace MenuReplayReadDetail;
    Reader input(raw);MenuReplayDocument out;
    out.version=input.I32();Require(out.version==1,"Unsupported SDK replay version (expected BNW raw version 1)");
    out.activePlayer=input.I32();out.mapScriptName=input.Text();
    out.worldSize=input.I32();out.climate=input.I32();out.seaLevel=input.I32();out.era=input.I32();out.gameSpeed=input.I32();
    out.gameOptions=input.Integers(1024);out.victoryTypes=input.Integers(256);out.victoryType=input.I32();
    // SdkEnumSerialization.cpp / SdkEnumTypes.inc: GameTypes is a signed BYTE.
    const auto gameType=input.Byte();out.gameType=gameType<128?gameType:static_cast<int>(gameType)-256;
    out.initialTurn=input.I32();out.startYear=input.I32();out.finalTurn=input.I32();out.finalDate=input.Text();
    out.calendar=input.I32();out.normalizedScore=input.I32();
    Require(out.initialTurn>=0 && out.finalTurn>=out.initialTurn && out.finalTurn<=10000000 &&
            out.finalTurn-out.initialTurn<=1000000,"Replay turn interval exceeds its bound");
    const auto playerCount=input.Count(64,32);out.players.resize(playerCount);
    Require(out.activePlayer>=-1 && out.activePlayer<static_cast<int>(playerCount),"Replay active player is outside its remapped roster");
    for(auto& player:out.players){
        player.civilization=input.I32();player.leader=input.I32();player.playerColor=input.I32();player.difficulty=input.I32();
        player.leaderName=input.Text();player.civilizationName=input.Text();
        player.civilizationShortName=input.Text();player.civilizationAdjective=input.Text();
    }
    const auto names=input.Count(256,4);out.dataSetNames.reserve(names);
    for(std::uint32_t i=0;i<names;++i){auto name=input.Text();
        Require(!name.empty() && std::find(out.dataSetNames.begin(),out.dataSetNames.end(),name)==out.dataSetNames.end(),
                "Replay dataset name is empty or duplicated");out.dataSetNames.push_back(std::move(name));}
    const auto histories=input.Count(64,4);Require(histories==playerCount,"Replay history roster differs from player metadata");
    for(auto& player:out.players){
        const auto dataSets=input.Count(names,4);player.dataSets.resize(dataSets);
        for(auto& history:player.dataSets){
            const auto count=input.Count(1000001,8);history.reserve(count);std::uint32_t previous=0;
            for(std::uint32_t i=0;i<count;++i){const auto turn=input.U32();const auto value=input.I32();
                Require(turn<=static_cast<unsigned>(out.finalTurn-out.initialTurn) && (!i || turn>previous),
                        "Replay dataset turn is outside its interval or is not strictly ordered");previous=turn;
                history.push_back({out.initialTurn+static_cast<int>(turn),value});}
        }
    }
    out.messageVersion=static_cast<int>(input.U32());Require(out.messageVersion==2,"Unsupported replay message version");
    const auto messages=input.Count(1000000,20);out.messages.reserve(messages);
    for(std::uint32_t i=0;i<messages;++i){
        MenuReplayMessage message;message.turn=input.I32();message.type=input.I32();
        Require(message.turn>=out.initialTurn && message.turn<=out.finalTurn && message.type>=0 && message.type<=6,
                "Replay event turn or type is outside its source contract");
        const auto count=input.Count(262144,4);message.plots.reserve(count);
        for(std::uint32_t p=0;p<count;++p){const int x=input.I16();const int y=input.I16();message.plots.push_back({x,y});}
        message.player=input.I32();Require(message.player>=-1 && message.player<static_cast<int>(playerCount),
                                         "Replay event has no remapped player");
        message.text=input.Text();out.messages.push_back(std::move(message));
    }
    out.width=input.I32();out.height=input.I32();
    Require(out.width>0 && out.height>0 && out.width<=1024 && out.height<=1024 &&
            std::uint64_t(out.width)*std::uint64_t(out.height)<=262144,"Replay map dimensions exceed their bound");
    const auto plots=input.Count(262144,4);Require(plots==static_cast<unsigned>(out.width*out.height),
                                               "Replay plot table does not cover the recorded map");
    out.plots.resize(plots);
    for(auto& plot:out.plots){
        const auto count=input.Count(1000001,8);plot.reserve(count);int previous=-1;
        for(std::uint32_t i=0;i<count;++i){const auto turn=input.U32();
            Require(turn<=static_cast<unsigned>(out.finalTurn) && turn>=static_cast<unsigned>(out.initialTurn) &&
                    static_cast<int>(turn)>previous,"Replay plot states have duplicate, unordered or out-of-range turns");
            previous=static_cast<int>(turn);MenuReplayPlotState state;state.turn=previous;
            state.plotType=input.Byte();state.terrain=input.Byte();state.feature=input.Byte();state.riverBits=input.Byte();
            Require(state.plotType<=3 && (state.riverBits&~14u)==0,"Replay plot or river encoding is unsupported");plot.push_back(state);}
    }
    for(const auto& message:out.messages)for(const auto& plot:message.plots)
        Require((plot.x==-1 && plot.y==-1) || (plot.x>=0 && plot.y>=0 && plot.x<out.width && plot.y<out.height),
                "Replay event coordinate escapes the map");
    Require(!input.Left(),"Replay has trailing bytes outside the known SDK raw stream");
    out.rawBytes=raw;return out;
}
}
