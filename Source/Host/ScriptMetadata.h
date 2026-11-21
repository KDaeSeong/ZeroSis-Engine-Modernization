#pragma once
#include "ScriptSystem.h"

namespace ZeroSisHost {
struct MapScriptMetadata {std::string name,description;unsigned customOptions=0;};
namespace ScriptMetadataDetail {
struct ReadCall {ScriptSystem* scripts;MapScriptMetadata* metadata;};
inline int Read(lua_State* state){
    auto* call=static_cast<ReadCall*>(lua_touserdata(state,1));lua_settop(state,0);
    lua_getglobal(state,"GetMapScriptInfo");
    if(!call->scripts->CallFunction(state,0,1))throw std::runtime_error(call->scripts->LastError());
    if(!lua_istable(state,-1))throw std::runtime_error("Map script metadata is not a table");
    lua_getfield(state,-1,"Name");
    if(lua_type(state,-1)!=LUA_TSTRING)throw std::runtime_error("Map script name is not a string");
    std::size_t length=0;const char* text=lua_tolstring(state,-1,&length);call->metadata->name.assign(text,length);lua_pop(state,1);
    lua_getfield(state,-1,"Description");
    if(lua_type(state,-1)!=LUA_TSTRING)throw std::runtime_error("Map script description is not a string");
    text=lua_tolstring(state,-1,&length);call->metadata->description.assign(text,length);lua_pop(state,1);
    lua_getfield(state,-1,"CustomOptions");
    if(!lua_isnil(state,-1) && !lua_istable(state,-1))throw std::runtime_error("Map script options are not a table");
    const auto count=lua_isnil(state,-1)?0:lua_objlen(state,-1);
    if(count>UINT_MAX)throw std::overflow_error("Too many map script options");
    call->metadata->customOptions=static_cast<unsigned>(count);return 0;
}
}
inline MapScriptMetadata ReadMapScriptMetadata(ScriptSystem& scripts,const char* file){
    struct Thread {
        ScriptSystem& scripts;lua_State* state;
        ~Thread(){scripts.FreeLuaThread(state);}
    } thread{scripts,scripts.CreateLuaThread("Map script metadata")};
    if(!scripts.LoadFile(thread.state,file))throw std::runtime_error(scripts.LastError());
    MapScriptMetadata result;ScriptMetadataDetail::ReadCall call={&scripts,&result};
    if(!scripts.CallCFunction(thread.state,&ScriptMetadataDetail::Read,&call))throw std::runtime_error(scripts.LastError());return result;
}
}
