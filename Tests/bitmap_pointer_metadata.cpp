// Runs production press identity/origin/coalescing functions without a window.
#define NOMINMAX
#define WIN32_LEAN_AND_MEAN
#include "BitmapWindow.h"
#include <cstddef>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <type_traits>

using namespace ZeroSisPresentation;
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
static BitmapInputEvent Drag(const BitmapPointerPress& press,float x,float y){
    BitmapInputEvent event{BitmapInputKind::ControlDrag,press.key,0,x,y,press.generation};
    StampBitmapPointerPress(event,press);return event;
}
static void AppendFields(){
    static_assert(std::is_standard_layout<BitmapInputEvent>::value,"Event must retain its standard aggregate layout");
    static_assert(offsetof(BitmapInputEvent,pointerPressId)>offsetof(BitmapInputEvent,wheelDelta),"Press metadata must be appended");
    BitmapInputEvent oldPrefix{BitmapInputKind::Scroll,71,72,73,74,75,76,77,78,79,80,81};
    Check(oldPrefix.wheelDelta==81 && oldPrefix.pointerPressId==0 && oldPrefix.pointerPressX==0 && oldPrefix.pointerPressY==0,"Existing aggregate initializer prefix changed");
    BitmapInputEvent oldSix{BitmapInputKind::ControlDrag,1,0,2,3,4};
    Check(oldSix.pointerPressId==0 && oldSix.pointerPressX==0 && oldSix.pointerPressY==0 && oldSix.scrollDelta==0,"Omitted appended fields are not default zero");
}
static void NativeOrder(){
    std::uint64_t sequence=0;BitmapPointerPress press;
    Check(BeginBitmapPointerPress(press,sequence,true,7,0x300000102ull,100,200),"Initial physical press did not begin");
    Check(sequence==1 && press.pointerPressId==1 && press.active && press.uiHit,"Initial press identity/domain changed");
    const auto snapshot=press;
    Check(!BeginBitmapPointerPress(press,sequence,false,8,3,999,999) && sequence==1 && press.pointerPressY==200,"Duplicate down consumed or replaced active press identity");
    std::vector<BitmapInputEvent> queued;bool overflow=false;
    QueueBitmapControlDrag(queued,Drag(press,100,200),4096,overflow); // Native down is a drag, not a click.
    QueueBitmapControlDrag(queued,Drag(press,103,231),4096,overflow);
    QueueBitmapControlDrag(queued,Drag(press,108,250),4096,overflow);
    Check(!overflow && queued.size()==1 && queued[0].logicalY==250 && queued[0].pointerPressY==200 && queued[0].pointerPressX==100,"Coalescing lost the real down point before the first drain");
    BitmapInputEvent release{BitmapInputKind::ControlClick,press.key,0,108,250,press.generation};StampBitmapPointerPress(release,snapshot);
    Check(release.pointerPressId==1 && release.pointerPressY==200 && release.logicalY==250,"Release lost its original press identity/origin");
    press={}; // Native up/cancel clears only the active record.
    Check(queued[0].pointerPressId==1 && queued[0].pointerPressY==200 && sequence==1,"Cancel changed queued snapshots or reset sequence");
    Check(BeginBitmapPointerPress(press,sequence,true,7,snapshot.key,500,600),"Second physical press did not begin");
    QueueBitmapControlDrag(queued,Drag(press,502,610),4096,overflow); // The prior release may have been filtered out.
    Check(queued.size()==2 && queued[0].pointerPressId==1 && queued[1].pointerPressId==2 && queued[1].pointerPressY==600,"Two physical presses merged when release was absent");
    queued.push_back(release);
    Check(queued.back().kind==BitmapInputKind::ControlClick && queued.back().pointerPressId==1,"A delayed old release was relabeled as a new press");
    BitmapPointerPress right;
    Check(BeginBitmapPointerPress(right,sequence,false,7,12,40,50) && right.pointerPressId==3 && !right.uiHit,"Two button domains did not share a unique window sequence");
    Check(press.pointerPressId==2 && press.pointerPressY==600,"Other button replaced an active origin");
}
static void CoalescingAndBounds(){
    BitmapPointerPress press;std::uint64_t sequence=0;Check(BeginBitmapPointerPress(press,sequence,true,17,9,5,6),"Queue setup failed");
    const auto first=Drag(press,10,11);auto other=Drag(press,20,21);
    Check(CanCoalesceBitmapControlDrag(first,other),"Same-press drag did not coalesce");
    other.controlKey=10;Check(!CanCoalesceBitmapControlDrag(first,other),"Different control key coalesced");
    other=first;other.sceneGeneration=18;Check(!CanCoalesceBitmapControlDrag(first,other),"Different input generation coalesced");
    other=first;other.pointerPressId=2;Check(!CanCoalesceBitmapControlDrag(first,other),"Different physical press coalesced");
    other=first;other.pointerPressY=7;Check(!CanCoalesceBitmapControlDrag(first,other),"Inconsistent origin coalesced");
    other=first;other.kind=BitmapInputKind::ControlClick;Check(!CanCoalesceBitmapControlDrag(other,other),"Release clicks coalesced as drags");
    other=first;other.pointerPressId=0;Check(!CanCoalesceBitmapControlDrag(other,other),"Unidentified legacy events were merged as one physical press");
    std::vector<BitmapInputEvent> queue(4096,first);bool overflow=false;
    auto latest=first;latest.logicalY=987;QueueBitmapControlDrag(queue,latest,4096,overflow);
    Check(queue.size()==4096 && !overflow && queue.back().logicalY==987,"A full queue could not replace its same-press tail");
    latest.pointerPressId=2;QueueBitmapControlDrag(queue,latest,4096,overflow);
    Check(queue.size()==4096 && overflow && queue.back().pointerPressId==1,"Queue overflow replaced a different physical press");
    queue.clear();overflow=false;QueueBitmapControlDrag(queue,first,0,overflow);Check(queue.empty() && overflow,"Zero queue capacity was not bounded");
    queue.clear();overflow=false;sequence=0;
    for(unsigned i=0;i<1024;++i){
        press={};Check(BeginBitmapPointerPress(press,sequence,true,22,9,float(i),float(i+10)),"Repeated cancel/press failed");
        QueueBitmapControlDrag(queue,Drag(press,float(i+1),float(i+11)),4096,overflow);
        QueueBitmapControlDrag(queue,Drag(press,float(i+2),float(i+12)),4096,overflow);
        Check(queue.size()==i+1 && queue.back().pointerPressId==static_cast<std::uint64_t>(i)+1 && queue.back().pointerPressY==float(i+10),"Cancelled physical presses merged or origin drifted");
    }
    Check(!overflow && sequence==1024,"Bounded press trace changed queue/sequence bounds");
}
static void Exhaustion(){
    std::uint64_t sequence=(std::numeric_limits<std::uint64_t>::max)()-1;BitmapPointerPress press;
    Check(BeginBitmapPointerPress(press,sequence,true,1,1,2,3) && press.pointerPressId==(std::numeric_limits<std::uint64_t>::max)(),"Final nonwrapping identity was not available");
    press={};Check(!BeginBitmapPointerPress(press,sequence,true,1,1,2,3) && !press.active && press.pointerPressId==0 && sequence==(std::numeric_limits<std::uint64_t>::max)(),"Exhausted identity wrapped or activated a press");
    Check(!BeginBitmapPointerPress(press,sequence,true,1,1,2,3) && sequence==(std::numeric_limits<std::uint64_t>::max)(),"Repeated exhausted identity wrapped");
}
int main(){try{
    AppendFields();NativeOrder();CoalescingAndBounds();Exhaustion();
    std::printf("{\"status\":\"PASS_SDK_FREE_BITMAP_POINTER_METADATA\",\"checks\":%u,\"production_pure_helper_executed\":true,\"hwnd_host_sdk_gpu_executed\":false}\n",checks);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}}
