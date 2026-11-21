#include "menu_frontend_scene_fixture.h"
#include "MenuFrontEndGridLayout.h"
#include <array>
#include <iostream>
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
template<class F>static void Reject(F fn){try{fn();}catch(const std::exception&){++checks;return;}throw std::runtime_error("Invalid grid layout was accepted");}
static float Float(const std::vector<unsigned char>& bytes,std::size_t& cursor){
    const auto word=U32(bytes,cursor);float value;std::memcpy(&value,&word,4);return value;
}
static std::string Text(const std::vector<unsigned char>& bytes,std::size_t& cursor){
    const auto n=U32(bytes,cursor);if(n>1024 || n>bytes.size()-cursor)throw std::runtime_error("Invalid grid fixture text");
    const std::string value(reinterpret_cast<const char*>(bytes.data()+cursor),n);cursor+=n;return value;
}
static std::vector<std::array<float,4>> Legacy(const MenuFrontEndAssets::Style& style,float x,float y,float width,float height){
    float left=0,right=0,top=0,bottom=0;
    for(const auto& piece:style.pieces){const auto w=piece.source[2]-piece.source[0],h=piece.source[3]-piece.source[1];
        if(piece.column==0)left=(std::max)(left,w);if(piece.column==2)right=(std::max)(right,w);
        if(piece.row==0)top=(std::max)(top,h);if(piece.row==2)bottom=(std::max)(bottom,h);}
    if(style.kind==1){top=bottom=0;}if(style.kind==2){left=right=0;}if(style.kind==3){left=right=top=bottom=0;}
    if(width<left+right || height<top+bottom)throw std::runtime_error("Invalid legacy test geometry");
    const float xs[]={x,x+left,x+width-right,x+width},ys[]={y,y+top,y+height-bottom,y+height};
    std::vector<std::array<float,4>> result;
    for(const auto& piece:style.pieces){const auto c=style.kind==2 || style.kind==3?1:piece.column,r=style.kind==1 || style.kind==3?1:piece.row;
        result.push_back({{xs[c],ys[r],xs[c+1],ys[r+1]}});}
    return result;
}
struct Row final {std::string name;bool actual=false;MenuFrontEndAssets::Style style;};
int wmain(int argc,wchar_t** argv){try{
    if(argc!=3)throw std::runtime_error("Expected exact immutable V3 pack and file-only golden matrix");
    const auto assets=MenuFrontEndAssets::Load(argv[1]);const auto bytes=Read(argv[2]);std::size_t cursor=0;
    Check(U32(bytes,cursor)==0x5247535a && U32(bytes,cursor)==0x31304449,"Grid golden schema differs");
    const auto count=U32(bytes,cursor);Check(count>16 && count<64,"Grid golden style inventory differs");std::vector<Row> rows;
    for(unsigned i=0;i<count;++i){Row row;row.name=Text(bytes,cursor);row.actual=U32(bytes,cursor)!=0;auto& style=row.style;
        style.kind=U32(bytes,cursor);style.texture=U32(bytes,cursor);style.width=Float(bytes,cursor);style.height=Float(bytes,cursor);
        style.stepX=Float(bytes,cursor);style.stepY=Float(bytes,cursor);const auto pieces=U32(bytes,cursor);Check(pieces>0 && pieces<=9,"Grid piece fixture count");
        for(unsigned n=0;n<pieces;++n){MenuFrontEndAssets::StylePiece piece;piece.column=U32(bytes,cursor);piece.row=U32(bytes,cursor);
            for(auto& value:piece.source)value=Float(bytes,cursor);style.pieces.push_back(piece);}
        rows.push_back(std::move(row));
    }
    auto empty=assets->Background();empty.sprites.clear();empty.hits.clear();empty.scrolls.clear();empty.lines.clear();
    std::size_t originalGridCalls=0,oracleTargets=0,legacyByteEqualTargets=0,asymmetricFrameProofs=0;
    const auto cases=U32(bytes,cursor);Check(cases>2000 && cases<10000,"Expected full current style/state matrix");
    for(unsigned n=0;n<cases;++n){const auto index=U32(bytes,cursor),state=U32(bytes,cursor);Check(index<rows.size() && state<4,"Grid case owner/state");
        const auto& row=rows[index];const auto& style=row.style;const float x=Float(bytes,cursor),y=Float(bytes,cursor),w=Float(bytes,cursor),h=Float(bytes,cursor);
        const auto legacyEqual=U32(bytes,cursor)!=0;const auto expectedCount=U32(bytes,cursor);Check(expectedCount==style.pieces.size(),"Grid oracle piece ordering");
        const auto targets=BuildMenuFrontEndGridLayout(style.kind,style.pieces,x,y,w,h);Check(targets.size()==expectedCount,"Grid output count");
        for(const auto& target:targets){float expected[4];for(auto& value:expected)value=Float(bytes,cursor);
            Check(std::memcmp(target.data(),expected,16)==0,"Grid target differs from independent per-cap oracle");++oracleTargets;}
        if(legacyEqual){const auto old=Legacy(style,x,y,w,h);Check(old.size()==targets.size(),"Legacy grid piece count");
            for(std::size_t i=0;i<old.size();++i){Check(std::memcmp(old[i].data(),targets[i].data(),16)==0,"Unaffected symmetric/H3/V3/stretch target bytes changed");++legacyByteEqualTargets;}}
        if(row.name=="Grid9DetailFive140" && x==480 && y==262 && w==960 && h==628){
            Check(targets[6]==std::array<float,4>{{480,840,554,890}} && targets[7]==std::array<float,4>{{554,820,1366,890}} && targets[8]==std::array<float,4>{{1366,840,1440,890}},"Original asymmetric frame cap sizes/alignment lost");
            const auto old=Legacy(style,x,y,w,h);Check(old[6][1]==820 && old[6][3]-old[6][1]==70 && targets[6][3]-targets[6][1]==50,"Fixture did not reproduce repaired 50px-to70px corner distortion");++asymmetricFrameProofs;
        }
        if(row.actual){auto scene=empty;assets->Grid(scene,6789,row.name,x,y,w,h,state);++originalGridCalls;std::size_t spriteIndex=0;
            for(std::size_t i=0;i<targets.size();++i){const auto& target=targets[i];if(target[2]<=target[0] || target[3]<=target[1])continue;
                Check(spriteIndex<scene.sprites.size(),"Actual assets.Grid omitted a positive cap");const auto& sprite=scene.sprites[spriteIndex++];const auto& piece=style.pieces[i];
                const float source[]={piece.source[0]+state*style.stepX,piece.source[1]+state*style.stepY,piece.source[2]+state*style.stepX,piece.source[3]+state*style.stepY};
                Check(sprite.textureIndex==style.texture && sprite.controlKey==6789,"Actual assets.Grid source texture/control identity changed");
                Check(std::memcmp(sprite.sourceRect,source,16)==0 && std::memcmp(sprite.targetRect,target.data(),16)==0,"Actual assets.Grid did not use exact source/state or per-cap destination");
                const float clip[]={0,0,1920,1080},tint[]={1,1,1,1};Check(std::memcmp(sprite.clipRect,clip,16)==0 && std::memcmp(sprite.tintRGBA,tint,16)==0,"Actual assets.Grid clip/color changed");
            }
            if(row.name=="GenericPullDown"){
                Check(spriteIndex<scene.sprites.size(),"Existing dropdown arrow was removed");const auto& arrow=scene.sprites[spriteIndex++];
                const float source[]={0.0f,state==1?16.0f:0.0f,16.0f,state==1?32.0f:16.0f},target[]={x+w-19,y+h-19,x+w-3,y+h-3};
                Check(arrow.textureIndex==assets->TextureNamed("corner16.dds").index && arrow.controlKey==6789 && std::memcmp(arrow.sourceRect,source,16)==0 && std::memcmp(arrow.targetRect,target,16)==0,"Existing dropdown arrow state or geometry changed");
            }
            Check(spriteIndex==scene.sprites.size() && scene.lines.empty() && scene.hits.empty() && scene.scrolls.empty(),"Grid gained unrelated drawing/input records");
        }
    }
    Check(cursor==bytes.size() && asymmetricFrameProofs==4,"Golden matrix exact consumption/frame states");
    const auto first=rows[0].style;const auto invoke=[&](unsigned kind,const std::vector<MenuFrontEndAssets::StylePiece>& pieces,float x,float y,float w,float h){BuildMenuFrontEndGridLayout(kind,pieces,x,y,w,h);};
    Reject([&]{invoke(4,first.pieces,0,0,960,628);});Reject([&]{invoke(0,{},0,0,960,628);});
    for(const auto value:{0.0f,-1.0f,100000.0f,(std::numeric_limits<float>::infinity)(),(std::numeric_limits<float>::quiet_NaN)()}){
        Reject([&]{invoke(0,first.pieces,0,0,value,628);});Reject([&]{invoke(0,first.pieces,0,0,960,value);});}
    for(const auto value:{100000.0f,-100000.0f,(std::numeric_limits<float>::infinity)(),(std::numeric_limits<float>::quiet_NaN)()}){
        Reject([&]{invoke(0,first.pieces,value,0,960,628);});Reject([&]{invoke(0,first.pieces,0,value,960,628);});}
    Reject([&]{invoke(0,first.pieces,0,0,147.875f,628);});Reject([&]{invoke(0,first.pieces,0,0,960,129.875f);});
    auto malformed=first.pieces;malformed[0].column=3;Reject([&]{invoke(0,malformed,0,0,960,628);});
    malformed=first.pieces;malformed[0].row=3;Reject([&]{invoke(0,malformed,0,0,960,628);});
    malformed=first.pieces;malformed[1]=malformed[0];Reject([&]{invoke(0,malformed,0,0,960,628);});
    malformed=first.pieces;malformed.push_back(malformed[0]);Reject([&]{invoke(0,malformed,0,0,960,628);});
    malformed=first.pieces;malformed[0].source[2]=malformed[0].source[0];Reject([&]{invoke(0,malformed,0,0,960,628);});
    malformed=first.pieces;malformed[0].source[3]=(std::numeric_limits<float>::quiet_NaN)();Reject([&]{invoke(0,malformed,0,0,960,628);});
    Reject([&]{auto scene=empty;assets->Grid(scene,0,"Grid9DetailFive140",0,0,960,628,4);});
    Reject([&]{auto scene=empty;assets->Grid(scene,0,"Grid9DetailFive140",0,0,147,628);});
    std::cout<<"{\"status\":\"PASS_ORIGINAL_PER_CAP_GRID_AND_ACTUAL_V3_SCENE\",\"checks\":"<<checks<<",\"matrix_cases\":"<<cases
        <<",\"actual_current_style_scene_calls\":"<<originalGridCalls<<",\"independent_oracle_targets\":"<<oracleTargets<<",\"unchanged_legacy_target_byte_comparisons\":"<<legacyByteEqualTargets
        <<",\"original_asymmetric_frame_state_proofs\":"<<asymmetricFrameProofs<<",\"native_host_sdk_window_gpu_executed\":false}"<<std::endl;return 0;
}catch(const std::exception& error){std::cerr<<error.what()<<std::endl;return 1;}}
