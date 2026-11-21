"""One-use, source-only owner/lifecycle edits. Never starts the engine."""
from pathlib import Path
import hashlib
import json
import os

PROJECT = Path(__file__).resolve().parents[3]
STAGE = Path(__file__).resolve().parent
BEFORE = json.loads((STAGE / 'before.json').read_bytes())
PINS = {Path(row['path']): row for row in BEFORE['sources']}
edits = {}


def load(relative):
    path = PROJECT / relative
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PINS[path]['sha256'], relative
    assert path.stat().st_nlink == 1, relative
    return path, raw.decode('utf-8-sig').replace('\r\n', '\n')


def replace(source, old, new, count=1):
    assert source.count(old) == count, old[:150]
    return source.replace(old, new)


path, text = load('Source/Host/InteractiveUiSession.h')
text = replace(text, 'if(popup_ && kind_==UiPopupKind::GameMenu){\n            auto requests=popup_->TakeGameMenuRequests();',
    'if(popup_ && (kind_==UiPopupKind::GameMenu || kind_==UiPopupKind::ExitConfirm)){\n            auto requests=popup_->TakeGameMenuRequests();')
text = replace(text, '    void OpenSaveMenu(std::shared_ptr<const UiSaveMenuCatalog> catalog){', '''    void OpenExitConfirm(){
        Require();
        if(stopping_ || !popup_ || kind_!=UiPopupKind::GameMenu || !popup_->IsActive() ||
           suspendedGameMenu_ || suspendedCity_ || suspendedCapture_ || suspendedEconomic_ ||
           !pending_.empty() || !host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("Exit confirmation requires its sole retained original GameMenu parent");
        const auto before=SdkStateSnapshot::Capture(host_);
        suspendedGameMenu_=std::move(popup_);gameMenuOpened_=opened_;
        try{
            const auto folder=directory_+L"\\\\play-exit-confirm-"+std::to_wstring(++contextSequence_);
            if(!CreateDirectoryW(folder.c_str(),nullptr))
                throw std::runtime_error("Cannot allocate original ExitConfirm child directory");
            kind_=UiPopupKind::ExitConfirm;
            popup_.reset(new UiPopupContext(owner_,*core_,folder,false,false,false,kind_,false,true));
            popup_->OpenExitConfirm();opened_=std::chrono::steady_clock::now();
            if(before!=SdkStateSnapshot::Capture(host_))
                throw std::runtime_error("ExitConfirm entry changed SDK gameplay");
            std::printf("INTERACTIVE_UI_OPENED=%u|exit-confirm\\n",contextSequence_);
        }catch(...){
            if(popup_){popup_->Stop();popup_.reset();}
            popup_=std::move(suspendedGameMenu_);kind_=UiPopupKind::GameMenu;opened_=gameMenuOpened_;
            host_.popupVisible=popup_ && popup_->IsActive();throw;
        }
    }
    void FinishExitConfirmForExit(){
        Require();
        if(!popup_ || kind_!=UiPopupKind::GameMenu || !popup_->IsActive() || suspendedGameMenu_ ||
           !pending_.empty() || !host_.scripts || !host_.scripts->IsQuiescent())
            throw std::logic_error("Confirmed exit must return through its original GameMenu parent");
        CloseCurrent();Update();
        if(HasModal() || popup_ || host_.popupVisible)
            throw std::logic_error("Confirmed exit did not release its original parent modal lifetime");
    }
    void OpenSaveMenu(std::shared_ptr<const UiSaveMenuCatalog> catalog){''')
text = replace(text, '        Require();bool changed=false;\n        if(popup_ && kind_==UiPopupKind::LoadMenu', '''        Require();bool changed=false;
        if(popup_ && kind_==UiPopupKind::ExitConfirm && !popup_->IsActive()){
            if(!suspendedGameMenu_ || popup_->HasPendingGameMenuRequests())
                throw std::logic_error("ExitConfirm return requires completed request handoff and its retained parent");
            const auto before=SdkStateSnapshot::Capture(host_);
            popup_->Stop();popup_.reset();popup_=std::move(suspendedGameMenu_);
            kind_=UiPopupKind::GameMenu;opened_=gameMenuOpened_;host_.popupVisible=popup_->IsActive();
            if(!host_.popupVisible || before!=SdkStateSnapshot::Capture(host_))
                throw std::runtime_error("ExitConfirm return lost its parent or changed gameplay");
            changed=true;std::puts("INTERACTIVE_EXIT_CONFIRM_PARENT_RETURNED=STATE_UNCHANGED");
        }
        if(popup_ && kind_==UiPopupKind::LoadMenu''')
text = replace(text, '            if(popup_ && kind_==UiPopupKind::LoadMenu){\n                const auto requests=', '''            if(popup_ && kind_==UiPopupKind::ExitConfirm){
                const auto requests=popup_->TakeGameMenuRequests();
                if(!requests.empty())
                    throw std::logic_error("Window close cannot discard a pending confirmed exit request");
            }
            if(popup_ && kind_==UiPopupKind::LoadMenu){
                const auto requests=''')
text = replace(text, '            case UiPopupKind::GameMenu:return "game-menu";',
    '            case UiPopupKind::GameMenu:return "game-menu";\n            case UiPopupKind::ExitConfirm:return "exit-confirm";')
edits[path] = text

path, text = load('Source/Host/InteractiveGameSession.h')
text = replace(text, 'pendingLoad_=LoadHandoff{};\n        turns_.reset();', 'pendingLoad_=LoadHandoff{};pendingExit_=false;\n        turns_.reset();')
text = replace(text, '    bool HasPendingLoad(){Owner();return !!pendingLoad_.archive;}',
    '    bool HasPendingExit(){Owner();return pendingExit_;}\n    bool HasPendingLoad(){Owner();return !!pendingLoad_.archive;}')
text = replace(text, '        const bool gameMenu=ui_->ActiveKind()==UiPopupKind::GameMenu;',
    '        const bool gameMenu=ui_->ActiveKind()==UiPopupKind::GameMenu;\n        const bool exitConfirm=ui_->ActiveKind()==UiPopupKind::ExitConfirm;')
text = replace(text, '        }else if(gameMenu){\n            // OnQuickSave',
    '        }else if(gameMenu || exitConfirm){\n            // OnQuickSave')
text = replace(text, '        if(requests.size()!=1 || !host_.scripts || !host_.scripts->IsQuiescent() ||\n           !host_.localCommands.IsQuiescent())',
    '        if(requests.size()!=1 || pendingExit_ || pendingLoad_.archive || !ui_ ||\n           !host_.scripts || !host_.scripts->IsQuiescent() || !host_.localCommands.IsQuiescent())')
text = replace(text, '        }else if(request.kind==GameMenuRequest::Kind::QuickSave){\n', '''        }else if(request.kind==GameMenuRequest::Kind::OpenExitConfirm){
            if(request.action!="ExitConfirm" || host_.autoSaveRunning || HasMandatoryUiDecision())
                throw std::logic_error("ExitConfirm request lost its original action or settled human owner");
            ui_->OpenExitConfirm();return;
        }else if(request.kind==GameMenuRequest::Kind::ExitGame){
            if(request.action!="ExitGame" || host_.autoSaveRunning || HasMandatoryUiDecision() || loadMenuCatalog_)
                throw std::logic_error("Confirmed exit conflicts with a save, load, or mandatory decision");
            // No save or SDK command is issued. The loop leaves after this
            // completed callback and its original parent has released its timer.
            ui_->FinishExitConfirmForExit();
            if(ui_->HasModal() || host_.popupVisible || !host_.scripts->IsQuiescent() ||
               !host_.localCommands.IsQuiescent())
                throw std::logic_error("Confirmed exit left an active modal or callback");
            pendingExit_=true;
            std::printf("INTERACTIVE_EXIT_GAME_HANDOFF_READY=%d|%d|NO_SAVE_NO_GAMEPLAY_COMMAND\\n",request.owner,request.turn);return;
        }else if(request.kind==GameMenuRequest::Kind::QuickSave){
''')
text = replace(text, '    LoadHandoff pendingLoad_;', '    LoadHandoff pendingLoad_;\n    bool pendingExit_=false;')
edits[path] = text

path, text = load('Source/Host/InteractiveGameLoop.h')
text = replace(text, '    InteractiveGameSession::LoadHandoff loadHandoff;',
    '    InteractiveGameSession::LoadHandoff loadHandoff;\n    bool menuExitRequested=false;')
text = replace(text, '                    if(live.HasPendingLoad()){\n', '''                    if(live.HasPendingExit()){
                        if(live.HasPendingLoad())throw std::logic_error("Confirmed exit cannot also load a save");
                        menuExitRequested=true;acted=true;break;
                    }
                    if(live.HasPendingLoad()){
''')
text = replace(text, '            if(loadHandoff.archive)return;\n            if(live.Tick())',
    '            if(loadHandoff.archive || menuExitRequested)return;\n            if(live.Tick())')
text = replace(text, '        if(loadHandoff.archive){\n            // Leave through the function boundary', '''        if(menuExitRequested){
            // Return before Tick, UpdateUi, saving, or publishing another scene.
            // Stack-owned window/GPU resources die before HostRun unloads Core.
            deferredEditorInput.Clear();
            if(window.NativeHandle() && !window.EnableTextInput(false,&error))throw std::runtime_error(Utf8(error));
            if(smoke)throw std::logic_error("Existing interactive smoke cannot skip its input sequence through ExitConfirm");
            std::puts("INTERACTIVE_EXIT_GAME_LOOP_EXIT=CALLBACK_COMPLETE_NO_SAVE_NO_EXTRA_TICK");
            return {};
        }
        if(loadHandoff.archive){
            // Leave through the function boundary''')
edits[path] = text

for path, text in edits.items():
    raw = path.read_bytes()
    assert hashlib.sha256(raw).hexdigest() == PINS[path]['sha256']
    data = text.replace('\n', '\r\n').encode('utf-8')
    if raw.startswith(b'\xef\xbb\xbf'):
        data = b'\xef\xbb\xbf' + data
    temporary = path.with_name(path.name + '.offline-exit-tmp')
    assert not temporary.exists()
    temporary.write_bytes(data)
    os.replace(temporary, path)
    print(path.relative_to(PROJECT), len(data), hashlib.sha256(data).hexdigest())
