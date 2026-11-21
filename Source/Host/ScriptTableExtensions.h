#pragma once

extern "C" {
#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>
}

#include <climits>
#include <cmath>

namespace ZeroSisHost {
namespace ScriptTableExtensionsDetail {

// Civ V's shipped Lua uses table.fill(value, length) to create an array and
// table.fill(existingTable, value, length) to overwrite its first length slots.
// The same value is assigned to every slot; table values therefore remain
// shared references, matching ordinary Lua assignment semantics.
inline int CheckedLength(lua_State* state,int index) {
    if(lua_type(state,index)!=LUA_TNUMBER)
        return luaL_error(state,"table.fill length must be a number");
    const lua_Number value=lua_tonumber(state,index);
    if(!std::isfinite(value) || value<0 || std::floor(value)!=value || value>INT_MAX)
        return luaL_error(state,"table.fill length must be an integer from 0 through INT_MAX");
    return static_cast<int>(value);
}

inline int Fill(lua_State* state) {
    const int arguments=lua_gettop(state);
    int tableIndex=0,valueIndex=0,lengthIndex=0;
    if(arguments==2) {
        valueIndex=1;lengthIndex=2;
    } else if(arguments==3) {
        if(!lua_istable(state,1))
            return luaL_error(state,"table.fill with three arguments requires a target table first");
        tableIndex=1;valueIndex=2;lengthIndex=3;
    } else {
        return luaL_error(state,"table.fill expects (value, length) or (table, value, length)");
    }

    const int length=CheckedLength(state,lengthIndex);
    if(arguments==2) {
        lua_newtable(state);
        tableIndex=lua_gettop(state);
    }

    // Avoid incrementing past INT_MAX, since lua_rawseti takes an int index.
    int index=1;
    while(index<=length) {
        lua_pushvalue(state,valueIndex);
        lua_rawseti(state,tableIndex,index);
        if(index==length)break;
        ++index;
    }
    lua_pushvalue(state,tableIndex);
    return 1;
}

}

// Call after Lua's standard libraries have been opened. The caller should put
// this function inside its normal protected Lua initialization boundary.
inline void InstallScriptTableExtensions(lua_State* state) {
    lua_getglobal(state,LUA_TABLIBNAME);
    if(!lua_istable(state,-1))
        luaL_error(state,"Lua table library is not open");
    lua_getfield(state,-1,"fill");
    if(!lua_isnil(state,-1))
        luaL_error(state,"table.fill is already defined");
    lua_pop(state,1);
    lua_pushcfunction(state,&ScriptTableExtensionsDetail::Fill);
    lua_setfield(state,-2,"fill");
    lua_pop(state,1);
}

}
