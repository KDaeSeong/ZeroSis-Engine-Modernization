// Controlled console check of the retail Locale argument dispatch with the real Lua 5.1 provider.
// No Host, SDK DLL, Localization library, window, GPU or audio is loaded.
#include "UiLocaleArguments.h"
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
#include <cmath>
#include <cstdio>
#include <limits>
#include <stdexcept>
#include <string>
#include <vector>

static unsigned checks=0;
static void Check(bool value,const char* why){++checks;if(!value)throw std::runtime_error(why);}

struct Recorder final {
    std::vector<std::string> pushes;bool accept=true;
    bool PushArgument(int value){pushes.push_back("int:"+std::to_string(value));return accept;}
    bool PushArgument(double value){
        char text[64];std::snprintf(text,sizeof(text),"double:%.17g%s",value,std::signbit(value)?"-":"+");
        pushes.push_back(text);return accept;
    }
    bool PushArgument(const std::string& value){pushes.push_back("text:"+value);return accept;}
};

static std::string Text(lua_State* state,int index){
    std::size_t bytes=0;const char* value=lua_tolstring(state,index,&bytes);return "lookup("+std::string(value,bytes)+")";
}

static std::vector<std::string> Dispatch(lua_State* state){
    Recorder value;
    for(int index=1;index<=lua_gettop(state);++index)
        Check(ZeroSisHost::PushRetailLocaleArgument(state,index,value,[state](int at){return Text(state,at);}),"Accepted argument reported rejection");
    return value.pushes;
}

template<class F>static void Reject(lua_State* state,F push,const char* why){
    lua_settop(state,0);push();Recorder value;
    try{ZeroSisHost::PushRetailLocaleArgument(state,1,value,[state](int at){return Text(state,at);});}
    catch(const std::invalid_argument&){Check(value.pushes.empty(),why);return;}
    Check(false,why);
}

int main(){
    lua_State* state=luaL_newstate();
    if(!state){std::fprintf(stderr,"Lua state allocation failed\n");return 1;}
    try{
        lua_pushboolean(state,1);lua_pushboolean(state,0);lua_pushnumber(state,3);lua_pushnumber(state,2.5);
        lua_pushnumber(state,-0.0);lua_pushnumber(state,-7);lua_pushnumber(state,4294967296.0);lua_pushstring(state,"TXT_KEY_A");
        lua_pushstring(state,"12");
        const auto pushes=Dispatch(state);
        const std::vector<std::string> expected={"int:1","int:0","double:3+","double:2.5+","double:-0-","double:-7-",
            "double:4294967296+","text:lookup(TXT_KEY_A)","text:lookup(12)"};
        Check(pushes==expected,"Retail boolean->int, number->double, string->text dispatch differs");
        Check(pushes[0]=="int:1" && pushes[1]=="int:0","Lua booleans become retail PushArgument(int) 1/0");
        Check(pushes[2]=="double:3+","Integral numbers keep the retail PushArgument(double) path");
        Check(pushes[8]=="text:lookup(12)","Numeric-looking strings keep the string branch");
        Reject(state,[&]{lua_pushnil(state);},"nil argument rejected without a push");
        Reject(state,[&]{lua_newtable(state);},"table argument rejected without a push");
        Reject(state,[&]{lua_pushlightuserdata(state,&checks);},"userdata argument rejected without a push");
        Reject(state,[&]{lua_pushcfunction(state,[](lua_State*)->int{return 0;});},"function argument rejected without a push");
        Reject(state,[&]{lua_pushnumber(state,std::numeric_limits<double>::quiet_NaN());},"NaN argument rejected");
        Reject(state,[&]{lua_pushnumber(state,std::numeric_limits<double>::infinity());},"infinite argument rejected");
        lua_settop(state,0);lua_pushboolean(state,1);Recorder refused;refused.accept=false;
        Check(!ZeroSisHost::PushRetailLocaleArgument(state,1,refused,[state](int at){return Text(state,at);}) && refused.pushes.size()==1,
              "A refused push is reported to the caller");
        lua_close(state);
        std::printf("{\"status\":\"PASS_RETAIL_LOCALE_ARGUMENT_DISPATCH_LUA51\",\"checks\":%u,\"lua_provider\":true,"
                    "\"localization_library_loaded\":false,\"native_execution\":false}\n",checks);
        return 0;
    }catch(const std::exception& error){lua_close(state);std::fprintf(stderr,"%s\n",error.what());return 1;}
}
