#pragma once

extern "C" {
#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>
}

#include <cmath>

namespace ZeroSisHost {
namespace ScriptMathExtensionsDetail {

// Shipped Civ V map scripts call math.clamp(value, minimum, maximum).
// luaL_checknumber matches Lua's built-in math function argument behavior,
// including numeric strings, while NaN bounds or values are rejected.
inline int Clamp(lua_State* state) {
    if (lua_gettop(state) != 3)
        return luaL_error(state, "math.clamp expects (value, minimum, maximum)");

    const lua_Number value = luaL_checknumber(state, 1);
    const lua_Number minimum = luaL_checknumber(state, 2);
    const lua_Number maximum = luaL_checknumber(state, 3);
    if (std::isnan(value) || std::isnan(minimum) || std::isnan(maximum))
        return luaL_error(state, "math.clamp does not accept NaN");
    if (minimum > maximum)
        return luaL_error(state, "math.clamp minimum must not exceed maximum");

    lua_pushnumber(state, value < minimum ? minimum : (value > maximum ? maximum : value));
    return 1;
}

} // namespace ScriptMathExtensionsDetail

// Call after Lua's standard libraries have been opened, from the protected
// initialization callback. Only the map scripts' value/minimum/maximum helper
// is installed; the rest of Lua's math library remains the standard library.
inline void InstallScriptMathExtensions(lua_State* state) {
    lua_getglobal(state, LUA_MATHLIBNAME);
    if (!lua_istable(state, -1))
        luaL_error(state, "Lua math library is not open");
    lua_getfield(state, -1, "clamp");
    if (!lua_isnil(state, -1))
        luaL_error(state, "math.clamp is already defined");
    lua_pop(state, 1);
    lua_pushcfunction(state, &ScriptMathExtensionsDetail::Clamp);
    lua_setfield(state, -2, "clamp");
    lua_pop(state, 1);
}

} // namespace ZeroSisHost
