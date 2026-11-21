#include <functional>
#include "menu_frontend_scene_fixture.h"
#include "MenuReplayPresentation.h"
#include <iostream>

using namespace ZeroSisHost;
using ZeroSisPresentation::BitmapInputEvent;
using ZeroSisPresentation::BitmapInputKind;
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
static void WriteReplayScene(const Scene& scene,const std::wstring& path){
    std::ofstream file(path,std::ios::binary);auto word=[&](std::uint32_t n){file.write(reinterpret_cast<const char*>(&n),4);};
    file.write("ZSUPIX02",8);word(scene.width);word(scene.height);word(static_cast<std::uint32_t>(scene.textures.size()));
    word(static_cast<std::uint32_t>(scene.sprites.size()));word(static_cast<std::uint32_t>(scene.hits.size()));word(0);
    for(const auto& texture:scene.textures){const auto text=Narrow(texture.path);word(static_cast<std::uint32_t>(text.size()));
        file.write(text.data(),static_cast<std::streamsize>(text.size()));}
    for(const auto& sprite:scene.sprites){word(sprite.textureIndex);file.write(reinterpret_cast<const char*>(&sprite.controlKey),8);
        file.write(reinterpret_cast<const char*>(sprite.sourceRect),64);}
    for(const auto& hit:scene.hits){file.write(reinterpret_cast<const char*>(&hit.controlKey),8);file.write(reinterpret_cast<const char*>(hit.bounds),16);}
    Check(static_cast<bool>(file),"Scene proof packet write failed");
}
static void CheckScene(const Scene& scene){
    Check(scene.width==1920 && scene.height==1080,"Replay viewport changed");
    Check(!scene.sprites.empty() && scene.sprites.size()<500000 && scene.textures.size()==25,"Replay sprite/texture bank bound differs");
    std::set<std::uint64_t> keys;
    for(const auto& sprite:scene.sprites){
        Check(sprite.textureIndex==0xffffffffu || sprite.textureIndex<scene.textures.size(),"Replay texture escaped original bank");
        for(float value:sprite.targetRect)Check(std::isfinite(value),"Replay sprite has nonfinite geometry");
        for(float value:sprite.tintRGBA)Check(value>=0 && value<=1,"Replay sprite has invalid tint");
    }
    for(const auto& hit:scene.hits){Check(keys.insert(hit.controlKey).second,"Replay control key collision");
        Check(hit.controlKey>=MenuReplayView::KeyBase,"Replay captured a front-end owned control key");
        Check(hit.bounds[0]>=0 && hit.bounds[1]>=0 && hit.bounds[2]<=1920 && hit.bounds[3]<=1080,"Replay hit escaped its viewport");
        Check(hit.bounds[2]<=1510 || hit.bounds[0]>=1790 || hit.bounds[3]<=1008 || hit.bounds[1]>=1053,
              "Replay input overlaps the front-end Back button");}
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc!=5)throw std::runtime_error("Expected actual asset pack, SDK writer seed, fixture labels/palette, owned output directory");
        const auto assets=MenuFrontEndAssets::Load(argv[1]);const auto raw=Read(argv[2]);const auto frozen=raw;
        const auto metadata=Read(argv[3]);std::size_t cursor=0;
        auto text=[&](){const auto length=U32(metadata,cursor);if(length>4096 || length>metadata.size()-cursor)throw std::runtime_error("Fixture label bound");
            std::string value(reinterpret_cast<const char*>(metadata.data()+cursor),length);cursor+=length;return Widen(value);};
        MenuReplayLabels labels;labels.title=text();labels.map=text();labels.graphs=text();labels.messages=text();labels.playPause=text();
        labels.turn=text();labels.noGraphData=text();labels.terrainReference=text();labels.unsupportedReplay=text();
        MenuReplayPalette palette;const auto count=U32(metadata,cursor);Check(count==2,"Actual recorded-color fixture roster differs");
        for(unsigned i=0;i<count;++i){float values[8];Check(metadata.size()-cursor>=sizeof(values),"Actual fixture colors missing");
            std::memcpy(values,metadata.data()+cursor,sizeof(values));cursor+=sizeof(values);
            palette.playerPrimary.push_back({values[0],values[1],values[2],.8f});palette.playerSecondary.push_back({values[4],values[5],values[6],1});}
        const auto names=U32(metadata,cursor);for(unsigned i=0;i<names;++i){const auto name=Narrow(text());const auto label=text();palette.dataSetLabels[name]=label;}
        Check(cursor==metadata.size(),"Fixture palette has trailing metadata");
        MenuReplayView view(raw,labels,palette);Check(view.Available() && view.ReadError().empty(),"Actual SDK writer fixture did not open");
        auto messages=view.Scene(*assets);CheckScene(messages);
        BitmapInputEvent input{};input.kind=BitmapInputKind::ControlClick;input.controlKey=MenuReplayView::KeyBase+7;
        Check(view.Input(input),"Replay Map tab was not routed");auto map=view.Scene(*assets);CheckScene(map);
        input.controlKey=MenuReplayView::SeekKey;input.logicalX=1190;Check(view.Input(input),"Replay seek target was not routed");
        Check(view.Timeline()->Turn()==9 && view.Timeline()->Frame().plots[1].cityOwner==-1,"Replay seek did not apply recorded final events");
        input.kind=BitmapInputKind::ControlDrag;input.logicalX=430;Check(view.Input(input) && view.Timeline()->Turn()==7,"Replay drag did not restore recorded initial state");
        input.logicalX=std::numeric_limits<float>::quiet_NaN();Check(!view.Input(input),"Replay accepted nonfinite slider input");
        input.kind=BitmapInputKind::ControlClick;input.controlKey=MenuReplayView::KeyBase+1;Check(view.Input(input),"Play/pause callback missing");
        Check(view.Advance(.25) && view.Timeline()->Turn()==8,"Playback update did not advance one recorded turn");
        Check(view.Input(input) && !view.Advance(1),"Paused playback advanced");
        input.controlKey=MenuReplayView::KeyBase+8;Check(view.Input(input),"Replay Graph tab was not routed");
        auto graph=view.Scene(*assets);CheckScene(graph);input.controlKey=MenuReplayView::KeyBase+0x1000;
        Check(view.Input(input),"Graph player toggle missing");Check(view.Scene(*assets).sprites.size()<graph.sprites.size(),"Hidden graph player still rendered");
        Check(view.Input(input),"Graph player restore missing");input.controlKey=MenuReplayView::KeyBase+17;
        Check(view.Input(input),"Graph dataset switch missing");CheckScene(view.Scene(*assets));
        input.controlKey=35;Check(!view.Input(input),"Replay consumed the front-end Back key");
        input.controlKey=MenuReplayView::SeekKey;input.logicalX=800;Check(!view.Input(input),"Hidden Map slider consumed Graph input");
        Check(!view.Advance(1),"Graph view advanced playback");
        input.controlKey=MenuReplayView::KeyBase+7;Check(view.Input(input),"Map return missing");input.kind=BitmapInputKind::KeyDown;input.virtualKey=0x23;
        Check(view.Input(input) && view.Timeline()->Turn()==9,"End key did not seek final turn");input.virtualKey=0x24;
        Check(view.Input(input) && view.Timeline()->Turn()==7,"Home key did not seek initial turn");
        auto invalidRaw=raw;invalidRaw[0]=3;MenuReplayView unsupported(invalidRaw,labels,palette);
        Check(!unsupported.Available() && !unsupported.ReadError().empty(),"Unknown replay format was silently accepted");CheckScene(unsupported.Scene(*assets));
        Check(raw==frozen && view.Timeline()->Document().rawBytes==frozen,"Replay view modified original bytes");
        const auto folder=std::wstring(argv[4]);WriteReplayScene(map,folder+L"\\replay_map.packet");
        WriteReplayScene(graph,folder+L"\\replay_graph.packet");WriteReplayScene(messages,folder+L"\\replay_messages.packet");
        std::cout<<"{\"status\":\"PASS_SDK_FREE_REPLAY_ACTUAL_ASSET_SCENE_AND_INPUT\",\"checks\":"<<checks
                 <<",\"actual_asset_textures\":"<<map.textures.size()<<",\"synthetic_fixture_history\":true,\"host_or_sdk_executed\":false,\"window_or_gpu_created\":false}"<<std::endl;
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<std::endl;return 1;}
}
