#pragma once
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace ZeroSisHost {
namespace MenuReplayScrollDetail {
inline double Unit(double value){
    if(!std::isfinite(value))throw std::invalid_argument("Replay scroll fraction is not finite");
    return (std::max)(0.0,(std::min)(1.0,value));
}
}
struct MenuReplayScrollGeometry final {
    double trackOrigin=0,trackLength=0,thumbLength=0,thumbOrigin=0,travel=0,fraction=0;
    static MenuReplayScrollGeometry Create(double origin,double length,double thumb,double unit){
        if(!std::isfinite(origin) || !std::isfinite(length) || !std::isfinite(thumb) || length<0 || thumb<0 || thumb>length ||
           !std::isfinite(origin+length) || (length>0 && origin+length<=origin))
            throw std::invalid_argument("Replay scroll geometry is not finite and representable");
        MenuReplayScrollGeometry result;result.trackOrigin=origin;result.trackLength=length;result.thumbLength=thumb;
        result.travel=length-thumb;result.fraction=MenuReplayScrollDetail::Unit(unit);
        result.thumbOrigin=origin+result.travel*result.fraction;
        if(!std::isfinite(result.thumbOrigin+thumb) || (result.travel>0 && origin+result.travel<=origin))
            throw std::invalid_argument("Replay scroll travel is not representable");
        return result;
    }
    bool Movable() const noexcept{return travel>0;}
    bool ContainsThumb(double coordinate) const noexcept {
        return coordinate>=thumbOrigin && coordinate<thumbOrigin+thumbLength;
    }
    bool SameDimensions(const MenuReplayScrollGeometry& other) const noexcept {
        return trackOrigin==other.trackOrigin && trackLength==other.trackLength && thumbLength==other.thumbLength;
    }
    double FractionAt(double coordinate,double grabOffset) const {
        if(!std::isfinite(coordinate) || !std::isfinite(grabOffset) || grabOffset<0 || grabOffset>thumbLength)
            throw std::invalid_argument("Replay scroll pointer/grab is outside its finite bounds");
        if(!Movable())return fraction;
        const double first=trackOrigin+grabOffset,last=first+travel;
        if(coordinate<=first)return 0;if(coordinate>=last)return 1;
        return MenuReplayScrollDetail::Unit((coordinate-first)/travel);
    }
};
struct MenuReplayScrollResult final {
    bool handled=false,preserveCurrent=false,began=false,ended=false;double fraction=0;
};
// One gesture belongs to one window's monotonic physical-press ID sequence.
// Zero-ID events remain usable for legacy synthetic component input only.
class MenuReplayScrollGesture final {
public:
    bool Active() const noexcept{return active_;}
    std::uint64_t PressId() const noexcept{return active_?pressId_:0;}
    bool Cancel() noexcept {
        const bool previous=active_;if(active_)Retire(pressId_);active_=false;pressId_=0;return previous;
    }
    MenuReplayScrollResult Drag(const MenuReplayScrollGeometry& geometry,std::uint64_t pressId,
        double originCoordinate,double currentCoordinate){
        if(!std::isfinite(originCoordinate) || !std::isfinite(currentCoordinate) || Stale(pressId))return Ignore(geometry);
        if(!geometry.Movable()){
            auto result=Ignore(geometry);result.handled=result.preserveCurrent=true;result.ended=Cancel();Retire(pressId);return result;
        }
        if(active_ && pressId_==pressId && !geometry_.SameDimensions(geometry)){
            auto result=Ignore(geometry);result.handled=result.preserveCurrent=true;result.ended=Cancel();return result;
        }
        bool began=false;
        if(!active_ || pressId_!=pressId){
            if(active_)Retire(pressId_);
            active_=true;pressId_=pressId;geometry_=geometry;originCoordinate_=previousCoordinate_=originCoordinate;
            insideThumb_=geometry.ContainsThumb(originCoordinate);
            grabOffset_=insideThumb_?originCoordinate-geometry.thumbOrigin:geometry.thumbLength*.5;began=true;
        }
        auto result=Position(geometry,currentCoordinate);
        result.began=began;result.preserveCurrent=currentCoordinate==previousCoordinate_ && (!began || insideThumb_);
        previousCoordinate_=currentCoordinate;return result;
    }
    MenuReplayScrollResult Release(const MenuReplayScrollGeometry& geometry,std::uint64_t pressId,double coordinate){
        if(!std::isfinite(coordinate) || Stale(pressId) || (active_ && pressId_!=pressId))return Ignore(geometry);
        if(active_){
            if(!geometry_.SameDimensions(geometry)){
                auto result=Ignore(geometry);result.handled=result.preserveCurrent=true;result.ended=Cancel();return result;
            }
            auto result=Position(geometry,coordinate);result.preserveCurrent=coordinate==previousCoordinate_;result.ended=Cancel();return result;
        }
        auto result=Ignore(geometry);result.handled=true;Retire(pressId);
        if(!geometry.Movable() || geometry.ContainsThumb(coordinate)){result.preserveCurrent=true;return result;}
        result.fraction=geometry.FractionAt(coordinate,geometry.thumbLength*.5);return result;
    }
private:
    static MenuReplayScrollResult Ignore(const MenuReplayScrollGeometry& geometry){
        MenuReplayScrollResult result;result.fraction=geometry.fraction;return result;
    }
    bool Stale(std::uint64_t id) const noexcept {
        return id && (id<=finishedThrough_ || (active_ && pressId_ && id<pressId_));
    }
    void Retire(std::uint64_t id) noexcept {if(id>finishedThrough_)finishedThrough_=id;}
    MenuReplayScrollResult Position(const MenuReplayScrollGeometry&,double coordinate) const {
        MenuReplayScrollResult result;result.handled=true;
        result.fraction=insideThumb_ && coordinate==originCoordinate_?geometry_.fraction:geometry_.FractionAt(coordinate,grabOffset_);return result;
    }
    MenuReplayScrollGeometry geometry_{};std::uint64_t pressId_=0,finishedThrough_=0;
    double originCoordinate_=0,previousCoordinate_=0,grabOffset_=0;bool active_=false,insideThumb_=false;
};
class MenuReplayScrollModel final {
public:
    // Exact ReplayViewer.lua OnTurnSliderValueChanged floor policy. The host
    // supplies a clamped slider fraction; no epsilon or nearest rounding.
    static int SourceFloor(double unit,int initial,int final){
        if(final<initial)throw std::invalid_argument("Replay turn interval is reversed");
        const auto span=static_cast<std::int64_t>(final)-initial;
        const auto step=static_cast<std::int64_t>(std::floor(MenuReplayScrollDetail::Unit(unit)*static_cast<double>(span)));
        return static_cast<int>(static_cast<std::int64_t>(initial)+step);
    }
    static double FloatContinuous(double unit,double maximum){
        if(!std::isfinite(maximum) || maximum<0)throw std::invalid_argument("Replay scroll extent is invalid");
        return MenuReplayScrollDetail::Unit(unit)*maximum;
    }
    static double Fraction(double offset,double maximum){
        if(!std::isfinite(offset) || !std::isfinite(maximum) || maximum<0)throw std::invalid_argument("Replay scroll offset/extent is invalid");
        if(maximum==0 || offset<=0)return 0;if(offset>=maximum)return 1;return offset/maximum;
    }
    // ReplayViewer.xml:224 TurnSlider WheelSteps="10".
    static constexpr float OriginalTurnSliderWheelSteps=10.0f;
    // Retail SliderControl WM_MOUSEWHEEL (CivilizationV_DX11.exe 005e0832):
    // one step per message, float32 1.0f/(100.0f/WheelSteps); HIWORD(wParam)>0
    // subtracts, otherwise adds. The store 007af7c0 clamps with 0>v -> +0 and
    // v>1 -> 1 before the slider callback runs. Each float operation is kept
    // separate so no compiler mode may fuse or reassociate it.
    static float WheelValue(float stored,float wheelSteps,bool positiveWheelDelta){
        if(!std::isfinite(stored) || !std::isfinite(wheelSteps) || !(wheelSteps>0))
            throw std::invalid_argument("Replay slider wheel state is not finite");
        volatile float divisor=100.0f;divisor=divisor/wheelSteps;
        volatile float step=1.0f;step=step/divisor;
        volatile float value=stored;
        if(positiveWheelDelta)value=value-step;else value=step+value;
        const float moved=value;
        return 0.0f>moved?0.0f:moved>1.0f?1.0f:moved;
    }
    // ReplayViewer.lua re-seeds TurnSlider with SetValue((turn-initial)/
    // (final-initial)) on every draw (SliderControl::SetValue stores a clamped
    // float without the callback). A wheel message therefore starts from that
    // float and OnTurnSliderValueChanged applies SourceFloor to the result.
    static int WheelTurn(int turn,int initial,int final,float wheelSteps,bool positiveWheelDelta){
        if(final<initial || turn<initial || turn>final)throw std::invalid_argument("Replay wheel turn escaped its recorded interval");
        const auto stored=static_cast<float>(Fraction(static_cast<double>(turn)-initial,static_cast<double>(final)-initial));
        return SourceFloor(static_cast<double>(WheelValue(stored,wheelSteps,positiveWheelDelta)),initial,final);
    }
};
}
