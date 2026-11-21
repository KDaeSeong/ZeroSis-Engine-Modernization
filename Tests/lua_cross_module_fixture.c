#include <lua.h>

/*
 * Small DLL side of the cross-module Lua 5.1 fixture.
 *
 * Exported ABI (x64 names are undecorated):
 *   FixturePushEmptyTable(lua_State*) -> pushes one empty table and returns 1
 *   FixtureCollect(lua_State*, int) -> runs full GC cycles, returns stack top
 *
 * lua_createtable(0, 0) creates a table whose hash part uses the implementation
 * module's private ltable.c dummynode_ sentinel. The caller owns the VM; this
 * fixture never closes it.
 */

__declspec(dllexport) int __cdecl FixturePushEmptyTable(lua_State* state)
{
    if (state == 0)
        return -1;
    lua_createtable(state, 0, 0);
    return 1;
}

__declspec(dllexport) int __cdecl FixtureCollect(lua_State* state, int cycles)
{
    int i;
    if (state == 0 || cycles < 0 || cycles > 100000)
        return -1;
    for (i = 0; i < cycles; ++i)
        lua_gc(state, LUA_GCCOLLECT, 0);
    return lua_gettop(state);
}
