#pragma once

#include <DatabaseResults.h>
#include <algorithm>
#include <climits>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>

extern "C" {
#include <lua.h>
#include <lauxlib.h>
}

namespace ZeroSisHost {
namespace GameDefinesDatabaseDetail {

enum class ValueKind { Null, Integer, Real, Text };

struct Entry {
    std::string name;
    std::string text;
    ValueKind kind = ValueKind::Null;
    double number = 0.0;
};

struct Snapshot {
    std::vector<Entry> entries;
};

inline void Require(Database::Connection& database, bool ok, const char* operation) {
    if (!ok) {
        const char* error = database.ErrorMessage();
        throw std::runtime_error(std::string(operation) + ": " + (error ? error : "database operation failed"));
    }
}

inline void Complete(Database::Connection& database) {
    const int code = database.ErrorCode();
    if (code != 0 && code != 101)
        throw std::runtime_error("Defines iteration failed");
}

inline Snapshot Read(Database::Connection& database) {
    // typeof(Value) reports SQLite's row storage class even when the declared
    // column affinity or the SDK provider's boolean mapping would hide it.
    Database::Results rows;
    Require(database, database.Execute(rows,
        "SELECT Name, Value, typeof(Value), length(CAST(Name AS BLOB)), "
        "length(CAST(Value AS BLOB)) FROM Defines ORDER BY Name"), "Defines query");
    if (rows.ColumnCount() != 5)
        throw std::runtime_error("Defines query returned an unexpected shape");

    Snapshot result;
    std::vector<std::string> names;
    while (rows.Step()) {
        if (rows.ColumnType(0) != Database::COLTYPE_TEXT)
            throw std::runtime_error("Defines.Name must be stored as text");
        const char* rawName = rows.GetText(0);
        const __int64 nameByteCount = rows.GetInt64(3);
        if (!rawName || nameByteCount <= 0 || nameByteCount > INT_MAX)
            throw std::runtime_error("Defines contains a null or empty Name");
        const int nameBytes = static_cast<int>(nameByteCount);

        Entry entry;
        entry.name.assign(rawName, static_cast<std::size_t>(nameBytes));
        if (std::find(names.begin(), names.end(), entry.name) != names.end())
            throw std::runtime_error("Defines contains a duplicate Name");
        names.push_back(entry.name);

        const char* storage = rows.GetText(2);
        if (!storage)
            throw std::runtime_error("SQLite returned no Defines.Value storage class");
        if (std::strcmp(storage, "null") == 0) {
            entry.kind = ValueKind::Null;
        } else if (std::strcmp(storage, "integer") == 0) {
            const __int64 value = rows.GetInt64(1);
            // Lua 5.1 numbers are doubles; reject values that cannot be
            // represented exactly instead of silently changing game rules.
            if (value < -9007199254740991LL || value > 9007199254740991LL)
                throw std::overflow_error("Defines integer is outside Lua 5.1's exact numeric range");
            entry.kind = ValueKind::Integer;
            entry.number = static_cast<double>(value);
        } else if (std::strcmp(storage, "real") == 0) {
            entry.kind = ValueKind::Real;
            entry.number = rows.GetDouble(1);
            if (!std::isfinite(entry.number))
                throw std::overflow_error("Defines real value must be finite");
        } else if (std::strcmp(storage, "text") == 0) {
            const __int64 valueByteCount = rows.GetInt64(4);
            const char* value = rows.GetText(1);
            if (valueByteCount < 0 || valueByteCount > INT_MAX || (valueByteCount > 0 && !value))
                throw std::runtime_error("Defines text value could not be read");
            const int valueBytes = static_cast<int>(valueByteCount);
            entry.kind = ValueKind::Text;
            entry.text.assign(value ? value : "", static_cast<std::size_t>(valueBytes));
        } else {
            throw std::runtime_error("Defines.Value uses an unsupported SQLite storage class");
        }

        if (result.entries.size() >= static_cast<std::size_t>(INT_MAX))
            throw std::overflow_error("Defines has too many entries for a Lua table");
        result.entries.push_back(std::move(entry));
    }
    Complete(database);
    return result;
}

// Invoked only by lua_cpcall. Its locals are trivial, so Lua's longjmp cannot
// skip a C++ destructor; the owning Snapshot remains in InstallGameDefines.
inline int Publish(lua_State* state) {
    const Snapshot* snapshot = static_cast<const Snapshot*>(lua_touserdata(state, 1));
    if (!snapshot)
        return luaL_error(state, "GameDefines snapshot is missing");

    lua_createtable(state, 0, static_cast<int>(snapshot->entries.size()));
    for (const Entry& entry : snapshot->entries) {
        lua_pushlstring(state, entry.name.data(), entry.name.size());
        switch (entry.kind) {
            case ValueKind::Null: lua_pushnil(state); break;
            case ValueKind::Integer:
            case ValueKind::Real: lua_pushnumber(state, entry.number); break;
            case ValueKind::Text:
                lua_pushlstring(state, entry.text.empty() ? "" : entry.text.data(), entry.text.size());
                break;
        }
        lua_rawset(state, -3);
    }
    lua_setglobal(state, "GameDefines");
    return 0;
}

struct InstallResult { char failure[1024]; int publishStatus; };

// Keep the owning C++ frame separate from the later lua_error frame. With
// MSVC /EHsc, longjmp can consult stale unwind state for an already destroyed
// block-local snapshot if both operations live in the same optimized frame.
__declspec(noinline) inline void PrepareAndPublish(lua_State* state, Database::Connection& database, InstallResult& result) {
    try {
        const Snapshot snapshot = Read(database);
        result.publishStatus = lua_cpcall(state, &Publish, const_cast<Snapshot*>(&snapshot));
    } catch (const std::exception& error) {
        std::snprintf(result.failure, sizeof(result.failure), "GameDefines: %s", error.what());
    } catch (...) {
        std::snprintf(result.failure, sizeof(result.failure), "GameDefines: unknown database failure");
    }
}

} // namespace GameDefinesDatabaseDetail

// Read the live rules database each time a VM is created. Call after the
// engine's GameInfo postprocessing when those updated numeric IDs are needed.
inline void InstallGameDefines(lua_State* state, Database::Connection& database) {
    GameDefinesDatabaseDetail::InstallResult result = {};
    GameDefinesDatabaseDetail::PrepareAndPublish(state, database, result);

    // This frame has no C++ owners, and PrepareAndPublish has already returned.
    if (result.failure[0])
        luaL_error(state, "%s", result.failure);
    if (result.publishStatus != 0)
        lua_error(state);
}

} // namespace ZeroSisHost
