#include "OriginalTerrainModel.h"
#include "original_terrain_golden.h"
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <iterator>

using namespace ZeroSisPresentation::OriginalTerrain;
namespace {
unsigned checks=0;
void Require(bool value,const char* what){++checks;if(!value)throw std::runtime_error(what);}
void Near(float actual,float expected,float tolerance=0.000003f){Require(std::abs(actual-expected)<=tolerance,"Terrain float reference differs");}
template<class F>void Reject(F body){bool rejected=false;try{body();}catch(const std::invalid_argument&){rejected=true;}Require(rejected,"Invalid terrain input was accepted");}
void Word(std::vector<unsigned char>& raw,std::size_t at,std::uint32_t value){
    for(unsigned b=0;b<4;++b)raw[at+b]=static_cast<unsigned char>(value>>(b*8));
}
void AppendWord(std::vector<unsigned char>& raw,std::uint32_t value){const auto at=raw.size();raw.resize(at+4);Word(raw,at,value);}
void AppendHalf(std::vector<unsigned char>& raw,std::uint16_t value){raw.push_back(static_cast<unsigned char>(value));raw.push_back(static_cast<unsigned char>(value>>8));}
struct FixturePiece {unsigned row=7,level=1;std::uint32_t mask=1;std::uint16_t height=32768;unsigned continent=0,hBlend=255,tBlend=128;};
std::vector<unsigned char> FixtureBytes(const std::vector<FixturePiece>& specs){
    std::vector<unsigned char> raw,rows,bytes,halves,records(specs.size()*0x56c,0);
    for(unsigned index=0;index<specs.size();++index){
        const auto& spec=specs[index];const std::size_t at=static_cast<std::size_t>(index)*0x56c;
        Word(records,at+0x94,10);Word(records,at+0x98,10);Word(records,at+0x3c0,10);Word(records,at+0x3c4,10);
        Word(records,at+0x3bc,index);Word(records,at+0x3c8,spec.level);Word(records,at+0x3d0,1);
        records[at+0x3ea]='P';
        for(unsigned cell=0;cell<100;++cell){Word(records,at+0x9c+cell*8,0xffffffffu);records[at+0x9c+cell*8+6]=0x4d;}
        Word(records,at+0x9c,spec.mask);records[at+0x9c+4]=static_cast<unsigned char>(spec.continent);records[at+0x9c+5]=1;
        for(unsigned channel=0;channel<4;++channel){
            Word(records,at+0x3d4+channel*4,static_cast<std::uint32_t>(rows.size()/4));
            for(unsigned row=0;row<128;++row){
                if(channel==0){AppendWord(rows,static_cast<std::uint32_t>(halves.size()/2));AppendHalf(halves,128);AppendHalf(halves,spec.height);}
                else{AppendWord(rows,static_cast<std::uint32_t>(bytes.size()));bytes.push_back(128);
                    bytes.push_back(static_cast<unsigned char>(channel==1?spec.row:channel==2?spec.hBlend:spec.tBlend));}
            }
        }
    }
    AppendWord(raw,20);AppendWord(raw,static_cast<std::uint32_t>(rows.size()/4));raw.insert(raw.end(),rows.begin(),rows.end());
    AppendWord(raw,static_cast<std::uint32_t>(bytes.size()));raw.insert(raw.end(),bytes.begin(),bytes.end());
    AppendWord(raw,static_cast<std::uint32_t>(halves.size()/2));raw.insert(raw.end(),halves.begin(),halves.end());
    AppendWord(raw,static_cast<std::uint32_t>(specs.size()));raw.insert(raw.end(),records.begin(),records.end());return raw;
}
std::vector<Cell> Cells(unsigned w,unsigned h){PlotInput p;p.terrainType=0;return std::vector<Cell>(static_cast<std::size_t>(w)*h,MakeCell(p));}
bool SamePlacements(const PlacementResult& a,const PlacementResult& b){
    if(a.placements.size()!=b.placements.size() || a.randomCalls!=b.randomCalls || a.finalRandomState!=b.finalRandomState)return false;
    for(std::size_t i=0;i<a.placements.size();++i){const auto& x=a.placements[i];const auto& y=b.placements[i];
        if(x.piece!=y.piece || x.orientation!=y.orientation || x.column!=y.column || x.row!=y.row)return false;}
    return true;
}
std::uint64_t Hash(const std::vector<unsigned>& values){std::uint64_t hash=14695981039346656037ull;
    for(const auto value:values)for(unsigned byte=0;byte<4;++byte){hash^=(value>>(8*byte))&255u;hash*=1099511628211ull;}return hash;}
void RandomAndCoordinates(){
    RetailRandom random(1);const unsigned sequence[]={41,18467,6334,26500,19169,15724,11478,29358,26962,24464};
    for(const auto value:sequence)Require(random.Next()==value,"MSVCR90 rand sequence differs");
    Require(random.Calls()==10,"Random call count differs");Reject([&]{random.Below(0);});
    RetailRandom narrow(1),wide(1),full(1);
    Require(narrow.Below(32767)==41 && narrow.Calls()==1,"15-bit shuffle range differs");
    Require(wide.Below(32768)==18467 && wide.Calls()==2,"Large shuffle bound did not extend rand bits");
    Require(full.Below(0xffffffffu)==GoldenFullRandom && full.Calls()==3,"32-bit shuffle bound differs");
    for(const unsigned count:{1u,4u,64u,33000u}){
        std::vector<unsigned> values(count);for(unsigned i=0;i<count;++i)values[i]=i;
        RetailRandom shuffle(12345);shuffle.Shuffle(values);
        const auto expected=count==1?GoldenHash1:count==4?GoldenHash4:count==64?GoldenHash64:GoldenHash33000;
        Require(Hash(values)==expected,"Original ascending shuffle differs from independent golden");
        std::sort(values.begin(),values.end());for(unsigned i=0;i<count;++i)Require(values[i]==i,"Shuffle lost or duplicated an element");
    }
    std::vector<unsigned> empty;RetailRandom zero(1);zero.Shuffle(empty);Require(zero.Calls()==0,"Empty shuffle consumes random values");
    for(int row=-9;row<=9;++row)for(int column=-9;column<=9;++column){
        const auto cube=OffsetToCube(column,row);const auto offset=CubeToOffset(cube);
        Require(cube.x+cube.y+cube.z==0 && offset[0]==column && offset[1]==row,"Negative-row offset/cube conversion differs");
    }
    Require(FloorHalf(-1)==-1 && FloorHalf(-3)==-2 && FloorHalf(3)==1,"Floor half uses truncation");
    const auto source=SourceTexelToCube(64,64);Near(static_cast<float>(source.x),1);Near(static_cast<float>(source.y),1);
    const auto inverse=CubeToSourceTexel(source);Near(static_cast<float>(inverse.x),64);Near(static_cast<float>(inverse.y),64);
    const CubePoint p{2,3,-5};
    const auto a=OrientPoint(p,1),b=OrientPoint(p,2),c=OrientPoint(p,3);
    // Original T*R(0)*mirror transforms the translation too; see phase10 cache_matrix_reference.json.
    Require(a.x==3 && a.y==0 && a.z==-3,"Mirror one differs");
    Require(b.x==-1 && b.y==3 && b.z==-2,"Mirror two differs");
    Require(c.x==0 && c.y==0 && c.z==0,"Half-turn differs");
    Reject([&]{OrientPoint(p,4);});Reject([]{RoundCube({std::numeric_limits<double>::infinity(),0,0});});
}
void MapRules(){
    for(int terrain=0;terrain<7;++terrain)for(unsigned hills=0;hills<2;++hills)for(unsigned mountain=0;mountain<2;++mountain){
        PlotInput plot;plot.terrainType=terrain;plot.continent=4;plot.hills=hills!=0;plot.mountain=mountain!=0;
        const auto cell=MakeCell(plot);const unsigned bit=terrain==5?13u:terrain==6?14u:mountain?10u:static_cast<unsigned>(terrain)+(hills?5u:0u);
        Require(cell.mask==(1u<<bit) && cell.continent==(terrain>=5?0u:4u),"Map terrain/mountain/hill priority differs");
    }
    const std::pair<const char*,unsigned> wonders[]={
        {"FEATURE_GEYSER",15},{"FEATURE_CRATER",16},{"FEATURE_POTOSI",17},{"FEATURE_FUJI",18},{"FEATURE_MESA",19},
        {"FEATURE_REEF",20},{"FEATURE_VOLCANO",21},{"FEATURE_ULURU",22},{"FEATURE_MT_SINAI",23},
        {"FEATURE_MT_KAILASH",24},{"FEATURE_SRI_PADA",25},{"FEATURE_GIBRALTAR",26},{"FEATURE_KILIMANJARO",11},{"FEATURE_LAKE_VICTORIA",12}};
    for(const auto& wonder:wonders){PlotInput p;p.terrainType=0;p.naturalWonder=true;p.feature=wonder.first;
        Require(MakeCell(p).mask==(1u<<wonder.second),"Natural-wonder bit differs");}
    for(const char* feature:{"FEATURE_FOREST","FEATURE_JUNGLE","FEATURE_MARSH","FEATURE_ICE","FEATURE_MOD_UNKNOWN"}){
        PlotInput p;p.terrainType=2;p.hills=true;p.feature=feature;Require(MakeCell(p).mask==0x80,"Ordinary feature changed terrain bit");
        p.naturalWonder=true;Require(MakeCell(p).mask==0x40000,"Unknown natural wonder did not use Fuji fallback");
    }
    for(const char* feature:{"FEATURE_FOUNTAIN_YOUTH","FEATURE_EL_DORADO"}){PlotInput p;p.terrainType=3;p.naturalWonder=true;p.feature=feature;
        Require(MakeCell(p).mask==8,"Natural wonder should preserve its base terrain");}
    PlotInput mines;mines.terrainType=6;mines.naturalWonder=true;mines.feature="FEATURE_SOLOMONS_MINES";
    Require(MakeCell(mines).mask==4 && MakeCell(mines).continent==0,"Solomon mines override differs");
    PlotInput hidden;hidden.revealed=false;hidden.continent=999;hidden.naturalWonder=true;hidden.feature="FEATURE_SECRET";
    Require(MakeCell(hidden).mask==0 && MakeCell(hidden).continent==0 && !MakeCell(hidden).revealed,"Hidden terrain entered placement input");
    hidden.exists=false;Require(MakeCell(hidden).mask==0x4000,"Missing plot is not ocean");
    PlotInput invalid;invalid.continent=256;Reject([&]{MakeCell(invalid);});
}
void LibraryAndPlacement(const std::vector<unsigned char>& real){
    auto library=DecodeLibrary(real);Require(library.pieces.size()==299,"Retail piece count differs");
    unsigned small=0,large=0;std::uint64_t pixels=0;
    for(unsigned i=0;i<library.pieces.size();++i){const auto decoded=library.Decode(i);const auto area=static_cast<std::size_t>(decoded.size)*decoded.size;
        Require(decoded.ids.size()==area && decoded.height.size()==area && decoded.heightBlend.size()==area && decoded.idBlend.size()==area,"Real RLE image shape differs");
        decoded.size==128?++small:++large;pixels+=area;
    }
    Require(small==148 && large==151 && pixels==42008576,"Real piece decoded pixel inventory differs");
    Require(library.pieces[0].name=="Amer_Grass_1_1.csv","Real piece name differs");
    auto fixture=FixtureBytes({FixturePiece{}});auto one=DecodeLibrary(fixture);const auto image=one.Decode(0);
    Require(image.ids[0]==7 && image.height[0]==32768 && image.heightBlend[0]==255 && image.idBlend[0]==128,"Fixture RLE channels are swapped");
    auto bad=fixture;Word(bad,0,21);Reject([&]{DecodeLibrary(bad);});
    bad=fixture;bad.pop_back();Reject([&]{DecodeLibrary(bad);});
    bad=fixture;bad.push_back(0);Reject([&]{DecodeLibrary(bad);});
    bad=fixture;Word(bad,4,0xffffffffu);Reject([&]{DecodeLibrary(bad);});
    bad=fixture;bad[one.runs8At]=0;Reject([&]{DecodeLibrary(bad);});
    bad=fixture;bad[one.runs8At]=129;Reject([&]{DecodeLibrary(bad);});
    bad=fixture;bad[one.runs8At+1]=41;Reject([&]{DecodeLibrary(bad);});
    bad=fixture;bad.insert(bad.begin()+one.runs8At+one.runs8Count,2,0);
    Word(bad,one.runs8At-4,static_cast<std::uint32_t>(one.runs8Count+2));Reject([&]{DecodeLibrary(bad);});
    bad=fixture;bad.insert(bad.begin()+one.runs16At+one.runs16Count*2,4,0);
    Word(bad,one.runs16At-4,static_cast<std::uint32_t>(one.runs16Count+2));Reject([&]{DecodeLibrary(bad);});
    Reject([&]{one.Decode(1);});Reject([&]{DecodeLibrary(fixture,3);});
    auto cells=Cells(2,2);const auto placed=PlacePieces(cells,2,2,one,17);
    Require(placed.placements.size()==4 && placed.randomCalls==286,"Greedy matching or final no-piece pass random count differs");
    Require(SamePlacements(placed,PlacePieces(cells,2,2,one,17)),"Fixed-seed placement is not deterministic");
    for(const auto& cell:placed.claimedCells)Require(cell.owned,"Single-owner fixture left unclaimed terrain");
    for(const auto& cell:cells)Require(!cell.owned,"Placement modified caller-owned cells");
    FixturePiece asia;asia.continent=2;const auto constrained=DecodeLibrary(FixtureBytes({asia}));
    for(auto& cell:cells)cell.continent=1;
    Require(PlacePieces(cells,2,2,constrained,17).placements.empty(),"Mismatching nonzero continents accepted");
    for(auto& cell:cells)cell.mask=0;
    Require(PlacePieces(cells,2,2,constrained,17).placements.size()==4,"Zero mask must bypass mask/continent mismatch");
    std::srand(12345);const int next=std::rand();std::srand(12345);PlacePieces(cells,2,2,one,17);
    Require(std::rand()==next,"Local terrain shuffle consumed process/global rand");
    auto secretA=Cells(2,2),secretB=secretA;secretA[1].revealed=secretB[1].revealed=false;
    secretA[1].mask=1;secretA[1].continent=1;secretB[1].mask=0x4000000;secretB[1].continent=4;
    const auto placementsA=PlacePieces(secretA,2,2,one,77),placementsB=PlacePieces(secretB,2,2,one,77);
    Require(SamePlacements(placementsA,placementsB),"Hidden terrain changed visible placement");
    const auto a=BuildAtlas(secretA,2,2,one,placementsA.placements,0,DefaultMaxAtlasTexels,true,true);
    const auto b=BuildAtlas(secretB,2,2,one,placementsB.placements,0,DefaultMaxAtlasTexels,true,true);
    Require(a.ids==b.ids && a.known==b.known && a.heights==b.heights,"Hidden terrain changed atlas output");
    Require(a.originX==-32 && a.originY==0 && a.width==128 && a.height==128,"Source atlas origin/64-texel geometry differs");
    bool hiddenFound=false;
    for(std::size_t i=0;i<a.ids.size();++i)if(!a.known[i]){hiddenFound=true;Require(a.ids[i]==UnknownRow && a.heights[i]==0,"Hidden atlas carries terrain/height");}
    Require(hiddenFound,"Hidden fixture did not exercise masked texels");
    FixturePiece second;second.row=8;second.height=65535;second.hBlend=128;
    auto two=DecodeLibrary(FixtureBytes({FixturePiece{},second}));
    auto all=Cells(2,2);std::vector<Placement> stamps={{0,0,0,0},{1,0,0,0}};
    const auto tied=BuildAtlas(all,2,2,two,stamps,0.25f,DefaultMaxAtlasTexels,true,true);
    const auto at=64u*128+64;
    Require(tied.ids[at]==7,"Equal T_BLEND must preserve earlier ID");
    // Independent float-accumulator / rational finalization golden: the
    // original heightmap stores truncate((sum/weight+.25)*65535) = 43718.
    Near(tied.heights[at],43718.0f/65535.0f-0.25f);
    second.tBlend=200;two=DecodeLibrary(FixtureBytes({FixturePiece{},second}));
    Require(BuildAtlas(all,2,2,two,stamps,0,DefaultMaxAtlasTexels,true,true).ids[at]==8,"Maximum T_BLEND did not choose material row");
    FixturePiece zero;zero.hBlend=0;zero.tBlend=0;one=DecodeLibrary(FixtureBytes({zero}));
    const auto defaults=BuildAtlas(all,2,2,one,{{0,0,0,0}},0,DefaultMaxAtlasTexels,true,true);
    Require(defaults.ids[at]==3 && defaults.heights[at]==0,"Zero blends changed default ID3/height sum");
    Reject([&]{BuildAtlas(all,2,2,one,{},0,1);});Reject([&]{PlacePieces(all,257,2,one,1);});
    Reject([&]{BuildAtlas(all,2,2,one,{{99,0,0,0}},0);});
    Reject([&]{BuildAtlas(all,2,2,one,{},std::numeric_limits<float>::quiet_NaN());});
}
Atlas FlatAtlas(unsigned size,unsigned row){Atlas atlas;atlas.width=atlas.height=size;const auto area=static_cast<std::size_t>(size)*size;
    atlas.ids.assign(area,static_cast<std::uint8_t>(row));atlas.known.assign(area,1);atlas.heights.assign(area,0);return atlas;}
void MaterialsAndBlend(){
    std::vector<Material> rows;for(unsigned i=0;i<12;++i)rows.push_back({i,0,0.14f});
    const auto table=ExpandMaterials(rows);Require(table.expanded.size()==12,"Flat material expansion differs");
    auto atlas=FlatAtlas(8,0);atlas.ids[4*8+4]=1;ChunkSlots slots;slots.count=2;slots.materials[0]=0;slots.materials[1]=1;
    auto weights=KernelWeights(atlas,table,slots,4,4,{});Near(weights.values[1],GoldenKernelCenter);
    Near(weights.values[0],1-GoldenKernelCenter);const auto quantized=QuantizeWeights(weights);
    Require(quantized[0]==214 && quantized[1]==40,"Weight bytes do not truncate independently");
    slots.count=1;weights=KernelWeights(atlas,table,slots,4,4,{});Near(weights.values[0],1-GoldenKernelCenter);
    slots.materials[0]=2;Near(KernelWeights(atlas,table,slots,4,4,{}).values[0],1);
    slots.count=2;slots.materials[0]=0;slots.materials[1]=1;
    for(unsigned y=0;y<8;++y)for(unsigned x=0;x<8;++x)if(x!=4 || y!=4){atlas.known[y*8+x]=0;atlas.ids[y*8+x]=254;atlas.heights[y*8+x]=std::numeric_limits<float>::quiet_NaN();}
    weights=KernelWeights(atlas,table,slots,4,4,{});Near(weights.values[0],0);Near(weights.values[1],1);
    const auto normal=SurfaceNormal(atlas,4,4,1);Near(normal.z,1);
    Require(!KernelWeights(atlas,table,slots,0,0,{}).known,"Unexplored vertex received neighbouring material");
    atlas=FlatAtlas(8,0);atlas.ids[4*8+7]=1;
    Require(KernelWeights(atlas,table,slots,0,4,{}).values[1]>0,"Kernel does not wrap a map edge");
    auto stripes=FlatAtlas(64,0);for(unsigned y=0;y<64;++y)for(unsigned x=0;x<64;++x)stripes.ids[y*64+x]=static_cast<std::uint8_t>((y+x/8)%12);
    const auto top=ChunkTop8(stripes,table,0,0);
    Require(top.count==8,"Chunk top-eight limit differs");
    for(unsigned i=0;i<8;++i)Require(top.materials[i]==GoldenChunkSlots[i],"Chunk border frequency/order differs");
    rows[1].projection=1;const auto projected=ExpandMaterials(rows);Require(projected.count[1]==3 && projected.first[2]==4,"Projection materials are not consecutive");
    atlas=FlatAtlas(8,1);slots.count=3;slots.materials[0]=1;slots.materials[1]=2;slots.materials[2]=3;
    Near(KernelWeights(atlas,projected,slots,4,4,{0,0,1}).values[0],1);
    Near(KernelWeights(atlas,projected,slots,4,4,{0,1,0}).values[1],1);
    Near(KernelWeights(atlas,projected,slots,4,4,{1,0,0}).values[2],1);
    Require(ProjectionForNormal({0,0,0.9f})==2 && ProjectionForNormal({0,0,0.90001f})==0,"Projection 0.9 boundary differs");
    for(unsigned mode=0;mode<3;++mode){const auto uv=MaterialUv({0,mode,0.14f},3,5,7);
        Near(static_cast<float>(uv.x),mode==0?0.1386f:mode==1?0.2772f:0.462f);
        Near(static_cast<float>(uv.y),mode==0?0.231f:0.6468f);}
    std::vector<Material> crowded;for(unsigned i=0;i<22;++i)crowded.push_back({i,1,1});Reject([&]{ExpandMaterials(crowded);});
    auto bad=rows;bad[1].row=99;Reject([&]{ExpandMaterials(bad);});bad=rows;bad[1].scale=0;Reject([&]{ExpandMaterials(bad);});
    slots.count=2;slots.materials[0]=slots.materials[1]=1;Reject([&]{KernelWeights(atlas,projected,slots,4,4,{});});
    BlendWeights blend;blend.known=true;blend.values[0]=blend.values[1]=0.5f;
    std::array<TextureSample,8> samples{};samples[0].diffuse={{0.25f,0,0}};samples[0].alpha=1;samples[0].height=0.2f;samples[0].specular={{0.5f,0,0,0.75f}};
    samples[1].diffuse={{0,0,0.75f}};samples[1].alpha=0.5f;samples[1].height=0.8f;samples[1].specular={{0,0,0.25f,0.25f}};
    const auto mixed=MixSquared(blend,samples);const float sum=0.5f+0.5f/256;
    Near(mixed.weightSum,sum);Near(mixed.diffuseSquared[0],0.5f*0.25f*0.25f/sum);
    Near(mixed.diffuseSquared[2],0.5f/256*0.75f*0.75f/sum);Near(mixed.diffuseSquared[3],(0.5f+0.5f/256*0.25f)/sum);
    Near(mixed.specularSquared[3],(0.5f*0.75f*0.75f+0.5f/256*0.25f*0.25f)/sum);
    Near(mixed.height,(0.5f*0.2f+0.5f/256*0.8f)/sum);
    blend.values[0]=0.01f;blend.values[1]=0;Near(MixSquared(blend,samples).weightSum,0);
    blend.known=false;samples[0].alpha=std::numeric_limits<float>::quiet_NaN();Near(MixSquared(blend,samples).weightSum,0);
}
}
int main(int argc,char** argv){
    try{
        Require(argc==2,"Expected a read-only original piece library path");
        std::ifstream file(argv[1],std::ios::binary);Require(file.good(),"Cannot read original piece library fixture");
        const std::vector<unsigned char> real((std::istreambuf_iterator<char>(file)),std::istreambuf_iterator<char>());
        Require(real.size()==27595584,"Original library byte count differs");
        RandomAndCoordinates();MapRules();LibraryAndPlacement(real);MaterialsAndBlend();
        std::printf("PASS_ORIGINAL_TERRAIN_MODEL checks=%u\n",checks);return 0;
    }catch(const std::exception& ex){std::fprintf(stderr,"FAIL: %s\n",ex.what());return 1;}
}
