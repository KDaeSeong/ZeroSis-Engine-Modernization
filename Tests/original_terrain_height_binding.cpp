#include "OriginalTerrainGeometry.h"
#include "height_binding_golden.h"
#include <cstdio>
#include <limits>

namespace T=ZeroSisPresentation::OriginalTerrain;
namespace S=ZeroSisPresentation::OriginalTerrainCacheSampling;
static unsigned checks=0;
static void Check(bool condition){++checks;if(!condition){std::fprintf(stderr,"check=%u\n",checks);throw std::runtime_error("Terrain height binding assertion failed");}}
static void Near(double actual,double expected,double tolerance=1e-7){
    if(std::abs(actual-expected)>tolerance)std::fprintf(stderr,"actual=%.17g expected=%.17g tolerance=%.17g\n",actual,expected,tolerance);
    Check(std::abs(actual-expected)<=tolerance);}
template<class Action>void Reject(Action action){bool caught=false;try{action();}catch(const std::invalid_argument&){caught=true;}Check(caught);}
static T::Atlas Atlas(unsigned side=2){T::Atlas a;a.width=a.height=side;a.heightOffset=T::HeightOffsetCandidate;
    a.ids.assign(side*side,3);a.known.assign(side*side,1);a.heights.assign(side*side,0);return a;}
static void Store(T::Atlas& a,std::size_t at,unsigned code){a.heights[at]=static_cast<float>(code)*(1.0f/65535.0f)-a.heightOffset;}
static double World(unsigned code){
    // Independent decimal/rational reference. The production helper preserves
    // original scalar float rounding; the comparison budget covers those ulps.
    return ((static_cast<double>(code)/255)*0.2-12)/64;
}
static void Codec(){
    auto a=Atlas(1);
    for(const float offset:{-2.0f,-1.0f,-0.25f,0.0f,T::HeightOffsetCandidate,0.5f,1.0f,2.0f}){
        a.heightOffset=offset;
        for(unsigned code=0;code<65536;++code){Store(a,0,code);Check(T::Detail::HeightmapCode(a,0)==code);}
    }
    a.heightOffset=T::HeightOffsetCandidate;a.known[0]=0;a.heights[0]=std::numeric_limits<float>::quiet_NaN();
    Reject([&]{T::Detail::HeightmapCode(a,0);});Near(T::AtlasWorldHeight(a,0,0),0);
    a.known[0]=1;Reject([&]{T::AtlasWorldHeight(a,0,0);});
    Check(T::HeightWorldScaleCandidate==S::NormalizedHeightRangeDefault);
    Near(T::HeightWorldScaleCandidate,0.803125,0.000001);Near(T::DisplayHeightOriginCandidate(),12,0.000001);
}
static void Sampling(){
    auto a=Atlas();const unsigned codes[4]={10000,30000,50000,65000};
    for(unsigned i=0;i<4;++i)Store(a,i,codes[i]);
    for(const bool wrapX:{false,true})for(const bool wrapY:{false,true}){
        a.wrapX=wrapX;a.wrapY=wrapY;
        for(const double x:{-0.75,0.0,0.25,1.0,1.25,2.0})for(const double y:{-0.5,0.0,0.5,1.0,1.5,2.0}){
            double expected=0,total=0;const int ix=static_cast<int>(std::floor(x)),iy=static_cast<int>(std::floor(y));
            const double fx=x-ix,fy=y-iy;
            for(unsigned index=0;index<4;++index){int px=ix+static_cast<int>(index%2),py=iy+static_cast<int>(index/2);
                if(!wrapX&&(px<0||px>=2))continue;if(!wrapY&&(py<0||py>=2))continue;
                px=(px%2+2)%2;py=(py%2+2)%2;
                const double weight=(index%2?fx:1-fx)*(index/2?fy:1-fy);
                expected+=World(codes[static_cast<unsigned>(py*2+px)])*weight;total+=weight;}
            Near(T::AtlasWorldHeight(a,x,y),total?expected/total:0,2e-7);
        }
    }
    a.wrapX=a.wrapY=false;Store(a,0,15300);Store(a,1,25500);Store(a,2,35700);Store(a,3,45900);
    Near(T::AtlasWorldHeight(a,0.25,0.5),World(15300)*0.375+World(25500)*0.125+World(35700)*0.375+World(45900)*0.125,2e-7);
    const auto display=T::AtlasWorldHeight(a,0.25,0.5);
    // The independent decimal oracle omits the original two float multiplies;
    // allow two source-world ulps after interpolation and origin restoration.
    Near(S::RestoreOriginalHeight(display,T::DisplayHeightOriginCandidate()),22,0.000008);
    // Known NaN at a zero-weight neighbour must not be fetched.
    a.heights[1]=a.heights[2]=a.heights[3]=std::numeric_limits<float>::quiet_NaN();
    Near(T::AtlasWorldHeight(a,0,0),World(15300),2e-7);
    // A double fraction can round to exactly 0 or 1 in the float weight calculation.
    auto corner=Atlas();
    corner.wrapX=corner.wrapY=false;
    corner.heights.assign(4,std::numeric_limits<float>::quiet_NaN());
    Store(corner,3,25500);
    const auto belowOne=std::nextafter(1.0,0.0);
    Near(T::AtlasWorldHeight(corner,belowOne,belowOne),World(25500),2e-7);
    Near(T::AtlasWorldHeight(corner,1,belowOne),World(25500),2e-7);
    Store(corner,0,15300);
    Near(T::AtlasWorldHeight(corner,std::nextafter(0.0,1.0),0),World(15300),2e-7);
    // Hidden nonzero-weight payloads are excluded before numeric reads.
    a.known[1]=a.known[2]=a.known[3]=0;
    Near(T::AtlasWorldHeight(a,0.25,0.5),World(15300),2e-7);
    a.wrapX=a.wrapY=false;Near(T::AtlasWorldHeight(a,2,0),0);Near(T::AtlasWorldHeight(a,0,2),0);
    a.wrapX=true;Near(T::AtlasWorldHeight(a,2,0),World(15300),2e-7);
    a.wrapX=false;a.wrapY=true;Near(T::AtlasWorldHeight(a,0,2),World(15300),2e-7);
    a.wrapX=a.wrapY=true;Near(T::AtlasWorldHeight(a,-2,-2),World(15300),2e-7);
    Reject([&]{T::AtlasWorldHeight(a,std::numeric_limits<double>::quiet_NaN(),0);});
}
static void Normals(){
    auto a=Atlas(7);for(unsigned i=0;i<49;++i)Store(a,i,15300);
    a.wrapX=a.wrapY=false;
    const auto n=T::SurfaceNormal(a,3,3,T::HeightWorldScaleCandidate);
    // Original opcode DAG flat-code golden from phase8, independent of the
    // production normal helper. Original positive flat tilt is preserved.
    const float g=0.056617219001054764f,mx=1.0f/64,my=0.866f/64;
    const float scale=T::HeightWorldScaleCandidate*(255.0f/65535.0f);
    const float nx=my*(g*scale),ny=mx*(g*scale),nz=my*mx;
    const double length=std::sqrt(static_cast<double>(nx)*nx+static_cast<double>(ny)*ny+static_cast<double>(nz)*nz);
    Near(n.x,static_cast<float>(nx/length),0);Near(n.y,static_cast<float>(ny/length),0);Near(n.z,static_cast<float>(nz/length),0);
    // Opposite-edge poison is reachable only with the corresponding wrap flag.
    a.heights[3*7+6]=std::numeric_limits<float>::quiet_NaN();
    const auto edge=T::SurfaceNormal(a,0,3,T::HeightWorldScaleCandidate);Check(std::isfinite(edge.x));
    a.wrapX=true;Reject([&]{T::SurfaceNormal(a,0,3,T::HeightWorldScaleCandidate);});
    a.wrapX=false;Store(a,3*7+6,15300);a.heights[6*7+3]=std::numeric_limits<float>::quiet_NaN();
    Check(std::isfinite(T::SurfaceNormal(a,3,0,T::HeightWorldScaleCandidate).x));
    a.wrapY=true;Reject([&]{T::SurfaceNormal(a,3,0,T::HeightWorldScaleCandidate);});
    a.wrapY=false;a.known[0]=0;a.heights[0]=std::numeric_limits<float>::quiet_NaN();
    const auto hidden=T::SurfaceNormal(a,0,0,T::HeightWorldScaleCandidate);Near(hidden.x,0);Near(hidden.y,0);Near(hidden.z,1);
}
static void Word(std::vector<unsigned char>& raw,std::size_t at,std::uint32_t value){for(unsigned b=0;b<4;++b)raw[at+b]=static_cast<unsigned char>(value>>(b*8));}
static void AppendWord(std::vector<unsigned char>& raw,std::uint32_t value){const auto at=raw.size();raw.resize(at+4);Word(raw,at,value);}
static void Half(std::vector<unsigned char>& raw,unsigned value){raw.push_back(static_cast<unsigned char>(value));raw.push_back(static_cast<unsigned char>(value>>8));}
static std::vector<unsigned char> Fixture(){
    std::vector<unsigned char> raw,rows,bytes,halves,records(2*0x56c,0);
    for(unsigned piece=0;piece<2;++piece){const auto at=static_cast<std::size_t>(piece)*0x56c;
        for(const unsigned field:{0x94u,0x98u,0x3c0u,0x3c4u})Word(records,at+field,10);
        Word(records,at+0x3bc,piece);Word(records,at+0x3c8,1);Word(records,at+0x3d0,1);records[at+0x3ea]='P';
        for(unsigned cell=0;cell<100;++cell){Word(records,at+0x9c+cell*8,0xffffffffu);records[at+0x9c+cell*8+6]=0x4d;}
        Word(records,at+0x9c,1);records[at+0xa1]=1;
        for(unsigned channel=0;channel<4;++channel){Word(records,at+0x3d4+channel*4,static_cast<std::uint32_t>(rows.size()/4));
            for(unsigned y=0;y<128;++y){if(!channel){AppendWord(rows,static_cast<std::uint32_t>(halves.size()/2));Half(halves,128);Half(halves,piece?65535:32768);}
                else{AppendWord(rows,static_cast<std::uint32_t>(bytes.size()));bytes.push_back(128);
                    bytes.push_back(static_cast<unsigned char>(channel==1?7:channel==2?(piece?128:255):128));}}}
    }
    AppendWord(raw,20);AppendWord(raw,static_cast<std::uint32_t>(rows.size()/4));raw.insert(raw.end(),rows.begin(),rows.end());
    AppendWord(raw,static_cast<std::uint32_t>(bytes.size()));raw.insert(raw.end(),bytes.begin(),bytes.end());
    AppendWord(raw,static_cast<std::uint32_t>(halves.size()/2));raw.insert(raw.end(),halves.begin(),halves.end());
    AppendWord(raw,2);raw.insert(raw.end(),records.begin(),records.end());return raw;
}
static void Stamp(){
    const auto library=T::DecodeLibrary(Fixture());T::PlotInput plot;plot.terrainType=0;
    std::vector<T::Cell> cells(4,T::MakeCell(plot));const std::vector<T::Placement> placements={{0,0,0,0},{1,0,0,0}};
    for(unsigned i=0;i<HeightBindingGolden::Count;++i){const float offset=HeightBindingGolden::Offsets[i];
        const auto atlas=T::BuildAtlas(cells,2,2,library,placements,offset,T::DefaultMaxAtlasTexels,true,true);
        const auto at=64u*128+64;Check(atlas.known[at]!=0);Check(atlas.ids[at]==7);
        Check(T::Detail::HeightmapCode(atlas,at)==HeightBindingGolden::Raw[i]);
        Near(T::AtlasWorldHeight(atlas,64,64),World(HeightBindingGolden::Raw[i]),2e-7);
    }
    cells[1].revealed=false;
    const auto masked=T::BuildAtlas(cells,2,2,library,placements,T::HeightOffsetCandidate,T::DefaultMaxAtlasTexels,true,true);
    unsigned hidden=0;for(std::size_t i=0;i<masked.known.size();++i)if(!masked.known[i]){++hidden;Check(masked.ids[i]==T::UnknownRow&&masked.heights[i]==0);}
    Check(hidden>0);
}
int main(){try{Codec();Sampling();Normals();Stamp();std::printf("PASS_ORIGINAL_TERRAIN_HEIGHT_BINDING checks=%u\n",checks);return 0;}
    catch(const std::exception& e){std::fprintf(stderr,"%s\n",e.what());return 1;}}
