#pragma once
#include "OriginalTerrainPatchPlacement.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <limits>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalTerrain { namespace Lod {

// The four diagonals of the source AABB are projected and divided by W.
// The retail footprint is a quarter of the largest NDC diagonal times the
// active target width. A box crossing the near plane needs the finest grid.
inline double ProjectedFootprint(const PatchWorld::Placement& cell,const std::array<float,16>& vp,
                                 unsigned viewportWidth,float lowHeight,float highHeight){
    struct Corner {double x,y,w;};
    std::array<Corner,8> corners;
    const auto origin=PatchWorld::DisplayOrigin(cell);
    const double width=static_cast<double>(cell.grid[2])/OriginalTerrainCacheSampling::SourceTexelsPerHex;
    const double depth=static_cast<double>(cell.grid[3])*RowSpacing/OriginalTerrainCacheSampling::SourceTexelsPerHex;
    unsigned commonOutside=63;
    bool crossesNear=false;
    for(unsigned i=0;i<corners.size();++i){
        const double x=origin[0]+((i&1)?width:0),y=(i&2)?highHeight:lowHeight,z=origin[1]-((i&4)?depth:0);
        const auto clip=[&](unsigned k){return x*vp[k]+y*vp[4+k]+z*vp[8+k]+vp[12+k];};
        const double cx=clip(0),cy=clip(1),cz=clip(2),cw=clip(3);
        corners[i]={cx,cy,cw};
        const unsigned outside=(cx< -cw?1u:0u)|(cx>cw?2u:0u)|(cy< -cw?4u:0u)|
                               (cy>cw?8u:0u)|(cz<0?16u:0u)|(cz>cw?32u:0u);
        commonOutside&=outside;
        crossesNear|=cw<=0 || cz<=0;
    }
    if(commonOutside)return 0;
    if(crossesNear)return (std::numeric_limits<double>::infinity)();
    double longestSquared=0;
    for(unsigned i=0;i<4;++i){
        const auto& a=corners[i];const auto& b=corners[7-i];
        const double dx=a.x/a.w-b.x/b.w,dy=a.y/a.w-b.y/b.w;
        longestSquared=(std::max)(longestSquared,dx*dx+dy*dy);
    }
    return std::sqrt(longestSquared)*viewportWidth*0.25;
}

inline float RequestedLevel(double footprint,unsigned intervals,unsigned targetPixels,unsigned subdivisions){
    if(!(footprint>=0) || !intervals || !targetPixels || !subdivisions)
        throw std::invalid_argument("Invalid projected terrain detail inputs");
    const double demand=(std::max)(1.0,footprint*0.5/(static_cast<double>(targetPixels)*subdivisions));
    const double level=0.5+std::log2(intervals/demand);
    return static_cast<float>((std::max)(-2.0,(std::min)(4.0,level)));
}

struct History {
    float accepted=0,band=0;
    unsigned GridLevel() const noexcept {return static_cast<unsigned>((std::max)(0.0f,std::floor(accepted)));}

    History Update(float requested) const {
        if(!std::isfinite(requested) || requested< -2 || requested>4)
            throw std::invalid_argument("Invalid terrain detail request");
        const float delta=requested-accepted;
        if(delta==0 || (std::abs(delta)<=std::abs(band) && delta*band<0))return *this;
        const float transition=std::floor(requested)-std::floor(accepted);
        return {requested,transition==0?band:transition*0.25f};
    }
};

struct GridIndices {
    std::vector<std::uint16_t> controls,rim;
};

inline GridIndices BuildGridIndices(unsigned level){
    constexpr unsigned side=PatchWorld::CellIntervals;
    if(level>PatchWorld::MaxLevel)throw std::invalid_argument("Invalid terrain index level");
    const unsigned step=1u<<level,inner=side/step-2;
    const auto index=[](unsigned x,unsigned y){return static_cast<std::uint16_t>(y*(PatchWorld::CellIntervals+1)+x);};
    GridIndices result;
    result.controls.reserve(16*inner*inner);
    result.rim.reserve(3*4*(side+inner));
    for(unsigned y=step;y<side-step;y+=step)for(unsigned x=step;x<side-step;x+=step){
        for(unsigned dy=0;dy<4;++dy)for(unsigned dx=0;dx<4;++dx)
            result.controls.push_back(index(x-step+dx*step,y-step+dy*step));
    }
    if(level==0){
        // Preserve the existing winding and diagonal of every full-detail rim quad.
        for(unsigned y=0;y<side;++y)for(unsigned x=0;x<side;++x){
            if(x && y && x+1<side && y+1<side)continue;
            const auto a=index(x,y),b=index(x+1,y),c=index(x,y+1),d=index(x+1,y+1);
            result.rim.insert(result.rim.end(),{a,b,c,b,d,c});
        }
        return result;
    }
    // Four trapezoids share corner diagonals. Fan every unit outer segment
    // into the coarse inner row, including at both ends of a side.
    for(unsigned edge=0;edge<4;++edge){
        const auto vertex=[&](unsigned along,unsigned inward){
            switch(edge){
            case 0:return index(along,inward);
            case 1:return index(side-inward,along);
            case 2:return index(side-along,side-inward);
            default:return index(inward,side-along);
            }
        };
        for(unsigned x=0;x<side;x+=step){
            const auto start=vertex((std::clamp)(x,step,side-step),step);
            const auto end=vertex((std::clamp)(x+step,step,side-step),step);
            for(unsigned j=x;j<x+step;++j)
                result.rim.insert(result.rim.end(),{vertex(j,0),vertex(j+1,0),start});
            if(start!=end)result.rim.insert(result.rim.end(),{vertex(x+step,0),end,start});
        }
    }
    return result;
}

}}}
