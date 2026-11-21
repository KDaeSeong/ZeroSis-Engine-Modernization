#include "MenuReplayGraphColors.h"
#include <cstdint>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <limits>

namespace {
using namespace ZeroSisHost;
void Check(bool value,const char* message){if(!value)throw std::runtime_error(message);}
class Reader final {
public:
    explicit Reader(const char* path){
        std::ifstream input(path,std::ios::binary);
        Check(bool(input),"Cannot open source-Lua golden fixture");
        bytes_.assign(std::istreambuf_iterator<char>(input),std::istreambuf_iterator<char>());
        Check(bytes_.size()>=12 && bytes_.size()<=32u*1024u*1024u,"Golden fixture size is out of bounds");
        Check(std::memcmp(bytes_.data(),"ZSGRC001",8)==0,"Golden fixture version differs");
        cursor_=8;
    }
    std::uint32_t U32(){
        Check(Left()>=4,"Truncated golden integer");std::uint32_t value=0;
        for(unsigned i=0;i<4;++i)value|=std::uint32_t(bytes_[cursor_++])<<(8*i);
        return value;
    }
    double Double(){
        Check(Left()>=8,"Truncated golden double");double value=0;
        std::memcpy(&value,bytes_.data()+cursor_,8);cursor_+=8;return value;
    }
    std::string Text(){
        const auto count=U32();Check(count<=4096 && count<=Left(),"Golden text exceeds bounds");
        const std::string value(reinterpret_cast<const char*>(bytes_.data()+cursor_),count);
        cursor_+=count;return value;
    }
    MenuReplayGraphColor Color(){
        MenuReplayGraphColor value;value.type=Text();value.r=Double();value.g=Double();value.b=Double();value.a=Double();
        return value;
    }
    std::size_t Left() const {return bytes_.size()-cursor_;}
private:
    std::vector<unsigned char> bytes_;std::size_t cursor_=0;
};
template<class Function> void Throws(Function function){
    bool failed=false;try{function();}catch(const std::runtime_error&){failed=true;}
    Check(failed,"Malformed graph color input did not fail explicitly");
}
unsigned InvalidAndBounds(){
    const MenuReplayGraphColor white{"WHITE",1,1,1,1};
    const std::vector<MenuReplayGraphColor> valid{white};
    const std::vector<std::pair<std::string,std::string>> roster{{"WHITE","WHITE"}};
    unsigned count=0;
    Throws([&]{SelectMenuReplayGraphColors({},roster);});++count;
    Throws([&]{SelectMenuReplayGraphColors({white,white},roster);});++count;
    for(const double value:{std::numeric_limits<double>::quiet_NaN(),
        std::numeric_limits<double>::infinity(),-std::numeric_limits<double>::infinity(),-0.001,1.001}){
        for(int channel=0;channel<4;++channel){
            auto bad=white;double* channels[]={&bad.r,&bad.g,&bad.b,&bad.a};*channels[channel]=value;
            Throws([&]{SelectMenuReplayGraphColors({bad},roster);});++count;
        }
    }
    auto bad=white;bad.type.clear();Throws([&]{SelectMenuReplayGraphColors({bad},roster);});++count;
    bad.type=std::string("WHITE\0TAIL",10);Throws([&]{SelectMenuReplayGraphColors({bad},roster);});++count;
    bad.type=std::string(1025,'X');Throws([&]{SelectMenuReplayGraphColors({bad},roster);});++count;
    Throws([&]{SelectMenuReplayGraphColors(valid,{{"MISSING","WHITE"}});});++count;
    Throws([&]{SelectMenuReplayGraphColors(valid,{{"WHITE","MISSING"}});});++count;
    Throws([&]{SelectMenuReplayGraphColors(valid,std::vector<std::pair<std::string,std::string>>(65,{"WHITE","WHITE"}));});++count;
    Check(SelectMenuReplayGraphColors(valid,{}).empty(),"Empty recorded roster should remain empty");++count;
    Check(SelectMenuReplayGraphColors(valid,std::vector<std::pair<std::string,std::string>>(64,{"WHITE","WHITE"})).size()==64,
        "Maximum recorded roster rejected");++count;
    std::vector<MenuReplayGraphColor> maximum;
    for(unsigned i=0;i<4096;++i)maximum.push_back({"BOUND_"+std::to_string(i),1,1,1,1});
    Check(SelectMenuReplayGraphColors(maximum,{{"BOUND_4095","BOUND_0"}})[0].type=="BOUND_4095",
        "Maximum bounded catalog rejected");++count;
    maximum.push_back({"TOO_MANY",1,1,1,1});
    Throws([&]{SelectMenuReplayGraphColors(maximum,roster);});++count;
    return count;
}
}

int main(int argc,char** argv){
    try{
        Check(argc==2,"Expected one source-Lua golden file");Reader input(argv[1]);
        const auto count=input.U32();Check(count>0 && count<=4096,"Golden case count out of bounds");
        std::size_t matched=0;
        for(std::uint32_t index=0;index<count;++index){
            const auto name=input.Text();
            const auto colors=input.U32();Check(colors>0 && colors<=4096,"Golden color count out of bounds");
            std::vector<MenuReplayGraphColor> catalog;catalog.reserve(colors);
            for(std::uint32_t i=0;i<colors;++i)catalog.push_back(input.Color());
            const auto players=input.U32();Check(players<=64,"Golden roster count out of bounds");
            std::vector<std::pair<std::string,std::string>> roster;
            for(std::uint32_t i=0;i<players;++i){const auto primary=input.Text();const auto secondary=input.Text();roster.emplace_back(primary,secondary);}
            const auto expectedCount=input.U32();Check(expectedCount==players,"Golden selected roster size differs");
            std::vector<MenuReplayGraphColor> expected;
            for(std::uint32_t i=0;i<expectedCount;++i)expected.push_back(input.Color());
            const auto actual=SelectMenuReplayGraphColors(catalog,roster);
            Check(actual.size()==expected.size(),"Selected graph color count differs from source Lua");
            for(std::size_t i=0;i<actual.size();++i){
                const auto& a=actual[i];const auto& e=expected[i];
                if(a.type!=e.type || a.r!=e.r || a.g!=e.g || a.b!=e.b || a.a!=e.a)
                    throw std::runtime_error("Graph color differs from original Lua: "+name+" player "+std::to_string(i)+
                        " expected "+e.type+" actual "+a.type);
                ++matched;
            }
        }
        Check(input.Left()==0,"Trailing bytes in source-Lua golden file");
        const auto invalid=InvalidAndBounds();
        std::cout<<"{\"status\":\"PASS_ORIGINAL_LUA_GRAPH_COLOR_GOLDENS_CXX14\",\"cases\":"<<count
            <<",\"matched_selected_colors\":"<<matched<<",\"invalid_and_bounds_checks\":"<<invalid
            <<",\"host_sdk_window_gpu_execution\":false}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
}
