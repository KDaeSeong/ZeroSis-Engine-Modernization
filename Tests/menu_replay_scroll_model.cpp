// Actual pure geometry/gesture/queue policies, independent of a window/SDK.
#include "MenuReplayScrollModel.h"
#include "BitmapPointerPress.h"
#include <array>
#include <cstring>
#include <cstdio>
#include <limits>
#include <vector>

using namespace ZeroSisHost;
using namespace ZeroSisPresentation;
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
static bool Near(double a,double b){return std::abs(a-b)<1e-10;}
struct FloorCase final {std::uint64_t bits;int initial,final,expected;};
#include "replay_scroll_stock_goldens.inc"
struct WheelCase final {int turn,initial,final,positive,expected;std::uint32_t valueBits;};
#include "replay_scroll_wheel_goldens.inc"
static double Number(std::uint64_t bits){double result=0;std::memcpy(&result,&bits,sizeof(result));return result;}
static std::uint32_t Bits(float value){std::uint32_t result=0;std::memcpy(&result,&value,sizeof(result));return result;}
static void OriginalWheel(){
    using Model=MenuReplayScrollModel;const float steps=Model::OriginalTurnSliderWheelSteps;
    Check(steps==SourceTurnSliderWheelSteps,"Engine TurnSlider WheelSteps differs from the original XML");
    for(const auto& row:StockWheelGoldens){
        const auto stored=static_cast<float>(Model::Fraction(static_cast<double>(row.turn)-row.initial,static_cast<double>(row.final)-row.initial));
        Check(Bits(Model::WheelValue(stored,steps,row.positive!=0))==row.valueBits,"Wheel binary32 step/clamp differs from retail instruction order");
        Check(Model::WheelTurn(row.turn,row.initial,row.final,steps,row.positive!=0)==row.expected,"Wheel turn differs from original slider callback");
    }
    // ReplayViewer 7..9: forward floors back to the same turn, backward moves one.
    Check(Model::WheelTurn(7,7,9,steps,false)==7 && Model::WheelTurn(8,7,9,steps,false)==8 && Model::WheelTurn(9,7,9,steps,false)==9,"Short replay forward wheel was repaired or overran");
    Check(Model::WheelTurn(9,7,9,steps,true)==8 && Model::WheelTurn(8,7,9,steps,true)==7 && Model::WheelTurn(7,7,9,steps,true)==7,"Short replay backward wheel differs");
    Check(Model::WheelTurn(0,0,100,steps,false)==10 && Model::WheelTurn(100,0,100,steps,true)==89,"Ten percent binary32 wheel step changed");
    Check(Model::WheelTurn(9,9,9,steps,false)==9 && Model::WheelTurn(9,9,9,steps,true)==9,"Single-turn replay wheel escaped its turn");
    const float zero=Model::WheelValue(0,steps,true),one=Model::WheelValue(1,steps,false);
    Check(Bits(zero)==0 && one==1.0f,"Retail clamp did not store +0 and 1");
    unsigned rejected=0;
    try{Model::WheelTurn(10,0,9,steps,true);}catch(const std::invalid_argument&){++rejected;}
    try{Model::WheelTurn(0,1,0,steps,true);}catch(const std::invalid_argument&){++rejected;}
    try{Model::WheelValue((std::numeric_limits<float>::quiet_NaN)(),steps,true);}catch(const std::invalid_argument&){++rejected;}
    try{Model::WheelValue(.5f,0,true);}catch(const std::invalid_argument&){++rejected;}
    Check(rejected==4,"Invalid wheel state was manufactured into a turn");
}
static void SourceCallback(){
    for(const auto& row:StockFloorGoldens)
        Check(MenuReplayScrollModel::SourceFloor(Number(row.bits),row.initial,row.final)==row.expected,"Original Lua floor callback changed");
    Check(MenuReplayScrollModel::SourceFloor(.6,7,9)==8,"Map selection still rounds to nearest instead of source floor");
    Check(MenuReplayScrollModel::SourceFloor(0,(std::numeric_limits<int>::min)(),(std::numeric_limits<int>::max)())==(std::numeric_limits<int>::min)(),"Full int32 lower endpoint overflow");
    Check(MenuReplayScrollModel::SourceFloor(1,(std::numeric_limits<int>::min)(),(std::numeric_limits<int>::max)())==(std::numeric_limits<int>::max)(),"Full int32 upper endpoint overflow");
    Check(MenuReplayScrollModel::SourceFloor(-1,2,7)==2 && MenuReplayScrollModel::SourceFloor(2,2,7)==7,"Host unit clamping escaped recorded turns");
}
static void GeometryInverse(){
    // First two records are exact authored map/messages geometry. Other
    // dimensions verify that the model has no prototype 14/18/32 constants.
    const double tracks[][3]={{710,500,32},{373,369,18},{373,344,256.3137254901961},{-10,111,17.5},{4.25,27.75,0},{5,18,18},{0,0,0}};
    std::uint64_t id=0;
    for(const auto& track:tracks)for(const double unit:{0.0,.01,.29,.5,.75,.99,1.0}){
        const auto geometry=MenuReplayScrollGeometry::Create(track[0],track[1],track[2],unit);
        Check(std::isfinite(geometry.thumbOrigin) && geometry.thumbOrigin>=geometry.trackOrigin && geometry.thumbOrigin+geometry.thumbLength<=geometry.trackOrigin+geometry.trackLength+1e-10,"Shuttle escaped authored track");
        Check(geometry.travel==track[1]-track[2],"Shuttle travel uses whole track length");
        for(const double grip:{0.0,.25,.5,.999}){
            const auto pointer=geometry.thumbOrigin+geometry.thumbLength*grip;
            Check(Near(geometry.FractionAt(pointer,geometry.thumbLength*grip),unit),"Track/shuttle forward and inverse geometry differ");
            MenuReplayScrollGesture gesture;
            const double physical=static_cast<float>(pointer); // Native metadata is float.
            const auto down=gesture.Drag(geometry,++id,physical,physical);
            if(geometry.Movable() && geometry.thumbLength>0 && geometry.ContainsThumb(physical)){
                Check(down.handled && down.began && down.preserveCurrent && down.fraction==unit && gesture.Active(),"Unmoved physical thumb press changed its existing value");
                const auto up=gesture.Release(geometry,id,physical);
                Check(up.handled && up.ended && up.preserveCurrent && !gesture.Active(),"Unmoved release re-quantized the value or kept capture");
            }else Check(down.handled && (geometry.Movable() || (down.preserveCurrent && !gesture.Active())),"Nonmoving/point-thumb track was not handled");
        }
        if(geometry.Movable()){
            Check(geometry.FractionAt(-(std::numeric_limits<double>::max)(),0)==0 && geometry.FractionAt((std::numeric_limits<double>::max)(),geometry.thumbLength)==1,"Finite out-of-track pointer did not clamp to endpoints");
        }
    }
}
static void FloorBoundaryGrip(){
    // k/span can round down again through source floor. An unchanged physical
    // grip must retain the existing k, without changing the source floor rule.
    std::uint64_t press=0;unsigned lowerAgain=0;
    for(int span=2;span<300;++span)for(int k=0;k<=span;++k){
        const auto unit=double(k)/span;const auto geometry=MenuReplayScrollGeometry::Create(710,500,32,unit);
        MenuReplayScrollGesture gesture;const double origin=static_cast<float>(geometry.thumbOrigin+16);
        const auto result=gesture.Drag(geometry,++press,origin,origin);
        Check(result.preserveCurrent && result.fraction==unit,"First thumb grab perturbed a fractional floor boundary");
        const int selected=result.preserveCurrent?k:MenuReplayScrollModel::SourceFloor(result.fraction,0,span);
        Check(selected==k,"Unchanged thumb changed recorded turn near a floor boundary");
        if(MenuReplayScrollModel::SourceFloor(unit,0,span)<k)++lowerAgain;
    }
    Check(lowerAgain>0,"Fixture did not exercise actual double floor roundtrip boundaries");
}
struct Event final {
    enum class Kind {ControlDrag,ControlClick};Kind kind=Kind::ControlDrag;
    std::uint64_t controlKey=9,sceneGeneration=3,pointerPressId=0;
    float logicalY=0,pointerPressX=0,pointerPressY=0;
};
static Event Move(const BitmapPointerPress& press,float coordinate){Event result;result.logicalY=coordinate;StampBitmapPointerPress(result,press);return result;}
static void NativeOrderAndCoalescing(){
    std::uint64_t sequence=0;BitmapPointerPress press;MenuReplayScrollGesture gesture;bool overflow=false;
    auto geometry=MenuReplayScrollGeometry::Create(373,369,18,.25);
    const float origin=static_cast<float>(geometry.thumbOrigin+geometry.thumbLength*.25);
    Check(BeginBitmapPointerPress(press,sequence,true,3,9,0,origin),"Physical press setup failed");
    std::vector<Event> queue;QueueBitmapControlDrag(queue,Move(press,origin),4096,overflow);
    QueueBitmapControlDrag(queue,Move(press,origin+4),4096,overflow);QueueBitmapControlDrag(queue,Move(press,origin+12),4096,overflow);
    Check(queue.size()==1 && !overflow && queue[0].pointerPressY==origin,"Production coalescing lost the original down metadata");
    auto result=gesture.Drag(geometry,queue[0].pointerPressId,queue[0].pointerPressY,queue[0].logicalY);
    Check(result.began && !result.preserveCurrent && Near(result.fraction,.25+12/351.0),"First coalesced movement was discarded or used full track length");
    geometry=MenuReplayScrollGeometry::Create(373,369,18,result.fraction);
    auto again=gesture.Drag(geometry,sequence,99999,origin+12);
    Check(again.preserveCurrent && Near(again.fraction,result.fraction),"Same physical press re-anchored from changed metadata/current thumb");
    const auto late=gesture.Release(geometry,sequence+1,origin+12);
    Check(!late.handled && gesture.Active(),"Unrelated release ended a current physical press");
    const auto release=gesture.Release(geometry,sequence,origin+12);
    Check(release.ended && release.preserveCurrent && !gesture.Active(),"Native up did not end the captured gesture");
    Check(!gesture.Drag(geometry,sequence,origin,origin+20).handled,"Retired press resumed after its release");
    press={};Check(BeginBitmapPointerPress(press,sequence,true,3,9,0,static_cast<float>(geometry.thumbOrigin+4.5)),"New physical press failed");
    queue.clear();QueueBitmapControlDrag(queue,Move(press,press.pointerPressY-2),4096,overflow);
    const auto second=gesture.Drag(geometry,press.pointerPressId,queue[0].pointerPressY,queue[0].logicalY);
    Check(second.began && Near(second.fraction,result.fraction-2/351.0),"Another physical press reused the previous grip offset");
    Check(gesture.Cancel() && !gesture.Active(),"Capture loss did not cancel model state");
    Check(!gesture.Release(geometry,press.pointerPressId,0).handled && !gesture.Drag(geometry,press.pointerPressId,0,10).handled,"Cancelled physical press produced a late seek");
    const auto newGeometry=MenuReplayScrollGeometry::Create(373,369,32,.7);
    auto third=gesture.Drag(newGeometry,++sequence,newGeometry.thumbOrigin+16,newGeometry.thumbOrigin+16);
    Check(third.began && third.preserveCurrent,"New variable-shuttle gesture did not begin");
    const auto changed=MenuReplayScrollGeometry::Create(373,500,32,.7);
    auto resized=gesture.Drag(changed,sequence,newGeometry.thumbOrigin+16,newGeometry.thumbOrigin+17);
    Check(resized.ended && resized.preserveCurrent && !gesture.Active(),"Geometry change retained a stale travel/grab");
    Check(!gesture.Drag(changed,sequence,500,510).handled,"Same physical press restarted after geometry cancellation");
}
static void TrackClicksAndContinuous(){
    const auto geometry=MenuReplayScrollGeometry::Create(373,369,18,.5);
    MenuReplayScrollGesture gesture;
    auto inside=gesture.Release(geometry,1,geometry.thumbOrigin+9);
    Check(inside.handled && inside.preserveCurrent && inside.fraction==.5 && !gesture.Active(),"Release-only component click moved its current thumb");
    auto start=gesture.Release(geometry,2,geometry.trackOrigin);
    auto end=gesture.Release(geometry,3,geometry.trackOrigin+geometry.trackLength);
    Check(start.fraction==0 && end.fraction==1,"Track click endpoints do not use shuttle center/travel");
    for(const double maximum:{0.0,1.0,405.0,1000000000000.0,(std::numeric_limits<double>::max)()})
        for(const double unit:{0.0,.125,.5,.75,1.0}){
            const auto offset=MenuReplayScrollModel::FloatContinuous(unit,maximum);
            Check(std::isfinite(offset) && offset>=0 && offset<=maximum,"Continuous extent overflowed/clipped the source domain");
            Check(Near(MenuReplayScrollModel::Fraction(offset,maximum),maximum==0?0:unit),"Continuous messages were rounded to pages or lost fractional offset");
        }
    Check(MenuReplayScrollModel::FloatContinuous(.5,405)==202.5,"Messages still round to a discrete page");
    Check(MenuReplayScrollModel::Fraction(-1,405)==0 && MenuReplayScrollModel::Fraction(406,405)==1,"Continuous extent clamping changed");
    Check(MenuReplayScrollModel::SourceFloor(.5,9,9)==9 && MenuReplayScrollModel::Fraction(0,0)==0,"Single-turn/zero-scroll extent divided by zero");
    const auto whole=MenuReplayScrollGeometry::Create(0,18,18,0);auto zero=gesture.Drag(whole,4,9,100);
    Check(zero.handled && zero.preserveCurrent && !gesture.Active(),"Zero travel unexpectedly began a capture");
    const auto legacy=gesture.Drag(geometry,0,geometry.thumbOrigin+9,geometry.thumbOrigin+9);
    Check(legacy.handled && legacy.preserveCurrent && gesture.Release(geometry,0,geometry.thumbOrigin+9).ended,"Legacy zero-ID component input is incompatible");
}
static void Invalid(){
    unsigned rejected=0;
    for(const auto& args:std::vector<std::array<double,4>>{{0,-1,0,0},{0,1,2,0},{0,1,-1,0},{0,1,1,(std::numeric_limits<double>::infinity)()},
        {(std::numeric_limits<double>::max)(),500,32,0},{0,1,(std::numeric_limits<double>::quiet_NaN)(),0}}){
        try{MenuReplayScrollGeometry::Create(args[0],args[1],args[2],args[3]);}catch(const std::invalid_argument&){++rejected;}
    }
    Check(rejected==6,"Invalid/nonrepresentable geometry was accepted");
    const auto geometry=MenuReplayScrollGeometry::Create(0,500,32,.5);MenuReplayScrollGesture gesture;
    Check(!gesture.Drag(geometry,1,0,(std::numeric_limits<double>::quiet_NaN)()).handled && !gesture.Active(),"Nonfinite pointer mutated gesture state");
    const auto start=gesture.Drag(geometry,1,geometry.thumbOrigin+16,geometry.thumbOrigin+16);Check(start.began,"Finite setup failed");
    Check(!gesture.Release(geometry,1,(std::numeric_limits<double>::infinity)()).handled && gesture.Active(),"Nonfinite release mutated active gesture state");
    bool negative=false,reversed=false,nan=false;
    try{MenuReplayScrollModel::FloatContinuous(.5,-1);}catch(const std::invalid_argument&){negative=true;}
    try{MenuReplayScrollModel::SourceFloor(.5,2,1);}catch(const std::invalid_argument&){reversed=true;}
    try{MenuReplayScrollModel::SourceFloor((std::numeric_limits<double>::quiet_NaN)(),0,1);}catch(const std::invalid_argument&){nan=true;}
    Check(negative && reversed && nan,"Invalid source domains were manufactured into scroll values");
}
int main(){try{
    SourceCallback();OriginalWheel();GeometryInverse();FloorBoundaryGrip();NativeOrderAndCoalescing();TrackClicksAndContinuous();Invalid();
    std::printf("{\"status\":\"PASS_SDK_FREE_REPLAY_SCROLL_MODEL\",\"checks\":%u,\"source_lua_floor_goldens\":%zu,\"source_wheel_goldens\":%zu,\"production_pointer_policy_executed\":true,\"native_host_sdk_window_gpu_executed\":false}\n",
        checks,sizeof(StockFloorGoldens)/sizeof(StockFloorGoldens[0]),sizeof(StockWheelGoldens)/sizeof(StockWheelGoldens[0]));return 0;
}catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}}
