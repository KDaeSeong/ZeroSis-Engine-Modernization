#pragma once

#include "OriginalTerrainCacheSamplingModel.h"
#include <array>
#include <cmath>
#include <cstdint>
#include <stdexcept>

namespace ZeroSisPresentation { namespace OriginalTerrain {

// Plot picking uses the logical hex grid. The retail terrain's physical Y
// metric is 0.866f; keep that conversion separate from display row spacing.
constexpr float RowSpacing=0.866025404f;

namespace PatchWorld {
constexpr unsigned CellIntervals=64;
constexpr unsigned MaxLevel=4;

struct Axis {
    unsigned firstTexel;
    unsigned intervals;
    unsigned patches;
    float spacing;
};

// The descriptor counts samples, including both endpoints of the surface.
inline Axis CellAxis(unsigned samples,unsigned cell,unsigned level){
    if(samples<2 || cell>(samples-2)/CellIntervals || level>MaxLevel)
        throw std::invalid_argument("Invalid terrain patch cell or level");
    const unsigned first=cell*CellIntervals;
    const unsigned remaining=samples-1-first;
    const unsigned span=remaining<CellIntervals?remaining:CellIntervals;
    unsigned nodes=span+1;
    for(unsigned i=0;i<level;++i)nodes=(nodes>>1)+1;
    return {first,span,nodes-1,static_cast<float>(span)/static_cast<float>(nodes-1)};
}

struct Placement {
    // Camera-relative source texels, followed by source texels per patch.
    std::array<float,4> originSpacing;
    // Patch columns, patch rows, exact cell width and height in intervals.
    std::array<std::uint32_t,4> grid;
};

struct Frame {
    unsigned samplesX,samplesY;
    double cameraWorldX,cameraWorldY; // centered native XY; Z is height in the native system
};

inline double NativeWorld(double texel,unsigned samples,float metric) noexcept {
    return (texel-static_cast<double>(samples/2))*metric;
}

inline Placement Place(const Frame& frame,unsigned column,unsigned row,
                       int drawColumn,int drawRow,unsigned level){
    const Axis x=CellAxis(frame.samplesX,column,level);
    const Axis y=CellAxis(frame.samplesY,row,level);
    // Resolve the canonical mesh before shifting its image on a wrapped map.
    // Subtract the camera in the same centered source space, before narrowing
    // to float. Page offsets used to sample the height texture never enter XY.
    const auto relative=[](const Axis& axis,unsigned samples,double camera,unsigned canonical,int draw,float metric){
        const auto cellCount=1+(samples-2)/CellIntervals;
        const std::int64_t difference=static_cast<std::int64_t>(draw)-canonical;
        if(difference%cellCount!=0)throw std::invalid_argument("Draw copy and canonical patch cell differ");
        const double copy=static_cast<double>(difference/cellCount)*(samples-1);
        const double origin=(NativeWorld(axis.firstTexel+copy,samples,metric)-camera)/metric;
        if(!std::isfinite(origin) || std::abs(origin)+axis.intervals>16777216.0)
            throw std::invalid_argument("Terrain patch texels exceed float coordinate precision");
        return static_cast<float>(origin);
    };
    return {{{relative(x,frame.samplesX,frame.cameraWorldX,column,drawColumn,OriginalTerrainCacheSampling::SourceMetricXDefault),
              relative(y,frame.samplesY,frame.cameraWorldY,row,drawRow,OriginalTerrainCacheSampling::SourceMetricYDefault),x.spacing,y.spacing}},
            {{x.patches,y.patches,x.intervals,y.intervals}}};
}

inline std::array<float,2> DisplayOrigin(const Placement& where) noexcept {
    constexpr float step=1.0f/OriginalTerrainCacheSampling::SourceTexelsPerHex;
    return {{where.originSpacing[0]*step,where.originSpacing[1]*(-RowSpacing*step)}};
}
// One coarse quad on each side is reserved for the join to the original
// unit-spaced chunk boundary. All controls still address the same 65x65 mesh.
inline Placement Interior(const Placement& full,unsigned level=0){
    if(level>MaxLevel || full.grid!=std::array<std::uint32_t,4>{{CellIntervals,CellIntervals,CellIntervals,CellIntervals}})
        throw std::invalid_argument("Invalid terrain interior grid");
    const unsigned step=1u<<level,side=CellIntervals/step-2;
    Placement result=full;
    result.originSpacing[0]+=step;
    result.originSpacing[1]+=step;
    result.originSpacing[2]=result.originSpacing[3]=static_cast<float>(step);
    result.grid={{side,side,side*step,side*step}};
    return result;
}
}}}
