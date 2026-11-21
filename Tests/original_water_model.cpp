#include "OriginalWaterModel.h"
#include "OriginalWaterState.h"
#include "OriginalTerrainModel.h"
#include "original_water_golden.h"
#include <cstdio>
#include <cstring>
#include <limits>
#include <string>

namespace Water=ZeroSisPresentation::OriginalWater;
namespace Terrain=ZeroSisPresentation::OriginalTerrain;
using namespace Water;
namespace {
unsigned checks=0;
const char* section="start";
void Check(bool condition,const char* reason){++checks;if(!condition)throw std::runtime_error(reason);}
void Near(double a,double b,double error=0.000003){
    const bool equal=std::isfinite(a)&&std::isfinite(b)&&std::abs(a-b)<=error;
    if(!equal)std::fprintf(stderr,"section=%s check=%u actual=%.17g expected=%.17g tolerance=%.17g\n",section,checks,a,b,error);
    Check(equal,"Water numeric reference differs");
}
template<class F>void Reject(F fn){bool rejected=false;try{fn();}catch(const std::invalid_argument&){rejected=true;}
    Check(rejected,"Malformed water input was accepted");}
struct GuardBool {bool value=false,forbidden=false;operator bool()const {if(forbidden)throw std::runtime_error("Hidden water boolean was read");return value;}};
struct GuardInt {int value=-1;bool forbidden=false;operator int()const {if(forbidden)throw std::runtime_error("Hidden water integer was read");return value;}};
struct Plot {
    int x=0,y=0;bool revealed=false,visible=false;
    GuardBool water,lake,hills,mountain,riverW,riverNW,riverNE;
    GuardInt terrainId,flowE,flowSE,flowSW;
    double unusedHeight=0;int unusedIndex=0;
};
struct View {int gridWidth=0,gridHeight=0;bool wrapX=false,wrapY=false;std::vector<Plot> plots;
    double camera=0,time=0;int selected=-1,seed=0,units=0;};
View Fixture(int width,int height,bool wrapX,bool wrapY){
    View result;result.gridWidth=width;result.gridHeight=height;result.wrapX=wrapX;result.wrapY=wrapY;
    for(int y=0;y<height;++y)for(int x=0;x<width;++x){
        Plot p;p.x=x;p.y=y;p.revealed=(x+3*y)%7!=0;p.visible=p.revealed&&x%2==0;
        p.water.value=(x+2*y)%3==0;p.hills.value=(x+y)%2!=0;p.mountain.value=(x+2*y)%11==0;p.terrainId.value=(x+y)%5;
        p.riverW.value=(3*x+y)%4!=0;p.riverNW.value=(3*x+y+1)%4!=0;p.riverNE.value=(3*x+y+2)%4!=0;
        p.flowE.value=(x+y)%3==0?-1:(x+y)%3==1?0:3;
        p.flowSE.value=(x+y+1)%3==0?-1:(x+y+1)%3==1?1:4;
        p.flowSW.value=(x+y+2)%3==0?-1:(x+y+2)%3==1?2:5;
        result.plots.push_back(p);
    }
    return result;
}
Grid Plain(int width,int height,bool water,bool wrapped=true){
    Grid result;result.width=width;result.height=height;result.wrapX=wrapped;result.wrapY=wrapped;
    result.cells.resize(static_cast<std::size_t>(width)*height);
    for(auto& cell:result.cells){cell.revealed=true;cell.water=water;cell.terrainId=water?6:0;}
    return result;
}
void Word(std::uint64_t& value,std::uint32_t word){for(unsigned b=0;b<4;++b){value^=(word>>(8*b))&255u;value*=1099511628211ull;}}
std::uint64_t TopologyHash(const Topology& value){
    std::uint64_t hash=14695981039346656037ull;Word(hash,0x77617465);
    for(const auto owner:value.waterCells)Word(hash,owner);
    const auto edges=[&](const std::vector<SharedEdge>& list,std::uint32_t marker){Word(hash,marker);
        for(const auto& edge:list){for(const auto word:{edge.owner,edge.neighbor,static_cast<unsigned>(edge.direction),
            static_cast<unsigned>(edge.flow),static_cast<unsigned>(edge.ownerWater),static_cast<unsigned>(edge.neighborWater),
            static_cast<unsigned>(edge.style)})Word(hash,word);}
    };
    edges(value.coasts,0x636f6173);edges(value.rivers,0x72697672);return hash;
}
void ReferenceTopology(){
    for(const auto& expected:GoldenWaterCases){
        const auto grid=CaptureWaterGrid(Fixture(expected.width,expected.height,expected.wrapX,expected.wrapY));
        const auto topology=BuildTopology(grid);
        Check(topology.waterCells.size()==expected.water&&topology.coasts.size()==expected.coasts&&
            topology.rivers.size()==expected.rivers,"Independent axial topology counts differ");
        Check(TopologyHash(topology)==expected.hash,"Independent axial topology ownership/flow/style differs");
        std::uint64_t neighborHash=14695981039346656037ull;
        for(int y=0;y<grid.height;++y)for(int x=0;x<grid.width;++x)for(unsigned dir=0;dir<6;++dir){
            const auto adjacent=NeighborOf(grid,x,y,static_cast<Direction>(dir));
            Word(neighborHash,static_cast<unsigned>(adjacent.x));Word(neighborHash,static_cast<unsigned>(adjacent.y));Word(neighborHash,adjacent.exists?1u:0u);
        }
        Check(neighborHash==expected.neighbors,"SDK neighbor differs from independent axial reference");
        for(const auto* list:{&topology.coasts,&topology.rivers}){
            std::vector<bool> seen(grid.cells.size()*3,false);
            for(const auto& edge:*list){const auto dir=static_cast<unsigned>(edge.direction);
                Check(dir>=1&&dir<=3,"Noncanonical water edge was emitted");
                const auto key=static_cast<std::size_t>(edge.owner)*3+dir-1;
                Check(!seen[key],"A representative water edge was duplicated");seen[key]=true;
                Check(grid.cells[edge.owner].revealed&&grid.cells[edge.neighbor].revealed,"Unknown neighbor contributed an edge");
                Check(std::isfinite(edge.a.x)&&std::isfinite(edge.a.z)&&std::isfinite(edge.b.x)&&std::isfinite(edge.b.z),"Nonfinite shared edge");
                const auto& owner=grid.cells[edge.owner];const int x=static_cast<int>(edge.owner%grid.width),y=static_cast<int>(edge.owner/grid.width);
                const double centerX=x+(y%2)*0.5,centerZ=-y*RowSpacing;
                const double deltaX=dir==1?1:dir==2?0.5:-0.5,deltaZ=dir==1?0:RowSpacing;
                Near((edge.a.x+edge.b.x)*0.5,centerX+deltaX*0.5,0);
                Near((edge.a.z+edge.b.z)*0.5,centerZ+deltaZ*0.5,1e-14);
                Check(owner.water==edge.ownerWater,"Edge owner water provenance differs");
            }
        }
    }
    for(int width:{1,2,3,8})for(bool wrapX:{false,true})for(bool wrapY:{false,true}){
        const auto grid=Plain(width,4,true);auto query=grid;query.wrapX=wrapX;query.wrapY=wrapY;
        for(int yi=-4;yi<=20;++yi)for(int xi=-4;xi<=40;++xi){
            const double x=xi/4.0,z=-yi/4.0*RowSpacing,row=-z/RowSpacing;
            const auto cube=Terrain::RoundCube({x-row*0.5,row,-x-row*0.5});auto expected=Terrain::CubeToOffset(cube);
            const auto mod=[](int value,int span){const int r=value%span;return r<0?r+span:r;};
            if(wrapX)expected[0]=mod(expected[0],width);if(wrapY)expected[1]=mod(expected[1],4);
            const bool exists=expected[0]>=0&&expected[1]>=0&&expected[0]<width&&expected[1]<4;
            const auto actual=OwnerAt(query,x,z);Check(actual.exists==exists,"Water owner differs from terrain owner");
            if(exists)Check(actual.x==expected[0]&&actual.y==expected[1],"Water owner coordinate differs from terrain owner");
        }
    }
    auto single=Plain(1,2,true);for(auto& cell:single.cells){cell.river={{true,true,true}};cell.flow={{0,1,2}};}
    const auto all=BuildTopology(single);Check(all.rivers.size()==6&&all.coasts.empty(),"Narrow wrap collapsed distinct representative edges");
    for(unsigned slot=0;slot<3;++slot){SharedEdge edge;edge.direction=static_cast<Direction>(slot+1);
        edge.flow=-1;Near(FlowSign(edge),0,0);edge.flow=static_cast<int>(slot);Near(FlowSign(edge),-1,0);
        edge.flow=static_cast<int>(slot+3);Near(FlowSign(edge),1,0);}
}
void SafeCaptureAndKeys(){
    auto view=Fixture(8,6,true,true);const auto before=CaptureWaterGrid(view);auto reverse=view;
    std::reverse(reverse.plots.begin(),reverse.plots.end());Check(SameWaterGrid(before,CaptureWaterGrid(reverse)),"Plot order changed canonical water state");
    for(auto& plot:view.plots){
        if(!plot.revealed){plot.water.forbidden=plot.lake.forbidden=plot.hills.forbidden=plot.mountain.forbidden=true;
            plot.riverW.forbidden=plot.riverNW.forbidden=plot.riverNE.forbidden=true;
            plot.terrainId.forbidden=plot.flowE.forbidden=plot.flowSE.forbidden=plot.flowSW.forbidden=true;}
        if(!plot.riverW.value)plot.flowE.forbidden=true;
        if(!plot.riverNW.value)plot.flowSE.forbidden=true;
        if(!plot.riverNE.value)plot.flowSW.forbidden=true;
    }
    Check(SameWaterGrid(before,CaptureWaterGrid(view)),"Hidden/false-flag fields were read or changed the key");
    for(int iteration=0;iteration<20;++iteration){view.camera=iteration;view.time=iteration*0.1;view.selected=iteration;view.seed=iteration;view.units=iteration;
        for(auto& plot:view.plots){plot.visible=plot.revealed&&(iteration%2==0);plot.unusedHeight=std::numeric_limits<double>::quiet_NaN();plot.unusedIndex=-iteration;}
        Check(SameWaterGrid(before,CaptureWaterGrid(view)),"Visibility/time/camera/selection/seed/units changed topology key");
    }
    auto changed=before;changed.wrapX=!changed.wrapX;Check(!SameWaterGrid(before,changed),"Wrapping omitted from water key");
    changed=before;changed.width=6;changed.height=8;Check(!SameWaterGrid(before,changed),"Dimensions omitted from water key");
    for(std::size_t index=0;index<before.cells.size();++index){
        if(!before.cells[index].revealed)continue;
        changed=before;changed.cells[index].revealed=false;Check(!SameWaterGrid(before,changed),"Exploration omitted from water key");
        changed=before;changed.cells[index].water=!changed.cells[index].water;Check(!SameWaterGrid(before,changed),"Water omitted from key");
        changed=before;changed.cells[index].hills=!changed.cells[index].hills;Check(!SameWaterGrid(before,changed),"Hills omitted from style key");
        changed=before;changed.cells[index].mountain=!changed.cells[index].mountain;Check(!SameWaterGrid(before,changed),"Mountain omitted from style key");
        changed=before;++changed.cells[index].terrainId;Check(!SameWaterGrid(before,changed),"Terrain omitted from style key");
        for(unsigned slot=0;slot<3;++slot){changed=before;changed.cells[index].river[slot]=!changed.cells[index].river[slot];
            if(changed.cells[index].river[slot])changed.cells[index].flow[slot]=-1;
            Check(!SameWaterGrid(before,changed),"A river flag was omitted from key");
            changed=before;if(changed.cells[index].river[slot]){changed.cells[index].flow[slot]=changed.cells[index].flow[slot]==-1?static_cast<int>(slot):-1;
                Check(!SameWaterGrid(before,changed),"An active river flow was omitted from key");}
            else {changed.cells[index].flow[slot]=999;Check(SameWaterGrid(before,changed),"An inactive river flow contaminated key");}
        }
    }
    changed=before;for(auto& cell:changed.cells)if(!cell.revealed){cell.water=cell.lake=cell.hills=cell.mountain=true;
        cell.terrainId=-999;cell.river={{true,true,true}};cell.flow={{999,999,999}};}
    Check(SameWaterGrid(before,changed),"Hidden cell payload contaminated water key");
    Check(TopologyHash(BuildTopology(before))==TopologyHash(BuildTopology(changed)),"Hidden cell payload contaminated topology");
    const auto topo=BuildTopology(before);for(const auto owner:topo.waterCells)Check(before.cells[owner].revealed&&before.cells[owner].water,"Invalid water surface owner");
}
struct HeightCheck {
    const Grid* grid;unsigned* calls;
    double operator()(double x,double z)const {++*calls;const auto owner=OwnerAt(*grid,x,z);
        Check(owner.exists&&grid->cells[static_cast<std::size_t>(owner.y)*grid->width+owner.x].revealed,"Height callback queried unknown/outside owner");return 0.5;}
};
void MeshGeometry(){
    const auto grid=CaptureWaterGrid(Fixture(8,6,true,true));unsigned heights=0,profiles=0;
    const auto profile=[&](LandStyle,unsigned band,double t){++profiles;Check(band==0,"Unexpected coast profile band");return 7+3*t;};
    const auto mesh=BuildMesh(grid,HeightCheck{&grid,&heights},profile);
    Check(!mesh.vertices.empty()&&!mesh.ranges.empty()&&heights>0&&profiles>0,"Known water geometry was not produced");
    Check(mesh.vertices.size()<=MaxVertices&&mesh.fallbackHeightSamples>0,"Geometry budget or unknown height fallback differs");
    unsigned offset=0,previous=0;bool first=true;
    for(const auto& range:mesh.ranges){Check(range.start==offset&&range.count>0&&range.count%3==0,"Water range is not a contiguous triangle list");
        Check(grid.cells[range.ownerCell].revealed&&(first||range.ownerCell>previous),"Water ranges have unknown or duplicate/out-of-order owners");
        offset+=range.count;previous=range.ownerCell;first=false;
    }
    Check(offset==mesh.vertices.size(),"Water ranges do not cover vertex buffer");
    for(const auto& v:mesh.vertices){Check(std::isfinite(v.x)&&std::isfinite(v.y)&&std::isfinite(v.z)&&std::isfinite(v.u)&&std::isfinite(v.v),"Nonfinite water geometry");
        Near(v.y,0.502,1e-6);Check(v.kind==0||v.kind==1||v.kind==2,"Unknown water surface kind");
        Check(v.depth>=0&&v.depth<=1,"Candidate depth left normalized range");
        if(v.kind==2)Check(v.flowSign==-1||v.flowSign==0||v.flowSign==1,"River flow sign invalid");else Near(v.flowSign,0,0);
    }
    const auto zero=BuildMesh(grid,[](double,double){return 0.5;},[](LandStyle,unsigned,double){return 0.0;});
    Check(mesh.vertices.size()==zero.vertices.size(),"Linear profile changed geometry size");
    for(std::size_t i=0;i<mesh.vertices.size();++i){Near(mesh.vertices[i].x,zero.vertices[i].x,0);Near(mesh.vertices[i].z,zero.vertices[i].z,0);}
    const auto curved=BuildMesh(grid,[](double,double){return 0.5;},[](LandStyle,unsigned,double t){return 500*std::sin(t*3.141592653589793);});
    bool shifted=false;
    for(std::size_t i=0;i<curved.vertices.size();++i){const auto& a=curved.vertices[i];const auto& b=zero.vertices[i];
        const double distance=std::hypot(a.x-b.x,a.z-b.z);Check(distance<=0.120001,"Candidate coast meander exceeds clamp");
        if(a.kind==1&&distance>1e-6)shifted=true;if(a.kind!=1)Near(distance,0,0);
    }
    Check(shifted,"Candidate coast profile did not affect coast geometry");
    auto full=Plain(4,4,true);const auto plane=BuildMesh(full,[](double x,double z){return 0.125*x-0.25*z+0.4;},[](LandStyle,unsigned,double){return 0.0;});
    for(const auto& v:plane.vertices)Near(v.y,0.125*v.x-0.25*v.z+0.402,2e-6);
    Grid unknown=Plain(4,4,false);for(auto& cell:unknown.cells){cell.revealed=false;cell.water=true;cell.river={{true,true,true}};cell.flow={{999,999,999}};}
    unsigned forbidden=0;const auto empty=BuildMesh(unknown,[&](double,double){++forbidden;return 0.0;},[&](LandStyle,unsigned,double){++forbidden;return 0.0;});
    Check(empty.vertices.empty()&&empty.ranges.empty()&&forbidden==0,"Unknown map triggered geometry callbacks");
}
void BudgetAndMath(){
    auto grid=Plain(128,128,false);
    for(unsigned y=0;y<128;++y)for(unsigned x=0;x<128;++x){auto& cell=grid.cells[y*128+x];cell.water=(x+y)%2==0;
        cell.river={{true,true,true}};cell.flow={{0,1,2}};}
    const auto large=BuildMesh(grid,[](double,double){return 0.5;},[](LandStyle,unsigned,double){return 0.0;});
    Check(large.vertices.size()<=MaxVertices&&(large.coastSegmentsUsed<8||large.riverSegmentsUsed<4),"2M water budget did not reduce candidate subdivisions");
    Check(large.waterCellCount==8192&&large.riverEdgeCount==49152,"Large bounded topology counts differ");
    for(const auto& range:large.ranges)Check(static_cast<std::size_t>(range.start)+range.count<=large.vertices.size(),"Reduced mesh range escaped vertex buffer");
    auto small=Plain(2,2,true);unsigned invoked=0;MeshPolicy budget;budget.maxVertices=1;
    Reject([&]{BuildMesh(small,[&](double,double){++invoked;return 0.0;},[](LandStyle,unsigned,double){return 0.0;},budget);});
    Check(invoked==0,"Impossible geometry budget called a height sampler before rejection");
    const auto uv=RetailWaterUvs(2,3,{{0.25,0.5,0.75,1}},0.125);
    const double expected[4][2]={{0.625,0.875},{-0.875,1.625},{-1.375,-2.125},{2.125,-2.875}};
    for(unsigned layer=0;layer<4;++layer){Near(uv[layer][0],expected[layer][0],0);Near(uv[layer][1],expected[layer][1],0);}
    for(const auto& item:GoldenDepths)Near(RetailDepthColourU(item.input),item.output,0);
    Near(RetailRiverVertexV(0.75,4),0.75-static_cast<double>(0.05f)*4,0);
    for(unsigned style=0;style<13;++style)Check(std::strcmp(StyleName(static_cast<LandStyle>(style)),GoldenStyleNames[style])==0,"Original coast style name order differs");
}
void Malformed(){
    auto view=Fixture(2,2,false,false);view.gridWidth=0;Reject([&]{CaptureWaterGrid(view);});
    view=Fixture(2,2,false,false);view.gridHeight=-1;Reject([&]{CaptureWaterGrid(view);});
    view=Fixture(2,2,false,false);view.gridWidth=257;Reject([&]{CaptureWaterGrid(view);});
    view=Fixture(2,2,false,false);view.gridHeight=257;Reject([&]{CaptureWaterGrid(view);});
    view=Fixture(2,2,false,false);view.plots.pop_back();Reject([&]{CaptureWaterGrid(view);});
    view=Fixture(2,2,false,false);view.plots[3]=view.plots[1];Reject([&]{CaptureWaterGrid(view);});
    view=Fixture(2,2,false,false);view.plots[0].x=-1;Reject([&]{CaptureWaterGrid(view);});
    view=Fixture(2,2,false,false);view.plots[0].y=2;Reject([&]{CaptureWaterGrid(view);});
    view=Fixture(2,2,false,false);view.plots[0].visible=true;Reject([&]{CaptureWaterGrid(view);});
    view=Fixture(2,3,false,true);Reject([&]{CaptureWaterGrid(view);});
    auto grid=Plain(256,65,false);Reject([&]{BuildTopology(grid);});
    grid=Plain(2,2,false);grid.cells[0].lake=true;Reject([&]{BuildTopology(grid);});
    for(unsigned slot=0;slot<3;++slot)for(int flow=-2;flow<=6;++flow){if(flow==-1||flow==static_cast<int>(slot)||flow==static_cast<int>(slot+3))continue;
        grid=Plain(2,2,false);grid.cells[0].river[slot]=true;grid.cells[0].flow[slot]=flow;Reject([&]{BuildTopology(grid);});}
    grid=Plain(2,2,true);const auto height=[](double,double){return 0.5;};const auto profile=[](LandStyle,unsigned,double){return 0.0;};
    const double nan=std::numeric_limits<double>::quiet_NaN(),inf=std::numeric_limits<double>::infinity();
    for(unsigned issue=0;issue<10;++issue){MeshPolicy policy;
        if(issue==0)policy.coastWidth=0;if(issue==1)policy.riverWidth=-1;if(issue==2)policy.lift=-0.01;
        if(issue==3)policy.uvScale=inf;if(issue==4)policy.profileUnits=0;if(issue==5)policy.maxMeander=nan;
        if(issue==6)policy.coastSegments=0;if(issue==7)policy.riverSegments=65;
        if(issue==8)policy.maxVertices=MaxVertices+1;if(issue==9)policy.waterDepth=2;
        Reject([&]{BuildMesh(grid,height,profile,policy);});
    }
    Reject([&]{BuildMesh(grid,[&](double,double){return nan;},profile);});
    grid.cells[0].water=false;Reject([&]{BuildMesh(grid,height,[&](LandStyle,unsigned,double){return nan;});});
    Reject([&]{OwnerAt(grid,inf,0);});Reject([&]{NeighborOf(grid,-1,0,Direction::E);});
    Reject([&]{NeighborOf(grid,0,0,static_cast<Direction>(6));});Reject([&]{StyleName(static_cast<LandStyle>(13));});
    Reject([&]{StyleForLand(grid.cells[1]);});Reject([&]{RetailDepthColourU(nan);});
    Reject([&]{RetailWaterUvs(nan,1,{{1,1,1,1}},0);});Reject([&]{RetailWaterUvs(1,1,{{1,1,inf,1}},0);});
    Reject([&]{RetailRiverVertexV(0,inf);});Grid malformed;Check(!SameWaterGrid(malformed,malformed),"Invalid grid reused water key");
}
}
int main(){try{
    section="ReferenceTopology";ReferenceTopology();section="SafeCaptureAndKeys";SafeCaptureAndKeys();
    section="MeshGeometry";MeshGeometry();section="BudgetAndMath";BudgetAndMath();section="Malformed";Malformed();
    std::printf("PASS_ORIGINAL_WATER_MODEL checks=%u\n",checks);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"Original water model: %s\n",error.what());return 1;}}
