#pragma once
#include "OriginalTerrainModel.h"
#include "OriginalTerrainBinding.h"
#include "OriginalTerrainPatchPlacement.h"
#include "WorldViewRenderer.h"
#include <algorithm>
#include <array>
#include <cmath>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalTerrain {
inline void GeometryRequire(bool value,const char* message){if(!value)throw std::invalid_argument(message);}
inline PatchWorld::Frame PatchFrameForCamera(const Atlas& atlas,int cameraColumn,int cameraRow){
    Detail::AtlasShape(atlas);
    GeometryRequire(cameraColumn>=0 && cameraRow>=0 &&
        static_cast<unsigned>(cameraColumn)<atlas.width/TexelsPerHex &&
        static_cast<unsigned>(cameraRow)<atlas.height/TexelsPerHex,"Invalid terrain patch camera plot");
    const auto cube=OffsetToCube(cameraColumn,cameraRow);
    const auto source=CubeToSourceTexel({static_cast<double>(cube.x),static_cast<double>(cube.y),static_cast<double>(cube.z)});
    // The current mesh has 64 intervals and a shared terminal vertex per
    // chunk; the atlas stores only the owned texels. Height sampling applies
    // its own boundary/visibility policy to that terminal vertex.
    const unsigned samplesX=atlas.width+1,samplesY=atlas.height+1;
    return {samplesX,samplesY,
        PatchWorld::NativeWorld(source.x-atlas.originX,samplesX,OriginalTerrainCacheSampling::SourceMetricXDefault),
        PatchWorld::NativeWorld(source.y-atlas.originY,samplesY,OriginalTerrainCacheSampling::SourceMetricYDefault)};
}
inline int WrappedCoordinate(int value,int span){
    if(value>=0 && value<span)return value;
    const int r=value%span;return r<0?r+span:r;
}
inline bool HasPatchControls(const Atlas& atlas,unsigned column,unsigned row){
    Detail::AtlasShape(atlas);
    const unsigned side=PatchWorld::CellIntervals;
    GeometryRequire(atlas.width%side==0 && atlas.height%side==0 &&
        column<atlas.width/side && row<atlas.height/side,"Invalid patch control cell");
    const unsigned x=column*side,y=row*side;
    const bool wrapsLastColumn=x+side==atlas.width,wrapsLastRow=y+side==atlas.height;
    if((wrapsLastColumn&&!atlas.wrapX)||(wrapsLastRow&&!atlas.wrapY))return false;
    for(unsigned i=0;i<=side;++i){
        const auto iy=y+i==atlas.height?0:y+i;
        const auto start=atlas.known.begin()+static_cast<std::size_t>(iy)*atlas.width;
        const auto first=start+x,end=first+(wrapsLastColumn?side:side+1);
        if(!std::all_of(first,end,[](std::uint8_t k){return k==1;}) || (wrapsLastColumn && *start!=1))return false;
    }
    return true;
}
inline std::array<int,2> WorldTile(double x,double z,int width,int height,bool wrapX,bool wrapY){
    GeometryRequire(width>0 && height>0 && std::isfinite(x) && std::isfinite(z) &&
        std::abs(x)<1000000 && std::abs(z)<1000000,"Invalid original terrain world coordinate");
    const double row=-z/RowSpacing;const double q=x-row*0.5;
    auto cell=CubeToOffset(RoundCube({q,row,-q-row}));
    if(wrapX)cell[0]=WrappedCoordinate(cell[0],width);
    if(wrapY)cell[1]=WrappedCoordinate(cell[1],height);
    if(cell[0]<0 || cell[0]>=width || cell[1]<0 || cell[1]>=height)return {{-1,-1}};
    return cell;
}
inline int TerrainTypeForFixture(const WorldViewPlot& p){
    if(p.terrainId>=0)return p.terrainId;
    if(p.terrain=="TERRAIN_GRASS")return 0;
    if(p.terrain=="TERRAIN_DESERT")return 2;
    if(p.terrain=="TERRAIN_TUNDRA")return 3;
    if(p.terrain=="TERRAIN_SNOW")return 4;
    if(p.terrain=="TERRAIN_COAST")return 5;
    if(p.terrain=="TERRAIN_OCEAN")return 6;
    return 1;
}
inline std::vector<Cell> CaptureTerrainCells(const WorldView& view){
    GeometryRequire(view.gridWidth>0 && view.gridHeight>0 && view.gridWidth<=256 && view.gridHeight<=256 &&
        static_cast<std::size_t>(view.gridWidth)*view.gridHeight<=16384,"Original terrain atlas exceeds the controlled map bound");
    PlotInput missing{};missing.exists=false;missing.revealed=false;
    std::vector<Cell> result(static_cast<std::size_t>(view.gridWidth)*view.gridHeight,MakeCell(missing));
    std::vector<bool> seen(result.size()),seenIds(result.size());
    for(const auto& p:view.plots){
        GeometryRequire(p.x>=0 && p.y>=0 && p.x<view.gridWidth && p.y<view.gridHeight && p.index>=0 &&
            static_cast<std::size_t>(p.index)<result.size() &&
            !(p.visible&&!p.revealed),"Invalid original terrain plot identity or visibility");
        const auto index=static_cast<std::size_t>(p.y)*view.gridWidth+p.x;
        GeometryRequire(!seen[index] && !seenIds[static_cast<std::size_t>(p.index)],"Duplicate original terrain plot coordinate or ID");
        seen[index]=true;seenIds[static_cast<std::size_t>(p.index)]=true;
        PlotInput input;input.revealed=p.revealed;
        if(p.revealed){input.terrainType=TerrainTypeForFixture(p);input.continent=p.continent;
            input.hills=p.hills;input.mountain=p.mountain;input.naturalWonder=p.naturalWonder;input.feature=p.feature;}
        result[index]=MakeCell(input);
    }
    return result;
}
inline bool SameTerrainCells(const std::vector<Cell>& a,const std::vector<Cell>& b){
    if(a.size()!=b.size())return false;
    for(std::size_t i=0;i<a.size();++i)if(a[i].mask!=b[i].mask || a[i].continent!=b[i].continent || a[i].revealed!=b[i].revealed)return false;
    return true;
}
inline float AtlasHeight(const Atlas& atlas,double x,double y){
    Detail::AtlasShape(atlas);
    GeometryRequire(std::isfinite(x) && std::isfinite(y) && std::abs(x)<1000000 && std::abs(y)<1000000,
        "Invalid original terrain height coordinate");
    const auto ix=static_cast<int>(std::floor(x)),iy=static_cast<int>(std::floor(y));
    const float fx=static_cast<float>(x-ix),fy=static_cast<float>(y-iy);float value=0,total=0;
    for(int dy=0;dy<=1;++dy)for(int dx=0;dx<=1;++dx){
        const auto index=static_cast<std::size_t>(WrappedCoordinate(iy+dy,static_cast<int>(atlas.height)))*atlas.width+
            static_cast<unsigned>(WrappedCoordinate(ix+dx,static_cast<int>(atlas.width)));
        if(!atlas.known[index])continue;
        const float weight=(dx?fx:1-fx)*(dy?fy:1-fy);if(weight==0)continue;
        GeometryRequire(std::isfinite(atlas.heights[index]),"Nonfinite known original terrain height");
        value+=atlas.heights[index]*weight;total+=weight;
    }
    return total>0?value/total:0;
}
inline float AtlasWorldHeight(const Atlas& atlas,double x,double y){
    Detail::AtlasShape(atlas);
    GeometryRequire(std::isfinite(x)&&std::isfinite(y)&&std::abs(x)<1000000&&std::abs(y)<1000000,
        "Invalid original terrain world-height coordinate");
    const int ix=static_cast<int>(std::floor(x)),iy=static_cast<int>(std::floor(y));
    const float fx=static_cast<float>(x-ix),fy=static_cast<float>(y-iy);float value=0,total=0;
    // Mesh and lighting-field vertices land on integer texels. Visit only
    // contributing taps and resolve the row once for fractional water samples.
    for(int dy=0;dy<2;++dy){
        const float wy=dy?fy:1-fy;
        if(wy==0)continue;
        int py=iy+dy;
        if(atlas.wrapY)py=WrappedCoordinate(py,static_cast<int>(atlas.height));
        else if(py<0||py>=static_cast<int>(atlas.height))continue;
        const auto row=static_cast<std::size_t>(py)*atlas.width;
        for(int dx=0;dx<2;++dx){
            const float weight=(dx?fx:1-fx)*wy;
            if(weight==0)continue;
            int px=ix+dx;
            if(atlas.wrapX)px=WrappedCoordinate(px,static_cast<int>(atlas.width));
            else if(px<0||px>=static_cast<int>(atlas.width))continue;
            const auto index=row+static_cast<unsigned>(px);
            if(!atlas.known[index])continue;
            const auto raw=Detail::HeightmapCode(atlas,index);
            const float height=OriginalTerrainCacheSampling::NormalizeOriginalHeight(raw,DisplayHeightOriginCandidate());
            value+=height*weight;total+=weight;
        }
    }
    return total>0?value/total:0;
}
}}
