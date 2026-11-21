"""Apply the reviewed original SaveMenu owner/child context integration."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def change(source, old, new, count=1):
    if source.count(old) != count:
        raise RuntimeError("Unexpected source anchor: " + old[:100])
    return source.replace(old, new, count)


def main():
    path = ROOT / "Source/Host/UiPopupContext.h"
    original = path.read_bytes()
    backup = HERE / "source_before/root/UiPopupContext.h"
    if original != backup.read_bytes():
        raise RuntimeError("Context source changed after its original snapshot")
    text = original.decode("utf-8").replace("\r\n", "\n")
    text = change(text, '#include "UiInputDispatch.h"', '#include "UiInputDispatch.h"\n#include "UiSaveMenuContract.h"')
    text = change(text, 'NotificationPanel,GameMenu };', 'NotificationPanel,GameMenu,SaveMenu };')
    text = change(text, 'enum class Kind { Open,QuickSave,Unavailable };', 'enum class Kind { Open,QuickSave,Unavailable,OpenSaveMenu };')
    text = change(text, 'UiPopupContext* economicOwner=nullptr,int economicSlot=-1)',
        'UiPopupContext* economicOwner=nullptr,int economicSlot=-1,std::shared_ptr<const UiSaveMenuCatalog> saveMenuCatalog={})')
    text = change(text, 'kind_(kind),economicOwner_(economicOwner)', 'kind_(kind),saveMenuCatalog_(std::move(saveMenuCatalog)),economicOwner_(economicOwner)')
    text = change(text, 'if(kind_==UiPopupKind::GameMenu && !externalRouting_)',
        'if((kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SaveMenu) && !externalRouting_)')
    text = change(text, 'if(kind_==UiPopupKind::GameMenu){\n            gameMenuOwner_',
        'if(kind_==UiPopupKind::SaveMenu && (!saveMenuCatalog_ || !saveMenuCatalog_->nameAvailable))\n'
        '            throw std::invalid_argument("SaveMenu requires its immutable current-session catalog");\n'
        '        if(kind_!=UiPopupKind::SaveMenu && saveMenuCatalog_)\n'
        '            throw std::invalid_argument("Save catalog cannot be attached to another popup kind");\n'
        '        if(kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SaveMenu){\n            gameMenuOwner_')
    text = change(text, 'scripts_.CreateLuaThread(kind_==UiPopupKind::GameMenu?',
        'scripts_.CreateLuaThread(kind_==UiPopupKind::SaveMenu?"BNW SaveMenu child UI":kind_==UiPopupKind::GameMenu?')
    text = change(text, 'scripts_.LoadFile(vm_,kind_==UiPopupKind::GameMenu?"GameMenuLayout"',
        'scripts_.LoadFile(vm_,kind_==UiPopupKind::SaveMenu?"SaveMenuLayout":kind_==UiPopupKind::GameMenu?"GameMenuLayout"')
    text = change(text, 'scripts_.LoadFile(vm_,kind_==UiPopupKind::GameMenu?"GameMenu":',
        'scripts_.LoadFile(vm_,kind_==UiPopupKind::SaveMenu?"SaveMenu":kind_==UiPopupKind::GameMenu?"GameMenu":')
    text = change(text, 'std::puts(kind_==UiPopupKind::GameMenu?"UI_POPUP_CONTEXT=',
        'std::puts(kind_==UiPopupKind::SaveMenu?"UI_POPUP_CONTEXT=OFFICIAL_BNW_SAVE_MENU_CHILD":kind_==UiPopupKind::GameMenu?"UI_POPUP_CONTEXT=')
    text = change(text, '    std::vector<GameMenuRequest> TakeGameMenuRequests(){', OPEN_AND_TAKE + '\n    std::vector<GameMenuRequest> TakeGameMenuRequests(){')
    text = change(text, '        if(IsNotificationInputPanel()){\n            if(!faulted_)Call',
        '        if(kind_==UiPopupKind::SaveMenu){\n'
        '            if(!faulted_ && active_){DispatchInput(UiInputKind::KeyDown,VK_ESCAPE);TakeSaveMenuRequests();}\n'
        '            active_=false;saveMenuRequests_.clear();saveMenuReady_=false;return;\n'
        '        }\n'
        '        if(IsNotificationInputPanel()){\n            if(!faulted_)Call')
    text = change(text, 'kind_==UiPopupKind::TopPanel || kind_==UiPopupKind::GameMenu || IsNotificationInputPanel()};',
        'kind_==UiPopupKind::TopPanel || kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SaveMenu || IsNotificationInputPanel()};')
    text = change(text, '        if(kind_==UiPopupKind::TradeRoute && tradeRouteOwner_',
        '        if(kind==UiInputKind::TextInput && kind_!=UiPopupKind::SaveMenu)return false;\n' +
        DISPATCH + '\n        if(kind_==UiPopupKind::TradeRoute && tradeRouteOwner_')
    text = change(text, '        if(kind_!=UiPopupKind::GameMenu || !externalRouting_ || !pregame_ || faulted_)',
        '        if((kind_!=UiPopupKind::GameMenu && kind_!=UiPopupKind::SaveMenu) || !externalRouting_ || !pregame_ || faulted_)')
    text = change(text, '    void RequireEmptyMenuModManifest(){', PRIVATE + '\n    void RequireEmptyMenuModManifest(){')
    text = change(text, 'std::strcmp(action,"SaveMenu")==0 || std::strcmp(action,"LoadMenu")==0 ||',
        'std::strcmp(action,"LoadMenu")==0 ||')
    text = change(text, '        return externalRouting_ && (kind_==UiPopupKind::GameMenu ||',
        '        return externalRouting_ && (kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::SaveMenu ||')
    text = change(text, '        case ZeroSisPresentation::BitmapInputKind::KeyDown:request.kind=',
        '        case ZeroSisPresentation::BitmapInputKind::TextInput:\n'
        '            if(kind_!=UiPopupKind::SaveMenu)return false;\n'
        '            request.kind=UiInputKind::TextInput;request.key=event.unicodeScalar;break;\n'
        '        case ZeroSisPresentation::BitmapInputKind::KeyDown:request.kind=')
    text = change(text, '        if(std::strcmp(operation,"gameMenuOpen")==0){',
        NATIVE + '\n        if(std::strcmp(operation,"gameMenuOpen")==0){')
    text = change(text, '    static int CloseGameMenuLua(lua_State* state){',
        '    static int OpenSaveMenuLua(lua_State* state){\n'
        '        lua_settop(state,0);lua_getglobal(state,"ZeroSisUi");lua_getfield(state,-1,"OpenSaveMenu");\n'
        '        if(lua_type(state,-1)!=LUA_TFUNCTION)throw std::runtime_error("Original SaveMenu entry bridge is missing");\n'
        '        lua_call(state,0,0);return 0;\n'
        '    }\n    static int CloseGameMenuLua(lua_State* state){')
    text = change(text, '        gameMenuRequests_.clear();gameMenuReady_=false;RestoreGameMenuCursor();\n',
        '        gameMenuRequests_.clear();gameMenuReady_=false;RestoreGameMenuCursor();\n'
        '        saveMenuRequests_.clear();saveMenuReady_=false;saveMenuInput_=false;\n')
    text = change(text, '    std::vector<GameMenuRequest> gameMenuRequests_;',
        '    std::shared_ptr<const UiSaveMenuCatalog> saveMenuCatalog_;\n'
        '    std::vector<SaveMenuRequest> saveMenuRequests_;\n'
        '    bool saveMenuInput_=false,saveMenuReady_=false;\n'
        '    UiInputKind saveMenuInputKind_=UiInputKind::KeyDown;\n'
        '    std::vector<GameMenuRequest> gameMenuRequests_;')
    updated = text.replace('\n', '\r\n').encode('utf-8') if b'\r\n' in original else text.encode('utf-8')
    path.write_bytes(updated)
    print(json.dumps(dict(status="SAVE_MENU_CONTEXT_SOURCE_APPLIED", bytes=len(updated), sha256=hashlib.sha256(updated).hexdigest())))


OPEN_AND_TAKE = r'''    void OpenSaveMenu(){
        Require();RequireSaveMenuOwner();
        if(!vm_ || active_ || dispatching_ || faulted_ || !scripts_.IsQuiescent() ||
           timerState_!=TimerState::Released || saveMenuInput_ || saveMenuReady_ || !saveMenuRequests_.empty())
            throw std::logic_error("SaveMenu entry requires its idle timer-free child context");
        const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
        Call(&OpenSaveMenuLua,nullptr);
        bool shown=false;Call(&ObserveActive,&shown);
        if(!shown || timerState_!=TimerState::Released || before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
            throw std::runtime_error("Original SaveMenu entry changed gameplay or its parent-owned timer");
        active_=true;host_.popupVisible=true;++sequence_;shownSnapshot_=WriteSnapshot("shown");
        std::printf("INTERACTIVE_SAVE_MENU_SHOWN=%d|%d|%u|0|STATE_UNCHANGED\n",gameMenuOwner_,gameMenuTurn_,sequence_);
    }
    std::vector<SaveMenuRequest> TakeSaveMenuRequests(){
        Require();RequireSaveMenuOwner();
        if(dispatching_ || saveMenuInput_ || faulted_ || !scripts_.IsQuiescent() || timerState_!=TimerState::Released)
            throw std::logic_error("SaveMenu requests require a completed timer-free child callback");
        if(!saveMenuReady_){
            if(!saveMenuRequests_.empty())throw std::logic_error("SaveMenu has an uncommitted callback request");
            return {};
        }
        if(active_ || saveMenuRequests_.empty() || saveMenuRequests_.size()>2 ||
           saveMenuRequests_.back().kind!=SaveMenuRequest::Kind::Close ||
           (saveMenuRequests_.size()==2 && saveMenuRequests_.front().kind!=SaveMenuRequest::Kind::Save))
            throw std::logic_error("SaveMenu command has not completed its original save/return boundary");
        for(const auto& request:saveMenuRequests_)
            if(request.owner!=game_->GetActivePlayer() || request.turn!=game_->GetGameTurn())
                throw std::logic_error("SaveMenu owner or turn changed before handoff");
        std::vector<SaveMenuRequest> result;result.swap(saveMenuRequests_);saveMenuReady_=false;return result;
    }'''

DISPATCH = r'''        if(kind_==UiPopupKind::SaveMenu){
            RequireSaveMenuOwner();
            if(saveMenuInput_ || saveMenuReady_ || !saveMenuRequests_.empty() || timerState_!=TimerState::Released)
                throw std::logic_error("SaveMenu input requires its refreshed timer-free child scope");
            const auto before=SdkStateSnapshot::Capture(host_);const auto seed=SynchronousRandomSeed();
            saveMenuInput_=true;saveMenuInputKind_=kind;
            try{Call(&UiInputDispatch::Dispatch,&request);}
            catch(...){saveMenuInput_=false;saveMenuRequests_.clear();saveMenuReady_=false;throw;}
            saveMenuInput_=false;
            bool stillActive=false;Call(&ObserveActive,&stillActive);
            if(!scripts_.IsQuiescent() || timerState_!=TimerState::Released ||
               before!=SdkStateSnapshot::Capture(host_) || seed!=SynchronousRandomSeed())
                throw std::runtime_error("Original SaveMenu input changed gameplay or its parent-owned timer");
            if(!saveMenuRequests_.empty()){
                if(!request.consumed || stillActive ||
                   (kind!=UiInputKind::LeftClick && kind!=UiInputKind::KeyDown))
                    throw std::logic_error("SaveMenu request escaped its completed original callback");
                saveMenuReady_=true;
            }
            active_=stillActive;
            // The retained parent remains modal even after the child closes.
            host_.popupVisible=true;
            if(request.consumed){
                if(active_){++revision_;const auto phase="updated-"+std::to_string(revision_);WriteSnapshot(phase.c_str());}
                else WriteSnapshot("closed");
            }
            std::printf("INTERACTIVE_SAVE_MENU_INPUT=%u|%llu|%u|%d|%d|%u|0|%zu|STATE_UNCHANGED\n",
                static_cast<unsigned>(kind),static_cast<unsigned long long>(key),request.consumed?1u:0u,
                gameMenuOwner_,gameMenuTurn_,active_?1u:0u,saveMenuRequests_.size());
            return request.consumed;
        }'''

PRIVATE = r'''    void RequireSaveMenuOwner(){
        if(kind_!=UiPopupKind::SaveMenu || !externalRouting_ || !saveMenuCatalog_ || !saveMenuCatalog_->nameAvailable || faulted_)
            throw std::logic_error("SaveMenu query is outside its immutable owned child context");
        RequireLocalMenuPlayer(gameMenuOwner_,gameMenuTurn_);
    }
    void QueueSaveMenuRequest(SaveMenuRequest::Kind kind,const char* name){
        RequireSaveMenuOwner();
        if(!active_ || !dispatching_ || !saveMenuInput_ || saveMenuReady_ || timerState_!=TimerState::Released ||
           (saveMenuInputKind_!=UiInputKind::LeftClick && saveMenuInputKind_!=UiInputKind::KeyDown))
            throw std::logic_error("SaveMenu callback requires its original owned input boundary");
        if(kind==SaveMenuRequest::Kind::Save){
            if(!saveMenuRequests_.empty() || !name || !*name || std::strlen(name)>128 || Utf8Length(name)>32)
                throw std::invalid_argument("SaveMenu named request is invalid or duplicated");
            if(!saveMenuCatalog_->nameAvailable(std::string(name)))
                throw std::invalid_argument("SaveMenu named request is unavailable");
        }else if(saveMenuRequests_.size()>1 || (!saveMenuRequests_.empty() && saveMenuRequests_.front().kind!=SaveMenuRequest::Kind::Save))
            throw std::logic_error("SaveMenu close request is duplicated or out of order");
        saveMenuRequests_.push_back({kind,gameMenuOwner_,gameMenuTurn_,name?name:""});
        std::printf("INTERACTIVE_SAVE_MENU_REQUEST_QUEUED=%u|%d|%d\n",static_cast<unsigned>(kind),gameMenuOwner_,gameMenuTurn_);
    }
    const UiSaveMenuFile& FindSaveMenuFile(const char* path){
        RequireSaveMenuOwner();
        for(const auto& file:saveMenuCatalog_->files)if(file.fileName==path)return file;
        throw std::invalid_argument("SaveMenu requested a file outside its immutable session list");
    }
    static void PushSaveMenuHeader(lua_State* state,const UiSaveMenuHeader& header){
        lua_newtable(state);
        Field(state,"PlayerCivilization",header.playerCivilization);Field(state,"GameSpeed",header.gameSpeed);
        Field(state,"StartEra",header.startEra);Field(state,"TurnNumber",header.turnNumber);
        Field(state,"Difficulty",header.difficulty);Field(state,"WorldSize",header.worldSize);
        Field(state,"CurrentEra",header.currentEra);Field(state,"GameType",header.gameType);
        lua_pushlstring(state,header.mapScript.data(),header.mapScript.size());lua_setfield(state,-2,"MapScript");
        lua_pushlstring(state,header.leaderName.data(),header.leaderName.size());lua_setfield(state,-2,"LeaderName");
        lua_pushlstring(state,header.civilizationName.data(),header.civilizationName.size());lua_setfield(state,-2,"CivilizationName");
    }'''

NATIVE = r'''        if(std::strcmp(operation,"saveMenuOpen")==0){
            if(lua_gettop(state)!=1 || self.kind_!=UiPopupKind::GameMenu)
                throw std::invalid_argument("SaveMenu opening requires its original GameMenu callback");
            self.QueueGameMenuRequest(GameMenuRequest::Kind::OpenSaveMenu,"SaveMenu");return 0;
        }
        if(std::strcmp(operation,"saveMenuSave")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("Original SaveMenu save takes one name");
            self.QueueSaveMenuRequest(SaveMenuRequest::Kind::Save,Text(state,2));return 0;
        }
        if(std::strcmp(operation,"saveMenuClose")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("Original SaveMenu close takes no arguments");
            self.QueueSaveMenuRequest(SaveMenuRequest::Kind::Close,nullptr);return 0;
        }
        if(std::strcmp(operation,"saveMenuCurrent")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("SaveMenu current header takes no arguments");
            self.RequireSaveMenuOwner();PushSaveMenuHeader(state,self.saveMenuCatalog_->current);return 1;
        }
        if(std::strcmp(operation,"saveMenuFiles")==0){
            if(lua_gettop(state)!=1)throw std::invalid_argument("SaveMenu file list takes no arguments");
            self.RequireSaveMenuOwner();lua_newtable(state);int index=0;
            for(const auto& file:self.saveMenuCatalog_->files){
                lua_pushlstring(state,file.fileName.data(),file.fileName.size());lua_rawseti(state,-2,++index);
            }
            return 1;
        }
        if(std::strcmp(operation,"saveMenuHeader")==0 || std::strcmp(operation,"saveMenuModificationTime")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("SaveMenu file query takes one listed path");
            const auto& file=self.FindSaveMenuFile(Text(state,2));
            if(std::strcmp(operation,"saveMenuHeader")==0){
                if(file.header)PushSaveMenuHeader(state,*file.header);else lua_pushnil(state);
            }else lua_pushlstring(state,file.modificationTime.data(),file.modificationTime.size());
            return 1;
        }
        if(std::strcmp(operation,"saveMenuNameAvailable")==0){
            if(lua_gettop(state)!=2)throw std::invalid_argument("SaveMenu availability query takes one name");
            self.RequireSaveMenuOwner();bool available=false;
            {const std::string name(Text(state,2));available=name.size()<=128 && self.saveMenuCatalog_->nameAvailable(name);}
            lua_pushboolean(state,available);return 1;
        }'''


if __name__ == "__main__":
    main()
