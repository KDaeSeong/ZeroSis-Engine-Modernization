#pragma once

// Detached, exploration-safe topology for water, coast and river overlays.
// SDK shared-edge ownership is reconstructed from source. Rendering calibration
// and interpretation of the original coast profiles remain explicit candidates.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <vector>

namespace ZeroSisPresentation { namespace OriginalWater {

constexpr double RowSpacing=static_cast<double>(0.866025404f);
constexpr std::size_t MaxCells=16384;
constexpr std::size_t MaxEdges=6*MaxCells;
constexpr std::size_t MaxVertices=2ull*1024*1024;

enum class Direction : unsigned {NE=0,E=1,SE=2,SW=3,W=4,NW=5};
enum class LandStyle : unsigned {Default=0,Grass,GrassHill,Plains,PlainsHill,Snow,SnowHill,
    Desert,DesertHill,Tundra,TundraHill,Mountain,DefaultShallows};
struct Point2 {double x=0,z=0;};
struct Cell {
    bool revealed=false,water=false,lake=false,hills=false,mountain=false;
    int terrainId=-1;
    std::array<bool,3> river{{false,false,false}}; // Canonical E, SE, SW.
    std::array<int,3> flow{{-1,-1,-1}};
};
struct Grid {int width=0,height=0;bool wrapX=false,wrapY=false;std::vector<Cell> cells;};
struct Neighbor {int x=-1,y=-1;bool exists=false;};
struct SharedEdge {
    unsigned owner=0,neighbor=0;Direction direction=Direction::E;int flow=-1;
    bool ownerWater=false,neighborWater=false;
    LandStyle style=LandStyle::Default;
    Point2 a,b;
};
struct Topology {std::vector<unsigned> waterCells;std::vector<SharedEdge> coasts,rivers;};
enum class SurfaceKind : unsigned {Water=0,Coast=1,River=2};
struct Vertex {float x=0,y=0,z=0,u=0,v=0,kind=0,depth=0,flowSign=0;};
struct DrawRange {unsigned ownerCell=0,start=0,count=0;};
struct Mesh {
    std::vector<Vertex> vertices;std::vector<DrawRange> ranges;
    unsigned coastSegmentsUsed=0,riverSegmentsUsed=0,fallbackHeightSamples=0;
    std::size_t waterCellCount=0,coastEdgeCount=0,riverEdgeCount=0;
};
struct MeshPolicy {
    unsigned coastSegments=8,riverSegments=4;
    double coastWidth=0.12,riverWidth=0.07,lift=0.002,uvScale=1,waterDepth=0.5;
    double profileUnits=64,maxMeander=0.12;
    std::size_t maxVertices=MaxVertices;
};
static_assert(sizeof(Vertex)==32,"Original water overlay vertex must remain 32 bytes");

namespace Detail {
inline void Require(bool value,const char* reason){if(!value)throw std::invalid_argument(reason);}
inline bool Shape(const Grid& grid) noexcept {
    return grid.width>0&&grid.height>0&&grid.width<=256&&grid.height<=256&&
        static_cast<std::size_t>(grid.width)*grid.height<=MaxCells&&
        grid.cells.size()==static_cast<std::size_t>(grid.width)*grid.height&&(!grid.wrapY||grid.height%2==0);
}
inline bool ValidFlow(unsigned slot,int flow) noexcept {
    return slot<3&&(flow==-1||flow==static_cast<int>(slot)||flow==static_cast<int>(slot+3));
}
inline bool ValidCell(const Cell& cell) noexcept {
    if(!cell.revealed)return true;
    if((cell.lake&&!cell.water)||cell.terrainId< -1)return false;
    for(unsigned slot=0;slot<3;++slot)if(cell.river[slot]&&!ValidFlow(slot,cell.flow[slot]))return false;
    return true;
}
inline void Validate(const Grid& grid){
    Require(Shape(grid),"Invalid bounded original water grid");
    for(const auto& cell:grid.cells)Require(ValidCell(cell),"Invalid original water cell or river flow");
}
inline int Wrap(int value,int span){const int result=value%span;return result<0?result+span:result;}
inline Neighbor Adjacent(const Grid& grid,int x,int y,Direction direction){
    const int parity=y&1;int nx=x,ny=y;
    switch(direction){
    case Direction::NE:nx+=parity;++ny;break;
    case Direction::E:++nx;break;
    case Direction::SE:nx+=parity;--ny;break;
    case Direction::SW:nx+=parity-1;--ny;break;
    case Direction::W:--nx;break;
    case Direction::NW:nx+=parity-1;++ny;break;
    default:Require(false,"Invalid original water edge direction");
    }
    if(grid.wrapX)nx=Wrap(nx,grid.width);if(grid.wrapY)ny=Wrap(ny,grid.height);
    if(nx<0||ny<0||nx>=grid.width||ny>=grid.height)return {};
    return {nx,ny,true};
}
inline Point2 Center(int x,int y){return {x+((y&1)?0.5:0.0),-y*RowSpacing};}
inline std::array<Point2,6> Corners(Point2 center){
    const double half=RowSpacing/3,full=half*2;
    return {{{center.x,center.z-full},{center.x+0.5,center.z-half},{center.x+0.5,center.z+half},
        {center.x,center.z+full},{center.x-0.5,center.z+half},{center.x-0.5,center.z-half}}};
}
}

inline Neighbor NeighborOf(const Grid& grid,int x,int y,Direction direction){
    Detail::Require(Detail::Shape(grid)&&x>=0&&y>=0&&x<grid.width&&y<grid.height,
        "Invalid original water neighbor query");
    return Detail::Adjacent(grid,x,y,direction);
}
inline Neighbor OwnerAt(const Grid& grid,double x,double z){
    Detail::Require(Detail::Shape(grid)&&std::isfinite(x)&&std::isfinite(z)&&std::abs(x)<=1000000&&std::abs(z)<=1000000,
        "Invalid original water world coordinate");
    const double row=-z/RowSpacing,q=x-row*0.5,s=-q-row;
    int iq=static_cast<int>(std::round(q)),ir=static_cast<int>(std::round(row));const int is=static_cast<int>(std::round(s));
    const double dq=std::abs(iq-q),dr=std::abs(ir-row),ds=std::abs(is-s);
    if(dq>dr&&dq>ds)iq=-ir-is;else if(dr>ds)ir=-iq-is;
    const int half=ir/2-((ir<0&&ir%2)?1:0);int col=iq+half;
    if(grid.wrapX)col=Detail::Wrap(col,grid.width);if(grid.wrapY)ir=Detail::Wrap(ir,grid.height);
    if(col<0||ir<0||col>=grid.width||ir>=grid.height)return {};
    return {col,ir,true};
}
inline const char* StyleName(LandStyle style){
    constexpr const char* names[]={"Default","Grass","GrassHill","Plains","PlainsHill","Snow","SnowHill",
        "Desert","DesertHill","Tundra","TundraHill","Mountain","DefaultShallows"};
    const auto index=static_cast<unsigned>(style);Detail::Require(index<13,"Invalid original coast style");return names[index];
}
inline LandStyle StyleForLand(const Cell& cell){
    Detail::Require(cell.revealed&&!cell.water,"Original coast style requires explored land");
    if(cell.mountain)return LandStyle::Mountain;
    switch(cell.terrainId){
    case 0:return cell.hills?LandStyle::GrassHill:LandStyle::Grass;
    case 1:return cell.hills?LandStyle::PlainsHill:LandStyle::Plains;
    case 2:return cell.hills?LandStyle::DesertHill:LandStyle::Desert;
    case 3:return cell.hills?LandStyle::TundraHill:LandStyle::Tundra;
    case 4:return cell.hills?LandStyle::SnowHill:LandStyle::Snow;
    default:return LandStyle::Default;
    }
}
inline Topology BuildTopology(const Grid& grid){
    Detail::Validate(grid);Topology result;
    for(int y=0;y<grid.height;++y)for(int x=0;x<grid.width;++x){
        const unsigned owner=static_cast<unsigned>(y*grid.width+x);const auto& cell=grid.cells[owner];
        if(!cell.revealed)continue;if(cell.water)result.waterCells.push_back(owner);
        const auto corners=Detail::Corners(Detail::Center(x,y));
        for(unsigned slot=0;slot<3;++slot){const auto direction=static_cast<Direction>(slot+1);
            const auto other=Detail::Adjacent(grid,x,y,direction);if(!other.exists)continue;
            const unsigned neighbor=static_cast<unsigned>(other.y*grid.width+other.x);
            const auto& next=grid.cells[neighbor];if(!next.revealed)continue;
            SharedEdge edge;edge.owner=owner;edge.neighbor=neighbor;edge.direction=direction;
            edge.ownerWater=cell.water;edge.neighborWater=next.water;
            edge.a=corners[slot+1];edge.b=corners[(slot+2)%6];
            if(cell.water!=next.water){edge.style=StyleForLand(cell.water?next:cell);result.coasts.push_back(edge);}
            if(cell.river[slot]){edge.flow=cell.flow[slot];result.rivers.push_back(edge);}
            Detail::Require(result.coasts.size()+result.rivers.size()<=MaxEdges,"Original water edge budget exceeded");
        }
    }
    return result;
}

// Exact operations from the pinned Water VS/PS listings. Runtime scale/time
// constants and the original cached height input are supplied by the caller.
inline std::array<std::array<double,2>,4> RetailWaterUvs(double x,double y,
    const std::array<double,4>& scales,double offset){
    Detail::Require(std::isfinite(x)&&std::isfinite(y)&&std::isfinite(offset)&&std::abs(x)<=1000000&&
        std::abs(y)<=1000000&&std::abs(offset)<=1000000,"Invalid retail water UV input");
    for(const auto scale:scales)Detail::Require(std::isfinite(scale)&&std::abs(scale)<=4096,"Invalid retail water UV scale");
    return {{{{x*scales[0]+offset,y*scales[0]+offset}},{{-x*scales[1]+offset,y*scales[1]+offset}},
        {{-x*scales[2]+offset,-y*scales[2]+offset}},{{x*scales[3]+offset,-y*scales[3]+offset}}}};
}
inline double RetailDepthColourU(double heightAlpha){
    Detail::Require(std::isfinite(heightAlpha),"Nonfinite retail water height alpha");
    return 1-(std::max)(0.0,(std::min)(1.0,4*heightAlpha));
}
inline double RetailRiverVertexV(double inputV,double time){
    Detail::Require(std::isfinite(inputV)&&std::isfinite(time)&&std::abs(inputV)<=1000000&&std::abs(time)<=1000000000,
        "Invalid retail river vertex UV input");
    // The confirmed River PS pass 0 does not consume this shifted coordinate.
    return inputV-static_cast<double>(0.05f)*time;
}
inline float FlowSign(const SharedEdge& edge){
    const unsigned direction=static_cast<unsigned>(edge.direction);
    Detail::Require(direction>=1&&direction<=3&&Detail::ValidFlow(direction-1,edge.flow),"Invalid canonical river flow");
    return edge.flow==-1?0.0f:edge.flow<3?-1.0f:1.0f;
}

namespace Detail {
inline void Policy(const MeshPolicy& policy){
    Require(policy.coastSegments>=1&&policy.coastSegments<=64&&policy.riverSegments>=1&&policy.riverSegments<=64&&
        policy.maxVertices>0&&policy.maxVertices<=MaxVertices,"Invalid original water mesh budget");
    Require(std::isfinite(policy.coastWidth)&&policy.coastWidth>0&&policy.coastWidth<=1&&
        std::isfinite(policy.riverWidth)&&policy.riverWidth>0&&policy.riverWidth<=1&&
        std::isfinite(policy.lift)&&policy.lift>=0&&policy.lift<=0.1&&
        std::isfinite(policy.uvScale)&&policy.uvScale>0&&policy.uvScale<=4096&&
        std::isfinite(policy.waterDepth)&&policy.waterDepth>=0&&policy.waterDepth<=1&&
        std::isfinite(policy.profileUnits)&&policy.profileUnits>0&&policy.profileUnits<=1000000&&
        std::isfinite(policy.maxMeander)&&policy.maxMeander>=0&&policy.maxMeander<=0.5,"Invalid original water mesh policy");
}
inline std::size_t Needed(const Topology& topology,unsigned coastSegments,unsigned riverSegments){
    return topology.waterCells.size()*18+(topology.coasts.size()*coastSegments+topology.rivers.size()*riverSegments)*6;
}
}

// Candidate geometry: atlas-following colour overlays, unlike the retail flat
// Water VS plane. The caller owns GPU colour-only/depth-read/picking protection.
template<class HeightFn,class ProfileFn>Mesh BuildMesh(const Grid& grid,HeightFn height,ProfileFn profile,
    const MeshPolicy& policy=MeshPolicy{}){
    Detail::Validate(grid);Detail::Policy(policy);const auto topology=BuildTopology(grid);Mesh result;
    unsigned coastSegments=policy.coastSegments,riverSegments=policy.riverSegments;
    while(Detail::Needed(topology,coastSegments,riverSegments)>policy.maxVertices&&(coastSegments>1||riverSegments>1)){
        const auto coastCost=topology.coasts.size()*coastSegments,riverCost=topology.rivers.size()*riverSegments;
        if(coastSegments>1&&(riverSegments==1||coastCost>=riverCost))coastSegments=(coastSegments+1)/2;
        else riverSegments=(riverSegments+1)/2;
    }
    const auto needed=Detail::Needed(topology,coastSegments,riverSegments);
    Detail::Require(needed<=policy.maxVertices,"Original water geometry exceeds its bounded vertex budget");
    result.coastSegmentsUsed=coastSegments;result.riverSegmentsUsed=riverSegments;
    result.waterCellCount=topology.waterCells.size();result.coastEdgeCount=topology.coasts.size();result.riverEdgeCount=topology.rivers.size();
    result.vertices.reserve(needed);result.ranges.reserve(grid.cells.size());
    std::size_t waterAt=0,coastAt=0,riverAt=0;
    for(unsigned owner=0;owner<grid.cells.size();++owner){
        if(!grid.cells[owner].revealed)continue;
        const auto start=result.vertices.size();const auto center=Detail::Center(static_cast<int>(owner%grid.width),static_cast<int>(owner/grid.width));
        bool haveAnchor=false;double anchor=0;
        const auto vertex=[&](Point2 point,double u,double v,SurfaceKind kind,double depth,float flow){
            const auto location=OwnerAt(grid,point.x,point.z);
            const bool known=location.exists&&grid.cells[static_cast<std::size_t>(location.y)*grid.width+location.x].revealed;
            double y=0;
            if(known)y=height(point.x,point.z);
            else{
                if(!haveAnchor){anchor=height(center.x,center.z);haveAnchor=true;}
                y=anchor;++result.fallbackHeightSamples;
            }
            Detail::Require(std::isfinite(y)&&std::abs(y)<=1000000&&std::isfinite(u)&&std::isfinite(v),
                "Invalid original water height callback or vertex UV");
            return Vertex{static_cast<float>(point.x),static_cast<float>(y+policy.lift),static_cast<float>(point.z),
                static_cast<float>(u),static_cast<float>(v),static_cast<float>(static_cast<unsigned>(kind)),static_cast<float>(depth),flow};
        };
        if(waterAt<topology.waterCells.size()&&topology.waterCells[waterAt]==owner){
            const auto corners=Detail::Corners(center);std::array<Vertex,6> ring;
            const auto middle=vertex(center,center.x*policy.uvScale,center.z*policy.uvScale,SurfaceKind::Water,policy.waterDepth,0);
            for(unsigned corner=0;corner<6;++corner)ring[corner]=vertex(corners[corner],corners[corner].x*policy.uvScale,
                corners[corner].z*policy.uvScale,SurfaceKind::Water,policy.waterDepth,0);
            for(unsigned corner=0;corner<6;++corner){result.vertices.push_back(middle);result.vertices.push_back(ring[(corner+1)%6]);
                result.vertices.push_back(ring[corner]);}
            ++waterAt;
        }
        const auto strip=[&](const SharedEdge& edge,SurfaceKind kind,unsigned segments){
            const double dx=edge.b.x-edge.a.x,dz=edge.b.z-edge.a.z,length=std::sqrt(dx*dx+dz*dz);
            Detail::Require(std::isfinite(length)&&length>0,"Invalid original water shared edge geometry");
            const Point2 normal{dz/length,-dx/length};const bool coast=kind==SurfaceKind::Coast;
            const double width=coast?policy.coastWidth:policy.riverWidth;
            double first=0,last=0;
            if(coast){first=profile(edge.style,0u,0.0);last=profile(edge.style,0u,1.0);
                Detail::Require(std::isfinite(first)&&std::isfinite(last)&&std::abs(first)<=1000000&&std::abs(last)<=1000000,
                    "Invalid original coast endpoint profile sample");}
            const auto across=[&](double t,double side){
                double shift=0;
                if(coast&&t>0&&t<1){const double raw=profile(edge.style,0u,t);
                    Detail::Require(std::isfinite(raw)&&std::abs(raw)<=1000000,"Invalid original coast profile sample");
                    shift=(raw-(first+(last-first)*t))/policy.profileUnits;
                    shift=(std::max)(-policy.maxMeander,(std::min)(policy.maxMeander,shift));}
                const double transverse=shift+(side-0.5)*width;
                const Point2 point{edge.a.x+dx*t+normal.x*transverse,edge.a.z+dz*t+normal.z*transverse};
                const double depth=coast?(edge.ownerWater?1-side:side):1;
                return vertex(point,length*t*policy.uvScale,side,kind,depth,coast?0:FlowSign(edge));
            };
            for(unsigned segment=0;segment<segments;++segment){
                const double t0=static_cast<double>(segment)/segments,t1=static_cast<double>(segment+1)/segments;
                const auto a=across(t0,0),b=across(t0,1),c=across(t1,0),d=across(t1,1);
                result.vertices.push_back(a);result.vertices.push_back(c);result.vertices.push_back(b);
                result.vertices.push_back(b);result.vertices.push_back(c);result.vertices.push_back(d);
            }
        };
        while(coastAt<topology.coasts.size()&&topology.coasts[coastAt].owner==owner)
            strip(topology.coasts[coastAt++],SurfaceKind::Coast,coastSegments);
        while(riverAt<topology.rivers.size()&&topology.rivers[riverAt].owner==owner)
            strip(topology.rivers[riverAt++],SurfaceKind::River,riverSegments);
        if(result.vertices.size()!=start)result.ranges.push_back({owner,static_cast<unsigned>(start),
            static_cast<unsigned>(result.vertices.size()-start)});
    }
    Detail::Require(result.vertices.size()==needed&&waterAt==topology.waterCells.size()&&coastAt==topology.coasts.size()&&
        riverAt==topology.rivers.size(),"Original water mesh ranges do not cover their exact topology");
    return result;
}
}}
