#include "SceneLineContract.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <type_traits>
#include <utility>
using namespace ZeroSisPresentation;
static unsigned checks=0;
static void Check(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
static SceneLine Stroke(std::uint32_t anchor=0){return {{660,400},{667,410},1,{.1f,.25f,1,.5f},{660,375,1380,735},anchor};}
static Sprite Quad(std::uint64_t key){return {key,kSolidRectangleTexture,{0,0,1,1},{20,30,40,50},{0,0,1920,1080},{.25f,.5f,.75f,1}};}
static void Bad(const Scene& scene){
    unsigned calls=0;std::wstring error;
    Check(!ValidateSceneLines(scene,&error) && !error.empty(),"Malformed line accepted by shared validator");
    Check(!DispatchScenePaint(scene,[&](const Sprite&){++calls;return true;},[&](const SceneLine&){++calls;return true;},nullptr),"Malformed line accepted by dispatcher");
    Check(calls==0,"Dispatcher painted before validating all line anchors and fields");
}
static void SameHit(const HitRecord& a,const HitRecord& b){Check(a.controlKey==b.controlKey && std::memcmp(a.bounds,b.bounds,16)==0,"Line dispatch changed input geometry");}
int main(){
    try{
        static_assert(std::is_pod<SceneLine>::value,"Live line record must own plain numeric fields");
        static_assert(sizeof(SceneLine)==56,"Live line field layout changed");
        Scene empty{};Check(IsSceneEmpty(empty),"Default scene is not empty");
        unsigned calls=0;Check(DispatchScenePaint(empty,[&](const Sprite&){++calls;return true;},[&](const SceneLine&){++calls;return true;},nullptr) && calls==0,"Empty scene painted content");
        empty.lines.push_back(Stroke());Check(!IsSceneEmpty(empty),"Line-only scene was discarded as empty");
        empty.lines.clear();empty.textures.push_back({L"original.dds"});Check(!IsSceneEmpty(empty),"Texture-only scene changed empty semantics");empty.textures.clear();
        empty.hits.push_back({1,{0,0,1,1}});Check(!IsSceneEmpty(empty),"Input-only scene changed empty semantics");empty.hits.clear();
        empty.scrolls.push_back({0,{0,0,1,1}});Check(!IsSceneEmpty(empty),"Owned zero-key scroll region changed empty semantics");empty.scrolls.clear();
        empty.pixelHits.keys.push_back(1);Check(!IsSceneEmpty(empty),"Pixel input-only scene changed empty semantics");
        Scene scene{};scene.width=1920;scene.height=1080;
        for(std::uint64_t i=0;i<3;++i)scene.sprites.push_back(Quad(i+1));
        scene.hits.push_back({77,{10,10,20,20}});scene.scrolls.push_back({78,{20,20,30,30}});scene.pixelHits.keys.push_back(79);scene.pixelHits.indices.push_back(1);
        const auto oldSprites=scene.sprites;std::vector<unsigned char> legacyBytes,orderedBytes;
        auto bytes=[&](const Sprite& sprite,std::vector<unsigned char>& out){
            const auto* key=reinterpret_cast<const unsigned char*>(&sprite.controlKey);out.insert(out.end(),key,key+8);
            const auto* texture=reinterpret_cast<const unsigned char*>(&sprite.textureIndex);out.insert(out.end(),texture,texture+4);
            const auto* fields=reinterpret_cast<const unsigned char*>(sprite.sourceRect);out.insert(out.end(),fields,fields+64);};
        for(const auto& sprite:oldSprites)bytes(sprite,legacyBytes);
        Check(DispatchScenePaint(scene,[&](const Sprite& sprite){bytes(sprite,orderedBytes);return true;},[](const SceneLine&){return false;},nullptr),"Legacy sprite-only dispatch failed");
        Check(orderedBytes==legacyBytes,"Sprite-only painter changed existing packet field bytes/order");
        for(auto anchor:{0u,0u,1u,2u,2u,3u})scene.lines.push_back(Stroke(anchor));
        std::vector<std::pair<char,std::size_t>> trace;std::vector<SceneLine> forwarded;
        Check(DispatchScenePaint(scene,[&](const Sprite& sprite){trace.push_back({'S',static_cast<std::size_t>(&sprite-scene.sprites.data())});return true;},
            [&](const SceneLine& line){trace.push_back({'L',static_cast<std::size_t>(&line-scene.lines.data())});forwarded.push_back(line);return true;},nullptr),"Ordered stroke dispatch failed");
        const std::vector<std::pair<char,std::size_t>> expected{{'L',0},{'L',1},{'S',0},{'L',2},{'S',1},{'L',3},{'L',4},{'S',2},{'L',5}};
        Check(trace==expected,"Line/sprite anchors or equal-anchor alpha order changed");
        for(std::size_t i=0;i<forwarded.size();++i){const auto& a=forwarded[i];const auto& b=scene.lines[i];
            Check(std::memcmp(a.start,b.start,8)==0 && std::memcmp(a.end,b.end,8)==0 && a.width==1 &&
                std::memcmp(a.tintRGBA,b.tintRGBA,16)==0 && std::memcmp(a.clipRect,b.clipRect,16)==0 && a.beforeSprite==b.beforeSprite,
                "Fake target received altered endpoints/width/alpha/clip/order");}
        SameHit(scene.hits[0],{77,{10,10,20,20}});SameHit(scene.scrolls[0],{78,{20,20,30,30}});
        Check(scene.pixelHits.keys==std::vector<std::uint64_t>{79} && scene.pixelHits.indices==std::vector<std::uint32_t>{1},"Visual line dispatch changed pixel picking");
        orderedBytes.clear();for(const auto& sprite:scene.sprites)bytes(sprite,orderedBytes);Check(orderedBytes==legacyBytes,"Line dispatch mutated legacy sprites");
        auto owned=scene;scene.lines[0].start[0]=999;Check(owned.lines[0].start[0]==660,"Scene lines borrow mutable external storage");scene=owned;
        auto malformed=scene;malformed.lines.back().beforeSprite=4;Bad(malformed);
        malformed=scene;malformed.lines[2].beforeSprite=2;malformed.lines[3].beforeSprite=1;Bad(malformed);
        const float nan=(std::numeric_limits<float>::quiet_NaN)(),infinity=(std::numeric_limits<float>::infinity)();
        for(unsigned axis=0;axis<2;++axis){for(float invalid:{nan,infinity,-infinity,10000001.0f,-10000001.0f}){
            malformed=scene;malformed.lines.back().start[axis]=invalid;Bad(malformed);
            malformed=scene;malformed.lines.back().end[axis]=invalid;Bad(malformed);}}
        for(float invalid:{0.0f,-1.0f,256.01f,nan,infinity}){malformed=scene;malformed.lines.back().width=invalid;Bad(malformed);}
        for(unsigned channel=0;channel<4;++channel)for(float invalid:{-0.01f,1.01f,nan,infinity}){
            malformed=scene;malformed.lines.back().tintRGBA[channel]=invalid;Bad(malformed);}
        for(unsigned edge=0;edge<4;++edge)for(float invalid:{nan,infinity,10000001.0f}){
            malformed=scene;malformed.lines.back().clipRect[edge]=invalid;Bad(malformed);}
        malformed=scene;malformed.lines.back().clipRect[2]=malformed.lines.back().clipRect[0];Bad(malformed);
        malformed=scene;malformed.lines.back().clipRect[3]=malformed.lines.back().clipRect[1]-1;Bad(malformed);
        Scene degenerate{};auto point=Stroke();point.end[0]=point.start[0];point.end[1]=point.start[1];degenerate.lines.push_back(point);
        unsigned dots=0;Check(DispatchScenePaint(degenerate,[](const Sprite&){return false;},[&](const SceneLine& line){++dots;return line.start[0]==line.end[0] && line.start[1]==line.end[1];},nullptr) && dots==1,"Degenerate line was invented as a marker or discarded by the dispatcher");
        Scene originalLimit{};originalLimit.lines.assign(6400,Stroke());calls=0;
        Check(DispatchScenePaint(originalLimit,[](const Sprite&){return false;},[&](const SceneLine& line){++calls;Check(line.width==1,"Source line width changed");return true;},nullptr) && calls==6400,"64 original 100-segment graphs exceeded presentation budget");
        Scene genericLimit{};genericLimit.lines.assign(kMaxSceneLines,Stroke());calls=0;
        Check(DispatchScenePaint(genericLimit,[](const Sprite&){return false;},[&](const SceneLine&){++calls;return true;},nullptr) && calls==kMaxSceneLines,"Documented generic line budget was not accepted");
        genericLimit.lines.push_back(Stroke());Bad(genericLimit);
        calls=0;Check(!DispatchScenePaint(scene,[&](const Sprite&){++calls;return true;},[&](const SceneLine&){++calls;return false;},nullptr) && calls==1,"Line target failure did not stop ordered dispatch");
        Scene spriteFailure{};spriteFailure.sprites.push_back(Quad(1));spriteFailure.lines.push_back(Stroke(1));calls=0;
        Check(!DispatchScenePaint(spriteFailure,[&](const Sprite&){++calls;return false;},[&](const SceneLine&){++calls;return true;},nullptr) && calls==1,"Sprite target failure did not stop later strokes");
        std::printf("{\"status\":\"PASS_SCENE_LINE_PURE_VALIDATION_AND_DISPATCH\",\"checks\":%u,\"original_graph_lines\":6400,\"generic_line_cap\":%u,\"ordered_trace_commands\":%zu,\"native_execution\":false,\"sdk_loaded\":false,\"gpu_execution\":false,\"hwnd_created\":false}\n",checks,kMaxSceneLines,trace.size());return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}
}
