#pragma once
#include "OriginalWaterModel.h"

namespace ZeroSisPresentation { namespace OriginalWater {

// Only explored fields are copied. The source's hidden water, relief, terrain,
// river flags and flow values are not evaluated, including their validity checks.
template<class View>Grid CaptureWaterGrid(const View& view){
    Detail::Require(view.gridWidth>0&&view.gridHeight>0&&view.gridWidth<=256&&view.gridHeight<=256,
        "Invalid original water view dimensions");
    const auto count=static_cast<std::size_t>(view.gridWidth)*view.gridHeight;
    Detail::Require(count<=MaxCells&&view.plots.size()==count,"Original water view requires exact bounded map coverage");
    Grid result;result.width=view.gridWidth;result.height=view.gridHeight;
    result.wrapX=view.wrapX;result.wrapY=view.wrapY;result.cells.resize(count);
    std::vector<unsigned char> seen(count,0);
    for(const auto& plot:view.plots){
        Detail::Require(plot.x>=0&&plot.y>=0&&plot.x<result.width&&plot.y<result.height&&(!plot.visible||plot.revealed),
            "Invalid original water plot coordinate or visibility");
        const auto index=static_cast<std::size_t>(plot.y)*result.width+plot.x;
        Detail::Require(!seen[index],"Duplicate original water plot coordinate");seen[index]=1;
        if(!plot.revealed)continue;
        auto& cell=result.cells[index];cell.revealed=true;
        cell.water=plot.water;cell.lake=plot.lake;cell.hills=plot.hills;cell.mountain=plot.mountain;cell.terrainId=plot.terrainId;
        cell.river={{plot.riverW,plot.riverNW,plot.riverNE}};
        if(cell.river[0])cell.flow[0]=plot.flowE;
        if(cell.river[1])cell.flow[1]=plot.flowSE;
        if(cell.river[2])cell.flow[2]=plot.flowSW;
    }
    Detail::Validate(result);return result;
}
inline bool SameWaterGrid(const Grid& a,const Grid& b) noexcept {
    if(!Detail::Shape(a)||!Detail::Shape(b)||a.width!=b.width||a.height!=b.height||a.wrapX!=b.wrapX||a.wrapY!=b.wrapY)return false;
    for(std::size_t index=0;index<a.cells.size();++index){const auto& x=a.cells[index];const auto& y=b.cells[index];
        if(x.revealed!=y.revealed)return false;if(!x.revealed)continue;
        if(!Detail::ValidCell(x)||!Detail::ValidCell(y)||x.water!=y.water||x.lake!=y.lake||x.hills!=y.hills||
            x.mountain!=y.mountain||x.terrainId!=y.terrainId)return false;
        for(unsigned slot=0;slot<3;++slot)if(x.river[slot]!=y.river[slot]||(x.river[slot]&&x.flow[slot]!=y.flow[slot]))return false;
    }
    return true;
}
}}
