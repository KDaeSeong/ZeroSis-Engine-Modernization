extern "C"
{
#include <lua.h>
#include <lauxlib.h>
#include <lualib.h>
}

#include <cstdio>
#include <cstring>
#include <stdexcept>

extern "C" __declspec(dllimport) int ZeroSisLuaInvoke(lua_State* state, lua_CFunction callback);

namespace
{
    int checks = 0;
    int destroyed = 0;
    char longMessage[2048] = {};

    bool Check(bool condition, const char* description)
    {
        ++checks;
        if(!condition)
        {
            std::fprintf(stderr, "SHARED_LUA_CALLBACKS_FAIL check=%d %s\n", checks, description);
            return false;
        }
        return true;
    }

    struct Lifetime
    {
        ~Lifetime() { ++destroyed; }
    };

    int ReturnSeven(lua_State* state)
    {
        lua_pushinteger(state, 7);
        return 1;
    }

    int ThrowStandard(lua_State*)
    {
        Lifetime lifetime;
        (void)lifetime;
        throw std::runtime_error("expected standard callback failure");
    }

    int ThrowUnknown(lua_State*)
    {
        Lifetime lifetime;
        (void)lifetime;
        throw 37;
    }

    int ThrowLongStandard(lua_State*)
    {
        Lifetime lifetime;
        (void)lifetime;
        throw std::runtime_error(longMessage);
    }

    int OrdinaryLuaError(lua_State* state)
    {
        return luaL_error(state, "ordinary Lua error must pass through");
    }

    int InvokeNormal(lua_State* state)
    {
        return ZeroSisLuaInvoke(state, &ReturnSeven);
    }

    int InvokeStandard(lua_State* state)
    {
        return ZeroSisLuaInvoke(state, &ThrowStandard);
    }

    int InvokeUnknown(lua_State* state)
    {
        return ZeroSisLuaInvoke(state, &ThrowUnknown);
    }

    bool ErrorContains(lua_State* state, const char* expected)
    {
        const char* actual = lua_tostring(state, -1);
        return actual != 0 && std::strstr(actual, expected) != 0;
    }

    int RecoverFromNestedPcall(lua_State* state)
    {
        lua_pushcfunction(state, &ThrowStandard);
        const int status = lua_pcall(state, 0, 0, 0);
        if(status != 0 && ErrorContains(state, "expected standard callback failure"))
        {
            lua_pop(state, 1);
            lua_pushinteger(state, 19);
            return 1;
        }
        return luaL_error(state, "nested pcall did not catch the callback error");
    }

    int RecoverFromNestedCpcall(lua_State* state)
    {
        const int status = lua_cpcall(state, &ThrowUnknown, 0);
        if(status != 0 && ErrorContains(state, "Unknown C++ Lua callback exception"))
        {
            lua_pop(state, 1);
            lua_pushinteger(state, 23);
            return 1;
        }
        return luaL_error(state, "nested cpcall did not catch the callback error");
    }

    bool Run(lua_State* state)
    {
        lua_pushcfunction(state, &InvokeNormal);
        if(!Check(lua_pcall(state, 0, 1, 0) == 0, "normal callback crosses bridge")) return false;
        if(!Check(lua_tointeger(state, -1) == 7, "normal callback result preserved")) return false;
        lua_pop(state, 1);

        lua_pushcfunction(state, &OrdinaryLuaError);
        if(!Check(lua_pcall(state, 0, 0, 0) != 0, "ordinary luaL_error remains a Lua error")) return false;
        const char* ordinaryError = lua_tostring(state, -1);
        if(!Check(ordinaryError != 0 && std::strcmp(ordinaryError, "ordinary Lua error must pass through") == 0,
            "ordinary Lua error payload is unchanged by the C++ guard")) return false;
        lua_pop(state, 1);

        destroyed = 0;
        if(!Check(lua_cpcall(state, &InvokeStandard, 0) != 0, "standard exception becomes Lua error")) return false;
        if(!Check(destroyed == 1, "standard exception destroys callback locals before longjmp")) return false;
        if(!Check(ErrorContains(state, "expected standard callback failure"), "standard exception message preserved")) return false;
        lua_pop(state, 1);

        destroyed = 0;
        lua_pushcfunction(state, &ThrowStandard);
        if(!Check(lua_pcall(state, 0, 0, 0) != 0, "raw standard callback passes through the shared ldo guard")) return false;
        if(!Check(destroyed == 1, "raw standard callback locals unwind before Lua catches")) return false;
        if(!Check(ErrorContains(state, "expected standard callback failure"), "raw callback exception reaches the protected Lua caller")) return false;
        lua_pop(state, 1);

        destroyed = 0;
        lua_pushcfunction(state, &ThrowUnknown);
        if(!Check(lua_pcall(state, 0, 0, 0) != 0, "raw unknown callback passes through the shared ldo guard")) return false;
        if(!Check(destroyed == 1, "raw unknown callback locals unwind before Lua catches")) return false;
        if(!Check(ErrorContains(state, "Unknown C++ Lua callback exception"), "raw unknown exception reaches the protected Lua caller")) return false;
        lua_pop(state, 1);

        destroyed = 0;
        if(!Check(lua_cpcall(state, &InvokeUnknown, 0) != 0, "unknown exception becomes Lua error")) return false;
        if(!Check(destroyed == 1, "unknown exception destroys callback locals before longjmp")) return false;
        if(!Check(ErrorContains(state, "Unknown C++ Lua callback exception"), "unknown exception is identified")) return false;
        lua_pop(state, 1);

        destroyed = 0;
        lua_pushcfunction(state, &ThrowLongStandard);
        if(!Check(lua_pcall(state, 0, 0, 0) != 0, "long standard exception becomes Lua error")) return false;
        if(!Check(destroyed == 1, "long-message callback locals unwind before Lua catches")) return false;
        std::size_t errorLength = 0;
        const char* error = lua_tolstring(state, -1, &errorLength);
        const char prefix[] = "C++ Lua callback: ";
        if(!Check(error != 0 && errorLength == 1023, "long exception is bounded to the fixed error buffer")) return false;
        if(!Check(error != 0 && std::strncmp(error, prefix, sizeof(prefix) - 1) == 0,
            "long exception retains the callback error prefix")) return false;
        bool remainderIsMessage = error != 0;
        for(std::size_t i = sizeof(prefix) - 1; remainderIsMessage && i < errorLength; ++i)
        {
            remainderIsMessage = error[i] == 'X';
        }
        if(!Check(remainderIsMessage, "long exception truncation has no corruption or overread")) return false;
        lua_pop(state, 1);

        lua_pushcfunction(state, &RecoverFromNestedPcall);
        if(!Check(lua_pcall(state, 0, 1, 0) == 0, "nested pcall recovers to its caller")) return false;
        if(!Check(lua_tointeger(state, -1) == 19, "nested pcall caller continues after recovery")) return false;
        lua_pop(state, 1);

        lua_pushcfunction(state, &RecoverFromNestedCpcall);
        if(!Check(lua_pcall(state, 0, 1, 0) == 0, "nested cpcall recovers to its caller")) return false;
        if(!Check(lua_tointeger(state, -1) == 23, "nested cpcall caller continues after recovery")) return false;
        lua_pop(state, 1);

        if(!Check(lua_gettop(state) == 0, "protected failures leave a clean stack")) return false;
        lua_pushcfunction(state, &InvokeNormal);
        if(!Check(lua_pcall(state, 0, 1, 0) == 0, "same VM remains usable after callback errors")) return false;
        if(!Check(lua_tointeger(state, -1) == 7, "reused VM returns expected result")) return false;
        lua_pop(state, 1);

        lua_State* coroutine = lua_newthread(state);
        if(!Check(coroutine != 0, "coroutine state is created")) return false;
        if(!Check(luaL_loadstring(coroutine, "return coroutine.yield(41)") == 0,
            "coroutine yield script loads")) return false;
        if(!Check(lua_resume(coroutine, 0) == LUA_YIELD, "ordinary coroutine yield is preserved")) return false;
        if(!Check(lua_tointeger(coroutine, -1) == 41, "coroutine yields its original value")) return false;
        if(!Check(lua_resume(coroutine, 0) == 0, "coroutine resumes after yield")) return false;
        if(!Check(lua_gettop(coroutine) == 0, "resumed coroutine completes with a clean stack")) return false;
        lua_pop(state, 1);
        return true;
    }
}

int main()
{
    std::memset(longMessage, 'X', sizeof(longMessage) - 1);
    longMessage[sizeof(longMessage) - 1] = '\0';
    lua_State* state = luaL_newstate();
    if(!Check(state != 0, "shared Lua state creation")) return 1;
    luaL_openlibs(state);

    const bool passed = Run(state);
    lua_close(state);
    if(!passed) return 1;

    std::printf("SHARED_LUA_CALLBACKS_PASS checks=%d GAMECORE_LOADED=false\n", checks);
    return 0;
}
