#include "UiInputDispatch.h"
#include "../Source/Presentation/BitmapSliderInput.h"
#define WIN32_LEAN_AND_MEAN
#include <Windows.h>
#include <iostream>
extern "C" {
#include <lualib.h>
}
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

using ZeroSisHost::UiInputDispatch;
using ZeroSisHost::UiInputRequest;
using ZeroSisHost::UiInputTarget;
using ZeroSisHost::UiInputTargetsRequest;

namespace {
int checks=0;
void Require(bool ok,const char* message){++checks;if(!ok)throw std::runtime_error(message);}

void SetTargets(lua_State* state,const char* expression){
    const std::string source=std::string("ZeroSisUi={GetInputTargets=function(requestedEvent) "
        "assert(requestedEvent=='LeftClick'); return ")+expression+" end}";
    if(luaL_dostring(state,source.c_str())!=0){
        const char* error=lua_tostring(state,-1);
        throw std::runtime_error(error?error:"could not install target fixture");
    }
}

void SetScrollTargets(lua_State* state,const char* expression){
    const std::string source=std::string("ZeroSisUi={GetScrollTargets=function() return ")+
        expression+" end}";
    if(luaL_dostring(state,source.c_str())!=0){
        const char* error=lua_tostring(state,-1);
        throw std::runtime_error(error?error:"could not install scroll target fixture");
    }
}

int ProtectedCollectTargets(lua_State* state);

bool Collect(lua_State* state,std::vector<UiInputTarget>& output){
    UiInputTargetsRequest request{&output};
    const int status=lua_cpcall(state,&ProtectedCollectTargets,&request);
    if(status!=0)lua_pop(state,1);
    return status==0;
}

bool CollectScrollTargets(lua_State* state,std::vector<UiInputTarget>& output){
    UiInputTargetsRequest request{&output,false,true};
    const int status=lua_cpcall(state,&ProtectedCollectTargets,&request);
    if(status!=0)lua_pop(state,1);
    return status==0;
}

// Mirrors ScriptSystem::ProtectedCallback: C++ exceptions become Lua errors,
// while normal Lua validation errors are recovered by the outer cpcall.
int ProtectedCollectTargets(lua_State* state){
    try{return UiInputDispatch::CollectTargets(state);}
    catch(const std::exception& error){lua_pushstring(state,error.what());return lua_error(state);}
    catch(...){lua_pushliteral(state,"unknown protected callback failure");return lua_error(state);}
}

int ProtectedDispatch(lua_State* state){
    try{return UiInputDispatch::Dispatch(state);}
    catch(const std::exception& error){lua_pushstring(state,error.what());return lua_error(state);}
    catch(...){lua_pushliteral(state,"unknown protected dispatch failure");return lua_error(state);}
}

bool Dispatch(lua_State* state,UiInputRequest& request){
    const int status=lua_cpcall(state,&ProtectedDispatch,&request);
    if(status!=0)lua_pop(state,1);
    return status==0;
}

void Accept(lua_State* state,const char* expression,std::vector<UiInputTarget>& output){
    SetTargets(state,expression);
    Require(Collect(state,output),"valid target payload rejected");
}

void Reject(lua_State* state,const char* expression){
    SetTargets(state,expression);
    UiInputTarget sentinel;sentinel.key=999;sentinel.id="sentinel";
    std::vector<UiInputTarget> output;output.push_back(std::move(sentinel));
    Require(!Collect(state,output),"invalid target payload accepted");
    Require(output.size()==1 && output.front().key==999 && output.front().id=="sentinel",
            "rejected payload changed the caller's prior snapshot");
}

void TestLegacyAndOptionalPayload(lua_State* state){
    std::vector<UiInputTarget> output;
    Accept(state,"{{key=12,id='CloseButton'}}",output);
    Require(output.size()==1 && output[0].key==12 && output[0].id=="CloseButton" && !output[0].hasVoidPayload,
            "legacy target ranking or identity changed");
    Accept(state,"{{key=73,id='ProdButton',void1=-2147483648,void2=2147483647}}",output);
    Require(output.size()==1 && output[0].key==73 && output[0].id=="ProdButton" && output[0].hasVoidPayload &&
            output[0].void1==(std::numeric_limits<int>::min)() && output[0].void2==(std::numeric_limits<int>::max)(),
            "optional ProductionPopup integer payload was not preserved exactly");
    Accept(state,"{{key=74,id='ProdButton',void1=0,void2=0}}",output);
    Require(output.size()==1 && output[0].hasVoidPayload && output[0].void1==0 && output[0].void2==0,
            "zero-valued optional payload was treated as absent");
}

void TestRequestedEventAndProtectedRejection(lua_State* state){
    std::vector<UiInputTarget> output;
    SetTargets(state,"{{key=21,id='Button',event='LeftClick',void1=6,void2=1}}" );
    Require(Collect(state,output),"valid requested left-click target was rejected");
    Require(output.size()==1 && output[0].key==21 && output[0].hasVoidPayload,
            "requested event target or optional values were lost");

    SetTargets(state,"{{key=22,id='Button',event='RightClick'}}");
    UiInputTarget sentinel;sentinel.key=999;sentinel.id="sentinel";
    output.clear();output.push_back(std::move(sentinel));
    Require(!Collect(state,output),"wrong event target was accepted");
    Require(output.size()==1 && output.front().key==999 && output.front().id=="sentinel",
            "protected Lua validation rejection replaced the prior output");

    SetTargets(state,"{{key=23,id='Button',event=17}}");
    Require(!Collect(state,output),"non-string target event was accepted");
    Require(output.size()==1 && output.front().key==999 && output.front().id=="sentinel",
            "second protected rejection changed the previous output");
}

void TestScrollTargetCollector(lua_State* state){
    std::vector<UiInputTarget> output;
    SetScrollTargets(state,"{{key=47,id='Viewport',event='Scroll'}}");
    Require(CollectScrollTargets(state,output),"valid visible ScrollPanel target rejected");
    Require(output.size()==1 && output[0].key==47 && output[0].id=="Viewport",
            "ScrollPanel key or identity was lost by scroll collector");

    UiInputTarget sentinel;sentinel.key=999;sentinel.id="sentinel";
    output.clear();output.push_back(std::move(sentinel));
    SetScrollTargets(state,"{{key=48,id='Viewport',event='LeftClick'}}");
    Require(!CollectScrollTargets(state,output),"non-Scroll event passed scroll target collector");
    Require(output.size()==1 && output[0].key==999 && output[0].id=="sentinel",
            "wrong scroll event replaced the caller's previous snapshot");
    SetScrollTargets(state,"{{key=49,id='Viewport'}}");
    Require(!CollectScrollTargets(state,output),"scroll target without explicit Scroll event was accepted");
    Require(output.size()==1 && output[0].key==999,"missing scroll event changed prior output");
    if(luaL_dostring(state,"ZeroSisUi={}")!=0)throw std::runtime_error("could not remove scroll export");
    Require(!CollectScrollTargets(state,output),"missing GetScrollTargets export was accepted");
    Require(output.size()==1 && output[0].key==999,"missing scroll export changed prior output");
}

void TestNonmodalConsumeMouseAndOriginalAction(lua_State* state){
    std::vector<UiInputTarget> output;
    const char* panel="{{key=7,id='PrimaryStretchy',event='ConsumeMouse',consumeMouse=true},"
        "{key=8,id='UnitActionButton',event='LeftClick',void1=0,consumeMouse=true}}";
    SetTargets(state,panel);
    Require(!Collect(state,output),"modal collector accepted a nonmodal input blocker");
    UiInputTargetsRequest request{&output,false,false,true};
    int status=lua_cpcall(state,&ProtectedCollectTargets,&request);
    if(status)lua_pop(state,1);
    Require(status==0 && output.size()==2 && output[0].key==7 && output[1].key==8,
            "nonmodal collector lost original parent/button input order");
    Require(output[0].consumeMouseOnly && !output[1].consumeMouseOnly,
            "ConsumeMouse-only identity was lost or assigned to a real button");
    Require(!output[0].hasVoid1 && !output[0].hasVoid2 && output[1].hasVoid1 &&
            output[1].void1==0 && !output[1].hasVoid2,
            "original zero action index or absent second argument was changed");
    SetTargets(state,"{{key=9,id='Background',event='ConsumeMouse'}}");
    status=lua_cpcall(state,&ProtectedCollectTargets,&request);if(status)lua_pop(state,1);
    Require(status!=0 && output.size()==2 && output[0].key==7,
            "undeclared input blocker accepted or previous scene replaced");
}

void TestFinitePointerAndScrollDispatch(lua_State* state){
    const char* source="ZeroSisUi={" 
        "DispatchPointerMove=function(key) LastPointerKey=key; return key==0 end," 
        "DispatchScroll=function(key,delta) LastScrollKey=key; LastScrollDelta=delta; return true end}";
    Require(luaL_dostring(state,source)==0,"could not install pointer/scroll dispatch fixture");
    UiInputRequest pointer{};pointer.kind=ZeroSisHost::UiInputKind::PointerMove;pointer.key=0;
    Require(Dispatch(state,pointer) && pointer.consumed,"pointer key zero did not clear hover as a consumed request");
    UiInputRequest scroll{};scroll.kind=ZeroSisHost::UiInputKind::Scroll;scroll.key=17;scroll.delta=-48.0;
    Require(Dispatch(state,scroll) && scroll.consumed,"finite owned-row scroll request was not consumed");
    Require(luaL_dostring(state,"assert(LastPointerKey==0 and LastScrollKey==17 and LastScrollDelta==-48)")==0,
            "pointer or scroll arguments changed across the C++/Lua boundary");

    const double badDeltas[]={0.0,(std::numeric_limits<double>::infinity)(),
        -(std::numeric_limits<double>::infinity)(),(std::numeric_limits<double>::quiet_NaN)(),32768.5};
    for(double delta:badDeltas){
        UiInputRequest invalid{};invalid.kind=ZeroSisHost::UiInputKind::Scroll;invalid.key=17;invalid.delta=delta;
        Require(!Dispatch(state,invalid) && !invalid.consumed,"invalid scroll delta reached Lua or remained consumed");
    }
    UiInputRequest noOwner{};noOwner.kind=ZeroSisHost::UiInputKind::Scroll;noOwner.key=0;noOwner.delta=48.0;
    Require(!Dispatch(state,noOwner) && !noOwner.consumed,"scroll without a retained row owner was accepted");
    UiInputRequest stale{};stale.kind=ZeroSisHost::UiInputKind::PointerMove;
    stale.key=UiInputDispatch::MaxExactLuaInteger+1;
    Require(!Dispatch(state,stale) && !stale.consumed,"inexact pointer target key reached Lua");
}


void TestSliderDispatchAndGeometry(lua_State* state){
    Require(luaL_dostring(state,"SliderCalls=0; ZeroSisUi={DispatchSliderValue=function(key,value) "
        "assert(key==73); SliderCalls=SliderCalls+1; LastSliderValue=value; return true end}")==0,"slider fixture installation failed");
    UiInputRequest input{};input.kind=ZeroSisHost::UiInputKind::SliderValue;input.key=73;
    for(double value:{0.0,0.01,0.5,1.0}){
        input.delta=value;Require(Dispatch(state,input) && input.consumed,"normalized slider value rejected");
        lua_getglobal(state,"LastSliderValue");Require(lua_tonumber(state,-1)==value,"normalized slider value changed");lua_pop(state,1);
    }
    for(double value:{-0.01,1.01,(std::numeric_limits<double>::infinity)(),(std::numeric_limits<double>::quiet_NaN)()}){
        input.delta=value;Require(!Dispatch(state,input) && !input.consumed,"invalid slider value reached Lua");
    }
    Require(luaL_dostring(state,"assert(SliderCalls==4)")==0,"invalid slider invoked callback");
    input.delta=0.5;input.key=0;Require(!Dispatch(state,input),"slider accepted owner zero");

    const char* row="{key=73,id='EffectsVolumeSlider',event='SliderValue',minimum=0,maximum=1,value=.5,"
        "bounds={x=20,y=40,width=180,height=32}}";
    std::string fixture=std::string("return {")+row+"}";
    const auto install=[&](const std::string& body){
        const std::string code="ZeroSisUi={GetInputTargets=function(event) assert(event=='SliderValue'); "+body+" end}";
        Require(luaL_dostring(state,code.c_str())==0,"slider collector fixture failed");
    };
    std::vector<UiInputTarget> targets;UiInputTargetsRequest request{&targets};request.slider=true;
    install(fixture);
    Require(lua_cpcall(state,&ProtectedCollectTargets,&request)==0,"valid slider collection failed");
    Require(targets.size()==1 && targets[0].slider && targets[0].width==180 && targets[0].value==.5,"slider target snapshot lost geometry");
    const char* corruptions[]={"t[1].value=0/0","t[1].value=-1","t[1].value=2","t[1].bounds.width=0",
        "t[1].bounds.x=-1","t[1].bounds.height=math.huge","t[1].bounds.x=1919","t[1].maximum=100",
        "t[1].minimum=-1","t[1].event='LeftClick'","t[1].bounds=setmetatable(t[1].bounds,{})",
        "t[1].bounds=nil","t[1].bounds.width='180'"};
    for(const auto* corruption:corruptions){
        install(std::string("local t={")+row+"}; "+corruption+"; return t");
        const int status=lua_cpcall(state,&ProtectedCollectTargets,&request);if(status)lua_pop(state,1);
        Require(status!=0,"invalid slider geometry/value accepted");
        Require(targets.size()==1 && targets[0].key==73 && targets[0].value==.5,"invalid slider changed old snapshot");
    }
    double output=-1;
    using ZeroSisPresentation::NormalizeHorizontalSlider;
    Require(NormalizeHorizontalSlider(20,40,180,32,110,56,false,output) && output==.5,"track midpoint mapping failed");
    Require(NormalizeHorizontalSlider(20,40,180,32,10,56,true,output) && output==0,"captured low endpoint clamp failed");
    Require(NormalizeHorizontalSlider(20,40,180,32,300,56,true,output) && output==1,"captured high endpoint clamp failed");
    Require(!NormalizeHorizontalSlider(20,40,180,32,10,56,false,output),"fresh click outside track accepted");
    Require(!NormalizeHorizontalSlider(20,40,180,32,110,10,false,output),"fresh click outside track y accepted");
    Require(!NormalizeHorizontalSlider(20,40,0,32,110,56,true,output),"zero track accepted");
    Require(!NormalizeHorizontalSlider(20,40,180,32,(std::numeric_limits<double>::quiet_NaN)(),56,true,output),"NaN pointer accepted");
}

void TestTargetLimitAndOrder(lua_State* state){
    std::vector<UiInputTarget> output;
    SetTargets(state,"(function() local t={} for i=1,4096 do t[i]={key=i,id='ProdButton',void1=i,void2=-i} end return t end)()");
    Require(Collect(state,output),"4096 targets exceeded the supported bound");
    Require(output.size()==4096 && output.front().key==1 && output.back().key==4096 &&
            output.back().void1==4096 && output.back().void2==-4096,
            "large target snapshot lost order or optional values");
}

void TestExplicitRightClickDispatch(lua_State* state){
    Require(luaL_dostring(state,"ZeroSisUi={DispatchLeftClick=function() error('wrong event') end,"
        "DispatchRightClick=function(key) LastRightKey=key; return key==73 end}")==0,
        "could not install independent right-click callback");
    UiInputRequest request{};request.kind=ZeroSisHost::UiInputKind::RightClick;request.key=73;
    Require(Dispatch(state,request) && request.consumed,"right click did not call its exact original callback");
    Require(luaL_dostring(state,"assert(LastRightKey==73)")==0,"right-click key changed across native/Lua boundary");
    request.key=0;Require(!Dispatch(state,request) && !request.consumed,"right click accepted key zero");
    request.key=UiInputDispatch::MaxExactLuaInteger+1;
    Require(!Dispatch(state,request) && !request.consumed,"right click accepted an inexact Lua key");
    request.key=73;
    Require(luaL_dostring(state,"ZeroSisUi.DispatchRightClick=nil")==0,"could not remove right-click callback");
    Require(!Dispatch(state,request) && !request.consumed,"missing right-click handler fell back to left click");
    Require(luaL_dostring(state,"ZeroSisUi.DispatchRightClick=function() return 1 end")==0,
        "could not install invalid right-click return");
    Require(!Dispatch(state,request) && !request.consumed,"nonboolean right-click response was accepted");
}

void TestUnicodeTextDispatch(lua_State* state){
    Require(luaL_dostring(state,"TextCalls=0; LastTextScalar=nil; ZeroSisUi={"
        "DispatchTextInput=function(scalar) TextCalls=TextCalls+1; LastTextScalar=scalar; return true end}")==0,
        "could not install the Unicode scalar dispatch fixture");
    UiInputRequest request{};request.kind=ZeroSisHost::UiInputKind::TextInput;
    const std::uint64_t accepted[]={0x20,0x41,0xd55c,0xae00,0x1f600,0x10ffff};
    for(const auto scalar:accepted){
        request.key=scalar;
        Require(Dispatch(state,request) && request.consumed,"valid Unicode scalar was rejected");
        lua_getglobal(state,"LastTextScalar");
        const bool exact=lua_type(state,-1)==LUA_TNUMBER && lua_tonumber(state,-1)==static_cast<lua_Number>(scalar);
        lua_pop(state,1);Require(exact,"Unicode scalar changed across the protected native/Lua boundary");
    }
    const std::uint64_t rejected[]={0,8,13,0x1f,0x7f,0x85,0x9f,0xd800,0xdbff,0xdc00,0xdfff,0x110000,
        UiInputDispatch::MaxExactLuaInteger+1};
    for(const auto scalar:rejected){
        request.key=scalar;request.consumed=true;
        Require(!Dispatch(state,request) && !request.consumed,"invalid Unicode/control scalar was accepted");
    }
    Require(luaL_dostring(state,"assert(TextCalls==6 and LastTextScalar==0x10ffff)")==0,
        "rejected text input reached the focused-control callback");
    request.key=0xd55c;
    Require(luaL_dostring(state,"ZeroSisUi.DispatchTextInput=nil")==0,"could not remove text-input export");
    Require(!Dispatch(state,request) && !request.consumed,"missing text export fell back to keydown");
    Require(luaL_dostring(state,"ZeroSisUi.DispatchTextInput=function() return 1 end")==0,
        "could not install invalid text-input return");
    Require(!Dispatch(state,request) && !request.consumed,"nonboolean text-input response was accepted");
    Require(luaL_dostring(state,"ZeroSisUi.DispatchTextInput=function() error('focus closed') end")==0,
        "could not install protected text-input failure");
    Require(!Dispatch(state,request) && !request.consumed,"Lua text callback error escaped protected rejection");
    Require(luaL_dostring(state,"ZeroSisUi.DispatchTextInput=function() return false end")==0,
        "could not install inactive-focus text-input response");
    Require(Dispatch(state,request) && !request.consumed,"inactive focus did not return an unconsumed scalar");
}

void TestMalformedPayloads(lua_State* state){
    std::vector<UiInputTarget> output;
    Accept(state,"{[1]={key=1,id='a',void1=1}}",output);
    Require(output[0].hasVoid1 && !output[0].hasVoid2,"single original first callback argument was lost");
    Accept(state,"{[1]={key=1,id='a',void2=1}}",output);
    Require(!output[0].hasVoid1 && output[0].hasVoid2,"single original second callback argument was lost");
    Reject(state,"{[1]={key=1,id='a',void1='1',void2=2}}");
    Reject(state,"{[1]={key=1,id='a',void1=1,void2=true}}");
    Reject(state,"{[1]={key=1,id='a',void1=1.5,void2=2}}");
    Reject(state,"{[1]={key=1,id='a',void1=0/0,void2=2}}");
    Reject(state,"{[1]={key=1,id='a',void1=math.huge,void2=2}}");
    Reject(state,"{[1]={key=1,id='a',void1=2147483648,void2=2}}");
    Reject(state,"{[1]={key=1,id='a',void1=-2147483649,void2=2}}");
    Reject(state,"{[1]={key=1,id='a'},[3]={key=3,id='c'}}");
    Reject(state,"{[1]={key=1,id='a'},[2]={key=1,id='b'}}");
    Reject(state,"{[1]={key=9007199254740992,id='a'}}");
    Reject(state,"{[1.5]={key=1,id='a'}}");
    Reject(state,"{named={key=1,id='a'}}");
    Reject(state,"{{key=1,id=7}}");
    Reject(state,"{{key=1,id='a'..string.char(0)..'b'}}");
    Reject(state,"{{key=1,id=string.rep('x',1025)}}");
    Reject(state,"setmetatable({{key=1,id='a'}},{})");
    Reject(state,"(function() local t={{key=1,id='a'}}; setmetatable(t[1],{}); return t end)()");
    Reject(state,"(function() local t={} for i=1,4097 do t[i]={key=i,id='x'} end return t end)()");
}
}

int main(){
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    lua_State* state=luaL_newstate();
    if(!state)throw std::runtime_error("luaL_newstate failed");
    luaL_openlibs(state);
    try{
        TestLegacyAndOptionalPayload(state);
        TestRequestedEventAndProtectedRejection(state);
        TestScrollTargetCollector(state);
        TestNonmodalConsumeMouseAndOriginalAction(state);
        TestFinitePointerAndScrollDispatch(state);
        TestExplicitRightClickDispatch(state);
        TestUnicodeTextDispatch(state);
        TestSliderDispatchAndGeometry(state);
        TestTargetLimitAndOrder(state);
        TestMalformedPayloads(state);
    }catch(...){lua_close(state);throw;}
    lua_close(state);
    std::cout<<"UI_INPUT_DISPATCH_PASS checks="<<checks<<" LUA51_SHARED=true GAMECORE_LOADED=false\n";
}
