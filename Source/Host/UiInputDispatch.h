#pragma once

// Protected Lua C thunks used by the native UI presentation driver. Call these
// only through ScriptSystem::CallCFunction while the GameCore owner lock is held.
extern "C" {
#include <lua.h>
#include <lauxlib.h>
}
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

namespace ZeroSisHost {

enum class UiInputKind : std::uint32_t { KeyDown=1, LeftClick=2, PointerMove=3, Scroll=4, RightClick=5, TextInput=6, SliderValue=7 };

struct UiInputRequest final {
    UiInputKind kind=UiInputKind::KeyDown;
    std::uint64_t key=0;
    bool consumed=false;
    double delta=0.0;
};

struct UiInputTarget final {
    std::uint64_t key=0;
    std::string id;
    bool hasVoidPayload=false;
    int void1=0;
    int void2=0;
    bool hasVoid1=false,hasVoid2=false;
    bool consumeMouseOnly=false;
    bool slider=false;
    double x=0,y=0,width=0,height=0,value=0;
};

struct UiInputTargetsRequest final {
    std::vector<UiInputTarget>* output=nullptr;
    bool trace=false;
    bool scroll=false;
    bool consumeMouse=false;
    bool slider=false;
};

struct UiInputDispatch final {
    static constexpr std::uint64_t MaxExactLuaInteger=9007199254740991ULL;
    static constexpr std::size_t MaxTargets=4096;

    // Pass as scripts.CallCFunction(vm,&UiInputDispatch::Dispatch,&request).
    // The request and its output field are owned by the caller for the full call.
    static int Dispatch(lua_State* state) {
        auto* request=static_cast<UiInputRequest*>(lua_touserdata(state,1));
        lua_settop(state,0);
        if(!request)return luaL_error(state,"UI input request is missing");
        request->consumed=false;
        const char* exportName=nullptr;
        int argumentCount=1;
        switch(request->kind){
        case UiInputKind::KeyDown:exportName="DispatchKeyDown";break;
        case UiInputKind::LeftClick:exportName="DispatchLeftClick";break;
        case UiInputKind::RightClick:exportName="DispatchRightClick";break;
        case UiInputKind::PointerMove:exportName="DispatchPointerMove";break;
        case UiInputKind::TextInput:
            exportName="DispatchTextInput";
            // Transport one printable Unicode scalar. UTF-8 conversion and the
            // focused EditBox callback belong to the receiving Lua context.
            if(request->key<0x20 || request->key>0x10ffff ||
               (request->key>=0x7f && request->key<=0x9f) ||
               (request->key>=0xd800 && request->key<=0xdfff))
                return luaL_error(state,"UI text input is not a printable Unicode scalar");
            break;
        case UiInputKind::SliderValue:
            exportName="DispatchSliderValue";argumentCount=2;
            if(request->key==0 || request->key>MaxExactLuaInteger || !std::isfinite(request->delta) ||
               request->delta<0.0 || request->delta>1.0)
                return luaL_error(state,"Invalid normalized UI slider request");
            break;
        case UiInputKind::Scroll:
            exportName="DispatchScroll";argumentCount=2;
            if(request->key==0 || request->key>MaxExactLuaInteger || !std::isfinite(request->delta) ||
               request->delta==0.0 || std::fabs(request->delta)>32768.0)
                return luaL_error(state,"Invalid finite UI scroll request");
            break;
        default:return luaL_error(state,"Unknown UI input dispatch kind");
        }
        if(request->key>MaxExactLuaInteger ||
           ((request->kind==UiInputKind::KeyDown || request->kind==UiInputKind::LeftClick || request->kind==UiInputKind::RightClick) && request->key==0))
            return luaL_error(state,"UI input key exceeds its valid exact integer range");
        lua_getglobal(state,"ZeroSisUi");
        if(!lua_istable(state,-1))return luaL_error(state,"ZeroSisUi input exports are missing");
        lua_getfield(state,-1,exportName);
        if(!lua_isfunction(state,-1))return luaL_error(state,"Required ZeroSisUi input export is missing");
        lua_pushnumber(state,static_cast<lua_Number>(request->key));
        if(request->kind==UiInputKind::Scroll || request->kind==UiInputKind::SliderValue)
            lua_pushnumber(state,static_cast<lua_Number>(request->delta));
        lua_call(state,argumentCount,1);
        if(lua_type(state,-1)!=LUA_TBOOLEAN)
            return luaL_error(state,"ZeroSisUi input export returned a non-boolean result");
        request->consumed=lua_toboolean(state,-1)!=0;
        return 0;
    }

    // Pass as scripts.CallCFunction(vm,&UiInputDispatch::CollectTargets,&request).
    // Lua traversal and validation finish before any std::string/vector allocation.
    static int CollectTargets(lua_State* state) {
        auto* request=static_cast<UiInputTargetsRequest*>(lua_touserdata(state,1));
        lua_settop(state,0);
        if(!request || !request->output)
            return luaL_error(state,"UI input target destination is missing");
        if(request->scroll && request->slider)return luaL_error(state,"Conflicting UI target filters");
        if(request->trace){std::fputs("UI_INPUT_TARGETS_STAGE=lua-begin\n",stdout);std::fflush(stdout);}

        lua_getglobal(state,"ZeroSisUi");
        if(!lua_istable(state,-1))return luaL_error(state,"ZeroSisUi input exports are missing");
        const char* collector=request->scroll?"GetScrollTargets":"GetInputTargets";
        const char* expectedEvent=request->scroll?"Scroll":request->slider?"SliderValue":"LeftClick";
        lua_getfield(state,-1,collector);
        if(!lua_isfunction(state,-1))return luaL_error(state,request->scroll?
            "Required ZeroSisUi scroll target export is missing":"Required ZeroSisUi input export is missing");
        // One retained identity is shared by a stock button's left and right
        // callbacks. Collect its left-click target once; individual contexts
        // explicitly opt into right-click dispatch at their native boundary.
        if(request->scroll)lua_call(state,0,1);
        else {lua_pushstring(state,expectedEvent);lua_call(state,1,1);}
        if(!lua_istable(state,-1))return luaL_error(state,"ZeroSisUi.GetInputTargets returned a non-table");
        if(!PlainTable(state,-1))return luaL_error(state,"ZeroSisUi.GetInputTargets returned a metatable-backed table");
        const int targets=lua_gettop(state);

        // Keep transient validation state in Lua-managed tables. Lua errors
        // use longjmp, so no native heap owner may be live during traversal.
        lua_newtable(state);
        const int uniqueKeys=lua_gettop(state);
        lua_newtable(state);
        const int normalized=lua_gettop(state);
        std::size_t count=0,maxIndex=0;
        lua_pushnil(state);
        while(lua_next(state,targets)!=0){
            std::uint64_t arrayIndex=0;
            if(!ExactInteger(state,-2,arrayIndex) || arrayIndex==0 || arrayIndex>MaxTargets)
                return luaL_error(state,"UI input target array has an invalid index");
            ++count;
            if(arrayIndex>maxIndex)maxIndex=static_cast<std::size_t>(arrayIndex);
            if(!lua_istable(state,-1))return luaL_error(state,"UI input target entry is not a table");
            if(!PlainTable(state,-1))return luaL_error(state,"UI input target entry has a metatable");
            const int entry=lua_gettop(state);

            bool consumeMouseOnly=false;
            lua_getfield(state,entry,"event");
            if((request->scroll || request->slider) && lua_type(state,-1)==LUA_TNIL)
                return luaL_error(state,"UI scroll target has no explicit Scroll event");
            if(lua_type(state,-1)!=LUA_TNIL){
                if(lua_type(state,-1)!=LUA_TSTRING)return luaL_error(state,"UI input target event is not a string");
                std::size_t eventBytes=0;const char* event=lua_tolstring(state,-1,&eventBytes);
                const std::size_t expectedBytes=std::strlen(expectedEvent);
                const bool consume=!request->scroll && !request->slider && request->consumeMouse && eventBytes==12 && std::memcmp(event,"ConsumeMouse",12)==0;
                if(consume){
                    lua_getfield(state,entry,"consumeMouse");
                    const bool declared=lua_type(state,-1)==LUA_TBOOLEAN && lua_toboolean(state,-1);lua_pop(state,1);
                    if(!declared)return luaL_error(state,"ConsumeMouse target lacks its explicit source contract");
                    consumeMouseOnly=true;
                }
                if(!consume && (eventBytes!=expectedBytes || std::memcmp(event,expectedEvent,expectedBytes)!=0))
                    return luaL_error(state,"UI input target event differs from the requested target collector");
            }
            lua_pop(state,1);

            lua_getfield(state,entry,"key");
            std::uint64_t key=0;
            const bool keyValid=ExactInteger(state,-1,key);
            lua_pop(state,1);
            if(!keyValid || key==0)return luaL_error(state,"UI input target key is not an exact positive integer");
            if(key>MaxExactLuaInteger)return luaL_error(state,"UI input target key exceeds exact Lua integer range");

            lua_getfield(state,entry,"id");
            if(lua_type(state,-1)!=LUA_TSTRING)
                return luaL_error(state,"UI input target ID is not a string");
            std::size_t idBytes=0;
            const char* id=lua_tolstring(state,-1,&idBytes);
            if(idBytes>1024)return luaL_error(state,"UI input target ID exceeds 1024 bytes");
            if(std::memchr(id,0,idBytes)!=nullptr)
                return luaL_error(state,"UI input target ID contains NUL");
            lua_pop(state,1);

            lua_getfield(state,entry,"void1");
            const bool hasVoid1=lua_type(state,-1)!=LUA_TNIL;
            int void1=0;
            if(hasVoid1 && !ExactInt32(state,-1,void1))return luaL_error(state,"UI input target void1 is not an exact int");
            lua_pop(state,1);
            lua_getfield(state,entry,"void2");
            const bool hasVoid2=lua_type(state,-1)!=LUA_TNIL;
            int void2=0;
            if(hasVoid2 && !ExactInt32(state,-1,void2))return luaL_error(state,"UI input target void2 is not an exact int");
            lua_pop(state,1);

            lua_pushnumber(state,static_cast<lua_Number>(key));
            lua_rawget(state,uniqueKeys);
            const bool duplicateKey=lua_type(state,-1)!=LUA_TNIL;
            lua_pop(state,1);
            if(duplicateKey)return luaL_error(state,"UI input target keys are duplicated");
            lua_pushnumber(state,static_cast<lua_Number>(key));lua_pushboolean(state,1);lua_rawset(state,uniqueKeys);

            // Normalize all validated values into Lua-owned storage. The
            // later native allocation pass only reads these scalar/string values.
            lua_newtable(state);
            const int row=lua_gettop(state);
            lua_pushinteger(state,1);lua_pushnumber(state,static_cast<lua_Number>(key));lua_rawset(state,row);
            lua_pushinteger(state,2);lua_pushlstring(state,id,idBytes);lua_rawset(state,row);
            lua_pushinteger(state,3);lua_pushboolean(state,hasVoid1 && hasVoid2);lua_rawset(state,row);
            if(hasVoid1){
                lua_pushinteger(state,4);lua_pushnumber(state,static_cast<lua_Number>(void1));lua_rawset(state,row);
            }
            if(hasVoid2){
                lua_pushinteger(state,5);lua_pushnumber(state,static_cast<lua_Number>(void2));lua_rawset(state,row);
            }
            lua_pushinteger(state,6);lua_pushboolean(state,hasVoid1);lua_rawset(state,row);
            lua_pushinteger(state,7);lua_pushboolean(state,hasVoid2);lua_rawset(state,row);
            lua_pushinteger(state,8);lua_pushboolean(state,consumeMouseOnly);lua_rawset(state,row);
            lua_pushinteger(state,9);lua_pushboolean(state,request->slider);lua_rawset(state,row);
            if(request->slider){
                const char* fields[]={"x","y","width","height","value"};
                double values[5]{};
                lua_getfield(state,entry,"bounds");
                if(!PlainTable(state,-1))return luaL_error(state,"Slider bounds must be a plain table");
                const int bounds=lua_gettop(state);
                for(int i=0;i<5;++i){
                    lua_getfield(state,i<4?bounds:entry,fields[i]);
                    if(lua_type(state,-1)!=LUA_TNUMBER || !std::isfinite(lua_tonumber(state,-1)))
                        return luaL_error(state,"Slider geometry/value must be finite numbers");
                    values[i]=lua_tonumber(state,-1);lua_pop(state,1);
                    lua_pushinteger(state,10+i);lua_pushnumber(state,values[i]);lua_rawset(state,row);
                }
                lua_pop(state,1);
                if(values[0]<0 || values[1]<0 || values[2]<=0 || values[3]<=0 ||
                   values[0]+values[2]>1920 || values[1]+values[3]>1080 || values[4]<0 || values[4]>1)
                    return luaL_error(state,"Slider target exceeds the committed viewport/value range");
                for(int i=0;i<2;++i){
                    lua_getfield(state,entry,i?"maximum":"minimum");
                    const bool valid=lua_type(state,-1)==LUA_TNUMBER && lua_tonumber(state,-1)==i;lua_pop(state,1);
                    if(!valid)return luaL_error(state,"Slider target must declare its normalized min/max");
                }
            }
            lua_pushnumber(state,static_cast<lua_Number>(arrayIndex));lua_pushvalue(state,row);lua_rawset(state,normalized);
            lua_pop(state,2); // normalized row and source entry, leaving lua_next key.
        }
        if(count!=maxIndex)return luaL_error(state,"UI input target array is sparse");
        if(request->trace){std::fprintf(stdout,"UI_INPUT_TARGETS_STAGE=lua-end|count=%zu\n",count);std::fflush(stdout);}

        if(!lua_checkstack(state,6))return luaL_error(state,"Could not grow UI input target read stack");
        // No native owner ever lives in this Lua-error-capable frame. MSVC
        // longjmp may consult stale optimized EH state even after a block's
        // owners have gone out of scope, so keep their complete lifetime in a
        // separate non-inlined helper that never raises a Lua error.
        if(!CopyNormalized(state,normalized,count,request->output,request->trace))
            return luaL_error(state,"Could not allocate UI input target snapshot");
        return 0;
    }

private:
    __declspec(noinline) static bool CopyNormalized(lua_State* state,int normalized,std::size_t count,
                                                   std::vector<UiInputTarget>* output,bool trace) noexcept {
        try{
                std::vector<UiInputTarget> collected;
                collected.reserve(count);
                for(std::size_t i=0;i<count;++i){
                    if(trace && i<2){std::fprintf(stdout,"UI_INPUT_TARGETS_STAGE=copy-begin|index=%zu\n",i);std::fflush(stdout);}
                    lua_rawgeti(state,normalized,static_cast<int>(i+1));
                    const int row=lua_gettop(state);
                    lua_rawgeti(state,row,1);const auto key=static_cast<std::uint64_t>(lua_tonumber(state,-1));lua_pop(state,1);
                    lua_rawgeti(state,row,2);std::size_t idBytes=0;const char* id=lua_tolstring(state,-1,&idBytes);
                    std::string idCopy(id,idBytes);lua_pop(state,1);
                    lua_rawgeti(state,row,3);const bool hasVoidPayload=lua_toboolean(state,-1)!=0;lua_pop(state,1);
                    lua_rawgeti(state,row,6);const bool hasVoid1=lua_toboolean(state,-1)!=0;lua_pop(state,1);
                    lua_rawgeti(state,row,7);const bool hasVoid2=lua_toboolean(state,-1)!=0;lua_pop(state,1);
                    lua_rawgeti(state,row,8);const bool consumeMouseOnly=lua_toboolean(state,-1)!=0;lua_pop(state,1);
                    int void1=0,void2=0;
                    if(hasVoid1){
                        lua_rawgeti(state,row,4);void1=static_cast<int>(lua_tonumber(state,-1));lua_pop(state,1);
                    }
                    if(hasVoid2){
                        lua_rawgeti(state,row,5);void2=static_cast<int>(lua_tonumber(state,-1));lua_pop(state,1);
                    }
                    lua_pop(state,1);
                    UiInputTarget target;
                    target.key=key;target.id=std::move(idCopy);target.hasVoidPayload=hasVoidPayload;
                    target.void1=void1;target.void2=void2;
                    target.hasVoid1=hasVoid1;target.hasVoid2=hasVoid2;
                    target.consumeMouseOnly=consumeMouseOnly;
                    // Validation completed before this non-raising allocation pass.
                    lua_rawgeti(state,normalized,static_cast<int>(i+1));const int geometryRow=lua_gettop(state);
                    lua_rawgeti(state,geometryRow,9);target.slider=lua_toboolean(state,-1)!=0;lua_pop(state,1);
                    if(target.slider){
                        double* fields[]={&target.x,&target.y,&target.width,&target.height,&target.value};
                        for(int j=0;j<5;++j){lua_rawgeti(state,geometryRow,10+j);*fields[j]=lua_tonumber(state,-1);lua_pop(state,1);}
                    }
                    lua_pop(state,1);
                    collected.push_back(std::move(target));
                    if(trace && i<2){std::fprintf(stdout,"UI_INPUT_TARGETS_STAGE=copy-end|index=%zu\n",i);std::fflush(stdout);}
                }
                *output=std::move(collected);
                if(trace){std::fputs("UI_INPUT_TARGETS_STAGE=copy-complete\n",stdout);std::fflush(stdout);}
                return true;
        }catch(...){return false;}
    }
    static bool PlainTable(lua_State* state,int index) noexcept {
        if(!lua_istable(state,index))return false;
        if(!lua_getmetatable(state,index))return true;
        lua_pop(state,1);return false;
    }

    static bool ExactInteger(lua_State* state,int index,std::uint64_t& output) noexcept {
        if(lua_type(state,index)!=LUA_TNUMBER)return false;
        const lua_Number value=lua_tonumber(state,index);
        if(!std::isfinite(static_cast<double>(value)) || value<0 ||
           value>static_cast<lua_Number>(MaxExactLuaInteger) ||
           std::floor(static_cast<double>(value))!=static_cast<double>(value))return false;
        output=static_cast<std::uint64_t>(value);
        return true;
    }

    static bool ExactInt32(lua_State* state,int index,int& output) noexcept {
        if(lua_type(state,index)!=LUA_TNUMBER)return false;
        const double value=static_cast<double>(lua_tonumber(state,index));
        if(!std::isfinite(value) || std::floor(value)!=value ||
           value<static_cast<double>((std::numeric_limits<int>::min)()) ||
           value>static_cast<double>((std::numeric_limits<int>::max)()))return false;
        output=static_cast<int>(value);
        return true;
    }
};

} // namespace ZeroSisHost
