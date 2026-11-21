#include "OriginalIceAssets.h"
#include "OriginalIceShader.h"
#include <iostream>
#include <limits>
#include <string>
#include <fcntl.h>
#include <io.h>

using namespace ZeroSisPresentation::OriginalIce;
namespace {
unsigned checks=0,actualAssets=0,actualTexels=0;
void Expect(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
void Near(double a,double b,const char* why){Expect(std::abs(a-b)<0.00001,why);}
template<class F>void Reject(F action,const char* why){bool threw=false;try{action();}catch(const std::invalid_argument&){threw=true;}Expect(threw,why);}
void Put(std::vector<unsigned char>& bytes,unsigned at,std::uint32_t value){for(unsigned i=0;i<4;++i)bytes.at(at+i)=static_cast<unsigned char>(value>>(i*8));}
std::uint32_t ReadWord(){unsigned char bytes[4];std::cin.read(reinterpret_cast<char*>(bytes),4);Expect(bool(std::cin),"Truncated test framing");return Word(bytes);}
void SelfChecks(){
    Expect(FeatureCellMask==128&&ReflectionSceneMask==1&&EffectId==59&&VertexStride==8&&IndexBytes==2,"Original recovered identifiers");
    Expect(!OriginalGeometryProviderAvailable&&!OriginalMaterialProviderAvailable,"Incomplete original provider must stay unavailable");
    Expect(MarkFeatureCell(3)==131&&IsMarkedFeatureCell(131)&&!IsMarkedFeatureCell(3),"Feature mask must preserve other bits");
    const BoundsRecord view{0,0,1,1,0};const std::vector<BoundsRecord> records{{-1,-1,0,0,7},{1,1,2,2,8},{1.01f,0,2,1,9}};
    const auto tokens=VisibleDrawTokens(true,records,view);Expect(tokens==std::vector<std::uint32_t>({7,8}),"Inclusive bounds and original token order");
    Expect(VisibleDrawTokens(false,records,view).empty(),"Disabled ice draw must submit nothing");
    Reject([&](){auto bad=view;bad.minX=std::numeric_limits<float>::quiet_NaN();BoundsIntersect(bad,view);},"Nonfinite bounds must fail");
    Reject([&](){BoundsIntersect({2,0,1,1,0},view);},"Inverted bounds must fail");
    const unsigned char raw[8]={0,128,255,127,0,128,255,64};const auto vertex=DecodeVertex(raw,8);
    Near(vertex.position[0],-1,"SNORM negative endpoint");Near(vertex.position[1],1,"SNORM positive endpoint");
    Near(vertex.normalAndHeight[1],128.0/255,"UNORM intermediate");Reject([&](){DecodeVertex(raw,7);},"Vertex extent");
    VertexConstants c{};c.rows[0][0]=c.rows[1][1]=c.rows[2][2]=c.rows[3][3]=1;
    c.rows[4]={{10,20,0,0}};c.rows[5]={{30,60,0,0}};c.rows[6][0]=51;c.rows[7][0]=-8;
    c.rows[8][0]=.01f;c.rows[9][1]=.02f;c.rows[11]={{1,2,0,0}};c.rows[12]={{100,100,30,0}};c.rows[13]={{.005f,.01f,2,-4}};
    const auto output=EvaluateVertex(vertex,c);Near(output.world[0],10,"World X");Near(output.world[1],60,"World Y");Near(output.world[2],4.8,"World Z");
    Near(output.normal[0],-1,"Normal decode X");Near(output.normal[2],1,"Normal decode Z");Near(output.toCamera[2],25.2,"Camera-relative Z");
    Near(output.clipXY[0],10,"Projection X");Near(output.clipXY[1],60,"Projection Y");Near(output.maskUv[0],.05,"Mask X sign/offset");
    Near(output.maskUv[1],-2.1,"Mask Y sign/offset");Near(output.unexploredUv[0],.06,"Unexplored X");Near(output.unexploredUv[1],.56,"Unexplored Y");
    Reject([&](){auto bad=c;bad.rows[3][3]=0;EvaluateVertex(vertex,bad);},"Zero projection W");
    const auto weights=ProjectionWeights({{1,2,3}});Near(weights[0],1.0/98,"Projection fourth power X");Near(weights[1],16.0/98,"Projection fourth power Y");Near(weights[2],81.0/98,"Projection fourth power Z");
    Reject([](){ProjectionWeights({{0,0,0}});},"Zero normal must fail");
    const std::array<double,4> rgba={{.75,.25,.5,.75}};const auto sides=DecodeMoments(rgba,.125,2,false),top=DecodeMoments(rgba,.125,2,true);
    Near(sides.meanX,1,"Ice S multiplies X");Near(sides.meanY,-1,"Ice S multiplies Y");Near(sides.varianceXX,1,"Ice covariance XX");Near(sides.varianceYY,2,"Ice covariance YY");
    Near(sides.varianceXY,-2,"Ice side cross-plane");Near(top.varianceXY,3,"Original top alpha cross source");
    const Vec3 material{{.8f,.6f,.4f}},unexplored{{.1f,.2f,.3f}},lut{{.3f,.4f,.5f}};
    const auto mixed=ApplyExplorationMask(material,unexplored,lut,.25f,.4f);Near(mixed[0],.27875,"Fog R blend");Near(mixed[1],.315,"Fog R/B recolor");Near(mixed[2],.35125,"Fog blue");
    Expect(ApplyExplorationMask(material,unexplored,lut,0,0)==unexplored,"Hidden ice material must not leak");
    Expect(MaskDiscards(0)&&!MaskDiscards(.0001f),"Original exact mask-zero discard");
    Reject([](){MaskDiscards(-1);},"Invalid mask");
    std::vector<unsigned char> lean(41);std::memcpy(lean.data(),"LEAN",4);const float scale=.25f;std::memcpy(lean.data()+4,&scale,4);
    Put(lean,8,1);Put(lean,12,1);Put(lean,16,1);Put(lean,20,1);Put(lean,24,36);Put(lean,28,40);lean[32]=1;
    lean[33]=9;lean[34]=8;lean[35]=7;lean[36]=0;lean[37]=64;lean[38]=128;lean[39]=255;lean[40]=17;
    const auto texture=DecodeLean8(lean.data(),lean.size());Expect(texture.planes[0][0].rowPitch==4&&texture.planes[1][0].offset==40,"8-bit plane layout");
    Expect(ReadLeanTexel(lean.data(),lean.size(),0,0,0)==std::array<unsigned,5>{{0,64,128,255,17}},"8-bit channels and opaque padding");
    Reject([&](){DecodeLean8(lean.data(),lean.size()-1);},"Truncated LEAN");Reject([&](){ReadLeanTexel(lean.data(),lean.size(),0,1,0);},"LEAN coordinate bound");
    Reject([&](){auto bad=lean;Put(bad,20,2);DecodeLean8(bad.data(),bad.size());},"Water16-bit must not enter ice8-bit");
    Reject([&](){auto bad=lean;Put(bad,16,2);DecodeLean8(bad.data(),bad.size());},"Incomplete/bad mip count");
    Reject([&](){VerifySource(lean,std::string(64,'0'));},"Source SHA must be checked");
    Reject([&](){DecodeDds(lean.data(),lean.size(),DdsRole::Environment);},"Non-DDS cannot become ice cube");
}
void ActualAssets(){
    char magic[8];std::cin.read(magic,8);Expect(bool(std::cin)&&std::memcmp(magic,"ZSICE12\0",8)==0,"Actual fixture framing");
    Expect(ReadWord()==6,"Actual source roles");
    const char* hashes[6]={"0031f344fb33f59123a88ec2c5b122ca99ea3ee1c20dcbfa450842b048160ceb","18aa6ae166db33d4ba52e32972ac7ab3c68a56b29ad8990664b24e79d6b6a045",
        "dd9ab0099a2e715519dee7018f19813157c319e8eb9815ac954a65266cb04b9d","1492e821d42b6ccdedc017e321e9859a90952e5aa0a69da23239f954fe12fd11",
        "df50794be4bb15417d31c594a123f927b6d33ed1cb58c496adca75b83ac0a6b8","41203210a463d575f727c5a5d531089da63f7428c58b14c228a906fd78a9da11"};
    for(unsigned role=0;role<6;++role){const auto bytes=ReadWord();Expect(bytes>0&&bytes<=4u*1024u*1024u,"Actual source byte bound");
        std::vector<unsigned char> raw(bytes);std::cin.read(reinterpret_cast<char*>(raw.data()),bytes);Expect(bool(std::cin),"Truncated actual asset");VerifySource(raw,hashes[role]);
        if(role<2){const auto texture=DecodeLean8(raw.data(),raw.size());Expect(texture.width==512&&texture.height==512&&texture.mips==10,"Actual ice LEAN shape");
            const auto count=ReadWord();Expect(count==30,"Independent actual LEAN sample count");
            for(unsigned sample=0;sample<count;++sample){const auto mip=ReadWord(),x=ReadWord(),y=ReadWord();unsigned char expected[5];std::cin.read(reinterpret_cast<char*>(expected),5);Expect(bool(std::cin),"Truncated actual sample");
                const auto texel=ReadLeanTexel(raw.data(),raw.size(),mip,x,y);for(unsigned i=0;i<5;++i)Expect(texel[i]==expected[i],"Independent original LEAN sample differs");++actualTexels;}}
        else{const DdsRole roles[4]={DdsRole::Diffuse,DdsRole::SideDiffuse,DdsRole::Environment,DdsRole::Displacement};const auto texture=DecodeDds(raw.data(),raw.size(),roles[role-2]);
            const unsigned widths[4]={512,512,128,256},mips[4]={10,10,8,9},faces[4]={1,1,6,1};
            Expect(texture.width==widths[role-2]&&texture.height==widths[role-2]&&texture.mips==mips[role-2]&&texture.faces==faces[role-2],"Original ice DDS face/mip layout");
            Reject([&](){DecodeDds(raw.data(),raw.size()-1,roles[role-2]);},"Actual DDS truncation must fail");}
        ++actualAssets;
    }
    Expect(std::cin.peek()==std::char_traits<char>::eof(),"Actual fixture trailing bytes");
}
}
int main(int argc,char** argv){
    if(argc==2&&std::string(argv[1])=="--emit-vs"){std::cout<<VertexShaderSource();return 0;}
    try{Expect(_setmode(_fileno(stdin),_O_BINARY)!=-1,"Binary RAM fixture input");SelfChecks();ActualAssets();std::cout<<"{\"status\":\"PASS\",\"checks\":"<<checks<<",\"actual_assets\":"<<actualAssets<<",\"actual_lean_texels\":"<<actualTexels
        <<",\"geometry_provider_available\":false,\"material_provider_available\":false}"<<std::endl;return 0;}
    catch(const std::exception& error){std::cerr<<error.what()<<std::endl;return 1;}
}
