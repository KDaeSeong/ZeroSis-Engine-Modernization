// SDK-free fixture. sdk_replay_writer.inc contains exact local SDK writer bodies.
#include "MenuReplayTimeline.h"
#include <climits>
#include <fstream>
#include <iostream>
#include <map>
#include <type_traits>

using uint=unsigned int;
using CvString=std::string;
enum GameTypes { GAME_TEST=-1 };
namespace CvChecked {template<class T,class U>T Integer(U value){
    if(value>static_cast<U>((std::numeric_limits<T>::max)()))throw std::length_error("fixture count");return static_cast<T>(value);}}
struct FDataStream {
    std::vector<unsigned char> bytes;
    template<class T,std::enable_if_t<std::is_integral<T>::value,int> =0>FDataStream& operator<<(T value){
        using U=typename std::make_unsigned<T>::type;const U bits=static_cast<U>(value);
        for(unsigned i=0;i<sizeof(T);++i)bytes.push_back(static_cast<unsigned char>((bits>>(8*i))&255u));return *this;}
    FDataStream& operator<<(GameTypes value){bytes.push_back(static_cast<unsigned char>(static_cast<int>(value)&255));return *this;}
    FDataStream& operator<<(const std::string& value);
    unsigned WriteIt(unsigned count,const void* data){const auto* raw=static_cast<const unsigned char*>(data);
        bytes.insert(bytes.end(),raw,raw+count);return count;}
};
class CvReplayMessage {
public:
    using PlotPositionList=std::vector<std::pair<short,short>>;
    int m_iTurn=7,m_eType=0,m_ePlayer=-1;PlotPositionList m_Plots;std::string m_strText;
    static unsigned Version(){return 2;}void write(FDataStream&) const;
};
class CvReplayInfo {
public:
    struct PlayerInfo {int m_eCivilization=0,m_eLeader=0,m_ePlayerColor=0,m_eDifficulty=0;
        std::string m_strCustomLeaderName,m_strCustomCivilizationName,m_strCustomCivilizationShortName,m_strCustomCivilizationAdjective;};
    struct PlotState {int m_ePlotType=2,m_eTerrain=0,m_eFeature=255;bool m_bNWOfRiver=false,m_bWOfRiver=false,m_bNEOfRiver=false;};
    using TurnData=std::map<unsigned,int>;using TurnDataSets=std::vector<TurnData>;
    using ReplayMessageList=std::vector<CvReplayMessage>;
    static int REPLAY_VERSION;
    int m_iActivePlayer=0,m_eWorldSize=2,m_eClimate=1,m_eSeaLevel=0,m_eEra=0,m_eGameSpeed=2;
    int m_eVictoryType=-1,m_iInitialTurn=7,m_iStartYear=-4000,m_iFinalTurn=9,m_eCalendar=0,m_iNormalizedScore=8;
    GameTypes m_eGameType=GAME_TEST;
    std::string m_strMapScriptName="Map.lua",m_strFinalDate="Final";
    std::vector<int> m_listGameOptions,m_listVictoryTypes;
    std::vector<PlayerInfo> m_listPlayerInfo;
    std::vector<std::string> m_dataSetMap;
    std::vector<TurnDataSets> m_listPlayerDataSets;
    ReplayMessageList m_listReplayMessages;
    int m_iMapWidth=2,m_iMapHeight=2;
    std::vector<std::map<unsigned,PlotState>> m_listPlots;
    void write(FDataStream&) const;
};
int CvReplayInfo::REPLAY_VERSION=1;
FDataStream& operator<<(FDataStream&,const CvReplayInfo::PlayerInfo&);
FDataStream& operator<<(FDataStream&,const CvReplayInfo::PlotState&);
FDataStream& operator<<(FDataStream&,const CvReplayInfo::TurnData&);
#include "sdk_replay_writer.inc"
FDataStream& FDataStream::operator<<(const std::string& value){writeText(*this,value.data(),value.size());return *this;}

using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool value){++checks;if(!value)throw std::runtime_error("Replay fixture assertion "+std::to_string(checks));}
template<class F>static void Reject(F function){bool rejected=false;try{function();}catch(const std::exception&){rejected=true;}Check(rejected);}
static CvReplayInfo Seed(){
    CvReplayInfo info;info.m_listGameOptions={1,4};info.m_listVictoryTypes={0,2};
    info.m_listPlayerInfo.resize(2);info.m_listPlayerInfo[0].m_strCustomLeaderName="Alpha";
    info.m_listPlayerInfo[1].m_strCustomLeaderName="Beta";info.m_listPlayerInfo[1].m_ePlayerColor=7;
    info.m_dataSetMap={"REPLAYDATASET_SCORE","REPLAYDATASET_POPULATION"};
    info.m_listPlayerDataSets={{{{0,3},{1,6},{2,8}}},{{{0,5},{2,7}},{{0,11},{2,20}}}};
    auto message=[&](int turn,int type,int player,short x,short y){CvReplayMessage event;
        event.m_iTurn=turn;event.m_eType=type;event.m_ePlayer=player;event.m_Plots={{x,y}};
        event.m_strText="recorded fixture "+std::to_string(turn);return event;};
    // Deliberately retain original vector order across different turns.
    info.m_listReplayMessages={message(9,4,-1,1,0),message(7,1,0,1,0),message(7,2,0,1,0),
        message(8,3,1,1,0),message(8,2,1,1,0),message(9,2,-1,1,0)};
    for(unsigned i=0;i<4;++i){CvReplayInfo::PlotState state;state.m_eTerrain=static_cast<int>(i);
        state.m_bNWOfRiver=i==1;info.m_listPlots.push_back({{9,state}});}
    return info;
}
int main(int argc,char** argv){
    try{
        FDataStream stream;Seed().write(stream);const auto original=stream.bytes;
        auto document=std::make_shared<const MenuReplayDocument>(ReadMenuReplay(stream.bytes));
        Check(document->rawBytes==original && stream.bytes==original);
        Check(document->gameType==-1 && document->version==1 && document->messageVersion==2);
        Check(document->initialTurn==7 && document->finalTurn==9 && document->players.size()==2);
        Check(document->messages[0].turn==9 && document->messages[1].plots[0].x==1 && document->messages[1].plots[0].y==0);
        MenuReplayTimeline timeline(document);const auto& first=timeline.Frame();
        Check(first.turn==7 && first.plots[1].owner==0 && first.plots[1].cityOwner==0);
        Check(first.usesFinalTerrainReference && first.plots[1].terrainSampleTurn==9 && first.plots[1].riverBits==2);
        Check(timeline.Seek(8) && timeline.Frame().plots[1].owner==1 && timeline.Frame().plots[1].cityOwner==1);
        Check(timeline.Seek(9) && timeline.Frame().plots[1].owner==-1 && timeline.Frame().plots[1].cityOwner==-1);
        Check(!timeline.Frame().usesFinalTerrainReference);
        Check(timeline.Seek(7) && timeline.Frame().plots[1].owner==0 && timeline.Frame().plots[1].cityOwner==0);
        auto graph=timeline.Graph(0);Check(graph.series.size()==2 && graph.series[1].points.size()==2);
        Check(graph.series[1].points[0].turn==7 && graph.series[1].points[1].turn==9 && graph.minimum==3 && graph.maximum==8);
        Check(timeline.Graph(1).series[0].points.empty());
        Check(!timeline.Advance(1));timeline.TogglePlaying();Check(timeline.Playing());
        Check(!timeline.Advance(.125));Check(timeline.Advance(.125) && timeline.Turn()==8);
        Check(timeline.Advance(.25) && timeline.Turn()==9);Check(timeline.Advance(.25) && timeline.Turn()==7);
        timeline.SetPlaying(false);Check(!timeline.Advance(3));
        Reject([&]{timeline.Seek(6);});Reject([&]{timeline.Seek(10);});Reject([&]{timeline.Graph(2);});
        Reject([&]{timeline.Advance(-.1);});Reject([&]{timeline.Advance(std::numeric_limits<double>::infinity());});
        Reject([&]{timeline.Advance(std::numeric_limits<double>::quiet_NaN());});Reject([&]{timeline.Advance(61);});
        auto wrong=original;wrong[0]=3;Reject([&]{ReadMenuReplay(wrong);});
        wrong=original;wrong.push_back(0);Reject([&]{ReadMenuReplay(wrong);});
        wrong=original;wrong[8]=0xff;wrong[9]=0xff;wrong[10]=0xff;wrong[11]=0xff;Reject([&]{ReadMenuReplay(wrong);});
        wrong=original;wrong[12]=0xc0;Reject([&]{ReadMenuReplay(wrong);});
        for(std::size_t length=0;length<original.size();++length){
            std::vector<unsigned char> truncated(original.begin(),original.begin()+length);Reject([&]{ReadMenuReplay(truncated);});}
        auto single=Seed();single.m_iFinalTurn=single.m_iInitialTurn;single.m_listReplayMessages.clear();
        single.m_listPlayerDataSets={{{{0,3}}},{{{0,5}},{{0,11}}}};
        for(auto& plot:single.m_listPlots){auto state=plot.begin()->second;plot.clear();plot[7]=state;}
        FDataStream singleton;single.write(singleton);MenuReplayTimeline one(std::make_shared<const MenuReplayDocument>(ReadMenuReplay(singleton.bytes)));
        one.SetPlaying(true);Check(!one.Advance(1) && one.Turn()==7 && !one.Frame().usesFinalTerrainReference);
        Check(stream.bytes==original && document->rawBytes==original);
        if(argc==2){std::ofstream file(argv[1],std::ios::binary|std::ios::trunc);
            file.write(reinterpret_cast<const char*>(original.data()),static_cast<std::streamsize>(original.size()));
            Check(static_cast<bool>(file));}
        std::cout<<"{\"status\":\"PASS_SDK_FREE_REPLAY_READER_AND_TIMELINE\",\"checks\":"<<checks
            <<",\"source_writer_fixture_bytes\":"<<original.size()<<",\"synthetic_fixture_history\":true,\"host_sdk_execution\":false}"<<std::endl;
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<std::endl;return 1;}
}
