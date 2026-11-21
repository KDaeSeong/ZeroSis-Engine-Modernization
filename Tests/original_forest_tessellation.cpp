#include "OriginalForestModel.h"
#include "OriginalTerrainTessellationModel.h"
#include "OriginalCameraModel.h"
#include <algorithm>
#include <cstdio>
#include <limits>

namespace F=ZeroSisPresentation::OriginalForest;
namespace T=ZeroSisPresentation::OriginalTerrainTessellation;
namespace C=ZeroSisPresentation::OriginalCamera;
unsigned checks=0;std::uint64_t surfaceSamples=0,colourSamples=0;double maximumSurfaceError=0,maximumColourError=0;
void Check(bool condition,const char* message){++checks;if(!condition)throw std::runtime_error(message);}
template<class Operation>void Reject(Operation operation,const char* message){bool rejected=false;try{operation();}catch(const std::invalid_argument&){rejected=true;}Check(rejected,message);}
const float NaN=(std::numeric_limits<float>::quiet_NaN)(),Infinity=(std::numeric_limits<float>::infinity)();

// Explicit test Bezier basis only. These values are never asserted to be the
// original engine's unresolved cb1[10..13] upload or used by production drawing.
const T::Basis Bezier{{{{-1,3,-3,1}},{{3,-6,3,0}},{{-3,3,0,0}},{{1,0,0,0}}}};
std::array<double,4> Bernstein(double t){const double a=1-t;return {{a*a*a,3*t*a*a,3*t*t*a,t*t*t}};}
double Reference(const T::Heights& controls,double u,double v){
    const auto x=Bernstein(u),y=Bernstein(v);double result=0;
    for(unsigned row=0;row<4;++row)for(unsigned column=0;column<4;++column)
        result+=x[column]*y[row]*static_cast<double>(controls[row*4+column]);
    return result;
}
void Surface(const T::Heights& controls,float u,float v){
    const double expected=Reference(controls,u,v),actual=T::Evaluate(controls,Bezier,u,v),error=std::abs(actual-expected);
    maximumSurfaceError=(std::max)(maximumSurfaceError,error);++surfaceSamples;
    Check(error<=0.00003+std::abs(expected)*0.000004,"Bicubic height differs from independent Bernstein reference");
}
void Tessellation(){
    T::Heights plane{};
    for(unsigned row=0;row<4;++row)for(unsigned column=0;column<4;++column)plane[row*4+column]=2.0f+3.0f*(static_cast<float>(column)/3.0f)-1.5f*(static_cast<float>(row)/3.0f);
    for(unsigned y=0;y<=32;++y)for(unsigned x=0;x<=32;++x){const float u=x/32.0f,v=y/32.0f;Surface(plane,u,v);
        Check(std::abs(T::Evaluate(plane,Bezier,u,v)-(2.0f+3.0f*u-1.5f*v))<0.00001f,"Planar Bezier patch lost its plane");}
    std::uint32_t state=0x924615u;
    for(unsigned fixture=0;fixture<64;++fixture){T::Heights controls{};
        for(auto& value:controls){state=state*1664525u+1013904223u;value=static_cast<float>(static_cast<int>((state>>8)%8193)-4096)/257.0f;}
        for(unsigned y=0;y<=16;++y)for(unsigned x=0;x<=16;++x)Surface(controls,x/16.0f,y/16.0f);
        Check(std::abs(T::Evaluate(controls,Bezier,0,0)-controls[0])<.00003f&&std::abs(T::Evaluate(controls,Bezier,1,0)-controls[3])<.00003f&&
              std::abs(T::Evaluate(controls,Bezier,0,1)-controls[12])<.00003f&&std::abs(T::Evaluate(controls,Bezier,1,1)-controls[15])<.00003f,"Bezier boundary corner interpolation changed");
        T::Heights adjacent{};for(unsigned row=0;row<4;++row){adjacent[row*4]=controls[row*4+3];
            for(unsigned column=1;column<4;++column)adjacent[row*4+column]=controls[row*4+3]+column*.25f;}
        for(unsigned y=0;y<=32;++y){const float v=y/32.0f;Check(std::abs(T::Evaluate(controls,Bezier,1,v)-T::Evaluate(adjacent,Bezier,0,v))<.00001f,"Shared patch boundary is discontinuous");}
    }
    std::array<std::uint8_t,16> known{};known.fill(1);T::Heights poison;poison.fill(NaN);
    for(unsigned index=0;index<16;++index){auto footprint=known;footprint[index]=0;
        const auto absent=T::EvaluateKnown(poison,footprint,Bezier,.25f,.75f);Check(!absent.available&&absent.height==0,"Unknown footprint consumed private NaN heights");}
    Reject([&]{T::EvaluateKnown(poison,known,Bezier,.25f,.75f);},"Known NaN control was accepted");
    auto malformed=known;malformed[3]=2;Reject([&]{T::EvaluateKnown(plane,malformed,Bezier,.25f,.75f);},"Nonboolean known byte accepted");
    for(float bad:{NaN,Infinity,-.01f,1.01f}){Reject([&]{T::Evaluate(plane,Bezier,bad,.5f);},"Invalid u accepted");Reject([&]{T::Evaluate(plane,Bezier,.5f,bad);},"Invalid v accepted");}
    for(float bad:{NaN,Infinity,1000001.0f}){auto basis=Bezier;basis[2][1]=bad;Reject([&]{T::Evaluate(plane,basis,.5f,.5f);},"Invalid basis entry accepted");
        auto heights=plane;heights[9]=bad;Reject([&]{T::Evaluate(heights,Bezier,.5f,.5f);},"Invalid control height accepted");}
    for(unsigned factor=1;factor<=64;++factor)Check(T::IntegerFactor(static_cast<float>(factor))==factor,"Integer factor changed");
    Check(T::IntegerFactor(1.01f)==2&&T::IntegerFactor(63.01f)==64,"Fractional integer tessellation factor rounding changed");
    for(float bad:{NaN,Infinity,0.0f,.999f,64.01f})Reject([&]{T::IntegerFactor(bad);},"Out-of-range tessellation factor accepted");
    const auto present=T::EvaluateKnown(plane,known,Bezier,.5f,.5f);Check(present.available&&std::abs(present.height-2.75f)<.00001f,"Known footprint lost its height");
}

std::array<double,4> ColourReference(const F::Colour& base,const F::Colour& overlay){
    const double urow[3]={-.147130,-.288860,.436000},vrow[3]={.615000,-.514990,-.100010};
    double ub=0,vb=0,uo=0,vo=0;
    for(unsigned component=0;component<3;++component){ub+=base[component]*urow[component];vb+=base[component]*vrow[component];uo+=overlay[component]*urow[component];vo+=overlay[component]*vrow[component];}
    const double alpha=overlay[3],u=(1-alpha)*ub+alpha*uo,v=(1-alpha)*vb+alpha*vo;
    return {{base[0]+1.139830*v,base[0]-.394650*u-.580600*v,base[0]+2.032110*u,base[3]}};
}
void Forest(){
    Check(F::TileTextures==4&&F::RandomTreesPerTile==360&&F::GriddedTreesPerTile==0&&F::OverlayAlpha==.60f&&F::MinimumSpacing==1.33f&&F::InstancesPerBatch==90,"Forest XML/shader constants changed");
    std::vector<F::Instance> instances;std::vector<std::array<float,4>> expected;
    for(unsigned index=0;index<181;++index){if(index%13==0){F::Instance hidden;hidden.translation={NaN,Infinity,-Infinity};hidden.scale=NaN;instances.push_back(hidden);}
        F::Instance current;current.revealed=true;current.translation={index*.25f,-static_cast<float>(index),index*.125f};current.scale=.25f+(index%5)*.5f;
        instances.push_back(current);expected.push_back({{current.translation.x,current.translation.y,current.translation.z,current.scale}});}
    const auto batches=F::BuildBatches(instances);Check(batches.size()==3&&batches[0].count==90&&batches[1].count==90&&batches[2].count==1,"Forest instance batches differ from 90/90/1");
    unsigned index=0;const F::Vector point{.25f,-.5f,1.0f};
    for(const auto& batch:batches)for(unsigned local=0;local<batch.count;++local,++index){Check(batch.transforms[local]==expected[index],"Forest batches changed source order or consumed hidden transforms");
        const auto transformed=F::Transform(point,batch,local);const auto& row=expected[index];
        Check(transformed.x==point.x*row[3]+row[0]&&transformed.y==point.y*row[3]+row[1]&&transformed.z==point.z*row[3]+row[2],"Forest instance transform differs from independent scale/translate");}
    Check(index==181&&F::BuildBatches({}).empty(),"Empty/complete forest batch coverage changed");
    std::vector<F::Instance> limit(F::MaxInstances);Check(F::BuildBatches(limit).empty(),"Unknown maximum-size forest input produced geometry");limit.emplace_back();Reject([&]{F::BuildBatches(limit);},"Oversized forest list accepted");
    for(float bad:{NaN,Infinity,0.0f,-1.0f,1000.01f}){F::Instance value;value.revealed=true;value.scale=bad;Reject([&]{F::BuildBatches({value});},"Invalid known tree scale accepted");}
    F::Instance bad;bad.revealed=true;bad.translation={NaN,0,0};Reject([&]{F::BuildBatches({bad});},"Known NaN tree translation accepted");
    Reject([&]{F::Transform({NaN,0,0},batches[0],0);},"Invalid forest point accepted");Reject([&]{F::Transform(point,batches[0],90);},"Out-of-range forest instance accepted");
    auto invalid=batches[0];invalid.count=91;Reject([&]{F::Transform(point,invalid,0);},"Unbounded forest batch count accepted");
    invalid=batches[0];invalid.transforms[0][0]=NaN;Reject([&]{F::Transform(point,invalid,0);},"Direct batch NaN transform accepted");
    invalid=batches[0];invalid.transforms[0][3]=0;Reject([&]{F::Transform(point,invalid,0);},"Direct batch zero scale accepted");
    invalid=batches[0];invalid.transforms[0][3]=1000;Reject([&]{F::Transform({1e38f,0,0},invalid,0);},"Overflowing tree transform accepted");
    Check(!F::PassesAlpha(0)&&!F::PassesAlpha(std::nextafter(.1f,0.0f))&&F::PassesAlpha(.1f)&&F::PassesAlpha(std::nextafter(.1f,1.0f))&&F::PassesAlpha(1),"Original alpha 0.1 clipping boundary changed");
    for(float badAlpha:{NaN,Infinity,-.01f,1.01f})Reject([&]{F::PassesAlpha(badAlpha);},"Invalid forest alpha accepted");
    const float levels[4]={0,.2f,.6f,1};
    for(unsigned baseIndex=0;baseIndex<64;++baseIndex)for(unsigned overlayIndex=0;overlayIndex<64;++overlayIndex)for(float alpha:{0.0f,.1f,.6f,1.0f}){
        const F::Colour base{{levels[baseIndex%4],levels[(baseIndex/4)%4],levels[baseIndex/16],.37f}},overlay{{levels[overlayIndex%4],levels[(overlayIndex/4)%4],levels[overlayIndex/16],alpha}};
        const auto expectedColour=ColourReference(base,overlay);const auto actual=F::ChromaOverlay(base,overlay);++colourSamples;
        for(unsigned component=0;component<4;++component){const double error=std::abs(expectedColour[component]-actual[component]);maximumColourError=(std::max)(maximumColourError,error);Check(error<.000001,"Forest chroma overlay differs from independent matrix");}
        Check(actual[3]==base[3],"Forest chroma overlay changed base alpha");
    }
    for(float value:{NaN,Infinity,-.1f,1.1f})for(unsigned component=0;component<4;++component){F::Colour colour{{.2f,.4f,.6f,1}};colour[component]=value;
        Reject([&]{F::ChromaOverlay(colour,{{0,0,0,0}});},"Invalid base colour accepted");Reject([&]{F::ChromaOverlay({{0,0,0,1}},colour);},"Invalid overlay colour accepted");}
}
double ComponentDot(C::Vector a,C::Vector b){return static_cast<double>(a.x)*b.x+static_cast<double>(a.y)*b.y+static_cast<double>(a.z)*b.z;}
C::Vector Point(const C::Matrix& matrix,C::Vector p){return {p.x*matrix[0]+p.y*matrix[4]+p.z*matrix[8]+matrix[12],
    p.x*matrix[1]+p.y*matrix[5]+p.z*matrix[9]+matrix[13],p.x*matrix[2]+p.y*matrix[6]+p.z*matrix[10]+matrix[14]};}
void Camera(){
    Check(C::ResetNearPlane==1&&C::ResetFarPlane==10000&&!C::WorldCameraCalibrationVerified,"General camera reset or world calibration scope changed");
    for(float degrees:{5.0f,30.5f,45.0f,60.0f,90.25f,120.0f,179.0f}){
        const float expected=static_cast<float>(static_cast<double>(degrees)*(std::acos(-1.0)/180.0));
        Check(C::Radians(degrees)==expected,"FOV did not widen/multiply/narrow as the original callsite");
        for(float aspect:{.5f,1.0f,16.0f/9.0f})for(float nearPlane:{.1f,1.0f}){
            const float farPlane=10000;const auto matrix=C::Perspective(degrees,aspect,nearPlane,farPlane);
            const auto ndc=[&](double z){return (z*matrix[10]+matrix[14])/(-z);};
            Check(std::abs(ndc(-nearPlane))<.000001&&std::abs(ndc(-farPlane)-1)<.000001,"RH projection near/far depth differs from analytic 0/1");
            const double halfY=nearPlane*std::tan(static_cast<double>(expected)/2),halfX=halfY*aspect;
            Check(std::abs(halfX*matrix[0]/nearPlane-1)<.000002&&std::abs(halfY*matrix[5]/nearPlane-1)<.000002,"Perspective frustum scale differs from analytic FOV");
            Check(matrix[11]==-1&&matrix[15]==0&&matrix[1]==0&&matrix[4]==0,"RH perspective shape changed");
        }
    }
    const C::Vector eyes[3]={{0,0,10},{3,4,8},{-11.5f,5.25f,1.75f}},targets[3]={{0,0,0},{-2,1,0},{4.5f,-3.0f,-8.0f}};
    for(unsigned sample=0;sample<3;++sample){const auto matrix=C::LookAt(eyes[sample],targets[sample],{.1f,1,.2f});
        const C::Vector right{matrix[0],matrix[4],matrix[8]},up{matrix[1],matrix[5],matrix[9]},back{matrix[2],matrix[6],matrix[10]};
        Check(std::abs(ComponentDot(right,right)-1)<.000001&&std::abs(ComponentDot(up,up)-1)<.000001&&std::abs(ComponentDot(back,back)-1)<.000001,"LookAt axes are not unit length");
        Check(std::abs(ComponentDot(right,up))<.000001&&std::abs(ComponentDot(right,back))<.000001&&std::abs(ComponentDot(up,back))<.000001,"LookAt axes are not orthogonal");
        const auto origin=Point(matrix,eyes[sample]),target=Point(matrix,targets[sample]);
        Check(std::abs(origin.x)<.00001f&&std::abs(origin.y)<.00001f&&std::abs(origin.z)<.00001f,"LookAt eye did not map to origin");
        const C::Vector delta{eyes[sample].x-targets[sample].x,eyes[sample].y-targets[sample].y,eyes[sample].z-targets[sample].z};
        Check(std::abs(target.x)<.00001f&&std::abs(target.y)<.00001f&&std::abs(target.z+std::sqrt(ComponentDot(delta,delta)))<.00001,"LookAt target is not on the negative RH Z axis");
        const auto cross=C::Cross(right,up);Check(std::abs(cross.x-back.x)<.000001f&&std::abs(cross.y-back.y)<.000001f&&std::abs(cross.z-back.z)<.000001f,"LookAt frame changed handedness");
    }
    for(float value:{NaN,Infinity,0.0f,-1.0f,180.0f,181.0f})Reject([&]{C::Radians(value);},"Invalid camera FOV accepted");
    for(float value:{NaN,Infinity,0.0f,-1.0f}){Reject([&]{C::Perspective(60,value,1,10000);},"Invalid camera aspect accepted");
        Reject([&]{C::Perspective(60,1,value,10000);},"Invalid camera near plane accepted");Reject([&]{C::Perspective(60,1,1,value);},"Invalid camera far plane accepted");}
    Reject([&]{C::Perspective(60,1,10,1);},"Reversed camera planes accepted");Reject([&]{C::Perspective(60,1,1,1);},"Equal camera planes accepted");
    Reject([&]{C::Perspective(60,1,2e38f,3e38f);},"Overflowing camera projection accepted");
    Reject([&]{C::LookAt({0,0,0},{0,0,0},{0,1,0});},"Degenerate eye/target accepted");
    Reject([&]{C::LookAt({0,0,1},{0,0,0},{0,0,0});},"Zero camera up vector accepted");
    Reject([&]{C::LookAt({0,0,1},{0,0,0},{0,0,2});},"Parallel camera up/back vectors accepted");
    Reject([&]{C::LookAt({NaN,0,1},{0,0,0},{0,1,0});},"Nonfinite camera eye accepted");
    Reject([&]{C::LookAt({0,0,1},{Infinity,0,0},{0,1,0});},"Nonfinite camera target accepted");
    Reject([&]{C::LookAt({0,0,1},{0,0,0},{0,NaN,0});},"Nonfinite camera up vector accepted");
    Reject([&]{C::LookAt({1e38f,0,0},{-1e38f,0,0},{0,1,0});},"Overflowing camera direction accepted");
}
int main(){try{Tessellation();Forest();Camera();std::printf("PASS_FOREST_TESSELLATION checks=%u surface_samples=%llu colour_samples=%llu max_surface_error=%.9g max_colour_error=%.9g original_basis_verified=0 runtime_executed=0\n",checks,
    static_cast<unsigned long long>(surfaceSamples),static_cast<unsigned long long>(colourSamples),maximumSurfaceError,maximumColourError);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"FAIL_FOREST_TESSELLATION %s\n",error.what());return 1;}}
