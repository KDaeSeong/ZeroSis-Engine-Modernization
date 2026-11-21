#include "UiSnapshotJson.h"
extern "C" {
#include <lauxlib.h>
#include <lualib.h>
}
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <windows.h>

static unsigned checks = 0;
static int failed = 0;
static char failure[1024] = {};

static void Check(bool ok, const char* message) {
    ++checks;
    if (!ok) {
        std::snprintf(failure, sizeof(failure), "%s", message);
        failed = 1;
    }
}

struct PushContext final {
    const std::string* value;
    int reference;
};

static int PushEncoded(lua_State* state) {
    PushContext* context = static_cast<PushContext*>(lua_touserdata(state, 1));
    const std::string* value = context ? context->value : nullptr;
    if (!value) return luaL_error(state, "missing encoded snapshot payload");
    lua_pushlstring(state, value->data(), value->size());
    context->reference = luaL_ref(state, LUA_REGISTRYINDEX);
    return 1;
}

static int SnapshotJson(lua_State* state) {
    const int originalTop = lua_gettop(state);
    char error[1024] = {};
    bool rejected = false;
    try {
        std::string encoded = ZeroSisHost::UiSnapshotJson::Encode(state, 1, 2);
        PushContext context = {&encoded, LUA_NOREF};
        const int pushStatus = lua_cpcall(state, &PushEncoded, &context);
        if (pushStatus != 0 || context.reference == LUA_NOREF) {
            const char* text = lua_tostring(state, -1);
            std::snprintf(error, sizeof(error), "%s", text ? text : "Lua allocation failed while returning UI JSON");
            lua_settop(state, originalTop);
            rejected = true;
        } else {
            if (!lua_checkstack(state, 1)) {
                luaL_unref(state, LUA_REGISTRYINDEX, context.reference);
                std::snprintf(error, sizeof(error), "%s", "Lua stack cannot grow to return UI JSON");
                lua_settop(state, originalTop);
                rejected = true;
            } else {
                lua_rawgeti(state, LUA_REGISTRYINDEX, context.reference);
                luaL_unref(state, LUA_REGISTRYINDEX, context.reference);
            }
            Check(lua_gettop(state) == originalTop + 1, "successful native callback stack result");
            if (!failed) return 1;
            std::snprintf(error, sizeof(error), "%s", failure);
            lua_settop(state, originalTop);
            rejected = true;
        }
    } catch (const std::exception& exception) {
        std::snprintf(error, sizeof(error), "%s", exception.what());
        rejected = true;
    } catch (...) {
        std::snprintf(error, sizeof(error), "%s", "unknown UI JSON encoder failure");
        rejected = true;
    }
    Check(lua_gettop(state) == originalTop, "rejected native callback restores Lua stack");
    if (failed) std::snprintf(error, sizeof(error), "%s", failure);
    if (rejected) {
        lua_settop(state, originalTop);
        lua_pushstring(state, error);
        return lua_error(state);
    }
    return 0;
}

static const char selfTest[] = R"lua(
local arrayType={}
local function enc(value) return __ZeroSisSnapshotJson(value,arrayType) end
local function rejected(fn)
  local ok,err=pcall(fn)
  assert(not ok and type(err)=='string' and #err>0)
end
local cases={}
cases.empty_array=enc(setmetatable({},arrayType));assert(cases.empty_array=='[]')
cases.empty_object=enc({});assert(cases.empty_object=='{}')
local sparse=setmetatable({[2]='ignored'},arrayType)
cases.sparse_array=enc(sparse);assert(cases.sparse_array=='[]')
local protectedArray=setmetatable({[2]='ignored'},{__metatable=arrayType})
cases.protected_array=enc(protectedArray);assert(cases.protected_array=='[]')
local ordered={z=3,a=1,m=2}
cases.sorted_object=enc(ordered);assert(cases.sorted_object=='{"a":1,"m":2,"z":3}')
local korean=string.char(236,149,136,235,133,149)
cases.utf8_and_controls=enc({text=korean,control='\0\1\31"\\'})
assert(cases.utf8_and_controls=='{"control":"\\u0000\\u0001\\u001f\\u0022\\u005c","text":"'..korean..'"}')
cases.finite_number=enc({n=1.2345678901234567})
assert(cases.finite_number=='{"n":1.2345678901234567}')
local shared={v=9};cases.shared_reference=enc({left=shared,right=shared})
assert(cases.shared_reference=='{"left":{"v":9},"right":{"v":9}}')
local noIndex=0
local ignored=setmetatable({ok=true},{__index=function() noIndex=noIndex+1;return 4 end})
cases.raw_metamethod=enc(ignored);assert(cases.raw_metamethod=='{"ok":true}' and noIndex==0)
local cycle={};cycle.self=cycle;rejected(function() enc(cycle) end)
rejected(function() enc(0/0) end)
rejected(function() enc(math.huge) end)
rejected(function() enc(function() end) end)
rejected(function() enc(coroutine.create(function() end)) end)
rejected(function() enc(newproxy(true)) end)
rejected(function() enc({[false]='bad'}) end)
assert(enc({[1]='array'})=='["array"]')
rejected(function() __ZeroSisSnapshotJson({},false) end)
local deep={};local cursor=deep
for i=1,129 do local nextValue={};cursor.child=nextValue;cursor=nextValue end
rejected(function() enc(deep) end)
local longKey=string.rep('k',1024*1024+1)
rejected(function() enc({[longKey]=true}) end)
local manyKeys={};for i=1,150000 do manyKeys['k'..i]=true end
rejected(function() enc(manyKeys) end)
local wide={};for i=1,1000000 do wide[i]=0 end
rejected(function() enc(wide) end)
rejected(function() enc(setmetatable({},wide)) end) -- raw metatable walk shares the visited-value budget
local nestedKeys={}
local overhead=__ZeroSisSnapshotJsonKeyOverhead
local maxKey=__ZeroSisSnapshotJsonMaxSingleKeyBytes
local maxTotal=__ZeroSisSnapshotJsonMaxTotalKeyBytes
for i=1,7 do nestedKeys[string.char(64+i)..string.rep('x',maxKey-1)]=true end
local tailSize=maxTotal-32-7*(maxKey+overhead)-overhead
nestedKeys['Z'..string.rep('z',tailSize-1)]=true
assert(pcall(enc,nestedKeys)) -- the child table alone fits just below the combined live-key bound
rejected(function() enc({nested=nestedKeys}) end) -- parent key storage remains live during child encoding
rejected(function() enc(string.rep('x',32*1024*1024+1)) end)
arrayType.__metatable=false
local maskedMarker=setmetatable({[2]='not-ipairs-array'},arrayType)
if #maskedMarker>0 then assert(enc(maskedMarker)=='[]') else rejected(function() enc(maskedMarker) end) end
snapshot_json_report={status='UI_SNAPSHOT_JSON_TEST_PASS',checks=20,cases=cases,
  rejection_cases=13,metamethod_reads=noIndex,source='Lua 5.1 shared provider'}
)lua";

static int RunChunk(lua_State* state, const char* bytes, std::size_t size, const char* name) {
    if (luaL_loadbuffer(state, bytes, size, name) != 0) return 1;
    return lua_pcall(state, 0, 0, 0);
}

static int NoopPrint(lua_State*) { return 0; }

int main(int argc, char** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    const std::string quote = ZeroSisHost::UiSnapshotJson::Quote(std::string("Q\0\"\\\x1f", 5));
    Check(quote == "\"Q\\u0000\\u0022\\u005c\\u001f\"", "standalone Quote escaping");
    lua_State* state = luaL_newstate();
    if (!state) { std::fprintf(stderr, "UI_SNAPSHOT_JSON_FAILED state allocation\n"); return 1; }
    luaL_openlibs(state);
    lua_pushcfunction(state, &SnapshotJson);
    lua_setglobal(state, "__ZeroSisSnapshotJson");
    lua_pushinteger(state, static_cast<lua_Integer>(2 * sizeof(std::string)));
    lua_setglobal(state, "__ZeroSisSnapshotJsonKeyOverhead");
    lua_pushinteger(state, static_cast<lua_Integer>(ZeroSisHost::UiSnapshotJson::MaxSingleKeyBytes));
    lua_setglobal(state, "__ZeroSisSnapshotJsonMaxSingleKeyBytes");
    lua_pushinteger(state, static_cast<lua_Integer>(ZeroSisHost::UiSnapshotJson::MaxTotalKeyBytes));
    lua_setglobal(state, "__ZeroSisSnapshotJsonMaxTotalKeyBytes");
    if (argc == 4 && std::strcmp(argv[1], "--run") == 0) {
        lua_pushcfunction(state, &NoopPrint);
        lua_setglobal(state, "print");
    }

    int status = 0;
    if (argc == 1) {
        status = RunChunk(state, selfTest, sizeof(selfTest) - 1, "ui-snapshot-json-self-test");
    } else if (argc == 4 && std::strcmp(argv[1], "--run") == 0) {
        if (luaL_loadfile(state, argv[2]) != 0) status = 1;
        else status = lua_pcall(state, 0, 0, 0);
        if (status == 0) {
            lua_getglobal(state, argv[3]);
            if (lua_type(state, -1) != LUA_TSTRING) {
                std::fprintf(stderr, "UI_SNAPSHOT_JSON_FAILED report global is not a JSON string\n"); status = 1;
            } else {
                std::size_t size = 0; const char* value = lua_tolstring(state, -1, &size);
                if (std::fputs("UI_SNAPSHOT_JSON_REPORT=", stdout) == EOF || !value ||
                    std::fwrite(value, 1, size, stdout) != size || std::fputc('\n', stdout) == EOF) status = 1;
            }
        }
    } else {
        std::fprintf(stderr, "usage: ui_snapshot_json_tests.exe [--run <harness.lua> <reportGlobal>]\n");
        status = 2;
    }
    if (status != 0) {
        const char* error = lua_tostring(state, -1);
        std::fprintf(stderr, "UI_SNAPSHOT_JSON_FAILED %s\n", error ? error : "Lua harness failed");
        lua_close(state); return 1;
    }
    if (argc == 1) {
        lua_getglobal(state, "snapshot_json_report");
        if (lua_type(state, -1) != LUA_TTABLE) { lua_close(state); return 1; }
        lua_getfield(state, -1, "status");
        const char* marker = lua_tostring(state, -1);
        if (!marker || std::strcmp(marker, "UI_SNAPSHOT_JSON_TEST_PASS") != 0) { lua_close(state); return 1; }
        std::printf("UI_SNAPSHOT_JSON_TEST_PASS checks=%u GAMECORE_LOADED=false\n", checks);
    }
    lua_close(state);
    return 0;
}
