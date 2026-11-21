#define NOMINMAX
#define PSAPI_VERSION 2
#include <Windows.h>
#include <Psapi.h>
#include "OriginalWaterSurfaceModel.h"
#include "OriginalWaterState.h"
#include "OriginalWaterOpticsModel.h"
#include "OriginalWaterLeanPackage.h"
#include "OriginalWaterSurfaceBinding.h"
#include "WorldTerrainReuse.h"
#include <chrono>
#include <cstdio>
#include <fstream>

namespace P=ZeroSisPresentation;
namespace W=P::OriginalWater;
namespace S=W::Surface;
namespace O=P::OriginalWaterOptics;
namespace L=P::OriginalWaterLean;
namespace B=P::OriginalWaterSurfaceBinding;
namespace T=P::OriginalTerrain;
namespace {
unsigned checks=0,opticsSamples=0,acceptedLobes=0,rejectedLobes=0,keyChecks=0;
constexpr std::size_t MemoryLimit=384ull*1024*1024;
std::size_t peakWorkingSet=0,peakCommit=0;
void Check(bool value,const char* reason){++checks;if(!value)throw std::runtime_error(reason);}
void Near(double actual,double expected,double tolerance=3e-10){
    Check(std::isfinite(actual)&&std::isfinite(expected)&&std::abs(actual-expected)<=tolerance*(1+std::abs(expected)),"Pipeline scalar reference differs");
}
void MemoryCheck(){PROCESS_MEMORY_COUNTERS_EX counters{};counters.cb=sizeof(counters);
    Check(K32GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&counters),sizeof(counters))!=0,"Cannot inspect own CPU process memory");
    peakWorkingSet=(std::max)(peakWorkingSet,static_cast<std::size_t>(counters.PeakWorkingSetSize));
    peakCommit=(std::max)(peakCommit,static_cast<std::size_t>(counters.PeakPagefileUsage));
    Check(peakWorkingSet<=MemoryLimit&&peakCommit<=MemoryLimit,"Surface pipeline exceeded384MiB");
}
std::vector<unsigned char> ReadPacket(const char* path){std::ifstream input(path,std::ios::binary|std::ios::ate);
    Check(input.good(),"Cannot read sealed LEAN package");const auto length=input.tellg();Check(length>=16&&length<=8*1024*1024,"Invalid bounded LEAN package size");
    std::vector<unsigned char> bytes(static_cast<std::size_t>(length));input.seekg(0);input.read(reinterpret_cast<char*>(bytes.data()),length);
    Check(input.good(),"Truncated LEAN package read");return bytes;}
P::WorldView Fixture(){P::WorldView view{};view.gridWidth=40;view.gridHeight=24;view.wrapX=true;view.wrapY=false;
    view.cameraX=20;view.cameraY=12;view.tileWidth=56;view.waterAssetsPath=L"sealed-water-package";
    view.terrainAssetsPath=L"sealed-terrain-package";view.waterSurfaceAssetsPath=L"sealed-water-lean-package";
    view.plots.reserve(960);
    for(int y=0;y<24;++y)for(int x=0;x<40;++x){P::WorldViewPlot plot{};plot.index=y*40+x;plot.x=x;plot.y=y;
        plot.revealed=x>=17&&x<=22&&y>=9&&y<=14;plot.visible=plot.revealed;plot.water=x==19||x==20;
        plot.terrainId=plot.water?6:0;plot.terrain=plot.water?"TERRAIN_OCEAN":"TERRAIN_GRASS";plot.continent=plot.water?0:1;
        view.plots.push_back(std::move(plot));}
    return view;
}
T::Atlas MakeAtlas(const W::Grid& grid,const S::Plane& plane){T::Atlas atlas;atlas.width=2560;atlas.height=1536;
    atlas.originX=-32;atlas.originY=0;atlas.wrapX=grid.wrapX;atlas.wrapY=grid.wrapY;
    const auto count=static_cast<std::size_t>(atlas.width)*atlas.height;atlas.ids.assign(count,T::UnknownRow);atlas.known.assign(count,0);atlas.heights.assign(count,0);
    for(unsigned y=0;y<atlas.height;++y)for(unsigned x=0;x<atlas.width;++x){
        const auto cell=W::OwnerAt(grid,x/64.0,-static_cast<double>(y)/64*W::RowSpacing);
        if(!cell.exists||!grid.cells[static_cast<std::size_t>(cell.y)*grid.width+cell.x].revealed)continue;
        const auto at=static_cast<std::size_t>(y)*atlas.width+x;atlas.known[at]=1;atlas.ids[at]=3;
        const double raw=plane.rawLevel+0.03*(std::abs(x/64.0-20.0)-0.55);
        atlas.heights[at]=static_cast<float>(raw-plane.heightOffset);
    }
    return atlas;
}
std::string Digest(const S::SurfaceMesh& mesh){
    static_assert(sizeof(S::Vertex)==32&&sizeof(S::Range)==16&&sizeof(S::Contour)==64,"Surface CPU ABI changed");
    const auto vertices=T::Sha256Hex(reinterpret_cast<const unsigned char*>(mesh.vertices.data()),mesh.vertices.size()*sizeof(S::Vertex));
    const auto ranges=T::Sha256Hex(reinterpret_cast<const unsigned char*>(mesh.ranges.data()),mesh.ranges.size()*sizeof(S::Range));
    const auto contours=T::Sha256Hex(reinterpret_cast<const unsigned char*>(mesh.contours.data()),mesh.contours.size()*sizeof(S::Contour));
    const auto text=vertices+ranges+contours+std::to_string(mesh.usedStep);return T::Sha256Hex(reinterpret_cast<const unsigned char*>(text.data()),text.size());
}
void Keys(const P::WorldView& original){const auto ground=P::WorldTerrainGroundKey::Capture(original,800,600,700,11,12);const auto state=W::CaptureWaterGrid(original);
    const auto test=[&](P::WorldView view,bool sameGround){
        Check(ground.Matches(view,800,600,700,11,12)==sameGround,"Current ground metadata invalidation policy differs");
        Check(W::SameWaterGrid(state,W::CaptureWaterGrid(view)),"Surface topology key changed with presentation-only metadata");keyChecks+=2;};
    auto view=original;++view.cameraX;test(view,false);view=original;++view.cameraY;test(view,false);
    view=original;view.tileWidth+=8;test(view,false);
    view=original;view.animationSeconds=2;test(view,true);view=original;view.waterAnimationSeconds=4;test(view,true);
    view=original;view.fogAnimationSeconds=8;test(view,true);
    view=original;view.waterSurfaceAssetsPath=L"changed-lean";test(view,false);
    view=original;view.waterSurfaceAssetsPath.clear();test(view,false);
    view=original;view.waterAssetsPath=L"changed-water";test(view,false);
    view=original;view.selectedCity=12;view.turn=7;view.units.push_back(P::WorldViewUnit{});test(view,true);
    auto off=original;off.waterSurfaceAssetsPath.clear();const auto offKey=P::WorldTerrainGroundKey::Capture(off,800,600,700,11,12);
    view=off;view.waterAssetsPath=L"changed-overlay";Check(offKey.Matches(view,800,600,700,11,12),"Legacy colour-only mode unnecessarily invalidated ground metadata");++keyChecks;
    view=off;view.waterSurfaceAssetsPath=L"enable-plane";Check(!offKey.Matches(view,800,600,700,11,12),"Enabling plane kept stale terrain selection metadata");++keyChecks;
}
O::Moments5 Moments(const L::Moments& value){return O::FromScalars(value.meanX,value.meanY,value.secondXX,value.secondYY,value.secondXY);}
unsigned Texel(double uv,unsigned span){const double repeated=uv-std::floor(uv);return (std::min)(span-1,static_cast<unsigned>(repeated*span));}
void Optics(const L::LeanPackage& packet,const S::SurfaceMesh& mesh){const auto& texture=L::FindAsset(packet,L::AssetRole::WaterBumps).texture;
    O::CandidateOpticsPolicy policy;O::Validate(policy);const auto view=O::NormalizeView({0.15,-0.1,1});
    const O::Vec3 light{0.4,0.2,0.9};
    for(std::size_t i=0;i<mesh.vertices.size()&&opticsSamples<1024;i+=3){const auto& vertex=mesh.vertices[i];if(vertex.kind!=0)continue;
        const auto uvs=W::RetailWaterUvs(vertex.x*64.0,-vertex.z*64.0,policy.uvScales,policy.uvTranslation*0.25);
        const auto rawA=L::ReadTexelUnorm(packet,L::AssetRole::WaterBumps,0,Texel(uvs[0][0],texture.width),Texel(uvs[0][1],texture.height));
        const auto rawB=L::ReadTexelUnorm(packet,L::AssetRole::WaterBumps,0,Texel(uvs[1][0],texture.width),Texel(uvs[1][1],texture.height));
        // Raw moments use S=1; only MixLayers applies the explicit runtime-scale candidate once.
        const auto a=Moments(L::DecodeMoments(rawA,false)),b=Moments(L::DecodeMoments(rawB,true));
        Near(a.meanX,2*rawA.rgba[0]-1);Near(b.meanX,-(2*rawB.rgba[0]-1));Near(a.xy,2*rawA.crossR-1);Near(b.xy,-(2*rawB.crossR-1));
        const auto mixed=O::MixLayers(a,b,{0.35,0.65},policy.scale);const double w0=0.35/policy.scale,w1=0.65/policy.scale;
        Near(mixed.covariance.xx,w0*w0*(a.xx-a.meanX*a.meanX)+w1*w1*(b.xx-b.meanX*b.meanX));
        Near(mixed.covariance.yy,w0*w0*(a.yy-a.meanY*a.meanY)+w1*w1*(b.yy-b.meanY*b.meanY));
        Near(mixed.covariance.xy,w0*w0*(a.xy-a.meanX*a.meanY)+w1*w1*(b.xy-b.meanX*b.meanY));
        const auto half=O::WarpedHalfSlope(view,light,{},1,mixed.mean,policy.horizontalEpsilon);Check(half.valid,"Controlled optics half vector unexpectedly invalid");
        const auto narrow=O::GaussianLobe(mixed.covariance,half.value,policy.primaryK),wide=O::GaussianLobe(mixed.covariance,half.value,policy.secondaryK,true);
        for(const auto& lobe:{narrow,wide}){Check(std::isfinite(lobe.value)&&std::isfinite(lobe.determinant),"Real LEAN moments produced nonfinite lobe");
            if(lobe.rejected){++rejectedLobes;Near(lobe.value,0,0);}else{++acceptedLobes;Check(lobe.determinant>0&&lobe.q<16,"Original Gaussian rejection contract changed");}}
        const auto reflected=O::ReflectionUvs(O::ProjectedReflectionUv(0.2,-0.1,1),mixed.covariance,wide.determinant);
        std::array<O::Rgba,4> taps;
        for(unsigned tap=0;tap<4;++tap)taps[tap]={0.5+0.1*std::cos(reflected[tap].x),0.5+0.1*std::sin(reflected[tap].y),0.25+0.05*std::cos(reflected[tap].x-reflected[tap].y),0.75};
        const auto reflection=O::AverageReflectionLinear(taps);
        double meanRed=0;for(const auto& tap:taps)meanRed+=tap.r*0.25;
        Near(reflection.rgb.x,std::pow(meanRed,O::ShaderGamma));Near(reflection.alpha,0.75,0);
        const double fresnel=O::RetailFresnel(mixed.mean,view),diffuse=O::RetailDiffuse(mixed.mean,light);
        const double specular=(narrow.value+wide.value)*0.0001;
        const auto encoded=O::EncodeLighting({0.3*diffuse*(1-fresnel)+reflection.rgb.x*fresnel+specular,
            0.4*diffuse*(1-fresnel)+reflection.rgb.y*fresnel+specular,0.5*diffuse*(1-fresnel)+reflection.rgb.z*fresnel+specular});
        Check(std::isfinite(encoded.x)&&std::isfinite(encoded.y)&&std::isfinite(encoded.z),"Linked reflection/gamma lighting is nonfinite");++opticsSamples;
    }
    Check(opticsSamples>=128&&acceptedLobes>0,"Real package was not linked through surface optics samples");
}
}
int main(int argc,char** argv){try{const auto start=std::chrono::steady_clock::now();Check(argc==2,"Expected sealed LEAN packet path");
    auto packet=L::DecodePackage(ReadPacket(argv[1]),B::LeanPackageSha256);MemoryCheck();
    Check(packet.assets.size()==1&&packet.assets[0].texture.mips==10,"Real LEAN packet shape differs");
    auto view=Fixture();const auto grid=W::CaptureWaterGrid(view);Keys(view);S::Plane plane;
    Check(plane.rawLevel==B::RawLevelCandidate,"Root plane/raw-level defaults differ");
    Check(static_cast<float>(S::PlaneHeight(plane))==B::WorldPlaneCandidate,"Root fixed-plane float differs from model metadata");
    auto atlas=MakeAtlas(grid,plane);const auto* const initialData=atlas.heights.data();const auto initialCapacity=atlas.heights.capacity();MemoryCheck();
    auto mesh=S::BuildSurface(grid,atlas,plane);MemoryCheck();
    Check(mesh.stats.waterVertices>0&&mesh.stats.shoreVertices>0&&!mesh.contours.empty(),"40x24 known/unknown fixture did not produce water and height contours");
    Check(static_cast<float>(mesh.planeY)==B::WorldPlaneCandidate,"Actual plane geometry disagrees with Root metadata height");
    Optics(packet,mesh);const auto geometrySha=Digest(mesh);const auto vertexCount=mesh.vertices.size(),contourCount=mesh.contours.size();const auto step=mesh.usedStep;
    auto hidden=view;std::size_t hiddenChanges=0;
    for(auto& plot:hidden.plots)if(!plot.revealed){plot.water=!plot.water;plot.hills=!plot.hills;plot.mountain=!plot.mountain;
        plot.terrainId=-999;plot.riverW=plot.riverNW=plot.riverNE=true;plot.flowE=plot.flowSE=plot.flowSW=999;++hiddenChanges;}
    Check(hiddenChanges==924&&W::SameWaterGrid(grid,W::CaptureWaterGrid(hidden)),"Unknown source properties contaminated water topology");
    std::size_t poisoned=0;
    for(std::size_t i=0;i<atlas.heights.size();++i)if(!atlas.known[i]){atlas.heights[i]=i%2?(std::numeric_limits<float>::quiet_NaN)():(std::numeric_limits<float>::infinity)();
        atlas.ids[i]=static_cast<std::uint8_t>(i%255);++poisoned;}
    mesh=S::BuildSurface(W::CaptureWaterGrid(hidden),atlas,plane);MemoryCheck();
    Check(Digest(mesh)==geometrySha,"Unknown poisoned texels changed surface/contours/UV/depth/ranges");
    Check(atlas.heights.data()==initialData&&atlas.heights.capacity()==initialCapacity,"Large atlas was replaced/copied during controlled pipeline");
    Check(poisoned>3700000,"Pipeline did not exercise the full default-sized unknown atlas");
    const auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count();
    Check(elapsed<=85000,"Controlled water pipeline exceeded85seconds");MemoryCheck();
    std::printf("PASS_ORIGINAL_WATER_SURFACE_PIPELINE checks=%u width=%u height=%u revealed=36 unknown_plots=%zu poisoned=%zu vertices=%zu contours=%zu step=%u optics_samples=%u accepted_lobes=%u rejected_lobes=%u key_checks=%u elapsed_ms=%lld peak_working_set=%zu peak_commit=%zu memory_limit=%zu geometry_sha=%s\n",
        checks,atlas.width,atlas.height,hiddenChanges,poisoned,vertexCount,contourCount,step,opticsSamples,acceptedLobes,rejectedLobes,keyChecks,
        static_cast<long long>(elapsed),peakWorkingSet,peakCommit,MemoryLimit,geometrySha.c_str());return 0;
}catch(const std::exception& error){std::fprintf(stderr,"Water surface pipeline: %s\n",error.what());return 1;}}
