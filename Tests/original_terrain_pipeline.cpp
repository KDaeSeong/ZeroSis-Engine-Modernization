#define NOMINMAX
#define PSAPI_VERSION 2
#include <Windows.h>
#include <Psapi.h>
#include "OriginalTerrainPackage.h"
#include "OriginalTerrainBinding.h"
#include "OriginalTerrainGeometry.h"
#include <chrono>
#include <cstdio>
#include <fstream>

using namespace ZeroSisPresentation;
using namespace ZeroSisPresentation::OriginalTerrain;
namespace {
unsigned checks=0;
constexpr std::size_t MemoryLimit=384ull*1024*1024;
std::size_t largestWorkingSet=0,largestCommit=0;
void Require(bool value,const char* text){++checks;if(!value)throw std::runtime_error(text);}
void MemoryCheck(){
    PROCESS_MEMORY_COUNTERS_EX counters{};counters.cb=sizeof(counters);
    Require(K32GetProcessMemoryInfo(GetCurrentProcess(),reinterpret_cast<PROCESS_MEMORY_COUNTERS*>(&counters),sizeof(counters))!=0,
        "Cannot inspect the controlled console's own memory");
    largestWorkingSet=std::max(largestWorkingSet,static_cast<std::size_t>(counters.PeakWorkingSetSize));
    largestCommit=std::max(largestCommit,static_cast<std::size_t>(counters.PeakPagefileUsage));
    Require(largestWorkingSet<=MemoryLimit && largestCommit<=MemoryLimit,"Controlled terrain pipeline exceeded384MiB");
}
std::vector<unsigned char> ReadPackage(const char* path){
    std::ifstream input(path,std::ios::binary|std::ios::ate);Require(input.good(),"Cannot read the sealed package");
    const auto length=input.tellg();Require(length>=24 && length<=128*1024*1024,"Package exceeds its fixture bound");
    std::vector<unsigned char> raw(static_cast<std::size_t>(length));input.seekg(0);
    input.read(reinterpret_cast<char*>(raw.data()),length);Require(input.good(),"Truncated package read");return raw;
}
WorldView Fixture(){
    WorldView view{};view.gridWidth=40;view.gridHeight=24;view.wrapX=true;view.wrapY=false;
    view.mapRandomSeed=1234567;view.cameraX=20;view.cameraY=11;view.tileWidth=56;view.plots.reserve(960);
    static const char* terrains[]={"TERRAIN_GRASS","TERRAIN_PLAINS","TERRAIN_DESERT","TERRAIN_TUNDRA","TERRAIN_SNOW","TERRAIN_COAST","TERRAIN_OCEAN"};
    for(int y=0;y<24;++y)for(int x=0;x<40;++x){
        WorldViewPlot p{};p.index=y*40+x;p.x=x;p.y=y;p.terrainId=(x+3*y)%7;p.continent=1+(x+y)%4;
        p.revealed=x>=19 && x<=21 && y>=10 && y<=12;p.visible=p.revealed;
        p.terrain=terrains[p.terrainId];p.water=p.terrainId>=5;p.hills=(x+y)%3==0;p.mountain=(x+y)%11==0;
        p.naturalWonder=(x+2*y)%13==0;p.feature=p.naturalWonder?"FEATURE_FUJI":"FEATURE_FOREST";
        if(p.revealed){
            const int slot=(y-10)*3+x-19;p.terrainId=slot%7;p.terrain=terrains[p.terrainId];p.water=p.terrainId>=5;
            p.hills=slot==3 || slot==4;p.mountain=slot==7;p.naturalWonder=slot==8;
            p.feature=p.naturalWonder?"FEATURE_GEYSER":"FEATURE_FOREST";p.continent=2;
        }
        view.plots.push_back(std::move(p));
    }
    return view;
}
bool SamePlacements(const PlacementResult& a,const PlacementResult& b){
    if(a.randomCalls!=b.randomCalls || a.finalRandomState!=b.finalRandomState || a.placements.size()!=b.placements.size())return false;
    for(std::size_t i=0;i<a.placements.size();++i){const auto& x=a.placements[i];const auto& y=b.placements[i];
        if(x.piece!=y.piece || x.orientation!=y.orientation || x.column!=y.column || x.row!=y.row)return false;}
    return SameTerrainCells(a.claimedCells,b.claimedCells);
}
void SameAtlas(const Atlas& a,const Atlas& b){
    Require(a.width==b.width && a.height==b.height && a.originX==b.originX && a.originY==b.originY &&
        a.wrapX==b.wrapX && a.wrapY==b.wrapY,"Pipeline atlas geometry changed");
    Require(a.ids==b.ids && a.known==b.known && a.heights==b.heights,"Hidden data or visibility changed the atlas");
}
struct Inventory {std::size_t known=0,unknown=0;std::array<bool,256> rows{};};
Inventory Inspect(const Atlas& atlas,unsigned rowCount){
    Require(atlas.width==2560 && atlas.height==1536,"40x24 map is not64texels per hex");
    const std::size_t area=2560u*1536u;
    Require(atlas.ids.size()==area && atlas.known.size()==area && atlas.heights.size()==area,"Global atlas vector extent differs");
    Inventory inventory;
    for(std::size_t i=0;i<area;++i){
        Require(std::isfinite(atlas.heights[i]),"Pipeline produced a nonfinite height");
        if(atlas.known[i]){++inventory.known;Require(atlas.ids[i]<rowCount,"Known texel is not a TerrainDef row");inventory.rows[atlas.ids[i]]=true;}
        else{++inventory.unknown;Require(atlas.ids[i]==UnknownRow && atlas.heights[i]==0,"Hidden material or height escaped into the atlas");}
    }
    Require(inventory.known>30000 && inventory.known<45000 && inventory.unknown>3800000,
        "Pipeline known mask does not describe the small revealed region");
    return inventory;
}
}
int main(int argc,char** argv){
    try{
        const auto start=std::chrono::steady_clock::now();Require(argc==2,"Expected a sealed package path");
        auto package=DecodePackage(ReadPackage(argv[1]),PackageSha256);MemoryCheck();
        Require(package.rows.size()==41 && package.textures.size()==72 && package.libraryBytes==27595584,"Real package inventory differs");
        std::vector<unsigned char> libraryBytes(package.bytes.begin()+package.libraryOffset,
            package.bytes.begin()+package.libraryOffset+package.libraryBytes);
        auto library=DecodeLibrary(std::move(libraryBytes),static_cast<unsigned>(package.rows.size()));
        Require(library.pieces.size()==299,"Pipeline did not decode the real299pieces");MemoryCheck();
        auto view=Fixture();const auto cells=CaptureTerrainCells(view);
        Require(cells.size()==960,"Capture changed the40x24cell count");
        std::size_t revealed=0;for(const auto& cell:cells)if(cell.revealed)++revealed;else Require(cell.mask==0 && cell.continent==0,"Hidden cell entered matching input");
        Require(revealed==9,"Fixture must reveal exactly3x3plots");
        const auto placements=PlacePieces(cells,40,24,library,view.mapRandomSeed);
        Require(!placements.placements.empty() && placements.placements.size()<=960,"Real greedy placement produced invalid coverage");
        const auto atlas=BuildAtlas(cells,40,24,library,placements.placements,HeightOffsetCandidate,
            DefaultMaxAtlasTexels,view.wrapX,view.wrapY);
        const auto inventory=Inspect(atlas,41);MemoryCheck();
        {
            auto hidden=view;std::size_t changes=0;
            for(auto& p:hidden.plots)if(!p.revealed){
                p.terrainId=(p.terrainId+4)%7;p.terrain="TERRAIN_SECRET_MODDED";p.continent=(p.continent+2)%5;
                p.hills=!p.hills;p.mountain=!p.mountain;p.water=!p.water;
                p.naturalWonder=!p.naturalWonder;p.feature="FEATURE_GIBRALTAR";++changes;
            }
            Require(changes==951,"Hidden mutation fixture differs");
            const auto hiddenCells=CaptureTerrainCells(hidden);Require(SameTerrainCells(cells,hiddenCells),"Hidden DTO properties changed matching cells");
            const auto hiddenPlacements=PlacePieces(hiddenCells,40,24,library,hidden.mapRandomSeed);
            Require(SamePlacements(placements,hiddenPlacements),"Hidden DTO properties changed real placements or random consumption");
            const auto hiddenAtlas=BuildAtlas(hiddenCells,40,24,library,hiddenPlacements.placements,HeightOffsetCandidate,
                DefaultMaxAtlasTexels,hidden.wrapX,hidden.wrapY);
            SameAtlas(atlas,hiddenAtlas);MemoryCheck();
        }
        {
            auto visibility=view;for(auto& p:visibility.plots)if(p.revealed)p.visible=false;
            const auto visibleCells=CaptureTerrainCells(visibility);Require(SameTerrainCells(cells,visibleCells),"Visible flag changed revealed terrain cells");
            const auto visiblePlacements=PlacePieces(visibleCells,40,24,library,visibility.mapRandomSeed);
            Require(SamePlacements(placements,visiblePlacements),"Visible flag changed placements");
            const auto visibleAtlas=BuildAtlas(visibleCells,40,24,library,visiblePlacements.placements,HeightOffsetCandidate,
                DefaultMaxAtlasTexels,visibility.wrapX,visibility.wrapY);
            SameAtlas(atlas,visibleAtlas);MemoryCheck();
        }
        const auto elapsed=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-start).count();
        Require(elapsed<=85000,"Controlled terrain pipeline exceeded85seconds");
        unsigned materialRows=0;for(const bool row:inventory.rows)if(row)++materialRows;
        const auto ids=Sha256Hex(atlas.ids.data(),atlas.ids.size()),known=Sha256Hex(atlas.known.data(),atlas.known.size()),
            heights=Sha256Hex(reinterpret_cast<const unsigned char*>(atlas.heights.data()),atlas.heights.size()*sizeof(float));
        MemoryCheck();
        std::printf("PASS_ORIGINAL_TERRAIN_PIPELINE checks=%u width=%u height=%u revealed=9 placements=%zu known=%zu unknown=%zu rows=%u elapsed_ms=%lld peak_working_set=%zu peak_commit=%zu memory_limit=%zu ids_sha=%s known_sha=%s heights_sha=%s\n",
            checks,atlas.width,atlas.height,placements.placements.size(),inventory.known,inventory.unknown,materialRows,
            static_cast<long long>(elapsed),largestWorkingSet,largestCommit,MemoryLimit,ids.c_str(),known.c_str(),heights.c_str());return 0;
    }catch(const std::exception& ex){std::fprintf(stderr,"FAIL: %s\n",ex.what());return 1;}
}
