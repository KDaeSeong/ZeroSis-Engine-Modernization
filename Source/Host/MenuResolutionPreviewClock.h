#pragma once
#include <cstdint>
#include <stdexcept>

namespace ZeroSisHost {
// Anchor after display application returns. Frame/animation time measured before
// that point must not consume the newly created confirmation interval.
class MenuResolutionPreviewClock final {
public:
    void Start(std::uint64_t now) noexcept {active_=true;last_=now;}
    void Stop() noexcept {active_=false;}
    bool Sample(std::uint64_t now,bool previewActive,double* seconds){
        if(!seconds)throw std::invalid_argument("Resolution preview clock needs an elapsed output");
        *seconds=0;
        if(!previewActive){Stop();return false;}
        if(!active_){Start(now);return false;}
        if(now<last_)throw std::logic_error("Resolution preview clock moved backwards");
        const auto elapsed=now-last_;last_=now;*seconds=static_cast<double>(elapsed)/1000.0;
        return elapsed!=0;
    }
    bool Active() const noexcept{return active_;}
private:
    bool active_=false;std::uint64_t last_=0;
};
}
