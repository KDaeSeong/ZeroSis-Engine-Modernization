#include "../Source/Presentation/WorldViewRenderer.h"

#include <Windows.h>
#include <wincodec.h>
#include <wrl/client.h>
#include <algorithm>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <stdexcept>
#include <string>
#include <vector>

using namespace ZeroSisPresentation;

namespace {
void Check(bool ok,const char* message){if(!ok)throw std::runtime_error(message);}

void CheckRender(bool result,const std::wstring& error,const char* label){
    if(result)return;
    std::string message=label;message+=": ";
    for(const wchar_t ch:error)message+=ch>=0&&ch<128?static_cast<char>(ch):'?';
    throw std::runtime_error(message);
}

WorldView MakeView(){
    WorldView view{};view.gridWidth=9;view.gridHeight=9;view.turn=1;view.activePlayer=0;
    view.wrapX=false;view.wrapY=false;view.cameraX=4;view.cameraY=4;view.tileWidth=56;
    view.plots.reserve(81);
    for(int y=0;y<9;++y)for(int x=0;x<9;++x){
        WorldViewPlot plot{};plot.index=y*9+x;plot.x=x;plot.y=y;plot.revealed=true;plot.visible=true;
        plot.terrain="TERRAIN_GRASS";plot.continent=4;view.plots.push_back(std::move(plot));
    }
    view.plots[3*9+4].visible=false;
    return view;
}

WorldViewUnit HiddenOwnedUnit(bool selected=false){
    WorldViewUnit unit{};unit.id=17;unit.owner=0;unit.x=4;unit.y=3;unit.moves=1;unit.damage=0;
    unit.selected=selected;unit.name=L"Roster unit";unit.maxHitPoints=100;unit.type="UNIT_WARRIOR";
    return unit;
}

bool HasHit(const Scene& scene,std::uint64_t key){
    return std::any_of(scene.hits.begin(),scene.hits.end(),[&](const HitRecord& hit){return hit.controlKey==key;});
}

std::vector<unsigned char> ReadPngBgra(const std::filesystem::path& path){
    const HRESULT init=CoInitializeEx(nullptr,COINIT_MULTITHREADED);
    Check(SUCCEEDED(init)||init==RPC_E_CHANGED_MODE,"COM initialization failed for PNG verification");
    struct Uninitialize{HRESULT hr;~Uninitialize(){if(SUCCEEDED(hr))CoUninitialize();}} uninit{init};
    Microsoft::WRL::ComPtr<IWICImagingFactory> factory;
    Check(SUCCEEDED(CoCreateInstance(CLSID_WICImagingFactory,nullptr,CLSCTX_INPROC_SERVER,
          IID_PPV_ARGS(&factory))),"WIC factory creation failed");
    Microsoft::WRL::ComPtr<IWICBitmapDecoder> decoder;
    Check(SUCCEEDED(factory->CreateDecoderFromFilename(path.c_str(),nullptr,GENERIC_READ,
          WICDecodeMetadataCacheOnLoad,&decoder)),"PNG decode failed");
    Microsoft::WRL::ComPtr<IWICBitmapFrameDecode> frame;
    Check(SUCCEEDED(decoder->GetFrame(0,&frame)),"PNG frame read failed");
    UINT width=0,height=0;
    Check(SUCCEEDED(frame->GetSize(&width,&height))&&width==1920&&height==1080,"PNG dimensions differ");
    Microsoft::WRL::ComPtr<IWICFormatConverter> converter;
    Check(SUCCEEDED(factory->CreateFormatConverter(&converter)),"WIC converter creation failed");
    Check(SUCCEEDED(converter->Initialize(frame.Get(),GUID_WICPixelFormat32bppBGRA,
          WICBitmapDitherTypeNone,nullptr,0,WICBitmapPaletteTypeCustom)),"PNG BGRA conversion failed");
    std::vector<unsigned char> pixels(static_cast<std::size_t>(width)*height*4);
    Check(SUCCEEDED(converter->CopyPixels(nullptr,width*4,static_cast<UINT>(pixels.size()),pixels.data())),
          "PNG pixels could not be copied");
    return pixels;
}

bool EqualMapCrop(const std::vector<unsigned char>& left,const std::vector<unsigned char>& right){
    constexpr unsigned width=1920,height=1080,mapWidth=1380;
    if(left.size()!=static_cast<std::size_t>(width)*height*4||right.size()!=left.size())return false;
    for(unsigned y=0;y<height;++y){
        const auto offset=static_cast<std::size_t>(y)*width*4;
        if(!std::equal(left.begin()+offset,left.begin()+offset+mapWidth*4,right.begin()+offset))return false;
    }
    return true;
}

bool SameHits(const std::vector<HitRecord>& left,const std::vector<HitRecord>& right){
    if(left.size()!=right.size())return false;
    for(std::size_t i=0;i<left.size();++i){
        if(left[i].controlKey!=right[i].controlKey)return false;
        for(unsigned j=0;j<4;++j)if(left[i].bounds[j]!=right[i].bounds[j])return false;
    }
    return true;
}

using PixelRect=std::array<int,4>;
// Bounds in the existing 1920x1080 output. They cover only the temporary
// selected-unit captions, Skip, Found, and action-list area respectively.
constexpr PixelRect UnitCaptionPixels{1401,180,1896,276};
constexpr PixelRect SkipPixels{1644,468,1875,534};
constexpr PixelRect FoundPixels{1401,543,1632,609};
constexpr PixelRect UnitActionPixels{1401,834,1896,1065};
constexpr PixelRect SuppressedPixels[]{UnitCaptionPixels,SkipPixels,FoundPixels,UnitActionPixels};

bool IsSuppressedPixel(int x,int y){
    return std::any_of(std::begin(SuppressedPixels),std::end(SuppressedPixels),[&](const PixelRect& rect){
        return x>=rect[0]&&x<rect[2]&&y>=rect[1]&&y<rect[3];
    });
}

std::size_t CheckSuppressedPixels(const std::vector<unsigned char>& before,
                                const std::vector<unsigned char>& after,const PixelRect& rect){
    std::size_t changed=0;
    for(int y=rect[1];y<rect[3];++y){
        // This untouched strip lies inside the HUD background but left of
        // every caption/button. Compare actual rendered background pixels.
        const auto background=(static_cast<std::size_t>(y)*1920+1392)*4;
        for(int x=rect[0];x<rect[2];++x){
            const auto pixel=(static_cast<std::size_t>(y)*1920+static_cast<unsigned>(x))*4;
            Check(std::equal(after.begin()+pixel,after.begin()+pixel+4,after.begin()+background),
                  "original UnitPanel left temporary caption/button pixels behind");
            if(!std::equal(before.begin()+pixel,before.begin()+pixel+4,after.begin()+pixel))++changed;
        }
    }
    Check(changed>0,"suppression pixel fixture did not exercise visible temporary UI");
    return changed;
}

void CheckPreservedPixels(const std::vector<unsigned char>& before,const std::vector<unsigned char>& after){
    Check(EqualMapCrop(before,after),"original UnitPanel changed the map viewport or map pixels");
    for(int y=0;y<1080;++y)for(int x=0;x<1920;++x){
        if(IsSuppressedPixel(x,y))continue;
        const auto pixel=(static_cast<std::size_t>(y)*1920+static_cast<unsigned>(x))*4;
        Check(std::equal(before.begin()+pixel,before.begin()+pixel+4,after.begin()+pixel),
              "original UnitPanel changed retained city/status/navigation/control pixels");
    }
}

bool IsSuppressedHit(const WorldView& view,std::uint64_t key){
    if(key==WorldViewHitKey::Action(WorldViewAction::Skip)||
       key==WorldViewHitKey::Action(WorldViewAction::Found)||
       key==WorldViewHitKey::Action(WorldViewAction::UnitActionsPrevious)||
       key==WorldViewHitKey::Action(WorldViewAction::UnitActionsNext))return true;
    return std::any_of(view.unitActions.begin(),view.unitActions.end(),[&](const WorldViewUnitAction& action){
        return key==WorldViewHitKey::UnitAction(action.index);
    });
}

void CheckSuppressedHits(const WorldView& view,const Scene& fallback,const Scene& original,std::size_t expectedRemoved){
    std::vector<HitRecord> retained;
    for(const auto& hit:fallback.hits)if(!IsSuppressedHit(view,hit.controlKey))retained.push_back(hit);
    Check(fallback.hits.size()-retained.size()==expectedRemoved,"fixture omitted a temporary action or page hit");
    Check(SameHits(retained,original.hits),"suppression changed retained hit order/bounds or kept a temporary hit");
    const WorldViewAction preserved[]{WorldViewAction::NextUnit,WorldViewAction::EndTurn,WorldViewAction::Save,
        WorldViewAction::Close,WorldViewAction::Research,WorldViewAction::Production,WorldViewAction::PanLeft,
        WorldViewAction::PanRight,WorldViewAction::PanUp,WorldViewAction::PanDown};
    for(const auto action:preserved)Check(HasHit(original,WorldViewHitKey::Action(action)),
        "original UnitPanel removed an unrelated navigation or session control");
    // Occupied plots deliberately route to their owned-unit hit in this
    // renderer. Use the adjacent empty visible plot for movement selection.
    Check(HasHit(fallback,WorldViewHitKey::Plot(4*9+5))&&HasHit(original,WorldViewHitKey::Plot(4*9+5)),
          "original UnitPanel removed the adjacent visible plot selection hit");
    Check(HasHit(original,WorldViewHitKey::OwnedUnit(17)),"original UnitPanel removed the selected owned-unit hit");
    Check(HasHit(original,WorldViewHitKey::OwnedCity(23)),"original UnitPanel removed the owned-city hit");
}

void Render(const WorldView& view,const std::filesystem::path& path,Scene* scene,const char* label){
    std::wstring error;
    CheckRender(RenderWorldView(view,path.wstring(),scene,&error),error,label);
}

void ExpectRejected(const WorldView& view,const std::filesystem::path& path,const char* label){
    Scene scene{};std::wstring error;
    Check(!RenderWorldView(view,path.wstring(),&scene,&error)&&!error.empty(),label);
}

void VerifyUnitPanelSuppression(const std::filesystem::path& output){
    auto view=MakeView();
    Check(!view.originalUnitPanel,"WorldView no longer defaults to the temporary UnitPanel fallback");
    auto unit=HiddenOwnedUnit(true);unit.y=4;unit.moves=2;unit.damage=23;unit.name=L"전사";
    view.units.push_back(unit);
    WorldViewCity city{};city.id=23;city.owner=0;city.x=3;city.y=4;city.name=L"서울";
    view.cities.push_back(city);view.selectedCity=city.id;view.status=L"선택 전환 검증";
    for(int i=0;i<13;++i)view.unitActions.push_back({100+i,L"행동 "+std::to_wstring(i)});
    view.unitActionPage=1;

    const auto fallbackPath=output/L"unit-panel-fallback.png",originalPath=output/L"unit-panel-original.png";
    Scene fallback{},original{};Render(view,fallbackPath,&fallback,"temporary unit HUD render failed");
    const auto fallbackPixels=ReadPngBgra(fallbackPath);
    Check(HasHit(fallback,WorldViewHitKey::Action(WorldViewAction::UnitActionsPrevious))&&
          HasHit(fallback,WorldViewHitKey::Action(WorldViewAction::UnitActionsNext)),
          "middle action page did not expose both paging controls");
    for(int i=106;i<112;++i)Check(HasHit(fallback,WorldViewHitKey::UnitAction(i)),
        "middle action page did not expose all six action hits");

    view.originalUnitPanel=true;Render(view,originalPath,&original,"original unit-panel suppression render failed");
    const auto originalPixels=ReadPngBgra(originalPath);
    CheckSuppressedHits(view,fallback,original,10);
    CheckPreservedPixels(fallbackPixels,originalPixels);
    std::size_t changed=0;
    for(const auto& rect:SuppressedPixels)changed+=CheckSuppressedPixels(fallbackPixels,originalPixels,rect);

    // A disappearing retained panel must restore the exact prior fallback,
    // including action-page controls and every map/navigation hit.
    view.originalUnitPanel=false;Scene restored{};const auto restoredPath=output/L"unit-panel-restored.png";
    Render(view,restoredPath,&restored,"unit-panel fallback restoration render failed");
    Check(ReadPngBgra(restoredPath)==fallbackPixels&&SameHits(restored.hits,fallback.hits),
          "disappearing original UnitPanel did not restore byte-identical fallback pixels and ordered hits");

    // The instruction shown for an empty action catalogue is also temporary.
    view.unitActions.clear();view.unitActionPage=0;
    const auto emptyPath=output/L"unit-panel-empty-fallback.png",emptyOriginalPath=output/L"unit-panel-empty-original.png";
    Scene empty{},emptyOriginal{};Render(view,emptyPath,&empty,"empty temporary unit HUD render failed");
    view.originalUnitPanel=true;Render(view,emptyOriginalPath,&emptyOriginal,"empty original unit-panel render failed");
    const auto emptyPixels=ReadPngBgra(emptyPath),emptyOriginalPixels=ReadPngBgra(emptyOriginalPath);
    CheckSuppressedHits(view,empty,emptyOriginal,2);
    CheckPreservedPixels(emptyPixels,emptyOriginalPixels);
    CheckSuppressedPixels(emptyPixels,emptyOriginalPixels,UnitActionPixels);
    std::cout<<"PASS_WORLD_VIEW_UNIT_PANEL_SUPPRESSION false_true_false_ordered_hits_map_pixels_preserved "
             <<"selected_captions_found_skip_actions_pages_and_empty_notice_removed changed_pixels="<<changed<<"\n";
}
}

int wmain(int argc,wchar_t** argv){
    std::filesystem::path output;
    try{
        Check(argc==2,"expected one private capture directory");
        output=argv[1];std::filesystem::create_directories(output);
        const auto basePath=output/L"base.png",hiddenPath=output/L"hidden-owned.png",selectedPath=output/L"selected-hidden-owned.png";

        const auto base=MakeView();Scene baseScene{};Render(base,basePath,&baseScene,"visible baseline render failed");
        auto hidden=base;hidden.units.push_back(HiddenOwnedUnit());Scene hiddenScene{};
        Render(hidden,hiddenPath,&hiddenScene,"hidden owned roster render failed");
        const auto basePixels=ReadPngBgra(basePath),hiddenPixels=ReadPngBgra(hiddenPath);
        Check(basePixels==hiddenPixels,"unselected hidden owned unit changed visible world/HUD pixels");
        Check(!HasHit(hiddenScene,WorldViewHitKey::OwnedUnit(17)),"hidden owned unit received a map hit record");
        Check(!HasHit(hiddenScene,WorldViewHitKey::Plot(3*9+4)),"currently hidden plot received a map hit record");
        Check(hiddenScene.pixelHits.indices.empty()&&hiddenScene.pixelHits.keys.empty(),
              "non-terrain hidden unit unexpectedly created pixel picking data");

        auto selected=hidden;selected.units[0].selected=true;selected.unitActions.push_back({0,L"Unit action"});
        Scene selectedScene{};Render(selected,selectedPath,&selectedScene,"selected hidden owned unit render failed");
        const auto selectedPixels=ReadPngBgra(selectedPath);
        Check(hiddenPixels!=selectedPixels,"selected hidden unit did not update the owned-unit HUD");
        Check(EqualMapCrop(basePixels,selectedPixels),"selected hidden unit changed map pixels or drew a fogged flag");
        Check(!HasHit(selectedScene,WorldViewHitKey::OwnedUnit(17)),"selected hidden unit received a map hit record");
        Check(HasHit(selectedScene,WorldViewHitKey::UnitAction(0)),"selected hidden unit lost its original action-panel hit");

        auto hiddenForeign=base;WorldViewUnit foreign=HiddenOwnedUnit();foreign.owner=1;foreign.selected=false;
        hiddenForeign.units.push_back(foreign);
        ExpectRejected(hiddenForeign,output/L"hidden-foreign.png","hidden foreign unit was accepted by WorldView validation");

        auto missingPlot=hidden;missingPlot.plots.erase(missingPlot.plots.begin()+3*9+4);
        ExpectRejected(missingPlot,output/L"missing-unit-plot.png","unit without a captured map coordinate was accepted");

        auto invalidId=hidden;invalidId.units[0].id=-1;
        ExpectRejected(invalidId,output/L"invalid-unit-id.png","negative unit ID was accepted");

        VerifyUnitPanelSuppression(output);

        std::filesystem::remove_all(output);
        std::cout<<"PASS_WORLD_VIEW_VISIBILITY hidden_owned_roster_selected_hud_map_pixels_and_hits_filtered hidden_foreign_missing_plot_invalid_id_rejected\n";
        return 0;
    }catch(const std::exception& ex){
        std::cerr<<"FAIL_WORLD_VIEW_VISIBILITY="<<ex.what()<<"\n";
        return 1;
    }
}
