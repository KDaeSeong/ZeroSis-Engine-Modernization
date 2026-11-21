#ifndef ZEROSIS_LUA_BORROWED_H
#define ZEROSIS_LUA_BORROWED_H

#include "lua.hpp"
#include <Windows.h>
#include <cstdint>
#include <exception>
#include <new>

namespace ZeroSisLuaBorrowed
{
// Records own no gameplay object. All Lua calls take place outside the lock.
struct Entry
{
    const void* target;
    Entry* next;
    Entry** previous;
    bool fence;
};
struct Tracking
{
    SRWLOCK lock;
    Entry* buckets[256];
    unsigned fences[256];
};
inline Tracking& State()
{
    // Trivial zero initialization/destruction: safe during module teardown too.
    static Tracking state = {};
    return state;
}
inline unsigned Bucket(const void* address)
{
    const std::uintptr_t value = reinterpret_cast<std::uintptr_t>(address);
    return static_cast<unsigned>(((value >> 4) ^ (value >> 13)) & 255);
}
inline void UnlinkLocked(Entry* entry)
{
    if (entry->previous)
    {
        if (entry->fence) --State().fences[Bucket(entry->target)];
        *entry->previous = entry->next;
        if (entry->next) entry->next->previous = entry->previous;
    }
    entry->target = NULL;
    entry->previous = NULL;
    entry->next = NULL;
}
inline void LinkLocked(Entry* entry, const void* target, bool fence)
{
    Entry** head = &State().buckets[Bucket(target)];
    entry->target = target;
    entry->fence = fence;
    if (fence) ++State().fences[Bucket(target)];
    entry->previous = head;
    entry->next = *head;
    if (*head) (*head)->previous = &entry->next;
    *head = entry;
}
inline bool FencedLocked(const void* target)
{
    if (!State().fences[Bucket(target)]) return false;
    for (Entry* entry = State().buckets[Bucket(target)]; entry; entry = entry->next)
        if (entry->target == target && entry->fence) return true;
    return false;
}
inline void InvalidateLocked(const void* target)
{
    Entry* entry = State().buckets[Bucket(target)];
    while (entry)
    {
        Entry* next = entry->next;
        if (entry->target == target && !entry->fence) UnlinkLocked(entry);
        entry = next;
    }
}
inline void Invalidate(const void* target) noexcept
{
    if (!target) return;
    AcquireSRWLockExclusive(&State().lock);
    InvalidateLocked(target);
    ReleaseSRWLockExclusive(&State().lock);
}
inline void Detach(Entry* entry) noexcept
{
    AcquireSRWLockExclusive(&State().lock);
    UnlinkLocked(entry);
    ReleaseSRWLockExclusive(&State().lock);
}
inline const void* Target(Entry* entry) noexcept
{
    AcquireSRWLockShared(&State().lock);
    const void* result = entry->target && !FencedLocked(entry->target) ? entry->target : NULL;
    ReleaseSRWLockShared(&State().lock);
    return result;
}
inline bool Observe(Entry* entry, const void* target) noexcept
{
    AcquireSRWLockExclusive(&State().lock);
    const bool allowed = target && !FencedLocked(target);
    if (allowed) LinkLocked(entry, target, false);
    ReleaseSRWLockExclusive(&State().lock);
    return allowed;
}
class InvalidationScope
{
    Entry entry_;
public:
    explicit InvalidationScope(const void* target) noexcept : entry_{}
    {
        if (!target) return;
        AcquireSRWLockExclusive(&State().lock);
        InvalidateLocked(target);
        LinkLocked(&entry_, target, true);
        ReleaseSRWLockExclusive(&State().lock);
    }
    ~InvalidationScope() noexcept { Detach(&entry_); }
    InvalidationScope(const InvalidationScope&) = delete;
    InvalidationScope& operator=(const InvalidationScope&) = delete;
};
class SuspensionScope
{
    Entry entry_;
public:
    explicit SuspensionScope(const void* target) noexcept : entry_{}
    {
        if (!target) return;
        AcquireSRWLockExclusive(&State().lock);
        LinkLocked(&entry_, target, true);
        ReleaseSRWLockExclusive(&State().lock);
    }
    ~SuspensionScope() noexcept { Detach(&entry_); }
    SuspensionScope(const SuspensionScope&) = delete;
    SuspensionScope& operator=(const SuspensionScope&) = delete;
};
class RetireOnExit
{
    const void* target_;
public:
    explicit RetireOnExit(const void* target) noexcept : target_(target) {}
    ~RetireOnExit() noexcept { Invalidate(target_); }
    RetireOnExit(const RetireOnExit&) = delete;
    RetireOnExit& operator=(const RetireOnExit&) = delete;
};
class InvalidNativeReference : public std::exception
{
public:
    const char* what() const noexcept override { return "Native gameplay object no longer exists or is changing state"; }
};
template<class T> class NativeReference
{
    mutable Entry entry_;
public:
    explicit NativeReference(T* pointer = NULL) noexcept : entry_{} { Observe(&entry_, pointer); }
    NativeReference(const NativeReference& other) noexcept : entry_{} { Observe(&entry_, other.Get()); }
    NativeReference& operator=(const NativeReference& other) noexcept
    {
        if (this != &other) Reset(other.Get());
        return *this;
    }
    NativeReference& operator=(T* pointer) noexcept { Reset(pointer); return *this; }
    ~NativeReference() noexcept { Detach(&entry_); }
    void Reset(T* pointer = NULL) noexcept { Detach(&entry_); Observe(&entry_, pointer); }
    T* Get() const noexcept { return static_cast<T*>(const_cast<void*>(Target(&entry_))); }
    operator T*() const noexcept { return Get(); }
    T* operator->() const
    {
        T* pointer = Get();
        if (!pointer) throw InvalidNativeReference();
        return pointer;
    }
    T& operator*() const { return *operator->(); }
};

template<class T, int Kind> inline void* RegistryKey()
{
    static unsigned char key;
    return &key;
}
inline int AbsoluteIndex(lua_State* L, int index)
{
    return index < 0 && index > LUA_REGISTRYINDEX ? lua_gettop(L) + index + 1 : index;
}
inline bool ValidIndex(lua_State* L, int index)
{
    if (index == 0) return false;
    if (index > 0) return index <= lua_gettop(L);
    return index <= LUA_REGISTRYINDEX || -index <= lua_gettop(L);
}
inline void PushWeakTable(lua_State* L, void* key, const char* mode)
{
    lua_pushlightuserdata(L, key);
    lua_rawget(L, LUA_REGISTRYINDEX);
    if (lua_isnil(L, -1))
    {
        lua_pop(L, 1);
        lua_newtable(L);
        lua_newtable(L);
        lua_pushstring(L, mode);
        lua_setfield(L, -2, "__mode");
        lua_setmetatable(L, -2);
        lua_pushlightuserdata(L, key);
        lua_pushvalue(L, -2);
        lua_rawset(L, LUA_REGISTRYINDEX);
    }
    else if (!lua_istable(L, -1))
        luaL_error(L, "Borrowed object registry is invalid");
}
template<class T> inline Entry* AuthenticatedToken(lua_State* L, int index)
{
    if (!ValidIndex(L, index)) return NULL;
    index = AbsoluteIndex(L, index);
    if (lua_type(L, index) != LUA_TUSERDATA || lua_objlen(L, index) != sizeof(Entry)) return NULL;
    const int top = lua_gettop(L);
    lua_pushlightuserdata(L, RegistryKey<T, 1>());
    lua_rawget(L, LUA_REGISTRYINDEX);
    bool owned = false;
    if (lua_istable(L, -1))
    {
        lua_pushvalue(L, index);
        lua_rawget(L, -2);
        owned = lua_type(L, -1) == LUA_TBOOLEAN && lua_toboolean(L, -1) != 0;
    }
    lua_settop(L, top);
    return owned ? static_cast<Entry*>(lua_touserdata(L, index)) : NULL;
}
template<class T> inline int Finalize(lua_State* L)
{
    Entry* entry = AuthenticatedToken<T>(L, 1);
    if (entry) Detach(entry);
    return 0;
}
template<class T> inline void PushTokenMetatable(lua_State* L)
{
    lua_pushlightuserdata(L, RegistryKey<T, 2>());
    lua_rawget(L, LUA_REGISTRYINDEX);
    if (lua_isnil(L, -1))
    {
        lua_pop(L, 1);
        lua_newtable(L);
        lua_pushcfunction(L, Finalize<T>);
        lua_setfield(L, -2, "__gc");
        lua_pushlightuserdata(L, RegistryKey<T, 2>());
        lua_pushvalue(L, -2);
        lua_rawset(L, LUA_REGISTRYINDEX);
    }
    else if (!lua_istable(L, -1)) luaL_error(L, "Borrowed object metatable is invalid");
}
template<class T> inline T* Find(lua_State* L, int index)
{
    if (!ValidIndex(L, index)) return NULL;
    index = AbsoluteIndex(L, index);
    if (lua_type(L, index) != LUA_TTABLE) return NULL;
    const int top = lua_gettop(L);
    T* result = NULL;
    lua_pushlightuserdata(L, RegistryKey<T, 0>());
    lua_rawget(L, LUA_REGISTRYINDEX);
    if (lua_istable(L, -1))
    {
        lua_pushvalue(L, index);
        lua_rawget(L, -2);
        Entry* entry = AuthenticatedToken<T>(L, -1);
        if (entry)
        {
            lua_pushliteral(L, "__instance");
            lua_rawget(L, index);
            // Finish potentially allocating Lua work before sampling liveness.
            const void* target = Target(entry);
            if (target && lua_type(L, -1) == LUA_TLIGHTUSERDATA && lua_touserdata(L, -1) == target)
                result = static_cast<T*>(const_cast<void*>(target));
        }
    }
    lua_settop(L, top);
    return result;
}
template<class T> struct Request
{
    T* pointer;
    Entry watch;
    bool stored;
    lua_CFunction thunk;
};
template<class T> inline void Attach(lua_State* L, int index, Request<T>* request)
{
    index = AbsoluteIndex(L, index);
    const int top = lua_gettop(L);
    PushWeakTable(L, RegistryKey<T, 0>(), "k");
    const int wrappers = lua_gettop(L);
    PushWeakTable(L, RegistryKey<T, 1>(), "k");
    const int tokens = lua_gettop(L);
    PushTokenMetatable<T>(L);
    const int metatable = lua_gettop(L);
    Entry* entry = new(lua_newuserdata(L, sizeof(Entry))) Entry{};
    const int userdata = lua_gettop(L);
    lua_pushvalue(L, metatable);
    lua_setmetatable(L, userdata);
    lua_pushvalue(L, userdata);
    lua_pushboolean(L, 1);
    lua_rawset(L, tokens);
    lua_pushvalue(L, index);
    lua_pushvalue(L, userdata);
    lua_rawset(L, wrappers);

    // An allocating Lua API may have run arbitrary GC finalizers above.
    AcquireSRWLockExclusive(&State().lock);
    const bool allowed = request->watch.target == request->pointer && !FencedLocked(request->pointer);
    if (allowed) LinkLocked(entry, request->pointer, false);
    ReleaseSRWLockExclusive(&State().lock);
    if (!allowed) luaL_error(L, "Object was invalidated while creating its Lua reference");
    lua_settop(L, top);
}
template<class T> inline void StoreResult(lua_State* L, Request<T>* request)
{
    lua_pushlightuserdata(L, request);
    lua_pushvalue(L, -2);
    lua_rawset(L, LUA_REGISTRYINDEX);
    request->stored = true;
}
inline void CopyError(char (&destination)[256], const char* message)
{
    unsigned index = 0;
    if (message)
        while (index < sizeof(destination) - 1 && message[index])
        {
            destination[index] = message[index];
            ++index;
        }
    destination[index] = '\0';
}
template<class T> inline int ProtectedThunk(lua_State* L)
{
    Request<T>* request = static_cast<Request<T>*>(lua_touserdata(L, 1));
    char error[256] = {};
    try { return request->thunk(L); }
    catch (const std::exception& exception)
    {
        CopyError(error, exception.what());
    }
    catch (...) { CopyError(error, "Unknown native object registration failure"); }
    // The native exception and catch scope have ended before Lua unwinds.
    return luaL_error(L, "%s", error[0] ? error : "Native object registration failure");
}
template<class T> inline void Push(lua_State* L, T* pointer, lua_CFunction thunk)
{
    if (!pointer) { lua_pushnil(L); return; }
    if (!lua_checkstack(L, 8)) { luaL_error(L, "Insufficient Lua stack for object reference"); return; }
    Request<T> request = {pointer, {}, false, thunk};
    if (!Observe(&request.watch, pointer))
    {
        luaL_error(L, "Object is being reset or destroyed");
        return;
    }
    int status;
    try { status = lua_cpcall(L, ProtectedThunk<T>, &request); }
    catch (...)
    {
        Detach(&request.watch);
        if (request.stored)
        {
            lua_pushlightuserdata(L, &request);
            lua_pushnil(L);
            lua_rawset(L, LUA_REGISTRYINDEX);
        }
        throw;
    }
    const bool alive = Target(&request.watch) == pointer;
    Detach(&request.watch);
    if (status)
    {
        if (request.stored)
        {
            lua_pushlightuserdata(L, &request);
            lua_pushnil(L);
            lua_rawset(L, LUA_REGISTRYINDEX);
        }
        lua_error(L);
        return;
    }
    // The existing lightuserdata key is removed without allocation.
    lua_pushlightuserdata(L, &request);
    lua_rawget(L, LUA_REGISTRYINDEX);
    lua_pushlightuserdata(L, &request);
    lua_pushnil(L);
    lua_rawset(L, LUA_REGISTRYINDEX);
    if (!alive || !request.stored)
    {
        lua_pop(L, 1);
        luaL_error(L, "Object was invalidated while publishing its Lua reference");
    }
}
}
#endif
