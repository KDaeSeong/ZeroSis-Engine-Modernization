#include "../Source/Presentation/BitmapEditorInput.h"
#include <cstdio>
#include <stdexcept>
#include <vector>

using namespace ZeroSisPresentation;

namespace {
int checks=0;
bool Expect(bool condition,const char* name){
    ++checks;if(!condition)std::fprintf(stderr,"FAIL %s\n",name);return condition;
}
BitmapInputEvent Text(std::uint32_t scalar,std::uint64_t generation,std::uint64_t owner,std::uint64_t epoch){
    BitmapInputEvent event{BitmapInputKind::TextInput,0,0,0,0,generation};
    event.unicodeScalar=scalar;event.editorOwner=owner;event.textFocusEpoch=epoch;return event;
}
BitmapInputEvent Key(std::uint32_t key,std::uint64_t generation,std::uint64_t owner,std::uint64_t epoch){
    BitmapInputEvent event{BitmapInputKind::KeyDown,0,key,0,0,generation};
    event.editorOwner=owner;event.textFocusEpoch=epoch;return event;
}
}

int main(){
    BitmapEditorInputBuffer queue;std::vector<BitmapInputEvent> replay;
    const auto first=Text(0xd55c,10,101,7);
    if(!Expect(!queue.Retain(first),"default-off queue refuses an unbound editor"))return 1;
    queue.Bind(101,7);
    if(!Expect(queue.Retain(first),"bound queue retains a committed Hangul scalar"))return 1;
    if(!Expect(queue.Retain(Text(0xae00,10,101,7)) && queue.Retain(Text(0x41,11,101,7)),
               "rapid text remains ordered across an original scene generation change"))return 1;
    if(!Expect(queue.Retain(Key(VK_BACK,11,101,7)) && queue.Retain(Key(VK_BACK,11,101,7)) &&
               queue.Retain(Key(VK_DELETE,11,101,7)),"same-batch repeated editing keys all survive"))return 1;
    queue.Bind(101,7);queue.Drain(101,7,replay);
    if(!Expect(replay.size()==6 && replay[0].unicodeScalar==0xd55c && replay[1].unicodeScalar==0xae00 &&
               replay[2].unicodeScalar==0x41 && replay[3].virtualKey==VK_BACK && replay[4].virtualKey==VK_BACK &&
               replay[5].virtualKey==VK_DELETE,"actual production buffer replays the complete rapid stream"))return 1;
    if(!Expect(replay[0].sceneGeneration==10 && replay[2].sceneGeneration==11,
               "replay never retags input geometry generations"))return 1;
    bool acted=false;unsigned accepted=0;
    for(const auto& event:replay){
        if(acted)break;
        ++accepted;acted=BitmapEditorInputBuffer::IsTerminalAction(event,true);
    }
    if(!Expect(accepted==6 && !acted,"the shared host action barrier allows every ordinary edit in one batch"))return 1;
    if(!Expect(!queue.Retain(Key(VK_RETURN,11,101,7)) && !queue.Retain(Key(VK_ESCAPE,11,101,7)),
               "Return and Escape cannot enter editor deferral"))return 1;
    BitmapInputEvent click{BitmapInputKind::ControlClick,33,0,0,0,10};click.editorOwner=101;click.textFocusEpoch=7;
    if(!Expect(!queue.Retain(click) && BitmapEditorInputBuffer::IsTerminalAction(click,false),
               "clicks retain their geometry and terminal action boundary"))return 1;
    if(!Expect(BitmapEditorInputBuffer::IsTerminalAction(Key(VK_RETURN,11,0,0),false) &&
               BitmapEditorInputBuffer::IsTerminalAction(Key(VK_ESCAPE,11,0,0),false),
               "terminal keys still stop same-batch callback processing"))return 1;
    if(!Expect(!queue.Retain(Text(0x42,11,102,7)) && !queue.Retain(Text(0x42,11,101,8)),
               "another child or native focus cannot append to the current editor"))return 1;
    queue.Retain(first);queue.Drain(102,7,replay);
    if(!Expect(replay.empty() && queue.Size()==0,"changing child/player/turn/Lua focus token clears old replay"))return 1;
    queue.Bind(101,7);queue.Retain(first);queue.Drain(101,8,replay);
    if(!Expect(replay.empty() && queue.Size()==0,"native HWND focus epoch change clears old replay"))return 1;
    queue.Bind(101,7);queue.Retain(first);queue.Bind(101,8);
    if(!Expect(queue.Size()==0 && !queue.Retain(first),"rebinding cannot reinterpret old native input"))return 1;
    queue.Bind(101,7);queue.Retain(first);queue.Bind(0,7);
    if(!Expect(queue.Size()==0 && !queue.Retain(first),"unfocused editor rejects retained text"))return 1;
    queue.Bind(101,7);
    for(std::size_t index=0;index<BitmapEditorInputBuffer::Limit;++index)queue.Retain(first);
    bool overflow=false;try{queue.Retain(first);}catch(const std::length_error&){overflow=true;}
    if(!Expect(overflow && queue.Size()==BitmapEditorInputBuffer::Limit,
               "continuous producers fail visibly at the fixed queue capacity"))return 1;
    queue.Clear();
    if(!Expect(queue.Size()==0 && !queue.Retain(first),"clear removes events and their owner binding"))return 1;
    std::printf("BITMAP_EDITOR_INPUT_BUFFER_PASS checks=%d WINDOW_CREATED=false SDK_LOADED=false\n",checks);
    return 0;
}
