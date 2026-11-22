#pragma once
#include "TurnBenchmarkObservation.h"
#include <CvLocalization.h>

namespace ZeroSisHost {
// Headless presentation of the stock informational reward. The installed Lua
// handles show, Escape and processed. Both timer calls go to the live GameCore.
class TurnBenchmarkGoldenAge final {
public:
    static const char* Script(){return "ui/ingame/popups/goldenagepopup.lua";}
    TurnBenchmarkGoldenAge(HostState& host, ICvGameContext3& context)
        :host_(host),scripts_(*host.scripts),game_(context.GetGame()){
        if(!game_ || host_.addPopup || host_.closeInformationalPopup)
            throw std::logic_error("Golden age fixture requires an unbound popup router and a live game");
        vm_=scripts_.CreateLuaThread("Headless GoldenAgePopup");
        try{
            if(!scripts_.CallCFunction(vm_,&Bind,this) || !scripts_.Execute(vm_,Bindings(),std::strlen(Bindings())) ||
               !scripts_.LoadFile(vm_,Script()))throw std::runtime_error(scripts_.LastError());
            host_.addPopup=[this](const CvPopupInfo& p){Show(p);};
            host_.closeInformationalPopup=[this](){if(visible_)Escape();};
        }catch(...){
            host_.addPopup={};host_.closeInformationalPopup={};
            scripts_.FreeLuaThread(vm_);throw;
        }
    }
    void Stop(){
        host_.addPopup={};host_.closeInformationalPopup={};
        if(visible_ && held_)Escape();
        if(held_)throw std::logic_error("Golden age fixture left a live turn timer");
        scripts_.FreeLuaThread(vm_);vm_=nullptr;
    }
private:
    static const char* Bindings(){return R"lua(
local receive, input, visibility, button, label, shown, processed
Mouse={eLClick=1}; KeyEvents={KeyDown=256}; Keys={VK_ESCAPE=27,VK_RETURN=13}; PopupPriority={GoldenAge='GoldenAge'}
Controls={DescriptionLabel={SetText=function(_,s) label=s end},
          CloseButton={RegisterCallback=function(_,key,fn) assert(key==Mouse.eLClick);button=fn end}}
Locale={ConvertTextKey=function(key) assert(key=='TXT_KEY_GOLDEN_AGE_FLAVOR');return BenchmarkGoldenAgeLabel end}
ContextPtr={SetInputHandler=function(_,fn) input=fn end,SetShowHideHandler=function(_,fn) visibility=fn end}
UI={incTurnTimerSemaphore=function() BenchmarkGoldenAgeTimer(1) end,
    decTurnTimerSemaphore=function() BenchmarkGoldenAgeTimer(-1) end}
Events={SerialEventGameMessagePopup={Add=function(fn) receive=fn end},
        GameplaySetActivePlayer={Add=function(fn) assert(type(fn)=='function') end},
        SerialEventGameMessagePopupShown=function(info) assert(info.Type==ButtonPopupTypes.BUTTONPOPUP_GOLDEN_AGE_REWARD);shown=true end,
        SerialEventGameMessagePopupProcessed={CallImmediate=function(kind,result)
          assert(shown and kind==ButtonPopupTypes.BUTTONPOPUP_GOLDEN_AGE_REWARD and result==0);processed=true end}}
UIManager={QueuePopup=function(_,ctx,priority)
           assert(ctx==ContextPtr and priority==PopupPriority.GoldenAge and not shown);visibility(false,false) end,
           DequeuePopup=function(_,ctx) assert(ctx==ContextPtr and shown and not processed);visibility(true,false) end}
function BenchmarkShowGoldenAge()
    label=nil;shown=false;processed=false
    receive({Type=ButtonPopupTypes.BUTTONPOPUP_GOLDEN_AGE_REWARD,Data1=-1,Data2=-1,Data3=-1})
    assert(type(button)=='function' and shown and not processed and type(label)=='string' and #label>0)
end
function BenchmarkEscapeGoldenAge()
    assert(input(KeyEvents.KeyDown,Keys.VK_ESCAPE,0) and processed)
end
)lua";}
    static int Bind(lua_State* vm){
        auto* self=static_cast<TurnBenchmarkGoldenAge*>(lua_touserdata(vm,1));
        if(!self)return luaL_error(vm,"Missing golden age presentation context");
        lua_pushlightuserdata(vm,self);lua_pushcclosure(vm,&Timer,1);lua_setglobal(vm,"BenchmarkGoldenAgeTimer");
        auto label=Localization::Lookup("TXT_KEY_GOLDEN_AGE_FLAVOR");
        lua_pushstring(vm,label.toUTF8());lua_setglobal(vm,"BenchmarkGoldenAgeLabel");
        return 0;
    }
    static int Timer(lua_State* vm){
        auto& self=*static_cast<TurnBenchmarkGoldenAge*>(lua_touserdata(vm,lua_upvalueindex(1)));
        const int delta=luaL_checkint(vm,1);
        if(delta==1 && !self.held_){self.game_->EndTurnTimerSemaphoreIncrement();self.held_=true;}
        else if(delta==-1 && self.held_){self.game_->EndTurnTimerSemaphoreDecrement();self.held_=false;}
        else return luaL_error(vm,"Unbalanced golden age turn timer");
        return 0;
    }
    void Dispatch(const char* command){
        const auto before=TurnBenchmarkObservation::SyncSeed(*game_);
        if(!scripts_.Execute(vm_,command,std::strlen(command)))throw std::runtime_error(scripts_.LastError());
        if(before!=TurnBenchmarkObservation::SyncSeed(*game_))throw std::runtime_error("Golden age presentation changed sync RNG");
    }
    void Show(const CvPopupInfo& p){
        if(p.eButtonPopupType!=BUTTONPOPUP_GOLDEN_AGE_REWARD)
            throw std::runtime_error("Unsupported headless turn popup type "+std::to_string(int(p.eButtonPopupType)));
        if(visible_ || held_ || p.iData1!=-1 || p.iData2!=-1 || p.iData3!=-1 ||
           p.iFlags || p.bOption1 || p.bOption2 || p.szText[0])
            throw std::runtime_error("Unexpected golden age popup payload or nested popup");
        Dispatch("BenchmarkShowGoldenAge()");
        if(!held_)throw std::runtime_error("Golden age shown without SDK timer");
        visible_=true;host_.Record("local-golden-age-shown");
    }
    void Escape(){
        Dispatch("BenchmarkEscapeGoldenAge()");
        if(held_)throw std::runtime_error("Golden age Escape did not release SDK timer");
        visible_=false;host_.Record("local-golden-age-escape-processed");
    }
    HostState& host_;
    ScriptSystem& scripts_;
    std::unique_ptr<ICvGame1> game_;
    lua_State* vm_=nullptr;
    bool visible_=false,held_=false;
};
}
