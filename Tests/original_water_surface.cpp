#include "OriginalWaterSurfaceModel.h"
#include <cstdio>
#include <functional>
#include <set>

namespace Water=ZeroSisPresentation::OriginalWater;
namespace Surface=Water::Surface;
namespace Terrain=ZeroSisPresentation::OriginalTerrain;
namespace {
unsigned checks=0;const char* section="start";
void Check(bool value,const char* reason){++checks;if(!value)throw std::runtime_error(reason);}
void Near(double a,double b,double tolerance=0.000003){const bool same=std::isfinite(a)&&std::isfinite(b)&&std::abs(a-b)<=tolerance;
    if(!same)std::fprintf(stderr,"section=%s check=%u a=%.17g b=%.17g tolerance=%.17g\n",section,checks,a,b,tolerance);
    Check(same,"Surface numeric reference differs");}
template<class F>void Reject(F body){bool rejected=false;try{body();}catch(const std::invalid_argument&){rejected=true;}Check(rejected,"Invalid surface input was accepted");}
Water::Grid Grid(int width,int height,bool allWater,bool wrap){Water::Grid grid;grid.width=width;grid.height=height;grid.wrapX=grid.wrapY=wrap;
    grid.cells.resize(static_cast<std::size_t>(width)*height);for(auto& cell:grid.cells){cell.revealed=true;cell.water=allWater;cell.terrainId=allWater?6:0;}return grid;}
Terrain::Atlas Atlas(const Water::Grid& grid,const std::function<double(double,double)>& raw){Terrain::Atlas atlas;
    atlas.width=static_cast<unsigned>(grid.width)*64;atlas.height=static_cast<unsigned>(grid.height)*64;atlas.wrapX=grid.wrapX;atlas.wrapY=grid.wrapY;
    const auto count=static_cast<std::size_t>(atlas.width)*atlas.height;atlas.known.assign(count,1);atlas.ids.assign(count,3);atlas.heights.resize(count);
    for(unsigned y=0;y<atlas.height;++y)for(unsigned x=0;x<atlas.width;++x)atlas.heights[static_cast<std::size_t>(y)*atlas.width+x]=static_cast<float>(raw(x/64.0,y/64.0));return atlas;}
Surface::Plane Plane(){Surface::Plane plane;plane.rawLevel=0.5;plane.heightOffset=0;plane.worldScale=2;return plane;}
double Area(const Surface::SurfaceMesh& mesh){double area=0;
    for(const auto& range:mesh.ranges)if(range.kind==Water::SurfaceKind::Water)for(unsigned at=range.start;at<range.start+range.count;at+=3){
        const auto& a=mesh.vertices[at];const auto& b=mesh.vertices[at+1];const auto& c=mesh.vertices[at+2];
        area+=std::abs((static_cast<double>(b.x)-a.x)*(c.z-a.z)-(static_cast<double>(c.x)-a.x)*(b.z-a.z))*0.5;}
    return area;
}
void ValidMesh(const Water::Grid& grid,const Surface::SurfaceMesh& mesh){unsigned end=0;bool shoreSeen=false;
    Check(mesh.vertices.size()<=Water::MaxVertices&&mesh.contours.size()<=Surface::MaxContours,"Surface output exceeded bounded storage");
    for(const auto& range:mesh.ranges){Check(range.ownerCell<grid.cells.size()&&range.start==end&&range.count&&range.count%3==0,"Invalid surface draw range");
        end+=range.count;if(range.kind==Water::SurfaceKind::Coast)shoreSeen=true;else Check(!shoreSeen,"Water surface emitted after shoreline colour ranges");
        for(unsigned at=range.start;at<end;++at){const auto& v=mesh.vertices[at];
            Check(std::isfinite(v.x)&&std::isfinite(v.y)&&std::isfinite(v.z)&&std::isfinite(v.depth)&&std::isfinite(v.u)&&std::isfinite(v.v),"Nonfinite surface vertex");
            Near(v.y,mesh.planeY,1e-7);Near(v.kind,static_cast<unsigned>(range.kind),0);Near(v.flowSign,0,0);
            if(range.kind==Water::SurfaceKind::Water)Check(v.depth<=0.500001f,"Seabed height above clipped water level");}
        if(range.kind==Water::SurfaceKind::Water)for(unsigned at=range.start;at<end;at+=3){
            const auto& a=mesh.vertices[at];const auto& b=mesh.vertices[at+1];const auto& c=mesh.vertices[at+2];
            const double cross=(static_cast<double>(b.x)-a.x)*(c.z-a.z)-(static_cast<double>(c.x)-a.x)*(b.z-a.z);
            Check(cross<=1e-10,"Surface winding inverted");if(std::abs(cross)<1e-12)continue;
            const auto owner=Water::OwnerAt(grid,(static_cast<double>(a.x)+b.x+c.x)/3,(static_cast<double>(a.z)+b.z+c.z)/3);
            Check(owner.exists&&grid.cells[static_cast<std::size_t>(owner.y)*grid.width+owner.x].revealed&&
                grid.cells[static_cast<std::size_t>(owner.y)*grid.width+owner.x].water,"Surface triangle escaped explored SDK water hex");}
    }
    Check(end==mesh.vertices.size(),"Surface ranges do not cover all vertices");
    for(const auto& contour:mesh.contours){Check(contour.waterCell<grid.cells.size()&&contour.landCell<grid.cells.size(),"Contour owner out of range");
        Check(grid.cells[contour.waterCell].revealed&&grid.cells[contour.waterCell].water&&grid.cells[contour.landCell].revealed&&!grid.cells[contour.landCell].water,
            "Shoreline inferred an unknown/nonshared land-water pair");
        bool adjacent=false;for(unsigned dir=0;dir<6;++dir){const auto neighbor=Water::NeighborOf(grid,static_cast<int>(contour.waterCell%grid.width),
            static_cast<int>(contour.waterCell/grid.width),static_cast<Water::Direction>(dir));
            if(neighbor.exists&&static_cast<unsigned>(neighbor.y*grid.width+neighbor.x)==contour.landCell)adjacent=true;}
        Check(adjacent,"Shoreline land is not a real shared SDK neighbor");
        Check(std::hypot(contour.b.x-contour.a.x,contour.b.z-contour.a.z)>0,"Degenerate contour emitted");
    }
}
void SameMesh(const Surface::SurfaceMesh& a,const Surface::SurfaceMesh& b){
    Check(a.vertices.size()==b.vertices.size()&&a.ranges.size()==b.ranges.size()&&a.contours.size()==b.contours.size()&&a.usedStep==b.usedStep,"Hidden payload changed surface shape");
    for(std::size_t i=0;i<a.vertices.size();++i){const auto& x=a.vertices[i];const auto& y=b.vertices[i];
        Check(x.x==y.x&&x.y==y.y&&x.z==y.z&&x.u==y.u&&x.v==y.v&&x.kind==y.kind&&x.depth==y.depth&&x.flowSign==y.flowSign,"Hidden payload changed vertex bytes");}
    for(std::size_t i=0;i<a.ranges.size();++i){const auto& x=a.ranges[i];const auto& y=b.ranges[i];
        Check(x.ownerCell==y.ownerCell&&x.start==y.start&&x.count==y.count&&x.kind==y.kind,"Hidden payload changed range");}
    for(std::size_t i=0;i<a.contours.size();++i){const auto& x=a.contours[i];const auto& y=b.contours[i];
        Check(x.ownerCell==y.ownerCell&&x.waterCell==y.waterCell&&x.landCell==y.landCell&&x.a.x==y.a.x&&x.a.z==y.a.z&&x.b.x==y.b.x&&x.b.z==y.b.z,
            "Hidden payload changed contour crossings");}
}
using NodeKey=std::pair<std::int64_t,std::int64_t>;
NodeKey Node(const Water::Grid& grid,Water::Point2 p){auto x=std::llround(p.x*64*Surface::CoordinateUnits),y=std::llround(-p.z/Water::RowSpacing*64*Surface::CoordinateUnits);
    const auto wrap=[](std::int64_t v,std::int64_t size){const auto r=v%size;return r<0?r+size:r;};
    if(grid.wrapX)x=wrap(x,static_cast<std::int64_t>(grid.width)*64*Surface::CoordinateUnits);
    if(grid.wrapY)y=wrap(y,static_cast<std::int64_t>(grid.height)*64*Surface::CoordinateUnits);return {x,y};}
void ClosedGraph(const Water::Grid& grid,const Surface::SurfaceMesh& mesh){std::map<NodeKey,unsigned> degree;
    std::set<std::pair<NodeKey,NodeKey>> edges;
    for(const auto& contour:mesh.contours){auto a=Node(grid,contour.a),b=Node(grid,contour.b);++degree[a];++degree[b];if(b<a)std::swap(a,b);
        Check(edges.emplace(a,b).second,"Duplicate canonical contour segment");}
    Check(!degree.empty(),"Expected closed contour graph is empty");for(const auto& node:degree)Check(node.second==2,"Shared contour crossing is not bit-identical or has a seam gap");
}
void PlanesAndAnalyticArea(){const auto plane=Plane();
    auto all=Grid(2,2,true,true);const auto wet=Atlas(all,[](double,double){return 0.25;});
    for(unsigned step:{1u,4u,16u,64u}){Surface::Policy policy;policy.initialStep=step;const auto mesh=Surface::BuildSurface(all,wet,plane,policy);
        ValidMesh(all,mesh);Near(Area(mesh),4*Water::RowSpacing,2e-6);Check(mesh.contours.empty(),"Flat fully wet map invented a coast");
        for(const auto& vertex:mesh.vertices)Near(vertex.depth,0.25,0);}
    const auto above=Atlas(all,[](double,double){return 0.75;});const auto dry=Surface::BuildSurface(all,above,plane);
    Check(dry.vertices.empty()&&dry.ranges.empty()&&dry.contours.empty(),"Dry map produced water or contour");
    const auto equal=Atlas(all,[](double,double){return 0.5;});const auto flat=Surface::BuildSurface(all,equal,plane);
    Near(Area(flat),4*Water::RowSpacing,2e-6);Check(flat.contours.empty(),"Coplanar triangles invented duplicate contours");
    auto one=Grid(3,4,false,false);one.cells[4].water=true;one.cells[4].terrainId=6;
    const auto slope=Atlas(one,[](double x,double){return 0.5+(x-1.5)*0.125;});
    for(unsigned step:{1u,4u,16u,64u}){Surface::Policy policy;policy.initialStep=step;const auto mesh=Surface::BuildSurface(one,slope,plane,policy);
        ValidMesh(one,mesh);Near(Area(mesh),Water::RowSpacing*0.5,2e-6);double length=0;
        for(const auto& contour:mesh.contours){Near(contour.a.x,1.5,0);Near(contour.b.x,1.5,0);length+=std::hypot(contour.b.x-contour.a.x,contour.b.z-contour.a.z);}
        Near(length,Water::RowSpacing*4/3,2e-8);Check(mesh.stats.shoreVertices>0,"True height-contour shoreline did not get a colour ribbon");}
}
void SharedCrossingsAndSeams(){const auto plane=Plane();auto grid=Grid(3,4,false,false);grid.cells[4].water=true;grid.cells[4].terrainId=6;
    const auto bowl=Atlas(grid,[](double x,double y){const double dx=x-1.5,dy=(y-1)*Water::RowSpacing;return 0.5+dx*dx+dy*dy-0.0625;});
    double lastError=1;
    for(unsigned step:{16u,8u,4u,1u}){Surface::Policy policy;policy.initialStep=step;const auto mesh=Surface::BuildSurface(grid,bowl,plane,policy);
        ValidMesh(grid,mesh);ClosedGraph(grid,mesh);const double error=std::abs(Area(mesh)-3.141592653589793*0.0625);
        Check(error<=lastError+1e-6,"Explicit LOD did not converge on independent circle area");lastError=error;}
    Check(lastError<0.001,"Dense linear triangle approximation differs too far from analytic circle area");
    auto seam=Grid(1,2,false,true);seam.cells[0].water=true;seam.cells[0].terrainId=6;
    const auto periodic=Atlas(seam,[](double x,double y){const double dx=(std::min)(x,1-x),dy=(std::min)(y,2-y)*Water::RowSpacing;
        return 0.5+dx*dx+dy*dy-0.04;});
    const auto mesh=Surface::BuildSurface(seam,periodic,plane);ValidMesh(seam,mesh);ClosedGraph(seam,mesh);
    Surface::Policy policy;const Surface::Detail::Context context{seam,periodic,plane,policy};
    const Surface::Detail::Node a{0,16},b{64,16},translatedA{64,16},translatedB{128,16};
    const auto first=Surface::Detail::SegmentKey(context,a,b),reverse=Surface::Detail::SegmentKey(context,b,a),translated=Surface::Detail::SegmentKey(context,translatedA,translatedB);
    Check(!(first<reverse)&&!(reverse<first)&&!(first<translated)&&!(translated<first)&&first.dx!=0,"Periodic full-loop contour collapsed or changed under orientation/translation");
}
void PrivacyAndBudgets(){const auto plane=Plane();auto grid=Grid(3,4,false,false);grid.cells[4].water=true;grid.cells[4].terrainId=6;
    grid.cells[5].revealed=false;auto source=Atlas(grid,[](double x,double){return 0.5+(x-1.5)*0.125;});
    source.known[67*source.width+99]=0;const auto baseline=Surface::BuildSurface(grid,source,plane);auto poisoned=source;
    for(unsigned y=0;y<source.height;++y)for(unsigned x=0;x<source.width;++x){const auto owner=Water::OwnerAt(grid,x/64.0,-static_cast<double>(y)/64*Water::RowSpacing);
        if(!owner.exists||!grid.cells[static_cast<std::size_t>(owner.y)*grid.width+owner.x].revealed||!source.known[static_cast<std::size_t>(y)*source.width+x])
            poisoned.heights[static_cast<std::size_t>(y)*source.width+x]=(x+y)%2?std::numeric_limits<float>::quiet_NaN():std::numeric_limits<float>::infinity();}
    std::fill(poisoned.ids.begin(),poisoned.ids.end(),static_cast<std::uint8_t>(255));SameMesh(baseline,Surface::BuildSurface(grid,poisoned,plane));
    auto unknown=Grid(2,2,true,true);for(auto& cell:unknown.cells){cell.revealed=false;cell.water=cell.lake=cell.hills=true;cell.terrainId=-999;cell.flow={{999,999,999}};}
    auto none=Atlas(unknown,[](double,double){return std::numeric_limits<double>::quiet_NaN();});
    const auto empty=Surface::BuildSurface(unknown,none,plane);Check(empty.vertices.empty()&&empty.contours.empty()&&empty.stats.validatedKnownHeights==0,"Hidden atlas was read or inferred");
    auto full=Grid(12,12,true,true);const auto atlas=Atlas(full,[](double,double){return 0.25;});Surface::Policy policy;policy.initialStep=1;
    const auto large=Surface::BuildSurface(full,atlas,plane,policy);
    Check(large.usedStep>1&&large.stats.lodAttempts>1&&large.vertices.size()<=Water::MaxVertices,"Actual 2M budget did not adapt the atlas step");
    Near(Area(large),144*Water::RowSpacing,0.0002);
    auto interior=Grid(3,4,false,false);interior.cells[4].water=true;auto holes=Atlas(interior,[](double,double){return 0.25;});
    holes.known[67*holes.width+99]=0;holes.heights[67*holes.width+99]=std::numeric_limits<float>::quiet_NaN();policy.initialStep=8;
    const auto noBridge=Surface::BuildSurface(interior,holes,plane,policy);Check(noBridge.stats.unknownQuads>0,"Interior unknown texel did not suppress its LOD quad");
    const double hx=99/64.0,hz=-67/64.0*Water::RowSpacing;
    for(const auto& range:noBridge.ranges)if(range.kind==Water::SurfaceKind::Water)for(unsigned i=range.start;i<range.start+range.count;i+=3){
        const auto& a=noBridge.vertices[i];const auto& b=noBridge.vertices[i+1];const auto& c=noBridge.vertices[i+2];
        const auto side=[&](const Water::Vertex& u,const Water::Vertex& v){return (v.x-u.x)*(hz-u.z)-(v.z-u.z)*(hx-u.x);};
        const double sa=side(a,b),sb=side(b,c),sc=side(c,a);
        Check(!((sa>1e-9&&sb>1e-9&&sc>1e-9)||(sa< -1e-9&&sb< -1e-9&&sc< -1e-9)),"LOD bridged a hidden interior texel");}
}
void Malformed(){const auto plane=Plane();const auto grid=Grid(2,2,true,true);const auto atlas=Atlas(grid,[](double,double){return 0.25;});
    auto bad=atlas;bad.heights[5]=std::numeric_limits<float>::quiet_NaN();Reject([&]{Surface::BuildSurface(grid,bad,plane);});
    bad=atlas;bad.originX=0;Reject([&]{Surface::BuildSurface(grid,bad,plane);});bad=atlas;bad.wrapX=false;Reject([&]{Surface::BuildSurface(grid,bad,plane);});
    bad=atlas;bad.known.pop_back();Reject([&]{Surface::BuildSurface(grid,bad,plane);});auto invalid=grid;invalid.height=3;Reject([&]{Surface::BuildSurface(invalid,atlas,plane);});
    for(unsigned issue=0;issue<10;++issue){auto p=plane;Surface::Policy policy;
        if(issue==0)p.rawLevel=std::numeric_limits<double>::quiet_NaN();if(issue==1)p.worldScale=0;if(issue==2)p.heightOffset=2;
        if(issue==3)policy.initialStep=3;if(issue==4)policy.initialStep=128;if(issue==5)policy.maxVertices=Water::MaxVertices+1;
        if(issue==6)policy.maxContours=Surface::MaxContours+1;if(issue==7)policy.shoreWidth=0;if(issue==8)policy.uvScale=std::numeric_limits<double>::infinity();
        if(issue==9){policy.maxVertices=1;policy.adaptive=false;}Reject([&]{Surface::BuildSurface(grid,atlas,p,policy);});}
    auto coast=Grid(3,4,false,false);coast.cells[4].water=true;const auto slope=Atlas(coast,[](double x,double){return 0.5+(x-1.5)*0.125;});
    Surface::Policy policy;policy.maxContours=1;policy.adaptive=false;Reject([&]{Surface::BuildSurface(coast,slope,plane,policy);});
}
}
int main(){try{section="PlanesAndAnalyticArea";PlanesAndAnalyticArea();section="SharedCrossingsAndSeams";SharedCrossingsAndSeams();
    section="PrivacyAndBudgets";PrivacyAndBudgets();section="Malformed";Malformed();std::printf("PASS_ORIGINAL_WATER_SURFACE checks=%u\n",checks);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"Original water surface: %s\n",error.what());return 1;}}
