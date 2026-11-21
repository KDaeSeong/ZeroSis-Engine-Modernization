// Execute production input policies without a window, replay SDK or renderer.
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include "BitmapWindow.h"
#include "BitmapKeyPolicy.h"
#include "MenuReplayInputBatch.h"
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <limits>
#include <set>
#include <stdexcept>

using namespace ZeroSisPresentation;
using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
static constexpr std::uint64_t Base=0x300000000ull,Messages=Base+0x104,Seek=Base+0x101;
static BitmapInputEvent Event(BitmapInputKind kind,std::uint64_t key,float delta=0,
    std::uint64_t generation=7){
    BitmapInputEvent value{};value.kind=kind;value.controlKey=key;value.scrollDelta=delta;
    value.sceneGeneration=generation;return value;
}
struct Outcome final {
    double offset=0,maximum=1000;unsigned accepted=0,drags=0,back=0,transitions=0,pointers=0;
    std::vector<std::uint64_t> presses;
};
static Outcome Dispatch(const std::vector<BitmapInputEvent>& events,double offset=0,double maximum=1000){
    Outcome result;result.offset=offset;result.maximum=maximum;
    for(const auto& input:events){
        if(input.sceneGeneration!=7)continue;
        bool handled=false;
        if(input.kind==BitmapInputKind::PointerMove){++result.pointers;handled=true;}
        else if(input.kind==BitmapInputKind::Scroll && input.controlKey==Messages &&
           std::isfinite(input.scrollDelta) && input.scrollDelta!=0){
            result.offset=(std::max)(0.0,(std::min)(result.maximum,result.offset+input.scrollDelta));handled=true;
        }else if(input.kind==BitmapInputKind::ControlDrag && input.controlKey==Seek && std::isfinite(input.logicalY)){
            result.offset=(std::max)(0.0,(std::min)(result.maximum,static_cast<double>(input.logicalY)));
            ++result.drags;result.presses.push_back(input.pointerPressId);handled=true;
        }else if((input.kind==BitmapInputKind::ControlClick && input.controlKey==Base+12) ||
                 (input.kind==BitmapInputKind::KeyDown && input.virtualKey==VK_END)){
            ++result.transitions;handled=true;
        }
        if(handled){
            ++result.accepted;
            if(ContinueHandledMenuReplayInputBatch(input,7,Base))continue;
            break;
        }
        if(input.kind==BitmapInputKind::ControlClick && input.controlKey==35){++result.back;break;}
    }
    return result;
}
static void BatchOrder(){
    const auto positive=Event(BitmapInputKind::Scroll,Messages,48),negative=Event(BitmapInputKind::Scroll,Messages,-48);
    auto result=Dispatch({positive,positive});
    Check(result.offset==96 && result.accepted==2,"Second same-generation wheel delta disappeared");
    result=Dispatch({positive,negative},90,100);
    Check(result.offset==52 && result.accepted==2,"Upper-clamped wheel events were combined or reordered");
    result=Dispatch({negative,positive},10,100);
    Check(result.offset==48 && result.accepted==2,"Lower-clamped wheel events were combined or reordered");
    result=Dispatch({positive,negative},50,1000);
    Check(result.offset==50 && result.accepted==2,"Opposing unclamped wheel events did not retain order");
    result=Dispatch({positive,positive,negative},990,1000);
    Check(result.offset==952 && result.accepted==3,"Clamping discarded later opposing wheel input");
    auto invalid=positive;invalid.sceneGeneration=6;
    auto future=positive;future.sceneGeneration=8;
    auto unowned=positive;unowned.controlKey=35;
    result=Dispatch({invalid,positive,future,unowned,positive});
    Check(result.offset==96 && result.accepted==2,"Stale/future generation or unowned key changed active scroll");
    invalid=positive;invalid.scrollDelta=std::numeric_limits<float>::quiet_NaN();
    result=Dispatch({positive,invalid,positive});
    Check(result.offset==96 && result.accepted==2,"Invalid owner-rejected scroll interrupted valid batch input");
    auto drag=Event(BitmapInputKind::ControlDrag,Seek);drag.logicalY=300;drag.pointerPressId=100;
    auto later=drag;later.logicalY=480;later.pointerPressId=101;
    result=Dispatch({positive,drag,negative,later,positive});
    Check(result.offset==528 && result.accepted==5 && result.drags==2 && result.presses==std::vector<std::uint64_t>{100,101},
        "Mixed continuous input lost order or physical press identity");
    const auto select=Event(BitmapInputKind::ControlClick,Base+12);
    result=Dispatch({positive,select,positive});
    Check(result.offset==48 && result.accepted==2 && result.transitions==1,"Selector click crossed its old-input commit boundary");
    auto key=Event(BitmapInputKind::KeyDown,0);key.virtualKey=VK_END;
    result=Dispatch({positive,key,positive});
    Check(result.offset==48 && result.accepted==2 && result.transitions==1,"Handled key crossed its old-input commit boundary");
    result=Dispatch({positive,Event(BitmapInputKind::ControlClick,35),positive});
    Check(result.offset==48 && result.accepted==1 && result.back==1,"Lifecycle Back crossed its old-input boundary");
    std::vector<BitmapInputEvent> bursts(4096,positive);result=Dispatch(bursts,0,1000000);
    Check(result.offset==4096*48 && result.accepted==4096,"A bounded full wheel queue lost valid deltas");
    const auto pointer=Event(BitmapInputKind::PointerMove,0),backPointer=Event(BitmapInputKind::PointerMove,35);
    result=Dispatch({pointer,positive,backPointer,Event(BitmapInputKind::ControlClick,35),positive});
    Check(result.offset==48 && result.pointers==2 && result.accepted==3 && result.back==1,
        "Accepted zero-key or Back hover discarded following wheel/click input");
    result=Dispatch({pointer,select,backPointer,positive});
    Check(result.pointers==1 && result.transitions==1 && result.accepted==2 && result.offset==0,
        "Pointer batching crossed the selector commit boundary");
}
static void OwnershipPolicy(){
    for(const auto kind:{BitmapInputKind::KeyDown,BitmapInputKind::ControlClick,BitmapInputKind::CloseRequest,
        BitmapInputKind::PointerMove,BitmapInputKind::Scroll,BitmapInputKind::ControlRightClick,BitmapInputKind::TextInput,
        BitmapInputKind::WorldWheel,BitmapInputKind::ControlDrag,static_cast<BitmapInputKind>(99)}){
        const bool continuous=kind==BitmapInputKind::Scroll || kind==BitmapInputKind::ControlDrag;
        for(const auto key:{0ull,35ull,Base-1,Base,Messages,(std::numeric_limits<std::uint64_t>::max)()}){
            for(const std::uint64_t generation:{0ull,6ull,7ull,8ull}){
                const auto value=Event(kind,key,48,generation);
                Check(ContinueHandledMenuReplayInputBatch(value,7,Base)==(generation==7 && (kind==BitmapInputKind::PointerMove || (continuous && key>=Base))),
                    "Batch owner/kind/generation admission policy changed");
                Check(!ContinueHandledMenuReplayInputBatch(value,0,Base),"Zero current generation admitted input");
                Check(!ContinueHandledMenuReplayInputBatch(value,7,0),"Missing replay owner namespace admitted input");
            }
        }
    }
}
static void KeyboardPolicy(){
    const std::set<std::uint32_t> expected={VK_TAB,VK_SPACE,VK_PRIOR,VK_NEXT,VK_END,VK_HOME,VK_LEFT,VK_UP,VK_RIGHT,VK_DOWN,VK_F5};
    Check(expected.size()==11,"Win32 key constants overlap unexpectedly");
    for(std::uint32_t key=0;key<1024;++key){
        Check(ShouldQueueBitmapGameplayNavigationKey(true,key)==(expected.count(key)!=0),"Gameplay navigation key policy disagrees with actual Win32 constants");
        Check(!ShouldQueueBitmapGameplayNavigationKey(false,key),"Disabled gameplay navigation queued a key");
    }
    Check(ShouldQueueBitmapGameplayNavigationKey(true,VK_HOME) && ShouldQueueBitmapGameplayNavigationKey(true,VK_END) &&
        ShouldQueueBitmapGameplayNavigationKey(true,VK_PRIOR) && ShouldQueueBitmapGameplayNavigationKey(true,VK_NEXT),
        "Replay Home End PageUp PageDown never reach the owner");
    Check(!ShouldQueueBitmapGameplayNavigationKey(true,VK_ESCAPE) && !ShouldQueueBitmapGameplayNavigationKey(true,VK_RETURN) &&
        !ShouldQueueBitmapGameplayNavigationKey(true,VK_BACK),"Escape Return or editor keys changed ownership");
    Check(!ShouldQueueBitmapGameplayNavigationKey(true,(std::numeric_limits<std::uint32_t>::max)()),"Unrecognized virtual key queued");
}
int main(){try{
    BatchOrder();OwnershipPolicy();KeyboardPolicy();
    std::printf("{\"status\":\"PASS_SDK_FREE_REPLAY_BATCH_AND_NATIVE_KEY_POLICY\",\"checks\":%u,\"sequential_wheel_boundaries\":true,\"physical_press_order_preserved\":true,\"native_key_route_policy_executed_without_hwnd\":true,\"native_execution\":false}\n",checks);
    return 0;
}catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}}
