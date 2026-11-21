#ifndef ZEROSIS_LUA_FRACTAL_H
#define ZEROSIS_LUA_FRACTAL_H

#include "lua.hpp"
#include <new>
#include <type_traits>

namespace ZeroSisLuaFractal
{
// No CvFractal layout change: this storage belongs only to the Lua VM.
template<class T> struct Storage
{
    bool alive;
    typename std::aligned_storage<sizeof(T), alignof(T)>::type value;
    T* Pointer() { return reinterpret_cast<T*>(&value); }
};

template<class T> inline void* RegistryKey()
{
    static unsigned char key;
    return &key;
}

inline int AbsoluteIndex(lua_State* L, int index)
{
    return index < 0 && index > LUA_REGISTRYINDEX ? lua_gettop(L) + index + 1 : index;
}

template<class T> inline void PushRegistry(lua_State* L)
{
    lua_pushlightuserdata(L, RegistryKey<T>());
    lua_rawget(L, LUA_REGISTRYINDEX);
    if (lua_isnil(L, -1))
    {
        lua_pop(L, 1);
        lua_newtable(L);
        lua_newtable(L);
        lua_pushliteral(L, "k");
        lua_setfield(L, -2, "__mode");
        lua_setmetatable(L, -2);
        lua_pushlightuserdata(L, RegistryKey<T>());
        lua_pushvalue(L, -2);
        lua_rawset(L, LUA_REGISTRYINDEX);
    }
    else if (!lua_istable(L, -1))
        luaL_error(L, "Fractal ownership registry is invalid");
}

template<class T> inline Storage<T>* Find(lua_State* L, int index)
{
    index = AbsoluteIndex(L, index);
    if (lua_type(L, index) != LUA_TUSERDATA || lua_objlen(L, index) != sizeof(Storage<T>))
        return NULL;
    const int top = lua_gettop(L);
    lua_pushlightuserdata(L, RegistryKey<T>());
    lua_rawget(L, LUA_REGISTRYINDEX);
    bool owned = false;
    if (lua_istable(L, -1))
    {
        lua_pushvalue(L, index);
        lua_rawget(L, -2);
        owned = lua_type(L, -1) == LUA_TBOOLEAN && lua_toboolean(L, -1) != 0;
    }
    lua_settop(L, top);
    // Do not inspect any native storage until this VM's membership is proved.
    return owned ? static_cast<Storage<T>*>(lua_touserdata(L, index)) : NULL;
}

template<class T> inline Storage<T>* CheckedStorage(lua_State* L, int index)
{
    Storage<T>* value = Find<T>(L, index);
    if (!value)
        luaL_argerror(L, index, "owned Fractal userdata expected");
    return value;
}

template<class T> inline T* Check(lua_State* L, int index)
{
    Storage<T>* value = CheckedStorage<T>(L, index);
    if (!value->alive)
        luaL_argerror(L, index, "Fractal has already been destroyed");
    return value->Pointer();
}

template<class T> inline T* Optional(lua_State* L, int index)
{
    return lua_isnoneornil(L, index) ? NULL : Check<T>(L, index);
}

template<class T> inline int Destroy(lua_State* L, int index)
{
    static_assert(std::is_nothrow_destructible<T>::value, "Lua finalizers must not throw C++ exceptions");
    Storage<T>* value = CheckedStorage<T>(L, index);
    if (value->alive)
    {
        value->alive = false;
        value->Pointer()->~T();
    }
    return 0;
}

template<class T> inline T* Create(lua_State* L, lua_CFunction getHeight, lua_CFunction buildRidges, lua_CFunction destroy)
{
    static_assert(alignof(Storage<T>) <= alignof(lua_Number), "Fractal storage exceeds Lua 5.1 userdata alignment");
    PushRegistry<T>(L);
    const int registry = lua_gettop(L);
    Storage<T>* value = new(lua_newuserdata(L, sizeof(Storage<T>))) Storage<T>;
    value->alive = false;
    const int userdata = lua_gettop(L);
    lua_pushvalue(L, userdata);
    lua_pushboolean(L, 1);
    lua_rawset(L, registry);

    lua_newtable(L);
    lua_newtable(L);
    lua_pushvalue(L, userdata);
    lua_pushcclosure(L, getHeight, 1);
    lua_setfield(L, -2, "GetHeight");
    lua_pushvalue(L, userdata);
    lua_pushcclosure(L, buildRidges, 1);
    lua_setfield(L, -2, "BuildRidges");
    lua_setfield(L, -2, "__index");
    lua_pushcclosure(L, destroy, 0);
    lua_setfield(L, -2, "__gc");
    lua_setmetatable(L, userdata);
    lua_remove(L, registry);

    // No allocating Lua API may run after native construction and before alive.
    T* result = new(&value->value) T;
    value->alive = true;
    return result;
}
}
#endif
