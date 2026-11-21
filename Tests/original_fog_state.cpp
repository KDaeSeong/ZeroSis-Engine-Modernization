#include "OriginalFogState.h"
#include <cstdio>
#include <string>

using namespace ZeroSisPresentation::OriginalFog;
namespace {
unsigned checks=0;
void Require(bool value,const char* reason){++checks;if(!value)throw std::runtime_error(reason);}
template<class F>void Reject(F body){bool rejected=false;try{body();}catch(const std::invalid_argument&){rejected=true;}Require(rejected,"Invalid fog state view was accepted");}
struct MinimalPlot {int x=0,y=0;bool revealed=false,visible=false;};
struct MinimalView {int gridWidth=0,gridHeight=0;bool wrapX=false,wrapY=false;std::vector<MinimalPlot> plots;};
struct RichPlot:MinimalPlot {
    double terrainHeight=0;int terrainId=0,continent=0,index=0;std::string feature;
};
struct RichView {int gridWidth=0,gridHeight=0;bool wrapX=false,wrapY=false;std::vector<RichPlot> plots;
    double cameraX=0,cameraY=0,zoom=1,animationSeconds=0;unsigned seed=0;int selected=-1,units=0;};
MinimalView Make(int width,int height){
    MinimalView result;result.gridWidth=width;result.gridHeight=height;
    for(int row=0;row<height;++row)for(int column=0;column<width;++column)
        result.plots.push_back({column,row,column%3!=0,column%3==1});
    return result;
}
void CaptureAndIdentity(){
    const auto minimal=Make(8,4);const auto grid=CaptureFogGrid(minimal);
    Require(grid.width==8&&grid.height==4&&grid.cells.size()==32,"Fog state dimensions differ");
    Require(!grid.wrapX&&!grid.wrapY,"Fog state wrap flags differ");
    for(const auto& plot:minimal.plots){const auto& cell=grid.cells[static_cast<std::size_t>(plot.y)*grid.width+plot.x];
        Require(cell.revealed==plot.revealed&&cell.visible==plot.visible,"Fog state row-major content differs");
    }
    Require(SameFogGrid(grid,grid),"Valid fog state key is not reflexive");
    auto shuffled=minimal;std::reverse(shuffled.plots.begin(),shuffled.plots.end());
    Require(SameFogGrid(grid,CaptureFogGrid(shuffled)),"Plot order changed canonical fog key");
    for(const bool wrapX:{false,true})for(const bool wrapY:{false,true}){
        auto wrapped=minimal;wrapped.wrapX=wrapX;wrapped.wrapY=wrapY;const auto value=CaptureFogGrid(wrapped);
        Require(value.wrapX==wrapX&&value.wrapY==wrapY,"Fog wrapping was not captured");
        Require(SameFogGrid(grid,value)==(!wrapX&&!wrapY),"Fog wrapping was omitted from key");
    }
    auto different=Make(4,8);Require(!SameFogGrid(grid,CaptureFogGrid(different)),"Equal cell count concealed dimension change");
    for(std::size_t i=0;i<minimal.plots.size();++i){
        auto changed=minimal;auto& plot=changed.plots[i];
        if(plot.visible)plot.visible=false;
        else if(plot.revealed)plot.visible=true;
        else plot.revealed=true;
        const auto value=CaptureFogGrid(changed);
        Require(!SameFogGrid(grid,value)&&!SameFogGrid(value,grid),"A cell visibility/exploration change reused the fog key");
    }
    auto maximum=Make(256,64);const auto large=CaptureFogGrid(maximum);
    Require(large.cells.size()==16384&&SameFogGrid(large,large),"Maximum bounded fog state failed");
    const auto smallest=CaptureFogGrid(Make(1,1));Require(smallest.cells.size()==1,"One-cell fog state failed");
}
void IgnoredInputs(){
    RichView view;view.gridWidth=8;view.gridHeight=4;view.wrapX=true;view.wrapY=true;
    const auto minimal=Make(8,4);
    for(const auto& plot:minimal.plots){RichPlot rich;rich.x=plot.x;rich.y=plot.y;rich.revealed=plot.revealed;rich.visible=plot.visible;
        view.plots.push_back(rich);}
    const auto before=CaptureFogGrid(view);
    for(int iteration=0;iteration<100;++iteration){
        view.cameraX=iteration*37.0;view.cameraY=-iteration*43.0;view.zoom=iteration+1.0;
        view.animationSeconds=iteration*999.0;view.seed=static_cast<unsigned>(iteration);view.selected=iteration;view.units=iteration*3;
        for(auto& plot:view.plots){plot.terrainHeight=std::numeric_limits<double>::quiet_NaN();
            plot.terrainId=-iteration;plot.continent=iteration;plot.index=1000000-iteration;plot.feature.assign(32,'X');}
        const auto after=CaptureFogGrid(view);
        Require(SameFogGrid(before,after),"Camera/time/seed/terrain/unit/selection input contaminated fog state key");
        const auto maskA=BuildMask(before),maskB=BuildMask(after);
        Require(maskA.texels.size()==maskB.texels.size(),"Ignored state changed mask size");
        for(std::size_t i=0;i<maskA.texels.size();++i){const auto& a=maskA.texels[i];const auto& b=maskB.texels[i];
            Require(a.r==b.r&&a.g==b.g&&a.b==b.b,"Ignored state changed fog mask pixels");
        }
    }
}
void MalformedViews(){
    auto view=Make(2,2);view.gridWidth=0;Reject([&]{CaptureFogGrid(view);});
    view=Make(2,2);view.gridHeight=-1;Reject([&]{CaptureFogGrid(view);});
    view=Make(2,2);view.gridWidth=257;Reject([&]{CaptureFogGrid(view);});
    view=Make(2,2);view.gridHeight=257;Reject([&]{CaptureFogGrid(view);});
    view=Make(256,65);Reject([&]{CaptureFogGrid(view);});
    view=Make(2,2);view.plots.pop_back();Reject([&]{CaptureFogGrid(view);});
    view=Make(2,2);view.plots.push_back(view.plots[0]);Reject([&]{CaptureFogGrid(view);});
    for(int index=0;index<4;++index){view=Make(2,2);view.plots[index].x=-1;Reject([&]{CaptureFogGrid(view);});
        view=Make(2,2);view.plots[index].x=2;Reject([&]{CaptureFogGrid(view);});
        view=Make(2,2);view.plots[index].y=-1;Reject([&]{CaptureFogGrid(view);});
        view=Make(2,2);view.plots[index].y=2;Reject([&]{CaptureFogGrid(view);});
        view=Make(2,2);view.plots[index].revealed=false;view.plots[index].visible=true;Reject([&]{CaptureFogGrid(view);});
    }
    view=Make(2,2);view.plots[3]=view.plots[0];Reject([&]{CaptureFogGrid(view);});
    view=Make(2,3);view.wrapY=true;Reject([&]{CaptureFogGrid(view);});
    Grid malformed;Require(!SameFogGrid(malformed,malformed),"Malformed grid was accepted as a reusable key");
    auto grid=CaptureFogGrid(Make(2,2));auto copy=grid;copy.cells.pop_back();Require(!SameFogGrid(grid,copy),"Partial grid reused key");
    copy=grid;copy.cells[0]={false,true};Require(!SameFogGrid(grid,copy),"Invalid visibility reused key");
    Require(!SameFogGrid(copy,copy),"Identical invalid visibility reused key");
    copy=grid;copy.width=-1;Require(!SameFogGrid(copy,copy),"Negative width reused key");
    copy=grid;copy.height=3;copy.cells.resize(6);copy.wrapY=true;Require(!SameFogGrid(copy,copy),"Odd vertical wrap reused key");
}
}
int main(){try{CaptureAndIdentity();IgnoredInputs();MalformedViews();
    std::printf("PASS_ORIGINAL_FOG_STATE checks=%u\n",checks);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"Original fog state: %s\n",error.what());return 1;}}
