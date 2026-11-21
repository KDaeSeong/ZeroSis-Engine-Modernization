#include "OriginalReflectionProjectionModel.h"
#include <cstdio>
#include <cstdlib>
#include <limits>

namespace R=ZeroSisPresentation::OriginalReflectionProjection;
namespace {
unsigned checks=0;
void Check(bool value){++checks;if(!value)std::abort();}
void Near(float a,float b,float tolerance=0.00001f){Check(std::isfinite(a)&&std::isfinite(b)&&std::abs(a-b)<=tolerance);}
template<class F> void Reject(F action){bool rejected=false;try{action();}catch(const std::invalid_argument&){rejected=true;}Check(rejected);}
R::WorldAdapter Adapter(){return {{{100,0,0,0,0,0,100,0,0,-100,0,0,10,20,30,1}},true};}
}
int main(){
    Check(!R::WorldCameraCalibrationVerified&&!R::OriginalClipPlaneVerified&&!R::IndexedViewAdjustmentVerified);
    Reject([]{R::Build({});});
    R::FrameInputs inputs{{-100,-50,-10},{100,50,10},{0,0,1},true};
    const auto base=R::Build(inputs);
    Near(base.center.x,0);Near(base.center.y,0);Near(base.center.z,0);Near(base.eye.z,-5000);
    Near(base.signedHalfSpan.x,-100);Near(base.signedHalfSpan.y,-50);
    // An axial analytic camera maps X to -X and keeps Y. The center has a
    // negative view depth; reversed near/far must produce the stated depth.
    const auto center=R::Transform({0,0,0,1},base.viewProjection);
    Near(center.x,0);Near(center.y,0);Near(center.z,5.0f/12.0f);Near(center.w,1);
    const auto left=R::WaterTexturePoint({100,0,0},base.viewProjection);
    Near(left.u,-1);Near(left.v,-0.5f);
    const auto right=R::WaterTexturePoint({-100,0,0},base.viewProjection);
    Near(right.u,0);Near(right.v,-0.5f);
    Near(R::WaterTexturePoint({0,50,0},base.viewProjection).v,-1);
    Near(R::WaterTexturePoint({0,-50,0},base.viewProjection).v,0);
    Near(R::Transform({0,0,-30000,1},base.projection).z,0);
    Near(R::Transform({0,0,30000,1},base.projection).z,1);
    auto obliqueInputs=inputs;obliqueInputs.axis={0.6f,0,0.8f};
    const auto oblique=R::Build(obliqueInputs);
    const auto obliqueUV=R::WaterTexturePoint({100,50,10},oblique.viewProjection);
    Near(obliqueUV.u,-0.87f);Near(obliqueUV.v,-1);
    obliqueInputs.axis={0,0,2};const auto doubled=R::Build(obliqueInputs);
    Near(doubled.eye.z,-10000);Near(R::Transform({0,0,0,1},doubled.viewProjection).z,1.0f/3.0f);
    // The shared consumer helper also retains W division for explicit
    // perspective adapters; the recovered base-view camera itself is ortho.
    R::Matrix perspective{{1,0,0,0.5f,0,1,0,0,0,0,1,0,0,0,0,1}};
    const auto divided=R::WaterTexturePoint({2,1,0},perspective);
    Near(divided.u,0);Near(divided.v,-0.75f);
    // Translating bounds and all tested positions leaves projection invariant.
    inputs.minimum={-63,-71,-1};inputs.maximum={137,29,19};
    const auto translated=R::Build(inputs);
    Near(translated.center.x,37);Near(translated.center.y,-21);Near(translated.center.z,9);
    for(int x=-2;x<=2;++x)for(int y=-2;y<=2;++y){
        const R::Vector p{static_cast<float>(x)*30,static_cast<float>(y)*17,3};
        const auto a=R::WaterTexturePoint(p,base.viewProjection);
        const auto b=R::WaterTexturePoint({p.x+37,p.y-21,p.z+9},translated.viewProjection);
        Near(a.u,b.u);Near(a.v,b.v);
    }
    // The producer and consumer must use the same supplied world adapter.
    const auto adapter=Adapter();R::Validate(adapter);
    const auto rawView=R::ForCurrentWorld(adapter,translated.view);
    const auto rawVP=R::Multiply(rawView,translated.projection);
    const auto consumerVP=R::ForCurrentWorld(adapter,translated.viewProjection);
    for(unsigned i=0;i<16;++i)Near(rawVP[i],consumerVP[i],0.00002f);
    for(int i=-3;i<=3;++i){
        const R::Vector current{static_cast<float>(i)*0.31f,0.2f,-0.17f};
        const auto original=R::Transform({current.x,current.y,current.z,1},adapter.currentToOriginal);
        const auto a=R::WaterTexturePoint({original.x,original.y,original.z},translated.viewProjection);
        const auto b=R::WaterTexturePointCurrent(current,adapter,translated);
        Near(a.u,b.u);Near(a.v,b.v);
        const auto producer=R::Transform({current.x,current.y,current.z,1},rawVP);
        Near(b.u,producer.x/producer.w*0.5f-0.5f);Near(b.v,-producer.y/producer.w*0.5f-0.5f);
    }
    // Clip conversion is algebraic and explicit, not a claim about the retail
    // waterline. Check signed half-spaces rather than only plane incidence.
    const R::Plane originalPlane{{0,0,1},-53};
    const auto currentPlane=R::ToCurrentPlane(adapter,originalPlane);
    Near(currentPlane.normal.x,0);Near(currentPlane.normal.y,100);Near(currentPlane.normal.z,0);Near(currentPlane.constant,-23);
    for(int i=-2;i<=2;++i){
        const R::Vector point{0,static_cast<float>(i),0};
        const auto p=R::Transform({point.x,point.y,point.z,1},adapter.currentToOriginal);
        Near(R::PlaneValue(point,currentPlane),R::PlaneValue({p.x,p.y,p.z},originalPlane));
    }
    R::FrameInputs bad=inputs;bad.supplied=false;Reject([&]{R::Build(bad);});
    bad=inputs;bad.maximum.x=bad.minimum.x;Reject([&]{R::Build(bad);});
    bad=inputs;bad.minimum.z=bad.maximum.z+1;Reject([&]{R::Build(bad);});
    bad=inputs;bad.axis={0,0,0};Reject([&]{R::Build(bad);});
    bad=inputs;bad.axis={0,1,0};Reject([&]{R::Build(bad);});
    bad=inputs;bad.axis.x=std::numeric_limits<float>::quiet_NaN();Reject([&]{R::Build(bad);});
    bad=inputs;bad.minimum.x=-std::numeric_limits<float>::max();bad.maximum.x=std::numeric_limits<float>::max();Reject([&]{R::Build(bad);});
    R::WorldAdapter badAdapter=adapter;badAdapter.supplied=false;Reject([&]{R::Validate(badAdapter);});
    badAdapter=adapter;badAdapter.currentToOriginal[15]=0;Reject([&]{R::Validate(badAdapter);});
    badAdapter=adapter;badAdapter.currentToOriginal[0]=0;Reject([&]{R::Validate(badAdapter);});
    Reject([&]{R::ToCurrentPlane(adapter,{});});
    auto zeroW=base.viewProjection;zeroW[15]=0;Reject([&]{R::WaterTexturePoint({},zeroW);});
    std::printf("PASS_ORIGINAL_REFLECTION_PROJECTION checks=%u native_graphics_calls=0\n",checks);return 0;
}
