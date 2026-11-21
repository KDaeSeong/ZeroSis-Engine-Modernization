#pragma once
#include <string>

namespace ZeroSisHost {

// The caller keeps its owner clock fixed throughout this synchronous dispatch.
// A consumed pointer event need not change the retained visual snapshot.
struct UiPanelRepaint final {
    template<class DispatchFunction,class SnapshotFunction>
    static bool Dispatch(bool pointerMove,bool* frameChanged,
                         DispatchFunction&& dispatch,SnapshotFunction&& snapshot) {
        if(frameChanged)*frameChanged=false;
        if(!frameChanged)return dispatch();
        if(!pointerMove){
            const bool consumed=dispatch();
            *frameChanged=consumed;
            return consumed;
        }
        const std::string before=snapshot();
        const bool consumed=dispatch();
        const std::string after=snapshot();
        *frameChanged=consumed && before!=after;
        return consumed;
    }
};

} // namespace ZeroSisHost
