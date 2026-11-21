// Actual immutable V3 bank/controller/view; no SDK, HWND, GPU or audio.
#include "menu_frontend_scene_fixture.h"
#include "MenuFrontEndOptionsView.h"
#include <functional>
#include <map>

using Model=MenuFrontEndOptionsModel;
using Control=Model::Control;
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
static std::map<std::string,std::wstring> labels;
static std::set<std::string> requested;
static std::wstring Label(const std::string& key){requested.insert(key);return labels.at(key);}
struct Rect final {float x=0,y=0,w=0,h=0;};
struct Golden final {bool reward=false,basic=false;Rect stack,rewardRow,basicRow;};
static float Float(const std::vector<unsigned char>& data,std::size_t& at){
    const auto bits=U32(data,at);float result;std::memcpy(&result,&bits,4);return result;
}
static Rect ReadRect(const std::vector<unsigned char>& data,std::size_t& at){return {Float(data,at),Float(data,at),Float(data,at),Float(data,at)};}
static std::string Text(const std::vector<unsigned char>& data,std::size_t& at){
    const auto length=U32(data,at);Check(length<=65536 && length<=data.size()-at,"Reward label/metadata truncated");
    const std::string result(reinterpret_cast<const char*>(data.data()+at),length);at+=length;return result;
}
static bool Has(const Scene& scene,std::uint64_t key){for(const auto& hit:scene.hits)if(hit.controlKey==key)return true;return false;}
static void Rectangle(float x,float y,float w,float h,const Rect& expected){
    Check(x==expected.x && y==expected.y && w==expected.w && h==expected.h,"Reward/basics layout differs from retained Lua/XML oracle");
}
static void Row(const MenuFrontEndAssets::OptionControl& row,const Rect& expected){Rectangle(row.x,row.y,row.width,row.height,expected);}
static void SceneCheck(const Scene& scene){
    Check(scene.width==1920 && scene.height==1080 && scene.textures.size()==62 && scene.lines.empty() && scene.sprites.size()<10000,"Reward view changed the retained Scene/bank contract");
    std::set<std::uint64_t> hits;
    for(const auto& hit:scene.hits)Check(hits.insert(hit.controlKey).second,"Reward view repeats a hit key");
    for(const auto& sprite:scene.sprites){
        Check(sprite.textureIndex==ZeroSisPresentation::kSolidRectangleTexture || sprite.textureIndex<scene.textures.size(),"Reward view texture escaped V3 bank");
        for(float value:sprite.targetRect)Check(std::isfinite(value),"Reward view nonfinite target");
        Check(sprite.clipRect[2]>sprite.clipRect[0] && sprite.clipRect[3]>sprite.clipRect[1],"Reward view invalid clip");
    }
}
static bool Click(Model& model,Control control){Model::Input input;input.key=model.KeyFor(control);return model.InputEvent(input);}
static bool Key(Model& model,unsigned code,bool shift=false){Model::Input input;input.kind=Model::InputKind::Key;input.virtualKey=code;input.shift=shift;return model.InputEvent(input);}
struct Owner final {
    MenuOptionsValues backend{};unsigned applies=0,persists=0;
    std::shared_ptr<MenuOptionsSession> session;Model model;
    static MenuOptionsCapabilities Caps(bool reward,bool basic){
        MenuOptionsCapabilities caps;caps.noRewardPopups=reward;caps.noBasicHelp=basic;caps.windowResolution=caps.fullscreen=caps.vsync=true;return caps;
    }
    Owner(const MenuFrontEndAssets& assets,bool reward,bool basic)
        :session(std::make_shared<MenuOptionsSession>(backend,Caps(reward,basic))),model(session,
            [this](const MenuOptionsValues& value){++applies;backend=value;return backend;},
            [this](const MenuOptionsValues&){++persists;}){
        ConfigureOriginalFrontEndOptions(assets,model);model.Open();
    }
    Scene Render(const MenuFrontEndAssets& assets){
        const auto before=model.Values(),oldBackend=backend;const auto oldApplies=applies,oldPersists=persists;
        requested.clear();auto scene=BuildOriginalFrontEndOptions(assets,model,0,Label);SceneCheck(scene);
        Check(model.Values()==before && backend==oldBackend && applies==oldApplies && persists==oldPersists,"View render changed preferences or invoked a backend");return scene;
    }
};
static void Checkbox(const Scene& scene,const MenuFrontEndAssets& assets,std::uint64_t key,const Rect& expected,bool checked){
    unsigned hits=0,sprites=0;const auto& texture=assets.TextureNamed("checkbox.dds");
    for(const auto& hit:scene.hits)if(hit.controlKey==key){++hits;Rectangle(hit.bounds[0],hit.bounds[1],hit.bounds[2]-hit.bounds[0],hit.bounds[3]-hit.bounds[1],expected);}
    for(const auto& sprite:scene.sprites)if(sprite.controlKey==key && sprite.textureIndex==texture.index){
        ++sprites;Rectangle(sprite.targetRect[0],sprite.targetRect[1],sprite.targetRect[2]-sprite.targetRect[0],sprite.targetRect[3]-sprite.targetRect[1],expected);
        Check(sprite.sourceRect[0]==0 && sprite.sourceRect[1]==(checked?32:0) && sprite.sourceRect[2]==32 && sprite.sourceRect[3]==(checked?64:32),"Reward checked state selected another original atlas cell");}
    Check(hits==1 && sprites==1,"Supported reward checkbox lacks one source-backed hit/atlas cell");
}
static void Packet(const Scene& scene,const std::wstring& path){
    std::ofstream file(path,std::ios::binary);if(!file)throw std::runtime_error("Cannot write owned reward CPU Scene");
    auto word=[&](std::uint32_t value){file.write(reinterpret_cast<const char*>(&value),4);};
    file.write("ZSUPIX02",8);word(scene.width);word(scene.height);word(static_cast<std::uint32_t>(scene.textures.size()));
    word(static_cast<std::uint32_t>(scene.sprites.size()));word(static_cast<std::uint32_t>(scene.hits.size()));word(static_cast<std::uint32_t>(scene.scrolls.size()));
    for(const auto& texture:scene.textures){const auto text=Narrow(texture.path);word(static_cast<std::uint32_t>(text.size()));file.write(text.data(),static_cast<std::streamsize>(text.size()));}
    for(const auto& sprite:scene.sprites){word(sprite.textureIndex);file.write(reinterpret_cast<const char*>(&sprite.controlKey),8);file.write(reinterpret_cast<const char*>(sprite.sourceRect),64);}
    for(const auto* rows:{&scene.hits,&scene.scrolls})for(const auto& row:*rows){file.write(reinterpret_cast<const char*>(&row.controlKey),8);file.write(reinterpret_cast<const char*>(row.bounds),16);}
    Check(bool(file),"Reward CPU Scene write incomplete");
}
int wmain(int argc,wchar_t** argv){try{
    if(argc!=4)throw std::runtime_error("Expected V3 assets, source metadata, owned CPU packet output");
    const auto assets=MenuFrontEndAssets::Load(argv[1]);const auto metadata=Read(argv[2]);
    Check(metadata.size()>=12 && !std::memcmp(metadata.data(),"ZSRWDO01",8),"Reward source metadata header changed");std::size_t at=8;
    const auto count=U32(metadata,at);Check(count>0 && count<100,"Reward localization count invalid");
    for(unsigned i=0;i<count;++i){const auto key=Text(metadata,at);labels.emplace(key,Widen(Text(metadata,at)));}
    const auto combinations=U32(metadata,at);Check(combinations==4,"Reward capability matrix missing");
    std::vector<Golden> goldens;
    for(unsigned i=0;i<combinations;++i){Golden golden;const auto mask=U32(metadata,at);golden.reward=(mask&1)!=0;golden.basic=(mask&2)!=0;
        golden.stack=ReadRect(metadata,at);golden.rewardRow=ReadRect(metadata,at);golden.basicRow=ReadRect(metadata,at);goldens.push_back(golden);}
    Check(at==metadata.size(),"Trailing reward metadata bytes");
    Check(static_cast<unsigned>(Control::NoRewardPopups)==17 && static_cast<unsigned>(Control::NoBasicHelp)==10,"Existing/new checkbox control IDs changed");
    Check(MenuRewardOptionsLayout::RewardLabelKey()==std::string("TXT_KEY_OPSCREEN_NO_REWARD_POPUPS") &&
        MenuRewardOptionsLayout::RewardTooltipKey()==std::string("TXT_KEY_OPSCREEN_NO_REWARD_POPUPS_TT"),"Source reward label/tooltip key changed");
    bool absent=false;try{assets->OptionsControl("NoRewardPopupsCheckbox");}catch(const std::out_of_range&){absent=true;}
    Check(absent,"Immutable V3 asset map unexpectedly gained an option row");
    for(unsigned size:{18u,20u,22u})for(const auto* key:{MenuRewardOptionsLayout::RewardLabelKey(),MenuRewardOptionsLayout::RewardTooltipKey()})
        for(const auto scalar:labels.at(key))Check(assets->FontFace(size,"Shadow").glyphs.count(static_cast<std::uint32_t>(scalar))!=0,"Original reward localization requires a missing existing glyph");
    unsigned renderedStates=0;
    for(const auto& golden:goldens){
        const auto layout=MenuRewardOptionsLayout::At(*assets,golden.reward,golden.basic);
        Check(layout.hasReward==golden.reward && layout.hasBasic==golden.basic,"Reward layout capability mask changed");
        Rectangle(layout.stackX,layout.stackY,layout.stackWidth,layout.stackHeight,golden.stack);
        if(golden.reward)Row(layout.reward,golden.rewardRow);if(golden.basic)Row(layout.basic,golden.basicRow);
        Owner owner(*assets,golden.reward,golden.basic);auto scene=owner.Render(*assets);++renderedStates;
        const auto rewardKey=owner.model.KeyFor(Control::NoRewardPopups),basicKey=owner.model.KeyFor(Control::NoBasicHelp);
        Check(Has(scene,rewardKey)==golden.reward && Has(scene,basicKey)==golden.basic,"Unsupported reward/basic row became clickable");
        if(golden.basic)Checkbox(scene,*assets,basicKey,golden.basicRow,false);
        if(golden.reward){
            Check(requested.count(MenuRewardOptionsLayout::RewardLabelKey())==1,"Source reward caption was not requested");Checkbox(scene,*assets,rewardKey,golden.rewardRow,false);
            Check(owner.model.Focus()==Control::NoRewardPopups,"Reward did not precede basic in source-derived keyboard order");
            Check(Key(owner.model,32) && owner.model.Values().noRewardPopups && !owner.backend.noRewardPopups && owner.persists==0,"Reward keyboard edit leaked before explicit commit");
            scene=owner.Render(*assets);++renderedStates;Checkbox(scene,*assets,rewardKey,golden.rewardRow,true);
            if(golden.basic){
                Packet(scene,argv[3]);Check(Key(owner.model,9) && owner.model.Focus()==Control::NoBasicHelp,"Keyboard Tab skipped the next supported original checkbox");
                Check(Key(owner.model,9,true) && owner.model.Focus()==Control::NoRewardPopups,"Keyboard ShiftTab did not restore source checkbox order");
            }
            owner.model.Cancel();Check(!owner.backend.noRewardPopups && owner.persists==0,"Cancel persisted the new reward draft");
        }else owner.model.Cancel();
    }
    {
        const auto baseline=assets->OptionsControl("NoBasicHelpCheckbox");
        for(unsigned field=0;field<6;++field){
            auto invalid=baseline;
            if(field==0)invalid.width=31;if(field==1)invalid.height=31;if(field==2)invalid.key=17;
            if(field==3)invalid.textKey="unsupported";if(field==4)invalid.x=std::numeric_limits<float>::quiet_NaN();if(field==5)invalid.y=0;
            bool rejected=false;try{MenuRewardOptionsLayout::FromBaseline(invalid,true,true);}catch(const std::invalid_argument&){rejected=true;}
            Check(rejected,"Invalid immutable reward baseline escaped its finite/candidate/viewport contract");
        }
    }
    {
        Owner owner(*assets,true,true);Check(Click(owner.model,Control::VideoTab),"Video regression route missing");
        auto scene=owner.Render(*assets);Check(!Has(scene,owner.model.KeyFor(Control::NoRewardPopups)),"Reward checkbox leaked onto video page");
        Check(!Click(owner.model,Control::NoRewardPopups),"Hidden reward callback changed video-page state");
        Check(Click(owner.model,Control::Fullscreen) && Click(owner.model,Control::ApplyResolution) && owner.model.ResolutionPreviewActive(),"Existing20-second resolution preview route changed");
        scene=owner.Render(*assets);Check(!Has(scene,owner.model.KeyFor(Control::NoRewardPopups)),"Reward checkbox escaped the resolution modal barrier");
        Check(Click(owner.model,Control::NoRewardPopups) && !owner.model.Values().noRewardPopups,"Modal consumed hidden reward click as an option edit");
        Check(Key(owner.model,27) && owner.model.Opened() && !owner.model.ResolutionPreviewActive(),"Resolution Escape regression after reward restoration");owner.model.Cancel();
    }
    std::printf("{\"status\":\"PASS_SOURCE_REWARD_LAYOUT_AND_ACTUAL_V3_MODEL_VIEW_CXX14\",\"checks\":%u,\"capability_combinations\":4,\"rendered_game_states\":%u,\"immutable_v3_reused\":true,\"source_callback_and_stack_oracle_required\":true,\"native_execution\":false}\n",checks,renderedStates);return 0;
}catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}}
