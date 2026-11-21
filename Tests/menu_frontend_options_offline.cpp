#include "menu_frontend_scene_fixture.h"
#include "MenuFrontEndOptionsView.h"
#include "MenuResolutionPreviewClock.h"
#include <thread>
static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}
template<class F>static void Reject(F fn){try{fn();}catch(const std::exception&){Check(true,"rejected");return;}Check(false,"Invalid request accepted");}
using Model=MenuFrontEndOptionsModel;using Control=Model::Control;using Page=Model::Page;
static bool Click(Model& model,Control control){Model::Input input;input.key=model.KeyFor(control);return model.InputEvent(input);}
static bool Key(Model& model,unsigned key,bool shift=false){Model::Input input;input.kind=Model::InputKind::Key;input.virtualKey=key;input.shift=shift;return model.InputEvent(input);}
static bool HoverKey(Model& model,unsigned key,std::uint64_t hover,bool shift=false){Model::Input input;input.kind=Model::InputKind::Key;input.virtualKey=key;input.shift=shift;input.hover=hover;return model.InputEvent(input);}
static bool VolumeKey(Model& model,unsigned key,bool shift=false){return HoverKey(model,key,model.KeyFor(Control::Volume),shift);}
static bool Wheel(Model& model,float delta){Model::Input input;input.kind=Model::InputKind::Wheel;input.key=model.KeyFor(Control::Volume);input.wheel=delta;return model.InputEvent(input);}
static_assert(Model::OriginalVolumeSliderWheelSteps==1,"OptionsMenu.xml EffectsVolumeSlider WheelSteps differs");
static void WriteScene(const Scene& scene,const std::wstring& path){
    std::ofstream file(path,std::ios::binary);if(!file)throw std::runtime_error("Cannot write owned options proof");
    auto word=[&](std::uint32_t value){file.write(reinterpret_cast<const char*>(&value),4);};
    file.write("ZSUPIX02",8);word(scene.width);word(scene.height);word(static_cast<std::uint32_t>(scene.textures.size()));word(static_cast<std::uint32_t>(scene.sprites.size()));word(static_cast<std::uint32_t>(scene.hits.size()));word(static_cast<std::uint32_t>(scene.scrolls.size()));
    for(const auto& texture:scene.textures){const auto text=Narrow(texture.path);word(static_cast<std::uint32_t>(text.size()));file.write(text.data(),static_cast<std::streamsize>(text.size()));}
    for(const auto& sprite:scene.sprites){word(sprite.textureIndex);file.write(reinterpret_cast<const char*>(&sprite.controlKey),8);file.write(reinterpret_cast<const char*>(sprite.sourceRect),64);}
    for(const auto* hits:{&scene.hits,&scene.scrolls})for(const auto& hit:*hits){file.write(reinterpret_cast<const char*>(&hit.controlKey),8);file.write(reinterpret_cast<const char*>(hit.bounds),16);}
}
static void ChooseResolution(Model& model,std::size_t row){
    Click(model,Control::VideoTab);Click(model,Control::Resolution);Model::Input input;input.key=model.ResolutionKey(row);
    Check(model.InputEvent(input) && !model.DropdownOpened(),"Actual resolution row selection failed");
}
static void ChangeVolume(Model& model,int value){
    Click(model,Control::AudioTab);Model::Input input;input.key=model.KeyFor(Control::Volume);
    input.x=model.VolumeLeft()+16+(model.VolumeWidth()-32)*value/100.0f;input.y=model.VolumeTop()+16;
    Check(model.InputEvent(input) && model.Values().uiCueVolumePercent==value,"Actual volume draft selection failed");
}
static void RewardModelIntegration(const MenuFrontEndAssets& assets,
    const std::function<std::wstring(const std::string&)>& label){
    static_assert(static_cast<unsigned>(Control::NoBasicHelp)==10 && static_cast<unsigned>(Control::ApplyResolution)==16 &&
        static_cast<unsigned>(Control::NoRewardPopups)==17 && static_cast<unsigned>(Control::KeepResolution)==23,
        "Existing option control identities must not migrate");
    for(unsigned support=0;support<4;++support){
        MenuOptionsCapabilities caps;caps.noBasicHelp=(support&1)!=0;caps.noRewardPopups=(support&2)!=0;
        MenuOptionsValues backend;unsigned writes=0;auto session=std::make_shared<MenuOptionsSession>(backend,caps);
        Model model(session,[&](const MenuOptionsValues& v){backend=v;return backend;},[&](const MenuOptionsValues&){++writes;});
        Check(model.Available()==(support!=0) && model.PageSupported(Page::Game)==(support!=0),"Game page capability union differs from its real backends");
        if(!support)continue;
        model.Open();Check(model.Focus()==((support&2)?Control::NoRewardPopups:Control::NoBasicHelp),"Original source control order was not used for initial focus");
        if(support&2){
            Check(Key(model,32) && model.Values().noRewardPopups && !backend.noRewardPopups,"Keyboard reward edit escaped its private cache");
            if(support&1){Check(Key(model,9) && model.Focus()==Control::NoBasicHelp,"Keyboard focus did not follow original reward/basic order");
                Check(Key(model,9,true) && model.Focus()==Control::NoRewardPopups,"Reverse focus order did not return to reward checkbox");}
        }else Check(!Click(model,Control::NoRewardPopups) && !model.Values().noRewardPopups,"Unavailable reward backend accepted a forged control");
        const auto scene=BuildOriginalFrontEndOptions(assets,model,0,label);unsigned rewardHits=0,basicHits=0;
        for(const auto& hit:scene.hits){if(hit.controlKey==model.KeyFor(Control::NoRewardPopups))++rewardHits;if(hit.controlKey==model.KeyFor(Control::NoBasicHelp))++basicHits;}
        Check(rewardHits==((support&2)?1u:0u) && basicHits==((support&1)?1u:0u),"Actual view exposed a hidden or missing reward/basic input");
        model.Cancel();Check(writes==0 && !backend.noRewardPopups,"Cancelling a new reward edit persisted preferences");
    }
    MenuOptionsCapabilities caps;caps.noRewardPopups=caps.noBasicHelp=caps.windowResolution=caps.fullscreen=caps.vsync=true;
    MenuOptionsValues backend;auto session=std::make_shared<MenuOptionsSession>(backend,caps);
    auto confirmed=std::make_shared<std::atomic<bool>>(false);session->BindNoRewardPopupsSnapshot(confirmed);
    std::string saved=MenuOptionsValues::Encode(backend);unsigned writes=0;bool fail=false;
    auto apply=[&](const MenuOptionsValues& value){backend=value;return backend;};
    auto persist=[&](const MenuOptionsValues& value){
        Check(confirmed->load(std::memory_order_acquire)==session->Committed().noRewardPopups,"SDK confirmed snapshot changed before atomic persistence completed");
        if(fail)throw std::runtime_error("Injected reward setting storage failure");saved=MenuOptionsValues::Encode(value);++writes;
    };
    Model model(session,apply,persist);ConfigureOriginalFrontEndOptions(assets,model);model.Open();
    const auto oldKey=model.KeyFor(Control::NoRewardPopups);Click(model,Control::NoRewardPopups);ChooseResolution(model,0);Click(model,Control::ApplyResolution);
    Check(model.ResolutionPreviewActive() && !confirmed->load() && !backend.noRewardPopups && writes==0,"Dedicated resolution apply leaked an unrelated reward draft");
    Click(model,Control::KeepResolution);
    Check(model.Opened() && model.Values().noRewardPopups && !session->Committed().noRewardPopups && !confirmed->load() && writes==1,
        "Display confirmation promoted a cached reward draft");
    Check(MenuOptionsValues::SchemaVersion(saved)==3 && !MenuOptionsValues::Decode(saved).noRewardPopups,"Display-only migration did not persist the committed reward default");
    model.Cancel();model.Open();Model::Input stale;stale.key=oldKey;
    Check(!model.InputEvent(stale) && !model.Values().noRewardPopups,"A prior reward control token crossed transactions");
    Click(model,Control::NoRewardPopups);ChooseResolution(model,1);Click(model,Control::Accept);
    Check(model.ResolutionPreviewActive() && confirmed->load() && session->Committed().noRewardPopups && MenuOptionsValues::Decode(saved).noRewardPopups && writes==2,
        "Original Accept did not commit reward preferences before asking about display changes");
    model.AdvanceResolutionPreview(21);
    Check(model.Opened() && !model.ResolutionPreviewActive() && confirmed->load() && backend.noRewardPopups && writes==2,
        "Display timeout undid an already committed reward preference");
    model.Cancel();model.Open();Click(model,Control::NoRewardPopups);const auto previous=saved;fail=true;Click(model,Control::Accept);fail=false;
    Check(!model.Opened() && model.LastResult()==Model::Result::ApplyFailed && confirmed->load() && backend.noRewardPopups && saved==previous && writes==2,
        "Failed reward persistence changed the SDK snapshot or confirmed bytes");
    model.Open();Click(model,Control::Defaults);Check(!model.Values().noRewardPopups && confirmed->load(),"Reset defaults bypassed the cached reward transaction");
    model.Cancel();Check(confirmed->load() && saved==previous,"Cancelling reward defaults changed confirmed settings");
    model.Open();Click(model,Control::Accept);Check(writes==2 && confirmed->load(),"An unchanged Apply rewrote or migrated private settings");
}
static void ResolutionPreviewIntegration(const MenuFrontEndAssets& assets,
    const std::function<std::wstring(const std::string&)>& label,const std::wstring& directory){
    MenuOptionsCapabilities caps;caps.noBasicHelp=caps.uiCueVolume=caps.windowResolution=caps.fullscreen=caps.vsync=caps.policyInfo=true;
    MenuOptionsValues initial,backend=initial;auto session=std::make_shared<MenuOptionsSession>(initial,caps);
    MenuResolutionPreviewClock clock;MenuResolutionCountdown timer;double elapsed=99;
    Check(!clock.Sample(0,false,&elapsed) && elapsed==0,"Inactive display clock consumed unrelated frame time");
    // A mode switch started at0 but did not complete until21000ms. The new
    // twenty-second interval starts after that operation, not at frame start.
    timer.Start();clock.Start(21000);Check(!clock.Sample(21000,true,&elapsed) && timer.Remaining()==20,"Slow mode application consumed the confirmation interval");
    Check(clock.Sample(21001,true,&elapsed) && elapsed==.001 && !timer.Advance(elapsed),"First post-apply clock sample differs from real elapsed time");
    Check(clock.Sample(81001,true,&elapsed) && elapsed==60 && timer.Advance(elapsed),"A later stalled frame was clamped or failed to expire");
    clock.Stop();clock.Start(90000);Check(clock.Sample(91000,true,&elapsed) && elapsed==1,"Repeated preview reused an older start clock");
    Check(!clock.Sample(92000,false,&elapsed) && !clock.Active(),"Closed preview retained its time origin");
    std::string saved=MenuOptionsValues::Encode(initial);bool failPersist=false;unsigned persists=0;
    auto apply=[&](const MenuOptionsValues& value){backend=value;return backend;};
    auto persist=[&](const MenuOptionsValues& value){++persists;if(failPersist)throw std::runtime_error("Injected display confirmation persistence failure");saved=MenuOptionsValues::Encode(value);};
    Model model(session,apply,persist);ConfigureOriginalFrontEndOptions(assets,model);model.Open();
    ChooseResolution(model,0);Click(model,Control::GameTab);Click(model,Control::NoBasicHelp);ChangeVolume(model,42);Click(model,Control::VideoTab);
    Check(model.ResolutionChanged() && Click(model,Control::ApplyResolution) && model.ResolutionPreviewActive(),"Original ApplyResButton did not start its preview");
    Check(backend.windowWidth==1024 && backend.windowHeight==768 && !backend.noBasicHelp && backend.uiCueVolumePercent==100 &&
        saved==MenuOptionsValues::Encode(initial) && persists==0,"Dedicated resolution preview committed unrelated drafts or preferences");
    const auto preview=BuildOriginalFrontEndOptions(assets,model,0,label);
    Check(preview.hits.size()==3 && preview.scrolls.size()==1 && preview.hits.front().controlKey==0 && preview.scrolls.front().controlKey==0,
        "Resolution confirmation did not isolate two source buttons behind a consuming screen barrier");
    for(const auto& hit:preview.hits)Check(hit.controlKey==0 || hit.controlKey==model.KeyFor(Control::KeepResolution) || hit.controlKey==model.KeyFor(Control::RevertResolution),"Countdown exposed an underlying control");
    WriteScene(preview,directory+L"\\options_resolution_preview.packet");
    const auto cached=model.Values();Click(model,Control::GameTab);Click(model,Control::Defaults);Click(model,Control::Cancel);
    Check(model.ResolutionPreviewActive() && model.Values()==cached && model.CurrentPage()==Page::Video,"Modal preview allowed an underlying edit or cancel action");
    Reject([&]{model.ApplyChanges();});
    const auto age=model.ResolutionPreviewElapsed();bool rejectedThread=false;
    std::thread other([&]{try{model.AdvanceResolutionPreview(.5);}catch(const std::exception&){rejectedThread=true;}});other.join();
    Check(rejectedThread && model.ResolutionPreviewElapsed()==age,"Foreign thread advanced the owned resolution deadline");
    Check(model.AdvanceResolutionPreview(0) && model.ResolutionCountdownSeconds()==21,"Original zero-delta countdown display was changed");
    Check(model.AdvanceResolutionPreview(.125) && model.ResolutionCountdownSeconds()==20 && model.ResolutionPreviewElapsed()==.125,"Subsecond countdown/animation tick was lost");
    Check(model.AdvanceResolutionPreview(45) && model.Opened() && !model.ResolutionPreviewActive(),"A long frame stall did not immediately revert and retain options");
    Check(backend==initial && saved==MenuOptionsValues::Encode(initial) && model.Values().noBasicHelp && model.Values().uiCueVolumePercent==42 &&
        model.Values().windowWidth==initial.windowWidth,"Timeout changed dedicated-apply drafts or persisted data");
    ChooseResolution(model,0);Click(model,Control::ApplyResolution);Click(model,Control::KeepResolution);
    auto accepted=initial;accepted.windowWidth=1024;accepted.windowHeight=768;
    Check(model.Opened() && !model.ResolutionPreviewActive() && session->Committed()==accepted && saved==MenuOptionsValues::Encode(accepted) &&
        model.Values().noBasicHelp && model.Values().uiCueVolumePercent==42,"Yes did not promote display-only baseline while retaining unrelated drafts");
    model.Cancel();Check(!session->Active() && backend==accepted && saved==MenuOptionsValues::Encode(accepted),"Cancel undid an already confirmed display mode");
    model.Open();ChooseResolution(model,1);Click(model,Control::GameTab);Click(model,Control::NoBasicHelp);ChangeVolume(model,64);
    Click(model,Control::VideoTab);Click(model,Control::VSync);Click(model,Control::Accept);
    auto nonResolution=accepted;nonResolution.noBasicHelp=true;nonResolution.uiCueVolumePercent=64;nonResolution.vsync=false;
    Check(model.ResolutionPreviewActive() && session->Committed()==nonResolution && saved==MenuOptionsValues::Encode(nonResolution) && backend.windowWidth==1280,
        "Original Accept path failed to commit non-resolution values before preview");
    Check(Key(model,27) && model.Opened() && !model.ResolutionPreviewActive() && backend==nonResolution && saved==MenuOptionsValues::Encode(nonResolution),
        "Escape did not preserve already committed Accept-path settings and stay in options");
    model.Cancel();const auto baseline=session->Committed();const auto oldSaved=saved;
    {Model owned(session,apply,persist);ConfigureOriginalFrontEndOptions(assets,owned);owned.Open();ChooseResolution(owned,1);Click(owned,Control::ApplyResolution);
        Check(owned.ResolutionPreviewActive() && backend.windowWidth==1280,"Destructor preview fixture did not apply candidate mode");}
    Check(!session->Active() && backend==baseline && saved==oldSaved,"Owned controller destruction did not restore its pending display");
    model.Open();ChooseResolution(model,1);Click(model,Control::ApplyResolution);failPersist=true;Click(model,Control::KeepResolution);failPersist=false;
    Check(!model.Opened() && !session->Active() && model.LastResult()==Model::Result::ApplyFailed && backend==baseline && saved==oldSaved,
        "Confirmation storage failure did not restore the last-confirmed display and old bytes");
    {
        auto broken=std::make_shared<MenuOptionsSession>(initial,caps);bool failRestore=false;MenuOptionsValues actual=initial;
        auto failing=[&](const MenuOptionsValues& value){if(failRestore && value==initial)throw std::runtime_error("Injected preview restore failure");actual=value;return actual;};
        Model fault(broken,failing,[](const MenuOptionsValues&){});ConfigureOriginalFrontEndOptions(assets,fault);fault.Open();ChooseResolution(fault,0);Click(fault,Control::ApplyResolution);
        failRestore=true;fault.AdvanceResolutionPreview(25);
        Check(!fault.Opened() && broken->Faulted() && !broken->Active() && fault.LastResult()==Model::Result::RollbackFailed,"Timed restore failure left an actionable options transaction");
    }
    {
        auto broken=std::make_shared<MenuOptionsSession>(initial,caps);bool failRestore=false;
        auto failing=[&](const MenuOptionsValues& value){if(failRestore && value==initial)throw std::runtime_error("Injected destructor restore failure");return value;};
        {Model owned(broken,failing,[](const MenuOptionsValues&){});ConfigureOriginalFrontEndOptions(assets,owned);owned.Open();ChooseResolution(owned,0);Click(owned,Control::ApplyResolution);failRestore=true;}
        Check(broken->Faulted() && !broken->Active(),"Destructor restore failure escaped or left an active owner");
    }
    Check(!model.AdvanceResolutionPreview(90),"Closed controller consumed an expired timer tick");
    Reject([&]{model.AdvanceResolutionPreview(std::numeric_limits<double>::infinity());});
}
int wmain(int argc,wchar_t** argv){
    try{
        if(argc!=6)throw std::runtime_error("Expected V2,V1,labels,owned proof directory and current V3 assets");
        auto assets=MenuFrontEndAssets::Load(argv[1]);auto v1=MenuFrontEndAssets::Load(argv[2]);
        Check(assets->Extended() && !v1->Extended(),"V1 compatibility and V2 extension detection");
        Check(v1->Fonts().size()==3 && assets->Fonts().size()==3,"Legacy three Shadow face API preserved");
        Check(assets->Icons().size()==148,"Exact original icon count");
        Check(assets->FontFace(18,"Base").lineAdvance>0 && assets->FontFace(20,"SoftShadow").lineAdvance>0,"Original new font styles");
        Check(assets->TextureNamed("BlueBar500x3.dds").width==500,"Named original separator texture");
        std::vector<std::pair<unsigned,unsigned>> textureSizes;
        for(const auto& texture:assets->Background().textures){const auto header=Read(texture.path);std::size_t cursor=12;
            auto height=U32(header,cursor),width=U32(header,cursor);textureSizes.push_back({width,height});}
        auto checkScene=[&](const Scene& scene){
            for(const auto& sprite:scene.sprites)if(sprite.textureIndex!=ZeroSisPresentation::kSolidRectangleTexture){
                const auto& size=textureSizes.at(sprite.textureIndex);
                Check(sprite.sourceRect[0]>=0 && sprite.sourceRect[1]>=0 && sprite.sourceRect[2]<=size.first && sprite.sourceRect[3]<=size.second,"Original source UV escaped DDS");}
        };
        const auto bytes=Read(argv[3]);std::size_t pos=0;auto count=U32(bytes,pos);std::map<std::string,std::wstring> labels;
        for(unsigned i=0;i<count;++i){auto n=U32(bytes,pos);std::string key(reinterpret_cast<const char*>(bytes.data()+pos),n);pos+=n;
            n=U32(bytes,pos);std::string text(reinterpret_cast<const char*>(bytes.data()+pos),n);pos+=n;labels.emplace(key,Widen(text));}
        Check(pos==bytes.size(),"Exact label fixture consumption");auto label=[&](const std::string& key){return labels.at(key);};
        MenuOptionsCapabilities caps;caps.noBasicHelp=caps.uiCueVolume=caps.windowResolution=caps.fullscreen=caps.vsync=caps.policyInfo=true;
        MenuOptionsValues initial;initial.windowWidth=1536;initial.windowHeight=864;
        auto session=std::make_shared<MenuOptionsSession>(initial,caps);MenuOptionsValues backend=initial;
        unsigned applies=0,persists=0;std::string persisted=MenuOptionsValues::Encode(initial);bool failPersist=false;
        auto apply=[&](const MenuOptionsValues& value){++applies;backend=value;return backend;};
        auto persist=[&](const MenuOptionsValues& value){++persists;if(failPersist)throw std::runtime_error("Injected persistence failure");persisted=MenuOptionsValues::Encode(value);};
        Model unavailable(nullptr,apply,persist);Check(!unavailable.Available(),"Absent model cannot open");Reject([&]{unavailable.Open();});
        Model noApply(session,{},persist);Check(!noApply.Available(),"Missing actual callback cannot open");
        session->Begin(2,20);{Model contender(session,apply,persist);Reject([&]{contender.Open();});}
        Check(session->Active(),"Rejected controller did not discard other consumer");session->Cancel(2,20);
        bool wrongThread=false;std::thread worker([&]{try{Model other(session,apply,persist);other.Available();}catch(const std::exception&){wrongThread=true;}});worker.join();Check(wrongThread,"Foreign thread rejected");
        Model model(session,apply,persist);ConfigureOriginalFrontEndOptions(*assets,model);model.Open();
        Check(model.VolumeTop()==414 && model.VolumeWidth()==500,"Original source-derived slider geometry");
        Check(model.Resolutions().size()==7,"Actual custom resolution retained");
        const auto oldKey=model.KeyFor(Control::NoBasicHelp);Click(model,Control::NoBasicHelp);Check(model.Values().noBasicHelp && !backend.noBasicHelp,"Edit remains cached until Apply");
        model.Cancel();Check(!session->Active() && persisted==MenuOptionsValues::Encode(initial) && applies==0,"Cancel preserved committed/backend/store values");
        model.Open();Model::Input stale;stale.key=oldKey;Check(!model.InputEvent(stale) && !model.Values().noBasicHelp,"Stale prior transaction key rejected");
        Click(model,Control::NoBasicHelp);Click(model,Control::Accept);Check(!model.Opened() && model.LastResult()==Model::Result::Applied,"Apply completed owned transaction");
        Check(backend.noBasicHelp && session->Committed()==backend && persisted==MenuOptionsValues::Encode(backend) && applies==1 && persists==1,"Canonical commit and readback");
        model.Open();Click(model,Control::InterfaceTab);Click(model,Control::PolicyInfo);const auto committed=session->Committed();const auto oldPersisted=persisted;
        failPersist=true;model.ApplyChanges();Check(model.LastResult()==Model::Result::ApplyFailed && !model.Opened() && !session->Active(),"Failed apply closes own transaction");
        Check(backend==committed && persisted==oldPersisted && session->Committed()==committed && applies==3,"Failed persistence rolled backend back exactly");
        failPersist=false;model.Open();Check(model.Values()==committed,"Reentry starts committed data");
        Click(model,Control::VideoTab);Click(model,Control::Resolution);Check(model.DropdownOpened(),"Original dropdown opens");
        Click(model,Control::Accept);Check(!model.DropdownOpened() && model.Opened(),"Dropdown outside click cannot also apply");
        Click(model,Control::Resolution);Key(model,36);Key(model,13);Check(model.Values().windowWidth==1024 && model.Values().windowHeight==768,"Keyboard dropdown selection");
        Click(model,Control::Resolution);Key(model,35);Key(model,13);Check(model.Values().windowWidth==1536,"Custom dropdown row keyboard selection");
        Click(model,Control::Fullscreen);Click(model,Control::VSync);Check(model.Values().fullscreen && !model.Values().vsync,"Display toggles cached");
        const auto prefix=std::wstring(argv[4]);
        for(unsigned page=0;page<4;++page){Click(model,static_cast<Control>(page+1));
            auto scene=BuildOriginalFrontEndOptions(*assets,model,0,label);Check(scene.width==1920 && scene.height==1080,"Logical original viewport");
            Check(scene.sprites.size()<10000 && scene.hits.size()>=8,"Bounded source scene and expected routes");
            for(const auto& sprite:scene.sprites){Check(sprite.textureIndex==ZeroSisPresentation::kSolidRectangleTexture || sprite.textureIndex<scene.textures.size(),"Scene texture index");
                for(float value:sprite.targetRect)Check(std::isfinite(value),"Finite sprite geometry");}
            for(const auto& hit:scene.hits)Check(hit.controlKey && hit.bounds[0]>=0 && hit.bounds[1]>=0 && hit.bounds[2]<=1920 && hit.bounds[3]<=1080,"Input bounds");
            checkScene(scene);
            if(page==3){Check(scene.scrolls.size()==1,"Real audio slider wheel route");WriteScene(scene,prefix+L"\\options_audio.packet");}
            if(page==2)WriteScene(scene,prefix+L"\\options_video.packet");
        }
        Model::Input slider;slider.key=model.KeyFor(Control::Volume);slider.x=model.VolumeLeft()+16;slider.y=model.VolumeTop()+16;
        Check(model.InputEvent(slider) && model.Values().uiCueVolumePercent==0,"Slider zero endpoint");slider.x=model.VolumeLeft()+model.VolumeWidth()-16;
        Check(model.InputEvent(slider) && model.Values().uiCueVolumePercent==100,"Slider full endpoint");
        slider.kind=Model::InputKind::Drag;slider.x=-10;Check(!model.InputEvent(slider),"Uncaptured drag rejected");slider.captured=true;
        Check(model.InputEvent(slider) && model.Values().uiCueVolumePercent==0,"Captured drag clamps original range");
        slider.x=std::numeric_limits<float>::quiet_NaN();Check(!model.InputEvent(slider),"Nonfinite drag rejected");
        // Retail Slider 0x5e03e0 key and wheel rules on the WheelSteps="1" volume slider; keys need the
        // pointer over the slider (retail state bit 0x10000 = pointer-over).
        Check(VolumeKey(model,37) && model.Values().uiCueVolumePercent==0,"Retail VK_LEFT subtract clamps at zero");
        Check(VolumeKey(model,39) && model.Values().uiCueVolumePercent==1,"Retail VK_RIGHT adds one WheelSteps step");
        Check(VolumeKey(model,40) && model.Values().uiCueVolumePercent==2,"Retail VK_DOWN adds one WheelSteps step");
        Check(VolumeKey(model,38) && model.Values().uiCueVolumePercent==1,"Retail VK_UP subtracts one WheelSteps step");
        Check(VolumeKey(model,39,true) && model.Values().uiCueVolumePercent==2,"Shift does not enlarge the retail step");
        Check(!VolumeKey(model,35) && !VolumeKey(model,36) && model.Values().uiCueVolumePercent==2,"Home/End do not move a retail slider");
        Check(model.Focus()==Control::Volume && !Key(model,39) && !Key(model,37) && model.Values().uiCueVolumePercent==2,
              "Keyboard focus without pointer-over does not move the retail slider");
        Check(!HoverKey(model,39,model.KeyFor(Control::Defaults)) && model.Values().uiCueVolumePercent==2,
              "Pointer over another control does not move the slider");
        Check(Key(model,9) && model.Focus()!=Control::Volume && VolumeKey(model,39) && model.Values().uiCueVolumePercent==3,
              "Pointer-over moves the slider whatever control holds keyboard focus");
        Check(VolumeKey(model,37) && model.Values().uiCueVolumePercent==2,"Pointer-over subtract after a focus change");
        Check(Wheel(model,-120) && model.Values().uiCueVolumePercent==1,"Wheel away (inverted scroll delta) subtracts one step");
        Check(Wheel(model,360) && model.Values().uiCueVolumePercent==2,"Wheel toward adds one step regardless of magnitude");
        Check(!Wheel(model,std::numeric_limits<float>::quiet_NaN()) && model.Values().uiCueVolumePercent==2,"Nonfinite wheel rejected");
        slider.kind=Model::InputKind::Click;slider.captured=false;slider.x=model.VolumeLeft()+model.VolumeWidth()-16;
        Check(model.InputEvent(slider) && model.Values().uiCueVolumePercent==100,"Slider full endpoint before key clamp");
        Check(VolumeKey(model,40) && Wheel(model,120) && model.Values().uiCueVolumePercent==100,"Retail add clamps at the full endpoint");
        Check(VolumeKey(model,37) && model.Values().uiCueVolumePercent==99,"Retail subtract from the full endpoint");
        Click(model,Control::VideoTab);Check(!VolumeKey(model,37) && model.Values().uiCueVolumePercent==99,"A stale volume hover on another page is ignored");
        Click(model,Control::AudioTab);
        auto audio=BuildOriginalFrontEndOptions(*assets,model,0,label);Check(audio.scrolls.size()==1,"Audio focus after keyboard input");
        Click(model,Control::VideoTab);Click(model,Control::Resolution);auto popup=BuildOriginalFrontEndOptions(*assets,model,model.ResolutionKey(0),label);
        Check(popup.hits.size()==model.Resolutions().size()+12,"Modal dropdown projects exact source entries and the original apply-resolution button");checkScene(popup);
        Click(model,Control::Resolution);
        Click(model,Control::Defaults);Check(model.Values()==MenuOptionsValues{},"Defaults use canonical private values");model.Cancel();Check(persisted==oldPersisted && backend==committed,"Defaults cancel preserves canonical values");
        model.Open();Click(model,Control::VideoTab);Click(model,Control::Resolution);Key(model,27);Check(model.Opened() && !model.DropdownOpened(),"Esc closes dropdown first");Key(model,27);Check(!model.Opened(),"Esc cancels options");
        {Model owned(session,apply,persist);owned.Open();}Check(!session->Active() && persisted==oldPersisted,"Owned destructor discarded only its transaction");
        auto broken=std::make_shared<MenuOptionsSession>(initial,caps);Model fault(broken,[](const MenuOptionsValues&)->MenuOptionsValues{throw std::runtime_error("backend rollback failure");},persist);
        fault.Open();Click(fault,Control::NoBasicHelp);fault.ApplyChanges();Check(fault.LastResult()==Model::Result::RollbackFailed && broken->Faulted() && !fault.Available(),"Backend rollback failure faults model");
        auto main=assets->BuildPage(MenuFrontEndPage::Main,true,4,label,L"Start",model.Available());bool optionsHit=false;for(const auto& hit:main.hits)if(hit.controlKey==4)optionsHit=true;Check(optionsHit,"Actual options entry enabled");
        auto noMain=assets->BuildPage(MenuFrontEndPage::Main,true,0,label,L"Start",false);for(const auto& hit:noMain.hits)Check(hit.controlKey!=4,"Absent backend options route disabled");
        auto glyphScene=assets->Background();const float clip[]={10,10,500,100};assets->GlyphRun(glyphScene,0,{'A',0x10ffff},10,50,clip,18,"Base",{.2f,.3f,.4f,1});
        assets->DrawInlineIcon(glyphScene,0,"ICON_GOLD",100,50,clip,{1,1,1,1});Check(glyphScene.sprites.back().textureIndex==assets->Icon("ICON_GOLD").textureIndex,"Actual inline icon atlas");
        Reject([&]{assets->GlyphRun(glyphScene,0,{0xd800},10,50,clip,18,"Base");});
        Reject([&]{assets->FontFace(19);});Reject([&]{assets->Grid(glyphScene,0,"Grid9DetailFive140",0,0,20,20);});
        auto raw=Read(std::wstring(argv[1])+L"\\frontend.bin");
        for(auto length:{0u,7u,100u,static_cast<unsigned>(raw.size()-1)}){auto bad=std::vector<unsigned char>(raw.begin(),raw.begin()+length);Reject([&]{MenuFrontEndAssets value;value.ReadBank(bad,assets->Background().textures.size());});}
        raw.push_back(0);Reject([&]{MenuFrontEndAssets value;value.ReadBank(raw,assets->Background().textures.size());});
        const auto current=MenuFrontEndAssets::Load(argv[5]);Check(current->HasFontFace(14,"Shadow"),"Current V3 asset bank was not selected");
        ResolutionPreviewIntegration(*current,label,prefix);
        RewardModelIntegration(*current,label);
        std::printf("{\"status\":\"PASS_SOURCE_REWARD_OPTIONS_V3_MIGRATION_AND_VIDEO_CONFIRMATION\",\"checks\":%u,\"legacy_faces\":6,\"icons\":148,\"resolution_preview_bound\":true,\"reward_committed_snapshot_bound\":true,\"native_window\":false,\"sdk_loaded\":false,\"gpu_execution\":false}\n",checks);return 0;
    }catch(const std::exception& error){std::fprintf(stderr,"%s\n",error.what());return 1;}
}
