#include "OriginalTerrainCacheModel.h"
#include "cache_golden.h"
#include <cstdio>
#include <limits>

namespace C=ZeroSisPresentation::OriginalTerrainCache;
static unsigned long long checks=0;
static void Check(bool value,const char* message){++checks;if(!value)throw std::runtime_error(message);}
template<class F>static void Reject(F action){bool rejected=false;try{action();}catch(const std::invalid_argument&){rejected=true;}Check(rejected,"Invalid cache input was accepted");}
static bool Close(double a,double b,double tolerance=0.0000003){return std::abs(a-b)<=tolerance;}

int main(){try{
    for(unsigned direction=0;direction<4;++direction){
        const auto matrix=C::OrientationMatrix(direction);
        for(unsigned i=0;i<16;++i)Check(matrix.values[i]==OriginalOrientationGolden[direction][i],"Original integer matrix golden differs");
    }
    for(int x=-32;x<=32;++x)for(int y=-32;y<=32;++y)for(unsigned fractional=0;fractional<2;++fractional){
        const double px=x+fractional*0.125,py=y-fractional*0.375,pz=-px-py;
        const C::Point expected[4]={{px,py,pz},{-pz-2,-py+3,-px-1},{pz+4,py,px-4},{-px+2,-py+3,-pz-5}};
        for(unsigned direction=0;direction<4;++direction){
            const auto point=C::OrientPoint({px,py,pz},direction);
            Check(point.x==expected[direction].x,"Original mirrored translation X differs");
            Check(point.y==expected[direction].y,"Original mirrored translation Y differs");
            Check(point.z==expected[direction].z,"Original mirrored translation Z differs");
            Check(point.x+point.y+point.z==0,"Orientation left the cube plane");
        }
    }
    const unsigned expectedNormal[4]={128,256,256,512},expectedAdvanced[4]={128,256,512,512};
    for(unsigned detail=0;detail<4;++detail)for(int capability=0;capability<16;++capability)for(unsigned advanced=0;advanced<2;++advanced){
        const auto layout=C::SelectScratchLayout({detail,capability,advanced!=0});
        const unsigned side=advanced&&capability>=8?expectedAdvanced[detail]:expectedNormal[detail];
        Check(layout.width==side&&layout.height==side,"Original cache quality branch differs");
        Check(layout.mipLevels==(side==128?8u:side==256?9u:10u),"Original full-mip allocation differs");
    }
    for(unsigned side=1;side<=16384;++side){
        unsigned expected=1;for(unsigned value=side;value>1;value/=2)++expected;
        Check(C::FullMipCount(side)==expected,"Original bit-length mip count differs");
        for(unsigned level=0;level<expected;++level)Check(C::MipExtent(side,level)==(side>>level),"Mip dimensions differ");
    }
    Check(C::LogicalMipBytes(128,4)==87380,"RGBA8 128 mip payload differs");
    Check(C::LogicalMipBytes(256,4)==349524,"RGBA8 256 mip payload differs");
    Check(C::LogicalMipBytes(512,4)==1398100,"RGBA8 512 mip payload differs");
    Check(C::LogicalMipBytes(512,8)==2796200,"Float16 512 mip payload differs");
    const auto descriptor=C::NormalCacheDescriptor();
    Check(descriptor.resourceFormat==27&&descriptor.renderViewFormat==28&&descriptor.sampleViewFormat==28,"Normal cache view formats differ");
    Check(descriptor.samplerIndex==5&&descriptor.filter==0x15&&descriptor.addressU==3&&descriptor.addressV==3&&descriptor.addressW==3,"Original sampler5 differs");
    for(unsigned channel=0;channel<256;++channel){
        const auto decoded=C::DecodeNormalRgba8({{static_cast<std::uint8_t>(channel),128,255,0}});
        Check(Close(decoded[0],2.0*channel/255.0-1),"RGBA8 normal decoder differs");
        Check(Close(decoded[1],1.0/255.0)&&decoded[2]==1,"GPU cache confused with biased CPU XY codec");
    }
    for(unsigned side: {128u,256u,512u})for(unsigned texel=0;texel<side;++texel){
        const auto sample=C::LinearClampAxis((texel+0.5)/side,side);
        Check(sample.before==texel&&sample.after==(texel+1<side?texel+1:texel)&&sample.fraction==0,"Texel-center linear clamp differs");
    }
    for(unsigned side:{128u,256u,512u}){
        const auto low=C::LinearClampAxis(-10,side),high=C::LinearClampAxis(10,side);
        Check(low.before==0&&low.after==0&&high.before==side-1&&high.after==side-1,"Clamp sampling leaks across the cache boundary");
    }
    Reject([]{C::OrientationMatrix(4);});Reject([]{C::OrientPoint({1,2,3},0);});
    Reject([]{C::OrientPoint({std::numeric_limits<double>::quiet_NaN(),0,0},0);});
    Reject([]{C::OrientPoint({1000001,0,-1000001},0);});
    Reject([]{C::SelectScratchLayout({4,8,true});});Reject([]{C::SelectScratchLayout({2,-1,true});});
    Reject([]{C::SelectScratchLayout({2,256,true});});Reject([]{C::FullMipCount(0);});Reject([]{C::FullMipCount(16385);});
    Reject([]{C::MipExtent(128,8);});Reject([]{C::LogicalMipBytes(512,3);});Reject([]{C::LinearClampAxis(0,0);});
    Reject([]{C::LinearClampAxis(std::numeric_limits<double>::infinity(),128);});
    std::printf("PASS_ORIGINAL_TERRAIN_CACHE checks=%llu\n",checks);return 0;
}catch(const std::exception& error){std::printf("FAIL_ORIGINAL_TERRAIN_CACHE %s\n",error.what());return 1;}}
