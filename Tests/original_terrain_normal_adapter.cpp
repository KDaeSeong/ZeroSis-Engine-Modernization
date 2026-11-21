#include "OriginalTerrainModel.h"
#include "OriginalTerrainBinding.h"
#include <cstdio>
#include <cstring>
#include <limits>
#include <stdexcept>
namespace T=ZeroSisPresentation::OriginalTerrain;
namespace N=ZeroSisPresentation::OriginalTerrainNormal;
static unsigned checks=0;
void Check(bool v){++checks;if(!v)throw std::runtime_error("Terrain normal adapter regression");}
void Near(double a,double b,double tolerance=2e-6){Check(std::abs(a-b)<tolerance);}
template<class F>void Reject(F f){bool rejected=false;try{f();}catch(const std::invalid_argument&){rejected=true;}Check(rejected);}
int main(){try{
    T::Atlas atlas;atlas.width=atlas.height=64;atlas.heightOffset=T::HeightOffsetCandidate;
    atlas.ids.assign(4096,3);atlas.known.assign(4096,1);atlas.heights.assign(4096,0);
    const auto normal=T::SurfaceNormal(atlas,24,24,T::HeightWorldScaleCandidate);
    // Independent static SIMD-DAG result from the original bulk producer for
    // a constant uint16(15300) input; preserve its small original flat bias.
    const double derivative=0.056617219001054764;
    const double metricScale=T::HeightWorldScaleCandidate*(255.0f/65535.0f);
    const double x=derivative*metricScale/(1.0f/64),y=derivative*metricScale/(0.866f/64);
    const double length=std::sqrt(x*x+y*y+1);
    Near(normal.x,x/length);Near(normal.y,y/length);Near(normal.z,1/length);
    Check(normal.x>0&&normal.y>0&&normal.z<1&&T::ProjectionForNormal(normal)==0);
    const auto quantized=N::QuantizeVertexNormal({normal.x,normal.y,normal.z});
    Check(quantized.x!=normal.x||quantized.y!=normal.y||quantized.z!=normal.z);
    // Raw float projection and half input must remain separate at z=.9.
    const T::Normal threshold{.4f,0,.90001f};const auto half=N::QuantizeVertexNormal({threshold.x,threshold.y,threshold.z});
    Check(T::ProjectionForNormal(threshold)==0);Check(T::ProjectionForNormal({half.x,half.y,half.z})!=0);
    // Poison every unknown numeric value: neither a hidden centre nor hidden
    // neighbours may be fetched, even if they carry NaNs or arbitrary IDs.
    atlas.known.assign(4096,0);atlas.heights.assign(4096,std::numeric_limits<float>::quiet_NaN());
    atlas.known[24*64+24]=1;atlas.heights[24*64+24]=0;
    const auto isolated=T::SurfaceNormal(atlas,24,24,T::HeightWorldScaleCandidate);
    Near(isolated.x,normal.x);Near(isolated.y,normal.y);Near(isolated.z,normal.z);
    const auto hidden=T::SurfaceNormal(atlas,25,24,T::HeightWorldScaleCandidate);Near(hidden.x,0);Near(hidden.y,0);Near(hidden.z,1);
    atlas.ids.assign(4096,255);const auto independentId=T::SurfaceNormal(atlas,24,24,T::HeightWorldScaleCandidate);
    Near(independentId.x,normal.x);Near(independentId.y,normal.y);Near(independentId.z,normal.z);
    atlas.heights[24*64+24]=std::numeric_limits<float>::quiet_NaN();Reject([&](){T::SurfaceNormal(atlas,24,24,2.3f);});
    atlas.heights[24*64+24]=0;atlas.heightOffset=std::numeric_limits<float>::infinity();Reject([&](){T::SurfaceNormal(atlas,24,24,2.3f);});
    atlas.heightOffset=T::HeightOffsetCandidate;Reject([&](){T::SurfaceNormal(atlas,24,24,-1);});
    Reject([&](){T::SurfaceNormal(atlas,1000000,24,2.3f);});
    std::printf("PASS_TERRAIN_NORMAL_ADAPTER checks=%u\n",checks);return 0;
}catch(const std::exception& ex){std::fprintf(stderr,"%s\n",ex.what());return 1;}}
