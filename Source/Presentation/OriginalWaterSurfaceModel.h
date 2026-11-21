#pragma once
#include "OriginalWaterModel.h"
#include "OriginalTerrainModel.h"
#include "OriginalTerrainBinding.h"
#include <limits>
#include <map>
#include <tuple>

namespace ZeroSisPresentation { namespace OriginalWater { namespace Surface {
namespace Terrain=::ZeroSisPresentation::OriginalTerrain;
using Vertex=::ZeroSisPresentation::OriginalWater::Vertex;
constexpr std::int64_t CoordinateUnits=16777216; // Candidate 2^-24 source-texel snapping.
constexpr std::size_t MaxContours=131072;
struct Plane {
    double rawLevel=0.19836;
    double heightOffset=static_cast<double>(Terrain::HeightOffsetCandidate);
    double worldScale=static_cast<double>(Terrain::HeightWorldScaleCandidate);
};
struct Policy {
    unsigned initialStep=4;bool adaptive=true;
    double shoreWidth=0.08,uvScale=1;
    std::size_t maxVertices=OriginalWater::MaxVertices,maxContours=MaxContours;
};
struct Range {unsigned ownerCell=0,start=0,count=0;SurfaceKind kind=SurfaceKind::Water;};
struct Contour {
    unsigned ownerCell=0,waterCell=0,landCell=0;LandStyle style=LandStyle::Default;
    Point2 a,b;
    int waterImageX=0,waterImageY=0,landImageX=0,landImageY=0;
};
struct Stats {
    std::uint64_t validatedKnownHeights=0,visitedQuads=0,unknownQuads=0,acceptedQuads=0;
    std::size_t waterVertices=0,shoreVertices=0;unsigned lodAttempts=0;
};
struct SurfaceMesh {
    std::vector<Vertex> vertices;std::vector<Range> ranges;std::vector<Contour> contours;
    unsigned usedStep=0;double planeY=0;Stats stats;
};
namespace Detail {
inline void Require(bool value,const char* reason){if(!value)throw std::invalid_argument(reason);}
inline double Snap(double value){return static_cast<double>(std::llround(value*CoordinateUnits))/CoordinateUnits;}
struct Node {double x=0,y=0,h=0,u=0,v=0;}; // Atlas coordinates, source texels.
struct Polygon {std::array<Node,16> points{};unsigned count=0;};
inline bool SamePoint(const Node& a,const Node& b){return a.x==b.x&&a.y==b.y;}
inline void Push(Polygon& p,const Node& point){
    if(p.count&&SamePoint(p.points[p.count-1],point))return;
    Require(p.count<p.points.size(),"Surface polygon exceeded its convex bound");p.points[p.count++]=point;
}
inline Node Mix(const Node& a,const Node& b,double t){
    t=(std::max)(0.0,(std::min)(1.0,t));
    return {Snap(a.x+(b.x-a.x)*t),Snap(a.y+(b.y-a.y)*t),a.h+(b.h-a.h)*t,a.u+(b.u-a.u)*t,a.v+(b.v-a.v)*t};
}
inline void Clean(Polygon& p){if(p.count>1&&SamePoint(p.points[0],p.points[p.count-1]))--p.count;}
inline double Area(const Polygon& p){double value=0;for(unsigned i=0;i<p.count;++i){const auto& a=p.points[i];const auto& b=p.points[(i+1)%p.count];value+=a.x*b.y-b.x*a.y;}return value*0.5;}
inline bool HasArea(Polygon& p){Clean(p);return p.count>=3&&std::abs(Area(p))>1e-12;}
inline Node HeightCross(Node a,Node b,double level){
    // Orient a shared source edge before interpolation, so reversed triangles
    // produce identical crossings before the explicit quantization policy.
    if(std::tie(b.x,b.y)<std::tie(a.x,a.y))std::swap(a,b);
    Require(a.h!=b.h,"Degenerate surface height intersection");
    auto point=Mix(a,b,(level-a.h)/(b.h-a.h));point.h=level;return point;
}
inline Polygon ClipHeight(const std::array<Node,3>& triangle,double level){
    Polygon result;
    for(unsigned i=0;i<3;++i){const auto& a=triangle[i];const auto& b=triangle[(i+1)%3];const bool inA=a.h<=level,inB=b.h<=level;
        if(inA)Push(result,a);if(inA!=inB)Push(result,HeightCross(a,b,level));}
    Clean(result);return result;
}
struct Hex {int x=0,y=0;unsigned owner=0;std::array<Node,6> corners{};};
inline int Parity(int y){const int half=y/2-((y<0&&y%2)?1:0);return y-half*2;}
inline Hex MakeHex(int x,int y,unsigned owner){
    const double cx=(x+Parity(y)*0.5)*64,cy=y*64.0;
    Hex result;result.x=x;result.y=y;result.owner=owner;
    result.corners={{{cx,cy+128.0/3},{cx+32,cy+64.0/3},{cx+32,cy-64.0/3},
        {cx,cy-128.0/3},{cx-32,cy-64.0/3},{cx-32,cy+64.0/3}}};return result;
}
inline double Side(const Node& a,const Node& b,const Node& p){return (b.x-a.x)*(p.y-a.y)-(b.y-a.y)*(p.x-a.x);}
inline Polygon ClipHex(Polygon p,const Hex& hex){
    for(unsigned edge=0;edge<6&&p.count;++edge){Polygon next;const auto& a=hex.corners[edge];const auto& b=hex.corners[(edge+1)%6];
        for(unsigned i=0;i<p.count;++i){const auto& u=p.points[i];const auto& v=p.points[(i+1)%p.count];const double su=Side(a,b,u),sv=Side(a,b,v);
            const bool inU=su<=0,inV=sv<=0;if(inU)Push(next,u);if(inU!=inV)Push(next,Mix(u,v,su/(su-sv)));}
        Clean(next);p=next;
    }
    return p;
}
inline bool ClipLine(Node& a,Node& b,const Hex& hex){
    double begin=0,end=1;
    for(unsigned edge=0;edge<6;++edge){const auto& u=hex.corners[edge];const auto& v=hex.corners[(edge+1)%6];
        const double sa=Side(u,v,a),sb=Side(u,v,b);if(sa>0&&sb>0)return false;
        if((sa>0)!=(sb>0)){const double t=sa/(sa-sb);if(sa>0)begin=(std::max)(begin,t);else end=(std::min)(end,t);}}
    if(begin>end)return false;const auto originalA=a,originalB=b;a=Mix(originalA,originalB,begin);b=Mix(originalA,originalB,end);
    return !SamePoint(a,b);
}
struct Context {
    const Grid& grid;const Terrain::Atlas& atlas;const Plane& plane;const Policy& policy;
    bool Known(int x,int y)const{
        const auto owner=OriginalWater::OwnerAt(grid,x/64.0,-y/64.0*OriginalWater::RowSpacing);
        if(!owner.exists||!grid.cells[static_cast<std::size_t>(owner.y)*grid.width+owner.x].revealed)return false;
        if(x<0||y<0||x>static_cast<int>(atlas.width)||y>static_cast<int>(atlas.height))return false;
        return atlas.known[Index(x,y)]!=0;
    }
    std::size_t Index(int x,int y)const{
        if(x==static_cast<int>(atlas.width))x=atlas.wrapX?0:x-1;
        if(y==static_cast<int>(atlas.height))y=atlas.wrapY?0:y-1;
        return static_cast<std::size_t>(y)*atlas.width+static_cast<unsigned>(x);
    }
    Node Sample(int x,int y)const{
        const double h=static_cast<double>(atlas.heights[Index(x,y)])+plane.heightOffset;
        return {static_cast<double>(x),static_cast<double>(y),h,x/64.0*policy.uvScale,-y/64.0*OriginalWater::RowSpacing*policy.uvScale};
    }
    bool QuadKnown(int x,int y,unsigned step)const{
        for(unsigned dy=0;dy<=step;++dy)for(unsigned dx=0;dx<=step;++dx)if(!Known(x+static_cast<int>(dx),y+static_cast<int>(dy)))return false;
        return true;
    }
};
inline std::vector<Hex> WaterHexes(const Context& context,int column,int row){
    std::vector<Hex> result;
    for(int y=row-1;y<=row+2;++y)for(int x=column-1;x<=column+2;++x){int nx=x,ny=y;
        if(context.grid.wrapX)nx=OriginalWater::Detail::Wrap(nx,context.grid.width);
        if(context.grid.wrapY)ny=OriginalWater::Detail::Wrap(ny,context.grid.height);
        if(nx<0||ny<0||nx>=context.grid.width||ny>=context.grid.height)continue;
        const unsigned owner=static_cast<unsigned>(ny*context.grid.width+nx);const auto& cell=context.grid.cells[owner];
        if(cell.revealed&&cell.water)result.push_back(MakeHex(x,y,owner));
    }
    return result;
}
inline bool LandNeighbor(const Context& context,const Hex& water,const Node& midpoint,Contour& result){
    const int ownerX=static_cast<int>(water.owner%context.grid.width),ownerY=static_cast<int>(water.owner/context.grid.width);
    double best=std::numeric_limits<double>::infinity();bool found=false;
    const int parity=Parity(water.y);
    const int dx[6]={parity,1,parity,parity-1,-1,parity-1},dy[6]={1,0,-1,-1,0,1};
    for(unsigned dir=0;dir<6;++dir){const auto neighbor=OriginalWater::NeighborOf(context.grid,ownerX,ownerY,static_cast<Direction>(dir));
        if(!neighbor.exists)continue;const unsigned land=static_cast<unsigned>(neighbor.y*context.grid.width+neighbor.x);const auto& cell=context.grid.cells[land];
        if(!cell.revealed||cell.water)continue;
        const int lx=water.x+dx[dir],ly=water.y+dy[dir];const double wx=(water.x+Parity(water.y)*0.5)*64,wy=water.y*64.0,
            ex=((lx+Parity(ly)*0.5)*64+wx)*0.5,ey=(ly*64.0+wy)*0.5;
        const double distance=(midpoint.x-ex)*(midpoint.x-ex)+(midpoint.y-ey)*(midpoint.y-ey)*OriginalWater::RowSpacing*OriginalWater::RowSpacing;
        if(!found||distance<best||(distance==best&&land<result.landCell)){found=true;best=distance;
            result.landCell=land;result.landImageX=lx;result.landImageY=ly;result.style=OriginalWater::StyleForLand(cell);}
    }
    return found;
}
struct Key {
    std::int64_t x=0,y=0,dx=0,dy=0;
    bool operator<(const Key& other)const{return std::tie(x,y,dx,dy)<std::tie(other.x,other.y,other.dx,other.dy);}
};
inline std::int64_t Quantized(double value){return std::llround(value*CoordinateUnits);}
inline std::int64_t Periodic(std::int64_t value,std::int64_t span,bool wrap){if(!wrap)return value;const auto r=value%span;return r<0?r+span:r;}
inline Key SegmentKey(const Context& context,const Node& a,const Node& b){
    const auto ax=Quantized(a.x),ay=Quantized(a.y),bx=Quantized(b.x),by=Quantized(b.y);
    const auto make=[&](std::int64_t x,std::int64_t y,std::int64_t dx,std::int64_t dy){return Key{
        Periodic(x,static_cast<std::int64_t>(context.atlas.width)*CoordinateUnits,context.grid.wrapX),
        Periodic(y,static_cast<std::int64_t>(context.atlas.height)*CoordinateUnits,context.grid.wrapY),dx,dy};};
    const auto forward=make(ax,ay,bx-ax,by-ay),reverse=make(bx,by,ax-bx,ay-by);return reverse<forward?reverse:forward;
}
struct Pending {Contour contour;unsigned sides=0;};
using PendingMap=std::map<Key,Pending>;
inline bool HeightLine(const std::array<Node,3>& triangle,double level,Node& a,Node& b,unsigned& sides){
    unsigned wet=0,dry=0,zeros=0;Polygon points;
    for(unsigned i=0;i<3;++i){const auto& p=triangle[i];const auto& q=triangle[(i+1)%3];
        if(p.h<level)++wet;else if(p.h>level)++dry;else{++zeros;Push(points,p);}
        if((p.h<level&&q.h>level)||(p.h>level&&q.h<level))Push(points,HeightCross(p,q,level));}
    Clean(points);if(points.count!=2||SamePoint(points.points[0],points.points[1]))return false;
    if(wet&&dry)sides=3;else if(zeros==2&&(wet||dry))sides=wet?1u:2u;else return false;
    a=points.points[0];b=points.points[1];a.h=b.h=level;return true;
}
template<class OnPolygon>bool PlanePass(const Context& context,unsigned step,OnPolygon onPolygon,PendingMap* pending,Stats& stats){
    for(int row=0;row<context.grid.height;++row)for(int col=0;col<context.grid.width;++col){
        const unsigned owner=static_cast<unsigned>(row*context.grid.width+col);const auto hexes=WaterHexes(context,col,row);
        if(hexes.empty())continue;
        for(unsigned y=0;y<64;y+=step)for(unsigned x=0;x<64;x+=step){++stats.visitedQuads;
            const int px=col*64+static_cast<int>(x),py=row*64+static_cast<int>(y);
            if(!context.QuadKnown(px,py,step)){++stats.unknownQuads;continue;}++stats.acceptedQuads;
            const int extent=static_cast<int>(step);const Node a=context.Sample(px,py),b=context.Sample(px+extent,py),
                c=context.Sample(px,py+extent),d=context.Sample(px+extent,py+extent);
            const std::array<Node,3> triangles[2]={{{a,b,c}},{{b,d,c}}};
            for(const auto& triangle:triangles){const auto clipped=ClipHeight(triangle,context.plane.rawLevel);
                Node lineA,lineB;unsigned sides=0;const bool hasLine=pending&&HeightLine(triangle,context.plane.rawLevel,lineA,lineB,sides);
                for(const auto& hex:hexes){
                    auto poly=ClipHex(clipped,hex);if(HasArea(poly)&&!onPolygon(poly,owner,SurfaceKind::Water))return false;
                    if(!hasLine)continue;auto ca=lineA,cb=lineB;if(!ClipLine(ca,cb,hex))continue;
                    Contour contour;contour.ownerCell=owner;contour.waterCell=hex.owner;contour.waterImageX=hex.x;contour.waterImageY=hex.y;
                    if(!LandNeighbor(context,hex,Mix(ca,cb,0.5),contour))continue;
                    contour.a={ca.x/64,-ca.y/64*OriginalWater::RowSpacing};contour.b={cb.x/64,-cb.y/64*OriginalWater::RowSpacing};
                    const auto key=SegmentKey(context,ca,cb);auto inserted=pending->emplace(key,Pending{contour,sides});
                    if(!inserted.second)inserted.first->second.sides|=sides;
                    if(pending->size()>context.policy.maxContours*2)return false;
                }
            }
        }
    }
    return true;
}
inline Polygon ShoreQuad(const Context& context,const Contour& contour){
    const double dx=contour.b.x-contour.a.x,dz=contour.b.z-contour.a.z,length=std::hypot(dx,dz);
    Require(std::isfinite(length)&&length>0,"Degenerate water contour");const double nx=dz/length,nz=-dx/length;
    Polygon result;
    for(unsigned i=0;i<4;++i){const bool end=i>=2;const double across=(i==0||i==3)?0.0:1.0,side=(across-0.5)*context.policy.shoreWidth;
        const auto& endpoint=end?contour.b:contour.a;
        Push(result,{Snap((endpoint.x+nx*side)*64),Snap(-(endpoint.z+nz*side)/OriginalWater::RowSpacing*64),context.plane.rawLevel,
            end?length*context.policy.uvScale:0,across});}
    if(Area(result)<0)std::reverse(result.points.begin(),result.points.begin()+result.count);return result;
}
template<class OnPolygon>bool ShorePass(const Context& context,const std::vector<Contour>& contours,OnPolygon onPolygon){
    for(const auto& contour:contours){const auto quad=ShoreQuad(context,contour);
        const Hex hexes[2]={MakeHex(contour.waterImageX,contour.waterImageY,contour.waterCell),MakeHex(contour.landImageX,contour.landImageY,contour.landCell)};
        for(const auto& hex:hexes){auto clipped=ClipHex(quad,hex);if(HasArea(clipped)&&!onPolygon(clipped,contour.ownerCell,SurfaceKind::Coast))return false;}}
    return true;
}
inline void Validate(const Grid& grid,const Terrain::Atlas& atlas,const Plane& plane,const Policy& policy){
    OriginalWater::Detail::Validate(grid);Terrain::Detail::AtlasShape(atlas);
    Require(atlas.width==static_cast<unsigned>(grid.width)*64&&atlas.height==static_cast<unsigned>(grid.height)*64&&
        atlas.originX==-32&&atlas.originY==0&&atlas.wrapX==grid.wrapX&&atlas.wrapY==grid.wrapY,"Water surface atlas/grid alignment differs");
    Require(std::isfinite(plane.rawLevel)&&plane.rawLevel>=0&&plane.rawLevel<=1&&std::isfinite(plane.heightOffset)&&
        plane.heightOffset>=0&&plane.heightOffset<=1&&std::isfinite(plane.worldScale)&&plane.worldScale>0&&plane.worldScale<=1024,
        "Invalid water surface plane calibration");
    Require(policy.initialStep>=1&&policy.initialStep<=64&&(policy.initialStep&(policy.initialStep-1))==0&&
        policy.maxVertices>0&&policy.maxVertices<=OriginalWater::MaxVertices&&policy.maxContours>0&&policy.maxContours<=MaxContours&&
        std::isfinite(policy.shoreWidth)&&policy.shoreWidth>0&&policy.shoreWidth<=0.5&&
        std::isfinite(policy.uvScale)&&policy.uvScale>0&&policy.uvScale<=4096,"Invalid water surface bounded policy");
}
}
inline double PlaneHeight(const Plane& plane){
    Detail::Require(std::isfinite(plane.rawLevel)&&std::isfinite(plane.heightOffset)&&std::isfinite(plane.worldScale),"Nonfinite water plane");
    return (plane.rawLevel-plane.heightOffset)*plane.worldScale;
}
inline SurfaceMesh BuildSurface(const Grid& grid,const Terrain::Atlas& atlas,const Plane& plane=Plane{},const Policy& policy=Policy{}){
    Detail::Validate(grid,atlas,plane,policy);const Detail::Context context{grid,atlas,plane,policy};SurfaceMesh result;
    result.planeY=PlaneHeight(plane);std::uint64_t known=0;
    for(unsigned y=0;y<atlas.height;++y)for(unsigned x=0;x<atlas.width;++x)if(context.Known(static_cast<int>(x),static_cast<int>(y))){
        Detail::Require(std::isfinite(atlas.heights[static_cast<std::size_t>(y)*atlas.width+x]),"Nonfinite known terrain height in water surface input");++known;}
    unsigned step=policy.initialStep,attempts=0;std::size_t total=0;
    for(;;){++attempts;Detail::PendingMap pending;Stats stats;std::vector<Contour> contours;std::size_t water=0,shore=0;
        const auto count=[&](const Detail::Polygon& polygon,unsigned,SurfaceKind kind){const auto vertices=static_cast<std::size_t>(polygon.count-2)*3;
            if(kind==SurfaceKind::Water)water+=vertices;else shore+=vertices;return water+shore<=policy.maxVertices;};
        bool fits=Detail::PlanePass(context,step,count,&pending,stats);
        if(fits){for(const auto& row:pending)if(row.second.sides==3){contours.push_back(row.second.contour);if(contours.size()>policy.maxContours){fits=false;break;}}}
        if(fits){std::stable_sort(contours.begin(),contours.end(),[](const Contour& a,const Contour& b){return a.ownerCell<b.ownerCell;});
            fits=Detail::ShorePass(context,contours,count);}
        if(fits){result.contours=std::move(contours);result.usedStep=step;result.stats=stats;
            result.stats.validatedKnownHeights=known;result.stats.waterVertices=water;result.stats.shoreVertices=shore;result.stats.lodAttempts=attempts;
            total=water+shore;break;}
        Detail::Require(policy.adaptive&&step<64,"Water surface/contours exceed bounded geometry even at the allowed explicit LOD");step*=2;
    }
    result.vertices.reserve(total);result.ranges.reserve(grid.cells.size()*2);
    const auto emit=[&](const Detail::Polygon& polygon,unsigned owner,SurfaceKind kind){
        const auto start=result.vertices.size();const auto vertex=[&](const Detail::Node& p){return Vertex{
            static_cast<float>(p.x/64),static_cast<float>(result.planeY),static_cast<float>(-p.y/64*OriginalWater::RowSpacing),
            static_cast<float>(p.u),static_cast<float>(p.v),static_cast<float>(static_cast<unsigned>(kind)),static_cast<float>(p.h),0};};
        for(unsigned i=1;i+1<polygon.count;++i){result.vertices.push_back(vertex(polygon.points[0]));result.vertices.push_back(vertex(polygon.points[i]));result.vertices.push_back(vertex(polygon.points[i+1]));}
        Detail::Require(result.vertices.size()<=policy.maxVertices,"Water surface emission exceeded its counted vertex budget");
        const auto count=static_cast<unsigned>(result.vertices.size()-start);
        if(!result.ranges.empty()&&result.ranges.back().ownerCell==owner&&result.ranges.back().kind==kind)result.ranges.back().count+=count;
        else result.ranges.push_back({owner,static_cast<unsigned>(start),count,kind});return true;
    };
    Stats ignored;Detail::Require(Detail::PlanePass(context,result.usedStep,emit,nullptr,ignored),"Water surface emission was interrupted");
    Detail::Require(Detail::ShorePass(context,result.contours,emit)&&result.vertices.size()==total,"Water surface emission differs from count pass");
    return result;
}
}}}
