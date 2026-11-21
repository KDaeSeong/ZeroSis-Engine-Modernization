#pragma once
#include "MenuFrontEndAssets.h"
#include "MenuFrontEndOptionsModel.h"
#include "MenuResolutionPreviewLayout.h"
#include "MenuRewardOptionsLayout.h"

namespace ZeroSisHost {
inline void ConfigureOriginalFrontEndOptions(const MenuFrontEndAssets& assets,MenuFrontEndOptionsModel& model){
    const auto& slider=assets.OptionsControl("EffectsVolumeSlider");
    model.SetVolumeGeometry(slider.x,slider.y,slider.width,slider.height);
}
inline ZeroSisPresentation::Scene BuildOriginalFrontEndOptions(const MenuFrontEndAssets& assets,
    const MenuFrontEndOptionsModel& model,std::uint64_t hovered,const std::function<std::wstring(const std::string&)>& label){
    using Model=MenuFrontEndOptionsModel;using Page=Model::Page;using Control=Model::Control;
    if(!model.Opened() || !assets.Extended() || !label)throw std::logic_error("Original front-end options need their owned open model and source assets");
    auto scene=assets.OptionsChrome();const auto& values=model.Values();
    auto text=[&](const std::wstring& value,float x,float y,float width,float height,unsigned px=22,
        MenuFrontEndTextAlign align=MenuFrontEndTextAlign::Left,MenuFrontEndAssets::Color tint={1,1,1,1}){
        assets.Text(scene,0,value,x,y,width,height,align,px,tint);
    };
    auto focus=[&](Control control,const MenuFrontEndAssets::OptionControl& row){
        if(model.Focus()!=control)return;
        assets.Rect(scene,0,row.x,row.y+row.height+1,row.width,1,{1,1,.78f,.8f});
    };
    const char* tabs[]={"GameButton","IFaceButton","VideoButton","AudioButton"};
    for(unsigned i=0;i<4;++i){const auto page=static_cast<Page>(i);const auto& row=assets.OptionsControl(tabs[i]);
        const auto control=static_cast<Control>(i+1);const bool enabled=model.PageSupported(page);const auto key=model.KeyFor(control);
        if(page==model.CurrentPage() || (enabled && key==hovered))assets.Grid(scene,key,page==model.CurrentPage()?"Grid9FrameTurns":"Grid9FrameTurnsHL",row.x,row.y-1,row.width,27);
        text(label(row.textKey),row.x,row.y,row.width,row.height,18,MenuFrontEndTextAlign::Center,{1,1,1,enabled?1.0f:.38f});
        if(enabled)scene.hits.push_back({key,{row.x,row.y,row.x+row.width,row.y+row.height}});focus(control,row);
    }
    const auto& audioTab=assets.OptionsControl("AudioButton");
    text(label("TXT_KEY_MULTIPLAYER_OPTIONS"),audioTab.x+audioTab.width,audioTab.y,200,24,18,MenuFrontEndTextAlign::Center,{1,1,1,.38f});
    const auto title=assets.OptionsControl(tabs[static_cast<unsigned>(model.CurrentPage())]).textKey;
    assets.Text(scene,0,label(title),540,267,840,22,MenuFrontEndTextAlign::Center,20,{1,1,1,1},"SoftShadow","MenuTitleColors");
    auto toggle=[&](Control control,const MenuFrontEndAssets::OptionControl& row,const char* capability,bool checked){
        if(!model.Supports(capability))return;const auto key=model.KeyFor(control);
        assets.Grid(scene,key,"Button_16",row.x,row.y,row.width,row.height,checked?1:0);
        text(label(row.textKey),row.x+row.width+4,row.y,350,40,22);
        scene.hits.push_back({key,{row.x,row.y,row.x+row.width,row.y+row.height}});focus(control,row);
    };
    if(model.CurrentPage()==Page::Game){
        const auto rows=MenuRewardOptionsLayout::At(assets,model.Supports("noRewardPopups"),model.Supports("noBasicHelp"));
        if(rows.hasReward)toggle(Control::NoRewardPopups,rows.reward,"noRewardPopups",values.noRewardPopups);
        if(rows.hasBasic)toggle(Control::NoBasicHelp,rows.basic,"noBasicHelp",values.noBasicHelp);
    }
    if(model.CurrentPage()==Page::Interface)toggle(Control::PolicyInfo,assets.OptionsControl("PolicyInfo"),"policyInfo",values.policyInfo);
    if(model.CurrentPage()==Page::Video){
        if(model.Supports("windowWidth")){
            const auto& row=assets.OptionsControl("WResolutionPull");const auto key=model.KeyFor(Control::Resolution);
            assets.StyleButton(scene,key,"GenericPullDown",row.x,row.y,row.width,row.height,
                std::to_wstring(values.windowWidth)+L" x "+std::to_wstring(values.windowHeight),true,hovered==key);
            text(label("TXT_KEY_OPSCREEN_RESOLUTION"),row.x-185,row.y,175,row.height,22,MenuFrontEndTextAlign::Right);focus(Control::Resolution,row);
        }
        toggle(Control::Fullscreen,assets.OptionsControl("FullscreenCheck"),"fullscreen",values.fullscreen);
        toggle(Control::VSync,assets.OptionsControl("VSyncCheck"),"vsync",values.vsync);
        const auto apply=MenuResolutionPreviewLayout::ApplyResolutionButton();
        const auto key=model.KeyFor(Control::ApplyResolution);const bool changed=model.ResolutionChanged();
        assets.StyleButton(scene,key,"SmallButton",apply.x,apply.y,apply.width,apply.height,L"",changed,hovered==key);
        assets.Text(scene,key,label("TXT_KEY_OPSCREEN_APPLY_RESOLUTION"),apply.x,apply.y,apply.width,apply.height,
            MenuFrontEndTextAlign::Center,18,{1,1,1,changed?1.0f:.38f},"Shadow","Beige_Black_Alpha");
        MenuFrontEndAssets::OptionControl row{};row.x=apply.x;row.y=apply.y;row.width=apply.width;row.height=apply.height;
        focus(Control::ApplyResolution,row);
    }
    if(model.CurrentPage()==Page::Audio && model.Supports("uiCueVolumePercent")){
        const auto& row=assets.OptionsControl("EffectsVolumeSlider");const auto key=model.KeyFor(Control::Volume);
        text(L"\uc778\ud130\ud398\uc774\uc2a4 \ud6a8\uacfc\uc74c: "+std::to_wstring(values.uiCueVolumePercent)+L"%",row.x,row.y-32,row.width,30,22);
        assets.Grid(scene,key,"Slider",row.x,row.y,row.width,row.height);
        const float handle=row.x+(row.width-32)*values.uiCueVolumePercent/100.0f;
        assets.Grid(scene,key,"Slider32",handle,row.y,32,32);
        scene.hits.push_back({key,{row.x,row.y,row.x+row.width,row.y+row.height}});
        scene.scrolls.push_back({key,{row.x,row.y,row.x+row.width,row.y+row.height}});focus(Control::Volume,row);
    }
    const char* footer[]={"DefaultButton","CancelButton","AcceptButton"};
    const Control footerControl[]={Control::Defaults,Control::Cancel,Control::Accept};
    for(unsigned i=0;i<3;++i){const auto& row=assets.OptionsControl(footer[i]);const auto key=model.KeyFor(footerControl[i]);
        assets.StyleButton(scene,key,i==2?"BaseButton":"SmallButton",row.x,row.y,row.width,row.height,label(row.textKey),true,hovered==key);focus(footerControl[i],row);
    }
    text(L"\uc9c0\uc6d0\ud558\ub294 \uc124\uc815\ub9cc \ud45c\uc2dc\ud569\ub2c8\ub2e4.",530,740,860,32,20,MenuFrontEndTextAlign::Center,{1,1,1,.65f});
    if(model.DropdownOpened()){
        const auto& row=assets.OptionsControl("WResolutionPull");const auto key=model.KeyFor(Control::Resolution);
        // The original dropdown is modal. A barrier after the underlying hits
        // prevents the same click from also committing or resetting settings.
        scene.hits.push_back({key,{0,0,1920,1080}});
        const auto& rows=model.Resolutions();const float top=row.y+row.height;
        assets.Grid(scene,0,"Grid9Frame27SquareBlack",row.x-5,top-2,220,float(rows.size())*24+10);
        for(std::size_t i=0;i<rows.size();++i){const auto& resolution=rows[i];const auto entry=model.ResolutionKey(i);
            assets.StyleButton(scene,entry,"ZoomButton",row.x,top+3+24*float(i),200,24,
                std::to_wstring(resolution.width)+L" x "+std::to_wstring(resolution.height),true,hovered==entry || model.ResolutionCursor()==i);
        }
    }
    if(model.ResolutionPreviewActive()){
        const auto message=label("TXT_KEY_OPSCREEN_RESOLUTION_TIMER");
        const auto timer=std::to_wstring(model.ResolutionCountdownSeconds());
        const auto preview=MenuResolutionPreviewLayout::At(assets,message,timer);
        // The source Countdown is declared last and consumes the full screen.
        // Its only actionable children are CountYes/CountNo; the barrier's key
        // zero blocks the previous page and dropdown without invoking a choice.
        scene.hits.clear();scene.scrolls.clear();scene.pixelHits={};
        assets.Rect(scene,0,0,0,1920,1080,{0,0,0,128.0f/255});
        scene.hits.push_back({0,{0,0,1920,1080}});scene.scrolls.push_back({0,{0,0,1920,1080}});
        assets.Grid(scene,0,"Grid9DetailFive140",preview.frame.x,preview.frame.y,preview.frame.width,preview.frame.height);
        auto image=[&](const char* name,const MenuResolutionPreviewBounds& bounds,float alpha=1.0f){
            const auto& texture=assets.TextureNamed(name);
            const float source[]={0,0,static_cast<float>(texture.width),static_cast<float>(texture.height)};
            const float target[]={bounds.x,bounds.y,bounds.Right(),bounds.Bottom()};
            assets.Texture(scene,0,texture.index,source,target,{1,1,1,alpha});
        };
        image("Dec32x64Left.dds",preview.leftDecoration);
        image("Dec32x64Right.dds",preview.rightDecoration);
        image("Top512IconTrim.dds",preview.topDecoration);
        image("NotificationFrameBase.dds",preview.notificationFrame);
        image("NotificationGenericGlow.dds",preview.glow,MenuResolutionPreviewLayout::GlowAlpha(model.ResolutionPreviewElapsed()));
        assets.Text(scene,0,message,preview.message.x,preview.message.y,preview.message.width,preview.message.height,
            MenuFrontEndTextAlign::Center,20,{1,1,1,1},"Shadow","Beige_Black_Alpha");
        assets.Text(scene,0,timer,preview.timer.x,preview.timer.y,preview.timer.width,preview.timer.height,
            MenuFrontEndTextAlign::Center,24,{1,1,1,1},"Shadow","Beige_Black_Alpha");
        auto choice=[&](Control control,const char* textKey,const MenuResolutionPreviewBounds& bounds){
            const auto key=model.KeyFor(control);
            assets.StyleButton(scene,key,"BaseButton",bounds.x,bounds.y,bounds.width,bounds.height,L"",true,hovered==key);
            assets.Text(scene,key,label(textKey),bounds.x,bounds.y,bounds.width,bounds.height,MenuFrontEndTextAlign::Center,
                20,{1,1,1,1},"Shadow","Beige_Black");
            MenuFrontEndAssets::OptionControl row{};row.x=bounds.x;row.y=bounds.y;row.width=bounds.width;row.height=bounds.height;
            focus(control,row);
        };
        choice(Control::KeepResolution,"TXT_KEY_YES_BUTTON",preview.yes);
        choice(Control::RevertResolution,"TXT_KEY_NO_BUTTON",preview.no);
    }
    return scene;
}
}
