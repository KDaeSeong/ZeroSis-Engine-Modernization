#ifndef ZEROSIS_LUA_FRACTAL_NUMERIC_H
#define ZEROSIS_LUA_FRACTAL_NUMERIC_H

#include "lua.hpp"
#include <exception>
#include <cstring>

namespace ZeroSisLuaFractalNumeric
{
// Catch C++ errors before returning to Lua; never longjmp from an active catch.
template<int (*Function)(lua_State*)> int Protected(lua_State* L)
{
    char message[256] = "Fractal native operation failed";
    try
    {
        return Function(L);
    }
    catch (const std::exception& error)
    {
        const char* text = error.what();
        if (text)
        {
            const std::size_t count = (std::strlen(text) < sizeof(message) - 1)
                ? std::strlen(text) : sizeof(message) - 1;
            std::memcpy(message, text, count);
            message[count] = '\0';
        }
    }
    catch (...)
    {
    }
    return luaL_error(L, "%s", message);
}
}
#endif
