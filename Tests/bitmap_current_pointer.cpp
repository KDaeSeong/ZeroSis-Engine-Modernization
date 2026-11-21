// Execute verbatim production snapshot/mapping/hit functions against fake,
// read-only OS queries. No Windows header, API, HWND or renderer is linked.
#include "BitmapRenderer.h"
#include "BitmapPointerPress.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <string>
#include <type_traits>
#include <vector>

using DWORD=std::uint32_t;
using HWND=std::uintptr_t;
struct POINT final {std::int32_t x=0,y=0;};
struct RECT final {std::int32_t left=0,top=0,right=0,bottom=0;};
struct FakeQueries final {
    DWORD thread=17;POINT cursor{500,400},origin{100,50};RECT client{0,0,1920,1080};
    bool cursorOk=true,conversionOk=true,clientOk=true;std::vector<unsigned> calls;
};
static FakeQueries queries;
static DWORD GetCurrentThreadId(){queries.calls.push_back(1);return queries.thread;}
static bool GetCursorPos(POINT* point){queries.calls.push_back(2);*point=queries.cursor;return queries.cursorOk;}
static bool ScreenToClient(HWND,POINT* point){queries.calls.push_back(3);point->x-=queries.origin.x;point->y-=queries.origin.y;return queries.conversionOk;}
static bool GetClientRect(HWND,RECT* rect){queries.calls.push_back(4);*rect=queries.client;return queries.clientOk;}

#include "bitmap_current_pointer_actual.inc"

using namespace ZeroSisPresentation;
static unsigned checks=0,samples=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
static void Append(std::ostringstream& text,const BitmapInputEvent& value){
    text<<static_cast<unsigned>(value.kind)<<','<<value.controlKey<<','<<value.virtualKey<<','<<value.logicalX<<','<<value.logicalY<<','<<value.sceneGeneration<<','
        <<value.scrollDelta<<','<<value.modifiers<<','<<value.unicodeScalar<<','<<value.editorOwner<<','<<value.textFocusEpoch<<','<<value.wheelDelta<<','
        <<value.pointerPressId<<','<<value.pointerPressX<<','<<value.pointerPressY<<';';
}
static std::string Fingerprint(const BitmapWindow& window){
    std::ostringstream text;text.precision(std::numeric_limits<float>::max_digits10);
    text<<window.ownerThreadId_<<','<<window.sceneGeneration_<<','<<window.productionPointerInputEnabled_<<','<<window.hwnd_<<','<<window.closing_<<','
        <<window.logicalWidth_<<','<<window.logicalHeight_<<','<<window.captureSentinel<<','<<window.trackingSentinel<<','<<window.overflowSentinel<<';';
    for(const auto& event:window.pending_)Append(text,event);
    for(const auto& hit:window.hits_){text<<hit.controlKey<<':';for(float bound:hit.bounds)text<<bound<<',';}
    for(const auto& key:window.pixelHits_.keys)text<<key<<',';
    for(const auto& index:window.pixelHits_.indices)text<<index<<',';
    return text.str();
}
static BitmapInputEvent Read(const BitmapWindow& window){
    const auto before=Fingerprint(window);queries.calls.clear();
    const auto result=window.CurrentPointerInput();++samples;
    Check(Fingerprint(window)==before,"Current pointer sample changed queue, hit map, capture, flags or window fields");
    Check(result.kind==BitmapInputKind::PointerMove && result.virtualKey==0 && result.scrollDelta==0 && result.modifiers==0 &&
        result.unicodeScalar==0 && result.editorOwner==0 && result.textFocusEpoch==0 && result.wheelDelta==0 &&
        result.pointerPressId==0 && result.pointerPressX==0 && result.pointerPressY==0,"Snapshot reused stale command/press/editor metadata");
    return result;
}
static void Neutral(const BitmapInputEvent& event,std::uint64_t generation){
    Check(event.logicalX==0 && event.logicalY==0 && event.controlKey==0 && event.sceneGeneration==generation,"Unavailable snapshot was not fully neutral");
}
static void Calls(std::initializer_list<unsigned> expected){Check(queries.calls==std::vector<unsigned>(expected),"Read-only native query order/short-circuit changed");}
static BitmapWindow Window(){
    BitmapWindow window;
    BitmapInputEvent queued{BitmapInputKind::ControlDrag,0x300000102ull,79,77,88,2};queued.pointerPressId=111;queued.pointerPressX=12;queued.pointerPressY=13;
    window.pending_.push_back(queued);window.pending_.push_back({BitmapInputKind::ControlClick,35,0,50,60,3});
    return window;
}
static void Failures(){
    auto window=Window();queries={};
    auto event=Read(window);Check(event.logicalX==400 && event.logicalY==350 && event.controlKey==0 && event.sceneGeneration==9,"Valid unowned key-zero pointer was lost");Calls({1,2,3,4});
    window.productionPointerInputEnabled_=false;Neutral(Read(window),9);Calls({1});window.productionPointerInputEnabled_=true;
    window.hwnd_=0;Neutral(Read(window),9);Calls({1});window.hwnd_=123;
    window.closing_=true;Neutral(Read(window),9);Calls({1});window.closing_=false;
    queries.thread=99;Neutral(Read(window),0);Calls({1});queries.thread=17;
    queries.cursorOk=false;Neutral(Read(window),9);Calls({1,2});queries.cursorOk=true;
    queries.conversionOk=false;Neutral(Read(window),9);Calls({1,2,3});queries.conversionOk=true;
    queries.clientOk=false;Neutral(Read(window),9);Calls({1,2,3,4});queries.clientOk=true;
    for(const auto size:{POINT{0,1080},POINT{1920,0},POINT{-1,1080},POINT{1920,-1}}){queries.client.right=size.x;queries.client.bottom=size.y;Neutral(Read(window),9);Calls({1,2,3,4});}
    queries={};
    for(const auto point:{POINT{99,50},POINT{100,49},POINT{2020,50},POINT{100,1130},POINT{-2000,-2000}}){queries.cursor=point;Neutral(Read(window),9);Calls({1,2,3,4});}
    queries={};queries.client={0,0,800,800};queries.origin={0,0};queries.cursor={400,400};
    event=Read(window);Check(event.logicalX==960 && event.logicalY==540,"Letterboxed pointer did not use the existing logical mapping");
    queries.cursor={400,174};Neutral(Read(window),9);queries.cursor={400,625};Neutral(Read(window),9);
    queries={};queries.origin={-1920,-100};queries.cursor={-960,440};
    event=Read(window);Check(event.logicalX==960 && event.logicalY==540,"Negative monitor origin was treated as an invalid client coordinate");
}
static void LiveScene(){
    auto window=Window();queries={};
    window.hits_.push_back({45,{399,349,401,351}});
    auto event=Read(window);Check(event.controlKey==45 && event.sceneGeneration==9,"Snapshot missed committed UI hit geometry");
    window.hits_.push_back({0x300001005ull,{399,349,401,351}});
    event=Read(window);Check(event.controlKey==0x300001005ull,"Snapshot changed reverse hit priority or truncated its key");
    window.hits_.back().controlKey=0;
    event=Read(window);Check(event.controlKey==0 && event.logicalX==400 && event.logicalY==350,"A key-zero committed hit erased valid coordinates");
    window.hits_.clear();window.pixelHits_.keys={0x400000003ull};window.pixelHits_.indices.assign(1920*1080,0);window.pixelHits_.indices[350*1920+400]=1;
    event=Read(window);Check(event.controlKey==0x400000003ull,"Snapshot bypassed the existing pixel hit map");
    window.hits_.push_back({71,{399,349,401,351}});
    event=Read(window);Check(event.controlKey==71,"Pixel hit incorrectly overrode an explicit committed hit");
    window.pixelHits_={};window.hits_.clear();window.sceneGeneration_=10;
    event=Read(window);Check(event.sceneGeneration==10 && event.controlKey==0 && event.logicalX==400 && event.logicalY==350,"Stationary pointer reused a queued old-generation snapshot after a panel change");
    window.productionPointerInputEnabled_=false;Neutral(Read(window),10);
    window.productionPointerInputEnabled_=true;window.sceneGeneration_=11;window.hits_.push_back({99,{399,349,401,351}});
    event=Read(window);Check(event.sceneGeneration==11 && event.controlKey==99 && event.logicalX==400 && event.logicalY==350,"Stationary pointer was not resampled on replay reentry without WM_MOUSEMOVE");
}
static void MappingGrid(){
    auto window=Window();
    const std::vector<POINT> sizes={{1920,1080},{1280,720},{2560,1440},{800,800},{3440,1440},{1080,1920},{1,1},{640,480},{3840,2160}};
    for(const auto size:sizes)for(int sx=0;sx<17;++sx)for(int sy=0;sy<17;++sy){
        queries={};queries.client={0,0,size.x,size.y};queries.origin={-320,170};
        const auto x=static_cast<std::int32_t>(static_cast<std::int64_t>(size.x)*sx/16),y=static_cast<std::int32_t>(static_cast<std::int64_t>(size.y)*sy/16);
        queries.cursor={x+queries.origin.x,y+queries.origin.y};
        const auto event=Read(window);Calls({1,2,3,4});
        // Independent centered 16:9 display oracle, with the existing float
        // display edges retained before mapping client integer coordinates.
        const long double scale=(std::min)(static_cast<long double>(size.x)/1920,static_cast<long double>(size.y)/1080);
        const float left=static_cast<float>((size.x-1920*scale)/2),top=static_cast<float>((size.y-1080*scale)/2);
        const float right=static_cast<float>(left+1920*scale),bottom=static_cast<float>(top+1080*scale);
        if(x<left || y<top || x>=right || y>=bottom)Neutral(event,9);
        else {const long double lx=(x-left)*1920.0L/(right-left),ly=(y-top)*1080.0L/(bottom-top);
            Check(event.controlKey==0 && event.sceneGeneration==9 && std::fabs(event.logicalX-lx)<.001L && std::fabs(event.logicalY-ly)<.001L,
                "Physical pointer/client conversion differs from the independent display oracle");}
    }
}
int main(){try{
    static_assert(std::is_same<decltype(&BitmapWindow::CurrentPointerInput),BitmapInputEvent(BitmapWindow::*)() const>::value,"Current pointer snapshot lost const by-value API");
    Failures();LiveScene();MappingGrid();
    std::printf("{\"status\":\"PASS_PRODUCTION_CURRENT_POINTER_WITH_FAKE_QUERIES\",\"checks\":%u,\"samples\":%u,\"mapping_client_sizes\":9,\"stationary_reentry\":true,\"queue_and_capture_unchanged\":true,\"native_api_executed\":false}\n",checks,samples);
    return 0;
}catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}}
