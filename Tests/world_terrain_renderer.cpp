#include "../Source/Presentation/WorldTerrainRenderer.h"
#include "../Source/Presentation/BitmapRenderer.h"

#include <Windows.h>
#include <d3d11.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace ZeroSisPresentation;

namespace {
void Check(bool condition,const char* message){if(!condition)throw std::runtime_error(message);}
void CheckRender(bool result,const std::wstring& error,const char* context){
    if(result)return;std::string message=context;message+=": ";
    for(const auto value:error)message+=value>=0&&value<128?static_cast<char>(value):'?';
    throw std::runtime_error(message);
}
std::uint32_t Read32(const std::vector<unsigned char>& bytes,std::size_t offset){
    Check(offset+4<=bytes.size(),"truncated package word");
    return std::uint32_t(bytes[offset])|(std::uint32_t(bytes[offset+1])<<8)|
        (std::uint32_t(bytes[offset+2])<<16)|(std::uint32_t(bytes[offset+3])<<24);
}
std::size_t StaticUnitPackageEnd(const std::vector<unsigned char>& bytes){
    Check(bytes.size()>=20,"truncated unit package header");
    const bool v1=std::memcmp(bytes.data(),"ZSUNIT01",8)==0&&Read32(bytes,8)==1;
    const bool v2=std::memcmp(bytes.data(),"ZSUNIT02",8)==0&&Read32(bytes,8)==2;
    Check(v1||v2,"invalid unit package header in static prefix parser");
    std::size_t cursor=12;
    const unsigned textures=Read32(bytes,cursor);cursor+=4;Check(textures>0&&textures<=64,"invalid fixture texture count");
    for(unsigned i=0;i<textures;++i){const auto size=Read32(bytes,cursor);cursor+=4;
        Check(size<=bytes.size()-cursor,"truncated fixture texture");cursor+=size;}
    const unsigned arts=Read32(bytes,cursor);cursor+=4;Check(arts>0&&arts<=64,"invalid fixture art count");
    for(unsigned a=0;a<arts;++a){const auto name=Read32(bytes,cursor);cursor+=4;
        Check(name<=bytes.size()-cursor,"truncated fixture art name");cursor+=name;
        const unsigned meshes=Read32(bytes,cursor);cursor+=4;Check(meshes>0&&meshes<=128,"invalid fixture mesh count");
        for(unsigned m=0;m<meshes;++m){const unsigned vertices=Read32(bytes,cursor+4),indices=Read32(bytes,cursor+8);cursor+=12;
            const std::size_t payload=static_cast<std::size_t>(vertices)*32+static_cast<std::size_t>(indices)*4;
            Check(payload<=bytes.size()-cursor,"truncated fixture mesh");cursor+=payload;}}
    Check(v2?cursor<bytes.size():cursor==bytes.size(),"unit static prefix boundary is invalid");return cursor;
}
float FirstUnitAnimationDuration(const std::vector<unsigned char>& bytes){
    std::size_t cursor=StaticUnitPackageEnd(bytes);Check(std::memcmp(bytes.data(),"ZSUNIT02",8)==0,"animation duration requires v2 package");
    const unsigned files=Read32(bytes,cursor);cursor+=4;Check(files>0&&files<=16,"invalid embedded unit file count");
    for(unsigned i=0;i<files;++i){const unsigned name=Read32(bytes,cursor);cursor+=4;
        Check(name<=bytes.size()-cursor,"truncated embedded unit filename");cursor+=name;
        const unsigned size=Read32(bytes,cursor);cursor+=4;Check(size<=bytes.size()-cursor,"truncated embedded unit file");cursor+=size;}
    const unsigned rigs=Read32(bytes,cursor);cursor+=4;Check(rigs>0&&rigs<=16&&cursor+20<=bytes.size(),"invalid animation rig table");
    float duration=0;std::memcpy(&duration,bytes.data()+cursor+16,sizeof(duration));
    Check(std::isfinite(duration)&&duration>0,"invalid original unit animation duration");return duration;
}
std::vector<unsigned char> ReadFile(const std::filesystem::path& path){
    std::ifstream in(path,std::ios::binary|std::ios::ate);Check(in.good(),"cannot read package");
    const auto length=in.tellg();Check(length>=0,"invalid package length");
    std::vector<unsigned char> bytes(static_cast<std::size_t>(length));in.seekg(0);
    in.read(reinterpret_cast<char*>(bytes.data()),length);Check(in.good(),"short package read");return bytes;
}
void WriteFile(const std::filesystem::path& path,const std::vector<unsigned char>& bytes){
    std::ofstream out(path,std::ios::binary|std::ios::trunc);Check(out.good(),"cannot write test fixture package");
    out.write(reinterpret_cast<const char*>(bytes.data()),static_cast<std::streamsize>(bytes.size()));
    Check(out.good(),"failed to write test fixture package");
}
WorldViewPlot Plot(int x,int y,const std::string& terrain,bool visible=true,bool hills=false,bool mountain=false,bool water=false){
    WorldViewPlot p{};p.index=y*9+x;p.x=x;p.y=y;p.revealed=true;p.visible=visible;p.water=water;
    p.hills=hills;p.mountain=mountain;p.terrain=terrain;p.feature="";p.continent=4;return p;
}
WorldView MakeView(const std::wstring& package){
    WorldView view{};view.gridWidth=9;view.gridHeight=9;view.turn=20;view.activePlayer=0;
    view.wrapX=false;view.wrapY=false;view.cameraX=4;view.cameraY=4;view.tileWidth=56;
    view.terrainAssetsPath=package;view.plots.reserve(81);
    const char* types[]={"TERRAIN_GRASS","TERRAIN_PLAINS","TERRAIN_DESERT","TERRAIN_TUNDRA",
        "TERRAIN_SNOW","TERRAIN_COAST","TERRAIN_OCEAN","TERRAIN_GRASS","TERRAIN_GRASS"};
    for(int y=0;y<9;++y)for(int x=0;x<9;++x){
        const int kind=(x+2*y)%9;const bool water=kind==5||kind==6;
        auto p=Plot(x,y,types[kind],true,kind==7,kind==8,water);
        if(kind==5)p.terrain="TERRAIN_COAST";
        if(kind==6)p.terrain="TERRAIN_OCEAN";
        view.plots.push_back(std::move(p));
    }
    view.plots[4*9+4].mountain=true;view.plots[4*9+4].hills=false;
    view.plots[4*9+4].terrain="TERRAIN_GRASS";
    view.plots[4*9+3].hills=true;view.plots[4*9+3].terrain="TERRAIN_GRASS";
    return view;
}
std::vector<std::uint64_t> Resolved(const TerrainFrame& frame){
    std::vector<std::uint64_t> output(frame.picking.indices.size());
    for(std::size_t i=0;i<output.size();++i){const auto key=frame.picking.indices[i];
        if(key){Check(key<=frame.picking.keys.size(),"pixel picking index outside key table");output[i]=frame.picking.keys[key-1];}}
    return output;
}
bool HasColor(const TerrainFrame& frame){
    for(std::size_t i=0;i+3<frame.bgra.size();i+=4)
        if(frame.bgra[i+3]!=0&&(frame.bgra[i]!=0||frame.bgra[i+1]!=0||frame.bgra[i+2]!=0))return true;
    return false;
}
void ValidateProjectedPlots(const TerrainFrame& frame,unsigned width,unsigned height,unsigned mapWidth){
    Check(frame.picking.indices.size()==static_cast<std::size_t>(width)*height,
          "projection validation received a malformed ID raster");
    std::map<int,std::vector<unsigned char>> expected;
    for(const auto& entry:frame.projectedPlots)
        expected.emplace(entry.first,std::vector<unsigned char>(static_cast<std::size_t>(width)*height,0));
    for(unsigned y=0;y<height;++y)for(unsigned x=0;x<mapWidth;++x){
        const auto offset=static_cast<std::size_t>(y)*width+x;
        const auto id=frame.picking.indices[offset];if(!id)continue;
        Check(id<=frame.picking.keys.size(),"terrain ID raster contains an invalid key index");
        const auto key=frame.picking.keys[id-1];
        for(const auto& entry:frame.projectedPlots){
            if(key!=WorldViewHitKey::Plot(entry.first))continue;
            const auto differs=[&](unsigned nx,unsigned ny){
                return frame.picking.indices[static_cast<std::size_t>(ny)*width+nx]!=id;
            };
            if(x==0||x+1==mapWidth||y==0||y+1==height||differs(x-1,y)||differs(x+1,y)||
               differs(x,y-1)||differs(x,y+1))
                expected.at(entry.first)[offset]=1;
            break;
        }
    }
    for(const auto& entry:frame.projectedPlots){
        const int plotIndex=entry.first;const auto& plot=entry.second;
        int previousY=-1,previousEnd=-1;
        auto actual=std::vector<unsigned char>(static_cast<std::size_t>(width)*height,0);
        for(const auto& span:plot.spans){
            const int y=span[0],x=span[1],count=span[2];
            Check(y>=0&&static_cast<unsigned>(y)<height&&x>=0&&count>0&&
                  static_cast<unsigned>(x)<=mapWidth&&static_cast<unsigned>(count)<=mapWidth-static_cast<unsigned>(x),
                  "projected contour span is outside the map raster");
            Check(y>previousY||(y==previousY&&x>previousEnd),
                  "projected contour spans are not strictly ordered or overlap");
            previousY=y;previousEnd=x+count-1;
            for(int dx=0;dx<count;++dx){
                const auto offset=static_cast<std::size_t>(y)*width+static_cast<unsigned>(x+dx);
                const auto id=frame.picking.indices[offset];
                Check(id>0&&id<=frame.picking.keys.size()&&frame.picking.keys[id-1]==WorldViewHitKey::Plot(plotIndex),
                      "projected contour span contains a pixel owned by another plot");
                actual[offset]=1;
            }
        }
        Check(actual==expected.at(plotIndex),
              "projected spans differ from the independent four-neighbor ID-raster contour");
        const auto center=frame.centers.find(plotIndex);
        Check(plot.anchorVisible==(center!=frame.centers.end()),
              "projected anchor visibility differs from retained pixel-verified centers");
        if(center!=frame.centers.end()){
            Check(plot.centerX==center->second.x&&plot.centerY==center->second.y,
                  "projected anchor differs from the retained terrain center");
            const auto x=static_cast<unsigned>(plot.centerX),y=static_cast<unsigned>(plot.centerY);
            Check(x<mapWidth&&y<height,"visible projected anchor is outside the map viewport");
            const auto id=frame.picking.indices[static_cast<std::size_t>(y)*width+x];
            Check(id>0&&id<=frame.picking.keys.size()&&frame.picking.keys[id-1]==WorldViewHitKey::Plot(plotIndex),
                  "visible projected anchor does not lie on its own plot ID");
        }
    }
}
bool SameProjectedPlots(const std::map<int,WorldProjectedPlot>& a,const std::map<int,WorldProjectedPlot>& b){
    if(a.size()!=b.size())return false;
    auto left=a.begin(),right=b.begin();
    for(;left!=a.end();++left,++right)
        if(left->first!=right->first||left->second.centerX!=right->second.centerX||
           left->second.centerY!=right->second.centerY||left->second.anchorVisible!=right->second.anchorVisible||
           left->second.spans!=right->second.spans)return false;
    return true;
}
bool SameCenters(const std::map<int,TerrainProjection>& a,const std::map<int,TerrainProjection>& b){
    if(a.size()!=b.size())return false;
    auto left=a.begin(),right=b.begin();
    for(;left!=a.end();++left,++right)
        if(left->first!=right->first||left->second.x!=right->second.x||left->second.y!=right->second.y)return false;
    return true;
}
struct TestGpuTarget {
    Microsoft::WRL::ComPtr<ID3D11Device> device;
    Microsoft::WRL::ComPtr<ID3D11DeviceContext> context;
    Microsoft::WRL::ComPtr<ID3D11Texture2D> texture;
};
bool SameHits(const std::vector<HitRecord>& a,const std::vector<HitRecord>& b){
    if(a.size()!=b.size())return false;
    for(std::size_t i=0;i<a.size();++i){
        if(a[i].controlKey!=b[i].controlKey)return false;
        for(unsigned j=0;j<4;++j)if(a[i].bounds[j]!=b[i].bounds[j])return false;
    }
    return true;
}
std::vector<unsigned char> ReadPngBgra(const std::filesystem::path& path,unsigned expectedWidth,unsigned expectedHeight){
    const HRESULT init=CoInitializeEx(nullptr,COINIT_MULTITHREADED);
    Check(SUCCEEDED(init)||init==RPC_E_CHANGED_MODE,"cannot initialize COM for world PNG comparison");
    struct Uninitialize {HRESULT hr;~Uninitialize(){if(SUCCEEDED(hr))CoUninitialize();}} uninit{init};
    Microsoft::WRL::ComPtr<IWICImagingFactory> factory;
    Check(SUCCEEDED(CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,
          IID_PPV_ARGS(&factory))),"cannot create WIC factory for world PNG comparison");
    Microsoft::WRL::ComPtr<IWICBitmapDecoder> decoder;
    Check(SUCCEEDED(factory->CreateDecoderFromFilename(path.c_str(),nullptr,GENERIC_READ,
          WICDecodeMetadataCacheOnLoad,&decoder)),"cannot decode world PNG comparison image");
    Microsoft::WRL::ComPtr<IWICBitmapFrameDecode> frame;
    Check(SUCCEEDED(decoder->GetFrame(0,&frame)),"cannot read world PNG frame");
    UINT width=0,height=0;Check(SUCCEEDED(frame->GetSize(&width,&height))&&width==expectedWidth&&height==expectedHeight,
          "world PNG comparison dimensions differ");
    Microsoft::WRL::ComPtr<IWICFormatConverter> converter;
    Check(SUCCEEDED(factory->CreateFormatConverter(&converter)),"cannot create world PNG pixel converter");
    Check(SUCCEEDED(converter->Initialize(frame.Get(),GUID_WICPixelFormat32bppBGRA,
          WICBitmapDitherTypeNone,nullptr,0,WICBitmapPaletteTypeCustom)),"cannot convert world PNG to BGRA");
    std::vector<unsigned char> pixels(static_cast<std::size_t>(width)*height*4);
    Check(SUCCEEDED(converter->CopyPixels(nullptr,width*4,static_cast<UINT>(pixels.size()),pixels.data())),
          "cannot read world PNG pixels");
    return pixels;
}
struct UnitMarkerEllipse {
    float centerX=0,centerY=0,rx=0,ry=0,strokeHalfWidth=0;
};
struct WorldViewPixelStats {
    std::size_t differingPixels=0;
    std::size_t differingChannelBytes=0;
    std::size_t differingPixelLimit=0;
    std::size_t ellipseAnnulusDiffPixels=0;
    std::size_t ellipseAnnulusOver16Pixels=0;
    std::uint64_t totalRgbDelta=0;
    unsigned maxChannelDelta=0;
    unsigned maxOutsideEllipseDelta=0;
    unsigned maxEllipseAnnulusDelta=0;
    bool alphaExact=true;
    bool differencesOnReferenceEdges=true;
    bool withinLimits=false;
};
bool IsUnitMarkerEllipseStroke(unsigned x,unsigned y,const UnitMarkerEllipse& ellipse){
    const float dx=(static_cast<float>(x)+0.5f-ellipse.centerX)/ellipse.rx;
    const float dy=(static_cast<float>(y)+0.5f-ellipse.centerY)/ellipse.ry;
    const float normalizedRadius=std::sqrt(dx*dx+dy*dy);
    return std::abs(normalizedRadius-1.0f)*std::min(ellipse.rx,ellipse.ry)<=ellipse.strokeHalfWidth+1.0f;
}
std::vector<UnitMarkerEllipse> MatchedUnitMarkerEllipses(const WorldView& view,const Scene& scene){
    std::vector<UnitMarkerEllipse> ellipses;
    for(const auto& unit:view.units){
        if(unit.owner!=view.activePlayer)continue;
        const auto key=WorldViewHitKey::OwnedUnit(unit.id);
        const auto found=std::find_if(scene.hits.begin(),scene.hits.end(),
            [&](const HitRecord& hit){return hit.controlKey==key;});
        if(found==scene.hits.end())continue;
        const float centerX=(found->bounds[0]+found->bounds[2])*0.5f;
        const float centerY=(found->bounds[1]+found->bounds[3])*0.5f;
        ellipses.push_back({centerX,centerY,4.2f*1.5f,5.3f*1.5f,(unit.selected?2.0f:1.0f)*1.5f*0.5f});
    }
    return ellipses;
}
bool ReferenceHasRgbEdge3x3(const std::vector<unsigned char>& reference,unsigned width,unsigned height,
                            unsigned x,unsigned y){
    unsigned minimum[3]={255,255,255},maximum[3]={0,0,0};
    const unsigned left=x?x-1:x,top=y?y-1:y,right=std::min(width-1,x+1),bottom=std::min(height-1,y+1);
    for(unsigned yy=top;yy<=bottom;++yy)for(unsigned xx=left;xx<=right;++xx){
        const auto offset=(static_cast<std::size_t>(yy)*width+xx)*4;
        for(unsigned channel=0;channel<3;++channel){
            const unsigned value=reference[offset+channel];minimum[channel]=std::min(minimum[channel],value);
            maximum[channel]=std::max(maximum[channel],value);
        }
    }
    for(unsigned channel=0;channel<3;++channel)if(maximum[channel]-minimum[channel]>=16)return true;
    return false;
}
WorldViewPixelStats CompareWorldViewPixels(const std::vector<unsigned char>& reference,
                                           const std::vector<unsigned char>& candidate,
                                           unsigned width,unsigned height,
                                           const std::vector<UnitMarkerEllipse>& markerEllipses={}){
    Check(reference.size()==candidate.size()&&reference.size()==static_cast<std::size_t>(width)*height*4,
          "world PNG comparison buffers have inconsistent dimensions");
    WorldViewPixelStats stats{};const std::size_t pixelCount=static_cast<std::size_t>(width)*height;
    stats.differingPixelLimit=pixelCount/1000;
    for(unsigned y=0;y<height;++y)for(unsigned x=0;x<width;++x){
        const auto offset=(static_cast<std::size_t>(y)*width+x)*4;bool pixelDiffers=false;unsigned pixelMaxDelta=0;
        for(unsigned channel=0;channel<4;++channel){
            const int signedDelta=static_cast<int>(candidate[offset+channel])-static_cast<int>(reference[offset+channel]);
            const unsigned delta=static_cast<unsigned>(std::abs(signedDelta));
            if(delta){pixelDiffers=true;++stats.differingChannelBytes;pixelMaxDelta=std::max(pixelMaxDelta,delta);}
            if(channel==3&&delta)stats.alphaExact=false;
            if(channel<3)stats.totalRgbDelta+=delta;
        }
        if(pixelDiffers){
            ++stats.differingPixels;
            stats.maxChannelDelta=std::max(stats.maxChannelDelta,pixelMaxDelta);
            if(!ReferenceHasRgbEdge3x3(reference,width,height,x,y))stats.differencesOnReferenceEdges=false;
            const bool onEllipseStroke=std::any_of(markerEllipses.begin(),markerEllipses.end(),
                [&](const UnitMarkerEllipse& ellipse){return IsUnitMarkerEllipseStroke(x,y,ellipse);});
            if(onEllipseStroke){
                ++stats.ellipseAnnulusDiffPixels;
                if(pixelMaxDelta>16)++stats.ellipseAnnulusOver16Pixels;
                stats.maxEllipseAnnulusDelta=std::max(stats.maxEllipseAnnulusDelta,pixelMaxDelta);
            }else stats.maxOutsideEllipseDelta=std::max(stats.maxOutsideEllipseDelta,pixelMaxDelta);
        }
    }
    const std::uint64_t rgbChannelCount=static_cast<std::uint64_t>(pixelCount)*3;
    stats.withinLimits=stats.alphaExact&&stats.differencesOnReferenceEdges&&stats.maxOutsideEllipseDelta<=16&&
        stats.maxEllipseAnnulusDelta<=64&&
        stats.differingPixels<=stats.differingPixelLimit&&stats.totalRgbDelta*100<=rgbChannelCount;
    return stats;
}
void CheckWorldViewPixelComparatorNegativeCases(){
    constexpr unsigned width=64,height=64;std::vector<unsigned char> reference(width*height*4,100);
    for(std::size_t pixel=0;pixel<width*height;++pixel)reference[pixel*4+3]=255;
    const UnitMarkerEllipse allowed{32.5f,32.5f,12.0f,14.0f,1.5f};
    const auto drawFilledEllipse=[&](std::vector<unsigned char>& pixels,float centerX){
        for(unsigned y=0;y<height;++y)for(unsigned x=0;x<width;++x){
            const float dx=(static_cast<float>(x)+0.5f-centerX)/allowed.rx;
            const float dy=(static_cast<float>(y)+0.5f-allowed.centerY)/allowed.ry;
            if(dx*dx+dy*dy<=1.0f){const auto offset=(static_cast<std::size_t>(y)*width+x)*4;
                pixels[offset]=pixels[offset+1]=pixels[offset+2]=120;}
        }
    };
    for(unsigned y=8;y<=20;++y)for(unsigned x=8;x<=9;++x){
        const auto offset=(static_cast<std::size_t>(y)*width+x)*4;
        reference[offset]=reference[offset+1]=reference[offset+2]=130;
    }
    drawFilledEllipse(reference,allowed.centerX);
    const auto annulusPixel=(static_cast<std::size_t>(18)*width+32)*4;
    const std::size_t pixelLimit=static_cast<std::size_t>(width)*height/1000;
    Check(pixelLimit>=2,"WorldView pixel comparator self-check budget is too small");
    std::size_t caseCount=0;
    const auto reportCase=[&](const char* name,const WorldViewPixelStats& stats,bool expectedPass,const char* reason){
        std::cout<<"WORLD_VIEW_PIXEL_SELF_CHECK name="<<name<<" accepted="<<(stats.withinLimits?"true":"false")
                 <<" expected="<<(expectedPass?"accept":"reject")<<" reason="<<reason
                 <<" differing_pixels="<<stats.differingPixels<<" pixel_limit="<<stats.differingPixelLimit
                 <<" outside_max_delta="<<stats.maxOutsideEllipseDelta
                 <<" annulus_max_delta="<<stats.maxEllipseAnnulusDelta
                 <<" alpha_exact="<<(stats.alphaExact?"true":"false")
                 <<" edge_only="<<(stats.differencesOnReferenceEdges?"true":"false")<<"\n";
        ++caseCount;Check(stats.withinLimits==expectedPass,"WorldView pixel comparator self-check produced an unexpected decision");
    };
    auto candidate=reference;candidate[annulusPixel]+=1;
    const auto acceptedEdge=CompareWorldViewPixels(reference,candidate,width,height,{allowed});
    reportCase("annulus_edge_plus1",acceptedEdge,true,"bounded_edge_delta");
    Check(acceptedEdge.withinLimits&&acceptedEdge.differingPixels<=pixelLimit&&acceptedEdge.maxEllipseAnnulusDelta==1&&
          acceptedEdge.alphaExact&&acceptedEdge.differencesOnReferenceEdges,
          "WorldView pixel comparator rejected a small reference-edge color change");

    candidate=reference;candidate[(static_cast<std::size_t>(14)*width+9)*4]+=32;
    const auto outsideEdgeDelta=CompareWorldViewPixels(reference,candidate,width,height,{allowed});
    reportCase("outside_annulus_edge_plus32",outsideEdgeDelta,false,"outside_max_gt16");
    Check(outsideEdgeDelta.differingPixels<=pixelLimit&&outsideEdgeDelta.maxOutsideEllipseDelta==32&&
          outsideEdgeDelta.differencesOnReferenceEdges&&outsideEdgeDelta.alphaExact&&
          outsideEdgeDelta.totalRgbDelta*100<=static_cast<std::uint64_t>(width)*height*3&&
          !outsideEdgeDelta.withinLimits,"WorldView outside-ellipse edge self-check did not isolate the 16-level guard");

    candidate=reference;candidate[annulusPixel]+=80;
    const auto largeAnnulusDelta=CompareWorldViewPixels(reference,candidate,width,height,{allowed});
    reportCase("annulus_edge_plus80",largeAnnulusDelta,false,"annulus_max_gt64");
    Check(largeAnnulusDelta.differingPixels<=pixelLimit&&largeAnnulusDelta.maxEllipseAnnulusDelta==80&&
          largeAnnulusDelta.differencesOnReferenceEdges&&largeAnnulusDelta.alphaExact&&
          largeAnnulusDelta.totalRgbDelta*100<=static_cast<std::uint64_t>(width)*height*3&&
          !largeAnnulusDelta.withinLimits,"WorldView ellipse-annulus self-check did not enforce the 64-level cap");

    candidate=reference;candidate[(static_cast<std::size_t>(32)*width+32)*4]+=17;
    const auto interiorTint=CompareWorldViewPixels(reference,candidate,width,height,{allowed});
    reportCase("ellipse_interior_tint_plus17",interiorTint,false,"outside_max_gt16_and_no_reference_edge");
    Check(interiorTint.differingPixels<=pixelLimit&&interiorTint.maxOutsideEllipseDelta==17&&
          !interiorTint.differencesOnReferenceEdges&&interiorTint.alphaExact&&
          interiorTint.totalRgbDelta*100<=static_cast<std::uint64_t>(width)*height*3&&
          !interiorTint.withinLimits,"WorldView ellipse-interior self-check did not stay outside the stroke mask");

    candidate=reference;candidate[annulusPixel+3]-=1;
    const auto alphaChange=CompareWorldViewPixels(reference,candidate,width,height,{allowed});
    reportCase("annulus_alpha_minus1",alphaChange,false,"alpha_not_exact");
    Check(alphaChange.differingPixels<=pixelLimit&&alphaChange.maxEllipseAnnulusDelta==1&&!alphaChange.alphaExact&&
          alphaChange.differencesOnReferenceEdges&&alphaChange.totalRgbDelta==0&&
          !alphaChange.withinLimits,"WorldView alpha self-check did not isolate exact alpha parity");

    candidate=reference;drawFilledEllipse(candidate,allowed.centerX+3.0f);
    const auto shiftedGeometry=CompareWorldViewPixels(reference,candidate,width,height,{allowed});
    reportCase("ellipse_geometry_shift_3px",shiftedGeometry,false,"outside_max_gt16_and_reference_edge_missing");
    Check(shiftedGeometry.differingPixels>0&&shiftedGeometry.maxOutsideEllipseDelta>16&&
          shiftedGeometry.alphaExact&&!shiftedGeometry.withinLimits,
          "WorldView shifted-ellipse geometry self-check escaped the stroke mask");

    candidate=reference;candidate[(static_cast<std::size_t>(1)*width+1)*4]+=1;
    const auto flatTint=CompareWorldViewPixels(reference,candidate,width,height,{allowed});
    reportCase("flat_region_tint_plus1",flatTint,false,"no_reference_edge");
    Check(flatTint.differingPixels<=pixelLimit&&flatTint.maxChannelDelta<=16&&flatTint.alphaExact&&
          !flatTint.differencesOnReferenceEdges&&flatTint.totalRgbDelta*100<=static_cast<std::uint64_t>(width)*height*3&&
          !flatTint.withinLimits,"WorldView flat-region tint self-check did not isolate the edge rule");
    Check(caseCount==7,"WorldView pixel comparator self-check count changed unexpectedly");
    std::cout<<"PASS_WORLD_VIEW_PIXEL_COMPARATOR_SELF_CHECK cases="<<caseCount<<"\n";
}
void CheckWorldViewGpuParity(const WorldView& view,const std::filesystem::path& legacyPng,
                             const std::filesystem::path& gpuPng,const TestGpuTarget& target,
                             const char* context){
    Scene legacyScene{},gpuScene{};WorldViewProjection legacyProjection{},gpuProjection{};std::wstring error;
    CheckRender(RenderWorldView(view,legacyPng.wstring(),&legacyScene,&error,&legacyProjection),error,
                "legacy full WorldView render failed");
    error.clear();
    CheckRender(RenderWorldViewToTexture(view,target.device.Get(),target.context.Get(),target.texture.Get(),
                &gpuScene,&error,&gpuProjection),error,"GPU full WorldView render failed");
    Check(gpuScene.width==legacyScene.width&&gpuScene.height==legacyScene.height&&
          SameHits(gpuScene.hits,legacyScene.hits)&&SameHits(gpuScene.scrolls,legacyScene.scrolls),
          "GPU WorldView changed UI hit/scroll records");
    Check(gpuScene.pixelHits.indices==legacyScene.pixelHits.indices&&gpuScene.pixelHits.keys==legacyScene.pixelHits.keys,
          "GPU WorldView changed pixel IDs or hit-key table");
    Check(legacyProjection.ready==gpuProjection.ready&&legacyProjection.frameGeneration==gpuProjection.frameGeneration&&
          legacyProjection.cameraX==gpuProjection.cameraX&&legacyProjection.cameraY==gpuProjection.cameraY&&
          legacyProjection.gridWidth==gpuProjection.gridWidth&&legacyProjection.gridHeight==gpuProjection.gridHeight&&
          legacyProjection.mapWidth==gpuProjection.mapWidth&&SameProjectedPlots(legacyProjection.plots,gpuProjection.plots),
          "GPU WorldView changed camera projection or city highlight spans");
    error.clear();
    CheckRender(CaptureD3D11TextureToPng(target.device.Get(),target.context.Get(),target.texture.Get(),
                gpuPng.wstring(),&error),error,"GPU WorldView diagnostic capture failed");
    const auto legacyPixels=ReadPngBgra(legacyPng,1920,1080);
    const auto gpuPixels=ReadPngBgra(gpuPng,1920,1080);
    const auto markerEllipses=MatchedUnitMarkerEllipses(view,legacyScene);
    const auto stats=CompareWorldViewPixels(legacyPixels,gpuPixels,1920,1080,markerEllipses);
    const std::uint64_t rgbChannelCount=static_cast<std::uint64_t>(1920)*1080*3;
    std::string name=context;for(char& value:name)if(value==' '||value=='/')value='_';
    std::cout<<"WORLD_VIEW_PIXEL_PARITY name="<<name<<" differing_pixels="<<stats.differingPixels
             <<" differing_channel_bytes="<<stats.differingChannelBytes<<" max_channel_delta="<<stats.maxChannelDelta
             <<" total_rgb_delta="<<stats.totalRgbDelta<<" rgb_channel_count="<<rgbChannelCount
             <<" differing_pixel_limit="<<stats.differingPixelLimit<<" alpha_exact="<<(stats.alphaExact?"true":"false")
             <<" reference_3x3_edge_only="<<(stats.differencesOnReferenceEdges?"true":"false")
             <<" matched_unit_marker_ellipses="<<markerEllipses.size()
             <<" ellipse_annulus_diff_pixels="<<stats.ellipseAnnulusDiffPixels
             <<" ellipse_annulus_delta_gt16_pixels="<<stats.ellipseAnnulusOver16Pixels
             <<" max_outside_ellipse_delta="<<stats.maxOutsideEllipseDelta
             <<" max_ellipse_annulus_delta="<<stats.maxEllipseAnnulusDelta
             <<" within_limits="<<(stats.withinLimits?"true":"false")<<"\n";
    if(!stats.withinLimits){
        std::string message=context;message+=" pixel parity thresholds failed: differing pixels ";
        message+=std::to_string(stats.differingPixels)+"/"+std::to_string(stats.differingPixelLimit);
        message+=", max channel delta "+std::to_string(stats.maxChannelDelta)+", RGB delta sum ";
        message+=std::to_string(stats.totalRgbDelta)+"/"+std::to_string(rgbChannelCount);
        message+=", alpha exact ";message+=(stats.alphaExact?"true":"false");message+=", reference edge only ";
        message+=(stats.differencesOnReferenceEdges?"true":"false");
        message+=", outside ellipse max "+std::to_string(stats.maxOutsideEllipseDelta);
        message+=", ellipse annulus max "+std::to_string(stats.maxEllipseAnnulusDelta);
        throw std::runtime_error(message);
    }
}
TestGpuTarget MakeGpuTarget(unsigned width,unsigned height){
    TestGpuTarget output;D3D_FEATURE_LEVEL level{};
    const D3D_FEATURE_LEVEL levels[]={D3D_FEATURE_LEVEL_11_0};
    HRESULT hr=D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_HARDWARE,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,
        levels,1,D3D11_SDK_VERSION,&output.device,&level,&output.context);
    if(FAILED(hr))hr=D3D11CreateDevice(nullptr,D3D_DRIVER_TYPE_WARP,nullptr,D3D11_CREATE_DEVICE_BGRA_SUPPORT,
        levels,1,D3D11_SDK_VERSION,&output.device,&level,&output.context);
    Check(SUCCEEDED(hr)&&level>=D3D_FEATURE_LEVEL_11_0,"cannot create a test D3D11 device");
    D3D11_TEXTURE2D_DESC desc{};desc.Width=width;desc.Height=height;desc.MipLevels=1;desc.ArraySize=1;
    desc.Format=DXGI_FORMAT_B8G8R8A8_UNORM;desc.SampleDesc.Count=1;desc.Usage=D3D11_USAGE_DEFAULT;
    desc.BindFlags=D3D11_BIND_RENDER_TARGET|D3D11_BIND_SHADER_RESOURCE;
    Check(SUCCEEDED(output.device->CreateTexture2D(&desc,nullptr,&output.texture)),"cannot create the candidate BGRA8 terrain texture");
    return output;
}
std::vector<unsigned char> ReadGpuTarget(const TestGpuTarget& target,unsigned width,unsigned height){
    D3D11_TEXTURE2D_DESC desc{};target.texture->GetDesc(&desc);desc.Usage=D3D11_USAGE_STAGING;
    desc.BindFlags=0;desc.MiscFlags=0;desc.CPUAccessFlags=D3D11_CPU_ACCESS_READ;
    Microsoft::WRL::ComPtr<ID3D11Texture2D> staging;
    Check(SUCCEEDED(target.device->CreateTexture2D(&desc,nullptr,&staging)),"cannot create terrain parity readback buffer");
    target.context->CopyResource(staging.Get(),target.texture.Get());D3D11_MAPPED_SUBRESOURCE mapped{};
    Check(SUCCEEDED(target.context->Map(staging.Get(),0,D3D11_MAP_READ,0,&mapped)),"cannot map terrain parity readback");
    std::vector<unsigned char> output(static_cast<std::size_t>(width)*height*4);
    for(unsigned y=0;y<height;++y)
        std::memcpy(output.data()+static_cast<std::size_t>(y)*width*4,
                    static_cast<const unsigned char*>(mapped.pData)+static_cast<std::size_t>(y)*mapped.RowPitch,
                    static_cast<std::size_t>(width)*4);
    target.context->Unmap(staging.Get(),0);return output;
}
void CheckGpuParity(const WorldView& view,const TerrainFrame& legacy,const TestGpuTarget& target,
                    unsigned width,unsigned height,unsigned mapWidth,const char* message){
    TerrainFrame gpu;std::wstring error;
    CheckRender(RenderWorldTerrainToTexture(view,width,height,mapWidth,target.device.Get(),target.context.Get(),
                                            target.texture.Get(),&gpu,&error),error,message);
    Check(gpu.bgra.empty(),"GPU terrain path unexpectedly performed a color readback");
    Check(ReadGpuTarget(target,width,height)==legacy.bgra,"sRGB terrain color bytes changed in BGRA8_UNORM target copy");
    Check(gpu.triangles==legacy.triangles&&gpu.unitTriangles==legacy.unitTriangles&&gpu.modelUnits==legacy.modelUnits,
          "GPU target path changed terrain/unit mesh counts");
    Check(gpu.picking.indices==legacy.picking.indices&&gpu.picking.keys==legacy.picking.keys,
          "GPU target path changed integer ID raster or key table");
    Check(SameCenters(gpu.centers,legacy.centers)&&SameProjectedPlots(gpu.projectedPlots,legacy.projectedPlots),
          "GPU target path changed depth-tested centers or raster contour spans");
}
}

int wmain(int argc,wchar_t** argv){
    try{
        CheckWorldViewPixelComparatorNegativeCases();
        Check(argc==3||argc==4,"usage: world_terrain_renderer.exe <terrain-assets.bin> <capture-dir> [unit-assets.bin]");
        const std::filesystem::path packagePath(argv[1]),captureDir(argv[2]);
        std::filesystem::create_directories(captureDir);
        auto view=MakeView(packagePath.wstring());

        TerrainFrame frame;std::wstring error;
        error.clear();bool rendered=RenderWorldTerrain(view,1920,1080,1380,&frame,&error);
        CheckRender(rendered,error,"terrain render failed");
        Check(frame.triangles>0&&frame.bgra.size()==1920u*1080u*4u,"terrain geometry/color output is empty");
        Check(frame.picking.indices.size()==1920u*1080u&&HasColor(frame),"terrain color or picking output is empty");
        ValidateProjectedPlots(frame,1920,1080,1380);
        for(std::uint32_t y=0;y<1080;++y)for(std::uint32_t x=1380;x<1920;++x)
            Check(frame.picking.indices[static_cast<std::size_t>(y)*1920+x]==0,"terrain wrote IDs in the HUD-side area");
        const int centerIndex=4*9+4;
        Check(frame.centers.count(centerIndex)==1,"center plot projection anchor was not retained after pixel-ID verification");
        const auto anchor=frame.centers.at(centerIndex);
        const auto anchorX=static_cast<unsigned>(anchor.x),anchorY=static_cast<unsigned>(anchor.y);
        const auto anchorId=frame.picking.indices[static_cast<std::size_t>(anchorY)*1920+anchorX];
        Check(anchorId>0&&anchorId<=frame.picking.keys.size()&&
              frame.picking.keys[anchorId-1]==WorldViewHitKey::Plot(centerIndex),
              "returned center anchor pixel does not resolve to its plot ID");
        const TerrainProjection center{690.0f,540.0f};
        const auto cx=static_cast<unsigned>(center.x),cy=static_cast<unsigned>(center.y);
        const auto id=frame.picking.indices[static_cast<std::size_t>(cy)*1920+cx];
        Check(id>0&&id<=frame.picking.keys.size()&&frame.picking.keys[id-1]==WorldViewHitKey::Plot(centerIndex),
              "projected center does not resolve to its known visible plot");
        const auto forwardResolved=Resolved(frame);const auto forwardColor=frame.bgra;

        const auto gpuTarget=MakeGpuTarget(1920,1080);TerrainFrame gpuFrame;
        rendered=RenderWorldTerrainToTexture(view,1920,1080,1380,gpuTarget.device.Get(),gpuTarget.context.Get(),
                                               gpuTarget.texture.Get(),&gpuFrame,&error);
        CheckRender(rendered,error,"caller-device terrain GPU target render failed");
        Check(gpuFrame.bgra.empty(),"caller-device terrain GPU path returned a CPU color buffer");
        Check(ReadGpuTarget(gpuTarget,1920,1080)==forwardColor,
              "caller-device BGRA8_UNORM target differs from legacy sRGB color bytes");
        Check(gpuFrame.triangles==frame.triangles&&gpuFrame.unitTriangles==frame.unitTriangles&&
              gpuFrame.modelUnits==frame.modelUnits,"caller-device path changed original mesh/depth draw counts");
        Check(gpuFrame.picking.indices==frame.picking.indices&&gpuFrame.picking.keys==frame.picking.keys&&
              SameCenters(gpuFrame.centers,frame.centers)&&SameProjectedPlots(gpuFrame.projectedPlots,frame.projectedPlots),
              "caller-device path changed integer IDs, pixel-verified anchors, or exact contour spans");
        ValidateProjectedPlots(gpuFrame,1920,1080,1380);

        TerrainFrame retainedFailure;retainedFailure.triangles=123;retainedFailure.bgra={9,8,7};error.clear();
        const bool wrongSizeAccepted=RenderWorldTerrainToTexture(view,1919,1080,1380,gpuTarget.device.Get(),
            gpuTarget.context.Get(),gpuTarget.texture.Get(),&retainedFailure,&error);
        Check(!wrongSizeAccepted&&!error.empty()&&retainedFailure.triangles==123&&retainedFailure.bgra==std::vector<unsigned char>({9,8,7}),
              "caller GPU target resize mismatch was not rejected transactionally");
        const auto foreignTarget=MakeGpuTarget(1920,1080);error.clear();
        const bool wrongDeviceAccepted=RenderWorldTerrainToTexture(view,1920,1080,1380,foreignTarget.device.Get(),
            foreignTarget.context.Get(),gpuTarget.texture.Get(),&retainedFailure,&error);
        Check(!wrongDeviceAccepted&&!error.empty()&&retainedFailure.triangles==123&&retainedFailure.bgra==std::vector<unsigned char>({9,8,7}),
              "caller GPU target from a different device was not rejected transactionally");
        Check(ReadGpuTarget(gpuTarget,1920,1080)==forwardColor,
              "rejected caller target validation changed the last successfully rendered color bytes");
        std::cout<<"PASS_TERRAIN_GPU_TARGET_CONTRACT color_bytes_preserved id_projection_parity resized_and_foreign_targets_rejected\n";

        std::reverse(view.plots.begin(),view.plots.end());TerrainFrame reversed;
        rendered=RenderWorldTerrain(view,1920,1080,1380,&reversed,&error);
        CheckRender(rendered,error,"reversed terrain render failed");
        Check(Resolved(reversed)==forwardResolved,"reversed plot order changed resolved pixel IDs");
        Check(reversed.bgra==forwardColor,"reversed plot order changed terrain color output");

        auto flatHeightView=view;std::reverse(flatHeightView.plots.begin(),flatHeightView.plots.end());
        const auto flatPath=captureDir/L"terrain_mountain_height_removed.bin";
        auto flatPackage=ReadFile(packagePath);std::size_t cursor=16;const auto materialCount=Read32(flatPackage,12);
        for(std::uint32_t i=0;i<materialCount;++i)cursor+=12+Read32(flatPackage,cursor+8);
        const auto pieceCount=Read32(flatPackage,cursor);cursor+=4;bool changedMountain=false;
        for(std::uint32_t i=0;i<pieceCount;++i){const auto kind=Read32(flatPackage,cursor),bytes=Read32(flatPackage,cursor+4);const auto dds=cursor+8;
            if(kind==2){for(std::size_t pixel=0;pixel<128u*128u;++pixel){const auto pos=dds+128+pixel*8;
                    for(unsigned c=0;c<3;++c){flatPackage[pos+c*2]=0xC4;flatPackage[pos+c*2+1]=0x3B;}}
                changedMountain=true;}
            cursor=dds+bytes;}
        Check(changedMountain,"mountain height fixture was not found");WriteFile(flatPath,flatPackage);
        flatHeightView.terrainAssetsPath=flatPath.wstring();TerrainFrame withoutHeight;
        rendered=RenderWorldTerrain(flatHeightView,1920,1080,1380,&withoutHeight,&error);
        CheckRender(rendered,error,"flat mountain render failed");
        Check(withoutHeight.bgra!=reversed.bgra,"removing mountain relief did not alter rendered color frame");
        Check(Resolved(withoutHeight)!=Resolved(reversed),"removing mountain relief did not alter pixel picking result");

        auto hiddenA=MakeView(packagePath.wstring());hiddenA.plots={Plot(4,4,"",false,false,false,false)};
        hiddenA.plots[0].revealed=false;hiddenA.plots[0].continent=-1;hiddenA.plots[0].terrain.clear();
        TerrainFrame hiddenFrameA;rendered=RenderWorldTerrain(hiddenA,1920,1080,1380,&hiddenFrameA,&error);
        CheckRender(rendered,error,"hidden baseline render failed");
        auto hiddenB=hiddenA;hiddenB.plots[0].mountain=true;hiddenB.plots[0].hills=true;hiddenB.plots[0].water=true;
        hiddenB.plots[0].continent=3;hiddenB.plots[0].terrain="SECRET_DESERT";hiddenB.plots[0].feature="SECRET";
        TerrainFrame hiddenFrameB;rendered=RenderWorldTerrain(hiddenB,1920,1080,1380,&hiddenFrameB,&error);
        CheckRender(rendered,error,"hidden-secret render failed");
        Check(hiddenFrameA.bgra==hiddenFrameB.bgra&&hiddenFrameA.picking.indices==hiddenFrameB.picking.indices&&
              hiddenFrameA.picking.keys==hiddenFrameB.picking.keys,"unrevealed terrain facts changed output");
        Check(hiddenFrameA.projectedPlots.empty()&&hiddenFrameB.projectedPlots.empty(),
              "unrevealed plot metadata leaked through projected geometry");

        auto revealedHidden=MakeView(packagePath.wstring());revealedHidden.plots={Plot(4,4,"TERRAIN_GRASS",false)};
        TerrainFrame revealedFrame;rendered=RenderWorldTerrain(revealedHidden,1920,1080,1380,&revealedFrame,&error);
        CheckRender(rendered,error,"revealed but currently hidden plot render failed");
        Check(revealedFrame.picking.keys.empty()&&std::all_of(revealedFrame.picking.indices.begin(),revealedFrame.picking.indices.end(),
              [](std::uint32_t value){return value==0;}),"revealed-not-visible plot received a pick ID");
        Check(revealedFrame.projectedPlots.empty(),"revealed-but-not-visible plot received a projected geometry row");

        Scene scene{};WorldViewProjection projection{};std::wstring viewError;const auto pngPath=captureDir/L"world_terrain_fixture.png";
        const bool worldRendered=RenderWorldView(view,pngPath.wstring(),&scene,&viewError,&projection);
        CheckRender(worldRendered,viewError,"WorldView PNG composition failed");
        Check(std::filesystem::file_size(pngPath)>1024,"WorldView terrain PNG is unexpectedly small");
        Check(scene.pixelHits.indices.size()==1920u*1080u,"WorldView did not preserve terrain hit map");
        Check(projection.ready&&projection.cameraX==view.cameraX&&projection.cameraY==view.cameraY&&
              projection.gridWidth==view.gridWidth&&projection.gridHeight==view.gridHeight&&projection.mapWidth==1380,
              "WorldView projection metadata does not describe the rendered terrain frame");
        Check(SameProjectedPlots(projection.plots,reversed.projectedPlots),
              "WorldView projection rows differ from the exact terrain frame used for composition");
        ValidateProjectedPlots(reversed,1920,1080,static_cast<unsigned>(projection.mapWidth));
        for(std::uint32_t y=0;y<1080;++y)for(std::uint32_t x=1380;x<1920;++x)
            Check(scene.pixelHits.indices[static_cast<std::size_t>(y)*1920+x]==0,"WorldView HUD area contains terrain pick IDs");
        auto cityView=view;cityView.cities.push_back({17,0,4,4,L"Projection Test City","Projection Test City"});
        cityView.selectedCity=17;
        CheckWorldViewGpuParity(cityView,captureDir/L"world_view_gpu_legacy.png",captureDir/L"world_view_gpu.png",
                                gpuTarget,"full world/HUD GPU parity");
        std::cout<<"PASS_WORLD_VIEW_GPU_CONTRACT exact_hits_pixel_ids_city_spans_bounded_edge_png_difference\n";

        if(argc==4){
            auto unitsView=MakeView(packagePath.wstring());unitsView.tileWidth=112;
            for(auto& plot:unitsView.plots){plot.hills=false;plot.mountain=false;plot.water=false;plot.terrain="TERRAIN_GRASS";}
            TerrainFrame ground;rendered=RenderWorldTerrain(unitsView,1920,1080,1380,&ground,&error);
            CheckRender(rendered,error,"unit ground baseline failed");
            const auto originalUnitPackage=ReadFile(argv[3]);
            const bool animatedUnitPackage=originalUnitPackage.size()>=12&&
                std::memcmp(originalUnitPackage.data(),"ZSUNIT02",8)==0&&Read32(originalUnitPackage,8)==2;
            unitsView.unitAssetsPath=argv[3];WorldViewUnit unit{};
            unit.id=1;unit.owner=0;unit.x=unit.y=4;unit.name=L"Original Warrior";unit.facingDirection=0;
            unit.unitArtInfoTag="ART_DEF_UNIT__WARRIOR";unit.type="UNIT_WARRIOR";unitsView.units.push_back(unit);
            TerrainFrame modeled;rendered=RenderWorldTerrain(unitsView,1920,1080,1380,&modeled,&error);
            CheckRender(rendered,error,"original Warrior render failed");
            Check(modeled.modelUnits==1&&modeled.unitTriangles>1000,"original formation was not drawn");
            Check(modeled.bgra!=ground.bgra,"original unit geometry did not affect the color target");
            Check(modeled.picking.indices==ground.picking.indices&&modeled.picking.keys==ground.picking.keys&&
                  SameProjectedPlots(modeled.projectedPlots,ground.projectedPlots),"unit geometry changed ground ID/projection semantics");
            CheckGpuParity(unitsView,modeled,gpuTarget,1920,1080,1380,
                           "caller-device original Warrior parity render failed");
            Scene unitScene;rendered=RenderWorldView(unitsView,(captureDir/L"original_warrior.png").wstring(),&unitScene,&error);
            CheckRender(rendered,error,"original Warrior composition failed");
            auto unitCityView=unitsView;unitCityView.cities.push_back({17,0,4,4,L"Warrior City","Warrior City"});
            unitCityView.selectedCity=17;
            auto markerOnlyView=unitCityView;markerOnlyView.unitAssetsPath.clear();
            CheckWorldViewGpuParity(markerOnlyView,captureDir/L"warrior_marker_no_model_gpu_legacy.png",
                                    captureDir/L"warrior_marker_no_model_gpu.png",gpuTarget,
                                    "unit marker ellipse without model GPU parity");
            CheckWorldViewGpuParity(unitCityView,captureDir/L"original_warrior_gpu_legacy.png",
                                    captureDir/L"original_warrior_gpu.png",gpuTarget,
                                    "original unit plus full world/HUD GPU parity");
            const auto unitAnimationT0=ReadPngBgra(captureDir/L"original_warrior_gpu_legacy.png",1920,1080);
            if(animatedUnitPackage){
                const auto renderAnimation=[&](double seconds,const wchar_t* legacyName,const wchar_t* gpuName,const char* label){
                    auto animatedView=unitCityView;animatedView.animationSeconds=seconds;TerrainFrame animatedFrame;
                    rendered=RenderWorldTerrain(animatedView,1920,1080,1380,&animatedFrame,&error);
                    CheckRender(rendered,error,"original unit animation frame failed");
                    Check(animatedFrame.modelUnits==modeled.modelUnits&&animatedFrame.unitTriangles==modeled.unitTriangles,
                          "animation changed original model or triangle counts");
                    Check(animatedFrame.picking.indices==modeled.picking.indices&&animatedFrame.picking.keys==modeled.picking.keys&&
                          SameProjectedPlots(animatedFrame.projectedPlots,modeled.projectedPlots),
                          "animation changed terrain IDs or plot projection");
                    CheckGpuParity(animatedView,animatedFrame,gpuTarget,1920,1080,1380,
                                   "same-device original unit animation parity failed");
                    CheckWorldViewGpuParity(animatedView,captureDir/legacyName,captureDir/gpuName,gpuTarget,label);
                    return ReadPngBgra(captureDir/legacyName,1920,1080);
                };
                const auto animationHalf=renderAnimation(0.5,L"warrior_animation_t05_legacy.png",
                    L"warrior_animation_t05_gpu.png","original unit animation t=0.5");
                const auto animationOne=renderAnimation(1.0,L"warrior_animation_t1_legacy.png",
                    L"warrior_animation_t1_gpu.png","original unit animation t=1");
                Check(animationHalf!=unitAnimationT0,"original IdleA at t=0.5 did not change rendered unit pixels");
                Check(animationOne!=unitAnimationT0,"original IdleA at t=1 did not change rendered unit pixels");
                const double duration=FirstUnitAnimationDuration(originalUnitPackage);
                const auto animationLoop=renderAnimation(duration,L"warrior_animation_loop_legacy.png",
                    L"warrior_animation_loop_gpu.png","original unit animation loop duration");
                Check(animationLoop==unitAnimationT0,"original IdleA loop duration did not return exactly to t=0 pixels");
                std::cout<<"PASS_ORIGINAL_WARRIOR_ANIMATION_CONTRACT t05_changed t1_changed loop_exact duration="
                         <<duration<<"\n";
            }
            unitsView.units[0].facingDirection=1;TerrainFrame turned;
            rendered=RenderWorldTerrain(unitsView,1920,1080,1380,&turned,&error);CheckRender(rendered,error,"turned Warrior failed");
            Check(turned.bgra!=modeled.bgra,"SDK facing did not alter unit geometry");unitsView.units[0].facingDirection=0;
            for(unsigned mode=0;mode<4;++mode){
                auto unsupported=unitsView;
                if(mode==0)unsupported.units[0].embarked=true;
                if(mode==1)unsupported.units[0].unitArtInfoCulturalVariation=true;
                if(mode==2)unsupported.units[0].unitArtInfoEraVariation=true;
                if(mode==3)unsupported.units[0].unitArtInfoTag="ART_DEF_MISSING";
                TerrainFrame skipped;rendered=RenderWorldTerrain(unsupported,1920,1080,1380,&skipped,&error);
                CheckRender(rendered,error,"unsupported unit art filtering failed");
                Check(skipped.modelUnits==0&&skipped.bgra==ground.bgra,"unsupported unit used the base land art");
            }
            auto hidden=unitsView;hidden.plots[40].visible=false;
            TerrainFrame hiddenUnit;rendered=RenderWorldTerrain(hidden,1920,1080,1380,&hiddenUnit,&error);
            CheckRender(rendered,error,"hidden unit frame failed");hidden.units.clear();TerrainFrame hiddenGround;
            rendered=RenderWorldTerrain(hidden,1920,1080,1380,&hiddenGround,&error);CheckRender(rendered,error,"hidden ground failed");
            Check(hiddenUnit.modelUnits==0&&hiddenUnit.bgra==hiddenGround.bgra,"hidden unit leaked through model rendering");

            auto lowered=originalUnitPackage;
            const auto staticEnd=StaticUnitPackageEnd(lowered);
            if(animatedUnitPackage){lowered.resize(staticEnd);std::memcpy(lowered.data(),"ZSUNIT01",8);lowered[8]=1;lowered[9]=lowered[10]=lowered[11]=0;}
            std::size_t pos=16;const unsigned textures=Read32(lowered,12);
            for(unsigned t=0;t<textures;++t)pos+=4+Read32(lowered,pos);
            const unsigned arts=Read32(lowered,pos);pos+=4;
            for(unsigned a=0;a<arts;++a){pos+=4+Read32(lowered,pos);const unsigned meshes=Read32(lowered,pos);pos+=4;
                for(unsigned m=0;m<meshes;++m){const unsigned vc=Read32(lowered,pos+4),ic=Read32(lowered,pos+8);pos+=12;
                    for(unsigned v=0;v<vc;++v){float y=0;std::memcpy(&y,lowered.data()+pos+v*32+4,4);y-=1;
                        std::memcpy(lowered.data()+pos+v*32+4,&y,4);}
                    pos+=static_cast<std::size_t>(vc)*32+static_cast<std::size_t>(ic)*4;
                }
            }
            Check(pos==lowered.size(),"unit fixture parser did not reach package end");
            const auto belowPath=captureDir/L"unit_below_ground.bin";WriteFile(belowPath,lowered);
            auto below=unitsView;below.unitAssetsPath=belowPath.wstring();TerrainFrame occluded;
            rendered=RenderWorldTerrain(below,1920,1080,1380,&occluded,&error);CheckRender(rendered,error,"below-ground fixture failed");
            Check(occluded.modelUnits==1&&occluded.bgra==ground.bgra,"terrain depth did not occlude the below-ground model");
            CheckGpuParity(below,occluded,gpuTarget,1920,1080,1380,
                           "caller-device depth-occluded unit parity render failed");
            auto invalid=originalUnitPackage;const auto invalidStaticEnd=StaticUnitPackageEnd(invalid);
            Check(invalidStaticEnd>=4,"unit static index fixture has no index payload");
            std::fill(invalid.begin()+static_cast<std::ptrdiff_t>(invalidStaticEnd-4),
                      invalid.begin()+static_cast<std::ptrdiff_t>(invalidStaticEnd),static_cast<unsigned char>(0xff));
            const auto invalidPath=std::filesystem::path(argv[3]).parent_path()/L"unit_bad_index.bin";WriteFile(invalidPath,invalid);
            auto badUnit=unitsView;badUnit.unitAssetsPath=invalidPath.wstring();TerrainFrame retained=modeled;
            error.clear();Check(!RenderWorldTerrain(badUnit,1920,1080,1380,&retained,&error)&&!error.empty(),"out-of-range unit index was accepted");
            Check(retained.bgra==modeled.bgra,"failed unit package replaced caller's prior frame");
            std::cout<<"PASS_ORIGINAL_WARRIOR_MODEL_CONTRACT triangles="<<modeled.unitTriangles<<"\n";
        }

        auto bad=MakeView(captureDir/L"missing-package.bin");TerrainFrame invalidFrame;
        error.clear();const bool badPackage=RenderWorldTerrain(bad,1920,1080,1380,&invalidFrame,&error);
        Check(!badPackage&&!error.empty(),"invalid terrain package did not return false plus error");
        error.clear();Check(!RenderWorldTerrain(view,1920,1080,1921,&invalidFrame,&error)&&!error.empty(),
                            "invalid projection boundary did not return false plus error");
        auto invalidView=view;invalidView.gridWidth=0;Scene invalidScene{};
        const bool badView=RenderWorldView(invalidView,pngPath.wstring(),&invalidScene,&viewError);
        Check(!badView&&!viewError.empty(),
              "invalid WorldView DTO did not return false plus error");

        std::cout<<"PASS_TERRAIN_COMPONENT_CONTRACT\n"<<"triangles="<<frame.triangles
                 <<" visible_keys="<<frame.picking.keys.size()<<" center="<<center.x<<","<<center.y
                 <<" png="<<std::filesystem::path(pngPath).string()<<"\n";
        return 0;
    }catch(const std::exception& ex){std::cerr<<"FAIL_TERRAIN_COMPONENT_CONTRACT="<<ex.what()<<"\n";return 1;}
}
