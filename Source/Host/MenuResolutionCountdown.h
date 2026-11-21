#pragma once
#include <cmath>
#include <stdexcept>

namespace ZeroSisHost {
// Transient timer only. The owner performs actual display confirm/reject and
// persistence. No option fields, settings schema, window or SDK are accessed.
class MenuResolutionCountdown final {
public:
    void Start() noexcept {
        active_=true;remaining_=20;elapsed_=0;displaySeconds_=20;
    }
    // True only on the active-to-expired transition. Preserve source subtraction
    // order and the complete elapsed delta; a stalled owner must expire at once.
    bool Advance(double seconds){
        if(!std::isfinite(seconds) || seconds<0)
            throw std::invalid_argument("Resolution countdown delta must be finite and nonnegative");
        if(!active_)return false;
        displaySeconds_=20;remaining_-=seconds;elapsed_+=seconds;
        if(remaining_<=0){active_=false;return true;}
        // Original OnUpdate prints %i(g_fTimer+1). At zero elapsed it prints21,
        // unlike ceil(remaining); all active remaining values are positive.
        displaySeconds_=static_cast<int>(std::floor(remaining_+1));return false;
    }
    bool Stop() noexcept {const bool wasActive=active_;active_=false;return wasActive;}
    bool Active() const noexcept{return active_;}
    double Remaining() const noexcept{return remaining_;}
    double Elapsed() const noexcept{return elapsed_;}
    int DisplaySeconds() const noexcept{return displaySeconds_;}
private:
    bool active_=false;double remaining_=20,elapsed_=0;int displaySeconds_=20;
};
}
