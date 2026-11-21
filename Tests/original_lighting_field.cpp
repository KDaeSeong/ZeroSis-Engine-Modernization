#include "OriginalLightingFieldModel.h"
#include "original_lighting_field_golden.h"
#include <cstdio>
#include <cstring>
#include <limits>

namespace F=ZeroSisPresentation::OriginalLighting::Field;
namespace L=ZeroSisPresentation::OriginalLighting;
namespace T=ZeroSisPresentation::OriginalTerrain;
namespace {
unsigned checks=0;const char* section="start";
void Check(bool value,const char* reason){++checks;if(!value)throw std::runtime_error(reason);}
void Near(double a,double b,double tolerance=3e-10){const bool same=std::isfinite(a)&&std::isfinite(b)&&std::abs(a-b)<=tolerance*(1+std::abs(b));
    if(!same)std::fprintf(stderr,"section=%s check=%u a=%.17g b=%.17g\n",section,checks,a,b);Check(same,"Independent field reference differs");}
template<class Fn>void Reject(Fn fn){bool rejected=false;try{fn();}catch(const std::invalid_argument&){rejected=true;}Check(rejected,"Malformed field input was accepted");}
std::uint32_t Bits(double value){const float f=static_cast<float>(value);std::uint32_t result=0;std::memcpy(&result,&f,4);return result;}
struct Plot {int x=0,y=0;bool revealed=false;};
struct View {int gridWidth=0,gridHeight=0;bool wrapX=false,wrapY=false;std::vector<Plot> plots;};
F::Domain Domain(unsigned width,unsigned height,bool wrap=true){F::Domain domain;domain.width=width;domain.height=height;domain.wrapX=domain.wrapY=wrap;
    domain.revealed.assign(static_cast<std::size_t>(width)*height,1);return domain;}
T::Atlas Atlas(const F::Domain& domain){T::Atlas atlas;atlas.width=domain.width*64;atlas.height=domain.height*64;atlas.wrapX=domain.wrapX;atlas.wrapY=domain.wrapY;
    const auto count=static_cast<std::size_t>(atlas.width)*atlas.height;atlas.known.assign(count,1);atlas.ids.assign(count,3);atlas.heights.resize(count);
    const double offset=static_cast<double>(T::HeightOffsetCandidate);
    for(unsigned y=0;y<atlas.height;++y)for(unsigned x=0;x<atlas.width;++x){const double raw=0.2+0.35*(x%16)/15.0+0.1*(y%8)/7.0;
        atlas.heights[static_cast<std::size_t>(y)*atlas.width+x]=static_cast<float>(raw-offset);}
    return atlas;}
void RawShadow(){
    for(const auto& expected:GoldenRawShadows){F::ShadowParams params;params.heightScale=expected.scale;params.biasAndStrength=expected.bias;
        const auto actual=F::RawShadow40(expected.initial,expected.alpha,expected.length,params);
        Near(actual.value,expected.value);Near(actual.lit,expected.lit);Check(actual.complete&&actual.steps==40&&actual.samples==41,"Raw shadow did not perform40 original steps");}
    F::ShadowParams params;params.heightScale=1;params.biasAndStrength=0.125;std::array<double,40> alpha{};alpha.fill(64.0/255);
    auto actual=F::RawShadow40(0,alpha,0,params);Near(actual.value,0,1e-12);Near(actual.lit,1,1e-12);
    alpha.fill(160.0/255);actual=F::RawShadow40(0,alpha,0,params);Near(actual.value,0.125,0);Near(actual.lit,0,0);
    params.biasAndStrength=0;alpha.fill(0.5);actual=F::RawShadow40(0.5,alpha,0,params);Near(actual.lit,1,0);
    Check(Bits(F::RayRise)==0x3ea1043du&&Bits(F::Inverse96)==0x3c2aaaabu,"Original shadow float constants changed");
    F::NormalPolicy normal;Near(normal.strength,16,0);Check(Bits(normal.strength)==0x41800000u,"Original normal strength literal changed");
}
void TraceOrderAndPrivacy(){
    F::ShadowParams params;params.directionX=-1;params.directionY=1;
    std::vector<std::array<double,2>> sampled;const auto allKnown=[](double,double){return true;};
    const auto result=F::GuardedShadow40(2.5,3.5,params,allKnown,[&](double x,double y){sampled.push_back({{x,y}});return 0.2;});
    Check(result.complete&&sampled.size()==41,"Guarded complete trace sample count differs");Near(sampled[0][0],2.5,0);Near(sampled[0][1],3.5,0);
    for(unsigned i=1;i<sampled.size();++i){Near(sampled[i][0],2.5-(i+1),0);Near(sampled[i][1],3.5+(i+1),0);}
    unsigned reads=0;const auto partial=F::GuardedShadow40(2.5,3.5,params,
        [](double x,double){return x> -3.5;},[&](double x,double){Check(x> -3.5,"Unknown shadow sample callback executed");++reads;return 0.8;});
    Check(!partial.complete&&partial.samples==5&&partial.steps==4&&reads==5,"Unknown-ray zero policy did not stop before invalid sample");Near(partial.value,0,0);
    reads=0;const auto empty=F::GuardedShadow40(0,0,params,[](double,double){return false;},[&](double,double){++reads;return 0.9;});
    Check(!empty.complete&&empty.samples==0&&reads==0,"Unknown origin read a shadow sample");
    params.directionX=params.directionY=0;unsigned knownCalls=0;
    const auto zero=F::GuardedShadow40(0,0,params,[&](double,double){++knownCalls;return true;},[&](double,double){++reads;return 0.9;});
    Check(!zero.complete&&zero.samples==0&&knownCalls==0&&reads==0,"Zero-direction safety policy sampled undefined original ray");
}
void RealAtlasGoldens(){const auto domain=Domain(2,2);const auto atlas=Atlas(domain);
    for(const auto& expected:GoldenAtlasShadows){F::ShadowParams params;params.directionX=expected.dx;params.directionY=expected.dy;
        unsigned reads=0;const auto result=F::GuardedShadow40(expected.x,expected.y,params,
            [&](double x,double y){return F::Detail::KnownSupport(domain,atlas,x,y);},
            [&](double x,double y){Check(F::Detail::KnownSupport(domain,atlas,x,y),"Atlas sampler reached unknown bilinear support");++reads;return F::Detail::Alpha(atlas,x,y,params.heightOffset);});
        Check(result.complete&&result.samples==41&&reads==41,"Wrapped real atlas trace failed support");Near(result.value,expected.value);Near(result.lit,expected.lit);
    }
    const F::TileSpec spec{0,0,64,1};const auto tile=F::BuildShadowTile(domain,atlas,spec);
    Check(tile.width==66&&tile.height==66&&tile.values.size()==4356&&tile.complete.size()==4356,"Shadow tile is not canonical66 squared");
    Check(tile.samples==4356ull*41&&tile.incompleteTexels==0,"Complete shadow tile sample accounting differs");
    for(const auto value:tile.values)Check(value>=0&&value<=0.125f,"Shadow tile left bounded UNORM amplitude");
    auto poison=atlas;poison.known[0]=0;poison.heights[0]=(std::numeric_limits<float>::quiet_NaN)();
    const auto guarded=F::BuildShadowTile(domain,poison,spec);Check(guarded.incompleteTexels>0,"Unknown support did not neutralize entire shadow rays");
    const auto repeated=F::GuardedShadow40(0.5+512*128,0.5-512*128,F::ShadowParams{},
        [&](double x,double y){return F::Detail::KnownSupport(domain,atlas,x,y);},
        [&](double x,double y){return F::Detail::Alpha(atlas,x,y,F::ShadowParams{}.heightOffset);});
    const auto original=F::GuardedShadow40(0.5,0.5,F::ShadowParams{},
        [&](double x,double y){return F::Detail::KnownSupport(domain,atlas,x,y);},
        [&](double x,double y){return F::Detail::Alpha(atlas,x,y,F::ShadowParams{}.heightOffset);});
    Check(repeated.complete&&original.complete,"Multiple512 wrapped atlas periods lost support");Near(repeated.value,original.value,0);
}
void NormalsAndSeams(){
    auto domain=Domain(3,4,false);const auto atlas=Atlas(domain);const F::TileSpec tile{1,1,64,1};unsigned reads=0;
    const auto normals=F::BuildNormalTile(domain,atlas,tile,[&](double x,double y){++reads;return 0.5+x/4096+y/8192;});
    Check(normals.width==66&&normals.height==66&&normals.materialSamples==4624&&reads==4624,"H68 producer did not memoize one sample per supported centre");
    Check(normals.fallbackTaps==0,"Interior canonical halo failed to cover Sobel stencil");
    const double nx=128.0/4096,ny=-128.0/8192,length=std::sqrt(nx*nx+ny*ny+16);
    const double expected[3]={0.5+nx/length*0.5,0.5+ny/length*0.5,0.5+4/length*0.5};
    for(std::size_t i=0;i<normals.encoded.size();++i){Check(normals.flags[i]==3,"Interior normal is not complete");
        for(unsigned c=0;c<3;++c)Near(normals.encoded[i][c],expected[c],4e-8);}
    auto wrapped=Domain(2,2);const auto periodic=Atlas(wrapped);
    const auto material=[](double x,double y){return 0.5+0.1*std::sin(x*6.283185307179586/128)+0.1*std::cos(y*6.283185307179586/128);};
    const auto a=F::BuildNormalTile(wrapped,periodic,{0,0,64,1},material),b=F::BuildNormalTile(wrapped,periodic,{1,0,64,1},material),
        c=F::BuildNormalTile(wrapped,periodic,{0,1,64,1},material);
    for(unsigned y=0;y<66;++y)for(unsigned pair=0;pair<2;++pair)for(unsigned component=0;component<3;++component){
        Near(a.encoded[y*66+64+pair][component],b.encoded[y*66+pair][component],0);
        Near(b.encoded[y*66+64+pair][component],a.encoded[y*66+pair][component],0);
        Near(a.encoded[(64+pair)*66+y][component],c.encoded[pair*66+y][component],0);
        Near(c.encoded[(64+pair)*66+y][component],a.encoded[pair*66+y][component],0);}
    const auto support=F::BuildKnownSupport(wrapped,periodic,{0,0,64,2});Check(support.size()==4624,"Height support is not68 squared");
    const auto actualBytes=normals.encoded.size()*sizeof(normals.encoded[0])+normals.flags.size()+4624*(sizeof(float)+1);
    Check(actualBytes<=F::MaxChunkFieldBytes,"Normal source and output payload exceed110KiB");
    // The newly identified t8 role is baked specular. Drive the actual renamed
    // CPU API from the generated detail normal, preserving the old scalar math.
    const auto& encoded=normals.encoded[33*66+33];L::TerrainBakeInput bake;
    bake.normalSample={encoded[0],encoded[1],encoded[2]};bake.albedo={0.2,0.3,0.4};bake.specular={0.1,0.12,0.14,0.25};bake.specularEnabled=true;
    const auto identity=[](L::Rgb value){return value;};
    const auto baked=L::BakeTerrain(bake,[](L::Rgb){return L::Rgb{0.4,0.5,0.6};},[](L::Rgb){return L::Rgb{0.1,0.2,0.3};},identity);
    L::TerrainFinalInput final;final.litCache=baked.diffuse;final.specularCache=baked.specular;final.useScreenLight=true;final.screenLight={1,1,1};
    const auto combined=L::FinalTerrain(final,identity,identity);final.useScreenLight=false;const auto diffuseOnly=L::FinalTerrain(final,identity,identity);
    Check(combined.r>diffuseOnly.r&&combined.g>diffuseOnly.g&&combined.b>diffuseOnly.b,"Baked specular did not add through the newly identified final t8 input");
    Near(diffuseOnly.r,baked.diffuse.x);Near(diffuseOnly.g,baked.diffuse.y);Near(diffuseOnly.b,baked.diffuse.z);
}
void SparseUnknownAndQuantization(){
    View sparse;sparse.gridWidth=sparse.gridHeight=4;sparse.plots.push_back({0,0,true});const auto domain=F::CaptureDomain(sparse);
    Check(domain.revealed.size()==16&&domain.revealed[0]==1,"Sparse domain dropped supplied reveal");
    for(unsigned i=1;i<16;++i)Check(domain.revealed[i]==0,"Sparse missing plot is not unknown");
    auto atlas=Atlas(domain);std::fill(atlas.heights.begin(),atlas.heights.end(),(std::numeric_limits<float>::quiet_NaN)());
    unsigned material=0;const auto normals=F::BuildNormalTile(domain,atlas,{2,2,64,1},[&](double,double){++material;return 0.8;});
    const auto shadow=F::BuildShadowTile(domain,atlas,{2,2,64,1});
    Check(normals.materialSamples==0&&material==0&&shadow.samples==0,"Sparse unknown tile accessed hidden material/physical height");
    for(std::size_t i=0;i<normals.encoded.size();++i){Check(normals.flags[i]==0&&shadow.complete[i]==0,"Missing sparse cell became known");
        Near(normals.encoded[i][0],0.5,0);Near(normals.encoded[i][1],0.5,0);Near(normals.encoded[i][2],1,0);Near(shadow.values[i],0,0);}
    for(const auto& expected:GoldenQuant)Check(F::ToUnorm16(expected.input)==expected.output,"UNORM16 bounded half-up conversion differs");
    for(unsigned value=0;value<=65535;++value){const auto normalized=F::FromUnorm16(static_cast<std::uint16_t>(value));
        Check(normalized>=0&&normalized<=1&&F::ToUnorm16(normalized)==value,"UNORM16 stored word does not roundtrip");}
    for(unsigned i=0;i<=1000;++i){const double input=i/1000.0;Near(F::FromUnorm16(F::ToUnorm16(input)),input,0.5/65535+1e-12);}
}
void Malformed(){
    auto domain=Domain(2,2);auto atlas=Atlas(domain);const double nan=(std::numeric_limits<double>::quiet_NaN)();
    auto invalid=atlas;invalid.originX=0;Reject([&]{F::BuildKnownSupport(domain,invalid,{0,0,64,2});});
    invalid=atlas;invalid.wrapX=false;Reject([&]{F::BuildKnownSupport(domain,invalid,{0,0,64,2});});
    Reject([&]{F::BuildKnownSupport(domain,atlas,{2,0,64,2});});Reject([&]{F::BuildKnownSupport(domain,atlas,{0,0,32,2});});
    Reject([&]{F::BuildKnownSupport(domain,atlas,{0,0,64,3});});
    F::NormalPolicy normal;normal.strength=nan;Reject([&]{F::BuildNormalTile(domain,atlas,{0,0,64,1},[](double,double){return 0.5;},normal);});
    Reject([&]{F::BuildNormalTile(domain,atlas,{0,0,64,1},[&](double,double){return nan;});});
    Reject([&]{F::BuildNormalTile(domain,atlas,{0,0,64,2},[](double,double){return 0.5;});});
    invalid=atlas;invalid.heights[0]=(std::numeric_limits<float>::quiet_NaN)();Reject([&]{F::BuildShadowTile(domain,invalid,{0,0,64,1});});
    F::ShadowParams params;params.biasAndStrength=2;Reject([&]{F::BuildShadowTile(domain,atlas,{0,0,64,1},params);});
    params={};params.directionX=nan;Reject([&]{F::BuildShadowTile(domain,atlas,{0,0,64,1},params);});
    params={};params.heightOffset=2;Reject([&]{F::BuildShadowTile(domain,atlas,{0,0,64,1},params);});
    std::array<double,40> raw{};raw[7]=nan;Reject([&]{F::RawShadow40(0.2,raw,0.01,F::ShadowParams{});});
    Reject([&]{F::ToUnorm16(nan);});
    View view;view.gridWidth=view.gridHeight=1;view.plots={{0,0,true},{0,0,true}};Reject([&]{F::CaptureDomain(view);});
    view.gridWidth=view.gridHeight=2;Reject([&]{F::CaptureDomain(view);});view.plots={{2,0,true}};Reject([&]{F::CaptureDomain(view);});
    view.plots.clear();view.gridWidth=500;view.gridHeight=1000;Reject([&]{F::CaptureDomain(view);});
    domain=Domain(2,3);atlas=Atlas(domain);Reject([&]{F::BuildKnownSupport(domain,atlas,{0,0,64,2});});
}
}
int main(){try{section="RawShadow";RawShadow();section="TraceOrderAndPrivacy";TraceOrderAndPrivacy();section="RealAtlasGoldens";RealAtlasGoldens();
    section="NormalsAndSeams";NormalsAndSeams();section="SparseUnknownAndQuantization";SparseUnknownAndQuantization();section="Malformed";Malformed();
    std::printf("PASS_ORIGINAL_LIGHTING_FIELD checks=%u\n",checks);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"Lighting field section=%s check=%u reason=%s\n",section,checks,error.what());return 1;}}
