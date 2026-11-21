#pragma once
#include <functional>
#include "MenuReplayTimeline.h"
#include "MenuReplayText.h"
#include "MenuReplayMessageViewport.h"
#include "MenuReplayScrollModel.h"
#include "MenuReplayGraphGeometry.h"
#include "MenuReplayPointerGuides.h"
#include "MenuReplayLayout.h"
#include "MenuReplayCalendar.h"
#include "MenuReplayGraphColors.h"
#include "../Presentation/BitmapWindow.h"
#include <set>

namespace ZeroSisHost {
struct MenuReplayLabels final {
    std::wstring title,map,graphs,messages,playPause,turn,noGraphData,terrainReference,unsupportedReplay,back;
    std::function<std::wstring(int)> turnCounter;
    std::wstring graphSimplified=L"\ud45c\uc2dc \ud55c\ub3c4\ub85c \uc77c\ubd80 \uc5f0\uacb0\uc120\uc744 \uc0dd\ub7b5\ud569\ub2c8\ub2e4. \uc6d0\ubcf8 \uae30\ub85d\uc740 \uc720\uc9c0\ub429\ub2c8\ub2e4.";
};
struct MenuReplayPalette final {
    using Color=MenuFrontEndAssets::Color;
    struct LegendIcon final {std::string texture;unsigned portrait=0,columns=0,rows=0;};
    std::vector<Color> playerPrimary,playerSecondary,messagePrimary,messageSecondary;
    std::vector<Color> graphColors;
    std::vector<LegendIcon> legendIcons;
    std::vector<std::string> playerLabels;
    std::set<std::size_t> initiallyHiddenPlayers;
    std::map<std::string,Color> richColors;
    std::map<int,Color> terrainColors;int iceFeature=-1;
    std::map<std::string,std::wstring> dataSetLabels;
    std::shared_ptr<const MenuReplayCalendar> calendar;
};
class MenuReplayView final {
public:
    using Color=MenuFrontEndAssets::Color;
    using SceneType=ZeroSisPresentation::Scene;
    static constexpr std::uint64_t KeyBase=0x300000000ull,SeekKey=KeyBase+0x100,MessageSeekKey=KeyBase+0x101,
        LegendSeekKey=KeyBase+0x102,LegendScrollKey=KeyBase+0x103,MessageScrollKey=KeyBase+0x104,
        TurnScrollKey=KeyBase+0x105;
    MenuReplayView(const std::vector<unsigned char>& raw,MenuReplayLabels labels,MenuReplayPalette palette={})
        :labels_(std::move(labels)),palette_(std::move(palette)),rawByteCount_(raw.size()){
        try{auto document=std::make_shared<const MenuReplayDocument>(ReadMenuReplay(raw));
            timeline_=std::make_unique<MenuReplayTimeline>(std::move(document));
            for(const auto player:palette_.initiallyHiddenPlayers)if(player<timeline_->Document().players.size())hidden_.insert(player);}
        catch(const std::exception& error){error_=error.what();}
    }
    bool Available() const noexcept{return static_cast<bool>(timeline_);}
    const std::string& ReadError() const noexcept{return error_;}
    const MenuReplayTimeline* Timeline() const noexcept{return timeline_.get();}
    const MenuReplayMessagePages* RichMessages() const noexcept{return messagePages_.get();}
    double MessageOffset() const noexcept{return messageScroll_;}
    const MenuReplayMessageViewport* MessageViewport() const noexcept{return messageViewport_.get();}
    float LegendOffset() const noexcept{return legendScroll_;}
    bool LegendDragging() const noexcept{return captureKey_==LegendSeekKey;}
    bool ScrollDragging() const noexcept{return captureKey_!=0;}
    MenuReplayPointerGuides PointerGuides() const {
        if(!timeline_)return {};
        const auto bounds=MenuReplayOriginalLayout::At().graph;
        return BuildMenuReplayPointerGuides(bounds.x,bounds.y,bounds.width,bounds.height,
            pointerX_,pointerY_,page_==Page::Graphs,pointerAvailable_);
    }
    bool PointerCapture(bool held){
        if(held)return false;
        const bool changed=captureKey_!=0;scrollGesture_.Cancel();captureKey_=capturePressId_=0;captureHits_.clear();captureScrolls_.clear();return changed;
    }
    std::array<MenuReplayCalendarResult,5> GraphDates() const {
        std::array<MenuReplayCalendarResult,5> dates{};
        if(!timeline_ || !palette_.calendar)return dates;
        const auto& doc=timeline_->Document();const auto domain=MenuReplayGraphDomain::Create(doc.initialTurn,doc.finalTurn);
        for(std::size_t i=0;i<dates.size();++i)if(domain.ticks[i].visible)
            dates[i]=palette_.calendar->ShortDate(doc.calendar,doc.gameSpeed,doc.startYear,domain.ticks[i].turn);
        return dates;
    }
    bool Advance(double seconds){return timeline_ && page_==Page::Map && timeline_->Advance(seconds);}
    bool Input(const ZeroSisPresentation::BitmapInputEvent& input){
        using ZeroSisPresentation::BitmapInputKind;
        if(!timeline_)return false;
        if(input.kind==BitmapInputKind::PointerMove)return TrackPointer(input.logicalX,input.logicalY);
        if(input.controlKey==35 && !ScrollDragging())return false;
        auto& timeline=*timeline_;const auto& doc=timeline.Document();auto key=input.controlKey;
        const auto layout=MenuReplayOriginalLayout::At();
        if(input.kind==BitmapInputKind::ControlClick && key!=captureKey_ && ScrollDragging()){
            if(input.pointerPressId && capturePressId_ && input.pointerPressId!=capturePressId_)return true;
            PointerCapture(false);return true;
        }
        if(!selectorOpen_ && !dataSetOpen_ && input.kind==BitmapInputKind::Scroll){
            if(!std::isfinite(input.scrollDelta) || input.scrollDelta==0)return false;
            PointerCapture(false);
            if(page_==Page::Graphs && key==LegendScrollKey){ScrollLegend(legendScroll_+input.scrollDelta,layout);return true;}
            if(page_==Page::Messages && key==MessageScrollKey && messageViewport_){ScrollMessages(messageScroll_+input.scrollDelta,layout);return true;}
            if(page_==Page::Map && key==TurnScrollKey){
                // One WM_MOUSEWHEEL is one queued Scroll event. BitmapWindow
                // negates the raw delta, so scrollDelta<0 is HIWORD(wParam)>0.
                // The source callback runs even when the clamped turn is unchanged.
                timeline.Seek(MenuReplayScrollModel::WheelTurn(timeline.Turn(),doc.initialTurn,doc.finalTurn,
                    MenuReplayScrollModel::OriginalTurnSliderWheelSteps,input.scrollDelta<0));
                return true;
            }
            return false;
        }
        if(input.kind==BitmapInputKind::KeyDown){
            PointerCapture(false);
            if(selectorOpen_ || dataSetOpen_)return false;
            if(page_==Page::Messages && messageViewport_){
                if(input.virtualKey==0x26)return ScrollMessages(messageScroll_-messageLineStep_,layout);
                if(input.virtualKey==0x28)return ScrollMessages(messageScroll_+messageLineStep_,layout);
                if(input.virtualKey==0x21)return ScrollMessages(messageScroll_-layout.text.height,layout);
                if(input.virtualKey==0x22)return ScrollMessages(messageScroll_+layout.text.height,layout);
                if(input.virtualKey==0x24)return ScrollMessages(0,layout);
                if(input.virtualKey==0x23)return ScrollMessages(messageViewport_->Maximum(layout.text.height),layout);
                return false;
            }
            else if(page_==Page::Map){switch(input.virtualKey){case 0x20:key=KeyBase+1;break;case 0x25:key=KeyBase+3;break;
                case 0x27:key=KeyBase+4;break;case 0x24:key=KeyBase+5;break;case 0x23:key=KeyBase+6;break;default:return false;}}
            else if(page_==Page::Graphs){
                if(input.virtualKey==0x26)return ScrollLegend(legendScroll_-layout.legendRowPitch,layout);
                if(input.virtualKey==0x28)return ScrollLegend(legendScroll_+layout.legendRowPitch,layout);
                if(input.virtualKey==0x21)return ScrollLegend(legendScroll_-layout.graphLegend.height,layout);
                if(input.virtualKey==0x22)return ScrollLegend(legendScroll_+layout.graphLegend.height,layout);
                if(input.virtualKey==0x24)return ScrollLegend(0,layout);
                if(input.virtualKey==0x23)return ScrollLegend(LegendMaximum(layout),layout);
                return false;
            }else return false;
        }else if(input.kind!=BitmapInputKind::ControlClick && input.kind!=BitmapInputKind::ControlDrag)return false;
        if(input.kind==BitmapInputKind::ControlClick && key==KeyBase+12){selectorOpen_=!selectorOpen_;dataSetOpen_=false;return true;}
        if(selectorOpen_){
            if(input.kind==BitmapInputKind::ControlClick){
                if(key==KeyBase+7 || key==KeyBase+8 || key==KeyBase+9){
                    page_=key==KeyBase+7?Page::Map:key==KeyBase+8?Page::Graphs:Page::Messages;
                    if(page_!=Page::Map)timeline.SetPlaying(false);}
                selectorOpen_=false;return true;
            }return false;
        }
        if(input.kind==BitmapInputKind::ControlClick && page_==Page::Graphs && key==KeyBase+13 && !doc.dataSetNames.empty()){
            dataSetOpen_=!dataSetOpen_;dataSetPage_=dataSet_/8;return true;
        }
        if(dataSetOpen_){
            if(input.kind!=BitmapInputKind::ControlClick)return false;
            if(key==KeyBase+16 && dataSetPage_){--dataSetPage_;return true;}
            if(key==KeyBase+17 && (dataSetPage_+1)*8<doc.dataSetNames.size()){++dataSetPage_;return true;}
            if(key>=KeyBase+0x2000+dataSetPage_*8 && key<KeyBase+0x2000+(dataSetPage_+1)*8 && key<KeyBase+0x2000+doc.dataSetNames.size())
                dataSet_=static_cast<std::size_t>(key-KeyBase-0x2000);
            dataSetOpen_=false;return true;
        }
        if(key==SeekKey && page_==Page::Map){
            if(!std::isfinite(input.logicalX))return false;
            const auto fraction=MenuReplayScrollModel::Fraction(timeline.Turn()-doc.initialTurn,doc.finalTurn-doc.initialTurn);
            const auto geometry=MenuReplayScrollGeometry::Create(layout.slider.x,layout.slider.width,32,fraction);
            return SliderInput(input,geometry,true,[&](double unit){timeline.Seek(MenuReplayScrollModel::SourceFloor(unit,doc.initialTurn,doc.finalTurn));});
        }
        if(key==MessageSeekKey && page_==Page::Messages && messageViewport_){
            if(!std::isfinite(input.logicalY))return false;
            const auto maximum=messageViewport_->Maximum(layout.text.height);
            const auto geometry=MessageSlider(layout);
            return SliderInput(input,geometry,false,[&](double unit){ScrollMessages(MenuReplayScrollModel::FloatContinuous(unit,maximum),layout);});
        }
        if(key==LegendSeekKey && page_==Page::Graphs){
            if(!std::isfinite(input.logicalY) || LegendMaximum(layout)<=0)return false;
            return SliderInput(input,LegendSlider(layout),false,[&](double unit){ScrollLegend(static_cast<float>(MenuReplayScrollModel::FloatContinuous(unit,LegendMaximum(layout))),layout);});
        }
        if(input.kind==BitmapInputKind::ControlDrag)return false;
        if(page_==Page::Map){
            if(key==KeyBase+1){timeline.TogglePlaying();return true;}
            if(input.kind==BitmapInputKind::KeyDown){
                if(key==KeyBase+3){timeline.Seek((std::max)(doc.initialTurn,timeline.Turn()-1));return true;}
                if(key==KeyBase+4){timeline.Seek((std::min)(doc.finalTurn,timeline.Turn()+1));return true;}
                if(key==KeyBase+5){timeline.Seek(doc.initialTurn);return true;}
                if(key==KeyBase+6){timeline.Seek(doc.finalTurn);return true;}
            }
        }else if(page_==Page::Graphs){
            if(key>=KeyBase+0x1000 && key<KeyBase+0x1000+doc.players.size()){
                const auto player=static_cast<std::size_t>(key-KeyBase-0x1000);
                const auto y=layout.graphLegend.y+float(player)*layout.legendRowPitch-legendScroll_;
                if(y+layout.legendRowHeight<=layout.graphLegend.y || y>=layout.graphLegend.Bottom())return false;
                if(hidden_.count(player))hidden_.erase(player);else hidden_.insert(player);return true;}
            if(key==KeyBase+18)return ScrollLegend(legendScroll_-layout.legendRowPitch,layout);
            if(key==KeyBase+19)return ScrollLegend(legendScroll_+layout.legendRowPitch,layout);
        }else if(page_==Page::Messages && messageViewport_){
            if(key==KeyBase+10)return ScrollMessages(messageScroll_-messageLineStep_,layout);
            if(key==KeyBase+11)return ScrollMessages(messageScroll_+messageLineStep_,layout);
        }
        return false;
    }
    SceneType Scene(const MenuFrontEndAssets& assets) const {
        auto scene=assets.Background();const auto layout=MenuReplayOriginalLayout::At();
        assets.Grid(scene,0,"Grid9DetailFive140",layout.frame.x,layout.frame.y,layout.frame.width,layout.frame.height);
        Image(assets,scene,"topframe.dds",{layout.frame.x+224,layout.frame.y-95,512,128});
        Image(assets,scene,"bottomframe_Thinner.dds",{layout.frame.x+224,layout.frame.Bottom()-99,512,128});
        Text(assets,scene,0,labels_.title.empty()?L"ZeroSis'":labels_.title,layout.frame.x+40,layout.frame.y+26,880,35,MenuFrontEndTextAlign::Center,24);
        Button(assets,scene,35,layout.back,labels_.back.empty()?L"\ub4a4\ub85c":labels_.back);
        if(!timeline_){
            Text(assets,scene,0,labels_.unsupportedReplay,layout.body.x,layout.body.y+80,920,80,MenuFrontEndTextAlign::Center);
            Text(assets,scene,0,std::to_wstring(rawByteCount_)+L" bytes",layout.body.x,layout.body.y+180,920,35,MenuFrontEndTextAlign::Center);
            return scene;
        }
        Image(assets,scene,"HorizontalTrim.dds",{layout.main.x,layout.main.y+30,920,5});
        if(page_==Page::Map)Map(assets,scene,layout);
        else if(page_==Page::Graphs)Graph(assets,scene,layout);
        else Messages(assets,scene,layout);
        const auto pageLabel=page_==Page::Map?labels_.map:page_==Page::Graphs?labels_.graphs:labels_.messages;
        Button(assets,scene,KeyBase+12,layout.selector,pageLabel,true,"GenericPullDown");
        if(selectorOpen_){
            // A real source PullDown occupies one control; its popup rows are
            // shown only while open and cannot route hidden-page callbacks.
            KeepBackAndSelectorHits(scene);const std::wstring names[]={labels_.messages,labels_.graphs,labels_.map};
            const std::uint64_t keys[]={KeyBase+9,KeyBase+8,KeyBase+7};
            for(unsigned i=0;i<3;++i){auto row=layout.selector;row.y+=row.height*(i+1);
                Button(assets,scene,keys[i],row,names[i],true,"GenericPullDown");}
        }else if(dataSetOpen_)DataSetPopup(assets,scene,layout);
        if(!selectorOpen_ && !dataSetOpen_){
            if(ScrollDragging()){scene.hits=captureHits_;scene.scrolls=captureScrolls_;}
            else {lastSceneHits_=scene.hits;lastSceneScrolls_=scene.scrolls;}
        }
        if(scene.sprites.size()>=500000)throw std::length_error("Replay scene exceeds its retained presentation bound");
        return scene;
    }
private:
    enum class Page { Messages,Graphs,Map };
    bool TrackPointer(float x,float y){
        const auto before=PointerGuides();
        pointerAvailable_=std::isfinite(x) && std::isfinite(y);
        pointerX_=pointerAvailable_?x:0;pointerY_=pointerAvailable_?y:0;
        const auto after=PointerGuides();
        if(before.visible!=after.visible)return true;
        if(!after.visible)return false;
        for(std::size_t i=0;i<after.lines.size();++i){const auto& a=before.lines[i];const auto& b=after.lines[i];
            if(a.startX!=b.startX || a.startY!=b.startY || a.endX!=b.endX || a.endY!=b.endY)return true;}
        return false;
    }
    template<class Apply> bool SliderInput(const ZeroSisPresentation::BitmapInputEvent& input,
        const MenuReplayScrollGeometry& geometry,bool horizontal,const Apply& apply){
        using ZeroSisPresentation::BitmapInputKind;
        const auto key=input.controlKey;
        const auto hit=std::find_if(lastSceneHits_.begin(),lastSceneHits_.end(),[&](const ZeroSisPresentation::HitRecord& row){return row.controlKey==key;});
        if(hit==lastSceneHits_.end())return false;
        if(ScrollDragging() && captureKey_!=key){
            if(input.pointerPressId && capturePressId_ && input.pointerPressId<capturePressId_)return false;
            PointerCapture(false);
        }
        const double coordinate=horizontal?input.logicalX:input.logicalY;
        const double origin=input.pointerPressId?(horizontal?input.pointerPressX:input.pointerPressY):coordinate;
        const auto result=input.kind==BitmapInputKind::ControlDrag?
            scrollGesture_.Drag(geometry,input.pointerPressId,origin,coordinate):
            scrollGesture_.Release(geometry,input.pointerPressId,coordinate);
        if(!result.handled)return false;
        if(result.began){captureKey_=key;capturePressId_=input.pointerPressId;captureHits_=lastSceneHits_;captureScrolls_=lastSceneScrolls_;}
        if(!result.preserveCurrent)apply(result.fraction);
        if(result.ended || input.kind==BitmapInputKind::ControlClick)PointerCapture(false);
        return true;
    }
    static std::wstring Wide(const std::string& text){
        std::wstring output;
        for(std::size_t at=0;at<text.size();){const auto first=static_cast<unsigned char>(text[at++]);std::uint32_t scalar=first;unsigned continuation=0;
            if(first>=0xf0){scalar=first&7u;continuation=3;}else if(first>=0xe0){scalar=first&15u;continuation=2;}
            else if(first>=0xc0){scalar=first&31u;continuation=1;}
            for(unsigned i=0;i<continuation;++i)scalar=(scalar<<6)|(static_cast<unsigned char>(text[at++])&63u);
            if(scalar<=0xffff)output.push_back(static_cast<wchar_t>(scalar));
            else{scalar-=0x10000;output.push_back(static_cast<wchar_t>(0xd800+(scalar>>10)));output.push_back(static_cast<wchar_t>(0xdc00+(scalar&1023)));}}
        return output;
    }
    static void Text(const MenuFrontEndAssets& assets,SceneType& scene,std::uint64_t key,const std::wstring& text,
        float x,float y,float width,float height,MenuFrontEndTextAlign align=MenuFrontEndTextAlign::Left,unsigned size=18,Color color={1,1,1,1}){
        const auto& font=assets.FontFace(size,"Shadow");std::vector<std::uint32_t> glyphs;float advance=0;
        for(std::size_t at=0;at<text.size() && glyphs.size()<1024;++at){auto cp=static_cast<std::uint32_t>(text[at]);
            if(cp>=0xd800 && cp<=0xdbff && at+1<text.size()){
                const auto low=static_cast<std::uint32_t>(text[++at]);cp=0x10000+((cp-0xd800)<<10)+(low-0xdc00);}
            if(cp=='\r' || cp=='\n')cp=' ';if(!font.glyphs.count(cp))cp='?';
            glyphs.push_back(cp);const auto& glyph=font.glyphs.at(cp);advance+=glyph.a+glyph.b+glyph.c;
        }
        const float pen=x+(align==MenuFrontEndTextAlign::Center?(width-advance)/2:align==MenuFrontEndTextAlign::Right?width-advance:0);
        const float clip[4]={x,y,x+width,y+height};
        assets.GlyphRun(scene,key,glyphs,pen,y+(std::max)(0.0f,(height-font.lineAdvance)/2)+font.baseline,clip,size,"Shadow",color);
    }
    static void Button(const MenuFrontEndAssets& assets,SceneType& scene,std::uint64_t key,const MenuReplayBounds& bounds,
        const std::wstring& label,bool enabled=true,const std::string& style="SmallButton"){
        assets.StyleButton(scene,key,style,bounds.x,bounds.y,bounds.width,bounds.height,L"",enabled);
        Text(assets,scene,key,label,bounds.x+4,bounds.y,bounds.width-8,bounds.height,MenuFrontEndTextAlign::Center,18,{1,1,1,enabled?1.0f:.38f});
    }
    static void Image(const MenuFrontEndAssets& assets,SceneType& scene,const std::string& name,const MenuReplayBounds& bounds){
        const auto& texture=assets.TextureNamed(name);const float source[]={0,0,float(texture.width),float(texture.height)};
        const float target[]={bounds.x,bounds.y,bounds.Right(),bounds.Bottom()};assets.Texture(scene,0,texture.index,source,target);
    }
    static void ClipSprites(SceneType& scene,std::size_t first,const MenuReplayBounds& bounds){
        auto retained=first;
        for(std::size_t i=first;i<scene.sprites.size();++i){auto& sprite=scene.sprites[i];
            sprite.clipRect[0]=(std::max)(sprite.clipRect[0],bounds.x);sprite.clipRect[1]=(std::max)(sprite.clipRect[1],bounds.y);
            sprite.clipRect[2]=(std::min)(sprite.clipRect[2],bounds.Right());sprite.clipRect[3]=(std::min)(sprite.clipRect[3],bounds.Bottom());
            if(sprite.clipRect[2]>sprite.clipRect[0] && sprite.clipRect[3]>sprite.clipRect[1] &&
               sprite.targetRect[2]>sprite.clipRect[0] && sprite.targetRect[3]>sprite.clipRect[1] &&
               sprite.targetRect[0]<sprite.clipRect[2] && sprite.targetRect[1]<sprite.clipRect[3])scene.sprites[retained++]=sprite;
        }
        scene.sprites.resize(retained);
    }
    static void ScrollButton(const MenuFrontEndAssets& assets,SceneType& scene,std::uint64_t key,const MenuReplayBounds& bounds,bool up,bool enabled){
        assets.StyleButton(scene,key,up?"ScrollBarUp":"ScrollBarDown",bounds.x,bounds.y,bounds.width,bounds.height,L"",enabled);
    }
    static void KeepBackAndSelectorHits(SceneType& scene){
        scene.scrolls.clear();
        scene.scrolls.push_back({0,{0,0,1920,1080}});
        scene.hits.erase(std::remove_if(scene.hits.begin(),scene.hits.end(),[](const ZeroSisPresentation::HitRecord& hit){return hit.controlKey!=35 && hit.controlKey!=KeyBase+12;}),scene.hits.end());
    }
    float LegendMaximum(const MenuReplayOriginalLayout& layout) const {
        const auto count=timeline_->Document().players.size();
        const auto height=count?float(count)*layout.legendRowPitch-(layout.legendRowPitch-layout.legendRowHeight):0;
        return (std::max)(0.0f,height-layout.graphLegend.height);
    }
    bool ScrollLegend(float value,const MenuReplayOriginalLayout& layout){
        const auto next=(std::max)(0.0f,(std::min)(LegendMaximum(layout),value));
        if(next==legendScroll_)return false;legendScroll_=next;return true;
    }
    MenuReplayScrollGeometry LegendSlider(const MenuReplayOriginalLayout& layout) const {
        const double maximum=LegendMaximum(layout),content=maximum+layout.graphLegend.height;
        const auto thumb=(std::max)(18.0,344.0*layout.graphLegend.height/content);
        return MenuReplayScrollGeometry::Create(layout.graphLegend.y+18,344,thumb,MenuReplayScrollModel::Fraction(legendScroll_,maximum));
    }
    MenuReplayScrollGeometry MessageSlider(const MenuReplayOriginalLayout& layout) const {
        const double content=(std::max)(static_cast<double>(layout.text.height),messageViewport_->ContentHeight());
        const auto thumb=(std::max)(18.0,layout.messageTrack.height*layout.text.height/content);
        return MenuReplayScrollGeometry::Create(layout.messageTrack.y,layout.messageTrack.height,thumb,
            MenuReplayScrollModel::Fraction(messageScroll_,messageViewport_->Maximum(layout.text.height)));
    }
    bool ScrollMessages(double offset,const MenuReplayOriginalLayout& layout){
        const auto next=messageViewport_->Clamp(offset,layout.text.height);
        if(next==messageScroll_)return false;messageScroll_=next;return true;
    }
    void LegendCaption(const MenuFrontEndAssets& assets,SceneType& scene,const std::string& source,
        float x,float y,float width,unsigned size) const {
        if(source.empty())return;
        EnsureTextCatalog(assets);const MenuReplayRichText rich(source,0,textCatalog_,{1,1,200.0f/255,1});
        const auto& font=assets.FontFace(size,"Shadow");const float clip[]={x,y,x+width,y+17};
        const float baseline=y+font.baseline;float pen=x,firstX=x;std::size_t count=0;Color selected{};
        std::vector<std::uint32_t> glyphs;
        const auto flush=[&](){if(!glyphs.empty()){assets.GlyphRun(scene,0,glyphs,firstX,baseline,clip,size,"Shadow",selected,true);glyphs.clear();}};
        for(const auto& atom:rich.Atoms()){
            const auto& run=rich.Runs()[atom.run];if(run.prefix)continue;
            if(count++>=1024 || atom.kind==MenuReplayRichText::Kind::Newline)break;
            if(atom.kind==MenuReplayRichText::Kind::Icon){flush();assets.DrawInlineIcon(scene,0,run.icon,pen,baseline,clip,run.color);
                pen+=textCatalog_.icons.at(run.icon).advance;continue;}
            if(atom.kind==MenuReplayRichText::Kind::Tab){flush();const auto& space=font.glyphs.at(' ');pen+=4*(space.a+space.b+space.c);continue;}
            if(atom.kind!=MenuReplayRichText::Kind::Text)continue;
            if(glyphs.empty() || selected.r!=run.color.r || selected.g!=run.color.g || selected.b!=run.color.b || selected.a!=run.color.a){
                flush();firstX=pen;selected=run.color;
            }
            const auto cp=font.glyphs.count(atom.scalar)?atom.scalar:std::uint32_t('?');glyphs.push_back(cp);
            const auto& glyph=font.glyphs.at(cp);pen+=glyph.a+glyph.b+glyph.c;
        }
        flush();
    }
    Color PlayerColor(int player,bool city) const {
        const auto& values=city?palette_.playerPrimary:palette_.playerSecondary;
        return player>=0 && static_cast<std::size_t>(player)<values.size()?values[static_cast<std::size_t>(player)]:Color{.65f,.65f,.65f,1};
    }
    Color GraphColor(int player) const {
        return player>=0 && static_cast<std::size_t>(player)<palette_.graphColors.size()?palette_.graphColors[static_cast<std::size_t>(player)]:PlayerColor(player,false);
    }
    static Color Over(Color color,Color base){return {color.r*color.a+base.r*(1-color.a),color.g*color.a+base.g*(1-color.a),color.b*color.a+base.b*(1-color.a),1};}
    void Map(const MenuFrontEndAssets& assets,SceneType& scene,const MenuReplayOriginalLayout& layout) const {
        const auto& frame=timeline_->Frame();const auto& doc=timeline_->Document();const auto& bounds=layout.map;
        assets.Rect(scene,0,bounds.x,bounds.y,bounds.width,bounds.height,{0,0,0,1});
        const float unit=(std::min)(bounds.width/(static_cast<float>(frame.width)+.5f),bounds.height/(frame.height*.8660254f));
        const float mapWidth=(frame.width+.5f)*unit,mapHeight=frame.height*.8660254f*unit;
        const float left=bounds.x+(bounds.width-mapWidth)*.5f,top=bounds.y+(bounds.height-mapHeight)*.5f;
        const bool fine=frame.plots.size()<=50000 && unit>=3;
        for(const auto& plot:frame.plots){auto found=palette_.terrainColors.find(plot.terrain);Color base=found==palette_.terrainColors.end()?Color{.19f,.22f,.23f,1}:found->second;
            if(plot.cityOwner>=0)base=Over(PlayerColor(plot.cityOwner,true),base);else if(plot.owner>=0)base=Over(PlayerColor(plot.owner,false),base);
            else if(palette_.iceFeature>=0 && plot.feature==palette_.iceFeature)base=Over({189.0f/255,242.0f/255,1,.7f},base);
            const float x=left+(plot.x+.5f*(plot.y&1))*unit,y=top+(frame.height-1-plot.y)*.8660254f*unit;
            if(fine){assets.Rect(scene,0,x+unit*.25f,y,unit*.5f,unit*.2165f,base);assets.Rect(scene,0,x,y+unit*.2165f,unit,unit*.433f,base);
                assets.Rect(scene,0,x+unit*.25f,y+unit*.6495f,unit*.5f,unit*.2165f,base);
                if(plot.cityOwner>=0)assets.Rect(scene,0,x+unit*.35f,y+unit*.3f,unit*.3f,unit*.3f,{1,1,1,1});}
            else assets.Rect(scene,0,x,y,unit,unit*.8660254f,base);}
        const auto turnText=labels_.turnCounter?labels_.turnCounter(frame.turn):labels_.turn+L" "+std::to_wstring(frame.turn);
        Text(assets,scene,0,turnText,layout.turnCaption.x,layout.turnCaption.y,layout.turnCaption.width,layout.turnCaption.height,MenuFrontEndTextAlign::Left,20);
        const auto fraction=MenuReplayScrollModel::Fraction(frame.turn-doc.initialTurn,doc.finalTurn-doc.initialTurn);
        const auto slider=MenuReplayScrollGeometry::Create(layout.slider.x,layout.slider.width,32,fraction);
        assets.Grid(scene,0,"Slider",layout.slider.x,layout.slider.y,layout.slider.width,32);
        assets.Grid(scene,SeekKey,"Slider32",static_cast<float>(slider.thumbOrigin),layout.slider.y,32,32);
        scene.hits.push_back({SeekKey,{layout.slider.x,layout.slider.y,layout.slider.Right(),layout.slider.Bottom()}});
        // Wheel reaches the original TurnSlider while the pointer is over it.
        scene.scrolls.push_back({TurnScrollKey,{layout.slider.x,layout.slider.y,layout.slider.Right(),layout.slider.Bottom()}});
        Button(assets,scene,KeyBase+1,layout.playPause,labels_.playPause);
        Text(assets,scene,0,labels_.terrainReference,layout.main.x,layout.frame.Bottom()-120,920,22,MenuFrontEndTextAlign::Center,18);
    }
    static void SourceLine(SceneType& scene,float x1,float y1,float x2,float y2,float width,Color color,const MenuReplayBounds& clip){
        ZeroSisPresentation::SceneLine line{};line.start[0]=x1;line.start[1]=y1;line.end[0]=x2;line.end[1]=y2;line.width=width;
        line.tintRGBA[0]=color.r;line.tintRGBA[1]=color.g;line.tintRGBA[2]=color.b;line.tintRGBA[3]=color.a;
        line.clipRect[0]=clip.x;line.clipRect[1]=clip.y;line.clipRect[2]=clip.Right();line.clipRect[3]=clip.Bottom();
        line.beforeSprite=static_cast<std::uint32_t>(scene.sprites.size());scene.lines.push_back(line);
    }
    const MenuReplayGraphGeometry& GraphGeometry() const {
        if(!graphGeometry_ || graphDataSet_!=dataSet_){
            graphGeometry_=std::make_unique<MenuReplayGraphGeometry>(BuildMenuReplayGraphGeometry(timeline_->Document(),dataSet_));graphDataSet_=dataSet_;
        }
        return *graphGeometry_;
    }
    std::wstring DataSetLabel(std::size_t index) const {
        const auto& name=timeline_->Document().dataSetNames.at(index);const auto found=palette_.dataSetLabels.find(name);
        return found==palette_.dataSetLabels.end()?Wide(name):found->second;
    }
    void DataSetPopup(const MenuFrontEndAssets& assets,SceneType& scene,const MenuReplayOriginalLayout& layout) const {
        KeepBackAndSelectorHits(scene);scene.hits.push_back({KeyBase+13,{layout.graphSelector.x,layout.graphSelector.y,layout.graphSelector.Right(),layout.graphSelector.Bottom()}});
        const auto& names=timeline_->Document().dataSetNames;
        for(std::size_t index=dataSetPage_*8;index<names.size() && index<(dataSetPage_+1)*8;++index){auto row=layout.graphSelector;
            row.y+=row.height*(float(index-dataSetPage_*8)+1);Button(assets,scene,KeyBase+0x2000+index,row,DataSetLabel(index),true,"GenericPullDown");}
        if(names.size()>8){auto row=layout.graphSelector;row.y+=row.height*9;row.width=190;Button(assets,scene,KeyBase+16,row,L"<",dataSetPage_>0,"GenericPullDown");
            row.x+=210;Button(assets,scene,KeyBase+17,row,L">",(dataSetPage_+1)*8<names.size(),"GenericPullDown");}
    }
    void Graph(const MenuFrontEndAssets& assets,SceneType& scene,const MenuReplayOriginalLayout& layout) const {
        const auto& doc=timeline_->Document();
        if(doc.dataSetNames.empty()){Text(assets,scene,0,labels_.noGraphData,layout.body.x,layout.body.y+140,920,80,MenuFrontEndTextAlign::Center);return;}
        const auto& graph=GraphGeometry();Button(assets,scene,KeyBase+13,layout.graphSelector,DataSetLabel(dataSet_),true,"GenericPullDown");
        const auto left=layout.graph.x,top=layout.graph.y,width=layout.graph.width,height=layout.graph.height;
        assets.Rect(scene,0,left,top,width,height,{0,0,0,200.0f/255});
        const auto dates=GraphDates();const unsigned smallFont=assets.HasFontFace(14,"Shadow")?14:18;
        const Color axisColor{1,1,200.0f/255,1};
        const MenuReplayBounds logicalClip{0,0,1920,1080};
        SourceLine(scene,left,top+height,left+width,top+height,1,axisColor,logicalClip);
        SourceLine(scene,left+width,top,left+width,top+height,1,axisColor,logicalClip);
        for(unsigned tick=0;tick<=40;++tick){const auto x=left+width*float(tick)/40;
            SourceLine(scene,x,top+height,x,top+height+(tick%5==0?10.0f:5.0f),1,axisColor,logicalClip);}
        for(unsigned tick=0;tick<=20;++tick){const auto y=top+height*float(tick)/20;
            SourceLine(scene,left+width,y,left+width+5,y,1,axisColor,logicalClip);}
        if(graph.hasData)for(std::size_t i=0;i<graph.verticalTicks.size();++i)
            Text(assets,scene,0,std::to_wstring(graph.verticalTicks[i]),left+730,top+height-float(i)*90-6,200,17,MenuFrontEndTextAlign::Left,smallFont);
        for(std::size_t i=0;i<dates.size();++i)if(dates[i].available){
            const auto x=left+width*static_cast<float>(i)/4;
            Text(assets,scene,0,dates[i].text,x-90,top+375,180,17,MenuFrontEndTextAlign::Center,smallFont);}
        for(const auto& series:graph.series){if(hidden_.count(static_cast<std::size_t>(series.playerIndex)))continue;
            for(const auto& line:series.lines)SourceLine(scene,left+line.startX,top+line.startY,left+line.endX,top+line.endY,1,GraphColor(series.playerIndex),layout.graph);}
        const auto pointerGuides=PointerGuides();
        if(pointerGuides.visible)for(const auto& line:pointerGuides.lines){
            const auto& c=line.rgba;const Color color{c[0]/255.0f,c[1]/255.0f,c[2]/255.0f,c[3]/255.0f};
            SourceLine(scene,left+static_cast<float>(line.startX),top+static_cast<float>(line.startY),
                left+static_cast<float>(line.endX),top+static_cast<float>(line.endY),static_cast<float>(line.width),color,logicalClip);
        }
        if(!graph.hasData)Text(assets,scene,0,labels_.noGraphData,left,top+height/2-17,width,34,MenuFrontEndTextAlign::Center,20);
        for(std::size_t p=0;p<doc.players.size();++p){
            const MenuReplayBounds row{layout.graphLegend.x,layout.graphLegend.y+float(p)*layout.legendRowPitch-legendScroll_,
                layout.legendRowWidth,layout.legendRowHeight};
            if(row.Bottom()<=layout.graphLegend.y || row.y>=layout.graphLegend.Bottom())continue;
            const auto firstSprite=scene.sprites.size();
            const auto key=KeyBase+0x1000+p;const bool checked=hidden_.count(p)==0;
            const auto name=doc.players[p].civilizationShortName.empty()?doc.players[p].leaderName:doc.players[p].civilizationShortName;
            const auto& caption=p<palette_.playerLabels.size()?palette_.playerLabels[p]:name;
            SourceLine(scene,row.x+40,row.y+8,row.x+110,row.y+8,2,GraphColor(static_cast<int>(p)),layout.graphLegend);
            if(assets.HasTextureNamed("bar300x2.dds")){
                const auto& bar=assets.TextureNamed("bar300x2.dds");const float source[]={0,0,300,1};
                const float target[]={row.x,row.Bottom()-1,row.Right(),row.Bottom()};assets.Texture(scene,0,bar.index,source,target);}
            if(p<palette_.legendIcons.size()){
                const auto& icon=palette_.legendIcons[p];
                if(icon.columns && icon.rows && icon.portrait<static_cast<std::uint64_t>(icon.columns)*icon.rows && assets.HasTextureNamed(icon.texture)){
                    const auto& texture=assets.TextureNamed(icon.texture);
                    const auto u=float((icon.portrait%icon.columns)*32),v=float((icon.portrait/icon.columns)*32);
                    if(u+32<=texture.width && v+32<=texture.height){const float source[]={u,v,u+32,v+32};
                        const float target[]={row.x,row.y-1,row.x+32,row.y+31};assets.Texture(scene,0,texture.index,source,target);}
                }
            }
            LegendCaption(assets,scene,caption,row.x+layout.legendNameOffsetX,row.y+layout.legendNameOffsetY,
                row.width-layout.legendNameOffsetX,smallFont);
            const MenuReplayBounds check{row.Right()-5-32,row.y-1,32,32};
            if(assets.HasTextureNamed("checkbox.dds")){
                const auto& texture=assets.TextureNamed("checkbox.dds");const float offset=checked?32.0f:0.0f;
                const float source[]={0,offset,32,offset+32};const float target[]={check.x,check.y,check.Right(),check.Bottom()};
                assets.Texture(scene,key,texture.index,source,target);
            }else assets.Rect(scene,key,check.x+8,check.y+8,16,16,checked?Color{1,1,.78f,1}:Color{.2f,.2f,.2f,1});
            scene.hits.push_back({key,{check.x,(std::max)(check.y,layout.graphLegend.y),check.Right(),(std::min)(check.Bottom(),layout.graphLegend.Bottom())}});
            auto retained=firstSprite;
            for(std::size_t i=firstSprite;i<scene.sprites.size();++i){auto& sprite=scene.sprites[i];
                sprite.clipRect[0]=(std::max)(sprite.clipRect[0],layout.graphLegend.x);sprite.clipRect[1]=(std::max)(sprite.clipRect[1],layout.graphLegend.y);
                sprite.clipRect[2]=(std::min)(sprite.clipRect[2],layout.graphLegend.Right());sprite.clipRect[3]=(std::min)(sprite.clipRect[3],layout.graphLegend.Bottom());
                if(sprite.clipRect[2]>sprite.clipRect[0] && sprite.clipRect[3]>sprite.clipRect[1] &&
                   sprite.targetRect[2]>sprite.clipRect[0] && sprite.targetRect[3]>sprite.clipRect[1] &&
                   sprite.targetRect[0]<sprite.clipRect[2] && sprite.targetRect[1]<sprite.clipRect[3])scene.sprites[retained++]=sprite;
            }
            scene.sprites.resize(retained);
        }
        if(LegendMaximum(layout)>0){
            const auto x=layout.graphLegend.Right()-18,y=layout.graphLegend.y;
            const MenuReplayBounds previous{x,y,18,18},next{x,y+360,18,18};
            assets.Grid(scene,0,"VertSlider",x,y+18,18,344);
            const auto slider=LegendSlider(layout);
            assets.Grid(scene,LegendSeekKey,"VertShuttle",x,static_cast<float>(slider.thumbOrigin),18,static_cast<float>(slider.thumbLength));
            scene.hits.push_back({LegendSeekKey,{x,y+18,x+18,y+362}});
            scene.scrolls.push_back({LegendScrollKey,{layout.graphLegend.x,y,layout.graphLegend.Right(),layout.graphLegend.Bottom()}});
            ScrollButton(assets,scene,KeyBase+18,previous,true,legendScroll_>0);
            ScrollButton(assets,scene,KeyBase+19,next,false,legendScroll_<LegendMaximum(layout));
        }
    }
    void EnsureTextCatalog(const MenuFrontEndAssets& assets) const {
        if(textAssets_==&assets)return;
        messageViewport_.reset();messagePages_.reset();messageAssets_=nullptr;textCatalog_.colors=palette_.richColors;textCatalog_.icons.clear();
        for(const auto& item:assets.Icons()){const auto& icon=item.second;
            textCatalog_.icons.emplace(item.first,MenuReplayTextIcon{icon.textureIndex,icon.u,icon.v,icon.width,icon.height,icon.advance,icon.originx,icon.originy});}
        textAssets_=&assets;
    }
    void EnsureMessages(const MenuFrontEndAssets& assets) const {
        if(messageAssets_==&assets && messagePages_)return;
        messageViewport_.reset();messagePages_.reset();EnsureTextCatalog(assets);
        messagePages_=std::make_unique<MenuReplayMessagePages>(timeline_->Document(),assets.FontFace(18,"Base"),textCatalog_,
            palette_.messagePrimary,palette_.messageSecondary,890.0f,405.0f);
        messageViewport_=std::make_unique<MenuReplayMessageViewport>(*messagePages_,63);
        messageLineStep_=assets.FontFace(18,"Base").lineAdvance;
        messageScroll_=messageViewport_->Clamp(messageScroll_,405);messageAssets_=&assets;
    }
    void Messages(const MenuFrontEndAssets& assets,SceneType& scene,const MenuReplayOriginalLayout& layout) const {
        EnsureMessages(assets);const auto& pages=*messagePages_;const auto visible=messageViewport_->Visible(messageScroll_,layout.text.height);
        const float clip[4]={layout.text.x,layout.text.y,layout.text.Right(),layout.text.Bottom()};const auto firstSprite=scene.sprites.size();
        for(auto row=visible.first;row<visible.last;++row){const auto& placementRow=pages.Rows()[row];
            const auto& block=pages.Block(placementRow.paragraph);
            const auto y=layout.text.y+static_cast<float>(messageViewport_->RowTop(row)-messageScroll_)+placementRow.before;
            const auto places=block.layout.Place(placementRow.line,layout.text.x,y);
            for(unsigned pass=0;pass<(block.ink.contrastOverlay?2u:1u);++pass){
                std::vector<std::uint32_t> run;float firstX=0,baseline=0;Color color{};bool active=false;std::size_t previousAtom=0;
                auto flush=[&](){if(!run.empty()){assets.GlyphRun(scene,0,run,firstX,baseline,clip,18,"Base",color);run.clear();}active=false;};
                for(const auto& place:places){const auto& atom=block.text.Atoms()[place.atom];const auto& sourceRun=block.text.Runs()[atom.run];
                    const auto selected=pass && !sourceRun.explicitColor?Color{1,1,1,120.0f/255}:sourceRun.color;
                    if(place.kind==MenuReplayRichText::Kind::Icon){flush();assets.DrawInlineIcon(scene,0,sourceRun.icon,place.x,place.baseline,clip,selected);continue;}
                    if(!active || previousAtom+1!=place.atom || selected.r!=color.r || selected.g!=color.g || selected.b!=color.b || selected.a!=color.a){flush();firstX=place.x;baseline=place.baseline;color=selected;active=true;}
                    run.push_back(place.scalar);previousAtom=place.atom;
                }flush();
            }
            if(placementRow.after>0){const auto bottom=layout.text.y+static_cast<float>(messageViewport_->RowEnd(row)-messageScroll_);
                Image(assets,scene,"BlueBar500x3.dds",{layout.text.x,bottom-2,500,1});
                Image(assets,scene,"BlueBar500x3.dds",{layout.text.Right()-500,bottom-2,500,1});}
        }
        ClipSprites(scene,firstSprite,layout.text);
        const auto maximum=messageViewport_->Maximum(layout.text.height);const auto slider=MessageSlider(layout);
        ScrollButton(assets,scene,KeyBase+10,layout.messageUp,true,messageScroll_>0);
        ScrollButton(assets,scene,KeyBase+11,layout.messageDown,false,messageScroll_<maximum);
        assets.Grid(scene,0,"VertSlider",layout.messageTrack.x,layout.messageTrack.y,layout.messageTrack.width,layout.messageTrack.height);
        assets.Grid(scene,MessageSeekKey,"VertShuttle",layout.messageTrack.x,static_cast<float>(slider.thumbOrigin),layout.messageTrack.width,static_cast<float>(slider.thumbLength));
        if(maximum>0)scene.hits.push_back({MessageSeekKey,{layout.messageTrack.x,layout.messageTrack.y,layout.messageTrack.Right(),layout.messageTrack.Bottom()}});
        scene.scrolls.push_back({maximum>0?MessageScrollKey:0,{layout.messages.x,layout.messages.y,layout.messages.Right(),layout.messages.Bottom()}});
    }
    MenuReplayLabels labels_;MenuReplayPalette palette_;std::unique_ptr<MenuReplayTimeline> timeline_;
    std::size_t rawByteCount_=0,dataSet_=0,dataSetPage_=0;float legendScroll_=0;
    mutable double messageScroll_=0,messageLineStep_=25;
    std::uint64_t captureKey_=0,capturePressId_=0;MenuReplayScrollGesture scrollGesture_;
    float pointerX_=0,pointerY_=0;bool pointerAvailable_=false;
    mutable std::vector<ZeroSisPresentation::HitRecord> lastSceneHits_,lastSceneScrolls_;
    std::vector<ZeroSisPresentation::HitRecord> captureHits_,captureScrolls_;
    std::string error_;Page page_=Page::Messages;bool selectorOpen_=false,dataSetOpen_=false;
    std::set<std::size_t> hidden_;mutable MenuReplayTextCatalog textCatalog_;mutable std::unique_ptr<MenuReplayMessagePages> messagePages_;
    mutable std::unique_ptr<MenuReplayMessageViewport> messageViewport_;
    mutable std::unique_ptr<MenuReplayGraphGeometry> graphGeometry_;mutable std::size_t graphDataSet_=static_cast<std::size_t>(-1);
    mutable const MenuFrontEndAssets* messageAssets_=nullptr,*textAssets_=nullptr;
};
}
