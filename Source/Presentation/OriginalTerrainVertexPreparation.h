#pragma once

#include "DeterministicWorkerPool.h"
#include "OriginalTerrainGeometry.h"
#include "OriginalTerrainBinding.h"
#include <cstring>

namespace ZeroSisPresentation { namespace OriginalTerrain {

using TerrainPreparationMetrics=DeterministicParallel::Metrics;

inline unsigned AutomaticTerrainWorkers() noexcept {
    return DeterministicParallel::ResolveWorkers(std::thread::hardware_concurrency());
}

namespace VertexPreparationDetail {
inline DeterministicParallel::WorkerPool<>& Pool(){
    static thread_local DeterministicParallel::WorkerPool<> pool;
    return pool;
}
template<class Vertex>struct PrepareVertex {
    const Atlas& atlas;
    const MaterialTable& table;
    const ChunkSlots slots;
    const int startX,startY;
    const unsigned divisions;
    Vertex operator()(std::size_t index) const {
        const unsigned side=divisions+1,x=static_cast<unsigned>(index%side),y=static_cast<unsigned>(index/side);
        const float u=static_cast<float>(x)/static_cast<float>(divisions),v=static_cast<float>(y)/static_cast<float>(divisions);
        const int px=startX+static_cast<int>(x*(64/divisions)),py=startY+static_cast<int>(y*(64/divisions));
        const auto normal=SurfaceNormal(atlas,px,py,HeightWorldScaleCandidate);
        const auto fetched=OriginalTerrainNormal::QuantizeVertexNormal({normal.x,normal.y,normal.z});
        const auto weights=QuantizeWeights(KernelWeights(atlas,table,slots,px,py,normal));
        std::uint32_t w0=0,w1=0;std::memcpy(&w0,weights.data(),4);std::memcpy(&w1,weights.data()+4,4);
        const float height=AtlasWorldHeight(atlas,px,py);
        const float light=0.48f+0.52f*std::abs((-normal.x*0.4f+normal.y*0.4f+normal.z*0.8f)/0.979795897f);
        return {u,height,-v*RowSpacing,u,v,light,w0,w1,fetched.x,fetched.y,fetched.z};
    }
};
}

// Atlas/table are caller-owned immutable storage for this synchronous call.
// Only the returned 44-byte vertex slots are written by workers. Chunk material
// selection, D3D upload and cache publication remain on the renderer owner.
template<class Vertex,class Factory>
std::vector<Vertex> PrepareTerrainVertices(const Atlas& atlas,const MaterialTable& table,const ChunkSlots& slots,
    unsigned column,unsigned row,unsigned workers,DeterministicParallel::WorkerPool<Factory>& pool,
    TerrainPreparationMetrics* diagnostics=nullptr){
    static_assert(sizeof(Vertex)==44,"Original terrain vertex layout differs");
    Detail::AtlasShape(atlas);const unsigned materials=Detail::TableSize(table);
    Detail::Require(atlas.width%64==0&&atlas.height%64==0&&column<atlas.width/64&&row<atlas.height/64,
        "Invalid canonical terrain vertex chunk");
    Detail::Require(slots.count<=8,"Invalid terrain vertex material slots");
    std::array<bool,64> seen{};
    for(unsigned i=0;i<slots.count;++i){
        Detail::Require(slots.materials[i]<materials&&!seen[slots.materials[i]],"Duplicate or invalid terrain vertex material");
        seen[slots.materials[i]]=true;
    }
    const unsigned divisions=slots.count?64u:1u;
    const VertexPreparationDetail::PrepareVertex<Vertex> operation{atlas,table,slots,
        static_cast<int>(column*64),static_cast<int>(row*64),divisions};
    return DeterministicParallel::TransformIndexed<Vertex>(static_cast<std::size_t>(divisions+1)*(divisions+1),workers,operation,pool,diagnostics);
}

template<class Vertex>
std::vector<Vertex> PrepareTerrainVertices(const Atlas& atlas,const MaterialTable& table,const ChunkSlots& slots,
    unsigned column,unsigned row,unsigned workers=AutomaticTerrainWorkers(),TerrainPreparationMetrics* diagnostics=nullptr){
    return PrepareTerrainVertices<Vertex>(atlas,table,slots,column,row,workers,VertexPreparationDetail::Pool(),diagnostics);
}

}}
