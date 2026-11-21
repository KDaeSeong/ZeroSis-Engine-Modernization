#include "lua.hpp"
#include "ScriptMathExtensions.h"
#include <cstdio>
#include <cstdlib>

static unsigned checks = 0;
static void Check(bool value, const char* message) {
    ++checks;
    if (!value) {
        std::fprintf(stderr, "HOST_SCRIPT_MATH_FAILED check=%u %s\n", checks, message);
        std::exit(1);
    }
}

static int InstallProtected(lua_State* state) {
    ZeroSisHost::InstallScriptMathExtensions(state);
    return 0;
}

int main() {
    lua_State* state = luaL_newstate();
    Check(state != nullptr, "Lua state allocation");
    luaL_openlibs(state);
    Check(lua_cpcall(state, &InstallProtected, nullptr) == 0, "protected extension installation");
    Check(lua_gettop(state) == 0, "installer stack balance");

    static const char source[] = R"lua(
assert(type(math.clamp)=='function')
assert(math.clamp(0.4,0,1)==0.4)
assert(math.clamp(-10,0,1)==0)
assert(math.clamp(10,0,1)==1)
assert(math.clamp(0,0,1)==0 and math.clamp(1,0,1)==1)
assert(math.clamp(5,5,5)==5)
assert(math.clamp(-math.huge,0,1)==0 and math.clamp(math.huge,0,1)==1)
assert(math.clamp('0.25',0,1)==0.25) -- Lua math functions accept numeric strings

local function rejected(fn)
  local ok=pcall(fn)
  assert(not ok)
end
rejected(function() math.clamp(1,0) end)
rejected(function() math.clamp(1,0,2,3) end)
rejected(function() math.clamp('not a number',0,1) end)
rejected(function() math.clamp(0/0,0,1) end)
rejected(function() math.clamp(1,0/0,1) end)
rejected(function() math.clamp(1,0,0/0) end)
rejected(function() math.clamp(1,2,0) end)
)lua";
    const int load = luaL_loadbuffer(state, source, sizeof(source) - 1, "sdk-host-script-math");
    if (load != 0) {
        const char* error = lua_tostring(state, -1);
        std::fprintf(stderr, "HOST_SCRIPT_MATH_FAILED load=%s\n", error ? error : "unknown Lua load error");
        lua_close(state);
        return 1;
    }
    const int call = lua_pcall(state, 0, 0, 0);
    if (call != 0) {
        const char* error = lua_tostring(state, -1);
        std::fprintf(stderr, "HOST_SCRIPT_MATH_FAILED run=%s\n", error ? error : "unknown Lua runtime error");
        lua_close(state);
        return 1;
    }
    Check(lua_gettop(state) == 0, "Lua test stack balance");
    lua_close(state);
    std::printf("HOST_SCRIPT_MATH_PASS checks=%u GAMECORE_LOADED=false\n", checks);
    return 0;
}
