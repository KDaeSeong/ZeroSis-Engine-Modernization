#include <functional>
#include "menu_frontend_scene_fixture.h"
#include "MenuReplayPresentation.h"
#define main sdk_writer_seed_fixture_main
#include "menu_replay_fixture.cpp"
#undef main

int wmain(int argc,wchar_t** argv){
    try{
        if(argc!=2)throw std::runtime_error("Expected the immutable original front-end asset pack");
        const auto assets=MenuFrontEndAssets::Load(argv[1]);
        auto info=Seed();info.m_iFinalTurn=info.m_iInitialTurn+1023;info.m_listReplayMessages.clear();
        info.m_listPlayerInfo.resize(64);info.m_listPlayerInfo[0].m_strCustomLeaderName=std::string(50000,'A');
        info.m_listPlayerInfo[1].m_strCustomLeaderName="\xf0\x9f\x98\x80";
        info.m_listPlayerDataSets.assign(64,CvReplayInfo::TurnDataSets(1));
        for(auto& player:info.m_listPlayerDataSets)for(unsigned turn=0;turn<1024;++turn)
            player[0][turn]=(turn&1)?INT_MAX:INT_MIN;
        for(auto& plot:info.m_listPlots){const auto state=plot.begin()->second;plot.clear();plot[static_cast<unsigned>(info.m_iFinalTurn)]=state;}
        FDataStream stream;info.write(stream);const auto original=stream.bytes;
        MenuReplayLabels labels;labels.title=L"Replay";labels.map=L"Map";labels.graphs=L"Graph";labels.messages=L"Messages";
        labels.playPause=L"Play/Pause";labels.turn=L"Turn";labels.noGraphData=L"No data";
        labels.terrainReference=L"Final terrain reference";labels.unsupportedReplay=L"Unsupported format";
        MenuReplayPalette palette;palette.playerPrimary.assign(64,{1,1,1,.8f});palette.playerSecondary.assign(64,{1,1,1,1});
        MenuReplayView viewer(stream.bytes,labels,palette);Check(viewer.Available());
        ZeroSisPresentation::BitmapInputEvent event{};event.kind=ZeroSisPresentation::BitmapInputKind::ControlClick;event.controlKey=MenuReplayView::KeyBase+8;
        Check(viewer.Input(event));const auto scene=viewer.Scene(*assets);
        std::size_t markers=0,linePixels=0;
        for(const auto& sprite:scene.sprites){
            if(sprite.textureIndex!=ZeroSisPresentation::kSolidRectangleTexture)continue;
            const auto width=sprite.targetRect[2]-sprite.targetRect[0],height=sprite.targetRect[3]-sprite.targetRect[1];
            if(width==4 && height==4)++markers;
            if(width==2 && height==2)++linePixels;
        }
        Check(markers==65536);Check(linePixels>0 && linePixels<=200000);Check(scene.sprites.size()<300000);
        const auto& document=viewer.Timeline()->Document();std::size_t points=0;
        for(const auto& player:document.players)points+=player.dataSets[0].size();
        Check(points==65536 && document.players[0].leaderName.size()==50000);
        Check(document.players[1].leaderName=="\xf0\x9f\x98\x80");
        Check(document.rawBytes==original && stream.bytes==original);
        std::cout<<"{\"status\":\"PASS_SDK_FREE_REPLAY_DISPLAY_BUDGET_AND_LONG_LABEL\",\"checks\":"<<checks
            <<",\"players\":64,\"recorded_points\":"<<points<<",\"rendered_point_markers\":"<<markers
            <<",\"connection_line_rectangles\":"<<linePixels<<",\"scene_sprites\":"<<scene.sprites.size()
            <<",\"original_name_bytes\":50000,\"source_records_unchanged\":true,\"host_or_sdk_executed\":false}"<<std::endl;
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<std::endl;return 1;}
}
