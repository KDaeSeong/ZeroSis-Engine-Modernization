#pragma once
#include <CvGameDatabase.h>
#include <lua.hpp>
#include <stdexcept>
#include <string>
#include <vector>

// Called by CvLuaEnums::pRegister inside the existing FLua protected call.
// Lua uses C longjmp: only the POD callback below may perform allocating Lua
// operations while C++ row storage is live. A failed registration invalidates
// the initializing VM; its owner must discard it, not publish partial tables.
namespace ZeroSisLuaEnums {
struct Row { int value; std::string name; };
struct PublishCall {
    const Row* rows;
    std::size_t size;
    const char* countName;
    int count;
};

inline int Publish(lua_State* state) {
    const PublishCall* call = static_cast<const PublishCall*>(lua_touserdata(state, lua_upvalueindex(2)));
    lua_pushvalue(state, lua_upvalueindex(1));
    for (std::size_t i = 0; i < call->size; ++i) {
        lua_pushstring(state, call->rows[i].name.c_str());
        lua_pushvalue(state, -1);
        lua_pushinteger(state, call->rows[i].value);
        lua_rawset(state, -4);
        lua_rawseti(state, -2, call->rows[i].value);
    }
    if (call->countName) {
        lua_pushstring(state, call->countName);
        lua_pushinteger(state, call->count);
        lua_rawset(state, -3);
    }
    return 0;
}

inline void RegisterDynamic(lua_State* state, Database::Connection* database,
                            const char* table, const char* id, const char* name,
                            const char* countName) {
    if (!state || !database || !table || !*table || !id || !*id || !name || !*name)
        throw std::invalid_argument("Dynamic enum registration requires a VM, database and query fields");
    if (!lua_istable(state, -1))
        throw std::invalid_argument("Dynamic enum registration requires a destination table");
    const int base = lua_gettop(state);
    PublishCall call = {nullptr, 0, countName, 0};
    // Prepare the protected closure BEFORE constructing any owning C++ locals.
    // Setup OOM reaches the outer FLua boundary with no live Results/vector here.
    if (!lua_checkstack(state, 3)) throw std::length_error("Dynamic enum Lua stack capacity exhausted");
    lua_pushvalue(state, -1);
    lua_pushlightuserdata(state, &call);
    lua_pushcclosure(state, Publish, 2);
    try {
        std::vector<Row> rows;
        const std::string sql = std::string("select ") + id + ", " + name + " from " + table;
        {
            Database::Results results;
            if (!database->Execute(results, sql.c_str()))
                throw std::runtime_error("Dynamic enum database query failed");
            while (results.Step()) {
                const int value = results.GetInt(0);
                const char* text = results.GetText(1);
                if (!text) throw std::runtime_error("Dynamic enum name is NULL or unreadable");
                rows.push_back(Row{value, std::string(text)});
            }
            // SQLite 3.7.17 SQLITE_DONE, also used by the SDK DB cache boundary.
            if (database->ErrorCode() != 101)
                throw std::runtime_error("Dynamic enum database iteration failed");
        }
        if (countName) {
            call.count = database->Count(table, false);
            if (call.count < 0) throw std::runtime_error("Dynamic enum database count failed");
        }
        call.rows = rows.data();
        call.size = rows.size();
        // No DB statement remains open when Lua runs/collects finalizers.
        const int status = lua_pcall(state, 0, 0, 0);
        if (status != 0) {
            const char* error = lua_type(state, -1) == LUA_TSTRING
                ? lua_tostring(state, -1) : "Dynamic enum Lua publication failed";
            throw std::runtime_error(error);
        }
    } catch (...) {
        lua_settop(state, base);
        throw;
    }
    lua_settop(state, base);
}
}
