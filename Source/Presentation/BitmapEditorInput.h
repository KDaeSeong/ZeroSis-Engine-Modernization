#pragma once
#include "BitmapWindow.h"
#include <stdexcept>

namespace ZeroSisPresentation {

// The host uses this bounded queue while an immutable UI packet is prepared.
// It does not retag generations or call gameplay/Lua/native-window callbacks.
class BitmapEditorInputBuffer final {
public:
    static constexpr std::size_t Limit=1024;
    static bool IsEditKey(std::uint32_t key) {
        return key==VK_BACK || key==VK_DELETE || key==VK_LEFT || key==VK_RIGHT ||
               key==VK_HOME || key==VK_END;
    }
    static bool IsEditorInput(const BitmapInputEvent& event) {
        return event.kind==BitmapInputKind::TextInput ||
               (event.kind==BitmapInputKind::KeyDown && IsEditKey(event.virtualKey));
    }
    static bool Matches(const BitmapInputEvent& event,std::uint64_t owner,std::uint64_t epoch) {
        return owner && epoch && IsEditorInput(event) &&
               event.editorOwner==owner && event.textFocusEpoch==epoch;
    }
    static bool IsTerminalAction(const BitmapInputEvent& event,bool ownedEditorInput) {
        return event.kind==BitmapInputKind::ControlClick || event.kind==BitmapInputKind::ControlRightClick ||
               (event.kind==BitmapInputKind::KeyDown && !ownedEditorInput);
    }
    void Bind(std::uint64_t owner,std::uint64_t epoch) {
        if(!owner || !epoch){Clear();return;}
        if(owner_!=owner || epoch_!=epoch)events_.clear();
        owner_=owner;epoch_=epoch;
    }
    void Clear(){events_.clear();owner_=epoch_=0;}
    bool Retain(const BitmapInputEvent& event) {
        if(!Matches(event,owner_,epoch_))return false;
        if(events_.size()>=Limit)throw std::length_error("Deferred editor input exceeded its bounded queue");
        events_.push_back(event);return true;
    }
    void Drain(std::uint64_t owner,std::uint64_t epoch,std::vector<BitmapInputEvent>& output) {
        output.clear();
        if(!owner || !epoch || owner!=owner_ || epoch!=epoch_){Clear();return;}
        output.swap(events_);
    }
    std::size_t Size() const {return events_.size();}
private:
    std::uint64_t owner_=0,epoch_=0;
    std::vector<BitmapInputEvent> events_;
};

// Shared by the real packet wait/scene commit and the native regression test.
// Input generations remain intact. Geometry callbacks are never retained here.
inline bool DrainBitmapPreparationInputs(BitmapWindow& window,bool& closeRequested,
                                         std::vector<BitmapInputEvent>& rejected,unsigned& pointers,
                                         std::wstring* error,std::uint64_t pointerGeneration=0,
                                         BitmapEditorInputBuffer* editorInput=nullptr) {
    std::vector<BitmapInputEvent> pending;
    if(!window.DrainInputs(&pending,error))return false;
    pointers=0;rejected.clear();
    for(const auto& input:pending){
        if(input.kind==BitmapInputKind::PointerMove && input.sceneGeneration==pointerGeneration)++pointers;
        if(input.kind==BitmapInputKind::CloseRequest)closeRequested=true;
        else if(editorInput && !closeRequested && editorInput->Retain(input))continue;
        else rejected.push_back(input);
    }
    if(closeRequested && editorInput)editorInput->Clear();
    return true;
}

} // namespace ZeroSisPresentation
