#pragma once
#include <cstdint>

namespace ZeroSisHost {
// Called only after the replay owner accepted the event. Continuous input does
// not change its page/modal selection, so later same-generation input must not
// disappear with the drained batch. Clicks and keys retain the commit boundary.
template<class Input> bool ContinueHandledMenuReplayInputBatch(const Input& input,
    std::uint64_t currentGeneration,std::uint64_t firstReplayKey) noexcept {
    using Kind=decltype(input.kind);
    if(!currentGeneration || input.sceneGeneration!=currentGeneration || !firstReplayKey)return false;
    // Pointer coordinates also belong to the replay owner over zero-key space
    // and the lifecycle Back button; accepting hover must not discard clicks.
    if(input.kind==Kind::PointerMove)return true;
    if(input.controlKey<firstReplayKey)return false;
    return input.kind==Kind::Scroll || input.kind==Kind::ControlDrag;
}
}
