#include "OriginalTerrainGeometry.h"
#include "WorldTerrainReuse.h"
#include <cstdio>
#include <limits>
#include <set>

using namespace ZeroSisPresentation;
using namespace ZeroSisPresentation::OriginalTerrain;
namespace {
unsigned checks=0,polygonSamples=0;
constexpr double ReferenceSpacing=0.86602540378443864676372317075294;
void Require(bool value){++checks;if(!value)throw std::runtime_error("Original terrain geometry regression");}
template<class Action>void Reject(Action action){
    bool rejected=false;try{action();}catch(const std::invalid_argument&){rejected=true;}Require(rejected);
}
struct IntPoint {long long u,v;};
long long Cross(IntPoint a,IntPoint b,IntPoint p){return (b.u-a.u)*(p.v-a.v)-(b.v-a.v)*(p.u-a.u);}
bool InTriangle(IntPoint a,IntPoint b,IntPoint c,IntPoint p){
    const auto x=Cross(a,b,p),y=Cross(b,c,p),z=Cross(c,a,p);
    return (x>=0 && y>=0 && z>=0)||(x<=0 && y<=0 && z<=0);
}
int Parity(int row){const int p=row%2;return p<0?p+2:p;}
int Modulo(int value,int span){while(value<0)value+=span;while(value>=span)value-=span;return value;}
bool InHex(int column,int row,IntPoint p,long long scale){
    const IntPoint center={(2ll*column+Parity(row))*scale,3ll*row*scale};
    const int corners[6][2]={{0,-2},{1,-1},{1,1},{0,2},{-1,1},{-1,-1}};
    for(unsigned i=0;i<6;++i){
        const auto j=(i+1)%6;
        const IntPoint a={center.u+corners[i][0]*scale,center.v+corners[i][1]*scale};
        const IntPoint b={center.u+corners[j][0]*scale,center.v+corners[j][1]*scale};
        if(InTriangle(center,a,b,p))return true;
    }
    return false;
}
std::set<std::array<int,2>> ReferenceOwners(IntPoint point,long long scale,int width,int height,bool wrapX,bool wrapY){
    std::set<std::array<int,2>> owners;
    const int nearColumn=static_cast<int>(point.u/(2*scale)),nearRow=static_cast<int>(point.v/(3*scale));
    for(int row=nearRow-3;row<=nearRow+3;++row)for(int column=nearColumn-3;column<=nearColumn+3;++column){
        if(!InHex(column,row,point,scale))continue;
        int x=column,y=row;if(wrapX)x=Modulo(x,width);if(wrapY)y=Modulo(y,height);
        owners.insert(x<0||y<0||x>=width||y>=height?std::array<int,2>{{-1,-1}}:std::array<int,2>{{x,y}});
    }
    return owners;
}
void PolygonReference(){
    const int width=4,height=3;const long long scale=12;
    for(unsigned wrap=0;wrap<4;++wrap){
        const bool wrapX=(wrap&1)!=0,wrapY=(wrap&2)!=0;
        for(long long v=-24;v<=132;v+=2)for(long long u=-24;u<=120;u+=2){
            const auto owners=ReferenceOwners({u,v},scale,width,height,wrapX,wrapY);Require(!owners.empty());
            const double x=static_cast<double>(u)/(2.0*static_cast<double>(scale)),z=-static_cast<double>(v)*ReferenceSpacing/(3.0*static_cast<double>(scale));
            const auto actual=WorldTile(x,z,width,height,wrapX,wrapY);
            Require(owners.count(actual)!=0);++polygonSamples;
        }
    }
    // One global one-texel triangle crosses the sloped edge between two plots.
    // Interior fragments must use interpolated world position, not one flat ID.
    std::set<std::array<int,2>> triangleOwners;
    const int weights[2][3]={{2,12,2},{2,2,12}};
    for(const auto& w:weights){
        const int px=w[0]+2*w[1]+w[2],py=22*w[0]+22*w[1]+23*w[2];
        const double x=static_cast<double>(px)/1024+0.5,z=-static_cast<double>(py)*ReferenceSpacing/1024;
        const auto actual=WorldTile(x,z,4,3,false,false);
        const auto owners=ReferenceOwners({2ll*px+1024,3ll*py},1024,4,3,false,false);
        Require(owners.size()==1 && owners.count(actual)==1);triangleOwners.insert(actual);
    }
    Require(triangleOwners.size()==2);
}
void CoordinateRoundTrips(){
    for(int row=-17;row<=17;++row)for(int column=-17;column<=17;++column){
        const auto cube=OffsetToCube(column,row);Require(CubeToOffset(cube)==std::array<int,2>({{column,row}}));
        const auto source=CubeToSourceTexel({static_cast<double>(cube.x),static_cast<double>(cube.y),static_cast<double>(cube.z)});
        const double expectedX=(column+Parity(row)*0.5-0.5)*64,expectedY=row*64.0;
        Require(source.x==expectedX && source.y==expectedY);
        Require(CubeToOffset(RoundCube(SourceTexelToCube(source.x,source.y)))==std::array<int,2>({{column,row}}));
        const double worldX=source.x/64+0.5,worldZ=-source.y*ReferenceSpacing/64;
        const auto actual=WorldTile(worldX,worldZ,4,3,true,true);
        Require(actual==std::array<int,2>({{Modulo(column,4),Modulo(row,3)}}));
    }
    const double samples[]={-129,-64,-32,-1,-0.5,0,0.5,1,31.5,64,128};
    for(const auto px:samples)for(const auto py:samples){
        const auto cube=SourceTexelToCube(px,py);const auto source=CubeToSourceTexel(cube);
        Require(std::abs(source.x-px)<1e-12 && std::abs(source.y-py)<1e-12);
    }
    Reject([](){WorldTile(0,0,0,3,false,false);});Reject([](){WorldTile(0,0,4,-1,false,false);});
    Reject([](){WorldTile(std::numeric_limits<double>::quiet_NaN(),0,4,3,false,false);});
    Reject([](){WorldTile(0,std::numeric_limits<double>::infinity(),4,3,false,false);});
    Reject([](){WorldTile(1000000,0,4,3,false,false);});
    Require(WorldTile(-3,0,4,3,false,false)==std::array<int,2>({{-1,-1}}));
}
WorldView View(){
    WorldView view{};view.gridWidth=view.gridHeight=3;view.wrapX=true;view.wrapY=false;view.mapRandomSeed=17;
    view.terrainAssetsPath=L"sealed-original-terrain.bin";
    for(int y=0;y<3;++y)for(int x=0;x<3;++x){
        WorldViewPlot plot{};plot.index=y*3+x;plot.x=x;plot.y=y;plot.revealed=plot.visible=true;
        plot.continent=1;plot.terrainId=0;plot.terrain="TERRAIN_GRASS";view.plots.push_back(plot);
    }
    view.plots[4].revealed=view.plots[4].visible=false;return view;
}
void Word(std::vector<unsigned char>& bytes,std::uint32_t value){
    for(unsigned i=0;i<4;++i)bytes.push_back(static_cast<unsigned char>(value>>(i*8)));
}
PieceLibrary UniformLibrary(){
    PieceLibrary library;library.materialRowCount=41;library.rowCount=512;library.rowsAt=0;
    for(unsigned image=0;image<4;++image)for(unsigned row=0;row<128;++row)Word(library.bytes,(image==0?row:(image-1)*128+row)*2);
    library.runs8At=library.bytes.size();library.runs8Count=768;
    for(unsigned image=1;image<4;++image)for(unsigned row=0;row<128;++row){library.bytes.push_back(128);library.bytes.push_back(static_cast<unsigned char>(image==1?11:255));}
    library.runs16At=library.bytes.size();library.runs16Count=256;
    for(unsigned row=0;row<128;++row){library.bytes.push_back(128);library.bytes.push_back(0);library.bytes.push_back(0);library.bytes.push_back(128);}
    Piece piece;piece.index=0;piece.level=1;piece.imageSize=128;piece.imageRows={{0,128,256,384}};
    library.pieces.push_back(piece);return library;
}
void InformationBoundary(){
    const auto view=View();auto hidden=view;
    hidden.plots[4].terrainId=999;hidden.plots[4].continent=999;hidden.plots[4].terrain="TERRAIN_SNOW";
    hidden.plots[4].feature="FEATURE_FUJI";hidden.plots[4].naturalWonder=true;
    hidden.plots[4].hills=hidden.plots[4].mountain=hidden.plots[4].water=true;
    const auto cells=CaptureTerrainCells(view),changed=CaptureTerrainCells(hidden);
    Require(SameTerrainCells(cells,changed) && !cells[4].revealed && cells[4].mask==0 && cells[4].continent==0);
    auto fog=view;fog.plots[8].visible=false;fog.plots[8].hills=true;fog.plots[8].terrainId=4;
    const auto remembered=CaptureTerrainCells(fog);Require(remembered[8].revealed && remembered[8].mask==0x200 && remembered[8].continent==1);
    fog.plots[8].visible=true;Require(SameTerrainCells(remembered,CaptureTerrainCells(fog)));
    auto feature=view;feature.plots[0].feature="FEATURE_FOREST";
    Require(SameTerrainCells(cells,CaptureTerrainCells(feature)));
    feature.plots[0].terrainId=2;Require(CaptureTerrainCells(feature)[0].mask==4);
    const auto library=UniformLibrary();const std::vector<Placement> placements={{0,0,0,0}};
    const auto a=BuildAtlas(cells,3,3,library,placements,0),b=BuildAtlas(changed,3,3,library,placements,0);
    Require(a.ids==b.ids && a.known==b.known && a.heights==b.heights);
    Require(std::any_of(a.heights.begin(),a.heights.end(),[](float value){return value>0.4f;}));
    for(int y=-2;y<=194;y+=7)for(int x=-2;x<=194;x+=7)Require(AtlasHeight(a,x+0.25,y+0.5)==AtlasHeight(b,x+0.25,y+0.5));
    auto poisoned=a;
    for(std::size_t i=0;i<poisoned.known.size();++i)if(!poisoned.known[i]){poisoned.ids[i]=40;poisoned.heights[i]=std::numeric_limits<float>::quiet_NaN();}
    for(int y=-2;y<=194;y+=7)for(int x=-2;x<=194;x+=7)Require(AtlasHeight(a,x+0.25,y+0.5)==AtlasHeight(poisoned,x+0.25,y+0.5));
    auto missing=view;missing.plots.pop_back();Require(!CaptureTerrainCells(missing)[8].revealed);
    auto invalid=view;invalid.plots[0].index=9;Reject([&](){CaptureTerrainCells(invalid);});
    invalid=view;invalid.plots[0].index=-1;Reject([&](){CaptureTerrainCells(invalid);});
    invalid=view;invalid.plots[1].index=0;Reject([&](){CaptureTerrainCells(invalid);});
    invalid=view;invalid.plots[1].x=0;Reject([&](){CaptureTerrainCells(invalid);});
    invalid=view;invalid.plots[0].x=-1;Reject([&](){CaptureTerrainCells(invalid);});
    invalid=view;invalid.plots[0].y=3;Reject([&](){CaptureTerrainCells(invalid);});
    invalid=view;invalid.plots[4].visible=true;Reject([&](){CaptureTerrainCells(invalid);});
    invalid=view;invalid.gridWidth=257;Reject([&](){CaptureTerrainCells(invalid);});
    invalid=view;invalid.gridWidth=invalid.gridHeight=129;Reject([&](){CaptureTerrainCells(invalid);});
}
void HeightsAndCache(){
    Atlas atlas;atlas.width=atlas.height=4;atlas.ids.assign(16,3);atlas.known.assign(16,1);atlas.heights.assign(16,0);
    atlas.heights[0]=2;atlas.heights[1]=10;atlas.heights[4]=6;atlas.heights[5]=99;atlas.known[5]=0;
    Require(AtlasHeight(atlas,0.5,0.5)==6);atlas.heights[5]=std::numeric_limits<float>::quiet_NaN();
    Require(AtlasHeight(atlas,0.5,0.5)==6 && AtlasHeight(atlas,1,1)==0);
    atlas.heights[1]=std::numeric_limits<float>::quiet_NaN();Require(AtlasHeight(atlas,0,0)==2);
    Reject([&](){AtlasHeight(atlas,0.25,0);});
    Reject([](){AtlasHeight(Atlas{},0,0);});
    auto incomplete=atlas;incomplete.known.pop_back();Reject([&](){AtlasHeight(incomplete,0,0);});
    Reject([&](){AtlasHeight(atlas,std::numeric_limits<double>::quiet_NaN(),0);});
    Reject([&](){AtlasHeight(atlas,0,1000000);});
    const auto view=View();const auto key=WorldTerrainGroundKey::Capture(view,1920,1080,1920,11,12);
    Require(key.Matches(view,1920,1080,1920,11,12));
    auto change=view;++change.mapRandomSeed;Require(!key.Matches(change,1920,1080,1920,11,12));
    change=view;change.plots[0].naturalWonder=true;Require(!key.Matches(change,1920,1080,1920,11,12));
    change=view;++change.plots[0].terrainId;Require(!key.Matches(change,1920,1080,1920,11,12));
}
}
int main(){
    try{CoordinateRoundTrips();PolygonReference();InformationBoundary();HeightsAndCache();
        std::printf("PASS_ORIGINAL_TERRAIN_GEOMETRY checks=%u polygon_samples=%u shared_triangle_tiles=2\n",checks,polygonSamples);return 0;
    }catch(const std::exception& ex){std::fprintf(stderr,"FAIL: %s\n",ex.what());return 1;}
}
