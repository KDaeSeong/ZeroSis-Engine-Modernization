#pragma once
#include <cstdint>
#include <limits>
#include <vector>

namespace ZeroSisPresentation {
// Owner-thread metadata only. Cancelling a press never resets the window's
// sequence, so a later press cannot inherit an earlier queued drag's identity.
struct BitmapPointerPress final {
    bool active=false,uiHit=false;
    std::uint64_t generation=0,key=0,pointerPressId=0;
    float pointerPressX=0,pointerPressY=0;
};
inline bool BeginBitmapPointerPress(BitmapPointerPress& press,std::uint64_t& sequence,
    bool uiHit,std::uint64_t generation,std::uint64_t key,float x,float y) noexcept {
    if(press.active || sequence==(std::numeric_limits<std::uint64_t>::max)())return false;
    ++sequence;press.active=true;press.uiHit=uiHit;press.generation=generation;press.key=key;
    press.pointerPressId=sequence;press.pointerPressX=x;press.pointerPressY=y;return true;
}
template<class Event> inline void StampBitmapPointerPress(Event& event,const BitmapPointerPress& press) noexcept {
    event.pointerPressId=press.pointerPressId;event.pointerPressX=press.pointerPressX;event.pointerPressY=press.pointerPressY;
}
template<class Event> inline bool CanCoalesceBitmapControlDrag(const Event& previous,const Event& next) noexcept {
    using Kind=decltype(next.kind);
    return previous.kind==Kind::ControlDrag && next.kind==Kind::ControlDrag && next.pointerPressId!=0 &&
        previous.controlKey==next.controlKey && previous.sceneGeneration==next.sceneGeneration &&
        previous.pointerPressId==next.pointerPressId && previous.pointerPressX==next.pointerPressX && previous.pointerPressY==next.pointerPressY;
}
template<class Event> inline void QueueBitmapControlDrag(std::vector<Event>& pending,const Event& event,
    std::size_t maximum,bool& overflow) {
    if(!pending.empty() && CanCoalesceBitmapControlDrag(pending.back(),event)){pending.back()=event;return;}
    if(pending.size()>=maximum){overflow=true;return;}pending.push_back(event);
}
}
