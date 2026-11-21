#pragma once
#include "MenuFrontEndAssets.h"
#include <algorithm>
#include <cmath>
#include <cstdint>
#include <stdexcept>
#include <string>

namespace ZeroSisHost {
struct MenuResolutionPreviewBounds final {
    float x=0,y=0,width=0,height=0;
    float Right() const noexcept{return x+width;}
    float Bottom() const noexcept{return y+height;}
};
struct MenuResolutionPreviewTextMetrics final {float width=0,height=0;std::size_t lines=1;};

// Match MenuFrontEndAssets::Text's existing scalar decoding/wrapping, using its
// sealed GlyphGen advances. Measuring is separate from drawing the same text;
// no new font, native label measurement or native pixel equivalence is implied.
inline MenuResolutionPreviewTextMetrics MeasureMenuResolutionPreviewText(
    const MenuFrontEndAssets::Font& font,const std::wstring& text,float wrapWidth){
    if(!std::isfinite(wrapWidth) || wrapWidth<=0 || wrapWidth>1920 || font.lineAdvance<=0 || text.size()>65536)
        throw std::invalid_argument("Invalid resolution preview label measurement");
    MenuResolutionPreviewTextMetrics result;float advance=0;bool nonempty=false;
    for(std::size_t index=0;index<text.size();++index){
        auto cp=static_cast<std::uint32_t>(text[index]);
        if(cp>=0xd800 && cp<=0xdbff){
            if(index+1>=text.size())throw std::invalid_argument("Unpaired resolution label high surrogate");
            const auto low=static_cast<std::uint32_t>(text[++index]);
            if(low<0xdc00 || low>0xdfff)throw std::invalid_argument("Unpaired resolution label low surrogate");
            cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00);
        }else if(cp>=0xdc00 && cp<=0xdfff)throw std::invalid_argument("Unpaired resolution label low surrogate");
        if(cp=='\r' || cp=='\n'){
            if(cp=='\r' && index+1<text.size() && text[index+1]=='\n')++index;
            result.width=(std::max)(result.width,advance);advance=0;nonempty=false;++result.lines;continue;
        }
        auto found=font.glyphs.find(cp);
        if(found==font.glyphs.end())found=font.glyphs.find('?');
        if(found==font.glyphs.end())throw std::invalid_argument("Resolution preview label has no fallback glyph");
        const auto& glyph=found->second;const float next=static_cast<float>(glyph.a+glyph.b+glyph.c);
        if(advance+next>wrapWidth && nonempty){result.width=(std::max)(result.width,advance);advance=0;nonempty=false;++result.lines;}
        advance+=next;nonempty=true;
    }
    result.width=(std::max)(result.width,advance);result.height=static_cast<float>(result.lines)*font.lineAdvance;
    if(!std::isfinite(result.height) || result.height<=0)throw std::invalid_argument("Resolution preview label height is invalid");
    return result;
}

struct MenuResolutionPreviewLayout final {
    using Bounds=MenuResolutionPreviewBounds;
    Bounds viewport{0,0,1920,1080},frame,message,timer,labelStack,buttonStack,yes,no;
    Bounds leftDecoration,rightDecoration,topDecoration,notificationFrame,glow;
    MenuResolutionPreviewTextMetrics messageMetrics,timerMetrics;
    // OptionsMenu.xml declares Grid Padding=0,20 but does not auto-size it.
    // Its script calculates/reanchors LabelStack only; padding is not another
    // child offset in the retained anchor contract.
    float framePaddingX=0,framePaddingY=20;

    static Bounds ApplyResolutionButton(){
        const Bounds viewport{0,0,1920,1080};
        const auto options=Anchor(viewport,960,658,Axis::Center,Axis::Center,0,36);
        const auto video=Anchor(options,971,500,Axis::Near,Axis::Near,0,44);
        const auto resolution=Anchor(video,395,200,Axis::Near,Axis::Near,40,100);
        return Anchor(resolution,200,32,Axis::Center,Axis::Far,0,20);
    }
    static MenuResolutionPreviewLayout At(const MenuFrontEndAssets& assets,
        const std::wstring& messageText,const std::wstring& timerText){
        MenuResolutionPreviewLayout result;
        // Base OptionsMenu.xml: full-screen Black.128, then centered400x300.
        result.frame=Anchor(result.viewport,400,300,Axis::Center,Axis::Center,0,0);
        result.messageMetrics=MeasureMenuResolutionPreviewText(assets.FontFace(20,"Shadow"),messageText,300);
        result.timerMetrics=MeasureMenuResolutionPreviewText(assets.FontFace(24,"Shadow"),timerText,300);
        const float labelHeight=result.messageMetrics.height+10+result.timerMetrics.height;
        result.labelStack=Anchor(result.frame,300,labelHeight,Axis::Center,Axis::Near,0,60);
        result.message=Anchor(result.labelStack,300,result.messageMetrics.height,Axis::Center,Axis::Near,0,0);
        result.timer=Anchor(result.labelStack,300,result.timerMetrics.height,Axis::Center,Axis::Near,0,result.messageMetrics.height+10);
        result.buttonStack=Anchor(result.frame,300,30+10+30,Axis::Center,Axis::Far,0,60);
        result.yes=Anchor(result.buttonStack,300,30,Axis::Center,Axis::Near,0,0);
        result.no=Anchor(result.buttonStack,300,30,Axis::Center,Axis::Near,0,30+10);
        // The active Expansion1 styles override BaseGame's -17/-27 offsets
        // and use Top512IconTrim, whose actual lossless pixels are256x64.
        const auto left=Anchor(result.frame,0,0,Axis::Near,Axis::Center,0,0,true,false);
        const auto right=Anchor(result.frame,0,0,Axis::Far,Axis::Center,0,0,true,false);
        result.leftDecoration=Anchor(left,32,64,Axis::Far,Axis::Center,-19,0);
        result.rightDecoration=Anchor(right,32,64,Axis::Near,Axis::Center,-19,0);
        const auto top=Anchor(result.frame,0,0,Axis::Center,Axis::Near,0,0,false,true);
        result.topDecoration=Anchor(top,256,64,Axis::Center,Axis::Far,0,-14);
        result.notificationFrame=Anchor(result.topDecoration,80,80,Axis::Center,Axis::Center,0,0);
        result.glow=Anchor(result.notificationFrame,80,80,Axis::Center,Axis::Center,0,0);
        return result;
    }
    // Reuse UiScene.lua alphaValue's explicit Speed=1/Pause=0/Bounce policy.
    // This source-derived triangle wave is not native shader/timing proof.
    static float GlowAlpha(double elapsed){
        if(!std::isfinite(elapsed) || elapsed<0)throw std::invalid_argument("Invalid resolution preview animation time");
        const double phase=std::fmod(elapsed,2.0);
        return static_cast<float>(phase<1.0?1.0-.5*phase:.5+.5*(phase-1.0));
    }
private:
    enum class Axis {Near,Center,Far};
    static Bounds Anchor(const Bounds& parent,float width,float height,Axis horizontal,Axis vertical,
        float offsetX,float offsetY,bool outsideX=false,bool outsideY=false){
        const float x=horizontal==Axis::Center?(parent.width-width)/2+offsetX:
            horizontal==Axis::Far?(outsideX?parent.width+offsetX:parent.width-width-offsetX):
            outsideX?-width-offsetX:offsetX;
        const float y=vertical==Axis::Center?(parent.height-height)/2+offsetY:
            vertical==Axis::Far?(outsideY?parent.height+offsetY:parent.height-height-offsetY):
            outsideY?-height-offsetY:offsetY;
        return {parent.x+x,parent.y+y,width,height};
    }
};
}
