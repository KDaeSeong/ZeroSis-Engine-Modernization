#include "OriginalFogModel.h"
#include "original_fog_golden.h"
#include <cstdio>
#include <cstdlib>

using namespace ZeroSisPresentation::OriginalFog;
namespace {
unsigned checks=0;
const char* section="startup";
void Require(bool value,const char* reason){++checks;if(!value)throw std::runtime_error(reason);}
void Near(double a,double b,double tolerance=0.000001){
    const bool same=std::isfinite(a)&&std::isfinite(b)&&std::abs(a-b)<=tolerance;
    if(!same)std::fprintf(stderr,"Section=%s check=%u actual=%.17g expected=%.17g tolerance=%.17g\n",section,checks,a,b,tolerance);
    Require(same,"Fog numeric reference differs");
}
template<class F>void Reject(F body){bool rejected=false;try{body();}catch(const std::invalid_argument&){rejected=true;}Require(rejected,"Invalid fog input was accepted");}
void ColourNear(const Colour& a,const Colour& b,double tolerance=0.000001){Near(a.r,b.r,tolerance);Near(a.g,b.g,tolerance);Near(a.b,b.b,tolerance);Near(a.a,b.a,tolerance);}
Grid MakeGrid(int width,int height,Cell state,bool wrapX=true,bool wrapY=true){
    Grid result;result.width=width;result.height=height;result.wrapX=wrapX;result.wrapY=wrapY;
    result.cells.assign(static_cast<std::size_t>(width)*height,state);return result;
}
std::vector<Colour> Identity(unsigned width,unsigned height,unsigned depth){
    std::vector<Colour> result;
    for(unsigned z=0;z<depth;++z)for(unsigned y=0;y<height;++y)for(unsigned x=0;x<width;++x)
        result.push_back({static_cast<float>((x+0.5)/width),static_cast<float>((y+0.5)/height),static_cast<float>((z+0.5)/depth),1});
    return result;
}
void RasterAndMasks(){
    for(const Cell state:{Cell{false,false},Cell{true,false},Cell{true,true}}){
        const auto texture=BuildMask(MakeGrid(6,4,state));Require(texture.width==96&&texture.height==64,"Fog raster size differs");
        for(const auto& mask:texture.texels){Near(mask.r,state.revealed?1:0);Near(mask.g,state.revealed?0:1);Near(mask.b,state.visible?1:0);}
        for(int y=-3;y<=10;++y)for(int x=-3;x<=10;++x){
            const auto value=SampleMask(texture,x/7.0,y/7.0,true,true);
            Near(value.r,state.revealed?1:0);Near(value.g,state.revealed?0:1);Near(value.b,state.visible?1:0);
        }
    }
    auto grid=MakeGrid(8,4,{true,false});grid.cells[2*8+3].visible=true;
    for(int row=0;row<grid.height;++row)for(int col=0;col<grid.width;++col)
        if(col>=4)grid.cells[static_cast<std::size_t>(row)*grid.width+col]={false,false};
    const auto first=BuildMask(grid),second=BuildMask(grid);
    Require(first.texels.size()==second.texels.size(),"Repeated fog raster size differs");
    unsigned fractional=0;double totalR=0,totalB=0;
    for(std::size_t i=0;i<first.texels.size();++i){const auto& a=first.texels[i];const auto& b=second.texels[i];
        Near(a.r,b.r,0);Near(a.g,b.g,0);Near(a.b,b.b,0);Require(a.b<=a.r,"Fog visibility exceeds exploration");
        Near(a.r+a.g,1,0);if(a.r>0&&a.r<1)++fractional;totalR+=a.r;totalB+=a.b;
    }
    Require(fractional>0,"Fog tile boundary was not smoothed");Near(totalR,GoldenMaskTotalR,0.000001);Near(totalB,GoldenMaskTotalB,0.000001);
    for(const auto& expected:GoldenMaskTexels){const auto& actual=first.texels[static_cast<std::size_t>(expected.y)*first.width+expected.x];
        Near(actual.r,expected.r,0);Near(actual.g,1-expected.r,0);Near(actual.b,expected.b,0);
    }
    for(int index=-3;index<=24;++index){const double v=index/19.0;
        const auto a=SampleMask(first,0,v,true,true),b=SampleMask(first,1,v,true,true);
        Near(a.r,b.r,0);Near(a.b,b.b,0);
        const auto c=SampleMask(first,-0.25,v,true,true),d=SampleMask(first,0.75,v,true,true);
        Near(c.r,d.r,0);Near(c.b,d.b,0);
    }
    const auto uv=MaskUv(4,-2*RowSpacing,8,4);Near(uv[0],0.5,0);Near(uv[1],0.5,0);
    const auto lower=SampleMask(first,-1,-1,false,false),corner=SampleMask(first,0,0,false,false);
    Near(lower.r,corner.r,0);Near(lower.b,corner.b,0);
    for(int row=0;row<grid.height;++row)for(int col=0;col<grid.width;++col){
        const auto center=MaskUv(col+(row%2)*0.5,-row*RowSpacing,grid.width,grid.height);
        const auto mask=SampleMask(first,center[0],center[1],true,true);
        const auto& cell=grid.cells[static_cast<std::size_t>(row)*grid.width+col];
        Near(mask.r,cell.revealed?1:0);Near(mask.b,cell.visible?1:0);
    }
}
void SamplingAndLuts(){
    const Colour pixels[4]={{0,0,0,0},{1,0,0,0.25f},{0,1,0,0.5f},{1,1,1,1}};
    ImageView image{pixels,2,2,4};ColourNear(Sample2D(image,0.25,0.25),pixels[0],0);
    ColourNear(Sample2D(image,0.75,0.75),pixels[3],0);
    ColourNear(Sample2D(image,0.5,0.5),{0.5f,0.5f,0.25f,0.4375f},0);
    ColourNear(Sample2D(image,-1,-1),pixels[0],0);ColourNear(Sample2D(image,2,2),pixels[3],0);
    ColourNear(Sample2D(image,0,0,AddressMode::Wrap),Sample2D(image,1,1,AddressMode::Wrap),0);
    ColourNear(Sample2D(image,-0.25,-0.25,AddressMode::Wrap),pixels[3],0);
    for(const unsigned dimension:{2u,4u,32u}){
        const auto values=Identity(dimension,dimension,dimension);
        Lut3DView lut{values.data(),dimension,dimension,dimension,values.size()};
        const float minimum=0.5f/dimension,maximum=1-minimum;
        for(int z=0;z<=8;++z)for(int y=0;y<=8;++y)for(int x=0;x<=8;++x){
            const Colour coordinate{static_cast<float>(x/8.0),static_cast<float>(y/8.0),static_cast<float>(z/8.0),1};
            const auto colour=SampleLut(lut,coordinate);
            Near(colour.r,(std::max)(minimum,(std::min)(maximum,coordinate.r)));
            Near(colour.g,(std::max)(minimum,(std::min)(maximum,coordinate.g)));
            Near(colour.b,(std::max)(minimum,(std::min)(maximum,coordinate.b)));Near(colour.a,1,0);
        }
    }
    const auto values=Identity(2,3,4);Lut3DView nonCube{values.data(),2,3,4,values.size()};
    ColourNear(SampleLut(nonCube,{0.5f,0.5f,0.5f,1}),{0.5f,0.5f,0.5f,1});
    const Colour one{0.2f,0.3f,0.4f,1};Lut3DView constant{&one,1,1,1,1};
    ColourNear(SampleLut(constant,{-1,0.5f,2,1}),one,0);
}
void PrivacyAndColourOrder(){
    const Colour terrain{0.8f,0.5f,0.1f,0.3f},replacement{0.2f,0.1f,0.4f,0.4f},lutColour{0.1f,0.6f,0.9f,0.5f};
    ColourNear(BlendFow(terrain,replacement,{1,0,1},lutColour,true),{0.8f,0.5f,0.1f,1});
    ColourNear(BlendFow(terrain,replacement,{1,0,0},lutColour,true),{0.1f,0.6f,0.9f,1});
    ColourNear(BlendFow(terrain,replacement,{0.5f,0.5f,0.25f},lutColour,true),{0.35f,0.4125f,0.49375f,1});
    const float poison=std::numeric_limits<float>::quiet_NaN();const Colour hidden{poison,poison,poison,poison};
    const Lut3DView absent;
    for(int r=0;r<=20;++r)for(int b=0;b<=r;++b){
        const Mask mask{r/20.0f,1-r/20.0f,b/20.0f};
        ColourNear(BlendFow(hidden,replacement,mask,hidden,false),{0.2f,0.1f,0.4f,1},0);
        ColourNear(ApplyFow(hidden,replacement,mask,absent,false),{0.2f,0.1f,0.4f,1},0);
    }
    ColourNear(BlendFow(hidden,replacement,{0,1,0},hidden,true),{0.2f,0.1f,0.4f,1},0);
    ColourNear(ApplyFow(terrain,replacement,{1,0,1},absent,true),{0.8f,0.5f,0.1f,1});
    const auto values=Identity(32,32,32);Lut3DView lut{values.data(),32,32,32,values.size()};
    const Mask partial{0.4f,0.6f,0.2f};const auto base=MixReplacement(terrain,replacement,partial,true);
    ColourNear(ApplyFow(terrain,replacement,partial,lut,true),BlendFow(terrain,replacement,partial,SampleLut(lut,base),true),0);
    Require(sizeof(Cell)==2,"Fog cell gained non-state inputs");
}
void DistanceAndFlow(){
    for(const auto& golden:GoldenDistances){
        const double actual=DistanceFogFactor({golden.x,golden.y,golden.z},golden.k,golden.density,golden.ramp);
        Near(actual,golden.expected,0.00000000001);
    }
    for(double z:{-1.0,-0.01,-1e-12,0.0,1e-12,0.01,1.0}){
        const double factor=DistanceFogFactor({10,20,z},0.01,0.1,0.4);
        Require(factor>=0&&factor<=0.4,"Distance fog left its ramp bound");
        if(std::abs(z)<1e-10)Near(factor,DistanceFogFactor({10,20,0},0.01,0.1,0.4),1e-12);
    }
    Near(DistanceFogFactor({1,2,3},0,3,1),0,0);Near(DistanceFogFactor({1,2,3},3,0,1),0,0);
    Near(DistanceFogFactor({1,2,3},3,3,0),0,0);Near(DistanceFogFactor({0,0,0},1,1,1),0,0);
    Near(DistanceFogFactor({10,10,100000},1,1,0.7),0.7,0);
    const auto uv=DistanceRampUv(-1,0.125);Near(uv[0],0,0);Near(uv[1],0.125,0);
    const auto uv2=DistanceRampUv(1,0.625);Near(uv2[0],1,0);Near(uv2[1],0.625,0);
    const Colour base{0.1f,0.2f,0.3f,0.2f},fog{146.0f/255,182.0f/255,243.0f/255,0.5f};
    ColourNear(ApplyDistanceFog(base,fog,0),{0.1f,0.2f,0.3f,1},0);
    ColourNear(ApplyDistanceFog(base,fog,1),{fog.r,fog.g,fog.b,1});
    // Only the pure CPU test owns this CRT RNG; model calls must consume none.
    std::srand(713);const int expected=std::rand();std::srand(713);
    for(unsigned layer=0;layer<3;++layer){
        for(int time=-100;time<=100;++time){const auto a=FlowUv(-3.5,8.2,time,layer),b=FlowUv(-3.5,8.2,time,layer);
            Near(a[0],b[0],0);Near(a[1],b[1],0);Require(a[0]>=0&&a[0]<1&&a[1]>=0&&a[1]<1,"Cloud UV left repeat bounds");
        }
        const auto start=FlowUv(0,0,0,layer),later=FlowUv(0,0,1,layer);
        Require(start[0]!=later[0]&&start[1]!=later[1],"Candidate cloud flow did not move");
    }
    Require(std::rand()==expected,"Fog model consumed a random value");
}
void InvalidInputs(){
    const double infinity=std::numeric_limits<double>::infinity();const float nan=std::numeric_limits<float>::quiet_NaN();
    Grid zero;Reject([&]{BuildMask(zero);});auto grid=MakeGrid(2,2,{true,true});
    grid.cells.pop_back();Reject([&]{BuildMask(grid);});grid=MakeGrid(2,2,{false,true});Reject([&]{BuildMask(grid);});
    grid=MakeGrid(2,3,{true,true});Reject([&]{BuildMask(grid);});grid=MakeGrid(2,2,{true,true});
    Reject([&]{BuildMask(grid,0);});Reject([&]{BuildMask(grid,65);});Reject([&]{BuildMask(grid,16,0);});
    Reject([&]{BuildMask(grid,16,1023);});Reject([&]{BuildMask(grid,16,DefaultMaxMaskTexels+1);});
    auto large=MakeGrid(256,64,{true,true});Reject([&]{BuildMask(large,64);});
    MaskTexture empty;Reject([&]{SampleMask(empty,0,0,false,false);});
    auto texture=BuildMask(grid);Reject([&]{SampleMask(texture,nan,0,false,false);});
    texture.texels[0].b=1;texture.texels[0].r=0;Reject([&]{SampleMask(texture,0,0,false,false);});
    Reject([&]{MaskUv(infinity,0,2,2);});Reject([&]{MaskUv(0,0,0,2);});
    Colour colour{0.1f,0.2f,0.3f,1};ImageView bad;Reject([&]{Sample2D(bad,0,0);});
    ImageView image{&colour,1,1,1};Reject([&]{Sample2D(image,infinity,0);});
    Reject([&]{Sample2D(image,0,0,static_cast<AddressMode>(99));});
    image.count=2;Reject([&]{Sample2D(image,0,0);});
    const Colour poisoned{nan,0,0,1};ImageView badSample{&poisoned,1,1,1};Reject([&]{Sample2D(badSample,0,0);});
    ImageView oversized{&colour,16384,16384,268435456};Reject([&]{Sample2D(oversized,0,0);});
    Lut3DView lut{&colour,1,1,1,1};Reject([&]{SampleLut(lut,{nan,0,0,1});});
    lut.count=2;Reject([&]{SampleLut(lut,colour);});
    Lut3DView hugeLut{&colour,16384,16384,16384,0};Reject([&]{SampleLut(hugeLut,colour);});
    Lut3DView badLut{&poisoned,1,1,1,1};Reject([&]{SampleLut(badLut,colour);});
    Reject([&]{BlendFow(colour,colour,{0.5f,0,1},colour,true);});
    Reject([&]{BlendFow({nan,0,0,1},colour,{1,0,0},colour,true);});
    Reject([&]{BlendFow(colour,{nan,0,0,1},{1,0,1},colour,false);});
    Reject([&]{ApplyFow(colour,colour,{1,0,0},Lut3DView{},true);});
    Reject([&]{DistanceRampUv(infinity,0);});Reject([&]{DistanceFogFactor({infinity,0,1},1,1,1);});
    Reject([&]{DistanceFogFactor({1,1,1},-1,1,1);});Reject([&]{DistanceFogFactor({1,1,1},1,-1,1);});
    Reject([&]{DistanceFogFactor({1,1,1},1,1,nan);});Reject([&]{ApplyDistanceFog(colour,colour,nan);});
    Reject([&]{FlowUv(0,0,0,3);});Reject([&]{FlowUv(0,0,infinity,0);});Reject([&]{FlowUv(0,0,1000000001,0);});
}
}
int main(){try{
    section="RasterAndMasks";RasterAndMasks();section="SamplingAndLuts";SamplingAndLuts();
    section="PrivacyAndColourOrder";PrivacyAndColourOrder();section="DistanceAndFlow";DistanceAndFlow();
    section="InvalidInputs";InvalidInputs();
    std::printf("PASS_ORIGINAL_FOG_MODEL checks=%u\n",checks);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"Original fog model: %s\n",error.what());return 1;}}
