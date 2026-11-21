#include "lua.hpp"
#include "ScriptTableExtensions.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>

static unsigned checks=0;
static void Check(bool value,const char* message) {
    ++checks;
    if(!value) {
        std::fprintf(stderr,"HOST_SCRIPT_TABLES_FAILED check=%u %s\n",checks,message);
        std::exit(1);
    }
}

static int InstallProtected(lua_State* state) {
    ZeroSisHost::InstallScriptTableExtensions(state);
    return 0;
}

int main() {
    lua_State* state=luaL_newstate();
    Check(state!=nullptr,"Lua state allocation");
    luaL_openlibs(state);
    Check(lua_cpcall(state,&InstallProtected,nullptr)==0,"protected extension installation");
    Check(lua_gettop(state)==0,"installer stack balance");

    static const char source[]=R"lua(
local created=table.fill(7,4)
assert(type(created)=='table' and #created==4)
for i=1,4 do assert(created[i]==7) end

local empty=table.fill('unused',0)
assert(type(empty)=='table' and next(empty)==nil)

local shared={value=19}
local references=table.fill(shared,3)
assert(references[1]==shared and references[2]==shared and references[3]==shared)
assert(references[1]==references[3]) -- shallow repeated reference, not a deep copy

local existing={[1]='old',[4]='preserved'}
local returned=table.fill(existing,false,3)
assert(returned==existing)
assert(existing[1]==false and existing[2]==false and existing[3]==false)
assert(existing[4]=='preserved') -- only the requested prefix is overwritten

local function rejected(fn)
  local ok=pcall(fn)
  assert(not ok)
end
rejected(function() table.fill(1) end)
rejected(function() table.fill(1,2,3,4) end)
rejected(function() table.fill(false,1,2) end)
rejected(function() table.fill(0,'3') end)
rejected(function() table.fill(0,-1) end)
rejected(function() table.fill(0,1.5) end)
rejected(function() table.fill(0,0/0) end)
rejected(function() table.fill(0,math.huge) end)
rejected(function() table.fill(0,2147483648) end)
local unchanged={[1]='before'}
rejected(function() table.fill(unchanged,9,1.25) end)
assert(unchanged[1]=='before') -- invalid lengths are rejected before mutation
)lua";
    const int load=luaL_loadbuffer(state,source,sizeof(source)-1,"sdk-host-script-tables");
    if(load!=0) {
        const char* error=lua_tostring(state,-1);
        std::fprintf(stderr,"HOST_SCRIPT_TABLES_FAILED load=%s\n",error?error:"unknown Lua load error");
        lua_close(state);return 1;
    }
    const int call=lua_pcall(state,0,0,0);
    if(call!=0) {
        const char* error=lua_tostring(state,-1);
        std::fprintf(stderr,"HOST_SCRIPT_TABLES_FAILED run=%s\n",error?error:"unknown Lua runtime error");
        lua_close(state);return 1;
    }
    Check(lua_gettop(state)==0,"Lua test stack balance");
    lua_close(state);
    std::printf("HOST_SCRIPT_TABLES_PASS checks=%u GAMECORE_LOADED=false\n",checks);
    return 0;
}
