// The same C++98 harness runs actual SDK x86 Lua and the x64 Lua candidate.
// It loads no GameCore module and exposes no game objects to Lua.
#include "lua.hpp"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <float.h>
#include <windows.h>

static unsigned long checks = 0;
static int finalized = 0;
static void require(bool condition)
{
    ++checks;
    if (!condition) { fprintf(stderr, "Lua trace assertion %lu failed\n", checks); exit(2); }
}
static int addUpvalue(lua_State* state)
{
    lua_pushinteger(state, lua_tointeger(state, 1) + lua_tointeger(state, lua_upvalueindex(1)));
    return 1;
}
static int finalize(lua_State*) { ++finalized; return 0; }
struct Chunk { char* bytes; size_t count; };
static int writeChunk(lua_State*, const void* bytes, size_t count, void* context)
{
    Chunk* chunk = static_cast<Chunk*>(context);
    char* next = static_cast<char*>(realloc(chunk->bytes, chunk->count + count));
    if (!next) return 1;
    chunk->bytes = next;
    memcpy(next + chunk->count, bytes, count);
    chunk->count += count;
    return 0;
}
static void runScripts(lua_State* state, FILE* trace)
{
    const char* scripts[] = {
        "local s=0 for i=1,10000 do s=s+(i*17)%991 end return s",
        "local t={} for i=3000,1,-1 do t[i]=(i*i)%997 end local s=0 for i=1,3000 do s=s+t[i] end return s",
        "local function outer(x) return function(y) x=x+y return x end end local f=outer(10) local s=0 for i=1,512 do s=s+f(i) end return s",
        "local t=setmetatable({},{__index=function(_,k) return k*7 end}) return t[93]",
        "local c=coroutine.create(function() for i=1,64 do coroutine.yield(i*i) end return 0 end) local s=0 while coroutine.status(c)~='dead' do local ok,v=coroutine.resume(c) assert(ok) s=s+v end return s",
        "local t={} for i=1,1024 do t[i]=1025-i end table.sort(t) local s=0 for i=1,#t do s=s+t[i]*i end return s",
        "local s='a'..string.char(0,128,255)..'z' assert(#s==5) local a,b,c=string.byte(s,2,4) return a+b*256+c*65536",
        "local n=0 for i=1,100 do local ok,e=pcall(function() error('expected',0) end) assert(not ok and e=='expected') n=n+1 end return n",
        "local t=setmetatable({},{__mode='v'}) do local x={} t[1]=x end collectgarbage('collect') return t[1]==nil and 1 or 0",
        "return math.floor(math.sqrt(123456789)) + math.abs(-1234) + math.max(1,7,3)",
        "local s,n=string.gsub('aa12 bb34 cc56','(%a+)(%d+)',function(a,b) return a..(tonumber(b)*2) end) assert(s=='aa24 bb68 cc112') return n",
        "local f=assert(loadstring('return function(x) return x*x+3 end'))() local d=string.dump(f) local g=assert(loadstring(d)) return g(317)"
    };
    luaL_openlibs(state);
    for (size_t i = 0; i < sizeof(scripts) / sizeof(scripts[0]); ++i) {
        lua_settop(state, 0);
        require(luaL_loadstring(state, scripts[i]) == 0 && lua_pcall(state, 0, 1, 0) == 0);
        require(lua_isnumber(state, -1) != 0);
        const __int64 result = static_cast<__int64>(lua_tointeger(state, -1));
        require(fwrite(&result, sizeof(result), 1, trace) == 1);
    }
    lua_settop(state, 0);
    lua_pushinteger(state, 19); lua_pushcclosure(state, addUpvalue, 1); lua_pushinteger(state, 23);
    require(lua_pcall(state, 1, 1, 0) == 0 && lua_tointeger(state, -1) == 42);
    lua_settop(state, 0);
    int* payload = static_cast<int*>(lua_newuserdata(state, sizeof(int)));
    *payload = 73;
    lua_newtable(state); lua_pushcfunction(state, finalize); lua_setfield(state, -2, "__gc");
    lua_setmetatable(state, -2);
    const int reference = luaL_ref(state, LUA_REGISTRYINDEX);
    lua_gc(state, LUA_GCCOLLECT, 0); require(finalized == 0);
    lua_rawgeti(state, LUA_REGISTRYINDEX, reference);
    require(lua_touserdata(state, -1) == payload && *payload == 73);
    lua_pop(state, 1); luaL_unref(state, LUA_REGISTRYINDEX, reference);
    lua_gc(state, LUA_GCCOLLECT, 0); require(finalized == 1);
    require(luaL_loadstring(state, "return 17*19") == 0);
    Chunk chunk = {NULL, 0};
    require(lua_dump(state, writeChunk, &chunk) == 0 && chunk.count > 12);
    lua_settop(state, 0);
    require(luaL_loadbuffer(state, chunk.bytes, chunk.count, "roundtrip") == 0);
    require(lua_pcall(state, 0, 1, 0) == 0 && lua_tointeger(state, -1) == 323);
    free(chunk.bytes);
}

int main(int argc, char** argv)
{
    require(argc == 4);
    FILE* input = fopen(argv[1], "rb"); FILE* output = fopen(argv[2], "wb"); FILE* scripts = fopen(argv[3], "wb");
    require(input && output && scripts);
    char magic[8]; unsigned int count = 0;
    require(fread(magic, 1, 8, input) == 8 && memcmp(magic, "ZLUA0001", 8) == 0);
    require(fread(&count, sizeof(count), 1, input) == 1);
    double* values = static_cast<double*>(malloc(sizeof(double) * count)); require(values != NULL);
    require(fread(values, sizeof(double), count, input) == count && fgetc(input) == EOF); fclose(input);
    lua_State* state = luaL_newstate(); require(state != NULL);
#ifndef _WIN64
    HMODULE module = GetModuleHandleA("lua51_Win32.dll");
    char loaded[MAX_PATH];
    require(module != NULL && GetModuleFileNameA(module, loaded, MAX_PATH) != 0);
    const char* separator = strrchr(argv[0], '\\'); require(separator != NULL);
    const size_t prefix = static_cast<size_t>(separator - argv[0]) + 1;
    require(_strnicmp(argv[0], loaded, prefix) == 0 && _stricmp(loaded + prefix, "lua51_Win32.dll") == 0);
#endif
    unsigned int originalControl = 0, currentControl = 0;
    require(_controlfp_s(&originalControl, 0, 0) == 0);
    const unsigned int modes[] = {_RC_NEAR, _RC_DOWN, _RC_UP, _RC_CHOP};
    for (unsigned int mode = 0; mode < 4; ++mode) {
        require(_controlfp_s(&currentControl, modes[mode], _MCW_RC) == 0);
        require((currentControl & _MCW_RC) == modes[mode]);
        for (unsigned int i = 0; i < count; ++i) {
            lua_settop(state, 0); lua_pushnumber(state, values[i]);
            const __int64 results[] = {static_cast<__int64>(lua_tointeger(state, 1)),
                static_cast<__int64>(luaL_checkinteger(state, 1)), static_cast<__int64>(luaL_optinteger(state, 1, 11))};
            require(fwrite(results, sizeof(results), 1, output) == 1);
        }
    }
    require(_controlfp_s(&currentControl, _RC_NEAR, _MCW_RC) == 0);
    runScripts(state, scripts);
    require(_controlfp_s(&currentControl, originalControl, _MCW_RC) == 0);
    lua_close(state); free(values);
    require(fclose(output) == 0 && fclose(scripts) == 0);
    printf("{\"status\":\"PASS\",\"inputs\":%u,\"rounding_modes\":4,\"conversion_results\":%u,"
           "\"script_cases\":12,\"checks\":%lu,\"lua_integer_bytes\":%u,\"pointer_bytes\":%u}\n",
           count, count*12, checks, static_cast<unsigned int>(sizeof(lua_Integer)), static_cast<unsigned int>(sizeof(void*)));
    return 0;
}
