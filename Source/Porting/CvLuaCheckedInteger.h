#ifndef ZEROSIS_CV_LUA_CHECKED_INTEGER_H
#define ZEROSIS_CV_LUA_CHECKED_INTEGER_H

#include "lua.hpp"
#include "CvCheckedNarrow.h"
#include <cmath>

namespace CvLuaChecked
{
// Keep the SDK's Lua ABI and its integer conversion operation. Check the floating
// value before that operation, then check its result before narrowing to game data.
inline lua_Integer ToInteger(lua_State* state, int index)
{
    const lua_Number value = lua_tonumber(state, index);
    const lua_Number exclusiveUpper = std::ldexp(lua_Number(1), std::numeric_limits<lua_Integer>::digits);
    if (!(value >= -exclusiveUpper && value < exclusiveUpper))
    {
        luaL_argerror(state, index, "finite Lua integer in native range expected");
        return 0;
    }
    return lua_tointeger(state, index);
}

template<class To> inline To ToGameInteger(lua_State* state, int index)
{
    static_assert(sizeof(lua_Integer) > sizeof(To), "This adapter requires the x64 Lua integer ABI");
    To result = 0;
    if (!CvChecked::TryInteger(ToInteger(state, index), result))
    {
        luaL_argerror(state, index, "integer outside the game field range");
        return 0;
    }
    return result;
}
inline int ToInt(lua_State* state, int index) { return ToGameInteger<int>(state, index); }
inline int CheckInt(lua_State* state, int index)
{
    luaL_checknumber(state, index); // Preserve numeric-string acceptance and type errors.
    return ToInt(state, index);
}
inline unsigned int CheckUInt(lua_State* state, int index)
{
    const lua_Number value = luaL_checknumber(state, index);
    if (!(value >= 0))
    {
        luaL_argerror(state, index, "nonnegative integer expected");
        return 0;
    }
    return ToGameInteger<unsigned int>(state, index);
}
inline int OptInt(lua_State* state, int index, int defaultValue)
{
    return lua_isnoneornil(state, index) ? defaultValue : CheckInt(state, index);
}
}
#endif
