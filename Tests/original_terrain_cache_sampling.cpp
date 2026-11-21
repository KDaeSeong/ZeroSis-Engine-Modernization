#include "OriginalTerrainCacheSamplingModel.h"
#include "OriginalTerrainCacheModel.h"
#include "cache_sampling_golden.h"
#include <cstdio>
#include <cstring>
#include <limits>

namespace S=ZeroSisPresentation::OriginalTerrainCacheSampling;
namespace C=ZeroSisPresentation::OriginalTerrainCache;
static unsigned checks=0;
static void Check(bool condition){++checks;if(!condition)throw std::runtime_error("Cache sampling assertion failed");}
static void Near(double actual,double expected,double tolerance=1e-10){Check(std::abs(actual-expected)<=tolerance);}
template<class Action>void Reject(Action action){bool rejected=false;try{action();}catch(const std::invalid_argument&){rejected=true;}Check(rejected);}
static std::uint64_t Fold(std::uint64_t hash,unsigned byte){return (hash^byte)*1099511628211ull;}
static void Heights(){
    Check(S::SourceMetricXDefault==1);Check(S::SourceMetricYDefault==0.866f);Check(S::SourceMetricZDefault==0.2f);
    std::uint64_t hash=1469598103934665603ull;
    for(unsigned raw=0;raw<65536;++raw){const float value=S::RawHeightToOriginalWorld(static_cast<std::uint16_t>(raw));
        std::uint32_t bits=0;std::memcpy(&bits,&value,4);
        for(unsigned b=0;b<4;++b)hash=Fold(hash,(bits>>(b*8))&255u);
        Check(std::isfinite(value)&&value>=0);}
    Check(hash==CacheSamplingGolden::RawHeightHash);
    hash=1469598103934665603ull;unsigned count=0;
    for(const float reference:{0.0f,15300.0f/65535.0f,1.0f})for(unsigned raw=0;raw<65536;++raw){
        const float normalized=static_cast<float>(raw)/65535.0f,centered=normalized-reference;
        const double reconstructed=static_cast<double>(centered)+reference;
        if(reconstructed<0||reconstructed>1)continue;
        const auto value=S::QuantizeCenteredHeight(centered,reference);
        hash=Fold(Fold(hash,value&255u),value>>8);++count;
        Check(value<=reconstructed*65535&&static_cast<unsigned>(value)+1>reconstructed*65535);}
    Check(count==CacheSamplingGolden::QuantizeCases);Check(hash==CacheSamplingGolden::QuantizeHash);
    Check(S::FinalizeStampedHeight(0,0.000001f,15300.0f/65535)==15299);
    Check(S::FinalizeStampedHeight(0.25f,0.5f,0)==32767);
    Check(S::FinalizeStampedHeight(-0.25f,0.5f,1)==32767);
    Check(S::QuantizeCenteredHeight(0.5f,0)==32767);
    const float origin=S::RawHeightToOriginalWorld(15300);
    Near(origin,12.0,0.000001);Near(S::NormalizeOriginalHeight(15300,origin),0);
    for(unsigned raw=0;raw<65536;raw+=257){const auto z=S::RawHeightToOriginalWorld(static_cast<std::uint16_t>(raw));
        const auto display=S::NormalizeOriginalHeight(static_cast<std::uint16_t>(raw),origin);
        Near(S::RestoreOriginalHeight(display,origin),z,0.000004);}
    Near(S::NormalizedHeightRangeDefault,0.803125,0.000001);
    Reject([]{S::FinalizeStampedHeight(0,0,0);});Reject([]{S::FinalizeStampedHeight(0,-1,0);});
    Reject([]{S::QuantizeCenteredHeight(2,0);});Reject([]{S::QuantizeCenteredHeight(-0.1f,0);});
    Reject([]{S::RawHeightToOriginalWorld(1,0);});Reject([]{S::NormalizeOriginalHeight(1,0,0);});
    Reject([]{S::RestoreOriginalHeight(std::numeric_limits<float>::quiet_NaN(),0);});
}
static void Coordinates(){
    for(const unsigned n:{128u,256u,512u}){
        S::ScratchFootprint f;f.originX=17;f.originY=-23;f.side=n;
        Check(C::FullMipCount(n)==(n==128?8u:n==256?9u:10u));
        for(unsigned y=0;y<n;++y)for(unsigned x=0;x<n;++x){
            // Independent inversion of the original RH ortho and translation:
            // clip=(2*(source-origin+1)/65-1-1/N, reversedY).
            const double expectedX=16+(static_cast<double>(x)+1)*65/n;
            const double expectedY=-24+(static_cast<double>(y)+1)*65/n;
            const auto source=S::ScratchRasterToSource(f,x+0.5,y+0.5);
            Near(source.x,expectedX);Near(source.y,expectedY);
            const auto uv=S::ScratchRasterUv(f,source.x,source.y);
            Near(uv.x,(x+0.5)/n);Near(uv.y,(y+0.5)/n);
            const auto sample=S::ScratchSampleUv(f,source.x,source.y);
            Near(sample.x,(x+1.0)/n);Near(sample.y,(y+1.0)/n);
        }
        for(unsigned y=0;y<66;++y)for(unsigned x=0;x<66;++x){
            const auto halo=S::HaloTexelCenter(x,y,66,1);
            const auto uv=S::ScratchSampleUv(f,halo.x+f.originX,halo.y+f.originY);
            Near(uv.x,(x+0.5)/65);Near(uv.y,(y+0.5)/65);}
    }
    Reject([]{S::ScratchFootprint f;f.side=66;S::ScratchSampleUv(f,0,0);});
    Reject([]{S::ScratchFootprint f;f.cellsX=0;S::ScratchRasterToSource(f,0,0);});
    Reject([]{S::HaloTexelCenter(66,0,66,1);});
}
static void Filtering(){
    const auto affine=[](unsigned x,unsigned y){return std::array<float,4>{{static_cast<float>(x),
        static_cast<float>(y),static_cast<float>(3*x+2*y),1}};};
    for(unsigned iy=0;iy<=24;++iy)for(unsigned ix=0;ix<=24;++ix){
        const double u=(static_cast<int>(ix)-4)/16.0,v=(static_cast<int>(iy)-4)/16.0;
        unsigned reads=0;const auto result=S::GuardedLinearClamp({u,v},4,4,[](unsigned,unsigned){return true;},
            [&](unsigned x,unsigned y){++reads;return affine(x,y);});
        Check(result.complete&&reads==4);
        const double x=(std::max)(0.0,(std::min)(3.0,u*4-0.5)),y=(std::max)(0.0,(std::min)(3.0,v*4-0.5));
        Near(result.value[0],x);Near(result.value[1],y);Near(result.value[2],3*x+2*y);
    }
    for(unsigned missing=0;missing<4;++missing){unsigned reads=0;
        const auto result=S::GuardedLinearClamp({0.5,0.5},2,2,[&](unsigned x,unsigned y){return y*2+x!=missing;},
            [&](unsigned,unsigned){++reads;return std::array<float,4>{{std::numeric_limits<float>::quiet_NaN(),0,0,0}};});
        Check(!result.complete&&reads==0);}
    unsigned reads=0;const auto zeroWeight=S::GuardedLinearClamp({0.25,0.25},2,2,
        [](unsigned x,unsigned y){return x==0&&y==0;},[&](unsigned,unsigned){++reads;return std::array<float,4>{{0,0,0,0}};});
    Check(!zeroWeight.complete&&reads==0);
    Reject([&]{S::GuardedLinearClamp({0,0},0,1,[](unsigned,unsigned){return true;},affine);});
    Reject([&]{S::GuardedLinearClamp({std::numeric_limits<double>::quiet_NaN(),0},1,1,[](unsigned,unsigned){return true;},affine);});
}
int main(){try{Heights();Coordinates();Filtering();std::printf("PASS_ORIGINAL_TERRAIN_CACHE_SAMPLING checks=%u\n",checks);return 0;}
    catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}}
