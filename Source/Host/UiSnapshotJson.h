#pragma once

extern "C" {
#include <lua.h>
}

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <limits>
#include <locale.h>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

namespace ZeroSisHost {
namespace UiSnapshotJson {

constexpr std::size_t MaxDepth = 128;
constexpr std::size_t MaxVisitedValues = 1000000;
constexpr std::size_t MaxOutputBytes = 32u * 1024u * 1024u;
constexpr std::size_t MaxSingleKeyBytes = 1024u * 1024u;
constexpr std::size_t MaxTotalKeyBytes = 8u * 1024u * 1024u;

class StackRestore final {
public:
    explicit StackRestore(lua_State* state) noexcept : state_(state), top_(lua_gettop(state)) {}
    ~StackRestore() { lua_settop(state_, top_); }
    StackRestore(const StackRestore&) = delete;
    StackRestore& operator=(const StackRestore&) = delete;
private:
    lua_State* state_;
    int top_;
};

inline int AbsoluteIndex(lua_State* state, int index) {
    if (index > 0 || index <= LUA_REGISTRYINDEX) return index;
    return lua_gettop(state) + index + 1;
}

inline void Append(std::string& out, const char* bytes, std::size_t size) {
    if (size > MaxOutputBytes - out.size()) throw std::length_error("UI snapshot JSON exceeds 32 MiB");
    out.append(bytes, size);
}

inline void AppendChar(std::string& out, char value) { Append(out, &value, 1); }

inline std::string Quote(const std::string& value) {
    std::string out;
    if (value.size() > MaxOutputBytes - 2) throw std::length_error("UI snapshot JSON string exceeds output bound");
    out.reserve(value.size() + 2);
    AppendChar(out, '"');
    static const char hex[] = "0123456789abcdef";
    for (unsigned char byte : value) {
        if (byte < 0x20 || byte == '"' || byte == '\\') {
            char escaped[6] = {'\\', 'u', '0', '0', hex[byte >> 4], hex[byte & 0x0f]};
            Append(out, escaped, sizeof(escaped));
        } else {
            AppendChar(out, static_cast<char>(byte));
        }
    }
    AppendChar(out, '"');
    return out;
}

class Encoder final {
public:
    explicit Encoder(lua_State* state) : state_(state), visited_(0), totalKeyBytes_(0),
        temporaryValueBytes_(0), workBytes_(0) {}

    std::string Run(int valueIndex, int arrayMarkerIndex) {
        if (!state_) throw std::invalid_argument("UI snapshot Lua state is null");
        const int value = AbsoluteIndex(state_, valueIndex);
        const int marker = AbsoluteIndex(state_, arrayMarkerIndex);
        if (value <= 0 || value > lua_gettop(state_) || marker <= 0 || marker > lua_gettop(state_))
            throw std::invalid_argument("UI snapshot indices must refer to stack values");
        if (lua_type(state_, marker) != LUA_TTABLE)
            throw std::invalid_argument("UI snapshot array marker must be a table");
        if (!lua_checkstack(state_, 8)) throw std::runtime_error("Lua stack cannot grow for UI snapshot encoding");
        StackRestore restore(state_);
        std::string output;
        output.reserve(1024);
        std::unordered_set<const void*> activeTables;
        Value(value, marker, 0, output, activeTables);
        return output;
    }

private:
    struct Key final {
        std::string bytes;
        std::string encodedValue;
    };

    struct ByteLess final {
        bool operator()(const Key& left, const Key& right) const noexcept {
            return std::lexicographical_compare(left.bytes.begin(), left.bytes.end(),
                                                right.bytes.begin(), right.bytes.end(),
                [](unsigned char a, unsigned char b) { return a < b; });
        }
    };

    void Visit() {
        if (visited_ >= MaxVisitedValues) throw std::length_error("UI snapshot exceeds one million visited values");
        ++visited_;
    }

    void Write(std::string& out, const char* bytes, std::size_t size) {
        if (size > MaxOutputBytes - out.size()) throw std::length_error("UI snapshot JSON exceeds 32 MiB");
        constexpr std::size_t MaxWorkBytes = 128u * 1024u * 1024u;
        if (size > MaxWorkBytes - workBytes_) throw std::length_error("UI snapshot JSON work exceeds its bound");
        workBytes_ += size;
        out.append(bytes, size);
    }

    void WriteChar(std::string& out, char value) { Write(out, &value, 1); }

    void String(const char* bytes, std::size_t size, std::string& out) {
        if (size > MaxOutputBytes - 2) throw std::length_error("UI snapshot string exceeds output bound");
        WriteChar(out, '"');
        static const char hex[] = "0123456789abcdef";
        for (std::size_t i = 0; i < size; ++i) {
            const unsigned char byte = static_cast<unsigned char>(bytes[i]);
            if (byte < 0x20 || byte == '"' || byte == '\\') {
                const char escaped[6] = {'\\', 'u', '0', '0', hex[byte >> 4], hex[byte & 0x0f]};
                Write(out, escaped, sizeof(escaped));
            } else WriteChar(out, static_cast<char>(byte));
        }
        WriteChar(out, '"');
    }

    void Number(lua_State* state, int index, std::string& out) {
        const double value = lua_tonumber(state, index);
        if (!std::isfinite(value)) throw std::invalid_argument("UI snapshot contains a non-finite number");
        static _locale_t cLocale = _create_locale(LC_NUMERIC, "C");
        if (!cLocale) throw std::runtime_error("Cannot create the C numeric locale for UI snapshot encoding");
        char buffer[64];
        const int count = _snprintf_l(buffer, sizeof(buffer), "%.17g", cLocale, value);
        if (count <= 0 || static_cast<std::size_t>(count) >= sizeof(buffer))
            throw std::runtime_error("Cannot format UI snapshot number");
        Write(out, buffer, static_cast<std::size_t>(count));
    }

    void Value(int index, int marker, std::size_t depth, std::string& out,
               std::unordered_set<const void*>& activeTables) {
        if (depth > MaxDepth) throw std::length_error("UI snapshot exceeds depth 128");
        Visit();
        if (!lua_checkstack(state_, 8)) throw std::runtime_error("Lua stack cannot grow during UI snapshot encoding");
        const int top = lua_gettop(state_);
        StackRestore restore(state_);
        const int absolute = AbsoluteIndex(state_, index);
        const int type = lua_type(state_, absolute);
        switch (type) {
        case LUA_TSTRING: {
            std::size_t size = 0;
            const char* value = lua_tolstring(state_, absolute, &size);
            if (!value) throw std::runtime_error("Lua string pointer is unavailable");
            String(value, size, out);
            return;
        }
        case LUA_TBOOLEAN:
            Write(out, lua_toboolean(state_, absolute) ? "true" : "false", lua_toboolean(state_, absolute) ? 4 : 5);
            return;
        case LUA_TNUMBER:
            Number(state_, absolute, out);
            return;
        case LUA_TTABLE:
            Table(absolute, marker, depth, top, out, activeTables);
            return;
        default:
            throw std::invalid_argument("UI snapshot contains an unsupported Lua value");
        }
    }

    void Table(int index, int marker, std::size_t depth, int top, std::string& out,
               std::unordered_set<const void*>& activeTables) {
        const void* identity = lua_topointer(state_, index);
        if (!identity || !activeTables.insert(identity).second) throw std::invalid_argument("UI snapshot contains a table cycle");
        struct ActiveErase final {
            std::unordered_set<const void*>& values;
            const void* identity;
            ~ActiveErase() { values.erase(identity); }
        } erase = {activeTables, identity};

        bool isArray = ArrayMarkerVisibleThroughLuaApi(index, marker, top);
        if (!isArray) isArray = lua_objlen(state_, index) > 0;
        if (isArray) {
            WriteChar(out, '[');
            bool first = true;
            for (int i = 1; ; ++i) {
                lua_rawgeti(state_, index, i);
                if (lua_isnil(state_, -1)) { lua_settop(state_, top); break; }
                if (!first) WriteChar(out, ',');
                Value(-1, marker, depth + 1, out, activeTables);
                lua_settop(state_, top);
                first = false;
                if (i == (std::numeric_limits<int>::max)()) throw std::length_error("Lua array index exceeds integer range");
            }
            WriteChar(out, ']');
            return;
        }

        std::vector<Key> keys;
        struct KeyStorageRestore final {
            std::size_t& total;
            std::size_t bytes;
            ~KeyStorageRestore() { total -= bytes; }
        } keyStorageRestore = {totalKeyBytes_, 0};
        lua_settop(state_, top);
        lua_pushnil(state_);
        while (lua_next(state_, index) != 0) {
            if (lua_type(state_, -2) != LUA_TSTRING)
                throw std::invalid_argument("UI snapshot object contains a non-string key");
            std::size_t size = 0;
            const char* key = lua_tolstring(state_, -2, &size);
            if (!key || size > MaxSingleKeyBytes || totalKeyBytes_ > MaxTotalKeyBytes ||
                sizeof(Key) > MaxTotalKeyBytes - totalKeyBytes_ ||
                size > MaxTotalKeyBytes - totalKeyBytes_ - sizeof(Key))
                throw std::length_error("UI snapshot key size exceeds its bound");
            const std::size_t reserved = size + sizeof(Key);
            totalKeyBytes_ += reserved;
            keyStorageRestore.bytes += reserved;
            if (keys.size() >= MaxVisitedValues) throw std::length_error("UI snapshot object has too many keys");
            Key entry{std::string(key, size), std::string()};
            Value(-1, marker, depth + 1, entry.encodedValue, activeTables);
            const std::size_t held = entry.encodedValue.size();
            constexpr std::size_t MaxTemporaryValueBytes = 32u * 1024u * 1024u;
            if (held > MaxTemporaryValueBytes - temporaryValueBytes_)
                throw std::length_error("UI snapshot temporary object values exceed 32 MiB");
            temporaryValueBytes_ += held;
            keys.push_back(std::move(entry));
            lua_pop(state_, 1); // retain the key required by lua_next
        }
        lua_settop(state_, top);
        struct TemporaryRestore final {
            std::size_t& total;
            std::size_t bytes;
            ~TemporaryRestore() { total -= bytes; }
        } temporaryRestore = {temporaryValueBytes_, 0};
        for (const auto& key : keys) temporaryRestore.bytes += key.encodedValue.size();
        std::sort(keys.begin(), keys.end(), ByteLess{});
        for (std::size_t i = 1; i < keys.size(); ++i)
            if (keys[i - 1].bytes == keys[i].bytes) throw std::invalid_argument("UI snapshot has duplicate object keys");

        WriteChar(out, '{');
        for (std::size_t i = 0; i < keys.size(); ++i) {
            if (i) WriteChar(out, ',');
            String(keys[i].bytes.data(), keys[i].bytes.size(), out);
            WriteChar(out, ':');
            Write(out, keys[i].encodedValue.data(), keys[i].encodedValue.size());
        }
        WriteChar(out, '}');
    }

    bool ArrayMarkerVisibleThroughLuaApi(int table, int marker, int top) {
        if (!lua_getmetatable(state_, table)) return false;
        const int metatable = AbsoluteIndex(state_, -1);
        const bool actualMatches = lua_rawequal(state_, metatable, marker) != 0;
        lua_pushnil(state_);
        bool hasProtectedValue = false;
        bool protectedValueMatches = false;
        while (lua_next(state_, metatable) != 0) {
            Visit();
            if (lua_type(state_, -2) == LUA_TSTRING) {
                std::size_t size = 0;
                const char* key = lua_tolstring(state_, -2, &size);
                if (key && size == 11 && std::memcmp(key, "__metatable", 11) == 0) {
                    hasProtectedValue = true;
                    protectedValueMatches = lua_rawequal(state_, -1, marker) != 0;
                    break;
                }
            }
            lua_pop(state_, 1);
        }
        lua_settop(state_, top);
        return hasProtectedValue ? protectedValueMatches : actualMatches;
    }

    lua_State* state_;
    std::size_t visited_;
    std::size_t totalKeyBytes_;
    std::size_t temporaryValueBytes_;
    std::size_t workBytes_;
};

inline std::string Encode(lua_State* state, int valueIndex, int arrayMarkerIndex) {
    return Encoder(state).Run(valueIndex, arrayMarkerIndex);
}

} // namespace UiSnapshotJson
} // namespace ZeroSisHost
