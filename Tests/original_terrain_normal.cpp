#include "OriginalTerrainNormalModel.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include "normal_contract_golden.h"

namespace N=ZeroSisPresentation::OriginalTerrainNormal;
static unsigned Checks=0;
static void Check(bool condition,const char* message){++Checks;if(!condition){std::fprintf(stderr,"FAIL %s\n",message);std::exit(1);}}
static bool Near(float left,float right,float tolerance=0.000001f){return std::abs(left-right)<=tolerance;}
static std::uint32_t Bits(float value){std::uint32_t result=0;std::memcpy(&result,&value,sizeof(result));return result;}
template<class Action>static void Reject(Action action){bool rejected=false;try{action();}catch(const std::invalid_argument&){rejected=true;}Check(rejected,"invalid input rejection");}

int main(){
    unsigned goldenIndex=0;
    for(const auto& row:NormalGoldens){
        const auto derivative=N::BulkDerivatives(row.raw);
        if(Bits(derivative.x)!=Bits(row.dx)||Bits(derivative.y)!=Bits(row.dy))
            std::fprintf(stderr,"DAG case=%u center=%u actual=%08x,%08x expected=%08x,%08x\n",goldenIndex,
                static_cast<unsigned>(row.raw[12]),Bits(derivative.x),Bits(derivative.y),Bits(row.dx),Bits(row.dy));
        Check(Bits(derivative.x)==Bits(row.dx)&&Bits(derivative.y)==Bits(row.dy),"original DAG float32 derivatives");
        N::KnownWindow window;window.centerKnown=true;window.height=row.raw;
        const auto normal=N::BaseNormal(window,{row.sx,row.sy,row.hs});
        Check(Near(normal.x,row.nx)&&Near(normal.y,row.ny)&&Near(normal.z,row.nz),"original DAG normal metric");
        const auto packed=N::PackVertexNormal(normal);
        Check(packed.value[0]==row.half[0]&&packed.value[1]==row.half[1]&&packed.value[2]==row.half[2]&&packed.value[3]==0x3c00u,
              "independent IEEE half normal fetch");
        ++goldenIndex;
    }
    std::array<std::uint16_t,25> flat{};flat.fill(15300);
    const auto flatDerivative=N::BulkDerivatives(flat);
    Check(Bits(flatDerivative.x)==Bits(0.056617219001054764f)&&Bits(flatDerivative.y)==Bits(0.056617219001054764f),
          "preserve original positive-flat bulk tilt");
    for(unsigned x=0;x<256;++x)for(unsigned y=0;y<256;++y){
        const auto value=N::DecodeCachedXY(static_cast<std::uint8_t>(x),static_cast<std::uint8_t>(y));
        const double nx=(static_cast<int>(x)-128)/255.0,ny=(static_cast<int>(y)-128)/255.0;
        Check(Near(value.x,static_cast<float>(nx))&&Near(value.y,static_cast<float>(ny))&&
            Near(value.z,static_cast<float>(std::sqrt(1.0-nx*nx-ny*ny)))&&value.z>0.70f,"all compressed XY pairs");
    }
    for(unsigned bits=0;bits<65536;++bits){
        const unsigned exponent=(bits>>10)&31u;
        if(exponent==31u)continue;
        const float value=N::UnpackNormalHalf(static_cast<std::uint16_t>(bits));
        if(std::abs(value)<=1.0f)Check(N::PackNormalHalf(value)==bits,"half roundtrip across unit-normal domain");
    }
    for(unsigned pattern=0;pattern<4096;++pattern){
        unsigned reads=0,expectedUnknown=0;
        auto known=[&](int x,int y){return x==0&&y==0?true:((pattern>>((N::Index(x,y)*7)%12))&1u)!=0;};
        auto window=N::CaptureKnownWindow(known,[&](int x,int y){Check(known(x,y),"unknown numeric height not fetched");++reads;return static_cast<std::uint16_t>(15300+11*x+7*y);});
        for(int x=-2;x<=2;++x)for(int y=-2;y<=2;++y)if(!known(x,y)){++expectedUnknown;Check(window.height[N::Index(x,y)]==15300,"unknown height centre substitution");}
        Check(window.centerKnown&&window.substitutedUnknown==expectedUnknown&&reads==25-expectedUnknown,"capture known mask accounting");
        const auto normal=N::BaseNormal(window,{1.0f/64.0f,0.866025404f/64.0f,2.3f*255.0f/65535.0f});
        Check(std::isfinite(normal.x)&&std::isfinite(normal.y)&&std::isfinite(normal.z),"partial-known finite normal");
    }
    unsigned reads=0;
    const auto unknown=N::CaptureKnownWindow([](int,int){return false;},[&](int,int){++reads;return static_cast<std::uint16_t>(65535);});
    Check(!unknown.centerKnown&&reads==0,"unknown centre has no numeric fetch");
    const auto up=N::BaseNormal(unknown,{});Check(up.x==0&&up.y==0&&up.z==1,"unknown centre privacy fallback");
    Check(N::SignedHalfDifference(0,1)==-1&&N::SignedHalfDifference(1,0)==0,"negative odd x86 SAR");
    Reject([](){N::Validate({0,1,1});});Reject([](){N::Validate({1,-1,1});});Reject([](){N::Validate({1,1,-1});});
    Reject([](){N::Validate({std::numeric_limits<float>::quiet_NaN(),1,1});});
    Reject([](){N::PackNormalHalf(1.1f);});Reject([](){N::PackNormalHalf(std::numeric_limits<float>::infinity());});
    Reject([](){N::UnpackNormalHalf(0x7c00u);});
    std::printf("PASS_ORIGINAL_TERRAIN_NORMAL checks=%u\n",Checks);return 0;
}
