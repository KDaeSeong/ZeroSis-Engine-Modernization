// Exact original Lua pointer-guide goldens; no SDK, window or renderer.
#include "MenuReplayPointerGuides.h"
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <limits>
#include <string>
#include <vector>

using namespace ZeroSisHost;
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
class Fixture final {
public:
    explicit Fixture(const wchar_t* path){
        std::ifstream stream(path,std::ios::binary);
        if(!stream)throw std::runtime_error("Cannot read pointer-guide goldens");
        bytes_.assign(std::istreambuf_iterator<char>(stream),{});
        if(bytes_.size()<12 || std::memcmp(bytes_.data(),"ZSGUID01",8))throw std::runtime_error("Pointer-guide golden header changed");
        at_=8;
    }
    template<class T> T Read(){
        if(sizeof(T)>bytes_.size()-at_)throw std::runtime_error("Pointer-guide golden truncated");
        T result{};std::memcpy(&result,bytes_.data()+at_,sizeof(T));at_+=sizeof(T);return result;
    }
    std::string Name(){
        const auto count=Read<std::uint32_t>();
        if(count>128 || count>bytes_.size()-at_)throw std::runtime_error("Pointer-guide case name invalid");
        const std::string value(reinterpret_cast<const char*>(bytes_.data()+at_),count);at_+=count;return value;
    }
    bool Finished() const noexcept{return at_==bytes_.size();}
private:
    std::vector<unsigned char> bytes_;std::size_t at_=0;
};
static unsigned OriginalGoldens(const wchar_t* path,unsigned& visible,unsigned& comparedCoordinates){
    Fixture input(path);const auto count=input.Read<std::uint32_t>();
    Check(count>0 && count<=4096,"Pointer-guide golden case count invalid");
    std::array<double,4> widths{};std::array<std::array<std::uint8_t,4>,4> colors{};
    for(unsigned line=0;line<4;++line){widths[line]=input.Read<double>();for(auto& value:colors[line])value=input.Read<std::uint8_t>();}
    for(unsigned index=0;index<count;++index){
        const auto name=input.Name();
        const auto originX=input.Read<double>(),originY=input.Read<double>();
        const auto width=input.Read<double>(),height=input.Read<double>();
        const auto pointerX=input.Read<double>(),pointerY=input.Read<double>();
        const auto graphsVisible=input.Read<std::uint32_t>(),expectedVisible=input.Read<std::uint32_t>();
        const auto actual=BuildMenuReplayPointerGuides(originX,originY,width,height,pointerX,pointerY,graphsVisible!=0);
        if(actual.visible!=(expectedVisible!=0))throw std::runtime_error("Original strict-bounds visibility differs: "+name);
        ++checks;if(actual.visible)++visible;
        for(unsigned line=0;line<4;++line){
            Check(actual.lines[line].width==widths[line] && actual.lines[line].rgba==colors[line],"Pointer-guide XML order/width/RGBA changed");
            const double actualCoordinates[]={actual.lines[line].startX,actual.lines[line].startY,actual.lines[line].endX,actual.lines[line].endY};
            for(const auto value:actualCoordinates){
                const auto expected=input.Read<double>();
                if(actual.visible){
                    if(value!=expected)throw std::runtime_error("Verbatim original Lua line coordinate differs: "+name);
                    ++checks;++comparedCoordinates;
                }
            }
        }
    }
    Check(input.Finished(),"Trailing pointer-guide golden bytes");return count;
}
static void OwnerAvailability(){
    for(const auto coordinate:{0.0,660.0,1020.0,1380.0,(std::numeric_limits<double>::max)(),
        std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),std::numeric_limits<double>::quiet_NaN()}){
        Check(!BuildMenuReplayPointerGuides(660,375,720,360,coordinate,555,true,false).visible,"Unavailable pointer emitted guide geometry");
        Check(!BuildMenuReplayPointerGuides(660,375,720,360,coordinate,555,false,true).visible,"Hidden graph panel emitted pointer guides");
    }
    const auto middle=BuildMenuReplayPointerGuides(660,375,720,360,1020,555,true);
    Check(middle.visible && middle.lines[0].startX==360 && middle.lines[0].startY==0 && middle.lines[0].endY==360,
        "Source V3 vertical crosshair origin changed");
    Check(middle.lines[1].startX==0 && middle.lines[1].startY==180 && middle.lines[1].endX==720,"Source V3 horizontal crosshair origin changed");
    Check(middle.lines[2].startY==360 && middle.lines[2].endY==368 && middle.lines[3].startX==720 && middle.lines[3].endX==728,
        "Original red eight-pixel guides were clipped to the canvas");
    Check(middle.lines[0].rgba==std::array<std::uint8_t,4>{{90,90,90,90}} &&
        middle.lines[2].rgba==std::array<std::uint8_t,4>{{255,0,0,255}},"Source guide alpha/color bytes changed");
}
static unsigned InvalidGeometry(){
    const auto nan=std::numeric_limits<double>::quiet_NaN(),inf=std::numeric_limits<double>::infinity();
    const std::array<double,4> invalid[]={
        {{nan,375,720,360}},{{660,inf,720,360}},{{660,375,nan,360}},{{660,375,720,inf}},
        {{660,375,0,360}},{{660,375,-1,360}},{{660,375,720,0}},{{660,375,720,-1}},
        {{0,0,10000000,360}},{{0,0,720,10000000}},{{10000000,0,1,360}},{{0,10000000,720,1}},
        {{-10000001,0,720,360}},{{0,-10000001,720,360}},{{9999991,0,2,360}},{{0,9999991,720,2}},
        {{1000000,0,(std::numeric_limits<double>::min)(),360}},{{0,1000000,720,(std::numeric_limits<double>::min)()}},
    };
    unsigned rejected=0;
    for(const auto& geometry:invalid){
        bool threw=false;try{BuildMenuReplayPointerGuides(geometry[0],geometry[1],geometry[2],geometry[3],0,0,false,false);}
        catch(const std::invalid_argument&){threw=true;++rejected;}
        Check(threw,"Invalid/unrepresentable guide geometry was accepted");
    }
    Check(BuildMenuReplayPointerGuides(9999990,9999990,2,2,9999991,9999991,true).visible,
        "Exact upper SceneLine coordinate limit was rejected");
    Check(BuildMenuReplayPointerGuides(-10000000,-10000000,720,360,-9999640,-9999820,true).visible,
        "Exact lower SceneLine origin limit was rejected");
    return rejected;
}
int wmain(int argc,wchar_t** argv){try{
    if(argc!=2)throw std::runtime_error("Expected owned original Lua golden fixture");
    unsigned visible=0,comparedCoordinates=0;const auto cases=OriginalGoldens(argv[1],visible,comparedCoordinates);
    OwnerAvailability();const auto rejected=InvalidGeometry();
    std::printf("{\"status\":\"PASS_VERBATIM_ORIGINAL_LUA_POINTER_GUIDES_CXX14\",\"checks\":%u,\"original_lua_cases\":%u,\"visible_cases\":%u,\"exact_line_coordinates\":%u,\"invalid_geometry_rejected\":%u,\"native_execution\":false}\n",
        checks,cases,visible,comparedCoordinates,rejected);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}}
