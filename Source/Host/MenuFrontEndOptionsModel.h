#pragma once
#include "MenuOptionsContract.h"
#include "MenuResolutionCountdown.h"
#include <algorithm>
#include <cstdint>
#include <cmath>
#include <limits>
#include <memory>
#include <vector>

namespace ZeroSisHost {

// Front-end ownership is a private Host transaction namespace. These values
// are never SDK player IDs, game turns, retail options or GameCore save data.
class MenuFrontEndOptionsModel final {
public:
    enum class Page { Game,Interface,Video,Audio };
    enum class Control : unsigned { GameTab=1,InterfaceTab=2,VideoTab=3,AudioTab=4,
        NoBasicHelp=10,PolicyInfo=11,Resolution=12,Fullscreen=13,VSync=14,Volume=15,ApplyResolution=16,NoRewardPopups=17,
        Defaults=20,Cancel=21,Accept=22,KeepResolution=23,RevertResolution=24,ResolutionEntry=64 };
    enum class InputKind { Click,Drag,Wheel,Key,FocusLost };
    struct Input final {InputKind kind=InputKind::Click;std::uint64_t key=0;unsigned virtualKey=0;
        float x=0,y=0,wheel=0;bool shift=false,captured=false;
        // Control under the pointer when a key event arrives (0 when none).
        std::uint64_t hover=0;};
    enum class Result { None,Applied,Cancelled,ApplyFailed,RollbackFailed };
    struct Resolution final {int width,height;};
    using Apply=MenuOptionsSession::ApplyBackend;
    using Persist=MenuOptionsSession::Persist;
    // OptionsMenu.xml EffectsVolumeSlider WheelSteps="1": one retail wheel message or arrow-key
    // release moves the normalized slider by float32 1/(100/WheelSteps)=0.01, one volume percent.
    static constexpr int OriginalVolumeSliderWheelSteps=1;

    MenuFrontEndOptionsModel(std::shared_ptr<MenuOptionsSession> session,Apply apply,Persist persist)
        :session_(std::move(session)),apply_(std::move(apply)),persist_(std::move(persist)){}
    ~MenuFrontEndOptionsModel() noexcept {
        // Only the transaction successfully begun by this controller is owned.
        // Other active consumers are never discarded or adopted at construction.
        if(owns_){try{session_->Discard();}catch(...){std::terminate();}}
    }
    MenuFrontEndOptionsModel(const MenuFrontEndOptionsModel&)=delete;
    MenuFrontEndOptionsModel& operator=(const MenuFrontEndOptionsModel&)=delete;
    bool Available() const {
        if(!session_ || session_->Faulted() || !apply_ || !persist_)return false;
        return Supports("noBasicHelp") || Supports("noRewardPopups") || Supports("policyInfo") || Supports("windowWidth") ||
            Supports("fullscreen") || Supports("vsync") || Supports("uiCueVolumePercent");
    }
    bool Supports(const std::string& key) const {return session_ && !session_->Faulted() && session_->Supports(key);}
    void SetVolumeGeometry(float left,float top,float width,float height){
        if(open_ || !std::isfinite(left) || !std::isfinite(top) || !std::isfinite(width) || !std::isfinite(height) ||
           left<0 || top<0 || width<32 || height!=32 || left+width>1920 || top+height>1080)
            throw std::invalid_argument("Front-end slider needs its sealed original source geometry");
        volumeLeft_=left;volumeTop_=top;volumeWidth_=width;
    }
    void Open(){
        if(open_ || owns_ || !Available())throw std::logic_error("Front-end options require one available inactive controller");
        if(epoch_>=0x3fffffff)throw std::overflow_error("Front-end option transaction namespace exhausted");
        const auto next=epoch_+1;resolutionCountdown_.Stop();
        // Begin rejects an active GameMenu/TouchHelp transaction. Do not call
        // Discard before Begin or weaken the existing game owner/turn checks.
        session_->Begin(0x46524f4e,static_cast<int>(next));
        owns_=true;open_=true;epoch_=next;result_=Result::None;error_.clear();dropdown_=false;
        page_=PageSupported(Page::Game)?Page::Game:PageSupported(Page::Interface)?Page::Interface:
            PageSupported(Page::Video)?Page::Video:Page::Audio;
        resolutions_={{1024,768},{1280,720},{1280,800},{1366,768},{1600,900},{1920,1080}};
        const auto& value=session_->Cached();
        if(std::none_of(resolutions_.begin(),resolutions_.end(),[&](const Resolution& row){return row.width==value.windowWidth && row.height==value.windowHeight;}))
            resolutions_.push_back({value.windowWidth,value.windowHeight});
        focus_=FirstPageControl();cursor_=SelectedResolution();
    }
    void Cancel(){
        Require();
        try{session_->Cancel(0x46524f4e,static_cast<int>(epoch_));
            resolutionCountdown_.Stop();owns_=false;open_=false;dropdown_=false;result_=Result::Cancelled;}
        catch(const std::exception& error){FinishFailure(error.what());}
    }
    void ApplyChanges(){
        Require();if(ResolutionPreviewActive())throw std::logic_error("Resolution preview must be confirmed or rejected first");dropdown_=false;
        try{
            if(session_->ResolutionChanged()){
                // OnOK commits non-resolution settings before OnApplyRes. The
                // dedicated ApplyResButton deliberately bypasses this step.
                session_->CommitNonResolution(0x46524f4e,static_cast<int>(epoch_),apply_,persist_);
                BeginResolutionPreview();return;
            }
            session_->Apply(0x46524f4e,static_cast<int>(epoch_),apply_,persist_);
            owns_=false;open_=false;result_=Result::Applied;error_.clear();
        }catch(const std::exception& error){
            FinishFailure(error.what());
        }catch(...){
            if(session_->Active())session_->Cancel(0x46524f4e,static_cast<int>(epoch_));
            owns_=false;open_=false;throw;
        }
    }
    bool InputEvent(const Input& input){
        if(!open_)return false;
        Require();
        if(input.kind==InputKind::FocusLost){dropdown_=false;dragging_=false;return true;}
        if(ResolutionPreviewActive()){
            if(input.kind==InputKind::Key){
                if(input.virtualKey==27){RevertResolutionChanges();return true;}
                if(input.virtualKey==9){focus_=focus_==Control::KeepResolution?Control::RevertResolution:Control::KeepResolution;return true;}
                if(input.virtualKey==13 || input.virtualKey==32){
                    if(focus_==Control::KeepResolution)KeepResolutionChanges();else RevertResolutionChanges();return true;}
                return false;
            }
            unsigned modal=0;if(input.key && !Decode(input.key,&modal))return false;
            if(input.kind==InputKind::Click){
                if(modal==static_cast<unsigned>(Control::KeepResolution))KeepResolutionChanges();
                else if(modal==static_cast<unsigned>(Control::RevertResolution))RevertResolutionChanges();
                return true;
            }
            return input.kind==InputKind::Drag || input.kind==InputKind::Wheel;
        }
        if(input.kind==InputKind::Key)return Key(input.virtualKey,input.shift,input.hover);
        unsigned control=0;
        if(input.key){if(!Decode(input.key,&control))return false;}
        if(dropdown_){
            if(input.kind==InputKind::Click && control>=64 && control<64+resolutions_.size()){
                SelectResolution(control-64);dropdown_=false;focus_=Control::Resolution;return true;
            }
            if(input.kind==InputKind::Click && control==static_cast<unsigned>(Control::Resolution)){dropdown_=false;return true;}
            if(input.kind==InputKind::Wheel){
                if(!std::isfinite(input.wheel))return false;
                MoveCursor(input.wheel>0?-1:input.wheel<0?1:0);return true;
            }
            // A dropdown is modal: clicks outside close it, and never fall
            // through into an Apply/defaults/tab action in the same input.
            if(input.kind==InputKind::Click){dropdown_=false;return true;}
            return false;
        }
        if((input.kind==InputKind::Drag || input.kind==InputKind::Click) && control==static_cast<unsigned>(Control::Volume) &&
           page_==Page::Audio && Supports("uiCueVolumePercent")){
            if(!std::isfinite(input.x) || !std::isfinite(input.y) ||
               (input.kind==InputKind::Drag && !input.captured) ||
               (input.kind==InputKind::Click && (input.x<volumeLeft_ || input.x>volumeLeft_+volumeWidth_ || input.y<volumeTop_ || input.y>volumeTop_+32)))return false;
            const float amount=(input.x-volumeLeft_-16)/(volumeWidth_-32);
            session_->Set("uiCueVolumePercent",static_cast<int>(std::floor((std::max)(0.0f,(std::min)(1.0f,amount))*100+0.5f)));
            focus_=Control::Volume;dragging_=input.kind==InputKind::Drag;return true;
        }
        if(input.kind==InputKind::Wheel && control==static_cast<unsigned>(Control::Volume) && page_==Page::Audio && Supports("uiCueVolumePercent")){
            // Retail Slider 0x5e03e0: HIWORD(wParam)>0 (wheel away) subtracts one step. Scroll
            // records carry the inverted wheel delta, so a negative value is the retail subtract.
            if(!std::isfinite(input.wheel))return false;
            AdjustVolume(input.wheel>0?OriginalVolumeSliderWheelSteps:input.wheel<0?-OriginalVolumeSliderWheelSteps:0);return true;
        }
        if(input.kind!=InputKind::Click)return false;
        if(control>=1 && control<=4){const auto page=static_cast<Page>(control-1);if(!PageSupported(page))return false;ChoosePage(page);return true;}
        const auto selected=static_cast<Control>(control);
        if(selected==Control::Accept){ApplyChanges();return true;}
        if(selected==Control::Cancel){Cancel();return true;}
        if(selected==Control::Defaults){session_->ResetDefaults();focus_=Control::Defaults;return true;}
        if(selected==Control::ApplyResolution && page_==Page::Video){
            if(!ResolutionChanged())return false;BeginResolutionPreview();return true;}
        if(selected==Control::Resolution && page_==Page::Video && Supports("windowWidth")){
            dropdown_=true;cursor_=SelectedResolution();focus_=Control::Resolution;return true;
        }
        return Toggle(selected);
    }
    bool Opened() const noexcept{return open_;}
    bool DropdownOpened() const noexcept{return dropdown_;}
    bool Dragging() const noexcept{return dragging_;}
    bool ResolutionChanged() const {return open_ && owns_ && !session_->Faulted() && session_->ResolutionChanged();}
    bool ResolutionPreviewActive() const noexcept{return open_ && resolutionCountdown_.Active();}
    int ResolutionCountdownSeconds() const noexcept{return resolutionCountdown_.DisplaySeconds();}
    double ResolutionPreviewElapsed() const noexcept{return resolutionCountdown_.Elapsed();}
    bool AdvanceResolutionPreview(double seconds){
        if(!std::isfinite(seconds) || seconds<0)throw std::invalid_argument("Resolution preview elapsed time must be finite and nonnegative");
        if(!ResolutionPreviewActive())return false;
        Require();
        if(resolutionCountdown_.Advance(seconds))RevertResolutionChanges();
        // The source AlphaAnim also advances between integer countdown ticks.
        return true;
    }
    Page CurrentPage() const noexcept{return page_;}
    Control Focus() const noexcept{return focus_;}
    Result LastResult() const noexcept{return result_;}
    const std::string& Error() const noexcept{return error_;}
    const MenuOptionsValues& Values() const {Require();return session_->Cached();}
    const std::vector<Resolution>& Resolutions()const noexcept{return resolutions_;}
    std::size_t ResolutionCursor()const noexcept{return cursor_;}
    std::uint64_t KeyFor(Control control) const {Require();return Base()+static_cast<unsigned>(control);}
    std::uint64_t ResolutionKey(std::size_t index) const {Require();if(index>=resolutions_.size())throw std::out_of_range("Front-end resolution row is absent");return Base()+64+index;}
    float VolumeLeft()const noexcept{return volumeLeft_;}
    float VolumeTop()const noexcept{return volumeTop_;}
    float VolumeWidth()const noexcept{return volumeWidth_;}
    bool PageSupported(Page page)const {
        if(page==Page::Game)return Supports("noBasicHelp") || Supports("noRewardPopups");
        if(page==Page::Interface)return Supports("policyInfo");
        if(page==Page::Video)return Supports("windowWidth") || Supports("fullscreen") || Supports("vsync");
        return page==Page::Audio && Supports("uiCueVolumePercent");
    }
private:
    void FinishFailure(const char* message){
        error_=message;resolutionCountdown_.Stop();
        try{if(session_->Active())session_->Cancel(0x46524f4e,static_cast<int>(epoch_));}
        catch(const std::exception& restore){error_+="; ";error_+=restore.what();}
        result_=session_->Faulted()?Result::RollbackFailed:Result::ApplyFailed;
        owns_=false;open_=false;dropdown_=false;dragging_=false;
    }
    void BeginResolutionPreview(){
        Require();dropdown_=false;dragging_=false;
        try{
            if(!session_->ResolutionChanged())return;
            session_->PreviewResolution(0x46524f4e,static_cast<int>(epoch_),apply_);
            resolutionCountdown_.Start();focus_=Control::KeepResolution;error_.clear();
        }catch(const std::exception& error){FinishFailure(error.what());}
    }
    void KeepResolutionChanges(){
        Require();
        try{session_->ConfirmResolution(0x46524f4e,static_cast<int>(epoch_),apply_,persist_);
            resolutionCountdown_.Stop();cursor_=SelectedResolution();focus_=FirstPageControl();}
        catch(const std::exception& error){FinishFailure(error.what());}
    }
    void RevertResolutionChanges(){
        Require();
        try{session_->RejectResolution(0x46524f4e,static_cast<int>(epoch_),apply_);
            resolutionCountdown_.Stop();cursor_=SelectedResolution();focus_=FirstPageControl();}
        catch(const std::exception& error){FinishFailure(error.what());}
    }
    void Require()const {if(!open_ || !owns_ || !session_ || !session_->Active())throw std::logic_error("Front-end options do not own an active transaction");}
    std::uint64_t Base()const noexcept{return 0x400000000ULL+(std::uint64_t(epoch_)<<8);}
    bool Decode(std::uint64_t key,unsigned* control)const noexcept{
        if(key<=Base() || key>=Base()+256)return false;*control=static_cast<unsigned>(key-Base());return true;
    }
    Control FirstPageControl()const{
        if(page_==Page::Game)return Supports("noRewardPopups")?Control::NoRewardPopups:Control::NoBasicHelp;
        if(page_==Page::Interface)return Control::PolicyInfo;
        if(page_==Page::Audio)return Control::Volume;
        return Supports("windowWidth")?Control::Resolution:Supports("fullscreen")?Control::Fullscreen:Control::VSync;
    }
    void ChoosePage(Page page){if(!PageSupported(page))return;page_=page;dropdown_=false;dragging_=false;focus_=FirstPageControl();}
    bool Toggle(Control control){
        const char* key=nullptr;
        if(control==Control::NoRewardPopups && page_==Page::Game)key="noRewardPopups";
        if(control==Control::NoBasicHelp && page_==Page::Game)key="noBasicHelp";
        if(control==Control::PolicyInfo && page_==Page::Interface)key="policyInfo";
        if(control==Control::Fullscreen && page_==Page::Video)key="fullscreen";
        if(control==Control::VSync && page_==Page::Video)key="vsync";
        if(!key || !Supports(key))return false;
        session_->Set(key,session_->Get(key)?0:1);focus_=control;return true;
    }
    std::size_t SelectedResolution()const{
        const auto& value=session_->Cached();
        for(std::size_t i=0;i<resolutions_.size();++i)if(resolutions_[i].width==value.windowWidth && resolutions_[i].height==value.windowHeight)return i;
        throw std::logic_error("Front-end current resolution is absent from its exact list");
    }
    void SelectResolution(std::size_t index){
        if(!Supports("windowWidth") || !Supports("windowHeight") || index>=resolutions_.size())throw std::invalid_argument("Unsupported front-end resolution selection");
        session_->Set("windowWidth",resolutions_[index].width);session_->Set("windowHeight",resolutions_[index].height);cursor_=index;
    }
    void MoveCursor(int delta){
        if(delta<0 && cursor_)--cursor_;
        if(delta>0 && cursor_+1<resolutions_.size())++cursor_;
    }
    void AdjustVolume(int delta){const int next=(std::max)(0,(std::min)(100,session_->Get("uiCueVolumePercent")+delta));session_->Set("uiCueVolumePercent",next);focus_=Control::Volume;}
    std::vector<Control> FocusOrder()const{
        std::vector<Control> order;
        for(int index=0;index<4;++index)if(PageSupported(static_cast<Page>(index)))order.push_back(static_cast<Control>(index+1));
        if(page_==Page::Game){
            if(Supports("noRewardPopups"))order.push_back(Control::NoRewardPopups);
            if(Supports("noBasicHelp"))order.push_back(Control::NoBasicHelp);
        }
        if(page_==Page::Interface && Supports("policyInfo"))order.push_back(Control::PolicyInfo);
        if(page_==Page::Video){if(Supports("windowWidth"))order.push_back(Control::Resolution);if(Supports("fullscreen"))order.push_back(Control::Fullscreen);
            if(ResolutionChanged())order.push_back(Control::ApplyResolution);if(Supports("vsync"))order.push_back(Control::VSync);}
        if(page_==Page::Audio && Supports("uiCueVolumePercent"))order.push_back(Control::Volume);
        order.insert(order.end(),{Control::Defaults,Control::Cancel,Control::Accept});return order;
    }
    bool Key(unsigned key,bool shift,std::uint64_t hover){
        if(key==27){if(dropdown_){dropdown_=false;return true;}Cancel();return true;}
        if(dropdown_){
            if(key==38 || key==37){MoveCursor(-1);return true;}
            if(key==40 || key==39){MoveCursor(1);return true;}
            if(key==36){cursor_=0;return true;}if(key==35){cursor_=resolutions_.size()-1;return true;}
            if(key==13 || key==32){SelectResolution(cursor_);dropdown_=false;return true;}
            if(key!=9)return false;dropdown_=false;
        }
        if(key==9){
            const auto order=FocusOrder();const auto found=std::find(order.begin(),order.end(),focus_);
            const auto index=found==order.end()?0:static_cast<std::size_t>(found-order.begin());
            focus_=order[(index+(shift?order.size()-1:1))%order.size()];return true;
        }
        if(page_==Page::Audio && Supports("uiCueVolumePercent") && hover==KeyFor(Control::Volume)){
            // Retail Slider 0x5e03e0 takes keys only while control state bit 0x10000 is set, and that bit is
            // the pointer-over state (set after Mouse.eMouseEnter, cleared after Mouse.eMouseExit), so keyboard
            // focus does not select the slider. VK_LEFT/VK_UP subtract and VK_RIGHT/VK_DOWN add one WheelSteps
            // step; Home, End and modifiers do not move it. Retail acts on WM_KEYUP; this window queues only
            // the first WM_KEYDOWN of a press, so one press still moves one step.
            if(key==37 || key==38){AdjustVolume(-OriginalVolumeSliderWheelSteps);return true;}
            if(key==39 || key==40){AdjustVolume(OriginalVolumeSliderWheelSteps);return true;}
        }
        if(focus_==Control::Resolution && page_==Page::Video && (key==38 || key==40 || key==13 || key==32)){
            dropdown_=true;cursor_=SelectedResolution();return true;
        }
        if(key==13 || key==32){Input input;input.kind=InputKind::Click;input.key=KeyFor(focus_);return InputEvent(input);}
        return false;
    }
    std::shared_ptr<MenuOptionsSession> session_;Apply apply_;Persist persist_;
    MenuResolutionCountdown resolutionCountdown_;
    std::vector<Resolution> resolutions_;std::uint32_t epoch_=0;std::size_t cursor_=0;
    Page page_=Page::Game;Control focus_=Control::NoBasicHelp;Result result_=Result::None;
    bool open_=false,owns_=false,dropdown_=false,dragging_=false;std::string error_;
    float volumeLeft_=715.5f,volumeTop_=397.0f,volumeWidth_=500;
};
}
