#pragma once
#include "OriginalFogModel.h"

namespace ZeroSisPresentation { namespace OriginalFog {

// The structural view contract reads only map dimensions/wrapping and each
// plot's coordinate/revealed/visible state. No game or presentation header is required.
template<class View>Grid CaptureFogGrid(const View& view){
    Detail::Require(view.gridWidth>0&&view.gridHeight>0&&view.gridWidth<=256&&view.gridHeight<=256,
        "Invalid original fog view dimensions");
    const auto count=static_cast<std::size_t>(view.gridWidth)*view.gridHeight;
    Detail::Require(count<=16384&&view.plots.size()==count,"Original fog view must contain each bounded map cell exactly once");
    Grid result;result.width=view.gridWidth;result.height=view.gridHeight;
    result.wrapX=view.wrapX;result.wrapY=view.wrapY;result.cells.resize(count);
    std::vector<unsigned char> seen(count,0);
    for(const auto& plot:view.plots){
        Detail::Require(plot.x>=0&&plot.y>=0&&plot.x<result.width&&plot.y<result.height&&
            (!plot.visible||plot.revealed),"Invalid original fog view cell coordinate or visibility");
        const auto index=static_cast<std::size_t>(plot.y)*result.width+plot.x;
        Detail::Require(!seen[index],"Duplicate original fog view cell coordinate");seen[index]=1;
        result.cells[index]={plot.revealed,plot.visible};
    }
    Detail::GridShape(result);return result;
}

namespace Detail {
inline bool StateGridShape(const Grid& grid) noexcept {
    return grid.width>0&&grid.height>0&&grid.width<=256&&grid.height<=256&&
        static_cast<std::size_t>(grid.width)*grid.height<=16384&&
        grid.cells.size()==static_cast<std::size_t>(grid.width)*grid.height&&(!grid.wrapY||grid.height%2==0);
}
}
// Invalid grids are never reusable keys, even if two malformed values match.
inline bool SameFogGrid(const Grid& a,const Grid& b) noexcept {
    if(!Detail::StateGridShape(a)||!Detail::StateGridShape(b)||a.width!=b.width||a.height!=b.height||
        a.wrapX!=b.wrapX||a.wrapY!=b.wrapY)return false;
    for(std::size_t i=0;i<a.cells.size();++i){const auto& x=a.cells[i];const auto& y=b.cells[i];
        if((x.visible&&!x.revealed)||(y.visible&&!y.revealed)||x.revealed!=y.revealed||x.visible!=y.visible)return false;
    }
    return true;
}
}}
