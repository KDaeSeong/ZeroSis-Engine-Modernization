#include "OriginalTerrainVertexPreparation.h"
#include <atomic>
#include <cstdio>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <system_error>

namespace OT=ZeroSisPresentation::OriginalTerrain;
namespace DP=ZeroSisPresentation::DeterministicParallel;
struct Vertex {float x,y,z,u,v,light;std::uint32_t w0,w1;float nx,ny,nz;};
static_assert(sizeof(Vertex)==44,"Vertex fixture layout differs");
static unsigned checks=0;static std::uint64_t verticesChecked=0,parallelVertexJobs=0;
static std::uint64_t vertexDigest=14695981039346656037ull;
std::uint64_t Signature(const std::vector<Vertex>& values){
    std::uint64_t result=14695981039346656037ull;const auto* bytes=reinterpret_cast<const unsigned char*>(values.data());
    for(std::size_t index=0;index<values.size()*sizeof(Vertex);++index){result^=bytes[index];result*=1099511628211ull;}
    return result;
}
void Check(bool condition,const char* message){++checks;if(!condition)throw std::runtime_error(message);}
template<class Operation>void Reject(Operation operation,const char* message){bool rejected=false;try{operation();}catch(const std::exception&){rejected=true;}Check(rejected,message);}

OT::Atlas Atlas(unsigned mode){
    OT::Atlas result;result.width=128;result.height=128;result.wrapX=true;result.wrapY=mode!=2;result.heightOffset=0.125f;
    result.ids.resize(128*128);result.known.resize(128*128);result.heights.resize(128*128);
    for(unsigned y=0;y<128;++y)for(unsigned x=0;x<128;++x){const auto at=y*128+x;
        const bool known=mode==0||(mode==1?(x+3*y)%11!=0:mode==2?x<65&&y<65:false);
        result.known[at]=static_cast<std::uint8_t>(known);result.ids[at]=known?static_cast<std::uint8_t>((x/9+y/13)%3):255;
        result.heights[at]=known?static_cast<float>((x*521u+y*233u+x*y*7u)%65536u)/65535.0f-result.heightOffset:
            (std::numeric_limits<float>::quiet_NaN)();
    }
    return result;
}

// Independent copy of the pre-change production loop, retaining its arithmetic
// and row-major push_back order. It does not invoke the parallel preparation.
std::vector<Vertex> OriginalSerial(const OT::Atlas& atlas,const OT::MaterialTable& table,const OT::ChunkSlots& slots,unsigned column,unsigned row){
    const int startX=static_cast<int>(column*64),startY=static_cast<int>(row*64);
    std::vector<Vertex> result;const unsigned divisions=slots.count?64u:1u;result.reserve((divisions+1)*(divisions+1));
    for(unsigned y=0;y<=divisions;++y)for(unsigned x=0;x<=divisions;++x){
        const float u=static_cast<float>(x)/static_cast<float>(divisions),v=static_cast<float>(y)/static_cast<float>(divisions);
        const int px=startX+static_cast<int>(x*(64/divisions)),py=startY+static_cast<int>(y*(64/divisions));
        const auto normal=OT::SurfaceNormal(atlas,px,py,OT::HeightWorldScaleCandidate);
        const auto fetched=ZeroSisPresentation::OriginalTerrainNormal::QuantizeVertexNormal({normal.x,normal.y,normal.z});
        const auto weights=OT::QuantizeWeights(OT::KernelWeights(atlas,table,slots,px,py,normal));
        std::uint32_t w0=0,w1=0;std::memcpy(&w0,weights.data(),4);std::memcpy(&w1,weights.data()+4,4);
        const float height=OT::AtlasWorldHeight(atlas,px,py);
        const float light=0.48f+0.52f*std::abs((-normal.x*0.4f+normal.y*0.4f+normal.z*0.8f)/0.979795897f);
        result.push_back({u,height,-v*OT::RowSpacing,u,v,light,w0,w1,fetched.x,fetched.y,fetched.z});
    }
    return result;
}
void Equal(const std::vector<Vertex>& actual,const std::vector<Vertex>& expected){
    Check(actual.size()==expected.size(),"Terrain vertex count changed");
    Check(actual.empty()||std::memcmp(actual.data(),expected.data(),actual.size()*sizeof(Vertex))==0,"Terrain vertex bytes differ from original scalar body");
    verticesChecked+=actual.size();
    const auto* bytes=reinterpret_cast<const unsigned char*>(actual.data());
    for(std::size_t index=0;index<actual.size()*sizeof(Vertex);++index){vertexDigest^=bytes[index];vertexDigest*=1099511628211ull;}
}
struct IndexedError:std::runtime_error {std::size_t index;explicit IndexedError(std::size_t at):std::runtime_error("controlled indexed failure"),index(at){}};
struct ThrowingOperation {std::uint64_t operator()(std::size_t index)const{if(index==7||index==1100)throw IndexedError(index);return index*17u;}};
struct ValueOperation {std::uint64_t operator()(std::size_t index)const{return static_cast<std::uint64_t>(index)*index+3u;}};
struct FailingFactory {
    unsigned* attempts;const unsigned failAfter;
    template<class Function>std::thread Start(Function function){
        const unsigned index=(*attempts)++;
        if(index==failAfter)throw std::system_error(std::make_error_code(std::errc::resource_unavailable_try_again));
        return std::thread(std::move(function));
    }
};

void PoolContracts(){
    Check(DP::ResolveWorkers(0)==0&&DP::ResolveWorkers(1)==0&&DP::ResolveWorkers(2)==2&&DP::ResolveWorkers(3)==2&&DP::ResolveWorkers(4)==4&&DP::ResolveWorkers(128)==4,"Worker selection is unbounded");
    DP::WorkerPool<> pool;DP::Metrics metrics;
    Check(DP::TransformIndexed<std::uint64_t>(0,4,ValueOperation{},pool,&metrics).empty()&&metrics.newThreads==0,"Empty batch launched work");
    const auto small=DP::TransformIndexed<std::uint64_t>(17,4,ValueOperation{},pool,&metrics);
    Check(small.size()==17&&metrics.workersUsed==0&&metrics.newThreads==0&&metrics.completed==17,"Small batch failed serial threshold");
    Reject([&]{DP::TransformIndexed<std::uint64_t>(8193,4,ValueOperation{},pool);},"Oversized batch accepted");
    Reject([&]{DP::TransformIndexed<std::uint64_t>(0,3,ValueOperation{},pool);},"Invalid worker count accepted");
    bool rejected=false;
    try{DP::TransformIndexed<std::uint64_t>(2048,4,ThrowingOperation{},pool,&metrics);}catch(const IndexedError& error){rejected=error.index==7;}
    Check(rejected&&metrics.failedIndex==7,"Lowest indexed worker failure was not propagated");
    const auto recovered=DP::TransformIndexed<std::uint64_t>(2048,2,ValueOperation{},pool,&metrics);
    Check(recovered[2047]==ValueOperation{}(2047)&&metrics.newThreads==0&&metrics.workersUsed==2,"Pool did not recover after a failed batch");
    bool wrongOwner=false;
    std::thread other([&]{try{DP::TransformIndexed<std::uint64_t>(2048,2,ValueOperation{},pool);}catch(const std::logic_error&){wrongOwner=true;}});other.join();
    Check(wrongOwner,"Wrong owner dispatched the persistent pool");
    for(unsigned failAfter=0;failAfter<4;++failAfter){
        unsigned attempts=0;DP::WorkerPool<FailingFactory> failing(FailingFactory{&attempts,failAfter});
        const auto fallback=DP::TransformIndexed<std::uint64_t>(2048,4,ValueOperation{},failing,&metrics);
        Check(metrics.serialFallback&&metrics.workersUsed==0&&metrics.completed==2048,"Launch failure did not complete the serial fallback");
        Check(fallback[17]==ValueOperation{}(17)&&fallback[2047]==ValueOperation{}(2047),"Serial fallback returned partial values");
        const unsigned before=attempts;
        DP::TransformIndexed<std::uint64_t>(2048,4,ValueOperation{},failing,&metrics);
        Check(attempts==before&&metrics.serialFallback,"Failed pool repeatedly attempted thread creation");
    }
}

void TerrainContracts(){
    auto table=OT::ExpandMaterials({{0,1,1.0f},{1,0,0.5f},{2,1,2.0f}});
    DP::WorkerPool<> pool;DP::Metrics metrics;
    bool first=true;
    for(unsigned mode=0;mode<4;++mode){const auto atlas=Atlas(mode);
        const auto ids=atlas.ids,known=atlas.known;const auto heights=atlas.heights;
        for(unsigned row=0;row<2;++row){const unsigned column=1-row;
            const auto slots=OT::ChunkTop8(atlas,table,static_cast<int>(column*64),static_cast<int>(row*64),64,64,OT::HeightWorldScaleCandidate);
            const auto expected=OriginalSerial(atlas,table,slots,column,row);
            std::printf("SCALAR_CASE key=map%u_row%u signature=%016llx\n",mode,row,static_cast<unsigned long long>(Signature(expected)));
            for(const unsigned workers:{0u,2u,4u}){
                const auto actual=OT::PrepareTerrainVertices<Vertex>(atlas,table,slots,column,row,workers,pool,&metrics);Equal(actual,expected);
                if(slots.count&&workers){
                    Check(metrics.workersUsed==workers&&metrics.completed==4225,"Useful terrain vertex work did not use its requested lanes");
                    for(unsigned lane=0;lane<workers;++lane){Check(metrics.laneJobs[lane]>0,"Parallel lane did not compute vertices");
                        for(unsigned other=0;other<lane;++other)Check(metrics.laneThreads[lane]!=metrics.laneThreads[other],"Worker lanes share one thread identity");}
                    parallelVertexJobs+=metrics.completed;
                    if(workers==4&&first){first=false;Check(metrics.newThreads==2,"Pool did not grow from two to four threads");}
                    else if(workers==4)Check(metrics.newThreads==0,"Persistent pool recreated mesh threads");
                }else Check(metrics.workersUsed==0,"Sparse/explicit serial mesh used background work");
            }
        }
        Check(atlas.ids==ids&&atlas.known==known&&std::memcmp(atlas.heights.data(),heights.data(),heights.size()*sizeof(float))==0,"Terrain preparation changed immutable inputs");
    }
    auto atlas=Atlas(0);const auto slots=OT::ChunkTop8(atlas,table,0,0,64,64,OT::HeightWorldScaleCandidate);
    Reject([&]{OT::PrepareTerrainVertices<Vertex>(atlas,table,slots,2,0,4,pool);},"Noncanonical wrapped column accepted");
    Reject([&]{OT::PrepareTerrainVertices<Vertex>(atlas,table,slots,0,2,4,pool);},"Noncanonical wrapped row accepted");
    auto badSlots=slots;badSlots.count=9;Reject([&]{OT::PrepareTerrainVertices<Vertex>(atlas,table,badSlots,0,0,4,pool);},"Unbounded slot count accepted");
    badSlots=slots;badSlots.count=2;badSlots.materials[1]=badSlots.materials[0];Reject([&]{OT::PrepareTerrainVertices<Vertex>(atlas,table,badSlots,0,0,4,pool);},"Duplicate slot accepted");
    auto broken=atlas;broken.known.pop_back();Reject([&]{OT::PrepareTerrainVertices<Vertex>(broken,table,slots,0,0,4,pool);},"Incomplete immutable atlas accepted");
    atlas.heights[0]=(std::numeric_limits<float>::quiet_NaN)();Reject([&]{OT::PrepareTerrainVertices<Vertex>(atlas,table,slots,0,0,4,pool);},"Known NaN did not fail the whole batch");
    atlas=Atlas(0);
    const unsigned saved=_mm_getcsr();
    for(const unsigned rounding:{0u,0x2000u,0x4000u,0x6000u}){
        _mm_setcsr((saved&~0x603fu)|rounding|0x8040u);
        const auto expected=OriginalSerial(atlas,table,slots,0,0);
        std::printf("SCALAR_CASE key=round%u signature=%016llx\n",rounding,static_cast<unsigned long long>(Signature(expected)));
        const auto actual=OT::PrepareTerrainVertices<Vertex>(atlas,table,slots,0,0,4,pool,&metrics);Equal(actual,expected);
        parallelVertexJobs+=metrics.completed;
        Check((_mm_getcsr()&0xffc0u)==(((saved&~0x6000u)|rounding|0x8040u)&0xffc0u),"Parallel preparation changed caller FP control");
    }
    _mm_setcsr(saved);
}

int main(){try{PoolContracts();TerrainContracts();std::printf("PASS_PARALLEL_TERRAIN checks=%u vertices=%llu useful_parallel_vertex_jobs=%llu vertex_digest=%016llx max_workers=4 runtime_executed=0\n",checks,
    static_cast<unsigned long long>(verticesChecked),static_cast<unsigned long long>(parallelVertexJobs),static_cast<unsigned long long>(vertexDigest));return 0;
}catch(const std::exception& error){std::fprintf(stderr,"FAIL_PARALLEL_TERRAIN %s\n",error.what());return 1;}}
