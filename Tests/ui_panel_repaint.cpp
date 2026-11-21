#include "UiPanelRepaint.h"
#include <cstddef>
#include <initializer_list>
#include <iostream>
#include <stdexcept>
#include <string>

// Exercises the production dispatch policy only. No panel, Lua VM, SDK,
// window, renderer, filesystem, or native runtime is constructed here.
namespace {
using ZeroSisHost::UiPanelRepaint;

struct Counters {
    unsigned checks=0;
    unsigned cases=0;
    unsigned dispatches=0;
    unsigned snapshots=0;
};

void Check(Counters& counts,bool value,const char* message) {
    ++counts.checks;
    if(!value)throw std::runtime_error(message);
}

void PointerCase(Counters& counts,const std::string& initial,
                 const std::string& updated,bool consumed,bool expectedChanged) {
    ++counts.cases;
    std::string retained=initial;
    unsigned dispatches=0,snapshots=0;
    std::string order;
    bool changed=true;
    const bool result=UiPanelRepaint::Dispatch(true,&changed,[&](){
        Check(counts,!changed,"Pointer output was not cleared before dispatch");
        ++dispatches;++counts.dispatches;order+='D';retained=updated;
        return consumed;
    },[&]() -> const std::string& {
        Check(counts,!changed,"Pointer output was published before snapshots completed");
        ++snapshots;++counts.snapshots;order+='S';return retained;
    });
    Check(counts,result==consumed,"Pointer consumption changed");
    Check(counts,changed==expectedChanged,"Pointer visual-change decision differs");
    Check(counts,dispatches==1 && snapshots==2,"Pointer dispatch/snapshot count differs");
    Check(counts,order=="SDS","Pointer callback order differs");
    Check(counts,retained==updated,"Pointer callback state was not retained");
}

void NonPointerCase(Counters& counts,bool consumed,bool mutate) {
    ++counts.cases;
    unsigned dispatches=0,snapshots=0;
    int retained=7;
    bool changed=true;
    const bool result=UiPanelRepaint::Dispatch(false,&changed,[&](){
        Check(counts,!changed,"Non-pointer output was not cleared before dispatch");
        ++dispatches;++counts.dispatches;
        if(mutate)retained=11;
        return consumed;
    },[&](){++snapshots;++counts.snapshots;return std::string("unused");});
    Check(counts,result==consumed && changed==consumed,"Non-pointer consumed/repaint policy changed");
    Check(counts,dispatches==1 && snapshots==0,"Non-pointer unexpectedly captured snapshots");
    Check(counts,retained==(mutate?11:7),"Non-pointer callback state changed");
}

void NullOutputCase(Counters& counts,bool pointerMove,bool consumed) {
    ++counts.cases;
    unsigned dispatches=0,snapshots=0;
    const bool result=UiPanelRepaint::Dispatch(pointerMove,nullptr,[&](){
        ++dispatches;++counts.dispatches;return consumed;
    },[&](){++snapshots;++counts.snapshots;return std::string("unused");});
    Check(counts,result==consumed,"Null-output dispatch changed consumption");
    Check(counts,dispatches==1 && snapshots==0,"Null-output dispatch captured snapshots or dispatched twice");
}

struct Injected {
    const void* identity;
    unsigned stage;
};

void ExceptionCase(Counters& counts,bool pointerMove,bool hasOutput,unsigned failStage) {
    ++counts.cases;
    unsigned dispatches=0,snapshots=0;
    bool changed=true;
    bool* const output=hasOutput?&changed:nullptr;
    int token=0;
    bool caught=false;
    try {
        (void)UiPanelRepaint::Dispatch(pointerMove,output,[&](){
            if(output)Check(counts,!changed,"Throwing dispatch observed a stale true output");
            ++dispatches;++counts.dispatches;
            if(failStage==2)throw Injected{&token,2};
            return true;
        },[&](){
            Check(counts,!changed,"Throwing snapshot observed a published output");
            ++snapshots;++counts.snapshots;
            const unsigned stage=snapshots==1?1u:3u;
            if(failStage==stage)throw Injected{&token,stage};
            return std::string("same");
        });
    }catch(const Injected& error){
        caught=true;
        Check(counts,error.identity==&token && error.stage==failStage,"Injected exception was wrapped or replaced");
    }
    Check(counts,caught,"Injected exception did not propagate");
    Check(counts,hasOutput?!changed:changed,"Failure published a visual-change result");
    const unsigned expectedDispatches=pointerMove && hasOutput && failStage==1?0u:1u;
    const unsigned expectedSnapshots=pointerMove && hasOutput?(failStage==3?2u:1u):0u;
    Check(counts,dispatches==expectedDispatches && snapshots==expectedSnapshots,
          "Failure retried callbacks or continued after its first exception");
}

void CheckOwnedSnapshot(Counters& counts) {
    // The callback returns the same mutable string object both times. The
    // helper must own the first value rather than retain a reference to it.
    PointerCase(counts,"button:normal","button:hover",true,true);
    const std::string binaryBefore("\0A\xff",3);
    const std::string binaryAfter("\0B\xff",3);
    PointerCase(counts,binaryBefore,binaryAfter,true,true);
    PointerCase(counts,binaryBefore,binaryBefore,true,false);
}

void Run(Counters& counts) {
    // Same-key accepted hover and repeated key-zero clearing are consumed,
    // but unchanged retained state must not request a whole-panel repaint.
    PointerCase(counts,"button:hover","button:hover",true,false);
    PointerCase(counts,"","",true,false);
    PointerCase(counts,"button:normal","button:hover",true,true);
    PointerCase(counts,"button:hover","button:normal",true,true);
    // Equal-length changes and tooltip-only changes are still visual changes.
    PointerCase(counts,"hover:A","hover:B",true,true);
    PointerCase(counts,"hover:A;tooltip:open","hover:A",true,true);
    // A rejected input retains its original false result, even if a callback
    // changed its state before refusing the request.
    PointerCase(counts,"before","after",false,false);
    PointerCase(counts,"same","same",false,false);
    CheckOwnedSnapshot(counts);

    NonPointerCase(counts,true,true);   // Click callback changed retained state.
    NonPointerCase(counts,true,false);  // Consumed click needs its usual repaint.
    NonPointerCase(counts,false,false);
    NonPointerCase(counts,false,true);  // Rejection never becomes a repaint.
    NonPointerCase(counts,true,true);   // Scroll uses the same non-pointer path.
    for(bool pointerMove:{false,true})for(bool consumed:{false,true})
        NullOutputCase(counts,pointerMove,consumed);

    ExceptionCase(counts,true,true,1);
    ExceptionCase(counts,true,true,2);
    ExceptionCase(counts,true,true,3);
    ExceptionCase(counts,false,true,2);
    ExceptionCase(counts,true,false,2);
    ExceptionCase(counts,false,false,2);

    // Reusing an output previously set true must not carry it into a no-op.
    ++counts.cases;
    bool changed=false;
    unsigned dispatches=0,snapshots=0;
    auto dispatch=[&](){++dispatches;++counts.dispatches;return true;};
    auto snapshot=[&](){++snapshots;++counts.snapshots;return std::string("unchanged");};
    Check(counts,UiPanelRepaint::Dispatch(false,&changed,dispatch,snapshot) && changed,
          "Consumed click failed to publish its existing repaint result");
    Check(counts,UiPanelRepaint::Dispatch(true,&changed,dispatch,snapshot) && !changed,
          "Previous true repaint leaked into a later no-op hover");
    Check(counts,dispatches==2 && snapshots==2,"Sequential dispatch count differs");
}
} // namespace

int main(int argc,char**) {
    if(argc!=1){std::cerr<<"This component takes no arguments\n";return 2;}
    Counters counts;
    try {
        Run(counts);
        std::cout<<"{\"schema\":\"zerosis.ui_panel_repaint_test.v1\","
            "\"status\":\"PASS_UI_PANEL_REPAINT_COMPONENT\",\"checks\":"<<counts.checks
            <<",\"cases\":"<<counts.cases<<",\"dispatch_calls\":"<<counts.dispatches
            <<",\"snapshot_calls\":"<<counts.snapshots
            <<",\"production_helper_used\":true,\"input_files_unchanged\":true,"
            "\"host_executed\":false,\"sdk_executed\":false,\"gamecore_loaded\":false,"
            "\"window_created\":false,\"window_calls\":0,\"game_accessed\":false,"
            "\"user_saves_accessed\":false,\"complete_player_validated\":false,"
            "\"complete_save_validated\":false,\"ruleset_compatibility_verified\":false,"
            "\"restore_approved\":false,\"full_engine_goal_complete\":false}\n";
        return 0;
    }catch(const std::exception& error){std::cerr<<error.what()<<'\n';return 1;}
    catch(...){std::cerr<<"Unexpected component exception\n";return 1;}
}
