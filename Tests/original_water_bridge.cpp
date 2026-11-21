#include "OriginalWaterBridge.h"
#include "OriginalWaterState.h"
#include <cstdio>
#include <fstream>
#include <limits>

namespace Water=ZeroSisPresentation::OriginalWater;
namespace Terrain=ZeroSisPresentation::OriginalTerrain;
namespace Sha=ZeroSisPresentation::OriginalTerrain;
namespace {
unsigned checks=0,profileSamples=0,mapCases=0,heightSamples=0,rejections=0;
void Check(bool condition,const char* message){++checks;if(!condition)throw std::runtime_error(message);}
void Near(double actual,double expected,double tolerance=0.00002){
    if(!std::isfinite(actual) || !std::isfinite(expected) || std::abs(actual-expected)>tolerance)
        std::fprintf(stderr,"actual=%.17g expected=%.17g tolerance=%.17g\n",actual,expected,tolerance);
    Check(std::isfinite(actual)&&std::isfinite(expected)&&std::abs(actual-expected)<=tolerance,"Water bridge numeric reference differs");
}
template<class F>void Reject(F fn){bool rejected=false;try{fn();}catch(const std::invalid_argument&){rejected=true;}
    Check(rejected,"Malformed bridge input accepted");++rejections;}
std::vector<unsigned char> Read(const std::string& path){
    std::ifstream stream(path,std::ios::binary|std::ios::ate);Check(stream.good(),"Missing bridge package");const auto length=stream.tellg();
    Check(length>0 && length<=16*1024*1024,"Unbounded bridge input");std::vector<unsigned char> raw(static_cast<std::size_t>(length));stream.seekg(0);
    stream.read(reinterpret_cast<char*>(raw.data()),static_cast<std::streamsize>(raw.size()));Check(stream.good(),"Truncated bridge package");return raw;
}
Water::Grid Grid(int width,int height,bool wx,bool wy,unsigned pattern){
    Water::Grid grid;grid.width=width;grid.height=height;grid.wrapX=wx;grid.wrapY=wy;grid.cells.resize(static_cast<std::size_t>(width)*height);
    for(int y=0;y<height;++y)for(int x=0;x<width;++x){
        auto& cell=grid.cells[static_cast<std::size_t>(y)*width+x];cell.revealed=pattern!=2 && (pattern!=1 || (3*x+y)%5!=0);
        cell.water=pattern==3 || ((pattern==0 || pattern==1 || pattern==2) && (x+2*y)%3==0);
        cell.terrainId=cell.water?6:(x+y)%5;cell.hills=(x+y)%2!=0;cell.mountain=(x+y)%11==0;
        for(unsigned slot=0;slot<3;++slot){cell.river[slot]=(pattern==0 || pattern==1 || pattern==5) && (x+2*y+static_cast<int>(slot))%4==0;
            cell.flow[slot]=static_cast<int>(slot)+(static_cast<unsigned>(x+y)%2?3:0);}
    }
    return grid;
}
Terrain::Atlas Atlas(float height,bool varied=false,bool holes=false){
    Terrain::Atlas atlas;atlas.width=40;atlas.height=24;atlas.originX=0;atlas.originY=0;atlas.wrapX=atlas.wrapY=true;
    atlas.heightOffset=Terrain::HeightOffsetCandidate;
    atlas.ids.resize(40*24,3);atlas.known.resize(40*24,1);atlas.heights.resize(40*24,height);
    for(unsigned y=0;y<24;++y)for(unsigned x=0;x<40;++x){const auto i=y*40+x;
        if(varied)atlas.heights[i]=static_cast<float>(height+0.0002*x-0.0003*y+0.0001*((x*y)%3));
        if(holes && (x+3*y)%7==0){atlas.known[i]=0;atlas.heights[i]=std::numeric_limits<float>::quiet_NaN();}
    }
    return atlas;
}
std::string GeometryHash(const Water::Mesh& mesh){return Sha::Sha256Hex(reinterpret_cast<const unsigned char*>(mesh.vertices.data()),mesh.vertices.size()*sizeof(Water::Vertex));}
int Wrap(int value,int span){return (value%span+span)%span;}
float WorldHeightReference(float centered,float offset){
    const double encoded=(static_cast<double>(centered)+offset)*65535.0;
    const unsigned code=static_cast<unsigned>(std::floor((std::max)(0.0,(std::min)(65535.0,encoded))+.5));
    const float scalar=static_cast<float>(code)*0.0039215688593685626983642578125f;
    const float original=scalar*0.20000000298023223876953125f;
    return (original-12.00000095367431640625f)/64.0f;
}
double HeightReference(const Terrain::Atlas& atlas,double x,double z){
    const double tx=x*64,ty=-z/Terrain::RowSpacing*64;const int ix=static_cast<int>(std::floor(tx)),iy=static_cast<int>(std::floor(ty));
    const double fx=tx-ix,fy=ty-iy;double sum=0,total=0;
    for(int dy=0;dy<2;++dy)for(int dx=0;dx<2;++dx){
        const auto index=static_cast<std::size_t>(Wrap(iy+dy,static_cast<int>(atlas.height)))*atlas.width+static_cast<unsigned>(Wrap(ix+dx,static_cast<int>(atlas.width)));
        if(!atlas.known[index])continue;const double weight=(dx?fx:1-fx)*(dy?fy:1-fy);if(weight==0)continue;
        Check(std::isfinite(atlas.heights[index]),"Reference consumed hidden/nonfinite height");
        // Independent original SSE metric constants and an explicit current
        // display origin. The public centered-float heightmap decodes to u16.
        const float world=WorldHeightReference(atlas.heights[index],atlas.heightOffset);
        sum+=world*weight;total+=weight;
    }
    return total>0?sum/total:0;
}
struct RefOwner {int x=0,y=0;bool exists=false,unique=false;};
RefOwner NearestCenter(const Water::Grid& grid,double x,double z){
    const int row=static_cast<int>(std::floor(-z/Water::RowSpacing));const int col=static_cast<int>(std::floor(x));
    double best=std::numeric_limits<double>::infinity(),second=best;int chosenX=0,chosenY=0;
    for(int y=row-2;y<=row+2;++y)for(int c=col-2;c<=col+2;++c){
        const double cx=c+((y%2+2)%2)*0.5,cz=-y*Water::RowSpacing;const double square=(cx-x)*(cx-x)+(cz-z)*(cz-z);
        if(square<best){second=best;best=square;chosenX=c;chosenY=y;}else if(square<second)second=square;
    }
    RefOwner result;result.unique=second-best>0.00001;
    if(grid.wrapX)chosenX=Wrap(chosenX,grid.width);if(grid.wrapY)chosenY=Wrap(chosenY,grid.height);
    result.x=chosenX;result.y=chosenY;result.exists=chosenX>=0&&chosenY>=0&&chosenX<grid.width&&chosenY<grid.height;return result;
}
void Profiles(const Water::WaterPackage& package,const std::string& filename){
    std::ifstream stream(filename);Check(stream.good(),"Missing profile reference");unsigned count=0;stream>>count;Check(count>8000,"Profile reference incomplete");
    auto styles=package.styles;
    for(unsigned i=0;i<count;++i){unsigned mode=0,index=0,band=0;double t=0,y=0;stream>>mode>>index>>band>>t>>y;Check(stream.good(),"Truncated profile reference");
        if(mode==0){styles[0].waterline.character=index;Near(Water::CoastProfileY(styles,package.profiles,Water::LandStyle::Default,0,t),y,1e-10);}
        else Near(Water::CoastProfileY(package.styles,package.profiles,static_cast<Water::LandStyle>(index),band,t),y,1e-10);
        ++profileSamples;
    }
    Reject([&](){Water::CoastProfileY(package.styles,package.profiles,Water::LandStyle::Grass,3,0.5);});
    Reject([&](){Water::CoastProfileY(package.styles,package.profiles,Water::LandStyle::Grass,0,-0.01);});
    Reject([&](){Water::CoastProfileY(package.styles,package.profiles,Water::LandStyle::Grass,0,std::numeric_limits<double>::quiet_NaN());});
}
void Maps(const Water::WaterPackage& package,const std::string& filename){
    std::ifstream stream(filename);Check(stream.good(),"Missing independent topology reference");unsigned count=0;stream>>count;Check(count>=8,"Map fixtures incomplete");
    const auto atlas=Atlas(0.02f,true);
    for(unsigned i=0;i<count;++i){
        int width=0,height=0;unsigned wx=0,wy=0,pattern=0;std::size_t water=0,coast=0,river=0,vertices=0;
        stream>>width>>height>>wx>>wy>>pattern>>water>>coast>>river>>vertices;Check(stream.good(),"Truncated map reference");
        const auto grid=Grid(width,height,wx!=0,wy!=0,pattern);const auto mesh=Water::BuildAtlasMesh(grid,atlas,package.styles,package.profiles);
        Check(mesh.waterCellCount==water&&mesh.coastEdgeCount==coast&&mesh.riverEdgeCount==river&&mesh.vertices.size()==vertices,"Independent axial topology differs at bridge output");
        Check(mesh.coastSegmentsUsed==8&&mesh.riverSegmentsUsed==4,"Unexpected bridge tessellation reduction");
        std::size_t covered=0;unsigned previous=0;bool first=true;
        for(const auto& range:mesh.ranges){
            Check(range.ownerCell<grid.cells.size()&&grid.cells[range.ownerCell].revealed&&range.start==covered&&range.count%3==0&&
                (first || range.ownerCell>previous),"Bridge ranges lost revealed ownership or contiguous coverage");first=false;previous=range.ownerCell;covered+=range.count;
            const double centerX=(range.ownerCell%grid.width)+((range.ownerCell/grid.width)%2)*0.5;
            const double centerZ=-static_cast<double>(range.ownerCell/grid.width)*Water::RowSpacing;
            for(std::size_t v=range.start;v<range.start+range.count;++v){const auto& vertex=mesh.vertices[v];
                Check(std::isfinite(vertex.x)&&std::isfinite(vertex.y)&&std::isfinite(vertex.z)&&std::isfinite(vertex.depth),"Nonfinite bridge vertex");
                Check(std::abs(vertex.x-centerX)<=1.2&&std::abs(vertex.z-centerZ)<=1.2,"Bridge vertex escaped owner neighborhood");
                const auto owner=NearestCenter(grid,vertex.x,vertex.z);if(!owner.unique)continue;
                const bool known=owner.exists&&grid.cells[static_cast<std::size_t>(owner.y)*grid.width+owner.x].revealed;
                const double source=known?HeightReference(atlas,vertex.x,vertex.z):HeightReference(atlas,centerX,centerZ);
                Near(vertex.y,source+0.002);++heightSamples;
                if(vertex.kind==static_cast<float>(Water::SurfaceKind::Water)){
                    const double raw=source/Terrain::HeightWorldScaleCandidate+Terrain::HeightOffsetCandidate;
                    Near(vertex.depth,raw);Near(Water::RetailDepthColourU(vertex.depth),1-std::max(0.0,std::min(1.0,4*raw)),0.00008);
                }else Check(vertex.depth>=0&&vertex.depth<=1,"Coast/river depth mask escaped byte range");
            }
        }
        Check(covered==mesh.vertices.size(),"Bridge ranges did not cover full mesh");
        if(pattern==2)Check(mesh.vertices.empty()&&mesh.ranges.empty(),"Unknown map emitted water geometry");
        ++mapCases;
    }
    Check(heightSamples>1000,"Independent atlas sample coverage too small");
}
void Mutations(const Water::WaterPackage& package){
    auto grid=Grid(6,4,true,true,1);const auto atlas=Atlas(-0.12f,true,true);
    const auto base=Water::BuildAtlasMesh(grid,atlas,package.styles,package.profiles);const auto hash=GeometryHash(base);
    auto hidden=grid;for(auto& cell:hidden.cells)if(!cell.revealed){cell.water=!cell.water;cell.lake=true;cell.mountain=!cell.mountain;
        cell.terrainId=-1000000;cell.river={{true,true,true}};cell.flow={{999,999,999}};}
    Check(Water::SameWaterGrid(grid,hidden),"Hidden water state affected static key");
    Check(hash==GeometryHash(Water::BuildAtlasMesh(hidden,atlas,package.styles,package.profiles)),"Hidden water state changed bridge geometry");
    auto poisoned=atlas;for(std::size_t i=0;i<poisoned.known.size();++i)if(!poisoned.known[i]){poisoned.heights[i]=std::numeric_limits<float>::infinity();poisoned.ids[i]=254;}
    Check(hash==GeometryHash(Water::BuildAtlasMesh(grid,poisoned,package.styles,package.profiles)),"Unknown atlas material/height leaked into bridge");
    Check(hash==GeometryHash(Water::BuildAtlasMesh(grid,atlas,package.styles,package.profiles)),"Repeated bridge build was nondeterministic");
    auto changed=grid;std::size_t at=0;while(at<changed.cells.size()&&!changed.cells[at].revealed)++at;Check(at<changed.cells.size(),"Missing explored fixture cell");
    changed.cells[at].water=!changed.cells[at].water;changed.cells[at].lake=false;
    Check(!Water::SameWaterGrid(grid,changed)&&hash!=GeometryHash(Water::BuildAtlasMesh(changed,atlas,package.styles,package.profiles)),"Explored water state failed to invalidate geometry");
    const auto plain=Grid(4,4,true,true,3);const auto a=Water::BuildAtlasMesh(plain,Atlas(-0.125f),package.styles,package.profiles);
    const auto b=Water::BuildAtlasMesh(plain,Atlas(-0.075f),package.styles,package.profiles);
    Check(GeometryHash(a)!=GeometryHash(b)&&a.vertices.size()==b.vertices.size(),"Atlas height change failed to alter geometry");
    for(std::size_t i=0;i<a.vertices.size();++i){Near(a.vertices[i].x,b.vertices[i].x,0);Near(a.vertices[i].z,b.vertices[i].z,0);
        const float wa=WorldHeightReference(-.125f,Terrain::HeightOffsetCandidate),wb=WorldHeightReference(-.075f,Terrain::HeightOffsetCandidate);
        Near(b.vertices[i].y-a.vertices[i].y,static_cast<double>(wb)-wa,1e-7);
        Near(a.vertices[i].depth,wa/Terrain::HeightWorldScaleCandidate+Terrain::HeightOffsetCandidate,1e-7);
        Near(b.vertices[i].depth,wb/Terrain::HeightWorldScaleCandidate+Terrain::HeightOffsetCandidate,1e-7);}
    for(float height:{-0.3f,-0.125f,-0.02f,0.1f}){const auto mesh=Water::BuildAtlasMesh(plain,Atlas(height),package.styles,package.profiles);
        const double raw=WorldHeightReference(height,Terrain::HeightOffsetCandidate)/Terrain::HeightWorldScaleCandidate+Terrain::HeightOffsetCandidate;
        const double expected=1-std::max(0.0,std::min(1.0,4*raw));
        for(const auto& vertex:mesh.vertices)Near(Water::RetailDepthColourU(vertex.depth),expected,1e-6);}
    auto river=Grid(4,4,true,true,4);river.cells[5].river[0]=true;river.cells[5].flow[0]=0;
    const auto north=Water::BuildAtlasMesh(river,Atlas(0),package.styles,package.profiles);river.cells[5].flow[0]=3;
    const auto south=Water::BuildAtlasMesh(river,Atlas(0),package.styles,package.profiles);
    Check(north.riverEdgeCount==1&&south.riverEdgeCount==1&&north.vertices.size()==24&&GeometryHash(north)!=GeometryHash(south),"River flow state did not reach bridge vertices");
    for(std::size_t i=0;i<north.vertices.size();++i){Near(north.vertices[i].x,south.vertices[i].x,0);Near(north.vertices[i].z,south.vertices[i].z,0);
        Check(north.vertices[i].flowSign==-1&&south.vertices[i].flowSign==1,"River flow sign differs");}
}
void Malformed(const Water::WaterPackage& package){
    const auto grid=Grid(4,4,true,true,0);const auto atlas=Atlas(0);
    for(unsigned mode=0;mode<7;++mode){auto profiles=package.profiles;
        if(mode==0)profiles[0].points.pop_back();else if(mode==1)profiles[0].points.push_back(profiles[0].points.back());
        else if(mode==2)profiles[0].points[1].x=std::numeric_limits<double>::quiet_NaN();
        else if(mode==3)profiles[0].points[1].y=std::numeric_limits<double>::infinity();
        else if(mode==4)profiles[0].points[1].z=1;
        else if(mode==5)profiles[0].points[1].x=profiles[0].points[0].x;else profiles[0].points[1].x=401;
        Reject([&](){Water::BuildAtlasMesh(grid,atlas,package.styles,profiles);});
    }
    auto styles=package.styles;styles[0].name="wrong";Reject([&](){Water::BuildAtlasMesh(grid,atlas,styles,package.profiles);});
    styles=package.styles;styles.pop_back();Reject([&](){Water::BuildAtlasMesh(grid,atlas,styles,package.profiles);});
    auto profiles=package.profiles;profiles.pop_back();Reject([&](){Water::BuildAtlasMesh(grid,atlas,package.styles,profiles);});
    auto incomplete=atlas;incomplete.known.pop_back();Reject([&](){Water::BuildAtlasMesh(grid,incomplete,package.styles,package.profiles);});
    auto bad=atlas;for(auto& value:bad.heights)value=std::numeric_limits<float>::quiet_NaN();Reject([&](){Water::BuildAtlasMesh(grid,bad,package.styles,package.profiles);});
    Water::MeshPolicy policy;policy.maxVertices=1;Reject([&](){Water::BuildAtlasMesh(grid,atlas,package.styles,package.profiles,policy);});
}
}
int main(int argc,char** argv){
    try{Check(argc==4,"Bridge arguments differ");const auto package=Water::DecodePackage(Read(argv[1]),"2ff227dae9d16398e038e8ea33624940a9581e0eb2d37c3891121fae22c25afc");
        Profiles(package,argv[2]);Maps(package,argv[3]);Mutations(package);Malformed(package);
        std::printf("PASS_ORIGINAL_WATER_BRIDGE checks=%u profile_samples=%u maps=%u height_samples=%u rejections=%u\n",checks,profileSamples,mapCases,heightSamples,rejections);return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"FAIL: %s\n",error.what());return 1;}
}
