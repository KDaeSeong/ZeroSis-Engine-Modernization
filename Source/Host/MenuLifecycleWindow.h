#pragma once
#if defined(ZEROSIS_UI_WINDOW_PRESENTATION)
#include "MenuLifecycleRetirement.h"
#include "MenuFrontEndAssets.h"
#include "MenuFrontEndOptionsView.h"
#include "MenuReplayInputBatch.h"
#include "MenuResolutionPreviewClock.h"
#include "../Presentation/BitmapWindow.h"
#include <CvLocalization.h>
#include <functional>

namespace ZeroSisHost {
struct MenuLifecycleRanking final {int threshold=0;std::wstring leader;};
enum class MenuLifecycleFrontEndChoice { Exit,StartCurrentSetup };
struct MenuFrontEndHooks final {
    std::shared_ptr<const MenuFrontEndAssets> assets;
    std::shared_ptr<MenuOptionsSession> options;
    std::function<MenuOptionsValues(ZeroSisPresentation::BitmapWindow&,const MenuOptionsValues&)> applyOptions;
    std::function<void(const MenuOptionsValues&)> persistOptions;
    std::function<ZeroSisPresentation::Scene(const MenuFrontEndAssets&)> replayScene;
    std::function<bool(const ZeroSisPresentation::BitmapInputEvent&)> replayInput;
    std::function<bool(double)> replayAdvance;
    std::function<bool(bool)> replayPointerCapture;
};
namespace MenuLifecycleWindowDetail {
inline std::wstring Wide(const std::string& text){
    if(text.empty())return {};
    const int size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),nullptr,0);
    if(size<=0)throw std::runtime_error("Menu text is not UTF-8");
    std::wstring result(static_cast<std::size_t>(size),L'\0');
    if(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),static_cast<int>(text.size()),&result[0],size)!=size)
        throw std::runtime_error("Menu text conversion failed");
    return result;
}
inline std::wstring Localized(const char* key){
    auto value=Localization::Lookup(key);const char* raw=value.toUTF8();
    if(!raw || !*raw || std::strcmp(raw,key)==0)throw std::runtime_error(std::string("Missing menu localization: ")+key);
    return Wide(raw);
}
inline std::wstring SourceLabel(std::string key){
    // The selected stock XML has one {KEY:upper} caption. Its Korean release
    // localization is retained; the wrapper is formatting, not part of the key.
    if(key.size()>2 && key.front()=='{' && key.back()=='}'){
        key=key.substr(1,key.size()-2);const auto colon=key.find(':');if(colon!=std::string::npos)key.resize(colon);
    }
    return key.empty()?std::wstring():Localized(key.c_str());
}
inline std::shared_ptr<const MenuFrontEndAssets> DefaultAssets(){
    std::vector<wchar_t> path(32768);const DWORD size=GetModuleFileNameW(nullptr,path.data(),static_cast<DWORD>(path.size()));
    if(!size || size>=path.size())throw std::runtime_error("Cannot locate the owned front-end assets");
    const std::wstring executable(path.data(),size);const auto slash=executable.find_last_of(L"\\/");
    if(slash==std::wstring::npos)throw std::runtime_error("Front-end executable path has no directory");
    return MenuFrontEndAssets::Load(executable.substr(0,slash)+L"\\UIFrontEnd");
}
inline ZeroSisPresentation::Scene OriginalPage(const MenuFrontEndAssets& assets,MenuFrontEndPage page,bool hasCurrentSetup,std::uint64_t hovered,bool hasOptions=false){
    auto scene=assets.BuildPage(page,hasCurrentSetup,hovered,[](const std::string& key){return SourceLabel(key);},
        L"\ud604\uc7ac \uc124\uc815\uc73c\ub85c \uc0c8 \uac8c\uc784",hasOptions);
    if(page==MenuFrontEndPage::ExitConfirm)
        assets.Text(scene,0,Localized("TXT_KEY_MENU_EXIT_WARN"),740,434,440,65,MenuFrontEndTextAlign::Center);
    else{
        assets.Text(scene,0,L"ZeroSis'",40,1000,300,35,MenuFrontEndTextAlign::Left,20);
        assets.Text(scene,0,L"\ud750\ub9b0 \ud56d\ubaa9\uc740 \uc544\uc9c1 \uc81c\uacf5\ud558\uc9c0 \uc54a\uc2b5\ub2c8\ub2e4.",540,1000,840,35,MenuFrontEndTextAlign::Center,20);
    }
    return scene;
}
}

// Entered only after the old gameplay window and GameCore are gone. Original
// artwork/fonts do not activate the retail SDK-dependent FrontEnd callbacks.
inline MenuLifecycleFrontEndChoice RunMenuLifecycleFrontEnd(bool hasCurrentSetup,
    const std::shared_ptr<const MenuLifecycleEndGame>& endGame,const std::vector<MenuLifecycleRanking>& rankings,
    const MenuFrontEndHooks& hooks=MenuFrontEndHooks{}){
    using namespace ZeroSisPresentation;using namespace MenuLifecycleWindowDetail;
    enum class Page { Main,SinglePlayer,ExitConfirm,Results,Ranking,Replay,Options };
    const auto assets=hooks.assets?hooks.assets:DefaultAssets();
    if(bool(hooks.replayScene)!=bool(hooks.replayInput) || bool(hooks.replayScene)!=bool(hooks.replayAdvance) ||
       bool(hooks.replayScene)!=bool(hooks.replayPointerCapture))
        throw std::logic_error("Replay presentation hooks require one complete owned controller");
    Page page=endGame?Page::Results:Page::Main,exitParent=Page::Main;
    BitmapWindow window;bool created=false,redraw=true;std::wstring error;std::size_t rankingPage=0;std::uint64_t hovered=0;
    MenuFrontEndOptionsModel options(hooks.options,
        hooks.applyOptions?MenuOptionsSession::ApplyBackend([&](const MenuOptionsValues& value){return hooks.applyOptions(window,value);}):MenuOptionsSession::ApplyBackend{},hooks.persistOptions);
    if(assets->Extended())ConfigureOriginalFrontEndOptions(*assets,options);
    const bool hasOptions=assets->Extended() && options.Available();std::wstring optionsError;
    const auto finishOptions=[&](){
        if(options.Opened())return;
        page=Page::Main;optionsError.clear();
        if(options.LastResult()==MenuFrontEndOptionsModel::Result::ApplyFailed)
            optionsError=L"\uc124\uc815\uc744 \uc801\uc6a9\ud558\uc9c0 \ubabb\ud588\uc2b5\ub2c8\ub2e4. \uc774\uc804 \uac12\uc744 \uc720\uc9c0\ud569\ub2c8\ub2e4.";
        else if(options.LastResult()==MenuFrontEndOptionsModel::Result::RollbackFailed)
            optionsError=L"\uc124\uc815 \ubcf5\uad6c\uac00 \uc2e4\ud328\ud588\uc2b5\ub2c8\ub2e4. \uc8fc \uba54\ub274\ub97c \ub2eb\uace0 \ub2e4\uc2dc \uc2e4\ud589\ud574 \uc8fc\uc2ed\uc2dc\uc624.";
        hovered=0;
    };
    const std::wstring mainLabel=Localized("TXT_KEY_MENU_EXIT_TO_MAIN");ULONGLONG previousTick=GetTickCount64();
    MenuResolutionPreviewClock resolutionClock;
    while(true){
        const auto tick=GetTickCount64();const double realElapsed=static_cast<double>(tick-previousTick)/1000.0;
        const double elapsed=(std::min)(0.25,realElapsed);previousTick=tick;
        // Keep the post-apply confirmation origin separate from animation time.
        double previewElapsed=0;
        if(resolutionClock.Sample(tick,page==Page::Options && options.ResolutionPreviewActive(),&previewElapsed) &&
           options.AdvanceResolutionPreview(previewElapsed)){finishOptions();redraw=true;}
        if(hooks.replayPointerCapture && hooks.replayPointerCapture(page==Page::Replay && created && window.HasControlDragCapture()))redraw=true;
        if(page==Page::Replay && created && hooks.replayInput){
            const auto pointer=window.CurrentPointerInput();
            if(pointer.sceneGeneration==window.SceneGeneration() && hooks.replayInput(pointer))redraw=true;
        }
        if(page==Page::Replay && hooks.replayAdvance && hooks.replayAdvance(elapsed))redraw=true;
        if(redraw){
            Scene scene;
            if(page==Page::Main || page==Page::SinglePlayer || page==Page::ExitConfirm){
                const auto original=page==Page::Main?MenuFrontEndPage::Main:
                    page==Page::SinglePlayer?MenuFrontEndPage::SinglePlayer:MenuFrontEndPage::ExitConfirm;
                scene=OriginalPage(*assets,original,hasCurrentSetup,hovered,hasOptions && options.Available());
                if(page==Page::Main && !optionsError.empty())assets->Text(scene,0,optionsError,540,910,840,65,MenuFrontEndTextAlign::Center,20);
            }else if(page==Page::Options){
                scene=BuildOriginalFrontEndOptions(*assets,options,hovered,[](const std::string& key){return SourceLabel(key);});
            }else if(page==Page::Replay){
                if(!endGame || !hooks.replayScene)throw std::logic_error("Replay page has no owned parsed replay controller");
                scene=hooks.replayScene(*assets);
                if(scene.width!=1920 || scene.height!=1080)throw std::logic_error("Replay controller returned an invalid viewport");
                // Replay owns its original source-derived Back control (35).
                // Appending a second generic button would duplicate its route.
                const auto count=std::count_if(scene.hits.begin(),scene.hits.end(),[](const HitRecord& hit){return hit.controlKey==35;});
                if(count!=1)throw std::logic_error("Replay page requires one original Back route");
            }else{
                if(!endGame)throw std::logic_error("Results page has no completed retirement packet");
                scene=assets->Background();assets->Rect(scene,0,420,140,1080,805,{0,0,0,0.72f});
                assets->Text(scene,0,L"ZeroSis' \u2014 "+Localized(page==Page::Ranking?"TXT_KEY_RANKING_TITLE":"TXT_KEY_RETIRE"),480,165,960,55,MenuFrontEndTextAlign::Center,24);
                assets->Text(scene,0,L"\ucd5c\uc885 \uc810\uc218: "+std::to_wstring(endGame->finalScore),480,225,960,45,MenuFrontEndTextAlign::Center);
                if(page==Page::Ranking){
                    float top=285;
                    for(std::size_t index=rankingPage*10;index<rankings.size() && index<(rankingPage+1)*10;++index){
                        const auto& row=rankings[index];
                        assets->Text(scene,0,row.leader+L"  "+std::to_wstring(row.threshold)+(endGame->finalScore>=row.threshold?L"  +":L""),500,top,920,37,MenuFrontEndTextAlign::Center,20);top+=39;
                    }
                    assets->Button(scene,30,760,720,400,45,mainLabel,true,hovered==30);
                    assets->Button(scene,35,760,780,400,45,L"\uc740\ud1f4 \uacb0\uacfc",true,hovered==35);
                    assets->Button(scene,34,500,850,300,45,L"\uc774\uc804",rankingPage>0,hovered==34);
                    assets->Button(scene,33,1120,850,300,45,L"\ub2e4\uc74c",(rankingPage+1)*10<rankings.size(),hovered==33);
                }else{
                    assets->Text(scene,0,L"\uc7ac\uc0dd \ud30c\uc77c: "+std::to_wstring(endGame->replay.size())+L" \ubc14\uc774\ud2b8",480,330,960,45,MenuFrontEndTextAlign::Center,20);
                    assets->Button(scene,30,760,600,400,45,mainLabel,true,hovered==30);
                    assets->Button(scene,31,760,670,400,45,Localized("TXT_KEY_RANKING_TITLE"),true,hovered==31);
                    assets->Button(scene,32,760,740,400,45,L"\uc7ac\uc0dd",bool(hooks.replayScene),hovered==32);
                }
            }
            bool prepared=false,dragVisual=false;
            if(created && (page==Page::Replay || page==Page::Options) && window.HasControlDragCapture()){
                if(!window.PrepareGpuFrame([&](ID3D11Device* device,ID3D11DeviceContext* context,ID3D11Texture2D* target,std::wstring* why){
                    return RenderSceneToD3D11Texture(scene,device,context,target,why);},&error))throw std::runtime_error(Utf8(error));
                prepared=true;
                // Refresh performs the complete input-geometry equality check.
                // Changed keys/rectangles use the usual commit and cancel capture.
                dragVisual=window.RefreshPreparedGpuFrame(scene,&error);
            }
            if(!created){
                const MenuOptionsValues startup=hasOptions?hooks.options->Committed():MenuOptionsValues{};
                if(!window.CreateGpuScene(scene,L"ZeroSis' \u2014 \uc8fc \uba54\ub274",startup.windowWidth,startup.windowHeight,startup.vsync,&error) ||
                   !window.EnableGameplayInput(true,&error) || !window.EnableProductionPointerInput(true,&error) ||
                   !window.EnableControlDragInput(true,&error))
                    throw std::runtime_error(Utf8(error));
                created=true;
                if(hasOptions && hooks.applyOptions(window,startup)!=startup)
                    throw std::runtime_error("Front-end canonical startup options did not read back from their actual backends");
            }else if(!dragVisual){
                const bool committed=prepared?window.UpdatePreparedGpuSceneRetainingInput(scene,&error):window.UpdateGpuSceneRetainingInput(scene,&error);
                if(!committed)throw std::runtime_error(Utf8(error));
            }
            redraw=false;
        }
        if(!window.PumpMessages(&error))throw std::runtime_error(Utf8(error));
        if(!window.IsOpen())return MenuLifecycleFrontEndChoice::Exit;
        std::vector<BitmapInputEvent> inputs;if(!window.DrainInputs(&inputs,&error))throw std::runtime_error(Utf8(error));
        for(const auto& input:inputs){
            if(input.sceneGeneration!=window.SceneGeneration())continue;
            if(input.kind==BitmapInputKind::CloseRequest){
                if(page==Page::Options){options.Cancel();finishOptions();exitParent=Page::Main;}else exitParent=page;
                page=Page::ExitConfirm;hovered=0;redraw=true;break;
            }
            if(page==Page::Options){
                MenuFrontEndOptionsModel::Input value;value.key=input.controlKey;value.virtualKey=input.virtualKey;
                value.x=input.logicalX;value.y=input.logicalY;value.shift=(input.modifiers&1u)!=0;value.hover=hovered;
                value.wheel=float(input.wheelDelta?input.wheelDelta:input.scrollDelta);value.captured=window.HasControlDragCapture();
                bool supported=true;
                if(input.kind==BitmapInputKind::KeyDown)value.kind=MenuFrontEndOptionsModel::InputKind::Key;
                else if(input.kind==BitmapInputKind::ControlClick)value.kind=MenuFrontEndOptionsModel::InputKind::Click;
                else if(input.kind==BitmapInputKind::ControlDrag)value.kind=MenuFrontEndOptionsModel::InputKind::Drag;
                else if(input.kind==BitmapInputKind::Scroll || input.kind==BitmapInputKind::WorldWheel)value.kind=MenuFrontEndOptionsModel::InputKind::Wheel;
                else supported=false;
                if(input.kind==BitmapInputKind::PointerMove && hovered!=input.controlKey){hovered=input.controlKey;redraw=true;}
                const bool previewBefore=options.ResolutionPreviewActive();
                if(supported && options.InputEvent(value)){
                    if(!previewBefore && options.ResolutionPreviewActive())resolutionClock.Start(GetTickCount64());
                    else if(!options.ResolutionPreviewActive())resolutionClock.Stop();
                    finishOptions();
                    redraw=true;break;
                }
                continue;
            }
            if(input.kind==BitmapInputKind::KeyDown && input.virtualKey==VK_ESCAPE){
                if(page==Page::ExitConfirm)page=exitParent;
                else if(page==Page::Main){exitParent=page;page=Page::ExitConfirm;}
                else if(page==Page::SinglePlayer)page=Page::Main;
                else page=Page::Results;
                hovered=0;redraw=true;break;
            }
            if(input.kind==BitmapInputKind::PointerMove && hovered!=input.controlKey){hovered=input.controlKey;redraw=true;}
            if(page==Page::Replay && hooks.replayInput && hooks.replayInput(input)){
                redraw=true;
                if(ContinueHandledMenuReplayInputBatch(input,window.SceneGeneration(),0x300000000ull))continue;
                break;
            }
            if(input.kind!=BitmapInputKind::ControlClick)continue;
            const auto key=input.controlKey;
            if(page==Page::Main && key==1)page=Page::SinglePlayer;
            else if(page==Page::Main && key==4 && hasOptions && options.Available()){
                options.Open();optionsError.clear();page=Page::Options;
            }
            else if(page==Page::Main && key==3){exitParent=page;page=Page::ExitConfirm;}
            else if(page==Page::SinglePlayer && key==10 && hasCurrentSetup)return MenuLifecycleFrontEndChoice::StartCurrentSetup;
            else if(page==Page::SinglePlayer && key==11)page=Page::Main;
            else if(page==Page::ExitConfirm && key==20)return MenuLifecycleFrontEndChoice::Exit;
            else if(page==Page::ExitConfirm && key==21)page=exitParent;
            else if((page==Page::Results || page==Page::Ranking) && key==30)page=Page::Main;
            else if(page==Page::Results && key==31)page=Page::Ranking;
            else if(page==Page::Results && key==32 && hooks.replayScene)page=Page::Replay;
            else if(page==Page::Ranking && key==33 && (rankingPage+1)*10<rankings.size())++rankingPage;
            else if(page==Page::Ranking && key==34 && rankingPage)--rankingPage;
            else if((page==Page::Ranking || page==Page::Replay) && key==35)page=Page::Results;
            else continue;
            hovered=0;redraw=true;break; // Every page change ends the old input batch.
        }
        if(!redraw)Sleep(8);
    }
}
}
#endif
