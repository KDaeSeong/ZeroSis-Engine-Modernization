// Actual controller/view with a value-only display backend; no HWND or GPU.
#include "menu_frontend_scene_fixture.h"
#include "MenuFrontEndOptionsView.h"
#include <functional>
#include <map>
#include <sstream>

using Model=MenuFrontEndOptionsModel;
using Control=Model::Control;
using Bounds=MenuResolutionPreviewBounds;
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
template<class F>static void Reject(F fn){try{fn();}catch(const std::exception&){Check(true,"rejected");return;}Check(false,"Invalid resolution label/clock accepted");}
static bool Near(float left,float right){return std::fabs(left-right)<.0001f;}
static void Rect(const float* actual,const Bounds& expected){
    Check(Near(actual[0],expected.x) && Near(actual[1],expected.y) && Near(actual[2],expected.Right()) && Near(actual[3],expected.Bottom()),"Scene rectangle differs from source-derived geometry");
}
static void BoundsEqual(const Bounds& actual,const Bounds& expected){
    const float values[]={actual.x,actual.y,actual.Right(),actual.Bottom()};Rect(values,expected);
}
static bool Has(const Scene& scene,std::uint64_t key){for(const auto& hit:scene.hits)if(hit.controlKey==key)return true;return false;}
static std::map<std::string,std::wstring> labels;
static std::map<std::string,Bounds> originalBounds;
struct OriginalSprite final {std::uint32_t texture;float source[4],target[4];};
static std::map<std::string,std::vector<OriginalSprite>> originalStyles;
static unsigned originalMessageLines=0,originalTimerLines=0;
static std::wstring Label(const std::string& key){return labels.at(key);}
static void SceneCheck(const Scene& scene){
    Check(scene.width==1920 && scene.height==1080 && scene.textures.size()==62 && scene.lines.empty(),"Options viewport/immutable texture bank changed");
    Check(scene.sprites.size()<10000,"Resolution confirmation emitted an unbounded Scene");
    for(const auto& sprite:scene.sprites){
        Check(sprite.textureIndex==ZeroSisPresentation::kSolidRectangleTexture || sprite.textureIndex<scene.textures.size(),"Confirmation texture escaped existing bank");
        for(float value:sprite.sourceRect)Check(std::isfinite(value),"Nonfinite source rectangle");
        for(float value:sprite.targetRect)Check(std::isfinite(value),"Nonfinite target rectangle");
        Check(sprite.clipRect[2]>sprite.clipRect[0] && sprite.clipRect[3]>sprite.clipRect[1],"Invalid confirmation clip");
        for(float value:sprite.tintRGBA)Check(std::isfinite(value) && value>=0 && value<=1,"Invalid confirmation tint");
    }
}
static bool Click(Model& model,Control control){Model::Input input;input.key=model.KeyFor(control);return model.InputEvent(input);}
static MenuOptionsCapabilities Capabilities(){
    MenuOptionsCapabilities caps;caps.noBasicHelp=caps.uiCueVolume=caps.windowResolution=caps.fullscreen=caps.vsync=caps.policyInfo=true;return caps;
}
struct Fixture final {
    MenuOptionsValues backend;unsigned applies=0,persists=0;
    std::shared_ptr<MenuOptionsSession> session=std::make_shared<MenuOptionsSession>(backend,Capabilities());
    Model model;
    explicit Fixture(const MenuFrontEndAssets& assets):model(session,
        [this](const MenuOptionsValues& value){++applies;backend=value;return backend;},
        [this](const MenuOptionsValues&){++persists;}){
        ConfigureOriginalFrontEndOptions(assets,model);model.Open();Check(Click(model,Control::VideoTab),"Actual controller cannot open video options");
    }
    Scene Render(const MenuFrontEndAssets& assets,std::uint64_t hovered=0){
        const auto values=model.Values(),oldBackend=backend;const auto oldApplies=applies,oldPersists=persists;
        auto scene=BuildOriginalFrontEndOptions(assets,model,hovered,Label);SceneCheck(scene);
        Check(model.Values()==values && backend==oldBackend && applies==oldApplies && persists==oldPersists,"Rendering changed owned preferences or invoked a backend");
        return scene;
    }
    void Preview(){
        Check(Click(model,Control::Fullscreen) && model.ResolutionChanged(),"Actual controller did not stage a display change");
        Check(Click(model,Control::ApplyResolution) && model.ResolutionPreviewActive(),"ApplyRes did not start the actual owned preview");
    }
};
static std::size_t Barrier(const Scene& scene){
    std::size_t found=scene.sprites.size();
    for(std::size_t i=0;i<scene.sprites.size();++i){const auto& sprite=scene.sprites[i];
        if(sprite.textureIndex==ZeroSisPresentation::kSolidRectangleTexture && sprite.targetRect[0]==0 && sprite.targetRect[1]==0 &&
           sprite.targetRect[2]==1920 && sprite.targetRect[3]==1080 && sprite.tintRGBA[0]==0 && sprite.tintRGBA[1]==0 &&
           sprite.tintRGBA[2]==0 && Near(sprite.tintRGBA[3],128.0f/255))found=i;
    }
    Check(found<scene.sprites.size(),"Source Black.128 full-screen confirmation barrier missing");return found;
}
static void Image(const Scene& scene,std::size_t index,const MenuFrontEndAssets& assets,const char* name,const Bounds& bounds,float alpha=1){
    const auto& texture=assets.TextureNamed(name);const auto& sprite=scene.sprites.at(index);
    Check(sprite.textureIndex==texture.index && sprite.controlKey==0,"Confirmation decoration changed its source order/texture");
    Check(sprite.sourceRect[0]==0 && sprite.sourceRect[1]==0 && sprite.sourceRect[2]==texture.width && sprite.sourceRect[3]==texture.height,"Confirmation cropped original full texture pixels");
    Rect(sprite.targetRect,bounds);Check(sprite.tintRGBA[0]==1 && sprite.tintRGBA[1]==1 && sprite.tintRGBA[2]==1 && Near(sprite.tintRGBA[3],alpha),"Confirmation decoration color/opacity changed");
}
static void Style(const Scene& scene,std::size_t start,const std::vector<OriginalSprite>& original){
    Check(original.size()==9,"Source style does not retain its nine caps");
    for(std::size_t i=0;i<original.size();++i){const auto& sprite=scene.sprites.at(start+i);const auto& expected=original[i];
        Check(sprite.textureIndex==expected.texture,"Source style selected another atlas");
        for(unsigned j=0;j<4;++j)Check(Near(sprite.sourceRect[j],expected.source[j]) && Near(sprite.targetRect[j],expected.target[j]),"Source style cap UV/target differs from active XML");
        for(float value:sprite.tintRGBA)Check(value==1,"Source style changed original tint");
    }
}
static void KeyStyle(const Scene& scene,std::uint64_t key,const std::string& name){
    const auto& expected=originalStyles.at(name);std::size_t first=scene.sprites.size();
    for(std::size_t i=0;i<scene.sprites.size();++i)if(scene.sprites[i].controlKey==key && scene.sprites[i].textureIndex==expected.front().texture){first=i;break;}
    Check(first<scene.sprites.size(),"Source button style missing");Style(scene,first,expected);
}
static void LabelInk(const Scene& scene,std::size_t start,const MenuFrontEndAssets& assets,const Bounds& bounds,unsigned size){
    const auto& font=assets.FontFace(size,"Shadow");const auto& colors=assets.ColorSet("Beige_Black_Alpha");unsigned found=0;
    for(std::size_t i=start;i<scene.sprites.size();++i){const auto& sprite=scene.sprites[i];
        if(!Near(sprite.clipRect[0],bounds.x) || !Near(sprite.clipRect[1],bounds.y) || !Near(sprite.clipRect[2],bounds.Right()) || !Near(sprite.clipRect[3],bounds.Bottom()))continue;
        std::size_t layer=0;while(layer<font.layers.size() && font.layers[layer].texture!=sprite.textureIndex)++layer;
        Check(layer<font.layers.size(),"Countdown label used another font face");const auto& color=colors[(std::min)(layer,colors.size()-1)];
        Check(Near(sprite.tintRGBA[0],color.r) && Near(sprite.tintRGBA[1],color.g) && Near(sprite.tintRGBA[2],color.b) && Near(sprite.tintRGBA[3],color.a),"Countdown label changed source Alpha color set");++found;
    }
    Check(found>0,"Countdown label emitted no original glyph layers");
}
static void ChoiceInk(const Scene& scene,const MenuFrontEndAssets& assets,std::uint64_t key,const std::wstring& text){
    Check(!text.empty(),"Source choice label empty");const auto& font=assets.FontFace(20,"Shadow");const auto& glyph=font.glyphs.at(static_cast<std::uint32_t>(text.front()));
    const auto& colors=assets.ColorSet("Beige_Black");
    for(std::size_t layer=0;layer<font.layers.size();++layer){bool found=false;const auto& color=colors[(std::min)(layer,colors.size()-1)];
        for(const auto& sprite:scene.sprites)if(sprite.controlKey==key && sprite.textureIndex==font.layers[layer].texture &&
           sprite.sourceRect[0]==glyph.u && sprite.sourceRect[1]==glyph.v && sprite.sourceRect[2]==glyph.u+glyph.width && sprite.sourceRect[3]==glyph.v+glyph.height &&
           Near(sprite.tintRGBA[0],color.r) && Near(sprite.tintRGBA[1],color.g) && Near(sprite.tintRGBA[2],color.b) && Near(sprite.tintRGBA[3],color.a))found=true;
        Check(found,"Choice did not preserve original20px Shadow/Beige_Black layers");
    }
}
static void Modal(Fixture& fixture,const MenuFrontEndAssets& assets){
    const auto scene=fixture.Render(assets);const auto keep=fixture.model.KeyFor(Control::KeepResolution),revert=fixture.model.KeyFor(Control::RevertResolution);
    Check(scene.hits.size()==3 && scene.hits[0].controlKey==0 && Has(scene,keep) && Has(scene,revert),"Countdown leaked an underlying option/dropdown callback");
    Check(scene.scrolls.size()==1 && scene.scrolls[0].controlKey==0 && scene.pixelHits.keys.empty() && scene.pixelHits.indices.empty(),"Countdown leaked an underlying wheel/pixel hit surface");
    Rect(scene.hits[0].bounds,{0,0,1920,1080});Rect(scene.scrolls[0].bounds,{0,0,1920,1080});
    for(const auto& hit:scene.hits)if(hit.controlKey)Rect(hit.bounds,originalBounds.at(hit.controlKey==keep?"yes":"no"));
    const auto start=Barrier(scene)+1;
    Style(scene,start,originalStyles.at("frame"));
    const auto decoration=start+originalStyles.at("frame").size();
    Image(scene,decoration,assets,"Dec32x64Left.dds",originalBounds.at("leftDecoration"));
    Image(scene,decoration+1,assets,"Dec32x64Right.dds",originalBounds.at("rightDecoration"));
    Image(scene,decoration+2,assets,"Top512IconTrim.dds",originalBounds.at("topDecoration"));
    Image(scene,decoration+3,assets,"NotificationFrameBase.dds",originalBounds.at("notificationFrame"));
    Image(scene,decoration+4,assets,"NotificationGenericGlow.dds",originalBounds.at("glow"),MenuResolutionPreviewLayout::GlowAlpha(fixture.model.ResolutionPreviewElapsed()));
    const auto layout=MenuResolutionPreviewLayout::At(assets,Label("TXT_KEY_OPSCREEN_RESOLUTION_TIMER"),std::to_wstring(fixture.model.ResolutionCountdownSeconds()));
    BoundsEqual(layout.frame,originalBounds.at("frame"));BoundsEqual(layout.labelStack,originalBounds.at("labelStack"));
    BoundsEqual(layout.message,originalBounds.at("message"));BoundsEqual(layout.timer,originalBounds.at("timer"));
    BoundsEqual(layout.buttonStack,originalBounds.at("buttonStack"));
    LabelInk(scene,start,assets,originalBounds.at("message"),20);LabelInk(scene,start,assets,originalBounds.at("timer"),24);
    KeyStyle(scene,keep,"yes");KeyStyle(scene,revert,"no");
    ChoiceInk(scene,assets,keep,Label("TXT_KEY_YES_BUTTON"));ChoiceInk(scene,assets,revert,Label("TXT_KEY_NO_BUTTON"));
    const auto hovered=fixture.Render(assets,keep);Check(hovered.hits.size()==3,"Hover enabled an underlying callback");KeyStyle(hovered,keep,"yes_hover");
}
static void Measurement(const MenuFrontEndAssets& assets){
    const auto& font=assets.FontFace(20,"Shadow");const auto actual=MeasureMenuResolutionPreviewText(font,Label("TXT_KEY_OPSCREEN_RESOLUTION_TIMER"),300);
    Check(actual.lines==originalMessageLines && actual.height==originalMessageLines*font.lineAdvance,"Original message height was replaced by a fixed box");
    const auto timer=MeasureMenuResolutionPreviewText(assets.FontFace(24,"Shadow"),L"20",300);
    Check(timer.lines==originalTimerLines,"Original timer label measurement changed");
    const auto multiline=MeasureMenuResolutionPreviewText(font,L"A\r\nB\rC\nD",300);Check(multiline.lines==4,"Measurement differs from existing CR/LF/CRLF rendering");
    const std::wstring supplementary={static_cast<wchar_t>(0xd83d),static_cast<wchar_t>(0xde00)};
    const auto fallback=MeasureMenuResolutionPreviewText(font,supplementary,300),question=MeasureMenuResolutionPreviewText(font,L"?",300);
    Check(fallback.width==question.width && fallback.height==question.height,"Supplementary scalar did not preserve existing missing-glyph fallback");
    Reject([&]{MeasureMenuResolutionPreviewText(font,std::wstring(1,static_cast<wchar_t>(0xd800)),300);});
    Reject([&]{MeasureMenuResolutionPreviewText(font,std::wstring(1,static_cast<wchar_t>(0xdc00)),300);});
    Reject([&]{MeasureMenuResolutionPreviewText(font,L"A",0);});
    Reject([&]{MeasureMenuResolutionPreviewText(font,L"A",std::numeric_limits<float>::quiet_NaN());});
    for(unsigned count=0;count<100;++count){const std::wstring text(count,L'A');const auto shortBox=MeasureMenuResolutionPreviewText(font,text,30);
        const auto largeBox=MeasureMenuResolutionPreviewText(font,text,300);Check(shortBox.lines>=largeBox.lines && shortBox.height==shortBox.lines*font.lineAdvance,"Dynamic label rows/height do not follow actual glyph advances");}
    for(unsigned step=0;step<=2000;++step){const auto t=step/100.0;const auto alpha=MenuResolutionPreviewLayout::GlowAlpha(t);
        const auto phase=std::fmod(t,2.0);const auto original=1.0-.5*(phase<=1?phase:2-phase);
        Check(std::isfinite(alpha) && alpha>=.5f && alpha<=1 && std::fabs(alpha-original)<1e-6,"Glow escaped the existing explicit-speed Bounce policy");}
    Check(MenuResolutionPreviewLayout::GlowAlpha(0)==1 && MenuResolutionPreviewLayout::GlowAlpha(1)==.5f && MenuResolutionPreviewLayout::GlowAlpha(2)==1,"Source glow initial/end/repeat values changed");
    Reject([]{MenuResolutionPreviewLayout::GlowAlpha(-1);});Reject([]{MenuResolutionPreviewLayout::GlowAlpha(std::numeric_limits<double>::infinity());});
}
int wmain(int argc,wchar_t** argv){try{
    if(argc!=3)throw std::runtime_error("Expected immutable V3 and source-derived fixture metadata");
    const auto assets=MenuFrontEndAssets::Load(argv[1]);const auto raw=Read(argv[2]);std::size_t at=0;
    auto word=[&](){return U32(raw,at);};
    auto string=[&](){const auto n=word();if(n>65536 || n>raw.size()-at)throw std::runtime_error("Source fixture string bound");std::string value(reinterpret_cast<const char*>(raw.data()+at),n);at+=n;return value;};
    const auto count=word();for(unsigned i=0;i<count;++i){const auto key=string();labels.emplace(key,Widen(string()));}
    auto number=[&](){const auto value=word();float result;std::memcpy(&result,&value,4);return result;};
    const auto bounds=word();for(unsigned i=0;i<bounds;++i){const auto key=string();originalBounds.emplace(key,Bounds{number(),number(),number(),number()});}
    const auto groups=word();for(unsigned group=0;group<groups;++group){const auto key=string();const auto spriteCount=word();auto& sprites=originalStyles[key];
        for(unsigned i=0;i<spriteCount;++i){OriginalSprite sprite{};sprite.texture=word();for(auto& value:sprite.source)value=number();for(auto& value:sprite.target)value=number();sprites.push_back(sprite);}}
    originalMessageLines=word();originalTimerLines=word();Check(at==raw.size(),"Trailing source fixture data");
    Measurement(*assets);BoundsEqual(MenuResolutionPreviewLayout::ApplyResolutionButton(),originalBounds.at("apply"));
    Fixture fixture(*assets);const auto unchanged=fixture.Render(*assets);Check(!Has(unchanged,fixture.model.KeyFor(Control::ApplyResolution)),"Unchanged resolution ApplyRes remained actionable");KeyStyle(unchanged,fixture.model.KeyFor(Control::ApplyResolution),"apply_disabled");
    Check(Click(fixture.model,Control::Fullscreen) && fixture.model.ResolutionChanged(),"Actual model did not stage fullscreen");
    const auto changed=fixture.Render(*assets);Check(Has(changed,fixture.model.KeyFor(Control::ApplyResolution)),"Changed source ApplyRes button missing");KeyStyle(changed,fixture.model.KeyFor(Control::ApplyResolution),"apply_active");
    for(const auto& hit:changed.hits)if(hit.controlKey==fixture.model.KeyFor(Control::ApplyResolution))Rect(hit.bounds,originalBounds.at("apply"));
    Check(Click(fixture.model,Control::ApplyResolution) && fixture.model.ResolutionPreviewActive(),"Actual model did not own the source countdown");
    Modal(fixture,*assets);Check(fixture.model.AdvanceResolutionPreview(.5),"Active source glow did not request a frame update");Modal(fixture,*assets);
    Check(Click(fixture.model,Control::RevertResolution) && !fixture.model.ResolutionPreviewActive() && fixture.model.Opened(),"No did not leave confirmation and retain the options owner");
    SceneCheck(fixture.Render(*assets));fixture.model.Cancel();
    Fixture accepted(*assets);accepted.Preview();Modal(accepted,*assets);Check(Click(accepted.model,Control::KeepResolution) && !accepted.model.ResolutionPreviewActive(),"Yes did not leave confirmation");accepted.model.Cancel();
    Fixture timed(*assets);timed.Preview();Check(timed.model.AdvanceResolutionPreview(120) && !timed.model.ResolutionPreviewActive(),"Expired source confirmation did not disappear");SceneCheck(timed.Render(*assets));timed.model.Cancel();
    std::printf("{\"status\":\"PASS_ACTUAL_OPTIONS_MODEL_ORIGINAL_RESOLUTION_PREVIEW_VIEW\",\"checks\":%u,\"texture_count\":62,\"decorations_reused\":5,\"actual_model_included\":true,\"dynamic_label_stack\":true,\"source_modal_input_isolation\":true,\"native_animation_equivalence\":false,\"host_sdk_hwnd_gpu_or_audio_executed\":false}\n",checks);
    return 0;
}catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}}
