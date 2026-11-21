#pragma once

// CPU reference for the reconstructed terrain rules. Original row-vector
// orientation composition is statically recovered; prior rand() calls remain
// a comparison gate: rule-equivalent, placement parity unverified.
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include "OriginalTerrainCacheSamplingModel.h"
#include <vector>
#include "OriginalTerrainNormalModel.h"
#include "OriginalTerrainCacheModel.h"

namespace ZeroSisPresentation { namespace OriginalTerrain {

constexpr unsigned TexelsPerHex=64;
constexpr unsigned UnknownRow=255;
constexpr std::size_t DefaultMaxAtlasTexels=64ull*1024*1024;

struct Cell {
    std::uint32_t mask=0xffffffffu;
    std::uint8_t continent=0;
    bool owned=false;
    bool revealed=true;
};
struct PlotInput {
    int terrainType=-1,continent=0;
    bool exists=true,revealed=true,hills=false,mountain=false,naturalWonder=false;
    std::string feature;
};
struct Cube {int x=0,y=0,z=0;};
struct CubePoint {double x=0,y=0,z=0;};
struct TexelPoint {double x=0,y=0;};
struct Normal {float x=0,y=0,z=1;}; // Original convention: Z is up.

class RetailRandom final {
public:
    explicit RetailRandom(std::uint32_t seed):state_(seed){}
    std::uint32_t Next() noexcept;
    std::uint32_t Below(std::uint32_t bound);
    std::uint32_t State() const noexcept{return state_;}
    std::uint64_t Calls() const noexcept{return calls_;}
    template<class T>void Shuffle(std::vector<T>& values);
private:
    std::uint32_t state_;std::uint64_t calls_=0;
};

struct Piece {
    std::uint32_t index=0,level=0,imageSize=0;
    std::array<Cell,100> cells;
    std::array<std::uint32_t,4> imageRows{};
    std::string name;
};
struct DecodedPiece {
    unsigned size=0;
    std::vector<std::uint16_t> height;
    std::vector<std::uint8_t> ids,heightBlend,idBlend;
};
struct PieceLibrary {
    // Compressed retail arrays stay owned; decode only the piece being stamped.
    std::vector<unsigned char> bytes;
    std::size_t rowsAt=0,rowCount=0,runs8At=0,runs8Count=0,runs16At=0,runs16Count=0;
    std::vector<Piece> pieces;
    unsigned materialRowCount=0;
    DecodedPiece Decode(unsigned index) const;
};
struct Placement {
    unsigned piece=0,orientation=0;
    int column=0,row=0;
};
struct PlacementResult {
    std::vector<Placement> placements;
    std::vector<Cell> claimedCells;
    std::uint64_t randomCalls=0;
    std::uint32_t finalRandomState=0;
};
struct Atlas {
    unsigned width=0,height=0;
    int originX=-32,originY=0;
    bool wrapX=true,wrapY=false;
    float heightOffset=0;
    // Color materials only. These are not the independent tile-selection IDs.
    std::vector<std::uint8_t> ids,known;
    std::vector<float> heights;
};
struct Material {
    unsigned row=0,projection=0;
    float scale=0;
};
struct MaterialTable {
    std::vector<Material> expanded;
    std::array<std::uint8_t,256> first{},count{};
};
struct ChunkSlots {
    unsigned count=0;
    std::array<std::uint8_t,8> materials{};
};
struct BlendWeights {
    std::array<float,8> values{};
    bool known=false;
};
struct TextureSample {
    std::array<float,3> diffuse{};
    std::array<float,4> specular{};
    float alpha=0,height=0;
};
struct MixedSample {
    // The original cache averages diffuse/specular squared, before lighting.
    std::array<float,4> diffuseSquared{},specularSquared{};
    float height=0,weightSum=0;
};

inline int FloorHalf(int value) noexcept;
inline Cube OffsetToCube(int column,int row) noexcept;
inline std::array<int,2> CubeToOffset(Cube point) noexcept;
inline CubePoint SourceTexelToCube(double px,double py) noexcept;
inline TexelPoint CubeToSourceTexel(CubePoint point) noexcept;
inline Cube RoundCube(CubePoint point);
inline CubePoint OrientPoint(CubePoint point,unsigned orientation);
inline Cell MakeCell(const PlotInput& plot);
inline PieceLibrary DecodeLibrary(std::vector<unsigned char> bytes,unsigned materialRowCount=41);
inline PlacementResult PlacePieces(const std::vector<Cell>& cells,unsigned width,unsigned height,
                                   const PieceLibrary& library,std::uint32_t seed);
inline Atlas BuildAtlas(const std::vector<Cell>& cells,unsigned gridWidth,unsigned gridHeight,
                        const PieceLibrary& library,const std::vector<Placement>& placements,
                        float heightOffset,std::size_t maxTexels=DefaultMaxAtlasTexels,
                        bool wrapX=true,bool wrapY=false);
inline MaterialTable ExpandMaterials(const std::vector<Material>& rows);
inline Normal SurfaceNormal(const Atlas& atlas,int x,int y,float heightScale);
inline unsigned ProjectionForNormal(Normal normal);
inline TexelPoint MaterialUv(const Material& material,float worldX,float worldY,float worldHeight);
inline ChunkSlots ChunkTop8(const Atlas& atlas,const MaterialTable& table,int x,int y,
                            unsigned width=64,unsigned height=64,float heightScale=1);
inline BlendWeights KernelWeights(const Atlas& atlas,const MaterialTable& table,
                                   const ChunkSlots& slots,int x,int y,Normal normal);
inline std::array<std::uint8_t,8> QuantizeWeights(const BlendWeights& weights);
inline MixedSample MixSquared(const BlendWeights& weights,const std::array<TextureSample,8>& samples);

namespace Detail {
inline void Require(bool value,const char* message){if(!value)throw std::invalid_argument(message);}
inline std::uint16_t U16(const std::vector<unsigned char>& b,std::size_t at){
    Require(at<=b.size() && b.size()-at>=2,"Truncated terrain u16");
    return static_cast<std::uint16_t>(b[at]|(static_cast<unsigned>(b[at+1])<<8));
}
inline std::uint32_t U32(const std::vector<unsigned char>& b,std::size_t at){
    Require(at<=b.size() && b.size()-at>=4,"Truncated terrain u32");
    return static_cast<std::uint32_t>(b[at])|(static_cast<std::uint32_t>(b[at+1])<<8)|
        (static_cast<std::uint32_t>(b[at+2])<<16)|(static_cast<std::uint32_t>(b[at+3])<<24);
}
inline std::size_t Area(unsigned w,unsigned h,std::size_t maxTexels=DefaultMaxAtlasTexels){
    Require(w && h && w<=16384 && h<=16384 && static_cast<std::uint64_t>(w)*h<=maxTexels,
            "Terrain dimensions exceed the bounded atlas");
    return static_cast<std::size_t>(w)*h;
}
inline void MapShape(const std::vector<Cell>& cells,unsigned w,unsigned h){
    Require(w && h && w<=256 && h<=256 && static_cast<std::uint64_t>(w)*h<=16384 &&
            cells.size()==static_cast<std::size_t>(w)*h,"Invalid bounded terrain cell grid");
}
inline void AtlasShape(const Atlas& atlas){
    const auto area=Area(atlas.width,atlas.height);
    Require(atlas.ids.size()==area && atlas.known.size()==area && atlas.heights.size()==area,
            "Incomplete terrain atlas");
    Require(std::isfinite(atlas.heightOffset)&&std::abs(atlas.heightOffset)<=2,"Invalid terrain atlas height offset");
}
inline int Wrap(int value,unsigned span) noexcept {
    const int s=static_cast<int>(span),result=value%s;return result<0?result+s:result;
}
inline std::size_t At(const Atlas& atlas,int x,int y) noexcept {
    return static_cast<std::size_t>(Wrap(y,atlas.height))*atlas.width+static_cast<unsigned>(Wrap(x,atlas.width));
}
inline float HeightAt(const Atlas& atlas,int x,int y,float fallback) noexcept {
    const auto at=At(atlas,x,y);return atlas.known[at]?atlas.heights[at]:fallback;
}
inline std::uint16_t HeightmapCode(const Atlas& atlas,std::size_t at){
    Require(at<atlas.heights.size()&&atlas.known[at]!=0,"Unavailable terrain heightmap code");
    const double raw=(static_cast<double>(atlas.heights[at])+atlas.heightOffset)*65535.0;
    Require(std::isfinite(raw),"Nonfinite known terrain heightmap code");
    // BuildAtlas already applied original truncation. This nearest-integer
    // conversion only decodes its centered float representation losslessly.
    return static_cast<std::uint16_t>(std::floor((std::max)(0.0,(std::min)(65535.0,raw))+.5));
}
inline unsigned MaterialAt(const MaterialTable& table,unsigned row,unsigned projection){
    Require(row<UnknownRow && table.count[row]>0 &&
            static_cast<unsigned>(table.first[row])+table.count[row]<=table.expanded.size(),
            "Terrain row is absent from its material table");
    return table.first[row]+(table.count[row]==3?projection:0);
}
inline unsigned TableSize(const MaterialTable& table){
    Require(!table.expanded.empty() && table.expanded.size()<=64,"Invalid expanded terrain material table");
    return static_cast<unsigned>(table.expanded.size());
}
}

inline std::uint32_t RetailRandom::Next() noexcept {
    state_=state_*214013u+2531011u;++calls_;return (state_>>16)&0x7fffu;
}
inline std::uint32_t RetailRandom::Below(std::uint32_t bound){
    Detail::Require(bound>0,"Terrain shuffle bound is zero");
    std::uint32_t mask=0x7fffu,value=Next()&mask;
    while(mask<bound && mask!=0xffffffffu){
        mask=(mask<<15)|0x7fffu;value=(value<<15)|(Next()&0x7fffu);
    }
    return value%bound;
}
template<class T>inline void RetailRandom::Shuffle(std::vector<T>& values){
    Detail::Require(values.size()<=0xffffffffu,"Terrain shuffle exceeds the original unsigned range");
    for(std::size_t next=1;next<values.size();++next){
        const auto selected=static_cast<std::size_t>(Below(static_cast<std::uint32_t>(next+1)));
        if(selected!=next)std::swap(values[next],values[selected]);
    }
}
inline int FloorHalf(int value) noexcept {return value/2-((value<0 && value%2)?1:0);}
inline Cube OffsetToCube(int column,int row) noexcept {
    const int x=column-FloorHalf(row);return {x,row,-x-row};
}
inline std::array<int,2> CubeToOffset(Cube point) noexcept {return {{point.x+FloorHalf(point.y),point.y}};}
inline CubePoint SourceTexelToCube(double px,double py) noexcept {
    const double y=py/64.0,x=px/64.0-py/128.0+0.5;return {x,y,-x-y};
}
inline TexelPoint CubeToSourceTexel(CubePoint point) noexcept {
    return {(point.x+point.y*0.5-0.5)*64.0,point.y*64.0};
}
inline Cube RoundCube(CubePoint point){
    Detail::Require(std::isfinite(point.x) && std::isfinite(point.y) && std::isfinite(point.z) &&
        std::abs(point.x)<1000000 && std::abs(point.y)<1000000 && std::abs(point.z)<1000000,
        "Invalid terrain cube coordinate");
    int x=static_cast<int>(std::round(point.x)),y=static_cast<int>(std::round(point.y)),z=static_cast<int>(std::round(point.z));
    const double dx=std::abs(static_cast<double>(x)-point.x),dy=std::abs(static_cast<double>(y)-point.y),
                 dz=std::abs(static_cast<double>(z)-point.z);
    if(dx>dy && dx>dz)x=-y-z;else if(dy>dz)y=-x-z;else z=-x-y;
    return {x,y,z};
}
inline CubePoint OrientPoint(CubePoint p,unsigned orientation){
    const auto transformed=OriginalTerrainCache::OrientPoint({p.x,p.y,p.z},orientation);
    return {transformed.x,transformed.y,transformed.z};
}
inline Cell MakeCell(const PlotInput& p){
    Cell cell;cell.owned=false;cell.revealed=p.exists && p.revealed;
    if(!p.exists){cell.mask=0x4000;cell.continent=0;return cell;}
    if(!p.revealed){cell.mask=0;cell.continent=0;return cell;}
    Detail::Require(p.continent>=0 && p.continent<=255,"Invalid original continent byte");
    cell.continent=static_cast<std::uint8_t>(p.continent);
    if(p.terrainType==5){cell.mask=0x2000;cell.continent=0;}
    else if(p.terrainType==6){cell.mask=0x4000;cell.continent=0;}
    else if(p.mountain)cell.mask=0x400;
    else{
        const unsigned flat=p.terrainType==0?0u:p.terrainType==2?2u:p.terrainType==3?3u:p.terrainType==4?4u:1u;
        cell.mask=1u<<(flat+(p.hills?5u:0u));
    }
    if(p.naturalWonder){
        static const std::pair<const char*,std::uint32_t> wonders[]={
            {"FEATURE_GEYSER",0x8000},{"FEATURE_CRATER",0x10000},{"FEATURE_POTOSI",0x20000},
            {"FEATURE_FUJI",0x40000},{"FEATURE_MESA",0x80000},{"FEATURE_REEF",0x100000},
            {"FEATURE_VOLCANO",0x200000},{"FEATURE_ULURU",0x400000},{"FEATURE_MT_SINAI",0x800000},
            {"FEATURE_MT_KAILASH",0x1000000},{"FEATURE_SRI_PADA",0x2000000},{"FEATURE_GIBRALTAR",0x4000000},
            {"FEATURE_KILIMANJARO",0x800},{"FEATURE_LAKE_VICTORIA",0x1000},{"FEATURE_SOLOMONS_MINES",0x4}};
        if(p.feature!="FEATURE_FOUNTAIN_YOUTH" && p.feature!="FEATURE_EL_DORADO"){
            cell.mask=0x40000;
            for(const auto& wonder:wonders)if(p.feature==wonder.first){cell.mask=wonder.second;break;}
        }
    }
    return cell;
}

namespace Detail {
inline void ImageRows(const PieceLibrary& library,const Piece& piece,unsigned channel,
                       std::vector<std::uint16_t>* wide,std::vector<std::uint8_t>* narrow,
                       std::size_t* used=nullptr){
    Require(channel<4 && (piece.imageSize==128 || piece.imageSize==512),"Invalid terrain image identity");
    const std::size_t pixels=static_cast<std::size_t>(piece.imageSize)*piece.imageSize;
    if(wide)wide->assign(pixels,0);if(narrow)narrow->assign(pixels,0);
    const auto start=static_cast<std::size_t>(piece.imageRows[channel]);
    Require(start<=library.rowCount && library.rowCount-start>=piece.imageSize,"Terrain image rows exceed the library");
    for(unsigned y=0;y<piece.imageSize;++y){
        std::size_t cursor=U32(library.bytes,library.rowsAt+(start+y)*4);unsigned total=0;
        while(total<piece.imageSize){
            unsigned count=0,value=0;
            if(channel==0){
                Require(cursor<=library.runs16Count && library.runs16Count-cursor>=2,"Truncated height RLE run");
                count=U16(library.bytes,library.runs16At+cursor*2);
                value=U16(library.bytes,library.runs16At+(cursor+1)*2);
            }else{
                Require(cursor<=library.runs8Count && library.runs8Count-cursor>=2,"Truncated byte RLE run");
                Require(library.runs8At+cursor+1<library.bytes.size(),"Byte RLE cursor escaped the library");
                count=library.bytes[library.runs8At+cursor];value=library.bytes[library.runs8At+cursor+1];
                if(channel==1)Require(value<library.materialRowCount,"Terrain piece ID is not a material row");
            }
            Require(count>0 && count<=piece.imageSize-total,"Terrain RLE run does not end at its row width");
            if(wide)std::fill_n(wide->begin()+static_cast<std::size_t>(y)*piece.imageSize+total,count,static_cast<std::uint16_t>(value));
            if(narrow)std::fill_n(narrow->begin()+static_cast<std::size_t>(y)*piece.imageSize+total,count,static_cast<std::uint8_t>(value));
            total+=count;cursor+=2;
        }
        if(used)*used=std::max(*used,cursor);
    }
}
}
inline DecodedPiece PieceLibrary::Decode(unsigned index) const {
    Detail::Require(index<pieces.size() && pieces[index].index==index,"Unknown compressed terrain piece");
    DecodedPiece decoded;decoded.size=pieces[index].imageSize;
    Detail::ImageRows(*this,pieces[index],0,&decoded.height,nullptr);
    Detail::ImageRows(*this,pieces[index],1,nullptr,&decoded.ids);
    Detail::ImageRows(*this,pieces[index],2,nullptr,&decoded.heightBlend);
    Detail::ImageRows(*this,pieces[index],3,nullptr,&decoded.idBlend);
    return decoded;
}
inline PieceLibrary DecodeLibrary(std::vector<unsigned char> bytes,unsigned materialRowCount){
    using namespace Detail;
    Require(bytes.size()>=20 && bytes.size()<=32*1024*1024 && materialRowCount>3 && materialRowCount<UnknownRow,
        "Invalid bounded terrain piece library or material-row count");
    Require(U32(bytes,0)==20,"Unknown terrain piece library version");
    PieceLibrary library;library.bytes=std::move(bytes);library.materialRowCount=materialRowCount;
    const unsigned strides[]={4,1,2,0x56c};std::array<std::size_t,4> starts{},counts{};std::size_t cursor=4;
    for(unsigned section=0;section<4;++section){
        const auto count=static_cast<std::size_t>(U32(library.bytes,cursor));cursor+=4;
        Require(cursor<=library.bytes.size() && count<=(library.bytes.size()-cursor)/strides[section],
            "Terrain counted array exceeds the input buffer");
        starts[section]=cursor;counts[section]=count;cursor+=count*strides[section];
    }
    Require(cursor==library.bytes.size() && counts[3]>0 && counts[3]<=299,"Terrain library trailing data or piece count differs");
    library.rowsAt=starts[0];library.rowCount=counts[0];library.runs8At=starts[1];library.runs8Count=counts[1];
    library.runs16At=starts[2];library.runs16Count=counts[2];library.pieces.reserve(counts[3]);
    std::uint32_t priorRow=0;std::size_t used8=0,used16=0;
    for(std::size_t i=0;i<counts[3];++i){
        const auto at=starts[3]+i*strides[3];Piece piece;
        piece.index=U32(library.bytes,at+0x3bc);piece.level=U32(library.bytes,at+0x3c8);
        Require(piece.index==i && piece.level>=1 && piece.level<=4 && U32(library.bytes,at+0x94)==10 &&
            U32(library.bytes,at+0x98)==10 && U32(library.bytes,at+0x3c0)==10 && U32(library.bytes,at+0x3c4)==10,
            "Terrain piece grid, index or level differs");
        const auto flags=U32(library.bytes,at+0x3d0);piece.imageSize=(flags&1)?128u:512u;
        unsigned owned=0;
        for(unsigned cell=0;cell<100;++cell){
            const auto offset=at+0x9c+cell*8;auto& c=piece.cells[cell];
            c.mask=U32(library.bytes,offset);c.continent=library.bytes[offset+4];c.owned=library.bytes[offset+5]!=0;
            Require(c.continent<=4 && library.bytes[offset+5]<=1,"Invalid terrain pattern cell");
            if(c.owned){Require(c.mask && !(c.mask&(c.mask-1)),"Owned terrain pattern is not a single bit");++owned;}
        }
        Require(owned>=1 && owned<=3,"Terrain piece must own one to three cells");
        for(unsigned channel=0;channel<4;++channel){
            const auto row=U32(library.bytes,at+0x3d4+channel*4);piece.imageRows[channel]=row;
            Require(row==priorRow && row<=library.rowCount && library.rowCount-row>=piece.imageSize,
                "Terrain image row tables are not contiguous");
            priorRow=row+piece.imageSize;
        }
        const std::size_t nameAt=at+0x3ea,nameEnd=at+0x42a;
        std::size_t stop=nameAt;while(stop<nameEnd && library.bytes[stop])++stop;
        Require(stop<nameEnd,"Unterminated terrain piece name");
        piece.name.assign(library.bytes.begin()+nameAt,library.bytes.begin()+stop);
        for(unsigned channel=0;channel<4;++channel)ImageRows(library,piece,channel,nullptr,nullptr,channel==0?&used16:&used8);
        library.pieces.push_back(std::move(piece));
    }
    Require(priorRow==library.rowCount && used8==library.runs8Count && used16==library.runs16Count,
        "Terrain row table or RLE stream has unconsumed entries");
    return library;
}

inline PlacementResult PlacePieces(const std::vector<Cell>& cells,unsigned width,unsigned height,
                                   const PieceLibrary& library,std::uint32_t seed){
    using namespace Detail;MapShape(cells,width,height);
    Require(!library.pieces.empty() && library.pieces.size()<=299,"Invalid terrain pattern count");
    struct PatternCell {Cube point;Cell cell;};
    struct Pattern {std::vector<PatternCell> significant;std::vector<Cube> owned;};
    std::vector<std::array<Pattern,4>> patterns(library.pieces.size());unsigned highest=0;
    for(std::size_t index=0;index<library.pieces.size();++index){
        const auto& piece=library.pieces[index];
        Require(piece.index==index && piece.level>=1 && piece.level<=4,"Invalid terrain pattern identity");
        highest=std::max(highest,piece.level);
        for(unsigned orientation=0;orientation<4;++orientation){
            auto& pattern=patterns[index][orientation];
            for(unsigned c=0;c<100;++c){
                const auto& cell=piece.cells[c];if(cell.mask==0xffffffffu && !cell.owned)continue;
                const auto source=OffsetToCube(static_cast<int>(c%10),static_cast<int>(c/10));
                const auto transformed=OrientPoint({static_cast<double>(source.x),static_cast<double>(source.y),static_cast<double>(source.z)},orientation);
                const Cube point{static_cast<int>(transformed.x),static_cast<int>(transformed.y),static_cast<int>(transformed.z)};
                pattern.significant.push_back({point,cell});if(cell.owned)pattern.owned.push_back(point);
            }
            Require(!pattern.owned.empty() && pattern.owned.size()<=3,"Terrain pattern has no bounded owner cells");
        }
    }
    PlacementResult result;result.claimedCells=cells;result.placements.reserve(cells.size());
    for(auto& cell:result.claimedCells)if(!cell.revealed){cell.mask=0;cell.continent=0;}
    RetailRandom random(seed);
    // Each pass constructs the index arrays once. Subsequent positions shuffle
    // their previous permutation in place (0x648a60/80, 0x648c33/49).
    for(int level=static_cast<int>(highest);level>=0;--level){
        std::vector<unsigned> order(library.pieces.size()),orientations{0,1,2,3};
        for(unsigned i=0;i<order.size();++i)order[i]=i;
        std::vector<Cube> positions;positions.reserve(static_cast<std::size_t>(width+4)*(height+4));
        for(int column=-2;column<static_cast<int>(width)+2;++column)
            for(int row=-2;row<static_cast<int>(height)+2;++row)positions.push_back(OffsetToCube(column,row));
        random.Shuffle(positions);
        for(const auto position:positions){
            random.Shuffle(order);random.Shuffle(orientations);
            const auto offset=CubeToOffset(position);
            for(const auto index:order){
                if(library.pieces[index].level!=static_cast<unsigned>(level))continue;
                for(const auto orientation:orientations){
                    const auto& pattern=patterns[index][orientation];bool accepted=true;unsigned covered=0;
                    const auto target=[&](Cube p)->Cell*{
                        p.x+=position.x;p.y+=position.y;p.z+=position.z;const auto cell=CubeToOffset(p);
                        if(cell[0]<0 || cell[1]<0 || cell[0]>=static_cast<int>(width) || cell[1]>=static_cast<int>(height))return nullptr;
                        return &result.claimedCells[static_cast<std::size_t>(cell[1])*width+static_cast<unsigned>(cell[0])];
                    };
                    // This early owner pass changes no random consumption or
                    // acceptance result, and avoids testing claimed patterns.
                    for(const auto p:pattern.owned){const auto* cell=target(p);if(!cell)continue;
                        ++covered;if(cell->owned){accepted=false;break;}}
                    if(!accepted || !covered)continue;
                    for(const auto& p:pattern.significant){
                        const auto* cell=target(p.point);if(!cell)continue;
                        if(p.cell.mask && cell->mask && (!(p.cell.mask&cell->mask) ||
                           (p.cell.continent && cell->continent && p.cell.continent!=cell->continent))){accepted=false;break;}
                    }
                    if(!accepted)continue;
                    Require(result.placements.size()<cells.size(),"Terrain placements exceed their claimed-cell bound");
                    result.placements.push_back({index,orientation,offset[0],offset[1]});
                    for(const auto p:pattern.owned){auto* cell=target(p);if(cell)cell->owned=true;}
                    // Retail continues through later orientations and pieces
                    // after claiming a match; there is no success break here.
                }
            }
        }
    }
    result.randomCalls=random.Calls();result.finalRandomState=random.State();return result;
}

inline Atlas BuildAtlas(const std::vector<Cell>& cells,unsigned gridWidth,unsigned gridHeight,
                        const PieceLibrary& library,const std::vector<Placement>& placements,
                        float heightOffset,std::size_t maxTexels,bool wrapX,bool wrapY){
    using namespace Detail;MapShape(cells,gridWidth,gridHeight);
    Require(std::isfinite(heightOffset) && std::abs(heightOffset)<=2,"Invalid terrain height reference offset");
    Require(maxTexels>0 && maxTexels<=DefaultMaxAtlasTexels && placements.size()<=cells.size(),
        "Terrain stamping exceeds its placement or memory bound");
    Atlas atlas;atlas.width=gridWidth*TexelsPerHex;atlas.height=gridHeight*TexelsPerHex;
    atlas.wrapX=wrapX;atlas.wrapY=wrapY;
    atlas.heightOffset=heightOffset;
    const auto area=Area(atlas.width,atlas.height,maxTexels);
    atlas.ids.assign(area,3);atlas.known.assign(area,0);atlas.heights.assign(area,0);
    std::vector<std::uint8_t> best(area,0);std::vector<float> weights(area,0.000001f);
    for(unsigned y=0;y<atlas.height;++y)for(unsigned x=0;x<atlas.width;++x){
        const auto cube=RoundCube(SourceTexelToCube(static_cast<double>(x)+atlas.originX,static_cast<double>(y)+atlas.originY));
        auto offset=CubeToOffset(cube);
        if(wrapX)offset[0]=Wrap(offset[0],gridWidth);if(wrapY)offset[1]=Wrap(offset[1],gridHeight);
        const auto at=static_cast<std::size_t>(y)*atlas.width+x;
        const bool inMap=offset[0]>=0 && offset[1]>=0 && offset[0]<static_cast<int>(gridWidth) && offset[1]<static_cast<int>(gridHeight);
        if(inMap && cells[static_cast<std::size_t>(offset[1])*gridWidth+static_cast<unsigned>(offset[0])].revealed)atlas.known[at]=1;
        else atlas.ids[at]=UnknownRow;
    }
    for(const auto& placement:placements){
        Require(placement.piece<library.pieces.size() && placement.orientation<4 &&
            placement.column>=-2 && placement.column<static_cast<int>(gridWidth)+2 &&
            placement.row>=-2 && placement.row<static_cast<int>(gridHeight)+2,"Invalid bounded terrain placement");
        const auto decoded=library.Decode(placement.piece);const auto position=OffsetToCube(placement.column,placement.row);
        // Candidate matrix order: orientation components, then placement.
        // Convert the transformed source origin once; the four directions are
        // exactly independent X/Y reversals in source-texel space.
        const auto a=OrientPoint(SourceTexelToCube(0,0),placement.orientation);
        const auto b=OrientPoint(SourceTexelToCube(1,1),placement.orientation);
        auto start=CubeToSourceTexel({a.x+position.x,a.y+position.y,a.z+position.z});
        const auto next=CubeToSourceTexel({b.x+position.x,b.y+position.y,b.z+position.z});
        const int stepX=static_cast<int>(std::round(next.x-start.x)),stepY=static_cast<int>(std::round(next.y-start.y));
        Require((stepX==1 || stepX==-1) && (stepY==1 || stepY==-1),"Terrain orientation is not an axis-reversed stamp");
        const int startX=static_cast<int>(std::round(start.x))-atlas.originX,
                  startY=static_cast<int>(std::round(start.y))-atlas.originY;
        for(unsigned sy=0;sy<decoded.size;++sy)for(unsigned sx=0;sx<decoded.size;++sx){
            const int x=Wrap(startX+stepX*static_cast<int>(sx),atlas.width),y=Wrap(startY+stepY*static_cast<int>(sy),atlas.height);
            const auto at=static_cast<std::size_t>(y)*atlas.width+static_cast<unsigned>(x);
            if(!atlas.known[at])continue;
            const auto sample=static_cast<std::size_t>(sy)*decoded.size+sx;
            if(decoded.idBlend[sample]>best[at]){best[at]=decoded.idBlend[sample];atlas.ids[at]=decoded.ids[sample];}
            const float weight=static_cast<float>(decoded.heightBlend[sample])*(1.0f/255.0f);
            atlas.heights[at]+=(static_cast<float>(decoded.height[sample])*(1.0f/65535.0f)-heightOffset)*weight;
            weights[at]+=weight;
        }
    }
    for(std::size_t at=0;at<area;++at){
        if(atlas.known[at]){
            const auto raw=OriginalTerrainCacheSampling::FinalizeStampedHeight(atlas.heights[at],weights[at],heightOffset);
            // Retain the existing centered-float public representation. No
            // second heightmap allocation is needed for the 16-bit codes.
            atlas.heights[at]=static_cast<float>(raw)*(1.0f/65535.0f)-heightOffset;
        }
        else{atlas.ids[at]=UnknownRow;atlas.heights[at]=0;}
    }
    return atlas;
}

inline MaterialTable ExpandMaterials(const std::vector<Material>& rows){
    using namespace Detail;
    Require(!rows.empty() && rows.size()<UnknownRow,"Invalid TerrainDef row count");
    MaterialTable table;table.first.fill(UnknownRow);table.count.fill(0);
    for(std::size_t row=0;row<rows.size();++row){
        const auto& value=rows[row];
        Require(value.row==row && value.projection<=1 && std::isfinite(value.scale) && value.scale>0 && value.scale<=1024,
            "TerrainDef row order, scale or projection differs");
        const unsigned count=value.projection?3u:1u;
        Require(table.expanded.size()+count<=64,"Expanded TerrainDef materials exceed 64");
        table.first[row]=static_cast<std::uint8_t>(table.expanded.size());table.count[row]=static_cast<std::uint8_t>(count);
        for(unsigned mode=0;mode<count;++mode)table.expanded.push_back({static_cast<unsigned>(row),mode,value.scale});
    }
    return table;
}
inline Normal SurfaceNormal(const Atlas& atlas,int x,int y,float heightScale){
    using namespace Detail;AtlasShape(atlas);
    Require(std::isfinite(heightScale)&&heightScale>=0&&heightScale<=1024&&
        std::abs(static_cast<double>(x))<1000000&&std::abs(static_cast<double>(y))<1000000,"Invalid terrain normal height scale or coordinate");
    namespace N=::ZeroSisPresentation::OriginalTerrainNormal;
    const auto window=N::CaptureKnownWindow([&](int dx,int dy){
            const int px=x+dx,py=y+dy;
            if((!atlas.wrapX&&(px<0||px>=static_cast<int>(atlas.width)))||
                (!atlas.wrapY&&(py<0||py>=static_cast<int>(atlas.height))))return false;
            return atlas.known[At(atlas,px,py)]!=0;
        },
        [&](int dx,int dy){return HeightmapCode(atlas,At(atlas,x+dx,y+dy));});
    const N::Metrics metric{1.0f/64.0f,OriginalTerrainCacheSampling::SourceMetricYDefault/64.0f,heightScale*(255.0f/65535.0f)};
    const auto normal=N::BaseNormal(window,metric);return {normal.x,normal.y,normal.z};
}
inline unsigned ProjectionForNormal(Normal normal){
    Detail::Require(std::isfinite(normal.x) && std::isfinite(normal.y) && std::isfinite(normal.z),"Nonfinite terrain projection normal");
    return normal.z>0.9f?0u:std::abs(normal.y)>std::abs(normal.x)?1u:2u;
}
inline TexelPoint MaterialUv(const Material& material,float worldX,float worldY,float worldHeight){
    Detail::Require(material.projection<=2 && std::isfinite(material.scale) && material.scale>0 &&
        std::isfinite(worldX) && std::isfinite(worldY) && std::isfinite(worldHeight),"Invalid terrain material UV input");
    const double scale=material.scale*(material.projection==0?0.33:0.66);
    if(material.projection==0)return {worldX*scale,worldY*scale};
    return {material.projection==1?worldX*scale:worldY*scale,worldHeight*scale};
}
inline ChunkSlots ChunkTop8(const Atlas& atlas,const MaterialTable& table,int x,int y,
                            unsigned width,unsigned height,float heightScale){
    using namespace Detail;AtlasShape(atlas);const unsigned count=TableSize(table);
    Require(width && height && width<=64 && height<=64 && std::abs(static_cast<double>(x))<1000000 &&
        std::abs(static_cast<double>(y))<1000000,"Invalid bounded terrain chunk");
    std::array<unsigned,64> histogram{};std::array<unsigned,64> order{};
    for(int py=y-2;py<y+static_cast<int>(height)+2;++py)for(int px=x-2;px<x+static_cast<int>(width)+2;++px){
        const auto at=At(atlas,px,py);if(!atlas.known[at])continue;
        const unsigned material=MaterialAt(table,atlas.ids[at],ProjectionForNormal(SurfaceNormal(atlas,px,py,heightScale)));
        ++histogram[material];
    }
    for(unsigned material=0;material<count;++material)order[material]=material;
    // Equal-frequency ordering was not established by the retail probe. Keep
    // material order as an explicit deterministic candidate tie policy.
    std::sort(order.begin(),order.begin()+count,[&](unsigned a,unsigned b){
        return histogram[a]!=histogram[b]?histogram[a]>histogram[b]:a<b;
    });
    ChunkSlots slots;
    for(unsigned index=0;index<count && slots.count<8;++index){
        if(!histogram[order[index]])break;
        slots.materials[slots.count++]=static_cast<std::uint8_t>(order[index]);
    }
    return slots;
}
inline BlendWeights KernelWeights(const Atlas& atlas,const MaterialTable& table,
                                   const ChunkSlots& slots,int x,int y,Normal normal){
    using namespace Detail;AtlasShape(atlas);const unsigned count=TableSize(table),projection=ProjectionForNormal(normal);
    Require(slots.count<=8 && std::abs(static_cast<double>(x))<1000000 &&
        std::abs(static_cast<double>(y))<1000000,"Invalid terrain blend slots or coordinates");
    std::array<bool,64> used{};
    for(unsigned i=0;i<slots.count;++i){Require(slots.materials[i]<count && !used[slots.materials[i]],"Duplicate or invalid terrain chunk material");used[slots.materials[i]]=true;}
    BlendWeights result;if(!atlas.known[At(atlas,x,y)] || !slots.count)return result;
    static const float taps[]={0.125f,0.6360560059547424f,1.0f,0.6360560059547424f,0.125f};
    std::array<float,64> full{};float total=0;
    for(int dy=-2;dy<=2;++dy)for(int dx=-2;dx<=2;++dx){
        const auto at=At(atlas,x+dx,y+dy);if(!atlas.known[at])continue;
        const auto material=MaterialAt(table,atlas.ids[at],projection);
        const float weight=taps[dy+2]*taps[dx+2];full[material]+=weight;total+=weight;
    }
    if(total<=0)return result;
    const float inverse=1.0f/total;float selected=0;result.known=true;
    for(unsigned i=0;i<slots.count;++i){result.values[i]=full[slots.materials[i]]*inverse;selected+=result.values[i];}
    // The retail writer extracts top-eight weights from the full normalised
    // table without renormalising them again (0x5cef10..0x5cf0fe).
    if(selected<0.001f)result.values[0]=1;
    return result;
}
inline std::array<std::uint8_t,8> QuantizeWeights(const BlendWeights& weights){
    std::array<std::uint8_t,8> result{};if(!weights.known)return result;
    for(unsigned i=0;i<8;++i){
        const float value=weights.values[i];Detail::Require(std::isfinite(value) && value>=0 && value<=1.000001f,"Invalid terrain material weight");
        result[i]=static_cast<std::uint8_t>(std::min(255.0f,value*255.0f));
    }
    return result;
}
inline MixedSample MixSquared(const BlendWeights& weights,const std::array<TextureSample,8>& samples){
    MixedSample result;if(!weights.known)return result;
    for(unsigned i=0;i<8;++i){
        const float input=weights.values[i];Detail::Require(std::isfinite(input) && input>=0 && input<=1.000001f,"Invalid terrain shader weight");
        if(input<=0.01f)continue;
        const auto& sample=samples[i];
        Detail::Require(std::isfinite(sample.alpha) && sample.alpha>=0 && sample.alpha<=1 &&
            std::isfinite(sample.height) && sample.height>=0 && sample.height<=1,"Invalid terrain texture sample");
        const float squared=sample.alpha*sample.alpha,fourth=squared*squared,weight=input*fourth*fourth;
        for(unsigned c=0;c<3;++c){
            Detail::Require(std::isfinite(sample.diffuse[c]) && sample.diffuse[c]>=0 && sample.diffuse[c]<=1 &&
                std::isfinite(sample.specular[c]) && sample.specular[c]>=0 && sample.specular[c]<=1,"Invalid terrain diffuse/specular sample");
            result.diffuseSquared[c]+=weight*sample.diffuse[c]*sample.diffuse[c];
            result.specularSquared[c]+=weight*sample.specular[c]*sample.specular[c];
        }
        Detail::Require(std::isfinite(sample.specular[3]) && sample.specular[3]>=0 && sample.specular[3]<=1,
            "Invalid terrain specular gloss sample");
        result.diffuseSquared[3]+=weight*squared;
        result.specularSquared[3]+=weight*sample.specular[3]*sample.specular[3];
        result.height+=weight*sample.height;result.weightSum+=weight;
    }
    if(result.weightSum>0){
        const float inverse=1.0f/result.weightSum;
        for(unsigned c=0;c<4;++c){result.diffuseSquared[c]*=inverse;result.specularSquared[c]*=inverse;}
        result.height*=inverse;
    }
    return result;
}

}} // namespace ZeroSisPresentation::OriginalTerrain
